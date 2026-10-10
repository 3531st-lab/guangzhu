"""Traceable rules and local electrical/load checks for a design version."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
from shapely.geometry import Polygon
from . import config,project as storage
from .models import GzError,obstacle_polygon
from .layout import row_spacing,usable_geometry

STANDARD='https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2024/art_96bd1b03e8d54760b4dff9ad60352ddc.html'
REGISTRY=[
 ('G01','组件都在可用区域内','layout','hard','行业做法','T04排板规则'),
 ('G02','冬至真太阳9–15时前后排不遮挡','layout','advice','国家标准','GB50797局部修订7.2.2(2)；屋顶保守规则'),
 ('G03','检修通道宽度达到要求','requirement','hard','用户要求','requirements.walkway_m_min'),
 ('G04','要求留空的区域没有组件','requirement','hard','用户要求','requirements.keep_clear_ids'),
 ('G05','倾角在要求范围内','requirement','hard','用户要求','requirements.tilt_deg_range'),
 ('G06','边距和障碍物避让达到要求','requirement','hard','用户要求','requirements.edge_setback_m_min/obstacle_clearance_m_min'),
 ('S01','单块全年遮挡损失不超阈值','shading','hard','行业做法','T05三段遮挡规则'),
 ('S02','平均遮挡损失不超提醒阈值','shading','advice','行业做法','T05三段遮挡规则'),
 ('E01','最冷开路电压不超逆变器上限','electrical','hard','国家标准','GB50797第6.4.2条及逆变器规格书'),
 ('E02','最冷开路电压不超组件系统上限','electrical','hard','厂家规格书','组件规格书'),
 ('E03','最热工作电压不低于MPPT下限','electrical','hard','国家标准','GB50797第6.4.2条'),
 ('E04','最冷工作电压不超MPPT上限','electrical','hard','厂家规格书','任务沿用2012公式的附加校核；2024第6.4.2已删此上界'),
 ('E05','每路最大短路电流不超允许值','electrical','hard','厂家规格书','逆变器规格书'),
 ('E06','每路工作电流不超最大输入','electrical','advice','厂家规格书','逆变器规格书'),
 ('E07','容配比在示意范围内','electrical','hard','行业做法','本项目配置'),
 ('E08','全部组件接入组串','electrical','hard','行业做法','本项目完整组串规则'),
 ('E09','同路MPPT各串块数一致','electrical','hard','行业做法','本项目组串规则'),
 ('E10','直流线路压降不超过限值','electrical','hard','设计假设','docs/sources.md T26；ABB2014§3.4.2'),
 ('E11','交流线路压降不超过限值','electrical','hard','设计假设','docs/sources.md T26；项目默认2%'),
 ('L01','附加荷载不超屋面核定值','structure','hard','用户要求','roof.load_capacity_kn_m2'),
 ('W01','夹具抗风揭','structure','hard','设计假设','structure.wind'),
 ('U01','装机不低于要求下限','requirement','hard','用户要求','requirements.capacity_kw_min'),
 ('U02','装机不超要求上限','requirement','hard','用户要求','requirements.capacity_kw_max'),
 ('U03','造价不超预算','economics','hard','用户要求','requirements.budget_cny_max'),
 ('U04','静态回本不超要求','economics','hard','用户要求','requirements.payback_years_max'),
 ('U05','不上网时限电不超要求','requirement','hard','用户要求','requirements.export_allowed/curtail_pct_max'),
 ('U06','逆变器合计不超变压器上限','requirement','hard','用户要求','requirements.transformer_kva/transformer_share'),
 ('U07','一期装机或预算满足要求','requirement','hard','用户要求','requirements.phase1_kw/phase1_budget_cny'),
 ('G07','组件最高点不超限高','requirement','hard','用户要求','requirements.max_height_m'),
 ('G08','地面组件最低点达到离地要求','requirement','hard','用户要求','ground.lower_edge_m；默认0.5米示意'),
 ('G09','车棚实际梁底净高达到项目参照','requirement','hard','项目参照','JGJ100-2015表4.2.5；适用车库的小型车2.2米'),
 ('G10','地面受光比例达到要求','requirement','hard','示意','本地代表日地影面积并集；默认50%示意'),
]


from . import orientation


def row_geometry(project, design):
    params = design.params
    length=design.statistics.get('gcr',0)*design.statistics.get('row_spacing_m',0)
    angle=math.radians(params.azimuth_deg)
    back=np.array([-math.sin(angle),-math.cos(angle)])
    rows=sorted({m.row for m in design.modules})
    if 'group_row_positions' in design.statistics:
        return length, np.abs(np.diff(design.statistics['group_row_positions'])), rows
    from .electrical import equipment_catalog
    seam=equipment_catalog()['racking'][project.equipment.racking]['module_gap_m']
    slope=(length-(params.rows_per_rack-1)*seam)/params.rows_per_rack
    positions=[np.mean([np.dot(m.corners[0][:2],back)-(m.tier-1)*(slope+seam)*math.cos(math.radians(params.tilt_deg))
               for m in design.modules if m.row==r]) for r in rows]
    return length, np.diff(positions), rows


def walkway_check(project, design):
    params, walkway = design.params, project.requirements.structured.walkway_m_min
    if project.roof.type == 'carport':
        minimum = 5.5 if project.roof.carport.aisles else None
        passed = minimum >= walkway if minimum is not None and walkway is not None else None
        return dict(status='na' if passed is None else 'pass' if passed else 'fail', value=minimum, limit=walkway,
                    suggestion=None, evidence='实际预留5.5米车道；柱不侵占净道', note='倒车垂直停车示例布局')
    length, gaps, rows = row_geometry(project, design)
    walkway_gaps=gaps[params.walkway_every_n_rows-1::params.walkway_every_n_rows] if params.walkway_every_n_rows else gaps
    footprint = design.statistics.get('pair_width_m', length * math.cos(math.radians(params.tilt_deg)))
    net=walkway_gaps-footprint
    minimum=float(net.min()) if len(net) else None
    passed=minimum>=walkway-.002 if walkway is not None and minimum is not None else None
    operation={'op':'set_param','name':'walkway_every_n_rows' if not params.walkway_every_n_rows else 'walkway_width_m',
               'value':1 if not params.walkway_every_n_rows else walkway}
    note='只有一排，没有排间通道' if len(rows)<2 else '未到指定通道位置' if minimum is None else ''
    evidence=f'前后排最小净距 {minimum:.3f} m {"≥" if passed else "<"} 要求 {walkway:g} m' if passed is not None else note or '用户未要求通道宽度'
    return dict(status='na' if passed is None else 'pass' if passed else 'fail', value=minimum, limit=walkway,
                suggestion=operation if passed is False else None, evidence=evidence, note=note)


def evaluate(project,design,shading,electrical,load,economics=None):
    from .installation import effective, facilities
    project = effective(project, design)
    requirement=project.requirements.structured
    params=design.params
    if project.roof.use is not None:
        from .livestock import facts
        load['livestock'] = facts(project, design)
    records=[]
    spec={row[0]:row for row in REGISTRY}
    def add(identifier,passed,value,limit,unit='',evidence='',suggestion=None,hint='',note='',source=None,level=None):
        _,name,category,default_level,kind,reference=spec[identifier]
        level=level or default_level
        status='na' if passed is None else 'pass' if passed else 'fail'
        records.append(dict(id=identifier,name_zh=name,category=category,source_type=kind,source_ref=source or reference,
                            level=level,status=status,value=value,limit=limit,unit=unit,evidence=evidence or f'{value}；限值{limit}',
                            suggestion=suggestion if status=='fail' else None,hint_zh=hint if status=='fail' else '',note=note))
    active=project.model_copy(deep=True)
    active.roof.keepouts+=design.added_keepouts
    geometry=usable_geometry(active,params)
    if project.roof.type == 'ground':
        from shapely.ops import unary_union
        geometry['usable'] = geometry['usable'].difference(unary_union([Polygon(p) for p in design.statistics.get('roads', [])]))
    footprints={m.id:Polygon([p[:2] for p in m.corners]) for m in design.modules}
    bad=[identifier for identifier,polygon in footprints.items() if not geometry['usable'].buffer(.001).covers(polygon)]
    if project.roof.type in ('pitched', 'carport'):
        from .pitched import geometry as face_geometry, conflicting_modules
        if project.roof.type == 'carport':
            from .installation import face_geometry
        from .roofplane import member
        conflicts = conflicting_modules(design.modules)
        for plane in project.roof.planes:
            usable = face_geometry(active, params, plane)['usable'].buffer(.001)
            bad = [mid for mid, polygon in footprints.items() if member(project.roof, mid).id == plane.id
                   and (plane.material == 'glass' or not usable.covers(polygon) or mid in conflicts)]
            add('G01', not bad, len(bad), 0, '块', suggestion=dict(op='remove_modules', module_ids=bad),
                hint='删除越过坡面边界或与其他坡面组件相交的组件')
            records[-1]['plane'] = plane.id
    else:
        add('G01',not bad,len(bad),0,'块',suggestion={'op':'remove_modules','module_ids':bad},hint='删除避让区域内的组件')
    metal = project.roof.type in ("metal", 'pitched', 'carport')
    mixed = len(orientation.groups(design)) > 1
    for identity, view in orientation.views(design):
        length, gaps, rows = row_geometry(project, view)
        needed = (row_spacing(project.site.lat, project.site.lon, view.params.tilt_deg, length,
                              view.params.azimuth_deg, view.params.winter_window_hours,
                              orientation_group=mixed or 'group_row_positions' in view.statistics)
                  ['row_spacing_m'] if length > 0 and not metal else 0)
        actual=float(gaps.min()) if len(gaps) else None
        add('G02',None if metal else actual is None or actual>=needed-.002,actual,needed,'m',
            suggestion={'op':'set_param','name':'winter_window_hours','value':[9,15]},hint='用冬至真太阳9至15窗口重新排板',
            note='2024改为宜；屋顶旧条文删除，本项目建议级保守规则',source=STANDARD+' 7.2.2(2)')
        if params.winter_window_hours != (9, 15):
            window = params.winter_window_hours
            records[-1].update(name_zh=f'冬至真太阳{window[0]:g}–{window[1]:g}时前后排不遮挡',
                               note=records[-1]['note'] + '；按本设计窗口校核，与国标建议9–15时区分')
            records[-1]['suggestion'] = None if records[-1]['status'] != 'fail' else dict(
                op='set_param', name='winter_window_hours', value=list(window))
            if records[-1]['status'] == 'fail':
                records[-1]['hint_zh'] = '按本设计冬至窗口重新排板'
        if mixed:
            records[-1]['group'] = identity
        walkway = walkway_check(project, view)
        add('G03',None if walkway['status']=='na' else walkway['status']=='pass',walkway['value'],walkway['limit'],'m',
            walkway['evidence'],suggestion=walkway['suggestion'],hint='设置通道排数及净宽',note=walkway['note'])
        if mixed:
            records[-1]['group'] = identity
    zones={o.id:obstacle_polygon(o) for o in active.roof.obstacles}|{k.id:Polygon(k.polygon) for k in active.roof.keepouts}
    occupied=[z for z in requirement.keep_clear_ids if z not in zones or any(p.intersects(zones[z]) for p in footprints.values())]
    zone=next((z for z in occupied if z in zones),None)
    add('G04',not occupied if requirement.keep_clear_ids else None,occupied,0,'区域',
        suggestion={'op':'remove_modules','where':{'zone_id':zone}} if zone else None,hint='清空指定区域；不存在的编号请修正要求')
    bounds=requirement.tilt_deg_range
    for identity, view in orientation.views(design):
        fixed_roof = project.roof.type in ('metal', 'pitched')
        add('G05',None if fixed_roof else bounds[0]<=view.params.tilt_deg<=bounds[1] if bounds else None,view.params.tilt_deg,bounds,'°',
            suggestion={'op':'set_param','name':'tilt_deg','value':min(max(view.params.tilt_deg,bounds[0]),bounds[1])} if bounds else None,
            hint='调整倾角至要求范围',note=f'彩钢瓦倾角等于坡度 {view.params.tilt_deg:g}°' if metal else '')
        if mixed:
            records[-1]['group'] = identity
    requirements=[('edge_setback_m',requirement.edge_setback_m_min),('obstacle_clearance_m',requirement.obstacle_clearance_m_min)]
    unmet=[(key,value) for key,value in requirements if value is not None and getattr(params,key)<value]
    add('G06',not unmet if any(v is not None for _,v in requirements) else None,
        {k:getattr(params,k) for k,_ in requirements},dict(requirements),'m',
        suggestion={'op':'set_param','name':unmet[0][0],'value':unmet[0][1]} if unmet else None,hint='提高避让参数后重新排板')
    losses={m['id']:m['total_loss_pct'] for m in shading['modules']}
    maximum=max(losses.values(),default=0)
    add('S01',maximum<=config.SHADING_THRESHOLD_PCT,maximum,config.SHADING_THRESHOLD_PCT,'%',
        suggestion={'op':'remove_modules','where':{'shading_loss_gt':config.SHADING_THRESHOLD_PCT}},hint='移除遮挡损失过高的组件',note='示意，可改')
    average=shading['summary']['avg_loss_pct']
    add('S02',average<=config.SHADING_AVG_THRESHOLD_PCT,average,config.SHADING_AVG_THRESHOLD_PCT,'%',hint='减少高遮挡组件后重算',note='示意，可改')
    for identifier,result in electrical['checks'].items():
        if identifier=='E09':
            groups={}
            identities = {m.id: orientation.key(m) for m in design.modules}
            orientations = {}
            for string in electrical['strings']:
                groups.setdefault((string['inverter'],string['mppt']),set()).add(len(string['module_ids']))
                orientations.setdefault((string['inverter'], string['mppt']), set()).update(
                    identities.get(mid) for mid in string['module_ids'])
            consistent=all(len(lengths)<=1 for lengths in groups.values())
            consistent = consistent and all(len(values) <= 1 and None not in values for values in orientations.values())
            result=dict(result,status='pass' if consistent else 'fail',value=[sorted(v) for v in groups.values()],
                        evidence=f'同路串长集合{[sorted(v) for v in groups.values()]}')
            if mixed:
                result['evidence'] += f'；同路朝向组数{[len(values) for values in orientations.values()]}，每路限1组'
        size=electrical['min_modules_per_string'] if identifier=='E03' else electrical['max_modules_per_string']
        suggestion=({'op':'set_string_size','modules_per_string':max(size,1)} if identifier in ['E01','E02','E03','E04','E09']
                    else {'op':'remove_modules','module_ids':electrical['unused_modules']} if identifier=='E08' else None)
        add(identifier,result['status']=='pass',result['value'],result['limit'],result['unit'],result['evidence'],suggestion,
            result.get('hint_zh') or '调整组串；电流或容配比不合格时更换型号或减少每路串数',note='示意，可改' if identifier=='E07' else '',
            source=result.get('source_ref'),level=result.get('level'))
    if project.roof.type == 'pitched':
        for row in load['planes']:
            add('L01', row['status'] == 'pass', row['added_kn_m2'], row['capacity_kn_m2'], 'kN/㎡',
                evidence=f"P{row['id']}最不利{row['worst_zone']}；{row['capacity_source']}；核定={row['verified']}",
                hint='请结构人员复核此坡面及固定支架与主体连接', note=load['note'])
            records[-1]['plane'] = row['id']
    elif project.roof.type in ('ground', 'carport'):
        add('L01', None, None, None, evidence=load['evidence'], note=load['note'])
        records[-1].update(source_ref='新建基础与钢结构厂家设计（示意，待专业复核）', source_type='示意')
        records[-1]['name_zh'] = '新建基础及结构由厂家设计'
    else:
        add('L01',load['added_kn_m2']<=load['capacity_kn_m2'],load['added_kn_m2'],load['capacity_kn_m2'],'kN/㎡',load['evidence'],
            hint=('业主要求只用压载、不打孔：压块超过屋面承重，需核实承重或同意用锚栓固定' if requirement.ballast_only
                  else '请结构人员复核承重或调整支架方案，不能减少抗风所需压块'),note=load['note'])
    wind_result = load.get('wind', {})
    clamp_failures = wind_result.get('clamp_failed')
    applicable = (project.roof.type == 'metal' or any('clamps' in r for r in wind_result.get('modules', []))) and clamp_failures is not None
    add('W01', clamp_failures == 0 if applicable else None, clamp_failures, 0, '块组件',
        evidence=f"需求{wind_result.get('clamp_required', 0)}个；实际布点{wind_result.get('clamp_count', 0)}个；同时核对最大间距",
        hint='换抗拔力更大的夹具，或请厂家复核', note=wind_result.get('note', '旧记录未计算抗风揭'))
    capacity=electrical['dc_kw']
    add('U01',capacity>=requirement.capacity_kw_min if requirement.capacity_kw_min is not None else None,capacity,
        requirement.capacity_kw_min,'kW',hint='调整倾角或横放以提高容量')
    upper=requirement.capacity_kw_max
    count=min(len(design.modules),math.ceil((capacity-upper)/(capacity/len(design.modules)))) if upper is not None and capacity>upper and design.modules else 0
    add('U02',capacity<=upper if upper is not None else None,capacity,upper,'kW',
        suggestion={'op':'remove_modules','where':{'worst_count':count}},hint='按遮挡损失优先删除多余容量')
    if economics is not None:
        budget=requirement.budget_cny_max
        capex=economics['capex_cny']
        count=min(len(design.modules),math.ceil((capex-budget)/(capex/len(design.modules)))) if budget is not None and capex>budget and design.modules else 0
        add('U03',capex<=budget if budget is not None else None,capex,budget,'元',
            evidence=f"分项或手填造价合计{capex:g}元；预算{budget}；删板按平均每块摊销估算，须重新核价",
            suggestion={'op':'remove_modules','where':{'worst_count':count}} if count else None,hint='减少组件以满足预算；复算容量和电气规则')
        payback=economics.get('u04_payback_years', economics['payback_years'])
        target=requirement.payback_years_max
        add('U04',payback is not None and payback<=target if target is not None else None,payback,target,'年',
            evidence=f'现金流年内插值静态回本={payback}年；用户上限={target}年',hint='核实造价、自用比例及电价，或调整回本要求；重算比较后再决定')
    from .personal import transformer_limit, phased, tilt_bounds
    from .electrical import equipment_catalog
    from .roofplane import elevation
    if project.roof.type == 'ground':
        lowest = min((p[2] for m in design.modules for p in m.corners), default=None)
        required = params.lower_edge_m if params.lower_edge_m is not None else project.roof.ground.lower_edge_m
        if project.roof.use == 'grazing':
            required = max(required, load['livestock']['animal_min_m'])
        add('G08', lowest >= required - 1e-9 if lowest is not None else None, lowest, required, 'm',
            evidence='实际全部组件角点相对地坪最低值；显式用户高度优先', hint='提高组件实际离地高度并重新排板',
            suggestion=dict(op='set_param', name='lower_edge_m', value=required) if project.roof.use == 'grazing' else None)
        if project.roof.use == 'grazing':
            grazing = load['livestock']
            light = grazing['ground_light']['sun_pct']
            limit = grazing['required_sun_pct']
            gap = design.params.extra_row_gap_m or 0
            add('G10', light is not None and light >= limit - 1e-9, light, limit, '%',
                evidence=grazing['ground_light']['method'], hint='加大排距并重新分析；场外遮挡仍需现场核实',
                suggestion=dict(op='set_param', name='extra_row_gap_m', value=min(30, gap + 1)) if gap < 30 else None,
                note='几何直射受光面积比例，不是牧草生长预测；要求为示意')
    if project.roof.type == 'carport':
        clear = min((f['clear_height_m'] for f in facilities(project, design)['faces']), default=None)
        required = max(2.2, project.roof.carport.clear_height_m)
        add('G09', clear >= required - 1e-9 if clear is not None else None, clear, required, 'm',
            evidence='实际棚面最低角点减明确的竖向结构深度', hint='提高棚面或调整厂家核定的结构深度',
            note='2.2米为车库小型车项目参照；开放车棚适用性待设计确认，不宣称全国所有车棚强制值')
    if requirement.max_height_m is not None:
        highest = max((p[2] - elevation(project.roof, p) for m in design.modules for p in m.corners), default=0)
        if project.roof.type in ('ground', 'carport'):
            highest = max((p[2] for m in design.modules for p in m.corners), default=0)
        suggestion = None
        if not metal:
            try:
                suggestion = dict(op='set_param', name='tilt_deg', value=tilt_bounds(project, design.params)[1])
            except GzError:
                pass
        add('G07', highest <= requirement.max_height_m + .001, highest, requirement.max_height_m, 'm',
            suggestion=suggestion, hint='按限高重新排板，每个斜面一排；金属屋面保持顺坡')
    limit = transformer_limit(project)
    catalog = equipment_catalog()
    power = catalog['modules'][project.equipment.module_id]['pmax_w'] / 1000
    if limit is not None:
        ac = sum(catalog['inverters'][u['inverter_id']]['rated_ac_kw'] for u in electrical['per_inverter'])
        count = min(len(design.modules), max(1, math.ceil(max(capacity - limit, ac - limit) / power)))
        phase_count = sum(m.phase == 1 for m in design.modules)
        if 0 < phase_count < len(design.modules):
            count = min(count, len(design.modules) - phase_count)
        add('U06', ac <= limit + 1e-9, ac, limit, 'kW', suggestion=dict(op='remove_modules', where=dict(worst_count=count)),
            hint='按最差组件减装后重新选型，核对全站两期逆变器合计', evidence=f'额定交流合计{ac:g}kW；变压器×比例={limit:g}kW')
    if requirement.export_allowed is False:
        cap = (economics or {}).get('curtailment', {})
        add('U05', cap['pct'] <= cap['limit'] + 1e-9 if 'pct' in cap else None, cap.get('pct'),
            cap.get('limit', requirement.curtail_pct_max if requirement.curtail_pct_max is not None else 10), '%',
            suggestion=dict(op='remove_modules', where=dict(worst_count=cap.get('worst_count', 0))),
            hint='按逐时比例估算删板后重算', note=cap.get('note', '填了月用电量和班次，才能按用电封顶'))
    if phased(project):
        connected = {mid for s in electrical['strings'] if s.get('phase') == 1 for mid in s['module_ids']}
        kw = len(connected) * power
        from .economics import resolve_parameters
        cost = design.statistics.get('phasing', {}).get('achieved_cny', 0)
        if (economics or {}).get('phases'):
            cost = economics['phases'][0]['capex_cny']
        budget = requirement.phase1_budget_cny
        passed = bool(connected) and (cost <= budget + .001 if budget is not None else kw >= requirement.phase1_kw - 1e-9)
        add('U07', passed, cost if budget is not None else kw, budget if budget is not None else requirement.phase1_kw,
            '元' if budget is not None else 'kW', hint='一期不足整串或目标不可达；核对预算、容量和组串',
            note=(f'一期实际{kw:g}kW/{cost:g}元；预算{budget:g}元，余额{budget - cost:g}元；'
                  + ('不足以形成非空完整组串' if not connected else '按预算及全站条件向下取完整串前缀')) if budget is not None
                  else f'目标{requirement.phase1_kw:g}kW，实际{kw:g}kW；装机向上整串，未接入板不计达标')
    return summarize(records)


def summarize(records):
    order=lambda r:0 if r['status']=='fail' and r['level']=='hard' else 1 if r['status']=='fail' else 2 if r['status']=='pass' else 3
    records=sorted(records,key=lambda r:(order(r),r['id']))
    return dict(total=len(records),passed=sum(r['status']=='pass' for r in records),
                hard_failed=sum(r['status']=='fail' and r['level']=='hard' for r in records),
                warnings=sum(r['status']=='fail' and r['level']=='advice' for r in records),na=sum(r['status']=='na' for r in records),items=records)


def save_result(project_id,version,name,result):
    path=storage._path(project_id,f'analysis/v{version}/{name}.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def check(project_id,version,*,offline=False):
    from . import electrical,structure,shading
    project,design=storage.load(project_id),storage.load_design(project_id,version)
    path=storage._path(project_id,f'analysis/v{version}/shading.json')
    shadows=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    digest = hashlib.sha256(storage._path(project_id, f'designs/v{version}.json').read_bytes()).hexdigest()
    if not shadows or shadows.get('version') != version or shadows.get('metadata', {}).get('design_sha256') != digest:
        shadows = shading.analyze(project_id, version, offline=offline)
    started=time.perf_counter()
    electric=electrical.calculate(project,design,offline=offline,shadows=shadows)
    load=structure.calculate(project,design)
    rules=evaluate(project,design,shadows,electric,load)
    rules['elapsed_seconds']=time.perf_counter()-started
    for name,result in [('electrical',electric),('structure',load),('rules',rules)]:
        save_result(project_id,version,name,result)
    return rules


def write_markdown():
    lines=['# 规则清单','', 'G02为建议级屋顶保守规则；2024局部修订7.2.2为“宜”，旧屋顶7.2.3删除。','',
           '| 编号 | 名称 | 等级 | 来源类型 | 出处 | 限值 |','| --- | --- | --- | --- | --- | --- |']
    limits={'G01':'违规0块，几何容差1mm','G02':'2025冬至真太阳9–15时',
            'G03':'排间实际净距≥requirements.walkway_m_min；未给或少于2排为na','G04':'requirements.keep_clear_ids内0块；未给为na',
            'G05':'requirements.tilt_deg_range；未给为na','G06':'requirements的边距/障碍距离下限；未给为na',
            'S01':f'{config.SHADING_THRESHOLD_PCT}%（示意）','S02':f'{config.SHADING_AVG_THRESHOLD_PCT}%（示意）',
            'E01':'逆变器1100 V','E02':'组件1500 V','E03':'阳光180 V；华为200 V（运行MPPT下限）',
            'E04':'1000 V（运行MPPT上限；厂家附加校核）','E05':'阳光50 A；华为40 A/MPPT',
            'E06':'30 A/MPPT','E07':f'整体和每台≤{config.DC_AC_MAX}为硬性；整体<{config.DC_AC_MIN}为建议，目标{config.DC_AC_TARGET}（示意）',
            'E08':'剩余0块','E09':'同路串长相同','E10':'2%及载流量合格（示意）','E11':'2%及载流量合格（示意）',
            'L01':'roof.load_capacity_kn_m2（用户核定值）',
            'U01':'requirements.capacity_kw_min；未给为na','U02':'requirements.capacity_kw_max；未给为na',
            'U03':'requirements.budget_cny_max；未给为na','U04':'requirements.payback_years_max；未给为na',
            'U05':'不上网限电≤curtail_pct_max或示意10%；缺用电数据为na','U06':'额定AC合计≤transformer_kva×share（示意默认0.8）',
            'U07':'一期kW向上整串；预算硬帽向下整串且非空','G07':'每块组件最高点−局部屋面≤max_height_m',
            'G08':'空地实际角点最低高≥用户离地要求；未指定0.5m示意默认',
            'G09':'车棚最低棚面−竖向结构深度≥max(2.2m车库参照,用户净高要求)',
            'G10':'牧光代表日地面受光比例≥50%（默认示意）；按原场地面积'}
    for identifier,name,category,level,kind,reference in REGISTRY:
        link=STANDARD+'；'+reference if kind=='国家标准' else 'data/catalog/（厂家官方链接、页码）；'+reference if kind=='厂家规格书' else reference
        level='hard（上限）/advice（下限）' if identifier=='E07' else level
        lines.append(f'| {identifier} | {name} | {level} | {kind} | {link} | {limits[identifier]} |')
    from .electrical import equipment_catalog
    lines+=['','E04沿用任务卡公式；2024修订6.4.2已删除旧MPPT上界公式，现标厂家规格书附加检查。',
            '满载MPPT范围按各型号记录在设备表；上述电气检查使用运行范围。',
            '自动串数取ceil(组件数/可行上限)，平均分为相差1块的两种串长，短串不低于下限；指定n时只用n和n−1，凑不齐则保留余板。',
            '组串按各台额定容量均衡分配，同一路MPPT只接同长度；优先空MPPT再并串；E05/E06及E07逐台按自己的型号检查。',
            'G03未专门设置通道时检查所有现有排间净距；启用通道时检查指定位置；少于2排为不适用。','', '厂家出处（访问2026-10-01）：']
    for group in ['modules','inverters']:
        for row in equipment_catalog()[group].values():
            lines.append(f"- [{row['model']}]({row['datasheet_url']})；{row['datasheet_version']}，PDF第{row['datasheet_page']}页。")
    (config.ROOT/'docs/rules.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')


def plot_strings(project,design,electrical,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as Patch
    figure,ax=plt.subplots(figsize=(11,7))
    ax.plot(*Polygon(project.roof.outline).exterior.xy,color='#243746')
    modules={m.id:m for m in design.modules}
    colors=plt.get_cmap('turbo')
    for i,string in enumerate(electrical['strings']):
        for identifier in string['module_ids']:
            m=modules[identifier]
            ax.add_patch(Patch(np.array(m.corners)[:,:2],facecolor=colors(i/max(len(electrical['strings'])-1,1)),edgecolor='white',linewidth=.2))
        center=modules[string['module_ids'][0]].center
        ax.text(center[0],center[1],f"I{string['inverter']}/M{string['mppt']}",fontsize=5)
    for identifier in electrical['unused_modules']:
        ax.add_patch(Patch(np.array(modules[identifier].corners)[:,:2],facecolor='#b83c28',hatch='//'))
    cable = electrical.get('cables', {})
    for kind, color in [('dc', '#b83c28'), ('ac', '#007b68')]:
        for row in cable.get(kind, []):
            ax.plot(*zip(*row['route']), color=color, linewidth=.6, alpha=.65)
    for row in cable.get('positions', []):
        ax.plot(*row['point'], marker='s', color='#243746')
        ax.annotate(row['label'], row['point'])
    ax.set(aspect='equal',xlabel='East (m)',ylabel='North (m)',
           title=f"{electrical['inverter_id']} x {electrical['inverter_count']} / {len(electrical['strings'])} strings")
    figure.tight_layout()
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    figure.savefig(path,dpi=160)
    plt.close(figure)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['list','check'])
    parser.add_argument('--markdown',action='store_true')
    parser.add_argument('--project')
    parser.add_argument('--version',type=int)
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.command=='list':
            write_markdown()
            output={'rules':len(REGISTRY),'file':'docs/rules.md'}
        else:
            if not args.project or not args.version:
                parser.error('check requires --project and --version')
            result=check(args.project,args.version,offline=args.offline)
            electrical=json.loads(storage._path(args.project,f'analysis/v{args.version}/electrical.json').read_text(encoding='utf-8'))
            plot_strings(storage.load(args.project),storage.load_design(args.project,args.version),electrical,config.ROOT/'reports/assets/T06-strings.png')
            output={k:v for k,v in result.items() if k!='items'}
        print(json.dumps(dict(ok=True,**output),ensure_ascii=False))
        return 0
    except GzError as error:
        print(json.dumps(error.as_dict(),ensure_ascii=False))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
