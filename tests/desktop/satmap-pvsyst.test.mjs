import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  SatMapView,
  solveHomography,
  projectPoint,
  pointInPolygon,
  SAT_PRESET_SITES,
  SAT_MODULE_CATALOG,
  SAT_INVERTER_CATALOG,
  MAX_SAT_ZOOM,
} from '../../desktop/web/satmap-view.js';
import {
  renderPvsystWorkbench,
  renderLiveWeatherPanel,
  renderPvsystWaterfallSvg,
  renderPvsystMonthlyTableAndChart,
  renderPvsystOptimizationAndSunPath,
  renderPvsystProbabilitiesAndTuning,
  pvsystProFoldMarkup,
  computeClientFallbackPvsyst,
} from '../../desktop/web/pvsyst-workbench.js';
import { getLang, setLang, toggleLang, toPureEnText, toPureZhText } from '../../desktop/web/i18n.js';
import { InnovationLabView, TAIZHOU_BENCHMARK_CASES } from '../../desktop/web/innovation-lab.js';
import {
  parsePanFile,
  serializePanFile,
  parseOndFile,
  serializeOndFile,
  computeStringSizingAndCables,
  computeStructuralVerification,
  computeShiftLoadSelfUse,
  computeFinancialDcf25Yr,
} from '../../desktop/web/pro-engineering-core.js';
import {
  computeSolarVectorBjt,
  buildSatmap3DGeometrySpec,
  compute3DPhysicalShading,
  computeAnnual3DShadingSummary,
  mountSatmap3DTwin,
} from '../../desktop/web/pro-3d-twin-engine.js';

test('solveHomography and projectPoint map 4 unit-square corners to arbitrary oblique quad with <1e-6 error', () => {
  const srcQuad = [
    [0, 0],
    [1, 0],
    [1, 1],
    [0, 1],
  ];
  const dstQuad = [
    [218, 178],
    [716, 168],
    [838, 392],
    [112, 408],
  ];
  const H = solveHomography(srcQuad, dstQuad);
  assert.equal(H.length, 9);
  for (let i = 0; i < 4; i++) {
    const [u, v] = projectPoint(H, srcQuad[i][0], srcQuad[i][1]);
    assert.ok(Math.abs(u - dstQuad[i][0]) < 1e-6, `Corner ${i} u mismatch: ${u} vs ${dstQuad[i][0]}`);
    assert.ok(Math.abs(v - dstQuad[i][1]) < 1e-6, `Corner ${i} v mismatch: ${v} vs ${dstQuad[i][1]}`);
  }
  const [cx, cy] = projectPoint(H, 0.5, 0.5);
  assert.ok(cx > 350 && cx < 600);
  assert.ok(cy > 220 && cy < 360);
});

test('SatMapView starts with a 100% clean satellite map before design, then lays out double-slope roof and MPPT table after user design', async () => {
  const notices = [];
  const view = new SatMapView(
    async () => ({}),
    (msg) => notices.push(msg),
    {}
  );
  await view.load();

  for (const tzKey of [
    'taizhou-cmc',
    'taizhou-xiangtai-warehouse',
    'taizhou-jielouwei-bipv',
    'taizhou-shenyuan-alloy',
    'taizhou-municipal-admin',
    'taizhou-jingjiang-shipbuild',
    'taizhou-taixing-chem',
    'taizhou-jiangyan-equip',
  ]) {
    assert.ok(SAT_PRESET_SITES.some((s) => s.key === tzKey), `Expected SAT_PRESET_SITES to include ${tzKey}`);
  }
  assert.ok(SAT_PRESET_SITES.some((s) => s.key === 'shandong-zibo'));
  assert.ok(SAT_MODULE_CATALOG.length >= 4);
  assert.ok(SAT_INVERTER_CATALOG.length >= 4);

  // 1. Before user outlines roof or clicks 一键铺设, the satellite map must be 100% clean (0 modules, no pre-run drawing)
  assert.equal(view.hasRoof, false, 'Map must not have pre-drawn roof before user designs');
  assert.equal(view.hasLaidOut, false, 'Map must not have pre-laid modules before user designs');
  assert.equal(view.modules.length, 0, 'Expected 0 modules before user designs');
  assert.equal(view.summary.moduleCount, 0);

  // 2a. By default (single_slope), user outlines roof and clicks 一键铺设 without unwanted auto-split
  assert.equal(view.roofType, 'single_slope');
  view.ensureRoofOutline({ withDefaultKeepouts: true });
  view.layoutModules({ quiet: true, autoCreateRoof: true });

  assert.equal(view.hasRoof, true);
  assert.equal(view.hasLaidOut, true);
  assert.ok(view.modules.length > 200, `Expected >200 modules placed after layoutModules, got ${view.modules.length}`);
  assert.equal(view.summary.northCount, 0, 'Default single_slope must not auto-split into north/south');
  assert.equal(view.summary.southCount, view.modules.length);

  // 2b. When user explicitly selects 双坡屋面 (double_slope), layout splits along ridge into South & North slopes
  view.roofType = 'double_slope';
  view.layoutModules({ quiet: true });
  assert.ok(view.summary.southCount > 0 && view.summary.northCount > 0, 'Both south and north slopes should have modules when double_slope is selected');
  assert.ok(view.summary.dcKw > 100);
  assert.ok(view.mpptRows.length >= 9);
  assert.ok(view.mpptRows.some((r) => r.status === '正常' && r.workCurrentA > 0 && r.shortCurrentA > r.workCurrentA));

  // Verify no module center falls inside the two skylight keepout strips (x in [-34, 34] and y in [-9.2, -7.4] or [7.4, 9.2])
  for (const m of view.modules) {
    if (m.cx >= -34.0 && m.cx <= 34.0) {
      assert.ok(!(m.cy >= -9.2 && m.cy <= -7.4), `Module ${m.id} collided with north skylight strip`);
      assert.ok(!(m.cy >= 7.4 && m.cy <= 9.2), `Module ${m.id} collided with south skylight strip`);
    }
  }

  // 3. Relocating to a new searched location resets to a clean satellite map at the new factory
  view.applyLocationCandidate({
    name: '宁德时代新能源科技股份有限公司',
    address: '福建省宁德市蕉城区漳湾镇新港路2号',
    lat: 26.719073,
    lon: 119.555596,
    zoom: 18,
  });
  assert.equal(view.hasRoof, false, 'Relocating to a new address must start with a clean map');
  assert.equal(view.modules.length, 0, 'Relocating to a new address must clear previous roof modules');
});

test('SatMapView renders all 5 workflow steps and all 4 CAD engineering drawings', () => {
  const view = new SatMapView(async () => ({}), () => {}, {});

  // Step 1: Satellite Map & AI Roof Layout
  view.step = 1;
  const html1 = view.html();
  assert.match(html1, /卫星地图 AI 光伏设计工作台/);
  assert.match(html1, /一键铺设/);
  assert.match(html1, /标定比例尺/);
  assert.match(html1, /双坡屋面/);

  // Step 2: Electrical Design & MPPT Table
  view.step = 2;
  const html2 = view.html();
  assert.match(html2, /MPPT 组串分配/);
  assert.match(html2, /最大工作电流/);
  assert.match(html2, /最大短路电流/);
  assert.match(html2, /确认电气设计并映射屋面组串/);

  // Step 3: 8760h Workbench & Official Live Weather
  view.step = 3;
  const html3 = view.html();
  assert.match(html3, /8760h/);
  assert.match(html3, /官方实时气象/);

  // Step 4: Oblique Photo 4-Point Perspective Homography + Parapet Sightline Occlusion
  view.step = 4;
  const html4 = view.html();
  assert.match(html4, /女儿墙视线遮挡区域/);
  assert.match(html4, /四点透视配准/);

  // Step 5: 4 CAD Drawings (光伏排布图 / 组串图 / 防雷接地图 / 支架图)
  view.step = 5;
  for (const [sheetKey, title] of [
    ['layout', '光伏排布图'],
    ['string', '组串接线图'],
    ['grounding', '防雷接地图'],
    ['bracket', '支架剖面与立面图'],
  ]) {
    view.cadSheet = sheetKey;
    const html5 = view.html();
    assert.ok(html5.includes(title), `Expected CAD sheet ${sheetKey} to contain ${title}`);
    const dxf = view.buildDxfString(sheetKey);
    assert.ok(dxf.includes('SECTION') && dxf.includes('ENTITIES') && dxf.includes('EOF'));
  }
});

