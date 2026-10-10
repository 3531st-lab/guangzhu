"""Contracts, safe failures, and real stdio framing for the twelve tools."""
import json
import os
from pathlib import Path
import subprocess
import sys
from contextlib import chdir
from unittest.mock import patch

import anyio
from jsonschema import Draft202012Validator
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client import stdio as transport
import pytest

from guangzhu import mcp_server as server, mcp_actions, project as storage
from guangzhu.config import ROOT
from guangzhu.models import LayoutParams, StructuredRequirements, validated
from scripts.mcp_smoke import AGH_ENV


def parsed(response):
    assert len(response.content) == 1 and response.content[0].type == "text"
    assert len(response.content[0].text.encode("utf-8")) <= 2048
    return json.loads(response.content[0].text)


def test_handwritten_contracts_match_model_fields_bounds_and_tool_annotations():
    assert set(server.PARAMS) == set(LayoutParams.model_fields)
    assert set(server.REQUIREMENTS) == set(StructuredRequirements.model_fields)
    for name, schema in server.SCHEMAS.items():
        Draft202012Validator.check_schema(schema)
        def walk(value):
            if isinstance(value, dict):
                assert "title" not in value
                if value.get("type") == "object":
                    assert value["additionalProperties"] is False and "required" in value
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(schema)
        tool = next(t for t in server.TOOLS if t.name == name)
        assert tool.annotations.read_only_hint == (name in server.READONLY)
        assert tool.annotations.destructive_hint is False
        assert len(tool.description.split("。")) - 1 <= 3
        if name == "gz_wait":
            assert "只读" in tool.description
        elif name in server.READONLY:
            assert "只读（只写可重算的缓存）" in tool.description
    for name, field in LayoutParams.model_fields.items():
        if server.PARAMS[name].get("type") not in ("number", "integer"):
            continue
        schema = server.PARAMS[name]
        for value in (schema["minimum"], schema.get("maximum", schema["minimum"] + 1)):
            assert Draft202012Validator(schema).is_valid(value)
            validated(LayoutParams, {name: value})
        assert not Draft202012Validator(schema).is_valid(schema["minimum"] - 1)
        if "maximum" in schema:
            assert not Draft202012Validator(schema).is_valid(schema["maximum"] + 1)
    validated(StructuredRequirements, {k: None for k in server.REQUIREMENTS if k != "keep_clear_ids"})


ERRORS = [
    ("gz_project_summary", {}, "INPUT_INVALID"),
    ("gz_project_summary", {"project_id": "../escape"}, "INPUT_INVALID"),
    ("gz_fetch_weather", {"project_id": "demo", "source": "invented"}, "INPUT_INVALID"),
    ("gz_generate_layout", {"project_id": "demo", "params": {"tilt_deg": 36}}, "INPUT_INVALID"),
    ("gz_edit_design", {"project_id": "demo", "version": 1, "reason": "test", "ops": [{"op": "shell"}]}, "INPUT_INVALID"),
    ("gz_analyze", {"project_id": "demo", "version": 0}, "INPUT_INVALID"),
    ("gz_set_requirements", {"project_id": "demo", "text": "test", "structured": {}, "extra": True}, "INPUT_INVALID"),
    ("gz_new_project", {"project_id": "new", "template": "../escape"}, "INPUT_INVALID"),
    ("gz_new_project", {"project_id": "new", "template": "changzhou-demo", "economics": {"price_self_cny_kwh": 2.1}}, "INPUT_INVALID"),
    ("gz_new_project", {"project_id": "new", "template": "changzhou-demo", "economics": {"assumptions_note": "override"}}, "INPUT_INVALID"),
    ("gz_unknown", {}, "TOOL_UNKNOWN"),
]


@pytest.mark.parametrize("name,args,code", ERRORS)
def test_errors_share_four_fields_and_never_expose_tracebacks(name, args, code):
    response = server.call(name, args)
    value = parsed(response)
    assert response.is_error and set(value) == {"ok", "error_code", "message_zh", "fix_hint"}
    assert value["ok"] is False and value["error_code"] == code
    assert "Traceback" not in response.content[0].text


