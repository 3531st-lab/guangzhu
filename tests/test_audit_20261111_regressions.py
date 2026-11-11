"""Permanent regression suite for 2026-11-11 Full Project Audit (L01..L06, E01..E16)."""
from __future__ import annotations

import copy
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from guangzhu import (
    api,
    live_weather as live,
    mcp_actions,
    project as storage,
    pvsyst_engine as pv,
    satmap_design as sat,
    weather,
    yieldsim,
)
from guangzhu.config import API_ORIGIN, DATA_DIR
from guangzhu.local_exports import approve_export, preview_export
from guangzhu.models import Design, LayoutParams, Project


BASE_SATMAP = {
    "offline": True,
    "site": {"lat": 32.4568, "lon": 119.9182},
    "roof": {
        "type": "double_slope",
        "slope_deg": 30,
        "polygon_m": [[-10, -8], [10, -8], [10, 8], [-10, 8]],
        "obstacles": [],
    },
}


def _run_satmap(changes: dict | None = None) -> dict:
    payload = copy.deepcopy(BASE_SATMAP)
    if changes:
        for k, v in changes.items():
            if isinstance(v, dict) and k in payload:
                payload[k].update(v)
            else:
                payload[k] = v
    return sat.run_satmap_design(payload)


def test_audit_lifecycle_export_review_and_satmap_transfer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers L01..L06 and unanalyzed_fallback without touching workspace projects."""
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(sat, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(weather, "CACHE_DIR", tmp_path / "weather")
    monkeypatch.setattr(yieldsim, "CACHE_DIR", tmp_path / "yields")
    monkeypatch.setattr(live, "LIVE_CACHE_DIR", tmp_path / "live-weather")

    source = json.loads((DATA_DIR / "demo/projects/changzhou-demo/project.json").read_text(encoding="utf-8"))
    source.update(id="lifecycle-probe", designs=[], requirements={})
    source["roof"] = dict(
        type="flat",
        outline=[[0, 0], [40, 0], [40, 24], [0, 24]],
        height_m=9,
        parapet_height_m=0,
        load_capacity_kn_m2=2,
        obstacles=[],
        keepouts=[],
    )
    source["equipment"]["racking"] = "ballast_tilt"
    record = storage.save(Project.model_validate(source))
    blank = storage.save_design(record.id, Design(params=LayoutParams(tilt_deg=15)), offline=True)
    edited = storage.edit_design(
        record.id,
        blank.version,
        [dict(op="add_modules", placements=[dict(center=[x, y]) for y in [7, 15] for x in [7, 15, 23]])],
        "isolated audit",
        "user",
        offline=True,
    )
    design = storage.load_design(record.id, edited["version"])
    pid, version = record.id, design.version
    base = storage._path(pid)
    prefix = f"/api/projects/{pid}"

    prepared = preview_export(pid, version)
    assert prepared["ready"] is True

    # L06: arbitrary unverified review JSON must not become verified
    mcp_actions._record_review(pid, version, "arbitrary-unverified-label", "approve", [])
    approved = approve_export(pid, version, prepared["approval_id"])
    assert approved["review"]["status"] == "unverified"

    with TestClient(api.app, base_url=API_ORIGIN, headers={"origin": API_ORIGIN}) as client:
        # Unanalyzed v1 PDF download must return 409
        with patch("guangzhu.report.render_pdf", side_effect=RuntimeError("missing-browser")):
            un_pdf = client.get(f"{prefix}/download/pdf?version=1")
        assert un_pdf.status_code == 409

        # L03: tampered DXF rejected on both download and /api/open
        target = base / f"exports/v{version}/layout-v{version}.dxf"
        target.write_bytes(target.read_bytes() + b"\nAUDIT-TAMPERED\n")
        (tmp_path / "home/Downloads").mkdir(parents=True)
        with patch("pathlib.Path.home", return_value=tmp_path / "home"), patch("subprocess.Popen") as spawned:
            download = client.get(f"{prefix}/download/dxf?version={version}")
            opened = client.post(
                "/api/open",
                json=dict(kind="export_file", project_id=pid, version=version, filename=target.name),
            )
        copied = tmp_path / "home/Downloads" / f"{pid}-{target.name}"
        assert download.status_code == 409
        assert opened.status_code == 409
        assert not copied.exists() and spawned.call_count == 0

        # L05: stale project input blocks stale PDF download and /api/open
        p = storage.load(pid)
        p.requirements.structured.capacity_kw_min = 100
        storage.save(p)
        report_file = base / f"reports/v{version}/report-v{version}.pdf"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_bytes(b"%PDF-1.4\nOLD-APPROVED-REPORT\n%%EOF")
        pdf_dl = client.get(f"{prefix}/download/pdf?version={version}")
        with patch("os.startfile") as start_mock:
            pdf_open = client.post("/api/open", json=dict(kind="project_report", project_id=pid, version=version))
        assert pdf_dl.status_code == 409
        assert pdf_open.status_code == 409 and start_mock.call_count == 0

        # L04: local-review on stale analysis returns 409
        review = client.post(f"{prefix}/local-review", json=dict(version=version))
        assert review.status_code == 409

    # L01 & L02: SatMap transfer fidelity & atomic lock protection
    original = dict(
        site=dict(lat=32.8, lon=120.3, name="isolated remote roof"),
        roof=dict(type="flat", slope_deg=0, polygon_m=[[0, 0], [24, 0], [24, 16], [0, 16]], obstacles=[]),
        layout_params=dict(
            stc_w=605,
            module_model="TSM-NEG19RC.20 / 605 W",
            length_m=2.382,
            width_m=1.134,
            tilt_deg=10,
            row_spacing_m=5.0,
            edge_setback_m=1.0,
        ),
        electrical_params=dict(inverter_model="SG50CX-P2", rated_ac_kw=50, modules_per_string=16),
        offline=True,
    )
    sat_res = sat.run_satmap_design(original)
    payload = dict(
        project_id="satmap-audit",
        name="original satellite design",
        address="isolated address",
        lat=32.8,
        lon=120.3,
        roof_type="flat",
        slope_deg=0,
        tilt_deg=10,
        row_spacing_m=5.0,
        edge_setback_m=1.0,
        modules_per_string=16,
        outline=original["roof"]["polygon_m"],
        obstacles=[],
        module_id="trina-tsm-605neg19rc20",
        inverter_id="sungrow-sg50cx-p2",
        modules=sat_res["modules"],
        module_count=sat_res["summary"]["module_count"],
        dc_kw=sat_res["summary"]["dc_kw"],
        ac_kw=sat_res["summary"]["ac_kw"],
        annual_kwh=sat_res["summary"]["annual_kwh"],
    )
    saved = sat.save_to_guangzhu_project(payload)
    proj_saved = storage.load(saved["project_id"])
    des_saved = storage.load_design(saved["project_id"], saved["version"])
    assert (proj_saved.site.lat, proj_saved.site.lon) == (32.8, 120.3)
    assert proj_saved.site.wind_city is None
    assert proj_saved.equipment.module_id == "trina-tsm-605neg19rc20"
    assert proj_saved.equipment.inverter_id == "sungrow-sg50cx-p2"
    assert proj_saved.requirements.structured.keep_clear_ids == []
    assert proj_saved.designs == ["v1"]
    assert des_saved.params.tilt_deg == 10.0
    assert des_saved.modules_per_string == 16
    assert len(des_saved.modules) == sat_res["summary"]["module_count"]

    locked = storage.edit_design(
        proj_saved.id,
        1,
        [dict(op="lock_modules", module_ids=[des_saved.modules[0].id])],
        "isolation lock",
        "user",
        offline=True,
    )
    sbase = storage._path(proj_saved.id)
    before_proj_bytes = (sbase / "project.json").read_bytes()
    before_v2_bytes = (sbase / f"designs/v{locked['version']}.json").read_bytes()
    with pytest.raises(Exception) as exc_info:
        sat.save_to_guangzhu_project(
            payload | dict(overwrite=True, name="mutated", outline=[[0, 0], [18, 0], [18, 12], [0, 12]])
        )
    assert getattr(exc_info.value, "error_code", "") == "DESIGN_LOCK_GEOMETRY_CHANGED"
    assert (sbase / "project.json").read_bytes() == before_proj_bytes
    assert (sbase / f"designs/v{locked['version']}.json").read_bytes() == before_v2_bytes


def test_audit_engineering_physics_electrical_and_financial_invariants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers E01..E16 physics, electrical, structural, financial, and live-weather invariants."""
    monkeypatch.setattr(live, "LIVE_CACHE_DIR", tmp_path / "live-weather")

    # E01: Connected modules == summary.module_count & dc_kw conservation
    base = _run_satmap()
    conn_base = sum(len(s["module_ids"]) for s in base["strings"])
    assert conn_base == base["summary"]["module_count"]
    assert abs(base["summary"]["dc_kw"] - round(conn_base * 0.58, 2)) < 1e-6

    # E04: Empty roof produces zero yield and None financial ratios
    empty = _run_satmap({"roof": {"polygon_m": [[0, 0], [1, 0], [1, 1], [0, 1]]}})
    assert empty["summary"]["module_count"] == 0
    assert empty["summary"]["dc_kw"] == 0.0
    assert empty["summary"]["annual_kwh"] == 0.0
    assert empty["financial_dcf"]["irr_pct"] is None
    assert empty["financial_dcf"]["static_payback_years"] is None

    # E02: All-negative cashflows return None IRR and None payback
    poor = _run_satmap({"financial_params": {"capex_per_w": 100, "tariff_self_rmb": 0.001, "tariff_feed_rmb": 0.001}})
    assert all(cf < 0 for cf in poor["financial_dcf"]["cashflows_wan"])
    assert poor["financial_dcf"]["irr_pct"] is None
    assert poor["financial_dcf"]["static_payback_years"] is None
    assert poor["financial_dcf"]["dynamic_payback_years"] is None

    # E14: Explicit zero self_use_ratio & zero discount_rate_pct preserved
    zero = _run_satmap({"financial_params": {"self_use_ratio": 0, "discount_rate_pct": 0}})
    assert zero["financial_dcf"]["self_use_ratio"] == 0.0
    assert zero["financial_dcf"]["discount_rate_pct"] == 0.0
    assert zero["financial_dcf"]["weighted_tariff_rmb"] == 0.38
    assert zero["financial_dcf"]["static_payback_years"] == zero["financial_dcf"]["dynamic_payback_years"]

    # E06: Snow load participates in GB 50009 / GB 55001 combination check
    low_snow = _run_satmap({"structural_params": {"s0_kn_m2": 0.1}})
    high_snow = _run_satmap({"structural_params": {"s0_kn_m2": 5.0}})
    assert low_snow["structural_check"]["all_pass"] is True
    assert high_snow["structural_check"]["all_pass"] is False
    assert high_snow["structural_check"]["avg_comb_down_kn_m2"] > low_snow["structural_check"]["avg_comb_down_kn_m2"]

    # E07a & E07b: Azimuth honored on double_slope & translation invariance
    az90 = _run_satmap({"layout_params": {"azimuth_deg": 90}})
    assert sorted(set(m["azimuth_deg"] for m in base["modules"])) == [0.0, 180.0]
    assert sorted(set(m["azimuth_deg"] for m in az90["modules"])) == [90.0, 270.0]
    translated = _run_satmap({"roof": {"polygon_m": [[-10, 12], [10, 12], [10, 28], [-10, 28]]}})
    assert translated["summary"] == base["summary"]

    # E10: 3D obstacle height shading
    h1 = _run_satmap({"roof": {"obstacles": [{"polygon_m": [[12, -8], [14, -8], [14, 8], [12, 8]], "height_m": 1}]}})
    h50 = _run_satmap({"roof": {"obstacles": [{"polygon_m": [[12, -8], [14, -8], [14, 8], [12, 8]], "height_m": 50}]}})
    assert h50["pvsyst"]["summary"]["shading_optical_loss_pct"] > h1["pvsyst"]["summary"]["shading_optical_loss_pct"] + 3.0
    assert h50["summary"]["annual_kwh"] < h1["summary"]["annual_kwh"] * 0.94

    # E08 & E09: MPPT allocation consistency & cold Vmp upper-bound check
    assign = _run_satmap(
        {
            "roof": {"polygon_m": [[-10, -9], [10, -9], [10, 9], [-10, 9]]},
            "electrical_params": {"mppt_count": 2, "strings_per_mppt": 2, "modules_per_string": 9},
        }
    )
    from_strings = Counter((s["inverter_index"], s["slope"]) for s in assign["strings"])
    from_table: Counter[tuple[int, str]] = Counter()
    for row in assign["mppt_table"]:
        if row["string_count"] > 0:
            from_table[(int(row["inverter_name"].split("#")[-1]), row["slope"])] += row["string_count"]
    assert from_strings == from_table

    voltage = _run_satmap({"electrical_params": {"modules_per_string": 18, "mppt_v_max": 800}})
    rows_18 = [r for r in voltage["mppt_table"] if r["modules_per_string"] == 18]
    assert rows_18 and all(r["vmp_cold_v"] > 800.0 and r["ok"] is False for r in rows_18)

    # E03: North-only roof on double_slope uses 0 deg North orientation
    north_only = _run_satmap(
        {"roof": {"obstacles": [{"polygon_m": [[-10, -8], [10, -8], [10, 0], [-10, 0]], "height_m": 0}]}}
    )
    north_correct = pv.simulate_pvsyst(
        32.4568, 119.9182, dc_kw=north_only["summary"]["dc_kw"], ac_kw=110, tilt_deg=30, azimuth_deg=0, offline=True
    )
    assert sorted(set(m["azimuth_deg"] for m in north_only["modules"])) == [0.0]
    assert abs(north_only["summary"]["annual_kwh"] - north_correct["summary"]["e_grid_kwh"]) <= 1.0

    # E11, E12, E13, E15, E16: Live weather alignment, night timestamp, AC cap, horizon passthrough & HTTP 422
    low_ac = pv.simulate_pvsyst(32.4568, 119.9182, dc_kw=100, ac_kw=10, offline=True)
    assert max(r["ac_kw"] for r in low_ac["live_weather"]["hourly_48h"]) <= 10.0 + 1e-6

    class Night(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 11, 23, 0, tzinfo=tz)

    with patch.object(live, "datetime", Night):
        night = live.fetch_live_weather(32.4568, 119.9182, offline=True)
    assert night["current"]["time"] == "2026-11-11T23:00"
    assert night["current"]["ghi_wm2"] == 0.0
    assert night["current"]["live_power_kw"] == 0.0

    times = pd.date_range("2026-06-21", periods=24, freq="h", tz="Asia/Shanghai")
    loc = live.pvlib.location.Location(32.4568, 119.9182, tz="Asia/Shanghai")
    cs = loc.get_clearsky(times - pd.Timedelta(minutes=30))
    fake_om = {
        "latitude": 32.4568,
        "longitude": 119.9182,
        "timezone": "Asia/Shanghai",
        "current_units": {"wind_speed_10m": "m/s"},
        "hourly_units": {"wind_speed_10m": "m/s"},
        "current": {
            "time": "2026-06-21T09:00",
            "temperature_2m": 25.0,
            "relative_humidity_2m": 60.0,
            "weather_code": 0,
            "cloud_cover": 5.0,
            "wind_speed_10m": 2.0,
            "wind_direction_10m": 180.0,
            "shortwave_radiation": float(cs.ghi.iloc[9]),
            "direct_normal_irradiance": float(cs.dni.iloc[9]),
            "diffuse_radiation": float(cs.dhi.iloc[9]),
        },
        "hourly": {
            "time": [t.strftime("%Y-%m-%dT%H:%M") for t in times],
            "temperature_2m": [25.0] * 24,
            "relative_humidity_2m": [60.0] * 24,
            "cloud_cover": [5.0] * 24,
            "wind_speed_10m": [2.0] * 24,
            "shortwave_radiation": cs.ghi.tolist(),
            "direct_normal_irradiance": cs.dni.tolist(),
            "diffuse_radiation": cs.dhi.tolist(),
        },
    }
    expected_9am = float(
        live._compute_poa_and_power_series(
            times - pd.Timedelta(minutes=30),
            32.4568,
            119.9182,
            cs.ghi.to_numpy(),
            cs.dni.to_numpy(),
            cs.dhi.to_numpy(),
            np.full(24, 25.0),
            np.full(24, 2.0),
            dc_kw=100,
            tilt_deg=60,
            azimuth_deg=90,
        )[0][9]
    )
    with patch.object(live, "_read_cached_payload", return_value=fake_om):
        wx_om = live.fetch_live_weather(32.4568, 119.9182, dc_kw=100, tilt_deg=60, azimuth_deg=90, offline=False)
    assert abs(wx_om["hourly_48h"][9]["poa_wm2"] - round(expected_9am, 1)) <= 0.15

    horizon = [{"azimuth": 0, "elevation": 75}, {"azimuth": 180, "elevation": 75}]
    api_hz = sat.api_pvsyst_simulate(
        {"lat": 32.4568, "lon": 119.9182, "dc_kw": 100, "offline": True, "horizon_profile": horizon}
    )
    direct_hz = pv.simulate_pvsyst(32.4568, 119.9182, dc_kw=100, offline=True, horizon_profile=horizon)
    assert api_hz["summary"]["e_grid_kwh"] == direct_hz["summary"]["e_grid_kwh"]

    t0 = time.monotonic()
    with pytest.raises(ValueError):
        pv.simulate_pvsyst(32.4568, 119.9182, dc_kw=100, lid_pct=120, offline=True)
    assert time.monotonic() - t0 < 0.5

    client = TestClient(api.app)
    assert (
        client.post(
            "/api/pvsyst/simulate", json={"lat": 32.4568, "lon": 119.9182, "dc_kw": 100, "lid_pct": 120, "offline": True}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/satmap/design", json={"offline": True, "layout_params": {"width_m": -1.134}}).status_code
        == 422
    )
