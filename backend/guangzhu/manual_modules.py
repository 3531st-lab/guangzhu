"""Atomic manual placement using catalogue dimensions and real roof-plane frames."""
import math

import numpy as np
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from .models import GzError, Module


OPERATIONS = {'add_modules', 'move_modules', 'rotate_modules'}
EPS = 1e-6


def transform_spec(project_record, design_record):
    """Publish the exact physical dimensions used by manual placement to the view.

    Historical captures sometimes only contain summaries. Those remain readable,
    but cannot supply the geometry needed for an interactive 3D edit.
    """
    from .layout import _catalog
    from .models import Project, Design
    try:
        project = Project.model_validate(project_record)
        design = Design.model_validate(design_record)
    except (ValueError, TypeError, GzError):
        return dict(available=False, reason='此记录缺少完整模型，无法启用三维组件拖拽。')
    try:
        supported(project, design)
        module, gap, lower = _catalog(project, design.params)
    except GzError as error:
        return dict(available=False, reason=error.message_zh)
    return dict(available=True, length_m=float(module['length_m']), width_m=float(module['width_m']),
                gap_m=gap, lower_edge_m=lower)


def fail(message, hint='调整位置、角度或选择范围后重新预览', code='MANUAL_MODULE_INVALID'):
    raise GzError(code, message, hint)


def number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        fail(f'{name}须为有限数值')
    return float(value)


def angle(value, name):
    result = number(value, name)
    if not -360 <= result <= 360:
        fail(f'{name}须在 -360° 至 360° 之间')
    return result


def supported(project, design):
    if project.roof.type not in ('flat', 'metal', 'pitched'):
        fail('地面桩基与车棚暂不支持单板手动变更', '使用整体结构排布，或选择屋顶单排支架', 'MANUAL_MODULE_UNSUPPORTED')
    if design.params.layout != 'rows' or design.params.rows_per_rack != 1 or any(m.tier != 1 for m in design.modules):
        fail('成组双排与东西向人字支架暂不支持单板手动变更', '选择屋顶单排支架方案后编辑', 'MANUAL_MODULE_UNSUPPORTED')


def surface(project, design, identifier=None):
    roof = project.roof
    if roof.type != 'pitched':
        if identifier is not None:
            fail('普通平屋顶和彩钢瓦不使用坡面编号')
        return roof
    if type(identifier) is not int:
        fail('整栋坡屋顶补放须指定所属坡面编号')
    plane = next((p for p in roof.planes if p.id == identifier), None)
    if plane is None or plane.material == 'glass' or design.params.plane_ids is not None and identifier not in design.params.plane_ids:
        fail('所属坡面不存在、为采光玻璃或未选用', '选择当前方案已选用的金属或混凝土坡面')
    return plane


def plane_id(module):
    return int(module.id.split('-', 1)[0][1:]) if module.id.startswith('P') else None


def frame(tilt, azimuth):
    beta, bearing = math.radians(tilt), math.radians(azimuth)
    right = np.array([-math.cos(bearing), math.sin(bearing), 0.0])
    uphill = np.array([-math.sin(bearing) * math.cos(beta), -math.cos(bearing) * math.cos(beta), math.sin(beta)])
    return right, uphill


