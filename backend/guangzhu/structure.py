"""Conservative added-load comparison; not a structural safety assessment."""

import math
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from .models import GzError
from .orientation import key, groups, views
from . import wind


def calculate(project,design):
    from .installation import effective, facilities
    project = effective(project, design)
    from .electrical import equipment_catalog
    from .layout import rack_id
    catalog=equipment_catalog()
    module=catalog['modules'][project.equipment.module_id]
    rack=catalog['racking'][rack_id(project, design.params)]
    long,short=float(module['length_m']),float(module['width_m'])
    gap=float(rack['module_gap_m'])
    footprints={}
    panel_racks = {}
    tiers = {}
    for m in [*design.modules, *design.removed_modules]:
        rack_key = key(m), m.row, m.col
        tiers[rack_key] = max(tiers.get(rack_key, 1), m.tier)
    physical = len(groups(design)) > 1 or 'group_row_positions' in next(views(design))[1].statistics
    for item in design.modules:
        beta,angle=math.radians(item.tilt),math.radians(item.azimuth)
        slope,width=(long,short) if item.orientation=='portrait' else (short,long)
        count = tiers[key(item), item.row, item.col] if physical else design.params.rows_per_rack
        length=count*slope+(count-1)*gap
        right,back=np.array([-math.cos(angle),math.sin(angle)]),np.array([-math.sin(angle),-math.cos(angle)])
        base=np.array(item.corners[0][:2])-(item.tier-1)*(slope+gap)*math.cos(beta)*back
        footprint=Polygon([base,base+width*right,base+width*right+length*math.cos(beta)*back,base+length*math.cos(beta)*back])
        footprints[(key(item),item.row,item.col,item.orientation)]=footprint
        panel_racks[item.id] = (key(item), item.row, item.col, item.orientation)
    area=unary_union(list(footprints.values())).area
    result, regions = wind.calculate(project, design, module, rack)
    def rack_masses():
        masses = dict.fromkeys(footprints, 0.0)
        for row in result['modules']:
            masses[panel_racks[row['id']]] += row['dead_kg'] + row['ballast_kg']
        return masses
    masses = rack_masses()
    extra = []
    if project.roof.type == 'flat' and not project.requirements.structured.ballast_only:
        # A rack whose wind ballast would overload the roof is anchored to the slab instead (common practice on concrete roofs).
        # An owner who forbids drilling keeps ballast, and L01 then reports the overload honestly.
        capacity = project.roof.load_capacity_kn_m2
        heavy = {k for k, shape in footprints.items() if shape.area and masses[k] * .00981 / shape.area > capacity + 1e-9}
        switched = [row for row in result['modules'] if panel_racks[row['id']] in heavy and row['ballast_kg']]
        for row in switched:
            wind.anchor(row)
        if switched:
            masses = rack_masses()
            result.update(zones=wind.totals(result['modules']), ballast_mass_kg=math.fsum(r['ballast_kg'] for r in result['modules']),
                          ballast_blocks=sum(r['ballast_blocks'] for r in result['modules']), anchored_modules=len(switched),
                          anchor_count=sum(r['anchors'] for r in switched), anchor_note=wind.ANCHOR_NOTE)
            extra.append(dict(key='flat_anchor', quantity=result['anchor_count'], hardware=True))
    outside = unary_union(list(footprints.values())).difference(Polygon(project.roof.outline))
    if outside.area > 1e-9:
        regions['outside'] = outside
    loads = wind.zone_loads(footprints, masses, regions)
    for name, values in loads.items():
        result['zones'].setdefault(name, dict(label=wind.LABELS[name], modules=0, ballast_blocks=0, ballast_kg=0))
        result['zones'][name].update(values)
    mass = math.fsum(masses.values())
    average = mass * .00981 / area if area else 0
    worst = max(loads, key=lambda name: loads[name]['load_kn_m2'])
    load = loads[worst]['load_kn_m2']
    result['worst_zone'] = worst
    if project.roof.type == 'metal':
        extra.append(dict(key='barn_clamp' if project.roof.use == 'barn' else 'wind_clamp',
                          quantity=result['clamp_count'], hardware=True))
    output = dict(added_kn_m2=load, average_kn_m2=average, capacity_kn_m2=project.roof.load_capacity_kn_m2,
                status='pass' if load <= project.roof.load_capacity_kn_m2 else 'fail', mass_kg=mass,
                ballast_mass_kg=result['ballast_mass_kg'], rack_projection_area_m2=area, wind=result, extra_cost_items=extra,
                evidence=f"最不利{wind.LABELS[worst]}={load:.6f}kN/㎡；总平均{mass:g}kg×9.81/1000/{area:.6f}㎡={average:.6f}",
                source_ref=module['datasheet_url'] + ';data/catalog/racking.csv;data/catalog/wind.csv',
                note=wind.NOTE + '；不能代替结构复核；分母仅支架投影，不含排间空地。')
    if result.get('anchor_count'):
        output['evidence'] += f"；{result['anchored_modules']}块组件的支架压块超承重，改用{result['anchor_count']}个锚栓固定（示意）"
        output['note'] += wind.ANCHOR_NOTE + '。'
    if project.roof.type == 'pitched':
        from .pitched import rack as face_rack
        rows = []
        for plane in project.roof.planes:
            subset = {k: v for k, v in footprints.items() if k[0][0] == plane.id}
            plane_loads = wind.zone_loads(subset, masses, regions)
            zone = max(plane_loads, key=lambda name: plane_loads[name]['load_kn_m2'])
            value = plane_loads[zone]['load_kn_m2']
            capacity = plane.load_capacity_kn_m2 if plane.load_capacity_kn_m2 is not None else project.roof.load_capacity_kn_m2
            rows.append(dict(id=plane.id, material=plane.material,
                             rack_id=face_rack(plane, project.roof) if plane.material != 'glass' else None,
                             added_kn_m2=value, capacity_kn_m2=capacity, status='pass' if value <= capacity else 'fail',
                             capacity_source='坡面值' if plane.load_capacity_kn_m2 is not None else '继承整栋',
                             verified=plane.load_verified if plane.load_verified is not None else project.roof.load_verified,
                             mass_kg=math.fsum(masses[k] for k in subset), zones=plane_loads, worst_zone=zone))
        governing = max(rows, key=lambda r: r['added_kn_m2'] / r['capacity_kn_m2'])
        output.update(planes=rows, added_kn_m2=governing['added_kn_m2'], capacity_kn_m2=governing['capacity_kn_m2'],
                      status=governing['status'], governing_plane=governing['id'],
                      evidence=f"P{governing['id']}控制；{governing['added_kn_m2']:.6f}kN/㎡；逐面核对各自承重")
        for plane in project.roof.planes:
            members = [r for r in result['modules'] if r['plane'] == plane.id]
            if plane.material == 'glass' or not members:
                continue
            hardware_key = 'wind_clamp' if plane.material == 'metal' else 'fixed_anchor'
            if plane.material == 'metal' and project.roof.use == 'barn':
                hardware_key = 'barn_clamp'
            count = sum(r['clamps']['adopted'] if 'clamps' in r else r['anchors'] for r in members)
            extra.append(dict(key=hardware_key, quantity=count, hardware=True, plane=plane.id))
        output['note'] += '混凝土坡面锚固每板4点仅为计量示意，未核定锚固抗拔、防水及主体传力。'
    if project.roof.type in ('ground', 'carport'):
        items = facilities(project, design)
        output.update(status='na', facilities=items, evidence='新建基础及结构须厂家设计，屋面附加载荷校核不适用')
        output['note'] = items['note'] + '；风压及高度为设计输入示意，未完成抗拔或承载验算'
        if project.roof.type == 'ground':
            extra.extend([dict(key='ground_pile', quantity=len(items['piles']), hardware=True),
                          dict(key='ground_rack', quantity=items['rack_count'], hardware=True),
                          dict(key='ground_road', quantity=items['road_area_m2'], hardware=False),
                          dict(key='animal_fence' if project.roof.use == 'grazing' else 'ground_fence',
                               quantity=items['fence_quote_m'], hardware=True)])
        else:
            # Empty sheds still require steel. 12kg/m² is explicitly an illustrative area floor.
            basis = design.statistics.get('canopy_installed_kw', len(design.modules) * float(module['stc_w']) / 1000)
            steel = max(basis * 60, items['canopy_area_m2'] * 12)
            items['steel_kg'] = steel
            items['steel_basis_kw'] = basis
            extra.append(dict(key='carport_steel', quantity=steel, hardware=True))
    return output
