"""Prepare PySAM's Windows native loader for installations in Unicode paths."""

from __future__ import annotations

import argparse
import hashlib
import importlib
from importlib.machinery import EXTENSION_SUFFIXES
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import uuid


_DLL_HANDLES: dict[str, object] = {}
_PREPARE_LOCK = threading.Lock()
_MANIFEST = "guangzhu-runtime.json"
_PROJECT = "guangzhu-pysam-runtime"


def _snapshot_identity(source: str, package_version: str, files: dict[Path, str]) -> str:
    identity = hashlib.sha256()
    identity.update((source + "\n" + package_version + "\n").encode("utf-8"))
    for relative, digest in files.items():
        identity.update((relative.as_posix() + "\n" + digest + "\n").encode("utf-8"))
    return identity.hexdigest()


def _file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _installation_snapshot(source: Path, package_version: str) -> tuple[str, dict[Path, str]]:
    """Identify the installed Pvwattsv8 runtime without copying other models."""
    extension = next(
        (source / ("Pvwattsv8" + suffix) for suffix in EXTENSION_SUFFIXES
         if (source / ("Pvwattsv8" + suffix)).is_file()),
        None,
    )
    if extension is None:
        raise RuntimeError("Installed PySAM has no compatible Pvwattsv8 extension.")
    required = [source / "__init__.py", source / "version.py", extension]
    required.extend(sorted(path for path in source.iterdir() if path.suffix.lower() == ".dll"))
    defaults = sorted((source / "defaults").glob("pvwattsv8_*.df"))
    if not (source / "SAM_api.dll").is_file() or not (source / "ssc.dll").is_file():
        raise RuntimeError("Installed PySAM is missing SAM_api.dll or ssc.dll.")
    if not (source / "defaults" / "pvwattsv8_pvwattsnone.df").is_file():
        raise RuntimeError("Installed PySAM is missing the PVWattsNone defaults file.")
    required.extend(defaults)
    files: dict[Path, str] = {}
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"Installed PySAM is missing required file: {path.name}")
        relative = path.relative_to(source)
        files[relative] = _file_digest(path)
    return _snapshot_identity(str(source.resolve()), package_version, files), files


def _reject_links(path: Path) -> None:
    # Check ancestors too: a real leaf can sit below a junction to another disk.
    for entry in (path, *path.parents):
        if entry.is_symlink() or entry.is_junction():
            raise RuntimeError("PySAM runtime cache must contain real paths, not links.")


def _real_directory(path: Path) -> None:
    _reject_links(path)
    path.mkdir(parents=True, exist_ok=True)
    _reject_links(path)
    if not str(path.resolve()).isascii():
        raise RuntimeError("PySAM runtime cache resolves to a non-ASCII physical path.")


def _runtime_root(*, create: bool = True) -> Path:
    setting = next((name for name in ("GUANGZHU_NATIVE_CACHE", "PUBLIC") if name in os.environ), "SYSTEMDRIVE")
    configured = os.environ.get(setting)
    # AGH inherits SYSTEMDRIVE through the MCP SDK whitelist, but not PUBLIC.
    if setting == "SYSTEMDRIVE" and configured:
        configured = str(Path(configured + "\\") / "Users" / "Public")
    if not configured or not configured.isascii() or not Path(configured).is_absolute():
        raise RuntimeError(f"{setting} must be an absolute ASCII path for the PySAM runtime cache.")
    root = Path(configured)
    if setting != "GUANGZHU_NATIVE_CACHE":
        root = root / "Documents" / "guangzhu-runtime"
    try:
        _reject_links(root)
        if not str(root.resolve()).isascii():
            raise RuntimeError(f"{setting} resolves to a non-ASCII physical path.")
        if create:
            _real_directory(root)
    except OSError as error:
        raise RuntimeError(f"Cannot create or access the ASCII PySAM runtime cache configured by {setting}.") from error
    return root.resolve()


