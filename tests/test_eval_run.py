"""Offline evaluation driver tests: fake product page, native receipts, and backend records."""

import ast
from collections import Counter
from datetime import timedelta
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import eval_run as driver
ORIGINAL_GUARD = driver.guard


MODELS = [dict(route='public', id='deepseek-flash', label='Flash'), dict(route='public', id='deepseek-v4-pro', label='Pro'),
          dict(route='public', id='agnes-3.0-flash', label='Agnes')]
IDENTITY = dict(commit='1' * 40, dirty=False, source_sha256='2' * 64, skill_rules_sha256='3' * 64,
                process_id=123, started_at='2026-10-03T00:00:02+00:00')
CASES = [dict(id=kind, template=kind, collection=kind, half=1 if index == 0 else 2, text='装机至少20kW',
              structured=dict(capacity_kw_min=20, budget_cny_max=100000, self_use_ratio=0.5, keep_clear_ids=['sky-1']),
              economics=dict(self_use_ratio=0.75), witness=dict(secret_answer='MUST_NOT_LEAK'), feasible=True)
         for index, kind in enumerate(('real', 'boundary', 'impossible'))]


def ledger(session='s1', requests=1, micros=10000, tool=None, model=None, reason='completed', verdict=None):
    data = [dict(type='session/start', data=dict(key=session))]
    data += [dict(type='request/sent', data=dict(model=model or {k: MODELS[0][k] for k in ('route', 'id')})) for _ in range(requests)]
    if tool:
        data += [dict(type='tool/call', data=dict(name=tool, toolUseId='t1', args={}))]
    if verdict:
        data += [dict(type='approval/decided', data=dict(requestId='r1', verdict=verdict))]
    data += [dict(type='cost/ledger', data=dict(purpose='inference', effectId=f'charge-{index}', billing=dict(source='estimated', usdMicros=micros)))
             for index in range(requests)]
    data += [dict(type='assistant/message', data=dict(content=[dict(type='text', text='{"tilt_deg":20}')])),
             dict(type='turn/end', data=dict(reason=reason))]
    return [row | dict(id=f'event-{index}', seq=index + 1, ts=f'2026-10-03T00:00:{index:02d}Z',
                      origin='model' if row['type'] == 'tool/call' else 'system', trust='trusted')
            for index, row in enumerate(data)]


def save_ledger(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(event) + '\n' for event in events), encoding='utf-8')


class FakeLocator:
    def __init__(self, page, selector):
        self.page, self.selector = page, selector

    def click(self, timeout=None):
        self.page.calls.append(('click', self.selector))
        if self.selector == '[data-action="start"]':
            self.page.queue += [dict(type='gz.session', session_id='s1')]
            if self.page.start_error:
                raise RuntimeError('Click timeout after the session actually started')
            if self.page.auto_finish:
                self.page.archive()
            self.page.queue += self.page.updates
        if self.selector == '[data-action="cancel"]':
            self.page.queue += [dict(type='gz.progress', session_id='s1', op='idle', nodes=[])]
        if self.selector == '[data-action="finish-retry"]':
            if self.page.finish_error:
                raise RuntimeError('API unavailable')
            self.page.archive()
        if self.selector in ('本会话允许', '拒绝'):
            self.page.card = False
            self.page.queue += [dict(type='gz.progress', session_id='s1', op='idle', nodes=[dict(kind='text', text='done')])]

    def fill(self, value):
        self.page.calls.append(('fill', self.selector, value))

    def select_option(self, value):
        self.page.calls.append(('select', self.selector, value))

    def set_checked(self, value):
        self.page.calls.append(('checked', self.selector, value))

    def is_visible(self):
        return self.page.card if self.selector == '#approval' else True

    def is_enabled(self, timeout=None):
        return True

    def get_by_role(self, role, name, exact):
        assert role == 'button' and exact
        return FakeLocator(self.page, name)

    def locator(self, selector):
        assert self.selector == '#approval' and selector == '[data-approval-key] > p'
        return FakeLocator(self.page, selector)

    @property
    def first(self):
        return self

    def count(self):
        return int(self.page.card_summary is not None)

    def inner_text(self):
        return self.page.card_summary


class FakePage:
    def __init__(self, root, identifier, auto_finish=False, events=None):
        self.root, self.identifier, self.auto_finish = root, identifier, auto_finish
        self.calls, self.queue, self.card = [], [], False
        self.card_summary = None
        self.events = events or ledger()
        self.updates = [dict(type='gz.progress', session_id='s1', op='idle', nodes=[dict(kind='text', text='done')])]
        self.now, self.start_error, self.finish_error = 0, False, False

    def goto(self, url):
        assert url == driver.URL
        self.queue = [dict(type='gz.ready', models=MODELS)]

    def wait_for_function(self, expression, timeout):
        assert 'gz.ready' in expression and timeout == 30000

    def evaluate(self, expression):
        if expression == 'window.__evalModels??[]':
            return MODELS
        assert expression == 'window.__evalMessages.splice(0)'
        values, self.queue = self.queue, []
        return values

    def locator(self, selector):
        return FakeLocator(self, selector)

    def frame_locator(self, selector):
        assert selector == '#agh'
        return self

    def wait_for_timeout(self, milliseconds):
        self.now += milliseconds / 1000

    def archive(self):
        folder = self.root / 'runs/eval-1003' / self.identifier
        folder.mkdir(parents=True, exist_ok=False)
        save_ledger(folder / 'ledger.agnes.jsonl', self.events)
        driver.write_json(folder / 'run.json', dict(session='s1', project_id=self.identifier, final_analysis=dict(version=1)))
        driver.write_json(folder / 'verification.json', dict(scope='evaluation', passed=True))
        return dict(session_id='s1', archive_path=folder.relative_to(self.root).as_posix())

    def expect_response(self, callback, timeout):
        assert callback(SimpleNamespace(url='http://127.0.0.1:8765/api/runs/finish'))
        value = dict(session_id='s1', archive_path=f'runs/eval-1003/{self.identifier}')
        return SimpleContext(SimpleNamespace(value=SimpleNamespace(json=lambda: value)))


class SimpleContext:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *args):
        return False


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, 'ROOT', tmp_path)
    monkeypatch.setattr(driver.time, 'monotonic', lambda: 0)
    monkeypatch.setattr(driver, 'guard', lambda paths, model=True: 0)
    monkeypatch.setattr(driver, 'preflight', lambda path: dict(IDENTITY))
    driver.write_json(tmp_path / 'reports/assets/T13-preflight.json', dict(identity=IDENTITY))
    template = tmp_path / 'project.json'
    driver.write_json(template, dict(site=dict(lat=30, lon=120), roof=dict(outline=[[0, 0], [10, 0], [10, 10]]),
                                   equipment=dict(module_id='public-module'), economics={}))
    monkeypatch.setattr(driver, 'resolve', lambda template_id: template)
    return tmp_path


