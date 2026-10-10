"""Deterministic flat-roof layout with winter true-solar-time spacing."""

import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import time

import numpy as np
import pandas as pd
import pvlib
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .config import DATA_DIR
from .models import Design, GzError, LayoutParams, Module, obstacle_polygon, validate_project, validated
from .solar import sun_position
from .roofplane import elevation

CAPACITY_NOTE = '冬至 10–14 时不挡，比国标建议的 9–15 时短，早晚前后排有少量遮挡，已算进遮挡损失'


def edge_azimuth(outline):
    points = np.asarray(outline)
    edges = np.roll(points, -1, axis=0) - points
    vector = edges[np.argmax(np.linalg.norm(edges, axis=1))]
    normal = math.degrees(math.atan2(-vector[1], vector[0])) % 360
    return round(min((normal, (normal + 180) % 360), key=lambda value: (abs(value - 180), value)), 8)


def rack_id(project, params):
    if project.roof.type in ('ground', 'carport'):
        return project.equipment.racking
    return 'ballast_ew' if params.layout == 'ew' else project.equipment.racking


def true_solar_times(lon, hours, date="2025-12-21"):
    """UTC instants: true solar = Beijing clock + 4*(lon-120) + SPA EOT minutes."""
    requested = pd.DatetimeIndex(pd.Timestamp(date, tz="Asia/Shanghai") + pd.to_timedelta(hours, unit="h"))
    instants = requested - pd.Timedelta(minutes=4 * (lon - 120))
    for _ in range(3):
        eot = pvlib.solarposition.get_solarposition(instants, 0, lon)["equation_of_time"].to_numpy()
        instants = requested - pd.to_timedelta(4 * (lon - 120) + eot, unit="m")
    return instants.tz_convert("UTC")


def row_spacing(lat, lon, tilt, slope_length, azimuth=180, window=(9, 15), *, orientation_group=False):
    if not 0 <= lat <= 55 or not (0 if orientation_group else 90) <= azimuth <= (360 if orientation_group else 270) or not 0 <= tilt <= 35:
        raise GzError("LAYOUT_PARAMS_INVALID", "场址或组件角度不在本卡支持范围", "使用北纬0至55度、朝向90至270度、倾角0至35度")
    if not 0 <= window[0] < window[1] <= 24 or slope_length <= 0:
        raise GzError("LAYOUT_PARAMS_INVALID", "时间窗口或支架斜长不正确", "填写递增的时间窗口和正的斜面长度")
    count = math.ceil((window[1] - window[0]) * 12) + 1
    hours = np.linspace(*window, count)
    times = true_solar_times(lon, hours)
    sun = sun_position(times, lat, lon)
    elevation, bearing = np.radians(sun.elevation.to_numpy()), np.radians(sun.azimuth.to_numpy())
    if (elevation <= 0).any():
        raise GzError("WINTER_SUN_BELOW_HORIZON", "冬至窗口含太阳尚未升起的时刻", "缩短窗口，避开日出前或日落后")
    beta = math.radians(tilt)
    # Shadow of the height difference projected opposite the facing direction.
    factor = np.maximum(np.cos(bearing - math.radians(azimuth)) / np.tan(elevation), 0)
    gap = float(slope_length * math.sin(beta) * factor.max())
    pitch = slope_length * math.cos(beta) + gap
    return dict(row_spacing_m=pitch, clear_gap_m=gap, gcr=slope_length/pitch,
                winter_sample_count=count, winter_sample_step_minutes=60*(hours[1]-hours[0]),
                winter_first_utc=times[0].isoformat(), winter_last_utc=times[-1].isoformat())


