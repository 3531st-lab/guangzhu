"""Local project storage and append-only design versions."""

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import Polygon

from .config import PROJECTS_DIR
from .models import (Design, GzError, Keepout, LayoutParams, Project, RemovedModule, Requirements,
                     obstacle_polygon, project_id as validate_id, validate_project, validated)


def _path(identifier, relative=""):
    root = Path(PROJECTS_DIR).resolve()
    path = (root / validate_id(identifier) / relative).resolve()
    if not path.is_relative_to(root):
        raise GzError("PROJECT_PATH_INVALID", "项目路径超出项目目录", "移除指向项目目录之外的链接，并使用合法项目编号")
    return path


def _read(path, model):
    try:
        return validated(model, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GzError("FILE_READ_FAILED", "无法读取项目或方案文件", "检查项目编号、版本号和JSON文件是否存在且完整") from error


def _write(path, record, exclusive=False):
    contents = record.model_dump_json(by_alias=True, indent=2) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as stream:
            stream.write(contents)
    except FileExistsError as error:
        raise GzError("DESIGN_VERSION_EXISTS", "该方案版本已存在，不能覆盖", "用next_version获取新版本号后再保存") from error
    except OSError as error:
        raise GzError("FILE_WRITE_FAILED", "无法保存项目或方案文件", "检查项目目录的写入权限和磁盘空间") from error


def init(from_dir, identifier=None):
    source = Path(from_dir)
    project = _read(source / "project.json", Project)
    if identifier is not None:
        project = project.model_copy(update={"id": validate_id(identifier), "designs": [], "requirements": Requirements()})
    destination = _path(project.id)
    if destination.exists():
        raise GzError("PROJECT_EXISTS", "该项目已存在", "加载现有项目，或给演示项目换一个新编号")
    try:
        if identifier is None:
            shutil.copytree(source, destination)
        else:
            image = Path(project.roof.underlay.image) if project.roof.underlay else None
            if image is not None and (image.is_absolute() or ".." in image.parts or not image.name
                    or not (source / image).resolve().is_relative_to(source.resolve())
                    or not (destination / "underlay" / image.name).resolve().is_relative_to(destination)):
                raise GzError("PROJECT_INIT_FAILED", "屋顶底图必须位于来源及新项目目录内", "用目录内的相对底图路径，不要跨项目引用")
            destination.mkdir(parents=True, exist_ok=False)
            if image is not None:
                target = Path("underlay") / image.name
                (destination / target).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / image, destination / target)
                project.roof.underlay.image = target.as_posix()
    except FileExistsError as error:
        raise GzError("PROJECT_EXISTS", "该项目已存在", "加载现有项目，或给演示项目换一个新编号") from error
    except OSError as error:
        raise GzError("PROJECT_INIT_FAILED", "无法复制演示项目", "检查来源目录和项目目录的读写权限") from error
    save(project)
    return project


def load(project_id):
    return _read(_path(project_id, "project.json"), Project)


def save(project):
    project = validate_project(project)
    from .park_store import transaction
    with transaction(_path(project.id)):
        if _path(project.id, 'project.json').exists():
            from .design_locks import geometry_signature, has_locks
            latest = next_version(project.id) - 1
            if latest and has_locks(load_design(project.id, latest)):
                if geometry_signature(load(project.id)) != geometry_signature(project):
                    raise GzError('DESIGN_LOCK_GEOMETRY_CHANGED', '已有锁定方案，不能覆盖屋面几何或组件安装规格',
                                  '先由用户解除锁定，再修改屋面高度、坡面、组件或支架')
        _write(_path(project.id, "project.json"), project)
    return project


