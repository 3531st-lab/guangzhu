"""Official SDK acceptance. Set T16_FULL_SDK=1 to opt in to sequential real calculations.

T16_SDK_EVIDENCE_DIR optionally copies evidence to reports/assets/T16/sdk.
Without it, all evidence stays under pytest's temporary directory.
"""
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from unittest.mock import patch

import anyio
from mcp import ClientSession
from mcp.client import stdio as transport
from mcp.client.stdio import StdioServerParameters, stdio_client
import pytest
import requests

from guangzhu import mcp_actions, mcp_server, project as storage, runtime_diagnostics
from guangzhu.config import ROOT
from guangzhu.models import validate_project
from scripts.mcp_smoke import AGH_ENV

FULL = pytest.mark.skipif(os.environ.get("T16_FULL_SDK") != "1", reason="opt in with T16_FULL_SDK=1")
ROOFS = ("t12-real-04", "t12-real-12", "rectangle-5000")


def serialized(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(serialized(value).encode("utf-8")).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


class Evidence:
    def __init__(self, path, name):
        self.path = path
        self.name = name
        self.started = time.perf_counter()
        self.data = dict(case=name, model_requests=0, agh_started=False, network_disabled=True,
                         sdk_timeout_seconds=60, maximum_request_seconds=45, sessions=[], direct=[])
        self.flush()

    def flush(self):
        self.data["total_elapsed_seconds"] = time.perf_counter() - self.started
        write_json(self.path, self.data)
        destination = os.environ.get("T16_SDK_EVIDENCE_DIR")
        if destination:
            target = Path(destination).resolve()
            assert target == (ROOT / "reports/assets/T16/sdk").resolve()
            write_json(target / (self.name + ".json"), self.data)


def forbid_network(*args, **kwargs):
    raise AssertionError("T16 SDK acceptance forbids network requests")


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    assert not tmp_path.resolve().is_relative_to(ROOT.resolve()), "use pytest temp outside the repository"
    monkeypatch.setattr(requests.Session, "request", forbid_network)
    monkeypatch.setattr(runtime_diagnostics, "LOG_DIR", tmp_path / "direct-diagnostics")
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "unused-projects")
    return tmp_path


def prepare(root, name, *, small=False):
    source = ROOT / ("data/demo/projects/changzhou-demo/project.json" if small or name == "rectangle-5000"
                     else f"data/roofs/{name}/project.json")
    payload = read_json(source)
    payload.update(id=name, designs=[])
    if small or name == "rectangle-5000":
        width, height = (8, 8) if small else (180, 135)
        payload["roof"].update(outline=[[0, 0], [width, 0], [width, height], [0, height]],
                               obstacles=[], keepouts=[], underlay=None)
        payload["requirements"] = dict(text="测试内生成的矩形屋顶", structured={})
    with patch.object(storage, "PROJECTS_DIR", root):
        storage.save(validate_project(payload))
        generated = mcp_actions._generate_layout(name, {})
        mcp_actions._analyze(name, generated["version"], offline=True)
    if name == "rectangle-5000":
        assert 4500 <= generated["modules"] <= 5500
    return generated


def clone_baseline(source, destination, name):
    assert not destination.exists()
    shutil.copytree(source / name, destination / name)
    before = {p.relative_to(source / name).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in (source / name).rglob("*") if p.is_file()}
    after = {p.relative_to(destination / name).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in (destination / name).rglob("*") if p.is_file()}
    assert before == after
    return before


def direct(root, evidence, tool, **args):
    started = time.perf_counter()
    with patch.object(storage, "PROJECTS_DIR", root):
        result = mcp_actions.ACTIONS[tool](**args)
    evidence.data["direct"].append(dict(tool=tool, arguments=args, seconds=time.perf_counter() - started,
                                       result_sha256=digest(result), result=result))
    evidence.flush()
    return result


