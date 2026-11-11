/* ============================================================================
 * 光筑 (Guangzhu) — 专业工程核心计算引擎 (pro-engineering-core.js)
 * Benchmarking full engineering depth across all three PV design pillars:
 *   1. Equipment Datasheet Physics & Standard .PAN / .OND File Import/Export
 *   2. Climate-Zone IEC 62548 / GB 50797 String Sizing & Per-String Cable Drop
 *   3. GB 55001-2021 / GB 50009-2012 Wind/Snow/Zone Uplift/Ballast/Clamp Engine
 *   4. C&I Shift-Load Coupling & Exact 25-Year Discounted Cash Flow (DCF) Solver
 *   5. 18-Item Engineering BOM & Full 16-Sheet Layered AutoCAD DXF Generator
 * ============================================================================ */

/**
 * Enrich a PV module object with full IEC 61215 / manufacturer datasheet coefficients.
 */
export function enrichModuleSpec(mod) {
  if (!mod) return null;
  const stcW = Number(mod.stc_w) || 580;
  const lenM = Number(mod.length_m) || 2.278;
  const widM = Number(mod.width_m) || 1.134;
  const areaM2 = Math.max(0.5, lenM * widM);
  const isNType = /N|TOPCon|BDV|NEG|HTD|HS/i.test(String(mod.model || ''));
  return {
    ...mod,
    stc_w: stcW,
    length_m: lenM,
    width_m: widM,
    area_m2: Number(areaM2.toFixed(3)),
    efficiency_pct: Number(mod.efficiency_pct || ((stcW / (areaM2 * 1000)) * 100).toFixed(2)),
    beta_voc_pct_c: Number.isFinite(Number(mod.beta_voc_pct_c))
      ? Number(mod.beta_voc_pct_c)
      : (isNType ? -0.25 : -0.27),
    gamma_pmax_pct_c: Number.isFinite(Number(mod.gamma_pmax_pct_c))
      ? Number(mod.gamma_pmax_pct_c)
      : (isNType ? -0.29 : -0.34),
    alpha_isc_pct_c: Number.isFinite(Number(mod.alpha_isc_pct_c))
      ? Number(mod.alpha_isc_pct_c)
      : 0.045,
    noct_c: Number(mod.noct_c) || 45,
    max_system_v: Number(mod.max_system_v) || 1500,
    weight_kg: Number(mod.weight_kg) || (lenM > 2.32 ? 33.5 : 31.8),
    cells_in_series: Number(mod.cells_in_series) || 144,
    bifaciality: Number.isFinite(Number(mod.bifaciality)) ? Number(mod.bifaciality) : 0.80,
    technology_zh: mod.technology_zh || (isNType ? 'N型双面双玻单晶组件' : '高效双面单晶组件'),
  };
}

/**
 * Enrich a string inverter object with full efficiency & MPPT full-load window specs.
 */
export function enrichInverterSpec(inv) {
  if (!inv) return null;
  const acKw = Number(inv.rated_ac_kw) || 110;
  const maxDcV = Number(inv.max_dc_v) || 1100;
  const mpptMin = Number(inv.mppt_v_min) || 200;
  const mpptMax = Number(inv.mppt_v_max) || 1000;
  return {
    ...inv,
    rated_ac_kw: acKw,
    max_dc_v: maxDcV,
    mppt_v_min: mpptMin,
    mppt_v_max: mpptMax,
    mppt_full_load_v_min: Number(inv.mppt_full_load_v_min) || (acKw >= 80 ? 520 : acKw >= 30 ? 480 : 320),
    mppt_full_load_v_max: Number(inv.mppt_full_load_v_max) || Math.min(850, mpptMax),
    max_eff_pct: Number(inv.max_eff_pct) || (acKw >= 100 ? 98.8 : 98.6),
    euro_eff_pct: Number(inv.euro_eff_pct) || (acKw >= 100 ? 98.5 : 98.2),
    nominal_ac_v: Number(inv.nominal_ac_v) || (acKw >= 150 ? 800 : 400),
  };
}

/* ============================================================================
 * 1. Standard .PAN (Module) & .OND (Inverter) Parser & Exporter
 * ============================================================================ */

function parseKeyValLines(text) {
  const kv = {};
  for (const rawLine of String(text || '').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('//') || line.startsWith('#') || line.startsWith(';')) continue;
    const eqIdx = line.indexOf('=');
    if (eqIdx <= 0) continue;
    const k = line.slice(0, eqIdx).trim();
    const v = line.slice(eqIdx + 1).trim();
    if (k && !(k in kv)) kv[k] = v;
  }
  return kv;
}

export function parsePanFile(text) {
  const kv = parseKeyValLines(text);
  const model = kv.Model || kv.CommercialName || 'Custom-PV-Module';
  const brand = kv.Manufacturer || kv.Brand || '自定义组件厂商';
  const stcW = Math.max(100, Number(kv.PNom || kv.Pmax || 580));
  const vocV = Math.max(15, Number(kv.Voc || 51.0));
  const vmpV = Math.max(12, Number(kv.Vmp || vocV * 0.83));
  const iscA = Math.max(2, Number(kv.Isc || 14.47));
  const impA = Math.max(2, Number(kv.Imp || (stcW / vmpV).toFixed(2)));
  const widthM = Math.max(0.5, Number(kv.Width || 1.134));
  const lengthM = Math.max(0.8, Number(kv.Height || kv.Length || 2.278));
  const weightKg = Math.max(8, Number(kv.Weight || 32.0));
  const maxSysV = Math.max(600, Number(kv.VMaxIEC || kv.MaxSystemV || 1500));
  const bifaciality = Math.max(0, Math.min(1, Number(kv.BifacialityFactor ?? 0.80)));
  const cells = Math.max(36, Math.round(Number(kv.NCelS || 144)));

  // Handle muVocSpec in mV/°C (standard .PAN) or BetaVocPct in %/°C
  let betaVocPct = -0.25;
  if (kv.BetaVocPct != null && Number.isFinite(Number(kv.BetaVocPct))) {
    betaVocPct = Number(kv.BetaVocPct);
  } else if (kv.muVocSpec != null && Number.isFinite(Number(kv.muVocSpec))) {
    const rawMuVoc = Number(kv.muVocSpec);
    // In .PAN files, muVocSpec is typically mV/°C (e.g. -127.5 mV/°C -> -0.25%/°C)
    betaVocPct = Math.abs(rawMuVoc) > 2.0 ? (rawMuVoc / (vocV * 10)) : rawMuVoc;
  }
  if (betaVocPct > 0) betaVocPct = -betaVocPct;

  let gammaPmaxPct = -0.29;
  if (kv.muPmpReq != null && Number.isFinite(Number(kv.muPmpReq))) {
    gammaPmaxPct = Number(kv.muPmpReq);
  } else if (kv.GammaPmaxPct != null && Number.isFinite(Number(kv.GammaPmaxPct))) {
    gammaPmaxPct = Number(kv.GammaPmaxPct);
  }
  if (gammaPmaxPct > 0) gammaPmaxPct = -gammaPmaxPct;

  let alphaIscPct = 0.045;
  if (kv.AlphaIscPct != null && Number.isFinite(Number(kv.AlphaIscPct))) {
    alphaIscPct = Number(kv.AlphaIscPct);
  } else if (kv.muISC != null && Number.isFinite(Number(kv.muISC))) {
    const rawMuIsc = Number(kv.muISC);
    // In .PAN files, muISC is typically mA/°C (e.g. 6.5 mA/°C -> +0.045%/°C)
    alphaIscPct = Math.abs(rawMuIsc) > 0.5 ? (rawMuIsc / (iscA * 10)) : rawMuIsc;
  }

  const slug = String(model).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'custom-pan';
  return enrichModuleSpec({
    id: `pan-${slug}-${Math.round(stcW)}`,
    model: /\d+\s*W/i.test(model) ? model : `${model} ${Math.round(stcW)}W`,
    brand,
    stc_w: Number(stcW.toFixed(1)),
    length_m: Number(lengthM.toFixed(3)),
    width_m: Number(widthM.toFixed(3)),
    vmp_v: Number(vmpV.toFixed(2)),
    imp_a: Number(impA.toFixed(2)),
    voc_v: Number(vocV.toFixed(2)),
    isc_a: Number(iscA.toFixed(2)),
    bifaciality: Number(bifaciality.toFixed(2)),
    beta_voc_pct_c: Number(betaVocPct.toFixed(3)),
    gamma_pmax_pct_c: Number(gammaPmaxPct.toFixed(3)),
    alpha_isc_pct_c: Number(alphaIscPct.toFixed(3)),
    max_system_v: maxSysV,
    weight_kg: Number(weightKg.toFixed(1)),
    cells_in_series: cells,
    source_format: 'PAN',
  });
}

export function serializePanFile(modInput) {
  const m = enrichModuleSpec(modInput);
  const muVocMvC = Number(((m.beta_voc_pct_c / 100) * m.voc_v * 1000).toFixed(2));
  const muIscMaC = Number(((m.alpha_isc_pct_c / 100) * m.isc_a * 1000).toFixed(2));
  return [
    'PVObject_=pvModule',
    '  Version=Guangzhu-2026.11',
    '  PVObject_Commercial=pvCommercial',
    `    Manufacturer=${m.brand}`,
    `    Model=${m.model}`,
    `    Width=${m.width_m.toFixed(3)}`,
    `    Height=${m.length_m.toFixed(3)}`,
    '    Depth=0.030',
    `    Weight=${m.weight_kg.toFixed(1)}`,
    '  End of PVObject pvCommercial',
    '  Technol=mtSiMono',
    `  NCelS=${m.cells_in_series}`,
    '  NCelP=2',
    '  NDiode=3',
    `  PNom=${m.stc_w}`,
    `  Isc=${m.isc_a}`,
    `  Voc=${m.voc_v}`,
    `  Imp=${m.imp_a}`,
    `  Vmp=${m.vmp_v}`,
    `  muISC=${muIscMaC}`,
    `  muVocSpec=${muVocMvC}`,
    `  muPmpReq=${m.gamma_pmax_pct_c}`,
    `  BetaVocPct=${m.beta_voc_pct_c}`,
    `  AlphaIscPct=${m.alpha_isc_pct_c}`,
    `  BifacialityFactor=${m.bifaciality}`,
    `  VMaxIEC=${m.max_system_v}`,
    'End of PVObject pvModule',
    '',
  ].join('\r\n');
}

