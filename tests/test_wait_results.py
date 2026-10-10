"""Transport association adversaries; all evidence and output are synthetic and local."""
import copy
from datetime import datetime, timedelta, timezone
import json
import subprocess

import pytest

from guangzhu import api
from scripts import agh_export_run as exporter, agh_verify_run as verifier
from test_agh_runs import complete, independent_review, resequence, reviewed_ledgers
from test_api import local, payload
from test_eval_score import fixture, case, scorer, jsonl


def content(event, value):
    event['data']['content'] = [dict(type='text', text=json.dumps(value, ensure_ascii=False))]


def asynchronous(events, names):
    events = copy.deepcopy(events)
    calls = {e['data']['toolUseId']: e for e in events if e['type'] == 'tool/call'}
    output = []
    for event in events:
        output.append(event)
        call = calls.get(event['data'].get('toolUseId'))
        if event['type'] != 'tool/result' or not call or exporter.tool_name(call) not in names:
            continue
        name, use = exporter.tool_name(call), call['data']['toolUseId']
        job = 'job-' + use
        pending = dict(ok=True, pending=True, job_id=job, tool=name)
        final = copy.deepcopy(event)
        content(final, exporter.result_value(event) | dict(tool=name, job_id=job))
        content(event, pending)
        for index in range(2):
            wait = copy.deepcopy(call)
            wait['data'].update(name='gz_wait', toolUseId=f'wait-{use}-{index}', args=dict(job_id=job))
            result = copy.deepcopy(event if index == 0 else final)
            result['data']['toolUseId'] = wait['data']['toolUseId']
            output += [wait, result]
    return resequence(output)


def small():
    events = complete()
    call = next(e for e in events if exporter.tool_name(e) == 'gz_analyze')
    result = next(e for e in events if e['type'] == 'tool/result' and e['data']['toolUseId'] == call['data']['toolUseId'])
    return asynchronous(resequence([events[0], call, result]), {'gz_analyze'})


def test_transport_is_pure_preserves_originals_and_four_steps():
    events = complete()
    call = copy.deepcopy(next(e for e in events if exporter.tool_name(e) == 'gz_analyze'))
    call['data'].update(name='gz_compare_options', toolUseId='compare', args=dict(project_id='changzhou-demo', version=2))
    result = copy.deepcopy(next(e for e in events if e['type'] == 'tool/result'))
    result['data']['toolUseId'] = 'compare'
    content(result, dict(ok=True, base_version=2, options=[dict(version=3), dict(version=4)]))
    events = asynchronous(resequence(events + [call, result]), {'gz_compare_options', 'gz_export'})
    before = copy.deepcopy(events)
    rows, unknown = exporter.resolve_results(events)
    assert not unknown and events == before
    result = verifier.verify(events)
    assert result['passed'] and all(c['passed'] for c in result['checks'])
    for row in rows:
        if row['wait_ids']:
            assert row['initial']['seq'] < row['result']['seq'] and not row['pending']
            assert 'tool' not in row['value'] and 'job_id' not in row['value']
            assert exporter.result_value(row['result'])['tool'] == row['name']


@pytest.mark.parametrize('attack', ['job', 'tool', 'args', 'sequence', 'session', 'duplicate_call', 'duplicate_result',
                                   'different_args', 'conflict', 'bad_pending', 'error_pending', 'no_origin', 'missing_result'])
