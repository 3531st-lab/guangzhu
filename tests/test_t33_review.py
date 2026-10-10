"""Review regressions use persisted designs, actual comparison and the parking API."""
import pytest
import requests
from fastapi.testclient import TestClient
from shapely.geometry import Point, Polygon

from guangzhu import api, installation, mcp_actions, project as storage
from guangzhu.config import API_ORIGIN, API_PORT, ROOT
from guangzhu.models import GzError, Roof
from test_t33_installation import project


@pytest.fixture
def stored(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    monkeypatch.setattr(requests.Session, 'request', lambda *a, **k: pytest.fail('review flow must remain offline'))
    def create(kind='carport', height=None):
        identifier = 'review-' + kind
        storage.init(ROOT / 'data/demo/projects/changzhou-demo', identifier)
        record = project(kind, direction_deg=0) if kind == 'carport' else project(kind)
        record.id = identifier
        record.equipment.inverter_id = None
        record.requirements.structured.max_height_m = height
        if kind == 'carport':
            record.roof.planes[1].slope_deg = 7
            record.roof.planes[1].offset_m = 3
        storage.save(record)
        mcp_actions._generate_layout(identifier, {}, offline=True)
        return identifier
    return create


@pytest.mark.parametrize('names', [('tilt_deg', 'clear_height_m'), ('clear_height_m', 'tilt_deg'),
                                 ('clear_height_m', 'edge_setback_m')])
def test_batch_parameters_accumulate_and_preserve_other_canopies(stored, names):
    identifier = stored()
    values = dict(tilt_deg=10, clear_height_m=3, edge_setback_m=.6)
    result = storage.edit_design(identifier, 1, [dict(op='set_param', name=n, value=values[n]) for n in names],
                                 '累计车棚参数', 'user', offline=True)
    design = storage.load_design(identifier, result['version'])
    faces = installation.effective(storage.load(identifier), design).roof.planes
    assert [p.slope_deg for p in faces] == ([10, 10] if 'tilt_deg' in names else [5, 7])
    assert [p.offset_m for p in faces] == pytest.approx([3.3, 3.3])


def test_unmodified_individual_clearance_survives_other_parameter(stored):
    identifier = stored()
    result = storage.edit_design(identifier, 1, [dict(op='set_param', name='edge_setback_m', value=.6)],
                                 '只改边距', 'user', offline=True)
    faces = storage.load_design(identifier, result['version']).installation_roof.planes
    assert [p.slope_deg for p in faces] == [5, 7]
    assert [p.offset_m for p in faces] == pytest.approx([2.8, 3])


def test_carport_real_comparison_with_feasible_height_limit(stored):
    identifier = stored(height=4)
    mcp_actions._analyze(identifier, 1, offline=True)
    result = mcp_actions._compare_options(identifier, 1, offline=True)
    assert result['options']
    assert storage.load(identifier).requirements.structured.max_height_m == 4
    for row in result['options']:
        design = storage.load_design(identifier, row['version'])
        assert design.params.layout == 'rows'
        rules = mcp_actions._read(identifier, f"analysis/v{row['version']}/rules.json")
        height = next(item for item in rules['items'] if item['id'] == 'G07')
        assert height['status'] == ('fail' if max(p[2] for m in design.modules for p in m.corners) > 4 + 1e-6 else 'pass')


@pytest.mark.parametrize('kind', ['ground', 'carport'])
def test_added_keepout_owned_once_through_repack_reopen_analysis_and_candidates(stored, kind):
    identifier = stored(kind)
    polygon = [[8, 8], [12, 8], [12, 12], [8, 12]]
    added = storage.edit_design(identifier, 1, [dict(op='add_keepout', label='检修实体', polygon=polygon)],
                                '保留检修区', 'user', offline=True)['version']
    repacked = storage.edit_design(identifier, added, [dict(op='set_param', name='edge_setback_m', value=.6)],
                                   '修改边距', 'user', offline=True)['version']
    def check(version):
        design = storage.load_design(identifier, version)
        view = installation.effective(storage.load(identifier), design)
        zones = [*view.roof.keepouts, *design.added_keepouts]
        assert len(zones) == 1 and zones[0].polygon == [tuple(p) for p in polygon]
        assert all(not Polygon(polygon).intersects(Polygon([p[:2] for p in m.corners])) for m in design.modules)
    mcp_actions._analyze(identifier, repacked, offline=True)
    check(repacked)
    edited = storage.edit_design(identifier, repacked, [dict(op='set_param', name='edge_setback_m', value=.7)],
                                 '继续调整', 'user', offline=True)['version']
    check(edited)
    mcp_actions._analyze(identifier, edited, offline=True)
    compared = mcp_actions._compare_options(identifier, edited, offline=True)
    for row in compared['options']:
        check(row['version'])


def test_parking_rebuild_ignores_old_derived_geometry_but_normal_save_rejects_it():
    record = project('carport', direction_deg=0)
    outline = [[0, 0], [20, 0], [20, 40], [0, 40]]
    with pytest.raises((GzError, ValueError)):
        Roof.model_validate(record.roof.model_dump() | dict(outline=outline))
    client = TestClient(api.app, base_url=f'http://127.0.0.1:{API_PORT}', headers={'origin': API_ORIGIN})
    response = client.post('/api/parking', json=dict(outline=outline, settings=record.roof.carport.model_dump()))
    assert response.status_code == 200, response.text
    value = response.json()
    roof = Roof.model_validate(record.roof.model_dump() | dict(outline=outline) | value)
    assert len(roof.carport.bays) == 32
    assert all(Polygon(outline).covers(Polygon(p.polygon)) for p in [*roof.carport.bays, *roof.carport.aisles])
    assert all(Polygon(outline).covers(Point(p)) for points in roof.carport.columns.values() for p in points)
