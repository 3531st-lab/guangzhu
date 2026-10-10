"""Manufacturer-based DC string sizing; the T03 CEC yield model is separate."""

import csv
import math
from . import orientation, cables
from collections import Counter, defaultdict

from .config import DATA_DIR, DC_AC_MIN, DC_AC_MAX, DC_AC_TARGET
from .models import Design, GzError, validate_project, validated
from .weather import load_nasa_daily_extremes

CATALOG_DIR = DATA_DIR / "catalog"
STANDARD_REF = "GB 50797-2012（2024年局部修订）6.4.2"


def load_catalog(filename):
    """Read plain installation CSV rows keyed by their unique equipment ID."""
    try:
        with (CATALOG_DIR / filename).open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        key = {"modules.csv": "module_id", "inverters.csv": "inverter_id", "racking.csv": "racking_id"}[filename]
        result = {}
        for row in rows:
            identifier = row.get(key) or row.get("racking")
            if not identifier or identifier in result or None in row:
                raise ValueError("invalid or duplicate equipment ID")
            for name, value in row.items():
                try:
                    row[name] = float(value)
                except (TypeError, ValueError):
                    pass
            result[identifier] = row
        if not result:
            raise ValueError("empty catalog")
        return result
    except (OSError, csv.Error, ValueError, KeyError) as error:
        raise GzError("EQUIPMENT_CATALOG_INVALID", "设备规格目录缺失或格式不正确", "检查厂家规格CSV及唯一设备编号") from error


def equipment_catalog():
    return {kind: load_catalog(kind + ".csv") for kind in ("modules", "inverters", "racking")}


def labels(result):
    lengths = defaultdict(int)
    for string in result.get('strings', []):
        lengths[len(string['module_ids'])] += 1
    strings = '、'.join(f'{size} 块 × {count} 串' for size, count in sorted(lengths.items(), reverse=True))
    devices = result.get('inverters') or [dict(model=result['inverter_model'], count=result['inverter_count'])]
    return strings, ' + '.join(f"{row['model']} × {row['count']}" for row in devices)


def _number(row, key, *, positive=True):
    value = row.get(key)
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise GzError("EQUIPMENT_PARAMETER_MISSING", f"设备规格缺少有效参数：{key}", "核对官方规格书；未给出的参数不能用于此项计算")
    return float(value)


def _source(row):
    return f"{row.get('datasheet_url', '')}；{row.get('datasheet_version', '')}；第{row.get('datasheet_page', '')}页"


def _temperatures(site, module, offline):
    low, high = site.design_temp_min_c, site.design_temp_max_c
    nasa = None if low is not None and high is not None else load_nasa_daily_extremes(
        site.lat, site.lon, start_year=1996, end_year=2025, offline=offline)
    low = low if low is not None else nasa["temp_min_c"]
    high = high if high is not None else nasa["temp_max_c"]
    if low > high:
        raise GzError("DESIGN_TEMPERATURE_INVALID", "覆盖值与NASA合并后的设计最低气温高于最高气温", "检查设计温度覆盖值，或同时填写有依据的最低和最高气温")
    noct = _number(module, "noct_c")
    hot = high + (noct - 20) / 800 * 1000
    return dict(temp_min_c=low, temp_max_c=high, cell_hot_c=hot, noct_c=noct,
                min_source="用户覆盖" if site.design_temp_min_c is not None else "NASA POWER 1996–2025",
                max_source="用户覆盖" if site.design_temp_max_c is not None else "NASA POWER 1996–2025",
                nasa=nasa, evidence=f"t′={high:g}+({noct:g}−20)/800×1000={hot:.6f} °C；偏保守简式")


BAND_M = 40  # illustrative wiring section along the rows; strings and inverter blocks stay inside one section


def _along(module):
    angle = math.radians(module.azimuth)
    return module.center[0] * -math.cos(angle) + module.center[1] * math.sin(angle)


