"""Measured perimeter walls share exact geometry between preview, rays and locks."""
import hashlib
import json
import math
from pathlib import Path
from shutil import copytree

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from guangzhu import api, myroofs, park_store, shading_geometry
from guangzhu.config import ROOT
from guangzhu.design_locks import geometry_signature, verify_geometry
from guangzhu.models import Design, GzError, LayoutParams, ParapetSegment, Project, Roof
from guangzhu.roofplane import generate, generate_parts, parapet_faces, path3d, scene_geometry
from guangzhu.shading_geometry import build_scene, ray_hits, shadow_polygons, sun_vector


OUTLINE = [[0, 0], [20, 0], [20, 10], [0, 10]]


def roof(**changes):
    return Roof.model_validate(dict(type='flat', outline=OUTLINE, height_m=9,
                                    parapet_height_m=1, load_capacity_kn_m2=.5) | changes)


def project(value=None):
    record = Project.model_validate_json((Path(__file__).parent / 'fixtures/roofs/symmetric.json').read_text(encoding='utf-8'))
    record.roof = value or roof()
    record.equipment.racking = {'metal': 'clamp_flush', 'pitched': 'plane_flush'}.get(record.roof.type, 'ballast_tilt')
    return record


def client():
    return TestClient(api.app, base_url='http://127.0.0.1:8765', headers={'origin': 'http://127.0.0.1:8765'})


def test_legacy_serialization_and_three_distinct_modes():
    legacy = roof()
    assert legacy.model_dump_json() == ('{"type":"flat","outline":[[0.0,0.0],[20.0,0.0],[20.0,10.0],[0.0,10.0]],'
        '"height_m":9.0,"parapet_height_m":1.0,"load_capacity_kn_m2":0.5,"obstacles":[],"keepouts":[],"underlay":null}')
    assert roof(parapet_segments=None).model_dump_json() == legacy.model_dump_json()
    assert len(parapet_faces(legacy)) == 4
    empty = roof(parapet_segments=[])
    assert empty.model_dump()['parapet_segments'] == []
    assert scene_geometry(empty)['parapets'] == []
    assert not build_scene(project(empty), Design(params=LayoutParams())).faces
    zero = roof(parapet_segments=[dict(edge_index=0, height_m=0)])
    assert parapet_faces(zero) == []
    assert zero.model_dump()['parapet_segments'][0]['height_m'] == 0


@pytest.mark.parametrize('change', [
    dict(edge_index=-1), dict(edge_index=True), dict(edge_index=1.0), dict(edge_index='1'),
    dict(start_ratio=-.01), dict(start_ratio=1), dict(start_ratio=True), dict(start_ratio='0'),
    dict(end_ratio=0), dict(end_ratio=1.01), dict(end_ratio=False), dict(end_ratio=float('nan')),
    dict(start_ratio=.7, end_ratio=.3), dict(height_m=-.1), dict(height_m=3.01),
    dict(height_m=True), dict(height_m='1'), dict(height_m=float('inf')),
])
def test_segment_rejects_invalid_types_nonfinite_values_and_intervals(change):
    with pytest.raises((ValidationError, GzError)):
        ParapetSegment.model_validate(dict(edge_index=0, height_m=1) | change)


def test_edge_bounds_overlap_and_segment_limit_are_checked():
    with pytest.raises(GzError, match='不存在'):
        roof(parapet_segments=[dict(edge_index=4, height_m=1)])
    with pytest.raises(GzError, match='重叠'):
        roof(parapet_segments=[dict(edge_index=0, start_ratio=.4, end_ratio=.8, height_m=1),
                              dict(edge_index=0, start_ratio=.1, end_ratio=.5, height_m=2)])
    adjacent = roof(parapet_segments=[dict(edge_index=0, start_ratio=.5, height_m=1),
                                     dict(edge_index=0, end_ratio=.5, height_m=2)])
    assert len(parapet_faces(adjacent)) == 2
    with pytest.raises(ValidationError):
        roof(parapet_segments=[dict(edge_index=0, height_m=1)] * 257)
    with pytest.raises(GzError):
        roof(type='ground', height_m=0, parapet_height_m=0,
             parapet_segments=[dict(edge_index=0, height_m=1)])


