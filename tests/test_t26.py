"""T26 independent cable arithmetic and routing contracts, entirely offline."""
import copy
import math
import hashlib
import json

import pytest

from guangzhu import electrical
from test_electrical import project, design


@pytest.fixture
def cable_context(tmp_path, monkeypatch, request):
    from guangzhu import analysis, layout, project as storage, rules
    from guangzhu.config import ROOT
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    p = storage.init(ROOT / 'data/demo/projects' / getattr(request, 'param', 'changzhou-demo'), 't26-offline')
    d = layout.generate_layout(p, {})
    storage.save_design(p.id, d)
    summary = analysis.analyze(p.id, d.version, offline=True)
    def read(name):
        return json.loads(storage._path(p.id, f'analysis/v{d.version}/{name}.json').read_text(encoding='utf-8'))
    before = read('electrical')
    rules.check(p.id, d.version, offline=True)
    assert read('electrical') == before
    context = dict(project=p.model_dump(mode='json'), design=d.model_dump(mode='json'), summary=summary, version=d.version,
                   compare=None, facts={}, review=None, approval=None, sessions=[], requirements=[], verification={},
                   sources={}, versions=[], relaxations=[], history=[], run={}, generated_at='2026-10-06T00:00:00+08:00',
                   run_id='T26-offline-no-AI', project_id=p.id, crosscheck=None)
    context.update({name: read(name) for name in ['electrical', 'shading', 'structure', 'rules', 'economics']})
    return context


def test_exported_cable_rows_and_report_page(cable_context, tmp_path):
    from openpyxl import load_workbook
    from guangzhu.report.deliverables import write_deliverables
    from guangzhu.report.view import render
    c = cable_context
    write_deliverables(c['project_id'], c['version'], tmp_path)
    book = load_workbook(tmp_path / 'bom-v1.xlsx')
    rows = list(book['材料清单'].values)
    expected = c['electrical']['cables']['summary']
    cables = [r for r in rows if r[0] in ['直流电缆', '交流电缆']]
    assert len(cables) == len(expected)
    for row, value in zip(cables, expected):
        assert row[4] == pytest.approx(value['length_m']) and row[5] == 'm'
        assert str(value['section_mm2']) in row[2]
    html = render(c)
    assert '电缆和压降' in html and '未模拟串内失配' in html and '20000h' in html
    assert len(json.dumps(c['summary'], ensure_ascii=False, separators=(',', ':')).encode()) <= 2048


def test_dc_loop_and_three_phase_hand_arithmetic(project):
    project.roof.inverter_positions = [(0, 0)]
    project.roof.grid_point = (20, 30)
    option = design(25, 25, cols=25)
    result = electrical.calculate(project, option, offline=True)
    dc = result['cables']['dc'][0]
    # Centres 1,1 ... 73,1: 72m jumpers +2m first lead +74m last lead.
    assert dc['route_m'] == 148
    assert dc['length_m'] == pytest.approx(162.8)
    assert dc['one_way_m'] == pytest.approx(81.4)
    module = electrical.equipment_catalog()['modules'][project.equipment.module_id]
    assert .0244125 * 162.8 * module['imp_a'] / (4 * 25 * module['vmp_v']) * 100 > 2
    drop = .0244125 * 162.8 * module['imp_a'] / (6 * 25 * module['vmp_v']) * 100
    assert dc['drop_pct'] == pytest.approx(drop)
    assert dc['section_mm2'] == 6
    ac = result['cables']['ac'][0]
    current = 99990 / (math.sqrt(3) * 400)
    length = 50 + project.roof.height_m + 5
    assert ac['current_a'] == pytest.approx(current)
    assert ac['route_m'] == length - 5 and ac['length_m'] == length and ac['conductor_m'] == 4 * length
    expected = math.sqrt(3) * .02233875 * length * current / (50 * 400) * 100
    assert ac['section_mm2'] == 50 and ac['drop_pct'] == pytest.approx(expected)
    assert result['checks']['E10']['status'] == result['checks']['E11']['status'] == 'pass'


@pytest.mark.parametrize('distance,section,status', [(150, 10, 'pass'), (1000, 10, 'fail')])
def test_dc_section_and_exhaustion(project, distance, section, status):
    project.roof.outline = [(0, 0), (1100, 0), (1100, 120), (0, 120)]
    project.roof.inverter_positions = [(distance, 0)]
    result = electrical.calculate(project, design(25, 25, cols=25), offline=True)
    assert result['cables']['dc'][0]['section_mm2'] == section
    assert result['checks']['E10']['status'] == status
    assert result['checks']['E10']['level'] == 'hard'
    assert '把逆变器放近一点，或分成两组' in result['checks']['E10']['hint_zh']


