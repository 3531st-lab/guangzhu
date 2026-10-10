"""Quantity-based illustrative quotations; only consumed catalog rows are recorded."""
import csv
import hashlib
import json
import math

from shapely.geometry import Polygon
from .config import DATA_DIR
from .models import GzError


def catalog():
    from .economics import CSV_COLUMNS
    with (DATA_DIR / 'catalog/costs.csv').open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
            raise GzError('COSTS_INVALID', '造价目录列名不正确', '核对costs.csv来源列')
        result = {}
        for row in reader:
            value = float(row['数值'])
            if row['key'] in result or not math.isfinite(value) or value < 0 or row['状态'] not in ('示意', '已查证'):
                raise ValueError('造价目录数值或编号不正确')
            if row['状态'] == '已查证' and not all(row[k] for k in ('链接', '发布日期', '访问日期')):
                raise ValueError('查证造价缺少来源')
            result[row['key']] = dict(row, value=value)
    return result


def voltage(ac_kw):
    return '380 V' if ac_kw <= 400 else '10 kV' if ac_kw <= 6000 else '更高电压，需当地电网核定'


def itemized(project, dc_kw, design=None, electric=None, load=None):
    from .electrical import equipment_catalog
    from .layout import rack_id
    equipment = equipment_catalog()
    if design is not None and load is None:
        from .structure import calculate
        load = calculate(project, design)
    prices = catalog()
    count = len(design.modules) if design is not None else dc_kw * 1000 / equipment['modules'][project.equipment.module_id]['pmax_w']
    rack = rack_id(project, design.params) if design is not None else project.equipment.racking
    rack_data = equipment['racking'][rack]
    barn = project.roof.use == 'barn'
    units = (electric or {}).get('per_inverter', [])
    ac = math.fsum(equipment['inverters'][u['inverter_id']]['rated_ac_kw'] for u in units)
    grid = voltage(ac)
    items = []
    def add(key, quantity, hardware=False, label=None):
        source = prices[key]
        items.append(dict(key=key, name=label or source['中文名'], quantity=quantity, unit=source['单位'].removeprefix('元/'),
                          unit_price_cny=source['value'], subtotal_cny=quantity * source['value'], hardware=hardware, source=source))
    if project.roof.type == 'pitched':
        from .roofplane import member
        counts = {p.id: sum(member(project.roof, m.id).id == p.id for m in design.modules) for p in project.roof.planes}
        for plane in project.roof.planes:
            if counts[plane.id]:
                add('module', dc_kw * 1000 * counts[plane.id] / count, True)
                items[-1]['plane'] = plane.id
    else:
        add('module', dc_kw * 1000, True)
    for unit in units:
        model = equipment['inverters'][unit['inverter_id']]
        add('inverter', model['rated_ac_kw'] * 1000, True, model['model'])
    if project.roof.type == 'pitched':
        for plane in project.roof.planes:
            if counts[plane.id]:
                rail = 'barn_rail' if barn else 'metal_rail'
                add(rail if plane.material == 'metal' else 'fixed_flush', counts[plane.id], True)
                items[-1]['plane'] = plane.id
    elif project.roof.type not in ('ground', 'carport'):
        rail = 'barn_rail' if barn else 'metal_rail'
        key = rail if rack in ('clamp_flush', 'clamp_barn') and (load or {}).get('wind') else rack
        add('barn_rail' if key == 'clamp_barn' else key, count, True)
    ballast = (load or {}).get('ballast_mass_kg', float(rack_data['ballast_weight_kg_per_module']) * count)
    if project.roof.type not in ('ground', 'carport'):
        add('ballast', ballast / 1000)
    for cable in (electric or {}).get('cables', {}).get('summary', []):
        key = cable['kind'] + '_cable'
        add(key, cable['length_m'] * cable['section_mm2'], True,
            ('直流' if key.startswith('dc') else '交流四芯') + f"电缆 {cable['section_mm2']:g} mm²")
        items[-1].update(quantity=cable['length_m'], unit='m', unit_price_cny=prices[key]['value'] * cable['section_mm2'])
        if project.roof.use == 'grazing' and cable['kind'] == 'dc':
            add('dc_animal_protection', cable['length_m'], True)
    add('grid_lv' if ac <= 400 else 'grid_mv' if ac <= 6000 else 'grid_hv', 1 if count else 0, True)
    add('monitor', 1 if count else 0, True)
    add('installation', dc_kw * 1000)
    add('design', 1 if count else 0)
    add('unlisted', dc_kw * 1000)  # switchgear, trays, grounding, fees: an ordinary roof lands on the industry average, extra work above it
    facts = project.facts
    refurbish = project.economics.refurbish or facts is not None and (facts.roof_age_years or 0) >= 10
    if project.roof.type not in ('ground', 'carport'):
        add('refurbishment', Polygon(project.roof.outline).area if refurbish and count else 0)
    for extra in (load or {}).get('extra_cost_items', []):
        add(extra['key'], extra['quantity'], extra.get('hardware', False))
        if 'plane' in extra:
            items[-1]['plane'] = extra['plane']
    quoted = math.fsum(row['subtotal_cny'] for row in items)
    manual = project.economics.capex_cny_per_w
    capex = dc_kw * 1000 * manual if manual is not None else quoted
    factor = capex / quoted if quoted else 1
    for row in items:
        row['quoted_subtotal_cny'] = row['subtotal_cny']
        row['subtotal_cny'] *= factor
        row['unit_price_cny'] *= factor
    if items:
        items[-1]['subtotal_cny'] += capex - math.fsum(row['subtotal_cny'] for row in items)
    consumed = {row['key']: row['source'] for row in items if row['quantity']}
    digest = hashlib.sha256(json.dumps(consumed, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return dict(items=items, capex_cny=capex, quoted_capex_cny=quoted, manual_override=manual is not None,
                hardware_cny=math.fsum(row['subtotal_cny'] for row in items if row['hardware']),
                replacement_cny=math.fsum(row['quoted_subtotal_cny'] for row in items if row['key'] == 'inverter'),
                effective_cny_per_w=capex / (dc_kw * 1000) if dc_kw else 0, cpia_reference_cny_per_w=2.59,
                grid_voltage=grid, rated_ac_kw=ac, source_fingerprint=digest,
                note='各项单价都是示意值，以施工单位报价为准；配电柜、桥架、防雷接地、管理费、预备费等没有单列的费用按每瓦0.70元计入'
                     '“其他费用”，使普通屋顶的总价落在中国光伏行业协会2025年工商业分布式平均2.59元/W附近，需要翻新、锚栓、10千伏接入或钢构时总价更高；'
                     '在填条件页手填了造价时，按手填总价同比例分到各项。交流电缆按四芯电缆的长度计价。',
                grid_note='按逆变器交流合计判断：约400千瓦及以下接380伏，约6兆瓦及以下接10千伏（分界为示意，国网接入技术规定原文未取得），'
                          '最终以当地供电公司的接入方案为准。')
