"""Independent wind arithmetic, conservation, geometry and shared quantity contracts."""
import json
import math

import pytest
from shapely.affinity import rotate
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from guangzhu import costs, electrical, layout, structure, wind
from guangzhu.config import DATA_DIR
from guangzhu.models import Project, WindSettings
from test_t28 import owner, phase_context


def project(name='changzhou-demo'):
    return Project.model_validate_json((DATA_DIR / f'demo/projects/{name}/project.json').read_text(encoding='utf-8'))


def test_fixed_force_oracles_and_one_fewer_block_fail():
    for angle, count, lift, slide, friction in [(0, 6, 87.43119266055045, 87.43119266055045, 12.6),
                                                (30, 13, 71.69839604074141, 189.12958870129188, 604.7943674201633)]:
        result = wind.ballast(2, .2 * 1.2 * 1.6, angle, 30)
        assert result['normal_force_n'] == pytest.approx(768)
        assert result['lift_required_kg'] == pytest.approx(lift)
        assert result['slide_required_kg'] == pytest.approx(slide)
        assert result['ballast_blocks'] == count
        assert result['friction_n'] == pytest.approx(friction)
        assert result['friction_n'] >= result['sliding_demand_n']
        assert result['friction_n'] - .5 * 15 * 9.81 < result['sliding_demand_n']
    assert wind.ballast(2, 0, 30, 30)['ballast_kg'] == 0


def test_integrated_corner_pressure_uses_actual_height_geometry_and_effective_rack():
    record = project()
    record.roof.outline = [(0, 0), (20, 0), (20, 10), (0, 10)]
    record.roof.height_m = 10
    record.roof.obstacles = []
    record.roof.keepouts = []
    record.roof.wind = WindSettings(basic_pressure_kpa=.2)
    design = layout.generate_layout(record, {})
    panel = design.modules[0]
    panel.corners = [(0, 0, 0), (1, 0, 0), (1, math.sqrt(3), 1), (0, math.sqrt(3), 1)]
    panel.center = (.5, math.sqrt(3) / 2, .5)
    panel.tilt = 30
    design.modules = [panel]
    module, rack = dict(weight_kg=24), dict(rack_weight_kg_per_module=6)
    actual, _ = wind.calculate(record, design, module, rack)
    row = actual['modules'][0]
    expected_pressure = .2 * (11 / 10) ** .3 * .8 * 1.6 * 1.2
    force = expected_pressure * 2 * 1000
    required = 1.5 * (force * math.cos(math.pi / 6) + force * .5 / .5) / 9.81 - 30
    assert row['zone'] == 'corner' and row['height_m'] == 11
    assert row['area_m2'] == pytest.approx(2)
    assert row['pressure_kpa'] == pytest.approx(expected_pressure)
    assert row['ballast_blocks'] == math.ceil(required / 15)
    design.params.layout = 'ew'
    other, _ = wind.calculate(record, design, module, rack)
    assert other['modules'][0]['pressure_kpa'] == pytest.approx(expected_pressure * .65 / .8)


def test_overlapping_racks_conserve_mass_and_union_area():
    shapes = {'A': box(0, 0, 4, 2), 'B': box(2, 0, 6, 2)}
    zones = {'left': box(0, 0, 3, 2), 'right': box(3, 0, 6, 2)}
    result = wind.zone_loads(shapes, {'A': 80, 'B': 160}, zones)
    assert result['left'] == pytest.approx(dict(area_m2=6, mass_kg=100, load_kn_m2=.1635))
    assert result['right'] == pytest.approx(dict(area_m2=6, mass_kg=140, load_kn_m2=.2289))
    assert sum(r['area_m2'] for r in result.values()) == 12
    assert sum(r['mass_kg'] for r in result.values()) == 240


def test_worst_zone_not_global_average():
    zones = {'corner': box(0, 0, 2, 1), 'middle': box(2, 0, 12, 1)}
    result = wind.zone_loads(zones, {'corner': 100, 'middle': 100}, zones)
    assert result['corner']['load_kn_m2'] == pytest.approx(.4905)
    assert result['middle']['load_kn_m2'] == pytest.approx(.0981)
    assert 200 * .00981 / 12 == pytest.approx(.1635)
    assert max(r['load_kn_m2'] for r in result.values()) > .3


