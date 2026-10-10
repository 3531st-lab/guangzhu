"""Exercise production stage cleanup, path validation, and fatal exclusions."""
import ctypes
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


spec = importlib.util.spec_from_file_location("installer_stage", Path(__file__).parents[1] / "scripts/installer_stage.py")
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


@pytest.fixture
def stage(tmp_path):
    (tmp_path / "runtime/python/Lib/site-packages").mkdir(parents=True)
    (tmp_path / "desktop").mkdir()
    return tmp_path


def test_real_cleanup_removes_unused_launchers_and_settings(stage):
    entries = stage / "runtime/python/Lib/site-packages/bin"
    entries.mkdir()
    (entries / "fastapi.exe").write_bytes(b"launcher#!" + sys.executable.encode() + b"\n")
    (stage / "desktop/settings.json").write_text('{"theme": "light"}')
    official = stage / "runtime/agh/LICENSE"
    official.parent.mkdir()
    official.write_bytes(b"original license")
    with pytest.raises(ValueError, match="Host/developer path"):
        packaging.validate_stage(stage, sys.executable, Path(__file__).parents[1])
    packaging.cleanup_stage(stage)
    assert not entries.exists()
    assert not (stage / "desktop/settings.json").exists()
    assert official.read_bytes() == b"original license"
    assert packaging.validate_stage(stage, sys.executable, Path(__file__).parents[1]) == 0
    packaging.cleanup_stage(stage)


@pytest.mark.parametrize("source,encoding", [("host", "utf-8"), ("developer", "utf-16-le")])
def test_scan_detects_installed_text_paths(stage, source, encoding):
    root = Path(__file__).parents[1]
    location = Path(sys.executable).parent if source == "host" else root
    (stage / "desktop/config.json").write_bytes(str(location).replace("\\", "\\\\").encode(encoding))
    with pytest.raises(ValueError, match="Host/developer path.*config.json"):
        packaging.validate_stage(stage, sys.executable, root)


def test_validation_rejects_launcher_directory_without_host_path(stage):
    (stage / "runtime/python/Lib/site-packages/bin").mkdir()
    with pytest.raises(ValueError, match="Excluded installed entry remains"):
        packaging.validate_stage(stage, sys.executable, Path(__file__).parents[1])


def test_cleanup_propagates_actual_locked_settings_failure(stage):
    settings = stage / "desktop/settings.json"
    settings.write_text("development settings")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                  ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(settings), 0x80000000, 0, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        with pytest.raises(PermissionError):
            packaging.cleanup_stage(stage)
        assert settings.exists()
    finally:
        assert kernel.CloseHandle(handle)
    packaging.cleanup_stage(stage)
    assert not settings.exists()


@pytest.mark.parametrize("nested,inside", [(False, False), (True, False), (True, True)])
def test_cleanup_rejects_junction_and_preserves_content(stage, tmp_path_factory, nested, inside):
    external = stage / "untouched" if inside else tmp_path_factory.mktemp("external")
    external.mkdir(exist_ok=True)
    keep = external / "keep"
    keep.write_text("user data")
    entries = stage / "runtime/python/Lib/site-packages/bin"
    if nested:
        entries.mkdir()
        entries = entries / "nested"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(entries), str(external)],
                            capture_output=True, text=True, encoding="mbcs", errors="replace")
    assert result.returncode == 0, result.stderr
    try:
        with pytest.raises(ValueError, match="escaped staging|Reparse"):
            packaging.cleanup_stage(stage)
        assert keep.read_text() == "user data"
    finally:
        entries.rmdir()


def test_payload_trimming_preserves_runtime_data_metadata_and_licenses(stage):
    site = stage / 'runtime/python/Lib/site-packages'
    removed = ['numpy/core/tests/test_math.py', 'scipy/sparse/tests/data/matrix.npz', 'pandas/tests/io/example.csv']
    kept = ['numpy/core/runtime.pyd', 'numpy/_testing/utils.py', 'pvlib/data/weather.csv', 'PySAM/SAM_api.lib',
            'numpy/tests/LICENSE.txt', 'scipy/tests/licenses/origin.txt', 'numpy-2.dist-info/RECORD',
            'unlisted/tests/runtime.py', 'numpy/tests/NOTICE', 'numpy/test_runtime.py']
    for name in [*removed, *kept]:
        path = site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'preserve bytes')
    audit = packaging.cleanup_stage(stage)
    assert audit['files'] == 3 and audit['bytes'] == 3 * len(b'preserve bytes')
    assert all(not (site / name).exists() for name in removed)
    assert all((site / name).read_bytes() == b'preserve bytes' for name in kept)
    assert packaging.cleanup_stage(stage)['files'] == 0


def test_payload_trimming_rejects_test_directory_junction_before_deletion(stage, tmp_path_factory):
    external = tmp_path_factory.mktemp('payload-external')
    keep = external / 'test_runtime.py'
    keep.write_text('user content')
    package = stage / 'runtime/python/Lib/site-packages/numpy'
    package.mkdir()
    link = package / 'tests'
    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(external)], capture_output=True)
    assert result.returncode == 0
    try:
        with pytest.raises(ValueError, match='escaped staging|Reparse'):
            packaging.cleanup_stage(stage)
        assert keep.read_text() == 'user content'
    finally:
        link.rmdir()
