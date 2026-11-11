"""Unit and API integration tests for PVsyst 7.x 8760h engine, official live weather, and satellite map AI design."""
from __future__ import annotations

from typing import Any
from fastapi.testclient import TestClient

from guangzhu.api import app
from guangzhu.live_weather import fetch_live_weather
from guangzhu.pvsyst_engine import simulate_pvsyst
from guangzhu.satmap_design import (
    ai_recognize_satellite_roof,
    export_satmap_dxf,
    list_satellite_presets,
    run_satmap_design,
    search_satellite_location,
)


def test_live_weather_offline_and_cache_structure():
    wx = fetch_live_weather(36.858844, 118.778089, dc_kw=417.6, tilt_deg=6.0, azimuth_deg=180.0, offline=True)
    assert wx["ok"] is True
    assert wx["provenance"]["mode"] in {
        "offline_tmy_fallback",
        "offline_tmy_climatology",
        "cached_official_api",
        "live_official_api",
    }
    assert "CMA" in wx["provenance"]["source"] or "Open-Meteo" in wx["provenance"]["source"]
    cur = wx["current"]
    assert -30.0 <= cur["temp_c"] <= 55.0
    assert 0.0 <= cur["ghi_wm2"] <= 1400.0
    assert 0.0 <= cur["poa_wm2"] <= 1500.0
    assert len(wx["hourly_48h"]) == 48

    # Also test live/cached fetch path (gracefully falls back if network unavailable)
    wx_live = fetch_live_weather(32.4562, 119.9231, dc_kw=290.0, tilt_deg=6.0, azimuth_deg=180.0, offline=False)
    assert wx_live["ok"] is True
    assert wx_live["provenance"]["mode"] in {
        "live_official_api",
        "cached_official_api",
        "offline_tmy_fallback",
    }


def test_pvsyst_8760h_engine_16_stages_and_monthly_balances():
    res = simulate_pvsyst(
        32.4562,
        119.9231,
        dc_kw=417.6,
        ac_kw=330.0,
        tilt_deg=6.0,
        azimuth_deg=180.0,
        albedo=0.22,
        bifaciality=0.80,
        soiling_pct=2.0,
        offline=True,
    )
    assert res["ok"] is True
    summary = res["summary"]
    assert 70.0 <= summary["pr_pct"] <= 95.0
    assert summary["e_grid_kwh"] > 350000
    assert summary["specific_yield_kwh_kwp"] > 850

    waterfall = res["waterfall"]
    assert len(waterfall) == 16
    stage_ids = [s["id"] for s in waterfall]
    assert stage_ids[0] == "glob_hor"
    assert "glob_inc" in stage_ids
    assert "glob_eff" in stage_ids
    assert "e_array" in stage_ids
    assert stage_ids[-1] == "e_grid"

    monthly = res["monthly_balances"]
    assert len(monthly) == 12
    sum_e_grid = sum(m["e_grid"] for m in monthly)
    assert abs(sum_e_grid - summary["e_grid_kwh"]) / summary["e_grid_kwh"] < 0.01

    opt = res["optimization_matrix"]
    assert len(opt["tilts"]) == 9
    assert len(opt["azimuths"]) == 9
    assert len(opt["grid_kwh_kwp"]) == 9
    assert opt["optimal_kwh_kwp"] >= summary["specific_yield_kwh_kwp"] * 0.95

    prob = res["probabilities"]
    assert prob["p50_kwh"] > prob["p75_kwh"] > prob["p90_kwh"] > prob["p99_kwh"]