def test_invalid_transport_never_selects_a_success(attack):
    events = small()
    original, pending, wait, progress, final_call, final = events[1:]
    if attack in ('job', 'tool'):
        content(final, exporter.result_value(final) | {attack if attack == 'tool' else 'job_id': 'wrong'})
    elif attack == 'args':
        final_call['data']['args']['job_id'] = 'wrong'
    elif attack == 'sequence':
        final['seq'] = final_call['seq'] - 1
    elif attack == 'session':
        start = copy.deepcopy(events[0])
        start['data']['key'] = 'foreign'
        events.insert(5, start)
        events = resequence(events)
    elif attack.startswith('duplicate_'):
        events.append(copy.deepcopy(original if attack == 'duplicate_call' else pending))
        events = resequence(events)
    elif attack == 'different_args':
        retry, response = copy.deepcopy(original), copy.deepcopy(pending)
        retry['data']['toolUseId'] = response['data']['toolUseId'] = 'retry'
        retry['data']['args']['version'] = 99
        events = resequence(events[:3] + [retry, response] + events[3:])
    elif attack == 'conflict':
        retry, response = copy.deepcopy(final_call), copy.deepcopy(final)
        retry['data']['toolUseId'] = response['data']['toolUseId'] = 'conflict'
        content(response, exporter.result_value(response) | dict(version=99))
        events = resequence(events + [retry, response])
    elif attack == 'bad_pending':
        content(pending, exporter.result_value(pending) | dict(ok=False))
    elif attack == 'error_pending':
        pending['data']['isError'] = True
    elif attack == 'no_origin':
        events = resequence([events[0]] + events[3:])
    else:
        events.remove(progress)
    rows, unknown = exporter.resolve_results(events)
    assert unknown and not any(r['result'] for r in rows)
    assert exporter.final_analysis(events) is None


def test_pending_is_neither_success_nor_tool_failure():
    events = small()[:-2]
    rows, unknown = exporter.resolve_results(events)
    assert not unknown and rows[0]['pending'] and rows[0]['result'] is None
    verification = verifier.verify(events)
    assert verification['pending_calls'] and verification['failed_call_count'] == 0
    assert not verification['passed']


def test_same_args_retries_and_identical_reads_reuse_job():
    events = small()
    retry, pending = copy.deepcopy(events[1]), copy.deepcopy(events[2])
    retry['data']['toolUseId'] = pending['data']['toolUseId'] = 'retry'
    wait, result = copy.deepcopy(events[-2]), copy.deepcopy(events[-1])
    wait['data']['toolUseId'] = result['data']['toolUseId'] = 'reread'
    events = resequence(events[:3] + [retry, pending] + events[3:] + [wait, result])
    rows, unknown = exporter.resolve_results(events)
    assert not unknown and len(rows) == 2
    assert rows[0]['result'] is rows[1]['result'] and len(rows[0]['wait_ids']) == 3
    assert rows[0]['initial'] is not rows[1]['initial']


def test_duplicated_pending_cannot_hide_behind_valid_same_job_retry():
    events = small()
    retry, pending = copy.deepcopy(events[1]), copy.deepcopy(events[2])
    retry['data']['toolUseId'] = pending['data']['toolUseId'] = 'retry'
    events = resequence(events[:3] + [copy.deepcopy(events[2]), retry, pending] + events[3:])
    rows, unknown = exporter.resolve_results(events)
    assert unknown and all(r['result'] is None for r in rows)


@pytest.mark.parametrize('duplicate', ['formal_pending', 'pending_formal', 'pending_other_job', 'wait_hidden_job'])
def test_every_duplicate_result_job_poisons_conflicting_originals(duplicate):
    events = small()
    start, original, pending, wait, progress, final_call, final = events
    retry, response = copy.deepcopy(original), copy.deepcopy(pending)
    retry['data']['toolUseId'] = response['data']['toolUseId'] = 'different-version'
    retry['data']['args']['version'] = 99
    content(final, exporter.result_value(final) | dict(version=99))
    other = copy.deepcopy(pending)
    content(other, exporter.result_value(other) | dict(job_id='other-job'))
    formal = copy.deepcopy(pending)
    content(formal, dict(ok=True, version=1))
    if duplicate == 'wait_hidden_job':
        wait['data']['args']['job_id'] = 'other-job'
        content(progress, exporter.result_value(progress) | dict(job_id='other-job'))
        hidden = copy.deepcopy(progress)
        content(hidden, exporter.result_value(hidden) | dict(job_id=exporter.result_value(pending)['job_id']))
        prefix = [original, other, wait, progress, hidden]
    else:
        duplicates = dict(formal_pending=[formal, pending], pending_formal=[pending, formal], pending_other_job=[other, pending])
        prefix = [original, *duplicates[duplicate]]
    events = resequence([start, *prefix, retry, response, final_call, final])
    before = copy.deepcopy(events)
    rows, unknown = exporter.resolve_results(events)
    assert events == before and unknown
    assert len(rows) == 2 and all(r['result'] is None for r in rows)
    assert exporter.final_analysis(events) is None


