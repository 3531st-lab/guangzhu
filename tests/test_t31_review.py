"""T31 review regressions: phase installation identity and copyable bounded tool facts."""
import json
import math
import os

import pytest
from scipy.spatial import cKDTree

from guangzhu import analysis, costs, electrical, layout, mcp_actions, mcp_server, personal, project as storage, structure, wind
from guangzhu.config import ROOT
from guangzhu.models import WindSettings


def capture(tmp_path, name, value):
    folder = ROOT / 'reports/assets/T31/revision' if os.environ.get('T31_CAPTURE') == '1' else tmp_path
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def test_metal_phase_points_match_budget_cash_and_real_bom(tmp_path, monkeypatch):
    from openpyxl import load_workbook
    from guangzhu.report.deliverables import write_deliverables
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    record = storage.init(ROOT / 'data/demo/projects/metal-demo-s', 't31-phase-clamps')
    record.roof.wind = WindSettings(clamp_min_spacing_m=.4)
    record.requirements.structured.phase1_kw = 20
    design = layout.generate_layout(record, {})
    shadows = dict(modules=[dict(id=m.id, total_loss_pct=0) for m in design.modules])
    original_order = [m.id for m in design.modules]
    candidates = []
    original_itemized = costs.itemized
    def observe(project, dc_kw, view=None, electric=None, load=None):
        actual_load = load or structure.calculate(project, view)
        quote = original_itemized(project, dc_kw, view, electric, actual_load)
        candidates.append(dict(ids=[m.id for m in view.modules], wind=actual_load['wind'], quote=quote))
        return quote
    monkeypatch.setattr(costs, 'itemized', observe)
    outcomes = []
    for budget in (None, 64000):
        design.version = storage.next_version(record.id)
        record.requirements.structured.phase1_kw = 20 if budget is None else None
        record.requirements.structured.phase1_budget_cny = budget
        personal.prepare(record, design, offline=True, shadows=shadows)
        first_members = [m for m in design.modules if m.phase == 1]
        first_ids = {m.id for m in first_members}
        chosen = next(row for row in reversed(candidates) if set(row['ids']) == first_ids)
        assert chosen['ids'] == [mid for mid in original_order if mid in first_ids]
        full = structure.calculate(record, design)['wind']
        first = structure.calculate(record, design.model_copy(update=dict(modules=first_members)))['wind']
        full_rows = {r['id']: r['clamps'] for r in full['modules'] if r['phase'] == 1}
        first_rows = {r['id']: r['clamps'] for r in first['modules']}
        candidate_rows = {r['id']: r['clamps'] for r in chosen['wind']['modules']}
        assert full_rows == first_rows == candidate_rows
        assert full['clamp_failed'] == first['clamp_failed'] == 0
        points = [point for r in full['modules'] for point in r['clamps']['points']]
        assert len({tuple(point) for point in points}) == len(points)
        assert not cKDTree(points).query_pairs(.4 - 1e-8)
        assert sum(r['adopted'] for r in full_rows.values()) == first['clamp_count']
        if budget is None:
            # Phase one is the 20 kW nearest the default grid point (south eave since the review's string allocation).
            assert len(first_members) == 37 and first['clamp_count'] == 220
        else:
            assert chosen['quote']['capex_cny'] <= budget
            assert design.statistics['phasing']['achieved_cny'] == chosen['quote']['capex_cny']
        storage.save(record)
        storage.save_design(record.id, design, offline=True, shadows=shadows)
        record = storage.load(record.id)
        analysis.analyze(record.id, design.version, offline=True)
        cash = mcp_actions._read(record.id, f'analysis/v{design.version}/economics.json')
        cash_rows = {r['id']: r['clamps'] for r in cash['first_phase_wind']['modules']}
        assert cash_rows == json.loads(json.dumps(first_rows))
        output = tmp_path / ('kw' if budget is None else 'budget')
        output.mkdir()
        write_deliverables(record.id, design.version, output)
        book = load_workbook(output / f'bom-v{design.version}.xlsx', data_only=True)
        rows = list(book['分期材料'].values)[1:]
        count = sum(r[3] for r in rows if r[0] == 1 and r[1] == '抗风夹具')
        assert count == first['clamp_count']
        materials = list(book['材料清单'].values)[1:]
        assert next(r[4] for r in materials if r[0] == '抗风夹具') == full['clamp_count']
        clamp_cost = next(r for r in chosen['quote']['items'] if r['key'] == 'wind_clamp')
        assert clamp_cost['quantity'] == count and clamp_cost['subtotal_cny'] == 5 * count
        book.close()
        outcomes.append(dict(budget=budget, first_ids=[m.id for m in first_members], first_clamps=count,
                             first_points=first_rows, full_clamps=full['clamp_count'], candidate_capex=chosen['quote']['capex_cny']))
    capture(tmp_path, 'metal-phase-identity.json', outcomes)


