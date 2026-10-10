"""Optional owner constraints and deterministic phased construction."""
import copy
import itertools
import math
from .models import GzError, LayoutParams


def transformer_limit(project):
    req = project.requirements.structured
    return req.transformer_kva * (req.transformer_share or .8) if req.transformer_kva is not None else None


def phased(project):
    req = project.requirements.structured
    return req.phase1_kw is not None or req.phase1_budget_cny is not None


def tilt_bounds(project, params):
    from .layout import _catalog
    req = project.requirements.structured
    low, high = req.tilt_deg_range or (0, 35)
    if req.max_height_m is not None:
        module, _, height = _catalog(project, params)
        if project.roof.type == 'ground':
            height = params.lower_edge_m if params.lower_edge_m is not None else project.roof.ground.lower_edge_m
        length = float(module['length_m' if params.orientation == 'portrait' else 'width_m'])
        if req.max_height_m < height:
            raise GzError('HEIGHT_CONFLICT', f'限高{req.max_height_m:g}m低于组件离屋面{height:g}m', '提高限高')
        if project.roof.type == 'metal':
            return project.roof.slope_deg, project.roof.slope_deg
        high = min(high, math.degrees(math.asin(min(1, (req.max_height_m - height) / length))))
    if params.layout == 'ew':
        low, high = max(5, low), min(15, high)
    if low > high:
        raise GzError('HEIGHT_CONFLICT', '限高与倾角范围或东西向5–15°要求冲突', '调整限高、倾角范围或排布方式')
    return low, high


def curtailment(project, energy, count):
    from .economics import load_curve
    req, economy = project.requirements.structured, project.economics
    if economy.monthly_kwh is None or economy.shifts is None or 'hourly' not in energy:
        return dict(note='填了月用电量和班次，才能按用电封顶')
    hourly = energy['hourly']
    loads = load_curve(economy.monthly_kwh, economy.shifts, hourly['utc'])
    produced = math.fsum(hourly['kwh'])
    limit = req.curtail_pct_max if req.curtail_pct_max is not None else 10
    def percent(removed):
        scale = (count - removed) / count if count else 0
        used = math.fsum(min(g * scale, load) for g, load in zip(hourly['kwh'], loads, strict=True))
        return 100 * (1 - used / (produced * scale)) if produced * scale else 0
    low, high = 0, count
    while low < high:
        mid = (low + high) // 2
        if percent(mid) <= limit + 1e-9:
            high = mid
        else:
            low = mid + 1
    return dict(pct=percent(0), limit=limit, worst_count=low, modules=count, generation_kwh=produced,
                note='按组件数与逐时发电同比例缩小的二分估算；删板后须重新分析，默认10%为示意')


