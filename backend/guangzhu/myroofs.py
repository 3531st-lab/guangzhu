"""T18: the user's own roofs, drawn in the app or traced from an imported image, PDF or DXF, saved as roof templates."""
import io
import math
import json
import re
import shutil
import time
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
from shapely.geometry import LineString, Polygon
from shapely.ops import split

from .config import ROOT
from .models import GzError, Obstacle, Project, obstacle_polygon, project_id
from .templates import resolve

BASE = "changzhou-demo"  # new roofs take the demo roof's equipment and example economics; requirements start empty
NOTE = ("自建屋顶沿用演示屋顶的示意经济参数（自用比例0.8、自用电价0.65元/kWh、折现率0.06、计算期25年），其余取 data/catalog/assumptions.csv 默认值；"
        "江苏以外地区请在填条件页按当地电价修改。")
IMAGES = ("png", "jpg", "jpeg", "bmp", "gif", "webp")
DXF_UNITS = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}  # $INSUNITS: inch, foot, mm, cm, m
LABELS = {"name": "屋顶名称", "lat": "纬度（0 到 55 度）", "lon": "经度（-180 到 180 度）", "height_m": "高度", "radius_m": "半径",
          "parapet_height_m": "女儿墙高度", "load_capacity_kn_m2": "屋面承重", "outline": "屋顶外形", "label": "名称", "distance_m": "标定距离"}


def folder(root=ROOT):
    return root / "data" / "my-roofs"


def upload(token, root=ROOT):
    if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
        raise GzError("DRAWING_NOT_FOUND", "找不到导入的图纸", "重新导入图纸")
    return folder(root) / ".uploads" / (token + ".png")


def import_drawing(name, data, page=1, root=ROOT):
    """Images and PDF pages become a PNG to trace over; a DXF gives its closed outlines to pick from."""
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    try:
        if suffix == "dxf":
            return dict(kind="dxf", **dxf_outlines(data))
        if suffix == "pdf":
            import pypdfium2
            document = pypdfium2.PdfDocument(data)
            pages = len(document)
            if not 1 <= page <= pages:
                raise GzError("DRAWING_PAGE_INVALID", f"这份 PDF 只有 {pages} 页", f"选 1 到 {pages} 页")
            width, height = document[page - 1].get_size()
            image = document[page - 1].render(scale=min(2400 / max(width, height), 8)).to_pil()  # long side about 2400 px
        elif suffix in IMAGES:
            from PIL import Image
            image, pages = Image.open(io.BytesIO(data)), 1
            image.thumbnail((3000, 3000))
        else:
            raise GzError("DRAWING_TYPE_INVALID", "只能导入图片（PNG、JPG）、PDF 或 DXF 图纸", "把图纸另存为这几种格式再导入")
        token = uuid.uuid4().hex
        upload(token, root).parent.mkdir(parents=True, exist_ok=True)
        for stale in upload(token, root).parent.glob("*.png"):  # drawings imported but never saved with a roof
            if stale.stat().st_mtime < time.time() - 86400:
                stale.unlink(missing_ok=True)
        image.convert("RGB").save(upload(token, root))
    except GzError:
        raise
    except Exception as error:
        raise GzError("DRAWING_UNREADABLE", "图纸打不开，可能已损坏或加了密码", "换一份图纸，或先导出成 PNG 再导入") from error
    return dict(kind="image", upload=token, width=image.width, height=image.height, pages=pages)


