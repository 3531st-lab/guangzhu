"""T13 no-export evidence and lean archives, using inert native export fixtures."""
import copy
import hashlib
import json
import shutil

import pytest

from guangzhu import api
from scripts import agh_export_run as exporter, agh_verify_run as verifier
from test_agh_runs import complete, resequence, reviewed_ledgers
from test_api import local


def evaluation_events():
    events = complete()
    removed = {e['data']['toolUseId'] for e in events if exporter.tool_name(e) in ('gz_export', 'gz_record_review')}
    return resequence([e for e in events if e['type'] not in ('approval/asked', 'approval/decided')
                       and e['data'].get('toolUseId', e['data'].get('tool', {}).get('toolUseId')) not in removed])


def append_tool(events, name='gz_analyze', *, version=2, what_if=False, ok=True, hard=0):
    template = next(e for e in events if exporter.tool_name(e) == name)
    call = copy.deepcopy(template)
    use_id = 'late-' + str(len(events))
    call['data'].update(toolUseId=use_id, args=dict(project_id='changzhou-demo', version=version))
    if what_if:
        call['data']['args']['what_if'] = {'capex_cny_per_w': 3}
    result = copy.deepcopy(next(e for e in events if e['type'] == 'tool/result'
                              and e['data']['toolUseId'] == template['data']['toolUseId']))
    result['data'].update(toolUseId=use_id, isError=not ok, content=[dict(type='text', text=json.dumps(
        dict(ok=ok, version=version, rules=dict(hard_failed=hard, failed=[]))))])
    return resequence(events + [call, result])


def test_no_export_preserves_other_three_stages():
    events = evaluation_events()
    actual = verifier.verify(events, no_export=True)
    assert actual['passed'] and actual['verified_exports'] == []
    assert actual['final_analysis']['version'] == 2
    assert actual['checks'][:3] == verifier.verify(complete())['checks'][:3]
    assert verifier.verify(events)['checks'][-1]['passed'] is False


@pytest.mark.parametrize('what_if,ok', [(False, False), (True, True), (True, False)])
def test_late_failed_or_what_if_analysis_does_not_replace_final(what_if, ok):
    events = evaluation_events()
    before = verifier.verify(events, no_export=True)
    events = append_tool(events, version=99, what_if=what_if, ok=ok, hard=1)
    actual = verifier.verify(events, no_export=True)
    assert actual['passed'] and actual['final_analysis'] == before['final_analysis']


def test_crosscheck_before_last_successful_analysis_is_not_final_proof():
    events = append_tool(evaluation_events())
    actual = verifier.verify(events, no_export=True)
    assert not actual['checks'][-1]['passed']
    assert actual['final_analysis']['analysis_seq'] == events[-1]['seq']
    assert verifier.verify(append_tool(events, 'gz_crosscheck_yield'), no_export=True)['passed']


@pytest.mark.parametrize('mutation', ['hard', 'hard-row', 'bool', 'version', 'missing', 'failed-crosscheck', 'duplicate'])
def test_final_proof_rejects_bad_rules_version_or_crosscheck(mutation):
    events = evaluation_events()
    final = exporter.final_analysis(events)
    result = final[1]
    value = exporter.result_value(result)
    if mutation == 'hard':
        value['rules']['hard_failed'] = 1
    elif mutation == 'hard-row':
        value['rules']['failed'] = [dict(id='G01', level='hard')]
    elif mutation == 'bool':
        value['rules']['hard_failed'] = False
    elif mutation == 'version':
        value['version'] = 3
    elif mutation == 'missing':
        value.pop('rules')
    elif mutation == 'failed-crosscheck':
        call = next(e for e in events if exporter.tool_name(e) == 'gz_crosscheck_yield')
        next(e for e in events if e['type'] == 'tool/result' and e['data']['toolUseId'] == call['data']['toolUseId'])['data']['isError'] = True
    else:
        events = resequence(events + [copy.deepcopy(result)])
    result['data']['content'][0]['text'] = json.dumps(value)
    assert verifier.verify(events, no_export=True)['passed'] is False


def test_lean_export_contains_only_final_summary_and_rules(tmp_path, monkeypatch):
    events = append_tool(append_tool(evaluation_events(), version=99, ok=False), version=88, what_if=True)
    monkeypatch.setenv('AGH_HOME', 'never-created')
    monkeypatch.setattr(exporter, 'export_ledger', lambda sid, path, executable: write_ledger(path, events))
    project = tmp_path / 'projects/changzhou-demo'
    for version in (1, 2, 88, 99):
        for name in ('summary', 'rules', 'shading', 'electrical'):
            exporter.write_json(project / f'analysis/v{version}/{name}.json', dict(version=version, kind=name))
        exporter.write_json(project / f'designs/v{version}.json', dict(version=version, parent_version=version-1 or None))
        exporter.write_json(project / f'reviews/v{version}-review.json', dict(version=version))
        exporter.write_json(project / f'exports/v{version}/manifest.json', dict(version=version, files={}))
    destination = tmp_path / 'runs/eval-1003/eval-1003-r01-C-1'
    exporter.export_run('fixture', 'changzhou-demo', destination.name, root=tmp_path, destination=destination, lean=True)
    meta = json.loads((destination / 'run.json').read_text(encoding='utf-8'))
    assert meta['lean'] and meta['final_version'] == 2
    assert meta['final_analysis'] == dict(version=2, summary='project/analysis/v2/summary.json', rules='project/analysis/v2/rules.json')
    assert set(meta['artifacts']) == {'project/analysis/v2/summary.json', 'project/analysis/v2/rules.json'}
    assert {p.relative_to(destination).as_posix() for p in destination.rglob('*') if p.is_file()} == {
        'ledger.agnes.jsonl', 'run.json', 'timeline.json', *meta['artifacts']}
    for relative, digest in meta['artifacts'].items():
        archived = destination / relative
        assert archived.read_bytes() == (project / relative.removeprefix('project/')).read_bytes()
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == digest
    assert exporter.read_events(destination / 'ledger.agnes.jsonl') == events