export function parseOndFile(text) {
  const kv = parseKeyValLines(text);
  const model = kv.Model || kv.CommercialName || 'Custom-String-Inverter';
  const brand = kv.Manufacturer || kv.Brand || '自定义逆变器厂商';
  const ratedAcKw = Math.max(1, Number(kv.PNomConv || kv.RatedAcKw || 110));
  const mpptCount = Math.max(1, Math.round(Number(kv.NbMPPT || kv.MpptCount || 9)));
  const totalInputs = Math.max(mpptCount, Math.round(Number(kv.NbInputs || mpptCount * 2)));
  const stringsPerMppt = Math.max(1, Math.round(totalInputs / mpptCount));
  const mpptMin = Math.max(80, Number(kv.VMppMin || 200));
  const mpptMax = Math.max(mpptMin + 100, Number(kv.VMPPMax || 1000));
  const maxDcV = Math.max(mpptMax, Number(kv.VAbsMax || 1100));
  const maxMpptCurrA = Math.max(10, Number(kv.IMaxDCPerMPPT || (kv.IMaxDC ? Number(kv.IMaxDC) / mpptCount : 30)));
  const maxShortCurrA = Math.max(maxMpptCurrA, Number(kv.IScMaxPerMPPT || (kv.IScMax ? Number(kv.IScMax) / mpptCount : maxMpptCurrA * 1.35)));
  const maxEffPct = Math.min(99.5, Math.max(90, Number(kv.EfficMax || 98.7)));
  const euroEffPct = Math.min(maxEffPct, Math.max(88, Number(kv.EfficEuro || 98.4)));

  const slug = String(model).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'custom-ond';
  return enrichInverterSpec({
    id: `ond-${slug}-${Math.round(ratedAcKw)}kw`,
    model,
    brand,
    rated_ac_kw: Number(ratedAcKw.toFixed(1)),
    mppt_count: mpptCount,
    strings_per_mppt: stringsPerMppt,
    max_mppt_current_a: Number(maxMpptCurrA.toFixed(1)),
    max_short_current_a: Number(maxShortCurrA.toFixed(1)),
    mppt_v_min: Math.round(mpptMin),
    mppt_v_max: Math.round(mpptMax),
    max_dc_v: Math.round(maxDcV),
    max_eff_pct: Number(maxEffPct.toFixed(2)),
    euro_eff_pct: Number(euroEffPct.toFixed(2)),
    source_format: 'OND',
  });
}

export function serializeOndFile(invInput) {
  const inv = enrichInverterSpec(invInput);
  const nbInputs = inv.mppt_count * inv.strings_per_mppt;
  return [
    'PVObject_=pvGInverter',
    '  Version=Guangzhu-2026.11',
    '  PVObject_Commercial=pvCommercial',
    `    Manufacturer=${inv.brand}`,
    `    Model=${inv.model}`,
    '  End of PVObject pvCommercial',
    `  PNomConv=${inv.rated_ac_kw}`,
    `  PMaxOUT=${(inv.rated_ac_kw * 1.1).toFixed(1)}`,
    `  VOutConv=${inv.nominal_ac_v}`,
    `  VMppMin=${inv.mppt_v_min}`,
    `  VMPPMax=${inv.mppt_v_max}`,
    `  VAbsMax=${inv.max_dc_v}`,
    `  NbMPPT=${inv.mppt_count}`,
    `  NbInputs=${nbInputs}`,
    `  IMaxDCPerMPPT=${inv.max_mppt_current_a}`,
    `  IScMaxPerMPPT=${inv.max_short_current_a}`,
    `  IMaxDC=${(inv.max_mppt_current_a * inv.mppt_count).toFixed(1)}`,
    `  IScMax=${(inv.max_short_current_a * inv.mppt_count).toFixed(1)}`,
    `  EfficMax=${inv.max_eff_pct}`,
    `  EfficEuro=${inv.euro_eff_pct}`,
    'End of PVObject pvGInverter',
    '',
  ].join('\r\n');
}

/* ============================================================================
 * 2. Site Climate Zone Extremes & IEC 62548 / GB 50797 String & Cable Engine
 * ============================================================================ */

export function estimateSiteClimateExtremes(lat = 32.46, lon = 119.92) {
  const phi = Number(lat) || 32.46;
  const lam = Number(lon) || 119.92;
  const isCoastal =
    (lam >= 119.2 && phi >= 21.0 && phi <= 36.5) ||
    (phi <= 24.5 && lam >= 109.0 && lam <= 122.0);

  let zoneZh = '夏热冬冷地区';
  let zoneEn = 'Hot-Summer Cold-Winter Zone';
  let tMinC = -8;
  let tMaxAmbC = 38;
  let w0KnM2 = 0.45;
  let s0KnM2 = 0.35;

  if (phi >= 42.0) {
    zoneZh = '严寒地区';
    zoneEn = 'Severe Cold Zone';
    tMinC = -28;
    tMaxAmbC = 34;
    w0KnM2 = 0.55;
    s0KnM2 = 0.65;
  } else if (phi >= 35.0) {
    zoneZh = '寒冷地区';
    zoneEn = 'Cold Climate Zone';
    tMinC = phi >= 38.5 ? -18 : -10;
    tMaxAmbC = 38;
    w0KnM2 = isCoastal ? 0.55 : 0.45;
    s0KnM2 = 0.35;
  } else if (phi >= 27.0) {
    zoneZh = '夏热冬冷地区';
    zoneEn = 'Hot-Summer Cold-Winter Zone';
    tMinC = phi >= 31.0 ? -8 : -5;
    tMaxAmbC = 39;
    w0KnM2 = isCoastal ? (phi < 31.2 ? 0.60 : 0.45) : 0.40;
    s0KnM2 = phi >= 30.5 ? 0.40 : 0.30;
  } else {
    zoneZh = '夏热冬暖地区';
    zoneEn = 'Hot-Summer Warm-Winter Zone';
    tMinC = 2;
    tMaxAmbC = 39;
    w0KnM2 = isCoastal ? 0.70 : 0.45;
    s0KnM2 = 0.0;
  }

  if (lam < 103.0 && phi >= 28.0) {
    zoneZh = '高原西北干寒区';
    zoneEn = 'Plateau & Northwest Zone';
    tMinC = Math.min(tMinC, -22);
    w0KnM2 = 0.50;
    s0KnM2 = 0.40;
  }

  const tCellHotC = tMaxAmbC + 30;
  return {
    zoneZh,
    zoneEn,
    tMinC,
    tMaxAmbC,
    tCellHotC,
    w0KnM2,
    s0KnM2,
    isCoastal,
  };
}

function calcPolylineLenM(pts) {
  if (!Array.isArray(pts) || pts.length < 2) return 0;
  let sum = 0;
  for (let i = 0; i + 1 < pts.length; i++) {
    sum += Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]);
  }
  return sum;
}

