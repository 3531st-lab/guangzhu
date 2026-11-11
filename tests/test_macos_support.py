"""Cross-platform macOS (darwin arm64 & x64) runtime, launcher, workspace sync, and bundle integrity tests."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import plistlib
from types import SimpleNamespace
import sys

from PIL import Image
import pytest

from guangzhu import agh_process, api, platform_compat, setup

ROOT = Path(__file__).resolve().parents[1]

SYNC_SPEC = importlib.util.spec_from_file_location("sync_macos_workspace", ROOT / "scripts/sync_macos_workspace.py")
sync_mod = importlib.util.module_from_spec(SYNC_SPEC)
SYNC_SPEC.loader.exec_module(sync_mod)

LAUNCHER_SPEC = importlib.util.spec_from_file_location("desktop_launcher_mac", ROOT / "desktop/app.py")
mac_launcher = importlib.util.module_from_spec(LAUNCHER_SPEC)
LAUNCHER_SPEC.loader.exec_module(mac_launcher)


@pytest.mark.parametrize("machine,expected_arch", [("arm64", "arm64"), ("aarch64", "arm64"), ("x86_64", "x64")])
def test_darwin_paths_and_data_home_conventions(tmp_path, monkeypatch, machine, expected_arch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform_compat.platform, "machine", lambda: machine)
    monkeypatch.delenv("GUANGZHU_DATA_HOME", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("GUANGZHU_RUNTIME_ROOT", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "mac-user"))

    assert platform_compat.is_macos() is True
    assert platform_compat.is_windows() is False
    assert platform_compat.darwin_arch_tag() == expected_arch
    assert platform_compat.default_data_home() == tmp_path / "mac-user/Library/Application Support/Guangzhu"

    app_root = tmp_path / "workspace"
    assert platform_compat.bundled_python_exe(app_root) == app_root / "runtime/python/bin/python3"
    assert platform_compat.bundled_agh_exe(app_root) == app_root / f"runtime/agh/agnes-darwin-{expected_arch}"

    bundle_runtime = tmp_path / "光筑.app/Contents/Resources/runtime"
    (bundle_runtime / "python/lib/python3.12/site-packages").mkdir(parents=True)
    (bundle_runtime / "python/bin").mkdir(parents=True)
    py_bin = bundle_runtime / "python/bin/python3"
    py_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("GUANGZHU_RUNTIME_ROOT", str(bundle_runtime))

    assert platform_compat.bundled_python_exe(app_root) == py_bin
    assert platform_compat.bundled_site_packages(app_root) == bundle_runtime / "python/lib/python3.12/site-packages"


def test_darwin_open_and_finder_reveal_commands(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform_compat.subprocess, "Popen", lambda cmd, **kw: calls.append(cmd))

    pdf_file = tmp_path / "report-v1.pdf"
    dxf_file = tmp_path / "layout-v1.dxf"
    platform_compat.posix_startfile(pdf_file)
    platform_compat.reveal_in_file_manager(dxf_file)
    browsers = platform_compat.candidate_pdf_browsers()

    assert calls == [["open", str(pdf_file)], ["open", "-R", str(dxf_file)]]
    assert any("Google Chrome.app/Contents/MacOS/Google Chrome" in p.as_posix() for p in browsers)


def test_darwin_desktop_launcher_uses_cocoa_wkwebview_and_checks_macos_version(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(mac_launcher.platform, "mac_ver", lambda: ("10.15.7", ("", "", ""), "x86_64"))
    with pytest.raises(RuntimeError, match="macOS 11"):
        mac_launcher.platform_check()

    monkeypatch.setattr(mac_launcher.platform, "mac_ver", lambda: ("14.6.1", ("", "", ""), "arm64"))
    mac_launcher.platform_check()

    calls = []
    bundle_rt = tmp_path / "Resources/runtime"
    (bundle_rt / "python/bin").mkdir(parents=True)
    (bundle_rt / "python/bin/python3").write_text("", encoding="utf-8")
    monkeypatch.setenv("GUANGZHU_RUNTIME_ROOT", str(bundle_rt))
    monkeypatch.setattr(mac_launcher, "ROOT", tmp_path)
    monkeypatch.setattr(mac_launcher, "INSTALLED", True, raising=False)
    monkeypatch.setattr(mac_launcher, "API_ORIGIN", "http://127.0.0.1:8766", raising=False)
    monkeypatch.setattr(mac_launcher, "load_backend", lambda: None)
    monkeypatch.setattr(mac_launcher, "single_instance", lambda: True)
    monkeypatch.setattr(mac_launcher, "register_app", lambda: calls.append("register"))
    monkeypatch.setattr(mac_launcher, "data_home", lambda: tmp_path / "support", raising=False)
    monkeypatch.setattr(
        mac_launcher,
        "OwnedServers",
        lambda: SimpleNamespace(start=lambda: calls.append("servers-start"), close=lambda: calls.append("servers-close")),
    )
    window = SimpleNamespace(
        load_url=lambda url: calls.append(("load_url", url)),
        load_html=lambda html: calls.append("load_html"),
        events=SimpleNamespace(loaded=SimpleNamespace(wait=lambda t: True)),
    )

    def fake_start(boot_fn, **kwargs):
        calls.append(("webview_start", kwargs["gui"], Path(kwargs["icon"]).name))
        boot_fn()

    monkeypatch.setitem(
        sys.modules,
        "webview",
        SimpleNamespace(create_window=lambda *a, **kw: window, start=fake_start, settings={}),
    )
    mac_launcher.main()

    assert ("webview_start", "cocoa", "guangzhu.icns") in calls
    assert ("load_url", "http://127.0.0.1:8766") in calls
    assert calls[-1] == "servers-close"


def test_darwin_standalone_setup_coordinator_succeeds_without_agh_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("GUANGZHU_DATA_HOME", str(tmp_path / "support"))
    monkeypatch.delenv("GUANGZHU_RUNTIME_ROOT", raising=False)

    app_root = tmp_path / "workspace"
    (app_root / "data/demo/park-seeds").mkdir(parents=True)
    (app_root / "build-manifest.json").write_text('{"version":"0.3.0","platform":"darwin-arm64"}', encoding="utf-8")

    coordinator = setup.Coordinator(
        app_root,
        analyze=lambda root: {"passed": True, "failures": []},
        port=lambda: False,
    )
    coordinator.step(1, True, "macOS 与 WKWebView 已就绪")
    coordinator.configure()
    state = coordinator.public()

    assert state["phase"] == "ready"
    assert state["ready"] is True
    assert state["required"] is False
    assert all(step["state"] == "ready" for step in state["steps"])


def test_darwin_posix_private_home_and_ps_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    home = tmp_path / "mac-agh-home"
    created = agh_process.private_home(home)
    assert created == home.resolve()

    ps_stdout = "Wed Nov 11 05:10:00 2026    42\n"
    monkeypatch.setattr(
        agh_process.subprocess,
        "run",
        lambda args, **kw: SimpleNamespace(returncode=0, stdout=ps_stdout),
    )
    monkeypatch.setattr(agh_process, "_posix_pid_path", lambda pid: "/Applications/光筑.app/Contents/Resources/runtime/agh/runtime/node")
    ident = agh_process.process_identity(43)
    assert ident["parent"] == 42
    assert ident["start"] > 1_700_000_000
    assert ident["path"].endswith("/runtime/node")


def test_macos_workspace_sync_preserves_user_projects_across_upgrades(tmp_path):
    payload = tmp_path / "payload"
    workspace = tmp_path / "workspace"

    (payload / "backend/guangzhu").mkdir(parents=True)
    (payload / "backend/guangzhu/api.py").write_text("# v1\n", encoding="utf-8")
    (payload / "desktop/web").mkdir(parents=True)
    (payload / "desktop/app.py").write_text("# app v1\n", encoding="utf-8")
    (payload / "desktop/web/index.html").write_text("<h1>v1</h1>", encoding="utf-8")
    (payload / "data/catalog").mkdir(parents=True)
    (payload / "data/catalog/modules.csv").write_text("id,power\nM1,550\n", encoding="utf-8")
    (payload / "LICENSE").write_text("MIT", encoding="utf-8")
    (payload / "THIRD_PARTY_NOTICES.md").write_text("Notices", encoding="utf-8")
    (payload / "build-manifest.json").write_text('{"version":"0.3.0","build":"1"}', encoding="utf-8")

    # 1. Fresh install sync
    first = sync_mod.sync_workspace(payload, workspace)
    assert first["synced"] is True
    assert (workspace / "backend/guangzhu/api.py").read_text(encoding="utf-8") == "# v1\n"
    assert (workspace / "projects").is_dir()

    # Create user data in workspace
    user_proj = workspace / "projects/taizhou-user-case/project.json"
    user_proj.parent.mkdir(parents=True)
    user_proj.write_text('{"id":"taizhou-user-case"}', encoding="utf-8")
    user_roof = workspace / "data/myroofs/roof-1/roof.json"
    user_roof.parent.mkdir(parents=True)
    user_roof.write_text('{"name":"我的泰州厂房"}', encoding="utf-8")
    user_settings = workspace / "desktop/settings.json"
    user_settings.write_text('{"custom":"preserved"}', encoding="utf-8")

    # 2. Second launch with identical manifest skips copying
    second = sync_mod.sync_workspace(payload, workspace)
    assert second["synced"] is False

    # 3. Upgrade payload -> refreshes immutable code while preserving all user data
    (payload / "backend/guangzhu/api.py").write_text("# v2 upgraded\n", encoding="utf-8")
    (payload / "desktop/web/index.html").write_text("<h1>v2</h1>", encoding="utf-8")
    (payload / "build-manifest.json").write_text('{"version":"0.3.1","build":"2"}', encoding="utf-8")

    third = sync_mod.sync_workspace(payload, workspace)
    assert third["synced"] is True
    assert (workspace / "backend/guangzhu/api.py").read_text(encoding="utf-8") == "# v2 upgraded\n"
    assert (workspace / "desktop/web/index.html").read_text(encoding="utf-8") == "<h1>v2</h1>"
    assert user_proj.read_text(encoding="utf-8") == '{"id":"taizhou-user-case"}'
    assert user_roof.read_text(encoding="utf-8") == '{"name":"我的泰州厂房"}'
    assert user_settings.read_text(encoding="utf-8") == '{"custom":"preserved"}'


def test_macos_bundle_assets_and_shell_scripts_have_valid_formats_and_lf_endings():
    icns_path = ROOT / "desktop/web/assets/guangzhu.icns"
    assert icns_path.is_file()
    raw_icns = icns_path.read_bytes()
    assert raw_icns[:4] == b"icns"
    with Image.open(icns_path) as img:
        assert img.format == "ICNS"
        assert img.size == (1024, 1024)

    plist_path = ROOT / "installer/macos/Info.plist"
    plist_data = plistlib.loads(plist_path.read_bytes())
    assert plist_data["CFBundleIdentifier"] == "cn.guangzhu.desktop"
    assert plist_data["CFBundleExecutable"] == "Guangzhu"
    assert plist_data["CFBundleDisplayName"] == "光筑"
    assert plist_data["LSHasLocalizedDisplayName"] is True
    assert plist_data["CFBundleIconFile"] == "guangzhu.icns"
    assert plist_data["LSMinimumSystemVersion"] == "11.0"
    assert plist_data["NSHighResolutionCapable"] is True

    for rel in (
        "scripts/build_macos_dmg.sh",
        "start-mac.command",
        "installer/macos/launch-fallback.sh",
    ):
        script_bytes = (ROOT / rel).read_bytes()
        assert b"\r" not in script_bytes, f"{rel} must use pure LF line endings for macOS bash"
        assert script_bytes.startswith(b"#!/usr/bin/env bash\n")
