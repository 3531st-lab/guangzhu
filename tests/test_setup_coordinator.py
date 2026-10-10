"""Exercise production setup with a deterministic official-DTO transport; never contact AGH."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from fastapi.testclient import TestClient
import pytest

from guangzhu import api, setup, setup_agh


class Fake:
    def __init__(self, home, package):
        self.home, self.package = home, package
        self.calls, self.operations = [], {}
        self.mcp = None
        self.plugin = {}
        self.workspace = None
        self.skill = None
        self.fail = self.switch = self.retry = None
        self.state = 'failed'
        self.permissions = set(setup_agh.PERMISSIONS.values()) | {'skills.refresh', 'skills.trust', 'resources.skills.write',
                                                                 'packages.read', 'packages.install', 'packages.trust', 'packages.activate'}
        self.preview = dict(id=package['name'], version=package['version'], integrity='sha256-' + 'a' * 64,
            capabilityHash='b' * 64, license='MIT', blockers=[],
            contributions=[dict(kind='client', id='plugin/aa00000000000000', rowId='ext:guangzhu-studio/main',
                                path='./extensions/main/agnes.client.json', client=dict(entry='./client/index.js'))])

    def send(self, surface, action, body=None):
        self.calls.append((surface, action, copy.deepcopy(body)))
        if action == 'context':
            suffix = setup_agh.scope(self.home) if not self.switch else 'sha256-' + 'f' * 64
            return dict(profile='local-dev', clientId=('resource-admin-web-' if surface == 'resources' else 'admin-web-') + suffix,
                        readOnly=False, permissions=sorted(self.permissions))
        if action in setup_agh.WRITES[surface]:
            if self.retry == action:
                self.retry = None
                raise OSError('simulated receipt loss')
            assert set(body) >= {'profile', 'clientId', 'commandId'}
            operation = 'operation-' + str(len(self.operations))
            result = dict(operationId=operation, state=self.state if action == self.fail else (
                'succeeded' if surface == 'resources' else 'completed'))
            if action == self.fail and self.state in {'failed', 'rolled-back'}:
                result['error' if surface == 'plugins' else 'lastSafeError'] = dict(code='E_OPERATION_STATE', safeMessage='not ready')
            if action == 'inspect':
                result['preview'] = self.preview
            if action != self.fail:
                self.apply(action, body)
            self.operations[operation] = result
            return dict(operationId=operation, **({'state': 'received'} if surface == 'resources' else {'profile': 'local-dev'}))
        if action in {'operation/get', 'operations/get'}:
            assert set(body) == {'profile', 'operationId'}
            return copy.deepcopy(self.operations[body['operationId']])
        if action == 'mcp/list':
            return dict(items=[self.mcp] if self.mcp else [])
        if action == 'mcp/get':
            return copy.deepcopy(self.mcp)
        if action == 'mcp/status':
            return dict(connectionState='ready', observedRevision=self.mcp['revision'], toolCount=12, catalogRevision='c' * 64)
        if action == 'mcp/tools':
            return dict(items=[dict(name=name) for name in setup_agh.TOOLS], catalogRevision='c' * 64)
        if action == 'list':
            return dict(packages=[self.plugin] if self.plugin else [])
        if action == 'skills/list':
            assert body == dict(profile='local-dev', kind='skill', workspaceId=self.workspace)
            return dict(items=[self.skill], skillRoots=[dict(rootKey='workspace-agnes', state='ready')])
        if action == 'skills/get':
            return copy.deepcopy(self.skill)
        raise AssertionError((surface, action, body))

    def apply(self, action, body):
        if action.startswith('mcp/'):
            if action == 'mcp/create':
                assert set(body) == {'profile', 'clientId', 'commandId', 'definition'}
                self.mcp = dict(serverId='guangzhu', definition=body['definition'], revision='0' * 63 + '1', trust='untrusted',
                                desired='disabled', actual='stopped')
            else:
                assert body['expectedRevision'] == self.mcp['revision']
                self.mcp['revision'] = f"{int(self.mcp['revision'], 16) + 1:064x}"
                if action == 'mcp/update':
                    self.mcp.update(definition=body['definition'], trust='untrusted')
                if action == 'mcp/trust':
                    self.mcp['trust'] = body['trust']
                if action in {'mcp/enable', 'mcp/reconnect'}:
                    self.mcp.update(desired='enabled', actual='ready')
                if action == 'mcp/disable':
                    self.mcp.update(desired='disabled', actual='stopped')
        elif action in {'install', 'update'}:
            assert 'expectedRevision' not in body
            assert body['expectedIntegrity'] == self.preview['integrity']
            self.plugin = dict(id=self.package['name'], version=self.package['version'], integrity=body['expectedIntegrity'],
                               capabilityHash=self.preview['capabilityHash'], trusted=False, desired='installed-disabled', actual='not-running', blockers=[])
        elif action == 'trust':
            self.plugin['trusted'] = True
        elif action == 'enable':
            self.plugin.update(desired='enabled', actual='running', actualIntegrity=self.plugin['integrity'])
        elif action == 'skills/refresh':
            assert body['rootKey'] == 'workspace-agnes'
            self.workspace = body['workspaceId']
            self.skill = dict(name='pv-rooftop-design', resourceId='skill/public-installation', revision='0' * 63 + '1', workspaceId=self.workspace,
                sourceIdentity=dict(rootKey='workspace-agnes'), resolution=dict(winner=True), trust='untrusted', desired='disabled',
                actual='blocked', stale=False)
        elif action.startswith('skills/'):
            assert body['expectedRevision'] == self.skill['revision']
            self.skill['revision'] = f"{int(self.skill['revision'], 16) + 1:064x}"
            self.skill.update(trust='trusted') if action == 'skills/trust' else self.skill.update(desired='enabled', actual='ready')

    @property
    def writes(self):
        return [call for call in self.calls if call[1] in setup_agh.WRITES[call[0]]]


@pytest.fixture
def installed(tmp_path, monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('GUANGZHU_DATA_HOME', str(tmp_path / 'local/guangzhu'))
    root = tmp_path / '光筑'
    package = dict(name='guangzhu-studio', version='0.3.9', license='MIT', agnes=dict(plugins=[dict(id='ext:guangzhu-studio/main')],
        clientDescriptors=[dict(rowId='ext:guangzhu-studio/main', path='./extensions/main/agnes.client.json')]))
    for path, content in [('build-manifest.json', '{}'), ('runtime/agh/agnes-win32-x64.exe', ''),
                          ('plugins/release/package.json', json.dumps(package))]:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    home = tmp_path / 'local/guangzhu/agh'
    (home / 'data').mkdir(parents=True)
    fake, starts, logs = Fake(home, package), [], []
    coordinator = setup.Coordinator(root, start=lambda **kw: starts.append(kw), send=fake.send,
                                    analyze=lambda root: dict(passed=True, failures=[]), port=lambda: False, probe=lambda root: True)
    coordinator.log = logs.append
    coordinator.step(1, True, 'Windows/WebView2 passed')
    return coordinator, fake, starts, logs


def wait(coordinator, phase):
    deadline = time.monotonic() + 3
    while coordinator.data['phase'] not in {phase, 'failed'} and time.monotonic() < deadline:
        threading.Event().wait(.01)
    assert coordinator.data['phase'] == phase, coordinator.public()


def workspace(coordinator):
    return dict(path=str(coordinator.root), workspaceId=hashlib.sha256(str(coordinator.root).encode()).hexdigest(), available=True)


def bridge(coordinator):
    coordinator.complete(coordinator.data['operation_id'], workspace(coordinator))
    wait(coordinator, 'waiting_models')


def models(ready=False):
    return dict(profile='local-dev', designConfigured=ready, reviewConfigured=ready,
                design=dict(id='design-model', route='public-design'), review=dict(id='review-model', route='public-review'),
                models=[dict(id='design-model', route='public-design'), dict(id='review-model', route='public-review')])


def test_get_and_incomplete_restart_never_start_or_mutate(installed, monkeypatch):
    coordinator, fake, starts, _ = installed
    monkeypatch.setattr(api, 'ROOT', coordinator.root)
    monkeypatch.setattr(api.app.state, 'setup', coordinator, raising=False)
    monkeypatch.setattr(api, 'reachable', lambda: False)
    client = TestClient(api.app)
    for _ in range(3):
        status = client.get('/api/setup/status').json()
        assert not status['ready'] and status['phase'] == 'unconfigured'
    coordinator.resume()
    assert not fake.calls and not starts
    assert client.get('/api/status').json()['installation'] == coordinator.installation


def test_own_keyless_then_complete_and_restart_revalidates_without_writes(installed):
    coordinator, fake, starts, logs = installed
    operation = coordinator.begin()['operation_id']
    wait(coordinator, 'waiting_workspace')
    assert len(starts) == 1 and starts[0] == dict(executable=str(coordinator.root / 'runtime/agh/agnes-win32-x64.exe'),
        home=str(coordinator.home), profile='local-dev', cwd=str(coordinator.root))
    bridge(coordinator)
    public = coordinator.models(operation, models())
    assert not public['ready']
    assert [row['state'] for row in public['steps']] == ['ready'] * 5 + ['waiting', 'ready']
    keyless = coordinator.restart_binding()
    assert keyless and keyless['completed'], 'tools, plugin, workspace and Skill are finished even before any key exists'
    assert coordinator.models(operation, models(True))['ready']
    cache = json.loads(coordinator.cache.read_text(encoding='utf-8'))
    assert not any('model' in key for key in cache) and cache['completed'] and cache['offline_passed']
    writes = len(fake.writes)
    restarted = setup.Coordinator(coordinator.root, start=lambda **kw: starts.append(kw), send=fake.send, port=lambda: False)
    restarted.log = logs.append
    restarted.step(1, True, 'passed')
    restarted.probe = lambda root: True
    assert restarted.restart_binding() == cache
    assert restarted.resume()['phase'] == 'waiting_models'
    assert [action for _, action, _ in fake.writes[writes:]] == ['inspect'] and len(starts) == 2  # restart only inspects the shipped plugin
    assert restarted.models(restarted.data['operation_id'], models(True))['ready']


def test_one_begin_and_one_bridge_completion(installed):
    coordinator, fake, starts, _ = installed
    gate = threading.Event()
    coordinator.analyze = lambda root: (gate.wait(3) or True) and dict(passed=True)
    first = coordinator.begin()
    assert coordinator.begin()['operation_id'] == first['operation_id']
    gate.set()
    wait(coordinator, 'waiting_workspace')
    with pytest.raises(ValueError, match='编号'):
        coordinator.complete('wrong', workspace(coordinator))
    with pytest.raises(ValueError, match='工作区'):
        coordinator.complete(first['operation_id'], workspace(coordinator) | dict(workspaceId='0' * 64))
    before = len(fake.writes)
    bridge(coordinator)
    with pytest.raises(ValueError, match='编号'):
        coordinator.complete(first['operation_id'], workspace(coordinator))
    assert len(starts) == 1 and len(fake.writes) == before + 3


@pytest.mark.parametrize('surface,state', [('resources', 'completed'), ('resources', 'failed'), ('resources', 'cancelled'),
                                         ('plugins', 'succeeded'), ('plugins', 'rolled-back'), ('plugins', 'cancelled')])
def test_terminal_vocabularies_fail_and_stop(installed, surface, state):
    coordinator, fake, _, logs = installed
    fake.fail, fake.state = ('mcp/create' if surface == 'resources' else 'inspect'), state
    coordinator.begin()
    wait(coordinator, 'failed')
    assert fake.writes[-1][1] == fake.fail
    assert logs[-1]['result'] == 'failed'
    assert coordinator.data['steps'][6]['state'] == 'ready'
    if state in {'failed', 'rolled-back'}:
        assert any(row.get('error_code') == 'E_OPERATION_STATE' and row.get('state') == state for row in logs)


def test_retry_same_command_and_changed_resource_fresh_revisions(installed):
    coordinator, fake, _, _ = installed
    fake.retry = 'mcp/create'
    coordinator.begin()
    wait(coordinator, 'waiting_workspace')
    creates = [body for _, action, body in fake.writes if action == 'mcp/create']
    assert len(creates) == 2 and creates[0] == creates[1]
    fake.mcp['definition'] = fake.mcp['definition'] | dict(displayName='old')
    start = len(fake.calls)
    coordinator.client.mcp(coordinator.definition, configure=True)
    writes = [call for call in fake.calls[start:] if call[1] in setup_agh.WRITES[call[0]]]
    assert [call[1] for call in writes] == ['mcp/disable', 'mcp/update', 'mcp/trust', 'mcp/enable', 'mcp/reconnect']
    assert len({body['commandId'] for _, _, body in writes}) == 5
    assert len({body['expectedRevision'] for _, _, body in writes}) == 5


@pytest.mark.parametrize('kind', ['foreign-port', 'identity', 'permission'])
def test_context_failures_do_not_write(installed, kind):
    coordinator, fake, starts, _ = installed
    if kind == 'foreign-port':
        coordinator.port = lambda: True
    fake.switch = kind in {'foreign-port', 'identity'}
    if kind == 'permission':
        fake.permissions.clear()
    coordinator.begin()
    wait(coordinator, 'failed')
    assert not fake.writes
    if kind == 'foreign-port':
        assert not starts and '被别的程序占用' in coordinator.data['error']


def test_our_own_instance_already_on_the_port_is_reused_without_a_second_start(installed):
    coordinator, fake, starts, _ = installed
    coordinator.port = lambda: True
    coordinator.begin()
    wait(coordinator, 'waiting_workspace')
    assert not starts and fake.writes


def test_exact_tools_and_identity_switch_on_bridge(installed):
    coordinator, fake, _, _ = installed
    coordinator.begin()
    wait(coordinator, 'waiting_workspace')
    original = fake.send
    def missing(surface, action, body=None):
        row = original(surface, action, body)
        if action == 'mcp/tools':
            row['items'][-1] = dict(name='wrong-tool')
        return row
    coordinator.client.send = missing
    with pytest.raises(ValueError, match='12'):
        coordinator.client.mcp(coordinator.definition)
    before = len(fake.writes)
    fake.switch = True
    coordinator.complete(coordinator.data['operation_id'], workspace(coordinator))
    wait(coordinator, 'failed')
    assert len(fake.writes) == before


def test_missing_callback_and_stale_build_cache(installed):
    coordinator, fake, starts, _ = installed
    coordinator.start = None
    coordinator.begin()
    wait(coordinator, 'failed')
    assert not starts and not fake.calls
    coordinator.cache.parent.mkdir(exist_ok=True)
    coordinator.cache.write_text(json.dumps(dict(installation_id='different-build', completed=True)), encoding='utf-8')
    assert setup.Coordinator(coordinator.root).restart_binding() is None


def test_mutation_host_origin_and_bounded_schema(installed, monkeypatch):
    coordinator, fake, starts, _ = installed
    monkeypatch.setattr(api, 'ROOT', coordinator.root)
    monkeypatch.setattr(api.app.state, 'setup', coordinator, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8765')
    assert client.post('/api/setup/configure', json={}).status_code == 403
    headers = dict(Origin='http://127.0.0.1:8765')
    assert client.post('/api/setup/configure', json=dict(choice='own'), headers=headers).status_code == 400
    assert client.post('/api/setup/configure', json=dict(executable='unapproved'), headers=headers).status_code == 400
    assert not fake.calls and not starts
    result = client.post('/api/setup/configure', json={}, headers=headers)
    assert result.status_code == 200 and result.json()['operation_id']
    wait(coordinator, 'waiting_workspace')


def test_model_denied_false_and_private_metadata_rejected(installed):
    coordinator, fake, _, _ = installed
    coordinator.begin()
    wait(coordinator, 'waiting_workspace')
    bridge(coordinator)
    operation = coordinator.data['operation_id']
    assert not coordinator.models(operation, models())['ready']
    with pytest.raises(ValueError, match='公开'):
        coordinator.models(operation, models(True) | dict(accounts=[]))
    metadata = models(True)
    metadata['review']['route'] = 'unconfigured-route'
    assert not coordinator.models(operation, metadata)['ready']


def test_installed_export_uses_selected_instance_and_ignores_dev_defaults(installed, monkeypatch):
    coordinator, fake, _, _ = installed
    monkeypatch.setattr(api, 'ROOT', coordinator.root)
    monkeypatch.setattr(api.app.state, 'setup', coordinator, raising=False)
    with pytest.raises(ValueError, match='准备'):
        api.settings()
    coordinator.begin()
    wait(coordinator, 'waiting_workspace')
    bridge(coordinator)
    coordinator.models(coordinator.data['operation_id'], models(True))
    assert api.settings() == dict(agh_runtime=str(coordinator.root / 'runtime/agh/agnes-win32-x64.exe'),
                                  agh_home=str(fake.home), agh_profile='local-dev')


def test_read_only_setup_does_not_claim_developer_runtime_is_bundled(tmp_path):
    coordinator = setup.Coordinator(tmp_path)
    status = coordinator.status()
    assert status['ready'] and status['required'] is False and status['steps'][1]['state'] == 'waiting'


def test_http_fixed_origin_minimal_dto_and_no_url_inputs(monkeypatch):
    seen = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return b'{"items":[]}'
    def receive(request, **kwargs):
        seen.append(request)
        assert kwargs == dict(timeout=3)
        return Response()
    monkeypatch.setattr(setup_agh, 'urlopen', receive)
    setup_agh.transport('resources', 'mcp/list', dict(profile='local-dev'))
    request = seen[0]
    assert request.full_url == 'http://127.0.0.1:4177/admin/resources/api/mcp/list'
    assert request.headers['Origin'] == 'http://127.0.0.1:4177' and request.headers['Host'] == '127.0.0.1:4177'
    assert json.loads(request.data) == dict(profile='local-dev')


@pytest.mark.parametrize('change', ['license', 'contribution', 'blocker', 'wrong-root'])
def test_preview_gate_precedes_install_and_keeps_safe_errors(installed, change, tmp_path):
    coordinator, fake, _, logs = installed
    if change == 'license':
        fake.preview['license'] = 'unapproved'
    if change == 'contribution':
        fake.preview['contributions'] = []
    if change == 'blocker':
        fake.preview['blockers'] = [dict(code='BLOCKED')]
    if change == 'wrong-root':
        fake.fail = 'inspect'
    coordinator.begin()
    wait(coordinator, 'failed')
    assert fake.writes[-1][1] == 'inspect'
    assert all('authScope' not in row and 'accounts' not in row for row in logs)


def test_failure_can_retry_explicitly_and_completed_conflicting_port_does_not_start(installed):
    coordinator, fake, starts, _ = installed
    fake.fail = 'mcp/create'
    first = coordinator.begin()['operation_id']
    wait(coordinator, 'failed')
    fake.fail = None
    assert coordinator.begin()['operation_id'] != first
    wait(coordinator, 'waiting_workspace')
    bridge(coordinator)
    coordinator.models(coordinator.data['operation_id'], models(True))
    restarted = setup.Coordinator(coordinator.root, start=lambda **kw: starts.append(kw), send=fake.send, port=lambda: True)
    restarted.probe = lambda root: True
    restarted.log = lambda row: None
    restarted.step(1, True, 'passed')
    writes, started = len(fake.writes), len(starts)
    assert restarted.resume()['phase'] == 'waiting_models'
    assert len(starts) == started and [action for _, action, _ in fake.writes[writes:]] == ['inspect']
    fake.switch = True
    foreign = setup.Coordinator(coordinator.root, start=lambda **kw: starts.append(kw), send=fake.send, port=lambda: True,
                                analyze=lambda root: dict(passed=True), probe=lambda root: True)
    foreign.log = lambda row: None
    foreign.step(1, True, 'passed')
    foreign.resume()
    wait(foreign, 'failed')
    assert len(starts) == started and [action for _, action, _ in fake.writes[writes:]] == ['inspect'] and '被别的程序占用' in foreign.data['error']


def export_cli_grammar(argv):
    """Pinned AGH 5da4073 args.ts dispatches only argv[0]; parse the supported export grammar."""
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export', allow_abbrev=False)
    export.add_argument('session')
    export.add_argument('--profile')
    export.add_argument('--format', choices=['agnes', 'sharegpt', 'claude-code'], required=True)
    export.add_argument('--out', required=True)
    sessions = commands.add_parser('sessions', allow_abbrev=False)
    sessions.add_argument('action', choices=['list'])
    sessions.add_argument('--profile')
    sessions.add_argument('--json', action='store_true')
    return parser.parse_args(argv)


@pytest.mark.parametrize('tail', [['export', 'parent', '--format', 'agnes', '--out', 'ledger'], ['sessions', 'list', '--json']])
def test_export_cli_grammar_rejects_profile_before_command(tail):
    with pytest.raises(SystemExit) as caught:
        export_cli_grammar(['--profile', 'local-dev', *tail])
    assert caught.value.code == 2


@pytest.mark.parametrize('discovery', ['cost', 'sessions'])
def test_export_passes_binding_to_parent_sessions_and_child_subprocesses(tmp_path, monkeypatch, discovery):
    from test_agh_runs import reviewed_ledgers, resequence
    from scripts import agh_export_run as exporter
    parent, child = reviewed_ledgers()
    sid = parent[0]['data']['key']
    child_id = exporter.own_events(child)[0]['data']['key']
    if discovery == 'cost':
        cost = copy.deepcopy(parent[-1])
        cost.update(type='subagent/cost', data=dict(childKey=child_id), origin='system', trust='trusted')
        parent = resequence(parent + [cost])
    calls = []
    env = dict(AGH_HOME='explicit-public-home')
    monkeypatch.delenv('AGH_HOME', raising=False)
    def run(command, **kwargs):
        assert command[0] == 'fixed-bundled-executable'
        parsed = export_cli_grammar(command[1:])
        assert parsed.profile == 'local-dev'
        assert kwargs['env'] == env
        assert kwargs['check'] and kwargs['capture_output']
        calls.append(parsed)
        if parsed.command == 'sessions':
            assert parsed.action == 'list' and parsed.json
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(dict(items=[dict(sessionId=child_id)])))
        assert parsed.format == 'agnes' and parsed.session in (sid, child_id)
        ledger = Path(parsed.out)
        events = child if parsed.session == child_id else parent
        ledger.write_text(''.join(json.dumps(event) + '\n' for event in events), encoding='utf-8')
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(exporter.subprocess, 'run', run)
    folder = exporter.export_run(sid, 'changzhou-demo', 'binding', root=tmp_path, executable='fixed-bundled-executable',
                                 with_children=True, env=env, profile='local-dev')
    assert [call.command for call in calls] == (['export', 'export'] if discovery == 'cost' else ['export', 'sessions', 'export'])
    assert [call.session for call in calls if call.command == 'export'] == [sid, child_id]
    metadata = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    assert metadata['children_complete'] is True and metadata['children_errors'] == []
    assert [row['session'] for row in metadata['children']] == [child_id]
    assert exporter.read_events(folder / metadata['children'][0]['ledger'], inherited=True) == exporter.sanitize(child)


def test_poll_timeout_stops_without_second_write(installed, monkeypatch):
    coordinator, fake, _, _ = installed
    fake.fail, fake.state = 'mcp/create', 'running'
    monkeypatch.setattr(setup_agh.time, 'sleep', lambda delay: None)
    coordinator.begin()
    wait(coordinator, 'failed')
    assert len(fake.writes) == 1
    assert len([call for call in fake.calls if call[1] == 'operations/get']) == 60


def test_identical_healthy_resource_skips_writes_and_bad_catalog_reconnects(installed):
    coordinator, fake, _, _ = installed
    coordinator.begin()
    wait(coordinator, 'waiting_workspace')
    before = len(fake.writes)
    coordinator.client.mcp(coordinator.definition, configure=True)
    assert len(fake.writes) == before
    original = fake.send
    broken = [True]
    def send(surface, action, body=None):
        result = original(surface, action, body)
        if action == 'mcp/reconnect':
            broken[0] = False
        if action == 'mcp/tools' and broken[0]:
            result['items'].pop()
        return result
    coordinator.client.send = send
    coordinator.client.mcp(coordinator.definition, configure=True)
    assert [action for _, action, _ in fake.writes[before:]] == ['mcp/reconnect']


def test_skill_identity_switch_stops_before_trust(installed):
    coordinator, fake, _, _ = installed
    coordinator.begin()
    wait(coordinator, 'waiting_workspace')
    original = fake.send
    def send(surface, action, body=None):
        result = original(surface, action, body)
        if action == 'skills/get':
            result['workspaceId'] = '0' * 64
        return result
    coordinator.client.send = send
    coordinator.complete(coordinator.data['operation_id'], workspace(coordinator))
    wait(coordinator, 'failed')
    assert fake.writes[-1][1] == 'skills/refresh'


def test_offline_failure_blocks_resource_writes_and_changed_manifest_invalidates_cache(installed):
    coordinator, fake, _, _ = installed
    coordinator.analyze = lambda root: dict(passed=False, failures=['native dependency failed'])
    coordinator.begin()
    wait(coordinator, 'failed')
    assert not fake.writes and coordinator.data['steps'][6]['state'] == 'failed'
    coordinator.cache.parent.mkdir(exist_ok=True)
    coordinator.cache.write_text(json.dumps(dict(installation_id=coordinator.installation['id'], completed=True)), encoding='utf-8')
    (coordinator.root / 'build-manifest.json').write_text('{"build":"different"}', encoding='utf-8')
    restarted = setup.Coordinator(coordinator.root)
    restarted.probe = lambda root: True
    assert restarted.restart_binding() is None and restarted.status()['phase'] == 'unconfigured'


def test_api_simultaneous_factory_and_begin_share_one_pipeline(installed, monkeypatch):
    original, fake, starts, logs = installed
    entered, contended, release, analysis_release = [threading.Event() for _ in range(4)]
    constructors = []
    actual_lock = threading.Lock()
    lock_calls = []
    class ObservedLock:
        def __enter__(self):
            lock_calls.append(True)
            if len(lock_calls) == 2:
                contended.set()
            actual_lock.acquire()
        def __exit__(self, *args):
            actual_lock.release()
    def construct(root, start=None):
        constructors.append(root)
        if len(constructors) > 1:
            contended.set()
        entered.set()
        assert release.wait(3)
        coordinator = setup.Coordinator(root, start=start, send=fake.send, port=lambda: False, probe=lambda root: True,
            analyze=lambda root: analysis_release.wait(3) and dict(passed=True))
        coordinator.log = logs.append
        coordinator.step(1, True, 'passed')
        return coordinator
    def begin():
        coordinator = api.setup_coordinator()
        return coordinator, coordinator.begin()['operation_id']
    monkeypatch.setattr(api, 'ROOT', original.root)
    monkeypatch.setattr(api, 'Coordinator', construct)
    monkeypatch.setattr(api, 'SETUP_LOCK', ObservedLock(), raising=False)
    monkeypatch.setattr(api.app.state, 'setup', None, raising=False)
    monkeypatch.setattr(api.app.state, 'start_agh', lambda **kw: starts.append(kw), raising=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(begin)
        try:
            assert entered.wait(3)
            second = pool.submit(begin)
            assert contended.wait(3)
        finally:
            release.set()
        results = [first.result(3), second.result(3)]
        analysis_release.set()
    assert len(constructors) == 1
    assert results[0][0] is results[1][0]
    assert results[0][1] == results[1][1]
    wait(results[0][0], 'waiting_workspace')
    assert len(starts) == 1
    assert [action for _, action, _ in fake.writes].count('mcp/create') == 1
    assert [action for _, action, _ in fake.writes].count('install') == 1


def test_api_factory_root_change_and_export_lock_are_independent(installed, monkeypatch, tmp_path):
    coordinator, fake, starts, _ = installed
    monkeypatch.setattr(api, 'ROOT', coordinator.root)
    monkeypatch.setattr(api.app.state, 'setup', None, raising=False)
    with api.LOCK:
        first = api.setup_coordinator()
        assert api.setup_coordinator() is first
        other = tmp_path / 'another-installation'
        monkeypatch.setattr(api, 'ROOT', other)
        second = api.setup_coordinator()
        assert second is api.setup_coordinator() and second is not first
        assert second.root == other.resolve()
    assert not fake.calls and not starts


@pytest.mark.parametrize('content', ['{', '[]', 'null', '42', '"scalar"', '{}', '{"completed":true}',
    '{"agh_home":[]}', '{"installation_id":"wrong","completed":true}'])
def test_malformed_binding_is_ignored_readonly_and_begin_recovers(installed, monkeypatch, content):
    original, fake, starts, logs = installed
    original.cache.parent.mkdir(parents=True, exist_ok=True)
    original.cache.write_text(content, encoding='utf-8')
    before = original.cache.read_bytes()
    def construct(root, start=None):
        coordinator = setup.Coordinator(root, start=lambda **kw: starts.append(kw), send=fake.send,
            analyze=lambda root: dict(passed=True), port=lambda: False, probe=lambda root: True)
        coordinator.log = logs.append
        coordinator.step(1, True, 'passed')
        return coordinator
    monkeypatch.setattr(api, 'ROOT', original.root)
    monkeypatch.setattr(api, 'Coordinator', construct)
    monkeypatch.setattr(api.app.state, 'setup', None, raising=False)
    client = TestClient(api.app)
    for _ in range(2):
        state = client.get('/api/setup/status').json()
        assert state['phase'] == 'unconfigured' and not state['ready'] and 'error' not in state
    coordinator = api.setup_coordinator()
    assert coordinator.restart_binding() is None
    coordinator.resume()
    assert not fake.calls and not starts and not logs
    assert original.cache.read_bytes() == before
    with pytest.raises(ValueError, match='准备'):
        api.settings()
    result = client.post('/api/setup/configure', json={}, headers={'Origin': 'http://127.0.0.1:8765',
        'Host': '127.0.0.1:8765'})
    assert result.status_code == 200
    assert 'error' not in result.json()
    wait(coordinator, 'waiting_workspace')
    bridge(coordinator)
    assert coordinator.models(coordinator.data['operation_id'], models(True))['ready']
    assert setup.Coordinator(original.root).restart_binding() is not None
    assert len(starts) == 1


@pytest.mark.parametrize('failure', [PermissionError('private read failure'), UnicodeError('private decode failure')])
def test_unreadable_binding_never_authorizes_restart(installed, monkeypatch, failure):
    original, fake, starts, logs = installed
    read_text = Path.read_text
    def read(path, *args, **kwargs):
        if path == original.cache:
            raise failure
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    coordinator = setup.Coordinator(original.root, start=lambda **kw: starts.append(kw), send=fake.send,
        probe=lambda root: True, port=lambda: False, analyze=lambda root: dict(passed=True))
    coordinator.log = logs.append
    coordinator.step(1, True, 'passed')
    assert coordinator.status()['phase'] == 'unconfigured'
    assert 'private' not in coordinator.public().get('error', '')
    assert coordinator.restart_binding() is None
    coordinator.resume()
    assert not fake.calls and not starts and not logs and not original.cache.exists()
    monkeypatch.setattr(Path, 'read_text', read_text)
    coordinator.begin()
    wait(coordinator, 'waiting_workspace')
    bridge(coordinator)
    assert coordinator.models(coordinator.data['operation_id'], models(True))['ready']
    assert setup.Coordinator(original.root).restart_binding() is not None


@pytest.mark.parametrize('changes', [dict(completed='true'), dict(completed=1), dict(offline_passed=1), dict(offline_passed=False),
    dict(choice=['own']), dict(choice='unknown'), dict(profile='other'), dict(agh_home=[]), dict(agh_home='relative'),
    dict(agh_home=''), dict(agh_home='x' * 1025), dict(workspace_id='0' * 64), dict(integrity=[]), dict(integrity='wrong'),
    dict(installation_id='0' * 64), dict(extra='private'), dict(agh_home='C:\\different-owned-home')])
def test_invalid_public_binding_schema_never_authorizes_restart(installed, changes):
    original, fake, starts, logs = installed
    original.begin()
    wait(original, 'waiting_workspace')
    bridge(original)
    original.models(original.data['operation_id'], models(True))
    content = json.dumps(original.binding | changes)
    original.cache.write_text(content, encoding='utf-8')
    before = len(fake.calls), len(starts), len(logs)
    coordinator = setup.Coordinator(original.root, start=lambda **kw: starts.append(kw), send=fake.send,
        probe=lambda root: True)
    coordinator.log = logs.append
    coordinator.step(1, True, 'passed')
    assert coordinator.restart_binding() is None
    assert coordinator.status()['phase'] == 'unconfigured'
    coordinator.resume()
    assert (len(fake.calls), len(starts), len(logs)) == before
    assert original.cache.read_text(encoding='utf-8') == content


def test_valid_legacy_development_settings_still_supply_export_defaults(tmp_path, monkeypatch):
    cache = tmp_path / 'desktop/settings.json'
    cache.parent.mkdir()
    values = dict(agh_runtime='existing-development-runtime', agh_home='existing-development-home')
    cache.write_text(json.dumps(values), encoding='utf-8')
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    assert api.settings() == values


def test_offline_child_is_hidden_and_failure_stderr_is_private(tmp_path, monkeypatch):
    calls = []
    results = [subprocess.CompletedProcess([], 0, '{"passed":true}', ''),
               subprocess.CompletedProcess([], 1, '', 'private runtime stderr')]
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return results.pop(0)
    monkeypatch.setattr(setup.subprocess, 'run', run)
    monkeypatch.setattr(setup.subprocess, 'CREATE_NO_WINDOW', 0x08000000, raising=False)
    assert setup.offline(tmp_path) == dict(passed=True)
    command, kwargs = calls[0]
    assert command[:5] == [str(tmp_path / 'runtime/python/python.exe'), '-X', 'utf8', '-B', '-c']
    assert 'offline_analysis()' in command[5]
    assert kwargs == dict(cwd=tmp_path, capture_output=True, text=True, encoding='utf-8', timeout=180,
                          creationflags=0x08000000)
    with pytest.raises(ValueError, match='内置 Python 或发电计算组件无法运行') as error:
        setup.offline(tmp_path)
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('encoding', ['cp936', 'ascii'])
def test_offline_real_child_preserves_chinese_json_under_non_utf8_locale(tmp_path, monkeypatch, encoding):
    package = tmp_path / 'guangzhu'
    package.mkdir()
    (package / '__init__.py').write_text('', encoding='utf-8')
    (package / 'selfcheck.py').write_text(
        'import sys\ndef offline_analysis():\n'
        '    return {"passed": True, "reason": "通过遮挡检查", "utf8_mode": sys.flags.utf8_mode}\n', encoding='utf-8')
    monkeypatch.setenv('PYTHONIOENCODING', encoding)
    monkeypatch.setenv('PYTHONUTF8', '0')
    monkeypatch.delenv('PYTHONPATH', raising=False)
    run = subprocess.run
    outputs = []
    def actual_child(command, **kwargs):
        result = run([sys.executable, *command[1:]], **kwargs)
        outputs.append(result.stdout)
        return result
    monkeypatch.setattr(setup.subprocess, 'run', actual_child)
    assert setup.offline(tmp_path) == dict(passed=True, reason='通过遮挡检查', utf8_mode=1)
    assert outputs[0].isascii()


class OwnedFake:
    def __init__(self, fail=False):
        self.fail, self.starts, self.closed = fail, [], 0

    def start(self, **values):
        if self.fail:
            raise RuntimeError('光筑自带的 AGH 未能启动。')
        self.starts.append(values)

    def close(self):
        self.closed += 1


@pytest.mark.parametrize('broken', [False, True])
def test_installer_entry_configures_everything_but_the_workspace_and_always_stops_its_agh(installed, monkeypatch, broken, capsys):
    coordinator, fake, _, logs = installed
    from guangzhu import agh_process
    owned = OwnedFake(fail=broken)
    monkeypatch.setattr(agh_process, 'OwnedAgh', lambda: owned)
    original = setup.Coordinator
    def build(root, start=None):
        made = original(root, start=start, send=fake.send, analyze=lambda root: dict(passed=True), port=lambda: False,
                        probe=lambda root: True)
        made.log = logs.append
        return made
    monkeypatch.setattr(setup, 'Coordinator', build)
    code = setup.install(coordinator.root)
    assert owned.closed == 1
    assert code == (1 if broken else 0)
    assert logs[-1]['result'] == 'install' and logs[-1]['phase'] == ('failed' if broken else 'waiting_workspace')
    if broken:
        assert not fake.writes and '未能启动' in capsys.readouterr().err
    else:
        assert len(owned.starts) == 1
        assert [action for _, action, _ in fake.writes].count('mcp/create') == 1
        assert not any(action.startswith('skills/') for _, action, _ in fake.writes)


def test_launch_resumes_a_finished_setup_and_otherwise_configures_without_asking(installed):
    coordinator, fake, starts, logs = installed
    assert coordinator.launch()['phase'] == 'configuring'
    wait(coordinator, 'waiting_workspace')
    bridge(coordinator)
    coordinator.models(coordinator.data['operation_id'], models(True))
    restarted = setup.Coordinator(coordinator.root, start=lambda **kw: starts.append(kw), send=fake.send, port=lambda: False,
                                  analyze=lambda root: dict(passed=True), probe=lambda root: True)
    restarted.log = logs.append
    restarted.step(1, True, 'passed')
    writes = len(fake.writes)
    assert restarted.launch()['phase'] == 'waiting_models'
    assert [action for _, action, _ in fake.writes[writes:]] == ['inspect']  # only checks the shipped plugin
    fake.preview['integrity'] = 'sha256-' + 'e' * 64  # an upgrade ships a different plugin
    again = setup.Coordinator(coordinator.root, start=lambda **kw: starts.append(kw), send=fake.send, port=lambda: False,
                              analyze=lambda root: dict(passed=True), probe=lambda root: True)
    again.log = logs.append
    again.step(1, True, 'passed')
    again.launch()
    wait(again, 'waiting_workspace')
    assert any(row.get('result') == 'resume-failed' for row in logs)


def test_data_home_override_keeps_test_installs_away_from_the_real_folder(monkeypatch, tmp_path):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'real'))
    monkeypatch.delenv('GUANGZHU_DATA_HOME', raising=False)
    assert setup.data_home() == tmp_path / 'real/guangzhu'
    monkeypatch.setenv('GUANGZHU_DATA_HOME', str(tmp_path / 'trial'))
    assert setup.data_home() == tmp_path / 'trial'
    assert setup.Coordinator(tmp_path / 'root').home == tmp_path / 'trial/agh'