def test_failed_formal_wait_keeps_native_error():
    events = small()
    events[-1]['data']['isError'] = True
    content(events[-1], dict(ok=False, error_code='FAILED', tool='gz_analyze', job_id='job-' + events[1]['data']['toolUseId']))
    rows, unknown = exporter.resolve_results(events)
    assert not unknown and not rows[0]['pending'] and rows[0]['result']['data']['isError'] is True
    assert exporter.final_analysis(events) is None
    assert verifier.verify(events)['failed_calls'][0]['error_code'] == 'FAILED'


@pytest.mark.parametrize('approval', ['original', 'wait_only', 'late'])
def test_export_approval_uses_initial_execution_boundary(approval):
    events = asynchronous(complete(), {'gz_export'})
    export = next(r for r in exporter.resolve_results(events)[0] if r['name'] == 'gz_export')
    ask = next(e for e in events if e['type'] == 'approval/asked')
    decision = next(e for e in events if e['type'] == 'approval/decided')
    events = [e for e in events if e['type'] != 'effect/intent']
    if approval == 'wait_only':
        ask['data']['toolUseId'] = export['wait_ids'][0]
    elif approval == 'late':
        events.remove(ask)
        events.remove(decision)
        index = events.index(export['initial']) + 1
        events[index:index] = [ask, decision]
    assert verifier.verify(resequence(events))['passed'] is (approval == 'original')


def test_independent_review_waits_and_unknown_waits():
    review = asynchronous(independent_review(), {'gz_analyze', 'gz_record_review'})
    for event in review:
        event['ts'] = event['ts'].replace('T00:', 'T01:')
    assert verifier.verify(complete(), reviews=[review])['review']['passed']
    orphan = copy.deepcopy(next(e for e in review if exporter.tool_name(e) == 'gz_wait'))
    orphan['data'].update(toolUseId='orphan', args=dict(job_id='unknown'))
    assert not verifier.verify(complete(), reviews=[resequence(review + [orphan])])['review']['passed']


def test_child_review_and_parent_record_can_wait():
    parent, child = reviewed_ledgers()
    parent = asynchronous(parent, {'gz_record_review'})
    child = asynchronous(child, {'gz_analyze'})
    assert verifier.verify(parent, children=[child])['review']['passed']


@pytest.mark.parametrize('name', ['gz_project_summary', 'gz_analyze', 'gz_record_review'])
def test_independent_review_may_repeat_read_only_queries_but_saves_once(name):
    # T20: a reviewer that checks a number twice is still a valid review; saving two verdicts is not.
    review = independent_review()
    call = copy.deepcopy(next(e for e in review if exporter.tool_name(e) == name))
    result = copy.deepcopy(next(e for e in review if e['type'] == 'tool/result'
                               and e['data']['toolUseId'] == call['data']['toolUseId']))
    call['data']['toolUseId'] = result['data']['toolUseId'] = 'extra-' + name
    review += [call, result]
    review = resequence(review)
    for event in review:
        event['ts'] = event['ts'].replace('T00:', 'T01:')
    outcome = verifier.verify(complete(), reviews=[review])['review']
    assert outcome['passed'] is (name != 'gz_record_review')
    assert outcome['independent'][0]['extra_read_only_calls'] == (name != 'gz_record_review')
    if name == 'gz_record_review':
        assert outcome['reason'] == '审核意见保存了不止一次'


