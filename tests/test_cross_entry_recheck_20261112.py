from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from guangzhu import analysis, api, electrical, live_weather, project as storage, satmap_design as sat, satmap_multifactor as mf
from guangzhu.models import GzError
from guangzhu.pvsyst_engine import simulate_pvsyst
from guangzhu.report.pvsyst_report import build_pvsyst_report_context, render_pvsyst_report_html, render_pvsyst_report_pdf


def _patch_isolated_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    proj_dir = tmp_path / "projects"
    proj_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(storage, "PROJECTS_DIR", proj_dir)
    monkeypatch.setattr(sat, "PROJECTS_DIR", proj_dir)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    cache_lw = tmp_path / "live_weather"
    cache_lw.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(live_weather, "LIVE_CACHE_DIR", cache_lw)


def test_f01_580w_and_growatt_save_reopen_analyze_and_locked_rollback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_isolated_dirs(monkeypatch, tmp_path)

    # Reject unknown equipment strictly (no silent default replacement)
    with pytest.raises(GzError) as exc_info:
        sat.save_to_guangzhu_project({
            "name": "UnknownEq",
            "module_id": "nonexistent-module-999",
            "inverter_id": "sungrow-sg110cx-p2",
            "outline": [[-20, -10], [20, -10], [20, 10], [-20, 10]],
        })
    assert exc_info.value.error_code == "EQUIPMENT_UNKNOWN"

    # Load exact UI save payload fixture if present, else construct equivalent 580W payload
    ui_fixture = ROOT / "output" / "recheck-20261112" / "flow" / "ui-save-payload.json"
    if ui_fixture.exists():
        payload = json.loads(ui_fixture.read_text("utf-8"))
    else:
        payload = {
            "name": "分布式屋顶光伏项目",
            "address": "山东省济南市历城区工业北路",
            "lat": 36.588644,
            "lon": 116.774288,
            "roof_type": "metal",
            "slope_deg": 6,
            "tilt_deg": 6,
            "azimuth_deg": 100,
            "row_spacing_m": 1.7,
            "edge_setback_m": 0.5,
            "modules_per_string": 18,
            "orientation": "portrait",
            "outline": [[-38, -18], [38, -18], [38, 18], [-38, 18]],
            "module_id": "jinko-jkm580n-72hl4-bdv",
            "inverter_id": "sungrow-sg110cx-p2",
            "layout_params": {"stc_w": 580, "length_m": 2.278, "width_m": 1.134, "voc_v": 51.2, "vmp_v": 42.6, "isc_a": 14.3, "imp_a": 13.71},
        }

    saved = sat.save_to_guangzhu_project(payload)
    p = storage.load(saved["project_id"])
    d = storage.load_design(p.id, saved["version"])
    assert p.equipment.module_id == payload.get("module_id", "jinko-jkm580n-72hl4-bdv")
    assert p.equipment.inverter_id == payload.get("inverter_id", "sungrow-sg110cx-p2")
    assert len(d.modules) == len(payload["modules"]) if payload.get("modules") else len(d.modules) > 0
    mod_spec = electrical.load_catalog("modules.csv", include_extended=True)[p.equipment.module_id]
    assert float(mod_spec["stc_w"]) == pytest.approx(580.0, abs=0.5)
    assert abs(d.statistics["dc_kw"] - (len(d.modules) * 0.58)) < 1.0

    # Downstream 3D analysis & report & DXF must pass without 605W imp_a > 30A E06 error
    an = analysis.analyze(p.id, saved["version"], offline=True)
    assert an["dc_kw"] == pytest.approx(len(d.modules) * 0.58, rel=0.02)
    assert not any(f.get("id") == "E06" for f in an["rules"].get("failed", []))

    proj_result = api.result_data(p.id, saved["version"])
    ctx = build_pvsyst_report_context(payload={"project_id": p.id, "version": saved["version"], "system": {"walkway_width_m": 0.8}}, project_result=proj_result, offline=True)
    pdf_path = tmp_path / "pro_580w.pdf"
    render_pvsyst_report_pdf(ctx, pdf_path)
    assert pdf_path.exists() and pdf_path.stat().st_size > 5000

    # Locked module must reject overwrite without touching files
    locked = storage.edit_design(p.id, 1, [{"op": "lock_modules", "module_ids": [d.modules[0].id]}], "lock test", "user", offline=True)
    p_dir = storage._path(p.id)
    before_proj = (p_dir / "project.json").read_bytes()
    before_design = (p_dir / f"designs/v{locked['version']}.json").read_bytes()
    with pytest.raises(GzError) as lock_err:
        sat.save_to_guangzhu_project({**payload, "overwrite": True, "name": "SHOULD NOT OVERWRITE"})
    assert lock_err.value.error_code == "DESIGN_LOCK_CONFLICT"
    assert (p_dir / "project.json").read_bytes() == before_proj
    assert (p_dir / f"designs/v{locked['version']}.json").read_bytes() == before_design

    # Growatt 100kW end-to-end save + analyze
    gw_saved = sat.save_to_guangzhu_project({
        "name": "GrowattFactory",
        "lat": 32.45,
        "lon": 119.91,
        "outline": [[-25, -15], [25, -15], [25, 15], [-25, 15]],
        "module_id": "tongwei-twmnd-72hs620",
        "inverter_id": "growatt-max-100ktl3-x",
    })
    gw_proj = storage.load(gw_saved["project_id"])
    assert gw_proj.equipment.inverter_brand == "Growatt"
    assert gw_proj.equipment.inverter_id == "growatt-max-100ktl3-x"
    gw_an = analysis.analyze(gw_proj.id, gw_saved["version"], offline=True)
    assert (gw_an["electrical"].get("rated_ac_kw") or 0) >= 100.0


