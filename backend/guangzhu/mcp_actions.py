"""MCP actions delegate calculation to the existing engineering modules."""

import hashlib
import itertools
import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from shapely.geometry import Polygon

from . import analysis, economics, electrical, layout, project as storage, rules, shading, structure, weather, yieldsim
from .catalog import load_cec_equipment
from .config import ROOT
from .models import Economics, GzError, Project, Requirements, validated
from .runtime_diagnostics import stage
from .templates import resolve
from .tilt import choose as choose_tilts, irradiation_by_tilt
from .code_identity import CODE_IDENTITY
from .installation import inherit_keepouts


def _read(project_id, relative):
    return json.loads(storage._path(project_id, relative).read_text(encoding="utf-8"))


def _write(path, record, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def _new_project(project_id, template, economics=None, equipment=None, facts=None):
    from .park_store import transaction
    with transaction(ROOT):
        return _new_project_snapshot(project_id, template, economics, equipment, facts)


def _new_project_snapshot(project_id, template, economics=None, equipment=None, facts=None):
    source = resolve(template, root=ROOT).parent
    labels = dict(price_self_cny_kwh="自用电价（元/度）", self_use_ratio="自用比例",
                  capex_cny_per_w="造价（元/W）", price_export_cny_kwh="余电上网电价（元/度）",
                  monthly_kwh="月用电量（度）", shifts="生产班次")
    from .economic_fields import LABELS
    labels.update(LABELS)
    changes = economics or {}
    if set(changes) - set(labels):
        raise GzError("ECONOMICS_INVALID", "任务书经济参数字段不正确", "只填写自用电价、比例、造价和余电上网电价")
    original = storage._read(source / "project.json", Project)
    if changes.get('monthly_kwh') is not None and changes.get('shifts') is not None and 'self_use_ratio' not in changes:
        original.economics.self_use_ratio = None
    updated = validated(Economics, original.economics.model_dump() | changes, "ECONOMICS_INVALID")
    if changes:
        shown = lambda v: format(v, 'g') if type(v) in (int, float) else str(v)
        note = "任务书覆盖：" + "；".join(f"{label}={shown(getattr(updated, key))}" for key, label in labels.items() if key in changes)
        updated.assumptions_note = (updated.assumptions_note or "") + "\n" + note
    from .brief import check_equipment
    if equipment is not None:
        try:
            check_equipment(equipment)
        except ValueError as error:
            raise GzError('EQUIPMENT_NOT_FOUND', '请选择目录中匹配的组件、逆变器品牌或型号', '核对equipment中的品牌和型号') from error
    from .models import SiteFacts
    validated_facts = validated(SiteFacts, facts, 'FACTS_INVALID') if facts is not None else None
    project = storage.init(source, project_id)
    if validated_facts is not None:
        project.facts = validated_facts
        storage.save(project)
    if changes:
        project.economics = updated
        storage.save(project)
    if equipment:
        for key, value in equipment.items():
            setattr(project.equipment, key, value)
        storage.save(project)
    return dict(_project_summary(project_id), created=True, code_identity=dict(CODE_IDENTITY))


def _project_summary(project_id):
    project = storage.load(project_id)
    roof = Polygon(project.roof.outline)
    version = storage.next_version(project_id) - 1
    design = storage.load_design(project_id, version) if version else None
    summaries = [storage._path(project_id, f"analysis/v{v}/summary.json") for v in range(version, 0, -1)]
    latest = next((json.loads(p.read_text(encoding="utf-8")) for p in summaries if p.exists()), None)
    from .wind import facts as wind_facts
    load_path = storage._path(project_id, f"analysis/v{latest['version']}/structure.json") if latest else None
    archived_wind = json.loads(load_path.read_text(encoding='utf-8')).get('wind') if load_path and load_path.is_file() else None
    wind = wind_facts(archived_wind, latest['version'] if latest else None)
    zones = lambda values: [dict(id=z.id, label=z.label) for z in values]
    return dict(ok=True, project_id=project_id, name=project.name, site=project.site.model_dump(),
                **(dict(use=project.roof.use) if project.roof.use else {}),
                **(dict(roof_type="metal", slope_deg=project.roof.slope_deg, slope_azimuth_deg=project.roof.slope_azimuth_deg)
                   if project.roof.type == "metal" else {}),
                **(dict(roof_type='pitched', plane_count=len(project.roof.planes)) if project.roof.type == 'pitched' else {}),
                **(dict(roof_type=project.roof.type, installation='新建安装面') if project.roof.type in ('ground', 'carport') else {}),
                roof_area_m2=roof.area, roof_bounds_m=list(roof.bounds), obstacles=zones(project.roof.obstacles),
                edge_azimuth_deg=layout.edge_azimuth(project.roof.outline),
                keepouts=zones([*project.roof.keepouts, *(design.added_keepouts if design else [])]),
                **(dict(surroundings=zones(project.roof.surroundings)) if project.roof.surroundings else {}),
                obstacle_count=len(project.roof.obstacles), keepout_count=len(project.roof.keepouts) + (len(design.added_keepouts) if design else 0),
                versions=project.designs, version=version or None, modules=len(design.modules) if design else 0,
                exported_versions=sorted(int(p.parent.name[1:]) for p in storage._path(project_id, "exports").glob("v*/manifest.json")
                                         if p.parent.name[1:].isdigit() and int(p.parent.name[1:]) > 0),
                dc_kw=design.statistics.get("dc_kw", 0) if design else 0,
                requirements=project.requirements.structured.model_dump(exclude_none=True),
                wind=wind,
                latest_analysis=None if latest is None else dict(version=latest["version"], **latest["rules"]))


def _capacity_ceiling(project, base, offline=False):
    """What the 「多装」 option of gz_compare_options can reach: the lowest allowed tilt in each arrangement, the walkway rule
    applied and panels over the shading threshold left out. 0 when it cannot be worked out, so the default layout stands."""
    from .installation import effective
    from .orientation import views
    from .tilt import FLOOR_DEG
    project = effective(project, base)
    if project.roof.type in ('metal', 'pitched'):  # flush or per-plane: no tilt to lower, the default layout is the most
        return 0.0
    requirement = project.requirements.structured
    bounds = requirement.tilt_deg_range
    if project.roof.type == 'carport':
        bounds = (max(0, bounds[0]), min(15, bounds[1])) if bounds else (0, 15)
    if requirement.max_height_m is not None and project.roof.type != 'carport':
        from .personal import tilt_bounds
        bounds = tilt_bounds(project, base.params.model_copy(update=dict(layout='rows')))
    bearings = dict(south=180, edge=layout.edge_azimuth(project.roof.outline))
    if project.roof.type == 'carport':
        bearings = dict(south=project.roof.planes[0].slope_azimuth_deg if project.roof.planes else 180)
    configurations = [dict(align=align, tilt_deg=bounds[0] if bounds else FLOOR_DEG, layout='rows', fill_landscape=True,
                           winter_window_hours=[10, 14]) for align in bearings if not (align == 'edge' and bearings[align] == 180)]
    best = 0.0  # east-west rows pack more panels but did not survive the full rule checks in comparisons, so they are not counted
    for parameters in configurations:
        try:
            design = layout.generate_layout(project, base.params.model_dump() | parameters)
            for _ in range(2):
                check = next((c for _, view in views(design) if (c := rules.walkway_check(project, view))['status'] == 'fail'), {})
                if check.get('status') != 'fail' or check['suggestion'] is None:
                    break
                design = layout.generate_layout(project, design.params.model_dump() | {check['suggestion']['name']: check['suggestion']['value']})
            shadows = shading.analyze_design(project, design, offline=offline)
            kept = sum(1 for row in shadows['modules'] if row['total_loss_pct'] <= shadows['summary']['threshold_pct'])
            best = max(best, design.statistics['dc_kw'] * kept / max(1, len(design.modules)))
        except (GzError, OSError, ValueError, RuntimeError):
            continue
    return best


def _set_requirements(project_id, text, structured, offline=False):
    project = storage.load(project_id)
    project.requirements = validated(Requirements, dict(text=text, structured=structured), "REQUIREMENTS_INVALID")
    from .personal import curtailment
    try:
        if project.roof.type == 'metal' and project.requirements.structured.max_height_m is not None:
            from .personal import tilt_bounds
            tilt_bounds(project, layout.LayoutParams())
        default = layout.generate_layout(project, {})
    except GzError as error:
        if error.error_code != 'HEIGHT_CONFLICT':
            raise
        storage.save(project)
        return dict(ok=True, requirements=project.requirements.model_dump(exclude_none=True), missing=[], contradictions=[error.message_zh])
    maximum, lower = default.statistics["dc_kw"], project.requirements.structured.capacity_kw_min
    if lower is not None and lower > maximum:  # the default layout falls short: judge by what the 多装 option reaches, rounded down
        with stage('requirements.capacity-ceiling'):
            maximum = max(maximum, math.floor(_capacity_ceiling(project, default, offline=offline)))
    result = economics.check_requirements_consistency(project.requirements.structured, project, max_capacity_kw=maximum)
    req = project.requirements.structured
    if req.export_allowed is False and req.capacity_kw_min is not None and project.economics.monthly_kwh and project.economics.shifts:
        try:
            shadows = shading.analyze_design(project, default, offline=offline)
            energy, _ = analysis.generation(project, default, shadows, default.statistics['dc_kw'], offline=offline)
            estimate = curtailment(project, energy, len(default.modules))
            maximum = default.statistics['dc_kw'] * (1 - estimate['worst_count'] / max(1, len(default.modules)))
            if maximum < req.capacity_kw_min:
                result['contradictions'].append(f'不上网按逐时发电同比例估算最多{maximum:.3f}kW，低于装机下限{req.capacity_kw_min:g}kW')
        except (OSError, ValueError, RuntimeError, GzError) as error:
            result['missing'].append(f'逐时天气/发电不可用（{type(error).__name__}），用电封顶与装机下限一致性未核实；有数据后须复核U05')
    storage.save(project)
    return dict(ok=True, requirements=project.requirements.model_dump(exclude_none=True), **result)


def _fetch_weather(project_id, source, year=2023, offline=False):
    site = storage.load(project_id).site
    frame, metadata = (weather.load_nasa_hourly(site.lat, site.lon, year, offline=offline) if source == "nasa_hourly"
                       else weather.load_pvgis_tmy(site.lat, site.lon, offline=offline))
    qc = weather.weather_qc(frame, site.lat, site.lon)
    return dict(ok=True, rows=qc["rows"], missing_counts=qc["missing_counts"],
                annual_ghi_kwh_m2=qc["annual_ghi_kwh_m2"], temp_min_c=float(frame.temp_air.min()),
                temp_max_c=float(frame.temp_air.max()), cache_hit=metadata["used"] in ("cache", "demo"),
                used=metadata["used"], source=metadata["source_description"])


def _generate_layout(project_id, params, offline=False):
    project = storage.load(project_id)
    design = layout.generate_layout(project, params)
    design.version, design.parent_version = storage.next_version(project_id), None
    design.author, design.reason = "agent", "按参数排板"
    storage.save_design(project_id, design, offline=offline)
    keys = ("dc_kw", "rows", "row_spacing_m", "obstacle_area_m2", "keepout_area_m2")
    return dict(ok=True, version=design.version, modules=len(design.modules),
                **(dict(fill_landscape_count=design.statistics['fill_landscape_count']) if design.params.fill_landscape else {}),
                **(dict(align='ew' if design.params.layout == 'ew' else design.params.align)
                   if design.params.align or design.params.layout == 'ew' else {}),
                **(dict(mount="flush", tilt_deg=design.params.tilt_deg, azimuth_deg=design.params.azimuth_deg)
                   if design.statistics.get("mount") == "flush" and project.roof.type != 'pitched' else {}),
                **(dict(mount='plane_flush', planes=[dict(id=p.id, tilt=p.slope_deg, azimuth=p.slope_azimuth_deg,
                    material=p.material, modules=next(r['module_count'] for r in design.statistics['planes'] if r['id'] == p.id))
                    for p in project.roof.planes]) if project.roof.type == 'pitched' else {}),
                **{key: design.statistics.get(key, 0) for key in keys})


def _what_if(project_id, version, changes, offline):
    project, design = storage.load(project_id), storage.load_design(project_id, version)
    from .personal import phased, phase_cash
    from .economic_analysis import energy_key
    names = ('shading', 'electrical', 'structure', 'economics')
    folder = storage._path(project_id, f'analysis/v{version}')
    records = {name: json.loads((folder / (name + '.json')).read_text(encoding='utf-8'))
               for name in names if (folder / (name + '.json')).is_file()}
    cached = records.get('economics', {})
    design_sha = hashlib.sha256(storage._path(project_id, f'designs/v{version}.json').read_bytes()).hexdigest()
    valid = len(records) == len(names) and cached.get('analysis_metadata', {}).get('design_sha256') == design_sha
    shadow_proof = records.get('shading', {})
    valid = valid and shadow_proof.get('version') == version and shadow_proof.get('metadata', {}).get('design_sha256') == design_sha
    valid = valid and cached.get('tariff', {}).get('bands') and not phased(project)
    valid = valid and project.requirements.structured.export_allowed is not False
    valid = valid and cached.get('input_fingerprint') and cached.get('energy_fingerprint') == energy_key(project)
    if valid:
        shadows = records['shading']
        energy = dict(cached['analysis_metadata']['yield_kwh'], tariff_basis=cached['tariff'])
        omitted = cached.get('generation', {}).get('omitted', {})
    else:
        shadows = shading.analyze_design(project, design, offline=offline)
    electric = electrical.calculate(project, design, offline=offline, shadows=shadows)
    load = structure.calculate(project, design)
    if not valid:
        energy, generated = analysis.generation(project, design, shadows, electric['dc_kw'], offline=offline)
        omitted = generated['omitted']
    cash = economics.calculate(project, electric['dc_kw'], energy, design=design, electric=electric, load=load, sensitivity=False)
    if phased(project):
        phase_cash(project, design, shadows, cash, offline=offline)
    checked = rules.evaluate(project, design, shadows, electric, load, cash)
    baseline = analysis._summary(design, shadows, electric, load, cash, energy, checked, omitted=omitted)
    params = cash['params']
    changed = project.model_copy(deep=True)
    changed.economics.price_self_cny_kwh = params['price_self_cny_kwh']
    for source, target in (("capex_change_pct", "capex_cny_per_w"), ("price_change_pct", "price_self_cny_kwh")):
        if source in changes:
            setattr(changed.economics, target, params[target] * (1 + changes[source] / 100))
    for key in ("self_use_ratio", "price_export_cny_kwh"):
        if key in changes:
            setattr(changed.economics, key, changes[key])
    updated = economics.calculate(changed, electric["dc_kw"], energy,
                                  design=design, electric=electric, load=load, sensitivity=False)
    if phased(changed):
        scale = 1 + changes['capex_change_pct'] / 100 if 'capex_change_pct' in changes else None
        scale = scale if project.economics.capex_cny_per_w is None else None
        phase_cash(changed, design, shadows, updated, offline=offline, cost_scale=scale)
    recalculated = rules.evaluate(changed, design, shadows, electric, load, updated)
    metrics = ("payback_years", "irr_pct", "lcoe_cny_kwh")
    values = {key: None if updated[key] is None else round(updated[key], 6) for key in metrics}
    delta = {key: None if updated[key] is None or cash[key] is None else round(updated[key] - cash[key], 6) for key in metrics}
    related = [{key: row[key] for key in ("id", "status", "value", "limit")} for row in recalculated["items"] if row["id"] in ("U03", "U04", "U07")]
    hard_failed = sum(row['level'] == 'hard' and row['status'] == 'fail' for row in recalculated['items'])
    result = dict(baseline, what_if=dict(saved=False, note="此结果未保存", **values, delta=delta, rules=related,
                                       hard_failed=hard_failed))
    return analysis.fit_summary(result)


def _analyze(project_id, version, what_if=None, offline=False):
    return (_what_if(project_id, version, what_if, offline) if what_if is not None
            else analysis.analyze(project_id, version, offline=offline))


def _edit_design(project_id, version, reason, ops, offline=False):
    before = storage.load_design(project_id, version).statistics.get('dc_kw')
    result = storage.edit_design(project_id, version, ops, reason, "agent", offline=offline)
    after = storage.load_design(project_id, result['version'])
    return dict(ok=True, **result, parent_version=after.parent_version, reason=after.reason,
                dc_kw_change=dict(before=before, after=after.statistics.get('dc_kw')))


def _cache_shadows(project_id, design, result):
    result["version"] = design.version
    result["metadata"]["design_sha256"] = hashlib.sha256(storage._path(project_id, f"designs/v{design.version}.json").read_bytes()).hexdigest()
    rules.save_result(project_id, design.version, "shading", result)


def recommend_options(current, options):
    eligible = [row for row in [current, *options] if row["hard_pass"] is True and not row["violated_requirements"]]
    if not eligible:
        return {key: dict(version=current["version"], why="三套都不满足要求，沿用当前方案")
                for key in ("max_capacity", "fast_payback", "balanced")}
    payback = lambda row: row["payback_years"] if row["payback_years"] is not None else float("inf")
    tie = lambda row: (row["version"] != current["version"], row["version"])
    capacity = min(eligible, key=lambda row: (-row["dc_kw"], payback(row), *tie(row)))
    fastest = min(eligible, key=lambda row: (payback(row), -row["dc_kw"], *tie(row)))
    window = [row for row in eligible if payback(row) <= payback(fastest) * 1.05]
    balanced = min(window, key=lambda row: (-row["annual_kwh"], *tie(row)))
    reasons = ("装机最多，同装机选回本短的", "回本最短，同回本选装机大的", "回本慢不超过5%，年发电最多")
    chosen = zip(("max_capacity", "fast_payback", "balanced"), (capacity, fastest, balanced), reasons)
    return {key: dict(version=row["version"], why=("回本未算出，" + ("年发电最多" if key == "balanced" else "装机最多")
                 if row["payback_years"] is None else reason))
            for key, row, reason in chosen}


def _comparison_metric(label, design, summary, checked, tilt=None):
    violations = [row["id"] for row in checked["items"] if row["source_type"] == "用户要求" and row["status"] == "fail"]
    fallback = 'south' if design.params.azimuth_deg == 180 else 'custom'
    align = 'ew' if design.params.layout == 'ew' else design.params.align or fallback
    return dict(name=label, version=design.version, tilt_deg=design.params.tilt_deg if tilt is None else tilt, dc_kw=summary["dc_kw"],
                align=align, **(dict(azimuth_deg=design.params.azimuth_deg) if align == 'custom' else {}),
                fill_landscape_count=design.statistics.get('fill_landscape_count', 0),
                annual_kwh=summary["yield_kwh"]["p50"], capex_cny=summary["economics"]["capex_cny"],
                kwh_per_kw=round(summary["yield_kwh"]["p50"] / summary["dc_kw"], 4) if summary["dc_kw"] else 0,
                payback_years=summary["economics"]["payback_years"], irr_pct=summary["economics"]["irr_pct"],
                avg_loss_pct=summary["shading"]["avg_loss_pct"], hard_pass=checked["hard_failed"] == 0,
                violated_requirements=violations)


def _compare_options(project_id, base_version, offline=False):
    project, base = storage.load(project_id), storage.load_design(project_id, base_version)
    from .installation import effective
    project = effective(project, base)
    if project.roof.type == "metal":
        raise GzError("COMPARE_NOT_APPLICABLE", "彩钢瓦顺坡平铺，倾角就是坡度，三方案（比倾角）不适用", "用当前通过的版本")
    try:
        current = _comparison_metric("当前方案", base, _read(project_id, f"analysis/v{base_version}/summary.json"),
                                     _read(project_id, f"analysis/v{base_version}/rules.json"))
    except (OSError, ValueError, KeyError) as error:
        raise GzError("ANALYSIS_MISSING", "当前方案缺少完整分析结果", "先分析当前方案，再做三方案对比") from error
    if project.roof.type == 'pitched':
        from .pitched_compare import compare
        return compare(project_id, base, current, offline=offline)
    requirement = project.requirements.structured
    bounds = requirement.tilt_deg_range
    if project.roof.type == 'carport':
        bounds = (max(0, bounds[0]), min(15, bounds[1])) if bounds else (0, 15)
        if bounds[0] > bounds[1]:
            raise GzError('REQUIREMENTS_INVALID', '车棚倾角要求与0–15°范围无交集', '调整倾角要求')
    if requirement.max_height_m is not None and project.roof.type != 'carport':
        from .personal import tilt_bounds
        bounds = tilt_bounds(project, base.params.model_copy(update=dict(layout='rows')))
    constrained = any(value is not None for value in (bounds, requirement.walkway_m_min, requirement.capacity_kw_max, requirement.budget_cny_max))
    constrained = constrained or requirement.export_allowed is False or requirement.transformer_kva is not None
    active = project.model_copy(deep=True)
    active.roof.keepouts += base.added_keepouts
    configurations, plans = [], {}
    with stage("compare.site"):
        nasa, _ = weather.load_nasa_hourly(project.site.lat, project.site.lon, 2023, offline=offline)
        site = shading.SiteShading(project, offline=offline)
        bearings = dict(south=180, edge=layout.edge_azimuth(project.roof.outline))
        if project.roof.type == 'carport':
            bearings = dict(south=project.roof.planes[0].slope_azimuth_deg if project.roof.planes else 180)
        if bearings.get('edge') == 180:
            del bearings['edge']
        for align, bearing in bearings.items():
            plan = choose_tilts(irradiation_by_tilt(nasa, project.site.lat, project.site.lon, bearing, project.site.albedo), bounds)
            if project.roof.type == 'carport':
                plan['capacity'] = bounds[0]
            plans[align] = plan
            configurations += [(label, dict(align=align, tilt_deg=tilt, layout='rows', fill_landscape=True,
                                             winter_window_hours=[10, 14] if label == '多装' else [9, 15]))
                               for label, tilts in [('多装', [plan['capacity']]), ('最快回本', plan['trials']), ('折中', [plan['balanced']])]
                               for tilt in tilts]
        low, high = bounds or (5, 15)
        if requirement.max_height_m is not None and project.roof.type != 'carport':
            try:
                low, high = tilt_bounds(project, base.params.model_copy(update=dict(layout='ew')))
            except GzError:
                low, high = 1, 0
        if project.roof.type != 'carport' and max(5, low) <= min(15, high):
            configurations.append(('多装', dict(layout='ew', tilt_deg=min(max(10, low), high), fill_landscape=True,
                                               winter_window_hours=[10, 14], walkway_every_n_rows=base.params.walkway_every_n_rows or 4)))
    def initial(configuration):
        _, parameters = configuration
        with stage('compare.initial.layout'):
            design = inherit_keepouts(layout.generate_layout(active, base.params.model_dump() | parameters), base)
            original, corrections = design, []
            for _ in range(2):
                from .orientation import views
                geometry = next((check for _, view in views(design) if (check := rules.walkway_check(project, view))['status'] == 'fail'), {})
                if geometry.get("status") != "fail":
                    break
                operation = geometry["suggestion"]
                if operation is None:
                    break
                corrections.append(operation)
                design = inherit_keepouts(layout.generate_layout(active,
                    design.params.model_dump() | {operation["name"]: operation["value"]}), base)
            reuse = shading.RemovalShading(project, design, site=site)
        with stage('compare.initial.shading'):
            shadows = reuse.analyze(design)
        return original, shadows, reuse, corrections
    # Each candidate owns geometry/ray caches; version writes remain in stable order.
    with ThreadPoolExecutor(max_workers=3) as executor:
        initial_results = list(executor.map(initial, configurations))
    candidates = []
    for (label, parameters), (original, shadows, reuse, corrections) in zip(configurations, initial_results):
        phase = label
        design = original.model_copy(deep=True)
        design.version, design.parent_version = storage.next_version(project_id), base_version
        design.reason, design.author = "三方案对比：" + label, "agent"
        design.added_keepouts = base.added_keepouts
        design.modules_per_string = base.modules_per_string
        storage.save_design(project_id, design, offline=offline, shadows=shadows if not corrections else None)
        for operation in corrections:
            design = storage.load_design(project_id, storage.edit_design(project_id, design.version,
                       [operation], label + "：按 G03 重新排板", "agent", offline=offline)["version"])
        _cache_shadows(project_id, design, shadows)
        def repair(design, identifier):
            if not storage._path(project_id, f"analysis/v{design.version}/shading.json").exists():
                with stage(f"compare.{phase}.shading-before-{identifier}"):
                    _cache_shadows(project_id, design, reuse.analyze(design))
            with stage(f"compare.{phase}.rule-{identifier}"):
                checked = rules.check(project_id, design.version, offline=offline)
            if identifier == 'U05':
                analysis.analyze(project_id, design.version, offline=offline)
                checked = _read(project_id, f'analysis/v{design.version}/rules.json')
            if identifier in ("U02", "U03"):
                electric = _read(project_id, f"analysis/v{design.version}/electrical.json")
                params, _ = economics.resolve_parameters(project)
                from .costs import itemized
                capex = itemized(project, electric['dc_kw'], design, electric)['capex_cny']
                cash = dict(capex_cny=capex, params=params, payback_years=None)
                checked = rules.evaluate(project, design, _read(project_id, f"analysis/v{design.version}/shading.json"),
                                         electric, _read(project_id, f"analysis/v{design.version}/structure.json"), cash)
            row = next((item for item in checked['items'] if item['id'] == identifier), dict(status='na'))
            if row["status"] == "fail" and row["suggestion"] is not None:
                operation = row["suggestion"]
                count = operation.get("where", {}).get("worst_count", len(operation.get("module_ids", [])))
                reason = f"{label}：按 {identifier} 删除 {count} 块" if identifier in ("U02", "U03") else label + "：自动修正 " + identifier
                design = storage.load_design(project_id, storage.edit_design(project_id, design.version,
                           [operation], reason, "agent", offline=offline)["version"])
            return design
        dynamic = requirement.transformer_kva is not None or requirement.export_allowed is False
        rounds = max(4, len(design.modules)) if dynamic else 4
        for round_index in range(rounds if constrained else 1):
            previous = design.version
            previous_count = len(design.modules)
            for identifier in ("U02", "U03", "U05", "U06") if constrained else ():
                design = repair(design, identifier)
            if label == "最快回本" and round_index == 0:
                if not storage._path(project_id, f"analysis/v{design.version}/shading.json").exists():
                    _cache_shadows(project_id, design, reuse.analyze(design))
                design = storage.load_design(project_id, storage.edit_design(project_id, design.version,
                           [dict(op="remove_modules", where=dict(shading_loss_gt=3))], "最快回本：移除遮挡大于3%的组件", "agent", offline=offline)["version"])
            for identifier in ("S01", "E08"):
                design = repair(design, identifier)
            if design.version == previous or dynamic and len(design.modules) >= previous_count:
                break
        if not storage._path(project_id, f"analysis/v{design.version}/shading.json").exists():
            with stage(f"compare.{phase}.final-shading"):
                _cache_shadows(project_id, design, reuse.analyze(design))
        with stage(f"compare.{phase}.analysis"):
            summary = analysis.analyze(project_id, design.version, offline=offline)
        checked = _read(project_id, f"analysis/v{design.version}/rules.json")
        candidates.append(_comparison_metric(label, design, summary, checked))
    options = []
    for label in ('多装', '最快回本', '折中'):
        choices = [row for row in candidates if row['name'] == label]
        eligible = [row for row in choices if row['hard_pass'] and not row['violated_requirements']]
        choices = eligible or choices
        if label == '折中':
            fastest = min((row['payback_years'] for row in choices if row['payback_years'] is not None), default=float('inf'))
            choices = [row for row in choices if (row['payback_years'] or float('inf')) <= fastest * 1.05]
        metric = {'多装': 'dc_kw', '最快回本': 'kwh_per_kw', '折中': 'annual_kwh'}[label]
        options.append(max(choices, key=lambda row: row[metric]))
    plan = plans[options[1]['align']]
    result = dict(ok=True, base_version=base_version, options=options, current=current, recommended=recommend_options(current, options),
                capacity_note=layout.CAPACITY_NOTE,
                tilt_trials=[{key: row[key] for key in ('tilt_deg', 'kwh_per_kw')} for row in candidates
                             if row['name'] == '最快回本' and row['align'] == options[1]['align']],
                site_tilt=dict(best=plan["best"], capacity=plan['capacity'], balanced=plan['balanced'], loss_pct=plan["loss_pct"]))
    if options[0]['align'] == 'ew' and result['recommended']['max_capacity']['version'] == options[0]['version']:
        result['recommended']['max_capacity']['why'] += '；东西向候选装机最多'
    if len(analysis.serialized(result).encode("utf-8")) > 1920:
        raise GzError("RESULT_TOO_LARGE", "三方案完整结果超过2KB", "保留完整分析结果并核对未满足的要求")
    rules.save_result(project_id, base_version, "compare", result)
    return result


def _crosscheck_yield(project_id, version, offline=False, group_offset=0):
    project, design = storage.load(project_id), storage.load_design(project_id, version)
    from . import orientation
    if type(group_offset) is not int or not 0 <= group_offset < len(orientation.groups(design)):
        raise GzError('GROUP_OFFSET_INVALID', '朝向组起点超出范围', '从0开始，按next_group_offset续取')
    if len(orientation.groups(design)) > 1:
        rows, totals = [], {}
        power = electrical.equipment_catalog()['modules'][project.equipment.module_id]['pmax_w'] / 1000
        for identity, view, generated in orientation.simulations(project, design, offline=offline):
            values = {name: round(row['specific_yield_kwh_kwp'], 4) for name, row in generated['results'].items()}
            capacity = len(view.modules) * power
            rows.append(dict(group=identity, kw=round(capacity, 4), per_kw=values, omitted=list(generated['omitted'])))
            for name, row in generated['results'].items():
                totals[name] = totals.get(name, 0) + capacity * row['specific_yield_kwh_kwp']
        complete = set.intersection(*(set(row['per_kw']) for row in rows))
        result = dict(ok=True, version=version, groups=rows,
                      total_kwh={name: round(value, 4) for name, value in totals.items() if name in complete},
                      note='分组及合计均为未扣遮挡的五链复核；缺链不计入合计。')
        result.update(specific_yield_kwh_kwp={name: round(totals[name] / (len(design.modules) * power), 4) for name in sorted(complete)},
                      differences=[], omitted={name: '部分朝向缺链' for row in rows for name in row['omitted']})
        rules.save_result(project_id, version, 'crosscheck', result)
        page = dict(result, groups=[], group_offset=group_offset, total_groups=len(rows))
        for index in range(group_offset, len(rows)):
            page['groups'].append(rows[index])
            page['next_group_offset'] = index + 1 if index + 1 < len(rows) else None
            if len(analysis.serialized(page).encode('utf-8')) > 1920:
                page['groups'].pop()
                page['next_group_offset'] = index
                break
        return page
    design = next(orientation.views(design))[1]
    loss = economics.load_assumptions()["design_system_loss_pct"]["value"]
    generated = yieldsim.simulate_design_yields(project.site.lat, project.site.lon, tilt=design.params.tilt_deg,
                                              azimuth=design.params.azimuth_deg, loss_percent=loss, offline=offline,
                                              module_id=project.equipment.module_id)
    values = {key: round(row["specific_yield_kwh_kwp"], 4) for key, row in generated["results"].items()}
    differences = [dict(left=a, right=b, difference_kwh_kwp=round(values[a] - values[b], 4)) for a, b in itertools.combinations(values, 2)]
    result = dict(ok=True, version=version, specific_yield_kwh_kwp=values, differences=differences,
                omitted=generated["omitted"], note="a/b/c使用同一NASA天气；b与b_tmy比较天气差异，b_tmy与d也有模型及天气产品差异。")
    rules.save_result(project_id, version, "crosscheck", result)
    return result


def _record_review(project_id, version, reviewer_model, verdict, findings):
    storage.load_design(project_id, version)
    if not reviewer_model.strip() or verdict not in ("approve", "revise") or any(
            set(row) != {"severity", "item", "evidence", "suggestion"} or row["severity"] not in ("high", "medium", "low")
            or any(not isinstance(row[key], str) for key in ("item", "evidence", "suggestion")) for row in findings):
        raise GzError("REVIEW_INVALID", "审核意见字段不正确", "填写审核模型、结论和完整的问题清单")
    timestamp = datetime.now(timezone.utc).isoformat()
    filename = f"v{version}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}-{uuid4().hex[:8]}.json"
    _write(storage._path(project_id, "reviews/" + filename), dict(version=version, reviewer_model=reviewer_model,
           verdict=verdict, findings=findings, created_at=timestamp), exclusive=True)
    return dict(ok=True, version=version, file=f"projects/{project_id}/reviews/{filename}")


def _export(project_id, version, offline=False):
    analysis.analyze(project_id, version, offline=offline)
    checked = _read(project_id, f"analysis/v{version}/rules.json")
    failed = [row["id"] for row in checked["items"] if row["status"] == "fail" and row["level"] == "hard"]
    if failed:
        raise GzError("EXPORT_BLOCKED", "硬性规则未通过，不能导出：" + "、".join(failed), "按建议修改并重新分析，全部硬性规则通过后再导出")
    directory = storage._path(project_id, f"exports/v{version}")
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = storage._path(project_id, f"exports/v{version}/manifest.json")
    if manifest_path.exists():
        manifest = _read(project_id, f"exports/v{version}/manifest.json")
        files = manifest.get("files", {})
        legacy = {"design.json", "summary.json", "rules.json", "economics.json"}
        expected = (legacy, legacy | {f"layout-v{version}.dxf", f"bom-v{version}.xlsx"})
        if manifest.get("version") != version or not isinstance(files, dict) or set(files) not in expected or any(
                not (directory / name).is_file() or hashlib.sha256(storage._path(project_id,
                f"exports/v{version}/{name}").read_bytes()).hexdigest() != digest for name, digest in files.items()):
            raise GzError("EXPORT_INVALID", "原导出包缺失或哈希不符，不能覆盖", "保留原证据，创建新的方案版本再导出")
    else:
        from .report.deliverables import write_deliverables
        files = write_deliverables(project_id, version, directory)
        for name, source in (("design", f"designs/v{version}.json"), ("summary", f"analysis/v{version}/summary.json"),
                             ("rules", f"analysis/v{version}/rules.json"), ("economics", f"analysis/v{version}/economics.json")):
            contents = storage._path(project_id, source).read_bytes()
            storage._path(project_id, f"exports/v{version}/{name}.json").write_bytes(contents)
            files[name + ".json"] = hashlib.sha256(contents).hexdigest()
        _write(manifest_path, dict(version=version, files=files))
    return dict(ok=True, version=version, directory=f"projects/{project_id}/exports/v{version}", files=files,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest())


ACTIONS = {"gz_" + name: action for name, action in dict(project_summary=_project_summary,
           set_requirements=_set_requirements, fetch_weather=_fetch_weather, generate_layout=_generate_layout,
           analyze=_analyze, edit_design=_edit_design, compare_options=_compare_options,
           crosscheck_yield=_crosscheck_yield, record_review=_record_review, export=_export, new_project=_new_project).items()}


def dispatch(name, args):
    return ACTIONS[name](**args)