def _version(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GzError("DESIGN_VERSION_INVALID", "方案版本号须为正整数", "填写从1开始的整数版本号")
    return value


def load_design(project_id, version):
    return _read(_path(project_id, f"designs/v{_version(version)}.json"), Design)


def next_version(project_id):
    versions = [int(match[1]) for p in _path(project_id, "designs").glob("v*.json")
                if (match := re.fullmatch(r"v([1-9]\d*)\.json", p.name))]
    return max(versions, default=0) + 1


def save_design(project_id, design, *, offline=False, shadows=None, _allow_lock_changes=False):
    from .park_store import transaction
    with transaction(_path(project_id)):
        return _save_design(project_id, design, offline=offline, shadows=shadows, _allow_lock_changes=_allow_lock_changes)


def _save_design(project_id, design, *, offline=False, shadows=None, _allow_lock_changes=False):
    version = _version(design.version if isinstance(design, Design) else design.get("version") if isinstance(design, dict) else None)
    path = _path(project_id, f"designs/v{version}.json")
    if path.exists():
        raise GzError("DESIGN_VERSION_EXISTS", "该方案版本已存在，不能覆盖", "用next_version获取新版本号后再保存")
    design = validated(Design, design, "DESIGN_INVALID")
    project = load(project_id)
    if version != next_version(project_id):
        raise GzError("DESIGN_VERSION_INVALID", "新方案版本号须接在已有版本之后", "用next_version获取下一个版本号")
    from .design_locks import has_locks, geometry_signature, verify_geometry
    from .installation import effective
    active = effective(project, design)
    if has_locks(design) and design.locked_geometry_sha256 is None:
        design.locked_geometry_sha256 = geometry_signature(active)
    verify_geometry(active, design)
    from .personal import prepare
    design = prepare(project, design, offline=offline, shadows=shadows)
    _enforce_latest_locks(project_id, design, allow_lock_changes=_allow_lock_changes)
    _write(path, design, exclusive=True)
    project.designs.append(f"v{version}")
    save(project)
    return design


def _enforce_latest_locks(project_id, design, *, allow_lock_changes=False):
    from .design_locks import enforce, has_locks
    latest = next_version(project_id) - 1
    if latest:
        previous = load_design(project_id, latest)
        if has_locks(previous):
            if design.parent_version != latest:
                raise GzError('DESIGN_LOCK_STALE', '存在较新的锁定方案，请先打开最新版本', '从最新版本预览并应用修改，不能用旧版本绕过锁定')
            enforce(previous, design, allow_lock_changes=allow_lock_changes)


def edit_fingerprint(project_id, version, ops, reason, author):
    payload = dict(project=load(project_id).model_dump(mode='json'),
                   source=load_design(project_id, version).model_dump(mode='json'),
                   latest_version=next_version(project_id) - 1, ops=ops, reason=reason, author=author)
    try:
        contents = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))
    except (TypeError, ValueError) as error:
        raise GzError('DESIGN_EDIT_INVALID', '修改参数必须为有限数值和合法JSON数据', '检查修改内容后重新预览') from error
    return hashlib.sha256(contents.encode('utf-8')).hexdigest()


def preview_edit(project_id, version, ops, reason, author='user', *, offline=False):
    fingerprint = edit_fingerprint(project_id, version, ops, reason, author)
    design, summary = _edited_design(project_id, version, ops, reason, author)
    from .personal import prepare
    from .design_locks import changes, verify_geometry
    from .installation import effective
    current = load(project_id)
    verify_geometry(effective(current, design), design)
    design = prepare(current, design, offline=offline)
    _enforce_latest_locks(project_id, design, allow_lock_changes=True)
    # A concurrent write or a changed project invalidates this preview immediately.
    if fingerprint != edit_fingerprint(project_id, version, ops, reason, author):
        raise GzError('DESIGN_PREVIEW_STALE', '预览期间项目已改变', '重新预览后再确认')
    return dict(design=design.model_dump(mode='json'), summary=summary,
                changes=changes(load_design(project_id, version), design), fingerprint=fingerprint)


def edit_design(project_id, version, ops, reason, author, *, offline=False, expected_fingerprint=None):
    # Reuse the application's reentrant OS lock: HTTP and MCP may live in separate processes.
    from .park_store import transaction
    with transaction(_path(project_id)):
        return _commit_edit(project_id, version, ops, reason, author, offline=offline,
                            expected_fingerprint=expected_fingerprint)


