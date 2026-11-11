"""Cross-platform runtime paths, user data locations, and native file openers (Windows & macOS)."""

from __future__ import annotations

import os
from pathlib import Path
import platform
import subprocess
import sys


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_windows() -> bool:
    return sys.platform == "win32"


def runtime_root(app_root: Path | str) -> Path:
    """Return bundled runtime directory, supporting read-only macOS .app bundles via GUANGZHU_RUNTIME_ROOT."""
    override = os.environ.get("GUANGZHU_RUNTIME_ROOT")
    if override:
        return Path(override)
    return Path(app_root) / "runtime"


def bundled_python_exe(app_root: Path | str) -> Path:
    rt = runtime_root(app_root)
    if is_windows():
        return rt / "python/python.exe"
    candidates = (
        rt / "python/bin/python3",
        rt / "python/bin/python3.12",
        rt / "python/python.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def bundled_site_packages(app_root: Path | str) -> Path:
    rt = runtime_root(app_root)
    if is_windows():
        win_site = rt / "python/Lib/site-packages"
        if win_site.exists() or not (rt / "python/lib/python3.12/site-packages").exists():
            return win_site
    posix_site = rt / "python/lib/python3.12/site-packages"
    if posix_site.exists():
        return posix_site
    win_site = rt / "python/Lib/site-packages"
    if win_site.exists():
        return win_site
    return win_site if is_windows() else posix_site


def darwin_arch_tag() -> str:
    machine = platform.machine().lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x64"


def bundled_agh_exe(app_root: Path | str) -> Path:
    agh_dir = runtime_root(app_root) / "agh"
    if is_windows():
        return agh_dir / "agnes-win32-x64.exe"
    if is_macos():
        arch = darwin_arch_tag()
        candidates = (
            agh_dir / f"agnes-darwin-{arch}",
            agh_dir / "agnes-darwin-arm64",
            agh_dir / "agnes-darwin-x64",
            agh_dir / "agnes-darwin",
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return candidates[0]
    return agh_dir / "agnes-linux-x64"


def bundled_agh_node_exe(agh_executable: Path | str) -> Path:
    parent = Path(agh_executable).parent
    if is_windows():
        return parent / "runtime/node.exe"
    for rel in ("runtime/node", "runtime/bin/node", "runtime/node.exe"):
        cand = parent / rel
        if cand.is_file():
            return cand
    return parent / "runtime/node"


def default_data_home() -> Path:
    """User-writable application data root on Windows (%LOCALAPPDATA%\\guangzhu) and macOS (~/Library/Application Support/Guangzhu)."""
    override = os.environ.get("GUANGZHU_DATA_HOME")
    if override:
        return Path(override)
    if is_windows() or "LOCALAPPDATA" in os.environ:
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "guangzhu"
    if is_macos():
        return Path.home() / "Library" / "Application Support" / "Guangzhu"
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".local" / "share")
    return base / "guangzhu"


def posix_startfile(filepath: Path | str) -> None:
    target = str(filepath)
    cmd = ["open", target] if is_macos() else ["xdg-open", target]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def ensure_os_startfile() -> None:
    """Provide os.startfile on macOS/POSIX so callers and monkeypatched tests share a single contract."""
    if not hasattr(os, "startfile"):
        setattr(os, "startfile", posix_startfile)


def reveal_in_file_manager(filepath: Path | str) -> None:
    target = Path(filepath)
    if is_macos():
        subprocess.Popen(["open", "-R", str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif is_windows():
        subprocess.Popen(["explorer.exe", f"/select,{target}"])
    else:
        subprocess.Popen(["xdg-open", str(target.parent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def candidate_pdf_browsers() -> list[Path]:
    """Return candidate Chromium-family browsers for headless HTML-to-PDF export."""
    if is_windows():
        return [
            Path(os.environ.get(key, "")) / suffix
            for suffix in ("Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe")
            for key in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")
        ]
    if is_macos():
        roots = [Path("/Applications"), Path.home() / "Applications"]
        bundles = (
            "Google Chrome.app/Contents/MacOS/Google Chrome",
            "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "Chromium.app/Contents/MacOS/Chromium",
            "Brave Browser.app/Contents/MacOS/Brave Browser",
        )
        return [root / bundle for root in roots for bundle in bundles]
    return [
        Path(p)
        for p in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge")
    ]