def panel(project, design, center, orientation, rotation, plane, catalogue, lower, original=None, row=None):
    """Corners retain the physical short/long axes used by bypass-diode sampling."""
    from .roofplane import elevation, plane_elevation
    long, short = float(catalogue['length_m']), float(catalogue['width_m'])
    length, width = (long, short) if orientation == 'portrait' else (short, long)
    flush = project.roof.type in ('metal', 'pitched')
    tilt = plane.slope_deg if flush else original.tilt if original is not None else design.params.tilt_deg
    azimuth = plane.slope_azimuth_deg if flush else ((original.azimuth if original is not None else design.params.azimuth_deg) + rotation) % 360
    right, uphill = frame(tilt, azimuth)
    if flush:
        previous = 0.0
        if original is not None:
            axis = np.subtract(original.corners[1], original.corners[0])
            previous = math.atan2(-float(axis @ uphill), float(axis @ right))
        theta = previous + math.radians(rotation)
        right, uphill = math.cos(theta) * right - math.sin(theta) * uphill, math.sin(theta) * right + math.cos(theta) * uphill
        z = (plane_elevation(plane, center) if project.roof.type == 'pitched' else elevation(project.roof, center)) + lower
    else:
        z = lower + length * math.sin(math.radians(tilt)) / 2
    middle = np.array([*center, z])
    corners = np.array([middle - right * width / 2 - uphill * length / 2,
                        middle + right * width / 2 - uphill * length / 2,
                        middle + right * width / 2 + uphill * length / 2,
                        middle - right * width / 2 + uphill * length / 2])
    if original is not None:
        values = original.model_dump()
    else:
        prefix = f'P{plane.id}-' if project.roof.type == 'pitched' else ''
        values = dict(id=f'{prefix}R{row:02d}-1-C001', row=row, tier=1, col=1)
    values.update(center=corners.mean(axis=0).tolist(), corners=corners.tolist(),
                  tilt=tilt, azimuth=azimuth, orientation=orientation)
    return Module.model_validate(values)


def validate_placements(project, design, changed, gap, legacy_ids=()):
    from .layout import usable_geometry
    from .pitched import geometry as plane_geometry
    from .roofplane import elevation
    footprints = [Polygon([p[:2] for p in module.corners]) for module in design.modules]
    index = STRtree(footprints)
    usable = {}
    for i, module in enumerate(design.modules):
        if module.id not in changed:
            continue
        pid = plane_id(module)
        plane = surface(project, design, pid)
        if pid not in usable:
            usable[pid] = (plane_geometry(project, design.params, plane) if project.roof.type == 'pitched'
                           else usable_geometry(project, design.params))['usable'].buffer(EPS)
        if not usable[pid].covers(footprints[i]):
            fail(f'组件 {module.id} 超出可安装范围或侵入屋边、设备、禁区避让',
                 '把整块组件放入所属屋面的可安装区域', 'MANUAL_MODULE_CLEARANCE')
        limit = project.requirements.structured.max_height_m
        if limit is not None and max(p[2] - elevation(project.roof, p, pid) for p in module.corners) > limit + EPS:
            fail(f'组件 {module.id} 超过设置的屋面限高', '调整方案倾角或明确修改限高要求', 'MANUAL_MODULE_CLEARANCE')
        for j in index.query(footprints[i].buffer(gap + EPS), predicate='intersects'):
            if i == j or j < i and design.modules[j].id in changed:
                continue
            other = design.modules[j]
            first, second = footprints[i], footprints[j]
            if first.intersection(second).area > EPS * EPS:
                fail(f'组件 {module.id} 与 {other.id} 重叠', code='MANUAL_MODULE_COLLISION')
            if project.roof.type in ('metal', 'pitched') and plane_id(other) == pid:
                right, uphill = frame(plane.slope_deg, plane.slope_azimuth_deg)
                first = Polygon([(float(np.asarray(p) @ right), float(np.asarray(p) @ uphill)) for p in module.corners])
                second = Polygon([(float(np.asarray(p) @ right), float(np.asarray(p) @ uphill)) for p in other.corners])
            # Old flat layouts stored millimetre-rounded coordinates. Their centre
            # spacing retains that uncertainty after restoring exact catalogue edges.
            tolerance = .001 if module.id in legacy_ids or other.id in legacy_ids else EPS
            if first.distance(second) < gap - tolerance:
                fail(f'组件 {module.id} 与 {other.id} 小于目录安装间隙 {gap:g} m', code='MANUAL_MODULE_COLLISION')