def usable_geometry(project, params):
    project, params = validate_project(project), validated(LayoutParams, params, "LAYOUT_PARAMS_INVALID")
    roof = Polygon(project.roof.outline)
    edge = roof.buffer(-params.edge_setback_m)
    obstacles = [(o.id, obstacle_polygon(o).buffer(params.obstacle_clearance_m)) for o in project.roof.obstacles]
    from .livestock import clearance
    keepouts = [(k.id, Polygon(k.polygon).buffer(clearance(project.roof, k, params.keepout_clearance_m)))
                for k in project.roof.keepouts]
    obstruction = unary_union([p for _, p in obstacles]).intersection(edge)
    excluded = unary_union([p for _, p in keepouts]).intersection(edge).difference(obstruction)
    usable = edge.difference(obstruction.union(excluded))
    return dict(roof=roof, edge=edge, usable=usable, obstacles=obstacles, keepouts=keepouts,
                area_statistics=dict(roof_area_m2=roof.area, usable_area_m2=usable.area,
                                     obstacle_area_m2=obstruction.area, keepout_area_m2=excluded.area))


def _catalog(project, params=None):
    def selected(filename, key, value):
        with (DATA_DIR/"catalog"/filename).open(encoding="utf-8-sig", newline="") as stream:
            rows = [r for r in csv.DictReader(stream) if r[key] == value]
        if len(rows) != 1:
            raise GzError("EQUIPMENT_NOT_FOUND", "组件或支架编号不存在或不唯一", "选用data/catalog中已有的唯一编号")
        return rows[0]
    module = selected("modules.csv", "module_id", project.equipment.module_id)
    rack = selected("racking.csv", "racking_id", rack_id(project, params) if params else project.equipment.racking)
    return module, float(rack["module_gap_m"]), float(rack["lower_edge_height_m"])


