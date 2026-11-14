import test from 'node:test';
import assert from 'node:assert/strict';

import { SatMapView, pointInPolygon } from '../../desktop/web/satmap-view.js';
import {
  fetch3DCatalog,
  importFrom3DItem,
  buildSyncTo3DPayload,
  syncSatmapTo3D,
  navigateTo3DTarget,
  persistLatestSatmapScheme,
  computeColdVocAndStringSafety,
  computeMultiFactorStructuralCheck,
  evaluateModuleShadingLossPct,
  runClientMultiFactorOptimization,
  requestMultiFactorOptimization,
  applyMultiFactorSchemeToView,
  restoreMultiFactorPreview,
  renderSixAxisRadarSvg,
  renderLinkageTopStrip,
  renderLinkageDiffCard,
  renderImport3DModal,
  renderMultiFactorStudioPanel,
  buildClientPvsystV2ReportHtml,
  exportPvsystProfessionalReportV2,
  previewGuangzhuProReport,
  renderProReportPreviewModal,
  computeClientEngineeringHealthCheck,
  runEngineeringHealthCheck,
  exportSatmapDeliveryBundle,
  SATMAP_LATEST_STORAGE_KEY,
} from '../../desktop/web/satmap-3d-linkage.js';
import { setLang, toPureZhText } from '../../desktop/web/i18n.js';

function installBrowserStorageAndLocationShims() {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
    clear: () => store.clear(),
  };
  globalThis.location = {
    hash: '#satmap',
    protocol: 'http:',
    hostname: 'offline.test',
  };
  return store;
}

function stripHtmlVisibleText(rawHtml) {
  return String(rawHtml || '')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/\s+/g, ' ')
    .trim();
}

function createMockCanvasContext() {
  const calls = { fillText: [], dashed: 0, rects: 0 };
  return {
    calls,
    save() {},
    restore() {},
    beginPath() {},
    closePath() {},
    moveTo() {},
    lineTo() {},
    arc() {},
    fill() {},
    stroke() {},
    clip() {},
    clearRect() {},
    fillRect() { calls.rects += 1; },
    strokeRect() {},
    drawImage() {},
    translate() {},
    rotate() {},
    scale() {},
    setLineDash(arr) { if (arr && arr.length) calls.dashed += 1; },
    createLinearGradient() { return { addColorStop() {} }; },
    measureText(txt) { return { width: String(txt || '').length * 7 }; },
    fillText(txt) { calls.fillText.push(String(txt)); },
  };
}

test('Deliverable 1A: 3D Catalog & importFrom3DItem load exact 3D roof polygon, parapet, obstacles (with heights/types), and equipment onto #satmap', async () => {
  installBrowserStorageAndLocationShims();
  setLang('zh');

  const apiCalls = [];
  const view = new SatMapView({
    appState: { roofs: [{ id: 'tpl-std-01', name: '标准门式刚架厂房', city: '常州', length_m: 66, width_m: 30 }] },
    api: async (endpoint) => {
      apiCalls.push(endpoint);
      if (endpoint === 'satmap/3d-catalog') {
        return {
          projects: [{ id: 'proj-3d-01', name: '泰州精密制造一期', city: '泰州市', version: 2, dc_kw: 412.5, parapet_height_m: 0.95 }],
          my_roofs: [{ id: 'my-roof-09', name: '自建多边形厂房', city: '苏州市', area_m2: 2400, parapet_height_m: 0.6 }],
          templates: [{ id: 'tpl-flat-concrete', name: '混凝土平屋面厂房', city: '常州市', area_m2: 1920, parapet_height_m: 0.8 }],
        };
      }
      if (endpoint.startsWith('satmap/from-3d/project/proj-3d-01')) {
        return {
          ok: true,
          source: { kind: 'project', id: 'proj-3d-01', name: '泰州精密制造一期', version: 2 },
          site: { name: '泰州精密制造一期', address: '泰州市海陵区工业园88号', lat: 32.4855, lon: 119.9231 },
          roof: {
            roof_type: 'flat',
            building_height_m: 14.5,
            parapet_height_m: 0.95,
            slope_deg: 2,
            setback_m: 1.1,
            polygon_m: [[-34, -18], [34, -18], [34, 18], [-34, 18]],
            obstacles: [
              { id: 'obs-hvac-1', kind: 'hvac', name: '中央空调冷却塔', height_m: 2.6, polygon_m: [[-6, -4], [4, -4], [4, 3], [-6, 3]] },
              { id: 'obs-sky-1', kind: 'skylight', name: '屋面采光天窗', height_m: 0.45, polygon_m: [[12, -5], [18, -5], [18, 5], [12, 5]] },
            ],
          },
          design: {
            module_id: 'trina-tsm-605neg19rc20',
            inverter_id: 'huawei-sun2000-115ktl-m2',
            tilt_deg: 16,
            azimuth_deg: 180,
            row_gap_m: 1.45,
            mount_orientation: 'portrait',
            modules_per_string: 18,
          },
          reference_metrics: {
            dc_kw: 388.4,
            module_count: 642,
            annual_kwh: 458000,
            pr_pct: 83.4,
          },
        };
      }
      throw new Error(`Unexpected endpoint: ${endpoint}`);
    },
  });

  const catalog = await fetch3DCatalog(view);
  assert.equal(catalog.projects.length, 1);
  assert.equal(catalog.my_roofs.length, 1);
  assert.equal(catalog.templates.length, 1);

  await importFrom3DItem(view, 'project', 'proj-3d-01', 2);

  assert.equal(view.hasRoof, true);
  assert.equal(view.hasLaidOut, true);
  assert.equal(view.roofType, 'flat');
  assert.equal(view.buildingHeightM, 14.5);
  assert.equal(view.parapetHeightMm, 950);
  assert.equal(view.edgeSetbackM, 1.1);
  assert.equal(view.tiltDeg, 16);
  assert.equal(view.moduleModelId, 'trina-tsm-605neg19rc20');
  assert.equal(view.inverterModelId, 'huawei-sun2000-100ktl-m2');
  assert.equal(view.obstacles.length, 2);
  assert.equal(view.obstacles[0].heightM, 2.6);
  assert.equal(view.obstacles[0].kind, 'hvac');
  assert.equal(view.obstacles[1].heightM, 0.45);
  assert.ok(view.modules.length > 80, 'Should automatically lay out PV modules onto imported 3D roof');
  assert.equal(view.linkage3d.showDiffCard, true);
  assert.equal(view.linkage3d.linkedSource.id, 'proj-3d-01');

  // Verify fallback catalog when satmap/3d-catalog is offline
  const fallbackView = new SatMapView({
    appState: { roofs: [{ id: 'r-local-1', name: '本地样板厂房', city: '南京市', length_m: 50, width_m: 26 }] },
    api: async (ep) => {
      if (ep === 'satmap/3d-catalog') throw new Error('404');
      if (ep === 'projects/local-list') return { projects: [{ id: 'p-loc-1', name: '离线三维项目', dc_kw: 220 }] };
      if (ep === 'roofs') return { roofs: [{ id: 'my-custom-1', is_custom: true, name: '自建屋顶一号', length_m: 48, width_m: 24 }] };
      return {};
    },
  });
  const fbCat = await fetch3DCatalog(fallbackView);
  assert.equal(fbCat.projects.length, 1);
  assert.equal(fbCat.my_roofs.length, 1);
  assert.ok(fbCat.templates.length >= 1);
});

