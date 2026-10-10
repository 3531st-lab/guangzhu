"""Codex review E2 and E3 on a real archived run, read through the real backend: every saved change says in Chinese what it did and opens
that version in 3D (removed modules come from its parent), and each of the three options opens its own layout."""
from fastapi.testclient import TestClient

from guangzhu import api
from guangzhu.config import API_ORIGIN, API_PORT
from test_t16_dom import browser_app  # noqa: F401

RUN, PROJECT = "gz-t11-changzhou-006", "t11-changzhou-006"
SCENE = """export const createScene = () => ({dispose(){}, setTheme(){}, setSun(){}, setMode(){}, selectString(){}, resetView(){},
  setData(data) { (window.sceneVersions ??= []).push([data.design.version, data.parent_design?.version ?? null]); }});"""


def test_codex_e2_e3_each_change_and_each_option_opens_its_own_version(browser_app):
    page, errors = browser_app
    backend = TestClient(api.app, base_url=f"http://127.0.0.1:{API_PORT}", headers={"origin": API_ORIGIN})

    def forward(route):
        reply = backend.get(route.request.url.split("offline.test", 1)[-1])
        route.fulfill(status=reply.status_code, body=reply.content, content_type="application/json")
    page.route(f"**/api/runs/{RUN}*", forward)
    page.route("**/scene.js", lambda route: route.fulfill(body=SCENE, content_type="text/javascript"))
    page.goto(f"http://offline.test/#result/{PROJECT}?run={RUN}", wait_until="commit")
    page.reload(wait_until="commit")  # loads the app again with the recording scene
    page.wait_for_selector(".why-row")
    rows = page.locator(".why-row")
    assert rows.count() == 12 and page.evaluate("window.sceneVersions.at(-1)") == [12, 11]
    change = page.locator('.why-row[data-version="2"]')  # v1 → v2 removed the modules shaded beyond the limit
    text = change.inner_text()
    assert "（S01）" in text and "S01（" not in text and "组件变化 -14 块" in text and "装机变化 -7.7 kW" in text
    assert "基准年发电变化 -7,455 kWh" in text and "回本变化 -0.03 年" in text
    change.click()
    page.wait_for_function("window.sceneVersions.at(-1)[0] === 2")
    assert page.evaluate("window.sceneVersions.at(-1)") == [2, 1]
    assert page.get_attribute('.why-row[data-version="2"]', "aria-pressed") == "true" and "v2" in page.text_content(".head p")
    page.click('.why-row[data-version="5"]')  # v5 was never analysed: rule names learnt from other versions still explain every change
    page.wait_for_function("window.sceneVersions.at(-1)[0] === 5")
    assert "全部组件接入组串（E08）" in page.text_content('.why-row[data-version="6"]')
    page.click('[data-result-tab="三方案"]')
    assert "v5 不在三方案对比里" in page.text_content("#result-panel")
    page.click('[data-result-tab="结论"]')
    page.click('.why-row[data-version="12"]')
    page.wait_for_function("window.sceneVersions.at(-1)[0] === 12")
    page.click('[data-result-tab="三方案"]')
    options = page.locator(".pick-option")
    assert options.count() == 3 and "回本余" in page.text_content(".compare-table")
    page.click('.pick-option[data-version="9"]')
    page.wait_for_function("window.sceneVersions.at(-1)[0] === 9")
    assert page.evaluate("window.sceneVersions.at(-1)") == [9, 8]
    assert page.get_attribute('.pick-option[data-version="9"]', "aria-pressed") == "true"
    assert "年发电 万kWh" in page.text_content(".compare-table thead") and "遮挡 %" in page.text_content(".compare-table thead")
    assert errors == []
