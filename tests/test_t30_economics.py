"""Independent hand values and actual engineering integration; no model/network calls."""
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from guangzhu import costs, economics, finance, tariff, layout, electrical, structure, park
from guangzhu.config import ROOT
from guangzhu.models import Economics, Project, SiteFacts
from guangzhu.economic_analysis import calculate

FIXTURES = Path(__file__).parent / 'fixtures/T30'
REFERENCE = json.loads((FIXTURES / 'reference.json').read_text(encoding='utf-8'))
BUSINESS = json.loads((FIXTURES / 'business.json').read_text(encoding='utf-8'))


@pytest.fixture
def project():
    p = Project.model_validate_json((ROOT / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    p.economics = Economics()
    return p


def day(date, values=None):
    start = datetime.fromisoformat(date).replace(tzinfo=timezone(timedelta(hours=8)))
    generation = values or [1] * 24
    return dict(p50=sum(generation), low=sum(generation), high=sum(generation),
                hourly=dict(utc=[(start + timedelta(hours=h)).astimezone(timezone.utc).isoformat() for h in range(24)], kwh=generation))


@pytest.mark.parametrize('index,date,kind,kva', [(0, '2023-03-15', 'single100', 100),
                                               (1, '2023-07-15', 'two_part', 315), (2, '2023-01-23', 'two_part', 315)])
def test_tou_every_hour_matches_official_hand_vector(project, index, date, kind, kva):
    project.economics.tariff_class = kind
    project.facts = SiteFacts(transformer_kva=kva)
    project.economics.self_use_ratio = 1
    result = tariff.integrate(project, day(date), 1, .65)
    oracle = REFERENCE['tou_days'][index]
    assert [r['price_cny_kwh'] for r in result['graph']] == pytest.approx(oracle['one_kwh_each_hour_prices'])
    assert result['revenue_cny'] == pytest.approx(oracle['daily_cny'])
    assert result['weighted_price_cny_kwh'] == pytest.approx(oracle['weighted_cny_per_kwh'])
    assert sum(r['self_use_kwh'] for r in result['bands'].values()) == 24


@pytest.mark.parametrize('kva,expected,eligible', [(None, 'single100', False), (99, 'single_small', False),
                                                (100, 'single100', False), (314, 'single100', False), (315, 'two_part', True)])
def test_category_boundaries_and_override(project, kva, expected, eligible):
    project.facts = SiteFacts(transformer_kva=kva)
    assert tariff.category(project) == (expected, eligible, kva)
    project.economics.tariff_class = 'single100'
    assert tariff.category(project) == ('single100', eligible, kva)


def test_manual_weighted_load_reference_and_holiday_boundaries(project):
    generation = [0] * 24
    generation[10], generation[15] = 1, 3
    project.economics = Economics(self_use_ratio=.5, monthly_kwh=1, shifts=1)
    result = tariff.integrate(project, day('2023-03-15', generation), .5, .65)
    assert result['weighted_price_cny_kwh'] == pytest.approx(.885625)
    assert result['revenue_cny'] == pytest.approx(1.77125)
    assert result['self_use_kwh'] == 2 and result['reference_self_use_kwh'] < 2
    assert result['load_mode'] == '手填比例均摊到各小时'
    for date, expected in [('2023-09-29', 'deep'), ('2023-10-06', 'deep'), ('2023-10-07', 'valley')]:
        assert tariff.band(datetime.fromisoformat(date).replace(hour=10), 0, True) == expected


@pytest.mark.parametrize('mode', ['self', 'emc', 'rent'])
def test_all_years_tax_replacement_and_business_oracles(mode):
    result = finance.ledger(11300, 11300, 1000, 2260, 100, mode=mode, rent=300, replacement=1130)
    for actual, expected in zip(result['accounts'], BUSINESS['modes']['rental' if mode == 'rent' else mode], strict=True):
        for key, value in expected.items():
            assert actual[key] == pytest.approx(value), (mode, actual['year'], key)
    assert result['accounts'][12]['replacement'] == 1130
    assert result['accounts'][11]['replacement'] == result['accounts'][13]['replacement'] == 0


def test_interest_deduction_and_zero_loan():
    result = finance.ledger(11300, 11300, 1000, 2260, 100, replacement=1130, loan_ratio=.5, loan_rate=.05)
    for actual, expected in zip(result['accounts'], BUSINESS['debt']['rows'], strict=True):
        for key, value in expected.items():
            assert actual[key] == pytest.approx(value), (actual['year'], key)
    zero = finance.debt_schedule(10000, .5, 0, 5, 25)
    assert all(r['principal'] == 1000 and r['interest'] == 0 for r in zero[:5])
    assert zero[4]['closing'] == 0 and zero[5]['payment'] == 0
    assert 'loan' not in finance.ledger(10000, 0, 2000, 0, 0)


@pytest.mark.parametrize('ac,level', [(399.9, '380 V'), (400, '380 V'), (400.1, '10 kV'), (6000, '10 kV'),
                                     (6000.1, '更高电压，需当地电网核定')])
def test_grid_voltage(ac, level):
    assert costs.voltage(ac) == level


def test_cost_quantities_manual_override_refurbishment_and_catalog_noop(project, monkeypatch):
    design = layout.generate_layout(project, {})
    electric = electrical.calculate(project, design, offline=True)
    load = structure.calculate(project, design)
    before = costs.itemized(project, electric['dc_kw'], design, electric, load)
    catalog = costs.catalog()
    hardware = 0
    total = 0
    for item in before['items']:
        expected = item['quantity'] * item['unit_price_cny']
        assert item['subtotal_cny'] == pytest.approx(expected)
        total += expected
        hardware += expected if item['hardware'] else 0
    assert before['capex_cny'] == pytest.approx(total)
    assert before['hardware_cny'] == pytest.approx(hardware)
    original = copy.deepcopy(catalog)
    catalog['future_unused'] = dict(value=9999)
    monkeypatch.setattr(costs, 'catalog', lambda: catalog)
    assert costs.itemized(project, electric['dc_kw'], design, electric, load) == before
    project.facts = SiteFacts(roof_age_years=10)
    renewed = costs.itemized(project, electric['dc_kw'], design, electric, load)
    assert renewed['capex_cny'] - total == pytest.approx(60 * 60 * 36)
    project.economics.capex_cny_per_w = 3
    overridden = costs.itemized(project, electric['dc_kw'], design, electric, load)
    assert sum(r['subtotal_cny'] for r in overridden['items']) == pytest.approx(electric['dc_kw'] * 3000)
    assert overridden['manual_override']


@pytest.mark.parametrize('blocked_price', [0, .391])
def test_zero_price_export_is_not_curtailment_and_defaults(project, blocked_price):
    project.economics = Economics(price_export_cny_kwh=0, self_use_ratio=.8)
    energy = day('2023-03-15', [100000 / 24] * 24)
    cash = calculate(project, 100, energy, sensitivity=False)
    assert cash['self_use']['export_kwh'] == pytest.approx(20000)
    assert cash['certificates']['tradable_estimate'] == pytest.approx(20)
    assert cash['income_breakdown']['green_cny'] == pytest.approx(126.4)
    assert cash['certificates']['issued_estimate'] == pytest.approx(100)
    assert 'loan' not in cash and cash['u04_basis'] == '税前'
    assert cash['subsidy']['amount_cny'] == 0
    project.requirements.structured.export_allowed = False
    project.economics.price_export_cny_kwh = blocked_price
    blocked = calculate(project, 100, energy, sensitivity=False)
    assert blocked['self_use']['curtailed_kwh'] == pytest.approx(20000)
    assert blocked['certificates']['tradable_estimate'] == 0
    assert blocked['certificates']['issued_estimate'] == pytest.approx(80)
    assert blocked['income_breakdown']['export_cny'] == blocked['income_breakdown']['green_cny'] == 0


def test_itemized_independent_hand_amounts_and_empty_generation(project):
    design = layout.generate_layout(project, {})
    design.modules = design.modules[:20]
    electric = dict(per_inverter=[dict(inverter_id='sungrow-sg50cx-p2')],
                    cables=dict(summary=[dict(kind='dc', section_mm2=4, length_m=100),
                                         dict(kind='ac', section_mm2=25, length_m=50)]))
    # Price arithmetic fixture supplies its own 600kg engineering quantity; T31 separately tests live wind quantities.
    result = costs.itemized(project, 11, design, electric, dict(ballast_mass_kg=600))
    expected = dict(module=9350, inverter=10000, ballast_tilt=2000, ballast=300, dc_cable=480,
                    ac_cable=5000, grid_lv=12000, monitor=8000, installation=3850, design=5000, unlisted=7700, refurbishment=0)
    assert {r['key']: r['subtotal_cny'] for r in result['items']} == pytest.approx(expected)
    assert result['capex_cny'] == pytest.approx(63680)  # 0.70 yuan/W of costs not priced one by one, calibrated to the CPIA average
    assert result['replacement_cny'] == 10000
    empty = calculate(project, 0, dict(p50=0, low=0, high=0, hourly=dict(utc=[], kwh=[])), sensitivity=False)
    assert empty['capex_cny'] == 0 and empty['payback_years'] is None
    assert empty['tariff']['weighted_price_cny_kwh'] == 0 and empty['certificates']['issued_estimate'] == 0


def test_unused_catalog_append_keeps_entire_business_output_identical(project, monkeypatch):
    energy = day('2023-03-15')
    before = calculate(project, 100, energy, sensitivity=False)
    catalog = costs.catalog()
    catalog['unselected_future_support'] = dict(value=9999, 来源标题='未选择的新支架')
    monkeypatch.setattr(costs, 'catalog', lambda: catalog)
    assert calculate(project, 100, energy, sensitivity=False) == before


@pytest.mark.parametrize('field', ['monthly_kwh', 'shifts', 'self_use_ratio', 'tariff_class', 'site', 'transformer', 'source'])
def test_energy_cache_keeps_load_location_class_and_source_proof(project, monkeypatch, field):
    from guangzhu import economics
    from guangzhu.economic_analysis import energy_key
    before = energy_key(project)
    if field == 'site':
        project.site.lat += .1
    elif field == 'transformer':
        project.requirements.structured.transformer_kva = 315
    elif field == 'source':
        rows = economics.load_assumptions()
        rows['design_system_loss_pct']['备注'] += '来源修订'
        monkeypatch.setattr(economics, 'load_assumptions', lambda: rows)
    else:
        values = dict(monthly_kwh=12345, shifts=3, self_use_ratio=.123, tariff_class='two_part')
        setattr(project.economics, field, values[field])
    assert energy_key(project) != before


def test_mechanism_expiration_subsidy_once_posttax_choice_and_park(project):
    project.economics = Economics(self_use_ratio=.8, mechanism_share=.5, mechanism_price=.3, mechanism_years=10,
                                  public_subsidy_confirmed=True, subsidy_year=2, posttax_payback=True, loan_ratio=.5)
    cash = calculate(project, 100, day('2023-03-15', [100000 / 24] * 24), sensitivity=False)
    assert cash['u04_payback_years'] == cash['posttax']['payback_years']
    assert cash['subsidy']['amount_cny'] == 30000
    assert cash['accounts'][1]['other'] - cash['accounts'][0]['other'] > 29000
    assert cash['accounts'][10]['other'] > cash['accounts'][9]['other']
    first_sales = 20000 * (.5 * .3 + .5 * .391)
    assert cash['accounts'][0]['sales'] == pytest.approx(first_sales)
    assert cash['accounts'][0]['output_vat'] == pytest.approx(first_sales * 13 / 113)
    base = dict(dc_kw=1, annual_kwh=2, capex_cny=100, co2_t=3, net_cny=[-100, 60, 60])
    total = park.total([dict(base, posttax_net_cny=[-100, 40, 80]), dict(base, posttax_net_cny=[-100, 60, 60])])
    assert total['posttax']['payback_years'] == pytest.approx(1 + 100 / 140)
    mixed = park.total([dict(base, posttax_net_cny=[-100, 40, 80]), base])
    assert 'posttax' not in mixed and '缺' in mixed['posttax_note']


def test_original_reference_credit_exhaustion_and_100000_debt():
    actual = finance.ledger(11300, 11300, 1000, 2260, 100)['accounts']
    keys = dict(output_vat='output_vat', credit_closing='credit_close', vat_paid='paid_vat', depreciation='depreciation',
                taxable_profit='taxable', cit='cit', pretax_cash='pretax', posttax_cash='posttax')
    for row, expected in zip(actual, REFERENCE['taxes']['rows']):
        for key, column in keys.items():
            assert row[column] == pytest.approx(expected[key])
    actual = finance.debt_schedule(100000, .5, .05, 20, 25)
    for row, expected in zip(actual, REFERENCE['debt']['rows']):
        for key, value in expected.items():
            assert row[key] == pytest.approx(value, abs=1e-8)