test('Deliverable 1B: syncSatmapTo3D, save-project fallback, Live Diff Card, one-click #result/#roof jumps, and localStorage #lab sync', async () => {
  const store = installBrowserStorageAndLocationShims();
  setLang('zh');

  let receivedSyncPayload = null;
  let roofsRefreshed = false;
  const appState = { roofs: [] };

  const view = new SatMapView({
    appState,
    api: async (endpoint, payload) => {
      if (endpoint === 'satmap/sync-to-3d') {
        receivedSyncPayload = payload;
        return {
          ok: true,
          project_id: 'proj-sync-88',
          version: 3,
          roof_id: 'my-sat-proj-sync-88',
          jump_result_hash: '#result/proj-sync-88?version=3',
          jump_roof_edit_hash: '#roof/my-sat-proj-sync-88',
          diff: {
            dc_kw_sat: payload.dc_kw,
            dc_kw_3d: Number((payload.dc_kw * 0.92).toFixed(2)),
            module_count_sat: payload.module_count,
            module_count_3d: Math.round(payload.module_count * 0.92),
            annual_kwh_sat: payload.annual_kwh,
            annual_kwh_3d: Math.round(payload.annual_kwh * 0.91),
            pr_pct_sat: 84.8,
            pr_pct_3d: 82.9,
            load_kg_m2: payload.pvsyst_summary.load_kg_m2,
          },
        };
      }
      if (endpoint === 'roofs') {
        roofsRefreshed = true;
        return { roofs: [{ id: 'my-sat-proj-sync-88', is_custom: true, name: '同步自建屋顶' }] };
      }
      return {};
    },
  });

  view.roofType = 'flat';
  view.parapetHeightMm = 800;
  view.obstacles = [
    { id: 'obs-1', name: '排烟风机', kind: 'hvac', heightM: 2.1, polygon: [[-4, -3], [4, -3], [4, 3], [-4, 3]] },
  ];
  view.layoutModules({ quiet: true, autoCreateRoof: true });

  const syncStatus = await syncSatmapTo3D(view, { syncMode: 'both' });
  assert.equal(syncStatus.ok, true);
  assert.equal(syncStatus.projectId, 'proj-sync-88');
  assert.equal(syncStatus.version, 3);
  assert.equal(syncStatus.roofId, 'my-sat-proj-sync-88');
  assert.ok(receivedSyncPayload, 'satmap/sync-to-3d must receive full engineering payload');
  assert.equal(receivedSyncPayload.parapet_height_m, 0.8);
  assert.equal(receivedSyncPayload.obstacles[0].height_m, 2.1);
  assert.ok(Array.isArray(receivedSyncPayload.roof_polygon_m) && receivedSyncPayload.roof_polygon_m.length >= 4);
  assert.ok(Array.isArray(receivedSyncPayload.modules_layout) && receivedSyncPayload.modules_layout.length > 0);
  assert.ok(receivedSyncPayload.multifactor_params.max_roof_load_kg_m2 >= 15);

  const diffHtml = renderLinkageDiffCard(view);
  assert.match(diffHtml, /jump-3d-result/);
  assert.match(diffHtml, /jump-3d-roof/);
  assert.match(diffHtml, /卫星深化方案/);

  await navigateTo3DTarget(view, 'result');
  assert.equal(globalThis.location.hash, '#result/proj-sync-88?version=3');

  await navigateTo3DTarget(view, 'roof');
  assert.equal(globalThis.location.hash, '#roof/my-sat-proj-sync-88');
  assert.equal(roofsRefreshed, true);
  assert.equal(appState.roofs[0].id, 'my-sat-proj-sync-88');

  // Verify live snapshot persisted in localStorage for #lab (Innovation Lab)
  const rawLatest = store.get(SATMAP_LATEST_STORAGE_KEY);
  assert.ok(rawLatest, 'gz.satmap.latestScheme should be stored in localStorage');
  const parsedLatest = JSON.parse(rawLatest);
  assert.equal(parsedLatest.dcKw, view.summary.dcKw);
  assert.equal(parsedLatest.moduleCount, view.summary.moduleCount);
  assert.equal(parsedLatest.syncedProjectId, 'proj-sync-88');

  // Verify graceful fallback to satmap/save-project when satmap/sync-to-3d fails
  let saveFallbackCalled = false;
  const viewFb = new SatMapView({
    api: async (ep) => {
      if (ep === 'satmap/sync-to-3d') throw new Error('Endpoint unavailable');
      if (ep === 'satmap/save-project') {
        saveFallbackCalled = true;
        return { project_id: 'fallback-proj-01', version: 1 };
      }
      return {};
    },
  });
  const fbRes = await syncSatmapTo3D(viewFb);
  assert.equal(saveFallbackCalled, true);
  assert.equal(fbRes.projectId, 'fallback-proj-01');
});

