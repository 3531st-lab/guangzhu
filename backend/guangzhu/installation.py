"""Physical ground and parking facilities shared by layouts, quantities and exports."""
import math

from shapely.affinity import affine_transform
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from .models import CarportSettings, GzError, GroundSettings, Keepout, RoofPlane, obstacle_polygon
from .roofplane import plane_elevation

TYPES = ('ground', 'carport')


def effective(project, design):
    if project.roof.type in TYPES and design.installation_roof is not None:
        project = project.model_copy(deep=True)
        project.roof = design.installation_roof.model_copy(deep=True)
    return project


def inherit_keepouts(design, base):
    """Repacking uses combined geometry, but design additions retain their own storage."""
    design.added_keepouts = [zone.model_copy(deep=True) for zone in base.added_keepouts]
    if design.installation_roof is not None:
        additions = {zone.id for zone in design.added_keepouts}
        design.installation_roof.keepouts = [zone for zone in design.installation_roof.keepouts if zone.id not in additions]
    return design


def validate_site(roof):
    if roof.height_m != 0 or roof.parapet_height_m != 0:
        raise GzError('SITE_HEIGHT_INVALID', '新建场地以地坪0米为基准，无女儿墙', '棚面和组件高度分别填写，不叠加建筑高度')
    if roof.type == 'ground':
        roof.ground = roof.ground or GroundSettings()
        if Polygon(roof.outline).buffer(-roof.ground.fence_setback_m).is_empty:
            raise GzError('FENCE_AREA_EMPTY', '围栏退让后没有安装区域', '减小退让或扩大场地')
        return
    roof.carport = roof.carport or CarportSettings()
    shape = Polygon(roof.outline)
    if len({p.id for p in roof.planes}) != len(roof.planes):
        raise ValueError('车棚编号必须唯一')
    for index, plane in enumerate(roof.planes):
        polygon = Polygon(plane.outline)
        if plane.slope_deg > 15 or not shape.buffer(1e-8).covers(polygon):
            raise ValueError('车棚倾角须为0–15°且完整位于场地内')
        if any(polygon.relate_pattern(Polygon(p.outline), '2********') for p in roof.planes[:index]):
            raise ValueError('独立车棚实体不能重叠；棚间车道和缝隙允许')
    for item in [*roof.carport.bays, *roof.carport.aisles, *roof.carport.strips]:
        if not shape.buffer(1e-8).covers(Polygon(item.polygon)):
            raise ValueError('停车设施必须完整位于场地内')
    for bay in roof.carport.bays:
        corners = list(Polygon(bay.polygon).minimum_rotated_rectangle.exterior.coords)
        sides = sorted(math.dist(a, b) for a, b in zip(corners, corners[1:]))
        if abs(sides[0] - 2.4) > 1e-6 or abs(sides[-1] - 5.1) > 1e-6:
            raise GzError('PARKING_REBUILD_REQUIRED', '净车位尺寸须保持2.4×5.1米',
                          '修改图纸比例后请重新生成停车设施：点击“按当前设置重新生成车位和棚面”')
    clear = unary_union([Polygon(p.polygon) for p in [*roof.carport.bays, *roof.carport.aisles]])
    for plane in roof.planes:
        points = roof.carport.columns.get(str(plane.id), [])
        support = Polygon(plane.outline)
        if not points or any(not support.covers(Point(p).buffer(.1)) for p in points):
            strips = [Polygon(s.polygon) for s in roof.carport.strips if s.id == f'P{plane.id}']
            space = support.intersection(unary_union(strips)).difference(clear.buffer(.101)).buffer(-.101)
            options = []
            angle = math.radians(roof.carport.direction_deg or 0)
            u, v = (math.cos(angle), math.sin(angle)), (-math.sin(angle), math.cos(angle))
            local = affine_transform(space, [*u, *v, 0, 0])
            if not local.is_empty:
                left, bottom, right, top = local.bounds
                ys = [(bottom + top) / 2] if roof.carport.column_rows == 1 else [bottom, top]
                count = max(1, math.ceil((right - left) / 4.8))
                for y in ys:
                    for i in range(count + 1):
                        x = left + (right - left) * i / count
                        point = (x * u[0] + y * v[0], x * u[1] + y * v[1])
                        if space.buffer(1e-8).covers(Point(point)):
                            options.append(point)
            if len(options) < 2 * roof.carport.column_rows:
                raise ValueError(f'P{plane.id}修改后结构带内无法布置至少两根合法立柱，请调整棚面或结构带')
            roof.carport.columns[str(plane.id)] = points = options
        if any(not shape.covers(Point(p).buffer(.1)) or clear.intersects(Point(p).buffer(.1)) for p in points):
            raise ValueError('示意直径0.2米立柱不能侵占净车位或净车道')


