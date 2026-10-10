"""Guangzhu's own AGH instance: start with its own port, own only the verified daemon generation, stop only that."""
import sys
from types import SimpleNamespace
import pytest

from guangzhu import agh_process, config


def process(calls):
    return SimpleNamespace(pid=42, _handle=4242, poll=lambda: None, terminate=lambda: calls.append('terminate'), wait=lambda **kw: calls.append('wait'))


@pytest.mark.parametrize('before_running,parent,start,path,reachable,generation,owned', [
    (False, 42, 101, 'runtime/node.exe', True, 'generation', True),
    (True, 42, 101, 'runtime/node.exe', True, 'generation', False),
    (False, 99, 101, 'runtime/node.exe', True, 'generation', False),
    (False, 42, 99, 'runtime/node.exe', True, 'generation', False),
    (False, 42, 101, 'other.exe', True, 'generation', False),
    (False, 42, 101, 'runtime/node.exe', False, 'generation', False),
    (False, 42, 101, 'runtime/node.exe', True, '', False),
    (False, 42, 101, 'other-runtime/node.exe', True, 'generation', False),
    (False, 42, 101, 'runtime.exe', True, 'generation', False),
])
def test_only_new_verified_child_generation_owned(tmp_path, monkeypatch, before_running, parent, start, path, reachable, generation, owned):
    calls = []
    home = tmp_path / 'existing-home'
    home.mkdir()
    executable = tmp_path / 'runtime.exe'
    servers = agh_process.OwnedAgh()
    monkeypatch.setattr(agh_process.subprocess, 'Popen', lambda args, **kw: calls.append((args,kw)) or process(calls))
    monkeypatch.setattr(agh_process, 'reachable', lambda: True)
    monkeypatch.setattr(agh_process, 'process_identity', lambda pid, retained=None: {'start':100,'parent':0,'path':str(executable)} if pid == 42 else
                        {'start':start,'parent':parent,'path':str(tmp_path / path)})
    owner = {'pid':43,'processStartId':f'win32:43:{start}','generation':generation,'startedAt':'date','socketPath':'pipe'}
    statuses = iter([{'running':before_running}, {'running':True,'socketReachable':reachable,'owner':owner}])
    monkeypatch.setattr(servers, 'daemon', lambda action: next(statuses))
    if reachable:
        servers.start(str(executable), str(home), 'local-dev', str(tmp_path))
    else:
        with pytest.raises(RuntimeError): servers.start(str(executable), str(home), 'local-dev', str(tmp_path))
    assert (servers.owner is not None) is owned
    args, options = calls[0]
    assert args == [str(executable),'serve','--home',str(home),'--profile','local-dev','--cwd',str(tmp_path),
                    '--port',str(config.AGH_PORT)]
    assert options['creationflags'] == agh_process.HIDDEN and options['cwd'] == str(tmp_path)
    assert options['stdout'] == options['stderr'] == agh_process.subprocess.DEVNULL


def test_realistic_bundled_node_daemon_claims_and_stops_only_its_verified_generation(tmp_path, monkeypatch):
    calls = []
    distribution = tmp_path / '中文安装' / 'runtime' / 'agh'
    node = distribution / 'runtime' / 'node.exe'
    node.parent.mkdir(parents=True)
    node.touch()
    executable = distribution / 'agnes-win32-x64.exe'
    executable.touch()
    home = tmp_path / 'own-home'
    home.mkdir()
    servers = agh_process.OwnedAgh()
    monkeypatch.setattr(agh_process.subprocess, 'Popen', lambda args, **kw: calls.append(('serve', args)) or process(calls))
    monkeypatch.setattr(agh_process, 'reachable', lambda: True)
    def identity(pid, retained=None):
        assert retained == (4242 if pid == 42 else None)
        return dict(start=100 if pid == 42 else 101, parent=0 if pid == 42 else 42,
                    path=str(executable if pid == 42 else node))
    monkeypatch.setattr(agh_process, 'process_identity', identity)
    owner = dict(pid=43, processStartId='win32:43:101', generation='new-generation', startedAt='date', socketPath='pipe')
    statuses = iter([dict(running=False), dict(running=True, socketReachable=True, owner=owner),
                     dict(running=True, socketReachable=True, owner=owner), dict(running=False)])
    def daemon(action):
        calls.append(action)
        return 'stopped' if action == 'stop' else next(statuses)
    monkeypatch.setattr(servers, 'daemon', daemon)
    servers.start(str(executable), str(home), 'local-dev', str(tmp_path))
    assert servers.owner == dict(pid=43, processStartId='win32:43:101', generation='new-generation')
    servers.close()
    assert calls.count('stop') == 1
    assert calls[-2:] == ['terminate', 'wait']


