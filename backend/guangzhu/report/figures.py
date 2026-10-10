"""Inline SVG views of archived geometry and calculated results."""
from html import escape
import math
from decimal import Decimal, ROUND_HALF_UP
from markupsafe import Markup

COLORS = ('#c87743', '#2a9d63', '#3f6fd8', '#9f668c', '#c98b0f', '#528d93')


def svg(body, height=360):
    return Markup(f'<svg viewBox="0 0 700 {height}" xmlns="http://www.w3.org/2000/svg" role="img">{body}</svg>')


def number(value, digits):
    return f'{Decimal(str(value)).quantize(Decimal(10) ** -digits, rounding=ROUND_HALF_UP):,.{digits}f}'


def text(x, y, value, size=12, raw=None):
    title = f'<title>原值 {escape(str(raw))}</title>' if raw is not None else ''
    return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="#4b423a">{title}{escape(str(value))}</text>'


def nice_length(span):
    """A 1, 2 or 5 × 10ⁿ metre scale bar about a fifth of the drawing wide."""
    target = max(span / 5, .5)
    power = 10 ** math.floor(math.log10(target))
    return min((step * power for step in (1, 2, 5, 10)), key=lambda length: abs(length - target))


def plan(data, heat=False, tallest=900, wind=False, overview=False):
    """Roof plan at the roof's own proportions: 700 wide, height follows the roof (capped), legend band underneath."""
    roof, design = data['project']['roof'], data['design']
    if roof.get('type') in ('ground', 'carport'):
        roof = design.get('installation_roof') or roof
    near = roof.get('surroundings', [])
    shapes = [roof['outline'], *[row.get('footprint') or [[row['center'][0] + dx * row['radius_m'], row['center'][1] + dy * row['radius_m']]
                                  for dx, dy in ((-1, -1), (1, 1))] for row in near]]
    xs, ys = [p[0] for shape in shapes for p in shape], [p[1] for shape in shapes for p in shape]
    width, height = max(max(xs) - min(xs), 1), max(max(ys) - min(ys), 1)
    scale = min(640 / width, tallest / height)
    left, top = (700 - width * scale) / 2, 34
    canvas = top + height * scale + 56
    point = lambda p: (left + (p[0] - min(xs)) * scale, top + (max(ys) - p[1]) * scale)

    def polygon(points, color, label):
        coords = ' '.join(f'{x:.2f},{y:.2f}' for x, y in map(point, points))
        return f'<polygon points="{coords}" fill="{color}" stroke="#998e83" stroke-width=".6"><title>{escape(label)}</title></polygon>'

    body = '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse">'
    body += '<path d="M0 6L6 0" stroke="#c98b0f" stroke-width="1"/></pattern></defs>'
    for row in near:
        if row.get('footprint'):
            body += polygon(row['footprint'], '#cfc6bb', row.get('label', '周边建筑'))
        else:
            x, y = point(row['center'])
            body += f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{row["radius_m"] * scale:.2f}" fill="#cfc6bb"><title>{escape(row["label"])}</title></circle>'
    outline_label = '场地轮廓' if roof.get('type') in ('ground', 'carport') else '屋顶轮廓'
    body += polygon(roof['outline'], '#edf0f2' if overview else '#f0e7d8', outline_label + '：x向东、y向北')
    if roof.get('type') in ('ground', 'carport'):
        from ..models import Project, Design
        from ..installation import facilities
        installed = facilities(Project.model_validate(data['project']), Design.model_validate(design))
        for road in installed.get('roads', []):
            body += polygon(road, '#b0aca2', '实际道路')
        for fence in installed.get('fence', []):
            body += polygon(fence, 'none', '内退围栏')
        for bay in installed.get('bays', []):
            body += polygon(bay['polygon'], 'none', bay['id'])
        for pole in [*installed.get('piles', []), *installed.get('columns', [])]:
            x, y = point(pole['point'])
            body += f'<circle cx="{x}" cy="{y}" r="2" fill="#724a34"><title>{escape(pole["id"])}</title></circle>'
    slope_arrow = ''
    if roof.get('type') in ('pitched', 'carport'):
        from shapely.geometry import Polygon
        slope_arrow = '<defs><marker id="plane-tip" viewBox="0 0 10 10" refX="9" refY="5" orient="auto" markerWidth="5" markerHeight="5">'
        slope_arrow += '<path d="M0 0L10 5L0 10Z" fill="#9c522b"/></marker></defs>'
        for plane in roof['planes']:
            body += polygon(plane['outline'], '#9fd6df' if plane['material'] == 'glass' else '#e2e5e9', f"P{plane['id']}")
            center = Polygon(plane['outline']).centroid
            x, y = point((center.x, center.y))
            angle = math.radians(plane['slope_azimuth_deg'])
            dx, dy = 28 * math.sin(angle), -28 * math.cos(angle)
            slope_arrow += f'<path d="M{x:.2f} {y:.2f}l{dx:.2f} {dy:.2f}" stroke="#9c522b" marker-end="url(#plane-tip)"/>'
            slope_arrow += text(x, y - 9, f"P{plane['id']} {plane['slope_deg']:g}°" + (' 玻璃' if plane['material'] == 'glass' else ''), 10)
    if roof.get('type') == 'metal':
        bearing = math.radians(roof['slope_azimuth_deg'])
        x, y = point([sum(xs) / len(xs), sum(ys) / len(ys)])
        dx, dy = 35 * math.sin(bearing), -35 * math.cos(bearing)
        slope_arrow = '<defs><marker id="slope-tip" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">'
        slope_arrow += '<path d="M0 0L10 5L0 10Z" fill="#c87743"/></marker></defs>'
        slope_arrow += f'<path d="M{x:.2f} {y:.2f}l{dx:.2f} {dy:.2f}" stroke="#c87743" stroke-width="3" marker-end="url(#slope-tip)"/>'
        slope_arrow += text(x, y - 10, f"坡度 {roof['slope_deg']:g}°")
    for row in roof['keepouts'] + design.get('added_keepouts', []):
        body += polygon(row['polygon'], 'url(#hatch)', row.get('label', '禁区'))
    for row in roof['obstacles']:
        if row['kind'] == 'cylinder':
            x, y = point(row['center'])
            body += f'<circle cx="{x}" cy="{y}" r="{row["radius_m"] * scale}" fill="#998e83"/>'
        else:
            body += polygon(row['footprint'], '#998e83', row.get('label', '障碍物'))
    losses = {row['id']: row['total_loss_pct'] for row in data['shading']['modules']}
    strings = (data.get('electrical') or {}).get('strings', [])
    colors = {mid: COLORS[index % len(COLORS)] for index, row in enumerate(strings) for mid in row['module_ids']}
    colors.update({m['id']: {1: '#2a9d63', 2: '#c87743'}[m['phase']] for m in design['modules'] if m.get('phase')})
    if wind:
        from ..wind import COLORS as WIND_COLORS
        colors = {m['id']: WIND_COLORS[m['zone']] for m in (data.get('structure') or {}).get('wind', {}).get('modules', [])}
    if overview:
        colors = {m['id']: '#3c667b' for m in design['modules']}
    for row in design['modules']:
        ratio = min(max(losses.get(row['id'], 0) / 8, 0), 1)
        stops = ((31, 58, 102), (200, 119, 67), (209, 73, 63))
        low, high = (stops[0], stops[1]) if ratio < .5 else (stops[1], stops[2])
        weight = ratio * 2 if ratio < .5 else (ratio - .5) * 2
        color = '#%02x%02x%02x' % tuple(round(a + (b - a) * weight) for a, b in zip(low, high))
        label = row['id'] + (f'；损失原值 {losses.get(row["id"])}%' if heat else '')
        body += polygon(row['corners'], color if heat else colors.get(row['id'], '#1f3a66'), label)
    body += slope_arrow
    cable = (data.get('electrical') or {}).get('cables', {}) if not heat and not wind and not overview else {}
    for kind, color in [('dc', '#b83c28'), ('ac', '#007b68')]:
        for row in cable.get(kind, []):
            coords = ' '.join(f'{x:.2f},{y:.2f}' for x, y in map(point, row['route']))
            body += f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width=".7"/>'
    for row in cable.get('positions', []):
        x, y = point(row['point'])
        body += f'<rect x="{x-3}" y="{y-3}" width="6" height="6" fill="#243746"/>'
        body += text(x + 5, y - 5, row['label'], 9)
    note = '障碍物：灰色　禁区：斜线' + ('　周边建筑：浅灰' if roof.get('surroundings') else '')
    if wind:
        note += '　角部红色 / 边部黄色 / 中部青色（示意）'
    if not heat and not wind and not overview and any(m.get('phase') for m in design['modules']):
        note += '　一期：绿色　二期：橙色'
    if not heat and not wind and not overview and strings:
        modules, placed = {row['id']: row for row in design['modules']}, []
        corners = design['modules'][0]['corners'] if design['modules'] else [[0, 0], [1, 0]]
        if math.dist(corners[0], corners[1]) * scale >= 7:  # a label only where a module is at least ~2 mm on paper
            for row in strings:
                x, y = point(modules[row['module_ids'][0]]['center'])
                if all(abs(x - u) > 24 or abs(y - v) > 10 for u, v in placed):
                    placed.append((x, y))
                    body += text(x, y - 3, row['id'], 8)
        if len(placed) < len(strings):
            note += '　串号太密未全部标出，见电气页'
    body += f'<path d="M680 {top + 36}V{top}L673 {top + 13}M680 {top}L687 {top + 13}" stroke="#4b423a" fill="none"/>' + text(675, top - 6, 'N')
    bar = nice_length(width)
    body += f'<path d="M20 {canvas - 30}h{bar * scale:.2f}" stroke="#4b423a" stroke-width="3"/>' + text(20, canvas - 38, f'{bar:g} m')
    body += text(20, canvas - 10, note)
    if heat:
        for index, (label, color) in enumerate(zip(('0%', '4%', '8%+'), ('#1f3a66', '#c87743', '#d1493f'))):
            body += f'<rect x="{370 + index * 85}" y="5" width="18" height="10" fill="{color}"/>'
            body += text(394 + index * 85, 15, label)
    return svg(body, round(canvas))


