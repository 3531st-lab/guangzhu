"""Read a single completed run; keep business values and evidence unchanged."""
import hashlib
import json
from pathlib import Path
import sys

from ..config import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import agh_export_run as evidence
from agh_verify_run import export_approvals


def load_archive(run_dir):
    from ..api import run_usage, run_options
    folder = Path(run_dir).resolve()
    if folder.parent.name == "reviews" or "review" in folder.name and not folder.name.startswith("gz-"):
        raise ValueError("方案书需要设计运行归档")
    def read(base, name):
        return json.loads(evidence.contained(base, name).read_text(encoding="utf-8-sig"))
    meta = read(folder, "run.json")
    verification = read(folder, "verification.json")
    capture = evidence.contained(folder, meta.get("capture", "."))
    captures = [capture]
    if meta.get("review_capture"):
        captures.append(evidence.contained(folder, meta["review_capture"]))
    sources, missing, sessions, records = {}, [], [], []
    manifests = {path: read(path, "run.json") for path in captures}
    def artifact(base, name):
        path = evidence.contained(base, name)
        if not path.is_file():
            missing.append(path.relative_to(folder).as_posix())
            return None
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if manifests[base].get("artifacts", {}).get(name) != digest:
            raise ValueError("归档文件SHA不一致：" + name)
        sources[path.relative_to(folder).as_posix()] = digest
        return read(base, name)
    exports = verification.get("verified_exports", [])
    version = exports[-1]["version"] if exports else meta.get("export_version")
    if type(version) is not int or version < 1:
        raise ValueError("归档没有明确的导出版本")
    data = {"run_id": folder.name, "project_id": meta["project_id"], "version": version,
            "ledger_path": (capture.relative_to(folder) / "ledger.agnes.jsonl").as_posix(),
            "verification": verification, "sources": sources, "missing": missing, "facts": meta.get("facts")}
    for name in ("project", "design", "summary", "rules", "shading", "electrical", "structure", "catalog", "economics"):
        relative = f"analysis/v{version}/{name}.json"
        if name in ("project", "catalog"):
            relative = name + ".json"
        elif name == "design":
            relative = f"designs/v{version}.json"
        elif name == "economics":
            relative = f"exports/v{version}/economics.json"
        data[name] = artifact(capture, "project/" + relative)
    if not data["project"] or not data["design"] or data["design"].get("version") != version:
        raise ValueError("项目或选定设计缺失或不匹配")
    if data["project"].get("id") != meta["project_id"]:
        raise ValueError("归档项目编号不一致")
    for base in captures:
        ledger = evidence.contained(base, "ledger.agnes.jsonl")
        events = evidence.read_events(ledger)
        info = manifests[base]
        if events[0]["data"].get("key") != info.get("session"):
            raise ValueError("原账本会话不一致")
        digest = hashlib.sha256(ledger.read_bytes()).hexdigest()
        if base != capture:
            associations = verification.get("review", {}).get("associations", [])
            if not any(row.get("session") == info["session"] and row.get("ledger_sha256") == digest for row in associations):
                raise ValueError("独立审核关联SHA不一致")
        sources[ledger.relative_to(folder).as_posix()] = digest
        sessions.append(dict(id=info["session"], model_ids=[m["id"].rsplit("/", 1)[-1] for m in info.get("models", []) if isinstance(m, dict)]))
        records.append((base, events))
    data.update(compare=None, crosscheck=None, review=None, approval=None, requirements=[], history=[], versions=[], run=run_options(folder))
    for base, events in records:
        for row in evidence.resolve_results(events)[0]:
            call, result, name = row["call"], row["value"], row["name"]
            args = call["data"].get("args", {})
            if (args.get("project_id") == meta["project_id"] and result.get("ok") is True
                    and row["result"] and row["result"]["data"].get("isError") is False):
                if base == capture and name == "gz_set_requirements":
                    data["requirements"].append(dict(seq=call["seq"], ts=call["ts"], **args))
                if base == capture and name == "gz_compare_options":
                    if result.get("base_version") == version or any(row.get("version") == version for row in result.get("options", [])):
                        data["compare"] = result
                if base == capture and name == "gz_crosscheck_yield" and result.get("version") == version:
                    data["crosscheck"] = (artifact(base, f"project/analysis/v{version}/crosscheck.json") or result
                                          if result.get('groups') else result)
                if name == "gz_record_review" and result.get("version") == version:
                    review = artifact(base, "project/reviews/" + Path(result["file"]).name)
                    if review and review.get("version") == version:
                        data["review"] = dict(review, reviewer_model=review.get("reviewer_model", "").rsplit("/", 1)[-1])
            if (base == capture and name == "gz_export" and args.get("project_id") == meta["project_id"]
                    and args.get("version") == version and result.get("version") == version
                    and row["result"] and row["result"]["data"].get("isError") is False and result.get("ok") is True):
                decisions = export_approvals(events, row)
                if decisions:
                    last = decisions[-1]
                    data["approval"] = dict(verdict=last["data"]["verdict"], ts=last["ts"], seq=last["seq"], tool_call_seq=call["seq"])
        if base != capture:
            continue
        for event in events:
            value = event["data"]
            if event["type"] in ("user/message", "inbox") and event.get("trust") == "trusted":
                items = value.get("items", []) if event["type"] == "inbox" else [value]
                text = "\n".join(b.get("text", "") for item in items for b in item.get("content", []) if b.get("type") == "text")
                data["history"].append(dict(seq=event["seq"], ts=event["ts"], text=text))
    compare = data["compare"] or {}
    if compare.get("current"):
        designs = {}
        for candidate in [compare["current"], *compare.get("options", [])]:
            identifier = candidate["version"]
            while identifier is not None and identifier not in designs:
                design = artifact(capture, f"project/designs/v{identifier}.json")
                if not design or design.get("version") != identifier:
                    raise ValueError("候选或父版本归档缺失或不匹配")
                designs[identifier] = design
                identifier = design.get("parent_version")
        data["versions"] = list(designs.values())
    data["usage"] = run_usage(folder)
    data["sessions"] = [dict(row, **{k: v for k, v in data["usage"].get(row["id"], {}).items() if k != "session_id"}) for row in sessions]
    data["relaxations"] = [dict(before=before, after=after,
        consent=[row for row in data["history"] if before["seq"] < row["seq"] < after["seq"]])
        for before, after in zip(data["requirements"], data["requirements"][1:])]
    return data