def _serpentine(modules):
    # Rows are walked section by section, so a string never stretches along a whole long (or thinned-out) row.
    # Inside a section the rows alternate direction; each next section starts at its corner nearest to where
    # the previous one ended. A roof no longer than one section keeps the plain row-by-row order.
    base = min((_along(m) for m in modules), default=0)
    sections = defaultdict(lambda: defaultdict(list))
    for module in modules:
        sections[math.floor((_along(module) - base) / BAND_M)][module.row, module.tier].append(module)
    ordered = []
    for band in sorted(sections):
        rows = sections[band]
        walks = [[module for index, key in enumerate(keys) for module in
                  sorted(rows[key], key=lambda m: (m.col, m.id), reverse=flip ^ bool(index % 2))]
                 for keys in (sorted(rows), sorted(rows, reverse=True)) for flip in (False, True)]
        start = ordered[-1].center[:2] if ordered else None
        ordered += min(walks, key=lambda walk: math.dist(start, walk[0].center[:2]) if start else 0)
    return [module.id for module in ordered]


def _lengths(design, identifiers, minimum, maximum):
    size = design.modules_per_string or max(1, maximum)
    count = math.ceil(len(identifiers) / size)
    short_count = count * size - len(identifiers)
    shortest = size - 1 if design.modules_per_string else len(identifiers) // max(1, count)
    if not design.modules_per_string and shortest >= minimum:
        size = math.ceil(len(identifiers) / count)
        short_count = count * size - len(identifiers)
    if shortest < minimum or short_count > count:
        count, remainder = divmod(len(identifiers), size)
        lengths = [size] * count
    else:
        remainder = 0
        lengths = [size] * (count - short_count) + [size - 1] * short_count
    shortest = min(lengths, default=size)
    return lengths, size, shortest


