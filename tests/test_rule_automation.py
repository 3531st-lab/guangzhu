"""Rule workflows preserve versions and never impersonate an independent reviewer."""
import hashlib
import json

from fastapi.testclient import TestClient
import pytest

from guangzhu import api, auto_agent, mcp_actions, project as storage
from guangzhu.config import API_ORIGIN
from guangzhu.models import GzError
from test_manual_modules import factory, add  # noqa: F401


@pytest.fixture
def rule_case(factory, tmp_path, monkeypatch):
    record, blank = factory()
    design = add(record, blank, [dict(center=[7, 7]), dict(center=[15, 7]), dict(center=[23, 7]),
                                 dict(center=[7, 15]), dict(center=[15, 15]), dict(center=[23, 15])])
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    monkeypatch.setattr(auto_agent, 'ROOT', tmp_path)
    monkeypatch.setattr(mcp_actions, 'ROOT', tmp_path)
    template = tmp_path / 'data/demo/projects/taizhou-cmc-pharma/project.json'
    template.parent.mkdir(parents=True)
    template.write_text(record.model_dump_json(), encoding='utf-8')
    with TestClient(api.app, base_url=API_ORIGIN, headers={'origin': API_ORIGIN}) as client:
        yield record, design, client


def file_hashes(base):
    return {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in base.rglob('*') if p.is_file()}


def test_invalid_repeated_auto_request_never_deletes_existing_project(rule_case):
    record, design, client = rule_case
    storage.edit_design(record.id, design.version, [dict(op='lock_modules', module_ids=[design.modules[0].id])],
                        '保留既有方案', 'user', offline=True)
    base = storage._path(record.id)
    before = file_hashes(base)
    for overwrite in (None, True, False):
        payload = dict(project_id=record.id, template='not-a-template')
        if overwrite is not None:
            payload['overwrite_existing'] = overwrite
        response = client.post('/api/projects/auto-run', json=payload)
        assert response.status_code == 422
        assert file_hashes(base) == before


@pytest.mark.parametrize('request_export', [False, True])
def test_rule_workflow_records_crosscheck_failure_without_review_or_export(rule_case, monkeypatch, request_export):
    record, design, client = rule_case
    checked = dict(version=design.version, hard_failed=0, passed=1, total=1,
                   items=[dict(id='G01', level='hard', status='pass')])
    directory = storage._path(record.id, f'analysis/v{design.version}')
    directory.mkdir(parents=True)
    (directory / 'rules.json').write_text(json.dumps(checked), encoding='utf-8')
    summary = dict(version=design.version, modules=6, dc_kw=3.3, shading=dict(avg_loss_pct=1),
                   yield_kwh=dict(p50=3000), suggestions=[])
    monkeypatch.setattr(auto_agent, '_safe_project_id', lambda _: record.id)
    monkeypatch.setattr(mcp_actions, '_new_project', lambda *_a, **_k: dict(name='test', roof_area_m2=960))
    monkeypatch.setattr(mcp_actions, '_set_requirements', lambda *_a, **_k: {})
    monkeypatch.setattr(mcp_actions, '_fetch_weather', lambda *_a, **_k: {})
    monkeypatch.setattr(mcp_actions, '_generate_layout', lambda *_a, **_k: dict(version=design.version, modules=6, dc_kw=3.3))
    monkeypatch.setattr(mcp_actions, '_analyze', lambda *_a, **_k: summary)
    monkeypatch.setattr(mcp_actions, '_crosscheck_yield', lambda *_a, **_k: (_ for _ in ()).throw(
        GzError('NO_DATA', '测试气象缺失', '先补数据')))
    exports, reviews = [], []
    monkeypatch.setattr(mcp_actions, '_export', lambda *_a, **_k: exports.append(True) or dict(manifest_sha256='0' * 64))
    monkeypatch.setattr(mcp_actions, '_record_review', lambda *_a, **_k: reviews.append(True))
    result = client.post('/api/projects/auto-run', json=dict(project_id=record.id, overwrite_existing=False,
                         export=request_export, compare=False)).json()
    assert exports == [] and reviews == []
    assert result['workflow_kind'] == 'rules'
    assert result['independent_review']['status'] == 'not_performed'
    assert result['crosscheck']['status'] == 'unavailable'
    assert '测试气象缺失' in result['crosscheck']['reason']
    assert result['exported'] is False
    assert result['export_status'] == ('awaiting_approval' if request_export else 'not_requested')
    assert not storage._path(record.id, 'reviews').exists()
    selected = json.loads(storage._path(record.id, 'local-selection.json').read_text(encoding='utf-8'))
    assert selected['version'] == design.version and selected['source'] == 'rule-auto'


