import importlib.util
import json
from pathlib import Path

import pytest


SOURCE = Path(__file__).parent / "embed_harness/server.py"
SPEC = importlib.util.spec_from_file_location("embed_harness_server", SOURCE)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


@pytest.mark.parametrize("sample,expected", [
    ("changzhou-demo", {"payback_years_max": 6, "walkway_m_min": 1, "keep_clear_ids": ["sky-1"]}),
    ("l-shape", {"budget_cny_max": 300000, "walkway_m_min": 1, "keep_clear_ids": ["sky"]}),
    ("rotated", {"walkway_m_min": 1, "keep_clear_ids": ["sky-1"], "tilt_deg_range": [15, 20]}),
    ("impossible", {"budget_cny_max": 50000, "capacity_kw_min": 300}),
])
def test_harness_presets_are_generated_by_brief_cli(sample, expected):
    result = SERVER.make_brief({"sample": sample, "id": "t10-harness-" + sample, "reviewer_model": "route/agnes-3.0-flash"})
    encoded = result["brief"].split("```json\n", 1)[1].split("\n```", 1)[0]
    data = json.loads(encoded)
    assert data["requirements"]["structured"] == expected
    assert data["run"]["review"]["model"] == "route/agnes-3.0-flash"
    assert result["command"][:3] == ["python", "-m", "guangzhu.brief"]
    assert data["project"]["template"] == ("l-shape" if sample == "impossible" else sample)


def test_harness_rejects_non_test_project_before_running_cli():
    with pytest.raises(ValueError):
        SERVER.make_brief({"sample": "changzhou-demo", "id": "production-roof"})


@pytest.mark.parametrize("mode", [None, "independent", "subagent"])
def test_harness_preserves_explicit_review_mode_after_cli_default_change(mode):
    spec = {"sample": "changzhou-demo", "id": "t10-harness-review-mode"}
    if mode is not None:
        spec["review_mode"] = mode
    result = SERVER.make_brief(spec)
    data = json.loads(result["brief"].split("```json\n", 1)[1].split("\n```", 1)[0])
    assert data["run"]["review"].get("mode", "subagent") == (mode or "independent")
    if mode is not None:
        position = result["command"].index("--review-mode")
        assert result["command"][position + 1] == mode


def test_logs_remove_user_directory_and_credentials_without_changing_numeric_tool_values():
    value = {"message": {"type": "gz.progress", "result": r"C:\Users\Someone\private.json", "api_key": "example-token", "sample": "sk-example_secret_key123456", "dc_kw": 220.625}}
    cleaned = SERVER.sanitized(value)
    assert "Someone" not in json.dumps(cleaned)
    assert "example-token" not in json.dumps(cleaned)
    assert "sk-example" not in json.dumps(cleaned)
    assert cleaned["message"]["dc_kw"] == 220.625
