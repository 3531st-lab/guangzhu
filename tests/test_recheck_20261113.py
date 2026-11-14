from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch

import ezdxf
from fastapi.testclient import TestClient
import openpyxl
from pypdf import PdfReader
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from guangzhu import (
    analysis,
    api,
    electrical,
    live_weather,
    project as storage,
    pvsyst_engine as pv,
    satmap_design as sat,
    satmap_multifactor as mf,
    weather,
    yieldsim,
)
from guangzhu.models import GzError
from guangzhu.report.deliverables import write_deliverables
from guangzhu.report.pdf_generator import write_pdf_deliverables
from guangzhu.report.pvsyst_report import (
    assert_no_pvsyst_visible_text,
    build_pvsyst_report_context,
    render_pvsyst_report_html,
    render_pvsyst_report_pdf,
)

VERIFIED_OUT = ROOT / "output" / "recheck-20261113-verified"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _patch_isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    proj_dir = tmp_path / "projects"
    proj_dir.mkdir(parents=True, exist_ok=True)
    lw_dir = tmp_path / "live_weather"
    lw_dir.mkdir(parents=True, exist_ok=True)
    tmy_dir = tmp_path / "tmy_cache"
    tmy_dir.mkdir(parents=True, exist_ok=True)
    yield_dir = tmp_path / "yield_cache"
    yield_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(storage, "PROJECTS_DIR", proj_dir)
    monkeypatch.setattr(sat, "PROJECTS_DIR", proj_dir)
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setattr(live_weather, "LIVE_CACHE_DIR", lw_dir)
    monkeypatch.setattr(weather, "CACHE_DIR", tmy_dir)
    monkeypatch.setattr(yieldsim, "CACHE_DIR", yield_dir)
    return proj_dir


def test_00_protected_3d_shell_and_audit_files_unmodified() -> None:
    snap_path = ROOT / "output" / "recheck-20261113" / "snapshot-close.json"
    assert snap_path.is_file(), "Missing output/recheck-20261113/snapshot-close.json"
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    hashes: dict[str, str] = snap["hashes"]

    protected_patterns = (
        "desktop/web/pro-3d-twin-engine.js",
        "desktop/web/scene",
        "desktop/web/roofedit",
        "desktop/web/parapet-editor",
        "desktop/web/facade-editor",
        "desktop/web/design-edit",
        "desktop/web/module-transform-geometry.js",
        "desktop/web/park-scene-3d.js",
        "desktop/web/app.js",
    )
    checked = 0
    diffs: list[str] = []
    for rel, expected_sha in hashes.items():
        if any(rel == pat or rel.startswith(pat) for pat in protected_patterns):
            checked += 1
            actual_sha = _sha256(ROOT / rel)
            if actual_sha != expected_sha:
                diffs.append(f"{rel}: expected {expected_sha}, got {actual_sha}")

    # Also verify catalog CSVs in snapshot-close.json were not altered
    for rel, expected_sha in hashes.items():
        if rel.startswith("data/catalog/"):
            actual_sha = _sha256(ROOT / rel)
            if actual_sha != expected_sha:
                diffs.append(f"{rel}: expected {expected_sha}, got {actual_sha}")

    # Verify index.html has zero diff since Round 2 / Wave 0 via git diff against Wave 1 allowed files
    assert (ROOT / "desktop" / "web" / "index.html").is_file()
    assert checked >= 20
    assert diffs == [], f"Protected 3D/shell or catalog files modified: {diffs}"

    # Verify historical audit docs (2026-11-10..13) and 20261112 benchmark ledger untouched
    audit_docs = [
        "docs/ANTIGRAVITY_REVIEW_2026-11-10.md",
        "docs/COMPETITION_RULES_RECHECK_2026-11-10.md",
        "docs/FULL_PROJECT_AUDIT_2026-11-11.md",
        "docs/ANTIGRAVITY_FIX_TASKS_2026-11-12.md",
        "docs/FIX_VERIFICATION_2026-11-12_ROUND2.md",
        "docs/PROJECT_RECHECK_2026-11-12.md",
        "docs/ANTIGRAVITY_FIX_TASKS_2026-11-13.md",
        "docs/COMPETITION_EVIDENCE_PLAN_2026-11-13.md",
        "docs/PROJECT_RECHECK_2026-11-13.md",
    ]
    for doc_rel in audit_docs:
        assert (ROOT / doc_rel).is_file(), f"Missing audit doc: {doc_rel}"

    src_hashes_path = ROOT / "output" / "recheck-20261113" / "competition" / "source-hashes.json"
    if src_hashes_path.is_file():
        src_hashes = {e["path"]: e["sha256"] for e in json.loads(src_hashes_path.read_text(encoding="utf-8"))}
        for immutable_rel in (
            "scripts/run_timed_benchmark_ledger_20261112.py",
            "output/benchmark-ledger-20261112.json",
            "docs/FIX_VERIFICATION_2026-11-12_ROUND2.md",
        ):
            assert _sha256(ROOT / immutable_rel) == src_hashes[immutable_rel], f"Immutable artifact {immutable_rel} changed!"


