"""Local desktop API: read original artifacts; export and verify native AGH evidence."""
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from urllib.parse import quote
from urllib.request import urlopen
import webbrowser

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from shapely.geometry import Polygon
from starlette.concurrency import run_in_threadpool
from . import myroofs, park, park_store, park_queue, sitecheck
from .brief import BriefSpec, render_brief
from .config import AGH_ORIGIN, API_ORIGIN, API_PORT, ROOT
from .economics import resolve_parameters
from .models import GzError, SiteFacts
from .templates import catalog_data, read_template
from .setup import Coordinator, installation

sys.path.insert(0, str(ROOT / "scripts"))
import agh_export_run as evidence
import agh_verify_run as verifier

AGH_URL = AGH_ORIGIN
LOCK = threading.Lock()
SETUP_LOCK = threading.Lock()
app = FastAPI(title="光筑", docs_url=None, redoc_url=None)


@app.middleware("http")
async def revalidate_pages(request, call_next):
    # An upgraded install must never show the previous version's cached page scripts.
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


def settings():
    if installation(ROOT)['installed']:
        coordinator = setup_coordinator()
        if not coordinator.data['ready'] or not coordinator.data['target']:
            raise ValueError('光筑还在准备设计工具，请稍候')
        coordinator.client.identity()
        return dict(agh_runtime=str(ROOT / 'runtime/agh/agnes-win32-x64.exe'),
                    agh_home=coordinator.data['target']['home'], agh_profile='local-dev')
    path = ROOT / "desktop/settings.json"
    values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {"agh_runtime": str(evidence.OFFICIAL), "agh_home": str(Path.home() / ".guangzhu-agh"), **values}


def setup_coordinator():
    with SETUP_LOCK:
        current = getattr(app.state, 'setup', None)
        if current is None or current.root != ROOT.resolve():
            current = Coordinator(ROOT, start=getattr(app.state, 'start_agh', None))
            app.state.setup = current
        return current


def local_only(request):
    if request.headers.get('host') != f'127.0.0.1:{API_PORT}' or request.headers.get('origin') != API_ORIGIN:
        raise HTTPException(403, '仅允许本地桌面同源配置')


def setup_input(request, payload, fields):
    local_only(request)
    if set(payload) != set(fields) or any(not isinstance(payload[key], kind) for key, kind in fields.items()):
        raise ValueError('配置参数不符合固定接口')
    if len(json.dumps(payload)) > 8192:
        raise ValueError('配置参数过长')


@app.get('/api/setup/status')
def setup_status():
    return setup_coordinator().status()


@app.post('/api/setup/{action}')
def setup_action(action: str, request: Request, payload: dict = Body(...)):
    coordinator = setup_coordinator()
    if action == 'configure':
        setup_input(request, payload, {})
        return coordinator.begin()
    if action in {'complete', 'models'}:
        field = 'workspace' if action == 'complete' else 'metadata'
        setup_input(request, payload, {'operation_id': str, field: dict})
        if not re.fullmatch('[a-f0-9]{32}', payload['operation_id']):
            raise ValueError('配置编号不合法')
        return getattr(coordinator, action)(**payload)
    raise HTTPException(404, '配置动作不存在')


def safe(base, relative):
    return evidence.contained(base, relative)


def read(path, default=None):
    path = safe(ROOT, path)
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else default


def identifier(value, limit=64):
    return evidence.identifier(value, limit=limit)


def session(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:_/-]{0,239}", value):
        raise ValueError("会话编号不合法")
    return value


def public(value):
    return JSONResponse(evidence.sanitize(value))


@app.exception_handler(ValueError)
@app.exception_handler(GzError)
@app.exception_handler(OSError)
@app.exception_handler(subprocess.SubprocessError)
@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    return JSONResponse({"errors": ["输入编号、文件或数据格式不正确"]}, status_code=400)


def reachable():
    try:
        with urlopen(AGH_URL, timeout=.25) as response:
            return response.status == 200
    except OSError:
        return False


def run_folder(run_id):
    direct = safe(ROOT / "runs", identifier(run_id, 95))
    return next((folder for alias, folder, _ in run_entries() if alias == run_id), direct)


def run_entries():
    for folder in sorted((ROOT / "runs").glob("*")):
        if folder.is_dir():
            if re.fullmatch(r"eval-[0-9]{4}", folder.name):
                for run in sorted(folder.glob("*/run.json")):
                    yield run.parent.name, safe(folder, run.parent), "design"
                continue
            yield folder.name, safe(ROOT / "runs", folder), "review" if "review" in folder.name and not folder.name.startswith("gz-") else "design"
            for review in sorted((folder / "reviews").glob("*")):
                if review.is_dir():
                    alias = "review-" + hashlib.sha256(review.relative_to(ROOT / "runs").as_posix().encode()).hexdigest()
                    yield alias, safe(folder, review), "review"
    for folder in sorted((ROOT / "data/showcase").glob("*")):  # Codex review E1: a real archived run shipped with the app, open without a key
        if folder.is_dir() and not (ROOT / "runs" / folder.name).is_dir():  # on the computer that made it, list the run once
            yield folder.name, safe(ROOT / "data/showcase", folder), "design"


def record(folder):
    meta = read(folder / "run.json", {})
    capture = safe(folder, meta["capture"]) if meta.get("capture") else folder
    verification = read(folder / "verification.json", read(capture / "verification.json", {}))
    if verification.get("scope") != "independent-review" and (folder.parent.name == "reviews" or "review" in folder.name and not folder.name.startswith("gz-")):
        verification = legacy_review_verification(capture, meta)
    return capture, meta, verification


