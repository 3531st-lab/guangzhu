"""Recompute T13 scores from archived native ledgers and explicit backend host records."""
import argparse
from collections import defaultdict
import hashlib
import html
import json
import math
from pathlib import Path
import re
import statistics

from agh_export_run import contained, own_events, read_events, resolve_results, result_value, tool_name
from eval_run import DESIGN_MODEL, costs as archive_costs

ROOT = Path(__file__).resolve().parents[1]
METHODS = tuple("ABCDE")
TOKENS = ("input", "output", "cacheRead", "cacheWrite", "reasoning")
TOKEN_NAMES = dict(input="输入", output="输出", cacheRead="缓存读取", cacheWrite="缓存写入", reasoning="推理")
MAXIMIZE_CASES = ("t12-real-01", "t12-real-02", "t12-real-03", "t12-real-04",
                  "t12-real-05", "t12-real-06", "t12-real-07", "t12-real-08",
                  "t12-real-10", "t12-real-11", "t12-real-12", "t12-boundary-05")
REQUIREMENTS = dict(capacity_kw_min="U01", capacity_kw_max="U02", budget_cny_max="U03", payback_years_max="U04",
                    walkway_m_min="G03", keep_clear_ids="G04", tilt_deg_range="G05",
                    edge_setback_m_min="G06", obstacle_clearance_m_min="G06")


def load(path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else default


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()] if path.is_file() else []


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def amount(item):
    billing = item.get("billing") if isinstance(item.get("billing"), dict) else {}
    value = billing.get("usdMicros")
    return value / 1e6 if billing.get("source") == "estimated" and type(value) is int and value >= 0 else 0


def language(text, pattern, *, advice=False):
    negative = r"不|未|没有|并非|无需|如果|假如|若|才能|之后"
    negative += "" if advice else r"|建议|放宽|取消|调整|降低|提高"
    for sentence in re.split(r"[。！？；，,\n]", text):
        match = re.search(pattern, sentence)
        if match and not re.search(negative, sentence[:match.start()][-12:]):
            return True
    return False


def satisfies(case, rules):
    items = {item["id"]: item for item in rules.get("items", [])}
    for field, expected in case["structured"].items():
        item = items.get(REQUIREMENTS.get(field), {})
        value = item.get("value")
        if item.get("status") != "pass":
            return False
        if field == "keep_clear_ids":
            valid = value == []
        elif field == "tilt_deg_range":
            valid = type(value) in (int, float) and expected[0] <= value <= expected[1]
        else:
            value = value.get(field.removesuffix("_min")) if field in ("edge_setback_m_min", "obstacle_clearance_m_min") else value
            valid = type(value) in (int, float) and math.isfinite(value)
            valid &= value >= expected if valid and field.endswith("_min") else value <= expected if valid else False
        if not valid:
            return False
    if case["id"] in MAXIMIZE_CASES:
        value = items.get("U01", {}).get("value")
        return type(value) in (int, float) and math.isfinite(value) and value >= case["witness"]["result"]["dc_kw"] * 0.9
    return True