test('PVsyst 7.x workbench renders 16-stage waterfall, 12-month balances, 9x9 heatmap, sun path, and P50/P90 curve', () => {
  const sim = computeClientFallbackPvsyst({
    lat: 36.858844,
    lon: 118.778089,
    dc_kw: 417.6,
    ac_kw: 330.0,
    tilt_deg: 6,
    azimuth_deg: 180,
  });

  assert.equal(sim.waterfall.length, 16, 'Waterfall must have all 16 PVsyst stages');
  assert.equal(sim.monthly_balances.length, 12, 'Monthly balances must have 12 months');
  assert.equal(sim.optimization_matrix.tilts.length, 9);
  assert.equal(sim.optimization_matrix.azimuths.length, 9);
  assert.ok(sim.summary.pr_pct > 70 && sim.summary.pr_pct < 96);
  assert.ok(sim.probabilities.p50_kwh > sim.probabilities.p90_kwh);
  assert.ok(sim.probabilities.p90_kwh > sim.probabilities.p99_kwh);

  const wbHtml = renderPvsystWorkbench(sim);
  assert.match(wbHtml, /GlobHor/);
  assert.match(wbHtml, /GlobInc/);
  assert.match(wbHtml, /GlobEff/);
  assert.match(wbHtml, /E_Array/);
  assert.match(wbHtml, /E_Grid/);
  assert.match(wbHtml, /Performance Ratio/);

  const foldHtml = pvsystProFoldMarkup({
    project_id: 'demo-proj',
    project: { site: { lat: 32.4562, lon: 119.9231 }, roof: { type: 'metal', slope_deg: 6 } },
    summary: { dc_kw: 250, yield_kwh: { p50: 295000 } },
  });
  assert.match(foldHtml, /data-pvsyst-workbench/);
  assert.match(foldHtml, /data-pvsyst-section="waterfall"/);
  assert.match(foldHtml, /data-pvsyst-section="monthly"/);
  assert.match(foldHtml, /data-pvsyst-section="optimization-sunpath"/);
  assert.match(foldHtml, /data-pvsyst-section="probabilities-tuning"/);
});

test('SatMapView removes preset case dropdown, evaluates weather-driven optimal tilt/spacing, and executes AI requirement design', async () => {
  const view = new SatMapView(async () => ({}), () => {}, {});
  await view.load();

  const html = view.html();
  // Ensure no preset case dropdown is rendered in the UI
  assert.doesNotMatch(html, /data-sat-field="presetSite"/);
  assert.doesNotMatch(html, /示范厂房切换/);
  // Ensure China-wide search bar and weather-coupled angle evaluation table are rendered
  assert.match(html, /data-sat-action="search-location"/);
  assert.match(html, /data-sat-weather-eval/);
  assert.match(html, /当地实时官方气象驱动的倾角设计/);

  const wxEval = view.evaluateWeatherAndAngles();
  assert.ok(wxEval.candidates.length >= 8);
  assert.ok(wxEval.weatherOptimalTiltDeg >= 6 && wxEval.weatherOptimalTiltDeg <= 35);
  assert.ok(wxEval.roofOptimalWanKwh > 10);

  // Test AI requirement one-click design parsing & execution
  view.aiRequirement = '目标装机 180kW，平屋面，按气象单瓦最优倾角，退距 1.2m';
  await view.runAiAutopilot();
  assert.equal(view.roofType, 'flat');
  assert.equal(view.edgeSetbackM, 1.2);
  assert.equal(view.tiltDeg, wxEval.weatherOptimalTiltDeg);
  assert.ok(view.summary.dcKw <= 180.5 && view.summary.dcKw > 150);
  assert.ok(view.aiExecutionNote.includes('已按要求完成设计'));
});

test('C-shaped roof (泰州学院济川路校区): zero polygon offset after drawing, orthogonal keepouts, auto direction recognition, and 100% interior string & home-run routing', () => {
  const view = new SatMapView(async () => ({}), () => {}, {});
  const W = 920, H = 580;

  // Simulate user clicking 8 vertices of a C-shaped roof on screen (matching Screenshot 1: top wing 84m, left wing 49m, bottom wing 59m)
  const clickedScreenPts = [
    [260, 120], // P1 top-left
    [740, 120], // P2 top-right
    [740, 195], // P3 top-wing inner-right
    [345, 195], // P4 courtyard top-left
    [345, 345], // P5 courtyard bottom-left
    [600, 345], // P6 bottom-wing inner-right
    [600, 415], // P7 bottom-right
    [260, 415], // P8 bottom-left
  ];

  // Convert screen clicks to local meters BEFORE roof is closed (hasRoof = false)
  const drawnMeters = clickedScreenPts.map(([sx, sy]) => view.canvasToLocalMeters(W, H, sx, sy));
  view.roofOutlineM = drawnMeters.map(([x, y]) => [Number(x.toFixed(2)), Number(y.toFixed(2))]);
  view.hasRoof = true;

  // Verify Bug #1 fix: after closing the roof, every vertex maps back to the EXACT screen pixel where the user clicked (zero shift!)
  for (let i = 0; i < clickedScreenPts.length; i++) {
    const [sxAfter, syAfter] = view.localMetersToCanvas(W, H, view.roofOutlineM[i][0], view.roofOutlineM[i][1]);
    assert.ok(Math.abs(sxAfter - clickedScreenPts[i][0]) < 0.5, `Vertex P${i + 1} shifted in X: ${sxAfter} vs ${clickedScreenPts[i][0]}`);
    assert.ok(Math.abs(syAfter - clickedScreenPts[i][1]) < 0.5, `Vertex P${i + 1} shifted in Y: ${syAfter} vs ${clickedScreenPts[i][1]}`);
  }

  // Verify Bug #3 fix: principal building angle is automatically recognized as 0 deg (east-west/north-south orthogonal walls)
  view.layoutModules({ quiet: true, autoCreateRoof: false });
  assert.ok(view.modules.length > 100, `Expected >100 modules on C-shaped roof, got ${view.modules.length}`);

  // Verify Bug #2 fix: drawing a straight rectangular keepout on screen after layout stays an axis-aligned rectangle (never rotated into a 45° diamond!)
  const [kx0, ky0] = view.canvasToLocalMeters(W, H, 450, 355);
  const [kx1, ky1] = view.canvasToLocalMeters(W, H, 540, 405);
  const keepoutPoly = [
    [kx0, ky0],
    [kx1, ky0],
    [kx1, ky1],
    [kx0, ky1],
  ];
  const keepoutScreen = keepoutPoly.map(([mx, my]) => view.localMetersToCanvas(W, H, mx, my));
  assert.ok(Math.abs(keepoutScreen[0][1] - keepoutScreen[1][1]) < 1e-4, 'Keepout top edge must be horizontal on screen');
  assert.ok(Math.abs(keepoutScreen[1][0] - keepoutScreen[2][0]) < 1e-4, 'Keepout right edge must be vertical on screen');

  view.obstacles.push({
    id: 'keepout-test-rect',
    name: '禁布区 #1',
    kind: 'skylight',
    polygon: keepoutPoly,
  });
  view.layoutModules({ quiet: true, autoCreateRoof: false });

  // Verify no module overlaps the keepout rectangle
  for (const m of view.modules) {
    assert.ok(!pointInPolygon([m.cx, m.cy], keepoutPoly), `Module ${m.id} must not be inside keepout`);
  }

  // Verify Bug #4 fix: 100% of intra-string wire segments and home-run paths stay inside the C-shaped roof polygon (never crossing the central courtyard!)
  assert.ok(view.strings.length >= 5, `Expected >=5 strings, got ${view.strings.length}`);
  for (const st of view.strings) {
    for (const [p0, p1] of st.wireSegmentsM) {
      for (const t of [0.2, 0.5, 0.8]) {
        const pt = [p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t];
        assert.ok(
          pointInPolygon(pt, view.roofOutlineM),
          `Intra-string wire of ${st.id} crossed outside C-shaped roof into courtyard at (${pt[0].toFixed(1)}, ${pt[1].toFixed(1)})`
        );
      }
    }
    const hr = st.homeRunPathM || [];
    assert.ok(hr.length >= 2, `String ${st.id} must have a home-run path`);
    for (let i = 0; i + 1 < hr.length; i++) {
      const p0 = hr[i];
      const p1 = hr[i + 1];
      for (const t of [0.25, 0.5, 0.75]) {
        const pt = [p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t];
        assert.ok(
          pointInPolygon(pt, view.roofOutlineM),
          `Home-run cable of ${st.id} crossed outside C-shaped roof into courtyard at (${pt[0].toFixed(1)}, ${pt[1].toFixed(1)})`
        );
      }
    }
  }

  // Verify CAD string drawing renders cleanly in orthogonal frame
  const cadStringSvg = view.renderCadSvg('string');
  assert.match(cadStringSvg, /光伏组串接线与逆变器布置图/);
  assert.match(cadStringSvg, /INV-1/);
});

