from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile

import ezdxf
from fastapi.testclient import TestClient
import openpyxl
from pypdf import PdfReader
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from guangzhu import (
    api,
    live_weather,
    project as storage,
    pvsyst_engine as pv,
    satmap_design as sat,
    satmap_multifactor as mf,
    weather,
    yieldsim,
)
from guangzhu.config import API_ORIGIN
from guangzhu.report.deliverables import write_deliverables
from guangzhu.report.pdf_generator import write_pdf_deliverables
from guangzhu.report.pvsyst_report import (
    assert_no_pvsyst_visible_text,
    build_pvsyst_report_context,
    render_pvsyst_report_html,
    render_pvsyst_report_pdf,
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _patch_isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    import shutil

    proj_dir = tmp_path / "projects"
    proj_dir.mkdir(parents=True, exist_ok=True)
    cat_dst = tmp_path / "data" / "catalog"
    if not cat_dst.exists():
        cat_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / "data" / "catalog", cat_dst)
    demo_tpl_src = ROOT / "data" / "demo" / "projects" / "changzhou-demo" / "project.json"
    demo_tpl_dst = tmp_path / "data" / "demo" / "projects" / "changzhou-demo" / "project.json"
    if demo_tpl_src.is_file() and not demo_tpl_dst.is_file():
        demo_tpl_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(demo_tpl_src, demo_tpl_dst)
    lw_dir = tmp_path / "live_weather"
    lw_dir.mkdir(parents=True, exist_ok=True)
    tmy_dir = tmp_path / "tmy_cache"
    tmy_dir.mkdir(parents=True, exist_ok=True)
    yield_dir = tmp_path / "yield_cache"
    yield_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(storage, "PROJECTS_DIR", proj_dir)
    monkeypatch.setattr(sat, "PROJECTS_DIR", proj_dir)
    monkeypatch.setattr(sat, "ROOT", tmp_path)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(live_weather, "LIVE_CACHE_DIR", lw_dir)
    monkeypatch.setattr(weather, "CACHE_DIR", tmy_dir)
    monkeypatch.setattr(yieldsim, "CACHE_DIR", yield_dir)
    return proj_dir


def test_r4_00_protected_files_catalog_and_historical_docs_intact() -> None:
    """Verify 0 byte changes across 25 protected 3D/shell files (+ index.html), 12 catalog CSVs, and historical audits."""
    snap_path = ROOT / "output" / "recheck-20261113" / "snapshot-close.json"
    assert snap_path.is_file(), "Missing output/recheck-20261113/snapshot-close.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8-sig"))
    hashes: dict[str, str] = {k.replace("\\", "/"): v.lower() for k, v in snap["hashes"].items()}

    protected_exact = [
        "desktop/web/app.js",
        "desktop/web/design-edit-ui.js",
        "desktop/web/design-edit.css",
        "desktop/web/facade-editor.css",
        "desktop/web/facade-editor.js",
        "desktop/web/module-transform-geometry.js",
        "desktop/web/parapet-editor.css",
        "desktop/web/parapet-editor.js",
        "desktop/web/park-scene-3d.js",
        "desktop/web/pro-3d-twin-engine.js",
        "desktop/web/roof-parapets.js",
        "desktop/web/roofedit-geometry.js",
        "desktop/web/roofedit-objects.css",
        "desktop/web/roofedit-objects.js",
        "desktop/web/roofedit-selection.js",
        "desktop/web/roofedit.js",
        "desktop/web/scene-camera.js",
        "desktop/web/scene-data.js",
        "desktop/web/scene-facade.js",
        "desktop/web/scene-models.js",
        "desktop/web/scene-module-transform.js",
        "desktop/web/scene-static.js",
        "desktop/web/scene-wiring.js",
        "desktop/web/scene.css",
        "desktop/web/scene.js",
    ]
    assert len(protected_exact) == 25
    diffs: list[str] = []
    for rel in protected_exact:
        exp = hashes.get(rel)
        assert exp is not None, f"{rel} missing from snapshot-close.json"
        cur = _sha256(ROOT / rel)
        if cur != exp:
            diffs.append(f"{rel}: expected {exp}, got {cur}")

    # Verify index.html untouched since Round 1 baseline
    index_sha = _sha256(ROOT / "desktop" / "web" / "index.html")
    assert index_sha == "e80b434b8fcdb1ce53f811f7dc7f1311555fc0af238823e69acb14d36f95c1cf"

    # Verify all 12 catalog CSV files untouched
    cat_files = sorted((ROOT / "data" / "catalog").glob("*.csv"))
    assert len(cat_files) == 12
    for p in cat_files:
        rel = p.relative_to(ROOT).as_posix()
        exp = hashes.get(rel)
        assert exp is not None, f"Catalog CSV {rel} missing from snapshot-close.json"
        cur = _sha256(p)
        if cur != exp:
            diffs.append(f"{rel}: expected {exp}, got {cur}")

    assert diffs == [], f"Protected files or catalog CSVs modified: {diffs}"

    # Verify historical recheck directories and docs remain present & intact
    for req_dir in ("output/recheck-20261112", "output/recheck-20261113"):
        assert (ROOT / req_dir / "snapshot-close.json").is_file()
    for doc_rel in (
        "docs/ANTIGRAVITY_REVIEW_2026-11-10.md",
        "docs/FULL_PROJECT_AUDIT_2026-11-11.md",
        "docs/FIX_VERIFICATION_2026-11-12_ROUND2.md",
        "docs/PROJECT_RECHECK_2026-11-12.md",
        "docs/PROJECT_RECHECK_2026-11-13.md",
        "docs/FIX_VERIFICATION_2026-11-13_ROUND3.md",
    ):
        assert (ROOT / doc_rel).is_file(), f"Missing historical doc: {doc_rel}"


