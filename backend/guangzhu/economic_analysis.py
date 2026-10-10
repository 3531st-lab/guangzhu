"""Connect engineering quantities, time-of-use energy and annual investor accounts."""
import math
import hashlib
import json
from shapely.geometry import Polygon
from . import costs, finance, tariff

FINANCIAL_KEYS = ('insurance_rate', 'cleaning_times', 'cleaning_per_w', 'replacement_year', 'loan_rate', 'green_price')


def energy_key(project):
    """Prove saved energy/TOU inputs; current shading uses roof-relative geometry."""
    from .economics import resolve_parameters
    from .electrical import equipment_catalog
    from .config import DATA_DIR
    inputs = project.model_dump(mode='json', exclude_none=True)
    for field in ('height_m', 'grid_point', 'inverter_positions'):
        inputs['roof'].pop(field, None)
    module = equipment_catalog()['modules'][project.equipment.module_id]
    record = [inputs, resolve_parameters(project), module,
              (DATA_DIR / 'catalog/tou-jiangsu.csv').read_text(encoding='utf-8-sig'), 'T30-energy/1']
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def cache_key(project, quoted):
    from .economics import resolve_parameters, load_assumptions
    from .config import DATA_DIR
    catalog = costs.catalog()
    used = {key: catalog[key] for key in FINANCIAL_KEYS}
    if project.roof.type == 'ground':
        used['land_rent'] = catalog['land_rent']
    if project.roof.use == 'grazing':
        used.update({key: catalog[key] for key in ('weeding_share', 'grazing_replacement')})
    assumptions = load_assumptions()
    business = {key: assumptions[key] for key in ('emc_discount', 'roof_rent_cny_m2_year')}
    record = [project.model_dump(mode='json', exclude_none=True), quoted, resolve_parameters(project), used, business,
              (DATA_DIR / 'catalog/tou-jiangsu.csv').read_text(encoding='utf-8-sig'), 'T30/1']
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def calculate(project, dc_kw, energy, *, design=None, electric=None, load=None, sensitivity=True):
    from .economics import resolve_parameters, load_assumptions
    if design is not None:
        from .installation import effective
        project = effective(project, design)
    params, sources = resolve_parameters(project)
    quoted = costs.itemized(project, dc_kw, design, electric, load)
    supplied = project.economics
    catalog = costs.catalog()
    if 'hourly' in energy:
        priced = tariff.integrate(project, energy, params['self_use_ratio'], params['price_self_cny_kwh'])
    elif 'tariff_basis' in energy:
        priced = tariff.reprice(project, energy['tariff_basis'], params['price_self_cny_kwh'])
    elif design is not None:
        raise ValueError('工程经济分析缺逐时发电')
    else:
        used = energy['p50'] * params['self_use_ratio']
        priced = dict(self_use_kwh=used, effective_ratio=params['self_use_ratio'], weighted_price_cny_kwh=params['price_self_cny_kwh'],
                      revenue_cny=used * params['price_self_cny_kwh'], load_mode='缺逐时，平价示意', graph=[], bands={},
                      note='低层估算入口缺逐时与工程上下文；不能作为完整项目分时测算。')
    params['self_use_ratio'] = priced['effective_ratio']
    if priced['load_mode'] == '按用电逐时算':
        sources['self_use_ratio'].update(value=params['self_use_ratio'], 数值=str(params['self_use_ratio']), basis='hourly_load',
                                         来源标题='月用电量和班次逐时计算', 状态='示意')
    params['capex_cny_per_w'] = quoted['effective_cny_per_w']
    sources['capex_cny_per_w'].update(value=params['capex_cny_per_w'], 数值=str(params['capex_cny_per_w']),
                                     basis='project.economics' if quoted['manual_override'] else 'costs.csv',
                                     来源标题='手填总价按比例分项' if quoted['manual_override'] else '实际工程分项合计', 状态='示意')
    blocked = project.requirements.structured.export_allowed is False
    exported = max(0, energy['p50'] - priced['self_use_kwh']) if not blocked else 0
    market = params['price_export_cny_kwh']
    mechanism = supplied.mechanism_share or 0
    mechanism_price = supplied.mechanism_price or 0
    mechanism_years = supplied.mechanism_years or 0
    green_share = supplied.green_sold_share or 0
    green_price = catalog['green_price']['value']
    cleaning_times = supplied.cleaning_times if supplied.cleaning_times is not None else catalog['cleaning_times']['value']
    if project.roof.use == 'barn' and supplied.cleaning_times is None:
        cleaning_times *= 2
    base_om = dc_kw * 1000 * params['om_cny_per_w_year']
    weeding = None
    if project.roof.use == 'grazing':
        share = catalog['weeding_share']['value']
        replacement = catalog['grazing_replacement']['value']
        if not 0 <= share <= 1 or not 0 <= replacement <= 1:
            raise ValueError('除草份额和放牧替代比例须在0–1之间')
        saving = base_om * share * replacement
        weeding = dict(original_base_cny=base_om, share=share, replacement=replacement,
                       saving_cny=saving, net_base_cny=base_om - saving, note='仅基础运维除草份额，比例均示意')
        base_om -= saving
    insurance = quoted['capex_cny'] * catalog['insurance_rate']['value']
    cleaning = dc_kw * 1000 * cleaning_times * catalog['cleaning_per_w']['value']
    subsidy = dc_kw * 1000 * .3 if supplied.public_subsidy_confirmed else 0
    subsidy_year = supplied.subsidy_year or 1
    def income(year, factor):
        active = mechanism if year <= mechanism_years else 0
        green = exported * factor * max(0, 1 - active - green_share) / 1000 * green_price
        return green + (subsidy if year == subsidy_year else 0)
    def settlement(year, factor):
        return exported * factor * mechanism * (mechanism_price - market) if year <= mechanism_years else 0
    ordinary = load_assumptions()
    rent = Polygon(project.roof.outline).area * ordinary['roof_rent_cny_m2_year']['value']
    if project.roof.type == 'carport':
        rent = 0
    land_rent = None
    if project.roof.type == 'ground':
        rate = supplied.land_rent_cny_mu_year
        rate = catalog['land_rent']['value'] if rate is None else rate
        land_rent = Polygon(project.roof.outline).area / (2000 / 3) * rate
        rent = 0
    discount = ordinary['emc_discount']['value']
    options = dict(years=int(params['lifetime_years']), degradation=params['degradation_annual_pct'], discount=params['discount_rate'],
                   rent=rent, land_rent=land_rent, emc_discount=discount, replacement=quoted['replacement_cny'],
                   replacement_year=int(catalog['replacement_year']['value']), other=income, sale_adjustment=settlement,
                   tax_holiday=bool(supplied.tax_holiday_confirmed), loan_ratio=supplied.loan_ratio or 0,
                   loan_rate=supplied.loan_rate if supplied.loan_rate is not None else catalog['loan_rate']['value'],
                   loan_years=supplied.loan_years or min(20, int(params['lifetime_years'])))
    accounts = {}
    models = []
    for key, name in (('self', '自投'), ('emc', '合同能源管理'), ('rent', '屋顶租赁')):
        account = finance.ledger(quoted['capex_cny'], quoted['hardware_cny'], priced['revenue_cny'], exported * market,
                                 base_om + insurance + cleaning, mode=key, **options)
        accounts[key] = account
        owner = account['pretax']['cashflows'][1]['net_cny'] if key == 'self' else priced['revenue_cny'] * discount if key == 'emc' else rent
        owner_post = account['posttax']['cashflows'][1]['net_cny'] if key == 'self' else owner * .75 if key == 'emc' else owner / 1.09 * .75
        owner_total = account['pretax']['operating_net_cny'] if key == 'self' else sum(
            priced['revenue_cny'] * discount * (1 - params['degradation_annual_pct'] / 100) ** (y - 1)
            if key == 'emc' else rent for y in range(1, int(params['lifetime_years']) + 1))
        models.append(dict(name=name, owner_capex_cny=quoted['capex_cny'] if key == 'self' else 0,
                           owner_first_year_cny=owner, owner_posttax_first_year_cny=owner_post, owner_total_cny=owner_total,
                           investor_payback_years=account['pretax']['payback_years'], investor_irr_pct=account['pretax']['irr_pct'],
                           investor_posttax_payback_years=account['posttax']['payback_years'],
                           investor_posttax_irr_pct=account['posttax']['irr_pct'], **account))
    own = accounts['self']
    result = dict(own['pretax'], capex_cny=quoted['capex_cny'], costs=quoted, tariff=priced, posttax=own['posttax'],
                  accounts=own['accounts'], params=params, source=sources, business_models=models,
                  input_economics=supplied.model_dump(), assumptions=finance.NOTES,
                  u04_basis='税后' if supplied.posttax_payback else '税前',
                  u04_payback_years=own['posttax' if supplied.posttax_payback else 'pretax']['payback_years'],
                  operating_costs=dict(base_om_cny=base_om, insurance_cny=insurance, cleaning_cny=cleaning,
                                       cleaning_times=cleaning_times, replacement_cny=quoted['replacement_cny'], replacement_year=13))
    if 'loan' in own:
        result['loan'] = own['loan']
    if project.roof.use == 'barn':
        result['operating_costs']['cleaning_basis'] = ('用户显式次数' if supplied.cleaning_times is not None
                                                     else '养殖场默认次数加倍（示意）')
    if weeding is not None:
        result['operating_costs']['weeding'] = weeding
    if project.roof.type == 'carport':
        result['business_models'][2]['name'] = '场地合作（租金未计）'
        result['lease_note'] = '未提供车棚场地或棚面租赁合同；该情景未计租金，不沿用屋顶默认租金，实际支出及出租方收入待核定。'
        result['assumptions'] = [*finance.NOTES[:-1], result['lease_note'], '合同能源管理下业主省下的电费按25%所得税估算。']
    if land_rent is not None:
        result['operating_costs']['land_rent_cny'] = land_rent
        result['land_rent'] = dict(annual_cny=land_rent, area_mu=Polygon(project.roof.outline).area / (2000 / 3),
                                   rate_cny_mu_year=rate, source=catalog['land_rent'],
                                   payer='项目投资人', recipient='土地出租方', recipient_pretax_annual_cny=land_rent,
                                   note='三模式均只扣一次地租；出租方所得税及土地税费未核定，不套用屋顶租赁税务假设')
        result['business_models'][2]['name'] = '场地租赁'
        result['assumptions'] = [*finance.NOTES[:-1], result['land_rent']['note'], '合同能源管理下业主省下的电费按25%所得税估算。']
    effective = priced['effective_ratio']
    reference_ratio = priced.get('reference_self_use_kwh')
    reference_ratio = reference_ratio / energy['p50'] if reference_ratio is not None and energy['p50'] else effective
    result['self_use'] = dict(algorithm='按用电逐时算' if supplied.monthly_kwh and supplied.shifts else priced['load_mode'],
                              effective_ratio=effective, ratio=reference_ratio,
                              self_use_kwh=priced['self_use_kwh'], export_kwh=exported,
                              curtailed_kwh=energy['p50'] - priced['self_use_kwh'] - exported,
                              weighted_price_cny_kwh=priced['weighted_price_cny_kwh'],
                              annual_load_kwh=supplied.monthly_kwh * 12 if supplied.monthly_kwh else None,
                              reference_self_use_kwh=priced.get('reference_self_use_kwh'),
                              manual_override=supplied.self_use_ratio is not None and priced['load_mode'] != '按用电逐时算')
    green_kwh = exported * max(0, 1 - (mechanism if mechanism_years else 0) - green_share)
    result['income_breakdown'] = dict(self_saving_cny=priced['revenue_cny'], export_cny=exported * market,
                                     green_cny=green_kwh / 1000 * green_price, subsidy_cny=subsidy if subsidy_year == 1 else 0,
                                     mechanism_adjustment_cny=exported * mechanism * (mechanism_price - market) if mechanism_years else 0)
    result['certificates'] = dict(issued_estimate=(priced['self_use_kwh'] + exported) / 1000, tradable_estimate=green_kwh / 1000,
                                  price_cny=green_price, source=catalog['green_price'], note='是按发电量估的张数，不是已经拿到的；自己用掉的电对应的绿证不能卖。')
    result['subsidy'] = dict(amount_cny=subsidy, year=subsidy_year, confirmed=bool(supplied.public_subsidy_confirmed),
                            note='常发改〔2025〕212号：常州公共机构，上一年并网审核通过，无重复市级以上支持且信用安全环保合格。'
                                 '用户确认全部资格才计一次性0.3元/W；2025-09-09施行，文件未列固定终止日。')
    for row in result['cashflows']:
        y = row['year']
        factor = (1 - params['degradation_annual_pct'] / 100) ** (y - 1) if y else 0
        row.update(generation_kwh=energy['p50'] * factor, self_use_kwh=priced['self_use_kwh'] * factor,
                   export_kwh=exported * factor, curtailed_kwh=(energy['p50'] - priced['self_use_kwh'] - exported) * factor,
                   income_cny=(priced['revenue_cny'] + exported * market) * factor + (income(y, factor) + settlement(y, factor) if y else 0),
                   om_cny=base_om + insurance + cleaning if y else 0)
        if land_rent is not None:
            row['land_rent_cny'] = land_rent if y else 0
    epv = sum(r['generation_kwh'] / (1 + params['discount_rate']) ** r['year'] for r in result['cashflows'][1:])
    opv = sum((r['om_cny'] + (land_rent or 0) + own['accounts'][r['year'] - 1]['replacement']) /
              (1 + params['discount_rate']) ** r['year'] for r in result['cashflows'][1:])
    result['lcoe_cny_kwh'] = (quoted['capex_cny'] + opv) / epv if epv else None
    result['carbon'] = {}
    for region, key in (('jiangsu', 'emission_factor_kgco2_kwh'), ('national', 'national_emission_factor_kgco2_kwh')):
        annual = [dict(year=r['year'], co2_t=r['generation_kwh'] * params[key] / 1000) for r in result['cashflows'][1:]]
        result['carbon'][region] = dict(emission_factor_kgco2_kwh=params[key], annual_t=annual,
                                        total_t=math.fsum(r['co2_t'] for r in annual), source=sources[key])
    result['co2_t_per_year'] = energy['p50'] * params['emission_factor_kgco2_kwh'] / 1000
    if blocked:
        from .personal import curtailment
        result['curtailment'] = curtailment(project, energy, len(design.modules) if design is not None else 0)
    result['sensitivity'] = scenarios(project, dc_kw, energy, result, design, electric, load) if sensitivity else []
    result['financial_sources'] = {key: catalog[key] for key in FINANCIAL_KEYS}
    if weeding is not None:
        result['financial_sources'].update({key: catalog[key] for key in ('weeding_share', 'grazing_replacement')})
    if land_rent is not None:
        result['financial_sources']['land_rent'] = catalog['land_rent']
    result['input_fingerprint'] = cache_key(project, quoted)
    result['energy_fingerprint'] = energy_key(project)
    return result