def prepare(project, design, *, offline=False, shadows=None):
    from . import electrical, shading, economics
    if not phased(project):
        for module in design.modules:
            module.phase = None
        design.statistics.pop('phasing', None)
        return design
    if not design.modules:
        return design
    shadows = shadows or shading.analyze_design(project, design, offline=offline)
    ordinary = design.model_copy(deep=True)
    for module in ordinary.modules:
        module.phase = None
    electric = electrical.calculate(project, ordinary, offline=offline, shadows=shadows)
    grid = next(p['point'] for p in electric['cables']['positions'] if p['label'] == 'GRID')
    losses = {row['id']: row['total_loss_pct'] for row in shadows['modules']}
    ordered = sorted(design.modules, key=lambda m: (losses[m.id], math.dist(m.center[:2], grid), m.id))
    req = project.requirements.structured
    power = electrical.equipment_catalog()['modules'][project.equipment.module_id]['pmax_w'] / 1000
    if req.phase1_kw:
        target = math.ceil(req.phase1_kw / power)
    else:
        from .costs import catalog as cost_catalog
        prices = cost_catalog()
        manual = project.economics.capex_cny_per_w
        minimum_per_w = manual if manual is not None else prices['module']['value'] + prices['installation']['value']
        maximum = math.floor(req.phase1_budget_cny / (power * 1000 * minimum_per_w)) if minimum_per_w else len(ordered)
        target = min(len(ordered), maximum)
    counts = range(max(1, target), len(ordered) + 1) if req.phase1_kw else range(min(target, len(ordered)), 0, -1)
    chosen, fallback, chosen_cost = 0, 0, 0
    catalog, limit = electrical.equipment_catalog(), transformer_limit(project)
    for count in counts:
        halves = [ordered[:count], ordered[count:]]
        choices = [[r for r in electrical.calculate(project, design.model_copy(update=dict(modules=members)),
                    offline=offline, options=True) if not r['unused_modules']] for members in halves if members]
        if not all(choices):
            continue
        from .costs import itemized
        first_ids = {m.id for m in halves[0]}
        first_members = [m.model_copy(update=dict(phase=None)) for m in design.modules if m.id in first_ids]
        first_view = design.model_copy(deep=True, update=dict(modules=first_members))
        if project.roof.type in ('pitched', 'ground', 'carport'):
            first_view.statistics['phasing'] = dict(grid_point=grid, grid_default=project.roof.grid_point is None)
        first_electric = electrical.calculate(project, first_view, offline=offline, shadows=shadows)
        first_cost = itemized(project, count * power, first_view, first_electric)['capex_cny']
        if req.phase1_budget_cny is not None and first_cost > req.phase1_budget_cny + .001:
            continue
        if all(choices) and not fallback:
            fallback = count
            chosen_cost = first_cost
        if all(choices) and any(limit is None or sum(catalog['inverters'][u['inverter_id']]['rated_ac_kw']
            for r in combination for u in r['per_inverter']) <= limit + 1e-9 for combination in itertools.product(*choices)):
            chosen = count
            chosen_cost = first_cost
            break
    chosen = chosen or fallback
    for index, module in enumerate(ordered):
        module.phase = 1 if index < chosen else 2
    design.statistics['phasing'] = dict(target_kw=req.phase1_kw, budget_cny=req.phase1_budget_cny,
        achieved_kw=chosen * power, achieved_cny=chosen_cost, grid_point=grid, grid_default=project.roof.grid_point is None,
        remainder_cny=req.phase1_budget_cny - chosen_cost if req.phase1_budget_cny is not None else None,
        note='按遮挡、距并网点、编号排序；装机向上整串，预算硬帽向下整串；不足一串时一期为空')
    return design


def phase_electrical(project, design, *, offline=False, shadows=None):
    from . import electrical, cables
    catalog = electrical.equipment_catalog()
    views = [design.model_copy(update=dict(modules=[m for m in design.modules if m.phase == phase])) for phase in (1, 2)]
    views = [view for view in views if view.modules]
    choices = [electrical.calculate(project, view, offline=offline, options=True) for view in views]
    combinations = list(itertools.product(*choices))
    ac = lambda rows: sum(catalog['inverters'][u['inverter_id']]['rated_ac_kw'] for row in rows for u in row['per_inverter'])
    limit = transformer_limit(project)
    feasible = [rows for rows in combinations if limit is None or ac(rows) <= limit + 1e-9]
    def rank(rows):
        checks = [c for row in rows for key, c in row['checks'].items() if key != 'E06' and c.get('level') != 'advice']
        return sum(c['status'] == 'fail' for c in checks), sum(abs(r['dc_ac_ratio'] - electrical.DC_AC_TARGET) for r in rows), ac(rows)
    selected = min(feasible or combinations, key=rank)
    parts = [electrical.calculate(project, view, offline=offline, shadows=shadows, selected=row) for view, row in zip(views, selected)]
    result = copy.deepcopy(parts[0])
    for key in ('strings', 'per_inverter', 'mppt_currents', 'unused_modules', 'inverters'):
        result[key] = []
    for view, part in zip(views, parts):
        phase, offset = view.modules[0].phase, len(result['per_inverter'])
        for key in ('strings', 'per_inverter', 'mppt_currents'):
            for original in part[key]:
                row = copy.deepcopy(original)
                row.update(phase=phase, inverter=row['inverter'] + offset)
                if key == 'strings':
                    row['id'] = f"P{phase}-" + row['id']
                    row['voc_cold_v'] = part['voc_cold_v'] * row['module_count'] / part['modules_per_string']
                    row['vmp_hot_v'] = part['vmp_hot_v'] * row['module_count'] / part.get('modules_per_string_short', part['modules_per_string'])
                if 'string_ids' in row:
                    row['string_ids'] = [f'P{phase}-' + value for value in row['string_ids']]
                for assignment in row.get('mppt_assignments', []):
                    assignment['string_ids'] = [f'P{phase}-' + value for value in assignment['string_ids']]
                result[key].append(row)
        result['unused_modules'] += part['unused_modules']
        result['inverters'] += [dict(row, phase=phase) for row in part['inverters']]
    for key in ('dc_kw', 'connected_dc_kw', 'module_count', 'inverter_count', 'string_count'):
        result[key] = sum(part[key] for part in parts)
    result['dc_ac_ratio'] = result['dc_kw'] / ac(parts) if ac(parts) else 0
    for key, pick in (('voc_cold_v', max), ('vmp_cold_v', max), ('vmp_hot_v', min), ('modules_per_string', max)):
        result[key] = pick(p[key] for p in parts)
    shortest = min(p.get('modules_per_string_short', p['modules_per_string']) for p in parts)
    if shortest < result['modules_per_string']:
        result['modules_per_string_short'] = shortest
    for code in result['checks']:
        values = [part['checks'][code] for part in parts]
        result['checks'][code] = copy.deepcopy(min(values, key=lambda c: (c['status'] != 'fail', c.get('level') == 'advice')))
        result['checks'][code]['evidence'] = '；'.join(f"{v.modules[0].phase}期：{c['evidence']}" for v, c in zip(views, values))
    result['checks']['E08']['value'] = len(result['unused_modules'])
    for code in ('E05', 'E06'):
        result['checks'][code]['per_mppt'] = result['mppt_currents']
    result['checks']['E07']['per_inverter'] = result['per_inverter']
    result['checks']['E07']['value'] = result['dc_ac_ratio']
    result['metadata']['inverter_source'] = '；'.join(dict.fromkeys(p['metadata']['inverter_source'] for p in parts))
    result['phases'] = [dict(phase=v.modules[0].phase, dc_kw=p['dc_kw'], inverters=p['inverters']) for v, p in zip(views, parts)]
    result['selection_reason'] = '两期独立选型、全站变压器上限联合筛选；无可行组合时保留失败诊断'
    result['wiring'] = dict(method='分期独立接线', reason='；'.join(p['wiring']['reason'] for p in parts))
    routing = project.model_copy(deep=True)
    routing.roof.grid_point = design.statistics.get('phasing', {}).get('grid_point', routing.roof.grid_point)
    result = cables.calculate(routing, design, result, catalog)
    grid = next(p for p in result['cables']['positions'] if p['label'] == 'GRID')
    if design.statistics.get('phasing', {}).get('grid_default'):
        grid.update(default=True, note='分期排序所用默认并网点；示意，按现场改')
    return result