test('End-to-end UI alignment: 3-tab left switcher, top modeling bar, 3-step electrical modals, and 3-stage CAD wizard with H1/Y0/Y1/A/X1/X2 bracket config', () => {
  const view = new SatMapView(async () => ({}), () => {}, {});
  view.layoutModules({ quiet: true, autoCreateRoof: true });

  // 1. Step 1: Verify 3-Tab Switcher (roof / layout / info), Top Modeling Bar, Right Drawer 2-Tab Switcher, and Bottom Edge Dimension Pill (mm)
  view.step = 1;
  const html1 = view.html();
  assert.match(html1, /data-sat-left-tab="roof"/);
  assert.match(html1, /data-sat-left-tab="layout"/);
  assert.match(html1, /data-sat-left-tab="info"/);
  assert.match(html1, /satmap-v1-modelbar/);
  assert.match(html1, /data-sat-action="toggle-shadow"/);
  assert.match(html1, /data-sat-action="open-elec-flow"/);
  assert.match(html1, /data-sat-right-tab="layout"/);
  assert.match(html1, /data-sat-right-tab="elec"/);
  assert.match(html1, /data-sat-field="liveEdgeLengthMm"/);

  // 2. Verify Video 1 Electrical Modals (请选择组串方式 -> 逆变器选型 7档功率段 -> MPPT 组串汇总 + 生成直流线缆)
  view.showStringModeModal = true;
  const htmlStringModal = view.html();
  assert.match(htmlStringModal, /请选择组串方式/);
  assert.match(htmlStringModal, /快速组串/);
  assert.match(htmlStringModal, /DIY 组串/);

  view.showStringModeModal = false;
  view.showInverterModal = true;
  const htmlInvModal = view.html();
  assert.match(htmlInvModal, /150kW以上/);
  assert.match(htmlInvModal, /data-sat-inv-power="100_150"/);
  assert.match(htmlInvModal, /data-sat-inv-power="50_100"/);
  assert.match(htmlInvModal, /data-sat-inv-power="30_50"/);
  assert.match(htmlInvModal, /data-sat-inv-power="10_30"/);
  assert.match(htmlInvModal, /10kW以下/);

  view.showInverterModal = false;
  view.showMpptModal = true;
  const htmlMpptModal = view.html();
  assert.match(htmlMpptModal, /自动生成直流线缆/);
  view.showMpptModal = false;

  // 3. Step 4: Verify visual adjustment controls
  view.step = 4;
  const html4 = view.html();
  assert.match(html4, /data-sat-field="effectModuleStyle"/);
  assert.match(html4, /data-sat-field="effectOpacityPct"/);
  assert.match(html4, /data-sat-field="effectGridSharpnessPct"/);
  assert.match(html4, /data-sat-field="effectGlarePct"/);

  // 4. Step 5: Verify Video 1 3-Stage CAD Wizard (1. 基本参数 -> 2. 支架设计 -> 3. 生成图纸) and H1/Y0/Y1/A/X1/X2 Bracket Config
  view.step = 5;
  view.cadSheet = 'bracket';
  const html5 = view.html();
  assert.match(html5, /data-sat-cad-wiz="basic"/);
  assert.match(html5, /data-sat-cad-wiz="bracket"/);
  assert.match(html5, /data-sat-cad-wiz="sheets"/);
  assert.match(html5, /data-sat-bracket="h1Mm"/);
  assert.match(html5, /data-sat-bracket="y0Mm"/);
  assert.match(html5, /data-sat-bracket="y1Mm"/);
  assert.match(html5, /data-sat-bracket="angleDeg"/);
  assert.match(html5, /data-sat-bracket="x1Mm"/);
  assert.match(html5, /data-sat-bracket="x2Mm"/);
  assert.match(html5, /支架侧视图预览/);
  assert.match(html5, /支架正视图预览/);
});

test('Multi-point polygon keepout drawing (禁区也用多点画): preserves exact clicked vertices, avoids modules and wires, and supports multiple consecutive polygons', () => {
  const view = new SatMapView(async () => ({}), () => {}, {});
  const W = 920, H = 580;

  // 1. Draw a roof first and lay out modules
  view.drawingPointsM = [
    [-36, -18],
    [36, -18],
    [36, 18],
    [-36, 18],
  ];
  view.finishPolygonRoof();
  view.layoutModules({ quiet: true, autoCreateRoof: false });
  const initialCount = view.modules.length;
  assert.ok(initialCount > 150);

  // 2. Switch to multi-point obstacle tool and click 5 vertices of an irregular pentagon skylight/vent
  view.activeTool = 'obstacle_poly';
  const obsScreenClicks = [
    [420, 250],
    [510, 245],
    [535, 295],
    [480, 330],
    [410, 305],
  ];
  view.drawingObstaclePointsM = obsScreenClicks.map(([sx, sy]) => view.canvasToLocalMeters(W, H, sx, sy));

  const htmlDuringDraw = view.html();
  assert.match(htmlDuringDraw, /data-sat-tool="obstacle_poly"/);
  assert.match(htmlDuringDraw, /完成禁布区闭合 \(5点\)/);

  const createdObs = view.finishPolygonObstacle();
  assert.ok(createdObs, 'finishPolygonObstacle should return the created obstacle');
  assert.equal(createdObs.polygon.length, 5);
  assert.equal(view.drawingObstaclePointsM.length, 0);

  // 3. Verify zero vertex shift: each vertex of the 5-point keepout maps back to the exact screen pixel clicked
  for (let i = 0; i < obsScreenClicks.length; i++) {
    const [sxAfter, syAfter] = view.localMetersToCanvas(W, H, createdObs.polygon[i][0], createdObs.polygon[i][1]);
    assert.ok(Math.abs(sxAfter - obsScreenClicks[i][0]) < 0.6, `Obstacle vertex ${i + 1} X shifted: ${sxAfter} vs ${obsScreenClicks[i][0]}`);
    assert.ok(Math.abs(syAfter - obsScreenClicks[i][1]) < 0.6, `Obstacle vertex ${i + 1} Y shifted: ${syAfter} vs ${obsScreenClicks[i][1]}`);
  }

  // 4. Verify modules automatically avoided the 5-point polygon keepout
  assert.ok(view.modules.length < initialCount, 'Module count should decrease after adding pentagon keepout');
  for (const m of view.modules) {
    assert.ok(!pointInPolygon([m.cx, m.cy], createdObs.polygon), `Module ${m.id} center must not be inside 5-point polygon keepout`);
  }
});

