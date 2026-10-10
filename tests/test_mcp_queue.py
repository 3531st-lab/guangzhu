"""Process-local jobs survive cancelled waiters and preserve original results."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import json

import anyio
import pytest

from guangzhu import mcp_actions, mcp_server as server, runtime_diagnostics as diagnostics, project as storage
from guangzhu.models import GzError
from guangzhu.config import ROOT


def value(result):
    return json.loads(result.content[0].text)


@pytest.fixture
def queue(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WAIT_SECONDS", .02)
    monkeypatch.setattr(diagnostics, "LOG_DIR", tmp_path)
    instance = server.JobQueue()
    yield instance
    instance.pool.shutdown()


ARGUMENTS = {
    "gz_project_summary": dict(project_id="test"),
    "gz_set_requirements": dict(project_id="test", text="", structured={}),
    "gz_fetch_weather": dict(project_id="test", source="nasa_hourly"),
    "gz_generate_layout": dict(project_id="test", params={}),
    "gz_analyze": dict(project_id="test", version=1),
    "gz_edit_design": dict(project_id="test", version=1, reason="test", ops=[dict(op="remove_modules", module_ids=[])]),
    "gz_compare_options": dict(project_id="test", base_version=1),
    "gz_crosscheck_yield": dict(project_id="test", version=1),
    "gz_record_review": dict(project_id="test", version=1, reviewer_model="test", verdict="approve", findings=[]),
    "gz_export": dict(project_id="test", version=1),
    "gz_new_project": dict(project_id="test", template="changzhou-demo"),
}


@pytest.mark.parametrize("name", ARGUMENTS)
@pytest.mark.parametrize("outcome", ["success", "known_error", "unexpected_error"])
def test_fast_original_bytes_and_error_flag(queue, monkeypatch, name, outcome):
    monkeypatch.setattr(server, "WAIT_SECONDS", 2)
    def dispatch(*args):
        if outcome == "known_error":
            raise GzError("TEST_ERROR", "受控错误", "稍后重试")
        if outcome == "unexpected_error":
            raise RuntimeError("private")
        return dict(ok=True, answer="中文结果")
    monkeypatch.setattr(mcp_actions, "dispatch", dispatch)
    original = server.call(name, ARGUMENTS[name])
    actual = anyio.run(queue.request, name, ARGUMENTS[name])
    assert actual.model_dump_json() == original.model_dump_json()


@pytest.mark.parametrize("failed", [False, True])
def test_pending_wait_result_and_single_serial_fifo_worker(queue, monkeypatch, failed):
    started, release = Event(), Event()
    executed = []
    def dispatch(name, args):
        executed.append(args["project_id"])
        if args["project_id"] == "first":
            with diagnostics.stage("compare.payback.analysis"), diagnostics.stage("analysis.shading"):
                started.set()
                assert release.wait(5)
        if failed:
            raise GzError("TEST_ERROR", "受控错误", "重试")
        return dict(ok=True, project_id=args["project_id"])
    monkeypatch.setattr(mcp_actions, "dispatch", dispatch)
    async def check():
        first = value(await queue.request("gz_project_summary", dict(project_id="first")))
        assert started.is_set() and first["pending"] is True
        assert first["stage"] == "正在算「最快回本」方案（2/3）"
        second = value(await queue.request("gz_project_summary", dict(project_id="second")))
        third = value(await queue.request("gz_project_summary", dict(project_id="third")))
        assert second["stage"] == third["stage"] == "排队中，等待前面的计算完成"
        waiting = value(await queue.request("gz_wait", dict(job_id=first["job_id"])))
        assert waiting["pending"] and waiting["job_id"] == first["job_id"]
        assert executed == ["first"]
        release.set()
        monkeypatch.setattr(server, "WAIT_SECONDS", 2)
        for job in (first, second, third):
            result = await queue.request("gz_wait", dict(job_id=job["job_id"]))
            content = value(result)
            assert result.is_error == failed
            assert content.pop("job_id") == job["job_id"]
            assert content.pop("tool") == "gz_project_summary"
            assert content["ok"] == (not failed) and "pending" not in content
        assert executed == ["first", "second", "third"]
    try:
        anyio.run(check)
    finally:
        release.set()


@pytest.mark.parametrize("failed", [False, True])
def test_concurrent_key_order_reuse_window_and_retained_results(queue, monkeypatch, failed):
    release = Event()
    now, executed = [1000], []
    monkeypatch.setattr(server, "monotonic", lambda: now[0])
    monkeypatch.setattr(server, "WAIT_SECONDS", 0)
    def dispatch(name, args):
        executed.append(name)
        assert release.wait(5)
        if failed:
            raise GzError("TEST_ERROR", f"受控错误{len(executed)}", "重试")
        return dict(ok=True, execution=len(executed))
    monkeypatch.setattr(mcp_actions, "dispatch", dispatch)
    first_args = dict(project_id="test", text="hello", structured=dict(capacity_kw_min=10, budget_cny_max=100000))
    second_args = dict(structured=dict(budget_cny_max=100000, capacity_kw_min=10), text="hello", project_id="test")
    def submit(args):
        return value(anyio.run(queue.request, "gz_set_requirements", args))
    try:
        with ThreadPoolExecutor(max_workers=2) as threads:
            first, second = list(threads.map(submit, (first_args, second_args)))
        assert first["job_id"] == second["job_id"] and len(queue.jobs) == 1
        now[0] += 700
        assert submit(first_args)["job_id"] == first["job_id"]
        release.set()
        first_original = queue.jobs[first["job_id"]]["future"].result(2)
        assert executed == ["gz_set_requirements"]
        if failed:
            retry = submit(first_args)
            assert len(queue.jobs) == 2 and retry != value(first_original)
            next(job for job in queue.jobs.values() if job["id"] != first["job_id"])["future"].result(2)
            retained = anyio.run(queue.request, "gz_wait", dict(job_id=first["job_id"]))
            assert retained.is_error and value(retained) == dict(value(first_original), tool="gz_set_requirements", job_id=first["job_id"])
            assert executed == ["gz_set_requirements", "gz_set_requirements"]
            return
        now[0] += 599
        assert submit(first_args) == value(queue.jobs[first["job_id"]]["future"].result())
        assert len(queue.jobs) == 1
        now[0] += 2
        retained = anyio.run(queue.request, "gz_wait", dict(job_id=first["job_id"]))
        assert retained.is_error == failed and value(retained)["job_id"] == first["job_id"]
        submit(first_args)
        assert len(queue.jobs) == 2 and first["job_id"] in queue.jobs
        for job_id, job in queue.jobs.items():
            original = job["future"].result(2)
            result = anyio.run(queue.request, "gz_wait", dict(job_id=job_id))
            assert result.is_error == original.is_error == failed
            assert value(result) == dict(value(original), tool="gz_set_requirements", job_id=job_id)
        assert first_original.content != original.content
        assert executed == ["gz_set_requirements", "gz_set_requirements"]
    finally:
        release.set()


@pytest.mark.parametrize("cancel_before_pending", [False, True])
def test_cancelled_waiters_leave_job_retrievable(queue, monkeypatch, cancel_before_pending):
    release, started = Event(), Event()
    executed = []
    def dispatch(name, args):
        executed.append(name)
        started.set()
        assert release.wait(5)
        return dict(ok=True)
    monkeypatch.setattr(mcp_actions, "dispatch", dispatch)
    async def check():
        arguments = dict(project_id="test")
        pending = None
        if not cancel_before_pending:
            pending = value(await queue.request("gz_project_summary", arguments))
        monkeypatch.setattr(server, "WAIT_SECONDS", 2)
        scope = anyio.CancelScope()
        async def cancelled():
            with scope:
                if pending:
                    await queue.request("gz_wait", dict(job_id=pending["job_id"]))
                else:
                    await queue.request("gz_project_summary", arguments)
                pytest.fail("waiting request should be cancelled")
        async with anyio.create_task_group() as group:
            group.start_soon(cancelled)
            while not started.is_set():
                await anyio.sleep(.001)
            await anyio.sleep(.005)
            scope.cancel()
        monkeypatch.setattr(server, "WAIT_SECONDS", .01)
        recovered = value(await queue.request("gz_project_summary", arguments))
        if pending:
            assert recovered["job_id"] == pending["job_id"]
        release.set()
        monkeypatch.setattr(server, "WAIT_SECONDS", 2)
        finished = value(await queue.request("gz_wait", dict(job_id=recovered["job_id"])))
        assert finished["ok"] and finished["job_id"] == recovered["job_id"]
        monkeypatch.setattr(server, "monotonic", lambda: queue.jobs[recovered["job_id"]]["finished"] + 601)
        assert value(await queue.request("gz_wait", dict(job_id=recovered["job_id"]))) == finished
        assert executed == ["gz_project_summary"]
    try:
        anyio.run(check)
    finally:
        release.set()


@pytest.mark.parametrize("name,args", [
    ("gz_wait", {}), ("gz_wait", dict(job_id=5)), ("gz_wait", dict(job_id="id", tool="gz_analyze")),
    ("gz_project_summary", []), ("gz_project_summary", dict(project_id=object())),
    ("gz_analyze", dict(project_id="test", version=float("nan"))), ("gz_unknown", {}),
])
def test_invalid_requests_are_structured_and_never_registered(queue, name, args):
    result = anyio.run(queue.request, name, args)
    assert result.is_error and value(result)["ok"] is False
    assert set(value(result)) == {"ok", "error_code", "message_zh", "fix_hint"}
    assert not queue.jobs


def test_unknown_and_restart_do_not_recover_jobs(queue):
    result = anyio.run(queue.request, "gz_wait", dict(job_id="previous-process"))
    assert result.is_error and value(result)["error_code"] == "JOB_UNKNOWN"
    assert value(result)["message_zh"] == "后台计算记录已失效，请按原参数重新调用原工具"


def test_first_execution_keeps_argument_order_and_other_keys_do_not_merge(queue, monkeypatch):
    monkeypatch.setattr(server, "WAIT_SECONDS", 2)
    executed = []
    def dispatch(name, args):
        executed.append((name, args))
        return dict(ok=True, fields=list(args["structured"]))
    monkeypatch.setattr(mcp_actions, "dispatch", dispatch)
    args = dict(project_id="test", text="", structured=dict(capacity_kw_min=10, budget_cny_max=100000))
    original = server.call("gz_set_requirements", args)
    queued = anyio.run(queue.request, "gz_set_requirements", args)
    assert queued.model_dump_json() == original.model_dump_json()
    anyio.run(queue.request, "gz_set_requirements", dict(args, project_id="other"))
    assert len(queue.jobs) == 2
    monkeypatch.setattr(mcp_actions, "dispatch", lambda *args: dict(ok=True))
    anyio.run(queue.request, "gz_crosscheck_yield", dict(project_id="test", version=1))
    anyio.run(queue.request, "gz_analyze", dict(project_id="test", version=1))
    assert len(queue.jobs) == 4
    old_id = next(iter(queue.jobs))
    restarted = server.JobQueue()
    try:
        unknown = anyio.run(restarted.request, "gz_wait", dict(job_id=old_id))
        assert unknown.is_error and value(unknown)["error_code"] == "JOB_UNKNOWN"
    finally:
        restarted.pool.shutdown()


def test_wait_metadata_allowance_preserves_2048_byte_business_limit(queue, monkeypatch):
    monkeypatch.setattr(server, "WAIT_SECONDS", 2)
    payload = dict(ok=True, data="")
    overhead = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    payload["data"] = "x" * (2048 - overhead)
    monkeypatch.setattr(mcp_actions, "dispatch", lambda *args: payload)
    original = anyio.run(queue.request, "gz_project_summary", dict(project_id="boundary"))
    assert len(original.content[0].text.encode("utf-8")) == 2048
    job_id = next(iter(queue.jobs))
    result = anyio.run(queue.request, "gz_wait", dict(job_id=job_id))
    assert not result.is_error
    assert 2048 < len(result.content[0].text.encode("utf-8")) <= 2048 + server.WAIT_METADATA_BYTES
    actual = value(result)
    actual.pop("tool")
    actual.pop("job_id")
    assert json.dumps(actual, ensure_ascii=False, separators=(",", ":")) == original.content[0].text
    payload["data"] += "x"
    rejected = anyio.run(queue.request, "gz_project_summary", dict(project_id="too-large"))
    assert rejected.is_error and value(rejected)["error_code"] == "RESULT_TOO_LARGE"


@pytest.fixture
def real_project(queue, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WAIT_SECONDS", 20)
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(server, "PROJECTS_OVERRIDE", tmp_path / "projects")
    source = ROOT / "data/demo/projects/changzhou-demo"
    return storage.init(source, "cache-test").id


def test_real_summary_layout_analysis_and_requirements_dependencies(queue, real_project):
    async def check():
        async def request(name, **args):
            result = await queue.request(name, dict(project_id=real_project, **args))
            assert not result.is_error, value(result)
            return value(result)
        first = await request("gz_project_summary")
        assert first["version"] is None and first["latest_analysis"] is None
        design = await request("gz_generate_layout", params={})
        after_layout = await request("gz_project_summary")
        assert after_layout["version"] == design["version"] and after_layout["modules"] > 0
        args = dict(version=design["version"], offline=True)
        before = await request("gz_analyze", **args)
        analyzed = await request("gz_project_summary")
        assert analyzed["latest_analysis"]["version"] == design["version"]
        await request("gz_set_requirements", text="budget at most one yuan", structured=dict(budget_cny_max=1))
        changed = await request("gz_analyze", **args)
        assert "U03" not in [row["id"] for row in before["rules"]["failed"]]
        assert "U03" in [row["id"] for row in changed["rules"]["failed"]]
        direct = server.call("gz_analyze", dict(project_id=real_project, **args))
        assert json.dumps(changed, ensure_ascii=False, separators=(",", ":")) == direct.content[0].text
        assert (await request("gz_project_summary"))["requirements"]["budget_cny_max"] == 1
    anyio.run(check)


def test_real_requirements_a_b_a_matches_return_and_disk(queue, real_project):
    async def check():
        a = dict(project_id=real_project, text="unrestricted", structured={})
        first = await queue.request("gz_set_requirements", a)
        second = await queue.request("gz_set_requirements", dict(
            project_id=real_project, text="at least 10000 kW", structured=dict(capacity_kw_min=10000)))
        third = await queue.request("gz_set_requirements", a)
        assert value(second)["contradictions"] and not value(third)["contradictions"]
        actual = storage.load(real_project).requirements.model_dump(exclude_none=True)
        assert actual == value(third)["requirements"]
        assert third.content[0].text == first.content[0].text and len(queue.jobs) == 3
    anyio.run(check)


def test_real_same_version_analysis_reads_changed_requirements(queue, real_project):
    async def check():
        design = value(await queue.request("gz_generate_layout", dict(project_id=real_project, params={})))
        args = dict(project_id=real_project, version=design["version"], offline=True)
        before = value(await queue.request("gz_analyze", args))
        await queue.request("gz_set_requirements", dict(project_id=real_project, text="one yuan", structured=dict(budget_cny_max=1)))
        after = value(await queue.request("gz_analyze", args))
        assert "U03" not in [row["id"] for row in before["rules"]["failed"]]
        assert "U03" in [row["id"] for row in after["rules"]["failed"]]
    anyio.run(check)


@pytest.mark.parametrize("writer", ["gz_new_project", "gz_set_requirements", "gz_generate_layout", "gz_edit_design", "gz_compare_options"])
@pytest.mark.parametrize("failed", [False, True])
def test_project_writes_invalidate_all_old_jobs_but_retain_ids_and_other_projects(queue, monkeypatch, writer, failed):
    monkeypatch.setattr(server, "WAIT_SECONDS", 2)
    executed = []
    def dispatch(name, args):
        executed.append((name, args["project_id"]))
        if failed and name == "gz_analyze":
            raise GzError("TEST_ERROR", f"错误{len(executed)}", "重试")
        return dict(ok=True, execution=len(executed))
    monkeypatch.setattr(mcp_actions, "dispatch", dispatch)
    async def check():
        first = await queue.request("gz_analyze", ARGUMENTS["gz_analyze"])
        old_id = next(iter(queue.jobs))
        other = dict(project_id="other", version=1)
        unchanged = await queue.request("gz_analyze", other)
        await queue.request(writer, ARGUMENTS[writer])
        second = await queue.request("gz_analyze", ARGUMENTS["gz_analyze"])
        assert second.content != first.content
        subsequent = await queue.request("gz_analyze", other)
        assert (subsequent.content == unchanged.content) == (not failed)
        retained = value(await queue.request("gz_wait", dict(job_id=old_id)))
        assert retained == dict(value(first), job_id=old_id, tool="gz_analyze")
        assert len(executed) == (5 if failed else 4)
    anyio.run(check)


@pytest.mark.parametrize("name,extra,invalidated", [
    ("gz_analyze", {}, True), ("gz_analyze", {"what_if": {}}, False),
    ("gz_export", {}, True), ("gz_crosscheck_yield", {}, False), ("gz_record_review", {}, False),
    ("gz_fetch_weather", {}, False),
])
def test_only_summary_invalidated_by_saved_analysis_or_export(queue, monkeypatch, name, extra, invalidated):
    monkeypatch.setattr(server, "WAIT_SECONDS", 2)
    executions = []
    def dispatch(name, args):
        executions.append(name)
        return dict(ok=True, execution=len(executions))
    monkeypatch.setattr(mcp_actions, "dispatch", dispatch)
    async def check():
        first = await queue.request("gz_project_summary", ARGUMENTS["gz_project_summary"])
        await queue.request("gz_generate_layout", ARGUMENTS["gz_generate_layout"])
        first = await queue.request("gz_project_summary", ARGUMENTS["gz_project_summary"])
        await queue.request(name, dict(ARGUMENTS[name], **extra))
        second = await queue.request("gz_project_summary", ARGUMENTS["gz_project_summary"])
        assert (second.content != first.content) == invalidated
        before = len(executions)
        await queue.request("gz_generate_layout", ARGUMENTS["gz_generate_layout"])
        assert len(executions) == before
    anyio.run(check)


def test_fifo_invalidates_queued_reads_at_submission_and_keeps_compare_recovery(queue, monkeypatch):
    release = Event()
    state, executed = {"text": "A"}, []
    def dispatch(name, args):
        executed.append(name)
        if name == "gz_compare_options":
            assert release.wait(10)
        if name == "gz_set_requirements":
            state["text"] = args["text"]
        return dict(ok=True, text=state["text"])
    monkeypatch.setattr(mcp_actions, "dispatch", dispatch)
    async def check():
        monkeypatch.setattr(server, "WAIT_SECONDS", 2)
        old = await queue.request("gz_project_summary", ARGUMENTS["gz_project_summary"])
        monkeypatch.setattr(server, "WAIT_SECONDS", .02)
        compare = value(await queue.request("gz_compare_options", ARGUMENTS["gz_compare_options"]))
        queued = value(await queue.request("gz_project_summary", ARGUMENTS["gz_project_summary"]))
        duplicate = value(await queue.request("gz_compare_options", ARGUMENTS["gz_compare_options"]))
        assert duplicate["job_id"] == compare["job_id"]
        old_analysis = value(await queue.request("gz_analyze", ARGUMENTS["gz_analyze"]))
        writer = value(await queue.request("gz_set_requirements", dict(ARGUMENTS["gz_set_requirements"], text="B")))
        fresh = value(await queue.request("gz_project_summary", ARGUMENTS["gz_project_summary"]))
        new_analysis = value(await queue.request("gz_analyze", ARGUMENTS["gz_analyze"]))
        assert fresh.get("pending") and fresh["job_id"] != queued["job_id"]
        assert new_analysis.get("pending") and new_analysis["job_id"] != old_analysis["job_id"]
        release.set()
        monkeypatch.setattr(server, "WAIT_SECONDS", 2)
        for item, expected in [(compare, "A"), (queued, "A"), (old_analysis, "A"), (writer, "B"),
                               (fresh, "B"), (new_analysis, "B")]:
            result = value(await queue.request("gz_wait", dict(job_id=item["job_id"])))
            assert result["text"] == expected
        assert value(old)["text"] == "A"
        assert executed == ["gz_project_summary", "gz_compare_options", "gz_project_summary", "gz_analyze",
                            "gz_set_requirements", "gz_project_summary", "gz_analyze"]
    try:
        anyio.run(check)
    finally:
        release.set()


@pytest.mark.parametrize("failure", ["controlled", "exception", "payload"])
def test_failed_jobs_rerun_same_args_and_wait_keeps_original_error(queue, monkeypatch, failure):
    monkeypatch.setattr(server, "WAIT_SECONDS", 2)
    executions = []
    def dispatch(name, args):
        executions.append(name)
        if len(executions) > 1:
            return dict(ok=True, recovered=True)
        if failure == "controlled":
            raise GzError("TEST_ERROR", "受控错误", "重试")
        if failure == "exception":
            raise RuntimeError("synthetic failure")
        return dict(ok=False, error_code="TEST_ERROR")
    monkeypatch.setattr(mcp_actions, "dispatch", dispatch)
    async def check():
        args = dict(project_id="retry")
        first = await queue.request("gz_project_summary", args)
        old_id = next(iter(queue.jobs))
        assert value(first)["ok"] is False
        second = await queue.request("gz_project_summary", args)
        assert value(second) == dict(ok=True, recovered=True)
        assert (await queue.request("gz_project_summary", args)).content == second.content
        original = await queue.request("gz_wait", dict(job_id=old_id))
        assert original.is_error == first.is_error
        assert value(original) == dict(value(first), tool="gz_project_summary", job_id=old_id)
        assert executions == ["gz_project_summary"] * 2
    anyio.run(check)