def _candidate(module, inverter, design, temperatures, identifiers, companion=None, losses=None, fixed_devices=None):
    models = [inverter] + ([companion] if companion else [])
    voc, vmp = _number(module, "voc_v"), _number(module, "vmp_v")
    beta, gamma = _number(module, "beta_voc_pct_c", positive=False) / 100, _number(module, "gamma_pmax_pct_c", positive=False) / 100
    low, hot = temperatures["temp_min_c"], temperatures["cell_hot_c"]
    cold_voc, cold_vmp, hot_vmp = voc * (1 + (low - 25) * beta), vmp * (1 + (low - 25) * gamma), vmp * (1 + (hot - 25) * gamma)
    if min(cold_voc, cold_vmp, hot_vmp) <= 0:
        raise GzError("ELECTRICAL_TEMPERATURE_INVALID", "设计温度与温度系数组合产生非正电压", "核对设计温度、NOCT和百分比温度系数")
    dc_limit = min(_number(row, "max_dc_voltage_v") for row in models)
    system_limit = _number(module, "max_system_voltage_v")
    mppt_min = max(_number(row, "mppt_min_v") for row in models)
    mppt_max = min(_number(row, "mppt_max_v") for row in models)
    minimum = math.ceil(mppt_min / hot_vmp)
    maximum = min(math.floor(min(dc_limit, system_limit) / cold_voc), math.floor(mppt_max / cold_vmp))
    lengths, tags, connected, unused, sizes, shortest_sizes = [], [], [], [], [], []
    partitions = []
    for identity, members in orientation.groups(design).items():
        classes = [[m for m in members if (losses[m.id] > 3) == shaded] for shaded in (False, True)] if losses else [members]
        if any(not _lengths(design, part, minimum, maximum)[0] for part in classes):
            classes = [members]
        partitions.extend((identity, part) for part in classes)
    for identity, modules in partitions:
        members = {m.id for m in modules}
        ordered = _serpentine(modules) if losses else [identifier for identifier in identifiers if identifier in members]
        sizes_here, size, shortest = _lengths(design, ordered, minimum, maximum)
        lengths.extend(sizes_here)
        tags.extend([identity] * len(sizes_here))
        connected.extend(ordered[:sum(sizes_here)])
        unused.extend(ordered[sum(sizes_here):])
        sizes.append(size)
        shortest_sizes.append(shortest)
    identifiers = connected + unused
    count, remainder = len(lengths), len(unused)
    size, shortest = max(sizes), min(shortest_sizes)
    isc, imp = _number(module, "isc_a"), _number(module, "imp_a")
    alpha = _number(module, "alpha_isc_pct_c", positive=False) / 100
    short = isc * (1 + alpha * (hot - 25))
    if short <= 0:
        raise GzError("ELECTRICAL_TEMPERATURE_INVALID", "温度校正后的短路电流非正", "核对短路电流温度系数和设计温度")
    dc_kw = len(identifiers) * _number(module, "pmax_w") / 1000
    ac_kw = _number(inverter, "rated_ac_kw")
    starts = [sum(lengths[:index]) for index in range(len(lengths))]
    panels = {m.id: m for m in design.modules}
    positions = [sum(_along(panels[mid]) for mid in identifiers[start:start + length]) / length for start, length in zip(starts, lengths)]
    # Walk the strings section by section along the rows, so that the inverters filled one after another each
    # serve one compact patch of the roof and the DC runs stay short.
    order = sorted(range(len(lengths)), key=lambda index: (math.floor((positions[index] - min(positions, default=0)) / BAND_M), index))
    def allocate(devices):
        groups, used, output = {}, defaultdict(int), {}
        capacities = [max(1, min(int(_number(row, "strings_per_mppt")),
                      math.floor(_number(row, "max_short_circuit_current_per_mppt_a") / short))) for row in devices]
        total = sum(_number(row, "rated_ac_kw") for row in devices)
        shares = {unit: sum(lengths) * _number(row, "rated_ac_kw") / total for unit, row in enumerate(devices, 1)}
        remaining = Counter(zip(tags, lengths))
        for index in order:
            length = lengths[index]
            choices = []
            token = (tags[index], length)
            remaining[token] -= 1
            reserved = sum(math.ceil(k / max(capacities)) for n, k in remaining.items() if n != token and k)
            empty = sum(int(_number(row, "mppt_count")) for row in devices) - len(groups)
            for unit, row in enumerate(devices, 1):
                capacity = _number(row, "rated_ac_kw")
                ports = int(_number(row, "strings_per_mppt"))
                allowed = max(1, min(ports, math.floor(_number(row, "max_short_circuit_current_per_mppt_a") / short)))
                for mppt in range(1, int(_number(row, "mppt_count")) + 1):
                    attached = groups.get((unit, mppt), [])
                    if len(attached) < allowed and (not attached or attached[0] == token):
                        overload = (used[unit] + length) * module["pmax_w"] / 1000 > DC_AC_MAX * capacity
                        reservation_failed = empty - (not attached) < reserved
                        choices.append((overload, reservation_failed, used[unit] + length / 2 > shares[unit], unit, len(attached), mppt))
            if not choices:
                return None
            _, _, _, unit, _, mppt = min(choices)
            groups.setdefault((unit, mppt), []).append(token)
            used[unit] += length
            output[index] = dict(id=f"S{index + 1:03}", module_ids=identifiers[starts[index]:starts[index] + length],
                                 module_count=length, inverter=unit, mppt=mppt)
        return [output[index] for index in sorted(output)]
    companion_ac = _number(companion, "rated_ac_kw") if companion else 0
    units = max(1, math.ceil((dc_kw / DC_AC_MAX - companion_ac) / ac_kw)) if count else 0
    while True:
        devices = fixed_devices if fixed_devices is not None else [inverter] * units + ([companion] if companion else [])
        strings = allocate(devices)
        safe = strings is not None and all(
            sum(len(s["module_ids"]) for s in strings if s["inverter"] == unit) * module["pmax_w"] / 1000
            <= DC_AC_MAX * _number(row, "rated_ac_kw") for unit, row in enumerate(devices, 1))
        if safe or units >= count or fixed_devices is not None:
            break
        units += 1
    strings = strings or []
    units = len(devices)
    ratio = dc_kw / sum(_number(row, "rated_ac_kw") for row in devices) if units else 0.0
    currents = []
    short_limit = min(_number(row, "max_short_circuit_current_per_mppt_a") for row in models)
    input_limit = min(_number(row, "max_input_current_per_mppt_a") for row in models)
    ports = int(_number(inverter, "strings_per_mppt"))
    allowed = min(ports, math.floor(short_limit / short))
    by_mppt = defaultdict(list)
    for string in strings:
        by_mppt[string["inverter"], string["mppt"]].append(string)
    per_inverter = []
    for unit, row in enumerate(devices, 1):
        mppts = int(_number(row, "mppt_count"))
        ports = int(_number(row, "strings_per_mppt"))
        short_limit = _number(row, "max_short_circuit_current_per_mppt_a")
        input_limit = _number(row, "max_input_current_per_mppt_a")
        allowed = min(ports, math.floor(short_limit / short))
        ac_kw = _number(row, "rated_ac_kw")
        assignments = []
        for mppt in range(1, mppts + 1):
            attached = by_mppt[unit, mppt]
            k = len(attached)
            assignments.append(dict(mppt=mppt, string_ids=[s["id"] for s in attached]))
            currents.append(dict(inverter=unit, mppt=mppt, string_ids=[s["id"] for s in attached], strings=k,
                                 working_a=k * imp, short_a=k * short, input_limit_a=input_limit, short_limit_a=short_limit, ports=ports,
                                 evidence=f"k={k}；Isc={k}×{isc:g}×[1+{alpha:g}×({hot:g}−25)]={k * short:.6f} A；Imp={k}×{imp:g}={k * imp:.6f} A"))
        attached_ids = [s["id"] for s in strings if s["inverter"] == unit]
        connected_modules = sum(len(s["module_ids"]) for s in strings if s["inverter"] == unit)
        unit_dc_kw = connected_modules * module["pmax_w"] / 1000
        unit_ratio = unit_dc_kw / ac_kw
        assignment_note = "；".join(f"MPPT{a['mppt']}={','.join(a['string_ids']) or '空'}" for a in assignments)
        per_inverter.append(dict(inverter=unit, inverter_id=row["inverter_id"], model=row["model"],
                                 string_ids=attached_ids, strings_count=len(attached_ids),
                                 module_count=connected_modules, dc_kw=unit_dc_kw, dc_ac_ratio=unit_ratio,
                                 mppt_assignments=assignments,
                                 evidence=f"第{unit}台：{connected_modules}块×{module['pmax_w']:g}/1000/{ac_kw:g}={unit_ratio:.6f}；"
                                          f"上限{DC_AC_MAX:g}；{assignment_note}"))
    checks = {}
    def check(code, value, limit, unit, passed, evidence, source):
        checks[code] = dict(value=value, limit=limit, unit=unit, status="pass" if passed else "fail", evidence=evidence, source_ref=source)
    cold_oc, hottest, cold_work = size * cold_voc, shortest * hot_vmp, size * cold_vmp
    voc_evidence = f"{size}×{voc:g}×[1+({low:g}−25)×({beta:g})]={cold_oc:.6f} V"
    work_note = "K′v以厂家功率温度系数近似"
    voltage_sources = '；'.join(_source(row) for row in models)
    check("E01", cold_oc, dc_limit, "V", cold_oc <= dc_limit, voc_evidence, STANDARD_REF + "；" + voltage_sources)
    check("E02", cold_oc, system_limit, "V", cold_oc <= system_limit, voc_evidence, _source(module))
    check("E03", hottest, mppt_min, "V", hottest >= mppt_min,
          f"{shortest}×{vmp:g}×[1+({hot:g}−25)×({gamma:g})]={hottest:.6f} V；{work_note}", STANDARD_REF + "；" + voltage_sources)
    check("E04", cold_work, mppt_max, "V", cold_work <= mppt_max,
          f"{size}×{vmp:g}×[1+({low:g}−25)×({gamma:g})]={cold_work:.6f} V；{work_note}；2024条文删除旧MPPT上界，本项另按厂家规格书检查",
          voltage_sources)
    worst_short = max(currents, key=lambda row: row['short_a'] / row['short_limit_a'], default={})
    worst_work = max(currents, key=lambda row: row['working_a'] / row['input_limit_a'], default={})
    short_limit = worst_short.get('short_limit_a', short_limit)
    input_limit = worst_work.get('input_limit_a', input_limit)
    max_short, max_work = worst_short.get('short_a', 0), worst_work.get('working_a', 0)
    current_evidence = f"各MPPT按对应型号限值校核，最不利Isc={max_short:.6f}/{short_limit:g} A；Imp={max_work:.6f}/{input_limit:g} A"
    check("E05", max_short, short_limit, "A", all(r["short_a"] <= r["short_limit_a"] and r["strings"] <= r["ports"] for r in currents),
          current_evidence, "；".join(_source(row) for row in models))
    check("E06", max_work, input_limit, "A", all(r["working_a"] <= r["input_limit_a"] for r in currents),
          current_evidence, "；".join(_source(row) for row in models))
    checks['E05']['per_mppt'] = currents
    checks['E06']['per_mppt'] = currents
    unit_ratios_pass = all(r["dc_ac_ratio"] <= DC_AC_MAX for r in per_inverter)
    units_note = f"接线、整体与每台容配比上限要求的最小台数={units}" if unit_ratios_pass else f"单串容量已超每台容配比上限，增加至{units}台仍不能满足，保留失败诊断"
    check("E07", ratio, [DC_AC_MIN, DC_AC_MAX], "", DC_AC_MIN <= ratio <= DC_AC_MAX and unit_ratios_pass,
          f"全部{len(identifiers)}块；整体容配比={ratio:.6f}；{units_note}；" + "；".join(r["evidence"] for r in per_inverter), "行业做法；示意，可改")
    checks["E07"]["per_inverter"] = per_inverter
    checks["E07"]["level"] = "advice" if ratio < DC_AC_MIN and unit_ratios_pass else "hard"
    checks["E07"]["hint_zh"] = ("逆变器容量偏大，可考虑更小功率的型号" if checks["E07"]["level"] == "advice"
                                else "容配比超过上限，请更换型号或减少每台连接的组件")
    check("E08", remainder, 0, "块", remainder == 0, f"{len(identifiers)}块，{count}串，{remainder}块剩余", "行业做法")
    identities = {m.id: orientation.key(m) for m in design.modules}
    tokens = [{(identities[mid], len(s['module_ids'])) for s in group for mid in s['module_ids']} for group in by_mppt.values()]
    check("E09", size, size, "块/串", all(len(group) <= 1 for group in tokens),
          "同一路MPPT只接同一种串长" if len(set(identities.values())) <= 1 else "同一路MPPT只接同朝向组、同一种串长", "行业做法")
    return dict(version=design.version, module_id=module["module_id"], inverter_id=inverter["inverter_id"], inverter_model=inverter["model"],
                inverters=[dict(inverter_id=row['inverter_id'], model=row['model'], count=devices.count(row)) for row in models],
                inverter_count=units, modules_per_string=size, **({'modules_per_string_short': shortest} if shortest < size else {}),
                min_modules_per_string=minimum, max_modules_per_string=maximum,
                feasible_range=[minimum, maximum], string_count=count, strings=strings, unused_modules=identifiers[sum(lengths):],
                module_count=len(identifiers), dc_kw=dc_kw, connected_dc_kw=sum(lengths) * module["pmax_w"] / 1000,
                voc_cold_v=cold_oc, vmp_hot_v=hottest, vmp_cold_v=cold_work, dc_ac_ratio=ratio,
                strings_per_mppt_allowed=allowed, mppt_currents=currents, per_inverter=per_inverter, temperature=temperatures, checks=checks,
                range_evidence=f"Nmin=ceil({mppt_min:g}/{hot_vmp:.6f})={minimum}；"
                               f"Nmax=min(floor({min(dc_limit, system_limit):g}/{cold_voc:.6f}),floor({mppt_max:g}/{cold_vmp:.6f}))={maximum}",
                wiring_note="排、层分组逐行蛇形；同一行的障碍物间断仍连续组串（简化）；按容量比例分台，同路MPPT同串长，为异长串预留MPPT")