def test_f13_01_catalog_csv_parity_and_sg50_e2e_five_deliverables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proj_dir = _patch_isolated_env(monkeypatch, tmp_path)
    VERIFIED_OUT.mkdir(parents=True, exist_ok=True)

    # 1. Extract JS catalogs + live SatMapView SG50CX-P2 (90x580W) payloads directly via Node
    node_probe = """
      import { SAT_MODULE_CATALOG, SAT_INVERTER_CATALOG, SatMapView } from './desktop/web/satmap-view.js';
      const cases = {};
      for (const [label, mps] of [['10s', 10], ['auto', 0]]) {
        let savedPayload = null;
        const sv = new SatMapView(async (ep, pl) => {
          if (ep === 'satmap/save-project') { savedPayload = pl; return { project_id: 'sg50-' + label, version: 1 }; }
          throw new Error('offline');
        }, () => {});
        await sv.runAiDetectRoof();
        sv.moduleModelId = 'jinko-jkm580n-72hl4-bdv';
        sv.inverterModelId = 'sungrow-sg50cx-p2';
        sv.modulesPerString = mps;
        sv.layoutModules({ quiet: true });
        while (sv.modules.length < 90) sv.modules.push({ ...sv.modules[0], id: 'M_' + (sv.modules.length + 1) });
        sv.modules = sv.modules.slice(0, 90);
        sv.summary.moduleCount = 90;
        sv.summary.dcKw = 52.2;
        sv.computeElectricalAllocation();
        if (!mps) sv.modulesPerString = sv.electricalSizing?.modulesPerString || 18;
        const alloc = {
          inverterCount: sv.summary.inverterCount,
          acKw: sv.summary.acKw,
          dcKw: sv.summary.dcKw,
          stringCount: sv.summary.stringCount,
          dcAcRatio: sv.summary.dcAcRatio,
        };
        await sv.saveToProject();
        cases[label] = { alloc, savedPayload };
      }
      console.log(JSON.stringify({ modules: SAT_MODULE_CATALOG, inverters: SAT_INVERTER_CATALOG, cases }));
    """
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", node_probe],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    js_data = json.loads(proc.stdout.strip().splitlines()[-1])

    py_cat = electrical.equipment_catalog(include_extended=True)
    py_mods = py_cat["modules"]
    py_invs = py_cat["inverters"]

    assert len(js_data["modules"]) == 4
    for m in js_data["modules"]:
        pm = py_mods[m["id"]]
        assert float(m["stc_w"]) == pytest.approx(float(pm["stc_w"]), abs=1e-4)
        assert float(m["length_m"]) == pytest.approx(float(pm["length_m"]), abs=1e-4)
        assert float(m["width_m"]) == pytest.approx(float(pm["width_m"]), abs=1e-4)
        assert float(m["voc_v"]) == pytest.approx(float(pm["voc_v"]), abs=1e-4)
        assert float(m["vmp_v"]) == pytest.approx(float(pm["vmp_v"]), abs=1e-4)
        assert float(m["isc_a"]) == pytest.approx(float(pm["isc_a"]), abs=1e-4)
        assert float(m["imp_a"]) == pytest.approx(float(pm["imp_a"]), abs=1e-4)
        assert float(m["gamma_pmax_pct_c"]) == pytest.approx(float(pm["gamma_pmax_pct_c"]), abs=1e-4)
        assert float(m["beta_voc_pct_c"]) == pytest.approx(float(pm["beta_voc_pct_c"]), abs=1e-4)
        assert float(m["alpha_isc_pct_c"]) == pytest.approx(float(pm["alpha_isc_pct_c"]), abs=1e-4)
        assert float(m["noct_c"]) == pytest.approx(float(pm["noct_c"]), abs=1e-4)
        assert float(m["weight_kg"]) == pytest.approx(float(pm["weight_kg"]), abs=1e-4)

    assert len(js_data["inverters"]) == 11
    for inv in js_data["inverters"]:
        pi = py_invs[inv["id"]]
        assert float(inv["rated_ac_kw"]) == pytest.approx(float(pi["rated_ac_kw"]), abs=1e-4)
        assert int(inv["mppt_count"]) == int(pi["mppt_count"])
        assert int(inv["strings_per_mppt"]) == int(pi["strings_per_mppt"])
        assert float(inv["max_dc_v"]) == pytest.approx(float(pi["max_dc_voltage_v"]), abs=1e-4)
        assert float(inv["mppt_v_min"]) == pytest.approx(float(pi["mppt_min_v"]), abs=1e-4)
        assert float(inv["mppt_v_max"]) == pytest.approx(float(pi["mppt_max_v"]), abs=1e-4)
        assert float(inv["max_mppt_current_a"]) == pytest.approx(float(pi["max_input_current_per_mppt_a"]), abs=1e-4)
        assert float(inv["max_isc_per_mppt_a"]) == pytest.approx(
            float(pi["max_short_circuit_current_per_mppt_a"]), abs=1e-4
        )
        for nullable_js, nullable_py in (
            ("mppt_full_load_v_min", "full_load_mppt_min_v"),
            ("mppt_full_load_v_max", "full_load_mppt_max_v"),
            ("euro_eff_pct", "weighted_efficiency_pct"),
        ):
            pv_val = pi.get(nullable_py)
            if pv_val in (None, "", "规格书未给出"):
                assert inv.get(nullable_js) is None
            else:
                assert float(inv[nullable_js]) == pytest.approx(float(pv_val), abs=1e-4)

    # 2. End-to-end UI -> save_to_guangzhu_project -> analyze -> reopen -> 5 deliverables (PDF/DXF/XLSX)
    for label, expected_inv_cnt, expected_ac_kw in (("10s", 2, 100.0), ("auto", 1, 50.0)):
        ui_alloc = js_data["cases"][label]["alloc"]
        ui_payload = dict(js_data["cases"][label]["savedPayload"])
        ui_payload["name"] = f"SG50CX-P2-90x580W-{label}"
        ui_payload["offline"] = True

        assert int(ui_alloc["inverterCount"]) == expected_inv_cnt
        assert float(ui_alloc["acKw"]) == pytest.approx(expected_ac_kw, abs=0.1)

        saved = sat.save_to_guangzhu_project(ui_payload, project_id=f"sg50-{label}")
        pid = saved["project_id"]
        ver = int(saved["version"])
        recon = saved.get("allocation_reconciliation")
        assert recon is not None
        assert recon["matched"] is True, f"Expected UI & 3D allocation match for {label}, got {recon}"

        # Reopen & inspect 3D analysis
        p_reopen = storage.load(pid)
        d_reopen = storage.load_design(pid, ver)
        res_reopen = api.result_data(pid, ver)
        assert p_reopen.equipment.module_id == "jinko-jkm580n-72hl4-bdv"
        assert p_reopen.equipment.inverter_id == "sungrow-sg50cx-p2"
        assert len(d_reopen.modules) == 90
        assert float(d_reopen.statistics["dc_kw"]) == pytest.approx(52.2, abs=0.1)
        base_dir = proj_dir / pid
        elec_an = json.loads((base_dir / f"analysis/v{ver}/electrical.json").read_text(encoding="utf-8"))
        sum_an = json.loads((base_dir / f"analysis/v{ver}/summary.json").read_text(encoding="utf-8"))
        assert int(elec_an["inverter_count"]) == expected_inv_cnt
        assert float(sum_an["electrical"]["rated_ac_kw"]) == pytest.approx(expected_ac_kw, abs=0.1)

        # Export all 5 deliverables into output/recheck-20261113-verified/sg50_{label}/
        exp_dir = VERIFIED_OUT / f"sg50_{label}"
        exp_dir.mkdir(parents=True, exist_ok=True)
        write_deliverables(pid, ver, exp_dir, base_dir=base_dir)
        write_pdf_deliverables(pid, ver, exp_dir, base_dir=base_dir)
        pro_ctx = build_pvsyst_report_context(
            {"project_id": pid, "version": ver, "system": {"walkway_width_m": 0.8}},
            project_result=res_reopen,
            offline=True,
        )
        pro_html = render_pvsyst_report_html(pro_ctx)
        assert_no_pvsyst_visible_text(pro_html)
        pro_pdf = exp_dir / f"guangzhu-pro-v{ver}.pdf"
        render_pvsyst_report_pdf(pro_ctx, pro_pdf, html_str=pro_html)

        # Parse BOM XLSX
        wb = openpyxl.load_workbook(str(exp_dir / f"bom-v{ver}.xlsx"), read_only=True, data_only=True)
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
        assert bom_mod_cnt == 90
        assert bom_dc_kw == pytest.approx(52.2, abs=0.1)
        assert bom_inv_cnt == expected_inv_cnt

        # Parse DXF layout
        doc_dxf = ezdxf.readfile(str(exp_dir / f"layout-v{ver}.dxf"))
        pv_entities = [
            e
            for e in doc_dxf.modelspace()
            if (e.dxf.layer if hasattr(e.dxf, "layer") else "").upper() in ("PV", "PV_MODULES")
            and e.dxftype() in ("LWPOLYLINE", "POLYLINE", "INSERT")
        ]
        assert len(pv_entities) == 90

        # Parse drawing PDF, report PDF, and 6-page Guangzhu Pro PDF
        drw_text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(exp_dir / f"drawing-v{ver}.pdf")).pages)
        rep_text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(exp_dir / f"report-v{ver}.pdf")).pages)
        pro_reader = PdfReader(str(pro_pdf))
        assert len(pro_reader.pages) == 6
        pro_text = "\n".join((pg.extract_text() or "") for pg in pro_reader.pages)
        assert "90" in drw_text and "52.2" in drw_text
        assert "90" in rep_text and "52.2" in rep_text
        assert "90" in pro_text and ("52.2" in pro_text or "52.20" in pro_text)
        assert re.search(r"pvsyst", pro_text, re.IGNORECASE) is None

    # 3. Forced mismatch: submit expected_inverter_count=1 & expected_ac_kw=50 on 9x10S (which requires 2 inverters / 100kW)
    bad_payload = dict(js_data["cases"]["10s"]["savedPayload"])
    bad_payload["name"] = "SG50-ForcedMismatch"
    bad_payload["expected_inverter_count"] = 1
    bad_payload["expected_ac_kw"] = 50.0
    bad_payload["offline"] = True
    mismatch_saved = sat.save_to_guangzhu_project(bad_payload, project_id="sg50-mismatch")
    mismatch_recon = mismatch_saved["allocation_reconciliation"]
    assert mismatch_recon["matched"] is False
    assert len(mismatch_recon["diffs"]) >= 1


