"""Serial T13 evaluation driver; --plan is offline, real runs require a running desktop."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from guangzhu import mcp_actions, project as storage
from guangzhu.models import LayoutParams
from guangzhu.templates import resolve
from guangzhu.code_identity import current_identity
from agh_export_run import OFFICIAL, ROOT, export_ledger, read_events, result_value, sanitize, summarize, timeline, write_json

URL = 'http://127.0.0.1:8765/?eval=1'
DESIGN_MODEL = 'deepseek-flash'
AGH_HOME = ''
CUTOFF = datetime(2026, 10, 7, 14, tzinfo=timezone.utc)
OBSERVER = """window.__evalMessages = [];
window.__evalModels = [];
addEventListener('message', e => {
  if (e.origin === 'http://127.0.0.1:4177' && e.source === document.querySelector('#agh')?.contentWindow && e.data?.v === 1) {
    window.__evalMessages.push(e.data);
    if (e.data.type === 'gz.ready') {
      window.__evalModels = e.data.models;
    }
  }
});"""
FIELDS = dict(payback='payback_years_max', budget='budget_cny_max', capMin='capacity_kw_min', capMax='capacity_kw_max',
              walkway='walkway_m_min', obstacle='obstacle_clearance_m_min', edge='edge_setback_m_min', notes='notes',
              capex='capex_cny_per_w', priceSelf='price_self_cny_kwh', priceExport='price_export_cny_kwh', selfUse='self_use_ratio')


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()] if path.exists() else []


def append(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(sanitize(value), ensure_ascii=False, allow_nan=False) + '\n')


def audit(action, **data):
    append(ROOT / 'reports/assets/T13-agh-commands.log', dict(ts=datetime.now(timezone.utc).isoformat(), action=action, **data))


def plan(cases, date, stage, tag=''):
    smoke = [next(c for c in cases if c['collection'] == kind) for kind in ('real', 'boundary', 'impossible')]
    stages = dict(smoke=[(c, m, 1) for c in smoke for m in 'ABC'], abc=[(c, m, 1) for m in 'ABC' for c in cases],
                  repeat=[(c, m, n) for n in (2, 3) for m in 'CB' for c in cases], e=[(c, 'E', 1) for c in cases],
                  d=[(c, 'D', n) for n in (1, 2, 3) for c in cases if c['half'] == 2])
    selected = sum(stages.values(), []) if stage == 'all' else stages[stage]
    prefix = f"eval-{date[5:7]}{date[8:10]}" + (f'-{tag}' if tag else '')
    return list({f"{prefix}-{c['id']}-{m}-{n}": (c, m, n) for c, m, n in selected}.items())


def preflight(path):
    receipt = json.loads(path.read_text(encoding='utf-8-sig'))
    identity, probe, actual = receipt['identity'], receipt['probe']['code_identity'], current_identity()
    keys = ('commit', 'source_sha256', 'skill_rules_sha256')
    if any(item.get('dirty') is not False for item in (identity, probe, actual)) or any(
            not actual.get(key) or not identity.get(key) == probe.get(key) == actual[key] for key in keys):
        raise RuntimeError('Preflight requires the same clean committed code and frozen Skill rules')
    process = receipt['process']
    templates = {case['template'] for case in json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8'))}
    if receipt['probe'].get('ok') is not True or receipt['probe'].get('created') is not True or receipt['template'] not in templates or (
            type(identity['process_id']) is not int or type(receipt['previous_process_id']) is not int
            or identity['process_id'] == receipt['previous_process_id'] or identity['process_id'] != process['pid']
            or datetime.fromisoformat(identity['started_at']) < datetime.fromisoformat(receipt['reconnected_at'])):
        raise RuntimeError('Preflight requires a successful new-template probe after official reconnect')
    command = '[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n'
    command += f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {identity['process_id']}').CommandLine"
    active = subprocess.run(['powershell', '-NoProfile', '-Command', command], capture_output=True, text=True, encoding='utf-8', check=True)
    if active.stdout.strip() != process['command_line'] or 'guangzhu.mcp_server' not in active.stdout:
        raise RuntimeError('Preflight MCP process changed or exited; reconnect and probe again')
    return identity


def costs(paths):
    seen, incomplete = {}, False
    for path in set(paths):
        metadata_path = path.parent / 'run.json'
        metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if path.name == 'ledger.agnes.jsonl' and metadata_path.is_file() else {}
        incomplete |= bool(metadata.get('children_errors')) or metadata.get('children_complete') is False or any(
            not (path.parent / item['ledger']).is_file() for item in metadata.get('children', []) if item.get('ledger'))
        events = rows(path)
        if not events:
            incomplete = True
        bills = [e for e in events if e.get('type') == 'cost/ledger' and not e.get('data', {}).get('adjustment')]
        inference = {e['data'].get('effectId') for e in bills if e['data'].get('purpose') == 'inference'}
        incomplete |= sum(e.get('type') == 'request/sent' for e in events) > len(inference)
        for event in bills:
            data = event['data']
            if event.get('origin') != 'system' or event.get('trust') != 'trusted' or not isinstance(data.get('effectId'), str) or not data['effectId']:
                raise ValueError('Untrusted billing record')
            key = data['effectId']
            bill = data.get('billing') if isinstance(data.get('billing'), dict) else {}
            if key in seen and seen[key] != data:
                raise ValueError('Conflicting billing effectId')
            seen[key] = data
            incomplete |= bill.get('source') != 'estimated' or type(bill.get('usdMicros')) is not int or bill.get('usdMicros', -1) < 0
    amounts = [c['billing'] for c in seen.values() if isinstance(c.get('billing'), dict)]
    return sum(b['usdMicros'] for b in amounts if b.get('source') == 'estimated' and type(b.get('usdMicros')) is int and b['usdMicros'] >= 0), incomplete


def guard(paths, model=True, now=None):
    micros, incomplete = costs(paths)
    incomplete |= any(r.get('method') != 'A' and (r.get('session') or r.get('evidence_error')) and not (
        ROOT / r['archive'] / 'ledger.agnes.jsonl').is_file() for journal in (ROOT / 'eval/results').glob('*/attempts.jsonl') for r in rows(journal))
    if (now or datetime.now(timezone.utc)) >= CUTOFF or micros > 6_000_000 or model and (incomplete or micros > 5_500_000):
        raise RuntimeError('Cutoff or billing guard: no new run; unknown charges are not zero')
    return micros


def backend(case, project_id, folder, params):
    def call(name, **args):
        call_id = str(len(rows(folder / 'execution.jsonl')) + 1)
        append(folder / 'execution.jsonl', dict(origin='external:eval-driver', type='backend/call', data=dict(callId=call_id, name=name, args=args)))
        try:
            value = mcp_actions.dispatch(name, args)
        except Exception as error:
            value = error.as_dict() if hasattr(error, 'as_dict') else dict(ok=False, error=type(error).__name__)
            append(folder / 'execution.jsonl', dict(origin='external:eval-driver', type='backend/result', data=dict(callId=call_id, isError=True, value=value)))
            raise
        append(folder / 'execution.jsonl', dict(origin='external:eval-driver', type='backend/result', data=dict(callId=call_id, isError=False, value=value)))
        return value
    call('gz_new_project', project_id=project_id, template=case['template'], economics=case['economics'])
    req = call('gz_set_requirements', project_id=project_id, text=case['text'], structured=case['structured'])
    settings = dict(params)
    string_size = settings.pop('modules_per_string', None)
    version = call('gz_generate_layout', project_id=project_id, params=settings)['version']
    if string_size is not None:
        version = call('gz_edit_design', project_id=project_id, version=version, reason='B single supplied string size',
                       ops=[dict(op='set_string_size', modules_per_string=string_size)])['version']
    result = call('gz_analyze', project_id=project_id, version=version, offline=True)
    for name in ('summary', 'rules'):
        write_json(folder / f'{name}.json', json.loads(storage._path(project_id, f'analysis/v{version}/{name}.json').read_text(encoding='utf-8')))
    final = dict(version=version, summary='summary.json', rules='rules.json')
    append(folder / 'execution.jsonl', dict(origin='external:eval-driver', type='driver/final', data=dict(text=json.dumps(dict(
        default_result=result, contradictions=req.get('contradictions', [])), ensure_ascii=False))))
    return final


def prompt(case, identifier):
    project = json.loads(resolve(case['template']).read_text(encoding='utf-8'))
    inputs = {key: case[key] for key in ('text', 'structured', 'economics')}
    inputs['roof'] = {key: project[key] for key in ('site', 'roof', 'equipment', 'economics')}
    schema = LayoutParams.model_json_schema()
    return identifier + '\n不要调用任何工具，也不要读 Skill。只输出一个排板参数 JSON，不解释，不加代码围栏。' + json.dumps(dict(
        input=inputs, layout_schema=schema, optional_modules_per_string='positive integer; set_string_size applied before analysis'), ensure_ascii=False)


def messages(page):
    return page.evaluate('window.__evalMessages.splice(0)')


def model_select(page, model):
    page.locator('#settings-open').click()
    page.locator('#design-model').select_option(model['route'] + '/' + model['id'])
    page.locator('#settings-close').click()
    audit('ui:model-select', model=model)


def fill(page, case, identifier, method):
    page.goto(URL)
    page.wait_for_function("window.__evalMessages.some(m=>m.type==='gz.ready')", timeout=30000)
    public = messages(page)
    models = next(m['models'] for m in public if m['type'] == 'gz.ready')
    flash = next(m for m in models if m['id'] == DESIGN_MODEL)
    model = next(m for m in models if m['id'] == 'agnes-3.0-flash') if method == 'E' else flash
    model_select(page, model)
    page.locator(f'[data-roof="{case["template"]}"]').click()
    if method == 'B':
        page.locator('[data-mode="chat"]').click()
    page.locator('a[href="#form"]').click()
    values = case['structured'] | case['economics']
    for field, key in FIELDS.items():
        value = values.get(key, '')
        if value != '' and field in ('budget', 'selfUse'):
            value = value / 10000 if field == 'budget' else value * 100
        page.locator(f'[data-field="{field}"]').fill(str(value))
    for field, value in dict(id=identifier, text=case['text'], tiltMin=values.get('tilt_deg_range', ['', ''])[0],
                             tiltMax=values.get('tilt_deg_range', ['', ''])[1]).items():
        page.locator(f'[data-field="{field}"]').fill(str(value))
    for key in values.get('keep_clear_ids', []):
        page.locator(f'[data-keep="{key}"]').click()
    page.locator('[data-field="maxRounds"]').select_option('6')
    for field in ('compare', 'review', 'exportOn'):
        page.locator(f'[data-field="{field}"]').set_checked(False)
    messages(page)
    return model, flash


def approval(page, pending, method, session):
    card = page.frame_locator('#agh').locator('#approval')
    if not session or not card.is_visible():
        return False
    summary = card.locator('[data-approval-key] > p').first
    named = re.match(r'^([A-Za-z][A-Za-z0-9_]*)\s*(?:\{|$)', summary.inner_text().strip()) if summary.count() else None
    tool = named[1] if named else pending.get('tool', '') if pending.get('pending') and pending.get('session_id') == session else ''
    if not tool:
        return False
    allowed = method != 'B' and (re.fullmatch(r'(?:.*_)?gz_[a-z_]+', tool) or tool == 'skill_read') and not tool.endswith('gz_export')
    label = '本会话允许' if allowed else '拒绝'
    audit('ui:approval', tool=tool, decision='allowed-session' if allowed else 'rejected')
    card.get_by_role('button', name=label, exact=True).click()
    pending.clear()
    return not allowed


def finish(page, folder, identifier, session, idle=False):
    from playwright.sync_api import TimeoutError as LocatorTimeout
    archived = folder.parent / identifier
    clicked = False
    for _ in range(30):
        if (archived / 'verification.json').exists() and (archived / 'ledger.agnes.jsonl').exists():
            metadata = json.loads((archived / 'run.json').read_text(encoding='utf-8'))
            if metadata.get('session') != session:
                raise ValueError('Automatic archive session mismatch')
            return dict(archive_path=archived.relative_to(ROOT).as_posix(), session_id=session)
        idle |= any(m.get('session_id') == session and m.get('op') == 'idle' for m in messages(page))
        button = page.locator('[data-action="finish-retry"]')
        try:
            if not clicked and idle and button.is_visible() and button.is_enabled(timeout=1000):
                button.click(timeout=1000)
                clicked = True
        except LocatorTimeout:
            pass
        page.wait_for_timeout(1000)
    raise RuntimeError('Product finish failed; native fallback is incomplete evidence')


def execute(page, case, identifier, method, folder, baseline, timeout=900):
    session, process, result, status, pending, progress = None, None, None, 'completed', {}, {}
    try:
        model, flash = fill(page, case, identifier, method)
    except Exception as error:
        return dict(session=None, status='failed', error=type(error).__name__, pre_request_failure=True,
                    environment_failure=True, environment_reason='bridge-form', configuration_error=isinstance(error, StopIteration))
    started = time.monotonic()
    live, events, error, evidence_error, restore_error, environment_failure = 0, None, None, False, False, False
    environment_reason = None
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            audit('ui:start', title=identifier, method=method)
            page.locator('[data-action="start"]').click()
            while time.monotonic() - started < timeout:
                for message in messages(page):
                    if message['type'] == 'gz.session':
                        session = message['session_id']
                    if message['type'] == 'gz.error':
                        status = 'failed'
                    if message.get('session_id') == session and message['type'] == 'gz.progress':
                        progress = message
                        live = max(live, sum(c['micros'] for c in (message.get('usage') or {}).get('costs', []) if c['currency'] == 'USD'))
                    if message.get('session_id') == session and message['type'] == 'gz.approval':
                        pending = message
                if session and method == 'B' and process is None:
                    initial = export_ledger(session, folder / 'ledger.agnes.jsonl', OFFICIAL)
                    if any(e['type'] == 'request/sent' for e in initial):
                        raise ValueError('B blank UI session already sent a model request')
                    command = [str(OFFICIAL), '-p', '--mode', 'json', '--meta', '--resume', session,
                               '--model', 'primary=' + model['route'] + '/' + model['id']]
                    audit('cli:prompt', command=command, session=session, title=identifier)
                    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                               cwd=ROOT, env=os.environ | dict(AGH_HOME=AGH_HOME))
                    process.stdin.write(prompt(case, identifier).encode('utf-8'))
                    process.stdin.close()
                if approval(page, pending, method, session):
                    status = 'violation'
                if baseline + live > 5_800_000:
                    status = 'budget'
                if status != 'completed' or method == 'B' and process and process.poll() is not None:
                    break
                if method != 'B' and progress.get('op') == 'idle' and progress.get('nodes'):
                    break
                page.wait_for_timeout(1000)
            else:
                status = 'timeout'
        except (Exception, KeyboardInterrupt) as caught:
            status, error = ('interrupted' if isinstance(caught, KeyboardInterrupt) else 'failed'), type(caught).__name__
            environment_failure = True
            environment_reason = 'ui-run'
        finally:
            for message in messages(page):
                if message['type'] == 'gz.session':
                    session = message['session_id']
            if status != 'completed' and session:
                try:
                    if page.locator('[data-action="cancel"]').is_enabled():
                        audit('ui:stop', session=session, reason=status)
                        page.locator('[data-action="cancel"]').click()
                        page.wait_for_timeout(2000)
                except Exception as caught:
                    evidence_error, error = True, type(caught).__name__
            if process:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=10)
                stdout.seek(0)
                stderr.seek(0)
                receipt = stdout.read().decode('utf-8-sig', errors='replace')
                write_json(folder / 'cli-output.json', dict(stdout=receipt, stderr=stderr.read().decode('utf-8-sig', errors='replace')))
                try:
                    result = json.loads(receipt)
                    write_json(folder / 'cli-result.json', result)
                    if result.get('v') != 'agnes-cli-result/v1' or result.get('sessionId') != session:
                        raise ValueError('Unexpected native CLI receipt')
                    if status == 'completed' and result['exitCode'] != 0:
                        status = 'failed'
                except (ValueError, KeyError):
                    status = 'failed' if status == 'completed' else status
            try:
                if session:
                    if method != 'B':
                        result = finish(page, folder, identifier, session, idle=progress.get('op') == 'idle')
                        events = rows(ROOT / result['archive_path'] / 'ledger.agnes.jsonl')
                    else:
                        events = export_ledger(session, folder / 'ledger.agnes.jsonl', OFFICIAL)
                        write_json(folder / 'timeline.json', timeline(events))
                        write_json(folder / 'run.json', summarize(events) | dict(session=session, project_id=identifier, run_id=identifier))
                    requests = [e for e in events if e['type'] == 'request/sent']
                    tools = [e['data'].get('name', '') for e in events if e['type'] == 'tool/call' and e.get('origin') == 'model']
                    forbidden = any(not re.fullmatch(r'(?:.*_)?gz_[a-z_]+|skill_read', name) or name.endswith('gz_export') for name in tools)
                    wrong_model = any({k: e['data'].get('model', {}).get(k) for k in ('route', 'id')} !=
                                      {k: model[k] for k in ('route', 'id')} for e in requests)
                    permanent = any(e['type'] == 'approval/decided' and e['data'].get('verdict') == 'allowed-permanent' for e in events)
                    if wrong_model or permanent or method == 'B' and (len(requests) > 1 or status == 'completed' and not requests):
                        status, environment_failure = 'failed', True
                        environment_reason = 'model-setting-or-approval'
                    if status == 'violation' and not (forbidden or method == 'B' and tools):
                        status, environment_failure, environment_reason = 'failed', True, 'driver-approval'
                    if forbidden or method == 'B' and tools:
                        status = 'violation'
                    if status == 'completed' and any(e['type'] == 'turn/end' and e['data'].get('reason') == 'error' for e in events):
                        status = 'failed'
            except Exception as caught:
                environment_reason = environment_reason or 'archive'
                evidence_error, error, environment_failure = True, type(caught).__name__, True
                if status == 'completed':
                    status = 'failed'
                if session:
                    try:
                        events = export_ledger(session, folder / 'ledger.agnes.jsonl', OFFICIAL)
                        write_json(folder / 'timeline.json', timeline(events))
                    except Exception:
                        events = None
                    evidence_error = events is None or costs([folder / 'ledger.agnes.jsonl'])[1]
                    if environment_reason == 'archive' and events is not None and not any(e['type'] == 'tool/result' and
                            result_value(e).get('ok') is True and 'rules' in result_value(e) for e in events):
                        environment_failure = False
                    write_json(folder / 'run.json', dict(session=session, project_id=identifier, run_id=identifier, evidence_complete=False))
                    write_json(folder / 'verification.json', dict(scope='driver-fallback', passed=None, error=error))
            finally:
                if method == 'E':
                    try:
                        model_select(page, flash)
                    except Exception as caught:
                        restore_error, error = True, type(caught).__name__
    evidence_error |= session is None
    return dict(session=session, status=status, result=result, error=error, evidence_error=evidence_error, restore_error=restore_error,
                environment_failure=environment_failure or restore_error,
                environment_reason=environment_reason or ('restore-model' if restore_error else None),
                pre_request_failure=status == 'failed' and events is not None and not any(e['type'] == 'request/sent' for e in events))


def run(cases, options, page=None):
    from eval_score import attempt_score
    destination = ROOT / 'eval/results' / options.date
    attempts = destination / 'attempts.jsonl'
    if getattr(options, 'pause_file', destination / 'PAUSE').exists():
        return
    snapshot = [dict(case, template_sha256=hashlib.sha256(resolve(case['template']).read_bytes()).hexdigest()) for case in cases]
    snapshot_path = destination / 'cases.json'
    if snapshot_path.exists() and json.loads(snapshot_path.read_text(encoding='utf-8')) != snapshot:
        raise RuntimeError('Case dataset changed; retain its snapshot and use a new evaluation directory')
    if not snapshot_path.exists():
        write_json(snapshot_path, snapshot)
    identity = preflight(getattr(options, 'preflight', ROOT / 'reports/assets/T13-preflight.json'))
    keys = ('commit', 'source_sha256', 'skill_rules_sha256')
    if any(any((r.get('code_identity') or {}).get(key) != identity[key] for key in keys) for r in rows(attempts)):
        raise RuntimeError('Mixed code versions cannot share an evaluation directory')
    repairs = getattr(options, 'repair_id', [])
    if any(r.get('evidence_error') and r['id'] not in repairs for r in rows(attempts)):
        raise RuntimeError('Resolve earlier incomplete evidence before new model charges')
    for identifier, (case, method, repeat) in plan(cases, options.date, options.stage, getattr(options, 'tag', '')):
        previous = [r for r in rows(attempts) if r['id'] == identifier]
        inputs = {key: case[key] for key in ('id', 'template', 'text', 'structured', 'economics')}
        template = resolve(case['template']).read_bytes()
        if hashlib.sha256(template).hexdigest() != next(item['template_sha256'] for item in snapshot if item['id'] == case['id']):
            raise RuntimeError('Template dataset changed during the batch; retain its snapshot')
        fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode() + template).hexdigest()
        if previous:
            if any(r['id'] == identifier and r.get('input_sha256') != fingerprint for r in rows(attempts)):
                raise ValueError('Resume input changed; retain old attempts and use a new evaluation date')
            if identifier not in repairs:
                continue
            classified = attempt_score(previous[-1], case, ROOT)
            if len(previous) != 1 or not classified['environment_failure'] or not classified['billing_complete']:
                raise RuntimeError('Repair permits one additional attempt for a recorded environment failure only')
        if method == 'D' and not options.experience_ledger:
            raise RuntimeError('D requires the archived experience session; root manages the Skill experience section')
        for path in options.experience_ledger if method == 'D' else []:
            requests = [event for event in read_events(path) if event['type'] == 'request/sent']
            if not requests or any(event.get('origin') != 'system' or event.get('trust') != 'trusted'
                                   or event['data'].get('model', {}).get('id') != DESIGN_MODEL for event in requests):
                raise RuntimeError('D requires a native experience ledger whose requests all use deepseek-flash')
        for attempt in range(len(previous) + 1, 3):
            if getattr(options, 'pause_file', destination / 'PAUSE').exists():
                return
            if preflight(getattr(options, 'preflight', ROOT / 'reports/assets/T13-preflight.json')) != identity:
                raise RuntimeError('Preflight identity changed during the batch')
            paths = list((ROOT / 'runs').glob('eval-*/**/*.agnes.jsonl')) + options.experience_ledger
            baseline = guard(paths, method != 'A')
            name = identifier + (f'-a{attempt}' if attempt > 1 else '')
            folder = ROOT / 'runs' / identifier[:9] / (name + '-driver' if method in 'CDE' else name)
            folder.mkdir(parents=True, exist_ok=False)
            started = time.monotonic()
            outcome = dict(status='failed', session=None, pre_request_failure=False)
            try:
                if method == 'A':
                    final = backend(case, name, folder, {})
                    write_json(folder / 'run.json', dict(project_id=name, run_id=name, final_analysis=final, model_requests=0))
                    write_json(folder / 'timeline.json', dict(origin='external:eval-driver', events=rows(folder / 'execution.jsonl')))
                    write_json(folder / 'verification.json', dict(scope='baseline', passed=None, checks=[]))
                    outcome['status'] = 'completed'
                else:
                    outcome = execute(page, case, name, method, folder, baseline)
                    if method == 'B' and outcome['status'] == 'completed':
                        params = json.loads(outcome['result']['text'])
                        final = backend(case, name, folder, params)
                        write_json(folder / 'run.json', json.loads((folder / 'run.json').read_text(encoding='utf-8')) | dict(final_analysis=final))
                        write_json(folder / 'verification.json', dict(scope='single-answer-baseline', passed=None, checks=[]))
                    elif (outcome.get('result') or {}).get('archive_path'):
                        archived = (ROOT / outcome['result']['archive_path']).resolve()
                        if archived.parent != folder.parent.resolve() or archived.name != name or outcome['result'].get('session_id') != outcome['session']:
                            raise ValueError('Unexpected finish archive identity')
                        for path in folder.iterdir():
                            path.unlink()
                        folder.rmdir()
                        folder = archived
            except (Exception, KeyboardInterrupt) as error:
                outcome.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed', error=type(error).__name__)
            if not (folder / 'run.json').exists():
                write_json(folder / 'run.json', dict(run_id=name, project_id=name, session=outcome.get('session'), status=outcome['status']))
            if not (folder / 'timeline.json').exists():
                write_json(folder / 'timeline.json', dict(origin='external:eval-driver', events=rows(folder / 'execution.jsonl')))
            if not (folder / 'verification.json').exists():
                write_json(folder / 'verification.json', dict(scope='driver-failed', passed=None, status=outcome['status'], error=outcome.get('error')))
            record = {key: value for key, value in outcome.items() if key != 'result'} | dict(id=identifier, case=case['id'], method=method,
                   repeat=repeat, archive=folder.relative_to(ROOT).as_posix(), attempt=attempt, input_sha256=fingerprint,
                   elapsed_seconds=time.monotonic() - started, code_identity=identity)
            try:
                classified = attempt_score(record, case, ROOT)
            except Exception as error:
                record.update(environment_failure=True, evidence_error=True, environment_reason='classification:' + type(error).__name__)
                append(attempts, record)
                raise RuntimeError('Evidence classification failed; original attempt retained and no new model starts') from error
            record.update(environment_failure=classified['environment_failure'], evidence_error=not classified['billing_complete'])
            append(attempts, record)
            print(f'{identifier} attempt={attempt} status={outcome["status"]}', flush=True)
            if record['evidence_error']:
                raise RuntimeError('Evidence unavailable; stop before new model charges')
            if outcome.get('restore_error'):
                raise RuntimeError('Restore Flash failed; archived attempt retained and no new model started')
            if outcome['status'] == 'interrupted':
                raise KeyboardInterrupt
            if classified['environment_failure'] and (not outcome['pre_request_failure'] or outcome.get('configuration_error')):
                raise RuntimeError('Environment failure retained; fix and explicitly repair once before continuing')
            if not outcome['pre_request_failure'] or attempt == 2:
                break


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--stage', choices=['smoke', 'abc', 'repeat', 'e', 'd', 'all'], default='smoke')
    parser.add_argument('--experience-ledger', type=Path, action='append', default=[])
    parser.add_argument('--tag', default='')
    parser.add_argument('--preflight', type=Path, default=ROOT / 'reports/assets/T13-preflight.json')
    parser.add_argument('--pause-file', type=Path)
    parser.add_argument('--repair-id', action='append', default=[])
    parser.add_argument('--plan', action='store_true')
    options = parser.parse_args(argv)
    datetime.strptime(options.date, '%Y-%m-%d')
    if options.tag and not re.fullmatch('[a-z0-9]+', options.tag):
        parser.error('--tag must contain lowercase letters and digits only')
    options.pause_file = options.pause_file or ROOT / 'eval/results' / options.date / 'PAUSE'
    cases = json.loads((ROOT / 'eval/cases.json').read_text(encoding='utf-8'))
    if options.plan:
        print('\n'.join(key for key, _ in plan(cases, options.date, options.stage, options.tag)))
        return 0
    if options.pause_file.exists():
        return 0
    preflight(options.preflight)
    write_json(ROOT / 'eval/results' / options.date / 'preflight.json', json.loads(options.preflight.read_text(encoding='utf-8-sig')))
    from guangzhu.api import settings
    global AGH_HOME, OFFICIAL
    config = settings()
    AGH_HOME, OFFICIAL = config['agh_home'], Path(config['agh_runtime'])
    os.environ['AGH_HOME'] = AGH_HOME
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix='guangzhu-eval-') as profile, sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(profile, channel='msedge', headless=False, viewport=dict(width=1440, height=900))
        page = context.pages[0]
        page.add_init_script(OBSERVER)
        try:
            run(cases, options, page)
        finally:
            try:
                models = page.evaluate('window.__evalModels??[]')
                flash = next((m for m in models if m['id'] == DESIGN_MODEL), None)
                if flash:
                    model_select(page, flash)
            finally:
                context.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
