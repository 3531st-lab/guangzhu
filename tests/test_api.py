"""Local API boundaries and native evidence capture; no AGH or model requests."""
import copy
import hashlib
import json
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest

from guangzhu import api
from test_agh_runs import complete, independent_review, resequence

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr("guangzhu.report.ROOT", tmp_path)
    monkeypatch.setattr(api, "reachable", lambda: False)
    monkeypatch.setattr(api, "settings", lambda: dict(agh_runtime="never-executed", agh_home=str(tmp_path / "unused")))
    monkeypatch.setenv("AGH_HOME", "unused-test-home")
    project = tmp_path / "projects/changzhou-demo"
    original = json.loads((ROOT / "data/demo/projects/changzhou-demo/project.json").read_text(encoding="utf-8"))
    original["requirements"] = {"text": "合成要求"}
    api.evidence.write_json(project / "project.json", original)
    for version, parent in [(1, None), (2, 1), (3, None), (4, 1)]:
        api.evidence.write_json(project / f"designs/v{version}.json", dict(version=version, parent_version=parent,
            modules=[dict(id=f"M{version}")], reason="合成", statistics=dict(dc_kw=version * 10)))
        for name, value in [("summary", dict(version=version, yield_kwh=dict(p50=1234))),
                            ("shading", dict(modules=[dict(id=f"M{version}", total_loss_pct=.25)])),
                            ("electrical", dict(strings=[dict(id="S001", module_ids=[f"M{version}"])])),
                            ("rules", dict(items=[]))]:
            api.evidence.write_json(project / f"analysis/v{version}/{name}.json", value)
    api.evidence.write_json(project / "exports/v2/manifest.json", dict(version=2, files={}))
    shutil.copytree(ROOT / "data/demo/projects", tmp_path / "data/demo/projects")
    events = complete()
    events[0]["data"]["key"] = "design-session"
    calls = []

    def native_export(sid, ledger, executable, **kwargs):
        assert executable == "never-executed"
        calls.append(sid)
        exported = independent_review() if sid == "review-session" else copy.deepcopy(events)
        exported[0]["data"]["key"] = sid
        ledger.write_text("".join(json.dumps(row) + "\n" for row in exported), encoding="utf-8")
        return exported

    monkeypatch.setattr(api.evidence, "export_ledger", native_export)
    return TestClient(api.app), tmp_path, project, events, calls


def payload(**extra):
    return dict(project_id="changzhou-demo", session_id="design-session", export_version=2, **extra)