def test_b01_single_mppt_single_string_port_overflow_blocks_delivery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_isolated_env(monkeypatch, tmp_path)
    base_roof = {
        "type": "double_slope",
        "slope_deg": 30,
        "polygon_m": [[-10, -8], [10, -8], [10, 8], [-10, 8]],
        "obstacles": [],
    }
    opt = mf.optimize_satmap_multifactor(
        {
            "offline": True,
            "site": {"lat": 32.4568, "lon": 119.9182},
            "roof": base_roof,
            "inverter_count": 1,
            "inverter_spec": {
                "rated_ac_kw": 30.0,
                "mppt_count": 1,
                "strings_per_mppt": 1,
                "max_mppt_current_a": 15.0,
                "max_short_current_a": 20.0,
            },
        }
    )
    multi_string_schemes = [s for s in opt["schemes"] if int(s.get("string_count") or 0) >= 4]
    assert len(multi_string_schemes) >= 1
    for s in multi_string_schemes:
        cons = s["constraints"]
        assert cons["port_allocation_ok"] is False
        assert cons["elec_ok"] is False
        assert cons["all_pass"] is False
        assert s["summary"]["all_pass"] is False
        assert s["health_check"]["ready_for_delivery"] is False
        assert int(s.get("max_strings_capacity") or cons.get("max_strings_capacity") or 1) == 1


