"""Exports consume the same version facilities and priced quantities as the physics."""
from ..models import Project, Design
from ..installation import effective, facilities


def context(project, design):
    record, version = Project.model_validate(project), Design.model_validate(design)
    return effective(record, version), version, facilities(record, version)


def cad(project, design, drawing, space):
    if project['roof']['type'] not in ('ground', 'carport'):
        return
    _, _, values = context(project, design)
    for layer in ('ROAD', 'FENCE', 'PILE', 'BAY', 'AISLE', 'CANOPY', 'COLUMN', 'BEAM'):
        drawing.layers.new(layer)
    for key, layer in (('roads', 'ROAD'), ('fence', 'FENCE')):
        for polygon in values.get(key, []):
            space.add_lwpolyline(polygon, close=True, dxfattribs=dict(layer=layer))
    for key, layer in (('bays', 'BAY'), ('aisles', 'AISLE')):
        for row in values.get(key, []):
            space.add_lwpolyline(row['polygon'], close=True, dxfattribs=dict(layer=layer))
    for face in values.get('faces', []):
        space.add_polyline3d(face['points'], close=True, dxfattribs=dict(layer='CANOPY'))
    for beam in values.get('beams', []):
        bottom = [[x, y, z - beam['depth_m']] for x, y, z in beam['points']]
        space.add_polyline3d(bottom, close=True, dxfattribs=dict(layer='BEAM'))
    for key, layer in (('piles', 'PILE'), ('columns', 'COLUMN')):
        for row in values.get(key, []):
            space.add_line(row['point'], [*row['point'][:2], row['top_m']], dxfattribs=dict(layer=layer))


def sheets(project, design, structure, economy, sheet, book):
    if project['roof']['type'] not in ('ground', 'carport'):
        return
    record, version, values = context(project, design)
    main = book['材料清单']
    main.delete_rows(4, 2)
    extras = structure['extra_cost_items']
    for item in extras:
        price = next(row for row in economy['costs']['items'] if row['key'] == item['key'])
        main.append([price['name'], None, price['key'], None, item['quantity'], price['unit'], None, values['note'],
                     price['unit_price_cny'], price['subtotal_cny'], '与造价明细同一实体数量，不重复相加'])
    rows = [['实体编号', '类型', 'x m', 'y m', '地坪 z m', '顶高 m', '关联组件或棚']]
    for key in ('piles', 'columns'):
        rows += [[p['id'], key, *p['point'], p['top_m'], ','.join(p.get('modules', [])) or p.get('plane')]
                 for p in values.get(key, [])]
    sheet('基础实体', rows)
    if values['kind'] == 'ground':
        sheet('道路围栏土地', [['项目', '数值', '单位'], ['土地面积', values['land_area_m2'], 'm²'],
              ['土地亩数', values['land_mu'], '亩'], ['道路并集面积', values['road_area_m2'], 'm²'],
              ['围栏实画长度', values['fence_physical_m'], 'm'], ['围栏报价周长', values['fence_quote_m'], 'm'],
              ['年地租（投资人支出）', economy['land_rent']['annual_cny'], '元/年']])
    else:
        sheet('车位及棚面', [['实体', '面积或净高', '说明']] +
              [[p['id'], p['clear_height_m'], 'm；最低棚面减竖向结构深度'] for p in values['faces']] +
              [[b['id'], str(b['polygon']), '净车位角点 m'] for b in values['bays']])
        main.append(['车棚钢量基准', None, '60kg/kW；12kg/m²棚面下限', None, structure['facilities']['steel_basis_kw'], 'kW',
                     structure['facilities']['steel_kg'], '生成时整棚一次建设；删板仍保留棚体；厂家设计示意'])
    if '分期材料' in book:
        page = book['分期材料']
        for i in reversed(range(2, page.max_row + 1)):
            if page.cell(i, 2).value == '支架':
                page.delete_rows(i)
        first_ids = {m.id for m in version.modules if m.phase == 1}
        construction_phase = 1 if first_ids else 2
        for key in ('piles', 'columns'):
            for p in values.get(key, []):
                phase = construction_phase if key == 'columns' else 1 if first_ids.intersection(p['modules']) else 2
                page.append([phase, p['id'], key, 1, '根'])
        racks = {}
        for pile in values.get('piles', []):
            racks[pile['rack']] = 1 if first_ids.intersection(pile['modules']) else 2
        for identifier, phase in racks.items():
            page.append([phase, identifier, '空地物理架', 1, '架'])
        for extra in extras:
            if extra['key'] not in ('ground_pile', 'ground_rack'):
                page.append([construction_phase, extra['key'], '场地固定设施一次建设', extra['quantity'], '见工程报价'])


def pages(c, add, fmt):
    if c['project']['roof']['type'] not in ('ground', 'carport'):
        return
    _, _, values = context(c['project'], c['design'])
    rows = []
    if values['kind'] == 'ground':
        rows = [('场地', values['land_area_m2'], 'm²'), ('土地', values['land_mu'], '亩'),
                ('桩', len(values['piles']), '根'), ('物理架', values['rack_count'], '架'),
                ('道路并集', values['road_area_m2'], 'm²'), ('围栏实画', values['fence_physical_m'], 'm'),
                ('围栏报价（原场地周长）', values['fence_quote_m'], 'm'),
                ('投资人年度地租', c['economics']['land_rent']['annual_cny'], '元/年')]
    else:
        rows = [('净车位', values['bay_count'], '个'), ('棚面', len(values['faces']), '个'),
                ('立柱', len(values['columns']), '根'), ('棚面投影', values['canopy_area_m2'], 'm²')]
        rows += [(f"P{p['id']}实际梁底净高", p['clear_height_m'], 'm') for p in values['faces']]
    add('新建安装实体与工程量', [values['note'],
        '空地围栏按原场地周长报价，内退后实画长度单列；道路按真实面并集。' if values['kind'] == 'ground' else
        'JGJ100-2015表4.3.4小型车倒车垂直停车净位2.4×5.1m、净车道5.5m；2.2m车库净高参照适用性待设计确认。'],
        [(label, fmt(value, unit)) for label, value, unit in rows], ['项目', '数值'])