def usage_fixture(root, costs, *, with_ledger=True):
    folder = root / "runs/usage-demo"
    metadata = dict(session="usage-session", started_at="2026-10-02T00:00:00Z", ended_at="2026-10-02T00:01:00Z",
        model_requests=2, tokens=dict(input=91, output=37, cacheRead=200, cacheWrite=0, reasoning=12, extra="discard"))
    api.evidence.write_json(folder / "run.json", metadata)
    events = [dict(seq=1, id="usage-start", type="session/start", data=dict(key="usage-session"))]
    for index, data in enumerate(costs, 2):
        events.append(dict(seq=index, id=f"usage-{index}", type="cost/ledger", origin="system", trust="trusted", data=data))
    if with_ledger:
        (folder / "ledger.agnes.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return folder, metadata


def test_archive_usage_deduplicates_cost_effects_and_preserves_metadata(local):
    client, root, _, _, calls = local
    inference = dict(effectId="fee-1", purpose="inference", billing=dict(source="estimated", usdMicros=120, subscription=False))
    title = dict(effectId="title-1", purpose="title", billing=dict(source="estimated", usdMicros=30), provider_payload="discard")
    folder, metadata = usage_fixture(root, [inference, inference, title, dict(effectId="fee-missing", purpose="inference")])
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    response = client.get("/api/runs/usage-demo")
    assert response.status_code == 200, response.text
    usage = response.json()["usage"]
    assert response.json()["usage_by_session"] == {"usage-session": usage}
    assert usage == dict(session_id="usage-session", started_at=metadata["started_at"], ended_at=metadata["ended_at"],
        model_requests=2, tokens={k: v for k, v in metadata["tokens"].items() if k != "extra"},
        costs=[dict(currency="USD", micros=150)], billing_complete=False, missing_costs=1)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
    assert calls == []


@pytest.mark.parametrize("billing", [None, "invalid", dict(source="estimated", usdMicros=True),
    dict(source="estimated", usdMicros=-1), dict(source="estimated", usdMicros=1.5),
    dict(source="estimated", usdMicros="17"), dict(currency="CNY", estimated=1000),
    dict(source="charged", usdMicros=20)])
def test_usage_missing_or_unrecognized_amount_is_unknown_not_zero(local, billing):
    client, root, _, _, _ = local
    usage_fixture(root, [dict(effectId="fee-1", billing=billing)])
    usage = client.get("/api/runs/usage-demo").json()["usage"]
    assert usage["costs"] == [] and usage["missing_costs"] == 1 and not usage["billing_complete"]


def test_usage_missing_ledger_does_not_invent_zero_missing_rows(local):
    client, root, _, _, _ = local
    usage_fixture(root, [], with_ledger=False)
    usage = client.get("/api/runs/usage-demo").json()["usage"]
    assert usage["costs"] == [] and usage["missing_costs"] is None and not usage["billing_complete"]


def test_usage_adjustment_does_not_conflict_with_or_duplicate_original_effect(local):
    client, root, _, _, _ = local
    fee = dict(effectId="same-fee", billing=dict(source="estimated", usdMicros=120))
    adjustment = fee | dict(adjustment=True, billing=dict(source="estimated", usdMicros=50))
    usage_fixture(root, [fee, adjustment, fee])
    usage = client.get("/api/runs/usage-demo").json()["usage"]
    assert usage["costs"] == [dict(currency="USD", micros=120)]
    assert usage["billing_complete"] is True and usage["missing_costs"] == 0


def test_usage_keeps_unknown_currency_separate_and_accepts_explicit_estimated_zero(local):
    client, root, _, _, _ = local
    folder, _ = usage_fixture(root, [dict(effectId="usd", billing=dict(source="estimated", usdMicros=0)),
                                    dict(effectId="cny", billing=dict(currency="CNY", estimated=1000))])
    usage = client.get("/api/runs/usage-demo").json()["usage"]
    assert usage["costs"] == [dict(currency="USD", micros=0)]
    assert usage["missing_costs"] == 1 and not usage["billing_complete"]
    ledger = folder / "ledger.agnes.jsonl"
    ledger.write_text("\n".join(ledger.read_text().splitlines()[:2]) + "\n", encoding="utf-8")
    assert client.get("/api/runs/usage-demo").json()["usage"]["billing_complete"] is True


@pytest.mark.parametrize("mutation", ["conflict", "session", "untrusted"])
def test_usage_rejects_conflicting_or_misassociated_native_costs(local, mutation):
    client, root, _, _, _ = local
    cost = dict(effectId="same", billing=dict(source="estimated", usdMicros=2))
    folder, _ = usage_fixture(root, [cost, cost | dict(billing=dict(source="estimated", usdMicros=3))] if mutation == "conflict" else [cost])
    ledger = folder / "ledger.agnes.jsonl"
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    if mutation == "session":
        events[0]["data"]["key"] = "other-session"
    elif mutation == "untrusted":
        events[1]["origin"] = "model"
    ledger.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    response = client.get("/api/runs/usage-demo")
    if mutation == "session":
        assert response.status_code == 200
        assert response.json()["usage"] is None and response.json()["usage_by_session"] == {}
    else:
        assert response.status_code == 400


def test_usage_finish_and_review_replay_keep_sessions_separate(local):
    client, root, _, _, _ = local
    body = client.post("/api/runs/finish", json=payload(review_session_id="review-session")).json()
    assert set(body["usage_by_session"]) == {"design-session", "review-session"}
    assert body["usage"] == body["usage_by_session"]["design-session"]
    detail = client.get("/api/runs/gz-changzhou-demo").json()
    assert detail["usage_by_session"] == body["usage_by_session"]
    alias = next(r["run_id"] for r in client.get("/api/runs").json()["runs"] if r["kind"] == "review")
    review = client.get("/api/runs/" + alias).json()
    assert set(review["usage_by_session"]) == {"review-session"}
    assert review["usage"] == body["usage_by_session"]["review-session"]


def test_actual_003_archive_usage_preserves_quota_missing_billing(monkeypatch):
    monkeypatch.setattr(api, "ROOT", ROOT)
    folder = ROOT / "runs/gz-t14-ui-impossible-003"
    meta = json.loads((folder / "run.json").read_text(encoding="utf-8-sig"))
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob("*") if p.is_file()}
    response = TestClient(api.app).get("/api/runs/" + folder.name)
    assert response.status_code == 200, response.text
    data = response.json()
    design = data["usage_by_session"][meta["session"]]
    review = data["usage_by_session"][meta["review_session_id"]]
    assert design == data["usage"] and design["session_id"] != review["session_id"]
    assert design["tokens"] == meta["tokens"] and design["model_requests"] == meta["model_requests"] == 18
    assert design["costs"] == [dict(currency="USD", micros=67616)]
    assert design["missing_costs"] == 1 and design["billing_complete"] is False
    assert review["costs"] == [dict(currency="USD", micros=0)]
    assert review["missing_costs"] == 0 and review["billing_complete"] is True
    assert hashes == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes}


def test_status_roofs_brief_static_and_progress(local):
    client, _, _, _, calls = local
    assert client.get("/api/status").json()["agh"]["connected"] is False
    roofs = client.get("/api/roofs").json()["roofs"]
    legacy_ids = {"changzhou-demo", "l-shape", "metal-demo-n", "metal-demo-s", "rotated", "south-tower"}
    pitched_ids = {"pitched-gable-demo", "pitched-saw-demo"}
    installation_ids = {'ground-demo', 'carport-demo'}
    livestock_ids = {'grazing-demo', 'barn-demo'}
    assert {roof["id"] for roof in roofs} == legacy_ids | pitched_ids | installation_ids | livestock_ids
    assert len(roofs) == 12 and all(r["area_m2"] > 0 and r["geometry"]["outline"] for r in roofs)
    response = client.post("/api/brief", json=dict(template="changzhou-demo", id="api-demo", text="预算20万元",
        structured=dict(budget_cny_max=200000), review_mode="independent"))
    assert response.status_code == 200 and "独立审核模式" in response.json()["brief"]
    assert response.json()["labels"] and not response.json()["errors"]
    assert client.post("/api/brief", json=dict(template="../escape", id="api-demo", text="要求")).status_code == 422
    steps = client.get("/api/projects/changzhou-demo/progress").json()["steps"]
    assert len(steps) == 10 and steps[1]["status"] == steps[2]["status"] == "completed"
    assert steps[6]["status"] == steps[7]["status"] == "not_started"
    assert client.get("/").status_code == 200
    # T15: after an upgrade the window must revalidate the page scripts instead of reusing the old version's copies.
    assert client.get("/app.js").headers["cache-control"] == "no-cache" and "cache-control" not in client.get("/api/status").headers
    assert calls == []