def run_usage(folder):
    capture, meta, _ = record(folder)
    captures = [capture] + ([safe(folder, meta["review_capture"])] if meta.get("review_capture") else [])
    usages = {}
    number = lambda value: value if type(value) is int and value >= 0 else None
    for capture in captures:
        info = read(capture / "run.json", {})
        if not info.get("session"):
            continue
        sid, ledger = session(info["session"]), safe(capture, "ledger.agnes.jsonl")
        events = evidence.read_events(ledger) if ledger.is_file() else []
        if events and events[0]["data"].get("key") != sid:
            continue
        seen, amounts, missing = {}, {}, 0
        for event in events:
            if event["type"] != "cost/ledger" or event.get("data", {}).get("adjustment"):
                continue
            data = event["data"]
            if event.get("origin") != "system" or event.get("trust") != "trusted" or not isinstance(data.get("effectId"), str) or not data["effectId"]:
                raise ValueError("用量记录缺少原生来源或费用编号")
            key = data["effectId"]
            if key in seen:
                if seen[key] != data:
                    raise ValueError("同一费用编号内容冲突")
                continue
            seen[key] = data
            billing = data.get("billing") if isinstance(data.get("billing"), dict) else {}
            amount = number(billing.get("usdMicros")) if billing.get("source") == "estimated" else None
            if amount is None:
                missing += 1
            else:
                amounts["USD"] = amounts.get("USD", 0) + amount
        usages[sid] = dict(session_id=sid, started_at=info.get("started_at"), ended_at=info.get("ended_at"),
            model_requests=number(info.get("model_requests")), tokens={k: number(info.get("tokens", {}).get(k))
                for k in ("input", "output", "cacheRead", "cacheWrite", "reasoning")},
            costs=[dict(currency=k, micros=v) for k, v in amounts.items()],
            billing_complete=bool(seen) and missing == 0, missing_costs=missing if ledger.is_file() else None)
    return usages


def legacy_review_verification(capture, meta):
    unknown = dict(passed=None, scope="independent-review", checks=[], review=dict(passed=None, state="unverified"))
    ledger = safe(capture, "ledger.agnes.jsonl")
    if not ledger.is_file() or not meta.get("session"):
        return unknown
    digest = hashlib.sha256(ledger.read_bytes()).hexdigest()
    for parent in project_runs(meta.get("project_id")):
        proof = read(parent / "verification.json", {}).get("review", {})
        linked = any(row.get("session") == meta["session"] and row.get("ledger_sha256") == digest for row in proof.get("associations", []))
        row = next((row for row in proof.get("independent", []) if row.get("session") == meta["session"]), None)
        if (proof.get("mode") == "independent" and proof.get("passed") is True and linked and row
                and all(row.get(key) is True for key in ("passed", "valid", "actual_model_verified"))):
            if evidence.read_events(ledger)[0]["data"].get("key") == meta["session"]:
                return dict(passed=True, scope="independent-review", checks=[], review=dict(row, state="verified"),
                            certificate=dict(parent_run_id=parent.name, session=meta["session"], ledger_sha256=digest))
    return unknown


def nodes_for(folder):
    return read(folder / "timeline.json", {}).get("nodes", []) if folder else []


def tool_result(nodes, name, version=None):
    for node in reversed(nodes):
        if node.get("kind") != "tool" or not node.get("name", "").endswith(name):
            continue
        try:
            value = node.get("result_json") if "result_json" in node else json.loads(node.get("result", ""))
            matched = version is None or matching_result(value, version, "base_version" if name == "gz_compare_options" else "version")
            if value.get("ok") is True and value.get("pending") is not True and node.get("isError") is not True and matched:
                if name == 'gz_crosscheck_yield' and value.get('total_groups', 0) > len(value.get('groups', [])):
                    continue  # The persisted crosscheck holds every group across pages.
                return value
        except (ValueError, AttributeError, TypeError):
            continue
    return None


def matching_result(value, version, field="version"):
    matched = value and (value.get(field) == version or field == "base_version"
                        and any(isinstance(row, dict) and row.get("version") == version for row in value.get("options", [])))
    return value if value and value.get("ok") and matched else None


