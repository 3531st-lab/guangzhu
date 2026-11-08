"""T22: buildings designed one at a time, read back from their verified exports and put side by side; nothing is recalculated."""
import hashlib
import json
import math
from html import escape

from . import sitecheck


def _exported(capture, meta, relative):
    path = capture / relative
    if (not path.resolve().is_relative_to(capture.resolve()) or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != meta.get("artifacts", {}).get(relative)):
        raise ValueError("导出文件与执行记录的哈希不一致：" + relative)
    return json.loads(path.read_text(encoding="utf-8"))


def building(row, capture, meta):
    version, project = row["version"], _exported(capture, meta, "project/project.json")
    summary, cash, design = (_exported(capture, meta, f"project/exports/v{version}/{name}.json") for name in ("summary", "economics", "design"))
    ratio = summary["electrical"]["dc_ac_ratio"]
    return dict(run_id=row["run_id"], project_id=project["id"], name=project["name"], version=version, showcase=row["showcase"],
                **(dict(building=project['roof']['building']) if project['roof'].get('building') else {}),
                ended_at=meta.get("ended_at"), modules=summary["modules"], dc_kw=summary["dc_kw"], ac_kw=summary["dc_kw"] / ratio if ratio else None,
                annual_kwh=summary["yield_kwh"]["p50"], capex_cny=cash["capex_cny"], payback_years=cash["payback_years"], irr_pct=cash["irr_pct"],
                **(dict(posttax_net_cny=[r['net_cny'] for r in cash['posttax']['cashflows']]) if 'posttax' in cash else {}),
                **(dict(equity_net_cny=[r['net_cny'] for r in cash['loan']['posttax']['cashflows']]) if 'loan' in cash else {}),
                co2_t=cash["co2_t_per_year"], net_cny=[year["net_cny"] for year in cash["cashflows"]],
                flags=sitecheck.flags(meta.get("facts"), project["roof"]["type"], project['roof'])["risk"], outline=project["roof"]["outline"],
                panels=[[[round(x, 2), round(y, 2)] for x, y, _ in module["corners"]] for module in design["modules"]],
                panels_3d=[[[round(x, 2), round(y, 2), round(z, 2)] for x, y, z in module["corners"]] for module in design["modules"]])


def overview(entries):
    """Every verified design is listed; the newest run of each roof name is ticked, the shipped real case is not."""
    buildings, skipped = [], []
    for row, capture, meta in entries:
        try:
            buildings.append(building(row, capture, meta))
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            skipped.append(row["run_id"])
    newest = {item["name"]: item["run_id"] for item in sorted(buildings, key=lambda item: item["ended_at"] or "") if not item["showcase"]}
    for item in buildings:
        item["default"] = newest.get(item["name"]) == item["run_id"]
    return dict(buildings=sorted(buildings, key=lambda item: (not item["default"], item["name"], item["ended_at"] or "")), skipped=skipped)


def total(rows):
    values = {key: sum(row[key] for row in rows) for key in ('dc_kw', 'annual_kwh', 'capex_cny', 'co2_t')}
    flow = [sum(row['net_cny'][year] if year < len(row['net_cny']) else 0 for row in rows)
            for year in range(max((len(row['net_cny']) for row in rows), default=0))]
    cumulative, payback = 0, None
    for year, net in enumerate(flow):
        before = cumulative
        cumulative += net
        if payback is None and year > 0 and before < 0 <= cumulative:
            payback = year - 1 - before / net
    extra = {}
    from .finance import metrics
    for key in ('posttax', 'equity'):
        field = key + '_net_cny'
        if rows and all(field in row for row in rows):
            annual = [math.fsum(row[field][y] if y < len(row[field]) else 0 for row in rows)
                      for y in range(max(len(row[field]) for row in rows))]
            extra[key] = metrics(annual)
        elif any(field in row for row in rows):
            extra[key + '_note'] = '部分旧记录或未贷款项目缺相应年度账，无法计算该合计；未以税前代替。'
    return dict(count=len(rows), payback_years=payback, net_cny=flow, **values, **extra)