def test_plan_order_uniqueness_and_smoke_reuse():
    all_cases = [dict(case, id=f'{case["id"]}-{index}', half=1 if index < 4 else 2) for case in CASES for index in range(8)]
    full = driver.plan(all_cases, '2026-10-03', 'all')
    smoke = driver.plan(all_cases, '2026-10-03', 'smoke')
    assert full[:9] == smoke and len(full) == len(dict(full)) == 228
    assert Counter(method for _, (_, method, _) in full) == dict(A=24, B=72, C=72, E=24, D=36)
    assert all(case['half'] == 2 for _, (case, method, _) in full if method == 'D')


def test_prompt_has_only_inputs_not_answers(isolated):
    text = driver.prompt(CASES[0], 'eval-1003-real-B-1')
    assert 'MUST_NOT_LEAK' not in text and 'witness' not in text and 'feasible' not in text and 'half' not in text
    assert '不要调用任何工具，也不要读 Skill' in text and 'modules_per_string' in text and 'layout_schema' in text


def test_fake_page_normal_ui_fill_and_manual_finish(isolated):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier)
    outcome = driver.execute(page, CASES[0], identifier, 'C', folder, 0)
    assert outcome['status'] == 'completed' and not outcome['pre_request_failure'] and not outcome['evidence_error']
    assert not (folder / 'run.json').exists(), 'API owns final metadata; driver cannot pre-create it'
    assert ('fill', '[data-field="budget"]', '10.0') in page.calls
    assert ('fill', '[data-field="selfUse"]', '75.0') in page.calls
    assert ('click', '[data-keep="sky-1"]') in page.calls
    assert ('select', '[data-field="maxRounds"]', '6') in page.calls
    assert all(('checked', f'[data-field="{field}"]', False) in page.calls for field in ('compare', 'review', 'exportOn'))


def test_automatic_finish_is_reused_without_click_or_native_overwrite(isolated, monkeypatch):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier, auto_finish=True)
    monkeypatch.setattr(driver, 'export_ledger', lambda *args: pytest.fail('Completed product archives must be reused'))
    outcome = driver.execute(page, CASES[0], identifier, 'C', folder, 0)
    assert outcome['status'] == 'completed' and not outcome['evidence_error']
    assert ('click', '[data-action="finish-retry"]') not in page.calls
    assert outcome['result']['archive_path'] == 'runs/eval-1003/' + identifier


@pytest.fixture
def disappearing_finish(monkeypatch):
    def install(page, phase, archive_state='complete'):
        state = dict(visible=False, removed=False, snapshot={})
        original = page.locator

        def remove_button():
            assert state['visible'] and not state['removed']
            state['removed'] = True
            if archive_state != 'missing':
                receipt = page.archive()
                archived = page.root / receipt['archive_path']
                if archive_state.startswith('missing-'):
                    filename = dict(ledger='ledger.agnes.jsonl', verification='verification.json', run='run.json')
                    (archived / filename[archive_state.removeprefix('missing-')]).unlink()
                elif archive_state == 'wrong-session':
                    metadata = json.loads((archived / 'run.json').read_text(encoding='utf-8'))
                    driver.write_json(archived / 'run.json', metadata | dict(session='different-session'))
                    save_ledger(archived / 'ledger.agnes.jsonl', ledger(session='different-session'))
                state['snapshot'] = {path.name: path.read_bytes() for path in archived.iterdir()}
            raise PlaywrightTimeoutError('Finish button detached after automatic archive navigation')

        class DisappearingLocator(FakeLocator):
            def is_visible(self):
                state['visible'] = not state['removed']
                return state['visible']

            def is_enabled(self, timeout=None):
                if phase == 'is_enabled':
                    remove_button()
                return super().is_enabled(timeout=timeout)

            def click(self, timeout=None):
                page.calls.append(('click', self.selector))
                remove_button()

        button = DisappearingLocator(page, '[data-action="finish-retry"]')
        monkeypatch.setattr(page, 'locator', lambda selector: button if selector == button.selector else original(selector))
        return state

    return install


@pytest.mark.parametrize('phase', ['is_enabled', 'click'])
def test_finish_button_disappears_after_same_session_archive_still_completes(isolated, monkeypatch, disappearing_finish, phase):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier)
    state = disappearing_finish(page, phase)
    fallback = []

    def export(*args):
        fallback.append(args)
        raise RuntimeError('Native fallback must not replace the complete product archive')

    monkeypatch.setattr(driver, 'export_ledger', export)
    outcome = driver.execute(page, CASES[0], identifier, 'C', folder, 0)
    assert state['removed']
    assert outcome['status'] == 'completed', outcome
    assert not outcome['evidence_error'] and not outcome['environment_failure'] and not outcome['pre_request_failure']
    assert outcome['result'] == dict(session_id='s1', archive_path='runs/eval-1003/' + identifier)
    assert not fallback and not (folder / 'run.json').exists()
    archived = folder.parent / identifier
    assert {path.name: path.read_bytes() for path in archived.iterdir()} == state['snapshot']


@pytest.mark.parametrize('phase', ['is_enabled', 'click'])
@pytest.mark.parametrize('archive_state', ['missing', 'missing-ledger', 'missing-verification', 'missing-run', 'wrong-session'])
def test_finish_button_disappearance_cannot_accept_missing_or_foreign_archive(isolated, disappearing_finish, phase, archive_state):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier)
    state = disappearing_finish(page, phase, archive_state)
    with pytest.raises((PlaywrightTimeoutError, RuntimeError, ValueError, FileNotFoundError)):
        driver.finish(page, folder, identifier, 's1', idle=True)
    assert state['removed']
    archived = folder.parent / identifier
    if archived.exists():
        assert {path.name: path.read_bytes() for path in archived.iterdir()} == state['snapshot']


@pytest.mark.parametrize('tool,method,label,violation', [('mcp_foo_gz_set_requirements', 'C', '本会话允许', False),
    ('skill_read', 'C', '本会话允许', False), ('mcp_foo_gz_export', 'C', '拒绝', True), ('read', 'C', '拒绝', True),
    ('mcp_foo_gz_set_requirements', 'B', '拒绝', True)])
def test_only_allowed_session_design_approvals(isolated, tool, method, label, violation):
    page = FakePage(isolated, 'eval-1003-real-C-1')
    page.card = True
    assert driver.approval(page, dict(tool=tool, pending=True, session_id='s1'), method, 's1') is violation
    assert ('click', label) in page.calls
    assert ('click', '对此配置始终允许') not in page.calls
    record = driver.rows(isolated / 'reports/assets/T13-agh-commands.log')[-1]
    assert record['decision'] == ('rejected' if violation else 'allowed-session')


