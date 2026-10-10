"""Illustrative livestock use; ground sunlight is geometric area, not crop growth."""
import math
from calendar import monthrange

import numpy as np
import pandas as pd
from shapely.geometry import Polygon
from shapely.ops import unary_union

HEIGHTS = {'sheep': 1.5, 'cow': 2.5}
TITLES = {'barn': '养殖场棚顶', 'grazing': '牧光互补'}
CORROSION = ('镀铝锌镁夹具及导轨为示意选型，价格比普通件高20%；'
             '材料氨水试验不等于整套夹具耐氨认证，螺栓、切边、异种金属及安装须厂家核实。')
LAND = ('自然资办发〔2023〕12号：新方阵不得占用任何耕地、基本草原；'
        '牧草地及复合利用须当地自然资源和林草部门认定。办草字〔2023〕126号的降雨分区高度不是牛羊统一高度。')
METHOD = ('2023年本地每月15日逐小时中点，太阳高度>0；真实面投影到地坪z=0，'
          '全部阴影并集裁原场地，按每月天数及1小时时长加权；几何直射受光面积占比，非PAR或产草量。')


def clearance(roof, zone, fallback):
    if zone.clearance_m is not None:
        return zone.clearance_m
    return 1.0 if roof.use == 'barn' and zone.preset else fallback


def fan_curve(monthly_kwh, stamps):
    output = []
    for stamp in stamps:
        day = 1 if 6 <= stamp.month <= 9 else .3 if stamp.month in (12, 1, 2) else .6
        denominator = monthrange(stamp.year, stamp.month)[1] * 12 * (day + .2)
        output.append(monthly_kwh * (day if 8 <= stamp.hour < 20 else .2) / denominator)
    return output


def shadow_area(scene, vector, site):
    """Union projected physical faces and solid obstacle bases, clipped to original land."""
    vector = np.asarray(vector)
    if vector[2] <= 0:
        return None
    shapes = list(scene.bases.values())
    for face in scene.faces:
        vertices = np.asarray(face)
        projected = vertices[:, :2] - vertices[:, 2, None] * vector[:2] / vector[2]
        shape = Polygon(projected)
        if shape.area > 1e-10:
            shapes.append(shape if shape.is_valid else shape.buffer(0))
    return unary_union(shapes).intersection(site).area


def light_totals(samples, area):
    """samples are transient (month, shadow m², days); no hourly payload is returned."""
    months = []
    for month in range(1, 13):
        selected = [(shadow, days) for m, shadow, days in samples if m == month]
        hours = sum(days for _, days in selected)
        shaded = math.fsum(shadow * days for shadow, days in selected)
        months.append(dict(month=month, daylight_samples=len(selected), represented_hours=hours,
                           shadow_m2_hours=shaded, sun_pct=100 * (1 - shaded / (area * hours)) if hours else None))
    hours = sum(row['represented_hours'] for row in months)
    shade = math.fsum(row['shadow_m2_hours'] for row in months)
    return dict(sun_pct=100 * (1 - shade / (area * hours)) if hours else None, site_area_m2=area,
                represented_hours=hours, months=months, method=METHOD, sample_interval_hours=1, weighted_by_month_days=True)


def ground_light(project, design):
    from .installation import effective
    from .shading_geometry import build_scene, sun_vector
    from .solar import sun_position
    project = effective(project, design)
    scene = build_scene(project, design)
    site = Polygon(project.roof.outline)
    times = pd.DatetimeIndex([pd.Timestamp(year=2023, month=m, day=15, hour=h, minute=30, tz=project.site.timezone)
                              for m in range(1, 13) for h in range(24)])
    positions = sun_position(times, project.site.lat, project.site.lon)
    samples = []
    for stamp, position in positions.iterrows():
        if position.elevation > 0:
            shadow = shadow_area(scene, sun_vector(position.elevation, position.azimuth), site)
            samples.append((stamp.month, shadow, monthrange(2023, stamp.month)[1]))
    return light_totals(samples, site.area)


def facts(project, design):
    roof = project.roof
    if roof.use is None:
        return None
    result = dict(use=roof.use, title=TITLES[roof.use], version=design.version)
    if roof.use == 'barn':
        result.update(corrosion=CORROSION, keepouts=[
            dict(id=k.id, label=k.label, preset=k.preset, clearance_m=clearance(roof, k, design.params.keepout_clearance_m))
            for k in [*roof.keepouts, *design.added_keepouts] if k.preset],
            fan_note='养殖场风机班次4为示意：6–9月白天1、春秋0.6、冬0.3，08–20时；夜间0.2，每月归一。')
    else:
        result.update(animal=roof.animal, animal_min_m=HEIGHTS[roof.animal],
                      actual_min_m=min((p[2] for m in design.modules for p in m.corners), default=None),
                      required_sun_pct=50 if roof.ground_sun_min_pct is None else roof.ground_sun_min_pct,
                      ground_light=ground_light(project, design), land_note=LAND,
                      protection_note='DC导体米含既有1.1富余，仅计一次防啃附加费；穿管或埋地的载流量降容须设计核定。')
    return result