def test_independent_review_failure_names_the_missing_query_and_foreign_tool():
    review = independent_review()
    use = next(e['data']['toolUseId'] for e in review if exporter.tool_name(e) == 'gz_crosscheck_yield')
    review = [e for e in review if e['data'].get('toolUseId') != use]
    assert verifier.verify(complete(), reviews=[review])['review']['reason'] == '缺少必需的查询：' + verifier.TOOL_NAMES_ZH['gz_crosscheck_yield']
    review = independent_review()
    next(e for e in review if exporter.tool_name(e) == 'gz_analyze')['data']['name'] = 'mcp_guangzhu_1234abcd_gz_edit_design'
    assert '用了审核不允许的工具：gz_edit_design' in verifier.verify(complete(), reviews=[review])['review']['reason']


def test_api_finish_snapshot_and_legacy_pending(local):
    client, root, _, events, _ = local
    events[:] = asynchronous(events, {'gz_export', 'gz_analyze'})
    response = client.post('/api/runs/finish', json=payload())
    assert response.status_code == 200, response.text
    assert response.json()['verification']['passed']
    folder = root / 'runs/gz-changzhou-demo'
    values = api.full_results(folder)
    assert api.tool_result(values, 'gz_export', 2)['ok']
    assert all(n['name'] != 'gz_wait' for n in values)
    legacy = [dict(kind='tool', name='gz_export', result=json.dumps(dict(ok=True, version=2, pending=True)))]
    assert api.tool_result(legacy, 'gz_export', 2) is None
    legacy[0]['result'] = json.dumps(dict(ok=True, version=2))
    assert api.tool_result(legacy, 'gz_export', 2)['ok']


def test_snapshot_collects_wait_compare_candidates(local, tmp_path):
    _, root, project, _, _ = local
    events = small()
    for event in events:
        if event['type'] == 'tool/call' and exporter.tool_name(event) == 'gz_analyze':
            event['data']['name'] = 'gz_compare_options'
        if event['type'] == 'tool/result':
            value = exporter.result_value(event) | dict(tool='gz_compare_options')
            if not value.get('pending'):
                value = dict(ok=True, tool='gz_compare_options', job_id=value['job_id'], options=[dict(version=4)])
            content(event, value)
    anomalies = []
    hashes = exporter.snapshot(events, 'changzhou-demo', tmp_path / 'snapshot', project.parent, anomalies)
    assert 'project/designs/v4.json' in hashes and not anomalies


def test_completion_order_and_full_timeline_fields():
    events = small()
    later, result = copy.deepcopy(events[1]), copy.deepcopy(events[-1])
    later['data']['toolUseId'] = result['data']['toolUseId'] = 'later'
    content(result, dict(ok=True, version=2))
    events = resequence(events[:3] + [later, result] + events[3:])
    assert exporter.final_analysis(events)[0]['data']['toolUseId'] != 'later'
    nodes = exporter.timeline(events)['nodes']
    assert all({'args_json', 'result_json', 'tool_use_id', 'session', 'result_seq'} <= n.keys() for n in nodes if n['kind'] == 'tool')


def test_timeline_full_json_survives_display_clipping_and_approval_via():
    events = asynchronous(complete(), {'gz_export'})
    wait = next(e for e in events if exporter.tool_name(e) == 'gz_wait')
    result = next(e for e in events if e['type'] == 'tool/result' and e['data']['toolUseId'] == wait['data']['toolUseId'])
    content(result, exporter.result_value(result) | dict(stage='进度' * 1100))
    nodes = exporter.timeline(events)['nodes']
    node = next(n for n in nodes if n.get('tool_use_id') == wait['data']['toolUseId'])
    assert node['result_json']['stage'] == '进度' * 1100
    assert len(node['result'].encode()) <= 2048
    assert any(n.get('via') == 'sync' for n in nodes if n['kind'] == 'approval')


