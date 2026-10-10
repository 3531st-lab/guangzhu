"""Export a completed AGH session without model requests; retain sanitized evidence."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / 'runtime/agh/agnes-win32-x64.exe' if (ROOT / 'build-manifest.json').is_file() else (
    ROOT.parent / '竞赛/work/agh-runtime-official/runtime-5da4073-03b1998b0818/distribution/agnes-win32-x64.exe')
SECRET = re.compile(
    r'(?i)(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}|\b(?:Bearer|Basic)\s+\S+'
    r'|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+'
    r'|(?:api[_-]?key|secret|access_token)\s*[=:]\s*[^\s,;]+'
)
PRIVATE_FIELD = re.compile(r'(?i).*headers?|authorization|api[_-]?key|password|secret|token|access_token|refresh_token')


def identifier(value, limit=64):
    if not isinstance(value, str) or not re.fullmatch(rf'[A-Za-z0-9][A-Za-z0-9_-]{{0,{limit - 1}}}', value):
        raise ValueError(f'编号只允许字母、数字、下划线和短横线，最长{limit}字符')
    return value


def contained(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('证据路径超出指定目录')
    return path


def sanitize(value):
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items() if not PRIVATE_FIELD.fullmatch(k)}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        if value.lstrip().startswith(('{', '[')):
            try:
                return json.dumps(sanitize(json.loads(value)), ensure_ascii=False, separators=(',', ':'))
            except ValueError:
                pass
        value = SECRET.sub('[REDACTED]', value)
        value = re.sub(re.escape(str(Path.home())), '%USERPROFILE%', value, flags=re.I)
        return re.sub(r'(?i)(?:[A-Z]:[\\/]Users[\\/]|/Users/|/home/)[^\\/\s"<>]+', '%USERPROFILE%', value)
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize(value), ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def read_events(path, *, inherited=False):
    events = [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    if not events or any(not isinstance(e, dict) or type(e.get('seq')) is not int for e in events):
        raise ValueError('记录为空或不是原生事件')
    if len({e['seq'] for e in events}) != len(events) or len({e.get('id') for e in events}) != len(events):
        raise ValueError('记录存在重复事件')
    starts = sorted((e for e in events if e.get('type') == 'session/start'), key=lambda e: e['seq'])
    parent = starts[-1]['data'].get('parent', {}) if starts else {}
    valid_child = (inherited and starts and type(parent.get('boundarySeq')) is int
                   and starts[-1]['seq'] == parent['boundarySeq'] + 1
                   and all(e['seq'] <= parent['boundarySeq'] for e in starts[:-1])
                   and (len(starts) == 1 or parent.get('key') in {e['data'].get('key') for e in starts[:-1]}))
    if len(starts) != 1 and not valid_child:
        raise ValueError('记录须且只能包含一个会话，不能拼接不同会话')
    return sorted(events, key=lambda e: e['seq'])


def own_events(events):
    start = max(e['seq'] for e in events if e['type'] == 'session/start')
    return [e for e in events if e['seq'] >= start]


def tool_name(event):
    match = re.search(r'(?:^|_)(gz_[a-z_]+)$', event.get('data', {}).get('name', ''))
    return match[1] if match else ''


def result_value(event):
    data = event.get('data', {})
    try:
        content = data['content']
        value = json.loads(content[0]['text']) if len(content) == 1 and content[0]['type'] == 'text' else None
        return value if isinstance(value, dict) else {}
    except (KeyError, ValueError, TypeError):
        return {}


def resolve_results(events):
    """Pair native results without mutating evidence or trusting an orphan transport result."""
    scopes, calls, results = {}, {}, {}
    session = None
    for event in sorted(events, key=lambda e: e['seq']):
        if event['type'] == 'session/start':
            session = event['seq']
        scopes[id(event)] = session
        key = (session, event['data'].get('toolUseId'))
        target = calls if event['type'] == 'tool/call' else results if event['type'] == 'tool/result' else None
        if target is not None:
            target.setdefault(key, []).append(event)
    rows, waits, jobs, poisoned = [], [], {}, set()
    for key, group in calls.items():
        for call in group:
            matches = results.get(key, [])
            initial = matches[0] if matches else None
            valid = bool(key[1] and len(group) == 1 and len(matches) == 1 and call['seq'] < initial['seq'])
            value = result_value(initial) if initial else {}
            row = dict(name=tool_name(call), call=call, initial=initial,
                       result=initial if valid and value.get('pending') is not True else None,
                       value=value if valid else {}, pending=value.get('pending') is True, wait_ids=[])
            if not valid:
                claimed = [result_value(result).get('job_id') for result in matches]
                if row['name'] == 'gz_wait':
                    claimed.append(call['data'].get('args', {}).get('job_id'))
                poisoned.update((key[0], job) for job in claimed if isinstance(job, str) and job)
            if row['name'] == 'gz_wait':
                waits.append((row, valid))
            elif row['name']:
                rows.append(row)
                job = value.get('job_id')
                if row['pending'] and isinstance(job, str) and job:
                    jobs.setdefault((key[0], job), []).append((row, valid))
    linked = set()
    for (scope, job), originals in jobs.items():
        signatures = {json.dumps([r['name'], r['call']['data'].get('args', {})], sort_keys=True) for r, _ in originals}
        valid = (scope, job) not in poisoned and len(signatures) == 1 and all(ok and r['value'].get('ok') is True
            and r['initial']['data'].get('isError') is False and r['value'].get('tool') == r['name'] for r, ok in originals)
        candidates, completed = [], []
        for wait, paired in waits:
            args, value = wait['call']['data'].get('args', {}), wait['value']
            raw = result_value(wait['initial']) if wait['initial'] else {}
            if scopes[id(wait['call'])] != scope or job not in (args.get('job_id'), raw.get('job_id')):
                continue
            eligible = [r for r, _ in originals if r['initial']['seq'] < wait['call']['seq']]
            wait['interrupted'] = bool(paired and eligible and wait['initial']['data'].get('code') == 'CANCELLED'
                and wait['initial']['data'].get('isError') is True and args.get('job_id') == job
                and raw.get('job_id') in (None, job) and raw.get('tool') in (None, originals[0][0]['name']))
            if wait['interrupted']:
                candidates.append(wait)
                continue
            valid &= bool(paired and eligible and args.get('job_id') == value.get('job_id') == job
                and value.get('tool') == originals[0][0]['name'] and type(wait['initial']['data'].get('isError')) is bool
                and (not wait['pending'] or value.get('ok') is True and wait['initial']['data']['isError'] is False))
            candidates.append(wait)
            if not wait['pending']:
                completed.append(wait)
        if not valid:
            continue
        bodies = {json.dumps([w['initial']['data'].get('isError'),
            {k: v for k, v in w['value'].items() if k not in ('tool', 'job_id')}], sort_keys=True) for w in completed}
        if len(bodies) > 1:
            continue
        for row, _ in originals:
            eligible = [w for w in candidates if row['initial']['seq'] < w['call']['seq']]
            row['wait_ids'] = [w['call']['data']['toolUseId'] for w in eligible]
            linked.update(id(w['call']) for w in eligible)
            final = min((w for w in eligible if not w['pending'] and not w.get('interrupted')),
                        key=lambda w: w['initial']['seq'], default=None)
            if final:
                row.update(result=final['initial'], value={k: v for k, v in final['value'].items() if k not in ('tool', 'job_id')},
                           pending=False)
    return sorted(rows, key=lambda r: r['call']['seq']), [w['call'] for w, _ in waits if id(w['call']) not in linked]


def summarize(events):
    requests = [e for e in events if e['type'] == 'request/sent']
    costs = {e['data']['effectId']: e['data'] for e in events if e['type'] == 'cost/ledger' and not e['data'].get('adjustment')}
    return dict(models=[json.loads(m) for m in sorted({json.dumps(e['data'].get('model'), sort_keys=True) for e in requests})],
                started_at=events[0].get('ts'), ended_at=events[-1].get('ts'), model_requests=len(requests),
                tokens={k: sum(c.get('tokens', {}).get(k, 0) for c in costs.values()) for k in ('input', 'output', 'cacheRead', 'cacheWrite', 'reasoning')},
                tool_calls=dict(Counter(tool_name(e) or e['data'].get('name', '') for e in events if e['type'] == 'tool/call')))


def timeline(events, children=()):
    nodes = []
    def clipped(value, limit):
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        return text.encode('utf-8')[:limit].decode('utf-8', errors='ignore')
    for ledger in [events, *children]:
        own = own_events(ledger)
        session = own[0]['data']['key']
        calls, results, asks = {}, {}, {}
        for event in own:
            target = {'tool/call': calls, 'tool/result': results, 'approval/asked': asks}.get(event['type'])
            if target is not None:
                key = event['data'].get('requestId' if event['type'] == 'approval/asked' else 'toolUseId')
                target.setdefault(key, []).append(event)
        for event in own:
            kind, data = event['type'], event['data']
            node = dict(session=session, seq=event['seq'], ts=event.get('ts'))
            if kind == 'assistant/message':
                node.update(kind='text', text=''.join(b.get('text', '') for b in data.get('content', []) if b.get('type') == 'text'))
                if not node['text']:
                    continue
            elif kind == 'tool/call':
                matches = results.get(data['toolUseId'], [])
                result = matches[0] if len(matches) == 1 else {}
                content = result.get('data', {}).get('content', [])
                node.update(kind='tool', name=tool_name(event) or data['name'], tool_use_id=data['toolUseId'],
                    args=clipped(data.get('args', {}), 1024), result=clipped(''.join(b.get('text', '') for b in content if b.get('type') == 'text'), 2048),
                    args_json=data.get('args', {}), result_json=result_value(result), isError=result.get('data', {}).get('isError'),
                    result_code=result.get('data', {}).get('code'),
                    started_at=event.get('ts'), ended_at=result.get('ts'), result_seq=result.get('seq'),
                    status='error' if result.get('data', {}).get('isError') else 'completed' if result else 'running')
                if len(matches) > 1:
                    # The second result establishes ambiguity; later results add only newly observed claims.
                    ordered = sorted(matches, key=lambda match: match['seq'])
                    jobs, evidence, truncated = set(), [], False
                    for index, match in enumerate(ordered[1:]):
                        claims = [result_value(match).get('job_id')]
                        if index == 0:
                            claims.append(result_value(ordered[0]).get('job_id'))
                            if tool_name(event) == 'gz_wait':
                                claims.append(data.get('args', {}).get('job_id'))
                        added = []
                        for job in claims:
                            if not isinstance(job, str) or not job or job in jobs:
                                continue
                            if len(job.encode('utf-8')) > 128 or len(jobs) == 64:
                                truncated = True
                            else:
                                jobs.add(job)
                                added.append(job)
                        if added or truncated or index == 0:
                            evidence.append(dict(seq=match['seq'], ts=match.get('ts'), job_ids=added, truncated=truncated))
                        if truncated:
                            # The whole session is now invalid, so later deltas cannot change its outcome.
                            break
                    node.update(invalid_job_ids=sorted(jobs), invalid_jobs_truncated=truncated, invalid_job_events=evidence,
                                conflict_seq=ordered[1]['seq'], conflict_at=ordered[1].get('ts'))
            elif kind in ('approval/asked', 'approval/decided'):
                matches = asks.get(data.get('requestId'), [])
                ask = matches[0] if len(matches) == 1 and (kind == 'approval/asked' or matches[0]['seq'] < event['seq']) else {}
                matches = calls.get(ask.get('data', {}).get('toolUseId'), [])
                call = matches[0] if len(matches) == 1 and matches[0]['seq'] < ask['seq'] else {}
                node.update(kind='approval', tool=tool_name(call) or call.get('data', {}).get('name', ''),
                    tool_use_id=call.get('data', {}).get('toolUseId'), args_json=sanitize(call.get('data', {}).get('args', {})),
                    request_id=data.get('requestId'), pending=kind == 'approval/asked', verdict=data.get('verdict'),
                    via=data.get('via'), options=data.get('options', []))
            else:
                continue
            nodes.append(node)
        if ledger is not events:
            ends = [e for e in own if e['type'] == 'turn/end']
            for phase, event in [('started', own[0])] + ([('ended', ends[-1])] if ends else []):
                nodes.append(dict(kind='child', phase=phase, session=session, seq=event['seq'], ts=event['ts'],
                    parent=own[0]['data'].get('parent', {}).get('key'), models=summarize(own)['models']))
    return dict(schema='guangzhu.timeline/1', nodes=sorted(nodes,
                key=lambda n: (datetime.fromisoformat(n['ts'].replace('Z', '+00:00')), n['session'], n['seq'])))


def final_analysis(events):
    candidates = [(r['call'], r['result'], r['value']) for r in resolve_results(events)[0]
                  if r['name'] == 'gz_analyze' and 'what_if' not in r['call']['data'].get('args', {})
                  and r['result'] and r['result']['data'].get('isError') is False and r['value'].get('ok') is True]
    return max(candidates, key=lambda row: row[1]['seq'], default=None)


def snapshot(events, project_id, destination, projects, anomalies=None, *, lean=False):
    anomalies = [] if anomalies is None else anomalies
    try:
        source = contained(projects, identifier(project_id))
    except ValueError:
        anomalies.append(dict(message='项目路径不安全，未复制其文件'))
        return {}
    versions = set()
    def collect(value, allow_empty=False, seq=None):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('version', 'base_version'):
                    if key == 'version' and item is None and allow_empty:
                        continue
                    if type(item) is not int or item < 1:
                        anomalies.append(dict(seq=seq, message='引用的方案版本号不合法'))
                        continue
                    versions.add(item)
                else:
                    collect(item, allow_empty, seq)
        elif isinstance(value, list):
            for item in value:
                collect(item, allow_empty, seq)
    rows, unlinked = resolve_results(events)
    anomalies.extend(dict(seq=c['seq'], message='等待结果无法关联原调用') for c in unlinked)
    for row in rows:
        event = row['call']
        if event['data'].get('args', {}).get('project_id') != project_id:
            anomalies.append(dict(seq=event['seq'], message='调用引用了其他项目，未复制其文件'))
            continue
        collect(event['data']['args'], seq=event['seq'])
        if row['result']:
            collect(row['value'], allow_empty=True, seq=row['result']['seq'])
    final = final_analysis(events) if lean else None
    if lean:
        version = final[2].get('version') if final else None
        versions = {version} if type(version) is int and version > 0 else set()
    pending, available = ([], versions) if lean else (list(versions), set())
    while pending:
        version = pending.pop()
        try:
            record = json.loads(contained(source, f'designs/v{version}.json').read_text(encoding='utf-8'))
            if not isinstance(record, dict) or type(record.get('version')) is not int or record['version'] != version:
                raise ValueError
        except (OSError, ValueError, TypeError):
            anomalies.append(dict(version=version, message='引用方案不存在、损坏或路径不安全'))
            continue
        available.add(version)
        parent = record.get('parent_version')
        if parent is not None:
            if type(parent) is not int or not 0 < parent < version:
                anomalies.append(dict(version=version, message='父版本须是更早的正整数版本，未跟随异常引用'))
                continue
            if parent not in versions:
                versions.add(parent)
                pending.append(parent)
    files, binaries = [], {}
    for version in sorted(available):
        try:
            if not lean:
                files += [contained(source, f'designs/v{version}.json')]
            files += [p for p in [contained(source, f'analysis/v{version}/{name}.json') for name in ('summary', 'rules')] if p.exists()]
            if lean:
                continue
            files += list(contained(source, 'reviews').glob(f'v{version}-*.json'))
            export = contained(source, f'exports/v{version}')
            if (export / 'manifest.json').exists():
                files += list(export.glob('*.json'))
                manifest = json.loads(contained(export, 'manifest.json').read_bytes())
                if not isinstance(manifest, dict) or not isinstance(manifest.get('files'), dict):
                    raise ValueError('交付物manifest格式不正确')
                for name in (f'layout-v{version}.dxf', f'bom-v{version}.xlsx'):
                    if manifest.get('version') == version and name in manifest.get('files', {}):
                        binary = contained(export, name)
                        if binary.parent != export or binary.name != name:
                            raise ValueError('交付物链接改变了批准的文件名')
                        binaries[binary] = manifest['files'][name]
                        files.append(binary)
        except (OSError, ValueError):
            anomalies.append(dict(version=version, message='部分证据路径不安全，已跳过'))
    hashes = {}
    for path in sorted(set(files)):
        try:
            path = contained(source, path.relative_to(source))
            original = path.read_bytes()
            target = contained(destination, Path('project') / path.relative_to(source))
            target.parent.mkdir(parents=True, exist_ok=True)
            if path in binaries:
                if hashlib.sha256(original).hexdigest() != binaries[path]:
                    raise ValueError('交付物与批准的manifest SHA不一致')
                target.write_bytes(original)
            else:
                value = json.loads(original)
                clean = sanitize(value)
                if path.name == 'manifest.json':
                    clean = clean | {'snapshot_note': 'files.sha256属于原导出件；脱敏快照的实际SHA256以run.json的artifacts为准。'}
                if clean == value:
                    target.write_bytes(original)
                else:
                    write_json(target, clean)
            hashes[target.relative_to(destination).as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
        except (OSError, ValueError, TypeError):
            anomalies.append(dict(file=path.name, message='证据无法安全复制，已跳过'))
    return hashes


def export_ledger(session, ledger, executable, *, inherited=False, env=None, profile=None):
    binding = ['--profile', profile] if profile else []
    subprocess.run([str(executable), 'export', session, *binding, '--format', 'agnes', '--out', str(ledger)],
                   check=True, capture_output=True, env=env)
    events = sanitize(read_events(ledger, inherited=inherited))
    ledger.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events), encoding='utf-8', newline='\n')
    return events


def export_run(session, project_id, run_id, *, root=ROOT, executable=OFFICIAL, with_children=False,
               destination=None, lean=False, env=None, profile=None):
    project_id = identifier(project_id)
    if not session or session.startswith('-') or '\x00' in session or not (os.environ if env is None else env).get('AGH_HOME'):
        raise ValueError('填写会话编号，并先设置独立实例的 AGH_HOME')
    identifier(run_id, limit=67 if destination is not None else 64)
    destination = contained(root / 'runs', destination if destination is not None else run_id)
    destination.mkdir(parents=True, exist_ok=lean and not (destination / 'run.json').exists())
    ledger = destination / 'ledger.agnes.jsonl'
    binding = dict(env=env, profile=profile) if env is not None or profile else {}
    events = export_ledger(session, ledger, executable, **binding)
    anomalies = []
    metadata = summarize(events) | dict(session=session, project_id=identifier(project_id), run_id=run_id, anomalies=anomalies,
                                      artifacts=snapshot(events, project_id, destination, root / 'projects', anomalies, lean=lean))
    if lean:
        final = final_analysis(events)
        version = final[2].get('version') if final else None
        metadata.update(lean=True, final_version=version, final_analysis=dict(version=version,
            summary=f'project/analysis/v{version}/summary.json', rules=f'project/analysis/v{version}/rules.json') if final else {})
    children = []
    if with_children:
        metadata.update(children=[], children_errors=[], children_complete=False)
        def child_failure(error, child_id=None):
            denied = 'CAPABILITY_DENIED' in str(getattr(error, 'stderr', ''))
            metadata['children_errors'].append(dict(session=child_id,
                error_code='CAPABILITY_DENIED' if denied else 'CHILDREN_EXPORT_FAILED',
                message='AGH拒绝子会话访问；未改变权限，父会话证据已保留' if denied else '子会话发现或导出失败；父会话证据已保留'))
        try:
            child_ids = sorted({e['data']['childKey'] for e in events if e['type'] == 'subagent/cost'
                                and e.get('origin') == 'system' and e.get('trust') == 'trusted'})
            if not child_ids and any(e['type'] == 'tool/call' and e['data'].get('name') == 'subagent_fork' for e in events):
                command = [str(executable), 'sessions', 'list', *(['--profile', profile] if profile else []), '--json']
                page = json.loads(subprocess.run(command, check=True, env=env,
                                                 capture_output=True, text=True, encoding='utf-8-sig').stdout)
                if page.get('next'):
                    raise ValueError('原生列表有未读分页，不能宣称子会话已全部导出')
                child_ids = [row.get('sessionId') for row in page['items']]
            prefixes = [f"{session}:{e.get('lane', 'main')}:{e['data']['toolUseId']}:" for e in events
                        if e['type'] == 'tool/call' and e['data'].get('name') == 'subagent_fork']
            for child_id in child_ids:
                if not isinstance(child_id, str) or not child_id.startswith(session + '/'):
                    continue
                if not isinstance(child_id, str) or not child_id or child_id.startswith('-') or '\x00' in child_id:
                    raise ValueError('原生子会话编号不合法')
                target = contained(destination, 'children/' + quote(child_id, safe='-_') + '.ledger.agnes.jsonl')
                target.parent.mkdir(exist_ok=True)
                if target.exists():
                    raise ValueError('原生子会话列表重复')
                try:
                    child = export_ledger(child_id, target, executable, inherited=True, **binding)
                except (OSError, ValueError, subprocess.SubprocessError) as error:
                    child_failure(error, child_id)
                    continue
                own = own_events(child)
                start, delegation = own[0]['data'], own[0]['data'].get('delegation', {})
                if (start.get('key') != child_id or start.get('parent', {}).get('key') != session
                        or delegation.get('kind') != 'fork' or not any(delegation.get('creationId', '').startswith(p) for p in prefixes)):
                    unassociated = contained(destination, 'unassociated/' + target.name)
                    unassociated.parent.mkdir(exist_ok=True)
                    target.replace(unassociated)
                    anomalies.append(dict(session=child_id, ledger=unassociated.relative_to(destination).as_posix(),
                                          message='候选记录缺少与父工具调用对应的原生 fork 关系，保留但不接纳为子会话'))
                    continue
                metadata['children'].append(summarize(own) | dict(session=child_id, parent=session, ledger=target.relative_to(destination).as_posix(),
                                                                ledger_sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
                children.append(child)
                if not lean:
                    metadata['artifacts'].update(snapshot(own, project_id, destination, root / 'projects', anomalies))
                else:
                    anomalies.append(dict(session=child_id, message='评测出现意外子会话；已保留原生账本并记为越界'))
            if prefixes and not children and not metadata['children_errors']:
                child_failure(ValueError('未发现可导出的子会话'))
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            child_failure(error)
        metadata['children_complete'] = not metadata['children_errors']
    write_json(destination / 'timeline.json', timeline(events, children))
    write_json(destination / 'run.json', metadata)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('session', 'project', 'run-id'):
        parser.add_argument('--' + field, required=True)
    parser.add_argument('--with-children', action='store_true')
    parser.add_argument('--lean', action='store_true')
    options = parser.parse_args(argv)
    try:
        path = export_run(options.session, options.project, options.run_id, with_children=options.with_children, lean=options.lean)
        metadata = json.loads((path / 'run.json').read_text(encoding='utf-8'))
        complete = metadata.get('children_complete', True)
        print(json.dumps(dict(ok=complete, run=str(path.relative_to(ROOT)),
                             children_errors=metadata.get('children_errors', [])), ensure_ascii=False))
        if not complete:
            print('子会话导出不完整；父ledger、run.json和timeline.json已保留。')
        return 0 if complete else 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print('导出失败：检查会话编号、AGH_HOME、运行包位置和本地项目证据；不读取密钥。')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