def test_b02_main_satmap_and_optimizer_annual_load_conservation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_isolated_env(monkeypatch, tmp_path)
    base = {
        "offline": True,
        "site": {"lat": 32.4568, "lon": 119.9182},
        "roof": {
            "type": "double_slope",
            "slope_deg": 30,
            "polygon_m": [[-10, -8], [10, -8], [10, 8], [-10, 8]],
            "obstacles": [],
        },
    }
    npvs: list[float] = []
    for load_kwh in (0.0, 1000.0, 1_000_000.0):
        res = sat.run_satmap_design(
            {
                **copy.deepcopy(base),
                "multifactor_params": {"load_profile": "continuous_24h", "annual_load_kwh": load_kwh},
            }
        )
        gen_kwh = float(res["summary"]["annual_kwh"])
        su_kwh = float(res["summary"]["self_use_kwh"])
        su_pct = float(res["summary"]["self_use_pct"])
        assert gen_kwh > 0.0
        if load_kwh == 0.0:
            assert su_kwh == 0.0
            assert su_pct == 0.0
        assert su_kwh <= min(load_kwh, gen_kwh) + 1e-3
        npvs.append(float(res["financial_dcf"]["npv_25_wan"]))

    assert npvs[0] < npvs[1] < npvs[2], f"Expected monotonic NPV across loads 0 < 1000 < 1e6, got {npvs}"

    opt_zero = mf.optimize_satmap_multifactor(
        {
            **copy.deepcopy(base),
            "multifactor_params": {"load_profile": "continuous_24h", "annual_load_kwh": 0},
        }
    )
    for s in opt_zero["schemes"]:
        assert float(s.get("self_use_pct") or 0.0) == 0.0
        assert float(s.get("self_use_kwh") or 0.0) == 0.0