def test_own_launch_removes_inherited_node_override_without_changing_parent_environment(tmp_path, monkeypatch):
    calls = []
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setenv('AGNES_NODE_EXEC_PATH', 'external-node.exe')
    monkeypatch.setattr(agh_process.subprocess, 'Popen', lambda args, **kw: calls.append(kw) or process([]))
    monkeypatch.setattr(agh_process, 'reachable', lambda: True)
    monkeypatch.setattr(agh_process, 'process_identity', lambda pid, retained=None: dict(start=100, parent=0, path='wrapper.exe'))
    servers = agh_process.OwnedAgh()
    statuses = iter([dict(running=False), dict(running=True, socketReachable=False)])
    monkeypatch.setattr(servers, 'daemon', lambda action: next(statuses))
    with pytest.raises(RuntimeError):
        servers.start(str(tmp_path / 'agnes-win32-x64.exe'), str(home), 'local-dev', str(tmp_path))
    assert 'AGNES_NODE_EXEC_PATH' not in calls[0]['env']
    assert agh_process.os.environ['AGNES_NODE_EXEC_PATH'] == 'external-node.exe'
    assert calls[0]['env']['AGH_HOME'] == str(home)
    assert calls[0]['env']['AGNES_WEB_ORIGIN'] == config.AGH_ORIGIN


@pytest.mark.parametrize('before_running', [False, True])
def test_a_start_given_up_stops_only_the_daemon_it_created(tmp_path, monkeypatch, before_running):
    # A slow first start (antivirus scanning the new runtime) used to leave the daemon running and install files locked.
    calls, clock = [], iter([0] + [1000] * 5)
    home = tmp_path / 'home'
    home.mkdir()
    servers = agh_process.OwnedAgh()
    monkeypatch.setattr(agh_process.subprocess, 'Popen', lambda args, **kw: process(calls))
    monkeypatch.setattr(agh_process, 'reachable', lambda: False)
    monkeypatch.setattr(agh_process.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(agh_process, 'process_identity', lambda pid, retained=None: dict(start=100, parent=0, path='wrapper.exe'))
    statuses = iter([dict(running=before_running), dict(running=True, socketReachable=False)])
    def daemon(action):
        calls.append(action)
        return 'stopped' if action == 'stop' else next(statuses)
    monkeypatch.setattr(servers, 'daemon', daemon)
    with pytest.raises(RuntimeError, match='未能启动'):
        servers.start(str(tmp_path / 'agnes-win32-x64.exe'), str(home), 'local-dev', str(tmp_path))
    assert calls == (['status', 'status'] if before_running else ['status', 'status', 'terminate', 'stop'])


@pytest.mark.parametrize('status,stop', [({'running':False},False), ({'running':True,'owner':{'pid':43}},False),
    ({'running':True,'owner':{'pid':43,'processStartId':'win32:43:101','generation':'other'}},False),
    ({'running':True,'owner':{'pid':43,'processStartId':'win32:43:101','generation':'same'}},True)])
def test_shutdown_only_matching_owned_generation_and_retained_helper(monkeypatch, status, stop):
    calls = []
    servers = agh_process.OwnedAgh()
    servers.process = process(calls)
    servers.owner = {'pid':43,'processStartId':'win32:43:101','generation':'same'}
    statuses = iter([status, {'running':False}])
    def daemon(action):
        calls.append(action)
        return 'stopped' if action == 'stop' else next(statuses)
    monkeypatch.setattr(servers, 'daemon', daemon)
    servers.close()
    assert ('stop' in calls) is stop
    assert calls[-2:] == ['terminate','wait']
    assert servers.closed
    with pytest.raises(RuntimeError, match='已关闭'): servers.start('ignored','ignored','local-dev','ignored')


def test_external_daemon_is_never_stopped(monkeypatch):
    calls = []
    servers = agh_process.OwnedAgh()
    servers.process = process(calls)
    monkeypatch.setattr(servers, 'daemon', lambda *a: pytest.fail('external daemon must not be inspected or stopped'))
    servers.close()
    assert calls == ['terminate', 'wait']
    servers = agh_process.OwnedAgh()
    servers.close()
    assert servers.owner is servers.process is None


@pytest.mark.parametrize('code,stdout,valid', [(1,'{"running":false}',True),(0,'{"running":true}',True),
    (0,'{"running":false}',False),(1,'bad',False),(0,'{}',False)])
def test_official_status_requires_matching_json_and_exit(monkeypatch, code, stdout, valid):
    servers = agh_process.OwnedAgh()
    servers.command, servers.scope = ['bundled.exe','daemon'], ['--home','isolated','--profile','local-dev','--workspace','root']
    monkeypatch.setattr(agh_process.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=code,stdout=stdout))
    if valid: assert type(servers.daemon('status')['running']) is bool
    else:
        with pytest.raises((RuntimeError, ValueError)): servers.daemon('status')


@pytest.mark.parametrize('stdout,code,valid', [('stopped\n',0,True),('not-running\n',0,True),('timeout\n',1,False),
                                           ('{"status":"stopped"}',0,False)])
def test_official_stop_uses_actual_plain_text_contract(monkeypatch, stdout, code, valid):
    servers = agh_process.OwnedAgh()
    servers.command, servers.scope = ['bundled.exe','daemon'], []
    monkeypatch.setattr(agh_process.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=code,stdout=stdout))
    if valid: assert servers.daemon('stop') == stdout.strip()
    else:
        with pytest.raises(RuntimeError): servers.daemon('stop')