@pytest.mark.parametrize('outline', [box(0, 0, 20, 10), box(0, 0, 20, .8),
                                   Polygon([(0, 0), (20, 0), (20, 4), (4, 4), (4, 10), (0, 10)])])
def test_regions_cover_rotated_concave_and_narrow_roofs(outline):
    width, zones = wind.zones(list(outline.exterior.coords)[:-1], 10)
    assert unary_union(list(zones.values())).symmetric_difference(outline).area < 1e-8
    assert sum(z.area for z in zones.values()) == pytest.approx(outline.area)
    turned = rotate(outline, 37, origin=(0, 0))
    other_width, others = wind.zones(list(turned.exterior.coords)[:-1], 10)
    assert width == pytest.approx(other_width)
    for name, shape in zones.items():
        assert rotate(shape, 37, origin=(0, 0)).symmetric_difference(others[name]).area < 1e-8


def test_zone_width_centers_and_city_status():
    width, zones = wind.zones([(0, 0), (20, 0), (20, 10), (0, 10)], 10)
    assert width == 1
    assert [wind.classify(point, zones) for point in [(0.5, .5), (5, .5), (5, 5), (1, 1)]] == [
        'corner', 'edge', 'middle', 'corner']
    rows = wind.catalog()
    assert set(rows) == set('南京 无锡 徐州 常州 苏州 南通 连云港 淮安 盐城 扬州 镇江 泰州 宿迁'.split())
    assert all(row['status'] == '示意' and row['page'] == '未核验' and '缺官方' in row['missing'] for row in rows.values())
    record = project()
    assert wind.city_pressure(record.site)['city'] == '常州'
    record.site.wind_city = '南京'
    assert wind.city_pressure(record.site)['selection'] == '用户指定'
    assert wind.city_pressure(record.site)['city'] == '南京'


def test_concave_corner_and_redundant_collinear_vertex():
    outline = [(0, 0), (20, 0), (20, 4), (4, 4), (4, 10), (0, 10)]
    _, regions = wind.zones(outline, 10)
    assert wind.classify((3.8, 4.2), regions) == 'corner'
    assert wind.classify((4.2, 3.8), regions) == 'corner'
    _, ordinary = wind.zones([(0, 0), (20, 0), (20, 10), (0, 10)], 10)
    _, redundant = wind.zones([(0, 0), (10, 0), (20, 0), (20, 10), (0, 10)], 10)
    assert ordinary['corner'].symmetric_difference(redundant['corner']).area == 0


@pytest.mark.parametrize('params', [{}, {'layout': 'ew'}, {'fill_landscape': True}])
def test_real_geometry_mass_quantities_and_deleted_panels(params):
    record = project()
    design = layout.generate_layout(record, params)
    removed = design.modules.pop(0)
    design.removed_modules.append(removed)
    result = structure.calculate(record, design)
    rows = result['wind']['modules']
    assert len(rows) == len(design.modules)
    assert result['ballast_mass_kg'] == sum(r['ballast_kg'] for r in rows)
    assert result['mass_kg'] == pytest.approx(len(rows) * 34.6 + result['ballast_mass_kg'])
    assert sum(r['mass_kg'] for r in result['wind']['zones'].values()) == pytest.approx(result['mass_kg'])
    assert sum(r['area_m2'] for r in result['wind']['zones'].values()) == pytest.approx(result['rack_projection_area_m2'])
    assert result['added_kn_m2'] == max(r['load_kn_m2'] for r in result['wind']['zones'].values())
    # Wind ballast would overload the 0.5 kN/m² demo roof, so every such rack is anchored to the slab instead.
    assert record.roof.load_capacity_kn_m2 == .5 and result['status'] == 'pass'
    assert all(r['fixing'] == 'anchor' and r['ballast_kg'] == 0 and r['anchors'] >= 2 for r in rows)
    assert result['wind']['anchor_count'] == sum(r['anchors'] for r in rows) == sum(
        z.get('anchors', 0) for z in result['wind']['zones'].values())
    assert '锚栓' in result['evidence'] and '锚栓' in result['note']
    assert all(r['height_m'] == record.roof.height_m + max(p[2] for p in m.corners)
               for r, m in zip(rows, design.modules))
    quote = costs.itemized(record, design.statistics['dc_kw'], design, load=result)
    assert next(r['quantity'] for r in quote['items'] if r['key'] == 'ballast') == result['ballast_mass_kg'] / 1000 == 0
    assert next(r['quantity'] for r in quote['items'] if r['key'] == 'flat_anchor') == result['wind']['anchor_count']
    strong = project()
    strong.roof.load_capacity_kn_m2 = 3
    ballasted = structure.calculate(strong, design)
    assert ballasted['status'] == 'pass' and 'anchor_count' not in ballasted['wind']
    assert ballasted['ballast_mass_kg'] > 30 * len(rows) and not any('fixing' in r for r in ballasted['wind']['modules'])
    assert ballasted['added_kn_m2'] > result['added_kn_m2']


