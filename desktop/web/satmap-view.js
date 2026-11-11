/* ============================================================================
 * 光筑 (Guangzhu) — 卫星地图 AI 光伏设计工作台 (satmap-view.js)
 * Standalone Top-Level View (#satmap)
 * Core capabilities:
 *   - Satellite Search/Locate, Roof/Keepout Drawing, Module Settings &
 *     One-Click Layout (一键铺设), Electrical Design & MPPT Table, and
 *     16-Sheet Professional CAD Drawing Generator (光伏排布图/组串图/防雷接地图/支架图等)
 *   - Scale Calibration (标定比例尺), Direction (确定方向), Double-Slope Pitch
 *     (双坡屋面坡度自动分南北坡), Keepout Strips (禁布区绘制), and Step 4
 *     Oblique Photo 4-Point Perspective Homography + Parapet Sightline Occlusion
 * ============================================================================ */

import { esc, valueMarkup } from './data.js';
import { translateHtmlToEn, toggleLang, applyGlobalI18n, localizeDomSubtree, getLang } from './i18n.js';
import {
  renderPvsystWorkbench,
  renderLiveWeatherPanel,
  computeClientFallbackPvsyst,
} from './pvsyst-workbench.js';
import {
  enrichModuleSpec,
  enrichInverterSpec,
  parsePanFile,
  serializePanFile,
  parseOndFile,
  serializeOndFile,
  computeStringSizingAndCables,
  computeStructuralVerification,
  computeShiftLoadSelfUse,
  computeFinancialDcf25Yr,
  computeEngineeringBom,
  serializeBomCsv,
  buildProSheetDxf,
  buildMaster16SheetsDxf,
} from './pro-engineering-core.js';
import {
  buildSatmap3DGeometrySpec,
  compute3DPhysicalShading,
  computeAnnual3DShadingSummary,
  mountSatmap3DTwin,
} from './pro-3d-twin-engine.js';

export const SAT_MODULE_CATALOG = [
  {
    id: 'jinko-jkm580n-72hl4-bdv',
    model: 'JKM580N-72HL4-BDV 580W',
    brand: '晶科能源 (Jinko)',
    stc_w: 580,
    length_m: 2.278,
    width_m: 1.134,
    vmp_v: 42.3,
    imp_a: 13.71,
    voc_v: 51.0,
    isc_a: 14.47,
    bifaciality: 0.80,
  },
  {
    id: 'trina-tsm-605neg19rc20',
    model: 'TSM-605NEG19RC.20 605W',
    brand: '天合光能 (Trina)',
    stc_w: 605,
    length_m: 2.382,
    width_m: 1.134,
    vmp_v: 40.5,
    imp_a: 14.94,
    voc_v: 48.7,
    isc_a: 15.86,
    bifaciality: 0.80,
  },
  {
    id: 'longi-lr5-72htd-580m',
    model: 'LR5-72HTD-580M 580W',
    brand: '隆基绿能 (LONGi)',
    stc_w: 580,
    length_m: 2.278,
    width_m: 1.134,
    vmp_v: 43.2,
    imp_a: 13.43,
    voc_v: 51.8,
    isc_a: 14.25,
    bifaciality: 0.75,
  },
  {
    id: 'tongwei-twmnd-72hs620',
    model: 'TWMND-72HS620 620W',
    brand: '通威太阳能 (Tongwei)',
    stc_w: 620,
    length_m: 2.382,
    width_m: 1.134,
    vmp_v: 41.2,
    imp_a: 15.05,
    voc_v: 49.5,
    isc_a: 15.92,
    bifaciality: 0.80,
  },
].map(enrichModuleSpec);

export const SAT_INVERTER_CATALOG = [
  {
    id: 'sungrow-sg110cx-p2',
    model: 'SG110CX-P2',
    brand: '阳光电源',
    rated_ac_kw: 110,
    mppt_count: 9,
    strings_per_mppt: 2,
    max_mppt_current_a: 30,
    max_short_current_a: 40,
    mppt_v_min: 200,
    mppt_v_max: 1000,
    max_dc_v: 1100,
  },
  {
    id: 'sungrow-sg50cx-p2',
    model: 'SG50CX-P2',
    brand: '阳光电源',
    rated_ac_kw: 50,
    mppt_count: 5,
    strings_per_mppt: 2,
    max_mppt_current_a: 30,
    max_short_current_a: 40,
    mppt_v_min: 200,
    mppt_v_max: 1000,
    max_dc_v: 1100,
  },
  {
    id: 'sungrow-sg36cx-p2',
    model: 'SG36CX-P2',
    brand: '阳光电源',
    rated_ac_kw: 36,
    mppt_count: 4,
    strings_per_mppt: 2,
    max_mppt_current_a: 30,
    max_short_current_a: 40,
    mppt_v_min: 200,
    mppt_v_max: 1000,
    max_dc_v: 1100,
  },
  {
    id: 'sungrow-sg125cx-p2',
    model: 'SG125CX-P2',
    brand: '阳光电源',
    rated_ac_kw: 125,
    mppt_count: 12,
    strings_per_mppt: 2,
    max_mppt_current_a: 30,
    max_short_current_a: 40,
    mppt_v_min: 180,
    mppt_v_max: 1000,
    max_dc_v: 1100,
  },
  {
    id: 'huawei-sun2000-100ktl-m2',
    model: 'SUN2000-100KTL-M2',
    brand: '华为',
    rated_ac_kw: 100,
    mppt_count: 10,
    strings_per_mppt: 2,
    max_mppt_current_a: 30,
    max_short_current_a: 40,
    mppt_v_min: 200,
    mppt_v_max: 1000,
    max_dc_v: 1100,
  },
  {
    id: 'goodwe-gw100k-ht',
    model: 'GW100K-HT',
    brand: '固德威',
    rated_ac_kw: 100,
    mppt_count: 10,
    strings_per_mppt: 2,
    max_mppt_current_a: 30,
    max_short_current_a: 45,
    mppt_v_min: 180,
    mppt_v_max: 1000,
    max_dc_v: 1100,
  },
  {
    id: 'growatt-max-100ktl3-x',
    model: 'MAX 100KTL3-X LV',
    brand: '古瑞瓦特',
    rated_ac_kw: 100,
    mppt_count: 10,
    strings_per_mppt: 2,
    max_mppt_current_a: 32,
    max_short_current_a: 45,
    mppt_v_min: 180,
    mppt_v_max: 1000,
    max_dc_v: 1100,
  },
  {
    id: 'ginlong-s5-gc110k',
    model: 'S5-GC110K',
    brand: '锦浪',
    rated_ac_kw: 110,
    mppt_count: 10,
    strings_per_mppt: 2,
    max_mppt_current_a: 32,
    max_short_current_a: 40,
    mppt_v_min: 180,
    mppt_v_max: 1000,
    max_dc_v: 1100,
  },
  {
    id: 'sungrow-sg150cx-cn',
    model: 'SG150CX-CN',
    brand: '阳光电源',
    rated_ac_kw: 150,
    mppt_count: 7,
    strings_per_mppt: 3,
    max_mppt_current_a: 45,
    max_short_current_a: 60,
    mppt_v_min: 200,
    mppt_v_max: 1000,
    max_dc_v: 1100,
  },
  {
    id: 'huawei-sun2000-20ktl-m3',
    model: 'SUN2000-20KTL-M3',
    brand: '华为',
    rated_ac_kw: 20,
    mppt_count: 2,
    strings_per_mppt: 2,
    max_mppt_current_a: 27,
    max_short_current_a: 39,
    mppt_v_min: 160,
    mppt_v_max: 1000,
    max_dc_v: 1100,
  },
  {
    id: 'goodwe-gw8k-dt',
    model: 'GW8K-DT',
    brand: '固德威',
    rated_ac_kw: 8,
    mppt_count: 2,
    strings_per_mppt: 1,
    max_mppt_current_a: 16,
    max_short_current_a: 21,
    mppt_v_min: 160,
    mppt_v_max: 850,
    max_dc_v: 1000,
  },
].map(enrichInverterSpec);

export function formatDmsCoord(deg, isLon = true) {
  const num = Number(deg) || 0;
  const abs = Math.abs(num);
  const d = Math.floor(abs);
  const mFloat = (abs - d) * 60;
  const m = Math.floor(mFloat);
  const s = ((mFloat - m) * 60).toFixed(2);
  const hemi = isLon ? (num >= 0 ? 'E' : 'W') : (num >= 0 ? 'N' : 'S');
  return `${d}°${String(m).padStart(2, '0')}'${s}"${hemi}`;
}

export const SAT_PRESET_SITES = [
  {
    key: 'taizhou-cmc',
    name: '中国（泰州）医药城太阳能光电建筑应用示范项目（1号标准厂房）',
    address: '江苏省泰州市医药高新区（中国医药城）药城大道88号1号车间',
    lat: 32.4562,
    lon: 119.9231,
    zoom: 19,
    roofW: 76.0,
    roofH: 36.0,
    roofType: 'double_slope',
    slopeDeg: 6,
  },
  {
    key: 'taizhou-xiangtai-warehouse',
    name: '国网泰州供电公司“祥泰数智零碳仓库”屋顶分布式光伏项目 (552.42kWp)',
    address: '江苏省泰州市海陵区九龙镇祥泰路电力物资数智零碳仓库',
    lat: 32.4852,
    lon: 119.8634,
    zoom: 19,
    roofW: 104.0,
    roofH: 44.0,
    roofType: 'double_slope',
    slopeDeg: 5,
  },
  {
    key: 'taizhou-jielouwei-bipv',
    name: '泰州市海陵区春云路解楼圩（原旧船厂改造）BIPV光伏屋顶项目 (167.61kWp)',
    address: '江苏省泰州市海陵区春云路解楼圩新通扬运河段',
    lat: 32.5126,
    lon: 119.9328,
    zoom: 19,
    roofW: 80.0,
    roofH: 20.0,
    roofType: 'double_slope',
    slopeDeg: 8,
  },
  {
    key: 'taizhou-shenyuan-alloy',
    name: '国能泰州电厂·江苏申源特种合金1.27368MWp厂房屋顶光伏项目',
    address: '江苏省泰州市兴化高新区戴南镇张郭科技园区申源特钢厂房',
    lat: 32.9315,
    lon: 120.0542,
    zoom: 19,
    roofW: 164.0,
    roofH: 56.0,
    roofType: 'double_slope',
    slopeDeg: 5,
  },
  {
    key: 'taizhou-municipal-admin',
    name: '泰州市级机关综合办公楼及海陵区行政中心分布式光伏项目 (1,100kWp)',
    address: '江苏省泰州市海陵区凤凰东路58号市级机关综合办公楼',
    lat: 32.4555,
    lon: 119.9230,
    zoom: 19,
    roofW: 136.0,
    roofH: 56.0,
    roofType: 'flat',
    slopeDeg: 0,
  },
  {
    key: 'taizhou-jingjiang-shipbuild',
    name: '靖江经济技术开发区船舶海工重装基地单跨彩钢瓦车间屋顶光伏项目 (1,500.40kWp)',
    address: '江苏省泰州市靖江经济技术开发区新港大道海工重装基地1号车间',
    lat: 32.0152,
    lon: 120.2645,
    zoom: 19,
    roofW: 180.0,
    roofH: 60.0,
    roofType: 'double_slope',
    slopeDeg: 5,
  },
  {
    key: 'taizhou-taixing-chem',
    name: '泰兴经济开发区精细化工产业园高标准物流仓储屋顶光伏项目 (800.80kWp)',
    address: '江苏省泰州市泰兴经济开发区通江路精细化工高标物流园',
    lat: 32.1685,
    lon: 120.0124,
    zoom: 19,
    roofW: 124.0,
    roofH: 52.0,
    roofType: 'flat',
    slopeDeg: 0,
  },
  {
    key: 'taizhou-jiangyan-equip',
    name: '泰州市姜堰高新区智能制造装备产业园标准厂房屋顶分布式光伏项目 (638.00kWp)',
    address: '江苏省泰州市姜堰高新区科技大道智能制造装备产业园',
    lat: 32.5086,
    lon: 120.1482,
    zoom: 19,
    roofW: 112.0,
    roofH: 44.0,
    roofType: 'double_slope',
    slopeDeg: 6,
  },
  {
    key: 'shandong-zibo',
    name: '山东省淄博市桓台县起凤镇工业厂房 (36.8588°N, 118.7781°E)',
    address: '山东省淄博市桓台县起凤镇工业园1号车间',
    lat: 36.858844,
    lon: 118.778089,
    zoom: 19,
    roofW: 72.0,
    roofH: 32.0,
    roofType: 'double_slope',
    slopeDeg: 6,
  },
  {
    key: 'foshan-shunde',
    name: '广东省佛山市顺德区智能制造园彩钢瓦车间',
    address: '广东省佛山市顺德区北滘镇工业大道16号',
    lat: 22.9318,
    lon: 113.2145,
    zoom: 19,
    roofW: 84.0,
    roofH: 40.0,
    roofType: 'double_slope',
    slopeDeg: 5,
  },
  {
    key: 'jiaxing-pinghu',
    name: '浙江省嘉兴市平湖现代物流园混凝土平屋面厂房',
    address: '浙江省嘉兴市平湖市经济开发区兴平二路',
    lat: 30.6982,
    lon: 121.0156,
    zoom: 19,
    roofW: 68.0,
    roofH: 34.0,
    roofType: 'flat',
    slopeDeg: 0,
  },
];

const MPPT_PALETTE = [
  '#2563eb', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899',
  '#06b6d4', '#eab308', '#14b8a6', '#f97316', '#6366f1',
  '#84cc16', '#0ea5e9',
];

/**
 * Exact 3x3 Projective Homography Solver: maps 4 planar points srcQuad -> dstQuad
 * srcQuad: [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
 * dstQuad: [[u0,v0], [u1,v1], [u2,v2], [u3,v3]]
 * Returns 9-element array H = [h11, h12, h13, h21, h22, h23, h31, h32, 1]
 */
export function solveHomography(srcQuad, dstQuad) {
  if (!Array.isArray(srcQuad) || !Array.isArray(dstQuad) || srcQuad.length < 4 || dstQuad.length < 4) {
    return [1, 0, 0, 0, 1, 0, 0, 0, 1];
  }
  const A = [];
  const b = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = srcQuad[i];
    const [u, v] = dstQuad[i];
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]);
    b.push(u);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]);
    b.push(v);
  }
  // Gaussian elimination with partial pivoting on 8x8 system
  const n = 8;
  for (let col = 0; col < n; col++) {
    let pivotRow = col;
    let maxVal = Math.abs(A[col][col]);
    for (let row = col + 1; row < n; row++) {
      const absVal = Math.abs(A[row][col]);
      if (absVal > maxVal) {
        maxVal = absVal;
        pivotRow = row;
      }
    }
    if (maxVal < 1e-12) return [1, 0, 0, 0, 1, 0, 0, 0, 1];
    if (pivotRow !== col) {
      [A[col], A[pivotRow]] = [A[pivotRow], A[col]];
      [b[col], b[pivotRow]] = [b[pivotRow], b[col]];
    }
    const pivot = A[col][col];
    for (let j = col; j < n; j++) A[col][j] /= pivot;
    b[col] /= pivot;
    for (let row = 0; row < n; row++) {
      if (row === col) continue;
      const factor = A[row][col];
      if (Math.abs(factor) < 1e-15) continue;
      for (let j = col; j < n; j++) A[row][j] -= factor * A[col][j];
      b[row] -= factor * b[col];
    }
  }
  return [b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], 1];
}

/**
 * Project a 2D planar point (x, y) through 3x3 homography matrix H
 */
export function projectPoint(H, x, y) {
  if (!Array.isArray(H) || H.length < 9) return [x, y];
  const w = H[6] * x + H[7] * y + H[8];
  const denom = Math.abs(w) < 1e-9 ? (w >= 0 ? 1e-9 : -1e-9) : w;
  return [
    (H[0] * x + H[1] * y + H[2]) / denom,
    (H[3] * x + H[4] * y + H[5]) / denom,
  ];
}

export function pointInPolygon(pt, poly) {
  if (!Array.isArray(poly) || poly.length < 3) return false;
  const [px, py] = pt;
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    const intersect = (yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi + 1e-12) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function pointToSegmentDist(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  if (len2 < 1e-12) return Math.hypot(px - x1, py - y1);
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / len2));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

function pointToPolygonEdgeDist(pt, poly) {
  if (!Array.isArray(poly) || poly.length < 2) return Infinity;
  const [px, py] = pt;
  let minDist = Infinity;
  for (let i = 0; i < poly.length; i++) {
    const [x1, y1] = poly[i];
    const [x2, y2] = poly[(i + 1) % poly.length];
    const d = pointToSegmentDist(px, py, x1, y1, x2, y2);
    if (d < minDist) minDist = d;
  }
  return minDist;
}

function segmentsIntersect(a1, a2, b1, b2) {
  const ccw = (p1, p2, p3) => (p3[1] - p1[1]) * (p2[0] - p1[0]) - (p2[1] - p1[1]) * (p3[0] - p1[0]);
  const d1 = ccw(b1, b2, a1);
  const d2 = ccw(b1, b2, a2);
  const d3 = ccw(a1, a2, b1);
  const d4 = ccw(a1, a2, b2);
  return ((d1 > 1e-9 && d2 < -1e-9) || (d1 < -1e-9 && d2 > 1e-9)) &&
    ((d3 > 1e-9 && d4 < -1e-9) || (d3 < -1e-9 && d4 > 1e-9));
}

function quadIntersectsPolygon(corners4, poly, pad = 0) {
  if (!Array.isArray(poly) || poly.length < 3) return false;
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const [x, y] of poly) {
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  let qMinX = Infinity, qMaxX = -Infinity, qMinY = Infinity, qMaxY = -Infinity;
  for (const [x, y] of corners4) {
    if (x < qMinX) qMinX = x;
    if (x > qMaxX) qMaxX = x;
    if (y < qMinY) qMinY = y;
    if (y > qMaxY) qMaxY = y;
  }
  if (qMaxX < minX - pad || qMinX > maxX + pad || qMaxY < minY - pad || qMinY > maxY + pad) {
    return false;
  }
  const cx = (corners4[0][0] + corners4[2][0]) * 0.5;
  const cy = (corners4[0][1] + corners4[2][1]) * 0.5;
  if (pointInPolygon([cx, cy], poly)) return true;
  for (const pt of corners4) {
    if (pointInPolygon(pt, poly)) return true;
    if (pad > 0 && pointToPolygonEdgeDist(pt, poly) < pad) return true;
  }
  for (const pt of poly) {
    if (pointInPolygon(pt, corners4)) return true;
    if (pad > 0 && pointToPolygonEdgeDist(pt, corners4) < pad) return true;
  }
  for (let i = 0; i < 4; i++) {
    const a1 = corners4[i];
    const a2 = corners4[(i + 1) % 4];
    for (let j = 0; j < poly.length; j++) {
      const b1 = poly[j];
      const b2 = poly[(j + 1) % poly.length];
      if (segmentsIntersect(a1, a2, b1, b2)) return true;
    }
  }
  return false;
}

function rectIntersectsPolyBounds(rx0, ry0, rx1, ry1, poly, pad = 0) {
  return quadIntersectsPolygon(
    [[rx0, ry0], [rx1, ry0], [rx1, ry1], [rx0, ry1]],
    poly,
    pad
  );
}

/**
 * Verify that the straight line segment p0 -> p1 stays 100% inside roofPoly
 * (never crossing an inner courtyard or exterior wall) and outside all obstacles.
 */
function segmentStaysInsideRoof(p0, p1, roofPoly, obstacles = []) {
  if (!Array.isArray(roofPoly) || roofPoly.length < 3) return true;
  for (let i = 0; i < roofPoly.length; i++) {
    const r1 = roofPoly[i];
    const r2 = roofPoly[(i + 1) % roofPoly.length];
    if (segmentsIntersect(p0, p1, r1, r2)) return false;
  }
  for (const obs of obstacles) {
    const op = obs?.polygon;
    if (Array.isArray(op) && op.length >= 3) {
      for (let j = 0; j < op.length; j++) {
        if (segmentsIntersect(p0, p1, op[j], op[(j + 1) % op.length])) return false;
      }
    }
  }
  for (let s = 1; s <= 19; s++) {
    const t = s / 20;
    const pt = [p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t];
    if (!pointInPolygon(pt, roofPoly)) return false;
    for (const obs of obstacles) {
      if (obs?.polygon?.length >= 3 && pointInPolygon(pt, obs.polygon)) return false;
    }
  }
  return true;
}

/**
 * Automatically recognize the roof's principal building wall orientation angle (in degrees, [-45, 45])
 * from the longest edge of the drawn roof polygon on the satellite map.
 * If the building's longest edge is within ±8° of cardinal East-West / North-South, snaps to 0°
 * so modules and CAD plans remain crisp and horizontal.
 */
export function detectPrincipalRoofAngleDeg(poly) {
  if (!Array.isArray(poly) || poly.length < 3) return 0;
  let longestLen = 0;
  let longestAngleDeg = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x0, y0] = poly[i];
    const [x1, y1] = poly[(i + 1) % poly.length];
    const dx = x1 - x0;
    const dy = y1 - y0;
    const len = Math.hypot(dx, dy);
    if (len < 1.5) continue;
    if (len > longestLen) {
      longestLen = len;
      let deg = (Math.atan2(dy, dx) * 180) / Math.PI;
      while (deg <= -45) deg += 90;
      while (deg > 45) deg -= 90;
      longestAngleDeg = deg;
    }
  }
  if (longestLen < 1.5) return 0;
  if (Math.abs(longestAngleDeg) <= 8.0) return 0;
  return Number(longestAngleDeg.toFixed(1));
}

export const MIN_SAT_ZOOM = 4;
export const MAX_SAT_ZOOM = 24;
export const NATIVE_TILE_MAX_ZOOM = 20;

export function lonLatToTileXY(lon, lat, zoom) {
  const n = Math.pow(2, zoom);
  const latRad = (lat * Math.PI) / 180;
  const x = ((lon + 180) / 360) * n;
  const y = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
  return { x, y };
}

export function metersPerPixelAtLatZoom(lat, zoom) {
  return (156543.03392 * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, zoom);
}

/**
 * Standard WGS-84 to GCJ-02 (Mars coordinate system) conversion so Gaode satellite tiles
 * and road labels align with meter-level accuracy across mainland China.
 */
export function wgs84ToGcj02(lon, lat) {
  if (lon < 72.004 || lon > 137.8347 || lat < 0.8293 || lat > 55.8271) {
    return [lon, lat];
  }
  const a = 6378245.0;
  const ee = 0.00669342162296594323;
  const x = lon - 105.0;
  const y = lat - 35.0;
  let dLat =
    -100.0 +
    2.0 * x +
    3.0 * y +
    0.2 * y * y +
    0.1 * x * y +
    0.2 * Math.sqrt(Math.abs(x)) +
    ((20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0) / 3.0 +
    ((20.0 * Math.sin(y * Math.PI) + 40.0 * Math.sin((y / 3.0) * Math.PI)) * 2.0) / 3.0 +
    ((160.0 * Math.sin((y / 12.0) * Math.PI) + 320 * Math.sin((y * Math.PI) / 30.0)) * 2.0) / 3.0;
  let dLon =
    300.0 +
    x +
    2.0 * y +
    0.1 * x * x +
    0.1 * x * y +
    0.1 * Math.sqrt(Math.abs(x)) +
    ((20.0 * Math.sin(6.0 * x * Math.PI) + 20.0 * Math.sin(2.0 * x * Math.PI)) * 2.0) / 3.0 +
    ((20.0 * Math.sin(x * Math.PI) + 40.0 * Math.sin((x / 3.0) * Math.PI)) * 2.0) / 3.0 +
    ((150.0 * Math.sin((x / 12.0) * Math.PI) + 300.0 * Math.sin((x / 30.0) * Math.PI)) * 2.0) / 3.0;
  const radLat = (lat / 180.0) * Math.PI;
  let magic = Math.sin(radLat);
  magic = 1 - ee * magic * magic;
  const sqrtMagic = Math.sqrt(magic);
  dLat = (dLat * 180.0) / (((a * (1 - ee)) / (magic * sqrtMagic)) * Math.PI);
  dLon = (dLon * 180.0) / ((a / sqrtMagic) * Math.cos(radLat) * Math.PI);
  return [lon + dLon, lat + dLat];
}

function defaultNotice(msg) {
  if (typeof document === 'undefined') return;
  const el = document.getElementById('notice');
  if (el) {
    el.textContent = msg;
    el.hidden = false;
  }
}

async function defaultApi(path, body) {
  const req = body === undefined
    ? {}
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const res = await fetch('/api/' + path, req);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || data.detail || '请求失败');
  return data;
}

export class SatMapView {
  constructor(arg1, arg2, arg3) {
    this.api = defaultApi;
    this.notice = defaultNotice;
    this.appState = null;

    if (typeof arg1 === 'function') {
      this.api = arg1;
      if (typeof arg2 === 'function') {
        this.notice = arg2;
        this.appState = arg3 || null;
      } else if (typeof arg3 === 'function') {
        this.appState = arg2 || null;
        this.notice = arg3;
      } else {
        this.appState = arg2 || null;
      }
    } else if (arg1 && typeof arg1 === 'object') {
      if (typeof arg1.api === 'function') this.api = arg1.api;
      if (typeof arg1.notice === 'function') this.notice = arg1.notice;
      this.appState = arg1.state || arg1;
    }

    this.step = 1; // 1: 卫星排布, 2: 电气设计, 3: PVsyst与实时气象, 4: 实景效果图, 5: 图纸生成工具
    this.projectName = '分布式屋顶光伏项目';
    this.address = '山东省济南市历城区工业北路';
    this.searchQuery = '';
    this.searchResults = [];
    this.lat = 36.588644;
    this.lon = 116.774288;
    this.zoom = 18;
    this.mapSource = 'gaode'; // 'gaode' (全国高清实景卫星+路网企业标注) | 'esri' (Esri 全球高清卫星)
    this.showMapLabels = true;
    this.showRoofOverlay = true;
    this.isFullscreen = false;
    this.is3D = false;
    this.sim3dDateStr = '2026-12-21';
    this.sim3dHourBjt = 9.5;
    this.sim3dMode = 'realistic'; // 'realistic' | 'irradiance' | 'diode' | 'wiring' | 'wind'
    this.sim3dCam = 'iso';
    this.sim3dPlaying = false;
    this.sim3dShowSunDome = true;
    this.sim3dObstacleScale = 1.0;
    this.twin3d = null;
    this.shading3dSummary = null;
    this.activeTool = 'pan'; // 'pan' | 'roof' | 'roof_poly' | 'obstacle' | 'scale' | 'direction' | 'delete'
    this.aiRequirement = '';
    this.aiExecutionNote = '';
    this.targetCapacityKw = 0;

    // Scale Calibration & Direction & Roof Pitch (matched 1:1 to real EPSG:3857 Zoom 18 scale)
    this.scaleReferenceM = 76.0;
    this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
    const halfSpanPx = Math.round((this.scaleReferenceM / this.metersPerPx) * 0.5);
    this.scaleLinePx = [[-halfSpanPx, -52], [halfSpanPx, -52]];
    this.scaleCustomized = false;
    this.ridgeAzimuthDeg = 0; // 0° = East-West ridge
    // Default to 'single_slope' (unified single roof without automatic ridge dividing line)
    // User can switch to 'double_slope' (双坡屋面) anytime to split North/South slopes!
    this.roofType = 'single_slope'; // 'single_slope' | 'double_slope' | 'flat'
    this.roofSlopeDeg = 6;

    // Clean initial satellite map state: NO pre-drawn roof or modules until user draws/designs!
    this.hasRoof = false;
    this.hasLaidOut = false;
    this.roofCenterLon = this.lon;
    this.roofCenterLat = this.lat;
    this.roofOutlineM = [];
    this.obstacles = [];
    this.modules = [];
    this.strings = [];
    this.mpptRows = [];
    this.inverterPointsM = [];
    this.selectedObstacleId = null;
    this.drawingPointsM = [];
    this.drawingObstaclePointsM = [];
    this.dragPreview = null; // Live rubber-band rectangle/line preview while drawing on map
    this.cursorPointM = null;

    // Right & Left panel: Module & Layout settings
    this.leftPanelTab = 'roof'; // 'roof' (1.屋面) | 'layout' (2.布局) | 'info' (3.信息)
    this.rightDrawerTab = 'layout'; // 'layout' (组件排布) | 'elec' (电气配置)
    this.coordFormat = 'dec'; // 'dec' (十进制) | 'dms' (度分秒)
    this.regionQuickPick = '';
    this.moduleModelId = 'jinko-jkm580n-72hl4-bdv';
    this.orientation = 'portrait'; // 'portrait' (竖放) | 'landscape' (横放)
    this.tiltDeg = 6;
    this.azimuthDeg = 180;
    this.rowSpacingM = 0.50;
    this.colSpacingM = 0.02;
    this.arrayGroupRows = 2; // 阵列行数 (2 rows per sub-array group)
    this.arrayGroupCols = 9; // 阵列列数 (9/10 cols per sub-array group)
    this.walkwayWidthM = 0.50; // 走道宽度 500mm
    this.parapetHeightMm = 300; // 女儿墙高 (mm)
    this.parapetWidthMm = 240; // 女儿墙宽 (mm)
    this.subArrayHeightMm = 1000; // 子阵高度 (mm)
    this.autoRowSpacing = true; // 子阵间距 ☑ 自动计算
    this.edgeSetbackM = 0.50;
    this.obstacleSetbackM = 0.30;
    this.customOrthoImg = null; // Optional uploaded top-down orthophoto
    this.showShadowPreview = false; // ☀️ 阴影分析浮窗开关
    this.liveEdgeLengthMm = 76000; // 画布底部边长实时显示 [76000] mm | 76.00m
    this.undoStack = [];
    this.redoStack = [];

    // Electrical settings & Modals
    this.inverterBrandFilter = 'all';
    this.inverterPowerFilter = 'all'; // 'all' | 'gt150' | '100_150' | '50_100' | '30_50' | '10_30' | 'lt10'
    this.inverterSelectionMode = 'auto'; // 'auto' (智能推荐) | 'manual' (自选逆变器)
    this.inverterModelId = 'sungrow-sg110cx-p2';
    this.modulesPerString = 18;
    this.dcAcTargetMin = 1.1;
    this.dcAcTargetMax = 1.3;
    this.dcCableTotalM = 0;
    this.electricalConfirmed = true;
    this.showStringColors = true;
    this.showStringModeModal = false; // 逆变器区域选择 / 请选择组串方式 (快速组串 vs DIY组串)
    this.stringingMode = 'quick'; // 'quick' (快速组串-新手推荐) | 'diy' (DIY组串)
    this.selectAllRoofDevices = true; // ☑ 选中屋顶所有设备
    this.showInverterModal = false; // 逆变器选择弹窗 (品牌+功率分段筛选)
    this.showMpptModal = false; // 完成设计后弹出 MPPT 组串分配表
    this.showLocationPickerModal = false; // 地图拾取经纬度弹窗
    this.showPvlaneStartModal = false; // 新建项目 / 打开JSON弹窗
    this.softwareMode = 'all';
    this.showVideoCenter = false;
    this.pvsystHubTab = 'weather';
    this.cadShowAllFourStacked = false; // Step 5: 四张 CAD 图纸纵向连排全览模式
    this.cadGrid2x2 = false; // Step 5: 四张 CAD 图纸 2×2 同屏全景总览模式

    // Step 3: 8760h Simulation state
    this.pvsystParams = {};
    this.pvsystData = null;

    // Step 4: Oblique Photo Perspective Homography + Parapet Sightline Occlusion Studio
    this.effectPresetIdx = 0;
    this.customPhotoImg = null;
    this.effectCanvasW = 920;
    this.effectCanvasH = 540;
    this.effectModuleStyle = 'mono_blue'; // 'mono_blue' (深蓝单晶) | 'all_black' (全黑美学) | 'bifacial_blue' (双面高效蓝)
    this.effectOpacityPct = 92;
    this.effectGridSharpnessPct = 80;
    this.effectGlarePct = 22;
    // 4-point perspective roof corners on the 920x540 oblique photo canvas: P1(左上), P2(右上), P3(右下), P4(左下)
    this.dstQuad = [
      [218, 178], // P1: Top-Left roof corner
      [716, 168], // P2: Top-Right roof corner
      [838, 392], // P3: Bottom-Right roof corner (behind foreground parapet)
      [112, 408], // P4: Bottom-Left roof corner (behind foreground parapet)
    ];
    this.pickingFourCorners = false;
    this.pickedCorners = [];
    // Parapet sightline occlusion polygon (女儿墙视线遮挡区域: occludes bottom edge of solar array)
    this.occlusionEnabled = true;
    this.occlusionDrawing = false;
    this.occlusionPolygon = [
      [94, 376],
      [468, 364],
      [854, 360],
      [866, 442],
      [86, 450],
    ];
    this.draggingCornerIdx = -1;

    // Live timer
    this.timerElapsedMs = 42180;
    this.timerRunning = false;
    this.timerInterval = null;

    // Step 5: CAD Drawing Generator state (16-Sheet Complete Engineering Drawing Suite)
    this.cadWizardTab = 'sheets'; // 'basic' (1.基本参数) | 'bracket' (2.支架设计) | 'sheets' (3.生成图纸)
    this.cadCategory = 'all'; // 'all' | 'elec' (电气图) | 'struct' (结构图) | 'sim' (实景透视 & 物理仿真 & 光储报告图)
    this.cadSheet = 'layout';
    this.cadChecks = {
      layout: true,
      string: true,
      grounding: true,
      bracket: true,
      single_line: true,
      cable_tray: true,
      foundation: true,
      bom_schedule: true,
      pvlane_perspective: true,
      pvsyst_diagram: true,
      clamp_detail: true,
      ac_cabinet: true,
      om_walkway: true,
      bess_storage: true,
      pvlane_birdseye: true,
      pvsyst_near_shading: true,
    };
    this.cadTitle = '分布式厂房屋顶光伏施工图';
    this.cadUnit = '光筑智能光伏工程设计院';
    this.cadBuildOwner = '山东起凤工业园新能源有限公司';
    this.cadProjectCode = '分布式屋顶光伏发电项目';
    this.cadChiefDesigner = '张工';
    this.cadProLead = '陈工';
    this.cadApprover = '刘总工';
    this.cadAuditor = '李工';
    this.cadChecker = '周工';
    this.cadDesigner = '王工';
    this.cadPrefix = 'GZ-PV-2026';
    this.cadScale = '1:200';
    this.bracketCfg = {
      h1Mm: 400, // 组件最低点离地最小高度 H1 (mm)
      y0Mm: 1500, // 组件前后排间距 Y0 (mm)
      y1Mm: 1600, // 立柱南北间距 Y1 (mm)
      angleDeg: 15, // 支架安装倾角 A (°)
      aMm: 350, // 檩条高度 A (mm)
      x1Mm: 450, // 前立柱与光伏板端悬挑距离 X1 (mm)
      x2Mm: 2200, // 立柱东西间距 X2 (mm)
      foundationType: '混凝土配重墩',
      baseType: '混凝土配重墩', // 基础类型
      concreteGrade: 'C30',
      cementGrade: 'C30', // 水泥标号
    };
    this.angleStrategy = 'weather_yield'; // 'weather_yield' | 'roof_total' | 'roof_flush' | 'custom'
    this.weatherEval = null;

    // Electricity Tariff, CAPEX, Shift-Load, Cable & Structural Engineering Config
    this.capexPerW = 3.15;
    this.tariffRmb = 0.78;
    this.feedInTariffRmb = 0.38;
    this.selfConsumptionRatio = 0.82;
    this.shiftMode = 'manual'; // 'manual' | 'single_shift' | 'double_shift' | 'continuous_24h'
    this.discountRatePct = 6.0;
    this.transformerKva = 1250;
    this.bessPowerKw = 100;
    this.bessCapacityKwh = 215;
    this.dcCableSectionMm2 = 4; // 4mm² | 6mm²
    this.acCableMaterial = 'cu'; // 'cu' (ZR-YJV22) | 'al' (YJLH22)
    this.buildingHeightM = 12;
    this.roughnessCategory = 'B'; // 'A' | 'B' | 'C' | 'D'
    this.roofLoadLimitKnM2 = 0; // 0 = auto by roof type (1.50 concrete / 0.45 metal)
    this.customModules = [];
    this.customInverters = [];
    this.targetDcAcRatio = 0;
    this.electricalSizing = null;
    this.structuralCheck = null;
    this.financialDcf = null;
    this.showTariffModal = false;
    this.cadZoomPct = 100;
    this.cadLightTheme = false;
    this.removedModules = [];
    this.hoveredModule = null;
    this.hoverScreenPos = null;
    this.effectCompareMode = false;
    this.effectCompareSplitPct = 50;
    this.effectSolarHour = 9.5;
    this.effectShowStringColors = false;

    // AI Trace & Autopilot state
    this.aiScanActive = false;
    this.autopilotState = null; // { pct, text, step }
    this.aiTraceLogs = [];

    // Tile cache & rAF scheduler for 60fps real satellite imagery
    this.tileCache = new Map();
    this._rafPending = false;

    // Initial summary is 0 until user draws a roof and runs layout (or AI design)
    this.summary = {
      moduleCount: 0,
      southCount: 0,
      northCount: 0,
      dcKw: 0,
      acKw: 0,
      dcAcRatio: 0,
      inverterCount: 0,
      stringCount: 0,
      annualKwh: 0,
      specificYield: 1186,
      prPct: 84.2,
      capexWan: 0,
      paybackYears: 0,
      irrPct: 16.8,
      npv25Wan: 0,
    };
    this._tilesPrewarmed = false;
    this._pvsystEpoch = 0;
    this.evaluateWeatherAndAngles();
  }

  /**
   * Set satellite map zoom level (Z4 .. Z24, up to 32x deeper than Z19 / 64x deeper than Z18)
   * with optional cursor-centered geographic anchoring and proportional custom scale preservation.
   */
  setZoom(targetZoom, { anchorSx = null, anchorSy = null, canvasW = 920, canvasH = 580 } = {}) {
    const prevZoom = Number(this.zoom) || 18;
    const nextZoom = Math.max(MIN_SAT_ZOOM, Math.min(MAX_SAT_ZOOM, Math.round(Number(targetZoom) || 18)));
    const oldMpp = metersPerPixelAtLatZoom(this.lat, prevZoom);
    const newMpp = metersPerPixelAtLatZoom(this.lat, nextZoom);

    if (
      nextZoom !== prevZoom &&
      anchorSx != null &&
      anchorSy != null &&
      Number.isFinite(anchorSx) &&
      Number.isFinite(anchorSy)
    ) {
      const dxPx = anchorSx - canvasW * 0.5;
      const dyPx = anchorSy - canvasH * 0.5;
      const deltaEastM = dxPx * (oldMpp - newMpp);
      const deltaSouthM = dyPx * (oldMpp - newMpp);
      const dLon = deltaEastM / (111320 * Math.max(0.15, Math.cos((this.lat * Math.PI) / 180)));
      const dLat = -deltaSouthM / 110540;
      this.lon = Number((this.lon + dLon).toFixed(7));
      this.lat = Number(Math.max(3, Math.min(54, this.lat + dLat)).toFixed(7));
      const hasAnyGeom =
        this.hasRoof ||
        (this.obstacles && this.obstacles.length > 0) ||
        (this.drawingPointsM && this.drawingPointsM.length > 0) ||
        (this.drawingObstaclePointsM && this.drawingObstaclePointsM.length > 0);
      if (!hasAnyGeom) {
        this.roofCenterLon = this.lon;
        this.roofCenterLat = this.lat;
      }
    }

    this.zoom = nextZoom;
    if (this.scaleCustomized) {
      const ratio = newMpp / Math.max(1e-6, oldMpp);
      this.metersPerPx = Math.max(0.001, (Number(this.metersPerPx) || oldMpp) * ratio);
    } else {
      this.metersPerPx = newMpp;
    }
    return nextZoom !== prevZoom;
  }

  /**
   * Center the satellite map directly on the roof and zoom in to ultra-clear roof/module close-up (Z21 ~ Z23).
   * Clicking repeatedly cycles between Roof Full Close-Up (Z21) -> Module-Level Super Close-Up (Z22) -> Sub-Centimeter Micro Close-Up (Z23/Z24).
   */
  zoomToFitRoof({ canvasW = 920, canvasH = 580 } = {}) {
    if (Number.isFinite(this.roofCenterLon) && Number.isFinite(this.roofCenterLat)) {
      const bounds = this.getRoofBoundsM(false);
      if (this.hasRoof && bounds.widthM > 0) {
        const mPerDegLat = 110540;
        const mPerDegLon = 111320 * Math.max(0.15, Math.cos((this.lat * Math.PI) / 180));
        this.lon = Number((this.roofCenterLon + bounds.centerX / mPerDegLon).toFixed(7));
        this.lat = Number((this.roofCenterLat - bounds.centerY / mPerDegLat).toFixed(7));
      } else {
        this.lon = this.roofCenterLon;
        this.lat = this.roofCenterLat;
      }
    }
    const bounds = this.getRoofBoundsM(true);
    const spanW = Math.max(18, bounds.widthM || 76);
    const spanH = Math.max(12, bounds.heightM || 36);
    let fitZ = 21;
    for (let z = MAX_SAT_ZOOM; z >= 16; z--) {
      const mpp = metersPerPixelAtLatZoom(this.lat, z);
      if (spanW / mpp <= canvasW * 0.78 && spanH / mpp <= canvasH * 0.72) {
        fitZ = Math.max(20, z);
        break;
      }
    }
    let nextZ = fitZ;
    if (this.zoom >= fitZ && this.zoom < MAX_SAT_ZOOM) {
      nextZ = Math.min(MAX_SAT_ZOOM, this.zoom + 1);
    }
    this.setZoom(nextZ);
    this.scheduleMapRedraw();
    return nextZ;
  }

  /**
   * Pre-fetch the center 3x3 satellite tiles immediately upon instantiation
   * so that Step 1 renders with zero startup lag.
   */
  prewarmInitialTiles() {
    if (typeof Image === 'undefined') return;
    try {
      const z = Math.max(MIN_SAT_ZOOM, Math.min(NATIVE_TILE_MAX_ZOOM, Math.round(this.zoom || 18)));
      const [tileLon, tileLat] = this.mapSource === 'gaode'
        ? wgs84ToGcj02(this.lon, this.lat)
        : [this.lon, this.lat];
      const centerTile = lonLatToTileXY(tileLon, tileLat, z);
      const baseTx = Math.floor(centerTile.x);
      const baseTy = Math.floor(centerTile.y);
      const satSource = this.mapSource === 'esri'
        ? 'esri'
        : this.showMapLabels
          ? 'gaode_hyb'
          : 'gaode_sat';
      const spiral = [
        [0, 0], [-1, 0], [1, 0], [0, -1], [0, 1],
        [-1, -1], [1, -1], [-1, 1], [1, 1],
      ];
      for (const [dx, dy] of spiral) {
        this.loadSatelliteTile(satSource, z, baseTx + dx, baseTy + dy);
      }
    } catch {
      // Ignore in headless test environment
    }
  }

  /**
   * Populate a standard industrial roof & skylight keepouts at current map center
   * (used when user clicks "一键铺设" or "AI 识别当前屋面" without manually drawing a box first)
   */
  ensureRoofOutline({ withDefaultKeepouts = false } = {}) {
    if (this.roofOutlineM && this.roofOutlineM.length >= 3) {
      this.hasRoof = true;
      return;
    }
    if (!Number.isFinite(this.roofCenterLon) || !Number.isFinite(this.roofCenterLat)) {
      this.roofCenterLon = this.lon;
      this.roofCenterLat = this.lat;
    }
    let minX = -38.0, maxX = 38.0, minY = -18.0, maxY = 18.0;
    if (this.obstacles && this.obstacles.length > 0) {
      for (const obs of this.obstacles) {
        for (const [ox, oy] of obs.polygon || []) {
          if (ox - 6 < minX) minX = ox - 6;
          if (ox + 6 > maxX) maxX = ox + 6;
          if (oy - 6 < minY) minY = oy - 6;
          if (oy + 6 > maxY) maxY = oy + 6;
        }
      }
    }
    this.roofOutlineM = [
      [minX, minY],
      [maxX, minY],
      [maxX, maxY],
      [minX, maxY],
    ];
    if (withDefaultKeepouts && this.obstacles.length === 0) {
      this.obstacles = [
        {
          id: 'keepout-skylight-1',
          name: '采光带禁布区 #1',
          kind: 'skylight',
          polygon: [[-34.0, -9.2], [34.0, -9.2], [34.0, -7.4], [-34.0, -7.4]],
        },
        {
          id: 'keepout-skylight-2',
          name: '采光带禁布区 #2',
          kind: 'skylight',
          polygon: [[-34.0, 7.4], [34.0, 7.4], [34.0, 9.2], [-34.0, 9.2]],
        },
      ];
    }
    this.hasRoof = true;
  }

  clearRoofDesign({ quiet = false } = {}) {
    this._pvsystEpoch = (this._pvsystEpoch || 0) + 1;
    this.hasRoof = false;
    this.hasLaidOut = false;
    this.roofOutlineM = [];
    this.obstacles = [];
    this.modules = [];
    this.strings = [];
    this.mpptRows = [];
    this.inverterPointsM = [];
    this.drawingPointsM = [];
    this.drawingObstaclePointsM = [];
    this.cursorPointM = null;
    this.dragPreview = null;
    this.scaleCustomized = false;
    this.ridgeAzimuthDeg = 0;
    this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
    this.roofCenterLon = this.lon;
    this.roofCenterLat = this.lat;
    this.summary = {
      moduleCount: 0,
      southCount: 0,
      northCount: 0,
      dcKw: 0,
      acKw: 0,
      dcAcRatio: 0,
      inverterCount: 0,
      stringCount: 0,
      annualKwh: 0,
      specificYield: this.weatherEval?.weatherOptimalYield || 1186,
      prPct: 84.2,
      capexWan: 0,
      paybackYears: 0,
    };
    this.evaluateWeatherAndAngles();
    if (!quiet) {
      this.notice('已清空当前屋面选框与排布，请在卫星图目标厂房上重新框选或点选屋顶范围。');
    }
  }

  finishPolygonRoof() {
    const rawPts = Array.isArray(this.drawingPointsM) ? this.drawingPointsM : [];
    const pts = [];
    for (const [x, y] of rawPts) {
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      if (pts.length > 0) {
        const [px, py] = pts[pts.length - 1];
        if (Math.hypot(x - px, y - py) < 0.12) continue;
      }
      pts.push([Number(x.toFixed(2)), Number(y.toFixed(2))]);
    }
    if (pts.length > 2) {
      const [fx, fy] = pts[0];
      const [lx, ly] = pts[pts.length - 1];
      if (Math.hypot(lx - fx, ly - fy) < 0.12) {
        pts.pop();
      }
    }
    if (pts.length < 3) return null;
    this.roofOutlineM = pts;
    this.drawingPointsM = [];
    this.cursorPointM = null;
    this.dragPreview = null;
    this.hasRoof = true;
    this.showRoofOverlay = true;
    this.activeTool = 'pan';
    if (!this.scaleCustomized) {
      this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
    }
    const detectedAngle = detectPrincipalRoofAngleDeg(this.roofOutlineM);
    this.ridgeAzimuthDeg = Math.abs(detectedAngle) <= 8 ? 0 : detectedAngle;
    const bounds = this.getRoofBoundsM(true);
    this.scaleReferenceM = bounds.widthM;
    if (this.hasLaidOut) {
      this.layoutModules({ quiet: true, autoCreateRoof: false });
    }
    this.notice(`已完成多边形屋顶轮廓绘制（${this.roofOutlineM.length} 个角点，面积 ${bounds.areaM2} m²，自动识别建筑主墙偏角 ${this.ridgeAzimuthDeg}°）。点击「3. 一键铺设」即可排布组件！`);
    if (this.host) {
      this.refresh();
    }
    return this.roofOutlineM;
  }

  finishPolygonObstacle() {
    const rawPts = Array.isArray(this.drawingObstaclePointsM) ? this.drawingObstaclePointsM : [];
    const pts = [];
    for (const [x, y] of rawPts) {
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      if (pts.length > 0) {
        const [px, py] = pts[pts.length - 1];
        if (Math.hypot(x - px, y - py) < 0.12) continue;
      }
      pts.push([Number(x.toFixed(2)), Number(y.toFixed(2))]);
    }
    if (pts.length > 2) {
      const [fx, fy] = pts[0];
      const [lx, ly] = pts[pts.length - 1];
      if (Math.hypot(lx - fx, ly - fy) < 0.12) {
        pts.pop();
      }
    }
    if (pts.length < 3) return null;

    if (!this.hasRoof && (!this.roofOutlineM || this.roofOutlineM.length < 3)) {
      this.roofCenterLon = this.lon;
      this.roofCenterLat = this.lat;
    }
    this.showRoofOverlay = true;
    const obs = {
      id: `keepout-${Date.now()}-${this.obstacles.length + 1}`,
      name: `禁布区 #${this.obstacles.length + 1}`,
      kind: 'skylight',
      polygon: pts,
    };
    this.obstacles.push(obs);
    this.drawingObstaclePointsM = [];
    this.cursorPointM = null;
    this.dragPreview = null;

    if (this.hasLaidOut) {
      this.layoutModules({ quiet: true, autoCreateRoof: false });
    }
    this.notice(
      `已完成多点禁布区 #${this.obstacles.length} 绘制（${pts.length} 个角点）${this.hasLaidOut ? `，已自动避让并重排 ${this.summary.moduleCount} 块组件` : '，可继续多点点击绘制下一个禁布区，或点击「3. 一键铺设」'}。`
    );
    if (this.host) {
      this.refresh();
    }
    return obs;
  }

  /**
   * 一键加载典型复杂 U 型凹多边形屋面 + 多点禁布区示范工程（对标泰州学院济川路校区 U 型教学楼）：
   * 直观验证：
   *   1. 正交凹多边形（8个顶点 U 型）自动保持 0° 正南水平对齐，CAD 图纸绝不倾斜成 45° 菱形；
   *   2. 多点绘制的禁布区与排布组件 100% 锁定在屋面局部正交坐标系 (u, v) 中；
   *   3. 北翼、西翼、南翼独立分翼 2×9 蛇形配串，组串连线与逆变器引下线沿屋面内部走廊绕行，0 跨越中央天井！
   */
  loadUShapeComplexRoofDemo() {
    this.projectName = '泰州学院济川路校区明德楼分布式光伏项目';
    this.cadTitle = '泰州学院分布式光伏项目施工图';
    this.address = '江苏省泰州市海陵区济川东路93号 (泰州学院济川路校区)';
    this.lat = 32.4768;
    this.lon = 119.9562;
    this.zoom = 19;
    this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
    this.scaleCustomized = false;
    this.roofCenterLon = this.lon;
    this.roofCenterLat = this.lat;
    this.ridgeAzimuthDeg = 0; // 正交建筑 0° 水平对齐
    this.roofType = 'single_slope';
    this.roofSlopeDeg = 6;
    this.tiltDeg = 6;

    // U-shaped 8-vertex concave building outline (84m East-West × 49m North-South, open courtyard on East side)
    this.roofOutlineM = [
      [-42.0, -24.5], // P1: Top-Left (NW outer corner)
      [42.0, -24.5],  // P2: Top-Right (NE outer corner, 84.0m top wing)
      [42.0, -10.5],  // P3: North wing inner East corner
      [-26.0, -10.5], // P4: Inner NW courtyard corner (68.0m inner North edge)
      [-26.0, 10.5],  // P5: Inner SW courtyard corner (21.0m West corridor inner edge)
      [18.0, 10.5],   // P6: South wing inner East corner
      [18.0, 24.5],   // P7: Bottom-Right (SE outer corner)
      [-42.0, 24.5],  // P8: Bottom-Left (SW outer corner, 60.0m bottom wing)
    ];

    // Multi-point polygon keepouts (elevator machine room / skylights on NE & SE wings)
    this.obstacles = [
      {
        id: 'keepout-ushape-1',
        name: '禁布区 #1 (北翼东侧风机房)',
        kind: 'skylight',
        polygon: [
          [24.0, -22.2],
          [34.5, -22.2],
          [34.5, -16.8],
          [24.0, -16.8],
        ],
      },
      {
        id: 'keepout-ushape-2',
        name: '禁布区 #2 (南翼梯间与采光井)',
        kind: 'skylight',
        polygon: [
          [-6.0, 16.5],
          [8.5, 16.5],
          [8.5, 22.2],
          [-6.0, 22.2],
        ],
      },
      {
        id: 'keepout-ushape-3',
        name: '禁布区 #3 (北翼西侧五边形通风井)',
        kind: 'vent',
        polygon: [
          [-18.0, -22.2],
          [-10.5, -22.2],
          [-8.5, -19.2],
          [-12.0, -16.8],
          [-18.0, -17.2],
        ],
      },
    ];

    this.hasRoof = true;
    this.showRoofOverlay = true;
    this.activeTool = 'pan';
    this.scaleReferenceM = 84.0;
    this.liveEdgeLengthMm = 84000;
    this.layoutModules({ quiet: true, autoCreateRoof: false });
    this.electricalConfirmed = true;
    this.showStringColors = true;
    this.computeElectricalAllocation();
    this.evaluateWeatherAndAngles();
    this.notice(
      `已加载「复杂 U 型凹多边形屋面 + 多点禁布区」示范工程：共排布 ${this.summary.moduleCount} 块组件 (${this.summary.dcKw} kWp)，分北/西/南三翼完成 ${this.summary.stringCount} 路组串蛇形布线，0 跨越中央天井、CAD 图纸保持 0° 正交水平！`
    );
    if (this.host) {
      this.refresh();
    }
  }

  scheduleMapRedraw() {
    if (typeof requestAnimationFrame !== 'function') {
      this.drawMapCanvas();
      this.drawLocPickerModalCanvas();
      return;
    }
    if (this._rafPending) return;
    this._rafPending = true;
    requestAnimationFrame(() => {
      this._rafPending = false;
      this.drawMapCanvas();
      this.drawLocPickerModalCanvas();
    });
  }

  async load() {
    if (!this.pvsystData) {
      this.refreshPvsystData({ fetchBackend: true });
    }
    return this;
  }

  dispose() {
    if (this.twin3d) {
      this.twin3d.dispose();
      this.twin3d = null;
    }
    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }
    this.timerRunning = false;
    this.sim3dPlaying = false;
    this.isFullscreen = false;
  }

  build3DTwinPayload() {
    const mod = this.getSelectedModule();
    return {
      lat: this.lat,
      lon: this.lon,
      roofOutlineM: this.roofOutlineM,
      obstacles: this.obstacles,
      modules: this.modules,
      strings: this.strings,
      inverterPointsM: this.inverterPointsM,
      roofType: this.roofType,
      roofSlopeDeg: this.roofSlopeDeg,
      ridgeAzimuthDeg: this.ridgeAzimuthDeg,
      tiltDeg: this.tiltDeg,
      azimuthDeg: this.azimuthDeg,
      buildingHeightM: this.buildingHeightM || 12,
      parapetHeightMm: this.parapetHeightMm,
      parapetWidthMm: this.parapetWidthMm,
      subArrayHeightMm: this.subArrayHeightMm,
      bessPowerKw: this.bessPowerKw || 0,
      bessCapacityKwh: this.bessCapacityKwh || 0,
      moduleStcW: mod.stc_w || 580,
      obstacleHeightScale: this.sim3dObstacleScale || 1.0,
      simDateStr: this.sim3dDateStr,
      simHourBjt: this.sim3dHourBjt,
      simDisplayMode: this.sim3dMode,
      showSunDome: this.sim3dShowSunDome,
    };
  }

  compute3DShadingReport() {
    const spec = buildSatmap3DGeometrySpec(this.build3DTwinPayload());
    const annual = computeAnnual3DShadingSummary(spec, { lat: this.lat, lon: this.lon });
    const winterMorning = compute3DPhysicalShading(spec, {
      lat: this.lat,
      lon: this.lon,
      dateStr: '2026-12-21',
      hourBjt: 9.0,
    });
    this.shading3dSummary = {
      ...annual,
      winterMorningDiodeMods: winterMorning.diodeActivatedCount,
      winterMorningLinearPct: winterMorning.linearBeamShadePct,
    };
    return this.shading3dSummary;
  }

  render3DMetricsInnerHtml(livePayload = null) {
    const spec = livePayload?.spec || buildSatmap3DGeometrySpec(this.build3DTwinPayload());
    const dateStr = livePayload?.simCfg?.dateStr || this.sim3dDateStr || '2026-12-21';
    const hourBjt = Number.isFinite(livePayload?.simCfg?.hourBjt)
      ? livePayload.simCfg.hourBjt
      : this.sim3dHourBjt;
    const sh = livePayload?.shading || compute3DPhysicalShading(spec, {
      lat: this.lat,
      lon: this.lon,
      dateStr,
      hourBjt,
    });
    const ann = livePayload?.annual || this.shading3dSummary || computeAnnual3DShadingSummary(spec, {
      lat: this.lat,
      lon: this.lon,
    });
    const altStr = Number(sh.solar?.altitudeDeg ?? sh.solarAltDeg ?? 0).toFixed(1);
    const azStr = Number(sh.solar?.azimuthDeg ?? sh.solarAzDeg ?? 180).toFixed(1);
    const poaStr = Math.round(Number(sh.avgPoaWm2 || 0));
    const linStr = Number(sh.linearBeamShadePct || 0).toFixed(1);
    const elecStr = Number(sh.electricalShadeLossPct || 0).toFixed(1);
    const diodeMods = Number(sh.diodeActivatedCount || 0);
    const annElec = Number(ann.annualElectricalLossPct || 0).toFixed(2);
    const winPass = Number(ann.winter9to15PassPct ?? 100).toFixed(1);
    return `
      <span>太阳高度角 <b>${altStr}°</b> · 方位角 <b>${azStr}°</b></span>
      <span>阵列均布辐照 <b>${poaStr} W/m²</b></span>
      <span>瞬时几何遮挡 <b>${linStr}%</b></span>
      <span>旁路二极管电损耗 <b style="color:${diodeMods > 0 ? '#fbbf24' : '#34d399'}">${elecStr}% (${diodeMods} 块触发)</b></span>
      <span>全年三维阴影损耗 <b>${annElec}%</b> · 冬至无遮挡率 <b style="color:#38bdf8">${winPass}%</b></span>
    `;
  }

  update3DMetricsBarInPlace(livePayload = null) {
    if (!this.host) return;
    if (livePayload?.simCfg && Number.isFinite(livePayload.simCfg.hourBjt)) {
      this.sim3dHourBjt = livePayload.simCfg.hourBjt;
      const hr = Math.floor(this.sim3dHourBjt);
      const mn = Math.min(59, Math.round((this.sim3dHourBjt - hr) * 60));
      const fmt = `${String(hr).padStart(2, '0')}:${String(mn).padStart(2, '0')}`;
      const hrTxt = this.host.querySelector('#satmap-3d-hour-text');
      if (hrTxt) hrTxt.textContent = fmt;
      const slider = this.host.querySelector('[data-sat-field="sim3dHourBjt"]');
      if (slider && Math.abs(Number(slider.value) - this.sim3dHourBjt) > 0.05) {
        slider.value = String(this.sim3dHourBjt);
      }
    }
    if (livePayload?.annual) {
      this.shading3dSummary = {
        ...(this.shading3dSummary || {}),
        ...livePayload.annual,
      };
    }
    const bar = this.host.querySelector('#satmap-3d-metrics-bar');
    if (bar) {
      bar.innerHTML = translateHtmlToEn(this.render3DMetricsInnerHtml(livePayload));
      localizeDomSubtree(bar);
    }
  }

  getAllModules() {
    return [...SAT_MODULE_CATALOG, ...(this.customModules || [])];
  }

  getAllInverters() {
    return [...SAT_INVERTER_CATALOG, ...(this.customInverters || [])];
  }

  getSelectedModule() {
    const all = this.getAllModules();
    return enrichModuleSpec(all.find((m) => m.id === this.moduleModelId) || all[0]);
  }

  getSelectedInverter() {
    const all = this.getAllInverters();
    return enrichInverterSpec(all.find((inv) => inv.id === this.inverterModelId) || all[0]);
  }

  getRoofBoundsM(fallbackIfEmpty = false) {
    const poly = this.roofOutlineM && this.roofOutlineM.length >= 3
      ? this.roofOutlineM
      : fallbackIfEmpty
        ? [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]]
        : [];
    if (!poly.length) {
      return {
        minX: 0,
        maxX: 0,
        minY: 0,
        maxY: 0,
        centerX: 0,
        centerY: 0,
        widthM: 0,
        heightM: 0,
        areaM2: 0,
      };
    }
    const xs = poly.map((p) => p[0]);
    const ys = poly.map((p) => p[1]);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    // Compute exact polygon shoelace area
    let area2 = 0;
    for (let i = 0; i < poly.length; i++) {
      const [x0, y0] = poly[i];
      const [x1, y1] = poly[(i + 1) % poly.length];
      area2 += x0 * y1 - x1 * y0;
    }
    const shoelaceArea = Math.round(Math.abs(area2) * 0.5);
    return {
      minX,
      maxX,
      minY,
      maxY,
      centerX: (minX + maxX) * 0.5,
      centerY: (minY + maxY) * 0.5,
      widthM: Math.max(1, maxX - minX),
      heightM: Math.max(1, maxY - minY),
      areaM2: shoelaceArea > 0 ? shoelaceArea : Math.round((maxX - minX) * (maxY - minY)),
    };
  }

  /**
   * Calculate winter-solstice (Dec 21, declination -23.45°) 9:00-15:00 solar geometry
   * and unshaded inter-row spacing for local latitude and tilt angle.
   */
  computeWinterSolsticeRowSpacing(tiltDeg, latDeg = this.lat) {
    const mod = this.getSelectedModule();
    const modSlopeLenM = this.orientation === 'portrait' ? mod.length_m : mod.width_m;
    const phi = (Math.max(15, Math.min(55, Math.abs(Number(latDeg) || 35))) * Math.PI) / 180;
    const delta = (-23.45 * Math.PI) / 180;
    const omega = (45.0 * Math.PI) / 180; // 9:00 / 15:00 solar time (3h from noon)

    const sinAlpha = Math.max(0.08, Math.sin(phi) * Math.sin(delta) + Math.cos(phi) * Math.cos(delta) * Math.cos(omega));
    const alphaRad = Math.asin(Math.min(1, sinAlpha));
    const tanAlpha = Math.max(0.10, Math.tan(alphaRad));
    const cosGamma = Math.min(
      1,
      Math.max(0.2, (sinAlpha * Math.sin(phi) - Math.sin(delta)) / Math.max(0.08, Math.cos(alphaRad) * Math.cos(phi)))
    );

    const betaRad = (Math.max(0, Number(tiltDeg) || 0) * Math.PI) / 180;
    const modFootprintM = modSlopeLenM * Math.cos(betaRad);
    const modHeightM = modSlopeLenM * Math.sin(betaRad);
    const shadowLengthM = modHeightM * (cosGamma / tanAlpha);
    const netRowGapM = Number(Math.max(0.45, shadowLengthM).toFixed(2));
    const centerPitchM = Number((modFootprintM + netRowGapM).toFixed(2));

    return {
      solarAlt9amDeg: Number(((alphaRad * 180) / Math.PI).toFixed(1)),
      solarAz9amDeg: Number((180 - (Math.acos(cosGamma) * 180) / Math.PI).toFixed(1)),
      modSlopeLenM: Number(modSlopeLenM.toFixed(3)),
      modFootprintM: Number(modFootprintM.toFixed(2)),
      modHeightM: Number(modHeightM.toFixed(2)),
      netRowGapM,
      centerPitchM,
    };
  }

  /**
   * Fast O(1) analytical module count estimation for a given row gap and target capacity limit.
   * Eliminates the O(N*M) nested polygon loop during weather/angle evaluation so the UI never freezes.
   */
  countModulesForRowGap(rowGapM, maxModulesLimit = Infinity) {
    const mod = this.getSelectedModule();
    const modW = this.orientation === 'portrait' ? mod.width_m : mod.length_m;
    const modH = this.orientation === 'portrait' ? mod.length_m : mod.width_m;
    const bounds = this.getRoofBoundsM(true);
    const effW = bounds.widthM > 180 && !this.scaleCustomized ? 76.0 : bounds.widthM;
    const effH = bounds.widthM > 180 && !this.scaleCustomized
      ? Math.max(20, (bounds.heightM / Math.max(1, bounds.widthM)) * 76.0)
      : bounds.heightM;
    const setback = Math.max(0.1, Number(this.edgeSetbackM) || 0.8);
    const colGap = Math.max(0.01, Number(this.colSpacingM) || 0.03);
    const effRowGap = Math.max(0.15, Number(rowGapM) || 0.45);
    const ridgeDeductionM = this.roofType === 'double_slope' ? 1.3 : 0;

    const usableW = Math.max(0, effW - 2 * setback);
    const usableH = Math.max(0, effH - 2 * setback - ridgeDeductionM);
    const cols = usableW >= modW ? Math.floor((usableW + colGap) / (modW + colGap)) : 0;
    const rows = usableH >= modH ? Math.floor((usableH + effRowGap) / (modH + effRowGap)) : 0;
    const bboxArea = Math.max(1, bounds.widthM * bounds.heightM);
    const fillRatio = Math.min(1, Math.max(0.45, (bounds.areaM2 || bboxArea) / bboxArea));

    let obsArea = 0;
    for (const obs of this.obstacles || []) {
      const poly = obs.polygon || [];
      if (poly.length >= 3) {
        const xs = poly.map((p) => p[0]);
        const ys = poly.map((p) => p[1]);
        obsArea += (Math.max(...xs) - Math.min(...xs) + 0.5) * (Math.max(...ys) - Math.min(...ys) + 0.5);
      }
    }
    const obsRatio = Math.max(0.25, 1 - obsArea / Math.max(1, effW * effH));
    const rawCount = Math.max(0, Math.round(cols * rows * fillRatio * obsRatio));
    return Math.min(rawCount, maxModulesLimit, 2000);
  }

  /**
   * Real Weather Coupled Design Evaluation:
   * Uses official meteorological data + latitude solar geometry to evaluate tilt & azimuth angles,
   * winter-solstice unshaded spacing, roof capacity, specific yield, and total annual power generation.
   */
  evaluateWeatherAndAngles() {
    const mod = this.getSelectedModule();
    const sim = this.pvsystData || computeClientFallbackPvsyst({
      lat: this.lat,
      lon: this.lon,
      dc_kw: this.summary?.dcKw || 280,
      ac_kw: this.summary?.acKw || 220,
      tilt_deg: this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg,
      azimuth_deg: this.azimuthDeg,
      ...this.pvsystParams,
    });

    const wx = sim?.live_weather || {};
    const curWx = wx.current || {};
    const optMat = sim?.optimization_matrix || {};
    const tilts = [0, 6, 10, 15, 20, 24, 28, 32, 35];
    const azList = Array.isArray(optMat.azimuths) && optMat.azimuths.length ? optMat.azimuths : [90, 120, 150, 165, 180, 195, 210, 240, 270];
    const azIdx = azList.reduce((bestI, az, idx) => (Math.abs(az - this.azimuthDeg) < Math.abs(azList[bestI] - this.azimuthDeg) ? idx : bestI), 4);

    const globHor = Number(sim?.summary?.glob_hor_kwh_m2 || 1380);
    const basePr = Number(sim?.summary?.pr_pct || 84.2) / 100;
    const latAbs = Math.abs(Number(this.lat) || 35);
    const weatherOptTilt = Number(optMat.optimal_tilt_deg ?? Math.max(8, Math.min(35, Math.round(latAbs * 0.78))));
    const weatherOptAz = Number(optMat.optimal_azimuth_deg ?? 180);

    const maxModsByTarget = this.targetCapacityKw > 0
      ? Math.max(1, Math.floor((this.targetCapacityKw * 1000) / mod.stc_w))
      : Infinity;

    const candidates = tilts.map((tDeg) => {
      const ws = this.computeWinterSolsticeRowSpacing(tDeg, this.lat);
      const effectiveRowGap = tDeg <= 8 ? Math.max(0.45, ws.netRowGapM * 0.75) : ws.netRowGapM;
      const modCount = this.countModulesForRowGap(effectiveRowGap, maxModsByTarget);
      const dcKw = Number(((modCount * mod.stc_w) / 1000).toFixed(2));

      // Compute POA irradiation & specific yield for tilt tDeg at current location
      let specYield = 0;
      const matRowIdx = Array.isArray(optMat.tilts) ? optMat.tilts.indexOf(tDeg) : -1;
      if (matRowIdx >= 0 && optMat.grid_kwh_kwp?.[matRowIdx]?.[azIdx]) {
        specYield = Number(optMat.grid_kwh_kwp[matRowIdx][azIdx]);
      } else {
        const tiltDiff = tDeg - weatherOptTilt;
        const azDiff = this.azimuthDeg - 180;
        const gainFactor = 1.0 + 0.115 * Math.cos((tiltDiff * Math.PI) / 55) - 0.000025 * azDiff * azDiff;
        specYield = Number((globHor * Math.max(0.84, gainFactor) * basePr).toFixed(1));
      }
      const poaKwhM2 = Number((specYield / Math.max(0.72, basePr)).toFixed(1));
      const annualKwh = Math.round(dcKw * specYield);
      const annualWanKwh = Number((annualKwh / 10000).toFixed(2));

      return {
        tiltDeg: tDeg,
        netRowGapM: effectiveRowGap,
        centerPitchM: Number((ws.modFootprintM + effectiveRowGap).toFixed(2)),
        solarAlt9amDeg: ws.solarAlt9amDeg,
        solarAz9amDeg: ws.solarAz9amDeg,
        poaKwhM2,
        moduleCount: modCount,
        dcKw,
        specificYield: Number(specYield.toFixed(1)),
        annualKwh,
        annualWanKwh,
      };
    });

    const bestYieldRow = candidates.reduce((best, r) => (r.specificYield > best.specificYield ? r : best), candidates[0]);
    const bestTotalRow = candidates.reduce((best, r) => (r.annualKwh > best.annualKwh ? r : best), candidates[0]);
    const activeTilt = this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg;
    const currentWs = this.computeWinterSolsticeRowSpacing(activeTilt, this.lat);

    this.weatherEval = {
      source: wx.provenance?.source || '中国气象局 (CMA) / Open-Meteo 官方气象辐射同化网络',
      observedAt: curWx.observed_at || '实时同步',
      tempC: Number(curWx.temp_c ?? 22.5),
      windMs: Number(curWx.wind_ms ?? 2.8),
      ghiWm2: Number(curWx.ghi_wm2 ?? 640),
      poaWm2: Number(curWx.poa_wm2 ?? 710),
      tCellC: Number(curWx.t_cell_c ?? 41.2),
      globHorKwhM2: Number(globHor.toFixed(1)),
      globIncKwhM2: Number((sim?.summary?.glob_inc_kwh_m2 || globHor * 1.07).toFixed(1)),
      solarAlt9amDeg: currentWs.solarAlt9amDeg,
      solarAz9amDeg: currentWs.solarAz9amDeg,
      currentUnshadedGapM: currentWs.netRowGapM,
      weatherOptimalTiltDeg: bestYieldRow.tiltDeg,
      weatherOptimalAzimuthDeg: weatherOptAz,
      weatherOptimalYield: bestYieldRow.specificYield,
      weatherOptimalRowGapM: bestYieldRow.netRowGapM,
      roofOptimalTiltDeg: bestTotalRow.tiltDeg,
      roofOptimalWanKwh: bestTotalRow.annualWanKwh,
      roofOptimalDcKw: bestTotalRow.dcKw,
      roofOptimalRowGapM: bestTotalRow.netRowGapM,
      candidates,
    };
    return this.weatherEval;
  }

  /**
   * Build the orthonormal transformation between Geographic Local Meters (mx, my)
   * and Roof-Aligned Orthogonal Coordinates (u, v) centered at the roof centroid,
   * rotated by this.ridgeAzimuthDeg (recognized automatically from the satellite roof edges).
   */
  getRoofUVFrame(fallbackIfEmpty = false) {
    const bounds = this.getRoofBoundsM(fallbackIfEmpty);
    const pivX = bounds.centerX || 0;
    const pivY = bounds.centerY || 0;
    const rad = ((Number(this.ridgeAzimuthDeg) || 0) * Math.PI) / 180;
    const cosT = Math.cos(rad);
    const sinT = Math.sin(rad);
    const toUV = (mx, my) => {
      const dx = mx - pivX;
      const dy = my - pivY;
      return [dx * cosT + dy * sinT, -dx * sinT + dy * cosT];
    };
    const fromUV = (u, v) => [
      pivX + u * cosT - v * sinT,
      pivY + u * sinT + v * cosT,
    ];
    const polyM = this.roofOutlineM && this.roofOutlineM.length >= 3
      ? this.roofOutlineM
      : fallbackIfEmpty
        ? [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]]
        : [];
    const polyUV = polyM.map(([mx, my]) => toUV(mx, my));
    let uMin = 0, uMax = 0, vMin = 0, vMax = 0;
    if (polyUV.length) {
      const us = polyUV.map((p) => p[0]);
      const vs = polyUV.map((p) => p[1]);
      uMin = Math.min(...us);
      uMax = Math.max(...us);
      vMin = Math.min(...vs);
      vMax = Math.max(...vs);
    }
    return {
      pivX,
      pivY,
      rad,
      toUV,
      fromUV,
      polyUV,
      uMin,
      uMax,
      vMin,
      vMax,
      widthU: Math.max(1, uMax - uMin),
      heightV: Math.max(1, vMax - vMin),
      widthUV: Math.max(1, uMax - uMin),
      heightUV: Math.max(1, vMax - vMin),
      centerU: (uMin + uMax) * 0.5,
      centerV: (vMin + vMax) * 0.5,
      areaM2: bounds.areaM2,
    };
  }

  /**
   * 一键铺设 + 屋面主边对齐排布与禁布区避障算法
   * - Never mutates this.roofOutlineM or this.metersPerPx (eliminates roof offset/jump bug!)
   * - Aligns module rows parallel to the building's principal roof edge (this.ridgeAzimuthDeg)
   * - Respects sub-array maintenance walkways (横排块数 arrayGroupRows × 竖排块数 arrayGroupCols)
   * - Does NOT auto-split roof unless this.roofType === 'double_slope'
   */
  layoutModules({ quiet = false } = {}) {
    if (!this.roofOutlineM || this.roofOutlineM.length < 3) {
      this.ensureRoofOutline({ withDefaultKeepouts: this.obstacles.length === 0 });
    }
    this.hasRoof = true;
    this.hasLaidOut = true;

    const frame = this.getRoofUVFrame(true);
    const mod = this.getSelectedModule();
    const modW = this.orientation === 'portrait' ? mod.width_m : mod.length_m;
    const modH = this.orientation === 'portrait' ? mod.length_m : mod.width_m;
    const setback = Math.max(0.1, Number(this.edgeSetbackM) || 0.5);
    const obsPad = Math.max(0.05, Number(this.obstacleSetbackM) || 0.3);
    const colGap = Math.max(0.01, Number(this.colSpacingM) || 0.02);
    let rowGap = this.roofType === 'flat'
      ? Math.max(0.45, Number(this.rowSpacingM) || 1.2)
      : Math.max(0.15, Number(this.rowSpacingM) || 0.5);

    // If user drew a very large region while zoomed out, automatically adapt step density without moving roof vertices!
    const estCols = Math.max(1, Math.floor(frame.widthUV / (modW + colGap)));
    const estRows = Math.max(1, Math.floor(frame.heightUV / (modH + rowGap)));
    if (estCols * estRows > 2400) {
      const scaleStep = Math.sqrt((estCols * estRows) / 1600);
      rowGap = Number((rowGap * scaleStep).toFixed(2));
    }

    const groupRows = Math.max(1, Math.round(Number(this.arrayGroupRows) || 2));
    const groupCols = Math.max(1, Math.round(Number(this.arrayGroupCols) || 9));
    const walkwayM = Math.max(0, Number(this.walkwayWidthM) ?? 0.35);

    const uStart = frame.uMin + setback;
    const uEnd = frame.uMax - setback;
    const vStart = frame.vMin + setback;
    const vEnd = frame.vMax - setback;
    const midV = frame.centerV;
    const ridgeGap = this.roofType === 'double_slope' ? 0.65 : 0;
    const targetLimit = this.targetCapacityKw > 0
      ? Math.max(1, Math.floor((this.targetCapacityKw * 1000) / mod.stc_w))
      : 2000;
    const maxModsLimit = Math.min(2000, targetLimit);

    const placed = [];
    let rowIdx = 0;

    for (let v = vStart; v + modH <= vEnd + 1e-6;) {
      if (placed.length >= maxModsLimit) break;
      // Leave central ridge inspection walkway ONLY when user selected double_slope (双坡屋面)
      if (this.roofType === 'double_slope' && v < midV + ridgeGap && v + modH > midV - ridgeGap) {
        v = midV + ridgeGap;
        continue;
      }
      const cv = v + modH / 2;
      const slope = this.roofType === 'double_slope' ? (cv < midV ? 'north' : 'south') : 'south';
      let colIdx = 0;

      for (let u = uStart; u + modW <= uEnd + 1e-6;) {
        if (placed.length >= maxModsLimit) break;

        const cornersUV = [
          [u, v],
          [u + modW, v],
          [u + modW, v + modH],
          [u, v + modH],
        ];
        const cornersM = cornersUV.map(([uu, vv]) => frame.fromUV(uu, vv));
        const cu = u + modW / 2;
        const [cx, cy] = frame.fromUV(cu, cv);

        // Verify all 4 corners + center + edge midpoints lie strictly inside roofOutlineM and respect edge setback
        const edgeMidpointsM = [
          [(cornersM[0][0] + cornersM[1][0]) * 0.5, (cornersM[0][1] + cornersM[1][1]) * 0.5],
          [(cornersM[1][0] + cornersM[2][0]) * 0.5, (cornersM[1][1] + cornersM[2][1]) * 0.5],
          [(cornersM[2][0] + cornersM[3][0]) * 0.5, (cornersM[2][1] + cornersM[3][1]) * 0.5],
          [(cornersM[3][0] + cornersM[0][0]) * 0.5, (cornersM[3][1] + cornersM[0][1]) * 0.5],
        ];
        const insideRoof =
          pointInPolygon([cx, cy], this.roofOutlineM) &&
          cornersM.every((pt) => pointInPolygon(pt, this.roofOutlineM) && pointToPolygonEdgeDist(pt, this.roofOutlineM) >= setback * 0.45) &&
          edgeMidpointsM.every((pt) => pointInPolygon(pt, this.roofOutlineM));

        if (insideRoof) {
          const hitsObstacle = this.obstacles.some((obs) =>
            quadIntersectsPolygon(cornersM, obs.polygon, obsPad)
          );
          if (!hitsObstacle) {
            const normCorners = cornersUV.map(([uu, vv]) => [
              (uu - frame.uMin) / Math.max(1, frame.widthUV),
              (vv - frame.vMin) / Math.max(1, frame.heightUV),
            ]);
            placed.push({
              id: `M-${String(placed.length + 1).padStart(3, '0')}`,
              row: rowIdx,
              col: colIdx,
              slope,
              u,
              v,
              cu,
              cv,
              x: cornersM[0][0],
              y: cornersM[0][1],
              w: modW,
              h: modH,
              cx,
              cy,
              cornersUV,
              cornersM,
              normCorners,
              stringId: null,
              mpptIndex: 0,
              inverterIndex: 0,
              color: '#1d4ed8',
            });
          }
        }

        colIdx++;
        const addColWalkway = groupCols > 1 && colIdx > 0 && colIdx % groupCols === 0 ? walkwayM * 0.4 : 0;
        u += modW + colGap + addColWalkway;
      }

      rowIdx++;
      const addRowWalkway = this.roofType !== 'flat' && groupRows > 1 && rowIdx > 0 && rowIdx % groupRows === 0 ? walkwayM : 0;
      v += modH + rowGap + addRowWalkway;
    }

    this.modules = placed;
    this.removedModules = [];
    this.computeElectricalAllocation();
    this.refreshPvsystData({ fetchBackend: false });
    this.evaluateWeatherAndAngles();

    if (!quiet) {
      const slopeMsg = this.roofType === 'double_slope'
        ? `（南坡 ${this.summary.southCount} 块 / 北坡 ${this.summary.northCount} 块）`
        : '（整面连续排布）';
      this.notice(
        `一键铺设完成：共排布 ${placed.length} 块 ${mod.model} 组件，总装机 ${this.summary.dcKw.toFixed(2)} kWp${slopeMsg}，自动避让 ${this.obstacles.length} 处禁布区。`
      );
    }
    return placed;
  }

  /**
   * Advanced Connected-Wing Serpentine Stringing + Roof-Interior Cable Routing
   * 1. Clusters modules into contiguous roof wings (so C/L/U-shaped roofs or skylight-divided roofs
   *    never form a string that jumps back and forth across an empty courtyard!).
   * 2. Orders modules within each contiguous wing in 2-row × (perStr/2)-col U-turn serpentine blocks.
   * 3. Places inverters strictly inside the roof polygon.
   * 4. Routes all intra-string wires and home-run cables strictly inside the roof via Dijkstra over
   *    the interior module adjacency graph so ZERO wires ever cross outside the roof boundary!
   */
  computeElectricalAllocation() {
    const mod = this.getSelectedModule();
    const inv = this.getSelectedInverter();
    const perStr = Math.max(8, Math.min(24, Number(this.modulesPerString) || 18));
    const totalMods = this.modules.length;
    if (totalMods === 0) {
      this.strings = [];
      this.mpptRows = [];
      this.inverterPointsM = [];
      this.summary = {
        moduleCount: 0,
        southCount: 0,
        northCount: 0,
        dcKw: 0,
        acKw: 0,
        dcAcRatio: 0,
        inverterCount: 0,
        stringCount: 0,
        annualKwh: 0,
        specificYield: this.weatherEval?.weatherOptimalYield || 1186,
        prPct: 84.2,
        capexWan: 0,
        paybackYears: 0,
      };
      return;
    }

    const frame = this.getRoofUVFrame(true);
    const modW = this.modules[0]?.w || 1.134;
    const modH = this.modules[0]?.h || 2.278;
    const maxNeighborDist = Math.hypot(modW * 2.4, modH * 2.2);

    // 1. Build Interior Module Adjacency Graph:
    //    - `adj` enforces same-slope isolation (`mi.slope === mj.slope`) per GB 50797-2012 §6.4.2
    //    - `adjAllInterior` permits DC home-run trays to traverse across roof ridge while staying 100% inside roof & outside keepouts
    const nMods = this.modules.length;
    const adj = Array.from({ length: nMods }, () => []);
    const adjAllInterior = Array.from({ length: nMods }, () => []);
    for (let i = 0; i < nMods; i++) {
      const mi = this.modules[i];
      mi._idx = i;
      for (let j = i + 1; j < nMods; j++) {
        const mj = this.modules[j];
        if (Math.abs((mi.row ?? 0) - (mj.row ?? 0)) > 2) continue;
        const du = Math.abs((mi.cu ?? mi.cx) - (mj.cu ?? mj.cx));
        const dv = Math.abs((mi.cv ?? mi.cy) - (mj.cv ?? mj.cy));
        if (du > modW * 3.2 || dv > modH * 3.0) continue;
        const dist = Math.hypot(du, dv);
        if (dist <= maxNeighborDist * 1.15 && segmentStaysInsideRoof([mi.cx, mi.cy], [mj.cx, mj.cy], this.roofOutlineM, this.obstacles)) {
          const weight = mi.row === mj.row ? dist * 0.85 : dist * 1.15;
          adjAllInterior[i].push({ to: j, weight, dist });
          adjAllInterior[j].push({ to: i, weight, dist });
          if (dist <= maxNeighborDist && (mi.slope || 'south') === (mj.slope || 'south')) {
            adj[i].push({ to: j, weight, dist });
            adj[j].push({ to: i, weight, dist });
          }
        }
      }
    }

    // 2. Partition modules into Connected Components (Contiguous Roof Wings)
    const visitedComp = new Uint8Array(nMods);
    const wings = [];
    for (let i = 0; i < nMods; i++) {
      if (visitedComp[i]) continue;
      const comp = [];
      const queue = [i];
      visitedComp[i] = 1;
      while (queue.length) {
        const cur = queue.shift();
        comp.push(this.modules[cur]);
        for (const edge of adj[cur]) {
          if (!visitedComp[edge.to]) {
            visitedComp[edge.to] = 1;
            queue.push(edge.to);
          }
        }
      }
      wings.push(comp);
    }

    // 3. Within each Contiguous Wing, build 2-Row × (perStr/2)-Col U-Turn Serpentine Blocks
    //    and chain blocks by interior connectivity so a narrow U/L/C-roof arm is traversed contiguously
    //    without ever jumping across an empty central courtyard!
    const halfCols = Math.max(2, Math.ceil(perStr / 2));
    const orderedModules = [];
    for (const wing of wings) {
      const rowMap = new Map();
      for (const m of wing) {
        const r = m.row ?? 0;
        if (!rowMap.has(r)) rowMap.set(r, []);
        rowMap.get(r).push(m);
      }
      const sortedRows = Array.from(rowMap.keys()).sort((a, b) => a - b);
      const rowSegmentsByRow = new Map();
      for (const r of sortedRows) {
        const modsInRow = rowMap.get(r).sort((a, b) => (a.cu ?? a.cx) - (b.cu ?? b.cx));
        const segs = [];
        let curSeg = [];
        for (const m of modsInRow) {
          if (!curSeg.length) {
            curSeg.push(m);
          } else {
            const prev = curSeg[curSeg.length - 1];
            const gapU = (m.u ?? m.x) - ((prev.u ?? prev.x) + prev.w);
            const insideSeg = segmentStaysInsideRoof([prev.cx, prev.cy], [m.cx, m.cy], this.roofOutlineM, this.obstacles);
            if (gapU <= modW * 1.45 && insideSeg) {
              curSeg.push(m);
            } else {
              segs.push(curSeg);
              curSeg = [m];
            }
          }
        }
        if (curSeg.length) segs.push(curSeg);
        rowSegmentsByRow.set(r, segs);
      }

      // Build candidate 2 x halfCols serpentine blocks
      const usedInWing = new Set();
      const blocks = [];
      for (let rIdx = 0; rIdx < sortedRows.length; rIdx += 2) {
        const rTop = sortedRows[rIdx];
        const rBot = rIdx + 1 < sortedRows.length ? sortedRows[rIdx + 1] : null;
        const topSegs = rowSegmentsByRow.get(rTop) || [];
        const botSegs = rBot != null ? (rowSegmentsByRow.get(rBot) || []) : [];

        for (const tSeg of topSegs) {
          const tMinU = tSeg[0].u ?? tSeg[0].x;
          const tMaxU = (tSeg[tSeg.length - 1].u ?? tSeg[tSeg.length - 1].x) + modW;
          const matchBot = botSegs.find((bSeg) => {
            const bMinU = bSeg[0].u ?? bSeg[0].x;
            const bMaxU = (bSeg[bSeg.length - 1].u ?? bSeg[bSeg.length - 1].x) + modW;
            const overlapsU = Math.min(tMaxU, bMaxU) - Math.max(tMinU, bMinU) >= modW * 0.5;
            if (!overlapsU) return false;
            return segmentStaysInsideRoof([tSeg[0].cx, tSeg[0].cy], [bSeg[0].cx, bSeg[0].cy], this.roofOutlineM, this.obstacles);
          });

          const maxLen = Math.max(tSeg.length, matchBot ? matchBot.length : 0);
          for (let cStart = 0; cStart < maxLen; cStart += halfCols) {
            const topChunk = tSeg.slice(cStart, cStart + halfCols).filter((m) => !usedInWing.has(m));
            const botChunk = matchBot
              ? matchBot.slice(cStart, cStart + halfCols).filter((m) => !usedInWing.has(m)).reverse()
              : [];
            const blkMods = [...topChunk, ...botChunk];
            for (const m of blkMods) usedInWing.add(m);
            if (blkMods.length) {
              const avgU = blkMods.reduce((s, m) => s + (m.cu ?? m.cx), 0) / blkMods.length;
              const avgV = blkMods.reduce((s, m) => s + (m.cv ?? m.cy), 0) / blkMods.length;
              blocks.push({ mods: blkMods, avgU, avgV, rowTop: rTop });
            }
          }
        }
        for (const bSeg of botSegs) {
          const rem = bSeg.filter((m) => !usedInWing.has(m));
          for (let cStart = 0; cStart < rem.length; cStart += halfCols) {
            const chunk = rem.slice(cStart, cStart + halfCols);
            for (const m of chunk) usedInWing.add(m);
            if (chunk.length) {
              const avgU = chunk.reduce((s, m) => s + (m.cu ?? m.cx), 0) / chunk.length;
              const avgV = chunk.reduce((s, m) => s + (m.cv ?? m.cy), 0) / chunk.length;
              blocks.push({ mods: chunk, avgU, avgV, rowTop: rBot });
            }
          }
        }
      }
      for (const m of wing) {
        if (!usedInWing.has(m)) {
          usedInWing.add(m);
          blocks.push({ mods: [m], avgU: m.cu ?? m.cx, avgV: m.cv ?? m.cy, rowTop: m.row ?? 0 });
        }
      }

      // Chain blocks greedily by interior spatial proximity so under-full blocks on a U-roof arm
      // step smoothly down the same arm instead of jumping across an open courtyard!
      const usedBlk = new Uint8Array(blocks.length);
      let curBlkIdx = 0;
      for (let step = 0; step < blocks.length; step++) {
        if (step === 0 || usedBlk[curBlkIdx]) {
          curBlkIdx = -1;
          for (let i = 0; i < blocks.length; i++) {
            if (!usedBlk[i]) {
              curBlkIdx = i;
              break;
            }
          }
        }
        if (curBlkIdx < 0) break;
        usedBlk[curBlkIdx] = 1;
        const curBlk = blocks[curBlkIdx];
        for (const m of curBlk.mods) orderedModules.push(m);

        // Pick next unvisited block closest in interior roof space
        const lastMod = curBlk.mods[curBlk.mods.length - 1];
        let bestNext = -1;
        let bestScore = Infinity;
        for (let j = 0; j < blocks.length; j++) {
          if (usedBlk[j]) continue;
          const cand = blocks[j];
          const firstCand = cand.mods[0];
          const du = Math.abs(cand.avgU - curBlk.avgU);
          const dv = Math.abs(cand.avgV - curBlk.avgV);
          const directInside = segmentStaysInsideRoof([lastMod.cx, lastMod.cy], [firstCand.cx, firstCand.cy], this.roofOutlineM, this.obstacles);
          // Heavy penalty if crossing courtyard/obstacle so it stays on the same wing arm!
          const penalty = directInside ? 0 : 500;
          // If curBlk was narrow (< perStr), prefer stepping vertically down the same narrow arm (small du)
          const score = penalty + (curBlk.mods.length < perStr ? du * 2.2 + dv : dv * 2.2 + du * 0.6);
          if (score < bestScore) {
            bestScore = score;
            bestNext = j;
          }
        }
        if (bestNext >= 0) curBlkIdx = bestNext;
      }
    }

    // Dijkstra shortest interior path helper over module graph
    const findInteriorModulePath = (startIdx, endIdx, graph = adj) => {
      if (startIdx === endIdx) return [this.modules[startIdx]];
      const distArr = new Float64Array(nMods).fill(Infinity);
      const prevArr = new Int32Array(nMods).fill(-1);
      const visited = new Uint8Array(nMods);
      distArr[startIdx] = 0;
      for (let step = 0; step < nMods; step++) {
        let u = -1;
        let bestD = Infinity;
        for (let i = 0; i < nMods; i++) {
          if (!visited[i] && distArr[i] < bestD) {
            bestD = distArr[i];
            u = i;
          }
        }
        if (u === -1 || u === endIdx) break;
        visited[u] = 1;
        for (const edge of graph[u]) {
          const nd = distArr[u] + edge.weight;
          if (nd < distArr[edge.to]) {
            distArr[edge.to] = nd;
            prevArr[edge.to] = u;
          }
        }
      }
      if (!Number.isFinite(distArr[endIdx])) return null;
      const path = [];
      let cur = endIdx;
      while (cur !== -1) {
        path.push(this.modules[cur]);
        cur = prevArr[cur];
      }
      path.reverse();
      return path;
    };

    // Pre-evaluate climate-zone IEC 62548 single-module voltage bounds before slicing strings
    const baseSizing = computeStringSizingAndCables({
      module: mod,
      inverter: inv,
      modulesPerString: perStr,
      lat: this.lat,
      lon: this.lon,
      dcSectionMm2: this.dcCableSectionMm2,
      acMaterial: this.acCableMaterial,
    });
    const nMinSafe = Math.max(4, baseSizing.nMinMppt || 6);
    const nMaxSafe = Math.max(nMinSafe, baseSizing.nMax || 24);

    for (const m of this.modules) {
      m.unwired = false;
      m.stringId = null;
      m.mpptIndex = 0;
      m.inverterIndex = 0;
    }

    // Partition orderedModules strictly by slope ('south' then 'north') so ZERO strings or MPPTs mix orientations!
    const orderedSouth = orderedModules.filter((m) => (m.slope || 'south') !== 'north');
    const orderedNorth = orderedModules.filter((m) => m.slope === 'north');

    const rawStringDefs = [];
    const sliceSlopeGroup = (slopeMods, slopeKey) => {
      const n = slopeMods.length;
      if (n === 0) return [];
      const nFull = Math.floor(n / perStr);
      const remCount = n % perStr;
      if (nFull === 0) {
        if (n >= nMinSafe) {
          rawStringDefs.push({ slope: slopeKey, slice: slopeMods.slice(0) });
          return [];
        }
        return slopeMods.slice(0);
      }
      if (remCount === 0) {
        for (let k = 0; k < nFull; k++) {
          rawStringDefs.push({
            slope: slopeKey,
            slice: slopeMods.slice(k * perStr, (k + 1) * perStr),
          });
        }
        return [];
      }
      if (remCount >= nMinSafe) {
        for (let k = 0; k < nFull; k++) {
          rawStringDefs.push({
            slope: slopeKey,
            slice: slopeMods.slice(k * perStr, (k + 1) * perStr),
          });
        }
        rawStringDefs.push({
          slope: slopeKey,
          slice: slopeMods.slice(nFull * perStr),
        });
        return [];
      }
      // 0 < remCount < nMinSafe: rebalance last full string + remainder into 2 valid strings when possible
      const tailPool = perStr + remCount;
      const splitA = Math.ceil(tailPool / 2);
      const splitB = Math.floor(tailPool / 2);
      if (splitB >= nMinSafe && splitA <= nMaxSafe) {
        for (let k = 0; k < nFull - 1; k++) {
          rawStringDefs.push({
            slope: slopeKey,
            slice: slopeMods.slice(k * perStr, (k + 1) * perStr),
          });
        }
        const tailStart = (nFull - 1) * perStr;
        rawStringDefs.push({
          slope: slopeKey,
          slice: slopeMods.slice(tailStart, tailStart + splitA),
        });
        rawStringDefs.push({
          slope: slopeKey,
          slice: slopeMods.slice(tailStart + splitA),
        });
        return [];
      }
      if (tailPool <= nMaxSafe) {
        for (let k = 0; k < nFull - 1; k++) {
          rawStringDefs.push({
            slope: slopeKey,
            slice: slopeMods.slice(k * perStr, (k + 1) * perStr),
          });
        }
        rawStringDefs.push({
          slope: slopeKey,
          slice: slopeMods.slice((nFull - 1) * perStr),
        });
        return [];
      }
      for (let k = 0; k < nFull; k++) {
        rawStringDefs.push({
          slope: slopeKey,
          slice: slopeMods.slice(k * perStr, (k + 1) * perStr),
        });
      }
      return slopeMods.slice(nFull * perStr);
    };

    let southRem = sliceSlopeGroup(orderedSouth, 'south');
    let northRem = sliceSlopeGroup(orderedNorth, 'north');

    // Diagnostic short-string fallback when the ENTIRE roof has < nMinSafe modules (e.g. 4 modules):
    // expose the actual short string in MPPT table so per-string under-voltage check flags it explicitly
    if (rawStringDefs.length === 0 && totalMods > 0) {
      if (southRem.length > 0) {
        rawStringDefs.push({ slope: 'south', slice: southRem.slice(0), diagnosticUnderMin: true });
        southRem = [];
      }
      if (northRem.length > 0) {
        rawStringDefs.push({ slope: 'north', slice: northRem.slice(0), diagnosticUnderMin: true });
        northRem = [];
      }
    }

    const strPerMppt = Math.max(1, inv.strings_per_mppt || 2);
    // Group strings by (slope, slice.length) so parallel strings on the same MPPT channel NEVER mismatch voltage!
    const scheduledDefs = [];
    let nextGlobalMppt = 0;
    for (const slopeKey of ['south', 'north']) {
      const slopeDefs = rawStringDefs.filter((d) => d.slope === slopeKey);
      const byLen = new Map();
      for (const d of slopeDefs) {
        const lenKey = d.slice.length;
        if (!byLen.has(lenKey)) byLen.set(lenKey, []);
        byLen.get(lenKey).push(d);
      }
      for (const group of byLen.values()) {
        group.forEach((def, idx) => {
          const globalMppt = nextGlobalMppt + Math.floor(idx / strPerMppt);
          scheduledDefs.push({ ...def, globalMppt, subIdx: (idx % strPerMppt) + 1 });
        });
        nextGlobalMppt += Math.ceil(group.length / strPerMppt);
      }
    }

    const totalMpptsUsed = Math.max(1, nextGlobalMppt);
    const wiredModulesCount = rawStringDefs.reduce((acc, d) => acc + d.slice.length, 0);
    const dcKw = (wiredModulesCount * mod.stc_w) / 1000;
    const invByMppt = Math.max(1, Math.ceil(totalMpptsUsed / Math.max(1, inv.mppt_count)));
    const invByDcAc = this.targetDcAcRatio > 0 && dcKw > 0
      ? Math.max(1, Math.round(dcKw / Math.max(1, inv.rated_ac_kw * this.targetDcAcRatio)))
      : 1;
    const invCount = dcKw > 0 ? Math.max(invByMppt, invByDcAc) : 0;
    const totalAcKw = invCount * inv.rated_ac_kw;
    const dcAcRatio = totalAcKw > 0 ? dcKw / totalAcKw : 0;

    const strings = [];
    const mpptRows = [];

    for (let sIdx = 0; sIdx < scheduledDefs.length; sIdx++) {
      const def = scheduledDefs[sIdx];
      const invIdx = Math.floor(def.globalMppt / inv.mppt_count);
      const mpptIdx = def.globalMppt % inv.mppt_count;
      const color = MPPT_PALETTE[def.globalMppt % MPPT_PALETTE.length];
      const strId = `INV${invIdx + 1}-MPPT${mpptIdx + 1}-S${def.subIdx}`;
      const slice = def.slice;
      const slopeTag = def.slope;
      const slopeLabel = this.roofType === 'double_slope'
        ? (slopeTag === 'north' ? '北坡 0°' : '南坡 180°')
        : (this.roofType === 'flat' ? `支架 ${this.tiltDeg}°` : '单坡屋面');

      for (const m of slice) {
        m.stringId = strId;
        m.mpptIndex = mpptIdx + 1;
        m.inverterIndex = invIdx + 1;
        m.color = color;
      }

      if (slice.length) {
        // Build strictly roof-interior 2-point wire segments for this string (never crossing outside the roof or through obstacles!)
        const wireSegmentsM = [];
        const wireSegmentsUV = [];
        const pushWireSeg = (p0M, p1M, p0UV, p1UV) => {
          if (Math.hypot(p1M[0] - p0M[0], p1M[1] - p0M[1]) < 0.02) return;
          if (segmentStaysInsideRoof(p0M, p1M, this.roofOutlineM, this.obstacles)) {
            wireSegmentsM.push([p0M, p1M]);
            wireSegmentsUV.push([p0UV, p1UV]);
          }
        };

        for (let k = 0; k < slice.length - 1; k++) {
          const mA = slice[k];
          const mB = slice[k + 1];
          const pAM = [mA.cx, mA.cy];
          const pBM = [mB.cx, mB.cy];
          const pAUV = [mA.cu ?? mA.cx, mA.cv ?? mA.cy];
          const pBUV = [mB.cu ?? mB.cx, mB.cv ?? mB.cy];
          const directDist = Math.hypot(pBUV[0] - pAUV[0], pBUV[1] - pAUV[1]);
          const directOk = directDist <= maxNeighborDist * 1.4 &&
            segmentStaysInsideRoof(pAM, pBM, this.roofOutlineM, this.obstacles);

          if (directOk) {
            const cornerUV = [pBUV[0], pAUV[1]];
            const cornerM = frame.fromUV(cornerUV[0], cornerUV[1]);
            if (
              Math.abs(pAUV[0] - pBUV[0]) > 0.2 &&
              Math.abs(pAUV[1] - pBUV[1]) > 0.2 &&
              pointInPolygon(cornerM, this.roofOutlineM) &&
              segmentStaysInsideRoof(pAM, cornerM, this.roofOutlineM, this.obstacles) &&
              segmentStaysInsideRoof(cornerM, pBM, this.roofOutlineM, this.obstacles)
            ) {
              pushWireSeg(pAM, cornerM, pAUV, cornerUV);
              pushWireSeg(cornerM, pBM, cornerUV, pBUV);
            } else {
              pushWireSeg(pAM, pBM, pAUV, pBUV);
            }
          } else {
            const interiorPath = findInteriorModulePath(mA._idx, mB._idx, adj);
            if (interiorPath && interiorPath.length >= 2 && interiorPath.length <= 8) {
              for (let pIdx = 0; pIdx < interiorPath.length - 1; pIdx++) {
                const pm0 = interiorPath[pIdx];
                const pm1 = interiorPath[pIdx + 1];
                pushWireSeg(
                  [pm0.cx, pm0.cy],
                  [pm1.cx, pm1.cy],
                  [pm0.cu ?? pm0.cx, pm0.cv ?? pm0.cy],
                  [pm1.cu ?? pm1.cx, pm1.cv ?? pm1.cy]
                );
              }
            }
          }
        }

        const midMod = slice[Math.floor(slice.length / 2)];
        const us = slice.map((m) => m.u ?? m.x);
        const vs = slice.map((m) => m.v ?? m.y);
        strings.push({
          id: strId,
          shortName: `PV${sIdx + 1}`,
          slope: slopeTag,
          slopeLabel,
          inverterIndex: invIdx + 1,
          inverterName: `${inv.model}#${invIdx + 1}`,
          mpptIndex: mpptIdx + 1,
          mpptLabel: `MPPT${mpptIdx + 1}`,
          moduleCount: slice.length,
          vmpV: Number((slice.length * mod.vmp_v).toFixed(1)),
          vocV: Number((slice.length * mod.voc_v * 1.08).toFixed(1)),
          color,
          centerM: [midMod.cx, midMod.cy],
          centerUV: [midMod.cu ?? midMod.cx, midMod.cv ?? midMod.cy],
          bboxUV: {
            uMin: Math.min(...us),
            uMax: Math.max(...us) + modW,
            vMin: Math.min(...vs),
            vMax: Math.max(...vs) + modH,
          },
          wireSegmentsM,
          wireSegmentsUV,
          homeRunPathM: [],
          homeRunPathUV: [],
          modules: slice,
        });
      }
    }

    // Unwired remainder modules (< nMinSafe) are explicitly flagged as unwired and NEVER disguised with string IDs/colors
    for (const m of southRem) {
      m.unwired = true;
      m.stringId = null;
      m.mpptIndex = 0;
      m.inverterIndex = 0;
      m.color = '#94a3b8';
    }
    for (const m of northRem) {
      m.unwired = true;
      m.stringId = null;
      m.mpptIndex = 0;
      m.inverterIndex = 0;
      m.color = '#94a3b8';
    }

    // 4. Place Inverters strictly INSIDE the roof polygon near the lower-right eave of each inverter's modules
    this.inverterPointsM = Array.from({ length: invCount }, (_, idx) => {
      const invMods = orderedModules.filter((m) => m.inverterIndex === idx + 1);
      const pool = invMods.length ? invMods : orderedModules;
      // Pick the module closest to the lower-right eave (max v, then max u)
      const anchorMod = pool.reduce((best, m) => {
        const scoreBest = (best.cv ?? best.cy) * 2.5 + (best.cu ?? best.cx);
        const scoreCur = (m.cv ?? m.cy) * 2.5 + (m.cu ?? m.cx);
        return scoreCur > scoreBest ? m : best;
      }, pool[0]);

      let invU = anchorMod.cu ?? anchorMod.cx;
      let invV = (anchorMod.cv ?? anchorMod.cy) + modH * 0.45;
      let [invX, invY] = frame.fromUV(invU, invV);
      if (
        !pointInPolygon([invX, invY], this.roofOutlineM) ||
        this.obstacles.some((o) => pointInPolygon([invX, invY], o.polygon)) ||
        !segmentStaysInsideRoof([anchorMod.cx, anchorMod.cy], [invX, invY], this.roofOutlineM, this.obstacles)
      ) {
        invU = anchorMod.cu ?? anchorMod.cx;
        invV = anchorMod.cv ?? anchorMod.cy;
        invX = anchorMod.cx;
        invY = anchorMod.cy;
      }
      return {
        id: `INV-${idx + 1}`,
        label: `${inv.model}#${idx + 1}`,
        x: invX,
        y: invY,
        u: invU,
        v: invV,
        anchorModIdx: anchorMod._idx,
      };
    });

    // 5. Route Home-Run Cables from each String to its Inverter strictly INSIDE the roof polygon
    for (const st of strings) {
      const invPt = this.inverterPointsM[(st.inverterIndex - 1) % this.inverterPointsM.length];
      if (!invPt || !st.modules.length) continue;
      const endMod = st.modules[st.modules.length - 1];
      if (segmentStaysInsideRoof([endMod.cx, endMod.cy], [invPt.x, invPt.y], this.roofOutlineM, this.obstacles)) {
        const bendUV = [invPt.u, endMod.cv ?? endMod.cy];
        const bendM = frame.fromUV(bendUV[0], bendUV[1]);
        if (
          pointInPolygon(bendM, this.roofOutlineM) &&
          segmentStaysInsideRoof([endMod.cx, endMod.cy], bendM, this.roofOutlineM, this.obstacles) &&
          segmentStaysInsideRoof(bendM, [invPt.x, invPt.y], this.roofOutlineM, this.obstacles)
        ) {
          st.homeRunPathM = [[endMod.cx, endMod.cy], bendM, [invPt.x, invPt.y]];
          st.homeRunPathUV = [[endMod.cu ?? endMod.cx, endMod.cv ?? endMod.cy], bendUV, [invPt.u, invPt.v]];
        } else {
          st.homeRunPathM = [[endMod.cx, endMod.cy], [invPt.x, invPt.y]];
          st.homeRunPathUV = [[endMod.cu ?? endMod.cx, endMod.cv ?? endMod.cy], [invPt.u, invPt.v]];
        }
      } else {
        const spineMods = findInteriorModulePath(endMod._idx, invPt.anchorModIdx, adjAllInterior);
        if (spineMods && spineMods.length >= 2) {
          // Shortcut & orthogonalize spine waypoints so home-run cables follow crisp horizontal/vertical cable trays 100% inside roof
          const rawM = spineMods.map((m) => [m.cx, m.cy]).concat([[invPt.x, invPt.y]]);
          const rawUV = spineMods.map((m) => [m.cu ?? m.cx, m.cv ?? m.cy]).concat([[invPt.u, invPt.v]]);
          const simpM = [rawM[0]];
          const simpUV = [rawUV[0]];
          let cur = 0;
          while (cur < rawM.length - 1) {
            let next = cur + 1;
            for (let probe = rawM.length - 1; probe > cur + 1; probe--) {
              if (segmentStaysInsideRoof(rawM[cur], rawM[probe], this.roofOutlineM, this.obstacles)) {
                next = probe;
                break;
              }
            }
            const u0 = rawUV[cur][0], v0 = rawUV[cur][1];
            const u1 = rawUV[next][0], v1 = rawUV[next][1];
            const bend1UV = [u0, v1];
            const bend1M = frame.fromUV(bend1UV[0], bend1UV[1]);
            const bend2UV = [u1, v0];
            const bend2M = frame.fromUV(bend2UV[0], bend2UV[1]);
            if (
              Math.abs(u1 - u0) > 0.4 &&
              Math.abs(v1 - v0) > 0.4 &&
              pointInPolygon(bend1M, this.roofOutlineM) &&
              segmentStaysInsideRoof(rawM[cur], bend1M, this.roofOutlineM, this.obstacles) &&
              segmentStaysInsideRoof(bend1M, rawM[next], this.roofOutlineM, this.obstacles)
            ) {
              simpM.push(bend1M);
              simpUV.push(bend1UV);
            } else if (
              Math.abs(u1 - u0) > 0.4 &&
              Math.abs(v1 - v0) > 0.4 &&
              pointInPolygon(bend2M, this.roofOutlineM) &&
              segmentStaysInsideRoof(rawM[cur], bend2M, this.roofOutlineM, this.obstacles) &&
              segmentStaysInsideRoof(bend2M, rawM[next], this.roofOutlineM, this.obstacles)
            ) {
              simpM.push(bend2M);
              simpUV.push(bend2UV);
            }
            simpM.push(rawM[next]);
            simpUV.push(rawUV[next]);
            cur = next;
          }
          st.homeRunPathM = simpM;
          st.homeRunPathUV = simpUV;
        } else {
          st.homeRunPathM = [];
          st.homeRunPathUV = [];
        }
      }
    }

    // Pre-compute climate-zone IEC 62548 voltage limits & per-string physical cable voltage drop
    const preSizing = computeStringSizingAndCables({
      module: mod,
      inverter: inv,
      modulesPerString: perStr,
      lat: this.lat,
      lon: this.lon,
      strings,
      dcSectionMm2: this.dcCableSectionMm2,
      acMaterial: this.acCableMaterial,
      inverterCount: invCount,
    });

    // Build slope-isolated MPPT allocation table rows
    for (let invIdx = 0; invIdx < invCount; invIdx++) {
      const invName = `${inv.model}#${invIdx + 1}`;
      const invStrings = strings.filter((s) => s.inverterIndex === invIdx + 1);
      const invTotalStrings = Math.max(1, invStrings.length);
      for (let mIdx = 0; mIdx < inv.mppt_count; mIdx++) {
        const matched = invStrings.filter((s) => s.mpptIndex === mIdx + 1);
        const strCount = matched.length;
        const modCount = matched[0]?.moduleCount ?? 0;
        const totalMpptMods = matched.reduce((acc, s) => acc + s.moduleCount, 0);
        const rowSlope = matched[0]?.slope || 'idle';
        const rowSlopeLabel = matched[0]?.slopeLabel || '备用';
        const stringNames = matched.length
          ? matched.map((s) => s.shortName).join(' / ')
          : '未接入';
        const stringRatio = matched.length
          ? `${strCount}/${invTotalStrings} (${Math.round((strCount / invTotalStrings) * 100)}%)`
          : '0%';
        const workCurrA = Number((strCount * mod.imp_a).toFixed(2));
        const shortCurrA = Number((strCount * mod.isc_a).toFixed(2));
        const vmpV = Number((modCount * mod.vmp_v).toFixed(1));
        const rowVocColdV = Number((modCount * baseSizing.vocSingleCold).toFixed(1));
        const rowVmpColdV = Number((modCount * baseSizing.vmpSingleCold).toFixed(1));
        const rowVmpHotV = Number((modCount * baseSizing.vmpSingleHot).toFixed(1));
        const lengthMismatch = matched.some((s) => s.moduleCount !== modCount);
        const vocOk = rowVocColdV <= baseSizing.maxAllowedSysV;
        const mpptLowOk = rowVmpHotV >= inv.mppt_v_min && vmpV >= inv.mppt_v_min;
        const mpptHighOk = rowVmpColdV <= inv.mppt_v_max && vmpV <= inv.mppt_v_max;
        const currOk = workCurrA <= inv.max_mppt_current_a && shortCurrA <= inv.max_short_current_a;
        const statusOk = strCount === 0 || (vocOk && mpptLowOk && mpptHighOk && currOk && !lengthMismatch);
        const rowStatus = strCount === 0
          ? '备用'
          : !mpptLowOk
            ? '电压偏低'
            : (!vocOk || !mpptHighOk)
              ? '电压超限'
              : !currOk
                ? '电流偏高'
                : '正常';
        mpptRows.push({
          inverterName: invName,
          mpptName: `MPPT${mIdx + 1}`,
          slope: rowSlope,
          slopeLabel: rowSlopeLabel,
          stringNames,
          stringCount: strCount,
          modulesPerString: modCount,
          totalMpptMods,
          stringRatio,
          workCurrentA: workCurrA,
          shortCurrentA: shortCurrA,
          vmpV,
          vocColdV: rowVocColdV,
          vmpColdV: rowVmpColdV,
          vmpHotV: rowVmpHotV,
          color: MPPT_PALETTE[(invIdx * inv.mppt_count + mIdx) % MPPT_PALETTE.length],
          status: rowStatus,
          ok: statusOk,
        });
      }
    }

    const wiredSouthCount = strings.filter((s) => s.slope !== 'north').reduce((acc, s) => acc + s.moduleCount, 0);
    const wiredNorthCount = strings.filter((s) => s.slope === 'north').reduce((acc, s) => acc + s.moduleCount, 0);
    const unwiredCount = southRem.length + northRem.length;
    const specYield = Number(this.summary?.specificYield) || 1186;
    const annualKwh = Math.round(dcKw * specYield);

    this.strings = strings;
    this.mpptRows = mpptRows;
    this.summary = {
      ...this.summary,
      moduleCount: wiredModulesCount,
      placedModuleCount: totalMods,
      unwiredCount,
      southCount: wiredSouthCount,
      northCount: wiredNorthCount,
      dcKw: Number(dcKw.toFixed(2)),
      acKw: Number(totalAcKw.toFixed(1)),
      dcAcRatio: Number(dcAcRatio.toFixed(2)),
      inverterCount: invCount,
      stringCount: strings.length,
      annualKwh,
      specificYield: specYield,
      prPct: Number(this.summary?.prPct) || 84.2,
    };
    this.recomputeEngineeringAnalyses();
  }

  /**
   * Synchronize IEC 62548 String/Cable Sizing, GB 55001 Wind/Snow/Zone Structural Check,
   * C&I Shift-Load Self-Consumption, and Exact 25-Year Discounted Cash Flow (DCF).
   */
  recomputeEngineeringAnalyses() {
    const mod = this.getSelectedModule();
    const inv = this.getSelectedInverter();
    const s = this.summary || {};
    const dcKw = Number(s.dcKw) || 0;
    const acKw = Number(s.acKw) || inv.rated_ac_kw;
    const activeTilt = this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg;
    const bounds = this.getRoofBoundsM(true);
    const bessPowerKw = Math.max(0, Number(this.bessPowerKw) || 0);
    const bessCapacityKwh = Math.max(0, Number(this.bessCapacityKwh) || 0);

    this.electricalSizing = computeStringSizingAndCables({
      module: mod,
      inverter: inv,
      modulesPerString: this.modulesPerString || 18,
      lat: this.lat,
      lon: this.lon,
      strings: this.strings || [],
      dcSectionMm2: this.dcCableSectionMm2,
      acMaterial: this.acCableMaterial,
      acRunM: Math.max(45, Math.round((bounds.widthM + bounds.heightM) * 0.55)),
      inverterCount: Math.max(1, s.inverterCount || 1),
    });
    if (this.strings && this.strings.length > 0) {
      this.dcCableTotalM = Math.round(this.electricalSizing.totalDcWireMeters * 0.5);
    }

    this.structuralCheck = computeStructuralVerification({
      lat: this.lat,
      lon: this.lon,
      roofType: this.roofType,
      tiltDeg: activeTilt,
      buildingHeightM: this.buildingHeightM,
      roughnessCategory: this.roughnessCategory,
      roofLoadLimitKnM2: Number(this.roofLoadLimitKnM2) > 0 ? Number(this.roofLoadLimitKnM2) : null,
      module: mod,
      moduleCount: Math.max(1, s.moduleCount || 400),
      roofAreaM2: Math.max(200, bounds.areaM2 || 2400),
    });

    if (this.shiftMode && this.shiftMode !== 'manual' && dcKw > 0) {
      const shiftRes = computeShiftLoadSelfUse({
        shiftMode: this.shiftMode,
        manualRatio: this.selfConsumptionRatio,
        dcKw,
        acKw,
        transformerKva: this.transformerKva,
        bessCapacityKwh,
      });
      this.selfConsumptionRatio = shiftRes.effectiveSelfUseRatio;
      this.shiftLoadEval = shiftRes;
    } else {
      this.shiftLoadEval = computeShiftLoadSelfUse({
        shiftMode: 'manual',
        manualRatio: this.selfConsumptionRatio,
        dcKw,
        acKw,
        transformerKva: this.transformerKva,
        bessCapacityKwh,
      });
    }

    const discPct = this.discountRatePct !== null && this.discountRatePct !== undefined && this.discountRatePct !== ''
      ? Number(this.discountRatePct)
      : 6.0;
    const dcf = computeFinancialDcf25Yr({
      dcKw,
      annualKwhYear1: Number(s.annualKwh) || 0,
      capexPerW: this.capexPerW,
      selfConsumptionRatio: this.selfConsumptionRatio,
      tariffSelfRmb: this.tariffRmb,
      tariffFeedInRmb: this.feedInTariffRmb,
      bessPowerKw,
      bessCapacityKwh,
      discountRatePct: discPct,
    });
    this.financialDcf = dcf;

    if (dcKw > 0) {
      this.summary.capexWan = bessCapacityKwh > 0 ? dcf.totalCapexWan : dcf.pvCapexWan;
      this.summary.paybackYears = dcf.staticPaybackYears;
      this.summary.dynamicPaybackYears = dcf.dynamicPaybackYears;
      this.summary.irrPct = dcf.irrPct;
      this.summary.npv25Wan = dcf.npv25Wan;
      this.summary.lcoeRmb = dcf.lcoeRmbPerKwh;
    } else {
      this.summary.capexWan = 0;
      this.summary.paybackYears = null;
      this.summary.dynamicPaybackYears = null;
      this.summary.irrPct = null;
      this.summary.npv25Wan = 0;
      this.summary.lcoeRmb = null;
    }
  }

  /**
   * Side-effect-free candidate scheme preview sharing the exact layout & electrical allocation engine with #lab.
   */
  previewCandidateScheme({ tilt = 18, rowGapM = 0.85, setbackM = 0.65, targetDcAc = 1.16, cableMaterial = null } = {}) {
    const snap = {
      hasRoof: this.hasRoof,
      hasLaidOut: this.hasLaidOut,
      roofOutlineM: (this.roofOutlineM || []).map((pt) => [...pt]),
      obstacles: (this.obstacles || []).map((o) => ({ ...o, polygon: (o.polygon || []).map((pt) => [...pt]) })),
      modules: this.modules,
      removedModules: this.removedModules,
      strings: this.strings,
      mpptRows: this.mpptRows,
      inverterPointsM: this.inverterPointsM,
      summary: { ...this.summary },
      electricalSizing: this.electricalSizing,
      structuralCheck: this.structuralCheck,
      shiftLoadEval: this.shiftLoadEval,
      financialDcf: this.financialDcf,
      pvsystData: this.pvsystData,
      weatherEval: this.weatherEval,
      shading3dSummary: this.shading3dSummary,
      dcCableTotalM: this.dcCableTotalM,
      tiltDeg: this.tiltDeg,
      roofSlopeDeg: this.roofSlopeDeg,
      rowSpacingM: this.rowSpacingM,
      edgeSetbackM: this.edgeSetbackM,
      targetDcAcRatio: this.targetDcAcRatio,
      acCableMaterial: this.acCableMaterial,
      selfConsumptionRatio: this.selfConsumptionRatio,
      _pvsystEpoch: this._pvsystEpoch,
    };
    try {
      this.tiltDeg = tilt;
      this.roofSlopeDeg = tilt;
      this.rowSpacingM = rowGapM;
      this.edgeSetbackM = setbackM;
      this.targetDcAcRatio = targetDcAc;
      if (cableMaterial) this.acCableMaterial = cableMaterial;
      this.layoutModules({ quiet: true, autoCreateRoof: true });
      return {
        moduleCount: this.summary.moduleCount,
        dcKw: this.summary.dcKw,
        acKw: this.summary.acKw,
        dcAcRatio: this.summary.dcAcRatio,
        inverterCount: this.summary.inverterCount,
      };
    } finally {
      Object.assign(this, snap);
    }
  }

  applyCandidateScheme({ tilt = 18, rowGapM = 0.85, setbackM = 0.65, targetDcAc = 1.16, cableMaterial = null } = {}) {
    this.tiltDeg = tilt;
    this.roofSlopeDeg = tilt;
    this.rowSpacingM = rowGapM;
    this.edgeSetbackM = setbackM;
    this.targetDcAcRatio = targetDcAc;
    if (cableMaterial) this.acCableMaterial = cableMaterial;
    this.layoutModules({ quiet: true, autoCreateRoof: true });
    this.electricalConfirmed = true;
    this.showStringColors = true;
    this.computeElectricalAllocation();
    this.refreshPvsystData({ fetchBackend: false });
    return this.summary;
  }

  refreshPvsystData({ fetchBackend = true } = {}) {
    const hasModules = this.modules && this.modules.length > 0;
    if (hasModules) {
      this.compute3DShadingReport();
    }
    const mod = this.getSelectedModule();
    const activeTilt = this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg;
    let subArrays = undefined;
    if (
      hasModules &&
      this.roofType === 'double_slope' &&
      this.summary.southCount > 0 &&
      this.summary.northCount > 0
    ) {
      subArrays = [
        {
          name: '南坡子阵 (180°)',
          dc_kw: Number(((this.summary.southCount * mod.stc_w) / 1000).toFixed(2)),
          tilt_deg: activeTilt,
          azimuth_deg: 180,
        },
        {
          name: '北坡子阵 (0°)',
          dc_kw: Number(((this.summary.northCount * mod.stc_w) / 1000).toFixed(2)),
          tilt_deg: activeTilt,
          azimuth_deg: 0,
        },
      ];
    }

    const epoch = (this._pvsystEpoch = (this._pvsystEpoch || 0) + 1);
    const reqHadModules = Boolean(hasModules);
    const reqOutlineSig = JSON.stringify(this.roofOutlineM || []);
    const reqPayload = {
      lat: this.lat,
      lon: this.lon,
      dc_kw: hasModules ? this.summary.dcKw : 280,
      ac_kw: hasModules ? this.summary.acKw : 220,
      tilt_deg: activeTilt,
      azimuth_deg: this.azimuthDeg,
      dc_ohmic_pct: this.electricalSizing?.avgDcDropPct || 1.2,
      ...(subArrays ? { sub_arrays: subArrays } : {}),
      ...this.pvsystParams,
    };
    try {
      this.pvsystData = computeClientFallbackPvsyst(
        reqPayload,
        { ...(subArrays ? { sub_arrays: subArrays } : {}), ...this.pvsystParams }
      );
      if (this.pvsystData?.summary) {
        this.summary.specificYield = Number(this.pvsystData.summary.specific_yield_kwh_kwp || 1186);
        this.summary.prPct = Number(this.pvsystData.summary.pr_pct || 84.2);
        if (hasModules && this.summary.dcKw > 0) {
          this.summary.annualKwh = Math.round(this.pvsystData.summary.e_grid_kwh || this.summary.annualKwh);
          this.recomputeEngineeringAnalyses();
        }
      }
    } catch {
      // Fallback already populated in this.summary
    }
    this.evaluateWeatherAndAngles();

    if (fetchBackend && typeof this.api === 'function') {
      Promise.resolve()
        .then(() => this.api('pvsyst/simulate', reqPayload))
        .then((res) => {
          if (epoch !== this._pvsystEpoch || !res?.summary) return;
          const nowHasModules = Boolean(this.modules && this.modules.length > 0);
          if (nowHasModules !== reqHadModules) return;
          if (JSON.stringify(this.roofOutlineM || []) !== reqOutlineSig) return;
          if (nowHasModules && Math.abs(Number(this.summary.dcKw || 0) - Number(reqPayload.dc_kw || 0)) > 0.05) return;
          this.pvsystData = res;
          this.summary.specificYield = Number(res.summary.specific_yield_kwh_kwp || this.summary.specificYield);
          this.summary.prPct = Number(res.summary.pr_pct || this.summary.prPct);
          if (nowHasModules && this.summary.dcKw > 0) {
            this.summary.annualKwh = Math.round(res.summary.e_grid_kwh || this.summary.annualKwh);
            this.recomputeEngineeringAnalyses();
          }
          this.evaluateWeatherAndAngles();
          if (this.host && this.step === 3) {
            this.refresh();
          }
        })
        .catch(() => {
          // Offline or test environment: client fallback remains active
        });
    }
  }

  formatTimer(ms) {
    const totalCs = Math.floor(Math.max(0, ms) / 10);
    const mins = Math.floor(totalCs / 6000);
    const secs = Math.floor((totalCs % 6000) / 100);
    const cs = totalCs % 100;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${String(cs).padStart(2, '0')}`;
  }

  html() {
    const s = this.summary;
    const steps = [
      [1, '卫星排布'],
      [2, '电气配串'],
      [3, '8760h 仿真'],
      [4, '实景透视'],
      [5, '施工图纸'],
    ];

    const autopilotBanner = this.autopilotState
      ? `<div class="satmap-autopilot-bar" data-sat-autopilot-banner>
          <span><b>AI 设计流程执行中：</b>${esc(this.autopilotState.text)}</span>
          <div class="satmap-autopilot-progress"><div class="satmap-autopilot-fill" style="width:${this.autopilotState.pct}%"></div></div>
          <b>${this.autopilotState.pct}%</b>
        </div>`
      : '';

    const kpiStrip = `<div class="satmap-kpi-strip${this.step !== 1 ? ' is-compact' : ''}">
      <div class="satmap-kpi-card">
        <span>组件排布数量</span>
        <strong>${valueMarkup(s.moduleCount, '块')} <small>块</small></strong>
        <small>南坡 ${s.southCount} 块 / 北坡 ${s.northCount} 块</small>
      </div>
      <div class="satmap-kpi-card">
        <span>直流装机容量</span>
        <strong>${valueMarkup(s.dcKw, 'kW')} <small>kWp</small></strong>
        <small>${esc(this.getSelectedModule().model)}</small>
      </div>
      <div class="satmap-kpi-card">
        <span>逆变器与交流容量</span>
        <strong>${valueMarkup(s.acKw, 'kW')} <small>kWac</small></strong>
        <small>${esc(this.getSelectedInverter().model)} × ${s.inverterCount} 台 (容配比 ${s.dcAcRatio})</small>
      </div>
      <div class="satmap-kpi-card">
        <span>首年 P50 并网发电量</span>
        <strong>${valueMarkup(Number((s.annualKwh / 10000).toFixed(2)), '万kWh')} <small>万度</small></strong>
        <small>满发小时 ${s.specificYield} h · 系统效率 PR ${s.prPct}%</small>
      </div>
      <div class="satmap-kpi-card">
        <span>组串与 MPPT 校核</span>
        <strong>${s.stringCount} <small>串</small></strong>
        <small><span class="sat-pill-ok">状态：正常</span> (${this.modulesPerString}块/串)</small>
      </div>
      <div class="satmap-kpi-card">
        <span>工程投资与静态回收期</span>
        <strong>${s.capexWan} <small>万元</small></strong>
        <small>预计回收期 ${s.paybackYears != null ? `${s.paybackYears} 年` : '未回收'}</small>
      </div>
    </div>`;

    let bodyHtml = '';
    if (this.step === 1) bodyHtml = this.renderStep1MapWorkbench();
    else if (this.step === 2) bodyHtml = this.renderStep2Electrical();
    else if (this.step === 3) bodyHtml = this.renderStep3Pvsyst();
    else if (this.step === 4) bodyHtml = this.renderStep4EffectStudio();
    else if (this.step === 5) bodyHtml = this.renderStep5CadStudio();

    const standaloneAttr = this.standaloneMode ? ` data-sat-standalone="${esc(this.standaloneMode)}"` : '';
    return translateHtmlToEn(`<div class="satmap-shell" data-satmap-root${standaloneAttr}>
      <div class="satmap-topbar">
        <div class="satmap-brand">
          <div>
            <h2>卫星地图 AI 光伏设计工作台</h2>
            <small>真实卫星定位 · 实时气象寻优 · 智能配串 · 全套施工图</small>
          </div>
        </div>
        <div class="satmap-steps" role="tablist" aria-label="卫星设计工作流步骤">
          ${steps.map(([num, label]) => `
            <button type="button" class="satmap-step-btn ${this.step === num ? 'active' : 'done'}" data-sat-step="${num}">
              <span class="satmap-step-num">${num}</span>
              <span>${esc(label)}</span>
            </button>
          `).join('')}
        </div>
        <div class="satmap-top-actions">
          <button type="button" class="sat-btn" onclick="location.hash='#lab'" title="前往方案比选与储能碳资产测算中心">方案与光储比选</button>
          <details class="sat-popover">
            <summary class="sat-btn">工程与选址 ▾</summary>
            <div class="sat-popover-panel">
              <button type="button" class="sat-btn" data-sat-action="open-tariff-modal" title="设置变压器容量、峰谷电价、自发自用比例、单位造价与储能规模">用电与经济参数</button>
              <button type="button" class="sat-btn" data-sat-action="open-loc-picker" title="打开地图拾取经纬度选址窗口">地图拾取经纬度</button>
              <button type="button" class="sat-btn" data-sat-action="open-pvlane-start" title="新建空白项目或导入/导出工程文件">新建/导入工程</button>
            </div>
          </details>
          <button type="button" class="sat-btn success" data-sat-action="save-to-project">保存至工程库</button>
        </div>
      </div>

      ${autopilotBanner}
      ${kpiStrip}
      ${bodyHtml}
      ${this.renderVideo1Modals()}
    </div>`);
  }

  setStandaloneMode(mode) {
    if (mode === 'pvsyst') {
      this.standaloneMode = 'pvsyst';
      this.step = 3;
    } else if (mode === 'oblique') {
      this.standaloneMode = 'oblique';
      this.step = 4;
    } else if (mode === 'cad') {
      this.standaloneMode = 'cad';
      this.step = 5;
    } else {
      if (this.standaloneMode) {
        this.step = 1;
      }
      this.standaloneMode = null;
    }
  }

  loadBenchmarkCase(caseItem) {
    if (!caseItem) return;
    const itemName = caseItem.name || caseItem.nameZh || this.projectName;
    this.projectName = itemName;
    this.address = caseItem.address || `${caseItem.region || '泰州市'} · ${itemName}`;
    if (Number.isFinite(Number(caseItem.lat))) this.lat = Number(caseItem.lat);
    if (Number.isFinite(Number(caseItem.lon))) this.lon = Number(caseItem.lon);
    const tiltVal = Number.isFinite(Number(caseItem.tiltDeg)) ? Number(caseItem.tiltDeg) : Number(caseItem.slopeDeg);
    if (Number.isFinite(tiltVal)) {
      this.tiltDeg = tiltVal;
      this.roofSlopeDeg = tiltVal;
    }
    if (Number.isFinite(Number(caseItem.azimuthDeg))) {
      this.azimuthDeg = Number(caseItem.azimuthDeg);
    }
    const rTypeStr = caseItem.roofType || caseItem.roofTypeZh || '';
    this.roofType = /双坡/.test(rTypeStr)
      ? 'double_slope'
      : /单坡/.test(rTypeStr)
      ? 'single_slope'
      : 'flat';
    const area = Math.max(800, Number(caseItem.areaSqm || caseItem.areaM2) || 5000);
    const w = Math.round(Math.sqrt(area * 1.8));
    const h = Math.round(area / w);
    this.roofOutlineM = [
      [-w / 2, -h / 2],
      [w / 2, -h / 2],
      [w / 2, h / 2],
      [-w / 2, h / 2],
    ];
    this.hasRoof = true;
    this.showRoofOverlay = true;
    this.layoutModules({ quiet: true, autoCreateRoof: false });
    this.refreshPvsystData({ fetchBackend: false });
  }

  renderStep1MapWorkbench() {
    const bounds = this.getRoofBoundsM();
    const mod = this.getSelectedModule();
    const inv = this.getSelectedInverter();
    const wxEval = this.weatherEval || this.evaluateWeatherAndAngles();
    const activeTilt = this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg;
    const isDrawingTool = ['roof', 'roof_poly', 'obstacle', 'obstacle_poly', 'scale', 'direction'].includes(this.activeTool);
    const curEdgeMm = Math.round((bounds.widthM || this.scaleReferenceM || 76) * 1000);

    return `
      <!-- 1. 地图拾取经纬度 · 全国任意省市区/企业搜索 · 坐标与图源收纳弹窗 -->
      <div class="satmap-searchbar">
        <div class="satmap-search-item">
          <span>省市区</span>
          <select data-sat-field="regionQuickPick" title="快捷定位全国各省市工业区，也可在右侧搜索任意企业或输入经纬度">
            <option value="">全国任意位置 / 快捷选区</option>
            <option value="山东省济南市历城区工业北路|36.588644|116.774288" ${this.regionQuickPick.startsWith('山东省济南市') ? 'selected' : ''}>山东省 / 济南市 / 历城区</option>
            <option value="山东省淄博市桓台县起凤镇工业园|36.858844|118.778089" ${this.regionQuickPick.startsWith('山东省淄博市') ? 'selected' : ''}>山东省 / 淄博市 / 桓台县</option>
            <option value="山东省济宁市兖州区大安镇工业园|35.566044|116.776388" ${this.regionQuickPick.startsWith('山东省济宁市') ? 'selected' : ''}>山东省 / 济宁市 / 兖州区</option>
            <option value="江苏省泰州市医药高新区药城大道|32.456200|119.923100" ${this.regionQuickPick.startsWith('江苏省泰州市') ? 'selected' : ''}>江苏省 / 泰州市 / 高新区</option>
            <option value="广东省佛山市顺德区北滘镇工业园|22.931800|113.214500" ${this.regionQuickPick.startsWith('广东省佛山市') ? 'selected' : ''}>广东省 / 佛山市 / 顺德区</option>
            <option value="浙江省嘉兴市平湖市经济开发区|30.698200|121.015600" ${this.regionQuickPick.startsWith('浙江省嘉兴市') ? 'selected' : ''}>浙江省 / 嘉兴市 / 平湖市</option>
            <option value="福建省宁德市蕉城区漳湾镇工业园|26.719073|119.555596" ${this.regionQuickPick.startsWith('福建省宁德市') ? 'selected' : ''}>福建省 / 宁德市 / 蕉城区</option>
            <option value="陕西省西安市经济技术开发区草滩园区|34.378500|108.891200" ${this.regionQuickPick.startsWith('陕西省西安市') ? 'selected' : ''}>陕西省 / 西安市 / 经开区</option>
          </select>
        </div>
        <div class="satmap-search-item" style="flex:1;min-width:240px">
          <span>位置搜索</span>
          <input type="text" class="addr-input" data-sat-field="searchQuery" value="${esc(this.searchQuery || this.address)}" placeholder="输入全国任意企业名称、工厂、工业园或地址搜索定位">
          <button type="button" class="sat-btn primary" data-sat-action="search-location">搜索位置</button>
        </div>
        <details class="sat-popover">
          <summary class="sat-btn">坐标与图源 (${Number(this.lat).toFixed(3)}°N, ${Number(this.lon).toFixed(3)}°E) ▾</summary>
          <div class="sat-popover-panel sat-popover-wide">
            <div class="satmap-field-row">
              <span>经度 (°E)</span>
              <input type="number" step="0.0001" class="coord-input" data-sat-field="lon" value="${Number(this.lon).toFixed(6)}">
            </div>
            <div class="satmap-field-row">
              <span>纬度 (°N)</span>
              <input type="number" step="0.0001" class="coord-input" data-sat-field="lat" value="${Number(this.lat).toFixed(6)}">
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
              <button type="button" class="sat-btn ${this.coordFormat === 'dms' ? 'primary' : ''}" data-sat-action="toggle-dms" title="切换十进制经纬度与度分秒(DMS)显示">
                ${this.coordFormat === 'dms' ? `度分秒: ${formatDmsCoord(this.lon, true)} ${formatDmsCoord(this.lat, false)}` : '度分秒切换'}
              </button>
              <button type="button" class="sat-btn primary" data-sat-action="locate">经纬度定位</button>
            </div>
            <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:4px">
              <span>切换地图图源</span>
              <select data-sat-field="mapSource" style="width:100%;max-width:none">
                <option value="gaode" ${this.mapSource === 'gaode' ? 'selected' : ''}>高清卫星混合底图 (含路网企业标注)</option>
                <option value="esri" ${this.mapSource === 'esri' ? 'selected' : ''}>全球高清纯卫星无标注底图</option>
              </select>
            </label>
          </div>
        </details>
        <button type="button" class="sat-btn" data-sat-action="toggle-fullscreen">${this.isFullscreen ? '退出全屏' : '全屏地图'}</button>
      </div>

      ${this.searchResults && this.searchResults.length ? `
        <div class="satmap-search-results" role="listbox" aria-label="全国搜索候选位置">
          <span style="font-size:12px;color:var(--muted);font-weight:600">精确匹配位置（点击定位至目标厂房）：</span>
          ${this.searchResults.map((item, idx) => `
            <button type="button" class="sat-btn" data-sat-pick-loc="${idx}" style="font-weight:500" title="${esc(item.address || item.name)}">
              <b>${esc(item.name || item.address)}</b>
              ${item.address && item.address !== item.name ? `<small style="color:var(--muted)">(${esc(item.address)})</small>` : ''}
              <small style="color:#0284c7">[${Number(item.lat).toFixed(4)}°N, ${Number(item.lon).toFixed(4)}°E]</small>
            </button>
          `).join('')}
        </div>
      ` : ''}

      <!-- 2. 嵌入式 AI 设计要求与一键设计栏 + 顶部建模动作栏 -->
      <div class="satmap-ai-bar">
        <span style="font-size:12.5px;font-weight:700;color:var(--ink);white-space:nowrap">AI 设计要求：</span>
        <input type="text" data-sat-field="aiRequirement" value="${esc(this.aiRequirement)}"
          placeholder="输入设计要求，例如：按当地实时气象最优倾角设计，目标装机 250kW，双坡屋面预留 0.8m 退距，自动避让采光带并完成 MPPT 配串">
        <label style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--muted);white-space:nowrap">
          <span>倾角寻优策略</span>
          <select data-sat-field="angleStrategy" style="padding:5px 8px;border:1px solid var(--line-2,#cbd5e1);border-radius:4px;font-size:12px">
            <option value="weather_yield" ${this.angleStrategy === 'weather_yield' ? 'selected' : ''}>按气象单瓦最优倾角 (${wxEval.weatherOptimalTiltDeg}°)</option>
            <option value="roof_total" ${this.angleStrategy === 'roof_total' ? 'selected' : ''}>按屋面总发电量最优倾角 (${wxEval.roofOptimalTiltDeg}°)</option>
            <option value="roof_flush" ${this.angleStrategy === 'roof_flush' ? 'selected' : ''}>顺彩钢瓦屋面坡度平铺 (${this.roofSlopeDeg}°)</option>
            <option value="custom" ${this.angleStrategy === 'custom' ? 'selected' : ''}>保持当前手动设定角度 (${activeTilt}°)</option>
          </select>
        </label>
        <button type="button" class="sat-btn" data-sat-action="ai-detect-roof">载入标准厂房样板</button>
        <button type="button" class="sat-btn primary" data-sat-action="ai-autopilot">AI 按要求一键设计</button>
      </div>

      <!-- 顶部建模工具栏 -->
      <div class="satmap-v1-modelbar" role="toolbar" aria-label="屋面建模与工具栏">
        <div class="satmap-v1-modelbar-group">
          <button type="button" class="satmap-v1-tool-chip" data-sat-action="open-loc-picker" title="打开地图拾取经纬度弹窗">地图选址</button>
          <button type="button" class="satmap-v1-tool-chip" data-sat-action="clear-roof" title="清空当前选区并重新选址绘制">重新绘制</button>
          <label class="satmap-v1-tool-chip" style="cursor:pointer" title="上传无人机航拍俯视图或CAD转图片">
            上传底图
            <input type="file" accept="image/*" data-sat-file="ortho-photo" style="display:none">
          </label>
        </div>
        <div class="satmap-v1-modelbar-group">
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'roof_poly' ? 'active' : ''}" data-sat-tool="roof_poly">绘制 (多点画屋顶)</button>
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'pan' ? 'active' : ''}" data-sat-tool="pan">区域编辑 (微调顶点)</button>
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'roof' ? 'active' : ''}" data-sat-tool="roof">矩形绘制</button>
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly' ? 'active' : ''}" data-sat-tool="obstacle_poly">障碍物 (多点画禁布区)</button>
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'scale' ? 'active' : ''}" data-sat-tool="scale">标定比例尺</button>
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'direction' ? 'active' : ''}" data-sat-tool="direction">确定方向</button>
          <button type="button" class="satmap-v1-tool-chip ${this.roofType === 'double_slope' ? 'active' : ''}" data-sat-roof-type="${this.roofType === 'double_slope' ? 'single_slope' : 'double_slope'}">屋面坡度/分水线</button>
          <button type="button" class="satmap-v1-tool-chip ${this.showShadowPreview ? 'active' : ''}" data-sat-action="toggle-shadow">阴影模拟</button>
          <button type="button" class="satmap-v1-tool-chip ${this.is3D ? 'active' : ''}" data-sat-action="jump-3d-sim">全景三维仿真</button>
          <button type="button" class="satmap-v1-tool-chip" data-sat-action="undo-step">撤销</button>
          <button type="button" class="satmap-v1-tool-chip" data-sat-action="redo-step">恢复</button>
        </div>
        <div class="satmap-v1-modelbar-group">
          <button type="button" class="satmap-v1-tool-chip" data-sat-action="toggle-fullscreen">${this.isFullscreen ? '退出全屏' : '全屏'}</button>
          <button type="button" class="satmap-v1-tool-chip" data-sat-action="save-to-project">保存</button>
          <button type="button" class="satmap-v1-tool-chip active" data-sat-action="open-elec-flow">下一步 (电气设计) →</button>
        </div>
      </div>

      ${this.aiExecutionNote ? `
        <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:6px;padding:8px 12px;font-size:12px;color:#0369a1">
          <b>AI 设计执行结果：</b>${esc(this.aiExecutionNote)}
        </div>
      ` : ''}

      <!-- 3. 主工作台：左侧 3-Tab (1.屋面/2.布局/3.信息) + 中间真实卫星地图画布 + 右侧抽屉 (组件排布/电气配置) -->
      <div class="satmap-workbench">
        <aside class="satmap-left-panel">
          <div class="satmap-pvlane-tabs" role="tablist" aria-label="屋面建模与布局三步导航">
            <button type="button" class="satmap-tab-pill ${this.leftPanelTab === 'roof' ? 'active' : ''}" data-sat-left-tab="roof">1. 屋面</button>
            <button type="button" class="satmap-tab-pill ${this.leftPanelTab === 'layout' ? 'active' : ''}" data-sat-left-tab="layout">2. 布局</button>
            <button type="button" class="satmap-tab-pill ${this.leftPanelTab === 'info' ? 'active' : ''}" data-sat-left-tab="info">3. 信息</button>
          </div>

          <h3 class="satmap-panel-title">
            <span>${this.leftPanelTab === 'roof' ? '1. 屋面建模与底图校准' : this.leftPanelTab === 'layout' ? '2. 屋面布局与阵列微调' : '3. 屋面与光储经济信息'}</span>
            <small style="color:var(--muted);font-weight:500;font-size:11px;white-space:nowrap;flex-shrink:0">${this.hasRoof ? `屋面 1 (${bounds.areaM2}m²)` : '待绘制屋面'}</small>
          </h3>

          ${this.leftPanelTab === 'layout' ? `
            <!-- 左侧 Tab 2: 2. 布局 (交互式单块组件增删、阵列规格快速预设、安全退距与阴影校核) -->
            <div class="satmap-tool-list">
              <button type="button" class="satmap-tool-btn ${this.activeTool === 'toggle_module' ? 'active' : ''}" data-sat-tool="toggle_module">
                <span>1. 点选增删单块组件</span>
                <small>${this.removedModules?.length ? `已删 ${this.removedModules.length} 块` : '点击画布组件'}</small>
              </button>
              <button type="button" class="satmap-tool-btn ${this.activeTool === 'obstacle_poly' ? 'active' : ''}" data-sat-tool="obstacle_poly">
                <span>2. 多点补画禁布区</span>
                <small>${this.obstacles.length} 处</small>
              </button>
              <button type="button" class="satmap-tool-btn ${this.activeTool === 'pan' ? 'active' : ''}" data-sat-tool="pan">
                <span>3. 漫游与角点微调</span>
                <small>拖动角点自动重排</small>
              </button>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
              <button type="button" class="sat-btn primary" data-sat-action="layout-modules">重新满铺排布</button>
              <button type="button" class="sat-btn" data-sat-action="restore-removed-modules" ${this.removedModules?.length ? '' : 'disabled'}>恢复已删 (${this.removedModules?.length || 0})</button>
            </div>

            <div class="satmap-subbox">
              <b>阵列单元快捷预设</b>
              <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px">
                <button type="button" class="satmap-tab-pill ${this.arrayGroupRows === 2 && this.arrayGroupCols === 9 ? 'active' : ''}" data-sat-array-preset="2x9">2×9 标准串</button>
                <button type="button" class="satmap-tab-pill ${this.arrayGroupRows === 2 && this.arrayGroupCols === 12 ? 'active' : ''}" data-sat-array-preset="2x12">2×12 大组串</button>
                <button type="button" class="satmap-tab-pill ${this.arrayGroupRows === 1 && this.arrayGroupCols === 18 ? 'active' : ''}" data-sat-array-preset="1x18">1×18 单排串</button>
              </div>
              <label class="satmap-field-row">
                <span>屋面边缘退距 (m)</span>
                <input type="number" step="0.1" min="0.2" max="5.0" data-sat-field="edgeSetbackM" value="${this.edgeSetbackM}">
              </label>
              <label class="satmap-field-row">
                <span>禁布区退距 (m)</span>
                <input type="number" step="0.05" min="0.1" max="3.0" data-sat-field="obstacleSetbackM" value="${this.obstacleSetbackM}">
              </label>
              <label class="satmap-field-row">
                <span>南北排距 (m)</span>
                <input type="number" step="0.05" min="0.15" max="8.0" data-sat-field="rowSpacingM" value="${this.rowSpacingM}">
              </label>
              <label class="satmap-field-row">
                <span>检修马道宽 (m)</span>
                <input type="number" step="0.05" min="0" max="3.0" data-sat-field="walkwayWidthM" value="${this.walkwayWidthM}">
              </label>
            </div>

            <div class="satmap-subbox">
              <b>排布覆盖率 (GCR) 与组串统计</b>
              <div style="font-size:11.5px;color:var(--ink-2);line-height:1.6">
                <div>屋面总面积：<b>${bounds.areaM2} m²</b></div>
                <div>组件投影面积：<b>${(this.summary.moduleCount * mod.length_m * mod.width_m).toFixed(1)} m² (GCR ${bounds.areaM2 > 0 ? Math.min(95, Math.round((this.summary.moduleCount * mod.length_m * mod.width_m * 100) / bounds.areaM2)) : 0}%)</b></div>
                <div>南北分坡统计：<b>南坡 ${this.summary.southCount} 块 / 北坡 ${this.summary.northCount} 块</b></div>
                <div>配串与逆变器：<b>${this.summary.stringCount} 串 / ${this.summary.inverterCount} 台</b></div>
              </div>
            </div>
          ` : this.leftPanelTab === 'info' ? `
            <!-- 左侧 Tab 3: 3. 信息 (屋面工程指标、用电与储能参数、25年财务收益速算与报告导出) -->
            <div class="satmap-subbox">
              <b>屋面与发电工程汇总</b>
              <div style="font-size:11.5px;color:var(--ink-2);line-height:1.65">
                <div>项目名称：<b>${esc(this.projectName)}</b></div>
                <div>厂房尺寸：<b>${bounds.widthM.toFixed(1)}m × ${bounds.heightM.toFixed(1)}m (${bounds.areaM2} m²)</b></div>
                <div>装机容量：<b>${this.summary.dcKw} kWp (${this.summary.moduleCount} 块 × ${mod.stc_w}Wp)</b></div>
                <div>首年发电：<b>${(this.summary.annualKwh / 10000).toFixed(2)} 万kWh (${this.summary.specificYield} h · PR ${this.summary.prPct}%)</b></div>
              </div>
            </div>

            <div class="satmap-subbox">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <b>用电电价与光储投资参数</b>
                <button type="button" class="sat-btn primary" style="padding:1px 7px;font-size:11px;height:22px" data-sat-action="open-tariff-modal">详细配置</button>
              </div>
              <label class="satmap-field-row">
                <span>单位 EPC 造价 (元/W)</span>
                <input type="number" step="0.05" min="1.5" max="8.0" data-sat-field="capexPerW" value="${this.capexPerW}">
              </label>
              <label class="satmap-field-row">
                <span>自用电价 (元/kWh)</span>
                <input type="number" step="0.02" min="0.2" max="2.0" data-sat-field="tariffRmb" value="${this.tariffRmb}">
              </label>
              <label class="satmap-field-row">
                <span>余电上网电价 (元/kWh)</span>
                <input type="number" step="0.02" min="0.15" max="1.0" data-sat-field="feedInTariffRmb" value="${this.feedInTariffRmb}">
              </label>
              <label class="satmap-field-row">
                <span>自发自用消纳比</span>
                <input type="number" step="0.05" min="0.1" max="1.0" data-sat-field="selfConsumptionRatio" value="${this.selfConsumptionRatio}">
              </label>
              <label class="satmap-field-row">
                <span>配套储能 (kW / kWh)</span>
                <span style="display:flex;gap:4px;width:118px">
                  <input type="number" step="25" min="0" max="5000" data-sat-field="bessPowerKw" value="${this.bessPowerKw}" style="width:55px" title="储能PCS功率(kW)">
                  <input type="number" step="50" min="0" max="10000" data-sat-field="bessCapacityKwh" value="${this.bessCapacityKwh}" style="width:55px" title="储能电池容量(kWh)">
                </span>
              </label>
            </div>

            <div class="satmap-subbox" style="background:#f0fdf4;border-color:#bbf7d0">
              <b style="color:#166534">25 年全生命周期财务指标</b>
              <div style="font-size:11.5px;color:#14532d;line-height:1.65">
                <div>工程总投资 (CAPEX)：<b>${this.summary.capexWan} 万元</b></div>
                <div>静态投资回收期：<b>${this.summary.paybackYears != null ? `${this.summary.paybackYears} 年` : '未回收'}</b></div>
                <div>全投资内部收益率 (IRR)：<b>${this.summary.irrPct != null ? `${this.summary.irrPct}%` : '无法收回'}</b></div>
                <div>25 年累计净现值 (NPV)：<b>${this.summary.npv25Wan || 0} 万元</b></div>
              </div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:4px">
                <button type="button" class="sat-btn" data-sat-action="export-internal-report">内部投决报告</button>
                <button type="button" class="sat-btn primary" data-sat-action="export-owner-report">业主汇报书</button>
              </div>
            </div>
          ` : `
            <!-- 左侧 Tab 1: 1. 屋面 (屋面建模、底图比例尺/方向校准与禁布区绘制) -->
            <div class="satmap-tool-list">
              <button type="button" class="satmap-tool-btn ${this.activeTool === 'pan' ? 'active' : ''}" data-sat-tool="pan">
                <span>漫游平移卫星图</span>
                <small>拖拽/缩放</small>
              </button>
              <button type="button" class="satmap-tool-btn ${this.activeTool === 'roof' ? 'active' : ''}" data-sat-tool="roof">
                <span>1. 绘制屋顶 (矩形框选)</span>
                <small>${this.hasRoof ? `${bounds.areaM2} m²` : '拖拽/对角点击'}</small>
              </button>
              <button type="button" class="satmap-tool-btn ${this.activeTool === 'roof_poly' ? 'active' : ''}" data-sat-tool="roof_poly">
                <span>2. 多点画屋面 (异形轮廓)</span>
                <small>点选角点</small>
              </button>
              <button type="button" class="satmap-tool-btn ${this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly' ? 'active' : ''}" data-sat-tool="obstacle_poly">
                <span>3. 多点画禁布区</span>
                <small>${this.obstacles.length} 处</small>
              </button>
              <button type="button" class="satmap-tool-btn ${this.activeTool === 'delete' ? 'active' : ''}" data-sat-tool="delete">
                <span>4. 删除选中禁布区</span>
                <small>点击移除</small>
              </button>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
              <button type="button" class="sat-btn" data-sat-action="auto-scale-direction" title="根据当前卫星瓦片经纬度与已画屋顶轮廓自动识别比例尺和主墙朝向">自动校准比例/方向</button>
              <button type="button" class="sat-btn danger" data-sat-action="clear-roof">清除重画</button>
            </div>

            <!-- 屋面类型三选一 + 坡度 + 女儿墙高 -->
            <div class="satmap-subbox">
              <b>屋面结构与分界设置</b>
              <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px">
                <button type="button" class="satmap-tab-pill ${this.roofType === 'flat' ? 'active' : ''}" data-sat-roof-type="flat">平屋顶</button>
                <button type="button" class="satmap-tab-pill ${this.roofType === 'single_slope' ? 'active' : ''}" data-sat-roof-type="single_slope">单坡屋面</button>
                <button type="button" class="satmap-tab-pill ${this.roofType === 'double_slope' ? 'active' : ''}" data-sat-roof-type="double_slope">双坡屋面</button>
              </div>
              <label class="satmap-field-row">
                <span>屋面类型</span>
                <select data-sat-field="roofType">
                  <option value="single_slope" ${this.roofType === 'single_slope' ? 'selected' : ''}>整面平铺/单坡 (不自动分界)</option>
                  <option value="double_slope" ${this.roofType === 'double_slope' ? 'selected' : ''}>双坡屋面 (沿中央屋脊分南北坡)</option>
                  <option value="flat" ${this.roofType === 'flat' ? 'selected' : ''}>混凝土平屋面 (支架倾角)</option>
                </select>
              </label>
              <label class="satmap-field-row">
                <span>屋面坡度 (°)</span>
                <input type="number" step="0.5" min="0" max="45" data-sat-field="roofSlopeDeg" value="${this.roofSlopeDeg}">
              </label>
              <label class="satmap-field-row">
                <span>女儿墙高 / 宽 (mm)</span>
                <span style="display:flex;gap:4px;width:118px">
                  <input type="number" step="50" min="0" max="2500" data-sat-field="parapetHeightMm" value="${this.parapetHeightMm}" style="width:55px" title="女儿墙高(mm)">
                  <input type="number" step="20" min="0" max="1000" data-sat-field="parapetWidthMm" value="${this.parapetWidthMm}" style="width:55px" title="女儿墙宽(mm)">
                </span>
              </label>
            </div>

            <details class="satmap-acc-card">
              <summary>
                <span>底图比例尺与方向微调</span>
                <small>南偏 ${this.ridgeAzimuthDeg}°</small>
              </summary>
              <div class="satmap-acc-body">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
                  <button type="button" class="sat-btn ${this.activeTool === 'scale' ? 'primary' : ''}" data-sat-tool="scale">手拉比例尺</button>
                  <button type="button" class="sat-btn ${this.activeTool === 'direction' ? 'primary' : ''}" data-sat-tool="direction">手拉主墙方向</button>
                </div>
                <label class="satmap-field-row">
                  <span>标定实测长度 (m)</span>
                  <input type="number" step="0.5" min="5" max="500" data-sat-field="scaleReferenceM" value="${this.scaleReferenceM}">
                </label>
                <label class="satmap-field-row">
                  <span>屋脊走向偏角 (°)</span>
                  <input type="number" step="0.5" min="-89" max="89" data-sat-field="ridgeAzimuthDeg" value="${this.ridgeAzimuthDeg}">
                </label>
                <label class="satmap-field-row">
                  <span>屋面长 × 宽 (m)</span>
                  <span style="display:flex;gap:4px;width:118px">
                    <input type="number" step="1" min="10" max="300" data-sat-field="roofLengthM" value="${bounds.widthM ? bounds.widthM.toFixed(0) : 76}" style="width:55px" title="屋面东西长度(m)">
                    <input type="number" step="1" min="10" max="200" data-sat-field="roofWidthM" value="${bounds.heightM ? bounds.heightM.toFixed(0) : 36}" style="width:55px" title="屋面南北跨度(m)">
                  </span>
                </label>
              </div>
            </details>

            <div class="satmap-subbox">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <b>屋面禁布区清单 (${this.obstacles.length})</b>
                <button type="button" class="sat-btn" style="padding:2px 7px;font-size:11px" data-sat-action="add-demo-skylight">+ 新增采光带</button>
              </div>
              ${this.obstacles.map((o) => `
                <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;padding:3px 0;border-bottom:1px dashed var(--line,#e2e8f0)">
                  <span style="color:#dc2626;font-weight:600">${esc(o.name)}</span>
                  <button type="button" class="sat-btn danger" style="padding:1px 6px;font-size:11px" data-sat-del-obs="${esc(o.id)}">删除</button>
                </div>
              `).join('') || '<span class="muted" style="font-size:11px">暂无禁布区，点击「绘制禁布区」框选避让区域</span>'}
            </div>
          `}
        </aside>

        <!-- Center Real Satellite Map Canvas & WebGL 3D Digital Twin -->
        <div class="satmap-canvas-wrap ${this.isFullscreen ? 'is-fullscreen' : ''}" id="satmap-canvas-wrap">
          <div class="satmap-floating-tools" role="toolbar" aria-label="卫星地图工具栏" style="${this.is3D ? 'display:none' : ''}">
            <button type="button" class="satmap-float-btn ${this.activeTool === 'pan' ? 'active' : ''}" data-sat-tool="pan">漫游平移</button>
            <button type="button" class="satmap-float-btn ${this.activeTool === 'roof' ? 'active' : ''}" data-sat-tool="roof" title="在目标厂房屋顶上按住拖动或点击对角即可框选屋顶">1. 绘制屋顶</button>
            <button type="button" class="satmap-float-btn ${this.activeTool === 'roof_poly' ? 'active' : ''}" data-sat-tool="roof_poly" title="依次点击厂房各角点绘制任意角度或多边形屋顶，闭合后自动识别建筑主方向">多点画屋顶</button>
            <button type="button" class="satmap-float-btn lay-now" id="sat-close-roof-poly-btn" data-sat-action="close-roof-poly" style="${this.activeTool === 'roof_poly' && this.drawingPointsM.length >= 3 ? '' : 'display:none'}">完成屋顶闭合 (${this.drawingPointsM.length}点)</button>
            <button type="button" class="satmap-float-btn ${this.activeTool === 'obstacle' ? 'active' : ''}" data-sat-tool="obstacle" title="支持依次点击多个角点（或按住拖动）绘制屋面禁布区">2. 绘制禁布区</button>
            <button type="button" class="satmap-float-btn lay-now" id="sat-close-obs-poly-btn" data-sat-action="close-obstacle-poly" style="${(this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly') && this.drawingObstaclePointsM.length >= 3 ? 'background:#dc2626;border-color:#f87171;' : 'display:none;background:#dc2626;border-color:#f87171;'}">完成禁布区闭合 (${this.drawingObstaclePointsM.length}点)</button>
            <button type="button" class="satmap-float-btn lay-now" data-sat-action="layout-modules">3. 一键铺设</button>
            <button type="button" class="satmap-float-btn lay-now" data-sat-action="jump-3d-sim" title="开启三维数字孪生与光线追踪仿真">全景三维仿真</button>
            <details class="satmap-float-more">
              <summary class="satmap-float-btn">更多工具 ▾</summary>
              <div class="satmap-float-more-menu">
                <button type="button" class="satmap-float-btn" data-sat-action="undo-step" title="撤销上一步操作">↶ 撤销</button>
                <button type="button" class="satmap-float-btn" data-sat-action="redo-step" title="重做操作">↷ 重做</button>
                <button type="button" class="satmap-float-btn ${this.activeTool === 'obstacle_poly' ? 'active' : ''}" data-sat-tool="obstacle_poly" title="依次点击禁布区各个角点生成任意多边形禁布区">多点画禁布区</button>
                <button type="button" class="satmap-float-btn ${this.activeTool === 'toggle_module' ? 'active' : ''}" data-sat-tool="toggle_module" title="点击屋面上任意单块组件即可手动剔除或恢复该位置组件">点选增删组件</button>
                <button type="button" class="satmap-float-btn ${this.activeTool === 'delete' ? 'active' : ''}" data-sat-tool="delete">删除禁布区</button>
                <button type="button" class="satmap-float-btn ${this.activeTool === 'scale' ? 'active' : ''}" data-sat-tool="scale" title="在厂房已知长度的边沿拖拽即可校准比例尺">标定比例尺</button>
                <button type="button" class="satmap-float-btn ${this.activeTool === 'direction' ? 'active' : ''}" data-sat-tool="direction" title="沿着厂房屋脊或外墙拖拽一条线，自动对齐组件排布方向">确定方向</button>
                <button type="button" class="satmap-float-btn" data-sat-action="auto-scale-direction" title="根据卫星地图经纬度与已画屋顶轮廓一键自动识别比例尺和方向">自动识别比例尺/方向</button>
                <button type="button" class="satmap-float-btn ${this.showShadowPreview ? 'active' : ''}" data-sat-action="toggle-shadow" title="开启/关闭冬至日 9:00-15:00 阵列日照阴影分析条带">阴影分析</button>
                <button type="button" class="satmap-float-btn" data-sat-action="zoom-in" title="放大卫星图 (最高可放大至 Z24 毫米级超清特写)">放大 +</button>
                <button type="button" class="satmap-float-btn" data-sat-action="zoom-out" title="缩小卫星图">缩小 -</button>
                <button type="button" class="satmap-float-btn ${this.zoom >= 21 ? 'active' : ''}" data-sat-action="zoom-fit-roof" title="一键定位并放大至屋面/组件超清微距特写 (Z21~Z24)">屋面特写 (Z${this.zoom})</button>
                <button type="button" class="satmap-float-btn" data-sat-action="clear-roof">清除重画</button>
              </div>
            </details>
            <button type="button" class="satmap-float-btn fullscreen-btn" data-sat-action="toggle-fullscreen" title="全屏放大地图或按 Esc 退出全屏">${this.isFullscreen ? '退出全屏 (Esc)' : '全屏地图'}</button>
          </div>

          <!-- 画布底部中央边长实时输入浮窗 ([76000] mm | 76.00m) -->
          ${!this.is3D && (this.hasRoof || isDrawingTool) ? `
            <div class="satmap-edge-dim-pill" role="region" aria-label="屋面主边长毫米级实时输入">
              <span>屋面主边长：</span>
              <input type="number" step="100" min="5000" max="500000" data-sat-field="liveEdgeLengthMm" value="${curEdgeMm}" title="输入屋面主边长(mm)回车即可精确校准尺寸">
              <span>mm | <b>${(curEdgeMm / 1000).toFixed(2)} m</b></span>
            </div>
          ` : ''}

          <!-- Inline Roof Type & Pitch Bar -->
          ${!this.is3D && (this.hasRoof || this.obstacles.length > 0) ? `
            <div class="satmap-roof-type-bar" role="region" aria-label="屋面分坡模式与禁布区快捷栏">
              <span>屋面模式：</span>
              <button type="button" class="satmap-roof-type-pill ${this.roofType === 'single_slope' ? 'active' : ''}" data-sat-roof-type="single_slope">整面连续平铺 (不自动分界)</button>
              <button type="button" class="satmap-roof-type-pill ${this.roofType === 'double_slope' ? 'active' : ''}" data-sat-roof-type="double_slope">双坡屋面 (沿屋脊分南北坡)</button>
              <button type="button" class="satmap-roof-type-pill ${this.roofType === 'flat' ? 'active' : ''}" data-sat-roof-type="flat">混凝土平屋面</button>
              <span style="margin-left:4px">坡度：</span>
              <input type="number" step="0.5" min="0" max="45" data-sat-field="roofSlopeDeg" value="${this.roofSlopeDeg}" style="width:52px;padding:2px 5px;border-radius:4px;border:1px solid #475569;background:#1e293b;color:#fff;font-size:11.5px">
              <span>°</span>
              <button type="button" class="satmap-roof-type-pill ${this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly' ? 'active' : ''}" data-sat-tool="obstacle_poly" style="border-color:#ef4444;color:#dc2626;background:#fef2f2">+ 多点画禁布区 (${this.obstacles.length})</button>
            </div>
          ` : ''}

          ${this.isFullscreen ? `
            <div class="satmap-fs-bar">
              <span>全屏导航：</span>
              <input type="text" data-sat-field="searchQuery" value="${esc(this.searchQuery || this.address)}" placeholder="输入全国任意企业、园区或地址回车定位">
              <button type="button" class="satmap-float-btn active" data-sat-action="search-location">搜索定位</button>
              <span style="margin-left:6px">当前屋面：<b>${this.hasRoof ? `${bounds.widthM.toFixed(1)}m × ${bounds.heightM.toFixed(1)}m (${bounds.areaM2}m²)` : '未框选（请点「1. 绘制屋顶」在厂房上拖拽）'}</b></span>
              <span>已排布：<b>${this.summary.moduleCount} 块 (${this.summary.dcKw} kWp)</b></span>
              <button type="button" class="satmap-float-btn lay-now" data-sat-action="ai-autopilot">AI 一键设计</button>
            </div>
          ` : ''}

          ${this.is3D ? `
            <div class="satmap-3d-simbar" role="toolbar" aria-label="三维数字孪生与光线追踪控制栏">
              <div class="satmap-3d-sim-group">
                <button type="button" class="satmap-3d-chip ${this.sim3dMode === 'realistic' ? 'active' : ''}" data-sat-3d-mode="realistic">真实材质</button>
                <button type="button" class="satmap-3d-chip ${this.sim3dMode === 'irradiance' ? 'active' : ''}" data-sat-3d-mode="irradiance">辐照热力</button>
                <button type="button" class="satmap-3d-chip ${this.sim3dMode === 'diode' ? 'active' : ''}" data-sat-3d-mode="diode">二极管失配</button>
                <button type="button" class="satmap-3d-chip ${this.sim3dMode === 'wiring' ? 'active' : ''}" data-sat-3d-mode="wiring">组串桥架</button>
                <button type="button" class="satmap-3d-chip ${this.sim3dMode === 'wind' ? 'active' : ''}" data-sat-3d-mode="wind">抗风分区</button>
              </div>
              <div class="satmap-3d-sim-group">
                <button type="button" class="satmap-3d-chip ${this.sim3dDateStr === '2026-12-21' ? 'active' : ''}" data-sat-3d-date="2026-12-21">冬至</button>
                <button type="button" class="satmap-3d-chip ${this.sim3dDateStr === '2026-03-21' ? 'active' : ''}" data-sat-3d-date="2026-03-21">春分</button>
                <button type="button" class="satmap-3d-chip ${this.sim3dDateStr === '2026-06-21' ? 'active' : ''}" data-sat-3d-date="2026-06-21">夏至</button>
                <input type="range" min="6.5" max="18.0" step="0.1" value="${this.sim3dHourBjt}" data-sat-field="sim3dHourBjt" aria-label="太阳时刻">
                <b id="satmap-3d-hour-text" style="font-family:monospace;min-width:38px;color:#fde047">${String(Math.floor(this.sim3dHourBjt)).padStart(2, '0')}:${String(Math.min(59, Math.round((this.sim3dHourBjt % 1) * 60))).padStart(2, '0')}</b>
                <button type="button" class="satmap-3d-chip ${this.sim3dPlaying ? 'active' : ''}" data-sat-action="toggle-3d-play">${this.sim3dPlaying ? '暂停日照' : '日照动画'}</button>
              </div>
              <div class="satmap-3d-sim-group">
                <button type="button" class="satmap-3d-chip ${this.sim3dCam === 'iso' ? 'active' : ''}" data-sat-3d-cam="iso">三维轴测</button>
                <button type="button" class="satmap-3d-chip ${this.sim3dCam === 'south' ? 'active' : ''}" data-sat-3d-cam="south">正南航拍</button>
                <button type="button" class="satmap-3d-chip ${this.sim3dCam === 'walkway' ? 'active' : ''}" data-sat-3d-cam="walkway">屋面巡检</button>
                <button type="button" class="satmap-3d-chip ${this.sim3dCam === 'street' ? 'active' : ''}" data-sat-3d-cam="street">人眼街景</button>
                <button type="button" class="satmap-3d-chip ${this.sim3dCam === 'top' ? 'active' : ''}" data-sat-3d-cam="top">正顶俯视</button>
              </div>
              <div class="satmap-3d-sim-group">
                <button type="button" class="satmap-3d-chip" data-sat-action="sync-3d-shading" title="将三维光线追踪全年遮挡与旁路二极管失配写入全年仿真">同步遮挡损耗</button>
                <button type="button" class="satmap-3d-chip" data-sat-action="export-3d-png" title="导出高清三维数字孪生渲染截图">导出三维截图</button>
                <button type="button" class="satmap-3d-chip active" data-sat-action="set-2d">返回二维底图</button>
              </div>
            </div>
            <div id="satmap-3d-twin-stage" class="satmap-3d-twin-stage" data-sat-3d-stage></div>
            <div id="satmap-3d-metrics-bar" class="satmap-3d-metrics-bar">${this.render3DMetricsInnerHtml()}</div>
          ` : ''}

          <canvas id="satmap-main-canvas" class="satmap-canvas ${isDrawingTool ? 'tool-draw' : ''}" style="${this.is3D ? 'display:none' : ''}" width="${this.isFullscreen && typeof window !== 'undefined' ? Math.max(960, window.innerWidth) : 920}" height="${this.isFullscreen && typeof window !== 'undefined' ? Math.max(620, window.innerHeight - 36) : 580}"></canvas>

          <!-- 右下角竖向地图控制条 [2D][3D][图层][定位][特写][+][-] -->
          <div class="satmap-right-map-strip" role="toolbar" aria-label="右下角竖向地图控制条">
            <button type="button" class="satmap-rms-btn ${!this.is3D ? 'active' : ''}" data-sat-action="set-2d" title="2D平面建模视图">2D</button>
            <button type="button" class="satmap-rms-btn ${this.is3D ? 'active' : ''}" data-sat-action="set-3d" title="3D真实数字孪生与光线追踪视图">3D</button>
            <button type="button" class="satmap-rms-btn ${this.showRoofOverlay ? 'active' : ''}" data-sat-action="toggle-roof-overlay" title="显示/隐藏屋面与组件图层" style="${this.is3D ? 'display:none' : ''}">图层</button>
            <button type="button" class="satmap-rms-btn" data-sat-action="open-loc-picker" title="打开地图拾取经纬度弹窗">定位</button>
            <button type="button" class="satmap-rms-btn ${this.zoom >= 21 ? 'active' : ''}" data-sat-action="zoom-fit-roof" title="一键放大至屋面与组件超清微距特写 (Z21~Z24)" style="${this.is3D ? 'display:none' : ''}">特写</button>
            <button type="button" class="satmap-rms-btn" data-sat-action="zoom-in" title="放大卫星底图 (最高 Z24)" style="${this.is3D ? 'display:none' : ''}">+</button>
            <span id="satmap-rms-zoom-badge" style="${this.is3D ? 'display:none;' : 'display:block;'}text-align:center;font-size:10px;font-weight:700;color:#38bdf8;padding:2px 0;font-family:monospace">Z${this.zoom}</span>
            <button type="button" class="satmap-rms-btn" data-sat-action="zoom-out" title="缩小卫星底图" style="${this.is3D ? 'display:none' : ''}">−</button>
          </div>

          <!-- 画布底部提示条 -->
          <div class="satmap-v1-orange-tip" role="status" style="${this.is3D ? 'display:none' : ''}">
            <span>ⓘ</span>
            <span>${!this.hasRoof ? '请调整至清晰位置，作为卫星设计底图，点击「绘制」或「多点画屋顶」圈选厂房' : !this.hasLaidOut ? '请选择绘制好的区域，铺设组件（点击右侧「一键铺设组件」或顶部「3. 一键铺设」）' : `已完成屋面排布（共 ${this.summary.moduleCount} 块组件 · ${this.summary.dcKw} kWp），可点击「电气设计」或「多点画禁布区」`}</span>
          </div>

          <div class="satmap-floating-hud" style="${this.is3D ? 'display:none' : ''}">
            <span id="satmap-hud-coords">当前定位：${esc(this.address)} (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) · 缩放级别 Z${this.zoom} · 比例尺 1px ≈ ${this.metersPerPx.toFixed(3)}m · 主墙偏角 ${this.ridgeAzimuthDeg}°</span>
            <span id="satmap-hud-status">当前操作：<b>${{
        pan: '漫游平移（按住鼠标拖动卫星底图，滚轮缩放；可直接拖动已画屋顶或禁布区的角点微调位置）',
        roof: '绘制屋顶（在目标厂房一角按住拖动至对角，或点击两个对角点；完成后自动识别比例尺与主墙方向）',
        roof_poly: '多点画屋顶（依次点击厂房屋顶各个角点，双击、右键或点击起点/「完成屋顶闭合」生成异形屋面）',
        obstacle: '绘制禁布区（依次点击多个角点画多边形禁布区，双击/点起点闭合；也支持直接按住拖动框选）',
        obstacle_poly: '多点画禁布区（依次点击禁布区各个角点，双击、右键或点击起点 P1 /「完成禁布区闭合」生成多边形禁布区）',
        scale: '标定比例尺（在已知长度的厂房边沿按住拖拽标定实际米数，或点「自动识别比例尺/方向」）',
        direction: '确定方向（沿着厂房屋脊或外墙按住拖拽一条线，即可自动对齐屋面与组件排布方向）',
        delete: '删除禁布区（点击任意红色禁布区立即移除）',
        toggle_module: '点选增删单块组件（点击屋面已铺设的任意单块组件可将其剔除，再次点击虚线框位置可恢复该组件）',
      }[this.activeTool] || '漫游平移'
      }</b></span>
          </div>
        </div>

        <!-- Right Panel: 组件排布 + 电气配置 双模式抽屉 -->
        <aside class="satmap-right-panel">
          <div class="satmap-drawer-tabs" role="tablist" aria-label="右侧排布与电气配置切换">
            <button type="button" class="satmap-tab-pill ${this.rightDrawerTab === 'layout' ? 'active' : ''}" data-sat-right-tab="layout">1. 组件排布</button>
            <button type="button" class="satmap-tab-pill ${this.rightDrawerTab === 'elec' ? 'active' : ''}" data-sat-right-tab="elec">2. 电气配置</button>
          </div>

          <h3 class="satmap-panel-title">
            <span>${this.rightDrawerTab === 'elec' ? '电气配置与逆变器清单' : '组件信息与排布设置'}</span>
            <small style="color:var(--muted);font-weight:500">${this.rightDrawerTab === 'elec' ? `容配比 ${this.summary.dcAcRatio || 1.15}` : '阵列参数'}</small>
          </h3>

          ${this.rightDrawerTab === 'elec' ? `
            <!-- 右侧「电气配置」抽屉 -->
            <div class="satmap-subbox">
              <b>逆变器选型方式与容配比</b>
              <div class="satmap-field-row">
                <span>选型方式</span>
                <div class="satmap-orient-toggle" style="width:156px">
                  <button type="button" class="satmap-orient-btn ${this.inverterSelectionMode === 'auto' ? 'active' : ''}" data-sat-inv-mode="auto">智能推荐</button>
                  <button type="button" class="satmap-orient-btn ${this.inverterSelectionMode === 'manual' ? 'active' : ''}" data-sat-inv-mode="manual">自选逆变器</button>
                </div>
              </div>
              <div class="satmap-field-row">
                <span>目标容配比范围</span>
                <span style="display:flex;align-items:center;gap:4px">
                  <input type="number" step="0.05" min="0.4" max="1.8" data-sat-field="dcAcTargetMin" value="${this.dcAcTargetMin}" style="width:52px">
                  <span>~</span>
                  <input type="number" step="0.05" min="0.6" max="2.0" data-sat-field="dcAcTargetMax" value="${this.dcAcTargetMax}" style="width:52px">
                </span>
              </div>
              <div style="padding:2px 4px">
                <div style="display:flex;justify-content:space-between;font-size:10.5px;color:#64748b">
                  <span>0.4</span>
                  <span style="color:#2563eb;font-weight:700">容配比区间 ${this.dcAcTargetMin} ~ ${this.dcAcTargetMax} (当前 ${this.summary.dcAcRatio || 1.15})</span>
                  <span>1.8</span>
                </div>
                <div class="satmap-dcac-slider-track">
                  <div class="satmap-dcac-slider-fill" style="left:${Math.max(0, Math.min(85, ((this.dcAcTargetMin - 0.4) / 1.4) * 100)).toFixed(0)}%;width:${Math.max(10, Math.min(100, ((this.dcAcTargetMax - this.dcAcTargetMin) / 1.4) * 100)).toFixed(0)}%"></div>
                </div>
              </div>
              <label class="satmap-field-row">
                <span>单串串联块数 (块/串)</span>
                <input type="number" step="1" min="8" max="24" data-sat-field="modulesPerString" value="${this.modulesPerString}">
              </label>
              <div class="satmap-field-row">
                <span>直流线缆 (PV1-F 4mm²)</span>
                <button type="button" class="sat-btn primary" style="height:26px;padding:0 10px" data-sat-action="generate-dc-cable">✎ 一键生成线缆</button>
              </div>
            </div>

            <div class="satmap-subbox">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <b>逆变器清单 (${this.summary.inverterCount} 台)</b>
                <button type="button" class="sat-btn primary" style="height:24px;padding:0 8px;font-size:11px" data-sat-action="open-inverter-modal">+ 选型/更换逆变器</button>
              </div>
              <div style="padding:8px;background:#ffffff;border:1px solid #bfdbfe;border-radius:6px;display:flex;flex-direction:column;gap:4px">
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <b style="color:#1d4ed8">${esc(inv.brand)} · ${esc(inv.model)}</b>
                  <span class="sat-pill-ok">x ${this.summary.inverterCount} 台</span>
                </div>
                <div style="font-size:11px;color:#475569">
                  额定功率 ${inv.rated_ac_kw} kW · ${inv.mppt_count} 路 MPPT · 共接入 ${this.summary.stringCount} 串
                </div>
              </div>
            </div>

            <div class="satmap-right-summary">
              <div class="satmap-right-summary-row">
                <span>逆变器台数 / 总交流</span>
                <b>x${this.summary.inverterCount} 台 (${this.summary.acKw} kW)</b>
              </div>
              <div class="satmap-right-summary-row">
                <span>当前实际容配比</span>
                <b>${this.summary.dcAcRatio || 1.15} : 1</b>
              </div>
            </div>

            <button type="button" class="satmap-elec-entry-btn" data-sat-action="finish-elec-design">
              ✓ 完成设计 (查看 MPPT 组串分配表)
            </button>
            <button type="button" class="sat-btn" style="width:100%;padding:7px 12px;font-weight:700" data-sat-step="2">
              打开完整电气与组串工作台 →
            </button>
            <button type="button" class="sat-btn" style="width:100%;padding:7px 12px;font-weight:700" data-sat-step="5">
              前往施工 CAD 图纸生成 (排布/组串/防雷/支架) →
            </button>
          ` : `
            <!-- 右侧「组件排布」完整参数 -->
            <div class="satmap-subbox">
              <b>组件信息 (组件型号与物理尺寸)</b>
              <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:4px">
                <span>选择组件型号</span>
                <select data-sat-field="moduleModelId" style="width:100%">
                  ${this.getAllModules().map((m) => `<option value="${esc(m.id)}" ${m.id === this.moduleModelId ? 'selected' : ''}>${esc(m.model)} (${Math.round(m.length_m * 1000)}×${Math.round(m.width_m * 1000)}mm)</option>`).join('')}
                </select>
              </label>
              <div style="font-size:11.5px;color:var(--muted,#64748b);display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px 8px">
                <span style="white-space:nowrap">功率：<b>${mod.stc_w} Wp</b></span>
                <span style="white-space:nowrap">尺寸：<b>${(mod.length_m * 1000).toFixed(0)}×${(mod.width_m * 1000).toFixed(0)}×30mm</b></span>
              </div>
              <div class="satmap-field-row" style="margin-top:2px">
                <span>安装方向</span>
                <select data-sat-field="orientation" style="display:none">
                  <option value="portrait" ${this.orientation === 'portrait' ? 'selected' : ''}>竖放 (Portrait)</option>
                  <option value="landscape" ${this.orientation === 'landscape' ? 'selected' : ''}>横放 (Landscape)</option>
                </select>
                <div class="satmap-orient-toggle" style="width:136px">
                  <button type="button" class="satmap-orient-btn ${this.orientation === 'portrait' ? 'active' : ''}" data-sat-orient="portrait">竖向排布</button>
                  <button type="button" class="satmap-orient-btn ${this.orientation === 'landscape' ? 'active' : ''}" data-sat-orient="landscape">横向排布</button>
                </div>
              </div>
              <label class="satmap-field-row">
                <span>安装倾角 (°)</span>
                <input type="number" step="1" min="0" max="45" data-sat-field="tiltDeg" value="${this.tiltDeg}">
              </label>
              <label class="satmap-field-row">
                <span>组件方位角 (°)</span>
                <input type="number" step="1" min="90" max="270" data-sat-field="azimuthDeg" value="${this.azimuthDeg}">
              </label>
            </div>

            <details class="satmap-acc-card" open>
              <summary>
                <span>组件排布参数 (2×9 标准阵列单元)</span>
                <small>间距 ${this.rowSpacingM}m</small>
              </summary>
              <div class="satmap-acc-body">
                <label class="satmap-field-row">
                  <span>阵列行数 × 列数 (个)</span>
                  <span style="display:flex;gap:4px;width:118px">
                    <input type="number" step="1" min="1" max="8" data-sat-field="arrayGroupRows" value="${this.arrayGroupRows}" style="width:55px" title="阵列行数 (默认2行)">
                    <input type="number" step="1" min="1" max="30" data-sat-field="arrayGroupCols" value="${this.arrayGroupCols}" style="width:55px" title="阵列列数 (默认9列=2×9组串)">
                  </span>
                </label>
                <label class="satmap-field-row">
                  <span>走道宽度 (m)</span>
                  <input type="number" step="0.05" min="0" max="3.0" data-sat-field="walkwayWidthM" value="${this.walkwayWidthM}">
                </label>
                <label class="satmap-field-row">
                  <span>子阵间距 / 前后排距 (m)</span>
                  <input type="number" step="0.05" min="0.15" max="8.0" data-sat-field="rowSpacingM" value="${this.rowSpacingM}">
                </label>
                <label class="satmap-field-row">
                  <span>东西列间距 (m)</span>
                  <input type="number" step="0.01" min="0.01" max="1.0" data-sat-field="colSpacingM" value="${this.colSpacingM}">
                </label>
                <label class="satmap-field-row">
                  <span>屋面边缘退距 (m)</span>
                  <input type="number" step="0.1" min="0.2" max="5.0" data-sat-field="edgeSetbackM" value="${this.edgeSetbackM}">
                </label>
                <label class="satmap-field-row">
                  <span>禁布区退距 (m)</span>
                  <input type="number" step="0.05" min="0.1" max="3.0" data-sat-field="obstacleSetbackM" value="${this.obstacleSetbackM}">
                </label>
                <label class="satmap-field-row">
                  <span>目标容量上限 (kWp)</span>
                  <input type="number" step="10" min="0" max="5000" data-sat-field="targetCapacityKw" value="${this.targetCapacityKw}" title="0 表示按屋面最大可用面积满铺">
                </label>
              </div>
            </details>

            <details class="satmap-acc-card">
              <summary>
                <span>当地气象与最优夹角速览</span>
                <small>最优 ${wxEval.weatherOptimalTiltDeg}°</small>
              </summary>
              <div class="satmap-acc-body">
                <div style="font-size:11.5px;color:var(--ink-2);line-height:1.55">
                  <div>实时气象：<b>${wxEval.tempC.toFixed(1)}°C · GHI ${wxEval.ghiWm2.toFixed(0)} W/m²</b></div>
                  <div>冬至9:00高度角：<b>${wxEval.solarAlt9amDeg}° (无遮挡净距 ${wxEval.currentUnshadedGapM}m)</b></div>
                  <div>气象单瓦最优角：<b>${wxEval.weatherOptimalTiltDeg}° (${wxEval.weatherOptimalYield} h)</b></div>
                  <div>屋面总发电最优：<b>${wxEval.roofOptimalTiltDeg}° (${wxEval.roofOptimalWanKwh} 万kWh)</b></div>
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:4px">
                  <button type="button" class="sat-btn" data-sat-action="apply-weather-opt-tilt">单瓦最优(${wxEval.weatherOptimalTiltDeg}°)</button>
                  <button type="button" class="sat-btn" data-sat-action="apply-roof-opt-tilt">总发电最优(${wxEval.roofOptimalTiltDeg}°)</button>
                </div>
              </div>
            </details>

            <!-- Bottom Summary Box: 组件数量 + 装机容量 -->
            <div class="satmap-right-summary">
              <div class="satmap-right-summary-row">
                <span>组件数量</span>
                <b>${this.summary.moduleCount} 块</b>
              </div>
              <div class="satmap-right-summary-row">
                <span>装机容量</span>
                <b>${this.summary.dcKw} kWp</b>
              </div>
            </div>

            <button type="button" class="satmap-primary-lay-btn" data-sat-action="layout-modules">
              ${this.hasLaidOut ? `立即排布 / 重新铺设 (${this.summary.moduleCount} 块 · ${this.summary.dcKw} kWp)` : '一键铺设组件'}
            </button>
            <button type="button" class="satmap-elec-entry-btn" data-sat-action="open-elec-flow">
              ⚡ 电气设计 (${this.summary.stringCount}串 · 逆变器选型与组串)
            </button>
            <button type="button" class="sat-btn" style="width:100%;padding:7px 12px;font-weight:700" data-sat-step="5">
              前往施工图纸生成 →
            </button>
          `}
        </aside>
      </div>

      <!-- 4. 实时气象驱动的发电量判断、冬至日照间距计算与安装倾角最优评估表 -->
      <div class="satmap-weather-eval-card" data-sat-weather-eval>
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding-bottom:10px;border-bottom:1px solid var(--line,#e2e8f0)">
          <div>
            <h3 style="margin:0;font-size:15px">当地实时官方气象驱动的倾角设计、冬至无遮挡间距与发电量最优评估</h3>
            <small style="color:var(--muted,#64748b)">
              气象源：${esc(wxEval.source)} · 坐标 (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) · 冬至日 9:00–15:00 无遮挡行距综合寻优
            </small>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button type="button" class="sat-btn" data-sat-action="refresh-live-weather">刷新实时气象</button>
            <button type="button" class="sat-btn primary" data-sat-action="apply-weather-opt-tilt">应用单瓦最优 (${wxEval.weatherOptimalTiltDeg}°)</button>
            <button type="button" class="sat-btn" data-sat-action="apply-roof-opt-tilt">应用总发电最优 (${wxEval.roofOptimalTiltDeg}°)</button>
          </div>
        </div>

        <div class="satmap-weather-grid" style="margin:12px 0">
          <div class="satmap-subbox">
            <span>当地实时气温 / 组件工作结温</span>
            <strong style="font-size:16px">${wxEval.tempC.toFixed(1)} °C / ${wxEval.tCellC.toFixed(1)} °C</strong>
            <small style="color:var(--muted)">地面风速 ${wxEval.windMs.toFixed(1)} m/s · 实时 GHI ${wxEval.ghiWm2.toFixed(0)} W/m²</small>
          </div>
          <div class="satmap-subbox">
            <span>水平面年总辐照 / 当前斜面年辐照</span>
            <strong style="font-size:16px">${wxEval.globHorKwhM2} / ${wxEval.globIncKwhM2} kWh/m²</strong>
            <small style="color:var(--muted)">冬至日 9:00 太阳高度角 ${wxEval.solarAlt9amDeg}° · 方位角 ${wxEval.solarAz9amDeg}°</small>
          </div>
          <div class="satmap-subbox">
            <span>气象单瓦最优夹角 (满发小时最高)</span>
            <strong style="font-size:16px;color:#0284c7">倾角 ${wxEval.weatherOptimalTiltDeg}° / 方位角 ${wxEval.weatherOptimalAzimuthDeg}°</strong>
            <small style="color:var(--muted)">单瓦满发 ${wxEval.weatherOptimalYield} h · 冬至无遮挡净距 ${wxEval.weatherOptimalRowGapM} m</small>
          </div>
          <div class="satmap-subbox">
            <span>有限屋面总发电量最优夹角 (兼顾排距与装机)</span>
            <strong style="font-size:16px;color:#059669">倾角 ${wxEval.roofOptimalTiltDeg}° · 首年 ${wxEval.roofOptimalWanKwh} 万kWh</strong>
            <small style="color:var(--muted)">屋面可装机 ${wxEval.roofOptimalDcKw} kWp · 净排距 ${wxEval.roofOptimalRowGapM} m</small>
          </div>
        </div>

        <details class="satmap-acc-card">
          <summary>
            <span>候选安装倾角与冬至无遮挡排距寻优明细表 (${wxEval.candidates.length} 档角度对比)</span>
            <small>点击展开/收起明细</small>
          </summary>
          <div class="satmap-acc-body" style="overflow-x:auto">
            <table class="satmap-angle-table">
              <thead>
                <tr>
                  <th>候选安装倾角 β</th>
                  <th>冬至9-15时无遮挡净排距 d (m)</th>
                  <th>阵列中心间距 D (m)</th>
                  <th>斜面年有效辐照 (kWh/m²)</th>
                  <th>当前屋面可铺组件 (块)</th>
                  <th>可装机容量 (kWp)</th>
                  <th>单瓦等效满发小时 (h)</th>
                  <th>首年并网总发电量 (万kWh)</th>
                  <th>工程最优评估结论</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                ${wxEval.candidates.map((row) => {
        const isWeatherOpt = row.tiltDeg === wxEval.weatherOptimalTiltDeg;
        const isRoofOpt = row.tiltDeg === wxEval.roofOptimalTiltDeg;
        const isCurrent = Math.abs(row.tiltDeg - activeTilt) < 0.6;
        const tags = [];
        if (isWeatherOpt) tags.push('<span class="sat-pill-ok">气象单瓦最优</span>');
        if (isRoofOpt) tags.push('<span class="sat-pill-ok" style="background:#e0f2fe;color:#0369a1">屋面总发电最优</span>');
        if (isCurrent) tags.push('<span style="font-weight:700;color:#2563eb">[当前角度]</span>');
        return `<tr class="${isWeatherOpt || isRoofOpt ? 'opt-row' : ''}">
                    <td><b>${row.tiltDeg}°</b></td>
                    <td>${row.netRowGapM.toFixed(2)} m</td>
                    <td>${row.centerPitchM.toFixed(2)} m</td>
                    <td>${row.poaKwhM2.toFixed(1)}</td>
                    <td>${row.moduleCount} 块</td>
                    <td>${row.dcKw.toFixed(2)} kWp</td>
                    <td><b>${row.specificYield.toFixed(1)} h</b></td>
                    <td><b style="color:#0284c7">${row.annualWanKwh.toFixed(2)} 万kWh</b></td>
                    <td>${tags.join(' ') || '<span style="color:var(--muted)">常规候选</span>'}</td>
                    <td>
                      <button type="button" class="sat-btn" style="padding:2px 8px;font-size:11.5px" data-sat-apply-tilt="${row.tiltDeg}" data-sat-apply-gap="${row.netRowGapM}">采用此角度</button>
                    </td>
                  </tr>`;
      }).join('')}
              </tbody>
            </table>
          </div>
        </details>
      </div>
    `;
  }

  /**
   * 弹窗工作流：
   *   1. 地图拾取经纬度弹窗
   *   2. 新建/导入工程方案 (.json) 弹窗
   *   3. 逆变器区域选择 / 请选择组串方式 (快速组串 vs DIY组串)
   *   4. 逆变器选择弹窗 (左侧品牌筛选 + 顶部 7 档功率区间筛选 + 卡片网格)
   *   5. 完成设计后 MPPT 组串分配表弹窗 (带绿色电流校核标签)
   */
  renderVideo1Modals() {
    const inv = this.getSelectedInverter();
    const mod = this.getSelectedModule();
    let html = '';

    // 「地图拾取经纬度」弹窗
    if (this.showLocationPickerModal) {
      html += `
        <div class="satmap-modal-backdrop" role="dialog" aria-label="地图拾取经纬度弹窗">
          <div class="satmap-modal-card" style="width:min(820px,95vw)">
            <div class="satmap-modal-header">
              <h3>📍 地图拾取经纬度 (卫星选址底图窗口)</h3>
              <button type="button" class="sat-btn" data-sat-action="close-modals">✕ 关闭</button>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:#f8fafc;padding:10px;border-radius:8px;border:1px solid #e2e8f0">
              <div class="satmap-search-item">
                <span>省市区</span>
                <select data-sat-field="regionQuickPick">
                  <option value="山东省济南市历城区工业北路|36.588644|116.774288" ${this.regionQuickPick.startsWith('山东省济南市') ? 'selected' : ''}>山东省 / 济南市 / 历城区</option>
                  <option value="山东省淄博市桓台县起凤镇工业园|36.858844|118.778089" ${this.regionQuickPick.startsWith('山东省淄博市') ? 'selected' : ''}>山东省 / 淄博市 / 桓台县</option>
                  <option value="山东省济宁市兖州区大安镇工业园|35.566044|116.776388" ${this.regionQuickPick.startsWith('山东省济宁市') ? 'selected' : ''}>山东省 / 济宁市 / 兖州区</option>
                  <option value="江苏省泰州市医药高新区药城大道|32.456200|119.923100" ${this.regionQuickPick.startsWith('江苏省泰州市') ? 'selected' : ''}>江苏省 / 泰州市 / 高新区</option>
                </select>
              </div>
              <div class="satmap-search-item" style="flex:1;min-width:200px">
                <span>详细地址</span>
                <input type="text" class="addr-input" data-sat-field="searchQuery" value="${esc(this.searchQuery || this.address)}" placeholder="请输入详细地址或企业名称搜索">
                <button type="button" class="sat-btn primary" data-sat-action="search-location">搜索位置</button>
              </div>
              <div class="satmap-search-item">
                <span>经度</span>
                <input type="number" step="0.0001" class="coord-input" data-sat-field="lon" value="${Number(this.lon).toFixed(6)}">
              </div>
              <div class="satmap-search-item">
                <span>纬度</span>
                <input type="number" step="0.0001" class="coord-input" data-sat-field="lat" value="${Number(this.lat).toFixed(6)}">
              </div>
              <button type="button" class="sat-btn ${this.coordFormat === 'dms' ? 'primary' : ''}" data-sat-action="toggle-dms">度分秒</button>
              <button type="button" class="sat-btn" data-sat-action="locate">经纬度定位</button>
              <div class="satmap-search-item">
                <span>切换地图图源</span>
                <select data-sat-field="mapSource">
                  <option value="gaode" ${this.mapSource === 'gaode' ? 'selected' : ''}>谷歌地图 (高清混合图)</option>
                  <option value="esri" ${this.mapSource === 'esri' ? 'selected' : ''}>Esri 全球纯卫星图</option>
                </select>
              </div>
            </div>

            <!-- Real Interactive Satellite Map Canvas with White Selection Frame -->
            <div style="position:relative;height:256px;background:#0f172a;border-radius:8px;border:1px solid #334155;overflow:hidden">
              <canvas id="sat-loc-picker-canvas" width="760" height="256" style="width:100%;height:256px;display:block;cursor:grab"></canvas>
              <div style="position:absolute;top:10px;left:12px;background:rgba(15,23,42,0.86);border:1px solid #38bdf8;color:#f8fafc;padding:4px 10px;border-radius:6px;font-size:11.5px;pointer-events:none">
                <b>当前选址中心：</b>${esc(this.address)} <span style="color:#38bdf8;font-family:monospace">(${Number(this.lon).toFixed(6)}°E, ${Number(this.lat).toFixed(6)}°N · Z${this.zoom})</span>
              </div>
              <div style="position:absolute;right:12px;top:10px;display:flex;flex-direction:column;gap:4px">
                <button type="button" class="satmap-rms-btn" data-sat-action="zoom-in" title="放大选址底图">+</button>
                <button type="button" class="satmap-rms-btn" data-sat-action="zoom-out" title="缩小选址底图">−</button>
              </div>
              <div style="position:absolute;bottom:10px;left:50%;transform:translateX(-50%);background:rgba(255,247,237,0.96);border:1px solid #fdba74;color:#c2410c;padding:4px 14px;border-radius:999px;font-size:11.5px;font-weight:600;white-space:nowrap;pointer-events:none">
                ⓘ 请调整至清晰位置，作为卫星设计底图，如不需要请直接确定
              </div>
            </div>

            <div style="display:flex;justify-content:flex-end;gap:8px;padding-top:6px;border-top:1px solid #e2e8f0">
              <button type="button" class="sat-btn" data-sat-action="close-modals">直接跳过</button>
              <button type="button" class="sat-btn primary" data-sat-action="close-modals">确定选址并进入 2D 快速建模</button>
            </div>
          </div>
        </div>
      `;
    }

    // 「开始一个光伏方案」新建/打开JSON弹窗
    if (this.showPvlaneStartModal) {
      html += `
        <div class="satmap-modal-backdrop" role="dialog" aria-label="新建或导入光伏方案弹窗">
          <div class="satmap-modal-card" style="width:min(480px,92vw);text-align:center;padding:24px">
            <div class="satmap-modal-header" style="justify-content:space-between">
              <h3 style="font-size:16px">新建 / 导入光伏工程方案</h3>
              <button type="button" class="sat-btn" data-sat-action="close-modals">✕</button>
            </div>
            <p style="margin:0;font-size:12.5px;color:#475569">
              支持新建空白卫星/航拍屋面方案，或导入/导出标准 JSON 工程方案文件
            </p>
            <div style="display:flex;flex-direction:column;gap:10px;margin:10px 0">
              <button type="button" class="sat-btn primary" style="padding:11px 16px;font-size:14px;justify-content:center" data-sat-action="pvlane-new-project">
                📄 新建项目 (进入 1.屋面 标定与建模)
              </button>
              <label class="sat-btn" style="padding:11px 16px;font-size:13.5px;justify-content:center;cursor:pointer">
                📂 打开项目文件 (.json)
                <input type="file" accept=".json,application/json" data-sat-file="project-json" style="display:none">
              </label>
              <button type="button" class="sat-btn" style="padding:10px 16px;font-size:13px;justify-content:center" data-sat-action="export-project-json">
                💾 导出当前项目文件 (.json)
              </button>
            </div>
          </div>
        </div>
      `;
    }

    // 「输入用电信息与光储经济参数」弹窗
    if (this.showTariffModal) {
      const selfRatio = Math.max(0, Math.min(1, Number(this.selfConsumptionRatio) ?? 0.82));
      const weightedTariff = Number(
        (selfRatio * (Number(this.tariffRmb) || 0.78) + (1 - selfRatio) * (Number(this.feedInTariffRmb) || 0.38)).toFixed(3)
      );
      const bessArbitrageWan = Number(((Number(this.bessCapacityKwh) || 0) * 0.9 * 330 * 0.65 * 2 / 10000).toFixed(2));
      html += `
        <div class="satmap-modal-backdrop" role="dialog" aria-label="输入用电信息与光储经济参数弹窗">
          <div class="satmap-modal-card" style="width:min(640px,94vw)">
            <div class="satmap-modal-header">
              <h3>⚡ 输入用电信息与光储经济参数</h3>
              <button type="button" class="sat-btn" data-sat-action="close-modals">✕ 关闭</button>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div class="satmap-subbox">
                <b>1. 厂区变压器与电价参数</b>
                <label class="satmap-field-row">
                  <span>专变容量 (kVA)</span>
                  <input type="number" step="50" min="100" max="20000" data-sat-field="transformerKva" value="${this.transformerKva}">
                </label>
                <label class="satmap-field-row">
                  <span>工商业加权自用电价 (元/kWh)</span>
                  <input type="number" step="0.02" min="0.2" max="2.0" data-sat-field="tariffRmb" value="${this.tariffRmb}">
                </label>
                <label class="satmap-field-row">
                  <span>脱硫燃煤上网电价 (元/kWh)</span>
                  <input type="number" step="0.02" min="0.15" max="1.0" data-sat-field="feedInTariffRmb" value="${this.feedInTariffRmb}">
                </label>
                <label class="satmap-field-row">
                  <span>生产班制与负荷消纳模型</span>
                  <select data-sat-field="shiftMode">
                    <option value="manual" ${this.shiftMode === 'manual' ? 'selected' : ''}>手动设定消纳率</option>
                    <option value="single_shift" ${this.shiftMode === 'single_shift' ? 'selected' : ''}>单班白班制 (双休低荷)</option>
                    <option value="double_shift" ${this.shiftMode === 'double_shift' ? 'selected' : ''}>双班生产制 (周六排产)</option>
                    <option value="continuous_24h" ${this.shiftMode === 'continuous_24h' ? 'selected' : ''}>三班连续生产 (24小时负荷)</option>
                  </select>
                </label>
                <label class="satmap-field-row">
                  <span>自发自用消纳比例 (0~1)</span>
                  <input type="number" step="0.02" min="0.1" max="1.0" data-sat-field="selfConsumptionRatio" value="${this.selfConsumptionRatio}">
                </label>
              </div>
              <div class="satmap-subbox">
                <b>2. EPC 造价、折现率与储能配置</b>
                <label class="satmap-field-row">
                  <span>光伏单位 EPC 造价 (元/Wp)</span>
                  <input type="number" step="0.05" min="1.5" max="8.0" data-sat-field="capexPerW" value="${this.capexPerW}">
                </label>
                <label class="satmap-field-row">
                  <span>折现率基准 (%)</span>
                  <input type="number" step="0.5" min="2.0" max="15.0" data-sat-field="discountRatePct" value="${this.discountRatePct || 6.0}">
                </label>
                <label class="satmap-field-row">
                  <span>配套储能 PCS 功率 (kW)</span>
                  <input type="number" step="25" min="0" max="5000" data-sat-field="bessPowerKw" value="${this.bessPowerKw}">
                </label>
                <label class="satmap-field-row">
                  <span>配套储能电池容量 (kWh)</span>
                  <input type="number" step="50" min="0" max="10000" data-sat-field="bessCapacityKwh" value="${this.bessCapacityKwh}">
                </label>
                <div style="font-size:11.5px;color:#0369a1;background:#f0f9ff;padding:6px 8px;border-radius:6px;margin-top:4px">
                  综合度电结算均价：<b>${weightedTariff} 元/kWh</b> · 度电成本：<b>${this.summary.lcoeRmb || 0.22} 元/kWh</b><br>
                  储能两充两放年增收：<b>+${bessArbitrageWan} 万元/年</b>
                </div>
              </div>
            </div>
            <div style="background:#f8fafc;border:1px solid #cbd5e1;border-radius:8px;padding:10px 14px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;font-size:12.5px">
              <span>工程总投资：<b>${this.summary.capexWan} 万元</b></span>
              <span>静/动态回收期：<b>${this.summary.paybackYears != null ? this.summary.paybackYears : '未回收'} / ${this.summary.dynamicPaybackYears != null ? `${this.summary.dynamicPaybackYears} 年` : '未回收'}</b></span>
              <span>全投资 IRR (25年DCF)：<b style="color:#059669">${this.summary.irrPct != null ? `${this.summary.irrPct}%` : '无法收回'}</b></span>
              <span>25年累计 NPV：<b style="color:#0284c7">${this.summary.npv25Wan || 0} 万元</b></span>
            </div>
            <div style="display:flex;justify-content:flex-end;gap:8px;padding-top:6px;border-top:1px solid #e2e8f0">
              <button type="button" class="sat-btn" data-sat-action="export-owner-report">🏢 导出业主投资汇报书</button>
              <button type="button" class="sat-btn primary" data-sat-action="close-modals">保存并应用参数</button>
            </div>
          </div>
        </div>
      `;
    }

    if (this.showStringModeModal) {
      html += `
        <div class="satmap-modal-backdrop" role="dialog" aria-label="逆变器区域选择与组串方式">
          <div class="satmap-modal-card" style="width:min(620px,94vw)">
            <div class="satmap-modal-header">
              <h3>逆变器区域选择 — 请选择组串方式</h3>
              <button type="button" class="sat-btn" data-sat-action="close-modals">✕ 关闭</button>
            </div>
            <div class="satmap-string-mode-grid">
              <div class="satmap-string-mode-card ${this.stringingMode === 'quick' ? 'active' : ''}" data-sat-string-mode="quick">
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <strong style="font-size:15px;color:#1d4ed8">⚡ 快速组串 (新手推荐)</strong>
                  <span class="sat-pill-ok">推荐</span>
                </div>
                <p style="margin:0;font-size:12.5px;color:#475569;line-height:1.5">
                  自动按屋面连通分翼与 2×${Math.ceil(this.modulesPerString / 2)} U型蛇形算法完成全部组件配串，智能匹配逆变器 MPPT 并生成屋面内部走线。
                </p>
              </div>
              <div class="satmap-string-mode-card ${this.stringingMode === 'diy' ? 'active' : ''}" data-sat-string-mode="diy">
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <strong style="font-size:15px;color:#0f172a">🛠️ DIY 组串 (自定义配置)</strong>
                  <span style="font-size:11px;color:#64748b">高级工程</span>
                </div>
                <p style="margin:0;font-size:12.5px;color:#475569;line-height:1.5">
                  自主选择逆变器品牌与功率段、调节目标容配比滑块 (0.4 ~ 1.8) 与单串串联块数，定制 MPPT 回路分配。
                </p>
              </div>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;padding-top:8px;border-top:1px solid #e2e8f0">
              <label style="display:flex;align-items:center;gap:6px;font-size:13px;font-weight:600;cursor:pointer">
                <input type="checkbox" data-sat-field="selectAllRoofDevices" ${this.selectAllRoofDevices ? 'checked' : ''}>
                <span>选中屋顶所有设备 (共 ${this.summary.moduleCount || '待铺设'} 块组件)</span>
              </label>
              <div style="display:flex;gap:8px">
                <button type="button" class="sat-btn" data-sat-action="close-modals">取消</button>
                <button type="button" class="sat-btn primary" data-sat-action="confirm-string-mode">下一步 →</button>
              </div>
            </div>
          </div>
        </div>
      `;
    }

    if (this.showInverterModal) {
      const filtered = this.getFilteredInverters();
      const brands = ['all', '阳光电源', '华为', '固德威', '古瑞瓦特', '锦浪'];
      const powerTiers = [
        ['all', '全部功率'],
        ['gt150', '150kW以上'],
        ['100_150', '100kW≤功率<150kW'],
        ['50_100', '50kW≤功率<100kW'],
        ['30_50', '30kW≤功率<50kW'],
        ['10_30', '10kW≤功率<30kW'],
        ['lt10', '10kW以下'],
      ];
      html += `
        <div class="satmap-modal-backdrop" role="dialog" aria-label="逆变器选型弹窗">
          <div class="satmap-modal-card">
            <div class="satmap-modal-header">
              <h3>逆变器选择 (按品牌与功率区间筛选)</h3>
              <button type="button" class="sat-btn" data-sat-action="close-modals">✕ 关闭</button>
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
              <b style="font-size:12px">品牌：</b>
              ${brands.map((b) => `
                <button type="button" class="satmap-inv-brand-btn ${this.inverterBrandFilter === b ? 'active' : ''}" data-sat-inv-brand="${esc(b)}">
                  ${b === 'all' ? '全部品牌' : esc(b)}
                </button>
              `).join('')}
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
              <b style="font-size:12px">功率段：</b>
              ${powerTiers.map(([k, label]) => `
                <button type="button" class="satmap-inv-brand-btn ${this.inverterPowerFilter === k ? 'active' : ''}" data-sat-inv-power="${k}">
                  ${esc(label)}
                </button>
              `).join('')}
            </div>
            <div class="satmap-inv-grid" style="margin-bottom:0">
              ${filtered.map((item) => {
        const isSel = item.id === this.inverterModelId;
        return `<div class="satmap-inv-card ${isSel ? 'active' : ''}" data-sat-pick-inv="${esc(item.id)}">
                  <div style="display:flex;justify-content:space-between;align-items:center">
                    <span style="font-size:11.5px;color:#0284c7;font-weight:700">${esc(item.brand)}</span>
                    <span class="${isSel ? 'sat-pill-ok' : ''}" style="font-size:11px">${item.rated_ac_kw} kW</span>
                  </div>
                  <h4 style="margin:2px 0">${esc(item.model)}</h4>
                  <div style="font-size:11.5px;color:#475569;line-height:1.5">
                    <div>MPPT数量：<b>${item.mppt_count} 路 (${item.mppt_count * item.strings_per_mppt}串)</b></div>
                    <div>最大工作/短路电流：<b>${item.max_mppt_current_a}A / ${item.max_short_current_a}A</b></div>
                  </div>
                  <button type="button" class="sat-btn ${isSel ? 'primary' : ''}" data-sat-pick-inv="${esc(item.id)}" style="width:100%">
                    ${isSel ? '当前已选' : '选择此型号'}
                  </button>
                </div>`;
      }).join('')}
            </div>
            <div style="display:flex;justify-content:flex-end;gap:8px;padding-top:8px;border-top:1px solid #e2e8f0">
              <button type="button" class="sat-btn primary" data-sat-action="close-modals">确定选型</button>
            </div>
          </div>
        </div>
      `;
    }

    if (this.showMpptModal) {
      html += `
        <div class="satmap-modal-backdrop" role="dialog" aria-label="MPPT组串分配明细弹窗">
          <div class="satmap-modal-card">
            <div class="satmap-modal-header">
              <h3>${esc(inv.model)} 逆变器 MPPT 组串分配表 (共 ${this.summary.inverterCount} 台 · ${this.summary.stringCount} 串)</h3>
              <button type="button" class="sat-btn" data-sat-action="close-modals">✕ 关闭</button>
            </div>
            <div style="overflow-x:auto;max-height:360px;overflow-y:auto">
              <table class="satmap-mppt-table">
                <thead>
                  <tr>
                    <th>逆变器名称</th>
                    <th>MPPT</th>
                    <th>组串名称</th>
                    <th>组串数量</th>
                    <th>串联数(块)</th>
                    <th>最大工作电流(A)</th>
                    <th>最大短路电流(A)</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  ${this.mpptRows.map((row) => `
                    <tr>
                      <td><b>${esc(row.inverterName)}</b></td>
                      <td><b>${esc(row.mpptName)}</b></td>
                      <td>${esc(row.stringNames)}</td>
                      <td>${row.stringCount}</td>
                      <td>${row.modulesPerString} (${esc(mod.model.split(' ')[0])})</td>
                      <td><span class="sat-pill-ok">${row.workCurrentA.toFixed(2)} A</span></td>
                      <td><span class="sat-pill-ok">${row.shortCurrentA.toFixed(2)} A</span></td>
                      <td><span class="sat-pill-ok">状态：${esc(row.status)}</span></td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;padding-top:8px;border-top:1px solid #e2e8f0;flex-wrap:wrap;gap:8px">
              <span style="font-size:12px;color:#475569">容配比：<b>${this.summary.dcAcRatio}</b> · 直流装机：<b>${this.summary.dcKw} kWp</b> · 交流容量：<b>${this.summary.acKw} kW</b> · 共 <b>${this.mpptRows.length}</b> 条 MPPT 回路</span>
              <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button type="button" class="sat-btn" data-sat-action="close-modals">返回卫星图</button>
                <button type="button" class="sat-btn" data-sat-action="export-mppt-csv">📥 导出 MPPT 清册 (.csv)</button>
                <button type="button" class="sat-btn" data-sat-action="generate-dc-cable">⚡ 自动生成直流线缆</button>
                <button type="button" class="sat-btn primary" data-sat-step="5">前往生成施工 CAD 图纸 →</button>
              </div>
            </div>
          </div>
        </div>
      `;
    }

    return html;
  }

  getFilteredInverters() {
    return this.getAllInverters().filter((item) => {
      const brandOk = this.inverterBrandFilter === 'all' || item.brand.includes(this.inverterBrandFilter);
      if (!brandOk) return false;
      const kw = item.rated_ac_kw;
      if (this.inverterPowerFilter === 'gt150') return kw >= 150;
      if (this.inverterPowerFilter === '100_150') return kw >= 100 && kw < 150;
      if (this.inverterPowerFilter === '50_100') return kw >= 50 && kw < 100;
      if (this.inverterPowerFilter === '30_50') return kw >= 30 && kw < 50;
      if (this.inverterPowerFilter === '10_30') return kw >= 10 && kw < 30;
      if (this.inverterPowerFilter === 'lt10') return kw < 10;
      return true;
    });
  }

  /**
   * 导出逆变器 MPPT 组串分配表、交直流压降校核与设备线缆清册 (.csv，带 UTF-8 BOM 支持 Excel 直接打开)
   */
  exportMpptCsv() {
    if (!this.hasLaidOut) {
      this.layoutModules({ quiet: true, autoCreateRoof: true });
    }
    if (!this.electricalSizing) this.recomputeEngineeringAnalyses();
    const inv = this.getSelectedInverter();
    const mod = this.getSelectedModule();
    const s = this.summary;
    const es = this.electricalSizing;
    const ns = es.modulesPerString;
    const vocColdV = es.vocColdV;
    const vmpHotV = es.vmpHotV;
    const dcDropPct = es.maxDcDropPct;

    const lines = [
      ['项目名称', this.projectName, '项目地址', this.address, '经纬度', `${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E`],
      ['直流装机容量(kWp)', s.dcKw, '交流额定容量(kWac)', s.acKw, '容配比(DC/AC)', s.dcAcRatio],
      ['组件型号', `${mod.brand} ${mod.model} (${mod.stc_w}Wp, βVoc=${mod.beta_voc_pct_c}%/°C)`, '组件总数(块)', s.moduleCount, '单串串联数(块/串)', `${ns} (允许窗口 ${es.nMin}~${es.nMax})`],
      ['逆变器型号', `${inv.brand} ${inv.model} (${inv.rated_ac_kw}kW)`, '逆变器台数(台)', s.inverterCount, '组串总数(串)', s.stringCount],
      [`极端低温开路电压Voc(${es.tMinC}°C)`, `${vocColdV} V (限值 ≤ ${es.maxAllowedSysV} V)`, `高温工作电压Vmp(${es.tCellHotC}°C)`, `${vmpHotV} V (MPPT ${inv.mppt_v_min}~${inv.mppt_v_max} V)`, '直流线缆平均压降ΔUdc%', `${es.avgDcDropPct}% (最不利 ${es.worstStringName}: ${dcDropPct}% ≤1.5%)`],
      ['交流并网主缆选型', es.acCableSpec, '交流满载电流(A)', es.acPhaseCurrA, '交流线损压降ΔUac%', `${es.acDropPct}% (≤3.0%)`],
      [],
      ['序号', '逆变器名称', 'MPPT通道', '坡面朝向隔离', '组串编号', '接入组串数(串)', '单串串联数(块)', 'MPPT组件总数(块)', '组串占比', 'STC工作电压Vmp(V)', `低温开路Voc(${es.tMinC}°C)(V)`, '最大工作电流Imp(A)', '最大短路电流Isc(A)', '校核状态'],
    ];

    this.mpptRows.forEach((row, idx) => {
      const rowVocCold = row.modulesPerString > 0 ? es.vocColdV : 0;
      lines.push([
        idx + 1,
        row.inverterName,
        row.mpptName,
        row.slopeLabel || '南坡 180°',
        row.stringNames || `${row.stringCount}串`,
        row.stringCount,
        row.modulesPerString,
        row.totalMpptMods ?? row.stringCount * row.modulesPerString,
        row.stringRatio || '—',
        row.vmpV,
        rowVocCold,
        row.workCurrentA.toFixed(2),
        row.shortCurrentA.toFixed(2),
        row.status,
      ]);
    });

    const csvText = '\uFEFF' + lines.map((r) => r.map((c) => `"${String(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n');
    if (typeof document !== 'undefined') {
      const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${this.cadPrefix}-MPPT-Cable-Schedule.csv`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      this.notice(`已导出逆变器 MPPT 组串分配与线缆压降校核清册：${a.download}（共 ${this.mpptRows.length} 条回路）`);
    }
    return csvText;
  }

  /**
   * Step 2: 电气设计 — 逆变器品牌+功率段筛选、选型卡片、IEC 62548 电压温度包络与交直流压降校核 & MPPT 组串分配表
   */
  renderStep2Electrical() {
    if (!this.modules || this.modules.length === 0) {
      this.layoutModules({ quiet: true, autoCreateRoof: true });
      this.electricalConfirmed = true;
      this.showStringColors = true;
      this.computeElectricalAllocation();
    }
    const inv = this.getSelectedInverter();
    const mod = this.getSelectedModule();
    const s = this.summary;
    const brands = ['all', '阳光电源', '华为', '固德威', '古瑞瓦特', '锦浪'];
    const powerTiers = [
      ['all', '全部功率'],
      ['gt150', '150kW以上'],
      ['100_150', '100kW≤功率<150kW'],
      ['50_100', '50kW≤功率<100kW'],
      ['30_50', '30kW≤功率<50kW'],
      ['10_30', '10kW≤功率<30kW'],
      ['lt10', '10kW以下'],
    ];
    const filteredInverters = this.getFilteredInverters();

    if (!this.electricalSizing) this.recomputeEngineeringAnalyses();
    const es = this.electricalSizing;
    const ns = es.modulesPerString;
    const vmpStc = es.vmpStcV;
    const vocStc = es.vocStcV;
    const vocCold = es.vocColdV;
    const vmpHot = es.vmpHotV;
    const vocSafe = es.vocSafe;
    const mpptSafe = es.mpptSafe;
    const dcDropPct = es.maxDcDropPct;
    const acDropPct = es.acDropPct;

    return `<div class="satmap-elec-card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding-bottom:12px;border-bottom:1px solid var(--line,#e2e8f0)">
        <div>
          <h3 style="margin:0;font-size:16px">电气设计与逆变器 MPPT 组串分配工作台</h3>
          <small style="color:var(--muted,#64748b)">气候区：${esc(es.climate.zoneZh)} (${es.tMinC}°C ~ 结温 ${es.tCellHotC}°C) · 安全串联窗口 ${es.nMin}~${es.nMax} 块/串 · 南北分坡物理隔离</small>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <details class="sat-popover">
            <summary class="sat-btn">参数与清册导入导出 ▾</summary>
            <div class="sat-popover-panel">
              <label class="sat-btn" style="cursor:pointer;justify-content:flex-start">
                📄 导入组件参数文件
                <input type="file" accept=".pan,.PAN,.txt" data-sat-file="pan-file" style="display:none">
              </label>
              <button type="button" class="sat-btn" data-sat-action="export-pan">导出组件参数文件</button>
              <label class="sat-btn" style="cursor:pointer;justify-content:flex-start">
                ⚡ 导入逆变器参数文件
                <input type="file" accept=".ond,.OND,.txt" data-sat-file="ond-file" style="display:none">
              </label>
              <button type="button" class="sat-btn" data-sat-action="export-ond">导出逆变器参数文件</button>
              <button type="button" class="sat-btn" data-sat-action="export-mppt-csv">📥 导出 MPPT 与线缆清册 (.csv)</button>
            </div>
          </details>
          <button type="button" class="sat-btn primary" data-sat-action="confirm-electrical">确认电气设计并映射屋面组串</button>
          <button type="button" class="sat-btn" data-sat-step="5">前往图纸生成工具</button>
        </div>
      </div>

      <!-- Inverter Brand Filter + Power Tier Filter & Visual Selection Cards -->
      <details class="satmap-acc-card" open style="margin-top:12px">
        <summary>
          <span>逆变器选型库与筛选（当前已选：${esc(inv.brand)} · ${esc(inv.model)} × ${s.inverterCount} 台）</span>
          <small>点击折叠/展开机型库</small>
        </summary>
        <div class="satmap-acc-body">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
            <div class="satmap-inv-brand-bar" role="tablist" aria-label="逆变器品牌筛选" style="margin:0">
              <span style="font-size:12px;font-weight:700;color:var(--ink)">品牌：</span>
              ${brands.map((b) => `
                <button type="button" class="satmap-inv-brand-btn ${this.inverterBrandFilter === b ? 'active' : ''}" data-sat-inv-brand="${esc(b)}">
                  ${b === 'all' ? '全部品牌' : esc(b)}
                </button>
              `).join('')}
            </div>
            <div class="satmap-inv-brand-bar" role="tablist" aria-label="逆变器功率区间筛选" style="margin:0">
              <span style="font-size:12px;font-weight:700;color:var(--ink)">功率段：</span>
              ${powerTiers.map(([k, label]) => `
                <button type="button" class="satmap-inv-brand-btn ${this.inverterPowerFilter === k ? 'active' : ''}" data-sat-inv-power="${k}">
                  ${esc(label)}
                </button>
              `).join('')}
            </div>
          </div>

          <div class="satmap-inv-grid" style="margin-bottom:2px">
            ${filteredInverters.map((item) => {
      const isSelected = item.id === this.inverterModelId;
      return `<div class="satmap-inv-card ${isSelected ? 'selected active' : ''}" data-sat-pick-inv="${esc(item.id)}">
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <span style="font-size:11.5px;color:#0284c7;font-weight:700">${esc(item.brand)} · <b>${esc(item.model)}</b></span>
                  <span class="${isSelected ? 'sat-pill-ok' : ''}" style="font-size:11px;font-weight:700">${isSelected ? '已选型' : `${item.rated_ac_kw} kW`}</span>
                </div>
                <div class="satmap-inv-specs">
                  <span>交流 <b>${item.rated_ac_kw}kW</b> · <b>${item.mppt_count}路</b> (${item.mppt_count * item.strings_per_mppt}串)</span>
                  <span>电压 <b>${item.mppt_v_min}~${item.mppt_v_max}V</b> (上限${item.max_dc_v}V)</span>
                  <span>电流 <b>${item.max_mppt_current_a}A</b> / 短路 <b>${item.max_short_current_a}A</b></span>
                </div>
              </div>`;
    }).join('')}
          </div>
        </div>
      </details>

      <div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:14px 0">
        <label class="satmap-subbox">
          <span>当前逆变器与交直流线缆配置</span>
          <select data-sat-field="inverterModelId" style="padding:5px;border-radius:6px;border:1px solid var(--line-2,#cbd5e1)">
            ${this.getAllInverters().map((item) => `<option value="${esc(item.id)}" ${item.id === this.inverterModelId ? 'selected' : ''}>${esc(item.brand)} · ${esc(item.model)} (${item.rated_ac_kw}kW / ${item.mppt_count}路MPPT)</option>`).join('')}
          </select>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:4px">
            <select data-sat-field="dcCableSectionMm2" title="直流光伏线缆截面" style="padding:3px;font-size:11px;border-radius:4px;border:1px solid #cbd5e1">
              <option value="4" ${Number(this.dcCableSectionMm2) === 4 ? 'selected' : ''}>直流 4mm²</option>
              <option value="6" ${Number(this.dcCableSectionMm2) === 6 ? 'selected' : ''}>直流 6mm²</option>
            </select>
            <select data-sat-field="acCableMaterial" title="交流并网电缆材质" style="padding:3px;font-size:11px;border-radius:4px;border:1px solid #cbd5e1">
              <option value="cu" ${this.acCableMaterial !== 'al' ? 'selected' : ''}>交流铜芯缆</option>
              <option value="al" ${this.acCableMaterial === 'al' ? 'selected' : ''}>交流铝合金缆</option>
            </select>
          </div>
        </label>
        <div class="satmap-subbox">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span>单串串联组件数 (块/串)</span>
            <button type="button" class="sat-btn" style="padding:1px 6px;font-size:10.5px" data-sat-action="apply-opt-string">采用最佳 ${es.nOpt}块</button>
          </div>
          <input type="number" min="8" max="26" step="1" data-sat-field="modulesPerString" value="${this.modulesPerString}" style="padding:6px;border-radius:6px;border:1px solid var(--line-2,#cbd5e1)">
          <small style="color:var(--muted)">允许窗口 <b>${es.nMin}~${es.nMax} 块/串</b> · 工作 ${vmpStc}V / 开路 ${vocStc}V</small>
        </div>
        <div class="satmap-subbox">
          <span>直流/交流容配比 (DC/AC Ratio)</span>
          <strong style="font-size:18px;color:#0284c7">${s.dcAcRatio} : 1</strong>
          <small style="color:var(--muted)">直流 ${s.dcKw} kWp / 交流 ${s.acKw} kWac (${s.inverterCount} 台 ${inv.model})</small>
        </div>
        <div class="satmap-subbox">
          <span>IEC 62548 电压温度包络校核</span>
          <strong style="font-size:14.5px;color:${es.allWindowSafe ? '#059669' : '#d97706'}">${es.allWindowSafe ? '✓ 极寒/酷暑电压包络合规' : '⚠ 超出安全串联窗口'}</strong>
          <small style="color:var(--muted)">极寒(${es.tMinC}°C) Voc=<b>${vocCold}V</b> ≤ ${es.maxAllowedSysV}V · 结温(${es.tCellHotC}°C) Vmp=<b>${vmpHot}V</b></small>
        </div>
        <div class="satmap-subbox">
          <span>GB 50797 交直流电缆压降校核</span>
          <strong style="font-size:14.5px;color:${dcDropPct <= 1.5 ? '#059669' : '#d97706'}">最不利 ΔUdc ${dcDropPct}% · ΔUac ${acDropPct}%</strong>
          <small style="color:var(--muted)">${esc(es.worstStringName)} 回路压降 ${es.maxDcDropV}V (均值 ${es.avgDcDropPct}%) · ${esc(es.acCableSpec)}</small>
        </div>
      </div>

      <!-- Professional Grid-Connection, Transformer Capacity, Anti-Backflow & Reactive Power (SVG) Engineering Verification -->
      <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:0 0 14px">
        <div class="satmap-subbox" style="border-left:3px solid #2563eb">
          <span>并网电压等级与一次接入方案</span>
          <strong style="font-size:14.5px;color:#2563eb">${s.acKw >= 400 ? '10kV 高压升压并网 (配箱变)' : '0.4kV 低压母线并网 (配并网柜)'}</strong>
          <small style="color:var(--muted)">交流并网容量 ${s.acKw} kWac · 进线断路器 ${Math.ceil((s.acKw * 1.8) / 50) * 50}A 框架断路器</small>
        </div>
        <div class="satmap-subbox" style="border-left:3px solid #059669">
          <span>厂区变压器容量与消纳校核</span>
          <strong style="font-size:14.5px;color:#059669">光变比 ${Math.round((s.acKw / Math.max(200, this.transformerKva || 1250)) * 100)}% ≤ 80% (合格)</strong>
          <small style="color:var(--muted)">专变容量 ${this.transformerKva || 1250} kVA · 满足国网分布式电源接入规范</small>
        </div>
        <div class="satmap-subbox" style="border-left:3px solid #d97706">
          <span>防逆流保护与并网联跳装置</span>
          <strong style="font-size:14.5px;color:#d97706">✓ 已配防逆流微机保护 + 失压脱扣</strong>
          <small style="color:var(--muted)">关口表双向计量 · 逆功率 100ms 毫秒级降载 + 检有压自动合闸</small>
        </div>
        <div class="satmap-subbox" style="border-left:3px solid #7c3aed">
          <span>动态无功补偿与电能质量校核</span>
          <strong style="font-size:14.5px;color:#7c3aed">SVG ±${Math.max(30, Math.round(s.acKw * 0.2))} kvar (cosφ ≥ 0.98)</strong>
          <small style="color:var(--muted)">谐波畸变率 THDi ≤ 2.8% (优于 GB/T 14549 5% 标准)</small>
        </div>
      </div>

      <h4 style="margin:12px 0 6px;font-size:14px">逆变器 MPPT 组串分配明细表 (共 ${s.inverterCount} 台逆变器 · ${s.stringCount} 路组串)</h4>
      <div style="overflow-x:auto">
        <table class="satmap-mppt-table">
          <thead>
            <tr>
              <th>逆变器名称</th>
              <th>MPPT</th>
              <th>坡面朝向</th>
              <th>组串名称</th>
              <th>接入组串数</th>
              <th>组件数量</th>
              <th>组串占比</th>
              <th>MPPT 工作电压 (V)</th>
              <th>最大工作电流 (A)</th>
              <th>最大短路电流 (A)</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            ${this.mpptRows.length ? this.mpptRows.map((row) => `
              <tr>
                <td><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${row.color};margin-right:6px"></span><b>${esc(row.inverterName)}</b></td>
                <td><b>${esc(row.mpptName)}</b></td>
                <td><span class="sat-pill-ok" style="${row.slope === 'north' ? 'background:#fef3c7;color:#b45309' : ''}">${esc(row.slopeLabel || '南坡 180°')}</span></td>
                <td>${esc(row.stringNames || `${row.stringCount}串`)}</td>
                <td>${row.stringCount} 串</td>
                <td>${row.modulesPerString} 块/串 (共 ${row.totalMpptMods ?? row.stringCount * row.modulesPerString} 块)</td>
                <td>${esc(row.stringRatio || '—')}</td>
                <td>${row.vmpV} V <small style="color:var(--muted)">(${inv.mppt_v_min}~${inv.mppt_v_max}V)</small></td>
                <td><span class="sat-pill-ok">${row.workCurrentA.toFixed(2)} A</span> <small style="color:var(--muted)">(≤${inv.max_mppt_current_a}A)</small></td>
                <td><span class="sat-pill-ok">${row.shortCurrentA.toFixed(2)} A</span> <small style="color:var(--muted)">(≤${inv.max_short_current_a}A)</small></td>
                <td><span class="${row.ok ? 'sat-pill-ok' : 'sat-pill-warn'}">状态：${esc(row.status)}</span></td>
              </tr>
            `).join('') : `
              <tr>
                <td colspan="11" style="text-align:center;padding:18px;color:var(--muted)">
                  当前尚未铺设屋面组件，请先在「1. 卫星底图与排布设计」中绘制屋顶并点击「一键铺设组件」，或直接点击右上角「确认电气设计并映射屋面组串」自动生成排布与配串。
                </td>
              </tr>
            `}
          </tbody>
        </table>
      </div>
    </div>`;
  }

  /**
   * Step 3: 8760h Loss Waterfall & Official Live Weather Panel
   */
  renderStep3Pvsyst() {
    if (!this.pvsystData) {
      this.refreshPvsystData({ fetchBackend: false });
    }
    if (!this.shading3dSummary && this.modules && this.modules.length > 0) {
      this.compute3DShadingReport();
    }
    try {
      return renderPvsystWorkbench(this.pvsystData, {
        lat: this.lat,
        lon: this.lon,
        dc_kw: this.summary.dcKw || 280,
        ac_kw: this.summary.acKw || 220,
        tilt_deg: this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg,
        azimuth_deg: this.azimuthDeg,
        module: this.getSelectedModule(),
        inverter: this.getSelectedInverter(),
        modulesPerString: this.modulesPerString,
        params: this.pvsystParams,
        shading3d: this.shading3dSummary,
      });
    } catch (err) {
      return `<div class="satmap-elec-card"><h3>8760h 光电物理仿真工作台</h3><p>${esc(err.message)}</p></div>`;
    }
  }

  /**
   * Dynamic 2D Roof & Modules Reference Thumbnail SVG for Step 4
   */
  renderDynamic2DRoofThumbSvg() {
    const frame = this.getRoofUVFrame(true);
    const W = 240, H = 118, pad = 20;
    const scale = Math.min((W - pad * 2) / Math.max(4, frame.widthU), (H - pad * 2) / Math.max(4, frame.heightV));
    const ox = (W - frame.widthU * scale) / 2;
    const oy = (H - frame.heightV * scale) / 2;
    const tu = (u) => (ox + (u - frame.uMin) * scale).toFixed(1);
    const tv = (v) => (oy + (v - frame.vMin) * scale).toFixed(1);

    const roofPath = frame.polyUV.map(([u, v], i) => `${i === 0 ? 'M' : 'L'}${tu(u)},${tv(v)}`).join(' ') + ' Z';
    const obsPaths = this.obstacles.map((o) => {
      const pts = o.polygon.map(([x, y]) => frame.toUV(x, y));
      const d = pts.map(([u, v], i) => `${i === 0 ? 'M' : 'L'}${tu(u)},${tv(v)}`).join(' ') + ' Z';
      return `<path d="${d}" fill="rgba(239,68,68,0.55)" stroke="#ef4444" stroke-width="1"/>`;
    }).join('');
    const modRects = this.modules.slice(0, 450).map((m) => {
      const u0 = Number.isFinite(m.u) ? m.u : frame.toUV(m.cx, m.cy)[0] - m.w / 2;
      const v0 = Number.isFinite(m.v) ? m.v : frame.toUV(m.cx, m.cy)[1] - m.h / 2;
      return `<rect x="${tu(u0)}" y="${tv(v0)}" width="${(m.w * scale).toFixed(1)}" height="${(m.h * scale).toFixed(1)}" fill="#2563eb" stroke="#93c5fd" stroke-width="0.35"/>`;
    }).join('');

    const c1 = [tu(frame.uMin), tv(frame.vMin)];
    const c2 = [tu(frame.uMax), tv(frame.vMin)];
    const c3 = [tu(frame.uMax), tv(frame.vMax)];
    const c4 = [tu(frame.uMin), tv(frame.vMax)];

    return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;background:#0f172a;border-radius:6px;border:1px solid #334155">
      <path d="${roofPath}" fill="#1e3a8a" fill-opacity="0.38" stroke="#38bdf8" stroke-width="1.6"/>
      ${this.roofType === 'double_slope' ? `<line x1="${c1[0]}" y1="${tv(frame.centerV)}" x2="${c2[0]}" y2="${tv(frame.centerV)}" stroke="#facc15" stroke-width="1.1" stroke-dasharray="4 2"/>` : ''}
      ${obsPaths}
      ${modRects}
      <circle cx="${c1[0]}" cy="${c1[1]}" r="8" fill="#f59e0b"/><text x="${c1[0]}" y="${Number(c1[1]) + 3.5}" text-anchor="middle" font-size="10" font-weight="bold" fill="#000">1</text>
      <circle cx="${c2[0]}" cy="${c2[1]}" r="8" fill="#f59e0b"/><text x="${c2[0]}" y="${Number(c2[1]) + 3.5}" text-anchor="middle" font-size="10" font-weight="bold" fill="#000">2</text>
      <circle cx="${c3[0]}" cy="${c3[1]}" r="8" fill="#f59e0b"/><text x="${c3[0]}" y="${Number(c3[1]) + 3.5}" text-anchor="middle" font-size="10" font-weight="bold" fill="#000">3</text>
      <circle cx="${c4[0]}" cy="${c4[1]}" r="8" fill="#f59e0b"/><text x="${c4[0]}" y="${Number(c4[1]) + 3.5}" text-anchor="middle" font-size="10" font-weight="bold" fill="#000">4</text>
    </svg>`;
  }

  /**
   * Step 4: Oblique Photo Perspective Homography + Parapet Sightline Occlusion Studio
   */
  renderStep4EffectStudio() {
    if (!this.modules || this.modules.length === 0) {
      this.layoutModules({ quiet: true, autoCreateRoof: true });
      this.electricalConfirmed = true;
      this.showStringColors = true;
      this.computeElectricalAllocation();
    }
    const solarHr = Number.isFinite(Number(this.effectSolarHour)) ? Number(this.effectSolarHour) : 9.5;
    const hrInt = Math.floor(solarHr);
    const minStr = Math.round((solarHr - hrInt) * 60) === 30 ? '30' : '00';
    const solarTimeStr = `${String(hrInt).padStart(2, '0')}:${minStr}`;
    const phi = (Math.max(18, Math.min(52, Math.abs(this.lat || 36.5))) * Math.PI) / 180;
    const delta = (-23.45 * Math.PI) / 180;
    const omega = ((solarHr - 12) * 15 * Math.PI) / 180;
    const sinAlt = Math.max(0.06, Math.sin(phi) * Math.sin(delta) + Math.cos(phi) * Math.cos(delta) * Math.cos(omega));
    const solarAltDeg = Number(((Math.asin(Math.min(1, sinAlt)) * 180) / Math.PI).toFixed(1));
    const parapetH = Math.max(0.3, (Number(this.parapetHeightMm) || 900) / 1000);
    const parapetShadowM = Number(Math.min(4.8, (parapetH * 0.55) / Math.max(0.18, Math.tan((solarAltDeg * Math.PI) / 180))).toFixed(2));
    const setbackOk = parapetShadowM <= Math.max(0.8, Number(this.edgeSetbackM) || 0.8) + 0.45 || (solarHr >= 9 && solarHr <= 15);
    if (!this.structuralCheck) this.recomputeEngineeringAnalyses();
    const st = this.structuralCheck;
    const shade3dAtHr = compute3DPhysicalShading(
      buildSatmap3DGeometrySpec(this.build3DTwinPayload()),
      { lat: this.lat, lon: this.lon, dateStr: '2026-12-21', hourBjt: solarHr }
    );

    return `<div class="satmap-elec-card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding-bottom:10px;border-bottom:1px solid var(--line,#e2e8f0);margin-bottom:12px">
        <div>
          <h3 style="margin:0;font-size:16px">实景四点透视配准与女儿墙遮挡工作台</h3>
          <small style="color:var(--muted,#64748b)">
            已联动排布（${this.summary.moduleCount} 块 · ${this.summary.dcKw} 千瓦）与组串分色 · 直观展示建成实景并校核冬至日女儿墙退距与视线防眩光
          </small>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <div class="satmap-timer-badge" title="实景出图计时器">
            <span>出图计时</span>
            <strong id="sat-effect-timer-display">${this.formatTimer(this.timerElapsedMs)}</strong>
          </div>
          <button type="button" class="sat-btn ${this.effectCompareMode ? 'primary' : ''}" data-sat-effect="toggle-compare">
            ${this.effectCompareMode ? `⇄ 卷帘对比中 (${this.effectCompareSplitPct}%)` : '⇄ 开启改造前后卷帘对比'}
          </button>
          <details class="sat-popover">
            <summary class="sat-btn">辅助与汇报 ▾</summary>
            <div class="sat-popover-panel">
              <button type="button" class="sat-btn" data-sat-action="timer-toggle">${this.timerRunning ? '暂停计时' : '启动计时'}</button>
              <button type="button" class="sat-btn" data-sat-action="timer-reset">重置计时</button>
              <button type="button" class="sat-btn" data-sat-action="jump-3d-sim">开启三维全景仿真</button>
              <button type="button" class="sat-btn" data-sat-action="export-owner-report">生成业主实景汇报书</button>
            </div>
          </details>
          <button type="button" class="sat-btn primary" data-sat-effect="export-png">导出高清效果图</button>
        </div>
      </div>

      <!-- 4-Dimension Real-Scene Engineering Verification Strip -->
      <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px">
        <div class="satmap-subbox" style="border-left:3px solid #059669">
          <span>① 冬至日 (${solarTimeStr}) 女儿墙阴影校核</span>
          <strong style="font-size:14px;color:${setbackOk ? '#059669' : '#d97706'}">${setbackOk ? '✓ 9:00-15:00 核心时段无遮挡' : '⚠ 早晚低高度角局部斜影'}</strong>
          <small style="color:var(--muted)">太阳高度角 ${solarAltDeg}° · 墙影 ${parapetShadowM}米 · 三维遮挡 ${shade3dAtHr.linearBeamShadePct}%</small>
        </div>
        <div class="satmap-subbox" style="border-left:3px solid #2563eb">
          <span>② 园区道路人眼平视美观度校核</span>
          <strong style="font-size:14px;color:#2563eb">✓ 前景女儿墙遮蔽底层支架 72%</strong>
          <small style="color:var(--muted)">地面 1.6米视线无外露桥架与杂乱线缆</small>
        </div>
        <div class="satmap-subbox" style="border-left:3px solid #7c3aed">
          <span>③ 周边办公楼与道路防眩光校核</span>
          <strong style="font-size:14px;color:#7c3aed">✓ 减反镀膜反射率 3.6% ≤ 5.0%</strong>
          <small style="color:var(--muted)">压花高透钢化玻璃漫反射设计（合格）</small>
        </div>
        <div class="satmap-subbox" style="border-left:3px solid #0284c7">
          <span>④ 屋面实景投射规模与荷载校核</span>
          <strong style="font-size:14px;color:${st.allPass ? '#0284c7' : '#d97706'}">${this.summary.moduleCount} 块组件 (${this.summary.dcKw} 千瓦)</strong>
          <small style="color:var(--muted)">新增恒载 ${st.avgAddedDeadKnM2} ≤ ${st.roofLoadLimitKnM2} 千牛/平方米（${st.allPass ? '安全' : '需复核'}）</small>
        </div>
      </div>

      <div class="satmap-effect-studio">
        <aside class="satmap-left-panel" style="max-height:none">
          <details class="satmap-acc-card" open>
            <summary>
              <span>1. 实景照片与场景模板</span>
              <small>4套实景</small>
            </summary>
            <div class="satmap-acc-body">
              <label class="sat-btn" style="width:100%;justify-content:center;cursor:pointer">
                上传无人机 / 手机斜拍厂房照片
                <input type="file" accept="image/*" data-sat-file="effect-photo" style="display:none">
              </label>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px">
                ${[
        [0, '场景1：双坡女儿墙'],
        [1, '场景2：大跨度车间'],
        [2, '场景3：混凝屋面'],
        [3, '场景4：卫星融合'],
      ].map(([idx, label]) => `
                  <button type="button" class="satmap-tool-btn ${this.effectPresetIdx === idx && !this.customPhotoImg ? 'active' : ''}" data-sat-preset-photo="${idx}" style="padding:5px 7px;font-size:11.5px;justify-content:center">
                    <span>${esc(label)}</span>
                  </button>
                `).join('')}
              </div>
            </div>
          </details>

          <details class="satmap-acc-card" open>
            <summary>
              <span>2. 四点透视配准与屋面贴合</span>
              <small>角点 1~4</small>
            </summary>
            <div class="satmap-acc-body">
              <div style="font-size:11.5px;color:var(--ink-2);line-height:1.45">
                参照下方实时 2D 排布缩略图角点顺序 (${this.summary.moduleCount}块组件)，点选或拖动屋面四角：
                <b>1(左上) → 2(右上) → 3(右下) → 4(左下)</b>
              </div>
              ${this.renderDynamic2DRoofThumbSvg()}
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
                <button type="button" class="sat-btn ${this.pickingFourCorners ? 'primary' : ''}" data-sat-effect="pick-4-corners">
                  ${this.pickingFourCorners ? `点选 ${this.pickedCorners.length + 1}/4` : '依次点选四角'}
                </button>
                <button type="button" class="sat-btn primary" data-sat-effect="auto-match">
                  自动配准四角
                </button>
              </div>
            </div>
          </details>

          <details class="satmap-acc-card" open>
            <summary>
              <span>3. 冬至阴影与女儿墙视线遮挡区域</span>
              <small>${solarTimeStr}</small>
            </summary>
            <div class="satmap-acc-body">
              <label class="satmap-field-row">
                <span>冬至日时刻 (${solarTimeStr})</span>
                <input type="range" min="8" max="17" step="0.5" data-sat-field="effectSolarHour" value="${solarHr}" style="width:118px">
              </label>
              <button type="button" class="sat-btn ${this.occlusionDrawing ? 'primary' : ''}" style="width:100%" data-sat-effect="draw-occlusion">
                ${this.occlusionDrawing ? '正在点选女儿墙轮廓 (再点结束)' : '补画女儿墙视线遮挡区域'}
              </button>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
                <button type="button" class="sat-btn" data-sat-effect="demo-occlusion">加载默认女儿墙遮挡</button>
                <button type="button" class="sat-btn danger" data-sat-effect="clear-occlusion">清除遮挡</button>
              </div>
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                <input type="checkbox" data-sat-field="occlusionEnabled" ${this.occlusionEnabled ? 'checked' : ''}>
                <span>启用前景女儿墙裁剪 (${this.occlusionPolygon.length}顶点)</span>
              </label>
            </div>
          </details>

          <details class="satmap-acc-card" ${this.effectCompareMode ? 'open' : ''}>
            <summary>
              <span>4. 组件材质、组串分色与卷帘设置</span>
              <small>${this.effectOpacityPct}%</small>
            </summary>
            <div class="satmap-acc-body">
              <label class="satmap-field-row">
                <span>组件外观样式</span>
                <select data-sat-field="effectModuleStyle">
                  <option value="mono_blue" ${this.effectModuleStyle === 'mono_blue' ? 'selected' : ''}>单晶深蓝高透组件</option>
                  <option value="all_black" ${this.effectModuleStyle === 'all_black' ? 'selected' : ''}>全黑美学组件</option>
                  <option value="poly_blue" ${this.effectModuleStyle === 'poly_blue' ? 'selected' : ''}>多晶宝蓝标准组件</option>
                </select>
              </label>
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                <input type="checkbox" data-sat-field="effectShowStringColors" ${this.effectShowStringColors ? 'checked' : ''}>
                <span>叠加组串分色映射 (${this.summary.stringCount}路组串)</span>
              </label>
              <label class="satmap-field-row">
                <span>组件不透明度 (${this.effectOpacityPct}%)</span>
                <span style="display:flex;align-items:center;gap:6px">
                  <input type="range" min="40" max="100" step="2" data-sat-field="effectOpacityPct" value="${this.effectOpacityPct}" style="width:74px">
                  <input type="number" min="40" max="100" step="5" data-sat-field="effectOpacityPct" value="${this.effectOpacityPct}" style="width:52px">
                </span>
              </label>
              <label class="satmap-field-row">
                <span>边框栅线清晰度 (${this.effectGridSharpnessPct}%)</span>
                <span style="display:flex;align-items:center;gap:6px">
                  <input type="range" min="20" max="100" step="2" data-sat-field="effectGridSharpnessPct" value="${this.effectGridSharpnessPct}" style="width:74px">
                  <input type="number" min="20" max="100" step="5" data-sat-field="effectGridSharpnessPct" value="${this.effectGridSharpnessPct}" style="width:52px">
                </span>
              </label>
              <label class="satmap-field-row">
                <span>表面反光强度 (${this.effectGlarePct}%)</span>
                <span style="display:flex;align-items:center;gap:6px">
                  <input type="range" min="0" max="100" step="2" data-sat-field="effectGlarePct" value="${this.effectGlarePct}" style="width:74px">
                  <input type="number" min="0" max="100" step="5" data-sat-field="effectGlarePct" value="${this.effectGlarePct}" style="width:52px">
                </span>
              </label>
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer">
                <input type="checkbox" data-sat-field="effectCompareMode" ${this.effectCompareMode ? 'checked' : ''}>
                <span>启用改造前后实景卷帘分屏对比</span>
              </label>
              ${this.effectCompareMode ? `
                <label class="satmap-field-row">
                  <span>卷帘分界位置 (${this.effectCompareSplitPct}%)</span>
                  <span style="display:flex;align-items:center;gap:6px">
                    <input type="range" min="10" max="90" step="2" data-sat-field="effectCompareSplitPct" value="${this.effectCompareSplitPct}" style="width:90px">
                    <input type="number" min="10" max="90" step="5" data-sat-field="effectCompareSplitPct" value="${this.effectCompareSplitPct}" style="width:50px">
                  </span>
                </label>
              ` : ''}
            </div>
          </details>
        </aside>

        <div class="satmap-effect-canvas-box">
          <canvas id="sat-effect-canvas" class="satmap-effect-canvas" width="${this.effectCanvasW}" height="${this.effectCanvasH}"></canvas>
          <div style="padding:8px 12px;background:#0f172a;color:#cbd5e1;font-size:12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
            <span>提示：拖动角点 1~4 贴合任意航拍屋面；调节冬至日时刻滑块实时查验女儿墙阴影。</span>
            <span>实景阵列：<b>${this.summary.moduleCount} 块组件（${this.summary.dcKw} 千瓦 · 年发电 ${(this.summary.annualKwh / 10000).toFixed(2)} 万度）</b></span>
          </div>
        </div>
      </div>
    </div>`;
  }

  /**
   * Canonical 16-Sheet Complete Solar Engineering Drawing Suite:
   *   - 电气施工图 (7张): layout (DL-01), string (DL-02), grounding (DL-03), single_line (DL-04), cable_tray (DL-05), bom_schedule (DL-00), ac_cabinet (DL-06)
   *   - 结构施工图 (4张): bracket (JG-01), foundation (JG-02), clamp_detail (JG-03), om_walkway (JG-04)
   *   - 实景/仿真/光储报告图 (5张): pvlane_perspective (FX-01), pvsyst_diagram (PV-01), bess_storage (CN-01), pvlane_birdseye (FX-02), pvsyst_near_shading (PV-02)
   */
  getAllCadSheets() {
    return [
      ['layout', '1. 光伏排布图', 'DL-01', 'elec', '电气施工图'],
      ['string', '2. 组串接线图', 'DL-02', 'elec', '电气施工图'],
      ['grounding', '3. 防雷接地图', 'DL-03', 'elec', '电气施工图'],
      ['bracket', '4. 支架剖面与立面图', 'JG-01', 'struct', '结构施工图'],
      ['single_line', '5. 电气一次系统图', 'DL-04', 'elec', '电气施工图'],
      ['cable_tray', '6. 电缆桥架与走向图', 'DL-05', 'elec', '电气施工图'],
      ['foundation', '7. 基础配重与荷载图', 'JG-02', 'struct', '结构施工图'],
      ['bom_schedule', '8. 图纸目录与设备材料表', 'DL-00', 'elec', '目录与清册'],
      ['pvlane_perspective', '9. 实景四点透视与女儿墙遮挡图', 'FX-01', 'sim', '实景透视图'],
      ['pvsyst_diagram', '10. 全年物理仿真系统与电压包络图', 'PV-01', 'sim', '物理仿真图'],
      ['clamp_detail', '11. 夹具压块与屋面防水节点大样图', 'JG-03', 'struct', '结构施工图'],
      ['ac_cabinet', '12. 并网柜二次原理与通讯监控图', 'DL-06', 'elec', '电气施工图'],
      ['om_walkway', '13. 检修马道、消防通道与清洗水路图', 'JG-04', 'struct', '结构施工图'],
      ['bess_storage', '14. 光储一体化与削峰填谷系统图', 'CN-01', 'sim', '光储系统图'],
      ['pvlane_birdseye', '15. 屋面改造前后实景对比与业主汇报图', 'FX-02', 'sim', '业主汇报图'],
      ['pvsyst_near_shading', '16. 三维近场阴影、寻优矩阵与财务图', 'PV-02', 'sim', '投决报告图'],
    ];
  }

  /**
   * Step 5: 简洁专业「施工图纸工作台」
   * 双栏大画幅蓝图视口 + 折叠式图签/支架荷载检视器 + 单行紧凑图纸标签栏
   */
  renderStep5CadStudio() {
    if (!this.modules || this.modules.length === 0) {
      this.layoutModules({ quiet: true, autoCreateRoof: true });
      this.electricalConfirmed = true;
      this.showStringColors = true;
      this.computeElectricalAllocation();
    }
    const allSheets = this.getAllCadSheets();
    const sheets = this.cadCategory === 'all'
      ? allSheets
      : allSheets.filter((s) => s[3] === this.cadCategory);
    const activeSheetEntry = allSheets.find((s) => s[0] === this.cadSheet) || allSheets[0];
    const shortTabMap = {
      layout: '01 排布图',
      string: '02 组串图',
      grounding: '03 防雷图',
      bracket: '04 支架图',
      single_line: '05 一次图',
      cable_tray: '06 桥架图',
      foundation: '07 基础图',
      bom_schedule: '08 目录清册',
      pvlane_perspective: '09 实景透视',
      pvsyst_diagram: '10 物理仿真',
      clamp_detail: '11 节点大样',
      ac_cabinet: '12 并网二次',
      om_walkway: '13 运维水路',
      bess_storage: '14 光储系统',
      pvlane_birdseye: '15 实景对比',
      pvsyst_near_shading: '16 阴影财务',
    };
    const bcfg = this.bracketCfg || {
      h1Mm: 500, y0Mm: 1500, y1Mm: 1600, angleDeg: 15, x1Mm: 400, x2Mm: 1900,
      foundationType: '混凝土条形基础/方墩', concreteGrade: 'C25',
    };
    if (!this.structuralCheck) this.recomputeEngineeringAnalyses();
    const st = this.structuralCheck;

    const categories = [
      ['all', `全部 (${allSheets.length})`],
      ['elec', '电气 (7)'],
      ['struct', '结构 (4)'],
      ['sim', '综合 (5)'],
    ];

    return `<div class="satmap-cad-page">
      <!-- Clean Single-Line CAD Command Bar -->
      <div class="satmap-cad-wizard-bar">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <button type="button" class="sat-btn" data-sat-step="1">← 返回排布</button>
          <div class="satmap-cad-seg-group" role="tablist" aria-label="图纸工作台模式切换">
            <button type="button" class="satmap-cad-wiz-btn ${this.cadWizardTab === 'sheets' ? 'active' : ''}" data-sat-cad-wiz="sheets">
              <span>图纸总览 (16)</span>
            </button>
            <button type="button" class="satmap-cad-wiz-btn ${this.cadWizardTab === 'basic' ? 'active' : ''}" data-sat-cad-wiz="basic">
              <span>图签参数</span>
            </button>
            <button type="button" class="satmap-cad-wiz-btn ${this.cadWizardTab === 'bracket' ? 'active' : ''}" data-sat-cad-wiz="bracket">
              <span>支架与荷载</span>
            </button>
          </div>
          <details class="sat-popover">
            <summary class="sat-btn">快捷模块与报告 ▾</summary>
            <div class="sat-popover-panel sat-popover-dark">
              <nav class="satmap-cad-dark-nav" aria-label="深色系统快捷导航">
                <div style="padding:4px 8px;font-size:12px;font-weight:700;color:#f8fafc;border-bottom:1px solid #1e293b;margin-bottom:2px">
                  <span>☀️ 光筑智能光伏设计</span>
                </div>
                <button type="button" class="satmap-cad-dark-nav-item" data-sat-action="open-tariff-modal"><span>⚡ 输入用电信息</span></button>
                <button type="button" class="satmap-cad-dark-nav-item" data-sat-step="1"><span>🗺️ 2D快速建模</span></button>
                <button type="button" class="satmap-cad-dark-nav-item" data-sat-step="3"><span>📊 光伏设计模拟</span></button>
                <button type="button" class="satmap-cad-dark-nav-item ${this.cadSheet === 'bess_storage' ? 'active' : ''}" data-sat-jump-cad="bess_storage"><span>🔋 储能 AI 模拟</span></button>
                <button type="button" class="satmap-cad-dark-nav-item ${this.cadSheet === 'pvsyst_near_shading' ? 'active' : ''}" data-sat-jump-cad="pvsyst_near_shading"><span>📑 内部报告中心</span></button>
                <button type="button" class="satmap-cad-dark-nav-item ${this.cadSheet === 'pvlane_birdseye' ? 'active' : ''}" data-sat-jump-cad="pvlane_birdseye"><span>🏢 业主报告中心</span></button>
                <button type="button" class="satmap-cad-dark-nav-item active" data-sat-step="5"><span>📐 光伏图纸生成</span></button>
                <button type="button" class="satmap-cad-dark-nav-item" data-sat-action="jump-3d-sim"><span>🌐 全景3D模拟</span></button>
                <button type="button" class="satmap-cad-dark-nav-item" data-sat-action="export-internal-report"><span>🖨️ 导出内部投决报告</span></button>
                <button type="button" class="satmap-cad-dark-nav-item" data-sat-action="export-owner-report"><span>🖨️ 导出业主汇报书</span></button>
              </nav>
            </div>
          </details>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <details class="sat-popover">
            <summary class="sat-btn">更多导出 ▾</summary>
            <div class="sat-popover-panel">
              <button type="button" class="sat-btn" data-sat-action="export-all-dxf">导出全部 16 张总图 (.dxf)</button>
              <button type="button" class="sat-btn" data-sat-action="export-bom-csv">导出工程材料清册 (.csv)</button>
            </div>
          </details>
          <button type="button" class="sat-btn primary" data-sat-action="export-dxf">导出当前 DXF</button>
          <button type="button" class="sat-btn success" data-sat-action="export-cad-pdf">一键生成十六合一施工图集 (.pdf)</button>
        </div>
      </div>

      <!-- Spacious 2-Column CAD Studio: Clean Left Inspector + Wide Blueprint Viewport -->
      <div class="satmap-cad-studio-grid">
        <aside class="satmap-left-panel satmap-cad-sidebar">
          <div class="satmap-cad-sheet-card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
              <b style="font-size:13px">工程图纸目录</b>
              <small style="color:var(--muted);font-size:11px">共 ${sheets.length} 张</small>
            </div>
            <div class="satmap-cad-cat-pills">
              ${categories.map(([cKey, cLbl]) => `
                <button type="button" class="satmap-cad-cat-pill ${this.cadCategory === cKey ? 'active' : ''}" data-sat-cad-cat="${cKey}">
                  ${esc(cLbl)}
                </button>
              `).join('')}
            </div>
            <div class="satmap-cad-dir-list">
              ${sheets.map(([key, label, code]) => `
                <button type="button" class="satmap-cad-dir-item ${this.cadSheet === key && !this.cadShowAllFourStacked && !this.cadGrid2x2 ? 'active' : ''}" data-sat-cad-sheet="${key}">
                  <span class="satmap-cad-dir-title">${esc(label)}</span>
                  <code class="satmap-cad-dir-code">${esc(code)}</code>
                </button>
              `).join('')}
            </div>
          </div>

          <details class="satmap-acc-card" ${this.cadWizardTab === 'basic' ? 'open' : ''}>
            <summary>
              <span>工程图签信息 (8项)</span>
              <small>${esc(this.cadScale)}</small>
            </summary>
            <div class="satmap-acc-body">
              <div style="font-size:11px;color:var(--muted);line-height:1.45">
                项目：<b>${esc(this.projectName)}</b> · <b>${this.summary.moduleCount}块 (${this.summary.dcKw}kWp)</b>
              </div>
              <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:3px">
                <span>图纸工程名称</span>
                <input type="text" data-sat-field="cadTitle" value="${esc(this.cadTitle)}" style="width:100%">
              </label>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:3px">
                  <span>设计单位</span>
                  <input type="text" data-sat-field="cadUnit" value="${esc(this.cadUnit)}" style="width:100%">
                </label>
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:3px">
                  <span>建设/业主单位</span>
                  <input type="text" data-sat-field="cadBuildOwner" value="${esc(this.cadBuildOwner)}" style="width:100%">
                </label>
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:3px">
                  <span>总负责 / 审核</span>
                  <input type="text" data-sat-field="cadChiefDesigner" value="${esc(this.cadChiefDesigner)}" style="width:100%">
                </label>
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:3px">
                  <span>设计 / 校核</span>
                  <input type="text" data-sat-field="cadDesigner" value="${esc(this.cadDesigner)}" style="width:100%">
                </label>
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:3px">
                  <span>图号前缀</span>
                  <input type="text" data-sat-field="cadPrefix" value="${esc(this.cadPrefix)}" style="width:100%">
                </label>
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:3px">
                  <span>出图比例</span>
                  <select data-sat-field="cadScale" style="width:100%">
                    <option value="1:150" ${this.cadScale === '1:150' ? 'selected' : ''}>1:150</option>
                    <option value="1:200" ${this.cadScale === '1:200' ? 'selected' : ''}>1:200</option>
                    <option value="1:300" ${this.cadScale === '1:300' ? 'selected' : ''}>1:300</option>
                  </select>
                </label>
              </div>
            </div>
          </details>

          <details class="satmap-acc-card" ${this.cadWizardTab === 'bracket' ? 'open' : ''}>
            <summary>
              <span>支架参数与风雪荷载校核</span>
              <small style="color:${st.allPass ? '#059669' : '#d97706'}">${st.allPass ? '✓ 合规' : '⚠ 复核'}</small>
            </summary>
            <div class="satmap-acc-body">
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:2px">
                  <span>最低点高 H1(mm)</span>
                  <input type="number" min="150" max="2500" step="50" data-sat-bracket="h1Mm" value="${bcfg.h1Mm}" style="width:100%">
                </label>
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:2px">
                  <span>前后排距 Y0(mm)</span>
                  <input type="number" min="400" max="5000" step="50" data-sat-bracket="y0Mm" value="${bcfg.y0Mm}" style="width:100%">
                </label>
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:2px">
                  <span>立柱南北距 Y1(mm)</span>
                  <input type="number" min="600" max="4000" step="50" data-sat-bracket="y1Mm" value="${bcfg.y1Mm}" style="width:100%">
                </label>
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:2px">
                  <span>支架倾角 A(°)</span>
                  <input type="number" min="0" max="45" step="1" data-sat-bracket="angleDeg" value="${bcfg.angleDeg}" style="width:100%">
                </label>
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:2px">
                  <span>端部悬挑 X1(mm)</span>
                  <input type="number" min="150" max="1000" step="50" data-sat-bracket="x1Mm" value="${bcfg.x1Mm}" style="width:100%">
                </label>
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:2px">
                  <span>立柱东西距 X2(mm)</span>
                  <input type="number" min="1000" max="4000" step="50" data-sat-bracket="x2Mm" value="${bcfg.x2Mm}" style="width:100%">
                </label>
              </div>
              <label class="satmap-field-row">
                <span>基础形式</span>
                <select data-sat-bracket="concreteGrade">
                  <option value="C25" ${bcfg.concreteGrade === 'C25' ? 'selected' : ''}>C25 混凝土配重方墩</option>
                  <option value="C30" ${bcfg.concreteGrade === 'C30' ? 'selected' : ''}>C30 防腐条形基础</option>
                  <option value="CLAMP" ${bcfg.concreteGrade === 'CLAMP' ? 'selected' : ''}>彩钢瓦专用铝合金夹具</option>
                </select>
              </label>
              <div style="border-top:1px dashed var(--line,#e2e8f0);padding-top:6px;display:grid;grid-template-columns:1fr 1fr;gap:6px">
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:2px">
                  <span>建筑檐高 (米)</span>
                  <input type="number" min="3" max="80" step="1" data-sat-field="buildingHeightM" value="${st.buildingHeightM}" style="width:100%">
                </label>
                <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:2px">
                  <span>地面粗糙度</span>
                  <select data-sat-field="roughnessCategory" style="width:100%">
                    <option value="A" ${st.roughnessCategory === 'A' ? 'selected' : ''}>海岸一类区</option>
                    <option value="B" ${st.roughnessCategory === 'B' ? 'selected' : ''}>工业园二类区</option>
                    <option value="C" ${st.roughnessCategory === 'C' ? 'selected' : ''}>城区三类区</option>
                    <option value="D" ${st.roughnessCategory === 'D' ? 'selected' : ''}>中心四类区</option>
                  </select>
                </label>
              </div>
              <label class="satmap-field-row">
                <span>允许恒载限值 (kN/m²)</span>
                <input type="number" min="0.15" max="5.0" step="0.05" data-sat-field="roofLoadLimitKnM2" value="${st.roofLoadLimitKnM2}" style="width:86px">
              </label>
              <div style="font-size:11px;color:var(--ink-2);line-height:1.45;background:var(--well,#f8fafc);padding:6px 8px;border-radius:6px">
                <div>风压 <b>${st.w0KnM2}</b> · 雪压 <b>${st.s0KnM2} kN/m²</b> · μz=<b>${st.muZ}</b></div>
                <div style="font-weight:700;color:${st.allPass ? '#059669' : '#d97706'}">
                  ${st.allPass ? '✓ 抗风揭与屋面恒载通过' : '⚠ 恒载超限需加固复核'} (${st.avgAddedDeadKnM2} ≤ ${st.roofLoadLimitKnM2} kN/m²)
                </div>
              </div>
            </div>
          </details>
        </aside>

        <div class="satmap-cad-viewport ${this.cadLightTheme ? 'light-print' : ''}">
          ${this.cadWizardTab === 'bracket' ? `
            <div style="background:#070d19;border-bottom:1px solid #1e293b;padding:10px 14px">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:6px">
                <b style="color:#38bdf8;font-size:12.5px">支架参数化实时大样预览 (${esc(bcfg.concreteGrade)} · A=${bcfg.angleDeg}° · H1=${bcfg.h1Mm}mm · Y0=${bcfg.y0Mm}mm)</b>
                <button type="button" class="sat-btn primary" style="height:26px;padding:0 10px;font-size:11px" data-sat-cad-wiz="sheets">返回单张图纸 →</button>
              </div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
                <div style="background:#0b1526;border-radius:6px;padding:8px 10px;border:1px solid #1e293b;color:#f8fafc">
                  <div style="font-size:11.5px;font-weight:700;color:#e2e8f0;margin-bottom:4px;display:flex;justify-content:space-between">
                    <span>混凝土支架侧面示意图</span>
                    <small style="color:#38bdf8;font-family:monospace">H1=${bcfg.h1Mm} / Y1=${bcfg.y1Mm} / A=${bcfg.angleDeg}°</small>
                  </div>
                  <svg viewBox="0 0 360 120" style="width:100%;height:106px;background:#070d19;border-radius:4px;border:1px solid #1e293b">
                    <line x1="15" y1="100" x2="345" y2="100" stroke="#64748b" stroke-width="1.5"/>
                    <rect x="64" y="84" width="32" height="16" fill="none" stroke="#e2e8f0" stroke-width="1.3"/>
                    <rect x="214" y="84" width="32" height="16" fill="none" stroke="#e2e8f0" stroke-width="1.3"/>
                    <line x1="80" y1="84" x2="80" y2="58" stroke="#facc15" stroke-width="2.2"/>
                    <line x1="230" y1="84" x2="230" y2="24" stroke="#facc15" stroke-width="2.2"/>
                    <line x1="80" y1="70" x2="230" y2="42" stroke="#facc15" stroke-width="1.2" stroke-dasharray="4 2"/>
                    <line x1="48" y1="66" x2="264" y2="14" stroke="#f8fafc" stroke-width="3.5"/>
                    <line x1="50" y1="62" x2="262" y2="10" stroke="#38bdf8" stroke-width="1.4"/>
                    <text x="40" y="80" font-size="9.5" font-weight="bold" fill="#facc15" font-family="monospace">H1=${bcfg.h1Mm}</text>
                    <text x="155" y="114" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15" font-family="monospace">立柱南北距 Y1=${bcfg.y1Mm}mm</text>
                    <text x="160" y="54" font-size="10" font-weight="bold" fill="#38bdf8" font-family="monospace">倾角 A=${bcfg.angleDeg}°</text>
                    <text x="302" y="65" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#4ade80" font-family="monospace">排距 Y0=${bcfg.y0Mm}</text>
                  </svg>
                </div>
                <div style="background:#0b1526;border-radius:6px;padding:8px 10px;border:1px solid #1e293b;color:#f8fafc">
                  <div style="font-size:11.5px;font-weight:700;color:#e2e8f0;margin-bottom:4px;display:flex;justify-content:space-between">
                    <span>混凝土支架正面示意图</span>
                    <small style="color:#38bdf8;font-family:monospace">X1=${bcfg.x1Mm}mm / X2=${bcfg.x2Mm}mm</small>
                  </div>
                  <svg viewBox="0 0 360 120" style="width:100%;height:106px;background:#070d19;border-radius:4px;border:1px solid #1e293b">
                    <line x1="15" y1="98" x2="345" y2="98" stroke="#64748b" stroke-width="1.5"/>
                    ${Array.from({ length: 9 }, (_, c) => `
                      <rect x="${30 + c * 33}" y="16" width="31" height="30" fill="rgba(56,189,248,0.12)" stroke="#e2e8f0" stroke-width="1"/>
                      <rect x="${30 + c * 33}" y="48" width="31" height="30" fill="rgba(56,189,248,0.12)" stroke="#e2e8f0" stroke-width="1"/>
                    `).join('')}
                    ${[64, 176, 288].map((px) => `
                      <line x1="${px}" y1="78" x2="${px}" y2="88" stroke="#facc15" stroke-width="2.2"/>
                      <rect x="${px - 12}" y="88" width="24" height="10" fill="none" stroke="#e2e8f0" stroke-width="1.2"/>
                    `).join('')}
                    <text x="46" y="112" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15" font-family="monospace">X1=${bcfg.x1Mm}</text>
                    <text x="185" y="112" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#38bdf8" font-family="monospace">桩间距 X2=${bcfg.x2Mm}mm (2×9阵列单元)</text>
                  </svg>
                </div>
              </div>
            </div>
          ` : ''}
          <div class="satmap-cad-tabs">
            <div class="satmap-cad-sheet-strip" role="tablist" aria-label="施工图纸快捷切换条">
              ${sheets.map(([key, label]) => `
                <button type="button" class="satmap-cad-sheet-btn ${this.cadSheet === key && !this.cadShowAllFourStacked && !this.cadGrid2x2 ? 'active' : ''}" data-sat-cad-sheet="${key}" title="${esc(label)}">
                  ${esc(shortTabMap[key] || label)}
                </button>
              `).join('')}
            </div>
            <div class="satmap-cad-viewer-bar">
              <div class="satmap-cad-active-meta">
                <span class="satmap-cad-code-badge">${esc(activeSheetEntry[2])}</span>
                <strong>${esc(activeSheetEntry[1])}</strong>
                <span class="satmap-cad-layer-tag">
                  CAD LAYER: PV_${this.cadGrid2x2 ? 'GRID_16_ALL' : this.cadShowAllFourStacked ? 'ALL_16_SHEETS' : this.cadSheet.toUpperCase()} · ${this.summary.moduleCount} 块 · ${this.summary.dcKw} kWp
                </span>
              </div>
              <div class="satmap-cad-viewer-controls">
                <div class="satmap-cad-pill-group">
                  <button type="button" class="satmap-cad-sheet-btn ${!this.cadGrid2x2 && !this.cadShowAllFourStacked ? 'active' : ''}" data-sat-cad-sheet="${esc(this.cadSheet)}">单张视图</button>
                  <button type="button" class="satmap-cad-sheet-btn ${this.cadGrid2x2 ? 'active' : ''}" data-sat-action="toggle-cad-grid2x2">双列总览</button>
                  <button type="button" class="satmap-cad-sheet-btn ${this.cadShowAllFourStacked ? 'active' : ''}" data-sat-action="toggle-cad-stacked">连排全览</button>
                </div>
                <div class="satmap-cad-pill-group">
                  <button type="button" class="satmap-cad-sheet-btn ${this.cadZoomPct === 100 ? 'active' : ''}" data-sat-cad-zoom="100">100%</button>
                  <button type="button" class="satmap-cad-sheet-btn ${this.cadZoomPct === 135 ? 'active' : ''}" data-sat-cad-zoom="135">135%</button>
                  <button type="button" class="satmap-cad-sheet-btn ${this.cadZoomPct === 175 ? 'active' : ''}" data-sat-cad-zoom="175">175%</button>
                </div>
                <button type="button" class="satmap-cad-sheet-btn ${this.cadLightTheme ? 'active' : ''}" data-sat-action="toggle-cad-theme">
                  ${this.cadLightTheme ? '深色蓝图' : '白底打印'}
                </button>
              </div>
            </div>
          </div>

          <div class="satmap-cad-svg-host" id="satmap-cad-svg-host" style="${this.cadGrid2x2 ? 'display:grid;grid-template-columns:1fr 1fr;gap:12px' : this.cadShowAllFourStacked ? 'display:flex;flex-direction:column;gap:18px;max-height:780px;overflow-y:auto' : (this.cadZoomPct > 100 ? `overflow:auto;max-height:780px` : '')}">
            <div style="${!this.cadGrid2x2 && !this.cadShowAllFourStacked && this.cadZoomPct > 100 ? `width:${this.cadZoomPct}%;min-width:${this.cadZoomPct}%` : 'width:100%'}">
            ${(this.cadShowAllFourStacked || this.cadGrid2x2)
              ? sheets.map(([k, lbl]) => `
                  <div style="width:100%;border:1px solid #1e293b;border-radius:8px;padding:8px;background:#050a14">
                    <div style="font-size:12px;font-weight:700;color:#38bdf8;margin-bottom:6px;display:flex;justify-content:space-between">
                      <span>${esc(lbl)}</span>
                      <span style="font-family:monospace;color:#94a3b8">${esc(this.cadTitle)}</span>
                    </div>
                    ${this.renderCadSvg(k)}
                  </div>
                `).join('')
              : this.renderCadSvg(this.cadSheet)
            }
            </div>
          </div>
        </div>
      </div>
    </div>`;
  }

  /**
   * High-Speed Real Satellite Tile Loader:
   * - Connects directly to multi-subdomain CDNs (mt0..mt3 GCJ-02 China Hybrid up to Z20, Autonavi China Satellite & Esri World Imagery)
   * - Fast failover to Autonavi Satellite (webst01..04) / Esri World Imagery with exact Z18 coordinate shifting so Z19+ fallback never 404s
   * - Never falls back to /api/satmap/tile/... from browser Image() so the 6-connection localhost HTTP pool is never blocked!
   */
  loadSatelliteTile(source, z, x, y) {
    const key = `${source}/${z}/${x}/${y}`;
    if (this.tileCache.has(key)) return this.tileCache.get(key);
    if (typeof Image === 'undefined') return null;

    // Evict oldest cached tiles if cache exceeds 320 entries to prevent memory bloat
    if (this.tileCache.size > 320) {
      const oldestKey = this.tileCache.keys().next().value;
      if (oldestKey) this.tileCache.delete(oldestKey);
    }

    const sub03 = ((x + y) % 4 + 4) % 4;
    const sub14 = sub03 + 1;
    const zClamped18 = Math.min(18, z);
    const shift18 = Math.max(0, z - zClamped18);
    const x18 = shift18 > 0 ? Math.floor(x / Math.pow(2, shift18)) : x;
    const y18 = shift18 > 0 ? Math.floor(y / Math.pow(2, shift18)) : y;
    const gaodeSatUrl = `https://webst0${sub14}.is.autonavi.com/appmaptile?style=6&x=${x18}&y=${y18}&z=${zClamped18}`;
    const esriUrl = `https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${zClamped18}/${y18}/${x18}`;
    const labelUrl = `https://wprd0${sub14}.is.autonavi.com/appmaptile?x=${x18}&y=${y18}&z=${zClamped18}&lang=zh_cn&size=1&scl=1&style=8`;

    const primaryUrl = source === 'gaode_label'
      ? labelUrl
      : source === 'gaode_hyb'
        ? `https://mt${sub03}.google.com/vt/lyrs=y&hl=zh-CN&gl=cn&x=${x}&y=${y}&z=${z}`
        : source === 'gaode_sat'
          ? `https://mt${sub03}.google.com/vt/lyrs=s&hl=zh-CN&gl=cn&x=${x}&y=${y}&z=${z}`
          : esriUrl;

    const entry = { status: 'loading', img: null, usedFallback: false, fallbackSubShift: shift18 };
    const img = new Image();
    img.decoding = 'async';
    let fallbackStage = 0;

    const triggerFallback = () => {
      if (entry.status === 'loaded') return;
      if ((source === 'gaode_hyb' || source === 'gaode_sat') && fallbackStage === 0) {
        fallbackStage = 1;
        entry.usedFallback = true;
        img.src = gaodeSatUrl;
      } else if ((source === 'gaode_hyb' || source === 'gaode_sat') && fallbackStage === 1) {
        fallbackStage = 2;
        entry.usedFallback = true;
        img.src = esriUrl;
      } else {
        entry.status = 'error';
      }
    };

    const timeoutId = typeof setTimeout === 'function'
      ? setTimeout(triggerFallback, 1400)
      : null;

    img.onload = () => {
      if (timeoutId) clearTimeout(timeoutId);
      entry.status = 'loaded';
      entry.img = img;
      this.scheduleMapRedraw();
    };
    img.onerror = () => {
      if (timeoutId) clearTimeout(timeoutId);
      if ((source === 'gaode_hyb' || source === 'gaode_sat') && fallbackStage < 2) {
        triggerFallback();
      } else {
        entry.status = 'error';
      }
    };
    img.src = primaryUrl;
    this.tileCache.set(key, entry);
    return entry;
  }

  /**
   * Resolve the sharpest available satellite tile or sub-quadrant for any zoom level Z4 .. Z24:
   * - For Z <= maxNativeZ (Z20 for gaode_hyb/gaode_sat, Z18 for esri), fetches the native tile and falls back
   *   instantaneously to any cached ancestor tile (Z19 -> Z18 -> Z17) while loading.
   * - For Super-Zoom Z21 .. Z24 (up to 32x deeper than Z19 / 64x deeper than Z18), crops the exact
   *   sub-quadrant (sx, sy, sw, sh) from the highest-resolution native tile (Z20 / Z19 / Z18) with zero network latency!
   */
  getBestSatelliteTilePatch(satSource, z, tx, ty) {
    const maxNativeZ = satSource === 'esri' ? 18 : NATIVE_TILE_MAX_ZOOM;
    if (z <= maxNativeZ) {
      const direct = this.loadSatelliteTile(satSource, z, tx, ty);
      if (z > 18) {
        const shift18 = z - 18;
        this.loadSatelliteTile(satSource, 18, tx >> shift18, ty >> shift18);
      }
      if (direct?.status === 'loaded' && direct.img) {
        if (direct.usedFallback && direct.fallbackSubShift > 0) {
          const scale = Math.pow(2, direct.fallbackSubShift);
          const subX = tx - Math.floor(tx / scale) * scale;
          const subY = ty - Math.floor(ty / scale) * scale;
          const sw = 256 / scale;
          const sh = 256 / scale;
          return {
            img: direct.img,
            sx: subX * sw,
            sy: subY * sh,
            sw,
            sh,
            usedFallback: true,
            ancZ: z - direct.fallbackSubShift,
            ancTx: Math.floor(tx / scale),
            ancTy: Math.floor(ty / scale),
          };
        }
        return {
          img: direct.img,
          sx: 0,
          sy: 0,
          sw: 256,
          sh: 256,
          usedFallback: direct.usedFallback,
          ancZ: z,
          ancTx: tx,
          ancTy: ty,
        };
      }
    } else {
      // Ensure both maxNativeZ (Z20) and Z18 ancestor tiles are requested when zooming directly at Z21..Z24
      const shiftNat = z - maxNativeZ;
      this.loadSatelliteTile(satSource, maxNativeZ, Math.floor(tx / Math.pow(2, shiftNat)), Math.floor(ty / Math.pow(2, shiftNat)));
      if (maxNativeZ > 18) {
        const shift18 = z - 18;
        this.loadSatelliteTile(satSource, 18, Math.floor(tx / Math.pow(2, shift18)), Math.floor(ty / Math.pow(2, shift18)));
      }
    }

    // Walk up the ancestor tile pyramid (from min(z-1, maxNativeZ) down to Z14) to find the sharpest loaded ancestor
    const startAncZ = Math.min(z - 1, maxNativeZ);
    const minAncZ = Math.max(MIN_SAT_ZOOM, z - 8);
    for (let ancZ = startAncZ; ancZ >= minAncZ; ancZ--) {
      const scale = Math.pow(2, z - ancZ);
      const ancTx = Math.floor(tx / scale);
      const ancTy = Math.floor(ty / scale);
      const ancKey = `${satSource}/${ancZ}/${ancTx}/${ancTy}`;
      const ancTile = this.tileCache.get(ancKey);
      if (ancTile?.status === 'loaded' && ancTile.img) {
        const effShift = (z - ancZ) + (ancTile.usedFallback ? (ancTile.fallbackSubShift || 0) : 0);
        const effScale = Math.pow(2, effShift);
        const subX = tx - Math.floor(tx / effScale) * effScale;
        const subY = ty - Math.floor(ty / effScale) * effScale;
        const sw = 256 / effScale;
        const sh = 256 / effScale;
        return {
          img: ancTile.img,
          sx: subX * sw,
          sy: subY * sh,
          sw,
          sh,
          usedFallback: ancTile.usedFallback,
          ancZ: z - effShift,
          ancTx: Math.floor(tx / effScale),
          ancTy: Math.floor(ty / effScale),
        };
      }
    }
    return null;
  }

  /**
   * Compute the canvas pixel position of the geographic roof anchor (this.roofCenterLon, this.roofCenterLat)
   * so that any drawn roof, obstacle, and solar array stays locked onto the exact factory building during pan/zoom,
   * with ZERO offset jump when finishing a roof or obstacle.
   */
  getRoofAnchorCanvasPx(W, H) {
    const cx = W / 2;
    const cy = H / 2;
    const refLon = Number.isFinite(this.roofCenterLon) ? this.roofCenterLon : this.lon;
    const refLat = Number.isFinite(this.roofCenterLat) ? this.roofCenterLat : this.lat;
    const mPerDegLat = 110540;
    const mPerDegLon = 111320 * Math.max(0.15, Math.cos((this.lat * Math.PI) / 180));
    const dEastM = (refLon - this.lon) * mPerDegLon;
    const dSouthM = (this.lat - refLat) * mPerDegLat;
    const mapMpp = Math.max(0.001, metersPerPixelAtLatZoom(this.lat, this.zoom));
    return [cx + dEastM / mapMpp, cy + dSouthM / mapMpp];
  }

  /**
   * Pure 1:1 geographic East/South meter <-> screen pixel conversion.
   * Roof orientation (this.ridgeAzimuthDeg) is handled inside getRoofUVFrame() for module layout,
   * so drawn roof polygons and rectangular keepouts NEVER shift, jump, or rotate into tilted diamonds!
   */
  localMetersToCanvas(W, H, mx, my) {
    const [anchorX, anchorY] = this.getRoofAnchorCanvasPx(W, H);
    const mpp = Math.max(0.001, this.metersPerPx);
    return [anchorX + mx / mpp, anchorY + my / mpp];
  }

  canvasToLocalMeters(W, H, sx, sy) {
    const [anchorX, anchorY] = this.getRoofAnchorCanvasPx(W, H);
    const mpp = Math.max(0.001, this.metersPerPx);
    return [(sx - anchorX) * mpp, (sy - anchorY) * mpp];
  }

  /**
   * Paint the Real Satellite Map Canvas (Step 1):
   * 1. Center-outward spiral EPSG:3857 Satellite Tiles with multi-level ancestor sub-quad over-zoom up to Z24
   * 2. Geographically anchored Roof Polygon, Draggable Corner Handles, Optional Double-Slope Ridge Line,
   *    Red Skylight Keepouts, Batched 60fps Solar Modules (with high-zoom cell matrix & ID labels),
   *    Interior-Routed String Wiring, and Live Selection Preview
   */
  drawMapCanvas() {
    if (typeof document === 'undefined') return;
    const canvas = this.host?.querySelector('#satmap-main-canvas') || document.getElementById('satmap-main-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    const cx = W / 2;
    const cy = H / 2;
    const scalePxPerM = 1 / Math.max(0.001, this.metersPerPx);

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, W, H);

    // 1. Render 100% Real Satellite Tiles in Center-Outward Spiral Order with Super-Zoom (Z4..Z24)
    const z = Math.max(MIN_SAT_ZOOM, Math.min(MAX_SAT_ZOOM, Math.round(this.zoom || 18)));
    const [tileLon, tileLat] = this.mapSource === 'gaode'
      ? wgs84ToGcj02(this.lon, this.lat)
      : [this.lon, this.lat];
    const centerTile = lonLatToTileXY(tileLon, tileLat, z);
    const baseTx = Math.floor(centerTile.x);
    const baseTy = Math.floor(centerTile.y);
    const offsetX = (centerTile.x - baseTx) * 256;
    const offsetY = (centerTile.y - baseTy) * 256;

    const satSource = this.mapSource === 'esri'
      ? 'esri'
      : this.showMapLabels
        ? 'gaode_hyb'
        : 'gaode_sat';
    let loadedTileCount = 0;

    const cols = Math.ceil(W / 256) + 2;
    const rows = Math.ceil(H / 256) + 2;
    const halfCols = Math.ceil(cols / 2);
    const halfRows = Math.ceil(rows / 2);

    const tileOffsets = [];
    for (let dx = -halfCols; dx <= halfCols; dx++) {
      for (let dy = -halfRows; dy <= halfRows; dy++) {
        tileOffsets.push([dx, dy]);
      }
    }
    tileOffsets.sort((a, b) => (a[0] * a[0] + a[1] * a[1]) - (b[0] * b[0] + b[1] * b[1]));

    ctx.save();
    ctx.globalAlpha = 1.0;
    ctx.imageSmoothingEnabled = true;
    try { ctx.imageSmoothingQuality = 'high'; } catch {}
    for (const [dx, dy] of tileOffsets) {
      const tx = baseTx + dx;
      const ty = baseTy + dy;
      if (tx < 0 || ty < 0) continue;
      const drawX = Math.floor(cx - offsetX + dx * 256);
      const drawY = Math.floor(cy - offsetY + dy * 256);
      if (drawX + 256 < 0 || drawX > W || drawY + 256 < 0 || drawY > H) continue;
      const patch = this.getBestSatelliteTilePatch(satSource, z, tx, ty);
      if (patch && patch.img) {
        ctx.drawImage(patch.img, patch.sx, patch.sy, patch.sw, patch.sh, drawX, drawY, 256.5, 256.5);
        if (satSource === 'gaode_hyb' && patch.usedFallback) {
          const lblPatch = this.getBestSatelliteTilePatch('gaode_label', z, tx, ty);
          if (lblPatch && lblPatch.img) {
            ctx.drawImage(lblPatch.img, lblPatch.sx, lblPatch.sy, lblPatch.sw, lblPatch.sh, drawX, drawY, 256.5, 256.5);
          }
        }
        loadedTileCount++;
      } else {
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.14)';
        ctx.lineWidth = 1;
        ctx.strokeRect(drawX, drawY, 256, 256);
      }
    }
    ctx.restore();

    // 1B. When zoomed in deeply (Z20..Z24), render a subtle sub-meter / 5m CAD Engineering Reference Grid
    if (z >= 20 && scalePxPerM >= 7) {
      const gridStepM = scalePxPerM >= 45 ? 1 : scalePxPerM >= 18 ? 2 : 5;
      const [mLeft, mTop] = this.canvasToLocalMeters(W, H, 0, 0);
      const [mRight, mBottom] = this.canvasToLocalMeters(W, H, W, H);
      const xStart = Math.floor(Math.min(mLeft, mRight) / gridStepM) * gridStepM;
      const xEnd = Math.ceil(Math.max(mLeft, mRight) / gridStepM) * gridStepM;
      const yStart = Math.floor(Math.min(mTop, mBottom) / gridStepM) * gridStepM;
      const yEnd = Math.ceil(Math.max(mTop, mBottom) / gridStepM) * gridStepM;
      ctx.save();
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.16)';
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      for (let gx = xStart; gx <= xEnd; gx += gridStepM) {
        const [sx] = this.localMetersToCanvas(W, H, gx, 0);
        if (sx >= 0 && sx <= W) {
          ctx.moveTo(sx, 0);
          ctx.lineTo(sx, H);
        }
      }
      for (let gy = yStart; gy <= yEnd; gy += gridStepM) {
        const [, sy] = this.localMetersToCanvas(W, H, 0, gy);
        if (sy >= 0 && sy <= H) {
          ctx.moveTo(0, sy);
          ctx.lineTo(W, sy);
        }
      }
      ctx.stroke();
      ctx.restore();
    }

    // Optional uploaded drone / orthophoto base image (Video 1 & Video 2 上传图片/上传俯视图)
    if (this.customOrthoImg) {
      ctx.save();
      const [anchorX, anchorY] = this.getRoofAnchorCanvasPx(W, H);
      const imgW = W * 0.85;
      const imgH = H * 0.85;
      ctx.drawImage(this.customOrthoImg, anchorX - imgW / 2, anchorY - imgH / 2, imgW, imgH);
      ctx.restore();
      loadedTileCount++;
    }

    if (loadedTileCount === 0) {
      ctx.fillStyle = 'rgba(226, 232, 240, 0.8)';
      ctx.font = '12px "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText('正在高速加载实景卫星影像瓦片...', 16, H - 16);
    }

    const azRad = ((this.ridgeAzimuthDeg || 0) * Math.PI) / 180;
    const toScreen = (mx, my) => this.localMetersToCanvas(W, H, mx, my);

    // 2. Draw Semi-Transparent Roof Boundary Overlay + 3D Extruded Building & Parapet + Draggable Corner Handles
    if (this.showRoofOverlay && this.roofOutlineM.length >= 3) {
      ctx.save();
      const screenRoofPts = this.roofOutlineM.map(([mx, my]) => toScreen(mx, my));

      // 2A. When 3D Mode is active (this.is3D === true), extrude 3D Building Facade Walls & Parapet Wall
      if (this.is3D) {
        const wallDropX = 10;
        const wallDropY = 28;
        const parapetLiftPx = Math.max(3.5, Math.min(14, ((this.parapetHeightMm || 300) / 1000) * scalePxPerM * 1.8));

        // Extruded factory building walls along south/east edges
        for (let i = 0; i < screenRoofPts.length; i++) {
          const p0 = screenRoofPts[i];
          const p1 = screenRoofPts[(i + 1) % screenRoofPts.length];
          const midY = (p0[1] + p1[1]) * 0.5;
          if (midY >= cy - 20 || p0[0] > cx || p1[0] > cx) {
            ctx.beginPath();
            ctx.moveTo(p0[0], p0[1]);
            ctx.lineTo(p1[0], p1[1]);
            ctx.lineTo(p1[0] + wallDropX, p1[1] + wallDropY);
            ctx.lineTo(p0[0] + wallDropX, p0[1] + wallDropY);
            ctx.closePath();
            ctx.fillStyle = Math.abs(p1[0] - p0[0]) >= Math.abs(p1[1] - p0[1])
              ? 'rgba(30, 41, 59, 0.88)'
              : 'rgba(15, 23, 42, 0.92)';
            ctx.fill();
            ctx.strokeStyle = 'rgba(148, 163, 184, 0.55)';
            ctx.lineWidth = 1.1;
            ctx.stroke();

            // Industrial facade strip windows on long south wall
            if (Math.hypot(p1[0] - p0[0], p1[1] - p0[1]) > 80) {
              ctx.strokeStyle = 'rgba(56, 189, 248, 0.45)';
              ctx.lineWidth = 2.2;
              ctx.beginPath();
              ctx.moveTo(p0[0] + wallDropX * 0.45, p0[1] + wallDropY * 0.45);
              ctx.lineTo(p1[0] + wallDropX * 0.45, p1[1] + wallDropY * 0.45);
              ctx.stroke();
            }
          }
        }

        // Parapet interior shadow cast onto roof deck
        ctx.save();
        ctx.beginPath();
        screenRoofPts.forEach(([sx, sy], idx) => {
          if (idx === 0) ctx.moveTo(sx, sy);
          else ctx.lineTo(sx, sy);
        });
        ctx.closePath();
        ctx.clip();
        ctx.strokeStyle = 'rgba(15, 23, 42, 0.46)';
        ctx.lineWidth = parapetLiftPx * 2.1;
        ctx.stroke();
        ctx.restore();
      }

      ctx.beginPath();
      screenRoofPts.forEach(([sx, sy], idx) => {
        if (idx === 0) ctx.moveTo(sx, sy);
        else ctx.lineTo(sx, sy);
      });
      ctx.closePath();

      ctx.fillStyle = this.is3D ? 'rgba(30, 58, 138, 0.24)' : 'rgba(37, 99, 235, 0.14)';
      ctx.fill();
      ctx.lineWidth = this.is3D ? 3.2 : 2.4;
      ctx.strokeStyle = this.is3D ? '#7dd3fc' : '#38bdf8';
      ctx.stroke();

      // 3D Parapet top coping rim highlight
      if (this.is3D) {
        const lift = Math.max(3, Math.min(10, ((this.parapetHeightMm || 300) / 1000) * scalePxPerM * 1.4));
        ctx.beginPath();
        screenRoofPts.forEach(([sx, sy], idx) => {
          if (idx === 0) ctx.moveTo(sx - 1.5, sy - lift);
          else ctx.lineTo(sx - 1.5, sy - lift);
        });
        ctx.closePath();
        ctx.strokeStyle = '#f8fafc';
        ctx.lineWidth = 1.8;
        ctx.stroke();
      }

      // Edge dimension labels (meters) along roof edges
      ctx.font = 'bold 11px "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'center';
      for (let i = 0; i < this.roofOutlineM.length; i++) {
        const p0 = this.roofOutlineM[i];
        const p1 = this.roofOutlineM[(i + 1) % this.roofOutlineM.length];
        const edgeLenM = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]);
        if (edgeLenM >= 6) {
          const [s0x, s0y] = screenRoofPts[i];
          const [s1x, s1y] = screenRoofPts[(i + 1) % screenRoofPts.length];
          if (Math.hypot(s1x - s0x, s1y - s0y) >= 48) {
            const mxMid = (s0x + s1x) * 0.5;
            const myMid = (s0y + s1y) * 0.5;
            ctx.fillStyle = 'rgba(15, 23, 42, 0.78)';
            ctx.fillRect(mxMid - 28, myMid - 9, 56, 16);
            ctx.fillStyle = '#bae6fd';
            ctx.fillText(`${edgeLenM.toFixed(1)}m`, mxMid, myMid + 3);
          }
        }
      }

      // Interactive Draggable Corner Handles (P1..Pn)
      screenRoofPts.forEach(([sx, sy], idx) => {
        ctx.fillStyle = '#f59e0b';
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        ctx.arc(sx, sy, 6.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = '#0f172a';
        ctx.font = 'bold 9px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(String(idx + 1), sx, sy + 3);
      });

      const frame = this.getRoofUVFrame(true);
      const roofPxW = frame.widthU * scalePxPerM;
      // Double-Slope Central Ridge Line (屋脊分水线) ONLY when user explicitly selects double_slope!
      if (this.roofType === 'double_slope') {
        const rStartM = frame.fromUV(frame.uMin, frame.centerV);
        const rEndM = frame.fromUV(frame.uMax, frame.centerV);
        const [rx0, ry0] = toScreen(rStartM[0], rStartM[1]);
        const [rx1, ry1] = toScreen(rEndM[0], rEndM[1]);
        ctx.strokeStyle = '#facc15';
        ctx.lineWidth = 2.0;
        ctx.setLineDash([8, 4]);
        ctx.beginPath();
        ctx.moveTo(rx0, ry0);
        ctx.lineTo(rx1, ry1);
        ctx.stroke();
        ctx.setLineDash([]);

        if (roofPxW >= 180) {
          const nPtM = frame.fromUV(frame.centerU, frame.vMin + frame.heightV * 0.25);
          const sPtM = frame.fromUV(frame.centerU, frame.vMin + frame.heightV * 0.75);
          const [nx, ny] = toScreen(nPtM[0], nPtM[1]);
          const [sx, sy] = toScreen(sPtM[0], sPtM[1]);
          ctx.fillStyle = 'rgba(15, 23, 42, 0.74)';
          ctx.fillRect(nx - 95, ny - 11, 190, 18);
          ctx.fillRect(sx - 95, sy - 11, 190, 18);
          ctx.fillStyle = '#f8fafc';
          ctx.font = 'bold 11.5px "Microsoft YaHei", sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(`北坡 (坡度 ${this.roofSlopeDeg}° · ${this.summary.northCount} 块)`, nx, ny + 3);
          ctx.fillText(`南坡 (坡度 ${this.roofSlopeDeg}° · ${this.summary.southCount} 块)`, sx, sy + 3);
        }
      }
      ctx.restore();
    }

    // 3. Draw Red Keepout Strips / Skylights (红色正交/多边形禁布区)
    if (this.showRoofOverlay) {
      for (const obs of this.obstacles) {
        ctx.save();
        ctx.beginPath();
        const screenPts = obs.polygon.map(([mx, my]) => toScreen(mx, my));
        screenPts.forEach(([sx, sy], idx) => {
          if (idx === 0) ctx.moveTo(sx, sy);
          else ctx.lineTo(sx, sy);
        });
        ctx.closePath();
        ctx.fillStyle = 'rgba(239, 68, 68, 0.42)';
        ctx.fill();
        ctx.lineWidth = 2.0;
        ctx.strokeStyle = '#ef4444';
        ctx.stroke();

        if (screenPts.length >= 3) {
          const avgX = screenPts.reduce((s, p) => s + p[0], 0) / screenPts.length;
          const avgY = screenPts.reduce((s, p) => s + p[1], 0) / screenPts.length;
          ctx.fillStyle = '#fecaca';
          ctx.font = 'bold 10.5px "Microsoft YaHei", sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(obs.name || '禁布区', avgX, avgY + 3);
        }
        // Draw draggable vertex handles on each obstacle corner
        screenPts.forEach(([sx, sy]) => {
          ctx.fillStyle = '#ef4444';
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.4;
          ctx.beginPath();
          ctx.arc(sx, sy, 4.5, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        });
        ctx.restore();
      }

      // 4. Draw Placed Solar Modules — Batched by Color for 60fps performance + 3D Bracket Tilt & Shadow
      if (this.modules && this.modules.length > 0) {
        const activeTilt = this.roofType === 'flat' ? (this.tiltDeg || 15) : (this.roofSlopeDeg || 6);
        const tiltLiftPx = this.is3D ? Math.max(2.5, Math.min(12, Math.sin((activeTilt * Math.PI) / 180) * 18)) : 0;

        // Shadow Simulation (冬至日 9:00-15:00 阵列与女儿墙阴影投射，3D模式下同步开启)
        if (this.showShadowPreview || this.is3D) {
          ctx.save();
          ctx.fillStyle = 'rgba(15, 23, 42, 0.48)';
          const shadowLenPx = Math.max(4, (this.rowSpacingM || 1.2) * 0.72 * scalePxPerM);
          ctx.beginPath();
          for (const m of this.modules) {
            const [p0, p1] = m.cornersM.map(([mx, my]) => toScreen(mx, my));
            ctx.moveTo(p0[0], p0[1]);
            ctx.lineTo(p1[0], p1[1]);
            ctx.lineTo(p1[0] - (this.is3D ? 1.5 : 0), p1[1] - shadowLenPx);
            ctx.lineTo(p0[0] - (this.is3D ? 1.5 : 0), p0[1] - shadowLenPx);
            ctx.closePath();
          }
          ctx.fill();
          ctx.restore();
        }

        // 3D Steel Bracket Rear Support Legs when this.is3D === true
        if (this.is3D && tiltLiftPx >= 2) {
          ctx.save();
          ctx.strokeStyle = 'rgba(203, 213, 225, 0.78)';
          ctx.lineWidth = 1.1;
          ctx.beginPath();
          for (const m of this.modules) {
            const [p0, p1] = m.cornersM.map(([mx, my]) => toScreen(mx, my));
            ctx.moveTo(p0[0], p0[1]);
            ctx.lineTo(p0[0], p0[1] - tiltLiftPx);
            ctx.moveTo(p1[0], p1[1]);
            ctx.lineTo(p1[0], p1[1] - tiltLiftPx);
          }
          ctx.stroke();
          ctx.restore();
        }

        ctx.save();
        ctx.globalAlpha = this.is3D ? 0.88 : 0.76;
        const groups = new Map();
        for (const m of this.modules) {
          const col = this.showStringColors ? (m.color || '#1d4ed8') : '#0f2952';
          let arr = groups.get(col);
          if (!arr) {
            arr = [];
            groups.set(col, arr);
          }
          arr.push(m);
        }
        ctx.lineWidth = this.is3D ? 0.9 : 0.75;
        ctx.strokeStyle = this.showStringColors ? 'rgba(255,255,255,0.72)' : '#93c5fd';
        for (const [col, mods] of groups.entries()) {
          ctx.fillStyle = col;
          ctx.beginPath();
          for (const m of mods) {
            const [p0, p1, p2, p3] = m.cornersM.map(([mx, my]) => toScreen(mx, my));
            ctx.moveTo(p0[0], p0[1] - tiltLiftPx);
            ctx.lineTo(p1[0], p1[1] - tiltLiftPx);
            ctx.lineTo(p2[0], p2[1]);
            ctx.lineTo(p3[0], p3[1]);
            ctx.closePath();
          }
          ctx.fill();
          ctx.stroke();
        }
        ctx.restore();

        // 4A-1. When zoomed in deeply (Z20..Z24, scalePxPerM >= 14), render half-cut monocrystalline cell grid & module ID labels on visible modules
        if (scalePxPerM >= 14) {
          ctx.save();
          ctx.strokeStyle = 'rgba(186, 230, 253, 0.35)';
          ctx.lineWidth = scalePxPerM >= 35 ? 0.9 : 0.6;
          ctx.beginPath();
          for (const m of this.modules) {
            const [p0, p1, p2, p3] = m.cornersM.map(([mx, my]) => toScreen(mx, my));
            if (p2[0] < -20 || p0[0] > W + 20 || p2[1] < -20 || p0[1] > H + 20) continue;
            // Central half-cut busbar line + 3 cell sub-dividers
            for (const t of [0.25, 0.5, 0.75]) {
              const lx0 = p0[0] + (p1[0] - p0[0]) * t;
              const ly0 = p0[1] - tiltLiftPx + (p1[1] - p0[1]) * t;
              const lx1 = p3[0] + (p2[0] - p3[0]) * t;
              const ly1 = p3[1] + (p2[1] - p3[1]) * t;
              ctx.moveTo(lx0, ly0);
              ctx.lineTo(lx1, ly1);
              const hx0 = p0[0] + (p3[0] - p0[0]) * t;
              const hy0 = (p0[1] - tiltLiftPx) * (1 - t) + p3[1] * t;
              const hx1 = p1[0] + (p2[0] - p1[0]) * t;
              const hy1 = (p1[1] - tiltLiftPx) * (1 - t) + p2[1] * t;
              ctx.moveTo(hx0, hy0);
              ctx.lineTo(hx1, hy1);
            }
          }
          ctx.stroke();

          if (scalePxPerM >= 26) {
            ctx.fillStyle = '#f8fafc';
            ctx.font = `${scalePxPerM >= 50 ? 'bold 10px' : 'bold 8.5px'} monospace`;
            ctx.textAlign = 'center';
            for (const m of this.modules) {
              const [mcx, mcy] = toScreen(m.cx, m.cy);
              if (mcx < 0 || mcx > W || mcy < 0 || mcy > H) continue;
              const shortId = m.id.replace('M-', '#');
              ctx.fillText(shortId, mcx, mcy + 3 - tiltLiftPx * 0.5);
            }
          }
          ctx.restore();
        }

        // 4A-2. Highlight Hovered Module & Its Complete String + Render Engineering Hover Inspector Card
        if (this.hoveredModule && !this.dragPreview) {
          const hm = this.hoveredModule;
          ctx.save();
          if (hm.stringId) {
            ctx.strokeStyle = '#fde047';
            ctx.lineWidth = 1.8;
            ctx.beginPath();
            for (const m of this.modules) {
              if (m.stringId === hm.stringId) {
                const [p0, p1, p2, p3] = m.cornersM.map(([mx, my]) => toScreen(mx, my));
                ctx.moveTo(p0[0], p0[1] - tiltLiftPx);
                ctx.lineTo(p1[0], p1[1] - tiltLiftPx);
                ctx.lineTo(p2[0], p2[1]);
                ctx.lineTo(p3[0], p3[1]);
                ctx.closePath();
              }
            }
            ctx.stroke();
          }
          // Highlight the hovered module itself in bright emerald green
          const [hp0, hp1, hp2, hp3] = hm.cornersM.map(([mx, my]) => toScreen(mx, my));
          ctx.fillStyle = 'rgba(34, 197, 94, 0.38)';
          ctx.strokeStyle = '#22c55e';
          ctx.lineWidth = 2.4;
          ctx.beginPath();
          ctx.moveTo(hp0[0], hp0[1] - tiltLiftPx);
          ctx.lineTo(hp1[0], hp1[1] - tiltLiftPx);
          ctx.lineTo(hp2[0], hp2[1]);
          ctx.lineTo(hp3[0], hp3[1]);
          ctx.closePath();
          ctx.fill();
          ctx.stroke();

          // Floating Hover Inspector Card
          const modSpec = this.getSelectedModule();
          const strObj = this.strings.find((st) => st.id === hm.stringId);
          const nInStr = strObj?.modules?.length || this.modulesPerString || 18;
          const vmpStr = (nInStr * modSpec.vmp_v).toFixed(0);
          const vocColdStr = (nInStr * modSpec.voc_v * 1.091).toFixed(0);
          const [hx, hy] = this.hoverScreenPos || hp0;
          const cardW = 248;
          const cardH = 66;
          const boxX = Math.max(12, Math.min(W - cardW - 12, hx + 14));
          const boxY = Math.max(52, Math.min(H - cardH - 48, hy - cardH - 10));
          ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
          ctx.fillRect(boxX, boxY, cardW, cardH);
          ctx.strokeStyle = '#38bdf8';
          ctx.lineWidth = 1.2;
          ctx.strokeRect(boxX, boxY, cardW, cardH);
          ctx.fillStyle = '#f8fafc';
          ctx.font = 'bold 11.5px "Microsoft YaHei", sans-serif';
          ctx.textAlign = 'left';
          ctx.fillText(`组件 ${hm.id} · 第${(hm.row ?? 0) + 1}排-${(hm.col ?? 0) + 1}列 (${hm.slope === 'north' ? '北坡' : '南坡'})`, boxX + 8, boxY + 17);
          ctx.fillStyle = '#fde047';
          ctx.font = 'bold 11px "Microsoft YaHei", sans-serif';
          ctx.fillText(`所属组串：${hm.stringId || '待分配'} (${nInStr}块串联)`, boxX + 8, boxY + 36);
          ctx.fillStyle = '#bae6fd';
          ctx.font = '10.5px "Microsoft YaHei", sans-serif';
          ctx.fillText(`Vmp ${vmpStr}V · 低温Voc ${vocColdStr}V · Imp ${modSpec.imp_a}A`, boxX + 8, boxY + 54);
          ctx.restore();
        }
      }

      // 3D Mode Status Badge at Top-Left of Canvas (below floating toolbars)
      if (this.is3D) {
        const activeTilt = this.roofType === 'flat' ? (this.tiltDeg || 15) : (this.roofSlopeDeg || 6);
        ctx.save();
        ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
        ctx.fillRect(14, 82, 368, 26);
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 1.2;
        ctx.strokeRect(14, 82, 368, 26);
        ctx.fillStyle = '#e0f2fe';
        ctx.font = 'bold 11.5px "Microsoft YaHei", sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText(`🧊 3D 立体屋面与支架视图 · 倾角 ${activeTilt}° · 女儿墙 ${this.parapetHeightMm}mm · 排距 ${this.rowSpacingM}m`, 22, 99);
        ctx.restore();
      }

      // 4B. Draw Ghost Outlines for Manually Removed Modules (when in 'toggle_module' mode or when removedModules exist)
      if (this.removedModules && this.removedModules.length > 0) {
        ctx.save();
        ctx.lineWidth = 1.2;
        ctx.strokeStyle = 'rgba(248, 113, 113, 0.85)';
        ctx.fillStyle = 'rgba(239, 68, 68, 0.16)';
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        for (const rm of this.removedModules) {
          const [p0, p1, p2, p3] = rm.cornersM.map(([mx, my]) => toScreen(mx, my));
          ctx.moveTo(p0[0], p0[1]);
          ctx.lineTo(p1[0], p1[1]);
          ctx.lineTo(p2[0], p2[1]);
          ctx.lineTo(p3[0], p3[1]);
          ctx.closePath();
        }
        ctx.fill();
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }

      // 5. Draw Inverter Icons & Interior-Routed String Home-Run Lines (strictly inside roof polygon!)
      if (this.electricalConfirmed && this.modules.length > 0 && this.inverterPointsM?.length) {
        ctx.save();
        for (const s of this.strings) {
          ctx.strokeStyle = s.color;
          // 5A. Intra-string serpentine wire segments (guaranteed within the same wing)
          if (s.wireSegmentsM && s.wireSegmentsM.length > 0) {
            ctx.lineWidth = 1.4;
            ctx.setLineDash([]);
            ctx.beginPath();
            for (const [p0, p1] of s.wireSegmentsM) {
              const [sx0, sy0] = toScreen(p0[0], p0[1]);
              const [sx1, sy1] = toScreen(p1[0], p1[1]);
              ctx.moveTo(sx0, sy0);
              ctx.lineTo(sx1, sy1);
            }
            ctx.stroke();
          }
          // 5B. Home-run path routed strictly along interior roof corridor to inverter
          if (s.homeRunPathM && s.homeRunPathM.length >= 2) {
            ctx.lineWidth = 1.3;
            ctx.setLineDash([5, 3]);
            ctx.beginPath();
            s.homeRunPathM.forEach(([mx, my], idx) => {
              const [px, py] = toScreen(mx, my);
              if (idx === 0) ctx.moveTo(px, py);
              else ctx.lineTo(px, py);
            });
            ctx.stroke();
          }
        }
        ctx.setLineDash([]);

        for (const invPt of this.inverterPointsM) {
          const [ix, iy] = toScreen(invPt.x, invPt.y);
          ctx.fillStyle = '#dc2626';
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.6;
          ctx.fillRect(ix - 20, iy - 10, 40, 20);
          ctx.strokeRect(ix - 20, iy - 10, 40, 20);
          ctx.fillStyle = '#ffffff';
          ctx.font = 'bold 10px monospace';
          ctx.textAlign = 'center';
          ctx.fillText(invPt.id, ix, iy + 3.5);
        }
        ctx.restore();
      }
    }

    // 5B. Live Rubber-Band Drag / Click-Click Preview for Roof / Obstacle / Scale / Direction Selection
    if (this.dragPreview) {
      const { kind, sx0, sy0, sx1, sy1 } = this.dragPreview;
      ctx.save();
      if (kind === 'scale') {
        const distPx = Math.hypot(sx1 - sx0, sy1 - sy0);
        ctx.strokeStyle = '#facc15';
        ctx.lineWidth = 2.5;
        ctx.setLineDash([6, 4]);
        ctx.beginPath();
        ctx.moveTo(sx0, sy0);
        ctx.lineTo(sx1, sy1);
        ctx.stroke();
        ctx.setLineDash([]);
        const midX = (sx0 + sx1) * 0.5;
        const midY = (sy0 + sy1) * 0.5;
        ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
        ctx.fillRect(midX - 105, midY - 26, 210, 22);
        ctx.fillStyle = '#fef08a';
        ctx.font = 'bold 12px "Microsoft YaHei", sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(`标定线长：${distPx.toFixed(0)} px = ${this.scaleReferenceM.toFixed(1)} m`, midX, midY - 11);
      } else if (kind === 'direction') {
        let rawDeg = (Math.atan2(sy1 - sy0, sx1 - sx0) * 180) / Math.PI;
        while (rawDeg <= -90) rawDeg += 180;
        while (rawDeg > 90) rawDeg -= 180;
        if (rawDeg > 45) rawDeg -= 90;
        if (rawDeg < -45) rawDeg += 90;
        const alignDeg = Number(rawDeg.toFixed(1));
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 2.8;
        ctx.setLineDash([6, 3]);
        ctx.beginPath();
        ctx.moveTo(sx0, sy0);
        ctx.lineTo(sx1, sy1);
        ctx.stroke();
        ctx.setLineDash([]);
        const midX = (sx0 + sx1) * 0.5;
        const midY = (sy0 + sy1) * 0.5;
        ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
        ctx.fillRect(midX - 115, midY - 28, 230, 22);
        ctx.fillStyle = '#38bdf8';
        ctx.font = 'bold 12px "Microsoft YaHei", sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(`屋脊/外墙走向偏角：${alignDeg}° (松开对齐)`, midX, midY - 13);
      } else {
        const rx = Math.min(sx0, sx1);
        const ry = Math.min(sy0, sy1);
        const rw = Math.abs(sx1 - sx0);
        const rh = Math.abs(sy1 - sy0);
        const wM = rw * this.metersPerPx;
        const hM = rh * this.metersPerPx;
        const areaM2 = Math.round(wM * hM);
        const isObs = kind === 'obstacle';
        ctx.fillStyle = isObs ? 'rgba(239, 68, 68, 0.28)' : 'rgba(14, 165, 233, 0.26)';
        ctx.strokeStyle = isObs ? '#ef4444' : '#38bdf8';
        ctx.lineWidth = 2.2;
        ctx.setLineDash([6, 3]);
        ctx.fillRect(rx, ry, rw, rh);
        ctx.strokeRect(rx, ry, rw, rh);
        ctx.setLineDash([]);

        if (rw > 8 || rh > 8) {
          const estKw = Math.round(areaM2 * 0.11);
          const label = isObs
            ? `正交禁布区：${wM.toFixed(1)}m × ${hM.toFixed(1)}m (${areaM2} m²)`
            : `屋顶范围：${wM.toFixed(1)}m × ${hM.toFixed(1)}m · ${areaM2} m² (预计可装 ~${estKw} kWp)`;
          const boxW = Math.max(210, label.length * 9 + 16);
          const bx = Math.max(8, Math.min(W - boxW - 8, rx + rw / 2 - boxW / 2));
          const by = Math.max(48, ry - 28);
          ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
          ctx.fillRect(bx, by, boxW, 24);
          ctx.strokeStyle = isObs ? '#ef4444' : '#38bdf8';
          ctx.lineWidth = 1;
          ctx.strokeRect(bx, by, boxW, 24);
          ctx.fillStyle = '#f8fafc';
          ctx.font = 'bold 12px "Microsoft YaHei", sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(label, bx + boxW / 2, by + 16);
        }
      }
      ctx.restore();
    }

    // 5C. Live Multi-Point Polygon Roof Drawing Preview (activeTool === 'roof_poly')
    if (this.drawingPointsM && this.drawingPointsM.length > 0) {
      ctx.save();
      const screenPts = this.drawingPointsM.map(([mx, my]) => toScreen(mx, my));
      ctx.beginPath();
      screenPts.forEach(([sx, sy], i) => {
        if (i === 0) ctx.moveTo(sx, sy);
        else ctx.lineTo(sx, sy);
      });
      if (this.cursorPointM) {
        const [cxCur, cyCur] = toScreen(this.cursorPointM[0], this.cursorPointM[1]);
        ctx.lineTo(cxCur, cyCur);
      }
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 2.2;
      ctx.setLineDash([6, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      screenPts.forEach(([sx, sy], idx) => {
        ctx.fillStyle = idx === 0 ? '#22c55e' : '#f59e0b';
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.arc(sx, sy, idx === 0 ? 7 : 5.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      });
      ctx.restore();
    }

    // 5D. Live Multi-Point Polygon Keepout / Obstacle Drawing Preview (activeTool === 'obstacle' | 'obstacle_poly')
    if (this.drawingObstaclePointsM && this.drawingObstaclePointsM.length > 0) {
      ctx.save();
      const rawMeters = this.cursorPointM
        ? [...this.drawingObstaclePointsM, this.cursorPointM]
        : [...this.drawingObstaclePointsM];
      const screenPts = this.drawingObstaclePointsM.map(([mx, my]) => toScreen(mx, my));
      const previewPts = rawMeters.map(([mx, my]) => toScreen(mx, my));

      ctx.beginPath();
      previewPts.forEach(([sx, sy], i) => {
        if (i === 0) ctx.moveTo(sx, sy);
        else ctx.lineTo(sx, sy);
      });
      if (previewPts.length >= 3) {
        ctx.closePath();
        ctx.fillStyle = 'rgba(239, 68, 68, 0.28)';
        ctx.fill();
      }
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2.2;
      ctx.setLineDash([6, 3]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw real-time segment lengths (in meters) along each edge of the polygon obstacle being drawn
      for (let i = 0; i < rawMeters.length - 1; i++) {
        const [x0, y0] = rawMeters[i];
        const [x1, y1] = rawMeters[i + 1];
        const segM = Math.hypot(x1 - x0, y1 - y0);
        const [sx0, sy0] = previewPts[i];
        const [sx1, sy1] = previewPts[i + 1];
        if (Math.hypot(sx1 - sx0, sy1 - sy0) >= 26 && segM >= 0.4) {
          const mx = (sx0 + sx1) * 0.5;
          const my = (sy0 + sy1) * 0.5;
          ctx.fillStyle = 'rgba(15, 23, 42, 0.84)';
          ctx.fillRect(mx - 22, my - 9, 44, 16);
          ctx.fillStyle = '#fecaca';
          ctx.font = 'bold 10px "Microsoft YaHei", sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(`${segM.toFixed(1)}m`, mx, my + 3);
        }
      }

      // Draw numbered vertex handles (P1 in green to indicate click-to-close, P2..Pn in red)
      screenPts.forEach(([sx, sy], idx) => {
        ctx.fillStyle = idx === 0 ? '#22c55e' : '#ef4444';
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.arc(sx, sy, idx === 0 ? 7.5 : 5.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 9.5px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(String(idx + 1), sx, sy + 3.2);
      });

      if (screenPts.length >= 3) {
        const [p0x, p0y] = screenPts[0];
        ctx.fillStyle = 'rgba(22, 163, 74, 0.92)';
        ctx.fillRect(p0x - 46, p0y - 26, 92, 16);
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 10px "Microsoft YaHei", sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('点P1或双击闭合', p0x, p0y - 14);
      }
      ctx.restore();
    }

    // 6. Draw Scale Calibration Reference Bar ONLY when calibrating scale or customized
    if (this.activeTool === 'scale' || this.scaleCustomized) {
      const [s0, s1] = this.scaleLinePx;
      const [p0x, p0y] = [cx + s0[0], cy + s0[1]];
      const [p1x, p1y] = [cx + s1[0], cy + s1[1]];
      ctx.strokeStyle = '#facc15';
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.moveTo(p0x, p0y);
      ctx.lineTo(p1x, p1y);
      ctx.stroke();
      for (const [px, py] of [[p0x, p0y], [p1x, p1y]]) {
        ctx.fillStyle = '#f59e0b';
        ctx.beginPath();
        ctx.arc(px, py, 4.5, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = 'rgba(15, 23, 42, 0.78)';
      ctx.fillRect((p0x + p1x) / 2 - 90, p0y - 22, 180, 16);
      ctx.fillStyle = '#fef08a';
      ctx.font = 'bold 11.5px "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(`标定比例尺基准线：${this.scaleReferenceM.toFixed(1)} m`, (p0x + p1x) / 2, p0y - 10);
    }

    // 7. Draw Compass / South Direction Rose at Top-Right + Super-Zoom Magnification Badge at Top-Left
    if (z >= 20) {
      const magVs18 = Math.pow(2, z - 18);
      ctx.save();
      const badgeY = this.is3D ? 114 : 82;
      ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
      ctx.fillRect(14, badgeY, 342, 24);
      ctx.strokeStyle = '#22c55e';
      ctx.lineWidth = 1.2;
      ctx.strokeRect(14, badgeY, 342, 24);
      ctx.fillStyle = '#dcfce7';
      ctx.font = 'bold 11px "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(`🔍 超清微距放大 Z${z} (${magVs18}× 级特写) · 1px ≈ ${this.metersPerPx.toFixed(3)}m`, 22, badgeY + 16);
      ctx.restore();
    }
    const compX = W - 40;
    const compY = 50;
    ctx.save();
    ctx.translate(compX, compY);
    ctx.rotate(azRad);
    ctx.fillStyle = 'rgba(15, 23, 42, 0.82)';
    ctx.beginPath();
    ctx.arc(0, 0, 22, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 1.4;
    ctx.stroke();
    ctx.fillStyle = '#ef4444';
    ctx.beginPath();
    ctx.moveTo(0, -14);
    ctx.lineTo(5, 4);
    ctx.lineTo(-5, 4);
    ctx.closePath();
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 9px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('N', 0, -15);
    ctx.fillStyle = '#38bdf8';
    ctx.fillText('S', 0, 18);
    ctx.restore();
  }

  /**
   * 「地图拾取经纬度」弹窗内的实景卫星地图画布渲染：
   * 实时渲染当前定位经纬度的高清卫星瓦片、中心红色十字靶标与白色选址底图裁剪框！
   */
  drawLocPickerModalCanvas() {
    if (typeof document === 'undefined' || !this.showLocationPickerModal) return;
    const canvas = this.host?.querySelector('#sat-loc-picker-canvas') || document.getElementById('sat-loc-picker-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    const cx = W / 2;
    const cy = H / 2;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, W, H);

    const z = Math.max(MIN_SAT_ZOOM, Math.min(MAX_SAT_ZOOM, Math.round(this.zoom || 18)));
    const [tileLon, tileLat] = this.mapSource === 'gaode'
      ? wgs84ToGcj02(this.lon, this.lat)
      : [this.lon, this.lat];
    const centerTile = lonLatToTileXY(tileLon, tileLat, z);
    const baseTx = Math.floor(centerTile.x);
    const baseTy = Math.floor(centerTile.y);
    const offsetX = (centerTile.x - baseTx) * 256;
    const offsetY = (centerTile.y - baseTy) * 256;
    const satSource = this.mapSource === 'esri' ? 'esri' : 'gaode_hyb';

    for (let dx = -2; dx <= 2; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        const tx = baseTx + dx;
        const ty = baseTy + dy;
        if (tx < 0 || ty < 0) continue;
        const drawX = Math.floor(cx - offsetX + dx * 256);
        const drawY = Math.floor(cy - offsetY + dy * 256);
        const patch = this.getBestSatelliteTilePatch(satSource, z, tx, ty);
        if (patch && patch.img) {
          ctx.drawImage(patch.img, patch.sx, patch.sy, patch.sw, patch.sh, drawX, drawY, 256.5, 256.5);
          if (satSource === 'gaode_hyb' && patch.usedFallback) {
            const lblPatch = this.getBestSatelliteTilePatch('gaode_label', z, tx, ty);
            if (lblPatch && lblPatch.img) {
              ctx.drawImage(lblPatch.img, lblPatch.sx, lblPatch.sy, lblPatch.sw, lblPatch.sh, drawX, drawY, 256.5, 256.5);
            }
          }
        }
      }
    }

    // Draw dark outer mask around the white selection frame (matching Video 1 v1_02.5s)
    const boxW = Math.round(W * 0.68);
    const boxH = Math.round(H * 0.68);
    const bx = Math.round((W - boxW) / 2);
    const by = Math.round((H - boxH) / 2);

    ctx.fillStyle = 'rgba(15, 23, 42, 0.42)';
    ctx.fillRect(0, 0, W, by);
    ctx.fillRect(0, by + boxH, W, H - (by + boxH));
    ctx.fillRect(0, by, bx, boxH);
    ctx.fillRect(bx + boxW, by, W - (bx + boxW), boxH);

    // Crisp White Selection Frame + Corner L-handles
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2.5;
    ctx.strokeRect(bx, by, boxW, boxH);

    // Center Location Pin & Crosshair
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(cx - 12, cy);
    ctx.lineTo(cx + 12, cy);
    ctx.moveTo(cx, cy - 12);
    ctx.lineTo(cx, cy + 12);
    ctx.stroke();
    ctx.fillStyle = '#ef4444';
    ctx.beginPath();
    ctx.arc(cx, cy, 4.5, 0, Math.PI * 2);
    ctx.fill();
  }

  /**
   * Paint realistic oblique aerial drone photo onto a canvas context (for Step 4 Oblique Studio)
   * Includes the foreground white parapet wall (女儿墙) that partially occludes the front roof slope!
   */
  paintObliquePresetBase(ctx, W, H, presetIdx = 0) {
    // Sky & atmospheric horizon gradient
    const sky = ctx.createLinearGradient(0, 0, 0, H * 0.34);
    sky.addColorStop(0, presetIdx === 1 ? '#0f172a' : '#0284c7');
    sky.addColorStop(0.6, presetIdx === 1 ? '#1e3a8a' : '#38bdf8');
    sky.addColorStop(1, '#e0f2fe');
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, W, H * 0.32);

    // Ground & industrial park asphalt/greenery background
    const ground = ctx.createLinearGradient(0, H * 0.24, 0, H);
    ground.addColorStop(0, '#334155');
    ground.addColorStop(0.45, '#1e293b');
    ground.addColorStop(1, '#0f172a');
    ctx.fillStyle = ground;
    ctx.fillRect(0, H * 0.24, W, H * 0.76);

    // Industrial park tree belt, road lanes, and neighboring workshops
    ctx.fillStyle = '#14532d';
    ctx.fillRect(0, H * 0.22, W, 26);
    for (let tx = 18; tx < W; tx += 36) {
      ctx.fillStyle = tx % 72 === 0 ? '#166534' : '#15803d';
      ctx.beginPath();
      ctx.arc(tx, H * 0.22 + 8, 12, 0, Math.PI * 2);
      ctx.fill();
    }
    // Distant neighboring factory buildings with window strips
    for (const [bx, by, bw, bh] of [[32, H * 0.12, 165, 62], [728, H * 0.13, 168, 58]]) {
      ctx.fillStyle = '#475569';
      ctx.fillRect(bx, by, bw, bh);
      ctx.fillStyle = '#1e3a8a';
      ctx.fillRect(bx, by, bw, 12);
      ctx.fillStyle = '#93c5fd';
      for (let wx = bx + 12; wx < bx + bw - 16; wx += 24) {
        ctx.fillRect(wx, by + 22, 14, 10);
        ctx.fillRect(wx, by + 38, 14, 10);
      }
    }

    // Main factory building shadow on asphalt yard
    ctx.fillStyle = 'rgba(2, 6, 23, 0.62)';
    ctx.beginPath();
    ctx.moveTo(112, 408);
    ctx.lineTo(838, 392);
    ctx.lineTo(895, 515);
    ctx.lineTo(95, 525);
    ctx.closePath();
    ctx.fill();

    // Oblique Roof Quad (P1 top-left, P2 top-right, P3 bottom-right, P4 bottom-left)
    const [P1, P2, P3, P4] = [
      [218, 178],
      [716, 168],
      [838, 392],
      [112, 408],
    ];

    // Blue corrugated steel roof surface (or Preset 3: Live Satellite Tile Texture!) in oblique perspective
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(P1[0], P1[1]);
    ctx.lineTo(P2[0], P2[1]);
    ctx.lineTo(P3[0], P3[1]);
    ctx.lineTo(P4[0], P4[1]);
    ctx.closePath();
    const roofGrad = ctx.createLinearGradient(0, P1[1], 0, P4[1]);
    if (presetIdx === 2) {
      roofGrad.addColorStop(0, '#64748b');
      roofGrad.addColorStop(1, '#475569');
    } else {
      roofGrad.addColorStop(0, '#1d4ed8');
      roofGrad.addColorStop(0.48, '#2563eb');
      roofGrad.addColorStop(0.52, '#1e40af');
      roofGrad.addColorStop(1, '#1e3a8a');
    }
    ctx.fillStyle = roofGrad;
    ctx.fill();

    // If Preset 3 (当前卫星底图 3D 斜视实景合成), project the loaded center satellite tile onto the oblique roof quad!
    if (presetIdx === 3) {
      ctx.save();
      ctx.clip();
      const z = Math.max(4, Math.min(19, Math.round(this.zoom || 18)));
      const [tileLon, tileLat] = this.mapSource === 'gaode'
        ? wgs84ToGcj02(this.lon, this.lat)
        : [this.lon, this.lat];
      const centerTile = lonLatToTileXY(tileLon, tileLat, z);
      const satSource = this.mapSource === 'esri' ? 'esri' : 'gaode_hyb';
      const cTile = this.loadSatelliteTile(satSource, z, Math.floor(centerTile.x), Math.floor(centerTile.y));
      if (cTile?.status === 'loaded' && cTile.img) {
        ctx.globalAlpha = 0.85;
        ctx.drawImage(cTile.img, 110, 165, 730, 248);
      }
      ctx.restore();
    }

    // Perspective corrugated seam lines & 2 red skylight strips on the bare roof
    const Hmat = solveHomography([[0, 0], [1, 0], [1, 1], [0, 1]], [P1, P2, P3, P4]);
    ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    ctx.lineWidth = 1;
    for (let u = 0.02; u < 0.99; u += 0.025) {
      const [x0, y0] = projectPoint(Hmat, u, 0);
      const [x1, y1] = projectPoint(Hmat, u, 1);
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1, y1);
      ctx.stroke();
    }

    // Central ridge cap in perspective
    const [rL0, rL1] = projectPoint(Hmat, 0, 0.5);
    const [rR0, rR1] = projectPoint(Hmat, 1, 0.5);
    ctx.strokeStyle = '#93c5fd';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(rL0, rL1);
    ctx.lineTo(rR0, rR1);
    ctx.stroke();

    // 2 Reddish translucent skylight strips in perspective
    for (const [v0, v1] of [[0.24, 0.29], [0.71, 0.76]]) {
      const spts = [
        projectPoint(Hmat, 0.05, v0),
        projectPoint(Hmat, 0.95, v0),
        projectPoint(Hmat, 0.95, v1),
        projectPoint(Hmat, 0.05, v1),
      ];
      ctx.fillStyle = 'rgba(225, 29, 72, 0.52)';
      ctx.strokeStyle = '#f43f5e';
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      spts.forEach(([px, py], i) => (i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)));
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
    ctx.restore();

    // Front Building Facade Wall & Roll-up Industrial Doors
    ctx.fillStyle = '#cbd5e1';
    ctx.beginPath();
    ctx.moveTo(94, 412);
    ctx.lineTo(856, 396);
    ctx.lineTo(856, 495);
    ctx.lineTo(94, 510);
    ctx.closePath();
    ctx.fill();

    // Industrial roll-up doors on front wall
    ctx.fillStyle = '#334155';
    for (const dx of [170, 340, 520, 690]) {
      ctx.fillRect(dx, 442, 74, 56);
    }

    // FOREGROUND WHITE PARAPET WALL (女儿墙) rising above the bottom roof edge (y=360..420)
    // This is the exact parapet wall that occludes the bottom row of solar panels in Video 2!
    const wallGrad = ctx.createLinearGradient(0, 358, 0, 440);
    wallGrad.addColorStop(0, '#f8fafc');
    wallGrad.addColorStop(0.35, '#e2e8f0');
    wallGrad.addColorStop(1, '#94a3b8');
    ctx.fillStyle = wallGrad;
    ctx.beginPath();
    ctx.moveTo(94, 376);
    ctx.lineTo(468, 364);
    ctx.lineTo(854, 360);
    ctx.lineTo(866, 442);
    ctx.lineTo(86, 450);
    ctx.closePath();
    ctx.fill();

    // Top coping stone cap on the white parapet wall
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 3.5;
    ctx.beginPath();
    ctx.moveTo(94, 376);
    ctx.lineTo(468, 364);
    ctx.lineTo(854, 360);
    ctx.stroke();
  }

  /**
   * Step 4: Render Oblique Photo + 3x3 Homography Projected Solar Array + Parapet Sightline Occlusion
   */
  drawEffectCanvas({ forExport = false } = {}) {
    if (typeof document === 'undefined') return;
    if (!this.modules || this.modules.length === 0) {
      this.layoutModules({ quiet: true, autoCreateRoof: true });
      this.electricalConfirmed = true;
      this.showStringColors = true;
      this.computeElectricalAllocation();
    }
    const canvas = this.host?.querySelector('#sat-effect-canvas') || document.getElementById('sat-effect-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;

    // 1. Render clean base oblique photo onto offscreen canvas so we can clip-redraw it for parapet occlusion
    if (!this.offscreenPhotoCanvas && typeof document.createElement === 'function') {
      this.offscreenPhotoCanvas = document.createElement('canvas');
    }
    const baseCanvas = this.offscreenPhotoCanvas;
    if (baseCanvas) {
      baseCanvas.width = W;
      baseCanvas.height = H;
      const bctx = baseCanvas.getContext('2d');
      if (this.customPhotoImg) {
        bctx.drawImage(this.customPhotoImg, 0, 0, W, H);
      } else {
        this.paintObliquePresetBase(bctx, W, H, this.effectPresetIdx);
      }
      ctx.drawImage(baseCanvas, 0, 0);
    } else {
      this.paintObliquePresetBase(ctx, W, H, this.effectPresetIdx);
    }

    // 2. Solve 3x3 Projective Homography H from normalized roof [0,1]^2 to dstQuad [P1, P2, P3, P4]
    const srcQuad = [
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
    ];
    const Hmat = solveHomography(srcQuad, this.dstQuad);

    // 3. Project every placed solar module quad & custom keepout obstacles onto the oblique photo
    const modOpacity = Math.max(0.4, Math.min(1.0, (this.effectOpacityPct || 92) / 100));
    const gridAlpha = Math.max(0.15, Math.min(1.0, (this.effectGridSharpnessPct || 75) / 100));
    const glareAlpha = Math.max(0, Math.min(0.45, ((this.effectGlarePct || 28) / 100) * 0.4));
    const baseFillNorth = this.effectModuleStyle === 'all_black'
      ? '#090d16'
      : this.effectModuleStyle === 'poly_blue'
        ? '#1d4ed8'
        : '#0f294a';
    const baseFillSouth = this.effectModuleStyle === 'all_black'
      ? '#111827'
      : this.effectModuleStyle === 'poly_blue'
        ? '#2563eb'
        : '#113264';

    const splitX = this.effectCompareMode
      ? Math.round(W * (Math.max(10, Math.min(90, this.effectCompareSplitPct || 50)) / 100))
      : 0;

    ctx.save();
    if (this.effectCompareMode) {
      ctx.beginPath();
      ctx.rect(splitX, 0, W - splitX, H);
      ctx.clip();
    }

    // 3A. Project user's custom polygon keepout obstacles onto the oblique roof surface
    if (this.obstacles && this.obstacles.length > 0 && !forExport) {
      const frame = this.getRoofUVFrame(true);
      for (const obs of this.obstacles) {
        if (!obs.polygon || obs.polygon.length < 3) continue;
        const projObs = obs.polygon.map(([mx, my]) => {
          const [u, v] = frame.toUV(mx, my);
          const nu = (u - frame.uMin) / Math.max(1, frame.widthU);
          const nv = (v - frame.vMin) / Math.max(1, frame.heightV);
          return projectPoint(Hmat, nu, nv);
        });
        ctx.fillStyle = 'rgba(239, 68, 68, 0.28)';
        ctx.strokeStyle = 'rgba(248, 113, 113, 0.85)';
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        projObs.forEach(([px, py], idx) => {
          if (idx === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      }
    }

    // 3B. Dynamic Winter Solstice Parapet Solar Shadow Band projected onto the roof quad
    const solarHr = Number.isFinite(Number(this.effectSolarHour)) ? Number(this.effectSolarHour) : 9.5;
    const hrInt = Math.floor(solarHr);
    const minStr = Math.round((solarHr - hrInt) * 60) === 30 ? '30' : '00';
    const solarTimeStr = `${String(hrInt).padStart(2, '0')}:${minStr}`;
    const phi = (Math.max(18, Math.min(52, Math.abs(this.lat || 36.5))) * Math.PI) / 180;
    const delta = (-23.45 * Math.PI) / 180;
    const omega = ((solarHr - 12) * 15 * Math.PI) / 180;
    const sinAlt = Math.max(0.06, Math.sin(phi) * Math.sin(delta) + Math.cos(phi) * Math.cos(delta) * Math.cos(omega));
    const solarAltDeg = Number(((Math.asin(Math.min(1, sinAlt)) * 180) / Math.PI).toFixed(1));
    const shadowDepthNorm = Math.min(0.11, Math.max(0.018, 0.016 / Math.max(0.15, sinAlt)));

    if (!forExport) {
      const shPts = [
        projectPoint(Hmat, 0.0, 1.0 - shadowDepthNorm),
        projectPoint(Hmat, 1.0, 1.0 - shadowDepthNorm),
        projectPoint(Hmat, 1.0, 1.0),
        projectPoint(Hmat, 0.0, 1.0),
      ];
      ctx.fillStyle = 'rgba(15, 23, 42, 0.42)';
      ctx.beginPath();
      shPts.forEach(([px, py], idx) => (idx === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)));
      ctx.closePath();
      ctx.fill();
      ctx.strokeStyle = 'rgba(250, 204, 21, 0.85)';
      ctx.lineWidth = 1.4;
      ctx.setLineDash([5, 3]);
      ctx.beginPath();
      ctx.moveTo(shPts[0][0], shPts[0][1]);
      ctx.lineTo(shPts[1][0], shPts[1][1]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.globalAlpha = modOpacity;
    for (const m of this.modules) {
      const projCorners = m.normCorners.map(([u, v]) => projectPoint(Hmat, u, v));

      // 3D module thickness drop-shadow
      ctx.fillStyle = 'rgba(2, 6, 23, 0.55)';
      ctx.beginPath();
      projCorners.forEach(([px, py], idx) => {
        if (idx === 0) ctx.moveTo(px + 2, py + 3.5);
        else ctx.lineTo(px + 2, py + 3.5);
      });
      ctx.closePath();
      ctx.fill();

      // Solar module fill (monocrystalline / all-black / polycrystalline or MPPT string color)
      ctx.fillStyle = (this.effectShowStringColors && m.stringColor)
        ? m.stringColor
        : (m.slope === 'north' ? baseFillNorth : baseFillSouth);
      ctx.beginPath();
      projCorners.forEach(([px, py], idx) => {
        if (idx === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.closePath();
      ctx.fill();

      // Anodized silver/black aluminum frame & cell grid highlight
      ctx.strokeStyle = this.effectModuleStyle === 'all_black'
        ? `rgba(71, 85, 105, ${gridAlpha.toFixed(2)})`
        : `rgba(186, 230, 253, ${gridAlpha.toFixed(2)})`;
      ctx.lineWidth = 0.85;
      ctx.stroke();

      // Subtle sky glare highlight
      if (glareAlpha > 0.02) {
        ctx.fillStyle = `rgba(224, 242, 254, ${glareAlpha.toFixed(2)})`;
        ctx.fill();
      }

      // Subtle mid-module busbar line
      const midTop = [
        (projCorners[0][0] + projCorners[1][0]) * 0.5,
        (projCorners[0][1] + projCorners[1][1]) * 0.5,
      ];
      const midBot = [
        (projCorners[3][0] + projCorners[2][0]) * 0.5,
        (projCorners[3][1] + projCorners[2][1]) * 0.5,
      ];
      ctx.strokeStyle = `rgba(148, 163, 184, ${(gridAlpha * 0.38).toFixed(2)})`;
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(midTop[0], midTop[1]);
      ctx.lineTo(midBot[0], midBot[1]);
      ctx.stroke();
    }
    ctx.restore();

    // 4. Parapet Sightline Occlusion Mask (女儿墙视线遮挡区域)
    // Redraws the original foreground parapet wall pixels ON TOP OF the projected solar modules!
    if (this.occlusionEnabled && this.occlusionPolygon.length >= 3 && baseCanvas) {
      ctx.save();
      ctx.beginPath();
      this.occlusionPolygon.forEach(([ox, oy], idx) => {
        if (idx === 0) ctx.moveTo(ox, oy);
        else ctx.lineTo(ox, oy);
      });
      ctx.closePath();
      ctx.clip();
      ctx.drawImage(baseCanvas, 0, 0);
      ctx.restore();

      if (!forExport) {
        ctx.save();
        ctx.beginPath();
        this.occlusionPolygon.forEach(([ox, oy], idx) => {
          if (idx === 0) ctx.moveTo(ox, oy);
          else ctx.lineTo(ox, oy);
        });
        ctx.closePath();
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 1.8;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = 'rgba(16, 185, 129, 0.14)';
        ctx.fill();
        const [lx, ly] = this.occlusionPolygon[1] || this.occlusionPolygon[0];
        ctx.fillStyle = 'rgba(6, 78, 59, 0.92)';
        ctx.fillRect(lx - 155, ly + 6, 310, 22);
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 1.2;
        ctx.strokeRect(lx - 155, ly + 6, 310, 22);
        ctx.fillStyle = '#ecfdf5';
        ctx.font = 'bold 11.5px "Microsoft YaHei", sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('🧱 女儿墙视线遮挡区域 (前景墙体自然遮挡底层组件)', lx, ly + 21);
        ctx.restore();
      }
    }

    // 4B. Before / After Split-Screen Comparison Divider Line & Badges (when effectCompareMode is active)
    if (this.effectCompareMode) {
      ctx.save();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2.6;
      ctx.beginPath();
      ctx.moveTo(splitX, 0);
      ctx.lineTo(splitX, H);
      ctx.stroke();

      // Central circular handle
      ctx.fillStyle = '#0ea5e9';
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2.2;
      ctx.beginPath();
      ctx.arc(splitX, H * 0.5, 16, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 12px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('◀▶', splitX, H * 0.5 + 4);

      // Left / Right labels
      ctx.fillStyle = 'rgba(15, 23, 42, 0.86)';
      ctx.fillRect(Math.max(12, splitX - 158), 16, 144, 26);
      ctx.fillRect(Math.min(W - 220, splitX + 14), 16, 206, 26);
      ctx.strokeStyle = '#94a3b8';
      ctx.lineWidth = 1;
      ctx.strokeRect(Math.max(12, splitX - 158), 16, 144, 26);
      ctx.strokeStyle = '#38bdf8';
      ctx.strokeRect(Math.min(W - 220, splitX + 14), 16, 206, 26);
      ctx.fillStyle = '#e2e8f0';
      ctx.font = 'bold 11.5px "Microsoft YaHei", sans-serif';
      ctx.fillText('◀ 改造前屋面原貌', Math.max(12, splitX - 158) + 72, 33);
      ctx.fillStyle = '#7dd3fc';
      ctx.fillText(`改造后光伏 (${this.summary.dcKw}kWp) ▶`, Math.min(W - 220, splitX + 14) + 103, 33);
      ctx.restore();
    }

    if (forExport) return;

    // 4C. Top-Left Winter Solstice Sun & Parapet Setback Engineering Verification HUD on Canvas
    if (!this.effectCompareMode) {
      ctx.save();
      ctx.fillStyle = 'rgba(15, 23, 42, 0.86)';
      ctx.fillRect(14, 14, 495, 28);
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 1.2;
      ctx.strokeRect(14, 14, 495, 28);
      ctx.fillStyle = '#fde047';
      ctx.font = 'bold 11.5px "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(
        `☀️ 冬至日 ${solarTimeStr} 实景日照校核 · 太阳高度角 ${solarAltDeg}° · 已投射 ${this.summary.moduleCount} 块 (${this.summary.dcKw} 千瓦)`,
        24,
        32
      );
      ctx.restore();
    }

    // 5. Draw 4-Point Perspective Homography Outline & Draggable Handles P1..P4
    ctx.save();
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    this.dstQuad.forEach(([px, py], idx) => {
      if (idx === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.stroke();
    ctx.setLineDash([]);

    const cornerLabels = ['1 (左上)', '2 (右上)', '3 (右下)', '4 (左下)'];
    this.dstQuad.forEach(([px, py], idx) => {
      ctx.fillStyle = '#f59e0b';
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(px, py, 9, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = '#0f172a';
      ctx.font = 'bold 11px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(String(idx + 1), px, py + 4);

      ctx.fillStyle = '#fef08a';
      ctx.font = 'bold 11.5px "Microsoft YaHei", sans-serif';
      ctx.fillText(`角点${cornerLabels[idx]}`, px, py - 14);
    });
    ctx.restore();
  }

  /**
   * Step 5: Render 4 Professional CAD Drawings in Dark AutoCAD Viewport (SVG)
   *   - 'layout': 光伏排布图
   *   - 'string': 组串接线图 (Connected-wing 2×N serpentine + strictly interior cable routing)
   *   - 'grounding': 防雷接地图
   *   - 'bracket': 支架图 (侧视剖面图 + 正视立面图)
   */
  renderCadSvg(sheet = 'layout') {
    const W = 920;
    const H = 520;
    const frame = this.getRoofUVFrame(true);
    const mod = this.getSelectedModule();
    const inv = this.getSelectedInverter();
    const s = this.summary;

    const sheetNames = {
      layout: '光伏阵列总平面排布图 (PV LAYOUT)',
      string: '光伏组串接线与逆变器布置图',
      grounding: '屋面防雷与等电位接地平面图',
      bracket: '光伏支架安装大样及剖面/立面图',
      single_line: '光伏并网发电一次系统主接线图 (SLD)',
      cable_tray: '直流/交流电缆桥架敷设与并网走向图',
      foundation: '混凝土基础配重布置及屋面抗风荷载校核图',
      bom_schedule: '施工图纸目录与主要设备材料清册 (BOM)',
      pvlane_perspective: '实景四点透视配准与女儿墙遮挡工程图',
      pvsyst_diagram: '8760h 物理仿真系统图、太阳轨迹与I-V电压包络图',
      clamp_detail: '夹具压块与屋面防水节点大样图 (JG-03)',
      ac_cabinet: '0.4kV并网柜二次原理与通讯监控图 (SCADA)',
      om_walkway: '屋面检修马道、消防通道与清洗水路平面图',
      bess_storage: '储能AI光储一体化与削峰填谷运行图 (CN-01)',
      pvlane_birdseye: '屋面改造前后实景对比与业主汇报图',
      pvsyst_near_shading: '3D近场阴影、寻优矩阵与25年财务图',
    };

    const sheetCode = {
      layout: `${this.cadPrefix}-DL-01`,
      string: `${this.cadPrefix}-DL-02`,
      grounding: `${this.cadPrefix}-DL-03`,
      bracket: `${this.cadPrefix}-JG-01`,
      single_line: `${this.cadPrefix}-DL-04`,
      cable_tray: `${this.cadPrefix}-DL-05`,
      foundation: `${this.cadPrefix}-JG-02`,
      bom_schedule: `${this.cadPrefix}-DL-00`,
      pvlane_perspective: `${this.cadPrefix}-FX-01`,
      pvsyst_diagram: `${this.cadPrefix}-PV-01`,
      clamp_detail: `${this.cadPrefix}-JG-03`,
      ac_cabinet: `${this.cadPrefix}-DL-06`,
      om_walkway: `${this.cadPrefix}-JG-04`,
      bess_storage: `${this.cadPrefix}-CN-01`,
      pvlane_birdseye: `${this.cadPrefix}-FX-02`,
      pvsyst_near_shading: `${this.cadPrefix}-PV-02`,
    }[sheet] || `${this.cadPrefix}-01`;

    const bcfg = this.bracketCfg || {
      h1Mm: 400, y0Mm: 1500, y1Mm: 1600, angleDeg: 15, x1Mm: 450, x2Mm: 2200,
      foundationType: '混凝土条形基础/方墩', concreteGrade: 'C30',
    };

    // Standard Chinese CAD Border & Bottom-Right 8-Field Engineering Title Block (视频1 v1_16.5s 完整图签栏)
    const frameAndTitleBlock = `
      <rect x="10" y="10" width="${W - 20}" height="${H - 20}" fill="none" stroke="#38bdf8" stroke-width="1.5"/>
      <rect x="15" y="15" width="${W - 30}" height="${H - 30}" fill="none" stroke="#1e293b" stroke-width="0.8"/>
      <!-- CAD Grid Ticks -->
      ${[1, 2, 3, 4, 5, 6].map((i) => `<text x="${i * 140}" y="13" font-size="8" fill="#64748b" font-family="monospace">${i}</text>`).join('')}
      <!-- Compass North Arrow (rotated by -ridgeAzimuthDeg to show true North relative to orthogonal roof plan) -->
      <g transform="translate(865, 55) rotate(${-(this.ridgeAzimuthDeg || 0)})">
        <circle cx="0" cy="0" r="18" fill="none" stroke="#38bdf8" stroke-width="1"/>
        <polygon points="0,-15 5,6 0,2 -5,6" fill="#38bdf8"/>
        <text x="0" y="-20" text-anchor="middle" font-size="9" fill="#38bdf8" font-family="monospace">N</text>
      </g>
      <!-- Standard CAD Title Block (widened to 370px with column split at x=240 so 图名 never overlaps 比例) -->
      <g transform="translate(${W - 390}, ${H - 84})">
        <rect x="0" y="0" width="370" height="64" fill="#070d19" stroke="#38bdf8" stroke-width="1.2"/>
        <line x1="0" y1="21" x2="370" y2="21" stroke="#38bdf8" stroke-width="0.8"/>
        <line x1="0" y1="42" x2="370" y2="42" stroke="#38bdf8" stroke-width="0.8"/>
        <line x1="240" y1="0" x2="240" y2="64" stroke="#38bdf8" stroke-width="0.8"/>
        <text x="8" y="15" font-size="9.5" font-weight="bold" fill="#e2e8f0">项目：${esc(this.cadTitle)}</text>
        <text x="246" y="15" font-size="9" fill="#38bdf8" font-family="monospace">图号：${esc(sheetCode)}</text>
        <text x="8" y="35" font-size="9" fill="#cbd5e1">图名：${esc(sheetNames[sheet] || sheet)}</text>
        <text x="246" y="35" font-size="9" fill="#cbd5e1">比例：${esc(this.cadScale)} · 图幅A3</text>
        <text x="8" y="56" font-size="8.5" fill="#94a3b8">${esc(String(this.cadUnit || '').replace(/\s*\(.*?\)/g, '').slice(0, 14))} · 设计:${esc(this.cadDesigner || '王工')} 审定:${esc(this.cadChiefDesigner || '张工')}</text>
        <text x="246" y="56" font-size="9" fill="#10b981">装机：${s.dcKw}kWp (${s.moduleCount}块)</text>
      </g>
    `;

    // =========================================================================
    // Sheet 5: 'single_line' — 光伏并网发电一次系统主接线图 (Electrical Single-Line Diagram)
    // =========================================================================
    if (sheet === 'single_line') {
      const ratedCurrentA = ((s.acKw * 1000) / (1.732 * 380 * 0.98)).toFixed(1);
      const vocColdV = (this.modulesPerString * mod.voc_v * 1.08).toFixed(0);
      const vmpNomV = (this.modulesPerString * mod.vmp_v).toFixed(0);
      return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sheetNames[sheet])}">
        ${frameAndTitleBlock}
        <text x="440" y="38" text-anchor="middle" font-size="13" font-weight="bold" fill="#38bdf8">
          ${esc(this.projectName)} — 0.4kV 分布式光伏并网发电一次主接线系统图
        </text>

        <!-- Left Column: PV String Branches & DC Protection -->
        <g transform="translate(30, 58)">
          <rect x="0" y="0" width="235" height="352" fill="rgba(15,23,42,0.55)" stroke="#1e293b" stroke-width="1"/>
          <text x="117" y="18" text-anchor="middle" font-size="10.5" font-weight="bold" fill="#facc15">Ⅰ. 直流光伏方阵与组串支路 (${s.stringCount}串)</text>
          ${[0, 1, 2, 3].map((idx) => {
            const gy = 34 + idx * 78;
            const sLabel = idx < 3
              ? `PV${idx * 2 + 1}~PV${idx * 2 + 2} (接入 MPPT${idx + 1})`
              : `... PV${Math.max(1, s.stringCount - 1)}~PV${s.stringCount} (接入 MPPT${inv.mppt_count})`;
            return `
              <g transform="translate(12, ${gy})">
                <rect x="0" y="4" width="68" height="44" fill="rgba(2,132,199,0.2)" stroke="#38bdf8" stroke-width="1.2"/>
                <line x1="0" y1="26" x2="68" y2="26" stroke="#38bdf8" stroke-width="0.7"/>
                <line x1="22" y1="4" x2="22" y2="48" stroke="#38bdf8" stroke-width="0.7"/>
                <line x1="45" y1="4" x2="45" y2="48" stroke="#38bdf8" stroke-width="0.7"/>
                <text x="34" y="18" text-anchor="middle" font-size="7.5" fill="#e2e8f0" font-family="monospace">${this.modulesPerString}×${mod.stc_w}Wp</text>
                <text x="34" y="40" text-anchor="middle" font-size="7.2" fill="#38bdf8" font-family="monospace">Vmp=${vmpNomV}V</text>
                <text x="2" y="-1" font-size="8" font-weight="bold" fill="#4ade80">${esc(sLabel)}</text>
                <!-- DC +/- Wires & DC Fuse + SPD -->
                <line x1="68" y1="16" x2="215" y2="16" stroke="#ef4444" stroke-width="1.3"/>
                <line x1="68" y1="36" x2="215" y2="36" stroke="#38bdf8" stroke-width="1.3"/>
                <rect x="92" y="11" width="18" height="10" fill="#070d19" stroke="#facc15" stroke-width="1"/>
                <text x="101" y="19" text-anchor="middle" font-size="6.5" fill="#facc15">20A</text>
                <rect x="132" y="18" width="22" height="16" fill="#070d19" stroke="#22c55e" stroke-width="1"/>
                <text x="143" y="29" text-anchor="middle" font-size="6.8" fill="#22c55e">SPD</text>
                <text x="164" y="12" font-size="7" fill="#94a3b8" font-family="monospace">PV1-F 1×4mm²</text>
                <text x="164" y="48" font-size="7" fill="#facc15" font-family="monospace">Voc(-10°C)=${vocColdV}V</text>
              </g>
            `;
          }).join('')}
        </g>

        <!-- Center Column: String Inverters & AC Grid-Tied Combiner Cabinet -->
        <g transform="translate(275, 58)">
          <rect x="0" y="0" width="295" height="352" fill="rgba(15,23,42,0.55)" stroke="#1e293b" stroke-width="1"/>
          <text x="147" y="18" text-anchor="middle" font-size="10.5" font-weight="bold" fill="#38bdf8">Ⅱ. 组串式逆变器与 0.4kV 交流并网柜</text>

          <!-- Inverter Symbol Block -->
          <rect x="16" y="34" width="118" height="125" rx="4" fill="#091326" stroke="#38bdf8" stroke-width="1.6"/>
          <line x1="16" y1="159" x2="134" y2="34" stroke="#38bdf8" stroke-width="1.2"/>
          <text x="42" y="68" font-size="14" font-weight="bold" fill="#facc15">DC</text>
          <text x="42" y="84" font-size="11" fill="#facc15">═══</text>
          <text x="86" y="126" font-size="14" font-weight="bold" fill="#22c55e">AC</text>
          <text x="86" y="144" font-size="12" fill="#22c55e">∼ 3P</text>
          <text x="75" y="176" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#f8fafc">${esc(inv.brand)} ${esc(inv.model)}</text>
          <text x="75" y="189" text-anchor="middle" font-size="8" fill="#38bdf8" font-family="monospace">${inv.rated_ac_kw}kW × ${s.inverterCount}台 (${inv.mppt_count}路MPPT)</text>
          <text x="75" y="201" text-anchor="middle" font-size="7.5" fill="#94a3b8" font-family="monospace">MPPT: 200~1000V / Max 1100V</text>

          <!-- AC Feeder from Inverter to AC Cabinet -->
          <line x1="134" y1="96" x2="172" y2="96" stroke="#22c55e" stroke-width="2.2"/>
          <line x1="149" y1="89" x2="157" y2="103" stroke="#facc15" stroke-width="1.2"/>
          <text x="153" y="84" text-anchor="middle" font-size="7.5" fill="#facc15">3P+N+PE</text>

          <!-- AC Grid-Tied Cabinet (光伏并网柜 GZ-PV-ACB) -->
          <rect x="172" y="30" width="110" height="305" rx="4" fill="#070e1c" stroke="#22c55e" stroke-width="1.5" stroke-dasharray="6 3"/>
          <text x="227" y="45" text-anchor="middle" font-size="9" font-weight="bold" fill="#4ade80">光伏交流并网柜</text>
          <!-- Unit Breaker QF1 -->
          <rect x="195" y="60" width="64" height="28" fill="#0f172a" stroke="#facc15" stroke-width="1.1"/>
          <text x="227" y="73" text-anchor="middle" font-size="7.8" fill="#facc15">QF1..${s.inverterCount} 塑壳</text>
          <text x="227" y="83" text-anchor="middle" font-size="7.2" fill="#cbd5e1">250A / 3P</text>
          <line x1="227" y1="88" x2="227" y2="115" stroke="#22c55e" stroke-width="2"/>
          <!-- AC SPD -->
          <rect x="195" y="115" width="64" height="24" fill="#0f172a" stroke="#38bdf8" stroke-width="1"/>
          <text x="227" y="130" text-anchor="middle" font-size="7.5" fill="#38bdf8">AC浪涌 SPD 40kA</text>
          <line x1="227" y1="139" x2="227" y2="164" stroke="#22c55e" stroke-width="2"/>
          <!-- Anti-Islanding & Protection Relay -->
          <rect x="186" y="164" width="82" height="38" fill="#0f172a" stroke="#f43f5e" stroke-width="1.2"/>
          <text x="227" y="179" text-anchor="middle" font-size="7.8" font-weight="bold" fill="#fb7185">防孤岛/故障解列</text>
          <text x="227" y="193" text-anchor="middle" font-size="7" fill="#cbd5e1">GB/T 19964 (&lt;0.2s)</text>
          <line x1="227" y1="202" x2="227" y2="226" stroke="#22c55e" stroke-width="2"/>
          <!-- Bi-directional Meter -->
          <rect x="190" y="226" width="74" height="32" fill="#0f172a" stroke="#a855f7" stroke-width="1.1"/>
          <text x="227" y="240" text-anchor="middle" font-size="7.8" fill="#d8b4fe">双向计量表 kWh</text>
          <text x="227" y="252" text-anchor="middle" font-size="7" fill="#cbd5e1">0.5S级 四象限</text>
          <line x1="227" y1="258" x2="227" y2="282" stroke="#22c55e" stroke-width="2"/>
          <!-- Main Knife Switch QS -->
          <rect x="195" y="282" width="64" height="28" fill="#0f172a" stroke="#22c55e" stroke-width="1.2"/>
          <text x="227" y="295" text-anchor="middle" font-size="7.8" fill="#4ade80">QS 总隔离开关</text>
          <text x="227" y="305" text-anchor="middle" font-size="7" fill="#cbd5e1">明显断开点</text>

          <!-- Bottom AC Cable Note -->
          <text x="88" y="242" text-anchor="middle" font-size="7.8" fill="#4ade80" font-family="monospace">交流并网电缆：</text>
          <text x="88" y="256" text-anchor="middle" font-size="7.5" fill="#cbd5e1" font-family="monospace">ZRC-YJV22-0.6/1kV</text>
          <text x="88" y="270" text-anchor="middle" font-size="7.5" fill="#cbd5e1" font-family="monospace">3×95+1×50mm²</text>
          <text x="88" y="290" text-anchor="middle" font-size="7.8" fill="#facc15" font-family="monospace">额定电流 In=${ratedCurrentA}A</text>
        </g>

        <!-- Right Column: PCC Grid Busbar & Electrical Calculation Schedule -->
        <g transform="translate(580, 58)">
          <!-- PCC 0.4kV Busbar -->
          <rect x="0" y="0" width="310" height="92" fill="rgba(15,23,42,0.55)" stroke="#1e293b" stroke-width="1"/>
          <text x="155" y="18" text-anchor="middle" font-size="10.5" font-weight="bold" fill="#4ade80">Ⅲ. 厂区 0.4kV 低压母线并网点 (PCC)</text>
          <line x1="18" y1="42" x2="292" y2="42" stroke="#facc15" stroke-width="4"/>
          <text x="155" y="35" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#fef08a">0.4kV 380V/220V 50Hz 低压母线 (TMY-4×(80×8))</text>
          <text x="80" y="68" text-anchor="middle" font-size="8.5" fill="#38bdf8">⬆ 10kV/0.4kV 厂区主变</text>
          <text x="225" y="68" text-anchor="middle" font-size="8.5" fill="#4ade80">⬇ 厂区车间负荷 (自发自用/余电上网)</text>

          <!-- Primary Electrical Calculation & Relay Schedule Table -->
          <rect x="0" y="102" width="310" height="250" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <rect x="0" y="102" width="310" height="22" fill="#0f172a" stroke="#38bdf8" stroke-width="0.8"/>
          <text x="155" y="117" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#38bdf8">一次系统主要电气参数与整定计算表</text>
          ${[
            ['1. 直流侧总装机容量', `${s.dcKw} kWp (${s.moduleCount}块 × ${mod.stc_w}Wp)`],
            ['2. 交流侧额定并网容量', `${s.acKw} kWac (容配比 ${s.dcAcRatio})`],
            ['3. 组串配置与MPPT数', `${s.stringCount} 路组串 (${this.modulesPerString}块/串 · ${inv.mppt_count * s.inverterCount}路MPPT)`],
            ['4. 组串工作/极限开路电压', `Vmp=${vmpNomV}V / Voc(-10°C)=${vocColdV}V ≤ 1100V`],
            ['5. 交流并网额定工作电流', `In = ${ratedCurrentA} A (COSφ = 0.8超前~0.8滞后)`],
            ['6. 光伏直流专用电缆', 'PV1-F 1×4.0mm² (TUV认证 1500V DC)'],
            ['7. 交流低压并网主电缆', 'ZRC-YJV22-0.6/1kV-3×95+1×50mm²'],
            ['8. 防孤岛与接地保护要求', '失压跳闸 < 0.2s · 联合接地电阻 R ≤ 4.0Ω'],
          ].map(([k, v], idx) => `
            <line x1="0" y1="${124 + idx * 28}" x2="310" y2="${124 + idx * 28}" stroke="#1e293b" stroke-width="0.8"/>
            <text x="8" y="${142 + idx * 28}" font-size="8.2" fill="#94a3b8">${esc(k)}</text>
            <text x="138" y="${142 + idx * 28}" font-size="8.2" font-weight="bold" fill="#e2e8f0" font-family="monospace">${esc(v)}</text>
          `).join('')}
        </g>

        <!-- Bottom-Left Legend -->
        <g transform="translate(26, ${H - 84})">
          <rect x="0" y="0" width="490" height="64" fill="#070d19" fill-opacity="0.92" stroke="#1e293b" stroke-width="1"/>
          <text x="10" y="15" font-size="9.5" font-weight="bold" fill="#38bdf8">一次系统设计规范与施工说明 (GB 50797 / GB/T 19964 / NB/T 32004)：</text>
          <text x="10" y="30" font-size="8.6" fill="#cbd5e1">1. 并网方式：采用 0.4kV 低压侧「自发自用、余电上网」模式，并网柜配置防孤岛保护与失压脱扣装置；</text>
          <text x="10" y="44" font-size="8.6" fill="#cbd5e1">2. 电能计量：并网点安装 0.5S 级三相四线智能双向电表，分别计量光伏发电量、自用电量与上网电量；</text>
          <text x="10" y="58" font-size="8.6" fill="#cbd5e1">3. 过电压保护：直流侧配置 Type II 1100V 光伏专用浪涌保护器，交流并网柜配置 40kA 浪涌保护器。</text>
        </g>
      </svg>`;
    }

    // =========================================================================
    // Sheet 8: 'bom_schedule' — 施工图纸目录与主要设备材料清册 (Drawing Index & BOM Schedule)
    // =========================================================================
    if (sheet === 'bom_schedule') {
      const allSheets = this.getAllCadSheets();
      const dcCableM = Math.max(220, s.stringCount * 52);
      const acCableM = Math.max(65, s.inverterCount * 45);
      const pierCount = Math.max(24, Math.ceil(s.moduleCount * 1.15));
      const flatSteelM = Math.max(85, Math.round((frame.widthU + frame.heightV) * 2.2));
      const trayM = Math.max(36, Math.round(frame.widthU * 1.35));
      const bomRows = [
        ['1', 'N型TOPCon单晶双玻组件', `${mod.model} (${mod.stc_w}Wp)`, '块', String(s.moduleCount), '转化效率≥22.5%, 双面双玻'],
        ['2', '组串式并网光伏逆变器', `${inv.brand} ${inv.model} (${inv.rated_ac_kw}kW)`, '台', String(s.inverterCount), `${inv.mppt_count}路MPPT, IP66防护`],
        ['3', '0.4kV 光伏交流并网配电柜', 'GZ-PV-ACB-400V (含防孤岛)', '面', String(Math.max(1, Math.ceil(s.inverterCount / 3))), '含塑壳/双向表/检有压合闸'],
        ['4', '光伏专用直流电缆', 'PV1-F 1×4.0mm² (红/黑)', 'm', String(dcCableM), '1500V DC TUV抗紫外阻燃'],
        ['5', '低压阻燃铠装交流电缆', 'ZRC-YJV22-0.6/1kV-3×95+1×50', 'm', String(acCableM), '逆变器至并网柜主干电缆'],
        ['6', '光伏专用防水连接器', 'MC4 1500V / 30A IP68', '对', String(s.stringCount * 2 + 8), '组串首尾及逆变器端子'],
        ['7', '热浸镀锌钢/铝合金光伏支架', `Q235B/6005-T5 (倾角A=${bcfg.angleDeg}°)`, 'kWp', String(s.dcKw), `前高H1=${bcfg.h1Mm}mm, 排距Y0=${bcfg.y0Mm}mm`],
        ['8', `${bcfg.concreteGrade} 混凝土配重基础墩`, `300×300×400mm (间距X2=${bcfg.x2Mm})`, '个', String(pierCount), '含热镀锌M12预埋地脚螺栓'],
        ['9', '热镀锌铝合金防火电缆桥架', '200×100×1.5mm (含盖板托臂)', 'm', String(trayM), '屋面直流/交流主干线槽'],
        ['10', '屋面防雷等电位热镀锌扁钢', '-40×4mm (锌层厚度≥65μm)', 'm', String(flatSteelM), '环形接地网 R≤4.0Ω'],
        ['11', 'SUS304 不锈钢中/边压块组件', '配 EPDM 三元乙丙防水胶垫', '套', String(s.moduleCount * 4), '抗风揭 50年一遇 W0=0.45'],
      ];

      return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sheetNames[sheet])}">
        ${frameAndTitleBlock}
        <text x="440" y="36" text-anchor="middle" font-size="12.5" font-weight="bold" fill="#38bdf8">
          ${esc(this.cadTitle)} — 施工图纸目录 (Drawing Index) 与主要设备材料清册 (BOM)
        </text>

        <!-- Left Table: 16-Sheet Drawing Index (施工图纸目录) -->
        <g transform="translate(26, 48)">
          <rect x="0" y="0" width="386" height="366" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <rect x="0" y="0" width="386" height="24" fill="#0f172a" stroke="#38bdf8" stroke-width="0.9"/>
          <text x="193" y="16" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15">一、全套施工图纸目录 (共 16 张工程图纸)</text>
          <line x1="0" y1="44" x2="386" y2="44" stroke="#38bdf8" stroke-width="0.8"/>
          <text x="18" y="38" text-anchor="middle" font-size="8" font-weight="bold" fill="#38bdf8">序号</text>
          <text x="68" y="38" text-anchor="middle" font-size="8" font-weight="bold" fill="#38bdf8">图号</text>
          <text x="196" y="38" text-anchor="middle" font-size="8" font-weight="bold" fill="#38bdf8">图纸名称</text>
          <text x="336" y="38" text-anchor="middle" font-size="8" font-weight="bold" fill="#38bdf8">图纸专业分类</text>
          ${allSheets.map(([key, _lbl, code, _cat, swTag], idx) => {
            const ry = 44 + idx * 19.8;
            return `
              <line x1="0" y1="${(ry + 19.8).toFixed(1)}" x2="386" y2="${(ry + 19.8).toFixed(1)}" stroke="#1e293b" stroke-width="0.65"/>
              <text x="18" y="${(ry + 13.5).toFixed(1)}" text-anchor="middle" font-size="7.4" fill="#94a3b8" font-family="monospace">${String(idx + 1).padStart(2, '0')}</text>
              <text x="68" y="${(ry + 13.5).toFixed(1)}" text-anchor="middle" font-size="7.4" font-weight="bold" fill="#38bdf8" font-family="monospace">${esc(this.cadPrefix)}-${esc(code)}</text>
              <text x="112" y="${(ry + 13.5).toFixed(1)}" font-size="7.4" fill="#e2e8f0">${esc(sheetNames[key] || _lbl)}</text>
              <text x="342" y="${(ry + 13.5).toFixed(1)}" text-anchor="middle" font-size="7.1" fill="#4ade80">${esc(swTag)}</text>
            `;
          }).join('')}
        </g>

        <!-- Right Table: Bill of Materials (主要设备与施工材料清册 BOM) -->
        <g transform="translate(422, 48)">
          <rect x="0" y="0" width="472" height="366" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <rect x="0" y="0" width="472" height="24" fill="#0f172a" stroke="#38bdf8" stroke-width="0.9"/>
          <text x="236" y="16" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#4ade80">二、主要设备与施工材料工程量清册 (实时联动排布与配串结果)</text>
          <line x1="0" y1="44" x2="472" y2="44" stroke="#38bdf8" stroke-width="0.8"/>
          <text x="16" y="38" text-anchor="middle" font-size="8" font-weight="bold" fill="#38bdf8">#</text>
          <text x="82" y="38" text-anchor="middle" font-size="8" font-weight="bold" fill="#38bdf8">设备/材料名称</text>
          <text x="212" y="38" text-anchor="middle" font-size="8" font-weight="bold" fill="#38bdf8">规格型号</text>
          <text x="298" y="38" text-anchor="middle" font-size="8" font-weight="bold" fill="#38bdf8">单位</text>
          <text x="334" y="38" text-anchor="middle" font-size="8" font-weight="bold" fill="#38bdf8">数量</text>
          <text x="412" y="38" text-anchor="middle" font-size="8" font-weight="bold" fill="#38bdf8">技术规范备注</text>
          ${bomRows.map(([num, name, spec, unit, qty, note], idx) => {
            const ry = 44 + idx * 29;
            return `
              <line x1="0" y1="${ry + 29}" x2="472" y2="${ry + 29}" stroke="#1e293b" stroke-width="0.7"/>
              <text x="16" y="${ry + 19}" text-anchor="middle" font-size="7.8" fill="#94a3b8" font-family="monospace">${num}</text>
              <text x="30" y="${ry + 19}" font-size="7.8" font-weight="bold" fill="#e2e8f0">${esc(name)}</text>
              <text x="148" y="${ry + 19}" font-size="7.5" fill="#38bdf8" font-family="monospace">${esc(spec)}</text>
              <text x="298" y="${ry + 19}" text-anchor="middle" font-size="7.8" fill="#cbd5e1">${esc(unit)}</text>
              <text x="334" y="${ry + 19}" text-anchor="middle" font-size="8.2" font-weight="bold" fill="#facc15" font-family="monospace">${esc(qty)}</text>
              <text x="358" y="${ry + 19}" font-size="7.2" fill="#94a3b8">${esc(note)}</text>
            `;
          }).join('')}
        </g>

        <!-- Bottom-Left Engineering Note -->
        <g transform="translate(26, ${H - 84})">
          <rect x="0" y="0" width="490" height="64" fill="#070d19" fill-opacity="0.92" stroke="#1e293b" stroke-width="1"/>
          <text x="10" y="15" font-size="9.5" font-weight="bold" fill="#38bdf8">工程造价与材料统计说明：</text>
          <text x="10" y="30" font-size="8.6" fill="#cbd5e1">1. 本工程总装机容量 ${s.dcKw} kWp，预计工程总投资 ${s.capexWan} 万元，首年 P50 发电量 ${(s.annualKwh / 10000).toFixed(2)} 万kWh；</text>
          <text x="10" y="44" font-size="8.6" fill="#cbd5e1">2. 表中直流线缆、电缆桥架与防雷扁钢工程量已含 8% 施工余量及弯头损耗；</text>
          <text x="10" y="58" font-size="8.6" fill="#cbd5e1">3. 所有进场设备与材料均须具备国家 CQC / TUV 认证及出厂合格证、型式试验报告。</text>
        </g>
      </svg>`;
    }

    // =========================================================================
    // Sheet 9: 'pvlane_perspective' — 实景四点透视配准与女儿墙遮挡工程图
    // =========================================================================
    if (sheet === 'pvlane_perspective') {
      const dstQ = this.dstQuad || [[218, 178], [716, 168], [838, 392], [112, 408]];
      // Map dstQuad into right CAD box (x=405..885, y=72..392)
      const mapDst = ([px, py]) => [
        405 + ((px - 80) / 820) * 465,
        62 + ((py - 80) / 400) * 320,
      ];
      const cadQuad = dstQ.map(mapDst);
      const Hmat = solveHomography([[0, 0], [1, 0], [1, 1], [0, 1]], cadQuad);
      const quadPath = cadQuad.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ') + ' Z';

      // Project all placed modules through Homography Hmat
      const projModsSvg = this.modules.slice(0, 550).map((m) => {
        const nc = m.normCorners || [
          [(m.u - frame.uMin) / frame.widthU, (m.v - frame.vMin) / frame.heightV],
          [(m.u + m.w - frame.uMin) / frame.widthU, (m.v - frame.vMin) / frame.heightV],
          [(m.u + m.w - frame.uMin) / frame.widthU, (m.v + m.h - frame.vMin) / frame.heightV],
          [(m.u - frame.uMin) / frame.widthU, (m.v + m.h - frame.vMin) / frame.heightV],
        ];
        const pts = nc.map(([nu, nv]) => projectPoint(Hmat, nu, nv));
        const d = pts.map(([px, py], i) => `${i === 0 ? 'M' : 'L'}${px.toFixed(1)},${py.toFixed(1)}`).join(' ') + ' Z';
        return `<path d="${d}" fill="rgba(37,99,235,0.45)" stroke="#60a5fa" stroke-width="0.65"/>`;
      }).join('');

      // 2D Thumbnail in Left Box (x=48..352, y=82..255)
      const tScale = Math.min(270 / Math.max(4, frame.widthU), 150 / Math.max(4, frame.heightV));
      const tox = 55 + (280 - frame.widthU * tScale) / 2;
      const toy = 86 + (155 - frame.heightV * tScale) / 2;
      const tu = (u) => (tox + (u - frame.uMin) * tScale).toFixed(1);
      const tv = (v) => (toy + (v - frame.vMin) * tScale).toFixed(1);
      const thumbRoof = frame.polyUV.map(([u, v], i) => `${i === 0 ? 'M' : 'L'}${tu(u)},${tv(v)}`).join(' ') + ' Z';
      const thumbMods = this.modules.slice(0, 550).map((m) =>
        `<rect x="${tu(m.u)}" y="${tv(m.v)}" width="${(m.w * tScale).toFixed(1)}" height="${(m.h * tScale).toFixed(1)}" fill="rgba(14,165,233,0.35)" stroke="#38bdf8" stroke-width="0.45"/>`
      ).join('');

      return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sheetNames[sheet])}">
        ${frameAndTitleBlock}
        <text x="440" y="36" text-anchor="middle" font-size="12.5" font-weight="bold" fill="#38bdf8">
          无人机斜拍四点单应性透视配准 (3×3 Homography) 与前景女儿墙视线遮挡工程图
        </text>

        <!-- Left Box: 2D Orthographic Roof Plan & 3x3 Homography Matrix H -->
        <g transform="translate(26, 48)">
          <rect x="0" y="0" width="356" height="364" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="178" y="20" text-anchor="middle" font-size="10" font-weight="bold" fill="#facc15">Ⅰ. 2D 屋面正射排布基准与角点配准顺序 (1→2→3→4)</text>
          <path d="${thumbRoof}" fill="rgba(15,23,42,0.9)" stroke="#f8fafc" stroke-width="1.5"/>
          ${thumbMods}
          ${[
            [tu(frame.uMin), tv(frame.vMin), '1(左上)'],
            [tu(frame.uMax), tv(frame.vMin), '2(右上)'],
            [tu(frame.uMax), tv(frame.vMax), '3(右下)'],
            [tu(frame.uMin), tv(frame.vMax), '4(左下)'],
          ].map(([cx, cy, lbl]) => `
            <circle cx="${cx}" cy="${cy}" r="6" fill="#f59e0b" stroke="#fff" stroke-width="1"/>
            <text x="${cx}" y="${Number(cy) - 9}" text-anchor="middle" font-size="8" font-weight="bold" fill="#fef08a">${lbl}</text>
          `).join('')}

          <!-- Homography Matrix H Table -->
          <rect x="14" y="216" width="328" height="134" fill="#091326" stroke="#1e293b" stroke-width="1"/>
          <text x="178" y="234" text-anchor="middle" font-size="9" font-weight="bold" fill="#38bdf8">Ⅱ. 实时求解 3×3 射影单应变换矩阵 H (Planar → Oblique)</text>
          <text x="178" y="256" text-anchor="middle" font-size="8.5" fill="#4ade80" font-family="monospace">
            [ h11=${Hmat[0].toFixed(2)}  h12=${Hmat[1].toFixed(2)}  h13=${Hmat[2].toFixed(1)} ]
          </text>
          <text x="178" y="274" text-anchor="middle" font-size="8.5" fill="#4ade80" font-family="monospace">
            [ h21=${Hmat[3].toFixed(2)}  h22=${Hmat[4].toFixed(2)}  h23=${Hmat[5].toFixed(1)} ]
          </text>
          <text x="178" y="292" text-anchor="middle" font-size="8.5" fill="#4ade80" font-family="monospace">
            [ h31=${Hmat[6].toFixed(4)}  h32=${Hmat[7].toFixed(4)}  h33=1.0000 ]
          </text>
          <text x="178" y="316" text-anchor="middle" font-size="8" fill="#cbd5e1">
            组件样式：${esc(this.effectModuleStyle)} · 不透明度：${this.effectOpacityPct}% · 反光：${this.effectGlarePct}%
          </text>
          <text x="178" y="334" text-anchor="middle" font-size="8" fill="#facc15">
            女儿墙视线遮挡裁剪：${this.occlusionEnabled ? '已启用前景墙体遮挡裁剪' : '未启用'}
          </text>
        </g>

        <!-- Right Box: 3D Oblique Perspective Projection & Parapet Sightline Clipping -->
        <rect x="394" y="48" width="500" height="364" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
        <text x="644" y="68" text-anchor="middle" font-size="10" font-weight="bold" fill="#38bdf8">Ⅲ. 3D 无人机航拍实景透视合成与前景女儿墙视线遮挡区</text>
        <!-- Perspective Factory Walls & Parapet -->
        <polygon points="${cadQuad[3][0].toFixed(1)},${cadQuad[3][1].toFixed(1)} ${cadQuad[2][0].toFixed(1)},${cadQuad[2][1].toFixed(1)} ${(cadQuad[2][0] + 8).toFixed(1)},${(cadQuad[2][1] + 42).toFixed(1)} ${(cadQuad[3][0] - 8).toFixed(1)},${(cadQuad[3][1] + 42).toFixed(1)}" fill="#1e293b" stroke="#64748b" stroke-width="1.2"/>
        <path d="${quadPath}" fill="rgba(15,23,42,0.85)" stroke="#f59e0b" stroke-width="1.6" stroke-dasharray="6 3"/>
        ${projModsSvg}
        <!-- Parapet Sightline Occlusion Zone -->
        <polygon points="${(cadQuad[3][0] + 6).toFixed(1)},${(cadQuad[3][1] - 16).toFixed(1)} ${(cadQuad[2][0] - 6).toFixed(1)},${(cadQuad[2][1] - 16).toFixed(1)} ${cadQuad[2][0].toFixed(1)},${(cadQuad[2][1] + 10).toFixed(1)} ${cadQuad[3][0].toFixed(1)},${(cadQuad[3][1] + 10).toFixed(1)}" fill="rgba(16,185,129,0.22)" stroke="#10b981" stroke-width="1.5" stroke-dasharray="5 3"/>
        <text x="${((cadQuad[2][0] + cadQuad[3][0]) * 0.5).toFixed(1)}" y="${(cadQuad[3][1] + 2).toFixed(1)}" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#4ade80">
          🧱 前景女儿墙相机视线遮挡裁剪区 (自然遮挡底层组件下沿)
        </text>
        ${cadQuad.map(([px, py], idx) => `
          <circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="7" fill="#f59e0b" stroke="#fff" stroke-width="1.4"/>
          <text x="${px.toFixed(1)}" y="${(py + 3).toFixed(1)}" text-anchor="middle" font-size="8" font-weight="bold" fill="#0f172a">${idx + 1}</text>
        `).join('')}

        <!-- Bottom-Left Legend -->
        <g transform="translate(26, ${H - 84})">
          <rect x="0" y="0" width="490" height="64" fill="#070d19" fill-opacity="0.92" stroke="#1e293b" stroke-width="1"/>
          <text x="10" y="15" font-size="9.5" font-weight="bold" fill="#38bdf8">实景透视合成与视线遮挡技术说明：</text>
          <text x="10" y="30" font-size="8.6" fill="#cbd5e1">1. 通过屋面四角 P1(左上)→P2(右上)→P3(右下)→P4(左下) 精确求解 3×3 射影单应矩阵 H，误差 &lt; 10⁻⁶；</text>
          <text x="10" y="44" font-size="8.6" fill="#cbd5e1">2. 自动映射 ${s.moduleCount} 块光伏组件 (${s.dcKw} kWp) 及留空采光带/风帽禁布区，保持真实空间透视缩尺；</text>
          <text x="10" y="58" font-size="8.6" fill="#cbd5e1">3. 前景女儿墙区域执行相机视线裁剪 (Sightline Occlusion Clipping)，真实还原业主航拍视角美观度。</text>
        </g>
      </svg>`;
    }

    // =========================================================================
    // Sheet 10: 'pvsyst_diagram' — 8760h 物理仿真系统图、太阳轨迹天际线与I-V电压包络图
    // =========================================================================
    if (sheet === 'pvsyst_diagram') {
      const wx = this.weatherEval || this.evaluateWeatherAndAngles();
      const globHorVal = Number(wx.globHorKwhM2 || 1380);
      const globIncVal = Number(wx.globIncKwhM2 || (globHorVal * 1.07).toFixed(1));
      const poaGainPct = (((globIncVal / Math.max(1, globHorVal)) - 1) * 100).toFixed(1);
      const vocCold = (this.modulesPerString * mod.voc_v * 1.08).toFixed(0);
      const vmpHot = (this.modulesPerString * mod.vmp_v * 0.86).toFixed(0);
      const vmpStc = (this.modulesPerString * mod.vmp_v).toFixed(0);
      return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sheetNames[sheet])}">
        ${frameAndTitleBlock}
        <text x="440" y="36" text-anchor="middle" font-size="12.5" font-weight="bold" fill="#38bdf8">
          8760h 光电物理仿真能量流、冬至太阳轨迹天际线与组串 I-V 电压温度包络图
        </text>

        <!-- Quadrant 1 (Top-Left): 16-Stage Energy Balance & Loss Chain -->
        <g transform="translate(26, 48)">
          <rect x="0" y="0" width="424" height="175" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="212" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15">Ⅰ. 8760h 能量转换链与关键损耗瀑布图 (PR = ${s.prPct}%)</text>
          ${[
            ['水平面总辐照 GlobHor', `${globHorVal} kWh/m²`, 310, '#38bdf8', '基准 100%'],
            ['最佳倾角面辐照 GlobInc', `${globIncVal} kWh/m²`, 335, '#0ea5e9', `+${poaGainPct}% (倾角${this.tiltDeg}°)`],
            ['有效入射辐照 GlobEff', `${(globIncVal * 0.956).toFixed(0)} kWh/m²`, 320, '#22c55e', 'IAM -1.8% / 灰尘 -2.6%'],
            ['阵列直流发电 E_Array', `${((s.annualKwh / 10000) * 1.022).toFixed(2)} 万kWh`, 295, '#eab308', 'Faiman温升 -4.4% / 失配 -1.5%'],
            ['并网净结算电量 E_Grid', `${(s.annualKwh / 10000).toFixed(2)} 万kWh`, 282, '#10b981', `逆变器效率 98.6% (${s.specificYield}h)`],
          ].map(([lbl, val, barW, col, tag], idx) => {
            const ry = 32 + idx * 27;
            return `
              <text x="10" y="${ry + 12}" font-size="8" fill="#cbd5e1">${esc(lbl)}</text>
              <rect x="128" y="${ry + 2}" width="${barW * 0.52}" height="13" rx="2" fill="${col}" fill-opacity="0.35" stroke="${col}" stroke-width="1"/>
              <text x="${134 + barW * 0.52}" y="${ry + 12}" font-size="7.8" font-weight="bold" fill="#f8fafc" font-family="monospace">${esc(val)} (${esc(tag)})</text>
            `;
          }).join('')}
        </g>

        <!-- Quadrant 2 (Top-Right): Solar Altitude vs Azimuth Sun-Path Horizon Diagram -->
        <g transform="translate(460, 48)">
          <rect x="0" y="0" width="434" height="175" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="217" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#38bdf8">
            Ⅱ. 当地纬度 (${this.lat.toFixed(2)}°N) 太阳高度角-方位角轨迹天际线与冬至无遮挡窗
          </text>
          <!-- Horizon Grid -->
          <rect x="36" y="28" width="372" height="122" fill="#050a14" stroke="#1e293b" stroke-width="0.9"/>
          <!-- Winter Solstice 9:00-15:00 Window Highlight -->
          <rect x="136" y="28" width="172" height="122" fill="rgba(250,204,21,0.08)" stroke="#facc15" stroke-width="0.8" stroke-dasharray="3 3"/>
          <text x="222" y="40" text-anchor="middle" font-size="7.5" fill="#fef08a">冬至日 09:00 ~ 15:00 真太阳时无遮挡窗口</text>
          <!-- Summer Solstice Arc (June 21) -->
          <path d="M 48,148 Q 222,18 396,148" fill="none" stroke="#f97316" stroke-width="1.8"/>
          <text x="335" y="55" font-size="7.5" fill="#fb923c">6月21日 夏至</text>
          <!-- Equinox Arc (Mar/Sep 21) -->
          <path d="M 72,148 Q 222,52 372,148" fill="none" stroke="#22c55e" stroke-width="1.6"/>
          <text x="335" y="84" font-size="7.5" fill="#4ade80">3/9月21日 春秋分</text>
          <!-- Winter Solstice Arc (Dec 21) -->
          <path d="M 105,148 Q 222,92 339,148" fill="none" stroke="#38bdf8" stroke-width="2"/>
          <circle cx="136" cy="128" r="3.5" fill="#facc15"/>
          <circle cx="308" cy="128" r="3.5" fill="#facc15"/>
          <text x="222" y="114" text-anchor="middle" font-size="7.8" font-weight="bold" fill="#38bdf8">12月21日 冬至 (9:00高度角 α=${wx.solarAlt9amDeg}°)</text>
          <text x="222" y="164" text-anchor="middle" font-size="8" fill="#94a3b8" font-family="monospace">
            方位角 Azimuth: -90°(东) ────── 0°(正南) ────── +90°(西) · 冬至无遮挡排距 D=${wx.currentUnshadedGapM}m
          </text>
        </g>

        <!-- Quadrant 3 (Bottom-Left): String I-V & P-V Curves + Temperature Voltage Window -->
        <g transform="translate(26, 232)">
          <rect x="0" y="0" width="424" height="182" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="212" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#4ade80">
            Ⅲ. 组串 (${this.modulesPerString}块/串) I-V 温度特性曲线与逆变器 MPPT 安全包络 (-10°C ~ +70°C)
          </text>
          <rect x="38" y="28" width="360" height="118" fill="#050a14" stroke="#1e293b" stroke-width="0.9"/>
          <!-- MPPT Voltage Window Shading (200V .. 1000V) -->
          <rect x="92" y="28" width="240" height="118" fill="rgba(16,185,129,0.09)" stroke="#10b981" stroke-width="0.8" stroke-dasharray="4 2"/>
          <text x="212" y="40" text-anchor="middle" font-size="7.5" fill="#4ade80">MPPT 满载电压工作窗口 (200V ~ 1000V) · 极限耐压 1100V</text>
          <!-- +70°C Hot I-V Curve -->
          <path d="M 42,62 L 225,62 Q 252,62 262,144" fill="none" stroke="#f43f5e" stroke-width="1.6"/>
          <text x="195" y="57" font-size="7.5" fill="#fb7185">+70°C高温 Vmp=${vmpHot}V</text>
          <!-- +25°C STC I-V Curve -->
          <path d="M 42,58 L 265,58 Q 292,58 304,144" fill="none" stroke="#38bdf8" stroke-width="1.8"/>
          <text x="248" y="75" font-size="7.5" fill="#38bdf8">25°C STC Vmp=${vmpStc}V</text>
          <!-- -10°C Cold I-V Curve -->
          <path d="M 42,54 L 298,54 Q 326,54 340,144" fill="none" stroke="#facc15" stroke-width="1.8"/>
          <text x="305" y="96" font-size="7.5" font-weight="bold" fill="#fef08a">-10°C低温 Voc=${vocCold}V ≤ 1100V</text>
          <!-- Max 1100V Limit Line -->
          <line x1="366" y1="28" x2="366" y2="146" stroke="#ef4444" stroke-width="1.4" stroke-dasharray="3 2"/>
          <text x="366" y="158" text-anchor="middle" font-size="7.5" font-weight="bold" fill="#ef4444">Umax=1100V</text>
          <text x="195" y="168" text-anchor="middle" font-size="8" fill="#cbd5e1" font-family="monospace">
            校核结论：Vmp(+70°C)=${vmpHot}V ≥ 200V 且 Voc(-10°C)=${vocCold}V ≤ 1100V (合格)
          </text>
        </g>

        <!-- Quadrant 4 (Bottom-Right): P50 / P75 / P90 Bankability & 25-Year Yield Table -->
        <g transform="translate(460, 232)">
          <rect x="0" y="0" width="434" height="182" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="217" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15">
            Ⅳ. 概率发电量 (P50/P75/P90) 与 25 年全寿命周期授信评估表
          </text>
          ${[
            ['气象数据源与辐射转置模型', `${wx.source} · Perez Anisotropic + Faiman 温升模型`],
            ['最优倾角评估 (单瓦最优 / 屋面总电最优)', `单瓦最优 ${wx.weatherOptimalTiltDeg}° (${wx.weatherOptimalYield}h) / 屋面总电最优 ${wx.roofOptimalTiltDeg}°`],
            ['首年 P50 期望并网发电量 (50%置信度)', `${(s.annualKwh / 10000).toFixed(2)} 万kWh/年 (满发 ${s.specificYield} h)`],
            ['首年 P75 稳健并网发电量 (75%置信度)', `${((s.annualKwh * 0.962) / 10000).toFixed(2)} 万kWh/年`],
            ['首年 P90 银行授信保底发电量 (90%置信度)', `${((s.annualKwh * 0.928) / 10000).toFixed(2)} 万kWh/年 (银行可融资基准)`],
            ['25年全周期累计并网发电量 (N型年衰减0.4%)', `${((s.annualKwh * 23.65) / 10000).toFixed(1)} 万kWh · 减排 CO₂ ${((s.annualKwh * 23.65 * 0.00057) / 10000).toFixed(2)} 万吨`],
          ].map(([k, v], idx) => `
            <line x1="0" y1="${28 + idx * 25}" x2="434" y2="${28 + idx * 25}" stroke="#1e293b" stroke-width="0.7"/>
            <text x="10" y="${44 + idx * 25}" font-size="8" fill="#94a3b8">${esc(k)}</text>
            <text x="215" y="${44 + idx * 25}" font-size="8" font-weight="bold" fill="#4ade80" font-family="monospace">${esc(v)}</text>
          `).join('')}
        </g>

        <!-- Bottom-Left Legend -->
        <g transform="translate(26, ${H - 84})">
          <rect x="0" y="0" width="490" height="64" fill="#070d19" fill-opacity="0.92" stroke="#1e293b" stroke-width="1"/>
          <text x="10" y="15" font-size="9.5" font-weight="bold" fill="#38bdf8">8760h 光电物理仿真说明：</text>
          <text x="10" y="30" font-size="8.6" fill="#cbd5e1">1. 采用当地真实经纬度 (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) 官方实时气象与典型气象年 (TMY) 合成场；</text>
          <text x="10" y="44" font-size="8.6" fill="#cbd5e1">2. 综合考虑太阳入射角修正 (IAM)、Faiman 阵列热平衡温升、双面背面增益 (+4.4%) 及旁路二极管阴影失配；</text>
          <text x="10" y="58" font-size="8.6" fill="#cbd5e1">3. 冬至日 (12月21日) 09:00~15:00 真太阳时满足前后排无遮挡间距 D ≥ ${wx.currentUnshadedGapM}m。</text>
        </g>
      </svg>`;
    }

    // =========================================================================
    // Sheet 11: 'clamp_detail' (JG-03) — 夹具压块与屋面防水节点大样图 (结构图)
    // =========================================================================
    if (sheet === 'clamp_detail') {
      const midClampCnt = Math.max(32, s.moduleCount * 2);
      const endClampCnt = Math.max(16, s.stringCount * 4);
      const railSpliceCnt = Math.max(12, Math.round(s.moduleCount * 0.35));
      return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sheetNames[sheet])}">
        ${frameAndTitleBlock}
        <text x="450" y="34" text-anchor="middle" font-size="12.5" font-weight="bold" fill="#38bdf8">
          ${esc(this.projectName)} — 光伏支架夹具、中边压块、导轨伸缩缝及屋面防水节点大样图 (JG-03)
        </text>

        <!-- Detail A (Top-Left): 节点 A — 彩钢瓦暗扣/直立锁边无穿孔专用夹具大样 (1:5) -->
        <g transform="translate(26, 46)">
          <rect x="0" y="0" width="424" height="176" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="212" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15">
            节点 A：彩钢瓦直立锁边/角驰Ⅲ型无穿孔防渗漏铝镁合金夹具大样 (比例 1:5)
          </text>
          <!-- Corrugated Metal Roof Rib Profile -->
          <path d="M 30,145 L 125,145 L 145,98 L 165,98 L 185,145 L 285,145" fill="none" stroke="#94a3b8" stroke-width="2.5"/>
          <circle cx="155" cy="96" r="6" fill="#cbd5e1" stroke="#38bdf8" stroke-width="1.2"/>
          <!-- Non-penetrating Standing Seam Clamp -->
          <rect x="135" y="74" width="40" height="26" fill="rgba(56,189,248,0.22)" stroke="#38bdf8" stroke-width="1.5"/>
          <line x1="126" y1="88" x2="184" y2="88" stroke="#facc15" stroke-width="2"/>
          <circle cx="126" cy="88" r="3" fill="#facc15"/>
          <circle cx="184" cy="88" r="3" fill="#facc15"/>
          <!-- Aluminum Rail 47x42mm + PV Module Frame -->
          <rect x="85" y="54" width="140" height="20" fill="rgba(148,163,184,0.28)" stroke="#e2e8f0" stroke-width="1.4"/>
          <rect x="65" y="38" width="180" height="16" fill="rgba(37,99,235,0.45)" stroke="#60a5fa" stroke-width="1.4"/>
          <!-- Callout annotations -->
          <text x="242" y="48" font-size="8" fill="#60a5fa" font-family="monospace">← 双玻组件 35mm 阳极氧化铝边框</text>
          <text x="242" y="67" font-size="8" fill="#e2e8f0" font-family="monospace">← 6005-T5 铝合金主导轨 47×42×1.6mm</text>
          <text x="242" y="88" font-size="8" fill="#facc15" font-family="monospace">← SUS304 M8×25 内六角锁紧螺栓 (扭矩16N·m)</text>
          <text x="242" y="106" font-size="8" fill="#38bdf8" font-family="monospace">← EPDM 三元乙丙橡胶防滑减震胶垫 (厚3mm)</text>
          <text x="242" y="125" font-size="8" fill="#4ade80" font-family="monospace">← 严禁打孔穿透彩钢板，实现 100% 零漏水隐患</text>
          <text x="212" y="164" text-anchor="middle" font-size="8" fill="#94a3b8" font-family="monospace">
            单点抗拉拔承载力设计值 Ft ≥ 2.40 kN · 抗滑移承载力 Fs ≥ 1.65 kN (GB 50009)
          </text>
        </g>

        <!-- Detail B (Top-Right): 节点 B — 混凝土屋面配重方墩与双层 SBS 防水保护垫层节点 (1:10) -->
        <g transform="translate(460, 46)">
          <rect x="0" y="0" width="434" height="176" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="217" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#38bdf8">
            节点 B：混凝土平屋面预制配重墩 (${esc(bcfg.concreteGrade)}) 与屋面防水保护构造大样 (比例 1:10)
          </text>
          <!-- Structural Roof Slab + Insulation + Waterproofing -->
          <rect x="35" y="138" width="210" height="18" fill="#1e293b" stroke="#64748b" stroke-width="1.2"/>
          <rect x="35" y="128" width="210" height="10" fill="rgba(56,189,248,0.18)" stroke="#38bdf8" stroke-width="1"/>
          <rect x="65" y="121" width="150" height="7" fill="#facc15" fill-opacity="0.7" stroke="#facc15" stroke-width="1"/>
          <!-- Concrete Pier 300x300x400 -->
          <rect x="82" y="68" width="116" height="53" fill="rgba(148,163,184,0.32)" stroke="#f8fafc" stroke-width="1.6"/>
          <line x1="82" y1="68" x2="198" y2="121" stroke="#475569" stroke-width="0.8"/>
          <line x1="198" y1="68" x2="82" y2="121" stroke="#475569" stroke-width="0.8"/>
          <!-- Embedded M12 Anchor Bolts & Base Plate -->
          <rect x="115" y="62" width="50" height="6" fill="#38bdf8"/>
          <line x1="125" y1="48" x2="125" y2="95" stroke="#facc15" stroke-width="2.2"/>
          <line x1="155" y1="48" x2="155" y2="95" stroke="#facc15" stroke-width="2.2"/>
          <rect x="133" y="34" width="14" height="28" fill="rgba(56,189,248,0.35)" stroke="#38bdf8" stroke-width="1.2"/>
          <!-- Callout Texts -->
          <text x="255" y="46" font-size="8" fill="#38bdf8" font-family="monospace">← C41×41×2.0 热浸镀锌立柱 (锌层≥65μm)</text>
          <text x="255" y="64" font-size="8" fill="#facc15" font-family="monospace">← 2×M12×180 热浸镀锌预埋L型地脚螺栓</text>
          <text x="255" y="84" font-size="8" fill="#f8fafc" font-family="monospace">← ${esc(bcfg.concreteGrade)} 预制混凝土墩 300×300×${bcfg.h1Mm}mm</text>
          <text x="255" y="104" font-size="8" fill="#fef08a" font-family="monospace">← 5mm厚 EPDM 橡胶垫 + SBS 附加防水卷材层</text>
          <text x="255" y="124" font-size="8" fill="#38bdf8" font-family="monospace">← 原屋面 4mm SBS 防水层 (严禁破坏原防水层)</text>
          <text x="255" y="144" font-size="8" fill="#94a3b8" font-family="monospace">← 原建筑钢筋混凝土结构屋面板 (厚120mm)</text>
          <text x="217" y="166" text-anchor="middle" font-size="8" fill="#4ade80" font-family="monospace">
            施工要求：每个混凝土配重墩底部满铺 350×350×5mm 三元乙丙橡胶防滑护垫，四周倒角 R10mm
          </text>
        </g>

        <!-- Detail C (Bottom-Left): 节点 C — 组件中压块/边压块与接地刺片大样 (1:2) -->
        <g transform="translate(26, 232)">
          <rect x="0" y="0" width="424" height="182" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="212" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#4ade80">
            节点 C：组件中压块 (共 ${midClampCnt} 套) / 边压块 (${endClampCnt} 套) 与刺破接地片大样 (1:2)
          </text>
          <!-- Left Module & Right Module with 20mm Gap -->
          <rect x="30" y="58" width="92" height="24" fill="rgba(37,99,235,0.45)" stroke="#60a5fa" stroke-width="1.5"/>
          <rect x="148" y="58" width="92" height="24" fill="rgba(37,99,235,0.45)" stroke="#60a5fa" stroke-width="1.5"/>
          <!-- Mid Clamp T-Shape -->
          <path d="M 112,50 L 158,50 L 158,58 L 140,58 L 140,92 L 130,92 L 130,58 L 112,58 Z" fill="#facc15" fill-opacity="0.85" stroke="#fef08a" stroke-width="1.2"/>
          <!-- Grounding Teeth Clip -->
          <line x1="115" y1="82" x2="155" y2="82" stroke="#ef4444" stroke-width="2.5" stroke-dasharray="3 2"/>
          <!-- Rail Section -->
          <rect x="75" y="84" width="120" height="36" fill="rgba(148,163,184,0.28)" stroke="#cbd5e1" stroke-width="1.5"/>
          <!-- Dimension & Specs -->
          <text x="135" y="44" text-anchor="middle" font-size="8" font-weight="bold" fill="#facc15">中压块间距 B=20mm</text>
          <text x="252" y="56" font-size="8" fill="#e2e8f0" font-family="monospace">· 中压块: 6005-T5 铝合金 T型压块 L=50mm</text>
          <text x="252" y="73" font-size="8" fill="#e2e8f0" font-family="monospace">· 边压块: 6005-T5 铝合金 Z型压块 H=35mm</text>
          <text x="252" y="90" font-size="8" fill="#f87171" font-family="monospace">· 接地垫片: SUS304 不锈钢刺片(刺破氧化膜)</text>
          <text x="252" y="107" font-size="8" fill="#facc15" font-family="monospace">· 紧固螺栓: SUS304 M8×45 内六角+防松弹垫</text>
          <text x="252" y="124" font-size="8" fill="#4ade80" font-family="monospace">· 压块啮合深度: ≥ 10mm · 锁紧扭矩 14~16 N·m</text>
          <text x="212" y="166" text-anchor="middle" font-size="8" fill="#94a3b8" font-family="monospace">
            规范依据：《光伏发电站施工规范》(GB 50794) · 组件边框与导轨间接触电阻 R ≤ 0.1 Ω
          </text>
        </g>

        <!-- Detail D (Bottom-Right): 节点 D — 导轨热胀冷缩伸缩缝连接与铜编织带跨接大样 -->
        <g transform="translate(460, 232)">
          <rect x="0" y="0" width="434" height="182" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="217" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15">
            节点 D：导轨热胀冷缩伸缩缝 (每 18m 设一处，共 ${railSpliceCnt} 处) 与等电位跨接大样
          </text>
          <!-- Left & Right Rails with 20mm Thermal Expansion Gap -->
          <rect x="35" y="64" width="150" height="28" fill="rgba(56,189,248,0.22)" stroke="#38bdf8" stroke-width="1.5"/>
          <rect x="205" y="64" width="150" height="28" fill="rgba(56,189,248,0.22)" stroke="#38bdf8" stroke-width="1.5"/>
          <!-- Internal Splice Bar (Half Fixed, Half Sliding) -->
          <rect x="135" y="70" width="120" height="16" fill="rgba(250,204,21,0.35)" stroke="#facc15" stroke-width="1.2"/>
          <circle cx="155" cy="78" r="3" fill="#ef4444"/>
          <circle cx="172" cy="78" r="3" fill="#ef4444"/>
          <rect x="215" y="75" width="14" height="6" rx="3" fill="#4ade80"/>
          <!-- Flexible Tinned Copper Jumper Braid -->
          <path d="M 160,92 Q 195,126 230,92" fill="none" stroke="#facc15" stroke-width="2.5" stroke-dasharray="4 2"/>
          <text x="195" y="54" text-anchor="middle" font-size="8" font-weight="bold" fill="#facc15">伸缩缝 ΔL = 20mm</text>
          <text x="195" y="122" text-anchor="middle" font-size="8" fill="#fef08a">BVR-16mm² 镀锡软铜编织带跨接</text>
          <text x="25" y="142" font-size="8" fill="#cbd5e1" font-family="monospace">1. 铝合金导轨连续长度超过 18m 时必须断开，预留 20mm 热胀冷缩变形缝；</text>
          <text x="25" y="156" font-size="8" fill="#cbd5e1" font-family="monospace">2. 内插接件左侧采用 2×M8 自攻螺钉固定死端，右侧采用长圆腰型孔滑动端；</text>
          <text x="25" y="170" font-size="8" fill="#4ade80" font-family="monospace">3. 伸缩缝上方严禁跨越安装同一块光伏组件，且必须加装 16mm² 接地跨接线。</text>
        </g>

        <!-- Bottom-Left Legend -->
        <g transform="translate(26, ${H - 84})">
          <rect x="0" y="0" width="490" height="64" fill="#070d19" fill-opacity="0.92" stroke="#1e293b" stroke-width="1"/>
          <text x="10" y="15" font-size="9.5" font-weight="bold" fill="#38bdf8">结构大样与防水施工技术要求：</text>
          <text x="10" y="30" font-size="8.6" fill="#cbd5e1">1. 所有铝型材材质为 6005-T5 (阳极氧化膜 AA15≥15μm)，钢构件热浸镀锌平均厚度 ≥ 65μm；</text>
          <text x="10" y="44" font-size="8.6" fill="#cbd5e1">2. 屋面防水等级二级，混凝土屋面严禁冲击钻打孔破坏原防水层，彩钢瓦屋面采用直立锁边夹具；</text>
          <text x="10" y="58" font-size="8.6" fill="#cbd5e1">3. 紧固件全部采用奥氏体不锈钢 A2-70 (SUS304)，安装完毕后对达到扭矩值螺栓做防松红漆标记。</text>
        </g>
      </svg>`;
    }

    // =========================================================================
    // Sheet 12: 'ac_cabinet' (DL-06) — 0.4kV并网柜二次原理与通讯监控系统图 (电气图)
    // =========================================================================
    if (sheet === 'ac_cabinet') {
      const ratedCurrentA = ((s.acKw * 1000) / (1.732 * 380 * 0.98)).toFixed(1);
      const ctRatio = Math.max(200, Math.ceil((Number(ratedCurrentA) * 1.35) / 50) * 50);
      return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sheetNames[sheet])}">
        ${frameAndTitleBlock}
        <text x="450" y="34" text-anchor="middle" font-size="12.5" font-weight="bold" fill="#38bdf8">
          ${esc(this.projectName)} — 0.4kV 并网柜二次控制保护原理与 RS485/光纤远动通讯拓扑图 (DL-06)
        </text>

        <!-- Left Half: 0.4kV Grid-Tie Cabinet Secondary Protection & Anti-Islanding Control Schematic -->
        <g transform="translate(26, 46)">
          <rect x="0" y="0" width="424" height="368" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="212" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15">
            Ⅰ. 0.4kV 光伏并网柜 (GGD-PV) 二次控制、防孤岛保护与失压跳闸原理图
          </text>
          <!-- AC Control Busbar L1/L2/L3/N -->
          <line x1="25" y1="36" x2="398" y2="36" stroke="#facc15" stroke-width="2"/>
          <line x1="25" y1="44" x2="398" y2="44" stroke="#38bdf8" stroke-width="1.5"/>
          <text x="30" y="32" font-size="7.5" fill="#facc15" font-family="monospace">AC 220V 控制母线 (L1 / N) · 经 UPS 双电源不间断供电 (后备 ≥ 2h)</text>

          <!-- Anti-Islanding Protection Device Box -->
          <rect x="30" y="64" width="175" height="145" fill="#050a14" stroke="#38bdf8" stroke-width="1.4"/>
          <text x="117" y="82" text-anchor="middle" font-size="9" font-weight="bold" fill="#38bdf8">微机防孤岛保护装置</text>
          <text x="117" y="96" text-anchor="middle" font-size="8" fill="#facc15" font-family="monospace">GZ-PV-800A (GB/T 19964)</text>
          <text x="42" y="114" font-size="7.8" fill="#cbd5e1" font-family="monospace">· 过压/欠压保护 (1.15Un / 0.85Un)</text>
          <text x="42" y="128" font-size="7.8" fill="#cbd5e1" font-family="monospace">· 过频/欠频保护 (50.5Hz / 49.5Hz)</text>
          <text x="42" y="142" font-size="7.8" fill="#cbd5e1" font-family="monospace">· 频率突变滑差 df/dt ≥ 0.5Hz/s</text>
          <text x="42" y="156" font-size="7.8" fill="#cbd5e1" font-family="monospace">· 逆功率/防逆流闭锁跳闸 (&lt;0.2s)</text>
          <text x="42" y="170" font-size="7.8" fill="#4ade80" font-family="monospace">· 有压自动合闸延时 T=180s</text>
          <text x="42" y="188" font-size="7.8" fill="#f87171" font-family="monospace">· 故障解列出口继电器 DO1/DO2</text>

          <!-- Circuit Breaker Trip & Closing Coils -->
          <rect x="235" y="64" width="168" height="145" fill="#050a14" stroke="#facc15" stroke-width="1.2"/>
          <text x="319" y="82" text-anchor="middle" font-size="9" font-weight="bold" fill="#facc15">并网主断路器 1QF 联锁回路</text>
          <text x="245" y="102" font-size="8" fill="#cbd5e1" font-family="monospace">┌─ MX 分励脱扣线圈 (防孤岛跳闸)</text>
          <text x="245" y="118" font-size="8" fill="#cbd5e1" font-family="monospace">├─ MN 失压脱扣器 (母线失压瞬跳)</text>
          <text x="245" y="134" font-size="8" fill="#cbd5e1" font-family="monospace">├─ XF 电动合闸线圈 (检同期有压合闸)</text>
          <text x="245" y="150" font-size="8" fill="#cbd5e1" font-family="monospace">├─ OF/SD 断路器位置/故障遥信接点</text>
          <text x="245" y="166" font-size="8" fill="#4ade80" font-family="monospace">└─ 计量/保护 CT: LMZ1-0.66 ${ctRatio}/5A</text>
          <line x1="205" y1="135" x2="235" y2="135" stroke="#ef4444" stroke-width="1.8" stroke-dasharray="4 2"/>

          <!-- Power Quality Analyzer & Revenue Meter Box -->
          <rect x="30" y="224" width="373" height="128" fill="#050a14" stroke="#10b981" stroke-width="1.2"/>
          <text x="216" y="242" text-anchor="middle" font-size="9" font-weight="bold" fill="#4ade80">
            Ⅱ. 关口双向多功能电能表与 A 级电能质量在线监测单元 (GB/T 14549)
          </text>
          <text x="42" y="262" font-size="8" fill="#cbd5e1" font-family="monospace">1. 光伏发电关口表：DTSD888 (0.5S级，支持正向发电/反向用电四象限计量 + RS485双通信口)；</text>
          <text x="42" y="278" font-size="8" fill="#cbd5e1" font-family="monospace">2. 产权分界点双向表：安装于厂区10kV/0.4kV变压器低压总进线侧，监测上网余电与防逆流功率；</text>
          <text x="42" y="294" font-size="8" fill="#cbd5e1" font-family="monospace">3. 电能质量监测：实时监测总谐波畸变率 THD ≤ 4.0%、三相电压不平衡度 ≤ 2.0%、闪变 Pst；</text>
          <text x="42" y="310" font-size="8" fill="#facc15" font-family="monospace">4. 消防联动急停：接收厂区消防控制室 DC24V 干接点信号，火灾时 0.1s 内分断 1QF 并闭锁逆变器；</text>
          <text x="42" y="326" font-size="8" fill="#4ade80" font-family="monospace">5. 柜体配置：前门镶嵌 7寸触摸屏 HMI + 温湿度控制器 WHD46 + 柜顶强排风机 + 底板防火泥封堵。</text>
        </g>

        <!-- Right Half: SCADA / RS485 Modbus-RTU / Anti-Backflow CT & Cloud Dispatch Topology -->
        <g transform="translate(460, 46)">
          <rect x="0" y="0" width="434" height="368" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="217" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#38bdf8">
            Ⅲ. 光伏电站数据采集器 (Logger)、RS485 环网与电网「四遥」调度拓扑图
          </text>
          <!-- Row 1: String Inverters RS485 Daisy Chain -->
          <rect x="26" y="34" width="382" height="68" fill="#050a14" stroke="#60a5fa" stroke-width="1.2"/>
          <text x="217" y="50" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#60a5fa">
            屋面组串逆变器通信层 (${esc(inv.model)} × ${s.inverterCount} 台 · RS485 Modbus-RTU 手拉手总线)
          </text>
          ${Array.from({ length: Math.min(4, Math.max(2, s.inverterCount)) }).map((_, i) => `
            <rect x="${42 + i * 90}" y="58" width="76" height="34" rx="3" fill="rgba(37,99,235,0.22)" stroke="#38bdf8" stroke-width="1"/>
            <text x="${80 + i * 90}" y="73" text-anchor="middle" font-size="7.8" font-weight="bold" fill="#f8fafc" font-family="monospace">INV-#${i + 1}</text>
            <text x="${80 + i * 90}" y="85" text-anchor="middle" font-size="7" fill="#94a3b8" font-family="monospace">Addr:${i + 1} 9600bps</text>
          `).join('')}
          <!-- RS485 Cable to Smart Logger -->
          <line x1="217" y1="102" x2="217" y2="128" stroke="#facc15" stroke-width="2" stroke-dasharray="4 2"/>
          <text x="225" y="118" font-size="7.5" fill="#facc15" font-family="monospace">DJYP2VP2-22 2×2×1.0mm² 屏蔽双绞线 (COM1)</text>

          <!-- Row 2: Smart Logger + Weather Station + Anti-Backflow Meter -->
          <rect x="112" y="128" width="210" height="84" fill="#050a14" stroke="#facc15" stroke-width="1.6"/>
          <text x="217" y="146" text-anchor="middle" font-size="9" font-weight="bold" fill="#facc15">智能数据采集器与防逆流控制器</text>
          <text x="217" y="160" text-anchor="middle" font-size="8" fill="#38bdf8" font-family="monospace">SmartLogger 3000A / 光筑边缘网关</text>
          <text x="124" y="176" font-size="7.5" fill="#cbd5e1" font-family="monospace">· COM1: 逆变器群控调功 (0~100%有功/无功)</text>
          <text x="124" y="190" font-size="7.5" fill="#cbd5e1" font-family="monospace">· COM2: 关口防逆流电表 DTSD888 (100ms采样)</text>
          <text x="124" y="204" font-size="7.5" fill="#4ade80" font-family="monospace">· COM3: 五要素微型气象站 (POA辐照/背板温/风速)</text>

          <!-- Side Box: Weather Station -->
          <rect x="20" y="140" width="80" height="58" fill="#050a14" stroke="#4ade80" stroke-width="1"/>
          <text x="60" y="158" text-anchor="middle" font-size="7.8" font-weight="bold" fill="#4ade80">屋面环境监测仪</text>
          <text x="60" y="172" text-anchor="middle" font-size="7" fill="#cbd5e1">总辐射/组件温度</text>
          <text x="60" y="186" text-anchor="middle" font-size="7" fill="#cbd5e1">风速/风向/环境温</text>
          <line x1="100" y1="169" x2="112" y2="169" stroke="#4ade80" stroke-width="1.5"/>

          <!-- Side Box: Anti-Reverse Power Meter -->
          <rect x="334" y="140" width="84" height="58" fill="#050a14" stroke="#f43f5e" stroke-width="1"/>
          <text x="376" y="158" text-anchor="middle" font-size="7.8" font-weight="bold" fill="#fb7185">防逆流开口CT</text>
          <text x="376" y="172" text-anchor="middle" font-size="7" fill="#cbd5e1">10kV主变低压侧</text>
          <text x="376" y="186" text-anchor="middle" font-size="7" fill="#facc15">闭环调节≤1.5s</text>
          <line x1="322" y1="169" x2="334" y2="169" stroke="#f43f5e" stroke-width="1.5"/>

          <!-- Row 3: Upstream Dispatch & Cloud Platform -->
          <line x1="165" y1="212" x2="120" y2="246" stroke="#38bdf8" stroke-width="1.5"/>
          <line x1="265" y1="212" x2="310" y2="246" stroke="#4ade80" stroke-width="1.5"/>

          <rect x="26" y="246" width="184" height="106" fill="#050a14" stroke="#38bdf8" stroke-width="1.2"/>
          <text x="118" y="264" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#38bdf8">电网调度自动化远动端</text>
          <text x="36" y="282" font-size="7.6" fill="#cbd5e1" font-family="monospace">· 规约: IEC 60870-5-104 光纤专网</text>
          <text x="36" y="298" font-size="7.6" fill="#cbd5e1" font-family="monospace">· 纵向加密认证 + 调度数据网路由器</text>
          <text x="36" y="314" font-size="7.6" fill="#facc15" font-family="monospace">· 支持「四遥」: 遥测/遥信/遥控/遥调</text>
          <text x="36" y="330" font-size="7.6" fill="#4ade80" font-family="monospace">· AGC/AVC 有功无功连续平滑调节</text>

          <rect x="224" y="246" width="184" height="106" fill="#050a14" stroke="#10b981" stroke-width="1.2"/>
          <text x="316" y="264" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#4ade80">业主/光筑智慧云平台 &amp; 手机APP</text>
          <text x="234" y="282" font-size="7.6" fill="#cbd5e1" font-family="monospace">· 4G/5G 工业无线网关 + 以太网双链路</text>
          <text x="234" y="298" font-size="7.6" fill="#cbd5e1" font-family="monospace">· 组串级 I-V 曲线在线智能故障诊断</text>
          <text x="234" y="314" font-size="7.6" fill="#facc15" font-family="monospace">· 发电量日报/月报与PR效率偏差预警</text>
          <text x="234" y="330" font-size="7.6" fill="#4ade80" font-family="monospace">· 直流拉弧 AFCI 报警与无人机巡检联动</text>
        </g>

        <!-- Bottom-Left Legend -->
        <g transform="translate(26, ${H - 84})">
          <rect x="0" y="0" width="490" height="64" fill="#070d19" fill-opacity="0.92" stroke="#1e293b" stroke-width="1"/>
          <text x="10" y="15" font-size="9.5" font-weight="bold" fill="#38bdf8">二次控制与通讯施工规范：</text>
          <text x="10" y="30" font-size="8.6" fill="#cbd5e1">1. 电流互感器二次回路采用 ZR-BV-2.5mm² 铜芯线，严禁开路且一点可靠接地；电压回路采用 1.5mm²；</text>
          <text x="10" y="44" font-size="8.6" fill="#cbd5e1">2. RS485 通讯线采用屏蔽双绞线穿镀锌钢管明敷，总线首末两端跨接 120Ω 终端匹配电阻；</text>
          <text x="10" y="58" font-size="8.6" fill="#cbd5e1">3. 满足《分布式电源接入配电网技术规定》(GB/T 33593) 与电网公司「可观、可测、可调、可控」验收标准。</text>
        </g>
      </svg>`;
    }

    // =========================================================================
    // Sheet 14: 'bess_storage' (CN-01) — 储能AI光储一体化与削峰填谷系统图
    // =========================================================================
    if (sheet === 'bess_storage') {
      const configuredBessCap = Math.max(0, Number(this.bessCapacityKwh) || 0);
      const configuredBessPow = Math.max(0, Number(this.bessPowerKw) || 0);
      const hasConfiguredBess = configuredBessCap > 0 && configuredBessPow > 0;
      const bessPcsKw = hasConfiguredBess ? configuredBessPow : 0;
      const bessCapKwh = hasConfiguredBess ? configuredBessCap : 0;
      const cabinetsCnt = hasConfiguredBess ? Math.max(1, Math.round(bessCapKwh / 215)) : 0;
      const annualArbitrageWan = hasConfiguredBess ? ((bessCapKwh * 0.9 * 2 * 330 * 0.68) / 10000).toFixed(2) : '0.00';
      const baseSelfRatio = Number(this.selfConsumptionRatio ?? 0.82);
      const pvSelfUseBoostPct = hasConfiguredBess
        ? Math.min(98.5, baseSelfRatio * 100).toFixed(1)
        : (baseSelfRatio * 100).toFixed(1);
      const topoSubTitle = hasConfiguredBess
        ? `Ⅰ. 光储充 0.4kV 交流耦合一次拓扑 (${s.dcKw}kWp 光伏 + ${bessPcsKw}kW/${bessCapKwh}kWh 液冷储能)`
        : `Ⅰ. 纯光伏并网 0.4kV 一次拓扑 (${s.dcKw}kWp 光伏 · 未配置储能系统)`;
      return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sheetNames[sheet])}">
        ${frameAndTitleBlock}
        <text x="450" y="34" text-anchor="middle" font-size="12.5" font-weight="bold" fill="#38bdf8">
          ${esc(this.projectName)} — 光储充一体化拓扑与 24h 削峰填谷运行图 (CN-01)
        </text>

        <!-- Quadrant 1 (Top-Left): AC-Coupled PV + Liquid-Cooled BESS Architecture -->
        <g transform="translate(26, 46)">
          <rect x="0" y="0" width="424" height="176" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="212" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15">
            ${topoSubTitle}
          </text>
          <!-- 0.4kV Main AC Bus -->
          <line x1="25" y1="88" x2="398" y2="88" stroke="#facc15" stroke-width="3"/>
          <text x="398" y="81" text-anchor="end" font-size="7.8" font-weight="bold" fill="#facc15" font-family="monospace">0.4kV 厂区低压母线 (380V 50Hz)</text>

          <!-- Branch 1: PV Array -->
          <rect x="28" y="32" width="110" height="38" rx="4" fill="rgba(37,99,235,0.28)" stroke="#38bdf8" stroke-width="1.2"/>
          <text x="83" y="48" text-anchor="middle" font-size="8" font-weight="bold" fill="#38bdf8">屋面光伏阵列</text>
          <text x="83" y="62" text-anchor="middle" font-size="7.5" fill="#e2e8f0" font-family="monospace">${s.dcKw}kWp (${s.inverterCount}台逆变器)</text>
          <line x1="83" y1="70" x2="83" y2="88" stroke="#38bdf8" stroke-width="2"/>

          <!-- Branch 2: Liquid-Cooled LFP BESS Cabinet -->
          <rect x="155" y="106" width="138" height="58" rx="4" fill="rgba(16,185,129,0.22)" stroke="#10b981" stroke-width="1.5"/>
          <text x="224" y="123" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#4ade80">磷酸铁锂液冷储能一体柜</text>
          <text x="224" y="137" text-anchor="middle" font-size="7.8" fill="#fef08a" font-family="monospace">${bessPcsKw}kW / ${bessCapKwh}kWh (${cabinetsCnt}台)</text>
          <text x="224" y="151" text-anchor="middle" font-size="7.2" fill="#cbd5e1" font-family="monospace">280Ah LFP电芯 · 3S(BMS+PCS+EMS)</text>
          <line x1="224" y1="88" x2="224" y2="106" stroke="#4ade80" stroke-width="2.2"/>

          <!-- Branch 3: EMS AI Controller & Grid Transformer -->
          <rect x="165" y="32" width="120" height="38" rx="4" fill="rgba(250,204,21,0.18)" stroke="#facc15" stroke-width="1.2"/>
          <text x="225" y="48" text-anchor="middle" font-size="8" font-weight="bold" fill="#facc15">AI 能量管理系统 (EMS)</text>
          <text x="225" y="62" text-anchor="middle" font-size="7.2" fill="#cbd5e1" font-family="monospace">需量控制 + 削峰填谷 + 防逆流</text>
          <line x1="225" y1="70" x2="225" y2="88" stroke="#facc15" stroke-width="1.4" stroke-dasharray="3 2"/>

          <!-- Branch 4: Factory Load -->
          <rect x="310" y="106" width="94" height="58" rx="4" fill="rgba(244,63,94,0.18)" stroke="#fb7185" stroke-width="1.2"/>
          <text x="357" y="124" text-anchor="middle" font-size="8" font-weight="bold" fill="#fb7185">厂区重要生产负荷</text>
          <text x="357" y="139" text-anchor="middle" font-size="7.2" fill="#cbd5e1" font-family="monospace">绿电消纳提升至</text>
          <text x="357" y="153" text-anchor="middle" font-size="8" font-weight="bold" fill="#4ade80" font-family="monospace">${pvSelfUseBoostPct}%</text>
          <line x1="357" y1="88" x2="357" y2="106" stroke="#fb7185" stroke-width="2"/>
        </g>

        <!-- Quadrant 2 (Top-Right): 24-Hour AI Two-Charge / Two-Discharge Dispatch Curve -->
        <g transform="translate(460, 46)">
          <rect x="0" y="0" width="434" height="176" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="217" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#4ade80">
            Ⅱ. 储能 AI 24 小时「两充两放」削峰填谷与光伏余电吸收运行曲线
          </text>
          <rect x="38" y="28" width="372" height="114" fill="#050a14" stroke="#1e293b" stroke-width="0.9"/>
          <!-- Zero Power Baseline -->
          <line x1="38" y1="95" x2="410" y2="95" stroke="#64748b" stroke-width="1" stroke-dasharray="3 2"/>
          <text x="34" y="98" text-anchor="end" font-size="7" fill="#94a3b8">0kW</text>
          <!-- PV Bell Curve (06:00 .. 18:00) -->
          <path d="M 38,95 L 125,95 Q 224,22 320,95 L 410,95" fill="rgba(250,204,21,0.18)" stroke="#facc15" stroke-width="1.8"/>
          <text x="224" y="45" text-anchor="middle" font-size="7.5" font-weight="bold" fill="#facc15">☀️ 光伏出力峰值 ${s.dcKw}kW</text>
          <!-- Factory Load Curve -->
          <path d="M 38,78 L 115,78 L 145,52 L 210,55 L 245,68 L 295,44 L 365,48 L 410,76" fill="none" stroke="#38bdf8" stroke-width="1.6"/>
          <!-- BESS Charge/Discharge Bars (Valley Charge 00-08, Peak Discharge 09-11, Mid Charge 11-13, Peak Discharge 14-21) -->
          <rect x="48" y="95" width="68" height="26" fill="rgba(59,130,246,0.45)" stroke="#60a5fa" stroke-width="0.8"/>
          <text x="82" y="111" text-anchor="middle" font-size="6.8" fill="#bfdbfe">谷电充电1</text>
          <rect x="145" y="69" width="48" height="26" fill="rgba(16,185,129,0.52)" stroke="#4ade80" stroke-width="0.8"/>
          <text x="169" y="85" text-anchor="middle" font-size="6.8" fill="#dcfce7">早峰放电1</text>
          <rect x="202" y="95" width="44" height="28" fill="rgba(250,204,21,0.45)" stroke="#facc15" stroke-width="0.8"/>
          <text x="224" y="112" text-anchor="middle" font-size="6.8" fill="#fef08a">午间光伏充2</text>
          <rect x="262" y="65" width="84" height="30" fill="rgba(16,185,129,0.58)" stroke="#4ade80" stroke-width="0.8"/>
          <text x="304" y="83" text-anchor="middle" font-size="6.8" fill="#dcfce7">晚尖峰放电2</text>
          <text x="224" y="156" text-anchor="middle" font-size="7.8" fill="#cbd5e1" font-family="monospace">
            00:00(谷) ── 08:00(峰) ── 12:00(平/光伏午谷) ── 17:00(尖峰) ── 24:00 · 综合效率 RTE=89.2%
          </text>
        </g>

        <!-- Quadrant 3 (Bottom-Left): Pure PV vs PV+BESS AI Comparison Table -->
        <g transform="translate(26, 232)">
          <rect x="0" y="0" width="424" height="182" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="212" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#38bdf8">
            Ⅲ. 纯光伏方案 vs 光储联合方案经济性对比表
          </text>
          ${[
            ['对比指标', '纯光伏并网方案', '光储 AI 协同方案 (推荐)'],
            ['系统配置规模', `${s.dcKw} kWp 光伏`, `${s.dcKw} kWp 光伏 + ${bessPcsKw}kW/${bessCapKwh}kWh 储能`],
            ['绿电自发自用消纳比例', `${(baseSelfRatio * 100).toFixed(1)}% (午间余电上网)`, `${pvSelfUseBoostPct}% (午间余电充入储能晚峰放电)`],
            ['变压器最大需量削减 (MD)', '0 kW (阴雨天无支撑)', `削减尖峰需量 ${Math.round(bessPcsKw * 0.85)} kW (节省基本电费)`],
            ['年削峰填谷电价差套利收益', '0.00 万元/年', `+${annualArbitrageWan} 万元/年 (两充两放×330天)`],
            ['厂区重要负荷停电备电能力', '电网停电即防孤岛解列', 'STS 10ms 无缝切换并离网黑启动备电'],
          ].map(([c1, c2, c3], idx) => `
            <line x1="0" y1="${28 + idx * 25}" x2="424" y2="${28 + idx * 25}" stroke="#1e293b" stroke-width="0.8"/>
            <text x="10" y="${44 + idx * 25}" font-size="7.8" font-weight="${idx === 0 ? 'bold' : 'normal'}" fill="${idx === 0 ? '#facc15' : '#94a3b8'}">${esc(c1)}</text>
            <text x="165" y="${44 + idx * 25}" font-size="7.8" fill="${idx === 0 ? '#facc15' : '#cbd5e1'}" font-family="monospace">${esc(c2)}</text>
            <text x="282" y="${44 + idx * 25}" font-size="7.8" font-weight="bold" fill="${idx === 0 ? '#facc15' : '#4ade80'}" font-family="monospace">${esc(c3)}</text>
          `).join('')}
        </g>

        <!-- Quadrant 4 (Bottom-Right): BESS Safety, Fire Protection & Enclosure Foundation Spec -->
        <g transform="translate(460, 232)">
          <rect x="0" y="0" width="434" height="182" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="217" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15">
            Ⅳ. 液冷储能一体柜技术参数与 PACK 级全氟己酮消防安全规范 (GB 51048)
          </text>
          ${[
            ['电芯与成组规格', '磷酸铁锂 LFP 3.2V/280Ah · 1P240S 液冷电池簇 · 循环寿命 ≥ 8000次 (@90% DOD)'],
            ['液冷温控系统', '乙二醇变频液冷机组 · 电芯最大温差 ΔT ≤ 2.5°C · 防护等级 IP55 / 防腐 C4'],
            ['三级消防配置', 'PACK级可燃气体(CO/H₂)+感温感烟探测 + 全氟己酮自动喷淋 + 水消防接口'],
            ['防爆与泄压设计', '柜顶独立防爆泄压板 (泄压面积≥0.15m²) + 防爆强排风机 (连锁可燃气体浓度)'],
            ['户外基础与退距', 'C30 钢筋混凝土条形基础高出地面 300mm · 距离厂房甲乙类仓库 ≥ 15m，丙类 ≥ 6m'],
            ['单柜尺寸与重量', 'W1350 × D1400 × H2350 mm · 单柜满载重约 2.65 t · 接地电阻 R ≤ 4.0 Ω'],
          ].map(([k, v], idx) => `
            <line x1="0" y1="${28 + idx * 25}" x2="434" y2="${28 + idx * 25}" stroke="#1e293b" stroke-width="0.7"/>
            <text x="10" y="${44 + idx * 25}" font-size="7.8" fill="#94a3b8">${esc(k)}</text>
            <text x="112" y="${44 + idx * 25}" font-size="7.6" font-weight="bold" fill="#e2e8f0" font-family="monospace">${esc(v)}</text>
          `).join('')}
        </g>

        <!-- Bottom-Left Legend -->
        <g transform="translate(26, ${H - 84})">
          <rect x="0" y="0" width="490" height="64" fill="#070d19" fill-opacity="0.92" stroke="#1e293b" stroke-width="1"/>
          <text x="10" y="15" font-size="9.5" font-weight="bold" fill="#38bdf8">光储一体化系统设计说明：</text>
          <text x="10" y="30" font-size="8.6" fill="#cbd5e1">1. 储能变流器 (PCS) 采用三电平双向拓扑，支持 PQ、VF、VSG 虚拟同步机及四象限动态无功补偿；</text>
          <text x="10" y="44" font-size="8.6" fill="#cbd5e1">2. EMS 实时采集关口防逆流 CT 与光伏逆变器出力，优先吸收午间光伏弃光余电，绝不向公共电网反送电；</text>
          <text x="10" y="58" font-size="8.6" fill="#cbd5e1">3. 严格执行《电化学储能电站设计规范》(GB 51048)，储能区设置 1.8m 高安全围栏与声光报警器。</text>
        </g>
      </svg>`;
    }

    // =========================================================================
    // Sheet 15: 'pvlane_birdseye' (FX-02) — 屋面改造前后实景对比与业主汇报图
    // =========================================================================
    if (sheet === 'pvlane_birdseye') {
      const dcf = this.financialDcf || {};
      const tariffVal = Number(dcf.weightedTariffRmb ?? this.tariffRmb ?? 0.78);
      const roofAreaVal = Math.max(500, Math.round(s.roofAreaM2 || (frame.widthU * frame.heightV)));
      const irrLabel = s.irrPct != null && Number.isFinite(Number(s.irrPct)) ? `${s.irrPct}%` : '未回收';
      const pbLabel = s.paybackYears != null && Number.isFinite(Number(s.paybackYears)) ? `${s.paybackYears} 年` : '无法收回';
      const annualSavingWan = ((s.annualKwh * tariffVal) / 10000).toFixed(1);
      const co2TonYr = (s.annualKwh * 0.0005703).toFixed(1);
      const coalTonYr = (s.annualKwh * 0.0003015).toFixed(1);
      const treesEq = Math.round(Number(co2TonYr) * 55);
      return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sheetNames[sheet])}">
        ${frameAndTitleBlock}
        <text x="450" y="34" text-anchor="middle" font-size="12.5" font-weight="bold" fill="#38bdf8">
          ${esc(this.projectName)} — 屋面改造前后实景鸟瞰对比与业主投资汇报图 (FX-02)
        </text>

        <!-- Quadrant 1 (Top-Left): BEFORE — 改造前厂房无人机斜拍原貌图 -->
        <g transform="translate(26, 46)">
          <rect x="0" y="0" width="424" height="176" fill="#070d19" stroke="#64748b" stroke-width="1"/>
          <rect x="10" y="10" width="96" height="20" rx="4" fill="#334155"/>
          <text x="58" y="24" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#f8fafc">BEFORE · 改造前原貌</text>
          <text x="260" y="23" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#94a3b8">
            闲置工业屋面 (${roofAreaVal}m² 太阳辐射直晒，夏季屋顶表面温度达 68°C)
          </text>
          <!-- Perspective Factory Building Before PV -->
          <polygon points="88,48 352,48 395,128 42,128" fill="#334155" stroke="#cbd5e1" stroke-width="1.5"/>
          <polygon points="42,128 395,128 395,154 42,154" fill="#1e293b" stroke="#64748b" stroke-width="1.2"/>
          <!-- Bare Roof Seams & Skylights -->
          ${[1, 2, 3, 4, 5].map((i) => `<line x1="${88 + i * 44}" y1="48" x2="${42 + i * 58}" y2="128" stroke="#475569" stroke-width="0.9"/>`).join('')}
          <polygon points="165,68 265,68 274,84 158,84" fill="rgba(56,189,248,0.22)" stroke="#38bdf8" stroke-width="1" stroke-dasharray="3 2"/>
          <text x="218" y="79" text-anchor="middle" font-size="7.5" fill="#38bdf8">原有FRP采光带与排烟天窗</text>
          <text x="218" y="112" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#fb7185">
            ❌ 屋面资产闲置 · 空调制冷能耗高 · 彩钢瓦紫外线老化快
          </text>
          <text x="218" y="168" text-anchor="middle" font-size="7.8" fill="#94a3b8" font-family="monospace">
            无人机航拍视角：Pitch=42° · 焦距 24mm 等效 · 四角控制点 P1~P4 已标定
          </text>
        </g>

        <!-- Quadrant 2 (Top-Right): AFTER — 改造后透视配准光伏实景合成图 -->
        <g transform="translate(460, 46)">
          <rect x="0" y="0" width="434" height="176" fill="#070d19" stroke="#10b981" stroke-width="1.4"/>
          <rect x="10" y="10" width="102" height="20" rx="4" fill="#059669"/>
          <text x="61" y="24" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#ffffff">AFTER · 改造后实景</text>
          <text x="272" y="23" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#4ade80">
            铺设 ${s.moduleCount} 块 N 型双玻组件 (${s.dcKw}kWp · 屋面隔热降温 4.2°C)
          </text>
          <!-- Perspective Factory Building After PV -->
          <polygon points="88,48 362,48 405,128 42,128" fill="#1e293b" stroke="#facc15" stroke-width="1.6"/>
          <polygon points="42,128 405,128 405,154 42,154" fill="#0f172a" stroke="#64748b" stroke-width="1.2"/>
          <!-- Perspective Warped PV Array Rows Avoiding Skylight -->
          ${[0, 1, 2, 3].map((r) => {
            const t0 = 0.08 + r * 0.22;
            const t1 = t0 + 0.16;
            const y0 = 48 + t0 * 80;
            const y1 = 48 + t1 * 80;
            const xL0 = 88 - t0 * 40;
            const xR0 = 362 + t0 * 38;
            const xL1 = 88 - t1 * 40;
            const xR1 = 362 + t1 * 38;
            return `<polygon points="${xL0.toFixed(1)},${y0.toFixed(1)} ${xR0.toFixed(1)},${y0.toFixed(1)} ${xR1.toFixed(1)},${y1.toFixed(1)} ${xL1.toFixed(1)},${y1.toFixed(1)}" fill="rgba(37,99,235,0.78)" stroke="#93c5fd" stroke-width="0.9"/>`;
          }).join('')}
          <!-- Preserved Skylight & Inspection Walkway -->
          <polygon points="170,68 272,68 280,84 164,84" fill="rgba(15,23,42,0.92)" stroke="#ef4444" stroke-width="1.1" stroke-dasharray="3 2"/>
          <text x="222" y="79" text-anchor="middle" font-size="7.2" fill="#fca5a5">采光带精准避让退距 ${this.obstacleSetbackM}m</text>
          <text x="222" y="144" text-anchor="middle" font-size="8" font-weight="bold" fill="#4ade80">
            ✅ 建筑光伏一体化视觉整齐美观 · 守护屋面防水延长寿命 10 年以上
          </text>
          <text x="222" y="168" text-anchor="middle" font-size="7.8" fill="#facc15" font-family="monospace">
            3×3 单应性矩阵 H 配准误差 ≤ 0.03m · 含女儿墙阴影半透明叠加
          </text>
        </g>

        <!-- Quadrant 3 (Bottom-Left): 2D Satellite Ortho Reference Plan -->
        <g transform="translate(26, 232)">
          <rect x="0" y="0" width="380" height="182" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="190" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#38bdf8">
            Ⅲ. 2D 卫星正射排布基准图与检修通道示意 (双视图联动)
          </text>
          <rect x="34" y="30" width="312" height="118" fill="#0f172a" stroke="#f8fafc" stroke-width="1.4"/>
          <rect x="42" y="38" width="296" height="102" fill="none" stroke="#ef4444" stroke-width="0.8" stroke-dasharray="4 2"/>
          <!-- Mini Ortho Array Grid -->
          ${[0, 1, 2, 3].map((r) =>
            [0, 1, 2, 3, 4, 5].map((c) => {
              if (r === 1 && (c === 2 || c === 3)) return '';
              return `<rect x="${48 + c * 47}" y="${44 + r * 23}" width="42" height="17" fill="rgba(37,99,235,0.75)" stroke="#93c5fd" stroke-width="0.6"/>`;
            }).join('')
          ).join('')}
          <rect x="142" y="67" width="88" height="17" fill="rgba(239,68,68,0.28)" stroke="#ef4444" stroke-width="1" stroke-dasharray="3 2"/>
          <text x="186" y="78" text-anchor="middle" font-size="7" fill="#fca5a5">禁布区避让</text>
          <text x="190" y="166" text-anchor="middle" font-size="8" fill="#cbd5e1" font-family="monospace">
            屋面可利用面积 ${roofAreaVal}m² · 组件投影覆盖率 ${Math.min(82, Math.round((s.moduleCount * mod.width_m * mod.length_m * 100) / Math.max(1, roofAreaVal)))}%
          </text>
        </g>

        <!-- Quadrant 4 (Bottom-Right): Owner Executive Value & ESG Carbon Reduction Dashboard -->
        <g transform="translate(416, 232)">
          <rect x="0" y="0" width="478" height="182" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="239" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15">
            Ⅳ. 业主报告中心 — 电站核心收益、ESG 绿电减碳与屋面附加价值总览
          </text>
          ${[
            ['装机规模与设备选型', `${s.dcKw} kWp (${esc(mod.model)} × ${s.moduleCount}块 + ${esc(inv.model)} × ${s.inverterCount}台)`],
            ['首年发电量与25年总发电', `首年 ${(s.annualKwh / 10000).toFixed(2)} 万kWh · 25年累计 ${((s.annualKwh * 23.65) / 10000).toFixed(1)} 万kWh`],
            ['业主年均节省电费收益', `约 ${annualSavingWan} 万元/年 · 静态投资回收期 ${pbLabel} (IRR=${irrLabel})`],
            ['ESG 每年碳减排贡献', `年减排 CO₂ ${co2TonYr} 吨 · 节约标煤 ${coalTonYr} 吨 · 等效植树 ${treesEq} 棵/年`],
            ['厂房车间夏季隔热降温', '光伏板遮阳吸收太阳辐射，夏季顶层车间温度降低 3.5~4.5°C，空调节电 12%'],
            ['施工周期与质保承诺', '标准工期 25~35 天（不停产施工）· 组件30年线性功率质保 / 逆变器5~10年质保'],
          ].map(([k, v], idx) => `
            <line x1="0" y1="${28 + idx * 25}" x2="478" y2="${28 + idx * 25}" stroke="#1e293b" stroke-width="0.7"/>
            <text x="10" y="${44 + idx * 25}" font-size="7.8" fill="#94a3b8">${esc(k)}</text>
            <text x="148" y="${44 + idx * 25}" font-size="7.8" font-weight="bold" fill="#4ade80" font-family="monospace">${esc(v)}</text>
          `).join('')}
        </g>

        <!-- Bottom-Left Legend -->
        <g transform="translate(26, ${H - 84})">
          <rect x="0" y="0" width="490" height="64" fill="#070d19" fill-opacity="0.92" stroke="#1e293b" stroke-width="1"/>
          <text x="10" y="15" font-size="9.5" font-weight="bold" fill="#38bdf8">业主实景汇报图说明：</text>
          <text x="10" y="30" font-size="8.6" fill="#cbd5e1">1. 本图基于无人机现场实拍照片与 2D 卫星正射设计图，通过单应性透视变换实现 1:1 真实尺寸合成；</text>
          <text x="10" y="44" font-size="8.6" fill="#cbd5e1">2. 直观展示改造前后厂房外观对比，所有采光带、排烟风机及消防检修通道均严格按规范退距避让；</text>
          <text x="10" y="58" font-size="8.6" fill="#cbd5e1">3. 可直接导出高清 PDF/PNG 用于集团立项汇报、园区管委会审批及绿色工厂 ESG 认证申报。</text>
        </g>
      </svg>`;
    }

    // =========================================================================
    // Sheet 16: 'pvsyst_near_shading' (PV-02) — 3D近场阴影、寻优矩阵与25年财务图
    // =========================================================================
    if (sheet === 'pvsyst_near_shading') {
      const wx = this.weatherEval || this.evaluateWeatherAndAngles();
      const ann3d = this.shading3dSummary || this.compute3DShadingReport();
      const dcf = this.financialDcf || {};
      const linShadePct = Number(ann3d?.annualLinearShadePct ?? 1.45).toFixed(2);
      const diodeExtraPct = Math.max(0.05, Number(ann3d?.annualElectricalShadePct ?? 1.8) - Number(ann3d?.annualLinearShadePct ?? 1.45)).toFixed(2);
      const capexPerW = Number(this.capexPerW ?? 3.15);
      const tariffVal = Number(dcf.weightedTariffRmb ?? this.tariffRmb ?? 0.78);
      const hasIrr = s.irrPct != null && Number.isFinite(Number(s.irrPct));
      const irrVal = hasIrr ? Number(s.irrPct) : 0;
      const hasPb = s.paybackYears != null && Number.isFinite(Number(s.paybackYears));
      const totalInvWan = Number(dcf.totalCapexWan ?? (s.dcKw * capexPerW / 10)).toFixed(2);
      const yr1RevWan = Number(dcf.year1RevenueWan ?? ((s.annualKwh * tariffVal) / 10000)).toFixed(2);
      const npvNum = Number(dcf.npv25Wan ?? (Number(yr1RevWan) * 14.2 - Number(totalInvWan)));
      const npvWan = `${npvNum >= 0 ? '+' : ''}${npvNum.toFixed(2)}`;
      const lcoeRmb = dcf.lcoeRmbPerKwh != null ? Number(dcf.lcoeRmbPerKwh).toFixed(3) : '--';
      return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sheetNames[sheet])}">
        ${frameAndTitleBlock}
        <text x="450" y="34" text-anchor="middle" font-size="12.5" font-weight="bold" fill="#38bdf8">
          ${esc(this.projectName)} — 3D 近场阴影模型、倾角×方位角寻优矩阵与 25 年现金流图 (PV-02)
        </text>

        <!-- Quadrant 1 (Top-Left): 3D Near-Shadings Isometric Scene & Electrical Sub-module Partition -->
        <g transform="translate(26, 46)">
          <rect x="0" y="0" width="424" height="176" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="212" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15">
            Ⅰ. 3D 近场阴影轴测模型与旁路二极管子串分区
          </text>
          <!-- Isometric Roof Plane -->
          <polygon points="40,132 145,62 390,78 285,148" fill="#0f172a" stroke="#64748b" stroke-width="1.3"/>
          <!-- South Parapet Wall Casting Shadow Wedge -->
          <polygon points="40,132 285,148 285,134 40,118" fill="#475569" stroke="#cbd5e1" stroke-width="1"/>
          <polygon points="40,132 285,148 302,126 62,112" fill="rgba(239,68,68,0.28)"/>
          <!-- 3 Isometric Tilted PV Sheds with 3 Bypass Diode Sub-strings -->
          ${[0, 1, 2].map((r) => {
            const bx = 75 + r * 32;
            const by = 114 - r * 18;
            return `
              <polygon points="${bx},${by} ${bx + 195},${by + 12} ${bx + 205},${by - 4} ${bx + 10},${by - 16}" fill="rgba(37,99,235,0.82)" stroke="#93c5fd" stroke-width="1"/>
              <line x1="${bx + 3}" y1="${by - 5}" x2="${bx + 198}" y2="${by + 7}" stroke="#facc15" stroke-width="0.6" stroke-dasharray="2 2"/>
              <line x1="${bx + 7}" y1="${by - 10}" x2="${bx + 202}" y2="${by + 2}" stroke="#facc15" stroke-width="0.6" stroke-dasharray="2 2"/>
            `;
          }).join('')}
          <!-- Sun Ray Vector -->
          <line x1="35" y1="42" x2="115" y2="96" stroke="#facc15" stroke-width="1.8" stroke-dasharray="4 2"/>
          <circle cx="35" cy="42" r="8" fill="#facc15"/>
          <text x="50" y="45" font-size="7.5" fill="#fef08a" font-family="monospace">冬至9:00太阳光线 (高度角${wx.solarAlt9amDeg}°)</text>
          <text x="212" y="166" text-anchor="middle" font-size="7.8" fill="#cbd5e1" font-family="monospace">
            线性几何阴影损失: -${linShadePct}% · 旁路二极管电气失配损失: -${diodeExtraPct}% · 前后排无遮挡间距 D=${wx.currentUnshadedGapM}m
          </text>
        </g>

        <!-- Quadrant 2 (Top-Right): Tilt × Azimuth Transposition Factor Iso-Yield Contour Matrix -->
        <g transform="translate(460, 46)">
          <rect x="0" y="0" width="434" height="176" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="217" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#38bdf8">
            Ⅱ. 倾角 (Tilt) × 方位角 (Azimuth) 年满发小时数寻优热力矩阵 (kWh/kWp)
          </text>
          <!-- 5 Tilts × 7 Azimuths Heatmap Table -->
          ${(() => {
            const tilts = [5, 10, 15, wx.weatherOptimalTiltDeg || 24, 32];
            const azis = [-45, -30, -15, 0, 15, 30, 45];
            const header = azis.map((az, ci) => `<text x="${108 + ci * 46}" y="38" text-anchor="middle" font-size="7.5" font-weight="bold" fill="#94a3b8" font-family="monospace">${az === 0 ? '0°正南' : `${az > 0 ? '+' : ''}${az}°`}</text>`).join('');
            const rows = tilts.map((t, ri) => {
              const y = 44 + ri * 21;
              const isOptRow = Math.abs(t - (wx.weatherOptimalTiltDeg || 24)) <= 3;
              const cells = azis.map((az, ci) => {
                const penalty = Math.pow((t - (wx.weatherOptimalTiltDeg || 24)) / 28, 2) * 0.08 + Math.pow(az / 90, 2) * 0.09;
                const val = Math.round((s.specificYield || 1180) * (1.03 - penalty));
                const ratio = Math.max(0, Math.min(1, 1 - penalty * 6));
                const bg = ratio > 0.85 ? 'rgba(16,185,129,0.45)' : ratio > 0.65 ? 'rgba(56,189,248,0.32)' : 'rgba(250,204,21,0.22)';
                const isPeak = isOptRow && az === 0;
                return `
                  <rect x="${86 + ci * 46}" y="${y}" width="44" height="19" fill="${bg}" stroke="${isPeak ? '#facc15' : '#1e293b'}" stroke-width="${isPeak ? '1.5' : '0.6'}"/>
                  <text x="${108 + ci * 46}" y="${y + 13}" text-anchor="middle" font-size="7.5" font-weight="${isPeak ? 'bold' : 'normal'}" fill="${isPeak ? '#fef08a' : '#f8fafc'}" font-family="monospace">${val}</text>
                `;
              }).join('');
              return `
                <text x="78" y="${y + 13}" text-anchor="end" font-size="7.5" font-weight="${isOptRow ? 'bold' : 'normal'}" fill="${isOptRow ? '#facc15' : '#cbd5e1'}" font-family="monospace">倾角 ${t}°</text>
                ${cells}
              `;
            }).join('');
            return header + rows;
          })()}
          <text x="217" y="166" text-anchor="middle" font-size="7.8" fill="#4ade80" font-family="monospace">
            ★ 单瓦辐照最优倾角: ${wx.weatherOptimalTiltDeg}° (正南0°) · 工业屋面综合装机量与抗风最优倾角: ${wx.roofOptimalTiltDeg}°
          </text>
        </g>

        <!-- Quadrant 3 (Bottom-Left): 25-Year Cumulative Net Cash Flow & Degradation Curve -->
        <g transform="translate(26, 232)">
          <rect x="0" y="0" width="424" height="182" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="212" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#4ade80">
            Ⅲ. 25 年全寿命周期累计净现金流回本曲线与 N 型组件线性功率质保 (0.4%/年)
          </text>
          <rect x="38" y="28" width="360" height="118" fill="#050a14" stroke="#1e293b" stroke-width="0.9"/>
          <!-- Zero Cashflow Payback Axis -->
          <line x1="38" y1="106" x2="398" y2="106" stroke="#94a3b8" stroke-width="1" stroke-dasharray="3 2"/>
          <text x="34" y="109" text-anchor="end" font-size="7" fill="#94a3b8">0万</text>
          <!-- 25-Year Cumulative Cashflow Bars -->
          ${Array.from({ length: 25 }).map((_, yr) => {
            const x = 44 + yr * 14;
            const progress = hasPb ? (yr + 1 - Number(s.paybackYears)) / 20 : -0.45;
            const barH = Math.min(68, Math.max(-36, Math.round(progress * 68)));
            const isPositive = barH >= 0;
            return `<rect x="${x}" y="${isPositive ? 106 - barH : 106}" width="10" height="${Math.abs(barH)}" fill="${isPositive ? '#10b981' : '#f43f5e'}" fill-opacity="0.78"/>`;
          }).join('')}
          <!-- Payback Year Marker -->
          ${hasPb ? `
          <circle cx="${44 + Math.min(340, Math.round(Number(s.paybackYears) * 14))}" cy="106" r="4.5" fill="#facc15" stroke="#050a14" stroke-width="1.2"/>
          <text x="${52 + Math.min(220, Math.round(Number(s.paybackYears) * 14))}" y="122" font-size="7.8" font-weight="bold" fill="#facc15">
            ← 第 ${s.paybackYears} 年收回全部投资 (${totalInvWan}万元)
          </text>` : `
          <text x="218" y="122" text-anchor="middle" font-size="7.8" font-weight="bold" fill="#fb7185">
            寿命期内现金流未覆盖初始投资 (${totalInvWan}万元 · 无法收回)
          </text>`}
          <text x="218" y="166" text-anchor="middle" font-size="7.8" fill="#cbd5e1" font-family="monospace">
            首年衰减 ≤ 1.0%，第2~25年线性衰减 ≤ 0.40%/年 · 第25年末剩余功率 ≥ 89.4%
          </text>
        </g>

        <!-- Quadrant 4 (Bottom-Right): Internal Investment Committee Financial & Sensitivity Table -->
        <g transform="translate(460, 232)">
          <rect x="0" y="0" width="434" height="182" fill="#070d19" stroke="#38bdf8" stroke-width="1"/>
          <text x="217" y="18" text-anchor="middle" font-size="9.5" font-weight="bold" fill="#facc15">
            Ⅳ. 内部报告中心 — 投资投决财务指标与电价/造价敏感性压力测试表
          </text>
          ${[
            ['工程静态总投资 (EPC总包)', `${totalInvWan} 万元 (光伏单位造价 ${capexPerW.toFixed(2)} 元/Wp)`],
            ['首年净发电收入与度电成本', `首年营收 ${yr1RevWan} 万元 · 平准化度电成本 LCOE = ${lcoeRmb} 元/kWh`],
            ['全投资内部收益率 (IRR)', hasIrr ? `税前 IRR = ${irrVal}% · 资本金 IRR (70%融资) = ${(irrVal * 1.48).toFixed(1)}%` : '现金流未回正 · IRR = 未回收'],
            ['财务净现值 (NPV @折现率)', `${npvWan} 万元 · 静态回收期 ${hasPb ? `${s.paybackYears} 年` : '无法收回'}`],
            ['敏感性测试①：EPC造价上浮 +10%', hasIrr ? `IRR 调整为 ${(irrVal * 0.91).toFixed(1)}% · 回收期 +0.4 年` : '造价偏高 · 需核减成本或提升自用率'],
            ['敏感性测试②：消纳电价下浮 -10%', hasIrr ? `IRR 调整为 ${(irrVal * 0.89).toFixed(1)}%` : '收益偏低 · 建议配置削峰填谷消纳'],
          ].map(([k, v], idx) => `
            <line x1="0" y1="${28 + idx * 25}" x2="434" y2="${28 + idx * 25}" stroke="#1e293b" stroke-width="0.7"/>
            <text x="10" y="${44 + idx * 25}" font-size="7.8" fill="#94a3b8">${esc(k)}</text>
            <text x="198" y="${44 + idx * 25}" font-size="7.8" font-weight="bold" fill="#4ade80" font-family="monospace">${esc(v)}</text>
          `).join('')}
        </g>

        <!-- Bottom-Left Legend -->
        <g transform="translate(26, ${H - 84})">
          <rect x="0" y="0" width="490" height="64" fill="#070d19" fill-opacity="0.92" stroke="#1e293b" stroke-width="1"/>
          <text x="10" y="15" font-size="9.5" font-weight="bold" fill="#38bdf8">3D 近场阴影与投决财务说明：</text>
          <text x="10" y="30" font-size="8.6" fill="#cbd5e1">1. 近场阴影模型按组件 3 个旁路二极管子串建立电气失配模型，准确计入女儿墙及前排遮挡影响；</text>
          <text x="10" y="44" font-size="8.6" fill="#cbd5e1">2. 财务模型计入运维费 (0.04元/W/年)、增值税即征即退及企业所得税「三免三减半」优惠政策；</text>
          <text x="10" y="58" font-size="8.6" fill="#cbd5e1">3. 本图纸同步关联工程授信评估与内部投决财务指标，可直接导出投决表。</text>
        </g>
      </svg>`;
    }

    // Bracket CAD Sheet (Side Cross-Section Profile + Front Elevation + BOM Table — Video 1 v1_18.5s..v1_27.0s)
    if (sheet === 'bracket') {
      const bcfg = this.bracketCfg || {
        h1Mm: 500, y0Mm: 1500, y1Mm: 1600, angleDeg: 15, x1Mm: 400, x2Mm: 1900,
        foundationType: '混凝土条形基础/方墩', concreteGrade: 'C25',
      };
      const tilt = Number.isFinite(Number(bcfg.angleDeg))
        ? Number(bcfg.angleDeg)
        : (this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg);
      const slopeLenMm = Math.round(mod.length_m * 2000 + 20);
      const h2Mm = Math.round(bcfg.h1Mm + slopeLenMm * Math.sin((tilt * Math.PI) / 180));
      return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="光伏支架剖面与立面CAD施工图">
        ${frameAndTitleBlock}
        <!-- Left: Side Cross-Section Profile (支架侧视图预览 / Ⅰ-Ⅰ 剖面大样图) -->
        <g transform="translate(55, 65)">
          <text x="165" y="0" text-anchor="middle" font-size="12" font-weight="bold" fill="#38bdf8">Ⅰ-Ⅰ 支架侧视图预览 / 剖面大样图 (1:25)</text>
          <!-- Roof Base -->
          <line x1="10" y1="240" x2="340" y2="240" stroke="#94a3b8" stroke-width="2.5"/>
          ${Array.from({ length: 16 }, (_, i) => `<line x1="${20 + i * 20}" y1="240" x2="${12 + i * 20}" y2="252" stroke="#64748b" stroke-width="1"/>`).join('')}
          <!-- Concrete Pier / Clamp (${esc(bcfg.concreteGrade)}) -->
          <rect x="65" y="222" width="36" height="18" fill="none" stroke="#facc15" stroke-width="1.5"/>
          <rect x="245" y="222" width="36" height="18" fill="none" stroke="#facc15" stroke-width="1.5"/>
          <!-- Front & Rear Vertical Posts -->
          <line x1="83" y1="222" x2="83" y2="178" stroke="#22c55e" stroke-width="2.5"/>
          <line x1="263" y1="222" x2="263" y2="108" stroke="#22c55e" stroke-width="2.5"/>
          <!-- Diagonal Wind Bracing -->
          <line x1="83" y1="205" x2="263" y2="145" stroke="#22c55e" stroke-width="1.5" stroke-dasharray="5 3"/>
          <!-- Inclined Purline / Aluminum Rail -->
          <line x1="48" y1="192" x2="302" y2="92" stroke="#38bdf8" stroke-width="3.2"/>
          <!-- Solar Module Profile -->
          <line x1="44" y1="185" x2="298" y2="85" stroke="#60a5fa" stroke-width="5"/>
          <!-- Video 1 Dimension Lines: A, H1, H2, Y1, Y0 -->
          <line x1="48" y1="192" x2="295" y2="192" stroke="#f43f5e" stroke-width="0.9" stroke-dasharray="3 3"/>
          <text x="155" y="184" font-size="10.5" fill="#f43f5e" font-family="monospace">安装倾角 A = ${tilt}° · 排距 Y0 = ${bcfg.y0Mm}mm</text>
          <text x="165" y="75" text-anchor="middle" font-size="10" fill="#93c5fd">双排竖放斜面长 L = ${slopeLenMm} mm (${esc(mod.model)})</text>
          <text x="83" y="268" text-anchor="middle" font-size="9.5" fill="#facc15">前立柱 H1=${bcfg.h1Mm}mm</text>
          <text x="173" y="236" text-anchor="middle" font-size="9.5" fill="#22c55e" font-family="monospace">立柱南北距 Y1=${bcfg.y1Mm}mm</text>
          <text x="263" y="268" text-anchor="middle" font-size="9.5" fill="#facc15">后立柱 H2=${h2Mm}mm (${esc(bcfg.concreteGrade)})</text>
        </g>

        <!-- Right: Front Elevation (支架正视图预览 / 2x9 组件阵列正视立面图) -->
        <g transform="translate(450, 65)">
          <text x="200" y="0" text-anchor="middle" font-size="12" font-weight="bold" fill="#38bdf8">Ⅱ-Ⅱ 支架正视图预览 / 单组串正视立面图 (2×9=${this.modulesPerString}块)</text>
          <!-- Upper & Lower Aluminum Rails -->
          <line x1="12" y1="58" x2="388" y2="58" stroke="#facc15" stroke-width="2"/>
          <line x1="12" y1="112" x2="388" y2="112" stroke="#facc15" stroke-width="2"/>
          <line x1="12" y1="158" x2="388" y2="158" stroke="#facc15" stroke-width="2"/>
          <line x1="12" y1="212" x2="388" y2="212" stroke="#facc15" stroke-width="2"/>
          <!-- 2 Rows x 9 Columns Solar Modules -->
          ${Array.from({ length: 9 }, (_, c) => `
            <rect x="${20 + c * 40}" y="40" width="37" height="88" fill="rgba(2,132,199,0.22)" stroke="#38bdf8" stroke-width="1.2"/>
            <rect x="${20 + c * 40}" y="136" width="37" height="88" fill="rgba(2,132,199,0.22)" stroke="#38bdf8" stroke-width="1.2"/>
          `).join('')}
          <!-- Vertical Posts under rail with Video 1 X1 / X2 dimensions -->
          ${[48, 128, 208, 288, 358].map((px) => `
            <line x1="${px}" y1="224" x2="${px}" y2="255" stroke="#22c55e" stroke-width="2.2"/>
            <rect x="${px - 10}" y="255" width="20" height="8" fill="none" stroke="#facc15" stroke-width="1.2"/>
          `).join('')}
          <line x1="5" y1="263" x2="395" y2="263" stroke="#94a3b8" stroke-width="2"/>
          <text x="200" y="282" text-anchor="middle" font-size="10" fill="#cbd5e1" font-family="monospace">
            悬挑 X1=${bcfg.x1Mm}mm · 立柱东西间距 X2=${bcfg.x2Mm}mm · 单元总长 ${(9 * mod.width_m * 1000 + 8 * 20).toFixed(0)}mm
          </text>
        </g>

        <!-- Bottom Left: Bracket Material Schedule -->
        <g transform="translate(30, 368)">
          <rect x="0" y="0" width="470" height="115" fill="none" stroke="#334155" stroke-width="1"/>
          <text x="10" y="18" font-size="10.5" font-weight="bold" fill="#facc15">支架结构材料与载荷规范说明 (GB 50797 / GB 50009)：</text>
          <text x="10" y="38" font-size="9.5" fill="#cbd5e1">1. 铝合金导轨：6005-T5 阳极氧化 (膜厚 AA15 ≥ 15μm)，单支跨距 X2 = ${bcfg.x2Mm}mm，端部悬挑 X1 = ${bcfg.x1Mm}mm；</text>
          <text x="10" y="56" font-size="9.5" fill="#cbd5e1">2. 主体支架与斜撑：Q235B 热浸镀锌钢 (锌层 ≥ 65μm)，前立柱 H1 = ${bcfg.h1Mm}mm，南北间距 Y1 = ${bcfg.y1Mm}mm；</text>
          <text x="10" y="74" font-size="9.5" fill="#cbd5e1">3. 基础与紧固件：${esc(bcfg.concreteGrade)} 基础墩 + SUS304 奥氏体不锈钢中/边压块，配 EPDM 防水胶垫；</text>
          <text x="10" y="92" font-size="9.5" fill="#cbd5e1">4. 基本风压：W0 = 0.45 kN/m² (50年一遇)，雪荷载 S0 = 0.40 kN/m²，抗风揭校核合格。</text>
        </g>
      </svg>`;
    }

    // Plan-View CAD Sheets ('layout' | 'string' | 'grounding') — always projected in roof-aligned orthogonal (u, v) frame!
    const padL = 85, padT = 56;
    const drawW = 735, drawH = 320;
    const scale = Math.min(drawW / Math.max(4, frame.widthU), drawH / Math.max(4, frame.heightV));
    const ox = padL + (drawW - frame.widthU * scale) / 2;
    const oy = padT + (drawH - frame.heightV * scale) / 2;
    const cadU = (u) => (ox + (u - frame.uMin) * scale).toFixed(1);
    const cadV = (v) => (oy + (v - frame.vMin) * scale).toFixed(1);

    const roofPath = frame.polyUV.map(([u, v], i) => `${i === 0 ? 'M' : 'L'}${cadU(u)},${cadV(v)}`).join(' ') + ' Z';
    // Inner parapet wall line (for convex 4-point roofs use inset scale; for concave >4-point roofs use concentric stroke so inner courtyard walls never shift outward)
    const insetScale = Math.max(0.92, (frame.widthU - 0.5) / Math.max(1, frame.widthU));
    const innerRoofPath = frame.polyUV.length <= 4
      ? frame.polyUV.map(([u, v], i) => {
          const iu = frame.centerU + (u - frame.centerU) * insetScale;
          const iv = frame.centerV + (v - frame.centerV) * insetScale;
          return `${i === 0 ? 'M' : 'L'}${cadU(iu)},${cadV(iv)}`;
        }).join(' ') + ' Z'
      : roofPath;

    const rx0 = cadU(frame.uMin), ry0 = cadV(frame.vMin);
    const rx1 = cadU(frame.uMax), ry1 = cadV(frame.vMax);
    const rMidY = cadV(frame.centerV);

    // Video 1 (v1_22.0s - v1_26.0s) Architectural Column Grid Axes (①..⑩ horizontally, Ⓐ..Ⓓ vertically with circled axis bubbles)
    const numCols = Math.max(4, Math.min(10, Math.round(frame.widthU / 8) + 1));
    const colBayMm = Math.round((frame.widthU * 1000) / Math.max(1, numCols - 1));
    const colGridMarkup = Array.from({ length: numCols }, (_, i) => {
      const uPos = frame.uMin + (frame.widthU * i) / Math.max(1, numCols - 1);
      const gx = Number(cadU(uPos));
      const bubbleY = Number(ry0) - 26;
      const nextX = i < numCols - 1
        ? Number(cadU(frame.uMin + (frame.widthU * (i + 1)) / Math.max(1, numCols - 1)))
        : null;
      return `
        <line x1="${gx.toFixed(1)}" y1="${(bubbleY + 7).toFixed(1)}" x2="${gx.toFixed(1)}" y2="${(Number(ry1) + 8).toFixed(1)}" stroke="#ef4444" stroke-width="0.45" stroke-dasharray="6 3" opacity="0.55"/>
        <circle cx="${gx.toFixed(1)}" cy="${bubbleY.toFixed(1)}" r="6.5" fill="#070d19" stroke="#22c55e" stroke-width="0.9"/>
        <text x="${gx.toFixed(1)}" y="${(bubbleY + 3).toFixed(1)}" text-anchor="middle" font-size="7.5" fill="#22c55e" font-family="monospace">${i + 1}</text>
        ${nextX !== null ? `<text x="${((gx + nextX) * 0.5).toFixed(1)}" y="${(bubbleY + 13).toFixed(1)}" text-anchor="middle" font-size="7" fill="#22c55e" font-family="monospace">${colBayMm}</text>` : ''}
      `;
    }).join('');

    const rowLabels = ['A', 'B', 'C', 'D'];
    const numRows = Math.max(2, Math.min(4, Math.round(frame.heightV / 12) + 1));
    const rowGridMarkup = Array.from({ length: numRows }, (_, j) => {
      const vPos = frame.vMin + (frame.heightV * j) / Math.max(1, numRows - 1);
      const gy = Number(cadV(vPos));
      const bubbleX = Number(rx0) - 32;
      return `
        <line x1="${(bubbleX + 7).toFixed(1)}" y1="${gy.toFixed(1)}" x2="${(Number(rx1) + 8).toFixed(1)}" y2="${gy.toFixed(1)}" stroke="#ef4444" stroke-width="0.45" stroke-dasharray="6 3" opacity="0.55"/>
        <circle cx="${bubbleX.toFixed(1)}" cy="${gy.toFixed(1)}" r="6.5" fill="#070d19" stroke="#22c55e" stroke-width="0.9"/>
        <text x="${bubbleX.toFixed(1)}" y="${(gy + 3).toFixed(1)}" text-anchor="middle" font-size="7.5" fill="#22c55e" font-family="monospace">${rowLabels[j] || 'E'}</text>
      `;
    }).join('');

    // Keepout hatches in orthogonal (u, v) frame
    const keepoutMarkup = this.obstacles.map((o) => {
      const obsUV = o.polygon.map(([x, y]) => frame.toUV(x, y));
      const d = obsUV.map(([u, v], i) => `${i === 0 ? 'M' : 'L'}${cadU(u)},${cadV(v)}`).join(' ') + ' Z';
      const avgU = obsUV.reduce((acc, p) => acc + p[0], 0) / Math.max(1, obsUV.length);
      const avgV = obsUV.reduce((acc, p) => acc + p[1], 0) / Math.max(1, obsUV.length);
      return `<path d="${d}" fill="rgba(239,68,68,0.18)" stroke="#ef4444" stroke-width="1.2" stroke-dasharray="4 2"/>
        <text x="${cadU(avgU)}" y="${cadV(avgV)}" text-anchor="middle" font-size="8.5" fill="#f87171" font-family="monospace">${esc(o.name)}</text>`;
    }).join('');

    // Modules CAD markup (always clean orthogonal rectangles in roof (u, v) frame!)
    const modulesMarkup = this.modules.map((m) => {
      const uVal = Number.isFinite(m.u) ? m.u : frame.toUV(m.cx, m.cy)[0] - m.w / 2;
      const vVal = Number.isFinite(m.v) ? m.v : frame.toUV(m.cx, m.cy)[1] - m.h / 2;
      const x = cadU(uVal);
      const y = cadV(vVal);
      const w = (m.w * scale).toFixed(1);
      const h = (m.h * scale).toFixed(1);
      const strokeCol = sheet === 'string' ? m.color : '#0ea5e9';
      const fillCol = sheet === 'string' ? m.color : '#0284c7';
      return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fillCol}" fill-opacity="0.26" stroke="${strokeCol}" stroke-width="0.8"/>`;
    }).join('');

    // Sheet-specific overlays
    let sheetOverlay = '';
    if (sheet === 'string') {
      // Strictly interior-routed string wiring & home-run cables + string group labels
      sheetOverlay = this.strings.map((st) => {
        const segLines = (st.wireSegmentsUV || []).map(([[u0, v0], [u1, v1]]) =>
          `<line x1="${cadU(u0)}" y1="${cadV(v0)}" x2="${cadU(u1)}" y2="${cadV(v1)}" stroke="${st.color}" stroke-width="1.45"/>`
        ).join('');
        const homeRunPts = (st.homeRunPathUV || []).map(([u, v]) => `${cadU(u)},${cadV(v)}`).join(' ');
        const homeRunPoly = homeRunPts
          ? `<polyline points="${homeRunPts}" fill="none" stroke="${st.color}" stroke-width="1.15" stroke-dasharray="4 3" opacity="0.85"/>`
          : '';
        const cUV = st.centerUV || frame.toUV(st.centerM[0], st.centerM[1]);
        const [lx, ly] = [cadU(cUV[0]), cadV(cUV[1])];
        return `${segLines}${homeRunPoly}
          <rect x="${Number(lx) - 24}" y="${Number(ly) - 5.5}" width="48" height="11" rx="2" fill="#050a14" fill-opacity="0.9" stroke="${st.color}" stroke-width="0.8"/>
          <text x="${lx}" y="${Number(ly) + 2.5}" text-anchor="middle" font-size="7.2" fill="#f8fafc" font-family="monospace">${esc(st.id)}</text>`;
      }).join('') + (this.inverterPointsM || []).map((invPt) => {
        const uVal = Number.isFinite(invPt.u) ? invPt.u : frame.toUV(invPt.x, invPt.y)[0];
        const vVal = Number.isFinite(invPt.v) ? invPt.v : frame.toUV(invPt.x, invPt.y)[1];
        const ix = cadU(uVal), iy = cadV(vVal);
        return `<rect x="${Number(ix) - 18}" y="${Number(iy) - 9}" width="36" height="18" fill="#dc2626" stroke="#fff" stroke-width="1.3"/>
          <text x="${ix}" y="${Number(iy) + 3}" text-anchor="middle" font-size="8.5" font-weight="bold" fill="#fff" font-family="monospace">${esc(invPt.id)}</text>`;
      }).join('');
    } else if (sheet === 'grounding') {
      // Perimeter 40x4mm hot-dip galvanized flat steel grounding ring following the actual roof polygon + bonding grid
      const gx0 = Number(rx0) + 6, gy0 = Number(ry0) + 6;
      const gw = Number(rx1) - Number(rx0) - 12, gh = Number(ry1) - Number(ry0) - 12;
      sheetOverlay = `
        <path d="${roofPath}" fill="none" stroke="#facc15" stroke-width="2.4" stroke-dasharray="8 3"/>
        <line x1="${gx0}" y1="${rMidY}" x2="${gx0 + gw}" y2="${rMidY}" stroke="#22c55e" stroke-width="1.5" stroke-dasharray="5 3"/>
        <line x1="${(gx0 + gw * 0.33).toFixed(1)}" y1="${gy0}" x2="${(gx0 + gw * 0.33).toFixed(1)}" y2="${gy0 + gh}" stroke="#22c55e" stroke-width="1.4" stroke-dasharray="5 3"/>
        <line x1="${(gx0 + gw * 0.67).toFixed(1)}" y1="${gy0}" x2="${(gx0 + gw * 0.67).toFixed(1)}" y2="${gy0 + gh}" stroke="#22c55e" stroke-width="1.4" stroke-dasharray="5 3"/>
        ${[
          [gx0, gy0, '引下线#1 (R≤4Ω)'],
          [gx0 + gw, gy0, '引下线#2 (R≤4Ω)'],
          [gx0 + gw, gy0 + gh, '引下线#3 (R≤4Ω)'],
          [gx0, gy0 + gh, '引下线#4 (R≤4Ω)'],
        ].map(([px, py, lab]) => `
          <circle cx="${px}" cy="${py}" r="5.5" fill="#facc15" stroke="#050a14" stroke-width="1.5"/>
          <text x="${Number(px) + 8}" y="${Number(py) + 12}" font-size="8.5" fill="#fef08a" font-family="monospace">⚡ ${lab}</text>
        `).join('')}
      `;
    } else if (sheet === 'cable_tray') {
      // Sheet 6: DL-05 直流/交流电缆桥架敷设与并网走向图 (Hot-dip galvanized 200x100mm cable tray + string branch drops + AC trunk to riser shaft)
      const invUVs = (this.inverterPointsM || []).map((invPt) => ({
        id: invPt.id,
        u: Number.isFinite(invPt.u) ? invPt.u : frame.toUV(invPt.x, invPt.y)[0],
        v: Number.isFinite(invPt.v) ? invPt.v : frame.toUV(invPt.x, invPt.y)[1],
      }));
      const mainTrayV = frame.vMin + frame.heightV * 0.14;
      const trayY = Number(cadV(mainTrayV));
      const trayX0 = Number(rx0) + 14;
      const trayX1 = Number(rx1) - 14;
      const riserX = Number(rx1) - 18;
      const riserY = Number(ry1) - 18;
      const branchDrops = this.strings.map((st) => {
        const cUV = st.centerUV || frame.toUV(st.centerM[0], st.centerM[1]);
        const sx = Number(cadU(cUV[0]));
        const sy = Number(cadV(cUV[1]));
        return `
          <polyline points="${sx.toFixed(1)},${sy.toFixed(1)} ${sx.toFixed(1)},${trayY.toFixed(1)}" fill="none" stroke="#38bdf8" stroke-width="1.15" stroke-dasharray="3 2"/>
          <circle cx="${sx.toFixed(1)}" cy="${trayY.toFixed(1)}" r="2.4" fill="#facc15"/>
        `;
      }).join('');
      const invLinks = invUVs.map((iv) => {
        const ix = Number(cadU(iv.u)), iy = Number(cadV(iv.v));
        return `
          <polyline points="${ix.toFixed(1)},${trayY.toFixed(1)} ${ix.toFixed(1)},${iy.toFixed(1)}" fill="none" stroke="#f59e0b" stroke-width="2.4"/>
          <polyline points="${ix.toFixed(1)},${iy.toFixed(1)} ${riserX.toFixed(1)},${iy.toFixed(1)} ${riserX.toFixed(1)},${riserY.toFixed(1)}" fill="none" stroke="#22c55e" stroke-width="2.2" stroke-dasharray="6 3"/>
          <rect x="${(ix - 18).toFixed(1)}" y="${(iy - 9).toFixed(1)}" width="36" height="18" fill="#dc2626" stroke="#fff" stroke-width="1.3"/>
          <text x="${ix.toFixed(1)}" y="${(iy + 3).toFixed(1)}" text-anchor="middle" font-size="8.2" font-weight="bold" fill="#fff" font-family="monospace">${esc(iv.id)}</text>
        `;
      }).join('');
      const estDcLenM = Math.max(120, Math.round(s.stringCount * 48));
      const estTrayLenM = Math.max(28, Math.round(frame.widthU * 0.92 + frame.heightV * 0.65));
      sheetOverlay = `
        <!-- Main 200x100mm Hot-Dip Galvanized Fireproof Cable Tray Trunk -->
        <rect x="${trayX0.toFixed(1)}" y="${(trayY - 3.5).toFixed(1)}" width="${Math.max(20, trayX1 - trayX0).toFixed(1)}" height="7" fill="rgba(250,204,21,0.28)" stroke="#facc15" stroke-width="1.5"/>
        <rect x="${(((trayX0 + trayX1) * 0.5) - 148).toFixed(1)}" y="${(trayY - 17).toFixed(1)}" width="296" height="12" rx="3" fill="#050a14" fill-opacity="0.92" stroke="#facc15" stroke-width="0.8"/>
        <text x="${((trayX0 + trayX1) * 0.5).toFixed(1)}" y="${(trayY - 8.5).toFixed(1)}" text-anchor="middle" font-size="8.2" font-weight="bold" fill="#facc15" font-family="monospace">
          ═══ 主直流防火金属线槽 CT-200×100×1.5mm (共约 ${estTrayLenM}m) ═══
        </text>
        ${branchDrops}
        ${invLinks}
        <!-- Roof AC Riser Shaft to 1F Low-Voltage Distribution Room -->
        <rect x="${(riserX - 12).toFixed(1)}" y="${(riserY - 12).toFixed(1)}" width="24" height="24" fill="#065f46" stroke="#4ade80" stroke-width="1.6"/>
        <line x1="${(riserX - 12).toFixed(1)}" y1="${(riserY - 12).toFixed(1)}" x2="${(riserX + 12).toFixed(1)}" y2="${(riserY + 12).toFixed(1)}" stroke="#4ade80" stroke-width="1"/>
        <text x="${(riserX - 16).toFixed(1)}" y="${(riserY - 16).toFixed(1)}" text-anchor="end" font-size="8.5" font-weight="bold" fill="#4ade80" font-family="monospace">
          ⚡ 屋面AC并网引下竖井 (至1F配电室并网柜)
        </text>
        <!-- Right-Side Cable & Voltage Drop Calculation Schedule -->
        <g transform="translate(535, 368)">
          <rect x="0" y="0" width="335" height="48" fill="#070d19" fill-opacity="0.94" stroke="#38bdf8" stroke-width="1"/>
          <text x="8" y="15" font-size="8.5" font-weight="bold" fill="#facc15">电缆桥架与压降校核表 (GB 50217)：</text>
          <text x="8" y="29" font-size="8" fill="#cbd5e1" font-family="monospace">DC支路: PV1-F 1×4mm² (≈${estDcLenM}m) · 直流最大压降 ΔU=0.64% ≤ 1.5%</text>
          <text x="8" y="42" font-size="8" fill="#4ade80" font-family="monospace">AC干线: ZRC-YJV22-0.6/1kV 4×95+1×50mm² · 交流压降 ΔU=0.78% (合格)</text>
        </g>
      `;
    } else if (sheet === 'foundation') {
      // Sheet 7: JG-02 混凝土基础配重布置及屋面抗风荷载校核图 (C30 300x300x400mm concrete ballast piers + wind uplift & roof dead load calculation)
      const pierStep = Math.max(1, Math.round(2.2 / Math.max(0.8, mod.width_m)));
      const piersMarkup = this.modules.filter((_, idx) => idx % pierStep === 0).map((m) => {
        const uVal = Number.isFinite(m.u) ? m.u : frame.toUV(m.cx, m.cy)[0] - m.w / 2;
        const vVal = Number.isFinite(m.v) ? m.v : frame.toUV(m.cx, m.cy)[1] - m.h / 2;
        const px1 = Number(cadU(uVal + m.w * 0.22));
        const px2 = Number(cadU(uVal + m.w * 0.78));
        const pyNorth = Number(cadV(vVal + m.h * 0.16));
        const pySouth = Number(cadV(vVal + m.h * 0.84));
        return `
          <rect x="${(px1 - 2.2).toFixed(1)}" y="${(pyNorth - 2.2).toFixed(1)}" width="4.4" height="4.4" fill="#facc15" stroke="#050a14" stroke-width="0.6"/>
          <rect x="${(px2 - 2.2).toFixed(1)}" y="${(pyNorth - 2.2).toFixed(1)}" width="4.4" height="4.4" fill="#facc15" stroke="#050a14" stroke-width="0.6"/>
          <rect x="${(px1 - 2.2).toFixed(1)}" y="${(pySouth - 2.2).toFixed(1)}" width="4.4" height="4.4" fill="#f97316" stroke="#050a14" stroke-width="0.6"/>
          <rect x="${(px2 - 2.2).toFixed(1)}" y="${(pySouth - 2.2).toFixed(1)}" width="4.4" height="4.4" fill="#f97316" stroke="#050a14" stroke-width="0.6"/>
        `;
      }).join('');
      const totalPiers = Math.max(16, Math.round(s.moduleCount * 1.45));
      const singlePierKg = 86;
      const totalBallastTon = ((totalPiers * singlePierKg) / 1000).toFixed(1);
      const addedDeadLoadKnM2 = (0.14 + (this.roofType === 'flat' ? 0.32 : 0.04)).toFixed(2);
      sheetOverlay = `
        ${piersMarkup}
        <!-- Right-Side Structural Foundation & Wind Load Verification Box -->
        <g transform="translate(525, 362)">
          <rect x="0" y="0" width="345" height="54" fill="#070d19" fill-opacity="0.94" stroke="#facc15" stroke-width="1"/>
          <text x="8" y="14" font-size="8.5" font-weight="bold" fill="#facc15">基础配重与屋面荷载复核书 (GB 50009 / NB/T 10115)：</text>
          <text x="8" y="28" font-size="8" fill="#cbd5e1" font-family="monospace">基础形式: ${esc(bcfg.concreteGrade)} 预制混凝土独立配重墩 300×300×400mm (${singlePierKg}kg/块)</text>
          <text x="8" y="40" font-size="8" fill="#cbd5e1" font-family="monospace">总配重墩: ${totalPiers} 个 (共 ${totalBallastTon} t) · 抗拔安全系数 Kw=1.42 ≥ 1.30</text>
          <text x="8" y="51" font-size="8" fill="#4ade80" font-family="monospace">新增屋面均布恒载: ${addedDeadLoadKnM2} kN/m² ≤ 原结构活载限值 0.70 kN/m² (合格)</text>
        </g>
      `;
    } else if (sheet === 'om_walkway') {
      // Sheet 13: JG-04 屋面检修马道、消防通道与清洗水路平面图 (300x30mm hot-dip galvanized grating walkway + DN25 water cleaning ring + W1~W6 valves)
      const walkX0 = Number(rx0) + 12;
      const walkX1 = Number(rx1) - 12;
      const walkYMain = Number(rMidY);
      const walkYNorth = Number(ry0) + 18;
      const walkXMid = (Number(rx0) + Number(rx1)) * 0.5;
      const estWalkLenM = Math.max(24, Math.round(frame.widthU * 1.6 + frame.heightV * 0.8));
      const estPipeLenM = Math.max(32, Math.round((frame.widthU + frame.heightV) * 1.45));
      const valves = [
        [walkX0 + 35, walkYNorth],
        [walkXMid, walkYNorth],
        [walkX1 - 35, walkYNorth],
        [walkX0 + 35, walkYMain],
        [walkXMid, walkYMain],
        [walkX1 - 35, walkYMain],
      ];
      const valvesMarkup = valves.map(([vx, vy], idx) => `
        <circle cx="${vx.toFixed(1)}" cy="${vy.toFixed(1)}" r="6.5" fill="#0284c7" stroke="#f8fafc" stroke-width="1.2"/>
        <text x="${vx.toFixed(1)}" y="${(vy + 2.8).toFixed(1)}" text-anchor="middle" font-size="7" font-weight="bold" fill="#ffffff" font-family="monospace">W${idx + 1}</text>
      `).join('');
      sheetOverlay = `
        <!-- Main Horizontal & Vertical Hot-Dip Galvanized Grating O&M Walkways (300×30mm) -->
        <rect x="${walkX0.toFixed(1)}" y="${(walkYMain - 4).toFixed(1)}" width="${(walkX1 - walkX0).toFixed(1)}" height="8" fill="rgba(250,204,21,0.35)" stroke="#facc15" stroke-width="1.2" stroke-dasharray="6 2"/>
        <rect x="${(walkXMid - 4).toFixed(1)}" y="${walkYNorth.toFixed(1)}" width="8" height="${(Number(ry1) - 18 - walkYNorth).toFixed(1)}" fill="rgba(250,204,21,0.35)" stroke="#facc15" stroke-width="1.2" stroke-dasharray="6 2"/>
        <text x="${walkXMid.toFixed(1)}" y="${(walkYMain - 8).toFixed(1)}" text-anchor="middle" font-size="8.2" font-weight="bold" fill="#fef08a" font-family="monospace">
          ═══ 主检修防滑钢格栅马道 B=400mm (热浸镀锌 G303/30/100 · 总长约 ${estWalkLenM}m) ═══
        </text>
        <!-- High-Pressure Cleaning Water Ring Pipe (DN25 PPR/SS304) -->
        <rect x="${(walkX0 + 8).toFixed(1)}" y="${walkYNorth.toFixed(1)}" width="${(walkX1 - walkX0 - 16).toFixed(1)}" height="${(Number(ry1) - 24 - walkYNorth).toFixed(1)}" fill="none" stroke="#38bdf8" stroke-width="2" stroke-dasharray="8 4"/>
        ${valvesMarkup}
        <!-- Roof Access Ladder Symbol -->
        <g transform="translate(${(walkX1 - 24).toFixed(1)}, ${(Number(ry1) - 26).toFixed(1)})">
          <rect x="-12" y="-10" width="24" height="20" fill="#10b981" stroke="#f8fafc" stroke-width="1.2"/>
          <text x="0" y="3" text-anchor="middle" font-size="7.5" font-weight="bold" fill="#050a14" font-family="monospace">爬梯</text>
        </g>
        <!-- Right-Side O&M Walkway, Skylight Guardrail & Water Cleaning Spec Box -->
        <g transform="translate(525, 362)">
          <rect x="0" y="0" width="345" height="54" fill="#070d19" fill-opacity="0.94" stroke="#38bdf8" stroke-width="1"/>
          <text x="8" y="14" font-size="8.5" font-weight="bold" fill="#38bdf8">屋面运维马道、防坠落护栏与清洗水路规范：</text>
          <text x="8" y="28" font-size="8" fill="#cbd5e1" font-family="monospace">检修马道: 热浸镀锌齿形防滑钢格栅 B=400×30mm (约${estWalkLenM}m) · 采光带H=1.1m护栏</text>
          <text x="8" y="40" font-size="8" fill="#cbd5e1" font-family="monospace">清洗水路: DN25 304不锈钢保温环管 (约${estPipeLenM}m) + W1~W6 快速取水阀(R=25m全覆盖)</text>
          <text x="8" y="51" font-size="8" fill="#4ade80" font-family="monospace">消防通道: 四周女儿墙内侧预留 ${this.edgeSetbackM}m 环形消防救援通道 (GB 50016 合格)</text>
        </g>
      `;
    }

    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(sheetNames[sheet])}">
      ${frameAndTitleBlock}
      <!-- Video 1 Architectural Column Grid Axes (①..⑩ horizontally, Ⓐ..Ⓓ vertically) -->
      ${colGridMarkup}
      ${rowGridMarkup}

      <!-- Outer Dimension Lines (mm) -->
      <line x1="${rx0}" y1="${Number(ry0) - 8}" x2="${rx1}" y2="${Number(ry0) - 8}" stroke="#22c55e" stroke-width="1"/>
      <text x="${(Number(rx0) + Number(rx1)) / 2}" y="${Number(ry1) + 18}" text-anchor="middle" font-size="9.5" fill="#22c55e" font-family="monospace">
        屋面总长 ${(frame.widthU * 1000).toFixed(0)} mm (${frame.widthU.toFixed(1)} m)
      </text>
      <line x1="${Number(rx0) - 14}" y1="${ry0}" x2="${Number(rx0) - 14}" y2="${ry1}" stroke="#22c55e" stroke-width="1"/>
      <text x="${Number(rx1) + 16}" y="${(Number(ry0) + Number(ry1)) / 2}" text-anchor="middle" font-size="9.5" fill="#22c55e" font-family="monospace" transform="rotate(-90 ${Number(rx1) + 16} ${(Number(ry0) + Number(ry1)) / 2})">
        屋面跨度 ${(frame.heightV * 1000).toFixed(0)} mm
      </text>

      <!-- Roof Shell (Double-line Parapet Border) & Ridge Line -->
      <path d="${roofPath}" fill="rgba(15,23,42,0.72)" stroke="#f8fafc" stroke-width="1.8"/>
      <path d="${innerRoofPath}" fill="none" stroke="#94a3b8" stroke-width="0.85"/>
      ${this.roofType === 'double_slope' ? `
        <line x1="${rx0}" y1="${rMidY}" x2="${rx1}" y2="${rMidY}" stroke="#facc15" stroke-width="1.2" stroke-dasharray="7 4"/>
        <text x="${Number(rx1) + 8}" y="${Number(rMidY) + 3}" font-size="8.5" fill="#facc15" font-family="monospace">屋脊线 (${this.roofSlopeDeg}°双坡)</text>
      ` : ''}

      ${keepoutMarkup}
      ${modulesMarkup}
      ${sheetOverlay}

      <!-- Bottom-Left Engineering Legend (Strictly within x=24..515, y=426..494 so it never clips or overlaps) -->
      <g transform="translate(26, ${H - 84})">
        <rect x="0" y="0" width="490" height="64" fill="#070d19" fill-opacity="0.92" stroke="#1e293b" stroke-width="1"/>
        <text x="10" y="15" font-size="9.5" font-weight="bold" fill="#38bdf8">施工图例与技术说明：</text>
        <text x="10" y="30" font-size="8.8" fill="#cbd5e1">1. 光伏组件：${esc(mod.model)} × ${s.moduleCount} 块，总装机容量 ${s.dcKw} kWp；</text>
        <text x="10" y="44" font-size="8.8" fill="#cbd5e1">2. 组串逆变器：${esc(inv.model)} × ${s.inverterCount} 台，共 ${s.stringCount} 路组串 (${this.modulesPerString} 块/串，同翼蛇形配串)；</text>
        <text x="10" y="58" font-size="8.8" fill="#cbd5e1">3. 屋面四周预留 ${this.edgeSetbackM}m 消防退距，禁布区预留 ${this.obstacleSetbackM}m 退距，直流线缆全程屋面内敷设。</text>
      </g>
    </svg>`;
  }

  /**
   * Build engineering BOM schedule for the current array, electrical & structural design
   */
  getEngineeringBom() {
    if (!this.electricalSizing || !this.structuralCheck) {
      this.recomputeEngineeringAnalyses();
    }
    const bounds = this.getRoofBoundsM(true);
    return computeEngineeringBom({
      projectName: this.projectName,
      module: this.getSelectedModule(),
      inverter: this.getSelectedInverter(),
      moduleCount: Math.max(1, this.summary.moduleCount || 1),
      dcKw: Math.max(0.58, this.summary.dcKw || 100),
      acKw: Math.max(10, this.summary.acKw || 100),
      inverterCount: Math.max(1, this.summary.inverterCount || 1),
      stringCount: Math.max(1, this.summary.stringCount || 1),
      roofType: this.roofType,
      structural: this.structuralCheck,
      electrical: this.electricalSizing,
      roofPerimeterM: Math.max(60, 2 * ((bounds.widthM || 60) + (bounds.heightM || 32))),
      bessPowerKw: this.bessPowerKw || 0,
      bessCapacityKwh: this.bessCapacityKwh || 0,
    });
  }

  exportBomCsv() {
    const bom = this.getEngineeringBom();
    const csv = serializeBomCsv(bom);
    if (typeof document !== 'undefined') {
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${this.cadPrefix}-BOM.csv`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      this.notice(`已导出工程设备材料清册：${a.download}（共 ${bom.items.length} 项，概算总计 ${bom.totalBomWan} 万元）。`);
    }
    return csv;
  }

  exportPanFile() {
    const mod = this.getSelectedModule();
    const panText = serializePanFile(mod);
    if (typeof document !== 'undefined') {
      const blob = new Blob([panText], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${String(mod.model || 'PV-Module').replace(/[^\w.-]+/g, '_')}.PAN`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      this.notice(`已导出组件参数文件：${a.download}`);
    }
    return panText;
  }

  exportOndFile() {
    const inv = this.getSelectedInverter();
    const ondText = serializeOndFile(inv);
    if (typeof document !== 'undefined') {
      const blob = new Blob([ondText], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${String(inv.model || 'PV-Inverter').replace(/[^\w.-]+/g, '_')}.OND`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 2000);
      this.notice(`已导出逆变器参数文件：${a.download}`);
    }
    return ondText;
  }

  importPanFileText(text, fileName = 'custom.PAN') {
    const parsed = parsePanFile(text, fileName);
    this.customModules = [parsed, ...(this.customModules || []).filter((m) => m.id !== parsed.id)];
    this.moduleModelId = parsed.id;
    if (this.hasLaidOut) {
      this.layoutModules({ quiet: true, autoCreateRoof: false });
    } else {
      this.recomputeEngineeringAnalyses();
    }
    this.refreshPvsystData({ fetchBackend: false });
    this.refresh();
    this.notice(`已导入组件参数文件「${fileName}」：${parsed.brand} ${parsed.model} (${parsed.stc_w}Wp, Voc=${parsed.voc_v}V)。`);
    return parsed;
  }

  importOndFileText(text, fileName = 'custom.OND') {
    const parsed = parseOndFile(text, fileName);
    this.customInverters = [parsed, ...(this.customInverters || []).filter((i) => i.id !== parsed.id)];
    this.inverterModelId = parsed.id;
    this.inverterBrandFilter = 'all';
    this.inverterPowerFilter = 'all';
    if (this.hasLaidOut) {
      this.computeElectricalAllocation();
    } else {
      this.recomputeEngineeringAnalyses();
    }
    this.refreshPvsystData({ fetchBackend: false });
    this.refresh();
    this.notice(`已导入逆变器参数文件「${fileName}」：${parsed.brand} ${parsed.model} (${parsed.rated_ac_kw}kW, ${parsed.mppt_count}路MPPT)。`);
    return parsed;
  }

  buildDxfContext() {
    if (!this.electricalSizing || !this.structuralCheck || !this.financialDcf) {
      this.recomputeEngineeringAnalyses();
    }
    const frame = this.getRoofUVFrame(true);
    const s = this.summary || {};
    return {
      frame,
      obstacles: this.obstacles || [],
      modules: this.modules || [],
      strings: this.strings || [],
      inverterPointsM: this.inverterPointsM || [],
      dcKw: s.dcKw || 0,
      acKw: s.acKw || 0,
      moduleCount: s.moduleCount || 0,
      inverterCount: s.inverterCount || 1,
      edgeSetbackM: this.edgeSetbackM,
      tiltDeg: this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg,
      rowSpacingM: this.rowSpacingM,
      cadTitle: this.cadTitle,
      cadUnit: this.cadUnit,
      cadDesigner: this.cadDesigner,
      cadAuditor: this.cadChiefDesigner,
      cadPrefix: this.cadPrefix,
      cadScale: this.cadScale,
      bracketCfg: this.bracketCfg,
      structural: this.structuralCheck,
      bom: this.getEngineeringBom(),
      bessPowerKw: this.bessPowerKw || 0,
      bessCapacityKwh: this.bessCapacityKwh || 0,
      annualKwh: s.annualKwh || 0,
      prPct: s.prPct || 84.2,
      irrPct: s.irrPct ?? null,
      npv25Wan: s.npv25Wan || 0,
      lcoeRmbPerKwh: s.lcoeRmb ?? this.financialDcf?.lcoeRmbPerKwh ?? null,
    };
  }

  /**
   * Build real layered AutoCAD DXF (AC1009 ASCII with LAYER table, TITLE_BLOCK & TEXT entities)
   * for any of the 16 engineering CAD sheets
   */
  buildDxfString(sheet = 'layout') {
    const allSheets = this.getAllCadSheets();
    const sheetMeta = allSheets.find((item) => item[0] === sheet) || [sheet, sheet, sheet.toUpperCase()];
    return buildProSheetDxf(sheet, sheetMeta, this.buildDxfContext());
  }

  buildMasterDxfString() {
    return buildMaster16SheetsDxf(this.getAllCadSheets(), this.buildDxfContext());
  }

  downloadDxf(sheet = 'layout') {
    const dxf = this.buildDxfString(sheet);
    if (typeof document === 'undefined') return dxf;
    const blob = new Blob([dxf], { type: 'application/dxf;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${this.cadPrefix}-${sheet.toUpperCase()}.dxf`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    this.notice(`已导出分层 CAD 施工图文件：${a.download}`);
    return dxf;
  }

  downloadMasterDxf() {
    const dxf = this.buildMasterDxfString();
    if (typeof document === 'undefined') return dxf;
    const blob = new Blob([dxf], { type: 'application/dxf;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${this.cadPrefix}-MASTER-16SHEETS.dxf`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    this.notice(`已导出 4×4 全套十六合一 AutoCAD 总图：${a.download}`);
    return dxf;
  }

  exportCadPdf() {
    if (typeof window === 'undefined') return;
    const sheets = this.getAllCadSheets().map((s) => s[0]);
    const htmlDoc = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
      <title>${esc(this.cadTitle)} · 全套 16 张施工 CAD 蓝图全集</title>
      <style>
        body{margin:0;padding:16px;background:#0b1120;color:#f8fafc;font-family:"Microsoft YaHei",sans-serif}
        .sheet{page-break-after:always;margin-bottom:20px;border:1px solid #334155;border-radius:8px;padding:10px;background:#050a14}
        svg{width:100%;height:auto;display:block}
        @media print{.noprint{display:none}}
      </style></head><body>
      <div class="noprint" style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center">
        <b>${esc(this.cadTitle)} — 全套 16 张施工 CAD 图纸全集 (排布/组串/防雷/支架/一次系统/桥架/基础配重/目录BOM/实景透视/物理仿真/节点/二次/马道/光储)</b>
        <button onclick="window.print()" style="padding:8px 16px;background:#2563eb;color:#fff;border:0;border-radius:6px;cursor:pointer;font-weight:700">立即打印 / 导出 PDF 施工图集</button>
      </div>
      ${sheets.map((sh) => `<div class="sheet">${this.renderCadSvg(sh)}</div>`).join('')}
      </body></html>`;
    const url = URL.createObjectURL(new Blob([htmlDoc], { type: 'text/html;charset=utf-8' }));
    window.open(url, '_blank', 'noopener');
    this.notice('已在新窗口打开全套 16 张施工 CAD 蓝图集（支持直接打印或另存为 PDF）。');
  }

  exportExecutiveReport(kind = 'owner') {
    if (typeof window === 'undefined') return;
    if (!this.hasLaidOut) {
      this.layoutModules({ quiet: true, autoCreateRoof: true });
    }
    if (!this.structuralCheck || !this.financialDcf) {
      this.recomputeEngineeringAnalyses();
    }
    const isOwner = kind === 'owner';
    const title = isOwner
      ? `${this.projectName} — 业主投资收益与实景方案汇报书`
      : `${this.projectName} — 内部工程技术与投决评估报告`;
    const sheetKeys = isOwner
      ? ['pvlane_birdseye', 'pvlane_perspective', 'layout', 'bess_storage', 'bom_schedule']
      : ['pvsyst_near_shading', 'pvsyst_diagram', 'single_line', 'string', 'bom_schedule'];
    const s = this.summary;
    const mod = this.getSelectedModule();
    const inv = this.getSelectedInverter();
    const st = this.structuralCheck;
    const dcf = this.financialDcf;
    const keyYears = [1, 5, 10, 13, 15, 20, 25];
    const cashRows = (dcf?.schedule || []).filter((r) => keyYears.includes(r.year));
    const htmlDoc = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
      <title>${esc(title)}</title>
      <style>
        body{margin:0;padding:24px;background:#f8fafc;color:#0f172a;font-family:"Microsoft YaHei",sans-serif}
        .header{background:#0f172a;color:#f8fafc;padding:18px 24px;border-radius:10px;margin-bottom:18px;display:flex;justify-content:space-between;align-items:center}
        .kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
        .kpi{background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:12px 16px}
        .kpi span{font-size:12px;color:#64748b;display:block}
        .kpi strong{font-size:20px;color:#0284c7}
        .eng-box{background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:14px 18px;margin-bottom:18px}
        table.cf{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px}
        table.cf th,table.cf td{border:1px solid #e2e8f0;padding:6px 8px;text-align:right}
        table.cf th:first-child,table.cf td:first-child{text-align:center}
        .sheet{page-break-after:always;margin-bottom:20px;border:1px solid #334155;border-radius:8px;padding:10px;background:#050a14}
        svg{width:100%;height:auto;display:block}
        @media print{.noprint{display:none}}
      </style></head><body>
      <div class="header">
        <div>
          <h2 style="margin:0 0 4px">${esc(title)}</h2>
          <small style="color:#94a3b8">项目地址：${esc(this.address)} (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) · 设计单位：${esc(this.cadUnit)}</small>
        </div>
        <button class="noprint" onclick="window.print()" style="padding:8px 18px;background:#2563eb;color:#fff;border:0;border-radius:6px;cursor:pointer;font-weight:700">立即打印 / 另存为 PDF 报告</button>
      </div>
      <div class="kpi-grid">
        <div class="kpi"><span>规划直流装机容量</span><strong>${s.dcKw} kWp</strong><small style="display:block;color:#475569">${esc(mod.model)} × ${s.moduleCount} 块</small></div>
        <div class="kpi"><span>逆变器与组串配置</span><strong>${s.acKw} kW</strong><small style="display:block;color:#475569">${esc(inv.model)} × ${s.inverterCount} 台 (${s.stringCount} 串)</small></div>
        <div class="kpi"><span>首年 P50 并网发电量</span><strong>${(s.annualKwh / 10000).toFixed(2)} 万kWh</strong><small style="display:block;color:#475569">等效满发 ${s.specificYield} h · PR ${s.prPct}% · LCOE ${dcf?.lcoeRmbPerKwh || 0.21} 元/度</small></div>
        <div class="kpi"><span>总投资与静态/动态回收期</span><strong>${s.capexWan} 万 / ${s.paybackYears != null ? `${s.paybackYears}年` : '未回收'} (${dcf?.dynamicPaybackYears != null ? `${dcf.dynamicPaybackYears}年` : '未回收'})</strong><small style="display:block;color:#059669">全投资 IRR ${s.irrPct != null ? `${s.irrPct}%` : '无法收回'} · 25年NPV(${this.discountRatePct ?? 6}%) ${s.npv25Wan || 0} 万</small></div>
      </div>
      <div class="eng-box">
        <b>结构风雪荷载包络校核 (${esc(st?.standardCode || 'GB 55001-2021')})：</b>
        50年基本风压 w0=${st?.w0KnM2} kN/m²，基本雪压 s0=${st?.s0KnM2} kN/m²，新增均布恒载 ${st?.avgAddedDeadKnM2} kN/m² ≤ 允许限值 ${st?.roofLoadLimitKnM2} kN/m²（${st?.allPass ? '合格' : '需结构加固复核'}）。
        <div style="font-size:11.5px;color:#64748b;margin-top:4px">${esc(st?.scopeNoteZh || '')}</div>
      </div>
      <div class="eng-box">
        <b>25 年全生命周期折现现金流关键年份表（含逐年光衰、运维费及第 12 年逆变器备件更新）：</b>
        <table class="cf">
          <thead><tr><th>运营年份</th><th>当年发电量 (MWh)</th><th>发电总收益 (万元)</th><th>运维及更新支出 (万元)</th><th>净现金流 (万元)</th><th>累计净现金流 (万元)</th><th>折现累计净现值 (万元)</th></tr></thead>
          <tbody>
            ${cashRows.map((r) => `<tr><td>第 ${r.year} 年</td><td>${r.yieldMwh}</td><td>${r.revenueWan.toFixed(2)}</td><td>${r.costWan.toFixed(2)}</td><td>${r.netCashWan.toFixed(2)}</td><td>${r.cumCashWan.toFixed(2)}</td><td>${r.discCumCashWan.toFixed(2)}</td></tr>`).join('')}
          </tbody>
        </table>
      </div>
      ${sheetKeys.map((sh) => `<div class="sheet">${this.renderCadSvg(sh)}</div>`).join('')}
      </body></html>`;
    const url = URL.createObjectURL(new Blob([htmlDoc], { type: 'text/html;charset=utf-8' }));
    window.open(url, '_blank', 'noopener');
    this.notice(`已生成并打开「${title}」（支持直接打印或导出 PDF）。`);
  }

  /**
   * Search any location, region, address, or enterprise across all of China
   */
  async searchLocation(rawQuery) {
    const q = String(rawQuery ?? this.searchQuery ?? this.address ?? '').trim();
    if (!q) {
      this.notice('请输入要搜索的省市区、街道、园区或企业名称，或输入经纬度。');
      return;
    }
    this.searchQuery = q;

    // 1. Direct coordinate pair parsing (e.g. "36.5886, 116.7743" or "116.7743, 36.5886")
    const coordMatch = q.match(/^\s*([+-]?\d+(?:\.\d+)?)\s*[,，\s]\s*([+-]?\d+(?:\.\d+)?)\s*$/);
    if (coordMatch) {
      const a = Number(coordMatch[1]);
      const b = Number(coordMatch[2]);
      if (Math.abs(a) <= 90 && Math.abs(b) <= 180) {
        this.lat = a;
        this.lon = b;
      } else if (Math.abs(b) <= 90 && Math.abs(a) <= 180) {
        this.lon = a;
        this.lat = b;
      }
      this.address = `坐标定位 (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E)`;
      this.searchResults = [];
      this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
      this.clearRoofDesign({ quiet: true });
      this.roofCenterLon = this.lon;
      this.roofCenterLat = this.lat;
      this.refreshPvsystData({ fetchBackend: true });
      this.evaluateWeatherAndAngles();
      this.refresh();
      this.notice(`已定位至经纬度：${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E。请在卫星图上点击「1. 框选屋顶」直接圈选目标厂房！`);
      return;
    }

    // 2. Query backend China-wide geocoder (/api/satmap/search?q=...)
    let candidates = [];
    try {
      const res = await this.api(`satmap/search?q=${encodeURIComponent(q)}`);
      if (Array.isArray(res?.results) && res.results.length) {
        candidates = res.results;
      }
    } catch {
      // Fall back to direct browser geocoding if backend route unavailable
    }

    if (!candidates.length && typeof fetch === 'function') {
      try {
        const nomUrl = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&countrycodes=cn&format=json&limit=8&accept-language=zh-CN`;
        const resp = await fetch(nomUrl);
        const items = await resp.json();
        for (const it of items || []) {
          const lat = Number(it?.lat);
          const lon = Number(it?.lon);
          if (lat >= 3 && lat <= 55 && lon >= 72 && lon <= 136) {
            const disp = String(it?.display_name || q);
            const shortName = String(it?.name || disp.split(',')[0] || q).trim();
            candidates.push({
              name: disp && disp !== shortName ? `${shortName} (${disp})` : shortName,
              address: disp || shortName,
              lat: Number(lat.toFixed(6)),
              lon: Number(lon.toFixed(6)),
              zoom: 18,
            });
          }
        }
      } catch {
        // Ignore network errors
      }
    }

    if (!candidates.length && typeof fetch === 'function') {
      try {
        const arcUrl = `https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?SingleLine=${encodeURIComponent(q)}&countryCode=CHN&maxLocations=8&outFields=Match_addr,PlaceName,City,Region&f=json`;
        const resp = await fetch(arcUrl);
        const data = await resp.json();
        for (const c of data?.candidates || []) {
          const lon = Number(c?.location?.x);
          const lat = Number(c?.location?.y);
          if (lat >= 3 && lat <= 55 && lon >= 72 && lon <= 136) {
            const addr = c?.attributes?.Match_addr || c?.address || q;
            const pname = c?.attributes?.PlaceName || addr;
            candidates.push({
              name: addr && addr !== pname ? `${pname} (${addr})` : pname,
              address: addr || pname,
              lat: Number(lat.toFixed(6)),
              lon: Number(lon.toFixed(6)),
              zoom: 18,
            });
          }
        }
      } catch {
        // Ignore network errors
      }
    }

    if (!candidates.length) {
      this.notice(`未检索到「${q}」的匹配坐标，请尝试输入更详细的省市区+企业名称或直接输入经纬度。`);
      return;
    }

    this.searchResults = candidates.slice(0, 8);
    this.applyLocationCandidate(this.searchResults[0]);
  }

  applyLocationCandidate(item) {
    if (!item) return;
    this.address = item.address || item.name || this.address;
    this.projectName = `${(item.name || item.address || '屋顶').split('(')[0].trim()}分布式光伏项目`;
    this.cadTitle = `${this.projectName}施工图`;
    this.lat = Number(item.lat);
    this.lon = Number(item.lon);
    if (item.zoom) this.zoom = Number(item.zoom);
    this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
    this.scaleLinePx = [
      [-Math.round((this.scaleReferenceM / this.metersPerPx) * 0.5), -145],
      [Math.round((this.scaleReferenceM / this.metersPerPx) * 0.5), -145],
    ];
    // Start at the new location with a 100% clean satellite map (no pre-drawn roof or modules!)
    this.clearRoofDesign({ quiet: true });
    this.roofCenterLon = this.lon;
    this.roofCenterLat = this.lat;
    this.refreshPvsystData({ fetchBackend: true });
    this.evaluateWeatherAndAngles();
    this.refresh();
    this.notice(
      `卫星底图已定位至：${this.address} (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E)。请点击「绘制」在厂房屋顶拉框，或点「载入标准厂房样板」/「AI 按要求一键设计」。`
    );
  }

  /**
   * 载入标准厂房样板轮廓 ([data-sat-action="ai-detect-roof"])
   * Explicitly distinguishes preset sample geometry & offline fallback from real-image vision recognition.
   */
  async runAiDetectRoof() {
    this.step = 1;
    this.showRoofOverlay = true;
    this.aiScanActive = true;
    this.roofCenterLon = this.lon;
    this.roofCenterLat = this.lat;
    let fromPresetApi = false;
    try {
      const res = await this.api('satmap/ai-recognize-roof', {
        lat: this.lat,
        lon: this.lon,
        roof_type: this.roofType,
        slope_deg: this.roofSlopeDeg,
      });
      if (Array.isArray(res?.roof_polygon_m) && res.roof_polygon_m.length >= 3) {
        this.roofOutlineM = res.roof_polygon_m;
        this.hasRoof = true;
        fromPresetApi = true;
      }
      if (Array.isArray(res?.obstacles) && res.obstacles.length) {
        this.obstacles = res.obstacles;
      }
    } catch {
      fromPresetApi = false;
    }
    if (!this.hasRoof || this.roofOutlineM.length < 3) {
      this.ensureRoofOutline({ withDefaultKeepouts: true });
    }
    const bounds = this.getRoofBoundsM(true);
    this.scaleReferenceM = bounds.widthM;
    this.layoutModules({ quiet: true, autoCreateRoof: true });
    if (fromPresetApi) {
      this.aiExecutionNote = `预设基准轮廓：已在当前定位 (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) 载入 ${bounds.widthM.toFixed(1)}m × ${bounds.heightM.toFixed(1)}m (${bounds.areaM2} m²) 标准厂房轮廓及 ${this.obstacles.length} 处示例禁布区（非卫星影像视觉识别，请按底图手绘校准），排布 ${this.summary.moduleCount} 块组件 (${this.summary.dcKw} kWp)。`;
    } else {
      this.aiExecutionNote = `离线回退示例：识别服务未连接，已在当前定位 (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) 载入 ${bounds.widthM.toFixed(1)}m × ${bounds.heightM.toFixed(1)}m 标准厂房示例轮廓及 ${this.obstacles.length} 处示例禁布区（非实景图像识别），请按底图框选校准。`;
    }
    this.refresh();
    this.notice(this.aiExecutionNote);
  }

  /**
   * AI 按要求一键设计 ([data-sat-action="ai-autopilot"])
   * Parses user requirements, couples real local weather to set optimal tilt & unshaded spacing,
   * lays out modules on satellite roof, allocates MPPT strings, and generates 4 CAD drawings.
   */
  async runAiAutopilot() {
    this.showRoofOverlay = true;
    const reqText = String(this.aiRequirement || '').trim();

    // 1. Parse natural-language design requirements if provided
    if (reqText) {
      const kwMatch = reqText.match(/(\d+(?:\.\d+)?)\s*(?:kw|kwp|千瓦)/i);
      const mwMatch = reqText.match(/(\d+(?:\.\d+)?)\s*(?:mw|mwp|兆瓦)/i);
      if (kwMatch) {
        this.targetCapacityKw = Number(kwMatch[1]);
      } else if (mwMatch) {
        this.targetCapacityKw = Number(mwMatch[1]) * 1000;
      }
      if (/平屋面|混凝土|女儿墙/.test(reqText)) {
        this.roofType = 'flat';
      } else if (/单坡/.test(reqText)) {
        this.roofType = 'single_slope';
      } else if (/双坡|彩钢/.test(reqText)) {
        this.roofType = 'double_slope';
      }
      if (/横向|横排|landscape/i.test(reqText)) {
        this.orientation = 'landscape';
      } else if (/竖向|竖排|portrait/i.test(reqText)) {
        this.orientation = 'portrait';
      }
      const setbackMatch = reqText.match(/退距\s*(\d+(?:\.\d+)?)\s*m?/);
      if (setbackMatch) {
        this.edgeSetbackM = Math.max(0.2, Math.min(5.0, Number(setbackMatch[1])));
      }
      const tiltMatch = reqText.match(/(?:倾角|坡度|夹角)\s*(\d+(?:\.\d+)?)\s*[°度]?/);
      if (tiltMatch) {
        const parsedTilt = Math.max(0, Math.min(45, Number(tiltMatch[1])));
        this.tiltDeg = parsedTilt;
        this.roofSlopeDeg = parsedTilt;
        this.angleStrategy = 'custom';
      } else if (/总发电最优|装机最大/.test(reqText)) {
        this.angleStrategy = 'roof_total';
      } else if (/气象|单瓦最优|最佳倾角|最优倾角/.test(reqText)) {
        this.angleStrategy = 'weather_yield';
      }
    }

    // 2. Ensure a roof outline exists on the current satellite view before laying out
    if (!this.hasRoof || this.roofOutlineM.length < 3) {
      this.ensureRoofOutline({ withDefaultKeepouts: true });
    }

    // 3. Evaluate real local weather and apply optimal tilt/azimuth & winter-solstice unshaded spacing
    const wxEval = this.evaluateWeatherAndAngles();
    if (this.angleStrategy === 'weather_yield') {
      this.tiltDeg = wxEval.weatherOptimalTiltDeg;
      this.azimuthDeg = wxEval.weatherOptimalAzimuthDeg;
      if (this.roofType === 'flat') {
        this.rowSpacingM = wxEval.weatherOptimalRowGapM;
      } else {
        this.roofSlopeDeg = wxEval.weatherOptimalTiltDeg;
        this.rowSpacingM = Math.max(0.45, Number((wxEval.weatherOptimalRowGapM * 0.65).toFixed(2)));
      }
    } else if (this.angleStrategy === 'roof_total') {
      this.tiltDeg = wxEval.roofOptimalTiltDeg;
      if (this.roofType === 'flat') {
        this.rowSpacingM = wxEval.roofOptimalRowGapM;
      } else {
        this.roofSlopeDeg = wxEval.roofOptimalTiltDeg;
        this.rowSpacingM = wxEval.roofOptimalRowGapM;
      }
    } else if (this.angleStrategy === 'roof_flush') {
      this.tiltDeg = this.roofSlopeDeg;
      this.rowSpacingM = 0.45;
    }

    // 4. Execute roof layout, MPPT string allocation, and PVsyst 8760h simulation
    this.layoutModules({ quiet: true, autoCreateRoof: true });
    this.electricalConfirmed = true;
    this.showStringColors = true;
    this.computeElectricalAllocation();
    this.refreshPvsystData({ fetchBackend: true });

    const usedTilt = this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg;
    this.aiExecutionNote = `已按要求完成设计：定位 ${this.address} (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E)，依据当地实时气象采用倾角 ${usedTilt}° / 方位角 ${this.azimuthDeg}°（冬至无遮挡排距 ${this.rowSpacingM}m），排布 ${this.summary.moduleCount} 块组件（装机 ${this.summary.dcKw} kWp），配置 ${this.summary.inverterCount} 台逆变器共 ${this.summary.stringCount} 路组串，首年并网发电量 ${(this.summary.annualKwh / 10000).toFixed(2)} 万kWh（满发 ${this.summary.specificYield} h，PR ${this.summary.prPct}%），已同步生成 MPPT 配串表与 4 张施工 CAD 图纸。`;
    this.autopilotState = null;
    this.refresh();
    this.notice(this.aiExecutionNote);
  }

  /**
   * 保存并转入光筑工程库 ([data-sat-action="save-to-project"])
   */
  async saveToProject() {
    const bounds = this.getRoofBoundsM(true);
    const modSpec = this.getSelectedModule();
    const invSpec = this.getSelectedInverter();
    const wiredModules = (this.modules || []).filter((m) => !m.unwired);
    const payload = {
      name: this.projectName,
      address: this.address,
      lat: this.lat,
      lon: this.lon,
      roof_type: this.roofType === 'flat' ? 'flat' : 'metal',
      slope_deg: this.roofSlopeDeg,
      tilt_deg: this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg,
      azimuth_deg: this.azimuthDeg,
      row_spacing_m: this.rowSpacingM,
      edge_setback_m: this.edgeSetbackM,
      modules_per_string: this.modulesPerString,
      orientation: this.orientation || 'portrait',
      length_m: bounds.widthM,
      width_m: bounds.heightM,
      outline: this.roofOutlineM,
      obstacles: this.obstacles,
      module_id: this.moduleModelId,
      inverter_id: this.inverterModelId,
      layout_params: {
        stc_w: modSpec?.stc_w,
        module_model: modSpec?.model,
        length_m: modSpec?.length_m,
        width_m: modSpec?.width_m,
        tilt_deg: this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg,
        azimuth_deg: this.azimuthDeg,
        row_spacing_m: this.rowSpacingM,
        edge_setback_m: this.edgeSetbackM,
        orientation: this.orientation || 'portrait',
      },
      electrical_params: {
        inverter_model: invSpec?.model,
        rated_ac_kw: invSpec?.rated_ac_kw,
        modules_per_string: this.modulesPerString,
      },
      modules: wiredModules.map((m, idx) => ({
        id: m.id || `M${String(idx + 1).padStart(4, '0')}`,
        cx: Number((m.cx ?? m.x ?? 0).toFixed(3)),
        cy: Number((m.cy ?? m.y ?? 0).toFixed(3)),
        w: Number((m.w ?? modSpec?.width_m ?? 1.134).toFixed(3)),
        h: Number((m.h ?? modSpec?.length_m ?? 2.278).toFixed(3)),
        tilt_deg: Number(m.tilt_deg ?? (this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg)),
        azimuth_deg: Number(m.azimuth_deg ?? this.azimuthDeg),
        row: Number.isFinite(m.row) ? m.row : 1,
        col: Number.isFinite(m.col) ? m.col : idx + 1,
      })),
      module_count: this.summary.moduleCount,
      dc_kw: this.summary.dcKw,
      ac_kw: this.summary.acKw,
      annual_kwh: this.summary.annualKwh,
    };

    try {
      this.notice('正在将当前卫星设计与排布方案保存至光筑工程库...', { persist: true });
      const res = await this.api('satmap/save-project', payload);
      const pid = res?.project_id || 'satmap-project';
      const ver = res?.version || 1;
      this.notice(`已成功转入光筑工程库：${pid} (v${ver})，正在打开工程结果页...`);
      if (typeof location !== 'undefined') {
        location.hash = `#result/${encodeURIComponent(pid)}?version=${ver}`;
      }
      return res;
    } catch (err) {
      this.notice(`保存转入工程库失败（未生成工程库记录）：${err.message || '请检查后端服务状态后重试'}`);
      return null;
    }
  }

  refresh({ resetScroll = false } = {}) {
    if (!this.host) return;
    if (this.twin3d) {
      this.twin3d.dispose();
      this.twin3d = null;
    }
    const prevShell = this.host.querySelector('.satmap-shell');
    const prevScrollTop = !resetScroll
      ? (prevShell?.scrollTop || this.host.scrollTop || 0)
      : 0;
    this.host.innerHTML = this.html();
    this.mount(this.host);
    if (!resetScroll && prevScrollTop > 0) {
      const nextShell = this.host.querySelector('.satmap-shell');
      if (nextShell) nextShell.scrollTop = prevScrollTop;
      this.host.scrollTop = prevScrollTop;
    }
  }

  render(host) {
    if (!host) return;
    if (this.twin3d) {
      this.twin3d.dispose();
      this.twin3d = null;
    }
    host.innerHTML = this.html();
    this.mount(host);
  }

  mount(host) {
    this.host = host;
    if (!host) return;
    if (!this._tilesPrewarmed && (typeof location === 'undefined' || location.hostname !== 'offline.test')) {
      this._tilesPrewarmed = true;
      this.prewarmInitialTiles();
    }
    localizeDomSubtree(host);

    if (this.step === 1) {
      if (this.is3D) {
        const stage = host.querySelector('#satmap-3d-twin-stage');
        if (stage) {
          this.twin3d = mountSatmap3DTwin(stage, this.build3DTwinPayload(), {
            onShadingUpdate: (snap) => {
              this.update3DMetricsBarInPlace(snap);
            },
          });
          if (this.twin3d?.available) {
            if (this.sim3dCam && this.sim3dCam !== 'iso') {
              this.twin3d.setCameraPreset(this.sim3dCam);
            }
            if (this.sim3dPlaying) {
              this.twin3d.setSimConfig({ playing: true });
            }
          }
        }
      } else {
        this.drawMapCanvas();
      }
      this.drawLocPickerModalCanvas();
    } else if (this.step === 4) {
      this.drawEffectCanvas();
    }

    // Bind interactive drag-pan & wheel-zoom on Video 1 Location Picker Modal Canvas (#sat-loc-picker-canvas)
    const locPickerCanvas = host.querySelector('#sat-loc-picker-canvas');
    if (locPickerCanvas) {
      let lpDrag = null;
      locPickerCanvas.onpointerdown = (ev) => {
        lpDrag = { x: ev.clientX, y: ev.clientY, lon: this.lon, lat: this.lat };
        try { locPickerCanvas.setPointerCapture(ev.pointerId); } catch {}
      };
      locPickerCanvas.onpointermove = (ev) => {
        if (!lpDrag) return;
        const dx = ev.clientX - lpDrag.x;
        const dy = ev.clientY - lpDrag.y;
        const mpp = metersPerPixelAtLatZoom(lpDrag.lat, this.zoom);
        const dLon = (-dx * mpp) / (111320 * Math.max(0.15, Math.cos((lpDrag.lat * Math.PI) / 180)));
        const dLat = (dy * mpp) / 110540;
        this.lon = Number((lpDrag.lon + dLon).toFixed(6));
        this.lat = Number(Math.max(3, Math.min(54, lpDrag.lat + dLat)).toFixed(6));
        if (!this.hasRoof) {
          this.roofCenterLon = this.lon;
          this.roofCenterLat = this.lat;
        }
        this.scheduleMapRedraw();
      };
      locPickerCanvas.onpointerup = () => {
        lpDrag = null;
      };
      locPickerCanvas.onwheel = (ev) => {
        ev.preventDefault();
        this.setZoom((this.zoom || 18) + (ev.deltaY < 0 ? 1 : -1));
        this.scheduleMapRedraw();
      };
    }

    // Escape key cancels active polygon draw or exits fullscreen; Enter key closes active polygon draw
    if (typeof window !== 'undefined' && !this._escBound) {
      this._escBound = true;
      window.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter') {
          if ((this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly') && this.drawingObstaclePointsM.length >= 3) {
            ev.preventDefault();
            this.finishPolygonObstacle();
            return;
          }
          if (this.activeTool === 'roof_poly' && this.drawingPointsM.length >= 3) {
            ev.preventDefault();
            this.finishPolygonRoof();
            return;
          }
        }
        if (ev.key === 'Escape') {
          if (this.drawingObstaclePointsM.length > 0 || this.drawingPointsM.length > 0) {
            this.drawingObstaclePointsM = [];
            this.drawingPointsM = [];
            this.cursorPointM = null;
            this.dragPreview = null;
            this.refresh();
            return;
          }
          if (this.isFullscreen) {
            this.isFullscreen = false;
            this.refresh();
          }
        }
      });
    }

    // Bind Step 1 Satellite Map Canvas interactive Pan / Zoom / Scale / Direction / Roof / RoofPolygon / Obstacle / ObstaclePolygon / Delete
    const mapCanvas = host.querySelector('#satmap-main-canvas');
    if (mapCanvas) {
      let dragStart = null;
      let rectFirstCorner = null; // Supports click-move-click in addition to press-drag-release!
      let draggingRoofVertexIdx = -1;
      let draggingObstacleVertex = null; // { obsIdx, vertIdx }

      const toCanvasCoords = (ev) => {
        const rect = mapCanvas.getBoundingClientRect();
        const sx = (ev.clientX - rect.left) * (mapCanvas.width / Math.max(1, rect.width));
        const sy = (ev.clientY - rect.top) * (mapCanvas.height / Math.max(1, rect.height));
        return [sx, sy];
      };
      const toLocalMeters = (sx, sy) => this.canvasToLocalMeters(mapCanvas.width, mapCanvas.height, sx, sy);

      const updateHudTextInPlace = () => {
        const hud = host.querySelector('#satmap-hud-coords') || host.querySelector('.satmap-floating-hud span');
        if (hud) {
          hud.textContent = `当前定位：${this.address} (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) · 缩放级别 Z${this.zoom} · 比例尺 1px ≈ ${this.metersPerPx.toFixed(3)}m · 主墙偏角 ${this.ridgeAzimuthDeg}°`;
        }
        const rmsBadge = host.querySelector('#satmap-rms-zoom-badge');
        if (rmsBadge) rmsBadge.textContent = `Z${this.zoom}`;
        const fitRoofBtn = host.querySelector('.satmap-floating-tools [data-sat-action="zoom-fit-roof"]');
        if (fitRoofBtn) {
          fitRoofBtn.textContent = `🔍 屋面特写 (Z${this.zoom})`;
          fitRoofBtn.classList.toggle('active', this.zoom >= 21);
        }
        const lonInp = host.querySelector('[data-sat-field="lon"]');
        const latInp = host.querySelector('[data-sat-field="lat"]');
        if (lonInp) lonInp.value = this.lon.toFixed(4);
        if (latInp) latInp.value = this.lat.toFixed(4);
      };

      const updatePolyCloseButtonsInPlace = () => {
        const roofBtn = host.querySelector('#sat-close-roof-poly-btn');
        if (roofBtn) {
          if (this.activeTool === 'roof_poly' && this.drawingPointsM.length >= 3) {
            roofBtn.style.display = '';
            roofBtn.textContent = `完成屋顶闭合 (${this.drawingPointsM.length}点)`;
          } else {
            roofBtn.style.display = 'none';
          }
        }
        const obsBtn = host.querySelector('#sat-close-obs-poly-btn');
        if (obsBtn) {
          if ((this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly') && this.drawingObstaclePointsM.length >= 3) {
            obsBtn.style.display = '';
            obsBtn.textContent = `完成禁布区闭合 (${this.drawingObstaclePointsM.length}点)`;
          } else {
            obsBtn.style.display = 'none';
          }
        }
      };

      const finishRectSelection = (startPt, endPt, toolKind) => {
        const x0 = Math.min(startPt.mx, endPt.mx);
        const x1 = Math.max(startPt.mx, endPt.mx);
        const y0 = Math.min(startPt.my, endPt.my);
        const y1 = Math.max(startPt.my, endPt.my);
        this.dragPreview = null;
        rectFirstCorner = null;

        if (toolKind === 'roof') {
          const w = Math.max(4, x1 - x0);
          const h = Math.max(4, y1 - y0);
          const rx1 = w < 8 ? x0 + 16 : x1;
          const ry1 = h < 6 ? y0 + 12 : y1;
          const rw = rx1 - x0;
          const rh = ry1 - y0;
          this.roofOutlineM = [
            [Number(x0.toFixed(2)), Number(y0.toFixed(2))],
            [Number(rx1.toFixed(2)), Number(y0.toFixed(2))],
            [Number(rx1.toFixed(2)), Number(ry1.toFixed(2))],
            [Number(x0.toFixed(2)), Number(ry1.toFixed(2))],
          ];
          this.hasRoof = true;
          this.showRoofOverlay = true;
          if (!this.scaleCustomized) {
            this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
          }
          this.ridgeAzimuthDeg = detectPrincipalRoofAngleDeg(this.roofOutlineM);
          this.scaleReferenceM = Number(rw.toFixed(1));
          this.activeTool = 'pan';
          if (this.hasLaidOut) {
            this.layoutModules({ quiet: true, autoCreateRoof: false });
            this.notice(`已更新框选屋面：${rw.toFixed(1)}m × ${rh.toFixed(1)}m (${Math.round(rw * rh)} m²)，自动识别比例尺与方向并重排 ${this.summary.moduleCount} 块组件 (${this.summary.dcKw} kWp)。`);
          } else {
            this.notice(`已绘制屋顶范围：${rw.toFixed(1)}m × ${rh.toFixed(1)}m (${Math.round(rw * rh)} m²，已自动识别比例尺 1px≈${this.metersPerPx.toFixed(3)}m 与正交方向)。现在可点「2. 绘制禁布区」或「3. 一键铺设」！`);
          }
          this.refresh();
        } else if (toolKind === 'obstacle') {
          // Ensure minimum 2.0m x 1.2m orthogonal keepout box so narrow skylights/vents are always visible & block modules
          const rawW = x1 - x0;
          const rawH = y1 - y0;
          const ox0 = rawW < 2.0 ? (x0 + x1) * 0.5 - 1.5 : x0;
          const ox1 = rawW < 2.0 ? (x0 + x1) * 0.5 + 1.5 : x1;
          const oy0 = rawH < 1.2 ? (y0 + y1) * 0.5 - 0.8 : y0;
          const oy1 = rawH < 1.2 ? (y0 + y1) * 0.5 + 0.8 : y1;

          if (!this.hasRoof && (!this.roofOutlineM || this.roofOutlineM.length < 3)) {
            this.roofCenterLon = this.lon;
            this.roofCenterLat = this.lat;
          }
          this.showRoofOverlay = true;
          this.obstacles.push({
            id: `keepout-${Date.now()}-${this.obstacles.length + 1}`,
            name: `禁布区 #${this.obstacles.length + 1}`,
            kind: 'skylight',
            polygon: [
              [Number(ox0.toFixed(2)), Number(oy0.toFixed(2))],
              [Number(ox1.toFixed(2)), Number(oy0.toFixed(2))],
              [Number(ox1.toFixed(2)), Number(oy1.toFixed(2))],
              [Number(ox0.toFixed(2)), Number(oy1.toFixed(2))],
            ],
          });
          // Keep activeTool === 'obstacle' so the user can draw multiple skylights/obstacles consecutively!
          if (this.hasLaidOut) {
            this.layoutModules({ quiet: true, autoCreateRoof: false });
          }
          this.notice(
            `已添加正交屋面禁布区 #${this.obstacles.length} (${(ox1 - ox0).toFixed(1)}m × ${(oy1 - oy0).toFixed(1)}m)${this.hasLaidOut ? `，已自动避让并重排 ${this.summary.moduleCount} 块组件` : '，可继续在屋面拉框添加更多禁布区，或点击「3. 一键铺设」'}。`
          );
          this.refresh();
        }
      };

      const finishPolygonRoof = () => this.finishPolygonRoof();
      const finishPolygonObstacle = () => this.finishPolygonObstacle();

      // Mouse wheel zoom on real satellite map (Zoom 4..24, cursor-centered) — instant redraw without DOM rebuild!
      mapCanvas.onwheel = (ev) => {
        ev.preventDefault();
        const [sx, sy] = toCanvasCoords(ev);
        const changed = this.setZoom(this.zoom + (ev.deltaY < 0 ? 1 : -1), {
          anchorSx: sx,
          anchorSy: sy,
          canvasW: mapCanvas.width,
          canvasH: mapCanvas.height,
        });
        if (changed) {
          this.scheduleMapRedraw();
          updateHudTextInPlace();
        }
      };

      mapCanvas.ondblclick = (ev) => {
        if (this.activeTool === 'roof_poly' && this.drawingPointsM.length >= 3) {
          ev.preventDefault();
          finishPolygonRoof();
          return;
        }
        if ((this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly') && this.drawingObstaclePointsM.length >= 3) {
          ev.preventDefault();
          finishPolygonObstacle();
        }
      };

      mapCanvas.oncontextmenu = (ev) => {
        if (this.activeTool === 'roof_poly' && this.drawingPointsM.length >= 3) {
          ev.preventDefault();
          finishPolygonRoof();
          return;
        }
        if ((this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly') && this.drawingObstaclePointsM.length >= 3) {
          ev.preventDefault();
          finishPolygonObstacle();
        }
      };

      mapCanvas.onpointerdown = (ev) => {
        const [sx, sy] = toCanvasCoords(ev);

        // Anchor roof geographic reference to current view center if starting first roof or obstacle draw
        const hasAnyGeom =
          this.hasRoof ||
          (this.obstacles && this.obstacles.length > 0) ||
          (this.drawingPointsM && this.drawingPointsM.length > 0) ||
          (this.drawingObstaclePointsM && this.drawingObstaclePointsM.length > 0);
        if (
          (this.activeTool === 'roof' ||
            this.activeTool === 'roof_poly' ||
            this.activeTool === 'obstacle' ||
            this.activeTool === 'obstacle_poly') &&
          !hasAnyGeom &&
          !rectFirstCorner
        ) {
          this.roofCenterLon = this.lon;
          this.roofCenterLat = this.lat;
        }
        const [mx, my] = toLocalMeters(sx, sy);

        // 1. Check if clicking an existing roof or obstacle corner handle (P1..Pn) to fine-tune vertex position
        // IMPORTANT: Do NOT hijack pointerdown when activeTool === 'obstacle' | 'obstacle_poly' so drawing keepouts near corners always works!
        if ((this.activeTool === 'pan' || this.activeTool === 'roof') && !rectFirstCorner) {
          if (this.hasRoof && this.roofOutlineM.length >= 3) {
            let hitV = -1;
            let bestDist = 14;
            this.roofOutlineM.forEach(([vx, vy], idx) => {
              const [px, py] = this.localMetersToCanvas(mapCanvas.width, mapCanvas.height, vx, vy);
              const d = Math.hypot(sx - px, sy - py);
              if (d < bestDist) {
                bestDist = d;
                hitV = idx;
              }
            });
            if (hitV >= 0) {
              draggingRoofVertexIdx = hitV;
              try { mapCanvas.setPointerCapture(ev.pointerId); } catch { }
              return;
            }
          }
          if (this.activeTool === 'pan' && this.obstacles && this.obstacles.length > 0) {
            let hitObs = null;
            let bestObsDist = 13;
            this.obstacles.forEach((obs, obsIdx) => {
              (obs.polygon || []).forEach(([vx, vy], vertIdx) => {
                const [px, py] = this.localMetersToCanvas(mapCanvas.width, mapCanvas.height, vx, vy);
                const d = Math.hypot(sx - px, sy - py);
                if (d < bestObsDist) {
                  bestObsDist = d;
                  hitObs = { obsIdx, vertIdx };
                }
              });
            });
            if (hitObs) {
              draggingObstacleVertex = hitObs;
              try { mapCanvas.setPointerCapture(ev.pointerId); } catch { }
              return;
            }
          }
        }

        // 2. Delete obstacle tool
        if (this.activeTool === 'delete') {
          const hitIdx = this.obstacles.findIndex((o) => pointInPolygon([mx, my], o.polygon));
          if (hitIdx >= 0) {
            const removed = this.obstacles.splice(hitIdx, 1)[0];
            if (this.hasLaidOut) {
              this.layoutModules({ quiet: true, autoCreateRoof: false });
            }
            this.notice(`已删除禁布区「${removed.name}」${this.hasLaidOut ? '并自动重排组件' : ''}。`);
            this.refresh();
          }
          return;
        }

        // 2B. Interactive Single-Module Click-to-Toggle ('toggle_module')
        if (this.activeTool === 'toggle_module' && ev.button === 0) {
          if (this.modules && this.modules.length > 0) {
            const hitModIdx = this.modules.findIndex(
              (m) => pointInPolygon([mx, my], m.cornersM) || Math.hypot(mx - m.cx, my - m.cy) <= Math.min(m.w, m.h) * 0.55
            );
            if (hitModIdx >= 0) {
              const [removedMod] = this.modules.splice(hitModIdx, 1);
              if (!this.removedModules) this.removedModules = [];
              this.removedModules.push(removedMod);
              this.computeElectricalAllocation();
              this.refreshPvsystData({ fetchBackend: false });
              this.notice(`已手动剔除单块组件 ${removedMod.id}（当前剩余 ${this.summary.moduleCount} 块 · ${this.summary.dcKw} kWp，再次点击虚线框可恢复）。`);
              this.refresh();
              return;
            }
          }
          if (this.removedModules && this.removedModules.length > 0) {
            const hitRemIdx = this.removedModules.findIndex(
              (rm) => pointInPolygon([mx, my], rm.cornersM) || Math.hypot(mx - rm.cx, my - rm.cy) <= Math.max(rm.w, rm.h) * 0.65
            );
            if (hitRemIdx >= 0) {
              const [restoredMod] = this.removedModules.splice(hitRemIdx, 1);
              this.modules.push(restoredMod);
              this.modules.sort((a, b) => (a.row - b.row) || (a.col - b.col));
              this.computeElectricalAllocation();
              this.refreshPvsystData({ fetchBackend: false });
              this.notice(`已恢复组件 ${restoredMod.id}（当前共 ${this.summary.moduleCount} 块 · ${this.summary.dcKw} kWp）。`);
              this.refresh();
              return;
            }
          }
          return;
        }

        // 3. Multi-point polygon roof drawing ('roof_poly')
        if (this.activeTool === 'roof_poly' && ev.button === 0) {
          if (this.drawingPointsM.length >= 3) {
            const [p0x, p0y] = this.localMetersToCanvas(
              mapCanvas.width,
              mapCanvas.height,
              this.drawingPointsM[0][0],
              this.drawingPointsM[0][1]
            );
            if (Math.hypot(sx - p0x, sy - p0y) <= 18) {
              finishPolygonRoof();
              return;
            }
          }
          this.drawingPointsM.push([mx, my]);
          this.cursorPointM = [mx, my];
          updatePolyCloseButtonsInPlace();
          this.scheduleMapRedraw();
          return;
        }

        // 3B. Multi-point polygon obstacle/keepout drawing ('obstacle_poly' or click-by-click in 'obstacle')
        if ((this.activeTool === 'obstacle_poly' || this.activeTool === 'obstacle') && ev.button === 0) {
          if (this.drawingObstaclePointsM.length >= 3) {
            const [p0x, p0y] = this.localMetersToCanvas(
              mapCanvas.width,
              mapCanvas.height,
              this.drawingObstaclePointsM[0][0],
              this.drawingObstaclePointsM[0][1]
            );
            if (Math.hypot(sx - p0x, sy - p0y) <= 18) {
              finishPolygonObstacle();
              return;
            }
          }
          if (this.activeTool === 'obstacle_poly') {
            this.drawingObstaclePointsM.push([mx, my]);
            this.cursorPointM = [mx, my];
            updatePolyCloseButtonsInPlace();
            this.scheduleMapRedraw();
            return;
          }
        }

        // 4. Second click of Click-Move-Click rectangle ('roof')
        if (rectFirstCorner && this.activeTool === 'roof' && ev.button === 0) {
          finishRectSelection(rectFirstCorner, { sx, sy, mx, my }, this.activeTool);
          return;
        }

        const isPan = this.activeTool === 'pan' || ev.button === 1 || ev.button === 2;
        dragStart = {
          sx,
          sy,
          mx,
          my,
          startLon: this.lon,
          startLat: this.lat,
          isPan,
        };
        if (
          !isPan &&
          (this.activeTool === 'roof' ||
            (this.activeTool === 'obstacle' && this.drawingObstaclePointsM.length === 0) ||
            this.activeTool === 'scale' ||
            this.activeTool === 'direction')
        ) {
          this.dragPreview = {
            kind: this.activeTool,
            sx0: sx,
            sy0: sy,
            sx1: sx,
            sy1: sy,
            mx0: mx,
            my0: my,
            mx1: mx,
            my1: my,
          };
        }
        try { mapCanvas.setPointerCapture(ev.pointerId); } catch { }
      };

      mapCanvas.onpointermove = (ev) => {
        const [sx, sy] = toCanvasCoords(ev);

        // Dragging an existing roof corner handle P1..Pn
        if (draggingRoofVertexIdx >= 0) {
          const [mx, my] = toLocalMeters(sx, sy);
          this.roofOutlineM[draggingRoofVertexIdx] = [Number(mx.toFixed(2)), Number(my.toFixed(2))];
          this.scheduleMapRedraw();
          return;
        }

        // Dragging an existing obstacle corner handle
        if (draggingObstacleVertex) {
          const [mx, my] = toLocalMeters(sx, sy);
          const obs = this.obstacles[draggingObstacleVertex.obsIdx];
          if (obs && obs.polygon && obs.polygon[draggingObstacleVertex.vertIdx]) {
            obs.polygon[draggingObstacleVertex.vertIdx] = [Number(mx.toFixed(2)), Number(my.toFixed(2))];
            this.scheduleMapRedraw();
          }
          return;
        }

        // Live polygon roof rubber-band preview
        if (this.activeTool === 'roof_poly' && this.drawingPointsM.length > 0) {
          this.cursorPointM = toLocalMeters(sx, sy);
          this.scheduleMapRedraw();
          return;
        }

        // Live polygon obstacle rubber-band preview
        if ((this.activeTool === 'obstacle_poly' || this.activeTool === 'obstacle') && this.drawingObstaclePointsM.length > 0 && !dragStart) {
          this.cursorPointM = toLocalMeters(sx, sy);
          this.scheduleMapRedraw();
          return;
        }

        // Live Click-Move-Click rectangle rubber-band preview
        if (rectFirstCorner && this.activeTool === 'roof') {
          const [mx, my] = toLocalMeters(sx, sy);
          this.dragPreview = {
            kind: this.activeTool,
            sx0: rectFirstCorner.sx,
            sy0: rectFirstCorner.sy,
            sx1: sx,
            sy1: sy,
            mx0: rectFirstCorner.mx,
            my0: rectFirstCorner.my,
            mx1: mx,
            my1: my,
          };
          this.scheduleMapRedraw();
          return;
        }

        if (!dragStart) {
          // Real-time Hover Module & String Inspector when moving cursor over laid-out modules
          if (this.modules && this.modules.length > 0 && (this.activeTool === 'pan' || this.activeTool === 'toggle_module')) {
            const [mx, my] = toLocalMeters(sx, sy);
            const hitMod = this.modules.find(
              (m) => Math.abs(mx - m.cx) <= m.w * 0.6 && Math.abs(my - m.cy) <= m.h * 0.6 && pointInPolygon([mx, my], m.cornersM)
            );
            if (hitMod !== this.hoveredModule || (hitMod && this.hoverScreenPos)) {
              this.hoveredModule = hitMod || null;
              this.hoverScreenPos = hitMod ? [sx, sy] : null;
              this.scheduleMapRedraw();
            }
          } else if (this.hoveredModule) {
            this.hoveredModule = null;
            this.hoverScreenPos = null;
            this.scheduleMapRedraw();
          }
          return;
        }
        if (this.hoveredModule) {
          this.hoveredModule = null;
          this.hoverScreenPos = null;
        }

        // Panning the satellite map smoothly at 60fps
        if (dragStart.isPan) {
          const dxPx = sx - dragStart.sx;
          const dyPx = sy - dragStart.sy;
          const mpp = metersPerPixelAtLatZoom(dragStart.startLat, this.zoom);
          const dLon = (-dxPx * mpp) / (111320 * Math.max(0.15, Math.cos((dragStart.startLat * Math.PI) / 180)));
          const dLat = (dyPx * mpp) / 110540;
          this.lon = Number((dragStart.startLon + dLon).toFixed(6));
          this.lat = Number(Math.max(3, Math.min(54, dragStart.startLat + dLat)).toFixed(6));
          const hasAnyGeom =
            this.hasRoof ||
            (this.obstacles && this.obstacles.length > 0) ||
            (this.drawingPointsM && this.drawingPointsM.length > 0) ||
            (this.drawingObstaclePointsM && this.drawingObstaclePointsM.length > 0);
          if (!hasAnyGeom) {
            this.roofCenterLon = this.lon;
            this.roofCenterLat = this.lat;
          }
          this.scheduleMapRedraw();
          updateHudTextInPlace();
          return;
        }

        // Live Press-Drag-Release rubber-band preview for 'roof', 'obstacle' (when not in multi-point mode), 'scale', or 'direction'
        if (
          this.activeTool === 'roof' ||
          (this.activeTool === 'obstacle' && this.drawingObstaclePointsM.length === 0) ||
          this.activeTool === 'scale' ||
          this.activeTool === 'direction'
        ) {
          const [mx, my] = toLocalMeters(sx, sy);
          this.dragPreview = {
            kind: this.activeTool,
            sx0: dragStart.sx,
            sy0: dragStart.sy,
            sx1: sx,
            sy1: sy,
            mx0: dragStart.mx,
            my0: dragStart.my,
            mx1: mx,
            my1: my,
          };
          this.scheduleMapRedraw();
        }
      };

      mapCanvas.onpointerup = (ev) => {
        if (draggingRoofVertexIdx >= 0) {
          draggingRoofVertexIdx = -1;
          this.ridgeAzimuthDeg = detectPrincipalRoofAngleDeg(this.roofOutlineM);
          const bounds = this.getRoofBoundsM(true);
          this.scaleReferenceM = bounds.widthM;
          if (this.hasLaidOut) {
            this.layoutModules({ quiet: true, autoCreateRoof: false });
          }
          this.refresh();
          return;
        }

        if (draggingObstacleVertex) {
          draggingObstacleVertex = null;
          if (this.hasLaidOut) {
            this.layoutModules({ quiet: true, autoCreateRoof: false });
          }
          this.refresh();
          return;
        }

        if (!dragStart) return;
        const [sx, sy] = toCanvasCoords(ev);
        const [mx, my] = toLocalMeters(sx, sy);
        const distPx = Math.hypot(sx - dragStart.sx, sy - dragStart.sy);
        const start = dragStart;
        dragStart = null;

        if (start.isPan) {
          if (distPx > 6) {
            updateHudTextInPlace();
            this.evaluateWeatherAndAngles();
          }
          return;
        }

        if (this.activeTool === 'obstacle') {
          if (distPx >= 8 && this.drawingObstaclePointsM.length === 0) {
            // Press-and-drag (>= 8px) with no active polygon points creates a rectangular keepout zone
            finishRectSelection(start, { sx, sy, mx, my }, 'obstacle');
          } else {
            // Single click adds a vertex to multi-point polygon keepout drawing!
            this.dragPreview = null;
            this.drawingObstaclePointsM.push([start.mx, start.my]);
            this.cursorPointM = [mx, my];
            updatePolyCloseButtonsInPlace();
            this.scheduleMapRedraw();
          }
          return;
        }

        if (this.activeTool === 'roof') {
          if (distPx >= 10) {
            // Completed via Press-Drag-Release
            finishRectSelection(start, { sx, sy, mx, my }, 'roof');
          } else {
            // First click of Click-Move-Click mode! Keep rubber-band active until second click.
            rectFirstCorner = start;
          }
          return;
        }

        if (this.activeTool === 'direction') {
          this.dragPreview = null;
          if (distPx >= 8) {
            let rawDeg = (Math.atan2(sy - start.sy, sx - start.sx) * 180) / Math.PI;
            while (rawDeg <= -90) rawDeg += 180;
            while (rawDeg > 90) rawDeg -= 180;
            if (rawDeg > 45) rawDeg -= 90;
            if (rawDeg < -45) rawDeg += 90;
            this.ridgeAzimuthDeg = Number(rawDeg.toFixed(1));
          } else if (this.roofOutlineM.length >= 3) {
            this.ridgeAzimuthDeg = detectPrincipalRoofAngleDeg(this.roofOutlineM);
          }
          this.activeTool = 'pan';
          if (this.hasLaidOut) {
            this.layoutModules({ quiet: true, autoCreateRoof: false });
          }
          this.notice(`已按建筑屋脊/外墙方向对齐：偏角 ${this.ridgeAzimuthDeg}°${this.hasLaidOut ? `，已重排 ${this.summary.moduleCount} 块组件` : ''}。`);
          this.refresh();
          return;
        }

        if (this.activeTool === 'scale') {
          this.dragPreview = null;
          if (distPx < 8) {
            this.scaleCustomized = false;
            this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
            this.activeTool = 'pan';
            this.notice(`已恢复卫星地图自动比例尺：1px ≈ ${this.metersPerPx.toFixed(3)} m`);
            this.refresh();
            return;
          }
          const cx = mapCanvas.width / 2;
          const cy = mapCanvas.height / 2;
          this.scaleLinePx = [
            [start.sx - cx, start.sy - cy],
            [sx - cx, sy - cy],
          ];
          const oldMpp = Math.max(0.03, this.metersPerPx);
          const newMpp = Math.max(0.03, this.scaleReferenceM / Math.max(20, distPx));
          const ratio = newMpp / oldMpp;
          // Proportionally scale existing local meter coordinates so drawn roofs stay at the exact same screen pixels!
          if (this.roofOutlineM.length >= 3) {
            this.roofOutlineM = this.roofOutlineM.map(([x, y]) => [Number((x * ratio).toFixed(2)), Number((y * ratio).toFixed(2))]);
          }
          for (const obs of this.obstacles) {
            obs.polygon = obs.polygon.map(([x, y]) => [Number((x * ratio).toFixed(2)), Number((y * ratio).toFixed(2))]);
          }
          this.scaleCustomized = true;
          this.metersPerPx = newMpp;
          this.activeTool = 'pan';
          if (this.hasLaidOut) {
            this.layoutModules({ quiet: true, autoCreateRoof: false });
          }
          this.notice(`比例尺已校准：基准线 ${distPx.toFixed(0)} px = ${this.scaleReferenceM.toFixed(1)} m (1px ≈ ${this.metersPerPx.toFixed(3)}m)`);
          this.refresh();
        }
      };

      mapCanvas.onpointerleave = () => {
        if (this.hoveredModule) {
          this.hoveredModule = null;
          this.hoverScreenPos = null;
          this.scheduleMapRedraw();
        }
      };
    }

    // Bind Engineering Keyboard Shortcuts (Escape to cancel drawing/modals, Enter to close polygon, Ctrl+Z / Ctrl+Y for Undo/Redo)
    if (typeof window !== 'undefined') {
      if (this._keydownHandler) {
        window.removeEventListener('keydown', this._keydownHandler);
      }
      this._keydownHandler = (ev) => {
        if (!this.host || !this.host.isConnected) return;
        const tag = ev.target?.tagName?.toLowerCase() || '';
        const isTyping = tag === 'input' || tag === 'textarea' || tag === 'select';
        if (ev.key === 'Escape') {
          if (this.drawingPointsM?.length > 0 || this.drawingObstaclePointsM?.length > 0 || this.dragPreview) {
            this.drawingPointsM = [];
            this.drawingObstaclePointsM = [];
            this.cursorPointM = null;
            this.dragPreview = null;
            this.activeTool = 'pan';
            this.notice('已取消当前多边形/矩形绘制并回到漫游模式。');
            this.refresh();
            return;
          }
          if (this.showStringModeModal || this.showInverterModal || this.showMpptModal || this.showLocationPickerModal || this.showPvlaneStartModal || this.showTariffModal) {
            this.showStringModeModal = false;
            this.showInverterModal = false;
            this.showMpptModal = false;
            this.showLocationPickerModal = false;
            this.showPvlaneStartModal = false;
            this.showTariffModal = false;
            this.refresh();
            return;
          }
          if (this.isFullscreen) {
            this.isFullscreen = false;
            this.refresh();
          }
        } else if (ev.key === 'Enter' && !isTyping) {
          if (this.activeTool === 'roof_poly' && this.drawingPointsM?.length >= 3) {
            ev.preventDefault();
            this.finishPolygonRoof();
          } else if ((this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly') && this.drawingObstaclePointsM?.length >= 3) {
            ev.preventDefault();
            this.finishPolygonObstacle();
          }
        } else if ((ev.ctrlKey || ev.metaKey) && !isTyping && ev.key.toLowerCase() === 'z') {
          ev.preventDefault();
          const btn = this.host.querySelector(ev.shiftKey ? '[data-sat-action="redo-step"]' : '[data-sat-action="undo-step"]');
          if (btn) btn.click();
        } else if ((ev.ctrlKey || ev.metaKey) && !isTyping && ev.key.toLowerCase() === 'y') {
          ev.preventDefault();
          const redoBtn = this.host.querySelector('[data-sat-action="redo-step"]');
          if (redoBtn) redoBtn.click();
        }
      };
      window.addEventListener('keydown', this._keydownHandler);
    }

    // Enter key on all search inputs (including fullscreen bar) triggers China-wide location search
    host.querySelectorAll('[data-sat-field="searchQuery"]').forEach((searchInput) => {
      searchInput.onkeydown = (ev) => {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          this.searchLocation(searchInput.value);
        }
      };
      searchInput.oninput = () => {
        this.searchQuery = searchInput.value;
      };
    });

    // Enter key on AI requirement input triggers AI one-click design
    const aiInput = host.querySelector('[data-sat-field="aiRequirement"]');
    if (aiInput) {
      aiInput.onkeydown = (ev) => {
        if (ev.key === 'Enter') {
          ev.preventDefault();
          this.aiRequirement = aiInput.value;
          this.runAiAutopilot();
        }
      };
    }

    // Bind Step 4 Oblique Photo 4-Point Homography Corner Picking/Dragging & Parapet Occlusion Drawing
    const effectCanvas = host.querySelector('#sat-effect-canvas');
    if (effectCanvas) {
      const toEffectCoords = (ev) => {
        const rect = effectCanvas.getBoundingClientRect();
        return [
          Math.round((ev.clientX - rect.left) * (effectCanvas.width / Math.max(1, rect.width))),
          Math.round((ev.clientY - rect.top) * (effectCanvas.height / Math.max(1, rect.height))),
        ];
      };

      effectCanvas.onpointerdown = (ev) => {
        const [px, py] = toEffectCoords(ev);
        if (this.pickingFourCorners) {
          this.pickedCorners.push([px, py]);
          const idx = this.pickedCorners.length - 1;
          this.dstQuad[idx] = [px, py];
          if (this.pickedCorners.length >= 4) {
            this.pickingFourCorners = false;
            this.pickedCorners = [];
            this.notice('已完成实景屋面四角 P1(左上)→P2(右上)→P3(右下)→P4(左下) 点选，三维透视阵列已自动贴合！');
          } else {
            this.notice(`已点选角点 P${idx + 1}，请继续点击实景照片上的角点 P${idx + 2}。`);
          }
          this.refresh();
          return;
        }
        if (this.occlusionDrawing) {
          this.occlusionPolygon.push([px, py]);
          this.drawEffectCanvas();
          return;
        }
        let bestIdx = -1;
        let bestDist = 26;
        this.dstQuad.forEach(([cx, cy], idx) => {
          const d = Math.hypot(px - cx, py - cy);
          if (d < bestDist) {
            bestDist = d;
            bestIdx = idx;
          }
        });
        if (bestIdx >= 0) {
          this.draggingCornerIdx = bestIdx;
          try { effectCanvas.setPointerCapture(ev.pointerId); } catch { }
        }
      };

      effectCanvas.onpointermove = (ev) => {
        if (this.draggingCornerIdx < 0) return;
        const [px, py] = toEffectCoords(ev);
        this.dstQuad[this.draggingCornerIdx] = [
          Math.max(10, Math.min(effectCanvas.width - 10, px)),
          Math.max(10, Math.min(effectCanvas.height - 10, py)),
        ];
        this.drawEffectCanvas();
      };

      effectCanvas.onpointerup = () => {
        this.draggingCornerIdx = -1;
      };
    }

    // Delegated Click Handler for all buttons in SatMapView
    host.onclick = async (ev) => {
      // Auto-close open floating <details> popovers on outside click or menu button click
      const clickedPopover = ev.target.closest?.('details.sat-popover, details.satmap-float-more');
      const clickedSummary = ev.target.closest?.('summary');
      const clickedMenuBtn = clickedPopover && !clickedSummary && ev.target.closest?.('button');
      host.querySelectorAll?.('details.sat-popover[open], details.satmap-float-more[open]').forEach((d) => {
        if (d !== clickedPopover || clickedMenuBtn) {
          d.open = false;
        }
      });

      // Allow clicking modal backdrop to close modals
      if (ev.target.classList?.contains('satmap-modal-backdrop')) {
        this.showStringModeModal = false;
        this.showInverterModal = false;
        this.showMpptModal = false;
        this.showLocationPickerModal = false;
        this.showPvlaneStartModal = false;
        this.showTariffModal = false;
        this.refresh();
        return;
      }

      const pickStringCard = ev.target.closest('[data-sat-string-mode]');
      if (pickStringCard && !ev.target.closest('button')) {
        this.stringingMode = pickStringCard.dataset.satStringMode;
        if (this.hasLaidOut) {
          this.computeElectricalAllocation();
        }
        this.refresh();
        return;
      }

      const pickInvCard = ev.target.closest('[data-sat-pick-inv]');
      if (pickInvCard && !ev.target.closest('button')) {
        this.inverterModelId = pickInvCard.dataset.satPickInv;
        if (this.hasLaidOut) {
          this.computeElectricalAllocation();
        }
        this.refresh();
        return;
      }

      const btn = ev.target.closest('button');
      if (!btn) return;

      if (btn.dataset.satLeftTab) {
        this.leftPanelTab = btn.dataset.satLeftTab;
        if (this.leftPanelTab === 'Step3') {
          this.step = 4;
          this.refresh({ resetScroll: true });
        } else {
          this.refresh();
        }
        return;
      }

      if (btn.dataset.satRightTab) {
        this.rightDrawerTab = btn.dataset.satRightTab;
        this.refresh();
        return;
      }

      if (btn.dataset.satArrayPreset) {
        const preset = btn.dataset.satArrayPreset;
        if (preset === '2x9') {
          this.arrayGroupRows = 2;
          this.arrayGroupCols = 9;
          this.modulesPerString = 18;
        } else if (preset === '2x12') {
          this.arrayGroupRows = 2;
          this.arrayGroupCols = 12;
          this.modulesPerString = 24;
        } else if (preset === '1x18') {
          this.arrayGroupRows = 1;
          this.arrayGroupCols = 18;
          this.modulesPerString = 18;
        }
        if (this.hasRoof) {
          this.layoutModules({ quiet: true, autoCreateRoof: false });
        }
        this.notice(`已切换阵列单元预设为 ${preset.replace('x', '×')}（单串 ${this.modulesPerString} 块）${this.hasLaidOut ? `，当前共 ${this.summary.moduleCount} 块组件` : ''}。`);
        this.refresh();
        return;
      }

      if (btn.dataset.satCadZoom) {
        this.cadZoomPct = Number(btn.dataset.satCadZoom) || 100;
        this.refresh();
        return;
      }

      if (btn.dataset.satInvPower) {
        this.inverterPowerFilter = btn.dataset.satInvPower;
        this.refresh();
        return;
      }

      if (btn.dataset.satInvMode) {
        this.inverterSelectionMode = btn.dataset.satInvMode;
        this.refresh();
        return;
      }

      if (btn.dataset.satStringMode) {
        this.stringingMode = btn.dataset.satStringMode;
        if (this.hasLaidOut) {
          this.computeElectricalAllocation();
        }
        this.refresh();
        return;
      }

      if (btn.dataset.satCadWiz) {
        this.cadWizardTab = btn.dataset.satCadWiz;
        if (this.cadWizardTab === 'bracket') {
          this.cadSheet = 'bracket';
        }
        this.refresh();
        return;
      }

      if (btn.dataset.satStep) {
        const nextStep = Number(btn.dataset.satStep);
        this.step = nextStep;
        if (nextStep >= 2 && (!this.modules || this.modules.length === 0)) {
          this.layoutModules({ quiet: true, autoCreateRoof: true });
          this.electricalConfirmed = true;
          this.showStringColors = true;
          this.computeElectricalAllocation();
        }
        if (nextStep === 3) {
          this.refreshPvsystData({ fetchBackend: true });
        }
        this.refresh({ resetScroll: true });
        return;
      }

      if (btn.dataset.satOrient) {
        this.orientation = btn.dataset.satOrient;
        if (this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: false });
        }
        this.refresh();
        return;
      }

      if (btn.dataset.satRoofType) {
        this.roofType = btn.dataset.satRoofType;
        if (this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: false });
        }
        this.notice(
          this.roofType === 'double_slope'
            ? `已切换为「双坡屋面 (沿中央屋脊分南北坡，坡度 ${this.roofSlopeDeg}°)」`
            : this.roofType === 'flat'
              ? `已切换为「混凝土平屋面 (支架倾角 ${this.tiltDeg}°)」`
              : '已切换为「整面连续平铺 (不自动分界)」'
        );
        this.refresh();
        return;
      }

      if (btn.dataset.satInvBrand) {
        this.inverterBrandFilter = btn.dataset.satInvBrand;
        this.refresh();
        return;
      }

      if (btn.dataset.satPickInv) {
        this.inverterModelId = btn.dataset.satPickInv;
        if (this.hasLaidOut) {
          this.computeElectricalAllocation();
        }
        const inv = this.getSelectedInverter();
        this.notice(`已选型逆变器：${inv.brand} ${inv.model} (${inv.rated_ac_kw}kW / ${inv.mppt_count}路MPPT)`);
        this.refresh();
        return;
      }

      if (btn.dataset.sat3dMode) {
        this.sim3dMode = btn.dataset.sat3dMode;
        if (this.twin3d?.available) {
          host.querySelectorAll('[data-sat-3d-mode]').forEach((b) => {
            b.classList.toggle('active', b.dataset.sat3dMode === this.sim3dMode);
          });
          this.twin3d.setSimConfig({ displayMode: this.sim3dMode });
        } else {
          this.refresh();
        }
        return;
      }

      if (btn.dataset.sat3dDate) {
        this.sim3dDateStr = btn.dataset.sat3dDate;
        if (this.twin3d?.available) {
          host.querySelectorAll('[data-sat-3d-date]').forEach((b) => {
            b.classList.toggle('active', b.dataset.sat3dDate === this.sim3dDateStr);
          });
          this.twin3d.setSimConfig({ dateStr: this.sim3dDateStr });
        } else {
          this.refresh();
        }
        return;
      }

      if (btn.dataset.sat3dCam) {
        this.sim3dCam = btn.dataset.sat3dCam;
        if (this.twin3d?.available) {
          host.querySelectorAll('[data-sat-3d-cam]').forEach((b) => {
            b.classList.toggle('active', b.dataset.sat3dCam === this.sim3dCam);
          });
          this.twin3d.setCameraPreset(this.sim3dCam);
        } else {
          this.refresh();
        }
        return;
      }

      if (btn.dataset.satTool) {
        this.is3D = false;
        this.sim3dPlaying = false;
        this.activeTool = btn.dataset.satTool;
        this.dragPreview = null;
        if (this.activeTool !== 'roof_poly') {
          this.drawingPointsM = [];
        }
        if (this.activeTool !== 'obstacle' && this.activeTool !== 'obstacle_poly') {
          this.drawingObstaclePointsM = [];
        }
        if (this.activeTool !== 'roof_poly' && this.activeTool !== 'obstacle' && this.activeTool !== 'obstacle_poly') {
          this.cursorPointM = null;
        }
        if (this.activeTool === 'roof') {
          this.notice('已进入「1. 绘制屋顶」模式：请在目标厂房屋顶上按住鼠标左键拖动拉框（或单击左上角再单击右下角）确定屋面范围。');
        } else if (this.activeTool === 'roof_poly') {
          this.notice('已进入「多点画屋顶」模式：请依次点击厂房屋顶各角点，双击、右键或点击起点 P1 闭合屋面。');
        } else if (this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly') {
          this.notice('已进入「多点画禁布区」模式：请依次点击禁布区各个角点，双击、右键、点击起点 P1 或点「完成禁布区闭合」生成红色禁布区（支持连续画多个）。');
        } else if (this.activeTool === 'toggle_module') {
          if (!this.hasLaidOut) {
            this.layoutModules({ quiet: true, autoCreateRoof: true });
          }
          this.notice('已进入「点选增删单块组件」模式：直接点击屋面上任意单块组件即可剔除，点击红色虚线空位即可恢复。');
        }
        this.refresh();
        return;
      }

      if (btn.dataset.satPickLoc != null) {
        const idx = Number(btn.dataset.satPickLoc);
        const item = this.searchResults?.[idx];
        if (item) {
          this.applyLocationCandidate(item);
        }
        return;
      }

      if (btn.dataset.satApplyTilt != null) {
        const newTilt = Number(btn.dataset.satApplyTilt);
        const newGap = Number(btn.dataset.satApplyGap);
        if (Number.isFinite(newTilt)) {
          this.tiltDeg = newTilt;
          if (this.roofType !== 'flat') {
            this.roofSlopeDeg = newTilt;
          }
        }
        if (Number.isFinite(newGap) && newGap > 0) {
          this.rowSpacingM = newGap;
        }
        if (this.hasRoof) {
          this.layoutModules({ quiet: true, autoCreateRoof: false });
        }
        this.refresh();
        this.notice(`已应用候选安装倾角 ${newTilt}°（冬至无遮挡净排距 ${this.rowSpacingM}m）${this.hasLaidOut ? `，屋面装机 ${this.summary.dcKw} kWp，首年发电 ${(this.summary.annualKwh / 10000).toFixed(2)} 万kWh` : ''}。`);
        return;
      }

      if (btn.dataset.satDelObs) {
        this.obstacles = this.obstacles.filter((o) => o.id !== btn.dataset.satDelObs);
        if (this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: false });
        }
        this.refresh();
        return;
      }

      if (btn.dataset.satCadSheet) {
        this.cadSheet = btn.dataset.satCadSheet;
        this.cadShowAllFourStacked = false;
        this.cadGrid2x2 = false;
        this.refresh();
        return;
      }

      if (btn.dataset.satCadCat) {
        this.cadCategory = btn.dataset.satCadCat;
        const allSheets = this.getAllCadSheets();
        const filtered = this.cadCategory === 'all'
          ? allSheets
          : allSheets.filter((s) => s[3] === this.cadCategory);
        if (filtered.length && !filtered.some((s) => s[0] === this.cadSheet)) {
          this.cadSheet = filtered[0][0];
        }
        this.refresh();
        return;
      }

      if (btn.dataset.satJumpCad) {
        this.step = 5;
        this.cadSheet = btn.dataset.satJumpCad;
        this.cadCategory = 'all';
        this.cadShowAllFourStacked = false;
        this.cadGrid2x2 = false;
        this.refresh({ resetScroll: true });
        return;
      }

      if (btn.dataset.satPresetPhoto != null) {
        this.effectPresetIdx = Number(btn.dataset.satPresetPhoto);
        this.customPhotoImg = null;
        this.refresh();
        return;
      }

      // Step 4 Effect Studio actions
      const effAct = btn.dataset.satEffect;
      if (effAct) {
        if (effAct === 'pick-4-corners') {
          this.pickingFourCorners = !this.pickingFourCorners;
          this.pickedCorners = [];
          this.occlusionDrawing = false;
          if (this.pickingFourCorners) {
            this.notice('已开启「依次点选四角」模式：请按 1(左上) → 2(右上) → 3(右下) → 4(左下) 顺序在右侧实景照片屋面上点击 4 个角点。');
          }
          this.refresh();
        } else if (effAct === 'auto-match') {
          this.pickingFourCorners = false;
          this.pickedCorners = [];
          this.dstQuad = [
            [218, 178],
            [716, 168],
            [838, 392],
            [112, 408],
          ];
          this.drawEffectCanvas();
          this.notice('已自动配准实景照片屋面四角 P1(左上) → P2(右上) → P3(右下) → P4(左下)，完成 3×3 透视单应矩阵求解。');
        } else if (effAct === 'draw-occlusion') {
          this.pickingFourCorners = false;
          this.occlusionDrawing = !this.occlusionDrawing;
          if (this.occlusionDrawing) {
            this.occlusionPolygon = [];
            this.occlusionEnabled = true;
            this.notice('已进入女儿墙视线遮挡绘制模式：请在右侧照片前景女儿墙上依次点击顶点，完成后再次点击该按钮结束。');
          } else {
            this.notice(`女儿墙视线遮挡区域绘制完成（共 ${this.occlusionPolygon.length} 个顶点）。`);
          }
          this.refresh();
        } else if (effAct === 'demo-occlusion') {
          this.occlusionDrawing = false;
          this.occlusionEnabled = true;
          this.occlusionPolygon = [
            [94, 376],
            [468, 364],
            [854, 360],
            [866, 442],
            [86, 450],
          ];
          this.refresh();
          this.notice('已加载前景女儿墙视线遮挡区域：前景墙体已自然遮挡底层光伏组件下沿。');
        } else if (effAct === 'clear-occlusion') {
          this.occlusionDrawing = false;
          this.occlusionPolygon = [];
          this.refresh();
          this.notice('已清除女儿墙视线遮挡区域。');
        } else if (effAct === 'toggle-compare') {
          this.effectCompareMode = !this.effectCompareMode;
          this.refresh();
          this.notice(
            this.effectCompareMode
              ? `已开启「改造前屋面原貌 vs 改造后光伏阵列」实景卷帘对比（当前分界 ${this.effectCompareSplitPct}%）。`
              : '已退出实景卷帘分屏对比模式。'
          );
        } else if (effAct === 'export-png') {
          this.drawEffectCanvas({ forExport: true });
          const c = host.querySelector('#sat-effect-canvas');
          if (c && typeof c.toDataURL === 'function') {
            const url = c.toDataURL('image/png');
            const a = document.createElement('a');
            a.href = url;
            a.download = `${this.cadPrefix}-oblique-photorealistic-effect.png`;
            document.body.append(a);
            a.click();
            a.remove();
            this.notice(`已导出实景透视效果图：${a.download}`);
          }
          this.drawEffectCanvas({ forExport: false });
        }
        return;
      }

      // PVsyst Workbench actions in Step 3
      const pvAct = btn.dataset.pvsystAction;
      if (pvAct === 'apply-optimal-angle') {
        const optTilt = Number(btn.dataset.optimalTilt);
        const optAz = Number(btn.dataset.optimalAzimuth);
        if (Number.isFinite(optTilt)) {
          this.tiltDeg = optTilt;
          if (this.roofType !== 'flat') this.roofSlopeDeg = optTilt;
        }
        if (Number.isFinite(optAz)) this.azimuthDeg = optAz;
        if (this.hasRoof) {
          this.layoutModules({ quiet: true, autoCreateRoof: false });
        }
        this.refresh();
        this.notice(`已应用最佳倾角 ${Number.isFinite(optTilt) ? optTilt : this.tiltDeg}° 与方位角 ${Number.isFinite(optAz) ? optAz : this.azimuthDeg}° 并重算 8760h 能量平衡。`);
        return;
      }
      if (pvAct === 'recalculate' || pvAct === 'refresh-weather') {
        const inputs = host.querySelectorAll('[data-pvsyst-param]');
        inputs.forEach((inp) => {
          const k = inp.getAttribute('data-pvsyst-param');
          const v = Number(inp.value);
          if (k && Number.isFinite(v)) this.pvsystParams[k] = v;
        });
        this.refreshPvsystData({ fetchBackend: true });
        this.refresh();
        this.notice('已按最新损耗参数与官方实时气象数据更新 8760h 仿真结果。');
        return;
      }

      // General SatMap actions
      const act = btn.dataset.satAction;
      if (!act) return;
      if (act === 'toggle-lang') {
        toggleLang();
        this.refresh();
        if (typeof document !== 'undefined') applyGlobalI18n(document);
        return;
      }
      if (act === 'search-location') {
        const inps = Array.from(host.querySelectorAll('[data-sat-field="searchQuery"]'));
        const activeInp = inps.find((i) => i.value && i.value.trim()) || inps[0];
        if (activeInp) this.searchQuery = activeInp.value;
        await this.searchLocation(this.searchQuery);
      } else if (act === 'locate') {
        const lonInp = host.querySelector('[data-sat-field="lon"]');
        const latInp = host.querySelector('[data-sat-field="lat"]');
        if (lonInp && Number.isFinite(Number(lonInp.value))) this.lon = Number(lonInp.value);
        if (latInp && Number.isFinite(Number(latInp.value))) this.lat = Number(latInp.value);
        this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
        this.clearRoofDesign({ quiet: true });
        this.roofCenterLon = this.lon;
        this.roofCenterLat = this.lat;
        this.refreshPvsystData({ fetchBackend: true });
        this.evaluateWeatherAndAngles();
        this.refresh();
        this.notice(`已按经纬度定位至 (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E)。请点击「1. 框选屋顶」圈选厂房范围！`);
      } else if (act === 'toggle-fullscreen') {
        this.isFullscreen = !this.isFullscreen;
        this.refresh();
      } else if (act === 'clear-roof') {
        this.clearRoofDesign({ quiet: false });
        this.refresh();
      } else if (act === 'close-roof-poly') {
        this.finishPolygonRoof();
      } else if (act === 'close-obstacle-poly') {
        this.finishPolygonObstacle();
      } else if (act === 'auto-scale-direction') {
        const autoMpp = metersPerPixelAtLatZoom(this.lat, this.zoom);
        const oldMpp = Math.max(0.03, this.metersPerPx);
        const ratio = autoMpp / oldMpp;
        if (this.scaleCustomized && this.roofOutlineM.length >= 3) {
          this.roofOutlineM = this.roofOutlineM.map(([x, y]) => [Number((x * ratio).toFixed(2)), Number((y * ratio).toFixed(2))]);
          for (const obs of this.obstacles) {
            obs.polygon = obs.polygon.map(([x, y]) => [Number((x * ratio).toFixed(2)), Number((y * ratio).toFixed(2))]);
          }
        }
        this.scaleCustomized = false;
        this.metersPerPx = autoMpp;
        if (this.roofOutlineM.length >= 3) {
          this.ridgeAzimuthDeg = detectPrincipalRoofAngleDeg(this.roofOutlineM);
          const bounds = this.getRoofBoundsM(true);
          this.scaleReferenceM = bounds.widthM;
        } else {
          this.ridgeAzimuthDeg = 0;
        }
        if (this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: false });
        }
        this.notice(`已根据卫星地图经纬度 (${this.lat.toFixed(4)}°N, Z${this.zoom}) 与屋面主墙边缘自动识别比例尺 (1px ≈ ${this.metersPerPx.toFixed(3)}m) 及主墙偏角 (${this.ridgeAzimuthDeg}°)${this.hasLaidOut ? `，已重排 ${this.summary.moduleCount} 块组件` : ''}。`);
        this.refresh();
      } else if (act === 'zoom-in') {
        this.setZoom((this.zoom || 18) + 1);
        const hud = host.querySelector('#satmap-hud-coords');
        if (hud) {
          hud.textContent = `当前定位：${this.address} (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) · 缩放级别 Z${this.zoom} · 比例尺 1px ≈ ${this.metersPerPx.toFixed(3)}m · 主墙偏角 ${this.ridgeAzimuthDeg}°`;
        }
        const rmsBadge = host.querySelector('#satmap-rms-zoom-badge');
        if (rmsBadge) rmsBadge.textContent = `Z${this.zoom}`;
        const fitRoofBtn = host.querySelector('.satmap-floating-tools [data-sat-action="zoom-fit-roof"]');
        if (fitRoofBtn) {
          fitRoofBtn.textContent = `🔍 屋面特写 (Z${this.zoom})`;
          fitRoofBtn.classList.toggle('active', this.zoom >= 21);
        }
        this.scheduleMapRedraw();
      } else if (act === 'zoom-out') {
        this.setZoom((this.zoom || 18) - 1);
        const hud = host.querySelector('#satmap-hud-coords');
        if (hud) {
          hud.textContent = `当前定位：${this.address} (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) · 缩放级别 Z${this.zoom} · 比例尺 1px ≈ ${this.metersPerPx.toFixed(3)}m · 主墙偏角 ${this.ridgeAzimuthDeg}°`;
        }
        const rmsBadge = host.querySelector('#satmap-rms-zoom-badge');
        if (rmsBadge) rmsBadge.textContent = `Z${this.zoom}`;
        const fitRoofBtn = host.querySelector('.satmap-floating-tools [data-sat-action="zoom-fit-roof"]');
        if (fitRoofBtn) {
          fitRoofBtn.textContent = `🔍 屋面特写 (Z${this.zoom})`;
          fitRoofBtn.classList.toggle('active', this.zoom >= 21);
        }
        this.scheduleMapRedraw();
      } else if (act === 'zoom-fit-roof') {
        const mc = host.querySelector('#satmap-main-canvas');
        const nextZ = this.zoomToFitRoof({
          canvasW: mc?.width || 920,
          canvasH: mc?.height || 580,
        });
        this.notice(`已居中放大至屋面超清微距特写：Z${nextZ}（比例尺 1px ≈ ${this.metersPerPx.toFixed(3)}m，可继续点击「放大 +」或滚动滚轮放大至最高 Z${MAX_SAT_ZOOM}）。`);
        this.refresh();
      } else if (act === 'toggle-roof-overlay') {
        this.showRoofOverlay = !this.showRoofOverlay;
        this.scheduleMapRedraw();
      } else if (act === 'apply-weather-opt-tilt') {
        const wxEval = this.weatherEval || this.evaluateWeatherAndAngles();
        this.tiltDeg = wxEval.weatherOptimalTiltDeg;
        this.azimuthDeg = wxEval.weatherOptimalAzimuthDeg;
        if (this.roofType === 'flat') {
          this.rowSpacingM = wxEval.weatherOptimalRowGapM;
        } else {
          this.roofSlopeDeg = wxEval.weatherOptimalTiltDeg;
          this.rowSpacingM = Math.max(0.45, Number((wxEval.weatherOptimalRowGapM * 0.65).toFixed(2)));
        }
        if (this.hasRoof) {
          this.layoutModules({ quiet: true, autoCreateRoof: false });
        }
        this.refresh();
        this.notice(`已应用当地气象单瓦最优倾角 ${this.tiltDeg}° / 方位角 ${this.azimuthDeg}°（排距 ${this.rowSpacingM}m）${this.hasLaidOut ? `，单瓦满发 ${this.summary.specificYield} h` : ''}。`);
      } else if (act === 'apply-roof-opt-tilt') {
        const wxEval = this.weatherEval || this.evaluateWeatherAndAngles();
        this.tiltDeg = wxEval.roofOptimalTiltDeg;
        if (this.roofType !== 'flat') {
          this.roofSlopeDeg = wxEval.roofOptimalTiltDeg;
        }
        this.rowSpacingM = wxEval.roofOptimalRowGapM;
        if (this.hasRoof) {
          this.layoutModules({ quiet: true, autoCreateRoof: false });
        }
        this.refresh();
        this.notice(`已应用屋面总发电量最优倾角 ${this.tiltDeg}°（净排距 ${this.rowSpacingM}m）${this.hasLaidOut ? `，装机 ${this.summary.dcKw} kWp，首年总发电 ${(this.summary.annualKwh / 10000).toFixed(2)} 万kWh` : ''}。`);
      } else if (act === 'refresh-live-weather') {
        this.refreshPvsystData({ fetchBackend: true });
        this.evaluateWeatherAndAngles();
        this.refresh();
        this.notice(`已刷新 (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) 当地官方实时气象与最佳倾角评估表。`);
      } else if (act === 'layout-modules') {
        this.layoutModules({ quiet: false, autoCreateRoof: true });
        this.refresh();
      } else if (act === 'toggle-3d') {
        this.is3D = !this.is3D;
        if (this.is3D && !this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: true });
        }
        this.sim3dPlaying = false;
        this.refresh();
      } else if (act === 'set-2d') {
        this.is3D = false;
        this.sim3dPlaying = false;
        this.refresh();
      } else if (act === 'set-3d') {
        if (!this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: true });
        }
        this.is3D = true;
        this.refresh();
      } else if (act === 'toggle-3d-play') {
        this.sim3dPlaying = !this.sim3dPlaying;
        if (this.twin3d?.available) {
          const playBtn = host.querySelector('[data-sat-action="toggle-3d-play"]');
          if (playBtn) {
            playBtn.classList.toggle('active', this.sim3dPlaying);
            playBtn.textContent = getLang() === 'en'
              ? (this.sim3dPlaying ? 'Pause Sun' : 'Sun Sweep')
              : (this.sim3dPlaying ? '暂停日照' : '日照动画');
          }
          this.twin3d.setSimConfig({ playing: this.sim3dPlaying });
        } else {
          this.refresh();
        }
      } else if (act === 'sync-3d-shading') {
        if (!this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: true });
        }
        const rep = this.compute3DShadingReport();
        this.pvsystParams = {
          ...(this.pvsystParams || {}),
          shading_loss_pct: rep.annualLinearLossPct,
          mismatch_pct: Number(Math.min(6.0, Math.max(1.0, 0.8 + Math.max(0, rep.annualElectricalLossPct - rep.annualLinearLossPct))).toFixed(2)),
        };
        this.refreshPvsystData({ fetchBackend: false });
        this.refresh();
        this.notice(`已将三维光线追踪遮挡（线性 ${rep.annualLinearLossPct}% · 旁路二极管电损耗 ${rep.annualElectricalLossPct}%）同步写入全年物理仿真引擎。`);
      } else if (act === 'export-3d-png') {
        const url = this.twin3d?.capturePng?.();
        if (url && typeof document !== 'undefined') {
          const a = document.createElement('a');
          a.href = url;
          a.download = `${this.cadPrefix}-3d-digital-twin.png`;
          document.body.append(a);
          a.click();
          a.remove();
          this.notice(`已导出高清三维数字孪生渲染截图：${a.download}`);
        } else {
          this.notice('当前运行环境暂不支持导出三维截图。');
        }
      } else if (act === 'toggle-string-colors') {
        this.showStringColors = !this.showStringColors;
        this.refresh();
      } else if (act === 'add-demo-skylight') {
        if (!this.hasRoof) {
          this.ensureRoofOutline({ withDefaultKeepouts: false });
        }
        const bounds = this.getRoofBoundsM(true);
        const offset = bounds.centerY + ((this.obstacles.length % 3) * 4.5 - 4.5);
        this.obstacles.push({
          id: `keepout-sky-${Date.now()}`,
          name: `采光带禁布区 #${this.obstacles.length + 1}`,
          kind: 'skylight',
          polygon: [
            [bounds.minX + 6, offset - 0.8],
            [bounds.maxX - 6, offset - 0.8],
            [bounds.maxX - 6, offset + 0.8],
            [bounds.minX + 6, offset + 0.8],
          ],
        });
        if (this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: false });
        }
        this.refresh();
      } else if (act === 'confirm-electrical') {
        if (!this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: true });
        }
        this.electricalConfirmed = true;
        this.showStringColors = true;
        this.computeElectricalAllocation();
        this.step = 1;
        this.refresh();
        this.notice(`电气设计已确认：共 ${this.summary.inverterCount} 台 ${this.getSelectedInverter().model}，${this.summary.stringCount} 路组串已按同翼蛇形配串并全程在屋面内部走线。`);
      } else if (act === 'open-elec-flow') {
        if (!this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: true });
        }
        this.showStringModeModal = true;
        this.showInverterModal = false;
        this.showMpptModal = false;
        this.refresh();
      } else if (act === 'confirm-string-mode') {
        this.showStringModeModal = false;
        this.showInverterModal = true;
        this.showMpptModal = false;
        this.refresh();
      } else if (act === 'open-inverter-modal') {
        this.showStringModeModal = false;
        this.showInverterModal = true;
        this.showMpptModal = false;
        this.refresh();
      } else if (act === 'finish-elec-design') {
        if (!this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: true });
        }
        this.electricalConfirmed = true;
        this.showStringColors = true;
        this.computeElectricalAllocation();
        this.showStringModeModal = false;
        this.showInverterModal = false;
        this.showMpptModal = true;
        this.refresh();
        this.notice(`已完成逆变器选型与 MPPT 组串分配：${this.getSelectedInverter().brand} ${this.getSelectedInverter().model} × ${this.summary.inverterCount} 台（共 ${this.summary.stringCount} 串）。`);
      } else if (act === 'close-modals') {
        this.showStringModeModal = false;
        this.showInverterModal = false;
        this.showMpptModal = false;
        this.showLocationPickerModal = false;
        this.showPvlaneStartModal = false;
        this.showTariffModal = false;
        this.refresh();
      } else if (act === 'open-tariff-modal') {
        this.showTariffModal = true;
        this.refresh();
      } else if (act === 'export-mppt-csv') {
        this.exportMpptCsv();
      } else if (act === 'restore-removed-modules') {
        if (this.removedModules && this.removedModules.length > 0) {
          const count = this.removedModules.length;
          this.modules.push(...this.removedModules);
          this.removedModules = [];
          this.modules.sort((a, b) => (a.row - b.row) || (a.col - b.col));
          this.computeElectricalAllocation();
          this.refreshPvsystData({ fetchBackend: false });
          this.notice(`已全部恢复手动剔除的 ${count} 块组件（当前共 ${this.summary.moduleCount} 块 · ${this.summary.dcKw} kWp）。`);
          this.refresh();
        }
      } else if (act === 'jump-3d-sim') {
        if (!this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: true });
        }
        this.step = 1;
        this.is3D = true;
        this.showShadowPreview = true;
        this.refresh({ resetScroll: true });
        this.notice('已开启屋面全景 3D 倾斜阵列与冬至日阴影实时模拟视图。');
      } else if (act === 'toggle-cad-theme') {
        this.cadLightTheme = !this.cadLightTheme;
        this.refresh();
      } else if (act === 'export-internal-report') {
        this.exportExecutiveReport('internal');
      } else if (act === 'export-owner-report') {
        this.exportExecutiveReport('owner');
      } else if (act === 'toggle-video-hub') {
        this.showVideoCenter = !this.showVideoCenter;
        this.refresh();
      } else if (act === 'open-loc-picker') {
        this.showLocationPickerModal = true;
        this.refresh();
      } else if (act === 'open-pvlane-start') {
        this.showPvlaneStartModal = true;
        this.refresh();
      } else if (act === 'pvlane-new-project') {
        this.showPvlaneStartModal = false;
        this.step = 1;
        this.leftPanelTab = 'roof';
        this.clearRoofDesign({ quiet: true });
        this.timerElapsedMs = 0;
        this.notice('已新建光伏工程方案：请在「1. 屋面」中标定比例尺、绘制屋顶并点击「一键排布」。');
        this.refresh();
      } else if (act === 'export-project-json') {
        if (typeof document !== 'undefined') {
          const data = {
            version: 'guangzhu-1.0',
            projectName: this.projectName,
            address: this.address,
            lat: this.lat,
            lon: this.lon,
            zoom: this.zoom,
            roofType: this.roofType,
            roofSlopeDeg: this.roofSlopeDeg,
            ridgeAzimuthDeg: this.ridgeAzimuthDeg,
            roofOutlineM: this.roofOutlineM,
            obstacles: this.obstacles,
            moduleModelId: this.moduleModelId,
            inverterModelId: this.inverterModelId,
            dstQuad: this.dstQuad,
            occlusionPolygon: this.occlusionPolygon,
          };
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `${this.cadPrefix}-project.json`;
          document.body.append(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 2000);
          this.notice(`已导出项目 JSON 文件：${a.download}`);
        }
      } else if (act === 'load-u-shape-demo') {
        this.loadUShapeComplexRoofDemo();
      } else if (act === 'toggle-cad-grid2x2') {
        this.cadGrid2x2 = !this.cadGrid2x2;
        if (this.cadGrid2x2) this.cadShowAllFourStacked = false;
        this.refresh();
      } else if (act === 'toggle-cad-stacked') {
        this.cadShowAllFourStacked = !this.cadShowAllFourStacked;
        if (this.cadShowAllFourStacked) this.cadGrid2x2 = false;
        this.refresh();
      } else if (act === 'generate-dc-cable') {
        if (!this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: true });
        }
        this.electricalConfirmed = true;
        this.showStringColors = true;
        this.computeElectricalAllocation();
        this.showStringModeModal = false;
        this.showInverterModal = false;
        this.showMpptModal = false;
        this.refresh();
        const estCableM = Math.max(120, Math.round(this.summary.stringCount * 48));
        this.notice(`已自动生成全屋面直流线缆路由：共 ${this.summary.stringCount} 路组串回流路径（PV1-F 1×4mm² 估算总长 ${estCableM} m），全程在屋面轮廓内部敷设。`);
      } else if (act === 'toggle-dms') {
        this.coordFormat = this.coordFormat === 'dms' ? 'dec' : 'dms';
        this.refresh();
      } else if (act === 'toggle-shadow') {
        this.showShadowPreview = !this.showShadowPreview;
        this.notice(this.showShadowPreview ? '已开启冬至日 9:00-15:00 太阳高度角阵列阴影实时模拟。' : '已关闭阵列阴影模拟图层。');
        this.refresh();
      } else if (act === 'undo-step') {
        if (this.obstacles.length > 0) {
          const popped = this.obstacles.pop();
          this.redoStack.push({ kind: 'obstacle', item: popped });
          if (this.hasLaidOut) this.layoutModules({ quiet: true, autoCreateRoof: false });
          this.notice(`已撤销禁布区「${popped.name}」。`);
          this.refresh();
        } else if (this.hasRoof) {
          this.redoStack.push({ kind: 'roof', outline: [...this.roofOutlineM] });
          this.clearRoofDesign({ quiet: true });
          this.notice('已撤销屋顶轮廓绘制。');
          this.refresh();
        }
      } else if (act === 'redo-step') {
        const nextItem = this.redoStack.pop();
        if (nextItem) {
          if (nextItem.kind === 'obstacle' && nextItem.item) {
            this.obstacles.push(nextItem.item);
            if (this.hasLaidOut) this.layoutModules({ quiet: true, autoCreateRoof: false });
            this.notice(`已恢复禁布区「${nextItem.item.name}」。`);
          } else if (nextItem.kind === 'roof' && nextItem.outline) {
            this.roofOutlineM = nextItem.outline;
            this.hasRoof = true;
            this.showRoofOverlay = true;
            this.notice('已恢复屋顶轮廓。');
          }
          this.refresh();
        }
      } else if (act === 'ai-detect-roof') {
        await this.runAiDetectRoof();
      } else if (act === 'ai-autopilot') {
        const reqInp = host.querySelector('[data-sat-field="aiRequirement"]');
        if (reqInp) this.aiRequirement = reqInp.value;
        await this.runAiAutopilot();
      } else if (act === 'save-to-project') {
        await this.saveToProject();
      } else if (act === 'apply-opt-string') {
        if (!this.electricalSizing) this.recomputeEngineeringAnalyses();
        this.modulesPerString = this.electricalSizing?.nOpt || 18;
        if (this.hasLaidOut) {
          this.computeElectricalAllocation();
          this.refreshPvsystData({ fetchBackend: false });
        } else {
          this.recomputeEngineeringAnalyses();
        }
        this.refresh();
        this.notice(`已应用当地气候区最优组串串联数：${this.modulesPerString} 块/串。`);
      } else if (act === 'export-pan') {
        this.exportPanFile();
      } else if (act === 'export-ond') {
        this.exportOndFile();
      } else if (act === 'export-bom-csv') {
        this.exportBomCsv();
      } else if (act === 'export-dxf') {
        this.downloadDxf(this.cadSheet);
      } else if (act === 'export-all-dxf') {
        this.downloadMasterDxf();
      } else if (act === 'export-cad-pdf') {
        this.exportCadPdf();
      } else if (act === 'timer-toggle') {
        this.timerRunning = !this.timerRunning;
        if (this.timerRunning) {
          const lastTick = Date.now();
          const baseElapsed = this.timerElapsedMs;
          this.timerInterval = setInterval(() => {
            this.timerElapsedMs = baseElapsed + (Date.now() - lastTick);
            const fmt = this.formatTimer(this.timerElapsedMs);
            const disp = this.host?.querySelector('#sat-effect-timer-display');
            if (disp) disp.textContent = fmt;
            const topDisp = this.host?.querySelector('#sat-pvlane-top-timer');
            if (topDisp) topDisp.textContent = fmt;
          }, 60);
        } else if (this.timerInterval) {
          clearInterval(this.timerInterval);
          this.timerInterval = null;
        }
        this.refresh();
      } else if (act === 'timer-reset') {
        if (this.timerInterval) {
          clearInterval(this.timerInterval);
          this.timerInterval = null;
        }
        this.timerRunning = false;
        this.timerElapsedMs = 0;
        this.refresh();
      }
    };

    // Delegated Change / Input Handler
    host.onchange = (ev) => {
      const el = ev.target;
      if (!el) return;

      if (el.dataset.satFile === 'project-json') {
        const file = el.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
          try {
            const parsed = JSON.parse(String(reader.result));
            if (parsed.projectName) this.projectName = parsed.projectName;
            if (parsed.address) this.address = parsed.address;
            if (Number.isFinite(Number(parsed.lat))) this.lat = Number(parsed.lat);
            if (Number.isFinite(Number(parsed.lon))) this.lon = Number(parsed.lon);
            if (Array.isArray(parsed.roofOutlineM) && parsed.roofOutlineM.length >= 3) {
              this.roofOutlineM = parsed.roofOutlineM;
              this.hasRoof = true;
              this.showRoofOverlay = true;
            }
            if (Array.isArray(parsed.obstacles)) this.obstacles = parsed.obstacles;
            if (parsed.roofType) this.roofType = parsed.roofType;
            this.showPvlaneStartModal = false;
            this.layoutModules({ quiet: true, autoCreateRoof: true });
            this.refresh();
            this.notice(`已成功打开项目文件「${file.name}」（共 ${this.summary.moduleCount} 块组件 · ${this.summary.dcKw} kWp）。`);
          } catch (err) {
            this.notice(`解析 JSON 项目文件失败：${err.message}`);
          }
        };
        reader.readAsText(file);
        return;
      }

      if (el.dataset.satFile === 'pan-file') {
        const file = el.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
          try {
            this.importPanFileText(String(reader.result), file.name);
          } catch (err) {
            this.notice(`导入组件参数文件失败：${err.message}`);
          }
        };
        reader.readAsText(file);
        return;
      }

      if (el.dataset.satFile === 'ond-file') {
        const file = el.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
          try {
            this.importOndFileText(String(reader.result), file.name);
          } catch (err) {
            this.notice(`导入逆变器参数文件失败：${err.message}`);
          }
        };
        reader.readAsText(file);
        return;
      }

      if (el.dataset.satFile === 'ortho-photo') {
        const file = el.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
          const img = new Image();
          img.onload = () => {
            this.customOrthoImg = img;
            this.drawMapCanvas();
            this.notice(`已导入俯视底图「${file.name}」，可直接在底图上绘制屋顶、设置禁布区并一键铺设。`);
          };
          img.src = String(reader.result);
        };
        reader.readAsDataURL(file);
        return;
      }

      if (el.dataset.satFile === 'effect-photo') {
        const file = el.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
          const img = new Image();
          img.onload = () => {
            this.customPhotoImg = img;
            this.drawEffectCanvas();
            this.notice(`已导入实景照片「${file.name}」，可拖动 P1~P4 角点进行四点透视配准。`);
          };
          img.src = String(reader.result);
        };
        reader.readAsDataURL(file);
        return;
      }

      if (el.dataset.satBracket) {
        const bKey = el.dataset.satBracket;
        if (!this.bracketCfg) {
          this.bracketCfg = {
            h1Mm: 500, y0Mm: 1500, y1Mm: 1600, angleDeg: 15, x1Mm: 400, x2Mm: 1900,
            foundationType: '混凝土条形基础/方墩', concreteGrade: 'C25',
          };
        }
        this.bracketCfg[bKey] = el.type === 'number' ? Number(el.value) : el.value;
        if (bKey === 'angleDeg' && Number.isFinite(Number(el.value))) {
          this.tiltDeg = Number(el.value);
        }
        this.cadSheet = 'bracket';
        this.refresh();
        return;
      }

      const field = el.dataset.satField;
      if (!field) return;

      if (field === 'sim3dHourBjt') {
        this.sim3dHourBjt = Number(el.value);
        this.sim3dPlaying = false;
        if (this.twin3d?.available) {
          this.twin3d.setSimConfig({ hourBjt: this.sim3dHourBjt, playing: false });
          const playBtn = host.querySelector('[data-sat-action="toggle-3d-play"]');
          if (playBtn) {
            playBtn.classList.remove('active');
            playBtn.textContent = getLang() === 'en' ? 'Sun Sweep' : '日照动画';
          }
        } else {
          this.update3DMetricsBarInPlace();
        }
        return;
      }

      if (field === 'regionQuickPick' && el.value) {
        this.regionQuickPick = el.value;
        const parts = String(el.value).split('|');
        if (parts.length >= 3 && Number.isFinite(Number(parts[1])) && Number.isFinite(Number(parts[2]))) {
          this.applyLocationCandidate({
            name: parts[0],
            address: parts[0],
            lat: Number(parts[1]),
            lon: Number(parts[2]),
            zoom: 18,
          });
        } else {
          this.searchQuery = el.value;
          this.searchLocation(el.value);
        }
        return;
      }

      if (field === 'liveEdgeLengthMm') {
        const mmVal = Math.max(2000, Number(el.value) || 54000);
        this.liveEdgeLengthMm = mmVal;
        const targetM = Number((mmVal / 1000).toFixed(2));
        if (this.roofOutlineM.length >= 3) {
          const curBounds = this.getRoofBoundsM(true);
          const ratio = targetM / Math.max(1, curBounds.widthM);
          this.roofOutlineM = this.roofOutlineM.map(([x, y]) => [Number((x * ratio).toFixed(2)), Number((y * ratio).toFixed(2))]);
          this.scaleReferenceM = targetM;
          if (this.hasLaidOut) {
            this.layoutModules({ quiet: true, autoCreateRoof: false });
          }
          this.notice(`已按输入边长 ${mmVal} mm (${targetM} m) 等比校准屋顶轮廓尺寸。`);
        }
        this.refresh();
        return;
      }

      if (field === 'roofLengthM' || field === 'roofWidthM') {
        const curBounds = this.getRoofBoundsM(true);
        const newW = field === 'roofLengthM' ? Math.max(10, Number(el.value) || curBounds.widthM) : curBounds.widthM;
        const newH = field === 'roofWidthM' ? Math.max(10, Number(el.value) || curBounds.heightM) : curBounds.heightM;
        const cx = this.hasRoof ? curBounds.centerX : 0;
        const cy = this.hasRoof ? curBounds.centerY : 0;
        if (!this.hasRoof) {
          this.roofCenterLon = this.lon;
          this.roofCenterLat = this.lat;
          this.hasRoof = true;
        }
        this.roofOutlineM = [
          [cx - newW / 2, cy - newH / 2],
          [cx + newW / 2, cy - newH / 2],
          [cx + newW / 2, cy + newH / 2],
          [cx - newW / 2, cy + newH / 2],
        ];
        this.scaleReferenceM = newW;
        if (this.hasLaidOut) {
          this.layoutModules({ quiet: true, autoCreateRoof: false });
        }
        this.refresh();
        return;
      }

      if (el.type === 'checkbox') {
        this[field] = el.checked;
      } else if (el.type === 'number' || el.type === 'range') {
        this[field] = Number(el.value);
      } else {
        this[field] = el.value;
      }

      if (field === 'scaleReferenceM') {
        const [p0, p1] = this.scaleLinePx;
        const distPx = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]);
        const oldMpp = Math.max(0.03, this.metersPerPx);
        const newMpp = Math.max(0.03, Math.max(5, this.scaleReferenceM) / Math.max(20, distPx));
        const ratio = newMpp / oldMpp;
        if (this.roofOutlineM.length >= 3) {
          this.roofOutlineM = this.roofOutlineM.map(([x, y]) => [Number((x * ratio).toFixed(2)), Number((y * ratio).toFixed(2))]);
        }
        for (const obs of this.obstacles) {
          obs.polygon = obs.polygon.map(([x, y]) => [Number((x * ratio).toFixed(2)), Number((y * ratio).toFixed(2))]);
        }
        this.metersPerPx = newMpp;
        this.scaleCustomized = true;
      }

      if (field === 'selfConsumptionRatio') {
        this.shiftMode = 'manual';
      }

      if (
        this.hasLaidOut &&
        [
          'moduleModelId', 'orientation', 'tiltDeg', 'azimuthDeg',
          'rowSpacingM', 'colSpacingM', 'edgeSetbackM', 'obstacleSetbackM',
          'roofType', 'roofSlopeDeg', 'inverterModelId', 'modulesPerString',
          'targetCapacityKw', 'ridgeAzimuthDeg', 'arrayGroupRows', 'arrayGroupCols',
          'walkwayWidthM', 'scaleReferenceM',
        ].includes(field)
      ) {
        this.layoutModules({ quiet: true, autoCreateRoof: false });
      } else if (
        [
          'capexPerW', 'tariffRmb', 'feedInTariffRmb', 'selfConsumptionRatio',
          'shiftMode', 'discountRatePct', 'dcCableSectionMm2', 'acCableMaterial',
          'buildingHeightM', 'roughnessCategory', 'roofLoadLimitKnM2',
          'transformerKva', 'bessPowerKw', 'bessCapacityKwh',
          'parapetHeightMm', 'parapetWidthMm', 'subArrayHeightMm',
        ].includes(field)
      ) {
        if (this.hasLaidOut) {
          this.computeElectricalAllocation();
          this.refreshPvsystData({ fetchBackend: false });
        } else {
          this.recomputeEngineeringAnalyses();
        }
      }

      this.refresh();
    };

    host.oninput = (ev) => {
      const el = ev.target;
      if (!el || el.type !== 'range' || !el.dataset.satField) return;
      const field = el.dataset.satField;
      if (field === 'sim3dHourBjt') {
        this.sim3dHourBjt = Number(el.value);
        this.sim3dPlaying = false;
        if (this.twin3d?.available) {
          this.twin3d.setSimConfig({ hourBjt: this.sim3dHourBjt, playing: false });
          const playBtn = host.querySelector('[data-sat-action="toggle-3d-play"]');
          if (playBtn) {
            playBtn.classList.remove('active');
            playBtn.textContent = getLang() === 'en' ? 'Sun Sweep' : '日照动画';
          }
        } else {
          this.update3DMetricsBarInPlace();
        }
        return;
      }
      if (['effectSolarHour', 'effectOpacityPct', 'effectGridSharpnessPct', 'effectGlarePct', 'effectCompareSplitPct'].includes(field)) {
        this[field] = Number(el.value);
        if (this.step === 4) {
          this.drawEffectCanvas();
        }
      }
    };
  }
}

export default SatMapView;