def test_native_card_visible_before_pending_bridge_message_waits_without_rejection(isolated):
    page = FakePage(isolated, 'eval-1003-real-C-1')
    page.card = True
    assert driver.approval(page, {}, 'C', 's1') is False
    assert page.card and ('click', '拒绝') not in page.calls and ('click', '本会话允许') not in page.calls
    assert not (isolated / 'reports/assets/T13-agh-commands.log').exists()
    pending = dict(type='gz.approval', session_id='s1', tool='mcp_guangzhu_gz_new_project', pending=True)
    assert driver.approval(page, pending, 'C', 's1') is False
    assert ('click', '本会话允许') in page.calls and ('click', '拒绝') not in page.calls
    assert driver.rows(isolated / 'reports/assets/T13-agh-commands.log')[-1]['tool'] == 'mcp_guangzhu_gz_new_project'
    assert pending == {}


@pytest.mark.parametrize('identity', ['native', 'pending'])
def test_next_unknown_card_cannot_reuse_allowed_design_pending(isolated, identity):
    page = FakePage(isolated, 'eval-1003-real-C-1')
    page.card = True
    pending = dict(type='gz.approval', session_id='s1', tool='mcp_guangzhu_gz_new_project', pending=True)
    assert driver.approval(page, pending, 'C', 's1') is False
    assert pending == {} and ('click', '本会话允许') in page.calls
    page.calls.clear()
    page.card, page.card_summary = True, '需要确认这个操作'
    assert driver.approval(page, pending, 'C', 's1') is False
    assert page.calls == [] and page.card
    if identity == 'native':
        page.card_summary = 'mcp_guangzhu_gz_export {"project_id":"p"}'
    else:
        pending.update(type='gz.approval', session_id='s1', tool='mcp_guangzhu_gz_export', pending=True)
    assert driver.approval(page, pending, 'C', 's1') is True
    assert ('click', '拒绝') in page.calls and ('click', '本会话允许') not in page.calls
    assert pending == {}


def test_pending_from_different_session_cannot_approve_unknown_card(isolated):
    page = FakePage(isolated, 'eval-1003-real-C-1')
    page.card = True
    pending = dict(session_id='old-session', tool='mcp_guangzhu_gz_new_project', pending=True)
    assert driver.approval(page, pending, 'C', 's1') is False
    assert page.calls == [] and page.card


@pytest.mark.parametrize('summary,label,violation', [('mcp_guangzhu_gz_new_project {"project_id":"p"}', '本会话允许', False),
    ('skill_read', '本会话允许', False), ('read {"path":"eval/cases.json"}', '拒绝', True),
    ('mcp_guangzhu_gz_export {"project_id":"p"}', '拒绝', True)])
def test_native_card_identifies_tool_when_bridge_pending_has_not_arrived(isolated, summary, label, violation):
    page = FakePage(isolated, 'eval-1003-real-C-1')
    page.card, page.card_summary = True, summary
    assert driver.approval(page, {}, 'C', 's1') is violation
    assert ('click', label) in page.calls


def test_execute_card_first_pending_later_completes_without_false_violation(isolated, monkeypatch):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier)
    page.card = True
    page.updates = [dict(type='gz.progress', session_id='s1', op='running', nodes=[])]
    original = page.wait_for_timeout
    delivered = []
    def wait(milliseconds):
        original(milliseconds)
        if not delivered:
            assert page.card and ('click', '拒绝') not in page.calls and ('click', '本会话允许') not in page.calls
            delivered.append(True)
            page.queue += [dict(type='gz.approval', session_id='s1', tool='mcp_guangzhu_gz_new_project', pending=True)]
    monkeypatch.setattr(page, 'wait_for_timeout', wait)
    outcome = driver.execute(page, CASES[0], identifier, 'C', folder, 0)
    assert outcome['status'] == 'completed' and not outcome['evidence_error']
    assert delivered and ('click', '本会话允许') in page.calls and ('click', '拒绝') not in page.calls


def test_timeout_stops_then_waits_idle_and_finishes(isolated, monkeypatch):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier)
    page.updates = [dict(type='gz.progress', session_id='s1', op='running', nodes=[])]
    monkeypatch.setattr(driver.time, 'monotonic', lambda: page.now)
    outcome = driver.execute(page, CASES[0], identifier, 'C', folder, 0, timeout=2)
    assert outcome['status'] == 'timeout' and not outcome['pre_request_failure']
    assert page.calls.index(('click', '[data-action="cancel"]')) < page.calls.index(('click', '[data-action="finish-retry"]'))
    assert page.now >= 4 and (isolated / outcome['result']['archive_path'] / 'ledger.agnes.jsonl').exists()


def test_live_billing_uses_max_not_repeated_updates(isolated, monkeypatch):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier)
    page.updates = [dict(type='gz.progress', session_id='s1', op='idle', nodes=[dict(kind='text', text='done')],
                         usage=dict(costs=[dict(currency='USD', micros=100000)]))] * 3
    outcome = driver.execute(page, CASES[0], identifier, 'C', folder, 5_500_000)
    assert outcome['status'] == 'completed'
    page = FakePage(isolated, identifier + '-a2')
    page.updates = [dict(type='gz.progress', session_id='s1', op='running', nodes=[], usage=dict(costs=[dict(currency='USD', micros=400000)]))]
    outcome = driver.execute(page, CASES[0], identifier + '-a2', 'C', folder, 5_500_000)
    assert outcome['status'] == 'budget' and ('click', '[data-action="cancel"]') in page.calls


def test_click_timeout_after_model_start_is_not_retried(isolated):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier, auto_finish=True)
    page.start_error = True
    page.archive()
    outcome = driver.execute(page, CASES[0], identifier, 'C', folder, 0)
    assert outcome['status'] == 'failed' and not outcome['pre_request_failure']
    assert outcome['session'] == 's1'


def test_click_timeout_without_session_is_unknown_evidence_and_not_retryable(isolated, monkeypatch):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier)
    original = FakeLocator.click
    def click(locator):
        if locator.selector == '[data-action="start"]':
            raise RuntimeError('Clicked but no session acknowledgement; request state unknown')
        original(locator)
    monkeypatch.setattr(FakeLocator, 'click', click)
    outcome = driver.execute(page, CASES[0], identifier, 'C', folder, 0)
    assert outcome['status'] == 'failed' and outcome['session'] is None
    assert outcome['evidence_error'] and not outcome['pre_request_failure']


def test_failed_normal_finish_preserves_complete_native_model_failure_evidence(isolated, monkeypatch):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier)
    page.finish_error = True
    def export(session, path, executable):
        save_ledger(path, page.events)
        return page.events
    monkeypatch.setattr(driver, 'export_ledger', export)
    outcome = driver.execute(page, CASES[0], identifier, 'C', folder, 0)
    assert not outcome['evidence_error'] and outcome['status'] == 'failed'
    assert not outcome['environment_failure']
    assert (folder / 'ledger.agnes.jsonl').exists()
    assert json.loads((folder / 'verification.json').read_text(encoding='utf-8'))['scope'] == 'driver-fallback'
    assert not (folder.parent / identifier).exists()