test('Zero external software names or video demos in UI/SVG while preserving all modals, 8760h simulation, and 16 CAD drawings', () => {
  const view = new SatMapView(async () => ({}), () => {}, {});
  view.layoutModules({ quiet: true, autoCreateRoof: true });

  // 1. Verify no video hub, no <video> tags, and no external software names appear across Steps 1..5
  for (const s of [1, 2, 3, 4, 5]) {
    view.step = s;
    const stepHtml = view.html();
    assert.doesNotMatch(stepHtml, /data-sat-video-hub/);
    assert.doesNotMatch(stepHtml, /<video\b/i);
    assert.doesNotMatch(stepHtml, /鹧鸪云/);
    assert.doesNotMatch(stepHtml, /PVLANE/);
    assert.doesNotMatch(stepHtml, /PVsyst 7/);
    assert.doesNotMatch(stepHtml, /三大相关软件/);
  }

  // 2. Verify Location Picker Modal & Stacked 4-Sheet CAD Preview
  view.step = 1;
  view.showLocationPickerModal = true;
  const v1Html = view.html();
  assert.match(v1Html, /地图拾取经纬度/);
  assert.match(v1Html, /请调整至清晰位置，作为卫星设计底图/);
  assert.match(v1Html, /satmap-right-map-strip/);
  view.showLocationPickerModal = false;

  view.step = 5;
  view.cadShowAllFourStacked = true;
  const cadStackedHtml = view.html();
  assert.match(cadStackedHtml, /satmap-cad-dark-nav/);
  assert.match(cadStackedHtml, /储能 AI 模拟/);
  assert.match(cadStackedHtml, /内部报告中心/);
  assert.match(cadStackedHtml, /业主报告中心/);
  assert.match(cadStackedHtml, /ALL_16_SHEETS/);

  // 3. Verify Project Open/New Modal & Dynamic 2D Roof Thumbnail in Step 4
  view.step = 1;
  view.showPvlaneStartModal = true;
  const v2Html = view.html();
  assert.match(v2Html, /新建 \/ 导入光伏工程方案/);
  assert.match(v2Html, /打开项目文件/);
  view.showPvlaneStartModal = false;

  view.step = 4;
  const effHtml = view.html();
  assert.match(effHtml, /参照下方实时 2D 排布缩略图角点顺序/);

  // 4. Verify Step 3 System Voltage-Temperature Envelope & Near Shadings 3D SVG
  view.step = 3;
  const pvHtml = view.html();
  assert.match(pvHtml, /data-pvsyst-section="system-near-shading"/);
  assert.match(pvHtml, /组串电压-温度包络校核/);
  assert.match(pvHtml, /Near Shadings 3D/);

  // 5. Verify Complex U-Shape Roof + Multi-Point Keepout & CAD 2x2 Grid / Bracket Schematics
  view.loadUShapeComplexRoofDemo();
  assert.equal(view.hasRoof, true);
  assert.equal(view.roofOutlineM.length, 8);
  assert.equal(view.obstacles.length, 3);
  assert.ok(view.modules.length >= 150, `Expected >=150 modules in U-shape roof, got ${view.modules.length}`);
  assert.ok(view.strings.length >= 8, `Expected >=8 strings in U-shape roof, got ${view.strings.length}`);
  for (const st of view.strings) {
    for (const [p0, p1] of st.wireSegmentsM) {
      const mid = [(p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5];
      assert.ok(pointInPolygon(mid, view.roofOutlineM), `U-shape string ${st.id} wire midpoint crossed outside U-roof`);
    }
    assert.ok(st.homeRunPathM.length >= 2, `U-shape string ${st.id} must have a connected interior home-run path`);
    for (let i = 0; i + 1 < st.homeRunPathM.length; i++) {
      const p0 = st.homeRunPathM[i];
      const p1 = st.homeRunPathM[i + 1];
      for (const t of [0.25, 0.5, 0.75]) {
        const pt = [p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t];
        assert.ok(pointInPolygon(pt, view.roofOutlineM), `U-shape string ${st.id} home-run crossed outside U-roof at (${pt[0].toFixed(1)}, ${pt[1].toFixed(1)})`);
      }
    }
  }

  view.step = 5;
  view.cadWizardTab = 'bracket';
  view.cadShowAllFourStacked = false;
  view.cadGrid2x2 = true;
  const cadGridHtml = view.html();
  assert.match(cadGridHtml, /混凝土支架侧面示意图/);
  assert.match(cadGridHtml, /混凝土支架正面示意图/);
  assert.match(cadGridHtml, /GRID_16_ALL/);

  // 6. Verify 16-Sheet Complete Engineering CAD Suite without any external brand names
  const allSheets = view.getAllCadSheets();
  assert.equal(allSheets.length, 16);
  const expectedKeys = [
    'layout',
    'string',
    'grounding',
    'bracket',
    'single_line',
    'cable_tray',
    'foundation',
    'bom_schedule',
    'pvlane_perspective',
    'pvsyst_diagram',
    'clamp_detail',
    'ac_cabinet',
    'om_walkway',
    'bess_storage',
    'pvlane_birdseye',
    'pvsyst_near_shading',
  ];
  assert.deepEqual(allSheets.map((s) => s[0]), expectedKeys);

  for (const key of expectedKeys) {
    const svg = view.renderCadSvg(key);
    assert.match(svg, /<svg viewBox="0 0 920 520"/, `Sheet ${key} must render a valid 920x520 CAD SVG`);
    assert.doesNotMatch(svg, /鹧鸪云|PVLANE|PVsyst/, `Sheet ${key} must not contain external software names`);
    const dxf = view.buildDxfString(key);
    assert.match(dxf, /SECTION/);
    assert.match(dxf, /ENTITIES/);
    assert.match(dxf, /EOF/);
  }

  // 7. Verify DL-00 (bom_schedule) lists all 16 sheets (01 through 16) in the Drawing Index table
  const bomSvg = view.renderCadSvg('bom_schedule');
  assert.match(bomSvg, />01<\/text>/);
  assert.match(bomSvg, />16<\/text>/);
  assert.match(bomSvg, /PV-02/);
});

test('Step 1 multi-tab switching, interactive tariff/BESS modal, and dynamic payback/IRR calculation', () => {
  const view = new SatMapView(async () => ({}), () => {}, {});
  view.layoutModules({ quiet: true, autoCreateRoof: true });

  // Left Panel Tab 1 ('roof'), Tab 2 ('layout'), Tab 3 ('info')
  view.step = 1;
  view.leftPanelTab = 'roof';
  assert.match(view.html(), /1\. 屋面建模与底图校准/);

  view.leftPanelTab = 'layout';
  const layoutTabHtml = view.html();
  assert.match(layoutTabHtml, /2\. 屋面布局与阵列微调/);
  assert.match(layoutTabHtml, /data-sat-tool="toggle_module"/);
  assert.match(layoutTabHtml, /data-sat-array-preset="2x9"/);

  view.leftPanelTab = 'info';
  const infoTabHtml = view.html();
  assert.match(infoTabHtml, /3\. 屋面与光储经济信息/);
  assert.match(infoTabHtml, /25 年全生命周期财务指标/);

  // Right Panel Tab 1 ('layout') vs Tab 2 ('elec') should not duplicate layout inputs when in 'elec' mode
  view.rightDrawerTab = 'elec';
  const elecDrawerHtml = view.html();
  assert.match(elecDrawerHtml, /逆变器选型方式与容配比/);
  assert.doesNotMatch(elecDrawerHtml, /组件排布参数 \(2×9 标准阵列单元\)/);

  // Tariff & BESS Modal and dynamic payback/IRR recalculation
  const basePayback = view.summary.paybackYears;
  view.tariffRmb = 1.15;
  view.selfConsumptionRatio = 0.92;
  view.capexPerW = 2.85;
  view.computeElectricalAllocation();
  assert.ok(view.summary.paybackYears < basePayback, `Higher tariff & lower CAPEX should shorten payback: ${view.summary.paybackYears} vs ${basePayback}`);
  assert.ok(view.summary.irrPct > 15);
  assert.ok(view.summary.npv25Wan > 0);

  view.showTariffModal = true;
  const modalHtml = view.html();
  assert.match(modalHtml, /输入用电信息与光储经济参数/);
  assert.doesNotMatch(modalHtml, /鹧鸪云|PVLANE|PVsyst/);
});

test('Step 2 IEC 62548 voltage-temperature envelope, cable voltage drop check, MPPT CSV export, and Step 4 before/after comparison', () => {
  const view = new SatMapView(async () => ({}), () => {}, {});
  view.layoutModules({ quiet: true, autoCreateRoof: true });

  // 1. Step 2 Electrical Workbench: verify IEC 62548 & GB 50797 voltage drop checks and CSV export button
  view.step = 2;
  const step2Html = view.html();
  assert.match(step2Html, /IEC 62548 电压温度包络校核/);
  assert.match(step2Html, /GB 50797 交直流电缆压降校核/);
  assert.match(step2Html, /data-sat-action="export-mppt-csv"/);
  assert.doesNotMatch(step2Html, /鹧鸪云|PVLANE|PVsyst/);

  // 2. Verify exportMpptCsv() outputs a complete UTF-8 BOM CSV with all MPPT rows
  const csv = view.exportMpptCsv();
  assert.ok(csv.startsWith('\uFEFF'), 'CSV should start with UTF-8 BOM');
  assert.match(csv, /极端低温开路电压Voc\(-10°C\)/);
  assert.match(csv, /直流线缆平均压降ΔUdc%/);
  assert.match(csv, /SG110CX-P2#1/);
  assert.match(csv, /MPPT1/);

  // 3. Step 4 Effect Studio: verify Before/After Split-Screen Comparison mode
  view.step = 4;
  view.effectCompareMode = true;
  view.effectCompareSplitPct = 45;
  const step4Html = view.html();
  assert.match(step4Html, /data-sat-effect="toggle-compare"/);
  assert.match(step4Html, /data-sat-field="effectCompareSplitPct"/);
  assert.doesNotMatch(step4Html, /鹧鸪云|PVLANE|PVsyst/);
});

test('Super-Zoom Z24 (32x deeper than Z19): cursor-centered zoom locks roof point under mouse, zoomToFitRoof centers close-up, and ancestor tile over-zoom crops exact sub-quadrant', () => {
  assert.equal(MAX_SAT_ZOOM, 24);
  const view = new SatMapView(async () => ({}), () => {}, {});
  view.layoutModules({ quiet: true, autoCreateRoof: true });

  const W = 920, H = 580;
  // Pick a roof corner and find its screen coordinates at Z18
  const [cornerMx, cornerMy] = view.roofOutlineM[0];
  const [sxBefore, syBefore] = view.localMetersToCanvas(W, H, cornerMx, cornerMy);

  // Zoom in 16x from Z18 -> Z22 anchored at that exact roof corner pixel (sxBefore, syBefore)
  view.setZoom(22, { anchorSx: sxBefore, anchorSy: syBefore, canvasW: W, canvasH: H });
  assert.equal(view.zoom, 22);
  const [sxAfter, syAfter] = view.localMetersToCanvas(W, H, cornerMx, cornerMy);
  assert.ok(Math.abs(sxAfter - sxBefore) < 0.8, `Expected corner X to stay locked under cursor: ${sxAfter} vs ${sxBefore}`);
  assert.ok(Math.abs(syAfter - syBefore) < 0.8, `Expected corner Y to stay locked under cursor: ${syAfter} vs ${syBefore}`);

  // Zoom all the way to Z24 (64x deeper than Z18, ~0.008 m/px so 1 module is >140px wide)
  view.setZoom(24);
  assert.equal(view.zoom, 24);
  assert.ok(view.metersPerPx < 0.012, `Expected <0.012 m/px at Z24, got ${view.metersPerPx}`);

  // Verify ancestor sub-quadrant tile over-zoom from cached Z18 tile when at Z22 (scale = 16, sw = 16px)
  const fakeImg = { width: 256, height: 256 };
  view.tileCache.set('gaode_hyb/18/100/200', { status: 'loaded', img: fakeImg, usedFallback: false, fallbackSubShift: 0 });
  const patch = view.getBestSatelliteTilePatch('gaode_hyb', 22, 100 * 16 + 3, 200 * 16 + 5);
  assert.ok(patch && patch.img === fakeImg, 'Expected Z22 tile request to resolve sub-quadrant from cached Z18 ancestor');
  assert.equal(patch.sw, 16);
  assert.equal(patch.sh, 16);
  assert.equal(patch.sx, 3 * 16);
  assert.equal(patch.sy, 5 * 16);

  // Verify zoomToFitRoof centers on the roof and zooms to >= Z20
  view.setZoom(18);
  const fitZ = view.zoomToFitRoof({ canvasW: W, canvasH: H });
  assert.ok(fitZ >= 20 && fitZ <= 24, `Expected zoomToFitRoof to select >=20, got ${fitZ}`);
});

test('Dedicated standalone pages (#pvsyst, #oblique, #cad), Innovation Lab (#lab), and ZH/EN bilingual switching', () => {
  const view = new SatMapView(async () => ({}), () => {}, {});
  view.layoutModules({ quiet: true, autoCreateRoof: true });

  // 1. Standalone page mode switching
  view.setStandaloneMode('pvsyst');
  assert.equal(view.step, 3);
  assert.match(view.html(), /data-sat-standalone="pvsyst"/);

  view.setStandaloneMode('oblique');
  assert.equal(view.step, 4);
  assert.match(view.html(), /data-sat-standalone="oblique"/);

  view.setStandaloneMode('cad');
  assert.equal(view.step, 5);
  assert.match(view.html(), /data-sat-standalone="cad"/);

  view.setStandaloneMode(null);
  assert.equal(view.step, 1);

  // 2. Bilingual ZH / EN toggle across SatMapView and InnovationLabView
  setLang('en');
  assert.equal(getLang(), 'en');
  const enSatHtml = view.html();
  assert.match(enSatHtml, /Satellite AI PV Design Workbench/);
  assert.match(enSatHtml, /Auto-Layout PV Array/);

  const lab = new InnovationLabView({
    onOpenCaseInSatmap: (c) => view.loadBenchmarkCase(c),
  });
  const enLabPareto = lab.html();
  assert.match(enLabPareto, /Guangzhu Innovation Lab/);
  assert.match(enLabPareto, /Pareto Frontier Candidate Matrix/);

  lab.state.activeTab = 'bess-carbon';
  const enLabBess = lab.html();
  assert.match(enLabBess, /PV\+BESS Dispatch & Carbon Asset Configuration/);
  assert.match(enLabBess, /EU CBAM Offset/);
  const bcGec = lab.computeBessAndCarbon();
  assert.equal(bcGec.domesticGreenRevWan, bcGec.gecRevWan);
  assert.equal(
    bcGec.totalExtraGainWan,
    Number((bcGec.annualBessArbitrageWan + bcGec.demandChargeSavingWan + bcGec.gecRevWan).toFixed(2)),
    'GEC and CCER/CBAM must never be double-counted into domestic cashflow total'
  );
  lab.domesticEnvMode = 'ccer';
  const bcCcer = lab.computeBessAndCarbon();
  assert.equal(bcCcer.domesticGreenRevWan, bcCcer.ccerRevWan);
  assert.equal(
    bcCcer.totalExtraGainWan,
    Number((bcCcer.annualBessArbitrageWan + bcCcer.demandChargeSavingWan + bcCcer.ccerRevWan).toFixed(2))
  );
  lab.domesticEnvMode = 'gec';

  lab.state.activeTab = 'benchmark';
  const enLabBench = lab.html();
  assert.match(enLabBench, /Metered Blind-Test MAPE = 5\.12%/);
  assert.match(enLabBench, /7 Industrial Roofs Mean Diff = 0\.7%/);
  assert.equal(TAIZHOU_BENCHMARK_CASES.length, 8);

  // Load a Taizhou benchmark case into SatMapView
  view.loadBenchmarkCase(TAIZHOU_BENCHMARK_CASES[0]);
  assert.ok(view.summary.dcKw > 100);

  // Restore default Chinese ('zh') for subsequent tests
  toggleLang();
  assert.equal(getLang(), 'zh');
  assert.match(view.html(), /卫星地图 AI 光伏设计工作台/);
});

test('Topnav deduplication, Lab-SatMap live bidirectional sync, realistic payback, auto-populated Step 4, and strict pure ZH/EN text', () => {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const indexHtml = fs.readFileSync(path.resolve(__dirname, '../../desktop/web/index.html'), 'utf8');
  const stylesCss = fs.readFileSync(path.resolve(__dirname, '../../desktop/web/styles.css'), 'utf8');

  // 1. Topnav deduplication & single-line non-wrapping layout
  const navMatch = indexHtml.match(/<nav class="navtabs"[^>]*>([\s\S]*?)<\/nav>/);
  assert.ok(navMatch, 'Expected <nav class="navtabs"> in index.html');
  assert.doesNotMatch(navMatch[1], /href="#(?:pvsyst|oblique|cad)"/, 'Redundant #pvsyst/#oblique/#cad tabs must not clutter topnav');
  assert.match(navMatch[1], /href="#new"/);
  assert.match(navMatch[1], /href="#satmap"/);
  assert.match(navMatch[1], /href="#lab"/);
  assert.match(navMatch[1], /href="#park"/);
  assert.match(navMatch[1], /href="#records"/);
  assert.doesNotMatch(indexHtml, /Agnes Harness|EN \/ 中文/);
  assert.match(stylesCss, /\.navtabs\s+a\s*\{[^}]*white-space:\s*nowrap/);

  // 2. Step 4 auto-populates modules when entered directly (never empty 0 块 / 0 kWp) + solar hour & string color check
  setLang('zh');
  const freshView = new SatMapView(async () => ({}), () => {}, {});
  assert.equal(freshView.modules.length, 0, 'Step 1 starts clean before user action');
  freshView.step = 4;
  const step4Html = freshView.html();
  assert.ok(freshView.modules.length > 0, 'Entering Step 4 auto-populates roof PV layout');
  assert.doesNotMatch(step4Html, /已投射组件：\s*0\s*块/);
  assert.match(step4Html, /effectSolarHour/);
  assert.match(step4Html, /effectShowStringColors/);
  assert.match(step4Html, /冬至日.*女儿墙阴影校核/);

  // 3. Step 2 professional grid-connection, transformer ratio, anti-backflow & SVG verification
  freshView.step = 2;
  const step2Html = freshView.html();
  assert.match(step2Html, /并网电压等级与一次接入方案/);
  assert.match(step2Html, /厂区变压器容量与消纳校核/);
  assert.match(step2Html, /防逆流保护与并网联跳装置/);
  assert.match(step2Html, /动态无功补偿与电能质量校核/);

  // 4. Lab realistic payback/IRR, non-overlapping P1..P5, and live bidirectional sync with SatMapView
  const lab = new InnovationLabView({ satmapView: freshView });
  const portfolio = lab.computeParetoPortfolio();
  assert.equal(portfolio.length, 5);
  const seenCoords = new Set();
  for (const p of portfolio) {
    assert.ok(p.paybackYr >= 2.5 && p.paybackYr <= 7.5, `Expected realistic C&I payback (2.5~7.5 yr), got ${p.paybackYr}`);
    assert.ok(p.irrPct >= 12 && p.irrPct <= 35, `Expected realistic IRR (12%~35%), got ${p.irrPct}%`);
    const coordKey = `${p.capKwp}:${p.specificYieldH}`;
    assert.ok(!seenCoords.has(coordKey), `Duplicate overlapping point ${p.id} at ${coordKey}`);
    seenCoords.add(coordKey);
  }
  lab.applySchemeToSatmap(0, { jump: false }); // Apply P1 (tilt 8°)
  assert.equal(freshView.tiltDeg, 8);
  lab.bessRatioPct = 25;
  lab.bessDurationH = 2;
  lab.applyBessToSatmap({ jump: false });
  assert.ok(freshView.bessPowerKw > 0 && freshView.bessCapacityKwh > 0);

  // 5. Strict Pure-Chinese ('zh') and Pure-English ('en') text guarantees across all steps & tabs
  const stripTags = (h) => h.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '').replace(/<[^>]+>/g, ' ');

  setLang('en');
  for (const st of [1, 2, 3, 4, 5]) {
    freshView.step = st;
    const visibleEn = stripTags(freshView.html());
    const cjkMatch = visibleEn.match(/[\u4e00-\u9fff]+/g);
    assert.equal(cjkMatch, null, `Step ${st} in EN mode must contain 0 Chinese chars, found: ${cjkMatch?.slice(0, 5)}`);
  }
  for (const tab of ['pareto', 'bess-carbon', 'benchmark']) {
    lab.activeTab = tab;
    const visibleLabEn = stripTags(lab.html());
    const cjkLab = visibleLabEn.match(/[\u4e00-\u9fff]+/g);
    assert.equal(cjkLab, null, `Lab tab ${tab} in EN mode must contain 0 Chinese chars, found: ${cjkLab?.slice(0, 5)}`);
  }

  setLang('zh');
  for (const st of [1, 2, 3, 4, 5]) {
    freshView.step = st;
    const visibleZh = toPureZhText(stripTags(freshView.html()));
    const engMatch = visibleZh.match(/[A-Za-z]+/g);
    assert.equal(engMatch, null, `Step ${st} in ZH mode must contain 0 English letters after DOM localization, found: ${engMatch?.slice(0, 5)}`);
  }
  for (const tab of ['pareto', 'bess-carbon', 'benchmark']) {
    lab.activeTab = tab;
    const visibleLabZh = toPureZhText(stripTags(lab.html()));
    const engLab = visibleLabZh.match(/[A-Za-z]+/g);
    assert.equal(engLab, null, `Lab tab ${tab} in ZH mode must contain 0 English letters after DOM localization, found: ${engLab?.slice(0, 5)}`);
  }
});

test('Professional Engineering Suite: .PAN/.OND round-trip, dual-slope string/MPPT isolation & sub_arrays, GB 55001 structural zones, 25-yr DCF IRR, layered 16-sheet DXF & BOM CSV', () => {
  setLang('zh');

  // 1. .PAN & .OND file serializer/parser round-trip + custom import into SatMapView
  const baseMod = SAT_MODULE_CATALOG[0];
  const panStr = serializePanFile(baseMod);
  assert.match(panStr, /PVObject_=pvModule/);
  const parsedMod = parsePanFile(panStr, 'Jinko580.PAN');
  assert.equal(parsedMod.stc_w, baseMod.stc_w);
  assert.ok(Math.abs(parsedMod.voc_v - baseMod.voc_v) < 0.05);
  assert.ok(Math.abs(parsedMod.vmp_v - baseMod.vmp_v) < 0.05);

  const baseInv = SAT_INVERTER_CATALOG[0];
  const ondStr = serializeOndFile(baseInv);
  assert.match(ondStr, /PVObject_=pvGInverter/);
  const parsedInv = parseOndFile(ondStr, 'Sungrow110.OND');
  assert.equal(parsedInv.rated_ac_kw, baseInv.rated_ac_kw);
  assert.equal(parsedInv.mppt_count, baseInv.mppt_count);
  assert.equal(parsedInv.max_dc_v, baseInv.max_dc_v);

  // 2. Climate-zone IEC 62548 string sizing: Severe Cold (Harbin 45.75°N) vs Warm South (Foshan 23.02°N)
  const harbinSizing = computeStringSizingAndCables({
    module: baseMod,
    inverter: baseInv,
    modulesPerString: 18,
    lat: 45.75,
    lon: 126.63,
  });
  const foshanSizing = computeStringSizingAndCables({
    module: baseMod,
    inverter: baseInv,
    modulesPerString: 18,
    lat: 23.02,
    lon: 113.12,
  });
  assert.ok(harbinSizing.tMinC <= -25, `Expected Harbin extreme cold <= -25°C, got ${harbinSizing.tMinC}`);
  assert.ok(harbinSizing.vocColdV > foshanSizing.vocColdV, 'Harbin cold Voc must exceed Foshan cold Voc');
  assert.ok(harbinSizing.nMax <= foshanSizing.nMax, 'Severe cold zone must allow fewer or equal max series modules');

  // 3. Dual-slope (double_slope) strict South/North string & MPPT isolation + heterogeneous 8760h sub_arrays
  const view = new SatMapView(async () => ({}), () => {}, {});
  view.lat = 32.48;
  view.lon = 119.90;
  view.roofType = 'double_slope';
  view.roofSlopeDeg = 10;
  view.layoutModules({ quiet: true, autoCreateRoof: true });
  assert.ok(view.summary.southCount > 0 && view.summary.northCount > 0, 'Expected both South and North modules on double_slope roof');
  assert.ok(view.strings.length >= 4);

  for (const st of view.strings) {
    const slopesInString = new Set(st.modules.map((m) => m.slope));
    assert.equal(slopesInString.size, 1, `String ${st.id} must NEVER mix South and North slope modules!`);
  }
  const mpptSlopeMap = new Map();
  for (const st of view.strings) {
    const key = `${st.inverterIndex}:${st.mpptIndex}`;
    if (!mpptSlopeMap.has(key)) mpptSlopeMap.set(key, st.slope);
    assert.equal(mpptSlopeMap.get(key), st.slope, `MPPT channel ${key} must NEVER mix South and North strings!`);
  }
  const subSummary = view.pvsystData?.sub_arrays_summary;
  assert.ok(Array.isArray(subSummary) && subSummary.length === 2, 'Expected 2 orientation sub-arrays on double_slope roof');
  const southSub = subSummary.find((x) => x.azimuth_deg === 180);
  const northSub = subSummary.find((x) => x.azimuth_deg === 0);
  assert.ok(southSub && northSub);
  assert.ok(
    southSub.specific_yield_kwh_kwp > northSub.specific_yield_kwh_kwp,
    `South slope specific yield (${southSub.specific_yield_kwh_kwp}) must exceed North slope (${northSub.specific_yield_kwh_kwp}) in Northern Hemisphere`
  );

  // Import custom .PAN & .OND directly into SatMapView
  const customPan = panStr.replace(/PNom\s*=\s*[\d.]+/, 'PNom=615').replace(/Model\s*=\s*.+/, 'Model=GZ-TOPCon-615W');
  const importedMod = view.importPanFileText(customPan, 'GZ615.PAN');
  assert.equal(importedMod.stc_w, 615);
  assert.equal(view.getSelectedModule().stc_w, 615);
  assert.ok(view.exportPanFile().includes('615'));
  assert.ok(view.exportOndFile().includes('PVObject_=pvGInverter'));

  // 4. GB 55001 / GB 50009 Wind, Snow & Roof Corner/Edge/Interior Zone Verification
  const flatStruct = computeStructuralVerification({
    lat: 32.48,
    lon: 119.90,
    roofType: 'flat',
    tiltDeg: 15,
    buildingHeightM: 15,
    roughnessCategory: 'B',
    module: baseMod,
    moduleCount: 400,
  });
  assert.equal(flatStruct.zones.length, 3);
  assert.ok(flatStruct.zones[2].wkUpliftKnM2 > flatStruct.zones[1].wkUpliftKnM2);
  assert.ok(flatStruct.zones[1].wkUpliftKnM2 > flatStruct.zones[0].wkUpliftKnM2);
  assert.ok(flatStruct.cornerBallastKgPerMod >= flatStruct.interiorBallastKgPerMod);
  assert.ok(flatStruct.totalBallastTon > 0);

  const metalStruct = computeStructuralVerification({
    lat: 32.48,
    lon: 119.90,
    roofType: 'double_slope',
    tiltDeg: 8,
    buildingHeightM: 15,
    roughnessCategory: 'B',
    module: baseMod,
    moduleCount: 400,
  });
  assert.equal(metalStruct.zones[0].clampsPerMod, 4);
  assert.equal(metalStruct.zones[2].clampsPerMod, 6, 'Corner high-suction zone on metal roof must reinforce to 6 clamps/module');
  assert.ok(metalStruct.maxClampTensionKn <= metalStruct.clampAllowableKn);

  // 5. C&I Shift-Load Coupling & Exact 25-Year DCF Solver Verification
  const s1 = computeShiftLoadSelfUse({ shiftMode: 'single_shift', dcKw: 300, acKw: 240, transformerKva: 1250 });
  const s2 = computeShiftLoadSelfUse({ shiftMode: 'double_shift', dcKw: 300, acKw: 240, transformerKva: 1250 });
  const s3 = computeShiftLoadSelfUse({ shiftMode: 'continuous_24h', dcKw: 300, acKw: 240, transformerKva: 1250 });
  assert.ok(s3.effectiveSelfUseRatio > s2.effectiveSelfUseRatio && s2.effectiveSelfUseRatio > s1.effectiveSelfUseRatio);

  const dcf = computeFinancialDcf25Yr({
    dcKw: 300,
    annualKwhYear1: 360000,
    capexPerW: 3.15,
    selfConsumptionRatio: 0.82,
    tariffSelfRmb: 0.88,
    tariffFeedInRmb: 0.39,
    discountRatePct: 6.0,
  });
  assert.equal(dcf.schedule.length, 25);
  assert.equal(dcf.cashflowsWan.length, 26);
  assert.ok(dcf.schedule[12].costWan > dcf.schedule[11].costWan, 'Year 13 must include inverter replacement reserve');
  assert.ok(dcf.dynamicPaybackYears > dcf.staticPaybackYears, 'Discounted payback must exceed static payback');
  assert.ok(dcf.lcoeRmbPerKwh > 0.12 && dcf.lcoeRmbPerKwh < 0.45, `Expected realistic LCOE, got ${dcf.lcoeRmbPerKwh}`);
  const rIrr = dcf.irrPct / 100;
  const npvAtIrr = dcf.cashflowsWan.reduce((acc, cf, t) => acc + cf / Math.pow(1 + rIrr, t), 0);
  assert.ok(Math.abs(npvAtIrr) < 0.08, `Bisection IRR (${dcf.irrPct}%) must drive 25-yr NPV to ~0, got ${npvAtIrr}`);

  // 6. Layered 16-Sheet AutoCAD DXF + 4x4 Master DXF + 15-Item Engineering BOM CSV
  const allSheets = view.getAllCadSheets();
  assert.equal(allSheets.length, 16);
  const dxfLengths = new Set();
  for (const [shKey] of allSheets) {
    const dxf = view.buildDxfString(shKey);
    assert.match(dxf, /TABLES/);
    assert.match(dxf, /LAYER/);
    assert.match(dxf, /TITLE_BLOCK/);
    assert.match(dxf, /\r\n0\r\nTEXT\r\n/);
    dxfLengths.add(`${shKey}:${dxf.length}`);
  }
  assert.equal(dxfLengths.size, 16);
  const masterDxf = view.buildMasterDxfString();
  assert.ok(masterDxf.length > view.buildDxfString('layout').length * 6, 'Master 4x4 16-sheet DXF must contain all 16 sheets');

  const bomCsv = view.exportBomCsv();
  assert.ok(bomCsv.startsWith('\uFEFF'));
  assert.match(bomCsv, /工程数量/);
  assert.match(bomCsv, /静止无功发生器动态补偿柜/);
  assert.ok(view.getEngineeringBom().items.length >= 15);
});

test('3D Digital Twin & Physical Ray-Traced Shading: NOAA solar vectors, gable/flat 3D geometry, Möller-Trumbore 3-diode mismatch, and strict ZH/EN purity in 3D mode', () => {
  setLang('zh');

  // 1. Astronomical solar vector & clear-sky irradiance monotonicity across seasons
  const winNoon = computeSolarVectorBjt(32.48, 119.92, '2026-12-21', 12.0);
  const eqNoon = computeSolarVectorBjt(32.48, 119.92, '2026-03-21', 12.0);
  const sumNoon = computeSolarVectorBjt(32.48, 119.92, '2026-06-21', 12.0);
  assert.ok(sumNoon.altitudeDeg > eqNoon.altitudeDeg && eqNoon.altitudeDeg > winNoon.altitudeDeg);
  assert.ok(winNoon.altitudeDeg > 25 && winNoon.dniWm2 > 300 && winNoon.ghiWm2 > 200);

  const winAm = computeSolarVectorBjt(32.48, 119.92, '2026-12-21', 9.0);
  const winPm = computeSolarVectorBjt(32.48, 119.92, '2026-12-21', 15.0);
  assert.ok(winAm.azimuthDeg < 180 && winAm.direction[0] > 0, 'Morning sun must be in SE quadrant (+X East)');
  assert.ok(winPm.azimuthDeg > 180 && winPm.direction[0] < 0, 'Afternoon sun must be in SW quadrant (-X West)');

  // 2. Gable (double_slope) 3D geometry builder: elevated ridge + opposing South/North normals
  const gableView = new SatMapView({ api: async () => ({}), notice: () => {} });
  gableView.lat = 32.48;
  gableView.lon = 119.92;
  gableView.roofType = 'double_slope';
  gableView.roofSlopeDeg = 12;
  gableView.buildingHeightM = 12;
  gableView.layoutModules({ quiet: true, autoCreateRoof: true });
  gableView.computeElectricalAllocation();

  const gableSpec = buildSatmap3DGeometrySpec(gableView.build3DTwinPayload());
  assert.ok(gableSpec.ridgePeakY > gableSpec.buildingHeightM + 1.0, 'Double-slope 3D gable ridge must rise above eave height');
  assert.ok(gableSpec.modules3d.length > 50);
  const southMods = gableSpec.modules3d.filter((m) => m.slope === 'south');
  const northMods = gableSpec.modules3d.filter((m) => m.slope === 'north');
  assert.ok(southMods.length > 0 && northMods.length > 0);
  assert.ok(southMods[0].normalVec[2] > 0, 'South-slope 3D panel normal must tilt toward +Z (South)');
  assert.ok(northMods[0].normalVec[2] < 0, 'North-slope 3D panel normal must tilt toward -Z (North)');
  assert.ok(gableSpec.inverters3d.length >= 1 && gableSpec.cableTrays3d.length >= 1);

  // 3. Flat roof with tall parapet + rooftop penthouse obstacle -> Möller-Trumbore ray-tracing & 3-bypass-diode electrical loss
  const flatView = new SatMapView({ api: async () => ({}), notice: () => {} });
  flatView.lat = 36.65;
  flatView.lon = 117.12;
  flatView.roofType = 'flat';
  flatView.tiltDeg = 20;
  flatView.rowSpacingM = 0.65;
  flatView.parapetHeightMm = 200;
  flatView.layoutModules({ quiet: true, autoCreateRoof: true });

  const lowParapetSpec = buildSatmap3DGeometrySpec(flatView.build3DTwinPayload());
  const shadeLowNoon = compute3DPhysicalShading(lowParapetSpec, { lat: 36.65, lon: 117.12, dateStr: '2026-12-21', hourBjt: 12.0 });
  const shadeLowEarly = compute3DPhysicalShading(lowParapetSpec, { lat: 36.65, lon: 117.12, dateStr: '2026-12-21', hourBjt: 8.3 });
  assert.ok(shadeLowEarly.linearBeamShadePct >= shadeLowNoon.linearBeamShadePct, 'Early morning winter shading must exceed solar noon');

  // Raise parapet to 2200mm and place a tall 3.2m elevator penthouse obstacle on the south side
  flatView.parapetHeightMm = 2200;
  const b = flatView.getRoofBoundsM(true);
  flatView.obstacles.push({
    id: 'obs-tall-penthouse',
    name: '南侧电梯机房',
    kind: 'penthouse',
    heightM: 3.2,
    polygon: [
      [-8, b.maxY - 6.5],
      [8, b.maxY - 6.5],
      [8, b.maxY - 2.0],
      [-8, b.maxY - 2.0],
    ],
  });
  const tallObsSpec = buildSatmap3DGeometrySpec(flatView.build3DTwinPayload());
  const shadeTallMorning = compute3DPhysicalShading(tallObsSpec, { lat: 36.65, lon: 117.12, dateStr: '2026-12-21', hourBjt: 9.0 });
  const shadeLowMorning = compute3DPhysicalShading(lowParapetSpec, { lat: 36.65, lon: 117.12, dateStr: '2026-12-21', hourBjt: 9.0 });
  assert.ok(
    shadeTallMorning.linearBeamShadePct > shadeLowMorning.linearBeamShadePct,
    `Expected tall parapet + penthouse (${shadeTallMorning.linearBeamShadePct}%) > low parapet (${shadeLowMorning.linearBeamShadePct}%)`
  );
  assert.ok(shadeTallMorning.diodeActivatedCount > 0, 'Shaded modules must activate bypass diodes');
  assert.ok(
    shadeTallMorning.electricalShadeLossPct >= shadeTallMorning.linearBeamShadePct,
    'Non-linear 3-bypass-diode electrical loss must be >= linear optical beam shade fraction'
  );

  const annSummary = computeAnnual3DShadingSummary(tallObsSpec, { lat: 36.65, lon: 117.12 });
  assert.ok(annSummary.annualElectricalLossPct >= annSummary.annualLinearLossPct);
  assert.equal(annSummary.moduleAnnualLossPct.length, tallObsSpec.modules3d.length);

  // Wind zones assigned on 3D modules
  const zoneSet = new Set(tallObsSpec.modules3d.map((m) => m.windZone));
  assert.ok(zoneSet.has('interior') && (zoneSet.has('edge') || zoneSet.has('corner')));

  // 4. Strict Bilingual Purity ('zh' & 'en') + Zero External Trademarks when is3D = true and in Step 3 Near Shadings 3D
  flatView.is3D = true;
  flatView.refreshPvsystData({ fetchBackend: false });
  const stripTags = (h) => h.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '').replace(/<[^>]+>/g, ' ');

  setLang('en');
  for (const st of [1, 3]) {
    flatView.step = st;
    const rawEn = flatView.html();
    assert.doesNotMatch(rawEn, /鹧鸪云|PVLANE|PVsyst 7/);
    const visEn = stripTags(rawEn);
    assert.doesNotMatch(visEn, /鹧鸪云|PVLANE|PVsyst/i);
    const cjk = visEn.match(/[\u4e00-\u9fff]+/g);
    assert.equal(cjk, null, `3D mode Step ${st} in EN must have 0 Chinese chars, found: ${cjk?.slice(0, 5)}`);
  }

  setLang('zh');
  for (const st of [1, 3]) {
    flatView.step = st;
    const rawZh = flatView.html();
    assert.doesNotMatch(rawZh, /鹧鸪云|PVLANE|PVsyst 7/);
    const visZh = toPureZhText(stripTags(rawZh));
    assert.doesNotMatch(visZh, /鹧鸪云|PVLANE|PVsyst/i);
    const eng = visZh.match(/[A-Za-z]+/g);
    assert.equal(eng, null, `3D mode Step ${st} in ZH must have 0 English letters after localization, found: ${eng?.slice(0, 5)}`);
  }

  // 5. Safe headless fallback for mountSatmap3DTwin when WebGL is absent
  const fakeContainer = {
    style: {},
    children: [],
    replaceChildren(...nodes) { this.children = nodes; },
    append(...nodes) { this.children.push(...nodes); },
  };
  const prevDoc = globalThis.document;
  globalThis.document = {
    createElement: () => ({ style: {}, getContext: () => null }),
  };
  try {
    const handle = mountSatmap3DTwin(fakeContainer, flatView.build3DTwinPayload());
    assert.equal(handle.available, false);
    assert.ok(handle.getShadingSnapshot().modules.length > 0);
    handle.dispose();
  } finally {
    globalThis.document = prevDoc;
  }
});