def _classify_dxf_layer(layer: str, is_largest: bool = False, is_circle: bool = False, aspect: float = 1.0) -> tuple[str, float, str]:
    upper = (layer or "").upper()
    if is_circle:
        if any(k in upper for k in ("TREE", "PLANT", "树", "绿化")):
            return "tree", 6.0, layer if layer and layer != "0" else "周边树木"
        return "tank", 3.0, layer if layer and layer != "0" else "圆形设备"
    if is_largest or any(k in upper for k in ("ROOF", "OUTLINE", "BOUNDARY", "屋面", "屋顶", "外轮廓", "轮廓")):
        return "roof", 0.0, layer if layer and layer != "0" else "屋面外轮廓"
    if any(k in upper for k in ("SKY", "LIGHT", "WINDOW", "GLAZ", "天窗", "采光", "气楼")):
        return "skylight", 0.0, layer if layer and layer != "0" else "采光带"
    if any(k in upper for k in ("VENT", "EXHAUST", "通风", "排烟", "风口")):
        return "vent", 0.0, layer if layer and layer != "0" else "通风口"
    if any(k in upper for k in ("KEEP", "ZONE", "WALK", "FIRE", "禁区", "通道", "消防", "天井")):
        return "keepout", 0.0, layer if layer and layer != "0" else "禁区"
    if any(k in upper for k in ("BLDG", "SURROUND", "NEIGH", "周边", "邻楼", "配楼")):
        return "building", 12.0, layer if layer and layer != "0" else "周边楼"
    if any(k in upper for k in ("OBSTACLE", "EQUIP", "HVAC", "MEP", "AHU", "DEV", "设备", "机房", "空调", "风机", "基础")):
        return "device", 2.5, layer if layer and layer != "0" else "屋面设备"
    if aspect >= 3.8:
        return "skylight", 0.0, "采光带"
    return "device", 2.5, layer if layer and layer != "0" else "屋面设备"


def dxf_outlines(data):
    from ezdxf import path, recover
    from shapely.ops import polygonize
    document, _ = recover.read(io.BytesIO(data))
    rows = []
    for entity in document.modelspace().query("LWPOLYLINE POLYLINE"):
        try:  # arc segments (bulges) follow the arc to 1/4000 of the outline's size (7.5 mm on a 30 m roof) instead of becoming straight lines
            curve = path.make_path(entity)
            size = max(curve.bbox().size.x, curve.bbox().size.y) if len(curve) else 0
            points = [(v.x, v.y) for v in curve.flattening(distance=max(size, 1e-6) / 4000)] if len(curve) else []
        except TypeError:  # 3D meshes and polyface outlines are not roof outlines
            continue
        closed = entity.closed if entity.dxftype() == "LWPOLYLINE" else entity.is_closed
        if len(points) > 3 and points[0] == points[-1]:
            points, closed = points[:-1], True
        shape = Polygon(points) if len(points) >= 3 else Polygon()
        if closed and shape.is_valid and shape.area > 0:
            rows.append(dict(points=[[round(x, 4), round(y, 4)] for x, y in points], area=shape.area, layer=entity.dxf.layer))
    if not rows:
        lines_by_layer: dict[str, list] = {}
        for entity in document.modelspace().query("LINE"):
            start, end = entity.dxf.start, entity.dxf.end
            if math.hypot(end.x - start.x, end.y - start.y) > 1e-6:
                lines_by_layer.setdefault(entity.dxf.layer, []).append(LineString([(start.x, start.y), (end.x, end.y)]))
        for layer_name, segs in lines_by_layer.items():
            if len(segs) >= 3:
                for poly in polygonize(segs):
                    if poly.is_valid and poly.area > 0:
                        pts = list(poly.exterior.coords)[:-1]
                        rows.append(dict(points=[[round(x, 4), round(y, 4)] for x, y in pts], area=poly.area, layer=layer_name))
    if not rows:
        raise GzError("DXF_NO_OUTLINE", "DXF 里没有找到闭合的多段线", "在 CAD 里用 BOUNDARY（边界）或 PEDIT 合并命令把屋顶外轮廓变成闭合多段线再导出")
    sorted_rows = sorted(rows, key=lambda r: -r["area"])[:30]
    for idx, row in enumerate(sorted_rows):
        xs = [p[0] for p in row["points"]]
        ys = [p[1] for p in row["points"]]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        aspect = max(w, h) / max(min(w, h), 1e-6)
        role_hint, height_hint, label_hint = _classify_dxf_layer(row["layer"], is_largest=(idx == 0), is_circle=False, aspect=aspect)
        row.update(role_hint=role_hint, height_hint=height_hint, label_hint=label_hint)
    circles = []
    for entity in document.modelspace().query("CIRCLE"):
        center = entity.dxf.center
        radius = float(entity.dxf.radius)
        if radius > 0:
            role_hint, height_hint, label_hint = _classify_dxf_layer(entity.dxf.layer, is_largest=False, is_circle=True)
            circles.append(dict(
                center=[round(center.x, 4), round(center.y, 4)],
                radius=round(radius, 4),
                area=round(math.pi * radius * radius, 4),
                layer=entity.dxf.layer,
                role_hint=role_hint,
                height_hint=height_hint,
                label_hint=label_hint,
            ))
    return dict(
        scale=DXF_UNITS.get(document.header.get("$INSUNITS", 0)),
        outlines=sorted_rows,
        circles=circles[:20],
    )


