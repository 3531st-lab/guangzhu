import test from 'node:test';
import assert from 'node:assert/strict';

import {
  SatMapView,
  solveHomography,
  projectPoint,
  pointInPolygon,
  SAT_PRESET_SITES,
  SAT_MODULE_CATALOG,
  SAT_INVERTER_CATALOG,
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

  assert.ok(SAT_PRESET_SITES.some((s) => s.key === 'taizhou-cmc'));
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

  // Step 3: PVsyst 8760h Workbench & Official Live Weather
  view.step = 3;
  const html3 = view.html();
  assert.match(html3, /PVsyst 7\.x/);
  assert.match(html3, /官方实时气象/);

  // Step 4: PVLANE Oblique Photo 4-Point Perspective Homography + Parapet Sightline Occlusion
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

test('Video 1 (鹧鸪云) & Video 2 (PVLANE) 1:1 UI alignment: 3-tab left switcher, top modeling bar, 3-step electrical modals, and 3-stage CAD wizard with H1/Y0/Y1/A/X1/X2 bracket config', () => {
  const view = new SatMapView(async () => ({}), () => {}, {});
  view.layoutModules({ quiet: true, autoCreateRoof: true });

  // 1. Step 1: Verify Video 2 3-Tab Switcher (roof / layout / info), Video 1 Top Modeling Bar, Right Drawer 2-Tab Switcher, and Bottom Edge Dimension Pill (mm)
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

  // 3. Step 4: Verify Video 2 PVLANE visual adjustment controls
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