def generate_layout(project, params, *, _plane=None):
    project = validate_project(project)
    if project.roof.type == 'carport' and _plane is None:
        from .installation import carport_layout
        return carport_layout(project, params)
    if project.roof.type == 'pitched' and _plane is None:
        from .pitched import layout
        return layout(project, params)
    metal = project.roof.type == "metal" or _plane is not None
    if isinstance(params, LayoutParams) and params.layout == 'ew':
        unset = {'tilt_deg', 'walkway_every_n_rows'} - params.model_fields_set
        params = params.model_dump(exclude=unset)
    elif project.roof.type == 'ground' and isinstance(params, LayoutParams):
        params = params.model_dump(exclude_unset=True)
    else:
        params = params.model_dump() if isinstance(params, LayoutParams) else dict(params)
    if project.roof.type not in ('pitched', 'carport') and (params.get('surface') or params.get('plane_ids') is not None):
        raise GzError('LAYOUT_PARAMS_INVALID', '坡面参数只用于整栋斜屋面', '普通平屋顶和彩钢瓦不要传surface或plane_ids')
    if project.roof.type == 'ground':
        for field in ('road_every', 'road_width_m', 'fence_setback_m'):
            if params.get(field) is not None:
                setattr(project.roof.ground, field, params[field])
        from .installation import validate_site
        validate_site(project.roof)
        params.setdefault('rows_per_rack', 2)
        if params.get('road_every') is not None or 'walkway_every_n_rows' not in params:
            params['walkway_every_n_rows'] = project.roof.ground.road_every
        if params.get('road_width_m') is not None or 'walkway_width_m' not in params:
            params['walkway_width_m'] = project.roof.ground.road_width_m
        params['edge_setback_m'] = max(params.get('edge_setback_m', 1), project.roof.ground.fence_setback_m)
    ew = params.get('layout') == 'ew'
    if project.requirements.structured.max_height_m is not None and not metal:
        from .personal import tilt_bounds
        low, high = tilt_bounds(project, LayoutParams.model_validate(params))
        params.update(tilt_deg=min(max(params.get('tilt_deg', 10 if ew else 25), low), high), rows_per_rack=1)
    if ew:
        if metal or not 5 <= params.get('tilt_deg', 10) <= 15:
            raise GzError('LAYOUT_PARAMS_INVALID', '东西向人字形只用于平屋顶，倾角5–15°', '改用平屋顶和允许的倾角')
        params.setdefault('tilt_deg', 10)
        params.setdefault('walkway_every_n_rows', 4)
        params.update(azimuth_deg=270, rows_per_rack=2)
    elif params.get('align'):
        params['azimuth_deg'] = edge_azimuth(project.roof.outline) if params['align'] == 'edge' else 180
    if metal:
        params = params.model_dump() if isinstance(params, LayoutParams) else dict(params)
        surface = _plane or project.roof
        params.update(tilt_deg=surface.slope_deg, azimuth_deg=surface.slope_azimuth_deg, rows_per_rack=1,
                      winter_window_hours=[9, 15])
        if _plane is not None:
            params.update(surface=True, align=None)
    params = validated(LayoutParams, params, "LAYOUT_PARAMS_INVALID")
    if params.extra_row_gap_m is not None and project.roof.type != 'ground':
        raise GzError('LAYOUT_PARAMS_INVALID', '附加排距只用于地面安装', '棚顶按真实坡面平铺')
    module, seam, height = _catalog(project, params)
    if project.roof.type == 'ground':
        height = params.lower_edge_m if params.lower_edge_m is not None else project.roof.ground.lower_edge_m
    long, short = float(module["length_m"]), float(module["width_m"])
    slope, width = (long, short) if params.orientation == "portrait" else (short, long)
    length = params.rows_per_rack*slope + (params.rows_per_rack-1)*seam
    spacing = (dict(row_spacing_m=length * math.cos(math.radians(params.tilt_deg)) + seam, clear_gap_m=seam,
                    gcr=length / (length * math.cos(math.radians(params.tilt_deg)) + seam), mount="flush") if metal else
               row_spacing(project.site.lat, project.site.lon, params.tilt_deg, length, params.azimuth_deg, params.winter_window_hours))
    if ew:
        footprint = length * math.cos(math.radians(params.tilt_deg))
        required = max(row_spacing(project.site.lat, project.site.lon, params.tilt_deg, slope, azimuth,
                                  params.winter_window_hours)['row_spacing_m'] for azimuth in (90, 270))
        spacing.update(row_spacing_m=max(footprint + seam, required), clear_gap_m=max(seam, required - footprint))
        spacing.update(gcr=length / spacing['row_spacing_m'], pair_width_m=footprint)
    if params.extra_row_gap_m is not None:
        spacing['row_spacing_m'] += params.extra_row_gap_m
        spacing['clear_gap_m'] += params.extra_row_gap_m
        spacing['gcr'] = length / spacing['row_spacing_m']
    pitch, gap = spacing["row_spacing_m"], spacing["clear_gap_m"]
    beta, bearing = math.radians(params.tilt_deg), math.radians(params.azimuth_deg)
    right, back = np.array([-math.cos(bearing), math.sin(bearing)]), np.array([-math.sin(bearing),-math.cos(bearing)])
    basis = np.stack([right, back])
    geometry = usable_geometry(project, params)
    if _plane is not None:
        from .pitched import geometry as face_geometry
        if project.roof.type == 'carport':
            from .installation import face_geometry
        geometry = face_geometry(project, params, _plane)
    tolerance_region = geometry["usable"].buffer(0.001)
    shapely.prepare(tolerance_region)
    local = np.array((_plane or project.roof).outline) @ basis.T
    cmin, vmin = local.min(axis=0)
    cmax, vmax = local.max(axis=0)
    column_pitch = width + seam
    tile = np.array([[0,0],[width,0],[width,slope*math.cos(beta)],[0,slope*math.cos(beta)]])
    tier_offsets = np.arange(params.rows_per_rack)*(slope+seam)*math.cos(beta)

    def trial(column_offset, row_offset, record=False):
        columns = np.arange(cmin+column_offset, cmax+1e-8, column_pitch)
        v, occupied_rows, accepted, rejected = vmin+row_offset, 0, [], []
        candidate_row = 0
        while v <= vmax+1e-8:
            candidate_row += 1
            base = np.empty((len(columns),params.rows_per_rack,2))
            base[:,:,0], base[:,:,1] = columns[:,None], v+tier_offsets[None,:]
            corners = (base[:,:,None,:]+tile) @ basis
            polygons = shapely.polygons(corners.round(3).reshape(-1,4,2))
            valid = shapely.covers(tolerance_region,polygons).reshape(len(columns),-1).all(axis=1)
            if valid.any():
                occupied_rows += 1
                for col, index in enumerate(np.flatnonzero(valid),1):
                    accepted.append((occupied_rows,col,columns[index],v))
            if record and (~valid).any():
                reasons = np.full(len(columns), "", dtype=object)
                edge_failed = ~shapely.covers(geometry["edge"].buffer(0.001),polygons).reshape(len(columns),-1).all(axis=1)
                reasons[edge_failed] = "edge"
                for kind in ["obstacles","keepouts"]:
                    prefix = "obstacle" if kind=="obstacles" else "keepout"
                    for identifier, polygon in sorted(geometry[kind]):
                        blocked = shapely.intersects(polygons,polygon.buffer(-0.001)).reshape(len(columns),-1).any(axis=1)
                        reasons[(reasons=="") & blocked] = prefix+":"+identifier
                for index in np.flatnonzero(~valid):
                    rejected.append(dict(row_candidate=candidate_row,col_candidate=int(index)+1,
                                         position_xy=(np.array([columns[index],v]) @ basis).round(3).tolist(),
                                         reason=str(reasons[index] or "edge")))
            aisle = max(gap,params.walkway_width_m)-gap if valid.any() and params.walkway_every_n_rows and occupied_rows%params.walkway_every_n_rows==0 else 0
            v += pitch + aisle
        return accepted, rejected

    # Five phases plus their reflected partners make the candidate set closed
    # under an east-west mirror, even when roof width is not a pitch multiple.
    seeds = np.linspace(0,column_pitch,6)[:-1]
    phases = sorted(set(float(x) for x in np.r_[seeds,(cmax-cmin-width-seeds)%column_pitch]))
    best, choice = -1, (0.0,0.0)
    for column_offset in phases:
        for row_offset in np.linspace(0,pitch,6)[:-1]:
            count = len(trial(column_offset,float(row_offset))[0])
            if count > best:
                best, choice = count, (column_offset,float(row_offset))
    accepted, rejected = trial(*choice,record=True)
    roads = []
    if project.roof.type == 'ground' and params.walkway_every_n_rows:
        from shapely.geometry import box
        from shapely.affinity import affine_transform
        stations = sorted({(row, v) for row, _, _, v in accepted})
        for (row, v), _next in zip(stations, stations[1:]):
            if row % params.walkway_every_n_rows == 0:
                front = v + length * math.cos(beta)
                strip = box(cmin, front, cmax, front + params.walkway_width_m)
                strip = affine_transform(strip, [right[0], back[0], right[1], back[1], 0, 0])
                clipped = strip.intersection(geometry['usable'])
                from shapely.ops import triangulate
                pieces = list(getattr(clipped, 'geoms', [clipped]))
                for polygon in pieces:
                    if polygon.geom_type != 'Polygon' or polygon.area <= 0:
                        continue
                    clear = [p for p in triangulate(polygon) if polygon.covers(p)] if polygon.interiors else [polygon]
                    roads.extend(list(p.exterior.coords)[:-1] for p in clear)
        geometry['usable'] = geometry['usable'].difference(unary_union([Polygon(p) for p in roads]))
        geometry['area_statistics']['usable_area_m2'] = geometry['usable'].area
    modules = []
    for row,col,c,v in accepted:
        for tier in range(1,params.rows_per_rack+1):
            along = v+(tier-1)*(slope+seam)*math.cos(beta)
            xy = (tile+np.array([c,along])) @ basis
            z0 = height+(tier-1)*(slope+seam)*math.sin(beta)
            corners = np.c_[xy,[z0,z0,z0+slope*math.sin(beta),z0+slope*math.sin(beta)]]
            if metal:
                corners[:, 2] = [elevation(project.roof, point, _plane.id if _plane else None) + height for point in xy]
            azimuth, number, level = params.azimuth_deg, col, tier
            if ew:
                number, level = 2 * col - 2 + tier, 1
                if tier == 2:
                    corners = corners[[2, 3, 0, 1]]
                    azimuth = 90
                corners[:, 2] = [height, height, height + slope * math.sin(beta), height + slope * math.sin(beta)]
            prefix = f'P{_plane.id}-' if _plane else ''
            precision = 9 if metal or project.roof.type == 'ground' else 3
            modules.append(Module(id=f"{prefix}R{row:02d}-{level}-C{number:03d}",row=row,tier=level,col=number,
                                  center=corners.mean(axis=0).round(precision),corners=corners.round(precision).tolist(),
                                  tilt=params.tilt_deg,azimuth=azimuth,orientation=params.orientation))
    if params.fill_landscape and params.orientation == 'portrait':
        modules += landscape_fill(modules, geometry['usable'], long, short, seam, metal, project.roof, ew, _plane)
        modules.sort(key=lambda module: module.row)
    statistics = dict(geometry["area_statistics"],**spacing, module_count=len(modules),
                      dc_kw=len(modules)*float(module["stc_w"])/1000, rows=len({m.row for m in modules}),
                      module_area_ratio=len(modules)*long*short/geometry["roof"].area,
                      offset_m=list(choice),rejected_positions=dict(sorted(Counter(r["reason"] for r in rejected).items())),
                      rejected_candidates=rejected)
    if params.fill_landscape:
        statistics['fill_landscape_count'] = sum(m.orientation == 'landscape' for m in modules) if params.orientation == 'portrait' else 0
    if ew:
        params = params.model_copy(update=dict(rows_per_rack=1))
    if project.roof.type == 'ground':
        statistics['roads'] = roads
        result = Design(params=params, modules=modules, statistics=statistics, installation_roof=project.roof.model_copy(deep=True))
        from .installation import facilities
        result.statistics['ground_piles'] = facilities(project, result)['piles']
        return result
    return Design(params=params,modules=modules,statistics=statistics)