@pytest.mark.parametrize('capacity', [.8, .001])
def test_analysis_summary_readonly_tools_and_whatif_keep_wind_facts(tmp_path, monkeypatch, capacity):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    record = storage.init(ROOT / 'data/demo/projects/metal-demo-s', 't31-tools')
    record.roof.wind = WindSettings(clamp_capacity_kn=capacity)
    storage.save(record)
    design = layout.generate_layout(record, {})
    design.modules = design.modules[:37]
    design.statistics.update(module_count=37, dc_kw=37 * .55)
    storage.save_design(record.id, design)
    unknown = mcp_actions._project_summary(record.id)['wind']
    assert unknown['W01'] == 'unknown' and '未记录' in unknown['source_status']
    response = mcp_server.call('gz_analyze', dict(project_id=record.id, version=design.version, offline=True))
    assert not response.is_error
    result = json.loads(response.content[0].text)
    archived = mcp_actions._read(record.id, f'analysis/v{design.version}/summary.json')
    load = mcp_actions._read(record.id, f'analysis/v{design.version}/structure.json')
    expected = wind.facts(load['wind'], design.version)
    assert expected['note'] == wind.NOTE and '仅GB55001' in expected['source_status']
    assert expected['W01'] == ('pass' if capacity == .8 else 'fail')
    assert expected['clamps']['adopted'] == load['wind']['clamp_count']
    assert expected['worst_zone'] == wind.LABELS[load['wind']['worst_zone']]
    assert archived['wind'] == result['wind'] == expected
    summary_reply = mcp_server.call('gz_project_summary', dict(project_id=record.id))
    assert not summary_reply.is_error and json.loads(summary_reply.content[0].text)['wind'] == expected
    assert {'gz_project_summary', 'gz_analyze'} <= mcp_server.READONLY
    sizes = dict(analyze=len(response.content[0].text.encode('utf-8')), summary=len(summary_reply.content[0].text.encode('utf-8')))
    paths = list(storage._path(record.id).rglob('*'))
    before = {path: path.read_bytes() for path in paths if path.is_file()}
    for change in (-10, 10):
        reply = mcp_server.call('gz_analyze', dict(project_id=record.id, version=design.version,
                                                what_if=dict(capex_change_pct=change), offline=True))
        assert not reply.is_error
        value = json.loads(reply.content[0].text)
        assert value['wind'] == expected and not value['what_if']['saved']
        assert value['rules']['hard_failed'] == result['rules']['hard_failed']
        assert {r['id'] for r in value['rules']['failed']} == {r['id'] for r in result['rules']['failed']}
        sizes[str(change)] = len(reply.content[0].text.encode('utf-8'))
        wrapped = mcp_server.JobQueue.response(dict(value, tool='gz_analyze', job_id='t31-wait-envelope'))
        assert len(wrapped.content[0].text.encode('utf-8')) <= 2048
    assert all(size + 128 <= 2048 for size in sizes.values())
    assert all(path.read_bytes() == payload for path, payload in before.items())
    capture(tmp_path, f'tool-facts-{capacity}.json', dict(wind=expected, bytes=sizes, allowance_bytes=128))
    load.pop('wind')
    folder = storage._path(record.id, f'analysis/v{design.version}')
    (folder / 'structure.json').write_text(json.dumps(load), encoding='utf-8')
    legacy = mcp_actions._project_summary(record.id)['wind']
    assert legacy['W01'] == 'unknown' and legacy['worst_zone'] is None
    assert '未记录' in legacy['source_status'] and legacy['note'] == wind.NOTE


def test_extreme_eight_failures_five_actions_keep_wind_and_envelope(tmp_path):
    from guangzhu.models import Design
    context = json.loads((ROOT / 'reports/assets/T31/export/context.json').read_text(encoding='utf-8'))
    rows = [dict(id=f'X{i}', name_zh='测试失败规则', value=i, limit=0, hint_zh='调整参数后重新分析',
                 level='hard', status='fail', suggestion=dict(op='set_string_size', modules_per_string=i + 1)) for i in range(15)]
    checked = dict(total=22, passed=0, items=rows)
    result = analysis._summary(Design.model_validate(context['design']), context['shading'], context['electrical'],
                               context['structure'], context['economics'], context['summary']['yield_kwh'], checked)
    assert result['wind']['note'] == wind.NOTE and result['wind']['W01'] == 'na'
    assert result['rules']['hard_failed'] == 15 and len(result['rules']['failed']) == 8
    assert result['suggestions'] == [r['suggestion'] for r in rows[:5]]
    for original, compact in zip(rows, result['rules']['failed']):
        assert all(compact[key] == original[key] for key in ('id', 'level', 'value', 'limit'))
    size = len(analysis.serialized(result).encode('utf-8'))
    assert size + 128 <= 2048
    capture(tmp_path, 'extreme-tool-facts.json', dict(bytes=size, allowance_bytes=128, result=result))
