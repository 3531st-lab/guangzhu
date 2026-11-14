import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  SAT_MODULE_CATALOG,
  SAT_INVERTER_CATALOG,
  SatMapView,
} from '../../desktop/web/satmap-view.js';
import {
  enrichModuleSpec,
  enrichInverterSpec,
  computeStringSizingAndCables,
} from '../../desktop/web/pro-engineering-core.js';
import {
  buildPvsystV2RequestPayload,
  buildPvsystProfessionalReportV2Html,
  pvsystProFoldMarkup,
} from '../../desktop/web/pvsyst-workbench.js';
import { persistLatestSatmapScheme } from '../../desktop/web/satmap-3d-linkage.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..', '..');

function splitCsvLine(line) {
  const out = [];
  let cur = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      out.push(cur.trim());
      cur = '';
    } else {
      cur += ch;
    }
  }
  out.push(cur.trim());
  return out;
}

function parseCsvCatalog(csvRelPaths, idCol) {
  const byId = new Map();
  for (const rel of csvRelPaths) {
    const raw = fs.readFileSync(path.join(ROOT, rel), 'utf8').trim();
    const lines = raw.split(/\r?\n/).filter(Boolean);
    const headers = splitCsvLine(lines[0]);
    for (let i = 1; i < lines.length; i += 1) {
      const cols = splitCsvLine(lines[i]);
      const row = {};
      headers.forEach((h, idx) => {
        const val = cols[idx] ?? '';
        if (val === '' || val === '规格书未给出') {
          row[h] = null;
        } else if (!Number.isNaN(Number(val)) && ![idCol, 'manufacturer', 'model', 'datasheet_version'].includes(h)) {
          row[h] = Number(val);
        } else {
          row[h] = val;
        }
      });
      if (row[idCol]) byId.set(row[idCol], row);
    }
  }
  return byId;
}

function stripHtmlTagsAndAttrs(html) {
  return html
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<[^>]+>/g, ' ');
}

