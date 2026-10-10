"""Exclude host pip launchers and reject development paths before packaging."""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat


TEST_PACKAGES = {'numpy', 'pandas', 'scipy', 'matplotlib', 'h5py', 'pvlib', 'shapely', 'ezdxf', 'pil'}


def removable_test(relative):
    parts = [part.lower() for part in Path(relative).parts]
    protected = any(part.startswith(('license', 'notice', 'copying')) for part in parts)
    return len(parts) > 2 and parts[0] in TEST_PACKAGES and 'tests' in parts[1:-1] and not protected


def contained(stage, target):
    stage = Path(stage).absolute()
    if stage.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f"Reparse staging root: {stage}")
    stage = stage.resolve(strict=True)
    target = Path(target).absolute()
    if not target.resolve().is_relative_to(stage) or target.resolve() == stage:
        raise ValueError(f"Path escaped staging: {target}")
    for item in (target, *target.parents):
        if item.is_symlink() or item.is_junction() or item.exists() and item.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"Reparse path in staging: {item}")
        if item == stage:
            break
    return target


def cleanup_stage(stage):
    stage = Path(stage)
    entries = contained(stage, stage / "runtime/python/Lib/site-packages/bin")
    if entries.exists():
        for item in entries.rglob("*"):
            contained(stage, item)
        shutil.rmtree(entries)
    settings = contained(stage, stage / "desktop/settings.json")
    if settings.exists():
        settings.unlink()
    return trim_tests(stage)


def trim_tests(stage):
    """Remove only upstream test files inside the isolated installer payload."""
    stage = Path(stage)
    site = contained(stage, stage / 'runtime/python/Lib/site-packages')
    candidates = []
    for package in sorted(site.iterdir()):
        if package.name.lower() not in TEST_PACKAGES:
            continue
        contained(stage, package)
        for directory, directories, filenames in os.walk(package, followlinks=False):
            for name in [*directories, *filenames]:
                contained(stage, Path(directory) / name)
            for name in filenames:
                path = Path(directory) / name
                relative = path.relative_to(site)
                if removable_test(relative):
                    candidates.append((path, relative.parts[0], path.stat().st_size))
    # Validate the full candidate tree first; never follow a junction while deleting.
    packages = {}
    for path, package, size in candidates:
        contained(stage, path).unlink()
        entry = packages.setdefault(package, dict(files=0, bytes=0))
        entry['files'] += 1
        entry['bytes'] += size
    return dict(policy='upstream-tests-only-v1', files=len(candidates), bytes=sum(row[2] for row in candidates), packages=packages)


def validate_stage(stage, host_python, developer_root):
    stage = Path(stage).absolute()
    contained(stage, stage / "runtime/python")
    roots = [Path(host_python).resolve().parent, Path(developer_root).resolve()]
    needles = []
    for root in roots:
        for value in (str(root), str(root).replace("\\", "/"), str(root).replace("\\", "\\\\")):
            for encoding in ("utf-8", "utf-16-le"):
                needles.append(value.encode(encoding).lower())
    suffixes = {".py", ".pth", "._pth", ".json", ".cfg", ".ini", ".toml", ".txt", ".md", ".js", ".cmd", ".ps1"}
    checked = 0
    for relative in ("runtime/python", "backend", "desktop", "scripts", "plugins"):
        for item in sorted((stage / relative).rglob("*")):
            contained(stage, item)
            if not item.is_file() or "licenses" in item.parts or item.name.lower().startswith(("license", "notice", "copying")):
                continue
            generated = "site-packages" in item.parts and "bin" in item.parts
            if not generated and item.suffix.lower() not in suffixes:
                continue
            content = item.read_bytes().lower()
            if any(needle in content for needle in needles):
                raise ValueError(f"Host/developer path in installed entry/text: {item.relative_to(stage)}")
            checked += 1
    for relative in ("runtime/python/Lib/site-packages/bin", "runtime/python/Scripts", "desktop/settings.json"):
        if (stage / relative).exists():
            raise ValueError(f"Excluded installed entry remains: {relative}")
    return checked


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("--host-python", type=Path, required=True)
    parser.add_argument("--developer-root", type=Path, required=True)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    if args.clean:
        audit = cleanup_stage(args.stage)
        target = contained(args.stage, args.stage / 'payload-pruning.json')
        target.write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
        print(f"Upstream tests removed from staging only: {audit['files']} files, {audit['bytes']} bytes")
    count = validate_stage(args.stage, args.host_python, args.developer_root)
    print(f"Installed generated entry/text scan passed: {count} files; pip bin/Scripts and settings absent")
