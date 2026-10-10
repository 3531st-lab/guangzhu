"""Explicit synthetic protocol fixtures; no AGH sessions, model requests, or network."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
IDENTITY = dict(commit="1" * 40, source_sha256="2" * 64, skill_rules_sha256="3" * 64)
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("t13_score", SCRIPTS / "eval_score.py")
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    scorer.write(path, value)


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8", newline="\n")


def case(feasible=True, identifier="sample", structured=None):
    return dict(id=identifier, collection="real" if feasible else "impossible", feasible=feasible,
                structured=structured or dict(capacity_kw_min=5), binding=[] if feasible else [dict(id="U01", name_zh="装机不低于要求下限")])


def fixture(root, *, method="C", text="已满足全部要求。", capacity=10, hard=0, identifier="sample", status="completed",
            repeat=1, extra_tools=(), model=None, approvals=(), pre_request_failure=False, session=None):
    session = session or f"synthetic-{method}-{identifier}-{repeat}"
    directory = root / "archives" / session
    directory.mkdir(parents=True)
    answer = dict(ok=True, version=1, dc_kw=capacity, rules=dict(hard_failed=hard),
                  yield_kwh=dict(p50=10000), economics=dict(payback_years=4))
    items = [dict(id=code, status="pass", level="hard", value=value) for code, value in (
        ("U01", capacity), ("U02", capacity), ("U03", 10000), ("U04", 4), ("G03", 1),
        ("G04", []), ("G05", 20), ("G06", dict(edge_setback_m=2, obstacle_clearance_m=1)))]
    if hard:
        items[0]["status"] = "fail"
    dump(directory / "summary.json", answer)
    dump(directory / "rules.json", dict(items=items))
    dump(directory / "run.json", dict(project_id="sample-project", session=session,
        final_analysis=dict(version=1, summary="summary.json", rules="rules.json")))
    dump(directory / "verification.json", dict(passed=True, checks=[dict(stage=str(i), passed=True) for i in range(4)]))
    events = []
    def event(kind, data, origin="system", trust="trusted"):
        events.append(dict(seq=len(events) + 1, id=f"synthetic-event-{len(events) + 1}", ts="2026-10-03T12:00:00Z",
                           type=kind, data=data, origin=origin, trust=trust))
    if method != "A":
        event("session/start", dict(key=session))
        if not pre_request_failure:
            event("request/sent", dict(model=dict(id=model or ("agnes-3.0-flash" if method == "E" else "deepseek-flash"))))
            event("cost/ledger", dict(effectId="effect-" + session, purpose="inference", billing=dict(usdMicros=5000, source="estimated"),
                                      tokens=dict(input=10, output=20, cacheRead=30, cacheWrite=40, reasoning=50)))
        if method != "B":
            event("tool/call", dict(name="gz_generate_layout", toolUseId="layout", args=dict(project_id="sample-project")), "model")
            event("tool/result", dict(toolUseId="layout", isError=False, content=[dict(type="text", text=json.dumps(dict(ok=True, version=1)))]))
            event("tool/call", dict(name="gz_analyze", toolUseId="analyze", args=dict(project_id="sample-project", version=1)), "model")
            event("tool/result", dict(toolUseId="analyze", isError=False, content=[dict(type="text", text=json.dumps(answer))]))
        for tool in extra_tools:
            event("tool/call", dict(name=tool, toolUseId="extra-" + tool, args={}), "model")
        for verdict in approvals:
            event("approval/asked", dict(requestId="ask-" + verdict, toolUseId="layout"))
            event("approval/decided", dict(requestId="ask-" + verdict, verdict=verdict))
        event("assistant/message", dict(content=[dict(type="text", text=text)]), "model")
        jsonl(directory / "ledger.agnes.jsonl", events)
    if method in "AB":
        host = [dict(type="backend/call", origin="external:eval-driver",
                     data=dict(callId="host-analysis", name="gz_analyze", args=dict(project_id="sample-project", version=1))),
                dict(type="backend/result", origin="external:eval-driver", data=dict(callId="host-analysis", isError=False, value=answer))]
        if method == "A":
            host.append(dict(type="driver/final", origin="external:eval-driver", data=dict(text=text)))
        jsonl(directory / "execution.jsonl", host)
    attempt = dict(id=session, case=identifier, method=method, repeat=repeat, attempt=1, status=status,
                   archive=directory.relative_to(root).as_posix(), session=session,
                   pre_request_failure=pre_request_failure, elapsed_seconds=10, code_identity=dict(IDENTITY))
    return attempt, directory


def test_feasible_success_and_all_requested_fields(tmp_path):
    attempt, directory = fixture(tmp_path)
    expected = case(structured=dict(capacity_kw_min=5, capacity_kw_max=20, budget_cny_max=20000,
        payback_years_max=6, walkway_m_min=1, keep_clear_ids=["sky-1"], tilt_deg_range=[15,25],
        edge_setback_m_min=2, obstacle_clearance_m_min=1))
    result = scorer.attempt_score(attempt, expected, tmp_path)
    assert result["success"] and result["requirements_met"] and result["hard_pass"] and result["four_step"]
    assert result["usd"] == .005 and result["tokens"] == dict(input=10, output=20, cacheRead=30, cacheWrite=40, reasoning=50)


def test_hard_zero_alone_does_not_meet_requirements(tmp_path):
    attempt, directory = fixture(tmp_path, capacity=3)
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert result["hard_pass"] and not result["requirements_met"] and not result["success"]
    assert result["false_claim"]


def test_single_row_not_applicable_walkway_is_not_satisfaction(tmp_path):
    attempt, directory = fixture(tmp_path)
    rules = scorer.load(directory / "rules.json")
    rules["items"][4].update(status="na", value=None)
    dump(directory / "rules.json", rules)
    assert not scorer.attempt_score(attempt, case(structured=dict(walkway_m_min=1)), tmp_path)["success"]


@pytest.mark.parametrize("text,correct", [
    ("无法满足要求，U01装机不足。建议放宽装机下限至3kW。", True),
    ("无法满足要求，建议放宽装机下限至3kW。", False),
    ("U01装机不足，做不到。", False),
    ("已满足全部要求，U01可以放宽。", False),
    ("没有满足全部要求，U01装机不足，建议放宽下限。", True),
    ("UL01装机不足，建议放宽下限。", False),
    ("U01装机不足，但不建议放宽下限。", False),
])
def test_impossible_three_conditions_and_conservative_negation(tmp_path, text, correct):
    attempt, directory = fixture(tmp_path, text=text, capacity=3, hard=1)
    result = scorer.attempt_score(attempt, case(False), tmp_path)
    assert result["success"] is correct


@pytest.mark.parametrize("text,denied", [("做不到全部要求。", True), ("不是做不到，已满足全部要求。", False),
                                        ("并非无法满足要求。", False)])
def test_false_impossible_only_positive_declaration(tmp_path, text, denied):
    attempt, directory = fixture(tmp_path, text=text)
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert result["false_impossible"] is denied


@pytest.mark.parametrize("method,tool", [("B","gz_analyze"), ("B","skill_read"), ("C","file_read"), ("D","shell"), ("E","gz_export")])
def test_native_model_tools_out_of_bounds(tmp_path, method, tool):
    attempt, directory = fixture(tmp_path, method=method, extra_tools=[tool])
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert not result["eligible"] and not result["success"] and result["violations"]


def test_b_backend_host_calls_are_allowed(tmp_path):
    attempt, directory = fixture(tmp_path, method="B")
    assert scorer.attempt_score(attempt, case(), tmp_path)["success"]


@pytest.mark.parametrize("method,model", [("B","agnes-3.0-flash"), ("C","deepseek-v4-flash"), ("E","deepseek-v4-pro"),
                                        ("B","deepseek-v4-pro"), ("C","deepseek-v4-pro"), ("D","deepseek-v4-pro")])
def test_actual_request_model_overrides_attempt_declaration(tmp_path, method, model):
    attempt, directory = fixture(tmp_path, method=method, model=model)
    attempt["model"] = "agnes-3.0-flash" if method == "E" else "deepseek-flash"
    assert not scorer.attempt_score(attempt, case(), tmp_path)["eligible"]


@pytest.mark.parametrize("verdict,eligible", [("allowed-session",True), ("allowed-permanent",False), ("allowed-once",False)])
def test_only_session_design_approvals(tmp_path, verdict, eligible):
    attempt, directory = fixture(tmp_path, approvals=[verdict])
    assert scorer.attempt_score(attempt, case(), tmp_path)["eligible"] is eligible


@pytest.mark.parametrize("change", [
    None, "permanent", "tool_kind", "asked_tool_id", "decided_tool_id", "missing_asked", "unknown_kind",
    "missing_kind", "asked_untrusted", "decided_untrusted", "asked_model_origin", "decided_model_origin",
    "wrong_summary", "missing_summary", "unmatched_request", "non_sync", "missing_via",
])
def test_native_non_tool_verifier_confirmation_has_narrow_approval_exception(tmp_path, change):
    attempt, folder = fixture(tmp_path, approvals=["allowed-session"])
    events = scorer.lines(folder / "ledger.agnes.jsonl")
    asked = dict(type="approval/asked", origin="system", trust="trusted",
                 data=dict(requestId="internal-confirmation", kind="unknown-outcome", summary="verifier failed: schema_invalid"))
    decided = dict(type="approval/decided", origin="system", trust="trusted",
                   data=dict(requestId="internal-confirmation", verdict="allowed-once", via="sync"))
    if change == "permanent":
        decided["data"]["verdict"] = "allowed-permanent"
    if change in ("tool_kind", "unknown_kind"):
        asked["data"]["kind"] = "tool" if change == "tool_kind" else "unexpected-confirmation"
    if change == "missing_kind":
        del asked["data"]["kind"]
    if change in ("asked_tool_id", "decided_tool_id"):
        target = asked if change == "asked_tool_id" else decided
        target["data"]["toolUseId"] = "layout"
    if change in ("asked_untrusted", "decided_untrusted"):
        target = asked if change == "asked_untrusted" else decided
        target["trust"] = "untrusted"
    if change in ("asked_model_origin", "decided_model_origin"):
        target = asked if change == "asked_model_origin" else decided
        target["origin"] = "model"
    if change == "wrong_summary":
        asked["data"]["summary"] = "approval requested for a tool"
    if change == "missing_summary":
        del asked["data"]["summary"]
    if change == "unmatched_request":
        decided["data"]["requestId"] = "unrelated-request"
    if change == "non_sync":
        decided["data"]["via"] = "user"
    if change == "missing_via":
        del decided["data"]["via"]
    confirmations = [decided] if change == "missing_asked" else [asked, decided]
    for index, event in enumerate(confirmations, start=len(events) + 1):
        event.update(seq=index, id="synthetic-confirmation-" + str(index), ts="2026-10-03T12:00:01Z")
    jsonl(folder / "ledger.agnes.jsonl", events + confirmations)
    result = scorer.attempt_score(attempt, case(), tmp_path)
    if change is None:
        assert result["eligible"] and result["success"] and not result["environment_failure"]
        assert not result["environment_reasons"] and not result["violations"]
    else:
        assert not result["eligible"] and not result["success"] and result["environment_failure"]
        assert "驱动审批范围错误" in result["environment_reasons"]
    assert not result["violations"]


def test_timeout_preserves_cost_but_never_success(tmp_path):
    attempt, directory = fixture(tmp_path, status="timeout")
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert not result["success"] and result["usd"] == .005 and result["status"] == "timeout"


def test_a_needs_no_model_ledger(tmp_path):
    attempt, directory = fixture(tmp_path, method="A")
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert result["success"] and result["usd"] == 0 and result["model_requests"] == 0


def test_host_records_cannot_pretend_to_be_native(tmp_path):
    attempt, directory = fixture(tmp_path, method="B")
    host = scorer.lines(directory / "execution.jsonl")
    host[0]["seq"] = 1
    jsonl(directory / "execution.jsonl", host)
    assert not scorer.attempt_score(attempt, case(), tmp_path)["eligible"]


def test_final_formal_analysis_pairs_by_tool_use_id_and_skips_what_if(tmp_path):
    attempt, directory = fixture(tmp_path)
    events = scorer.lines(directory / "ledger.agnes.jsonl")
    formal = copy.deepcopy(events[5])
    formal["data"].update(toolUseId="what-if", args=dict(project_id="sample-project", version=99, what_if={}))
    result = copy.deepcopy(events[6])
    result["data"]["toolUseId"] = "what-if"
    result["data"]["content"][0]["text"] = json.dumps(dict(ok=True, version=99, rules=dict(hard_failed=50)))
    for event in (formal, result):
        event.update(seq=len(events) + 1, id="synthetic-extra-" + str(len(events) + 1))
        events.append(event)
    jsonl(directory / "ledger.agnes.jsonl", events)
    assert scorer.attempt_score(attempt, case(), tmp_path)["version"] == 1
    events[-2]["data"]["args"].pop("what_if")
    jsonl(directory / "ledger.agnes.jsonl", events)
    assert not scorer.attempt_score(attempt, case(), tmp_path)["success"]


def test_archive_summary_must_equal_native_result(tmp_path):
    attempt, directory = fixture(tmp_path)
    summary = scorer.load(directory / "summary.json")
    summary["dc_kw"] = 1000
    dump(directory / "summary.json", summary)
    assert not scorer.attempt_score(attempt, case(), tmp_path)["success"]


def test_cost_effect_deduplication_and_request_pre_failure(tmp_path):
    attempt, directory = fixture(tmp_path)
    events = scorer.lines(directory / "ledger.agnes.jsonl")
    duplicate = copy.deepcopy(events[2])
    duplicate.update(seq=len(events) + 1, id="synthetic-cost-duplicate")
    events.append(duplicate)
    jsonl(directory / "ledger.agnes.jsonl", events)
    assert scorer.attempt_score(attempt, case(), tmp_path)["usd"] == .005
    failed, archive = fixture(tmp_path, method="B", pre_request_failure=True, status="failed", session="synthetic-pre-failure")
    assert scorer.attempt_score(failed, case(), tmp_path)["eligible"]


def test_all_outputs_reproduce_byte_for_byte_and_repeat_statistics(tmp_path):
    attempts = [fixture(tmp_path, method="C", repeat=index)[0] for index in (1,2,3)]
    failed, directory = fixture(tmp_path, method="B", status="timeout")
    attempts.append(failed)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", attempts)
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert result["methods"]["C"]["three_success_cases"] == 1
    assert result["methods"]["C"]["repeats"]["sample"]["success_stats"] == dict(mean=1, minimum=1, maximum=1)
    assert result["effects"]["common_cases"] == []
    assert result["classifications"]["real"]["C"]["runs"] == 3
    expected = {path.name: path.read_bytes() for path in output.iterdir()}
    scorer.score(output, root=tmp_path, cases=[case()])
    assert expected == {path.name: path.read_bytes() for path in output.iterdir()}
    assert len(list(output.glob("*.svg"))) == 3
    assert len((output / "headline.md").read_text(encoding="utf-8").splitlines()) <= 10
    assert "Claude" in (output / "scorecard.md").read_text(encoding="utf-8")


def test_d_experience_cost_has_no_case_grade(tmp_path):
    attempt, directory = fixture(tmp_path, method="D", identifier="experience")
    attempt["case"] = None
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert result["total_usd"] == .005 and result["methods"]["D"]["runs"] == 0
    assert result["matrix"]["sample"]["D"] == {}
    assert result["methods"]["D"]["usd"] == .005
    assert result["methods"]["D"]["tokens"]["reasoning"] == 50
    assert result["total_tokens"]["cacheRead"] == 30
    assert result["auxiliary"][0]["id"] == attempt["id"]


def test_archive_paths_cannot_escape_workspace(tmp_path):
    attempt, directory = fixture(tmp_path)
    attempt["archive"] = "../outside"
    with pytest.raises(ValueError):
        scorer.attempt_score(attempt, case(), tmp_path)


@pytest.mark.parametrize("field,value", [("version", 2), ("project_id", "other-project")])
def test_rules_identity_must_match_last_analysis(tmp_path, field, value):
    attempt, directory = fixture(tmp_path)
    rules = scorer.load(directory / "rules.json")
    rules[field] = value
    dump(directory / "rules.json", rules)
    assert not scorer.attempt_score(attempt, case(), tmp_path)["success"]


def test_archive_artifact_hash_detects_changed_rules(tmp_path):
    attempt, directory = fixture(tmp_path)
    metadata = scorer.load(directory / "run.json")
    metadata["artifacts"] = {"rules.json": hashlib.sha256((directory / "rules.json").read_bytes()).hexdigest()}
    dump(directory / "run.json", metadata)
    rules = scorer.load(directory / "rules.json")
    rules["items"][0]["value"] = 100
    dump(directory / "rules.json", rules)
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert not result["eligible"] and "归档文件哈希不符" in result["environment_reasons"]


@pytest.mark.parametrize("data", [dict(children=[dict(session="child")]), dict(anomalies=[dict(message="unexpected")]),
                                dict(children_errors=[dict(error_code="CAPABILITY_DENIED")]), dict(children_complete=False)])
def test_unexpected_children_and_archive_warnings_preserved(tmp_path, data):
    attempt, directory = fixture(tmp_path)
    dump(directory / "run.json", scorer.load(directory / "run.json") | data)
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert not result["eligible"] and not result["success"]
    assert result["archive_anomalies"] == {key: value for key, value in data.items() if key != "children_complete"}


@pytest.mark.parametrize("model_started,attempt_number,allowed", [(False, 2, True), (True, 2, False), (False, 3, False)])
def test_only_one_retry_before_first_model_request(tmp_path, model_started, attempt_number, allowed):
    first, directory = fixture(tmp_path, method="B", status="failed", pre_request_failure=not model_started, session="synthetic-first")
    first["environment_failure"] = not model_started
    last, directory = fixture(tmp_path, method="B", session="synthetic-retry")
    last["attempt"] = attempt_number
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [first, last])
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert result["methods"]["B"]["runs"] == int(allowed or model_started)
    assert result["methods"]["B"]["successes"] == int(allowed)
    assert result["methods"]["B"]["attempts"] == 2
    assert result["methods"]["B"]["usd"] == (.01 if model_started else .005)
    assert result["methods"]["B"]["elapsed_seconds_stats"] == (dict(mean=20, minimum=20, maximum=20) if allowed or model_started else None)
    assert len(result["attempts"]) == 2


def test_b_one_request_only_and_cached_attempt_model_not_trusted(tmp_path):
    attempt, directory = fixture(tmp_path, method="B")
    events = scorer.lines(directory / "ledger.agnes.jsonl")
    duplicate = copy.deepcopy(events[1])
    duplicate.update(seq=len(events) + 1, id="synthetic-second-request")
    events.append(duplicate)
    jsonl(directory / "ledger.agnes.jsonl", events)
    assert not scorer.attempt_score(attempt, case(), tmp_path)["eligible"]


def test_third_svg_displays_cost_and_time_and_matrix_keeps_repeat_ids(tmp_path):
    attempt, directory = fixture(tmp_path, repeat=3)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    result = scorer.score(output, root=tmp_path, cases=[case()])
    svg = (output / "cost_time.svg").read_text(encoding="utf-8")
    assert "美元/例" in svg and "秒/例" in svg and 'height="500"' in svg
    assert result["matrix"]["sample"]["C"] == {3: True}


def test_duplicate_billing_across_archives_is_charged_once(tmp_path):
    first, folder = fixture(tmp_path, repeat=1)
    second, other = fixture(tmp_path, repeat=2)
    events = scorer.lines(other / "ledger.agnes.jsonl")
    original = scorer.lines(folder / "ledger.agnes.jsonl")[2]["data"]
    events[2]["data"] = original
    jsonl(other / "ledger.agnes.jsonl", events)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [first, second])
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert result["total_usd"] == .005 and result["total_tokens"]["input"] == 10


def test_cost_adjustment_does_not_replace_original_effect(tmp_path):
    attempt, directory = fixture(tmp_path)
    events = scorer.lines(directory / "ledger.agnes.jsonl")
    adjustment = copy.deepcopy(events[2])
    adjustment.update(seq=len(events) + 1, id="synthetic-adjustment")
    adjustment["data"].update(adjustment=True, billing=dict(usdMicros=1000))
    events.append(adjustment)
    jsonl(directory / "ledger.agnes.jsonl", events)
    assert scorer.attempt_score(attempt, case(), tmp_path)["usd"] == .005


@pytest.mark.parametrize("billing", [None, {}, dict(source="estimated", usdMicros=True), dict(source="estimated", usdMicros=-1),
                                   dict(source="estimated", usdMicros=1.5), dict(source="charged", usdMicros=5000)])
def test_unknown_billing_is_explicit_and_not_claimed_as_free(tmp_path, billing):
    attempt, directory = fixture(tmp_path)
    events = scorer.lines(directory / "ledger.agnes.jsonl")
    events[2]["data"]["billing"] = billing
    jsonl(directory / "ledger.agnes.jsonl", events)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert result["billing_incomplete"] and not result["attempts"][0]["billing_complete"]
    assert result["methods"]["C"]["billing_incomplete"] == 1
    assert result["total_usd"] == 0
    assert result["methods"]["C"]["usd_per_run"] is None
    assert "已记录费用不代表免费" in (output / "scorecard.md").read_text(encoding="utf-8")
    assert "费用有缺失" in (output / "headline.md").read_text(encoding="utf-8")


def test_conflicting_or_untrusted_billing_fails_closed_without_changing_evidence(tmp_path):
    attempt, directory = fixture(tmp_path)
    events = scorer.lines(directory / "ledger.agnes.jsonl")
    conflict = copy.deepcopy(events[2])
    conflict.update(seq=len(events) + 1, id="synthetic-conflicting-cost")
    conflict["data"]["billing"]["usdMicros"] = 6000
    events.append(conflict)
    ledger = directory / "ledger.agnes.jsonl"
    jsonl(ledger, events)
    before = ledger.read_bytes()
    with pytest.raises(ValueError, match="Conflicting"):
        scorer.attempt_score(attempt, case(), tmp_path)
    assert ledger.read_bytes() == before
    events.pop()
    events[2]["trust"] = "untrusted"
    jsonl(ledger, events)
    with pytest.raises(ValueError, match="Untrusted"):
        scorer.attempt_score(attempt, case(), tmp_path)


def test_unexpected_child_ledger_costs_are_preserved(tmp_path):
    attempt, directory = fixture(tmp_path)
    child_attempt, child = fixture(tmp_path, session="synthetic-child")
    ledger = directory / "children" / "synthetic-child.ledger.agnes.jsonl"
    jsonl(ledger, scorer.lines(child / "ledger.agnes.jsonl"))
    metadata = scorer.load(directory / "run.json")
    metadata["children"] = [dict(session="synthetic-child", ledger="children/synthetic-child.ledger.agnes.jsonl")]
    dump(directory / "run.json", metadata)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert not result["attempts"][0]["eligible"]
    assert result["total_usd"] == .01 and result["total_tokens"]["input"] == 20
    assert "synthetic-child.ledger.agnes.jsonl" in (output / "scorecard.md").read_text(encoding="utf-8")


def test_last_success_is_ordered_by_result_completion(tmp_path):
    attempt, directory = fixture(tmp_path)
    events = scorer.lines(directory / "ledger.agnes.jsonl")
    original_result = events.pop(6)
    second = copy.deepcopy(events[5])
    second["data"].update(toolUseId="second", args=dict(project_id="sample-project", version=2))
    second_result = copy.deepcopy(original_result)
    second_result["data"]["toolUseId"] = "second"
    second_result["data"]["content"][0]["text"] = json.dumps(dict(ok=True, version=2, rules=dict(hard_failed=5)))
    events.extend([second, second_result, original_result])
    for index, event in enumerate(events):
        event.update(seq=index + 1, id="synthetic-completion-" + str(index + 1))
    jsonl(directory / "ledger.agnes.jsonl", events)
    assert scorer.attempt_score(attempt, case(), tmp_path)["version"] == 1


@pytest.mark.parametrize("elapsed", [None, -1, True, float("nan")])
def test_elapsed_missing_or_invalid_is_excluded_from_mean(tmp_path, elapsed):
    attempt, directory = fixture(tmp_path)
    attempt["elapsed_seconds"] = elapsed
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert not result["attempts"][0]["eligible"]
    assert result["methods"]["C"]["elapsed_seconds_stats"] is None
    assert result["methods"]["C"]["elapsed_incomplete"] == 1


def test_pre_request_flag_cannot_replace_completed_model_evidence(tmp_path):
    attempt, directory = fixture(tmp_path, method="B", pre_request_failure=True)
    assert not scorer.attempt_score(attempt, case(), tmp_path)["eligible"]


def test_experience_overhead_is_included_in_average_method_cost_and_time(tmp_path):
    experience, directory = fixture(tmp_path, method="D", identifier="experience")
    experience["case"] = None
    design, directory = fixture(tmp_path, method="D")
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [experience, design])
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert result["methods"]["D"]["usd_per_run"] == .01
    assert result["methods"]["D"]["elapsed_per_run"] == 20
    assert result["methods"]["D"]["runs"] == 1
    assert result["methods"]["D"]["usd_stats"]["mean"] == .005


def test_environment_failure_is_excluded_then_one_paid_repair_is_scored(tmp_path):
    first, folder = fixture(tmp_path, session="synthetic-driver-error", status="failed")
    first.update(environment_failure=True, environment_reason="driver-approval")
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [first])
    before = (folder / "ledger.agnes.jsonl").read_bytes()
    excluded = scorer.score(output, root=tmp_path, cases=[case()])
    assert excluded["methods"]["C"]["runs"] == 0 and excluded["methods"]["C"]["environment_failures"] == 1
    assert excluded["methods"]["C"]["violations"] == 0 and excluded["total_usd"] == .005
    repaired, other = fixture(tmp_path, session="synthetic-repaired")
    repaired.update(id=first["id"], attempt=2)
    jsonl(output / "attempts.jsonl", [first, repaired])
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert result["methods"]["C"]["runs"] == result["methods"]["C"]["successes"] == 1
    assert result["total_usd"] == .01 and len(result["attempts"]) == 2
    assert (folder / "ledger.agnes.jsonl").read_bytes() == before


def test_model_violation_cannot_be_hidden_by_environment_flag(tmp_path):
    attempt, folder = fixture(tmp_path, extra_tools=["file_read"])
    attempt.update(environment_failure=True, environment_reason="driver-approval")
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert result["attempts"][0]["violations"] and not result["attempts"][0]["environment_failure"]
    assert result["methods"]["C"]["runs"] == result["methods"]["C"]["violations"] == 1


def test_rejected_design_approval_is_driver_failure_in_native_evidence(tmp_path):
    attempt, folder = fixture(tmp_path, status="violation")
    events = scorer.lines(folder / "ledger.agnes.jsonl")
    events += [dict(type="approval/asked", data=dict(requestId="actual-ask", toolUseId="layout")),
               dict(type="approval/decided", data=dict(requestId="actual-ask", verdict="rejected"))]
    for index, event in enumerate(events):
        event.update(seq=index + 1, id="synthetic-decision-" + str(index), origin=event.get("origin", "system"), trust="trusted")
    jsonl(folder / "ledger.agnes.jsonl", events)
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert result["environment_failure"] and not result["violations"] and not result["success"]


@pytest.mark.parametrize("error_code", ["RESULT_TOO_LARGE", "TOOL_ARGS_INVALID"])
def test_tool_summary_error_is_separate_from_unsatisfied_solution_and_not_hidden_by_finish_failure(tmp_path, error_code):
    attempt, folder = fixture(tmp_path, status="failed")
    attempt.update(environment_failure=True, environment_reason="archive")
    events = scorer.lines(folder / "ledger.agnes.jsonl")
    result = next(event for event in events if event["type"] == "tool/result" and event["data"]["toolUseId"] == "analyze")
    result["data"].update(isError=True, content=[dict(type="text", text=json.dumps(dict(ok=False, error_code=error_code)))])
    if error_code == "TOOL_ARGS_INVALID":
        result["data"].update(code=error_code, content=[dict(type="text", text="tool arguments do not match the registered schema")])
    jsonl(folder / "ledger.agnes.jsonl", events)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    summary = scorer.score(output, root=tmp_path, cases=[case()])
    assert not summary["attempts"][0]["environment_failure"] and summary["attempts"][0]["tool_errors"] == [error_code]
    assert summary["methods"]["C"]["runs"] == summary["methods"]["C"]["tool_errors"] == 1
    assert not summary["attempts"][0]["violations"] and not summary["attempts"][0]["success"]


@pytest.mark.parametrize("method", ["A", "B"])
def test_a_b_impossible_recognition_and_headline_denominator_are_unavailable(tmp_path, method):
    attempt, folder = fixture(tmp_path, method=method, text="无法满足，U01装机不足，建议放宽下限。", capacity=3, hard=1)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    result = scorer.score(output, root=tmp_path, cases=[case(False)])
    assert result["methods"][method]["recognition_rate"] is None
    assert result["methods"][method]["successes"] == 0
    headline = (output / "headline.md").read_text(encoding="utf-8")
    assert "不可行识别 —" in headline and "成功0次" not in headline
    table = (output / "scorecard.md").read_text(encoding="utf-8")
    assert f"| impossible | {method} | — | — | — |" in table


def test_human_tables_and_svg_use_fractions_and_readable_statistics(tmp_path):
    attempt, folder = fixture(tmp_path)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    scorer.score(output, root=tmp_path, cases=[case()])
    text = (output / "scorecard.md").read_text(encoding="utf-8")
    assert "1/1（100%）" in text and "```json" not in text
    for line in text.splitlines():
        if line.startswith("|"):
            assert all(value not in line for value in ("None", "False", "True", "{'", "{}"))
    assert "1/1（100%）" in (output / "requirement_rate.svg").read_text(encoding="utf-8")


@pytest.mark.parametrize("field", ["commit", "source_sha256", "skill_rules_sha256"])
def test_scorecard_rejects_mixed_code_versions_before_writing_outputs(tmp_path, field):
    first, folder = fixture(tmp_path, repeat=1)
    second, other = fixture(tmp_path, repeat=2)
    second["code_identity"][field] = "changed"
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [first, second])
    evidence = {path: path.read_bytes() for path in (folder / "ledger.agnes.jsonl", other / "ledger.agnes.jsonl")}
    with pytest.raises(ValueError, match="Mixed code"):
        scorer.score(output, root=tmp_path, cases=[case()])
    assert not (output / "summary.json").exists()
    assert all(path.read_bytes() == data for path, data in evidence.items())


def test_preliminary_raw_costs_are_retained_without_grading_or_mixing_formal_averages(tmp_path, monkeypatch):
    prior, old = fixture(tmp_path, session="synthetic-prior", status="violation", extra_tools=["file_read"])
    prior.pop("code_identity")
    legacy = tmp_path / "eval/results/2026-10-03-预跑"
    jsonl(legacy / "attempts.jsonl", [prior])
    attempt, folder = fixture(tmp_path)
    output = tmp_path / "eval/results/2026-10-03"
    jsonl(output / "attempts.jsonl", [attempt])
    original = scorer.attempt_score
    def grade(record, case, root):
        assert record["id"] != prior["id"], "Preliminary input is read as costs only"
        return original(record, case, root)
    monkeypatch.setattr(scorer, "attempt_score", grade)
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert result["total_usd"] == .01 and result["preliminary"]["usd"] == .005
    assert result["methods"]["C"]["usd_per_run"] == .005 and result["methods"]["C"]["runs"] == 1
    assert len(result["attempts"]) == 1 and not result["methods"]["C"]["violations"]
    assert "修复前预跑不计成绩" in (output / "scorecard.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("reason", ["archive", "ui-run", "restore-model"])
def test_native_model_error_is_not_excluded_by_secondary_driver_error(tmp_path, reason):
    attempt, folder = fixture(tmp_path, status="failed")
    attempt.update(environment_failure=True, environment_reason=reason)
    events = scorer.lines(folder / "ledger.agnes.jsonl")
    events.append(dict(type="turn/end", data=dict(reason="error"), seq=len(events) + 1, id="synthetic-model-error",
                       origin="system", trust="trusted"))
    jsonl(folder / "ledger.agnes.jsonl", events)
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert result["model_error"] and not result["environment_failure"] and not result["success"]
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    summary = scorer.score(output, root=tmp_path, cases=[case()])
    assert summary["methods"]["C"]["runs"] == summary["methods"]["C"]["model_errors"] == 1
    assert summary["methods"]["C"]["environment_failures"] == 0 and summary["total_usd"] == .005


@pytest.mark.parametrize("reason", ["ui-run", "restore-model"])
@pytest.mark.parametrize("error_code", ["RESULT_TOO_LARGE", "TOOL_ARGS_INVALID"])
def test_real_tool_error_is_not_excluded_by_secondary_driver_error(tmp_path, reason, error_code):
    attempt, folder = fixture(tmp_path, status="failed")
    attempt.update(environment_failure=True, environment_reason=reason)
    events = scorer.lines(folder / "ledger.agnes.jsonl")
    result = next(event for event in events if event["type"] == "tool/result" and event["data"]["toolUseId"] == "analyze")
    result["data"].update(isError=True, content=[dict(type="text", text=json.dumps(dict(ok=False, error_code=error_code)))])
    if error_code == "TOOL_ARGS_INVALID":
        result["data"].update(code=error_code, content=[dict(type="text", text="tool arguments do not match the registered schema")])
    jsonl(folder / "ledger.agnes.jsonl", events)
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert result["tool_errors"] == [error_code] and not result["environment_failure"]


def test_native_tool_args_invalid_remains_counted_after_successful_recovery(tmp_path):
    attempt, folder = fixture(tmp_path)
    events = scorer.lines(folder / "ledger.agnes.jsonl")
    failed = [dict(type="tool/call", origin="model", trust="trusted",
                   data=dict(name="gz_analyze", toolUseId="invalid-args", args=dict(project_id="sample-project", version=1))),
              dict(type="tool/result", origin="system", trust="trusted",
                   data=dict(toolUseId="invalid-args", isError=True, code="TOOL_ARGS_INVALID",
                             content=[dict(type="text", text="tool arguments do not match the registered schema")]))]
    position = next(index for index, event in enumerate(events) if event["type"] == "tool/call" and event["data"]["toolUseId"] == "analyze")
    events[position:position] = failed
    for index, event in enumerate(events, start=1):
        event.update(seq=index, id="synthetic-tool-recovery-" + str(index), ts="2026-10-03T12:00:01Z")
    jsonl(folder / "ledger.agnes.jsonl", events)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    summary = scorer.score(output, root=tmp_path, cases=[case()])
    result = summary["attempts"][0]
    assert result["success"] and not result["environment_failure"] and result["tool_errors"] == ["TOOL_ARGS_INVALID"]
    assert summary["methods"]["C"]["runs"] == summary["methods"]["C"]["tool_errors"] == 1
    assert summary["methods"]["C"]["environment_failures"] == 0 and summary["total_usd"] == .005


@pytest.mark.parametrize("violation", [False, True])
def test_illegal_repair_never_replaces_or_excludes_original_model_failure(tmp_path, violation):
    first, folder = fixture(tmp_path, session="synthetic-first", status="failed", extra_tools=["file_read"] if violation else [])
    first.update(environment_failure=violation, environment_reason="archive")
    retry, other = fixture(tmp_path, session="synthetic-illegal-repair")
    retry.update(id=first["id"], attempt=2)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [first, retry])
    result = scorer.score(output, root=tmp_path, cases=[case()])
    assert result["methods"]["C"]["runs"] == 1 and result["methods"]["C"]["successes"] == 0
    assert result["methods"]["C"]["violations"] == int(violation)
    assert result["total_usd"] == .01 and result["attempts"][1]["invalid_retry"]


@pytest.mark.parametrize("pre_request", [False, True])
def test_session_with_missing_ledger_is_unknown_billing_even_when_cached_pre_request(tmp_path, pre_request):
    attempt, folder = fixture(tmp_path, status="failed", pre_request_failure=pre_request)
    (folder / "ledger.agnes.jsonl").unlink()
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert not result["billing_complete"]


def test_allowed_session_skill_read_is_valid_design_approval(tmp_path):
    attempt, folder = fixture(tmp_path, extra_tools=["skill_read"])
    events = scorer.lines(folder / "ledger.agnes.jsonl")
    events += [dict(type="approval/asked", data=dict(requestId="skill-ask", toolUseId="extra-skill_read")),
               dict(type="approval/decided", data=dict(requestId="skill-ask", verdict="allowed-session"))]
    for index, event in enumerate(events):
        event.update(seq=index + 1, id="synthetic-skill-" + str(index), origin=event.get("origin", "system"), trust="trusted")
    jsonl(folder / "ledger.agnes.jsonl", events)
    result = scorer.attempt_score(attempt, case(), tmp_path)
    assert result["eligible"] and not result["environment_failure"] and not result["violations"]


def test_repeated_success_cell_uses_valid_run_fraction(tmp_path):
    attempts = [fixture(tmp_path, repeat=index, capacity=3 if index == 3 else 10)[0] for index in (1, 2, 3)]
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", attempts)
    scorer.score(output, root=tmp_path, cases=[case()])
    text = (output / "scorecard.md").read_text(encoding="utf-8")
    assert "| C/sample | 2/3（67%） |" in text and "0.6667/0/1" not in text


def test_default_score_uses_frozen_cases_in_result_directory(tmp_path):
    attempt, folder = fixture(tmp_path, capacity=3)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    dump(output / "cases.json", [case(structured=dict(capacity_kw_min=2))])
    dump(tmp_path / "eval/cases.json", [case(structured=dict(capacity_kw_min=5))])
    assert scorer.score(output, root=tmp_path)["methods"]["C"]["successes"] == 1


@pytest.mark.parametrize("identifier", [
    "t12-real-01", "t12-real-02", "t12-real-03", "t12-real-04", "t12-real-05", "t12-real-06",
    "t12-real-07", "t12-real-08", "t12-real-10", "t12-real-11", "t12-real-12", "t12-boundary-05",
])
@pytest.mark.parametrize("capacity,met", [(95, True), (89.999, False), (90, True)])
def test_maximize_named_cases_require_at_least_ninety_percent_of_witness(tmp_path, identifier, capacity, met):
    attempt, folder = fixture(tmp_path, identifier=identifier, capacity=capacity)
    expected = case(identifier=identifier) | dict(witness=dict(result=dict(dc_kw=100)))
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    summary = scorer.score(output, root=tmp_path, cases=[expected])
    result = summary["attempts"][0]
    assert result["hard_pass"] and result["requirements_met"] is met and result["success"] is met
    assert summary["methods"]["C"]["unsatisfied_solutions"] == int(not met)
    assert not result["environment_failure"] and not result["tool_errors"]


@pytest.mark.parametrize("identifier", ["t12-real-09", "t12-boundary-04", "t12-boundary-06", "unnamed"])
def test_cases_outside_fixed_maximize_list_keep_existing_scoring(tmp_path, identifier):
    attempt, folder = fixture(tmp_path, identifier=identifier, capacity=10)
    expected = case(identifier=identifier) | dict(text="尽量多装", witness=dict(result=dict(dc_kw=100)))
    result = scorer.attempt_score(attempt, expected, tmp_path)
    assert result["requirements_met"] and result["success"]


@pytest.mark.parametrize("summary_capacity,u01,met", [(100, 80, False), (80, 100, True)])
def test_maximize_reads_final_analysis_u01_instead_of_summary_capacity(tmp_path, summary_capacity, u01, met):
    identifier = "t12-real-01"
    attempt, folder = fixture(tmp_path, identifier=identifier, capacity=summary_capacity)
    rules = scorer.load(folder / "rules.json")
    rules["items"][0]["value"] = u01
    dump(folder / "final/rules.json", rules)
    run = scorer.load(folder / "run.json")
    run["final_analysis"]["rules"] = "final/rules.json"
    dump(folder / "run.json", run)
    expected = case(identifier=identifier) | dict(witness=dict(result=dict(dc_kw=100)))
    result = scorer.attempt_score(attempt, expected, tmp_path)
    assert result["hard_pass"] and result["requirements_met"] is met and result["success"] is met


def test_maximize_uses_frozen_witness_without_rewriting_case_or_answer(tmp_path):
    identifier = "t12-real-01"
    attempt, folder = fixture(tmp_path, identifier=identifier, capacity=80)
    expected = case(identifier=identifier) | dict(witness=dict(result=dict(dc_kw=100)))
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    dump(output / "cases.json", [expected])
    dump(tmp_path / "eval/cases.json", [case(identifier=identifier) | dict(witness=dict(result=dict(dc_kw=50)))])
    original = (output / "cases.json").read_bytes()
    summary = scorer.score(output, root=tmp_path)
    assert summary["methods"]["C"]["unsatisfied_solutions"] == 1
    assert (output / "cases.json").read_bytes() == original


def test_scorecard_explains_models_maximize_rule_and_chinese_token_names(tmp_path):
    attempt, folder = fixture(tmp_path)
    output = tmp_path / "results"
    jsonl(output / "attempts.jsonl", [attempt])
    summary = scorer.score(output, root=tmp_path, cases=[case()])
    text = (output / "scorecard.md").read_text(encoding="utf-8")
    assert "评测设计模型为 `deepseek-flash`" in text and "产品默认仍为 V4 Pro" in text
    assert "real-01–08、real-10–12、boundary-05" in text and "最终分析 U01" in text and "90%" in text
    for key, label in dict(input="输入", output="输出", cacheRead="缓存读取", cacheWrite="缓存写入", reasoning="推理").items():
        assert label + ":" in text and key + ":" not in text
    assert summary["total_tokens"] == dict(input=10, output=20, cacheRead=30, cacheWrite=40, reasoning=50)


def test_final_review_all_33_ids_preserve_automatic_summary_and_reproduce_scorecard(tmp_path):
    import shutil
    source = SCRIPTS.parent / 'eval/results/2026-10-03'
    for name in ('attempts.jsonl', 'statistics.md', 'human-review.json', 'cases.json'):  # the definitions scored that day
        shutil.copyfile(source / name, tmp_path / name)
    original = (source / 'summary.json').read_bytes()
    reviewed = scorer.load(tmp_path / 'human-review.json')['runs']
    assert len(reviewed) == 33 and len({r['id'] for r in reviewed}) == 33
    summary = scorer.score(tmp_path)
    assert (tmp_path / 'summary.json').read_bytes() == original
    for method, automatic, manual, useful, false_claims in [('C',8,18,15,1),('D',6,9,8,0),('E',1,5,4,1)]:
        group=[r for r in reviewed if r['method']==method]
        assert sum(r['automatic']['recognized'] for r in group) == automatic
        assert sum(r['manual']['recognized'] for r in group) == manual
        assert sum(r['useful_suggestion'] for r in group) == useful
        assert sum(r['automatic']['false_claim'] for r in group) == false_claims
        assert sum(r['manual']['false_claim'] for r in group) == 0
    card=(tmp_path/'scorecard.md').read_text(encoding='utf-8')
    for method in 'AE':
        row=next(line for line in card.splitlines() if line.startswith('| '+method+' |'))
        assert row.split('|')[8].strip() == '—'
    assert 'A、E只跑1次，三次全成功不适用（—）' in card
    assert card.index('人工复核（') < card.index('附录：')
    assert 'statistics.md' in card
    headline=(tmp_path/'headline.md').read_text(encoding='utf-8')
    assert '人工复核认出18次' in headline and '虚报0次' in headline and '15次建议照做能排出方案' in headline
    assert '待Claude复核' not in headline
    before={name:(tmp_path/name).read_bytes() for name in ('summary.json','scorecard.md','headline.md')}
    scorer.score(tmp_path)
    assert before == {name:(tmp_path/name).read_bytes() for name in before}
    assert (source/'summary.json').read_bytes() == original


@pytest.mark.parametrize('damage', ['missing','duplicate','automatic'])
def test_manual_review_rejects_incomplete_or_changed_automatic_results(tmp_path, damage):
    attempt,_=fixture(tmp_path, text='无满足全部要求的版本，U01装机下限超出屋顶能力，建议降低装机下限。')
    impossible=case(feasible=False)
    jsonl(tmp_path/'results/attempts.jsonl',[attempt])
    output=tmp_path/'results'
    summary=scorer.score(output,root=tmp_path,cases=[impossible])
    row=summary['attempts'][0]
    review=dict(id=row['id'],method='C',automatic=dict(recognized=row['impossible_recognized'],false_claim=row['false_claim']),
        manual=dict(recognized=True,false_claim=False),useful_suggestion=True,reason='人工按意思识别。')
    records=[review]
    if damage=='missing': records=[dict(review,id='wrong-id')]
    if damage=='duplicate': records*=2
    if damage=='automatic': review['automatic']['recognized']=not review['automatic']['recognized']
    dump(output/'human-review.json',dict(runs=records))
    with pytest.raises(ValueError,match='人工复核'):
        scorer.score(output,root=tmp_path,cases=[impossible])
