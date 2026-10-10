"""Exercise the real launcher with isolated process, registry and transport fakes."""
import builtins
import ctypes
import importlib.util
import io
import json
import runpy
from pathlib import Path
import socket
import sys
import threading
import urllib.request
from types import SimpleNamespace
import pytest

from guangzhu import agh_process

SPEC = importlib.util.spec_from_file_location('desktop_launcher', Path(__file__).resolve().parents[1] / 'desktop/app.py')
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)
launcher.load_backend()


def fake_server(monkeypatch, calls):
    class Server:
        started = False
        should_exit = False
        def __init__(self, config):
            self.config = config
            calls.append(('server', config['port']))
        def run(self):
            self.started = True
    class Thread:
        def __init__(self, target, daemon):
            self.target = target
        def start(self):
            self.target()
        def join(self, timeout):
            calls.append('join')
        def is_alive(self):
            return True
    monkeypatch.setitem(sys.modules, 'uvicorn', SimpleNamespace(Server=Server, Config=lambda app, **kw: kw))
    monkeypatch.setattr(launcher.threading, 'Thread', Thread)


def test_same_installed_backend_reuses_without_mutation(monkeypatch):
    monkeypatch.setattr(launcher, 'backend_ready', lambda: True)
    monkeypatch.setattr(agh_process.subprocess, 'Popen', lambda *a, **kw: pytest.fail('must reuse'))
    monkeypatch.setattr(launcher, 'setup_coordinator', lambda: pytest.fail('must not configure another backend'))
    servers = launcher.OwnedServers()
    servers.start()
    servers.close()
    assert servers.server is None and servers.agh.process is None and servers.agh.owner is None


@pytest.mark.parametrize('completed', [False, True])
def test_installed_start_binds_callback_then_finishes_setup_in_the_background(monkeypatch, completed):
    calls = []
    fake_server(monkeypatch, calls)
    readiness = iter([False, True])
    monkeypatch.setattr(launcher, 'backend_ready', lambda: next(readiness))
    monkeypatch.setattr(launcher, 'INSTALLED', True)
    monkeypatch.setattr(launcher, 'API_PORT', 8766)
    def coordinator():
        assert launcher.app.state.start_agh.__self__ is servers.agh
        return SimpleNamespace(step=lambda *args: calls.append(('step', args)), launch=lambda: calls.append('launch'),
                               restart_binding=lambda: {'completed': True} if completed else None)
    monkeypatch.setattr(launcher, 'setup_coordinator', coordinator)
    monkeypatch.setattr(agh_process.subprocess, 'Popen', lambda *a, **kw: pytest.fail('the launcher itself must not start AGH'))
    servers = launcher.OwnedServers()
    servers.start()
    servers.close()
    assert calls[0][0] == 'step' and calls[0][1][0:2] == (1, True)
    assert ('server', 8766) in calls
    assert calls.count('launch') == 1 and calls.index('launch') > calls.index(('server', 8766))


@pytest.mark.parametrize('body', ['{}', '{"app":"other"}', '{"app":"guangzhu"}', 'bad'])
def test_wrong_backend_on_our_port_is_reported_plainly(monkeypatch, body):
    monkeypatch.setattr(launcher, 'urlopen', lambda *a, **kw: io.StringIO(body))
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def settimeout(self, value): pass
        def connect_ex(self, address): return 0
    monkeypatch.setattr(launcher.socket, 'socket', Socket)
    with pytest.raises(RuntimeError, match='被别的程序占用'):
        launcher.backend_ready()


def test_exact_installation_required_on_our_port(monkeypatch):
    identity = launcher.installation(launcher.ROOT)
    monkeypatch.setattr(launcher, 'urlopen', lambda *a, **kw: io.StringIO(json.dumps({'app':'guangzhu','installation':identity})))
    assert launcher.backend_ready() is True
    for key in ['id', 'root', 'build', 'installed']:
        wrong = {**identity, key: 'different'}
        monkeypatch.setattr(launcher, 'urlopen', lambda *a, **kw: io.StringIO(json.dumps({'app':'guangzhu','installation':wrong})))
        with pytest.raises(RuntimeError): launcher.backend_ready()


