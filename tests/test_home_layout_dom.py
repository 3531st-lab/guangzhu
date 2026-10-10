"""Codex review R04: on short laptop windows the home page keeps roof rows clickable and 下一步 reachable, before and after the keys are set."""
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

from guangzhu import api
from guangzhu.config import API_ORIGIN, API_PORT

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "desktop/web"
FORWARDED = ("/api/roofs", "/api/my-roofs", "/api/drawings", "/api/tilt", "/api/brief")
MODELS = "[{id:'deepseek-v4-pro',route:'deepseek',name:'DeepSeek V4 Pro',label:'DeepSeek V4 Pro'},{id:'agnes-3.0-flash',route:'agnes',name:'Agnes 3.0 Flash',label:'Agnes 3.0 Flash'}]"
RECORDS = [dict(run_id=f"gz-run-{i}", project_id=f"changzhou-demo-{i}", template="changzhou-demo", created_at=f"2026-10-0{1 + i % 5}T10:00:00+08:00",
                status="completed", verification=dict(passed=True)) for i in range(8)]


@pytest.fixture
def home(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "data/demo/projects", tmp_path / "data/demo/projects")
    shutil.copytree(ROOT / "data/roofs", tmp_path / "data/roofs")
    for target in ("guangzhu.api.ROOT", "guangzhu.brief.ROOT"):
        monkeypatch.setattr(target, tmp_path)
    backend = TestClient(api.app, base_url=f"http://127.0.0.1:{API_PORT}", headers={"origin": API_ORIGIN})
    for name in ("无锡 2 号厂房", "常州仓库"):
        backend.post("/api/my-roofs", json=dict(name=name, site=dict(lat=31.58, lon=120.3), underlay=None, roof=dict(
            outline=[[0, 0], [60, 0], [60, 30], [48, 30], [48, 36], [0, 36], [0, 26], [8, 26], [8, 10], [0, 10]], height_m=12,
            parapet_height_m=0.8, load_capacity_kn_m2=0.5, obstacles=[], keepouts=[], surroundings=[]))).raise_for_status()
    script = (WEB / "app.js").read_text(encoding="utf-8") + "\nwindow.testApp={state,bridge,setup,render,updateKeyBar};"
    bridge = "export function setAghOrigin() {}\nexport class Bridge {constructor(){this.ready=true;this.models=[];} setAvailable(){} setTheme(){} send(){}}"
    canned = {"/api/runs": {"runs": RECORDS}, "/api/status": {"agh": {"connected": True, "url": "http://127.0.0.1:4178"}},
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
            elif path.startswith("/api/projects/") and path.endswith("/exists"):
                route.fulfill(json={"exists": False})
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
        page.goto("http://offline.test/#new", wait_until="commit")
        page.wait_for_function("Boolean(window.testApp) && document.querySelectorAll('.roofrow').length > 5")
        yield page, errors
        browser.close()


def keys_ready(page):
    page.evaluate(f"testApp.bridge.models = {MODELS}; testApp.state.designModel = testApp.bridge.models[0]; "
                  "testApp.state.reviewModel = testApp.bridge.models[1]; testApp.render()")
    page.wait_for_selector(".roofrow")


def on_screen(page, selector, height):
    box = page.locator(selector).first.bounding_box()
    return box is not None and box["y"] >= 0 and box["y"] + box["height"] <= height


@pytest.mark.parametrize("ready", [False, True], ids=["first-run", "keys-saved"])
@pytest.mark.parametrize("width,height", [(1280, 680), (1280, 720), (1366, 768), (1536, 834), (1100, 650)])
def test_codex_r04_roof_rows_and_next_are_usable_by_mouse_on_short_windows(home, width, height, ready):
    page, errors = home
    if ready:
        keys_ready(page)
    page.set_viewport_size(dict(width=width, height=height))
    assert on_screen(page, ".roofrow", height) and on_screen(page, ".next", height)
    page.mouse.move(width * 0.3, height - 60)
    page.mouse.wheel(0, 4000)
    page.wait_for_timeout(200)
    rows = page.locator(".roofrow")
    last = rows.nth(rows.count() - 1)
    box = last.bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= height
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_function("document.querySelectorAll('.roofrow')[document.querySelectorAll('.roofrow').length - 1].getAttribute('aria-pressed') === 'true'")
    name = page.locator(".roofrow").nth(rows.count() - 1).locator("h4").inner_text().split("\n")[0].strip()
    assert page.locator(".preview h3").inner_text() == name
    assert on_screen(page, ".next", height)
    next_box = page.locator(".next").bounding_box()
    page.mouse.click(next_box["x"] + next_box["width"] / 2, next_box["y"] + next_box["height"] / 2)
    page.wait_for_function("location.hash === '#form' && document.querySelector('[data-field=\"text\"]')")
    page.locator('a[href="#new"].btn').first.click()
    page.wait_for_selector(".roofrow")
    mine = page.locator('.roofrow:has-text("常州仓库")')
    mine.click()
    page.locator('.preview a[href^="#roof/"]').click()
    page.wait_for_selector("#re-svg")
    for selector in ('[data-re-act="save"]', '.re-actions a[href="#new"]', "#re-svg"):
        assert on_screen(page, selector, height), selector
    page.locator('.re-actions a[href="#new"]').click()
    page.wait_for_selector(".roofrow")
    assert errors == []


def test_codex_r04_the_key_bar_folds_to_one_line_once_a_model_works_and_opens_on_request(home):
    page, errors = home
    page.set_viewport_size(dict(width=1280, height=680))
    assert page.locator(".keybar.slim").count() == 0 and page.locator("input[data-key]").count() == 3
    page.locator('input[data-key="agnes"]').fill("half-typed")
    page.evaluate(f"testApp.bridge.models = {MODELS}; testApp.updateKeyBar()")
    assert page.locator("input[data-key]").count() == 3 and page.locator('input[data-key="agnes"]').input_value() == "half-typed"
    page.locator('input[data-key="agnes"]').fill("")
    page.locator("h1").click()
    page.evaluate("testApp.updateKeyBar()")
    bar = page.locator(".keybar.slim")
    assert bar.count() == 1 and bar.bounding_box()["height"] < 70 and "已可用" in bar.inner_text()
    page.locator('[data-action="keys-open"]').click()
    assert page.locator("input[data-key]").count() == 3
    page.evaluate("testApp.updateKeyBar()")
    assert page.locator(".keybar.slim").count() == 0
    page.locator('[data-action="keys-close"]').click()
    assert page.locator(".keybar.slim").count() == 1
    assert errors == []