def test_n01_validation_and_n02_voc_mppt_bounds() -> None:
    rect = [(-20.0, -10.0), (20.0, -10.0), (20.0, 10.0), (-20.0, 10.0)]
    for bad_kwargs in (
        {"module_length_m": 0.0},
        {"module_width_m": -1.1},
        {"col_gap_m": -0.05},
        {"row_gap_override_m": -0.2},
        {"module_length_m": float("nan")},
    ):
        with pytest.raises(ValueError):
            mf.build_multifactor_layout(roof_poly_pts=rect, obstacles=[], roof_type="flat", slope_deg=0.0, lat=32.0, **bad_kwargs)

    # N02: Cold Vmpp must not exceed mppt_v_max without 1.03 inflation
    # Construct module & inverter where 20 * cold_vmp = 1015V (<= 1030V old cap, > 1000V real mppt_v_max)
    res = mf.compute_string_voc_safety(
        module_spec={"stc_w": 580.0, "voc_v": 51.0, "vmp_v": 46.0, "beta_voc_pct_c": -0.24, "gamma_vmp_pct_c": -0.32},
        inverter_spec={"max_dc_v": 1200.0, "mppt_v_min": 200.0, "mppt_v_max": 1000.0},
        extreme_temp_min_c=-10.0,
        requested_series=20,
    )
    assert res["requested_cold_vmpp_v"] > 1000.0
    assert res["mppt_overvoltage_risk"] is True
    assert res["safe"] is False
    assert res["max_series_mppt_cold"] * res["cold_vmpp_per_module_v"] <= 1000.0 + 1e-6


