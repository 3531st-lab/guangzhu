"""Shared physical roof planes; all elevations are relative to the building eave datum."""
import math
from itertools import combinations

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import split, unary_union

TOLERANCE = .02


def plane_elevation(plane, point):
    bearing = math.radians(plane.slope_azimuth_deg)
    station = lambda p: -p[0] * math.sin(bearing) - p[1] * math.cos(bearing)
    return plane.offset_m + (station(point) - min(map(station, plane.outline))) * math.tan(math.radians(plane.slope_deg))


def member(roof, identifier):
    number = int(identifier.split('-', 1)[0][1:]) if isinstance(identifier, str) else identifier
    return next(p for p in roof.planes if p.id == number)


def elevation(roof, point, plane_id=None):
    if roof.type in ('pitched', 'carport'):
        plane = member(roof, plane_id) if plane_id is not None else min(
            roof.planes, key=lambda p: (Polygon(p.outline).distance(Point(point[:2])), p.id))
        return plane_elevation(plane, point)
    if roof.type != "metal":
        return 0.0
    bearing = math.radians(roof.slope_azimuth_deg)
    uphill = (-math.sin(bearing), -math.cos(bearing))
    station = lambda p: p[0] * uphill[0] + p[1] * uphill[1]
    return (station(point) - min(map(station, roof.outline))) * math.tan(math.radians(roof.slope_deg))


def pieces(geometry):
    if geometry.is_empty:
        return []
    return list(geometry.geoms) if hasattr(geometry, 'geoms') else [geometry]


def vertices(geometry):
    if geometry.is_empty:
        return []
    if hasattr(geometry, 'geoms'):
        return [p for part in geometry.geoms for p in vertices(part)]
    if geometry.geom_type == 'Polygon':
        return list(geometry.exterior.coords) + [p for ring in geometry.interiors for p in ring.coords]
    return list(geometry.coords)


def minimum(roof, footprint, plane_id=None):
    if roof.type != 'pitched':
        return min((elevation(roof, p) for p in vertices(footprint)), default=0)
    planes = [member(roof, plane_id)] if plane_id is not None else roof.planes
    return min((plane_elevation(p, xy) for p in planes
                for xy in vertices(Polygon(p.outline).intersection(footprint))), default=0)


def path3d(roof, points):
    """Split an existing XY route at every face edge; outside spans interpolate eave endpoints."""
    from shapely.ops import nearest_points
    shape = Polygon(roof.outline)
    plane_shapes = [(plane, Polygon(plane.outline)) for plane in roof.planes]
    # GEOS exact boundary intersection can miss a rotated ridge when a route is a
    # few floating-point ulps outside its parallel edge. This numerical tolerance
    # is deliberately far smaller than the separate 2 cm roof seam validation.
    precision = 1e-8
    cross = lambda a, b: a[0] * b[1] - a[1] * b[0]

    def crossings(a, b, c, d):
        direction = (b[0] - a[0], b[1] - a[1])
        edge = (d[0] - c[0], d[1] - c[1])
        delta = (c[0] - a[0], c[1] - a[1])
        run, span = math.hypot(*direction), math.hypot(*edge)
        if span <= 1e-12:
            return []
        determinant = cross(direction, edge)
        if abs(determinant) <= 1e-12 * run * span:
            if abs(cross(delta, direction)) / run > precision:
                return []
            candidates = [sum((p[i] - a[i]) * direction[i] for i in range(2)) / run for p in (c, d)]
        else:
            t, u = cross(delta, edge) / determinant, cross(delta, direction) / determinant
            if not -precision / span <= u <= 1 + precision / span:
                return []
            candidates = [t * run]
        return [min(run, max(0, value)) for value in candidates if -precision <= value <= run + precision]

    output = []
    for a, b in zip(points, points[1:]):
        segment = LineString([a[:2], b[:2]])
        if segment.length < 1e-12:
            continue
        distances = {0.0, segment.length}
        for plane, _ in plane_shapes:
            for c, d in zip(plane.outline, plane.outline[1:] + plane.outline[:1]):
                distances.update(crossings(a, b, c, d))
        stops = []
        for distance in sorted(distances):
            if not stops or distance - stops[-1] > precision:
                stops.append(distance)
        stops[-1] = segment.length
        coordinates = [segment.interpolate(d).coords[0] for d in stops]
        for left, right in zip(coordinates, coordinates[1:]):
            middle = Point((left[0] + right[0]) / 2, (left[1] + right[1]) / 2)
            plane = min(plane_shapes, key=lambda pair: (
                0 if pair[1].distance(middle) <= precision else pair[1].distance(middle), pair[0].id))[0]
            inside = shape.distance(middle) <= precision
            for point in (left, right):
                anchor = point if shape.distance(Point(point)) <= precision else nearest_points(shape, Point(point))[0].coords[0]
                height = plane_elevation(plane, anchor) if inside else elevation(roof, anchor)
                value = [*point, height]
                if not output or math.dist(output[-1], value) > 1e-9:
                    output.append(value)
    return output


