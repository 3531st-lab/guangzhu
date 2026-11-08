"""Facade presentation settings persist without changing photovoltaic design or locks."""
import json
from shutil import copytree

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from guangzhu import api, layout, myroofs, project as storage
from guangzhu.config import ROOT
from guangzhu.design_locks import geometry_signature, verify_geometry
from guangzhu.models import FacadeSettings, GzError, Project, Roof
from guangzhu.shading_geometry import build_scene


OUTLINE = [[0, 0], [24, 0], [24, 16], [0, 16]]


def project():
    source = json.loads((ROOT / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    source.update(id='facade-case', designs=[], requirements={})
    source['roof'].update(outline=OUTLINE, obstacles=[], keepouts=[], surroundings=[])
    return Project.model_validate(source)


def test_absent_facade_keeps_legacy_roof_serialization_exact():
    value = Roof(outline=OUTLINE, height_m=9, parapet_height_m=0, load_capacity_kn_m2=.5)
    expected = ('{"type":"flat","outline":[[0.0,0.0],[24.0,0.0],[24.0,16.0],[0.0,16.0]],'
                '"height_m":9.0,"parapet_height_m":0.0,"load_capacity_kn_m2":0.5,'
                '"obstacles":[],"keepouts":[],"underlay":null}')
    assert value.facade is None
    assert value.model_dump_json() == expected
    assert Roof.model_validate_json(expected).model_dump_json() == expected


def test_facade_settings_save_and_reopen_through_roof_editor(tmp_path):
    copytree(ROOT / 'data/demo/projects/changzhou-demo', tmp_path / 'data/demo/projects/changzhou-demo')
    record = project()
    record.roof.facade = FacadeSettings(wall_material='brick', wall_color='#B28A6F', front_edge=1,
                                        window_rows=2, doors=3, loading_docks=2, canopy_depth_m=2)
    payload = dict(name='厂房立面示意', site=record.site.model_dump(), roof=record.roof.model_dump())
    identifier = myroofs.save(payload, tmp_path)
    saved = Project.model_validate_json((tmp_path / 'data/my-roofs' / identifier / 'project.json').read_text(encoding='utf-8'))
    assert saved.roof.facade == record.roof.facade
    assert saved.roof.facade.door_color == '#3c5969'
    assert saved.roof.facade.personnel_door is True


@pytest.mark.parametrize('field,value', [
    ('wall_color', '#fff'), ('trim_color', '49606c'), ('base_color', '#12345g'),
    ('door_color', '#12345678'), ('wall_color', '#123456\n'), ('wall_material', 'timber'),
    ('bay_width_m', 1.9), ('base_height_m', -1), ('window_rows', 1.5), ('window_rows', True),
    ('window_width_m', float('nan')), ('window_height_m', float('inf')), ('window_sill_m', 12.1),
    ('front_edge', -1), ('front_edge', True), ('doors', 7), ('door_width_m', 9), ('door_height_m', 1.9),
    ('canopy_depth_m', 4.1), ('loading_docks', 5), ('dock_height_m', .2),
])
def test_invalid_facade_colors_dimensions_and_counts_are_rejected(field, value):
    with pytest.raises(ValidationError):
        FacadeSettings.model_validate({field: value})


def test_front_edge_is_checked_against_final_roof_outline():
    record = project().model_dump()
    record['roof']['facade'] = {'front_edge': len(OUTLINE)}
    with pytest.raises(GzError) as caught:
        Project.model_validate(record)
    assert caught.value.error_code == 'FACADE_FRONT_EDGE_INVALID'
    record['roof']['facade']['front_edge'] = None
    assert Project.model_validate(record).roof.facade.front_edge is None


@pytest.mark.parametrize('compound', [False, True])
def test_roof_preview_preserves_and_validates_facade(compound):
    client = TestClient(api.app, base_url='http://127.0.0.1:8765', headers={'origin': 'http://127.0.0.1:8765'})
    payload = dict(parts=[dict(id='main', label='厂房', kind='gable', eave_height_m=9, outline=OUTLINE)]) if compound else dict(
        outline=OUTLINE, settings=dict(kind='gable', slope_deg=8))
    payload['facade'] = dict(wall_color='#AABBCC', front_edge=1, doors=1, canopy_depth_m=0)
    response = client.post('/api/roof-planes', json=payload)
    assert response.status_code == 200, response.text
    facade = response.json()['roof']['facade']
    assert facade['wall_color'] == '#AABBCC' and facade['front_edge'] == 1
    assert facade['canopy_depth_m'] == 0 and facade['window_height_m'] == 1.2
    payload['facade']['front_edge'] = 100
    assert client.post('/api/roof-planes', json=payload).status_code == 422
    payload['facade'] = {'wall_color': 'red'}
    assert client.post('/api/roof-planes', json=payload).status_code == 422


def test_facade_changes_do_not_change_locked_geometry_layout_or_shadow_scene(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    record = storage.save(project())
    initial = storage.save_design(record.id, layout.generate_layout(record, dict(tilt_deg=10)), offline=True)
    result = storage.edit_design(record.id, initial.version,
                                 [dict(op='lock_modules', module_ids=[initial.modules[0].id])],
                                 '锁定已确定位置', 'user', offline=True)
    locked = storage.load_design(record.id, result['version'])
    design_bytes = storage._path(record.id, f'designs/v{locked.version}.json').read_bytes()
    before_signature = geometry_signature(record)
    before_scene = build_scene(record, initial)

    changed = storage.load(record.id)
    changed.roof.facade = FacadeSettings(wall_material='concrete', wall_color='#eeeeee', front_edge=2,
                                        window_rows=2, doors=4, loading_docks=3, canopy_depth_m=4)
    changed = storage.save(changed)
    assert geometry_signature(changed) == before_signature
    verify_geometry(changed, locked)
    assert storage._path(record.id, f'designs/v{locked.version}.json').read_bytes() == design_bytes
    regenerated = layout.generate_layout(changed, initial.params)
    assert regenerated.modules == initial.modules
    assert regenerated.statistics == initial.statistics
    after_scene = build_scene(changed, initial)
    assert before_scene.identifiers == after_scene.identifiers
    assert all(np.array_equal(left, right) for left, right in zip(before_scene.faces, after_scene.faces, strict=True))