def parking(roof):
    """Explicit rebuild only. Reverse perpendicular small-car dimensions, JGJ100 table4.3.4."""
    config = (roof.carport or CarportSettings()).model_copy(deep=True)
    shape = Polygon(roof.outline)
    if config.direction_deg is None:
        points = list(shape.minimum_rotated_rectangle.exterior.coords)
        a, b = max(zip(points, points[1:]), key=lambda pair: math.dist(*pair))
        config.direction_deg = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
    angle = math.radians(config.direction_deg)
    u, v = (math.cos(angle), math.sin(angle)), (-math.sin(angle), math.cos(angle))
    local = affine_transform(shape, [*u, *v, 0, 0])
    xmin, ymin, xmax, ymax = local.bounds
    unit_depth = config.bay_rows * 5.1 + config.structural_strip_m
    config.bays, config.aisles, config.strips, config.columns = [], [], [], {}
    planes = []

    def world(polygon):
        return affine_transform(polygon, [u[0], v[0], u[1], v[1], 0, 0])

    def zone(identifier, label, polygon):
        return Keepout(id=identifier, label=label, polygon=list(world(polygon).exterior.coords)[:-1])

    y = ymin + 5.5
    while y + unit_depth + 5.5 <= ymax + 1e-8:
        cells = []
        x = xmin
        while x + 2.4 <= xmax + 1e-8:
            full = box(x, y - 5.5, x + 2.4, y + unit_depth + 5.5)
            blocked = any(world(full).intersects(obstacle_polygon(o)) for o in roof.obstacles)
            blocked = blocked or any(world(full).intersects(Polygon(k.polygon)) for k in roof.keepouts)
            if local.buffer(1e-8).covers(full) and not blocked:
                cells.append(x)
            x += 2.4
        runs = []
        for x in cells:
            if not runs or x - runs[-1][-1] > 2.401:
                runs.append([])
            runs[-1].append(x)
        for run in runs:
            pid = len(planes) + 1
            left, right = run[0], run[-1] + 2.4
            strip_y = y + 5.1 if config.bay_rows == 2 else y
            strip = box(left, strip_y, right, strip_y + config.structural_strip_m)
            config.strips.append(zone(f'P{pid}', '立柱结构预留带（示意）', strip))
            for x in run:
                for row in range(config.bay_rows):
                    bottom = y if config.bay_rows == 2 and row == 0 else strip_y + config.structural_strip_m
                    config.bays.append(zone(f'B{len(config.bays) + 1}', '小型车倒车垂直停车净位', box(x, bottom, x + 2.4, bottom + 5.1)))
            for bottom in (y - 5.5, y + unit_depth):
                config.aisles.append(zone(f'A{len(config.aisles) + 1}', '5.5米净车道', box(left, bottom, right, bottom + 5.5)))
            outline = list(world(box(left, y, right, y + unit_depth)).exterior.coords)[:-1]
            azimuth = 180 if config.facing == 'south' else (90 - config.direction_deg) % 360
            planes.append(RoofPlane(id=pid, outline=outline, slope_deg=config.tilt_deg, slope_azimuth_deg=azimuth,
                                    offset_m=config.clear_height_m + config.structure_depth_m))
            xs = [left + .3 + i * (right - left - .6) / max(1, math.ceil((right - left - .6) / 4.8))
                  for i in range(max(1, math.ceil((right - left - .6) / 4.8)) + 1)]
            ys = ([strip_y + config.structural_strip_m / 2] if config.column_rows == 1 else
                  [strip_y + .15, strip_y + config.structural_strip_m - .15])
            config.columns[str(pid)] = [tuple(world(Point(x, yy)).coords[0]) for x in xs for yy in ys]
        y += unit_depth + 5.5
    return dict(planes=[p.model_dump() for p in planes], carport=config.model_dump())