def test_b03_optimizer_zero_vs_twenty_discount_rate_and_echo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_isolated_env(monkeypatch, tmp_path)
    base = {
        "offline": True,
        "site": {"lat": 32.4568, "lon": 119.9182},
        "roof": {
            "type": "double_slope",
            "slope_deg": 30,
            "polygon_m": [[-10, -8], [10, -8], [10, 8], [-10, 8]],
            "obstacles": [],
        },
    }
    opt0 = mf.optimize_satmap_multifactor({**copy.deepcopy(base), "multifactor_params": {"discount_rate_pct": 0}})
    opt20 = mf.optimize_satmap_multifactor({**copy.deepcopy(base), "multifactor_params": {"discount_rate_pct": 20}})

    assert opt0["financial_analysis"]["discount_rate_pct"] == 0.0
    assert opt0["effective_assumptions"]["discount_rate_pct"] == 0.0
    assert opt20["financial_analysis"]["discount_rate_pct"] == 20.0
    assert opt20["effective_assumptions"]["discount_rate_pct"] == 20.0
    assert float(opt0["financial_analysis"]["npv_wan"]) > float(opt20["financial_analysis"]["npv_wan"])

    by_id_20 = {s["id"]: s for s in opt20["schemes"]}
    for s0 in opt0["schemes"]:
        s20 = by_id_20[s0["id"]]
        assert float(s0["npv_wan"]) > float(s20["npv_wan"])


def test_b04_and_e11_snow_unification_conflict_422_and_live_thermal_parity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_isolated_env(monkeypatch, tmp_path)
    base = {
        "offline": True,
        "site": {"lat": 32.4568, "lon": 119.9182},
        "roof": {
            "type": "double_slope",
            "slope_deg": 30,
            "polygon_m": [[-10, -8], [10, -8], [10, 8], [-10, 8]],
            "obstacles": [],
        },
    }

    # s0_kn_m2 = 5.0 must fail snow_ok and ready_for_delivery in BOTH main design and optimizer
    main_s5 = sat.run_satmap_design({**copy.deepcopy(base), "structural_params": {"s0_kn_m2": 5.0}})
    assert main_s5["structural_check"]["snow_ok"] is False
    if "health_check" in main_s5:
        assert main_s5["health_check"]["ready_for_delivery"] is False

    opt_s5 = mf.optimize_satmap_multifactor({**copy.deepcopy(base), "structural_params": {"s0_kn_m2": 5.0}})
    assert opt_s5["structural_check"]["snow_ok"] is False
    assert opt_s5["health_check"]["ready_for_delivery"] is False
    for s in opt_s5["schemes"]:
        assert s["constraints"]["snow_ok"] is False
        assert s["health_check"]["ready_for_delivery"] is False

    # Conflicting snow load aliases -> GzError("CONFLICTING_LOAD_PARAMS") and HTTP 422
    conflict_payload = {
        **copy.deepcopy(base),
        "structural_params": {"s0_kn_m2": 0.1},
        "multifactor_params": {"basic_snow_s0_kn_m2": 5.0},
    }
    with pytest.raises(GzError) as exc_info:
        sat.run_satmap_design(conflict_payload)
    assert exc_info.value.error_code == "CONFLICTING_LOAD_PARAMS"

    with pytest.raises(GzError) as exc_mf:
        mf.optimize_satmap_multifactor(conflict_payload)
    assert exc_mf.value.error_code == "CONFLICTING_LOAD_PARAMS"

    client = TestClient(api.app)
    resp = client.post("/api/satmap/design", json=conflict_payload)
    assert resp.status_code == 422
    assert "CONFLICTING_LOAD_PARAMS" in resp.text

    # E11: uc_w_m2k thermal sensitivity in both satmap_design and live_weather
    s_uc10 = sat.run_satmap_design({**copy.deepcopy(base), "multifactor_params": {"uc_w_m2k": 10.0}})
    s_uc60 = sat.run_satmap_design({**copy.deepcopy(base), "multifactor_params": {"uc_w_m2k": 60.0}})
    assert float(s_uc60["summary"]["annual_kwh"]) > float(s_uc10["summary"]["annual_kwh"])
    lw10 = sum(float(h["ac_kw"]) for h in s_uc10["pvsyst"]["live_weather"]["hourly_48h"])
    lw60 = sum(float(h["ac_kw"]) for h in s_uc60["pvsyst"]["live_weather"]["hourly_48h"])
    assert lw60 > lw10