test('Deliverable 2A: East-West butterfly (east_west) paired topology, higher packing density, strict E/W string & MPPT isolation, and dual sub_arrays', () => {
  installBrowserStorageAndLocationShims();
  const view = new SatMapView();
  view.roofType = 'flat';
  view.roofOutlineM = [[-32, -16], [32, -16], [32, 16], [-32, 16]];
  view.hasRoof = true;
  view.tiltDeg = 18;
  view.rowSpacingM = 1.65;

  // Baseline south_fixed at 18° tilt
  view.orientationMode = 'south_fixed';
  view.mfState.orientationMode = 'south_fixed';
  view.layoutModules({ quiet: true, autoCreateRoof: false });
  const southCount = view.summary.moduleCount;

  // Switch to East-West butterfly at 10° tilt
  view.orientationMode = 'east_west';
  view.mfState.orientationMode = 'east_west';
  view.tiltDeg = 10;
  view.layoutModules({ quiet: true, autoCreateRoof: false });
  view.electricalConfirmed = true;
  view.computeElectricalAllocation();
  view.refreshPvsystData({ fetchBackend: false });

  assert.ok(view.summary.eastCount > 0, 'Should place East-facing butterfly wing modules');
  assert.ok(view.summary.westCount > 0, 'Should place West-facing butterfly wing modules');
  assert.ok(
    view.summary.moduleCount > southCount,
    `East-West butterfly (${view.summary.moduleCount}) should pack more modules than wide-spaced South 18° (${southCount})`
  );

  // Verify exact 90° / 270° metadata on modules
  for (const m of view.modules) {
    assert.ok(m.slope === 'east' || m.slope === 'west');
    assert.equal(m.azimuth_deg, m.slope === 'east' ? 90 : 270);
  }

  // Verify strict electrical isolation: NO string mixes East and West modules, NO MPPT mixes East and West strings!
  assert.ok(view.strings.length >= 2);
  for (const st of view.strings) {
    const slopesInString = new Set(st.modules.map((m) => m.slope));
    assert.equal(slopesInString.size, 1, `String ${st.id} must not mix East and West butterfly wings`);
  }
  const activeMppts = view.mpptRows.filter((mppt) => mppt.stringCount > 0);
  assert.ok(activeMppts.length >= 2);
  for (const mppt of activeMppts) {
    assert.ok(
      mppt.slope === 'east' || mppt.slope === 'west',
      `MPPT ${mppt.inverterName}-${mppt.mpptName} must isolate single butterfly orientation`
    );
  }

  // Verify dual-orientation sub_arrays in PVsyst payload
  assert.ok(Array.isArray(view.pvsystLastPayload?.sub_arrays));
  assert.equal(view.pvsystLastPayload.sub_arrays.length, 2);
  const azimuths = view.pvsystLastPayload.sub_arrays.map((sa) => sa.azimuth_deg).sort((a, b) => a - b);
  assert.deepEqual(azimuths, [90, 270]);
});

test('Deliverable 2B: Elevated Solar Canopy (elevated_canopy) bridges over low obstacles while avoiding tall obstacles', () => {
  installBrowserStorageAndLocationShims();
  const view = new SatMapView();
  view.roofType = 'flat';
  view.roofOutlineM = [[-25, -14], [25, -14], [25, 14], [-25, 14]];
  view.hasRoof = true;

  const lowPoly = [[-12, -5], [2, -5], [2, 5], [-12, 5]]; // Large 14m × 10m low pipe/skylight zone (H = 1.1m)
  const tallPoly = [[8, -4], [18, -4], [18, 4], [8, 4]];   // Tall 10m × 8m elevator room (H = 4.2m)
  view.obstacles = [
    { id: 'obs-low', name: '低矮管线设备区', kind: 'skylight', heightM: 1.1, polygon: lowPoly },
    { id: 'obs-tall', name: '电梯机房', kind: 'elevator', heightM: 4.2, polygon: tallPoly },
  ];

  // Standard south_fixed avoids both obstacles
  view.orientationMode = 'south_fixed';
  view.mfState.orientationMode = 'south_fixed';
  view.layoutModules({ quiet: true, autoCreateRoof: false });
  const groundCount = view.modules.length;
  const overLowInGround = view.modules.filter((m) => pointInPolygon([m.cx, m.cy], lowPoly)).length;
  assert.equal(overLowInGround, 0, 'Standard rack must not place modules over low obstacle');

  // Switch to elevated_canopy (clearance 2.8m -> bridges obstacles <= 2.5m, avoids 4.2m)
  view.orientationMode = 'elevated_canopy';
  view.mfState.orientationMode = 'elevated_canopy';
  view.mfState.canopyClearanceM = 2.8;
  view.layoutModules({ quiet: true, autoCreateRoof: false });

  const overLowInCanopy = view.modules.filter((m) => pointInPolygon([m.cx, m.cy], lowPoly)).length;
  const overTallInCanopy = view.modules.filter((m) => pointInPolygon([m.cx, m.cy], tallPoly)).length;
  assert.ok(view.modules.length > groundCount, 'Elevated canopy should recover roof capacity over low obstacles');
  assert.ok(overLowInCanopy > 0, 'Elevated canopy should bridge over 1.1m low obstacle');
  assert.equal(overTallInCanopy, 0, 'Elevated canopy must still strictly avoid 4.2m tall elevator room');
});