export function computeStringSizingAndCables({
  module: rawMod,
  inverter: rawInv,
  modulesPerString = 18,
  lat = 32.46,
  lon = 119.92,
  customTminC = null,
  customTcellHotC = null,
  strings = [],
  dcSectionMm2 = 4,
  acMaterial = 'cu',
  acRunM = 65,
  inverterCount = 1,
} = {}) {
  const mod = enrichModuleSpec(rawMod);
  const inv = enrichInverterSpec(rawInv);
  const climate = estimateSiteClimateExtremes(lat, lon);
  const tMinC = customTminC != null && Number.isFinite(Number(customTminC)) ? Number(customTminC) : climate.tMinC;
  const tCellHotC = customTcellHotC != null && Number.isFinite(Number(customTcellHotC)) ? Number(customTcellHotC) : climate.tCellHotC;

  const betaVoc = mod.beta_voc_pct_c / 100; // negative, e.g. -0.0025 / °C
  const betaVmp = (mod.gamma_pmax_pct_c - 0.03) / 100; // Vmp temp coeff slightly steeper than Voc

  const vocSingleCold = mod.voc_v * (1 + betaVoc * (tMinC - 25));
  const vmpSingleCold = mod.vmp_v * (1 + betaVmp * (tMinC - 25));
  const vmpSingleHot = mod.vmp_v * (1 + betaVmp * (tCellHotC - 25));

  const maxAllowedSysV = Math.min(inv.max_dc_v, mod.max_system_v);
  const maxModsVoc = Math.floor(maxAllowedSysV / Math.max(1, vocSingleCold));
  const maxModsMppt = Math.floor(inv.mppt_v_max / Math.max(1, vmpSingleCold * 0.96));
  const nMax = Math.max(1, Math.min(maxModsVoc, maxModsMppt));

  const nMinMppt = Math.ceil(inv.mppt_v_min / Math.max(1, vmpSingleHot));
  const nMinFullLoad = Math.ceil(inv.mppt_full_load_v_min / Math.max(1, vmpSingleHot));
  const nMin = Math.max(4, nMinMppt);

  // Target 640~740V nominal Vmp for 1100V three-phase inverter peak efficiency
  const targetNominalV = inv.max_dc_v >= 1050 ? 680 : 580;
  let nOpt = Math.round(targetNominalV / Math.max(1, mod.vmp_v));
  nOpt = Math.max(Math.min(nMax, Math.max(nMin, nMinFullLoad)), Math.min(nMax, nOpt));

  const ns = Math.max(1, Math.round(Number(modulesPerString) || nOpt));
  const vmpStcV = Number((ns * mod.vmp_v).toFixed(1));
  const vocStcV = Number((ns * mod.voc_v).toFixed(1));
  const vocColdV = Number((ns * vocSingleCold).toFixed(1));
  const vmpHotV = Number((ns * vmpSingleHot).toFixed(1));
  const vmpColdV = Number((ns * vmpSingleCold).toFixed(1));

  const vocSafe = vocColdV <= maxAllowedSysV;
  const vmpColdSafe = vmpColdV <= inv.mppt_v_max;
  const mpptSafe = vmpHotV >= inv.mppt_v_min && vmpStcV <= inv.mppt_v_max && vmpColdSafe;
  const fullLoadSafe = vmpHotV >= inv.mppt_full_load_v_min;

  // Per-string physical DC cable routing length & ohmic voltage drop
  // Copper resistivity at 70°C: 0.0214 Ω·mm²/m
  const rhoCu70 = 0.0214;
  const secDc = Math.max(4, Number(dcSectionMm2) || 4);
  const stringDrops = [];
  let totalOneWayM = 0;

  if (Array.isArray(strings) && strings.length > 0) {
    for (const st of strings) {
      let intraM = 0;
      for (const seg of st.wireSegmentsM || []) {
        if (Array.isArray(seg) && seg.length >= 2) {
          intraM += Math.hypot(seg[1][0] - seg[0][0], seg[1][1] - seg[0][1]);
        }
      }
      if (intraM < 1) intraM = Math.max(12, (st.moduleCount || ns) * 1.25);
      const homeRunM = Math.max(6, calcPolylineLenM(st.homeRunPathM || []));
      // Total positive + negative loop length = intra-string leapfrog + 2 * homerun + 5m tray/riser slack
      const oneWayEqM = Number((intraM * 0.5 + homeRunM + 3.5).toFixed(1));
      const loopLenM = Number((intraM + 2 * homeRunM + 7.0).toFixed(1));
      const stVmp = Number(((st.moduleCount || ns) * mod.vmp_v).toFixed(1));
      const dropV = Number(((loopLenM * mod.imp_a * rhoCu70) / secDc).toFixed(2));
      const dropPct = Number(((dropV / Math.max(80, stVmp)) * 100).toFixed(2));
      totalOneWayM += oneWayEqM;
      stringDrops.push({
        id: st.id || st.shortName || 'STR',
        shortName: st.shortName || st.id || 'STR',
        slope: st.slope || 'south',
        oneWayM: oneWayEqM,
        loopLenM,
        dropV,
        dropPct,
      });
    }
  } else {
    const fallbackOneWay = 42.0;
    const loopLenM = fallbackOneWay * 2;
    const dropV = Number(((loopLenM * mod.imp_a * rhoCu70) / secDc).toFixed(2));
    const dropPct = Number(((dropV / Math.max(80, vmpStcV)) * 100).toFixed(2));
    totalOneWayM = fallbackOneWay;
    stringDrops.push({ id: 'PV1', shortName: 'PV1', slope: 'south', oneWayM: fallbackOneWay, loopLenM, dropV, dropPct });
  }

  const avgStringOneWayM = Number((totalOneWayM / Math.max(1, stringDrops.length)).toFixed(1));
  const totalDcWireMeters = Math.round(stringDrops.reduce((a, b) => a + b.loopLenM, 0));
  const avgDcDropPct = Number((stringDrops.reduce((a, b) => a + b.dropPct, 0) / Math.max(1, stringDrops.length)).toFixed(2));
  const worstString = stringDrops.reduce((w, cur) => (cur.dropPct > w.dropPct ? cur : w), stringDrops[0]);
  const recommendedDcMm2 = worstString.dropPct > 1.5 && secDc < 6 ? 6 : secDc;

  // AC Cable Sizing (ZR-YJV22 Copper vs YJLH22 Aluminum Alloy, GB 50797 ΔUac <= 3.0%)
  const acPhaseCurrA = Number(((inv.rated_ac_kw * 1000) / (1.732 * 380 * 0.99)).toFixed(1));
  const isAl = acMaterial === 'al';
  const rhoAc = isAl ? 0.0348 : 0.0214;
  // Standard cross-section table by phase current
  let acSecMm2 = 70;
  if (acPhaseCurrA > 210) acSecMm2 = isAl ? 240 : 150;
  else if (acPhaseCurrA > 155) acSecMm2 = isAl ? 185 : 120;
  else if (acPhaseCurrA > 110) acSecMm2 = isAl ? 150 : 95;
  else if (acPhaseCurrA > 70) acSecMm2 = isAl ? 95 : 50;
  else acSecMm2 = isAl ? 50 : 35;

  const acLenM = Math.max(15, Number(acRunM) || 65);
  const acDropV = (1.732 * acLenM * acPhaseCurrA * rhoAc) / acSecMm2;
  const acDropPct = Number(((acDropV / 380) * 100).toFixed(2));
  const acCableSpec = isAl
    ? `YJLH22-0.6/1kV 3×${acSecMm2}+1×${Math.round(acSecMm2 * 0.5)}`
    : `ZR-YJV22-0.6/1kV 3×${acSecMm2}+1×${Math.round(acSecMm2 * 0.5)}`;
  const totalAcMeters = Math.round(acLenM * Math.max(1, inverterCount));

  return {
    climate,
    tMinC,
    tCellHotC,
    nMin,
    nMinMppt,
    nMax,
    nOpt,
    nMinFullLoad,
    modulesPerString: ns,
    vocSingleCold,
    vmpSingleCold,
    vmpSingleHot,
    vmpStcV,
    vocStcV,
    vocColdV,
    vmpHotV,
    vmpColdV,
    maxAllowedSysV,
    vocSafe,
    vmpColdSafe,
    mpptSafe,
    fullLoadSafe,
    allWindowSafe: vocSafe && mpptSafe && ns >= nMinMppt && ns <= nMax,
    dcSectionMm2: secDc,
    recommendedDcMm2,
    avgStringOneWayM,
    totalDcWireMeters,
    avgDcDropPct,
    maxDcDropPct: worstString.dropPct,
    maxDcDropV: worstString.dropV,
    worstStringName: worstString.shortName,
    stringDrops,
    acPhaseCurrA,
    acSecMm2,
    acCableSpec,
    acDropPct,
    totalAcMeters,
  };
}

/* ============================================================================
 * 3. GB 55001-2021 / GB 50009-2012 Structural Wind / Snow / Roof Zone Engine
 * ============================================================================ */

const MU_Z_TABLE = {
  A: [[5, 1.09], [10, 1.28], [15, 1.42], [20, 1.52], [30, 1.67]],
  B: [[5, 1.00], [10, 1.00], [15, 1.13], [20, 1.23], [30, 1.39]],
  C: [[5, 0.65], [10, 0.65], [15, 0.74], [20, 0.84], [30, 0.98]],
  D: [[5, 0.51], [10, 0.51], [15, 0.51], [20, 0.57], [30, 0.69]],
};

function interpolateMuZ(heightM, cat = 'B') {
  const pts = MU_Z_TABLE[cat] || MU_Z_TABLE.B;
  const h = Math.max(3, Math.min(50, Number(heightM) || 12));
  if (h <= pts[0][0]) return pts[0][1];
  for (let i = 0; i + 1 < pts.length; i++) {
    const [h0, m0] = pts[i];
    const [h1, m1] = pts[i + 1];
    if (h >= h0 && h <= h1) {
      return m0 + ((h - h0) / (h1 - h0)) * (m1 - m0);
    }
  }
  return pts[pts.length - 1][1];
}