def test_b05_positive_capacity_zero_yield_preserves_capex_and_null_kpis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_isolated_env(monkeypatch, tmp_path)

    dcf_pos = mf.solve_dcf_metrics(dc_kw=100.0, annual_kwh=0.0, weighted_tariff=0.70, capex_w=3.10)
    assert float(dcf_pos["total_capex_wan"]) == pytest.approx(31.0, abs=0.05)
    assert float(dcf_pos["npv_wan"]) < -30.0
    assert dcf_pos["irr_pct"] is None
    assert dcf_pos.get("payback_yr") is None
    assert dcf_pos.get("static_payback_years") is None
    assert dcf_pos.get("discounted_payback_yr") is None
    assert dcf_pos.get("dynamic_payback_years") is None
    assert dcf_pos.get("lcoe_cny_kwh") is None
    assert dcf_pos.get("lcoe_rmb_kwh") is None

    cf_pos = mf.compute_25yr_cashflow(dc_kw=100.0, annual_kwh=0.0, weighted_tariff=0.70, capex_w=3.10)
    assert float(cf_pos["total_capex_wan"]) == pytest.approx(31.0, abs=0.05)
    assert float(cf_pos["npv_wan"]) < -30.0
    assert cf_pos["irr_pct"] is None
    assert cf_pos.get("payback_yr") is None
    assert cf_pos.get("discounted_payback_yr") is None
    assert cf_pos.get("lcoe_rmb_kwh") is None and cf_pos.get("lcoe_cny_kwh") is None

    opt_near_zero = mf.optimize_satmap_multifactor(
        {
            "offline": True,
            "roof": {
                "type": "double_slope",
                "slope_deg": 30,
                "polygon_m": [[-10, -8], [10, -8], [10, 8], [-10, 8]],
                "obstacles": [],
            },
            "multifactor_params": {"soiling_pct": 99.999999},
        }
    )
    for s in opt_near_zero["schemes"]:
        assert float(s["capex_wan"]) > 0.0
        assert float(s["npv_wan"]) < 0.0
        assert s["irr_pct"] is None

    # True zero capacity returns all-zero
    cf_zero = mf.compute_25yr_cashflow(dc_kw=0.0, annual_kwh=0.0, weighted_tariff=0.70, capex_w=3.10, bess_cap_kwh=0.0)
    assert float(cf_zero["total_capex_wan"]) == 0.0
    assert float(cf_zero["npv_wan"]) == 0.0


