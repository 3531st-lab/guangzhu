"""Illustrative wind envelope; verified load factors do not verify missing wind tables."""
import csv
import math

from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .config import DATA_DIR

NOTE = '示意，不能代替结构计算，施工前要由结构工程师按规范复核'
LABELS = {'corner': '角部', 'edge': '边部', 'middle': '中部', 'outside': '屋面外'}
COLORS = {'corner': '#c94e42', 'edge': '#d79935', 'middle': '#368c90', 'outside': '#777777'}
FACTOR_SOURCE = 'GB55001-2021 §3.1.13；住建部2021年第70号；PDF13–14/印刷10–11页'
FACTOR_URL = 'https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2021/art_17339_761192.html'
MISSING = '缺GB50009-2012附录E目标表E.5、粗糙度高度表、屋面分区图；缺NB/T10115-2018斜放/EW体型原表及页码'
# Illustrative post-installed anchors for flat concrete roofs; the values are placeholders for the structural engineer.
ANCHOR_CAPACITY_N = 5000
ANCHOR_MINIMUM = 2
ANCHOR_NOTE = ('压块后超过屋面承重的支架改用化学锚栓与屋面结构层连接（示意：每个锚栓抗拉、抗剪设计值各按5kN，每块组件至少2个）；'
               '锚固抗拔、局部防水和主体传力须结构人员及厂家核定')


def facts(result=None, version=None):
    """Required copyable facts for compact tools, including truthful legacy absence."""
    if not result or result.get('version') != version:
        return dict(version=version, note=NOTE, source_status='未计算或旧档未记录风荷载', worst_zone=None, W01='unknown')
    metal = result.get('roof_type') == 'metal' or any('clamps' in row for row in result['modules'])
    value = dict(version=version, note=NOTE, source_status='示意；仅GB55001分项系数已核验',
                 worst_zone=LABELS[result['worst_zone']], W01='fail' if result['clamp_failed'] else 'pass' if metal else 'na')
    if metal:
        value['clamps'] = dict(required=result['clamp_required'], adopted=result['clamp_count'], failed=result['clamp_failed'])
    if result.get('anchor_count'):
        value['anchors'] = dict(count=result['anchor_count'], modules=result['anchored_modules'], why='压块超屋面承重，改锚栓固定（示意）')
    return value


def anchor(row):
    """Carry one module's factored uplift and sliding force by anchors instead of ballast blocks."""
    tension = max(0.0, 1.5 * row['uplift_n'] - row['dead_kg'] * 9.81)
    shear = 1.5 * row['horizontal_n']
    count = max(ANCHOR_MINIMUM, math.ceil(tension / ANCHOR_CAPACITY_N), math.ceil(shear / ANCHOR_CAPACITY_N))
    row.update(fixing='anchor', anchors=count, anchor_tension_n=tension, anchor_shear_n=shear, ballast_blocks=0, ballast_kg=0)


def totals(rows):
    """Per-zone ballast (and, when used, anchor) totals of module rows."""
    result = {}
    for name in LABELS:
        members = [r for r in rows if r['zone'] == name]
        if name == 'outside' and not members:
            continue
        result[name] = dict(label=LABELS[name], modules=len(members), ballast_blocks=sum(r['ballast_blocks'] for r in members),
                            ballast_kg=math.fsum(r['ballast_kg'] for r in members),
                            pressure_kpa_range=[min((r['pressure_kpa'] for r in members), default=0),
                                                max((r['pressure_kpa'] for r in members), default=0)],
                            blocks_range=[min((r['ballast_blocks'] for r in members), default=0),
                                          max((r['ballast_blocks'] for r in members), default=0)])
        anchored = [r for r in members if r.get('fixing') == 'anchor']
        if anchored:
            result[name].update(anchors=sum(r['anchors'] for r in anchored), anchored_modules=len(anchored))
    return result


def catalog():
    with (DATA_DIR / 'catalog/wind.csv').open(encoding='utf-8-sig', newline='') as stream:
        return {row['city']: row for row in csv.DictReader(stream)}


