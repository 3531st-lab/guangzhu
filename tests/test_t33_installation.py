"""Independent geometry, occupancy and recurring-cash contracts for new installations."""
import math

import pytest
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from guangzhu import finance, installation, layout, structure
from guangzhu.config import ROOT
from guangzhu.models import Project, Roof


def project(kind='ground', width=24, depth=40, **settings):
    record = Project.model_validate_json((ROOT / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    record.roof = Roof.model_validate(dict(type=kind, outline=[[0, 0], [width, 0], [width, depth], [0, depth]],
                                          height_m=0, parapet_height_m=0, load_capacity_kn_m2=.5, **{kind: settings}))
    record.requirements.structured = record.requirements.structured.__class__()
    record.equipment.racking = 'ground_pile' if kind == 'ground' else 'carport_steel'
    if kind == 'carport':
        record.roof = Roof.model_validate(dict(record.roof.model_dump(), **installation.parking(record.roof)))
    return record


def test_parking_has_real_bays_clear_aisles_and_reserved_columns():
    record = project('carport', depth=38.1, direction_deg=0)
    facilities = record.roof.carport
    assert len(facilities.bays) == 40
    assert len(record.roof.planes) == 2
    for bay in facilities.bays:
        assert Polygon(bay.polygon).area == pytest.approx(2.4 * 5.1)
    clear = unary_union([Polygon(p.polygon) for p in [*facilities.bays, *facilities.aisles]])
    assert all(not clear.intersects(Point(point).buffer(.1)) for points in facilities.columns.values() for point in points)
    assert sum(Polygon(p.outline).area for p in record.roof.planes) == pytest.approx(24 * 21.6)


def test_explicit_zero_tilt_and_canopy_snapshot_survive_template_change():
    record = project('carport', direction_deg=0)
    result = layout.generate_layout(record, dict(tilt_deg=0, clear_height_m=2.2))
    assert result.modules
    assert all(m.tilt == 0 for m in result.modules)
    assert all(f['clear_height_m'] == pytest.approx(2.2) for f in installation.facilities(record, result)['faces'])
    assert record.roof.planes[0].slope_deg == 5
    record.roof.planes[0].offset_m = 7
    assert installation.effective(record, result).roof.planes[0].offset_m == pytest.approx(2.5)
    empty = record.model_copy(deep=True)
    empty.roof.planes = []
    assert not layout.generate_layout(empty, {}).modules


def test_ground_true_roads_fences_heights_and_stable_partial_rack():
    record = project(width=120, depth=80, road_every=2)
    result = layout.generate_layout(record, dict(lower_edge_m=.3, fill_landscape=True))
    facts = installation.facilities(record, result)
    assert facts['land_mu'] == pytest.approx(14.4)
    assert facts['fence_quote_m'] == 400
    assert facts['fence_physical_m'] == 384
    assert min(p[2] for m in result.modules for p in m.corners) == .3
    assert facts['roads']
    road = unary_union([Polygon(p) for p in facts['roads']])
    assert all(road.intersection(Polygon([p[:2] for p in m.corners])).area < 1e-7 for m in result.modules)
    original = facts['piles'][0]
    subset = result.model_copy(deep=True)
    subset.modules = [m for m in result.modules if m.id == original['modules'][0]]
    actual = installation.facilities(record, subset)
    assert len(actual['piles']) == 2
    assert actual['piles'][0] == original
    assert structure.calculate(record, subset)['status'] == 'na'


def test_annual_land_rent_exact_pretax_oracle_in_every_mode():
    for mode in ('self', 'emc', 'rent'):
        args = dict(capex=10000, hardware=8000, saving=3000, export=200, om=100, discount=.08, mode=mode)
        zero = finance.ledger(**args, land_rent=0)
        rent = finance.ledger(**args, land_rent=1440)
        assert rent['pretax']['npv_cny'] - zero['pretax']['npv_cny'] == pytest.approx(-15371.677711567545)
        assert all(row['land_rent_cny'] == 1440 and row['rent'] == 0 for row in rent['accounts'])


def test_resize_repositions_supports_impossible_move_rejects_and_delete_keeps_bays():
    record = project('carport', direction_deg=0)
    roof = record.roof.model_dump()
    original = roof['carport']['columns']['1']
    roof['planes'][0]['outline'] = [(2, 5.5), (21, 5.5), (21, 16.3), (2, 16.3)]
    resized = Roof.model_validate(roof)
    points = resized.carport.columns['1']
    assert points != original and len(points) >= 2
    assert all(Polygon(resized.planes[0].outline).covers(Point(p).buffer(.1)) for p in points)
    bad = resized.model_dump()
    bad['planes'][0]['outline'] = [(2, 5.5), (21, 5.5), (21, 9), (2, 9)]
    with pytest.raises(ValueError, match='无法布置'):
        Roof.model_validate(bad)
    record.roof.planes = record.roof.planes[1:]
    result = layout.generate_layout(record, {})
    actual = installation.facilities(record, result)
    assert actual['bay_count'] == 40
    assert all(c['plane'] == 2 for c in actual['columns'])


def test_concave_same_canopy_fixed_xy_route_drops_at_real_gaps():
    from guangzhu.models import Module, RoofPlane
    record = project('carport', direction_deg=0)
    record.roof.planes = [RoofPlane(id=1, outline=[(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)],
                                   slope_deg=0, slope_azimuth_deg=180, offset_m=2.9)]
    def module(col, xy):
        x, y = xy
        return Module(id=f'P1-R01-1-C{col:03}', row=1, tier=1, col=col, center=(x, y, 3),
                      corners=[(x, y, 3), (x + .1, y, 3), (x + .1, y + .1, 3), (x, y + .1, 3)],
                      tilt=0, azimuth=180, orientation='portrait')
    a, b = module(1, (2, 8)), module(2, (8, 2))
    path = installation.cable_route(record.roof, {m.id: m for m in (a, b)}, [(a.center[:2], a.id), (b.center[:2], b.id)])
    assert sum(math.dist(a, b) for a, b in zip(path, path[1:])) == pytest.approx(18)
    assert [4, 8, 0] in path and [8, 4, 0] in path
    assert [4, 8, 3] in path and [8, 4, 3] in path


@pytest.mark.parametrize('kind,height,status', [('ground', .3, 'pass'), ('ground', .299, 'fail'),
                                               ('carport', 2.2, 'pass'), ('carport', 2.199, 'fail')])
def test_real_corner_height_rules(kind, height, status):
    from guangzhu import electrical, rules
    record = project(kind, direction_deg=0) if kind == 'carport' else project(kind)
    result = layout.generate_layout(record, dict(clear_height_m=height) if kind == 'carport' else dict(lower_edge_m=.3))
    if kind == 'ground' and height < .3:
        result.modules[0].corners = tuple((x, y, height if z == .3 else z) for x, y, z in result.modules[0].corners)
    shadows = dict(modules=[dict(id=m.id, total_loss_pct=0) for m in result.modules], summary=dict(avg_loss_pct=0))
    electric = electrical.calculate(record, result, offline=True)
    checked = rules.evaluate(record, result, shadows, electric, structure.calculate(record, result))
    target = 'G08' if kind == 'ground' else 'G09'
    assert next(r for r in checked['items'] if r['id'] == target)['status'] == status
    assert next(r for r in checked['items'] if r['id'] == 'L01')['status'] == 'na'


def test_full_canopies_shade_even_after_modules_removed_and_own_front_stays_clear():
    import numpy as np
    from guangzhu.shading_geometry import build_scene, ray_hits, sun_vector
    record = project('carport', direction_deg=0)
    result = layout.generate_layout(record, dict(tilt_deg=0))
    empty = result.model_copy(deep=True)
    empty.modules = []
    scene = build_scene(record, empty)
    # From the northern canopy, a low southward ray hits the raised southern full canopy.
    scene.project.roof.planes[0].offset_m = 5
    empty.installation_roof = scene.project.roof
    scene = build_scene(record, empty)
    points = np.array([[12, 21.8, 2.9], [12, 10, 5.1]])
    assert list(ray_hits(scene, points, sun_vector(10, 180), np.array([-1, -1]))) == ['roof', '']


def test_land_policy_does_not_approve_ordinary_cultivated_land():
    from guangzhu.sitecheck import rows
    for land in ('cultivated', 'permanent'):
        checks = rows(dict(land_type=land), roof_type='ground')
        assert next(r for r in checks if r['item'] == '土地性质')['status'] == 'risk'
        assert '任何耕地' in next(r for r in checks if r['item'] == '土地性质')['text']


def test_carport_positive_area_overlap_and_real_outside_edit_are_rejected():
    record = project('carport', direction_deg=0)
    roof = record.roof.model_dump()
    roof['planes'][1]['outline'] = [(0, 16.299), (24, 16.299), (24, 27.1), (0, 27.1)]
    with pytest.raises(ValueError, match='不能重叠'):
        Roof.model_validate(roof)
    roof = record.roof.model_dump()
    roof['planes'][0]['outline'] = [(-.001, 5.5), (24, 5.5), (24, 16.3), (-.001, 16.3)]
    with pytest.raises(ValueError):
        Roof.model_validate(roof)
