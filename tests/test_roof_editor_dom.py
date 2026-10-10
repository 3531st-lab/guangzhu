"""T18 roof editor in a real browser: page requests for roofs, drawings and saving go to the real backend in-process."""
import io
import json
import math
import shutil
from pathlib import Path

import ezdxf
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

from guangzhu import api
from guangzhu.config import API_ORIGIN, API_PORT

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "desktop/web"
FORWARDED = ("/api/roofs", "/api/my-roofs", "/api/drawings", "/api/tilt", "/api/brief", '/api/roof-planes', '/api/parking')


@pytest.fixture
def editor(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "data/demo/projects/changzhou-demo", tmp_path / "data/demo/projects/changzhou-demo")
    for target in ("guangzhu.api.ROOT", "guangzhu.brief.ROOT"):
        monkeypatch.setattr(target, tmp_path)
    monkeypatch.setattr(api, "tilt_hint", lambda payload: dict(available=True, best=round(payload["site"]["lat"]), balanced=12, capacity=10,
                                                               loss_pct=dict(balanced=4.7, capacity=5.8)))
    backend = TestClient(api.app, base_url=f"http://127.0.0.1:{API_PORT}", headers={"origin": API_ORIGIN})
    script = (WEB / "app.js").read_text(encoding="utf-8") + "\nwindow.testApp={state,render};"
    bridge = "export function setAghOrigin() {}\nexport class Bridge {constructor(){this.ready=true;this.models=[];} setAvailable(){} setTheme(){} send(){}}"
    canned = {"/api/runs": {"runs": []}, "/api/status": {"agh": {"connected": False}},
              "/api/setup/status": {"installation": {"installed": False, "id": "development"}, "required": False, "ready": True, "steps": []}}
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport=dict(width=1440, height=900))
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def respond(route):
            request = route.request
            url = request.url.split("offline.test", 1)[-1]
            path = url.split("?", 1)[0]
            if path.startswith(FORWARDED):
                reply = backend.request(request.method, url, content=request.post_data_buffer,
                                        headers={"content-type": request.headers.get("content-type", "application/octet-stream")})
                route.fulfill(status=reply.status_code, body=reply.content, content_type=reply.headers.get("content-type"))
            elif path in canned:
                route.fulfill(json=canned[path])
            elif path == "/app.js":
                route.fulfill(body=script, content_type="text/javascript")
            elif path == "/bridge.js":
                route.fulfill(body=bridge, content_type="text/javascript")
            elif path == "/scene.js":
                route.fulfill(body="export const createScene = () => ({dispose(){}});", content_type="text/javascript")
            elif path.startswith("/vendor/"):
                route.fulfill(body="", content_type="text/javascript")
            else:
                file = WEB / ("index.html" if path == "/" else path.lstrip("/"))
                route.fulfill(path=str(file)) if file.is_file() else route.abort()

        page.route("**/*", respond)
        page.goto("http://offline.test/#roof", wait_until="commit")
        page.wait_for_function("Boolean(window.testApp) && document.querySelector('#re-svg') && document.querySelector('#re-city option[value=\"无锡\"]')")
        yield page, errors, tmp_path
        browser.close()


def click_at(page, x, y, *, pixels=False):
    """Click the canvas at a roof coordinate in metres (or at a drawing pixel before the scale is set)."""
    point = page.evaluate("""([x, y, pixels]) => { const svg = document.getElementById('re-svg'), p = svg.createSVGPoint();
      [p.x, p.y] = [x, pixels ? y : -y]; const q = p.matrixTransform(svg.getScreenCTM()); return [q.x, q.y]; }""", [x, y, pixels])
    page.mouse.click(*point)


def saved(root):
    files = list((root / "data/my-roofs").glob("*/project.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8")), files[0].parent