def calculate(project, design, *, offline=False, shadows=None, options=False, selected=None):
    project, design = validate_project(project), validated(Design, design, "DESIGN_INVALID")
    from .installation import effective
    project = effective(project, design)
    from .personal import phase_electrical, transformer_limit
    if not options and selected is None and any(m.phase is not None for m in design.modules):
        return phase_electrical(project, design, offline=offline, shadows=shadows)
    catalog = equipment_catalog()
    try:
        module = catalog["modules"][project.equipment.module_id]
        candidates = ([catalog["inverters"][project.equipment.inverter_id]] if project.equipment.inverter_id
                      else [catalog["inverters"][key] for key in sorted(catalog["inverters"])])
    except KeyError as error:
        raise GzError("EQUIPMENT_NOT_FOUND", "找不到指定组件或逆变器型号", "使用设备目录里的module_id或inverter_id") from error
    candidates = [r for r in candidates if not project.equipment.inverter_brand or r['manufacturer'] == project.equipment.inverter_brand]
    if not candidates:
        raise GzError('EQUIPMENT_NOT_FOUND', '指定品牌与型号没有匹配设备', '核对逆变器品牌和目录型号')
    temperatures = _temperatures(project.site, module, offline)
    identifiers = [identifier for modules in orientation.groups(design).values() for identifier in _serpentine(modules)]
    results = [_candidate(module, candidate, design, temperatures, identifiers) for candidate in candidates]
    if not project.equipment.inverter_id:
        results += [_candidate(module, large, design, temperatures, identifiers, small)
                    for large in candidates for small in candidates
                    if large['manufacturer'] == small['manufacturer'] and large['rated_ac_kw'] > small['rated_ac_kw']]
    def rank(result):
        hard_failures = sum(check["status"] == "fail" for code, check in result["checks"].items() if code != "E06" and check.get("level") != "advice")
        identifier = '+'.join(row['inverter_id'] for row in result['inverters'])
        return hard_failures, abs(result["dc_ac_ratio"] - DC_AC_TARGET), result["inverter_count"], identifier
    if options:
        return results
    limit = transformer_limit(project)
    ac = lambda r: sum(catalog['inverters'][u['inverter_id']]['rated_ac_kw'] for u in r['per_inverter'])
    feasible = [r for r in results if limit is None or ac(r) <= limit + 1e-9]
    selected = selected or min(feasible or results, key=rank)
    selected["candidates"] = [dict(inverter_id=r["inverter_id"], inverter_count=r["inverter_count"], inverters=r['inverters'],
                                   modules_per_string=r["modules_per_string"], dc_ac_ratio=r["dc_ac_ratio"],
                                   hard_failures=rank(r)[0], failed_checks=[code for code, c in r["checks"].items() if c["status"] == "fail"]) for r in results]
    selected["selection_reason"] = ("用户指定型号，保留失败诊断" if project.equipment.inverter_id else
                                    f"优先硬失败最少，再取容配比最接近示意目标{DC_AC_TARGET:g}，再取台数少、编号顺序")
    selected["metadata"] = dict(module_source=_source(module),
                                inverter_source='；'.join(_source(catalog['inverters'][row['inverter_id']]) for row in selected['inverters']),
                                standard_ref=STANDARD_REF,
                                standard_revision="2024修订附件PDF第26页（印刷20）：6.4.2删除旧Vmpptmax上界，E04另按厂家规格书校核MPPT范围",
                                working_voltage_coefficient="功率温度系数近似工作电压温度系数", dc_capacity_basis="整体按全部排板组件，含未接入剩余；每台按实际接入组件；另列connected_dc_kw")
    selected = cables.calculate(project, design, selected, catalog)
    losses = {row['id']: row['total_loss_pct'] for row in (shadows or {}).get('modules', [])}
    wiring = dict(method='按位置接', reason='缺少本版本完整逐板遮挡结果，保留位置接法')
    if shadows and shadows.get('version') == design.version and all(m.id in losses for m in design.modules):
        models = [catalog['inverters'][r['inverter_id']] for r in selected['inverters']]
        devices = [catalog['inverters'][r['inverter_id']] for r in selected['per_inverter']]
        alternative = _candidate(module, models[0], design, temperatures, identifiers,
                                 models[1] if len(models) > 1 else None, losses, devices)
        alternative = cables.calculate(project, design, alternative, catalog)
        before, after = cables.spread(selected, losses), cables.spread(alternative, losses)
        old_length, new_length = selected['cables']['total_length_m'], alternative['cables']['total_length_m']
        connected = lambda result: {mid for s in result['strings'] for mid in s['module_ids']}
        safe = connected(selected) <= connected(alternative)
        safe = safe and alternative['cables']['routing']['blocked_routes'] <= selected['cables']['routing']['blocked_routes']
        safe = safe and all(selected['checks'][code]['status'] != 'pass' or alternative['checks'][code]['status'] == 'pass'
                            for code in ('E10', 'E11'))
        choose = safe and before - after >= 1 and new_length <= old_length * 1.1
        wiring = dict(method='按阴影接' if choose else '按位置接', position_spread_pct=before, shadow_spread_pct=after,
                      position_length_m=old_length, shadow_length_m=new_length,
                      reason=f'串内最大遮挡差{before:.2f}→{after:.2f}个百分点；电缆{old_length:.1f}→{new_length:.1f}m；'
                             + ('达到至少降1个百分点、增长不超过10%' if choose else '未同时满足降1个百分点、增长≤10%、余板和线路可行性不退化'))
        if choose:
            selected = dict(alternative, **{key: selected[key] for key in ['candidates', 'selection_reason', 'metadata']})
    selected['wiring'] = wiring
    return selected