def write_ledger(path, events):
    path.write_text(''.join(json.dumps(row) + '\n' for row in events), encoding='utf-8')
    return events


def test_cli_no_export_uses_native_ledger(tmp_path):
    write_ledger(tmp_path / 'ledger.agnes.jsonl', evaluation_events())
    assert verifier.main([str(tmp_path), '--no-export']) == 0
    result = json.loads((tmp_path / 'verification.json').read_text(encoding='utf-8'))
    assert result['passed'] and result['final_analysis']['version'] == 2
    assert verifier.main([str(tmp_path)]) == 1


def test_lean_finish_retry_can_complete_an_interrupted_native_export(tmp_path, monkeypatch):
    events, calls = evaluation_events(), []
    monkeypatch.setenv('AGH_HOME', 'never-created')
    def native_export(sid, path, executable):
        calls.append(sid)
        write_ledger(path, events)
        if len(calls) == 1:
            raise OSError('interrupted native export')
        return events
    monkeypatch.setattr(exporter, 'export_ledger', native_export)
    destination = tmp_path / 'runs/eval-1003/eval-1003-r01-C-1'
    arguments = dict(root=tmp_path, destination=destination, lean=True)
    with pytest.raises(OSError):
        exporter.export_run('fixture', 'changzhou-demo', destination.name, **arguments)
    before = (destination / 'ledger.agnes.jsonl').read_bytes()
    exporter.export_run('fixture', 'changzhou-demo', destination.name, **arguments)
    assert before == (destination / 'ledger.agnes.jsonl').read_bytes()
    assert calls == ['fixture', 'fixture'] and (destination / 'run.json').exists()
    with pytest.raises(FileExistsError):
        exporter.export_run('fixture', 'changzhou-demo', destination.name, **arguments)


def test_lean_export_preserves_and_reports_unexpected_native_child(tmp_path, monkeypatch):
    parent, child = reviewed_ledgers()
    sid, child_id = parent[0]['data']['key'], exporter.own_events(child)[0]['data']['key']
    cost = copy.deepcopy(parent[0])
    cost.update(type='subagent/cost', data=dict(childKey=child_id), origin='system', trust='trusted')
    parent = resequence(parent + [cost])
    monkeypatch.setenv('AGH_HOME', 'never-created')
    def native_export(session, path, executable, **kwargs):
        return write_ledger(path, child if session == child_id else parent)
    monkeypatch.setattr(exporter, 'export_ledger', native_export)
    folder = exporter.export_run(sid, 'changzhou-demo', 'eval-1003-r01-C-1', root=tmp_path, with_children=True, lean=True)
    meta = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    assert len(meta['children']) == 1 and meta['children_complete'] is True
    assert any(row.get('session') == child_id and '越界' in row['message'] for row in meta['anomalies'])
    ledger = folder / meta['children'][0]['ledger']
    assert exporter.read_events(ledger, inherited=True) == child
    assert not list((folder / 'project').rglob('*.json'))
    assert verifier.main([str(folder), '--no-export']) == 1


def test_api_evaluation_uses_finish_path_and_preserves_lean_archive(local, monkeypatch):
    client, root, project, events, calls = local
    project_id = 'eval-1003-r01-C-1'
    target = project.with_name(project_id)
    shutil.copytree(project, target)
    events[:] = evaluation_events()
    events[0]['data']['key'] = 'design-session'
    for event in events:
        if exporter.tool_name(event):
            event['data']['args']['project_id'] = project_id
    monkeypatch.setattr(api, 'snapshot_scene', lambda *args: pytest.fail('evaluation cannot archive scene'))
    monkeypatch.setattr(api, 'make_report', lambda *args: pytest.fail('evaluation cannot generate report'))
    payload = dict(project_id=project_id, session_id='design-session', evaluation=True)
    response = client.post('/api/runs/finish', json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['archive_path'] == f'runs/eval-1003/{project_id}' and body['session_id'] == 'design-session'
    assert body['selected_version'] == 2 and body['verification']['passed'] and body['review_prompt'] is None
    folder = root / body['archive_path']
    assert {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()} == {
        'ledger.agnes.jsonl', 'run.json', 'verification.json', 'timeline.json',
        'project/analysis/v2/summary.json', 'project/analysis/v2/rules.json'}
    assert not (root / ('runs/gz-' + project_id)).exists()
    before = {p: p.read_bytes() for p in folder.rglob('*') if p.is_file()}
    assert client.post('/api/runs/finish', json=payload).json() == body
    assert calls == ['design-session'] and before == {p: p.read_bytes() for p in before}
    assert client.get('/api/runs').json()['runs'][0]['selected_version'] == 2
    shutil.rmtree(target)
    archived = client.get('/api/runs/' + project_id)
    assert archived.status_code == 200 and archived.json()['result']['summary']['version'] == 2
    assert archived.json()['result']['rules'] == {'items': []}


def test_api_evaluation_rejects_unsafe_id_and_independent_review(local):
    client, _, _, _, calls = local
    for payload in (dict(project_id='plain', session_id='design-session', evaluation=True),
                    dict(project_id='eval-1003-r01-C-1', session_id='design-session', evaluation=True, review_session_id='review-session')):
        assert client.post('/api/runs/finish', json=payload).status_code == 400
    assert calls == []