def _cache_files(installation: Path, root: Path) -> set[Path]:
    """Inventory without traversing links, and reject unexpected directories."""
    result: set[Path] = set()
    pending = [installation]
    while pending:
        directory = pending.pop()
        _reject_links(directory)
        if not directory.resolve().is_relative_to(root) or directory.resolve() == root:
            raise RuntimeError("PySAM runtime cache entry resolves outside its cache root.")
        for entry in directory.iterdir():
            _reject_links(entry)
            if not entry.resolve().is_relative_to(root):
                raise RuntimeError("PySAM runtime cache entry resolves outside its cache root.")
            relative = entry.relative_to(installation)
            if entry.is_dir():
                if relative.as_posix() not in {"PySAM", "PySAM/defaults", "PySAM/__pycache__"}:
                    raise RuntimeError("PySAM runtime cache contains an unrecognized directory.")
                pending.append(entry)
            elif entry.is_file():
                result.add(relative)
            else:
                raise RuntimeError("PySAM runtime cache contains an unrecognized file type.")
    return result


def _check_contents(installation: Path, root: Path, files: dict[Path, str], *, complete: bool) -> None:
    expected = {Path("PySAM") / relative for relative in files}
    actual = _cache_files(installation, root)
    extras = actual - expected - {Path(_MANIFEST)}
    if any(not re.fullmatch(r"PySAM/__pycache__/(__init__|version)\.cpython-\d+(?:\.opt-[12])?\.pyc",
                            path.as_posix()) for path in extras):
        raise RuntimeError("PySAM runtime cache contains unrecognized user content.")
    if complete and (not expected.issubset(actual) or any(
        _file_digest(installation / "PySAM" / relative) != digest for relative, digest in files.items()
    )):
        raise RuntimeError("PySAM runtime cache does not match its recorded file digests.")


def _read_manifest(installation: Path) -> tuple[Path, str, dict[Path, str]]:
    manifest = json.loads((installation / _MANIFEST).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("project") != _PROJECT or manifest.get("schema") != 1:
        raise ValueError("Unrecognized PySAM cache manifest.")
    source, package_version, entries = manifest["source"], manifest["version"], manifest["files"]
    if (not isinstance(source, str) or not Path(source).is_absolute()
            or not isinstance(package_version, str) or not package_version
            or not isinstance(entries, dict)):
        raise ValueError("Invalid PySAM cache provenance.")
    files: dict[Path, str] = {}
    for name, digest in entries.items():
        if (not isinstance(name, str) or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not re.fullmatch(r"__init__\.py|version\.py|Pvwattsv8(?:\.[A-Za-z0-9_-]+)*\.(?:pyd|so)|"
                                    r"[A-Za-z0-9_-]+\.dll|defaults/pvwattsv8_[A-Za-z0-9_-]+\.df", name)):
            raise ValueError("Invalid PySAM cache file list.")
        files[Path(name)] = digest
    required = {Path("__init__.py"), Path("version.py"), Path("SAM_api.dll"), Path("ssc.dll"),
                Path("defaults/pvwattsv8_pvwattsnone.df")}
    if (not required.issubset(files) or sum(name.name.startswith("Pvwattsv8.") for name in files) != 1
            or _snapshot_identity(source, package_version, files) != installation.name):
        raise ValueError("PySAM cache manifest does not match its directory identity.")
    return Path(source), package_version, files


def _write_manifest(installation: Path, source: Path, package_version: str, files: dict[Path, str]) -> None:
    manifest = {"project": _PROJECT, "schema": 1, "source": str(source.resolve()),
                "version": package_version, "files": {path.as_posix(): digest for path, digest in files.items()}}
    temporary = installation / (_MANIFEST + ".tmp-" + uuid.uuid4().hex)
    try:
        temporary.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, installation / _MANIFEST)
    finally:
        temporary.unlink(missing_ok=True)