def test_new_own_home_protection_only_after_callback(tmp_path, monkeypatch):
    calls = []
    home = tmp_path / 'fresh-home'
    servers = agh_process.OwnedAgh()
    assert not home.exists()
    def run(args, **kw):
        calls.append(args)
        assert kw['creationflags'] == agh_process.HIDDEN
        return SimpleNamespace(stdout='"user","S-1-5-21-123"\n')
    monkeypatch.setattr(agh_process.subprocess, 'run', run)
    monkeypatch.setattr(servers, 'daemon', lambda action: (_ for _ in ()).throw(RuntimeError('fake status failure')))
    with pytest.raises(RuntimeError): servers.start('fake.exe',str(home),'local-dev',str(tmp_path))
    assert calls[0][0] == 'whoami' and calls[1][0] == 'icacls'
    calls.clear()
    with pytest.raises(RuntimeError): servers.start('fake.exe',str(home),'local-dev',str(tmp_path))
    assert calls == []


@pytest.mark.skipif(sys.platform != 'win32', reason='Real Windows directory ACL boundary')
@pytest.mark.parametrize('default_encoding', ['utf-8', 'cp936'])
def test_new_own_home_real_acl_is_private_before_any_agh_start(tmp_path, monkeypatch, default_encoding):
    import win32security
    home = tmp_path / '新建隔离目录'
    servers = agh_process.OwnedAgh()
    monkeypatch.setattr(agh_process.subprocess, '_text_encoding', lambda: default_encoding)
    monkeypatch.setattr(servers, 'daemon', lambda action: (_ for _ in ()).throw(RuntimeError('stop before AGH')))
    with pytest.raises(RuntimeError, match='stop before AGH'):
        servers.start('never-run.exe', str(home), 'local-dev', str(tmp_path))
    descriptor = win32security.GetFileSecurity(str(home), win32security.OWNER_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION)
    assert descriptor.GetSecurityDescriptorControl()[0] & win32security.SE_DACL_PROTECTED
    acl = descriptor.GetSecurityDescriptorDacl()
    assert acl.GetAceCount() == 1
    kind, rights, sid = acl.GetAce(0)
    assert kind == (win32security.ACCESS_ALLOWED_ACE_TYPE, 3)
    assert rights == 0x1F01FF
    assert sid == descriptor.GetSecurityDescriptorOwner()
    sentinel = home / '可写.txt'
    sentinel.write_text('正常访问', encoding='utf-8')
    assert sentinel.read_text(encoding='utf-8') == '正常访问'


@pytest.mark.parametrize('retained', [None, 4242])
def test_win32_identity_reads_filetime_parent_and_image_from_retained_handle(monkeypatch, retained):
    calls = []
    def open_process(access, inherit, pid):
        calls.append(('open',pid))
        return 4343
    def times(handle, creation, exit_time, kernel_time, user_time):
        creation._obj.dwHighDateTime, creation._obj.dwLowDateTime = 1, 2
        return 1
    def query(handle, kind, info, size, required):
        info._obj.parent = 42
        return 0
    def image(handle, flags, path, size):
        path.value = 'C:\\bundled\\agnes-win32-x64.exe'
        return 1
    kernel = SimpleNamespace(OpenProcess=open_process,CloseHandle=lambda handle: calls.append(('close',handle)),
                             GetProcessTimes=times,QueryFullProcessImageNameW=image)
    ntdll = SimpleNamespace(NtQueryInformationProcess=query)
    monkeypatch.setattr(agh_process.ctypes, 'WinDLL', lambda name, **kw: kernel if name == 'kernel32' else ntdll)
    result = agh_process.process_identity(43, retained)
    assert result == {'start':4294967298,'parent':42,'path':'C:\\bundled\\agnes-win32-x64.exe'}
    assert calls == ([] if retained else [('open',43),('close',4343)])


def test_exited_original_serve_cannot_claim_a_reused_parent_pid(tmp_path, monkeypatch):
    calls = []
    home = tmp_path / 'home'
    home.mkdir()
    servers = agh_process.OwnedAgh()
    helper = process(calls)
    helper.poll = lambda: 1
    monkeypatch.setattr(agh_process.subprocess, 'Popen', lambda *a, **kw: helper)
    monkeypatch.setattr(agh_process, 'reachable', lambda: True)
    def identity(pid, retained=None):
        assert retained == (4242 if pid == 42 else None)
        return {'start':100 if pid == 42 else 101,'parent':42,'path':str(tmp_path / 'runtime.exe')}
    monkeypatch.setattr(agh_process, 'process_identity', identity)
    statuses = iter([{'running':False},{'running':True,'socketReachable':True,
        'owner':{'pid':43,'processStartId':'win32:43:101','generation':'same','startedAt':'date','socketPath':'pipe'}}])
    monkeypatch.setattr(servers, 'daemon', lambda action: next(statuses))
    with pytest.raises(RuntimeError): servers.start(str(tmp_path / 'runtime.exe'),str(home),'local-dev',str(tmp_path))
    assert servers.owner is None
    servers.close()
    assert calls == []
