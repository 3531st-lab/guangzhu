"""Replay six default layouts and offline analysis; compare files and fields."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from guangzhu import analysis, layout, project, shading

ROOFS = ("changzhou-demo", "l-shape", "rotated", "south-tower", "metal-demo-s", "metal-demo-n")


def canonical(value):
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()
                if key not in {"created_at", "elapsed_seconds", "elapsed_s", "duration_seconds"}}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    return value


def differences(before, after, field="$"):
    if type(before) is not type(after):
        return [field.strip()]
    if isinstance(before, dict):
        return [path for key in sorted(before.keys() | after.keys())
                for path in ([field.strip() + "." + key] if key not in before or key not in after
                             else differences(before[key], after[key], field.strip() + "." + key))]
    if isinstance(before, list) and len(before) == len(after):
        return [path for i, (a, b) in enumerate(zip(before, after)) for path in differences(a, b, f"{field.strip()}[{i}]")]
    return [] if before == after else [field.strip()]


def reference_manifest(path):
    manifest = path if path.is_file() else path / 'manifest.json'
    hashes = json.loads(manifest.read_text(encoding='utf-8'))
    for name, expected in hashes.items():
        if Path(name).name != name or not name.endswith('.json'):
            raise ValueError(f'Invalid baseline filename: {name}')
        payload = (manifest.parent / name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError(f'Baseline checksum mismatch: {name}')
    return manifest.parent, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest, changed = {}, {}
    reference, expected = reference_manifest(args.compare) if args.compare else (None, {})
    required = {f'{name}-{kind}.json' for name in ROOFS for kind in ('layout', 'summary', 'electrical', 'economics')}
    if args.compare and expected.keys() != required:
        raise ValueError('Baseline manifest entries differ: ' + ','.join(sorted(expected.keys() ^ required)))
    with ExitStack() as stack:
        stack.enter_context(patch.object(project, "PROJECTS_DIR", (args.work or args.output) / "projects"))
        stack.enter_context(patch.object(shading, "time", SimpleNamespace(perf_counter=lambda: 0)))
        for name in ROOFS:
            source = ROOT / "data/demo/projects" / name
            instance = project.init(source, "baseline-" + name)
            design = layout.generate_layout(instance, {})
            design.created_at = datetime(2026, 10, 6, tzinfo=timezone.utc)
            project.save_design(instance.id, design)
            summary = analysis.analyze(instance.id, design.version, offline=True)
            records = {"layout": design.model_dump(exclude={"created_at"}), "summary": summary}
            for kind in ("electrical", "economics"):
                path = project._path(instance.id, f"analysis/v{design.version}/{kind}.json")
                records[kind] = json.loads(path.read_text(encoding="utf-8"))
            for kind, record in records.items():
                filename = name + "-" + kind + ".json"
                data = (json.dumps(canonical(record), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                (args.output / filename).write_bytes(data)
                manifest[filename] = hashlib.sha256(data).hexdigest()
                if args.compare:
                    if filename not in expected:
                        raise ValueError(f'Baseline manifest missing: {filename}')
                    old = (reference / filename).read_bytes()
                    if data != old:
                        changed[filename] = differences(json.loads(old), json.loads(data))
            print(name, len(design.modules), summary["ok"], flush=True)
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if args.compare and manifest.keys() != expected.keys():
        raise ValueError('Baseline manifest contains unexpected files: ' + ','.join(sorted(expected.keys() - manifest.keys())))
    print(json.dumps(dict(changed=changed), ensure_ascii=False), flush=True)
    return bool(changed)


if __name__ == "__main__":
    raise SystemExit(main())