def test_timeline_approvals_retain_each_original_export_identity_and_sanitized_args():
    events = asynchronous(complete(), {'gz_export'})
    original = next(e for e in events if exporter.tool_name(e) == 'gz_export')
    original['data']['args'].update(secret='example-secret', label='Bearer private-credential')
    ask = next(e for e in events if e['type'] == 'approval/asked')
    decision = next(e for e in events if e['type'] == 'approval/decided')
    retry, retry_ask, retry_decision = copy.deepcopy(original), copy.deepcopy(ask), copy.deepcopy(decision)
    retry['data']['toolUseId'] = retry_ask['data']['toolUseId'] = 'export-version-99'
    retry['data']['args']['version'] = 99
    retry_ask['data']['requestId'] = retry_decision['data']['requestId'] = 'approval-version-99'
    events = resequence(events + [retry, retry_ask, retry_decision])
    nodes = [n for n in exporter.timeline(events)['nodes'] if n['kind'] == 'approval']
    for source in [original, retry]:
        approvals = [n for n in nodes if n.get('tool_use_id') == source['data']['toolUseId']]
        assert len(approvals) == 2 and {n['pending'] for n in approvals} == {True, False}
        assert all(n['args_json'] == exporter.sanitize(source['data']['args']) for n in approvals)
        assert all(n['tool'] == 'gz_export' and n['args_json']['label'] == '[REDACTED]' for n in approvals)
        assert all('secret' not in n['args_json'] for n in approvals)


def test_timeline_duplicate_result_claims_retain_every_job_and_actual_conflict_position():
    events = small()
    original = events[1]
    result = events[2]
    duplicate = copy.deepcopy(result)
    content(result, dict(ok=True, version=3))
    content(duplicate, dict(ok=True, pending=True, job_id='hidden-job', tool='gz_analyze'))
    events = resequence(events + [duplicate])
    node = next(n for n in exporter.timeline(events)['nodes'] if n.get('tool_use_id') == original['data']['toolUseId'])
    assert node['invalid_job_ids'] == ['hidden-job']
    assert node['conflict_seq'] == events[-1]['seq']
    assert node['conflict_at'] == events[-1]['ts']
    assert not node['invalid_jobs_truncated'] and node['result_json'] == {}


def test_timeline_duplicate_wait_claims_include_args_and_fail_closed_at_metadata_bound():
    events = small()
    wait = next(e for e in events if exporter.tool_name(e) == 'gz_wait')
    result = next(e for e in events if e['type'] == 'tool/result' and e['data']['toolUseId'] == wait['data']['toolUseId'])
    duplicates = []
    for index in range(66):
        duplicate = copy.deepcopy(result)
        content(duplicate, dict(ok=True, job_id=f'claimed-{index:02d}', tool='gz_analyze'))
        duplicates.append(duplicate)
    events = resequence(events + duplicates)
    node = next(n for n in exporter.timeline(events)['nodes'] if n.get('tool_use_id') == wait['data']['toolUseId'])
    assert len(node['invalid_job_ids']) == 64 and node['invalid_jobs_truncated']
    assert node['conflict_seq'] == events[-66]['seq']
    small_events = resequence(events[:7] + duplicates[:1])
    node = next(n for n in exporter.timeline(small_events)['nodes'] if n.get('tool_use_id') == wait['data']['toolUseId'])
    assert wait['data']['args']['job_id'] in node['invalid_job_ids']


@pytest.mark.parametrize('claims', [[None, None, 'job-target'], [None, *[f'claim-{i}' for i in range(65)]],
                                  [None, 'bounded', '长' * 43]])