def parapet_faces(roof):
    """Shared render/ray faces; heights follow each actual exterior roof span."""
    if roof.parapet_segments is None:
        runs = [(i, 0, 1, roof.parapet_height_m) for i in range(len(roof.outline))]
    else:
        runs = [(s.edge_index, s.start_ratio, s.end_ratio, s.height_m) for s in roof.parapet_segments]
    faces = []
    for index, start, end, height in runs:
        if height <= 0:
            continue
        a, b = roof.outline[index], roof.outline[(index + 1) % len(roof.outline)]
        points = [[a[j] + (b[j] - a[j]) * ratio for j in range(2)] for ratio in (start, end)]
        boundary = path3d(roof, points) if roof.type == 'pitched' else [[*p, elevation(roof, p)] for p in points]
        for first, last in zip(boundary, boundary[1:]):
            if math.dist(first[:2], last[:2]) <= 1e-9:
                continue
            faces.append([first, last, [*last[:2], last[2] + height], [*first[:2], first[2] + height]])
    return faces


def scene_geometry(roof, added_keepouts=()):
    """Serializable render geometry from the same validated surfaces used by rays."""
    from .models import obstacle_polygon, Keepout
    faces = [dict(id=p.id, material=p.material, outline=p.outline,
                  **({'part_id': p.part_id} if p.part_id is not None else {}),
                  points=[[*xy, plane_elevation(p, xy)] for xy in p.outline]) for p in roof.planes]
    ring = [*roof.outline, roof.outline[0]]
    boundary = path3d(roof, ring) if roof.type in ('pitched', 'carport') and roof.planes else [
        [*p, elevation(roof, p)] for p in ring]
    walls = [[a, b, [*b[:2], -roof.height_m], [*a[:2], -roof.height_m]] for a, b in zip(boundary, boundary[1:])
             if math.dist(a[:2], b[:2]) > 1e-9]
    steps = step_walls(roof)
    walls.extend(steps)
    keepouts, keepout_faces = [], []
    for zone in [*roof.keepouts, *[Keepout.model_validate(k) for k in added_keepouts]]:
        for plane in roof.planes:
            if zone.plane_id is not None and zone.plane_id != plane.id:
                continue
            for shape in pieces(Polygon(plane.outline).intersection(Polygon(zone.polygon))):
                if shape.geom_type == 'Polygon':
                    points = [[*p, plane_elevation(plane, p) + .02] for p in list(shape.exterior.coords)[:-1]]
                    keepouts.append(points)
                    keepout_faces.append(dict(id=zone.id, points=points))
    return dict(faces=faces, boundary=boundary, walls=walls, step_walls=steps, keepouts=keepouts,
                keepout_faces=keepout_faces, parapets=parapet_faces(roof),
                obstacle_bases={o.id: minimum(roof, obstacle_polygon(o), o.plane_id) for o in roof.obstacles})