def test_partial_wall_gap_and_height_have_analytic_shadow_and_ray_hits(monkeypatch):
    value = roof(parapet_segments=[dict(edge_index=0, start_ratio=.25, end_ratio=.75, height_m=2)])
    expected = [[[5, 0, 0], [15, 0, 0], [15, 0, 2], [5, 0, 2]]]
    np.testing.assert_allclose(scene_geometry(value)['parapets'], expected)
    scene = build_scene(project(value), Design(params=LayoutParams()))
    np.testing.assert_allclose(scene.faces, expected)
    points = [[10, 1, .1], [2, 1, .1], [10, 2.1, .1], [14.9, 1.8, .1]]
    assert ray_hits(scene, points, sun_vector(45, 180), -2).tolist() == ['parapet', '', '', 'parapet']
    monkeypatch.setattr(shading_geometry, '_sun_at', lambda *args: (45, 180))
    shadow = shadow_polygons(scene, '2026-12-21T12:00+08:00')['parapet']
    assert shadow.area == pytest.approx(10 * 2)
    assert shadow.bounds == pytest.approx((5, 0, 15, 2))


def test_rotated_translated_wall_exact_vertices_and_clockwise_input_is_explicitly_rejected():
    angle = math.radians(37)
    def transform(p):
        return [p[0] * math.cos(angle) - p[1] * math.sin(angle) + 83,
                p[0] * math.sin(angle) + p[1] * math.cos(angle) - 27]
    outline = list(map(transform, OUTLINE))
    segments = [dict(edge_index=1, start_ratio=.2, end_ratio=.8, height_m=1.7)]
    actual = parapet_faces(roof(outline=outline, parapet_segments=segments))
    expected = [[[ *transform([20, 2]), 0], [*transform([20, 8]), 0],
                 [*transform([20, 8]), 1.7], [*transform([20, 2]), 1.7]]]
    np.testing.assert_allclose(actual, expected, atol=1e-12)
    with pytest.raises(GzError) as caught:
        roof(outline=[outline[0], *reversed(outline[1:])], parapet_segments=segments)
    assert caught.value.error_code == 'PARAPET_EDGE_DIRECTION_INVALID'


def test_metal_wall_follows_actual_inclined_deck():
    value = roof(type='metal', slope_deg=math.degrees(math.atan(.5)), slope_azimuth_deg=270,
                 parapet_segments=[dict(edge_index=0, start_ratio=.25, end_ratio=.75, height_m=2)])
    expected = [[[5, 0, 2.5], [15, 0, 7.5], [15, 0, 9.5], [5, 0, 4.5]]]
    np.testing.assert_allclose(scene_geometry(value)['parapets'], expected, atol=1e-12)
    np.testing.assert_allclose(build_scene(project(value), Design(params=LayoutParams())).faces, expected, atol=1e-12)


def test_gable_wall_splits_at_ridge_without_vertical_shortcut():
    generated = generate(OUTLINE, dict(kind='gable', slope_deg=math.degrees(math.atan(.2)),
                                       ridge=[[10, -10], [10, 20]]))
    value = roof(type='pitched', planes=generated['planes'], parapet_segments=[dict(edge_index=0, height_m=1)])
    faces = parapet_faces(value)
    np.testing.assert_allclose(faces, [
        [[0, 0, 0], [10, 0, 2], [10, 0, 3], [0, 0, 1]],
        [[10, 0, 2], [20, 0, 0], [20, 0, 1], [10, 0, 3]],
    ], atol=1e-12)
    scene = build_scene(project(value), Design(params=LayoutParams()))
    actual = [face for cause, face in zip(scene.causes, scene.faces) if cause == 'parapet']
    np.testing.assert_allclose(actual, faces)


@pytest.mark.parametrize('degrees', [0, 37, 179, 271])
def test_translated_rotated_ridge_and_partial_wall_keep_analytic_peak(degrees):
    angle = math.radians(degrees)
    def point(x, y, z=None):
        xy = [83 + x * math.cos(angle) - y * math.sin(angle),
              -27 + x * math.sin(angle) + y * math.cos(angle)]
        return xy if z is None else [*xy, z]
    outline = [point(x, y) for x, y in OUTLINE]
    generated = generate(outline, dict(kind='gable', slope_deg=math.degrees(math.atan(.2)),
                                       ridge=[point(10, -10), point(10, 20)]))
    value = roof(type='pitched', outline=outline, planes=generated['planes'],
                 parapet_segments=[dict(edge_index=0, start_ratio=.1, end_ratio=.9, height_m=1.7)])
    np.testing.assert_allclose(path3d(value, [point(0, 0), point(20, 0)]),
                               [point(0, 0, 0), point(10, 0, 2), point(20, 0, 0)], atol=1e-10)
    expected = [[point(2, 0, .4), point(10, 0, 2), point(10, 0, 3.7), point(2, 0, 2.1)],
                [point(10, 0, 2), point(18, 0, .4), point(18, 0, 2.1), point(10, 0, 3.7)]]
    np.testing.assert_allclose(parapet_faces(value), expected, atol=1e-10)
    rendering = scene_geometry(value)
    np.testing.assert_allclose(rendering['parapets'], expected, atol=1e-10)
    assert max(p[2] for p in rendering['boundary']) == pytest.approx(2)
    restored = Roof.model_validate_json(value.model_dump_json())
    np.testing.assert_allclose(parapet_faces(restored), expected, atol=1e-10)