def test_r4_e11_simulate_pvsyst_uc_uv_propagates_to_live_weather_48h(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E11 + Codex boundaries.py probe: uc_w_m2k & uv_w_m2k_ms propagate to BOTH annual e_grid_kwh AND 48h forecast."""
    _patch_isolated_env(monkeypatch, tmp_path)

    r10 = pv.simulate_pvsyst(32.4568, 119.9182, dc_kw=100.0, ac_kw=110.0, uc_w_m2k=10.0, offline=True)
    r60 = pv.simulate_pvsyst(32.4568, 119.9182, dc_kw=100.0, ac_kw=110.0, uc_w_m2k=60.0, offline=True)

    # Higher Uc cools cells -> strictly higher annual yield AND strictly higher 48h live_weather AC output
    assert r60["summary"]["e_grid_kwh"] > r10["summary"]["e_grid_kwh"] + 5000.0
    h10 = r10["live_weather"]["hourly_48h"]
    h60 = r60["live_weather"]["hourly_48h"]
    assert len(h10) == 48 and len(h60) == 48
    sum10 = sum(float(pt["ac_kw"]) for pt in h10)
    sum60 = sum(float(pt["ac_kw"]) for pt in h60)
    diff_hours = sum(1 for a, b in zip(h10, h60) if abs(float(a["ac_kw"]) - float(b["ac_kw"])) > 1e-3)
    assert sum60 > sum10 + 25.0, f"Expected 48h sum ac_kw to increase significantly with Uc=60 vs 10: {sum10} -> {sum60}"
    assert diff_hours >= 12, f"Expected daylight hours to differ in hourly_48h, got {diff_hours}"

    # Wind thermal coefficient uv_w_m2k_ms also propagates into both annual and 48h live_weather
    ruv0 = pv.simulate_pvsyst(32.4568, 119.9182, dc_kw=100.0, ac_kw=110.0, uc_w_m2k=15.0, uv_w_m2k_ms=0.0, offline=True)
    ruv3 = pv.simulate_pvsyst(32.4568, 119.9182, dc_kw=100.0, ac_kw=110.0, uc_w_m2k=15.0, uv_w_m2k_ms=3.0, offline=True)
    assert ruv3["summary"]["e_grid_kwh"] > ruv0["summary"]["e_grid_kwh"]
    assert sum(float(pt["ac_kw"]) for pt in ruv3["live_weather"]["hourly_48h"]) > sum(
        float(pt["ac_kw"]) for pt in ruv0["live_weather"]["hourly_48h"]
    )

    # Strict finite / non-bool / range validation in simulate_pvsyst & fetch_live_weather
    for bad_kwargs in (
        {"dc_kw": -1.0},
        {"dc_kw": float("nan")},
        {"dc_kw": True},
        {"ac_kw": -5.0},
        {"uc_w_m2k": 0.0},
        {"uc_w_m2k": -10.0},
        {"uv_w_m2k_ms": -0.5},
        {"tilt_deg": 95.0},
        {"albedo": 1.2},
    ):
        with pytest.raises((ValueError, TypeError)):
            pv.simulate_pvsyst(32.4568, 119.9182, offline=True, **bad_kwargs)
    for bad_lw in (
        {"dc_kw": -10.0},
        {"uc_w_m2k": 0.0},
        {"uv_w_m2k_ms": -1.0},
        {"albedo": -0.1},
        {"bifaciality": 1.5},
    ):
        with pytest.raises((ValueError, TypeError)):
            live_weather.fetch_live_weather(32.4568, 119.9182, offline=True, **bad_lw)


def test_r4_api_pvsyst_simulate_forwards_orientation_snow_stc_eff_spectral(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """POST /api/pvsyst/simulate forwards orientation_mode, snow_loss_pct, stc_eff_pct, spectral_corr_pct & bifacial_factor."""
    _patch_isolated_env(monkeypatch, tmp_path)
    base_req = {
        "lat": 32.4568,
        "lon": 119.9182,
        "dc_kw": 100.0,
        "ac_kw": 90.0,
        "tilt_deg": 18.0,
        "azimuth_deg": 180.0,
        "bifacial": True,
        "albedo": 0.28,
        "offline": True,
    }

    with TestClient(api.app, base_url=API_ORIGIN) as client:
        r_south = client.post("/api/pvsyst/simulate", json={**base_req, "orientation_mode": "south_fixed"})
        r_ew = client.post("/api/pvsyst/simulate", json={**base_req, "orientation_mode": "east_west"})
        assert r_south.status_code == 200 and r_ew.status_code == 200
        e_south = r_south.json()["summary"]["e_grid_kwh"]
        e_ew = r_ew.json()["summary"]["e_grid_kwh"]
        assert abs(e_south - e_ew) > 2000.0, f"orientation_mode had no effect: south={e_south}, ew={e_ew}"
        assert "pvsyst" not in json.dumps(r_south.json(), ensure_ascii=False).lower()

        r_snow0 = client.post("/api/pvsyst/simulate", json={**base_req, "snow_loss_pct": 0.0})
        r_snow8 = client.post("/api/pvsyst/simulate", json={**base_req, "snow_loss_pct": 8.0})
        assert r_snow0.status_code == 200 and r_snow8.status_code == 200
        assert r_snow8.json()["summary"]["e_grid_kwh"] < r_snow0.json()["summary"]["e_grid_kwh"] * 0.94

        r_eff18 = client.post("/api/pvsyst/simulate", json={**base_req, "stc_eff_pct": 18.0})
        r_eff23 = client.post("/api/pvsyst/simulate", json={**base_req, "stc_eff_pct": 23.0})
        assert r_eff18.status_code == 200 and r_eff23.status_code == 200
        area18 = r_eff18.json()["loss_tree_detail"]["collector_area_m2"]
        area23 = r_eff23.json()["loss_tree_detail"]["collector_area_m2"]
        assert area18 == pytest.approx(100.0 / 0.18, rel=0.02)
        assert area23 == pytest.approx(100.0 / 0.23, rel=0.02)
        assert area18 > area23 + 90.0

        r_spec_neg = client.post("/api/pvsyst/simulate", json={**base_req, "spectral_corr_pct": -2.0})
        r_spec_pos = client.post("/api/pvsyst/simulate", json={**base_req, "spectral_corr_pct": 2.0})
        assert r_spec_neg.status_code == 200 and r_spec_pos.status_code == 200
        assert r_spec_pos.json()["summary"]["e_grid_kwh"] > r_spec_neg.json()["summary"]["e_grid_kwh"] + 2500.0

        r_bf0 = client.post("/api/pvsyst/simulate", json={**base_req, "bifacial_factor": 0.0})
        r_bf85 = client.post("/api/pvsyst/simulate", json={**base_req, "bifacial_factor": 0.85})
        assert r_bf0.status_code == 200 and r_bf85.status_code == 200
        assert r_bf85.json()["summary"]["e_grid_kwh"] > r_bf0.json()["summary"]["e_grid_kwh"]


def test_r4_strict_422_on_nan_bool_negative_and_conflicting_loads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """All satmap, pvsyst, live-weather, and pro-report endpoints return HTTP 422 (never 500) on invalid inputs."""
    _patch_isolated_env(monkeypatch, tmp_path)
    valid_roof = {
        "type": "flat",
        "slope_deg": 0.0,
        "polygon_m": [[-15.0, -10.0], [15.0, -10.0], [15.0, 10.0], [-15.0, 10.0]],
        "obstacles": [],
    }
    headers = {"X-Guangzhu-Test": "1", "Content-Type": "application/json"}

    with TestClient(api.app, base_url=API_ORIGIN, raise_server_exceptions=False) as client:
        # 1. Raw JSON with NaN / Infinity across endpoints -> must be 422 (never 500)
        for ep in (
            "/api/pvsyst/simulate",
            "/api/pvsyst/live-weather",
            "/api/satmap/design",
            "/api/satmap/optimize-multifactor",
            "/api/satmap/drawings",
            "/api/satmap/save-project",
            "/api/satmap/sync-to-3d",
            "/api/satmap/engineering-health-check",
            "/api/satmap/export-delivery-bundle",
            "/api/pvsyst/professional-report",
            "/api/guangzhu/pro-report/export-pdf",
        ):
            r_nan = client.post(ep, content=b'{"dc_kw": NaN, "offline": true}', headers=headers)
            assert r_nan.status_code == 422, f"{ep} with raw NaN returned {r_nan.status_code}: {r_nan.text[:200]}"
            r_inf = client.post(ep, content=b'{"dc_kw": Infinity, "offline": true}', headers=headers)
            assert r_inf.status_code == 422, f"{ep} with raw Infinity returned {r_inf.status_code}: {r_inf.text[:200]}"

        # 2. Structured invalid payloads: bool-as-number, negative values, out-of-range %, conflicting wind/snow
        sim_bad_cases = [
            {"dc_kw": True, "offline": True},
            {"dc_kw": -25.0, "offline": True},
            {"dc_kw": 100.0, "ac_kw": -10.0, "offline": True},
            {"dc_kw": 100.0, "albedo": 1.5, "offline": True},
            {"dc_kw": 100.0, "soiling_pct": 100.0, "offline": True},
            {"lat": 95.0, "lon": 119.9, "dc_kw": 100.0, "offline": True},
            {"lat": 32.4, "lon": -185.0, "dc_kw": 100.0, "offline": True},
            {"dc_kw": 100.0, "uc_w_m2k": 0.0, "offline": True},
        ]
        for bad in sim_bad_cases:
            resp = client.post("/api/pvsyst/simulate", json=bad, headers=headers)
            assert resp.status_code == 422, f"/api/pvsyst/simulate {bad} -> {resp.status_code}: {resp.text[:200]}"

        # GET & POST /api/pvsyst/live-weather invalid cases
        for q in (
            "dc_kw=-10&offline=true",
            "albedo=1.4&offline=true",
            "bifaciality=-0.2&offline=true",
            "uc_w_m2k=0&offline=true",
            "lat=92&lon=120&offline=true",
        ):
            rg = client.get(f"/api/pvsyst/live-weather?{q}")
            assert rg.status_code == 422, f"GET live-weather?{q} -> {rg.status_code}"
        for lw_bad in (
            {"dc_kw": True, "offline": True},
            {"dc_kw": -5.0, "offline": True},
            {"albedo": 1.2, "offline": True},
            {"uc_w_m2k": -3.0, "offline": True},
        ):
            rp = client.post("/api/pvsyst/live-weather", json=lw_bad, headers=headers)
            assert rp.status_code == 422, f"POST live-weather {lw_bad} -> {rp.status_code}"

        # /api/satmap/design, /api/satmap/optimize-multifactor, /api/satmap/save-project, /api/satmap/sync-to-3d, /api/satmap/export-delivery-bundle
        sat_bad_cases = [
            {"offline": True, "roof": valid_roof, "dc_kw": -10.0},
            {"offline": True, "roof": valid_roof, "ac_kw": -5.0},
            {"offline": True, "roof": valid_roof, "annual_load_kwh": -100.0},
            {"offline": True, "roof": valid_roof, "annual_load_kwh": True},
            {"offline": True, "roof": valid_roof, "walkway_width_m": -0.4},
            {"offline": True, "roof": valid_roof, "financial_params": {"capex_per_w": -1.0}},
            {"offline": True, "roof": valid_roof, "financial_params": {"tariff_self": -0.2}},
            {"offline": True, "roof": valid_roof, "financial_params": {"tariff_grid": -0.1}},
            {"offline": True, "roof": valid_roof, "financial_params": {"discount_rate_pct": -2.0}},
            {"offline": True, "roof": valid_roof, "multifactor_params": {"soiling_pct": 100.0}},
            {"offline": True, "roof": valid_roof, "multifactor_params": {"albedo": 1.25}},
            {
                "offline": True,
                "roof": valid_roof,
                "w0_kn_m2": 0.40,
                "structural_params": {"basic_wind_w0_kn_m2": 0.90},
            },
            {
                "offline": True,
                "roof": valid_roof,
                "structural_params": {"s0_kn_m2": 0.15},
                "multifactor_params": {"basic_snow_s0_kn_m2": 4.5},
            },
            {"offline": True, "roof": valid_roof, "layout_params": {"width_m": 0.0}},
            {"offline": True, "roof": valid_roof, "layout_params": {"length_m": -0.1}},
        ]
        for bad in sat_bad_cases:
            for ep in ("/api/satmap/design", "/api/satmap/optimize-multifactor"):
                r = client.post(ep, json=bad, headers=headers)
                assert r.status_code == 422, f"{ep} with {bad} -> {r.status_code}: {r.text[:200]}"

        for ep in (
            "/api/satmap/drawings",
            "/api/satmap/save-project",
            "/api/satmap/sync-to-3d",
            "/api/satmap/engineering-health-check",
            "/api/satmap/export-delivery-bundle",
        ):
            for bad in (
                {"offline": True, "roof": valid_roof, "dc_kw": -10.0},
                {"offline": True, "roof": valid_roof, "dc_kw": True},
                {
                    "offline": True,
                    "roof": valid_roof,
                    "w0_kn_m2": 0.35,
                    "structural_params": {"basic_wind_w0_kn_m2": 0.85},
                },
            ):
                r = client.post(ep, json=bad, headers=headers)
                assert r.status_code == 422, f"{ep} with {bad} -> {r.status_code}: {r.text[:200]}"

        # Report endpoints: negative / bool / out-of-range coords / conflicting loads -> HTTP 422
        report_bad_cases = [
            {"system": {"dc_kw": -10.0}, "offline": True},
            {"system": {"dc_kw": True}, "offline": True},
            {"system": {"dc_kw": 100.0, "ac_kw": -5.0}, "offline": True},
            {"system": {"module_count": -3}, "offline": True},
            {"site": {"lat": 95.0, "lon": 120.0}, "system": {"dc_kw": 50.0}, "offline": True},
            {"site": {"lat": 31.0, "lon": 190.0}, "system": {"dc_kw": 50.0}, "offline": True},
            {"version": 0, "system": {"dc_kw": 50.0}, "offline": True},
            {
                "system": {"dc_kw": 100.0},
                "w0_kn_m2": 0.40,
                "structural_params": {"basic_wind_w0_kn_m2": 0.90},
                "offline": True,
            },
        ]
        for bad in report_bad_cases:
            for ep in (
                "/api/pvsyst/professional-report",
                "/api/guangzhu/pro-report",
                "/api/guangzhu/pro-report/export-pdf",
            ):
                r = client.post(ep, json=bad, headers=headers)
                assert r.status_code == 422, f"{ep} with {bad} -> {r.status_code}: {r.text[:200]}"

        # Project report GET routes: invalid slug -> 400/422, missing project -> 404/422 (never 500)
        for ep in (
            "/api/projects/nonexistent-r4-proj/pvsyst-report-html",
            "/api/projects/nonexistent-r4-proj/pvsyst-report-pdf",
        ):
            r_miss = client.get(ep)
            assert r_miss.status_code in (404, 422)


def test_r4_multifactor_all_candidates_electrical_completeness_and_5_deliverables_reconciliation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every multifactor candidate carries complete electrical allocation and reconciles 100% on 3D save + 5 deliverables."""
    proj_dir = _patch_isolated_env(monkeypatch, tmp_path)
    headers = {"X-Guangzhu-Test": "1"}

    opt_req = {
        "offline": True,
        "objective": "balanced",
        "site": {"name": "泰州医药城智能制造厂房R4核验", "lat": 32.4568, "lon": 119.9182},
        "roof": {
            "type": "flat",
            "building_height_m": 12.0,
            "parapet_height_m": 0.6,
            "slope_deg": 0.0,
            "setback_m": 1.0,
            "polygon_m": [[-22.0, -12.0], [22.0, -12.0], [22.0, 12.0], [-22.0, 12.0]],
            "obstacles": [
                {
                    "id": "hvac-1",
                    "kind": "hvac",
                    "name": "屋顶空调机组",
                    "polygon_m": [[-3.0, -2.0], [3.0, -2.0], [3.0, 2.0], [-3.0, 2.0]],
                    "height_m": 1.8,
                }
            ],
        },
        "multifactor_params": {
            "albedo": 0.28,
            "pollution_level": "light_industrial",
            "extreme_temp_min_c": -10.0,
            "extreme_temp_max_c": 40.0,
            "load_profile": "industrial_day",
            "annual_load_kwh": 650000.0,
            "discount_rate_pct": 6.0,
        },
    }

    with TestClient(api.app, base_url=API_ORIGIN) as client:
        r_opt = client.post("/api/satmap/optimize-multifactor", json=opt_req, headers=headers)
        assert r_opt.status_code == 200, r_opt.text
        opt_data = r_opt.json()
        schemes = opt_data.get("schemes") or []
        assert len(schemes) >= 5, f"Expected >=5 candidate schemes, got {len(schemes)}"

        required_elec_keys = (
            "modules_per_string",
            "string_count",
            "inverter_count",
            "ac_kw",
            "dc_ac_ratio",
            "mppt_ports_used",
            "mppt_ports_total",
            "module_id",
            "inverter_id",
            "setback_m",
        )
        valid_candidates = 0
        recommended_saved_pid: str | None = None
        recommended_scheme: dict | None = None

        for idx, cand in enumerate(schemes):
            for k in required_elec_keys:
                assert cand.get(k) is not None, f"Scheme {cand.get('id')} missing {k}: {cand}"
            if isinstance(cand.get("electrical"), dict):
                for ek in ("modules_per_string", "string_count", "inverter_count", "ac_kw", "mppt_ports_used", "mppt_ports_total"):
                    assert cand["electrical"].get(ek) == cand.get(ek), f"Scheme {cand.get('id')} electrical.{ek} mismatch"

            if int(cand.get("module_count") or 0) <= 0:
                continue

            valid_candidates += 1
            assert int(cand["modules_per_string"]) >= 1
            assert int(cand["string_count"]) >= 1
            assert int(cand["inverter_count"]) >= 1
            assert float(cand["ac_kw"]) > 0.0
            assert float(cand["dc_ac_ratio"]) > 0.0
            assert int(cand["mppt_ports_used"]) <= int(cand["mppt_ports_total"])

            pid = f"r4-mf-cand-{idx + 1}-{re.sub(r'[^a-z0-9]+', '-', str(cand['id']).lower()).strip('-')[:18]}"
            save_payload = {
                "project_id": pid,
                "project_name": f"R4寻优候选_{cand['id']}",
                "offline": True,
                "site": opt_req["site"],
                "roof": {
                    **opt_req["roof"],
                    "setback_m": cand["setback_m"],
                },
                "module_id": cand["module_id"],
                "inverter_id": cand["inverter_id"],
                "modules_per_string": cand["modules_per_string"],
                "orientation_mode": cand.get("orientation_mode"),
                "mount_orientation": cand.get("mount_orientation"),
                "tilt_deg": cand.get("tilt_deg"),
                "azimuth_deg": cand.get("azimuth_deg"),
                "modules": cand.get("modules") or [],
                "summary": {
                    "module_count": cand["module_count"],
                    "dc_kw": cand["dc_kw"],
                    "ac_kw": cand["ac_kw"],
                    "dc_ac_ratio": cand["dc_ac_ratio"],
                    "string_count": cand["string_count"],
                    "modules_per_string": cand["modules_per_string"],
                    "inverter_count": cand["inverter_count"],
                    "module_id": cand["module_id"],
                    "inverter_id": cand["inverter_id"],
                    "annual_kwh": cand.get("annual_kwh"),
                },
                "multifactor": {
                    "orientation_mode": cand.get("orientation_mode"),
                    "canopy_clearance_m": cand.get("canopy_clearance_m", 2.8),
                    "effective_setback_m": cand["setback_m"],
                },
            }
            r_save = client.post("/api/satmap/save-project", json=save_payload, headers=headers)
            assert r_save.status_code == 200, f"Saving {cand['id']} failed: {r_save.text}"
            save_res = r_save.json()
            recon = save_res.get("allocation_reconciliation") or {}
            assert recon.get("matched") is True, (
                f"Candidate {cand['id']} failed 3D allocation_reconciliation: {json.dumps(recon, ensure_ascii=False)}"
            )
            assert recon.get("diffs") == []

            if cand["id"] == opt_data.get("recommended_id") or recommended_saved_pid is None:
                recommended_saved_pid = pid
                recommended_scheme = cand

        assert valid_candidates >= 5
        assert recommended_saved_pid is not None and recommended_scheme is not None

        # Cross-reconcile all 5 engineering deliverables for the adopted recommended scheme!
        ver = 1
        base_dir = proj_dir / recommended_saved_pid
        assert (base_dir / f"analysis/v{ver}/summary.json").is_file()
        elec_an = json.loads((base_dir / f"analysis/v{ver}/electrical.json").read_text(encoding="utf-8"))
        sum_an = json.loads((base_dir / f"analysis/v{ver}/summary.json").read_text(encoding="utf-8"))

        exp_mods = int(recommended_scheme["module_count"])
        exp_dc = float(recommended_scheme["dc_kw"])
        exp_ac = float(recommended_scheme["ac_kw"])
        exp_inv = int(recommended_scheme["inverter_count"])
        exp_str = int(recommended_scheme["string_count"])
        assert int(elec_an["inverter_count"]) == exp_inv
        assert float(sum_an["electrical"]["rated_ac_kw"]) == pytest.approx(exp_ac, abs=0.2)

        # Deliverables 1..4: BOM XLSX, Layout DXF, Drawing PDF, Report PDF via write_deliverables & write_pdf_deliverables
        deliv_dir = tmp_path / "deliverables_3d"
        deliv_dir.mkdir(parents=True, exist_ok=True)
        write_deliverables(recommended_saved_pid, ver, deliv_dir, base_dir=base_dir)
        write_pdf_deliverables(recommended_saved_pid, ver, deliv_dir, base_dir=base_dir)

        wb = openpyxl.load_workbook(str(deliv_dir / f"bom-v{ver}.xlsx"), read_only=True, data_only=True)
        ws = wb["材料清单"]
        bom_mod_cnt = None
        bom_inv_cnt = None
        bom_dc_kw = None
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or row[0] is None:
                continue
            if str(row[0]).strip() == "组件":
                bom_mod_cnt = int(row[4])
                bom_dc_kw = float(row[6])
            elif str(row[0]).strip() == "逆变器":
                bom_inv_cnt = int(row[4])
        wb.close()
        assert bom_mod_cnt == exp_mods
        assert bom_inv_cnt == exp_inv
        assert bom_dc_kw == pytest.approx(exp_dc, abs=0.2)

        dxf_doc_3d = ezdxf.readfile(str(deliv_dir / f"layout-v{ver}.dxf"))
        pv_entities = [
            e
            for e in dxf_doc_3d.modelspace()
            if (e.dxf.layer if hasattr(e.dxf, "layer") else "").upper() in ("PV", "PV_MODULES")
            and e.dxftype() in ("LWPOLYLINE", "POLYLINE", "INSERT")
        ]
        assert len(pv_entities) == exp_mods

        drw_text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(deliv_dir / f"drawing-v{ver}.pdf")).pages)
        rep_text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(deliv_dir / f"report-v{ver}.pdf")).pages)
        assert str(exp_mods) in drw_text
        assert str(exp_mods) in rep_text

        # Deliverable 5: 6-Page Guangzhu Pro Report HTML & PDF via FastAPI GET routes + Satmap CAD & ZIP Bundle
        r_html = client.get(f"/api/projects/{recommended_saved_pid}/pvsyst-report-html")
        assert r_html.status_code == 200
        html_doc = r_html.text
        assert_no_pvsyst_visible_text(html_doc)
        assert f"{exp_mods} 块" in html_doc
        assert f"{exp_str} 串" in html_doc
        assert f"{exp_inv} 台" in html_doc

        r_pdf = client.get(f"/api/projects/{recommended_saved_pid}/pvsyst-report-pdf")
        assert r_pdf.status_code == 200
        assert r_pdf.content.startswith(b"%PDF-")
        pdf_reader = PdfReader(io.BytesIO(r_pdf.content))
        assert len(pdf_reader.pages) == 6
        full_pdf_txt = "\n".join(pg.extract_text() or "" for pg in pdf_reader.pages)
        assert str(exp_mods) in full_pdf_txt
        assert "pvsyst" not in full_pdf_txt.lower()

        r_cad = client.post(
            "/api/satmap/drawings",
            json={
                "roof": opt_req["roof"],
                "modules": recommended_scheme.get("modules") or [],
                "summary": {
                    "module_count": exp_mods,
                    "dc_kw": exp_dc,
                    "ac_kw": exp_ac,
                    "string_count": exp_str,
                    "inverter_count": exp_inv,
                },
            },
            headers=headers,
        )
        assert r_cad.status_code == 200
        cad_json = r_cad.json()
        assert len(cad_json.get("sheets") or cad_json.get("drawings") or {}) >= 4

        r_bnd = client.post(
            "/api/satmap/export-delivery-bundle",
            json={
                "test_mode": True,
                "open_folder": False,
                "offline": True,
                "project_name": f"R4交付包_{recommended_scheme['id']}",
                "site": opt_req["site"],
                "roof": opt_req["roof"],
                "modules": recommended_scheme.get("modules") or [],
                "summary": {
                    "module_count": exp_mods,
                    "dc_kw": exp_dc,
                    "ac_kw": exp_ac,
                    "dc_ac_ratio": recommended_scheme["dc_ac_ratio"],
                    "string_count": exp_str,
                    "modules_per_string": recommended_scheme["modules_per_string"],
                    "inverter_count": exp_inv,
                    "annual_kwh": recommended_scheme.get("annual_kwh"),
                },
            },
            headers=headers,
        )
        assert r_bnd.status_code == 200, r_bnd.text
        bnd = r_bnd.json()
        assert bnd["ok"] is True
        assert bnd["file_count"] == 4
        r_zip = client.get(bnd["download_zip_url"])
        assert r_zip.status_code == 200
        with zipfile.ZipFile(io.BytesIO(r_zip.content), "r") as zf:
            names = zf.namelist()
            assert len(names) == 4
            ver_name = next(n for n in names if n.endswith(".json"))
            ver_json = json.loads(zf.read(ver_name).decode("utf-8"))
            assert ver_json["summary"]["module_count"] == exp_mods
            assert float(ver_json["summary"]["dc_kw"]) == pytest.approx(exp_dc, abs=0.2)
            assert "pvsyst" not in json.dumps(ver_json, ensure_ascii=False).lower()


