"""Monthly representative-day geometric shading, weighted by NASA 2023 POA."""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
import pvlib
from shapely.geometry import Polygon

from .config import ROOT, SHADING_THRESHOLD_PCT
from .models import Design, GzError, validate_project, validated, obstacle_polygon
from .shading_geometry import build_scene, sample_points, ray_hits, ray_candidates, candidate_hits, sun_vector, beam_fractions, shadow_polygons, pole_shadow
from .solar import sun_position, poa_irradiance
from .weather import load_nasa_hourly
from .runtime_diagnostics import stage
from . import orientation


def _front_mask(design):
    """A front rack must overlap in the column direction; missing racks count."""
    n=len(design.modules)
    if not n:
        return np.zeros(0,dtype=bool)
    angle=np.radians(design.params.azimuth_deg)
    right=np.array([-np.cos(angle),np.sin(angle)])
    projected=np.array([m.corners for m in design.modules])[:,:,:2] @ right
    low,high=projected.min(axis=1),projected.max(axis=1)
    rows=np.array([m.row for m in design.modules])
    overlaps=(low[:,None]<high[None,:]-1e-6)&(high[:,None]>low[None,:]+1e-6)
    return (overlaps & (rows[:,None]>rows[None,:])).any(axis=1)


class SiteShading:
    """A comparison shares immutable weather and sun positions for one site."""

    def __init__(self, project, *, offline=False):
        with stage("shading.weather"):
            self.weather, self.metadata = load_nasa_hourly(project.site.lat, project.site.lon, 2023, offline=offline)
        with stage("shading.annual-sun"):
            self.sun = sun_position(self.weather.index + pd.Timedelta(minutes=30), project.site.lat, project.site.lon)
        times = pd.DatetimeIndex([pd.Timestamp(year=2023, month=m, day=15, hour=h, tz="UTC") + pd.Timedelta(minutes=30)
                                  for m in range(1, 13) for h in range(24)])
        with stage("shading.representative-sun"):
            self.positions = sun_position(times, project.site.lat, project.site.lon)


class RemovalShading:
    """Retain exact ray intersections within one comparison, not across calls.

    A removed rack may uncover a farther blocker. Keep every ordered positive
    intersection, then filter removed owners before choosing the nearest one.
    When the byte limit is reached we recompute that hour without retaining it.
    """

    def __init__(self, project, design, *, offline=False, site=None, max_cache_bytes=16 * 1024 * 1024):
        self.project = project.model_copy(deep=True)
        self.reference = design.model_copy(deep=True)
        self.site = site or SiteShading(project, offline=offline)
        self.scene, self.points = build_scene(project, design), sample_points(design)
        self.owners = np.broadcast_to(np.arange(len(design.modules))[:, None, None], self.points.shape[:-1])
        self.module_geometry = {module.id: module.model_dump(exclude={'phase'}) for module in design.modules}
        self.index = {module.id: i for i, module in enumerate(design.modules)}
        self.cache, self.cache_bytes, self.max_cache_bytes = {}, 0, max_cache_bytes

    def analyze(self, design):
        if design.installation_roof != self.reference.installation_roof:
            raise ValueError('reuse requires unchanged physical installation')
        if design.params != self.reference.params or any(self.module_geometry.get(m.id) != m.model_dump(exclude={'phase'}) for m in design.modules):
            raise ValueError("reuse requires unchanged geometry and parameters; only module removal is allowed")
        indices = np.array([self.index[m.id] for m in design.modules], dtype=int)
        active = np.zeros(len(self.reference.modules), dtype=bool)
        active[indices] = True
        def hits(scene, points, vector, owners):
            key = tuple(vector)
            candidates = self.cache.get(key)
            if candidates is None:
                candidates = ray_candidates(self.scene, self.points, vector, self.owners)
                size = sum(value.nbytes for value in candidates)
                if self.cache_bytes + size <= self.max_cache_bytes:
                    self.cache[key] = candidates
                    self.cache_bytes += size
            return candidate_hits(self.scene, self.points.shape[:-1], candidates, active)[indices]
        return analyze_design(self.project, design, _site=self.site, _ray_hits=hits)