def scenarios(project, dc_kw, energy, base, design, electric, load):
    rows = []
    for key, label in (('capex_cny_per_w', '造价'), ('price_self_cny_kwh', '平段电价'),
                       ('self_use_ratio', '自用比例'), ('generation_kwh', '发电量')):
        for direction, multiplier in (('low', .9), ('high', 1.1)):
            changed = project.model_copy(deep=True)
            power = dict(energy)
            if key == 'generation_kwh':
                value = energy[direction]
                scale = value / energy['p50'] if energy['p50'] else 0
                power = dict(energy, p50=value)
                if 'hourly' in energy:
                    power['hourly'] = dict(utc=energy['hourly']['utc'], kwh=[g * scale for g in energy['hourly']['kwh']])
            else:
                value = min(1, max(0, base['params'][key] + multiplier - 1)) if key == 'self_use_ratio' else base['params'][key] * multiplier
                setattr(changed.economics, key, value)
            other = calculate(changed, dc_kw, power, design=design, electric=electric, load=load, sensitivity=False)
            row = dict(variable=key, name_zh=label, direction=direction, value=value)
            for metric in ('payback_years', 'irr_pct'):
                row[metric] = other[metric]
                row['delta_' + metric] = other[metric] - base[metric] if other[metric] is not None and base[metric] is not None else None
            rows.append(row)
    return rows
