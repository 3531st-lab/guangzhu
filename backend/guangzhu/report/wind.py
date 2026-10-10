"""Wind pages and material rows consume the archived engineering result."""
from markupsafe import Markup

from .figures import plan


def pages(context, add, fmt):
    load = context.get('structure') or {}
    wind = load.get('wind')
    if not wind:
        return
    city = wind['city']
    notes = [wind['note'], f"风压城市：{city['city']}；{city['selection']}；距市中心{city['distance_km']:.1f}km",
             f"50年基本风压{wind['basic_pressure_kpa']:g}kPa（示意）；分区宽{wind['zone_width_m']:g}m（示意）",
             wind['zone_note'], wind['height_note'], wind['method']]
    anchored = bool(wind.get('anchor_count'))
    if anchored:
        notes.append(f"{wind['anchored_modules']}块组件的支架改用锚栓，共{wind['anchor_count']}个。" + wind['anchor_note'])
    rows, weight = [], wind['assumptions']['block_kg']
    span = lambda low, high, unit='': f'{low:g}{unit}' if low == high else f'{low:g}–{high:g}{unit}'
    for row in wind['zones'].values():
        count = row.get('modules')
        if count == 0:  # no panel in this zone: dashes, not calculated zeros
            rows.append((row['label'], 0, '—', '—', '—', '—') + (('—',) if anchored else ()))
            continue
        pressure = row.get('pressure_kpa_range', [0, 0])
        blocks = row.get('blocks_range', [0, 0])
        each = f'{span(*blocks, "块")}（{span(blocks[0] * weight, blocks[1] * weight, "kg")}）' if blocks[1] else (
            '改锚栓' if row.get('anchors') else '0块')
        total = Markup('{}块 / {}').format(row['ballast_blocks'], fmt(row['ballast_kg'], 'kg')) if row['ballast_blocks'] else '—'
        rows.append((row['label'], '—' if count is None else count, f'{pressure[0]:.3f}–{pressure[1]:.3f}', each, total,
                     fmt(row['load_kn_m2'], 'kN/m²', 3)) + ((row.get('anchors', 0),) if anchored else ()))
    if context['project']['roof']['type'] in ('ground', 'carport'):
        rows = [(r['id'], r['zone'], fmt(r['pressure_kpa'], 'kPa', 3),
                 fmt(r['uplift_n'], 'N'), fmt(r['horizontal_n'], 'N')) for r in wind['modules'][:12]]
        notes.append('仅列前12块的风作用示意，完整逐板结果见材料表；桩基及钢结构由厂家复核，不构成承载结论。')
        add('新建安装风作用（示意）', notes, rows, ['组件', '分区', '风压', '上拔', '水平力'],
            plan(context, wind=True), kind='wind', newpage=True)
    else:
        add('风荷载与分区压块', notes, rows, ['分区', '组件', '风压kPa', '每板压块', '压块合计', '区荷载']
            + (['锚栓'] if anchored else []), plan(context, wind=True), kind='wind', newpage=True)
    factors = wind['factor_source']
    references = [wind['missing'], f"城市风压出处目标：{city['standard']} {city['table']}；页码{city['page']}；{city['url']}",
                  f"仅分项系数已核验：{factors['title']}；{factors['url']}；发布{factors['published']}；访问{factors['accessed']}",
                  '风压、高度、体型、阵风、摩擦、分区和通用夹具参数仍为示意；GB55001核验不等于全套风设计核验。',
                  'S-5 ER-805 2025-09-15 Table1第8页的2.492kN仅适用其特定ASD组合，不作为通用夹具设计容量。']
    if any('clamps' in row for row in wind['modules']):
        clamps = [row['clamps'] for row in wind['modules'] if 'clamps' in row]
        references += [f"夹具需求{wind['clamp_required']}个；实际布点{wind['clamp_count']}个；不满足的组件{wind['clamp_failed']}块。",
                       'W01未通过时清单为现有可布点统计，不代表需求已满足；换抗拔力更大的夹具，或请厂家复核。',
                       clamps[0]['basis'], clamps[0]['note'],
                       f"单夹具设计容量{clamps[0]['capacity_kn']:g}kN；最大/最小间距{clamps[0]['max_spacing_m']:g}/"
                       f"{clamps[0]['min_spacing_m']:g}m；板缝距{clamps[0]['seam_spacing_m']:g}m（均示意）"]
    add('风荷载依据与待核实项', references, kind='wind-sources')


def materials(load, sheet, book):
    wind = load.get('wind')
    if not wind:
        return
    page = book['材料清单']
    for row in wind['zones'].values():
        if row['ballast_blocks']:
            page.append([row['label'] + '压块', None, f"{wind['assumptions']['block_kg']:g}kg/块", None,
                         row['ballast_blocks'], '块', row['ballast_kg'], wind['note']])
    if any('clamps' in r for r in wind['modules']):
        page.append(['抗风夹具', None, '示意通用设计容量', None, wind['clamp_count'], '个', None,
                     wind['note'] + f"；需求{wind['clamp_required']}；W01失败组件{wind['clamp_failed']}"])
    if wind.get('anchor_count'):
        page.append(['化学锚栓（含局部防水）', None, '示意5kN/个', None, wind['anchor_count'], '个', None, wind['anchor_note']])
    fields = ['id', 'zone', 'pressure_kpa', 'uplift_n', 'horizontal_n', 'ballast_blocks', 'ballast_kg']
    headers = ['组件', '分区', '风压kPa', '上拔N', '水平N', '压块个数', '压块kg', '夹具需求', '可布', '采用', '符合']
    rows = [[r[k] for k in fields] + [r.get('clamps', {}).get(k) for k in ('required', 'available', 'adopted', 'passed')]
            for r in wind['modules']]
    if wind.get('anchor_count'):
        headers.append('锚栓个数')
        for row, record in zip(rows, wind['modules']):
            row.append(record.get('anchors', 0) if record.get('fixing') == 'anchor' else 0)
    sheet('风荷载', [headers] + rows + [[wind['note']], [wind['missing']]])
