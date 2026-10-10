"""T23 independent counts, month totals, cashflows and backwards compatibility."""
import copy
import json
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest

from guangzhu import analysis, brief, economics, electrical, layout, mcp_actions, project as storage
from guangzhu.config import DATA_DIR
from guangzhu.models import Economics, GzError, validate_project
from test_electrical import design


def factory(name='changzhou-demo'):
    data = json.loads((DATA_DIR / f'demo/projects/{name}/project.json').read_text(encoding='utf-8'))
    data['site'].update(design_temp_min_c=-13.45, design_temp_max_c=42.06)
    data['equipment']['inverter_id'] = None
    return validate_project(data)


@pytest.mark.parametrize('count,expected', [(280, {26: 5, 25: 6}), (396, {25: 12, 24: 4}), (390, {26: 15})])
def test_balanced_lengths_and_separate_mppts(count, expected):
    result = electrical.calculate(factory(), design(count), offline=True)
    assert Counter(len(s['module_ids']) for s in result['strings']) == expected
    assert result['unused_modules'] == [] and result['checks']['E08']['status'] == 'pass'
    for row in result['mppt_currents']:
        lengths = {len(s['module_ids']) for s in result['strings'] if s['id'] in row['string_ids']}
        assert len(lengths) <= 1
    assert result['checks']['E03']['value'] / min(expected) == pytest.approx(result['vmp_hot_v'] / min(expected))
    assert result['checks']['E01']['value'] == result['voc_cold_v']


@pytest.mark.parametrize('identifier', ['sungrow-sg50cx-p2', 'huawei-sun2000-50ktl-m3'])
def test_short_string_has_reserved_mppt_without_unnecessary_second_inverter(identifier):
    p = factory()
    p.equipment.inverter_id = identifier
    result = electrical.calculate(p, design(114), offline=True)
    assert Counter(len(s['module_ids']) for s in result['strings']) == {23: 4, 22: 1}
    assert result['inverter_count'] == 1 and result['dc_ac_ratio'] == pytest.approx(1.254)
    assert result['checks']['E07']['status'] == 'pass' and result['checks']['E08']['status'] == 'pass'
    assert all(len({len(s['module_ids']) for s in result['strings'] if s['id'] in row['string_ids']}) <= 1
               for row in result['mppt_currents'])


def test_short_voltage_explicit_fallback_and_too_few_modules():
    p = factory()
    p.equipment.inverter_id = 'sungrow-sg100cx-p2'
    long = electrical.calculate(p, design(280, 26), offline=True)
    same = electrical.calculate(p, design(260, 26), offline=True)
    assert long['vmp_hot_v'] == pytest.approx(same['vmp_hot_v'] * 25 / 26)
    assert long['voc_cold_v'] == same['voc_cold_v'] and long['vmp_cold_v'] == same['vmp_cold_v']
    minimum = long['min_modules_per_string']
    fallback = electrical.calculate(p, design(minimum * 2 + 1, minimum), offline=True)
    assert len(fallback['unused_modules']) == 1 and fallback['checks']['E08']['status'] == 'fail'
    tiny = electrical.calculate(p, design(minimum - 1), offline=True)
    assert tiny['string_count'] == 0 and tiny['checks']['E08']['status'] == 'fail'


@pytest.mark.parametrize('name', ['l-shape', 'rotated'])
def test_demo_selection_has_good_ratio_and_each_device_uses_own_limits(name):
    p = factory(name)
    result = electrical.calculate(p, layout.generate_layout(p, {}), offline=True)
    assert 1 <= result['dc_ac_ratio'] <= 1.3 and result['checks']['E07']['status'] == 'pass'
    catalog = electrical.equipment_catalog()['inverters']
    for row in result['per_inverter']:
        spec = catalog[row['inverter_id']]
        assert row['dc_ac_ratio'] == pytest.approx(row['dc_kw'] / spec['rated_ac_kw'])
        for current in result['mppt_currents']:
            if current['inverter'] == row['inverter']:
                assert current['input_limit_a'] == spec['max_input_current_per_mppt_a']
                assert current['short_limit_a'] == spec['max_short_circuit_current_per_mppt_a']
    assert sum(r['count'] for r in result['inverters']) == result['inverter_count']