def _commit_edit(project_id, version, ops, reason, author, *, offline=False, expected_fingerprint=None):
    if expected_fingerprint is not None and expected_fingerprint != edit_fingerprint(project_id, version, ops, reason, author):
        raise GzError('DESIGN_PREVIEW_STALE', '预览已过期或修改内容发生变化', '重新预览，核对变化后再确认')
    result = preview_edit(project_id, version, ops, reason, author, offline=offline)
    if (expected_fingerprint is not None and result['fingerprint'] != expected_fingerprint
            or result['fingerprint'] != edit_fingerprint(project_id, version, ops, reason, author)):
        raise GzError('DESIGN_PREVIEW_STALE', '确认期间项目发生变化，原预览已过期', '重新预览并确认后再保存')
    design = validated(Design, result['design'], 'DESIGN_INVALID')
    save_design(project_id, design, offline=offline, _allow_lock_changes=True)
    return dict(version=design.version, summary=result['summary'])


def _edited_design(project_id, version, ops, reason, author):
    from .layout import usable_geometry
    from .design_locks import apply_operation, locked_ids, reflow
    if not isinstance(reason, str) or not reason.strip() or author not in ("agent", "user", "rule"):
        raise GzError("DESIGN_EDIT_INVALID", "修改须填写原因和合法修改人", "填写原因，修改人使用agent、user或rule")
    project, design = load(project_id), load_design(project_id, version)
    from .installation import effective
    project = effective(project, design)
    original_ids = {m.id for m in design.modules}
    before, new_version, details = len(design.modules), next_version(project_id), []
    if not isinstance(ops, list) or not ops:
        raise GzError("DESIGN_EDIT_INVALID", "修改操作不能为空", "填写至少一项允许的修改操作")
    if any(isinstance(operation, dict) and operation.get('op') == 'undo_last_edit' for operation in ops):
        if author != 'user':
            raise GzError('DESIGN_LOCK_USER_REQUIRED', '撤销修改需要用户操作', '请用户在局部修改中预览并确认撤销')
        if len(ops) != 1 or set(ops[0]) != {'op'}:
            raise GzError('DESIGN_EDIT_INVALID', '撤销必须是独立的一次操作', '单独预览撤销上次修改，再进行其他编辑')
        if version != new_version - 1 or design.parent_version is None:
            raise GzError('DESIGN_UNDO_UNAVAILABLE', '只有最新版本且存在父版本时才能撤销', '打开最新方案，确认它由已有方案修改而来')
        restored = load_design(project_id, design.parent_version).model_copy(deep=True)
        if design.statistics.get('manual_edits') or design.statistics.get('geometry_sky'):
            restored.statistics['geometry_sky'] = True
        restored.version, restored.parent_version = new_version, version
        restored.reason, restored.author, restored.created_at = reason, author, datetime.now(timezone.utc)
        return restored, f'撤销 v{version} 的修改，恢复 v{design.parent_version} 的排布与锁定；保存为 v{new_version}'
    repacked, manual_changed = False, False
    for index, operation in enumerate(ops, 1):
        if not isinstance(operation, dict):
            raise GzError("DESIGN_EDIT_INVALID", "每项修改须是操作对象", "填写op及该操作所需字段")
        active = effective(project, design).model_copy(deep=True)
        active.roof.keepouts += design.added_keepouts
        op = operation.get("op")
        where = operation.get("where", {})
        if op in ('lock_modules', 'unlock_modules', 'lock_plane', 'unlock_plane', 'lock_region', 'unlock_region'):
            details.append(apply_operation(active, design, operation, author))
            continue
        if op in ('add_modules', 'move_modules', 'rotate_modules'):
            from .manual_modules import apply
            design, detail = apply(active, design, operation)
            manual_changed = True
            details.append(detail)
            continue
        if manual_changed and op == 'remove_modules' and isinstance(where, dict) and (
                'shading_loss_gt' in where or 'worst_count' in where):
            raise GzError('DESIGN_EDIT_DEPENDENCY', '手动位置已改变，不能按旧遮挡结果继续删除组件',
                          '先保存新版本并重新分析，再按该版本的遮挡结果编辑')
        if op == 'reflow_unlocked':
            updates = operation.get('params', {})
            if not isinstance(updates, dict):
                raise GzError('LAYOUT_PARAMS_INVALID', '重排参数须为对象', '填写params中的排布参数')
            params = validated(LayoutParams, design.params.model_dump() | updates, 'LAYOUT_PARAMS_INVALID')
            design = reflow(active, design, params)
            repacked = True
            details.append('保留锁定组件与区域，对未锁定部分重新排板')
            continue
        if repacked and op == "remove_modules" and ("module_ids" in operation or isinstance(where, dict)
                and ("shading_loss_gt" in where or "worst_count" in where)):
            raise GzError("DESIGN_EDIT_DEPENDENCY", "改参数会重新排板，请先单独改参数并重新分析，再删组件", "先仅执行set_param，再分析新版本并按新建议删除组件")
        if op == "set_param":
            name = operation.get("name")
            if project.roof.type in ("metal", 'pitched') and name in ("tilt_deg", "azimuth_deg", "rows_per_rack", "winter_window_hours"):
                if project.roof.type == 'pitched':
                    raise GzError('ROOF_PLANE_PARAM_FIXED', '整栋各面顺坡平铺，角度由真实坡面决定', '在屋顶资料中修改对应坡面')
                raise GzError("METAL_PARAM_FIXED", "彩钢瓦顺坡平铺，倾角和朝向跟着屋面走", "改屋顶资料中的坡度和坡向")
            if name not in LayoutParams.model_fields or "value" not in operation:
                raise GzError("LAYOUT_PARAMS_INVALID", "排板参数名称不正确或缺少值", "只修改gz_generate_layout列出的参数，并填写value")
            params = validated(LayoutParams, design.params.model_dump() | {name: operation["value"]}, "LAYOUT_PARAMS_INVALID")
            arguments = params
            if project.roof.type == 'carport':
                arguments = params.model_dump(exclude={'tilt_deg', 'clear_height_m'} - {name})
            fresh = reflow(active, design, arguments)
            design = fresh
            repacked = True
            details.append(f"重新排板，保留锁定部分（{name}）" if locked_ids(design)
                           else f"重新排板，之前删除的组件和删除记录已重置（{name}）")
            continue
        if op == "set_string_size":
            value = operation.get("modules_per_string")
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise GzError("STRING_SIZE_INVALID", "每串组件数须为正整数", "填写大于0的整数，电气校核将在T06进行")
            design.modules_per_string = value
            details.append(f"每串{value}块")
            continue
        if op == "add_keepout":
            zone = validated(Keepout, dict(id=f"edit-v{new_version}-{index}", label=operation.get("label"),
                             polygon=operation.get("polygon"), preset=operation.get('preset'),
                             clearance_m=operation.get('clearance_m')), "KEEPOUT_POLYGON_INVALID")
            active.roof.keepouts.append(zone)
            validate_project(active.model_dump(by_alias=True))
            design.added_keepouts.append(zone)
            from .livestock import clearance
            polygon = Polygon(zone.polygon).buffer(clearance(active.roof, zone, design.params.keepout_clearance_m))
            removal_reason = f"新增禁区 {zone.label}"
            select = lambda module: polygon.intersects(Polygon([p[:2] for p in module.corners]))
            design.statistics.update(usable_geometry(active, design.params)["area_statistics"])
        elif op == "remove_modules":
            where = operation.get("where", {})
            if not isinstance(where, dict):
                raise GzError("DESIGN_EDIT_INVALID", "删除条件须是对象", "填写where.zone_id，或使用module_ids数组")
            if "shading_loss_gt" in where or "worst_count" in where:
                threshold = where.get("shading_loss_gt", 0)
                count = where.get("worst_count")
                if "worst_count" in where and (type(count) is not int or not 1 <= count <= len(original_ids)):
                    raise GzError("DESIGN_EDIT_INVALID", "删除数量须为不超过原版本组件数的正整数", "填写where.worst_count的整数数量")
                if type(threshold) not in (int, float) or not 0 <= threshold <= 100:
                    raise GzError("DESIGN_EDIT_INVALID", "遮挡损失阈值须为0到100之间的有限数值", "填写where.shading_loss_gt的百分比数值")
                try:
                    result = json.loads(_path(project_id, f"analysis/v{version}/shading.json").read_text(encoding="utf-8"))
                    if (not isinstance(result, dict) or type(result.get("version")) is not int or result["version"] != version
                            or not isinstance(result.get("modules"), list)):
                        raise ValueError
                    losses = {}
                    for item in result["modules"]:
                        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in losses:
                            raise ValueError
                        loss = item.get("total_loss_pct")
                        if type(loss) not in (int, float) or not 0 <= loss <= 100:
                            raise ValueError
                        losses[item["id"]] = loss
                    if set(losses) != original_ids or not {m.id for m in design.modules} <= original_ids:
                        raise ValueError
                except FileNotFoundError as error:
                    raise GzError("ANALYSIS_MISSING", "该方案版本还没有遮挡分析结果", "先对该版本运行遮挡分析") from error
                except (OSError, UnicodeError, ValueError) as error:
                    raise GzError("ANALYSIS_INVALID", "该版本遮挡结果损坏或组件不匹配", "重新对该版本运行遮挡分析") from error
                ids = set(sorted(losses, key=lambda identifier: (-losses[identifier], identifier))[:count]) if count is not None else set()
                select = lambda module: module.id in ids if count is not None else losses[module.id] > threshold
            elif "zone_id" in where:
                zones = {o.id: obstacle_polygon(o) for o in active.roof.obstacles}
                zones.update({k.id: Polygon(k.polygon) for k in active.roof.keepouts})
                if where["zone_id"] not in zones:
                    raise GzError("ZONE_NOT_FOUND", "找不到指定障碍物或禁区", "检查where.zone_id是否与项目或方案禁区编号一致")
                polygon = zones[where["zone_id"]]
                select = lambda module: polygon.intersects(Polygon([p[:2] for p in module.corners]))
            else:
                ids = operation.get("module_ids")
                if not isinstance(ids, list) or not ids or not all(isinstance(v, str) for v in ids):
                    raise GzError("DESIGN_EDIT_INVALID", "删除组件须提供编号或区域编号", "填写module_ids数组或where.zone_id")
                select = lambda module: module.id in ids
            removal_reason = reason
        else:
            raise GzError("DESIGN_EDIT_INVALID", "不支持该修改操作", "使用remove_modules、set_param、set_string_size或add_keepout")
        previous = len(design.modules)
        removed = [m for m in design.modules if select(m)]
        if {module.id for module in removed} & locked_ids(design):
            raise GzError('DESIGN_LOCK_CONFLICT', '此次修改会删除已锁定组件', '调整删除范围，或由用户先解除相关锁定')
        design.modules = [m for m in design.modules if not select(m)]
        design.removed_modules += [RemovedModule(**m.model_dump(), reason=removal_reason) for m in removed]
        fraction = len(design.modules) / previous if previous else 0
        for key in ("dc_kw", "module_area_ratio"):
            design.statistics[key] = round(design.statistics.get(key, 0) * fraction, 6)
        design.statistics.update(module_count=len(design.modules), rows=len({m.row for m in design.modules}))
        if design.params.fill_landscape:
            design.statistics['fill_landscape_count'] = sum(m.orientation == 'landscape' for m in design.modules)
        details.append(f"删除{len(removed)}块，原因：{removal_reason}")
    design.version, design.parent_version = new_version, version
    design.reason, design.author, design.created_at = reason, author, datetime.now(timezone.utc)
    return design, f"组件 {before} → {len(design.modules)}；" + "；".join(details)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init"])
    parser.add_argument("--from", dest="from_dir", required=True)
    parser.add_argument("--id", dest="identifier", help="新运行的项目编号；只复制屋顶基础资料，不复制需求和运行结果")
    arguments = parser.parse_args(argv)
    try:
        project = init(arguments.from_dir, arguments.identifier)
        print(json.dumps(dict(ok=True, project_id=project.id), ensure_ascii=False))
        return 0
    except GzError as error:
        print(json.dumps(error.as_dict(), ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