def landscape_fill(modules, usable, long, short, seam, metal, roof, ew, plane=None):
    """Fill lower row pockets; EW halves keep both low edges and an explicit ridge gap."""
    from shapely.affinity import affine_transform
    from shapely.geometry import box
    additions = []
    occupied = unary_union([Polygon(np.array(m.corners)[:, :2]) for m in modules]).buffer(seam - .001)
    for row in sorted({m.row for m in modules}):
        members = [m for m in modules if m.row == row]
        next_col = max(m.col for m in members)
        front = min(members, key=lambda m: (m.tier, m.col))
        angle, beta = math.radians(front.azimuth), math.radians(front.tilt)
        right = np.array([-math.cos(angle), math.sin(angle)])
        back = np.array([-math.sin(angle), -math.cos(angle)])
        basis = np.stack([right, back])
        free = affine_transform(usable.difference(occupied), [*basis[0], *basis[1], 0, 0])
        v = float(np.array(front.corners[0][:2]) @ back)
        depth = short * math.cos(beta)
        band = free.intersection(box(free.bounds[0], v, free.bounds[2], v + depth)) if not free.is_empty else free
        starts = {x for shape in getattr(band, 'geoms', [band]) if shape.geom_type == 'Polygon'
                  for x, _ in shape.exterior.coords}
        candidates = sorted({float(c) for x in starts for shift in (0, -long)
                             for c in np.arange(x + shift, free.bounds[2] - long + .001, long + seam)})
        for c in candidates:
            tile = np.array([[c, v], [c + long, v], [c + long, v + depth], [c, v + depth]])
            xy = tile @ basis
            z0 = front.corners[0][2]
            corners = np.c_[xy, [z0, z0, z0 + short * math.sin(beta), z0 + short * math.sin(beta)]]
            sets = [(corners, front.azimuth)]
            if ew:
                other = next(m for m in members if m.azimuth != front.azimuth)
                low = float(np.array(other.corners[0][:2]) @ back)
                twin = corners[[1, 0, 3, 2]].copy()
                twin[:, :2] += (low - v - np.array([0, 0, 2 * depth, 2 * depth]))[:, None] * back
                sets.append((twin, other.azimuth))
            shapes = [Polygon(points[:, :2]) for points, _ in sets]
            if not all(usable.buffer(.001).covers(p) and not occupied.intersects(p.buffer(-.001)) for p in shapes):
                continue
            for points, azimuth in sets:
                next_col += 1
                if metal:
                    identifier = plane.id if plane else None
                    height = z0 - elevation(roof, front.corners[0][:2], identifier)
                    points[:, 2] = [elevation(roof, p, identifier) + height for p in points[:, :2]]
                    if plane is None:
                        points[:, 2] = [elevation(roof, p) + z0 - elevation(roof, front.corners[0][:2]) for p in points[:, :2]]
                prefix = f'P{plane.id}-' if plane else ''
                precision = 9 if metal or roof.type == 'ground' else 3
                additions.append(Module(id=f'{prefix}R{row:02d}-1-C{next_col:03d}', row=row, tier=1, col=next_col,
                                        center=points.mean(axis=0).round(precision), corners=points.round(precision).tolist(),
                                        tilt=front.tilt, azimuth=azimuth, orientation='landscape'))
            occupied = occupied.union(unary_union(shapes).buffer(seam - .001))
    return additions