def test_capacity_command_preserves_locked_panels_and_uses_supported_operation(rule_case, monkeypatch):
    record, design, client = rule_case
    protected = [module.id for module in design.modules[-2:]]
    locked = storage.edit_design(record.id, design.version, [dict(op='lock_modules', module_ids=protected)],
                                 '保留锁板', 'user', offline=True)['version']
    checked = dict(version=locked, hard_failed=0, passed=1, total=1, items=[])

    def analyze(pid, version, **_kwargs):
        current = storage.load_design(pid, version)
        directory = storage._path(pid, f'analysis/v{version}')
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'rules.json').write_text(json.dumps(checked | dict(version=version)), encoding='utf-8')
        return dict(dc_kw=len(current.modules) * .55, yield_kwh=dict(p50=3000), suggestions=[])

    monkeypatch.setattr(mcp_actions, '_fetch_weather', lambda *_a, **_k: {})
    monkeypatch.setattr(mcp_actions, '_analyze', analyze)
    monkeypatch.setattr(mcp_actions, '_export', lambda *_a, **_k: pytest.fail('Copilot must not export implicitly'))
    response = client.post(f'/api/projects/{record.id}/copilot', json=dict(version=locked, text='把容量调整到 2 kW'))
    assert response.status_code == 200, response.text
    saved = storage.load_design(record.id, response.json()['version'])
    assert len(saved.modules) == 3
    assert {module.id for module in saved.modules} >= set(protected)
    old = {module.id: module for module in storage.load_design(record.id, locked).modules}
    assert all(module == old[module.id] for module in saved.modules if module.id in protected)
    selected = json.loads(storage._path(record.id, 'local-selection.json').read_text(encoding='utf-8'))
    assert selected['version'] == saved.version and selected['source'] == 'rule-command'
    response = client.post(f'/api/projects/{record.id}/copilot', json=dict(version=saved.version, text='容量调整到 0.5 kW'))
    assert response.status_code == 422
    assert '锁定' in response.text
    assert storage.next_version(record.id) == saved.version + 1


def test_repair_uses_authoritative_rule_suggestions_and_does_not_guess_payback_pruning(rule_case):
    record, design, _client = rule_case
    target = design.modules[0].id
    checked = dict(items=[dict(id='E08', level='hard', status='fail', value=1, limit=0,
                              suggestion=dict(op='remove_modules', module_ids=[target]))])
    ops, _ = auto_agent._repair_operations(record, design, {}, checked)
    assert ops == [dict(op='remove_modules', module_ids=[target])]
    checked = dict(items=[dict(id='U04', level='hard', status='fail', value=12, limit=6, suggestion=None)])
    ops, _ = auto_agent._repair_operations(record, design, {}, checked)
    assert ops == []