export function computeStructuralVerification({
  lat = 32.46,
  lon = 119.92,
  roofType = 'single_slope',
  tiltDeg = 6,
  buildingHeightM = 12,
  roughnessCategory = 'B',
  roofLoadLimitKnM2 = null,
  module: rawMod = null,
  moduleCount = 400,
  roofAreaM2 = 2400,
  purlinSpacingM = 1.5,
  customW0KnM2 = null,
  customS0KnM2 = null,
} = {}) {
  const mod = enrichModuleSpec(rawMod || {});
  const climate = estimateSiteClimateExtremes(lat, lon);
  const w0 = customW0KnM2 != null && Number.isFinite(Number(customW0KnM2)) && Number(customW0KnM2) > 0 ? Number(customW0KnM2) : climate.w0KnM2;
  const s0 = customS0KnM2 != null && Number.isFinite(Number(customS0KnM2)) && Number(customS0KnM2) >= 0 ? Number(customS0KnM2) : climate.s0KnM2;
  const rough = ['A', 'B', 'C', 'D'].includes(roughnessCategory) ? roughnessCategory : 'B';
  const muZ = Number(interpolateMuZ(buildingHeightM, rough).toFixed(2));
  const betaZ = 1.40; // Wind gust factor for roof PV structures per NB/T 10115
  const isFlat = roofType === 'flat';
  const defaultLimit = isFlat ? 1.50 : 0.45; // Concrete roof 1.50 kN/m² vs Metal purlin roof 0.45 kN/m²
  const limitKnM2 = Number.isFinite(Number(roofLoadLimitKnM2)) && Number(roofLoadLimitKnM2) > 0
    ? Number(roofLoadLimitKnM2)
    : defaultLimit;

  const betaRad = (Math.max(0, Math.min(60, Number(tiltDeg) || 6)) * Math.PI) / 180;
  const modArea = mod.area_m2;
  // Self-weight of PV module + aluminum rails/racking (kg per module)
  const rackKgPerMod = isFlat ? 11.5 : 5.2;
  const selfMassKg = mod.weight_kg + rackKgPerMod;
  const gkSelfKnM2 = (selfMassKg * 9.81) / (1000 * modArea);

  // Snow distribution factor mu_r(tilt) per GB 50009
  const tiltNum = Number(tiltDeg) || 6;
  const muSnow = tiltNum <= 25 ? 1.0 : tiltNum >= 60 ? 0.0 : (60 - tiltNum) / 35;
  const skSnowKnM2 = Number((muSnow * s0).toFixed(3));

  // Aerodynamic shape factor |mu_s| for Corner / Edge / Interior zones
  const tiltBoost = isFlat ? (0.75 + 0.025 * Math.min(30, tiltNum)) : 0.85;
  const zoneDefs = [
    { key: 'interior', labelZh: '屋面中心区', labelEn: 'Interior Zone', share: 0.68, muS: Number((0.90 * tiltBoost).toFixed(2)) },
    { key: 'edge', labelZh: '屋面边缘区', labelEn: 'Perimeter Edge Zone', share: 0.22, muS: Number((1.35 * tiltBoost).toFixed(2)) },
    { key: 'corner', labelZh: '屋面角部风吸区', labelEn: 'Corner High-Suction Zone', share: 0.10, muS: Number((1.80 * tiltBoost).toFixed(2)) },
  ];

  const frictionCoeff = 0.55; // EPDM anti-slip pad on concrete roof
  const clampAllowableKn = 3.50; // Standing-seam Al6005-T5 clamp pull-out design capacity (kN/pcs)
  const bracketDownAllowKnM2 = isFlat ? 4.20 : 2.40; // GB 55001 downward combination bearing envelope (1.3 Gk + 1.5 Sk)

  const zones = zoneDefs.map((z) => {
    const wkUpliftKnM2 = Number((betaZ * z.muS * muZ * w0).toFixed(3));
    // GB 55001-2021 uplift design load: gamma_W * W_k - 1.0 * G_k * cos(beta)
    const designUpliftNetKnM2 = Math.max(0, 1.5 * wkUpliftKnM2 - 1.0 * gkSelfKnM2 * Math.cos(betaRad));
    const zoneMods = Math.max(1, Math.round(Math.max(1, moduleCount) * z.share));

    if (isFlat) {
      // Required ballast for overturning & sliding resistance (safety factor >= 1.30)
      const reqBallastKnM2 = Math.max(
        designUpliftNetKnM2 * 1.15,
        (1.5 * wkUpliftKnM2 * Math.sin(betaRad) * 1.30) / frictionCoeff - gkSelfKnM2
      );
      const ballastKgPerMod = Math.max(20, Math.ceil(((Math.max(0, reqBallastKnM2) * modArea * 1000) / 9.81) / 5) * 5);
      const totalMassKgPerMod = selfMassKg + ballastKgPerMod;
      const projAreaM2 = Math.max(1.2, modArea * Math.cos(betaRad));
      const addedDeadKnM2 = Number(((totalMassKgPerMod * 9.81) / (1000 * projAreaM2)).toFixed(2));
      const combDownDesignKnM2 = Number((1.3 * addedDeadKnM2 + 1.5 * skSnowKnM2).toFixed(2));
      const safetyFactorOverturn = Number((((totalMassKgPerMod * 9.81) / 1000) / Math.max(0.05, wkUpliftKnM2 * modArea)).toFixed(2));
      return {
        ...z,
        zoneMods,
        wkUpliftKnM2,
        ballastKgPerMod,
        clampsPerMod: 0,
        clampTensionKn: 0,
        addedDeadKnM2,
        combDownDesignKnM2,
        safetyFactor: safetyFactorOverturn,
        zoneOk: addedDeadKnM2 <= limitKnM2 && combDownDesignKnM2 <= bracketDownAllowKnM2,
      };
    }

    // Metal Pitched Roof: Standing-seam non-penetrating clamps (4 pcs standard, 6 pcs in high-suction corner zone)
    const panelUpliftDesignKn = 1.5 * wkUpliftKnM2 * modArea;
    const clampsPerMod = (z.key === 'corner' || panelUpliftDesignKn / 4 > clampAllowableKn * 0.78) ? 6 : 4;
    const clampTensionKn = Number((panelUpliftDesignKn / clampsPerMod).toFixed(2));
    const safetyFactorClamp = Number((clampAllowableKn / Math.max(0.05, clampTensionKn)).toFixed(2));
    const addedDeadKnM2 = Number(gkSelfKnM2.toFixed(2));
    const combDownDesignKnM2 = Number((1.3 * addedDeadKnM2 + 1.5 * skSnowKnM2).toFixed(2));
    return {
      ...z,
      zoneMods,
      wkUpliftKnM2,
      ballastKgPerMod: 0,
      clampsPerMod,
      clampTensionKn,
      addedDeadKnM2,
      combDownDesignKnM2,
      safetyFactor: safetyFactorClamp,
      zoneOk: addedDeadKnM2 <= limitKnM2 && clampTensionKn <= clampAllowableKn && combDownDesignKnM2 <= bracketDownAllowKnM2,
    };
  });

  const avgAddedDeadKnM2 = Number(
    zones.reduce((acc, z) => acc + z.addedDeadKnM2 * z.share, 0).toFixed(2)
  );
  const maxZoneDeadKnM2 = Number(Math.max(...zones.map((z) => z.addedDeadKnM2)).toFixed(2));
  const totalBallastTon = isFlat
    ? Number((zones.reduce((acc, z) => acc + z.zoneMods * z.ballastKgPerMod, 0) / 1000).toFixed(1))
    : 0;
  const totalClampsCount = !isFlat
    ? zones.reduce((acc, z) => acc + z.zoneMods * z.clampsPerMod, 0)
    : 0;
  const purlinLineLoadKnM = Number(((avgAddedDeadKnM2 + skSnowKnM2) * (Number(purlinSpacingM) || 1.5)).toFixed(2));
  const cornerZone = zones[2];
  const allPass = zones.every((z) => z.zoneOk);

  return {
    standardCode: 'GB 55001-2021 / GB 50009-2012 / NB/T 10115',
    isFlat,
    roughnessCategory: rough,
    buildingHeightM: Number(buildingHeightM) || 12,
    muZ,
    w0KnM2: w0,
    s0KnM2: s0,
    skSnowKnM2,
    roofLoadLimitKnM2: limitKnM2,
    avgAddedDeadKnM2,
    maxZoneDeadKnM2,
    totalBallastTon,
    totalClampsCount,
    clampAllowableKn,
    maxClampTensionKn: cornerZone.clampTensionKn,
    cornerBallastKgPerMod: cornerZone.ballastKgPerMod,
    interiorBallastKgPerMod: zones[0].ballastKgPerMod,
    purlinLineLoadKnM,
    zones,
    allPass,
    scopeNoteZh: '本荷载与抗风揭计算为前期方案级包络校核，正式施工图出图前须结合原厂房结构竣工蓝图由注册结构工程师复核签章',
  };
}

/* ============================================================================
 * 4. C&I Shift Load Coupling & Exact 25-Year DCF Financial Engine
 * ============================================================================ */

export function computeShiftLoadSelfUse({
  shiftMode = 'double_shift', // 'single_shift' | 'double_shift' | 'continuous_24h' | 'manual'
  manualRatio = 0.82,
  dcKw = 300,
  acKw = 250,
  transformerKva = 1250,
  bessCapacityKwh = 0,
} = {}) {
  if (shiftMode === 'manual') {
    const rawManual = manualRatio !== null && manualRatio !== undefined && manualRatio !== '' && Number.isFinite(Number(manualRatio))
      ? Number(manualRatio)
      : 0.82;
    const r = Math.max(0, Math.min(1.0, rawManual));
    return {
      shiftMode,
      shiftLabelZh: '手动设定消纳率',
      shiftLabelEn: 'Manual Self-Use Share',
      baseSelfUseRatio: r,
      effectiveSelfUseRatio: r,
      exportRatio: Number((1 - r).toFixed(3)),
    };
  }

  // Average daytime industrial load relative to transformer capacity (cosPhi=0.9, typical loading factor)
  const dayLoadKw = Math.max(40, (Number(transformerKva) || 1250) * 0.56);
  const pvPeakKw = Math.max(10, Number(dcKw) * 0.76);
  const loadToPv = dayLoadKw / pvPeakKw;

  // Workday vs Weekend availability factor for solar generation window (08:00 - 17:00)
  let workdayCapture = Math.min(0.97, 0.52 + 0.42 * Math.tanh(loadToPv * 0.85));
  let weekendFactor = 0.72;
  let shiftLabelZh = '双班生产 (08:00-22:00 · 周六排产)';
  let shiftLabelEn = 'Two-Shift Production (08:00-22:00)';

  if (shiftMode === 'single_shift') {
    workdayCapture = Math.min(0.93, 0.46 + 0.40 * Math.tanh(loadToPv * 0.8));
    weekendFactor = 0.36; // Sat/Sun low base load -> weekend feed-in!
    shiftLabelZh = '单班白班制 (08:00-17:30 · 双休低荷)';
    shiftLabelEn = 'Single Day-Shift (5 Days/Wk)';
  } else if (shiftMode === 'continuous_24h') {
    workdayCapture = Math.min(0.99, 0.64 + 0.34 * Math.tanh(loadToPv * 0.95));
    weekendFactor = 0.96;
    shiftLabelZh = '三班连续生产 (24小时连续负荷)';
    shiftLabelEn = 'Continuous 24/7 Industrial Load';
  }

  const baseRatio = ((5 * workdayCapture + 2 * workdayCapture * weekendFactor) / 7);
  const bessBoost = Number(bessCapacityKwh) > 0
    ? Math.min(0.16, (Number(bessCapacityKwh) / Math.max(100, Number(dcKw) * 2.5)) * 0.14)
    : 0;
  const effRatio = Number(Math.max(0.25, Math.min(0.985, baseRatio + bessBoost)).toFixed(3));

  return {
    shiftMode,
    shiftLabelZh,
    shiftLabelEn,
    dayLoadKw: Math.round(dayLoadKw),
    baseSelfUseRatio: Number(baseRatio.toFixed(3)),
    effectiveSelfUseRatio: effRatio,
    exportRatio: Number((1 - effRatio).toFixed(3)),
  };
}

/**
 * Exact 25-Year Discounted Cash Flow (DCF) Financial Engine:
 * Solves exact IRR via bisection, NPV @ discountRate, LCOE (RMB/kWh), static & dynamic payback.
 */