def test_r4_real_js_to_python_report_wire_contract_and_dcf_om_consistency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Execute actual JS payload builders in Node and feed their JSON directly into Python report routes."""
    _patch_isolated_env(monkeypatch, tmp_path)

    node_probe = r"""
import { SatMapView } from './desktop/web/satmap-view.js';
import { buildProReportPayload } from './desktop/web/satmap-3d-linkage.js';
import { InnovationLabView } from './desktop/web/innovation-lab.js';

const sv = new SatMapView(async () => ({}), () => {});
await sv.runAiDetectRoof();
sv.layoutModules({ quiet: true });
sv.computeElectricalAllocation();
const satNormal = buildProReportPayload(sv, { openNative: false });

const svZero = new SatMapView(async () => ({}), () => {});
await svZero.runAiDetectRoof();
svZero.hasLaidOut = true;
svZero.modules = [];
svZero.strings = [];
svZero.summary = {
  ...svZero.summary,
  moduleCount: 0,
  dcKw: 0,
  acKw: 0,
  dcAcRatio: 0,
  stringCount: 0,
  inverterCount: 0,
  annualKwh: 0,
  irrPct: null,
  paybackYears: null,
  lcoeRmbKwh: null,
  npv25Wan: 0,
};
const satZero = buildProReportPayload(svZero, { openNative: false });

