"""Synthetic verifier cases and the saved T09/008 timeline; no instance or model calls."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile

import pytest

from scripts import agh_export_run as exporter, agh_verify_run as verifier

FIXTURES = Path(__file__).parent / 'fixtures/ledger'
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def owned_directory():
    parent = ROOT / '.pytest_cache'
    parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='agh-runs-', dir=parent) as temporary:
        folder = Path(temporary).resolve()
        assert folder.is_relative_to(parent.resolve())
        yield folder
    assert not folder.exists()


def complete():
    return exporter.read_events(FIXTURES / '合成-完整.agnes.jsonl')


def resequence(events):
    events = copy.deepcopy(events)
    for seq, event in enumerate(events, 1):
        event.update(seq=seq, id=f'{seq:026d}', ts=f'2026-10-02T00:00:{seq:02d}Z')
    calls = {e['data']['toolUseId']: e['seq'] for e in events if e['type'] == 'tool/call'}
    for event in events:
        if event['type'] == 'effect/intent' and 'tool' in event['data']:
            event['data']['argsSeq'] = calls[event['data']['tool']['toolUseId']]
    return events


def reviewed_ledgers():
    parent = complete()
    record = next(e for e in parent if exporter.tool_name(e) == 'gz_record_review')
    record['data']['args']['reviewer_model'] = 'agnes-3.0-flash'
    result = next(e for e in parent if e['type'] == 'tool/result' and e['data']['toolUseId'] == record['data']['toolUseId'])
    fork, answer = copy.deepcopy(record), copy.deepcopy(result)
    fork['data'].update(name='subagent_fork', toolUseId='synthetic-fork', args=dict(question='项目 changzhou-demo，版本2。返回JSON', model='agnes-3.0-flash'))
    answer['data']['toolUseId'] = fork['data']['toolUseId']
    parent[parent.index(record):parent.index(record)] = [fork, answer]
    child = independent_review()
    child[0]['data'].update(key=parent[0]['data']['key'] + '/synthetic-child',
        parent=dict(key=parent[0]['data']['key'], boundarySeq=2),
        delegation=dict(kind='fork', creationId=f"{parent[0]['data']['key']}:main:synthetic-fork:1"))
    use = next(e['data']['toolUseId'] for e in child if exporter.tool_name(e) == 'gz_record_review')
    child = [e for e in child if e['data'].get('toolUseId') != use]
    message = copy.deepcopy(next(e for e in parent if e['type'] == 'assistant/message'))
    child.append(message)
    set_review(parent, child)
    return resequence(parent), resequence(parent[:2] + child)


def set_review(parent, child, verdict='approve', findings=(), fork_id='synthetic-fork', version=2):
    packet = dict(verdict=verdict, findings=list(findings))
    answer = next(e for e in parent if e['type'] == 'tool/result' and e['data']['toolUseId'] == fork_id)
    text = '审核结论。\n```json\n' + json.dumps(packet, ensure_ascii=False) + '\n```'
    answer['data']['content'] = [dict(type='text', text=text)]
    message = [e for e in child if e['type'] == 'assistant/message'][-1]
    message['data']['content'] = [dict(type='text', text=text)]
    record = next(e for e in parent[parent.index(answer)+1:] if exporter.tool_name(e) == 'gz_record_review')
    record['data']['args'].update(packet, version=version)
    result = next(e for e in parent if e['type'] == 'tool/result' and e['data']['toolUseId'] == record['data']['toolUseId'])
    result['data']['content'][0]['text'] = json.dumps(dict(ok=True, saved=True, version=version))


def corrected_review_ledgers():
    parent, final = reviewed_ledgers()
    first = next(e for e in parent if e['type'] == 'tool/call' and e['data']['name'] == 'subagent_fork')
    index = parent.index(first)
    block = parent[index:index+4]
    del parent[index:index+4]
    index = next(i for i,e in enumerate(parent) if exporter.tool_name(e) == 'gz_edit_design')
    parent[index:index] = block
    retry = copy.deepcopy(block)
    for event in retry:
        event['data']['toolUseId'] += '-retry'
    index = next(i for i,e in enumerate(parent) if exporter.tool_name(e) == 'gz_export')
    parent[index:index] = retry
    previous = copy.deepcopy(final)
    for call in (e for e in exporter.own_events(previous) if e['type'] == 'tool/call' and exporter.tool_name(e) != 'gz_project_summary'):
        call['data']['args']['version'] = 1
        result = next(e for e in previous if e['type'] == 'tool/result' and e['data']['toolUseId'] == call['data']['toolUseId'])
        result['data']['content'][0]['text'] = json.dumps(exporter.result_value(result) | dict(version=1))
    own = exporter.own_events(final)
    own[0]['data']['key'] += '-retry'
    own[0]['data']['delegation']['creationId'] = f"{parent[0]['data']['key']}:main:synthetic-fork-retry:1"
    set_review(parent, previous, 'revise', [dict(severity='high', item='E08', evidence='余件', suggestion='删除')], version=1)
    return resequence(parent), [previous, final]


def independent_review(version=2, offset=3600):
    original = complete()
    events = copy.deepcopy(original[:2])
    events[0]['data']['key'] = f'synthetic-independent-{version}'
    events[1]['data']['model'] = dict(route='synthetic', id='agnes-3.0-flash')
    for name in ('gz_project_summary', 'gz_analyze', 'gz_crosscheck_yield', 'gz_record_review'):
        call = copy.deepcopy(next(e for e in original if exporter.tool_name(e) == name))
        result = copy.deepcopy(next(e for e in original if e['type'] == 'tool/result' and e['data']['toolUseId'] == call['data']['toolUseId']))
        if name != 'gz_project_summary':
            call['data']['args']['version'] = version
        if name == 'gz_record_review':
            call['data']['args']['reviewer_model'] = 'agnes-3.0-flash'
        result['data']['content'][0]['text'] = json.dumps(exporter.result_value(result) | dict(version=version))
        events += [call, result]
    events = resequence(events)
    for event in events:
        event['ts'] = (datetime(2026, 10, 2, tzinfo=timezone.utc) + timedelta(seconds=offset + event['seq'])).isoformat()
    return events


def independent_correction():
    parent, first = complete(), independent_review(1, 13)
    record = next(e for e in first if exporter.tool_name(e) == 'gz_record_review')
    record['data']['args'].update(verdict='revise', findings=[dict(severity='high', item='E08', evidence='余件', suggestion='删除')])
    for event in parent:
        if event['seq'] >= 14:
            event['ts'] = f"2026-10-02T00:01:{event['seq']:02d}Z"
    return parent, [first, independent_review()]


def recovery_ledgers():
    original = complete()
    layout = next(e for e in original if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_generate_layout')
    layout_result = next(e for e in original if e['type'] == 'tool/result' and e['data']['toolUseId'] == layout['data']['toolUseId'])
    wrong, failed = copy.deepcopy(layout), copy.deepcopy(layout_result)
    wrong['data'].update(toolUseId='synthetic-invalid-layout', args=dict(project_id='../wrong', params=dict(tilt_deg=99)))
    failed['data'].update(toolUseId='synthetic-invalid-layout', isError=True, content=[dict(type='text', text=json.dumps(
        dict(ok=False, error_code='INPUT_INVALID', message_zh='合成参数错误', fix_hint='合成测试重试')))])
    index = original.index(layout)
    retry = original[:index] + [wrong, failed] + original[index:]
    analyses = [e for e in original if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_analyze']
    question = copy.deepcopy(analyses[-1])
    question['data'].update(toolUseId='synthetic-after-export', args=dict(project_id='changzhou-demo', version=2, what_if=dict(price_change_pct=-10)))
    answer = copy.deepcopy(next(e for e in original if e['type'] == 'tool/result' and e['data']['toolUseId'] == analyses[-1]['data']['toolUseId']))
    value = exporter.result_value(answer) | dict(what_if=dict(saved=False, hard_failed=1))
    answer['data'].update(toolUseId='synthetic-after-export', content=[dict(type='text', text=json.dumps(value))])
    after = original[:-2] + [question, answer] + original[-2:]
    export_call = next(e for e in original if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_export')
    timed = copy.deepcopy(export_call)
    timed['data']['toolUseId'] = 'synthetic-timeout-export'
    ask = copy.deepcopy(next(e for e in original if e['type'] == 'approval/asked'))
    ask['data'].update(requestId='synthetic-timeout-approval', toolUseId='synthetic-timeout-export')
    decision = copy.deepcopy(next(e for e in original if e['type'] == 'approval/decided'))
    decision['data'].update(requestId='synthetic-timeout-approval', verdict='rejected', via='timeout')
    refusal = copy.deepcopy(failed)
    refusal['data'].update(toolUseId='synthetic-timeout-export', code='APPROVAL_REJECTED', content=[dict(type='text', text='合成审批超时拒绝')])
    index = original.index(export_call)
    timeout = original[:index] + [timed, ask, decision, refusal] + original[index:]
    return {name: resequence(events) for name, events in zip(('合成-参数重试', '合成-导出后追问', '合成-超时重试'), (retry, after, timeout))}


@pytest.mark.parametrize('name,passed,reason', [
    ('合成-完整', True, ''),
    ('合成-缺反馈', False, '对应建议或规则编号'),
    ('合成-缺批准', False, '人工单次批准'),
    ('合成-最终失败', False, '最终硬性规则未全部通过'),
])
def test_four_synthetic_ledgers(name, passed, reason):
    result = verifier.verify(exporter.read_events(FIXTURES / (name + '.agnes.jsonl')))
    assert result['passed'] is passed
    assert any(reason in c['reason'] for c in result['checks'])


def test_verify_cli_writes_chinese_evidence_and_original_order(owned_directory, capsys):
    ledger = owned_directory / 'ledger.agnes.jsonl'
    ledger.write_bytes((FIXTURES / '合成-完整.agnes.jsonl').read_bytes())
    assert verifier.main([str(owned_directory)]) == 0
    assert '任务规划 | 通过' in capsys.readouterr().out
    assert json.loads((owned_directory / 'verification.json').read_text(encoding='utf-8'))['passed']
    result = verifier.verify(exporter.read_events(ledger))
    assert result['feedback_sequences'] == [[13, 14]]


def test_plan_after_initial_project_query_before_saving_requirements_is_accepted():
    events = complete()
    plan = next(e for e in events if e['type'] == 'assistant/message')
    events.remove(plan)
    index = next(i for i, e in enumerate(events) if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_set_requirements')
    events.insert(index, plan)
    result = verifier.verify(resequence(events))
    assert result['passed'] and result['checks'][0]['passed']


def test_new_project_then_summary_then_plan_is_preparation():
    events = complete()
    summary = next(e for e in events if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_project_summary')
    answer = next(e for e in events if e['type'] == 'tool/result' and e['data']['toolUseId'] == summary['data']['toolUseId'])
    new, created = copy.deepcopy(summary), copy.deepcopy(answer)
    new['data'].update(toolUseId='synthetic-new', name='mcp_guangzhu_1234abcd_gz_new_project',
                       args=dict(project_id='changzhou-demo', template='changzhou-demo'))
    created['data'].update(toolUseId='synthetic-new', content=[dict(type='text', text=json.dumps(dict(ok=True, created=True, project_id='changzhou-demo')))])
    plan = next(e for e in events if e['type'] == 'assistant/message')
    events.remove(plan)
    index = events.index(summary)
    events[index:index] = [new, created]
    index = next(i for i, e in enumerate(events) if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_set_requirements')
    events.insert(index, plan)
    assert verifier.verify(resequence(events))['passed']
    new['data']['args']['project_id'] = 'another-project'
    assert '工具链的项目编号不一致' in verifier.verify(resequence(events))['errors']


@pytest.mark.parametrize('early_tool', ['gz_set_requirements', 'gz_fetch_weather', 'gz_generate_layout',
                                      'gz_edit_design', 'gz_compare_options', 'gz_record_review', 'gz_export'])
@pytest.mark.parametrize('failed_attempt', [False, True])
def test_weather_or_any_write_before_plan_is_rejected_even_if_attempt_fails(early_tool, failed_attempt):
    events = complete()
    plan = next(e for e in events if e['type'] == 'assistant/message')
    events.remove(plan)
    source = next(e for e in events if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_set_requirements')
    early = copy.deepcopy(source)
    early['data'].update(toolUseId='synthetic-before-plan', name='mcp_guangzhu_1234abcd_' + early_tool)
    answer = copy.deepcopy(next(e for e in events if e['type'] == 'tool/result' and e['data']['toolUseId'] == source['data']['toolUseId']))
    answer['data'].update(toolUseId='synthetic-before-plan', isError=failed_attempt,
                          content=[dict(type='text', text=json.dumps(dict(ok=not failed_attempt)))])
    index = events.index(source)
    result = verifier.verify(resequence(events[:index] + [early, answer, plan] + events[index:]))
    assert not result['passed'] and not result['checks'][0]['passed']


def test_plan_after_requirements_cannot_retroactively_cover_work():
    events = complete()
    plan = next(e for e in events if e['type'] == 'assistant/message')
    events.remove(plan)
    index = next(i for i, e in enumerate(events) if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_fetch_weather')
    events.insert(index, plan)
    assert not verifier.verify(resequence(events))['checks'][0]['passed']


@pytest.mark.parametrize('change', ['wrong_tool', 'old_request', 'guardian', 'session', 'after_execution', 'error', 'different_version'])
def test_export_approval_and_result_must_be_real_bound_events(change):
    events = complete()
    ask = next(e for e in events if e['type'] == 'approval/asked')
    decision = next(e for e in events if e['type'] == 'approval/decided')
    effect = next(e for e in events if e['type'] == 'effect/intent')
    export = next(e for e in events if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_export')
    if change == 'wrong_tool':
        ask['data']['toolUseId'] = 'synthetic-other-tool'
    elif change == 'old_request':
        decision['data']['requestId'] = 'synthetic-other-approval'
    elif change == 'guardian':
        decision['data']['via'] = 'guardian'
    elif change == 'session':
        decision['data']['verdict'] = 'allowed-session'
    elif change == 'after_execution':
        decision['seq'] = effect['seq'] + 1
    elif change == 'different_version':
        export['data']['args']['version'] = 1
    else:
        next(e for e in events if e['type'] == 'tool/result' and e['data']['toolUseId'] == export['data']['toolUseId'])['data']['isError'] = True
    assert not verifier.verify(events)['passed']


def test_separate_review_session_is_not_required_in_design_ledger():
    events = complete()
    review_id = next(e['data']['toolUseId'] for e in events if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_record_review')
    events = [e for e in events if e['data'].get('toolUseId') != review_id]
    assert verifier.verify(events)['passed']


def test_child_review_uses_own_agnes_requests_and_keeps_four_stages():
    parent, child = reviewed_ledgers()
    result = verifier.verify(parent, children=[child])
    assert result['passed'] and result['review']['passed']
    assert len(result['checks']) == 4
    assert result['review']['children'][0]['model'] == 'agnes-3.0-flash'
    assert result['review']['children'][0]['json_unchanged'] is True
    assert result['review']['children'][0]['actual_model_verified'] is True


def test_missing_plan_is_rejected():
    result = verifier.verify([e for e in complete() if e['type'] != 'assistant/message'])
    assert not result['passed'] and not result['checks'][0]['passed']


def test_without_child_ledger_parent_json_cannot_pass_actual_review():
    parent, _ = reviewed_ledgers()
    verified = verifier.verify(parent)
    result = verified['review']
    assert not verified['passed'] and not result['passed']
    assert result['children'][0]['json_unchanged'] is True
    assert result['children'][0]['actual_model_verified'] is False


@pytest.mark.parametrize('change', ['verdict', 'one_character', 'trailing_text', 'duplicate_key', 'wrong_shape', 'child_json', 'duplicate_read', 'extra_write'])
def test_child_json_is_valid_unchanged_and_three_reads_exactly_once(change):
    parent, child = reviewed_ledgers()
    set_review(parent, child, findings=[dict(severity='medium', item='经济', evidence='电价0.65元', suggestion='现场核实')])
    record = next(e for e in parent if exporter.tool_name(e) == 'gz_record_review')
    answer = next(e for e in parent if e['type'] == 'tool/result' and e['data']['toolUseId'] == 'synthetic-fork')
    if change == 'verdict':
        record['data']['args']['verdict'] = 'revise'
    elif change == 'one_character':
        record['data']['args']['findings'][0]['evidence'] = '电价0.66元'
    elif change == 'trailing_text':
        answer['data']['content'][0]['text'] += '\n额外内容'
    elif change == 'duplicate_key':
        answer['data']['content'][0]['text'] = answer['data']['content'][0]['text'].replace('"verdict":', '"verdict":"revise","verdict":')
    elif change == 'wrong_shape':
        answer['data']['content'][0]['text'] = '结论\n```json\n{"verdict":"approve","findings":"none"}\n```'
    elif change == 'child_json':
        message = [e for e in child if e['type'] == 'assistant/message'][-1]
        message['data']['content'][0]['text'] = message['data']['content'][0]['text'].replace('0.65', '0.66')
    else:
        extra = copy.deepcopy(next(e for e in exporter.own_events(child) if exporter.tool_name(e) == 'gz_project_summary'))
        result = copy.deepcopy(next(e for e in child if e['type'] == 'tool/result' and e['data']['toolUseId'] == extra['data']['toolUseId']))
        extra['data']['toolUseId'] = result['data']['toolUseId'] = 'extra'
        if change == 'extra_write':
            extra['data']['name'] = 'gz_record_review'
        child = resequence(child + [extra, result])
    assert not verifier.verify(parent, children=[child])['review']['passed']


@pytest.mark.parametrize('change', [None, 'selected_route', 'actual_route', 'missing_fork'])
def test_native_inbox_brief_model_is_authoritative_including_route(change):
    parent, child = reviewed_ledgers()
    model = 'synthetic/agnes-3.0-flash'
    fork = next(e for e in parent if e['data'].get('name') == 'subagent_fork')
    fork['data']['args']['model'] = 'other/agnes-3.0-flash' if change == 'selected_route' else model
    next(e for e in parent if exporter.tool_name(e) == 'gz_record_review')['data']['args']['reviewer_model'] = model
    inbox = copy.deepcopy(parent[1])
    inbox['type'] = 'inbox'
    inbox['data'] = dict(items=[dict(content=[dict(type='text', text='【光筑任务书】\n```json\n' + json.dumps(
        dict(brief='guangzhu.brief/1', run=dict(review=dict(enabled=True, model=model)))) + '\n```')])])
    parent.insert(2, inbox)
    if change == 'actual_route':
        next(e for e in exporter.own_events(child) if e['type'] == 'request/sent')['data']['model']['route'] = 'other'
    if change == 'missing_fork':
        parent = [e for e in parent if e['data'].get('toolUseId') != fork['data']['toolUseId']]
        child = None
    result = verifier.verify(resequence(parent), children=[child] if child else [])
    assert result['review']['passed'] is (change is None)


def test_unusable_json_can_retry_once_but_cannot_be_recorded_or_pass_alone():
    parent, children = corrected_review_ledgers()
    first = next(e for e in parent if e['type'] == 'tool/result' and e['data'].get('toolUseId') == 'synthetic-fork')
    first['data']['content'][0]['text'] = '审核完成，但没有JSON'
    message = [e for e in children[0] if e['type'] == 'assistant/message'][-1]
    message['data']['content'][0]['text'] = first['data']['content'][0]['text']
    record = next(e for e in parent if exporter.tool_name(e) == 'gz_record_review')
    assert not verifier.verify(parent, children=children)['review']['passed']
    parent = [e for e in parent if e['data'].get('toolUseId') != record['data']['toolUseId']]
    result = verifier.verify(resequence(parent), children=children)['review']
    assert result['passed'] and result['children'][0]['retryable']
    parent = [e for e in parent if not e['data'].get('toolUseId', '').endswith('-retry')]
    assert not verifier.verify(parent, children=children[:1])['review']['passed']


def test_independent_review_after_export_is_explicit_and_keeps_four_stages():
    result = verifier.verify(complete(), reviews=[independent_review()])
    assert result['passed'] and len(result['checks']) == 4
    assert result['review']['mode'] == 'independent' and result['review']['children'] == []
    assert result['review']['independent'][0]['model'] == 'agnes-3.0-flash'


def test_legacy_t09_review_without_declared_fallback_mode_can_precede_export():
    assert verifier.verify(complete(), reviews=[independent_review(offset=22)])['passed']


@pytest.mark.parametrize('kind', ['user/message', 'inbox'])
@pytest.mark.parametrize('stage', ['failed', 'design', 'reviewed', 'reviewed_before_export', 'reviewed_at_export', 'untrusted'])
def test_declared_independent_mode_survives_failure_and_waiting_for_audit(kind, stage):
    from guangzhu.brief import render_brief
    parent = complete()[:2] if stage == 'failed' else complete()
    message = copy.deepcopy(parent[1])
    message['type'] = kind
    message['trust'] = 'untrusted' if stage == 'untrusted' else 'trusted'
    content = dict(content=[dict(type='text', text=render_brief(dict(
        template='changzhou-demo', id='changzhou-demo', text='需求', review_mode='independent')))])
    message['data'] = dict(items=[content]) if kind == 'inbox' else content
    parent.insert(2, message)
    audits = [independent_review(offset={'reviewed_before_export': 23, 'reviewed_at_export': 26}.get(stage, 3600))] if stage.startswith('reviewed') else []
    result = verifier.verify(resequence(parent), reviews=audits)
    assert result['review']['mode'] == ('child' if stage == 'untrusted' else 'independent')
    assert result['review']['requested'] is (stage != 'untrusted')
    assert result['review']['passed'] is (None if stage == 'untrusted' else stage == 'reviewed')
    assert result['review']['children'] == []
    assert len(result['review']['independent']) == len(audits)
    assert all(check['passed'] for check in result['checks']) is (stage != 'failed')


@pytest.mark.parametrize('change', ['wrong_model', 'wrong_project', 'wrong_version', 'write_tool', 'result_error',
                                  'model_provenance', 'child_disguised', 'missing_crosscheck', 'stale', 'label',
                                  'what_if', 'unsaved', 'wrong_saved_path'])
def test_independent_review_requires_actual_model_scope_and_same_version(change):
    review = independent_review(offset=0 if change == 'stale' else 3600)
    call = next(e for e in review if exporter.tool_name(e) == 'gz_record_review')
    request = next(e for e in review if e['type'] == 'request/sent')
    if change == 'wrong_model':
        request['data']['model']['id'] = 'deepseek-flash'
    elif change in ('wrong_project', 'wrong_version', 'label'):
        key, value = {'wrong_project': ('project_id', 'another'), 'wrong_version': ('version', 1),
                      'label': ('reviewer_model', 'deepseek-flash')}[change]
        call['data']['args'][key] = value
    elif change == 'write_tool':
        call['data']['name'] = 'mcp_guangzhu_1234abcd_gz_edit_design'
    elif change == 'result_error':
        next(e for e in review if e['type'] == 'tool/result' and e['data']['toolUseId'] == call['data']['toolUseId'])['data']['isError'] = True
    elif change == 'model_provenance':
        request['origin'], request['trust'] = 'model', 'untrusted'
    elif change == 'child_disguised':
        review[0]['data']['parent'] = dict(key='fake-parent', boundarySeq=0)
    elif change == 'missing_crosscheck':
        use = next(e['data']['toolUseId'] for e in review if exporter.tool_name(e) == 'gz_crosscheck_yield')
        review = [e for e in review if e['data'].get('toolUseId') != use]
    elif change == 'what_if':
        next(e for e in review if exporter.tool_name(e) == 'gz_analyze')['data']['args']['what_if'] = {}
    elif change in ('unsaved', 'wrong_saved_path'):
        result = next(e for e in review if e['type'] == 'tool/result' and e['data']['toolUseId'] == call['data']['toolUseId'])
        value = exporter.result_value(result)
        value.pop('saved')
        if change == 'wrong_saved_path':
            value['file'] = 'projects/another/reviews/v2-any.json'
        result['data']['content'][0]['text'] = json.dumps(value)
    result = verifier.verify(complete(), reviews=[review])
    assert all(c['passed'] for c in result['checks']) and not result['review']['passed']


def test_native_saved_review_file_is_accepted_and_duplicate_audit_is_not():
    review = independent_review()
    record = next(e for e in review if exporter.tool_name(e) == 'gz_record_review')
    result = next(e for e in review if e['type'] == 'tool/result' and e['data']['toolUseId'] == record['data']['toolUseId'])
    result['data']['content'][0]['text'] = json.dumps(dict(ok=True, version=2, file='projects/changzhou-demo/reviews/v2-native.json'))
    assert verifier.verify(complete(), reviews=[review])['passed']
    assert not verifier.verify(complete(), reviews=[review, review])['review']['passed']


@pytest.mark.parametrize('missing', [None, 'edit', 'analysis', 'crosscheck', 'reason', 'late_crosscheck', 'early_edit'])
def test_independent_high_requires_later_corresponding_edit_analysis_crosscheck_and_review(missing):
    parent, reviews = independent_correction()
    if missing:
        name = dict(edit='gz_edit_design', analysis='gz_analyze', crosscheck='gz_crosscheck_yield', reason='gz_edit_design',
                    late_crosscheck='gz_crosscheck_yield', early_edit='gz_edit_design')[missing]
        call = next(e for e in parent if e['type'] == 'tool/call' and exporter.tool_name(e) == name
                    and (name != 'gz_analyze' or e['data']['args']['version'] == 2))
        if missing == 'reason':
            call['data']['args']['reason'] = '无关的经济修订'
        elif missing == 'early_edit':
            call['ts'] = '2026-10-02T00:00:15Z'
        elif missing == 'late_crosscheck':
            next(e for e in parent if e['type'] == 'tool/result' and e['data']['toolUseId'] == call['data']['toolUseId'])['ts'] = '2026-10-02T02:00:00Z'
        else:
            parent = [e for e in parent if e['data'].get('toolUseId') != call['data']['toolUseId']]
    assert verifier.verify(parent, reviews=reviews)['review']['passed'] is (missing is None)


@pytest.mark.parametrize('metadata_change', [None, 'project_id', 'session'])
def test_independent_review_cli_association_records_ledger_hash(owned_directory, metadata_change):
    design, audit = owned_directory / 'design', owned_directory / 'review'
    for run, events, session in ((design, complete(), '合成-完整'), (audit, independent_review(), 'synthetic-independent-2')):
        exporter.write_json(run / 'run.json', dict(project_id='changzhou-demo', session=session, run_id=run.name))
        (run / 'ledger.agnes.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events), encoding='utf-8')
    if metadata_change:
        info = json.loads((audit / 'run.json').read_text(encoding='utf-8'))
        exporter.write_json(audit / 'run.json', info | {metadata_change: 'mismatch'})
    assert verifier.main([str(design), '--review-run', str(audit)]) == (0 if metadata_change is None else 1)
    result = json.loads((design / 'verification.json').read_text(encoding='utf-8'))
    if metadata_change is None:
        assert result['review']['associations'] == [dict(run='review', session='synthetic-independent-2',
            ledger_sha256=hashlib.sha256((audit / 'ledger.agnes.jsonl').read_bytes()).hexdigest())]


@pytest.mark.parametrize('verdict', ['approve', 'revise'])
def test_final_child_review_cannot_export_unresolved_high_findings(verdict):
    parent, child = reviewed_ledgers()
    set_review(parent, child, verdict, [dict(severity='high', item='E08', evidence='组件未入串', suggestion='删除余件')])
    assert not verifier.verify(parent, children=[child])['review']['passed']
    set_review(parent, child, 'revise', [dict(severity='medium', item='经济', evidence='假设示意', suggestion='现场核实')])
    assert verifier.verify(parent, children=[child])['review']['passed']


@pytest.mark.parametrize('missing', [None, 'edit', 'analysis', 'crosscheck', 'reason', 'unrelated_reason', 'late_analysis', 'late_crosscheck'])
def test_high_review_requires_parent_edit_analysis_crosscheck_and_second_review(missing):
    parent, children = corrected_review_ledgers()
    if missing:
        name = dict(edit='gz_edit_design', analysis='gz_analyze', crosscheck='gz_crosscheck_yield', reason='gz_edit_design',
                    unrelated_reason='gz_edit_design', late_analysis='gz_analyze', late_crosscheck='gz_crosscheck_yield')[missing]
        call = next(e for e in parent if e['type'] == 'tool/call' and exporter.tool_name(e) == name
                    and (name != 'gz_analyze' or e['data']['args']['version'] == 2))
        if missing in ('reason', 'unrelated_reason'):
            call['data']['args']['reason'] = '' if missing == 'reason' else '修改经济说明'
        elif missing.startswith('late_'):
            answer = next(e for e in parent if e['type'] == 'tool/result' and e['data']['toolUseId'] == call['data']['toolUseId'])
            parent.remove(call)
            parent.remove(answer)
            index = next(i for i, e in enumerate(parent) if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_export')
            parent[index:index] = [call, answer]
            parent = resequence(parent)
        else:
            parent = [e for e in parent if e['data'].get('toolUseId') != call['data']['toolUseId']]
    result = verifier.verify(parent, children=children)
    assert result['review']['passed'] is (missing is None)


def test_child_review_rejects_a_result_from_another_version():
    parent, child = reviewed_ledgers()
    analysis = next(e for e in exporter.own_events(child) if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_analyze')
    answer = next(e for e in child if e['type'] == 'tool/result' and e['data']['toolUseId'] == analysis['data']['toolUseId'])
    answer['data']['content'][0]['text'] = json.dumps(exporter.result_value(answer) | dict(version=1))
    assert not verifier.verify(parent, children=[child])['review']['passed']


@pytest.mark.parametrize('change', ['wrong_model', 'write_tool', 'review_error'])
def test_previous_high_review_also_requires_actual_agnes_and_successful_allowed_calls(change):
    parent, children = corrected_review_ledgers()
    own = exporter.own_events(children[0])
    if change == 'wrong_model':
        next(e for e in own if e['type'] == 'request/sent')['data']['model']['id'] = 'deepseek-flash'
    elif change == 'write_tool':
        next(e for e in own if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_project_summary')['data']['name'] = 'gz_edit_design'
    else:
        use_id = next(e['data']['toolUseId'] for e in own if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_analyze')
        next(e for e in own if e['type'] == 'tool/result' and e['data']['toolUseId'] == use_id)['data']['isError'] = True
    assert not verifier.verify(parent, children=children)['review']['passed']


@pytest.mark.parametrize('change', ['wrong_parent', 'wrong_creation', 'wrong_model', 'wrong_selected_model',
                                     'write_tool', 'review_error', 'review_label', 'model_provenance', 'fork_error'])
def test_child_review_requires_native_link_model_allowlist_and_saved_result(change):
    parent, child = reviewed_ledgers()
    own = exporter.own_events(child)
    start, request = own[:2]
    record = next(e for e in parent if exporter.tool_name(e) == 'gz_record_review')
    result = next(e for e in parent if e['type'] == 'tool/result' and e['data']['toolUseId'] == record['data']['toolUseId'])
    fork = next(e for e in parent if e['type'] == 'tool/call' and e['data']['name'] == 'subagent_fork')
    if change == 'wrong_parent':
        start['data']['parent']['key'] = 'different-parent'
    elif change == 'wrong_creation':
        start['data']['delegation']['creationId'] = 'another-fork'
    elif change == 'wrong_model':
        request['data']['model']['id'] = 'deepseek-flash'
    elif change == 'wrong_selected_model':
        fork['data']['args']['model'] = 'deepseek-flash'
    elif change == 'write_tool':
        next(e for e in own if e['type'] == 'tool/call')['data']['name'] = 'gz_record_review'
    elif change == 'review_error':
        result['data']['isError'] = True
    elif change == 'review_label':
        record['data']['args']['reviewer_model'] = 'deepseek-flash'
    elif change == 'model_provenance':
        request['origin'], request['trust'] = 'model', 'untrusted'
    elif change == 'fork_error':
        next(e for e in parent if e['type'] == 'tool/result' and e['data']['toolUseId'] == fork['data']['toolUseId'])['data']['isError'] = True
    verified = verifier.verify(parent, children=[child])
    assert len(verified['checks']) == 4 and all(row['passed'] for row in verified['checks'])
    assert not verified['passed'] and not verified['review']['passed']


def test_native_web_callback_approval_without_optional_tool_name():
    events = complete()
    ask = next(e for e in events if e['type'] == 'approval/asked')
    ask['data'].pop('tool', None)
    decision = next(e for e in events if e['type'] == 'approval/decided')
    decision['data']['via'] = 'callback'
    decision['origin'] = 'external:callback'
    assert verifier.verify(events)['passed']


def test_analysis_cannot_hide_hard_fail_and_modification_must_match():
    events = complete()
    edit = next(e for e in events if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_edit_design')
    edit['data']['args'].update(ops=[dict(op='set_param', name='tilt_deg', value=15)], reason='无关修改')
    result = verifier.verify(events)
    assert not result['checks'][2]['passed']
    events = complete()
    final_call = [e for e in events if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_analyze'][-1]
    final = next(e for e in events if e['type'] == 'tool/result' and e['data']['toolUseId'] == final_call['data']['toolUseId'])
    value = exporter.result_value(final)
    value['rules'].pop('hard_failed')
    final['data']['content'][0]['text'] = json.dumps(value)
    assert not verifier.verify(events)['checks'][3]['passed']


def test_native_async_order_and_cross_session_rejection(owned_directory):
    events = complete()
    ledger = owned_directory / 'synthetic.agnes.jsonl'
    ledger.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in reversed(events)), encoding='utf-8')
    assert verifier.verify(exporter.read_events(ledger))['passed']
    extra = copy.deepcopy(events[0])
    extra.update(seq=100, id=f'{100:026d}')
    extra['data']['key'] = 'synthetic-another-session'
    ledger.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events + [extra]), encoding='utf-8')
    with pytest.raises(ValueError, match='不能拼接不同会话'):
        exporter.read_events(ledger)


def test_usage_uses_cost_ledger_once_not_streaming_estimates():
    events = complete()
    cost = next(e for e in events if e['type'] == 'cost/ledger')
    events += [copy.deepcopy(cost), dict(type='assistant/output', data=dict(estimatedTokens=9999))]
    result = exporter.summarize(events)
    assert result['model_requests'] == 1
    assert result['tokens'] == dict(input=100, output=50, cacheRead=10, cacheWrite=0, reasoning=0)
    assert result['models'] == [dict(route='synthetic', id='synthetic-only-no-model')]


def test_sanitization_does_not_write_sensitive_values():
    sensitive = 'sk' + '-' + ('abcdef123456' * 3)
    value = dict(headers={'Authorization': sensitive}, requestHeaders={'x-private': sensitive},
                 message='Bearer ' + sensitive, nested=[str(Path.home()) + '/file', sensitive],
                 content=json.dumps(dict(headers={'x': sensitive}, text=sensitive)))
    result = exporter.sanitize(value)
    rendered = json.dumps(result)
    assert sensitive not in rendered and 'headers' not in rendered.lower()
    assert '%USERPROFILE%' in rendered and str(Path.home()) not in rendered
    assert json.loads(result['content'])['text'] == '[REDACTED]'


def test_export_cli_is_official_export_only_and_copies_referenced_evidence(owned_directory, monkeypatch):
    project = owned_directory / 'projects/changzhou-demo'
    for version in (1, 2):
        exporter.write_json(project / f'designs/v{version}.json', dict(version=version, parent_version=version - 1 or None))
        exporter.write_json(project / f'analysis/v{version}/summary.json', dict(ok=True, version=version))
    exporter.write_json(project / 'reviews/v2-synthetic.json', dict(version=2, verdict='approve'))
    exporter.write_json(project / 'exports/v2/design.json', dict(version=2))
    design = project / 'exports/v2/design.json'
    exporter.write_json(project / 'exports/v2/manifest.json', dict(version=2, files={'design.json': hashlib.sha256(design.read_bytes()).hexdigest()}))
    invoked = []
    def official_stub(command, **kwargs):
        invoked.append(command)
        Path(command[-1]).write_bytes((FIXTURES / '合成-完整.agnes.jsonl').read_bytes())
        assert kwargs['check'] and kwargs['capture_output']
    monkeypatch.setenv('AGH_HOME', str(owned_directory / 'agh-home-not-created'))
    monkeypatch.setattr(exporter.subprocess, 'run', official_stub)
    run = exporter.export_run('合成-完整', 'changzhou-demo', 'synthetic-run', root=owned_directory, executable='never-executed')
    assert invoked[0][1:] == ['export', '合成-完整', '--format', 'agnes', '--out', str(run / 'ledger.agnes.jsonl')]
    assert not (owned_directory / 'agh-home-not-created').exists()
    metadata = json.loads((run / 'run.json').read_text(encoding='utf-8'))
    assert len(metadata['artifacts']) == 7
    for relative, digest in metadata['artifacts'].items():
        assert hashlib.sha256((run / relative).read_bytes()).hexdigest() == digest
    assert (run / 'project/exports/v2/design.json').read_bytes() == design.read_bytes()
    assert 'run.json' in json.loads((run / 'project/exports/v2/manifest.json').read_text(encoding='utf-8'))['snapshot_note']
    assert verifier.main([str(run)]) == 0


@pytest.mark.parametrize('retried', [False, True])
def test_export_discovers_real_direct_fork_and_retains_inherited_prefix(owned_directory, monkeypatch, retried):
    if retried:
        parent, children = corrected_review_ledgers()
    else:
        parent, child = reviewed_ledgers()
        children = [child]
    session = parent[0]['data']['key']
    by_id = {exporter.own_events(child)[0]['data']['key']: child for child in children}
    unrelated = copy.deepcopy(children[0])
    exporter.own_events(unrelated)[0]['data'].update(key=session + '/unrelated-fork', delegation=dict(kind='fork', creationId='another-call'))
    by_id[exporter.own_events(unrelated)[0]['data']['key']] = unrelated
    project = owned_directory / 'projects/changzhou-demo'
    for version in (1, 2):
        exporter.write_json(project / f'designs/v{version}.json', dict(version=version))
    invoked = []
    def official_stub(command, **kwargs):
        invoked.append(command)
        if command[1] == 'sessions':
            class Reply:
                stdout = json.dumps(dict(items=[dict(sessionId=key) for key in by_id]
                                               + [dict(sessionId='unrelated', parent='another-session')]))
            return Reply()
        events = parent if command[2] == session else by_id[command[2]]
        Path(command[-1]).write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events), encoding='utf-8')
    monkeypatch.setenv('AGH_HOME', str(owned_directory / 'not-created'))
    monkeypatch.setattr(exporter.subprocess, 'run', official_stub)
    run = exporter.export_run(session, 'changzhou-demo', 'with-child', root=owned_directory, executable='never-executed', with_children=True)
    metadata = json.loads((run / 'run.json').read_text(encoding='utf-8'))
    assert len(metadata['children']) == len(children)
    for row in metadata['children']:
        assert row['models'] == [dict(route='synthetic', id='agnes-3.0-flash')]
        assert row['ledger'] == 'children/' + exporter.quote(row['session'], safe='-_') + '.ledger.agnes.jsonl'
        assert len((run / row['ledger']).read_text(encoding='utf-8').splitlines()) == len(by_id[row['session']])
    assert len(invoked) == 2 + len(by_id) and invoked[1][1:] == ['sessions', 'list', '--json']
    assert len(list((run / 'children').iterdir())) == len(children)
    assert len(list((run / 'unassociated').iterdir())) == 1
    assert any('缺少' in row['message'] and row['ledger'].startswith('unassociated/') for row in metadata['anomalies'])
    assert not (owned_directory / 'not-created').exists()


def test_export_discovers_completed_child_from_native_cost_without_session_list(owned_directory, monkeypatch):
    parent, child = reviewed_ledgers()
    session = parent[0]['data']['key']
    child_id = exporter.own_events(child)[0]['data']['key']
    cost = copy.deepcopy(parent[-1])
    cost.update(type='subagent/cost', data=dict(childKey=child_id, complete=True))
    parent = resequence(parent + [cost])
    invoked = []
    def official_stub(command, **kwargs):
        invoked.append(command)
        assert command[1] == 'export'
        events = parent if command[2] == session else child
        Path(command[-1]).write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events), encoding='utf-8')
    monkeypatch.setenv('AGH_HOME', str(owned_directory / 'not-created'))
    monkeypatch.setattr(exporter.subprocess, 'run', official_stub)
    run = exporter.export_run(session, 'changzhou-demo', 'native-cost-child', root=owned_directory, executable='never-executed', with_children=True)
    metadata = json.loads((run / 'run.json').read_text(encoding='utf-8'))
    assert len(invoked) == 2 and metadata['children'][0]['session'] == child_id
    assert (run / 'timeline.json').is_file()
    assert verifier.main([str(run)]) == 0


@pytest.mark.parametrize('failure', ['child_denied', 'listing_denied', 'pagination'])
def test_children_export_failure_keeps_parent_evidence_and_reports_partial_result(owned_directory, monkeypatch, capsys, failure):
    parent, child = reviewed_ledgers()
    session = parent[0]['data']['key']
    child_id = exporter.own_events(child)[0]['data']['key']
    if failure == 'child_denied':
        cost = copy.deepcopy(parent[-1])
        cost.update(type='subagent/cost', data=dict(childKey=child_id, complete=True))
        parent = resequence(parent + [cost])
    def official_stub(command, **kwargs):
        if command[1] == 'export' and command[2] == session:
            Path(command[-1]).write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in parent), encoding='utf-8')
        elif failure == 'pagination':
            class Reply:
                stdout = json.dumps(dict(items=[], next='unread-page'))
            return Reply()
        else:
            raise exporter.subprocess.CalledProcessError(1, command, stderr=b'agnes: CAPABILITY_DENIED (-32006)')
    monkeypatch.setenv('AGH_HOME', str(owned_directory / 'not-created'))
    monkeypatch.setattr(exporter.subprocess, 'run', official_stub)
    run = exporter.export_run(session, 'changzhou-demo', failure, root=owned_directory, executable='never-executed', with_children=True)
    metadata = json.loads((run / 'run.json').read_text(encoding='utf-8'))
    assert metadata['children_complete'] is False and metadata['children'] == []
    assert metadata['children_errors'][0]['error_code'] == ('CHILDREN_EXPORT_FAILED' if failure == 'pagination' else 'CAPABILITY_DENIED')
    assert metadata['children_errors'][0]['session'] == (child_id if failure == 'child_denied' else None)
    assert exporter.read_events(run / 'ledger.agnes.jsonl') == exporter.sanitize(parent)
    assert json.loads((run / 'timeline.json').read_text(encoding='utf-8')) == exporter.timeline(exporter.sanitize(parent))
    assert verifier.main([str(run)]) == 1
    verification = json.loads((run / 'verification.json').read_text(encoding='utf-8'))
    assert not verification['review']['passed'] and '子会话导出不完整' in verification['errors']
    original = exporter.export_run
    monkeypatch.setattr(exporter, 'export_run', lambda *a, **kw: original(*a, **kw, root=owned_directory, executable='never-executed'))
    monkeypatch.setattr(exporter, 'ROOT', owned_directory)
    assert exporter.main(['--session', session, '--project', 'changzhou-demo', '--run-id', failure + '-cli', '--with-children']) == 1
    assert '子会话导出不完整' in capsys.readouterr().out


def test_timeline_008_matches_every_source_message_tool_and_approval():
    events = exporter.read_events(ROOT / 'runs/t09-changzhou-008/ledger.agnes.jsonl')
    result = exporter.timeline(events)
    assert result['schema'] == 'guangzhu.timeline/1'
    nodes = result['nodes']
    assert [n['ts'] for n in nodes] == sorted(n['ts'] for n in nodes)
    messages = [e for e in events if e['type'] == 'assistant/message' and any(b.get('type') == 'text' and b.get('text') for b in e['data'].get('content', []))]
    calls = [e for e in events if e['type'] == 'tool/call']
    approvals = [e for e in events if e['type'] in ('approval/asked', 'approval/decided')]
    assert len(nodes) == len(messages) + len(calls) + len(approvals)
    by_seq = {e['seq']: e for e in events}
    for node in nodes:
        source = by_seq[node['seq']]
        assert source['ts'] == node['ts'] and node['session'] == events[0]['data']['key']
        if node['kind'] == 'text':
            assert node['text'] == ''.join(b.get('text', '') for b in source['data']['content'] if b['type'] == 'text')
        elif node['kind'] == 'tool':
            answer = by_seq[node['result_seq']]
            assert source['data']['toolUseId'] == answer['data']['toolUseId'] == node['tool_use_id']
            assert node['started_at'] == source['ts'] and node['ended_at'] == answer['ts']
            assert len(node['result'].encode('utf8')) <= 2048
            assert len(node['args'].encode('utf8')) <= 1024
            assert ''.join(b.get('text', '') for b in answer['data']['content'] if b['type'] == 'text').startswith(node['result'])
        else:
            assert node['pending'] == (source['type'] == 'approval/asked')
            assert node['verdict'] == source['data'].get('verdict')
    assert any(n.get('verdict') == 'allowed-once' and n['tool'] == 'gz_export' for n in nodes)


def test_timeline_child_boundaries_come_from_native_turn_end_and_omit_inherited_events():
    parent, child = reviewed_ledgers()
    result = exporter.timeline(parent, [child])
    child_id = exporter.own_events(child)[0]['data']['key']
    child_nodes = [n for n in result['nodes'] if n['session'] == child_id]
    assert len([n for n in child_nodes if n['kind'] == 'tool']) == 3
    assert [n['phase'] for n in child_nodes if n['kind'] == 'child'] == ['started']
    end = copy.deepcopy(child[-1])
    end.update(type='turn/end', data=dict(reason='completed'))
    child = resequence(child + [end])
    boundaries = [n for n in exporter.timeline(parent, [child])['nodes'] if n['kind'] == 'child']
    assert [n['phase'] for n in boundaries] == ['started', 'ended']
    assert boundaries[-1]['seq'] == child[-1]['seq'] and boundaries[-1]['ts'] == child[-1]['ts']


def test_redacted_export_snapshot_has_its_own_sha_without_writing_original_sensitive_text(owned_directory, monkeypatch):
    project = owned_directory / 'projects/changzhou-demo'
    for version in (1, 2):
        exporter.write_json(project / f'designs/v{version}.json', dict(version=version))
    source = project / 'exports/v2/design.json'
    exporter.write_json(source, dict(version=2, note='synthetic-source-placeholder'))
    sensitive = 'sk' + '-' + ('abcdef123456' * 3)
    only_in_memory = json.dumps(dict(version=2, api_key=sensitive)).encode()
    original_digest = hashlib.sha256(only_in_memory).hexdigest()
    exporter.write_json(source.parent / 'manifest.json', dict(version=2, files={'design.json': original_digest}))
    read_original = Path.read_bytes
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'read_bytes', lambda path: only_in_memory if path.resolve() == source.resolve() else read_original(path))
        hashes = exporter.snapshot(complete(), 'changzhou-demo', owned_directory / 'run', owned_directory / 'projects')
    destination = owned_directory / 'run'
    exporter.write_json(destination / 'run.json', dict(artifacts=hashes))
    snapshot = destination / 'project/exports/v2/design.json'
    assert sensitive not in snapshot.read_text(encoding='utf-8')
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == hashes['project/exports/v2/design.json']
    assert hashes['project/exports/v2/design.json'] != original_digest
    manifest = json.loads((destination / 'project/exports/v2/manifest.json').read_text(encoding='utf-8'))
    assert manifest['files']['design.json'] == original_digest
    assert 'run.json' in manifest['snapshot_note']
    assert all(sensitive not in p.read_text(encoding='utf-8') for p in owned_directory.rglob('*.json'))


@pytest.mark.parametrize('identifier', ['../escape', '..', 'bad/id', 'bad\\id', 'bad:drive', ''])
def test_identifiers_reject_path_traversal(identifier):
    with pytest.raises(ValueError):
        exporter.identifier(identifier)


def test_snapshot_logs_other_projects_and_invalid_versions(owned_directory):
    events = complete()
    first = next(e for e in events if e['type'] == 'tool/call')
    first['data']['args']['project_id'] = '../other'
    anomalies = []
    exporter.snapshot(events, 'changzhou-demo', owned_directory / 'run', owned_directory / 'projects', anomalies)
    assert any('其他项目' in a['message'] and a['seq'] == first['seq'] for a in anomalies)
    events = complete()
    first = next(e for e in events if e['type'] == 'tool/call')
    first['data']['args']['version'] = '../escape'
    anomalies = []
    exporter.snapshot(events, 'changzhou-demo', owned_directory / 'run', owned_directory / 'projects', anomalies)
    assert any('版本号不合法' in a['message'] and a['seq'] == first['seq'] for a in anomalies)


def test_new_roof_summary_null_version_is_not_a_design_reference(owned_directory):
    projects = owned_directory / 'projects'
    for version in (1, 2):
        exporter.write_json(projects / f'changzhou-demo/designs/v{version}.json', dict(version=version))
    events = complete()
    first = next(e for e in events if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_project_summary')
    result = next(e for e in events if e['type'] == 'tool/result' and e['data']['toolUseId'] == first['data']['toolUseId'])
    result['data']['content'][0]['text'] = json.dumps(dict(ok=True, version=None, versions=[], modules=0))
    snapshots = exporter.snapshot(events, 'changzhou-demo', owned_directory / 'run', projects)
    assert set(snapshots) == {'project/designs/v1.json', 'project/designs/v2.json'}
    first['data']['args']['version'] = None
    anomalies = []
    snapshots = exporter.snapshot(events, 'changzhou-demo', owned_directory / 'strict-run', projects, anomalies)
    assert len(snapshots) == 2 and any('版本号不合法' in a['message'] for a in anomalies)


def test_compare_final_versions_snapshot_also_copies_implicit_ancestors(owned_directory):
    projects = owned_directory / 'projects'
    for version in (1, 2, 3, 4, 5):
        exporter.write_json(projects / f'changzhou-demo/designs/v{version}.json', dict(version=version, parent_version=version - 1 or None))
    events = complete()
    events += [dict(seq=100, type='tool/call', data=dict(toolUseId='synthetic-compare', name='mcp_guangzhu_1234abcd_gz_compare_options',
                                                      args=dict(project_id='changzhou-demo', base_version=2))),
               dict(seq=101, type='tool/result', data=dict(toolUseId='synthetic-compare', isError=False,
                    content=[dict(type='text', text=json.dumps(dict(ok=True, base_version=2, options=[dict(version=4)])))]))]
    snapshots = exporter.snapshot(events, 'changzhou-demo', owned_directory / 'run', projects)
    assert set(snapshots) == {f'project/designs/v{v}.json' for v in (1, 2, 3, 4)}
    assert not (owned_directory / 'run/project/designs/v5.json').exists()
    for version in (1, 2, 3, 4):
        assert (owned_directory / f'run/project/designs/v{version}.json').read_bytes() == (projects / f'changzhou-demo/designs/v{version}.json').read_bytes()


@pytest.mark.parametrize('parent', [0, -1, 2, 3, True, '../outside'])
def test_snapshot_rejects_invalid_or_cyclic_ancestry(owned_directory, parent):
    projects = owned_directory / 'projects'
    for version in (1, 2):
        exporter.write_json(projects / f'changzhou-demo/designs/v{version}.json', dict(version=version, parent_version=parent if version == 2 else None))
    anomalies = []
    copied = exporter.snapshot(complete(), 'changzhou-demo', owned_directory / 'run', projects, anomalies)
    assert len(copied) == 2
    assert any('父版本须是更早的正整数版本' in a['message'] for a in anomalies)


def test_snapshot_reports_missing_reference_instead_of_silently_omitting_it(owned_directory):
    projects = owned_directory / 'projects'
    exporter.write_json(projects / 'changzhou-demo/designs/v1.json', dict(version=1))
    anomalies = []
    copied = exporter.snapshot(complete(), 'changzhou-demo', owned_directory / 'run', projects, anomalies)
    assert set(copied) == {'project/designs/v1.json'}
    assert any(a.get('version') == 2 and '引用方案不存在' in a['message'] for a in anomalies)


@pytest.mark.parametrize('name,failed,rejected', [('合成-参数重试', 1, 0), ('合成-导出后追问', 0, 0), ('合成-超时重试', 1, 1)])
def test_real_recovery_patterns_are_accepted_with_failures_preserved(name, failed, rejected):
    events = exporter.read_events(FIXTURES / (name + '.agnes.jsonl'))
    result = verifier.verify(events)
    assert result['passed'] and result['errors'] == []
    assert result['failed_call_count'] == failed and result['rejected_approval_count'] == rejected
    assert all(row['call_seq'] > 0 and row['result_seq'] > row['call_seq'] for row in result['failed_calls'])
    assert all(row['seq'] > 0 for row in result['rejected_approvals'])
    assert result['verified_exports'][0]['version'] == 2


def test_feedback_allows_successful_readonly_calls_between_analysis_and_edit():
    events = complete()
    summary = next(e for e in events if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_project_summary')
    result = next(e for e in events if e['type'] == 'tool/result' and e['data']['toolUseId'] == summary['data']['toolUseId'])
    summary, result = copy.deepcopy(summary), copy.deepcopy(result)
    summary['data']['toolUseId'] = result['data']['toolUseId'] = 'synthetic-readonly-between'
    index = next(i for i, e in enumerate(events) if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_edit_design')
    result = verifier.verify(resequence(events[:index] + [summary, result] + events[index:]))
    assert result['passed'] and result['feedback_sequences'][0][1] - result['feedback_sequences'][0][0] == 3


def test_last_normal_analysis_for_export_version_cannot_be_replaced_by_what_if():
    events = complete()
    final = [e for e in events if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_analyze'][-1]
    final['data']['args']['what_if'] = {}
    assert not verifier.verify(events)['checks'][3]['passed']


def test_anomalous_references_still_export_ledger_run_metadata_and_safe_artifacts(owned_directory, monkeypatch):
    events = complete()
    first = next(e for e in events if e['type'] == 'tool/call')
    first['data']['args']['project_id'] = '../wrong-project'
    final = [e for e in events if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_analyze'][-1]
    final['data']['args']['version'] = '../invalid-version'
    cross = next(e for e in events if e['type'] == 'tool/call' and exporter.tool_name(e) == 'gz_crosscheck_yield')
    cross['data']['args']['version'] = 999
    project = owned_directory / 'projects/changzhou-demo'
    for version in (1, 2):
        exporter.write_json(project / f'designs/v{version}.json', dict(version=version, parent_version=version - 1 or None))
    exporter.write_json(owned_directory / 'projects/wrong-project/designs/v77.json', dict(version=77))
    def official_stub(command, **kwargs):
        Path(command[-1]).write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events), encoding='utf-8')
    monkeypatch.setenv('AGH_HOME', str(owned_directory / 'never-created-agh'))
    monkeypatch.setattr(exporter.subprocess, 'run', official_stub)
    run = exporter.export_run('synthetic-session', 'changzhou-demo', 'synthetic-anomalies', root=owned_directory, executable='never-executed')
    metadata = json.loads((run / 'run.json').read_text(encoding='utf-8'))
    assert len(exporter.read_events(run / 'ledger.agnes.jsonl')) == len(events)
    assert {'project/designs/v1.json', 'project/designs/v2.json'} == set(metadata['artifacts'])
    assert any('其他项目' in a['message'] for a in metadata['anomalies'])
    assert any('版本号不合法' in a['message'] for a in metadata['anomalies'])
    assert any(a.get('version') == 999 and '引用方案不存在' in a['message'] for a in metadata['anomalies'])
    assert not (run / 'project/designs/v77.json').exists()
