"""Local project storage and append-only design versions."""

import argparse
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


def save_design(project_id, design, *, offline=False, shadows=None):
    version = _version(design.version if isinstance(design, Design) else design.get("version") if isinstance(design, dict) else None)
    path = _path(project_id, f"designs/v{version}.json")
    if path.exists():
        raise GzError("DESIGN_VERSION_EXISTS", "该方案版本已存在，不能覆盖", "用next_version获取新版本号后再保存")
    design = validated(Design, design, "DESIGN_INVALID")
    project = load(project_id)
    if version != next_version(project_id):
        raise GzError("DESIGN_VERSION_INVALID", "新方案版本号须接在已有版本之后", "用next_version获取下一个版本号")
    from .personal import prepare
    design = prepare(project, design, offline=offline, shadows=shadows)
    _write(path, design, exclusive=True)
    project.designs.append(f"v{version}")
    save(project)
    return design


def edit_design(project_id, version, ops, reason, author, *, offline=False):
    from .layout import generate_layout, usable_geometry
    if not isinstance(reason, str) or not reason.strip() or author not in ("agent", "user", "rule"):
        raise GzError("DESIGN_EDIT_INVALID", "修改须填写原因和合法修改人", "填写原因，修改人使用agent、user或rule")
    project, design = load(project_id), load_design(project_id, version)
    from .installation import effective, inherit_keepouts
    project = effective(project, design)
    original_ids = {m.id for m in design.modules}
    before, new_version, details = len(design.modules), next_version(project_id), []
    if not isinstance(ops, list) or not ops:
        raise GzError("DESIGN_EDIT_INVALID", "修改操作不能为空", "填写至少一项允许的修改操作")
    repacked = False
    for index, operation in enumerate(ops, 1):
        if not isinstance(operation, dict):
            raise GzError("DESIGN_EDIT_INVALID", "每项修改须是操作对象", "填写op及该操作所需字段")
        active = effective(project, design).model_copy(deep=True)
        active.roof.keepouts += design.added_keepouts
        op = operation.get("op")
        where = operation.get("where", {})
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
            fresh = inherit_keepouts(generate_layout(active, arguments), design)
            fresh.modules_per_string = design.modules_per_string
            design = fresh
            repacked = True
            details.append(f"重新排板，之前删除的组件和删除记录已重置（{name}）")
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
    save_design(project_id, design, offline=offline)
    return dict(version=new_version, summary=f"组件 {before} → {len(design.modules)}；" + "；".join(details))


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