def test_unexpected_exception_and_nonfinite_and_large_result_are_bounded(monkeypatch):
    def fail(*args):
        raise RuntimeError("internal exception must stay private")
    monkeypatch.setattr(mcp_actions, "dispatch", fail)
    response = server.call("gz_project_summary", {"project_id": "demo"})
    assert parsed(response)["error_code"] == "TOOL_FAILED"
    assert "internal exception" not in response.content[0].text
    assert parsed(server.call("gz_analyze", {"project_id": "demo", "version": float("nan")}))["ok"] is False
    monkeypatch.setattr(mcp_actions, "dispatch", lambda *args: dict(ok=True, data="中" * 1000))
    assert parsed(server.call("gz_project_summary", {"project_id": "demo"}))["error_code"] == "RESULT_TOO_LARGE"


def test_actual_stdio_tools_and_safe_errors(tmp_path):
    async def check():
        params = StdioServerParameters(command=sys.executable, args=["-m", "guangzhu.mcp_server", "--projects-dir", str(tmp_path / "projects"), "--offline"],
                                      env={key: os.environ[key] for key in AGH_ENV})
        with patch.object(transport, "get_default_environment", lambda: {}), chdir(os.environ["TEMP"]):
            await check_session(params)
    async def check_session(params):
        async with stdio_client(params) as streams, ClientSession(*streams) as client:
            await client.initialize()
            listing = await client.list_tools()
            assert len(listing.tools) == 12
            assert [t.name for t in listing.tools] == list(server.SCHEMAS)
            assert len(listing.model_dump_json(by_alias=True, exclude_unset=True).encode("utf-8")) + 50 <= 16384
            for name, args, code in ERRORS:
                response = await client.call_tool(name, args)
                assert response.is_error and parsed(response)["error_code"] == code
            response = await client.call_tool("gz_project_summary", dict(project_id="not-created"))
            assert response.is_error and parsed(response)["ok"] is False
            created = parsed(await client.call_tool("gz_new_project", dict(project_id="stdio-new", template="changzhou-demo")))
            assert created["created"] and created["version"] is None and created["exported_versions"] == []
            startup = json.loads((tmp_path / "projects/.mcp-startup.json").read_text(encoding="utf-8"))
            assert created["code_identity"] == startup and startup["process_id"] > 0
            assert len(startup["source_sha256"]) == len(startup["skill_rules_sha256"]) == 64
            assert startup["commit"] and type(startup["dirty"]) is bool
            repeated = parsed(await client.call_tool("gz_new_project", dict(project_id="stdio-new", template="changzhou-demo")))
            assert repeated == created
            unknown = parsed(await client.call_tool("gz_wait", dict(job_id="before-restart")))
            assert unknown["error_code"] == "JOB_UNKNOWN"
            for args in ({}, {"job_id": 1}, {"job_id": "id", "tool": "gz_analyze"}):
                invalid = await client.call_tool("gz_wait", args)
                assert invalid.is_error and parsed(invalid)["error_code"] == "INPUT_INVALID"
    anyio.run(check)


def test_new_demo_roofs_keep_original_geometry_and_trigger_required_rules():
    from guangzhu import layout, rules
    from guangzhu.models import Project
    for project_id, fixture, rule in (("l-shape", "l_shape", "U03"), ("rotated", "rotated", "G05")):
        record = json.loads((ROOT / f"data/demo/projects/{project_id}/project.json").read_text(encoding="utf-8"))
        original = json.loads((ROOT / f"tests/fixtures/roofs/{fixture}.json").read_text(encoding="utf-8"))
        assert record["roof"] == original["roof"]
        project = validated(Project, record)
        assert project.designs == []
        design = layout.generate_layout(project, {})
        if rule == "U03":
            assert design.statistics["dc_kw"] * 1000 * 2.59 > project.requirements.structured.budget_cny_max
        else:
            assert design.params.tilt_deg > project.requirements.structured.tilt_deg_range[1]