def _matched_edges(first, second):
    """Pair near boundary runs, including narrow tapered seams, with one total tolerance."""
    common = Polygon(first.outline).boundary.intersection(Polygon(second.outline).boundary)
    for a, b in zip(first.outline, first.outline[1:] + first.outline[:1]):
        length = math.dist(a, b)
        unit = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        station = lambda p: (p[0] - a[0]) * unit[0] + (p[1] - a[1]) * unit[1]
        normal = lambda p: (p[0] - a[0]) * unit[1] - (p[1] - a[1]) * unit[0]
        for c, d in zip(second.outline, second.outline[1:] + second.outline[:1]):
            if abs(normal(c) - normal(d)) > 1e-7:
                near = LineString([c, d]).intersection(LineString([a, b]).buffer(TOLERANCE + 1e-9, cap_style=2))
                # Different edges near an exact shared corner are not another seam.
                near = near.difference(common.buffer(TOLERANCE + 1e-9))
                for part in pieces(near):
                    if part.geom_type != 'LineString':
                        continue
                    right = [part.coords[0], part.coords[-1]]
                    stations = [min(length, max(0, station(p))) for p in right]
                    if abs(stations[1] - stations[0]) <= 1e-8:
                        continue
                    left = [(a[0] + t * unit[0], a[1] + t * unit[1]) for t in stations]
                    yield left, right
                continue
            if abs(normal(c)) > TOLERANCE + 1e-9:
                continue
            low, high = max(0, min(station(c), station(d))), min(length, max(station(c), station(d)))
            if high - low <= 1e-8:
                continue
            left = [(a[0] + t * unit[0], a[1] + t * unit[1]) for t in (low, high)]
            edge = LineString([c, d])
            right = [edge.interpolate(edge.project(Point(p))).coords[0] for p in left]
            yield left, right


def seams(roof):
    output = []
    for a, b in combinations(roof.planes, 2):
        for left, right in _matched_edges(a, b):
            points = [((p[0] + q[0]) / 2, (p[1] + q[1]) / 2) for p, q in zip(left, right)]
            output.append((a, b, LineString(points)))
    return output


def step_walls(roof):
    """Vertical shared walls between explicit volumes, split where height order changes."""
    if not roof.parts:
        return []
    output = []
    part_ids = {part.id for part in roof.parts}
    for a, b, edge in seams(roof):
        if a.part_id not in part_ids or b.part_id not in part_ids or a.part_id == b.part_id:
            continue
        left, right = list(edge.coords)
        delta = [plane_elevation(a, p) - plane_elevation(b, p) for p in (left, right)]
        stops = [left, right]
        if delta[0] * delta[1] < 0:
            ratio = delta[0] / (delta[0] - delta[1])
            stops.insert(1, tuple(x + ratio * (y - x) for x, y in zip(left, right)))
        for start, end in zip(stops, stops[1:]):
            heights = [(plane_elevation(a, p), plane_elevation(b, p)) for p in (start, end)]
            if max(abs(x - y) for x, y in heights) <= 1e-9:
                continue
            points = [[*start, min(heights[0])], [*end, min(heights[1])],
                      [*end, max(heights[1])], [*start, max(heights[0])]]
            clean = []
            for point in points:
                if not clean or math.dist(point, clean[-1]) > 1e-9:
                    clean.append(point)
            if math.dist(clean[0], clean[-1]) <= 1e-9:
                clean.pop()
            if len(clean) >= 3:
                output.append(clean)
    return output


def validate_planes(roof):
    from .models import GzError
    fail = lambda text: GzError('ROOF_PLANES_INVALID', text, '检查坡面外形、坡向和最低边偏移，容差为2厘米')
    if not roof.planes or len({p.id for p in roof.planes}) != len(roof.planes):
        raise fail('整栋需要坡面，且坡面编号不能重复')
    part_ids = {part.id for part in roof.parts}
    if any(p.part_id is not None and p.part_id not in part_ids for p in roof.planes):
        raise fail('坡面引用了不存在的屋顶部分')
    boundary = Polygon(roof.outline)
    shapes = [Polygon(p.outline) for p in roof.planes]
    # Maximum local thickness is the diameter of an inscribed disk in a residual.
    thick = lambda shape: not shape.buffer(-TOLERANCE / 2 - 1e-9).is_empty
    if thick(boundary.difference(unary_union(shapes))):
        raise fail('坡面之间留下超过2厘米的缺口')
    for shape in shapes:
        if not boundary.buffer(TOLERANCE + 1e-9).covers(shape):
            raise fail('坡面超出整栋外形超过2厘米')
    for a, b in combinations(shapes, 2):
        if thick(a.intersection(b)):
            raise fail('坡面重叠宽度超过2厘米')
    for a, b in combinations(roof.planes, 2):
        # A declared volume boundary is an intentional step; ordinary ridge seams retain 2 cm validation.
        if a.part_id in part_ids and b.part_id in part_ids and a.part_id != b.part_id:
            continue
        intersection = Polygon(a.outline).boundary.intersection(Polygon(b.outline).boundary)
        samples = [(p, p) for p in vertices(intersection)]
        samples += [(p, q) for left, right in _matched_edges(a, b) for p, q in zip(left, right)]
        if any(abs(plane_elevation(a, p) - plane_elevation(b, q)) > TOLERANCE + 1e-9 for p, q in samples):
            raise fail(f'P{a.id}与P{b.id}的公共边高度差超过2厘米')


