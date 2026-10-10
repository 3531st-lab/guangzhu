"""T22 in the real page against the real backend: the questionnaire reaches the brief, the park view plans phases, and a result shows
its checks before construction."""
import json

from fastapi.testclient import TestClient

from guangzhu import api
from guangzhu.config import API_ORIGIN, API_PORT
from test_t16_dom import browser_app  # noqa: F401


def forward_to(page):
    backend = TestClient(api.app, base_url=f"http://127.0.0.1:{API_PORT}", headers={"origin": API_ORIGIN})

    def forward(route):
        path = route.request.url.split("offline.test", 1)[-1]
        reply = (backend.post(path, content=route.request.post_data, headers={"content-type": "application/json"})
                 if route.request.method == "POST" else backend.get(path))
        route.fulfill(status=reply.status_code, body=reply.content, content_type="application/json")
    return backend, forward


def test_questionnaire_answers_reach_the_brief(browser_app):
    page, errors = browser_app
    _, forward = forward_to(page)
    page.route("**/api/brief", forward)
    page.goto("http://offline.test/#form", wait_until="commit")
    page.wait_for_selector('[data-field="fRoof"]')
    assert page.locator(".grid3 select").count() == 6 and page.locator('.grid3 input[type="number"]').count() == 3
    page.fill('[data-field="text"]', "6 年回本")
    page.select_option('[data-field="fRoof"]', "metal")
    page.fill('[data-field="fKwh"]', "1.5")
    page.select_option('[data-field="fExport"]', "0")
    page.wait_for_function("document.querySelector('#brief-pre').textContent.includes('\"facts\"')")
    brief = page.text_content("#brief-pre")
    data = json.loads(brief.split("```json\n")[1].split("\n```")[0])
    assert data["facts"] == dict(roof_type="metal", monthly_kwh=15000, export_allowed=False) and list(data)[-2:] == ["facts", "run"]
    page.select_option('[data-field="fRoof"]', "")
    page.fill('[data-field="fKwh"]', "")
    page.select_option('[data-field="fExport"]', "")
    page.wait_for_function("!document.querySelector('#brief-pre').textContent.includes('\"facts\"')")
    assert errors == []


def test_owner_words_most_capacity_pick_the_max_plan_unless_picked_by_hand(browser_app):
    page, errors = browser_app
    _, forward = forward_to(page)
    page.route("**/api/brief", forward)
    page.goto("http://offline.test/#form", wait_until="commit")
    page.wait_for_selector('[data-field="prefer"]')
    page.fill('[data-field="text"]', "尽量多装，6 年内回本")
    assert page.input_value('[data-field="prefer"]') == "max_capacity" and "三方案都满足时选：多装" in page.text_content("#recognized")
    page.wait_for_function("document.querySelector('#brief-pre').textContent.includes('\"prefer\":\"max_capacity\"')")
    page.fill('[data-field="text"]', "6 年内回本")
    assert page.input_value('[data-field="prefer"]') == "balanced"
    page.select_option('[data-field="prefer"]', "fast_payback")
    page.fill('[data-field="text"]', "尽量多装，6 年内回本")
    assert page.input_value('[data-field="prefer"]') == "fast_payback" and "最快回本（已选的优先）" in page.text_content("#recognized")
    assert errors == []


def forward_named_parks(page, backend, tmp_path, monkeypatch):
    def forward(route):
        with monkeypatch.context() as isolated:
            isolated.setattr(api, 'ROOT', tmp_path)
            reply = backend.get('/api/parks')
        route.fulfill(status=reply.status_code, body=reply.content, content_type='application/json')
    page.route('**/api/parks', forward)


