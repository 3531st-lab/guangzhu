"""T18 backend: the user's own roofs (save, edit, delete) and drawing import (image, PDF, DXF)."""
import io
import json
import math
import os
import shutil
import time
from pathlib import Path

import ezdxf
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from guangzhu import api, myroofs, templates
from guangzhu.config import API_ORIGIN, API_PORT
from guangzhu.models import GzError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def root(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "data/demo/projects", tmp_path / "data/demo/projects")
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr("guangzhu.brief.ROOT", tmp_path)
    monkeypatch.setattr("guangzhu.mcp_actions.ROOT", tmp_path)
    monkeypatch.setattr("guangzhu.project.PROJECTS_DIR", tmp_path / "projects")
    return tmp_path


def client():
    return TestClient(api.app, base_url=f"http://127.0.0.1:{API_PORT}", headers={"origin": API_ORIGIN})


def roof(**changes):
    payload = dict(name="无锡某厂 2 号厂房", site=dict(lat=31.5777, lon=120.2953), underlay=None,
                   roof=dict(outline=[[0, 0], [80, 0], [80, 40], [0, 40]], height_m=12, parapet_height_m=0.8, load_capacity_kn_m2=0.6,
                             obstacles=[dict(id="dev-1", label="风机", kind="prism", height_m=2, footprint=[[10, 10], [14, 10], [14, 13], [10, 13]])],
                             keepouts=[dict(id="zone-1", label="天窗", polygon=[[30, 20], [50, 20], [50, 22], [30, 22]])],
                             surroundings=[dict(id="bldg-1", label="南边办公楼", kind="prism", height_m=15, footprint=[[0, -30], [40, -30], [40, -10], [0, -10]]),
                                           dict(id="tree-1", label="香樟", kind="cylinder", height_m=6, center=[70, -6], radius_m=3)]))
    for key, value in changes.items():
        target, field = (payload["roof"], key[5:]) if key.startswith("roof_") else (payload, key)
        target[field] = value
    return payload


def drawing_png(scale=10, margin=50):
    """The demo-style 60 x 36 m roof drawn at `scale` px per metre, north up."""
    image = Image.new("RGB", (60 * scale + 2 * margin, 36 * scale + 2 * margin), "white")
    ImageDraw.Draw(image).rectangle([margin, margin, margin + 60 * scale, margin + 36 * scale], outline="black", width=3)
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue(), image


def test_saved_roof_is_a_template_listed_as_mine_and_usable_for_a_design(root):
    reply = client().post("/api/my-roofs", json=roof())
    assert reply.status_code == 200, reply.json()
    identifier = reply.json()["id"]
    saved = json.loads((root / "data/my-roofs" / identifier / "project.json").read_text(encoding="utf-8"))
    assert {k: saved["site"][k] for k in ("lat", "lon", "timezone")} == dict(lat=31.5777, lon=120.2953, timezone="Asia/Shanghai")
    assert saved["requirements"]["text"] == "" and not any(saved["requirements"]["structured"].values()) and saved["designs"] == []
    assert [len(saved["roof"][k]) for k in ("obstacles", "keepouts", "surroundings")] == [1, 1, 2]
    assert "江苏以外" in saved["economics"]["assumptions_note"] and saved["roof"]["underlay"] is None
    rows = {row["id"]: row for row in client().get("/api/roofs").json()["roofs"]}
    assert rows[identifier]["collection"] == "mine" and rows[identifier]["area_m2"] == 3200
    assert rows["changzhou-demo"]["collection"] == "demo"
    assert templates.resolve(identifier, root=root).parent.name == identifier
    assert identifier not in templates.catalog(all=True, root=root, mine=False)
    brief = client().post("/api/brief", json=dict(id="from-my-roof", template=identifier, text="6年回本", max_rounds=3,
        reviewer_model="agnes-3.0-flash", structured={}, economics={}, compare=True, review=True, export=True))
    assert brief.status_code == 200 and identifier in brief.json()["brief"], brief.json()
    from guangzhu import mcp_actions
    created = mcp_actions.ACTIONS["gz_new_project"]("design-on-my-roof", identifier)
    assert created["created"] and created["roof_area_m2"] == 3200 and created["obstacle_count"] == 1
    layout = mcp_actions.ACTIONS["gz_generate_layout"]("design-on-my-roof", {})
    assert layout["modules"] > 100, layout
    edited = client().post("/api/my-roofs", json=roof(id=identifier, name="改过名字"))
    assert edited.json()["id"] == identifier
    assert json.loads((root / "data/my-roofs" / identifier / "project.json").read_text(encoding="utf-8"))["name"] == "改过名字"
    assert client().post(f"/api/my-roofs/{identifier}/delete").status_code == 200
    assert not (root / "data/my-roofs" / identifier).exists()
    assert "未能" not in json.dumps(client().post(f"/api/my-roofs/{identifier}/delete").json(), ensure_ascii=False)