def generate_parts(parts):
    """Compile connected non-overlapping flat/gable volumes into one canonical roof."""
    from .models import GzError, RoofPart, RoofPlane, ccw, validated
    fail = lambda text: GzError('ROOF_PARTS_INVALID', text, '各部分须相邻、不重叠、不留内孔；填写独立檐口高度和坡度')
    if not isinstance(parts, (list, tuple)) or not 1 <= len(parts) <= 32:
        raise fail('组合屋顶需要1至32个部分')
    parts = [validated(RoofPart, part, 'ROOF_PARTS_INVALID') for part in parts]
    if len({part.id for part in parts}) != len(parts):
        raise fail('屋顶部分编号不能重复')
    shapes = [Polygon(part.outline) for part in parts]
    if any(a.intersection(b).area > 1e-8 for a, b in combinations(shapes, 2)):
        raise fail('屋顶部分的平面轮廓不能重叠')
    boundary = unary_union(shapes)
    if boundary.geom_type != 'Polygon' or not boundary.is_valid or boundary.interiors:
        raise fail('屋顶部分须通过公共边相连，合并后不能有缺口或内孔')
    datum = min(part.eave_height_m for part in parts)
    reserved = [identifier for part in parts for identifier in part.plane_ids]
    if len(set(reserved)) != len(reserved):
        raise fail('不同屋顶部分不能使用相同坡面编号')
    next_id = max(reserved, default=0) + 1
    planes = []
    for part in parts:
        if part.kind == 'flat':
            generated = [RoofPlane(id=1, outline=part.outline, slope_deg=0, slope_azimuth_deg=180,
                                   material=part.material).model_dump()]
        else:
            generated = generate(part.outline, dict(kind='gable', slope_deg=part.slope_deg,
                                 material=part.material, ridge_mode=part.ridge_mode))['planes']
        assigned = part.plane_ids[:len(generated)]
        while len(assigned) < len(generated):
            assigned.append(next_id)
            next_id += 1
        part.plane_ids = assigned
        for identifier, item in zip(assigned, generated):
            item.update(id=identifier, part_id=part.id, offset_m=item['offset_m'] + part.eave_height_m - datum,
                        load_capacity_kn_m2=part.load_capacity_kn_m2, load_verified=part.load_verified)
            planes.append(item)
    return dict(parts=[part.model_dump() for part in parts], planes=planes,
                outline=ccw(list(boundary.exterior.coords)[:-1]), height_m=datum)


