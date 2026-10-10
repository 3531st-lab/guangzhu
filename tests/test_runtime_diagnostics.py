"""Process-local timing must remain useful without recording user input."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from guangzhu import runtime_diagnostics as diagnostics


def test_call_records_parallel_stages_but_no_free_text(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, "LOG_DIR", tmp_path)
    with diagnostics.call_record("gz_compare_options", {"project_id": "safe-r2", "base_version": 5,
                                                        "text": "private user input", "unknown": "do not log"}):
        def phase(i):
            with diagnostics.stage(f"tilt.{i}"):
                return sum(range(10000))
        with ThreadPoolExecutor(max_workers=3) as pool:
            assert list(pool.map(phase, range(3))) == [49995000] * 3
    records = [json.loads(row) for row in next(tmp_path.glob("mcp-*.jsonl")).read_text().splitlines()]
    record = records[-1]
    assert record["project_id"] == "safe-r2" and record["base_version"] == 5
    assert {p["name"] for p in record["stages"]} == {"tilt.0", "tilt.1", "tilt.2"}
    assert all(p["elapsed_seconds"] >= 0 for p in record["stages"])
    assert record["process_cpu_seconds"] >= 0 and record["pid"] == os.getpid()
    contents = next(tmp_path.glob("mcp-*.jsonl")).read_text()
    assert "private user input" not in contents and "do not log" not in contents


def test_current_stage_keeps_parallel_stacks_and_business_phase(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, "LOG_DIR", tmp_path)
    entered = [Event(), Event()]
    release = [Event(), Event()]
    def phase(index, name):
        with diagnostics.stage(name), diagnostics.stage("analysis.shading"):
            entered[index].set()
            assert release[index].wait(5)
    with diagnostics.call_record("gz_compare_options", {}), ThreadPoolExecutor(max_workers=2) as pool:
        try:
            first = pool.submit(phase, 0, "compare.initial-10.shading")
            assert entered[0].wait(2)
            second = pool.submit(phase, 1, "compare.candidate-20.yield")
            assert entered[1].wait(2)
            assert diagnostics.current_stage() == "正在计算不同倾角的遮挡和发电量"
            release[0].set()
            first.result(2)
            assert diagnostics.current_stage() == "正在计算不同倾角的遮挡和发电量"
            release[1].set()
            second.result(2)
        finally:
            for event in release:
                event.set()
        assert diagnostics.current_stage() == "正在准备/计算，请稍候"
        with diagnostics.stage("compare.capacity.analysis"), diagnostics.stage("analysis.shading"):
            assert diagnostics.current_stage() == "正在算「多装」方案（1/3）"
    assert diagnostics.current_stage() == "正在准备/计算，请稍候"
    assert diagnostics._active == {}


@pytest.mark.parametrize("name,label", [
    ("compare.site", "正在准备三方案的数据"),
    ("compare.payback.analysis", "正在算「最快回本」方案（2/3）"),
    ("compare.balanced.analysis", "正在算「折中」方案（3/3）"),
    ("analysis.shading", "正在计算遮挡"),
    ("shading.rays", "正在计算遮挡"),
    ("analysis.yield", "正在计算发电量"),
    ("analysis.economics", "正在计算收益"),
    ("analysis.rules", "正在检查规则"),
    ("analysis.save", "正在保存分析结果"),
    ("tool.imports", "正在准备/计算，请稍候"),
])
def test_current_stage_chinese_labels(tmp_path, monkeypatch, name, label):
    monkeypatch.setattr(diagnostics, "LOG_DIR", tmp_path)
    with diagnostics.call_record("gz_analyze", {}), diagnostics.stage(name):
        assert diagnostics.current_stage() == label


def test_diagnostics_failure_does_not_break_calculation(tmp_path, monkeypatch):
    target = tmp_path / "not-a-directory"
    target.write_text("x")
    monkeypatch.setattr(diagnostics, "LOG_DIR", target)
    with diagnostics.call_record("gz_analyze", {"project_id": "safe-r2", "version": 1}):
        with diagnostics.stage("analysis.shading"):
            value = 42
    assert value == 42


@pytest.mark.parametrize("arguments", [None, [], "invalid"])
def test_invalid_arguments_remain_a_structured_error(tmp_path, monkeypatch, arguments):
    from guangzhu import mcp_server
    monkeypatch.setattr(diagnostics, "LOG_DIR", tmp_path)
    response = mcp_server.call("gz_project_summary", arguments)
    assert response.is_error
    assert json.loads(response.content[0].text)["error_code"] == "INPUT_INVALID"


def test_startup_ignores_old_probe_and_thread_failure_does_not_block_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, "LOG_DIR", tmp_path)
    def no_thread(self):
        raise RuntimeError("cannot allocate thread")
    monkeypatch.setattr(diagnostics.threading.Thread, "start", no_thread)
    request = tmp_path / "startup-probe.json"
    request.write_text(json.dumps(dict(project_id="safe-r2", version=1)))
    diagnostics.startup()
    assert request.exists()
    with diagnostics.call_record("gz_analyze", dict(project_id="safe-r2", version=1)):
        value = 42
    assert value == 42
    records = [json.loads(row) for row in next(tmp_path.glob("mcp-*.jsonl")).read_text().splitlines()]
    assert records[0]["kind"] == "startup"
    assert records[-1]["kind"] == "call"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows execution throttling API")
def test_execution_speed_opt_out_in_own_child_process():
    code = "from guangzhu.runtime_diagnostics import configure_execution_speed; import json; print(json.dumps(configure_execution_speed()))"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "backend")
    result = subprocess.run([sys.executable, "-c", code], env=environment, capture_output=True, text=True, check=True)
    state = json.loads(result.stdout)
    assert state["success"] is True
    assert state["after"]["control_mask"] & 1 == 1
    assert state["after"]["state_mask"] & 1 == 0