def analyze_design(project, design, *, offline=False, _site=None, _ray_hits=None):
    started=time.perf_counter()
    project,design=validate_project(project),validated(Design,design,"DESIGN_INVALID")
    from .installation import effective
    project = effective(project, design)
    design = next(orientation.views(design))[1] if len(orientation.groups(design)) == 1 else design
    site = _site or SiteShading(project, offline=offline)
    if len(orientation.groups(design)) > 1:
        scene = None if _ray_hits else build_scene(project, design)
        points = sample_points(design)
        owners = np.broadcast_to(np.arange(len(design.modules))[:, None, None], points.shape[:-1])
        indices = {module.id: i for i, module in enumerate(design.modules)}
        cache, results = {}, []
        for identity, view in orientation.views(design):
            selected = [indices[module.id] for module in view.modules]
            def hits(unused_scene, unused_points, vector, unused_owners):
                stamp = tuple(vector)
                if stamp not in cache:
                    cache[stamp] = (_ray_hits or ray_hits)(scene, points, vector, owners)
                return cache[stamp][selected]
            results.append((identity, analyze_design(project, view, _site=site, _ray_hits=hits)))
        modules = {row['id']: row for _, result in results for row in result['modules']}
        summary = dict(results[0][1]['summary'])
        for name in ('avg_loss_pct', 'modules_over_threshold'):
            summary[name] = sum(r['summary'][name] * (len(r['modules']) / len(modules) if name == 'avg_loss_pct' else 1)
                                for _, r in results)
        summary.update(module_count=len(modules), max_loss_pct=max(row['total_loss_pct'] for row in modules.values()))
        for name in ('source_loss_pct', 'beam_cause_loss_pct'):
            summary[name] = {cause: sum(r['summary'][name].get(cause, 0) * len(r['modules']) / len(modules) for _, r in results)
                             for cause in sorted(set().union(*(r['summary'][name] for _, r in results)))}
        lost = sum(summary['source_loss_pct'].values())
        summary['source_loss_share_pct'] = {cause: 100 * value / lost if lost else 0
                                           for cause, value in summary['source_loss_pct'].items()}
        metadata = dict(groups=[dict(group=identity, **r['metadata']) for identity, r in results],
                        elapsed_seconds=time.perf_counter() - started)
        return dict(version=design.version, modules=[modules[m.id] for m in design.modules], summary=summary, metadata=metadata)
    weather,weather_meta=site.weather,site.metadata
    params=design.params
    sun=site.sun
    with stage("shading.poa"):
        poa=poa_irradiance(weather,sun,params.tilt_deg,params.azimuth_deg,project.site.albedo)
    total=float(poa.poa_global.sum())
    if total<=0:
        raise GzError("IRRADIANCE_MISSING","全年斜面辐照为零，无法折算遮挡比例","检查NASA2023天气数据与排板角度")
    weights=np.zeros((12,24))
    np.add.at(weights,(weather.index.month-1,weather.index.hour),poa.poa_direct.to_numpy())
    positions=site.positions
    with stage("shading.scene"):
        scene=None if _ray_hits else build_scene(project,design)
        points=sample_points(design)
    owners=np.broadcast_to(np.arange(len(design.modules))[:,None,None],points.shape[:-1])
    beam=np.zeros(len(design.modules))
    causes=defaultdict(lambda: np.zeros(len(design.modules)))
    orientations=[m.orientation for m in design.modules]
    daylight=0
    with stage("shading.rays"):
        for instant,position in positions.iterrows():
            if position.elevation<=0:
                continue
            if project.roof.type in ('pitched', 'carport'):
                beta, bearing = np.radians([params.tilt_deg, params.azimuth_deg])
                normal = np.array([np.sin(beta) * np.sin(bearing), np.sin(beta) * np.cos(bearing), np.cos(beta)])
                if np.dot(normal, sun_vector(position.elevation, position.azimuth)) <= 0:
                    continue
            daylight+=1
            hits=(_ray_hits or ray_hits)(scene,points,sun_vector(position.elevation,position.azimuth),owners)
            fraction,shares=beam_fractions(hits,orientations)
            weight=weights[instant.month-1,instant.hour]
            beam+=weight*fraction
            for cause,share in shares.items():
                causes[cause]+=weight*share
    # Passias assumes isotropic sky; applying its factor to Perez sky is the
    # task's approximation. Obstacle/parapet diffuse shading is excluded.
    sky_fraction=0.0 if params.tilt_deg==0 or project.roof.type in ("metal", 'pitched', 'carport') else float(pvlib.shading.sky_diffuse_passias(
        pvlib.shading.masking_angle_passias(params.tilt_deg,design.statistics["gcr"])))
    diffuse=_front_mask(design)*sky_fraction*float(poa.poa_sky_diffuse.sum())
    losses=100*(beam+diffuse)/total
    per_module=[]
    for i,module in enumerate(design.modules):
        positive=[(float(value[i]),cause) for cause,value in causes.items() if value[i]>0]
        main=min(positive,key=lambda pair:(-pair[0],pair[1]))[1] if positive else "none"
        per_module.append(dict(id=module.id,beam_loss_pct=float(100*beam[i]/total),
                               diffuse_loss_pct=float(100*diffuse[i]/total),total_loss_pct=float(losses[i]),main_cause=main))
    denominator=len(design.modules)*total
    detail={cause:100*float(value.sum())/denominator for cause,value in sorted(causes.items())} if denominator else {}
    categories=dict(obstacles=0.0,parapet=0.0,front_row=100*float(diffuse.sum())/denominator if denominator else 0.0)
    if project.roof.type in ('pitched', 'carport'):
        categories['roof'] = 0.0
    nearby={row.id for row in project.roof.surroundings}
    categories|=dict(surroundings=0.0) if nearby else {}
    for cause,loss in detail.items():
        known = ('parapet', 'front_row', 'roof') if project.roof.type in ('pitched', 'carport') else ('parapet', 'front_row')
        categories[cause if cause in known else "surroundings" if cause in nearby else "obstacles"]+=loss
    lost=sum(categories.values())
    source_shares={cause:100*loss/lost if lost else 0.0 for cause,loss in categories.items()}
    summary=dict(module_count=len(design.modules),avg_loss_pct=float(losses.mean()) if len(losses) else 0,
                 max_loss_pct=float(losses.max()) if len(losses) else 0,
                 modules_over_threshold=int((losses>SHADING_THRESHOLD_PCT).sum()),threshold_pct=SHADING_THRESHOLD_PCT,
                 source_loss_pct=categories,source_loss_share_pct=source_shares,beam_cause_loss_pct=detail)
    metadata=dict(weather=weather_meta,weather_sha256=weather_meta["data_file_sha256"],
                  threshold_pct=SHADING_THRESHOLD_PCT,threshold_note="示意",sample_year=2023,
                  representative_days=12,daylight_hours=daylight,points_per_module=9,
                  timestamp_rule="UTC month-15 hour label + 30 minutes",sky_masking_fraction=sky_fraction,
                  poa_global_wh_m2=total,poa_direct_wh_m2=float(poa.poa_direct.sum()),
                  poa_sky_diffuse_wh_m2=float(poa.poa_sky_diffuse.sum()),elapsed_seconds=time.perf_counter()-started)
    if project.roof.type == 'pitched':
        metadata['roof_note'] = '真实坡面含玻璃面按不透光几何遮挡示意；仅正面入射代表光线计直射损失；未模拟透射及天空遮挡'
    if project.roof.type == 'carport':
        metadata['roof_note'] = '完整有效车棚按不透光实体计算互遮挡；删板不删棚；仅正面入射；未模拟天空遮挡'
    return dict(version=design.version,modules=per_module,summary=summary,metadata=metadata)