def test_a_project_is_created_with_the_module_chosen_in_the_conditions(root):
    """A park's shared conditions pick a module; creating the project with it broke once when the brief check grew an argument."""
    from guangzhu import mcp_actions
    created = mcp_actions.ACTIONS["gz_new_project"]("with-module", "changzhou-demo", None, dict(module_id="trina-tsm-605neg19rc20"))
    assert created["created"]
    saved = json.loads((root / "projects/with-module/project.json").read_text(encoding="utf-8"))
    assert saved["equipment"]["module_id"] == "trina-tsm-605neg19rc20"
    with pytest.raises(GzError) as error:
        mcp_actions.ACTIONS["gz_new_project"]("with-unknown-module", "changzhou-demo", None, dict(module_id="no-such-module"))
    assert error.value.error_code == "EQUIPMENT_NOT_FOUND"


def test_a_drawn_roof_runs_the_whole_design_calculation_offline(root):
    """Acceptance 3 without a model key: the agent's own tools on an editor roof (demo weather is cached for this site)."""
    from guangzhu import analysis, mcp_actions
    identifier = client().post("/api/my-roofs", json=roof(site=dict(lat=31.81, lon=119.97))).json()["id"]
    mcp_actions.ACTIONS["gz_new_project"]("offline-on-my-roof", identifier)
    version = mcp_actions.ACTIONS["gz_generate_layout"]("offline-on-my-roof", {})["version"]
    summary = analysis.analyze("offline-on-my-roof", version, offline=True)
    assert summary["ok"] and summary["yield_kwh"]["p50"] > 0 and summary["modules"] > 100
    shading = json.loads((root / f"projects/offline-on-my-roof/analysis/v{version}/shading.json").read_text(encoding="utf-8"))
    assert shading["summary"]["source_loss_pct"]["surroundings"] > 0  # the office block and tree south of the roof cast shadows on it


@pytest.mark.parametrize("changes,reason", [
    (dict(roof_outline=[[0, 0], [10, 10], [10, 0], [0, 10]]), "不能自相交"),
    (dict(site=dict(lat=70, lon=120)), "纬度"),
    (dict(name=" "), "起个名字"),
    (dict(roof_height_m=None), "高度"),
    (dict(roof_outline=[[0, 0], [3, 0], [3, 3], [0, 3]], roof_obstacles=[], roof_keepouts=[], roof_surroundings=[]), "不像真实厂房"),
    (dict(roof_surroundings=[dict(id="bldg-1", label="压着的楼", kind="prism", height_m=9, footprint=[[5, 5], [9, 5], [9, 9], [5, 9]])]), "压在屋顶上"),
    (dict(roof_obstacles=[dict(id="tree-1", label="重名", kind="prism", height_m=1, footprint=[[1, 1], [2, 1], [2, 2], [1, 2]])]), "编号重复"),
])
def test_wrong_input_gets_a_chinese_reason_and_writes_nothing(root, changes, reason):
    reply = client().post("/api/my-roofs", json=roof(**changes))
    assert reply.status_code == 422 and reason in reply.json()["errors"][0], reply.json()
    assert not (root / "data/my-roofs").exists() or not any((root / "data/my-roofs").glob("*/project.json"))


def test_only_the_desktop_page_may_save_or_delete(root):
    bare = TestClient(api.app, base_url=f"http://127.0.0.1:{API_PORT}")
    assert bare.post("/api/my-roofs", json=roof()).status_code == 403
    assert bare.post("/api/drawings?name=a.png", content=drawing_png()[0]).status_code == 403
    assert bare.post("/api/my-roofs/my-x/delete", headers={"origin": "https://example.com"}).status_code == 403