def test_draw_by_size_with_city_equipment_and_surroundings_then_pick_it_on_the_home_page(editor):
    page, errors, root = editor
    page.select_option("#re-city", "无锡")
    page.wait_for_function("document.getElementById('re-tilt').textContent.includes('本地最佳倾角 32°')")
    assert page.input_value('[data-re="lat"]') == "31.5777"
    page.fill('[data-re-rect="w"]', "80")
    page.fill('[data-re-rect="d"]', "40")
    assert page.text_content("#re-size").startswith("3,200 m²")
    for tool, a, b in (("device", (10, 10), (14, 13)), ("keepout", (30, 20), (50, 22)), ("building", (0, -20), (40, -8)), ("tree", (70, -45), (73, -45))):
        if tool == "tree":
            page.click('[data-re-zoom="-1"]')  # zoom out to reach a tree further south
        page.click(f'[data-re-tool="{tool}"]')
        click_at(page, *a)
        click_at(page, *b)
    assert page.locator(".re-item").count() == 4
    page.fill('[data-item="2"][data-key="height"]', "15")
    page.fill('[data-re="name"]', "无锡某厂 2 号厂房")
    page.fill('[data-re="load"]', "0.6")
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new' && document.querySelector('.rooflist')?.textContent.includes('我的屋顶')")
    project, folder = saved(root)
    assert project["site"]["lat"] == 31.5777 and project["roof"]["load_capacity_kn_m2"] == 0.6
    assert math.isclose(abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(project["roof"]["outline"], project["roof"]["outline"][1:] +
                                                                              project["roof"]["outline"][:1])) / 2), 3200)
    assert project["roof"]["obstacles"][0]["footprint"] and project["roof"]["keepouts"][0]["label"] == "禁区1"
    assert project["roof"]["surroundings"][0]["height_m"] == 15 and project["roof"]["surroundings"][1]["radius_m"] == 3
    row = page.locator(f'[data-roof="{folder.name}"]')
    assert "我画的" in row.text_content() and "2处周边遮挡" in row.text_content()
    row.click()
    page.locator('a[href^="#roof/"]').click()
    page.wait_for_function("document.querySelector('.head h1')?.textContent === '编辑屋顶'")
    assert page.input_value('[data-re="name"]') == "无锡某厂 2 号厂房" and page.locator(".re-item").count() == 4
    page.once("dialog", lambda dialog: dialog.accept())
    page.click('[data-re-act="delete"]')
    page.wait_for_function("location.hash === '#new' && document.querySelector('.rooflist') && !document.querySelector('.rooflist').textContent.includes('我的屋顶')")
    assert not folder.exists() and errors == []


def test_trace_a_pdf_after_setting_its_scale_within_one_percent(editor, tmp_path):
    page, errors, root = editor
    scale, margin = 10, 60  # the drawing: a 60 x 36 m roof with a 20 x 10 m notch at the north-east corner, 10 px per metre
    corners = [(0, 0), (60, 0), (60, 26), (40, 26), (40, 36), (0, 36)]
    image = Image.new("RGB", (60 * scale + 2 * margin, 36 * scale + 2 * margin), "white")
    pixel = lambda x, y: (margin + x * scale, margin + (36 - y) * scale)
    ImageDraw.Draw(image).polygon([pixel(*c) for c in corners], outline="black", width=3)
    image.save(tmp_path / "屋顶图纸.pdf", "PDF")
    page.click('[data-re-mode="2"]')
    page.set_input_files("#re-file", str(tmp_path / "屋顶图纸.pdf"))
    page.wait_for_function("document.querySelector('#re-svg image') && document.getElementById('re-scale').textContent.includes('还没定比例')")
    shown = float(page.get_attribute("#re-svg image", "width")) / image.width
    click_at(page, *[v * shown for v in pixel(0, 0)], pixels=True)
    click_at(page, *[v * shown for v in pixel(60, 0)], pixels=True)
    page.fill('[data-re="distance"]', "60")
    page.click('[data-re-act="calibrate"]')
    page.click('[data-re-act="trace"]')
    for corner in corners:
        click_at(page, *corner)
    page.click('[data-re-act="close"]')
    page.fill('[data-re="name"]', "按 PDF 描的厂房")
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    project, folder = saved(root)
    outline, calibration = project["roof"]["outline"], project["roof"]["underlay"]["calibration"]
    measured = math.dist(calibration["p1_px"], calibration["p2_px"]) / shown / scale
    assert abs(measured - 60) / 60 < 0.01
    area = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(outline, outline[1:] + outline[:1]))) / 2
    assert abs(area - (60 * 36 - 20 * 10)) / 1960 < 0.01 and (folder / "underlay.png").is_file()
    page.evaluate(f"location.hash = '#roof/{folder.name}'")
    page.wait_for_function("document.querySelector('#re-svg image') && document.getElementById('re-panel')?.textContent.includes('比例已定')")
    assert errors == []


