"""Geometry-only editor helpers. These endpoints do not save roof or project files."""
import math

from fastapi import APIRouter, Request
from pydantic import Field, field_validator
from shapely import affinity
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .models import Point2, Record, ccw

router = APIRouter()


class CrossWalkwaysRequest(Record):
    outline: list[Point2] = Field(min_length=3, max_length=1000)
    width_m: float = Field(default=1.0, gt=0, le=10)
    setback_m: float = Field(default=1.2, ge=0, le=100)
    _outline = field_validator('outline')(ccw)


def cross_walkways(payload: CrossWalkwaysRequest):
    roof = Polygon(payload.outline)
    edges = list(zip(payload.outline, payload.outline[1:] + payload.outline[:1]))
    a, b = max(edges, key=lambda edge: math.dist(*edge))
    angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    origin = roof.centroid.coords[0]
    local = affinity.rotate(roof, -angle, origin=origin)
    inside = local.buffer(-payload.setback_m, join_style=2)
    if inside.is_empty:
        return dict(polygons=[], width_m=payload.width_m, note='屋顶在当前退距下没有可生成通道的区域，请减小退距或手动画通道。')
    x0, y0, x1, y1 = inside.bounds
    cx, cy, half = (x0 + x1) / 2, (y0 + y1) / 2, payload.width_m / 2
    proposed = unary_union([box(x0, cy - half, x1, cy + half), box(cx - half, y0, cx + half, y1)])
    clipped = inside.intersection(proposed)
    pieces = list(clipped.geoms) if hasattr(clipped, 'geoms') else [clipped]
    polygons = []
    for part in pieces:
        if not isinstance(part, Polygon) or part.area <= 1e-8:
            continue
        restored = affinity.rotate(part, angle, origin=origin)
        # Input roof has no holes; a cross-shaped intersection cannot introduce one.
        if restored.interiors:
            raise ValueError('通道生成结果包含内孔，请改用手动画通道')
        polygons.append([[float(x), float(y)] for x, y in list(restored.exterior.coords)[:-1]])
    return dict(polygons=polygons, width_m=payload.width_m,
                note=f'按实际屋顶边界和退距裁切为{len(polygons)}段；请核实通道连通性、设备避让及项目消防要求。')


@router.post('/api/roof-tools/cross-walkways')
def cross_walkways_endpoint(request: Request, payload: CrossWalkwaysRequest):
    from .api import local_only
    local_only(request)
    return cross_walkways(payload)