def actual_ac(electric):
    units = electric.get('per_inverter', [])
    if not units or electric.get('inverter_count') != len(units) or len({u.get('inverter') for u in units}) != len(units):
        raise ValueError('逆变器清单缺失或数量不一致')
    numbers = []
    for unit in units:
        dc, ratio = unit.get('dc_kw'), unit.get('dc_ac_ratio')
        if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in (dc, ratio)):
            raise ValueError('每台直流容量或未舍入容配比缺失、为零或非法')
        value = dc / ratio
        if not math.isfinite(value) or value <= 0:
            raise ValueError('额定 AC 无法还原')
        if 'rated_ac_kw' in unit and not math.isclose(unit['rated_ac_kw'], value, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError('每台额定 AC 与还原值矛盾')
        numbers.append(value)
    return dict(rated_ac_kw=math.fsum(numbers), inverter_count=len(units))


def named(park, entries, root, *, require_export=False):
    from .park_store import transaction
    with transaction(root):
        return _named(park, entries, root, require_export=require_export)


def _local_building(project_dir, run_id, shading_note, *, require_export=False):
    from .design_evidence import capture
    from .local_exports import export_evidence
    project = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    selection = project_dir / 'local-selection.json'
    if selection.is_file():
        version = json.loads(selection.read_text(encoding='utf-8'))['version']
    else:
        trace = json.loads((project_dir / 'agent_trace.json').read_text(encoding='utf-8'))
        version = trace['final_version']
    if type(version) is not int or version < 1:
        raise ValueError('园区本地方案没有明确选中版本')
    proof = capture(project_dir, version)
    if (proof['analysis']['status'] != 'recorded' or proof['analysis']['input_binding'] != 'matched'
            or proof['analysis']['completion_status'] != 'matched' or proof['rules']['status'] != 'pass'):
        raise ValueError('园区本地方案计算未完成、输入已变化或硬规则未通过')
    exported = export_evidence(project_dir, version)
    approved = exported.get('status') == 'verified'
    if require_export and not approved:
        raise ValueError('园区正式报告仅汇总已批准且文件核验一致的导出')
    summary = json.loads((project_dir / f"analysis/v{version}/summary.json").read_text(encoding="utf-8"))
    cash = json.loads((project_dir / f"analysis/v{version}/economics.json").read_text(encoding="utf-8"))
    design = json.loads((project_dir / f"designs/v{version}.json").read_text(encoding="utf-8"))
    electric = json.loads((project_dir / f"analysis/v{version}/electrical.json").read_text(encoding="utf-8"))
    ratio = summary["electrical"]["dc_ac_ratio"]
    res = dict(
        run_id=run_id, project_id=project["id"], name=project["name"], version=version, showcase=False,
        **(dict(building=project['roof']['building']) if project['roof'].get('building') else {}),
        ended_at=design.get("created_at"),
        modules=summary["modules"], dc_kw=summary["dc_kw"], ac_kw=summary["dc_kw"] / ratio if ratio else None,
        annual_kwh=summary["yield_kwh"]["p50"], capex_cny=cash["capex_cny"], payback_years=cash["payback_years"], irr_pct=cash["irr_pct"],
        **(dict(posttax_net_cny=[r['net_cny'] for r in cash['posttax']['cashflows']]) if 'posttax' in cash else {}),
        **(dict(equity_net_cny=[r['net_cny'] for r in cash['loan']['posttax']['cashflows']]) if 'loan' in cash else {}),
        co2_t=cash["co2_t_per_year"], net_cny=[year["net_cny"] for year in cash["cashflows"]],
        flags=sitecheck.flags(None, project["roof"]["type"], project['roof'])["risk"], outline=project["roof"]["outline"],
        panels=[[[round(x, 2), round(y, 2)] for x, y, _ in module["corners"]] for module in design["modules"]],
        panels_3d=[[[round(x, 2), round(y, 2), round(z, 2)] for x, y, z in module["corners"]] for module in design["modules"]],
        shading_note=shading_note,
        status_label='已批准导出·未核实独立审核' if approved else '规则计算候选·待批准导出',
        locally_approved=approved,
    )
    try:
        res.update(actual_ac(electric))
        res['ac_missing'] = None
    except (OSError, ValueError, KeyError, TypeError):
        res.update(rated_ac_kw=None, inverter_count=None, ac_missing='每台设备证据不足，无法核定')
    return res


def _named(park, entries, root, *, require_export=False):
    from . import park_store as store
    sources = {b.template: store.Project.model_validate(store.read(store.resolve(b.template, root=root))).model_dump(mode='json')
               for b in park.buildings}
    latest, skipped = {}, []
    for row, capture, meta in sorted(entries, key=lambda item: item[2].get('ended_at') or ''):
        try:
            project = _exported(capture, meta, 'project/project.json')
            association = project.get('park')
            matches = [association['template']] if association and association['id'] == park.id else []
            if not association and park.id == 'legacy':
                project = store.Project.model_validate(project).model_dump(mode='json')
                matches = [key for key, source in sources.items()
                           if source['roof'] == project['roof'] and source['site'] == project['site']]
            if len(matches) != 1 or matches[0] not in sources or row['showcase']:
                continue
            result = building(row, capture, meta)
            current = store.read(store.folder(park.id, root) / 'roofs' / (park.id + '--' + matches[0]) / 'project.json')['park']
            result['shading_note'] = ('已考虑园区邻楼' if association['snapshot'] == current['snapshot'] else '使用旧园区位置，需重设计') \
                if association else '原模板设计，未自动考虑园区邻楼'
            try:
                result.update(actual_ac(_exported(capture, meta, f"project/analysis/v{row['version']}/electrical.json")))
                result['ac_missing'] = None
            except (OSError, ValueError, KeyError, TypeError):
                result.update(rated_ac_kw=None, inverter_count=None, ac_missing='每台设备证据不足，无法核定')
            latest[matches[0]] = result
        except (OSError, ValueError, KeyError, TypeError):
            skipped.append(row['run_id'])
    # Local batch retries receive new project IDs. Association and the current
    # frozen roof, not a hardcoded showcase name, establish park membership.
    local_candidates = {}
    for path in sorted((root / 'projects').glob('*/project.json')):
        try:
            if path.parent.is_symlink() or not path.resolve().is_relative_to((root / 'projects').resolve()):
                continue
            source = store.Project.model_validate(store.read(path)).model_dump(mode='json')
            association = source.get('park') or {}
            template = association.get('template')
            if association.get('id') != park.id or template not in sources:
                continue
            current = store.read(store.folder(park.id, root) / 'roofs' / (park.id + '--' + template) / 'project.json')
            current = store.Project.model_validate(current).model_dump(mode='json')
            if any(source[field] != current[field] for field in ('park', 'roof', 'site')):
                skipped.append(source['id'] + ': 园区位置或屋顶输入已变化，需重新计算')
                continue
            result = _local_building(path.parent, 'auto-' + source['id'],
                '采用当前园区位置及邻楼保守棱柱模型', require_export=require_export)
            previous = local_candidates.get(template) or latest.get(template)
            if previous is None or (result['ended_at'] or '') > (previous['ended_at'] or ''):
                local_candidates[template] = result
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            continue
    latest.update(local_candidates)
    ordered = sorted(latest.values(), key=lambda row: (row['name'], row['ended_at'] or ''))
    rows = sorted(ordered, key=lambda row: row['payback_years'] if row['payback_years'] is not None else 1e9)
    cost, power, first = 0, 0, []
    for row in rows:
        fits = ((park.budget_cny is None or cost + row['capex_cny'] <= park.budget_cny)
                and (park.grid_kw is None or power + (row['ac_kw'] or 0) <= park.grid_kw))
        row['park_phase'] = 1 if fits else 2
        if fits:
            first.append(row)
            cost, power = cost + row['capex_cny'], power + (row['ac_kw'] or 0)
    known = bool(rows) and all(row['rated_ac_kw'] is not None for row in rows)
    ac = math.fsum(row['rated_ac_kw'] for row in rows) if known else None
    risks = [dict(label=label, limit=limit, excess=max(0, ac - limit) if ac is not None and limit is not None else None)
             for label, limit in [('变压器×0.8（示意）', park.transformer_kva * .8 if park.transformer_kva else None), ('并网容量', park.grid_kw)]]
    buildings = [dict(b.model_dump(), name=sources[b.template]['name'], roof=sources[b.template]['roof'], result=latest.get(b.template))
                 for b in park.buildings]
    return dict(buildings=buildings, all=total(rows), phase1=total(first), rated_ac_kw=ac, risks=risks, skipped=skipped,
                inverter_count=sum(row['inverter_count'] for row in rows) if known else None)


def map_svg(data):
    from .park_store import Building, transform
    shapes = [(b, transform(b['roof']['outline'], Building.model_validate({k: b[k] for k in Building.model_fields})))
              for b in data['buildings']]
    points = [point for _, outline in shapes for point in outline] or [[0, 0], [100, 100]]
    xs, ys = [p[0] for p in points], [-p[1] for p in points]
    span_x = max(max(xs) - min(xs), 20)
    span_y = max(max(ys) - min(ys), 20)
    span = max(span_x, span_y, 30)
    font = max(min(span / 46, 5.2), 2.2)
    pad_x = max(span * 0.16, 24)
    pad_y_top = max(span * 0.18, 26)
    pad_y_bot = max(span * 0.12, 18)
    vx0 = min(xs) - pad_x
    vy0 = min(ys) - pad_y_top
    vw = span_x + pad_x * 2
    vh = span_y + pad_y_top + pad_y_bot
    view = f'{vx0:.1f} {vy0:.1f} {vw:.1f} {vh:.1f}'
    chunks = [
        f'<svg id="park-map" viewBox="{view}" role="img" aria-label="园区总图，北向上">',
        f'<rect x="{vx0:.1f}" y="{vy0:.1f}" width="{vw:.1f}" height="{vh:.1f}" rx="{font * 1.2:.1f}" fill="#f6f4ef" stroke="#d8d0c5" stroke-width="0.6" pointer-events="none"/>',
    ]
    step = 50 if span > 180 else 25 if span > 80 else 10
    gx = int(vx0 // step) * step
    while gx <= vx0 + vw:
        if vx0 < gx < vx0 + vw:
            chunks.append(f'<line x1="{gx}" y1="{vy0:.1f}" x2="{gx}" y2="{vy0 + vh:.1f}" stroke="#e7e1d6" stroke-width="0.35" pointer-events="none"/>')
        gx += step
    gy = int(vy0 // step) * step
    while gy <= vy0 + vh:
        if vy0 < gy < vy0 + vh:
            chunks.append(f'<line x1="{vx0:.1f}" y1="{gy}" x2="{vx0 + vw:.1f}" y2="{gy}" stroke="#e7e1d6" stroke-width="0.35" pointer-events="none"/>')
        gy += step
    # Header legend & compass badge (using rect/text only, pointer-events="none")
    leg_y = vy0 + font * 1.8
    chunks.append(
        f'<g pointer-events="none" style="font-size:{font * 0.88:.2f}px;fill:#3b4a5a;font-weight:600">'
        f'<text x="{vx0 + font * 1.2:.1f}" y="{leg_y:.1f}">↑ N 北向 · 比例网格 {step}m</text>'
        f'<rect x="{vx0 + vw - font * 22:.1f}" y="{leg_y - font * 0.85:.1f}" width="{font * 0.95:.1f}" height="{font * 0.95:.1f}" rx="{font * 0.2:.1f}" fill="#247786"/>'
        f'<text x="{vx0 + vw - font * 20.6:.1f}" y="{leg_y:.1f}">一期阵列</text>'
        f'<rect x="{vx0 + vw - font * 14.2:.1f}" y="{leg_y - font * 0.85:.1f}" width="{font * 0.95:.1f}" height="{font * 0.95:.1f}" rx="{font * 0.2:.1f}" fill="#bc824a"/>'
        f'<text x="{vx0 + vw - font * 12.8:.1f}" y="{leg_y:.1f}">二期阵列</text>'
        f'<rect x="{vx0 + vw - font * 6.4:.1f}" y="{leg_y - font * 0.85:.1f}" width="{font * 0.95:.1f}" height="{font * 0.95:.1f}" rx="{font * 0.2:.1f}" fill="#ede7dd" stroke="#786f63" stroke-width="0.4"/>'
        f'<text x="{vx0 + vw - font * 5.0:.1f}" y="{leg_y:.1f}">屋面轮廓</text>'
        f'</g>'
    )
    path = lambda pts: ' '.join(f'{x},{-y}' for x, y in pts)
    for b, outline in shapes:
        building = Building.model_validate({k: b[k] for k in Building.model_fields})
        result = b['result'] or {}
        colour = '#247786' if result.get('park_phase') == 1 else '#bc824a'
        chunks.append(f'<g data-building="{escape(b["template"])}"><polygon points="{path(outline)}" '
                      'fill="#ede7dd" stroke="#5c5346" stroke-width="1.2" vector-effect="non-scaling-stroke"/>')
        for panel in result.get('panels', []):
            chunks.append(f'<polygon points="{path(transform(panel, building))}" fill="{colour}" fill-opacity="0.88"/>')
        raw_label = f"{b['name']} · {b['roof']['height_m']:g}m"
        if result.get('dc_kw'):
            raw_label += f" ({result['dc_kw']:.0f}kW)"
        label = escape(raw_label)
        b_xs = [p[0] for p in outline]
        b_ys = [-p[1] for p in outline]
        cx = (min(b_xs) + max(b_xs)) / 2
        top_y = min(b_ys)
        badge_h = font * 1.55
        badge_w = max(len(raw_label) * font * 0.78 + font * 1.4, font * 7.5)
        badge_y = top_y - badge_h - font * 0.35
        chunks.append(
            f'<rect x="{cx - badge_w / 2:.1f}" y="{badge_y:.1f}" width="{badge_w:.1f}" height="{badge_h:.1f}" '
            f'rx="{font * 0.35:.1f}" fill="#ffffff" fill-opacity="0.92" stroke="#94a3b8" stroke-width="0.4" pointer-events="none"/>'
            f'<text x="{cx:.1f}" y="{badge_y + badge_h * 0.72:.1f}" text-anchor="middle" pointer-events="none" '
            f'style="font-size:{font * 0.92:.2f}px;font-weight:600;fill:#1e293b">{label}</text></g>'
        )
    return ''.join(chunks) + '</svg>'
