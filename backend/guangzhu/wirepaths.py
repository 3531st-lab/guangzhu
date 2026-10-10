"""Deterministic route candidates; restricted rectilinear paths are not a construction design."""
from functools import lru_cache
import heapq
import math

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import nearest_points, unary_union

from .roofplane import elevation, path3d, vertices

NOTE = ('场地内横竖走线，绕开屋面设备；设备净距0.05m为示意，圆形设备按外接方框保守避让。'
        '禁区、采光带和玻璃面尽量绕行，无法绕开时按桥架跨越计（示意，线长照计）。'
        '固定串成员及MPPT，比较原顺序与最近邻加2-opt候选，取可达且线长较短者；不保证全局最优。'
        '实际桥架、穿管、防火、支撑和施工净距须现场核定。')
CROSSING = 4  # a metre over a keepout, skylight or glass face costs as much as this many metres of detour


def compact(points):
    output = []
    for point in points:
        value = list(point)
        if not output or math.dist(value, output[-1]) > 1e-9:
            output.append(value)
    return output


def distance(points):
    return math.fsum(math.dist(a, b) for a, b in zip(points, points[1:]))


class Planner:
    def __init__(self, roof, design):
        self.roof = roof
        self.modules = {m.id: m for m in design.modules}
        self.boundary = Polygon(roof.outline)
        blocks = []
        for item in roof.obstacles:
            if item.kind == 'cylinder':
                x, y = item.center
                r = item.radius_m
                shape = box(x - r, y - r, x + r, y + r)
            else:
                shape = Polygon(item.footprint)
            blocks.append(shape.buffer(.05, join_style=2))
        # Equipment is a wall for cables. Keepouts, skylight bands and glass faces only cost extra: a band that runs from
        # eave to ridge would otherwise cut the roof into islands that no string could leave.
        zones = [*roof.keepouts, *design.added_keepouts]
        soft = [Polygon(zone.polygon) for zone in zones] + [Polygon(plane.outline) for plane in roof.planes if plane.material == 'glass']
        self.domain = self.boundary.difference(unary_union(blocks))
        self.allowed = self.domain.buffer(1e-8, join_style=2)
        self.soft = unary_union(soft).intersection(self.domain) if soft else Polygon()
        self.inner = self.soft.buffer(-1e-7, join_style=2) if not self.soft.is_empty else self.soft
        points = vertices(self.domain) + vertices(self.soft)
        self.xs = sorted({p[0] for p in points})
        self.ys = sorted({p[1] for p in points})
        self.visible = lru_cache(maxsize=32768)(self.visible)
        self.over = lru_cache(maxsize=32768)(self.over)
        self.xy = lru_cache(maxsize=8192)(self.xy)

    def free(self, point):
        return self.allowed.covers(Point(point)) and not self.inner.covers(Point(point))

    def default_position(self, center):
        edge = self.domain.difference(self.soft).intersection(self.boundary.exterior)
        if edge.is_empty:
            edge = self.domain.intersection(self.boundary.exterior)
        if edge.is_empty:
            edge = self.boundary.exterior
        return list(nearest_points(Point(center), edge)[1].coords[0])

    def visible(self, a, b):
        shape = Point(a) if a == b else LineString([a, b])
        return self.allowed.covers(shape)

    def over(self, a, b):
        """Metres of the straight run a-b that lie on a keepout, skylight or glass face."""
        if a == b or self.inner.is_empty:
            return 0.0
        return LineString([a, b]).intersection(self.inner).length

    def crossing(self, path):
        return math.fsum(self.over(tuple(a[:2]), tuple(b[:2])) for a, b in zip(path, path[1:]))

    def xy(self, a, b):
        if not self.visible(a, a) or not self.visible(b, b):
            return None
        for corner in ((b[0], a[1]), (a[0], b[1])):
            if self.visible(a, corner) and self.visible(corner, b) and not self.over(a, corner) and not self.over(corner, b):
                return compact([a, corner, b])
        xs = sorted(set(self.xs + [a[0], b[0]]))
        ys = sorted(set(self.ys + [a[1], b[1]]))
        start = xs.index(a[0]), ys.index(a[1])
        finish = xs.index(b[0]), ys.index(b[1])
        queue, costs, previous = [(0, 0, start)], {start: 0}, {}
        while queue:
            _, cost, node = heapq.heappop(queue)
            if cost > costs[node] + 1e-9:
                continue
            if node == finish:
                path = [node]
                while path[-1] != start:
                    path.append(previous[path[-1]])
                return compact([(xs[x], ys[y]) for x, y in reversed(path)])
            x, y = node
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                    continue
                p, q = (xs[x], ys[y]), (xs[nx], ys[ny])
                if not self.visible(p, q):
                    continue
                value = cost + math.dist(p, q) + (CROSSING - 1) * self.over(p, q)
                if value + 1e-9 >= costs.get((nx, ny), math.inf):
                    continue
                costs[nx, ny] = value
                previous[nx, ny] = node
                heuristic = abs(q[0] - b[0]) + abs(q[1] - b[1])
                heapq.heappush(queue, (value + heuristic, value, (nx, ny)))
        return self.diagonal(a, b)

    def diagonal(self, a, b):
        """Shortest run between corners when no horizontal/vertical path fits, e.g. a narrow slanted wing of a rotated roof."""
        corners = list(dict.fromkeys(tuple(p) for p in vertices(self.domain)))
        nodes = [a, b, *[p for p in corners if p not in (a, b)]]
        queue, costs, previous = [(0, 0, 0)], {0: 0}, {}
        while queue:
            _, cost, index = heapq.heappop(queue)
            if cost > costs[index] + 1e-9:
                continue
            if index == 1:
                path = [1]
                while path[-1] != 0:
                    path.append(previous[path[-1]])
                return compact([nodes[i] for i in reversed(path)])
            for other in range(len(nodes)):
                if other == index or not self.visible(nodes[index], nodes[other]):
                    continue
                value = cost + math.dist(nodes[index], nodes[other]) + (CROSSING - 1) * self.over(nodes[index], nodes[other])
                if value + 1e-9 < costs.get(other, math.inf):
                    costs[other], previous[other] = value, index
                    heapq.heappush(queue, (value + math.dist(nodes[other], b), value, other))
        return None

    def surface(self, points):
        if self.roof.type == 'pitched' and len(points) > 1:
            return compact(path3d(self.roof, points))
        return [[*p, elevation(self.roof, p)] for p in points]

    def leg(self, a, b, first=None, second=None):
        xy = self.xy(tuple(a[:2]), tuple(b[:2]))
        if xy is None:
            return None
        if self.roof.type not in ('ground', 'carport'):
            return self.surface(xy)
        aa = list(self.modules[first].center) if first else [*a[:2], 0]
        bb = list(self.modules[second].center) if second else [*b[:2], 0]
        same = first and second and first.split('-')[0] == second.split('-')[0]
        if same:
            panel = self.modules[first]
            p, q, _, r = panel.corners
            dx, dy = q[0] - p[0], q[1] - p[1]
            ex, ey = r[0] - p[0], r[1] - p[1]
            determinant = dx * ey - dy * ex
            sx = ((q[2] - p[2]) * ey - (r[2] - p[2]) * dy) / determinant
            sy = (dx * (r[2] - p[2]) - ex * (q[2] - p[2])) / determinant
            raised = [[x, y, p[2] + sx * (x - p[0]) + sy * (y - p[1])] for x, y in xy]
            if self.roof.type == 'ground' or Polygon(next(f for f in self.roof.planes
                    if 'P' + str(f.id) == first.split('-')[0]).outline).covers(LineString(xy)):
                return compact([aa, *raised, bb])
        return compact([aa, *[[*p, 0] for p in xy], bb])

    def string(self, ids, inverter):
        ends = [None, *ids, None]
        points = [inverter, *[self.modules[mid].center[:2] for mid in ids], inverter]
        legs = [self.leg(a, b, first, second) for a, b, first, second in zip(points, points[1:], ends, ends[1:])]
        missing = sum(path is None for path in legs)
        if missing:
            estimate = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(points, points[1:]))
            return dict(path=[], length=estimate, blocked=missing)
        path = compact([point for leg in legs for point in leg])
        return dict(path=path, length=distance(path), blocked=0)

    def optimize(self, ids, inverter):
        original = self.string(ids, inverter)
        remaining, greedy, current = set(ids), [], inverter
        metric = lambda a, b: abs(a[0] - b[0]) + abs(a[1] - b[1])
        while remaining:
            chosen = min(remaining, key=lambda mid: (metric(current, self.modules[mid].center), mid))
            greedy.append(chosen)
            remaining.remove(chosen)
            current = self.modules[chosen].center
        points = lambda order: [inverter, *[self.modules[mid].center for mid in order], inverter]
        for _ in range(4):
            improved = False
            p = points(greedy)
            for i in range(len(greedy) - 1):
                for j in range(i + 1, len(greedy)):
                    before = metric(p[i], p[i + 1]) + metric(p[j + 1], p[j + 2])
                    after = metric(p[i], p[j + 1]) + metric(p[i + 1], p[j + 2])
                    if after + 1e-8 < before:
                        greedy[i:j + 1] = reversed(greedy[i:j + 1])
                        p = points(greedy)
                        improved = True
            if not improved:
                break
        candidate = self.string(greedy, inverter) if greedy != ids else original
        rank = lambda value: (value['blocked'], round(value['length'], 8))
        use = rank(candidate) < rank(original)
        selected = candidate if use else original
        return dict(selected, ids=greedy if use else ids, original=original, changed=use)