def test_compound_wall_uses_final_boundary_and_does_not_bridge_height_jump():
    parts = [dict(id='low', label='低跨', kind='flat', eave_height_m=6,
                  outline=[[0, 0], [10, 0], [10, 10], [0, 10]]),
             dict(id='high', label='高跨', kind='flat', eave_height_m=12,
                  outline=[[10, 0], [20, 0], [20, 10], [10, 10]])]
    compiled = generate_parts(parts)
    outline = compiled['outline']
    front_edges = [i for i, p in enumerate(outline) if p[1] == 0 and outline[(i + 1) % len(outline)][1] == 0]
    segments = [dict(edge_index=i, height_m=1.5) for i in front_edges]
    value = roof(type='pitched', **compiled, parapet_segments=segments)
    faces = parapet_faces(value)
    assert sum(math.dist(face[0][:2], face[1][:2]) for face in faces) == pytest.approx(20)
    assert sorted({round(face[0][2], 8) for face in faces}) == [0, 6]
    for face in faces:
        assert face[0][2] == pytest.approx(face[1][2])
        assert face[2][2] - face[1][2] == pytest.approx(1.5)
    changed = value.model_dump(mode='json')
    changed['parts'][1]['outline'][1][0] = 21
    changed['parts'][1]['outline'][2][0] = 21
    with pytest.raises(GzError) as caught:
        Roof.model_validate(changed)
    assert caught.value.error_code == 'PARAPET_EDGE_CHANGED'