export function computeFinancialDcf25Yr({
  dcKw = 300,
  annualKwhYear1 = 355800,
  capexPerW = 3.15,
  selfConsumptionRatio = 0.82,
  tariffSelfRmb = 0.78,
  tariffFeedInRmb = 0.38,
  bessPowerKw = 0,
  bessCapacityKwh = 0,
  bessCostPerKwh = 760,
  peakValleySpreadRmb = 0.65,
  discountRatePct = 6.0,
  omPerWYear = 0.045,
  inverterReplaceYear = 13,
  inverterReplacePerW = 0.15,
  lidYear1Pct = 1.0,
  linearDegPct = 0.40,
} = {}) {
  const numOr = (val, def) => (val !== null && val !== undefined && val !== '' && Number.isFinite(Number(val)) ? Number(val) : def);
  const capKw = Math.max(0, numOr(dcKw, 0));
  const y1Kwh = Math.max(0, numOr(annualKwhYear1, 0));
  if (capKw <= 0 || y1Kwh <= 0) {
    return {
      pvCapexWan: 0,
      bessCapexWan: 0,
      totalCapexWan: 0,
      weightedTariffRmb: 0,
      year1RevenueWan: 0,
      year1NetCashWan: 0,
      staticPaybackYears: null,
      dynamicPaybackYears: null,
      irrPct: null,
      npv25Wan: 0,
      lcoeRmbPerKwh: null,
      lifetimeYieldGwh: 0,
      cashflowsWan: [],
      schedule: [],
    };
  }

  const selfRatio = Math.max(0, Math.min(1, numOr(selfConsumptionRatio, 0.82)));
  const tSelf = Math.max(0, numOr(tariffSelfRmb, 0.78));
  const tFeed = Math.max(0, numOr(tariffFeedInRmb, 0.38));
  const weightedTariffRmb = Number((selfRatio * tSelf + (1 - selfRatio) * tFeed).toFixed(4));

  const pvCapexWan = Number(((capKw * Math.max(0.01, numOr(capexPerW, 3.15))) / 10).toFixed(2));
  const bessKwh = Math.max(0, numOr(bessCapacityKwh, 0));
  const bessCapexWan = Number(((bessKwh * Math.max(0, numOr(bessCostPerKwh, 760))) / 10000).toFixed(2));
  // Include BESS investment and arbitrage cashflows whenever bessKwh > 0
  const totalCapexWan = Number((pvCapexWan + bessCapexWan).toFixed(2));

  const annualOmWan = (capKw * Math.max(0, numOr(omPerWYear, 0.045))) / 10 + bessCapexWan * 0.015;
  const annualBessGainWan = bessKwh > 0
    ? (bessKwh * 0.90 * 1.80 * 0.895 * 330 * Math.max(0, numOr(peakValleySpreadRmb, 0.65))) / 10000
    : 0;

  const rDisc = Math.max(0, numOr(discountRatePct, 6.0) / 100);
  const cashflowsWan = [-totalCapexWan];
  const schedule = [];
  let cumCash = -totalCapexWan;
  let discCumCash = -totalCapexWan;
  let staticPaybackYears = null;
  let dynamicPaybackYears = null;
  let staticCrossed = false;
  let dynamicCrossed = false;
  let discCostWan = totalCapexWan;
  let discKwhSum = 0;
  let lifetimeKwh = 0;
  const degRate = Math.max(0, numOr(linearDegPct, 0.40));
  const repPerW = Math.max(0, numOr(inverterReplacePerW, 0.15));

  for (let yr = 1; yr <= 25; yr++) {
    // Year 1 already reflects first-year LID in PVsyst E_Grid; Years 2..25 apply 0.40%/yr N-type linear degradation
    const degFactor = Math.max(0.75, 1 - ((yr - 1) * degRate) / 100);
    const yrKwh = y1Kwh * degFactor;
    lifetimeKwh += yrKwh;
    const pvRevWan = (yrKwh * weightedTariffRmb) / 10000;
    const bessRevWan = annualBessGainWan * Math.max(0.72, 1 - (yr - 1) * 0.012);
    const grossRevWan = pvRevWan + bessRevWan;

    const invRepWan = yr === inverterReplaceYear ? (capKw * repPerW) / 10 : 0;
    const yrCostWan = annualOmWan + invRepWan;
    const netCashWan = grossRevWan - yrCostWan;
    cashflowsWan.push(netCashWan);

    const prevCum = cumCash;
    cumCash += netCashWan;
    if (!staticCrossed && cumCash >= 0 && netCashWan > 0) {
      staticPaybackYears = (yr - 1) + Math.abs(prevCum) / netCashWan;
      staticCrossed = true;
    }

    const df = Math.pow(1 + rDisc, yr);
    const discNet = netCashWan / df;
    const prevDiscCum = discCumCash;
    discCumCash += discNet;
    if (!dynamicCrossed && discCumCash >= 0 && discNet > 0) {
      dynamicPaybackYears = (yr - 1) + Math.abs(prevDiscCum) / discNet;
      dynamicCrossed = true;
    }

    discCostWan += yrCostWan / df;
    discKwhSum += yrKwh / df;

    schedule.push({
      year: yr,
      yieldMwh: Number((yrKwh / 1000).toFixed(1)),
      revenueWan: Number(grossRevWan.toFixed(2)),
      costWan: Number(yrCostWan.toFixed(2)),
      netCashWan: Number(netCashWan.toFixed(2)),
      cumCashWan: Number(cumCash.toFixed(2)),
      discCumCashWan: Number(discCumCash.toFixed(2)),
    });
  }

  // Exact IRR via sign-checked bisection on NPV(r) = 0; returns null when cashflows have no real root
  const evalNpv = (rate) => {
    let s = cashflowsWan[0];
    for (let t = 1; t < cashflowsWan.length; t++) {
      s += cashflowsWan[t] / Math.pow(1 + rate, t);
    }
    return s;
  };

  const hasPositiveCf = cashflowsWan.some((v) => v > 0);
  const hasNegativeCf = cashflowsWan.some((v) => v < 0);
  let irrPct = null;
  if (hasPositiveCf && hasNegativeCf) {
    let lo = -0.95;
    let hi = 5.00;
    let fLo = evalNpv(lo);
    let fHi = evalNpv(hi);
    if (Number.isFinite(fLo) && Number.isFinite(fHi) && fLo * fHi <= 0) {
      for (let iter = 0; iter < 90; iter++) {
        const mid = 0.5 * (lo + hi);
        const fMid = evalNpv(mid);
        if (fMid === 0) {
          lo = mid;
          hi = mid;
          break;
        }
        if ((fLo > 0 && fMid > 0) || (fLo < 0 && fMid < 0)) {
          lo = mid;
          fLo = fMid;
        } else {
          hi = mid;
          fHi = fMid;
        }
      }
      irrPct = Number((((lo + hi) * 0.5) * 100).toFixed(2));
    }
  }

  const npv25Wan = Number(discCumCash.toFixed(2));
  const lcoeRmbPerKwh = discKwhSum > 0 ? Number(((discCostWan * 10000) / discKwhSum).toFixed(3)) : null;

  return {
    pvCapexWan,
    bessCapexWan,
    totalCapexWan,
    selfConsumptionRatio: selfRatio,
    discountRatePct: Number((rDisc * 100).toFixed(2)),
    weightedTariffRmb,
    year1RevenueWan: schedule[0]?.revenueWan || 0,
    year1NetCashWan: schedule[0]?.netCashWan || 0,
    staticPaybackYears: staticPaybackYears != null ? Number(staticPaybackYears.toFixed(2)) : null,
    dynamicPaybackYears: dynamicPaybackYears != null ? Number(dynamicPaybackYears.toFixed(2)) : null,
    irrPct,
    npv25Wan,
    lcoeRmbPerKwh,
    lifetimeYieldGwh: Number((lifetimeKwh / 1e6).toFixed(2)),
    cashflowsWan,
    schedule,
  };
}

/* ============================================================================
 * 5. 18-Item Engineering BOM Schedule & CSV Serializer
 * ============================================================================ */

