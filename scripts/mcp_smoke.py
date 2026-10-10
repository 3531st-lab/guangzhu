"""Exercise three demos in AGH's exact stdio environment; never run a model/AGH."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import subprocess
from contextlib import chdir
from unittest.mock import patch

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client import stdio as transport
from guangzhu.templates import catalog, resolve

ROOT = Path(__file__).resolve().parents[1]
# AGH 5da4073 mcp-server-opener.ts:153/178, connect.ts:264; MCP TS SDK
# v1.25.2 src/client/stdio.ts getDefaultEnvironment: Windows list, no extra vars.
AGH_ENV = ("APPDATA", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "PATH", "PROCESSOR_ARCHITECTURE",
           "SYSTEMDRIVE", "SYSTEMROOT", "TEMP", "USERNAME", "USERPROFILE", "PROGRAMFILES")


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def hashes(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob("*") if p.is_file()}


async def poll_tool(client, name, arguments):
    started, requests, job_id = time.perf_counter(), [], None
    request_name, request_args = name, arguments
    while True:
        sent = time.perf_counter()
        response = await client.call_tool(request_name, request_args, read_timeout_seconds=60)
        elapsed = time.perf_counter() - sent
        assert elapsed <= 45, (request_name, elapsed)
        assert len(response.content) == 1 and response.content[0].type == "text"
        text = response.content[0].text
        size, result = len(text.encode("utf-8")), json.loads(text)
        assert not response.is_error and result["ok"] is True, (request_name, result)
        requests.append(dict(tool=request_name, arguments=request_args, result=dict(result), bytes=size, seconds=elapsed))
        if result.get("pending") is True:
            assert size <= 2048 and result["tool"] == name
            assert isinstance(result["job_id"], str) and result["job_id"]
            assert job_id is None or result["job_id"] == job_id
            job_id = result["job_id"]
            request_name, request_args = "gz_wait", dict(job_id=job_id)
            continue
        if job_id is None:
            assert "tool" not in result and "job_id" not in result
        else:
            assert result.get("tool") == name and result.get("job_id") == job_id
            result.pop("tool")
            result.pop("job_id")
            body = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            body_size = len(body.encode("utf-8"))
            assert 0 <= size - body_size <= 128
            size = body_size
        assert size <= 2048
        return result, size, time.perf_counter() - started, requests


async def run(projects, *, project_id="changzhou-demo", list_only=False, online=False):
    env = {k: os.environ[k] for k in AGH_ENV if k in os.environ}
    probe_code = ("import os,json,guangzhu\n"
                  "print(json.dumps(dict(environment_keys=sorted(os.environ),cwd=os.getcwd(),source=guangzhu.__file__)))")
    probe = json.loads(subprocess.check_output([sys.executable, "-c", probe_code], env=env, cwd=env["TEMP"], text=True))
    assert set(probe["environment_keys"]) == set(env) == set(AGH_ENV)
    assert Path(probe["source"]).resolve() == ROOT / "backend/guangzhu/__init__.py"
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "guangzhu.mcp_server", "--projects-dir", str(projects)] + ([] if online else ["--offline"]), env=env)
    records, chain, protocol = [], [], {}
    original_parser = transport._parse_line
    def counted_parser(line):
        item = original_parser(line)
        if not isinstance(item, Exception) and "tools" in getattr(item.message, "result", {}):
            raw = (line + "\n").encode("utf-8")
            protocol.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        return item
    class Capture:
        async def __aenter__(self):
            self.scope = patch.multiple(transport, _parse_line=counted_parser, get_default_environment=lambda: {})
            self.scope.start()
            self.cwd = chdir(env["TEMP"])
            self.cwd.__enter__()
        async def __aexit__(self, *args):
            self.cwd.__exit__(*args)
            self.scope.stop()
    started = time.perf_counter()
    async with Capture(), stdio_client(parameters) as streams, ClientSession(*streams) as client:
        await client.initialize()
        handshake = time.perf_counter() - started
        listing = await client.list_tools()
        wire = listing.model_dump_json(by_alias=True, exclude_unset=True)
        tools = json.loads(wire)
        assert len(tools["tools"]) == 12 and protocol["bytes"] <= 12288
        assert next(tool for tool in tools["tools"] if tool["name"] == "gz_wait")["annotations"]["readOnlyHint"] is True
        if list_only:
            return dict(tools=tools, tools_list_result_bytes=len(wire.encode("utf-8")),
                        tools_list_protocol_bytes=protocol["bytes"], handshake_seconds=handshake, launch=probe)
        async def call(step, name, **args):
            result, size, elapsed, requests = await poll_tool(client, name, {"project_id": project_id, **args})
            if "version" in args:
                assert result["version"] > args["version"] if name == "gz_edit_design" else result["version"] == args["version"]
                if name == "gz_edit_design":
                    saved = json.loads((projects / project_id / f"designs/v{result['version']}.json").read_text(encoding="utf-8"))
                    assert saved["parent_version"] == args["version"]
            records.append(dict(step=step, tool=name, arguments=args, result=result, bytes=size, seconds=elapsed, requests=requests))
            return result
        created_id = "t10-smoke-" + project_id
        created = await call(0, "gz_new_project", project_id=created_id, template=project_id, economics=dict(price_self_cny_kwh=.75))
        assert created["created"] and created["version"] is None and created["versions"] == []
        created_directory = (projects / created_id).resolve()
        assert created_directory.is_relative_to(projects.resolve()) and created_directory != projects.resolve()
        assert set(hashes(created_directory)) == {"project.json"}
        assert json.loads((created_directory / "project.json").read_text(encoding="utf-8"))["economics"]["price_self_cny_kwh"] == .75
        shutil.rmtree(created_directory)
        assert not created_directory.exists()
        await call(1, "gz_project_summary")
        directory = projects / project_id
        requirements = json.loads((directory / "project.json").read_text(encoding="utf-8"))["requirements"]
        await call(2, "gz_set_requirements", **requirements)
        await call(3, "gz_fetch_weather", source="nasa_hourly", offline=not online)
        generated = await call(4, "gz_generate_layout", params={})
        version = generated["version"]
        summary = await call(5, "gz_analyze", version=version, offline=not online)
        assert summary["rules"]["hard_failed"] > 0
        repairs = 0
        while summary["rules"]["hard_failed"] and repairs < 6:
            ops = summary["suggestions"]
            assert ops
            ids = [row["id"] for row in summary["rules"]["failed"] if row["level"] == "hard"]
            edited = await call(6, "gz_edit_design", version=version, reason="修正 " + "、".join(ids), ops=ops)
            assert edited["version"] > version
            version = edited["version"]
            summary = await call(7, "gz_analyze", version=version, offline=not online)
            repairs += 1
        assert summary["rules"]["hard_failed"] == 0
        before = hashes(directory)
        scenario = await call(8, "gz_analyze", version=version, what_if=dict(price_change_pct=-10), offline=not online)
        after = hashes(directory)
        assert before == after and scenario["what_if"]["saved"] is False
        options = await call(9, "gz_compare_options", base_version=version, offline=not online)
        for option in options["options"]:
            cursor, seen = option["version"], set()
            while cursor != version:
                assert cursor not in seen
                seen.add(cursor)
                design = json.loads((directory / f"designs/v{cursor}.json").read_text(encoding="utf-8"))
                assert design["parent_version"] is not None and design["author"] == "agent"
                cursor = design["parent_version"]
        crosscheck = await call(10, "gz_crosscheck_yield", version=version, offline=not online)
        assert set(crosscheck["specific_yield_kwh_kwp"]) | set(crosscheck["omitted"]) == {"a", "b", "c", "b_tmy", "d"}
        await call(11, "gz_record_review", version=version, reviewer_model="合成本地测试（未调用模型）", verdict="approve", findings=[])
        exported = await call(12, "gz_export", version=version, offline=not online)
        for filename, digest in exported["files"].items():
            assert hashlib.sha256((directory / f"exports/v{version}" / filename).read_bytes()).hexdigest() == digest
        for path in sorted((directory / "designs").glob("v*.json"), key=lambda p: int(p.stem[1:])):
            design = json.loads(path.read_text(encoding="utf-8"))
            chain.append(dict(version=design["version"], parent_version=design["parent_version"], reason=design["reason"],
                              author=design["author"], modules=len(design["modules"]), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        return dict(tools=tools, tools_list_result_bytes=len(wire.encode("utf-8")),
                    tools_list_protocol_bytes=protocol["bytes"], tools_list_protocol_sha256=protocol["sha256"],
                    launch=probe, handshake_seconds=round(handshake, 6), network_disabled=not online, model_requests=0, agh_started=False, logical_steps=13,
                    new_project_removed=not created_directory.exists(),
                    total_seconds=time.perf_counter() - started,
                    repair_rounds=repairs, records=records, what_if_files_unchanged=before == after,
                    what_if_files_checked=len(before), design_versions=chain, final_version=version)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--handshakes", type=int, default=0)
    parser.add_argument("--online", action="store_true", help="预取缓存后测试联网模式")
    parser.add_argument("--project", choices=list(catalog(all=True, root=ROOT)))
    parser.add_argument("--output", type=Path, default=ROOT / "reports/assets/T10-spike/mcp-smoke.json")
    parser.add_argument("--list-out", type=Path, default=ROOT / "reports/assets/T10-spike/mcp-tools.json")
    args = parser.parse_args(argv)
    scratch = ROOT / ".pytest_cache"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="t10-stdio-", dir=scratch) as temporary:
        owned = Path(temporary).resolve()
        assert owned.is_relative_to(scratch.resolve())
        projects = owned / "projects"
        names = [args.project] if args.project else ["changzhou-demo", "l-shape", "rotated"]
        for name in names:
            shutil.copytree(resolve(name, root=ROOT).parent, projects / name)
        if args.handshakes or args.list_only:
            measured = [anyio.run(lambda: run(projects, list_only=True)) for _ in range(args.handshakes or 1)]
            listing = measured[0].pop("tools")
            for item in measured[1:]:
                item.pop("tools")
            result = dict(handshakes=measured, all_below_two_seconds=all(m["handshake_seconds"] < 2 for m in measured))
            assert result["all_below_two_seconds"]
        else:
            results = {name: anyio.run(lambda: run(projects, project_id=name, online=args.online)) for name in names}
            listing = results[names[0]]["tools"]
            for item in results.values():
                item.pop("tools")
            result = dict(projects=results, environment_keys=list(AGH_ENV), model_requests=0, agh_started=False)
    assert not owned.exists()
    save(args.list_out, listing)
    result["temporary_directory_removed"] = True
    save(args.output, result)
    print(json.dumps(dict(output=str(args.output), projects=list(result.get("projects", {})),
                          handshakes=len(result.get("handshakes", [])), temporary_directory_removed=True), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