def test_zero_request_native_fallback_is_retryable_without_unknown_charges(isolated, monkeypatch):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier)
    page.start_error = True
    page.finish_error = True
    def export(session, path, executable):
        events = ledger(requests=0)
        save_ledger(path, events)
        return events
    monkeypatch.setattr(driver, 'export_ledger', export)
    outcome = driver.execute(page, CASES[0], identifier, 'C', folder, 0)
    assert outcome['status'] == 'failed' and outcome['pre_request_failure'] and not outcome['evidence_error']
    assert driver.costs([folder / 'ledger.agnes.jsonl']) == (0, False)
    assert json.loads((folder / 'verification.json').read_text(encoding='utf-8'))['scope'] == 'driver-fallback'


def test_e_restore_failure_keeps_completed_session_and_archive(isolated, monkeypatch):
    identifier = 'eval-1003-real-E-1'
    page = FakePage(isolated, identifier, auto_finish=True, events=ledger(model=dict(route='public', id='agnes-3.0-flash')))
    original = driver.model_select
    def model_select(page, model):
        if model['id'] == 'deepseek-flash':
            raise RuntimeError('Restore settings unavailable')
        original(page, model)
    monkeypatch.setattr(driver, 'model_select', model_select)
    monkeypatch.setattr(driver, 'plan', lambda *args: [(identifier, (CASES[0], 'E', 1))])
    options = SimpleNamespace(date='2026-10-03', stage='e', experience_ledger=[])
    with pytest.raises(RuntimeError, match='Restore Flash failed'):
        driver.run(CASES, options, page)
    recorded = driver.rows(isolated / 'eval/results/2026-10-03/attempts.jsonl')
    assert len(recorded) == 1 and recorded[0]['status'] == 'completed' and recorded[0]['restore_error']
    assert recorded[0]['session'] == 's1' and recorded[0]['archive'] == f'runs/eval-1003/{identifier}'
    assert (isolated / recorded[0]['archive'] / 'ledger.agnes.jsonl').exists()


def test_title_cost_cannot_replace_missing_inference_billing(tmp_path):
    path = tmp_path / 'ledger.jsonl'
    events = ledger()
    next(row for row in events if row['type'] == 'cost/ledger')['data']['purpose'] = 'title'
    save_ledger(path, events)
    assert driver.costs([path]) == (10000, True)
    with pytest.raises(RuntimeError):
        driver.guard([path], now=driver.CUTOFF - timedelta(seconds=1))


def test_main_uses_product_runtime_and_home_not_inherited_shell(isolated, monkeypatch):
    from guangzhu import api
    import playwright.sync_api
    home, executable = str(isolated / 'independent-home'), str(isolated / 'official.exe')
    monkeypatch.setenv('AGH_HOME', 'wrong-inherited-instance')
    monkeypatch.setattr(api, 'settings', lambda: dict(agh_home=home, agh_runtime=executable))
    page = FakePage(isolated, 'eval-1003-real-C-1')
    context = SimpleNamespace(pages=[page], close=lambda: None)
    calls = []
    def launch(profile, **options):
        assert profile != home and options['channel'] == 'msedge' and options['headless'] is False
        calls.append(profile)
        return context
    monkeypatch.setattr(page, 'add_init_script', lambda observer: None, raising=False)
    monkeypatch.setattr(driver, 'AGH_HOME', driver.AGH_HOME)
    monkeypatch.setattr(driver, 'OFFICIAL', driver.OFFICIAL)
    monkeypatch.setattr(playwright.sync_api, 'sync_playwright', lambda: SimpleContext(SimpleNamespace(
        chromium=SimpleNamespace(launch_persistent_context=launch))))
    def run(cases, options, page):
        assert driver.os.environ['AGH_HOME'] == home and driver.AGH_HOME == home and driver.OFFICIAL == Path(executable)
    monkeypatch.setattr(driver, 'run', run)
    driver.write_json(isolated / 'eval/cases.json', CASES)
    assert driver.main(['--date', '2026-10-03']) == 0 and len(calls) == 1


@pytest.mark.parametrize('events,status', [(ledger(tool='read'), 'violation'), (ledger(tool='mcp_x_gz_export'), 'violation'),
    (ledger(verdict='allowed-permanent'), 'failed'), (ledger(model=dict(route='public', id='wrong-model')), 'failed')])
def test_native_record_checks_catch_hidden_projection_violations(isolated, events, status):
    identifier = 'eval-1003-real-C-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier, auto_finish=True, events=events)
    outcome = driver.execute(page, CASES[0], identifier, 'C', folder, 0)
    assert outcome['status'] == status
    assert outcome['environment_failure'] is (status == 'failed')


def test_native_model_error_is_not_retryable_and_e_restores_flash(isolated):
    identifier = 'eval-1003-real-E-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    events = ledger(reason='error', model=dict(route='public', id='agnes-3.0-flash'))
    page = FakePage(isolated, identifier, auto_finish=True, events=events)
    outcome = driver.execute(page, CASES[0], identifier, 'E', folder, 0)
    assert outcome['status'] == 'failed' and not outcome['pre_request_failure']
    selected = [call for call in page.calls if call[0] == 'select' and call[1] == '#design-model']
    assert selected[0][2] == 'public/agnes-3.0-flash' and selected[-1][2] == 'public/deepseek-flash'


def test_b_resumes_verified_blank_session_one_prompt_and_keeps_cli_receipt(isolated, monkeypatch):
    instance = str(isolated / 'configured-test-instance')
    monkeypatch.setattr(driver, 'AGH_HOME', instance)
    identifier = 'eval-1003-real-B-1'
    folder = isolated / 'runs/eval-1003' / identifier
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier)
    exports, commands = [], []
    def export(session, path, executable):
        events = ledger(requests=0) if not exports else ledger()
        exports.append(session)
        save_ledger(path, events)
        return events
    class Process:
        def __init__(self, command, stdin, stdout, stderr, cwd, env):
            commands.append(command)
            assert env['AGH_HOME'] == instance and cwd == isolated
            self.stdin = io.BytesIO()
            stdout.write(json.dumps(dict(v='agnes-cli-result/v1', sessionId='s1', reason='completed', exitCode=0,
                                         lastSeq=5, text='{"tilt_deg":20}')).encode())
        def poll(self):
            return 0
        def wait(self, timeout):
            return 0
    monkeypatch.setattr(driver, 'export_ledger', export)
    monkeypatch.setattr(driver.subprocess, 'Popen', Process)
    outcome = driver.execute(page, CASES[0], identifier, 'B', folder, 0)
    assert outcome['status'] == 'completed' and exports == ['s1', 's1']
    assert ('click', '[data-mode="chat"]') in page.calls
    assert '--resume' in commands[0] and '--park' not in commands[0] and 'primary=public/deepseek-flash' in commands[0]
    assert json.loads((folder / 'cli-result.json').read_text(encoding='utf-8'))['sessionId'] == 's1'


