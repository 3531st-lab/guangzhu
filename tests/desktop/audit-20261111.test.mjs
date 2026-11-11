import test from "node:test";
import assert from "node:assert/strict";

import {
  computeFinancialDcf25Yr,
  computeStringSizingAndCables,
} from "../../desktop/web/pro-engineering-core.js";
import {
  SatMapView,
  SAT_MODULE_CATALOG,
  SAT_INVERTER_CATALOG,
} from "../../desktop/web/satmap-view.js";
import { InnovationLabView } from "../../desktop/web/innovation-lab.js";
import { buildSatmap3DGeometrySpec } from "../../desktop/web/pro-3d-twin-engine.js";
import {
  computeClientFallbackPvsyst,
  pvsystProFoldMarkup,
} from "../../desktop/web/pvsyst-workbench.js";
import { ParkView } from "../../desktop/web/park-view.js";
import { translateHtmlToEn, setLang } from "../../desktop/web/i18n.js";

test("P1-01 & E14: DCF returns null IRR/payback on non-recovering cashflows and preserves explicit 0 inputs", () => {
  const dcf = computeFinancialDcf25Yr({
    dcKw: 100,
    annualKwhYear1: 1000,
    capexPerW: 8,
    tariffSelfRmb: 0.2,
    tariffFeedInRmb: 0.1,
  });
  assert.equal(dcf.irrPct, null);
  assert.equal(dcf.staticPaybackYears, null);
  assert.equal(dcf.dynamicPaybackYears, null);

  const dcfZero = computeFinancialDcf25Yr({
    dcKw: 100,
    annualKwhYear1: 120000,
    capexPerW: 3.0,
    selfConsumptionRatio: 0,
    discountRatePct: 0,
    tariffSelfRmb: 1.0,
    tariffFeedInRmb: 0.4,
  });
  assert.equal(dcfZero.selfConsumptionRatio, 0);
  assert.equal(dcfZero.discountRatePct, 0);
  assert.equal(dcfZero.weightedTariffRmb, 0.4);
});

test("P1-02..05, P1-07, P2-11, P2-13..14: SatMap + InnovationLab wiring, voltage, BESS, Pareto, BOM DXF & honest preset wording", async () => {
  const notices = [];
  const sv = new SatMapView(async () => {
    throw new Error("offline");
  }, (m) => notices.push(m));
  await sv.runAiDetectRoof();
  assert.ok(notices.at(-1).includes("离线回退示例") && notices.at(-1).includes("非实景图像识别"));
  assert.ok(!sv.html().includes("AI 智能识顶"));
  assert.ok(sv.html().includes("载入标准厂房样板"));

  const wiredCount = sv.strings.reduce((s, v) => s + v.moduleCount, 0);
  const expectedDcKw = Number(((wiredCount * sv.getSelectedModule().stc_w) / 1000).toFixed(2));
  assert.equal(sv.summary.dcKw, expectedDcKw);

  const small = new SatMapView(async () => {
    throw new Error("offline");
  }, () => {});
  small.roofOutlineM = sv.roofOutlineM;
  small.hasRoof = true;
  small.modules = sv.modules.slice(0, 4).map((m) => ({ ...m }));
  small.inverterSelectionMode = "manual";
  small.computeElectricalAllocation();
  assert.equal(small.mpptRows[0].ok, false);

  const customInv = { ...SAT_INVERTER_CATALOG[0], mppt_v_max: 800, max_dc_v: 1500 };
  const siz = computeStringSizingAndCables({
    module: SAT_MODULE_CATALOG[0],
    inverter: customInv,
    modulesPerString: 18,
    customTminC: -28,
  });
  assert.equal(siz.mpptSafe, false);
  assert.equal(siz.allWindowSafe, false);

  const lab = new InnovationLabView({ satmapView: sv, onNotice: (m) => notices.push(m) });
  const bess = lab.computeBessAndCarbon();
  lab.applyBessToSatmap();
  assert.equal(sv.selfConsumptionRatio, Number((bess.selfUseAfterPct / 100).toFixed(4)));
  assert.ok(sv.financialDcf.bessCapexWan > 0);

  const selected = lab.computeParetoPortfolio()[0];
  lab.applySchemeToSatmap(0);
  assert.equal(selected.capKwp, sv.summary.dcKw);
  assert.equal(selected.dcAc, sv.summary.dcAcRatio);

  const bom = sv.getEngineeringBom();
  const bomDxf = sv.buildDxfString("bom_schedule");
  assert.ok(bom.items.length > 12);
  assert.equal(bom.items.filter((i) => !bomDxf.includes(i.name)).length, 0);

  sv.bessPowerKw = 0;
  sv.bessCapacityKwh = 0;
  sv.recomputeEngineeringAnalyses();
  assert.equal(sv.buildDxfString("bess_storage").includes("BESS 100kW/215kWh"), false);
  assert.equal(sv.buildDxfString("bess_storage").includes("No BESS Configured"), true);
  assert.equal(sv.renderCadSvg("bess_storage").includes("未配置储能系统"), true);
});