def plot_layout(project, design, path, wind=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as Patch
    figure, axes = plt.subplots(figsize=(11,7))
    roof = Polygon(project.roof.outline)
    edge = roof.buffer(-design.params.edge_setback_m)
    def boundary(geometry, **style):
        for polygon in getattr(geometry,"geoms",[geometry]):
            if not polygon.is_empty:
                x,y = polygon.exterior.xy
                axes.plot(x,y,**style)
    boundary(roof,color="#243746",linewidth=2,label="Roof")
    boundary(edge,color="#84929d",linestyle="--",label="Setback")
    if project.roof.type == 'pitched':
        for plane in project.roof.planes:
            shape = Polygon(plane.outline)
            if plane.material == 'glass':
                axes.add_patch(Patch(plane.outline, facecolor='#9fd6df', edgecolor='#526174', alpha=.6))
            boundary(shape, color='#526174', linewidth=1)
            angle = math.radians(plane.slope_azimuth_deg)
            center = shape.centroid
            axes.annotate('', xy=(center.x + 2 * math.sin(angle), center.y + 2 * math.cos(angle)),
                          xytext=(center.x, center.y), arrowprops=dict(arrowstyle='->', color='#9c522b'), zorder=5)
            axes.text(center.x, center.y, f'P{plane.id} {plane.slope_deg:g}°', fontsize=8, zorder=5)
    for obstacle in project.roof.obstacles:
        polygon=obstacle_polygon(obstacle)
        axes.add_patch(Patch(np.array(polygon.exterior.coords),facecolor="#d1956b",edgecolor="#825230"))
        axes.text(polygon.centroid.x,polygon.centroid.y,obstacle.id,ha="center",fontsize=8)
    for zone in [*project.roof.keepouts,*design.added_keepouts]:
        axes.add_patch(Patch(zone.polygon,facecolor="#eddfb1",edgecolor="#aa8d36",hatch="//"))
        centroid=Polygon(zone.polygon).centroid
        axes.text(centroid.x,centroid.y,zone.id,ha="center",fontsize=8)
    wind_rows = {r['id']: r for r in wind.get('modules', [])} if wind else {}
    for module in design.modules:
        color = {1: '#2a9d63', 2: '#c87743'}.get(module.phase, '#307aa1')
        if wind:
            from .wind import COLORS
            color = COLORS.get(wind_rows.get(module.id, {}).get('zone'), '#777777')
        axes.add_patch(Patch(np.array(module.corners)[:,:2],facecolor=color,edgecolor="white",linewidth=0.3))
    if wind:
        for zone, label in [('corner', 'Corner'), ('edge', 'Edge'), ('middle', 'Middle')]:
            axes.plot([], [], color=COLORS[zone], linewidth=6, label=label + ' (illustrative)')
    if not wind and any(m.phase for m in design.modules):
        axes.plot([], [], color='#2a9d63', linewidth=6, label='一期')
        axes.plot([], [], color='#c87743', linewidth=6, label='二期')
    xmin,ymin,xmax,ymax=roof.bounds
    axes.annotate("N",xy=(xmax+2,ymax-1),xytext=(xmax+2,ymax-7),ha="center",arrowprops=dict(arrowstyle="->"))
    axes.plot([xmin,xmin+5],[ymin-2,ymin-2],color="black",linewidth=3)
    axes.text(xmin+2.5,ymin-3,"5 m",ha="center")
    rows=sorted({module.row for module in design.modules})
    if project.roof.type == 'metal':
        a = np.array([roof.centroid.x, roof.centroid.y])
        angle = math.radians(project.roof.slope_azimuth_deg)
        b = a + min(xmax - xmin, ymax - ymin) / 4 * np.array([math.sin(angle), math.cos(angle)])
        axes.annotate(f"Slope {project.roof.slope_deg:g}°", xy=b, xytext=a, color="#c87743",
                      arrowprops=dict(arrowstyle="->", color="#c87743"))
    elif len(rows)>=2:
        first=[min((m for m in design.modules if m.row==r),key=lambda m:m.col) for r in rows[:2]]
        a=np.array(first[0].corners[0])[:2]
        angle=math.radians(design.params.azimuth_deg)
        b=a+design.statistics['row_spacing_m']*np.array([-math.sin(angle),-math.cos(angle)])
        axes.annotate("",xy=a,xytext=b,arrowprops=dict(arrowstyle="<->",color="#9a3150"))
        axes.text(*(a+b)/2,f"D={design.statistics['row_spacing_m']:.3f} m",fontsize=8,color="#9a3150")
    axes.set(xlabel="East x (m)",ylabel="North y (m)",title=f"{len(design.modules)} modules / {design.statistics['dc_kw']:.2f} kWp")
    axes.set_aspect("equal")
    axes.legend(loc="upper left",bbox_to_anchor=(1,1), prop={'family': 'Microsoft YaHei'} if any(m.phase for m in design.modules) else None)
    figure.tight_layout()
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    figure.savefig(path,dpi=160)
    plt.close(figure)


def main(argv=None):
    from . import project as storage
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["generate"])
    parser.add_argument("--project",required=True)
    parser.add_argument("--tilt",type=float,default=25)
    parser.add_argument("--azimuth",type=float,default=180)
    parser.add_argument("--orientation",choices=["portrait","landscape"],default="portrait")
    parser.add_argument("--png",type=Path)
    args=parser.parse_args(argv)
    try:
        project=storage.load(args.project)
        params=validated(LayoutParams,dict(tilt_deg=args.tilt,azimuth_deg=args.azimuth,orientation=args.orientation),"LAYOUT_PARAMS_INVALID")
        started=time.perf_counter()
        design=generate_layout(project,params)
        elapsed=time.perf_counter()-started
        design.version=storage.next_version(args.project)
        design.parent_version=None
        design.reason="按参数重新排板"
        storage.save_design(args.project,design)
        if args.png:
            plot_layout(project,design,args.png)
        print(json.dumps(dict(ok=True,version=design.version,elapsed_seconds=elapsed,statistics=design.statistics),ensure_ascii=False))
        return 0
    except GzError as error:
        print(json.dumps(error.as_dict(),ensure_ascii=False))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