def test_retry_once_only_before_request_and_resume_identical_inputs(isolated, monkeypatch):
    monkeypatch.setattr(driver, 'plan', lambda *args: [('eval-1003-real-C-1', (CASES[0], 'C', 1))])
    calls = []
    def attempt(page, case, identifier, method, folder, baseline):
        calls.append(identifier)
        if len(calls) > 1:
            save_ledger(folder / 'ledger.agnes.jsonl', ledger(session=identifier, reason='error'))
        return dict(status='failed', session=None if len(calls) == 1 else identifier, pre_request_failure=len(calls) == 1)
    monkeypatch.setattr(driver, 'execute', attempt)
    options = SimpleNamespace(date='2026-10-03', stage='smoke', experience_ledger=[])
    driver.run(CASES, options, object())
    records = driver.rows(isolated / 'eval/results/2026-10-03/attempts.jsonl')
    assert len(records) == 2 and [row['attempt'] for row in records] == [1, 2]
    assert records[0]['archive'].endswith('-driver') and records[1]['archive'].endswith('-a2-driver')
    driver.run(CASES, options, object())
    assert len(calls) == 2
    altered = dict(CASES[0], text='different input')
    monkeypatch.setattr(driver, 'plan', lambda *args: [('eval-1003-real-C-1', (altered, 'C', 1))])
    with pytest.raises(ValueError, match='Resume input changed'):
        driver.run(CASES, options, object())


@pytest.mark.parametrize('method', ['A', 'B'])
def test_failed_backend_archives_keep_real_execution_timeline_and_unknown_verification(isolated, monkeypatch, method):
    identifier = f'eval-1003-real-{method}-1'
    monkeypatch.setattr(driver, 'plan', lambda *args: [(identifier, (CASES[0], method, 1))])
    def backend(case, project, folder, params):
        driver.append(folder / 'execution.jsonl', dict(origin='external:eval-driver', type='backend/result',
            data=dict(callId='actual-failure', isError=True, value=dict(ok=False, error_code='RESULT_TOO_LARGE'))))
        raise RuntimeError('Backend summary overflow')
    monkeypatch.setattr(driver, 'backend', backend)
    if method == 'B':
        def execute(page, case, project, method, folder, baseline):
            save_ledger(folder / 'ledger.agnes.jsonl', ledger(session='actual-b-session'))
            return dict(status='completed', session='actual-b-session', pre_request_failure=False, result=dict(text='{}'))
        monkeypatch.setattr(driver, 'execute', execute)
    options = SimpleNamespace(date='2026-10-03', stage='smoke', experience_ledger=[])
    driver.run(CASES, options, object())
    attempt = driver.rows(isolated / 'eval/results/2026-10-03/attempts.jsonl')[0]
    folder = isolated / attempt['archive']
    assert attempt['status'] == 'failed' and not attempt['pre_request_failure']
    timeline = json.loads((folder / 'timeline.json').read_text(encoding='utf-8'))
    assert timeline['origin'] == 'external:eval-driver' and timeline['events'] == driver.rows(folder / 'execution.jsonl')
    assert timeline['events'][0]['data']['value']['error_code'] == 'RESULT_TOO_LARGE'
    verification = json.loads((folder / 'verification.json').read_text(encoding='utf-8'))
    assert verification == dict(scope='driver-failed', passed=None, status='failed', error='RuntimeError')
    assert (folder / 'run.json').exists()


def test_failed_archive_supplement_never_overwrites_existing_native_artifacts(isolated, monkeypatch):
    identifier = 'eval-1003-real-B-1'
    monkeypatch.setattr(driver, 'plan', lambda *args: [(identifier, (CASES[0], 'B', 1))])
    expected = {}
    def execute(page, case, project, method, folder, baseline):
        for name, value in dict(timeline=dict(nodes=['native-original']), verification=dict(scope='native-original', passed=False)).items():
            path = folder / (name + '.json')
            driver.write_json(path, value)
            expected[path] = path.read_bytes()
        save_ledger(folder / 'ledger.agnes.jsonl', ledger(session='original-session', reason='error'))
        return dict(status='failed', session='original-session', pre_request_failure=False, error='OriginalError')
    monkeypatch.setattr(driver, 'execute', execute)
    options = SimpleNamespace(date='2026-10-03', stage='smoke', experience_ledger=[])
    driver.run(CASES, options, object())
    assert all(path.read_bytes() == original for path, original in expected.items())
    assert driver.rows(isolated / 'eval/results/2026-10-03/attempts.jsonl')[0]['status'] == 'failed'


def test_known_failure_before_start_is_retryable(isolated, monkeypatch):
    page = FakePage(isolated, 'eval-1003-real-C-1')
    monkeypatch.setattr(page, 'wait_for_function', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('No bridge')))
    outcome = driver.execute(page, CASES[0], page.identifier, 'C', isolated, 0)
    assert outcome['pre_request_failure'] and outcome['session'] is None
    assert ('click', '[data-action="start"]') not in page.calls


def test_a_backend_call_records_actual_args_results_and_final_artifacts(isolated, monkeypatch):
    folder = isolated / 'runs/eval-1003/eval-1003-real-A-1'
    folder.mkdir(parents=True)
    dispatched = []
    def dispatch(name, args):
        dispatched.append((name, args))
        if name == 'gz_analyze':
            for file in ('summary', 'rules'):
                driver.write_json(isolated / f'{file}.json', dict(version=1, actual=True))
            return dict(version=1, rules=dict(hard_failed=0), actual=True)
        return dict(ok=True, version=1, contradictions=[])
    monkeypatch.setattr(driver.mcp_actions, 'dispatch', dispatch)
    monkeypatch.setattr(driver.storage, '_path', lambda project, relative: isolated / Path(relative).name)
    result = driver.backend(CASES[0], folder.name, folder, {})
    assert [name for name, _ in dispatched] == ['gz_new_project', 'gz_set_requirements', 'gz_generate_layout', 'gz_analyze']
    assert dispatched[-1][1]['offline'] is True and dispatched[-2][1]['params'] == {}
    assert result == dict(version=1, summary='summary.json', rules='rules.json')
    records = driver.rows(folder / 'execution.jsonl')
    assert all(row['origin'] == 'external:eval-driver' and 'seq' not in row and 'trust' not in row for row in records)
    assert len(records) == 9 and records[-1]['type'] == 'driver/final'
    assert 'MUST_NOT_LEAK' not in (folder / 'execution.jsonl').read_text(encoding='utf-8')


