"""光筑桌面窗口：先出窗口，再在后台启动光筑后端和自带的 AGH（支持 Windows WebView2 与 macOS WKWebView）。"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import threading
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

APP_ID = 'Guangzhu.Desktop'
MAC_BUNDLE_ID = 'cn.guangzhu.desktop'
TITLE = '光筑'
ICON = ROOT / 'desktop/web/assets/guangzhu.ico'
ICON_MAC = ROOT / 'desktop/web/assets/guangzhu.icns'
ICON_PNG = ROOT / 'desktop/web/assets/guangzhu-128.png'
WEBVIEW_URL = 'https://developer.microsoft.com/microsoft-edge/webview2/'
LOADING = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>光筑</title>
<style>html,body{height:100%;margin:0;background:#1b1714;color:#f4ece3;font:15px "PingFang SC","Hiragino Sans GB","Microsoft YaHei UI",-apple-system,sans-serif}
body{display:grid;place-items:center}main{text-align:center}b{display:block;font-size:42px;color:#e08a4f;letter-spacing:6px}
p{color:#b9ab9d;margin:14px 0 22px}i{display:block;width:180px;height:3px;margin:auto;background:#3a312a;overflow:hidden}
i:after{content:"";display:block;width:60px;height:3px;background:#e08a4f;animation:m 1.2s infinite ease-in-out}
@keyframes m{from{transform:translateX(-60px)}to{transform:translateX(180px)}}</style>
<main><b>光筑</b><p>{message}</p><i></i></main></html>'''


def native_error(message):
    if sys.platform == 'win32':
        ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10)
        return
    if sys.platform == 'darwin':
        try:
            subprocess.run(
                [
                    'osascript',
                    '-e', 'on run argv',
                    '-e', f'display alert "{TITLE}" message (item 1 of argv) as critical buttons {{"好"}} default button 1',
                    '-e', 'end run',
                    str(message),
                ],
                check=False,
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
    sys.stderr.write(f'{TITLE}: {message}\n')


def load_backend():
    global API_ORIGIN, API_PORT, INSTALLED, app, settings, setup_coordinator, installation, data_home, OwnedAgh, agh_reachable
    try:
        from guangzhu.config import API_ORIGIN, API_PORT, INSTALLED
        from guangzhu.api import app, settings, setup_coordinator
        from guangzhu.setup import data_home, installation
        from guangzhu.agh_process import OwnedAgh, reachable as agh_reachable
    except Exception:
        raise RuntimeError('光筑的安装文件不完整，请重新安装光筑。') from None


def platform_check():
    if sys.platform == 'darwin':
        ver_str = platform.mac_ver()[0] or ''
        major_str = ver_str.split('.', 1)[0]
        if major_str.isdigit() and int(major_str) < 11:
            raise RuntimeError('光筑需要 macOS 11 (Big Sur) 或更新版本。')
        return
    if sys.platform != 'win32' and os.name != 'nt':
        raise RuntimeError('光筑桌面端需要 Windows 10+ 或 macOS 11+。')
    if os.name != 'nt' or sys.getwindowsversion().major < 10:
        raise RuntimeError('光筑需要 Windows 10 或更新版本。')
    import winreg
    key = r'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, key, 0, winreg.KEY_READ | view) as entry:
                    version = winreg.QueryValueEx(entry, 'pv')[0]
                    if isinstance(version, str) and version not in ('', '0.0.0.0'):
                        return
            except OSError:
                pass
    raise RuntimeError('没有找到 Microsoft WebView2（Windows 自带的网页组件）。请安装后再打开光筑：\n' + WEBVIEW_URL)


def _activate_macos_window():
    script = (
        f'try\n'
        f'  tell application id "{MAC_BUNDLE_ID}" to activate\n'
        f'on error\n'
        f'  tell application "System Events"\n'
        f'    set matches to (every process whose name is "{TITLE}")\n'
        f'    if (count of matches) > 0 then set frontmost of item 1 of matches to true\n'
        f'  end tell\n'
        f'end try'
    )
    try:
        subprocess.Popen(['osascript', '-e', script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def single_instance():
    """True for the first copy. A second double-click only brings the open window to the front."""
    digest = hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:16]
    if sys.platform != 'win32':
        import fcntl
        lock_base = Path(os.environ.get('GUANGZHU_DATA_HOME') or (
            Path.home() / 'Library/Application Support/Guangzhu' if sys.platform == 'darwin' else Path('/tmp')
        ))
        lock_base.mkdir(parents=True, exist_ok=True)
        lock_file = (lock_base / f'instance-{digest}.lock').open('a+b')
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock_file.close()
            if sys.platform == 'darwin':
                _activate_macos_window()
            return False
        single_instance.handle = lock_file
        return True

    kernel, user = ctypes.windll.kernel32, ctypes.windll.user32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    name = f'Local\\{APP_ID}.' + digest
    single_instance.handle = kernel.CreateMutexW(None, False, name)
    if kernel.GetLastError() != 183:
        return True
    window = user.FindWindowW(None, TITLE)
    if window:
        user.ShowWindow(window, 9)
        user.SetForegroundWindow(window)
    return False


def register_app():
    """Register application identity and Dock/taskbar icon."""
    if sys.platform == 'win32':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        return
    if sys.platform == 'darwin':
        try:
            from AppKit import NSApplication, NSImage  # type: ignore[import-not-found]
            icon_file = ICON_MAC if ICON_MAC.is_file() else ICON_PNG
            if icon_file.is_file():
                ns_app = NSApplication.sharedApplication()
                image = NSImage.alloc().initWithContentsOfFile_(str(icon_file))
                if image is not None:
                    ns_app.setApplicationIconImage_(image)
        except Exception:
            pass


def _installed_runtime_present(root):
    rt = Path(os.environ.get('GUANGZHU_RUNTIME_ROOT', str(root / 'runtime')))
    if sys.platform == 'darwin':
        return (rt / 'python/bin/python3').is_file() or (rt / 'python/bin/python3.12').is_file()
    return (rt / 'agh/agnes-win32-x64.exe').is_file() and (rt / 'python/python.exe').is_file()


def backend_ready():
    try:
        # Status includes the separately starting AGH service. Read our local
        # identity only, so an unavailable AGH cannot look like a port conflict.
        with urlopen(API_ORIGIN + '/api/identity', timeout=2) as response:
            data = json.load(response)
        if data.get('app') == 'guangzhu' and data.get('installation') == installation(ROOT):
            return True
    except (OSError, ValueError):
        with socket.socket() as connection:
            connection.settimeout(.35)
            if connection.connect_ex(('127.0.0.1', API_PORT)) != 0:
                return False
    raise RuntimeError(f'端口 {API_PORT} 被别的程序占用。请关闭它后重新打开光筑。')


class OwnedServers:
    def __init__(self):
        self.agh = OwnedAgh()
        self.server = self.thread = None

    def start(self):
        if backend_ready():
            return
        import uvicorn
        coordinator = None
        if INSTALLED:
            app.state.start_agh = self.agh.start
            coordinator = setup_coordinator()
            step1_msg = 'macOS 与 WKWebView 已就绪' if sys.platform == 'darwin' else 'Windows 与 WebView2 已就绪'
            coordinator.step(1, True, step1_msg)
        else:
            values = settings()
            if not agh_reachable() and Path(values['agh_runtime']).is_file():
                self.agh.start(values['agh_runtime'], values['agh_home'], 'local-dev', str(ROOT))
        self.server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=API_PORT, log_level='warning'))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.05)
        if not self.server.started or not backend_ready():
            raise RuntimeError(f'光筑后台没能启动，请检查端口 {API_PORT}。')
        if coordinator:
            threading.Thread(target=coordinator.launch, daemon=True).start()

    def close(self):
        if self.server:
            self.server.should_exit = True
            self.thread.join(timeout=3)
        self.agh.close()


def main():
    try:
        platform_check()
        if not single_instance():
            return
        register_app()
        load_backend()
        if INSTALLED and not _installed_runtime_present(ROOT):
            raise RuntimeError('安装文件缺少内置组件，请重新安装光筑。')
        import webview
        try:
            webview.settings['ALLOW_DOWNLOADS'] = True
        except Exception:
            pass
    except RuntimeError as error:
        return native_error(str(error))
    except Exception:
        if sys.platform == 'darwin':
            return native_error('光筑没能打开。请重新安装光筑 Mac 版，或检查系统权限设置。')
        return native_error('光筑没能打开。请重新安装光筑；如果还不行，请安装 WebView2：\n' + WEBVIEW_URL)
    servers = OwnedServers()
    window = webview.create_window(TITLE, html=LOADING.replace('{message}', '正在启动…'), width=1280, height=760,
                                   min_size=(1100, 680), maximized=True, background_color='#1b1714')

    def boot():
        try:
            servers.start()
            window.load_url(API_ORIGIN)
        except Exception as error:
            message = str(error) if isinstance(error, RuntimeError) else '光筑后台没能启动，请重新打开；如果还不行，请重新安装光筑。'
            window.events.loaded.wait(10)  # a failure within milliseconds (port taken) must not be covered by the starting page still loading
            window.load_html(LOADING.replace('{message}', message).replace('<i></i>', ''))
    storage = data_home() / 'webview'
    storage.mkdir(parents=True, exist_ok=True)
    gui_backend = 'cocoa' if sys.platform == 'darwin' else 'edgechromium'
    window_icon = str(ICON_MAC if ICON_MAC.is_file() else ICON_PNG) if sys.platform == 'darwin' else str(ICON)
    try:
        webview.start(boot, gui=gui_backend, private_mode=False, storage_path=str(storage), icon=window_icon)
    except Exception:
        if sys.platform == 'darwin':
            native_error('macOS 原生窗口组件（WKWebView）无法打开，请重新安装光筑 Mac 版。')
        else:
            native_error('WebView2 无法打开，请修复或重新安装它：\n' + WEBVIEW_URL)
    finally:
        try:
            servers.close()
        except Exception:
            native_error('光筑自带的 AGH 没能正常关闭，下次打开时会自动处理。')


if __name__ == '__main__':
    main()