def test_default_projection_and_legacy_serialization(project):
    before = project.model_dump(mode='json')
    assert 'inverter_positions' not in before['roof'] and 'grid_point' not in before['roof']
    project.roof.outline = [(0, 0), (100, 0), (100, 60), (0, 60)]
    result = electrical.calculate(project, design(25, 25, cols=25), offline=True)
    points = result['cables']['positions']
    assert points[0]['point'] == [37, 0] and points[0]['default']
    assert points[-1]['point'] == [37, 0] and points[-1]['default']
    assert all('示意' in row['note'] for row in points)


def test_position_strings_unchanged_and_shadow_selection(project):
    project.roof.inverter_positions = [(40, 0)]
    option = design(100, 25, cols=10)
    baseline = electrical.calculate(project, option, offline=True)
    losses = dict(version=option.version, modules=[dict(id=m.id, total_loss_pct=6 if m.col <= 5 else 0) for m in option.modules])
    alternative = electrical.calculate(project, option, offline=True, shadows=losses)
    assert alternative['wiring']['method'] == '按阴影接'
    assert alternative['wiring']['shadow_spread_pct'] == 0
    assert alternative['wiring']['position_spread_pct'] == 6
    assert alternative['dc_kw'] == baseline['dc_kw']
    uniform = copy.deepcopy(losses)
    for row in uniform['modules']:
        row['total_loss_pct'] = 0
    positional = electrical.calculate(project, option, offline=True, shadows=uniform)
    assert positional['wiring']['method'] == '按位置接'
    assert positional['strings'] == baseline['strings']
    assert positional['per_inverter'] == baseline['per_inverter']


def test_ac_long_distance_fails_and_empty_design_is_finite(project):
    project.roof.grid_point = (10000, 10000)
    result = electrical.calculate(project, design(25, 25), offline=True)
    assert result['checks']['E11']['status'] == 'fail'
    assert result['cables']['ac'][0]['section_mm2'] == 185
    empty = electrical.calculate(project, design(0), offline=True)
    assert empty['dc_drop_pct_max'] == empty['ac_drop_pct_max'] == 0


@pytest.mark.parametrize('cable_context', ['l-shape'], indirect=True)
def test_analyze_then_rule_check_retains_real_shadow_wiring(cable_context):
    # Review fix: section-based strings changed the l-shape numbers; the stored choice must follow the selection rule.
    w = cable_context['electrical']['wiring']
    gain = w['position_spread_pct'] - w['shadow_spread_pct'] >= 1 and w['shadow_length_m'] <= w['position_length_m'] * 1.1
    assert w['method'] == '按阴影接' if gain and '压降不新增超限' not in w['reason'] else w['method'] == '按位置接'


def test_fixed_device_count_and_no_stale_short_length(project):
    project.roof.inverter_positions = [(14, 17)]
    option = design(90, cols=10)
    original = electrical.calculate(project, option, offline=True)
    losses = dict(version=option.version, modules=[dict(id=m.id, total_loss_pct=6 if i < 36 else 0)
                                                for i, m in enumerate(option.modules)])
    selected = electrical.calculate(project, option, offline=True, shadows=losses)
    assert selected['wiring']['method'] == '按阴影接'
    assert original['modules_per_string_short'] == 22
    assert 'modules_per_string_short' not in selected
    assert {len(s['module_ids']) for s in selected['strings']} == {18}
    assert selected['inverters'] == original['inverters']
    assert selected['inverter_count'] == original['inverter_count']


@pytest.mark.parametrize('loss,method', [(3.99, '按位置接'), (4, '按阴影接')])
def test_one_percentage_point_boundary(project, loss, method):
    project.roof.inverter_positions = [(40, 0)]
    option = design(100, 25, cols=10)
    shadows = dict(version=1, modules=[dict(id=m.id, total_loss_pct=loss if m.col <= 5 else 3) for m in option.modules])
    result = electrical.calculate(project, option, offline=True, shadows=shadows)
    assert result['wiring']['method'] == method


def test_longer_wire_rejected_small_class_merges_and_missing_loss_is_explicit(project):
    option = design(100, cols=10)
    shadows = dict(version=1, modules=[dict(id=m.id, total_loss_pct=6 if i < 10 else 0) for i, m in enumerate(option.modules)])
    result = electrical.calculate(project, option, offline=True, shadows=shadows)
    assert result['wiring']['shadow_spread_pct'] == 0
    assert result['wiring']['shadow_length_m'] > result['wiring']['position_length_m'] * 1.1
    assert result['wiring']['method'] == '按位置接'
    option.modules_per_string = 25
    merged = electrical.calculate(project, option, offline=True, shadows=shadows)
    assert merged['wiring']['shadow_spread_pct'] == merged['wiring']['position_spread_pct']
    shadows['modules'].pop()
    missing = electrical.calculate(project, option, offline=True, shadows=shadows)
    assert '缺少' in missing['wiring']['reason']


def test_ampacity_cannot_pass_on_small_voltage_drop():
    from guangzhu.cables import conductor
    dc = conductor('dc', 1, 80, 1000, 100)
    assert dc['drop_pct'] < 2 and not dc['feasible'] and dc['section_mm2'] == 10