test('Deliverable 2C: Dead-load limit check, extreme cold Voc string safety cap, typhoon wind setback, and central fire lane', () => {
  installBrowserStorageAndLocationShims();
  const view = new SatMapView();
  view.roofType = 'flat';
  view.roofOutlineM = [[-30, -16], [30, -16], [30, 16], [-30, 16]];
  view.hasRoof = true;

  // 1. Extreme cold Voc safety (-30°C with 24 modules/string should exceed 1100V and auto-cap series length!)
  view.modulesPerString = 24;
  view.mfState.extremeTempMinC = -30;
  const vocUnsafe = computeColdVocAndStringSafety(view.getSelectedModule(), view.getSelectedInverter(), view.mfState, 24);
  assert.equal(vocUnsafe.safe, false, '24×51V modules at -30°C must flag >1100V overvoltage');
  assert.ok(vocUnsafe.max_series_safe < 21 && vocUnsafe.max_series_safe >= 14);

  view.layoutModules({ quiet: true, autoCreateRoof: false });
  view.electricalConfirmed = true;
  view.computeElectricalAllocation();
  assert.ok(
    view.modulesPerString <= vocUnsafe.max_series_safe,
    `computeElectricalAllocation must auto-cap modulesPerString (${view.modulesPerString}) <= ${vocUnsafe.max_series_safe}`
  );

  // 2. Roof dead-load verification: ballast on light steel roof limit (22 kg/m²) vs clamp
  const ballastCheck = computeMultiFactorStructuralCheck({
    roofType: 'flat',
    orientationMode: 'south_fixed',
    rackRows: '2P',
    tiltDeg: 15,
    buildingHeightM: 12,
    edgeSetbackM: 0.8,
    moduleSpec: view.getSelectedModule(),
    mfParams: { ...view.mfState, fixingType: 'ballast', maxRoofLoadKgM2: 22 },
  });
  assert.equal(ballastCheck.load_ok, false, 'Concrete ballast (~48 kg/m²) must fail 22 kg/m² light-roof limit');

  const clampCheck = computeMultiFactorStructuralCheck({
    roofType: 'single_slope',
    orientationMode: 'flush_pitched',
    rackRows: '2P',
    tiltDeg: 5,
    buildingHeightM: 12,
    edgeSetbackM: 0.8,
    moduleSpec: view.getSelectedModule(),
    mfParams: { ...view.mfState, fixingType: 'clamp', maxRoofLoadKgM2: 22 },
  });
  assert.equal(clampCheck.load_ok, true, 'Standing-seam clamp (~15.5 kg/m²) must pass 22 kg/m² limit');

  // 3. Typhoon wind w0=0.85 kN/m² + Fire lane width 2.0m
  view.mfState.basicWindW0KnM2 = 0.85;
  view.mfState.fireLaneWidthM = 2.0;
  view.edgeSetbackM = 0.6;
  view.layoutModules({ quiet: true, autoCreateRoof: false });

  for (const m of view.modules) {
    // Typhoon setback reinforcement pushes modules >= ~1.35m inside ±30m / ±16m perimeter
    assert.ok(Math.abs(m.cx) < 30 - 1.1, `Module cx=${m.cx} respects typhoon perimeter setback`);
    // Central cross fire lane (width 2.0m => half-width 1.0m around x=0 and y=0)
    assert.ok(Math.abs(m.cx) >= 0.95, `Module cx=${m.cx} respects vertical main fire lane`);
    assert.ok(Math.abs(m.cy) >= 0.95, `Module cy=${m.cy} respects horizontal main fire lane`);
  }
});

test('Deliverable 2D: Poison-module shading threshold auto-prunes heavily shaded slots and renders dashed ghost slots on 2D canvas', () => {
  installBrowserStorageAndLocationShims();
  const view = new SatMapView();
  view.roofType = 'flat';
  view.roofOutlineM = [[-26, -15], [26, -15], [26, 15], [-26, 15]];
  view.hasRoof = true;
  view.parapetHeightMm = 1500; // Tall 1.5m south parapet
  view.obstacles = [
    { id: 'obs-tower', name: '高大冷却塔', kind: 'chimney', heightM: 5.5, polygon: [[-5, 2], [5, 2], [5, 8], [-5, 8]] },
  ];

  // Without auto-pruning
  view.mfState.autoPruneShaded = false;
  view.layoutModules({ quiet: true, autoCreateRoof: false });
  const unprunedCount = view.modules.length;
  assert.equal(view.prunedShadedModules.length, 0);

  // Enable auto-pruning at 9% shading loss threshold
  view.mfState.autoPruneShaded = true;
  view.mfState.maxModuleShadingLossPct = 9;
  view.mfState.showPrunedShadedSlots = true;
  view.layoutModules({ quiet: true, autoCreateRoof: false });

  assert.ok(view.prunedShadedModules.length > 0, 'Should auto-prune heavily shaded modules near 5.5m tower / 1.5m parapet');
  assert.equal(view.modules.length + view.prunedShadedModules.length, unprunedCount);
  for (const pm of view.prunedShadedModules) {
    assert.ok(pm.shadingLossPct >= 9, `Pruned module shadingLossPct (${pm.shadingLossPct}%) must exceed threshold`);
  }

  // Test 2D canvas rendering (East-West arrows + obstacle height label + amber dashed pruned slots)
  view.orientationMode = 'east_west';
  view.mfState.orientationMode = 'east_west';
  view.zoom = 21;
  const mockCtx = createMockCanvasContext();
  view.host = {
    querySelector: (sel) => {
      if (sel === '#satmap-main-canvas') {
        return {
          width: 960,
          height: 600,
          getContext: () => mockCtx,
        };
      }
      return null;
    },
  };
  view.drawMapCanvas();
  assert.ok(mockCtx.calls.dashed >= 1, 'Should draw dashed ghost outlines for pruned shaded modules');
  assert.ok(
    mockCtx.calls.fillText.some((t) => t.includes('5.5m')),
    'Should render obstacle 3D height label on 2D canvas'
  );
});

test('Deliverable 2E: Multi-Factor Optimizer (backend API + client fallback), 6-Axis Radar SVG, Preview, Restore, and Apply', async () => {
  installBrowserStorageAndLocationShims();
  setLang('zh');

  const view = new SatMapView();
  view.roofType = 'flat';
  view.layoutModules({ quiet: true, autoCreateRoof: true });
  const initialMode = view.orientationMode;
  const initialCount = view.summary.moduleCount;

  // 1. Offline deterministic client multi-factor optimization
  const clientRes = await requestMultiFactorOptimization(view);
  assert.equal(clientRes.ok, true);
  assert.equal(clientRes.source, 'client_physics');
  assert.ok(clientRes.schemes.length >= 5, 'Should evaluate at least 5 multi-factor candidate schemes');
  assert.ok(clientRes.recommended_id);

  // Verify 6-axis radar SVG & Studio Panel rendering
  view.mfState.openInStep1 = true;
  const studioHtml = renderMultiFactorStudioPanel(view, { context: 'step1' });
  assert.match(studioHtml, /satmap-mf-radar-svg/);
  assert.match(studioHtml, /data-sat-mf-preview/);
  assert.match(studioHtml, /data-sat-mf-apply/);

  // 2. Preview East-West scheme -> verify layout updates -> Restore -> verify exact prior layout returns
  const ewScheme = clientRes.schemes.find((s) => s.orientation_mode === 'east_west');
  assert.ok(ewScheme, 'Candidate matrix must include East-West butterfly scheme');

  applyMultiFactorSchemeToView(view, ewScheme.id, { previewOnly: true });
  assert.equal(view.orientationMode, 'east_west');
  assert.ok(view.mfState.previewSnapshot, 'Preview mode must save snapshot');

  const restored = restoreMultiFactorPreview(view);
  assert.equal(restored, true);
  assert.equal(view.orientationMode, initialMode);
  assert.equal(view.summary.moduleCount, initialCount);

  // 3. Apply scheme permanently + test mocked backend satmap/optimize-multifactor
  applyMultiFactorSchemeToView(view, ewScheme.id, { previewOnly: false });
  assert.equal(view.orientationMode, 'east_west');
  assert.equal(view.mfState.previewSnapshot, null);

  let backendOptCalled = false;
  view.api = async (ep, body) => {
    if (ep === 'satmap/optimize-multifactor') {
      backendOptCalled = true;
      assert.ok(body.multifactor_params);
      return {
        ok: true,
        recommended_id: 'backend-ew-1p',
        schemes: [
          {
            id: 'backend-ew-1p',
            name_zh: '东西向双坡蝴蝶阵',
            name_en: 'East-West Butterfly Rack',
            orientation_mode: 'east_west',
            mount_orientation: 'portrait',
            rack_type: '1P',
            tilt_deg: 10,
            azimuth_deg: 90,
            dc_kw: 420.5,
            module_count: 725,
            annual_kwh: 486000,
            specific_yield_kwh_kwp: 1156,
            pr_pct: 85.1,
            load_kg_m2: 18.2,
            lcoe_cny_kwh: 0.215,
            payback_yr: 4.1,
            composite_score: 93.4,
            constraints: { all_pass: true, load_ok: true, voc_ok: true, wind_ok: true },
            factor_scores: { capacity: 96, yield: 92, economics: 94, safety: 91, self_use: 89, shading_resilience: 93 },
          },
        ],
      };
    }
    return {};
  };
  const apiOptRes = await requestMultiFactorOptimization(view);
  assert.equal(backendOptCalled, true);
  assert.equal(apiOptRes.source, 'backend_engine');
  assert.equal(apiOptRes.recommended_id, 'backend-ew-1p');
});