def test_n03_n04_n05_multifactor_dcf_load_and_subarrays() -> None:
    # N05: continuous_24h with annual_load_kwh == 0 must stay 0% self-use
    lm_zero = mf.evaluate_load_matching_and_economics(
        orientation_mode="south_fixed",
        dc_kw=100.0,
        annual_kwh=120000.0,
        load_profile="continuous_24h",
        annual_load_kwh=0.0,
        base_self_tariff_cny=0.80,
        feed_in_tariff_cny=0.35,
    )
    assert lm_zero["self_use_pct"] == 0.0
    assert lm_zero["weighted_tariff_cny_kwh"] == pytest.approx(0.35, abs=1e-4)

    # N04: discount_rate_pct=0% strictly different from 1%
    d0 = mf.solve_dcf_metrics(dc_kw=100.0, annual_kwh=120000.0, weighted_tariff=0.65, capex_w=3.0, discount_rate_pct=0.0)
    d1 = mf.solve_dcf_metrics(dc_kw=100.0, annual_kwh=120000.0, weighted_tariff=0.65, capex_w=3.0, discount_rate_pct=1.0)
    assert d0["npv_wan"] > d1["npv_wan"]

    # N04: all-loss returns None for IRR and payback (never fake 0.0% / 25.0)
    loss_d = mf.evaluate_load_matching_and_economics(
        orientation_mode="south_fixed",
        dc_kw=100.0,
        annual_kwh=120000.0,
        load_profile="export_all",
        base_self_tariff_cny=0.0,
        feed_in_tariff_cny=0.0,
    )
    assert loss_d["irr_pct"] is None
    assert loss_d["payback_yr"] is None

    # N03: north-only sub-array flips azimuth by 180 deg vs south-only
    south_sim = mf._call_pvsyst_for_scheme(
        lat=32.45, lon=119.91, dc_kw=58.0, ac_kw=50.0, orientation_mode="flush_pitched",
        tilt_deg=15.0, azimuth_deg=180.0, modules=[{"slope": "south"}] * 100,
        stc_w=580.0, shading_loss_pct=1.0, albedo=0.2, soiling_pct=2.0, snow_loss_pct=0.0, offline=True,
    )
    north_sim = mf._call_pvsyst_for_scheme(
        lat=32.45, lon=119.91, dc_kw=58.0, ac_kw=50.0, orientation_mode="flush_pitched",
        tilt_deg=15.0, azimuth_deg=180.0, modules=[{"slope": "north"}] * 100,
        stc_w=580.0, shading_loss_pct=1.0, albedo=0.2, soiling_pct=2.0, snow_loss_pct=0.0, offline=True,
    )
    assert south_sim["annual_kwh"] > north_sim["annual_kwh"] * 1.10


def test_n06_e10_satmap_design_wind_snow_and_shading_level() -> None:
    with pytest.raises(ValueError):
        sat.run_satmap_design({
            "lat": 32.45, "lon": 119.91,
            "roof": {"polygon_m": [[-20, -10], [20, -10], [20, 10], [-20, 10]], "wind_w0_kn_m2": 0.45},
            "multifactor_params": {"basic_wind_w0_kn_m2": 0.85},
            "offline": True,
        })

    out = sat.run_satmap_design({
        "lat": 32.45, "lon": 119.91,
        "roof": {"polygon_m": [[-25, -12], [25, -12], [25, 12], [-25, 12]]},
        "multifactor_params": {"basic_wind_w0_kn_m2": 0.72, "basic_snow_s0_kn_m2": 0.45},
        "offline": True,
    })
    assert out["shading_model_level"] == "scheme_heuristic_annual"
    assert out["structural_check"]["w0_kn_m2"] == pytest.approx(0.72, abs=0.01)
    assert out["structural_check"]["s0_kn_m2"] == pytest.approx(0.45, abs=0.01)
    assert out["multifactor"]["effective_setback_m"] >= 0.5


def test_e11_live_weather_subarrays_and_bifacial_forward() -> None:
    sa_ew = [
        {"name": "E", "dc_kw": 50.0, "tilt_deg": 12.0, "azimuth_deg": 90.0},
        {"name": "W", "dc_kw": 50.0, "tilt_deg": 12.0, "azimuth_deg": 270.0},
    ]
    w_south = live_weather.fetch_live_weather(32.45, 119.91, dc_kw=100.0, ac_kw=85.0, tilt_deg=12.0, azimuth_deg=180.0, bifacial=False, offline=True)
    w_ew = live_weather.fetch_live_weather(32.45, 119.91, dc_kw=100.0, ac_kw=85.0, tilt_deg=12.0, azimuth_deg=180.0, sub_arrays=sa_ew, bifacial=False, offline=True)
    w_bifi = live_weather.fetch_live_weather(32.45, 119.91, dc_kw=100.0, ac_kw=85.0, tilt_deg=12.0, azimuth_deg=180.0, bifacial=True, bifaciality=0.80, albedo=0.60, offline=True)

    assert w_ew["hourly_48h"] != w_south["hourly_48h"]
    sum_bifi = sum(h["ac_kw"] for h in w_bifi["hourly_48h"])
    sum_mono = sum(h["ac_kw"] for h in w_south["hourly_48h"])
    assert sum_bifi > sum_mono

    with patch("guangzhu.pvsyst_engine.fetch_live_weather", wraps=live_weather.fetch_live_weather) as spy_lw:
        simulate_pvsyst(32.45, 119.91, dc_kw=100.0, orientation_mode="east_west", bifacial=True, albedo=0.50, offline=True)
        kwargs = spy_lw.call_args.kwargs
        assert kwargs["bifacial"] is True
        assert kwargs["albedo"] == pytest.approx(0.50, abs=1e-4)
        assert isinstance(kwargs["sub_arrays"], list) and len(kwargs["sub_arrays"]) == 2