def generate(outline, settings):
    """Generate exact affine surfaces, retaining clipping offsets and user input."""
    from .models import GzError, PitchedSettings, RoofPlane, ccw, validated
    settings = validated(PitchedSettings, settings, 'PITCHED_INPUT_INVALID')
    shape = Polygon(ccw(outline))
    planes = []
    beta = math.tan(math.radians(settings.slope_deg))
    def add(polygon, angle, slope=None, material=None, height=None):
        for part in pieces(polygon):
            if part.geom_type != 'Polygon' or part.area <= 1e-9:
                continue
            points = ccw(list(part.exterior.coords)[:-1])
            offset = min(height(p) for p in points) if height else 0
            planes.append(RoofPlane(id=len(planes) + 1, outline=points, slope_deg=slope or settings.slope_deg,
                                    slope_azimuth_deg=angle % 360, offset_m=max(0, offset), material=material or settings.material))
    rectangle = list(shape.minimum_rotated_rectangle.exterior.coords)[:-1]
    edges = [(math.dist(a, b), a, b) for a, b in zip(rectangle, rectangle[1:] + rectangle[:1])]
    length, origin, end = max(edges, key=lambda row: row[0])
    ux, uy = (end[0] - origin[0]) / length, (end[1] - origin[1]) / length
    width = min(row[0] for row in edges)
    world = lambda x, y: (origin[0] + x * ux - y * uy, origin[1] + x * uy + y * ux)
    if not shape.covers(Point(world(length / 2, width / 2))):
        ux, uy = -ux, -uy
        origin = end
    bearing = lambda x, y: math.degrees(math.atan2(x, y)) % 360
    extra = {}
    if settings.kind == 'single':
        add(shape, settings.azimuth_deg)
    elif settings.kind == 'gable':
        center = shape.centroid
        dx, dy = (ux, uy) if settings.ridge_mode == 'long' else (-uy, ux)
        a, b = settings.ridge or ((center.x, center.y), (center.x + dx, center.y + dy))
        dx, dy = b[0] - a[0], b[1] - a[1]
        norm = math.hypot(dx, dy)
        if norm <= 1e-9:
            raise GzError('RIDGE_INVALID', '屋脊需要两个不同点', '重新画屋脊')
        span = (length + width) * 10
        line = LineString([(a[0] - dx / norm * span, a[1] - dy / norm * span),
                           (a[0] + dx / norm * span, a[1] + dy / norm * span)])
        halves = pieces(split(shape, line))
        if len(halves) != 2 or any(p.area <= 1e-8 for p in halves):
            raise GzError('RIDGE_INVALID', '屋脊须把屋顶分成两个完整坡面', '调整屋脊位置')
        widths = [max(line.distance(Point(p)) for p in part.exterior.coords) for part in halves]
        peak = max(widths) * beta
        for part in halves:
            side = dx * (part.centroid.y - a[1]) - dy * (part.centroid.x - a[0])
            add(part, bearing(-dy, dx) if side > 0 else bearing(dy, -dx), height=lambda p: peak - line.distance(Point(p)) * beta)
    elif settings.kind == 'hip':
        if shape.symmetric_difference(shape.minimum_rotated_rectangle).area > 1e-7:
            raise GzError('HIP_RECTANGLE_REQUIRED', '四坡需要矩形外形', '改用矩形或其他屋面类型')
        left, right = width / 2, length - width / 2
        for points, direction in [([(0, 0), (length, 0), (right, left), (left, left)], (uy, -ux)),
                                   ([(length, width), (0, width), (left, left), (right, left)], (-uy, ux)),
                                   ([(0, width), (0, 0), (left, left)], (-ux, -uy)),
                                   ([(length, 0), (length, width), (right, left)], (ux, uy))]:
            clean = list(dict.fromkeys(world(x, y) for x, y in points))
            add(Polygon(clean), bearing(*direction))
    else:
        angle = math.radians(settings.azimuth_deg)
        up = (-math.sin(angle), -math.cos(angle))
        across = (up[1], -up[0])
        station = lambda p: p[0] * up[0] + p[1] * up[1]
        low, high = min(map(station, outline)), max(map(station, outline))
        count = max(1, math.floor((high - low) / settings.tooth_width_m + .5)) if settings.tooth_width_m else settings.teeth
        pitch = (high - low) / count
        glass = math.tan(math.radians(settings.glass_deg))
        gentle = pitch * glass / (beta + glass)
        cross_values = [p[0] * across[0] + p[1] * across[1] for p in outline]
        left, right = min(cross_values) - 1, max(cross_values) + 1
        def strip(start, finish):
            return Polygon([(s * up[0] + t * across[0], s * up[1] + t * across[1])
                            for s, t in [(start, left), (finish, left), (finish, right), (start, right)]]).intersection(shape)
        for tooth in range(count):
            start = low + tooth * pitch
            add(strip(start, start + gentle), settings.azimuth_deg, height=lambda p: (station(p) - start) * beta)
            add(strip(start + gentle, start + pitch), settings.azimuth_deg + 180, settings.glass_deg, 'glass',
                height=lambda p: (start + pitch - station(p)) * glass)
        extra = dict(actual_teeth=count, actual_pitch_m=pitch)
    return dict(planes=[p.model_dump() for p in planes], **extra)
