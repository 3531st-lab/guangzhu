"""光筑桌面窗口：先出窗口，再在后台启动光筑后端和自带的 AGH。"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

APP_ID = 'Guangzhu.Desktop'
TITLE = '光筑'
ICON = ROOT / 'desktop/web/assets/guangzhu.ico'
WEBVIEW_URL = 'https://developer.microsoft.com/microsoft-edge/webview2/'
LOADING = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>光筑</title>
<style>html,body{height:100%;margin:0;background:#1b1714;color:#f4ece3;font:15px "Microsoft YaHei UI",sans-serif}
body{display:grid;place-items:center}main{text-align:center}b{display:block;font-size:42px;color:#e08a4f;letter-spacing:6px}
p{color:#b9ab9d;margin:14px 0 22px}i{display:block;width:180px;height:3px;margin:auto;background:#3a312a;overflow:hidden}
i:after{content:"";display:block;width:60px;height:3px;background:#e08a4f;animation:m 1.2s infinite ease-in-out}
@keyframes m{from{transform:translateX(-60px)}to{transform:translateX(180px)}}</style>
<main><b>光筑</b><p>{message}</p><i></i></main></html>'''


def native_error(message):
    ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10)


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


def single_instance():
    """True for the first copy. A second double-click only brings the open window to the front."""
    kernel, user = ctypes.windll.kernel32, ctypes.windll.user32
    kernel.CreateMutexW.restype = ctypes.c_void_p
    name = f'Local\\{APP_ID}.' + hashlib.sha256(str(ROOT).lower().encode()).hexdigest()[:16]
    single_instance.handle = kernel.CreateMutexW(None, False, name)
    if kernel.GetLastError() != 183:
        return True
    window = user.FindWindowW(None, TITLE)
    if window:
        user.ShowWindow(window, 9)
        user.SetForegroundWindow(window)
    return False


def register_app():
    """Same id as the shortcuts, so the taskbar shows the Guangzhu icon and name, not Python's."""
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def backend_ready():
    try:
        with urlopen(API_ORIGIN + '/api/status', timeout=.35) as response:
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
            coordinator.step(1, True, 'Windows 与 WebView2 已就绪')
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
        if INSTALLED and not all((ROOT / name).is_file() for name in
                                        ('runtime/agh/agnes-win32-x64.exe', 'runtime/python/python.exe')):
            raise RuntimeError('安装文件缺少内置组件，请重新安装光筑。')
        import webview
    except RuntimeError as error:
        return native_error(str(error))
    except Exception:
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
    try:
        webview.start(boot, gui='edgechromium', private_mode=False, storage_path=str(storage), icon=str(ICON))
    except Exception:
        native_error('WebView2 无法打开，请修复或重新安装它：\n' + WEBVIEW_URL)
    finally:
        try:
            servers.close()
        except Exception:
            native_error('光筑自带的 AGH 没能正常关闭，下次打开时会自动处理。')


if __name__ == '__main__':
    main()
