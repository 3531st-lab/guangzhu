"""Independent geometry, persistence and ray checks for multi-height building volumes."""
import copy
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, box

from guangzhu import api, layout, myroofs, roofplane
from guangzhu.config import ROOT
from guangzhu.models import Design, GzError, LayoutParams, Project, Roof
from guangzhu.shading_geometry import build_scene, ray_candidates, ray_hits


def outline(x0, y0, x1, y1):
    return list(box(x0, y0, x1, y1).exterior.coords)[:-1]


def parts():
    return [dict(id='main', label='双坡主楼', outline=outline(0, 0, 20, 10), kind='gable',
                 eave_height_m=9, slope_deg=10, material='metal'),
            dict(id='annex', label='平顶附楼', outline=outline(20, 0, 30, 10), kind='flat',
                 eave_height_m=5, material='concrete')]


def roof(**changes):
    return Roof.model_validate(dict(type='pitched', parts=parts(), parapet_height_m=0,
                                    load_capacity_kn_m2=1) | changes)


def project(value=None):
    record = Project.model_validate_json((ROOT / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    record.roof = value or roof()
    record.equipment.racking = 'plane_flush'
    return Project.model_validate(record.model_dump())


def test_flat_annex_and_gable_have_independent_absolute_elevations_and_materials():
    value = roof()
    assert Polygon(value.outline).area == pytest.approx(300)
    assert value.height_m == 5
    assert len(value.planes) == 3
    annex = next(p for p in value.planes if p.part_id == 'annex')
    assert annex.slope_deg == 0 and annex.material == 'concrete'
    assert roofplane.elevation(value, (25, 5), annex.id) == 0
    assert value.height_m + roofplane.elevation(value, (10, 0)) == pytest.approx(9)
    assert value.height_m + roofplane.elevation(value, (10, 5)) == pytest.approx(9 + 5 * math.tan(math.radians(10)))
    geometry = roofplane.scene_geometry(value)
    assert len(geometry['step_walls']) == 2
    assert all(w in geometry['walls'] for w in geometry['step_walls'])
    assert sum(abs(w[1][1] - w[0][1]) for w in geometry['step_walls']) == pytest.approx(10)


def test_only_explicit_parts_allow_height_steps_and_unowned_zero_pitch_is_invalid():
    value = roof()
    legacy = value.model_dump()
    legacy.pop('parts')
    for plane in legacy['planes']:
        plane.pop('part_id')
        plane['slope_deg'] = max(1, plane['slope_deg'])
    with pytest.raises(GzError, match='高度差'):
        Roof.model_validate(legacy)
    spoofed = copy.deepcopy(legacy)
    spoofed['planes'][0]['part_id'] = 'unregistered'
    with pytest.raises(GzError, match='不存在'):
        Roof.model_validate(spoofed)


@pytest.mark.parametrize('change', ['overlap', 'gap', 'duplicate'])
def test_invalid_part_topologies_are_rejected(change):
    values = parts()
    if change == 'overlap':
        values[1]['outline'] = outline(19, 0, 30, 10)
    elif change == 'gap':
        values[1]['outline'] = outline(20.001, 0, 30, 10)
    else:
        values[1]['id'] = 'main'
    with pytest.raises(GzError) as error:
        roofplane.generate_parts(values)
    assert error.value.error_code == 'ROOF_PARTS_INVALID'


def test_hole_and_corner_only_contact_are_not_silently_filled():
    surrounding = [outline(0, 0, 10, 2), outline(0, 2, 2, 8), outline(8, 2, 10, 8), outline(0, 8, 10, 10)]
    values = [dict(id=f'p{i}', label='外圈', outline=shape, eave_height_m=5) for i, shape in enumerate(surrounding)]
    with pytest.raises(GzError, match='内孔'):
        roofplane.generate_parts(values)
    values = parts()
    values[1]['outline'] = outline(20, 10, 30, 20)
    with pytest.raises(GzError, match='公共边'):
        roofplane.generate_parts(values)


def test_plane_identities_survive_part_reordering_and_insertion():
    record = roof().model_dump()
    before = {part['id']: part['plane_ids'] for part in record['parts']}
    record['parts'].reverse()
    record['parts'].insert(0, dict(id='new', label='新附楼', outline=outline(-10, 0, 0, 10), eave_height_m=7))
    after = Roof.model_validate(record)
    assert {p.id: p.plane_ids for p in after.parts if p.id != 'new'} == before
    assert set(after.parts[0].plane_ids).isdisjoint(n for identifiers in before.values() for n in identifiers)
    assert Roof.model_validate_json(after.model_dump_json()).model_dump() == after.model_dump()


def test_parts_are_authoritative_and_stale_compiled_geometry_is_rebuilt():
    record = roof().model_dump()
    record['parts'][1]['eave_height_m'] = 6
    record['height_m'] = 99
    record['planes'][0]['offset_m'] = 999
    value = Roof.model_validate(record)
    assert value.height_m == 6
    assert max(p.offset_m for p in value.planes) == pytest.approx(3)


def test_step_wall_blocks_low_annex_ray_and_all_faces_remain_finite():
    record = project(roof(parapet_height_m=.5))
    scene = build_scene(record, Design(params=LayoutParams()))
    point = np.array([[21, 5, .2]])
    vector = np.array([-1, 0, .1])
    candidates = ray_candidates(scene, point, vector, [-1])
    assert candidates[0].size
    assert scene.identifiers[candidates[1][0]].startswith('roof-step-')
    assert ray_hits(scene, point, vector, [-1]).tolist() == ['roof']
    assert ray_hits(scene, point, [1, 0, 1], [-1]).tolist() == ['']
    assert np.isfinite(scene.normals).all()


def test_crossing_heights_create_finite_triangles_with_exact_wall_area():
    values = parts()
    values[1]['eave_height_m'] = 9.4
    value = roof(parts=values)
    walls = roofplane.step_walls(value)
    assert len(walls) == 4 and all(len(wall) == 3 for wall in walls)
    pitch = math.tan(math.radians(10))
    crossing = .4 / pitch
    expected = crossing * .4 + (5 - crossing) * (5 * pitch - .4)
    area = sum(np.linalg.norm(np.cross(np.asarray(w)[1] - w[0], np.asarray(w)[2] - w[0])) / 2 for w in walls)
    assert area == pytest.approx(expected)
    scene = build_scene(project(value), Design(params=LayoutParams()))
    assert np.isfinite(scene.normals).all()
    assert sum(identity.startswith('roof-step-') for identity in scene.identifiers) == 4


def test_equipment_is_bound_to_surface_and_follows_part_height():
    obstacle = dict(id='hvac', label='附楼设备', kind='prism', footprint=outline(22, 2, 24, 4), height_m=1)
    value = roof(obstacles=[obstacle])
    equipment = value.obstacles[0]
    annex = next(p for p in value.planes if p.part_id == 'annex')
    assert equipment.plane_id == annex.id and equipment.part_id == 'annex'
    assert roofplane.scene_geometry(value)['obstacle_bases']['hvac'] == 0
    payload = value.model_dump()
    payload['parts'][1]['eave_height_m'] = 11
    moved = Roof.model_validate(payload)
    assert moved.obstacles[0].plane_id == annex.id
    assert roofplane.scene_geometry(moved)['obstacle_bases']['hvac'] == 2
    scene = build_scene(project(moved), Design(params=LayoutParams()))
    top = next(face for face, identity in zip(scene.faces, scene.identifiers) if identity == 'hvac')
    assert np.allclose(top[:, 2], 3)


def test_cross_step_equipment_and_silent_rebinding_are_rejected():
    obstacle = dict(id='hvac', label='设备', kind='prism', footprint=outline(19, 2, 21, 4), height_m=1)
    with pytest.raises(GzError, match='跨越'):
        roof(obstacles=[obstacle])
    obstacle['footprint'] = outline(22, 2, 24, 4)
    obstacle['part_id'] = 'main'
    with pytest.raises(GzError, match='已改变'):
        roof(obstacles=[obstacle])


def test_compound_api_preview_and_layout_use_the_same_planes():
    client = TestClient(api.app, base_url='http://127.0.0.1:8765', headers={'origin': 'http://127.0.0.1:8765'})
    response = client.post('/api/roof-planes', json={'parts': parts(), 'parapet_height_m': .5,
                           'obstacles': [dict(id='hvac', label='附楼设备', kind='prism',
                                              footprint=outline(22, 2, 24, 4), height_m=1)]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result['planes']) == 3 and len(result['geometry']['step_walls']) == 2
    assert result['height_m'] == 5
    assert result['roof']['parapet_height_m'] == .5
    assert result['roof']['obstacles'][0]['part_id'] == 'annex'
    assert result['geometry']['obstacle_bases']['hvac'] == 0
    record = project()
    design = layout.generate_layout(record, {})
    assert design.modules
    annex = next(p for p in record.roof.planes if p.part_id == 'annex')
    members = [m for m in design.modules if m.id.startswith(f'P{annex.id}-')]
    assert members and all(m.tilt == 0 for m in members)
    assert all(Polygon(annex.outline).covers(Polygon([p[:2] for p in m.corners])) for m in members)
    assert client.post('/api/roof-planes', json={'parts': []}).status_code == 422


def test_editor_save_persists_compound_geometry(tmp_path):
    from shutil import copytree
    copytree(ROOT / 'data/demo/projects/changzhou-demo', tmp_path / 'data/demo/projects/changzhou-demo')
    value = project()
    payload = dict(name='组合厂房', site=value.site.model_dump(), roof=value.roof.model_dump())
    identifier = myroofs.save(payload, tmp_path)
    saved = Project.model_validate_json((tmp_path / 'data/my-roofs' / identifier / 'project.json').read_text(encoding='utf-8'))
    assert len(saved.roof.parts) == 2 and len(saved.roof.planes) == 3
    assert saved.equipment.racking == 'plane_flush'
