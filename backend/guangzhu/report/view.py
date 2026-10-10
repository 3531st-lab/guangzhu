"""Readable proposal pages, formatted without changing archived calculations."""
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from .figures import bars, cashflow, plan
from ..sitecheck import rows
from ..electrical import labels as electrical_labels, load_catalog

WORDS = dict(pass_='通过', fail='未通过', warn='建议', na='不适用', hard='硬性', soft='建议', advice='建议', approve='通过', revise='需修改')
WORDS.update(low='低（low）', medium='中（medium）', high='高（high）')
APPROVALS = {'allowed-once': '仅允许这次', 'allowed-session': '本会话允许', 'rejected': '已拒绝', 'cancelled': '已取消', 'unavailable': '不可用'}
FIELDS = {'edge_setback_m': '边距', 'obstacle_clearance_m': '障碍物间距', 'tilt_deg': '倾角'}
CHAINS = {'a': 'NASA POWER 2023 · pvlib 简化', 'b': 'NASA POWER 2023 · CEC 详细', 'c': 'NASA POWER 2023 · PySAM PVWatts',
          'b_tmy': 'ERA5 TMY · CEC 详细', 'd': 'ERA5 多年 · PVGIS PVcalc'}


def beijing_time(value):
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M（北京时间）') if stamp.tzinfo else '未提供时区'
    except (AttributeError, ValueError):
        return '未提供'


def field_unit(key, unit):
    return unit or ('m' if str(key).endswith('_m') else '°' if str(key).endswith('_deg') else '')


def fmt(value, unit='', digits=None, raw=None):
    if value is None:
        return '未提供'
    if isinstance(value, bool):
        return '是' if value else '否'
    if isinstance(value, (dict, list)):
        items = [Markup('{} {}').format(FIELDS.get(k, k), fmt(v, field_unit(k, unit), digits)) for k, v in value.items()] if isinstance(value, dict) else [
            fmt(v, unit, digits) for v in value]
        return Markup('；').join(items) or '无'
    if not isinstance(value, (float, int)):
        return WORDS.get('pass_' if value == 'pass' else value, str(value))
    if digits is None:
        digits = 0 if unit.startswith('kWh') else 1 if re.search(r'kW|%', unit) else 2 if re.search(r'年|m|米|°|㎡|平方', unit) else 0
    shown = f'{Decimal(str(value)).quantize(Decimal(10) ** -digits, rounding=ROUND_HALF_UP):,.{digits}f}'
    return Markup('<span class="num" title="原值 {}">{}</span>{}').format(value if raw is None else raw, shown, ' ' + unit if unit else '')


def link(value, label=None):
    match = re.search(r'https?://[^\s；]+', value or '')
    return Markup('<a href="{}" title="{}">{}</a>').format(match[0], value, label or value) if match else value or '未提供'


def rule_value(rule, field):
    if rule['id'] == 'E09' and field == 'value':
        lengths = [length for group in rule[field] for length in group]
        if lengths and len(set(lengths)) == 1:
            return Markup('{} 串，均为 {}').format(len(lengths), fmt(lengths[0], rule.get('unit', '')))
    return fmt(rule[field], rule.get('unit', ''), 2 if rule['id'] == 'E07' else None)


def rule_source(rule, verified=False):
    source = rule['source_ref']
    if source.startswith('requirements.'):
        return '用户要求：' + rule['name_zh']
    return link(source.replace('roof.load_capacity_kn_m2', '屋面资料：核定荷载' if verified else '屋面资料：示意荷载（待结构核定）').replace('T04排板规则', '光筑排板规则')
                .replace('T05三段遮挡规则', '光筑遮挡规则'), rule['source_type'])


def source_value(value, unit):
    if unit == '比例':
        return fmt(value * 100 if value is not None else None, '%', raw=value)
    digits = 4 if unit == 'kgCO₂/kWh' else 3 if unit in ('元/W', '元/kWh', '元/(W·年)') else 2 if unit == '%' else 0 if unit == '年' else None
    return fmt(value, unit, digits)


