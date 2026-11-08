"""Immutable placement locks shared by manual edits and the agent's tools."""
from copy import deepcopy
import hashlib
import json
import re

from shapely.geometry import Polygon
from shapely.ops import unary_union

from .models import GzError, LockedRegion, validated


FIELDS = ('locked_module_ids', 'locked_plane_ids', 'locked_regions')


def has_locks(design):
    return any(getattr(design, field) for field in FIELDS)


def geometry_signature(project):
    """Freeze the roof's absolute datum and panel hardware, but allow economic/load inputs."""
    roof = project.roof.model_dump(mode='json')
    geometry = {key: roof.get(key) for key in ('type', 'outline', 'height_m', 'slope_deg', 'slope_azimuth_deg', 'ground', 'carport')}
    geometry['planes'] = [{key: plane.get(key) for key in
        ('id', 'outline', 'slope_deg', 'slope_azimuth_deg', 'offset_m', 'material', 'part_id')}
        for plane in roof.get('planes', [])]
    # Preserve pre-segment lock hashes; explicit walls, including [], are physical geometry.
    if project.roof.parapet_segments is not None:
        geometry['parapet_segments'] = sorted(roof['parapet_segments'], key=lambda s: (s['edge_index'], s['start_ratio']))
    geometry['module_id'], geometry['racking'] = project.equipment.module_id, project.equipment.racking
    return hashlib.sha256(json.dumps(geometry, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def verify_geometry(project, design):
    if not has_locks(design):
        return
    if design.locked_geometry_sha256 is None:
        raise GzError('DESIGN_LOCK_GEOMETRY_UNKNOWN', '锁定记录缺少屋面基准，不能确认原位置', '由用户解除原锁定后，按当前屋面重新核对并锁定')
    if design.locked_geometry_sha256 != geometry_signature(project):
        raise GzError('DESIGN_LOCK_GEOMETRY_CHANGED', '屋面几何、离地基准或组件安装规格与锁定时不同', '先恢复原屋面与组件规格，或由用户解除锁定后重新设计')


def plane_id(module):
    return int(module.id.split('-', 1)[0][1:]) if module.id.startswith('P') else None


def footprint(module):
    return Polygon([point[:2] for point in module.corners])


def locked_ids(design):
    regions = [Polygon(region.polygon) for region in design.locked_regions]
    return {module.id for module in design.modules if module.id in design.locked_module_ids
            or plane_id(module) in design.locked_plane_ids
            or any(footprint(module).intersection(region).area > 1e-9 for region in regions)}


def apply_operation(project, design, operation, author):
    """Apply one explicit lock operation; unlocks require the user's editing route."""
    op = operation['op']
    if op.startswith('unlock_') and author != 'user':
        raise GzError('DESIGN_LOCK_USER_REQUIRED', '解除锁定需要用户操作', '请用户在局部修改中解锁后，再继续优化')
    unlocking = op.startswith('unlock_')
    if not unlocking:
        verify_geometry(project, design)
    if op.endswith('_modules'):
        ids = operation.get('module_ids')
        available = {module.id for module in design.modules}
        if not isinstance(ids, list) or not ids or any(not isinstance(value, str) for value in ids) or not set(ids) <= available:
            raise GzError('DESIGN_EDIT_INVALID', '组件选择为空或包含不存在的编号', '从当前版本选择需要锁定或解锁的组件')
        design.locked_module_ids = sorted(set(design.locked_module_ids).difference(ids) if unlocking
                                         else set(design.locked_module_ids).union(ids))
    elif op.endswith('_plane'):
        identifier = operation.get('plane_id')
        if type(identifier) is not int or identifier not in {plane.id for plane in project.roof.planes}:
            raise GzError('ROOF_PLANES_INVALID', '找不到需要锁定的坡面', '选择当前屋顶已有的坡面编号')
        design.locked_plane_ids = sorted(set(design.locked_plane_ids).difference([identifier]) if unlocking
                                        else set(design.locked_plane_ids).union([identifier]))
    elif op.endswith('_region'):
        identifier = operation.get('id')
        if unlocking:
            if identifier not in {region.id for region in design.locked_regions}:
                raise GzError('ZONE_NOT_FOUND', '找不到锁定区域', '选择当前版本已有的锁定区域编号')
            design.locked_regions = [region for region in design.locked_regions if region.id != identifier]
        else:
            region = validated(LockedRegion, dict(id=identifier, polygon=operation.get('polygon')), 'DESIGN_EDIT_INVALID')
            if not Polygon(project.roof.outline).buffer(.001).covers(Polygon(region.polygon)):
                raise GzError('DESIGN_EDIT_INVALID', '锁定区域超出屋顶', '请在屋顶轮廓内选择区域')
            if identifier in {region.id for region in design.locked_regions}:
                raise GzError('DESIGN_EDIT_INVALID', '锁定区域编号已存在', '使用新编号，或先解除原区域锁定')
            design.locked_regions.append(region)
    if has_locks(design) and design.locked_geometry_sha256 is None:
        design.locked_geometry_sha256 = geometry_signature(project)
    if not has_locks(design):
        design.locked_geometry_sha256 = None
    return f"{'解除' if unlocking else '设置'}锁定；当前保留 {len(locked_ids(design))} 块组件"


def enforce(previous, candidate, *, allow_lock_changes=False):
    """A final persistence barrier, including callers that bypass edit_design."""
    if not has_locks(previous):
        return
    if not allow_lock_changes and any(getattr(previous, field) != getattr(candidate, field) for field in FIELDS):
        raise GzError('DESIGN_LOCK_CONFLICT', '新方案不能移除或改写已有锁定', '使用局部重排保留锁定；解除锁定须由用户操作')
    protected = previous.model_copy(deep=True)
    if allow_lock_changes:
        # Only locks still present after the user's explicit unlock apply to the old state.
        protected.locked_module_ids = [mid for mid in previous.locked_module_ids if mid in candidate.locked_module_ids]
        protected.locked_plane_ids = [pid for pid in previous.locked_plane_ids if pid in candidate.locked_plane_ids]
        protected.locked_regions = [region for region in previous.locked_regions if region in candidate.locked_regions]
    if has_locks(protected) and candidate.locked_geometry_sha256 != previous.locked_geometry_sha256:
        raise GzError('DESIGN_LOCK_GEOMETRY_CHANGED', '不能改写已有锁定的屋面基准', '先由用户解除原锁定，再按新的屋面设计并锁定')
    locked = locked_ids(protected)
    before = {module.id: module for module in previous.modules}
    after = {module.id: module for module in candidate.modules}
    if any(identifier not in after or before[identifier] != after[identifier] for identifier in locked):
        raise GzError('DESIGN_LOCK_CONFLICT', '修改会删除或移动已锁定组件', '先调整可编辑区域或参数；需要改动锁定组件时由用户解锁')
    # Region/face locks freeze empty space too, so regeneration cannot add panels into it.
    occupied = protected.model_copy(update=dict(modules=candidate.modules))
    if locked_ids(occupied) - locked:
        raise GzError('DESIGN_LOCK_CONFLICT', '修改会向锁定区域添加组件', '只在未锁定区域重排')


def recount(project, design):
    from .layout import _catalog
    catalog, _, _ = _catalog(project, design.params)
    power = float(catalog['stc_w']) / 1000
    panel_area = float(catalog['length_m']) * float(catalog['width_m'])
    design.statistics.update(module_count=len(design.modules), dc_kw=len(design.modules) * power,
                             rows=len({(plane_id(module), module.row) for module in design.modules}),
                             module_area_ratio=len(design.modules) * panel_area / Polygon(project.roof.outline).area)
    if design.params.fill_landscape:
        design.statistics['fill_landscape_count'] = sum(module.orientation == 'landscape' for module in design.modules)
    for row in design.statistics.get('planes', []):
        modules = [module for module in design.modules if plane_id(module) == row['id']]
        row.update(module_count=len(modules), dc_kw=len(modules) * power)
        stats = row.get('statistics')
        if stats is not None:
            stats.update(module_count=len(modules), dc_kw=len(modules) * power, rows=len({module.row for module in modules}))
            if stats.get('roof_area_m2'):
                stats['module_area_ratio'] = len(modules) * panel_area / stats['roof_area_m2']


def reflow(project, previous, params):
    """Search the existing deterministic grid, then retain protected placements verbatim."""
    from .layout import generate_layout, usable_geometry, _catalog
    from .installation import inherit_keepouts
    verify_geometry(project, previous)
    fresh = inherit_keepouts(generate_layout(project, params), previous)
    fresh.modules_per_string = previous.modules_per_string
    if previous.statistics.get('manual_edits') or previous.statistics.get('geometry_sky'):
        fresh.statistics['geometry_sky'] = True
    if not has_locks(previous):
        return fresh
    if project.roof.type in ('ground', 'carport'):
        raise GzError('DESIGN_LOCK_REFLOW_UNSUPPORTED', '地面或车棚结构联动暂不支持锁定重排', '保留当前版本，或由用户解除锁定后重新生成')
    locked = locked_ids(previous)
    retained = [module.model_copy(deep=True) for module in previous.modules if module.id in locked]
    if fresh.params.plane_ids is not None and any(plane_id(module) not in fresh.params.plane_ids for module in retained):
        raise GzError('DESIGN_LOCK_CONFLICT', '选用坡面不能排除已有锁定组件所在屋面', '把已锁定坡面保留在选用列表中；仅未锁定区域会重新排布')
    usable = usable_geometry(project, fresh.params)['usable'].buffer(.001)
    for module in retained:
        allowed = usable
        if project.roof.type == 'pitched':
            from .pitched import geometry
            plane = next((plane for plane in project.roof.planes if plane.id == plane_id(module)), None)
            if plane is None:
                raise GzError('DESIGN_LOCK_GEOMETRY_CHANGED', '已锁定组件所属坡面已不存在', '恢复原坡面，或由用户解除锁定后重新设计')
            allowed = geometry(project, fresh.params, plane)['usable'].buffer(.001)
        if not allowed.covers(footprint(module)):
            raise GzError('DESIGN_LOCK_CONFLICT', f'新避让参数与锁定组件 {module.id} 冲突', '缩小此次修改范围，或由用户解除相关组件锁定')
    _, seam, _ = _catalog(project, fresh.params)
    exclusions = [footprint(module).buffer(max(seam, .001) - 1e-9) for module in retained]
    exclusions += [Polygon(region.polygon) for region in previous.locked_regions]
    exclusions += [Polygon(plane.outline) for plane in project.roof.planes if plane.id in previous.locked_plane_ids]
    blocked = unary_union(exclusions)
    generated = [module for module in fresh.modules if footprint(module).intersection(blocked).area <= 1e-9]
    old_by_geometry = {tuple(module.corners): module for module in previous.modules if module.id not in locked}
    maximum_row = max((module.row for module in [*previous.modules, *previous.removed_modules]), default=0)
    used = set(locked)
    for module in generated:
        old = old_by_geometry.get(tuple(module.corners))
        if old is not None and old.id not in used and old.tilt == module.tilt and old.azimuth == module.azimuth:
            module.id, module.row, module.col, module.tier = old.id, old.row, old.col, old.tier
        else:
            module.row += maximum_row
            module.id = re.sub(r'R\d+-', f'R{module.row:02d}-', module.id)
        used.add(module.id)
    fresh.modules = retained + generated
    for field in FIELDS:
        setattr(fresh, field, deepcopy(getattr(previous, field)))
    fresh.locked_geometry_sha256 = previous.locked_geometry_sha256
    fresh.removed_modules = deepcopy(previous.removed_modules)
    fresh.statistics['partial_reflow'] = True
    if previous.statistics.get('manual_edits') and retained:
        fresh.statistics['manual_edits'] = True
        inherited = set(previous.statistics.get('manual_legacy_geometry_ids', [])) & {module.id for module in retained}
        inherited.update(module.id for module in generated
                         if all(abs(value - round(value, 3)) < 1e-10 for point in module.corners for value in point))
        if inherited:
            fresh.statistics['manual_legacy_geometry_ids'] = sorted(inherited)
    recount(project, fresh)
    enforce(previous, fresh)
    return fresh


def changes(before, after):
    old = {module.id: module for module in before.modules}
    new = {module.id: module for module in after.modules}
    common = old.keys() & new.keys()
    return dict(before_count=len(old), after_count=len(new),
                dc_kw=dict(before=before.statistics.get('dc_kw'), after=after.statistics.get('dc_kw')),
                added=sorted(new.keys() - old.keys()), removed=sorted(old.keys() - new.keys()),
                moved=sorted(mid for mid in common if old[mid] != new[mid]),
                retained=sorted(mid for mid in common if old[mid] == new[mid]), locked=sorted(locked_ids(after)),
                analysis_status='not_recomputed',
                analysis_note='几何预览；发电、造价、回本和组串须针对新方案复算')
