"""Independent livestock geometry, monthly energy and incremental cost contracts."""
from types import SimpleNamespace
import json

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from guangzhu import costs, economics, electrical, installation, layout, livestock, sitecheck, structure
from guangzhu.config import ROOT
from guangzhu.models import Project, Roof
from test_t30_economics import day


def demo(kind):
    return Project.model_validate_json((ROOT / f'data/demo/projects/{kind}-demo/project.json').read_text(encoding='utf-8'))


def test_fan_independent_month_sums_seasons_night_and_sundays():
    stamps = pd.date_range('2024-01-01', '2025-01-01', inclusive='left', freq='h', tz='Asia/Shanghai')
    values = np.array(economics.load_curve(3720, 4, [p.isoformat() for p in stamps]))
    for month in range(1, 13):
        assert values[stamps.month == month].sum() == pytest.approx(3720)
    winter = values[(stamps.month == 1) & (stamps.hour == 10)][0]
    summer = values[(stamps.month == 7) & (stamps.hour == 10)][0]
    assert summer > winter
    assert summer / values[(stamps.month == 7) & (stamps.hour == 22)][0] == pytest.approx(5)
    assert len(set(values[(stamps.month == 7) & (stamps.hour == 10)])) == 1


def test_shadow_union_clipping_actual_height_night_and_day_weighting():
    face = np.array([[2, 2, 2], [6, 2, 2], [6, 4, 2], [2, 4, 2]])
    scene = SimpleNamespace(faces=[face, face.copy()], bases={})
    site = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    assert livestock.shadow_area(scene, [0, 0, 1], site) == pytest.approx(8)
    assert livestock.shadow_area(scene, [2, 0, 1], site) == pytest.approx(4)
    assert livestock.shadow_area(scene, [0, 0, -1], site) is None
    totals = livestock.light_totals([(1, 20, 31), (2, 80, 28), (2, 60, 28)], 100)
    assert totals['sun_pct'] == pytest.approx(100 * (1 - (20*31 + 140*28) / (100*87)))
    assert totals['represented_hours'] == 87
    assert 'hourly' not in totals


@pytest.mark.parametrize('animal,height', [('sheep', 1.5), ('cow', 2.5)])
def test_defaults_preserve_saved_low_and_zero_threshold(animal, height):
    roof = demo('grazing').roof.model_dump()
    roof.update(animal=animal, ground_sun_min_pct=0)
    roof['ground'].pop('lower_edge_m')
    assert Roof.model_validate(roof).ground.lower_edge_m == height
    for low in (.3, .5):
        roof['ground']['lower_edge_m'] = low
        actual = Roof.model_validate(roof)
        assert actual.ground.lower_edge_m == low and actual.ground_sun_min_pct == 0


def test_barn_keepout_identity_zero_actual_avoidance_and_costs():
    record = demo('barn')
    record.roof.keepouts[0].clearance_m = 0
    result = layout.generate_layout(record, {})
    footprints = [Polygon([p[:2] for p in m.corners]) for m in result.modules]
    for zone in record.roof.keepouts:
        distance = 0 if zone.id == 'vent-1' else 1
        assert livestock.clearance(record.roof, zone, .5) == distance
        assert all(p.intersection(Polygon(zone.polygon).buffer(distance)).area < 1e-7 for p in footprints)
    load = structure.calculate(record, result)
    electric = electrical.calculate(record, result, offline=True)
    priced = costs.itemized(record, result.statistics['dc_kw'], result, electric, load)
    items = priced['items']
    assert sum(p['quantity'] for p in items if p['key'] == 'barn_clamp') == load['wind']['clamp_count']
    assert all(p['unit_price_cny'] == 54 for p in items if p['key'] == 'barn_rail')
    assert all(p['unit_price_cny'] == 6 for p in items if p['key'] == 'barn_clamp')
    assert not any(p['key'] in ('metal_rail', 'wind_clamp') for p in items)
    checks = sitecheck.rows({}, roof_type='pitched', roof=record.roof.model_dump())
    assert {'氨气腐蚀','羽毛灰尘','养殖场防火'} <= {r['item'] for r in checks}


def test_grazing_costs_actual_dc_and_component_only_saving():
    record = demo('grazing')
    result = layout.generate_layout(record, {})
    load = structure.calculate(record, result)
    electric = electrical.calculate(record, result, offline=True)
    priced = costs.itemized(record, result.statistics['dc_kw'], result, electric, load)
    rows = priced['items']
    assert not any(r['key'] == 'ground_fence' for r in rows)
    assert next(r['quantity'] for r in rows if r['key'] == 'animal_fence') == 200
    actual = sum(r['length_m'] for r in electric['cables']['dc'])
    assert sum(r['quantity'] for r in rows if r['key'] == 'dc_animal_protection') == pytest.approx(actual)
    assert not any(r['key'] == 'dc_animal_protection' for r in load['extra_cost_items'])
    cash = economics.calculate(record, result.statistics['dc_kw'], day('2023-07-15'),
                               design=result, electric=electric, load=load, sensitivity=False)
    saving = cash['operating_costs']['weeding']
    assert saving['saving_cny'] == pytest.approx(saving['original_base_cny'] * .1)
    assert cash['operating_costs']['base_om_cny'] == pytest.approx(saving['original_base_cny'] * .9)