export function computeEngineeringBom({
  projectName = '分布式屋顶光伏项目',
  module: rawMod,
  inverter: rawInv,
  moduleCount = 450,
  dcKw = 261,
  acKw = 220,
  inverterCount = 2,
  stringCount = 25,
  roofType = 'single_slope',
  structural = null,
  electrical = null,
  roofPerimeterM = 220,
  bessPowerKw = 0,
  bessCapacityKwh = 0,
} = {}) {
  const mod = enrichModuleSpec(rawMod || {});
  const inv = enrichInverterSpec(rawInv || {});
  const isFlat = roofType === 'flat';
  const dcWireM = electrical?.totalDcWireMeters || Math.max(400, stringCount * 85);
  const dcSec = electrical?.recommendedDcMm2 || 4;
  const acSpec = electrical?.acCableSpec || 'ZR-YJV22-0.6/1kV 3×95+1×50';
  const acWireM = electrical?.totalAcMeters || Math.max(65, inverterCount * 65);
  const clampCount = isFlat ? moduleCount * 4 : (structural?.totalClampsCount || moduleCount * 4);
  const ballastBlocks = isFlat ? Math.ceil(((structural?.totalBallastTon || moduleCount * 0.045) * 1000) / 20) : 0;
  const railMeters = Math.round(moduleCount * mod.width_m * 2.15);
  const trayMeters = Math.round(Math.max(45, roofPerimeterM * 0.48));
  const groundFlatSteelM = Math.round(roofPerimeterM * 1.18 + stringCount * 3.5);
  const svgKvar = Math.max(30, Math.round(acKw * 0.2));

  const items = [
    { no: 1, category: '一、光伏发电核心设备', name: '高效双面双玻单晶光伏组件', spec: `${mod.brand} ${mod.model} (${mod.stc_w}Wp, 效率${mod.efficiency_pct}%)`, unit: '块', qty: moduleCount, unitPriceRmb: Number((mod.stc_w * 0.82).toFixed(0)) },
    { no: 2, category: '一、光伏发电核心设备', name: '智能组串式并网逆变器', spec: `${inv.brand} ${inv.model} (${inv.rated_ac_kw}kW, ${inv.mppt_count}路MPPT, IP66)`, unit: '台', qty: inverterCount, unitPriceRmb: Math.round(inv.rated_ac_kw * 165) },
    { no: 3, category: '二、支架与抗风固定系统', name: '高强阳极氧化铝合金导轨及纵梁', spec: 'AL6005-T5 42×48×1.8mm (含伸缩节与连接板)', unit: '米', qty: railMeters, unitPriceRmb: 26 },
    isFlat
      ? { no: 4, category: '二、支架与抗风固定系统', name: '热浸镀锌倾角三角支架与C30配重块', spec: `Q235B镀锌≥65μm + C30预制配重墩 (总重 ${structural?.totalBallastTon || 18}t + EPDM防滑垫)`, unit: '套', qty: Math.max(1, ballastBlocks), unitPriceRmb: 28 }
      : { no: 4, category: '二、支架与抗风固定系统', name: '彩钢瓦免穿孔铝合金抗风夹具及中边压块', spec: `AL6005-T5 直立锁边/角驰专用夹具 (抗拉≥3.5kN, 角部加密)`, unit: '套', qty: clampCount, unitPriceRmb: 11.5 },
    { no: 5, category: '三、交直流线缆与桥架', name: '光伏专用耐候镀锡铜芯直流线缆', spec: `PV1-F 1×${dcSec}mm² DC1500V 低烟无卤阻燃 (红/黑双色)`, unit: '米', qty: dcWireM, unitPriceRmb: dcSec >= 6 ? 6.8 : 4.6 },
    { no: 6, category: '三、交直流线缆与桥架', name: '光伏专用防水直流连接器', spec: 'MC4-Evo2 DC1500V 30A IP68 (含公母成对压接端子)', unit: '对', qty: stringCount * 3, unitPriceRmb: 14 },
    { no: 7, category: '三、交直流线缆与桥架', name: '低压交流铠装并网动力电缆', spec: acSpec, unit: '米', qty: acWireM, unitPriceRmb: acSpec.includes('YJLH') ? 78 : 132 },
    { no: 8, category: '三、交直流线缆与桥架', name: '屋面热浸镀锌耐腐密封走线槽盒', spec: '200×100×1.5mm 热浸镀锌电缆桥架 (含盖板、跨接线与支吊架)', unit: '米', qty: trayMeters, unitPriceRmb: 68 },
    { no: 9, category: '四、并网配电与继电保护', name: acKw >= 400 ? '10kV华式光伏升压箱式变电站' : '0.4kV光伏交流并网总柜', spec: acKw >= 400 ? `S13-${Math.ceil(acKw * 1.15 / 100) * 100}kVA/10.5/0.4kV` : `GGD-PV-${Math.ceil(acKw * 1.8 / 50) * 50}A 含框架断路器/刀熔/双向计量`, unit: '台', qty: 1, unitPriceRmb: acKw >= 400 ? 148000 : Math.max(18500, Math.round(acKw * 85)) },
    { no: 10, category: '四、并网配电与继电保护', name: '防逆流微机保护及孤岛联跳装置', spec: 'AM5SE-PV 双向功率监测 (100ms快速降载 + 失压脱扣 + 检有压合闸)', unit: '套', qty: 1, unitPriceRmb: 8600 },
    { no: 11, category: '四、并网配电与继电保护', name: '静止无功发生器动态补偿柜', spec: `SVG ±${svgKvar}kvar (功率因数 cosφ≥0.98, THDi≤2.8%)`, unit: '套', qty: 1, unitPriceRmb: Math.round(svgKvar * 165) },
    { no: 12, category: '四、并网配电与继电保护', name: '通讯数据采集器与气象环境监测仪', spec: 'RS485/4G智慧能源网关 + 斜面总辐射/背板温度/风速传感器', unit: '套', qty: 1, unitPriceRmb: 7200 },
    { no: 13, category: '五、防雷接地与运维安全', name: '屋面环形防雷等电位接地扁钢网', spec: '热浸镀锌扁钢 -40×4mm + 黄绿双色铜芯接地跨接线 BVR-6mm²', unit: '米', qty: groundFlatSteelM, unitPriceRmb: 19 },
    { no: 14, category: '五、防雷接地与运维安全', name: '屋面检修安全马道与清洗给水管网', spec: '玻璃钢防滑格栅走道 (宽350mm) + DN25镀锌屋面冲洗水路及水阀', unit: '米', qty: Math.round(roofPerimeterM * 0.42), unitPriceRmb: 75 },
    { no: 15, category: '六、施工安装与并网验收', name: '屋面吊装、机电安装及预防性交接试验', spec: '含组件吊装、支架安装、交直流耐压绝缘试验、电能质量检测与电网验收', unit: '瓦', qty: Math.round(dcKw * 1000), unitPriceRmb: 0.42 },
  ];

  if (Number(bessCapacityKwh) > 0) {
    items.push({
      no: 16,
      category: '七、工商业液冷储能系统',
      name: '磷酸铁锂液冷一体式工商业储能柜',
      spec: `${bessPowerKw}kW / ${bessCapacityKwh}kWh (含PCS/BMS/EMS及全氟己酮消防)`,
      unit: '瓦时',
      qty: Math.round(bessCapacityKwh * 1000),
      unitPriceRmb: 0.76,
    });
  }

  const enrichedItems = items.map((it) => {
    const subtotalWan = Number(((it.qty * it.unitPriceRmb) / 10000).toFixed(2));
    return { ...it, subtotalWan };
  });
  const totalBomWan = Number(enrichedItems.reduce((a, b) => a + b.subtotalWan, 0).toFixed(2));

  return {
    projectName,
    items: enrichedItems,
    totalBomWan,
    unitPerW: dcKw > 0 ? Number(((totalBomWan * 10) / dcKw).toFixed(2)) : 0,
  };
}

