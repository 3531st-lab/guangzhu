"""Indicative conductor quantities and resistive voltage drop; sources in docs/sources.md T26."""
import math
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from .wirepaths import Planner, NOTE, distance as path_length

DC = [(4, 44), (6, 57), (10, 79)]
AC = list(zip((6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185), (44, 60, 80, 105, 128, 154, 194, 233, 268, 300, 340)))
NOTES = [
    NOTE,
    '直流跳线及正负两端各计一次，导体总长乘1.1富余（示意）；等效单程=导体总长/2。',
    '直流120°C、环境60°C、两带载贴面相触：Nexans 4/6/10mm²为44/57/79A；120°C仅20000h热耐久条件，非25年保证。',
    '交流90°C XLPE/EPR铜多芯、三相、表面穿管、空气30°C：Prysmian C3.4。温度、成束及敷设均示意，现场复核降容。',
    '铜ρ20=0.0175，α=0.00395（ABB2006附录E）；ρ(T)=ρ20[1+α(T−20)]，并非产品最大电阻保证。',
    '直流2%为ABB2014建议1–2%内项目取值；交流2%为项目假设，均非中国强制限值。交流400V、功率因数1。',
    '交流加屋面高度及5m落地余量（示意），按四芯电缆路线米计量，另列四根导体米；暂不改变造价。',
    '发电按每块板单独计算，未模拟串内失配；改接法仅以串内遮挡差表示好处，不改发电量。',
]
SOURCE = 'docs/sources.md#t26；ABB2006附录E；ABB2014§3.4.2；Nexans产品页2；Prysmian C3.4'


def route(points):
    return [p for a, b in zip(points, points[1:]) for p in (list(a), [b[0], a[1]], list(b))]


def length(points):
    return sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(points, points[1:]))


def conductor(kind, distance, current, voltage, required):
    temperature = 120 if kind == 'dc' else 90
    rho = .0175 * (1 + .00395 * (temperature - 20))
    factor = 1 if kind == 'dc' else math.sqrt(3)
    for section, ampacity in DC if kind == 'dc' else AC:
        drop = factor * rho * distance * current / (section * voltage) * 100
        if ampacity >= required and drop <= 2:
            break
    return dict(section_mm2=section, ampacity_a=ampacity, required_a=required, current_a=current, voltage_v=voltage,
                drop_pct=drop, feasible=ampacity >= required and drop <= 2, temperature_c=temperature, rho=rho)


def calculate(project, design, electric, catalog):
    from .installation import effective
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
                              module['vmp_v'] * len(s['module_ids']), 1.25 * module['isc_a'])['drop_pct'] for s in strings), default=0)
    panels = unary_union([Polygon([c[:2] for c in m.corners]) for m in design.modules]) if design.modules else Polygon()
    def position(label, center, supplied, strings=()):
        point = min(supplied, key=lambda p: math.dist(p, center)) if supplied else planner.default_position(center)
        note = '示意，按现场改' if not supplied else '手工放置点，可共用'
        # On a large flat roof an edge inverter can be too far from its strings; mount it among the arrays instead
        # (in an aisle or row gap, never on an obstacle or a panel), at the spot with the smallest worst-case drop.
        if not supplied and strings and roof.type == 'flat' and worst(point, strings) > 2:
            xs, ys = zip(*[modules[mid] for s in strings for mid in s['module_ids']])
            grid = [(min(xs) + (max(xs) - min(xs)) * i / 16, min(ys) + (max(ys) - min(ys)) * j / 16) for i in range(17) for j in range(17)]
            inside = [p for p in [tuple(center), *grid] if planner.free(p) and not panels.covers(Point(p))]
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
        row = conductor('dc', distance, module['imp_a'], module['vmp_v'] * len(string['module_ids']), 1.25 * module['isc_a'])
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
        row = conductor('ac', distance, current, 400, current)
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
            evidence=f'最大压降{maximum:.6f}%；同时校核载流量及路径可达；温度/敷设示意，见电缆页', hint_zh=hint)
        for row in rows:
            key = kind, row['section_mm2']
            total = summary.setdefault(key, dict(kind=kind, section_mm2=key[1], length_m=0, drop_pct_max=0))
            total['length_m'] += row['length_m']
            total['drop_pct_max'] = max(total['drop_pct_max'], row['drop_pct'])
    electric['cables'] = dict(positions=positions, dc=dc, ac=ac, summary=list(summary.values()), notes=NOTES,
                              total_length_m=sum(row['length_m'] for row in dc + ac))
    baseline = sum(r['baseline_length_m'] or 0 for r in dc)
    comparable = all(r['baseline_length_m'] is not None and r['routing_status'] == 'ok' for r in dc)
    electric['cables']['routing'] = dict(version=1, method='固定组串的候选节线路径',
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