test('F13-01: SAT_MODULE_CATALOG (4) and SAT_INVERTER_CATALOG (11) match data/catalog/*.csv field-for-field', () => {
  const csvModules = parseCsvCatalog(
    ['data/catalog/modules.csv', 'data/catalog/modules_extended.csv'],
    'module_id'
  );
  const csvInverters = parseCsvCatalog(
    ['data/catalog/inverters.csv', 'data/catalog/inverters_extended.csv'],
    'inverter_id'
  );

  assert.equal(SAT_MODULE_CATALOG.length, 4);
  assert.equal(SAT_INVERTER_CATALOG.length, 11);

  const modFields = [
    ['stc_w', 'stc_w'],
    ['length_m', 'length_m'],
    ['width_m', 'width_m'],
    ['voc_v', 'voc_v'],
    ['vmp_v', 'vmp_v'],
    ['isc_a', 'isc_a'],
    ['imp_a', 'imp_a'],
    ['gamma_pmax_pct_c', 'gamma_pmax_pct_c'],
    ['beta_voc_pct_c', 'beta_voc_pct_c'],
    ['alpha_isc_pct_c', 'alpha_isc_pct_c'],
    ['noct_c', 'noct_c'],
    ['weight_kg', 'weight_kg'],
  ];

  for (const mod of SAT_MODULE_CATALOG) {
    const csvRow = csvModules.get(mod.id);
    assert.ok(csvRow, `Missing module ${mod.id} in CSV catalog`);
    for (const [jsKey, csvKey] of modFields) {
      assert.equal(
        mod[jsKey],
        csvRow[csvKey],
        `Module ${mod.id} field ${jsKey} (${mod[jsKey]}) != CSV ${csvKey} (${csvRow[csvKey]})`
      );
    }
  }

  // Spot-check critical F13-01 module corrections
  const trina605 = SAT_MODULE_CATALOG.find((m) => m.id === 'trina-tsm-605neg19rc20');
  assert.equal(trina605.isc_a, 15.83);
  assert.equal(trina605.beta_voc_pct_c, -0.24);
  assert.equal(trina605.alpha_isc_pct_c, 0.04);
  assert.equal(trina605.noct_c, 43.0);
  assert.equal(trina605.weight_kg, 33.7);

  const invFields = [
    ['rated_ac_kw', 'rated_ac_kw'],
    ['mppt_count', 'mppt_count'],
    ['strings_per_mppt', 'strings_per_mppt'],
    ['max_dc_v', 'max_dc_voltage_v'],
    ['mppt_v_min', 'mppt_min_v'],
    ['mppt_v_max', 'mppt_max_v'],
    ['mppt_full_load_v_min', 'full_load_mppt_min_v'],
    ['mppt_full_load_v_max', 'full_load_mppt_max_v'],
    ['max_mppt_current_a', 'max_input_current_per_mppt_a'],
    ['max_isc_per_mppt_a', 'max_short_circuit_current_per_mppt_a'],
    ['max_eff_pct', 'max_efficiency_pct'],
    ['euro_eff_pct', 'weighted_efficiency_pct'],
  ];

  for (const inv of SAT_INVERTER_CATALOG) {
    const csvRow = csvInverters.get(inv.id);
    assert.ok(csvRow, `Missing inverter ${inv.id} in CSV catalog`);
    for (const [jsKey, csvKey] of invFields) {
      const jsVal = inv[jsKey] ?? null;
      assert.equal(
        jsVal,
        csvRow[csvKey],
        `Inverter ${inv.id} field ${jsKey} (${jsVal}) != CSV ${csvKey} (${csvRow[csvKey]})`
      );
    }
  }

  // Spot-check SG50CX-P2 and null preservation in enrichInverterSpec
  const sg50 = SAT_INVERTER_CATALOG.find((i) => i.id === 'sungrow-sg50cx-p2');
  assert.equal(sg50.mppt_count, 4);
  assert.equal(sg50.strings_per_mppt, 2);
  assert.equal(sg50.mppt_v_min, 160);
  assert.equal(sg50.mppt_v_max, 1000);
  assert.equal(sg50.mppt_full_load_v_min, 500);
  assert.equal(sg50.mppt_full_load_v_max, 800);
  assert.equal(sg50.max_mppt_current_a, 30);
  assert.equal(sg50.max_isc_per_mppt_a, 40);
  assert.equal(sg50.max_eff_pct, 98.5);
  assert.equal(sg50.euro_eff_pct, 98.3);

  const hw50Csv = csvInverters.get('huawei-sun2000-50ktl-m3');
  assert.ok(hw50Csv);
  assert.equal(hw50Csv.full_load_mppt_min_v, null);
  const enrichedNullEuro = enrichInverterSpec({
    ...sg50,
    id: 'test-null-euro',
    euro_eff_pct: null,
  });
  assert.equal(enrichedNullEuro.euro_eff_pct, null, 'Explicit null euro_eff_pct must not be overwritten with 98.5');

  const hw100 = SAT_INVERTER_CATALOG.find((i) => i.id === 'huawei-sun2000-100ktl-m2');
  assert.equal(hw100.mppt_full_load_v_min, null);
  assert.equal(hw100.mppt_full_load_v_max, null);
  const enrichedHw100 = enrichInverterSpec(hw100);
  assert.equal(enrichedHw100.mppt_full_load_v_min, null, 'Explicit null mppt_full_load_v_min must stay null');
  assert.equal(enrichedHw100.mppt_full_load_v_max, null, 'Explicit null mppt_full_load_v_max must stay null');

  const enrichedMod = enrichModuleSpec(trina605);
  const sizing = computeStringSizingAndCables({
    module: enrichedMod,
    inverter: enrichedHw100,
    extremeTempMinC: -10,
    cellTempMaxC: 65,
    modulesPerString: 18,
    totalModules: 180,
  });
  assert.equal(sizing.effFullLoadMinV, enrichedHw100.mppt_v_min);
  assert.equal(sizing.effFullLoadMaxV, enrichedHw100.mppt_v_max);
  assert.ok(sizing.vmpHotV >= enrichedHw100.mppt_v_min && sizing.vmpHotV <= enrichedHw100.mppt_v_max);
});

