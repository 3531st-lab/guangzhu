from __future__ import annotations

import math
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from guangzhu.pvsyst_engine import simulate_pvsyst

REPO_ROOT = Path(__file__).resolve().parents[1]


REQUIRED_LOSS_TREE_KEYS = (
    "glob_hor",
    "inc_gain_pct",
    "near_shading_loss_pct",
    "iam_loss_pct",
    "soiling_loss_pct",
    "bifacial_gain_pct",
    "glob_eff",
    "stc_eff_pct",
    "e_nom_kwh",
    "irrad_level_loss_pct",
    "temp_loss_pct",
    "quality_gain_pct",
    "lid_loss_pct",
    "mismatch_loss_pct",
    "dc_ohmic_loss_pct",
    "e_mpp_kwh",
    "inv_eff_loss_pct",
    "inv_clip_loss_pct",
    "ac_ohmic_loss_pct",
    "e_grid_kwh",
)


def _collect_string_values(obj: Any, out: list[str] | None = None) -> list[str]:
    if out is None:
        out = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_string_values(v, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_string_values(item, out)
    return out


def test_pvsyst_orientation_modes_and_east_west_physics() -> None:
    """Verify south_fixed, east_west, flush_pitched, and elevated_canopy physics fidelity."""
    south = simulate_pvsyst(
        lat=32.4852,
        lon=119.8634,
        dc_kw=500.0,
        ac_kw=355.0,  # DC/AC ~ 1.41 to highlight midday clipping vs E-W shoulder broadening
        tilt_deg=15.0,
        azimuth_deg=180.0,
        bifaciality=0.75,
        albedo=0.28,
        shading_loss_pct=3.2,
        orientation_mode="south_fixed",
        offline=True,
    )
    east_west = simulate_pvsyst(
        lat=32.4852,
        lon=119.8634,
        dc_kw=500.0,
        ac_kw=355.0,
        tilt_deg=12.0,
        azimuth_deg=180.0,
        bifaciality=0.75,
        albedo=0.28,
        shading_loss_pct=3.2,
        orientation_mode="east_west",
        offline=True,
    )
    flush_pitched = simulate_pvsyst(
        lat=32.4852,
        lon=119.8634,
        dc_kw=500.0,
        ac_kw=420.0,
        tilt_deg=12.0,
        azimuth_deg=180.0,
        bifaciality=0.75,
        albedo=0.28,
        orientation_mode="flush_pitched",
        offline=True,
    )
    elevated_canopy = simulate_pvsyst(
        lat=32.4852,
        lon=119.8634,
        dc_kw=500.0,
        ac_kw=420.0,
        tilt_deg=12.0,
        azimuth_deg=180.0,
        bifaciality=0.75,
        albedo=0.28,
        orientation_mode="elevated_canopy",
        offline=True,
    )
    south_ref = simulate_pvsyst(
        lat=32.4852,
        lon=119.8634,
        dc_kw=500.0,
        ac_kw=420.0,
        tilt_deg=12.0,
        azimuth_deg=180.0,
        bifaciality=0.75,
        albedo=0.28,
        orientation_mode="south_fixed",
        offline=True,
    )

    # 1. Dual 50% / 50% East (-90° / 90° compass) + West (+90° / 270° compass) planes
    assert east_west["summary"]["orientation_mode"] == "east_west"
    subs = east_west["sub_arrays_summary"]
    assert len(subs) == 2
    assert subs[0]["dc_kw"] == pytest.approx(250.0)
    assert subs[1]["dc_kw"] == pytest.approx(250.0)
    assert {subs[0]["azimuth_deg"], subs[1]["azimuth_deg"]} == {90.0, 270.0}
    assert {subs[0]["pvsyst_azimuth_deg"], subs[1]["pvsyst_azimuth_deg"]} == {-90.0, 90.0}

    # 2. Broader morning & afternoon power shoulders relative to midday peak for East-West
    def _shoulder_to_midday_ratio(sim_res: dict) -> float:
        prof = {int(p["hour"]): float(p["mean_ac_kw"]) for p in sim_res["diurnal_profile_24h"]}
        shoulders = sum(prof[h] for h in (6, 7, 8, 16, 17, 18))
        midday = sum(prof[h] for h in (11, 12, 13))
        return shoulders / max(1e-6, midday)

    assert _shoulder_to_midday_ratio(east_west) > _shoulder_to_midday_ratio(south)

    # 3. Minimal inter-row mutual shading & reduced inverter clipping for East-West
    assert east_west["loss_tree_detail"]["near_shading_loss_pct"] < south["loss_tree_detail"]["near_shading_loss_pct"]
    assert east_west["loss_tree_detail"]["inv_clip_loss_pct"] < south["loss_tree_detail"]["inv_clip_loss_pct"]

    # 4. Thermal & bifacial mount physics
    assert flush_pitched["loss_tree_detail"]["temp_loss_pct"] > south_ref["loss_tree_detail"]["temp_loss_pct"]
    assert south_ref["loss_tree_detail"]["temp_loss_pct"] > elevated_canopy["loss_tree_detail"]["temp_loss_pct"]
    assert flush_pitched["loss_tree_detail"]["bifacial_gain_pct"] < south_ref["loss_tree_detail"]["bifacial_gain_pct"]
    assert south_ref["loss_tree_detail"]["bifacial_gain_pct"] < elevated_canopy["loss_tree_detail"]["bifacial_gain_pct"]

    # 5. Explicit sub_arrays passed with orientation_mode="east_west" must not double-scale shading_loss_pct
    explicit_ew = simulate_pvsyst(
        lat=32.4852,
        lon=119.8634,
        dc_kw=500.0,
        ac_kw=420.0,
        shading_loss_pct=1.8,
        orientation_mode="east_west",
        sub_arrays=[
            {"tilt_deg": 10.0, "azimuth_deg": 90.0, "dc_kw": 250.0},
            {"tilt_deg": 10.0, "azimuth_deg": 270.0, "dc_kw": 250.0},
        ],
        offline=True,
    )
    assert explicit_ew["loss_tree_detail"]["near_shading_loss_pct"] == pytest.approx(1.8, abs=0.05)

    with pytest.raises(ValueError, match="orientation_mode"):
        simulate_pvsyst(lat=32.0, lon=120.0, dc_kw=100.0, orientation_mode="invalid_mode", offline=True)


def test_pvsyst_multifactor_inputs_heatmap_monthly_and_zero_brand_leak() -> None:
    """Verify 12x24 heatmap, monthly wind_ms & glob_bak_kwh_m2, diagnostic series, and 0 'PVsyst' strings."""
    base = simulate_pvsyst(
        lat=32.4852,
        lon=119.8634,
        dc_kw=600.0,
        ac_kw=500.0,
        tilt_deg=18.0,
        azimuth_deg=180.0,
        bifaciality=0.80,
        albedo=0.24,
        soiling_pct=2.5,
        snow_loss_pct=0.0,
        spectral_corr_pct=0.0,
        lid_pct=1.0,
        module_quality_pct=-0.3,
        offline=True,
    )
    monofacial = simulate_pvsyst(
        lat=32.4852,
        lon=119.8634,
        dc_kw=600.0,
        ac_kw=500.0,
        tilt_deg=18.0,
        azimuth_deg=180.0,
        bifaciality=0.0,
        albedo=0.24,
        offline=True,
    )
    high_albedo_spectral = simulate_pvsyst(
        lat=32.4852,
        lon=119.8634,
        dc_kw=600.0,
        ac_kw=500.0,
        tilt_deg=18.0,
        azimuth_deg=180.0,
        bifaciality=0.80,
        albedo=0.62,
        soiling_pct=1.2,
        snow_loss_pct=0.0,
        spectral_corr_pct=0.8,
        lid_pct=0.6,
        module_quality_pct=-1.0,
        offline=True,
    )
    snowy_dirty = simulate_pvsyst(
        lat=32.4852,
        lon=119.8634,
        dc_kw=600.0,
        ac_kw=500.0,
        tilt_deg=18.0,
        azimuth_deg=180.0,
        bifaciality=0.80,
        albedo=0.20,
        soiling_pct=5.5,
        snow_loss_pct=2.8,
        spectral_corr_pct=-0.6,
        lid_pct=2.0,
        module_quality_pct=0.8,
        offline=True,
    )

    assert high_albedo_spectral["summary"]["e_grid_kwh"] > base["summary"]["e_grid_kwh"]
    assert snowy_dirty["summary"]["e_grid_kwh"] < base["summary"]["e_grid_kwh"]

    # 1. 16-stage loss waterfall & 13-column-ready 12-month balances (including wind_ms & glob_bak_kwh_m2)
    assert len(base["waterfall"]) == 16
    assert len(base["monthly_balances"]) == 12
    for m_row in base["monthly_balances"]:
        assert set(m_row.keys()) >= {
            "month",
            "glob_hor_kwh_m2",
            "diff_hor_kwh_m2",
            "t_amb_c",
            "wind_ms",
            "glob_inc_kwh_m2",
            "glob_eff_kwh_m2",
            "glob_bak_kwh_m2",
            "e_array_kwh",
            "e_grid_kwh",
            "yf_kwh_kwp_d",
            "lc_kwh_kwp_d",
            "pr_pct",
        }
        assert 0.3 <= m_row["wind_ms"] <= 15.0
        assert m_row["glob_bak_kwh_m2"] > 0.0
        assert m_row["yf_kwh_kwp_d"] > 0.0
        assert m_row["lc_kwh_kwp_d"] >= 0.0
    assert sum(m["glob_bak_kwh_m2"] for m in base["monthly_balances"]) == pytest.approx(
        base["summary"]["glob_bak_kwh_m2"], abs=0.2
    )
    assert base["summary"]["mean_wind_ms"] > 0.0
    assert all(m["glob_bak_kwh_m2"] == 0.0 for m in monofacial["monthly_balances"])

    # 2. hourly_heatmap_12x24: 12 months × 24 local hours AC kW & POA W/m² matrix
    hm = base["hourly_heatmap_12x24"]
    assert hm["months"] == list(range(1, 13))
    assert hm["hours"] == list(range(24))
    assert len(hm["ac_kw"]) == 12
    assert len(hm["poa_w_m2"]) == 12
    assert len(hm["rows"]) == 12
    for r_ac, r_poa in zip(hm["ac_kw"], hm["poa_w_m2"]):
        assert len(r_ac) == 24
        assert len(r_poa) == 24
        assert r_ac[0] == 0.0 and r_ac[23] == 0.0
        assert r_ac[12] > 50.0
        assert r_poa[12] > 100.0
    assert hm["max_ac_kw"] > 100.0
    assert hm["max_poa_w_m2"] > 200.0

    # 3. daily_io_points, power_distribution & loss_tree_detail
    daily_io = base["daily_io_points"]
    assert len(daily_io) == 365
    assert sum(pt["e_grid_kwh"] for pt in daily_io) == pytest.approx(
        base["loss_tree_detail"]["e_grid_kwh"], abs=3.0
    )
    pdist = base["power_distribution"]
    assert len(pdist) == 10
    assert sum(b["energy_kwh"] for b in pdist) == pytest.approx(
        base["loss_tree_detail"]["e_grid_kwh"], abs=3.0
    )
    lt = base["loss_tree_detail"]
    for key in REQUIRED_LOSS_TREE_KEYS:
        assert key in lt and isinstance(lt[key], (int, float)) and math.isfinite(lt[key])

    # 4. ZERO visible "PVsyst" strings anywhere in returned labels/titles/metadata
    ext_re = re.compile("pv" + "syst", re.IGNORECASE)
    leaked = [s for s in _collect_string_values(base) if ext_re.search(s)]
    assert leaked == [], f"Unexpected external brand string in simulate_pvsyst output: {leaked}"


def test_frontend_holistic_synergy_pro_report_pdf_park_and_i18n() -> None:
    """Verify Guangzhu Professional Report PDF export + dialog modal, zero window.open, zero 'PVsyst', and i18n."""
    node_script = r"""
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { InnovationLabView } from './desktop/web/innovation-lab.js';
import { ParkView, computeParkMultifactorKpis } from './desktop/web/park-view.js';
import { setLang, toPureEnText, toPureZhText, translateHtmlToEn } from './desktop/web/i18n.js';

const EXT_BRAND_RE = new RegExp('pv' + 'syst', 'i');

function stripTags(html) {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&[a-zA-Z0-9#]+;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Ensure neither innovation-lab.js nor park-view.js ever calls window.open
for (const ownedJs of ['desktop/web/innovation-lab.js', 'desktop/web/park-view.js']) {
  const src = fs.readFileSync(ownedJs, 'utf8');
  assert.doesNotMatch(src, /window\.open\s*\(/, `${ownedJs} must never use window.open popups in pywebview`);
}

// Mock localStorage & minimal DOM for <a download> + <dialog> preview verification
const store = new Map();
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
};
globalThis.location = { hash: '#lab' };

const clickedDownloads = [];
const appendedDialogs = new Map();
function makeFakeElement(tag) {
  const attrs = new Map();
  const el = {
    tagName: String(tag).toUpperCase(),
    id: '',
    href: '',
    download: '',
    rel: '',
    open: false,
    style: {},
    innerHTML: '',
    setAttribute(k, v) {
      attrs.set(k, String(v));
      if (k === 'id') this.id = String(v);
      if (k === 'open') this.open = true;
    },
    getAttribute(k) { return attrs.get(k) ?? null; },
    removeAttribute(k) {
      attrs.delete(k);
      if (k === 'open') this.open = false;
    },
    showModal() { this.open = true; },
    close() { this.open = false; },
    click() {
      if (this.tagName === 'A') {
        clickedDownloads.push({ href: this.href, download: this.download });
      }
    },
    remove() {},
    querySelector() { return { src: '', srcdoc: '', onclick: null }; },
    querySelectorAll() { return []; },
  };
  return el;
}
globalThis.document = {
  documentElement: { lang: 'zh-CN' },
  body: {
    appendChild(el) {
      if (el.id) appendedDialogs.set(el.id, el);
      return el;
    },
  },
  getElementById(id) {
    return appendedDialogs.get(id) || null;
  },
  createElement(tag) {
    return makeFakeElement(tag);
  },
};

// 1. InnovationLabView: sync from localStorage, import 3D project, and POST /api/guangzhu/pro-report/export-pdf
store.set('gz.satmap.latestScheme', JSON.stringify({
  project_name: '泰州海陵东西双坡示范屋面',
  dc_kw: 820.4,
  roof_area_m2: 6800,
  annual_kwh: 895000,
  pr_pct: 84.6,
  orientation_mode: 'east_west',
  added_load_kg_m2: 14.2,
  max_roof_load_kg_m2: 25.0,
  tariff_self_rmb: 0.92,
  tariff_feed_in_rmb: 0.391,
}));

const apiCalls = [];
const mockFetch = async (url, init = {}) => {
  apiCalls.push({ url, method: init.method || 'GET', body: init.body ? JSON.parse(init.body) : null });
  if (url === '/api/projects/local-list') {
    return {
      ok: true,
      json: async () => ({
        projects: [
          { id: 'proj-3d-01', name: '三维数字孪生一号厂房', dc_kw: 960.0, annual_kwh: 1084000, pr_pct: 83.9, latest_version: 2 },
        ],
      }),
    };
  }
  if (url === '/api/projects/proj-3d-01/result') {
    return {
      ok: true,
      json: async () => ({
        project: { name: '三维数字孪生一号厂房', price_self_cny_kwh: 0.86 },
        metrics: { dc_kw: 960.0, annual_kwh: 1084000, pr_pct: 83.9 },
        roof: { area_m2: 7900, type: 'metal', max_load_kg_m2: 30.0 },
        structure: { added_load_kg_m2: 18.5, max_load_kg_m2: 30.0 },
        layout: { orientation_mode: 'south_fixed', tilt_deg: 18 },
      }),
    };
  }
  if (url === '/api/guangzhu/pro-report/export-pdf') {
    return {
      ok: true,
      headers: { get: () => 'application/json' },
      json: async () => ({
        ok: true,
        file_id: 'gz-rep-001',
        filename: '光筑专业报告_三维数字孪生一号厂房_v2.pdf',
        saved_display: 'Downloads/光筑专业报告_三维数字孪生一号厂房_v2.pdf',
        download_url: '/api/guangzhu/pro-report/file/gz-rep-001',
        html_url: '/api/guangzhu/pro-report/html/gz-rep-001',
        opened_natively: false,
        pages: 6,
      }),
    };
  }
  if (url === '/api/guangzhu/professional-report') {
    return {
      ok: true,
      headers: { get: () => 'text/html' },
      text: async () => '<!doctype html><html><body><h1>光筑专业报告</h1></body></html>',
    };
  }
  return { ok: false, status: 404 };
};

const lab = new InnovationLabView({ fetchImpl: mockFetch });
const syncedSat = lab.syncFromSatmapLatest();
assert.equal(syncedSat.dcKw, 820.4);
assert.equal(lab.generationProfileMode, 'east_west');
assert.equal(lab.addedLoadKgM2, 14.2);

const lmsEw = lab.computeLoadMatchingAndSensitivity();
assert.equal(lmsEw.orientationMode, 'east_west');
assert.equal(lmsEw.hourly24.length, 24);
assert.equal(lmsEw.sensitivityGrid.length, 3);
assert.equal(lmsEw.sensitivityGrid[0].cells.length, 3);

// Import from 3D project
const synced3d = await lab.importFrom3dProject('proj-3d-01');
assert.equal(synced3d.dcKw, 960.0);
assert.equal(synced3d.source, '3d-project');

// Export 《光筑专业报告》 PDF via POST /api/guangzhu/pro-report/export-pdf + <a download> fallback
const rep = await lab.exportGuangzhuProReport({ previewOnly: false, openNative: true });
assert.equal(rep.ok, true);
assert.equal(rep.download_url, '/api/guangzhu/pro-report/file/gz-rep-001');
assert.doesNotMatch(rep.html || '', EXT_BRAND_RE);
const postCall = apiCalls.find((c) => c.url === '/api/guangzhu/pro-report/export-pdf' && c.method === 'POST');
assert.ok(postCall, 'Expected POST /api/guangzhu/pro-report/export-pdf');
assert.equal(postCall.body.open_native, true);
assert.equal(postCall.body.branding.report_title, '光筑专业报告');
assert.equal(postCall.body.branding.icon_url, '/assets/guangzhu-128.png');
assert.equal(clickedDownloads.length, 1);
assert.equal(clickedDownloads[0].href, '/api/guangzhu/pro-report/file/gz-rep-001');

// In-app <dialog> preview modal in #lab
const prevRes = await lab.exportGuangzhuProReport({ previewOnly: true, openNative: false });
assert.equal(prevRes.ok, true);
assert.equal(prevRes.preview, true);
assert.equal(appendedDialogs.get('gz-lab-pro-report-modal')?.open, true);
assert.doesNotMatch(appendedDialogs.get('gz-lab-pro-report-modal')?.innerHTML || '', EXT_BRAND_RE);

// Bilingual zero-leak & zero-PVsyst check across all 3 #lab tabs
for (const tab of ['pareto', 'bess-carbon', 'benchmark']) {
  lab.activeTab = tab;
  setLang('en');
  const htmlEn = lab.html();
  assert.match(htmlEn, /data-lab-sync-bar="1"/);
  assert.match(htmlEn, /data-lab-action="export-pro-report"/);
  assert.match(htmlEn, /Export Guangzhu Professional Report \(PDF\)/);
  assert.match(htmlEn, /\/assets\/guangzhu-128\.png/);
  const textEn = stripTags(htmlEn);
  assert.equal(textEn.match(/[\u4e00-\u9fff]+/g), null, `Unexpected CJK in #lab (${tab}) EN mode`);
  assert.doesNotMatch(textEn, EXT_BRAND_RE, `Unexpected external brand in #lab (${tab}) EN mode`);

  setLang('zh');
  const htmlZh = lab.html();
  assert.match(htmlZh, /同步当前卫星\/三维方案数据/);
  assert.match(htmlZh, /导出光筑专业报告 \(PDF\)/);
  assert.match(htmlZh, /预览光筑专业报告/);
  const rawZhText = stripTags(htmlZh);
  assert.doesNotMatch(rawZhText, EXT_BRAND_RE, `Unexpected external brand in #lab (${tab}) ZH mode`);
  const pureZhText = toPureZhText(rawZhText);
  assert.equal(pureZhText.match(/[A-Za-z]+/g), null, `Unexpected ASCII in #lab (${tab}) ZH mode: ${JSON.stringify(pureZhText.match(/[A-Za-z]+/g))}`);
}

// 2. ParkView: multi-factor KPIs + 《光筑专业报告》 PDF export & preview modal + 0 external brand
const park = new ParkView({
  api: async () => ({}),
  fetchImpl: mockFetch,
  roofs: [],
  queue: { id: 'park-01', queue: null, item: null, load: async () => {} },
});
park.id = 'park-01';
park.parks = [{ id: 'park-01', name: '泰州零碳示范工业园' }];
park.current = {
  park: {
    id: 'park-01',
    name: '泰州零碳示范工业园',
    transformer_kva: 2500,
    grid_kw: 2000,
    budget_cny: 4200000,
    buildings: [
      { template: 'b1', x_m: 0, y_m: 0, rotation_deg: 0 },
      { template: 'b2', x_m: 85, y_m: 0, rotation_deg: 0 },
    ],
  },
  data: {
    all: { dc_kw: 620.5, annual_kwh: 698000, capex_cny: 1985000, payback_years: 3.9, co2_t: 398.1, count: 1 },
    phase1: { dc_kw: 620.5 },
    inverter_count: 6,
    rated_ac_kw: 520,
    risks: [{ label: '变压器容量上限', limit: 2000, excess: -1480 }],
    buildings: [
      {
        template: 'b1',
        name: '一号冲压车间',
        rotation_deg: 0,
        roof: { type: 'metal', height_m: 11, area_m2: 4200 },
        result: { project_id: 'proj-b1', version: 2, dc_kw: 620.5, annual_kwh: 698000, pr_pct: 84.2, capex_cny: 1985000, payback_years: 3.9, park_phase: 1 },
      },
      {
        template: 'b2',
        name: '二号恒温立体库',
        rotation_deg: 0,
        roof: { type: 'flat', height_m: 14, area_m2: 3600 },
        result: null,
      },
    ],
  },
  svg: '<svg viewBox="0 0 100 100"></svg>',
  queue: null,
};
const kpis = computeParkMultifactorKpis(park.current, null);
assert.equal(kpis.totalDcKwp, 620.5);
assert.ok(kpis.weightedPrPct > 80 && kpis.weightedPrPct < 90);
assert.ok(kpis.selfConsumptionSynergyPct > 70);
assert.ok(kpis.annualCo2Ton > 300);
assert.equal(kpis.roofLoadSafety.totalCount, 2);
assert.equal(kpis.roofLoadSafety.safeCount, 2);

setLang('zh');
const parkHtmlZh = park.html();
assert.match(parkHtmlZh, /data-park-multifactor-kpis="1"/);
assert.match(parkHtmlZh, /在卫星排布中深化/);
assert.match(parkHtmlZh, /导出光筑专业报告 \(PDF\)/);
assert.match(parkHtmlZh, />光筑专业报告</);
assert.doesNotMatch(parkHtmlZh, /target="_blank"/);
assert.doesNotMatch(stripTags(parkHtmlZh), EXT_BRAND_RE);

const parkExportRes = await park.exportBuildingProReport('proj-b1', 2, '一号冲压车间', { previewOnly: false, openNative: true });
assert.equal(parkExportRes.ok, true);
const parkPreviewRes = await park.exportBuildingProReport('proj-b1', 2, '一号冲压车间', { previewOnly: true, openNative: false });
assert.equal(parkPreviewRes.ok, true);
assert.equal(appendedDialogs.get('gz-park-pro-report-modal')?.open, true);

setLang('en');
const parkHtmlEn = translateHtmlToEn(park.html());
const parkTextEn = stripTags(parkHtmlEn);
assert.equal(parkTextEn.match(/[\u4e00-\u9fff]+/g), null, 'Expected 0 CJK chars in ParkView EN translation');
assert.doesNotMatch(parkTextEn, EXT_BRAND_RE, 'Expected 0 external brand tokens in ParkView EN translation');
assert.match(parkTextEn, /Export Guangzhu Professional Report \(PDF\)/);
assert.match(parkTextEn, /Guangzhu Professional Report/);
assert.doesNotMatch(parkHtmlEn, /DeleteCampus|3DShading|Campus\s+Campus/);
const parkBtnMatches = [...parkHtmlEn.matchAll(/<button\b[^>]*>([\s\S]*?)<\/button>/gi)];
assert.ok(parkBtnMatches.length >= 13, `Expected >=13 buttons in ParkView, got ${parkBtnMatches.length}`);
for (const m of parkBtnMatches) {
  const btnText = stripTags(m[1]);
  assert.match(btnText, /[A-Za-z0-9]/, `Blank button in ParkView EN mode: ${m[0]}`);
}

// 3. i18n.js: Guangzhu Pro Report, streamlined #satmap workflow, delivery bundle, health check & zero external brand
setLang('en');
const requiredPhrases = [
  ['光筑专业报告', /^Guangzhu Professional Report$/],
  ['导出光筑专业报告 (PDF)', /^Export Guangzhu Professional Report \(PDF\)$/],
  ['在线预览光筑专业报告', /^Preview Guangzhu Professional Report Online$/],
  ['1. 选址与圈屋顶', /^1\. Site & Roof Outline$/],
  ['5. 图纸与光筑报告', /^5\. CAD & Guangzhu Report$/],
  ['当前操作向导', /^Guided Workflow$/],
  ['④ 配串与导出光筑专业报告', /^④ Stringing & Guangzhu Report$/],
  ['③ 一键导出全套工程交付包 & 同步三维设计', /Export Full Engineering Delivery Bundle & Sync 3D Design/],
  ['光筑工程交付包', /^Guangzhu Engineering Delivery Bundle$/],
  ['8项出图前工程合规自检卡', /^8-Item Pre-Delivery Engineering Compliance Checklist$/],
  ['同步当前卫星/三维方案数据', /Sync Active Satellite \/ 3D Scheme Data/],
  ['东西向双坡蝴蝶阵', /East-West Butterfly Array/],
  ['彩钢瓦免打孔夹具', /Standing-Seam Non-Penetrating Clamp/],
  ['混凝土压块配重', /Concrete Ballast Mounting/],
  ['屋面静荷载上限', /Roof Dead-Load Limit/],
  ['台风风区与边角抗风揭退距', /Typhoon Wind Zone & Perimeter Uplift Setback/],
  ['极端低温开路电压校核', /Extreme Cold Open-Circuit Voc Check/],
  ['障碍物阴影剔除', /Obstacle Shadow Pruning/],
  ['按原始坐标摆放', /^Reset Coordinates$/],
  ['🏢 一键同步邻楼3D遮挡', /Sync Neighbor 3D Shading/],
  ['删除园区', /^Delete Campus$/],
  ['加入厂房', /^Add Building$/],
  ['园区 3D 全景数字孪生沙盘 · 共 4 栋厂房（已出方案 2 栋 / 合计 1280 块光伏板）· 按住厂房旋转 / 按住地面或右键滑动平移 / 滚轮指哪缩哪', /Campus 3D Digital Twin · 4 Buildings \(2 Designed \/ 1280 PV Modules\)/],
  ['太阳时 06-21 14:30 (高度角 62.4° / 方位 248.1°)', /Solar Time 06-21 14:30 \(Alt 62\.4° \/ Az 248\.1°\)/],
  ['阵列排布参数 (2×9单元)', /^Array Layout Parameters \(2×9 Unit\)$/],
];
for (const [zh, enRegex] of requiredPhrases) {
  const en = toPureEnText(zh);
  assert.match(en, enRegex, `Expected "${zh}" -> ${enRegex}, got "${en}"`);
  assert.equal(en.match(/[\u4e00-\u9fff]+/g), null);
  assert.doesNotMatch(en, EXT_BRAND_RE);
  const pureZh = toPureZhText(zh);
  assert.equal(pureZh.match(/[A-Za-z]+/g), null, `Expected pure ZH for "${zh}", got "${pureZh}"`);
  assert.doesNotMatch(pureZh, EXT_BRAND_RE);
}

// Legacy brand scrubbing guarantee: even if legacy strings enter i18n, 0 occurrences survive in ZH or EN
const legacyInputs = [
  '导出 ' + 'PV' + 'syst 专业仿真报告 (V2)',
  'PV' + 'syst 7.x 能量平衡表',
  'CAD LAYER: PV_' + 'PV' + 'SYST_DIAGRAM',
];
for (const rawLegacy of legacyInputs) {
  assert.doesNotMatch(toPureEnText(rawLegacy), EXT_BRAND_RE);
  assert.doesNotMatch(toPureZhText(rawLegacy), EXT_BRAND_RE);
}

// Guard against blank EN tag labels across #park, #satmap, #pvsyst, and #lab sources
for (const relPath of [
  'desktop/web/park-view.js',
  'desktop/web/park-scene-3d.js',
  'desktop/web/satmap-view.js',
  'desktop/web/satmap-3d-linkage.js',
  'desktop/web/pvsyst-workbench.js',
  'desktop/web/innovation-lab.js',
]) {
  const src = fs.readFileSync(relPath, 'utf8');
  for (const m of src.matchAll(/>([^<${]*[\u4e00-\u9fff][^<${]*)</g)) {
    const raw = m[1].trim();
    if (!raw) continue;
    const en = toPureEnText(raw).trim();
    assert.match(en, /[A-Za-z0-9]/, `Blank EN translation in ${relPath} for "${raw}" -> "${en}"`);
    assert.equal(en.match(/[\u4e00-\u9fff]+/g), null, `Residual CJK in ${relPath} for "${raw}" -> "${en}"`);
    assert.doesNotMatch(en, EXT_BRAND_RE, `External brand leak in ${relPath} for "${raw}" -> "${en}"`);
  }
}

console.log('ALL_HOLISTIC_JS_CHECKS_PASSED');
"""
    proc = subprocess.run(
        ["node", "--input-type=module", "-e", node_script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, f"Node holistic check failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "ALL_HOLISTIC_JS_CHECKS_PASSED" in proc.stdout
