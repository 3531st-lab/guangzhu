"""Verify the PySAM environment fix without running a generation calculation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from textwrap import dedent

import pytest

from guangzhu import native_runtime


ROOT = Path(__file__).resolve().parents[1]
WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="Windows native-loader compatibility")
# AGH mcp-server-opener.ts:153,178 (baseEnv={}); base/src/mcp/connect.ts:264.
# MCP TS SDK 1.25.2 src/client/stdio.ts:41-79 getDefaultEnvironment, 111-120 spawn:
# https://raw.githubusercontent.com/modelcontextprotocol/typescript-sdk/v1.25.2/src/client/stdio.ts
AGH_STDIO_ENV_VARS = ("APPDATA", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "PATH",
                      "PROCESSOR_ARCHITECTURE", "SYSTEMDRIVE", "SYSTEMROOT", "TEMP",
                      "USERNAME", "USERPROFILE", "PROGRAMFILES")


@pytest.fixture
def ascii_workspace() -> Path:
    # The usual Windows pytest temp path contains the user's Unicode name.
    # create=False only resolves the managed cache; temporary files go beside it.
    parent = native_runtime._runtime_root(create=False).parent if os.name == "nt" else None
    with tempfile.TemporaryDirectory(prefix="guangzhu-native-test-", dir=parent) as directory:
        workspace = Path(directory)
        try:
            yield workspace
        finally:
            if parent is not None:
                assert workspace.resolve().parent == parent.resolve()
                native_runtime._reject_links(workspace)


def synthetic_source(parent: Path, name: str) -> Path:
    source = parent / name / "PySAM"
    source.mkdir(parents=True)
    names = ["__init__.py", "version.py", "Pvwattsv8" + native_runtime.EXTENSION_SUFFIXES[0],
             "SAM_api.dll", "ssc.dll", "defaults/pvwattsv8_pvwattsnone.df"]
    for name in names:
        path = source / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(b"synthetic runtime test fixture")
    return source


def mirror_fixture(source: Path) -> Path:
    identity, files = native_runtime._installation_snapshot(source, "unit-test-version")
    return native_runtime._mirror(source, identity, files, "unit-test-version").parent


@WINDOWS_ONLY
def test_prepare_is_idempotent_and_copies_only_required_extension() -> None:
    first = native_runtime.prepare_pysam()
    extensions = list(first.glob("Pvwattsv8*.pyd"))
    assert len(extensions) == 1
    before = extensions[0].stat().st_mtime_ns
    handles = len(native_runtime._DLL_HANDLES)
    assert native_runtime.prepare_pysam() == first
    assert extensions[0].stat().st_mtime_ns == before
    assert len(native_runtime._DLL_HANDLES) == handles
    assert str(first.resolve()).isascii()
    assert not first.is_symlink() and not first.is_junction()
    import PySAM
    source = Path(PySAM.__file__).resolve().parent
    if not str(source).isascii():
        assert len(list(first.glob("*.pyd"))) == 1
        assert not os.path.samefile(source / extensions[0].name, extensions[0])


def run_native_probe(*, ascii_source: bool, cache: Path) -> dict:
    script = dedent("""
        import json
        import sys
        from pathlib import Path
        from guangzhu.native_runtime import prepare_pysam

        if sys.argv[1]:
            sys.path.insert(0, sys.argv[1])
        runtime = prepare_pysam()
        from PySAM import Pvwattsv8
        assert Path(Pvwattsv8.__file__).resolve().parent == runtime
        model = Pvwattsv8.default('PVWattsNone')
        names = ('system_capacity', 'dc_ac_ratio', 'array_type', 'module_type', 'losses', 'tilt')
        print(json.dumps({
            'runtime': str(runtime),
            'defaults': {name: getattr(model.SystemDesign, name) for name in names},
        }))
    """)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "backend")
    environment["GUANGZHU_NATIVE_CACHE"] = str(cache)
    source_parent = str(native_runtime.prepare_pysam().parent) if ascii_source else ""
    result = subprocess.run(
        [sys.executable, "-c", script, source_parent], cwd=ROOT, env=environment,
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert result.returncode == 0, f"Native probe failed: exit {result.returncode}; {result.stderr}"
    return json.loads(result.stdout)


@WINDOWS_ONLY
@pytest.mark.parametrize("ascii_source", [False, True])
def test_subprocess_imports_native_extension_and_default_parameters(ascii_source: bool, ascii_workspace: Path) -> None:
    cache = ascii_workspace / "native-cache"
    result = run_native_probe(ascii_source=ascii_source, cache=cache)
    assert result["runtime"].isascii()
    if not ascii_source:
        assert Path(result["runtime"]).is_relative_to(cache)
    assert result["defaults"] == pytest.approx({
        "system_capacity": 100000.0, "dc_ac_ratio": 1.15, "array_type": 1.0,
        "module_type": 0.0, "losses": 14.0757, "tilt": 20.0,
    })


@WINDOWS_ONLY
def test_real_native_loader_with_agh_minimal_environment(ascii_workspace: Path) -> None:
    environment = {key: os.environ[key] for key in AGH_STDIO_ENV_VARS if key in os.environ}
    assert len(AGH_STDIO_ENV_VARS) == 12
    public_root = Path(environment["SYSTEMDRIVE"] + "\\") / "Users" / "Public" / "Documents" / "guangzhu-runtime"
    import PySAM
    source = Path(PySAM.__file__).resolve().parent
    identity, files = native_runtime._installation_snapshot(source, native_runtime.version("nrel-pysam"))
    installation = public_root / identity
    newly_created = not installation.exists()
    script = dedent("""
        import json, os
        from pathlib import Path
        from guangzhu.native_runtime import _runtime_root, prepare_pysam
        assert not {'PUBLIC', 'GUANGZHU_NATIVE_CACHE', 'PYTHONPATH', 'PYTHONUTF8'} & os.environ.keys()
        root = _runtime_root(create=False)
        runtime = prepare_pysam()
        from PySAM import Pvwattsv8
        assert Path(Pvwattsv8.__file__).resolve().parent == runtime
        model = Pvwattsv8.default('PVWattsNone')
        print(json.dumps({'root': str(root), 'runtime': str(runtime),
                          'system_capacity': model.SystemDesign.system_capacity,
                          'losses': model.SystemDesign.losses, 'env_keys': list(os.environ)}))
    """)
    try:
        result = subprocess.run([sys.executable, "-c", script], cwd=ascii_workspace, env=environment,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        actual = json.loads(result.stdout)
        assert Path(actual["root"]) == public_root.resolve()
        assert actual["runtime"].isascii() and set(actual["env_keys"]) == set(environment)
        if not str(source).isascii():
            assert Path(actual["runtime"]) == installation / "PySAM"
        assert actual["system_capacity"] == 100000 and actual["losses"] == pytest.approx(14.0757)
    finally:
        if newly_created and installation.exists():
            # Delete only this test's verified copy, never another public cache.
            assert installation.resolve().parent == public_root.resolve() and installation.name == identity
            native_runtime._read_manifest(installation)
            native_runtime._check_contents(installation, public_root.resolve(), files, complete=True)
            shutil.rmtree(installation)


@WINDOWS_ONLY
def test_systemdrive_fallback_root_and_clean_command(monkeypatch: pytest.MonkeyPatch, ascii_workspace: Path) -> None:
    monkeypatch.delenv("GUANGZHU_NATIVE_CACHE", raising=False)
    monkeypatch.delenv("PUBLIC", raising=False)
    monkeypatch.setenv("SYSTEMDRIVE", str(ascii_workspace))
    root = ascii_workspace / "Users" / "Public" / "Documents" / "guangzhu-runtime"
    assert native_runtime._runtime_root(create=False) == root
    assert native_runtime.clean_cache() == [] and not root.exists()
    source = synthetic_source(ascii_workspace, "orphan-source")
    installation = mirror_fixture(source)
    sentinel = root / "unrelated.txt"
    sentinel.write_text("keep", encoding="utf-8")
    assert source.resolve().is_relative_to(ascii_workspace.resolve())
    shutil.rmtree(source)
    environment = {key: os.environ[key] for key in AGH_STDIO_ENV_VARS if key in os.environ}
    result = subprocess.run([sys.executable, "-m", "guangzhu.native_runtime", "--clean"],
                            cwd=ascii_workspace, env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "Removed 1 verified" in result.stdout and not installation.exists()
    assert sentinel.read_text(encoding="utf-8") == "keep"
    for invalid in ("", "relative-drive", str(ascii_workspace / "非ASCII")):
        monkeypatch.setenv("SYSTEMDRIVE", invalid)
        with pytest.raises(RuntimeError, match="SYSTEMDRIVE must be an absolute ASCII path"):
            native_runtime._runtime_root()


@WINDOWS_ONLY
def test_non_ascii_public_has_clear_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GUANGZHU_NATIVE_CACHE", raising=False)
    monkeypatch.setenv("PUBLIC", str(tmp_path / "非ASCII目录"))
    with pytest.raises(RuntimeError, match="PUBLIC must be an absolute ASCII path"):
        native_runtime._runtime_root()


@WINDOWS_ONLY
def test_unwritable_public_has_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GUANGZHU_NATIVE_CACHE", raising=False)
    monkeypatch.setenv("PUBLIC", str(Path(os.environ["SYSTEMDRIVE"] + "\\") / "Users" / "Public"))

    def denied(path: Path, **kwargs) -> None:
        raise PermissionError("simulated read-only directory")
    monkeypatch.setattr(Path, "mkdir", denied)
    with pytest.raises(RuntimeError, match="Cannot create or access.*PUBLIC"):
        native_runtime._runtime_root()


@WINDOWS_ONLY
def test_snapshot_changes_when_installed_content_changes(tmp_path: Path) -> None:
    source = synthetic_source(tmp_path, "installed")
    original, _ = native_runtime._installation_snapshot(source, "unit-test-version")
    (source / "defaults/pvwattsv8_pvwattsnone.df").write_bytes(b"updated runtime test fixture")
    updated, _ = native_runtime._installation_snapshot(source, "unit-test-version")
    assert original != updated


def test_cache_setting_override_default_and_validation(monkeypatch: pytest.MonkeyPatch, ascii_workspace: Path) -> None:
    monkeypatch.delenv("GUANGZHU_NATIVE_CACHE", raising=False)
    monkeypatch.setenv("PUBLIC", str(ascii_workspace))
    assert native_runtime._runtime_root(create=False) == ascii_workspace / "Documents" / "guangzhu-runtime"
    cache = ascii_workspace / "custom-cache"
    monkeypatch.setenv("GUANGZHU_NATIVE_CACHE", str(cache))
    monkeypatch.setenv("PUBLIC", "无效")
    assert native_runtime._runtime_root(create=False) == cache
    assert native_runtime.clean_cache() == []
    assert not cache.exists()
    assert native_runtime._runtime_root() == cache
    for invalid in ("", "relative-cache", str(ascii_workspace / "中文")):
        monkeypatch.setenv("GUANGZHU_NATIVE_CACHE", invalid)
        with pytest.raises(RuntimeError, match="GUANGZHU_NATIVE_CACHE must be an absolute ASCII path"):
            native_runtime._runtime_root()


def test_cleanup_command_removes_only_verified_orphans_then_all(monkeypatch: pytest.MonkeyPatch, ascii_workspace: Path) -> None:
    cache = ascii_workspace / "cache"
    monkeypatch.setenv("GUANGZHU_NATIVE_CACHE", str(cache))
    live_source = synthetic_source(ascii_workspace, "live")
    old_source = synthetic_source(ascii_workspace, "old")
    live, orphan = mirror_fixture(live_source), mirror_fixture(old_source)
    user = cache / ("f" * 64)
    user.mkdir()
    (user / "notes.txt").write_text("user content", encoding="utf-8")
    (cache / "unrelated.txt").write_text("user content", encoding="utf-8")
    assert old_source.resolve().is_relative_to(ascii_workspace.resolve())
    shutil.rmtree(old_source)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "backend")
    for arguments, count in ((["--clean"], 1), (["--clean", "--all"], 1)):
        result = subprocess.run([sys.executable, "-m", "guangzhu.native_runtime", *arguments],
                                cwd=ROOT, env=environment, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert f"Removed {count} verified" in result.stdout
        assert not orphan.exists()
        assert live.exists() == (arguments == ["--clean"])
        assert (user / "notes.txt").read_text(encoding="utf-8") == "user content"
        assert (cache / "unrelated.txt").exists()


def test_legacy_cache_needs_verified_source_before_adoption(monkeypatch: pytest.MonkeyPatch, ascii_workspace: Path) -> None:
    monkeypatch.setenv("GUANGZHU_NATIVE_CACHE", str(ascii_workspace / "cache"))
    source = synthetic_source(ascii_workspace, "installed")
    installation = mirror_fixture(source)
    manifest = installation / native_runtime._MANIFEST
    manifest.unlink()
    assert native_runtime.clean_cache(all_copies=True) == []
    extension = installation / "PySAM" / ("Pvwattsv8" + native_runtime.EXTENSION_SUFFIXES[0])
    before = extension.stat().st_mtime_ns
    assert mirror_fixture(source) == installation
    assert extension.stat().st_mtime_ns == before
    assert json.loads(manifest.read_text(encoding="utf-8"))["source"] == str(source.resolve())
    manifest.unlink()
    (installation / "user-notes.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unrecognized user content"):
        mirror_fixture(source)
    assert native_runtime.clean_cache(all_copies=True) == []
    assert (installation / "user-notes.txt").exists()


def test_cleanup_keeps_tampered_manifests_and_added_user_content(monkeypatch: pytest.MonkeyPatch, ascii_workspace: Path) -> None:
    monkeypatch.setenv("GUANGZHU_NATIVE_CACHE", str(ascii_workspace / "cache"))
    added = mirror_fixture(synthetic_source(ascii_workspace, "added"))
    (added / "PySAM" / "user-data.txt").write_text("keep", encoding="utf-8")
    invalid = mirror_fixture(synthetic_source(ascii_workspace, "invalid"))
    manifest_path = invalid / native_runtime._MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["../../outside.txt"] = "a" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    changed = mirror_fixture(synthetic_source(ascii_workspace, "changed"))
    (changed / "PySAM" / "ssc.dll").write_bytes(b"unrecognized replacement")
    assert native_runtime.clean_cache(all_copies=True) == []
    assert all(path.exists() for path in (added, invalid, changed))


@WINDOWS_ONLY
@pytest.mark.parametrize("placement", ["root", "copy", "nested"])
def test_cleanup_rejects_junctions_without_touching_target(monkeypatch: pytest.MonkeyPatch, ascii_workspace: Path,
                                                        placement: str) -> None:
    cache = ascii_workspace / "cache"
    monkeypatch.setenv("GUANGZHU_NATIVE_CACHE", str(cache))
    outside = ascii_workspace / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("keep", encoding="utf-8")
    installation = None
    if placement == "root":
        link = cache
    elif placement == "copy":
        cache.mkdir()
        link = cache / ("f" * 64)
    else:
        installation = mirror_fixture(synthetic_source(ascii_workspace, "installed"))
        link = installation / "PySAM" / "linked-defaults"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                            capture_output=True, text=True, encoding="mbcs", errors="replace", timeout=30)
    assert result.returncode == 0, result.stderr
    try:
        if placement == "root":
            # A non-existing leaf under a junction is also rejected.
            monkeypatch.setenv("GUANGZHU_NATIVE_CACHE", str(link / "new-cache"))
            with pytest.raises(RuntimeError, match="real paths, not links"):
                native_runtime.clean_cache(all_copies=True)
            assert not (outside / "new-cache").exists()
        else:
            assert native_runtime.clean_cache(all_copies=True) == []
            assert link.is_junction()
            if installation is not None:
                assert installation.exists()
        assert sentinel.read_text(encoding="utf-8") == "keep"
    finally:
        link.rmdir()  # Remove the junction itself before fixture teardown.