def test_budget_deduplicates_across_archives_and_counts_failed_and_experience(tmp_path):
    first, duplicate, experience = [tmp_path / name for name in ('failed.jsonl', 'duplicate.jsonl', 'experience.jsonl')]
    save_ledger(first, ledger(micros=300000))
    save_ledger(duplicate, ledger(micros=300000))
    extra = ledger(session='experience', micros=700000)
    next(row for row in extra if row['type'] == 'cost/ledger')['data']['effectId'] = 'experience-charge'
    save_ledger(experience, extra)
    assert driver.costs([first, duplicate, experience]) == (1000000, False)
    with pytest.raises(RuntimeError, match='billing guard'):
        driver.guard([first], now=driver.CUTOFF)
    assert driver.guard([first], now=driver.CUTOFF - timedelta(seconds=1)) == 300000


@pytest.mark.parametrize('bill', [dict(source='unknown', usdMicros=999), dict(source='estimated', usdMicros=None),
                                 dict(source='estimated', usdMicros=-10), dict(source='estimated', usdMicros=True)])
def test_unknown_billing_is_not_zero_or_counted_as_valid_cost(tmp_path, bill):
    path = tmp_path / 'ledger.jsonl'
    events = ledger()
    next(row for row in events if row['type'] == 'cost/ledger')['data']['billing'] = bill
    save_ledger(path, events)
    assert driver.costs([path]) == (0, True)
    with pytest.raises(RuntimeError, match='unknown charges'):
        driver.guard([path], now=driver.CUTOFF - timedelta(seconds=1))


def test_zero_estimate_and_reserve_and_conflicting_effects(tmp_path):
    path, conflict = tmp_path / 'a.jsonl', tmp_path / 'b.jsonl'
    save_ledger(path, ledger(micros=0))
    assert driver.costs([path]) == (0, False)
    save_ledger(path, ledger(micros=5500001))
    with pytest.raises(RuntimeError):
        driver.guard([path], now=driver.CUTOFF - timedelta(seconds=1))
    save_ledger(conflict, ledger(micros=1))
    with pytest.raises(ValueError, match='Conflicting'):
        driver.costs([path, conflict])


def test_native_billing_provenance_and_missing_completed_request(tmp_path):
    path = tmp_path / 'a.jsonl'
    events = ledger()
    next(row for row in events if row['type'] == 'cost/ledger')['origin'] = 'tool:read'
    save_ledger(path, events)
    with pytest.raises(ValueError, match='Untrusted'):
        driver.costs([path])
    save_ledger(path, [row for row in ledger() if row['type'] != 'cost/ledger'])
    assert driver.costs([path]) == (0, True)


def test_new_runner_has_one_statement_per_line_and_max_160_chars():
    path = Path(driver.__file__)
    source = path.read_text(encoding='utf-8')
    assert max(map(len, source.splitlines())) <= 160
    counts = Counter(node.lineno for node in ast.walk(ast.parse(source)) if isinstance(node, ast.stmt))
    assert max(counts.values()) == 1
    assert 'launch_persistent_context(profile, channel=\'msedge\'' in source
    assert 'download_browser' not in source and '--park' not in source


@pytest.fixture
def selfcheck(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, 'ROOT', tmp_path)
    monkeypatch.setattr(driver, 'current_identity', lambda: dict(IDENTITY))
    command_line = 'python -m guangzhu.mcp_server'
    receipt = dict(identity=dict(IDENTITY), probe=dict(ok=True, created=True, code_identity=dict(IDENTITY)), template='real',
                   previous_process_id=122, reconnected_at='2026-10-03T00:00:01+00:00',
                   process=dict(pid=123, command_line=command_line))
    monkeypatch.setattr(driver.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=command_line))
    driver.write_json(tmp_path / 'eval/cases.json', CASES)
    return tmp_path / 'preflight.json', receipt


def test_preflight_accepts_current_frozen_code_in_a_fresh_registered_process(selfcheck):
    path, receipt = selfcheck
    receipt['probe']['code_identity']['process_id'] = 124
    driver.write_json(path, receipt)
    assert driver.preflight(path) == IDENTITY


@pytest.mark.parametrize('change', ['dirty', 'commit', 'hash', 'rules', 'old-pid', 'old-start', 'bad-probe', 'demo-template'])
def test_preflight_rejects_stale_or_unverified_code_before_browser_launch(selfcheck, change):
    path, receipt = selfcheck
    if change in ('dirty', 'commit', 'hash', 'rules'):
        key = dict(dirty='dirty', commit='commit', hash='source_sha256', rules='skill_rules_sha256')[change]
        receipt['identity'][key] = True if change == 'dirty' else 'changed'
    elif change == 'old-pid':
        receipt['previous_process_id'] = 123
    elif change == 'old-start':
        receipt['identity']['started_at'] = '2026-10-03T00:00:00+00:00'
    elif change == 'bad-probe':
        receipt['probe']['created'] = False
    else:
        receipt['template'] = 'demo'
    driver.write_json(path, receipt)
    with pytest.raises(RuntimeError, match='Preflight'):
        driver.preflight(path)


def test_preflight_rejects_a_reused_pid_or_changed_command(selfcheck, monkeypatch):
    path, receipt = selfcheck
    driver.write_json(path, receipt)
    monkeypatch.setattr(driver.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(stdout='other process'))
    with pytest.raises(RuntimeError, match='changed or exited'):
        driver.preflight(path)


def test_tag_preserves_archive_date_prefix_and_changes_every_plan_id():
    before = driver.plan(CASES, '2026-10-03', 'smoke')
    tagged = driver.plan(CASES, '2026-10-03', 'smoke', 'r1')
    assert len(tagged) == len(before) == 9
    assert all(identifier.startswith('eval-1003-r1-') and identifier[:9] == 'eval-1003' for identifier, _ in tagged)
    assert not set(dict(before)) & set(dict(tagged))


def test_pause_file_stops_at_run_boundary_after_preserving_current_attempt(isolated, monkeypatch):
    planned = [('eval-1003-real-A-1', (CASES[0], 'A', 1)), ('eval-1003-boundary-A-1', (CASES[1], 'A', 1))]
    monkeypatch.setattr(driver, 'plan', lambda *args: planned)
    pause = isolated / 'eval/results/2026-10-03/PAUSE'
    calls = []
    def backend(case, identifier, folder, params):
        calls.append(identifier)
        pause.parent.mkdir(parents=True, exist_ok=True)
        pause.write_text('user requested pause', encoding='utf-8')
        return dict(version=1)
    monkeypatch.setattr(driver, 'backend', backend)
    options = SimpleNamespace(date='2026-10-03', stage='abc', experience_ledger=[])
    driver.run(CASES, options)
    assert calls == [planned[0][0]]
    attempts = driver.rows(pause.parent / 'attempts.jsonl')
    assert len(attempts) == 1 and attempts[0]['status'] == 'completed' and attempts[0]['code_identity'] == IDENTITY
    driver.run(CASES, options)
    assert calls == [planned[0][0]]