export function serializeBomCsv(bom) {
  const rows = [
    ['工程名称', bom.projectName, '设备及安装概算总计(万元)', bom.totalBomWan, '折合单瓦造价(元/Wp)', bom.unitPerW],
    [],
    ['序号', '分部分项类别', '设备/材料名称', '技术规格与工程参数', '单位', '工程数量', '综合单价(元)', '合价(万元)'],
    ...bom.items.map((it) => [
      it.no,
      it.category,
      it.name,
      it.spec,
      it.unit,
      it.qty,
      it.unitPriceRmb,
      it.subtotalWan.toFixed(2),
    ]),
    ['合计', '', '工程主材、配电保护及施工安装总计', '', '', '', '', bom.totalBomWan.toFixed(2)],
  ];
  return '\uFEFF' + rows.map((r) => r.map((c) => `"${String(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n');
}

/* ============================================================================
 * 6. Genuine Layered AutoCAD DXF Generator (Single Sheet + 16-Sheet 4x4 Master)
 * ============================================================================ */

const CAD_LAYER_DEFS = [
  ['0', 7],
  ['FRAME_BORDER', 7],
  ['TITLE_BLOCK', 3],
  ['ROOF_OUTLINE', 2],
  ['ROOF_KEEPOUT', 1],
  ['PV_MODULES', 5],
  ['STRING_WIRING', 3],
  ['HOMERUN_CABLE', 6],
  ['INVERTER_EQUIP', 2],
  ['GROUNDING_GRID', 3],
  ['CABLE_TRAY_MAIN', 4],
  ['BRACKET_STRUCT', 4],
  ['SCHEMATIC_BUS', 1],
  ['DIMENSIONS_TEXT', 7],
];

function sanitizeDxfText(str) {
  // Clean control chars while preserving UTF-8 / ASCII engineering labels
  return String(str ?? '').replace(/[\r\n\t]+/g, ' ').trim();
}

function createDxfWriter() {
  const out = [
    '0', 'SECTION',
    '2', 'HEADER',
    '9', '$ACADVER', '1', 'AC1009',
    '9', '$INSUNITS', '70', '6',
    '0', 'ENDSEC',
    '0', 'SECTION',
    '2', 'TABLES',
    '0', 'TABLE', '2', 'LAYER', '70', String(CAD_LAYER_DEFS.length),
  ];
  for (const [lname, col] of CAD_LAYER_DEFS) {
    out.push('0', 'LAYER', '2', lname, '70', '0', '62', String(col), '6', 'CONTINUOUS');
  }
  out.push('0', 'ENDTAB', '0', 'ENDSEC', '0', 'SECTION', '2', 'ENTITIES');

  const line = (x1, y1, x2, y2, layer = '0', color = 7) => {
    out.push(
      '0', 'LINE', '8', layer, '62', String(color),
      '10', Number(x1).toFixed(3), '20', Number(y1).toFixed(3), '30', '0.0',
      '11', Number(x2).toFixed(3), '21', Number(y2).toFixed(3), '31', '0.0'
    );
  };
  const rect = (x, y, w, h, layer = '0', color = 7) => {
    line(x, y, x + w, y, layer, color);
    line(x + w, y, x + w, y + h, layer, color);
    line(x + w, y + h, x, y + h, layer, color);
    line(x, y + h, x, y, layer, color);
  };
  const poly = (pts, layer = '0', color = 7, closed = true) => {
    if (!pts || pts.length < 2) return;
    const limit = closed ? pts.length : pts.length - 1;
    for (let i = 0; i < limit; i++) {
      const p0 = pts[i];
      const p1 = pts[(i + 1) % pts.length];
      line(p0[0], p0[1], p1[0], p1[1], layer, color);
    }
  };
  const circle = (cx, cy, r, layer = '0', color = 7) => {
    out.push(
      '0', 'CIRCLE', '8', layer, '62', String(color),
      '10', Number(cx).toFixed(3), '20', Number(cy).toFixed(3), '30', '0.0',
      '40', Number(r).toFixed(3)
    );
  };
  const text = (x, y, height, str, layer = 'DIMENSIONS_TEXT', color = 7) => {
    const clean = sanitizeDxfText(str);
    if (!clean) return;
    out.push(
      '0', 'TEXT', '8', layer, '62', String(color),
      '10', Number(x).toFixed(3), '20', Number(y).toFixed(3), '30', '0.0',
      '40', Number(height).toFixed(3),
      '1', clean
    );
  };
  const finish = () => {
    out.push('0', 'ENDSEC', '0', 'EOF');
    return out.join('\r\n');
  };
  return { line, rect, poly, circle, text, finish };
}

function emitSheetIntoDxf(w, sheetKey, sheetMeta, ctx, ox = 0, oy = 0) {
  const frame = ctx.frame;
  const spanU = Math.max(24, frame.widthU || 76);
  const spanV = Math.max(16, frame.heightV || 36);
  const boxW = Math.max(96, spanU + 28);
  const boxH = Math.max(66, spanV + 26);

  // Outer & Inner Engineering Drawing Frame + Title Block (lower-right corner)
  w.rect(ox, oy, boxW, boxH, 'FRAME_BORDER', 7);
  w.rect(ox + 1.2, oy + 1.2, boxW - 2.4, boxH - 2.4, 'FRAME_BORDER', 7);

  const tbW = 34;
  const tbH = 12;
  const tbX = ox + boxW - 1.2 - tbW;
  const tbY = oy + 1.2;
  w.rect(tbX, tbY, tbW, tbH, 'TITLE_BLOCK', 3);
  w.line(tbX, tbY + 4, tbX + tbW, tbY + 4, 'TITLE_BLOCK', 3);
  w.line(tbX, tbY + 8, tbX + tbW, tbY + 8, 'TITLE_BLOCK', 3);
  w.line(tbX + 22, tbY, tbX + 22, tbY + 8, 'TITLE_BLOCK', 3);

  const code = sheetMeta?.[2] || sheetKey.toUpperCase();
  const sheetTitle = sheetMeta?.[1] || sheetKey;
  w.text(ox + 3.0, oy + boxH - 4.2, 1.6, `${code}  ${sheetTitle}`, 'TITLE_BLOCK', 3);
  w.text(tbX + 1.0, tbY + 9.2, 1.05, `${ctx.cadUnit || 'Guangzhu PV Institute'} | ${ctx.cadTitle || 'PV CAD'}`, 'TITLE_BLOCK', 7);
  w.text(tbX + 1.0, tbY + 5.3, 0.95, `DC ${ctx.dcKw}kWp (${ctx.moduleCount}pcs) / AC ${ctx.acKw}kW`, 'TITLE_BLOCK', 7);
  w.text(tbX + 23.0, tbY + 5.3, 0.95, `Scale ${ctx.cadScale || '1:200'}`, 'TITLE_BLOCK', 7);
  w.text(tbX + 1.0, tbY + 1.4, 0.9, `Designer: ${ctx.cadDesigner || 'Eng'}  Audit: ${ctx.cadAuditor || 'Lead'}`, 'TITLE_BLOCK', 7);
  w.text(tbX + 23.0, tbY + 1.4, 0.95, `${ctx.cadPrefix || 'GZ'}-${code}`, 'TITLE_BLOCK', 3);

  // Coordinate mapping for roof plan sheets inside [ox+6 .. ox+boxW-8, oy+15 .. oy+boxH-7]
  const mapX = (u) => ox + 8 + (u - frame.uMin);
  const mapY = (v) => oy + 15 + (frame.vMax - v);

  const drawRoofAndModules = (withModules = true, colorByMppt = false) => {
    const roofPts = (frame.polyUV || []).map(([u, v]) => [mapX(u), mapY(v)]);
    w.poly(roofPts, 'ROOF_OUTLINE', 2, true);
    // Dimension ticks
    w.line(mapX(frame.uMin), mapY(frame.vMax) - 2.2, mapX(frame.uMax), mapY(frame.vMax) - 2.2, 'DIMENSIONS_TEXT', 7);
    w.text(mapX(frame.centerU) - 4, mapY(frame.vMax) - 3.8, 1.0, `L=${frame.widthU.toFixed(2)}m`, 'DIMENSIONS_TEXT', 7);
    w.text(mapX(frame.uMin) - 6.5, mapY(frame.centerV), 1.0, `W=${frame.heightV.toFixed(2)}m`, 'DIMENSIONS_TEXT', 7);

    for (const obs of ctx.obstacles || []) {
      const pts = (obs.polygon || []).map(([x, y]) => {
        const [u, v] = frame.toUV(x, y);
        return [mapX(u), mapY(v)];
      });
      w.poly(pts, 'ROOF_KEEPOUT', 1, true);
    }
    if (withModules) {
      for (const m of ctx.modules || []) {
        const u0 = Number.isFinite(m.u) ? m.u : frame.toUV(m.cx, m.cy)[0] - m.w / 2;
        const v0 = Number.isFinite(m.v) ? m.v : frame.toUV(m.cx, m.cy)[1] - m.h / 2;
        const col = colorByMppt ? ((m.mpptIndex || 1) % 6) + 1 : 5;
        w.poly(
          [
            [mapX(u0), mapY(v0)],
            [mapX(u0 + m.w), mapY(v0)],
            [mapX(u0 + m.w), mapY(v0 + m.h)],
            [mapX(u0), mapY(v0 + m.h)],
          ],
          'PV_MODULES',
          col,
          true
        );
      }
    }
  };

  // Distinct professional engineering CAD content for each of the 16 sheets
  if (sheetKey === 'layout') {
    drawRoofAndModules(true, false);
    w.text(ox + 6, oy + 4.5, 1.0, `Note: Setback ${ctx.edgeSetbackM}m, Tilt ${ctx.tiltDeg}deg, Pitch ${ctx.rowSpacingM}m`, 'DIMENSIONS_TEXT', 7);
  } else if (sheetKey === 'string') {
    drawRoofAndModules(true, true);
    for (const st of ctx.strings || []) {
      const col = ((st.mpptIndex || 1) % 6) + 1;
      for (const [[u0, v0], [u1, v1]] of st.wireSegmentsUV || []) {
        w.line(mapX(u0), mapY(v0), mapX(u1), mapY(v1), 'STRING_WIRING', col);
      }
      const hr = (st.homeRunPathUV || []).map(([u, v]) => [mapX(u), mapY(v)]);
      w.poly(hr, 'HOMERUN_CABLE', 6, false);
      if (st.centerUV) {
        w.text(mapX(st.centerUV[0]) - 1.2, mapY(st.centerUV[1]), 0.85, st.shortName || st.id, 'DIMENSIONS_TEXT', col);
      }
    }
    for (const invPt of ctx.inverterPointsM || []) {
      const ix = mapX(invPt.u ?? 0);
      const iy = mapY(invPt.v ?? 0);
      w.rect(ix - 1.2, iy - 0.9, 2.4, 1.8, 'INVERTER_EQUIP', 2);
      w.text(ix - 1.0, iy - 0.3, 0.8, invPt.id || 'INV', 'INVERTER_EQUIP', 2);
    }
  } else if (sheetKey === 'grounding') {
    drawRoofAndModules(false, false);
    const roofPts = (frame.polyUV || []).map(([u, v]) => [mapX(u), mapY(v)]);
    w.poly(roofPts, 'GROUNDING_GRID', 3, true);
    for (let k = 1; k <= 3; k++) {
      const vy = frame.vMin + (frame.heightV * k) / 4;
      w.line(mapX(frame.uMin), mapY(vy), mapX(frame.uMax), mapY(vy), 'GROUNDING_GRID', 3);
    }
    w.circle(mapX(frame.uMin), mapY(frame.vMin), 0.9, 'GROUNDING_GRID', 2);
    w.circle(mapX(frame.uMax), mapY(frame.vMax), 0.9, 'GROUNDING_GRID', 2);
    w.text(ox + 6, oy + 4.5, 1.0, 'Hot-Dip Galvanized Flat Steel -40x4mm Grounding Ring, R <= 4.0 Ohm', 'DIMENSIONS_TEXT', 3);
  } else if (sheetKey === 'bracket') {
    const b = ctx.bracketCfg || { h1Mm: 400, y0Mm: 1500, y1Mm: 1600, angleDeg: 15, x1Mm: 450, x2Mm: 2200 };
    // Side Elevation Detail + Front Elevation Detail
    const bx = ox + 12;
    const by = oy + 22;
    w.line(bx, by, bx + 34, by, 'BRACKET_STRUCT', 7);
    w.rect(bx + 5, by, 3.0, 1.6, 'BRACKET_STRUCT', 2);
    w.rect(bx + 22, by, 3.0, 1.6, 'BRACKET_STRUCT', 2);
    w.line(bx + 6.5, by + 1.6, bx + 6.5, by + 6.5, 'BRACKET_STRUCT', 4);
    w.line(bx + 23.5, by + 1.6, bx + 23.5, by + 13.5, 'BRACKET_STRUCT', 4);
    w.line(bx + 3.5, by + 5.2, bx + 27.0, by + 15.0, 'PV_MODULES', 5);
    w.text(bx + 4, by - 2.5, 1.1, `Side Section: H1=${b.h1Mm}mm  Y1=${b.y1Mm}mm  Tilt=${b.angleDeg}deg`, 'DIMENSIONS_TEXT', 4);
    // Front Elevation
    const fx = ox + 52;
    w.line(fx, by, fx + 34, by, 'BRACKET_STRUCT', 7);
    w.rect(fx + 2, by + 5, 30, 10, 'PV_MODULES', 5);
    w.line(fx + 6, by, fx + 6, by + 5, 'BRACKET_STRUCT', 4);
    w.line(fx + 17, by, fx + 17, by + 5, 'BRACKET_STRUCT', 4);
    w.line(fx + 28, by, fx + 28, by + 5, 'BRACKET_STRUCT', 4);
    w.text(fx + 2, by - 2.5, 1.1, `Front Elevation: X1=${b.x1Mm}mm  Span X2=${b.x2Mm}mm`, 'DIMENSIONS_TEXT', 4);
  } else if (sheetKey === 'single_line') {
    // Electrical Single-Line Diagram (SLD)
    const busY = oy + boxH - 16;
    w.line(ox + 10, busY, ox + boxW - 12, busY, 'SCHEMATIC_BUS', 1);
    w.text(ox + 10, busY + 1.6, 1.2, `0.4kV / 10kV Grid Tie Busbar (AC ${ctx.acKw}kW, SVG +- ${Math.max(30, Math.round(ctx.acKw * 0.2))}kvar)`, 'SCHEMATIC_BUS', 1);
    const nInv = Math.min(6, Math.max(1, ctx.inverterCount || 2));
    for (let i = 0; i < nInv; i++) {
      const ix = ox + 16 + i * 13;
      w.line(ix, busY, ix, busY - 12, 'STRING_WIRING', 3);
      w.rect(ix - 3.5, busY - 19, 7.0, 7.0, 'INVERTER_EQUIP', 2);
      w.text(ix - 2.8, busY - 16.2, 0.95, `INV-${i + 1}`, 'INVERTER_EQUIP', 2);
      w.line(ix, busY - 19, ix, busY - 28, 'STRING_WIRING', 5);
      w.rect(ix - 3.2, busY - 33, 6.4, 5.0, 'PV_MODULES', 5);
      w.text(ix - 2.6, busY - 31.2, 0.85, 'PV STR', 'PV_MODULES', 5);
    }
  } else if (sheetKey === 'cable_tray') {
    drawRoofAndModules(false, false);
    const mainTrayV = frame.vMin + frame.heightV * 0.16;
    w.line(mapX(frame.uMin + 1), mapY(mainTrayV), mapX(frame.uMax - 1), mapY(mainTrayV), 'CABLE_TRAY_MAIN', 4);
    for (const st of ctx.strings || []) {
      if (st.centerUV) {
        w.line(mapX(st.centerUV[0]), mapY(st.centerUV[1]), mapX(st.centerUV[0]), mapY(mainTrayV), 'HOMERUN_CABLE', 6);
      }
    }
    w.text(ox + 6, oy + 4.5, 1.0, '200x100x1.5mm Hot-Dip Galvanized Sealed Cable Tray Routing Plan', 'DIMENSIONS_TEXT', 4);
  } else if (sheetKey === 'foundation') {
    drawRoofAndModules(false, false);
    for (const m of ctx.modules || []) {
      const u0 = Number.isFinite(m.u) ? m.u : frame.toUV(m.cx, m.cy)[0] - m.w / 2;
      const v0 = Number.isFinite(m.v) ? m.v : frame.toUV(m.cx, m.cy)[1] - m.h / 2;
      w.rect(mapX(u0 + 0.15), mapY(v0 + 0.45), 0.35, 0.35, 'BRACKET_STRUCT', 2);
      w.rect(mapX(u0 + m.w - 0.5), mapY(v0 + m.h - 0.15), 0.35, 0.35, 'BRACKET_STRUCT', 2);
    }
    const stInfo = ctx.structural;
    w.text(
      ox + 6,
      oy + 4.5,
      1.0,
      `GB 55001 Wind w0=${stInfo?.w0KnM2 || 0.45}kN/m2, Snow s0=${stInfo?.s0KnM2 || 0.35}kN/m2, Dead=${stInfo?.avgAddedDeadKnM2 || 0.15}kN/m2`,
      'DIMENSIONS_TEXT',
      2
    );
  } else if (sheetKey === 'bom_schedule') {
    const bomItems = ctx.bom?.items || [];
    const tx = ox + 6;
    let ty = oy + boxH - 11;
    w.text(tx, ty, 1.20, `Engineering Bill of Materials & Drawing Index (Total Est: ${ctx.bom?.totalBomWan || 0} x10^4 RMB, ${bomItems.length} Items)`, 'TITLE_BLOCK', 3);
    ty -= 2.6;
    const rowStep = Math.min(2.5, Math.max(1.55, (boxH - 19) / Math.max(1, bomItems.length)));
    const fontH = Math.min(0.88, Math.max(0.68, rowStep * 0.42));
    for (const it of bomItems) {
      w.line(tx, ty - 0.5, ox + boxW - 8, ty - 0.5, 'FRAME_BORDER', 7);
      w.text(tx + 0.5, ty, fontH, `${String(it.no).padStart(2, '0')}  ${it.name} | ${it.spec} | ${it.qty} ${it.unit} | ${it.subtotalWan}w`, 'DIMENSIONS_TEXT', 7);
      ty = Number((ty - rowStep).toFixed(3));
    }
  } else if (sheetKey === 'clamp_detail') {
    const cx0 = ox + 22;
    const cy0 = oy + 24;
    // Standing-seam rib + non-penetrating clamp cross-section
    w.line(cx0 - 12, cy0, cx0 + 28, cy0, 'ROOF_OUTLINE', 2);
    w.line(cx0 + 4, cy0, cx0 + 4, cy0 + 8, 'ROOF_OUTLINE', 2);
    w.circle(cx0 + 4, cy0 + 8.8, 0.9, 'ROOF_OUTLINE', 2);
    w.rect(cx0 + 1.5, cy0 + 6.2, 5.0, 6.0, 'BRACKET_STRUCT', 4);
    w.rect(cx0 - 4, cy0 + 12.2, 22.0, 3.2, 'BRACKET_STRUCT', 3);
    w.rect(cx0 - 6, cy0 + 15.4, 26.0, 1.8, 'PV_MODULES', 5);
    w.text(cx0 - 10, cy0 - 4, 1.1, `AL6005-T5 Standing-Seam Clamp Detail (Pull-out >= 3.50kN, Design=${ctx.structural?.maxClampTensionKn || 1.25}kN)`, 'DIMENSIONS_TEXT', 4);
  } else if (sheetKey === 'ac_cabinet') {
    const gx = ox + 14;
    const gy = oy + 20;
    w.rect(gx, gy, 28, 32, 'INVERTER_EQUIP', 2);
    w.line(gx + 14, gy + 30, gx + 14, gy + 4, 'SCHEMATIC_BUS', 1);
    w.circle(gx + 14, gy + 22, 2.2, 'TITLE_BLOCK', 3);
    w.circle(gx + 14, gy + 13, 2.2, 'TITLE_BLOCK', 4);
    w.rect(gx + 36, gy + 8, 28, 20, 'CABLE_TRAY_MAIN', 4);
    w.line(gx + 28, gy + 18, gx + 36, gy + 18, 'HOMERUN_CABLE', 6);
    w.text(gx, gy - 3, 1.05, 'Grid-Tie Cabinet Secondary Protection, Anti-Backflow (100ms) & RS485/4G SCADA', 'DIMENSIONS_TEXT', 3);
  } else if (sheetKey === 'om_walkway') {
    drawRoofAndModules(true, false);
    w.line(mapX(frame.uMin + 1), mapY(frame.centerV), mapX(frame.uMax - 1), mapY(frame.centerV), 'BRACKET_STRUCT', 4);
    w.line(mapX(frame.centerU), mapY(frame.vMin + 1), mapX(frame.centerU), mapY(frame.vMax - 1), 'BRACKET_STRUCT', 4);
    w.circle(mapX(frame.uMin + 2), mapY(frame.centerV), 0.8, 'CABLE_TRAY_MAIN', 3);
    w.circle(mapX(frame.uMax - 2), mapY(frame.centerV), 0.8, 'CABLE_TRAY_MAIN', 3);
    w.text(ox + 6, oy + 4.5, 1.0, '350mm FRP Anti-Slip O&M Walkway + DN25 Galvanized Water Cleaning Loop', 'DIMENSIONS_TEXT', 4);
  } else if (sheetKey === 'bess_storage') {
    const bx = ox + 14;
    const by = oy + 24;
    const bessCap = Math.max(0, Number(ctx.bessCapacityKwh) || 0);
    const bessPow = Math.max(0, Number(ctx.bessPowerKw) || 0);
    w.rect(bx, by, 22, 16, 'PV_MODULES', 5);
    w.text(bx + 2, by + 8, 1.1, `PV Array ${ctx.dcKw}kWp`, 'PV_MODULES', 5);
    if (bessCap > 0 && bessPow > 0) {
      w.rect(bx + 32, by, 24, 16, 'INVERTER_EQUIP', 3);
      w.text(bx + 34, by + 8, 1.1, `BESS ${bessPow}kW/${bessCap}kWh`, 'INVERTER_EQUIP', 3);
      w.line(bx + 22, by + 8, bx + 32, by + 8, 'SCHEMATIC_BUS', 1);
      w.line(bx + 56, by + 8, bx + 72, by + 8, 'SCHEMATIC_BUS', 1);
      w.circle(bx + 75, by + 8, 3.0, 'SCHEMATIC_BUS', 2);
      w.text(bx, by - 5, 1.05, 'PV + Liquid-Cooled LFP BESS Coupled Peak-Shaving & EMS Topology', 'DIMENSIONS_TEXT', 3);
    } else {
      w.rect(bx + 32, by, 28, 16, 'FRAME_BORDER', 7);
      w.text(bx + 33.2, by + 8, 0.92, 'No BESS Configured (0kWh)', 'DIMENSIONS_TEXT', 7);
      w.line(bx + 22, by + 8, bx + 32, by + 8, 'SCHEMATIC_BUS', 1);
      w.line(bx + 60, by + 8, bx + 72, by + 8, 'SCHEMATIC_BUS', 1);
      w.circle(bx + 75, by + 8, 3.0, 'SCHEMATIC_BUS', 2);
      w.text(bx, by - 5, 1.05, 'Pure Grid-Tied PV Topology (BESS Interface Reserved, 0kW/0kWh)', 'DIMENSIONS_TEXT', 3);
    }
  } else {
    // Perspective / Birdseye / 8760h Energy Balance / Near-Shading & 25-Yr DCF Summary Sheets
    drawRoofAndModules(true, sheetKey === 'pvsyst_diagram');
    const irrLabel = ctx.irrPct != null ? `${ctx.irrPct}%` : 'N/A';
    w.text(
      ox + 6,
      oy + 4.5,
      1.0,
      `Annual Yield ${(ctx.annualKwh / 10000).toFixed(2)}x10^4 kWh | PR ${ctx.prPct}% | IRR ${irrLabel} | NPV25 ${ctx.npv25Wan}w | LCOE ${ctx.lcoeRmbPerKwh ?? 'N/A'} RMB/kWh`,
      'DIMENSIONS_TEXT',
      3
    );
  }

  return { width: boxW, height: boxH };
}

export function buildProSheetDxf(sheetKey, sheetMeta, ctx) {
  const writer = createDxfWriter();
  emitSheetIntoDxf(writer, sheetKey, sheetMeta, ctx, 0, 0);
  return writer.finish();
}

export function buildMaster16SheetsDxf(allSheets, ctx) {
  const writer = createDxfWriter();
  const spanU = Math.max(24, ctx.frame?.widthU || 76);
  const spanV = Math.max(16, ctx.frame?.heightV || 36);
  const stepX = Math.max(96, spanU + 28) + 14;
  const stepY = Math.max(66, spanV + 26) + 14;

  allSheets.forEach((sMeta, idx) => {
    const col = idx % 4;
    const row = Math.floor(idx / 4);
    const ox = col * stepX;
    const oy = (3 - row) * stepY;
    emitSheetIntoDxf(writer, sMeta[0], sMeta, ctx, ox, oy);
  });
  return writer.finish();
}