def cached_compare(base, version):
    paths = sorted((base / "analysis").glob("v*/compare.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return next((value for path in paths if (value := matching_result(read(safe(base, path)), version, "base_version"))), None)


def project_runs(project_id):
    return sorted((p for p in (ROOT / "runs").glob("*") if p.is_dir()
                   and read(p / "run.json", {}).get("project_id") == project_id),
                  key=lambda p: read(p / "run.json", {}).get("ended_at", ""), reverse=True)


def full_results(folder):
    if not folder:
        return []
    capture, meta, _ = record(folder)
    if not (capture / "ledger.agnes.jsonl").is_file():
        return nodes_for(folder)
    events = evidence.read_events(safe(capture, "ledger.agnes.jsonl"))
    rows = [r for r in evidence.resolve_results(events)[0] if r["result"]
            and r["call"]["data"].get("args", {}).get("project_id") == meta.get("project_id")]
    return [dict(kind="tool", name=r["name"], result=json.dumps(r["value"]), result_json=r["value"],
                 result_seq=r["result"]["seq"], isError=r["result"]["data"].get("isError"))
            for r in sorted(rows, key=lambda r: r["result"]["seq"])]


def result_data(project_id, version=None, folder=None):
    identifier(project_id)
    archived = folder is not None
    meta, verification = {}, {}
    if folder:
        capture, meta, verification = record(folder)
        base = safe(capture, "project")
    else:
        base = safe(ROOT / "projects", project_id)
        if not base.is_dir():
            raise HTTPException(404, "项目不存在")
        folder = next((p for p in project_runs(project_id) if record(p)[2].get("verified_exports")), None)
        if folder:
            _, meta, verification = record(folder)
    def original(path):
        path = safe(base, path)
        if archived and path.is_file():
            key = path.relative_to(base.parent).as_posix()
            if hashlib.sha256(path.read_bytes()).hexdigest() != meta.get("artifacts", {}).get(key):
                return None
        return read(path)
    designs = {int(p.stem[1:]): original(p) for p in sorted((base / "designs").glob("v*.json")) if re.fullmatch(r"v[1-9][0-9]*", p.stem)}
    designs = {v: d if isinstance(d, dict) and d.get("version") == v else None for v, d in designs.items()}
    exported = [read(safe(base, p), {}).get("version") for p in (base / "exports").glob("v*/manifest.json")]
    verified = [row["version"] for row in verification.get("verified_exports", []) if row.get("version") in designs]
    selected = verified[-1] if verified else max((v for v in exported if type(v) is int and v in designs), default=None)
    if meta.get("lean"):
        selected = meta.get("final_version")
    valid = [v for v, d in designs.items() if d]
    passed = [v for v in valid if original(base / f"analysis/v{v}/rules.json") and
              original(base / f"analysis/v{v}/rules.json").get("hard_failed") == 0]
    version = version if version is not None else selected if selected is not None else max(passed or valid, default=None)
    if version is not None and version not in designs and not (meta.get("lean") and version == selected):
        raise HTTPException(404, "没有该方案版本")
    design = designs.get(version)
    parent = designs.get(design.get("parent_version")) if design else None
    project = original(base / "project.json")
    analysis = safe(base, f"analysis/v{version}")
    summary = read(analysis / "summary.json", {})
    shading, electrical = original(analysis / "shading.json"), original(analysis / "electrical.json")
    nodes = full_results(folder)
    review_files = [safe(base, p) for p in (base / "reviews").glob(f"v{version}-*.json")]
    if meta.get("review_capture"):
        review_files += [safe(folder, p) for p in safe(folder, meta["review_capture"] + "/project/reviews").glob(f"v{version}-*.json")]
    structure = original(analysis / 'structure.json')
    scene = dict(project=project, design=design, parent_design=parent, shading=shading, electrical=electrical)
    if project and design and project['roof']['type'] in ('ground', 'carport'):
        from .models import Project, Design
        from .installation import effective, facilities
        model, version_model = Project.model_validate(project), Design.model_validate(design)
        scene['project'] = effective(model, version_model).model_dump(mode='json')
        scene['facilities'] = facilities(model, version_model)
    if project and project['roof']['type'] == 'pitched':
        from .models import Roof
        from .roofplane import scene_geometry
        scene['roof_geometry'] = scene_geometry(Roof.model_validate(project['roof']), (design or {}).get('added_keepouts', []))
    if structure and structure.get('wind', {}).get('version') == version:
        scene['wind'] = structure['wind']
    if structure and structure.get('livestock', {}).get('version') == version:
        scene['livestock'] = structure['livestock']
    sources = {key: str(path.relative_to(ROOT)).replace("\\", "/") for key, path in
               (("project", base / "project.json"), ("shading", analysis / "shading.json"),
                ("electrical", analysis / "electrical.json"), ("structure", analysis / "structure.json")) if path.is_file()}
    return dict(project_id=project_id, run_id=folder.name if folder else None, selected_version=selected, version=version,
        display_passed=version in passed, project=project, run=run_options(folder) if folder else {},
        design=design, parent_design=parent, scene=scene, sources=sources, economics=original(analysis / "economics.json"),
        missing=[key for key, value in scene.items() if value is None and (key != "parent_design" or design and design.get("parent_version") is not None)],
        metrics=summary, summary=summary, versions=[{k: d.get(k) for k in ("version", "parent_version", "reason", "statistics", "created_at")} |
        dict(metrics=version_metrics(read(analysis.parent / f"v{key}/summary.json", {}))) for key, d in sorted(designs.items()) if d],
        compare=tool_result(nodes, "gz_compare_options", version) or cached_compare(base, version), rules=read(analysis / "rules.json", {}),
        crosscheck=tool_result(nodes, "gz_crosscheck_yield", version) or matching_result(read(analysis / "crosscheck.json"), version),
        reviews=list({json.dumps(read(p), sort_keys=True): read(p) for p in sorted(review_files)}.values()),
        review_files={p.name: read(p) for p in sorted(review_files)},
        files=read(safe(base, f"exports/v{version}/manifest.json"), {}), verification=verification,
        facts=meta.get("facts"),  # T22: the owner's answers before construction, checked against this version
        site_checks=sitecheck.rows(meta.get("facts"), summary,
            (original(analysis / "economics.json") or {}).get('params') or resolve_parameters(project)[0], project['roof']['type'],
            project.get('requirements', {}).get('structured'), project['roof']) if project else [],
        report=meta.get("report") if meta.get("report", {}).get("version") == version else None)


def version_metrics(summary):  # Codex review E2: what each saved change did to yield and payback, shown next to the change
    return dict(annual_kwh=(summary.get("yield_kwh") or {}).get("p50"), payback_years=(summary.get("economics") or {}).get("payback_years")) if summary else None


def report_ready(result):
    checks = result["verification"].get("checks", [])
    return bool(result["selected_version"] and not result["missing"] and len(checks) == 4 and all(c.get("passed") is True for c in checks))


def make_report(folder, regenerated=False):
    metadata = read(folder / "run.json", {})
    if not metadata.get("project_id"):
        raise HTTPException(404, "运行不存在")
    result = result_data(metadata["project_id"], folder=folder)
    if not report_ready(result):
        raise HTTPException(409, "四步核对和场景快照齐全后才能生成方案书")
    try:
        from .report import generate
        report = generate(folder, regenerated=regenerated)
    except Exception:
        report = dict(status="error", version=result["selected_version"], files=[], error="方案书生成失败，请稍后重试",
                      generated_at=datetime.now(timezone.utc).isoformat(), regenerated=regenerated)
        evidence.write_json(folder / "run.json", read(folder / "run.json") | dict(report=report))
    return report


def scene_is_public(value):
    if isinstance(value, dict):
        return all((key == "nasa_header" or not evidence.PRIVATE_FIELD.fullmatch(key)) and scene_is_public(item) for key, item in value.items())
    if isinstance(value, list):
        return all(scene_is_public(item) for item in value)
    return evidence.sanitize(value) == value


def snapshot_scene(capture, project_id):
    source = safe(ROOT / "projects", project_id)
    files = [source / "project.json"]
    for design in (capture / "project/designs").glob("v*.json"):
        version = read(design)["version"]
        files += [source / f"analysis/v{version}/{name}.json" for name in ("shading", "electrical", "structure")]
    metadata = read(capture / "run.json")
    for path in files:
        path = safe(source, path)
        if path.is_file():
            target = safe(capture / "project", path.relative_to(source))
            target.parent.mkdir(parents=True, exist_ok=True)
            content = path.read_bytes()
            if not scene_is_public(json.loads(content)):
                raise ValueError("场景原文件含私密信息，不能作为原字节快照")
            if target.exists() and target.read_bytes() != content:
                raise ValueError("原场景快照与当前项目不同，保留旧证据")
            target.write_bytes(content)
            metadata["artifacts"][target.relative_to(capture).as_posix()] = hashlib.sha256(content).hexdigest()
            if path.name == 'project.json':
                metadata['module_id'] = json.loads(content).get('equipment', {}).get('module_id')
    metadata["scene_snapshot_complete"] = True
    evidence.write_json(capture / "run.json", metadata)


def review_prompt(project_id, version, model):
    return (f"全程使用中文。独立审核项目 {project_id} 的已导出版本{version}。只用mcp_guangzhu_df14eb73_gz_project_summary、"
        "mcp_guangzhu_df14eb73_gz_analyze、mcp_guangzhu_df14eb73_gz_crosscheck_yield、"
        "mcp_guangzhu_df14eb73_gz_record_review四个业务工具，逐个调用并等待正式返回，各一次。"
        "允许mcp_guangzhu_df14eb73_gz_wait；收到pending就用同一job_id持续等待，不重调业务工具。禁止skill_read、"
        "skill_list、其他Skill工具、shell、文件、网页，不修改方案、不导出。只审核指定版本，不能改审最新候选。"
        "核对保存需求、硬性规则、发电复核和经济假设；数字只照抄工具结果，不计算、不编造。"
        "summary的latest_version可能是三方案候选，不能代替指定已导出版本。"
        "复核a/b/c使用同一NASA天气；b_tmy/d使用不同天气，不能混作同天气误差。数字不另算、不舍入。"
        "严重程度必须与证据一致；hard_failed=0不能写成硬性规则失败，低于预算上限不能写成超预算。"
        f"最后调用gz_record_review，project_id={project_id}，version={version}，reviewer_model={model}，"
        "verdict为approve或revise；findings含severity/item/evidence/suggestion，severity只用high/medium/low；"
        "item、evidence、suggestion写给业主看，用中文名称（如检修通道、回本），不写英文字段名和工具名；核对后没有问题、无需调整的项写low。"
        "按证据独立判断，不强迫同意；记录后说明结论和依据。")


def brief_packet(ledger):
    """The one-click brief's JSON exactly as the user sent it (T22 reads its facts from here)."""
    if ledger.is_file():
        for event in evidence.read_events(ledger):
            if event["type"] != "user/message":
                continue
            text = "".join(b.get("text", "") for b in event["data"].get("content", []))
            for match in re.finditer(r"```json\s*(\{.*?\})\s*```", text, re.S):
                try:
                    packet = json.loads(match[1])
                    if isinstance(packet.get("run"), dict) and "project" in packet:
                        return packet
                except ValueError:
                    continue
    return {}


def brief_facts(ledger):
    try:
        return SiteFacts.model_validate(brief_packet(ledger)["facts"]).model_dump() or None
    except (KeyError, ValidationError):
        return None


def run_options(folder):
    return brief_packet(record(folder)[0] / "ledger.agnes.jsonl").get("run", {})


def capture_path(folder, kind, key, *, fresh=False):
    base = safe(folder, kind + "/" + hashlib.sha256(key.encode()).hexdigest()[:20])
    candidates = sorted(base.parent.glob(base.name + "*"))
    complete = next((p for p in candidates if (p / "run.json").exists()), None)
    return (complete if not fresh else None) or (base.with_name(base.name + f"-{len(candidates)}") if base.exists() else base)


def finish(payload):
    project_id, sid = identifier(payload.get("project_id")), session(payload.get("session_id"))
    evaluation = payload.get("evaluation") is True
    if evaluation and not re.fullmatch(r"eval-[0-9]{4}-[A-Za-z0-9_-]+", project_id):
        raise ValueError("评测项目编号须为 eval-MMDD-案例-做法-次数")
    version = payload.get("export_version")
    if version is not None and (type(version) is not int or version < 1):
        raise ValueError("版本须为正整数")
    review_sid = session(payload["review_session_id"]) if payload.get("review_session_id") else None
    if evaluation and review_sid:
        raise ValueError("评测不接入独立审核会话")
    model = payload.get("reviewer_model", "agnes-3.0-flash")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("填写审核模型")
    run_id, config = project_id if evaluation else "gz-" + project_id, settings()
    folder = safe(ROOT / "runs", f"eval-{project_id.split('-')[1]}/{run_id}") if evaluation else run_folder(run_id)
    with LOCK:
        existing = read(folder / "run.json", {})
        if existing and existing.get("session") != sid:
            raise HTTPException(409, "项目记录已属于另一个设计会话")
        if version is None:
            version = existing.get("export_version")
        export_binding = dict(env={**os.environ, 'AGH_HOME': config['agh_home']}, profile=config.get('agh_profile', 'local-dev'))
        capture = folder if evaluation else capture_path(folder, "captures", f"{sid}:{version}")
        if not (capture / "run.json").exists():
            evidence.export_run(sid, project_id, run_id, root=ROOT, executable=config["agh_runtime"],
                                with_children=True, destination=capture, **export_binding, **({"lean": True} if evaluation else {}))
        if not evaluation and not read(capture / "run.json").get("scene_snapshot_complete"):
            snapshot_scene(capture, project_id)
        events = evidence.read_events(capture / "ledger.agnes.jsonl")
        resolved, unlinked = evidence.resolve_results(events)
        projects = {r["call"]["data"].get("args", {}).get("project_id") for r in resolved}
        if events[0]["data"].get("key") != sid or projects != {project_id} or unlinked:
            raise ValueError("原生记录的项目或会话不匹配")
        command = [str(capture), "--reviewer-model", model]
        if evaluation:
            command.append("--no-export")
        review = capture_path(folder, "reviews", review_sid, fresh=True) if review_sid else None
        if not review and existing.get("capture") == capture.relative_to(folder).as_posix() and existing.get("review_capture"):
            review = safe(folder, existing["review_capture"])
        if review:
            if not (review / "run.json").exists():
                evidence.export_run(review_sid, project_id, run_id, root=ROOT, executable=config["agh_runtime"],
                                    with_children=True, destination=review, **export_binding)
            if not read(review / "run.json").get("scene_snapshot_complete"):
                snapshot_scene(review, project_id)
            command += ["--review-run", str(review)]
        verifier.main(command)
        metadata = read(capture / "run.json") | dict(capture=capture.relative_to(folder).as_posix(), export_version=version)
        if facts := brief_facts(capture / "ledger.agnes.jsonl"):  # T22: the owner's answers before construction travel with the record
            metadata["facts"] = facts
        if review:
            metadata["review_capture"] = review.relative_to(folder).as_posix()
            metadata["review_session_id"] = read(review / "run.json")["session"]
        verification = read(capture / "verification.json")
        if review:
            assessment = next((row for row in verification.get("review", {}).get("independent", [])
                               if row["session"] == metadata["review_session_id"]), {})
            evidence.write_json(review / "verification.json", dict(passed=assessment.get("passed", False),
                                scope="independent-review", checks=[], review=assessment))
        actual = [r["value"].get("version") for r in sorted(resolved, key=lambda r: (r["result"] or {}).get("seq", -1))
                  if r["name"] == "gz_export" and r["result"] and r["result"]["data"].get("isError") is False
                  and r["value"].get("ok") is True and r["value"].get("version") == r["call"]["data"].get("args", {}).get("version")]
        if version is not None and (not actual or actual[-1] != version):
            raise ValueError("指定版本不是该原生会话最后成功导出的版本")
        timeline = read(capture / "timeline.json")
        if review:
            timeline["nodes"] = sorted(timeline["nodes"] + nodes_for(review), key=lambda row: row.get("ts", ""))
        for name, value in (("run", metadata), ("verification", verification), ("timeline", timeline)):
            evidence.write_json(folder / f"{name}.json", value)
        if (not evaluation and (review or verification.get("review", {}).get("requested") is False)
                and report_ready(result_data(project_id, folder=folder))):
            make_report(folder)
    result = result_data(project_id, folder=folder)
    usages = run_usage(folder)
    return dict(run_id=run_id, session_id=sid, archive_path=folder.relative_to(ROOT).as_posix(), verification=verification,
        selected_version=result["selected_version"], usage=usages.get(sid), usage_by_session=usages,
        result=result, review_prompt=review_prompt(project_id, result["selected_version"], model)
        if not evaluation and result["selected_version"] and len(verification.get("checks", [])) == 4
        and all(c["passed"] for c in verification["checks"]) else None)


@app.get("/api/status")
def status():
    return {"app": "guangzhu", "version": "0.1.0", "agh": {"connected": reachable(), "url": AGH_URL}, 'installation': installation(ROOT)}


TILT_HINTS = {}


@app.get("/api/roofs/{roof_id}/tilt")
def roof_tilt(roof_id: str):
    return tilt_hint(read_template(identifier(roof_id), root=ROOT))


@app.get("/api/tilt")
def site_tilt(lat: float = Query(ge=0, le=55), lon: float = Query(ge=-180, le=180)):
    # T18: the roof editor shows the local best tilt as soon as a city or coordinates are chosen.
    base = read_template(myroofs.BASE, root=ROOT)
    return tilt_hint(dict(base, site=dict(base["site"], lat=lat, lon=lon)))


def tilt_hint(payload):
    """T19：按屋顶所在地的全年天气给倾角提示；有缓存就离线算，没有就取 NASA POWER 公开数据，取不到就说明。"""
    from . import layout, weather
    from .tilt import choose, irradiation_by_tilt
    project = layout.validate_project(payload)
    key = (round(project.site.lat, 3), round(project.site.lon, 3))
    if key not in TILT_HINTS:
        nasa = None
        for offline in (True, False):
            try:
                nasa, _ = weather.load_nasa_hourly(project.site.lat, project.site.lon, 2023, offline=offline)
                break
            except Exception:
                continue
        if nasa is None:
            return {"available": False, "hint": "开始设计后按当地天气计算"}
        plan = choose(irradiation_by_tilt(nasa, project.site.lat, project.site.lon, albedo=project.site.albedo))
        slope = float(layout._catalog(project)[0]["length_m"])
        pitch = lambda tilt: layout.row_spacing(project.site.lat, project.site.lon, tilt, slope)["row_spacing_m"]
        TILT_HINTS[key] = {"available": True, "lat": project.site.lat, "best": plan["best"], "balanced": plan["balanced"],
                           "capacity": plan["capacity"], "loss_pct": plan["loss_pct"],
                           "more_rows_pct": round(100 * (pitch(plan["best"]) / pitch(plan["balanced"]) - 1))}
    return TILT_HINTS[key]


@app.get("/api/roofs")
def roofs(all: bool = False):
    rows = []
    for path, project in catalog_data(all=all, root=ROOT).values():
        roof = project["roof"]
        geometry = Polygon(roof["outline"])
        x0, y0, x1, y1 = geometry.bounds
        mine = path.parent.parent.name == "my-roofs"
        rows.append(dict(id=path.parent.name, collection="mine" if mine else project.get("collection") or "demo", name=project["name"],
            area_m2=geometry.area, dimensions_m=[x1-x0, y1-y0], project=project, geometry=roof, obstacles=roof["obstacles"],
            keepouts=roof["keepouts"], defaults=resolve_parameters(project)[0]))
    # Factory roofs lead the demo list and the default pick; new surface kinds follow (folder names alone put the carport first).
    kinds = {"flat": 0, "metal": 1, "pitched": 2, "ground": 3, "carport": 4}
    rows.sort(key=lambda r: (r["id"] != "changzhou-demo", kinds.get(r["geometry"].get("type", "flat"), 5))
              if r["collection"] == "demo" else (2, 0))
    from .electrical import load_catalog
    return public({"roofs": rows, 'inverters': [dict(id=k, model=v['model'], brand=v['manufacturer']) for k, v in load_catalog('inverters.csv').items()],
                   'modules': [dict(id=key, model=value['model'])
                                             for key, value in load_catalog('modules.csv').items()]})


def roof_reply(action):
    try:
        return public(action())
    except GzError as error:
        return JSONResponse({"errors": [f"{error.message_zh}。{error.fix_hint}"]}, status_code=422)


@app.post("/api/drawings")
async def import_drawing(request: Request, name: str = Query(max_length=200), page: int = Query(1, ge=1)):
    local_only(request)
    data = await request.body()
    if len(data) > 60 * 2**20:
        return JSONResponse({"errors": ["图纸超过 60 MB。只导出屋顶那一页再导入"]}, status_code=413)
    return await run_in_threadpool(roof_reply, lambda: myroofs.import_drawing(name, data, page, ROOT))


@app.get("/api/drawings/{token}")
def drawing_image(token: str):
    return FileResponse(myroofs.upload(token, ROOT), media_type="image/png")


@app.post("/api/my-roofs")
def save_roof(request: Request, payload: dict = Body(...)):
    local_only(request)
    return roof_reply(lambda: dict(id=myroofs.save(payload, ROOT)))


@app.post('/api/roof-planes')
def preview_roof_planes(request: Request, payload: dict = Body(...)):
    local_only(request)
    def preview():
        from .models import Roof, validated
        from .roofplane import generate, scene_geometry
        result = generate(payload.get('outline', []), payload.get('settings', {}))
        if payload.get('planes'):
            result['planes'] = payload['planes']
        roof = validated(Roof, dict(type='pitched', outline=payload['outline'], planes=result['planes'],
                         height_m=payload.get('height_m', 9), parapet_height_m=0, load_capacity_kn_m2=.5))
        return dict(result, geometry=scene_geometry(roof))
    return roof_reply(preview)


@app.post('/api/parking')
def preview_parking(request: Request, payload: dict = Body(...)):
    local_only(request)
    def preview():
        from .models import Roof, validated
        from .installation import parking
        settings = payload.get('settings', {})
        if isinstance(settings, dict):
            settings = {key: value for key, value in settings.items() if key not in ('bays', 'aisles', 'strips', 'columns')}
        roof = validated(Roof, dict(type='carport', outline=payload.get('outline', []), carport=settings,
                                    height_m=0, parapet_height_m=0, load_capacity_kn_m2=.5,
                                    obstacles=payload.get('obstacles', []), keepouts=payload.get('keepouts', [])))
        generated = validated(Roof, roof.model_dump() | parking(roof))
        return dict(planes=[p.model_dump() for p in generated.planes], carport=generated.carport.model_dump())
    return roof_reply(preview)


@app.post("/api/my-roofs/{roof_id}/delete")
def delete_roof(request: Request, roof_id: str):
    local_only(request)
    return roof_reply(lambda: myroofs.delete(roof_id, ROOT) or {})


@app.get("/api/my-roofs/{roof_id}/underlay")
def roof_underlay(roof_id: str):
    path = myroofs.folder(ROOT) / identifier(roof_id) / "underlay.png"
    if not path.is_file():
        raise HTTPException(404, "这个屋顶没有底图")
    return FileResponse(path, media_type="image/png")


@app.post("/api/brief")
def brief(payload: dict = Body(...)):
    try:
        spec = BriefSpec.model_validate(payload)
        if safe(ROOT / "projects", spec.id).exists():
            return JSONResponse({"errors": ["项目编号已存在"]}, status_code=409)
        return public(dict(brief=render_brief(spec), labels=[f"{k}: {v}" for k, v in
            spec.structured.model_dump(exclude_none=True).items() if v not in ([], "")], errors=[]))
    except ValidationError as error:
        return JSONResponse({"brief": None, "labels": [], "errors": [brief_error(e) for e in error.errors()]}, status_code=422)


def brief_error(error):
    if error["type"] == "value_error":
        message = str(error.get("ctx", {}).get("error", ""))
        if re.search(r"[\u4e00-\u9fff]", message):
            return message
    field = next(iter(error.get("loc", [])), "")
    hints = {"text": "请填写1至200字的需求", "max_rounds": "自改轮数须为1至6的整数",
        "id": "项目编号只允许字母、数字、下划线和短横线，最长64字符", "template": "请选择可用的屋顶模板",
        "reviewer_model": "请选择审核模型", "structured": "请检查硬性要求的格式和范围",
        "economics": "请检查经济参数的格式和范围", "compare": "请选择是否生成三方案",
        "facts": "请检查开工前问答的格式和范围", "review": "请选择是否独立审核", "export": "请选择是否导出",
        "review_mode": "请选择有效的审核模式", "prefer": "请选择有效的设计偏好"}
    return hints.get(field, "任务书包含不支持或缺失的字段")


@app.get("/api/projects/{project_id}/result")
def project_result(project_id: str, version: int | None = Query(None, ge=1)):
    return public(result_data(project_id, version))


def cached_weather(project):
    site = (project or {}).get("site", {})
    if "lat" not in site or "lon" not in site:
        return None
    key = f"nasa_{site['lat']:.4f}_{site['lon']:.4f}_2023"
    for relative in ("data/cache/weather", "data/demo/weather"):
        folder = safe(ROOT, relative)
        metadata, data = read(folder / (key + ".json"), {}), safe(folder, key + ".csv.gz")
        if (data.is_file() and metadata.get("latitude") == site["lat"] and metadata.get("longitude") == site["lon"]
                and hashlib.sha256(data.read_bytes()).hexdigest() == metadata.get("data_file_sha256")):
            return metadata
    return None


@app.get("/api/projects/{project_id}/exists")
def project_exists(project_id: str):
    return {"exists": safe(ROOT / "projects", identifier(project_id)).exists()}


@app.get("/api/projects/{project_id}/progress")
def progress(project_id: str):
    base = safe(ROOT / "projects", identifier(project_id))
    project = read(base / "project.json")
    designs = sorted((base / "designs").glob("v*.json"), key=lambda p: int(p.stem[1:]))
    latest = read(designs[-1], {}) if designs else {}
    summary = read(base / "analysis" / f"v{latest.get('version')}" / "summary.json", {})
    runs = project_runs(project_id)
    nodes = nodes_for(runs[0]) if runs else []
    facts = full_results(runs[0]) if runs else []
    caches = sorted([p for p in (base / "analysis").glob("v*/*.json") if p.name in ("compare.json", "crosscheck.json")], key=lambda p: p.stat().st_mtime)
    exported = sorted((base / "exports").glob("v*/manifest.json"), key=lambda p: p.stat().st_mtime)
    choice = read(safe(base, (exported or caches)[-1]), {}) if exported or caches else {}
    version = choice.get("version", choice.get("base_version", latest.get("version")))
    compare = tool_result(facts, "gz_compare_options", version) or cached_compare(base, version)
    crosscheck = tool_result(facts, "gz_crosscheck_yield", version) or matching_result(read(safe(base, f"analysis/v{version}/crosscheck.json")), version)
    required = bool(project and project.get("requirements", {}).get("text"))
    weather = tool_result(facts, "gz_fetch_weather") or cached_weather(project)
    checks = [bool(project), required, required, bool(weather), bool(designs), bool(summary),
              bool(compare), bool(crosscheck),
              bool(list((base / "reviews").glob("*.json"))), bool(list((base / "exports").glob("v*/manifest.json")))]
    return public(dict(project_id=project_id, source="project-files", steps=[dict(number=i+1,
        status="completed" if yes else "not_started") for i, yes in enumerate(checks)],
        project=project, design=latest, summary=summary, weather=weather, nodes=nodes, active_version=version, compare=compare, crosscheck=crosscheck,
        missing=[name for name, value in (("gz_compare_options", compare), ("gz_crosscheck_yield", crosscheck)) if not value]))


@app.post("/api/runs/finish")
def finish_run(payload: dict = Body(...)):
    return public(finish(payload))


@app.get("/api/runs")
def runs():
    rows = []
    for alias, folder, kind in run_entries():
        try:
            capture, meta, verification = record(folder)
            verification = verification or dict(passed=False, checks=[], errors=["尚无核对记录"])
            versions = [v["version"] for v in verification.get("verified_exports", [])] or verification.get("review", {}).get("versions", [])
            display = run_summary(capture, meta, verification) if kind == "design" and meta.get("project_id") else {}
            rows.append(dict(meta, run_id=alias, kind=kind, verification=verification, showcase=folder.parent.name == "showcase",
                module_model=display.get('module_model'),
                display_version=display.get("version"), evaluation=meta.get("evaluation") if type(meta.get("evaluation")) is bool
                    else bool(re.match(r"eval-[0-9]{4}-", alias)),
                parent_run_id=folder.parent.parent.name if folder.parent.name == "reviews" else None,
                can_report=kind == "design" and bool(meta.get("scene_snapshot_complete"))
                    and report_ready(display),
                selected_version=meta.get("final_version") if meta.get("lean") else versions[-1] if versions else None))
        except (OSError, ValueError, KeyError):
            rows.append(dict(run_id=alias, kind=kind, verification={"passed": False}, errors=["记录不可读"]))
    return public({"runs": rows})


@app.get('/api/parks')
def parks():
    rows = park_store.listing(ROOT)
    for row in rows:
        active = park_queue.current(park_queue.load(row['id'], ROOT))
        row['queue_active'] = bool(active and active.status != 'pending')
    return public(rows)


@app.post('/api/parks/{identifier}/{action}')
def change_park(identifier: str, action: str, request: Request, payload: dict = Body(...)):
    local_only(request)
    if not scene_is_public(payload):
        raise ValueError('园区只保存公开设计条件，不保存凭据')
    if action == 'save' and payload.get('id') == identifier:
        return park_store.save(payload, ROOT)
    if action == 'delete':
        park_store.delete(identifier, ROOT)
        return dict(ok=True)
    if action == 'place':
        return park_store.place(park_store.Park.model_validate(payload), ROOT).model_dump()
    if action == 'demo' and identifier == 'wujin-demo':
        return park_store.demo(ROOT)
    if action in ('report', 'open-report'):
        from . import park_report
        if action == 'report':
            return park_report.generate(park_store.load(identifier, ROOT), park_entries(final=True), ROOT)
        os.startfile(park_report.verified_pdf(identifier, ROOT))
        return dict(ok=True)
    raise ValueError('园区操作不存在')


def queue_verification(item, final):
    capture, meta, verification = record(run_folder('gz-' + item.spec.id))
    if meta.get('project_id') != item.spec.id or meta.get('session') != item.design_session:
        return None
    exported = verification.get('verified_exports', [])
    if not exported and not final:
        return None
    saved = park._exported(capture, meta, 'project/project.json')
    if saved.get('park', {}).get('snapshot') != item.snapshot:
        return None
    if exported:
        for name in ('summary', 'economics', 'design'):
            park._exported(capture, meta, f"project/exports/v{exported[-1]['version']}/{name}.json")
    checks = verification.get('checks', [])
    good = len(checks) == 4 and all(c.get('passed') is True for c in checks)
    if not final:
        return good
    if item.spec.export and not good:
        return 'failed'
    if not item.spec.review or not exported:
        return 'completed' if not item.spec.export or good and bool(exported) else 'failed'
    if meta.get('review_session_id') != item.review_session or not meta.get('review_capture'):
        return None
    return 'completed' if good and verification.get('review', {}).get('passed') is True else 'failed'


@app.get('/api/parks/{identifier}/queue')
def read_park_queue(identifier: str):
    return public(park_queue.load(identifier, ROOT).model_dump(mode='json'))


@app.get('/api/parks/{identifier}/prompt')
def park_prompt(identifier: str):
    item = park_queue.current(park_queue.load(identifier, ROOT))
    if not item:
        raise ValueError('没有活动厂房')
    if item.stage == 'design':
        return dict(brief=render_brief(item.spec))
    capture, meta, verification = record(run_folder('gz-' + item.spec.id))
    if not queue_verification(item, False):
        raise ValueError('审核需要已核验的导出')
    return dict(brief=review_prompt(item.spec.id, verification['verified_exports'][-1]['version'], item.spec.reviewer_model))


@app.post('/api/parks/{identifier}/queue/{action}')
def change_queue(identifier: str, action: str, request: Request, payload: dict = Body(...)):
    local_only(request)
    if not scene_is_public(payload):
        raise ValueError('队列不可包含凭据或私密文件路径')
    return park_queue.action(identifier, action, payload, queue_verification, ROOT)


def park_entries(final=False):
    entries = []
    for alias, folder, kind in run_entries():
        try:
            capture, meta, verification = record(folder)
        except (OSError, ValueError, KeyError):
            continue
        checks, versions = verification.get("checks", []), [row["version"] for row in verification.get("verified_exports", [])]
        review = verification.get('review', {})
        if final and review.get('requested'):
            reviews = review.get('independent' if review.get('mode') == 'independent' else 'children', [])
            if (verification.get('passed') is not True or review.get('passed') is not True or not reviews or not versions
                    or reviews[-1].get('passed') is not True or versions[-1] not in reviews[-1].get('versions', [])):
                continue
        if kind == "design" and versions and not re.match(r"eval-[0-9]{4}-", alias) and len(checks) == 4 and all(c.get("passed") is True for c in checks):
            entries.append((dict(run_id=alias, version=versions[-1], showcase=folder.parent.name == "showcase"), capture, meta))
    return entries


@app.get('/api/park')
def park_overview():
    return public(park.overview(park_entries()))


@app.get('/api/parks/{identifier}')
def named_park(identifier: str):
    with park_store.transaction(ROOT):
        saved = park_store.load(identifier, ROOT)
        data = park.named(saved, park_entries(final=True), ROOT)
        return public(dict(park=saved.model_dump(), data=data, svg=park.map_svg(data),
                           queue=park_queue.load(identifier, ROOT).model_dump(mode='json'), cost=park_cost()))


def park_cost():
    records = []
    for alias, folder, kind in run_entries():
        if kind != 'design' or alias.startswith('eval-') or folder.parent.name == 'showcase':
            continue
        try:
            _, meta, _ = record(folder)
            sessions = list(run_usage(folder).values())
            costs = [cost for row in sessions for cost in row.get('costs', [])]
            if not sessions or not costs or any(not row.get('billing_complete') for row in sessions):
                continue
            currencies = {cost['currency'] for cost in costs}
            currency = currencies.pop() if len(currencies) == 1 else None
            records.append((meta.get('ended_at') or '', currency, sum(cost['micros'] for cost in costs) / 1e6))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    recent = sorted(records, reverse=True)[:5]
    if not recent or any(row[1] is None for row in recent) or len({row[1] for row in recent}) != 1:
        return None
    return dict(currency=recent[0][1], per_building=sum(row[2] for row in recent) / len(recent), samples=len(recent))


def run_summary(capture, meta, verification):
    from .electrical import load_catalog
    base, artifacts = safe(capture, "project"), meta.get("artifacts", {})
    def present(path):
        path = safe(base, path)
        return path.is_file() and path.relative_to(capture).as_posix() in artifacts
    designs = [int(p.stem[1:]) for p in (base / "designs").glob("v*.json")
               if re.fullmatch(r"v[1-9][0-9]*", p.stem) and present(p)]
    exported = [read(safe(base, p), {}).get("version") for p in (base / "exports").glob("v*/manifest.json")]
    verified = [r["version"] for r in verification.get("verified_exports", []) if r.get("version") in designs]
    selected = meta.get("final_version") if meta.get("lean") else verified[-1] if verified else max(
        (v for v in exported if type(v) is int and v in designs), default=None)
    passed = []
    for version in designs if selected is None else []:
        path = safe(base, f"analysis/v{version}/rules.json")
        if present(path) and hashlib.sha256(path.read_bytes()).hexdigest() == artifacts[path.relative_to(capture).as_posix()]:
            if read(path, {}).get("hard_failed") == 0:
                passed.append(version)
    version = selected if selected is not None else max(passed or designs, default=None)
    required = ["project.json", f"designs/v{selected}.json", f"analysis/v{selected}/shading.json", f"analysis/v{selected}/electrical.json"]
    required += [key.removeprefix("project/") for key in artifacts if key.startswith("project/designs/")]
    module_id = meta.get('module_id')
    model = load_catalog('modules.csv').get(module_id, {}).get('model', module_id)
    return dict(version=version, selected_version=selected, verification=verification, module_model=model,
                missing=[] if all(present(path) for path in required) else ["scene"])


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str, version: int | None = Query(None, ge=1)):
    folder = run_folder(run_id)
    if not folder.is_dir():
        raise HTTPException(404, "运行不存在")
    _, meta, verification = record(folder)
    kind = "review" if folder.parent.name == "reviews" or "review" in folder.name and not folder.name.startswith("gz-") else "design"
    result = result_data(meta["project_id"], version, folder) if meta.get("project_id") else None
    options = dict(review=dict(enabled=True, mode="independent")) if kind == "review" else run_options(folder)
    usages = run_usage(folder)
    return public(dict(run=dict(meta, kind=kind, parent_run_id=folder.parent.parent.name if folder.parent.name == "reviews" else None),
                       run_id=run_id, verification=verification, run_options=options, usage=usages.get(meta.get("session")), usage_by_session=usages,
                       timeline=read(folder / "timeline.json", {"nodes": []}), result=result))


@app.post("/api/runs/{run_id}/report")
def generate_report(run_id: str):
    with LOCK:
        return public(make_report(run_folder(run_id), regenerated=True))


@app.post("/api/open")
def open_target(payload: dict = Body(...)):
    kind = payload.get("kind")
    if kind == "agh":
        suffix = "/?session=" + quote(session(payload["session_id"]), safe="") if payload.get("session_id") else "/"
        webbrowser.open(AGH_URL + suffix)
    elif kind == "report":
        folder = run_folder(payload.get("run_id"))
        metadata = read(folder / "run.json", {})
        files = metadata.get("report", {}).get("files", [])
        files = [f for f in files if re.fullmatch(r"report-v[1-9][0-9]*\.(pdf|html)", f.get("name", ""))]
        if not files:
            raise HTTPException(404, "尚无方案书")
        entry = sorted(files, key=lambda f: f["name"].endswith(".pdf"))[-1]
        path = safe(folder, "report/" + entry["name"])
        if (not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256")
                or metadata.get("artifacts", {}).get("report/" + entry["name"]) != entry.get("sha256")):
            raise ValueError("方案书文件未通过校验")
        os.startfile(path)
    elif kind in ("export", "run"):
        path = run_folder(payload.get("run_id")) if kind == "run" else safe(ROOT / "projects",
            identifier(payload.get("project_id")) + "/exports/v" + str(payload.get("version")))
        if kind == "export" and (type(payload.get("version")) is not int or payload["version"] < 1):
            raise ValueError("版本须为正整数")
        if kind == "export" and payload.get("run_id"):
            capture = record(run_folder(payload["run_id"]))[0]
            path = safe(capture, f"project/exports/v{payload['version']}")
        if not path.is_dir():
            raise HTTPException(404, "文件夹不存在")
        os.startfile(path)
    else:
        raise ValueError("只允许打开会话、方案书、导出或执行记录")
    return {"ok": True}


app.mount("/", StaticFiles(directory=ROOT / "desktop/web", html=True), name="desktop")