def test_auto_preserves_template_requirements_and_only_overrides_requested_fields(rule_case, monkeypatch):
    record, _design, _client = rule_case
    path = auto_agent.ROOT / 'data/demo/projects/taizhou-cmc-pharma/project.json'
    template = json.loads(path.read_text(encoding='utf-8'))
    template['roof']['keepouts'] = [dict(id='access', label='检修预留', polygon=[[1, 1], [3, 1], [3, 3], [1, 3]])]
    template['requirements'] = dict(text='保留检修预留区及通道', structured=dict(
        keep_clear_ids=['access'], walkway_m_min=1.2, payback_years_max=8, budget_cny_max=50000))
    path.write_text(json.dumps(template, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(mcp_actions, '_fetch_weather', lambda *_a, **_k: {})

    class BeforeLayout(Exception):
        pass

    def stop_after_saved_requirements(*_args, **_kwargs):
        raise BeforeLayout

    monkeypatch.setattr(mcp_actions, '_generate_layout', stop_after_saved_requirements)
    with pytest.raises(BeforeLayout):
        auto_agent.run_autonomous_design(dict(project_id='constraints-preserved', text='预算改为六万元',
            structured=dict(budget_cny_max=60000)))
    actual = storage.load('constraints-preserved').requirements
    assert actual.structured.keep_clear_ids == ['access']
    assert actual.structured.walkway_m_min == 1.2 and actual.structured.payback_years_max == 8
    assert actual.structured.budget_cny_max == 60000
    assert '保留检修预留区' in actual.text and '预算改为六万元' in actual.text


def test_command_reuses_only_complete_current_calculation(rule_case, monkeypatch):
    from guangzhu import analysis
    record, design, client = rule_case
    analysis.analyze(record.id, design.version, offline=True)
    monkeypatch.setattr(mcp_actions, '_fetch_weather', lambda *_a, **_k: {})
    original = mcp_actions._analyze
    calls = []

    def observed(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(mcp_actions, '_analyze', observed)
    before = file_hashes(storage._path(record.id))
    response = client.post(f'/api/projects/{record.id}/copilot', json=dict(version=design.version, text='移除遮挡大于100%的组件'))
    assert response.status_code == 422 and calls == []
    assert file_hashes(storage._path(record.id)) == before
    changed = storage.load(record.id)
    changed.economics.price_self_cny_kwh = .92
    storage.save(changed)
    before = file_hashes(storage._path(record.id))
    response = client.post(f'/api/projects/{record.id}/copilot', json=dict(version=design.version, text='不支持的指令'))
    assert response.status_code == 422 and calls == []
    assert file_hashes(storage._path(record.id)) == before
    response = client.post(f'/api/projects/{record.id}/copilot', json=dict(version=design.version, text='移除遮挡大于100%的组件'))
    assert response.status_code == 422 and len(calls) == 1
    assert storage.next_version(record.id) == design.version + 1


def test_invalid_equipment_never_changes_current_or_stale_locked_project(rule_case, monkeypatch):
    from guangzhu import analysis
    record, design, client = rule_case
    version = storage.edit_design(record.id, design.version,
        [dict(op='lock_modules', module_ids=[design.modules[0].id])], '保留锁板', 'user', offline=True)['version']
    analysis.analyze(record.id, version, offline=True)
    monkeypatch.setattr(mcp_actions, '_fetch_weather', lambda *_a, **_k: {})
    monkeypatch.setattr(mcp_actions, '_analyze', lambda *_a, **_k: pytest.fail('Invalid equipment must not recalculate'))
    payloads = [dict(module_id='unknown-module'), dict(inverter_id='unknown-inverter'),
                dict(module_id='longi-himo9-660m', inverter_id='unknown-inverter'),
                dict(dc_cable_family='YJLH22'), dict(ac_cable_family='unknown-cable'),
                dict(module_id=['invalid-type']), dict(ac_cable_family=['invalid-type'])]
    for stale in (False, True):
        if stale:
            project = storage.load(record.id)
            project.economics.price_self_cny_kwh = .93
            storage.save(project)
        before = file_hashes(storage._path(record.id))
        for changed in payloads:
            response = client.post(f'/api/projects/{record.id}/copilot', json=dict(
                version=version, action='change_equipment', **changed))
            assert response.status_code == 422, response.text
            assert file_hashes(storage._path(record.id)) == before
            assert storage.next_version(record.id) == version + 1