def test_satmap_design_mppt_allocation_and_four_cad_drawings():
    presets = list_satellite_presets()
    assert len(presets) >= 4
    loc = search_satellite_location("36.858844, 118.778089", offline=True)
    assert loc["ok"] is True
    assert abs(loc["results"][0]["lat"] - 36.858844) < 1e-4

    ai_roof = ai_recognize_satellite_roof(
        {"lat": 32.4568, "lon": 119.9182, "roof_type": "double_slope", "slope_deg": 6.0}
    )
    assert ai_roof["ok"] is True
    assert len(ai_roof["roof_polygon_m"]) == 4
    assert len(ai_roof["obstacles"]) >= 2

    design = run_satmap_design(
        {
            "lat": 32.4568,
            "lon": 119.9182,
            "roof_polygon_m": ai_roof["roof_polygon_m"],
            "obstacles": ai_roof["obstacles"],
            "roof_type": "double_slope",
            "slope_deg": 6.0,
            "offline": True,
        }
    )
    assert design["ok"] is True
    assert design["summary"]["module_count"] > 200
    assert design["summary"]["south_count"] > 0
    assert design["summary"]["north_count"] > 0
    assert len(design["electrical"]["mppt_table"]) >= 9
    assert len(design["strings"]) == design["summary"]["string_count"]
    w_opt = design["wiring_optimization"]
    assert w_opt["dc_cable_saved_pct"] > 5.0
    assert w_opt["keepout_crossings"] == 0
    assert w_opt["cu_cable_model"].startswith("ZR-YJV22")
    assert w_opt["al_cable_model"].startswith("YJLH22")
    assert w_opt["cu_ac_drop_pct"] <= 2.0
    assert w_opt["al_ac_drop_pct"] <= 2.0
    assert w_opt["al_cost_saving_pct"] > 45.0
    assert set(design["cad_drawings"].keys()) == {"layout", "string", "grounding", "bracket"}
    for sheet_key, svg in design["cad_drawings"].items():
        assert svg.startswith("<svg") and "</svg>" in svg
        dxf_bytes = export_satmap_dxf(design, drawing_type=sheet_key)
        dxf_text = dxf_bytes.decode("utf-8")
        assert "SECTION" in dxf_text and "EOF" in dxf_text


def test_satmap_and_pvsyst_fastapi_routes():
    client = TestClient(app)
    r_presets = client.get("/api/satmap/presets")
    assert r_presets.status_code == 200
    presets_list = r_presets.json()["presets"]
    assert len(presets_list) >= 11
    preset_keys = {p["key"] for p in presets_list}
    for tz_key in (
        "taizhou-cmc",
        "taizhou-xiangtai-warehouse",
        "taizhou-jielouwei-bipv",
        "taizhou-shenyuan-alloy",
        "taizhou-municipal-admin",
        "taizhou-jingjiang-shipbuild",
        "taizhou-taixing-chem",
        "taizhou-jiangyan-equip",
    ):
        assert tz_key in preset_keys
    for preset in presets_list:
        assert "鹧鸪云" not in preset.get("name", "")
        assert "PVLANE" not in preset.get("name", "")

    r_exp = client.get("/api/satmap/experiments")
    assert r_exp.status_code == 200
    exp_json = r_exp.json()
    assert exp_json["ok"] is True
    assert exp_json["exp1_taizhou_8_real_projects"]["total_projects"] == 8
    assert exp_json["exp1_taizhou_8_real_projects"]["industrial_7_mape_chain_b_pct"] < 1.0
    assert exp_json["exp1_taizhou_8_real_projects"]["mape_chain_b_pct"] < 3.0

    r_wx = client.get("/api/pvsyst/live-weather?lat=32.4562&lon=119.9231&dc_kw=250&offline=true")
    assert r_wx.status_code == 200
    wx_data = r_wx.json()
    assert wx_data["ok"] is True
    assert "current" in wx_data

    r_sim = client.post(
        "/api/pvsyst/simulate",
        json={
            "lat": 32.4562,
            "lon": 119.9231,
            "dc_kw": 300.0,
            "ac_kw": 250.0,
            "tilt_deg": 12.0,
            "azimuth_deg": 180.0,
            "offline": True,
        },
    )
    assert r_sim.status_code == 200
    sim_data = r_sim.json()
    assert sim_data["ok"] is True
    assert len(sim_data["waterfall"]) == 16

    r_design = client.post(
        "/api/satmap/design",
        json={
            "lat": 32.4562,
            "lon": 119.9231,
            "roof_type": "double_slope",
            "slope_deg": 6.0,
            "offline": True,
        },
    )
    assert r_design.status_code == 200
    d_json = r_design.json()
    assert d_json["ok"] is True
    assert d_json["summary"]["module_count"] > 200
    assert "layout" in d_json["cad_drawings"]

    # Verify /api/satmap/ai-recognize-roof route alias works and uses honest calibration step metadata
    r_ai = client.post(
        "/api/satmap/ai-recognize-roof",
        json={"lat": 32.4568, "lon": 119.9182, "roof_type": "double_slope", "slope_deg": 6.0},
    )
    assert r_ai.status_code == 200
    ai_json = r_ai.json()
    assert ai_json["ok"] is True
    assert all("confidence_pct" not in step for step in ai_json["ai_steps"])

    # Verify /api/satmap/save-project preserves C-shaped 8-vertex concave roof and keepout
    import shutil
    from guangzhu.config import PROJECTS_DIR
    from guangzhu import project as storage

    c_shape_outline = [
        [-42.0, -24.0],
        [42.0, -24.0],
        [42.0, -10.0],
        [-26.0, -10.0],
        [-26.0, 10.0],
        [24.0, 10.0],
        [24.0, 24.0],
        [-42.0, 24.0],
    ]
    c_keepout = [
        {"id": "kp-c1", "name": "南翼天窗 #1", "polygon": [[-10.0, -20.0], [15.0, -20.0], [15.0, -14.0], [-10.0, -14.0]]}
    ]
    test_pid = "test-satmap-c-roof-save"
    if (PROJECTS_DIR / test_pid).exists():
        shutil.rmtree(PROJECTS_DIR / test_pid, ignore_errors=True)
    try:
        r_save = client.post(
            "/api/satmap/save-project",
            json={
                "project_id": test_pid,
                "overwrite": True,
                "name": "C型屋顶卫星转入测试",
                "address": "江苏省泰州市海陵区济川东路93号",
                "lat": 32.4568,
                "lon": 119.9182,
                "roof_type": "flat",
                "outline": c_shape_outline,
                "obstacles": c_keepout,
            },
        )
        assert r_save.status_code == 200
        save_json = r_save.json()
        assert save_json["ok"] is True
        assert save_json["outline_vertices"] == 8
        assert save_json["keepout_count"] == 1
        saved_proj = storage.load(save_json["project_id"])
        assert len(saved_proj.roof.outline) == 8
        assert len(saved_proj.roof.keepouts) == 1
    finally:
        if (PROJECTS_DIR / test_pid).exists():
            shutil.rmtree(PROJECTS_DIR / test_pid, ignore_errors=True)