def test_clamp_spacing_and_force_are_independent_and_no_duplicate_entities():
    from guangzhu.wind_clamps import arrange
    record = project('metal-demo-s')
    design = layout.generate_layout(record, {})
    panel = design.modules[0]
    occupied = set()
    result = arrange(record.roof, panel, 3, {}, occupied)
    assert result['force_required'] == 4
    assert result['required'] >= 4
    assert result['adopted'] <= result['available']
    assert result['passed']
    assert result['max_actual_spacing_m'] <= 1.2 + 1e-8
    failed = arrange(record.roof, panel, 100, {}, set())
    assert not failed['passed'] and failed['required'] > failed['available']
    sparse = arrange(record.roof, panel, .01, {'seam_spacing_m': 10}, set())
    assert not sparse['passed']
    second = arrange(record.roof, panel, 3, {}, occupied)
    assert not set(second['points']) & set(result['points'])
    assert all(math.dist(a, b) >= .2 - 1e-8 for a in result['points'] for b in second['points'])


def test_optional_wind_fields_preserve_legacy_serialization_and_explicit_zero():
    record = project()
    assert 'wind' not in record.model_dump()['roof']
    assert 'wind_city' not in record.model_dump()['site']
    record.roof.wind = WindSettings(basic_pressure_kpa=0)
    result = structure.calculate(record, layout.generate_layout(record, {}))
    assert result['wind']['basic_pressure_kpa'] == 0
    assert result['ballast_mass_kg'] == 0
    with pytest.raises(ValueError):
        WindSettings(clamp_min_spacing_m=2, clamp_max_spacing_m=1)


def test_four_real_clamp_sites_pass_and_three_fail():
    from guangzhu.wind_clamps import arrange
    from guangzhu.roofplane import elevation
    record = project('metal-demo-s')
    panel = layout.generate_layout(record, {}).modules[0].model_copy(deep=True)
    panel.corners = [(x, y, elevation(record.roof, (x, y)) + .1) for x, y in [(0, 0), (1.6, 0), (1.6, 1.1), (0, 1.1)]]
    settings = dict(seam_spacing_m=.8, seam_offset_m=.4, clamp_min_spacing_m=.8)
    four = arrange(record.roof, panel, 3, settings, set())
    assert four['required'] == four['available'] == four['adopted'] == 4
    assert four['passed']
    three = arrange(record.roof, panel, 3, settings, {four['points'][0]})
    assert three['available'] == 3 and not three['passed']