test("P1-06: 3D module geometry preserves orthonormal basis and exact area across arbitrary azimuths", () => {
  for (const azimuthDeg of [180, 90, 45, 0, 270, 135]) {
    const g = buildSatmap3DGeometrySpec({
      roofType: "flat",
      roofOutlineM: [[0, 0], [20, 0], [20, 20], [0, 20]],
      tiltDeg: 20,
      azimuthDeg,
      modules: [{ id: "M1", cx: 10, cy: 10, w: 1.134, h: 2.278 }],
    });
    const m = g.modules3d[0];
    const a = m.corners3d[1].map((v, i) => v - m.corners3d[0][i]);
    const b = m.corners3d[3].map((v, i) => v - m.corners3d[0][i]);
    const cross = [
      a[1] * b[2] - a[2] * b[1],
      a[2] * b[0] - a[0] * b[2],
      a[0] * b[1] - a[1] * b[0],
    ];
    const area = Math.hypot(...cross);
    const basisDot = m.rightVec.reduce((sum, v, i) => sum + v * m.upSlopeVec[i], 0);
    assert.ok(Math.abs(basisDot) < 1e-12);
    assert.ok(Math.abs(area - 1.134 * 2.278) < 1e-9);
  }
});

test("P1-08, P1-10, P2-12, P2-15: Backend PVsyst authority, stale async discard, i18n input preservation, and ParkView selection", async () => {
  const sim = computeClientFallbackPvsyst({ dc_kw: 100, ac_kw: 85 });
  sim.summary.e_grid_kwh = 12345;
  const result = { project: { site: { lat: 32, lon: 120 } }, metrics: { dc_kw: 100 }, pvsyst: sim };
  assert.equal(pvsystProFoldMarkup(result).includes("12,345"), true);
  assert.equal(pvsystProFoldMarkup(result, { params: {} }).includes("12,345"), true);
  assert.equal(pvsystProFoldMarkup(result, { params: { _clientPreview: true, tilt_deg: 28 } }).includes("12,345"), false);

  let release;
  const delayed = new SatMapView(
    () =>
      new Promise((r) => {
        release = r;
      }),
    () => {}
  );
  delayed.refreshPvsystData({ fetchBackend: true });
  await Promise.resolve();
  delayed.roofOutlineM = [[0, 0], [24, 0], [24, 16], [0, 16]];
  delayed.hasRoof = true;
  delayed.layoutModules({ quiet: true, autoCreateRoof: false });
  const beforeAnnual = delayed.summary.annualKwh;
  release({ summary: { dc_kw: 280, e_grid_kwh: 999999, specific_yield_kwh_kwp: 3571, pr_pct: 82 } });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(delayed.summary.annualKwh, beforeAnnual);
  assert.notEqual(delayed.pvsystData.summary.dc_kw, 280);

  setLang("en");
  const translated = translateHtmlToEn(
    '<input type="text" value="ACME ABC Factory" placeholder="搜索地点"/><input value="GZ-PV-2026"/>'
  );
  assert.ok(translated.includes('value="ACME ABC Factory"'));
  assert.ok(translated.includes('value="GZ-PV-2026"'));
  setLang("zh");

  const calls = [];
  const park = new ParkView(
    async (p, body) => {
      calls.push({ p, body });
      return {};
    },
    {},
    () => {},
    () => {},
    () => {}
  );
  park.id = "audit";
  park.current = {
    park: {
      id: "audit",
      buildings: [
        { template: "A", x_m: 10, y_m: 10 },
        { template: "B", x_m: 100, y_m: 100 },
      ],
      settings: {},
    },
  };
  park.roofs = [];
  const boxes = [
    { checked: false, dataset: { pick: "A" } },
    { checked: false, dataset: { pick: "B" } },
  ];
  const picked = await park.applyOneClickSetup(
    { querySelectorAll: (s) => (s.includes(":checked") ? [] : boxes) },
    { quiet: true }
  );
  assert.equal(picked.length, 0);
  assert.equal(calls.length, 0);
});
