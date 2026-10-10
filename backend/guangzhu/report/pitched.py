"""Physical face tables and bill quantities shared by the proposal and workbook."""
import math

from ..models import Project, Design
from ..pitched import table

MATERIALS = dict(metal='彩钢瓦', concrete='混凝土', glass='采光玻璃（不装）')


def rows(project, design, shadows, economy, load):
    energy = economy.get('analysis_metadata', {}).get('yield_kwh', {})
    return table(Project.model_validate(project), Design.model_validate(design), shadows, energy, load)


def pages(context, add, fmt):
    if context['project']['roof']['type'] != 'pitched':
        return
    roof = context['project']['roof']
    kind = dict(single='单坡', gable='双坡', hip='四坡', sawtooth='锯齿形').get((roof.get('pitched') or {}).get('kind'), '自定义')
    seam = roof.get('seam_setback_m')
    seam = .5 if seam is None else seam
    add('整栋斜屋面', [f'{kind}整栋；屋脊/斜脊/天沟两侧退让{seam:g}m（示意，可改）。',
        '按实际共面高度计算射线；玻璃按不透光遮挡示意；正面入射时凸双坡可没有互遮损失，不预设北坡损失。',
        '各面顺坡平铺；组串不跨坡面；固定费用按整栋一次，逆变器和电缆按实际合并方案计价。'], kind='pitched', newpage=True)
    details = rows(context['project'], context['design'], context['shading'], context['economics'], context['structure'])
    prices = context['economics']['costs']['items']
    for row in details:
        energy = row['energy'] or {}
        load = row['load'] or {}
        subtotal = math.fsum(p['subtotal_cny'] for p in prices if p.get('plane') == row['id'])
        cells = [('材料', MATERIALS[row['material']]), ('坡度 / 下行朝向', f"{row['slope_deg']:g}° / {row['azimuth_deg']:g}°"),
                 ('真实坡面面积', fmt(row['area_m2'], 'm²')), ('檐边最低偏移', fmt(row['offset_m'], 'm')),
                 ('离地最低 / 最高', f"{row['min_height_m']:.3f} / {row['max_height_m']:.3f} m"),
                 ('组件 / 装机', f"{row['module_count']} 块 / {energy.get('dc_kw', 0):g} kW"),
                 ('每千瓦净年发电', fmt(energy.get('per_kw'), 'kWh/kW')), ('净年发电', fmt(energy.get('p50'), 'kWh')),
                 ('平均遮挡', fmt(row['shading_pct'], '%')), ('最不利附加荷载', fmt(load.get('added_kn_m2'), 'kN/㎡')),
                 ('允许荷载与来源', f"{row['capacity_kn_m2']:g} kN/㎡；{row['capacity_source']}；{'核定' if row['verified'] else '示意待核定'}"),
                 ('本面组件与支架硬件', fmt(subtotal, '元'))]
        note = ['本面金额不含整栋共用逆变器、电缆、施工及固定费用，合计以造价明细为准。']
        if row['material'] == 'concrete':
            note.append('固定导轨及每板4锚固件仅计量示意；未核定抗拔、防水和主体传力。无压块、无金属瓦夹具。')
        add(f"P{row['id']} 坡面", note, cells, ['项目', '结果'], kind='plane-table')


def sheets(project, design, shadows, economy, load, sheet, book):
    if project['roof']['type'] != 'pitched':
        return
    details = rows(project, design, shadows, economy, load)
    sheet('坡面', [['坡面', '材料', '坡度°', '下行朝向°', '最低边偏移m', '最低高m', '最高高m', '坡面面积m²',
                   '组件数', '装机kW', '净年发电kWh', '每千瓦净发电', '遮挡%', '荷载kN/㎡', '允许kN/㎡', '来源', '核定']] +
          [[r['id'], MATERIALS[r['material']], r['slope_deg'], r['azimuth_deg'], r['offset_m'], r['min_height_m'], r['max_height_m'],
            r['area_m2'], r['module_count'], (r['energy'] or {}).get('dc_kw', 0), (r['energy'] or {}).get('p50', 0),
            (r['energy'] or {}).get('per_kw'), r['shading_pct'], (r['load'] or {}).get('added_kn_m2'), r['capacity_kn_m2'],
            r['capacity_source'], r['verified']] for r in details])
    material = book['材料清单']
    for index in range(material.max_row, 1, -1):
        if material.cell(index, 1).value == '组件、支架及压块总质量':
            material.cell(index, 1, '组件、逐面支架及连接件总质量')
            material.cell(index, 8, '示意；含组件、金属夹具或混凝土锚固；无压块')
        if material.cell(index, 1).value in ('逐面顺坡支架', '抗风夹具'):
            material.delete_rows(index)
    for price in economy['costs']['items']:
        if price.get('plane') is None or price['key'] == 'module':
            continue
        material.append([f"P{price['plane']} {price['name']}", None, price['key'], None, price['quantity'], price['unit'], None,
                         price['source']['备注']])
    sheet('坡面造价', [['坡面（空为整栋共用）', '项目', '数量', '单位', '单价元', '小计元', '状态']] +
          [[r.get('plane'), r['name'], r['quantity'], r['unit'], r['unit_price_cny'], r['subtotal_cny'], r['source']['状态']]
           for r in economy['costs']['items']])


def cad(roof, drawing, space):
    if roof['type'] != 'pitched':
        return
    from shapely.geometry import Polygon
    for plane in roof['planes']:
        name = f"P{plane['id']}_{plane['material']}"
        drawing.layers.new(name, dxfattribs=dict(color=4 if plane['material'] == 'glass' else 8))
        space.add_lwpolyline(plane['outline'], close=True, dxfattribs=dict(layer=name))
        center = Polygon(plane['outline']).centroid
        angle = math.radians(plane['slope_azimuth_deg'])
        end = (center.x + 2 * math.sin(angle), center.y + 2 * math.cos(angle))
        space.add_line((center.x, center.y), end, dxfattribs=dict(layer=name))
        for delta in (-.4, .4):
            tip = (end[0] - .5 * math.sin(angle + delta), end[1] - .5 * math.cos(angle + delta))
            space.add_line(tip, end, dxfattribs=dict(layer=name))
        label = f"P{plane['id']} {plane['slope_deg']:g}deg / {plane['slope_azimuth_deg']:g}deg {plane['material']}"
        space.add_text(label, dxfattribs=dict(layer=name, height=.35, insert=(center.x, center.y)))
