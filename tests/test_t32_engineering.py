"""Real face identity, quantities and downstream T32 contracts."""
import math

import pytest
from shapely.geometry import Polygon

from guangzhu import layout, roofplane, structure, costs
from guangzhu.models import Project
from guangzhu.config import DATA_DIR


def project(kind='gable', **settings):
    payload = Project.model_validate_json((DATA_DIR / 'demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    values = payload.model_dump()
    outline = [[0, 0], [30, 0], [30, 20], [0, 20]]
    planes = roofplane.generate(outline, dict(kind=kind, **settings))['planes']
    values['roof'].update(type='pitched', outline=outline, planes=planes, obstacles=[], keepouts=[], parapet_height_m=0)
    values['equipment']['racking'] = 'plane_flush'
    return Project.model_validate(values)


def test_all_faces_are_flush_glass_empty_and_actual_planes():
    record = project('sawtooth', teeth=2, slope_deg=10)
    design = layout.generate_layout(record, {})
    assert design.modules and design.statistics['planes']
    for panel in design.modules:
        plane = roofplane.member(record.roof, panel.id)
        assert plane.material == 'metal'
        assert panel.tier == 1 and panel.tilt == plane.slope_deg
        assert Polygon(plane.outline).covers(Polygon([p[:2] for p in panel.corners]))
        for point in panel.corners:
            assert point[2] == pytest.approx(roofplane.plane_elevation(plane, point) + .1, abs=2e-9)
    assert {int(m.id.split('-')[0][1:]) for m in design.modules} == {1, 3}


def test_mixed_material_load_and_cost_use_only_actual_hardware_once():
    record = project()
    record.roof.planes[1].material = 'concrete'
    design = layout.generate_layout(record, {})
    load = structure.calculate(record, design)
    assert load['ballast_mass_kg'] == 0
    metal = sum(m.id.startswith('P1-') for m in design.modules)
    concrete = len(design.modules) - metal
    quote = costs.itemized(record, design.statistics['dc_kw'], design=design, load=load)
    quantities = {r['key']: r['quantity'] for r in quote['items']}
    assert quantities['metal_rail'] == metal
    assert quantities['fixed_flush'] == concrete
    assert quantities['fixed_anchor'] == concrete * 4
    assert quantities['wind_clamp'] == load['wind']['clamp_count']
    assert quantities['design'] == quantities['monitor'] == quantities['grid_lv'] == 1
    assert len(load['planes']) == 2
    assert sum(p['mass_kg'] for p in load['planes']) == pytest.approx(load['mass_kg'])
    assert quote['capex_cny'] == pytest.approx(math.fsum(r['subtotal_cny'] for r in quote['items']))


def test_selected_plane_and_steep_surface_keep_explicit_identity():
    record = project('single', slope_deg=45)
    design = layout.generate_layout(record, dict(plane_ids=[1]))
    assert design.modules and all(p.tilt == 45 for p in design.modules)
    assert design.params.plane_ids == [1]
    from guangzhu import shading
    result = shading.analyze_design(record, design, offline=True)
    assert result['summary']['source_loss_pct']['roof'] == 0


@pytest.mark.parametrize('name', ['changzhou-demo', 'metal-demo-s'])
@pytest.mark.parametrize('params', [dict(surface=True, tilt_deg=80), dict(plane_ids=[1])])
def test_ordinary_roofs_reject_pitched_parameter_override(name, params):
    from guangzhu.models import GzError
    record = Project.model_validate_json((DATA_DIR / f'demo/projects/{name}/project.json').read_text(encoding='utf-8'))
    with pytest.raises(GzError) as caught:
        layout.generate_layout(record, params)
    assert caught.value.error_code == 'LAYOUT_PARAMS_INVALID'


def test_slope_route_uses_piecewise_height_and_shared_ridge():
    from guangzhu import cables
    record = project('gable', slope_deg=30)
    assert hasattr(roofplane, 'path3d')
    path = roofplane.path3d(record.roof, [[15, 0], [15, 20]])
    assert path[1] == pytest.approx([15, 10, 5.773502691896257])
    assert math.fsum(math.dist(a, b) for a, b in zip(path, path[1:])) == pytest.approx(23.09401076758503)
    assert cables.length([[15, 0], [15, 20]]) == 20
    path = roofplane.path3d(record.roof, [[2, 2], [8, 2], [8, 18]])
    assert math.fsum(math.dist(a, b) for a, b in zip(path, path[1:])) == pytest.approx(24.475208614068023)


@pytest.mark.parametrize('facts', [None, dict(roof_type='metal'), dict(roof_type='concrete')])
def test_pitched_site_check_does_not_claim_flat_ballast_or_one_material(facts):
    from guangzhu import sitecheck
    row = sitecheck.rows(facts, roof_type='pitched')[0]
    assert row['status'] == 'ask'
    assert '逐面' in row['text'] and '压块算' not in row['text']


def test_scene_contains_actual_roof_faces_and_cross_valley_obstacle_base():
    from guangzhu.shading_geometry import build_scene
    from guangzhu.models import Design, LayoutParams, Obstacle
    record = project('sawtooth', teeth=2, slope_deg=10)
    scene = build_scene(record, Design(params=LayoutParams()))
    assert sum(cause == 'roof' for cause in scene.causes) == 4
    assert sorted(max(p[2] for p in face) for face in scene.faces) == pytest.approx([1.6569316261720353] * 4)
    obstacle = Obstacle(id='cross', label='跨谷', kind='prism', footprint=[[2, 9.7], [8, 9.7], [8, 10.9], [2, 10.9]], height_m=2)
    assert all(roofplane.elevation(record.roof, p) > .01 for p in [*obstacle.footprint, [5, 10.3]])
    record.roof.obstacles = [obstacle]
    scene = build_scene(record, Design(params=LayoutParams()))
    top = next(face for face, cause in zip(scene.faces, scene.causes) if cause == 'cross')
    assert all(p[2] == pytest.approx(2) for p in top)


def test_phase_one_clamp_sites_and_cost_match_standalone_across_faces():
    record = project()
    design = layout.generate_layout(record, {})
    for index, panel in enumerate(design.modules):
        panel.phase = 1 if index % 3 == 0 else 2
    full = structure.calculate(record, design)
    first = design.model_copy(update=dict(modules=[m.model_copy(update=dict(phase=None)) for m in design.modules if m.phase == 1]))
    alone = structure.calculate(record, first)
    actual = [r for r in full['wind']['modules'] if r['phase'] == 1]
    assert [r['clamps']['points'] for r in actual] == [r['clamps']['points'] for r in alone['wind']['modules']]
    points = [tuple(p) for r in full['wind']['modules'] for p in r['clamps']['points']]
    assert len(points) == len(set(points))
