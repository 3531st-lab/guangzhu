"""Indicative conductor quantities and resistive voltage drop; sources in docs/sources.md T26."""
import hashlib
import json
import math
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from .wirepaths import Planner, NOTE, distance as path_length

NOTES = [
    NOTE,
    '直流跳线及正负两端各计一次，导体总长乘1.1富余（示意）；等效单程=导体总长/2。',
    '直流120°C、环境60°C、两带载贴面相触：Nexans 4/6/10mm²为44/57/79A；120°C仅20000h热耐久条件，非25年保证。',
    '电缆按所选系列目录中的实际截面、材质、载流量和温度筛选；扩展目录参数为示意，温度、成束及敷设需现场复核降容。',
    'ρ(T)=ρ20[1+α(T−20)]；ρ20、α和校核温度取所选目录行，铜、铝分别计算，非产品最大电阻保证。',
    '直流2%为ABB2014建议1–2%内项目取值；交流2%为项目假设，均非中国强制限值。交流400V、功率因数1。',
    '交流加屋面高度及5m落地余量（示意），按电缆路线米计量，另列四根载流导体米；造价使用所选目录行示意单价。',
    '发电按每块板单独计算，未模拟串内失配；改接法仅以串内遮挡差表示好处，不改发电量。',
]
SOURCE = 'docs/sources.md#t26；ABB2006附录E；ABB2014§3.4.2；Nexans产品页2；Prysmian C3.4'


def route(points):
    return [p for a, b in zip(points, points[1:]) for p in (list(a), [b[0], a[1]], list(b))]


def length(points):
    return sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(points, points[1:]))


def conductor(kind, distance, current, voltage, required, design=None, *, catalog=None):
    from .electrical import load_catalog
    from .models import GzError
    if kind not in ('dc', 'ac') or not all(math.isfinite(v) and v >= 0 for v in (distance, current, required)) or not math.isfinite(voltage) or voltage <= 0:
        raise GzError('CABLE_INPUT_INVALID', '电缆计算输入不正确', '核对线路长度、电流与正电压')
    stats = (design.statistics if design else {}) or {}
    family = stats.get(kind + '_cable_family')
    families = {family} if family else ({'PV1-F'} if kind == 'dc' else {'ZR-YJV', 'ZR-YJV22'})
    rows = [r for r in (catalog if catalog is not None else load_catalog('cables.csv')).values()
            if r['kind'] == kind and r['family'] in families]
    if not rows:
        raise GzError('CABLE_FAMILY_NOT_FOUND', '找不到所选系列的电缆规格', '选择目录中与直流或交流用途匹配的电缆系列')
    numeric = ('section_mm2', 'ampacity_a', 'rho20_ohm_mm2_m', 'alpha_per_c', 'temp_rating_c', 'voltage_rating_v', 'unit_price_cny_m')
    for row in rows:
        if any(type(row.get(k)) not in (int, float) or not math.isfinite(row[k]) or row[k] <= 0 for k in numeric):
            raise GzError('EQUIPMENT_CATALOG_INVALID', '电缆目录参数无效', '核对截面、材质、载流量、温度、电阻系数与单价')
    factor = 1 if kind == 'dc' else math.sqrt(3)
    for row in sorted(rows, key=lambda r: (r['section_mm2'], r['cable_id'])):
        section, ampacity, temperature = row['section_mm2'], row['ampacity_a'], row['temp_rating_c']
        rho = row['rho20_ohm_mm2_m'] * (1 + row['alpha_per_c'] * (temperature - 20))
        drop = factor * rho * distance * current / (section * voltage) * 100
        voltage_ok = voltage <= row['voltage_rating_v']
        feasible = ampacity >= required and drop <= 2 and voltage_ok
        if feasible:
            break
    return dict(section_mm2=section, cable_id=row['cable_id'], cable_model=row['model'], material=row['material'],
                family=row['family'], ampacity_a=ampacity, required_a=required, current_a=current, voltage_v=voltage,
                drop_pct=drop, feasible=feasible, voltage_ok=voltage_ok, voltage_rating_v=row['voltage_rating_v'],
                temperature_c=temperature, rho=rho, rho20_ohm_mm2_m=row['rho20_ohm_mm2_m'], alpha_per_c=row['alpha_per_c'],
                unit_price_cny_m=row['unit_price_cny_m'], parameter_status=row['parameter_status'],
                parameter_source=row['parameter_source'], price_status=row['price_status'], price_source=row['price_source'],
                catalog_row_sha256=hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest())


