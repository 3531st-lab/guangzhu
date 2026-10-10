"""One building with physical flush roof faces and a shared equipment installation."""
import math

from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .models import Design, GzError, LayoutParams
from . import roofplane


def rack(plane, roof=None):
    if plane.material == 'metal' and roof is not None and roof.use == 'barn':
        return 'clamp_barn'
    return 'clamp_flush' if plane.material == 'metal' else 'fixed_flush'


def geometry(project, params, plane):
    from .layout import usable_geometry
    base = usable_geometry(project, params)
    shape = Polygon(plane.outline)
    distance = .5 if project.roof.seam_setback_m is None else project.roof.seam_setback_m
    joins = unary_union([line for a, b, line in roofplane.seams(project.roof) if plane.id in (a.id, b.id)])
    edge = base['edge'].intersection(shape).difference(joins.buffer(distance, cap_style=2))
    usable = base['usable'].intersection(edge)
    return dict(base, roof=shape, edge=edge, usable=usable,
                area_statistics=dict(base['area_statistics'], roof_area_m2=shape.area, usable_area_m2=usable.area))


def conflicting_modules(modules):
    """Keep the first occupant; distinct faces cannot share positive footprint area."""
    footprints = [Polygon([p[:2] for p in module.corners]) for module in modules]
    index = STRtree(footprints)
    rejected = set()
    for number, panel in enumerate(modules):
        for other in index.query(footprints[number], predicate='intersects'):
            previous = modules[other]
            if other >= number or previous.id in rejected or previous.id.split('-')[0] == panel.id.split('-')[0]:
                continue
            # Boundary contact is allowed; a 2-dimensional intersection has no roof-input tolerance.
            if footprints[number].relate_pattern(footprints[other], '2********'):
                rejected.add(panel.id)
                break
    return rejected


def layout(project, params):
    from .layout import generate_layout, _catalog
    params = params if isinstance(params, LayoutParams) else LayoutParams.model_validate(params)
    if params.layout != 'rows':
        raise GzError('LAYOUT_PARAMS_INVALID', '多坡屋顶按各面顺坡平铺', '选择顺坡排板')
    available = {p.id for p in project.roof.planes if p.material != 'glass'}
    selected = available if params.plane_ids is None else set(params.plane_ids)
    if not selected <= available:
        raise GzError('ROOF_PLANES_INVALID', '选用坡面不存在或为玻璃', '选择金属或混凝土坡面')
    modules, rows = [], []
    for plane in project.roof.planes:
        design = generate_layout(project, params, _plane=plane) if plane.id in selected else None
        if design:
            modules.extend(design.modules)
        rows.append(dict(id=plane.id, material=plane.material, selected=plane.id in selected,
                         module_count=len(design.modules) if design else 0,
                         dc_kw=design.statistics['dc_kw'] if design else 0,
                         statistics=design.statistics if design else {}))
    rejected = conflicting_modules(modules)
    if rejected:
        modules = [panel for panel in modules if panel.id not in rejected]
        catalog, _, _ = _catalog(project, params)
        area = float(catalog['length_m']) * float(catalog['width_m'])
        for row in rows:
            members = [panel for panel in modules if panel.id.startswith(f"P{row['id']}-")]
            if len(members) == row['module_count']:
                continue
            row.update(module_count=len(members), dc_kw=len(members) * float(catalog['stc_w']) / 1000)
            row['statistics'].update(module_count=len(members), dc_kw=row['dc_kw'], rows=len({panel.row for panel in members}),
                                     module_area_ratio=len(members) * area / row['statistics']['roof_area_m2'])
            if params.fill_landscape:
                row['statistics']['fill_landscape_count'] = (sum(panel.orientation == 'landscape' for panel in members)
                                                            if params.orientation == 'portrait' else 0)
    first = next((r['statistics'] for r in rows if r['statistics']), {})
    stats = dict(first, planes=rows, module_count=len(modules), dc_kw=sum(r['dc_kw'] for r in rows),
                 roof_area_m2=Polygon(project.roof.outline).area,
                 usable_area_m2=sum(r['statistics'].get('usable_area_m2', 0) for r in rows),
                 rows=sum(r['statistics'].get('rows', 0) for r in rows),
                 seam_setback_m=.5 if project.roof.seam_setback_m is None else project.roof.seam_setback_m)
    if params.fill_landscape:
        stats['fill_landscape_count'] = sum(r['statistics'].get('fill_landscape_count', 0) for r in rows)
    if rejected:
        stats.update(module_area_ratio=len(modules) * area / stats['roof_area_m2'], cross_face_removed=sorted(rejected))
    return Design(params=params, modules=modules, statistics=stats)


def table(project, design, shadows=None, energy=None, load=None):
    """The same per-face facts feed the editor, archives and every export."""
    losses = {r['id']: r['total_loss_pct'] for r in (shadows or {}).get('modules', [])}
    loads = {r['id']: r for r in (load or {}).get('planes', [])}
    yields = {r['id']: r for r in (energy or {}).get('planes', [])}
    rows = []
    for plane in project.roof.planes:
        panels = [m for m in design.modules if roofplane.member(project.roof, m.id).id == plane.id]
        heights = [roofplane.plane_elevation(plane, p) for p in plane.outline]
        capacity = plane.load_capacity_kn_m2 if plane.load_capacity_kn_m2 is not None else project.roof.load_capacity_kn_m2
        rows.append(dict(id=plane.id, material=plane.material, slope_deg=plane.slope_deg,
                         azimuth_deg=plane.slope_azimuth_deg, offset_m=plane.offset_m,
                         min_height_m=project.roof.height_m + min(heights), max_height_m=project.roof.height_m + max(heights),
                         area_m2=Polygon(plane.outline).area / math.cos(math.radians(plane.slope_deg)),
                         module_count=len(panels), capacity_kn_m2=capacity,
                         capacity_source='坡面值' if plane.load_capacity_kn_m2 is not None else '继承整栋',
                         verified=plane.load_verified if plane.load_verified is not None else project.roof.load_verified,
                         shading_pct=sum(losses.get(m.id, 0) for m in panels) / len(panels) if panels else 0,
                         load=loads.get(plane.id), energy=yields.get(plane.id)))
    return rows