test('Deliverable 3 & Guardrails: PVsyst V2 Professional Report (with software icon) + strict pure ZH/EN & zero external branding across all open panels', async () => {
  installBrowserStorageAndLocationShims();
  setLang('zh');

  let reportPayloadSent = null;
  const view = new SatMapView({
    api: async (ep, payload) => {
      if (ep === 'pvsyst/professional-report') {
        reportPayloadSent = payload;
        return {
          ok: true,
          html: `<!DOCTYPE html><html><body><img src="${payload.icon_url}"><h1>专业仿真报告 V2</h1></body></html>`,
        };
      }
      return {};
    },
  });

  view.layoutModules({ quiet: true, autoCreateRoof: true });

  // Verify export-pvsyst-v2 button exists in Top Strip (Step 1), Step 3, and Step 5
  view.step = 1;
  assert.match(view.html(), /data-sat-action="export-pvsyst-v2"/);
  view.step = 3;
  assert.match(view.html(), /data-sat-action="export-pvsyst-v2"/);
  view.step = 5;
  assert.match(view.html(), /data-sat-action="export-pvsyst-v2"/);

  // Test backend report call
  const repApi = await exportPvsystProfessionalReportV2(view, { openWindow: false });
  assert.equal(repApi.ok, true);
  assert.equal(repApi.source, 'backend_api');
  assert.equal(reportPayloadSent.icon_url, '/assets/guangzhu-128.png');
  assert.ok(reportPayloadSent.system.dc_kw > 0);
  assert.ok(reportPayloadSent.multifactor);
  assert.match(repApi.html, /\/assets\/guangzhu-128\.png/);

  // Test offline client-side printable 6-page Guangzhu Pro Report fallback
  view.api = async () => { throw new Error('offline'); };
  const repFallback = await exportPvsystProfessionalReportV2(view, { openNative: false });
  assert.equal(repFallback.ok, true);
  assert.equal(repFallback.source, 'client_fallback');
  assert.match(repFallback.html, /\/assets\/guangzhu-128\.png/);
  assert.match(repFallback.html, /光筑专业报告/);
  assert.match(repFallback.html, /id="gz-report-page-1"/);
  assert.match(repFallback.html, /id="gz-report-page-6"/);
  assert.doesNotMatch(repFallback.html, /pvsyst/i);

  // Open Import 3D Modal + Diff Card + Multi-Factor Studio simultaneously and check strict ZH/EN purity + zero forbidden names!
  view.linkage3d.showImportModal = true;
  view.linkage3d.showDiffCard = true;
  view.linkage3d.linkedSource = { kind: 'project', id: 'proj-01', name: '常州标准厂房', version: 1 };
  view.linkage3d.catalog = {
    projects: [{ id: 'proj-01', name: '常州标准厂房', name_en: 'Changzhou Plant', city: '常州市', city_en: 'Changzhou', dc_kw: 320, parapet_height_m: 0.6 }],
    my_roofs: [],
    templates: [],
  };
  view.mfState.openInStep1 = true;
  view.mfState.openInStep3 = true;

  for (const step of [1, 2, 3, 4, 5]) {
    view.step = step;
    setLang('zh');
    const rawZh = view.html();
    assert.doesNotMatch(rawZh, /鹧鸪云|PVLANE|PVsyst 7|三大相关软件/, `Step ${step} raw HTML must not contain external software names`);
    const newPanelsZh = `${renderLinkageTopStrip(view)}${renderLinkageDiffCard(view)}${renderImport3DModal(view)}${renderMultiFactorStudioPanel(view, { context: 'step1' })}`;
    assert.doesNotMatch(stripHtmlVisibleText(newPanelsZh), /鹧鸪云|PVLANE|PVsyst/i, 'New linkage & multi-factor panels must have zero external brand names');
    const visZh = toPureZhText(stripHtmlVisibleText(rawZh));
    assert.doesNotMatch(visZh, /[A-Za-z]/, `Step ${step} ZH visible text must have 0 ASCII letters, got leak in: ${visZh.match(/[A-Za-z]+/g)?.slice(0, 5)}`);

    setLang('en');
    const rawEn = view.html();
    assert.doesNotMatch(rawEn, /鹧鸪云|PVLANE|PVsyst 7|三大相关软件/, `Step ${step} EN raw HTML must not contain external software names`);
    const newPanelsEn = `${renderLinkageTopStrip(view)}${renderLinkageDiffCard(view)}${renderImport3DModal(view)}${renderMultiFactorStudioPanel(view, { context: 'step1' })}`;
    assert.doesNotMatch(stripHtmlVisibleText(newPanelsEn), /鹧鸪云|PVLANE|PVsyst/i, 'New linkage & multi-factor EN panels must have zero external brand names');
    const visEn = stripHtmlVisibleText(rawEn);
    assert.doesNotMatch(visEn, /[\u4e00-\u9fff]/, `Step ${step} EN visible text must have 0 Chinese chars, got leak in: ${visEn.match(/[\u4e00-\u9fff]+/g)?.slice(0, 5)}`);
  }

  setLang('zh');
});