def test_absent_backend_is_distinct_from_invalid_service(monkeypatch):
    monkeypatch.setattr(launcher, 'urlopen', lambda *a, **kw: (_ for _ in ()).throw(OSError()))
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def settimeout(self, value): pass
        def connect_ex(self, address): return 1
    monkeypatch.setattr(launcher.socket, 'socket', Socket)
    assert launcher.backend_ready() is False


def test_installed_and_development_use_separate_ports():
    from guangzhu import config
    assert (config.API_PORT, config.AGH_PORT) == ((8766, 4178) if config.INSTALLED else (8765, 4177))
    assert config.API_ORIGIN == f'http://127.0.0.1:{config.API_PORT}' and config.AGH_ORIGIN == f'http://127.0.0.1:{config.AGH_PORT}'


@pytest.mark.parametrize('failure', ['platform', 'webview', 'runtime', 'second-copy'])
def test_native_failure_is_visible_and_the_window_opens_before_the_backend(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(launcher, 'load_backend', lambda: None)
    calls = []
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setattr(launcher, 'data_home', lambda: tmp_path / 'guangzhu')
    monkeypatch.setattr(launcher, 'OwnedServers', lambda: SimpleNamespace(start=lambda: calls.append('start'), close=lambda: calls.append('close')))
    monkeypatch.setattr(launcher, 'platform_check', lambda: (_ for _ in ()).throw(RuntimeError('需要 WebView2')) if failure == 'platform' else None)
    monkeypatch.setattr(launcher, 'single_instance', lambda: failure != 'second-copy')
    monkeypatch.setattr(launcher, 'register_app', lambda: calls.append('register'))
    monkeypatch.setattr(launcher, 'INSTALLED', failure == 'runtime')
    monkeypatch.setattr(launcher, 'native_error', lambda text: calls.append(text))
    window = SimpleNamespace(load_url=lambda url: calls.append('load'), load_html=lambda html: calls.append('error-page'),
                             events=SimpleNamespace(loaded=SimpleNamespace(wait=lambda timeout: True)))
    def start(func=None, **kw):
        calls.append('gui')
        assert kw['icon'].endswith('guangzhu.ico') and kw['private_mode'] is False
        if failure == 'webview':
            raise ValueError('private unsafe detail')
        func()
    monkeypatch.setitem(sys.modules, 'webview', SimpleNamespace(create_window=lambda *a, **kw: calls.append(('window', a[0])) or window,
                                                                start=start))
    launcher.main()
    assert 'private unsafe detail' not in ' '.join(map(str, calls))
    if failure == 'second-copy':
        assert calls == []
    elif failure in {'platform', 'runtime'}:
        assert not any(isinstance(row, tuple) for row in calls) and 'gui' not in calls
        assert any('WebView2' in str(text) or '重新安装' in str(text) for text in calls)
    elif failure == 'webview':
        assert calls[:3] == ['register', ('window', '光筑'), 'gui'] and calls[-1] == 'close'
        assert any('WebView2' in str(text) for text in calls)


def test_backend_failure_after_the_window_opens_shows_a_readable_page(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(launcher, 'load_backend', lambda: None)
    monkeypatch.setattr(launcher, 'platform_check', lambda: None)
    monkeypatch.setattr(launcher, 'single_instance', lambda: True)
    monkeypatch.setattr(launcher, 'register_app', lambda: None)
    monkeypatch.setattr(launcher, 'INSTALLED', False)
    monkeypatch.setattr(launcher, 'data_home', lambda: tmp_path / 'guangzhu')
    monkeypatch.setattr(launcher, 'native_error', lambda text: calls.append(('native', text)))
    def failing():
        raise RuntimeError('端口 8766 被别的程序占用。请关闭它后重新打开光筑。')
    monkeypatch.setattr(launcher, 'OwnedServers', lambda: SimpleNamespace(start=failing, close=lambda: calls.append('close')))
    # the error waits for the starting page to finish loading, or that page would cover it
    window = SimpleNamespace(load_url=lambda url: calls.append('load'), load_html=lambda html: calls.append(('page', html)),
                             events=SimpleNamespace(loaded=SimpleNamespace(wait=lambda timeout: calls.append(('loaded', timeout)) or True)))
    monkeypatch.setitem(sys.modules, 'webview', SimpleNamespace(create_window=lambda *a, **kw: window, start=lambda func, **kw: func()))
    launcher.main()
    page = next(row[1] for row in calls if isinstance(row, tuple) and row[0] == 'page')
    assert calls.index(('loaded', 10)) < next(i for i, row in enumerate(calls) if isinstance(row, tuple) and row[0] == 'page')
    assert '被别的程序占用' in page and 'load' not in calls and calls[-1] == 'close'
    assert not any(isinstance(row, tuple) and row[0] == 'native' for row in calls)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows registry adapter')
def test_platform_registry_probe_uses_vendor_runtime_identity_before_webview_import(monkeypatch):
    import winreg
    calls = []
    runtime_guid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    vendor_probe = Path(launcher.sys.prefix) / 'Lib/site-packages/webview/platforms/winforms.py'
    assert runtime_guid in vendor_probe.read_text(encoding='utf-8')
    class Key:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def open_key(hive, path, reserved, flags):
        calls.append((hive, path, flags))
        assert path.endswith(runtime_guid)
        return Key()
    monkeypatch.setattr(winreg, 'OpenKey', open_key)
    monkeypatch.setattr(winreg, 'QueryValueEx', lambda key, name: ('154.0.4258.53', 1))
    monkeypatch.setitem(sys.modules, 'webview', None)
    launcher.platform_check()
    assert len(calls) == 1


def entry_fakes(tmp_path, monkeypatch, failing_module=None, failure=ImportError, second=False):
    calls = []
    dialogs = []
    identity = {'installed': False, 'id': 'isolated-entry'}
    def message_box(owner, message, title, flags):
        dialogs.append((owner, message, title, flags))
    kernel = SimpleNamespace(CreateMutexW=lambda *args: 7, GetLastError=lambda: 183 if second else 0)
    user = SimpleNamespace(MessageBoxW=message_box, FindWindowW=lambda *args: calls.append('find') or 0)
    shell = SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=lambda value: calls.append(('appid', value)))
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=user, kernel32=kernel, shell32=shell))
    monkeypatch.setattr(sys, 'path', sys.path.copy())
    monkeypatch.setattr(sys, 'getwindowsversion', lambda: SimpleNamespace(major=10))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(agh_process.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('must not launch AGH'))
    class Key:
        def __enter__(self):
            calls.append('platform')
            return self
        def __exit__(self, *args):
            pass
    registry = SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2, KEY_WOW64_32KEY=4,
                               KEY_WOW64_64KEY=8, KEY_READ=16, OpenKey=lambda *args: Key(),
                               QueryValueEx=lambda *args: ('1.0.0.0', 1))
    monkeypatch.setitem(sys.modules, 'winreg', registry)
    class Socket:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def settimeout(self, timeout):
            pass
        def connect_ex(self, address):
            return 1
    monkeypatch.setattr(socket, 'socket', Socket)
    def status(*args, **kwargs):
        calls.append('status')
        if calls.count('status') == 1:
            raise OSError('isolated backend absent')
        return io.StringIO(json.dumps({'app': 'guangzhu', 'installation': identity}))
    monkeypatch.setattr(urllib.request, 'urlopen', status)
    class Server:
        started = False
        should_exit = False
        def __init__(self, config):
            calls.append('server')
        def run(self):
            calls.append('serve')
            self.started = True
    class Thread:
        def __init__(self, target, daemon):
            self.target = target
        def start(self):
            self.target()
        def is_alive(self):
            return True
        def join(self, timeout):
            calls.append('close')
    monkeypatch.setattr(threading, 'Thread', Thread)
    owned = SimpleNamespace(start=lambda *a, **kw: pytest.fail('development must not start AGH here'), close=lambda: calls.append('agh-close'))
    window = SimpleNamespace(load_url=lambda url: calls.append(('load', url)), load_html=lambda html: calls.append('error-page'),
                             events=SimpleNamespace(loaded=SimpleNamespace(wait=lambda timeout: True)))
    modules = {
        'guangzhu.config': SimpleNamespace(API_ORIGIN='http://127.0.0.1:8765', API_PORT=8765, INSTALLED=False),
        'guangzhu.api': SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()),
                                        settings=lambda: {'agh_runtime': str(tmp_path / 'missing-runtime.exe'), 'agh_home': 'unused'},
                                        setup_coordinator=lambda: pytest.fail('development must not configure installed instance')),
        'guangzhu.setup': SimpleNamespace(installation=lambda root: identity, data_home=lambda: tmp_path / 'guangzhu'),
        'guangzhu.agh_process': SimpleNamespace(OwnedAgh=lambda: owned, reachable=lambda: False),
        'uvicorn': SimpleNamespace(Server=Server, Config=lambda app, **kwargs: kwargs),
        'webview': SimpleNamespace(create_window=lambda *args, **kwargs: calls.append('window') or window,
                                   start=lambda func, **kwargs: calls.append('webview-start') or func()),
    }
    original_import = builtins.__import__
    def import_boundary(name, *args, **kwargs):
        if name in modules:
            calls.append(name)
            if name == failing_module:
                raise failure('private unsafe dependency detail')
            return modules[name]
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', import_boundary)
    return calls, dialogs


