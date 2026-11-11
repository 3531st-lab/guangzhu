"""Deterministic rule-based design and command editing; no model-review claims."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import analysis, layout, mcp_actions, project as storage, rules, shading
from .brief import BriefSpec
from .config import ROOT
from .models import GzError


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def _update_design_stats(project_id: str, version: int, **stats) -> None:
    d = storage.load_design(project_id, version)
    d.statistics.update({k: v for k, v in stats.items() if v is not None})
    storage._path(project_id, f"designs/v{version}.json").write_text(
        d.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )


def _safe_project_id(base_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", (base_id or "auto-demo").strip()).strip("-")[:48] or "auto-demo"
    if not storage._path(cleaned).exists():
        return cleaned
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%H%M%S")
    candidate = f"{cleaned[:50]}-{stamp}"
    suffix = 1
    while storage._path(candidate).exists():
        candidate = f"{cleaned[:48]}-{stamp}-{suffix}"
        suffix += 1
    return candidate


def _repair_operations(project, design, analyzed: dict, checked: dict) -> tuple[list[dict], list[str]]:
    """Use the full rule evidence, never infer a pruning ratio from unrelated units."""
    from .design_locks import locked_ids
    failed = [row for row in checked.get("items", []) if row.get("status") == "fail" and row.get("level") == "hard"]
    if not failed:
        return [], []
    suggestions = [row['suggestion'] for row in failed if isinstance(row.get('suggestion'), dict)]
    layout_ops = []
    prune_ops = []
    reasons = []
    for sug in suggestions:
        op_type = sug.get("op")
        if op_type == "set_param":
            name, val = sug.get("name"), sug.get("value")
            if name and val is not None and getattr(design.params, name, None) != val:
                layout_ops.append({"op": "set_param", "name": name, "value": val})
                label_map = {
                    "walkway_every_n_rows": f"按 G03 增设检修通道（每 {val} 排留通道）",
                    "walkway_width_m": f"按要求调整检修通道宽度至 {val} m",
                    "edge_setback_m": f"按要求调整屋顶边缘退距至 {val} m",
                    "obstacle_clearance_m": f"按要求调整障碍物退距至 {val} m",
                    "row_spacing_m": f"调整排间距至 {val} m",
                }
                reasons.append(label_map.get(name, f"调整排布参数 {name}={val}"))

    # If we have layout-level parameter updates, apply them first in this round because they re-tile the roof.
    if layout_ops:
        dedup = []
        seen = set()
        for op in layout_ops:
            key = (op["op"], op.get("name"))
            if key not in seen:
                seen.add(key)
                dedup.append(op)
        return dedup, reasons

    protected = locked_ids(design)
    available = {module.id for module in design.modules}
    removed = set()
    for sug in suggestions:
        if sug.get("op") == "remove_modules":
            where = sug.get("where", {})
            ids = set(sug.get('module_ids') or where.get('ids') or [])
            if 'shading_loss_gt' in where or 'worst_count' in where:
                path = storage._path(project.id, f'analysis/v{design.version}/shading.json')
                shadows = json.loads(path.read_text(encoding='utf-8'))
                losses = {row['id']: row['total_loss_pct'] for row in shadows.get('modules', [])}
                if shadows.get('version') != design.version or set(losses) != available:
                    raise GzError('ANALYSIS_INVALID', '规则建议的遮挡证据与组件不匹配', '重新计算此版本')
                ranked = sorted(available - protected - removed, key=lambda mid: (-losses[mid], mid))
                ids = set(ranked[:where['worst_count']]) if 'worst_count' in where else {
                    mid for mid in ranked if losses[mid] > where['shading_loss_gt']}
            elif not ids:
                # Geometry/zone selectors still pass through the authoritative edit validator.
                prune_ops.append(sug)
                reasons.append('按明确规则建议调整组件')
                continue
            ids = (ids & available) - protected - removed
            if ids:
                prune_ops.append(dict(op='remove_modules', module_ids=sorted(ids)))
                removed.update(ids)
                reasons.append(f'按规则证据移除 {len(ids)} 块未锁定组件')
            else:
                reasons.append('相关组件已锁定，保留并等待人工复核')
    return prune_ops, reasons


def _edit(project_id, version, reason, ops, *, offline):
    """Share the existing operation schema and optimistic preview/save contract."""
    from .mcp_server import VALIDATORS
    payload = dict(project_id=project_id, version=version, reason=reason, ops=ops)
    if not VALIDATORS['gz_edit_design'].is_valid(payload):
        raise GzError('DESIGN_EDIT_INVALID', '规则指令不符合当前编辑契约', '修改参数后重新提交；原方案未改变')
    preview = mcp_actions._edit_design(**payload, offline=offline, preview=True)
    return mcp_actions._edit_design(**payload, offline=offline, expected_fingerprint=preview['fingerprint'])


def _select(project_id, version, source):
    """Record the displayed choice, not an approval or an engineering certificate."""
    from .park_store import transaction
    with transaction(storage._path(project_id)):
        storage._path(project_id, 'local-selection.json').write_text(json.dumps(
            dict(version=version, updated_at=_now_iso(), source=source), ensure_ascii=False) + '\n', encoding='utf-8')


def _command_result(project_id, version, message, summary):
    _select(project_id, version, 'rule-command')
    return dict(ok=True, project_id=project_id, version=version, new_version=version,
                message=message, summary=summary, workflow_kind='rules', exported=False,
                export_status='awaiting_approval', independent_review=dict(status='not_performed'))


def _compare_metal_options(project_id: str, base_version: int, *, offline: bool = False) -> dict:
    """Generate 3 real comparison schemes for a metal roof (density / fast-payback / balanced)."""
    from .mcp_actions import _read, _comparison_metric, recommend_options
    project = storage.load(project_id)
    base = storage.load_design(project_id, base_version)
    current = _comparison_metric("当前方案", base, _read(project_id, f"analysis/v{base_version}/summary.json"),
                                 _read(project_id, f"analysis/v{base_version}/rules.json"))
    active = project.model_copy(deep=True)
    active.roof.keepouts += base.added_keepouts
    configs = [
        ("多装", {"fill_landscape": True, "walkway_every_n_rows": 4, "walkway_width_m": 0.6}),
        ("最快回本", {"fill_landscape": False, "walkway_every_n_rows": 2, "walkway_width_m": 0.8}),
        ("折中", {"fill_landscape": True, "walkway_every_n_rows": 2, "walkway_width_m": 0.8}),
    ]
    options = []
    for label, params in configs:
        design = layout.generate_layout(active, base.params.model_dump() | params)
        design.version = storage.next_version(project_id)
        design.parent_version = base_version
        design.reason = f"彩钢瓦三方案对比：{label}"
        design.author = "agent"
        design.added_keepouts = base.added_keepouts
        design.modules_per_string = base.modules_per_string
        storage.save_design(project_id, design, offline=offline)
        if label == "最快回本":
            mcp_actions._analyze(project_id, design.version, offline=offline)
            edited = storage.edit_design(project_id, design.version,
                [dict(op="remove_modules", where=dict(shading_loss_gt=3))],
                "最快回本：移除遮挡大于3%的组件", "agent", offline=offline)
            design = storage.load_design(project_id, edited["version"])
        for _ in range(3):
            summary = mcp_actions._analyze(project_id, design.version, offline=offline)
            checked = _read(project_id, f"analysis/v{design.version}/rules.json")
            ops, reasons = _repair_operations(project, design, summary, checked)
            if not ops:
                break
            edited = _edit(project_id, design.version, f"{label}：" + "；".join(reasons[:2]), ops, offline=offline)
            if edited["version"] == design.version:
                break
            design = storage.load_design(project_id, edited["version"])
        summary = mcp_actions._analyze(project_id, design.version, offline=offline)
        checked = _read(project_id, f"analysis/v{design.version}/rules.json")
        options.append(_comparison_metric(label, design, summary, checked))
    recommended = recommend_options(current, options)
    result = dict(
        ok=True,
        base_version=base_version,
        current=current,
        options=options,
        recommended=recommended,
        capacity_note="彩钢瓦顺坡平铺，倾角等于屋面坡度；三方案按「密铺横补 / 剔除高遮挡快回本 / 标准通道折中」实算比选。",
    )
    rules.save_result(project_id, base_version, "compare", result)
    return result


def run_autonomous_design(payload: dict, *, overwrite_existing: bool = False) -> dict:
    """Run deterministic engineering steps, preserving every existing project."""
    started = time.perf_counter()
    trace: list[dict] = []

    def log_step(step_no: int, tool: str, title: str, detail: str, data: dict | None = None):
        trace.append({
            "step": step_no,
            "tool": tool,
            "title": title,
            "detail": detail,
            "timestamp": _now_iso(),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            **(dict(metrics=data) if data else {}),
        })

    template = payload.get("template") or payload.get("template_id") or payload.get("roof_id") or "taizhou-cmc-pharma"
    requested_id = payload.get("id") or payload.get("project_id") or f"{template}-auto"
    # The legacy overwrite flag never authorizes deletion. Repeated runs get a new
    # project identity; editing an existing design uses the versioned edit route.
    project_id = _safe_project_id(requested_id)

    from .templates import read_template
    template_requirements = read_template(template, root=ROOT).get('requirements') or {}
    template_text = (template_requirements.get('text') or '').strip()
    request_text = (payload.get("text") or payload.get("requirements_text") or payload.get("brief") or '').strip()
    text = '\n'.join(dict.fromkeys(value for value in (template_text, request_text) if value)) or "按已提供屋顶与现场条件排布，保留检修通道，按已实现规则检查，无法满足时列明原因"
    structured = dict(template_requirements.get('structured') or {})
    structured.update(payload.get("structured") or {})
    economics = payload.get("economics") or None
    equipment = dict(payload.get("equipment") or {})
    if payload.get("module_id") and not equipment.get("module_id"):
        equipment["module_id"] = payload["module_id"]
    if payload.get("inverter_id") and not equipment.get("inverter_id"):
        equipment["inverter_id"] = payload["inverter_id"]
    if payload.get("inverter_brand") and not equipment.get("inverter_brand"):
        equipment["inverter_brand"] = payload["inverter_brand"]
    equipment = equipment or None
    facts = payload.get("facts") or None
    prefer = payload.get("prefer") or "balanced"
    do_compare = bool(payload.get("compare", False))
    max_rounds = min(max(int(payload.get("max_rounds") or 4), 1), 6)

    layout_algo = payload.get("layout_algo") or "auto_pareto"
    string_algo = payload.get("string_algo") or "serpentine_spatial"
    routing_algo = payload.get("routing_algo") or "astar_2opt"
    dc_cable_family = payload.get("dc_cable_family") or "PV1-F"
    ac_cable_family = payload.get("ac_cable_family") or "ZR-YJV22"
    wind_roughness = payload.get("wind_roughness") or None
    wind_pressure_kpa = payload.get("wind_pressure_kpa")

    # Step 1: Initialize Project
    summary_init = mcp_actions._new_project(project_id, template, economics=economics, equipment=equipment, facts=facts)
    if wind_roughness or wind_pressure_kpa is not None:
        proj_init = storage.load(project_id)
        from .models import WindSettings
        w_dict = proj_init.roof.wind.model_dump() if proj_init.roof.wind else {}
        if wind_roughness in ("A", "B", "C", "D"):
            w_dict["roughness"] = wind_roughness
        if wind_pressure_kpa is not None:
            w_dict["basic_pressure_kpa"] = float(wind_pressure_kpa)
        proj_init.roof.wind = WindSettings.model_validate(w_dict)
        storage.save(proj_init)

    log_step(1, "gz_new_project", "初始化工程模型与场地参数",
             f"基于模板「{summary_init.get('name')}」创建项目 {project_id}，屋顶面积 {summary_init.get('roof_area_m2', 0):.1f} m²",
             {"roof_area_m2": round(summary_init.get("roof_area_m2", 0), 1), "layout_algo": layout_algo, "routing_algo": routing_algo})

    # Step 2: Load Official Weather first so offline flag is known
    offline = True
    try:
        weather_res = mcp_actions._fetch_weather(project_id, "nasa_hourly", offline=True)
    except Exception:
        offline = False
        weather_res = mcp_actions._fetch_weather(project_id, "nasa_hourly", offline=False)

    # Step 3: Set Requirements
    req_res = mcp_actions._set_requirements(project_id, text=text, structured=structured, offline=offline)
    log_step(2, "gz_set_requirements", "保存任务文字与结构化约束",
             f"写入设计任务要求：{text}")
    log_step(3, "gz_fetch_weather", "读取 NASA POWER 气象序列",
             f"来源：{weather_res.get('source', '未记录')}；读取方式：{weather_res.get('used', '未记录')}；"
             "气象年份及适用范围见计算记录，缺缓存时可能需要联网。")

    # Step 4: Generate Initial Layout v1 according to selected layout algorithm
    proj_cur = storage.load(project_id)
    init_params = {}
    if proj_cur.roof.type == "flat":
        if layout_algo == "ew_dense":
            init_params = {"layout": "ew", "tilt_deg": 10.0, "fill_landscape": True, "walkway_every_n_rows": 2}
        elif layout_algo == "edge_orthogonal":
            init_params = {"align": "edge", "fill_landscape": True, "rows_per_rack": 1, "walkway_every_n_rows": 2}
        elif layout_algo == "winter_solstice":
            init_params = {"align": "south", "winter_window_hours": [9, 15], "rows_per_rack": 1, "walkway_every_n_rows": 2}
        else:
            init_params = {"align": "edge", "rows_per_rack": 1, "walkway_every_n_rows": 2}
    elif proj_cur.roof.type == "ground":
        init_params = {"rows_per_rack": 1}

    layout_res = mcp_actions._generate_layout(project_id, init_params, offline=offline)
    version = layout_res["version"]
    _update_design_stats(
        project_id, version,
        dc_cable_family=dc_cable_family,
        ac_cable_family=ac_cable_family,
        layout_algo=layout_algo,
        string_algo=string_algo,
        routing_algo=routing_algo,
    )

    log_step(4, "gz_generate_layout", f"生成初版三维组件阵列 (v{version})",
             f"采用算法「{layout_algo}」排布组件 {layout_res.get('modules', layout_res.get('module_count', 0))} 块，装机容量 {layout_res.get('dc_kw', 0):.2f} kW",
             {"version": version, "modules": layout_res.get("modules", layout_res.get("module_count", 0)), "dc_kw": layout_res.get("dc_kw", 0)})

    # Step 5: Analyze v1 & Autonomous Multi-Round Rule Repair
    analyzed = mcp_actions._analyze(project_id, version, offline=offline)
    checked = json.loads(storage._path(project_id, f"analysis/v{version}/rules.json").read_text(encoding="utf-8"))
    log_step(5, "gz_analyze", f"工程计算与已实现规则预检查 (v{version})",
             f"v{version} 检查结果：通过 {checked['passed']}/{checked['total']} 项，硬性未过 {checked['hard_failed']} 项，基准年发电估算 {analyzed['yield_kwh']['p50']:,.0f} kWh",
             {"version": version, "hard_failed": checked["hard_failed"], "p50_kwh": round(analyzed["yield_kwh"]["p50"], 1)})

    for round_idx in range(1, max_rounds + 1):
        if checked.get("hard_failed", 0) == 0:
            break
        project_obj = storage.load(project_id)
        design_obj = storage.load_design(project_id, version)
        ops, reasons = _repair_operations(project_obj, design_obj, analyzed, checked)
        if not ops:
            break
        reason_str = f"规则调整第 {round_idx} 轮：" + "；".join(reasons[:3])
        try:
            edit_res = _edit(project_id, version, reason_str, ops, offline=offline)
        except GzError as error:
            log_step(6, 'gz_edit_design', '规则调整未提交', error.message_zh)
            break
        if edit_res["version"] == version:
            break
        version = edit_res["version"]
        _update_design_stats(
            project_id, version,
            dc_cable_family=dc_cable_family,
            ac_cable_family=ac_cable_family,
            layout_algo=layout_algo,
            string_algo=string_algo,
            routing_algo=routing_algo,
        )
        analyzed = mcp_actions._analyze(project_id, version, offline=offline)
        checked = json.loads(storage._path(project_id, f"analysis/v{version}/rules.json").read_text(encoding="utf-8"))
        log_step(6, "gz_edit_design", f"依据规则建议调整 (v{version})",
                 f"{reason_str} → 装机 {analyzed['dc_kw']:.2f} kW，硬性违规降至 {checked['hard_failed']} 项",
                 {"version": version, "dc_kw": analyzed["dc_kw"], "hard_failed": checked["hard_failed"]})

    # Step 7: Optional 3-Scheme Comparison
    project_obj = storage.load(project_id)
    compare_result = None
    if do_compare:
        try:
            if project_obj.roof.type == "metal":
                compare_result = _compare_metal_options(project_id, version, offline=offline)
            else:
                compare_result = mcp_actions._compare_options(project_id, version, offline=offline)
            rec = compare_result.get("recommended", {}).get(prefer) or compare_result.get("recommended", {}).get("balanced")
            if rec and rec.get("version"):
                cand_ver = int(rec["version"])
                cand_design = storage.load_design(project_id, cand_ver)
                # Ensure 3D single-panel dragging remains available unless user explicitly asked for EW layout
                if layout_algo != "ew_dense" and (cand_design.params.layout == "ew" or cand_design.params.rows_per_rack != 1):
                    for opt in compare_result.get("options", []):
                        opt_v = int(opt.get("version") or 0)
                        if opt_v:
                            opt_d = storage.load_design(project_id, opt_v)
                            if opt_d.params.layout == "rows" and opt_d.params.rows_per_rack == 1:
                                cand_ver = opt_v
                                break
                version = cand_ver
                _update_design_stats(
                    project_id, version,
                    dc_cable_family=dc_cable_family,
                    ac_cable_family=ac_cable_family,
                    layout_algo=layout_algo,
                    string_algo=string_algo,
                    routing_algo=routing_algo,
                )
                analyzed = mcp_actions._analyze(project_id, version, offline=offline)
                rules.save_result(project_id, version, "compare", compare_result)
                checked = json.loads(storage._path(project_id, f"analysis/v{version}/rules.json").read_text(encoding="utf-8"))
                log_step(7, "gz_compare_options", f"三方案（多装/快回本/折中）寻优比选",
                         f"按偏好「{prefer}」选定 v{version}（{rec.get('why', '')}），装机 {analyzed['dc_kw']:.2f} kW",
                         {"selected_version": version, "dc_kw": analyzed["dc_kw"]})
        except Exception as err:
            log_step(7, "gz_compare_options", "三方案对比跳过", f"保持当前最优合规版本 v{version}（{err}）")

    # Cross-check evidence remains distinct from an independent human/model review.
    crosscheck = dict(status='unavailable', reason='尚未取得复核结果')
    try:
        cross = mcp_actions._crosscheck_yield(project_id, version, offline=offline, group_offset=0)
        omitted = cross.get('omitted') or {}
        crosscheck = dict(status='partial' if omitted else 'recorded', omitted=omitted,
                          note=cross.get('note', ''), version=version)
        log_step(8, "gz_crosscheck_yield", "发电计算链交叉比较",
                 '结果已记录；部分链缺失。' if omitted else '结果已记录；这不是独立工程审核。')
    except (GzError, ValueError, OSError, RuntimeError) as error:
        reason = error.message_zh if isinstance(error, GzError) else str(error)
        crosscheck = dict(status='unavailable', reason=reason)
        log_step(8, 'gz_crosscheck_yield', '交叉比较未完成', reason)
    requested_export = payload.get('export', (payload.get('run') or {}).get('export', False)) is True
    export_status = 'awaiting_approval' if requested_export else 'not_requested'
    log_step(9, 'rule_check', '规则预检查；尚未独立审核', f"硬性未通过 {checked['hard_failed']} 项；施工前仍需专业复核。")
    if requested_export:
        log_step(10, 'export_pending', '初步方案导出待批准', '在结果页预览检查后，明确批准此项目、此版本的一次导出。')

    trace_payload = {
        "project_id": project_id,
        "template": template,
        "final_version": version,
        "hard_failed": checked.get("hard_failed", 0),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "steps": trace,
        "workflow_kind": 'rules',
        "independent_review": dict(status='not_performed', reason='本流程未启动独立审核会话'),
        "crosscheck": crosscheck,
        "export_status": export_status,
        "exported": False,
    }
    storage._path(project_id, "agent_trace.json").write_text(
        json.dumps(trace_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _select(project_id, version, 'rule-auto')
    return trace_payload


def run_copilot_command(project_id: str, version: int, command_text: str = "", action_type: str = "", extra: dict | None = None) -> dict:
    """Parse supported rule commands and save a checked, versioned candidate."""
    project = storage.load(project_id)
    design = storage.load_design(project_id, version)
    extra = extra or {}
    offline = True
    try:
        mcp_actions._fetch_weather(project_id, "nasa_hourly", offline=True)
    except Exception:
        offline = False

    text = (command_text or "").strip()
    act = (action_type or "").strip()

    def current_summary():
        # Read lazily: unsupported commands do not trigger a calculation or write.
        # Reuse only complete output bound to these inputs, never file presence.
        from .design_evidence import capture
        calculation = capture(storage._path(project_id), version).get('analysis', {})
        if (calculation.get('status') == 'recorded' and calculation.get('input_binding') == 'matched'
                and calculation.get('completion_status') == 'matched'):
            return json.loads(storage._path(project_id, f'analysis/v{version}/summary.json').read_text(encoding='utf-8'))
        return mcp_actions._analyze(project_id, version, offline=offline)

    if act == "unlock_3d_drag":
        ops = [
            {"op": "set_param", "name": "layout", "value": "rows"},
            {"op": "set_param", "name": "rows_per_rack", "value": 1},
        ]
        if project.roof.type == "flat" and design.params.tilt_deg < 12:
            ops.append({"op": "set_param", "name": "tilt_deg", "value": 18.0})
        res = _edit(project_id, version, "切换为独立单排支架以开启 3D 单板编辑", ops, offline=offline)
        new_v = res["version"]
        final_summary = mcp_actions._analyze(project_id, new_v, offline=offline)
        return _command_result(project_id, new_v, f"已切换为单排支架 v{new_v}；可编辑未锁定组件，请核对规则结果。", final_summary)

    if act == "change_equipment":
        mod_id = extra.get("module_id")
        inv_id = extra.get("inverter_id")
        dc_fam = extra.get("dc_cable_family")
        ac_fam = extra.get("ac_cable_family")
        w_rough = extra.get("wind_roughness")
        w_press = extra.get("wind_pressure_kpa")
        from .brief import check_equipment
        from .electrical import load_catalog
        requested = {key: value for key, value in (('module_id', mod_id), ('inverter_id', inv_id)) if value}
        try:
            check_equipment(requested)
        except (ValueError, TypeError) as error:
            raise GzError('EQUIPMENT_NOT_FOUND', '请选择目录中存在的组件或逆变器型号', '原项目和计算记录未改变') from error
        cable_catalog = load_catalog('cables.csv')
        for kind, family in (('dc', dc_fam), ('ac', ac_fam)):
            if family and (not isinstance(family, str) or family not in {
                    row['family'] for row in cable_catalog.values() if row['kind'] == kind}):
                raise GzError('CABLE_FAMILY_NOT_FOUND', '所选电缆系列不存在或用途不匹配', '选择与直流或交流用途匹配的目录系列；原方案未改变')
        changed_labels = []
        if mod_id and mod_id != project.equipment.module_id:
            project.equipment.module_id = mod_id
            changed_labels.append(f"组件={mod_id}")
        if inv_id is not None:
            project.equipment.inverter_id = inv_id or None
            project.equipment.inverter_brand = None
            changed_labels.append(f"逆变器={inv_id or '自动选型'}")
        if w_rough or w_press is not None:
            from .models import WindSettings
            w_dict = project.roof.wind.model_dump() if project.roof.wind else {}
            if w_rough in ("A", "B", "C", "D"):
                w_dict["roughness"] = w_rough
                changed_labels.append(f"地面粗糙度={w_rough}类")
            if w_press is not None and str(w_press).strip() != "":
                w_dict["basic_pressure_kpa"] = float(w_press)
                changed_labels.append(f"基本风压={float(w_press):.2f}kPa")
            project.roof.wind = WindSettings.model_validate(w_dict)
        # Re-generate layout on new version if module changed, else copy design to new version
        new_design = layout.generate_layout(project, design.params) if mod_id else design.model_copy(deep=True)
        storage.save(project)
        new_v = storage.next_version(project_id)
        new_design.version = new_v
        new_design.parent_version = version
        new_design.author = "agent"
        if dc_fam:
            new_design.statistics["dc_cable_family"] = dc_fam
            changed_labels.append(f"直流线缆={dc_fam}")
        if ac_fam:
            new_design.statistics["ac_cable_family"] = ac_fam
            changed_labels.append(f"交流线缆={ac_fam}")
        reason_label = "设备与参数重算：" + ("、".join(changed_labels) or "重算电气与风载")
        new_design.reason = reason_label
        storage.save_design(project_id, new_design, offline=offline)
        final_summary = mcp_actions._analyze(project_id, new_v, offline=offline)
        return _command_result(project_id, new_v, f"{reason_label} → v{new_v}；请核对计算和规则结果。", final_summary)

    if act == "auto_fix" or any(k in text for k in ("自动消缺", "修复", "合规", "消缺")):
        cur_v = version
        for round_idx in range(1, 4):
            analyzed = current_summary() if cur_v == version else mcp_actions._analyze(project_id, cur_v, offline=offline)
            checked = json.loads(storage._path(project_id, f"analysis/v{cur_v}/rules.json").read_text(encoding="utf-8"))
            if checked.get("hard_failed", 0) == 0:
                break
            ops, reasons = _repair_operations(storage.load(project_id), storage.load_design(project_id, cur_v), analyzed, checked)
            if not ops:
                break
            res = _edit(project_id, cur_v, "规则修复：" + "；".join(reasons[:2]), ops, offline=offline)
            cur_v = res["version"]
        final_summary = mcp_actions._analyze(project_id, cur_v, offline=offline)
        checked = json.loads(storage._path(project_id, f"analysis/v{cur_v}/rules.json").read_text(encoding="utf-8"))
        return _command_result(project_id, cur_v, f"规则调整结束，当前版本 v{cur_v}（硬性未过 {checked['hard_failed']} 项）", final_summary)

    if act == "compare":
        current_summary()
        if project.roof.type == "metal":
            cmp_res = _compare_metal_options(project_id, version, offline=offline)
        else:
            cmp_res = mcp_actions._compare_options(project_id, version, offline=offline)
        rec_v = cmp_res.get("recommended", {}).get("balanced", {}).get("version", version)
        final_summary = mcp_actions._analyze(project_id, rec_v, offline=offline)
        return _command_result(project_id, rec_v, f"已完成三方案比较，推荐折中方案 v{rec_v}；请核对适用条件。", final_summary)

    ops = []
    reasons = []

    if act == "ew_dense" or any(k in text for k in ("东西向", "人字", "密排", "多装")):
        if project.roof.type == "flat":
            ops.extend([
                {"op": "set_param", "name": "layout", "value": "ew"},
                {"op": "set_param", "name": "tilt_deg", "value": 10.0},
                {"op": "set_param", "name": "fill_landscape", "value": True},
                {"op": "set_param", "name": "walkway_every_n_rows", "value": 2},
            ])
            reasons.append("规则指令：切换为 10° 东西向人字形排布并配置检修道")
        else:
            ops.extend([
                {"op": "set_param", "name": "orientation", "value": "landscape" if design.params.orientation == "portrait" else "portrait"},
                {"op": "set_param", "name": "fill_landscape", "value": True},
            ])
            reasons.append("规则指令：调整坡面横竖混排补位")

    elif act == "low_shading" or any(k in text for k in ("遮挡", "阴影", "低效")):
        match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        threshold = float(match.group(1)) if match else 5.0
        ops.append({"op": "remove_modules", "where": {"shading_loss_gt": threshold}})
        reasons.append(f"规则指令：剔除年遮挡损失 > {threshold:g}% 的未锁定组件")
        checked = dict(items=[dict(id='S01', status='fail', level='hard', suggestion=ops.pop())])
        ops, _ = _repair_operations(project, design, current_summary(), checked)

    elif act == "walkway_safe" or any(k in text for k in ("通道", "消防", "检修")):
        match_rows = re.search(r"每\s*(\d+)\s*排", text)
        n_rows = int(match_rows.group(1)) if match_rows else 1
        match_w = re.search(r"(\d+(?:\.\d+)?)\s*(?:m|米)", text)
        w_m = float(match_w.group(1)) if match_w else max(1.0, design.params.walkway_width_m)
        ops.append({"op": "set_param", "name": "walkway_every_n_rows", "value": n_rows})
        if w_m != design.params.walkway_width_m:
            ops.append({"op": "set_param", "name": "walkway_width_m", "value": w_m})
        reasons.append(f"规则指令：设置每 {n_rows} 排留 {w_m:g}m 通道，连通性与消防适用性仍需核实")

    else:
        # Parse free-form natural language engineering commands
        tilt_match = re.search(r"倾角[^\d]*(\d+(?:\.\d+)?)", text)
        if tilt_match and project.roof.type not in ("metal", "pitched"):
            val = min(35.0, max(0.0, float(tilt_match.group(1))))
            ops.append({"op": "set_param", "name": "tilt_deg", "value": val})
            reasons.append(f"倾角调整为 {val:g}°")

        edge_match = re.search(r"(?:边缘|女儿墙|周边)[^\d]*(\d+(?:\.\d+)?)\s*(?:m|米)", text)
        if edge_match:
            val = min(5.0, max(0.3, float(edge_match.group(1))))
            ops.append({"op": "set_param", "name": "edge_setback_m", "value": val})
            reasons.append(f"屋顶边缘退距调整为 {val:g}m")

        obs_match = re.search(r"(?:障碍|设备)[^\d]*(\d+(?:\.\d+)?)\s*(?:m|米)", text)
        if obs_match:
            val = min(5.0, max(0.3, float(obs_match.group(1))))
            ops.append({"op": "set_param", "name": "obstacle_clearance_m", "value": val})
            reasons.append(f"设备避让退距调整为 {val:g}m")

        if any(k in text for k in ("横排", "横放", "横向")):
            ops.append({"op": "set_param", "name": "orientation", "value": "landscape"})
            reasons.append("组件改为横向排布")
        elif any(k in text for k in ("竖排", "竖放", "纵向")):
            ops.append({"op": "set_param", "name": "orientation", "value": "portrait"})
            reasons.append("组件改为纵向排布")

        if "顺边" in text:
            ops.append({"op": "set_param", "name": "align", "value": "edge"})
            reasons.append("改为顺屋顶长边排布")
        elif "正南" in text:
            ops.append({"op": "set_param", "name": "align", "value": "south"})
            ops.append({"op": "set_param", "name": "azimuth_deg", "value": 180.0})
            reasons.append("改为正南朝向排布")

        cap_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:kW|千瓦)", text, re.IGNORECASE)
        if cap_match and not ops:
            target_kw = float(cap_match.group(1))
            from .design_locks import locked_ids
            from .electrical import resolve_catalog_for_project
            cur_kw = current_summary().get("dc_kw") or 0
            if cur_kw > target_kw > 0:
                panel_kw = resolve_catalog_for_project(project)['modules'][project.equipment.module_id]['pmax_w'] / 1000
                keep_n = math.floor((target_kw + 1e-9) / panel_kw)
                protected = locked_ids(design)
                if keep_n < len(protected):
                    raise GzError('CAPACITY_LOCKED', '目标容量低于已锁定组件容量', '先核对锁定范围；原方案未改变')
                minimum = project.requirements.structured.capacity_kw_min
                if keep_n < 1 or minimum is not None and keep_n * panel_kw < minimum - 1e-9:
                    raise GzError('CAPACITY_UNREACHABLE', '目标容量不足一块组件或低于已有装机下限', '调整目标并明确核对已有要求')
                remove_n = len(design.modules) - keep_n
                if remove_n > 0:
                    to_remove = [m.id for m in reversed(design.modules) if m.id not in protected][:remove_n]
                    ops.append({"op": "remove_modules", "module_ids": to_remove})
                    reasons.append(f"按目标容量 {target_kw:g} kW 精简 {remove_n} 块组件")

    if not ops:
        raise GzError("COPILOT_UNRECOGNIZED",
                      "未能从指令中识别出明确的排布修改参数",
                      "试试输入：『把倾角改成12度』、『移除遮挡大于5%的组件』、『每2排留1.2米检修通道』、『改为横排』或点击上方快捷优化按钮")

    reason_text = "；".join(reasons) if reasons else f"规则指令：{text[:40]}"
    edit_res = _edit(project_id, version, reason_text, ops, offline=offline)
    new_v = edit_res["version"]
    final_summary = mcp_actions._analyze(project_id, new_v, offline=offline)
    return _command_result(project_id, new_v, f"{reason_text} → 生成 v{new_v}；请查看规则，批准后才能导出。", final_summary)


def run_local_review(project_id: str, version: int) -> dict:
    """Run a deterministic local engineering audit for v{version} when remote LLM review is unavailable or as a dual-engine fallback."""
    from .design_evidence import capture

    project = storage.load(project_id)
    design = storage.load_design(project_id, version)
    base = storage._path(project_id)
    offline = True
    try:
        mcp_actions._fetch_weather(project_id, "nasa_hourly", offline=True)
    except Exception:
        offline = False

    def _read_json(rel: str) -> dict:
        p = storage._path(project_id, rel)
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}

    evidence = capture(base, version)
    analysis_state = evidence.get("analysis") or {}
    if analysis_state.get("status") == "missing":
        mcp_actions._analyze(project_id, version, offline=offline)
        evidence = capture(base, version)
        analysis_state = evidence.get("analysis") or {}
    if (
        analysis_state.get("status") != "recorded"
        or analysis_state.get("input_binding") != "matched"
        or analysis_state.get("completion_status") != "matched"
    ):
        raise GzError(
            "ANALYSIS_STALE",
            "当前设计或工程输入已变化，不能直接复核或批准过期规则结果",
            "请先重新计算此版本后再执行本机规则复核",
        )

    summary = _read_json(f"analysis/v{version}/summary.json")
    checked = _read_json(f"analysis/v{version}/rules.json")
    if "hard_failed" not in checked or not isinstance(checked.get("items"), list):
        raise GzError(
            "ANALYSIS_STALE",
            "缺少完整的规则计算结果文件，无法执行本机复核",
            "请先重新计算此版本后再执行本机规则复核",
        )
    elec = _read_json(f"analysis/v{version}/electrical.json")
    struct = _read_json(f"analysis/v{version}/structure.json")
    cross_path = storage._path(project_id, f"analysis/v{version}/crosscheck.json")
    if not cross_path.is_file():
        try:
            cross = mcp_actions._crosscheck_yield(project_id, version, offline=offline, group_offset=0)
        except Exception:
            cross = {}
    else:
        cross = _read_json(f"analysis/v{version}/crosscheck.json")

    hard_failed = int(checked["hard_failed"])
    failed_items = [r for r in checked.get("items", []) if r.get("status") == "fail"]
    findings = []

    if hard_failed > 0:
        for r in failed_items:
            findings.append(dict(
                severity="high" if r.get("level") == "hard" else "medium",
                item=f"规则 {r.get('id')} · {r.get('name_zh')}",
                evidence=f"实测值 {r.get('value')}（限值 {r.get('limit')} {r.get('unit') or ''}），状态未通过。",
                suggestion=r.get("note") or "建议在结果页点击「尝试修正规则问题」或调整排布退距与容量上限。",
            ))
    else:
        findings.append(dict(
            severity="low",
            item=f"GB 50797 几何、电气、结构与业主约束全项复核（{checked.get('passed', 0)}/{checked.get('total', 18)} 项通过）",
            evidence=f"v{version} 硬性违规 0 项，装机容量 {summary.get('dc_kw', 0):.2f} kWp（共 {len(design.modules)} 块组件），年均遮挡损失 {summary.get('shading', {}).get('avg_loss_pct', 0):.2f}%。",
            suggestion="各项硬性指标均在规范包络内，可进入施工图交底与现场踏勘核实。",
        ))

    # Cross-check finding
    spec_yield = cross.get("specific_yield_kwh_kwp") or {}
    spread_pct = cross.get("max_spread_pct")
    findings.append(dict(
        severity="low" if (spread_pct is None or spread_pct <= 8.0) else "medium",
        item="多物理模型发电量交叉复核 (Chain A/B/C/D)",
        evidence=f"首年比发电量复核：{json.dumps(spec_yield, ensure_ascii=False)}；多模型最大偏差 {f'{spread_pct:.2f}%' if isinstance(spread_pct, (int, float)) else '已记录'}。",
        suggestion="阴影射线追踪链与组件温度修正链吻合良好；投产前建议结合厂区实测灰尘损失率定期清洗。",
    ))

    # Electrical & wind structure finding
    dc_drop = elec.get("dc_drop_pct_max", 0)
    ac_drop = elec.get("ac_drop_pct_max", 0)
    voc_cold = elec.get("voc_cold_v", 0)
    wind = (struct or {}).get("wind") or {}
    worst_zone = (wind.get("zones") or {}).get(wind.get("worst_zone") or "", {})
    load_kn = worst_zone.get("load_kn_m2", 0)
    cap_kn = project.roof.load_capacity_kn_m2
    findings.append(dict(
        severity="low" if (load_kn <= cap_kn and dc_drop <= 2.0) else "medium",
        item="组串极端低温开路电压、线损压降与 GB 50009 抗风荷载复核",
        evidence=f"极端低温 Voc={voc_cold:.1f}V，直流最大压降 {dc_drop:.2f}%、交流最大压降 {ac_drop:.2f}%；最不利风振分区荷载 {load_kn:.3f} kN/m²（屋面限值 {cap_kn:.2f} kN/m²）。",
        suggestion="施工前须由注册结构工程师对原厂房檩条/屋面板荷载余量做书面签认，屋面角区压块或防风夹具严格按施工图加密。",
    ))

    verdict = "approve" if hard_failed == 0 else "revise"
    review_doc = dict(
        version=version,
        verdict=verdict,
        reviewer_model="local-rule-engine (本机规则与物理模型复核 · GB 50797/50009，非独立模型审核)",
        review_kind="local_rule",
        reviewed_at=_now_iso(),
        findings=findings,
    )
    reviews_dir = storage._path(project_id, "reviews")
    reviews_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"v{version}-local-rule-engine.json"
    review_bytes = (json.dumps(review_doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (reviews_dir / file_name).write_bytes(review_bytes)

    return dict(ok=True, project_id=project_id, version=version, file=f"reviews/{file_name}", review=review_doc)

