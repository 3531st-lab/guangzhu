"""Post-run reports reuse archive evidence without exporting AGH again."""
import hashlib
import copy
import json
import shutil
import sys
from types import SimpleNamespace

import pytest

from guangzhu import api, report
from test_api import local, payload
from test_agh_runs import resequence


@pytest.fixture(autouse=True)
def requested_review(local):
    events = local[3]
    message = copy.deepcopy(events[0])
    packet = dict(brief="guangzhu.brief/1", run=dict(review=dict(enabled=True, mode="independent", model="agnes-3.0-flash")))
    message.update(type="user/message", origin="user", data=dict(content=[dict(type="text",
        text="【光筑任务书】\n```json\n" + json.dumps(packet) + "\n```")]))
    events.insert(2, message)
    events[:] = resequence(events)


@pytest.fixture
def generator(monkeypatch):
    calls = []

    def generate(folder, *, regenerated=False):
        calls.append((folder, regenerated))
        metadata = api.read(folder / "run.json")
        assert (folder / "verification.json").is_file()
        contents = [("report-v2.html", b"<html>archived</html>"), ("report-v2.pdf", b"%PDF-test")]
        files = []
        for name, data in contents:
            path = folder / "report" / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
            files.append(dict(name=name, sha256=hashlib.sha256(data).hexdigest()))
        status = dict(status="ready", version=2, generated_at="2026-10-03T00:00:00Z", regenerated=regenerated, files=files)
        metadata["report"] = status
        metadata["artifacts"].update({"report/" + row["name"]: row["sha256"] for row in files})
        api.evidence.write_json(folder / "run.json", metadata)
        return status

    monkeypatch.setattr(report, "generate", generate)
    return calls


def test_auto_generation_waits_for_review_and_keeps_approved_export(local, generator):
    client, root, project, _, _ = local
    first = client.post("/api/runs/finish", json=payload()).json()
    assert first["result"]["report"] is None and generator == []
    original = {p: p.read_bytes() for p in (project / "exports").rglob("*") if p.is_file()}
    second = client.post("/api/runs/finish", json=payload(review_session_id="review-session")).json()
    folder = root / "runs/gz-changzhou-demo"
    assert generator == [(folder, False)]
    assert second["verification"] == api.read(folder / "verification.json")
    assert second["result"]["report"]["status"] == "ready"
    assert not (project / "reports").exists()  # The mocked generator owns copying; the API must not duplicate it.
    assert {p: p.read_bytes() for p in original} == original
    assert client.get("/api/runs/gz-changzhou-demo?version=1").json()["result"]["report"] is None


def test_completed_reviewer_refreshes_initial_capture_without_overwriting_it(local, generator, monkeypatch):
    client, root, project, _, calls = local
    native_export = api.evidence.export_ledger
    ready = False

    def export(sid, ledger, executable, **kwargs):
        exported = native_export(sid, ledger, executable, **kwargs)
        if sid == "review-session" and not ready:
            exported = exported[:1]
            for seq, kind in enumerate(("x/agnes/code-mode/kernel", "x/core/model-switch", "user/inbox-add"), 2):
                event = copy.deepcopy(exported[0])
                event.update(seq=seq, id=f"initial-{seq}", type=kind, data={})
                exported.append(event)
            ledger.write_text("".join(json.dumps(row) + "\n" for row in exported), encoding="utf-8")
        return exported

    monkeypatch.setattr(api.evidence, "export_ledger", export)
    first = client.post("/api/runs/finish", json=payload(review_session_id="review-session"))
    assert first.status_code == 200, first.text
    assert first.json()["verification"]["review"]["passed"] is False
    folder = root / "runs/gz-changzhou-demo"
    old = folder / api.read(folder / "run.json")["review_capture"]
    before = {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()}
    assert api.read(old / "run.json")["model_requests"] == 0
    ready = True
    review = dict(version=2, verdict="approve", reviewer_model="agnes-3.0-flash", findings=[])
    api.evidence.write_json(project / "reviews/v2-synthetic.json", review)
    final = client.post("/api/runs/finish", json=payload(review_session_id="review-session"))
    assert final.status_code == 200, final.text
    assert final.json()["verification"]["review"]["passed"] is True
    current = folder / api.read(folder / "run.json")["review_capture"]
    assert current != old
    assert {p.relative_to(old): p.read_bytes() for p in old.rglob("*") if p.is_file()} == before
    assert len(api.evidence.read_events(current / "ledger.agnes.jsonl")) > 4
    assert final.json()["result"]["reviews"] == [review]
    assert final.json()["result"]["report"]["status"] == "ready"
    assert calls == ["design-session", "review-session", "review-session"]
    replay = client.get("/api/runs/gz-changzhou-demo").json()
    assert replay["verification"]["review"]["passed"] is True
    assert replay["run"]["review_capture"] == current.relative_to(folder).as_posix()
    client.post("/api/runs/finish", json=payload())
    assert calls == ["design-session", "review-session", "review-session"]


def test_explicitly_unrequested_review_generates_after_design_finish(local, generator):
    client, _, _, events, _ = local
    events[2]["data"]["content"][0]["text"] = events[2]["data"]["content"][0]["text"].replace('"enabled": true', '"enabled": false')
    result = client.post("/api/runs/finish", json=payload()).json()
    assert result["verification"]["review"]["requested"] is False
    assert result["result"]["report"]["status"] == "ready"
    assert len(generator) == 1 and generator[0][1] is False


