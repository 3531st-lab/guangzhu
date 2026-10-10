"""T28 owner constraints: independent values, real electrical choices, immutable phases."""
import hashlib
import json
import math
from itertools import product

import pytest
from pydantic import ValidationError
from guangzhu import analysis, brief, economics, electrical, layout, mcp_actions, personal, project as storage, rules, shading, structure
from guangzhu.config import ROOT
from guangzhu.models import Equipment, GzError, Module, RemovedModule, StructuredRequirements
from test_electrical import design
from test_t23 import factory


@pytest.fixture
def owner(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    p = storage.init(ROOT / 'data/demo/projects/changzhou-demo', 't28-test')
    p.site.design_temp_min_c = -13.45
    p.site.design_temp_max_c = 42.06
    p.equipment.inverter_id = None
    storage.save(p)
    return p


@pytest.mark.parametrize('key,bad,good', [
    ('export_allowed', 'false', False), ('curtail_pct_max', 101, 0), ('transformer_kva', 0, 800),
    ('transformer_share', 1.01, .7), ('max_height_m', -1, 0), ('phase1_kw', 0, 200), ('phase1_budget_cny', -1, 500000)])
def test_optional_fields_validate_and_omit_only_new_nulls(key, bad, good):
    empty = StructuredRequirements().model_dump_json()
    assert StructuredRequirements(**{key: None}).model_dump_json() == empty
    assert '"notes":null' in empty and key not in json.loads(empty)
    assert StructuredRequirements(**{key: good}).model_dump()[key] == good
    with pytest.raises(ValidationError):
        StructuredRequirements(**{key: bad})
    if key != 'export_allowed':
        with pytest.raises(ValidationError):
            StructuredRequirements(**{key: float('nan')})


def test_phase_and_equipment_serialization_and_validation():
    with pytest.raises(ValidationError):
        StructuredRequirements(phase1_kw=5, phase1_budget_cny=5000)
    panel = design(1).modules[0]
    assert 'phase' not in panel.model_dump()
    assert 'phase' not in RemovedModule(**panel.model_dump(), reason='test').model_dump()
    with pytest.raises(ValidationError):
        Module(**panel.model_dump(), phase=True)
    assert Equipment(module_id='x').model_dump() == dict(module_id='x', inverter_id=None, racking='ballast_tilt')
    for selected in [dict(inverter_brand='other'), dict(inverter_id='missing'),
                     dict(inverter_brand='Huawei', inverter_id='sungrow-sg50cx-p2')]:
        with pytest.raises(ValueError):
            brief.check_equipment(selected)


def test_intake_defaults_and_brand_only_project(owner):
    spec = brief.BriefSpec(template='changzhou-demo', id='t28-brief', text='只自用',
                          facts=dict(export_allowed=False, transformer_kva=800), structured=dict(transformer_kva=600),
                          equipment=dict(inverter_brand='Huawei'))
    parsed = json.loads(brief.render_brief(spec).split('```json\n')[1].split('\n```')[0])
    assert parsed['requirements']['structured']['export_allowed'] is False
    assert parsed['requirements']['structured']['transformer_kva'] == 600
    assert parsed['economics']['price_export_cny_kwh'] == 0
    mcp_actions._new_project('t28-brand', 'changzhou-demo', equipment=spec.equipment)
    assert storage.load('t28-brand').equipment.inverter_brand == 'Huawei'


def test_curtailment_first_integer_and_manual_immunity(monkeypatch):
    p = factory()
    p.requirements.structured = StructuredRequirements(export_allowed=False, curtail_pct_max=10)
    p.economics.monthly_kwh, p.economics.shifts, p.economics.self_use_ratio = 1, 1, .99
    monkeypatch.setattr(economics, 'load_curve', lambda *args: [4, 2])
    energy = dict(p50=16, low=16, high=16, hourly=dict(utc=['2023-01-02T00:00:00+00:00', '2023-01-02T01:00:00+00:00'], kwh=[8, 8]))
    cap = personal.curtailment(p, energy, 10)
    assert cap['pct'] == 62.5 and cap['worst_count'] == 7
    def percent(count):
        produced = [8 * count / 10] * 2
        return 100 * (sum(produced) - sum(min(a, b) for a, b in zip(produced, [4, 2]))) / sum(produced)
    assert percent(3) <= 10 and percent(4) > 10
    cash = economics.calculate(p, 5.5, energy)
    assert cash['params']['self_use_ratio'] == pytest.approx(.375)
    assert cash['self_use']['export_kwh'] == 0 and not cash['self_use']['manual_override']
    assert all(r['export_kwh'] == 0 for r in cash['cashflows'])
    p.economics.shifts = None
    assert personal.curtailment(p, energy, 10) == dict(note='填了月用电量和班次，才能按用电封顶')


def test_height_hand_ceiling_zero_and_conflict(owner, monkeypatch):
    monkeypatch.setattr(layout, '_catalog', lambda *args: (dict(length_m=2, width_m=1), .02, .2))
    owner.requirements.structured.max_height_m = 1.2
    assert personal.tilt_bounds(owner, design(1).params)[1] == pytest.approx(30)
    owner.requirements.structured.max_height_m = .2
    assert personal.tilt_bounds(owner, design(1).params)[1] == 0
    owner.requirements.structured.max_height_m = .1
    storage.save(owner)
    result = mcp_actions._set_requirements(owner.id, '限高太低', dict(max_height_m=.1), offline=True)
    assert '低于' in result['contradictions'][0]


def test_real_layout_height_and_metal(owner):
    owner.requirements.structured.max_height_m = .4
    for orientation in ('portrait', 'landscape'):
        d = layout.generate_layout(owner, dict(orientation=orientation, rows_per_rack=2, fill_landscape=True))
        assert d.params.rows_per_rack == 1
        assert max(p[2] for m in d.modules for p in m.corners) <= .401
    owner.requirements.structured.max_height_m = .2
    with pytest.raises(GzError):
        layout.generate_layout(owner, dict(layout='ew'))
    metal = factory('metal-demo-n')
    old = layout.generate_layout(metal, {})
    metal.requirements.structured.max_height_m = .1
    new = layout.generate_layout(metal, {})
    assert [m.corners for m in new.modules] == [m.corners for m in old.modules]


def test_phase_order_rounding_and_joint_selection(owner, monkeypatch):
    d = design(260)
    losses = {m.id: i // 20 for i, m in enumerate(reversed(d.modules))}
    fake = dict(version=1, modules=[dict(id=m.id, total_loss_pct=losses[m.id]) for m in d.modules])
    monkeypatch.setattr(shading, 'analyze_design', lambda *args, **kwargs: fake)
    owner.requirements.structured = StructuredRequirements(phase1_kw=35, transformer_kva=150, transformer_share=1)
    owner.equipment.inverter_brand = 'Sungrow'
    personal.prepare(owner, d, offline=True)
    grid = d.statistics['phasing']['grid_point']
    ordered = sorted(d.modules, key=lambda m: (losses[m.id], math.dist(m.center[:2], grid), m.id))
    count = sum(m.phase == 1 for m in ordered)
    assert [m.phase for m in ordered] == [1] * count + [2] * (len(ordered) - count)
    assert count * .55 >= 35
    e = electrical.calculate(owner, d, offline=True)
    catalog = electrical.equipment_catalog()['inverters']
    ac = sum(catalog[u['inverter_id']]['rated_ac_kw'] for u in e['per_inverter'])
    choices = [electrical.calculate(owner, d.model_copy(update=dict(modules=[m for m in d.modules if m.phase == phase])),
                                   offline=True, options=True) for phase in (1, 2)]
    assert any(sum(catalog[u['inverter_id']]['rated_ac_kw'] for r in rows for u in r['per_inverter']) <= 150 for rows in product(*choices))
    assert ac <= 150
    for string in e['strings']:
        assert {m.phase for m in d.modules if m.id in string['module_ids']} == {string['phase']}
    for unit in e['per_inverter']:
        assert {s['phase'] for s in e['strings'] if s['inverter'] == unit['inverter']} == {unit['phase']}
        assert unit['inverter_id'].startswith('sungrow')
    assert {s['id'] for s in e['strings']} == {r['id'] for r in e['cables']['dc']}
    owner.requirements.structured.transformer_kva = 130
    impossible = electrical.calculate(owner, d, offline=True)
    assert all(sum(catalog[u['inverter_id']]['rated_ac_kw'] for r in rows for u in r['per_inverter']) > 130 for rows in product(*choices))
    assert sum(catalog[u['inverter_id']]['rated_ac_kw'] for u in impossible['per_inverter']) > 130
    assert '无可行组合' in impossible['selection_reason']
    cost = economics.resolve_parameters(owner)[0]['capex_cny_per_w'] * 550
    owner.requirements.structured = StructuredRequirements(phase1_budget_cny=65 * cost)
    personal.prepare(owner, d, offline=True)
    assert 0 < sum(m.phase == 1 for m in d.modules) < len(d.modules)
    assert d.statistics['phasing']['achieved_cny'] <= owner.requirements.structured.phase1_budget_cny
    owner.requirements.structured.phase1_budget_cny = cost
    personal.prepare(owner, d, offline=True)
    assert not any(m.phase == 1 for m in d.modules)


@pytest.fixture
def phase_context(owner):
    owner.requirements.structured = StructuredRequirements(phase1_kw=30, max_height_m=1.2)
    owner.economics.monthly_kwh, owner.economics.shifts = 10000, 1
    owner.roof.inverter_positions = [(10, 15), (40, 15)]
    storage.save(owner)
    mcp_actions._generate_layout(owner.id, {}, offline=True)
    d = storage.load_design(owner.id, 1)
    before = storage._path(owner.id, 'designs/v1.json').read_bytes()
    summary = analysis.analyze(owner.id, 1, offline=True)
    assert storage._path(owner.id, 'designs/v1.json').read_bytes() == before
    def read(name):
        return json.loads(storage._path(owner.id, f'analysis/v1/{name}.json').read_text(encoding='utf-8'))
    context = dict(project=owner.model_dump(mode='json'), design=d.model_dump(mode='json'), summary=summary, version=1,
                   compare=None, facts={}, review=None, approval=None, sessions=[], requirements=[], verification={}, sources={},
                   versions=[], relaxations=[], history=[], run={}, generated_at='2026-10-06T00:00:00+08:00',
                   run_id='T28-offline-no-AI', project_id=owner.id, crosscheck=None)
    context.update({name: read(name) for name in ['electrical', 'shading', 'structure', 'rules', 'economics']})
    return context


def test_phase_economics_outputs_and_xlsx(phase_context, tmp_path):
    from openpyxl import load_workbook
    from guangzhu.report.deliverables import write_deliverables
    from guangzhu.report.view import render
    c = phase_context
    cash = c['economics']
    first, total, increment = cash['phases']
    assert increment['profit_cny'] == pytest.approx(total['profit_cny'] - first['profit_cny'])
    assert total['capex_cny'] == cash['capex_cny'] and len(cash['business_models']) == 3
    def no_vectors(value):
        if isinstance(value, dict):
            return 'hourly' not in value and all(no_vectors(v) for v in value.values())
        return all(no_vectors(v) for v in value) if isinstance(value, list) else True
    assert all(no_vectors(json.loads(p.read_text(encoding='utf-8')))
               for p in storage._path(c['project_id'], 'analysis/v1').glob('*.json'))
    write_deliverables(c['project_id'], 1, tmp_path)
    book = load_workbook(tmp_path / 'bom-v1.xlsx')
    rows = list(book['分期材料'].values)[1:]
    assert sum(r[3] for r in rows if r[1] == '组件') == len(c['design']['modules'])
    assert sum(r[3] for r in rows if r[1] == '逆变器') == c['electrical']['inverter_count']
    html = render(c)
    assert '分期建设' in html and '一期绿色' in html and '最高点' in html
    paths = list(storage._path(c['project_id']).rglob('*.json'))
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    changed = mcp_actions._what_if(c['project_id'], 1, dict(capex_change_pct=10), True)
    assert changed['what_if']['saved'] is False
    assert before == {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def test_shared_load_increment_is_total_minus_first(monkeypatch):
    p = factory()
    p.requirements.structured.phase1_kw = 1.1
    p.economics.monthly_kwh, p.economics.shifts, p.economics.self_use_ratio = 1, 1, .99
    monkeypatch.setattr(economics, 'load_curve', lambda *args: [4, 2])
    def energy(values):
        return dict(p50=sum(values), low=sum(values), high=sum(values), hourly=dict(utc=['2023-01-02T00:00:00+00:00', '2023-01-02T01:00:00+00:00'], kwh=values))
    d = design(8)
    for i, m in enumerate(d.modules):
        m.phase = 1 if i < 2 else 2
    monkeypatch.setattr(shading, 'analyze_design', lambda *args, **kwargs: {})
    monkeypatch.setattr(analysis, 'generation', lambda *args, **kwargs: (energy([2, 2]), {}))
    for budget in (False, True):
        p.requirements.structured = StructuredRequirements(**({'phase1_budget_cny':10000} if budget else {'phase1_kw':1.1}))
        cash = economics.calculate(p, 4.4, energy([8, 8]))
        personal.phase_cash(p, d, {}, cash, offline=True)
        first, increment = cash['phase_cashflows']['first'], cash['phase_cashflows']['increment']
        assert (first[1]['self_use_kwh'], cash['cashflows'][1]['self_use_kwh'], increment[1]['self_use_kwh']) == (4, 6, 2)
        assert cash['self_use']['export_kwh'] == 10 and cash['self_use']['curtailed_kwh'] == 0
        assert cash['source']['self_use_ratio']['basis'] == 'hourly_load'
        for a, b, c in zip(first, cash['cashflows'], increment):
            for key in b.keys() - {'year'}:
                assert c[key] == pytest.approx(b[key] - a[key])


def test_real_u05_delete_reanalyze_and_setter_consistency(owner, monkeypatch):
    owner.requirements.structured = StructuredRequirements(export_allowed=False, curtail_pct_max=10)
    owner.economics.monthly_kwh, owner.economics.shifts = 10000, 1
    storage.save(owner)
    mcp_actions._generate_layout(owner.id, {}, offline=True)
    def analyze(version):
        analysis.analyze(owner.id, version, offline=True)
        return json.loads(storage._path(owner.id, f'analysis/v{version}/rules.json').read_text(encoding='utf-8'))
    def u05(result):
        return next(r for r in result['items'] if r['id'] == 'U05')
    failed = u05(analyze(1))
    assert failed['status'] == 'fail' and failed['suggestion']['where']['worst_count'] > 0
    edited = storage.edit_design(owner.id, 1, [failed['suggestion']], 'U05验收', 'rule', offline=True)
    for _ in range(3):
        check = u05(analyze(edited['version']))
        if check['status'] == 'pass':
            break
        edited = storage.edit_design(owner.id, edited['version'], [check['suggestion']], 'U05重新核对', 'rule', offline=True)
    assert check['status'] == 'pass'
    result = mcp_actions._set_requirements(owner.id, '只自用但至少200kW',
        dict(export_allowed=False, capacity_kw_min=200), offline=True)
    assert any('同比例估算' in row for row in result['contradictions'])
    def missing(*args, **kwargs):
        raise OSError('cached weather unavailable')
    monkeypatch.setattr(analysis, 'generation', missing)
    result = mcp_actions._set_requirements(owner.id, '只自用但至少200kW',
        dict(export_allowed=False, capacity_kw_min=200), offline=True)
    assert not any('同比例估算' in row for row in result['contradictions'])
    assert any('一致性未核实' in row for row in result['missing'])


def test_transformer_brand_limit_delete_and_same_site_limit(owner):
    from guangzhu import sitecheck
    owner.requirements.structured = StructuredRequirements(transformer_kva=100, transformer_share=1)
    owner.equipment.inverter_brand = 'Huawei'
    storage.save(owner)
    mcp_actions._generate_layout(owner.id, {}, offline=True)
    versions = []
    version = 1
    for _ in range(5):
        summary = analysis.analyze(owner.id, version, offline=True)
        checked = json.loads(storage._path(owner.id, f'analysis/v{version}/rules.json').read_text(encoding='utf-8'))
        row = next(r for r in checked['items'] if r['id'] == 'U06')
        versions.append((version, row['value'], row['status']))
        assert summary['electrical']['rated_ac_kw'] == row['value']
        if row['status'] == 'pass':
            break
        version = storage.edit_design(owner.id, version, [row['suggestion']], 'U06验收', 'rule', offline=True)['version']
    assert versions[0][2] == 'fail' and versions[-1][2] == 'pass'
    electric = json.loads(storage._path(owner.id, f'analysis/v{version}/electrical.json').read_text(encoding='utf-8'))
    assert all(u['inverter_id'].startswith('huawei') for u in electric['per_inverter'])
    site = sitecheck.rows({}, summary, requirements=owner.requirements.structured.model_dump())
    transformer = next(r for r in site if r['item'] == '变压器')
    assert transformer['status'] == 'ok' and '=100kW' in transformer['text']


def test_phase_edits_resave_labels_and_preserve_prior_version(phase_context):
    identifier = phase_context['project_id']
    old = storage._path(identifier, 'designs/v1.json').read_bytes()
    d = storage.load_design(identifier, 1)
    victim = d.modules[0]
    edit = storage.edit_design(identifier, 1, [dict(op='remove_modules', module_ids=[victim.id])], '分期删板', 'rule', offline=True)
    new = storage.load_design(identifier, edit['version'])
    assert all(m.phase in (1, 2) for m in new.modules)
    assert new.removed_modules[-1].phase == victim.phase
    assert storage._path(identifier, 'designs/v1.json').read_bytes() == old
    changed = storage.edit_design(identifier, new.version, [dict(op='set_param', name='tilt_deg', value=10)],
                                  '分期重新排板', 'rule', offline=True)
    rebuilt = storage.load_design(identifier, changed['version'])
    assert not rebuilt.removed_modules and all(m.phase in (1, 2) for m in rebuilt.modules)


def test_height_compare_and_ew_half_row(owner):
    owner.roof.outline = [(0, 0), (20, 0), (20, 18), (0, 18)]
    owner.roof.obstacles, owner.roof.keepouts, owner.roof.parapet_height_m = [], [], 0
    owner.requirements.structured = StructuredRequirements(max_height_m=.5)
    with pytest.raises(GzError):
        personal.tilt_bounds(owner, design(1).params.model_copy(update=dict(layout='ew')))
    owner.requirements.structured.max_height_m = .7
    storage.save(owner)
    mcp_actions._generate_layout(owner.id, {}, offline=True)
    analysis.analyze(owner.id, 1, offline=True)
    result = mcp_actions._compare_options(owner.id, 1, offline=True)
    candidates = [storage.load_design(owner.id, v) for v in range(2, storage.next_version(owner.id))]
    assert len(result['options']) == 3 and any(d.params.layout == 'ew' for d in candidates)
    for d in candidates:
        assert d.params.rows_per_rack == 1
        assert max((p[2] for m in d.modules for p in m.corners), default=0) <= .701
        assert d.params.tilt_deg <= personal.tilt_bounds(owner, d.params)[1] + 1e-9
        if d.params.layout == 'ew':
            assert {m.azimuth for m in d.modules} <= {90, 270}


def test_metal_actual_local_height_and_conflict(owner):
    metal = factory('metal-demo-n')
    owner.roof, owner.equipment = metal.roof, metal.equipment
    owner.requirements.structured.max_height_m = .01
    storage.save(owner)
    returned = mcp_actions._set_requirements(owner.id, '不能高出屋面1厘米', dict(max_height_m=.01), offline=True)
    assert any('低于组件离屋面' in row for row in returned['contradictions'])
    owner.requirements.structured.max_height_m = .2
    storage.save(owner)
    mcp_actions._generate_layout(owner.id, {}, offline=True)
    analysis.analyze(owner.id, 1, offline=True)
    checked = mcp_actions._read(owner.id, 'analysis/v1/rules.json')
    height = next(r for r in checked['items'] if r['id'] == 'G07')
    assert height['status'] == 'pass' and height['value'] == pytest.approx(layout._catalog(owner)[2])


@pytest.mark.parametrize('limit', [130, 80])
def test_joint_infeasibility_retains_u06_and_recovers_after_real_deletion(phase_context, limit):
    identifier = phase_context['project_id']
    p = storage.load(identifier)
    p.requirements.structured.transformer_kva, p.requirements.structured.transformer_share = limit, 1
    p.equipment.inverter_brand = 'Sungrow'
    storage.save(p)
    version, statuses = 1, []
    for _ in range(10):
        analysis.analyze(identifier, version, offline=True)
        row = next(r for r in mcp_actions._read(identifier, f'analysis/v{version}/rules.json')['items'] if r['id'] == 'U06')
        statuses.append(row['status'])
        if row['status'] == 'pass':
            break
        version = storage.edit_design(identifier, version, [row['suggestion']], 'U06两期合计复核', 'rule', offline=True)['version']
    assert statuses[0] == 'fail' and statuses[-1] == 'pass'
    saved = storage.load_design(identifier, version)
    assert {m.phase for m in saved.modules} == ({1, 2} if limit == 130 else {1})
    checked = mcp_actions._read(identifier, f'analysis/v{version}/rules.json')
    assert next(r for r in checked['items'] if r['id'] == 'U07')['status'] == 'pass'


def test_exact_model_preserves_failed_electrical_diagnostics(owner):
    owner.equipment.inverter_brand, owner.equipment.inverter_id = 'Huawei', 'huawei-sun2000-100ktl-m2'
    d = design(100)
    d.modules_per_string = 40
    result = electrical.calculate(owner, d, offline=True)
    assert all(u['inverter_id'] == owner.equipment.inverter_id for u in result['per_inverter'])
    assert any(r['status'] == 'fail' for r in result['checks'].values())


def test_compare_repairs_two_phase_discrete_ac_boundary(owner):
    owner.roof.outline = [(0, 0), (30, 0), (30, 25), (0, 25)]
    owner.roof.obstacles, owner.roof.keepouts, owner.roof.parapet_height_m = [], [], 0
    owner.requirements.structured = StructuredRequirements(phase1_kw=20, transformer_kva=80, transformer_share=1, tilt_deg_range=(10, 10))
    owner.equipment.inverter_brand = 'Sungrow'
    storage.save(owner)
    mcp_actions._generate_layout(owner.id, dict(tilt_deg=10), offline=True)
    analysis.analyze(owner.id, 1, offline=True)
    result = mcp_actions._compare_options(owner.id, 1, offline=True)
    for option in result['options']:
        checked = mcp_actions._read(owner.id, f"analysis/v{option['version']}/rules.json")
        assert all(r['status'] == 'pass' for r in checked['items'] if r['id'] in ('U06', 'U07'))
    repaired = []
    for version in range(2, storage.next_version(owner.id)):
        d = storage.load_design(owner.id, version)
        if '自动修正 U06' in d.reason:
            repaired.append(version)
            assert len(d.modules) < len(storage.load_design(owner.id, d.parent_version).modules)
    assert repaired


def test_removal_shading_ignores_only_phase_metadata(owner):
    d = layout.generate_layout(owner, {})
    d.modules = d.modules[:8]
    reuse = shading.RemovalShading(owner, d, offline=True)
    changed = d.model_copy(deep=True)
    for m in changed.modules:
        m.phase = 1
    assert reuse.analyze(changed)['modules'] == shading.analyze_design(owner, changed, offline=True)['modules']
    for field in ('azimuth', 'corners', 'orientation'):
        bad = changed.model_copy(deep=True)
        if field == 'azimuth':
            bad.modules[0].azimuth += 1
        elif field == 'orientation':
            bad.modules[0].orientation = 'landscape'
        else:
            bad.modules[0].corners = tuple((x, y, z + .1) for x, y, z in bad.modules[0].corners)
        with pytest.raises(ValueError, match='unchanged geometry'):
            reuse.analyze(bad)


def test_u07_budget_insufficiency_and_u05_missing_data_are_explicit(owner):
    owner.requirements.structured = StructuredRequirements(phase1_budget_cny=1, export_allowed=False)
    owner.economics.monthly_kwh, owner.economics.shifts = None, None
    storage.save(owner)
    mcp_actions._generate_layout(owner.id, {}, offline=True)
    analysis.analyze(owner.id, 1, offline=True)
    checked = {r['id']: r for r in mcp_actions._read(owner.id, 'analysis/v1/rules.json')['items']}
    assert checked['U07']['status'] == 'fail' and checked['U07']['value'] == 0
    assert '预算1元，余额1元' in checked['U07']['note'] and '非空完整组串' in checked['U07']['note']
    assert checked['U05']['status'] == 'na' and '月用电量和班次' in checked['U05']['note']
    owner.requirements.structured = StructuredRequirements()
    owner.economics.price_export_cny_kwh = 0
    storage.save(owner)
    mcp_actions._generate_layout(owner.id, {}, offline=True)
    analysis.analyze(owner.id, 2, offline=True)
    assert 'U05' not in {r['id'] for r in mcp_actions._read(owner.id, 'analysis/v2/rules.json')['items']}


@pytest.mark.parametrize('change,budget_ratio,before_status,after_status', [(10, 1.05, 'pass', 'fail'), (-10, .95, 'fail', 'pass')])
def test_what_if_reports_phase_budget_crossing_without_writes(phase_context, change, budget_ratio, before_status, after_status):
    identifier = phase_context['project_id']
    p = storage.load(identifier)
    cost = phase_context['economics']['phases'][0]['capex_cny']
    budget = cost * budget_ratio
    p.requirements.structured = StructuredRequirements(phase1_budget_cny=budget)
    storage.save(p)
    analysis.analyze(identifier, 1, offline=True)
    checked = mcp_actions._read(identifier, 'analysis/v1/rules.json')
    old = next(r for r in checked['items'] if r['id'] == 'U07')
    assert old['status'] == before_status
    paths = list(storage._path(identifier).rglob('*'))
    before = {str(path): path.read_bytes() for path in paths if path.is_file()}
    result = mcp_actions._what_if(identifier, 1, dict(capex_change_pct=change), True)
    row = next(r for r in result['what_if']['rules'] if r['id'] == 'U07')
    assert row == dict(id='U07', status=after_status, value=pytest.approx(cost * (1 + change / 100)), limit=budget)
    other = sum(r['level'] == 'hard' and r['status'] == 'fail' for r in checked['items'] if r['id'] != 'U07')
    assert result['what_if']['hard_failed'] == other + (after_status == 'fail')
    assert result['what_if']['saved'] is False and len(analysis.serialized(result).encode('utf-8')) + 128 <= 2048
    from guangzhu.wind import NOTE
    assert result['wind']['note'] == NOTE and result['wind']['W01'] == 'na'
    assert result['wind']['worst_zone'] and '仅GB55001' in result['wind']['source_status']
    print(json.dumps(dict(t31_phase_what_if_change=change, body_bytes=len(analysis.serialized(result).encode('utf-8')),
                          reserved_bytes=128, wind=result['wind'], failed=result['rules']['failed']), ensure_ascii=False))
    assert before == {str(path): path.read_bytes() for path in storage._path(identifier).rglob('*') if path.is_file()}


def test_metal_setter_ignores_inapplicable_tilt_bounds(owner):
    metal = factory('metal-demo-n')
    owner.roof, owner.equipment = metal.roof, metal.equipment
    storage.save(owner)
    result = mcp_actions._set_requirements(owner.id, '限高20厘米，倾角5度', dict(max_height_m=.2, tilt_deg_range=[5, 5]), offline=True)
    assert not result['contradictions']
    mcp_actions._generate_layout(owner.id, {}, offline=True)
    analysis.analyze(owner.id, 1, offline=True)
    rows = {r['id']: r for r in mcp_actions._read(owner.id, 'analysis/v1/rules.json')['items']}
    assert rows['G07']['status'] == 'pass' and rows['G05']['status'] == 'na'
    result = mcp_actions._set_requirements(owner.id, '限高1厘米，倾角5度', dict(max_height_m=.01, tilt_deg_range=[5, 5]), offline=True)
    assert any('低于组件离屋面' in value for value in result['contradictions'])


def test_zero_capex_budget_saves_complete_prefix(owner):
    owner.economics.capex_cny_per_w = 0
    owner.requirements.structured.phase1_budget_cny = 1
    storage.save(owner)
    mcp_actions._generate_layout(owner.id, {}, offline=True)
    d = storage.load_design(owner.id, 1)
    assert all(m.phase == 1 for m in d.modules)
    assert d.statistics['phasing']['achieved_cny'] == 0 and d.statistics['phasing']['remainder_cny'] == 1
    result = electrical.calculate(storage.load(owner.id), d, offline=True)
    assert not result['unused_modules']


def test_phase_png_legend_does_not_overlap_scale(owner, monkeypatch, tmp_path):
    from matplotlib.figure import Figure
    saved = Figure.savefig
    observations = []
    def inspect(figure, *args, **kwargs):
        figure.canvas.draw()
        axes, renderer = figure.axes[0], figure.canvas.get_renderer()
        legend = axes.get_legend()
        assert {'一期', '二期'} <= {text.get_text() for text in legend.get_texts()}
        scale = next(text for text in axes.texts if text.get_text() == '5 m')
        assert not legend.get_window_extent(renderer).overlaps(scale.get_window_extent(renderer))
        observations.append(True)
        return saved(figure, *args, **kwargs)
    monkeypatch.setattr(Figure, 'savefig', inspect)
    d = layout.generate_layout(owner, {})
    for index, module in enumerate(d.modules):
        module.phase = 1 if index < 55 else 2
    target = tmp_path / 'phase-layout.png'
    layout.plot_layout(owner, d, target)
    assert observations == [True] and target.stat().st_size > 1000