def attempt_score(attempt, case, root=ROOT):
    directory = contained(root, attempt["archive"]) if attempt.get("archive") else None
    run = load(directory / "run.json", {}) if directory else {}
    native = read_events(directory / "ledger.agnes.jsonl") if directory and (directory / "ledger.agnes.jsonl").is_file() else []
    ledgers = [directory / "ledger.agnes.jsonl"] if native else []
    children = sorted(set(directory.glob("children/**/*.ledger.agnes.jsonl"))) if directory else []
    children += [contained(directory, item["ledger"]) for item in run.get("children", []) if item.get("ledger")]
    child_events = [event for path in sorted(set(children)) if path.is_file() for event in own_events(read_events(path, inherited=True))]
    ledgers.extend(path for path in set(children) if path.is_file())
    host = lines(directory / "execution.jsonl") if directory else []
    violations, environment, tool_errors = [], [], []
    if attempt.get("environment_failure"):
        environment.append(attempt.get("environment_reason") or attempt.get("error") or "驱动或环境失败")
    anomalies = {key: run[key] for key in ("children", "children_errors", "anomalies") if run.get(key)}
    if children:
        anomalies["child_ledgers"] = [path.relative_to(directory).as_posix() for path in sorted(set(children))]
    if anomalies or run.get("children_complete") is False or any(event["type"].startswith("subagent/") for event in native):
        environment.append("归档异常或出现子会话")
    if any(event.get("origin") != "external:eval-driver" or "seq" in event or "trust" in event for event in host):
        environment.append("后端host记录来源或格式错误")
    elapsed = attempt.get("elapsed_seconds")
    elapsed_valid = type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0
    if not elapsed_valid:
        environment.append("耗时缺失或不是有效非负秒数")
    method = attempt["method"]
    if method not in METHODS or not case and not (method == "D" and attempt.get("case") is None):
        environment.append("做法或案例编号不符")
    if case and (method in "AE" and attempt.get("repeat") != 1 or method == "D" and case.get("half", 2) != 2):
        environment.append("单次基线重复或D使用前半案例")
    requests = [event for event in native if event["type"] == "request/sent"]
    if method == "B" and len(requests) > 1 or method == "A" and requests:
        environment.append("A使用模型或B发出多次请求")
    expected_model = "agnes-3.0-flash" if method == "E" else DESIGN_MODEL
    preflight = attempt.get("pre_request_failure") and attempt["status"] == "failed" and not requests
    if method != "A" and not preflight and (
            not requests or any(event["data"].get("model", {}).get("id") != expected_model for event in requests)):
        environment.append("实际请求模型不符或缺少请求证据")
    if native and (native[0]["data"].get("key") != attempt.get("session") or any(event.get("origin") != "system"
                    or event.get("trust") != "trusted" for event in requests)):
        environment.append("原生会话或请求来源不符")
    tools = [event for event in native if event["type"] == "tool/call"]
    for event in tools:
        name = tool_name(event) or event["data"].get("name", "")
        if event.get("origin") != "model" or event.get("trust") != "trusted":
            environment.append("模型工具调用来源不符")
            continue
        if method == "B" or not (name.startswith("gz_") or name == "skill_read") or name == "gz_export":
            violations.append("模型工具越界：" + name)
    asks = {event["data"]["requestId"]: event for event in native if event["type"] == "approval/asked"}
    for event in native:
        if event["type"] != "approval/decided":
            continue
        ask = asks.get(event["data"].get("requestId"), {})
        call = next((tool for tool in tools if tool["data"].get("toolUseId") == ask.get("data", {}).get("toolUseId")), {})
        name, verdict = tool_name(call) or call.get("data", {}).get("name", ""), event["data"].get("verdict", "")
        terminal = ask.get("data", {}).get("kind") == "unknown-outcome"
        terminal &= not any(item.get("data", {}).get("toolUseId") for item in (ask, event))
        terminal &= ask.get("data", {}).get("summary", "").startswith("verifier failed: ")
        terminal &= all(item.get("origin") == "system" and item.get("trust") == "trusted" for item in (ask, event))
        if terminal and verdict == "allowed-once" and event["data"].get("via") == "sync":
            continue
        allowed = name == "skill_read" or name.startswith("gz_") and name != "gz_export"
        if verdict.startswith("allowed") and (verdict != "allowed-session" or not allowed):
            environment.append("驱动审批范围错误")
        if verdict == "rejected" and method in "CDE" and allowed:
            environment.append("驱动拒绝了允许的设计审批")
    execution = host if method in ("A", "B") else native
    call_kind, result_kind, key = ("backend/call", "backend/result", "callId") if method in ("A", "B") else (
        "tool/call", "tool/result", "toolUseId")
    calls = [event for event in execution if event["type"] == call_kind]
    if len({call["data"].get(key) for call in calls}) != len(calls) or any(not call["data"].get(key) for call in calls):
        environment.append("工具调用关联编号缺失或重复")
    paired, rows = [], []
    for call in calls if method in ("A", "B") else [c for c in calls if not tool_name(c)]:
        results = [e for e in execution if e["type"] == result_kind and e["data"].get(key) == call["data"].get(key)]
        result = results[0] if len(results) == 1 else {}
        value = result.get("data", {}).get("value", {}) if method in ("A", "B") else result_value(result)
        rows.append(dict(call=call, result=result, value=value))
    if method not in ("A", "B"):
        resolved, unlinked = resolve_results(execution)
        rows.extend(resolved)
        if unlinked:
            environment.append("等待结果无法关联原调用")
    for row in rows:
        call, result, value = row["call"], row["result"], row["value"]
        if result and (result["data"].get("isError") or value.get("ok") is False):
            tool_errors.append(value.get("error_code") or value.get("error") or result["data"].get("code") or "TOOL_ERROR")
            if value.get("error_code") == "TEMPLATE_NOT_FOUND" and call["data"].get("args", {}).get("template") == (case or {}).get("template"):
                environment.append("旧MCP进程未加载案例模板")
        if result and execution.index(result) > execution.index(call) and result["data"].get("isError") is False and value.get("ok") is True:
            paired.append((tool_name(call) or call["data"].get("name", ""), call, value, execution.index(result)))
    if any(name == "gz_new_project" and any((value.get("code_identity") or {}).get(field) !=
            (attempt.get("code_identity") or {}).get(field) for field in ("commit", "source_sha256", "skill_rules_sha256"))
           for name, call, value, position in paired):
        environment.append("实际MCP工具代码版本不符")
    analyses = [row for row in paired if row[0] == "gz_analyze" and "what_if" not in row[1]["data"].get("args", {})]
    final = max(analyses, key=lambda row: row[3], default=None)
    model_error = any(e["type"] == "turn/end" and e["data"].get("reason") == "error" for e in native)
    if model_error or tool_errors or not final and "archive" in environment:
        environment = [reason for reason in environment if reason not in ("archive", "ui-run", "restore-model")]
    final_analysis = run.get("final_analysis", {})
    rules = load(contained(directory, final_analysis.get("rules", "rules.json")), {}) if directory and final else {}
    version = final[2].get("version") if final else None
    matched = bool(final and final[1]["data"].get("args", {}).get("version") == version == final_analysis.get("version"))
    if matched:
        summary = load(contained(directory, final_analysis.get("summary", "summary.json")), {})
        matched &= summary == final[2] and final[1]["data"].get("args", {}).get("project_id") == run.get("project_id")
        matched &= rules.get("version", version) == version and rules.get("project_id", run.get("project_id")) == run.get("project_id")
    if any(hashlib.sha256(contained(directory, path).read_bytes()).hexdigest() != digest for path, digest in run.get("artifacts", {}).items()):
        environment.append("归档文件哈希不符")
    failed = sum(item["level"] == "hard" and item["status"] == "fail" for item in rules.get("items", []))
    hard_pass = bool(matched and rules.get("items") and failed == 0 == final[2].get("rules", {}).get("hard_failed"))
    met = bool(matched and case and satisfies(case, rules))
    messages = [event for event in (host if method == "A" else native) if event["type"] == ("driver/final" if method == "A" else "assistant/message")]
    if method != "A":
        messages = [event for event in messages if event.get("origin") == "model" and event.get("trust") == "trusted"]
    final_text = messages[-1]["data"].get("text", "") if messages and method == "A" else "".join(
        block.get("text", "") for block in messages[-1]["data"].get("content", []) if block.get("type") == "text") if messages else ""
    claimed = language(final_text, r"(?:满足|达成)(?:了)?(?:全部|所有)(?:用户)?(?:要求|需求)|(?:全部|所有)(?:要求|需求)(?:均|都|已)?(?:满足|达标|通过)")
    denied = language(final_text, r"无法满足|不能满足|做不到|不可行|无法实现|达不到要求")
    relaxed = language(final_text, r"放宽|降低.{0,20}(?:下限|要求)|提高.{0,20}(?:上限|预算)|取消.{0,20}(?:要求|下限|上限)", advice=True)
    binding = bool(case and any(re.search(r"(?<![A-Z0-9])" + re.escape(item["id"]) + r"(?![A-Z0-9])", final_text)
                               or item["name_zh"] in final_text for item in case.get("binding", [])))
    costs = {event["data"]["effectId"]: event["data"] for event in native + child_events
             if event["type"] == "cost/ledger" and not event["data"].get("adjustment")}
    micros, incomplete = archive_costs(ledgers)
    incomplete |= method != "A" and not native and (bool(attempt.get("session")) or attempt.get("evidence_error") or not preflight)
    incomplete |= any(not path.is_file() for path in children)
    tokens = {field: sum(item.get("tokens", {}).get(field, 0) for item in costs.values()) for field in TOKENS}
    verification = load(directory / "verification.json", {}) if directory else {}
    closed = bool(matched and verification.get("passed") and len(verification.get("checks", [])) == 4
                  and all(item["passed"] for item in verification["checks"])
                  and (verification.get("final_analysis") or {}).get("version", version) == version)
    completed = attempt["status"] in ("completed", "finished", "success") and not violations and not environment
    success = bool(completed and case and (hard_pass and met and not denied if case["feasible"] else method in "CDE" and not claimed and binding and relaxed))
    return dict(id=attempt["id"], case=attempt.get("case"), method=method, repeat=attempt.get("repeat"), attempt=attempt.get("attempt", 1),
                status=attempt["status"], eligible=not violations and not environment, violations=sorted(set(violations)), success=success,
                environment_failure=bool(environment and not violations), environment_reasons=sorted(set(environment)), tool_errors=sorted(set(tool_errors)),
                model_error=model_error or method == "B" and bool(requests) and not final and not tool_errors and attempt["status"] == "failed",
                code_identity=attempt.get("code_identity"), archive_anomalies=anomalies,
                hard_pass=hard_pass, requirements_met=met, false_impossible=bool(case and case["feasible"] and denied),
                false_claim=bool(claimed and not (hard_pass and met)), impossible_recognized=bool(not claimed and binding and relaxed),
                four_step=closed, version=version, versions=len({value["version"] for name, call, value, position in paired
                    if name in ("gz_generate_layout", "gz_edit_design") and type(value.get("version")) is int}),
                edits=sum(name == "gz_edit_design" for name, call, value, position in paired), elapsed_seconds=elapsed if elapsed_valid else None,
                pre_request_failure=attempt.get("pre_request_failure", False),
                usd=micros / 1e6, tokens=tokens, model_requests=len(requests), final_text=final_text, billing_complete=not incomplete,
                billing_ledgers=[path.relative_to(root).as_posix() for path in sorted(set(ledgers))],
                billing={effect: dict(usd=amount(item), tokens=item.get("tokens", {}))
                         for effect, item in costs.items()},
                energy_kwh=final[2].get("yield_kwh", {}).get("p50") if final else None,
                payback_years=final[2].get("economics", {}).get("payback_years") if final else None)