def bars(rows, unit):
    rows = list(rows)
    extent = max((abs(value) for _, value in rows if value is not None), default=1) or 1
    body = text(200, 16, unit)
    for index, (label, value) in enumerate(rows):
        if value is None:
            y = 36 + index * 29
            body += text(8, y + 13, label) + text(340, y + 13, '无可算差值（基准或情景未回本）')
            continue
        y, width = 36 + index * 29, abs(value) / extent * 260
        x = 340 - width if value < 0 else 340
        body += text(8, y + 13, label) + f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="17" fill="#c87743"/>'
        body += text(610, y + 13, number(value, 0 if 'kWh' in unit else 2), raw=value)
    return svg(body, max(100, 62 + len(rows) * 29))


def cashflow(economics):
    rows = economics['cashflows']
    values = [row['cumulative_cny'] for row in rows]
    low, high = min(values + [0]), max(values + [0])
    y = lambda value: 220 - (value - low) / (high - low or 1) * 185
    points = ' '.join(f'{45 + row["year"] * 23:.2f},{y(row["cumulative_cny"]):.2f}' for row in rows)
    body = f'<path d="M45 {y(0)}H630" stroke="#998e83"/><polyline points="{points}" fill="none" stroke="#c87743" stroke-width="3"/>'
    body += text(45, 20, f'累计现金流（元）　最高 {number(high, 0)}；最低 {number(low, 0)}', raw=f'{high}；{low}')
    for year in (0, 5, 10, 15, 20, 25):
        body += text(45 + year * 23, 245, f'{year}年')
    payback = economics.get('payback_years')
    if payback is not None and payback <= 25:
        x = 45 + payback * 23
        body += f'<path d="M{x} 30V220" stroke="#2a9d63" stroke-dasharray="4"/>'
        body += text(x + 4, 50, f'回本 {number(payback, 2)}年', raw=payback)
    return svg(body, 260)