def test_manual_generation_is_archive_only_without_another_agh_export(local, generator):
    client, root, project, _, exports = local
    client.post("/api/runs/finish", json=payload())
    folder = root / "runs/gz-changzhou-demo"
    before = (folder / "verification.json").read_bytes()
    shutil.rmtree(project)
    rows = client.get("/api/runs").json()["runs"]
    assert next(row for row in rows if row["run_id"] == folder.name)["can_report"] is True
    response = client.post("/api/runs/gz-changzhou-demo/report")
    assert response.status_code == 200 and response.json()["regenerated"] is True
    assert generator == [(folder, True)] and exports == ["design-session"]
    assert (folder / "verification.json").read_bytes() == before
    assert not project.exists()


@pytest.mark.parametrize("failure", ["checks", "nonboolean", "scene"])
def test_manual_generation_requires_four_passed_checks_and_intact_scene(local, generator, failure):
    client, root, _, _, exports = local
    client.post("/api/runs/finish", json=payload())
    folder = root / "runs/gz-changzhou-demo"
    if failure != "scene":
        verification = api.read(folder / "verification.json")
        verification["checks"][0]["passed"] = "true" if failure == "nonboolean" else False
        api.evidence.write_json(folder / "verification.json", verification)
    else:
        capture = api.record(folder)[0]
        (capture / "project/analysis/v2/shading.json").write_text("{}", encoding="utf-8")
    assert client.post("/api/runs/gz-changzhou-demo/report").status_code == 409
    assert generator == [] and exports == ["design-session"]
    assert next(row for row in client.get("/api/runs").json()["runs"] if row["run_id"] == folder.name)["can_report"] is (failure == "scene")
    assert client.post("/api/runs/nonexistent/report").status_code == 404


def test_generator_exception_is_report_error_and_does_not_invalidate_verification(local, monkeypatch):
    client, root, _, _, _ = local

    def fail(*args, **kwargs):
        raise RuntimeError("C:\\Users\\private\\not-public")

    monkeypatch.setattr(report, "generate", fail)
    response = client.post("/api/runs/finish", json=payload(review_session_id="review-session"))
    assert response.status_code == 200
    data = response.json()
    assert all(check["passed"] for check in data["verification"]["checks"])
    assert data["result"]["report"]["status"] == "error"
    assert "private" not in response.text
    assert api.read(root / "runs/gz-changzhou-demo/run.json")["report"] == data["result"]["report"]


def test_copy_failure_preserves_archive_and_verification(local, monkeypatch):
    client, root, _, _, _ = local

    def fail(*args):
        raise PermissionError("test copy denied")

    original_generate = report.generate
    monkeypatch.setattr(report, "ROOT", root)
    monkeypatch.setattr(report, "load_archive", lambda folder: dict(version=2, project_id="changzhou-demo"))
    monkeypatch.setitem(sys.modules, "guangzhu.report.view", SimpleNamespace(render=lambda context: "<p>光筑</p>"))
    monkeypatch.setattr(report, "generate", lambda folder, **kwargs: original_generate(folder, browsers=[], **kwargs))
    client.post("/api/runs/finish", json=payload())
    monkeypatch.setattr(report.shutil, "copyfile", fail)
    response = client.post("/api/runs/finish", json=payload(review_session_id="review-session"))
    assert response.status_code == 200
    data = response.json()
    assert all(check["passed"] for check in data["verification"]["checks"])
    assert data["result"]["report"]["status"] == "html-only"
    assert "副本未能写入" in data["result"]["report"]["hint"]
    assert (root / "runs/gz-changzhou-demo/report/report-v2.html").is_file()


def test_open_report_ignores_payload_path_and_checks_registry_and_digest(local, generator, monkeypatch):
    client, root, project, _, _ = local
    client.post("/api/runs/finish", json=payload())
    client.post("/api/runs/gz-changzhou-demo/report")
    opened = []
    monkeypatch.setattr(api.os, "startfile", opened.append)
    request = dict(kind="report", run_id="gz-changzhou-demo", filename="../../outside.html")
    assert client.post("/api/open", json=request).status_code == 200
    folder = root / "runs/gz-changzhou-demo"
    assert opened == [folder / "report/report-v2.pdf"]
    metadata = api.read(folder / "run.json")
    metadata["report"]["files"] = metadata["report"]["files"][:1]
    api.evidence.write_json(folder / "run.json", metadata)
    assert client.post("/api/open", json=request).status_code == 200
    assert opened[-1].name == "report-v2.html"
    metadata["artifacts"]["report/report-v2.html"] = "0" * 64
    api.evidence.write_json(folder / "run.json", metadata)
    assert client.post("/api/open", json=request).status_code == 400
    metadata["report"]["files"] = [dict(name="../outside.html", sha256="0" * 64)]
    api.evidence.write_json(folder / "run.json", metadata)
    assert client.post("/api/open", json=request).status_code == 404
    assert len(opened) == 2
    shutil.rmtree(project)
    assert client.post("/api/open", json=dict(kind="export", run_id=folder.name, project_id="changzhou-demo", version=2)).status_code == 200
    assert opened[-1] == api.record(folder)[0] / "project/exports/v2"


def test_report_open_rejects_a_report_directory_link_outside_archive(local, generator, monkeypatch):
    client, root, _, _, _ = local
    client.post("/api/runs/finish", json=payload())
    client.post("/api/runs/gz-changzhou-demo/report")
    folder = root / "runs/gz-changzhou-demo"
    outside = root / "outside-reports"
    (folder / "report").rename(outside)
    try:
        (folder / "report").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable")
    opened = []
    monkeypatch.setattr(api.os, "startfile", opened.append)
    response = client.post("/api/open", json=dict(kind="report", run_id=folder.name))
    assert response.status_code == 400 and opened == []