@pytest.mark.parametrize('kind', ['flat', 'metal', 'gable', 'parts'])
def test_preview_api_preserves_segments_and_rejects_invalid_complete_input(kind):
    segment = dict(edge_index=0, start_ratio=.2, end_ratio=.7, height_m=1.8)
    if kind in ('flat', 'metal'):
        values = dict(type=kind, parapet_segments=[segment])
        if kind == 'metal':
            values.update(slope_deg=5, slope_azimuth_deg=180)
        payload = dict(roof=roof(**values).model_dump())
    elif kind == 'gable':
        payload = dict(outline=OUTLINE, settings=dict(kind='gable', slope_deg=5), parapet_segments=[segment])
    else:
        payload = dict(parts=[dict(id='main', label='厂房', kind='flat', eave_height_m=9, outline=OUTLINE)],
                       parapet_segments=[segment])
    response = client().post('/api/roof-planes', json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['roof']['parapet_segments'] == [segment]
    assert body['geometry']['parapets']
    target = payload.get('roof', payload)
    target['parapet_segments'] = [dict(edge_index=99, height_m=1)]
    assert client().post('/api/roof-planes', json=payload).status_code == 422
    target['parapet_segments'] = []
    empty = client().post('/api/roof-planes', json=payload)
    assert empty.status_code == 200 and empty.json()['geometry']['parapets'] == []


def test_save_reopen_preserves_custom_and_explicit_empty_modes(tmp_path):
    copytree(ROOT / 'data/demo/projects/changzhou-demo', tmp_path / 'data/demo/projects/changzhou-demo')
    for segments in ([dict(edge_index=2, start_ratio=.1, end_ratio=.9, height_m=2)], []):
        record = project(roof(parapet_segments=segments))
        identifier = myroofs.save(dict(name='分段女儿墙', site=record.site.model_dump(), roof=record.roof.model_dump()), tmp_path)
        saved = Project.model_validate_json((tmp_path / 'data/my-roofs' / identifier / 'project.json').read_text(encoding='utf-8'))
        assert saved.roof.parapet_segments == record.roof.parapet_segments


@pytest.mark.parametrize('outline', [5, 'invalid', [[0, 0], [20], [20, 10]], [[0, 0], [20, 0], [20, 10, 0]]])
def test_invalid_raw_outline_with_segments_is_an_api_validation_error(outline):
    payload = roof(parapet_segments=[dict(edge_index=0, height_m=1)]).model_dump(mode='json')
    payload['outline'] = outline
    assert client().post('/api/roof-planes', json=dict(roof=payload)).status_code == 422


def test_explicit_wall_parameters_enter_locks_without_changing_legacy_hash():
    record = project()
    raw = record.roof.model_dump(mode='json')
    old = {key: raw.get(key) for key in ('type', 'outline', 'height_m', 'slope_deg', 'slope_azimuth_deg', 'ground', 'carport')}
    old.update(planes=[], module_id=record.equipment.module_id, racking=record.equipment.racking)
    expected = hashlib.sha256(json.dumps(old, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert geometry_signature(record) == expected
    record.roof = roof(parapet_segments=[dict(edge_index=0, height_m=1), dict(edge_index=1, height_m=2)])
    signature = geometry_signature(record)
    assert signature != expected
    explicit = project(roof(parapet_segments=[dict(edge_index=0, start_ratio=0, end_ratio=1, height_m=1),
                                              dict(edge_index=1, start_ratio=0, end_ratio=1, height_m=2)]))
    assert geometry_signature(explicit) == signature
    locked = Design(params=LayoutParams(), locked_regions=[dict(id='kept', polygon=[[1, 1], [2, 1], [2, 2], [1, 2]])],
                    locked_geometry_sha256=signature)
    verify_geometry(record, locked)
    record.roof.parapet_segments.reverse()
    assert geometry_signature(record) == signature
    record.roof.parapet_segments[0].height_m = 2.5
    with pytest.raises(GzError) as caught:
        verify_geometry(record, locked)
    assert caught.value.error_code == 'DESIGN_LOCK_GEOMETRY_CHANGED'
    record.roof = roof(parapet_segments=[])
    assert geometry_signature(record) not in (expected, signature)


def test_split_keepout_faces_keep_source_identity():
    generated = generate(OUTLINE, dict(kind='gable', slope_deg=5, ridge=[[10, -10], [10, 20]]))
    value = roof(type='pitched', planes=generated['planes'], keepouts=[dict(id='sky-1', label='天窗',
        polygon=[[8, 2], [12, 2], [12, 8], [8, 8]])])
    geometry = scene_geometry(value)
    assert len(geometry['keepout_faces']) == 2
    assert {face['id'] for face in geometry['keepout_faces']} == {'sky-1'}
    assert [face['points'] for face in geometry['keepout_faces']] == geometry['keepouts']


def test_legacy_gable_split_rejects_segment_indices_before_writing(tmp_path):
    record = project(roof(type='metal', slope_deg=5, slope_azimuth_deg=180,
                          parapet_segments=[dict(edge_index=0, height_m=1)]))
    with pytest.raises(GzError) as caught:
        myroofs.save_gable(dict(name='旧式拆分', site=record.site.model_dump(), roof=record.roof.model_dump()), tmp_path)
    assert caught.value.error_code == 'PARAPET_SPLIT_UNSUPPORTED'
    assert not (tmp_path / 'data/my-roofs').exists()


@pytest.mark.parametrize('segments,extra', [(None, 1), ([], 0), ([dict(edge_index=0, height_m=2.8)], 2.8)])
def test_park_neighbour_envelope_uses_effective_wall_height(tmp_path, segments, extra):
    for identifier, height in [('low', 9), ('high', 12)]:
        record = project(roof(height_m=height, parapet_segments=segments if identifier == 'high' else None))
        record.id, record.name = identifier, identifier
        park_store.write(tmp_path / 'data/my-roofs' / identifier / 'project.json', record.model_dump(mode='json'))
    park_store.save(dict(id='factory', name='厂区', buildings=[dict(template='low'), dict(template='high', x_m=30)]), tmp_path)
    generated = Project.model_validate(park_store.read(tmp_path / 'data/parks/factory/roofs/factory--low/project.json'))
    assert generated.roof.surroundings[0].height_m == pytest.approx(3 + extra)


@pytest.mark.parametrize('kind', ['flat', 'metal'])
def test_saved_result_api_returns_authoritative_flat_and_metal_walls(tmp_path, monkeypatch, kind):
    options = dict(type=kind, parapet_segments=[dict(edge_index=0, height_m=1.4)])
    if kind == 'metal':
        options.update(slope_deg=5, slope_azimuth_deg=180)
    record = project(roof(**options))
    base = tmp_path / 'projects' / record.id
    park_store.write(base / 'project.json', record.model_dump(mode='json'))
    park_store.write(base / 'designs/v1.json', Design(params=LayoutParams()).model_dump(mode='json'))
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    result = api.result_data(record.id)
    np.testing.assert_allclose(result['scene']['roof_geometry']['parapets'], parapet_faces(record.roof))
