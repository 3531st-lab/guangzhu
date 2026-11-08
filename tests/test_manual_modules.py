"""Manual panel edits keep catalogue dimensions, roof contact and atomic locks."""
import json
import math

import numpy as np
import pytest
from shapely.geometry import Polygon

from guangzhu import layout, project as storage
from guangzhu.config import DATA_DIR
from guangzhu.models import Design, GzError, LayoutParams, Project, Roof
from guangzhu.roofplane import elevation, generate


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    def make(kind='flat', **params):
        source = json.loads((DATA_DIR / 'demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
        source.update(id='manual-' + kind, designs=[], requirements={})
        value = dict(type=kind, outline=[[0, 0], [40, 0], [40, 24], [0, 24]], height_m=9,
                     parapet_height_m=0, load_capacity_kn_m2=2, obstacles=[], keepouts=[])
        if kind == 'metal':
            value.update(slope_deg=30, slope_azimuth_deg=180)
        if kind == 'pitched':
            value.update(generate(value['outline'], dict(kind='gable', slope_deg=30, ridge=[[20, -20], [20, 40]])))
        source['roof'] = value
        source['equipment']['racking'] = {'flat': 'ballast_tilt', 'metal': 'clamp_flush', 'pitched': 'plane_flush'}[kind]
        record = storage.save(Project.model_validate(source))
        design = storage.save_design(record.id, Design(params=LayoutParams(tilt_deg=15, **params)), offline=True)
        return record, design
    return make


def edit(record, version, ops, author='user'):
    result = storage.edit_design(record.id, version, ops, '手动位置核验', author, offline=True)
    return storage.load_design(record.id, result['version'])


def add(record, design, placements):
    return edit(record, design.version, [dict(op='add_modules', placements=placements)])


def geometry(module, record, design):
    catalogue, _, lower = layout._catalog(record, design.params)
    long, short = float(catalogue['length_m']), float(catalogue['width_m'])
    depth, width = (long, short) if module.orientation == 'portrait' else (short, long)
    corners = np.array(module.corners)
    u, v = corners[1] - corners[0], corners[3] - corners[0]
    assert np.linalg.norm(u) == pytest.approx(width, abs=1e-9)
    assert np.linalg.norm(v) == pytest.approx(depth, abs=1e-9)
    assert np.dot(u, v) == pytest.approx(0, abs=1e-9)
    np.testing.assert_allclose(corners.mean(axis=0), module.center, atol=1e-10)
    np.testing.assert_allclose(corners[2], corners[1] + corners[3] - corners[0], atol=1e-10)
    normal = np.cross(u, v)
    normal /= np.linalg.norm(normal)
    beta, bearing = math.radians(module.tilt), math.radians(module.azimuth)
    np.testing.assert_allclose(normal, [math.sin(beta) * math.sin(bearing), math.sin(beta) * math.cos(bearing), math.cos(beta)], atol=1e-9)
    if record.roof.type in ('metal', 'pitched'):
        pid = int(module.id.split('-')[0][1:]) if record.roof.type == 'pitched' else None
        assert all(p[2] - elevation(record.roof, p, pid) == pytest.approx(lower, abs=1e-9) for p in module.corners)
    else:
        assert min(corners[:, 2]) == pytest.approx(lower, abs=1e-9)


def test_empty_design_add_preview_commit_move_rotate_and_undo(factory):
    record, initial = factory()
    before = storage._path(record.id, 'designs/v1.json').read_bytes()
    ops = [dict(op='add_modules', placements=[dict(center=[5, 5]), dict(center=[12, 5], orientation='landscape', rotation_deg=30)])]
    preview = storage.preview_edit(record.id, 1, ops, '补放', offline=True)
    assert storage.next_version(record.id) == 2
    assert len(preview['changes']['added']) == 2 and preview['changes']['analysis_status'] == 'not_recomputed'
    result = storage.edit_design(record.id, 1, ops, '补放', 'user', offline=True, expected_fingerprint=preview['fingerprint'])
    placed = storage.load_design(record.id, result['version'])
    assert placed.statistics['manual_edits'] and placed.statistics['partial_reflow']
    assert placed.statistics['module_count'] == 2
    assert placed.statistics['dc_kw'] == pytest.approx(1.1)
    assert [m.row for m in placed.modules] == [1, 2]
    for module in placed.modules:
        geometry(module, record, placed)
    mid = placed.modules[0].id
    moved = edit(record, 2, [dict(op='move_modules', module_ids=[mid], dx_m=2, dy_m=3)])
    assert moved.modules[0].id == mid
    assert moved.modules[0].center[:2] == pytest.approx((7, 8))
    rotated = edit(record, 3, [dict(op='rotate_modules', module_ids=[mid], angle_deg=37)])
    assert rotated.modules[0].azimuth == pytest.approx(217)
    np.testing.assert_allclose(rotated.modules[0].center, moved.modules[0].center)
    geometry(rotated.modules[0], record, rotated)
    assert rotated.modules[1] == moved.modules[1]
    undone = edit(record, 4, [dict(op='undo_last_edit')])
    assert undone.modules == moved.modules and undone.statistics['manual_edits']
    assert storage._path(record.id, 'designs/v1.json').read_bytes() == before
    assert not storage._path(record.id, 'analysis/v4').exists()


@pytest.mark.parametrize('kind', ['metal', 'pitched'])
@pytest.mark.parametrize('turn', [37, 90, -123])
def test_flush_rotation_is_rigid_in_real_roof_plane_and_move_keeps_contact(factory, kind, turn):
    record, initial = factory(kind)
    placement = dict(center=[10, 10])
    if kind == 'pitched':
        plane = record.roof.planes[0]
        placement.update(center=list(Polygon(plane.outline).centroid.coords[0]), plane_id=plane.id)
    placed = add(record, initial, [placement])
    original = placed.modules[0]
    rotated = edit(record, 2, [dict(op='rotate_modules', module_ids=[original.id], angle_deg=turn)])
    actual = rotated.modules[0]
    assert actual.tilt == original.tilt and actual.azimuth == original.azimuth
    assert actual.orientation == original.orientation
    np.testing.assert_allclose(actual.center, original.center, atol=1e-10)
    geometry(actual, record, rotated)
    moved = edit(record, 3, [dict(op='move_modules', module_ids=[actual.id], dx_m=.4, dy_m=.6)])
    geometry(moved.modules[0], record, moved)
    np.testing.assert_allclose(np.subtract(moved.modules[0].corners[1], moved.modules[0].corners[0]),
                               np.subtract(actual.corners[1], actual.corners[0]), atol=1e-10)


def test_flush_minimum_gap_measures_real_plane_distance(factory):
    record, initial = factory('metal')
    catalogue, gap, _ = layout._catalog(record, initial.params)
    spacing = (float(catalogue['length_m']) + gap) * math.cos(math.radians(30))
    placed = add(record, initial, [dict(center=[10, 8]), dict(center=[10, 8 + spacing])])
    assert len(placed.modules) == 2
    with pytest.raises(GzError) as error:
        edit(record, 2, [dict(op='move_modules', module_ids=[placed.modules[1].id], dx_m=0, dy_m=-.005)])
    assert error.value.error_code == 'MANUAL_MODULE_COLLISION'


@pytest.mark.parametrize('placement,code', [
    (dict(center=[.2, 5]), 'MANUAL_MODULE_CLEARANCE'),
    (dict(center=[5, 5]), 'MANUAL_MODULE_COLLISION'),
    (dict(center=[6.101, 5]), 'MANUAL_MODULE_COLLISION'),
])
def test_add_batch_failure_is_atomic_for_edge_overlap_and_minimum_spacing(factory, placement, code):
    record, initial = factory()
    before = storage._path(record.id, 'designs/v1.json').read_bytes()
    with pytest.raises(GzError) as error:
        add(record, initial, [dict(center=[5, 5]), placement])
    assert error.value.error_code == code
    assert storage.next_version(record.id) == 2
    assert storage._path(record.id, 'designs/v1.json').read_bytes() == before


def test_obstacles_keepouts_added_keepouts_and_height_are_enforced(factory):
    record, initial = factory()
    raw = record.model_dump()
    raw['roof']['obstacles'] = [dict(id='unit', label='设备', kind='prism', height_m=2,
                                    footprint=[[8, 8], [12, 8], [12, 12], [8, 12]])]
    raw['roof']['keepouts'] = [dict(id='sky', label='天窗', polygon=[[18, 8], [22, 8], [22, 12], [18, 12]])]
    record = storage.save(raw)
    for center in ([10, 10], [20, 10]):
        with pytest.raises(GzError, match='避让'):
            add(record, initial, [dict(center=center)])
    with_zone = edit(record, 1, [dict(op='add_keepout', label='走道', polygon=[[27, 2], [32, 2], [32, 10], [27, 10]])])
    with pytest.raises(GzError, match='避让'):
        add(record, with_zone, [dict(center=[30, 5])])
    record.requirements.structured.max_height_m = .4
    storage.save(record)
    with pytest.raises(GzError, match='限高'):
        add(record, with_zone, [dict(center=[5, 5])])


def test_locked_empty_regions_and_modules_cannot_be_occupied_or_moved(factory):
    record, initial = factory()
    locked = edit(record, 1, [dict(op='lock_region', id='empty', polygon=[[2, 2], [8, 2], [8, 8], [2, 8]])])
    with pytest.raises(GzError) as error:
        add(record, locked, [dict(center=[5, 5])])
    assert error.value.error_code == 'DESIGN_LOCK_CONFLICT'
    placed = add(record, locked, [dict(center=[14, 5])])
    mid = placed.modules[0].id
    with pytest.raises(GzError) as error:
        edit(record, placed.version, [dict(op='move_modules', module_ids=[mid], dx_m=-9, dy_m=0)])
    assert error.value.error_code == 'DESIGN_LOCK_CONFLICT'
    protected = edit(record, placed.version, [dict(op='lock_modules', module_ids=[mid])])
    with pytest.raises(GzError, match='锁定'):
        edit(record, protected.version, [dict(op='rotate_modules', module_ids=[mid], angle_deg=90)])
    with pytest.raises(GzError) as error:
        edit(record, protected.version, [dict(op='unlock_modules', module_ids=[mid]),
                                         dict(op='move_modules', module_ids=[mid], dx_m=2, dy_m=0)], author='agent')
    assert error.value.error_code == 'DESIGN_LOCK_USER_REQUIRED'
    moved = edit(record, protected.version, [dict(op='unlock_modules', module_ids=[mid]),
                                            dict(op='move_modules', module_ids=[mid], dx_m=2, dy_m=0)])
    assert moved.modules[0].center[0] == pytest.approx(16)


def test_pitched_requires_plane_and_blocks_empty_plane_locks_and_crossings(factory):
    record, initial = factory('pitched')
    plane = record.roof.planes[0]
    center = list(Polygon(plane.outline).centroid.coords[0])
    with pytest.raises(GzError):
        add(record, initial, [dict(center=center)])
    protected = edit(record, 1, [dict(op='lock_plane', plane_id=plane.id)])
    with pytest.raises(GzError) as error:
        add(record, protected, [dict(center=center, plane_id=plane.id)])
    assert error.value.error_code == 'DESIGN_LOCK_CONFLICT'
    placed = edit(record, protected.version, [dict(op='unlock_plane', plane_id=plane.id),
        dict(op='add_modules', placements=[dict(center=center, plane_id=plane.id)])])
    with pytest.raises(GzError, match='可安装'):
        edit(record, placed.version, [dict(op='move_modules', module_ids=[placed.modules[0].id], dx_m=20 if center[0] < 20 else -20, dy_m=0)])


def test_move_then_old_shading_delete_rejected_and_new_version_has_no_old_analysis(factory):
    record, initial = factory()
    placed = add(record, initial, [dict(center=[5, 5])])
    shadow = storage._path(record.id, 'analysis/v2/shading.json')
    shadow.parent.mkdir(parents=True)
    shadow.write_text(json.dumps(dict(version=2, modules=[dict(id=placed.modules[0].id, total_loss_pct=10)])), encoding='utf-8')
    move = dict(op='move_modules', module_ids=[placed.modules[0].id], dx_m=2, dy_m=0)
    with pytest.raises(GzError) as error:
        edit(record, 2, [move, dict(op='remove_modules', where=dict(worst_count=1))])
    assert error.value.error_code == 'DESIGN_EDIT_DEPENDENCY'
    moved = edit(record, 2, [move])
    assert not storage._path(record.id, f'analysis/v{moved.version}/shading.json').exists()
    with pytest.raises(GzError) as error:
        edit(record, moved.version, [dict(op='remove_modules', where=dict(worst_count=1))])
    assert error.value.error_code == 'ANALYSIS_MISSING'


@pytest.mark.parametrize('operation', [
    dict(op='add_modules', placements=[]), dict(op='add_modules', placements=[dict(center=[5, 5])]*101),
    dict(op='add_modules', placements=[dict(center=[True, 5])]),
    dict(op='add_modules', placements=[dict(center=[5, 5], rotation_deg=361)]),
    dict(op='add_modules', placements=[dict(center=[5, 5], orientation='diagonal')]),
    dict(op='add_modules', placements=[dict(center=[5, 5], corners=[])]),
    dict(op='move_modules', module_ids=[], dx_m=1, dy_m=0),
    dict(op='move_modules', module_ids=['unknown'], dx_m=1, dy_m=0),
    dict(op='rotate_modules', module_ids=['R01-1-C001'], angle_deg=float('nan')),
])
def test_invalid_manual_payloads_do_not_create_versions(factory, operation):
    record, initial = factory()
    with pytest.raises(GzError):
        edit(record, initial.version, [operation])
    assert storage.next_version(record.id) == 2


@pytest.mark.parametrize('params', [dict(layout='ew'), dict(rows_per_rack=2)])
def test_group_racks_are_explicitly_unsupported(factory, params):
    record, initial = factory(**params)
    with pytest.raises(GzError) as error:
        add(record, initial, [dict(center=[5, 5])])
    assert error.value.error_code == 'MANUAL_MODULE_UNSUPPORTED'


def test_undo_first_manual_edit_keeps_calculation_method_marker(factory):
    record, initial = factory()
    placed = add(record, initial, [dict(center=[5, 5])])
    restored = edit(record, placed.version, [dict(op='undo_last_edit')])
    assert restored.modules == []
    assert restored.statistics['geometry_sky'] is True
    assert not restored.statistics.get('manual_edits')


@pytest.mark.parametrize('operation', [dict(op='move_modules', dx_m=0, dy_m=0),
    dict(op='rotate_modules', angle_deg=0), dict(op='rotate_modules', angle_deg=360),
    dict(op='rotate_modules', angle_deg=-360)])
def test_equivalent_transform_does_not_create_a_spurious_version(factory, operation):
    record, initial = factory()
    placed = add(record, initial, [dict(center=[5, 5])])
    with pytest.raises(GzError) as error:
        edit(record, placed.version, [operation | dict(module_ids=[placed.modules[0].id])])
    assert error.value.error_code == 'MANUAL_MODULE_NO_CHANGE'
    assert storage.next_version(record.id) == 3


def test_old_oblique_grid_preserves_catalogue_geometry_with_millimetre_spacing_tolerance(factory):
    from guangzhu.manual_modules import apply
    record, initial = factory()
    generated = layout.generate_layout(record, dict(tilt_deg=15, azimuth_deg=197))
    record.roof.outline = [(-1, -1), (41, -1), (41, 25), (-1, 25)]
    moved, _ = apply(record, generated, dict(op='move_modules', module_ids=[m.id for m in generated.modules], dx_m=.1, dy_m=.1))
    assert len(moved.modules) == len(generated.modules)
    assert moved.statistics['manual_legacy_geometry_ids']
    for module in moved.modules:
        geometry(module, record, moved)


def test_preview_apply_api_commits_exact_candidate_and_marks_analysis_incomplete(factory):
    from fastapi.testclient import TestClient
    from guangzhu import api
    from guangzhu.config import API_ORIGIN
    record, initial = factory()
    client = TestClient(api.app, base_url=API_ORIGIN, headers={'origin': API_ORIGIN})
    body = dict(version=1, ops=[dict(op='add_modules', placements=[dict(center=[5, 5])])], reason='真实接口补放')
    preview = client.post(f'/api/projects/{record.id}/design-edits/preview', json=body)
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert storage.next_version(record.id) == 2
    committed = client.post(f'/api/projects/{record.id}/design-edits/apply', json=body | dict(fingerprint=data['fingerprint']))
    assert committed.status_code == 200, committed.text
    assert committed.json()['analysis_complete'] is False
    saved = storage.load_design(record.id, 2)
    assert [m.model_dump(mode='json') for m in saved.modules] == data['design']['modules']
    stale = client.post(f'/api/projects/{record.id}/design-edits/apply', json=body | dict(fingerprint=data['fingerprint']))
    assert stale.status_code == 409
