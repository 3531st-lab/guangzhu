"""Codex review E1: a real, fully verified run ships with the app (data/showcase) and opens without any model key."""
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from guangzhu import api
from guangzhu.config import API_ORIGIN, API_PORT
from test_t16_dom import browser_app  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
RUN = "gz-changzhou-demo-1008-2113"


@pytest.fixture
def installed(tmp_path, monkeypatch):
    shutil.copytree(ROOT / "runs" / RUN, tmp_path / "data/showcase" / RUN)
    (tmp_path / "runs").mkdir()
    monkeypatch.setattr(api, "ROOT", tmp_path)
    return TestClient(api.app, base_url=f"http://127.0.0.1:{API_PORT}", headers={"origin": API_ORIGIN})


def test_codex_e1_the_shipped_run_is_listed_as_a_showcase_and_opens_with_its_result(installed):
    rows = installed.get("/api/runs").json()["runs"]
    assert [(row["run_id"], row["showcase"], row["verification"]["passed"]) for row in rows] == [(RUN, True, True)]
    detail = installed.get(f"/api/runs/{RUN}").json()
    result = detail["result"]
    assert result["run_id"] == RUN and result["selected_version"] == 14 and result["report"]["files"] and detail["timeline"]["nodes"]


def test_on_the_computer_that_made_the_shipped_run_it_is_listed_once(installed, tmp_path):
    shutil.copytree(ROOT / "runs" / RUN, tmp_path / "runs" / RUN)
    rows = installed.get("/api/runs").json()["runs"]
    assert [(row["run_id"], row["showcase"]) for row in rows if row["run_id"] == RUN] == [(RUN, False)]


def test_codex_e1_without_a_key_the_home_page_offers_the_real_case_and_its_replay(browser_app, installed):
    page, errors = browser_app

    def forward(route):
        reply = installed.get(route.request.url.split("offline.test", 1)[-1])
        route.fulfill(status=reply.status_code, body=reply.content, content_type="application/json")
    page.route("**/api/runs**", forward)
    page.route("**/api/setup/status", lambda route: route.fulfill(json={"installation": {"installed": False, "id": "development"},
                                                                       "required": False, "ready": True, "steps": []}))
    page.evaluate("location.hash = '#new'")
    page.reload(wait_until="commit")
    page.wait_for_selector('#kb-state a[href*="run="]')
    assert "没有 key？先看一个真实案例" in page.text_content("#kb-state") and "真实案例" in page.text_content(".recent")
    page.click('#kb-state a[href*="run="]')
    page.wait_for_function(f"location.hash.includes('{RUN}') && document.querySelector('.why-row')")
    assert page.locator(f'.head a[href="#replay/{RUN}"]').count() == 1 and page.locator('[data-action="open-exports"]').count() == 0
    page.click('[data-result-tab="文件"]')
    assert page.locator('[data-action="open-report"]').count() == 1
    page.click(f'.head a[href="#replay/{RUN}"]')
    page.wait_for_function("location.hash.startsWith('#replay/') && document.getElementById('replay-seek')")
    assert errors == []