def sample_dxf_bytes(preset: str = "cmc") -> tuple[str, bytes]:
    """Generate a standard multi-layer AutoCAD DXF sample drawing for Taizhou industrial scenarios."""
    import ezdxf
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 6  # metres
    msp = doc.modelspace()
    if preset == "shipyard":
        filename = "泰州靖江海工分段车间_标准CAD.dxf"
        msp.add_lwpolyline([(0, 0), (96, 0), (96, 36), (0, 36)], close=True, dxfattribs={"layer": "ROOF_屋面外轮廓"})
        msp.add_lwpolyline([(18, 16.5), (44, 16.5), (44, 19.5), (18, 19.5)], close=True, dxfattribs={"layer": "SKYLIGHT_屋脊采光气楼"})
        msp.add_lwpolyline([(52, 16.5), (78, 16.5), (78, 19.5), (52, 19.5)], close=True, dxfattribs={"layer": "SKYLIGHT_屋脊采光气楼"})
        msp.add_lwpolyline([(12, 27), (17, 27), (17, 31), (12, 31)], close=True, dxfattribs={"layer": "EQUIP_焊接除尘机组"})
        msp.add_lwpolyline([(79, 27), (84, 27), (84, 31), (79, 31)], close=True, dxfattribs={"layer": "EQUIP_焊接除尘机组"})
        msp.add_circle((32, 29), 1.8, dxfattribs={"layer": "TANK_RTO排气筒"})
        msp.add_circle((64, 29), 1.8, dxfattribs={"layer": "TANK_RTO排气筒"})
    elif preset == "watertown":
        filename = "泰州凤城河三水湾展馆_标准CAD.dxf"
        msp.add_lwpolyline([(0, 0), (44, 0), (44, 24), (0, 24)], close=True, dxfattribs={"layer": "ROOF_屋面外轮廓"})
        msp.add_lwpolyline([(17, 8), (27, 8), (27, 16), (17, 16)], close=True, dxfattribs={"layer": "KEEPOUT_水乡采光天井"})
        msp.add_lwpolyline([(6, 17), (10, 17), (10, 20), (6, 20)], close=True, dxfattribs={"layer": "EQUIP_青砖排风亭"})
        msp.add_lwpolyline([(34, 17), (38, 17), (38, 20), (34, 20)], close=True, dxfattribs={"layer": "EQUIP_青砖排风亭"})
        msp.add_circle((-3.5, 6), 2.5, dxfattribs={"layer": "TREE_三水湾古银杏"})
        msp.add_circle((47.5, 6), 2.5, dxfattribs={"layer": "TREE_三水湾古银杏"})
    else:
        filename = "泰州中国医药城洁净厂房_标准CAD.dxf"
        msp.add_lwpolyline([(0, 0), (76, 0), (76, 20), (54, 20), (54, 30), (0, 30)], close=True, dxfattribs={"layer": "ROOF_屋面外轮廓"})
        msp.add_lwpolyline([(10, 20), (18, 20), (18, 24), (10, 24)], close=True, dxfattribs={"layer": "EQUIP_GMP洁净空调机组"})
        msp.add_lwpolyline([(26, 20), (34, 20), (34, 24), (26, 24)], close=True, dxfattribs={"layer": "EQUIP_GMP洁净空调机组"})
        msp.add_lwpolyline([(12, 8), (24, 8), (24, 10.2), (12, 10.2)], close=True, dxfattribs={"layer": "SKYLIGHT_洁净走廊采光天窗"})
        msp.add_lwpolyline([(30, 8), (42, 8), (42, 10.2), (30, 10.2)], close=True, dxfattribs={"layer": "SKYLIGHT_洁净走廊采光天窗"})
        msp.add_lwpolyline([(2, 14), (52, 14), (52, 15.2), (2, 15.2)], close=True, dxfattribs={"layer": "KEEPOUT_消防主检修通道"})
        msp.add_circle((44, 22), 1.6, dxfattribs={"layer": "TANK_酸雾洗涤塔"})
        msp.add_circle((64, 13), 1.5, dxfattribs={"layer": "TANK_纯化水膨胀罐"})
    stream = io.StringIO()
    doc.write(stream)
    return filename, stream.getvalue().encode("utf-8")