@pytest.mark.parametrize('module', ['guangzhu.config', 'guangzhu.api', 'guangzhu.setup', 'guangzhu.agh_process'])
@pytest.mark.parametrize('failure', [ImportError, OSError, RuntimeError])
def test_actual_entry_dependency_failure_shows_one_safe_native_message(tmp_path, monkeypatch, module, failure):
    calls, dialogs = entry_fakes(tmp_path, monkeypatch, module, failure)
    escaped = None
    try:
        runpy.run_path(str(SPEC.origin), run_name='__main__')
    except Exception as error:
        escaped = error
    assert escaped is None, f'{type(escaped).__name__} escaped the actual entry'
    assert len(dialogs) == 1
    owner, message, title, flags = dialogs[0]
    assert owner is None and title == '光筑' and flags == 0x10
    assert '重新安装' in message and '光筑' in message
    assert 'private unsafe dependency detail' not in message
    assert all(name not in calls for name in ('uvicorn', 'webview', 'server', 'serve', 'window', 'webview-start'))


def test_actual_entry_healthy_bootstrap_opens_the_window_first_then_the_backend(tmp_path, monkeypatch):
    calls, dialogs = entry_fakes(tmp_path, monkeypatch)
    runpy.run_path(str(SPEC.origin), run_name='__main__')
    assert dialogs == []
    assert calls == ['platform', ('appid', 'Guangzhu.Desktop'), 'guangzhu.config', 'guangzhu.api', 'guangzhu.setup',
                     'guangzhu.agh_process', 'webview', 'window', 'webview-start', 'status', 'uvicorn', 'server', 'serve', 'status',
                     ('load', 'http://127.0.0.1:8765'), 'close', 'agh-close']
    assert (tmp_path / 'guangzhu/webview').is_dir()


def test_second_copy_only_raises_the_open_window(tmp_path, monkeypatch):
    calls, dialogs = entry_fakes(tmp_path, monkeypatch, second=True)
    runpy.run_path(str(SPEC.origin), run_name='__main__')
    assert dialogs == [] and calls == ['platform', 'find']