def test_one_paid_environment_repair_preserves_both_attempts_and_never_runs_a_third(isolated, monkeypatch):
    identifier = 'eval-1003-real-C-1'
    monkeypatch.setattr(driver, 'plan', lambda *args: [(identifier, (CASES[0], 'C', 1))])
    calls = []
    def execute(page, case, name, method, folder, baseline):
        calls.append(name)
        save_ledger(folder / 'ledger.agnes.jsonl', ledger(session=name))
        return dict(status='failed' if len(calls) == 1 else 'completed', session=name, pre_request_failure=False,
                    environment_failure=len(calls) == 1, environment_reason='driver-approval', result=None)
    monkeypatch.setattr(driver, 'execute', execute)
    options = SimpleNamespace(date='2026-10-03', stage='abc', experience_ledger=[], repair_id=[])
    with pytest.raises(RuntimeError, match='Environment failure retained'):
        driver.run(CASES, options, object())
    path = isolated / 'eval/results/2026-10-03/attempts.jsonl'
    original = path.read_bytes()
    options.repair_id = [identifier]
    driver.run(CASES, options, object())
    assert path.read_bytes().startswith(original)
    assert [row['attempt'] for row in driver.rows(path)] == [1, 2]
    with pytest.raises(RuntimeError, match='one additional attempt'):
        driver.run(CASES, options, object())
    assert calls == [identifier, identifier + '-a2']


def test_model_failure_cannot_be_selected_for_environment_repair(isolated, monkeypatch):
    identifier = 'eval-1003-real-C-1'
    monkeypatch.setattr(driver, 'plan', lambda *args: [(identifier, (CASES[0], 'C', 1))])
    def execute(page, case, name, method, folder, baseline):
        save_ledger(folder / 'ledger.agnes.jsonl', ledger(session='paid', reason='error'))
        return dict(status='failed', session='paid', pre_request_failure=False)
    monkeypatch.setattr(driver, 'execute', execute)
    options = SimpleNamespace(date='2026-10-03', stage='abc', experience_ledger=[], repair_id=[])
    driver.run(CASES, options, object())
    options.repair_id = [identifier]
    with pytest.raises(RuntimeError, match='environment failure only'):
        driver.run(CASES, options, object())


def test_resume_rejects_mixed_commits_without_mutating_original_attempts(isolated, monkeypatch):
    identifier = 'eval-1003-real-A-1'
    monkeypatch.setattr(driver, 'plan', lambda *args: [(identifier, (CASES[0], 'A', 1))])
    monkeypatch.setattr(driver, 'backend', lambda *args: dict(version=1))
    options = SimpleNamespace(date='2026-10-03', stage='abc', experience_ledger=[])
    driver.run(CASES, options)
    path = isolated / 'eval/results/2026-10-03/attempts.jsonl'
    original = path.read_bytes()
    monkeypatch.setattr(driver, 'preflight', lambda path: dict(IDENTITY, commit='9' * 40))
    with pytest.raises(RuntimeError, match='Mixed code versions'):
        driver.run(CASES, options)
    assert path.read_bytes() == original


@pytest.mark.parametrize('empty', [False, True])
def test_missing_or_empty_explicit_ledger_is_unknown_and_cannot_fund_d(tmp_path, empty):
    path = tmp_path / 'experience.ledger.agnes.jsonl'
    if empty:
        path.write_text('', encoding='utf-8')
    assert driver.costs([path]) == (0, True)
    with pytest.raises(RuntimeError, match='billing guard'):
        driver.guard([path], now=driver.CUTOFF - timedelta(seconds=1))


def test_registered_missing_child_ledger_is_unknown_cost(tmp_path):
    path = tmp_path / 'ledger.agnes.jsonl'
    save_ledger(path, ledger())
    driver.write_json(tmp_path / 'run.json', dict(children=[dict(ledger='children/missing.ledger.agnes.jsonl')]))
    assert driver.costs([path]) == (10000, True)


def test_guard_counts_child_billing_and_stops_if_a_paid_attempt_lost_its_ledger(isolated):
    parent = isolated / 'runs/eval-1003/parent/ledger.agnes.jsonl'
    child = parent.parent / 'children/child.ledger.agnes.jsonl'
    save_ledger(parent, ledger())
    events = ledger(session='child')
    next(event for event in events if event['type'] == 'cost/ledger')['data']['effectId'] = 'different-child-charge'
    save_ledger(child, events)
    driver.write_json(parent.parent / 'run.json', dict(children=[dict(ledger='children/child.ledger.agnes.jsonl')]))
    assert driver.costs(list((isolated / 'runs').glob('eval-*/**/*.agnes.jsonl'))) == (20000, False)
    driver.append(isolated / 'eval/results/2026-10-03/attempts.jsonl', dict(method='C', session='lost-paid',
        archive='runs/eval-1003/lost-paid', evidence_error=True))
    with pytest.raises(RuntimeError, match='billing guard'):
        ORIGINAL_GUARD([parent, child], now=driver.CUTOFF - timedelta(seconds=1))


def test_repair_gate_uses_native_model_violation_instead_of_cached_environment_flag(isolated, monkeypatch):
    identifier = 'eval-1003-real-C-1'
    monkeypatch.setattr(driver, 'plan', lambda *args: [(identifier, (CASES[0], 'C', 1))])
    def execute(page, case, name, method, folder, baseline):
        save_ledger(folder / 'ledger.agnes.jsonl', ledger(session=name, tool='file_read'))
        return dict(status='failed', session=name, pre_request_failure=False, environment_failure=True, environment_reason='archive')
    monkeypatch.setattr(driver, 'execute', execute)
    options = SimpleNamespace(date='2026-10-03', stage='abc', experience_ledger=[], repair_id=[])
    driver.run(CASES, options, object())
    path = isolated / 'eval/results/2026-10-03/attempts.jsonl'
    assert not driver.rows(path)[0]['environment_failure']
    options.repair_id = [identifier]
    with pytest.raises(RuntimeError, match='environment failure only'):
        driver.run(CASES, options, object())
    assert len(driver.rows(path)) == 1


def test_missing_paid_native_evidence_is_recorded_and_never_eligible_for_repair(isolated, monkeypatch):
    identifier = 'eval-1003-real-C-1'
    monkeypatch.setattr(driver, 'plan', lambda *args: [(identifier, (CASES[0], 'C', 1))])
    monkeypatch.setattr(driver, 'execute', lambda *args: dict(status='failed', session='lost-paid', pre_request_failure=False,
        environment_failure=True, environment_reason='ui-run', evidence_error=True))
    options = SimpleNamespace(date='2026-10-03', stage='abc', experience_ledger=[], repair_id=[])
    with pytest.raises(RuntimeError, match='Evidence unavailable'):
        driver.run(CASES, options, object())
    options.repair_id = [identifier]
    with pytest.raises(RuntimeError, match='environment failure only'):
        driver.run(CASES, options, object())
    records = driver.rows(isolated / 'eval/results/2026-10-03/attempts.jsonl')
    assert len(records) == 1 and records[0]['evidence_error']