test('F13-01: SG50CX-P2 + 90x580W computeElectricalAllocation matches backend and saveToProject surfaces reconciliation diff', async () => {
  let capturedSavePayload = null;
  let mockMatched = true;
  const sv = new SatMapView(
    async (endpoint, payload) => {
      if (endpoint === 'satmap/save-project') {
        capturedSavePayload = payload;
        return {
          project_id: 'sg50-ui-test',
          version: 1,
          allocation_reconciliation: mockMatched
            ? { matched: true, diffs: [] }
            : {
                matched: false,
                submitted: { inverter_count: 1, ac_kw: 50 },
                analyzed_3d: { inverter_count: 2, ac_kw: 100 },
                diffs: ['inverter_count: submitted 1 != analyzed 2'],
              },
        };
      }
      throw new Error('offline test stub');
    },
    () => {}
  );

  await sv.runAiDetectRoof();
  sv.moduleModelId = 'jinko-jkm580n-72hl4-bdv';
  sv.inverterModelId = 'sungrow-sg50cx-p2';
  sv.layoutModules({ quiet: true });
  while (sv.modules.length < 90) {
    sv.modules.push({ ...sv.modules[0], id: `M_${sv.modules.length + 1}` });
  }
  sv.modules = sv.modules.slice(0, 90);
  sv.summary.moduleCount = 90;
  sv.summary.dcKw = 52.2;

  // Case 1: 9 x 10S -> 9 strings exceed 1 x SG50CX-P2 (4 MPPT x 2 = 8 max strings), so 2 inverters (100 kW AC, ratio 0.52)
  sv.modulesPerString = 10;
  sv.computeElectricalAllocation();
  assert.equal(sv.summary.stringCount, 9);
  assert.equal(sv.summary.inverterCount, 2);
  assert.equal(sv.summary.acKw, 100);
  assert.ok(Math.abs(sv.summary.dcAcRatio - 0.522) < 0.02);

  // Case 2: 18S -> 5 strings fit 1 x SG50CX-P2 (50 kW AC, ratio 1.044)
  sv.modulesPerString = 18;
  sv.computeElectricalAllocation();
  assert.equal(sv.summary.stringCount, 5);
  assert.equal(sv.summary.inverterCount, 1);
  assert.equal(sv.summary.acKw, 50);
  assert.ok(Math.abs(sv.summary.dcAcRatio - 1.044) < 0.02);

  // Save payload carries expected_* fields and mismatch sets reconciliation alert state
  mockMatched = false;
  await sv.saveToProject();
  assert.ok(capturedSavePayload, 'saveToProject must invoke satmap/save-project');
  assert.equal(capturedSavePayload.expected_module_count, 90);
  assert.equal(capturedSavePayload.expected_inverter_count, 1);
  assert.equal(capturedSavePayload.expected_ac_kw, 50);
  assert.ok(Math.abs(capturedSavePayload.expected_dc_kw - 52.2) < 0.05);
  assert.ok(
    sv.lastSaveReconciliation && sv.lastSaveReconciliation.matched === false,
    'Mismatch response must be recorded on sv.lastSaveReconciliation for UI alert display'
  );
});

test('Q01: buildPvsystV2RequestPayload preserves 0 and null/undefined without Math.max(1, ...) clamping', () => {
  const zeroSim = {
    summary: { dc_kw: 0, ac_kw: 0, e_grid_kwh: 0, pr_pct: 0 },
    monthly: [],
  };
  const payloadZero = buildPvsystV2RequestPayload(zeroSim, {
    projectId: 'zero-cap',
    projectName: '零容量项目',
    dcKw: 0,
    acKw: 0,
    moduleCount: 0,
  });
  assert.equal(payloadZero.system.dc_kw, 0);
  assert.equal(payloadZero.system.ac_kw, 0);
  assert.equal(payloadZero.system.module_count, 0);
  assert.equal(payloadZero.system.modules_per_string, 0);
  assert.equal(payloadZero.system.string_count, 0);

  const payloadNull = buildPvsystV2RequestPayload(
    {},
    {
      projectId: 'null-cap',
      projectName: '空值测试',
      dcKw: null,
      acKw: null,
      moduleCount: null,
    }
  );
  assert.equal(payloadNull.system.dc_kw, null);
  assert.equal(payloadNull.system.ac_kw, null);
  assert.equal(payloadNull.system.module_count, null);
});