def test_result_uses_exported_version_and_actual_parent(local):
    client, _, _, _, _ = local
    result = client.get("/api/projects/changzhou-demo/result").json()
    assert result["selected_version"] == result["version"] == 2
    assert result["scene"]["shading"]["modules"][0]["total_loss_pct"] == .25
    older = client.get("/api/projects/changzhou-demo/result?version=4").json()
    assert older["parent_design"]["version"] == 1 and older["selected_version"] == 2
    assert client.get("/api/projects/changzhou-demo/result?version=50").status_code == 404
    assert client.get("/api/projects/missing/result").status_code == 404


def test_finish_captures_original_scene_and_is_idempotent(local):
    client, root, project, _, calls = local
    response = client.post("/api/runs/finish", json=payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert all(c["passed"] for c in body["verification"]["checks"])
    assert body["selected_version"] == 2 and "latest_version" in body["review_prompt"]
    assert "全程使用中文" in body["review_prompt"]
    folder = root / "runs/gz-changzhou-demo"
    capture, metadata, _ = api.record(folder)
    assert metadata["children_complete"] is True
    assert metadata['module_id'] == api.read(project / 'project.json')['equipment']['module_id']
    assert client.get('/api/runs').json()['runs'][0]['module_model'] == 'TSM-550DE19'
    for relative in ("project.json", "analysis/v2/shading.json", "analysis/v2/electrical.json"):
        target = capture / "project" / relative
        assert target.read_bytes() == (project / relative).read_bytes()
        assert metadata["artifacts"]["project/" + relative] == hashlib.sha256(target.read_bytes()).hexdigest()
    before = (capture / "ledger.agnes.jsonl").read_bytes()
    again = client.post("/api/runs/finish", json=payload()).json()
    assert again["verification"] == body["verification"] and calls == ["design-session"]
    assert (capture / "ledger.agnes.jsonl").read_bytes() == before
    assert client.get("/api/runs").json()["runs"][0]["run_id"] == "gz-changzhou-demo"
    shutil.rmtree(project)
    archived = client.get("/api/runs/gz-changzhou-demo").json()
    assert archived["result"]["scene"]["project"] and archived["result"]["scene"]["electrical"]
    assert archived["result"]["missing"] == []


def test_review_association_survives_repeated_design_finish(local):
    client, root, project, _, calls = local
    assert client.post("/api/runs/finish", json=payload()).status_code == 200
    review = dict(version=2, verdict="approve", reviewer_model="agnes-3.0-flash", findings=[])
    api.evidence.write_json(project / "reviews/v2-synthetic.json", review)
    result = client.post("/api/runs/finish", json=payload(review_session_id="review-session")).json()
    assert result["verification"]["passed"] and result["verification"]["review"]["passed"]
    assert result["result"]["reviews"] == [review]
    assert result["result"]["review_files"] == {"v2-synthetic.json": review}
    assert result["verification"]["review"]["associations"][0]["session"] == "review-session"
    again = client.post("/api/runs/finish", json=payload()).json()
    assert again["verification"] == result["verification"] and calls == ["design-session", "review-session"]
    detail = client.get("/api/runs/gz-changzhou-demo").json()
    assert detail["run"]["review_session_id"] == "review-session"
    assert {n["session"] for n in detail["timeline"]["nodes"]} == {"design-session", "review-session"}


def test_new_export_creates_new_capture_without_overwriting_history(local):
    client, root, project, events, calls = local
    assert client.post("/api/runs/finish", json=payload()).status_code == 200
    old = api.record(root / "runs/gz-changzhou-demo")[0]
    before = (old / "ledger.agnes.jsonl").read_bytes()
    for e in events:
        if e["type"] == "tool/call" and api.evidence.tool_name(e) == "gz_export":
            e["data"]["args"]["version"] = 4
            use = e["data"]["toolUseId"]
    result = next(e for e in events if e["type"] == "tool/result" and e["data"]["toolUseId"] == use)
    result["data"]["content"][0]["text"] = json.dumps(dict(ok=True, version=4))
    api.evidence.write_json(project / "exports/v4/manifest.json", dict(version=4, files={}))
    answer = client.post("/api/runs/finish", json=payload() | dict(export_version=4)).json()
    assert answer["verification"]["passed"] is False and answer["review_prompt"] is None
    assert api.record(root / "runs/gz-changzhou-demo")[0] != old
    assert (old / "ledger.agnes.jsonl").read_bytes() == before and len(calls) == 2


@pytest.mark.parametrize("change", [dict(project_id="another"), dict(export_version=3), dict(export_version=True),
    dict(project_id="../escape"), dict(session_id="--export"), dict(session_id="bad\x00session")])
def test_finish_rejects_invalid_or_mismatched_identity(local, change):
    client, root, _, _, _ = local
    response = client.post("/api/runs/finish", json=payload() | change)
    assert response.status_code == 400 and response.json()["errors"]
    assert not (root / "runs/gz-another/run.json").exists()


def test_scene_hash_tamper_is_missing_not_silently_borrowed(local):
    client, root, _, _, _ = local
    client.post("/api/runs/finish", json=payload())
    capture = api.record(root / "runs/gz-changzhou-demo")[0]
    api.evidence.write_json(capture / "project/analysis/v2/shading.json", dict(modules=[]))
    result = client.get("/api/runs/gz-changzhou-demo").json()["result"]
    assert result["scene"]["shading"] is None and "shading" in result["missing"]
    assert client.get("/api/projects/changzhou-demo/result").json()["scene"]["shading"] is not None


def test_open_only_allows_three_targets_and_redacts_private_fields(local, monkeypatch):
    client, root, project, _, _ = local
    opened = []
    monkeypatch.setattr(api.webbrowser, "open", opened.append)
    monkeypatch.setattr(api.os, "startfile", lambda p: opened.append(str(p)))
    assert client.post("/api/open", json=dict(kind="agh")).status_code == 200
    assert opened.pop() == api.AGH_URL + "/"
    assert client.post("/api/open", json=dict(kind="agh", session_id="parent/child")).status_code == 200
    assert opened.pop().endswith("parent%2Fchild")
    assert client.post("/api/open", json=dict(kind="export", project_id="changzhou-demo", version=2)).status_code == 200
    assert client.post("/api/open", json=dict(kind="run", run_id="../escape")).status_code == 400
    assert client.post("/api/open", json=dict(kind="file", path=str(root))).status_code == 400
    assert len(opened) == 1
    original = json.loads((project / "project.json").read_text(encoding="utf-8"))
    original.update(api_key="example-key", debug=str(Path.home() / "private"))
    (project / "project.json").write_text(json.dumps(original), encoding="utf-8")
    text = client.get("/api/projects/changzhou-demo/result").text
    assert "example-key" not in text and "api_key" not in text and str(Path.home()) not in text


def test_saved_t10_run_has_backfilled_selected_scene_and_keeps_candidate_missing_explicit():
    client = TestClient(api.app)
    response = client.get("/api/runs/t10-impossible-007")
    assert response.status_code == 200
    data = response.json()
    assert data["verification"]["passed"] and data["result"]["selected_version"] == 6
    assert data["result"]["scene"]["project"]["id"] == "t10-impossible-007"
    assert data["result"]["missing"] == []
    assert data["run_options"]["review"]["enabled"] is True
    assert data["result"]["compare"]["ok"] and data["result"]["crosscheck"]["ok"]
    candidate = api.result_data("t10-impossible-007", version=9, folder=ROOT / "runs/t10-impossible-007")
    assert candidate["scene"]["electrical"] is None and candidate["missing"] == ["electrical"]


def test_partial_export_failure_can_retry_without_deleting_evidence(local, monkeypatch):
    client, root, _, _, calls = local
    original = api.evidence.export_ledger
    def fail(sid, ledger, executable, **kw):
        ledger.write_text("synthetic partial evidence\n", encoding="utf-8")
        raise api.subprocess.CalledProcessError(1, ["never-executed"])
    monkeypatch.setattr(api.evidence, "export_ledger", fail)
    assert client.post("/api/runs/finish", json=payload()).status_code == 400
    partial = next((root / "runs/gz-changzhou-demo/captures").glob("*/ledger.agnes.jsonl"))
    assert client.get("/api/runs").json()["runs"][0]["verification"]["passed"] is False
    monkeypatch.setattr(api.evidence, "export_ledger", original)
    assert client.post("/api/runs/finish", json=payload()).status_code == 200
    assert partial.read_text(encoding="utf-8") == "synthetic partial evidence\n"
    assert len(list(partial.parent.parent.iterdir())) == 2 and calls == ["design-session"]


def test_fallback_weather_requires_matching_site_and_original_hash(local):
    client, root, project, _, _ = local
    shutil.rmtree(project / "analysis")
    shutil.copytree(ROOT / "data/demo/weather", root / "data/demo/weather")
    data = client.get("/api/projects/changzhou-demo/progress").json()
    assert data["steps"][3]["status"] == "completed" and data["weather"]["source"] == "nasa"
    weather = root / "data/demo/weather" / data["weather"]["data_file"]
    weather.write_bytes(b"corrupt")
    data = client.get("/api/projects/changzhou-demo/progress").json()
    assert data["steps"][3]["status"] == "not_started" and data["weather"] is None


def test_result_rejects_directory_link_escape(local):
    client, root, project, _, _ = local
    shading = project / "analysis/v2/shading.json"
    shading.unlink()
    outside = root / "other.json"
    outside.write_text('{"modules":[]}', encoding="utf-8")
    try:
        shading.symlink_to(outside)
    except OSError:
        pytest.skip("Windows symlink permission unavailable")
    assert client.get("/api/projects/changzhou-demo/result").status_code == 400


@pytest.mark.parametrize("change,expected", [({"text": ""}, "1至200字"), ({"text": "长" * 201}, "1至200字"),
    ({"max_rounds": 7}, "1至6"), ({"max_rounds": 1.5}, "整数"), ({"review": "yes"}, "是否独立审核"),
    ({"reviewer_model": ""}, "审核模型"), ({"structured": {"budget_cny_max": -1}}, "数值超出"),
    ({"review_mode": "not-a-mode"}, "审核模式"), ({"unexpected": "PRIVATE_INPUT"}, "不支持"),
    ({"template": "../escape"}, "编号")])
def test_brief_errors_are_short_chinese_not_pydantic_text(local, change, expected):
    client, _, _, _, _ = local
    response = client.post("/api/brief", json=dict(template="changzhou-demo", id="api-demo", text="需求") | change)
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any(expected in error for error in errors)
    assert all(any("\u4e00" <= char <= "\u9fff" for char in error) for error in errors)
    assert not any(word in " ".join(errors) for word in ("String", "Input", "Value error", "PRIVATE_INPUT", "not-a-mode"))


def test_progress_cached_comparison_and_crosscheck_match_exported_version(local):
    client, root, project, _, _ = local
    compare = dict(ok=True, base_version=2, options=[dict(version=4, dc_kw=10)])
    crosscheck = dict(ok=True, version=2, specific_yield_kwh_kwp=dict(a=1250, b=1260, c=1255))
    api.evidence.write_json(project / "analysis/v2/compare.json", compare)
    api.evidence.write_json(project / "analysis/v2/crosscheck.json", crosscheck)
    api.evidence.write_json(project / "analysis/v4/crosscheck.json", crosscheck | dict(version=4))
    data = client.get("/api/projects/changzhou-demo/progress").json()
    assert data["active_version"] == 2 and data["compare"] == compare and data["crosscheck"] == crosscheck
    assert [s["status"] for s in data["steps"][6:8]] == ["completed", "completed"]
    result = client.get("/api/projects/changzhou-demo/result").json()
    assert result["selected_version"] == 2 and result["compare"] == compare and result["crosscheck"] == crosscheck
    api.evidence.write_json(project / "analysis/v2/crosscheck.json", crosscheck | dict(version=1))
    data = client.get("/api/projects/changzhou-demo/progress").json()
    assert data["steps"][6]["status"] == "completed" and data["steps"][7]["status"] == "not_started"


def test_before_export_progress_follows_original_compare_base_not_new_candidate(local):
    client, _, project, _, _ = local
    shutil.rmtree(project / "exports")
    api.evidence.write_json(project / "analysis/v2/compare.json", dict(ok=True, base_version=2, options=[]))
    data = client.get("/api/projects/changzhou-demo/progress").json()
    assert data["active_version"] == 2 and data["design"]["version"] == 4
    assert data["steps"][6]["status"] == "completed" and data["steps"][7]["status"] == "not_started"


@pytest.mark.parametrize("version,invalid", [(2, False), (2, True), (1, False), (1, True)])
def test_archived_design_and_parent_require_their_original_sha(local, version, invalid):
    client, root, _, _, _ = local
    assert client.post("/api/runs/finish", json=payload()).status_code == 200
    capture = api.record(root / "runs/gz-changzhou-demo")[0]
    path = capture / f"project/designs/v{version}.json"
    if invalid:
        path.write_bytes(b"incomplete JSON")
    else:
        value = json.loads(path.read_text(encoding="utf-8"))
        value["modules"] = [{"id": "not-in-original-snapshot"}]
        path.write_text(json.dumps(value), encoding="utf-8")
    response = client.get("/api/runs/gz-changzhou-demo")
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["selected_version"] == result["version"] == 2
    field = "design" if version == 2 else "parent_design"
    assert result[field] is None and result["scene"][field] is None and field in result["missing"]
    assert "not-in-original-snapshot" not in response.text
    assert version not in [row["version"] for row in result["versions"]]


def test_archived_missing_parent_is_explicit_but_root_design_has_no_missing_parent(local):
    client, root, _, _, _ = local
    assert client.post("/api/runs/finish", json=payload()).status_code == 200
    capture = api.record(root / "runs/gz-changzhou-demo")[0]
    root_design = client.get("/api/runs/gz-changzhou-demo?version=1").json()["result"]
    assert root_design["parent_design"] is None and "parent_design" not in root_design["missing"]
    (capture / "project/designs/v1.json").unlink()
    result = client.get("/api/runs/gz-changzhou-demo").json()["result"]
    assert result["design"]["parent_version"] == 1 and result["parent_design"] is None
    assert "parent_design" in result["missing"]


def test_nested_review_is_listed_with_stable_single_segment_id_and_own_replay(local, monkeypatch):
    client, root, project, _, _ = local
    assert client.post("/api/runs/finish", json=payload(review_session_id="review-session")).status_code == 200
    rows = client.get("/api/runs").json()["runs"]
    nested = next(row for row in rows if row["kind"] == "review")
    alias = nested["run_id"]
    assert alias.startswith("review-") and len(alias) == 71 and "/" not in alias
    assert nested["session"] == "review-session"
    assert nested["verification"]["scope"] == "independent-review"
    assert nested["verification"]["passed"] and nested["verification"]["checks"] == []
    assert nested["verification"]["review"]["passed"]
    assert nested["selected_version"] == 2 and nested["parent_run_id"] == "gz-changzhou-demo"
    detail = client.get("/api/runs/" + alias).json()
    assert detail["run"]["kind"] == "review" and detail["run"]["session"] == "review-session"
    assert detail["run"]["parent_run_id"] == "gz-changzhou-demo"
    assert detail["run_options"]["review"] == dict(enabled=True, mode="independent")
    assert {n["session"] for n in detail["timeline"]["nodes"]} == {"review-session"}
    assert detail["result"]["selected_version"] == 2
    opened = []
    monkeypatch.setattr(api.os, "startfile", lambda p: opened.append(Path(p)))
    assert client.post("/api/open", json=dict(kind="run", run_id=alias)).status_code == 200
    assert opened[0].is_relative_to(root / "runs/gz-changzhou-demo/reviews")
    assert client.post("/api/runs/finish", json=payload()).status_code == 200
    assert next(r for r in client.get("/api/runs").json()["runs"] if r["kind"] == "review")["run_id"] == alias
    assert client.get("/api/runs/review-" + "0" * 64).status_code == 404


def test_failed_nested_review_remains_separate_from_parent_and_other_review(local):
    client, root, _, _, _ = local
    assert client.post("/api/runs/finish", json=payload(review_session_id="review-session")).status_code == 200
    original = next(r for r in client.get("/api/runs").json()["runs"] if r["kind"] == "review")
    api.evidence.write_json(root / "runs/gz-changzhou-demo/reviews/failed/run.json",
        dict(session="failed-review", project_id="changzhou-demo"))
    rows = client.get("/api/runs").json()["runs"]
    failed = next(r for r in rows if r.get("session") == "failed-review")
    assert failed["kind"] == "review" and not failed["verification"]["passed"]
    assert failed["run_id"] != original["run_id"]
    assert next(r for r in rows if r["run_id"] == "gz-changzhou-demo")["verification"]["passed"]


def test_design_project_name_containing_review_is_not_an_independent_review(local):
    client, root, _, _, _ = local
    api.evidence.write_json(root / "runs/gz-roof-review-001/run.json", dict(session="design-session"))
    record = next(r for r in client.get("/api/runs").json()["runs"] if r["run_id"] == "gz-roof-review-001")
    assert record["kind"] == "design"
    detail = client.get("/api/runs/gz-roof-review-001").json()
    assert detail["run"]["kind"] == "design" and detail["run_options"] == {}


def legacy_review_pair(root):
    child, parent = root / "runs/old-review", root / "runs/old-design"
    events = independent_review()
    sid = events[0]["data"]["key"]
    child.mkdir(parents=True)
    ledger = child / "ledger.agnes.jsonl"
    ledger.write_text("".join(json.dumps(row) + "\n" for row in events), encoding="utf-8")
    api.evidence.write_json(child / "run.json", dict(session=sid, project_id="changzhou-demo", run_id=child.name))
    api.evidence.write_json(child / "verification.json", dict(passed=False, checks=[dict(passed=False)] * 4,
        review=dict(requested=False, passed=None, mode="child")))
    api.evidence.write_json(parent / "run.json", dict(session="design-session", project_id="changzhou-demo"))
    certificate = dict(passed=True, checks=[dict(passed=True)] * 4, verified_exports=[dict(version=2)],
        review=dict(requested=True, passed=True, mode="independent",
            independent=[dict(session=sid, actual_model_verified=True, valid=True, passed=True, high=False, versions=[2])],
            associations=[dict(run=child.name, session=sid, ledger_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest())]))
    api.evidence.write_json(parent / "verification.json", certificate)
    return child, parent, certificate


@pytest.mark.parametrize("mutation", [None, "ledger_bytes", "corrupt_ledger", "metadata_uuid", "association_uuid", "row_uuid",
                                      "actual_ledger_uuid", "wrong_project", "no_certificate", "unverified_model"])
def test_legacy_review_pass_requires_parent_certificate_and_exact_original_ledger(local, mutation):
    client, root, _, _, _ = local
    child, parent, certificate = legacy_review_pair(root)
    if mutation == "ledger_bytes":
        with (child / "ledger.agnes.jsonl").open("a", encoding="utf-8") as stream:
            stream.write("\n")
    elif mutation == "corrupt_ledger":
        (child / "ledger.agnes.jsonl").write_text("invalid ledger bytes", encoding="utf-8")
    elif mutation == "metadata_uuid":
        api.evidence.write_json(child / "run.json", dict(session="wrong-session", project_id="changzhou-demo"))
    elif mutation == "association_uuid":
        certificate["review"]["associations"][0]["session"] = "wrong-session"
    elif mutation == "row_uuid":
        certificate["review"]["independent"][0]["session"] = "wrong-session"
    elif mutation == "actual_ledger_uuid":
        ledger = child / "ledger.agnes.jsonl"
        events = api.evidence.read_events(ledger)
        events[0]["data"]["key"] = "wrong-session"
        ledger.write_text("".join(json.dumps(row) + "\n" for row in events), encoding="utf-8")
        certificate["review"]["associations"][0]["ledger_sha256"] = hashlib.sha256(ledger.read_bytes()).hexdigest()
    elif mutation == "wrong_project":
        api.evidence.write_json(parent / "run.json", dict(session="design-session", project_id="other-project"))
    elif mutation == "no_certificate":
        certificate["review"]["associations"] = []
    elif mutation == "unverified_model":
        certificate["review"]["independent"][0]["actual_model_verified"] = False
    api.evidence.write_json(parent / "verification.json", certificate)
    originals = {p: p.read_bytes() for p in (child / "run.json", child / "verification.json", parent / "verification.json")}
    rows = client.get("/api/runs").json()["runs"]
    listed = next(row for row in rows if row["run_id"] == child.name)
    response = client.get("/api/runs/" + child.name)
    detail = response.json()
    verifications = [listed["verification"]]
    if mutation == "corrupt_ledger":
        assert response.status_code == 400 and detail["errors"]
    else:
        assert response.status_code == 200 and detail["run"]["kind"] == "review"
        verifications.extend([detail["verification"], detail["result"]["verification"]])
    for verification in verifications:
        assert verification["scope"] == "independent-review" and verification["checks"] == []
        assert verification["passed"] is (True if mutation is None else None)
        assert verification["review"]["state"] == ("verified" if mutation is None else "unverified")
    assert listed["kind"] == "review"
    assert listed["selected_version"] == (2 if mutation is None else None)
    assert originals == {p: p.read_bytes() for p in originals}


def test_actual_t10_old_review_certificate_is_project_session_and_sha_bound(monkeypatch):
    child = ROOT / "runs/t10-impossible-007-review-003"
    if not (child / "run.json").is_file():
        pytest.skip("Real T10 independent-review snapshot is not included in this checkout")
    monkeypatch.setattr(api, "ROOT", ROOT)
    originals = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in
        (child / "run.json", child / "verification.json", ROOT / "runs/t10-impossible-007/verification.json")}
    original = json.loads((child / "verification.json").read_text(encoding="utf-8"))
    assert original["passed"] is False and original["review"]["passed"] is None
    client = TestClient(api.app)
    row = next(row for row in client.get("/api/runs").json()["runs"] if row["run_id"] == child.name)
    assert row["kind"] == "review" and row["selected_version"] == 6
    assert row["verification"]["passed"] is True and row["verification"]["checks"] == []
    assert row["verification"]["review"]["session"] == "58ca40f1-b88b-424f-8ff4-e956ddd3ad38"
    assert row["verification"]["certificate"]["ledger_sha256"] == "6af712f492b249d17f8e0096fbffb03218f422098c04091314da1a07d70ce39b"
    assert originals == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in originals}


