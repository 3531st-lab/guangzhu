import test from 'node:test';
import assert from 'node:assert/strict';

import {
  SAT_MODULE_CATALOG,
  SAT_INVERTER_CATALOG,
  SatMapView,
} from '../../desktop/web/satmap-view.js';
import {
  SATMAP_LATEST_STORAGE_KEY,
  finiteNum,
  finiteOrNull,
  computeColdVocAndStringSafety,
  computeMultiFactorStructuralCheck,
  computeClientEngineeringHealthCheck,
  buildClientPvsystV2ReportHtml,
  buildProReportPayload,
  exportSatmapDeliveryBundle,
  runClientMultiFactorOptimization,
  requestMultiFactorOptimization,
  applyMultiFactorSchemeToView,
  persistLatestSatmapScheme,
  fetch3DCatalog,
} from '../../desktop/web/satmap-3d-linkage.js';
import { enrichModuleSpec, computeStringSizingAndCables } from '../../desktop/web/pro-engineering-core.js';
import { InnovationLabView } from '../../desktop/web/innovation-lab.js';
import { buildPvsystV2RequestPayload, pvsystProFoldMarkup } from '../../desktop/web/pvsyst-workbench.js';
import { setLang, getLang } from '../../desktop/web/i18n.js';

function createMemoryStorage() {
  const store = new Map();
  return {
    getItem(k) {
      return store.has(k) ? store.get(k) : null;
    },
    setItem(k, v) {
      store.set(k, String(v));
    },
    removeItem(k) {
      store.delete(k);
    },
    clear() {
      store.clear();
    },
  };
}