def test_new_catalog_has_small_and_large_official_models():
    rows = electrical.equipment_catalog()['inverters'].values()
    for manufacturer in ('Huawei', 'Sungrow'):
        brand = [r for r in rows if r['manufacturer'] == manufacturer]
        assert any(30 <= r['rated_ac_kw'] <= 60 for r in brand)
        assert any(r['rated_ac_kw'] > 110 for r in brand)
        for row in brand:
            assert len(row) == 29 and row['datasheet_url'].startswith('https://')
            assert all(row[k] for k in ('datasheet_version', 'datasheet_page', 'datasheet_date'))


@pytest.mark.parametrize('shifts', [1, 2, 3])
def test_each_beijing_month_totals_and_shift_hours(shifts):
    start = datetime(2023, 1, 1, tzinfo=timezone(timedelta(hours=8)))
    dates = [start + timedelta(hours=i) for i in range(8760)]
    timestamps = [d.astimezone(timezone.utc).isoformat() for d in dates]
    loads = economics.load_curve(12000, shifts, timestamps)
    for month in range(1, 13):
        assert sum(load for d, load in zip(dates, loads) if d.month == month) == pytest.approx(12000)
    by_date = dict(zip(dates, loads))
    monday = start + timedelta(days=1)
    production = by_date[monday + timedelta(hours=8)]
    assert by_date[monday + timedelta(hours=7)] == pytest.approx(production if shifts == 3 else production * .2)
    assert by_date[monday + timedelta(hours=17)] == pytest.approx(production * .2 if shifts == 1 else production)
    assert by_date[start + timedelta(hours=8)] == pytest.approx(production * .2)


def test_min_algorithm_and_manual_ratio_priority():
    assert economics.hourly_consumption([10, 0], [0, 10]) == 0
    assert economics.hourly_consumption([10, 20], [1000, 1000]) == 30
    p = factory()
    p.economics = Economics(monthly_kwh=12000, shifts=1)
    energy = dict(p50=30, low=25, high=35, hourly=dict(utc=['2023-01-02T00:00:00+00:00',
                                                       '2023-01-02T01:00:00+00:00'], kwh=[10, 20]))
    calculated = economics.calculate(p, 1, energy)
    assert calculated['params']['self_use_ratio'] == 1
    assert calculated['source']['self_use_ratio']['basis'] == 'hourly_load'
    p.economics.self_use_ratio = .4
    manual = economics.calculate(p, 1, energy)
    assert manual['params']['self_use_ratio'] == .4 and manual['self_use']['ratio'] == 1
    assert manual['self_use']['manual_override'] and manual['self_use']['reference_self_use_kwh'] == 30


@pytest.mark.parametrize('partial', [{}, {'monthly_kwh': 12000}, {'shifts': 2}])
def test_legacy_cashflows_and_economic_summary_bytes(partial):
    p = factory()
    energy = dict(p50=200000, low=180000, high=220000)
    before = economics.calculate(p, 200, energy)
    for key, value in partial.items():
        setattr(p.economics, key, value)
    after = economics.calculate(p, 200, energy)
    assert before['cashflows'] == after['cashflows']
    fields = ['capex_cny', 'payback_years', 'irr_pct', 'lcoe_cny_kwh', 'co2_t_per_year']
    assert analysis.serialized({k: before[k] for k in fields}) == analysis.serialized({k: after[k] for k in fields})
    old = p.economics.model_dump()
    assert ('monthly_kwh' in old) == ('monthly_kwh' in partial)
    assert ('shifts' in old) == ('shifts' in partial)


def test_brief_both_answers_only_and_no_export():
    spec = dict(id='t23-test', template='changzhou-demo', text='尽量多装')
    empty = brief.render_brief(spec)
    assert empty == brief.render_brief(spec | dict(facts={}))
    for answers in ({'monthly_kwh': 12000}, {'shifts': 1}):
        data = json.loads(brief.render_brief(spec | dict(facts=answers)).split('```json\n')[1].split('\n```')[0])
        assert data['economics'] == {}
    answers = dict(monthly_kwh=12000, shifts=2, export_allowed=False)
    data = json.loads(brief.render_brief(spec | dict(facts=answers)).split('```json\n')[1].split('\n```')[0])
    assert data['economics'] == dict(monthly_kwh=12000, shifts=2, price_export_cny_kwh=0)
    p = factory()
    p.economics.price_export_cny_kwh = 0
    result = economics.calculate(p, 100, dict(p50=100000, low=90000, high=110000))
    row = result['cashflows'][1]
    assert row['income_cny'] == pytest.approx(row['self_use_kwh'] * result['params']['price_self_cny_kwh'] + 126.4)
    assert result['self_use']['export_kwh'] == pytest.approx(20000)