def face_geometry(project, params, plane):
    from .layout import usable_geometry
    base = usable_geometry(project, params)
    shape = Polygon(plane.outline)
    edge = base['edge'].intersection(shape)
    usable = base['usable'].intersection(edge)
    return dict(base, roof=shape, edge=edge, usable=usable,
                area_statistics=dict(base['area_statistics'], roof_area_m2=shape.area, usable_area_m2=usable.area))


def carport_layout(project, params):
    from .models import LayoutParams
    from .pitched import layout
    values = params.model_dump(exclude_unset=True) if isinstance(params, LayoutParams) else dict(params)
    view = project.model_copy(deep=True)
    if values.get('clear_height_m') is not None:
        view.roof.carport.clear_height_m = values['clear_height_m']
    for plane in view.roof.planes:
        if 'tilt_deg' in values:
            plane.slope_deg = values['tilt_deg']
        if values.get('clear_height_m') is not None:
            plane.offset_m = values['clear_height_m'] + view.roof.carport.structure_depth_m
    validate_site(view.roof)
    arguments = dict(values)
    arguments.setdefault('tilt_deg', view.roof.carport.tilt_deg)
    result = layout(view, arguments)
    result.installation_roof = view.roof.model_copy(deep=True)
    result.statistics['canopy_installed_kw'] = result.statistics['dc_kw']
    return result


def facilities(project, design):
    project = effective(project, design)
    roof = project.roof
    area = Polygon(roof.outline)
    if roof.type == 'carport':
        active = {int(m.id.split('-')[0][1:]) for m in design.modules}
        columns = [dict(id=f'P{p.id}-C{i + 1}', plane=p.id, point=[*xy, 0],
                        top_m=plane_elevation(p, xy) - roof.carport.structure_depth_m)
                   for p in roof.planes for i, xy in enumerate(roof.carport.columns.get(str(p.id), []))]
        return dict(kind='carport', bays=[b.model_dump() for b in roof.carport.bays],
                    aisles=[a.model_dump() for a in roof.carport.aisles], columns=columns,
                    beams=beam_geometry(roof), structure_depth_m=roof.carport.structure_depth_m,
                    faces=[dict(id=p.id, points=[[*xy, plane_elevation(p, xy)] for xy in p.outline],
                                clear_height_m=min(plane_elevation(p, xy) for xy in p.outline) - roof.carport.structure_depth_m,
                                active=p.id in active) for p in roof.planes],
                    bay_count=len(roof.carport.bays), canopy_area_m2=sum(Polygon(p.outline).area for p in roof.planes),
                    note='新建车棚；钢量、梁深、柱径与布点均为示意，基础及钢结构须由厂家设计复核')
    if roof.type != 'ground':
        return {}
    groups = {}
    for panel in design.modules:
        col = (panel.col + 1) // 2 if design.params.layout == 'ew' else panel.col
        key = f'R{panel.row}-{panel.orientation}-C{col}'
        groups.setdefault(key, []).append(panel)
    piles = []
    for key, members in groups.items():
        footprint = unary_union([Polygon([p[:2] for p in m.corners]) for m in members]).convex_hull
        a, b = list(footprint.minimum_rotated_rectangle.exterior.coords)[:2]
        center = footprint.centroid
        vector = ((b[0] - a[0]) / 4, (b[1] - a[1]) / 4)
        for number, sign in enumerate((-1, 1), 1):
            xy = (center.x + sign * vector[0], center.y + sign * vector[1])
            nearest = min(members, key=lambda m: Polygon([p[:2] for p in m.corners]).distance(Point(xy)))
            start, across, back = nearest.corners[0], nearest.corners[1], nearest.corners[3]
            u = [across[i] - start[i] for i in range(3)]
            v = [back[i] - start[i] for i in range(3)]
            determinant = u[0] * v[1] - u[1] * v[0]
            along = (u[0] * (xy[1] - start[1]) - u[1] * (xy[0] - start[0])) / determinant
            rail = [[start[i] + across_axis * u[i] + along * v[i] for i in range(3)] for across_axis in (0, 1)]
            horizontal = ((xy[0] - start[0]) * v[1] - (xy[1] - start[1]) * v[0]) / determinant
            top = start[2] + horizontal * u[2] + along * v[2]
            piles.append(dict(id=f'{key}-F{number}', rack=key, point=[*xy, 0], rail=rail,
                              modules=[m.id for m in members], top_m=top))
    inner = area.buffer(-roof.ground.fence_setback_m, join_style=2)
    if 'ground_piles' in design.statistics:
        active = {m.id for m in design.modules}
        piles = [p for p in design.statistics['ground_piles'] if active.intersection(p['modules'])]
    roads = design.statistics.get('roads', [])
    return dict(kind='ground', piles=piles, rack_count=len({p['rack'] for p in piles}), roads=roads,
                road_area_m2=unary_union([Polygon(p) for p in roads]).area,
                fence=[list(p.exterior.coords) for p in getattr(inner, 'geoms', [inner])],
                fence_physical_m=inner.length, fence_quote_m=area.length, land_area_m2=area.area, land_mu=area.area / (2000 / 3),
                note='地桩位置、每架两桩及画面围栏高1.5m为示意；打桩深度、承载与抗拔由厂家按勘察和风荷载设计')