def test_rule_check_recomputes_stale_shading(cable_context, monkeypatch):
    from guangzhu import project as storage, rules, shading
    path = storage._path(cable_context['project_id'], 'analysis/v1/shading.json')
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['metadata']['design_sha256'] = 'stale'
    path.write_text(json.dumps(payload), encoding='utf-8')
    called = []
    original = shading.analyze
    def recalculate(*args, **kwargs):
        called.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(shading, 'analyze', recalculate)
    rules.check(cable_context['project_id'], 1, offline=True)
    assert len(called) == 1
    current = json.loads(path.read_text(encoding='utf-8'))
    assert current['metadata']['design_sha256'] == hashlib.sha256(storage._path(cable_context['project_id'], 'designs/v1.json').read_bytes()).hexdigest()


def test_shadow_wiring_keeps_orientation_and_surface_groups(project):
    from guangzhu.orientation import key
    option = design(180, cols=10)
    for i, m in enumerate(option.modules):
        m.id = f'P{1 + i // 90}-' + m.id
        m.azimuth = 180 if i < 90 else 90
    losses = dict(version=1, modules=[dict(id=m.id, total_loss_pct=6 if i % 90 < 36 else 0) for i, m in enumerate(option.modules)])
    result = electrical.calculate(project, option, offline=True, shadows=losses)
    identities = {m.id: key(m) for m in option.modules}
    ports = {}
    for string in result['strings']:
        assert len({identities[mid] for mid in string['module_ids']}) == 1
        ports.setdefault((string['inverter'], string['mppt']), set()).update(identities[mid] for mid in string['module_ids'])
    assert all(len(group) == 1 for group in ports.values())
    assert result['checks']['E09']['status'] == 'pass'


def test_legacy_electrical_what_if_cache_is_recomputed_without_writes(cable_context, monkeypatch):
    from guangzhu import analysis, project as storage, mcp_actions
    path = storage._path(cable_context['project_id'], 'analysis/v1/electrical.json')
    old = json.loads(path.read_text(encoding='utf-8'))
    for key in ['cables', 'dc_drop_pct_max', 'ac_drop_pct_max', 'wiring']:
        old.pop(key)
    path.write_text(json.dumps(old), encoding='utf-8')
    folder = storage._path(cable_context['project_id'])
    before = {p: p.read_bytes() for p in folder.rglob('*') if p.is_file()}
    monkeypatch.setattr(analysis, 'generation', lambda *a, **kw: pytest.fail('cached yield must be reused'))
    result = mcp_actions._what_if(cable_context['project_id'], 1, {'price_change_pct': -10}, True)
    assert result['electrical'] == cable_context['summary']['electrical']
    assert result['rules'] == cable_context['summary']['rules']
    assert {p: p.read_bytes() for p in folder.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('changed_input', ['positions', 'height'])
def test_cached_what_if_uses_current_cable_inputs_without_writes(cable_context, monkeypatch, changed_input):
    from guangzhu import analysis, mcp_actions, project as storage, rules, shading
    from guangzhu import costs, structure
    pid, version = cable_context['project_id'], cable_context['version']
    p, option = storage.load(pid), storage.load_design(pid, version)
    if changed_input == 'positions':
        p.roof.inverter_positions = [(1000, 1000)]
        p.roof.grid_point = (10000, 10000)
    else:
        p.roof.height_m = 1000
    storage.save(p)
    fresh = electrical.calculate(p, option, offline=True, shadows=cable_context['shading'])
    expected = {code: fresh['checks'][code]['status'] for code in ['E10', 'E11']}
    assert expected['E11'] == 'fail'
    assert expected['E10'] == ('fail' if changed_input == 'positions' else 'pass')
    evaluated, evaluate = [], rules.evaluate
    def capture(*args):
        result = evaluate(*args)
        evaluated.append({row['id']: row['status'] for row in result['items'] if row['id'] in expected})
        return result
    monkeypatch.setattr(rules, 'evaluate', capture)
    def forbidden(*args, **kwargs):
        pytest.fail('cached what-if must reuse shading and yield')
    monkeypatch.setattr(analysis, 'generation', forbidden)
    monkeypatch.setattr(shading, 'analyze_design', forbidden)
    folder = storage._path(pid)
    before = {path: path.read_bytes() for path in folder.rglob('*') if path.is_file()}
    result = mcp_actions._what_if(pid, version, {'price_change_pct': -10}, True)
    quoted = costs.itemized(p, fresh['dc_kw'], option, fresh, structure.calculate(p, option))
    assert result['economics']['capex_cny'] == round(quoted['capex_cny'], 4)
    assert result['economics']['capex_cny'] != cable_context['summary']['economics']['capex_cny']
    for field in ['dc_drop_pct_max', 'ac_drop_pct_max']:
        assert result['electrical'][field] == round(fresh[field], 4)
    assert evaluated == [expected, expected]
    assert result['yield_kwh'] == cable_context['summary']['yield_kwh']
    assert {path: path.read_bytes() for path in folder.rglob('*') if path.is_file()} == before