def test_duplicate_negative_evidence_replays_only_at_native_claim_or_overflow(claims):
    source = small()
    original, initial, wait, final = copy.deepcopy([source[1], source[2], source[-2], source[-1]])
    content(initial, dict(ok=True, pending=True, job_id='job-target', tool='gz_analyze'))
    wait['data']['args']['job_id'] = 'job-target'
    content(final, dict(ok=True, job_id='job-target', tool='gz_analyze', version=3))
    unrelated = copy.deepcopy(original)
    unrelated['data'].update(toolUseId='unrelated', args={})
    duplicates = []
    for claim in claims:
        response = copy.deepcopy(initial)
        response['data']['toolUseId'] = 'unrelated'
        content(response, dict(ok=True, job_id=claim))
        duplicates.append(response)
    events = [source[0], original, initial, unrelated, duplicates[0], wait, final, *duplicates[1:]]
    sequences = [0, 1, 2, 3, 4, 5, 6, 9, *range(15, 15 + len(claims) - 2)]
    for event, seq in zip(events, sequences):
        event.update(seq=seq, id=f'{seq:026d}', ts=(datetime(2026, 10, 2, tzinfo=timezone.utc) + timedelta(seconds=seq)).isoformat())
    timeline = exporter.timeline(events)
    node = next(n for n in timeline['nodes'] if n.get('tool_use_id') == 'unrelated')
    assert 'invalid_job_events' in node
    milestones = node['invalid_job_events']
    assert len(milestones) <= 66
    assert all(e['seq'] in sequences[7:] for e in milestones)
    assert sum(len(e['job_ids']) for e in milestones) <= 64
    assert all(len(job.encode('utf-8')) <= 128 for e in milestones for job in e['job_ids'])
    assert len([e for e in milestones if e['truncated']]) <= 1
    if len(claims) == 3 and claims[-1] == 'job-target':
        assert milestones == [dict(seq=9, ts=events[7]['ts'], job_ids=[], truncated=False),
                              dict(seq=15, ts=events[-1]['ts'], job_ids=['job-target'], truncated=False)]
    else:
        assert milestones[-1]['truncated'] and milestones[-1]['seq'] == events[-1]['seq']
    script = '''
import {readFileSync} from 'node:fs';
import {replayEvents, projectReplay} from './desktop/web/replay.js';
import {resolvedTools} from './desktop/web/tool-results.js';
const timeline = JSON.parse(readFileSync(0, 'utf8'));
const events = replayEvents(timeline, timeline.nodes[0].session);
const states = events.map((event, i) => ({seq:event.at[1],
  pending:resolvedTools(projectReplay(events, i + 1).nodes).find(n => n.tool_use_id !== 'unrelated')?.pending}));
process.stdout.write(JSON.stringify({states, full:resolvedTools(timeline.nodes)[0].pending}));
'''
    result = subprocess.run(['node', '--input-type=module', '-e', script], input=json.dumps(timeline),
                            cwd=exporter.ROOT, text=True, capture_output=True, check=True)
    replay = json.loads(result.stdout)
    states = [state for state in replay['states'] if state['seq'] >= 6]
    assert states[-1]['seq'] == events[-1]['seq'] and states[-1]['pending']
    assert all(not state['pending'] for state in states[:-1])
    assert replay['full']
    assert exporter.resolve_results(events)[0][0]['pending'] == (claims[-1] == 'job-target')


def cancelled_wait(events):
    call, result = copy.deepcopy(events[-2]), copy.deepcopy(events[-1])
    call['data']['toolUseId'] = result['data']['toolUseId'] = 'cancelled-wait'
    result['data'].update(code='CANCELLED', isError=True, content=[dict(type='text', text='aborted: Request timed out')])
    return resequence(events[:-2] + [call, result] + events[-2:])


def test_native_cancelled_wait_is_interrupted_transport_and_later_completion_remains_owned():
    events = cancelled_wait(small())
    before = copy.deepcopy(events)
    rows, unknown = exporter.resolve_results(events)
    assert not unknown and events == before and not rows[0]['pending']
    assert rows[0]['result'] is events[-1]
    assert rows[0]['wait_ids'] == [e['data']['toolUseId'] for e in events if exporter.tool_name(e) == 'gz_wait']
    node = next(n for n in exporter.timeline(events)['nodes'] if n.get('tool_use_id') == 'cancelled-wait')
    assert node['result_code'] == 'CANCELLED' and node['status'] == 'error'
    rows, unknown = exporter.resolve_results(events[:-2])
    assert not unknown and rows[0]['pending'] and rows[0]['result'] is None


