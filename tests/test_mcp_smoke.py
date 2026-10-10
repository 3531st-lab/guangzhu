"""The maintenance smoke follows one SDK request chain without relaxing limits."""
import json

import anyio
import pytest
from mcp import types

from scripts import mcp_smoke as smoke


def response(value):
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(
        value, ensure_ascii=False, separators=(",", ":")))], isError=False)


class Client:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    async def call_tool(self, name, arguments, *, read_timeout_seconds):
        self.calls.append((name, arguments, read_timeout_seconds))
        return response(next(self.values))


def pending(job="job", tool="gz_compare_options"):
    return dict(ok=True, pending=True, job_id=job, tool=tool)


def test_multiple_waits_keep_original_arguments_and_total_time(monkeypatch):
    times = iter([0, 0, 40, 40, 80, 80, 110, 110])
    monkeypatch.setattr(smoke.time, "perf_counter", lambda: next(times))
    client = Client([pending(), pending(), dict(ok=True, version=4, tool="gz_compare_options", job_id="job")])
    args = dict(project_id="p", base_version=1)
    result, size, seconds, requests = anyio.run(smoke.poll_tool, client, "gz_compare_options", args)
    assert result == dict(ok=True, version=4)
    assert size == len('{"ok":true,"version":4}'.encode())
    assert seconds == 110 and [row["seconds"] for row in requests] == [40, 40, 30]
    assert [row["tool"] for row in requests] == ["gz_compare_options", "gz_wait", "gz_wait"]
    assert client.calls == [("gz_compare_options", args, 60), ("gz_wait", {"job_id": "job"}, 60),
                            ("gz_wait", {"job_id": "job"}, 60)]
    assert requests[0]["arguments"] == args and requests[0]["result"] == pending()


@pytest.mark.parametrize("values", [
    [pending(tool="gz_analyze")],
    [pending(), pending(job="other")],
    [pending(), pending(tool="gz_analyze")],
    [pending(), dict(ok=True, tool="gz_compare_options", job_id="other")],
    [pending(), dict(ok=True, tool="gz_analyze", job_id="job")],
    [dict(ok=True, tool="gz_compare_options", job_id="job")],
    [pending(), dict(ok=True)],
])
def test_rejects_mismatched_or_orphaned_transport(values):
    with pytest.raises(AssertionError):
        anyio.run(smoke.poll_tool, Client(values), "gz_compare_options", dict(project_id="p"))


@pytest.mark.parametrize("waited", [False, True])
@pytest.mark.parametrize("extra", [0, 1])
def test_business_body_stays_limited_to_2048_bytes(waited, extra):
    body = dict(ok=True, data="")
    overhead = len(response(body).content[0].text.encode())
    body["data"] = "x" * (2048 - overhead + extra)
    values = [pending(), dict(body, tool="gz_compare_options", job_id="job")] if waited else [body]
    if extra:
        with pytest.raises(AssertionError):
            anyio.run(smoke.poll_tool, Client(values), "gz_compare_options", {})
    else:
        actual, size, _, _ = anyio.run(smoke.poll_tool, Client(values), "gz_compare_options", {})
        assert actual == body and size == 2048


def test_wait_metadata_cannot_exceed_small_allowance():
    job = "x" * 200
    with pytest.raises(AssertionError):
        anyio.run(smoke.poll_tool, Client([pending(job), dict(ok=True, job_id=job, tool="gz_compare_options")]),
                  "gz_compare_options", {})


@pytest.mark.parametrize("elapsed", [45, 45.0001])
def test_each_request_has_45_second_boundary(monkeypatch, elapsed):
    times = iter([0, 0, elapsed, elapsed])
    monkeypatch.setattr(smoke.time, "perf_counter", lambda: next(times))
    client = Client([dict(ok=True)])
    if elapsed > 45:
        with pytest.raises(AssertionError):
            anyio.run(smoke.poll_tool, client, "gz_project_summary", {})
    else:
        assert anyio.run(smoke.poll_tool, client, "gz_project_summary", {})[2] == elapsed