def test_satmap_and_pvsyst_browser_e2e(tmp_path):
    """Verify #satmap 5-step workbench and PVsyst 8760h UI in real headless Chromium/Edge with 0 page errors."""
    import os
    from pathlib import Path
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    from guangzhu.config import ROOT

    client = TestClient(app)
    web_dir = ROOT / "desktop/web"
    artifact_dir = Path(
        os.environ.get(
            "GUANGZHU_ARTIFACT_DIR",
            r"C:\Users\华硕\.gemini\antigravity\brain\b09cf10a-e60c-4846-b582-824a954cfbf2",
        )
    )
    out_dir = artifact_dir if artifact_dir.exists() else tmp_path

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:
                pytest.skip(f"Headless browser unavailable: {exc}")
        page = browser.new_page(viewport={"width": 1520, "height": 920})
        page_errors: list[str] = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        def handle_route(route):
            url = route.request.url
            if "offline.test" not in url:
                # External tile requests: abort cleanly in offline test so procedural + fallback renders fast
                route.abort()
                return
            rel = url.split("offline.test", 1)[-1]
            path_only = rel.split("?", 1)[0]
            if path_only.startswith("/api/"):
                method = route.request.method.upper()
                if method == "POST":
                    body = route.request.post_data_json or {}
                    resp = client.post(rel, json=body)
                else:
                    resp = client.get(rel)
                route.fulfill(
                    status=resp.status_code,
                    body=resp.content,
                    headers={"content-type": resp.headers.get("content-type", "application/json")},
                )
                return
            if path_only in ("", "/"):
                file_path = web_dir / "index.html"
            else:
                file_path = web_dir / path_only.lstrip("/")
            if file_path.is_file():
                route.fulfill(path=str(file_path))
            else:
                route.abort()

        page.route("**/*", handle_route)
        page.goto("http://offline.test/#satmap")
        page.wait_for_selector("[data-satmap-root]")
        assert page.locator('.navtabs a[href="#satmap"]').get_attribute("aria-current") == "page"
        assert page.locator('[data-sat-field="presetSite"]').count() == 0
        assert page.locator('[data-sat-weather-eval]').count() == 1

        # 1. Verify initial state is a 100% clean satellite map (0 modules before user designs)
        initial_btn_text = page.locator(".satmap-primary-lay-btn").inner_text()
        assert initial_btn_text == "一键铺设组件", f"Expected clean initial state '一键铺设组件', got {initial_btn_text}"

        # 2. Verify fullscreen map toggle works
        page.locator('.satmap-floating-tools [data-sat-action="toggle-fullscreen"]').click()
        assert page.locator(".satmap-canvas-wrap.is-fullscreen").count() == 1
        page.locator('.satmap-floating-tools [data-sat-action="toggle-fullscreen"]').click()
        assert page.locator(".satmap-canvas-wrap.is-fullscreen").count() == 0

        # 3. Draw a roof and a keepout zone on #satmap-main-canvas, verify no unwanted auto-split by default
        page.locator('.satmap-floating-tools [data-sat-tool="roof"]').click()
        canvas_box = page.locator("#satmap-main-canvas").bounding_box()
        assert canvas_box is not None
        cx = canvas_box["x"] + canvas_box["width"] * 0.5
        cy = canvas_box["y"] + canvas_box["height"] * 0.5
        page.mouse.move(cx - 120, cy - 60)
        page.mouse.down()
        page.mouse.move(cx + 120, cy + 60, steps=5)
        page.mouse.up()
        assert page.locator(".satmap-roof-type-bar").count() == 1
        assert page.locator('.satmap-roof-type-pill[data-sat-roof-type="single_slope"].active').count() == 1

        # Draw a keepout zone (禁布区) via mouse drag on the roof
        page.locator('.satmap-floating-tools [data-sat-tool="obstacle"]').click()
        page.mouse.move(cx - 50, cy - 15)
        page.mouse.down()
        page.mouse.move(cx + 50, cy + 15, steps=5)
        page.mouse.up()
        assert page.locator("[data-sat-del-obs]").count() >= 1

        # Click '3. 一键铺设' to lay out modules on the satellite roof avoiding the keepout zone
        page.locator('.satmap-floating-tools [data-sat-action="layout-modules"]').click()
        page.wait_for_timeout(300)
        laid_btn_text = page.locator(".satmap-primary-lay-btn").inner_text()
        assert "重新铺设" in laid_btn_text and ("千瓦" in laid_btn_text or "kWp" in laid_btn_text), f"Expected modules laid out, got {laid_btn_text}"
        page.screenshot(path=str(out_dir / "satmap_step1_workbench.png"))

        # Launch WebGL Three.js 3D Digital Twin & Ray-Traced Shading Simulator
        page.locator('.satmap-floating-tools [data-sat-action="jump-3d-sim"]').click()
        page.wait_for_selector("#satmap-3d-twin-stage")
        assert page.locator(".satmap-3d-simbar").count() == 1
        assert page.locator("#satmap-3d-metrics-bar").count() == 1
        metrics_txt = page.locator("#satmap-3d-metrics-bar").inner_text()
        assert "太阳高度角" in metrics_txt and "旁路二极管" in metrics_txt, f"Unexpected 3D metrics text: {metrics_txt}"
        page.locator('[data-sat-3d-mode="irradiance"]').click()
        page.locator('[data-sat-3d-mode="diode"]').click()
        page.locator('[data-sat-3d-mode="wind"]').click()
        page.locator('[data-sat-3d-mode="realistic"]').click()
        page.locator('[data-sat-3d-cam="walkway"]').click()
        page.locator('[data-sat-3d-cam="iso"]').click()
        page.wait_for_timeout(200)
        page.screenshot(path=str(out_dir / "satmap_step1_3d_digital_twin.png"))
        page.locator('.satmap-3d-simbar [data-sat-action="sync-3d-shading"]').click()
        page.locator('.satmap-3d-simbar [data-sat-action="set-2d"]').click()
        assert page.locator("#satmap-3d-twin-stage").count() == 0

        # Verify vertical scrolling works inside .satmap-shell and does NOT jump back up
        scroll_info = page.evaluate(
            """() => {
                const shell = document.querySelector('.satmap-shell');
                if (!shell) return { scrollHeight: 0, clientHeight: 0, scrollTop: 0 };
                shell.scrollTop = 780;
                return {
                    scrollHeight: shell.scrollHeight,
                    clientHeight: shell.clientHeight,
                    scrollTop: shell.scrollTop
                };
            }"""
        )
        assert scroll_info["scrollHeight"] > scroll_info["clientHeight"], f"Expected scrollable .satmap-shell, got {scroll_info}"
        assert scroll_info["scrollTop"] > 100, f"Expected .satmap-shell to scroll down, got {scroll_info}"
        page.wait_for_timeout(400)
        after_wait_scroll = page.evaluate("() => document.querySelector('.satmap-shell')?.scrollTop || 0")
        assert after_wait_scroll > 100, f"Expected Step 1 scroll not to jump back to 0, got {after_wait_scroll}"
        page.screenshot(path=str(out_dir / "satmap_step1_weather_angle_eval.png"))
        page.evaluate("() => { const s = document.querySelector('.satmap-shell'); if (s) s.scrollTop = 0; }")

        # Step 2: Electrical Design & MPPT Table + Inverter Brand Filter
        page.locator('.satmap-steps [data-sat-step="2"]').click()
        page.wait_for_selector(".satmap-mppt-table")
        assert page.locator(".satmap-inv-card").count() >= 6
        assert page.locator(".satmap-mppt-table tbody tr").count() >= 9
        page.screenshot(path=str(out_dir / "satmap_step2_mppt.png"))

        # Step 3: 8760h Simulation & Official Live Weather (verify scroll stability without infinite loop!)
        page.locator('.satmap-steps [data-sat-step="3"]').click()
        page.wait_for_selector("[data-pvsyst-workbench]")
        assert page.locator('[data-pvsyst-section="waterfall"]').count() == 1
        assert page.locator('[data-pvsyst-section="monthly"]').count() == 1
        assert page.locator('[data-pvsyst-section="optimization-sunpath"]').count() == 1
        page.evaluate("() => { const s = document.querySelector('.satmap-shell'); if (s) s.scrollTop = 450; }")
        page.wait_for_timeout(450)
        step3_scroll = page.evaluate("() => document.querySelector('.satmap-shell')?.scrollTop || 0")
        assert step3_scroll > 200, f"Expected Step 3 scroll not to jump back to 0, got {step3_scroll}"
        page.evaluate("() => { const s = document.querySelector('.satmap-shell'); if (s) s.scrollTop = 0; }")
        page.screenshot(path=str(out_dir / "satmap_step3_pvsyst.png"), full_page=True)

        # Step 4: Oblique Photo 4-Point Perspective Homography + Parapet Sightline Occlusion
        page.locator('.satmap-steps [data-sat-step="4"]').click()
        page.wait_for_selector("#sat-effect-canvas")
        page.locator('[data-sat-effect="demo-occlusion"]').click()
        page.evaluate("() => { const s = document.querySelector('.satmap-shell'); if (s) s.scrollTop = 0; }")
        page.screenshot(path=str(out_dir / "satmap_step4_oblique_effect.png"))

        # Step 5: 4 CAD Drawings (排布图 / 组串图 / 防雷接地图 / 支架图)
        page.locator('.satmap-steps [data-sat-step="5"]').click()
        page.wait_for_selector("#satmap-cad-svg-host svg")
        page.screenshot(path=str(out_dir / "satmap_step5_cad_layout.png"))
        page.locator('.satmap-cad-tabs [data-sat-cad-sheet="bracket"]').click()
        page.screenshot(path=str(out_dir / "satmap_step5_cad_bracket.png"))

        # Verify Topnav has exactly 5 clean non-wrapping tabs & #lab bidirectional sync + pure ZH/EN mode
        assert page.locator(".navtabs a").count() == 5
        page.locator('.navtabs a[href="#lab"]').click()
        page.wait_for_selector("[data-lab-tab]")
        page.wait_for_timeout(200)
        page.screenshot(path=str(out_dir / "lab_zh_overview.png"))

        # Switch to English mode via top-right #lang-toggle and verify single-line navtabs + pure EN UI
        page.locator("#lang-toggle").click()
        page.wait_for_timeout(250)
        en_nav_heights = page.evaluate(
            "() => Array.from(document.querySelectorAll('.navtabs a')).map(a => Math.round(a.getBoundingClientRect().height))"
        )
        assert all(h <= 40 for h in en_nav_heights), f"Expected single-line English nav tabs (<=40px), got {en_nav_heights}"
        page.screenshot(path=str(out_dir / "lab_en_overview.png"))

        # Switch back to Chinese mode
        page.locator("#lang-toggle").click()
        page.wait_for_timeout(200)

        assert not page_errors, f"Unexpected browser page errors: {page_errors}"
        browser.close()