@pytest.mark.parametrize('attack', ['generic_error', 'wrong_args', 'wrong_result_job', 'wrong_tool', 'duplicate', 'not_error'])
def test_interrupted_transport_exception_never_accepts_ambiguous_or_incorrect_cancellation(attack):
    events = cancelled_wait(small())
    call, result = events[-4:-2]
    if attack == 'generic_error':
        result['data']['code'] = 'OTHER_ERROR'
    elif attack == 'wrong_args':
        call['data']['args']['job_id'] = 'orphan-job'
    elif attack == 'wrong_result_job':
        content(result, dict(job_id='wrong'))
    elif attack == 'wrong_tool':
        content(result, dict(tool='gz_export'))
    elif attack == 'duplicate':
        events = resequence(events + [copy.deepcopy(result)])
    else:
        result['data']['isError'] = False
    rows, unknown = exporter.resolve_results(events)
    assert rows[0]['pending'] or unknown


@pytest.mark.parametrize('identity', ['unknown', 'missing', 'call_after_ask', 'decision_before_ask', 'duplicate_call', 'duplicate_ask', 'wait'])
def test_timeline_approval_identity_never_guesses_an_export(identity):
    events = asynchronous(complete(), {'gz_export'})
    original = next(e for e in events if exporter.tool_name(e) == 'gz_export')
    ask = next(e for e in events if e['type'] == 'approval/asked')
    decision = next(e for e in events if e['type'] == 'approval/decided')
    if identity == 'unknown':
        ask['data']['toolUseId'] = 'missing-original'
    elif identity == 'missing':
        ask['data'].pop('toolUseId')
    elif identity == 'call_after_ask':
        events.remove(original)
        events.insert(events.index(ask) + 1, original)
    elif identity == 'decision_before_ask':
        events.remove(decision)
        events.insert(events.index(ask), decision)
    elif identity == 'duplicate_call':
        events.insert(events.index(ask), copy.deepcopy(original))
    elif identity == 'duplicate_ask':
        events.insert(events.index(decision), copy.deepcopy(ask))
    else:
        wait = next(e for e in events if exporter.tool_name(e) == 'gz_wait')
        ask['data']['toolUseId'] = wait['data']['toolUseId']
        events.remove(ask)
        events.remove(decision)
        events[events.index(wait) + 1:events.index(wait) + 1] = [ask, decision]
    nodes = [n for n in exporter.timeline(resequence(events))['nodes'] if n['kind'] == 'approval']
    if identity == 'wait':
        assert all(n.get('tool_use_id') == wait['data']['toolUseId'] and n['tool'] == 'gz_wait' for n in nodes)
        assert all(n.get('args_json') == wait['data']['args'] for n in nodes)
    else:
        unresolved = nodes if identity != 'decision_before_ask' else [n for n in nodes if not n['pending']]
        assert all(n.get('tool_use_id') is None and n.get('args_json') == {} for n in unresolved)


@pytest.mark.parametrize('method', ['C', 'D', 'E'])
def test_scoring_strips_transport_metadata_and_keeps_orphan_errors(tmp_path, method):
    attempt, directory = fixture(tmp_path, method=method)
    events = asynchronous(exporter.read_events(directory / 'ledger.agnes.jsonl'), {'gz_analyze'})
    jsonl(directory / 'ledger.agnes.jsonl', events)
    assert scorer.attempt_score(attempt, case(), tmp_path)['success']
    orphan = copy.deepcopy(next(e for e in events if exporter.tool_name(e) == 'gz_wait'))
    orphan['data'].update(toolUseId='orphan', args=dict(job_id='unknown'))
    jsonl(directory / 'ledger.agnes.jsonl', resequence(events + [orphan]))
    actual = scorer.attempt_score(attempt, case(), tmp_path)
    assert not actual['success'] and '等待结果无法关联原调用' in actual['environment_reasons']