let labLowRatioPayload = null;
const lab = new InnovationLabView({
  dcKw: 100,
  dcAcRatio: 0.8,
  fetchImpl: async (_url, opts) => {
    labLowRatioPayload = JSON.parse(opts.body);
    return { ok: true, json: async () => ({ ok: true, html: '<html></html>' }) };
  },
});
lab.selectedParetoIdx = 2;
await lab.exportGuangzhuProReport({ previewOnly: true, openNative: false });

let labZeroPayload = null;
const labZero = new InnovationLabView({
  dcKw: 0,
  moduleCount: 0,
  annualKwh: 0,
  fetchImpl: async (_url, opts) => {
    labZeroPayload = JSON.parse(opts.body);
    return { ok: true, json: async () => ({ ok: true, html: '<html></html>' }) };
  },
});
await labZero.exportGuangzhuProReport({ previewOnly: true, openNative: false });

console.log(JSON.stringify({ satNormal, satZero, labLowRatioPayload, labZeroPayload }));
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", node_probe],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    js_payloads = json.loads(proc.stdout.strip().splitlines()[-1])

    with TestClient(api.app, base_url=API_ORIGIN) as client:
        headers = {"X-Guangzhu-Test": "1"}

        # 1. Real SatMapView normal payload -> 6-page report context + HTML + PDF
        sat_norm = {**js_payloads["satNormal"], "format": "json", "offline": True}
        r1 = client.post("/api/pvsyst/professional-report", json=sat_norm, headers=headers)
        assert r1.status_code == 200, r1.text
        ctx1 = r1.json()["report_context"]
        html1 = r1.json()["html"]
        assert_no_pvsyst_visible_text(html1)
        assert ctx1["pv_array"]["vmpp_60c_v"] > 450.0, "Must use string_hot_vmpp_v, never single-module hot_vmpp_v (~38V)"
        # Verify Page 6 Year-1 O&M matches 0.042 CNY/Wp/yr (= dc_kw * 0.042 / 10.0 万元/yr)
        dc1 = float(ctx1["pv_array"]["dc_kw"])
        yr1_opex = float(ctx1["lifecycle"]["yearly_25"][0]["opex_wan"])
        assert yr1_opex == pytest.approx(dc1 * 0.042 / 10.0, abs=0.06)

        # 2. Real SatMapView cleared 0-module payload -> 0 块 / 0 串 / 0 台 & RECHECK REQUIRED
        sat_zero = {**js_payloads["satZero"], "format": "json", "offline": True}
        assert sat_zero["system"]["module_count"] == 0
        assert sat_zero["system"]["dc_kw"] == 0
        r2 = client.post("/api/pvsyst/professional-report", json=sat_zero, headers=headers)
        assert r2.status_code == 200, r2.text
        ctx2 = r2.json()["report_context"]
        html2 = r2.json()["html"]
        assert_no_pvsyst_visible_text(html2)
        assert ctx2["pv_array"]["module_count"] == 0
        assert ctx2["inverter"]["count"] == 0
        assert ctx2["verification"]["all_pass"] is False
        assert "RECHECK REQUIRED" in html2
        assert "0 块 / 0 串 / 0 台" in html2

        # 3. Real InnovationLabView dcAcRatio=0.8 payload -> ac_kw > dc_kw preserved (not clamped to 1.0!)
        lab_low = js_payloads["labLowRatioPayload"]
        assert float(lab_low["dc_ac_ratio"]) < 1.0
        assert float(lab_low["ac_kw"]) > float(lab_low["dc_kw"])
        r3 = client.post("/api/guangzhu/pro-report/export-pdf", json=lab_low, headers=headers)
        assert r3.status_code == 200, r3.text
        j3 = r3.json()
        assert j3["ok"] is True and j3["pages"] == 6
        assert_no_pvsyst_visible_text(j3["html"])

        # 4. Real InnovationLabView 0 kWp payload -> 0 kWp & RECHECK REQUIRED
        lab_zero = js_payloads["labZeroPayload"]
        assert lab_zero["dc_kw"] == 0
        assert lab_zero["ac_kw"] == 0
        assert lab_zero["module_count"] == 0
        r4 = client.post("/api/pvsyst/professional-report", json={**lab_zero, "format": "json"}, headers=headers)
        assert r4.status_code == 200, r4.text
        ctx4 = r4.json()["report_context"]
        assert ctx4["pv_array"]["dc_kw"] == 0.0
        assert ctx4["inverter"]["count"] == 0
        assert ctx4["verification"]["all_pass"] is False
        assert "RECHECK REQUIRED" in r4.json()["html"]