def test_point_by_point_outline_and_a_png_drawing_also_save(editor, tmp_path):
    page, errors, root = editor
    page.click('[data-re-mode="1"]')
    page.click('[data-re-act="trace"]')
    for corner in ((0, 0), (50, 0), (50, 20), (30, 20), (30, 40), (0, 40)):
        click_at(page, corner[0] + 0.2, corner[1] - 0.2)  # clicks a little off the corner snap to the 0.5 m grid
    page.click('[data-re-act="close"]')
    assert page.text_content("#re-size").startswith("1,600 m²") and page.locator("[data-vx]").count() == 6
    page.fill('[data-vx="1"]', "52")  # the south-east corner moves 2 m east: a 2 x 20 m triangle more
    assert page.text_content("#re-size").startswith("1,620 m²")
    Image.new("RGB", (800, 500), "white").save(tmp_path / "卫星截图.png")
    page.click('[data-re-mode="2"]')
    page.set_input_files("#re-file", str(tmp_path / "卫星截图.png"))
    page.wait_for_function("document.querySelector('#re-svg image')")
    click_at(page, 100, 400, pixels=True)
    click_at(page, 700, 400, pixels=True)
    page.fill('[data-re="distance"]', "60")
    page.click('[data-re-act="calibrate"]')
    assert "1 米 ≈ 10 像素" in page.text_content("#re-panel")
    page.fill('[data-re="name"]', "描点画的 L 形厂房")
    page.click('[data-re-act="save"]')  # the outline was drawn before this drawing came in: it has to be traced or adopted first
    page.wait_for_function("document.getElementById('notice').textContent.includes('沿用现在的外形')")
    page.click('[data-re-act="adopt"]')
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    project, folder = saved(root)
    assert len(project["roof"]["outline"]) == 6 and project["roof"]["underlay"]["calibration"]["distance_m"] == 60
    assert (folder / "underlay.png").is_file() and errors == []


def test_dxf_outline_is_picked_and_scaled_from_millimetres(editor, tmp_path):
    page, errors, root = editor
    document = ezdxf.new()
    document.header["$INSUNITS"] = 4
    document.modelspace().add_lwpolyline([(1000, 2000), (61000, 2000), (61000, 38000), (1000, 38000)], close=True)
    document.modelspace().add_lwpolyline([(5000, 5000), (9000, 5000), (9000, 8000), (5000, 8000)], close=True)
    document.saveas(tmp_path / "厂房.dxf")
    page.click('[data-re-mode="2"]')
    page.set_input_files("#re-file", str(tmp_path / "厂房.dxf"))
    page.wait_for_selector('[data-cand="1"]')
    assert page.input_value("#re-unit") == "0.001"
    page.click('[data-re-act="save"]')
    page.wait_for_function("document.getElementById('notice').textContent.includes('屋顶外轮廓')")
    page.click('[data-cand="0"]')
    assert page.text_content("#re-size").startswith("2,160 m²")
    page.click('[data-cand="1"]')  # the 4 x 3 m equipment base becomes a keep-out zone
    page.click('[data-re-act="dxf-done"]')
    assert page.locator(".re-item").count() == 1 and page.locator("[data-cand]").count() == 0
    page.fill('[data-re="name"]', "CAD 导入的厂房")
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    project = saved(root)[0]
    assert sorted(map(tuple, project["roof"]["outline"])) == [(0, 0), (0, 36), (60, 0), (60, 36)]
    assert sorted(map(tuple, project["roof"]["keepouts"][0]["polygon"])) == [(4, 3), (4, 6), (8, 3), (8, 6)] and errors == []


def test_wrong_input_keeps_the_drawing_and_says_why(editor):
    page, errors, root = editor
    page.fill('[data-re="lat"]', "70")
    page.fill('[data-re="name"]', "试试")
    page.click('[data-re-act="save"]')
    page.wait_for_function("document.getElementById('notice').textContent.includes('纬度')")
    page.fill('[data-re="lat"]', "31.8")
    page.click('[data-re-tool="building"]')
    click_at(page, 10, 10)
    click_at(page, 20, 20)
    page.click('[data-re-act="save"]')
    page.wait_for_function("document.getElementById('notice').textContent.includes('压在屋顶上')")
    assert page.evaluate("location.hash") == "#roof" and page.text_content("#re-size").startswith("2,160 m²")
    assert page.locator(".re-item").count() == 1 and not (root / "data/my-roofs").exists() and errors == []