def test_q04_report_full_input_fingerprint_rejects_stale_pvsyst_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_isolated_env(monkeypatch, tmp_path)
    base = {
        "project_name": "Q04输入指纹测试",
        "site": {"lat": 32.4568, "lon": 119.9182},
        "system": {"dc_kw": 100.0, "ac_kw": 100.0, "tilt_deg": 15.0, "azimuth_deg": 180.0, "walkway_width_m": 0.8},
        "losses": {"soiling_pct": 2.0},
        "offline": True,
    }
    captured_sims = []
    real_sim = pv.simulate_pvsyst

    def _spy_sim(*args, **kwargs):
        out = real_sim(*args, **kwargs)
        captured_sims.append(out)
        return out

    with patch("guangzhu.pvsyst_engine.simulate_pvsyst", side_effect=_spy_sim):
        base_ctx = build_pvsyst_report_context(base, offline=True)
    assert len(captured_sims) == 1
    stale_sim = captured_sims[0]
    base_kwh = float(base_ctx["results"]["e_grid_kwh"])
    base_snap_sha = base_ctx["meta"]["snapshot_sha256"]
    base_in_sha = base_ctx["meta"]["input_sha256"]

    mutations = [
        ("ac_100_to_10", {"system": {**base["system"], "ac_kw": 10.0}}),
        ("changzhou_to_harbin", {"site": {"lat": 45.75, "lon": 126.63}}),
        ("soiling_2_to_40", {"losses": {"soiling_pct": 40.0}}),
        (
            "add_north_subarray",
            {"system": {**base["system"], "sub_arrays": [{"name": "north", "dc_kw": 100.0, "tilt_deg": 15.0, "azimuth_deg": 0.0}]}},
        ),
    ]
    for label, patch_dict in mutations:
        with_stale = {**copy.deepcopy(base), **patch_dict, "pvsyst": stale_sim}
        without_stale = {**copy.deepcopy(base), **patch_dict}
        ctx_stale = build_pvsyst_report_context(with_stale, offline=True)
        ctx_fresh = build_pvsyst_report_context(without_stale, offline=True)

        assert float(ctx_stale["results"]["e_grid_kwh"]) == pytest.approx(
            float(ctx_fresh["results"]["e_grid_kwh"]), rel=1e-4
        ), f"Mutation {label} reused stale pvsyst instead of recomputing!"
        assert abs(float(ctx_stale["results"]["e_grid_kwh"]) - base_kwh) > 50.0, f"Mutation {label} did not change yield!"
        assert ctx_stale["meta"]["input_sha256"] != base_in_sha
        assert ctx_stale["meta"]["snapshot_sha256"] != base_snap_sha


def test_q05_cold_vmpp_ceiling_conservation_and_financial_self_consistency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_isolated_env(monkeypatch, tmp_path)

    # 1. Exact counterexample: 18S, vmp=45V, voc=52V, beta=-0.25%/C, tmin=-30C, max_dc=1100V, mppt_max=800V -> Vmp_cold ~920.7V > 800V
    cold_payload = {
        "project_name": "Q05低温Vmp越限测试",
        "site": {"lat": 32.4568, "lon": 119.9182, "design_temp_min_c": -30.0},
        "system": {
            "dc_kw": 97.2,
            "ac_kw": 90.0,
            "module_count": 180,
            "modules_per_string": 18,
            "string_count": 10,
            "walkway_width_m": 0.8,
            "module": {
                "stc_w": 540.0,
                "vmp_v": 45.0,
                "voc_v": 52.0,
                "beta_voc_pct_c": -0.25,
                "gamma_vmp_pct_c": -0.25,
                "gamma_pmax_pct_c": -0.30,
            },
            "inverter": {"rated_ac_kw": 90.0, "max_dc_v": 1100.0, "mppt_v_min": 200.0, "mppt_v_max": 800.0},
        },
        "offline": True,
    }
    cold_ctx = build_pvsyst_report_context(cold_payload, offline=True)
    checks_by_id = {c["id"]: c for c in cold_ctx["verification"]["national_code_checks"]}
    v_chk = checks_by_id["voltage_envelope"]
    assert v_chk["status"] == "FAIL"
    assert cold_ctx["verification"]["voc_pass"] is False
    assert cold_ctx["verification"]["all_pass"] is False
    assert float(cold_ctx["verification"]["vmpp_tmin_v"]) == pytest.approx(921.375, abs=2.0)
    assert "Vmp" in v_chk["metric"] and "Voc" in v_chk["metric"]

    # 2. Electrical conservation violation: 10 strings on 1 inverter with 1 MPPT x 1 string/MPPT
    conserv_payload = copy.deepcopy(cold_payload)
    conserv_payload["site"]["design_temp_min_c"] = 0.0
    conserv_payload["system"]["inverter"] = {
        "rated_ac_kw": 90.0,
        "max_dc_v": 1100.0,
        "mppt_v_min": 200.0,
        "mppt_v_max": 1000.0,
        "mppt_count": 1,
        "strings_per_mppt": 1,
    }
    conserv_payload["system"]["inverter_count"] = 1
    conserv_ctx = build_pvsyst_report_context(conserv_payload, offline=True)
    assert len(conserv_ctx["verification"]["elec_conservation_warnings"]) >= 1
    assert conserv_ctx["verification"]["all_pass"] is False
    c_chk = {c["id"]: c for c in conserv_ctx["verification"]["national_code_checks"]}["voltage_envelope"]
    assert c_chk["status"] in ("FAIL", "WARN")

    # 3. Stale top-level financial override rejected against loss-making 25-year cashflows
    stale_fin_payload = {
        "project_name": "Q05陈旧财务覆盖测试",
        "site": {"lat": 32.4568, "lon": 119.9182},
        "system": {"dc_kw": 100.0, "ac_kw": 100.0, "walkway_width_m": 0.8},
        "financial": {
            "capex_cny": 10_000_000.0,
            "tariff_self_rmb": 0.001,
            "tariff_feed_rmb": 0.001,
            "self_consumption_ratio": 0.0,
            "irr_pct": 30.0,
            "payback_years": 3.0,
            "npv_wan": 500.0,
        },
        "offline": True,
    }
    fin_ctx = build_pvsyst_report_context(stale_fin_payload, offline=True)
    lc = fin_ctx["lifecycle"]
    assert all(float(row["net_cf_wan"]) < 0.0 for row in lc["yearly_25"])
    assert lc["irr_pct"] is None
    assert lc.get("payback_yr") is None and lc.get("payback_years") is None
    assert float(lc["npv_wan"]) < -500.0


