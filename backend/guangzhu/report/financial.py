"""Proposal and spreadsheet views of saved T30 accounts, never recalculating archives."""
from markupsafe import Markup, escape


def graph_svg(graph):
    maximum = max([1] + [r['generation_kwh'] for r in graph])
    parts = ['<svg viewBox="0 0 720 440" xmlns="http://www.w3.org/2000/svg" aria-label="全年电价与出力">']
    for index, (key, label, scale, colour) in enumerate((('price_cny_kwh', '分时电价 元/度', 2, '#287b91'),
                                                       ('generation_kwh', '光伏出力 kWh/小时', maximum, '#d37a32'))):
        parts.append(f'<text x="65" y="{20 + index * 210}" font-size="14">{label}（浅色0 → 深色{scale:.2f}）</text>')
        for row in graph:
            x, y = 65 + row['hour'] * 25, 30 + index * 210 + (row['month'] - 1) * 13
            opacity = .08 + .92 * min(1, row[key] / scale)
            parts.append(f'<rect x="{x}" y="{y}" width="24" height="12" fill="{colour}" opacity="{opacity}"/>')
        for month in (1, 6, 12):
            parts.append(f'<text x="25" y="{40 + index * 210 + (month - 1) * 13}" font-size="12">{month}月</text>')
        for hour in (0, 6, 12, 18, 23):
            parts.append(f'<text x="{65 + hour * 25}" y="{204 + index * 210}" font-size="12">{hour}时</text>')
    return Markup(''.join(parts) + '</svg>')


def pages(cash, add, fmt):
    if 'costs' not in cash:
        return
    costs = cash['costs']
    rows = [(r['name'], fmt(r['quantity'], r['unit'], 3), fmt(r['unit_price_cny'], '元', 3),
             fmt(r['subtotal_cny'], '元'), r['source']['状态']) for r in costs['items']]
    add('造价明细', [costs['note'], f"合计{costs['capex_cny']:.2f}元，折合{costs['effective_cny_per_w']:.3f}元/W；CPIA参考2.59元/W。",
                    costs['grid_voltage'] + '；' + costs['grid_note']], rows, ['项目', '数量', '单价', '小计', '状态'], newpage=True)
    income = cash['income_breakdown']
    labels = dict(self_saving_cny='自用节省', export_cny='余电收入', green_cny='绿证', subsidy_cny='补贴', mechanism_adjustment_cny='机制差价')
    add('电价与收益', [cash['tariff']['note'], f"加权自用电价{cash['tariff']['weighted_price_cny_kwh']:.4f}元/度；月内同小时平均示意。",
                     cash['certificates']['note']], [(labels[k], fmt(v, '元')) for k, v in income.items()], ['首年构成', '金额'],
        chart=graph_svg(cash['tariff']['graph']), newpage=True)
    metrics = [('自投税前', cash), ('自投税后', cash['posttax'])]
    if 'loan' in cash:
        metrics += [('自有资金税前', cash['loan']['pretax']), ('自有资金税后', cash['loan']['posttax'])]
    rows = [(name, fmt(r['payback_years'], '年'), fmt(r['irr_pct'], '%'), fmt(r['profit_cny'], '元')) for name, r in metrics]
    rows += [(r['name'] + '投资方税后', fmt(r['investor_posttax_payback_years'], '年'),
              fmt(r['investor_posttax_irr_pct'], '%'), fmt(r['posttax']['profit_cny'], '元')) for r in cash['business_models'][1:]]
    notes = [f"回本要求按{cash['u04_basis']}；税后与贷款不自动替换税前指标。",
             f"贷款{cash['loan']['ratio']:.0%}，本金{cash['capex_cny'] * cash['loan']['ratio']:.2f}元，"
             f"期限{cash['loan']['years']}年，自有初投{cash['loan']['initial_equity_cny']:.2f}元；年利率{cash['loan']['rate']:.2%}。"
             if 'loan' in cash else '未填写贷款比例，未计贷款。', *cash['assumptions'][:4]]
    add('税和贷款', notes, rows, ['口径', '回本', '收益率', '累计净收益'], newpage=True)


def sheets(cash, sheet, book):
    if 'costs' not in cash:
        return
    headers = ['项目', '数量', '单位', '单价元', '小计元', '状态', '依据']
    items = cash['costs']['items']
    sheet('造价明细', [headers] + [[r['name'], r['quantity'], r['unit'], r['unit_price_cny'], r['subtotal_cny'],
                                  r['source']['状态'], r['source']['备注']] for r in items] + [['总计', None, None, None, cash['capex_cny']]])
    material = book['材料清单']
    material.cell(1, 9, '单价元')
    material.cell(1, 10, '小计元')
    material.cell(1, 11, '计价说明')
    for row in range(2, material.max_row + 1):
        name = material.cell(row, 1).value
        keys = ['module'] if name == '组件' else ['inverter'] if name == '逆变器' else ['dc_cable'] if name == '直流电缆' else []
        if name == '交流电缆':
            keys = ['ac_cable']
        if any(word in name for word in ('支架', '夹具', '导轨')) and '总质量' not in name:
            keys = ['ballast_tilt', 'ballast_ew', 'clamp_flush', 'metal_rail', 'barn_rail']
        if name == '抗风夹具':
            keys = ['wind_clamp', 'barn_clamp']
        if name.endswith('压块'):
            keys = ['ballast']
        if name.startswith('化学锚栓'):
            keys = ['flat_anchor']
        matches = [r for r in items if r['key'] in keys]
        if name.startswith('P') and ' ' in name:
            prefix = name.split(' ', 1)[0][1:]
            if prefix.isdigit():
                keys = [material.cell(row, 3).value]
                matches = [r for r in items if r['key'] in keys and r.get('plane') == int(prefix)]
        if keys and keys[0] in ('dc_cable', 'ac_cable'):
            section = str(material.cell(row, 3).value).replace('4×', '').replace(' mm²', '')
            matches = [r for r in matches if f'{float(section):g} mm²' in r['name']]
        subtotal = sum(r['subtotal_cny'] for r in matches)
        if keys == ['ballast']:
            total_kg = sum(r['quantity'] for r in matches) * 1000
            subtotal *= material.cell(row, 7).value / total_kg if total_kg else 0
        quantity = material.cell(row, 5).value
        material.cell(row, 9, subtotal / quantity if matches and quantity else '不适用')
        material.cell(row, 10, subtotal if matches else '不适用')
        material.cell(row, 11, '按本行采购单位折合；不与造价明细重复相加' if matches else '工程统计行，不重复计采购费用')
    fields = [('年份', 'year'), ('自用节省', 'saving'), ('售电含税', 'sales'), ('租金支出', 'rent'), ('更换', 'replacement'),
              ('实缴增值税', 'paid_vat'), ('结转进项', 'credit_close'), ('折旧', 'depreciation'), ('所得税', 'cit'),
              ('税前净流', 'pretax'), ('税后净流', 'posttax'), ('利息', 'interest'), ('本金', 'principal'), ('权益税后', 'equity_posttax')]
    if 'land_rent' in cash:
        fields.insert(4, ('地租支出（投资方）', 'land_rent_cny'))
    for model in cash['business_models']:
        sheet(model['name'] + '年度账', [[label for label, _ in fields]] + [[r.get(key) for _, key in fields] for r in model['accounts']])
    sheet('分时与收入', [['项目', '值']] + [['加权自用价', cash['tariff']['weighted_price_cny_kwh']]] +
          [[k, v] for k, v in cash['income_breakdown'].items()])