def city_pressure(site):
    rows = catalog()
    def distance(row):
        lat1, lat2 = math.radians(site.lat), math.radians(float(row['lat']))
        dlat = lat2 - lat1
        dlon = math.radians(float(row['lon']) - site.lon)
        sine = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 12742 * math.asin(min(1, math.sqrt(sine)))
    explicit = getattr(site, 'wind_city', None)
    selected = rows[explicit] if explicit else min(rows.values(), key=distance)
    return dict(selected, basic_pressure_kpa=float(selected['pressure_kpa']), distance_km=distance(selected),
                selection='用户指定' if explicit else '最近江苏市中心示意推定，非行政归属；省外请核实当地值')


def zones(outline, height):
    roof = orient(Polygon(outline).simplify(1e-9), sign=1)
    rectangle = list(roof.minimum_rotated_rectangle.exterior.coords)
    width = min(min(math.dist(a, b) for a, b in zip(rectangle, rectangle[1:])) * .1, height * .2)
    points = list(roof.exterior.coords)
    bands = [LineString([a, b]).buffer(width, cap_style=2).intersection(roof) for a, b in zip(points, points[1:])]
    corner = unary_union([band.intersection(bands[(i + 1) % len(bands)]) for i, band in enumerate(bands)])
    concave = []
    vertices = points[:-1]
    for i, vertex in enumerate(vertices):
        before, after = vertices[i - 1], vertices[(i + 1) % len(vertices)]
        incoming = (vertex[0] - before[0], vertex[1] - before[1])
        outgoing = (after[0] - vertex[0], after[1] - vertex[1])
        if incoming[0] * outgoing[1] - incoming[1] * outgoing[0] < -1e-9:
            u = [v / math.hypot(*incoming) * width for v in incoming]
            v = [c / math.hypot(*outgoing) * width for c in outgoing]
            square = Polygon([(vertex[0] + a * u[0] + b * v[0], vertex[1] + a * u[1] + b * v[1])
                              for a, b in [(1, 1), (-1, 1), (-1, -1), (1, -1)]])
            concave.append(square.intersection(roof))
    corner = unary_union([corner, *concave])
    boundary = unary_union([*bands, corner])
    return width, {'corner': corner, 'edge': boundary.difference(corner), 'middle': roof.difference(boundary)}


def classify(center, regions):
    point = Point(center[:2])
    return next((name for name, shape in regions.items() if shape.covers(point)), 'outside')


def ballast(area, pressure, tilt, dead, *, friction=.5, block_kg=15, permanent=1, wind_factor=1.5):
    normal = pressure * area * 1000
    uplift = normal * math.cos(math.radians(tilt))
    horizontal = normal * abs(math.sin(math.radians(tilt)))
    lift = max(0, wind_factor * uplift / (permanent * 9.81) - dead)
    slide = max(0, wind_factor * (uplift + horizontal / friction) / (permanent * 9.81) - dead)
    blocks = math.ceil(max(lift, slide) / block_kg)
    return dict(normal_force_n=normal, uplift_n=uplift, horizontal_n=horizontal, lift_required_kg=lift,
                slide_required_kg=slide, ballast_blocks=blocks, ballast_kg=blocks * block_kg,
                friction_n=friction * (permanent * (dead + blocks * block_kg) * 9.81 - wind_factor * uplift),
                sliding_demand_n=wind_factor * horizontal)


def zone_loads(footprints, masses, regions):
    """Allocate each rack's mass once; use union areas for the denominators."""
    combined = unary_union(list(footprints.values()))
    results = {}
    for zone, region in regions.items():
        area = combined.intersection(region).area
        mass = math.fsum(masses[key] * shape.intersection(region).area / shape.area
                         for key, shape in footprints.items() if shape.area)
        results[zone] = dict(area_m2=area, mass_kg=mass, load_kn_m2=mass * .00981 / area if area else 0)
    return results