def _mirror(source: Path, identity: str, files: dict[Path, str], package_version: str) -> Path:
    """Reuse matching files; atomically replace absent or changed real copies."""
    if identity != _snapshot_identity(str(source.resolve()), package_version, files):
        raise RuntimeError("PySAM runtime cache identity does not match its source installation.")
    root = _runtime_root()
    installation = root / identity
    target = installation / "PySAM"
    try:
        _real_directory(installation)
        has_manifest = (installation / _MANIFEST).exists()
        if has_manifest:
            _cache_files(installation, root)
            try:
                _read_manifest(installation)
            except (ValueError, KeyError, TypeError) as error:
                raise RuntimeError("Cannot reuse an unrecognized PySAM runtime cache manifest.") from error
            _check_contents(installation, root, files, complete=False)
        elif any(installation.iterdir()):
            # An old cache has no provenance. Adopt it only with a verified live
            # source snapshot; a hash-shaped directory alone is insufficient.
            _check_contents(installation, root, files, complete=True)
        _real_directory(target)
        for relative, digest in files.items():
            destination = target / relative
            _real_directory(destination.parent)
            _reject_links(destination)
            if destination.is_file() and _file_digest(destination) == digest:
                continue
            temporary = destination.with_name(destination.name + ".tmp-" + uuid.uuid4().hex)
            try:
                shutil.copy2(source / relative, temporary)
                if _file_digest(temporary) != digest:
                    raise RuntimeError("PySAM installation changed while preparing its runtime; retry.")
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        if not has_manifest:
            _write_manifest(installation, source, package_version, files)
    except OSError as error:
        raise RuntimeError("Cannot write or verify the ASCII PySAM runtime cache.") from error
    return target.resolve()


def clean_cache(*, all_copies: bool = False) -> list[Path]:
    """Delete verified project copies whose source has gone, or all with opt-in.

    Unmarked legacy copies are kept until a verified source reuse migrates them.
    Unexpected files, invalid manifests and any links cause the copy to be kept.
    """
    root = _runtime_root(create=False)
    if not root.exists():
        return []
    removed = []
    for installation in sorted(root.iterdir()):
        try:
            if not re.fullmatch(r"[0-9a-f]{64}", installation.name):
                continue
            _cache_files(installation, root)
            source, _, files = _read_manifest(installation)
            _check_contents(installation, root, files, complete=True)
            if not all_copies:
                try:
                    source.lstat()
                except FileNotFoundError:
                    pass
                else:
                    continue
            # Recheck immediately before removal; never give rmtree a linked or
            # unbounded path, including links buried below a real directory.
            _check_contents(installation, root, files, complete=True)
            shutil.rmtree(installation)
            removed.append(installation)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            continue
    return removed


def prepare_pysam() -> Path:
    """Return the actual runtime path, retaining DLL search handles until exit.

    Windows PySAM resolves native data files through an ASCII path. A Unicode
    installation therefore receives real copies of the Pvwattsv8 extension,
    package metadata, DLLs, and Pvwattsv8 defaults. The cache identity includes
    source path, installed version, and every selected file's content digest.
    Other PySAM models are outside this runtime's current scope.
    """
    with _PREPARE_LOCK:
        package = importlib.import_module("PySAM")
        if not package.__file__:
            raise RuntimeError("Cannot determine the physical PySAM installation path.")
        source = Path(package.__file__).resolve().parent
        if os.name != "nt":
            return source
        if str(source).isascii():
            target = source
        else:
            package_version = version("nrel-pysam")
            identity, files = _installation_snapshot(source, package_version)
            target = _mirror(source, identity, files, package_version)
        loaded = sys.modules.get("PySAM.Pvwattsv8")
        if loaded is not None and Path(loaded.__file__).resolve().parent != target:
            raise RuntimeError("Prepare PySAM before importing its Pvwattsv8 native extension.")
        directory = str(target)
        if directory not in _DLL_HANDLES:
            try:
                _DLL_HANDLES[directory] = os.add_dll_directory(directory)
            except OSError as error:
                raise RuntimeError("Cannot register the ASCII PySAM DLL search directory.") from error
        package.__path__ = list(dict.fromkeys([directory, str(source)]))
        if package.__spec__ is not None:
            package.__spec__.submodule_search_locations = package.__path__
        importlib.invalidate_caches()
        return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean verified Guangzhu PySAM runtime copies.")
    parser.add_argument("--clean", action="store_true", help="remove copies whose source installation is absent")
    parser.add_argument("--all", action="store_true", help="with --clean, remove all verified project copies")
    arguments = parser.parse_args()
    if not arguments.clean:
        parser.error("--clean is required; use --clean --all to include current installations")
    try:
        removed = clean_cache(all_copies=arguments.all)
    except (OSError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    for path in removed:
        print(f"Removed: {path}")
    print(f"Removed {len(removed)} verified PySAM runtime cache(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