def test_business_model_small_hand_example():
    p = factory()
    p.roof.outline = [(0, 0), (10, 0), (10, 10), (0, 10)]
    p.economics = Economics(capex_cny_per_w=1, om_cny_per_w_year=.01, self_use_ratio=.5,
                            price_self_cny_kwh=1, price_export_cny_kwh=.4, degradation_annual_pct=0)
    result = economics.calculate(p, 10, dict(p50=20000, low=18000, high=22000))
    own, emc, rent = result['business_models']
    assert own['owner_capex_cny'] == 10000 and own['owner_first_year_cny'] == pytest.approx(13843.2)
    assert own['owner_total_cny'] == pytest.approx(13843.2 * 25) and own['investor_payback_years'] == pytest.approx(10000 / 13843.2)
    assert emc['owner_capex_cny'] == rent['owner_capex_cny'] == 0
    assert emc['owner_first_year_cny'] == 1500 and emc['owner_total_cny'] == 37500
    assert rent['owner_first_year_cny'] == 500 and rent['owner_total_cny'] == 12500
    assert emc['investor_payback_years'] == pytest.approx(10000 / 12343.2)
    assert rent['investor_payback_years'] == pytest.approx(10000 / 13343.2)
    assert emc['investor_irr_pct'] == economics._irr([-10000] + [12343.2] * 25)