function stripTags(html) {
  return String(html || '')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

test('R4-UI-01: finiteNum & finiteOrNull reject null/blank/boolean/object while preserving explicit 0 and Cold Vmpp ceiling', async () => {
  // 1. finiteNum & finiteOrNull coercion guards
  assert.equal(finiteNum(null, 99), 99);
  assert.equal(finiteNum(undefined, 99), 99);
  assert.equal(finiteNum('', 99), 99);
  assert.equal(finiteNum('   ', 99), 99);
  assert.equal(finiteNum(true, 99), 99);
  assert.equal(finiteNum(false, 99), 99);
  assert.equal(finiteNum([], 99), 99);
  assert.equal(finiteNum({}, 99), 99);
  assert.equal(finiteNum(Number.NaN, 99), 99);
  assert.equal(finiteNum(Number.POSITIVE_INFINITY, 99), 99);
  assert.equal(finiteNum(0, 99), 0);
  assert.equal(finiteNum('0', 99), 0);
  assert.equal(finiteNum(' -12.5 ', 99), -12.5);

  assert.equal(finiteOrNull(null), null);
  assert.equal(finiteOrNull(undefined), null);
  assert.equal(finiteOrNull(''), null);
  assert.equal(finiteOrNull('   '), null);
  assert.equal(finiteOrNull(true), null);
  assert.equal(finiteOrNull(false), null);
  assert.equal(finiteOrNull([]), null);
  assert.equal(finiteOrNull(0), 0);
  assert.equal(finiteOrNull('0'), 0);

  // 2. Catalog beta_voc_pct_c / gamma_pmax_pct_c & cold Vmpp <= mppt_v_max ceiling
  const mod580 = SAT_MODULE_CATALOG.find((m) => m.id === 'jinko-jkm580n-72hl4-bdv') || SAT_MODULE_CATALOG[0];
  const inv800Mppt = {
    id: 'inv-mppt-800',
    rated_ac_kw: 50,
    max_dc_v: 1100,
    mppt_v_min: 200,
    mppt_v_max: 800,
    mppt_count: 4,
    strings_per_mppt: 2,
  };
  const coldCheck18 = computeColdVocAndStringSafety(mod580, inv800Mppt, { extremeTempMinC: -15 }, 18);
  assert.equal(coldCheck18.beta_voc_pct_c, mod580.beta_voc_pct_c);
  assert.equal(coldCheck18.gamma_pmax_pct_c, mod580.gamma_pmax_pct_c);
  assert.ok(coldCheck18.string_cold_voc_v <= 1100, 'Cold Voc is still <= 1100V');
  assert.ok(coldCheck18.string_cold_vmpp_v > 800, `Expected 18S cold Vmpp > 800V, got ${coldCheck18.string_cold_vmpp_v}`);
  assert.equal(coldCheck18.safe, false, '18S exceeding 800V MPPT ceiling must return safe === false');
  assert.ok(coldCheck18.max_series_safe < 18, `Expected max_series_safe < 18, got ${coldCheck18.max_series_safe}`);

  // Also verify SatMapView.computeElectricalAllocation runs cold check even when extremeTempMinC >= -10 (e.g. -5C)
  const sv = new SatMapView(async () => ({}), () => {});
  await sv.runAiDetectRoof();
  sv.layoutModules({ quiet: true });
  sv.mfState.extremeTempMinC = -5;
  sv.computeElectricalAllocation();
  assert.ok(sv.summary.coldVocV > 0 || sv.electricalSizing, 'Electrical allocation evaluated at -5C');
});

test('R4-UI-02: computeMultiFactorStructuralCheck recommended_edge_setback_m & honest Health Check on 0/null/deficit', async () => {
  // 1. Typhoon wind uplift setback deficit must NOT pass wind_ok via auto-inflated effective_setback_m
  const st = computeMultiFactorStructuralCheck({
    roofType: 'flat',
    orientationMode: 'south_fixed',
    rackRows: '2P',
    tiltDeg: 15,
    buildingHeightM: 12,
    edgeSetbackM: 0.8,
    mfParams: { basicWindW0KnM2: 0.85, fixingType: 'ballast' },
  });
  assert.equal(st.actual_setback_m, 0.8);
  assert.ok(st.recommended_edge_setback_m > 0.8, `Expected recommended_edge_setback_m > 0.8, got ${st.recommended_edge_setback_m}`);
  assert.equal(st.recommended_edge_setback_m, st.min_required_setback_m);
  assert.equal(st.wind_ok, false, '0.8m setback in w0=0.85 typhoon zone must have wind_ok === false');
  assert.equal(st.all_pass, false);

  // 2. computeClientEngineeringHealthCheck on a 0-module / typhoon setback deficit / missing cable drop / null-IRR view
  const sv = new SatMapView(async () => ({}), () => {});
  await sv.runAiDetectRoof();
  sv.hasLaidOut = true;
  sv.modules = [];
  sv.strings = [];
  sv.edgeSetbackM = 0.8;
  sv.mfState.basicWindW0KnM2 = 0.85;
  sv.electricalSizing = null;
  sv.summary = {
    ...sv.summary,
    moduleCount: 0,
    dcKw: 0,
    acKw: 0,
    dcAcRatio: 0,
    stringCount: 0,
    inverterCount: 0,
    annualKwh: 0,
    irrPct: null,
    paybackYears: null,
  };

  const hc = computeClientEngineeringHealthCheck(sv);
  assert.equal(hc.passed, false);
  assert.equal(hc.ready_for_delivery, false);
  const byCode = Object.fromEntries(hc.items.map((it) => [it.code, it]));
  assert.equal(byCode['CHK-01'].status, 'fail');
  assert.equal(byCode['CHK-02'].status, 'fail');
  assert.notEqual(byCode['CHK-05'].status, 'pass', 'Typhoon setback deficit must not pass CHK-05');
  assert.equal(byCode['CHK-06'].status, 'fail');
  assert.equal(byCode['CHK-08'].status, 'fail');

  // Ensure zero fabricated fallback numbers (1.18, 14.5, 5.6, 0.85%) in display strings
  const joinedZh = hc.items.map((i) => i.display_zh).join(' | ');
  const joinedEn = hc.items.map((i) => i.display_en).join(' | ');
  assert.ok(!joinedZh.includes('1.18'), `Unexpected fabricated 1.18 in ZH: ${joinedZh}`);
  assert.ok(!joinedZh.includes('14.5%'), `Unexpected fabricated 14.5% in ZH: ${joinedZh}`);
  assert.ok(!joinedZh.includes('5.6 年'), `Unexpected fabricated 5.6 yr in ZH: ${joinedZh}`);
  assert.ok(!/[\u4e00-\u9fff]/.test(joinedEn), `English health check display leaked CJK: ${joinedEn}`);
});

test('R4-UI-03: Offline fallback reports display OFFLINE UNVERIFIED PREVIEW, N/A for null KPIs, zero PVsyst, and zero-module guards', async () => {
  let layoutCallCount = 0;
  const sv = new SatMapView(async () => {
    throw new Error('backend offline');
  }, () => {});
  await sv.runAiDetectRoof();
  sv.hasLaidOut = true;
  sv.modules = [];
  sv.strings = [];
  sv.summary = {
    ...sv.summary,
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
    npv25Wan: null,
  };
  const origLayout = sv.layoutModules.bind(sv);
  sv.layoutModules = (...args) => {
    layoutCallCount += 1;
    return origLayout(...args);
  };

  // 1. buildProReportPayload & exportSatmapDeliveryBundle must NOT re-run layoutModules when hasLaidOut === true & modules.length === 0
  const payload = buildProReportPayload(sv, { openNative: false });
  assert.equal(layoutCallCount, 0);
  assert.equal(payload.system.module_count, 0);
  assert.equal(payload.system.dc_kw, 0);
  assert.equal(payload.system.string_count, 0);
  assert.equal(payload.system.inverter_count, 0);
  assert.equal(payload.financial.irr_pct, null);
  assert.equal(payload.financial.payback_years, null);

  await exportSatmapDeliveryBundle(sv, { syncTo3D: false, openFolder: false });
  assert.equal(layoutCallCount, 0, 'exportSatmapDeliveryBundle must not auto-layout cleared 0-module roof');
  assert.equal(sv.modules.length, 0);

  // 2. satmap-3d-linkage.js offline fallback report HTML
  const satOfflineHtml = buildClientPvsystV2ReportHtml(payload);
  assert.ok(satOfflineHtml.includes('OFFLINE UNVERIFIED PREVIEW'));
  assert.ok(satOfflineHtml.includes('N/A（未核验/不适用）'));
  assert.ok(!/pvsyst/i.test(stripTags(satOfflineHtml)), 'satOfflineHtml must contain zero visible PVsyst text');

  // 3. innovation-lab.js offline fallback report HTML
  const lab = new InnovationLabView({ dcKw: 0, moduleCount: 0, annualKwh: 0 });
  const labOfflineHtml = lab.buildOfflineFallbackReportHtml(
    { projectName: '离线空方案测试', address: '泰州海陵' },
    { capKwp: 0, moduleCount: 0, prPct: 0, annualMwh: 0, specificYieldH: 0, irrPct: null, paybackYr: null, lcoeRmbPerKwh: null, npv25Wan: null },
    { bessPowerKw: 0, bessCapKwh: 0, selfUseBeforePct: 0, selfUseAfterPct: 0 },
    { roofLoadSafe: false }
  );
  assert.ok(labOfflineHtml.includes('OFFLINE UNVERIFIED PREVIEW'));
  assert.ok(labOfflineHtml.includes('N/A（未核验/不适用）'));
  assert.ok(!/pvsyst/i.test(stripTags(labOfflineHtml)), 'labOfflineHtml must contain zero visible PVsyst text');
});

test('R4-UI-04: Multifactor forwarding, 0-load / tiny-roof / discount-rate / cold-Vmpp / MPPT-port client fallback, and Lab project isolation + ac_kw fix', async () => {
  const prevStorage = globalThis.localStorage;
  const memStorage = createMemoryStorage();
  globalThis.localStorage = memStorage;
  const prevLang = getLang();

  try {
    // 1. requestMultiFactorOptimization forwards annual_load_kwh: 0, discount_rate_pct, modules_per_string, and inverter_spec
    let capturedOptReq = null;
    const sv = new SatMapView(
      async (ep, body) => {
        if (ep === 'satmap/optimize-multifactor') {
          capturedOptReq = body;
        }
        throw new Error('force client fallback');
      },
      () => {}
    );
    await sv.runAiDetectRoof();
    sv.modulesPerString = 16;
    const optZeroLoad = await requestMultiFactorOptimization(sv, {
      annual_load_kwh: 0,
      discount_rate_pct: 8.5,
      modules_per_string: 16,
    });
    assert.ok(capturedOptReq, 'Expected satmap/optimize-multifactor to be called');
    assert.equal(capturedOptReq.annual_load_kwh, 0);
    assert.equal(capturedOptReq.discount_rate_pct, 8.5);
    assert.equal(capturedOptReq.modules_per_string, 16);
    assert.equal(capturedOptReq.financial_params.annual_load_kwh, 0);
    assert.ok(capturedOptReq.inverter_spec && capturedOptReq.inverter_spec.mppt_v_max > 0);
    assert.equal(optZeroLoad.source, 'client_physics');
    for (const s of optZeroLoad.schemes) {
      assert.equal(s.self_use_pct, 0, `0 annual load must yield 0% self-use on ${s.id}`);
      assert.equal(s.self_use_kwh, 0);
    }

    // 2. Discount rate sensitivity (4% vs 12%) produces distinct npv_25_wan; non-positive cashflow gives null IRR/payback
    const optDiscLow = runClientMultiFactorOptimization(sv, { annual_load_kwh: 500000, discount_rate_pct: 4.0 });
    const optDiscHigh = runClientMultiFactorOptimization(sv, { annual_load_kwh: 500000, discount_rate_pct: 12.0 });
    const sLow = optDiscLow.schemes.find((s) => s.id === 'south_portrait_2p');
    const sHigh = optDiscHigh.schemes.find((s) => s.id === 'south_portrait_2p');
    assert.ok(sLow.npv_25_wan > sHigh.npv_25_wan + 5, `NPV at 4% (${sLow.npv_25_wan}) must exceed 12% (${sHigh.npv_25_wan})`);

    const optLossMaking = runClientMultiFactorOptimization(sv, {
      annual_load_kwh: 0,
      tariff_grid: 0.001,
      tariff_self: 0.001,
      capex_per_w: 50.0,
    });
    for (const s of optLossMaking.schemes) {
      if (s.dc_kw > 0) {
        assert.equal(s.irr_pct, null, 'Loss-making scheme must return null IRR instead of clamping to 5.5%');
        assert.equal(s.payback_yr, null, 'Loss-making scheme must return null payback');
      }
    }

    // 3. Tiny 12 m² roof (4m x 3m) must NOT clamp rawSlots to >= 16 modules
    const svTiny = new SatMapView(async () => ({}), () => {});
    svTiny.hasRoof = true;
    svTiny.roofOutlineM = [
      [-2, -1.5],
      [2, -1.5],
      [2, 1.5],
      [-2, 1.5],
    ];
    svTiny.edgeSetbackM = 0.5;
    const optTiny = runClientMultiFactorOptimization(svTiny);
    for (const s of optTiny.schemes) {
      assert.ok(s.module_count < 16, `Tiny 12m² roof scheme ${s.id} must have < 16 modules, got ${s.module_count}`);
    }

    // 4. Cold Vmpp ceiling violation (18S on 800V MPPT max at -15C) & B01 MPPT port overflow fail constraints.all_pass
    const svColdFail = new SatMapView(async () => ({}), () => {});
    await svColdFail.runAiDetectRoof();
    svColdFail.getSelectedInverter = () => ({
      id: 'inv-800v',
      rated_ac_kw: 50,
      max_dc_v: 1100,
      mppt_v_min: 200,
      mppt_v_max: 800,
      mppt_count: 4,
      strings_per_mppt: 2,
    });
    const optColdFail = runClientMultiFactorOptimization(svColdFail, {
      extremeTempMinC: -15,
      modules_per_string: 18,
    });
    assert.equal(optColdFail.string_voc_check.safe, false);
    for (const s of optColdFail.schemes) {
      if (s.module_count > 0) {
        assert.equal(s.constraints.all_pass, false, `Cold Vmpp violation must force all_pass=false on ${s.id}`);
      }
    }

    // applyMultiFactorSchemeToView adopts modules_per_string / safe series
    const adopted = applyMultiFactorSchemeToView(sv, { ...optDiscLow.schemes[0], modules_per_string: 15 });
    assert.ok(adopted);
    assert.equal(sv.modulesPerString, 15);

    // 5. Per-project latestScheme isolation across InnovationLabView & pvsyst-workbench.js
    sv.projectName = '项目A厂房';
    sv.summary.dcKw = 312.4;
    persistLatestSatmapScheme(sv, { projectId: 'proj-A' });

    const labProbe = new InnovationLabView({});
    const hitA = labProbe.readLatestSatmapStorage('proj-A');
    const missB = labProbe.readLatestSatmapStorage('proj-B');
    assert.ok(hitA && hitA.dcKw === 312.4);
    assert.equal(missB, null, 'proj-A cached scheme must NEVER leak into readLatestSatmapStorage("proj-B")');

    const wbPayloadB = buildPvsystV2RequestPayload(
      { summary: { e_grid_kwh: 120000, pr_pct: 83.5 } },
      { projectId: 'proj-B', projectName: '项目B独立工程', dcKw: 100, acKw: 90 }
    );
    assert.equal(wbPayloadB.project_id, 'proj-B');
    assert.equal(wbPayloadB.system.dc_kw, 100, 'proj-A dcKw (312.4) must NEVER leak into proj-B report payload');

    // 6. InnovationLabView({ dcKw: 100, dcAcRatio: 0.8 }).exportGuangzhuProReport sends ac_kw === 125
    let capturedLabReportBody = null;
    const labLowRatio = new InnovationLabView({
      dcKw: 100,
      dcAcRatio: 0.8,
      fetchImpl: async (_ep, opts) => {
        capturedLabReportBody = JSON.parse(opts.body);
        return { ok: true, json: async () => ({ ok: true, html: '<html><body>ok</body></html>' }) };
      },
    });
    labLowRatio.selectedParetoIdx = 2; // P3 uses this.dcAcRatio (0.8) and synced dcKw (100)
    await labLowRatio.exportGuangzhuProReport({ previewOnly: true, openNative: false });
    assert.ok(capturedLabReportBody);
    assert.equal(capturedLabReportBody.dc_kw, 100);
    assert.equal(capturedLabReportBody.ac_kw, 125);
    assert.equal(capturedLabReportBody.system.ac_kw, 125);

    // 7. InnovationLabView EN mode renders zero CJK characters and zero literal NaN/undefined across all 3 tabs
    setLang('en');
    const labZeroEn = new InnovationLabView({ dcKw: 0, moduleCount: 0, annualKwh: 0 });
    for (const tab of ['pareto', 'bess-carbon', 'benchmark']) {
      labZeroEn.activeTab = tab;
      const htmlTab = labZeroEn.html();
      const visibleText = stripTags(htmlTab);
      assert.ok(!/[\u4e00-\u9fff]/.test(visibleText), `Tab ${tab} in EN mode leaked CJK: ${visibleText.slice(0, 240)}`);
      assert.ok(!/\b(?:NaN|undefined)\b/.test(visibleText), `Tab ${tab} leaked NaN/undefined`);
      assert.ok(!/pvsyst/i.test(visibleText), `Tab ${tab} leaked PVsyst text`);
    }
  } finally {
    setLang(prevLang || 'zh');
    if (prevStorage === undefined) {
      delete globalThis.localStorage;
    } else {
      globalThis.localStorage = prevStorage;
    }
  }
});

test('R4-UI-05: id-only equipment specs never emit NaN SVG attributes on #result & fetch3DCatalog never calls non-existent GET /api/my-roofs', async () => {
  // 1. Reproduces test_t35_demo.py & live E2E #result console errors when equipment only carries `{ id }`
  const modIdOnly = enrichModuleSpec({ id: 'longi-lr5-72hph-550m' });
  assert.ok(Number.isFinite(modIdOnly.voc_v) && modIdOnly.voc_v > 0, `voc_v must be finite > 0, got ${modIdOnly.voc_v}`);
  assert.ok(Number.isFinite(modIdOnly.vmp_v) && modIdOnly.vmp_v > 0, `vmp_v must be finite > 0, got ${modIdOnly.vmp_v}`);
  assert.ok(Number.isFinite(modIdOnly.isc_a) && modIdOnly.isc_a > 0, `isc_a must be finite > 0, got ${modIdOnly.isc_a}`);
  assert.ok(Number.isFinite(modIdOnly.imp_a) && modIdOnly.imp_a > 0, `imp_a must be finite > 0, got ${modIdOnly.imp_a}`);
  assert.ok(typeof modIdOnly.model === 'string' && modIdOnly.model.trim().length > 0);

  const sizing = computeStringSizingAndCables({
    module: { id: 'longi-lr5-72hph-550m' },
    inverter: { id: 'huawei-sun2000-100ktl-m2' },
    lat: 31.81,
    lon: 119.97,
  });
  assert.ok(Number.isFinite(sizing.vocColdV) && sizing.vocColdV > 0);
  assert.ok(Number.isFinite(sizing.vmpStcV) && sizing.vmpStcV > 0);
  assert.ok(Number.isFinite(sizing.vmpHotV) && sizing.vmpHotV > 0);

  const unanalysedResultMarkup = pvsystProFoldMarkup({
    project_id: 't35-demo',
    version: 2,
    project: {
      id: 't35-demo',
      name: '离线牧光工程',
      site: { lat: 31.81, lon: 119.97 },
      equipment: {
        module_id: 'longi-lr5-72hph-550m',
        inverter_id: 'huawei-sun2000-100ktl-m2',
      },
    },
    design: { version: 2, params: { tilt_deg: 10 }, modules: [] },
  });
  assert.ok(!/\bNaN\b/.test(unanalysedResultMarkup), 'pvsystProFoldMarkup emitted NaN in HTML/SVG');
  assert.ok(!/\bundefined\b/.test(unanalysedResultMarkup), 'pvsystProFoldMarkup emitted undefined in HTML/SVG');

  // 2. Reproduces live E2E 404 console error on GET /api/my-roofs when my_roofs is empty
  const calledEndpoints = [];
  const mockViewOk = {
    api: async (ep) => {
      calledEndpoints.push(ep);
      if (ep === 'satmap/3d-catalog') {
        return { projects: [{ id: 'changzhou-demo', name: '常州厂房' }], my_roofs: [], templates: [{ id: 't1', name: '标准屋面' }] };
      }
      if (ep === 'roofs') {
        return { roofs: [{ id: 't1', name: '标准屋面', collection: 'demo' }] };
      }
      throw new Error(`Unexpected endpoint: ${ep}`);
    },
  };
  await fetch3DCatalog(mockViewOk);
  assert.ok(!calledEndpoints.includes('my-roofs'), `fetch3DCatalog called non-existent GET /api/my-roofs: ${calledEndpoints}`);
  assert.deepEqual(
    calledEndpoints,
    ['satmap/3d-catalog'],
    `When satmap/3d-catalog succeeds with empty my_roofs, fetch3DCatalog should not re-fetch fallback endpoints: ${calledEndpoints}`
  );

  const fallbackEndpoints = [];
  const mockViewFallback = {
    api: async (ep) => {
      fallbackEndpoints.push(ep);
      if (ep === 'satmap/3d-catalog') throw new Error('offline');
      if (ep === 'projects/local-list') return { projects: [] };
      if (ep === 'projects') return { projects: [] };
      if (ep === 'roofs') return { roofs: [{ id: 't1', name: '标准屋面', collection: 'demo' }] };
      throw new Error(`Non-existent endpoint called: ${ep}`);
    },
  };
  await fetch3DCatalog(mockViewFallback);
  assert.ok(!fallbackEndpoints.includes('my-roofs'), `Fallback path called non-existent GET /api/my-roofs: ${fallbackEndpoints}`);
});