def phase_cash(project, design, shadows, cash, *, offline=False, cost_scale=None):
    from . import analysis, economics, electrical, shading, structure
    members = [m for m in design.modules if m.phase == 1]
    if not members:
        return
    view = design.model_copy(update=dict(modules=members))
    shade = shading.analyze_design(project, view, offline=offline)
    power = electrical.equipment_catalog()['modules'][project.equipment.module_id]['pmax_w'] / 1000
    energy, _ = analysis.generation(project, view, shade, len(members) * power, offline=offline)
    electric = electrical.calculate(project, view, offline=offline, shadows=shade)
    phase_load = structure.calculate(project, view)
    first_project = project.model_copy(deep=True)
    if cost_scale is not None:
        from .costs import itemized
        first_project.economics.capex_cny_per_w = None
        amount = itemized(first_project, len(members) * power, view, electric, phase_load)['capex_cny']
        first_project.economics.capex_cny_per_w = amount * cost_scale / (len(members) * power * 1000)
    first = economics.calculate(first_project, len(members) * power, energy,
                                design=view, electric=electric, load=phase_load, sensitivity=False)
    fields = ('capex_cny', 'payback_years', 'profit_cny', 'operating_net_cny')
    cash['phases'] = [dict(name=name, **{k: value[k] for k in fields}) for name, value in [('一期单独', first), ('两期合计', cash)]]
    cash['phases'].append(dict(name='二期增加', capex_cny=cash['capex_cny'] - first['capex_cny'], payback_years=None,
        profit_cny=cash['profit_cny'] - first['profit_cny'], operating_net_cny=cash['operating_net_cny'] - first['operating_net_cny']))
    cash['phase_cashflows'] = dict(first=first['cashflows'], increment=[
        {key: total[key] - one.get(key, 0) if key != 'year' else total[key] for key in total}
        for one, total in zip(first['cashflows'], cash['cashflows'], strict=True)])
    cash['first_phase_wind'] = phase_load['wind']
    if project.roof.type in ('ground', 'carport'):
        cash['first_phase_facilities'] = phase_load['facilities']
    cash['phase_note'] = '同一基准年比较；二期增加=两期合计−一期单独；未假定开工间隔，共用负荷只计一次'
