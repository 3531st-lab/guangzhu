"""Tests for the 6-Page Swiss Technical《光筑专业报告》(Guangzhu Professional Simulation Report)."""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

from fastapi.testclient import TestClient
from pypdf import PdfReader
import pytest

from guangzhu.api import app
from guangzhu.report.pvsyst_report import (
    ASSETS_DIR,
    SIM_MODEL_VERSION,
    _compute_sim_input_fingerprint,
    assert_no_private_path_leak,
    assert_no_pvsyst_visible_text,
    build_pvsyst_report_context,
    get_guangzhu_icon_assets,
    make_pro_report_filename,
    render_pvsyst_report_html,
    render_pvsyst_report_pdf,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_guangzhu_software_icon_and_diagonal_watermark_six_pages():
    icons = get_guangzhu_icon_assets()
    raw_128 = (ASSETS_DIR / "guangzhu-128.png").read_bytes()
    raw_512 = (ASSETS_DIR / "guangzhu-512.png").read_bytes()

    expected_128 = "data:image/png;base64," + base64.b64encode(raw_128).decode("ascii")
    expected_512 = "data:image/png;base64," + base64.b64encode(raw_512).decode("ascii")
    assert icons["icon_128_uri"] == expected_128
    assert icons["icon_512_uri"] == expected_512

    ctx = build_pvsyst_report_context(
        {
            "project_name": "常州高新电子厂房分布式光伏工程",
            "site": {"name": "常州高新区B2厂房", "city": "常州市", "lat": 31.81, "lon": 119.97},
            "system": {"dc_kw": 320.0, "ac_kw": 275.0, "tilt_deg": 12.0, "azimuth_deg": 180.0},
        },
        offline=True,
    )
    assert ctx["meta"]["total_pages"] == 6
    html = render_pvsyst_report_html(ctx)

    # Exact 6 Swiss A4 pages, 6 repeating headers, 6 footers, and P1..P6 quick jumps
    pages = re.findall(r'<section class="pvs-page"[^>]*data-page="(\d+)">', html)
    assert pages == ["1", "2", "3", "4", "5", "6"]
    assert html.count('<header class="pvs-page-header">') == 6
    assert html.count('<footer class="pvs-page-footer">') == 6
    for pg in range(1, 7):
        assert f"Page {pg} of 6" in html
        assert f"window.__jumpGzPage({pg})" in html

    # Diagonal repeating "光筑" software watermark on ALL 6 pages (3x4 = 12 tiles/page = 72 tiles)
    assert html.count('class="pvs-watermark-layer"') == 6
    assert html.count('class="pvs-wm-tile"') == 72
    assert "光筑 · GUANGZHU" in html
    assert "光筑专业报告" in html
    assert ".pvs-wm-logo" in html

    # Software icon appears in all 6 page headers, footers, action bar, watermark CSS, cover badge, and sign-off stamp
    assert html.count(expected_128) >= 8
    assert html.count(expected_512) >= 2
    assert 'class="pvs-cover-badge-icon"' in html
    assert 'class="pvs-signoff-logo"' in html
    assert "@page" in html and "size: A4 portrait" in html
    assert "border-radius: 0" in html
    assert "tabular-nums" in html


def test_zero_pvsyst_visible_text_and_pro_report_filenames():
    assert make_pro_report_filename("常州示范厂房", 2, "pdf") == "光筑专业报告_常州示范厂房_v2.pdf"
    dirty_fn = make_pro_report_filename(r"PVsyst 7.4 Demo C:\Users\secret_user\roof.dxf", 3, "pdf")
    assert dirty_fn.startswith("光筑专业报告_")
    assert dirty_fn.endswith("_v3.pdf")
    assert "pvsyst" not in dirty_fn.lower()
    assert "secret_user" not in dirty_fn.lower()

    # Even when upstream payload injects "PVsyst" in project/site/shading strings, rendered HTML scrubs 100% of it
    ctx = build_pvsyst_report_context(
        {
            "project_name": "PVsyst 8.0 迁移测试厂房项目",
            "site": {
                "name": "PVsyst Industrial Park Roof",
                "city": "苏州市",
                "meteo_source": "PVsyst Meteonorm 8.1 TMY",
                "lat": 31.30,
                "lon": 120.62,
            },
            "system": {
                "dc_kw": 400.0,
                "ac_kw": 350.0,
                "shading_status": "PVsyst 3D Near-Shadings Linear",
            },
        },
        offline=True,
    )
    html = render_pvsyst_report_html(ctx)
    assert_no_pvsyst_visible_text(html)

    # Verify negative check works as expected if "PVsyst" were ever injected into visible text
    with pytest.raises(ValueError):
        assert_no_pvsyst_visible_text("<html><head><title>Bad PVsyst Title</title></head><body>x</body></html>")


def test_six_page_swiss_engineering_sections_and_deep_tables():
    ctx = build_pvsyst_report_context(
        {
            "project_id": "gz-ew-butterfly-01",
            "project_name": "苏州工业园东西向双坡示范项目",
            "site": {"name": "苏州工业园C1屋面", "city": "苏州市", "lat": 31.30, "lon": 120.62, "altitude_m": 12.0},
            "system": {
                "dc_kw": 464.0,
                "ac_kw": 400.0,
                "stc_w": 580.0,
                "module_count": 800,
                "modules_per_string": 20,
                "string_count": 40,
                "tilt_deg": 10.0,
                "azimuth_deg": 90.0,
                "orientation_mode": "east_west",
                "mount_orientation": "landscape",
            },
            "multifactor": {
                "albedo": "white_tpo",
                "pruned_shaded_modules": 6,
                "string_voc_check": {"string_cold_voc_v": 1032.4, "cold_voc_v": 51.62},
                "structural_check": {
                    "fixing_type": "ballast",
                    "added_dead_load_kg_m2": 26.4,
                    "max_roof_load_kg_m2": 45.0,
                    "basic_wind_w0_kn_m2": 0.45,
                    "basic_snow_s0_kn_m2": 0.35,
                    "effective_setback_m": 1.2,
                    "walkway_width_m": 0.8,
                    "load_ok": True,
                    "wind_ok": True,
                },
            },
        },
        offline=True,
    )
    assert ctx["site"]["albedo"] == pytest.approx(0.65)
    assert ctx["orientation"]["mode"] == "east_west"
    assert ctx["pv_array"]["voc_tmin_v"] == pytest.approx(1032.4)
    assert len(ctx["normalized_monthly"]) == 12
    assert len(ctx["loss_sensitivity_ranking"]) == 8
    assert len(ctx["daily_io"]) == 365
    assert len(ctx["power_distribution"]) == 10
    assert len(ctx["hourly_heatmap_12x24"]["ac_kw"]) == 12
    assert all(len(row) == 24 for row in ctx["hourly_heatmap_12x24"]["ac_kw"])
    assert len(ctx["verification"]["national_code_checks"]) == 6
    assert len(ctx["lifecycle"]["yearly_25"]) == 25
    assert len(ctx["lifecycle"]["sensitivity_matrix_3x3"]) == 3

    html = render_pvsyst_report_html(ctx)

    # Page 1: Single-line Schematic + 4 Swiss Parameter Frames + Loss Factors + Executive KPI Strip + Toolbar
    for expected_p1 in (
        "Grid-Connected Single-Line System Schematic",
        "PV SUB-ARRAYS",
        "DC STRINGS",
        "MPPT INVERTER",
        "USER LOAD",
        "UTILITY GRID",
        "Geographical Site &amp; Meteo Boundary",
        ".MET 8760h",
        "Orientation &amp; 3D Near Shadings",
        "α_lim =",
        "PV Array Characteristics",
        ".PAN Spec",
        "γPmp / βVoc",
        "Inverter Characteristics",
        ".OND Spec",
        "η_euro =",
        "Detailed System Loss Factors",
        "window.print()",
        "__downloadStandaloneGzHtml",
        "__cyclePvsLang",
    ):
        assert expected_p1 in html

    # Page 2: Main Results Strip, Dual Monthly Charts, and 13-Column Balances Table
    for expected_p2 in (
        "Normalized Production (per installed kWp)",
        "Lc: Collection Loss",
        "Ls: System Loss",
        "Yf: Produced Useful Energy",
        "Performance Ratio PR",
        "Balances and Main Results (13-Column Engineering Ledger)",
        "GlobHor",
        "DiffHor",
        "T_Amb",
        "WindVel",
        "GlobInc",
        "GlobEff",
        "GlobBak",
        "EArray",
        "E_Grid",
    ):
        assert expected_p2 in html

    # Page 3: Proportional 8760h Branching Loss Diagram + Sensitivity Ranking Table
    for expected_p3 in (
        "Annual 8760h Energy Flow &amp; Branching Loss Diagram",
        "Horizontal global irradiation (GlobHor)",
        "Global incident in collector plane (GlobInc)",
        "3D Near Shadings: irradiance loss",
        "IAM factor on global",
        "Surface soiling loss factor",
        "Bifacial rear gain",
        "Effective irradiation on collectors (GlobEff × Area)",
        "Array nominal energy (at STC efficiency)",
        "PV loss due to low irradiance level",
        "PV loss due to cell temperature",
        "Spectral response correction",
        "LID - First-year light induced degradation",
        "Module &amp; string mismatch",
        "DC array ohmic wiring loss",
        "Array virtual energy at MPP (EArray)",
        "Inverter conversion loss",
        "Available Energy at Inverter Output",
        "Energy injected into utility grid (E_Grid)",
        "Loss &amp; Gain Mechanism Sensitivity Ranking",
    ):
        assert expected_p3 in html

    # Page 4: 7-Season Sky Dome, Daily I/O, Output Power Histogram, 12x24 Matrix & P50/P75/P90/P95
    for expected_p4 in (
        "Iso-Shadings Sky Dome",
        "7-Season Solar Tracks",
        "8h",
        "12h",
        "16h",
        "Daily Input / Output Diagram",
        "System Output Power Distribution",
        "12×24 Hourly Mean AC Output Profile Matrix",
        "P50 (基准期望值)",
        "P75 (稳健评估值)",
        "P90 (银行融资基准)",
        "P95 (极端保守保底)",
    ):
        assert expected_p4 in html

    # Page 5: MPPT Channel Allocation + ΔUdc + 6 National Code Cards + Cable/SPD/Grounding Spec
    for expected_p5 in (
        "Inverter MPPT Channel String Allocation &amp; Voltage Drop Schedule",
        "ΔUdc",
        "6-Dimension National Code Engineering Verification",
        "GB 55001",
        "26.4 / 45.0 kg/m²",
        "GB 50797",
        "GB 50009-2012",
        "IEC 62548",
        "Voc 1032.4/",
        "IEC 61724",
        "剔除 6 块",
        "GB 50016",
        "PV1-F 1×4.0 mm²",
    ):
        assert expected_p5 in html

    # Page 6: Full 25-Row Cashflow Schedule (Y01..Y25), 3x3 Sensitivity Matrix & Official Sign-Off
    for yr in (1, 5, 10, 15, 20, 25):
        assert f"Y{yr:02d} (第{yr:02d}年)" in html
    for expected_p6 in (
        "25-Year Annual Degradation &amp; Cashflow Schedule (Full Y01–Y25 Ledger)",
        "3×3 Tariff × CAPEX IRR / Payback Matrix",
        "编制 · Prepared By",
        "校核 · Checked By",
        "审定 · Approved By",
        "光筑工程仿真核验章",
        "GUANGZHU VERIFIED",
    ):
        assert expected_p6 in html


def test_project_routes_v1_coexistence_and_pdf_watermark_zero_pvsyst(tmp_path: Path):
    client = TestClient(app)

    # 1. Existing V1 report endpoint must remain 100% intact alongside《光筑专业报告》
    r_v1 = client.get("/api/projects/taizhou-cmc-showcase/report-html")
    assert r_v1.status_code == 200
    assert "<html" in r_v1.text.lower()

    # 2. Both new /pro-report-html and legacy alias /pvsyst-report-html return 6-page《光筑专业报告》
    for html_route in (
        "/api/projects/taizhou-cmc-showcase/pro-report-html",
        "/api/projects/taizhou-cmc-showcase/pvsyst-report-html",
    ):
        r_html = client.get(html_route)
        assert r_html.status_code == 200
        assert r_html.headers["content-type"].startswith("text/html")
        assert r_html.text.count('<section class="pvs-page"') == 6
        assert r_html.text.count('class="pvs-watermark-layer"') == 6
        assert "data:image/png;base64," in r_html.text
        assert_no_private_path_leak(r_html.text)
        assert_no_pvsyst_visible_text(r_html.text)

    # 3. Both new /pro-report-pdf and legacy alias /pvsyst-report-pdf return 6-page PDF with 光筑专业报告 filename
    for pdf_route in (
        "/api/projects/taizhou-cmc-showcase/pro-report-pdf",
        "/api/projects/taizhou-cmc-showcase/pvsyst-report-pdf",
    ):
        r_pdf = client.get(pdf_route)
        assert r_pdf.status_code == 200
        assert r_pdf.headers["content-type"] == "application/pdf"
        cd = unquote(r_pdf.headers.get("content-disposition", ""))
        assert "光筑专业报告_" in cd
        assert "pvsyst" not in cd.lower()
        assert r_pdf.content[:5] == b"%PDF-"
        assert len(r_pdf.content) > 15_000
        reader = PdfReader(io.BytesIO(r_pdf.content))
        assert len(reader.pages) == 6
        meta_dump = json.dumps({k: str(v) for k, v in (reader.metadata or {}).items()}, ensure_ascii=False)
        assert "pvsyst" not in meta_dump.lower()
        for idx_p, pg in enumerate(reader.pages, 1):
            txt = pg.extract_text() or ""
            assert "pvsyst" not in txt.lower(), f"Leaked 'PVsyst' in PDF page {idx_p}"

    # 4. Pure-Python ReportLab 6-page fallback when no headless browser is available
    ctx = build_pvsyst_report_context({"project_name": "无浏览器纯Python六页回退核验"}, offline=True)
    fallback_pdf = tmp_path / "fallback-reportlab-6p.pdf"
    render_pvsyst_report_pdf(ctx, fallback_pdf, browsers=[])
    assert fallback_pdf.is_file()
    pdf_bytes = fallback_pdf.read_bytes()
    assert pdf_bytes[:5] == b"%PDF-"
    assert len(pdf_bytes) > 15_000
    fb_reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(fb_reader.pages) == 6
    fb_meta = json.dumps({k: str(v) for k, v in (fb_reader.metadata or {}).items()}, ensure_ascii=False)
    assert "pvsyst" not in fb_meta.lower()
    assert "光筑专业报告" in fb_meta
    for idx_p, pg in enumerate(fb_reader.pages, 1):
        txt = pg.extract_text() or ""
        assert "pvsyst" not in txt.lower(), f"ReportLab page {idx_p} leaked 'PVsyst'"
        assert "光筑" in txt, f"ReportLab page {idx_p} missing 光筑 header/watermark text"


def test_native_export_pdf_auto_open_downloads_and_cached_routes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client = TestClient(app)

    # A. Test-mode export (with X-Guangzhu-Test: 1) skips OS viewer launch while caching PDF & HTML
    export_payload = {
        "project_name": "常州天合智慧园区B区",
        "version": 2,
        "open_native": True,
        "site": {"name": "常州天合B区屋面", "city": "常州市", "lat": 31.81, "lon": 119.97},
        "system": {"dc_kw": 360.0, "ac_kw": 300.0, "tilt_deg": 11.0, "azimuth_deg": 180.0},
    }
    r_exp = client.post(
        "/api/guangzhu/pro-report/export-pdf",
        json=export_payload,
        headers={"X-Guangzhu-Test": "1"},
    )
    assert r_exp.status_code == 200
    exp_data = r_exp.json()
    assert exp_data["ok"] is True
    assert exp_data["pages"] == 6
    assert exp_data["filename"] == "光筑专业报告_常州天合智慧园区B区_v2.pdf"
    assert exp_data["opened_natively"] is False
    assert exp_data["saved_display"] == "Downloads/光筑专业报告_常州天合智慧园区B区_v2.pdf"
    assert_no_pvsyst_visible_text(exp_data["html"])

    # Cached PDF download & HTML preview routes
    r_file = client.get(exp_data["download_url"])
    assert r_file.status_code == 200
    assert r_file.headers["content-type"] == "application/pdf"
    assert len(PdfReader(io.BytesIO(r_file.content)).pages) == 6

    r_html = client.get(exp_data["html_url"])
    assert r_html.status_code == 200
    assert r_html.text.count('<section class="pvs-page"') == 6
    assert_no_pvsyst_visible_text(r_html.text)

    # B. Desktop native export + auto-open path (isolated tmp Downloads + mocked os.startfile)
    fake_home = tmp_path / "isolated_user_home"
    fake_downloads = fake_home / "Downloads"
    fake_downloads.mkdir(parents=True, exist_ok=True)
    started_paths: list[Path] = []

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    monkeypatch.setattr(os, "startfile", lambda p: started_paths.append(Path(p)), raising=False)

    r_native = client.post(
        "/api/guangzhu/pro-report/export-pdf",
        json={**export_payload, "open_native": True, "include_html": False},
    )
    assert r_native.status_code == 200
    nat_data = r_native.json()
    assert nat_data["ok"] is True
    assert nat_data["opened_natively"] is True
    assert "html" not in nat_data
    expected_dl_file = fake_downloads / "光筑专业报告_常州天合智慧园区B区_v2.pdf"
    assert expected_dl_file.is_file()
    assert expected_dl_file.read_bytes()[:5] == b"%PDF-"
    assert started_paths == [expected_dl_file]

    # Also verify POST /api/open with kind == "pro_report_pdf"
    started_paths.clear()
    r_open = client.post("/api/open", json={"kind": "pro_report_pdf", "file_id": nat_data["file_id"]})
    assert r_open.status_code == 200
    assert r_open.json()["ok"] is True
    assert started_paths == [expected_dl_file]


def test_post_pro_report_formats_and_path_sanitization():
    client = TestClient(app)

    dirty_payload = {
        "format": "json",
        "project_id": "nonexistent-live-draft-01",
        "project_name": r"厂房方案 C:\Users\alice_secret\Documents\roof.dxf",
        "site": {
            "name": "/Users/bob_private/Desktop/site.json 示范园区",
            "city": "/home/eve/secret_project 常州市",
            "lat": 31.82,
            "lon": 119.95,
        },
        "system": {"dc_kw": 290.0, "ac_kw": 250.0, "tilt_deg": 14.0, "azimuth_deg": 180.0},
        "agh_account": "account-acct-secret-999",
    }

    for route in ("/api/guangzhu/pro-report", "/api/pvsyst/professional-report"):
        r_json = client.post(route, json=dirty_payload)
        assert r_json.status_code == 200
        data = r_json.json()
        assert data["ok"] is True
        assert data["report_version"] == "2.0"
        assert data["summary"]["e_grid_kwh"] > 100_000
        assert data["filename"].startswith("光筑专业报告_")

        serialized = json.dumps(data, ensure_ascii=False)
        assert "alice_secret" not in serialized
        assert "bob_private" not in serialized
        assert "/home/eve" not in serialized
        assert "account-acct" not in serialized
        assert_no_private_path_leak(data["html"])
        assert_no_pvsyst_visible_text(data["html"])

    # HTML format via POST
    r_html = client.post(
        "/api/guangzhu/pro-report",
        json={**dirty_payload, "format": "html"},
    )
    assert r_html.status_code == 200
    assert r_html.text.count('class="pvs-page-header"') == 6
    assert "alice_secret" not in r_html.text
    assert_no_pvsyst_visible_text(r_html.text)

    # PDF format via POST
    r_pdf = client.post(
        "/api/guangzhu/pro-report",
        json={
            "format": "pdf",
            "project_id": "taizhou-cmc-showcase",
            "version": 1,
        },
    )
    assert r_pdf.status_code == 200
    assert r_pdf.content[:5] == b"%PDF-"
    assert len(PdfReader(io.BytesIO(r_pdf.content)).pages) == 6


def test_frontend_workbench_zero_pvsyst_zero_popups_and_offline_6page():
    # 1. Static source check: zero window.open calls or references anywhere in pvsyst-workbench.js
    wb_src = (REPO_ROOT / "desktop" / "web" / "pvsyst-workbench.js").read_text(encoding="utf-8")
    assert "window.open" not in wb_src

    # 2. Node ESM behavioral verification across ZH & EN and offline 6-page fallback
    js_check = """
import assert from 'node:assert/strict';
import { setLang } from './desktop/web/i18n.js';
import {
  GUANGZHU_ICON_URL,
  GUANGZHU_ICON_DATA_URI,
  makeClientProReportFilename,
  renderPvsystWorkbench,
  pvsystProFoldMarkup,
  openGuangzhuProReportModal,
  exportGuangzhuProReportPdf,
  openPvsystStandardReport,
  openPvsystProfessionalReportV2,
  downloadPvsystProfessionalReportPdf,
  buildPvsystProfessionalReportV2Html,
} from './desktop/web/pvsyst-workbench.js';

function assertZeroVisiblePvsyst(markup, ctxLabel) {
  const noCode = markup
    .replace(/<script\\b[\\s\\S]*?<\\/script>/gi, ' ')
    .replace(/<style\\b[\\s\\S]*?<\\/style>/gi, ' ');
  const vis = noCode.replace(/<[^>]+>/g, ' ');
  assert.ok(!/pvsyst/i.test(vis), `${ctxLabel} leaked visible 'PVsyst': ${vis.match(/.{0,30}pvsyst.{0,30}/i)?.[0]}`);
}

assert.equal(GUANGZHU_ICON_URL, '/assets/guangzhu-128.png');
assert.match(GUANGZHU_ICON_DATA_URI, /^data:image\\/png;base64,iVBOR/);
const fnScrubbed = makeClientProReportFilename('苏州工业园PVsyst项目', 2, 'pdf');
assert.ok(fnScrubbed.startsWith('光筑专业报告_苏州工业园') && fnScrubbed.endsWith('_v2.pdf'));
assert.ok(!/pvsyst/i.test(fnScrubbed));
assert.equal(typeof openGuangzhuProReportModal, 'function');
assert.equal(typeof exportGuangzhuProReportPdf, 'function');
assert.equal(typeof openPvsystStandardReport, 'function');
assert.equal(typeof openPvsystProfessionalReportV2, 'function');
assert.equal(typeof downloadPvsystProfessionalReportPdf, 'function');

setLang('zh');
const wbZh = renderPvsystWorkbench(null, { lat: 31.8, lon: 119.9, dcKw: 260 });
assert.ok(wbZh.includes('导出光筑专业报告'));
assert.ok(wbZh.includes('/assets/guangzhu-128.png'));
assert.ok(wbZh.includes('data-pvsyst-action="export-pvsyst-v2"'));
assert.ok(wbZh.includes('data-pvsyst-action="download-pvsyst-v2-pdf"'));
assert.ok(wbZh.includes('data-pvsyst-action="print-report"'));
assertZeroVisiblePvsyst(wbZh, 'Workbench ZH');
assertZeroVisiblePvsyst(pvsystProFoldMarkup(null, { lat: 31.8, lon: 119.9, dcKw: 260 }), 'Fold ZH');

setLang('en');
const wbEn = renderPvsystWorkbench(null, { lat: 31.8, lon: 119.9, dcKw: 260 });
assert.ok(wbEn.includes('Export Guangzhu Professional Report'));
assertZeroVisiblePvsyst(wbEn, 'Workbench EN');
assertZeroVisiblePvsyst(pvsystProFoldMarkup(null, { lat: 31.8, lon: 119.9, dcKw: 260 }), 'Fold EN');
setLang('zh');

const offlineRes = await openPvsystProfessionalReportV2(null, {
  forceOffline: true,
  noOpen: true,
  projectName: '离线六页报告校验 PVsyst C:\\\\Users\\\\leak\\\\secret',
  dcKw: 300,
});
assert.equal(offlineRes.ok, true);
assert.equal(offlineRes.source, 'client-fallback');
assert.equal((offlineRes.html.match(/<section class="pvs-page"/g) || []).length, 6);
assert.equal((offlineRes.html.match(/class="pvs-watermark-layer"/g) || []).length, 6);
assert.ok(offlineRes.html.includes(GUANGZHU_ICON_DATA_URI));
assert.ok(!offlineRes.html.includes('C:\\\\Users\\\\leak'));
assertZeroVisiblePvsyst(offlineRes.html, 'Offline 6-page HTML');

const pdfFallback = await downloadPvsystProfessionalReportPdf(null, { forceOffline: true, noOpen: true });
assert.equal(pdfFallback.ok, true);
console.log('FRONTEND_GUANGZHU_PRO_REPORT_OK');
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", js_check],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, f"Node ESM check failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "FRONTEND_GUANGZHU_PRO_REPORT_OK" in proc.stdout


def test_saved_3d_projects_and_orientation_mode_aliases_no_http_400():
    """3D design.params.layout aliases and all saved 3D projects render 6-page《光筑专业报告》cleanly."""
    expected_modes = {
        "ew": "east_west",
        "butterfly": "east_west",
        "south": "south_fixed",
        "auto": "south_fixed",
        "roof": "flush_pitched",
        "single_slope": "flush_pitched",
        "double_slope": "flush_pitched",
        "canopy": "elevated_canopy",
    }
    for alias, canonical in expected_modes.items():
        ctx = build_pvsyst_report_context(
            {"project_id": f"alias-{alias}", "version": 1},
            project_result={
                "project": {"id": f"alias-{alias}", "name": f"Layout {alias}", "site": {"lat": 32.45, "lon": 119.92}},
                "design": {"params": {"layout": alias, "tilt_deg": 10.0, "azimuth_deg": 180.0}, "statistics": {"dc_kw": 220.0, "module_count": 380}},
            },
            offline=True,
        )
        assert ctx["orientation"]["mode"] == canonical
        assert ctx["results"]["e_grid_kwh"] > 50_000

    client = TestClient(app)
    proj_dirs = [d.name for d in sorted((REPO_ROOT / "projects").iterdir()) if d.is_dir() and (d / "project.json").is_file()]
    assert len(proj_dirs) >= 5
    for pid in proj_dirs:
        r_html = client.get(f"/api/projects/{pid}/pro-report-html")
        assert r_html.status_code == 200, f"GET pro-report-html failed for {pid}: {r_html.text}"
        assert r_html.text.count('<section class="pvs-page"') == 6
        assert_no_private_path_leak(r_html.text)
        assert_no_pvsyst_visible_text(r_html.text)

    r_ew_pdf = client.get("/api/projects/taizhou-xiangtai-warehouse/pro-report-pdf")
    assert r_ew_pdf.status_code == 200
    assert r_ew_pdf.content[:5] == b"%PDF-"
    assert len(PdfReader(io.BytesIO(r_ew_pdf.content)).pages) == 6


def test_live_satmap_payload_precedence_and_visual_svg_geometry():
    """Live SatMap fields override fallback project_result, and SVGs across Pages 1–6 have exact geometry."""
    client = TestClient(app)

    live_payload = {
        "format": "json",
        "project_id": "taizhou-cmc-showcase",
        "version": 1,
        "site": {
            "name": "泰州医药城智能制造中心二期屋面电站",
            "city": "泰州市",
            "lat": 32.4568,
            "lon": 119.9182,
        },
        "system": {
            "dc_kw": 208.8,
            "ac_kw": 180.0,
            "module_count": 360,
            "string_count": 20,
            "modules_per_string": 18,
            "tilt_deg": 10.0,
            "azimuth_deg": 90.0,
            "orientation_mode": "ew",
            "mount_orientation": "landscape",
            "parapet_height_m": 1.15,
        },
        "electrical": {
            "mppt_rows": [
                {
                    "inverterName": "LIVE-INV #1 (SG110CX)",
                    "mpptName": "MPPT1",
                    "slope": "east",
                    "slopeLabel": "东坡",
                    "stringNames": ["S-LIVE-01", "S-LIVE-02"],
                    "stringCount": 2,
                    "modulesPerString": 18,
                    "totalMpptMods": 36,
                    "vmpHotV": 688.5,
                    "vocColdV": 1018.6,
                    "dcDropPct": 0.84,
                    "status": "正常",
                    "ok": True,
                },
                {
                    "inverterName": "LIVE-INV #1 (SG110CX)",
                    "mpptName": "MPPT2",
                    "slope": "west",
                    "slopeLabel": "西坡",
                    "stringNames": ["S-LIVE-03", "S-LIVE-04"],
                    "stringCount": 2,
                    "modulesPerString": 18,
                    "totalMpptMods": 36,
                    "vmpHotV": 686.2,
                    "vocColdV": 1016.4,
                    "dcDropPct": 0.91,
                    "status": "正常",
                    "ok": True,
                },
            ],
        },
        "multifactor": {
            "fixing_type": "ballast",
            "added_dead_load_kg_m2": 28.6,
            "max_roof_load_kg_m2": 48.0,
            "basic_wind_w0_kn_m2": 0.75,
            "basic_snow_s0_kn_m2": 0.40,
            "effective_setback_m": 1.35,
            "pruned_shaded_count": 9,
            "string_cold_voc_v": 1018.6,
            "load_ok": True,
            "wind_ok": True,
        },
    }

    resp = client.post("/api/guangzhu/pro-report", json=live_payload)
    assert resp.status_code == 200
    body = resp.json()
    ver = body["verification"]
    ctx = body["report_context"]
    html = body["html"]

    assert ctx["orientation"]["mode"] == "east_west"
    assert ver["dead_load_kg_m2"] == pytest.approx(28.6)
    assert ver["max_load_kg_m2"] == pytest.approx(48.0)
    assert ver["wind_w0_kn_m2"] == pytest.approx(0.75)
    assert ver["edge_setback_m"] == pytest.approx(1.35)
    assert ver["pruned_shaded_modules"] == 9
    assert len(ver["mppt_rows"]) == 2
    assert ver["mppt_rows"][0]["unit"] == "LIVE-INV #1 (SG110CX)"
    assert "MPPT1" in ver["mppt_rows"][0]["mppt_used"]
    assert "S-LIVE-01, S-LIVE-02" in ver["mppt_rows"][0]["strings_label"]
    assert ver["mppt_rows"][0]["voc_cold_v"] == pytest.approx(1018.6)
    assert ver["mppt_rows"][0]["dc_drop_pct"] == pytest.approx(0.84)
    assert "28.6 / 48.0 kg/m²" in html
    assert "剔除 9 块" in html
    assert "S-LIVE-01, S-LIVE-02" in html
    assert "0.84%" in html

    # Zero mid-token truncation on Page 1 site / meteo / shading strings
    assert ctx["site"]["name"] in html
    assert ctx["site"]["meteo_source"] in html
    assert ctx["orientation"]["shading_status"] in html

    # SVG viewBoxes & legend placement across Pages 2, 3, 4, and 6
    assert 'y="35.8" font-size="6.3" font-weight="800" fill="#1d4ed8">Annual PR =' in html
    assert 'viewBox="0 0 800 572"' in html
    assert "交流集电线损、升压变损耗及不可用率" in html
    assert 'viewBox="0 0 740 164"' in html
    assert 'viewBox="0 0 356 150"' in html
    assert "25-Year Cumulative Cashflow (万元)" in html
    assert "scroll-margin-top: 54px" in html


def test_playwright_headless_a4_zero_overflow_all_six_pages():
    """Verify in real Chromium/Edge layout engine that all 6 A4 sheets have 0px horizontal/vertical overflow."""
    pw_mod = pytest.importorskip("playwright.sync_api")
    ctx = build_pvsyst_report_context(
        {
            "project_name": "常州高新电子厂房六页零溢出几何校核",
            "site": {"name": "常州高新区B2厂房", "city": "常州市", "lat": 31.81, "lon": 119.97},
            "system": {"dc_kw": 1250.0, "ac_kw": 1000.0, "tilt_deg": 12.0, "azimuth_deg": 180.0},
        },
        offline=True,
    )
    html = render_pvsyst_report_html(ctx)

    with pw_mod.sync_playwright() as p:
        browser = None
        for kwargs in ({"channel": "msedge", "headless": True}, {"headless": True}):
            try:
                browser = p.chromium.launch(**kwargs)
                break
            except Exception:
                continue
        if browser is None:
            pytest.skip("No headless Chromium/Edge binary available for Playwright geometry check")

        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.set_content(html, wait_until="load")
            for media in ("screen", "print"):
                page.emulate_media(media=media)
                metrics = page.evaluate(
                    """() => Array.from(document.querySelectorAll('.pvs-page')).map(el => {
                        const body = el.querySelector('.pvs-page-body');
                        const ftr = el.querySelector('.pvs-page-footer');
                        const kids = body ? Array.from(body.children) : [];
                        const lastKid = kids[kids.length - 1];
                        const lastBottom = lastKid ? lastKid.getBoundingClientRect().bottom : 0;
                        const ftrTop = ftr ? ftr.getBoundingClientRect().top : 0;
                        return {
                            page: el.getAttribute('data-page'),
                            overflowX: Math.max(0, el.scrollWidth - el.clientWidth),
                            overflowY: Math.max(0, el.scrollHeight - el.clientHeight),
                            clearanceToFooter: Math.round(ftrTop - lastBottom),
                        };
                    })"""
                )
                assert len(metrics) == 6
                for m in metrics:
                    assert m["overflowX"] <= 1, f"[{media}] Page {m['page']} horizontal overflow: {m}"
                    assert m["overflowY"] <= 1, f"[{media}] Page {m['page']} vertical overflow: {m}"
                    assert m["clearanceToFooter"] >= 4, f"[{media}] Page {m['page']} body overlaps footer: {m}"
        finally:
            browser.close()



def test_q04_sim_input_fingerprint_reuse_and_invalidation():
    """Q04: Changing ac_kw, lat/lon, soiling_pct, or sub_arrays invalidates stale pvsyst reuse & updates hashes."""
    from guangzhu.pvsyst_engine import simulate_pvsyst

    stale_pvs = simulate_pvsyst(31.81, 119.97, dc_kw=100.0, ac_kw=100.0, tilt_deg=12.0, azimuth_deg=180.0, soiling_pct=2.0, offline=True)
    base = {
        "project_name": "指纹测试",
        "site": {"lat": 31.81, "lon": 119.97},
        "system": {"dc_kw": 100.0, "ac_kw": 100.0, "tilt_deg": 12.0, "azimuth_deg": 180.0},
        "losses": {"soiling_pct": 2.0},
        "pvsyst": stale_pvs,
    }
    ctx_a = build_pvsyst_report_context(base, offline=True)
    fp_a = ctx_a["meta"]["sim_input_fingerprint"]
    sha_a = ctx_a["meta"]["snapshot_sha256"]
    e_a = ctx_a["results"]["e_grid_kwh"]
    assert isinstance(fp_a, str) and len(fp_a) == 64
    assert ctx_a["meta"]["input_sha256"] == fp_a

    # Matching fingerprint stamped on pvsyst snapshot allows deterministic reuse
    sentinel_pvs = {
        **stale_pvs,
        "_sim_input_fingerprint": fp_a,
        "summary": {**stale_pvs["summary"], "e_grid_kwh": 123456.0},
    }
    ctx_reused = build_pvsyst_report_context({**base, "pvsyst": sentinel_pvs}, offline=True)
    assert ctx_reused["meta"]["sim_input_fingerprint"] == fp_a
    assert ctx_reused["results"]["e_grid_kwh"] == pytest.approx(123456.0)

    # Identical inputs produce identical fingerprint and snapshot_sha256
    ctx_a2 = build_pvsyst_report_context(base, offline=True)
    assert ctx_a2["meta"]["sim_input_fingerprint"] == fp_a
    assert ctx_a2["meta"]["snapshot_sha256"] == sha_a

    # 1. Change ac_kw (100 → 10) with stale_pvs attached → must recompute (severe clipping lowers E_Grid!)
    ctx_b = build_pvsyst_report_context(
        {**base, "system": {**base["system"], "ac_kw": 10.0}},
        offline=True,
    )
    assert ctx_b["meta"]["sim_input_fingerprint"] != fp_a
    assert ctx_b["meta"]["snapshot_sha256"] != sha_a
    assert ctx_b["results"]["e_grid_kwh"] < e_a * 0.65

    # 2. Change lat/lon (常州 → 哈尔滨) with stale_pvs attached → must recompute
    ctx_c = build_pvsyst_report_context(
        {**base, "site": {"lat": 45.75, "lon": 126.65}},
        offline=True,
    )
    assert ctx_c["meta"]["sim_input_fingerprint"] != fp_a
    assert ctx_c["meta"]["snapshot_sha256"] != sha_a
    assert ctx_c["results"]["e_grid_kwh"] != e_a

    # 3. Change soiling_pct (2% → 40%) with stale_pvs attached → must recompute
    ctx_d = build_pvsyst_report_context(
        {**base, "losses": {"soiling_pct": 40.0}},
        offline=True,
    )
    assert ctx_d["meta"]["sim_input_fingerprint"] != fp_a
    assert ctx_d["meta"]["snapshot_sha256"] != sha_a
    assert ctx_d["results"]["e_grid_kwh"] < e_a * 0.70

    # 4. Add steep north-slope sub_arrays with stale_pvs attached → must recompute
    ctx_e = build_pvsyst_report_context(
        {
            **base,
            "system": {
                **base["system"],
                "orientation_mode": "multi_plane",
                "sub_arrays": [
                    {"name": "北坡子阵 North", "dc_kw": 100.0, "tilt_deg": 35.0, "azimuth_deg": 0.0},
                ],
            },
        },
        offline=True,
    )
    assert ctx_e["meta"]["sim_input_fingerprint"] != fp_a
    assert ctx_e["meta"]["snapshot_sha256"] != sha_a
    assert ctx_e["results"]["e_grid_kwh"] < e_a * 0.85

    # Verify _compute_sim_input_fingerprint is deterministic
    fp_direct = _compute_sim_input_fingerprint(
        dc_kw=300.0, ac_kw=250.0, lat=31.81, lon=119.97, albedo=0.22,
        tilt_deg=12.0, azimuth_compass=180.0, orientation_mode="south_fixed",
        sub_arrays=None, stc_w=550.0, vmp_stc_v=31.6, voc_stc_v=37.9,
        bifaciality=0.8, gamma_pmax_pct_c=-0.34, beta_voc_pct_c=-0.25,
        euro_eff_pct=98.4, soiling_pct=2.0, iam_b0=0.04, lid_pct=1.0,
        mismatch_pct=1.0, dc_ohmic_pct=1.2, ac_ohmic_pct=0.8,
        near_shading_pct=1.85, uc_w_m2k=29.0, uv_w_m2k_ms=0.0,
        snow_loss_pct=0.0, transformer_loss_pct=0.9, availability_pct=99.2,
        offline=True,
    )
    assert isinstance(fp_direct, str) and len(fp_direct) == 64
    assert SIM_MODEL_VERSION == "gz-pvsyst-sim-v3.2"


def test_q05_cold_vmpp_upper_limit_fail_and_conservation():
    """Q05: 18S with vmp=45V, voc=52V, beta=-0.25%/°C, tmin=-30°C, max_dc=1100V, mppt_max=800V → FAIL."""
    ctx = build_pvsyst_report_context(
        {
            "project_name": "冷态Vmpp超限校核",
            "site": {"lat": 45.75, "lon": 126.65},
            "system": {
                "dc_kw": 145.8,
                "ac_kw": 110.0,
                "modules_per_string": 18,
                "string_count": 9,
                "module_count": 162,
            },
            "module": {
                "stc_w": 900.0,
                "vmp_v": 45.0,
                "voc_v": 52.0,
                "beta_voc_pct_c": -0.25,
                "gamma_pmax_pct_c": -0.30,
                "length_m": 2.4,
                "width_m": 1.2,
            },
            "inverter": {
                "mppt_v_max": 800.0,
                "mppt_v_min": 200.0,
                "max_dc_v": 1100.0,
                "rated_ac_kw": 110.0,
                "mppt_count": 9,
            },
            "multifactor": {
                "extreme_temp_min_c": -30.0,
            },
        },
        offline=True,
    )

    ver = ctx["verification"]
    pva = ctx["pv_array"]

    # voc_tmin_v = 18 * 52 * 1.1375 = 1064.7 V <= 1100 V, yet vmpp_tmin_v = 18 * 45 * 1.1375 = 921.4 V > 800 V
    assert pva["voc_tmin_v"] <= 1100.0
    assert pva["vmpp_tmin_v"] == pytest.approx(921.4, abs=1.0)
    assert pva["vmpp_tmin_v"] > 800.0

    voc_chk = next(c for c in ver["national_code_checks"] if c["id"] == "voltage_envelope")
    assert voc_chk["status"] == "FAIL"
    assert "Voc" in voc_chk["metric"] and "Vmp_cold" in voc_chk["metric"]
    assert "冷态 Vmp=" in voc_chk["detail"]
    assert ver["voc_pass"] is False
    assert ver["all_pass"] is False

    html = render_pvsyst_report_html(ctx)
    assert "RECHECK REQUIRED" in html
    assert "GUANGZHU VERIFIED" not in html


def test_q05_electrical_conservation_and_financial_self_consistency():
    """Q05: Module/MPPT conservation mismatches fail voltage_envelope, and stale financial KPIs are rejected."""
    # A. module_count * stc_w / 1000 != dc_kw
    ctx_mod = build_pvsyst_report_context(
        {
            "project_name": "电气守恒不一致校核",
            "system": {"dc_kw": 200.0, "module_count": 500, "ac_kw": 180.0},
        },
        offline=True,
    )
    ver_mod = ctx_mod["verification"]
    assert len(ver_mod["elec_conservation_warnings"]) >= 1
    assert "module_count" in ver_mod["elec_conservation_warnings"][0]
    voc_chk_mod = next(c for c in ver_mod["national_code_checks"] if c["id"] == "voltage_envelope")
    assert voc_chk_mod["status"] == "FAIL"

    # B. MPPT channel / strings-per-MPPT overflow (1 inv × 1 MPPT × 1 string/MPPT vs 4 strings)
    ctx_mppt = build_pvsyst_report_context(
        {
            "project_name": "MPPT端口超限校核",
            "system": {
                "dc_kw": 39.6,
                "ac_kw": 36.0,
                "module_count": 72,
                "modules_per_string": 18,
                "string_count": 4,
                "inverter_count": 1,
                "mppt_count": 1,
                "strings_per_mppt": 1,
            },
        },
        offline=True,
    )
    ver_mppt = ctx_mppt["verification"]
    assert any("MPPT" in w for w in ver_mppt["elec_conservation_warnings"])
    voc_chk_mppt = next(c for c in ver_mppt["national_code_checks"] if c["id"] == "voltage_envelope")
    assert voc_chk_mppt["status"] == "FAIL"
    assert ver_mppt["mppt_rows"][0]["status"] == "FAIL"

    # C. Stale top-level financial KPIs conflicting with 25-year cashflow table must be rejected
    ctx_fin = build_pvsyst_report_context(
        {
            "project_name": "财务自洽性校核",
            "system": {"dc_kw": 200.0, "ac_kw": 170.0},
            "financial": {
                "capex_cny": 630000.0,
                "self_consumption_ratio": 0.80,
                "tariff_self_rmb": 0.76,
                "tariff_feed_rmb": 0.38,
                "irr_pct": 49.5,
                "payback_years": 1.1,
                "npv_wan": 8888.0,
                "lcoe_rmb_kwh": 0.01,
            },
        },
        offline=True,
    )
    lc = ctx_fin["lifecycle"]
    from guangzhu.satmap_multifactor import solve_irr_and_payback_from_cashflows
    expected_irr, expected_pb = solve_irr_and_payback_from_cashflows(
        lc["capex_wan"], [r["net_cf_wan"] for r in lc["yearly_25"]]
    )
    assert lc["irr_pct"] is not None and lc["irr_pct"] < 35.0
    assert lc["irr_pct"] == pytest.approx(expected_irr, abs=0.05)
    assert lc["payback_yr"] is not None and lc["payback_yr"] > 2.5
    assert lc["payback_yr"] == pytest.approx(expected_pb, abs=0.05)
    assert lc["npv_wan"] < 500.0
    assert lc["lcoe_cny_kwh"] is not None and lc["lcoe_cny_kwh"] > 0.10
    assert lc["lcoe_rmb_kwh"] == lc["lcoe_cny_kwh"]

    # D. Unrecoverable all-loss cashflow with stale positive payback/IRR overrides → must remain None
    ctx_unrec = build_pvsyst_report_context(
        {
            "system": {"dc_kw": 100.0, "ac_kw": 85.0},
            "financial": {
                "self_consumption_ratio": 0.0,
                "tariff_self_rmb": 0.0,
                "tariff_feed_rmb": 0.0,
                "irr_pct": 16.5,
                "payback_years": 5.2,
            },
        },
        offline=True,
    )
    assert ctx_unrec["lifecycle"]["irr_pct"] is None
    assert ctx_unrec["lifecycle"]["payback_yr"] is None


def test_q06_minimal_params_unverified_no_stamp(tmp_path: Path):
    """Q06: Minimal input + walkway_width_m=0.8 → structural/wind/snow/shading UNVERIFIED, all_pass=False, non-red stamp."""
    ctx = build_pvsyst_report_context(
        {
            "project_name": "最小参数UNVERIFIED校核",
            "site": {"lat": 31.81, "lon": 119.97},
            "system": {
                "dc_kw": 320.0,
                "ac_kw": 275.0,
                "tilt_deg": 12.0,
                "azimuth_deg": 180.0,
                "walkway_width_m": 0.8,
            },
        },
        offline=True,
    )

    ver = ctx["verification"]
    checks = {c["id"]: c for c in ver["national_code_checks"]}
    expected_note = "未提供项目实测/结构输入原值，当前仅按估算兜底值展示，待人工复核"

    for cid in ("dead_load", "wind_uplift", "snow_load", "shading_mismatch"):
        assert checks[cid]["status"] == "UNVERIFIED", f"{cid} should be UNVERIFIED on fallback defaults"
        assert checks[cid]["verified_source"] == "default"
        assert expected_note in checks[cid]["detail"]

    assert checks["fire_walkway"]["status"] == "PASS"
    assert checks["fire_walkway"]["verified_source"] == "explicit"
    assert checks["fire_walkway"]["metric"] == "检修主通道 0.80 m · 通道净宽达标"
    assert "仅校核检修主通道净宽 ≥ 0.60 m" in checks["fire_walkway"]["detail"]
    assert "防火分区合规" not in checks["fire_walkway"]["metric"]

    assert ver["all_pass"] is False

    html = render_pvsyst_report_html(ctx)
    assert "GUANGZHU VERIFIED" not in html
    assert "光筑工程仿真核验章" not in html
    assert 'class="pvs-stamp-seal unverified"' in html
    assert "工程复核提示" in html and "RECHECK REQUIRED" in html

    rl_pdf = tmp_path / "minimal-unverified.pdf"
    render_pvsyst_report_pdf(ctx, rl_pdf, browsers=[])
    p6_txt = PdfReader(io.BytesIO(rl_pdf.read_bytes())).pages[5].extract_text() or ""
    assert "GUANGZHU VERIFIED" not in p6_txt
    assert "RECHECK REQUIRED" in p6_txt


def test_q06_full_explicit_params_verified_stamp():
    """Q06: Full explicit structural/wind/snow/shading/walkway params → all PASS → GUANGZHU VERIFIED stamp."""
    ctx = build_pvsyst_report_context(
        {
            "project_name": "全参数核验通过校核",
            "site": {"lat": 31.81, "lon": 119.97},
            "system": {
                "dc_kw": 319.0,
                "stc_w": 580.0,
                "module_count": 550,
                "ac_kw": 275.0,
                "tilt_deg": 12.0,
                "azimuth_deg": 180.0,
                "walkway_width_m": 0.9,
            },
            "losses": {
                "near_shading_loss_pct": 1.5,
            },
            "multifactor": {
                "pruned_shaded_modules": 4,
                "structural_check": {
                    "load_ok": True,
                    "wind_ok": True,
                    "added_dead_load_kg_m2": 14.5,
                    "max_roof_load_kg_m2": 55.0,
                    "basic_wind_w0_kn_m2": 0.40,
                    "basic_snow_s0_kn_m2": 0.25,
                    "effective_setback_m": 1.2,
                    "walkway_width_m": 0.9,
                },
            },
        },
        offline=True,
    )

    ver = ctx["verification"]
    checks = {c["id"]: c for c in ver["national_code_checks"]}

    for cid in ("dead_load", "wind_uplift", "snow_load", "voltage_envelope", "shading_mismatch", "fire_walkway"):
        assert checks[cid]["status"] == "PASS", f"{cid} expected PASS, got {checks[cid]}"

    assert ver["all_pass"] is True

    html = render_pvsyst_report_html(ctx)
    assert 'class="pvs-stamp-seal"' in html
    assert "光筑工程仿真核验章" in html
    assert "GUANGZHU VERIFIED" in html


# ---------------------------------------------------------------------------
# Round 4 Deep Cross-Entry Compatibility, 0-kWp Honesty & Validation Suite
# ---------------------------------------------------------------------------

def test_r4_satmap_3d_linkage_payload_shape_and_hot_vmpp_guard():
    """Round 4: Exact satmap-3d-linkage.js buildProReportPayload shape (including single-module hot_vmpp_v + string_hot_vmpp_v)."""
    payload = {
        "format": "html",
        "project_name": "苏州智造园B2厂房",
        "variant_code": "GZ-PRO-V1",
        "site": {
            "name": "苏州工业园区站址",
            "city": "苏州市",
            "lat": 31.3041,
            "lon": 120.5954,
            "albedo": 0.22,
            "extreme_temp_min_c": -10,
        },
        "system": {
            "dc_kw": 208.8,
            "ac_kw": 180.0,
            "module_count": 360,
            "stc_w": 580,
            "tilt_deg": 12.0,
            "azimuth_deg": 180.0,
            "orientation_mode": "south_fixed",
            "gcr": 0.56,
            "row_pitch_m": 3.45,
            "inverter_count": 2,
            "modules_per_string": 18,
            "string_count": 20,
            "bifaciality": 0.80,
            "albedo": 0.22,
            "mount_orientation": "landscape",
            "rack_type": "clamp",
            "walkway_width_m": 0.90,
            "module": {
                "manufacturer": "LONGi",
                "model": "LR5-72HTD-580M",
                "stc_w": 580,
                "voc_v": 52.2,
                "vmp_v": 44.1,
                "isc_a": 14.2,
                "imp_a": 13.15,
                "temp_coeff_voc_pct": -0.25,
                "temp_coeff_pmax_pct": -0.29,
                "bifaciality": 0.80,
            },
            "inverter": {
                "manufacturer": "Huawei",
                "model": "SUN2000-100KTL-M2",
                "rated_ac_kw": 90.0,
                "max_dc_v": 1100,
                "mppt_min_v": 200,
                "mppt_max_v": 1000,
                "mppt_count": 10,
                "euro_eff_pct": 98.4,
            },
        },
        "losses": {
            "soiling_pct": 2.5,
            "iam_b0": 0.05,
            "lid_pct": 1.0,
            "mismatch_pct": 1.5,
            "dc_ohmic_pct": 1.2,
            "ac_ohmic_pct": 0.8,
            "near_shading_loss_pct": 1.8,
            "uc_w_m2k": 29.0,
            "uv_w_m2k_ms": 0.0,
            "snow_loss_pct": 0.4,
        },
        "multifactor": {
            "orientation_mode": "south_fixed",
            "albedo_preset": "concrete",
            "albedo": 0.22,
            "extreme_temp_min_c": -10,
            # computeStringVocCheck spreads BOTH single-module hot_vmpp_v (~38.4V) and string_hot_vmpp_v (~690.7V)
            "cold_voc_v": 56.77,
            "hot_vmpp_v": 38.37,
            "string_cold_voc_v": 1021.8,
            "string_hot_vmpp_v": 690.7,
            "voc_safe": True,
            # computeMultiFactorStructuralCheck fields
            "fixing_type": "clamp",
            "added_dead_load_kg_m2": 14.5,
            "max_roof_load_kg_m2": 55.0,
            "effective_setback_m": 1.2,
            "load_ok": True,
            "wind_ok": True,
            "snow_ok": True,
            "pruned_shaded_modules": 2,
        },
        "financial": {
            "tariff_self_rmb": 0.82,
            "feed_in_tariff_rmb": 0.39,
            "self_consumption_ratio": 0.85,
            "capex_per_w": 3.10,
        },
    }

    ctx = build_pvsyst_report_context(payload, offline=True)
    assert ctx["pv_array"]["vmpp_60c_v"] == pytest.approx(690.7, abs=0.3)
    assert ctx["pv_array"]["voc_tmin_v"] == pytest.approx(1021.8, abs=0.5)
    assert ctx["pv_array"]["beta_voc_pct_c"] == pytest.approx(-0.25, abs=1e-3)
    assert ctx["pv_array"]["gamma_pmax_pct_c"] == pytest.approx(-0.29, abs=1e-3)
    assert ctx["verification"]["voc_pass"] is True
    checks = {c["id"]: c for c in ctx["verification"]["national_code_checks"]}
    assert checks["voltage_envelope"]["status"] == "PASS"
    assert checks["dead_load"]["status"] == "PASS"
    assert ctx["lifecycle"]["capex_wan"] == pytest.approx(208.8 * 1000.0 * 3.10 / 10000.0, abs=0.05)

    html = render_pvsyst_report_html(ctx)
    assert_no_pvsyst_visible_text(html)

    # Explicit False flags from satmap-3d-linkage.js must report FAIL even without w0/s0
    fail_payload = json.loads(json.dumps(payload))
    fail_payload["multifactor"]["wind_ok"] = False
    fail_payload["multifactor"]["snow_ok"] = False
    fail_ctx = build_pvsyst_report_context(fail_payload, offline=True)
    fail_checks = {c["id"]: c for c in fail_ctx["verification"]["national_code_checks"]}
    assert fail_checks["wind_uplift"]["status"] == "FAIL"
    assert fail_checks["snow_load"]["status"] == "FAIL"
    assert fail_ctx["verification"]["all_pass"] is False


def test_r4_innovation_lab_payload_aliases_zero_and_none_preservation():
    """Round 4: Exact innovation-lab.js exportGuangzhuProReport aliases + explicit 0.0 / None preservation."""
    innov_payload = {
        "format": "html",
        "project_name": "创新方案工坊·东西双坡零碳屋面",
        "variant_name": "INNOV-EW-01",
        "site": {
            "name": "嘉兴平湖示范站",
            "lat": 30.70,
            "lon": 121.02,
            "altitude_m": 0.0,
            "albedo": 0.35,
        },
        "system": {
            "dc_kw": 406.0,
            "ac_kw": 330.0,
            "module_count": 700,
            "stc_w": 580,
            "tilt_deg": 10.0,
            "azimuth_deg": 180.0,
            "orientation_mode": "east_west",
            "bifaciality": 0.80,
            "albedo": 0.35,
            "row_pitch_m": 2.65,
            "gcr": 0.86,
        },
        "losses": {
            "soiling_pct": 2.0,
            "iam_b0": 0.05,
            "lid_pct": 1.0,
            "mismatch_pct": 1.2,
            "dc_ohmic_pct": 1.1,
            "ac_ohmic_pct": 0.7,
            "near_shading_loss_pct": 1.4,
            "uc_w_m2k": 29.0,
            "uv_w_m2k_ms": 0.0,
            "annual_degradation_pct": 0.0,
        },
        "multifactor": {
            "orientation_mode": "east_west",
            "added_load_kg_m2": 14.8,
            "max_roof_load_kg_m2": 35.0,
            "roof_load_safe": True,
        },
        "financial": {
            "capex_wan": 125.86,
            "annual_rev_wan": 32.40,
            "payback_yr": 4.21,
            "irr_pct": 22.9,
            "npv25_wan": 218.5,
            "lcoe_rmb_kwh": 0.238,
        },
    }

    ctx = build_pvsyst_report_context(innov_payload, offline=True)
    assert ctx["meta"]["variant_code"] == "INNOV-EW-01"
    assert ctx["site"]["altitude_m"] == 0.0
    assert ctx["losses"]["annual_degradation_pct"] == 0.0
    assert ctx["verification"]["dead_load_kg_m2"] == pytest.approx(14.8, abs=0.05)
    assert ctx["verification"]["max_load_kg_m2"] == pytest.approx(35.0, abs=0.05)
    assert ctx["verification"]["load_pass"] is True
    checks = {c["id"]: c for c in ctx["verification"]["national_code_checks"]}
    assert checks["dead_load"]["status"] == "PASS"

    lc = ctx["lifecycle"]
    assert lc["yearly_25"][0]["rev_self_wan"] + lc["yearly_25"][0]["rev_feed_wan"] == pytest.approx(32.40, abs=0.05)
    assert lc["payback_yr"] == pytest.approx(4.21, abs=0.25)
    assert lc["irr_pct"] is not None and lc["irr_pct"] > 15.0
    assert lc["npv25_wan"] == lc["npv_wan"] == lc["npv_25_wan"]

    html = render_pvsyst_report_html(ctx)
    assert_no_pvsyst_visible_text(html)

    # Explicit 0.0 load and roof_load_safe=False + npv_25_wan=0.0 preservation
    zero_alias_payload = json.loads(json.dumps(innov_payload))
    zero_alias_payload["multifactor"]["added_load_kg_m2"] = 0.0
    zero_alias_payload["multifactor"]["roof_load_safe"] = False
    zero_alias_payload["financial"] = {
        "capex_wan": 0.0,
        "annual_rev_wan": 0.0,
        "payback_yr": None,
        "irr_pct": None,
        "npv_25_wan": 0.0,
    }
    ctx_z = build_pvsyst_report_context(zero_alias_payload, offline=True)
    assert ctx_z["verification"]["dead_load_kg_m2"] == 0.0
    assert ctx_z["verification"]["load_pass"] is False
    checks_z = {c["id"]: c for c in ctx_z["verification"]["national_code_checks"]}
    assert checks_z["dead_load"]["status"] == "FAIL"
    assert ctx_z["lifecycle"]["capex_wan"] == 0.0
    assert ctx_z["lifecycle"]["payback_yr"] is None
    assert ctx_z["lifecycle"]["irr_pct"] is None


def test_r4_zero_capacity_six_page_honesty_and_recheck_required(tmp_path: Path):
    """Round 4: 0 kWp / 0 modules shows 0 块 / 0 串 / 0 台 across Pages 1, 2, 5 and RECHECK REQUIRED (never PASS)."""
    from pypdf import PdfReader

    zero_payload = {
        "project_name": "零装机空方案诚实性测试",
        "site": {"name": "宁波北仑站", "lat": 29.90, "lon": 121.85},
        "system": {
            "dc_kw": 0.0,
            "ac_kw": 110.0,
            "module_count": 0,
            "stc_w": 580,
            "inverter_count": 1,
            "modules_per_string": 18,
            "string_count": 0,
            "walkway_width_m": 0.9,
        },
        "multifactor": {
            "added_dead_load_kg_m2": 14.5,
            "max_roof_load_kg_m2": 55.0,
            "basic_wind_w0_kn_m2": 0.45,
            "basic_snow_s0_kn_m2": 0.25,
            "load_ok": True,
            "wind_ok": True,
            "snow_ok": True,
            "pruned_shaded_modules": 0,
        },
        "losses": {"near_shading_loss_pct": 0.0},
    }

    ctx = build_pvsyst_report_context(zero_payload, offline=True)
    assert ctx["pv_array"]["dc_kw"] == 0.0
    assert ctx["pv_array"]["module_count"] == 0
    assert ctx["pv_array"]["string_count"] == 0
    assert ctx["pv_array"]["modules_per_string"] == 0
    assert ctx["inverter"]["count"] == 0
    assert ctx["inverter"]["total_ac_kw"] == 0.0
    assert ctx["results"]["e_grid_kwh"] == 0.0
    assert ctx["results"]["self_use_pct"] == 0.0
    assert ctx["hourly_heatmap_12x24"]["max_ac_kw"] == 0.0
    assert ctx["verification"]["all_pass"] is False
    assert all(c["status"] == "UNVERIFIED" for c in ctx["verification"]["national_code_checks"])
    assert ctx["verification"]["mppt_rows"][0]["unit"] == "0 台"
    assert ctx["verification"]["mppt_rows"][0]["config"] == "0 × 0S"

    html = render_pvsyst_report_html(ctx)
    assert_no_pvsyst_visible_text(html)
    assert "GUANGZHU VERIFIED" not in html
    assert "RECHECK REQUIRED" in html

    pages = {
        int(m.group(1)): m.group(2)
        for m in re.finditer(r'<section[^>]*data-page="(\d+)"[^>]*>(.*?)</section>', html, re.S)
    }
    assert len(pages) == 6

    # Page 1 & Page 2 & Page 5 must explicitly display 0 块 / 0 串 / 0 台 and never 1 台 or 18S
    assert "0 块 / 0 串 (0S) / 0 台" in pages[1]
    assert "0 块 / 0 串 / 0 台" in pages[1]
    assert "1 台" not in pages[1]
    assert "18S" not in pages[1]

    assert "0 块 / 0 串 / 0 台" in pages[2]
    assert "余电上网 0.0%" in pages[2]

    assert "Peak 0.0 kW" in pages[4]

    assert "0 块 / 0 串 / 0 台" in pages[5]
    assert "0 × 0S" in pages[5]
    assert "1 台" not in pages[5]
    assert "18S" not in pages[5]

    assert "单瓦 ¥0.00/Wp" in pages[6]
    assert "RECHECK REQUIRED" in pages[6]

    pdf_out = tmp_path / "zero-cap-r4.pdf"
    render_pvsyst_report_pdf(ctx, pdf_out, browsers=[])
    reader = PdfReader(io.BytesIO(pdf_out.read_bytes()))
    assert len(reader.pages) == 6
    p1_pdf = reader.pages[0].extract_text() or ""
    p6_pdf = reader.pages[5].extract_text() or ""
    assert "0 块" in p1_pdf and "0 串" in p1_pdf and "0 台" in p1_pdf
    assert "18S" not in p1_pdf
    assert "RECHECK REQUIRED" in p6_pdf
    assert "GUANGZHU VERIFIED" not in p6_pdf


def test_r4_negative_cashflow_null_irr_payback_and_strict_input_validation():
    """Round 4: Negative-cashflow None IRR/payback honesty + ValueError on negative/NaN/Inf/out-of-range inputs."""
    neg_cf_ctx = build_pvsyst_report_context(
        {
            "project_name": "负现金流诚实性校核",
            "site": {"lat": 31.2, "lon": 121.5},
            "system": {"dc_kw": 200.0, "ac_kw": 170.0, "module_count": 345, "stc_w": 580},
            "financial": {
                "capex_wan": 80.0,
                "annual_rev_wan": 0.0,
                "opex_wan_yr": 5.0,
                "payback_yr": None,
                "irr_pct": None,
            },
        },
        offline=True,
    )
    assert neg_cf_ctx["lifecycle"]["irr_pct"] is None
    assert neg_cf_ctx["lifecycle"]["payback_yr"] is None
    neg_html = render_pvsyst_report_html(neg_cf_ctx)
    assert_no_pvsyst_visible_text(neg_html)
    assert "N/A (不可行)" in neg_html
    assert ">25 年 (未回本)" in neg_html

    invalid_payloads = [
        {"system": {"dc_kw": -10.0}},
        {"system": {"dc_kw": 100.0, "ac_kw": -5.0}},
        {"system": {"module_count": -4}},
        {"system": {"dc_kw": float("nan")}},
        {"system": {"dc_kw": 100.0, "ac_kw": float("inf")}},
        {"system": {"dc_kw": 100.0}, "losses": {"soiling_pct": float("-inf")}},
        {"site": {"lat": 91.2, "lon": 120.0}, "system": {"dc_kw": 50.0}},
        {"site": {"lat": -90.5, "lon": 120.0}, "system": {"dc_kw": 50.0}},
        {"site": {"lat": 31.2, "lon": 180.5}, "system": {"dc_kw": 50.0}},
        {"site": {"lat": 31.2, "lon": -181.0}, "system": {"dc_kw": 50.0}},
    ]
    for bad in invalid_payloads:
        with pytest.raises(ValueError):
            build_pvsyst_report_context(bad, offline=True)

    # Boundary coordinates [-90, 90] and [-180, 180] must succeed cleanly without NaN
    polar_ctx = build_pvsyst_report_context(
        {"site": {"lat": 90.0, "lon": -180.0}, "system": {"dc_kw": 58.0, "module_count": 100, "stc_w": 580}},
        offline=True,
    )
    assert polar_ctx["site"]["lat"] == 90.0
    assert polar_ctx["site"]["lon"] == -180.0
    polar_html = render_pvsyst_report_html(polar_ctx)
    assert_no_pvsyst_visible_text(polar_html)
    scrubbed_polar_html = re.sub(r'data:image/[^"\']+', "DATA_URI", polar_html)
    assert not re.search(r"\bnan\b", scrubbed_polar_html, re.I)

