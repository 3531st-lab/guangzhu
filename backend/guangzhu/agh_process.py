"""Start and stop Guangzhu's own AGH instance: official runtime, own home and own port."""
import contextlib
import csv
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from urllib.request import urlopen

from .config import AGH_ORIGIN, AGH_PORT
from .setup_agh import regular

HIDDEN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def reachable(origin=AGH_ORIGIN):
    try:
        with urlopen(origin, timeout=1.5) as response:
            return response.status == 200
    except OSError:
        return False


def process_identity(pid, retained=None):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    class Basic(ctypes.Structure):
        _fields_ = [('reserved', ctypes.c_void_p * 4), ('pid', ctypes.c_size_t), ('parent', ctypes.c_size_t)]
    handle = retained or kernel.OpenProcess(0x1400, False, pid)
    if not handle:
        raise OSError('无法核对进程身份')
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        info, size, path = Basic(), wintypes.DWORD(32768), ctypes.create_unicode_buffer(32768)
        query = ctypes.WinDLL('ntdll').NtQueryInformationProcess
        query.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            raise OSError('无法核对进程创建时间')
        if query(handle, 0, ctypes.byref(info), ctypes.sizeof(info), None) != 0:
            raise OSError('无法核对父进程')
        if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            raise OSError('无法核对进程程序')
        return dict(start=(times[0].dwHighDateTime << 32) | times[0].dwLowDateTime, parent=info.parent, path=path.value)
    finally:
        if retained is None:
            kernel.CloseHandle(handle)


def private_home(path):
    """Create the instance home so that only the current user can read it (AGH refuses shared homes)."""
    path = Path(path)
    regular(next(item for item in (path, *path.parents) if item.exists()))
    if not path.exists():
        path.mkdir(parents=True)
        regular(path)
        identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True,
                                  encoding='ascii', errors='replace', creationflags=HIDDEN, check=True, timeout=5)
        sid = next(csv.reader(identity.stdout.splitlines()))[1]
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', '*' + sid + ':(OI)(CI)F'],
                       capture_output=True, creationflags=HIDDEN, check=True, timeout=5)
    return regular(path)


class OwnedAgh:
    """Only stops the daemon this object started, verified by pid, creation time and generation."""

    def __init__(self):
        self.process = self.owner = self.command = None
        self.lock = threading.Lock()
        self.closed = False

    def daemon(self, action):
        result = subprocess.run([*self.command, action, *self.scope], capture_output=True, text=True, encoding='utf-8',
                                creationflags=HIDDEN, timeout=40)
        if action == 'stop':
            if result.returncode != 0 or result.stdout.strip() not in ('stopped', 'not-running'):
                raise RuntimeError('光筑自带的 AGH 未能正常停止。')
            return result.stdout.strip()
        data = json.loads(result.stdout)
        if (not isinstance(data, dict) or type(data.get('running')) is not bool or
                result.returncode != (0 if data['running'] else 1)):
            raise RuntimeError('无法核对 AGH 实例状态')
        return data

    def start(self, executable, home, profile, cwd):
        with self.lock:
            if self.closed:
                raise RuntimeError('光筑已关闭，请重新打开。')
            self._start(executable, home, profile, cwd)

    def startup_record(self, home, event, started, http_ready, socket_ready, exit_code):
        """Keep only probe outcomes; never persist command arguments or daemon identity payloads."""
        record = dict(event=event, time_utc=datetime.now(timezone.utc).isoformat(),
                      elapsed_seconds=round(time.monotonic() - started, 3), http_ready=bool(http_ready),
                      daemon_socket_ready=bool(socket_ready), serve_exit_code=exit_code)
        self.startup_diagnostics = record
        # A diagnostics write must not turn a healthy launch into a failed launch.
        with contextlib.suppress(OSError, ValueError):
            folder = Path(home).parent / 'setup'
            folder.mkdir(exist_ok=True)
            regular(folder)
            destination = folder / 'agh-startup.jsonl'
            if destination.exists() or destination.is_symlink():
                regular(destination)
            with destination.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')

    def _start(self, executable, home, profile, cwd):
        private_home(home)
        self.command = [executable, 'daemon']
        self.scope = ['--home', home, '--profile', profile, '--workspace', cwd]
        before = self.daemon('status')
        environment = {key: value for key, value in os.environ.items() if key != 'AGNES_NODE_EXEC_PATH'}
        environment.update(AGH_HOME=home, AGNES_WEB_ORIGIN=AGH_ORIGIN)
        self.process = subprocess.Popen([executable, 'serve', '--home', home, '--profile', profile, '--cwd', cwd,
                                         '--port', str(AGH_PORT)], cwd=cwd, env=environment,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=HIDDEN)
        parent = process_identity(self.process.pid, self.process._handle)
        started = time.monotonic()
        deadline = started + 120  # antivirus and cold filesystem reads can delay the first start
        after, ready, http_ready, socket_ready, previous = {}, False, False, False, None
        while self.process.poll() is None and time.monotonic() < deadline:
            http_ready = reachable()
            after = self.daemon('status')
            socket_ready = after.get('running') is True and after.get('socketReachable') is True
            exit_code = self.process.poll()
            snapshot = http_ready, socket_ready, exit_code
            if snapshot != previous:
                self.startup_record(home, 'probe', started, http_ready, socket_ready, exit_code)
                previous = snapshot
            remaining = deadline - time.monotonic()
            if http_ready and socket_ready and exit_code is None and remaining >= 0:
                ready = True
                break
            if remaining <= 0 or exit_code is not None:
                break
            time.sleep(min(.1, remaining))
        owner = after.get('owner', {})
        if ready and before['running'] is False and owner:
            child = process_identity(owner['pid'])
            start_id = f"win32:{owner['pid']}:{child['start']}"
            if (self.process.poll() is None and child['parent'] == self.process.pid and child['start'] >= parent['start'] and
                    Path(child['path']).resolve() == (Path(executable).parent / 'runtime' / 'node.exe').resolve() and
                    owner.get('processStartId') == start_id and
                    all(isinstance(owner.get(key), str) and owner[key] for key in ('generation', 'startedAt', 'socketPath'))):
                self.owner = {key: owner[key] for key in ('pid', 'processStartId', 'generation')}
        exit_code = self.process.poll()
        if not ready or exit_code is not None:
            self.startup_record(home, 'failed', started, http_ready, socket_ready, exit_code)
            if before['running'] is False:  # giving up must not leave the daemon we started running unseen, locking install files
                with contextlib.suppress(Exception):
                    if self.process.poll() is None:
                        self.process.terminate()
                    self.daemon('stop')
            raise RuntimeError('光筑自带的 AGH 未能启动。')
        self.startup_record(home, 'ready', started, http_ready, socket_ready, exit_code)

    def close(self):
        self.closed = True
        with self.lock:
            try:
                if self.owner:
                    status = self.daemon('status')
                    if status.get('running') and all(status.get('owner', {}).get(key) == value for key, value in self.owner.items()):
                        self.daemon('stop')
                        if self.daemon('status')['running']:
                            raise RuntimeError('光筑自带的 AGH 未能正常停止。')
                    self.owner = None
            finally:
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    self.process.wait(timeout=5)