test('3D roof elevation alignment across single_slope/double_slope/flat, live solar HUD, and ZH unit boundaries', () => {
  setLang('zh');
  for (const roofType of ['single_slope', 'double_slope', 'flat']) {
    const view = new SatMapView(async () => ({}), () => {}, {});
    // Offset roof centroid away from origin to catch any centerX/centerY variable shadowing
    view.roofOutlineM = [
      [15, 22],
      [91, 22],
      [91, 58],
      [15, 58],
    ];
    view.hasRoof = true;
    view.roofType = roofType;
    view.roofSlopeDeg = roofType === 'flat' ? 0 : 8;
    view.tiltDeg = 16;
    view.layoutModules({ quiet: true });
    assert.ok(view.modules.length > 50, `${roofType} should place modules`);

    const spec = buildSatmap3DGeometrySpec(view.build3DTwinPayload());
    for (const m of spec.modules3d) {
      // Module horizontal center must lie inside centered world X/Z bounds
      assert.ok(Math.abs(m.center3d[0]) <= spec.widthM * 0.5 + 0.01, `${roofType} module X out of roof bounds`);
      assert.ok(Math.abs(m.center3d[2]) <= spec.depthM * 0.5 + 0.01, `${roofType} module Z out of roof bounds (${m.center3d[2]})`);
      // Every corner of every module must sit strictly above the local roof plane
      for (const [cx, cy, cz] of m.corners3d) {
        const localRoofY = spec.roofElevationAt(cx + spec.centerX, cz + spec.centerY);
        assert.ok(
          cy >= localRoofY + 0.08,
          `${roofType} module ${m.id} corner Y=${cy.toFixed(3)} buried near/under roof=${localRoofY.toFixed(3)}`
        );
      }
    }

    view.sim3dDateStr = '2026-12-21';
    view.sim3dHourBjt = 9.5;
    const hudHtml = view.render3DMetricsInnerHtml();
    assert.doesNotMatch(hudHtml, /太阳高度角 <b>0\.0°<\/b>/, 'Solar altitude at 09:30 BJT must be > 0°');
  }

  assert.equal(toPureZhText('10kV 高压升压并网'), '10千伏 高压升压并网');
  assert.equal(toPureZhText('谐波畸变率 THDi'), '谐波畸变率');
  assert.equal(toPureZhText('实时水平总辐照 GHI'), '实时水平总辐照');
  assert.equal(toPureZhText('交流 550.0 kWac'), '交流 550.0 千瓦');
});