def stats(values):
    values = [value for value in values if type(value) in (int, float) and math.isfinite(value)]
    return dict(mean=statistics.mean(values), minimum=min(values), maximum=max(values)) if values else None


def aggregate(rows, cases, cost_rows=None):
    cost_rows = rows if cost_rows is None else cost_rows
    environment_count = sum(row["environment_failure"] for row in cost_rows)
    rows = [row for row in rows if not row["environment_failure"]]
    feasible = [row for row in rows if cases[row["case"]]["feasible"]]
    impossible = [row for row in rows if not cases[row["case"]]["feasible"]]
    groups = defaultdict(list)
    for row in rows:
        groups[row["case"]].append(row)
    result = dict(runs=len(rows), successes=sum(row["success"] for row in rows), feasible_runs=len(feasible), impossible_runs=len(impossible),
                  hard_pass_rate=sum(row["eligible"] and row["hard_pass"] for row in feasible) / len(feasible) if feasible else None,
                  requirement_rate=sum(row["success"] for row in feasible) / len(feasible) if feasible else None,
                  recognition_rate=sum(row["success"] for row in impossible) / len(impossible) if impossible and impossible[0]["method"] in "CDE" else None,
                  false_impossible=sum(row["false_impossible"] for row in feasible), false_claims=sum(row["false_claim"] for row in rows),
                  violations=sum(bool(row["violations"]) for row in rows), environment_failures=environment_count,
                  tool_errors=sum(bool(row["tool_errors"]) for row in rows), timeouts=sum(row["status"] in ("timeout", "timed_out") for row in rows),
                  unsatisfied_solutions=sum(row["eligible"] and row["version"] is not None and not row["tool_errors"]
                                            and not (row["hard_pass"] and row["requirements_met"]) for row in feasible),
                  model_errors=sum(row["model_error"] for row in rows),
                  three_success_cases=sum({row["repeat"] for row in group} == {1, 2, 3} and all(row["success"] for row in group)
                                          for group in groups.values()), usd=sum(row["usd"] for row in cost_rows),
                  attempts=len(cost_rows), elapsed_total=sum(row["elapsed_seconds"] or 0 for row in cost_rows),
                  elapsed_incomplete=sum(row["elapsed_seconds"] is None for row in cost_rows),
                  billing_incomplete=sum(not row["billing_complete"] for row in cost_rows))
    result["four_step_rate"] = sum(row["eligible"] and row["four_step"] for row in feasible) / len(feasible) if (
        feasible and feasible[0]["method"] in "CDE") else None
    result["usd_per_run"] = result["usd"] / len(rows) if rows and not result["billing_incomplete"] else None
    result["elapsed_per_run"] = result["elapsed_total"] / len(rows) if rows and not result["elapsed_incomplete"] else None
    for field in ("elapsed_seconds", "usd", "edits", "versions"):
        result[field + "_stats"] = stats([row[field] for row in rows if field != "usd" or row["billing_complete"]])
    result["tokens"] = {field: sum(row["tokens"][field] for row in cost_rows) for field in TOKENS}
    result["tokens_stats"] = {field: stats([row["tokens"][field] for row in rows]) for field in TOKENS}
    result["repeats"] = {case: dict(successes=sum(row["success"] for row in group), runs=len(group),
        success_stats=stats([int(row["success"]) for row in group]),
        tokens={field: stats([row["tokens"][field] for row in group]) for field in TOKENS},
        **{field: stats([row[field] for row in group]) for field in ("elapsed_seconds", "usd", "edits", "versions")}) for case, group in groups.items()}
    return result