class SDK:
    def __init__(self, client, evidence, session):
        self.client = client
        self.evidence = evidence
        self.session = session

    async def request(self, name, arguments, *, error=False):
        started = time.perf_counter()
        record = dict(tool=name, arguments=arguments)
        self.session["requests"].append(record)
        try:
            response = await self.client.call_tool(name, arguments, read_timeout_seconds=60)
        except BaseException as exc:
            record.update(seconds=time.perf_counter() - started, exception=type(exc).__name__)
            self.evidence.flush()
            raise
        elapsed = time.perf_counter() - started
        assert len(response.content) == 1 and response.content[0].type == "text"
        value = json.loads(response.content[0].text)
        record.update(seconds=elapsed, result=value, result_sha256=digest(value), is_error=response.is_error,
                      pending=value.get("pending", False), stage=value.get("stage"), job_id=value.get("job_id"))
        self.evidence.flush()
        assert elapsed <= 45, record
        assert response.is_error == error, record
        assert value["ok"] == (not error), record
        return value

    async def finish(self, value, tool):
        job_id = value.get("job_id")
        while value.get("pending") is True:
            assert value["tool"] == tool and value["job_id"] == job_id
            value = await self.request("gz_wait", dict(job_id=job_id))
        if job_id is not None:
            value = dict(value)
            assert value.pop("tool") == tool
            assert value.pop("job_id") == job_id
        return value

    async def calculate(self, tool, args):
        started = time.perf_counter()
        initial = await self.request(tool, args)
        pending = initial.get("pending") is True
        result = await self.finish(dict(initial), tool)
        row = dict(tool=tool, seconds=time.perf_counter() - started, pending=pending, result_sha256=digest(result))
        self.session.setdefault("calculations", []).append(row)
        self.evidence.flush()
        return result, pending


@asynccontextmanager
async def connect(root, scratch, evidence, label, *, wait=None):
    assert Path(sys.executable).resolve() == (ROOT / ".venv/Scripts/python.exe").resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    launch = scratch / "launch.json"
    environment = {key: os.environ[key] for key in AGH_ENV}
    args = [str(ROOT / "tests/_t16_sdk_launcher.py"), "--launch-evidence", str(launch),
            "--diagnostics-dir", str(scratch / "diagnostics"), "--projects-dir", str(root), "--offline"]
    if wait is not None:
        args += ["--test-wait-seconds", str(wait)]
    parameters = StdioServerParameters(command=sys.executable, args=args, env=environment, cwd=scratch)
    session = dict(label=label, requests=[], started_unix=time.time())
    evidence.data["sessions"].append(session)
    started = time.perf_counter()
    try:
        with patch.object(transport, "get_default_environment", lambda: {}):
            async with stdio_client(parameters) as streams:
                async with ClientSession(*streams, read_timeout_seconds=60) as client:
                    await client.initialize()
                    session["launch"] = read_json(launch)
                    assert set(session["launch"]["environment_keys"]) == set(AGH_ENV)
                    assert Path(session["launch"]["cwd"]).resolve() == scratch.resolve()
                    assert not scratch.resolve().is_relative_to(ROOT.resolve())
                    assert Path(session["launch"]["source"]).resolve() == ROOT / "backend/guangzhu/mcp_server.py"
                    assert session["launch"]["wait_seconds"] == (40 if wait is None else wait)
                    evidence.flush()
                    yield SDK(client, evidence, session)
    finally:
        session["total_seconds"] = time.perf_counter() - started
        session["diagnostics"] = [read_json_lines(p) for p in sorted((scratch / "diagnostics").glob("*.jsonl"))]
        evidence.flush()


def read_json_lines(path):
    return dict(filename=path.name, records=[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()])


def design_records(root, name):
    result = {}
    for path in sorted((root / name / "designs").glob("v*.json"), key=lambda path: int(path.stem[1:])):
        record = read_json(path)
        record.pop("created_at")
        result[record["version"]] = record
    return result


def compare_designs(expected_root, actual_root, name, options):
    expected, actual = design_records(expected_root, name), design_records(actual_root, name)
    assert serialized(actual) == serialized(expected)
    chains = {}
    for option in options["options"]:
        cursor, chain = option["version"], []
        while cursor != options["base_version"]:
            assert cursor not in chain
            chain.append(cursor)
            cursor = actual[cursor]["parent_version"]
            assert cursor is not None
        chains[option["name"]] = [*chain, cursor]
    return dict(normalized_sha256=digest(actual), ignored_fields=["created_at"], parent_chains=chains,
                versions=sorted(actual), component_counts={version: len(row["modules"]) for version, row in actual.items()})


def test_sdk_entry_probe(isolated):
    evidence = Evidence(isolated / "probe.json", "probe")
    projects = isolated / "probe-projects"
    generated = prepare(projects, "sdk-probe", small=True)
    async def check():
        async with connect(projects, isolated / "stdio", evidence, "production") as sdk:
            listing = await sdk.client.list_tools()
            assert len(listing.tools) == 12
            assert next(tool for tool in listing.tools if tool.name == "gz_wait").annotations.read_only_hint is True
            summary, pending = await sdk.calculate("gz_project_summary", dict(project_id="sdk-probe"))
            assert summary["modules"] == generated["modules"] and summary["versions"] == ["v1"]
            assert not pending
    anyio.run(check)
    evidence.data["accepted"] = True
    evidence.flush()
    print(f"T16 SDK probe evidence: {evidence.path}")


