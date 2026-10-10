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
                panels=[[[round(x, 2), round(y, 2)] for x, y, _ in module["corners"]] for module in design["modules"]])


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


def named(park, entries, root):
    from .park_store import transaction
    with transaction(root):
        return _named(park, entries, root)


def _named(park, entries, root):
    from . import park_store as store
    sources = {b.template: store.Project.model_validate(store.read(store.resolve(b.template, root=root))).model_dump(mode='json')
               for b in park.buildings}
    latest, skipped = {}, []
    for row, capture, meta in sorted(entries, key=lambda item: item[2].get('ended_at') or ''):
        try:
            project = _exported(capture, meta, 'project/project.json')
            association = project.get('park')
            matches = [association['template']] if association and association['id'] == park.id else []
            if not association:
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
    font = max(max(xs) - min(xs), max(ys) - min(ys), 10) / 35
    view = f'{min(xs)-15} {min(ys)-15} {max(xs)-min(xs)+30} {max(ys)-min(ys)+30}'
    chunks = [f'<svg id="park-map" viewBox="{view}" role="img" aria-label="园区总图，北向上">']
    path = lambda pts: ' '.join(f'{x},{-y}' for x, y in pts)
    for b, outline in shapes:
        building = Building.model_validate({k: b[k] for k in Building.model_fields})
        result = b['result'] or {}
        colour = '#247786' if result.get('park_phase') == 1 else '#bc824a'
        chunks.append(f'<g data-building="{escape(b["template"])}"><polygon points="{path(outline)}" '
                      'fill="#ede7dd" stroke="#786f63" vector-effect="non-scaling-stroke"/>')
        for panel in result.get('panels', []):
            chunks.append(f'<polygon points="{path(transform(panel, building))}" fill="{colour}"/>')
        label = escape(b['name']) + f" · {b['roof']['height_m']:g}m"
        chunks.append(f'<text x="{min(p[0] for p in outline)+font}" y="{-max(p[1] for p in outline)+font*2}" '
                      f'style="font-size:{font}px">{label}</text></g>')
    return ''.join(chunks) + '</svg>'