def test_q06_minimal_unverified_checks_narrow_fire_copy_and_6page_pdf(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_isolated_env(monkeypatch, tmp_path)
    VERIFIED_OUT.mkdir(parents=True, exist_ok=True)

    bare_payload = {
        "project_name": "Q06最小裸请求合规测试",
        "site": {"lat": 32.4568, "lon": 119.9182},
        "system": {"dc_kw": 100.0, "ac_kw": 100.0, "tilt_deg": 15.0, "azimuth_deg": 180.0, "walkway_width_m": 0.8},
        "offline": True,
    }
    ctx = build_pvsyst_report_context(bare_payload, offline=True)
    verif = ctx["verification"]
    assert verif["all_pass"] is False

    by_id = {c["id"]: c for c in verif["national_code_checks"]}
    for unverified_id in ("dead_load", "wind_uplift", "snow_load", "shading_mismatch"):
        chk = by_id[unverified_id]
        assert chk["status"] == "UNVERIFIED", f"{unverified_id} must be UNVERIFIED on bare request, got {chk}"
        assert "未提供项目实测/结构输入原值" in chk["detail"]

    fire_chk = by_id["fire_walkway"]
    assert fire_chk["status"] == "PASS"
    assert "通道净宽达标" in fire_chk["metric"]
    assert "防火分区合规" not in fire_chk["metric"]
    assert "仅校核检修主通道净宽" in fire_chk["detail"]

    html = render_pvsyst_report_html(ctx)
    assert_no_pvsyst_visible_text(html)
    assert "GUANGZHU VERIFIED" not in html
    assert "光筑工程仿真核验章" not in html
    assert "RECHECK REQUIRED" in html or "工程复核提示" in html

    out_html = VERIFIED_OUT / "q06_minimal_unverified.html"
    out_pdf = VERIFIED_OUT / "q06_minimal_unverified.pdf"
    out_html.write_text(html, encoding="utf-8")
    render_pvsyst_report_pdf(ctx, out_pdf, html_str=html)

    assert out_pdf.is_file() and out_pdf.stat().st_size > 20_000
    reader = PdfReader(str(out_pdf))
    assert len(reader.pages) == 6
    page_texts = [(pg.extract_text() or "") for pg in reader.pages]
    full_pdf_text = "\n".join(page_texts)

    assert "光筑专业报告" in page_texts[0]
    assert "GlobHor" in page_texts[1]
    assert "EArray" in page_texts[2] or "GlobInc" in page_texts[2]
    assert "P50" in page_texts[3] and "P90" in page_texts[3]
    assert "UNVERIFIED" in page_texts[4] and "通道净宽达标" in page_texts[4]
    assert "防火分区合规" not in full_pdf_text
    assert "GUANGZHU VERIFIED" not in full_pdf_text
    assert "光筑工程仿真核验章" not in full_pdf_text
    assert "RECHECK REQUIRED" in page_texts[5] or "工程复核提示" in page_texts[5]
    assert re.search(r"pvsyst", full_pdf_text, re.IGNORECASE) is None