def test_image_and_pdf_become_traceable_pngs(root):
    png, image = drawing_png()
    uploads = root / "data/my-roofs/.uploads"
    uploads.mkdir(parents=True)
    (uploads / ("a" * 32 + ".png")).write_bytes(b"never saved")
    os.utime(uploads / ("a" * 32 + ".png"), (time.time() - 2 * 86400,) * 2)
    (uploads / ("b" * 32 + ".png")).write_bytes(b"imported a minute ago")
    reply = client().post("/api/drawings?name=屋顶.png", content=png).json()
    assert not (uploads / ("a" * 32 + ".png")).exists() and (uploads / ("b" * 32 + ".png")).exists()
    assert reply["kind"] == "image" and (reply["width"], reply["height"], reply["pages"]) == image.size + (1,)
    assert client().get("/api/drawings/" + reply["upload"]).content[:8] == b"\x89PNG\r\n\x1a\n"
    pdf = io.BytesIO()
    image.save(pdf, "PDF", save_all=True, append_images=[image.rotate(90, expand=True)])
    second = client().post("/api/drawings?name=图纸.PDF&page=2", content=pdf.getvalue()).json()
    assert second["pages"] == 2 and max(second["width"], second["height"]) == 2400 and second["height"] > second["width"]
    out_of_range = client().post("/api/drawings?name=图纸.pdf&page=3", content=pdf.getvalue())
    assert out_of_range.status_code == 422 and "只有 2 页" in out_of_range.json()["errors"][0]
    huge = Image.new("RGB", (5000, 1000), "white")
    stream = io.BytesIO()
    huge.save(stream, "JPEG")
    assert client().post("/api/drawings?name=scan.jpg", content=stream.getvalue()).json()["width"] == 3000


@pytest.mark.parametrize("name,content,reason", [("roof.docx", b"PK", "只能导入"), ("roof.pdf", b"%PDF-1.4 broken", "打不开"),
                                                  ("roof.png", b"not an image", "打不开")])
def test_unusable_drawings_are_refused_with_a_reason(root, name, content, reason):
    reply = client().post("/api/drawings?name=" + name, content=content)
    assert reply.status_code == 422 and reason in reply.json()["errors"][0]


def test_dxf_lists_closed_outlines_largest_first_with_units(root):
    document = ezdxf.new()
    document.header["$INSUNITS"] = 4
    space = document.modelspace()
    space.add_lwpolyline([(0, 0), (60000, 0), (60000, 36000), (0, 36000)], close=True, dxfattribs=dict(layer="屋面"))
    space.add_lwpolyline([(5000, 5000), (9000, 5000), (9000, 8000), (5000, 8000), (5000, 5000)])
    space.add_lwpolyline([(0, 0), (100, 100), (200, 0)])
    space.add_line((0, 0), (1, 1))
    stream = io.StringIO()
    document.write(stream)
    reply = client().post("/api/drawings?name=厂房.dxf", content=stream.getvalue().encode("utf-8")).json()
    assert reply["kind"] == "dxf" and reply["scale"] == 0.001
    assert [o["area"] for o in reply["outlines"]] == [60000 * 36000, 4000 * 3000] and reply["outlines"][0]["layer"] == "屋面"
    empty = ezdxf.new()
    empty.modelspace().add_line((0, 0), (5, 5))
    stream = io.StringIO()
    empty.write(stream)
    refused = client().post("/api/drawings?name=空.dxf", content=stream.getvalue().encode("utf-8"))
    assert refused.status_code == 422 and "闭合的多段线" in refused.json()["errors"][0]


def test_traced_underlay_is_saved_and_copied_into_a_new_design_project(root, monkeypatch):
    token = client().post("/api/drawings?name=屋顶.png", content=drawing_png()[0]).json()["upload"]
    calibration = dict(p1_px=[50, 410], p2_px=[650, 410], distance_m=60)
    identifier = client().post("/api/my-roofs", json=roof(underlay=dict(upload=token, calibration=calibration),
        roof_outline=[[0, 0], [60, 0], [60, 36], [0, 36]], roof_obstacles=[], roof_keepouts=[], roof_surroundings=[])).json()["id"]
    folder = root / "data/my-roofs" / identifier
    assert (folder / "underlay.png").read_bytes()[:4] == b"\x89PNG"
    assert client().get(f"/api/my-roofs/{identifier}/underlay").status_code == 200
    kept = client().post("/api/my-roofs", json=roof(id=identifier, underlay=dict(upload="", calibration=calibration),
        roof_outline=[[0, 0], [60, 0], [60, 36], [0, 36]], roof_obstacles=[], roof_keepouts=[], roof_surroundings=[]))
    assert kept.status_code == 200 and (folder / "underlay.png").is_file()
    from guangzhu import project
    monkeypatch.setattr(project, "PROJECTS_DIR", root / "projects")
    created = project.init(folder, "design-on-my-roof")
    assert created.roof.underlay.image == "underlay/underlay.png" and (root / "projects/design-on-my-roof/underlay/underlay.png").is_file()
    client().post("/api/my-roofs", json=roof(id=identifier, roof_obstacles=[], roof_keepouts=[], roof_surroundings=[]))
    assert not (folder / "underlay.png").exists()
    with pytest.raises(GzError, match="底图"):
        myroofs.save(roof(id=identifier, underlay=dict(upload="", calibration=calibration)), root)