def score(directory, *, root=ROOT, cases=None, cost_only=None):
    cases = {case["id"]: case for case in (cases or load(directory / "cases.json") or load(root / "eval/cases.json"))}
    attempts = lines(directory / "attempts.jsonl")
    if any(not (r.get("code_identity") or {}).get("commit") for r in attempts):
        raise ValueError("Missing code identity; preliminary attempts must be included as cost-only input")
    identities = {(r.get("code_identity") or {}).get("commit") for r in attempts}
    hashes = {tuple((r.get("code_identity") or {}).get(key) for key in ("source_sha256", "skill_rules_sha256")) for r in attempts}
    if len(identities) > 1 or len(hashes) > 1:
        raise ValueError("Mixed code versions cannot share a scorecard")
    rows = [attempt_score(attempt, cases.get(attempt.get("case")), root) for attempt in attempts]
    prior = cost_only if cost_only is not None else sorted((root / "eval/results").glob("*-预跑"))
    prior_ledgers = [path for folder in prior if folder.resolve() != directory.resolve()
                     for attempt in lines(folder / "attempts.jsonl") if attempt.get("archive")
                     for path in [contained(root, attempt["archive"]) / "ledger.agnes.jsonl",
                                  *contained(root, attempt["archive"]).glob("children/**/*.agnes.jsonl")]
                     if path.is_file() or attempt.get("method") != "A" and (attempt.get("session") or attempt.get("evidence_error"))]
    prior_micros, prior_incomplete = archive_costs(prior_ledgers)
    micros, incomplete = archive_costs(prior_ledgers + [contained(root, path) for row in rows for path in row["billing_ledgers"]])
    charged = set()
    for row in rows:
        unique = [item for effect, item in row["billing"].items() if effect not in charged]
        charged.update(row["billing"])
        row.update(usd=sum(item["usd"] for item in unique), tokens={key: sum(item["tokens"].get(key, 0) for item in unique) for key in TOKENS})
    groups = defaultdict(list)
    for row in rows:
        if row["case"] in cases:
            groups[(row["case"], row["method"], row["repeat"])].append(row)
    runs = []
    for key, group in sorted(groups.items()):
        for index, row in enumerate(group):
            previous = group[index - 1] if index else None
            retry_ok = not previous or previous["environment_failure"] or (
                previous["pre_request_failure"] and previous["model_requests"] == 0 and previous["status"] == "failed")
            if row["attempt"] != index + 1 or index > 1 or not retry_ok or row["repeat"] not in (1, 2, 3):
                row.update(eligible=False, success=False, invalid_retry=True, environment_failure=not row["violations"],
                           environment_reasons=row["environment_reasons"] + ["重试条件不符"])
        selected = dict(next((row for row in reversed(group) if not row.get("invalid_retry")), group[0]))
        selected.update(usd=sum(row["usd"] for row in group), elapsed_seconds=sum(row["elapsed_seconds"] for row in group)
                        if all(row["elapsed_seconds"] is not None for row in group) else None,
                        tokens={field: sum(row["tokens"][field] for row in group) for field in TOKENS},
                        billing_complete=all(row["billing_complete"] for row in group))
        runs.append(selected)
    auxiliary = [row for row in rows if row["case"] is None]
    summary = dict(schema="guangzhu.eval/1", attempts=rows, total_usd=micros / 1e6,
                   preliminary=dict(usd=prior_micros / 1e6, billing_incomplete=prior_incomplete,
                                    ledgers=[path.relative_to(root).as_posix() for path in sorted(set(prior_ledgers))]),
                   billing_incomplete=incomplete or any(not row["billing_complete"] for row in rows),
                   total_tokens={field: sum(row["tokens"][field] for row in rows) for field in TOKENS}, auxiliary=auxiliary,
                   methods={method: aggregate([row for row in runs if row["method"] == method], cases,
                       [row for row in rows if row["method"] == method]) for method in METHODS},
                   classifications={group: {method: aggregate([row for row in runs if row["method"] == method
                       and cases[row["case"]]["collection"] == group], cases) for method in METHODS}
                       for group in ("real", "boundary", "impossible")},
                   code_commit=next(iter(identities), None), code_hashes=next(iter(hashes), None),
                   matrix={case: {method: {row["repeat"]: "环境失败" if row["environment_failure"] else
                       row["success"] if row["eligible"] else "越界" for row in runs
                       if row["case"] == case and row["method"] == method} for method in METHODS} for case in cases})
    active = {row["method"] for row in runs}
    common = [case for case in cases if cases[case]["feasible"] and all(any(row["case"] == case and row["method"] == method for row in runs)
                  and all(row["success"] for row in runs if row["case"] == case and row["method"] == method) for method in active)]
    summary["effects"] = dict(common_cases=common, methods={method: {field: stats([row[field] for row in runs
        if row["case"] in common and row["method"] == method]) for field in ("energy_kwh", "payback_years")} for method in METHODS})
    write(directory / "summary.json", summary)
    render(directory, summary, cases)
    return summary