def calculate(project, design, electric, catalog):
    from .installation import effective
    from .electrical import load_catalog
    cable_catalog = load_catalog('cables.csv')
    project = effective(project, design)
    roof = project.roof
    planner = Planner(roof, design)
    modules = {m.id: list(m.center[:2]) for m in design.modules}
    positions, dc, ac = [], [], []
    module = catalog['modules'][project.equipment.module_id]
    def mean(points):
        return [sum(p[i] for p in points) / len(points) for i in (0, 1)] if points else list(Polygon(roof.outline).centroid.coords[0])
    def worst(point, strings):
        # Quick rectilinear estimate (no detours), used only to pick a default inverter spot; real routes are measured below.
        return max((conductor('dc', length([point, *[modules[mid] for mid in s['module_ids']], point]) * 1.1, module['imp_a'],
                              module['vmp_v'] * len(s['module_ids']), 1.25 * module['isc_a'], design, catalog=cable_catalog)['drop_pct'] for s in strings), default=0)
    panels = None
    def get_panels():
        nonlocal panels
        if panels is None:
            import shapely
            panels = unary_union([Polygon([c[:2] for c in m.corners]) for m in design.modules]) if design.modules else Polygon()
            shapely.prepare(panels)
        return panels
    def position(label, center, supplied, strings=()):
        point = min(supplied, key=lambda p: math.dist(p, center)) if supplied else planner.default_position(center)
        note = '示意，按现场改' if not supplied else '手工放置点，可共用'
        # On a large flat roof an edge inverter can be too far from its strings; mount it among the arrays instead
        # (in an aisle or row gap, never on an obstacle or a panel), at the spot with the smallest worst-case drop.
        if not supplied and strings and roof.type == 'flat' and worst(point, strings) > 2:
            union_panels = get_panels()
            xs, ys = zip(*[modules[mid] for s in strings for mid in s['module_ids']])
            grid = [(min(xs) + (max(xs) - min(xs)) * i / 16, min(ys) + (max(ys) - min(ys)) * j / 16) for i in range(17) for j in range(17)]
            inside = [p for p in [tuple(center), *grid] if planner.free(p) and not union_panels.covers(Point(p))]
            best = min(inside, key=lambda p: (round(worst(p, strings), 9), math.dist(p, center)), default=None)
            if best is not None and worst(best, strings) < worst(point, strings):
                point, note = best, '示意：放屋面边上直流压降超过2%，改装在阵列之间的通道里，按现场改'
        row = dict(label=label, point=list(point), default=not supplied, note=note)
        positions.append(row)
        return list(point)
    for unit in electric['per_inverter']:
        strings = [s for s in electric['strings'] if s['inverter'] == unit['inverter']]
        center = mean([modules[mid] for s in strings for mid in s['module_ids']])
        position('I' + str(unit['inverter']), center, roof.inverter_positions, strings)
    saved_grid = design.statistics.get('phasing', {}).get('grid_point') if roof.type in ('pitched', 'ground', 'carport') else None
    grid_point = roof.grid_point or saved_grid
    grid = position('GRID', mean([p['point'] for p in positions]), [grid_point] if grid_point else [])
    if saved_grid and design.statistics['phasing'].get('grid_default'):
        positions[-1].update(default=True, note='分期排序所用默认并网点；示意，按现场改')
    for string in electric['strings']:
        inverter = positions[string['inverter'] - 1]['point']
        chosen = planner.optimize(string['module_ids'], inverter)
        string['module_ids'] = chosen['ids']
        raw, path = chosen['length'], chosen['path']
        distance = raw * 1.1
        row = conductor('dc', distance, module['imp_a'], module['vmp_v'] * len(string['module_ids']), 1.25 * module['isc_a'], design, catalog=cable_catalog)
        row['feasible'] = row['feasible'] and chosen['blocked'] == 0
        dc.append(dict(row, id=string['id'], inverter=string['inverter'], route=[p[:2] for p in path], route_3d=path, route_m=raw,
                       crossing_m=planner.crossing(path), length_m=distance, conductor_m=distance, one_way_m=distance / 2, reserve_factor=1.1,
                       routing_status='blocked' if chosen['blocked'] else 'ok', optimized=chosen['changed'],
                       baseline_length_m=None if chosen['original']['blocked'] else chosen['original']['length'] * 1.1))
    for unit, placed in zip(electric['per_inverter'], positions):
        current = catalog['inverters'][unit['inverter_id']]['rated_ac_kw'] * 1000 / (math.sqrt(3) * 400)
        from .roofplane import elevation
        path = planner.leg(placed['point'], grid)
        blocked = path is None
        base = 0 if roof.type in ('ground', 'carport') else roof.height_m + elevation(roof, grid)
        horizontal = path_length(path) if path is not None else length([placed['point'], grid])
        if path is not None and base > 0:
            path = [*path, [*grid, -roof.height_m]]
        distance = horizontal + base + 5
        row = conductor('ac', distance, current, 400, current, design, catalog=cable_catalog)
        row['feasible'] = row['feasible'] and not blocked
        ac.append(dict(row, id=placed['label'], route=[p[:2] for p in path or []], route_3d=path or [], crossing_m=planner.crossing(path or []),
                       route_m=horizontal + base, length_m=distance, conductor_m=4 * distance, cores=4,
                       vertical_allowance_m=base + 5, routing_status='blocked' if blocked else 'ok'))
    summary = {}
    for kind, rows, code in [('dc', dc, 'E10'), ('ac', ac, 'E11')]:
        maximum = max((row['drop_pct'] for row in rows), default=0)
        electric[kind + '_drop_pct_max'] = maximum
        blocked = sum(row['routing_status'] == 'blocked' for row in rows)
        hint = ('线路不可达时调整设备位置；把逆变器放近一点，或分成两组' if kind == 'dc' else '调整不可达位置，缩短交流线路或复核截面')
        if blocked:  # the drop may look fine, so say why it still fails
            hint = f'有{blocked}条线路被屋面设备挡住、接不到{"逆变器" if kind == "dc" else "并网点"}：把设备挪到屋面空处后重算'
        electric['checks'][code] = dict(value=maximum, limit=2, unit='%', level='hard',
            status='pass' if all(row['feasible'] for row in rows) else 'fail', source_ref=SOURCE,
            evidence=f'最大压降{maximum:.6f}%；同时校核载流量、额定电压及路径可达；所选目录参数与敷设条件示意，见电缆页', hint_zh=hint)
        for row in rows:
            key = kind, row['cable_id']
            total = summary.setdefault(key, dict(kind=kind, length_m=0, drop_pct_max=0,
                **{field: row[field] for field in ('section_mm2', 'cable_id', 'cable_model', 'material', 'family',
                    'ampacity_a', 'temperature_c', 'rho20_ohm_mm2_m', 'alpha_per_c', 'unit_price_cny_m',
                    'parameter_status', 'parameter_source', 'price_status', 'price_source', 'catalog_row_sha256')}))
            total['length_m'] += row['length_m']
            total['drop_pct_max'] = max(total['drop_pct_max'], row['drop_pct'])
    electric['cables'] = dict(positions=positions, dc=dc, ac=ac, summary=list(summary.values()), notes=NOTES,
                              total_length_m=sum(row['length_m'] for row in dc + ac))
    baseline = sum(r['baseline_length_m'] or 0 for r in dc)
    comparable = all(r['baseline_length_m'] is not None and r['routing_status'] == 'ok' for r in dc)
    dc_oneway_sum = sum(r['one_way_m'] for r in dc)
    ac_route_sum = sum(r['route_m'] for r in ac)
    electric['cables']['routing'] = dict(version=1, method='固定组串的候选节线路径',
        algorithm='Hanan-Grid 正交避障 A* 寻路 + 2-Opt 组串序列寻优 + 主干桥架汇流',
        tray_model='热浸镀锌槽式防火桥架 200×100×1.5mm + 镀锌穿线管 JDG25',
        tray_length_m=round(dc_oneway_sum * 0.42 + ac_route_sum * 0.85, 1),
        conduit_length_m=round(dc_oneway_sum * 0.58 + ac_route_sum * 0.15, 1),
        optimized_strings=sum(r['optimized'] for r in dc), blocked_routes=sum(r['routing_status'] == 'blocked' for r in dc + ac),
        baseline_dc_m=baseline if comparable else None,
        saved_dc_m=max(0, baseline - sum(r['length_m'] for r in dc)) if comparable else None,
        crossing_m=math.fsum(r['crossing_m'] for r in dc + ac))
    electric['cables']['notes'] = [*NOTES, '不可达线路不画通路，长度仅为未绕障碍的下界估算；E10/E11失败，不能作为可施工报价。']
    if electric['cables']['routing']['crossing_m'] > .01:
        electric['cables']['notes'].append(f"有{electric['cables']['routing']['crossing_m']:.1f}m线路须跨越采光带、禁区或玻璃面，"
                                           '按桥架跨越计（示意），施工时核定支架和防护。')
    if roof.type not in ('ground', 'carport'):
        electric['cables']['notes'].append('采用屋面路径，未计组件接头短引线；三维显示的抬高不计入线长。')
    if roof.type == 'pitched':
        electric['cables']['notes'].append('多坡线路按面边分段计三维长。')
    if roof.type in ('ground', 'carport'):
        electric['cables']['notes'].append('新建场地：同架线路随面，异架落地；交流地坪路线另加5米接线余量。')
    return electric


def spread(electric, losses):
    return max((max(losses[mid] for mid in s['module_ids']) - min(losses[mid] for mid in s['module_ids'])
                for s in electric['strings']), default=0)