def test_hot_energy_cache_height_recalculates_wind_cost_and_does_not_write(tmp_path, monkeypatch):
    from guangzhu import analysis, mcp_actions, project as storage
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    record = storage.init(DATA_DIR / 'demo/projects/changzhou-demo', 't31-hot-height')
    record.roof.load_capacity_kn_m2 = 3  # a strong roof keeps ballast, so a taller roof needs more of it
    storage.save(record)
    design = layout.generate_layout(record, {})
    storage.save_design(record.id, design)
    original = analysis.analyze(record.id, 1, offline=True)
    old_load = mcp_actions._read(record.id, 'analysis/v1/structure.json')
    record = storage.load(record.id)
    original_height = record.roof.height_m
    record.roof.height_m = 30
    storage.save(record)
    paths = list(storage._path(record.id, 'analysis/v1').glob('*.json'))
    before = {p: p.read_bytes() for p in paths}
    def no_generation(*args, **kwargs):
        pytest.fail('Height-only hot cache must reuse valid roof-relative energy')
    monkeypatch.setattr(analysis, 'generation', no_generation)
    current = mcp_actions._what_if(record.id, 1, {}, True)
    new_load = structure.calculate(record, design)
    assert new_load['wind']['modules'][0]['height_m'] - old_load['wind']['modules'][0]['height_m'] == pytest.approx(30 - original_height)
    assert new_load['ballast_mass_kg'] > old_load['ballast_mass_kg']
    assert current['economics']['capex_cny'] > original['economics']['capex_cny']
    assert current['load']['added_kn_m2'] > original['load']['added_kn_m2']
    assert all(path.read_bytes() == value for path, value in before.items())


def test_metal_rule_and_cost_share_actual_points():
    from guangzhu import rules, shading
    record = project('metal-demo-s')
    design = layout.generate_layout(record, {})
    design.modules = design.modules[:4]
    record.roof.wind = WindSettings(clamp_capacity_kn=.001)
    load = structure.calculate(record, design)
    electric = electrical.calculate(record, design, offline=True)
    shade = shading.analyze_design(record, design, offline=True)
    checked = rules.evaluate(record, design, shade, electric, load, None)
    row = next(r for r in checked['items'] if r['id'] == 'W01')
    assert row['status'] == 'fail' and row['level'] == 'hard'
    assert '换抗拔力更大的夹具' in row['hint_zh']
    quantity = load['wind']['clamp_count']
    assert quantity == sum(r['clamps']['adopted'] for r in load['wind']['modules'])
    quote = costs.itemized(record, len(design.modules) * .55, design, electric, load)
    assert next(r['quantity'] for r in quote['items'] if r['key'] == 'wind_clamp') == quantity


def test_phase_wind_bom_and_first_phase_actual_cost(phase_context, tmp_path):
    from openpyxl import load_workbook
    from guangzhu.models import Design
    from guangzhu.report.deliverables import write_deliverables
    context = phase_context
    wind_result = context['structure']['wind']
    cash = context['economics']
    first_wind = cash['first_phase_wind']
    assert {r['id'] for r in first_wind['modules']} == {m['id'] for m in context['design']['modules'] if m['phase'] == 1}
    assert first_wind['ballast_mass_kg'] == sum(r['ballast_kg'] for r in first_wind['modules'])
    # The 0.5 kN/m² demo roof cannot carry the wind ballast, so phase one is anchored like the whole site.
    assert first_wind['anchor_count'] == sum(r['anchors'] for r in first_wind['modules']) >= 2 * len(first_wind['modules'])
    record = Project.model_validate(context['project'])
    design = Design.model_validate(context['design'])
    design.modules = [m for m in design.modules if m.phase == 1]
    quote = costs.itemized(record, len(design.modules) * .55, design,
                           electrical.calculate(record, design, offline=True), structure.calculate(record, design))
    assert cash['phases'][0]['capex_cny'] == pytest.approx(quote['capex_cny'])
    write_deliverables(context['project_id'], 1, tmp_path)
    book = load_workbook(tmp_path / 'bom-v1.xlsx', data_only=True)
    rows = list(book['分期材料'].values)[1:]
    assert sum(r[3] for r in rows if r[1].endswith('压块')) == wind_result['ballast_blocks']
    for phase in (1, 2):
        expected = sum(r['ballast_blocks'] for r in wind_result['modules'] if r['phase'] == phase)
        assert sum(r[3] for r in rows if r[0] == phase and r[1].endswith('压块')) == expected
        anchors = sum(r['anchors'] for r in wind_result['modules'] if r['phase'] == phase and r.get('fixing') == 'anchor')
        assert sum(r[3] for r in rows if r[0] == phase and r[1].startswith('化学锚栓')) == anchors > 0
    book.close()