def test_park_view_sums_the_ticked_buildings_and_splits_phases_by_budget(browser_app, tmp_path, monkeypatch):
    page, errors = browser_app
    backend, forward = forward_to(page)
    page.route("**/api/park", forward)
    forward_named_parks(page, backend, tmp_path, monkeypatch)
    expected = backend.get("/api/park").json()["buildings"]
    page.goto("http://offline.test/#park", wait_until="commit")
    page.get_by_role('link', name='已有设计汇总').click()
    page.wait_for_selector(".park-card")
    assert page.locator(".park-card").count() == len(expected)
    ticked = [b for b in expected if b["default"]]
    assert page.locator(".park-card:not(.off)").count() == len(ticked)
    assert page.text_content(".park-kpis .kpi:first-child b").startswith(str(len(ticked)))
    assert page.locator(".park-card .pill", has_text="二期").count() == 0
    cheapest = min(b["capex_cny"] for b in ticked)
    page.fill('[data-park-field="budget"]', str(cheapest / 1e4))
    page.wait_for_function("document.querySelectorAll('.park-card .pill.warn').length > 0")
    assert page.locator(".park-card .pill.ok", has_text="一期").count() >= 1
    assert "一期栋数" in page.text_content(".park-kpis")
    page.click(f'input[data-park="{ticked[0]["run_id"]}"]')  # the card is redrawn, so address it by its run
    page.wait_for_function(f"document.querySelectorAll('.park-card:not(.off)').length === {len(ticked) - 1}")
    assert not page.is_checked(f'input[data-park="{ticked[0]["run_id"]}"]')
    assert page.get_attribute('a[href="#park"]', "aria-current") == "page" and errors == []


def test_park_ticks_designs_finished_since_the_last_visit_and_keeps_hand_picks(browser_app, tmp_path, monkeypatch):
    page, errors = browser_app
    backend, _ = forward_to(page)
    forward_named_parks(page, backend, tmp_path, monkeypatch)
    first = backend.get("/api/park").json()
    kept, replaced, *others = [b for b in first["buildings"] if b["default"]]
    newer = dict(replaced, run_id="gz-newer-design", ended_at="2099-01-01T00:00:00Z")  # the same roof designed again while the app stayed open
    second = dict(first, buildings=[dict(b, default=b is not replaced and b["default"]) for b in first["buildings"]] + [newer])
    replies = [second, first]
    page.route("**/api/park", lambda route: route.fulfill(json=replies.pop() if len(replies) > 1 else replies[0]))
    page.goto("http://offline.test/#park", wait_until="commit")
    page.get_by_role('link', name='已有设计汇总').click()
    page.wait_for_selector(".park-card")
    page.click(f'input[data-park="{kept["run_id"]}"]')  # left out by hand
    page.wait_for_function(f"!document.querySelector('input[data-park=\"{kept['run_id']}\"]').checked")
    page.evaluate("location.hash = '#records'")
    page.wait_for_selector('a[href="#records"][aria-current="page"]')
    page.locator('.navtabs a[href="#park"]').click()
    page.get_by_role('link', name='已有设计汇总').click()
    page.wait_for_selector('input[data-park="gz-newer-design"]')
    assert page.is_checked('input[data-park="gz-newer-design"]') and not page.is_checked(f'input[data-park="{replaced["run_id"]}"]')
    assert not page.is_checked(f'input[data-park="{kept["run_id"]}"]')
    assert all(page.is_checked(f'input[data-park="{b["run_id"]}"]') for b in others) and errors == []


def test_result_page_lists_the_checks_before_construction(browser_app):
    page, errors = browser_app
    _, forward = forward_to(page)
    page.route("**/api/runs/gz-t11-changzhou-006*", forward)
    page.goto("http://offline.test/#result/t11-changzhou-006?run=gz-t11-changzhou-006", wait_until="commit")
    page.wait_for_selector('[data-result-tab="开工前"]')
    page.click('[data-result-tab="开工前"]')
    assert page.locator(".rulelist.site > div").count() == 9
    assert "并网电压" in page.locator(".rulelist.site").inner_text()
    assert "这次没有填开工前问答" in page.text_content("#result-panel") and page.locator(".rulelist.site .pill", has_text="没填").count() == 9
    assert errors == []