@FULL
@pytest.mark.parametrize("name", ROOFS)
def test_large_jobs(isolated, name):
    evidence = Evidence(isolated / (name + ".json"), name)
    baseline, original, queued = (isolated / key for key in ("baseline", "direct", "sdk"))
    generated = prepare(baseline, name)
    evidence.data["baseline"] = dict(modules=generated["modules"], version=generated["version"],
                                    files=clone_baseline(baseline, original, name))
    assert clone_baseline(baseline, queued, name) == evidence.data["baseline"]["files"]
    compare_args = dict(project_id=name, base_version=generated["version"], offline=True)
    analyze_args = dict(project_id=name, version=generated["version"], offline=True)
    expected_options = direct(original, evidence, "gz_compare_options", **compare_args)
    expected_analysis = direct(original, evidence, "gz_analyze", **analyze_args)
    async def check():
        async with connect(queued, isolated / "production", evidence, "production-40s") as sdk:
            actual_options, compare_pending = await sdk.calculate("gz_compare_options", compare_args)
            assert serialized(actual_options) == serialized(expected_options)
            evidence.data["design_comparison"] = compare_designs(original, queued, name, actual_options)
            evidence.flush()
            if name == "t12-real-12":
                assert compare_pending, "real-12 must genuinely exceed production 40 seconds"
            actual_analysis, _ = await sdk.calculate("gz_analyze", analyze_args)
            assert serialized(actual_analysis) == serialized(expected_analysis)
        forced = isolated / "forced"
        clone_baseline(baseline, forced, name)
        async with connect(forced, isolated / "short-wait", evidence, "test-only-1s", wait=1) as sdk:
            if not compare_pending:
                forced_options, pending = await sdk.calculate("gz_compare_options", compare_args)
                assert pending and serialized(forced_options) == serialized(expected_options)
                compare_designs(original, forced, name, forced_options)
            forced_analysis, pending = await sdk.calculate("gz_analyze", analyze_args)
            assert pending and serialized(forced_analysis) == serialized(expected_analysis)
    anyio.run(check)
    evidence.data["accepted"] = True
    evidence.flush()
    print(f"T16 SDK full acceptance evidence: {evidence.path}")


@FULL
def test_real_stdio_queue_cancel_and_restart(isolated):
    evidence = Evidence(isolated / "queue.json", "queue")
    projects, name = isolated / "queue-projects", "sdk-queue"
    prepare(projects, name, small=True)
    reference = isolated / "queue-reference"
    clone_baseline(projects, reference, name)
    args = dict(project_id=name, base_version=1, offline=True)
    expected = direct(reference, evidence, "gz_compare_options", **args)
    async def check():
        async with connect(projects, isolated / "queue-stdio", evidence, "test-only-0.02s", wait=.02) as sdk:
            pending = await sdk.request("gz_compare_options", args)
            assert pending["pending"] is True
            queued = await sdk.request("gz_project_summary", dict(project_id=name))
            assert queued["pending"] is True and queued["stage"] == "排队中，等待前面的计算完成"
            duplicate = await sdk.request("gz_compare_options", args)
            assert duplicate["job_id"] == pending["job_id"]
            with anyio.move_on_after(.005) as scope:
                await sdk.request("gz_wait", dict(job_id=pending["job_id"]))
            assert scope.cancel_called, "real SDK waiting request must actually be cancelled"
            result = await sdk.finish(dict(pending), "gz_compare_options")
            summary = await sdk.finish(dict(queued), "gz_project_summary")
            assert serialized(result) == serialized(expected)
            expected_versions = read_json(reference / name / "project.json")["designs"]
            assert summary["versions"] == expected_versions
            reused = await sdk.request("gz_compare_options", args)
            assert serialized(reused) == serialized(result)
            evidence.data["design_comparison"] = compare_designs(reference, projects, name, result)
            assert read_json(projects / name / "project.json")["designs"] == expected_versions
            evidence.data["queue_checks"] = dict(same_job_id=pending["job_id"], cancellation_survived=True,
                                                summary_not_busy=True, no_extra_versions=True)
        async with connect(projects, isolated / "restart", evidence, "restarted-production-40s") as sdk:
            unknown = await sdk.request("gz_wait", dict(job_id=pending["job_id"]), error=True)
            assert unknown["error_code"] == "JOB_UNKNOWN"
            assert unknown["message_zh"] == "后台计算记录已失效，请按原参数重新调用原工具"
    anyio.run(check)
    evidence.data["accepted"] = True
    evidence.flush()
    print(f"T16 SDK queue evidence: {evidence.path}")
