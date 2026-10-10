"""T27 geometry, selected CEC modules and full option contracts; offline only."""
import json
import math

import numpy as np
import pytest
from shapely.geometry import Polygon

from guangzhu import catalog, electrical, layout, mcp_actions, orientation, project as storage, rules, structure
from guangzhu.brief import BriefSpec, render_brief
from guangzhu.config import ROOT
from guangzhu.models import LayoutParams, GzError


@pytest.fixture
def roof(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    p = storage.init(ROOT / 'data/demo/projects/changzhou-demo', 't27-test')
    p.roof.outline = [(0, 0), (20, 0), (20, 20), (0, 20)]
    p.roof.obstacles = []
    p.roof.keepouts = []
    p.roof.parapet_height_m = 0
    storage.save(p)
    return p


def test_edge_alignment_and_legacy_parameter_serialization(roof):
    source = storage._read(ROOT / 'data/demo/projects/rotated/project.json', type(roof))
    points = np.asarray(source.roof.outline)
    edges = np.roll(points, -1, axis=0) - points
    edge = edges[np.argmax(np.linalg.norm(edges, axis=1))]
    normal = math.degrees(math.atan2(-edge[1], edge[0])) % 360
    expected = min([normal, (normal + 180) % 360], key=lambda value: abs(value - 180))
    d = layout.generate_layout(source, dict(align='edge', azimuth_deg=100))
    assert d.params.azimuth_deg == pytest.approx(expected)
    assert all(m.azimuth == pytest.approx(expected) for m in d.modules)
    assert layout.generate_layout(source, dict(align='south')).params.azimuth_deg == 180
    assert not {'align', 'layout', 'fill_landscape'} & LayoutParams().model_dump().keys()
    assert mcp_actions._project_summary(roof.id)['edge_azimuth_deg'] == 180


def test_landscape_fills_one_shallow_row_end_without_extra_height(roof):
    roof.roof.outline = [(0, 0), (8, 0), (8, 1.4), (4, 1.4), (4, 6), (0, 6)]
    params = dict(tilt_deg=10, edge_setback_m=0)
    old = layout.generate_layout(roof, params)
    new = layout.generate_layout(roof, dict(params, fill_landscape=True))
    fills = [m for m in new.modules if m.orientation == 'landscape']
    assert len(fills) == new.statistics['fill_landscape_count'] == 1
    assert [m.model_dump() for m in new.modules if m.orientation == 'portrait'] == [m.model_dump() for m in old.modules]
    fill = fills[0]
    same_row = [m for m in old.modules if m.row == fill.row]
    assert fill.col > max(m.col for m in same_row)
    assert [m.row for m in new.modules] == sorted(m.row for m in new.modules)
    assert fill.corners[0][1:] == same_row[0].corners[0][1:]
    assert max(p[2] for p in fill.corners) < max(p[2] for p in same_row[0].corners)
    shapes = [Polygon([p[:2] for p in m.corners]) for m in new.modules]
    assert all(Polygon(roof.roof.outline).buffer(.001).covers(p) for p in shapes)
    assert all(a.intersection(b).area < 1e-8 for i, a in enumerate(shapes) for b in shapes[i + 1:])


def test_ew_pairs_share_ridge_and_have_real_aisles(roof):
    d = layout.generate_layout(roof, dict(layout='ew', walkway_every_n_rows=2, walkway_width_m=1.2))
    assert d.params.tilt_deg == 10
    assert layout.generate_layout(roof, LayoutParams(layout='ew')).params.tilt_deg == 10
    assert {m.azimuth for m in d.modules} == {90, 270}
    assert len(orientation.groups(d)) == 2
    assert len(d.modules) % 2 == 0
    for a, b in zip(d.modules[::2], d.modules[1::2]):
        assert a.row == b.row
        assert max(p[2] for p in a.corners) == max(p[2] for p in b.corners)
        assert {p[1] for p in a.corners} == {p[1] for p in b.corners}
        assert len({p[0] for p in a.corners}) == 2
    roof.requirements.structured.walkway_m_min = 1.2
    for _, view in orientation.views(d):
        assert rules.walkway_check(roof, view)['status'] == 'pass'
    result = electrical.calculate(roof, d, offline=True)
    identities = {m.id: orientation.key(m) for m in d.modules}
    assert all(len({identities[mid] for mid in s['module_ids']}) == 1 for s in result['strings'])
    rack = electrical.equipment_catalog()['racking']['ballast_ew']
    module = electrical.equipment_catalog()['modules'][roof.equipment.module_id]
    dead = module['weight_kg'] + rack['rack_weight_kg_per_module']
    ballast = 0
    for panel in d.modules:
        a, b, _, c = panel.corners
        area = math.dist(a, b) * math.dist(a, c)
        height = roof.roof.height_m + max(p[2] for p in panel.corners)
        # Independent rectangular partition: min(20*.1, 9*.2)=1.8m; do not use the product's assigned zone.
        x, y = panel.center[:2]
        edge_x, edge_y = min(x, 20 - x) <= 1.8, min(y, 20 - y) <= 1.8
        coefficient = 1.6 if edge_x and edge_y else 1.3 if edge_x or edge_y else 1
        pressure = .4 * (height / 10) ** .3 * .65 * coefficient * 1.2
        force = pressure * area * 1000
        required = 1.5 * force * (math.cos(math.radians(10)) + math.sin(math.radians(10)) / .5) / 9.81 - dead
        ballast += math.ceil(max(required, 0) / 15) * 15
    expected_mass = len(d.modules) * dead + ballast
    roof.roof.load_capacity_kn_m2 = 3  # a strong roof keeps the ballast (a weak one would be anchored instead)
    assert structure.calculate(roof, d)['mass_kg'] == pytest.approx(expected_mass)
    assert roof.equipment.racking == 'ballast_tilt'


@pytest.mark.parametrize('identifier,series,parallel', [
    ('trina-tsm-550de19', 22, 6), ('runergy-hy-wh144p8-550', 19, 7),
    ('trina-tsm-605neg19rc20', 20, 6), ('jinko-jkm605n-66hl4m-bdv', 20, 6),
])
def test_every_catalog_module_uses_own_original_cec_row(identifier, series, parallel):
    module, inverter, meta = catalog.load_cec_equipment(offline=True, module_id=identifier)
    expected = electrical.equipment_catalog()['modules'][identifier]
    assert meta['module_name'] == expected['sam_original_name']
    assert module.name == expected['pvlib_key']
    assert (meta['series'], meta['parallel']) == (series, parallel)
    assert inverter['Mppt_low'] <= meta['stc_string_vmp_v'] <= inverter['Mppt_high']
    assert 1.1 <= meta['dc_ac_ratio'] <= 1.25
    if identifier == 'jinko-jkm605n-66hl4m-bdv':
        assert module['N_s'] == 22
    if identifier == 'trina-tsm-550de19':
        old = catalog.load_cec_equipment(offline=True)
        assert meta == old[2] and module.equals(old[0])


def test_equipment_brief_and_new_project_are_optional_and_validated(roof):
    selected = dict(module_id='jinko-jkm605n-66hl4m-bdv')
    spec = BriefSpec(template='changzhou-demo', id='t27-new', text='尽量多装', equipment=selected)
    assert json.loads(render_brief(spec).split('```json\n')[1].split('\n```')[0])['equipment'] == selected
    mcp_actions._new_project(spec.id, spec.template, equipment=selected)
    assert storage.load(spec.id).equipment.module_id == selected['module_id']
    with pytest.raises(GzError):
        mcp_actions._new_project('t27-bad', spec.template, equipment=dict(module_id='missing'))
    assert not storage._path('t27-bad').exists()


def test_capacity_window_hand_projection_and_own_g02(roof):
    from guangzhu.solar import sun_position
    a = layout.row_spacing(31.81, 119.97, 10, 2.384, window=(9, 15))
    b = layout.row_spacing(31.81, 119.97, 10, 2.384, window=(10, 14))
    sun = sun_position(layout.true_solar_times(119.97, [10, 12, 14]), 31.81, 119.97)
    hand = 2.384 * math.cos(math.radians(10)) + max(
        2.384 * math.sin(math.radians(10)) * math.cos(math.radians(azimuth - 180)) / math.tan(math.radians(elevation))
        for azimuth, elevation in zip(sun.azimuth, sun.elevation))
    assert b['row_spacing_m'] == pytest.approx(hand, rel=1e-6)
    assert b['row_spacing_m'] < a['row_spacing_m']
    d = layout.generate_layout(roof, dict(tilt_deg=10, winter_window_hours=[10, 14]))
    checked = rules.evaluate(roof, d, dict(summary=dict(avg_loss_pct=0, modules_over_threshold=0), modules=[]),
                             electrical.calculate(roof, d, offline=True), structure.calculate(roof, d))
    g02 = next(row for row in checked['items'] if row['id'] == 'G02')
    assert g02['status'] == 'pass' and g02['limit'] == pytest.approx(hand, abs=.002)
    assert '10–14' in g02['name_zh']


def test_compare_trials_include_alignments_fill_and_ew(roof):
    from guangzhu import analysis
    # Make the long edge oblique while keeping the test inexpensive.
    angle = math.radians(20)
    basis = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    roof.roof.outline = list(map(tuple, np.array([[0, 0], [15, 0], [15, 12], [0, 12]]) @ basis))
    storage.save(roof)
    base = layout.generate_layout(roof, dict(azimuth_deg=200))
    storage.save_design(roof.id, base)
    analysis.analyze(roof.id, 1, offline=True)
    result = mcp_actions._compare_options(roof.id, 1, offline=True)
    assert result['current']['align'] == 'custom' and result['current']['azimuth_deg'] == 200
    assert [r['name'] for r in result['options']] == ['多装', '最快回本', '折中']
    designs = [storage.load_design(roof.id, v) for v in range(2, storage.next_version(roof.id))]
    assert {d.params.align for d in designs if d.params.layout == 'rows'} == {'south', 'edge'}
    assert any(d.params.layout == 'ew' for d in designs)
    assert all(d.params.fill_landscape for d in designs)
    assert all('align' in r and 'fill_landscape_count' in r for r in [result['current'], *result['options']])
    capacity = storage.load_design(roof.id, result['options'][0]['version'])
    assert capacity.params.winter_window_hours == (10, 14)
    assert '早晚前后排' in result['capacity_note']
    assert len(analysis.serialized(result).encode()) + 128 <= 2048


def test_real_ew_group_energy_and_crosscheck_sum(roof, tmp_path):
    from guangzhu import analysis, shading, yieldsim
    roof.roof.outline = [(0, 0), (14, 0), (14, 10), (0, 10)]
    roof.economics.monthly_kwh, roof.economics.shifts = 10000, 1
    roof.equipment.module_id = 'jinko-jkm605n-66hl4m-bdv'
    storage.save(roof)
    d = layout.generate_layout(roof, dict(layout='ew', fill_landscape=True))
    storage.save_design(roof.id, d)
    shadows = shading.analyze_design(roof, d, offline=True)
    energy, generated = analysis.generation(roof, d, shadows, d.statistics['dc_kw'], offline=True)
    expected = 0
    losses = {m['id']: m['total_loss_pct'] for m in shadows['modules']}
    from guangzhu.economics import load_assumptions
    loss = load_assumptions()['design_system_loss_pct']['value']
    for _, view in orientation.views(d):
        own = yieldsim.simulate_design_yields(roof.site.lat, roof.site.lon, tilt=10, azimuth=view.params.azimuth_deg,
                                              loss_percent=loss, offline=True, module_id=roof.equipment.module_id)
        expected += own['results']['b']['specific_yield_kwh_kwp'] * .605 * sum(1 - losses[m.id] / 100 for m in view.modules)
    assert energy['p50'] == pytest.approx(expected)
    assert sum(energy['hourly']['kwh']) == pytest.approx(energy['p50'])
    cross = mcp_actions._crosscheck_yield(roof.id, 1, offline=True)
    assert cross['total_kwh']['b'] == pytest.approx(sum(g['kw'] * g['per_kw']['b'] for g in cross['groups']), abs=.002)
    analysis.analyze(roof.id, 1, offline=True)
    cash = mcp_actions._read(roof.id, 'analysis/v1/economics.json')
    assert '"hourly"' not in json.dumps(cash)
    assert len(generated['groups']) == 2


def test_landscape_ew_pairs_keep_both_bottom_lines_and_gap(roof):
    # A short north-side notch intersects only the taller/deeper portrait halves.
    base = layout.generate_layout(roof, dict(layout='ew', edge_setback_m=0))
    module = electrical.equipment_catalog()['modules'][roof.equipment.module_id]
    long, short = module['length_m'], module['width_m']
    pair = base.modules[:2]
    occupied = [Polygon(np.array(m.corners)[:, :2]) for m in pair]
    # Offer a separate along-ridge bay limited to the two shallow outside strips.
    from shapely.geometry import box
    from shapely.ops import unary_union
    strips = []
    ymax = min(p[1] for p in pair[0].corners) - .04
    for m in pair:
        xy = np.array(m.corners)[:, :2]
        x = xy[0, 0]
        other = x + short * math.cos(math.radians(10)) * (1 if m.azimuth == 270 else -1)
        strips.append(box(min(x, other), ymax - long, max(x, other), ymax))
    free = unary_union([*occupied, *strips])
    fills = layout.landscape_fill(pair, free, long, short, .02, False, roof.roof, True)
    assert len(fills) == 2 and {m.azimuth for m in fills} == {90, 270}
    for original, filled in zip(pair, fills):
        axis = 0  # Low edges are N–S, so x and z must stay fixed.
        assert filled.corners[0][axis] == original.corners[0][axis]
        assert filled.corners[0][2] == original.corners[0][2]
        assert max(p[2] for p in filled.corners) < max(p[2] for p in original.corners)
    assert abs(fills[0].corners[2][0] - fills[1].corners[2][0]) > .5
    d = base.model_copy(update=dict(modules=[*pair, *fills]))
    from guangzhu import shading
    result = shading.analyze_design(roof, d, offline=True)
    assert len(result['modules']) == 4
    assert all(0 <= row['total_loss_pct'] <= 100 for row in result['modules'])
    raised = d.model_copy(deep=True)
    for module in raised.modules[2:]:
        module.corners = tuple((x, y, z + 2) for x, y, z in module.corners)
    higher = shading.analyze_design(roof, raised, offline=True)
    assert higher['summary']['avg_loss_pct'] != pytest.approx(result['summary']['avg_loss_pct'])


def test_b_chain_selected_module_changes_real_power(roof):
    from guangzhu import weather, yieldsim
    nasa, _ = weather.load_nasa_hourly(roof.site.lat, roof.site.lon, 2023, offline=True)
    values = {}
    for identifier in electrical.equipment_catalog()['modules']:
        selected = catalog.load_cec_equipment(offline=True, module_id=identifier)
        result = yieldsim.simulate_pvlib_detailed(nasa, roof.site.lat, roof.site.lon, equipment=selected)
        values[identifier] = result['specific_yield_kwh_kwp']
        assert result['metadata']['catalog']['module_key'] == selected[0].name
    assert len(set(values.values())) == 4


def test_tool_budget_and_equipment_schemas():
    from guangzhu import mcp_server
    from jsonschema import Draft202012Validator
    payload = json.dumps([t.model_dump(by_alias=True, exclude_none=True) for t in mcp_server.TOOLS], ensure_ascii=False, separators=(',', ':'))
    assert len(payload.encode()) <= 16 * 1024
    Draft202012Validator(mcp_server.SCHEMAS['gz_new_project']).validate(dict(
        project_id='t27', template='changzhou-demo', equipment=dict(module_id='trina-tsm-605neg19rc20')))