def render(c):
    if c['project']['roof']['type'] in ('ground', 'carport'):
        from copy import deepcopy
        c = deepcopy(c)
        c['project']['roof'] = c['design'].get('installation_roof') or c['project']['roof']
    s, e, d, p = c['summary'], c['economics'], c['design'], c['project']
    verified = bool(p['roof'].get('load_verified'))  # Codex review R10: an unconfirmed roof load is never called 核定

    def name(rule):
        if p['roof']['type'] in ('ground', 'carport'):
            return rule['name_zh'].replace('屋面', '安装面').replace('屋顶', '场地')
        return rule['name_zh'] if verified else rule['name_zh'].replace('屋面核定值', '屋面示意值（待结构核定）')
    el, shade, rules = c['electrical'], c['shading']['summary'], c['rules']['items']
    pages = []

    def add(title, paragraphs=(), table=(), headers=(), chart=None, metrics=(), kind='', newpage=False):
        pages.append(dict(title=title, paragraphs=paragraphs, rows=table, headers=headers, chart=chart, metrics=metrics, kind=kind,
                          newpage=newpage or not pages))

    def facts(data, specifications):
        return [(label, fmt(data.get(key), unit)) for key, label, unit in specifications]

    headline = [('直流装机容量', fmt(s['dc_kw'], 'kW')), ('组件数量', fmt(s['modules'], '块')),
                ('基准年发电估算', fmt(s['yield_kwh']['p50'], 'kWh')), ('静态投资回收期', fmt(e['payback_years'], '年')),
                ('内部收益率（IRR）', fmt(e['irr_pct'], '%')), ('首年减排量', fmt(e['co2_t_per_year'], 't'))]
    stamp = beijing_time(c.get('generated_at'))
    notice = '本方案书在运行结束后由光筑根据已导出文件和 AGH 执行记录生成，不属于审批时的导出文件'
    if not c.get('sessions'):
        notice = '本方案书根据离线工具输出生成；未提供 AI 会话、AGH 执行记录、导出批准和独立审核证据'
    approval = c.get('approval') or {}
    review = c.get('review') or {}
    check = c['verification'].get('review', {})
    failed = [text for text, broken in (('审核员要求修改', review.get('verdict') == 'revise'), ('审核记录核对没通过', check.get('passed') is False)) if broken]
    review_state = ('独立审核（' + review.get('reviewer_model', '模型未记录') + '）：' + ('审核未通过（' + '；'.join(failed) + '）' if failed
                    else '审核员结论' + fmt(review.get('verdict')))) if review else '本归档未提供独立审核原文'
    approved = '导出经 AGH 审批卡批准（仅允许这次）' if approval.get('verdict') == 'allowed-once' else '导出批准证据见执行记录页'
    add(p['name'], [f'屋顶光伏初步设计 · v{c["version"]} · {stamp}',
        Markup('纬度 {} / 经度 {}').format(fmt(p['site']['lat'], '°'), fmt(p['site']['lon'], '°')),
        ('光筑 Agent 生成 · ' if c.get('sessions') else '光筑工具生成 · ') + review_state + ' · ' + approved,
        notice], chart=plan(c, tallest=520, overview=True), metrics=headline[:3], kind='cover')
    asked = [r for r in rules if r['source_type'] == '用户要求']
    requests = [(name(r), rule_value(r, 'limit'), rule_value(r, 'value'), fmt(r['status'])) for r in asked if r['status'] != 'na']
    requirement_notes = ['当前要求：' + c['requirements'][-1]['text']] if c.get('requirements') else ['归档未提供需求原文']
    for change in c.get('relaxations', []):
        requirement_notes += ['原要求：' + change['before']['text'], '新要求：' + change['after']['text']]
        consent = list(dict.fromkeys(row['text'] for row in change['consent'] if row['text']))
        requirement_notes += ['用户同意原话：' + line for line in consent] or ['归档中未找到用户同意原话']
    if len(requests) < len(asked):
        requirement_notes.append(f'其余 {len(asked) - len(requests)} 项要求没有提，按不适用处理（见规则清单）。')
    requirement_notes += [r['note'] for r in asked if r['id'] == 'U05' and r['status'] == 'na']
    interval = '五链年发电复核范围（不是置信区间）：' + str(fmt(s['yield_kwh']['low'], 'kWh')) + ' — ' + str(fmt(s['yield_kwh']['high'], 'kWh'))
    add('一页结论', [Markup(interval), *requirement_notes], requests, ['需求事项', '要求值', '结果', '是否满足'], metrics=headline, newpage=True)
    compare = c.get('compare') or {}
    options = [*([compare['current']] if compare.get('current') else []), *compare.get('options', [])]
    recommended = compare.get('recommended', {}).get(c.get('run', {}).get('prefer', 'balanced'), {}).get('version')
    versions = {row['version']: row for row in c.get('versions', [])}
    labels = dict(G03='通道不够', G04='留空区域被占用', G05='倾角超范围', G06='避让距离不足', L01='承重超限',
                  U01='装机不足', U02='装机超上限', U03='超预算', U04='回本超限')
    def option_name(row):
        mark = '选定' if row['version'] == c['version'] else '推荐' if row['version'] == recommended else ''
        ancestor, reason, visited = None if row is compare.get('current') else versions.get(row['version']), '', set()
        while ancestor and ancestor['version'] != compare.get('base_version') and ancestor['version'] not in visited:
            visited.add(ancestor['version'])
            if (cut := re.fullmatch(r'(?:多装|最快回本|折中)：按 (U02|U03) 删除 \d+ 块', ancestor.get('reason', ''))) and ancestor.get('statistics') and not reason:
                reason = f"{'预算' if cut[1] == 'U03' else '装机上限'}删板后{ancestor['statistics']['module_count']:,}块"
            ancestor = versions.get(ancestor.get('parent_version'))
        name = Markup('{} · v{} {}').format(row['name'], row['version'], mark)
        return name + Markup('<br><small>{}</small>').format(reason) if reason else name
    def arrangement(row):
        if row.get('align') == 'pitched':
            return '顺坡；' + '、'.join(f'P{i}' for i in row['planes'])
        label = dict(south='正南', edge='顺边', ew='东西向', custom=f"朝向 {row.get('azimuth_deg')}°").get(row.get('align'), '原排法')
        return f"{label}；补位 {row.get('fill_landscape_count', 0)} 块"
    comparison = [(option_name(row), arrangement(row), '按坡面' if row.get('align') == 'pitched' else fmt(row.get('tilt_deg'), '°'),
        fmt(row['dc_kw'], 'kW'),
        fmt(row['annual_kwh'], 'kWh'), fmt(row['payback_years'], '年'), fmt(row['irr_pct'], '%'), fmt(row['avg_loss_pct'], '%'),
        '、'.join(labels.get(key, key) for key in row['violated_requirements']) or
        ('满足' if row['hard_pass'] else '硬性规则未过')) for row in options]
    site = compare.get('site_tilt')
    tilts = [f"倾角按当地全年天气定：成排参考最佳 {site['best']}°；多装参考 {site['capacity']}°（每千瓦少 {site['loss_pct']['capacity']}%），"
             f"折中参考 {site['balanced']}°（少 {site['loss_pct']['balanced']}%）。实际排法和倾角见表，东西向另算发电。"] if site else []
    if compare.get('capacity_note'):
        tilts.append(compare['capacity_note'] + '。多装按各候选完成规则修正后的装机量选择。')
    if d['params'].get('layout') == 'ew':
        tilts.append('东西向主阵列共用屋脊；横放补位沿两侧原底边，上缘更低且不相接，中间空隙不作检修通道。')
    curve = bars([(f"多装 {site['capacity']}°", site['loss_pct']['capacity']), (f"折中 {site['balanced']}°", site['loss_pct']['balanced']),
                  (f"成排最佳 {site['best']}°", 0)], '成排参考：每千瓦年发电比最佳倾角少（%）') if site and options else None
    metal = p['roof']['type'] == 'metal'
    bearing = p['roof'].get('slope_azimuth_deg') if metal else 180
    direction = ('北', '东北', '东', '东南', '南', '西南', '西', '西北')[round(bearing / 45) % 8]
    metal_note = f"彩钢瓦单坡 {p['roof'].get('slope_deg'):g}°、朝{direction}（{bearing:g}°），夹具顺坡平铺，没有压块" if metal else ''
    add('三方案对比', ['彩钢瓦，不适用：顺坡平铺，倾角就是坡度'] if metal else tilts if options else ['本次未做三方案对比'],
        comparison, ['方案', '排法', '倾角', '装机', '年发电', '回本', '收益率', '遮挡', '满足要求'],
        curve, kind='options')
    layout = facts(d['params'], [('tilt_deg', '倾角', '°'), ('azimuth_deg', '方位角', '°'), ('edge_setback_m', '边距', 'm')])
    layout += facts(d['statistics'], [('row_spacing_m', '排距', 'm'), ('clear_gap_m', '净距', 'm'),
                                    ('usable_area_m2', '可用面积', 'm²')])
    layout.append(('GCR', fmt(d['statistics']['gcr'] * 100, '%', raw=d['statistics']['gcr'])))
    if metal:
        layout = [row for row in layout if row[0] not in ('排距', '净距')]
    if p['roof']['type'] == 'pitched':
        layout = [row for row in layout if row[0] in ('边距', '可用面积')]
        layout += [('安装方式', '各面顺坡平铺，坡度与朝向见逐面表'), ('接缝两侧退让', fmt(d['statistics']['seam_setback_m'], 'm'))]
    color_note = '组件按期着色：一期绿色、二期橙色。' if e.get('phases') else '组件按组串着色，串号标在第一块组件旁。'
    add('屋顶与排布', [metal_note] if metal else ['x 向东，y 向北；' + color_note],
        layout, ['参数', '值'], plan(c), kind='layout')
    for row in rules:
        if row['id'] == 'G07':
            add('组件高度', [f"最高点{row['value']:.3f}m；限高{row['limit']:g}m，均相对局部屋面"])
    if e.get('phases'):
        phase_rows = [(r['name'], fmt(r['capex_cny'], '元'), fmt(r['payback_years'], '年'), fmt(r['profit_cny'], '元')) for r in e['phases']]
        phase = d['statistics'].get('phasing', {})
        note = f"一期实际{phase.get('achieved_kw', 0):g}kW、{phase.get('achieved_cny', 0):g}元；装机向上整串，预算向下整串"
        note += f"；预算{phase['budget_cny']:g}元、余额{phase['remainder_cny']:g}元" if phase.get('budget_cny') else f"；目标{phase.get('target_kw'):g}kW"
        add('分期建设', [e['phase_note'], note, '一期绿色；二期橙色'], phase_rows,
            ['阶段', '造价', '回本', '全期净收益'], plan(c), kind='phases', newpage=True)
    if metal:
        add('彩钢瓦说明', ['另一坡面单独设计，本方案和3D不画另一坡面，忽略两坡互遮挡。',
            '夹具和导轨均为示意，夹具间距及抗风揭需要厂家和结构复核；已算风荷载时按实际布点计夹具数量，造价见分项表。'])
    from .wind import pages as wind_pages
    wind_pages(c, add, fmt)
    from .pitched import pages as pitched_pages
    pitched_pages(c, add, fmt)
    from .installation import pages as installation_pages
    installation_pages(c, add, fmt)
    from .livestock import pages as livestock_pages
    livestock_pages(c, add, fmt)
    chains = (c.get('crosscheck') or {}).get('specific_yield_kwh_kwp', {})
    groups = (c.get('crosscheck') or {}).get('groups', [])
    if groups:
        add('各朝向发电复核', ['按所在坡面、倾角、朝向分组；下表未扣遮挡，缺链不计入合计。'],
            [(f"坡面{g['group'][0]} / {g['group'][1]:g}° / 朝向{g['group'][2]:g}°", chain, fmt(value, 'kWh/kWp'))
             for g in groups for chain, value in g['per_kw'].items()], ['朝向组', '链', '每千瓦发电量'])
    add('发电量与复核', ['基准年估算用 b 链：NASA POWER 2023 年逐时天气 + CEC 详细模型，再扣掉遮挡损失；只代表 2023 这一年的天气，不是概率意义上的 P50。', '区间是五条链天气与模型的差异范围，不是统计置信区间',
        '前三链使用同一 NASA POWER 2023 天气；后两链分别使用 ERA5 典型年与多年天气。CEC 详细模型使用 Sandia 逆变器。'],
        facts(s['yield_kwh'], [('p50', '基准年估算', 'kWh'), ('low', '区间下限', 'kWh'), ('high', '区间上限', 'kWh')]),
        ['发电量', '结果'], bars([(CHAINS.get(key, key), value) for key, value in chains.items()], '每千瓦发电量 kWh/kWp') if chains else None, kind='yield')
    shade_rows = facts(shade, [('avg_loss_pct', '平均遮挡', '%'), ('max_loss_pct', '最大遮挡', '%'),
                             ('modules_over_threshold', '超阈值组件', '块'), ('threshold_pct', '阈值（示意）', '%')])
    causes = {'parapet': '女儿墙', 'obstacles': '障碍物', 'front_row': '前排组件', 'diffuse': '天空漫射', 'surroundings': '周边建筑'}
    shade_rows += [(causes.get(k, k) + '占比', fmt(v, '%')) for k, v in shade.get('source_loss_share_pct', {}).items()]
    add('遮挡与损失', ['图例为全年损失0–8%，超过8%按最高色阶显示。'], shade_rows, ['项目', '值'], plan(c, heat=True), kind='shading')
    def evidence(r):
        text = r['evidence'].replace('本项按任务卡额外检查厂家范围', '本项另按厂家规格书检查')
        if r['id'] == 'E07':
            return text.split('；接线')[0].split('；第1台')[0] + '（每台分配见下表）'
        lengths = {length for row in el.get('strings', []) for length in [len(row['module_ids'])]}
        return f"{len(el.get('strings', []))} 串，每串都是 {lengths.pop()} 块" if r['id'] == 'E09' and len(lengths) == 1 else text
    electrical = [(r['id'], r['name_zh'], rule_value(r, 'value'), rule_value(r, 'limit'), evidence(r)) for r in rules if r['id'].startswith('E')]
    string_label, inverter_label = electrical_labels(el)
    module_label = load_catalog('modules.csv').get(el['module_id'], {}).get('model', el['module_id'])
    add('电气与组串', [f'组件：{module_label}；逆变器：{inverter_label}',
        Markup('组串 {}；容配比 {}。').format(string_label, fmt(el['dc_ac_ratio'], digits=2))],
        electrical, ['编号', '校核', '数值', '限值', '证据式'], kind='electrical')
    cable = el.get('cables')
    if cable:
        totals = [('直流' if r['kind'] == 'dc' else '交流四芯', fmt(r['section_mm2'], 'mm²'),
                   fmt(r['length_m'], 'm'), fmt(r['drop_pct_max'], '%')) for r in cable['summary']]
        places = '；'.join(f"{r['label']}：({r['point'][0]:.1f}, {r['point'][1]:.1f})m（{r['note']}）" for r in cable['positions'])
        add('电缆和压降', [el['wiring']['method'] + '：' + el['wiring']['reason'], places, *cable['notes']],
            totals, ['电缆', '截面', '总长', '最大压降'], kind='cables', newpage=True)
        routing = cable.get('routing')
        if routing:
            detail = [(r['id'], '可达' if r['routing_status'] == 'ok' else '不可达，仅下界估算',
                       fmt(r['length_m'], 'm'), fmt(r['drop_pct'], '%')) for r in cable['dc']]
            saving = (Markup('相比可达的原顺序节省直流{}（含富余）。').format(fmt(routing['saved_dc_m'], 'm'))
                      if routing['saved_dc_m'] is not None else '存在不可达路径，不能比较节线量。')
            add('串联布线方案', [routing['method'] + '；不改变串成员、MPPT和逆变器归属。',
                Markup('优化{}串；不可达{}条；{}').format(routing['optimized_strings'], routing['blocked_routes'], saving),
                '串内连接顺序及设备归属见材料清单的“串联布线”页；3D可选择单串查看。'],
                detail, ['串号', '路径状态', '导体长度（含富余）', '压降'], kind='wiring', newpage=True)
    def span(ids):
        return '、'.join(ids) if ids else '无'
    allocation = [(f"第 {row['inverter']} 台", span(row['string_ids']), fmt(row['module_count'], '块'), fmt(row['dc_kw'], 'kW'),
                   fmt(row['dc_ac_ratio'], digits=2), f"{sum(1 for m in row['mppt_assignments'] if m['string_ids'])} / {len(row['mppt_assignments'])}")
                  for row in el.get('per_inverter', [])]
    if allocation:
        add('逆变器分配', ['每台逆变器接哪些组串；MPPT 一栏是用到的路数 / 总路数。'], allocation,
            ['逆变器', '组串', '组件', '直流容量', '容配比', 'MPPT'], kind='allocation')
    add('承重核对', ['只做附加荷载对比，不能代替结构复核', *([] if verified else ['屋面允许荷载是示意值，没有经过结构核定；施工前必须请结构工程师复核'])],
        facts(s['load'], [('added_kn_m2', '附加荷载', 'kN/m²'),
                          ('capacity_kn_m2', '屋面核定值' if verified else '屋面允许值（示意，待结构核定）', 'kN/m²')]), ['项目', '值'])
    if p['roof']['type'] in ('ground', 'carport'):
        pages[-1].update(title='基础与结构', paragraphs=['L01不适用；由基础和钢结构厂家设计，地勘、抗拔与结构验算未完成。'], rows=[])
    returns = facts(e, [('capex_cny', '初始投资估算', '元'), ('payback_years', '静态投资回收期', '年'),
                       ('dynamic_payback_years', '动态投资回收期', '年'), ('irr_pct', '内部收益率（IRR）', '%'), ('npv_cny', '净现值（NPV）', '元')])
    returns.append(('平准化度电成本（LCOE）', fmt(e['lcoe_cny_kwh'], '元/kWh', 3)))
    sensitivity = [(row['name_zh'] + (' ↓' if row['direction'] == 'low' else ' ↑'), row['delta_payback_years']) for row in e['sensitivity']]
    add('回报与敏感性', e['assumptions'], returns, ['项目', '结果'], cashflow(e) + bars(sensitivity, '回本变化（年）'), kind='economics')
    from .financial import pages as financial_pages
    financial_pages(e, add, fmt)
    if e.get('business_models'):
        models = [(r['name'], fmt(r['owner_capex_cny'], '元'), fmt(r['owner_first_year_cny'], '元'),
                   fmt(r['owner_total_cny'], '元'), fmt(r['investor_payback_years'], '年'), fmt(r['investor_irr_pct'], '%'))
                  for r in e['business_models']]
        use = e['self_use']
        reference = f"逐时参考 {use['ratio']:.1%}；" if use['algorithm'] == '按用电逐时算' else ''
        lease_note = '折扣15%、租金5元/m²·年为示意。'
        if p['roof']['type'] == 'carport':
            lease_note = e['lease_note']
        if p['roof']['type'] == 'ground':
            rent = e['land_rent']
            lease_note = f"地租{rent['rate_cny_mu_year']:g}元/亩·年，投资人年支出{rent['annual_cny']:g}元，三模式各扣一次。"
            lease_note += '土地出租方单列收到同额租金；表中业主用电收益不重复加入该租金。'
        add('三种投资方式', [f"自用比例口径：{use['algorithm']}；账里按 {use['effective_ratio']:.1%}，",
            reference + f"自用电价 {use['weighted_price_cny_kwh']:.3f} 元/度（示意）；" + lease_note,
            '余电被限掉，无上网收入。' if e.get('self_use', {}).get('curtailed_kwh', 0) > 0 else
            '允许物理上网；当前余电售电价为0元。' if e['params']['price_export_cny_kwh'] == 0 else '余电按示意上网电价计算。'], models,
            ['方式', '业主投资', '业主首年', '业主25年合计', '投资方回本', '投资方收益率'], kind='business', newpage=True)
    carbon = [(name, fmt(row['annual_t'][0]['co2_t'], 't'), fmt(row['total_t'], 't'),
               fmt(row['emission_factor_kgco2_kwh'], 'kgCO₂/kWh', 4), link(row['source']['链接'], row['source']['来源标题']))
              for key, name in [('jiangsu', '江苏'), ('national', '全国对照')] if (row := e['carbon'].get(key))]
    add('减碳估算', ['采用归档中的电力平均排放因子，25年结果已包含发电衰减。'], carbon, ['口径', '首年', '25年合计', '因子', '来源'])
    site = [(r['item'], dict(ok='没问题', risk='有风险', ask='没填')[r['status']], r['text'])
            for r in rows(c.get('facts'), s, e['params'], p['roof']['type'], p.get('requirements', {}).get('structured'), p['roof'])]
    add('开工前要核实的事', ['业主在开工前问答里填的情况；10 年、80% 是示意提醒线，不是规范限值。' if c.get('facts') else
        '这次没有填开工前问答，下面是开工前要问清的事。'], site, ['事项', '情况', '说明'], kind='site')  # T22
    order = lambda r: 0 if r['status'] == 'fail' and r['level'] == 'hard' else 1 if r['status'] in ('fail', 'warn') else 3 if r['status'] == 'na' else 2
    checklist = [(r['id'], name(r), fmt(r['level']) + ' / ' + fmt(r['status']), rule_value(r, 'value'),
                  rule_value(r, 'limit'), rule_source(r, verified)) for r in sorted(rules, key=order)]
    rule_title = '规则清单（含新建安装校核）' if p['roof']['type'] in ('ground', 'carport') else '22条规则清单'
    add(rule_title, ['未通过项优先，其次建议、通过、不适用。来源链接保留完整出处作为悬停提示。'],
        checklist, ['编号', '规则', '等级 / 结果', '数值', '限值', '来源'], kind='rules')
    sources = [(row['中文名'], source_value(e['params'].get(key), row['单位']), row['状态'],
                link(row['链接'] or row['来源标题'], row['来源标题']), row['访问日期'] or '未提供') for key, row in e['source'].items()]
    equipment = [link(el['metadata'][key], name) for key, name in [('module_source', '组件规格书'), ('inverter_source', '逆变器规格书')]]
    add('假设与来源', equipment, sources, ['参数', '数值', '状态', '来源', '访问日期'], kind='sources')
    checked = '通过' if check.get('passed') else '没通过：' + check.get('reason', '原因未记录') if check.get('passed') is False else '未核对'
    notes = [review_state, '审核意见是模型的判断，原样转载', '审核模型：' + review.get('reviewer_model', '未提供'),
             '审核员结论：' + fmt(review.get('verdict')), '审核记录核对（光筑按执行记录检查审核员有没有按规矩查数据）：' + checked]
    findings = [(fmt(row['severity']), row['item'], row['evidence'], row['suggestion']) for row in review.get('findings', [])]
    add('独立审核', notes, findings, ['等级（附原文）', '问题（原文）', '证据（原文）', '建议（原文）'], kind='review')
    execution = [(row['stage'], fmt({True: 'pass', False: 'fail'}.get(row.get('passed')))) for row in c['verification'].get('checks', [])]
    for row in c.get('sessions', []):
        tokens = row.get('tokens', {})
        costs = Markup('；').join(fmt(cost['micros'] / 1e6, cost['currency'], 6, raw=cost['micros']) for cost in row.get('costs', []))
        costs += '（已知小计，另有缺额）' if costs and not row.get('billing_complete') else '（估算，0不表示免费）' if costs else '未知（未提供费用记录）'
        execution += [(row['id'][:8] + ' · ' + ' / '.join(row.get('model_ids', [])),
            Markup('请求 {}；输入 {}；输出 {}；缓存读 {}；缓存写 {}；推理 {}；估算 {}').format(fmt(row.get('model_requests')),
                *[fmt(tokens.get(key)) for key in ('input', 'output', 'cacheRead', 'cacheWrite', 'reasoning')], costs))]
    execution += [('导出审批', APPROVALS.get(approval.get('verdict'), '未提供') + ' · ' + beijing_time(approval.get('ts')))]
    execution += [('执行记录', c['run_id'] + '/' + path) for path in c['sources'] if path.endswith('ledger.agnes.jsonl')]
    add('执行记录与交付', [notice, ('补生成于 ' if c.get('regenerated') else '生成于 ') + stamp,
        '模型费用是估算，缺失字段为未知；推理token属于输出子集，不重复相加。',
        '本方案为初步设计，示意值需要按实际报价和现场条件确认，施工前需要专业复核。'], execution, ['记录', '内容'], kind='execution')
    if p['roof']['type'] in ('ground', 'carport'):
        label = '空地' if p['roof']['type'] == 'ground' else '车棚'
        for page in pages:
            page['title'] = page['title'].replace('屋顶', label).replace('屋面', '安装面')
            page['paragraphs'] = [paragraph.replace('屋顶', label).replace('屋面', '安装面') for paragraph in page['paragraphs']]
    return render_pages(pages, c)


def render_pages(pages, c):
    from .document import prepare
    pages, document = prepare(pages, c, beijing_time(c.get('generated_at')))
    root = Path(__file__).resolve().parents[3]
    fonts = root / 'desktop/web/vendor/fonts'
    assets = {name: base64.b64encode((fonts / file).read_bytes()).decode() for name, file in
              [('mono', 'IBMPlexMono-Regular.woff2'), ('brand', 'NotoSerifSC-900-guangzhu.woff2')]}
    environment = Environment(loader=FileSystemLoader(Path(__file__).parent), autoescape=select_autoescape(['html']))
    return environment.get_template('template.html').render(pages=pages, context=c, fonts=assets, document=document)