def test_multi_orientation_8760_slope_isolation_structural_and_dcf():
    """Verify heterogeneous dual-slope 8760h physics, strict South/North string & MPPT isolation, GB 55001 check, 25-yr DCF & layered DXF."""
    sim_multi = simulate_pvsyst(
        32.4562,
        119.9231,
        dc_kw=300.0,
        ac_kw=250.0,
        tilt_deg=10.0,
        azimuth_deg=180.0,
        sub_arrays=[
            {"name": "南坡子阵 (180°)", "dc_kw": 150.0, "tilt_deg": 10.0, "azimuth_deg": 180.0},
            {"name": "北坡子阵 (0°)", "dc_kw": 150.0, "tilt_deg": 10.0, "azimuth_deg": 0.0},
        ],
        offline=True,
    )
    assert sim_multi["ok"] is True
    subs = sim_multi.get("sub_arrays_summary") or []
    assert len(subs) == 2
    south_sub = next(s for s in subs if abs(s["azimuth_deg"] - 180.0) < 1e-3)
    north_sub = next(s for s in subs if abs(s["azimuth_deg"] - 0.0) < 1e-3)
    assert south_sub["glob_inc_kwh_m2"] > north_sub["glob_inc_kwh_m2"]
    assert south_sub["specific_yield_kwh_kwp"] > north_sub["specific_yield_kwh_kwp"]

    design_res = run_satmap_design(
        {
            "lat": 32.4562,
            "lon": 119.9231,
            "roof_type": "double_slope",
            "slope_deg": 8.0,
            "offline": True,
        }
    )
    assert design_res["ok"] is True
    assert design_res["summary"]["south_count"] > 0
    assert design_res["summary"]["north_count"] > 0

    # Zero strings and zero MPPT channels may mix South and North slopes
    mod_slope_by_id = {m["id"]: m.get("slope") for m in design_res["modules"]}
    for st in design_res["strings"]:
        slope_val = st.get("slope")
        assert slope_val in ("south", "north")
        for mid in st.get("module_ids") or []:
            assert mod_slope_by_id.get(mid) == slope_val, f"String {st['id']} mixed South and North modules!"

    for mrow in design_res["mppt_table"]:
        if mrow["string_count"] > 0:
            assert mrow["slope"] in ("south", "north")

    st_chk = design_res["structural_check"]
    assert "GB 55001" in st_chk["standard_code"]
    assert st_chk["w0_kn_m2"] > 0
    assert st_chk["avg_added_dead_kn_m2"] <= st_chk["roof_load_limit_kn_m2"]

    dcf = design_res["financial_dcf"]
    assert 10.0 <= dcf["irr_pct"] <= 40.0
    assert dcf["dynamic_payback_years"] > dcf["static_payback_years"]
    assert 0.10 <= dcf["lcoe_rmb_kwh"] <= 0.55

    assert len(design_res["pvsyst"].get("sub_arrays_summary") or []) == 2

    dxf_bytes = export_satmap_dxf(design_res, drawing_type="all")
    dxf_str = dxf_bytes.decode("utf-8")
    for required_token in ("FRAME_BORDER", "TITLE_BLOCK", "INVERTER_EQUIP", "DIMENSIONS_TEXT", "TEXT"):
        assert required_token in dxf_str