def apply(project, design, operation):
    """Return a fully checked candidate; failed batches never mutate the input."""
    from .design_locks import enforce, locked_ids, recount, verify_geometry
    from .layout import _catalog
    supported(project, design)
    verify_geometry(project, design)
    op = operation['op']
    allowed = {'op', 'placements'} if op == 'add_modules' else {'op', 'module_ids', 'dx_m', 'dy_m'} if op == 'move_modules' else {'op', 'module_ids', 'angle_deg'}
    if set(operation) - allowed:
        fail('手动编辑包含不支持的字段')
    catalogue, gap, lower = _catalog(project, design.params)
    candidate = design.model_copy(deep=True)
    legacy_ids = set(design.statistics.get('manual_legacy_geometry_ids', [
        m.id for m in design.modules if all(abs(v - round(v, 3)) < 1e-10 for p in m.corners for v in p)]))
    changed = set()
    if op == 'add_modules':
        placements = operation.get('placements')
        if not isinstance(placements, list) or not 1 <= len(placements) <= 100:
            fail('每次补放须提供 1 至 100 个组件中心')
        row = max((m.row for m in [*design.modules, *design.removed_modules]), default=0)
        for item in placements:
            if not isinstance(item, dict) or set(item) - {'center', 'plane_id', 'orientation', 'rotation_deg'}:
                fail('补放组件须提供中心、所属坡面及可选朝向')
            center = item.get('center')
            if not isinstance(center, (list, tuple)) or len(center) != 2:
                fail('组件中心须为 [x, y] 两个米制坐标')
            center = [number(v, '组件中心') for v in center]
            orientation = item.get('orientation', design.params.orientation)
            if orientation not in ('portrait', 'landscape'):
                fail('组件横竖放参数不正确')
            plane = surface(project, design, item.get('plane_id'))
            row += 1
            module = panel(project, design, center, orientation, angle(item.get('rotation_deg', 0), '旋转角度'),
                           plane, catalogue, lower, row=row)
            candidate.modules.append(module)
            changed.add(module.id)
    else:
        ids = operation.get('module_ids')
        available = {m.id: m for m in design.modules}
        if not isinstance(ids, list) or not ids or any(not isinstance(mid, str) for mid in ids) or len(ids) != len(set(ids)) or not set(ids) <= available.keys():
            fail('请选择存在且不重复的组件编号')
        if set(ids) & locked_ids(design):
            fail('此次变更包含已锁定组件', '先由用户明确解除相关组件、区域或坡面锁定', 'DESIGN_LOCK_CONFLICT')
        dx, dy = (number(operation.get(key), key) for key in ('dx_m', 'dy_m')) if op == 'move_modules' else (0, 0)
        rotation = angle(operation.get('angle_deg'), '旋转角度') if op == 'rotate_modules' else 0
        if op == 'move_modules' and dx == 0 and dy == 0 or op == 'rotate_modules' and rotation % 360 == 0:
            fail('此次操作不会改变组件位置或角度', '填写非零位移或有效旋转角度', 'MANUAL_MODULE_NO_CHANGE')
        changed = set(ids)
        candidate.modules = [panel(project, design, [m.center[0] + dx, m.center[1] + dy], m.orientation, rotation,
                                   surface(project, design, plane_id(m)), catalogue, lower, original=m)
                             if m.id in changed else m for m in candidate.modules]
    # Region and plane locks protect empty space as well as existing panels.
    enforce(design, candidate)
    validate_placements(project, candidate, changed, gap, legacy_ids)
    recount(project, candidate)
    candidate.statistics.update(manual_edits=True, geometry_sky=True, partial_reflow=True)
    candidate.statistics['manual_legacy_geometry_ids'] = sorted(legacy_ids & {m.id for m in candidate.modules})
    return candidate, f"{'补放' if op == 'add_modules' else '移动' if op == 'move_modules' else '旋转'} {len(changed)} 块组件"
