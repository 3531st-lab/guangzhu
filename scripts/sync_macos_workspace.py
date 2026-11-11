"""Synchronize read-only macOS .app payload into user-writable Application Support workspace.

Why this exists on macOS:
- A signed `光筑.app` inside `/Applications` (or mounted from a read-only `.dmg` volume or
  App Translocation path) must never be modified at runtime, otherwise macOS Gatekeeper
  invalidates the bundle signature (`codesign --verify`).
- User projects (`projects/`), runs (`runs/`), custom roofs (`data/myroofs/`), edited parks
  (`data/parks/`), caches (`data/cache/`), and `desktop/settings.json` must survive app upgrades
  when the user drags a new `光筑.app` into `/Applications`.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sys

IMMUTABLE_DIRS = (
    "backend",
    "desktop/web",
    "data/catalog",
    "data/demo",
    "data/roofs",
    "data/showcase",
    "scripts",
    "plugins",
    ".agh",
)

IMMUTABLE_FILES = (
    "desktop/app.py",
    "desktop/settings.example.json",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "build-manifest.json",
)

USER_DIRS = (
    "projects",
    "runs",
    "data/parks",
    "data/myroofs",
    "data/cache",
)


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace_tree(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.is_symlink() or dst.is_symlink():
        raise ValueError(f"Refusing symlink in bundle sync: {src} -> {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = dst.with_name(f".{dst.name}.sync-{os.getpid()}")
    if tmp_dst.exists():
        shutil.rmtree(tmp_dst)
    shutil.copytree(src, tmp_dst, symlinks=False)
    if dst.exists():
        shutil.rmtree(dst)
    tmp_dst.replace(dst)


def _copy_atomic_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        return
    if src.is_symlink() or dst.is_symlink():
        raise ValueError(f"Refusing symlink file in bundle sync: {src} -> {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp_dst = dst.with_name(f".{dst.name}.sync-{os.getpid()}")
    shutil.copy2(src, tmp_dst)
    tmp_dst.replace(dst)


def sync_workspace(payload_root: Path, workspace_root: Path, *, force: bool = False) -> dict:
    """Sync immutable app code/catalogs from payload_root to workspace_root while preserving user data."""
    payload = Path(payload_root).resolve(strict=True)
    workspace = Path(workspace_root).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    for rel in USER_DIRS:
        (workspace / rel).mkdir(parents=True, exist_ok=True)

    src_manifest = payload / "build-manifest.json"
    dst_manifest = workspace / "build-manifest.json"
    src_hash = _sha256_file(src_manifest)
    dst_hash = _sha256_file(dst_manifest)

    needs_sync = (
        force
        or not src_hash
        or src_hash != dst_hash
        or not (workspace / "desktop/app.py").is_file()
        or not (workspace / "backend/guangzhu/api.py").is_file()
    )
    if not needs_sync:
        return {"synced": False, "manifest_sha256": dst_hash, "workspace": str(workspace)}

    # Remove old manifest first so an interrupted copy always retries on next launch.
    if dst_manifest.is_file():
        dst_manifest.unlink()

    for rel_dir in IMMUTABLE_DIRS:
        _replace_tree(payload / rel_dir, workspace / rel_dir)

    for rel_file in IMMUTABLE_FILES:
        if rel_file == "build-manifest.json":
            continue
        _copy_atomic_file(payload / rel_file, workspace / rel_file)

    # Write build-manifest.json last as atomic commit marker.
    _copy_atomic_file(src_manifest, dst_manifest)
    return {"synced": True, "manifest_sha256": _sha256_file(dst_manifest), "workspace": str(workspace)}


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    force = "--force" in args
    positional = [a for a in args if not a.startswith("--")]
    if len(positional) != 2:
        sys.stderr.write("Usage: sync_macos_workspace.py [--force] <payload_dir> <workspace_dir>\n")
        return 2
    sync_workspace(Path(positional[0]), Path(positional[1]), force=force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