def test_current_complete_native_model_failure_does_not_stop_next_case(isolated, monkeypatch):
    planned = [('eval-1003-real-C-1', (CASES[0], 'C', 1)), ('eval-1003-boundary-C-1', (CASES[1], 'C', 1))]
    monkeypatch.setattr(driver, 'plan', lambda *args: planned)
    def execute(page, case, name, method, folder, baseline):
        save_ledger(folder / 'ledger.agnes.jsonl', ledger(session=name, reason='error'))
        return dict(status='failed', session=name, pre_request_failure=False, environment_failure=True, environment_reason='archive', evidence_error=True)
    monkeypatch.setattr(driver, 'execute', execute)
    driver.run(CASES, SimpleNamespace(date='2026-10-03', stage='abc', experience_ledger=[]), object())
    records = driver.rows(isolated / 'eval/results/2026-10-03/attempts.jsonl')
    assert len(records) == 2 and all(not row['environment_failure'] and not row['evidence_error'] for row in records)


def test_dataset_snapshot_rejects_changes_to_unstarted_case_or_template(isolated, monkeypatch):
    identifier = 'eval-1003-real-A-1'
    monkeypatch.setattr(driver, 'plan', lambda *args: [(identifier, (CASES[0], 'A', 1))])
    monkeypatch.setattr(driver, 'backend', lambda *args: dict(version=1))
    options = SimpleNamespace(date='2026-10-03', stage='abc', experience_ledger=[])
    driver.run(CASES, options)
    changed = [CASES[0], dict(CASES[1], text='unstarted case changed'), CASES[2]]
    with pytest.raises(RuntimeError, match='Case dataset changed'):
        driver.run(changed, options)
    template = driver.resolve('real')
    template.write_text(template.read_text(encoding='utf-8') + '\n', encoding='utf-8')
    with pytest.raises(RuntimeError, match='Case dataset changed'):
        driver.run(CASES, options)


@pytest.mark.parametrize('method', ['B', 'C', 'D', 'E'])
def test_public_model_selection_uses_exact_flash_even_when_pro_is_first(isolated, monkeypatch, method):
    page = FakePage(isolated, 'eval-1003-r1-real-' + method + '-1')
    def goto(url):
        assert url == driver.URL
        page.queue = [dict(type='gz.ready', models=[MODELS[1], MODELS[0], MODELS[2]])]
    monkeypatch.setattr(page, 'goto', goto)
    model, restore = driver.fill(page, CASES[0], page.identifier, method)
    expected = 'agnes-3.0-flash' if method == 'E' else 'deepseek-flash'
    assert model['id'] == expected and restore['id'] == 'deepseek-flash'
    assert ('select', '#design-model', 'public/' + expected) in page.calls
    assert ('select', '#design-model', 'public/deepseek-v4-pro') not in page.calls


@pytest.mark.parametrize('method', ['B', 'C', 'D', 'E'])
def test_missing_exact_flash_stops_before_model_request_and_never_uses_pro(isolated, monkeypatch, method):
    page = FakePage(isolated, 'eval-1003-r1-real-' + method + '-1')
    def goto(url):
        assert url == driver.URL
        page.queue = [dict(type='gz.ready', models=[MODELS[1], MODELS[2],
                      dict(route='public', id='deepseek-v4-flash', label='Wrong Flash ID')])]
    monkeypatch.setattr(page, 'goto', goto)
    outcome = driver.execute(page, CASES[0], page.identifier, method, isolated, 0)
    assert outcome['status'] == 'failed' and outcome['pre_request_failure'] and outcome['environment_failure']
    assert outcome['session'] is None and ('click', '[data-action="start"]') not in page.calls
    assert not any(call[0] == 'select' and call[1] == '#design-model' for call in page.calls)


@pytest.mark.parametrize('method', ['C', 'D'])
def test_native_pro_request_is_rejected_even_if_ui_selected_flash(isolated, method):
    identifier = 'eval-1003-r1-real-' + method + '-1'
    folder = isolated / 'runs/eval-1003' / (identifier + '-driver')
    folder.mkdir(parents=True)
    page = FakePage(isolated, identifier, auto_finish=True, events=ledger(model=dict(route='public', id='deepseek-v4-pro')))
    outcome = driver.execute(page, CASES[0], identifier, method, folder, 0)
    assert outcome['status'] == 'failed' and outcome['environment_failure'] and not outcome['pre_request_failure']
    assert ('select', '#design-model', 'public/deepseek-flash') in page.calls
    assert ('select', '#design-model', 'public/deepseek-v4-pro') not in page.calls


def test_d_accepts_native_flash_experience_before_starting_case(isolated, monkeypatch):
    identifier = 'eval-1003-r1-boundary-D-1'
    monkeypatch.setattr(driver, 'plan', lambda *args: [(identifier, (CASES[1], 'D', 1))])
    experience = isolated / 'experience.ledger.agnes.jsonl'
    save_ledger(experience, ledger(session='experience', requests=2))
    original = experience.read_bytes()
    calls = []
    def execute(page, case, name, method, folder, baseline):
        calls.append(name)
        save_ledger(folder / 'ledger.agnes.jsonl', ledger(session=name, reason='error'))
        return dict(status='failed', session=name, pre_request_failure=False)
    monkeypatch.setattr(driver, 'execute', execute)
    driver.run(CASES, SimpleNamespace(date='2026-10-03', stage='d', experience_ledger=[experience]), object())
    assert calls == [identifier] and experience.read_bytes() == original
    attempts = driver.rows(isolated / 'eval/results/2026-10-03/attempts.jsonl')
    assert len(attempts) == 1 and attempts[0]['session'] == identifier


@pytest.mark.parametrize('requests', [0, 1])
def test_d_rejects_pro_or_requestless_experience_before_starting_case(isolated, monkeypatch, requests):
    identifier = 'eval-1003-r1-boundary-D-1'
    monkeypatch.setattr(driver, 'plan', lambda *args: [(identifier, (CASES[1], 'D', 1))])
    experience = isolated / 'experience.ledger.agnes.jsonl'
    save_ledger(experience, ledger(session='experience', requests=requests, model=dict(route='public', id='deepseek-v4-pro')))
    original = experience.read_bytes()
    monkeypatch.setattr(driver, 'execute', lambda *args: pytest.fail('D must not start with this experience ledger'))
    options = SimpleNamespace(date='2026-10-03', stage='d', experience_ledger=[experience])
    with pytest.raises(RuntimeError, match='native experience ledger whose requests all use deepseek-flash'):
        driver.run(CASES, options, object())
    assert experience.read_bytes() == original
    assert not driver.rows(isolated / 'eval/results/2026-10-03/attempts.jsonl')