test('Audit Round 1 Regressions (#13): HTML5 data-sat-3dcat-tab click, synced-only report project_id + pruned_shaded_modules, and 6-axis radar viewBox padding', async () => {
  installBrowserStorageAndLocationShims();
  setLang('zh');

  let lastReportPayload = null;
  const view = new SatMapView({
    api: async (ep, payload) => {
      if (ep === 'satmap/from-3d/project/proj-ew-demo?version=2') {
        return {
          ok: true,
          source: { kind: 'project', id: 'proj-ew-demo', name: '泰州祥泰仓库', version: 2 },
          roof: {
            roof_type: 'flat',
            parapet_height_m: 1.5,
            building_height_m: 11,
            outline_local_m: [[-26, -15], [26, -15], [26, 15], [-26, 15]],
            obstacles: [
              { id: 'obs-1', name: '冷却塔', kind: 'chimney', height_m: 5.2, polygon: [[-4, 2], [4, 2], [4, 7], [-4, 7]] },
            ],
          },
          design: { tilt_deg: 18, azimuth_deg: 180 },
          reference_metrics: { dc_kw: 260, module_count: 448, annual_kwh: 298000, pr_pct: 83.4 },
        };
      }
      if (ep === 'satmap/sync-to-3d') {
        return {
          ok: true,
          project_id: 'proj-ew-demo',
          version: 3,
          roof_id: 'my-sat-proj-ew-demo',
          jump_result_hash: '#result/proj-ew-demo?version=3',
          jump_roof_edit_hash: '#roof/my-sat-proj-ew-demo',
        };
      }
      if (ep === 'pvsyst/professional-report') {
        lastReportPayload = payload;
        return { ok: true, html: '<!DOCTYPE html><html><body>OK</body></html>' };
      }
      return {};
    },
  });

  // 1. P1 Real-Chrome HTML5 DOMStringMap rule: data-sat-3dcat-tab -> dataset['sat-3dcatTab'], dataset.sat3dcatTab === undefined
  view.linkage3d.showImportModal = true;
  view.linkage3d.catalog = {
    projects: [{ id: 'p1', name: '项目一', dc_kw: 100 }],
    my_roofs: [{ id: 'my-r1', name: '自建屋顶一', area_m2: 1800 }],
    templates: [{ id: 'tpl-1', name: '标准厂房样板', area_m2: 2400 }],
  };
  const mockHost = {
    innerHTML: view.html(),
    scrollTop: 0,
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  view.mount(mockHost);
  assert.equal(typeof mockHost.onclick, 'function');

  const makeChromeTabButton = (tabVal) => {
    const btn = {
      dataset: { 'sat-3dcatTab': tabVal }, // Chrome HTML5 spec: '-3' does NOT camelCase to sat3dcatTab!
      getAttribute: (attr) => (attr === 'data-sat-3dcat-tab' ? tabVal : null),
      closest: (sel) => (sel === 'button' ? btn : null),
    };
    assert.equal(btn.dataset.sat3dcatTab, undefined);
    return btn;
  };

  await mockHost.onclick({ target: makeChromeTabButton('my_roofs') });
  assert.equal(view.linkage3d.catalogTab, 'my_roofs');
  assert.match(mockHost.innerHTML, /my-r1/);

  await mockHost.onclick({ target: makeChromeTabButton('templates') });
  assert.equal(view.linkage3d.catalogTab, 'templates');
  assert.match(mockHost.innerHTML, /tpl-1/);

  // 2. P2 Unsynced import vs Synced vs Stale project_id + pruned_shaded_modules in V2 report payload
  view.mfState.autoPruneShaded = true;
  view.mfState.maxModuleShadingLossPct = 9;
  await importFrom3DItem(view, 'project', 'proj-ew-demo', 2);
  assert.equal(view.linkage3d.syncStatus, null);
  assert.ok(view.prunedShadedModules.length > 0, 'Tall parapet + 5.2m tower should prune shaded modules');

  // Unsynced export: must NOT send stale project_id, and MUST send both pruned_shaded_count & pruned_shaded_modules
  await exportPvsystProfessionalReportV2(view, { openWindow: false });
  assert.equal('project_id' in lastReportPayload, false, 'Unsynced 3D import must omit project_id');
  assert.equal(lastReportPayload.multifactor.pruned_shaded_count, view.prunedShadedModules.length);
  assert.equal(lastReportPayload.multifactor.pruned_shaded_modules, view.prunedShadedModules.length);
  assert.equal(lastReportPayload.system.pruned_shaded_modules, view.prunedShadedModules.length);

  // Also support literal string syncStatus === 'synced'
  view.linkage3d.syncStatus = 'synced';
  await exportPvsystProfessionalReportV2(view, { openWindow: false });
  assert.equal(lastReportPayload.project_id, 'proj-ew-demo');

  // Sync to 3D -> fresh syncStatus object attaches synced project_id & version=3
  await syncSatmapTo3D(view);
  assert.equal(view.linkage3d.syncStatus.state, 'synced');
  assert.equal(view.linkage3d.syncStatus.stale, false);
  await exportPvsystProfessionalReportV2(view, { openWindow: false });
  assert.equal(lastReportPayload.project_id, 'proj-ew-demo');
  assert.equal(lastReportPayload.version, 3);

  // Subsequent layout edit marks syncStatus stale -> omits stale project_id until re-synced
  view.orientationMode = 'east_west';
  view.mfState.orientationMode = 'east_west';
  view.layoutModules({ quiet: true, autoCreateRoof: false });
  assert.equal(view.linkage3d.syncStatus.stale, true);
  await exportPvsystProfessionalReportV2(view, { openWindow: false });
  assert.equal('project_id' in lastReportPayload, false, 'Stale post-sync edits must omit stale project_id');

  // 3. P2 6-Axis Radar SVG viewBox="-18 -10 306 242" & non-overlapping spoke labels
  const radarSvg = renderSixAxisRadarSvg({
    factor_scores: {
      capacity: 100,
      yield: 100,
      economics: 100,
      safety: 100,
      self_use: 100,
      shading_resilience: 100,
    },
  });
  assert.match(radarSvg, /viewBox="-18 -10 306 242"/);
  const topLabelMatch = radarSvg.match(/<text x="([\d.-]+)" y="([\d.-]+)"[^>]*>装机容量 100<\/text>/);
  const leftLabelMatch = radarSvg.match(/<text x="([\d.-]+)" y="([\d.-]+)"[^>]*>抗遮挡度 100<\/text>/);
  const topCircleMatch = radarSvg.match(/<circle cx="135" cy="([\d.-]+)"/);
  assert.ok(topLabelMatch && leftLabelMatch && topCircleMatch);
  const topLabelY = Number(topLabelMatch[2]);
  const topDotCy = Number(topCircleMatch[1]);
  const leftLabelX = Number(leftLabelMatch[1]);
  assert.ok(topLabelY <= topDotCy - 14, `Top label y=${topLabelY} must sit >=14px above top dot cy=${topDotCy}`);
  assert.ok(leftLabelX - 64 >= -18, `Left label x=${leftLabelX} (width ~64px) must stay inside viewBox left=-18`);
});

test('Audit Round 2 Regression (#19): SatMapView.refresh() prevents Blink NotFoundError re-entrancy when focused Multi-Factor input blurs during innerHTML', () => {
  installBrowserStorageAndLocationShims();
  const prevDocument = globalThis.document;
  try {
    const bodyStub = {};
    const mockDoc = {
      body: bodyStub,
      activeElement: bodyStub,
      getElementById: () => null,
      querySelector: () => null,
    };
    globalThis.document = mockDoc;

    const view = new SatMapView();
    view.layoutModules({ quiet: true, autoCreateRoof: true });

    let rawHtml = '';
    let settingInnerHtml = false;
    let innerHtmlWriteCount = 0;

    const blinkHost = {
      scrollTop: 0,
      contains: (node) => Boolean(node && node._insideHost),
      querySelector: () => null,
      querySelectorAll: () => [],
      get innerHTML() {
        return rawHtml;
      },
      set innerHTML(val) {
        if (settingInnerHtml) {
          throw new Error(
            "DOMException: NotFoundError: Failed to set the 'innerHTML' property on 'Element': The node to be removed is no longer a child of this node."
          );
        }
        settingInnerHtml = true;
        try {
          // Simulate Blink detaching a still-focused child mid-innerHTML -> synchronous blur + change!
          if (mockDoc.activeElement && blinkHost.contains(mockDoc.activeElement)) {
            const strayFocused = mockDoc.activeElement;
            strayFocused.blur();
          }
          rawHtml = String(val);
          innerHtmlWriteCount += 1;
        } finally {
          settingInnerHtml = false;
        }
      },
    };

    view.render(blinkHost);
    assert.equal(typeof blinkHost.onchange, 'function');

    const makeFocusedMfInput = (fieldName, value) => {
      let dirtyOnFocus = true;
      const input = {
        _insideHost: true,
        type: 'number',
        value: String(value),
        dataset: { satMfField: fieldName },
        getAttribute: (attr) => (attr === 'data-sat-mf-field' ? fieldName : null),
        blur() {
          if (mockDoc.activeElement === input) {
            mockDoc.activeElement = bodyStub;
            // Simulate Blink firing synchronous change on blur when value edited while focused
            if (dirtyOnFocus) {
              dirtyOnFocus = false;
              blinkHost.onchange?.({ target: input });
            }
          }
        },
      };
      mockDoc.activeElement = input;
      return input;
    };

    // Case 1: Focused <input data-sat-mf-field="maxRoofLoadKgM2"> fires onchange directly
    const loadInput = makeFocusedMfInput('maxRoofLoadKgM2', 48);
    const writesBefore1 = innerHtmlWriteCount;
    assert.doesNotThrow(() => {
      blinkHost.onchange({ target: loadInput });
    });
    assert.equal(view.mfState.maxRoofLoadKgM2, 48);
    assert.equal(mockDoc.activeElement, bodyStub, 'Focused input must be blurred before innerHTML detachment');
    assert.equal(innerHtmlWriteCount, writesBefore1 + 1, 'Suppresses duplicate blur->change echo to a single DOM write');

    // Case 2: Uncommitted focused input blurs when an external refresh({ resetScroll: true }) runs
    makeFocusedMfInput('basicWindW0KnM2', 0.78);
    assert.doesNotThrow(() => {
      view.refresh({ resetScroll: true });
    });
    assert.equal(view.mfState.basicWindW0KnM2, 0.78);
    assert.equal(mockDoc.activeElement, bodyStub);
    assert.equal(view._isRefreshing, false);
    assert.equal(view._pendingRefreshOpts, null);
  } finally {
    if (prevDocument === undefined) {
      delete globalThis.document;
    } else {
      globalThis.document = prevDocument;
    }
  }
});

test('Iteration 2 (#23): Streamlined UX, Native PDF Export (0 window.open), In-App 6-Page Preview Modal, Step 5 3-Card Delivery Center + 8-Item Health Check, and Zero PVsyst Visible Text', async () => {
  installBrowserStorageAndLocationShims();
  setLang('zh');

  let windowOpenCalls = 0;
  const prevWindow = globalThis.window;
  globalThis.window = {
    location: globalThis.location,
    open: () => {
      windowOpenCalls += 1;
      return null;
    },
    print: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
  };

  try {
    const apiLog = [];
    const view = new SatMapView({
      api: async (ep, payload) => {
        apiLog.push({ ep, payload });
        if (ep === 'guangzhu/pro-report/export-pdf') {
          if (payload?.preview_only) {
            return {
              ok: true,
              html: '<!DOCTYPE html><html><body><section id="gz-report-page-1">光筑专业报告第1页</section><section id="gz-report-page-6">光筑专业报告第6页</section></body></html>',
            };
          }
          return {
            ok: true,
            pdf_path: 'C:/Users/demo/Downloads/光筑专业报告.pdf',
            download_url: '/api/guangzhu/pro-report/download/rep-01.pdf',
            filename: '光筑专业报告_测试厂房.pdf',
            opened_natively: true,
            page_count: 6,
          };
        }
        if (ep === 'satmap/export-delivery-bundle') {
          return {
            ok: true,
            bundle_id: 'bnd-2026-01',
            folder_name: '光筑工程交付包_测试厂房',
            display_path: 'Downloads/光筑工程交付包_测试厂房',
            opened_natively: true,
            file_count: 4,
            download_zip_url: '/api/satmap/delivery-bundles/bnd-2026-01.zip',
            files: [
              { key: 'report_pdf', filename: '01_光筑专业报告.pdf', format: 'pdf', download_url: '/api/dl/1' },
              { key: 'master_dxf', filename: '02_总平面施工图.dxf', format: 'dxf', download_url: '/api/dl/2' },
              { key: 'bom_csv', filename: '03_设备材料清册.csv', format: 'csv', download_url: '/api/dl/3' },
              { key: 'verification_json', filename: '04_合规校核.json', format: 'json', download_url: '/api/dl/4' },
            ],
          };
        }
        if (ep === 'satmap/sync-to-3d') {
          return {
            ok: true,
            project_id: 'proj-3d-99',
            version: 2,
            roof_id: 'my-sat-proj-3d-99',
          };
        }
        if (ep === 'satmap/engineering-health-check') {
          return {
            ok: true,
            overall_status: 'pass',
            score: 100,
            pass_count: 8,
            warn_count: 0,
            fail_count: 0,
            ready_for_delivery: true,
            items: [
              { id: 'dc_ac_ratio', code: 'CHK-01', status: 'pass' },
              { id: 'cold_voc_margin', code: 'CHK-02', status: 'pass' },
              { id: 'hot_vmpp_window', code: 'CHK-03', status: 'pass' },
              { id: 'roof_dead_load', code: 'CHK-04', status: 'pass' },
              { id: 'wind_uplift_setback', code: 'CHK-05', status: 'pass' },
              { id: 'dc_voltage_drop', code: 'CHK-06', status: 'pass' },
              { id: 'shading_loss', code: 'CHK-07', status: 'pass' },
              { id: 'financial_return', code: 'CHK-08', status: 'pass' },
            ],
          };
        }
        return {};
      },
    });

    view.layoutModules({ quiet: true, autoCreateRoof: true });

    // 1. Step 1 Streamlined UX: 1-Line Guided Bar, Next-Step CTA, Folded AI Popover, Quick-Start Guide, Modal MF Studio
    view.step = 1;
    view.mfState.openInStep1 = true;
    const step1Html = view.html();
    assert.match(step1Html, /data-sat-workflow-guide/);
    assert.match(step1Html, /data-sat-action="next-step"/);
    assert.match(step1Html, /satmap-ai-popover/);
    assert.match(step1Html, /data-sat-quickstart="1"/);
    assert.match(step1Html, /data-sat-mf-modal="step1"/);
    assert.match(step1Html, /data-sat-action="preview-pro-report"/);

    // 2. Native PDF Export (open_native: true) + In-App 6-Page Preview Modal + ZERO window.open!
    const pdfRes = await exportPvsystProfessionalReportV2(view, { openNative: true });
    assert.equal(pdfRes.ok, true);
    assert.equal(pdfRes.openedNatively, true);
    const pdfCall = apiLog.find((c) => c.ep === 'guangzhu/pro-report/export-pdf' && !c.payload?.preview_only);
    assert.ok(pdfCall, 'Should call guangzhu/pro-report/export-pdf first');
    assert.equal(pdfCall.payload.open_native, true);

    const prevRes = await previewGuangzhuProReport(view);
    assert.equal(prevRes.ok, true);
    assert.equal(view.linkage3d.reportPreview.open, true);
    const modalHtml = renderProReportPreviewModal(view);
    assert.match(modalHtml, /data-sat-pro-report-modal="1"/);
    assert.match(modalHtml, /data-sat-report-page="1"/);
    assert.match(modalHtml, /data-sat-report-page="6"/);

    // Also test CAD Blueprint preview & Executive Report preview — ZERO window.open calls!
    view.exportCadPdf();
    assert.equal(view.linkage3d.reportPreview.open, true);
    view.exportExecutiveReport('owner');
    assert.equal(view.linkage3d.reportPreview.open, true);
    assert.equal(windowOpenCalls, 0, 'Must NEVER invoke window.open anywhere in satmap workflows');

    // 3. Step 5 3-Card Delivery Center + 8-Item Engineering Compliance Health Check
    const clientHc = computeClientEngineeringHealthCheck(view);
    assert.equal(clientHc.items.length, 8);
    assert.deepEqual(clientHc.items.map((i) => i.code), [
      'CHK-01', 'CHK-02', 'CHK-03', 'CHK-04', 'CHK-05', 'CHK-06', 'CHK-07', 'CHK-08',
    ]);

    const backendHc = await runEngineeringHealthCheck(view);
    assert.equal(backendHc.source, 'backend');
    assert.equal(backendHc.score, 100);
    assert.equal(backendHc.pass_count, 8);

    const bundleRes = await exportSatmapDeliveryBundle(view, { syncTo3D: true, openFolder: true });
    assert.equal(bundleRes.ok, true);
    assert.equal(bundleRes.file_count, 4);
    assert.equal(bundleRes.synced_3d?.projectId, 'proj-3d-99');

    view.step = 5;
    const step5Html = view.html();
    assert.match(step5Html, /data-sat-delivery-center="1"/);
    assert.match(step5Html, /data-sat-delivery-card="report"/);
    assert.match(step5Html, /data-sat-delivery-card="cad"/);
    assert.match(step5Html, /data-sat-delivery-card="bundle"/);
    assert.match(step5Html, /data-sat-health-check="1"/);

    // 4. Zero visible "PVsyst" & Strict Bilingual Purity across all 5 steps + open modals in ZH and EN!
    for (const step of [1, 2, 3, 4, 5]) {
      view.step = step;
      setLang('zh');
      const visZh = stripHtmlVisibleText(view.html());
      assert.doesNotMatch(visZh, /pvsyst/i, `Step ${step} ZH visible text must have 0 "PVsyst" occurrences`);
      const pureZh = toPureZhText(visZh);
      assert.doesNotMatch(pureZh, /[A-Za-z]/, `Step ${step} ZH must have 0 ASCII letters, got: ${pureZh.match(/[A-Za-z]+/g)?.slice(0, 5)}`);

      setLang('en');
      const visEn = stripHtmlVisibleText(view.html());
      assert.doesNotMatch(visEn, /pvsyst/i, `Step ${step} EN visible text must have 0 "PVsyst" occurrences`);
      assert.doesNotMatch(visEn, /[\u4e00-\u9fff]/, `Step ${step} EN must have 0 Chinese chars, got: ${visEn.match(/[\u4e00-\u9fff]+/g)?.slice(0, 5)}`);
    }
  } finally {
    setLang('zh');
    if (prevWindow === undefined) {
      delete globalThis.window;
    } else {
      globalThis.window = prevWindow;
    }
  }
});