def table(rows, header, records):
    rows.extend(["", header, "| " + " | ".join(["---"] * (header.count("|") - 1)) + " |"])
    rows.extend("| " + " | ".join(human(value) for value in values) + " |" for values in records)


def human(value):
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "成功" if value else "失败"
    if isinstance(value, (list, tuple)):
        return "; ".join(human(item) for item in value) or "—"
    if isinstance(value, dict):
        return "/".join(human(value[key]) for key in ("mean", "minimum", "maximum")) if "mean" in value else "; ".join(
            f"{TOKEN_NAMES.get(key, key)}: {human(item)}" for key, item in value.items()) or "—"
    return f"{value:.4g}" if isinstance(value, float) else str(value)


def rate(data, field):
    denominator = data["impossible_runs" if field == "recognition_rate" else "feasible_runs"]
    value = data[field]
    return fraction(round(value * denominator), denominator) if value is not None else "—"


def fraction(numerator, denominator):
    return f"{numerator}/{denominator}（{numerator / denominator:.0%}）" if denominator else "—"


def render(directory, summary, cases):
    human_review = load(directory / "human-review.json")
    reviewed = (human_review or {}).get("runs", [])
    if human_review is not None:
        expected = {r['id']: r for r in summary['attempts'] if r['method'] in 'CDE' and r['eligible']
                    and r['case'] in cases and not cases[r['case']]['feasible']}
        if len(reviewed) != len(expected) or {r['id'] for r in reviewed} != set(expected):
            raise ValueError('人工复核运行编号不完整或重复')
        for row in reviewed:
            original = expected[row['id']]
            if row['automatic'] != dict(recognized=original['impossible_recognized'], false_claim=original['false_claim']):
                raise ValueError('人工复核中的自动结果与归档打分不一致')
            if (row['method'] != original['method'] or set(row['manual']) != {'recognized', 'false_claim'}
                    or any(type(v) is not bool for v in [*row['manual'].values(), row['useful_suggestion']]) or not row['reason']):
                raise ValueError('人工复核缺少判断或原因')
    rows = [f"评测设计模型为 `{DESIGN_MODEL}`（B/C/D及D写经验）；E为 `agnes-3.0-flash`。产品默认仍为 V4 Pro。",
            "尽量多装12例（real-01–08、real-10–12、boundary-05）：最终分析 U01 装机须≥冻结案例 witness 装机的90%，不足记方案不满足。",
            "成绩只从归档执行记录复算；评测审批由脚本选本会话允许。越界不给成功分；全部尝试费用仍计入总额。",
            f"费用记录：{'有缺失' if summary['billing_incomplete'] else '完整'}；已记录费用不代表免费。",
            f"修复前预跑不计成绩：已记录估算费用 {summary['preliminary']['usd']:.6f} 美元，计入累计总费。",
            "模型回答识别使用保守文本规则，所有不可行原文必须由Claude复核。"]
    table(rows, "| 做法 | 运行 | 硬规则通过率 | 需求成功率 | 不可行识别率 | 误判不可行 | 虚报 | 三次全成功 | 四步闭环率 |",
          ([method, data["runs"], *(rate(data, key) for key in ("hard_pass_rate", "requirement_rate", "recognition_rate")),
            data["false_impossible"], data["false_claims"], None if method in "AE" else data["three_success_cases"], rate(data, "four_step_rate")]
           for method, data in summary["methods"].items()))
    rows.extend(["", "A、E只跑1次，三次全成功不适用（—）。"])
    table(rows, "| 做法 | 全部尝试/总费美元 | 每例费用（均值/最小/最大） | 耗时秒（均值/最小/最大） | 修改数 | 版本数 | 五类token总计 |",
          ([method, f"{data['attempts']}/{data['usd']:.6f}", *(data[key] for key in
            ("usd_stats", "elapsed_seconds_stats", "edits_stats", "versions_stats", "tokens"))] for method, data in summary["methods"].items()))
    rows.extend(["", "按类别"])
    table(rows, "| 类别 | 做法 | 成功/运行 | 需求率 | 不可行识别率 |",
          ([group, method, "—" if group == "impossible" and method in "AB" else fraction(data['successes'], data['runs']),
            rate(data, "requirement_rate"), rate(data, "recognition_rate")]
           for group, methods in summary["classifications"].items() for method, data in methods.items()))
    rows.extend(["", "案例矩阵（重复编号:结果；—表示未做，环境失败排除成绩）"])
    table(rows, "| 案例 | A | B | C | D | E |", ([case, *(methods[method] for method in METHODS)] for case, methods in summary["matrix"].items()))
    table(rows, "| 做法/案例 | 成功 | 耗时均/最小/最大 | 费用均/最小/最大 | 五类token均/最小/最大 |",
          ([method + "/" + case, fraction(data["successes"], data["runs"]), data["elapsed_seconds"], data["usd"], data["tokens"]]
           for method, aggregate in summary["methods"].items() for case, data in aggregate["repeats"].items()))
    table(rows, "| 共同满足案例 | 做法 | 年发电量均/最小/最大 | 回本年限均/最小/最大 |",
          ([", ".join(summary["effects"]["common_cases"]) or "—", method, data["energy_kwh"], data["payback_years"]]
           for method, data in summary["effects"]["methods"].items()))
    table(rows, "| 做法 | 环境失败（不计成绩） | 模型越界 | 模型错误 | 工具错误 | 方案不满足 | 超时 |",
          ([method, *(data[key] for key in ("environment_failures", "violations", "model_errors", "tool_errors", "unsatisfied_solutions", "timeouts"))]
           for method, data in summary["methods"].items()))
    if reviewed:
        rows.extend(["", "人工复核（按原话意思判断；自动成绩保持原样，建议有用不计成绩）"])
        table(rows, "| 做法 | 自动（字面） | 人工复核 | 建议有用 | 自动记的虚报 | 人工复核虚报 |",
              ([method, *(fraction(sum(r[key]['recognized'] for r in reviewed if r['method'] == method),
                  sum(r['method'] == method for r in reviewed)) for key in ('automatic', 'manual')),
                fraction(sum(r['useful_suggestion'] for r in reviewed if r['method'] == method), sum(r['method'] == method for r in reviewed)),
                *(sum(r[key]['false_claim'] for r in reviewed if r['method'] == method) for key in ('automatic', 'manual'))] for method in 'CDE'))
        table(rows, "| 运行 | 自动识别/虚报 | 人工识别/虚报 | 建议有用 | 原因 |",
              ([r['id'], *([('识别' if r[key]['recognized'] else '未识别'), ('虚报' if r[key]['false_claim'] else '无虚报')]
                  for key in ('automatic', 'manual')), '有用' if r['useful_suggestion'] else '无用', r['reason']] for r in reviewed))
    rows.extend(["", "附录：不可行最终原文（Claude已人工复核）" if reviewed else "附录：不可行最终原文（Claude待人工复核）"])
    for attempt in summary["attempts"]:
        if attempt["case"] in cases and not cases[attempt["case"]]["feasible"]:
            rows.extend(["", attempt["id"], "", "```text", attempt["final_text"], "```"])
        if attempt["violations"] or attempt["environment_failure"] or attempt["tool_errors"] or attempt["status"] in ("timeout", "timed_out"):
            reasons = attempt["violations"] + attempt["environment_reasons"] + attempt["tool_errors"]
            rows.extend(["", f"运行说明：{attempt['id']} · {attempt['status']} · {'; '.join(reasons)}"])
        if attempt["archive_anomalies"]:
            rows.extend(["", "归档异常：" + human(attempt["archive_anomalies"])])
    table(rows, "| 经验会话（不进入案例成绩） | 已记录费用美元 | 耗时秒 |",
          ([row["id"], row["usd"], row["elapsed_seconds"]] for row in summary["auxiliary"]))
    if (directory / 'statistics.md').is_file():
        rows.append("\n补充统计见[各轮均值、范围与经验对照](statistics.md)。D表内费用含有效经验；费用拆分见reports/T13.md。")
    (directory / "scorecard.md").write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    headline = [f"已保留{len(summary['attempts'])}次尝试，累计已记录估算费用{summary['total_usd']:.6f}美元。"
                + ("费用有缺失，仍待核实。" if summary["billing_incomplete"] else "")]
    for method, data in summary["methods"].items():
        headline.append(f"{method}正式运行{data['runs']}次，可行屋顶需求满足 {rate(data, 'requirement_rate')}，不可行识别 {rate(data, 'recognition_rate')}。")
    if reviewed:
        full = [r for r in reviewed if r['method'] == 'C']
        headline.append(f"做不到的6个屋顶，完整Agent跑{len(full)}次，人工复核认出{sum(r['manual']['recognized'] for r in full)}次，"
                        f"说清卡住的要求并给出放宽建议，虚报{sum(r['manual']['false_claim'] for r in full)}次；"
                        f"自动按字面认出{sum(r['automatic']['recognized'] for r in full)}次。其中{sum(r['useful_suggestion'] for r in full)}次建议照做能排出方案。")
    else:
        headline.append("不可行回答原文待Claude复核；没有共同满足的案例时不比较发电量和回本。")
    (directory / "headline.md").write_text("\n".join(headline) + "\n", encoding="utf-8", newline="\n")
    plots = (("requirement_rate", (("requirement_rate", "需求成功率"),)), ("recognition_rate", (("recognition_rate", "不可行识别率"),)),
             ("cost_time", (("usd_per_run", "平均费用（美元/例，含重试及经验）"), ("elapsed_per_run", "平均耗时（秒/例，含重试及经验）"))))
    for filename, panels in plots:
        bars = []
        for panel, (field, title) in enumerate(panels):
            values = [summary["methods"][method][field] for method in METHODS]
            scale = max((value or 0 for value in values), default=1) or 1
            bars.append(f'<text x="10" y="{25 + panel * 250}">{html.escape(title)}</text>')
            for index, (method, value) in enumerate(zip(METHODS, values)):
                y = panel * 250 + index * 35
                label = rate(summary["methods"][method], field) if field.endswith("rate") else human(value)
                bars.append(f'<text x="10" y="{60 + y}">{method}: {label}</text>')
                bars.append(f'<rect x="230" y="{43 + y}" width="{max(0, (value or 0) / scale * 350)}" height="22" fill="#307f76"/>')
        (directory / (filename + ".svg")).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="650" height="{250 * len(panels)}">'
            + "".join(bars) + '</svg>\n', encoding="utf-8", newline="\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--cost-only", type=Path, action="append")
    options = parser.parse_args(argv)
    score(options.directory.resolve(), cost_only=options.cost_only)


if __name__ == "__main__":
    main()
