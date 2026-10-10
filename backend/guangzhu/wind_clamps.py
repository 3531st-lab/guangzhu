"""Module-owned clamp sites on illustrative seams; all distances use roof-plane 3D."""
import math

from shapely.affinity import affine_transform
from shapely.geometry import LineString, Polygon

from .roofplane import elevation, member


def arrange(roof, panel, demand_kn, settings, occupied):
    plane = member(roof, panel.id) if roof.type == 'pitched' else None
    capacity = settings.get('clamp_capacity_kn', .8)
    seam_pitch = settings.get('seam_spacing_m', .5)
    angle = math.radians(settings.get('seam_azimuth_deg') if settings.get('seam_azimuth_deg') is not None
                         else (plane or roof).slope_azimuth_deg)
    along = (math.sin(angle), math.cos(angle))
    across = (along[1], -along[0])
    minimum = settings.get('clamp_min_spacing_m', .2)
    maximum = settings.get('clamp_max_spacing_m', 1.2)
    margin = settings.get('clamp_edge_m', .1)
    offset = settings.get('seam_offset_m', 0)
    polygon = Polygon([p[:2] for p in panel.corners])
    local = affine_transform(polygon, [*across, *along, 0, 0])
    inner = local.buffer(-margin, join_style=2)
    required_force = math.ceil(demand_kn / capacity)
    def world(x, y):
        point = (x * across[0] + y * along[0], x * across[1] + y * along[1])
        return (*point, elevation(roof, point, plane.id if plane else None))
    def clear(point, existing):
        return all(math.dist(point, other) >= minimum - 1e-8 for other in existing)
    available, lines = [], []
    if not inner.is_empty:
        xmin, ymin, xmax, ymax = inner.bounds
        for index in range(math.ceil((xmin - offset) / seam_pitch), math.floor((xmax - offset) / seam_pitch) + 1):
            x = offset + index * seam_pitch
            segment = inner.intersection(LineString([(x, ymin - 1), (x, ymax + 1)]))
            if segment.is_empty or segment.geom_type != 'LineString':
                continue
            start, end = segment.bounds[1], segment.bounds[3]
            length = math.dist(world(x, start), world(x, end))
            intervals = max(1, math.floor(length / minimum))
            points = [world(x, start + (end - start) * i / intervals) for i in range(intervals + 1)]
            points = [p for p in points if clear(p, occupied)]
            indices = []
            for point in points:
                if clear(point, available):
                    indices.append(len(available))
                    available.append(point)
            full = local.intersection(LineString([(x, local.bounds[1] - 1), (x, local.bounds[3] + 1)]))
            lines.append((x, indices, world(x, full.bounds[1]), world(x, full.bounds[3])))
    selected = set()
    for _, indices, _, _ in lines:
        if not indices:
            continue
        selected.add(indices[0])
        current = 0
        while current < len(indices) - 1:
            next_index = current + 1
            while next_index + 1 < len(indices) and math.dist(available[indices[current]], available[indices[next_index + 1]]) <= maximum:
                next_index += 1
            selected.add(indices[next_index])
            current = next_index
    required = max(required_force, len(selected), 2)
    for index in range(len(available)):
        if len(selected) >= required:
            break
        selected.add(index)
    gaps = []
    for _, indices, start, end in lines:
        points = [available[i] for i in indices if i in selected]
        if not points:
            gaps.append(math.inf)
            continue
        gaps.extend(math.dist(a, b) for a, b in zip(points, points[1:]))
        gaps.extend([2 * math.dist(start, points[0]), 2 * math.dist(end, points[-1])])
    xs = [x for x, indices, _, _ in lines if any(i in selected for i in indices)]
    if xs:
        xmin, ymin, xmax, ymax = local.bounds
        gaps.extend(math.dist(world(a, (ymin + ymax) / 2), world(b, (ymin + ymax) / 2)) for a, b in zip(xs, xs[1:]))
        gaps.extend([2 * math.dist(world(xmin, 0), world(xs[0], 0)), 2 * math.dist(world(xmax, 0), world(xs[-1], 0))])
    worst = max(gaps, default=math.inf)
    points = [available[i] for i in sorted(selected)]
    occupied.update(points)
    passed = required <= len(available) and len(points) >= required and worst <= maximum + 1e-8
    return dict(required=required, force_required=required_force, available=len(available), adopted=len(points), points=points,
                demand_kn=demand_kn, capacity_kn=capacity, passed=passed, max_actual_spacing_m=worst if math.isfinite(worst) else None,
                max_spacing_m=maximum, min_spacing_m=minimum, seam_spacing_m=seam_pitch, seam_azimuth_deg=math.degrees(angle),
                seam_offset_m=offset, edge_m=margin, basis='示意设计抗拔力；非S-5特定ASD组合；模块专属点，不共享承载力',
                note='示意板缝/间距/安装边距，现场与厂家核对；相邻板点位去重并保持最小距离',
                hint='换抗拔力更大的夹具，或请厂家复核' if not passed else '需厂家核对板型、厚度、扭矩及屋面到主体的连接')
