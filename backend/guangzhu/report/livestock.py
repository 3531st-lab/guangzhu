"""Livestock reports use archived geometry and priced conductor quantities."""
from shapely.geometry import Polygon

from ..models import Roof, Keepout
from ..livestock import clearance


def cad(project, design, drawing, space):
    if project['roof'].get('use') != 'barn':
        return
    roof = Roof.model_validate(project['roof'])
    drawing.layers.new('BARN_CLEARANCE')
    for value in [*project['roof']['keepouts'], *design.get('added_keepouts', [])]:
        zone = Keepout.model_validate(value)
        distance = clearance(roof, zone, design['params']['keepout_clearance_m'])
        boundary = Polygon(zone.polygon).buffer(distance)
        space.add_lwpolyline(list(boundary.exterior.coords), close=True, dxfattribs=dict(layer='BARN_CLEARANCE'))


def details(value):
    if value['use'] == 'barn':
        return [value['corrosion'], value['fan_note']], [
            [k['label'], k['preset'], k['clearance_m'], 'm 四周避让'] for k in value['keepouts']]
    light = value['ground_light']
    notes = [value['land_note'], value['protection_note'], light['method'],
             '羊1.5米、牛2.5米和受光50%均为设计示意，非官方统一牲畜高度或产草保证。']
    rows = [['真实最低边', value['actual_min_m'], 'm', '按实际组件角点'],
            ['牲畜示意最低', value['animal_min_m'], 'm', value['animal']],
            ['全年地面受光', light['sun_pct'], '%', '按月天数及昼照时长加权'],
            ['受光要求', value['required_sun_pct'], '%', 'G10可通过加大排距重排改善']]
    rows += [[f"{r['month']}月", r['sun_pct'], '%', f"{r['represented_hours']}小时"] for r in light['months']]
    return notes, rows


def sheets(project, design, structure, economy, electric, sheet, book):
    value = structure.get('livestock')
    if not value:
        return
    notes, rows = details(value)
    sheet('畜牧用途', [['项目', '数值或类型', '单位或避让', '说明']] + rows + [[text] for text in notes])
    operating = economy['operating_costs']
    if operating.get('weeding'):
        saving = operating['weeding']
        book['畜牧用途'].append(['除草运维年节约', saving['saving_cny'], '元', saving['note']])
    if operating.get('cleaning_basis'):
        book['畜牧用途'].append(['清洗采用', operating['cleaning_times'], '次/年', operating['cleaning_basis']])
    for item in economy['costs']['items']:
        if item['key'] == 'dc_animal_protection':
            book['材料清单'].append([item['name'], None, item['key'], None, item['quantity'], item['unit'], None,
                                  value['protection_note'], item['unit_price_cny'], item['subtotal_cny'], '与造价明细同项'])
    if value['use'] == 'grazing' and '分期材料' in book:
        phase_by_string = {s['id']: s['phase'] for s in electric['strings']}
        for route in electric['cables']['dc']:
            book['分期材料'].append([phase_by_string[route['id']], 'DC防啃附加费', route['id'], route['length_m'], '导体m'])


def pages(context, add, fmt):
    value = (context.get('structure') or {}).get('livestock')
    if not value:
        return
    notes, rows = details(value)
    economy = context['economics']
    rows = [[r[0], fmt(r[1], digits=1 if r[2] == '%' else 2) if isinstance(r[1], (int, float)) else r[1], *r[2:]] for r in rows]
    operating = economy['operating_costs']
    if operating.get('cleaning_basis'):
        notes.append(f"清洗采用{operating['cleaning_times']}次/年；{operating['cleaning_basis']}")
    if operating.get('weeding'):
        saving = operating['weeding']
        notes.append(f"仅基础运维的除草份额{saving['share']:.0%}×放牧替代{saving['replacement']:.0%}；"
                     f"节约{saving['saving_cny']:.2f}元/年；保险、清洗、更换、地租及偿债不减免。")
    rows += [[r['name'], fmt(r['quantity'], r['unit']), fmt(r['subtotal_cny'], '元'), '示意，与造价明细同项']
             for r in economy['costs']['items'] if r['key'] in ('barn_rail', 'barn_clamp', 'animal_fence', 'dc_animal_protection')]
    add(value['title'] + '与采用参数', notes, rows, ['项目', '数值', '单位或金额', '说明'], kind='livestock', newpage=True)