def calculate(project, design, module, rack):
    from .wind_clamps import arrange
    settings = project.roof.wind
    params = settings.model_dump() if settings else {}
    city = city_pressure(project.site)
    reference_height = project.roof.height_m
    if project.roof.type in ('ground', 'carport'):
        reference_height = max((p[2] for m in design.modules for p in m.corners), default=0)
    width, regions = zones(project.roof.outline, reference_height)
    base = params.get('basic_pressure_kpa')
    base = city['basic_pressure_kpa'] if base is None else base
    roughness = params.get('roughness', 'B')
    exponent = {'A': .2, 'B': .3, 'C': .44, 'D': .6}[roughness]
    shape_base = .65 if design.params.layout == 'ew' else 1 if project.roof.type == 'metal' else .8
    dead = float(module['weight_kg']) + float(rack['rack_weight_kg_per_module'])
    rows = []
    occupied = set()
    if project.roof.type == 'pitched':
        from .roofplane import member
        from .pitched import rack as face_rack
        from .electrical import equipment_catalog
        supports = equipment_catalog()['racking']
    # Phase-one sites must be identical when priced alone and when phase two is subsequently installed.
    for panel in sorted(design.modules, key=lambda item: item.phase != 1):
        plane = None
        if project.roof.type == 'pitched':
            plane = member(project.roof, panel.id)
            support = supports[face_rack(plane, project.roof)]
            dead = float(module['weight_kg']) + float(support['rack_weight_kg_per_module'])
            shape_base = 1
        zone = classify(panel.center, regions)
        shape = shape_base * {'corner': 1.6, 'edge': 1.3, 'middle': 1, 'outside': 1.6}[zone]
        height = project.roof.height_m + max(p[2] for p in panel.corners)
        height_factor = (max(height, 5) / 10) ** exponent
        a, b, _, d = panel.corners
        area = math.dist(a, b) * math.dist(a, d)
        pressure = base * height_factor * shape * 1.2
        forces = ballast(area, pressure, panel.tilt, dead, friction=params.get('friction', .5),
                         block_kg=params.get('block_kg', 15))
        if project.roof.type != 'flat':
            forces.update(ballast_blocks=0, ballast_kg=0)
        row = dict(id=panel.id, zone=zone, phase=panel.phase, area_m2=area, height_m=height,
                   height_factor=height_factor, shape_factor=shape, pressure_kpa=pressure, dead_kg=dead, **forces)
        if plane is not None:
            row.update(plane=plane.id, material=plane.material, rack_id=face_rack(plane, project.roof))
            if plane.material == 'concrete':
                row['anchors'] = 4
        if project.roof.type == 'metal' or plane is not None and plane.material == 'metal':
            row['clamps'] = arrange(project.roof, panel, 1.5 * forces['uplift_n'] / 1000, params, occupied)
        rows.append(row)
    clamp_rows = [r['clamps'] for r in rows if 'clamps' in r]
    result = dict(version=design.version, roof_type=project.roof.type, city=city, basic_pressure_kpa=base, zone_width_m=width,
                  regions={name: mapping(shape) for name, shape in regions.items()}, modules=rows, zones=totals(rows),
                  ballast_mass_kg=math.fsum(r['ballast_kg'] for r in rows), ballast_blocks=sum(r['ballast_blocks'] for r in rows),
                  clamp_count=sum(r['adopted'] for r in clamp_rows), clamp_required=sum(r['required'] for r in clamp_rows),
                  clamp_failed=sum(not r['passed'] for r in clamp_rows), note=NOTE, missing=MISSING,
                  factor_source=dict(title=FACTOR_SOURCE, url=FACTOR_URL, published='2021-04-09', accessed='2026-10-06'),
                  assumptions=dict(status='示意', roughness=roughness, gust_factor=1.2, shape_base=shape_base,
                                   block_kg=params.get('block_kg', 15), friction=params.get('friction', .5),
                                   permanent_factor=1, wind_factor=1.5),
                  method='示意法向不利风包络；东西向两坡不抵消；滑移扣除上拔；支架质量按投影均布，不是支点局部应力',
                  zone_note='示意宽度min(短边×0.1,屋面高度×0.2)；边带相邻交集为角部，凹角增加两边方向宽度邻域；非已核验GB分区',
                  height_note='示意高度幂律，默认B，工业区也可能C；现场确认粗糙度及脉动放大')
    if project.roof.type in ('ground', 'carport'):
        result['zone_note'] = '示意宽度min(场地短边×0.1,实际安装最高点×0.2)；基础及钢结构须厂家核定，不代表规范分区验算'
        result['missing'] = '缺GB50009风压、地面支架和车棚具体体型原表；基本风压及结构参数均待设计方核定'
    return result, regions
