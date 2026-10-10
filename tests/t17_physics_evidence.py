"""T17 real offline evidence driver; invoke explicitly, never during test discovery.

No comparison algorithm lives here. All layout/edit/analyze/compare work delegates
to the normal backend. 'before' must finish before production source is edited.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version as package_version
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
REAL_COUNTER = time.perf_counter
FROZEN_UTC = "2026-10-04T00:00:00+00:00"
ARCHIVES = {
    "real12-budget": "gz-t16-real12-1004-1219",
    "real04-capacity": "gz-t16-real04-1004-1248",
    "rotated-walkway": "gz-rotated-1004-1226",
}
INPUT_DIRS = (
    "data/demo/weather", "data/demo/yields", "data/cache/weather",
    "data/cache/yields", "data/cache/catalog", "data/catalog",
)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = cls.fromisoformat(FROZEN_UTC)
        return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(root):
    return {p.relative_to(root).as_posix(): sha(p)
            for p in sorted(root.rglob("*")) if p.is_file()}


def source_manifest():
    files = [*ROOT.glob("backend/**/*.py"), ROOT / "requirements.lock.txt",
             ROOT / "requirements.txt", ROOT / "requirements-dev.txt", ROOT / "pyproject.toml"]
    locks = [*ROOT.glob("agh-plugin/**/package-lock.json"), *ROOT.glob("scripts/**/package-lock.json")]
    source_diff = subprocess.check_output(["git", "diff", "HEAD", "--no-ext-diff", "--", "backend"], cwd=ROOT)
    dirty_source = subprocess.check_output(["git", "status", "--porcelain", "--", "backend"], cwd=ROOT, text=True)
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(files + locks)},
        "backend_git_diff_sha256": hashlib.sha256(source_diff).hexdigest(),
        "backend_dirty_tracked_source_status": dirty_source.strip().splitlines(),
        "source_identity_note": "HEAD describes repository ancestry; actual executed source is identified by files and diff hash",
        "python": sys.version,
        "packages": {name: package_version(name) for name in
                     ("numpy", "pandas", "pvlib", "scipy", "shapely", "pydantic", "requests", "NREL-PySAM")},
        "frozen_datetime_utc": FROZEN_UTC,
        "shading_counter": "module-local replacement returning 0; physical computations unchanged",
        "total_timing": "saved original time.perf_counter; real elapsed seconds",
        "driver_sha256": sha(Path(__file__).resolve()),
        "argv": sys.argv,
    }


def offline_environment(stack, work, inputs):
    import requests
    from guangzhu import catalog, economics, electrical, models, mcp_actions
    from guangzhu import project, runtime_diagnostics, shading, weather, yieldsim

    def no_network(*args, **kwargs):
        raise AssertionError("T17 evidence forbids all HTTP requests")

    stack.enter_context(patch.object(requests.Session, "request", no_network))
    stack.enter_context(patch.object(project, "PROJECTS_DIR", work / "projects"))
    stack.enter_context(patch.object(runtime_diagnostics, "LOG_DIR", work / "diagnostics"))
    for module in (models, project, mcp_actions):
        stack.enter_context(patch.object(module, "datetime", FrozenDatetime))
    # Do not patch time.perf_counter on the shared Python time module.
    stack.enter_context(patch.object(shading, "time", SimpleNamespace(perf_counter=lambda: 0.0)))
    for module, cache, demo in ((weather, "weather", "weather"), (yieldsim, "yields", "yields")):
        stack.enter_context(patch.object(module, "CACHE_DIR", inputs / "data/cache" / cache))
        stack.enter_context(patch.object(module, "DEMO_DIR", inputs / "data/demo" / demo))
    stack.enter_context(patch.object(catalog, "CACHE_DIR", inputs / "data/cache/catalog"))
    for module in (catalog, electrical):
        stack.enter_context(patch.object(module, "CATALOG_DIR", inputs / "data/catalog"))
    stack.enter_context(patch.object(economics, "ASSUMPTIONS_PATH", inputs / "data/catalog/assumptions.csv"))


def copy_input_snapshots(output):
    for relative in INPUT_DIRS:
        source = ROOT / relative
        if source.exists():
            shutil.copytree(source, output / "cache-inputs" / relative)
    write(output / "cache-inputs-manifest.json", fingerprint(output / "cache-inputs"))
    templates = output / "template-inputs"
    cases = ROOT / "eval/cases.json"
    (templates / "eval").mkdir(parents=True)
    shutil.copy2(cases, templates / "eval/cases.json")
    copied = {}
    for case in read(cases):
        relative = Path("data/roofs") / case["template"] / "project.json"
        destination = templates / relative
        destination.parent.mkdir(parents=True)
        shutil.copy2(ROOT / relative, destination)
        copied[relative.as_posix()] = sha(destination)
    write(templates / "manifest.json", dict(cases_sha256=sha(cases), templates=copied))


def input_manifest(output):
    manifest = read(output / "cache-inputs-manifest.json")
    for name, digest in manifest.items():
        safe_input_name(name)
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("Invalid cache input digest")
    return manifest


def safe_input_name(name):
    parts = name.split("/")
    forbidden = re.compile(r'[\\:<>"|?*\x00-\x1f]')
    reserved = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
    if not name or PurePosixPath(name).is_absolute():
        raise ValueError("Invalid cache input path")
    for part in parts:
        if part in ("", ".", "..") or part.rstrip(" .") != part or forbidden.search(part) or reserved.match(part):
            raise ValueError("Unsafe cache input path: " + name)
    return name


def checked_archive(archive, manifest):
    entries = archive.infolist()
    seen = set()
    for entry in entries:
        if entry.orig_filename != entry.filename:
            raise ValueError("Cache archive path contains a null character")
        name = safe_input_name(entry.filename)
        key = name.casefold()
        if key in seen:
            raise ValueError("Duplicate cache input path: " + name)
        seen.add(key)
        kind = stat.S_IFMT(entry.external_attr >> 16)
        if entry.is_dir() or kind not in (0, stat.S_IFREG) or entry.external_attr & 0x10:
            raise ValueError("Cache archive accepts regular files only")
        if entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ValueError("Unsupported cache archive entry")
    if {entry.filename for entry in entries} != set(manifest):
        raise ValueError("Cache archive membership differs from manifest")
    for key in seen:
        parts = key.split("/")
        if any("/".join(parts[:index]) in seen for index in range(1, len(parts))):
            raise ValueError("Cache archive file and directory paths conflict")
    for entry in entries:
        digest = hashlib.sha256()
        with archive.open(entry) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != manifest[entry.filename]:
            raise ValueError("Cache input hash differs: " + entry.filename)
    return entries


def cache_representation(output):
    raw = output / "cache-inputs"
    archive = output / "cache.zip"
    if raw.exists() == archive.exists():
        raise ValueError("Expected exactly one raw or archived cache input representation")
    return raw, archive


def assert_inputs(output):
    manifest = input_manifest(output)
    raw, archive = cache_representation(output)
    if raw.exists():
        assert fingerprint(raw) == manifest
    else:
        with zipfile.ZipFile(archive) as contents:
            checked_archive(contents, manifest)


def materialize_inputs(output, destination):
    """Restore immutable inputs only to a fresh short temporary destination."""
    destination = destination.resolve()
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if not destination.is_relative_to(temporary_root) or len(str(destination)) > 80 or destination.exists():
        raise ValueError("Cache restore requires a fresh short OS temporary directory")
    manifest = input_manifest(output)
    raw, archive = cache_representation(output)
    if raw.exists():
        assert fingerprint(raw) == manifest
        shutil.copytree(raw, destination)
    else:
        with zipfile.ZipFile(archive) as contents:
            entries = checked_archive(contents, manifest)
            destination.mkdir(parents=True, exist_ok=False)
            for entry in entries:
                target = destination.joinpath(*PurePosixPath(entry.filename).parts)
                if not target.resolve().is_relative_to(destination):
                    raise ValueError("Cache input escapes temporary directory")
                target.parent.mkdir(parents=True, exist_ok=True)
                with contents.open(entry) as source, target.open("xb") as restored:
                    shutil.copyfileobj(source, restored)
    assert fingerprint(destination) == manifest


def rank_templates(output):
    from guangzhu import layout
    from guangzhu.models import LayoutParams, Project
    cases = read(ROOT / "eval/cases.json")
    assert len(cases) == 24
    rows = []
    for case in cases:
        path = ROOT / "data/roofs" / case["template"] / "project.json"
        record = Project.model_validate(read(path))
        started = REAL_COUNTER()
        design = layout.generate_layout(record, LayoutParams())
        rows.append(dict(case_id=case["id"], template=case["template"],
                         project_sha256=sha(path), params=design.params.model_dump(),
                         modules=len(design.modules), dc_kw=design.statistics["dc_kw"],
                         layout_seconds=REAL_COUNTER() - started))
    rows.sort(key=lambda row: (-row["dc_kw"], row["case_id"]))
    result = dict(method="real layout.generate_layout with identical LayoutParams() for all 24 templates",
                  rows=rows, largest_three=[row["case_id"] for row in rows[:3]])
    write(output / "default-layout-ranking.json", result)
    return result


def archived_base(seed, output):
    from guangzhu import project
    folder = ROOT / "runs" / ARCHIVES[seed]
    outer = read(folder / "run.json")
    capture = (folder / outer["capture"]).resolve()
    assert capture.is_relative_to(folder.resolve())
    manifest = read(capture / "run.json")["artifacts"]
    source = capture / "project"
    identifier = read(source / "project.json")["id"]
    base = 3
    target = project._path(identifier)
    original = output / "original-inputs" / seed
    checked = {}
    relatives = ["project.json", *[f"designs/v{v}.json" for v in range(1, base + 1)]]
    relatives += [p.relative_to(source).as_posix() for p in (source / f"analysis/v{base}").glob("*.json")]
    for relative in relatives:
        path = source / relative
        digest = sha(path)
        assert manifest["project/" + relative] == digest, (seed, relative)
        checked[relative] = digest
        for destination in (target / relative, original / relative):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    record = project.load(identifier)
    record.designs = [f"v{v}" for v in range(1, base + 1)]
    project.save(record)
    assert read(target / f"analysis/v{base}/rules.json")["hard_failed"] == 0
    return identifier, base, dict(kind="verified archive", run=folder.relative_to(ROOT).as_posix(),
                                  capture=outer["capture"], artifact_hashes=checked,
                                  operations=["retain original v1-v3 bytes; truncate project.designs to v1-v3"])


def prepare_seeds(output, work):
    from guangzhu import analysis, mcp_actions, project
    cases = {case["id"]: case for case in read(ROOT / "eval/cases.json")}
    prepared = []
    for seed in ("changzhou-unconstrained", "real12-budget", "real04-capacity", "rotated-walkway", "real03-tilt"):
        operations = []
        if seed in ARCHIVES:
            identifier, base, origin = archived_base(seed, output)
            if seed == "rotated-walkway":
                text, structured = "留2米的检修道路", {"walkway_m_min": 2}
            else:
                case = cases["t12-real-12" if seed == "real12-budget" else "t12-real-04"]
                text, structured = case["text"], case["structured"]
            before_structured = project.load(identifier).requirements.structured.model_dump()
            mcp_actions._set_requirements(identifier, text, structured)
            assert project.load(identifier).requirements.structured.model_dump() == before_structured
            operations.append(dict(action="set_requirements", text=text, structured=structured,
                                   note="normalize archived mojibake text; structured exactly unchanged"))
        elif seed == "changzhou-unconstrained":
            source = ROOT / "data/demo/projects/changzhou-demo"
            shutil.copytree(source, output / "original-inputs" / seed)
            record = project.init(source)
            identifier, base = record.id, 3
            origin = dict(kind="demo v3", path=source.relative_to(ROOT).as_posix(), files=fingerprint(source))
            text = "6年内回本、天窗留空"
            structured = dict(payback_years_max=6, keep_clear_ids=record.requirements.structured.keep_clear_ids)
            mcp_actions._set_requirements(identifier, text, structured)
            operations.append(dict(action="set_requirements", text=text, structured=structured,
                                   note="clear demo walkway/budget/capacity/tilt requirements"))
            assert fingerprint(source) == origin["files"]
        else:
            case = cases["t12-real-03"]
            source = ROOT / "data/roofs" / case["template"]
            shutil.copytree(source, output / "original-inputs" / seed)
            identifier = "t17-real03-tilt"
            mcp_actions._new_project(identifier, case["template"], case["economics"])
            mcp_actions._set_requirements(identifier, case["text"], case["structured"])
            witness = case["witness"]
            base = mcp_actions._generate_layout(identifier, witness["params"])["version"]
            kept = set(witness["kept_module_ids"])
            design = project.load_design(identifier, base)
            removed = [module.id for module in design.modules if module.id not in kept]
            assert kept <= {module.id for module in design.modules}
            ops = [dict(op="set_string_size", modules_per_string=witness["modules_per_string"])]
            if removed:
                ops.append(dict(op="remove_modules", module_ids=removed))
            base = project.edit_design(identifier, base, ops, "T17 seed：按公开 witness 构造通过基线", "agent")["version"]
            origin = dict(kind="case witness via normal APIs", case_id=case["id"],
                          cases_sha256=sha(ROOT / "eval/cases.json"), template_files=fingerprint(source), witness=witness)
            operations += [dict(action="new_project", template=case["template"], economics=case["economics"]),
                           dict(action="set_requirements", text=case["text"], structured=case["structured"]),
                           dict(action="generate_layout", params=witness["params"]),
                           dict(action="edit_design", ops=ops, version=base)]
        started = REAL_COUNTER()
        summary = analysis.analyze(identifier, base, offline=True)
        seconds = REAL_COUNTER() - started
        checked = read(project._path(identifier, f"analysis/v{base}/rules.json"))
        assert checked["hard_failed"] == 0, (seed, summary["rules"])
        assert not [row["id"] for row in checked["items"] if row["source_type"] == "用户要求" and row["status"] == "fail"]
        target = output / "seeds" / seed
        shutil.copytree(project._path(identifier), target)
        operations.append(dict(action="analyze", version=base, offline=True, seconds=seconds))
        prepared.append(dict(seed=seed, project_id=identifier, base_version=base, origin=origin,
                             operations=operations, base_summary=summary, files=fingerprint(target)))
        print(json.dumps(dict(prepared=seed, base_version=base, base_analysis_seconds=seconds), ensure_ascii=False), flush=True)
    write(output / "seed-manifest.json", prepared)
    return prepared


def compare_phase(output, phase, work, seeds):
    from guangzhu import analysis, mcp_actions, project, shading
    results = []
    for entry in seeds:
        seed, identifier, base = entry["seed"], entry["project_id"], entry["base_version"]
        source = output / "seeds" / seed
        assert fingerprint(source) == entry["files"], seed
        destination = project._path(identifier)
        shutil.copytree(source, destination)
        analyzed, caches = [], []
        actual_analyze, actual_cache = analysis.analyze, shading.RemovalShading.__init__

        def observed_analyze(project_id, version, *args, **kwargs):
            analyzed.append(dict(project_id=project_id, version=version))
            return actual_analyze(project_id, version, *args, **kwargs)

        def observed_cache(self, record, design, *args, **kwargs):
            caches.append(dict(tilt_deg=design.params.tilt_deg, params=design.params.model_dump(), modules=len(design.modules)))
            return actual_cache(self, record, design, *args, **kwargs)

        started = REAL_COUNTER()
        try:
            with patch.object(analysis, "analyze", observed_analyze), patch.object(shading.RemovalShading, "__init__", observed_cache):
                result = mcp_actions._compare_options(identifier, base, offline=True)
        except BaseException as error:
            failure = output / phase / seed / "failure"
            shutil.copytree(destination, failure / "project")
            if (work / "diagnostics").exists():
                shutil.copytree(work / "diagnostics", failure / "diagnostics")
            write(failure / "failure.json", dict(seed=seed, project_id=identifier, base_version=base,
                                                  complete=False, exception_type=type(error).__name__,
                                                  error_code=getattr(error, "error_code", None),
                                                  traceback=traceback.format_exc(),
                                                  partial_elapsed_seconds=REAL_COUNTER() - started,
                                                  analyze_calls=analyzed, removal_caches=caches,
                                                  project_files=fingerprint(destination)))
            raise
        seconds = REAL_COUNTER() - started
        evidence = output / phase / seed
        shutil.copytree(destination, evidence / "project")
        encoded = analysis.serialized(result).encode("utf-8")
        (evidence / "return.utf8.json").write_bytes(encoded)
        new_files = {name: digest for name, digest in fingerprint(destination).items() if name not in entry["files"]}
        assert all(sha(destination / name) == digest for name, digest in entry["files"].items() if name.startswith("designs/"))
        details = []
        for option in result["options"]:
            version = option["version"]
            final = project.load_design(identifier, version)
            chain = []
            design = final
            while design.version != base:
                assert design.author == "agent" and design.parent_version is not None
                assert design.parent_version < design.version
                chain.append(dict(version=design.version, parent_version=design.parent_version,
                                  author=design.author, reason=design.reason, modules=len(design.modules)))
                design = project.load_design(identifier, design.parent_version)
            checked = read(destination / f"analysis/v{version}/rules.json")
            details.append(dict(name=option["name"], version=version, modules=len(final.modules),
                                chain=chain, g03=next(row for row in checked["items"] if row["id"] == "G03")))
        row = dict(seed=seed, project_id=identifier, base_version=base, seconds=seconds,
                   result=result, utf8_bytes=len(encoded), new_files=new_files,
                   project_files=fingerprint(destination), analyze_calls=analyzed,
                   removal_caches=caches, final_options=details,
                   current_not_reanalyzed=all(call["version"] != base for call in analyzed))
        write(evidence / "evidence.json", row)
        results.append(row)
        print(json.dumps(dict(phase=phase, seed=seed, seconds=seconds, utf8_bytes=len(encoded)), ensure_ascii=False), flush=True)
    write(output / phase / "results.json", results)
    return results


def verify_after(output):
    before = {row["seed"]: row for row in read(output / "before/results.json")}
    after = {row["seed"]: row for row in read(output / "after/results.json")}
    checks = []
    for seed, row in after.items():
        assert row["utf8_bytes"] <= 2048, (seed, row["utf8_bytes"])
        assert row["current_not_reanalyzed"], seed
        current = row["result"]["current"]
        assert current["version"] == row["base_version"]
        original = read(output / "seeds" / seed / f"analysis/v{row['base_version']}/summary.json")
        base_design = read(output / "seeds" / seed / f"designs/v{row['base_version']}.json")
        expected = dict(tilt_deg=base_design["params"]["tilt_deg"], dc_kw=original["dc_kw"],
                        annual_kwh=original["yield_kwh"]["p50"], capex_cny=original["economics"]["capex_cny"],
                        payback_years=original["economics"]["payback_years"], irr_pct=original["economics"]["irr_pct"],
                        avg_loss_pct=original["shading"]["avg_loss_pct"], hard_pass=True, violated_requirements=[])
        assert {key: current[key] for key in expected} == expected, (seed, current, expected)
        assert current["kwh_per_kw"] == round(original["yield_kwh"]["p50"] / original["dc_kw"], 4)
        cached_tilts = [cache["tilt_deg"] for cache in row["removal_caches"]]
        assert len(cached_tilts) == len(set(cached_tilts)), (seed, cached_tilts)
        for option in row["result"]["options"]:
            if seed != "changzhou-unconstrained":
                assert option["hard_pass"] is True and option["violated_requirements"] == [], (seed, option)
            if seed == "real12-budget":
                assert option["capex_cny"] <= 1800000
            if seed == "real04-capacity":
                assert option["dc_kw"] <= 800
            if seed == "real03-tilt":
                assert 15 <= option["tilt_deg"] <= 25
        for final in row["final_options"]:
            required_rule = {"real12-budget": "U03", "real04-capacity": "U02"}.get(seed)
            if required_rule:
                assert any(required_rule in node["reason"] for node in final["chain"]), (seed, final)
            for node in final["chain"]:
                parent_path = output / "after" / seed / "project" / f"designs/v{node['parent_version']}.json"
                child_path = output / "after" / seed / "project" / f"designs/v{node['version']}.json"
                parent, child = read(parent_path), read(child_path)
                walkway_changed = any(parent["params"][key] != child["params"][key]
                                      for key in ("walkway_every_n_rows", "walkway_width_m"))
                if walkway_changed:
                    assert "G03" in node["reason"], (seed, node)
                if "U02" in node["reason"] or "U03" in node["reason"]:
                    removed = len(parent["modules"]) - len(child["modules"])
                    stated = re.search(r"删除\s*(\d+)\s*块", node["reason"])
                    assert removed > 0 and stated and int(stated[1]) == removed, (seed, node, removed)
        if seed == "rotated-walkway":
            assert all(final["g03"]["status"] == "pass" and final["g03"]["value"] >= 1.998
                       for final in row["final_options"])
        checks.append(dict(seed=seed, constraints_pass=True, utf8_bytes=row["utf8_bytes"],
                           before_seconds=before[seed]["seconds"], after_seconds=row["seconds"]))
    seed = "changzhou-unconstrained"
    legacy = {key: value for key, value in after[seed]["result"].items() if key not in ("current", "recommended")}
    assert legacy == before[seed]["result"]
    # All generated design and complete shading bytes, including metadata/hash.
    selected = lambda row: {name: digest for name, digest in row["new_files"].items()
                            if name.startswith("designs/") or name.endswith("/shading.json")}
    assert selected(before[seed]) == selected(after[seed])
    verified = dict(checks=checks, unconstrained_legacy_return_exact=True,
                    unconstrained_new_designs_and_shading_bytes_exact=True)
    path = output / "after/verification.json"
    if path.exists():
        assert read(path) == verified
    else:
        write(path, verified)


def largest_three_sizes(output, work):
    from guangzhu import analysis, mcp_actions, project
    chosen = read(output / "default-layout-ranking.json")["largest_three"]
    cases = {case["id"]: case for case in read(output / "template-inputs/eval/cases.json")}
    existing = {"t12-real-12": "real12-budget", "t12-real-04": "real04-capacity"}
    size_rows = []
    for case_id in chosen:
        if case_id in existing:
            entry = read(output / "after" / existing[case_id] / "evidence.json")
            size_rows.append(dict(case_id=case_id, reused_evidence=f"after/{existing[case_id]}/evidence.json",
                                  utf8_bytes=entry["utf8_bytes"], seconds=entry["seconds"], result=entry["result"]))
            continue
        case = cases[case_id]
        relative = Path("data/roofs") / case["template"] / "project.json"
        assert sha(ROOT / relative) == sha(output / "template-inputs" / relative)
        identifier = "t17-size-" + case_id
        mcp_actions._new_project(identifier, case["template"], case["economics"])
        mcp_actions._set_requirements(identifier, case["text"], case["structured"])
        witness = case["witness"]
        base = mcp_actions._generate_layout(identifier, witness["params"])["version"]
        design = project.load_design(identifier, base)
        kept = set(witness["kept_module_ids"])
        assert kept <= {module.id for module in design.modules}
        removed = [module.id for module in design.modules if module.id not in kept]
        ops = [dict(op="set_string_size", modules_per_string=witness["modules_per_string"])]
        if removed:
            ops.append(dict(op="remove_modules", module_ids=removed))
        base = project.edit_design(identifier, base, ops, "T17 2KB seed：正常接口复现公开 witness", "agent")["version"]
        summary = analysis.analyze(identifier, base, offline=True)
        assert summary["rules"]["hard_failed"] == 0
        seed_dir = output / "size-seeds" / case_id
        shutil.copytree(project._path(identifier), seed_dir)
        started = REAL_COUNTER()
        try:
            result = mcp_actions._compare_options(identifier, base, offline=True)
        except BaseException as error:
            failure = output / "after/sizes" / case_id / "failure"
            shutil.copytree(project._path(identifier), failure / "project")
            write(failure / "failure.json", dict(case_id=case_id, project_id=identifier, base_version=base,
                                                  complete=False, exception_type=type(error).__name__,
                                                  error_code=getattr(error, "error_code", None),
                                                  traceback=traceback.format_exc(),
                                                  partial_elapsed_seconds=REAL_COUNTER() - started))
            raise
        seconds = REAL_COUNTER() - started
        contents = analysis.serialized(result).encode("utf-8")
        destination = output / "after/sizes" / case_id
        shutil.copytree(project._path(identifier), destination / "project")
        (destination / "return.utf8.json").write_bytes(contents)
        assert len(contents) <= 2048, (case_id, len(contents))
        row = dict(case_id=case_id, project_id=identifier, base_version=base, seed_files=fingerprint(seed_dir),
                   normal_preparation=dict(case=case, edit_ops=ops, offline_base_summary=summary),
                   utf8_bytes=len(contents), seconds=seconds, result=result,
                   project_files=fingerprint(destination / "project"))
        write(destination / "evidence.json", row)
        size_rows.append(row)
        print(json.dumps(dict(size_case=case_id, seconds=seconds, utf8_bytes=len(contents))), flush=True)
    assert len(size_rows) == 3 and all(row["utf8_bytes"] <= 2048 for row in size_rows)
    write(output / "after/largest-three-size-results.json", size_rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.phase == "verify":
        assert_inputs(output)
        verify_after(output)
        return
    if args.phase == "before":
        output.mkdir(parents=True, exist_ok=False)
        write(output / "before/source-manifest.json", source_manifest())
        shutil.copy2(Path(__file__).resolve(), output / "before/driver.py.txt")
        copy_input_snapshots(output)
    else:
        assert output.exists() and not (output / "after").exists()
        write(output / "after/source-manifest.json", source_manifest())
        shutil.copy2(Path(__file__).resolve(), output / "after/driver.py.txt")
    source_before = source_manifest()
    assert_inputs(output)
    # Persistent evidence contains immutable input copies; every computation
    # writes exclusively into a fresh OS temporary project/diagnostic tree.
    with tempfile.TemporaryDirectory(prefix="t17-") as temporary:
        work = Path(temporary)
        scratch_inputs = work / "inputs"
        materialize_inputs(output, scratch_inputs)
        with ExitStack() as stack:
            offline_environment(stack, work, scratch_inputs)
            if args.phase == "before":
                rank_templates(output)
                seeds = prepare_seeds(output, work)
                # A second temporary project root starts compare from frozen seeds.
                compare_work = work / "comparisons"
                from guangzhu import project
                with patch.object(project, "PROJECTS_DIR", compare_work / "projects"):
                    compare_phase(output, "before", compare_work, seeds)
            else:
                compare_phase(output, "after", work, read(output / "seed-manifest.json"))
                largest_three_sizes(output, work)
        assert fingerprint(scratch_inputs) == read(output / "cache-inputs-manifest.json")
    assert source_manifest()["files"] == source_before["files"], "Source changed during physics capture"
    assert_inputs(output)
    write(output / args.phase / "completion.json", dict(complete=True, temporary_directory_removed=not work.exists(),
                                                        network_requests=0, agh_started=False, model_requests=0,
                                                        source_files_unchanged_during_capture=True))
    if args.phase == "after":
        verify_after(output)


if __name__ == "__main__":
    main()