def beam_geometry(roof):
    """Illustrative transverse beams connect columns to faces; dimensions are not structural approval."""
    from shapely.geometry import LineString
    angle = math.radians(roof.carport.direction_deg or 0)
    u, v = (math.cos(angle), math.sin(angle)), (-math.sin(angle), math.cos(angle))
    result = []
    for face in roof.planes:
        shape = Polygon(face.outline)
        span = math.hypot(shape.bounds[2] - shape.bounds[0], shape.bounds[3] - shape.bounds[1]) * 2
        used = set()
        for xy in roof.carport.columns.get(str(face.id), []):
            station = round(xy[0] * u[0] + xy[1] * u[1], 6)
            if station in used:
                continue
            used.add(station)
            ends = [(xy[0] + sign * v[0] * span, xy[1] + sign * v[1] * span) for sign in (-1, 1)]
            parts = shape.intersection(LineString(ends).buffer(.1, cap_style=2))
            for polygon in getattr(parts, 'geoms', [parts]):
                if polygon.geom_type == 'Polygon' and polygon.area > 1e-8:
                    points = [[*p, plane_elevation(face, p)] for p in list(polygon.exterior.coords)[:-1]]
                    result.append(dict(plane=face.id, points=points, depth_m=roof.carport.structure_depth_m))
    return result


def cable_route(roof, modules, points):
    """Same-canopy runs follow its face; across gaps drop to the actual ground datum."""
    output = []
    for (a, first), (b, second) in zip(points, points[1:]):
        aa = list(modules[first].center) if first else [*a, 0]
        bb = list(modules[second].center) if second else [*b, 0]
        same = first and second and first.split('-')[0] == second.split('-')[0]
        if same:
            middle = [bb[0], aa[1], (aa[2] + bb[2]) / 2]
            if roof.type == 'carport':
                plane = next(p for p in roof.planes if f'P{p.id}' == first.split('-')[0])
                gap = aa[2] - plane_elevation(plane, aa)
                middle[2] = plane_elevation(plane, middle) + gap
            if roof.type == 'carport':
                shape = Polygon(plane.outline)
                for left, right in ((aa, middle), (middle, bb)):
                    line = LineString([left[:2], right[:2]])
                    if line.length < 1e-12:
                        continue
                    from .roofplane import vertices
                    cuts = {0.0, line.length, *(line.project(Point(p)) for p in vertices(line.intersection(shape.boundary)))}
                    intervals = sorted(cuts)
                    for start, end in zip(intervals, intervals[1:]):
                        raised = shape.covers(line.interpolate((start + end) / 2))
                        for distance in (start, end):
                            xy = line.interpolate(distance).coords[0]
                            output.append([*xy, plane_elevation(plane, xy) + gap if raised else 0])
            else:
                output.extend([aa, middle, bb])
        else:
            output.extend([aa, [*aa[:2], 0], [bb[0], aa[1], 0], [*bb[:2], 0], bb])
    return output
