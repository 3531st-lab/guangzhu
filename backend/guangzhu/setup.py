"""Guangzhu's own AGH instance: the installer configures it, every launch finishes and re-verifies it.

There is no first-run wizard and nothing to choose. Installing is the consent: the instance has its own
home (%LOCALAPPDATA%\\guangzhu\\agh) and its own port, so no other AGH on the computer is touched.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import uuid
from .config import AGH_PORT
from .setup_agh import Management, TOOLS, regular


def installation(root):
    root = Path(root).resolve()
    manifest = root / 'build-manifest.json'
    build = hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else 'development'
    return dict(root=str(root), installed=manifest.is_file(), build=build,
                id=hashlib.sha256((str(root) + '\n' + build).encode()).hexdigest())


def data_home():
    """光筑自己的数据目录。GUANGZHU_DATA_HOME 只给测试用，让试装不碰正式数据。"""
    override = os.environ.get('GUANGZHU_DATA_HOME')
    return Path(override) if override else Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'guangzhu'


def occupied():
    with socket.socket() as connection:
        connection.settimeout(.2)
        return connection.connect_ex(('127.0.0.1', AGH_PORT)) == 0


def runtime(root):
    result = subprocess.run([str(root / 'runtime/agh/agnes-win32-x64.exe'), '--version'], cwd=root,
        capture_output=True, text=True, encoding='utf-8', timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return result.returncode == 0 and result.stdout.startswith('agh ') and 'protocol _agnes/v1' in result.stdout


def offline(root):
    code = '''import json
from guangzhu.selfcheck import offline_analysis
print(json.dumps(offline_analysis(), ensure_ascii=True))'''
    result = subprocess.run([str(root / 'runtime/python/python.exe'), '-X', 'utf8', '-B', '-c', code], cwd=root,
        capture_output=True, text=True, encoding='utf-8', timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('内置 Python 或发电计算组件无法运行，请重新安装光筑')
    return json.loads(result.stdout)


class Coordinator:
    def __init__(self, root, start=None, send=None, analyze=offline, port=occupied, probe=runtime):
        self.root, self.start, self.send, self.analyze, self.port = Path(root).resolve(), start, send, analyze, port
        self.installation = installation(root)
        self.probe = probe
        self.home = data_home() / 'agh'
        self.cache = self.root / 'desktop/settings.json'
        self.lock = threading.RLock()
        self.data = dict(operation_id=None, busy=False, ready=False, phase='unconfigured', target=None, workspace_id=None,
                         installation=self.installation, steps=[dict(number=i, state='waiting', reason='尚未检查', action='')
                                                              for i in range(1, 8)])
        reasons = ['等待检查 Windows 和 WebView2', '尚未检查自带 AGH', '尚未启动自带 AGH', '尚未检查12个设计工具',
                   '尚未检查插件、工作区和 Skill', '还没有可用的模型 key', '尚未运行离线计算自检']
        for row, reason in zip(self.data['steps'], reasons):
            row['reason'] = reason
        self.binding = {}
        try:
            binding = json.loads(self.cache.read_text(encoding='utf-8-sig'))
            fields = dict(installation_id=str, choice=str, agh_home=str, profile=str, workspace_id=str,
                          offline_passed=bool, integrity=str, completed=bool)
            if not isinstance(binding, dict) or set(binding) != set(fields) or any(type(binding[key]) is not kind for key, kind in fields.items()):
                raise ValueError('binding schema')
            if any(not value or len(value) > 1024 or '\x00' in value for value in binding.values() if isinstance(value, str)):
                raise ValueError('binding fields')
            if (binding['installation_id'] != self.installation['id'] or binding['choice'] != 'own'
                or binding['profile'] != 'local-dev' or binding['agh_home'] != str(self.home)
                or binding['workspace_id'] != hashlib.sha256(str(self.root).encode()).hexdigest()
                or not re.fullmatch('sha256-[a-f0-9]{64}', binding['integrity'])
                or binding['completed'] and not binding['offline_passed']):
                raise ValueError('binding association')
            self.binding = binding
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError, ValueError):
            self.log(dict(result='binding-reset', reason='保存的配置无法读取或安装已变化，重新配置'))
        self.client = None

    def log(self, row):
        folder = self.home.parent / 'setup'
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / 'actions.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')

    def step(self, number, ready, reason, action=''):
        with self.lock:
            self.data['steps'][number - 1].update(state='ready' if ready else 'waiting', reason=reason, action='' if ready else action)
            self.data['ready'] = all(row['state'] == 'ready' for row in self.data['steps'])

    def public(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def status(self):
        if not self.installation['installed']:
            self.data.update(ready=True, required=False)
        elif self.data['steps'][1]['state'] == 'waiting':
            self.check_runtime()
        return self.public()

    def check_runtime(self):
        try:
            ready = bool(self.probe(self.root))
        except (OSError, subprocess.SubprocessError):
            ready = False
        self.step(2, ready, '自带 AGH 可以运行' if ready else '自带 AGH 无法运行，请重新安装光筑')
        if not ready:
            self.data['steps'][1]['state'] = 'failed'
        return ready

    def restart_binding(self):
        return copy.deepcopy(self.binding) if (self.binding.get('completed') is True and self.binding.get('choice') == 'own'
            and self.binding.get('agh_home') == str(self.home) and self.binding.get('profile') == 'local-dev'
            and self.binding.get('workspace_id') == hashlib.sha256(str(self.root).encode()).hexdigest()) else None

    def prepare(self):
        selected = self.home
        self.data['target'] = dict(choice='own', home=str(selected), profile='local-dev')
        if not self.port():
            if self.start is None:
                raise ValueError('启动器没有提供启动 AGH 的方法，请重新打开光筑')
            if selected.exists():
                regular(selected)
            self.start(executable=str(self.root / 'runtime/agh/agnes-win32-x64.exe'), home=str(selected),
                       profile='local-dev', cwd=str(self.root))
        self.client = Management(selected, self.log, **({'send': self.send} if self.send else {}))
        try:
            self.client.identity()
        except ValueError:
            raise ValueError(f'端口 {AGH_PORT} 被别的程序占用，请关闭它后重新打开光筑') from None
        if not selected.is_dir() or not os.access(selected, os.W_OK):
            raise ValueError('光筑数据目录不可写，请检查磁盘权限')
        self.step(3, True, '自带 AGH 已启动')
        releases = list((self.root / 'plugins').iterdir())
        if len(releases) != 1:
            raise ValueError('安装文件里的插件缺失，请重新安装光筑')
        self.release = regular(releases[0])
        self.package = json.loads((self.release / 'package.json').read_text(encoding='utf-8'))
        if self.package['name'] != 'guangzhu-studio':
            raise ValueError('安装文件里的插件不正确，请重新安装光筑')
        self.definition = dict(serverId='guangzhu', displayName='光筑', secretBinding=dict(kind='none'), toolPolicy=dict(allow=TOOLS),
            transport=dict(kind='stdio', executable=str(self.root / 'runtime/python/python.exe'), args=['-m', 'guangzhu.mcp_server']))

    def fail(self, error):
        known = isinstance(error, (ValueError, RuntimeError)) and not isinstance(error, json.JSONDecodeError)
        reason = str(error) if known else '配置失败（' + type(error).__name__ + '），可点重试或重新安装光筑'
        self.log(dict(result='failed', reason=reason))
        with self.lock:
            self.data.update(busy=False, ready=False, phase='failed', error=reason)
            row = self.data['steps'][getattr(self, 'checking', 1) - 1]
            row.update(state='failed', reason=reason, action='重试')

    def begin(self):
        with self.lock:
            if self.data['busy'] or self.data['phase'] == 'waiting_workspace':
                return self.public()
            self.data.pop('error', None)
            self.data.update(operation_id=uuid.uuid4().hex, busy=True, ready=False, phase='configuring', workspace_id=None)
            for number in (3, 4, 5, 6, 7):
                self.step(number, False, '正在准备')
            threading.Thread(target=self.configure, daemon=True).start()
            return self.public()

    def launch(self):
        """Called by the app at every start: re-verify a finished setup, otherwise finish it. Never asks the user."""
        return self.resume() if self.restart_binding() else self.begin()

    def configure(self):
        try:
            if self.data['steps'][0]['state'] != 'ready':
                raise ValueError('Windows 或 WebView2 还没有通过检查')
            self.checking = 2
            if not self.check_runtime():
                raise ValueError('自带 AGH 无法运行，请重新安装光筑')
            self.checking = 3
            self.prepare()
            self.checking = 7
            result = self.analyze(self.root)
            self.step(7, result.get('passed') is True, '离线发电计算自检通过' if result.get('passed') else '离线计算自检没有通过')
            if result.get('passed') is not True:
                raise ValueError('离线计算自检没有通过：' + '; '.join(result.get('failures', [])))
            self.checking = 4
            self.client.mcp(self.definition, configure=True)
            self.step(4, True, '光筑12个设计工具已就绪')
            self.checking = 5
            self.integrity = self.client.plugin(self.package, dict(type='file', ref='file:./plugins/' + self.release.name))
            self.client.identity()
            self.data.update(busy=False, phase='waiting_workspace')
        except Exception as error:
            self.fail(error)

    def complete(self, operation_id, workspace):
        with self.lock:
            if operation_id != self.data['operation_id'] or self.data['phase'] != 'waiting_workspace' or self.data['busy']:
                raise ValueError('配置编号已失效或工作区已提交，请重新读取配置状态')
            expected = hashlib.sha256(str(self.root).encode()).hexdigest()
            if workspace != dict(path=str(self.root), workspaceId=expected, available=True):
                raise ValueError('插件登记的工作区与安装目录不一致')
            self.data.update(busy=True, phase='configuring_skill')
            threading.Thread(target=self.finish_workspace, args=(expected,), daemon=True).start()
            return self.public()

    def finish_workspace(self, workspace):
        try:
            self.checking = 5
            self.client.identity()
            self.client.skill(workspace, configure=True)
            self.client.identity()
            with self.lock:
                self.data.update(workspace_id=workspace, busy=False, phase='waiting_models')
                self.step(5, True, '插件、工作区和设计 Skill 已就绪')
                self.save(True)  # tools, plugin, workspace and Skill are done; keys are checked on every start
        except Exception as error:
            self.fail(error)

    def save(self, completed):
        self.binding = dict(installation_id=self.installation['id'], choice='own',
            agh_home=self.data['target']['home'], profile='local-dev', workspace_id=self.data['workspace_id'],
            offline_passed=self.data['steps'][6]['state'] == 'ready', integrity=self.integrity, completed=completed)
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.binding, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.cache)

    def models(self, operation_id, metadata):
        with self.lock:
            if operation_id != self.data['operation_id'] or self.data['phase'] not in {'waiting_models', 'ready'}:
                raise ValueError('模型检查不属于当前配置')
            if (set(metadata) != {'profile', 'designConfigured', 'reviewConfigured', 'design', 'review', 'models'}
                    or not isinstance(metadata['models'], list) or len(metadata['models']) > 1024):
                raise ValueError('模型桥只接受公开配置摘要')
            for row in [metadata['design'], metadata['review'], *metadata['models']]:
                if row is not None and (not isinstance(row, dict) or not {'id', 'route'} <= set(row) <= {'id', 'route', 'name'}
                    or any(not isinstance(value, str) or not value or len(value) > 256 for value in row.values())):
                    raise ValueError('模型桥字段不合法')
            if any(row is None for row in metadata['models']):
                raise ValueError('公开模型列表不能包含空项')
            self.client.identity()
            ready = metadata.get('profile') == 'local-dev'
            for kind in ('design', 'review'):
                selected = metadata.get(kind)
                ready = ready and metadata.get(kind + 'Configured') is True and selected is not None and any(
                    all(row[key] == selected[key] for key in ('id', 'route')) for row in metadata['models'])
            self.step(6, bool(ready), '模型 key 可用' if ready else '在首页上方填好 key 就能开始设计')
            self.data['phase'] = 'ready' if self.data['ready'] else 'waiting_models'
            self.save(True)
            return self.public()

    def resume(self):
        binding = self.restart_binding()
        if not binding or not binding.get('offline_passed') or self.data['steps'][0]['state'] != 'ready':
            return self.status()
        try:
            self.checking = 2
            if not self.check_runtime():
                raise ValueError('自带 AGH 无法运行，请重新安装光筑')
            self.checking = 3
            self.prepare()
            self.checking = 4
            self.client.mcp(self.definition)
            self.checking = 5
            # Inspect the plugin shipped with this install: after an upgrade AGH still runs the previous one until it is updated.
            if self.client.plugin(self.package, dict(type='file', ref='file:./plugins/' + self.release.name)) != binding['integrity']:
                raise ValueError('插件和上次配置时不一样，正在重新配置')
            self.client.skill(binding['workspace_id'])
            for number in (2, 3, 4, 5, 7):
                self.step(number, True, '已核对')
            self.integrity = binding['integrity']
            self.data.update(operation_id=uuid.uuid4().hex, workspace_id=binding['workspace_id'], phase='waiting_models')
        except Exception as error:
            self.log(dict(result='resume-failed', reason=str(error) if isinstance(error, ValueError) else type(error).__name__))
            self.binding = {}
            return self.begin()
        return self.public()


def compile_python(root):
    """Compile bytecode once (about 20 s): a cold first start of the tools would miss AGH's 10-second handshake."""
    import compileall
    return all([compileall.compile_dir(str(Path(root) / folder), quiet=1, workers=0)
                for folder in ('runtime/python/Lib/site-packages', 'backend')])


def install(root):
    """Run by the installer right after copying files. Everything except the browser-side workspace step."""
    from .agh_process import OwnedAgh
    agh = OwnedAgh()
    coordinator = Coordinator(root, start=agh.start)
    coordinator.log(dict(result='compile', passed=compile_python(root)))
    coordinator.step(1, True, '安装时不检查窗口组件，打开光筑时再检查')
    try:
        coordinator.configure()
    finally:
        try:
            agh.close()
        except Exception as error:
            coordinator.log(dict(result='install-stop-failed', reason=type(error).__name__))
    state = coordinator.public()
    coordinator.log(dict(result='install', phase=state['phase'], reason=state.get('error', '')))
    if state['phase'] != 'waiting_workspace':
        print(state.get('error', '配置失败'), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    if sys.argv[1:] != ['install']:
        raise SystemExit('用法：python -m guangzhu.setup install')
    raise SystemExit(install(Path(__file__).resolve().parents[2]))