def test_public_nasa_metadata_stays_byte_exact_and_interrupted_scene_copy_recovers(local, monkeypatch):
    client, root, project, _, calls = local
    public_header = dict(title="NASA/POWER Source Native Resolution Hourly Data", api=dict(version="v2.10.2", name="POWER Hourly API"), sources=["MERRA2"])
    for name, value in [("shading", dict(modules=[], metadata=dict(weather=dict(nasa_header=public_header)))),
                        ("electrical", dict(strings=[], temperature=dict(nasa=dict(metadata=dict(nasa_header=public_header)))))]:
        api.evidence.write_json(project / f"analysis/v2/{name}.json", value)
        # The existing generic writer intentionally removes all header-like fields.
        (project / f"analysis/v2/{name}.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    original = api.snapshot_scene
    def interrupted(capture, project_id):
        (capture / "project/project.json").write_bytes((project / "project.json").read_bytes())
        raise ValueError("synthetic interrupted scene copy")
    monkeypatch.setattr(api, "snapshot_scene", interrupted)
    assert client.post("/api/runs/finish", json=payload()).status_code == 400
    capture = next((root / "runs/gz-changzhou-demo/captures").iterdir())
    ledger_before = (capture / "ledger.agnes.jsonl").read_bytes()
    assert not (root / "runs/gz-changzhou-demo/run.json").exists()
    monkeypatch.setattr(api, "snapshot_scene", original)
    response = client.post("/api/runs/finish", json=payload())
    assert response.status_code == 200, response.text
    assert response.json()["selected_version"] == 2 and calls == ["design-session"]
    assert (capture / "ledger.agnes.jsonl").read_bytes() == ledger_before
    metadata = json.loads((capture / "run.json").read_text(encoding="utf-8"))
    assert metadata["scene_snapshot_complete"]
    for name in ("shading", "electrical"):
        path = capture / f"project/analysis/v2/{name}.json"
        assert path.read_bytes() == (project / f"analysis/v2/{name}.json").read_bytes()
        assert metadata["artifacts"][f"project/analysis/v2/{name}.json"] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("private", [dict(authorization="example-token"), dict(api_key="example-key"), dict(headers={"other": "value"})])
def test_nasa_public_header_does_not_allow_nested_private_fields(private):
    assert not api.scene_is_public(dict(metadata=dict(nasa_header=private)))


def test_real_cz003_scene_metadata_is_public_read_only():
    project = ROOT / "projects/t14-changzhou-003"
    if not project.exists():
        project = next((ROOT / "runs/gz-t14-changzhou-003/captures").glob("*/project"), project)
    if not project.exists():
        pytest.skip("CZ003 real snapshot is not included in this checkout")
    paths = [project / "project.json"] + list(project.glob("analysis/v*/shading.json")) + list(project.glob("analysis/v*/electrical.json"))
    assert paths and all(api.scene_is_public(json.loads(path.read_text(encoding="utf-8"))) for path in paths)


def test_selected_comparison_candidate_matches_its_base_cache_and_ignores_unrelated_newer_cache(local):
    client, _, project, _, _ = local
    selected = dict(ok=True, base_version=1, options=[dict(version=2, dc_kw=20), dict(version=3, dc_kw=30)])
    unrelated = dict(ok=True, base_version=4, options=[dict(version=5)])
    api.evidence.write_json(project / "analysis/v1/compare.json", selected)
    api.evidence.write_json(project / "analysis/v4/compare.json", unrelated)
    result = client.get("/api/projects/changzhou-demo/result").json()
    assert result["selected_version"] == 2 and result["compare"] == selected
    progress = client.get("/api/projects/changzhou-demo/progress").json()
    assert progress["active_version"] == 2 and progress["compare"] == selected
    assert progress["steps"][6]["status"] == "completed"
    assert client.get("/api/projects/changzhou-demo/result?version=3").json()["compare"] == selected
    assert client.get("/api/projects/changzhou-demo/result?version=4").json()["compare"] == unrelated


def test_archived_compare_candidate_uses_own_project_ledger_not_current_project(local):
    client, root, project, events, _ = local
    original = dict(ok=True, base_version=1, options=[dict(version=2, dc_kw=20)])
    call = copy.deepcopy(next(e for e in events if e["type"] == "tool/call"))
    result = copy.deepcopy(next(e for e in events if e["type"] == "tool/result"))
    call["data"].update(name="mcp_guangzhu_test_gz_compare_options", toolUseId="api-compare",
                        args=dict(project_id="changzhou-demo", base_version=1))
    result["data"].update(toolUseId="api-compare", content=[dict(type="text", text=json.dumps(original))])
    events[:] = resequence(events + [call, result])
    assert client.post("/api/runs/finish", json=payload()).status_code == 200
    api.evidence.write_json(project / "analysis/v1/compare.json", original | dict(options=[dict(version=2, dc_kw=999)]))
    result = client.get("/api/runs/gz-changzhou-demo").json()["result"]
    assert result["compare"] == original


def test_real_cz003_candidate_compare_is_exact_native_return_read_only():
    folder = ROOT / "runs/gz-t14-changzhou-003"
    if not (folder / "run.json").exists():
        pytest.skip("CZ003 root archive not included in this checkout")
    result = api.result_data("t14-changzhou-003", folder=folder)
    assert result["selected_version"] == 12
    assert result["compare"]["base_version"] == 3
    assert [row["version"] for row in result["compare"]["options"]] == [6, 9, 12]
    native = api.tool_result(api.full_results(folder), "gz_compare_options", 12)
    assert result["compare"] == native

@pytest.mark.parametrize("mode", ["passed", "latest", "missing", "empty"])
def test_unexported_result_chooses_real_pass_or_latest_valid_and_keeps_export_absent(local, mode):
    client, _, project, _, _ = local
    shutil.rmtree(project / "exports")
    if mode == "empty":
        shutil.rmtree(project / "designs")
    elif mode == "passed":
        api.evidence.write_json(project / "analysis/v2/rules.json", dict(hard_failed=0))
        api.evidence.write_json(project / "analysis/v3/rules.json", dict(hard_failed=0))
    elif mode == "latest":
        api.evidence.write_json(project / "analysis/v4/rules.json", dict(hard_failed=1))
    else:
        for path in (project / "analysis").glob("v*/rules.json"):
            path.unlink()
    data = client.get("/api/projects/changzhou-demo/result").json()
    assert data["selected_version"] is None
    assert data["version"] == (None if mode == "empty" else 3 if mode == "passed" else 4)
    assert data["display_passed"] is (mode == "passed")
    if mode != "empty":
        explicit = client.get("/api/projects/changzhou-demo/result?version=1").json()
        assert explicit["version"] == explicit["design"]["version"] == 1
        assert explicit["scene"]["electrical"]["strings"][0]["module_ids"] == ["M1"]
        assert explicit["selected_version"] is None
        explicit_three = client.get("/api/projects/changzhou-demo/result?version=3").json()
        assert explicit_three["version"] == explicit_three["design"]["version"] == 3
        assert explicit_three["selected_version"] is None
    else:
        assert data["design"] is None and data["versions"] == []


def test_roof_placeholders_resolve_actual_assumptions_and_preserve_non_null_override(local, monkeypatch):
    client, root, _, _, _ = local
    from guangzhu import economics
    defaults = economics.load_assumptions()
    defaults["capex_cny_per_w"]["value"] = 3.71
    defaults["price_export_cny_kwh"]["value"] = .456
    monkeypatch.setattr(economics, "load_assumptions", lambda: defaults)
    path = root / "data/demo/projects/changzhou-demo/project.json"
    project = api.read(path)
    project["economics"].update(capex_cny_per_w=None, price_export_cny_kwh=None, price_self_cny_kwh=.8)
    api.evidence.write_json(path, project)
    data = next(r for r in client.get("/api/roofs").json()["roofs"] if r["id"] == "changzhou-demo")
    assert data["defaults"]["capex_cny_per_w"] == 3.71
    assert data["defaults"]["price_export_cny_kwh"] == .456
    assert data["defaults"]["price_self_cny_kwh"] == .8
    assert data["project"]["economics"]["capex_cny_per_w"] is None

def test_archived_unexported_default_uses_hashed_rules_and_never_borrows_live_pass(local, monkeypatch):
    client, root, project, _, _ = local
    shutil.rmtree(project / "exports")
    api.evidence.write_json(project / "analysis/v2/rules.json", dict(hard_failed=0))
    folder = root / "runs/gz-unexported"
    shutil.copytree(project, folder / "project")
    artifacts = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (folder / "project").rglob("*") if p.is_file()}
    api.evidence.write_json(folder / "run.json", dict(session="offline-session", project_id="changzhou-demo", artifacts=artifacts))
    result = client.get("/api/runs/gz-unexported").json()["result"]
    assert client.get("/api/runs").json()["runs"][0]["display_version"] == result["version"] == 2
    for version in [1, 3]:
        explicit = client.get(f"/api/runs/gz-unexported?version={version}").json()["result"]
        assert explicit["version"] == explicit["design"]["version"] == version
        assert explicit["selected_version"] is None
    api.evidence.write_json(folder / "project/analysis/v2/rules.json", dict(hard_failed=1))
    result = client.get("/api/runs/gz-unexported").json()["result"]
    assert result["version"] == 4 and not result["display_passed"]
    assert api.read(project / "analysis/v2/rules.json")["hard_failed"] == 0
    with monkeypatch.context() as patch:
        for method in ("read_bytes", "read_text"):
            original = getattr(Path, method)
            def small(path, *args, _read=original, **kwargs):
                assert path.name not in ("ledger.agnes.jsonl", "timeline.json", "shading.json", "electrical.json", "project.json")
                assert path.parent.name != "designs"
                return _read(path, *args, **kwargs)
            patch.setattr(Path, method, small)
        row = next(row for row in client.get("/api/runs").json()["runs"] if row["run_id"] == folder.name)
        assert row["display_version"] == 4 and row["selected_version"] is None and not row["can_report"]


def test_runs_prefers_explicit_evaluation_flag_before_legacy_run_id(local, monkeypatch):
    client, root, _, _, _ = local
    folder = root / "runs/eval-1003-historical"
    api.evidence.write_json(folder / "run.json", dict(session="sample", evaluation=False))
    monkeypatch.setattr(api, "run_entries", lambda: [(folder.name, folder, "review")])
    row = client.get("/api/runs").json()["runs"][0]
    assert row["evaluation"] is False and row["run_id"] == folder.name


def test_existing_project_refuses_brief_and_exists_includes_empty_directory(local):
    client, root, project, _, calls = local
    for identifier in ("changzhou-demo", "reserved-empty"):
        (root / "projects" / identifier).mkdir(exist_ok=True)
        assert client.get(f"/api/projects/{identifier}/exists").json() == dict(exists=True)
        response = client.post("/api/brief", json=dict(template="changzhou-demo", id=identifier, text="保留通道"))
        assert response.status_code == 409 and response.json()["errors"] == ["项目编号已存在"]
    assert client.get("/api/projects/fresh-project/exists").json() == dict(exists=False)
    assert calls == []