def export_roof_dxf_bytes(payload: dict) -> tuple[str, bytes]:
    """Export a roof editor payload (outline, obstacles, keepouts, surroundings) to a layered AutoCAD DXF."""
    import ezdxf
    name = (payload.get("name") or "屋顶CAD底图").strip()
    roof = payload.get("roof") or {}
    doc = ezdxf.new("R2010", setup=["linetypes"])
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for lname in ("ROOF", "OBSTACLE", "SKYLIGHT", "KEEPOUT", "SURROUNDING"):
        doc.layers.new(lname, dxfattribs={"linetype": "DASHED" if lname in ("KEEPOUT", "SKYLIGHT") else "CONTINUOUS"})
    outline = roof.get("outline") or []
    if len(outline) >= 3:
        msp.add_lwpolyline([p[:2] for p in outline], close=True, dxfattribs={"layer": "ROOF"})
    for obs in roof.get("obstacles") or []:
        if obs.get("kind") == "cylinder" and obs.get("center"):
            msp.add_circle(obs["center"][:2], float(obs.get("radius_m") or 1.0), dxfattribs={"layer": "OBSTACLE"})
        elif obs.get("footprint"):
            msp.add_lwpolyline([p[:2] for p in obs["footprint"]], close=True, dxfattribs={"layer": "OBSTACLE"})
    for kp in roof.get("keepouts") or []:
        layer = "SKYLIGHT" if kp.get("preset") == "skylight" or "天窗" in (kp.get("label") or "") or "采光" in (kp.get("label") or "") else "KEEPOUT"
        if kp.get("polygon"):
            msp.add_lwpolyline([p[:2] for p in kp["polygon"]], close=True, dxfattribs={"layer": layer})
    for sur in roof.get("surroundings") or []:
        if sur.get("kind") == "cylinder" and sur.get("center"):
            msp.add_circle(sur["center"][:2], float(sur.get("radius_m") or 2.0), dxfattribs={"layer": "SURROUNDING"})
        elif sur.get("footprint"):
            msp.add_lwpolyline([p[:2] for p in sur["footprint"]], close=True, dxfattribs={"layer": "SURROUNDING"})
    stream = io.StringIO()
    doc.write(stream)
    safe_name = re.sub(r'[\\/:*?"<>|]+', "_", name) or "roof"
    return f"{safe_name}.dxf", stream.getvalue().encode("utf-8")