def test_r01_r02_r03_r04_pro_report_honesty(tmp_path: Path) -> None:
    # R01: zero self-use preserved + unrecoverable all-loss cashflows return None (no 0.5% / 25y)
    ctx_loss = build_pvsyst_report_context({
        "system": {"dc_kw": 100.0, "module_count": 172, "walkway_width_m": 0.8},
        "financial": {"self_consumption_ratio": 0.0, "tariff_self_rmb": 0.0, "tariff_feed_rmb": 0.0},
    }, offline=True)
    assert ctx_loss["results"]["self_use_pct"] == 0.0
    assert ctx_loss["lifecycle"]["irr_pct"] is None
    assert ctx_loss["lifecycle"]["payback_yr"] is None
    html_loss = render_pvsyst_report_html(ctx_loss)
    assert "pvsyst" not in html_loss.lower()
    assert "N/A (不可行)" in html_loss
    render_pvsyst_report_pdf(ctx_loss, tmp_path / "loss.pdf")
    assert (tmp_path / "loss.pdf").exists()

    # R02: explicit 0 capacity does NOT fabricate 480 modules
    ctx_zero = build_pvsyst_report_context({
        "system": {"dc_kw": 0, "module_count": 0, "walkway_width_m": 0.8},
    }, offline=True)
    assert ctx_zero["pv_array"]["module_count"] == 0
    assert ctx_zero["pv_array"]["dc_kw"] == 0.0
    assert ctx_zero["results"]["e_grid_kwh"] == 0.0
    assert ctx_zero["verification"]["all_pass"] is False
    render_pvsyst_report_pdf(ctx_zero, tmp_path / "zero.pdf")
    assert (tmp_path / "zero.pdf").exists()

    # R03: 0.2m fire walkway is FAIL (not clamped to 0.60), omitted is UNVERIFIED
    ctx_walk_fail = build_pvsyst_report_context({"system": {"dc_kw": 100.0, "module_count": 172, "walkway_width_m": 0.2}}, offline=True)
    fw_fail = [c for c in ctx_walk_fail["verification"]["national_code_checks"] if c["id"] == "fire_walkway"][0]
    assert ctx_walk_fail["verification"]["walkway_width_m"] == 0.2
    assert fw_fail["status"] == "FAIL"
    assert ctx_walk_fail["verification"]["all_pass"] is False

    ctx_walk_omit = build_pvsyst_report_context({"system": {"dc_kw": 100.0, "module_count": 172}}, offline=True)
    fw_omit = [c for c in ctx_walk_omit["verification"]["national_code_checks"] if c["id"] == "fire_walkway"][0]
    assert ctx_walk_omit["verification"]["walkway_width_m"] is None
    assert fw_omit["status"] == "UNVERIFIED"
    assert ctx_walk_omit["verification"]["all_pass"] is False
    html_omit = render_pvsyst_report_html(ctx_walk_omit)
    assert "RECHECK REQUIRED" in html_omit

    # R04: stale pvsyst snapshot with wrong dc_kw must be recomputed, and snapshot_sha256 exists
    stale_pvs = simulate_pvsyst(32.45, 119.91, dc_kw=264.0, offline=True)
    ctx_recomp = build_pvsyst_report_context({
        "system": {"dc_kw": 58.0, "module_count": 100, "walkway_width_m": 0.8},
        "pvsyst": stale_pvs,
    }, offline=True)
    assert len(ctx_recomp["meta"]["snapshot_sha256"]) == 64
    assert ctx_recomp["results"]["e_grid_kwh"] < 120000.0