def test_new_project_load_avoids_template_ratio_but_preserves_manual(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    mcp_actions._new_project('t23-load', 'changzhou-demo', dict(monthly_kwh=12000, shifts=2))
    loaded = storage.load('t23-load')
    assert loaded.economics.monthly_kwh == 12000 and loaded.economics.self_use_ratio is None
    mcp_actions._new_project('t23-manual', 'changzhou-demo', dict(monthly_kwh=12000, shifts=2, self_use_ratio=.7))
    assert storage.load('t23-manual').economics.self_use_ratio == .7


def test_what_if_reuses_hourly_ratio_unless_overridden(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    p = storage.init(DATA_DIR / 'demo/projects/changzhou-demo')
    p.economics.monthly_kwh, p.economics.shifts, p.economics.self_use_ratio = 12000, 2, None
    storage.save(p)
    energy = dict(p50=200000, low=180000, high=220000, hourly=dict(utc=['2023-01-02T00:00:00+00:00'], kwh=[200000]))
    original = economics.calculate
    cash = original(p, 206.25, energy)
    monkeypatch.setattr(analysis, 'generation', lambda *args, **kw: (energy, {'omitted': {}}))
    monkeypatch.setattr(mcp_actions.shading, 'analyze_design', lambda *args, **kw: {'summary': {'avg_loss_pct': 0}})
    monkeypatch.setattr(mcp_actions.rules, 'evaluate', lambda *args: {'items': [], 'total': 0, 'passed': 0})
    monkeypatch.setattr(analysis, '_summary', lambda *args, **kw: {'economics': args[4]['params']})
    calls = []
    def capture(project, dc_kw, yield_kwh, **context):
        calculated = original(project, dc_kw, yield_kwh, **context)
        calls.append(calculated['params'])
        return calculated
    monkeypatch.setattr(economics, 'calculate', capture)
    mcp_actions._what_if(p.id, 3, {'price_change_pct': -10}, True)
    assert calls[-1]['self_use_ratio'] == cash['params']['self_use_ratio']
    assert calls[-1]['price_self_cny_kwh'] == cash['params']['price_self_cny_kwh'] * .9
    mcp_actions._what_if(p.id, 3, {'self_use_ratio': .6}, True)
    assert calls[-1]['self_use_ratio'] == .6


def test_cached_hourly_what_if_skips_physics_and_detects_inputs(tmp_path, monkeypatch):
    import hashlib
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    p = storage.init(DATA_DIR / 'demo/projects/changzhou-demo')
    p.economics.monthly_kwh, p.economics.shifts, p.economics.self_use_ratio = 12000, 2, None
    storage.save(p)
    energy = dict(p50=200000, low=180000, high=220000, hourly=dict(utc=['2023-01-02T00:00:00+00:00'], kwh=[200000]))
    d = storage.load_design(p.id, 3)
    electric = electrical.calculate(p, d, offline=True)
    from guangzhu import structure
    load = structure.calculate(p, d)
    cash = economics.calculate(p, electric['dc_kw'], energy, design=d, electric=electric, load=load)
    cash['analysis_metadata'] = dict(design_sha256=hashlib.sha256(storage._path(p.id, 'designs/v3.json').read_bytes()).hexdigest(),
                                    yield_kwh={key: value for key, value in energy.items() if key != 'hourly'})
    shadows = dict(summary={'avg_loss_pct': 0}, version=3,
                   metadata=dict(design_sha256=cash['analysis_metadata']['design_sha256']))
    cached = [dict(ok=True), shadows, electric, load, cash, dict(items=[])]
    folder = storage._path(p.id, 'analysis/v3')
    folder.mkdir(parents=True, exist_ok=True)
    for name, value in zip(('summary', 'shading', 'electrical', 'structure', 'economics', 'rules'), cached):
        (folder / (name + '.json')).write_text(json.dumps(value), encoding='utf-8')
    monkeypatch.setattr(mcp_actions.rules, 'evaluate', lambda *args: dict(items=[], total=0, passed=0))
    monkeypatch.setattr(analysis, '_summary', lambda *args, **kw: {'economics': args[4]['params']})
    def forbidden(*args, **kw):
        pytest.fail('cached what_if must reuse saved hourly physics')
    monkeypatch.setattr(mcp_actions.shading, 'analyze_design', forbidden)
    before = {x.name: x.read_bytes() for x in folder.iterdir()}
    result = mcp_actions._what_if(p.id, 3, {'price_change_pct': -10}, True)
    assert result['economics']['self_use_ratio'] == cash['params']['self_use_ratio']
    assert before == {x.name: x.read_bytes() for x in folder.iterdir()}
    p.economics.monthly_kwh = 24000
    storage.save(p)
    called = []
    def physics(*args, **kw):
        called.append(True)
        return dict(summary={'avg_loss_pct': 0})
    monkeypatch.setattr(mcp_actions.shading, 'analyze_design', physics)
    monkeypatch.setattr(analysis, 'generation', lambda *args, **kw: (energy, {'omitted': {}}))
    mcp_actions._what_if(p.id, 3, {}, True)
    assert called
    called.clear()
    p.economics.monthly_kwh = 12000
    storage.save(p)
    cash.pop('input_fingerprint')
    (folder / 'economics.json').write_text(json.dumps(cash), encoding='utf-8')
    mcp_actions._what_if(p.id, 3, {}, True)
    assert called, 'legacy cash has no proof that monthly demand or reference ratio was calculated'


def test_unavailable_payback_difference_is_labelled_not_zero():
    from guangzhu.report.figures import bars
    markup = str(bars([('未回本', None), ('不变', 0)], '回本变化（年）'))
    assert '无可算差值（基准或情景未回本）' in markup
    assert markup.count('<rect') == 1


@pytest.mark.parametrize('monthly,manual', [(None, None), (12000, None), (12000, .7)])
def test_real_offline_hourly_stays_in_memory_and_compact_exports(tmp_path, monkeypatch, monthly, manual):
    import requests
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    monkeypatch.setattr(requests.Session, 'request', lambda *a, **k: pytest.fail('T23 actual b chain must remain offline'))
    p = storage.init(DATA_DIR / 'demo/projects/changzhou-demo')
    p.roof.inverter_positions = [(30, 18)]
    p.economics.monthly_kwh, p.economics.shifts, p.economics.self_use_ratio = monthly, 2, manual
    p.requirements.structured.ballast_only = True  # an owner who forbids drilling keeps the overloading wind ballast
    storage.save(p)
    rejected = analysis.analyze(p.id, 3, offline=True)
    assert p.roof.load_capacity_kn_m2 == .5
    assert any(row['id'] == 'L01' and row['level'] == 'hard' for row in rejected['rules']['failed'])
    with pytest.raises(GzError) as blocked:
        mcp_actions._export(p.id, 3, offline=True)
    assert blocked.value.error_code == 'EXPORT_BLOCKED' and 'L01' in blocked.value.message_zh
    # Anchoring allowed again: the racks that ballast would overload are anchored, so the export contract reaches its positive path.
    p.requirements.structured.ballast_only = None
    storage.save(p)
    original, memory = analysis.generation, []
    def capture(*args, **kwargs):
        values = original(*args, **kwargs)
        memory.append(values)
        return values
    monkeypatch.setattr(analysis, 'generation', capture)
    result = analysis.analyze(p.id, 3, offline=True)
    current = json.loads(storage._path(p.id, 'analysis/v3/electrical.json').read_text(encoding='utf-8'))
    assert all(current['checks'][code]['status'] == 'pass' for code in ['E10', 'E11'])
    cash = json.loads(storage._path(p.id, 'analysis/v3/economics.json').read_text(encoding='utf-8'))
    energy, generated = memory[-1]
    assert len(generated['results']['b']['hourly']['utc']) == 8760
    if monthly is not None:
        assert len(energy['hourly']['utc']) == len(energy['hourly']['kwh']) == 8760
        assert sum(energy['hourly']['kwh']) == pytest.approx(energy['p50'])
        calculated = economics.hourly_self_use(monthly, 2, energy['hourly'])
        assert cash['self_use']['ratio'] == pytest.approx(calculated['ratio'])
        assert cash['params']['self_use_ratio'] == pytest.approx(calculated['ratio'] if manual is None else manual)
        assert cash['cashflows'][1]['self_use_kwh'] == pytest.approx(energy['p50'] * cash['params']['self_use_ratio'])
    assert len(analysis.serialized(result).encode('utf-8')) <= 2048
    changes = dict(price_change_pct=-10, capex_change_pct=5)
    with monkeypatch.context() as cached:
        cached.setattr(analysis, 'generation', lambda *a, **k: pytest.fail('cached scenario must not regenerate hourly data'))
        scenario = mcp_actions._what_if(p.id, 3, changes, True)
    economics_path = storage._path(p.id, 'analysis/v3/economics.json')
    assert economics_path.stat().st_size <= 320 * 1024
    assert len(cash["tariff"]["graph"]) <= 288
    assert len({(r["month"], r["hour"]) for r in cash["tariff"]["graph"]}) == len(cash["tariff"]["graph"])
    for model in cash["business_models"]:
        assert len(model["accounts"]) == 25
        assert len(model["pretax"]["cashflows"]) == len(model["posttax"]["cashflows"]) == 26
    def compact(value):
        if isinstance(value, list):
            assert len(value) <= 288
            for entry in value:
                compact(entry)
        elif isinstance(value, dict):
            assert 'utc' not in value and 'date' not in value
            for entry in value.values():
                compact(entry)
    compact(cash)
    economics_path.unlink()
    assert mcp_actions._what_if(p.id, 3, changes, True) == scenario
    mcp_actions._export(p.id, 3, offline=True)
    def no_hourly(value):
        if isinstance(value, dict):
            assert 'hourly' not in value
            for item in value.values():
                no_hourly(item)
        elif isinstance(value, list):
            for item in value:
                no_hourly(item)
    for path in storage._path(p.id, '').rglob('*.json'):
        no_hourly(json.loads(path.read_text(encoding='utf-8')))


@pytest.mark.parametrize('summary', [None, dict(yield_kwh=dict(p50=150000))])
def test_single_shift_sitecheck_states_six_day_production_and_background_load(summary):
    from guangzhu.sitecheck import rows
    result = rows(dict(monthly_kwh=12000, shifts=1), summary)
    text = next(row['text'] for row in result if row['item'] == '用电量')
    assert '周一至周六8–17时' in text and '20%示意负荷' in text
    assert '周末不用电' not in text