def save(payload, root=ROOT, validate_only=False, create=False):
    """Create or update a roof from the editor; returns its id. Wrong input raises GzError with a Chinese reason."""
    if payload.get("roof_mode") == "metal-gable":
        return save_gable(payload, root)
    identifier = payload.get("id") or "my-" + datetime.now(timezone(timedelta(hours=8))).strftime("%m%d-%H%M%S")
    while not payload.get("id") and (folder(root) / identifier).exists():  # two new roofs saved in the same second never share a folder
        identifier += "x"
    directory = folder(root) / project_id(identifier)
    if payload.get("id") and not validate_only and not create and not (directory / "project.json").is_file():
        raise GzError("ROOF_NOT_FOUND", "这个屋顶已不存在", "回首页重新选择")
    name, site, roof, underlay = (payload.get(key) for key in ("name", "site", "roof", "underlay"))
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
        raise GzError("ROOF_NAME_INVALID", "请给屋顶起个名字（1 到 40 个字）", "在第 4 步填屋顶名称")
    base = json.loads(resolve(BASE, root=root).read_text(encoding="utf-8"))
    project = dict(base, id=identifier, name=name.strip(), requirements={}, designs=[], economics=dict(base["economics"], assumptions_note=NOTE),
                   site=dict(site or {}, timezone="Asia/Shanghai"), roof=dict(roof or {}))
    if project["roof"].get("type") == "metal":
        project["equipment"] = dict(base["equipment"], racking="clamp_barn" if project['roof'].get('use') == 'barn' else "clamp_flush")
    if project['roof'].get('type') in ('ground', 'carport'):
        kind = project['roof']['type']
        project['equipment'] = dict(base['equipment'], racking='ground_pile' if kind == 'ground' else 'carport_steel')
        project['roof'].update(height_m=0, parapet_height_m=0)
        project['economics']['assumptions_note'] = '新建场地；经济参数与工程量均为示意，待现场、接网与厂家确认'
        if kind == 'carport' and 'planes' not in project['roof']:
            from .installation import parking
            from .models import Roof
            project['roof'].update(parking(Roof.model_validate(project['roof'])))
    if project['roof'].get('type') == 'pitched':
        from .roofplane import generate
        project['equipment'] = dict(base['equipment'], racking='plane_flush')
        if not project['roof'].get('planes') and not project['roof'].get('parts'):
            project['roof']['planes'] = generate(project['roof']['outline'], project['roof'].get('pitched', {}))['planes']
    if underlay:
        project["roof"]["underlay"] = dict(image="underlay.png", calibration=underlay.get("calibration"))
    try:
        model = Project.model_validate(project)
    except ValidationError as error:
        field = next((LABELS[p] for p in reversed(error.errors()[0]["loc"]) if p in LABELS), "数据")
        raise GzError("ROOF_INPUT_INVALID", f"{field}没填或填得不对", "检查这一项再保存") from error
    area = Polygon(model.roof.outline).area
    if not 20 <= area <= 500000:
        raise GzError("ROOF_SIZE_IMPLAUSIBLE", f"屋顶面积算出来是 {area:,.0f} 平方米，不像真实厂房", "检查比例尺、标定距离或 DXF 单位")
    if underlay and not underlay.get("upload") and not (directory / "underlay.png").is_file():
        raise GzError("DRAWING_NOT_FOUND", "找不到这个屋顶原来的底图", "重新导入图纸")
    if underlay and underlay.get("upload") and not upload(underlay["upload"], root).is_file():
        raise GzError("DRAWING_NOT_FOUND", "导入的图纸已过期（导入后超过一天没保存）", "重新导入图纸")
    if validate_only:
        return model
    directory.mkdir(parents=True, exist_ok=True)
    if underlay and underlay.get("upload"):
        shutil.copyfile(upload(underlay["upload"], root), directory / "underlay.png")
    elif not underlay:
        (directory / "underlay.png").unlink(missing_ok=True)
    (directory / "project.json").write_text(model.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return identifier


def save_gable(payload, root):
    """Validate both complete roof records before creating either directory."""
    roof = dict(payload.get("roof") or {})
    if roof.get('parapet_segments'):
        raise GzError('PARAPET_SPLIT_UNSUPPORTED', '旧式双坡拆分不能保留分段女儿墙的外边编号',
                      '改用整栋坡面编辑，或先恢复统一女儿墙模式')
    save(dict(payload, roof_mode="metal-single"), root, validate_only=True)
    shape = Polygon(roof.get("outline", []))
    ridge = payload.get("ridge")
    if not ridge:
        box = list(shape.minimum_rotated_rectangle.exterior.coords)[:4]
        edges = [(math.dist(a, b), a, b) for a, b in zip(box, box[1:] + box[:1])]
        _, a, b = sorted(edges, key=lambda row: row[0])[0 if payload.get("ridge_mode") != "short" else -1]
        center = shape.centroid
        ridge = [[center.x, center.y], [center.x + b[1] - a[1], center.y - b[0] + a[0]]]
    try:
        a, b = ridge
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if len(a) != 2 or len(b) != 2 or not all(math.isfinite(v) for p in ridge for v in p):
            raise ValueError("屋脊坐标")
    except (TypeError, ValueError, IndexError) as error:
        raise GzError("RIDGE_INVALID", "屋脊需要两个有效坐标点", "重新画屋脊") from error
    if not length or not shape.is_valid:
        raise GzError("RIDGE_INVALID", "屋脊需要两个不同点和有效外形", "重新画屋脊")
    span = max(shape.bounds[2] - shape.bounds[0], shape.bounds[3] - shape.bounds[1]) * 100
    line = LineString([[a[0] - dx / length * span, a[1] - dy / length * span],
                       [a[0] + dx / length * span, a[1] + dy / length * span]])
    halves = list(split(shape, line).geoms)
    if len(halves) != 2 or any(part.area < 20 for part in halves):
        raise GzError("RIDGE_INVALID", "屋脊须把屋顶分成两个完整坡面", "调整屋脊位置")
    building = payload.get("name", "")
    identifier = "my-" + uuid.uuid4().hex[:12]
    records = []
    for index, half in enumerate(halves):
        side = dx * (half.centroid.y - a[1]) - dy * (half.centroid.x - a[0])
        vx, vy = (-dy, dx) if side > 0 else (dy, -dx)
        azimuth = math.degrees(math.atan2(vx, vy)) % 360
        direction = ("北", "东北", "东", "东南", "南", "西南", "西", "西北")[round(azimuth / 45) % 8]
        piece = dict(roof, type="metal", building=building, slope_azimuth_deg=azimuth, outline=list(half.exterior.coords)[:-1])
        for key in ("obstacles", "keepouts"):
            selected = []
            for item in roof.get(key, []):
                polygon = Polygon(item["polygon"]) if key == "keepouts" else obstacle_polygon(Obstacle.model_validate(item))
                if not any(part.covers(polygon) for part in halves):
                    raise GzError("RIDGE_ZONE_CROSSING", f"{item['label']}跨屋脊，请分成两个", "请分成两个后再保存")
                if half.covers(polygon):
                    selected.append(item)
            piece[key] = selected
        record = dict(payload, id=identifier + f"-{index}", name=building + f"（{direction}坡）", roof=piece, roof_mode="metal-single")
        save(record, root, validate_only=True)
        records.append(record)
    identifiers = [save(record, root, create=True) for record in records]
    return identifiers[0]


def delete(identifier, root=ROOT):
    directory = folder(root) / project_id(identifier)
    if not (directory / "project.json").is_file():
        raise GzError("ROOF_NOT_FOUND", "这个屋顶已不存在", "回首页刷新")
    shutil.rmtree(directory)