def test_cleaning_none_only_and_plain_serialization_unchanged():
    record = demo('barn')
    design = layout.generate_layout(record, {})
    load = structure.calculate(record, design)
    electric = electrical.calculate(record, design, offline=True)
    for supplied, expected in [(None, 4), (0, 0), (1, 1)]:
        record.economics.cleaning_times = supplied
        cash = economics.calculate(record, design.statistics['dc_kw'], day('2023-07-15'),
                                   design=design, load=load, electric=electric, sensitivity=False)
        assert cash['operating_costs']['cleaning_times'] == expected
    for path in (ROOT / 'data/demo/projects').glob('*/project.json'):
        if path.parent.name in ('barn-demo', 'grazing-demo'):
            continue
        original = json.loads(path.read_text(encoding='utf-8'))
        model = Project.model_validate(original).model_dump(mode='json')
        assert 'use' not in model['roof']
        assert 'animal' not in model['roof']
        assert all('preset' not in k and 'clearance_m' not in k for k in model['roof']['keepouts'])


def test_actual_low_g08_failed_g10_edit_and_no_hourly_payload():
    from guangzhu import rules
    record = demo('grazing')
    record.roof.ground.lower_edge_m = .3
    record.roof.ground_sun_min_pct = 100
    design = layout.generate_layout(record, {})
    shading = dict(modules=[dict(id=m.id,total_loss_pct=0) for m in design.modules], summary=dict(avg_loss_pct=0))
    result = rules.evaluate(record, design, shading, electrical.calculate(record, design, offline=True), structure.calculate(record, design))
    checks = {row['id']:row for row in result['items']}
    assert checks['G08']['status'] == 'fail' and checks['G08']['value'] == .3 and checks['G08']['limit'] == 1.5
    assert checks['G10']['status'] == 'fail' and checks['G10']['suggestion']['name'] == 'extra_row_gap_m'
    assert checks['G10']['suggestion']['value'] == 1
    fresh = layout.generate_layout(record, dict(extra_row_gap_m=1))
    assert fresh.statistics['row_spacing_m'] == pytest.approx(design.statistics['row_spacing_m'] + 1)
    assert fresh.modules[0].corners != design.modules[0].corners or len(fresh.modules) != len(design.modules)
    light = livestock.ground_light(record, fresh)
    assert len(light['months']) == 12 and len(json.dumps(light)) < 5000


def test_manual_zero_fan_and_common_load_priority():
    from guangzhu import tariff
    record = demo('barn')
    record.economics.monthly_kwh = 1
    record.economics.self_use_ratio = 0
    energy = day('2023-07-15')
    assert tariff.integrate(record, energy, 0, .65)['self_use_kwh'] == 0
    for mode in ('phase', 'no-export'):
        record.requirements.structured.phase1_kw = 10 if mode == 'phase' else None
        record.requirements.structured.export_allowed = mode != 'no-export'
        value = tariff.integrate(record, energy, 0, .65)
        assert value['self_use_kwh'] == pytest.approx(1 / 31)


def test_phase_dc_protection_uses_own_conductor_quantity_and_fixed_fence_once():
    from guangzhu import personal
    record = demo('grazing')
    record.requirements.structured.phase1_kw = 30
    design = layout.generate_layout(record, {})
    shadows = dict(modules=[dict(id=m.id,total_loss_pct=0) for m in design.modules], summary=dict(avg_loss_pct=0))
    design = personal.prepare(record, design, offline=True, shadows=shadows)
    assert {m.phase for m in design.modules} == {1, 2}
    first = design.model_copy(deep=True)
    first.modules = [m.model_copy(update=dict(phase=None)) for m in design.modules if m.phase == 1]
    values = []
    for view in (first, design):
        electric = electrical.calculate(record, view, offline=True)
        quote = costs.itemized(record, len(view.modules) * .55, view, electric, structure.calculate(record, view))
        protection = sum(r['quantity'] for r in quote['items'] if r['key'] == 'dc_animal_protection')
        assert protection == pytest.approx(sum(r['length_m'] for r in electric['cables']['dc']))
        assert next(r['quantity'] for r in quote['items'] if r['key'] == 'animal_fence') == 200
        grid = next(r['point'] for r in electric['cables']['positions'] if r['label'] == 'GRID')
        assert grid == design.statistics['phasing']['grid_point']
        values.append(protection)
    assert 0 < values[0] < values[1]


def test_tool_schema_stays_compact_and_exposes_real_operations():
    from guangzhu.mcp_server import TOOLS, VALIDATORS
    size = len(json.dumps([tool.model_dump(mode='json', exclude_none=True) for tool in TOOLS],
                          ensure_ascii=False, separators=(',', ':')).encode())
    assert size <= 16384
    assert VALIDATORS['gz_edit_design'].is_valid(dict(project_id='x', version=1, reason='牧光加排距',
        ops=[dict(op='set_param', name='extra_row_gap_m', value=2)]))
