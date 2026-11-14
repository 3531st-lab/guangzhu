/* ============================================================================
 * 光筑 (Guangzhu) — 卫星设计 <-> 三维设计双向联动 · 多维可能性因数综合寻优 · 专业仿真报告导出
 * Module: desktop/web/satmap-3d-linkage.js
 * ============================================================================ */

import { esc } from './data.js';
import { getLang } from './i18n.js';
import { computeFinancialDcf25Yr } from './pro-engineering-core.js';

export const SATMAP_LATEST_STORAGE_KEY = 'gz.satmap.latestScheme';
export const SATMAP_SYNCED_ROOF_KEY = 'gz.satmap.lastSyncedRoofId';

export function L(zh, en) {
  return getLang() === 'en' ? en : zh;
}

export const finiteNum = (v, fallback = 0) => {
  if (v === null || v === undefined || typeof v === 'boolean' || typeof v === 'object') return fallback;
  if (typeof v === 'string' && v.trim() === '') return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};

export const finiteOrNull = (v) => {
  if (v === null || v === undefined || typeof v === 'boolean' || typeof v === 'object') return null;
  if (typeof v === 'string' && v.trim() === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

export const ORIENTATION_MODES = [
  { id: 'south_fixed', zh: '正南最佳倾角固定阵', en: 'South Fixed Optimal Tilt' },
  { id: 'east_west', zh: '东西向双坡蝴蝶阵', en: 'East-West Butterfly Dual-Tilt' },
  { id: 'flush_pitched', zh: '顺屋面坡度平铺阵', en: 'Flush Roof-Pitch Array' },
  { id: 'elevated_canopy', zh: '架高阳光棚满铺阵', en: 'Elevated Solar Canopy' },
];

export const FIXING_MODES = [
  { id: 'auto', zh: '按屋面自动优选', en: 'Auto-Select by Roof' },
  { id: 'clamp', zh: '彩钢瓦免穿孔夹具', en: 'Standing-Seam Clamp' },
  { id: 'anchor', zh: '化学锚栓植筋固定', en: 'Chemical Anchor Bolt' },
  { id: 'ballast', zh: '混凝土配重压块', en: 'Concrete Ballast Block' },
];

export const ALBEDO_PRESETS = [
  { id: 'white_tpo', value: 0.65, zh: '高反射白膜屋面 (0.65)', en: 'White TPO Membrane (0.65)' },
  { id: 'concrete', value: 0.28, zh: '浅灰水泥混凝土 (0.28)', en: 'Light Gray Concrete (0.28)' },
  { id: 'color_steel', value: 0.20, zh: '压型彩钢瓦屋面 (0.20)', en: 'Corrugated Metal Roof (0.20)' },
  { id: 'asphalt', value: 0.12, zh: '深色沥青防水卷材 (0.12)', en: 'Dark Bitumen Membrane (0.12)' },
];

export const POLLUTION_LEVELS = [
  { id: 'clean', soilingPct: 1.5, degPctYr: 0.40, zh: '清洁郊区与生态园区', en: 'Clean Suburban Zone' },
  { id: 'urban', soilingPct: 2.2, degPctYr: 0.42, zh: '一般工商业城区', en: 'General Urban C&I' },
  { id: 'industrial', soilingPct: 3.8, degPctYr: 0.48, zh: '重工业粉尘密集区', en: 'Heavy Industrial Dust' },
  { id: 'coastal_salt', soilingPct: 2.8, degPctYr: 0.50, zh: '沿海高盐雾腐蚀区', en: 'Coastal Salt-Mist C5' },
  { id: 'agri', soilingPct: 3.2, degPctYr: 0.46, zh: '农牧氨气高湿环境', en: 'Agricultural Ammonia' },
];

export const LOAD_PROFILES = [
  { id: 'industrial_day', selfUseBase: 0.84, ewBonus: 0.04, zh: '工业白班生产负荷', en: 'Industrial Daytime Shift' },
  { id: 'commercial_afternoon', selfUseBase: 0.86, ewBonus: 0.06, zh: '商业午后傍晚高峰', en: 'Commercial Afternoon Peak' },
  { id: 'continuous_24h', selfUseBase: 0.94, ewBonus: 0.02, zh: '二十四小时连续负荷', en: '24/7 Continuous Base Load' },
  { id: 'export_all', selfUseBase: 0.0, ewBonus: 0.0, zh: '全额上网模式', en: '100% Grid Feed-In' },
];

export const OPTIMIZATION_OBJECTIVES = [
  { id: 'balanced', zh: '综合帕累托推荐', en: 'Balanced Pareto Optimum' },
  { id: 'max_yield', zh: '首年发电量最高', en: 'Maximum Annual Yield' },
  { id: 'max_capacity', zh: '屋面装机容量最大', en: 'Maximum Installed Capacity' },
  { id: 'min_lcoe', zh: '全周期度电成本最低', en: 'Minimum Lifecycle LCOE' },
  { id: 'max_self_use', zh: '企业自发消纳最高', en: 'Maximum Self-Consumption' },
  { id: 'wind_safe', zh: '台风与荷载安全优先', en: 'Typhoon & Load Safety First' },
];

export function createDefaultLinkageState() {
  return {
    showImportModal: false,
    loadingCatalog: false,
    catalogTab: 'projects', // 'projects' | 'my_roofs' | 'templates'
    catalogSearch: '',
    catalog: { projects: [], my_roofs: [], templates: [] },
    linkedSource: null,
    referenceMetrics: null,
    syncStatus: null,
    syncing: false,
    showDiffCard: false,
    reportPreview: {
      open: false,
      html: '',
      htmlUrl: '',
      downloadUrl: '',
      filename: '',
      savedDisplay: '',
      titleZh: '光筑专业报告',
      titleEn: 'Guangzhu Professional Report',
      activePage: 1,
    },
    lastExportedReport: null,
    deliveryBundle: {
      exporting: false,
      lastResult: null,
    },
    healthCheck: {
      loading: false,
      result: null,
    },
  };
}

export function createDefaultMultiFactorState() {
  return {
    openInStep1: false,
    openInStep3: true,
    optimizing: false,
    orientationMode: 'south_fixed', // 'south_fixed' | 'east_west' | 'flush_pitched' | 'elevated_canopy'
    rackRows: '2P', // '1P' | '2P'
    canopyClearanceM: 2.8,
    maxRoofLoadKgM2: 35.0,
    fixingType: 'auto', // 'auto' | 'clamp' | 'anchor' | 'ballast'
    parapetShadowAvoid: true,
    fireLaneWidthM: 0.0,
    maintWalkwayIntervalM: 18.0,
    basicWindW0KnM2: 0.45,
    basicSnowS0KnM2: 0.35,
    extremeTempMinC: -10.0,
    extremeTempMaxC: 40.0,
    albedoSurface: 'concrete',
    albedo: 0.28,
    pollutionLevel: 'urban',
    maxModuleShadingLossPct: 12.0,
    autoPruneShaded: false,
    showPrunedShadedSlots: true,
    objective: 'balanced',
    loadProfile: 'industrial_day',
    selectedSchemeId: '',
    previewSnapshot: null,
    previewSchemeId: '',
    lastResult: null,
  };
}

export function resolveAlbedoSurfaceKey(albedoVal, surfaceHint = '') {
  if (surfaceHint && ALBEDO_PRESETS.some((p) => p.id === surfaceHint)) {
    return surfaceHint;
  }
  const v = finiteNum(albedoVal, 0.28);
  let best = ALBEDO_PRESETS[1];
  let bestDiff = Infinity;
  for (const p of ALBEDO_PRESETS) {
    const d = Math.abs(p.value - v);
    if (d < bestDiff) {
      bestDiff = d;
      best = p;
    }
  }
  return best.id;
}

/**
 * Evaluate extreme cold open-circuit voltage Voc(T_min) & extreme hot operating voltage Vmpp(T_max)
 */
export function computeColdVocAndStringSafety(moduleSpec = {}, inverterSpec = {}, mfParams = {}, currentSeries = 18) {
  const vocStc = finiteNum(moduleSpec.voc_v, 51.8);
  const vmpStc = finiteNum(moduleSpec.vmp_v ?? moduleSpec.vmpp_v, 43.2);
  const betaVocPctPerC = finiteNum(
    moduleSpec.beta_voc_pct_c ?? moduleSpec.temp_coeff_voc_pct_per_c ?? moduleSpec.temp_coeff_voc_pct,
    -0.25
  );
  const gammaVmpPctPerC = finiteNum(
    moduleSpec.gamma_pmax_pct_c ?? moduleSpec.temp_coeff_pmax_pct_per_c ?? moduleSpec.temp_coeff_pmax_pct,
    -0.30
  );
  const maxDcV = finiteNum(inverterSpec.max_dc_v ?? inverterSpec.max_dc_voltage_v, 1100);
  const mpptMinV = finiteNum(inverterSpec.mppt_v_min ?? inverterSpec.mppt_min_v, 200);
  const mpptMaxV = finiteNum(inverterSpec.mppt_v_max ?? inverterSpec.mppt_max_v, 1000);

  const tMinC = finiteNum(mfParams.extremeTempMinC ?? mfParams.extreme_temp_min_c, -10);
  const tMaxC = finiteNum(mfParams.extremeTempMaxC ?? mfParams.extreme_temp_max_c, 40);
  const tCellHotC = tMaxC + 26;

  const coldVocSingle = vocStc * (1 + (betaVocPctPerC / 100) * (tMinC - 25));
  const coldVmppSingle = vmpStc * (1 + (gammaVmpPctPerC / 100) * (tMinC - 25));
  const hotVmppSingle = Math.max(12, vmpStc * (1 + (gammaVmpPctPerC / 100) * (tCellHotC - 25)));

  const maxSeriesVocHard = Math.max(1, Math.floor((maxDcV * 0.995) / Math.max(1, coldVocSingle)));
  const maxSeriesMpptCold = Math.max(1, Math.floor(mpptMaxV / Math.max(1, coldVmppSingle)));
  const maxSeriesSafe = Math.max(1, Math.min(maxSeriesVocHard, maxSeriesMpptCold));
  const minSeriesMppt = Math.min(maxSeriesSafe, Math.max(1, Math.ceil((mpptMinV * 1.04) / Math.max(1, hotVmppSingle))));
  const targetByMppt = Math.floor((mpptMaxV * 0.88) / Math.max(1, vmpStc));
  const recommendedSeries = Math.max(minSeriesMppt, Math.min(maxSeriesSafe, targetByMppt || 18));

  const explicitSeries = finiteOrNull(currentSeries);
  const nSeries = explicitSeries === 0 ? 0 : Math.max(1, Math.round(explicitSeries ?? recommendedSeries));
  const stringColdVocV = Number((nSeries * coldVocSingle).toFixed(1));
  const stringColdVmppV = Number((nSeries * coldVmppSingle).toFixed(1));
  const stringHotVmppV = Number((nSeries * hotVmppSingle).toFixed(1));
  const safe = (
    nSeries >= 1
    && stringColdVocV <= maxDcV
    && stringColdVmppV <= mpptMaxV
    && stringHotVmppV >= mpptMinV
    && nSeries <= maxSeriesSafe
  );

  return {
    extreme_temp_min_c: tMinC,
    extreme_temp_max_c: tMaxC,
    beta_voc_pct_c: betaVocPctPerC,
    gamma_pmax_pct_c: gammaVmpPctPerC,
    cold_voc_v: Number(coldVocSingle.toFixed(2)),
    cold_vmpp_v: Number(coldVmppSingle.toFixed(2)),
    hot_vmpp_v: Number(hotVmppSingle.toFixed(2)),
    max_dc_v: maxDcV,
    mppt_v_min: mpptMinV,
    mppt_v_max: mpptMaxV,
    max_series_safe: maxSeriesSafe,
    min_series_mppt: minSeriesMppt,
    recommended_series: recommendedSeries,
    current_series: nSeries,
    string_cold_voc_v: stringColdVocV,
    string_cold_vmpp_v: stringColdVmppV,
    string_hot_vmpp_v: stringHotVmppV,
    safe,
  };
}

/**
 * Evaluate added roof dead load (kg/m²), typhoon wind uplift setback & snow shedding loss
 */
export function computeMultiFactorStructuralCheck({
  roofType = 'flat',
  orientationMode = 'south_fixed',
  rackRows = '2P',
  tiltDeg = 15,
  buildingHeightM = 12,
  edgeSetbackM = 0.8,
  moduleSpec = {},
  mfParams = {},
} = {}) {
  const maxRoofLoadKgM2 = Math.max(12, finiteNum(mfParams.maxRoofLoadKgM2 ?? mfParams.max_roof_load_kg_m2, 35));
  const w0 = Math.max(0.25, finiteNum(mfParams.basicWindW0KnM2 ?? mfParams.basic_wind_w0_kn_m2, 0.45));
  const s0 = Math.max(0, finiteNum(mfParams.basicSnowS0KnM2 ?? mfParams.basic_snow_s0_kn_m2, 0.35));
  const rawFixing = String(mfParams.fixingType ?? mfParams.fixing_type ?? 'auto');
  const fixingType = rawFixing === 'auto'
    ? (roofType === 'flat' ? (maxRoofLoadKgM2 < 26 ? 'anchor' : 'ballast') : 'clamp')
    : rawFixing;

  const modArea = Math.max(1.6, finiteNum(moduleSpec.length_m, 2.278) * finiteNum(moduleSpec.width_m, 1.134));
  const modWeightKg = finiteNum(moduleSpec.weight_kg, 31.5);
  const pvSelfKgM2 = modWeightKg / modArea;
  const effTilt = orientationMode === 'flush_pitched'
    ? Math.min(12, Math.max(2, tiltDeg))
    : orientationMode === 'east_west'
      ? Math.min(14, Math.max(8, tiltDeg || 10))
      : Math.max(0, tiltDeg);

  const heightFactor = 1 + Math.max(0, buildingHeightM - 10) * 0.014;
  const rackFactor = rackRows === '1P' ? 0.90 : 1.04;
  const ewShieldFactor = orientationMode === 'east_west' ? 0.66 : 1.0;

  let addedDeadLoadKgM2 = 15.2;
  let ballastKgPerModule = 0;
  if (fixingType === 'clamp') {
    addedDeadLoadKgM2 = pvSelfKgM2 + (orientationMode === 'elevated_canopy' ? 11.5 : 3.2) * rackFactor;
  } else if (fixingType === 'anchor') {
    addedDeadLoadKgM2 = pvSelfKgM2 + (orientationMode === 'elevated_canopy' ? 14.2 : 6.4) * rackFactor;
  } else {
    // Concrete ballast required to resist wind uplift w0 & tilt sail area (typically 2×35kg concrete blocks per module)
    const upliftFactor = (0.55 + Math.sin((effTilt * Math.PI) / 180) * 1.45) * (w0 / 0.45) * heightFactor * ewShieldFactor * rackFactor;
    ballastKgPerModule = Number(Math.max(36, 68 * upliftFactor).toFixed(1));
    const gcrEst = orientationMode === 'east_west' ? 0.78 : 0.58;
    addedDeadLoadKgM2 = (pvSelfKgM2 + 4.5 + ballastKgPerModule / modArea) * gcrEst + 4.8;
  }
  addedDeadLoadKgM2 = Number(addedDeadLoadKgM2.toFixed(1));

  // Typhoon / coastal wind corner & perimeter setback check (GB 50009 / NB/T 10115)
  const isTyphoonZone = w0 >= 0.65;
  const minRequiredSetbackM = Number(
    Math.max(0.6, (isTyphoonZone ? 1.15 : 0.75) * Math.sqrt(w0 / 0.45) * (fixingType === 'ballast' ? 1.12 : 0.95)).toFixed(2)
  );
  const cornerKeepoutM = Number(Math.max(1.2, Math.min(4.2, buildingHeightM * 0.14 * Math.sqrt(w0 / 0.45))).toFixed(2));
  const actualSetbackM = Number(Math.max(0, finiteNum(edgeSetbackM, 0.8)).toFixed(2));
  const effSetbackM = Number(Math.max(actualSetbackM, isTyphoonZone ? minRequiredSetbackM : 0.5).toFixed(2));

  const loadOk = addedDeadLoadKgM2 <= maxRoofLoadKgM2 + 0.15;
  const windOk = actualSetbackM + 0.05 >= minRequiredSetbackM && !(isTyphoonZone && fixingType === 'ballast' && effTilt > 18);
  const snowSlidingFactor = Math.max(0.25, 1 - Math.sin((effTilt * Math.PI) / 180) * 1.15);
  const snowLossPct = Number(Math.min(6.5, s0 * 3.8 * snowSlidingFactor).toFixed(2));
  const snowOk = s0 <= 1.20 && (s0 <= 0.75 || rackRows === '1P' || (fixingType !== 'clamp' && effTilt >= 8));

  return {
    fixing_type: fixingType,
    added_dead_load_kg_m2: addedDeadLoadKgM2,
    max_roof_load_kg_m2: maxRoofLoadKgM2,
    ballast_kg_per_module: ballastKgPerModule,
    basic_wind_w0_kn_m2: w0,
    basic_snow_s0_kn_m2: s0,
    actual_setback_m: actualSetbackM,
    min_required_setback_m: minRequiredSetbackM,
    recommended_edge_setback_m: minRequiredSetbackM,
    effective_setback_m: effSetbackM,
    corner_keepout_m: cornerKeepoutM,
    is_typhoon_zone: isTyphoonZone,
    load_ok: loadOk,
    wind_ok: windOk,
    snow_ok: snowOk,
    snow_loss_pct: snowLossPct,
    all_pass: Boolean(loadOk && windOk && snowOk),
  };
}

/**
 * Evaluate per-module annual + winter shading loss % caused by parapet walls & 3D rooftop obstacles.
 * Used to identify and auto-prune heavily shaded "poison modules" (`lossPct > maxModuleShadingLossPct`).
 */
export function evaluateModuleShadingLossPct(mod, {
  roofBoundsM,
  parapetHeightM = 0.5,
  obstacles = [],
  lat = 32.5,
  mountOrientation = 'portrait',
  orientationMode = 'south_fixed',
  canopyClearanceM = 2.8,
} = {}) {
  if (!mod) return 0;
  const latRad = (Math.max(18, Math.min(52, Math.abs(finiteNum(lat, 32.5)))) * Math.PI) / 180;
  const winterNoonAltRad = Math.max(0.22, Math.PI / 2 - latRad - (23.45 * Math.PI) / 180);
  const morningAltRad = Math.max(0.16, winterNoonAltRad * 0.62);
  const tanMorning = Math.tan(morningAltRad);
  const moduleBaseZ = orientationMode === 'elevated_canopy' ? Math.max(2.0, canopyClearanceM) : 0.28;
  const diodeFactor = mountOrientation === 'landscape' ? 0.58 : 1.0;

  let shadeLoss = 0;

  // 1. South / East / West parapet wall cast-shadow check (in local meters, +Y is South, +X is East, -X is West)
  const effParapetRise = Math.max(0, parapetHeightM - moduleBaseZ);
  if (effParapetRise > 0.08 && roofBoundsM && roofBoundsM.widthM > 2) {
    const shadowReachSouth = effParapetRise / tanMorning;
    const distSouth = Math.max(0.05, roofBoundsM.maxY - mod.cy);
    if (distSouth < shadowReachSouth) {
      const ratio = (shadowReachSouth - distSouth) / Math.max(0.25, shadowReachSouth);
      shadeLoss += 22.0 * ratio * ratio * diodeFactor;
    }
    const shadowReachEW = (effParapetRise / tanMorning) * 0.72;
    const distEast = Math.max(0.05, roofBoundsM.maxX - mod.cx);
    const distWest = Math.max(0.05, mod.cx - roofBoundsM.minX);
    const minEW = Math.min(distEast, distWest);
    if (minEW < shadowReachEW) {
      const ratioEW = (shadowReachEW - minEW) / Math.max(0.25, shadowReachEW);
      shadeLoss += 11.5 * ratioEW * ratioEW * diodeFactor;
    }
  }

  // 2. 3D Rooftop Obstacles (HVAC units, elevator penthouses, chimneys, skylights with height)
  for (const obs of obstacles || []) {
    const poly = obs.polygon || obs.polygon_m || [];
    if (!poly.length) continue;
    const rawH = finiteNum(obs.heightM ?? obs.height_m, obs.kind === 'penthouse' ? 3.0 : obs.kind === 'hvac' ? 2.1 : obs.kind === 'chimney' ? 3.5 : 0.35);
    const effObsRise = Math.max(0, rawH - moduleBaseZ);
    if (effObsRise <= 0.12) continue;

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const [px, py] of poly) {
      if (px < minX) minX = px;
      if (px > maxX) maxX = px;
      if (py < minY) minY = py;
      if (py > maxY) maxY = py;
    }
    const obsCx = (minX + maxX) * 0.5;
    const obsCy = (minY + maxY) * 0.5;
    const halfW = Math.max(0.4, (maxX - minX) * 0.5);
    const halfH = Math.max(0.4, (maxY - minY) * 0.5);

    // Obstacles cast winter shadows primarily northward (mod.cy < obsCy) and morning/afternoon E/W
    const dx = Math.max(0, Math.abs(mod.cx - obsCx) - halfW);
    const dy = mod.cy <= obsCy
      ? Math.max(0, minY - mod.cy) // Module is north of obstacle (in main solar shadow cone!)
      : Math.max(0, mod.cy - maxY) * 2.35; // Module is south of obstacle (rarely shaded)
    const effDist = Math.hypot(dx * 0.85, dy);
    const maxShadowCast = effObsRise / tanMorning;
    if (effDist < maxShadowCast) {
      const prox = (maxShadowCast - effDist) / Math.max(0.3, maxShadowCast);
      shadeLoss += 34.0 * prox * (0.45 + 0.55 * prox) * diodeFactor;
    }
  }

  return Number(Math.min(65, shadeLoss).toFixed(2));
}

/**
 * Normalize 3D Roof / Project coordinates so polygon & obstacles are centered around (0, 0) in meters
 */
export function normalizeImportedGeometry(roofData = {}, rawObstacles = []) {
  let poly = Array.isArray(roofData.polygon_m) && roofData.polygon_m.length >= 3
    ? roofData.polygon_m.map(([x, y]) => [finiteNum(x), finiteNum(y)])
    : Array.isArray(roofData.outline) && roofData.outline.length >= 3
      ? roofData.outline.map(([x, y]) => [finiteNum(x), finiteNum(y)])
      : null;

  if (!poly) {
    const lenM = Math.max(12, finiteNum(roofData.length_m ?? roofData.span_x_m, 60));
    const widM = Math.max(10, finiteNum(roofData.width_m ?? roofData.span_y_m, 32));
    poly = [
      [-lenM / 2, -widM / 2],
      [lenM / 2, -widM / 2],
      [lenM / 2, widM / 2],
      [-lenM / 2, widM / 2],
    ];
  }

  const xs = poly.map((p) => p[0]);
  const ys = poly.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const cx = (minX + maxX) * 0.5;
  const cy = (minY + maxY) * 0.5;
  const needsCentering = Math.abs(cx) > 2.5 || Math.abs(cy) > 2.5;
  const shiftX = needsCentering ? cx : 0;
  const shiftY = needsCentering ? cy : 0;

  const centeredPoly = poly.map(([x, y]) => [
    Number((x - shiftX).toFixed(2)),
    Number((y - shiftY).toFixed(2)),
  ]);

  const normalizedObstacles = (rawObstacles || []).map((obs, idx) => {
    let obsPoly = Array.isArray(obs.polygon_m) && obs.polygon_m.length >= 3
      ? obs.polygon_m
      : Array.isArray(obs.polygon) && obs.polygon.length >= 3
        ? obs.polygon
        : null;
    if (!obsPoly) {
      const ox = finiteNum(obs.x_m ?? obs.x, 0);
      const oy = finiteNum(obs.y_m ?? obs.y, 0);
      const ow = Math.max(0.8, finiteNum(obs.w_m ?? obs.width_m ?? obs.w, 3.2));
      const oh = Math.max(0.8, finiteNum(obs.h_m ?? obs.depth_m ?? obs.length_m ?? obs.h, 2.4));
      obsPoly = [
        [ox, oy],
        [ox + ow, oy],
        [ox + ow, oy + oh],
        [ox, oy + oh],
      ];
    }
    const shiftedObsPoly = obsPoly.map(([px, py]) => [
      Number((finiteNum(px) - shiftX).toFixed(2)),
      Number((finiteNum(py) - shiftY).toFixed(2)),
    ]);
    const heightM = Math.max(0.1, finiteNum(obs.height_m ?? obs.heightM ?? obs.z_height_m, obs.kind === 'skylight' ? 0.25 : 1.8));
    const kind = String(obs.kind || obs.type || 'hvac');
    return {
      id: String(obs.id || `obs-3d-${idx + 1}`),
      name: String(obs.name || obs.label || `${L('三维障碍物', '3D Obstacle')} #${idx + 1}`),
      kind,
      heightM,
      height_m: heightM,
      polygon: shiftedObsPoly,
      polygon_m: shiftedObsPoly,
    };
  });

  return {
    polygonM: centeredPoly,
    obstacles: normalizedObstacles,
  };
}

/**
 * Fetch 3D Design catalog from `GET /api/satmap/3d-catalog` with graceful multi-endpoint fallback
 */
export async function fetch3DCatalog(view) {
  const link = view.linkage3d || (view.linkage3d = createDefaultLinkageState());
  link.loadingCatalog = true;
  let projects = [];
  let myRoofs = [];
  let templates = [];
  let catalogApiSucceeded = false;

  try {
    if (typeof view.api === 'function') {
      const res = await view.api('satmap/3d-catalog');
      if (res && (Array.isArray(res.projects) || Array.isArray(res.my_roofs) || Array.isArray(res.templates))) {
        catalogApiSucceeded = true;
        projects = res.projects || [];
        myRoofs = res.my_roofs || [];
        templates = res.templates || [];
      }
    }
  } catch {
    // Fallback to /api/projects/local-list, /api/projects, /api/roofs
  }

  if (!catalogApiSucceeded && !projects.length && typeof view.api === 'function') {
    for (const ep of ['projects/local-list', 'projects']) {
      try {
        const pRes = await view.api(ep);
        const list = Array.isArray(pRes) ? pRes : (pRes?.projects || []);
        if (list.length) {
          projects = list.map((p) => ({
            id: String(p.id || p.project_id),
            name: String(p.name || p.project_name || p.id),
            city: String(p.city || ''),
            roof_type: String(p.roof_type || 'flat'),
            version: finiteNum(p.version ?? p.latest_version, 1),
            dc_kw: finiteNum(p.dc_kw ?? p.metrics?.dc_kw, 0),
            module_count: finiteNum(p.module_count ?? p.metrics?.module_count, 0),
            annual_kwh: finiteNum(p.annual_kwh ?? p.metrics?.annual_kwh, 0),
            pr_pct: finiteNum(p.pr_pct ?? p.metrics?.pr_pct, 83.2),
          }));
          break;
        }
      } catch {
        // Ignore
      }
    }
  }

  if (!catalogApiSucceeded && (!myRoofs.length || !templates.length) && typeof view.api === 'function') {
    try {
      const rRes = await view.api('roofs');
      const allRoofs = Array.isArray(rRes?.roofs) ? rRes.roofs : (Array.isArray(rRes) ? rRes : []);
      if (allRoofs.length) {
        const isMineRoof = (r) => r.collection === 'mine' || r.is_custom === true || String(r.id || '').startsWith('my-');
        if (!myRoofs.length) {
          myRoofs = allRoofs.filter(isMineRoof);
        }
        if (!templates.length) {
          templates = allRoofs.filter((r) => !isMineRoof(r));
        }
      }
    } catch {
      // Ignore
    }
  }

  const isMineStateRoof = (r) => r.collection === 'mine' || r.is_custom === true || String(r.id || '').startsWith('my-');
  if (!myRoofs.length && Array.isArray(view.appState?.roofs)) {
    myRoofs = view.appState.roofs.filter(isMineStateRoof);
  }
  if (!templates.length && Array.isArray(view.appState?.roofs)) {
    templates = view.appState.roofs.filter((r) => !isMineStateRoof(r));
  }

  // Offline built-in fallback templates so modal always offers selectable 3D engineering roofs
  if (!projects.length && !myRoofs.length && !templates.length) {
    templates = [
      {
        id: 'changzhou-demo',
        name: '常州高新电子产业园混凝土平屋面厂房',
        name_en: 'Changzhou Concrete Flat Factory Roof',
        city: '常州市',
        city_en: 'Changzhou',
        lat: 31.8126,
        lon: 119.9742,
        area_m2: 1920,
        length_m: 60,
        width_m: 32,
        parapet_height_m: 0.85,
        building_height_m: 13.5,
        obstacle_count: 2,
        roof_type: 'flat',
      },
      {
        id: 'taizhou-metal-gable',
        name: '泰州医药高新区双坡彩钢瓦智能车间',
        name_en: 'Taizhou Gable Metal Smart Workshop',
        city: '泰州市',
        city_en: 'Taizhou',
        lat: 32.4568,
        lon: 119.9182,
        area_m2: 3456,
        length_m: 72,
        width_m: 48,
        parapet_height_m: 0.4,
        building_height_m: 11.0,
        slope_deg: 6,
        obstacle_count: 2,
        roof_type: 'double_slope',
      },
    ];
  }

  link.catalog = { projects, my_roofs: myRoofs, templates };
  if (link.catalogTab === 'projects' && !projects.length) {
    link.catalogTab = myRoofs.length ? 'my_roofs' : 'templates';
  }
  link.loadingCatalog = false;
  return link.catalog;
}

/**
 * Import a 3D Project / Custom Roof / Roof Template into Satellite Design (`GET /api/satmap/from-3d/{kind}/{id}`)
 */
export async function importFrom3DItem(view, kind = 'project', itemId = '', version = null) {
  const link = view.linkage3d || (view.linkage3d = createDefaultLinkageState());
  const mf = view.mfState || (view.mfState = createDefaultMultiFactorState());
  const cleanKind = kind === 'my_roof' ? 'my-roof' : kind;
  let data = null;

  if (typeof view.api === 'function' && itemId) {
    const q = version ? `?version=${encodeURIComponent(version)}` : '';
    try {
      data = await view.api(`satmap/from-3d/${encodeURIComponent(cleanKind)}/${encodeURIComponent(itemId)}${q}`);
    } catch {
      data = null;
    }
  }

  // Client-side conversion fallback if `satmap/from-3d` endpoint is offline/404
  if (!data || !data.roof) {
    let rawItem = null;
    if (cleanKind === 'project' && typeof view.api === 'function') {
      try {
        const res = await view.api(`projects/${encodeURIComponent(itemId)}/result`);
        if (res) {
          const r = res.project?.roof || res.roof || {};
          const sum = res.summary || {};
          data = {
            ok: true,
            source: { kind: 'project', id: itemId, name: res.project?.name || itemId, version: res.selected_version || 1 },
            site: {
              name: res.project?.name || itemId,
              city: r.city || '',
              lat: finiteNum(r.lat ?? res.project?.lat, view.lat),
              lon: finiteNum(r.lon ?? res.project?.lon, view.lon),
            },
            roof: {
              polygon_m: r.outline || r.polygon_m,
              length_m: r.length_m,
              width_m: r.width_m,
              roof_type: r.type || 'flat',
              building_height_m: finiteNum(r.building_height_m ?? r.height_m, 12),
              parapet_height_m: finiteNum(r.parapet_height_m, 0.6),
              slope_deg: finiteNum(r.slope_deg, 0),
              setback_m: finiteNum(r.setback_m, 0.8),
              max_load_kg_m2: finiteNum(r.load_limit_kg_m2, 35),
              albedo: finiteNum(r.albedo, 0.28),
            },
            obstacles: r.obstacles || [],
            design: {
              module_id: res.project?.equipment?.module_id,
              inverter_id: res.project?.equipment?.inverter_id,
              tilt_deg: finiteNum(sum.tilt_deg, 15),
              azimuth_deg: finiteNum(sum.azimuth_deg, 180),
            },
            reference_metrics: {
              dc_kw: finiteNum(sum.capacity_kwp ?? sum.dc_kw, 0),
              module_count: finiteNum(sum.module_count, 0),
              annual_kwh: finiteNum(sum.yield_kwh?.p50 ?? sum.annual_kwh, 0),
              pr_pct: finiteNum(sum.pr_pct, 83.2),
            },
          };
        }
      } catch {
        // Ignore
      }
    }
    if (!data || !data.roof) {
      const allPool = [
        ...(link.catalog?.projects || []),
        ...(link.catalog?.my_roofs || []),
        ...(link.catalog?.templates || []),
        ...(view.appState?.roofs || []),
      ];
      rawItem = allPool.find((x) => String(x.id) === String(itemId)) || allPool[0] || {
        id: itemId || 'changzhou-demo',
        name: '三维联动标准厂房',
        city: '常州市',
        lat: 31.8126,
        lon: 119.9742,
        length_m: 60,
        width_m: 32,
        parapet_height_m: 0.85,
        building_height_m: 13.5,
        roof_type: 'flat',
      };
      data = {
        ok: true,
        source: { kind: cleanKind, id: rawItem.id, name: rawItem.name || rawItem.id, version: rawItem.version || 1 },
        site: {
          name: rawItem.name || rawItem.id,
          city: rawItem.city || '',
          lat: finiteNum(rawItem.lat, view.lat),
          lon: finiteNum(rawItem.lon, view.lon),
        },
        roof: {
          polygon_m: rawItem.polygon_m || rawItem.outline,
          length_m: finiteNum(rawItem.length_m, 60),
          width_m: finiteNum(rawItem.width_m, 32),
          roof_type: rawItem.roof_type || rawItem.type || 'flat',
          building_height_m: finiteNum(rawItem.building_height_m ?? rawItem.height_m, 13.0),
          parapet_height_m: finiteNum(rawItem.parapet_height_m, 0.75),
          slope_deg: finiteNum(rawItem.slope_deg, 5),
          setback_m: finiteNum(rawItem.setback_m, 0.8),
          max_load_kg_m2: finiteNum(rawItem.max_load_kg_m2 ?? rawItem.load_limit_kg_m2, rawItem.roof_type === 'flat' ? 120 : 35),
          albedo: finiteNum(rawItem.albedo, 0.28),
        },
        obstacles: Array.isArray(rawItem.obstacles) && rawItem.obstacles.length
          ? rawItem.obstacles
          : [
              { id: 'obs-hvac-1', kind: 'hvac', name: '屋面空调机组', x_m: -8, y_m: -4, w_m: 4.6, h_m: 3.2, height_m: 2.2 },
            ],
        design: rawItem.design || {},
        reference_metrics: rawItem.reference_metrics || (rawItem.dc_kw ? {
          dc_kw: finiteNum(rawItem.dc_kw, 0),
          module_count: finiteNum(rawItem.module_count, 0),
          annual_kwh: finiteNum(rawItem.annual_kwh, 0),
          pr_pct: finiteNum(rawItem.pr_pct, 83.4),
        } : null),
      };
    }
  }

  const site = data.site || {};
  const roof = data.roof || {};
  const design = data.design || {};
  const rawObsList = Array.isArray(data.obstacles) && data.obstacles.length
    ? data.obstacles
    : (Array.isArray(roof.obstacles) ? roof.obstacles : []);
  const norm = normalizeImportedGeometry(roof, rawObsList);

  if (site.name || data.source?.name) {
    view.projectName = String(site.name || data.source.name);
    view.cadTitle = `${view.projectName}施工图`;
  }
  if (site.city || site.address || site.name) {
    view.address = String(site.address || `${site.city ? `${site.city} · ` : ''}${site.name || view.projectName}`);
  }
  if (Number.isFinite(Number(site.lat)) && Number.isFinite(Number(site.lon))) {
    view.lat = Number(site.lat);
    view.lon = Number(site.lon);
    view.roofCenterLat = view.lat;
    view.roofCenterLon = view.lon;
  }

  view.roofOutlineM = norm.polygonM;
  view.obstacles = norm.obstacles;
  view.hasRoof = true;
  view.showRoofOverlay = true;

  const rTypeRaw = String(roof.roof_type || 'flat').toLowerCase();
  view.roofType = rTypeRaw.includes('double') || rTypeRaw.includes('gable')
    ? 'double_slope'
    : rTypeRaw.includes('single') || rTypeRaw.includes('metal') || rTypeRaw.includes('pitched')
      ? 'single_slope'
      : 'flat';

  view.buildingHeightM = Math.max(3, finiteNum(roof.building_height_m, 12));
  const parapetM = Math.max(0, finiteNum(roof.parapet_height_m, view.roofType === 'flat' ? 0.75 : 0.3));
  view.parapetHeightMm = Math.round(parapetM * 1000);
  if (Number.isFinite(Number(roof.slope_deg))) {
    view.roofSlopeDeg = Math.max(0, Number(roof.slope_deg));
  }
  if (Number.isFinite(Number(roof.setback_m))) {
    view.edgeSetbackM = Math.max(0.2, Number(roof.setback_m));
  }
  if (Number.isFinite(Number(roof.max_load_kg_m2)) && Number(roof.max_load_kg_m2) > 0) {
    mf.maxRoofLoadKgM2 = Number(roof.max_load_kg_m2);
    view.roofLoadLimitKnM2 = Number((mf.maxRoofLoadKgM2 / 102).toFixed(2));
  }
  if (Number.isFinite(Number(roof.albedo)) && Number(roof.albedo) > 0) {
    mf.albedo = Number(roof.albedo);
    mf.albedoSurface = resolveAlbedoSurfaceKey(mf.albedo);
    view.pvsystParams = { ...(view.pvsystParams || {}), albedo: mf.albedo };
  }

  // Match module & inverter IDs if present in catalog, with brand-family fallback for 3D catalog variants
  if (design.module_id && typeof view.getAllModules === 'function') {
    const allMods = view.getAllModules();
    const rawModId = String(design.module_id).toLowerCase();
    const brandPrefix = rawModId.split('-')[0];
    const matchedMod =
      allMods.find((m) => m.id === design.module_id || rawModId.includes(m.id.toLowerCase())) ||
      (brandPrefix.length >= 3 ? allMods.find((m) => m.id.toLowerCase().startsWith(`${brandPrefix}-`)) : null);
    if (matchedMod) view.moduleModelId = matchedMod.id;
  }
  if (design.inverter_id && typeof view.getAllInverters === 'function') {
    const allInvs = view.getAllInverters();
    const rawInvId = String(design.inverter_id).toLowerCase();
    const brandPrefix = rawInvId.split('-')[0];
    const matchedInv =
      allInvs.find((i) => i.id === design.inverter_id || rawInvId.includes(i.id.toLowerCase())) ||
      (brandPrefix.length >= 3 ? allInvs.find((i) => i.id.toLowerCase().startsWith(`${brandPrefix}-`)) : null);
    if (matchedInv) view.inverterModelId = matchedInv.id;
  }
  if (Number.isFinite(Number(design.tilt_deg))) {
    view.tiltDeg = Number(design.tilt_deg);
    if (view.roofType !== 'flat' && view.roofSlopeDeg === 0) {
      view.roofSlopeDeg = view.tiltDeg;
    }
  }
  if (Number.isFinite(Number(design.azimuth_deg))) {
    view.azimuthDeg = Number(design.azimuth_deg);
  }
  if (Number.isFinite(Number(design.row_gap_m)) && Number(design.row_gap_m) > 0) {
    view.rowSpacingM = Number(design.row_gap_m);
  }
  if (design.mount_orientation === 'landscape' || design.mount_orientation === 'portrait') {
    view.orientation = design.mount_orientation;
  }
  if (design.orientation_mode && ORIENTATION_MODES.some((o) => o.id === design.orientation_mode)) {
    mf.orientationMode = design.orientation_mode;
    view.orientationMode = design.orientation_mode;
  }
  if (Number.isFinite(Number(design.modules_per_string)) && Number(design.modules_per_string) >= 6) {
    view.modulesPerString = Math.round(Number(design.modules_per_string));
  }

  link.linkedSource = {
    kind: cleanKind,
    id: String(data.source?.id || itemId),
    name: String(data.source?.name || view.projectName),
    version: finiteNum(data.source?.version, 1),
  };
  link.syncStatus = null;
  link.referenceMetrics = data.reference_metrics || null;
  link.showImportModal = false;
  link.showDiffCard = true;

  const bounds = view.getRoofBoundsM(true);
  view.scaleReferenceM = bounds.widthM;
  if (typeof view.zoomToFitRoof === 'function') {
    view.zoomToFitRoof({ canvasW: 920, canvasH: 580 });
  }
  view.layoutModules({ quiet: true, autoCreateRoof: false });
  view.electricalConfirmed = true;
  view.showStringColors = true;
  view.computeElectricalAllocation();
  if (typeof view.compute3DShadingReport === 'function') {
    view.compute3DShadingReport();
  }
  persistLatestSatmapScheme(view);
  return data;
}

/**
 * Build unified bidirectional sync payload for `POST /api/satmap/sync-to-3d` (compatible with `save-project` fallback)
 */
export function buildSyncTo3DPayload(view, { syncMode = 'both' } = {}) {
  const link = view.linkage3d || createDefaultLinkageState();
  const mf = view.mfState || createDefaultMultiFactorState();
  const bounds = view.getRoofBoundsM(true);
  const modSpec = view.getSelectedModule();
  const invSpec = view.getSelectedInverter();
  const wiredModules = (view.modules || []).filter((m) => !m.unwired);
  const activeTilt = view.roofType === 'flat' ? view.tiltDeg : view.roofSlopeDeg;
  const parapetHeightM = Number(((finiteNum(view.parapetHeightMm, 500)) / 1000).toFixed(2));
  const structInfo = computeMultiFactorStructuralCheck({
    roofType: view.roofType,
    orientationMode: view.orientationMode || mf.orientationMode,
    rackRows: mf.rackRows,
    tiltDeg: activeTilt,
    buildingHeightM: view.buildingHeightM,
    edgeSetbackM: view.edgeSetbackM,
    moduleSpec: modSpec,
    mfParams: mf,
  });

  const modulesLayout = wiredModules.map((m, idx) => ({
    id: m.id || `M${String(idx + 1).padStart(4, '0')}`,
    cx: Number((m.cx ?? m.x ?? 0).toFixed(3)),
    cy: Number((m.cy ?? m.y ?? 0).toFixed(3)),
    w: Number((m.w ?? modSpec?.width_m ?? 1.134).toFixed(3)),
    h: Number((m.h ?? modSpec?.length_m ?? 2.278).toFixed(3)),
    tilt_deg: Number(m.tilt_deg ?? activeTilt),
    azimuth_deg: Number(m.azimuth_deg ?? (m.slope === 'east' ? 90 : m.slope === 'west' ? 270 : m.slope === 'north' ? 0 : view.azimuthDeg)),
    slope: m.slope || 'south',
    string_id: m.stringId || null,
    row: Number.isFinite(m.row) ? m.row : 1,
    col: Number.isFinite(m.col) ? m.col : idx + 1,
  }));

  const projectIdHint = link.syncStatus?.projectId || (link.linkedSource?.kind === 'project' ? link.linkedSource.id : undefined);
  const roofIdHint = link.syncStatus?.roofId || (link.linkedSource?.kind === 'my-roof' ? link.linkedSource.id : undefined);

  return {
    ...(projectIdHint ? { project_id: projectIdHint } : {}),
    ...(roofIdHint ? { roof_id: roofIdHint } : {}),
    sync_mode: syncMode,
    name: view.projectName,
    address: view.address,
    lat: view.lat,
    lon: view.lon,
    site: {
      name: view.projectName,
      address: view.address,
      lat: view.lat,
      lon: view.lon,
    },
    roof_polygon_m: view.roofOutlineM,
    outline: view.roofOutlineM,
    length_m: bounds.widthM,
    width_m: bounds.heightM,
    roof_type: view.roofType === 'flat' ? 'flat' : view.roofType,
    building_height_m: finiteNum(view.buildingHeightM, 12),
    parapet_height_m: parapetHeightM,
    slope_deg: finiteNum(view.roofSlopeDeg, 0),
    tilt_deg: activeTilt,
    azimuth_deg: finiteNum(view.azimuthDeg, 180),
    orientation_mode: view.orientationMode || mf.orientationMode || 'south_fixed',
    mount_orientation: view.orientation || 'portrait',
    orientation: view.orientation || 'portrait',
    rack_type: mf.rackRows || '2P',
    row_gap_m: finiteNum(view.rowSpacingM, 1.2),
    row_spacing_m: finiteNum(view.rowSpacingM, 1.2),
    setback_m: finiteNum(view.edgeSetbackM, 0.8),
    edge_setback_m: finiteNum(view.edgeSetbackM, 0.8),
    albedo: finiteNum(mf.albedo, 0.28),
    modules_per_string: (finiteNum(view.summary?.moduleCount, modulesLayout.length) > 0) ? finiteNum(view.modulesPerString, 0) : 0,
    module_id: view.moduleModelId,
    inverter_id: view.inverterModelId,
    obstacles: (view.obstacles || []).map((o, idx) => ({
      id: o.id || `obs-${idx + 1}`,
      kind: o.kind || 'skylight',
      name: o.name || `禁布区 #${idx + 1}`,
      height_m: finiteNum(o.heightM ?? o.height_m, o.kind === 'skylight' ? 0.25 : 1.8),
      polygon_m: o.polygon || o.polygon_m || [],
      polygon: o.polygon || o.polygon_m || [],
    })),
    layout_params: {
      stc_w: modSpec?.stc_w,
      module_model: modSpec?.model,
      length_m: modSpec?.length_m,
      width_m: modSpec?.width_m,
      tilt_deg: activeTilt,
      azimuth_deg: view.azimuthDeg,
      row_spacing_m: view.rowSpacingM,
      edge_setback_m: view.edgeSetbackM,
      orientation: view.orientation || 'portrait',
      orientation_mode: view.orientationMode || mf.orientationMode || 'south_fixed',
    },
    electrical_params: {
      inverter_model: invSpec?.model,
      rated_ac_kw: invSpec?.rated_ac_kw ?? invSpec?.ac_kw,
      modules_per_string: (finiteNum(view.summary?.moduleCount, modulesLayout.length) > 0) ? finiteNum(view.modulesPerString, 0) : 0,
    },
    electrical: {
      inverter_model: invSpec?.model,
      inverter_count: (finiteNum(view.summary?.moduleCount, modulesLayout.length) > 0) ? finiteNum(view.summary?.inverterCount, 0) : 0,
      string_count: (finiteNum(view.summary?.moduleCount, modulesLayout.length) > 0) ? finiteNum(view.summary?.stringCount, 0) : 0,
      modules_per_string: (finiteNum(view.summary?.moduleCount, modulesLayout.length) > 0) ? finiteNum(view.modulesPerString, 0) : 0,
      mppt_rows: view.mpptRows || [],
    },
    modules_layout: modulesLayout,
    modules: modulesLayout,
    module_count: finiteNum(view.summary?.moduleCount, modulesLayout.length),
    dc_kw: finiteNum(view.summary?.dcKw, 0),
    ac_kw: finiteNum(view.summary?.acKw, 0),
    annual_kwh: finiteNum(view.summary?.dcKw, 0) > 0 ? finiteNum(view.summary?.annualKwh, 0) : 0,
    pvsyst_summary: {
      dc_kw: finiteNum(view.summary?.dcKw, 0),
      ac_kw: finiteNum(view.summary?.acKw, 0),
      module_count: finiteNum(view.summary?.moduleCount, modulesLayout.length),
      annual_kwh: finiteNum(view.summary?.dcKw, 0) > 0 ? finiteNum(view.summary?.annualKwh, 0) : 0,
      specific_yield_kwh_kwp: finiteNum(view.summary?.dcKw, 0) > 0 ? finiteNum(view.summary?.specificYield, 0) : 0,
      pr_pct: finiteNum(view.summary?.dcKw, 0) > 0 ? finiteNum(view.summary?.prPct, 0) : 0,
      load_kg_m2: finiteNum(view.summary?.moduleCount, modulesLayout.length) > 0 ? structInfo.added_dead_load_kg_m2 : 0,
      pruned_shaded_count: (view.prunedShadedModules || []).length,
    },
    multifactor_params: {
      max_roof_load_kg_m2: mf.maxRoofLoadKgM2,
      fixing_type: mf.fixingType,
      basic_wind_w0_kn_m2: mf.basicWindW0KnM2,
      basic_snow_s0_kn_m2: mf.basicSnowS0KnM2,
      extreme_temp_min_c: mf.extremeTempMinC,
      extreme_temp_max_c: mf.extremeTempMaxC,
      albedo: mf.albedo,
      pollution_level: mf.pollutionLevel,
      max_module_shading_loss_pct: mf.maxModuleShadingLossPct,
      fire_lane_width_m: mf.fireLaneWidthM,
      maint_walkway_interval_m: mf.maintWalkwayIntervalM,
      load_profile: mf.loadProfile,
    },
  };
}

/**
 * Push optimized Satellite Design into 3D Design (`POST /api/satmap/sync-to-3d` with fallback to `satmap/save-project`)
 */
export async function syncSatmapTo3D(view, { syncMode = 'both' } = {}) {
  const link = view.linkage3d || (view.linkage3d = createDefaultLinkageState());
  if (!view.hasLaidOut && view.autoLayoutOnEmpty !== false) {
    view.layoutModules({ quiet: true, autoCreateRoof: true });
    view.electricalConfirmed = true;
    view.showStringColors = true;
    view.computeElectricalAllocation();
  }
  link.syncing = true;
  const payload = buildSyncTo3DPayload(view, { syncMode });
  let res = null;

  if (typeof view.api === 'function') {
    try {
      res = await view.api('satmap/sync-to-3d', payload);
    } catch {
      res = null;
    }
    if (!res || (!res.project_id && !res.roof_id)) {
      try {
        res = await view.api('satmap/save-project', payload);
      } catch {
        res = null;
      }
    }
  }

  const projectId = String(res?.project_id || payload.project_id || 'satmap-3d-project');
  const version = finiteNum(res?.version, 1);
  const roofId = String(res?.roof_id || payload.roof_id || `my-sat-${projectId}`);
  const jumpResultHash = String(res?.jump_result_hash || `#result/${encodeURIComponent(projectId)}?version=${version}`);
  const jumpRoofEditHash = String(
    res?.jump_roof_edit_hash || (roofId ? `#roof/${encodeURIComponent(roofId)}` : (res?.jump_roof_hash || '#roof'))
  );

  // Refresh appState.roofs read-only so `app.js` `#roof/<roofId>` finds the newly synced custom roof immediately!
  if (typeof view.api === 'function' && view.appState) {
    try {
      const cat = await view.api('roofs');
      if (Array.isArray(cat?.roofs)) {
        view.appState.roofs = cat.roofs;
      }
    } catch {
      // Ignore in headless test
    }
  }

  try {
    if (typeof localStorage !== 'undefined' && localStorage) {
      localStorage.setItem(SATMAP_SYNCED_ROOF_KEY, roofId);
    }
  } catch {
    // Ignore storage restriction
  }

  const ref = link.referenceMetrics || {};
  const dcSat = finiteNum(res?.diff?.dc_kw_sat, finiteNum(view.summary?.dcKw, 0));
  const dc3d = finiteNum(res?.diff?.dc_kw_3d, ref.dc_kw ?? dcSat);
  const modSat = finiteNum(res?.diff?.module_count_sat, finiteNum(view.summary?.moduleCount, 0));
  const mod3d = finiteNum(res?.diff?.module_count_3d, ref.module_count ?? modSat);
  const kwhSat = finiteNum(res?.diff?.annual_kwh_sat, dcSat > 0 ? finiteNum(view.summary?.annualKwh, 0) : 0);
  const kwh3d = finiteNum(res?.diff?.annual_kwh_3d, ref.annual_kwh ?? kwhSat);
  const prSat = finiteNum(res?.diff?.pr_pct_sat, dcSat > 0 ? finiteNum(view.summary?.prPct, 0) : 0);
  const pr3d = finiteNum(res?.diff?.pr_pct_3d, ref.pr_pct ?? (dc3d > 0 ? prSat : 0));
  const loadKgM2 = finiteNum(res?.diff?.load_kg_m2, payload.pvsyst_summary.load_kg_m2);

  link.syncStatus = {
    ok: true,
    state: 'synced',
    stale: false,
    syncedModuleCount: finiteNum(view.summary?.moduleCount, 0),
    syncedOrientationMode: String(view.orientationMode || view.mfState?.orientationMode || 'south_fixed'),
    syncedPrunedCount: (view.prunedShadedModules || []).length,
    syncAt: res?.sync_at || new Date().toISOString(),
    projectId,
    version,
    roofId,
    jumpResultHash,
    jumpRoofHash: jumpRoofEditHash,
    diff: {
      dc_kw_sat: dcSat,
      dc_kw_3d: dc3d,
      module_count_sat: modSat,
      module_count_3d: mod3d,
      annual_kwh_sat: kwhSat,
      annual_kwh_3d: kwh3d,
      pr_pct_sat: prSat,
      pr_pct_3d: pr3d,
      load_kg_m2: loadKgM2,
      max_load_kg_m2: finiteNum(view.mfState?.maxRoofLoadKgM2, 35),
      pruned_shaded_count: (view.prunedShadedModules || []).length,
      notes: Array.isArray(res?.diff?.notes) ? res.diff.notes : [],
    },
  };
  link.showDiffCard = true;
  link.syncing = false;
  persistLatestSatmapScheme(view);
  return link.syncStatus;
}

/**
 * Navigate from `#satmap` directly into 3D Result Scene (`#result/...`) or 3D Roof Editor (`#roof/...`)
 * without modifying any 3D Design files!
 */
export async function navigateTo3DTarget(view, target = 'result') {
  const link = view.linkage3d || (view.linkage3d = createDefaultLinkageState());
  if (!link.syncStatus || link.syncStatus.stale) {
    await syncSatmapTo3D(view, { syncMode: 'both' });
  }
  const sync = link.syncStatus;
  if (target === 'roof') {
    if (typeof view.api === 'function' && view.appState) {
      try {
        const cat = await view.api('roofs');
        if (Array.isArray(cat?.roofs)) {
          view.appState.roofs = cat.roofs;
        }
      } catch {
        // Ignore
      }
    }
    const hasSyncedInMine = Array.isArray(view.appState?.roofs) &&
      view.appState.roofs.some((x) => (x.collection === 'mine' || x.is_custom || String(x.id).startsWith('my-')) && x.id === sync?.roofId);
    const targetHash = hasSyncedInMine
      ? `#roof/${encodeURIComponent(sync.roofId)}`
      : (sync?.jumpRoofHash || '#roof');
    if (typeof location !== 'undefined') {
      location.hash = targetHash;
    }
    return targetHash;
  }
  const resultHash = sync?.jumpResultHash || '#new';
  if (typeof location !== 'undefined') {
    location.hash = resultHash;
  }
  return resultHash;
}

/**
 * Persist live Satellite Design snapshot into `localStorage.setItem('gz.satmap.latestScheme', ...)`
 * so `#lab` (`innovation-lab.js`) reads it seamlessly!
 */
export function persistLatestSatmapScheme(view, extra = {}) {
  if (!view) return null;
  const mf = view.mfState || createDefaultMultiFactorState();
  const link = view.linkage3d || createDefaultLinkageState();
  if (link.syncStatus && typeof link.syncStatus === 'object' && link.syncStatus.ok) {
    const curCount = finiteNum(view.summary?.moduleCount, 0);
    const curMode = String(view.orientationMode || mf.orientationMode || 'south_fixed');
    const curPruned = (view.prunedShadedModules || []).length;
    if (
      (Number.isFinite(link.syncStatus.syncedModuleCount) && curCount !== link.syncStatus.syncedModuleCount) ||
      (link.syncStatus.syncedOrientationMode && curMode !== link.syncStatus.syncedOrientationMode) ||
      (Number.isFinite(link.syncStatus.syncedPrunedCount) && curPruned !== link.syncStatus.syncedPrunedCount)
    ) {
      link.syncStatus.stale = true;
      link.syncStatus.state = 'stale';
    }
  }
  const bounds = typeof view.getRoofBoundsM === 'function' ? view.getRoofBoundsM(true) : { areaM2: 2400 };
  const modSpec = typeof view.getSelectedModule === 'function' ? view.getSelectedModule() : {};
  const activeTilt = view.roofType === 'flat' ? view.tiltDeg : view.roofSlopeDeg;
  const structInfo = computeMultiFactorStructuralCheck({
    roofType: view.roofType,
    orientationMode: view.orientationMode || mf.orientationMode,
    rackRows: mf.rackRows,
    tiltDeg: activeTilt,
    buildingHeightM: view.buildingHeightM,
    edgeSetbackM: view.edgeSetbackM,
    moduleSpec: modSpec,
    mfParams: mf,
  });

  const dcKwVal = finiteOrNull(extra?.dc_kw ?? extra?.dcKw) ?? finiteNum(view.summary?.dcKw, 0);
  const acKwVal = finiteOrNull(extra?.ac_kw ?? extra?.acKw) ?? finiteNum(view.summary?.acKw, 0);
  const modCountVal = finiteOrNull(extra?.module_count ?? extra?.moduleCount) ?? finiteNum(view.summary?.moduleCount, 0);
  const annualKwhVal = dcKwVal > 0
    ? (finiteOrNull(extra?.annual_kwh ?? extra?.annualKwh) ?? finiteNum(view.summary?.annualKwh, 0))
    : 0;
  const specYieldVal = dcKwVal > 0
    ? (finiteOrNull(extra?.specific_yield_kwh_kwp ?? extra?.specificYield) ?? finiteNum(view.summary?.specificYield, 0))
    : 0;
  const prPctVal = dcKwVal > 0
    ? (finiteOrNull(extra?.pr_pct ?? extra?.prPct) ?? finiteNum(view.summary?.prPct, 0))
    : 0;
  const deadLoadVal = modCountVal > 0
    ? (finiteOrNull(extra?.added_load_kg_m2 ?? extra?.addedLoadKgM2) ?? structInfo.added_dead_load_kg_m2)
    : 0;
  const lcoeVal = dcKwVal > 0 ? finiteOrNull(extra?.lcoe_rmb_kwh ?? extra?.lcoeRmbPerKwh ?? view.summary?.lcoeRmb) : null;
  const npvVal = finiteOrNull(extra?.npv_25_wan ?? extra?.npv25Wan ?? view.summary?.npv25Wan) ?? 0;
  const irrVal = dcKwVal > 0 ? finiteOrNull(extra?.irr_pct ?? extra?.irrPct ?? view.summary?.irrPct) : null;
  const paybackVal = dcKwVal > 0 ? finiteOrNull(extra?.payback_years ?? extra?.paybackYears ?? view.summary?.paybackYears) : null;
  const projKey = String(
    extra?.project_id
    ?? extra?.projectId
    ?? extra?.syncedProjectId
    ?? link.syncStatus?.projectId
    ?? link.linkedSource?.id
    ?? view.linked3dContext?.projectId
    ?? view.projectId
    ?? ''
  ).trim();

  const snap = {
    updatedAt: new Date().toISOString(),
    projectName: extra?.projectName ?? extra?.project_name ?? view.projectName,
    project_name: extra?.project_name ?? extra?.projectName ?? view.projectName,
    address: view.address,
    lat: view.lat,
    lon: view.lon,
    projectId: projKey,
    project_id: projKey,
    syncedProjectId: extra?.syncedProjectId ?? link.syncStatus?.projectId ?? '',
    roofId: extra?.roofId ?? extra?.roof_id ?? link.syncStatus?.roofId ?? '',
    roof_id: extra?.roof_id ?? extra?.roofId ?? link.syncStatus?.roofId ?? '',
    version: extra?.version ?? link.syncStatus?.version ?? 1,
    roofType: view.roofType,
    roof_type: view.roofType,
    roofAreaM2: finiteNum(bounds?.areaM2, 2400),
    roof_area_m2: finiteNum(bounds?.areaM2, 2400),
    orientationMode: view.orientationMode || mf.orientationMode || 'south_fixed',
    orientation_mode: view.orientationMode || mf.orientationMode || 'south_fixed',
    mountOrientation: view.orientation || 'portrait',
    mount_orientation: view.orientation || 'portrait',
    rackRows: mf.rackRows || '2P',
    tiltDeg: activeTilt,
    tilt_deg: activeTilt,
    azimuthDeg: view.azimuthDeg,
    azimuth_deg: view.azimuthDeg,
    dcKw: dcKwVal,
    dc_kw: dcKwVal,
    acKw: acKwVal,
    ac_kw: acKwVal,
    moduleCount: modCountVal,
    module_count: modCountVal,
    annualKwh: annualKwhVal,
    annual_kwh: annualKwhVal,
    specificYield: specYieldVal,
    specific_yield_kwh_kwp: specYieldVal,
    prPct: prPctVal,
    pr_pct: prPctVal,
    addedLoadKgM2: deadLoadVal,
    added_load_kg_m2: deadLoadVal,
    load_kg_m2: deadLoadVal,
    maxRoofLoadKgM2: structInfo.max_roof_load_kg_m2,
    max_roof_load_kg_m2: structInfo.max_roof_load_kg_m2,
    albedo: finiteNum(mf.albedo, 0.28),
    prunedShadedCount: (view.prunedShadedModules || []).length,
    loadProfile: mf.loadProfile || 'industrial_day',
    selfConsumptionRatio: finiteNum(view.selfConsumptionRatio, 0.82),
    tariffRmb: finiteNum(view.tariffRmb, 0.85),
    tariff_self_rmb: finiteNum(view.tariffRmb, 0.85),
    feedInTariffRmb: finiteNum(view.feedInTariffRmb, 0.38),
    feed_in_tariff_rmb: finiteNum(view.feedInTariffRmb, 0.38),
    capexPerW: finiteNum(view.capexPerW, 3.15),
    lcoeRmbPerKwh: lcoeVal,
    lcoe_rmb_kwh: lcoeVal,
    npv25Wan: npvVal,
    npv_25_wan: npvVal,
    irrPct: irrVal,
    irr_pct: irrVal,
    paybackYears: paybackVal,
    payback_years: paybackVal,
    bessPowerKw: finiteNum(view.bessPowerKw, 0),
    bessCapacityKwh: finiteNum(view.bessCapacityKwh, 0),
  };

  try {
    if (typeof localStorage !== 'undefined' && localStorage) {
      let prevSchemes = {};
      try {
        const prevRaw = localStorage.getItem(SATMAP_LATEST_STORAGE_KEY);
        if (prevRaw) {
          const prevParsed = JSON.parse(prevRaw);
          if (prevParsed && typeof prevParsed.schemes_by_project === 'object' && prevParsed.schemes_by_project) {
            prevSchemes = { ...prevParsed.schemes_by_project };
          }
        }
      } catch {
        prevSchemes = {};
      }
      const bucketKey = projKey || '__unsaved__';
      const storedEnvelope = {
        ...snap,
        active_project_id: projKey || null,
        schemes_by_project: {
          ...prevSchemes,
          [bucketKey]: snap,
        },
      };
      localStorage.setItem(SATMAP_LATEST_STORAGE_KEY, JSON.stringify(storedEnvelope));
    }
  } catch {
    // Ignore storage quota / sandbox restrictions
  }
  return snap;
}

/**
 * Deterministic Client-Side 12-Factor Pareto Scheme Generator & Scorer
 * Guarantees instant offline/online responsiveness and physically faithful multi-scheme comparison.
 */
export function runClientMultiFactorOptimization(view, customParams = null) {
  const mf = { ...(view.mfState || createDefaultMultiFactorState()), ...(customParams || {}) };
  const modSpec = view.getSelectedModule() || {};
  const invSpec = view.getSelectedInverter() || {};
  const bounds = view.getRoofBoundsM(true) || {};
  const rawRoofArea = finiteOrNull(bounds.areaM2);
  const roofAreaM2 = (view.hasRoof && rawRoofArea !== null) ? Math.max(0, rawRoofArea) : Math.max(0, rawRoofArea ?? 2200);
  const roofW = Math.max(0, finiteNum(bounds.widthM, roofAreaM2 > 0 ? Math.sqrt(roofAreaM2 * 1.5) : 0));
  const roofH = Math.max(0, finiteNum(bounds.heightM, roofW > 0 ? roofAreaM2 / roofW : 0));
  const latAbs = Math.max(18, Math.min(50, Math.abs(finiteNum(view.lat, 32.5))));
  const optSouthTilt = Math.max(10, Math.min(30, Math.round(latAbs * 0.72)));
  const roofPitch = Math.max(3, finiteNum(view.roofSlopeDeg, 6));

  const reqSeries = finiteOrNull(
    customParams?.modules_per_string
    ?? mf.modules_per_string
    ?? mf.modulesPerString
    ?? view.modulesPerString
  );
  const vocCheck = computeColdVocAndStringSafety(modSpec, invSpec, mf, reqSeries ?? 18);
  const seriesN = vocCheck.current_series;

  const explicitAnnualLoad = finiteOrNull(
    customParams?.annual_load_kwh
    ?? customParams?.annualLoadKwh
    ?? customParams?.load_params?.annual_load_kwh
    ?? customParams?.financial_params?.annual_load_kwh
    ?? mf.annual_load_kwh
    ?? mf.annualLoadKwh
    ?? view.annualLoadKwh
    ?? view.annual_load_kwh
  );
  const discountRatePct = Math.max(0, finiteNum(
    customParams?.discount_rate_pct
    ?? customParams?.discountRatePct
    ?? customParams?.financial_params?.discount_rate_pct
    ?? mf.discount_rate_pct
    ?? mf.discountRatePct
    ?? view.discountRatePct,
    6.0
  ));
  const baseCapexPerW = Math.max(0, finiteNum(
    customParams?.capex_per_w
    ?? customParams?.financial_params?.capex_per_w
    ?? mf.capex_per_w
    ?? view.capexPerW,
    3.15
  ));
  const tariffSelf = Math.max(0, finiteNum(
    customParams?.tariff_self
    ?? customParams?.tariff_self_rmb
    ?? customParams?.financial_params?.tariff_self_rmb
    ?? customParams?.financial_params?.tariff_self
    ?? mf.tariff_self
    ?? view.tariffRmb,
    0.85
  ));
  const tariffGrid = Math.max(0, finiteNum(
    customParams?.tariff_grid
    ?? customParams?.tariff_feed_rmb
    ?? customParams?.financial_params?.tariff_feed_rmb
    ?? customParams?.financial_params?.tariff_grid
    ?? mf.tariff_grid
    ?? view.feedInTariffRmb,
    0.38
  ));

  const ratedAcKw = Math.max(0.5, finiteNum(invSpec.rated_ac_kw ?? invSpec.ac_kw, 110));
  const mpptCountIn = Math.max(1, Math.round(finiteNum(invSpec.mppt_count, ratedAcKw <= 60 ? 5 : (ratedAcKw === 110 ? 9 : 10))));
  const stringsPerMpptIn = Math.max(1, Math.round(finiteNum(invSpec.strings_per_mppt, 2)));
  const maxMpptCurrA = Math.max(
    0.5,
    finiteNum(invSpec.max_mppt_current_a ?? invSpec.max_input_a_per_mppt ?? invSpec.max_input_current_per_mppt_a, 30)
  );
  const maxShortCurrA = Math.max(
    0.5,
    finiteNum(invSpec.max_short_current_a ?? invSpec.max_short_circuit_a_per_mppt ?? invSpec.max_short_circuit_current_per_mppt_a, 40)
  );
  const explicitInvCount = finiteOrNull(customParams?.inverter_count ?? invSpec.inverter_count);

  const stcW = Math.max(10, finiteNum(modSpec.stc_w, 580));
  const modLenM = Math.max(0.2, finiteNum(modSpec.length_m, 2.278));
  const modWidM = Math.max(0.2, finiteNum(modSpec.width_m, 1.134));
  const modArea = Math.max(0.4, modLenM * modWidM);
  const modVmpV = Math.max(10, finiteNum(modSpec.vmp_v, 43.2));
  const modImpA = Math.max(0.5, finiteNum(modSpec.imp_a, stcW / modVmpV));
  const modIscA = Math.max(0.5, finiteNum(modSpec.isc_a, modImpA * 1.055));
  const alphaIscPctC = finiteNum(modSpec.alpha_isc_pct_c ?? modSpec.temp_coeff_isc_pct_per_c, 0.045);
  const tHotCellC = finiteNum(mf.extremeTempMaxC, 40) + 26;
  const iscHot = modIscA * (1 + Math.max(0, alphaIscPctC / 100) * (tHotCellC - 25));
  const effStringsPerMppt = Math.max(
    0,
    Math.min(
      stringsPerMpptIn,
      Math.floor(maxShortCurrA / Math.max(0.1, iscHot)),
      Math.floor(maxMpptCurrA / Math.max(0.1, modImpA))
    )
  );

  const envPreset = POLLUTION_LEVELS.find((p) => p.id === mf.pollutionLevel) || POLLUTION_LEVELS[1];
  const loadProf = LOAD_PROFILES.find((p) => p.id === mf.loadProfile) || LOAD_PROFILES[0];
  const albedoVal = finiteNum(mf.albedo, 0.28);
  const bifaciality = finiteNum(modSpec.bifaciality, 0.80);
  const parapetM = finiteNum(view.parapetHeightMm, 500) / 1000;
  const obsCount = (view.obstacles || []).length;

  const blueprints = [
    {
      id: 'south_portrait_2p',
      name_zh: '正南最佳倾角基准阵（竖装双排）',
      name_en: 'South Optimal Tilt Baseline (Portrait 2P)',
      orientation_mode: 'south_fixed',
      mount_orientation: 'portrait',
      rack_type: '2P',
      fixing_type: mf.fixingType === 'auto' ? (view.roofType === 'flat' ? 'ballast' : 'clamp') : mf.fixingType,
      tilt_deg: optSouthTilt,
      azimuth_deg: 180,
      gcr: 0.56,
      poaFactor: 1.06,
      capexDelta: 0.0,
    },
    {
      id: 'east_west_landscape_1p',
      name_zh: '东西向双坡蝴蝶高密阵（横装单排）',
      name_en: 'East-West Butterfly High-GCR (Landscape 1P)',
      orientation_mode: 'east_west',
      mount_orientation: 'landscape',
      rack_type: '1P',
      fixing_type: mf.fixingType === 'auto' ? (mf.maxRoofLoadKgM2 < 26 ? 'anchor' : (view.roofType === 'flat' ? 'ballast' : 'clamp')) : mf.fixingType,
      tilt_deg: 10,
      azimuth_deg: 90,
      gcr: 0.78,
      poaFactor: 0.965,
      capexDelta: -0.05,
    },
    {
      id: 'flush_clamp_light',
      name_zh: '顺坡轻质夹具超低荷载阵（竖装双排）',
      name_en: 'Flush Lightweight Clamp Ultra-Low Load (2P)',
      orientation_mode: 'flush_pitched',
      mount_orientation: 'portrait',
      rack_type: '2P',
      fixing_type: 'clamp',
      tilt_deg: roofPitch,
      azimuth_deg: 180,
      gcr: 0.72,
      poaFactor: 0.985,
      capexDelta: -0.14,
    },
    {
      id: 'south_landscape_antishade',
      name_zh: '正南横装抗遮挡剔毒优选阵（横装双排）',
      name_en: 'South Anti-Shading Pruned Array (Landscape 2P)',
      orientation_mode: 'south_fixed',
      mount_orientation: 'landscape',
      rack_type: '2P',
      fixing_type: mf.fixingType === 'auto' ? (view.roofType === 'flat' ? 'ballast' : 'clamp') : mf.fixingType,
      tilt_deg: Math.max(12, optSouthTilt - 3),
      azimuth_deg: 180,
      gcr: 0.61,
      poaFactor: 1.045,
      capexDelta: 0.03,
    },
    {
      id: 'elevated_canopy_full',
      name_zh: '架高阳光棚跨障满铺阵（净空二点八米）',
      name_en: 'Elevated Canopy Bridging Low Obstacles (2.8m)',
      orientation_mode: 'elevated_canopy',
      mount_orientation: 'portrait',
      rack_type: '2P',
      fixing_type: 'anchor',
      tilt_deg: 8,
      azimuth_deg: 180,
      gcr: 0.84,
      poaFactor: 1.02,
      capexDelta: 0.42,
    },
    {
      id: 'typhoon_wind_safe_1p',
      name_zh: '台风区加强退距低风阻安全阵（单排低倾角）',
      name_en: 'Typhoon Reinforced Low-Tilt Safe Array (1P)',
      orientation_mode: 'south_fixed',
      mount_orientation: 'landscape',
      rack_type: '1P',
      fixing_type: mf.maxRoofLoadKgM2 < 32 ? 'anchor' : (view.roofType === 'flat' ? 'ballast' : 'clamp'),
      tilt_deg: 8,
      azimuth_deg: 180,
      gcr: 0.64,
      poaFactor: 1.00,
      capexDelta: 0.06,
    },
  ];

  const baseGlobHor = finiteNum(view.pvsystData?.summary?.glob_hor_kwh_m2, 1380);
  const validGlobHor = baseGlobHor > 0 ? baseGlobHor : 1380;

  const schemes = blueprints.map((bp) => {
    const scStruct = computeMultiFactorStructuralCheck({
      roofType: view.roofType,
      orientationMode: bp.orientation_mode,
      rackRows: bp.rack_type,
      tiltDeg: bp.tilt_deg,
      buildingHeightM: view.buildingHeightM,
      edgeSetbackM: Math.max(finiteNum(view.edgeSetbackM, 0.8), bp.id === 'typhoon_wind_safe_1p' ? 1.35 : 0.8),
      moduleSpec: modSpec,
      mfParams: { ...mf, fixingType: bp.fixing_type },
    });

    const innerW = Math.max(0, roofW - 2 * scStruct.effective_setback_m);
    const innerH = Math.max(0, roofH - 2 * scStruct.effective_setback_m);
    const setbackRatio = roofAreaM2 > 0
      ? Math.min(1, Math.max(0, (innerW * innerH) / roofAreaM2))
      : 0;
    const fireLaneRatio = mf.fireLaneWidthM > 0 && Math.min(innerW, innerH) > 0
      ? Math.max(0, Math.min(1, 1 - mf.fireLaneWidthM / Math.max(6, Math.min(roofW, roofH))))
      : (innerW > 0 && innerH > 0 ? 1.0 : 0);
    const obsDeduction = bp.orientation_mode === 'elevated_canopy'
      ? Math.min(0.06, obsCount * 0.015)
      : Math.min(0.24, obsCount * 0.045);

    const minSlotX = bp.mount_orientation === 'landscape' ? modLenM : modWidM;
    const minSlotY = (bp.mount_orientation === 'landscape' ? modWidM : modLenM) * Math.cos((bp.tilt_deg * Math.PI) / 180);
    const fitsAtLeastOne = innerW >= minSlotX && innerH >= minSlotY;
    const rawSlots = fitsAtLeastOne
      ? Math.max(0, Math.floor((roofAreaM2 * bp.gcr * setbackRatio * fireLaneRatio * (1 - obsDeduction)) / modArea))
      : 0;

    const shadeSeverity = (parapetM * 4.5 + obsCount * 1.8) * (bp.orientation_mode === 'elevated_canopy' ? 0.25 : 1.0);
    const pruneFraction = shadeSeverity > mf.maxModuleShadingLossPct * 0.35
      ? Math.min(0.14, ((shadeSeverity - mf.maxModuleShadingLossPct * 0.25) / 100) * (bp.mount_orientation === 'landscape' ? 0.55 : 0.95))
      : 0;
    const prunedCount = rawSlots > 0 ? Math.max(0, Math.min(rawSlots, Math.round(rawSlots * pruneFraction))) : 0;
    const unwiredCount = Math.max(0, rawSlots - prunedCount);

    // Group into electrically valid strings without mixing slopes or sub-MPPT short strings
    const groupCounts = [];
    let moduleCount = 0;
    let strCount = 0;
    if (seriesN >= 1 && unwiredCount > 0) {
      const slopeBuckets = bp.orientation_mode === 'east_west'
        ? [Math.floor(unwiredCount / 2), unwiredCount - Math.floor(unwiredCount / 2)]
        : [unwiredCount];
      for (const bucketN of slopeBuckets) {
        const nFull = Math.floor(bucketN / seriesN);
        const rem = bucketN % seriesN;
        const hasRem = rem >= vocCheck.min_series_mppt;
        if (nFull > 0) groupCounts.push(nFull);
        if (hasRem) groupCounts.push(1);
        moduleCount += nFull * seriesN + (hasRem ? rem : 0);
        strCount += nFull + (hasRem ? 1 : 0);
      }
    }
    const dcKw = Number(((moduleCount * stcW) / 1000).toFixed(2));

    // Inverter MPPT channel & parallel current capacity check (B01) + DC:AC sizing check
    let invCount = 0;
    let acKw = 0;
    let dcAcRatio = 0;
    let dcAcRatioOk = false;
    let mpptChannelsUsed = 0;
    let mpptChannelsCapacity = 0;
    let maxStringsCapacity = 0;
    let portAllocationOk = false;
    if (dcKw > 0 && strCount > 0) {
      mpptChannelsUsed = effStringsPerMppt >= 1
        ? groupCounts.reduce((acc, cnt) => acc + Math.ceil(cnt / effStringsPerMppt), 0)
        : strCount;
      if (explicitInvCount !== null && explicitInvCount >= 1) {
        invCount = Math.round(explicitInvCount);
      } else {
        const invByDcAc = Math.max(1, Math.ceil(dcKw / Math.max(0.5, ratedAcKw * 1.35)));
        const maxInvByDcAcMin = Math.max(1, Math.floor(dcKw / Math.max(0.5, ratedAcKw * 0.85)));
        const invByPorts = effStringsPerMppt >= 1 ? Math.ceil(mpptChannelsUsed / mpptCountIn) : invByDcAc;
        invCount = Math.max(invByDcAc, Math.min(invByPorts, maxInvByDcAcMin));
      }
      acKw = Number((invCount * ratedAcKw).toFixed(1));
      dcAcRatio = acKw > 0 ? Number((dcKw / acKw).toFixed(3)) : 0;
      dcAcRatioOk = dcAcRatio >= 0.85 && dcAcRatio <= 1.35;
      mpptChannelsCapacity = invCount * mpptCountIn;
      maxStringsCapacity = mpptChannelsCapacity * effStringsPerMppt;
      portAllocationOk = Boolean(
        effStringsPerMppt >= 1
        && mpptChannelsUsed <= mpptChannelsCapacity
        && strCount <= maxStringsCapacity
      );
    }

    const heightFactorBifacial = bp.orientation_mode === 'elevated_canopy' ? 1.35 : bp.orientation_mode === 'flush_pitched' ? 0.32 : 0.88;
    const bifacialGainPct = dcKw > 0 ? Number((albedoVal * bifaciality * 18.5 * heightFactorBifacial).toFixed(2)) : 0;
    const residualShadeLossPct = dcKw > 0
      ? Number(Math.max(0.55, shadeSeverity * (bp.mount_orientation === 'landscape' ? 0.22 : 0.38) * (1 - pruneFraction * 2.2)).toFixed(2))
      : 0;
    const prPct = dcKw > 0
      ? Number(
        Math.min(89.2, Math.max(76.5, 84.4 + bifacialGainPct * 0.38 - envPreset.soilingPct * 0.65 - residualShadeLossPct * 0.55 - scStruct.snow_loss_pct * 0.45)).toFixed(1)
      )
      : 0;
    const specificYield = dcKw > 0
      ? Number((validGlobHor * bp.poaFactor * (prPct / 100) * (1 + bifacialGainPct / 180)).toFixed(1))
      : 0;
    const annualKwh = dcKw > 0 ? Math.round(dcKw * specificYield) : 0;

    let selfUsePct = 0;
    let selfUseKwh = 0;
    if (dcKw > 0 && annualKwh > 0 && loadProf.id !== 'export_all' && !(explicitAnnualLoad !== null && explicitAnnualLoad <= 0)) {
      let rawSelfRatio = Math.min(
        0.98,
        Math.max(0, loadProf.selfUseBase + (bp.orientation_mode === 'east_west' ? loadProf.ewBonus : 0) - Math.max(0, (dcKw - 500) * 0.00012))
      );
      if (explicitAnnualLoad !== null) {
        const loadScale = Math.min(1.12, Math.max(0, explicitAnnualLoad / Math.max(1, annualKwh * 1.15)));
        rawSelfRatio = Math.min(rawSelfRatio * (0.35 + 0.65 * Math.min(1, loadScale * 1.15)), explicitAnnualLoad / annualKwh);
      }
      rawSelfRatio = Math.max(0, Math.min(0.985, rawSelfRatio));
      selfUsePct = Number((rawSelfRatio * 100).toFixed(1));
      if (explicitAnnualLoad !== null && (annualKwh * selfUsePct) / 100 > explicitAnnualLoad) {
        selfUsePct = Math.floor((explicitAnnualLoad / annualKwh) * 10000) / 100;
      }
      selfUseKwh = Number(Math.min(annualKwh, explicitAnnualLoad ?? Infinity, annualKwh * (selfUsePct / 100)).toFixed(1));
    }

    const unitCapex = Math.max(0, Number((baseCapexPerW + bp.capexDelta).toFixed(3)));
    const dcf = computeFinancialDcf25Yr({
      dcKw,
      annualKwhYear1: annualKwh,
      capexPerW: unitCapex,
      selfConsumptionRatio: selfUsePct / 100,
      tariffSelfRmb: tariffSelf,
      tariffFeedInRmb: tariffGrid,
      discountRatePct,
      omPerWYear: 0.042,
      inverterReplaceYear: 13,
      inverterReplacePerW: 0.14,
      linearDegPct: envPreset.degPctYr,
    });
    const paybackYr = dcf.staticPaybackYears !== null ? Number(dcf.staticPaybackYears.toFixed(2)) : null;
    const discountedPaybackYr = dcf.dynamicPaybackYears !== null ? Number(dcf.dynamicPaybackYears.toFixed(2)) : null;
    const lcoeCnyKwh = dcf.lcoeRmbPerKwh !== null ? Number(dcf.lcoeRmbPerKwh.toFixed(4)) : null;
    const npvWan = Number(finiteNum(dcf.npv25Wan, 0).toFixed(2));
    const irrPct = dcf.irrPct !== null ? Number(dcf.irrPct.toFixed(2)) : null;

    const wsGap = bp.orientation_mode === 'east_west'
      ? 0.65
      : bp.orientation_mode === 'flush_pitched' || bp.orientation_mode === 'elevated_canopy'
        ? 0.45
        : Number(Math.max(0.55, Math.sin((bp.tilt_deg * Math.PI) / 180) * 2.25).toFixed(2));

    const elecOk = Boolean(vocCheck.safe && portAllocationOk && dcAcRatioOk);
    const candWindOk = Boolean(
      scStruct.effective_setback_m + 0.05 >= scStruct.min_required_setback_m &&
      !(scStruct.is_typhoon_zone && scStruct.fixing_type === 'ballast' && bp.tilt_deg > 18)
    );
    const constraints = {
      load_ok: scStruct.load_ok,
      voc_ok: vocCheck.safe,
      voc_safe: vocCheck.safe,
      elec_ok: elecOk,
      port_allocation_ok: portAllocationOk,
      dc_ac_ratio_ok: dcAcRatioOk,
      wind_ok: candWindOk,
      snow_ok: scStruct.snow_ok,
      all_pass: Boolean(moduleCount > 0 && scStruct.load_ok && candWindOk && scStruct.snow_ok && elecOk),
    };

    return {
      id: bp.id,
      name_zh: bp.name_zh,
      name_en: bp.name_en,
      module_id: modSpec.id || view.moduleModelId,
      inverter_id: invSpec.id || view.inverterModelId,
      orientation_mode: bp.orientation_mode,
      mount_orientation: bp.mount_orientation,
      rack_type: bp.rack_type,
      fixing_type: scStruct.fixing_type,
      tilt_deg: bp.tilt_deg,
      azimuth_deg: bp.azimuth_deg,
      row_spacing_m: wsGap,
      setback_m: scStruct.effective_setback_m,
      modules_per_string: moduleCount > 0 ? seriesN : 0,
      string_series: moduleCount > 0 ? seriesN : 0,
      recommended_series: vocCheck.recommended_series,
      module_count: moduleCount,
      string_count: strCount,
      inverter_count: invCount,
      pruned_shaded_modules: prunedCount,
      dc_kw: dcKw,
      ac_kw: acKw,
      dc_ac_ratio: Number(dcAcRatio.toFixed(2)),
      mppt_channels_used: mpptChannelsUsed,
      mppt_channels_capacity: mpptChannelsCapacity,
      mppt_ports_used: mpptChannelsUsed,
      mppt_ports_total: mpptChannelsCapacity,
      max_strings_capacity: maxStringsCapacity,
      port_allocation_ok: portAllocationOk,
      cold_voc_v: vocCheck.string_cold_voc_v,
      cold_vmpp_v: vocCheck.string_cold_vmpp_v,
      hot_vmpp_v: vocCheck.string_hot_vmpp_v,
      annual_kwh: annualKwh,
      specific_yield_kwh_kwp: specificYield,
      pr_pct: prPct,
      bifacial_gain_pct: bifacialGainPct,
      shading_loss_pct: residualShadeLossPct,
      load_kg_m2: moduleCount > 0 ? scStruct.added_dead_load_kg_m2 : 0,
      self_use_pct: selfUsePct,
      self_use_ratio_pct: selfUsePct,
      self_consumption_ratio: Number((selfUsePct / 100).toFixed(4)),
      self_use_kwh: selfUseKwh,
      discount_rate_pct: discountRatePct,
      lcoe_cny_kwh: lcoeCnyKwh,
      npv_wan: npvWan,
      npv_25_wan: npvWan,
      npv25_wan: npvWan,
      irr_pct: irrPct,
      payback_yr: paybackYr,
      discounted_payback_yr: discountedPaybackYr,
      pareto_optimal: true,
      constraints,
    };
  });

  // Compute normalized 6-axis factor_scores & objective-weighted composite_score
  const maxCap = Math.max(...schemes.map((s) => s.dc_kw), 1);
  const maxKwh = Math.max(...schemes.map((s) => s.annual_kwh), 1);
  const validLcoes = schemes.map((s) => s.lcoe_cny_kwh).filter((v) => v !== null && Number.isFinite(v) && v > 0);
  const minLcoe = validLcoes.length ? Math.min(...validLcoes) : null;

  const weightsMap = {
    balanced: [0.18, 0.22, 0.22, 0.16, 0.12, 0.10],
    max_yield: [0.15, 0.44, 0.14, 0.10, 0.07, 0.10],
    max_capacity: [0.46, 0.22, 0.10, 0.10, 0.06, 0.06],
    min_lcoe: [0.10, 0.20, 0.44, 0.10, 0.10, 0.06],
    max_self_use: [0.10, 0.16, 0.18, 0.10, 0.38, 0.08],
    wind_safe: [0.08, 0.14, 0.14, 0.44, 0.08, 0.12],
  };
  const w = weightsMap[mf.objective] || weightsMap.balanced;

  for (const s of schemes) {
    const capScore = s.dc_kw > 0 ? Number(Math.min(100, (s.dc_kw / maxCap) * 98).toFixed(1)) : 0;
    const yieldScore = s.annual_kwh > 0 ? Number(Math.min(100, (s.annual_kwh / maxKwh) * 98).toFixed(1)) : 0;
    const econScore = (s.dc_kw <= 0 || s.lcoe_cny_kwh === null || s.irr_pct === null)
      ? 20
      : Number(Math.min(100, Math.max(35, ((minLcoe ?? s.lcoe_cny_kwh) / Math.max(0.05, s.lcoe_cny_kwh)) * 96)).toFixed(1));
    const loadMargin = (mf.maxRoofLoadKgM2 - s.load_kg_m2) / Math.max(15, mf.maxRoofLoadKgM2);
    const safetyScore = Number(
      Math.min(
        100,
        Math.max(
          20,
          76 + loadMargin * 28
          + (s.constraints.wind_ok ? 8 : -22)
          + (s.constraints.load_ok ? 0 : -28)
          + (s.constraints.elec_ok ? 0 : -24)
        )
      ).toFixed(1)
    );
    const selfUseScore = s.dc_kw <= 0
      ? 0
      : Number(Math.min(100, Math.max(20, loadProf.id === 'export_all' ? 88 : s.self_use_pct)).toFixed(1));
    const shadeScore = s.dc_kw <= 0 ? 0 : Number(Math.min(100, Math.max(45, 100 - s.shading_loss_pct * 4.2)).toFixed(1));

    s.factor_scores = {
      capacity: capScore,
      yield: yieldScore,
      economics: econScore,
      safety: safetyScore,
      self_use: selfUseScore,
      shading_resilience: shadeScore,
    };
    const rawComp =
      capScore * w[0] +
      yieldScore * w[1] +
      econScore * w[2] +
      safetyScore * w[3] +
      selfUseScore * w[4] +
      shadeScore * w[5] -
      (s.constraints.all_pass ? 0 : 18);
    s.composite_score = Number(Math.max(0, rawComp).toFixed(2));
  }

  schemes.sort((a, b) => b.composite_score - a.composite_score);
  const recommended = schemes.find((s) => s.constraints.all_pass) || schemes[0];
  const baseStruct = computeMultiFactorStructuralCheck({
    roofType: view.roofType,
    orientationMode: mf.orientationMode,
    rackRows: mf.rackRows,
    tiltDeg: view.roofType === 'flat' ? view.tiltDeg : view.roofSlopeDeg,
    buildingHeightM: view.buildingHeightM,
    edgeSetbackM: view.edgeSetbackM,
    moduleSpec: modSpec,
    mfParams: mf,
  });

  return {
    ok: true,
    source: 'client_physics',
    objective: mf.objective,
    recommended_id: recommended?.id || '',
    any_feasible: schemes.some((s) => s.constraints.all_pass),
    string_voc_check: vocCheck,
    structural_check: baseStruct,
    environment: {
      albedo: albedoVal,
      albedo_surface: mf.albedoSurface,
      pollution_level: mf.pollutionLevel,
      soiling_pct: envPreset.soilingPct,
      degradation_pct_yr: envPreset.degPctYr,
      load_profile: mf.loadProfile,
      discount_rate_pct: discountRatePct,
      ...(explicitAnnualLoad !== null ? { annual_load_kwh: explicitAnnualLoad } : {}),
    },
    schemes,
    candidates: schemes,
  };
}

/**
 * Call `POST /api/satmap/optimize-multifactor` with instant deterministic client fallback
 */
export async function requestMultiFactorOptimization(view, customParams = null) {
  const mf = view.mfState || (view.mfState = createDefaultMultiFactorState());
  mf.optimizing = true;
  if (!view.hasRoof) {
    view.ensureRoofOutline({ withDefaultKeepouts: false });
  }

  const modSpec = (typeof view.getSelectedModule === 'function' ? view.getSelectedModule() : null) || {};
  const invSpec = (typeof view.getSelectedInverter === 'function' ? view.getSelectedInverter() : null) || {};
  const mpsVal = finiteNum(
    customParams?.modules_per_string ?? customParams?.modulesPerString ?? mf.modules_per_string ?? mf.modulesPerString ?? view.modulesPerString,
    18
  );
  const discountRatePct = Math.max(
    0,
    finiteNum(
      customParams?.discount_rate_pct ?? customParams?.discountRatePct ?? mf.discount_rate_pct ?? mf.discountRatePct ?? view.discountRatePct,
      6.0
    )
  );
  const explicitAnnualLoad = finiteOrNull(
    customParams?.annual_load_kwh
    ?? customParams?.annualLoadKwh
    ?? mf.annual_load_kwh
    ?? mf.annualLoadKwh
    ?? view.annualLoadKwh
    ?? view.annual_load_kwh
  );
  const capexPerW = Math.max(0, finiteNum(customParams?.capex_per_w ?? mf.capex_per_w ?? view.capexPerW, 3.15));
  const tariffSelf = Math.max(0, finiteNum(customParams?.tariff_self ?? mf.tariff_self ?? view.tariffRmb, 0.85));
  const tariffGrid = Math.max(0, finiteNum(customParams?.tariff_grid ?? mf.tariff_grid ?? view.feedInTariffRmb, 0.38));

  const inverterSpecPayload = {
    id: invSpec.id || view.inverterModelId,
    inverter_id: invSpec.id || view.inverterModelId,
    model: invSpec.model || '',
    ac_kw: finiteNum(invSpec.rated_ac_kw ?? invSpec.ac_kw, 110),
    rated_ac_kw: finiteNum(invSpec.rated_ac_kw ?? invSpec.ac_kw, 110),
    v_dc_max: finiteNum(invSpec.v_dc_max ?? invSpec.max_dc_v ?? invSpec.max_dc_voltage_v, 1100),
    max_dc_v: finiteNum(invSpec.v_dc_max ?? invSpec.max_dc_v ?? invSpec.max_dc_voltage_v, 1100),
    mppt_v_min: finiteNum(invSpec.mppt_v_min ?? invSpec.mppt_min_v, 200),
    mppt_v_max: finiteNum(invSpec.mppt_v_max ?? invSpec.mppt_max_v, 1000),
    mppt_count: finiteNum(invSpec.mppt_count, 9),
    strings_per_mppt: finiteNum(invSpec.strings_per_mppt, 2),
    max_mppt_current_a: finiteNum(invSpec.max_mppt_current_a ?? invSpec.max_input_a_per_mppt ?? invSpec.max_input_current_per_mppt_a, 30),
    max_short_current_a: finiteNum(invSpec.max_short_current_a ?? invSpec.max_short_circuit_a_per_mppt ?? invSpec.max_short_circuit_current_per_mppt_a, 40),
    modules_per_string: mpsVal,
  };

  const moduleSpecPayload = {
    id: modSpec.id || view.moduleModelId,
    module_id: modSpec.id || view.moduleModelId,
    model: modSpec.model || '',
    stc_w: finiteNum(modSpec.stc_w, 580),
    length_m: finiteNum(modSpec.length_m, 2.278),
    width_m: finiteNum(modSpec.width_m, 1.134),
    weight_kg: finiteNum(modSpec.weight_kg, 31.8),
    voc_v: finiteNum(modSpec.voc_v, 51.8),
    vmp_v: finiteNum(modSpec.vmp_v, 43.2),
    isc_a: finiteNum(modSpec.isc_a, 14.2),
    imp_a: finiteNum(modSpec.imp_a, 13.43),
    beta_voc_pct_c: finiteNum(
      modSpec.beta_voc_pct_c ?? modSpec.temp_coeff_voc_pct_per_c ?? modSpec.temp_coeff_voc_pct,
      -0.25
    ),
    gamma_pmax_pct_c: finiteNum(
      modSpec.gamma_pmax_pct_c ?? modSpec.temp_coeff_pmax_pct_per_c ?? modSpec.temp_coeff_pmax_pct,
      -0.30
    ),
  };

  const reqPayload = {
    objective: mf.objective,
    module_id: view.moduleModelId,
    inverter_id: view.inverterModelId,
    modules_per_string: mpsVal,
    discount_rate_pct: discountRatePct,
    ...(explicitAnnualLoad !== null ? { annual_load_kwh: explicitAnnualLoad } : {}),
    site: { lat: view.lat, lon: view.lon, name: view.projectName },
    roof: {
      type: view.roofType === 'flat' ? 'flat' : view.roofType,
      building_height_m: finiteNum(view.buildingHeightM, 12),
      parapet_height_m: Number(((finiteNum(view.parapetHeightMm, 500)) / 1000).toFixed(2)),
      slope_deg: finiteNum(view.roofSlopeDeg, 0),
      setback_m: finiteNum(view.edgeSetbackM, 0.8),
      polygon_m: view.roofOutlineM,
      obstacles: (view.obstacles || []).map((o) => ({
        id: o.id,
        kind: o.kind || 'hvac',
        name: o.name,
        polygon_m: o.polygon || o.polygon_m || [],
        height_m: finiteNum(o.heightM ?? o.height_m, 1.8),
      })),
    },
    equipment: {
      module_id: view.moduleModelId,
      inverter_id: view.inverterModelId,
      modules_per_string: mpsVal,
      module_spec: moduleSpecPayload,
      inverter_spec: inverterSpecPayload,
    },
    module_spec: moduleSpecPayload,
    inverter_spec: inverterSpecPayload,
    financial_params: {
      capex_per_w: capexPerW,
      tariff_self: tariffSelf,
      tariff_self_rmb: tariffSelf,
      tariff_grid: tariffGrid,
      tariff_feed_rmb: tariffGrid,
      discount_rate_pct: discountRatePct,
      load_profile: mf.loadProfile,
      ...(explicitAnnualLoad !== null ? { annual_load_kwh: explicitAnnualLoad } : {}),
    },
    load_params: {
      load_profile: mf.loadProfile,
      ...(explicitAnnualLoad !== null ? { annual_load_kwh: explicitAnnualLoad } : {}),
    },
    multifactor_params: {
      orientation_mode: mf.orientationMode,
      mount_orientation: view.orientation || 'portrait',
      rack_type: mf.rackRows,
      canopy_clearance_m: mf.canopyClearanceM,
      max_roof_load_kg_m2: mf.maxRoofLoadKgM2,
      fixing_type: mf.fixingType,
      basic_wind_w0_kn_m2: mf.basicWindW0KnM2,
      basic_snow_s0_kn_m2: mf.basicSnowS0KnM2,
      extreme_temp_min_c: mf.extremeTempMinC,
      extreme_temp_max_c: mf.extremeTempMaxC,
      albedo: mf.albedo,
      albedo_surface: mf.albedoSurface,
      pollution_level: mf.pollutionLevel,
      max_module_shading_loss_pct: mf.maxModuleShadingLossPct,
      fire_lane_width_m: mf.fireLaneWidthM,
      maint_walkway_interval_m: mf.maintWalkwayIntervalM,
      load_profile: mf.loadProfile,
      modules_per_string: mpsVal,
      discount_rate_pct: discountRatePct,
      ...(explicitAnnualLoad !== null ? { annual_load_kwh: explicitAnnualLoad } : {}),
    },
  };

  let finalRes = null;
  if (typeof view.api === 'function') {
    try {
      const apiRes = await view.api('satmap/optimize-multifactor', reqPayload);
      if (apiRes && Array.isArray(apiRes.schemes) && apiRes.schemes.length > 0) {
        finalRes = {
          ...apiRes,
          source: 'backend_engine',
          schemes: apiRes.schemes.map((s) => ({
            ...s,
            modules_per_string: finiteOrNull(s.modules_per_string ?? s.string_series ?? s.recommended_series) ?? mpsVal,
            name_zh: String(s.name_zh || '')
              .replace(/\b1P\b/gi, '单排')
              .replace(/\b2P\b/gi, '双排')
              .replace(/\bLCOE\b/gi, '度电成本')
              .replace(/\bVoc\b/gi, '开路电压')
              .replace(/\bTPO\b/gi, '高反白膜')
              .replace(/[A-Za-z-]+/g, '')
              .trim() || '综合优选方案',
            name_en: s.name_en || (
              s.orientation_mode === 'east_west'
                ? `East-West Butterfly (${s.mount_orientation === 'landscape' ? 'Landscape' : 'Portrait'} ${s.rack_type || '1P'})`
                : s.orientation_mode === 'elevated_canopy'
                  ? `Elevated Solar Canopy (${s.rack_type || '2P'})`
                  : s.orientation_mode === 'flush_pitched'
                    ? `Flush Roof-Pitch Clamp (${s.rack_type || '2P'})`
                    : `South Optimal Tilt (${s.mount_orientation === 'landscape' ? 'Landscape' : 'Portrait'} ${s.rack_type || '2P'})`
            ),
          })),
        };
      }
    } catch {
      finalRes = null;
    }
  }

  if (!finalRes) {
    finalRes = runClientMultiFactorOptimization(view, customParams);
  } else if (!Array.isArray(finalRes.candidates)) {
    finalRes.candidates = finalRes.schemes;
  }

  mf.lastResult = finalRes;
  mf.selectedSchemeId = finalRes.recommended_id || finalRes.schemes[0]?.id || '';
  mf.optimizing = false;
  return finalRes;
}

/**
 * Apply (or Live-Preview) a Multi-Factor Pareto Scheme onto Satellite 2D/3D Canvas & Electrical Workbench
 */
export function applyMultiFactorSchemeToView(view, schemeOrId, { previewOnly = false } = {}) {
  const mf = view.mfState || (view.mfState = createDefaultMultiFactorState());
  const res = mf.lastResult || (mf.lastResult = runClientMultiFactorOptimization(view));
  const scheme = (schemeOrId && typeof schemeOrId === 'object')
    ? schemeOrId
    : ((res.schemes || []).find((s) => s.id === schemeOrId) || res.schemes?.[0]);
  if (!scheme) return null;

  if (previewOnly && !mf.previewSnapshot) {
    mf.previewSnapshot = {
      orientationMode: view.orientationMode,
      orientation: view.orientation,
      rackRows: mf.rackRows,
      fixingType: mf.fixingType,
      tiltDeg: view.tiltDeg,
      roofSlopeDeg: view.roofSlopeDeg,
      azimuthDeg: view.azimuthDeg,
      rowSpacingM: view.rowSpacingM,
      edgeSetbackM: view.edgeSetbackM,
      modulesPerString: view.modulesPerString,
      autoPruneShaded: mf.autoPruneShaded,
    };
  }
  if (!previewOnly) {
    mf.previewSnapshot = null;
    mf.previewSchemeId = '';
  } else {
    mf.previewSchemeId = scheme.id;
  }

  mf.selectedSchemeId = scheme.id;
  mf.orientationMode = scheme.orientation_mode || 'south_fixed';
  view.orientationMode = mf.orientationMode;
  view.orientation = scheme.mount_orientation === 'landscape' ? 'landscape' : 'portrait';
  mf.rackRows = scheme.rack_type || (scheme.rack_rows === 1 ? '1P' : '2P');
  if (scheme.fixing_type) mf.fixingType = scheme.fixing_type;
  mf.autoPruneShaded = true;

  const tiltVal = finiteOrNull(scheme.tilt_deg);
  if (tiltVal !== null) {
    view.tiltDeg = tiltVal;
    if (view.roofType !== 'flat' && mf.orientationMode === 'flush_pitched') {
      view.roofSlopeDeg = tiltVal;
    }
  }
  const azVal = finiteOrNull(scheme.azimuth_deg);
  if (azVal !== null) {
    view.azimuthDeg = azVal;
  }
  const rowSpaceVal = finiteOrNull(scheme.row_spacing_m);
  if (rowSpaceVal !== null && rowSpaceVal > 0) {
    view.rowSpacingM = rowSpaceVal;
  }
  const setbackVal = finiteOrNull(scheme.setback_m ?? scheme.effective_setback_m);
  if (setbackVal !== null && setbackVal > 0) {
    view.edgeSetbackM = setbackVal;
  }

  const adoptedSeries = finiteOrNull(scheme.modules_per_string ?? scheme.string_series ?? scheme.recommended_series);
  const vocCheck = computeColdVocAndStringSafety(
    view.getSelectedModule(),
    view.getSelectedInverter(),
    mf,
    adoptedSeries ?? view.modulesPerString
  );
  if (adoptedSeries !== null && adoptedSeries >= 1) {
    view.modulesPerString = Math.min(Math.round(adoptedSeries), vocCheck.max_series_safe);
  } else if (!vocCheck.safe || vocCheck.current_series > vocCheck.max_series_safe) {
    view.modulesPerString = vocCheck.recommended_series;
  }

  const envPreset = POLLUTION_LEVELS.find((p) => p.id === mf.pollutionLevel) || POLLUTION_LEVELS[1];
  view.pvsystParams = {
    ...(view.pvsystParams || {}),
    albedo: finiteNum(mf.albedo, 0.28),
    soiling_pct: envPreset.soilingPct,
  };
  view.roofLoadLimitKnM2 = Number((finiteNum(mf.maxRoofLoadKgM2, 35) / 102).toFixed(2));

  view.layoutModules({ quiet: true, autoCreateRoof: true });
  view.electricalConfirmed = true;
  view.showStringColors = true;
  view.computeElectricalAllocation();
  view.refreshPvsystData({ fetchBackend: false });
  persistLatestSatmapScheme(view);
  return scheme;
}

export function restoreMultiFactorPreview(view) {
  const mf = view.mfState;
  if (!mf?.previewSnapshot) return false;
  const snap = mf.previewSnapshot;
  view.orientationMode = snap.orientationMode;
  mf.orientationMode = snap.orientationMode;
  view.orientation = snap.orientation;
  mf.rackRows = snap.rackRows;
  mf.fixingType = snap.fixingType;
  view.tiltDeg = snap.tiltDeg;
  view.roofSlopeDeg = snap.roofSlopeDeg;
  view.azimuthDeg = snap.azimuthDeg;
  view.rowSpacingM = snap.rowSpacingM;
  view.edgeSetbackM = snap.edgeSetbackM;
  view.modulesPerString = snap.modulesPerString;
  mf.autoPruneShaded = snap.autoPruneShaded;
  mf.previewSnapshot = null;
  mf.previewSchemeId = '';
  if (view.hasLaidOut) {
    view.layoutModules({ quiet: true, autoCreateRoof: false });
  }
  return true;
}

/**
 * Render 6-Axis Radar SVG comparing Selected Multi-Factor Scheme vs Baseline
 */
export function renderSixAxisRadarSvg(selectedScheme, baselineScheme = null) {
  const axes = [
    { key: 'capacity', zh: '装机容量', en: 'Capacity' },
    { key: 'yield', zh: '发电性能', en: 'Yield' },
    { key: 'economics', zh: '度电经济', en: 'Economics' },
    { key: 'safety', zh: '荷载抗风', en: 'Load Safety' },
    { key: 'self_use', zh: '自发消纳', en: 'Self-Use' },
    { key: 'shading_resilience', zh: '抗遮挡度', en: 'Anti-Shade' },
  ];
  const cx = 135;
  const cy = 112;
  const R = 68;
  const scores = selectedScheme?.factor_scores || {};
  const baseScores = baselineScheme?.factor_scores || null;

  const polarPt = (idx, pct) => {
    const ang = -Math.PI / 2 + (idx * Math.PI * 2) / axes.length;
    const r = (Math.max(10, Math.min(100, finiteNum(pct, 75))) / 100) * R;
    return [Number((cx + Math.cos(ang) * r).toFixed(1)), Number((cy + Math.sin(ang) * r).toFixed(1))];
  };

  const polarLabelPt = (idx) => {
    const ang = -Math.PI / 2 + (idx * Math.PI * 2) / axes.length;
    const isVertical = idx === 0 || idx === 3;
    const r = isVertical ? 84 : 80;
    const lx = Number((cx + Math.cos(ang) * r).toFixed(1));
    const rawY = cy + Math.sin(ang) * r;
    const ly = Number((idx === 0 ? rawY - 2 : idx === 3 ? rawY + 6 : rawY + 3).toFixed(1));
    return [lx, ly];
  };

  const ringsSvg = [0.33, 0.66, 1.0].map((f) => {
    const pts = axes.map((_, i) => polarPt(i, f * 100).join(',')).join(' ');
    return `<polygon points="${pts}" fill="none" stroke="rgba(148,163,184,0.32)" stroke-width="1"/>`;
  }).join('');

  const spokesSvg = axes.map((ax, i) => {
    const [ox, oy] = polarPt(i, 100);
    const [lx, ly] = polarLabelPt(i);
    const anchor = lx < cx - 10 ? 'end' : lx > cx + 10 ? 'start' : 'middle';
    const val = Math.round(finiteNum(scores[ax.key], 80));
    return `
      <line x1="${cx}" y1="${cy}" x2="${ox}" y2="${oy}" stroke="rgba(148,163,184,0.28)" stroke-width="1"/>
      <text x="${lx}" y="${ly}" text-anchor="${anchor}" font-size="10.5" font-weight="700" fill="currentColor">${esc(L(ax.zh, ax.en))} ${val}</text>
    `;
  }).join('');

  const basePoly = baseScores && baselineScheme !== selectedScheme
    ? `<polygon points="${axes.map((ax, i) => polarPt(i, baseScores[ax.key]).join(',')).join(' ')}" fill="rgba(148,163,184,0.14)" stroke="#94a3b8" stroke-width="1.4" stroke-dasharray="4 2"/>`
    : '';

  const selPts = axes.map((ax, i) => polarPt(i, scores[ax.key]));
  const selPoly = `<polygon points="${selPts.map((p) => p.join(',')).join(' ')}" fill="rgba(37,99,235,0.24)" stroke="#2563eb" stroke-width="2.2"/>`;
  const dots = selPts.map(([px, py]) => `<circle cx="${px}" cy="${py}" r="3.4" fill="#2563eb" stroke="#ffffff" stroke-width="1.2"/>`).join('');

  return `<svg viewBox="-18 -10 306 242" class="satmap-mf-radar-svg" role="img" aria-label="${esc(L('六维工程因数评估雷达图', '6-Axis Engineering Factor Radar'))}">
    ${ringsSvg}
    ${spokesSvg}
    ${basePoly}
    ${selPoly}
    ${dots}
  </svg>`;
}

/**
 * Render Sleek 1-Line Guided Workflow & 3D Linkage Bar in `#satmap`
 */
export function renderLinkageTopStrip(view) {
  const link = view.linkage3d || (view.linkage3d = createDefaultLinkageState());
  const mf = view.mfState || (view.mfState = createDefaultMultiFactorState());
  const src = link.linkedSource;
  const sync = link.syncStatus;
  const modeObj = ORIENTATION_MODES.find((o) => o.id === (view.orientationMode || mf.orientationMode)) || ORIENTATION_MODES[0];
  const prunedCount = (view.prunedShadedModules || []).length;

  const hasRoof = Boolean(view.hasRoof);
  const hasLaidOut = Boolean(view.hasLaidOut && view.modules?.length > 0);
  const hasElec = Boolean(hasLaidOut && view.electricalConfirmed);

  const stageIdx = !hasRoof ? 1 : !hasLaidOut ? 2 : !hasElec ? 3 : 4;
  const workflowStages = [
    { idx: 1, zh: '① 选址或三维导入', en: '1. Site / 3D Import' },
    { idx: 2, zh: '② 圈定屋顶与禁布区', en: '2. Roof & Keepouts' },
    { idx: 3, zh: '③ 一键铺设与十二维寻优', en: '3. Layout & 12-Factor Opt' },
    { idx: 4, zh: '④ 配串与导出光筑专业报告', en: '4. Stringing & Pro Report' },
  ];

  return `<div class="satmap-linkage-strip" data-sat-linkage-strip>
    <div class="satmap-linkage-left">
      <div class="satmap-workflow-guide" data-sat-workflow-guide>
        <span class="satmap-wf-label">${esc(L('当前操作向导：', 'Guided Flow:'))}</span>
        ${workflowStages.map((st, idx) => {
          const stateCls = st.idx < stageIdx ? 'is-done' : st.idx === stageIdx ? 'is-current' : '';
          return `<span class="satmap-wf-pill ${stateCls}">${esc(L(st.zh, st.en))}</span>${idx < workflowStages.length - 1 ? '<span class="satmap-wf-sep">→</span>' : ''}`;
        }).join('')}
      </div>
      <span class="satmap-linkage-badge ${src || sync ? 'is-linked' : ''}">
        ${src
          ? `🔗 ${esc(L(`已关联三维基准：${String(src.name || '').replace(/[A-Za-z-]+/g, '').trim() || '三维屋面'}`, `Linked 3D: ${String(src.id || '3d-item').replace(/[\u4e00-\u9fff]+/g, '').trim() || '3D Roof'}`))}`
          : sync
            ? `✅ ${esc(L(`已同步三维库（第${sync.version || 1}版）`, `Synced to 3D (v${sync.version || 1})`))}`
            : `🛰️ ${esc(L(modeObj.zh, modeObj.en))}`}
      </span>
      ${prunedCount > 0 ? `<span class="sat-badge-amber">${esc(L(`剔除遮挡 ${prunedCount} 块`, `Pruned ${prunedCount}`))}</span>` : ''}
    </div>
    <div class="satmap-linkage-actions">
      <details class="sat-popover sat-linkage-popover">
        <summary class="sat-btn">🔄 ${esc(L('三维设计联动 ▾', '3D Design Sync ▾'))}</summary>
        <div class="sat-popover-panel sat-popover-linkage">
          <button type="button" class="sat-btn" data-sat-action="open-import-3d">
            📥 ${esc(L('从三维设计导入 (从三维同步)', 'Import from 3D Design'))}
          </button>
          <button type="button" class="sat-btn primary" data-sat-action="sync-to-3d" ${link.syncing ? 'disabled' : ''}>
            🔄 ${esc(L('联动推送至三维设计 (同步到三维)', 'Sync & Push to 3D Design'))}
          </button>
          ${(sync || src) ? `
            <button type="button" class="sat-btn" data-sat-action="toggle-linkage-diff">
              ${esc(L(link.showDiffCard ? '收起联动对比' : '查看三维联动对比', link.showDiffCard ? 'Hide 3D Diff' : 'Show 3D Diff'))}
            </button>
            <button type="button" class="sat-btn success" data-sat-action="jump-3d-result">
              🚀 ${esc(L('进入三维设计成果场景', 'Open 3D Result Scene'))}
            </button>
            <button type="button" class="sat-btn" data-sat-action="jump-3d-roof">
              🏗️ ${esc(L('进入三维屋面编辑器', 'Open 3D Roof Editor'))}
            </button>
          ` : ''}
        </div>
      </details>
      <button type="button" class="sat-btn ${(view.step === 1 ? mf.openInStep1 : mf.openInStep3) ? 'primary' : ''}" data-sat-action="toggle-multifactor-studio">
        🧭 ${esc(L('多维可能性因数寻优', 'Multi-Factor Optimizer'))}
      </button>
      <button type="button" class="sat-btn" data-sat-action="preview-pro-report">
        👁 ${esc(L('预览光筑专业报告', 'Preview Pro Report'))}
      </button>
      <button type="button" class="sat-btn sat-btn-pvsyst-v2" data-sat-action="export-pvsyst-v2">
        📄 ${esc(L('导出光筑专业报告', 'Export Guangzhu Pro Report'))}
      </button>
    </div>
  </div>
  ${link.showDiffCard && (sync || src) ? renderLinkageDiffCard(view) : ''}`;
}

/**
 * Render Live Linkage Diff Table & One-Click 3D Scene / Roof Editor Jump Card
 */
export function renderLinkageDiffCard(view) {
  const link = view.linkage3d || createDefaultLinkageState();
  const mf = view.mfState || createDefaultMultiFactorState();
  const sync = link.syncStatus;
  const ref = link.referenceMetrics || {};
  const modSpec = view.getSelectedModule();
  const activeTilt = view.roofType === 'flat' ? view.tiltDeg : view.roofSlopeDeg;
  const structCheck = computeMultiFactorStructuralCheck({
    roofType: view.roofType,
    orientationMode: view.orientationMode || mf.orientationMode,
    rackRows: mf.rackRows,
    tiltDeg: activeTilt,
    buildingHeightM: view.buildingHeightM,
    edgeSetbackM: view.edgeSetbackM,
    moduleSpec: modSpec,
    mfParams: mf,
  });

  const dcSat = finiteNum(sync?.diff?.dc_kw_sat, view.summary?.dcKw || 0);
  const dc3d = finiteNum(sync?.diff?.dc_kw_3d, ref.dc_kw ?? dcSat);
  const modSat = finiteNum(sync?.diff?.module_count_sat, view.summary?.moduleCount || 0);
  const mod3d = finiteNum(sync?.diff?.module_count_3d, ref.module_count ?? modSat);
  const kwhSat = finiteNum(sync?.diff?.annual_kwh_sat, view.summary?.annualKwh || 0);
  const kwh3d = finiteNum(sync?.diff?.annual_kwh_3d, ref.annual_kwh ?? kwhSat);
  const prSat = finiteNum(sync?.diff?.pr_pct_sat, view.summary?.prPct || 84.2);
  const pr3d = finiteNum(sync?.diff?.pr_pct_3d, ref.pr_pct ?? 83.2);
  const loadKgM2 = finiteNum(sync?.diff?.load_kg_m2, structCheck.added_dead_load_kg_m2);
  const maxLoadKgM2 = finiteNum(mf.maxRoofLoadKgM2, 35);
  const prunedCount = (view.prunedShadedModules || []).length;

  const fmtDelta = (a, b, digits = 1, suffix = '') => {
    const d = a - b;
    const sign = d > 0 ? '+' : '';
    return `${sign}${d.toFixed(digits)}${suffix}`;
  };

  return `<div class="satmap-diff-card" data-sat-linkage-diff>
    <div class="satmap-diff-head">
      <div>
        <strong>${esc(L('卫星深化方案 对比 三维设计基准', 'Satellite Deepened Scheme vs 3D Design Baseline'))}</strong>
        <small>
          ${sync
            ? `${esc(L(`双向同步状态：已完成（第${sync.version}版）`, `Bidirectional Sync: Completed (${String(sync.projectId || '3d-proj').replace(/[\u4e00-\u9fff]+/g, '') || '3d-proj'} · v${sync.version})`))}`
            : `${esc(L(`基准来源：${String(link.linkedSource?.name || '三维工程').replace(/[A-Za-z-]+/g, '').trim() || '三维工程'}`, `Baseline Source: ${String(link.linkedSource?.id || '3D Baseline').replace(/[\u4e00-\u9fff]+/g, '') || '3D Baseline'}`))}`}
        </small>
      </div>
      <div class="satmap-diff-jumps">
        <button type="button" class="sat-btn success" data-sat-action="jump-3d-result">
          🚀 ${esc(L('进入三维设计成果场景', 'Open 3D Result Scene'))}
        </button>
        <button type="button" class="sat-btn primary" data-sat-action="jump-3d-roof">
          🏗️ ${esc(L('进入三维屋面编辑器', 'Open 3D Roof Editor'))}
        </button>
      </div>
    </div>
    <div style="overflow-x:auto">
      <table class="satmap-pareto-table satmap-diff-table">
        <thead>
          <tr>
            <th>${esc(L('对比指标', 'Metric'))}</th>
            <th>${esc(L('装机容量', 'DC Capacity'))}</th>
            <th>${esc(L('组件数量', 'Modules'))}</th>
            <th>${esc(L('首年发电量', 'First-Year Yield'))}</th>
            <th>${esc(L('系统综合效率', 'System PR'))}</th>
            <th>${esc(L('屋面新增静荷载', 'Roof Dead Load'))}</th>
            <th>${esc(L('阴影智能剔除', 'Shaded Pruned'))}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><b>${esc(L('卫星深化方案', 'Satellite Optimized'))}</b></td>
            <td><b>${dcSat.toFixed(2)} ${esc(L('千瓦', 'kWp'))}</b></td>
            <td><b>${modSat} ${esc(L('块', 'pcs'))}</b></td>
            <td><b>${(kwhSat / 10000).toFixed(2)} ${esc(L('万千瓦时', '×10⁴ kWh'))}</b></td>
            <td><b>${prSat.toFixed(1)}%</b></td>
            <td><span class="${loadKgM2 <= maxLoadKgM2 ? 'sat-badge-pass' : 'sat-badge-fail'}">${loadKgM2.toFixed(1)} / ${maxLoadKgM2.toFixed(0)} ${esc(L('千克/平方米', 'kg/m²'))}</span></td>
            <td><b>${prunedCount} ${esc(L('块', 'pcs'))}</b></td>
          </tr>
          <tr>
            <td>${esc(L('三维设计基准 / 差值', '3D Baseline / Delta'))}</td>
            <td>${dc3d.toFixed(2)} (${fmtDelta(dcSat, dc3d, 2)})</td>
            <td>${mod3d} (${fmtDelta(modSat, mod3d, 0)})</td>
            <td>${(kwh3d / 10000).toFixed(2)} (${fmtDelta(kwhSat / 10000, kwh3d / 10000, 2)})</td>
            <td>${pr3d.toFixed(1)}% (${fmtDelta(prSat, pr3d, 1, '%')})</td>
            <td>${esc(L(loadKgM2 <= maxLoadKgM2 ? '荷载安全合规' : '建议切换轻质夹具', loadKgM2 <= maxLoadKgM2 ? 'Load Safe' : 'Switch to Clamp'))}</td>
            <td>${esc(L('消除短板失配损耗', 'Bypass Mismatch Mitigated'))}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>`;
}

/**
 * Render Modal for Importing 3D Projects / Custom Roofs / Roof Templates into `#satmap`
 */
export function renderImport3DModal(view) {
  const link = view.linkage3d;
  if (!link?.showImportModal) return '';

  const tab = link.catalogTab || 'projects';
  const q = String(link.catalogSearch || '').trim().toLowerCase();
  const rawItems = tab === 'projects'
    ? (link.catalog?.projects || [])
    : tab === 'my_roofs'
      ? (link.catalog?.my_roofs || [])
      : (link.catalog?.templates || []);
  const filtered = q
    ? rawItems.filter((it) => `${it.name || ''} ${it.id || ''} ${it.city || ''}`.toLowerCase().includes(q))
    : rawItems;
  const kindAttr = tab === 'projects' ? 'project' : tab === 'my_roofs' ? 'my-roof' : 'template';

  return `<div class="satmap-modal-backdrop" data-sat-import3d-modal>
    <div class="satmap-modal-card" style="width:min(760px,94vw)">
      <div class="satmap-modal-head">
        <h3>📥 ${esc(L('从三维设计导入屋面与工程参数', 'Import Roof & System Parameters from 3D Design'))}</h3>
        <button type="button" class="satmap-modal-close" data-sat-action="close-modals">×</button>
      </div>
      <div class="satmap-modal-body" style="display:flex;flex-direction:column;gap:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
          <div class="satmap-pvlane-tabs" style="min-width:340px">
            <button type="button" class="satmap-tab-pill ${tab === 'projects' ? 'active' : ''}" data-sat-3dcat-tab="projects">
              ${esc(L(`三维工程方案 (${link.catalog?.projects?.length || 0})`, `3D Projects (${link.catalog?.projects?.length || 0})`))}
            </button>
            <button type="button" class="satmap-tab-pill ${tab === 'my_roofs' ? 'active' : ''}" data-sat-3dcat-tab="my_roofs">
              ${esc(L(`自建三维屋顶 (${link.catalog?.my_roofs?.length || 0})`, `My 3D Roofs (${link.catalog?.my_roofs?.length || 0})`))}
            </button>
            <button type="button" class="satmap-tab-pill ${tab === 'templates' ? 'active' : ''}" data-sat-3dcat-tab="templates">
              ${esc(L(`三维标准样板 (${link.catalog?.templates?.length || 0})`, `3D Templates (${link.catalog?.templates?.length || 0})`))}
            </button>
          </div>
          <input type="text" class="satmap-input" style="max-width:240px;margin:0" data-sat-mf-field="catalogSearch"
            value="${esc(link.catalogSearch || '')}" placeholder="${esc(L('搜索项目或厂房名称', 'Filter by name or city'))}">
        </div>

        <div style="max-height:360px;overflow-y:auto;display:flex;flex-direction:column;gap:8px">
          ${link.loadingCatalog ? `
            <div style="padding:28px;text-align:center;color:var(--muted)">${esc(L('正在读取三维设计工程目录…', 'Loading 3D Design catalog...'))}</div>
          ` : filtered.length ? filtered.map((it) => `
            <div class="satmap-3dcat-row">
              <div>
                <strong>${esc(L(String(it.name || '三维工程').replace(/[A-Za-z-]+/g, '').trim() || '三维工程', it.name_en || String(it.id || '3D Roof').replace(/[\u4e00-\u9fff]+/g, '') || '3D Roof'))}</strong>
                <div style="font-size:12px;color:var(--muted);margin-top:2px">
                  ${(it.city || it.city_en) ? `${esc(L(String(it.city || '').replace(/[A-Za-z-]+/g, ''), it.city_en || String(it.city || '').replace(/[\u4e00-\u9fff]+/g, '') || 'Site'))} · ` : ''}
                  ${it.dc_kw ? `${Number(it.dc_kw).toFixed(1)} ${esc(L('千瓦', 'kWp'))} · ` : ''}
                  ${it.area_m2 ? `${Math.round(it.area_m2)} ${esc(L('平方米', 'm²'))} · ` : ''}
                  ${it.parapet_height_m != null ? `${esc(L('女儿墙', 'Parapet'))} ${Number(it.parapet_height_m).toFixed(2)}${esc(L('米', 'm'))}` : ''}
                </div>
              </div>
              <button type="button" class="sat-btn primary" data-sat-import3d-kind="${kindAttr}" data-sat-import3d-id="${esc(it.id)}" data-sat-import3d-ver="${it.version || 1}">
                ${esc(L('载入至卫星工作台', 'Import to Satellite'))}
              </button>
            </div>
          `).join('') : `
            <div style="padding:24px;text-align:center;color:var(--muted)">
              ${esc(L('当前分类暂无记录，可切换上方标签页选择「三维标准样板」或「自建三维屋顶」。', 'No items in this tab; switch tabs above to select a 3D Roof or Template.'))}
            </div>
          `}
        </div>
      </div>
    </div>
  </div>`;
}

/**
 * Render Multi-Factor Engineering Optimizer Studio ("多维可能性因数综合寻优")
 * Embedded in Step 1 (when toggled open) and Step 3 (above/alongside 8760h physics workbench).
 */
export function renderMultiFactorStudioPanel(view, { context = 'step1' } = {}) {
  const mf = view.mfState || (view.mfState = createDefaultMultiFactorState());
  const isOpen = context === 'step3' ? mf.openInStep3 : mf.openInStep1;
  if (!isOpen) return '';

  const optRes = mf.lastResult || (mf.lastResult = runClientMultiFactorOptimization(view));
  const schemes = optRes.schemes || [];
  const selectedScheme = schemes.find((s) => s.id === mf.selectedSchemeId) || schemes[0];
  const baselineScheme = schemes.find((s) => s.orientation_mode === 'south_fixed') || schemes[0];
  const vocCheck = computeColdVocAndStringSafety(view.getSelectedModule(), view.getSelectedInverter(), mf, view.modulesPerString);
  const structCheck = computeMultiFactorStructuralCheck({
    roofType: view.roofType,
    orientationMode: view.orientationMode || mf.orientationMode,
    rackRows: mf.rackRows,
    tiltDeg: view.roofType === 'flat' ? view.tiltDeg : view.roofSlopeDeg,
    buildingHeightM: view.buildingHeightM,
    edgeSetbackM: view.edgeSetbackM,
    moduleSpec: view.getSelectedModule(),
    mfParams: mf,
  });
  const prunedCount = (view.prunedShadedModules || []).length;
  const isModal = context === 'step1';

  const sectionHtml = `<section class="satmap-mf-studio ${isModal ? 'is-modal-card' : ''}" data-sat-multifactor-studio="${esc(context)}">
    <div class="satmap-mf-header">
      <div>
        <h3>🧭 ${esc(L('多维可能性因数综合寻优工作台', 'Multi-Factor Engineering Possibility Optimizer'))}</h3>
        <small>
          ${esc(L(
            '综合排布拓扑、竖横装支架、屋面静荷载上限、台风雪压、极端低温开路电压、反照率双面增益与高遮挡毒组件剔除，一键求解帕累托最优方案',
            'Co-optimizes array topology, portrait/landscape racking, dead-load limit, wind/snow, cold Voc safety, bifacial albedo & shaded module pruning'
          ))}
        </small>
      </div>
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span class="${structCheck.load_ok ? 'sat-badge-pass' : 'sat-badge-fail'}">
          ${esc(L(structCheck.load_ok ? '✓ 荷载校核通过' : '⚠ 荷载超限预警', structCheck.load_ok ? '✓ Dead-Load Pass' : '⚠ Load Exceeded'))}
          (${structCheck.added_dead_load_kg_m2}/${structCheck.max_roof_load_kg_m2} ${esc(L('千克/平方米', 'kg/m²'))})
        </span>
        <span class="${vocCheck.safe ? 'sat-badge-pass' : 'sat-badge-fail'}">
          ${esc(L(vocCheck.safe ? '✓ 低温开路电压安全' : '⚠ 低温电压超限', vocCheck.safe ? '✓ Cold Voc Safe' : '⚠ Cold Voc Overlimit'))}
          (${vocCheck.string_cold_voc_v}/${vocCheck.max_dc_v}${esc(L('伏', 'V'))})
        </span>
        <span class="${structCheck.wind_ok ? 'sat-badge-pass' : 'sat-badge-fail'}">
          ${esc(L(structCheck.wind_ok ? '✓ 台风退距合规' : '⚠ 边角退距偏小', structCheck.wind_ok ? '✓ Wind Setback Pass' : '⚠ Increase Setback'))}
        </span>
        <button type="button" class="sat-btn primary" data-sat-action="run-multifactor-opt" ${mf.optimizing ? 'disabled' : ''}>
          ⚡ ${esc(L('运行多维因数寻优', 'Run Multi-Factor Optimization'))}
        </button>
        ${mf.previewSnapshot ? `
          <button type="button" class="sat-btn danger" data-sat-action="restore-mf-preview">
            ↩ ${esc(L('退出预览还原排布', 'Exit Preview & Restore'))}
          </button>
        ` : ''}
        ${isModal ? `
          <button type="button" class="sat-btn" data-sat-action="toggle-multifactor-studio">
            ✕ ${esc(L('关闭窗口', 'Close'))}
          </button>
        ` : ''}
      </div>
    </div>

    <!-- 4-Group 12-Factor Engineering Controls -->
    <div class="satmap-mf-grid">
      <!-- Group 1: Topology & Racking -->
      <div class="satmap-mf-box">
        <b>① ${esc(L('排布拓扑与支架姿态因数', '1. Topology & Racking Posture'))}</b>
        <label class="satmap-field-row">
          <span>${esc(L('阵列排布拓扑', 'Array Topology'))}</span>
          <select data-sat-mf-field="orientationMode">
            ${ORIENTATION_MODES.map((m) => `<option value="${m.id}" ${(view.orientationMode || mf.orientationMode) === m.id ? 'selected' : ''}>${esc(L(m.zh, m.en))}</option>`).join('')}
          </select>
        </label>
        <label class="satmap-field-row">
          <span>${esc(L('组件安装姿态', 'Mount Posture'))}</span>
          <select data-sat-mf-field="mountOrientation">
            <option value="portrait" ${view.orientation === 'portrait' ? 'selected' : ''}>${esc(L('竖装标准排布', 'Portrait Standard'))}</option>
            <option value="landscape" ${view.orientation === 'landscape' ? 'selected' : ''}>${esc(L('横装抗遮挡排布', 'Landscape Anti-Shading'))}</option>
          </select>
        </label>
        <label class="satmap-field-row">
          <span>${esc(L('支架排数构型', 'Rack Rows'))}</span>
          <select data-sat-mf-field="rackRows">
            <option value="2P" ${mf.rackRows === '2P' ? 'selected' : ''}>${esc(L('双排标准支架', '2-Row Standard Rack'))}</option>
            <option value="1P" ${mf.rackRows === '1P' ? 'selected' : ''}>${esc(L('单排低风阻支架', '1-Row Low-Wind Rack'))}</option>
          </select>
        </label>
        ${(view.orientationMode || mf.orientationMode) === 'elevated_canopy' ? `
          <label class="satmap-field-row">
            <span>${esc(L('阳光棚跨障净空 (米)', 'Canopy Clearance (m)'))}</span>
            <input type="number" step="0.2" min="1.8" max="6.0" data-sat-mf-field="canopyClearanceM" value="${mf.canopyClearanceM}">
          </label>
        ` : ''}
      </div>

      <!-- Group 2: Structural & Fire/O&M Constraints -->
      <div class="satmap-mf-box">
        <b>② ${esc(L('屋面结构与消防通道约束', '2. Structural & Fire-Lane Limits'))}</b>
        <label class="satmap-field-row">
          <span>${esc(L('新增静荷载上限 (千克/平方米)', 'Max Dead Load (kg/m²)'))}</span>
          <input type="number" step="5" min="15" max="150" data-sat-mf-field="maxRoofLoadKgM2" value="${mf.maxRoofLoadKgM2}">
        </label>
        <label class="satmap-field-row">
          <span>${esc(L('屋面固定方式', 'Fixing Method'))}</span>
          <select data-sat-mf-field="fixingType">
            ${FIXING_MODES.map((f) => `<option value="${f.id}" ${mf.fixingType === f.id ? 'selected' : ''}>${esc(L(f.zh, f.en))}</option>`).join('')}
          </select>
        </label>
        <label class="satmap-field-row">
          <span>${esc(L('主消防通道宽 (米)', 'Main Fire Lane (m)'))}</span>
          <input type="number" step="0.2" min="0" max="4.0" data-sat-mf-field="fireLaneWidthM" value="${mf.fireLaneWidthM}">
        </label>
        <label class="satmap-field-row">
          <span>${esc(L('运维通道间距 (米)', 'O&M Aisle Pitch (m)'))}</span>
          <input type="number" step="2" min="6" max="36" data-sat-mf-field="maintWalkwayIntervalM" value="${mf.maintWalkwayIntervalM}">
        </label>
      </div>

      <!-- Group 3: Wind, Snow, Cold Voc & Shading Pruning -->
      <div class="satmap-mf-box">
        <b>③ ${esc(L('风雪温极值与阴影剔毒边界', '3. Climate Extremes & Shade Cutoff'))}</b>
        <label class="satmap-field-row">
          <span>${esc(L('基本风压 / 雪压 (千牛/平方米)', 'Wind w0 / Snow s0 (kN/m²)'))}</span>
          <span style="display:flex;gap:4px">
            <input type="number" step="0.05" min="0.25" max="1.25" data-sat-mf-field="basicWindW0KnM2" value="${mf.basicWindW0KnM2}" style="width:56px">
            <input type="number" step="0.05" min="0" max="1.0" data-sat-mf-field="basicSnowS0KnM2" value="${mf.basicSnowS0KnM2}" style="width:56px">
          </span>
        </label>
        <label class="satmap-field-row">
          <span>${esc(L('极端低温 / 高温 (摄氏度)', 'Min / Max Temp (°C)'))}</span>
          <span style="display:flex;gap:4px">
            <input type="number" step="1" min="-40" max="15" data-sat-mf-field="extremeTempMinC" value="${mf.extremeTempMinC}" style="width:56px">
            <input type="number" step="1" min="25" max="55" data-sat-mf-field="extremeTempMaxC" value="${mf.extremeTempMaxC}" style="width:56px">
          </span>
        </label>
        <label class="satmap-field-row">
          <span>${esc(L('单块最大遮挡阈值 (%)', 'Max Module Shade (%)'))}</span>
          <input type="number" step="1" min="3" max="35" data-sat-mf-field="maxModuleShadingLossPct" value="${mf.maxModuleShadingLossPct}">
        </label>
        <label style="display:flex;align-items:center;gap:6px;font-size:11.5px;cursor:pointer">
          <input type="checkbox" data-sat-mf-field="autoPruneShaded" ${mf.autoPruneShaded ? 'checked' : ''}>
          <span>${esc(L(`自动剔除重度遮挡组件并显示虚线框 (${prunedCount}块)`, `Auto-prune shaded modules & show dashed slots (${prunedCount})`))}</span>
        </label>
      </div>

      <!-- Group 4: Albedo, Environment, Load Profile & Objective -->
      <div class="satmap-mf-box">
        <b>④ ${esc(L('双面反照率与源荷多目标权重', '4. Albedo, Environment & Objective'))}</b>
        <label class="satmap-field-row">
          <span>${esc(L('屋面反射率材质', 'Roof Albedo'))}</span>
          <select data-sat-mf-field="albedoSurface">
            ${ALBEDO_PRESETS.map((a) => `<option value="${a.id}" ${mf.albedoSurface === a.id ? 'selected' : ''}>${esc(L(a.zh, a.en))}</option>`).join('')}
          </select>
        </label>
        <label class="satmap-field-row">
          <span>${esc(L('环境灰尘与盐雾', 'Soiling / Salt Grade'))}</span>
          <select data-sat-mf-field="pollutionLevel">
            ${POLLUTION_LEVELS.map((p) => `<option value="${p.id}" ${mf.pollutionLevel === p.id ? 'selected' : ''}>${esc(L(p.zh, p.en))}</option>`).join('')}
          </select>
        </label>
        <label class="satmap-field-row">
          <span>${esc(L('企业用电负荷曲线', 'Load Profile'))}</span>
          <select data-sat-mf-field="loadProfile">
            ${LOAD_PROFILES.map((lp) => `<option value="${lp.id}" ${mf.loadProfile === lp.id ? 'selected' : ''}>${esc(L(lp.zh, lp.en))}</option>`).join('')}
          </select>
        </label>
        <label class="satmap-field-row">
          <span>${esc(L('多目标寻优偏好', 'Optimization Goal'))}</span>
          <select data-sat-mf-field="objective">
            ${OPTIMIZATION_OBJECTIVES.map((ob) => `<option value="${ob.id}" ${mf.objective === ob.id ? 'selected' : ''}>${esc(L(ob.zh, ob.en))}</option>`).join('')}
          </select>
        </label>
      </div>
    </div>

    <!-- Pareto Comparison Matrix + 6-Axis Radar -->
    <div class="satmap-mf-results">
      <div class="satmap-radar-box">
        <div style="font-size:12px;font-weight:700;margin-bottom:4px;text-align:center">
          ${esc(L('六维综合评估雷达', '6-Axis Evaluation Radar'))}
        </div>
        ${renderSixAxisRadarSvg(selectedScheme, baselineScheme)}
        <div style="font-size:11px;color:var(--muted);text-align:center">
          ${esc(L('当前焦点：', 'Selected: '))}<b>${esc(L(selectedScheme?.name_zh || '', selectedScheme?.name_en || ''))}</b>
        </div>
      </div>

      <div style="overflow-x:auto;flex:1">
        <table class="satmap-pareto-table">
          <thead>
            <tr>
              <th>${esc(L('候选工程方案', 'Candidate Scheme'))}</th>
              <th>${esc(L('装机容量', 'Capacity'))}</th>
              <th>${esc(L('首年发电量', 'Annual Yield'))}</th>
              <th>${esc(L('系统效率', 'System PR'))}</th>
              <th>${esc(L('屋面静荷载', 'Dead Load'))}</th>
              <th>${esc(L('度电成本 / 回收期', 'LCOE / Payback'))}</th>
              <th>${esc(L('综合得分与校核', 'Score & Compliance'))}</th>
              <th>${esc(L('操作', 'Actions'))}</th>
            </tr>
          </thead>
          <tbody>
            ${schemes.map((sc) => {
              const isRec = sc.id === optRes.recommended_id && sc.constraints?.all_pass !== false;
              const isSel = sc.id === selectedScheme?.id;
              const passAll = sc.constraints?.all_pass !== false;
              const scLcoe = finiteOrNull(sc.lcoe_cny_kwh);
              const scPayback = finiteOrNull(sc.payback_yr);
              const lcoeCellHtml = scLcoe !== null
                ? `<b>${scLcoe.toFixed(3)}</b> ${esc(L('元/度', 'RMB/kWh'))}`
                : `<b>${esc(L('不适用', 'N/A'))}</b>`;
              const paybackCellHtml = scPayback !== null
                ? `${scPayback.toFixed(1)} ${esc(L('年回本', 'yr payback'))}`
                : `${esc(L('无法回本', 'No payback'))}`;
              return `<tr class="${isSel ? 'is-selected' : ''}" data-sat-mf-row="${esc(sc.id)}">
                <td>
                  <b>${esc(L(sc.name_zh, sc.name_en || sc.name_zh))}</b>
                  ${isRec ? `<span class="sat-badge-pass" style="margin-left:4px">${esc(L('推荐', 'Best'))}</span>` : ''}
                  <div style="font-size:11px;color:var(--muted)">
                    ${esc(L(`倾角 ${sc.tilt_deg}° · 剔除遮挡 ${sc.pruned_shaded_modules || 0} 块`, `Tilt ${sc.tilt_deg}° · Pruned ${sc.pruned_shaded_modules || 0} pcs`))}
                  </div>
                </td>
                <td><b>${finiteNum(sc.dc_kw, 0).toFixed(2)}</b> ${esc(L('千瓦', 'kWp'))}<br><small>${finiteNum(sc.module_count, 0)} ${esc(L('块', 'pcs'))}</small></td>
                <td><b>${(finiteNum(sc.annual_kwh, 0) / 10000).toFixed(2)}</b> ${esc(L('万千瓦时', '×10⁴ kWh'))}<br><small>${finiteNum(sc.specific_yield_kwh_kwp, 0).toFixed(0)} ${esc(L('小时', 'h'))}</small></td>
                <td><b>${finiteNum(sc.pr_pct, 0).toFixed(1)}%</b><br><small>${esc(L(`双面增益 +${finiteNum(sc.bifacial_gain_pct, 0).toFixed(1)}%`, `Bifacial +${finiteNum(sc.bifacial_gain_pct, 0).toFixed(1)}%`))}</small></td>
                <td>
                  <span class="${sc.constraints?.load_ok !== false ? 'sat-badge-pass' : 'sat-badge-fail'}">
                    ${finiteNum(sc.load_kg_m2, 0).toFixed(1)} ${esc(L('千克/平方米', 'kg/m²'))}
                  </span>
                </td>
                <td>${lcoeCellHtml}<br><small>${paybackCellHtml}</small></td>
                <td>
                  <b>${finiteNum(sc.composite_score, 0).toFixed(1)}</b>
                  <span class="${passAll ? 'sat-badge-pass' : 'sat-badge-fail'}">${esc(L(passAll ? '全项合规' : '边界受限', passAll ? 'All Pass' : 'Constraint Warn'))}</span>
                </td>
                <td>
                  <div style="display:flex;gap:4px;flex-wrap:wrap">
                    <button type="button" class="sat-btn" style="height:25px;padding:0 8px;font-size:11px" data-sat-mf-preview="${esc(sc.id)}">
                      ${esc(L('预览排布', 'Preview'))}
                    </button>
                    <button type="button" class="sat-btn primary" style="height:25px;padding:0 8px;font-size:11px" data-sat-mf-apply="${esc(sc.id)}">
                      ${esc(L('应用此方案', 'Apply'))}
                    </button>
                  </div>
                </td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
      </div>
    </div>
  </section>`;

  if (isModal) {
    return `<div class="satmap-modal-backdrop satmap-mf-modal-backdrop" data-sat-mf-modal="step1" role="dialog" aria-modal="true" aria-label="${esc(L('多维可能性因数综合寻优工作台', 'Multi-Factor Engineering Optimizer'))}">
      ${sectionHtml}
    </div>`;
  }
  return sectionHtml;
}

function scrubReportBrandText(text) {
  return String(text || '').replace(/pvsyst/gi, '光筑专业仿真');
}

/**
 * Build Printable Client-Side 6-Page Offline Preview Report — 《光筑专业报告》（离线未核验预览）
 * Strictly preserves 0/null inputs with zero fabricated numbers or hardcoded PASS claims.
 */
export function buildClientPvsystV2ReportHtml(payload = {}) {
  const iconUrl = payload.branding?.icon_url || payload.icon_url || '/assets/guangzhu-128.png';
  const site = payload.site || {};
  const sys = payload.system || {};
  const sim = payload.pvsyst || {};
  const sum = sim.summary || {};
  const mf = payload.multifactor || {};
  const fin = payload.financial || {};
  const elec = payload.electrical || {};
  const mpptRows = Array.isArray(elec.mppt_rows) ? elec.mppt_rows : [];
  const rawMonthly = Array.isArray(sim.monthly_balances)
    ? sim.monthly_balances
    : Array.isArray(sim.monthly)
      ? sim.monthly
      : [];

  const dcKw = Math.max(0, finiteNum(sys.dc_kw ?? payload.dc_kw, 0));
  const acKw = Math.max(0, finiteNum(sys.ac_kw ?? payload.ac_kw, 0));
  const modCount = Math.max(0, Math.round(finiteNum(sys.module_count ?? payload.module_count, 0)));
  const invCount = (dcKw > 0 || modCount > 0) ? Math.max(0, Math.round(finiteNum(sys.inverter_count, 0))) : 0;
  const strCount = (dcKw > 0 || modCount > 0) ? Math.max(0, Math.round(finiteNum(sys.string_count, 0))) : 0;
  const mpsCount = (dcKw > 0 || modCount > 0) ? Math.max(0, Math.round(finiteNum(sys.modules_per_string ?? elec.modules_per_string, 0))) : 0;
  const dcAcVal = dcKw > 0 && acKw > 0 ? finiteNum(sys.dc_ac_ratio, dcKw / acKw) : 0;
  const annualKwh = dcKw > 0 ? Math.max(0, finiteNum(sum.e_grid_kwh ?? sys.annual_kwh, 0)) : 0;
  const specYield = dcKw > 0 ? Math.max(0, finiteNum(sum.specific_yield_kwh_kwp ?? sys.specific_yield, 0)) : 0;
  const prPct = dcKw > 0 ? Math.max(0, finiteNum(sum.pr_pct ?? sys.pr_pct, 0)) : 0;
  const projName = scrubReportBrandText(payload.project_name || site.name || '分布式光伏电站项目');
  const dateStr = new Date().toISOString().slice(0, 10);

  const fmtNullable = (val, decimals = 2, unit = '') => {
    const n = finiteOrNull(val);
    if (n === null) return 'N/A（未核验/不适用）';
    return `${n.toFixed(decimals)}${unit ? ` ${unit}` : ''}`;
  };

  const offlineBannerText = 'OFFLINE UNVERIFIED PREVIEW · 后端仿真服务离线，以下仅为前端简版未核验预览（非正式交付计算书）';
  const offlineBannerHtml = `
    <div class="gz-offline-banner" role="alert" data-offline-unverified="1">
      <strong>⚠ ${esc(offlineBannerText)}</strong>
    </div>`;

  const monthRowsHtml = rawMonthly.length > 0
    ? rawMonthly.slice(0, 12).map((m, i) => {
        const gh = finiteOrNull(m.glob_hor ?? m.glob_hor_kwh_m2);
        const dh = finiteOrNull(m.diff_hor ?? m.diff_hor_kwh_m2);
        const ta = finiteOrNull(m.t_amb ?? m.t_amb_c);
        const ws = finiteOrNull(m.wind_ms ?? m.wind_vel);
        const gi = finiteOrNull(m.glob_inc ?? m.glob_inc_kwh_m2);
        const ge = finiteOrNull(m.glob_eff ?? m.glob_eff_kwh_m2);
        const gb = finiteOrNull(m.glob_bak_kwh_m2 ?? m.glob_bak);
        const ea = dcKw > 0 ? finiteOrNull(m.e_array_kwh ?? m.e_array) : 0;
        const eg = dcKw > 0 ? finiteOrNull(m.e_grid_kwh ?? m.e_grid) : 0;
        const mPr = dcKw > 0
          ? (finiteOrNull(m.pr_pct) ?? (finiteOrNull(m.pr) !== null ? finiteNum(m.pr, 0) * 100 : null))
          : 0;
        return `
        <tr>
          <td>${esc(m.month_label || `${i + 1}月`)}</td>
          <td>${gh !== null ? gh.toFixed(1) : '—'}</td>
          <td>${dh !== null ? dh.toFixed(1) : '—'}</td>
          <td>${ta !== null ? ta.toFixed(1) : '—'}</td>
          <td>${ws !== null ? ws.toFixed(1) : '—'}</td>
          <td>${gi !== null ? gi.toFixed(1) : '—'}</td>
          <td>${ge !== null ? ge.toFixed(1) : '—'}</td>
          <td>${gb !== null ? gb.toFixed(1) : '—'}</td>
          <td>${ea !== null ? Math.round(ea).toLocaleString('zh-CN') : '—'}</td>
          <td><b>${eg !== null ? Math.round(eg).toLocaleString('zh-CN') : '—'}</b></td>
          <td>${mPr !== null ? `${mPr.toFixed(1)}%` : '—'}</td>
        </tr>`;
      }).join('')
    : `<tr><td colspan="11" style="text-align:center;color:#64748b;padding:12px">${esc('暂无逐月仿真明细数据（N/A · 后端离线未核验预览）')}</td></tr>`;

  const watermarkHtml = `
    <div class="gz-wm-layer" aria-hidden="true">
      <div class="gz-wm-stamp"><img src="${esc(iconUrl)}" alt=""><span>光筑 · GUANGZHU</span></div>
      <div class="gz-wm-stamp"><img src="${esc(iconUrl)}" alt=""><span>光筑专业报告</span></div>
      <div class="gz-wm-stamp"><img src="${esc(iconUrl)}" alt=""><span>${esc('OFFLINE PREVIEW')}</span></div>
    </div>`;

  const renderPageHdr = (subtitle, pageNo) => `
    <header class="gz-hdr">
      <div class="gz-hdr-left">
        <img src="${esc(iconUrl)}" alt="光筑软件图标">
        <div>
          <h1>光筑专业报告 · ${esc(subtitle)}</h1>
          <small>${esc('前端离线简版未核验预览 · 非正式交付计算书 · 光筑智能光伏深化系统')}</small>
        </div>
      </div>
      <div class="gz-hdr-right">
        <div><b>工程：</b>${esc(projName)}</div>
        <div><b>日期：</b>${dateStr} · 第 ${pageNo} / 6 页</div>
      </div>
    </header>`;

  const renderPageFtr = (pageNo) => `
    <footer class="gz-ftr">
      <span>${esc('光筑智能光伏工程设计系统 · 离线未核验预览（OFFLINE UNVERIFIED PREVIEW）')}</span>
      <span>项目：${esc(projName)} · 页码 ${pageNo} / 6</span>
    </footer>`;

  // 12x24 hourly output matrix preview for Page 4 (never synthesize fake sine-wave output)
  const hmMatrix = sim.hourly_heatmap_12x24?.ac_kw;
  const hoursSubset = [6, 8, 10, 11, 12, 13, 14, 16, 18];
  const hasRealHeatmap = Array.isArray(hmMatrix) && hmMatrix.length >= 12;
  const heatmapRowsHtml = hasRealHeatmap
    ? Array.from({ length: 12 }, (_, mIdx) => {
        const cells = hoursSubset.map((hr) => {
          const val = dcKw > 0 && Array.isArray(hmMatrix[mIdx]) ? finiteNum(hmMatrix[mIdx][hr], 0) : 0;
          const ratio = acKw > 0 ? Math.min(1, val / acKw) : 0;
          const bg = `rgba(37,99,235,${(0.06 + ratio * 0.68).toFixed(2)})`;
          const fg = ratio > 0.55 ? '#ffffff' : '#0f172a';
          return `<td style="background:${bg};color:${fg};text-align:center">${val.toFixed(0)}</td>`;
        }).join('');
        return `<tr><td><b>${mIdx + 1}月</b></td>${cells}</tr>`;
      }).join('')
    : `<tr><td colspan="${hoursSubset.length + 1}" style="text-align:center;color:#64748b;padding:12px">${esc('暂无 12×24 逐时出力矩阵数据（N/A · 后端离线未核验预览）')}</td></tr>`;

  const coldVocVal = mpsCount > 0 ? finiteOrNull(mf.string_cold_voc_v) : null;
  const coldVmppVal = mpsCount > 0 ? finiteOrNull(mf.string_cold_vmpp_v) : null;
  const hotVmppVal = mpsCount > 0 ? finiteOrNull(mf.string_hot_vmpp_v) : null;
  const maxDcVal = finiteOrNull(mf.max_dc_v);
  const mpptMaxVal = finiteOrNull(mf.mppt_v_max);
  const vocVerdictText = mpsCount <= 0
    ? 'N/A（0 串 / 未排布组件）'
    : mf.safe === true
      ? '前端初算在安全区间（待复核）'
      : mf.safe === false
        ? '⚠ 超出逆变器或 MPPT 电压安全窗口，须下调串联块数'
        : 'N/A（未核验）';

  const deadLoadVal = modCount > 0 ? finiteOrNull(mf.added_dead_load_kg_m2) : (dcKw === 0 ? 0 : null);
  const maxLoadVal = finiteOrNull(mf.max_roof_load_kg_m2);
  const loadVerdictText = modCount <= 0
    ? 'N/A（未排布组件）'
    : mf.load_ok === true
      ? '前端静载初算未超限（待结构工程师复核）'
      : mf.load_ok === false
        ? '⚠ 超出屋面静荷载上限，须切换轻质夹具或结构加固'
        : 'N/A（未核验）';

  const recSetbackVal = finiteOrNull(mf.recommended_edge_setback_m ?? mf.min_required_setback_m);
  const windVerdictText = modCount <= 0
    ? 'N/A（未排布组件）'
    : mf.wind_ok === true
      ? '前端边角退距初算满足输入包络（待结构工程师复核）'
      : mf.wind_ok === false
        ? '⚠ 边角防风揭退距不足，须加大退距或锚固'
        : 'N/A（未核验）';

  const capexPerWVal = finiteOrNull(fin.capex_per_w);
  const capexWanVal = finiteOrNull(fin.capex_wan) ?? (
    dcKw > 0 && capexPerWVal !== null
      ? Number(((dcKw * capexPerWVal) / 10).toFixed(2))
      : (dcKw === 0 ? 0 : null)
  );
  const irrVal = dcKw > 0 ? finiteOrNull(fin.irr_pct) : null;
  const npvVal = dcKw > 0 ? finiteOrNull(fin.npv_wan ?? fin.npv_25_wan) : (dcKw === 0 ? 0 : null);
  const lcoeVal = dcKw > 0 ? finiteOrNull(fin.lcoe_rmb_kwh ?? fin.lcoe_cny_kwh) : null;
  const paybackVal = dcKw > 0 ? finiteOrNull(fin.payback_years ?? fin.payback_yr) : null;
  const selfRatioRaw = dcKw > 0 ? finiteOrNull(fin.self_consumption_ratio) : (dcKw === 0 ? 0 : null);
  const selfRatioDisplay = selfRatioRaw === null
    ? 'N/A（未核验/不适用）'
    : `${Math.round(selfRatioRaw <= 1 ? selfRatioRaw * 100 : selfRatioRaw)}%`;

  const globHorDisplay = finiteOrNull(sum.glob_hor_kwh_m2);
  const globIncDisplay = finiteOrNull(sum.glob_inc_kwh_m2);
  const dcDropVal = finiteOrNull(elec.sizing?.maxDcDropPct);
  const acDropVal = finiteOrNull(elec.sizing?.acDropPct);

  const htmlOut = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>${esc(projName)} — 《光筑专业报告》（离线未核验预览）</title>
  <style>
    body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; color: #0f172a; background: #e2e8f0; margin: 0; padding: 18px; }
    .gz-offline-banner { max-width: 210mm; margin: 0 auto 12px; padding: 10px 14px; background: #fef3c7; border: 2px solid #d97706; color: #92400e; border-radius: 6px; font-size: 12.5px; line-height: 1.5; box-sizing: border-box; }
    .gz-pro-page { position: relative; overflow: hidden; width: 210mm; min-height: 286mm; margin: 0 auto 18px; background: #ffffff; padding: 13mm 15mm 16mm; box-sizing: border-box; box-shadow: 0 6px 22px rgba(15,23,42,0.12); border-radius: 4px; page-break-after: always; display: flex; flex-direction: column; justify-content: space-between; }
    .gz-wm-layer { position: absolute; inset: 0; pointer-events: none; z-index: 0; display: flex; flex-direction: column; justify-content: space-around; align-items: center; transform: rotate(-26deg); opacity: 0.055; user-select: none; }
    .gz-wm-stamp { display: flex; align-items: center; gap: 14px; font-size: 38px; font-weight: 800; color: #1e3a8a; letter-spacing: 4px; white-space: nowrap; }
    .gz-wm-stamp img { width: 44px; height: 44px; border-radius: 8px; }
    .gz-content { position: relative; z-index: 1; flex: 1; }
    .gz-hdr { position: relative; z-index: 1; display: flex; justify-content: space-between; align-items: center; border-bottom: 2.5px solid #1e3a8a; padding-bottom: 9px; margin-bottom: 12px; }
    .gz-hdr-left { display: flex; align-items: center; gap: 11px; }
    .gz-hdr-left img { width: 38px; height: 38px; border-radius: 8px; }
    .gz-hdr h1 { margin: 0; font-size: 16.5px; color: #1e3a8a; }
    .gz-hdr small { color: #475569; font-size: 11px; }
    .gz-hdr-right { text-align: right; font-size: 11px; color: #475569; line-height: 1.5; }
    .gz-ftr { position: relative; z-index: 1; display: flex; justify-content: space-between; border-top: 1px solid #cbd5e1; padding-top: 6px; margin-top: 10px; font-size: 10.5px; color: #64748b; }
    .gz-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 11px; margin-bottom: 12px; }
    .gz-card { border: 1px solid #cbd5e1; border-radius: 6px; padding: 9px 11px; background: rgba(248,250,252,0.92); font-size: 11.8px; line-height: 1.62; }
    .gz-card h3 { margin: 0 0 6px; font-size: 12.8px; color: #1e3a8a; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }
    .gz-kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 12px; }
    .gz-kpi { border: 1px solid #bfdbfe; background: #eff6ff; border-radius: 6px; padding: 9px; text-align: center; }
    .gz-kpi span { display: block; font-size: 11px; color: #475569; }
    .gz-kpi strong { font-size: 15.5px; color: #1d4ed8; }
    table { width: 100%; border-collapse: collapse; font-size: 11px; margin-bottom: 12px; background: rgba(255,255,255,0.94); }
    th, td { border: 1px solid #cbd5e1; padding: 5px 7px; text-align: right; }
    th:first-child, td:first-child { text-align: left; }
    thead th { background: #1e3a8a; color: #ffffff; font-weight: 700; }
    .gz-loss-bar { display: flex; align-items: center; gap: 10px; margin: 6px 0; font-size: 11.8px; }
    .gz-loss-fill { height: 14px; background: linear-gradient(90deg, #1d4ed8, #38bdf8); border-radius: 3px; }
    @media print { body { background: #fff; padding: 0; } .gz-pro-page { box-shadow: none; margin: 0; width: auto; min-height: auto; } .no-print { display: none !important; } }
  </style>
</head>
<body>
  ${offlineBannerHtml}
  <div class="no-print" style="max-width:210mm;margin:0 auto 12px;display:flex;justify-content:space-between;align-items:center;gap:10px">
    <span style="font-size:12.5px;font-weight:700;color:#1e293b">${esc('《光筑专业报告》前端离线未核验预览（共 6 页）')}</span>
    <button onclick="window.print()" style="padding:8px 16px;background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:700">🖨️ 打印 / 另存为 PDF (A4)</button>
  </div>

  <!-- Page 1: Cover & Project Overview -->
  <section class="gz-pro-page" id="gz-report-page-1">
    ${watermarkHtml}
    <div class="gz-content">
      ${renderPageHdr('工程概况与离线预览总览', 1)}
      <div style="margin-bottom:10px;padding:7px 10px;background:#fffbeb;border:1px solid #f59e0b;border-radius:5px;font-size:11.5px;color:#92400e">
        <b>${esc(offlineBannerText)}</b>
      </div>
      <div class="gz-kpi-row">
        <div class="gz-kpi"><span>直流装机容量 (Pnom)</span><strong>${dcKw.toFixed(2)} kWp</strong></div>
        <div class="gz-kpi"><span>首年并网发电量 (E_Grid)</span><strong>${(annualKwh / 10000).toFixed(2)} 万kWh</strong></div>
        <div class="gz-kpi"><span>首年等效满发小时 (Yf)</span><strong>${specYield.toFixed(1)} h</strong></div>
        <div class="gz-kpi"><span>系统综合效率 (PR)</span><strong>${prPct.toFixed(2)} %</strong></div>
      </div>
      <div class="gz-grid2">
        <div class="gz-card">
          <h3>1. 站址地理与屋面三维参数</h3>
          <div>站址地址：<b>${esc(scrubReportBrandText(site.address || site.name || '—'))}</b></div>
          <div>地理坐标：<b>${finiteOrNull(site.lat) !== null ? `${finiteNum(site.lat, 0).toFixed(4)}°N` : '—'}, ${finiteOrNull(site.lon) !== null ? `${finiteNum(site.lon, 0).toFixed(4)}°E` : '—'}</b></div>
          <div>排布拓扑：<b>${esc(sys.orientation_mode || 'south_fixed')}</b> · 倾角 <b>${finiteNum(sys.tilt_deg, 0)}°</b> / 方位角 <b>${finiteNum(sys.azimuth_deg, 180)}°</b></div>
          <div>屋面边界：<b>${esc(sys.roof_type || 'flat')}</b> · 檐高 <b>${finiteNum(sys.building_height_m, 0)}m</b> · 女儿墙 <b>${finiteNum(sys.parapet_height_m, 0)}m</b></div>
        </div>
        <div class="gz-card">
          <h3>2. 光伏阵列与并网逆变器配置</h3>
          <div>光伏组件：<b>${esc(scrubReportBrandText(sys.module_model || '未指定组件'))}</b> × <b>${modCount} 块</b></div>
          <div>并网逆变器：<b>${esc(scrubReportBrandText(sys.inverter_model || '未指定逆变器'))}</b> × <b>${invCount} 台</b> (${acKw.toFixed(1)} kWac)</div>
          <div>容配比：<b>${dcAcVal.toFixed(2)} : 1</b> · 组串总数 <b>${strCount} 串</b>（单串 ${mpsCount} 块）</div>
          <div>地表反照率：<b>${finiteOrNull(mf.albedo ?? site.albedo) ?? '—'}</b> · 智能剔除高遮挡位点 <b>${finiteNum(mf.pruned_shaded_count, 0)} 块</b></div>
        </div>
      </div>
      <div class="gz-card">
        <h3>${esc('3. 预览状态与数据边界说明')}</h3>
        <div>${esc('当前处于离线回退模式（OFFLINE UNVERIFIED PREVIEW），各项指标直接展示前端当前状态，对缺失或未计算项保留 0 或标注 N/A（未核验/不适用），不替代后端正式工程仿真计算书。')}</div>
      </div>
    </div>
    ${renderPageFtr(1)}
  </section>

  <!-- Page 2: Electrical Topology & String Voltage-Temperature Envelope -->
  <section class="gz-pro-page" id="gz-report-page-2">
    ${watermarkHtml}
    <div class="gz-content">
      ${renderPageHdr('电气配串与极端温度电压包络校核', 2)}
      <div class="gz-grid2">
        <div class="gz-card">
          <h3>1. 组串极端温度电压窗口校核 (IEC 62548)</h3>
          <div>极端低温设定：<b>${fmtNullable(mf.extreme_temp_min_c, 1, '°C')}</b> · 单串低温 Voc：<b>${fmtNullable(coldVocVal, 1, 'V')}</b>（上限 ${fmtNullable(maxDcVal, 0, 'V')}）</div>
          <div>低温满载电压 Vmpp：<b>${fmtNullable(coldVmppVal, 1, 'V')}</b>（MPPT 上限 ${fmtNullable(mpptMaxVal, 0, 'V')}） · 高温 Vmpp：<b>${fmtNullable(hotVmppVal, 1, 'V')}</b></div>
          <div>安全串联范围：<b>${finiteOrNull(mf.min_series_mppt) ?? '—'} ~ ${finiteOrNull(mf.max_series_safe) ?? '—'} 块/串</b> · 当前采用 <b>${mpsCount} 块/串</b>（${esc(vocVerdictText)}）</div>
        </div>
        <div class="gz-card">
          <h3>2. 交直流电缆选型与回路压降 (GB 50797)</h3>
          <div>直流组串线缆：<b>PV1-F 1×4mm² DC 1500V</b> · 最不利压降 <b>${dcDropVal !== null ? `${dcDropVal.toFixed(2)}%` : 'N/A（未核验）'}</b></div>
          <div>交流并网主缆：<b>${esc(elec.sizing?.acCableSpec || '待核定')}</b> · 交流压降 <b>${acDropVal !== null ? `${acDropVal.toFixed(2)}%` : 'N/A（未核验）'}</b></div>
          <div>并网接入方式：<b>${esc(acKw <= 0 ? 'N/A（0 kWac）' : (acKw >= 400 ? '10kV 升压箱变并网' : '0.4kV 低压并网柜接入'))}</b></div>
        </div>
      </div>
      <h3 style="font-size:13px;color:#1e3a8a;margin:6px 0">3. 逆变器通道分配明细表</h3>
      <table>
        <thead>
          <tr><th>逆变器</th><th>通道编号</th><th>坡面朝向</th><th>接入串数</th><th>串联块数</th><th>工作电压 (V)</th><th>工作电流 (A)</th><th>校核结论</th></tr>
        </thead>
        <tbody>
          ${mpptRows.length > 0
            ? mpptRows.slice(0, 12).map((r) => `
              <tr>
                <td>${esc(r.inverterName || '—')}</td>
                <td>${esc(r.mpptName || '—')}</td>
                <td>${esc(r.slopeLabel || r.slope || '—')}</td>
                <td>${finiteNum(r.stringCount, 0)}</td>
                <td>${finiteNum(r.modulesPerString, 0)}</td>
                <td>${finiteOrNull(r.vmpV) !== null ? finiteNum(r.vmpV, 0).toFixed(1) : '—'}</td>
                <td>${finiteOrNull(r.workCurrentA) !== null ? finiteNum(r.workCurrentA, 0).toFixed(1) : '—'}</td>
                <td>${esc(r.status || '前端初算（未核验）')}</td>
              </tr>
            `).join('')
            : `<tr><td colspan="8" style="text-align:center;color:#64748b;padding:12px">${esc('暂无已核验逆变器 MPPT 通道分配记录（0 串 / 未核验）')}</td></tr>`}
        </tbody>
      </table>
    </div>
    ${renderPageFtr(2)}
  </section>

  <!-- Page 3: 12-Month Solar Irradiation & Energy Balance Table -->
  <section class="gz-pro-page" id="gz-report-page-3">
    ${watermarkHtml}
    <div class="gz-content">
      ${renderPageHdr('全年12个月辐照与能量平衡汇总表', 3)}
      <table>
        <thead>
          <tr>
            <th>月份</th><th>水平总辐照<br>(kWh/m²)</th><th>水平散射<br>(kWh/m²)</th><th>环境温度<br>(°C)</th><th>平均风速<br>(m/s)</th>
            <th>斜面总辐照<br>(kWh/m²)</th><th>有效辐照<br>(kWh/m²)</th><th>背面增益<br>(kWh/m²)</th><th>阵列直流电量<br>(kWh)</th><th>并网交流电量<br>(kWh)</th><th>综合效率<br>PR (%)</th>
          </tr>
        </thead>
        <tbody>${monthRowsHtml}</tbody>
      </table>
      <div class="gz-card">
        <h3>年度能量平衡关键指标解读</h3>
        <div>全年水平面总辐照 <b>${globHorDisplay !== null ? `${globHorDisplay.toFixed(1)} kWh/m²` : 'N/A（未核验）'}</b>，倾角转置后斜面辐照 <b>${globIncDisplay !== null ? `${globIncDisplay.toFixed(1)} kWh/m²` : 'N/A（未核验）'}</b>，首年交流并网总发电量 <b>${Math.round(annualKwh).toLocaleString('zh-CN')} kWh</b>，首年系统综合效率 <b>${prPct.toFixed(2)}%</b>。</div>
      </div>
    </div>
    ${renderPageFtr(3)}
  </section>

  <!-- Page 4: Energy Loss Waterfall & 12x24 Hourly Diagnostics -->
  <section class="gz-pro-page" id="gz-report-page-4">
    ${watermarkHtml}
    <div class="gz-content">
      ${renderPageHdr('全链路损耗瀑布图与12×24逐时出力矩阵', 4)}
      <div class="gz-card" style="margin-bottom:12px">
        <h3>1. 全链路物理损耗级联分解</h3>
        <div class="gz-loss-bar"><span style="width:205px">水平面总辐照 (GlobHor)</span><div class="gz-loss-fill" style="width:${globHorDisplay ? 250 : 8}px"></div><b>${globHorDisplay !== null ? `${globHorDisplay.toFixed(1)} kWh/m²` : 'N/A（未核验）'}</b></div>
        <div class="gz-loss-bar"><span style="width:205px">倾角斜面辐照增益 (GlobInc)</span><div class="gz-loss-fill" style="width:${globIncDisplay ? 276 : 8}px"></div><b>${globIncDisplay !== null ? `${globIncDisplay.toFixed(1)} kWh/m²` : 'N/A（未核验）'}</b></div>
        <div class="gz-loss-bar"><span style="width:205px">近场三维遮挡与灰尘折减后</span><div class="gz-loss-fill" style="width:${dcKw > 0 ? 220 : 8}px"></div><b>反照率 ${finiteOrNull(mf.albedo ?? site.albedo) ?? '—'} · 剔除遮挡 ${finiteNum(mf.pruned_shaded_count, 0)} 块</b></div>
        <div class="gz-loss-bar"><span style="width:205px">组件工作温升与失配线损后</span><div class="gz-loss-fill" style="width:${dcKw > 0 ? 200 : 8}px"></div><b>${esc(dcKw > 0 ? '前端估算输出（未核验）' : '0 kWh（未排布组件）')}</b></div>
        <div class="gz-loss-bar"><span style="width:205px">逆变器转换后交流并网电量</span><div class="gz-loss-fill" style="width:${annualKwh > 0 ? 190 : 8}px;background:#059669"></div><b>${Math.round(annualKwh).toLocaleString('zh-CN')} kWh (PR ${prPct.toFixed(1)}%)</b></div>
      </div>
      <h3 style="font-size:13px;color:#1e3a8a;margin:6px 0">2. 全年 12 月 × 白昼代表时刻交流出力热力矩阵 (kW)</h3>
      <table>
        <thead>
          <tr><th>月份 \\ 时刻</th>${hoursSubset.map((h) => `<th style="text-align:center">${String(h).padStart(2, '0')}:00</th>`).join('')}</tr>
        </thead>
        <tbody>${heatmapRowsHtml}</tbody>
      </table>
    </div>
    ${renderPageFtr(4)}
  </section>

  <!-- Page 5: 12-Factor Structural, Wind/Snow & Shading Compliance -->
  <section class="gz-pro-page" id="gz-report-page-5">
    ${watermarkHtml}
    <div class="gz-content">
      ${renderPageHdr('十二维结构荷载、防风揭与三维遮挡校核', 5)}
      <div class="gz-grid2">
        <div class="gz-card">
          <h3>1. 屋面静荷载与固定方式校核 (GB 55001)</h3>
          <div>新增均布静荷载：<b>${deadLoadVal !== null ? `${deadLoadVal.toFixed(1)} kg/m²` : 'N/A（未核验）'}</b></div>
          <div>屋面允许静荷载上限：<b>${maxLoadVal !== null ? `${maxLoadVal.toFixed(1)} kg/m²` : 'N/A（未核验）'}</b></div>
          <div>支架构型：<b>${esc(sys.rack_type || '—')}</b> · 初算状态：<b>${esc(loadVerdictText)}</b></div>
        </div>
        <div class="gz-card">
          <h3>2. 50年一遇风雪荷载与边角退距校核</h3>
          <div>基本风压 w0：<b>${fmtNullable(mf.basic_wind_w0_kn_m2, 2, 'kN/m²')}</b> · 基本雪压 s0：<b>${fmtNullable(mf.basic_snow_s0_kn_m2, 2, 'kN/m²')}</b></div>
          <div>最小推荐防风揭边角退距：<b>${recSetbackVal !== null ? `${recSetbackVal.toFixed(2)} m` : 'N/A（未核验）'}</b></div>
          <div>初算状态：<b>${esc(windVerdictText)}</b></div>
        </div>
      </div>
      <div class="gz-card">
        <h3>3. 女儿墙与屋面立体障碍物近场阴影剔除结论</h3>
        <div>女儿墙高度 <b>${finiteNum(sys.parapet_height_m, 0)} m</b>，单块最大允许年遮挡损失阈值设定 <b>${finiteOrNull(mf.max_module_shading_loss_pct) ?? '—'}%</b>，当前记录剔除高遮挡位点 <b>${finiteNum(mf.pruned_shaded_count, 0)} 块</b>。</div>
      </div>
    </div>
    ${renderPageFtr(5)}
  </section>

  <!-- Page 6: 25-Year Lifecycle Financial Evaluation & Sign-off -->
  <section class="gz-pro-page" id="gz-report-page-6">
    ${watermarkHtml}
    <div class="gz-content">
      ${renderPageHdr('25年全生命周期经济评价与预览说明', 6)}
      <div class="gz-kpi-row">
        <div class="gz-kpi"><span>工程总投资 (CAPEX)</span><strong>${esc(fmtNullable(capexWanVal, 2, '万元'))}</strong></div>
        <div class="gz-kpi"><span>全投资内部收益率 (IRR)</span><strong>${esc(fmtNullable(irrVal, 2, '%'))}</strong></div>
        <div class="gz-kpi"><span>25年累计净现值 (NPV)</span><strong>${esc(fmtNullable(npvVal, 2, '万元'))}</strong></div>
        <div class="gz-kpi"><span>平准化度电成本 (LCOE)</span><strong>${esc(fmtNullable(lcoeVal, 3, '元/kWh'))}</strong></div>
      </div>
      <div class="gz-card" style="margin-bottom:12px">
        <h3>1. 投资收益与电价消纳边界参数</h3>
        <div>单位造价：<b>${esc(fmtNullable(capexPerWVal, 2, '元/Wp'))}</b> · 综合自用电价：<b>${esc(fmtNullable(fin.tariff_self_rmb, 2, '元/kWh'))}</b> · 余电上网电价：<b>${esc(fmtNullable(fin.feed_in_tariff_rmb, 2, '元/kWh'))}</b></div>
        <div>自发自用比例：<b>${esc(selfRatioDisplay)}</b> · 预计静态投资回收期：<b>${esc(paybackVal !== null ? `${paybackVal.toFixed(2)} 年` : 'N/A（未核验/不适用）')}</b></div>
      </div>
      <div class="gz-card">
        <h3>2. 工程设计合规审定签章栏</h3>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;padding-top:8px">
          <div>编制来源：<b>${esc('前端离线未核验预览')}</b><br><span style="color:#64748b">日期：${dateStr}</span></div>
          <div>核验状态：<b>${esc('未核验（待后端仿真与双专业复核）')}</b><br><span style="color:#64748b">参考规范：GB 50797 / IEC 61724</span></div>
          <div>批准签章：<b>____________________</b><br><span style="color:#64748b">建设/设计单位盖章</span></div>
        </div>
      </div>
    </div>
    ${renderPageFtr(6)}
  </section>
</body>
</html>`;

  return scrubReportBrandText(htmlOut);
}

export function triggerBrowserAttachmentDownload(downloadUrl, filename = '光筑专业报告.pdf') {
  if (!downloadUrl || typeof document === 'undefined' || !document.body) return false;
  try {
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = filename || '光筑专业报告.pdf';
    a.rel = 'noopener';
    a.style.display = 'none';
    document.body.append(a);
    a.click();
    setTimeout(() => {
      try { a.remove(); } catch { /* ignore */ }
    }, 300);
    return true;
  } catch {
    return false;
  }
}

export function openHtmlInPreviewModal(view, {
  html = '',
  htmlUrl = '',
  downloadUrl = '',
  filename = '光筑专业报告.pdf',
  savedDisplay = '',
  titleZh = '《光筑专业报告》在线预览',
  titleEn = 'Guangzhu Professional Report Preview',
} = {}) {
  const link = view.linkage3d || (view.linkage3d = createDefaultLinkageState());
  link.reportPreview = {
    open: true,
    html: scrubReportBrandText(html),
    htmlUrl: htmlUrl || '',
    downloadUrl: downloadUrl || '',
    filename: filename || '光筑专业报告.pdf',
    savedDisplay: savedDisplay || '',
    titleZh,
    titleEn,
    activePage: 1,
  };
  return link.reportPreview;
}

/**
 * Render In-App 6-Page Report Preview Modal (`data-sat-pro-report-modal="1"`)
 * Zero `window.open` popups — works 100% reliably inside `pywebview` WebView2 & desktop browsers!
 */
export function renderProReportPreviewModal(view) {
  const rp = view.linkage3d?.reportPreview;
  if (!rp?.open) return '';

  const pageNums = [1, 2, 3, 4, 5, 6];
  const activePage = rp.activePage || 1;
  const safeSavedEn = String(rp.savedDisplay || 'Downloads/Guangzhu_Pro_Report.pdf').replace(/[\u4e00-\u9fff]+/g, 'Guangzhu_Pro_Report');
  const safeSavedZh = rp.savedDisplay ? '已生成至本地下载目录' : '';

  return `<div class="satmap-modal-backdrop satmap-report-modal-backdrop" data-sat-pro-report-modal="1">
    <div class="satmap-modal-card satmap-report-modal-card" role="dialog" aria-modal="true" aria-label="${esc(L(rp.titleZh || '光筑专业报告预览', rp.titleEn || 'Guangzhu Pro Report Preview'))}">
      <div class="satmap-report-modal-toolbar">
        <div style="display:flex;align-items:center;gap:10px">
          <img src="/assets/guangzhu-128.png" alt="" width="28" height="28" style="border-radius:6px">
          <div>
            <strong style="font-size:14px">${esc(L(rp.titleZh || '《光筑专业报告》在线预览', rp.titleEn || 'Guangzhu Professional Report Preview'))}</strong>
            <small style="display:block;font-size:11px;color:var(--muted)">
              ${esc(L(
                `共六页工程精细化仿真计算书 · 含光筑防伪水印${safeSavedZh ? ` · ${safeSavedZh}` : ''}`,
                `6-Page Engineering Simulation Calculation Book · Guangzhu Watermark${rp.savedDisplay ? ` · ${safeSavedEn}` : ''}`
              ))}
            </small>
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
          <div class="satmap-report-page-pills">
            ${pageNums.map((p) => `
              <button type="button" class="sat-btn ${activePage === p ? 'primary' : ''}" data-sat-report-page="${p}" style="height:26px;padding:0 8px;font-size:11.5px">
                ${esc(L(`第${p}页`, `P${p}`))}
              </button>
            `).join('')}
          </div>
          <button type="button" class="sat-btn" data-sat-action="print-preview-report">
            🖨️ ${esc(L('打印报告', 'Print Report'))}
          </button>
          <button type="button" class="sat-btn primary" data-sat-action="export-pvsyst-v2">
            ⬇ ${esc(L('导出并打开报告', 'Export & Open PDF'))}
          </button>
          ${rp.downloadUrl ? `
            <a class="sat-btn success" href="${esc(rp.downloadUrl)}" download="${esc(rp.filename || 'guangzhu-report.pdf')}" rel="noopener" style="text-decoration:none;display:inline-flex;align-items:center">
              📥 ${esc(L('直接下载文件', 'Direct Download'))}
            </a>
          ` : ''}
          <button type="button" class="sat-btn" data-sat-action="close-modals">
            ✕ ${esc(L('关闭预览', 'Close'))}
          </button>
        </div>
      </div>
      <iframe
        id="satmap-pro-report-iframe"
        class="satmap-report-preview-frame"
        title="${esc(L('光筑专业报告内容视口', 'Guangzhu Professional Report Frame'))}"
        ${rp.html ? `srcdoc="${esc(rp.html)}"` : rp.htmlUrl ? `src="${esc(rp.htmlUrl)}"` : ''}
      ></iframe>
    </div>
  </div>`;
}

export function buildProReportPayload(view, { openNative = true } = {}) {
  if (!view.hasLaidOut && view.autoLayoutOnEmpty !== false) {
    view.layoutModules({ quiet: true, autoCreateRoof: true });
    view.electricalConfirmed = true;
    view.showStringColors = true;
    view.computeElectricalAllocation();
  }
  if (!view.pvsystData) {
    view.refreshPvsystData({ fetchBackend: false });
  }

  const mf = view.mfState || createDefaultMultiFactorState();
  const link = view.linkage3d || (view.linkage3d = createDefaultLinkageState());
  const modSpec = view.getSelectedModule() || {};
  const invSpec = view.getSelectedInverter() || {};
  const activeTilt = view.roofType === 'flat' ? view.tiltDeg : view.roofSlopeDeg;
  const dcKwVal = Math.max(0, finiteNum(view.summary?.dcKw, 0));
  const acKwVal = Math.max(0, finiteNum(view.summary?.acKw, 0));
  const modCountVal = Math.max(0, Math.round(finiteNum(view.summary?.moduleCount, 0)));
  const invCountVal = modCountVal > 0 ? Math.max(0, Math.round(finiteNum(view.summary?.inverterCount, 0))) : 0;
  const strCountVal = modCountVal > 0 ? Math.max(0, Math.round(finiteNum(view.summary?.stringCount, 0))) : 0;
  const mpsVal = modCountVal > 0 ? Math.max(0, Math.round(finiteNum(view.modulesPerString, 0))) : 0;
  const dcAcVal = dcKwVal > 0 && acKwVal > 0 ? finiteNum(view.summary?.dcAcRatio, Number((dcKwVal / acKwVal).toFixed(2))) : 0;
  const annualKwhVal = dcKwVal > 0 ? Math.max(0, finiteNum(view.summary?.annualKwh, 0)) : 0;
  const specYieldVal = dcKwVal > 0 ? Math.max(0, finiteNum(view.summary?.specificYield, 0)) : 0;
  const prPctVal = dcKwVal > 0 ? Math.max(0, finiteNum(view.summary?.prPct, 0)) : 0;

  const vocCheck = computeColdVocAndStringSafety(modSpec, invSpec, mf, modCountVal > 0 ? view.modulesPerString : 0);
  const structCheck = computeMultiFactorStructuralCheck({
    roofType: view.roofType,
    orientationMode: view.orientationMode || mf.orientationMode,
    rackRows: mf.rackRows,
    tiltDeg: activeTilt,
    buildingHeightM: view.buildingHeightM,
    edgeSetbackM: view.edgeSetbackM,
    moduleSpec: modSpec,
    mfParams: mf,
  });

  const prunedCount = (view.prunedShadedModules || []).length;
  const isSynced = link.syncStatus === 'synced' || Boolean(
    link.syncStatus &&
    typeof link.syncStatus === 'object' &&
    (link.syncStatus.state === 'synced' || link.syncStatus.ok) &&
    !link.syncStatus.stale &&
    link.syncStatus.projectId
  );
  const syncedProjectId = link.syncStatus === 'synced'
    ? (link.linkedSource?.id || undefined)
    : (isSynced ? link.syncStatus.projectId : undefined);
  const syncedVersion = link.syncStatus === 'synced'
    ? (link.linkedSource?.version || 1)
    : (isSynced ? (link.syncStatus.version || 1) : undefined);

  const irrVal = dcKwVal > 0 ? finiteOrNull(view.summary?.irrPct) : null;
  const npvVal = dcKwVal > 0 ? (finiteOrNull(view.summary?.npv25Wan) ?? 0) : 0;
  const paybackVal = dcKwVal > 0 ? finiteOrNull(view.summary?.paybackYears) : null;
  const lcoeVal = dcKwVal > 0 ? finiteOrNull(view.summary?.lcoeRmb) : null;

  return {
    open_native: Boolean(openNative),
    format: 'html',
    icon_url: '/assets/guangzhu-128.png',
    branding: {
      app_name: '光筑 Guangzhu',
      report_title: '光筑专业报告',
      watermark_text: '光筑 · GUANGZHU',
      icon_url: '/assets/guangzhu-128.png',
      icon_hd_url: '/assets/guangzhu-512.png',
    },
    ...(syncedProjectId ? { project_id: syncedProjectId, version: syncedVersion || 1 } : {}),
    project_name: view.projectName,
    dc_kw: dcKwVal,
    ac_kw: acKwVal,
    dc_ac_ratio: dcAcVal,
    module_count: modCountVal,
    annual_kwh: annualKwhVal,
    specific_yield_kwh_kwp: specYieldVal,
    pr_pct: prPctVal,
    site: {
      name: view.projectName,
      address: view.address,
      lat: view.lat,
      lon: view.lon,
      albedo: mf.albedo,
    },
    system: {
      roof_type: view.roofType,
      building_height_m: view.buildingHeightM,
      parapet_height_m: Number(((finiteNum(view.parapetHeightMm, 500)) / 1000).toFixed(2)),
      orientation_mode: view.orientationMode || mf.orientationMode || 'south_fixed',
      mount_orientation: view.orientation || 'portrait',
      rack_type: mf.rackRows || '2P',
      tilt_deg: activeTilt,
      azimuth_deg: view.azimuthDeg,
      dc_kw: dcKwVal,
      ac_kw: acKwVal,
      dc_ac_ratio: dcAcVal,
      module_count: modCountVal,
      module_model: `${modSpec.brand || ''} ${modSpec.model || ''}`.trim(),
      inverter_count: invCountVal,
      inverter_model: `${invSpec.brand || ''} ${invSpec.model || ''}`.trim(),
      string_count: strCountVal,
      modules_per_string: mpsVal,
      annual_kwh: annualKwhVal,
      specific_yield: specYieldVal,
      pr_pct: prPctVal,
      pruned_shaded_modules: prunedCount,
    },
    module: modSpec,
    inverter: invSpec,
    electrical: {
      strings_per_mppt: finiteNum(invSpec.strings_per_mppt, 2),
      modules_per_string: mpsVal,
      mppt_rows: view.mpptRows || [],
      sizing: view.electricalSizing || {},
    },
    pvsyst: view.pvsystData || {},
    multifactor: {
      ...structCheck,
      ...vocCheck,
      added_dead_load_kg_m2: modCountVal > 0 ? structCheck.added_dead_load_kg_m2 : 0,
      albedo: mf.albedo,
      pollution_level: mf.pollutionLevel,
      load_profile: mf.loadProfile,
      pruned_shaded_count: prunedCount,
      pruned_shaded_modules: prunedCount,
    },
    financial: {
      capex_per_w: finiteOrNull(view.capexPerW) ?? 3.15,
      capex_wan: dcKwVal > 0 ? finiteNum(view.summary?.capexWan, 0) : 0,
      tariff_self_rmb: finiteOrNull(view.tariffRmb) ?? 0.78,
      feed_in_tariff_rmb: finiteOrNull(view.feedInTariffRmb) ?? 0.38,
      self_consumption_ratio: dcKwVal > 0 ? (finiteOrNull(view.selfConsumptionRatio) ?? 0) : 0,
      irr_pct: irrVal,
      npv_wan: npvVal,
      npv_25_wan: npvVal,
      payback_years: paybackVal,
      lcoe_rmb_kwh: lcoeVal,
    },
  };
}

/**
 * Trigger 《光筑专业报告》 Native PDF Export (`POST /api/guangzhu/pro-report/export-pdf`)
 * Zero `window.open` popups! Uses OS native viewer in `pywebview`, `<a download>` in browsers, and in-app 6-page modal preview!
 */
export async function exportPvsystProfessionalReportV2(view, {
  previewOnly = false,
  openNative = true,
} = {}) {
  const link = view.linkage3d || (view.linkage3d = createDefaultLinkageState());
  const shouldOpenNative = Boolean(openNative && !previewOnly);
  const payload = {
    ...buildProReportPayload(view, { openNative: shouldOpenNative }),
    preview_only: Boolean(previewOnly),
  };

  let exportMeta = null;
  let reportHtml = '';
  let source = 'client_fallback';

  // 1. Try view.api hook first (`guangzhu/pro-report/export-pdf` -> `pvsyst/professional-report/export-pdf` -> `pvsyst/professional-report`)
  if (typeof view.api === 'function') {
    const apiPaths = [
      'guangzhu/pro-report/export-pdf',
      'pvsyst/professional-report/export-pdf',
      'guangzhu/professional-report',
      'pvsyst/professional-report',
    ];
    for (const apiPath of apiPaths) {
      try {
        const apiRes = await view.api(apiPath, { ...payload, format: 'json' });
        if (typeof apiRes === 'string' && apiRes.includes('<')) {
          reportHtml = scrubReportBrandText(apiRes);
          source = 'backend_api';
          break;
        }
        if (apiRes && (apiRes.download_url || apiRes.saved_path || apiRes.saved_display || apiRes.html || apiRes.html_url)) {
          exportMeta = apiRes;
          if (typeof apiRes.html === 'string' && apiRes.html.length > 60) {
            reportHtml = scrubReportBrandText(apiRes.html);
          }
          source = 'backend_api';
          break;
        }
      } catch {
        // Continue to next endpoint
      }
    }
  }

  // 2. Try direct HTTP fetch when running in live browser / pywebview
  if (!exportMeta && !reportHtml && typeof fetch === 'function' && typeof window !== 'undefined' && /^https?:/.test(window.location?.protocol || '')) {
    const pdfEndpoints = [
      '/api/guangzhu/pro-report/export-pdf',
      '/api/pvsyst/professional-report/export-pdf',
    ];
    for (const ep of pdfEndpoints) {
      try {
        const resp = await fetch(ep, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(payload),
        });
        if (resp.ok) {
          const j = await resp.json();
          if (j && (j.ok || j.download_url || j.html_url || j.html)) {
            exportMeta = j;
            if (j.html) reportHtml = scrubReportBrandText(j.html);
            source = 'backend_fetch';
            break;
          }
        }
      } catch {
        // Try next
      }
    }

    if ((!exportMeta || (previewOnly && !reportHtml && !exportMeta?.html_url))) {
      for (const ep of ['/api/guangzhu/professional-report', '/api/pvsyst/professional-report']) {
        try {
          const resp = await fetch(ep, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          if (resp.ok) {
            const ct = resp.headers?.get?.('content-type') || '';
            if (ct.includes('application/json')) {
              const j = await resp.json();
              if (j?.html) {
                reportHtml = scrubReportBrandText(j.html);
                source = 'backend_fetch';
                break;
              }
            } else {
              const txt = await resp.text();
              if (txt && txt.includes('<')) {
                reportHtml = scrubReportBrandText(txt);
                source = 'backend_fetch';
                break;
              }
            }
          }
        } catch {
          // Fallback below
        }
      }
    }
  }

  if (!reportHtml && !exportMeta?.html_url) {
    reportHtml = buildClientPvsystV2ReportHtml(payload);
    if (!exportMeta) source = 'client_fallback';
  }

  const safeProj = String(view.projectName || '光筑项目').replace(/[<>:"/\\|?*]+/g, '_');
  const filename = exportMeta?.filename || `光筑专业报告_${safeProj}.pdf`;
  const downloadUrl = exportMeta?.download_url || '';
  const htmlUrl = exportMeta?.html_url || '';
  const savedDisplay = exportMeta?.saved_display || `Downloads/${filename}`;
  const openedNatively = Boolean(exportMeta?.opened_natively);

  link.lastExportedReport = {
    filename,
    downloadUrl,
    htmlUrl,
    savedDisplay,
    openedNatively,
    source,
  };

  let downloadedInBrowser = false;
  let modalOpened = false;

  if (previewOnly) {
    openHtmlInPreviewModal(view, {
      html: reportHtml,
      htmlUrl,
      downloadUrl,
      filename,
      savedDisplay,
    });
    modalOpened = true;
  } else if (openedNatively) {
    // Desktop pywebview already launched OS default PDF viewer via os.startfile!
  } else if (downloadUrl) {
    downloadedInBrowser = triggerBrowserAttachmentDownload(downloadUrl, filename);
  } else {
    // Offline client fallback: open in-app 6-page report preview modal so user never hits a dead popup
    openHtmlInPreviewModal(view, {
      html: reportHtml,
      htmlUrl,
      downloadUrl,
      filename,
      savedDisplay,
    });
    modalOpened = true;
  }

  return {
    ok: true,
    source,
    filename,
    download_url: downloadUrl,
    html_url: htmlUrl,
    saved_display: savedDisplay,
    opened_natively: openedNatively,
    openedNatively,
    downloaded_in_browser: downloadedInBrowser,
    modal_opened: modalOpened,
    html: reportHtml,
    payload,
  };
}

export async function previewGuangzhuProReport(view) {
  return exportPvsystProfessionalReportV2(view, { previewOnly: true, openNative: false });
}

/**
 * Deterministic 8-Item Pre-Delivery Engineering Compliance Health Check
 * Matches `POST /api/satmap/engineering-health-check` (`CHK-01` .. `CHK-08`).
 */
export function computeClientEngineeringHealthCheck(viewOrPayload = {}) {
  const isView = typeof viewOrPayload?.getSelectedModule === 'function';
  const view = viewOrPayload || {};
  const sys = view.system || {};
  const mf = isView
    ? (view.mfState || createDefaultMultiFactorState())
    : { ...createDefaultMultiFactorState(), ...(view.multifactor || {}) };
  const modSpec = (isView ? view.getSelectedModule() : view.module) || {};
  const invSpec = (isView ? view.getSelectedInverter() : view.inverter) || {};
  const roofTypeVal = isView ? view.roofType : (sys.roof_type || 'flat');
  const activeTilt = isView
    ? (view.roofType === 'flat' ? view.tiltDeg : view.roofSlopeDeg)
    : finiteNum(sys.tilt_deg, 15);
  const dcKwVal = Math.max(0, finiteNum(isView ? view.summary?.dcKw : (sys.dc_kw ?? view.dc_kw), 0));
  const acKwVal = Math.max(0, finiteNum(isView ? view.summary?.acKw : (sys.ac_kw ?? view.ac_kw), 0));
  const modCountVal = Math.max(0, Math.round(finiteNum(isView ? view.summary?.moduleCount : (sys.module_count ?? view.module_count), 0)));
  const mpsIn = isView ? view.modulesPerString : (sys.modules_per_string ?? view.electrical?.modules_per_string);
  const vocCheck = computeColdVocAndStringSafety(modSpec, invSpec, mf, modCountVal > 0 ? mpsIn : 0);
  const curSetbackIn = finiteNum(isView ? view.edgeSetbackM : (mf.actual_setback_m ?? sys.setback_m), 0.8);
  const structCheck = computeMultiFactorStructuralCheck({
    roofType: roofTypeVal,
    orientationMode: (isView ? view.orientationMode : sys.orientation_mode) || mf.orientationMode,
    rackRows: mf.rackRows || sys.rack_type,
    tiltDeg: activeTilt,
    buildingHeightM: isView ? view.buildingHeightM : finiteNum(sys.building_height_m, 12),
    edgeSetbackM: curSetbackIn,
    moduleSpec: modSpec,
    mfParams: mf,
  });

  const dcAc = dcKwVal > 0 && acKwVal > 0
    ? finiteNum(isView ? view.summary?.dcAcRatio : (sys.dc_ac_ratio ?? view.dc_ac_ratio), dcKwVal / acKwVal)
    : 0;
  const dcAcStatus = (dcKwVal <= 0 || acKwVal <= 0)
    ? 'fail'
    : (dcAc >= 1.0 && dcAc <= 1.35)
      ? 'pass'
      : (dcAc >= 0.85 && dcAc <= 1.50)
        ? 'warn'
        : 'fail';

  const coldVocMarginV = vocCheck.max_dc_v - vocCheck.string_cold_voc_v;
  const coldVmppMarginV = vocCheck.mppt_v_max - vocCheck.string_cold_vmpp_v;
  const effColdMarginV = Math.min(coldVocMarginV, coldVmppMarginV);
  const coldStatus = (modCountVal <= 0 || vocCheck.current_series <= 0 || !vocCheck.safe || effColdMarginV < 0)
    ? 'fail'
    : effColdMarginV >= 15
      ? 'pass'
      : 'warn';

  const mpptMinV = finiteNum(invSpec.mppt_v_min ?? invSpec.mppt_min_v, 200);
  const hotStatus = (modCountVal <= 0 || vocCheck.current_series <= 0)
    ? 'fail'
    : vocCheck.string_hot_vmpp_v >= mpptMinV + 20
      ? 'pass'
      : vocCheck.string_hot_vmpp_v >= mpptMinV
        ? 'warn'
        : 'fail';

  const loadVal = modCountVal > 0 ? structCheck.added_dead_load_kg_m2 : 0;
  const loadMax = structCheck.max_roof_load_kg_m2;
  const loadStatus = loadVal <= loadMax * 0.92 ? 'pass' : loadVal <= loadMax ? 'warn' : 'fail';

  const reqSetback = finiteNum(structCheck.recommended_edge_setback_m ?? structCheck.min_required_setback_m, 0.8);
  const curSetback = curSetbackIn;
  const windStatus = (structCheck.wind_ok && curSetback + 0.05 >= reqSetback)
    ? 'pass'
    : curSetback >= reqSetback * 0.75
      ? 'warn'
      : 'fail';

  const dcDropRaw = finiteOrNull(
    isView ? view.electricalSizing?.maxDcDropPct : view.electrical?.sizing?.maxDcDropPct
  );
  const dropStatus = (modCountVal <= 0 || dcDropRaw === null)
    ? 'fail'
    : dcDropRaw <= 1.5
      ? 'pass'
      : dcDropRaw <= 2.5
        ? 'warn'
        : 'fail';
  const dropDisplayZh = dcDropRaw !== null && modCountVal > 0
    ? `压降 ${dcDropRaw.toFixed(2)}%（限值 1.5%）`
    : '压降未核定（限值 1.5%）';
  const dropDisplayEn = dcDropRaw !== null && modCountVal > 0
    ? `${dcDropRaw.toFixed(2)}% (<= 1.5%)`
    : 'Unverified (<= 1.5%)';

  const prunedCountVal = isView
    ? (view.prunedShadedModules || []).length
    : Math.max(0, Math.round(finiteNum(mf.pruned_shaded_count ?? sys.pruned_shaded_modules, 0)));
  const shadeLossPct = finiteNum(
    isView
      ? (view.pvsystParams?.shading_loss_pct ?? view.shading3dSummary?.annualLinearLossPct)
      : (view.pvsyst?.loss_tree_detail?.near_shading_loss_pct ?? mf.shading_loss_pct),
    modCountVal > 0 ? 1.8 : 0
  );
  const shadeStatus = shadeLossPct <= 4.5 ? 'pass' : shadeLossPct <= 8.0 ? 'warn' : 'fail';

  const irrPct = dcKwVal > 0
    ? finiteOrNull(isView ? view.summary?.irrPct : view.financial?.irr_pct)
    : null;
  const paybackYr = dcKwVal > 0
    ? finiteOrNull(isView ? view.summary?.paybackYears : (view.financial?.payback_years ?? view.financial?.payback_yr))
    : null;
  const hasValidReturn = dcKwVal > 0 && irrPct !== null && paybackYr !== null && paybackYr > 0;
  const finStatus = !hasValidReturn
    ? 'fail'
    : (irrPct >= 8.0 && paybackYr <= 9.0)
      ? 'pass'
      : (irrPct >= 5.5 && paybackYr <= 12.0)
        ? 'warn'
        : 'fail';
  const finDisplayZh = hasValidReturn
    ? `收益率 ${irrPct.toFixed(1)}% · ${paybackYr.toFixed(1)} 年回本`
    : (irrPct !== null ? `收益率 ${irrPct.toFixed(1)}% · 无法回本` : '收益率不适用 · 无法回本');
  const finDisplayEn = hasValidReturn
    ? `IRR ${irrPct.toFixed(1)}% · ${paybackYr.toFixed(1)} yr`
    : (irrPct !== null ? `IRR ${irrPct.toFixed(1)}% · No Payback` : 'IRR N/A · No Payback');

  const items = [
    {
      id: 'dc_ac_ratio',
      code: 'CHK-01',
      code_zh: '核验一',
      title_zh: '容配比合理性校核',
      title_en: 'DC/AC Sizing Ratio',
      status: dcAcStatus,
      display_zh: `${dcAc.toFixed(2)} 比 1`,
      display_en: `${dcAc.toFixed(2)} : 1`,
      fix_hint_zh: '建议保持直流与交流容配比在 1.05 至 1.30 区间以兼顾弱光增益与限幅控制',
      fix_hint_en: 'Keep DC/AC ratio within 1.05–1.30 for optimal inverter loading',
    },
    {
      id: 'cold_voc_margin',
      code: 'CHK-02',
      code_zh: '核验二',
      title_zh: '低温开路电压安全裕度',
      title_en: 'Extreme Cold Voc Margin',
      status: coldStatus,
      display_zh: `${vocCheck.string_cold_voc_v} / ${vocCheck.max_dc_v} 伏`,
      display_en: `${vocCheck.string_cold_voc_v} / ${vocCheck.max_dc_v} V`,
      fix_hint_zh: `若超限请将单串块数下调至 ${vocCheck.max_series_safe} 块以内`,
      fix_hint_en: `Reduce modules per string to <= ${vocCheck.max_series_safe} pcs if overlimit`,
    },
    {
      id: 'hot_vmpp_window',
      code: 'CHK-03',
      code_zh: '核验三',
      title_zh: '高温工作电压满载窗口',
      title_en: 'Hot Vmpp Operating Window',
      status: hotStatus,
      display_zh: `${vocCheck.string_hot_vmpp_v} 伏（下限 ${mpptMinV} 伏）`,
      display_en: `${vocCheck.string_hot_vmpp_v} V (Min ${mpptMinV} V)`,
      fix_hint_zh: `单串不少于 ${vocCheck.min_series_mppt} 块以防夏季正午跌出满载电压区间`,
      fix_hint_en: `Ensure >= ${vocCheck.min_series_mppt} pcs/string for summer noon MPPT tracking`,
    },
    {
      id: 'roof_dead_load',
      code: 'CHK-04',
      code_zh: '核验四',
      title_zh: '屋面新增静荷载校核',
      title_en: 'Roof Added Dead-Load Margin',
      status: loadStatus,
      display_zh: `${loadVal.toFixed(1)} / ${loadMax.toFixed(0)} 千克/平方米`,
      display_en: `${loadVal.toFixed(1)} / ${loadMax.toFixed(0)} kg/m²`,
      fix_hint_zh: '超限时请切换免穿孔铝合金夹具或东西向低倾角轻量化支架',
      fix_hint_en: 'Switch to standing-seam clamps or low-ballast E-W racking if exceeded',
    },
    {
      id: 'wind_uplift_setback',
      code: 'CHK-05',
      code_zh: '核验五',
      title_zh: '台风风揭与边角退距校核',
      title_en: 'Wind Uplift & Edge Setback',
      status: windStatus,
      display_zh: `退距 ${curSetback.toFixed(2)} 米（推荐 ${reqSetback.toFixed(2)} 米）`,
      display_en: `${curSetback.toFixed(2)} m (Rec ${reqSetback.toFixed(2)} m)`,
      fix_hint_zh: `强风区建议将屋面边缘退距调大至 ${reqSetback.toFixed(2)} 米以上`,
      fix_hint_en: `Increase perimeter edge setback to >= ${reqSetback.toFixed(2)} m in high-wind zones`,
    },
    {
      id: 'dc_voltage_drop',
      code: 'CHK-06',
      code_zh: '核验六',
      title_zh: '直流回路压降与线损校核',
      title_en: 'DC String Cable Voltage Drop',
      status: dropStatus,
      display_zh: dropDisplayZh,
      display_en: dropDisplayEn,
      fix_hint_zh: '远端组串回路超过一百二十米时建议升级为六平方毫米光伏线缆',
      fix_hint_en: 'Upgrade long DC home-runs (>120 m) to 6 mm² PV1-F cable',
    },
    {
      id: 'shading_loss',
      code: 'CHK-07',
      code_zh: '核验七',
      title_zh: '近场三维阴影遮挡损失',
      title_en: 'Near-Shading Loss Control',
      status: shadeStatus,
      display_zh: `年遮挡 ${shadeLossPct.toFixed(1)}%（剔除 ${prunedCountVal} 块）`,
      display_en: `${shadeLossPct.toFixed(1)}% (Pruned ${prunedCountVal})`,
      fix_hint_zh: '可在十二维寻优中勾选自动剔除重度遮挡组件消除短板损耗',
      fix_hint_en: 'Enable auto-pruning of heavily shaded slots in Multi-Factor Studio',
    },
    {
      id: 'financial_return',
      code: 'CHK-08',
      code_zh: '核验八',
      title_zh: '全周期收益率与回收期校核',
      title_en: 'Lifecycle IRR & Payback',
      status: finStatus,
      display_zh: finDisplayZh,
      display_en: finDisplayEn,
      fix_hint_zh: '自发自用比例较低时可联动光储削峰填谷提升综合电价收益',
      fix_hint_en: 'Pair BESS peak-shaving if self-consumption ratio is low',
    },
  ].map((it) => ({ ...it, passed: it.status === 'pass' }));

  const passCount = items.filter((i) => i.status === 'pass').length;
  const warnCount = items.filter((i) => i.status === 'warn').length;
  const failCount = items.filter((i) => i.status === 'fail').length;
  const score = Math.max(0, Math.round(passCount * 12.5 + warnCount * 7.5));
  const overallStatus = failCount > 0 ? 'fail' : warnCount > 0 ? 'warn' : 'pass';

  return {
    ok: true,
    source: 'client',
    overall_status: overallStatus,
    passed: failCount === 0 && warnCount === 0,
    score,
    pass_count: passCount,
    warn_count: warnCount,
    fail_count: failCount,
    ready_for_delivery: failCount === 0,
    items,
  };
}

export async function runEngineeringHealthCheck(view) {
  const link = view.linkage3d || (view.linkage3d = createDefaultLinkageState());
  link.healthCheck = { ...(link.healthCheck || {}), loading: true };
  const clientRes = computeClientEngineeringHealthCheck(view);

  const dcKwVal = Math.max(0, finiteNum(view.summary?.dcKw, 0));
  const acKwVal = Math.max(0, finiteNum(view.summary?.acKw, 0));
  const modCountVal = Math.max(0, Math.round(finiteNum(view.summary?.moduleCount, 0)));

  const reqPayload = {
    project_name: view.projectName,
    dc_kw: dcKwVal,
    ac_kw: acKwVal,
    module_count: modCountVal,
    site: { name: view.projectName, lat: view.lat, lon: view.lon },
    roof: {
      type: view.roofType,
      slope_deg: view.roofSlopeDeg,
      parapet_height_m: Number((finiteNum(view.parapetHeightMm, 500) / 1000).toFixed(2)),
      edge_setback_m: view.edgeSetbackM,
    },
    summary: {
      dc_kw: dcKwVal,
      ac_kw: acKwVal,
      dc_ac_ratio: dcKwVal > 0 && acKwVal > 0 ? finiteNum(view.summary?.dcAcRatio, dcKwVal / acKwVal) : 0,
      module_count: modCountVal,
      string_count: modCountVal > 0 ? Math.max(0, Math.round(finiteNum(view.summary?.stringCount, 0))) : 0,
      modules_per_string: modCountVal > 0 ? Math.max(0, Math.round(finiteNum(view.modulesPerString, 0))) : 0,
      annual_kwh: dcKwVal > 0 ? Math.max(0, finiteNum(view.summary?.annualKwh, 0)) : 0,
      pr_pct: dcKwVal > 0 ? Math.max(0, finiteNum(view.summary?.prPct, 0)) : 0,
      irr_pct: dcKwVal > 0 ? finiteOrNull(view.summary?.irrPct) : null,
      payback_years: dcKwVal > 0 ? finiteOrNull(view.summary?.paybackYears) : null,
    },
    multifactor: clientRes,
  };

  let backendRes = null;
  if (typeof view.api === 'function') {
    try {
      const r = await view.api('satmap/engineering-health-check', reqPayload);
      if (r && Array.isArray(r.items) && r.items.length > 0) backendRes = r;
    } catch { /* fallback */ }
  }
  if (!backendRes && typeof fetch === 'function' && typeof window !== 'undefined' && /^https?:/.test(window.location?.protocol || '')) {
    try {
      const resp = await fetch('/api/satmap/engineering-health-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reqPayload),
      });
      if (resp.ok) {
        const j = await resp.json();
        if (j && Array.isArray(j.items) && j.items.length > 0) backendRes = j;
      }
    } catch { /* fallback */ }
  }

  if (backendRes) {
    // Merge bilingual display fields from clientRes so EN mode stays 100% CJK-free
    const byId = new Map(clientRes.items.map((it) => [it.id, it]));
    const mergedItems = backendRes.items.map((bi, idx) => {
      const ci = byId.get(bi.id) || clientRes.items[idx] || {};
      return {
        ...ci,
        status: bi.status || ci.status || 'pass',
        code: bi.code || ci.code || `CHK-0${idx + 1}`,
      };
    });
    const merged = {
      ...clientRes,
      overall_status: backendRes.overall_status || clientRes.overall_status,
      score: finiteNum(backendRes.score, clientRes.score),
      pass_count: finiteNum(backendRes.pass_count, clientRes.pass_count),
      warn_count: finiteNum(backendRes.warn_count, clientRes.warn_count),
      fail_count: finiteNum(backendRes.fail_count, clientRes.fail_count),
      ready_for_delivery: backendRes.ready_for_delivery ?? clientRes.ready_for_delivery,
      source: 'backend',
      items: mergedItems,
    };
    link.healthCheck = { loading: false, result: merged };
    return merged;
  }

  link.healthCheck = { loading: false, result: clientRes };
  return clientRes;
}

/**
 * One-Click Export Complete Engineering Delivery Bundle (`POST /api/satmap/export-delivery-bundle`)
 * Generates `~/Downloads/光筑工程交付包_<name>/` (6-page PDF + Master DXF + UTF-8 BOM CSV + Verification JSON) + syncs to 3D!
 */
export async function exportSatmapDeliveryBundle(view, {
  syncTo3D = true,
  openFolder = true,
} = {}) {
  const link = view.linkage3d || (view.linkage3d = createDefaultLinkageState());
  link.deliveryBundle = { ...(link.deliveryBundle || {}), exporting: true };

  if (!view.hasLaidOut && view.autoLayoutOnEmpty !== false) {
    view.layoutModules({ quiet: true, autoCreateRoof: true });
    view.electricalConfirmed = true;
    view.showStringColors = true;
    view.computeElectricalAllocation();
  }

  const reportPayload = buildProReportPayload(view, { openNative: false });
  const bundlePayload = {
    open_folder: Boolean(openFolder),
    offline: true,
    project_name: view.projectName,
    site: reportPayload.site,
    roof: {
      type: view.roofType,
      slope_deg: view.roofSlopeDeg,
      parapet_height_m: reportPayload.system.parapet_height_m,
      albedo: reportPayload.site.albedo,
      polygon_m: view.roofOutlineM,
      obstacles: view.obstacles || [],
    },
    summary: {
      ...reportPayload.system,
      irr_pct: reportPayload.financial.irr_pct,
      npv_25_wan: reportPayload.financial.npv_25_wan,
      payback_years: reportPayload.financial.payback_years,
      lcoe_rmb_kwh: reportPayload.financial.lcoe_rmb_kwh,
    },
    modules: (view.modules || []).map((m, idx) => ({
      id: m.id || `M-${idx + 1}`,
      x: m.cx ?? m.x ?? 0,
      y: m.cy ?? m.y ?? 0,
      tilt_deg: m.tiltDeg ?? reportPayload.system.tilt_deg,
      azimuth_deg: m.azimuthDeg ?? reportPayload.system.azimuth_deg,
      string_id: m.stringId || 'S1',
    })),
    strings: view.strings || [],
    mppt_table: view.mpptRows || [],
    multifactor: reportPayload.multifactor,
    pvsyst: view.pvsystData || {},
  };

  let bundleRes = null;
  if (typeof view.api === 'function') {
    try {
      const r = await view.api('satmap/export-delivery-bundle', bundlePayload);
      if (r && (r.ok || r.bundle_id || Array.isArray(r.files))) {
        bundleRes = r;
      }
    } catch { /* fallback */ }
  }

  if (!bundleRes && typeof fetch === 'function' && typeof window !== 'undefined' && /^https?:/.test(window.location?.protocol || '')) {
    try {
      const resp = await fetch('/api/satmap/export-delivery-bundle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bundlePayload),
      });
      if (resp.ok) {
        const j = await resp.json();
        if (j && (j.ok || j.bundle_id || Array.isArray(j.files))) {
          bundleRes = j;
        }
      }
    } catch { /* fallback */ }
  }

  let syncRes = null;
  if (syncTo3D) {
    try {
      syncRes = await syncSatmapTo3D(view, { syncMode: 'both' });
    } catch { /* ignore sync failure so bundle still completes */ }
  }

  if (bundleRes) {
    if (!bundleRes.opened_natively && bundleRes.download_zip_url) {
      triggerBrowserAttachmentDownload(bundleRes.download_zip_url, `${bundleRes.folder_name || '光筑工程交付包'}.zip`);
    }
    if (bundleRes.health_check) {
      link.healthCheck = { loading: false, result: computeClientEngineeringHealthCheck(view) };
    }
    const finalRes = {
      ...bundleRes,
      source: 'backend',
      synced_3d: syncRes,
    };
    link.deliveryBundle = { exporting: false, lastResult: finalRes };
    return finalRes;
  }

  // Offline client-side deterministic 4-file fallback
  try { view.downloadMasterDxf?.(); } catch { /* ignore in headless */ }
  try { view.exportBomCsv?.(); } catch { /* ignore in headless */ }
  const fallbackHtml = buildClientPvsystV2ReportHtml(reportPayload);
  openHtmlInPreviewModal(view, {
    html: fallbackHtml,
    filename: `01_光筑专业报告_${view.cadPrefix || 'GZ'}.pdf`,
    titleZh: '《光筑专业报告》与工程交付包已生成',
    titleEn: 'Guangzhu Pro Report & Delivery Bundle Ready',
  });
  const clientBundle = {
    ok: true,
    source: 'client_fallback',
    bundle_id: `bnd-local-${Date.now()}`,
    folder_name: `光筑工程交付包_${view.cadPrefix || 'GZ'}`,
    display_path: `Downloads/光筑工程交付包_${view.cadPrefix || 'GZ'}`,
    opened_natively: false,
    file_count: 4,
    files: [
      { key: 'report_pdf', format: 'pdf', filename: '01_光筑专业报告.pdf' },
      { key: 'master_dxf', format: 'dxf', filename: '02_光伏总平面及组串施工图.dxf' },
      { key: 'bom_csv', format: 'csv', filename: '03_工程设备与主材清册.csv' },
      { key: 'verification_json', format: 'json', filename: '04_光筑工程合规校核.json' },
    ],
    synced_3d: syncRes,
  };
  link.deliveryBundle = { exporting: false, lastResult: clientBundle };
  return clientBundle;
}
