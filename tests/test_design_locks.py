"""Placement locks survive regeneration, guarded writes and preview/commit round trips."""
import json

import pytest
from shapely.geometry import Polygon

from guangzhu import layout, project as storage
from guangzhu.config import DATA_DIR
from guangzhu.design_locks import locked_ids
from guangzhu.models import Design, GzError


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    source = json.loads((DATA_DIR / 'demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    source.update(id='locks', designs=[])
    source['requirements'] = {}
    source['roof'].update(outline=[[0, 0], [24, 0], [24, 16], [0, 16]], obstacles=[], keepouts=[], surroundings=[])
    project = storage.save(source)
    design = layout.generate_layout(project, dict(tilt_deg=10, edge_setback_m=1))
    storage.save_design(project.id, design, offline=True)
    return project, design


def edit(project, version, ops, author='user', **kwargs):
    return storage.edit_design(project.id, version, ops, '局部修改测试', author, offline=True, **kwargs)


def lock_first(project, design):
    identifier = design.modules[0].id
    result = edit(project, design.version, [dict(op='lock_modules', module_ids=[identifier])])
    return storage.load_design(project.id, result['version']), identifier


def test_preview_has_no_writes_and_commit_requires_same_inputs(case):
    project, design = case
    folder = storage._path(project.id)
    before = {path.relative_to(folder): path.read_bytes() for path in folder.rglob('*') if path.is_file()}
    ops = [dict(op='lock_modules', module_ids=[design.modules[0].id])]
    preview = storage.preview_edit(project.id, 1, ops, '锁定东侧', offline=True)
    assert preview['changes']['locked'] == [design.modules[0].id]
    assert preview['changes']['analysis_status'] == 'not_recomputed'
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob('*') if path.is_file()} == before
    with pytest.raises(GzError) as caught:
        storage.edit_design(project.id, 1, ops, '原因改变', 'user', expected_fingerprint=preview['fingerprint'], offline=True)
    assert caught.value.error_code == 'DESIGN_PREVIEW_STALE'
    saved = storage.edit_design(project.id, 1, ops, '锁定东侧', 'user', expected_fingerprint=preview['fingerprint'], offline=True)
    assert saved['version'] == 2
    with pytest.raises(GzError) as caught:
        storage.edit_design(project.id, 1, ops, '锁定东侧', 'user', expected_fingerprint=preview['fingerprint'], offline=True)
    assert caught.value.error_code == 'DESIGN_PREVIEW_STALE'
    assert storage._path(project.id, 'designs/v1.json').read_bytes() == before[next(key for key in before if str(key).endswith('v1.json'))]


def test_changed_project_invalidates_preview(case):
    project, design = case
    ops = [dict(op='set_string_size', modules_per_string=10)]
    preview = storage.preview_edit(project.id, 1, ops, '测试', offline=True)
    project.name = 'changed'
    storage.save(project)
    with pytest.raises(GzError) as caught:
        storage.edit_design(project.id, 1, ops, '测试', 'user', expected_fingerprint=preview['fingerprint'], offline=True)
    assert caught.value.error_code == 'DESIGN_PREVIEW_STALE'


@pytest.mark.parametrize('change_before_preview', [True, False])
def test_commit_rechecks_fingerprint_around_preview(case, monkeypatch, change_before_preview):
    project, _ = case
    ops = [dict(op='set_string_size', modules_per_string=10)]
    approved = storage.preview_edit(project.id, 1, ops, '确认测试', offline=True)
    original_preview = storage.preview_edit

    def raced_preview(*args, **kwargs):
        if change_before_preview:
            project.name = 'changed before candidate calculation'
            storage.save(project)
        result = original_preview(*args, **kwargs)
        if not change_before_preview:
            project.name = 'changed after candidate calculation'
            storage.save(project)
        return result

    monkeypatch.setattr(storage, 'preview_edit', raced_preview)
    with pytest.raises(GzError) as caught:
        storage.edit_design(project.id, 1, ops, '确认测试', 'user', expected_fingerprint=approved['fingerprint'], offline=True)
    assert caught.value.error_code == 'DESIGN_PREVIEW_STALE'
    assert storage.next_version(project.id) == 2


def test_locked_component_cannot_be_deleted_or_covered_by_new_keepout(case):
    project, design = case
    locked, identifier = lock_first(project, design)
    module = next(module for module in locked.modules if module.id == identifier)
    for ops in ([dict(op='remove_modules', module_ids=[identifier])],
                [dict(op='add_keepout', label='检修区', polygon=[point[:2] for point in module.corners])]):
        with pytest.raises(GzError) as caught:
            edit(project, locked.version, ops)
        assert caught.value.error_code == 'DESIGN_LOCK_CONFLICT'
    assert storage.next_version(project.id) == 3


def test_unlock_is_user_only_and_old_versions_cannot_bypass_new_lock(case):
    project, design = case
    locked, identifier = lock_first(project, design)
    with pytest.raises(GzError) as caught:
        edit(project, locked.version, [dict(op='unlock_modules', module_ids=[identifier])], author='agent')
    assert caught.value.error_code == 'DESIGN_LOCK_USER_REQUIRED'
    with pytest.raises(GzError) as caught:
        edit(project, 1, [dict(op='remove_modules', module_ids=[identifier])])
    assert caught.value.error_code == 'DESIGN_LOCK_STALE'
    result = edit(project, locked.version, [dict(op='unlock_modules', module_ids=[identifier]),
                                            dict(op='remove_modules', module_ids=[identifier])])
    assert identifier not in {module.id for module in storage.load_design(project.id, result['version']).modules}


def test_agent_can_add_locks_without_releasing_user_locks(case):
    project, design = case
    locked, identifier = lock_first(project, design)
    extra = locked.modules[1].id
    result = edit(project, 2, [dict(op='lock_modules', module_ids=[extra])], author='agent')
    assert set(storage.load_design(project.id, result['version']).locked_module_ids) == {identifier, extra}


def test_nonfinite_preview_input_is_a_structured_error(case):
    project, _ = case
    with pytest.raises(GzError) as caught:
        storage.preview_edit(project.id, 1, [dict(op='set_param', name='tilt_deg', value=float('nan'))], 'invalid')
    assert caught.value.error_code == 'DESIGN_EDIT_INVALID'


def test_direct_save_cannot_drop_or_move_locked_components(case):
    project, design = case
    locked, identifier = lock_first(project, design)
    candidate = layout.generate_layout(project, dict(tilt_deg=20))
    candidate.version, candidate.parent_version = 3, 2
    with pytest.raises(GzError) as caught:
        storage.save_design(project.id, candidate, offline=True)
    assert caught.value.error_code == 'DESIGN_LOCK_CONFLICT'
    candidate = locked.model_copy(deep=True, update=dict(version=3, parent_version=2))
    candidate.modules[0].center = (0, 0, 0)
    with pytest.raises(GzError) as caught:
        storage.save_design(project.id, candidate, offline=True)
    assert caught.value.error_code == 'DESIGN_LOCK_CONFLICT'


def test_local_reflow_preserves_locked_geometry_and_has_no_collisions(case):
    project, design = case
    locked, identifier = lock_first(project, design)
    result = edit(project, 2, [dict(op='reflow_unlocked', params=dict(orientation='landscape'))])
    candidate = storage.load_design(project.id, result['version'])
    old = next(module for module in locked.modules if module.id == identifier)
    assert next(module for module in candidate.modules if module.id == identifier) == old
    assert candidate.locked_module_ids == [identifier]
    assert len({module.id for module in candidate.modules}) == len(candidate.modules)
    polygons = [Polygon([point[:2] for point in module.corners]) for module in candidate.modules]
    assert all(first.intersection(second).area < 1e-8 for i, first in enumerate(polygons) for second in polygons[i + 1:])
    assert candidate.statistics['module_count'] == len(candidate.modules)
    assert candidate.statistics['dc_kw'] == pytest.approx(len(candidate.modules) * .550)
    assert any(module.orientation == 'landscape' for module in candidate.modules)


def test_lock_conflicts_with_larger_setback_are_explicit(case):
    project, design = case
    locked, identifier = lock_first(project, design)
    with pytest.raises(GzError) as caught:
        edit(project, 2, [dict(op='set_param', name='edge_setback_m', value=7)])
    assert caught.value.error_code == 'DESIGN_LOCK_CONFLICT'
    assert identifier in locked_ids(storage.load_design(project.id, 2))


def test_locked_project_rejects_absolute_datum_and_hardware_changes_but_allows_load_data(case):
    project, design = case
    lock_first(project, design)
    original = storage._path(project.id, 'project.json').read_bytes()
    raised = storage.load(project.id)
    raised.roof.height_m += 2
    with pytest.raises(GzError) as caught:
        storage.save(raised)
    assert caught.value.error_code == 'DESIGN_LOCK_GEOMETRY_CHANGED'
    replaced = storage.load(project.id)
    replaced.equipment.module_id = 'runergy-hy-wh144p8-550'
    with pytest.raises(GzError) as caught:
        storage.save(replaced)
    assert caught.value.error_code == 'DESIGN_LOCK_GEOMETRY_CHANGED'
    assert storage._path(project.id, 'project.json').read_bytes() == original
    updated = storage.load(project.id)
    updated.roof.load_capacity_kn_m2 = 2
    updated.economics.price_self_cny_kwh = .8
    storage.save(updated)
    assert storage.load(project.id).roof.load_capacity_kn_m2 == 2


@pytest.mark.parametrize('change', ['raise_annex', 'remove_annex'])
def test_compound_locked_face_rejects_changed_or_missing_surface_before_reflow(case, change):
    from guangzhu.models import Project, Roof
    from guangzhu.design_locks import reflow
    project, _ = case
    project.id, project.designs = 'compound-locks', []
    project.roof = Roof(type='pitched', parts=[
        dict(id='main', label='主楼', kind='flat', outline=[[0, 0], [20, 0], [20, 10], [0, 10]], eave_height_m=9),
        dict(id='annex', label='附楼', kind='flat', outline=[[20, 0], [30, 0], [30, 10], [20, 10]], eave_height_m=5),
    ], parapet_height_m=0, load_capacity_kn_m2=1)
    project.equipment.racking = 'plane_flush'
    project = storage.save(project)
    design = layout.generate_layout(project, {})
    storage.save_design(project.id, design, offline=True)
    identifier = next(module.id for module in design.modules if module.id.startswith('P2-'))
    locked = edit(project, 1, [dict(op='lock_modules', module_ids=[identifier])])
    design = storage.load_design(project.id, locked['version'])
    data = project.model_dump()
    if change == 'raise_annex':
        data['roof']['parts'][1]['eave_height_m'] = 11
    else:
        data['roof']['parts'] = data['roof']['parts'][:1]
    changed = Project.model_validate(data)
    with pytest.raises(GzError) as caught:
        storage.save(changed)
    assert caught.value.error_code == 'DESIGN_LOCK_GEOMETRY_CHANGED'
    with pytest.raises(GzError) as caught:
        reflow(changed, design, {})
    assert caught.value.error_code == 'DESIGN_LOCK_GEOMETRY_CHANGED'
    # Even an out-of-band file rewrite cannot make an unchanged XY panel valid at a new elevation.
    storage._path(project.id, 'project.json').write_text(changed.model_dump_json(), encoding='utf-8')
    with pytest.raises(GzError) as caught:
        edit(changed, design.version, [dict(op='reflow_unlocked', params={})])
    assert caught.value.error_code == 'DESIGN_LOCK_GEOMETRY_CHANGED'
    assert storage.next_version(project.id) == 3


def test_empty_region_stays_empty_after_regeneration(case):
    project, design = case
    polygon = [[0, 0], [12, 0], [12, 16], [0, 16]]
    selected = [module.id for module in design.modules if Polygon([point[:2] for point in module.corners]).intersects(Polygon(polygon))]
    removed = edit(project, 1, [dict(op='remove_modules', module_ids=selected)])
    locked = edit(project, removed['version'], [dict(op='lock_region', id='east', polygon=polygon)])
    result = edit(project, locked['version'], [dict(op='reflow_unlocked', params=dict(orientation='landscape'))])
    candidate = storage.load_design(project.id, result['version'])
    assert candidate.locked_regions[0].id == 'east'
    assert candidate.modules
    assert all(Polygon([point[:2] for point in module.corners]).intersection(Polygon(polygon)).area < 1e-8
               for module in candidate.modules)


def test_mcp_regenerate_preserves_locks_and_preview_schema(case):
    from guangzhu import mcp_actions, mcp_server
    project, design = case
    locked, identifier = lock_first(project, design)
    result = mcp_actions._generate_layout(project.id, dict(orientation='landscape'), offline=True)
    candidate = storage.load_design(project.id, result['version'])
    assert candidate.parent_version == 2 and candidate.locked_module_ids == [identifier]
    assert next(module for module in candidate.modules if module.id == identifier) == locked.modules[0]
    arguments = dict(project_id=project.id, version=result['version'], reason='测试', preview=True,
                     ops=[dict(op='reflow_unlocked', params=dict(orientation='portrait'))])
    assert mcp_server.VALIDATORS['gz_edit_design'].is_valid(arguments)
    preview = mcp_actions._edit_design(**arguments, offline=True)
    assert preview['preview'] and len(preview['fingerprint']) == 64
    assert len(json.dumps(preview, ensure_ascii=False).encode('utf-8')) <= 2048


def test_mcp_summary_reports_effective_locks_and_bounds_long_region_lists(case):
    from guangzhu import mcp_actions
    project, design = case
    empty = mcp_actions._project_summary(project.id)
    assert empty['locks']['module_count'] == 0 and not empty['locks']['truncated']
    ops = [dict(op='lock_modules', module_ids=[design.modules[0].id])]
    polygon = [[0, 0], [12, 0], [12, 16], [0, 16]]
    ids = ['锁定区域' * 12 + f'-{index:02}' for index in range(24)]
    ops += [dict(op='lock_region', id=identifier, polygon=polygon) for identifier in ids]
    result = edit(project, 1, ops)
    saved = storage.load_design(project.id, result['version'])
    summary = mcp_actions._project_summary(project.id)
    assert summary['locks']['module_count'] == len(locked_ids(saved))
    assert summary['locks']['region_count'] == 24 and summary['locks']['plane_count'] == 0
    assert summary['locks']['truncated']
    assert set(summary['locks']['region_ids']) <= set(ids)
    assert len(json.dumps(summary, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) <= 1920


def test_pitched_face_lock_freezes_entire_face(case):
    from guangzhu.roofplane import generate
    from guangzhu.models import RoofPlane
    project, _ = case
    project.id, project.designs = 'pitched-locks', []
    project.roof.type = 'pitched'
    project.equipment.racking = 'plane_flush'
    project.roof.planes = [RoofPlane.model_validate(plane) for plane in generate(project.roof.outline, dict(kind='gable', slope_deg=8))['planes']]
    project = storage.save(project)
    design = layout.generate_layout(project, {})
    storage.save_design(project.id, design, offline=True)
    locked = edit(project, 1, [dict(op='lock_plane', plane_id=1)])
    result = edit(project, locked['version'], [dict(op='reflow_unlocked', params=dict(orientation='landscape'))])
    candidate = storage.load_design(project.id, result['version'])
    assert [module for module in candidate.modules if module.id.startswith('P1-')] == [module for module in design.modules if module.id.startswith('P1-')]
    assert any(module.orientation == 'landscape' and module.id.startswith('P2-') for module in candidate.modules)


def test_undo_restores_geometry_and_locks_as_new_versions(case):
    project, design = case
    locked, identifier = lock_first(project, design)
    changed = edit(project, 2, [dict(op='reflow_unlocked', params=dict(orientation='landscape'))])
    candidate = storage.load_design(project.id, changed['version'])
    preview = storage.preview_edit(project.id, 3, [dict(op='undo_last_edit')], '撤销上次修改', offline=True)
    assert storage.next_version(project.id) == 4
    result = storage.edit_design(project.id, 3, [dict(op='undo_last_edit')], '撤销上次修改', 'user',
                                 expected_fingerprint=preview['fingerprint'], offline=True)
    restored = storage.load_design(project.id, result['version'])
    assert restored.modules == locked.modules and restored.locked_module_ids == [identifier]
    assert restored.parent_version == 3 and restored.version == 4
    repeated = edit(project, 4, [dict(op='undo_last_edit')])
    redone = storage.load_design(project.id, repeated['version'])
    assert redone.modules == candidate.modules and redone.parent_version == 4
    assert storage.load_design(project.id, 3) == candidate


def test_undo_is_user_only_latest_and_standalone_and_can_undo_lock(case):
    project, design = case
    locked, identifier = lock_first(project, design)
    for version, ops, author, code in (
        (2, [dict(op='undo_last_edit')], 'agent', 'DESIGN_LOCK_USER_REQUIRED'),
        (1, [dict(op='undo_last_edit')], 'user', 'DESIGN_UNDO_UNAVAILABLE'),
        (2, [dict(op='undo_last_edit'), dict(op='set_string_size', modules_per_string=10)], 'user', 'DESIGN_EDIT_INVALID'),
    ):
        with pytest.raises(GzError) as caught:
            edit(project, version, ops, author)
        assert caught.value.error_code == code
    result = edit(project, 2, [dict(op='undo_last_edit')])
    restored = storage.load_design(project.id, result['version'])
    assert not restored.locked_module_ids and restored.modules == design.modules
    assert storage.load_design(project.id, 2).locked_module_ids == [identifier]