test('Q02: buildPvsystProfessionalReportV2Html offline fallback shows OFFLINE UNVERIFIED PREVIEW without fake numbers or stamps', () => {
  const zeroSim = {
    summary: { dc_kw: 0, ac_kw: 0, e_grid_kwh: 0, pr_pct: 0 },
    monthly: [],
  };
  const html = buildPvsystProfessionalReportV2Html(zeroSim, {
    projectId: 'offline-zero',
    projectName: '离线未核验测试',
    dcKw: 0,
    acKw: 0,
    moduleCount: 0,
    financial: { self_consumption_ratio: 0, tariff_self_rmb: 0, tariff_feed_rmb: 0 },
    system: { walkway_width_m: 0.2 },
  });

  assert.match(html, /OFFLINE UNVERIFIED PREVIEW/);
  assert.match(html, /后端专业报告服务离线/);
  assert.match(html, /UNVERIFIED/);
  assert.match(html, /N\/A \(待后端核验\)|待后端配串核验/);
  assert.match(html, /FAIL/);

  // Forbidden fabricated figures, strings, stamps, and visible PVsyst brand text
  assert.doesNotMatch(html, /15\.8%/);
  assert.doesNotMatch(html, /5\.4\s*(?:年|yr|y)/i);
  assert.doesNotMatch(html, /undefined\s*[×x]\s*undefinedS/i);
  assert.doesNotMatch(html, /GUANGZHU VERIFIED/);
  assert.doesNotMatch(html, /光筑工程仿真核验章/);
  assert.doesNotMatch(stripHtmlTagsAndAttrs(html), /pvsyst/i);
});

test('Q03: Project B 100kW report request and fold markup never leak Project A 513-module gz.satmap.latestScheme cache', async () => {
  const prevStorage = globalThis.localStorage;
  const store = {};
  globalThis.localStorage = {
    getItem: (k) => store[k] ?? null,
    setItem: (k, v) => {
      store[k] = String(v);
    },
    removeItem: (k) => {
      delete store[k];
    },
  };

  try {
    const av = new SatMapView(async () => {
      throw new Error('offline');
    }, () => {});
    await av.runAiDetectRoof();
    av.projectName = '项目A卫星513块方案';
    av.moduleModelId = 'jinko-jkm580n-72hl4-bdv';
    av.layoutModules({ quiet: true });
    while (av.modules.length < 513) {
      av.modules.push({ ...av.modules[0], id: `MA_${av.modules.length + 1}` });
    }
    av.modules = av.modules.slice(0, 513);
    const snapA = persistLatestSatmapScheme(av);
    assert.equal(snapA.module_count, 513);

    const bSim = {
      summary: { dc_kw: 100, ac_kw: 100, e_grid_kwh: 118500, pr_pct: 82.4 },
      monthly: [],
    };
    const bResult = {
      project: {
        id: 'project-B-100kw',
        name: '项目B独立100kW工程',
        site: { lat: 32.4568, lon: 119.9182 },
        equipment: {
          module_id: 'trina-tsm-550de19',
          inverter_id: 'sungrow-sg110cx-p2',
        },
      },
      version: 2,
      summary: { dc_kw: 100, annual_kwh: 118500 },
      pvsyst: bSim,
    };

    const reqFromResult = buildPvsystV2RequestPayload(bSim, {
      result: bResult,
      preferAuthoritative: true,
    });
    assert.equal(reqFromResult.project_id, 'project-B-100kw');
    assert.equal(reqFromResult.project_name, '项目B独立100kW工程');
    assert.notEqual(reqFromResult.system.module_count, 513);
    assert.equal(reqFromResult.system.dc_kw, 100);

    store['gz.satmap.latestScheme'] = JSON.stringify({
      project_id: 'project-A-513',
      project_name: '项目A污染源',
      module_count: 513,
      dc_kw: 297.54,
      module: { id: 'a-custom-600', model: 'A_POLLUTED_600W', stc_w: 600 },
      financial: { capex_wan: 999, irr_pct: 48, payback_years: 1.9 },
      multifactor: { basic_snow_s0_kn_m2: 5.0 },
    });

    const reqFromOpts = buildPvsystV2RequestPayload(bSim, {
      projectId: 'project-B-100kw',
      projectName: '项目B独立100kW工程',
      dcKw: 100,
      acKw: 100,
      tiltDeg: 15,
      azimuthDeg: 180,
    });
    assert.equal(reqFromOpts.project_id, 'project-B-100kw');
    assert.equal(reqFromOpts.project_name, '项目B独立100kW工程');
    assert.equal(reqFromOpts.system.dc_kw, 100);
    assert.notEqual(reqFromOpts.system.module_count, 513);
    assert.notEqual(reqFromOpts.system.module?.model, 'A_POLLUTED_600W');
    assert.notEqual(reqFromOpts.financial?.capex_wan, 999);

    const foldHtml = pvsystProFoldMarkup(bResult);
    assert.doesNotMatch(stripHtmlTagsAndAttrs(foldHtml), /pvsyst/i);
    assert.match(foldHtml, /project-B-100kw/);
    assert.doesNotMatch(foldHtml, /project-A-513/);
  } finally {
    globalThis.localStorage = prevStorage;
  }
});