def test_codex_r10_a_roof_load_counts_as_verified_only_when_ticked_and_new_roofs_never_share_an_id(root):
    plain = client().post("/api/my-roofs", json=roof()).json()["id"]
    ticked = client().post("/api/my-roofs", json=roof(name="核定过的厂房", roof_load_verified=True)).json()["id"]
    assert plain != ticked
    stored = {key: json.loads((root / "data/my-roofs" / key / "project.json").read_text(encoding="utf-8"))["roof"] for key in (plain, ticked)}
    assert "load_verified" not in stored[plain] and stored[ticked]["load_verified"] is True
    listed = {row["id"]: row for row in client().get("/api/roofs").json()["roofs"]}
    assert listed[ticked]["geometry"]["load_verified"] is True and not listed[plain]["geometry"].get("load_verified")


SAMPLE = [[0, 0], [60, 0], [60, 30], [48, 30], [48, 36], [0, 36], [0, 26], [8, 26], [8, 10], [0, 10]]  # Codex review R12: 1960 m²


def turned(points, degrees):
    a = math.radians(degrees)
    return [[x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)] for x, y in points]


@pytest.mark.parametrize("turn", [0, 17])
def test_codex_r12_the_notched_sample_keeps_its_shape_through_layout_and_dxf_export(root, tmp_path, turn):
    from shapely.geometry import Polygon
    from guangzhu import analysis, mcp_actions
    from guangzhu.report.deliverables import write_deliverables
    outline, skylight = turned(SAMPLE, turn), turned([[20, 14], [30, 14], [30, 20], [20, 20]], turn)
    identifier = client().post("/api/my-roofs", json=roof(site=dict(lat=31.81, lon=119.97), roof_outline=outline, roof_obstacles=[],
        roof_surroundings=[], roof_keepouts=[dict(id="zone-1", label="天窗", polygon=skylight)])).json()["id"]
    stored = json.loads((root / "data/my-roofs" / identifier / "project.json").read_text(encoding="utf-8"))["roof"]["outline"]
    assert len(stored) == 10 and abs(Polygon(stored).area - 1960) < 0.01 and max(map(math.dist, stored, outline)) < 1e-3
    name = f"codex-sample-{turn}"
    mcp_actions.ACTIONS["gz_new_project"](name, identifier)
    version = mcp_actions.ACTIONS["gz_generate_layout"](name, {})["version"]
    assert analysis.analyze(name, version, offline=True)["ok"]
    design = json.loads((root / f"projects/{name}/designs/v{version}.json").read_text(encoding="utf-8"))
    panels = [Polygon([corner[:2] for corner in module["corners"]]) for module in design["modules"]]
    shape, zone = Polygon(outline).buffer(1e-6), Polygon(skylight)
    assert len(panels) > 100 and all(shape.contains(panel) for panel in panels)  # never in the two notches
    assert all(panel.intersection(zone).area < 1e-9 for panel in panels)
    write_deliverables(name, version, tmp_path)
    exported = [entity for entity in ezdxf.readfile(tmp_path / f"layout-v{version}.dxf").modelspace().query("LWPOLYLINE") if entity.dxf.layer == "ROOF"]
    assert len(exported) == 1 and max(map(math.dist, [p[:2] for p in exported[0].get_points()], outline)) < 1e-6


def dxf_bytes(build):
    document = ezdxf.new()
    build(document.modelspace())
    stream = io.StringIO()
    document.write(stream)
    return stream.getvalue().encode("utf-8")


def test_codex_r08_arcs_in_a_dxf_outline_follow_the_arc_and_curves_that_cannot_be_read_are_refused(root):
    arc = dxf_bytes(lambda space: space.add_lwpolyline([(0, 0, 0), (20, 0, 0), (20, 20, 1), (0, 20, 0)], format="xyb", close=True))
    outline = client().post("/api/drawings?name=半圆.dxf", content=arc).json()["outlines"][0]
    assert abs(outline["area"] - (400 + math.pi * 50)) / 557.08 < 0.001 and max(p[1] for p in outline["points"]) > 29.99
    square = dxf_bytes(lambda space: space.add_lwpolyline([(0, 0), (20, 0), (20, 20), (0, 20)], close=True))
    assert client().post("/api/drawings?name=方.dxf", content=square).json()["outlines"][0]["area"] == 400
    spline = dxf_bytes(lambda space: space.add_spline([(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)]))
    refused = client().post("/api/drawings?name=样条.dxf", content=spline)
    assert refused.status_code == 422 and "BOUNDARY" in json.dumps(refused.json(), ensure_ascii=False)
