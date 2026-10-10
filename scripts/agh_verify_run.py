"""Check the four 3.1 stages from native AGH events, including human export approval."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

if __package__:
    from .agh_export_run import contained, final_analysis, own_events, read_events, resolve_results, tool_name, write_json
else:
    from agh_export_run import contained, final_analysis, own_events, read_events, resolve_results, tool_name, write_json


def moment(event):
    value = datetime.fromisoformat(event['ts'].replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('跨会话关联须有带时区的原生时间戳')
    return value


def review_json(event):
    text = ''.join(b.get('text', '') for b in event.get('data', {}).get('content', []) if b.get('type') == 'text')
    blocks = re.findall(r'```json\s*\n(.*?)\n```', text, re.S)
    def unique(pairs):
        if len(dict(pairs)) != len(pairs):
            raise ValueError('审核JSON存在重复键')
        return dict(pairs)
    try:
        value = json.loads(blocks[0], object_pairs_hook=unique) if len(blocks) == 1 and text.rstrip().endswith('```') else None
        if (isinstance(value, dict) and set(value) == {'verdict', 'findings'} and value['verdict'] in ('approve', 'revise')
                and isinstance(value['findings'], list) and all(isinstance(f, dict)
                    and set(f) == {'severity', 'item', 'evidence', 'suggestion'} and f['severity'] in ('high', 'medium', 'low')
                    and all(isinstance(v, str) and v for v in f.values()) for f in value['findings'])):
            return value
    except ValueError:
        pass
    return None


TOOL_NAMES_ZH = dict(gz_project_summary='项目摘要', gz_analyze='方案分析', gz_crosscheck_yield='发电复核', gz_record_review='保存审核意见')


def verify_review(events, children, exports, project_id, model, paired, reviews=()):
    forks = [e for e in events if e['type'] == 'tool/call' and e['data'].get('name') == 'subagent_fork']
    rows, parent = [], next(e['data']['key'] for e in events if e['type'] == 'session/start')
    requested = bool(forks or children or reviews)
    declared_independent = False
    for event in events:
        if event['type'] not in ('user/message', 'inbox') or event.get('trust') != 'trusted':
            continue
        items = event['data'].get('items', []) if event['type'] == 'inbox' else [event['data']]
        for block in (block for item in items for block in item.get('content', [])):
            if not block.get('text', '').startswith('【光筑任务书'):
                continue
            for raw in re.findall(r'```json\s*\n(.*?)\n```', block.get('text', ''), re.S):
                try:
                    brief = json.loads(raw)
                    if brief.get('brief') == 'guangzhu.brief/1':
                        model = brief['run']['review']['model']
                        requested |= brief['run']['review']['enabled']
                        declared_independent |= brief['run']['review'].get('mode') == 'independent'
                except (ValueError, KeyError, TypeError, AttributeError):
                    pass
    model_id = model.split('/')[-1]
    independent = bool(reviews) or declared_independent
    allowed = {'gz_project_summary', 'gz_analyze', 'gz_crosscheck_yield'} | ({'gz_record_review'} if independent else set())
    for source in reviews if independent else forks:
        fork = None if independent else source
        associated = [c for c in children if own_events(c)[0]['data'].get('delegation', {}).get('creationId', '').startswith(
            f"{parent}:{fork.get('lane', 'main')}:{fork['data']['toolUseId']}:")] if fork else []
        own = own_events(source) if independent else own_events(associated[0]) if len(associated) == 1 else []
        start = own[0]['data'] if own else {}
        delegation = start.get('delegation', {})
        resolved, unlinked = resolve_results(own)
        wait_ids = {use_id for r in resolved for use_id in r['wait_ids']}
        calls = [e for e in own if e['type'] == 'tool/call' and e['data'].get('toolUseId') not in wait_ids]
        requests = [e for e in own if e['type'] == 'request/sent']
        models = {e['data'].get('model', {}).get('id') for e in requests}
        returned = [e for e in events if e['type'] == 'tool/result' and fork and e['data'].get('toolUseId') == fork['data']['toolUseId']]
        successful, records, saved = [], [], []
        boundary = next((f['seq'] for f in forks if fork and f['seq'] > fork['seq']), float('inf'))
        recording = [c for c in events if c['type'] == 'tool/call' and tool_name(c) == 'gz_record_review'
                     and len(returned) == 1 and returned[0]['seq'] < c['seq'] < boundary] if not independent else []
        for call in calls + recording:
            matches = resolved if call in calls else resolve_results(events)[0]
            row = next((r for r in matches if r['call'] is call), {})
            result, value = row.get('result'), row.get('value', {})
            args = call['data'].get('args', {})
            if (result and call['seq'] < result['seq'] and result['data'].get('isError') is False
                    and value.get('ok') is True and args.get('project_id') == project_id
                    and not (tool_name(call) == 'gz_analyze' and 'what_if' in args)
                    and (tool_name(call) == 'gz_project_summary' or type(args.get('version')) is int and args['version'] > 0
                         and value.get('version') == args.get('version'))):
                if call in calls:
                    successful.append(call)
                if (tool_name(call) == 'gz_record_review' and args.get('reviewer_model') == model
                        and (value.get('saved') is True or
                             re.fullmatch(r'projects/' + re.escape(project_id or '') + r'/reviews/v'
                                          + str(args.get('version')) + r'-[^/\\]+\.json', value.get('file', '')))):
                    records.append(args)
                    saved.append(result)
        high = any(f.get('severity') == 'high' for r in records for f in r.get('findings', []))
        linked = (not start.get('parent') and not delegation) if independent else bool(
            fork and fork.get('origin') == 'system' and fork.get('trust') == 'trusted' and fork['data'].get('args', {}).get('model') == model
            and len(returned) == 1 and returned[0]['data'].get('isError') is False and fork['seq'] < returned[0]['seq'])
        versions = {c['data'].get('args', {}).get('version') for c in successful if tool_name(c) != 'gz_project_summary'} | {r['version'] for r in records}
        # T20: an independent reviewer may repeat read-only checks; every required tool must still succeed once and nothing else may be used.
        foreign, missing = sorted({tool_name(c) for c in calls} - allowed), sorted(allowed - {tool_name(c) for c in successful})
        problems = [text for broken, text in (
            (not (own and own[0].get('origin') == 'system' and own[0].get('trust') == 'trusted'), '审核会话不是光筑建立的'),
            (models != {model_id}, f"审核用的模型（{'、'.join(sorted(m for m in models if m)) or '无'}）和任务书指定的 {model_id} 不一致"),
            (not all(e.get('origin') == 'system' and e.get('trust') == 'trusted' for e in requests), '模型请求不是光筑发出的'),
            ('/' in model and not all(e['data']['model'].get('route') == model.rsplit('/', 1)[0] for e in requests), '审核模型的账户线路和任务书不一致'),
            (bool(unlinked), '有工具调用没有对应结果'), (bool(foreign), '用了审核不允许的工具：' + '、'.join(foreign)),
            (bool(missing), '缺少必需的查询：' + '、'.join(TOOL_NAMES_ZH.get(name, name) for name in missing)),
            (len({c['data']['toolUseId'] for c in calls}) != len(calls), '工具调用编号重复'),
            (sum(tool_name(c) == 'gz_record_review' for c in calls) > 1, '审核意见保存了不止一次')) if broken]
        extra = sum(tool_name(c) != 'gz_record_review' for c in calls) - len(allowed - {'gz_record_review'})
        strict = bool(len(calls) == len(allowed) and len(successful) == len(calls) and {tool_name(c) for c in calls} == allowed)
        ledger_valid = not problems and (independent or strict)
        payload = review_json(returned[0]) if len(returned) == 1 else None
        messages = [e for e in own if e['type'] == 'assistant/message']
        copied = bool(payload and len(records) == 1 and payload == {k: records[0].get(k) for k in ('verdict', 'findings')})
        child_valid = bool(len(associated) == 1 and ledger_valid and len(calls) == 3
            and start.get('parent', {}).get('key') == parent and delegation.get('kind') == 'fork'
            and messages and messages[-1].get('origin') == 'model' and messages[-1].get('trust') == 'trusted'
            and review_json(messages[-1]) == payload)
        problems += [text for broken, text in ((not linked, '审核会话和设计会话的关联不对'), (not records, '审核意见没有保存'),
            (len(versions) > 1, '审核查看的方案版本不一致'), (not all(r.get('verdict') in ('approve', 'revise') for r in records), '审核结论不是通过或修改'),
            (independent and len(records) != sum(tool_name(c) == 'gz_record_review' for c in calls), '有一次保存审核意见没有成功')) if broken]
        valid = bool(linked and records and len(versions) == 1
            and all(r.get('verdict') in ('approve', 'revise') for r in records)
            and (ledger_valid and len(records) == sum(tool_name(c) == 'gz_record_review' for c in calls) if independent
                 else child_valid and copied and len(recording) == 1))
        passed = bool(valid and not high and any(ex['version'] in versions
            and (moment(own[0]) > moment(next(e for e in events
                 if e['seq'] == ex['export_result_seq' if declared_independent else 'analysis_seq'])) if independent
                 else saved[0]['seq'] < ex['export_call_seq']) for ex in exports))
        rows.append(dict(session=start.get('key', fork['data']['toolUseId'] if fork else None), model=model_id if models == {model_id} else None,
                         agnes=model_id.lower().startswith('agnes') and models == {model_id},
                         actual_model_verified=ledger_valid, json_unchanged=copied if not independent else None, valid=valid, passed=passed, high=high,
                         retryable=bool(not independent and linked and child_valid and payload is None and not recording),
                         versions=sorted(versions), fork_call_seq=fork['seq'] if fork else None,
                         fork_result_seq=returned[0]['seq'] if len(returned) == 1 else None,
                         started_at=own[0].get('ts') if own else fork.get('ts'), saved_at=saved[-1].get('ts') if saved else None,
                         high_items=[f.get('item', '') for r in records for f in r.get('findings', []) if f.get('severity') == 'high'],
                         problems=problems, extra_read_only_calls=max(extra, 0) if independent and not foreign else 0))
    if independent:
        rows.sort(key=lambda r: moment(dict(ts=r['saved_at'])) if r['saved_at'] else moment(dict(ts=r['started_at'])))
    passed = bool(rows and len(rows) <= 2 and len({r['session'] for r in rows}) == len(rows)
                  and (independent or len(forks) <= 2 and (not children or len(children) == len(forks)))
                  and all(r['valid'] or i == 0 and r['retryable'] for i, r in enumerate(rows)) and
                  (rows[-1]['passed'] if independent else any(r['passed'] and r['fork_call_seq'] == forks[-1]['seq'] for r in rows)))
    for row in (r for r in rows if r['high']):
        reachable, cursor, edits = set(row['versions']), row['fork_result_seq'], []
        after = moment(dict(ts=row['saved_at'])) if independent and row['saved_at'] else None
        before = moment(dict(ts=rows[-1]['started_at'])) if independent else None
        for name, call, result, value in paired:
            args = call['data'].get('args', {})
            subsequent = (after is not None and after < moment(call) < moment(result) < before) if independent else (
                cursor is not None and cursor < call['seq'] < result['seq'] < forks[-1]['seq'])
            if (name == 'gz_edit_design' and subsequent
                    and args.get('version') in reachable and type(value.get('version')) is int and value['version'] > args['version']
                    and args.get('ops') and args.get('reason', '').strip()):
                reachable.add(value['version'])
                edits.append((result['seq'], value['version'], args['reason']))
                cursor = result['seq']
        reasons = '\n'.join(e[2] for e in edits)
        resolved = all(item and item in reasons for item in row['high_items']) and any(
            edit_version == ex['version'] and edit_seq < ex['analysis_seq']
            and any(name == 'gz_crosscheck_yield' and ex['analysis_seq'] < call['seq'] < result['seq']
                    and (moment(result) < before if independent else result['seq'] < forks[-1]['seq'])
                    and call['data'].get('args', {}).get('version') == value.get('version') == ex['version']
                    for name, call, result, value in paired)
            for edit_seq, edit_version, _ in edits for ex in exports)
        row['resolved'] = resolved
        passed &= resolved
    return dict(requested=requested, passed=passed if requested else None, mode='independent' if independent else 'child',
                children=[] if independent else rows, independent=rows if independent else [],
                reason=('审核证据齐全' if independent or children else '父会话JSON记录一致；未导出子会话，实际模型与工具未核实') if passed
                else '未请求审核' if not requested else '；'.join(rows[-1]['problems']) if rows and rows[-1]['problems'] else
                '审核会话没有找到' if not rows else '会话关联、审核模型、只读工具、JSON原样记录或同版本审核证据不齐')


def export_approvals(events, row):
    """Authorize only the original export, before execution, with one trusted decision."""
    call, initial = row["call"], row["initial"]
    approved = []
    effects = [e for e in events if e['type'] == 'effect/intent' and e['data'].get('tool', {}).get('toolUseId') == call['data']['toolUseId']]
    execution = min([e['seq'] for e in effects] + [initial['seq']])
    asked = [e for e in events if e['type'] == 'approval/asked' and e.get('origin') == 'system' and e.get('trust') == 'trusted'
             and e['data'].get('kind') == 'tool' and e['data'].get('toolUseId') == call['data']['toolUseId']
             and e['data'].get('tool', call['data']['name']) == call['data']['name'] and call['seq'] < e['seq'] < execution]
    for ask in asked:
        decisions = [e for e in events if e['type'] == 'approval/decided' and e['data'].get('requestId') == ask['data']['requestId']]
        if len(decisions) == 1:
            decision = decisions[0]
            if (ask['seq'] < decision['seq'] < execution and decision['data'].get('verdict') == 'allowed-once'
                    and decision['data'].get('via') in ('sync', 'callback') and decision.get('trust') == 'trusted'
                    and decision.get('origin') in ('system', 'external:callback')):
                approved.append(decision)
    return approved


def verify(events, *, children=(), reviewer_model='agnes-3.0-flash', reviews=(), no_export=False):
    rows, unlinked = resolve_results(events)
    calls = [r['call'] for r in rows]
    paired, failed_calls, pending_calls = [], [], []
    errors = ['等待结果无法关联原调用'] if unlinked else []
    if len({c['data'].get('toolUseId') for c in calls}) != len(calls):
        errors.append('工具调用编号重复，不能复用结果')
    for row in rows:
        call, result, value = row['call'], row['result'], row['value']
        if row['pending']:
            pending_calls.append(dict(tool=row['name'], call_seq=call['seq']))
            continue
        if not result or result['seq'] <= call['seq'] or result['data'].get('isError') is not False or value.get('ok') is not True:
            failed_calls.append(dict(tool=tool_name(call), call_seq=call['seq'], result_seq=result['seq'] if result else None,
                                     pending=row['pending'],
                                     error_code=value.get('error_code', result['data'].get('code') if result else 'RESULT_MISSING')))
        else:
            paired.append((tool_name(call), call, result, value))
    found = lambda name: [p for p in paired if p[0] == name]
    requirements = found('gz_set_requirements')
    weather, layouts, analyses = found('gz_fetch_weather'), found('gz_generate_layout'), found('gz_analyze')
    initial_queries = {'gz_new_project', 'gz_project_summary', 'gz_analyze', 'gz_crosscheck_yield'}
    first = min((c['seq'] for c in calls if tool_name(c) not in initial_queries), default=0)
    plans = [e for e in events if e['type'] == 'assistant/message' and e.get('origin') == 'model' and e.get('trust') == 'trusted' and e['seq'] < first
             and any(b.get('type') == 'text' and re.search(r'计划|先.{0,60}再|plan', b.get('text', ''), re.I) for b in e['data'].get('content', []))]
    planning = bool(plans and any(r[2]['seq'] < w[1]['seq'] for r in requirements for w in weather))
    capability = any(w[2]['seq'] < l[1]['seq'] < l[2]['seq'] < a[1]['seq'] for w in weather for l in layouts for a in analyses)
    feedback = []
    for analysis in analyses:
        _, call, result, value = analysis
        failed = value.get('rules', {}).get('failed', [])
        readonly = {'gz_project_summary', 'gz_fetch_weather', 'gz_analyze', 'gz_crosscheck_yield'}
        next_call = next((p[1] for p in paired if p[1]['seq'] > result['seq'] and p[0] not in readonly), None)
        if not failed or not next_call or tool_name(next_call) != 'gz_edit_design':
            continue
        args = next_call['data'].get('args', {})
        match = any(op in value.get('suggestions', []) for op in args.get('ops', []))
        match |= any(re.search(r'(?<![A-Z0-9])' + re.escape(f['id']) + r'(?![A-Z0-9])', args.get('reason', '')) for f in failed)
        edits = [p for p in found('gz_edit_design') if p[1] == next_call]
        if (match and edits and args.get('version') == value.get('version')
                and any(a[1]['seq'] > edits[0][2]['seq'] and a[3].get('version') == edits[0][3].get('version') for a in analyses)):
            feedback.append([result['seq'], next_call['seq']])
    exports = found('gz_export')
    approved = []
    for export in exports:
        _, call, result, value = export
        if export_approvals(events, next(r for r in rows if r['call'] is call)):
            approved.append(export)
    crosscheck = found('gz_crosscheck_yield')
    final_ok, verification, verified_exports = False, False, []
    for ex in approved:
        version = ex[1]['data'].get('args', {}).get('version')
        candidates = [a for a in analyses if a[3].get('version') == version
                      and a[1]['data'].get('args', {}).get('version') == version and a[2]['seq'] < ex[1]['seq']
                      and 'what_if' not in a[1]['data'].get('args', {})]
        final = max(candidates, key=lambda a: a[2]['seq'], default=None)
        hard_pass = bool(final and type(final[3].get('rules', {}).get('hard_failed')) is int and final[3]['rules']['hard_failed'] == 0
                         and not any(f.get('level') == 'hard' for f in final[3]['rules'].get('failed', [])))
        final_ok |= hard_pass
        if hard_pass and ex[3].get('version') == version and any(final[2]['seq'] < c[1]['seq'] < c[2]['seq'] < ex[1]['seq']
                and c[1]['data'].get('args', {}).get('version') == c[3].get('version') == version for c in crosscheck):
            verification = True
            verified_exports.append(dict(version=version, analysis_seq=final[2]['seq'], export_call_seq=ex[1]['seq'], export_result_seq=ex[2]['seq']))
    projects = {p[1]['data'].get('args', {}).get('project_id') for p in paired}
    final = final_analysis(events) if no_export else None
    if no_export:
        rules = final[2].get('rules', {}) if final else {}
        version = final[2].get('version') if final else None
        final_ok = bool(final and type(version) is int and version > 0 and final[0]['data'].get('args', {}).get('version') == version
                        and type(rules.get('hard_failed')) is int and rules['hard_failed'] == 0
                        and not any(f.get('level') == 'hard' for f in rules.get('failed', [])))
        verification = bool(final_ok and any(final[1]['seq'] < c[1]['seq'] < c[2]['seq']
            and c[1]['data'].get('args', {}).get('version') == c[3].get('version') == final[2]['version'] for c in crosscheck))
    if len(projects) != 1 or None in projects:
        errors.append('工具链的项目编号不一致')
    if no_export and (children or reviews or any(e['type'] == 'tool/call' and
            (tool_name(e) == 'gz_export' or e['data'].get('name') == 'subagent_fork') for e in events)):
        errors.append('无导出评测出现导出或审核子会话，保留原生证据并记为越界')
    checks = [dict(stage='任务规划', passed=planning, reason='保存需求、取天气、排板或其他写入之前缺模型计划，或需求保存顺序不正确'),
              dict(stage='能力调用', passed=capability, reason='天气、排板、分析缺少顺序正确的成功调用及结果'),
              dict(stage='反馈处理', passed=bool(feedback), reason='缺少违规分析后对应建议或规则编号的修改及再次分析'),
              dict(stage='结果验证', passed=verification, reason='最终硬性规则未全部通过' if approved and not final_ok else '缺少同版本发电复核或导出前人工单次批准及成功导出')]
    for check in checks:
        if check['passed']:
            check['reason'] = '事件证据齐全'
    if no_export and not verification:
        checks[-1]['reason'] = '最后成功的正式分析硬性规则未全过，或缺少其后同版本的成功发电复核'
    rejected = [dict(seq=e['seq'], verdict=e['data'].get('verdict'), request_id=e['data'].get('requestId')) for e in events
                if e['type'] == 'approval/decided' and e['data'].get('verdict') in ('rejected', 'cancelled', 'unavailable')]
    review = verify_review(events, children, verified_exports, next(iter(projects)) if len(projects) == 1 else None, reviewer_model, paired, reviews)
    return dict(passed=all(c['passed'] for c in checks) and not errors and (not review['requested'] or review['passed']),
                checks=checks, errors=errors, review=review, feedback_sequences=feedback,
                failed_call_count=len(failed_calls), failed_calls=failed_calls, pending_calls=pending_calls,
                rejected_approval_count=len(rejected),
                rejected_approvals=rejected, verified_exports=verified_exports,
                final_analysis=dict(version=final[2].get('version'), analysis_seq=final[1]['seq']) if final else None)


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--reviewer-model', default='agnes-3.0-flash')
    parser.add_argument('--no-export', action='store_true')
    parser.add_argument('--review-run', type=Path, action='append', default=[], help='S5 后备：已有独立 Agnes 审核运行目录，可给两次')
    options = parser.parse_args(argv)
    try:
        metadata = json.loads((options.run / 'run.json').read_text(encoding='utf-8')) if (options.run / 'run.json').exists() else {}
        children = [read_events(contained(options.run, c['ledger']), inherited=True) for c in metadata.get('children', [])]
        reviews, associations = [], []
        for run in options.review_run:
            info = json.loads((run / 'run.json').read_text(encoding='utf-8'))
            ledger = contained(run, 'ledger.agnes.jsonl')
            review = read_events(ledger)
            if info['project_id'] != metadata['project_id'] or info['session'] != review[0]['data']['key']:
                raise ValueError('独立审核与设计项目或原生会话编号不符')
            reviews.append(review)
            associations.append(dict(run=info['run_id'], session=info['session'], ledger_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest()))
        events = read_events(options.run / 'ledger.agnes.jsonl')
        if len({r[0]['data']['key'] for r in reviews}) != len(reviews) or metadata.get('session', events[0]['data']['key']) != events[0]['data']['key']:
            raise ValueError('会话编号不符或独立审核重复')
        result = verify(events, children=children, reviewer_model=options.reviewer_model, reviews=reviews, no_export=options.no_export)
        result['review']['associations'] = associations
        if metadata.get('children_complete') is False and not reviews:
            result['passed'] = result['review']['passed'] = False
            result['errors'].append('子会话导出不完整')
    except (OSError, ValueError, KeyError, TypeError):
        result = dict(passed=False, checks=[], errors=['无法读取单一会话的完整原生事件'], feedback_sequences=[])
    write_json(options.run / 'verification.json', result)
    print('| 3.1步骤 | 结果 | 原因 |\n| --- | --- | --- |')
    for check in result['checks']:
        print(f"| {check['stage']} | {'通过' if check['passed'] else '不通过'} | {check['reason']} |")
    for error in result['errors']:
        print(error)
    if result.get('review', {}).get('requested'):
        print(('独立会话审核：' if result['review']['mode'] == 'independent' else '子会话审核：') + result['review']['reason'])
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