def analyze(project_id, version, *, offline=False):
    from . import project as storage
    project,design=storage.load(project_id),storage.load_design(project_id,version)
    result=analyze_design(project,design,offline=offline)
    result["metadata"]["design_sha256"]=hashlib.sha256(storage._path(project_id,f"designs/v{version}.json").read_bytes()).hexdigest()
    path=storage._path(project_id,f"analysis/v{version}/shading.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    return result


def plot_analysis(project,design,result,directory):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PatchCollection
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import Polygon as Patch, PathPatch
    from matplotlib.path import Path as PlotPath
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    roof=Polygon(project.roof.outline)
    def background(ax):
        ax.plot(*roof.exterior.xy,color="#243746",linewidth=1.5)
        for obstacle in project.roof.obstacles:
            p=obstacle_polygon(obstacle)
            ax.add_patch(Patch(np.array(p.exterior.coords),facecolor="#d1956b",edgecolor="#825230"))
            ax.text(p.centroid.x,p.centroid.y,obstacle.id,ha="center",fontsize=7)
        for zone in [*project.roof.keepouts,*design.added_keepouts]:
            ax.add_patch(Patch(zone.polygon,facecolor="#eddfb1",edgecolor="#aa8d36",hatch="//"))
        xmin,ymin,xmax,ymax=roof.bounds
        ax.set(xlim=(xmin-2,xmax+2),ylim=(ymin-2,ymax+2),xlabel="East (m)",ylabel="North (m)",aspect="equal")
    figure,ax=plt.subplots(figsize=(11,7))
    background(ax)
    patches=[Patch(np.array(m.corners)[:,:2]) for m in design.modules]
    colors=LinearSegmentedColormap.from_list("shading",["#1c2b4a","#c97a12","#b83c28"])
    collection=PatchCollection(patches,cmap=colors,edgecolor="white",linewidth=0.2)
    collection.set_array(np.array([m["total_loss_pct"] for m in result["modules"]]))
    collection.set_clim(0,max(result["summary"]["max_loss_pct"],SHADING_THRESHOLD_PCT))
    ax.add_collection(collection)
    figure.colorbar(collection,ax=ax,label="Total shading loss (%)")
    ax.set_title(f"v{design.version}: {len(design.modules)} modules / mean {result['summary']['avg_loss_pct']:.2f}%")
    figure.tight_layout()
    figure.savefig(directory/"T05-heatmap.png",dpi=160)
    plt.close(figure)
    figure,axes=plt.subplots(1,3,figsize=(16,5))
    scene=build_scene(project,design)
    for hour,ax in zip([9,12,15],axes):
        background(ax)
        polygons=shadow_polygons(scene,pd.Timestamp(f"2025-12-21T{hour:02}:00+08:00"))
        for key,shape in polygons.items():
            for polygon in getattr(shape,"geoms",[shape]):
                if polygon.geom_type=="Polygon" and not polygon.is_empty:
                    rings=[np.array(ring.coords) for ring in [polygon.exterior,*polygon.interiors]]
                    paths=[PlotPath(ring,[PlotPath.MOVETO]+[PlotPath.LINETO]*(len(ring)-2)+[PlotPath.CLOSEPOLY]) for ring in rings]
                    ax.add_patch(PathPatch(PlotPath.make_compound_path(*paths),facecolor="#354655",alpha=0.22,linewidth=0))
        for module in design.modules:
            ax.add_patch(Patch(np.array(module.corners)[:,:2],fill=False,edgecolor="#307aa1",linewidth=0.2))
        ax.set_title(f"Winter solstice / Beijing {hour:02}:00")
    figure.tight_layout()
    figure.savefig(directory/"T05-shadows.png",dpi=160)
    plt.close(figure)


def main(argv=None):
    from . import project as storage
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    annual=commands.add_parser("analyze")
    annual.add_argument("--project",required=True)
    annual.add_argument("--version",type=int,required=True)
    annual.add_argument("--offline",action="store_true")
    pole=commands.add_parser("pole")
    pole.add_argument("--lat",type=float,required=True)
    pole.add_argument("--lon",type=float,required=True)
    pole.add_argument("--time",required=True)
    pole.add_argument("--height",type=float,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=="pole":
            output=pole_shadow(args.lat,args.lon,args.time,args.height)
        else:
            result=analyze(args.project,args.version,offline=args.offline)
            plot_analysis(storage.load(args.project),storage.load_design(args.project,args.version),result,ROOT/"reports/assets")
            output=dict(version=args.version,**result["summary"],metadata=result["metadata"])
        print(json.dumps(dict(ok=True,**output),ensure_ascii=False))
        return 0
    except (ValueError,OSError) as error:
        error=GzError("SHADING_INPUT_INVALID","遮挡输入、天气或输出文件不正确","检查时区、天气缓存、方案版本和文件权限")
        print(json.dumps(error.as_dict(),ensure_ascii=False))
        return 1
    except GzError as error:
        print(json.dumps(error.as_dict(),ensure_ascii=False))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
