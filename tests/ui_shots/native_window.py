"""Review-requested Windows evidence: ShellExecute, PrintWindow and WM_CLOSE.

Only the named Guangzhu window is targeted. Captures keep the full original
window pixels. No AGH profile, key, browser storage, or application state is read.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
USER = C.WinDLL('user32', use_last_error=True)
GDI = C.WinDLL('gdi32', use_last_error=True)
SHELL = C.WinDLL('shell32', use_last_error=True)
USER.SetProcessDPIAware()
SHELL.ShellExecuteW.argtypes = [W.HWND, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, C.c_int]
USER.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
USER.IsWindowVisible.argtypes = [W.HWND]
USER.GetWindowDC.restype = W.HDC
GDI.CreateCompatibleDC.restype = W.HDC
GDI.CreateCompatibleBitmap.restype = W.HBITMAP
GDI.SelectObject.restype = W.HGDIOBJ
USER.GetWindowDC.argtypes = [W.HWND]
USER.ReleaseDC.argtypes = [W.HWND, W.HDC]
GDI.CreateCompatibleDC.argtypes = [W.HDC]
GDI.CreateCompatibleBitmap.argtypes = [W.HDC, C.c_int, C.c_int]
GDI.SelectObject.argtypes = [W.HDC, W.HGDIOBJ]
GDI.DeleteObject.argtypes = [W.HGDIOBJ]
GDI.DeleteDC.argtypes = [W.HDC]
USER.PrintWindow.argtypes = [W.HWND, W.HDC, W.UINT]
USER.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
USER.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
USER.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
USER.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
USER.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
USER.SetForegroundWindow.argtypes = [W.HWND]
USER.GetForegroundWindow.restype = W.HWND
USER.ShowWindow.argtypes = [W.HWND, C.c_int]
USER.GetDpiForWindow.argtypes = [W.HWND]
USER.IsZoomed.argtypes = [W.HWND]
USER.SetCursorPos.argtypes = [C.c_int, C.c_int]
USER.GetCursorPos.argtypes = [C.POINTER(W.POINT)]
USER.mouse_event.argtypes = [W.DWORD, W.DWORD, W.DWORD, W.DWORD, C.c_size_t]
USER.AttachThreadInput.argtypes = [W.DWORD, W.DWORD, W.BOOL]
CALLBACK = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)


def windows():
    found = []
    def each(hwnd, unused):
        title = C.create_unicode_buffer(256)
        USER.GetWindowTextW(hwnd, title, len(title))
        if title.value == '光筑工作台' and USER.IsWindowVisible(hwnd):
            pid = W.DWORD()
            USER.GetWindowThreadProcessId(hwnd, C.byref(pid))
            found.append({'hwnd': hwnd, 'pid': pid.value, 'title': title.value})
        return True
    USER.EnumWindows(CALLBACK(each), 0)
    return found


def rect(function, hwnd):
    box = W.RECT()
    assert function(hwnd, C.byref(box))
    return [box.left, box.top, box.right, box.bottom]


def activate(hwnd):
    if USER.IsIconic(hwnd):
        USER.ShowWindow(hwnd, 9)
    foreground = USER.GetForegroundWindow()
    current_thread = C.WinDLL('kernel32').GetCurrentThreadId()
    foreground_thread = USER.GetWindowThreadProcessId(foreground, None)
    attached = USER.AttachThreadInput(current_thread, foreground_thread, True)
    try:
        USER.SetForegroundWindow(hwnd)
        return USER.GetForegroundWindow() == hwnd
    finally:
        if attached:
            USER.AttachThreadInput(current_thread, foreground_thread, False)


def capture(hwnd, path):
    box = rect(USER.GetWindowRect, hwnd)
    width, height = box[2]-box[0], box[3]-box[1]
    class Header(C.Structure):
        _fields_ = [('size', W.DWORD), ('width', W.LONG), ('height', W.LONG),
                    ('planes', W.WORD), ('bits', W.WORD), ('compression', W.DWORD),
                    ('image_size', W.DWORD), ('x', W.LONG), ('y', W.LONG),
                    ('used', W.DWORD), ('important', W.DWORD)]
    header = Header(C.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = C.create_string_buffer(width*height*4)
    dc = USER.GetWindowDC(hwnd)
    memory = GDI.CreateCompatibleDC(dc)
    bitmap = GDI.CreateCompatibleBitmap(dc, width, height)
    previous = GDI.SelectObject(memory, bitmap)
    try:
        assert USER.PrintWindow(hwnd, memory, 2), 'PrintWindow failed'
        GDI.SelectObject(memory, previous)
        GDI.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, C.c_void_p, C.c_void_p, W.UINT]
        assert GDI.GetDIBits(memory, bitmap, 0, height, pixels, C.byref(header), 0) == height
        with path.open('xb') as stream:
            Image.frombuffer('RGB', (width, height), pixels, 'raw', 'BGRX', 0, 1).save(stream, 'PNG')
    finally:
        GDI.SelectObject(memory, previous)
        GDI.DeleteObject(bitmap)
        GDI.DeleteDC(memory)
        USER.ReleaseDC(hwnd, dc)
    work = W.RECT()
    USER.SystemParametersInfoW(48, 0, C.byref(work), 0)
    frame = W.RECT()
    dwm = C.WinDLL('dwmapi')
    dwm.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, C.c_void_p, W.DWORD]
    assert dwm.DwmGetWindowAttribute(hwnd, 9, C.byref(frame), C.sizeof(frame)) == 0
    return dict(file=str(path), width=width, height=height, window_rect=box,
                client_rect=rect(USER.GetClientRect, hwnd), dpi=USER.GetDpiForWindow(hwnd),
                maximized=bool(USER.IsZoomed(hwnd)), work_area=[work.left,work.top,work.right,work.bottom],
                visible_frame=[frame.left,frame.top,frame.right,frame.bottom])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['list','launch','capture','activate','click','close'])
    parser.add_argument('--hwnd', type=int)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--x', type=int)
    parser.add_argument('--y', type=int)
    args = parser.parse_args()
    before = windows()
    if args.action == 'list':
        print(json.dumps(before, ensure_ascii=False))
        return
    if args.action == 'launch':
        SHELL.ShellExecuteW.restype = C.c_void_p
        started = time.monotonic()
        result = SHELL.ShellExecuteW(None, 'open', str(ROOT/'desktop/start.cmd'), None, str(ROOT), 1)
        assert result > 32, result
        previous = {row['hwnd'] for row in before}
        while time.monotonic()-started < 30:
            new = [row for row in windows() if row['hwnd'] not in previous]
            if new:
                assert len(new) == 1, new
                print(json.dumps(dict(new[0], elapsed_seconds=time.monotonic()-started), ensure_ascii=False))
                return
            time.sleep(.1)
        raise RuntimeError('No new Guangzhu window within 30 seconds')
    row, = [row for row in before if row['hwnd'] == args.hwnd]
    if args.action == 'capture':
        assert args.output is not None
        row.update(capture(args.hwnd, args.output))
    elif args.action == 'activate':
        row['foreground'] = activate(args.hwnd)
    elif args.action == 'close':
        assert USER.PostMessageW(args.hwnd, 0x10, 0, 0)
        row['sent'] = 'WM_CLOSE'
    elif args.action == 'click':
        assert args.x is not None and args.y is not None
        box = rect(USER.GetWindowRect, args.hwnd)
        assert 0 <= args.x < box[2]-box[0] and 0 <= args.y < box[3]-box[1]
        assert activate(args.hwnd), 'Target is not foreground; click not sent'
        expected = (box[0]+args.x, box[1]+args.y)
        assert USER.SetCursorPos(*expected)
        pointer = W.POINT()
        assert USER.GetCursorPos(C.byref(pointer))
        assert (pointer.x, pointer.y) == expected, 'Cursor did not reach the requested point'
        USER.mouse_event(2, 0, 0, 0, 0)
        USER.mouse_event(4, 0, 0, 0, 0)
        row['clicked_window_point'] = [args.x, args.y]
        row['screen_point'] = [pointer.x, pointer.y]
    print(json.dumps(row, ensure_ascii=False))


if __name__ == '__main__':
    main()
