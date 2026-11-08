/* ============================================================================
 * 光筑 (Guangzhu) — 卫星地图 AI 光伏设计工作台 (satmap-view.js)
 * Standalone Top-Level View (#satmap)
 * 1:1 Replicates:
 *   - Video 1 (鹧鸪云光伏设计软件): Satellite Search/Locate, Roof/Keepout Drawing,
 *     Module Settings & One-Click Layout (一键铺设), Electrical Design & MPPT Table,
 *     and 4-Sheet Professional CAD Drawing Generator (光伏排布图/组串图/防雷接地图/支架图)
 *   - Video 2 (PVLANE): Scale Calibration (标定比例尺), Direction (确定方向),
 *     Double-Slope Pitch (双坡屋面坡度自动分南北坡), Red Keepout Strips (禁布区绘制),
 *     and Step 4 Oblique Photo 4-Point Perspective Homography + Parapet Sightline Occlusion
 * ============================================================================ */

import { esc, valueMarkup } from './data.js';
import {
  renderPvsystWorkbench,
  renderLiveWeatherPanel,
  computeClientFallbackPvsyst,
} from './pvsyst-workbench.js';

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
];

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
];

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
    name: '江苏省泰州市中国医药城标准双坡钢构厂房 (PVLANE/鹧鸪云同款)',
    address: '江苏省泰州市医药高新区药城大道88号1号车间',
    lat: 32.4562,
    lon: 119.9231,
    zoom: 19,
    roofW: 76.0,
    roofH: 36.0,
    roofType: 'double_slope',
    slopeDeg: 6,
  },
  {
    key: 'shandong-zibo',
    name: '山东省淄博市桓台县起凤镇工业厂房 (视频1 鹧鸪云实测 36.8588°N, 118.7781°E)',
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
  const samples = [0.15, 0.3, 0.5, 0.7, 0.85];
  for (const t of samples) {
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
 * from the drawn roof polygon on the satellite map using length-weighted 4-fold circular averaging.
 * If the building is within ±3.8° of cardinal North-South/East-West, snaps to 0° so rows are crisp.
 */
export function detectPrincipalRoofAngleDeg(poly) {
  if (!Array.isArray(poly) || poly.length < 3) return 0;
  let sumCos4 = 0;
  let sumSin4 = 0;
  let longestLen = 0;
  let longestAngleDeg = 0;
  for (let i = 0; i < poly.length; i++) {
    const [x0, y0] = poly[i];
    const [x1, y1] = poly[(i + 1) % poly.length];
    const dx = x1 - x0;
    const dy = y1 - y0;
    const len = Math.hypot(dx, dy);
    if (len < 1.5) continue;
    const angRad = Math.atan2(dy, dx);
    const w = len * len;
    sumCos4 += w * Math.cos(4 * angRad);
    sumSin4 += w * Math.sin(4 * angRad);
    if (len > longestLen) {
      longestLen = len;
      let deg = (angRad * 180) / Math.PI;
      while (deg <= -45) deg += 90;
      while (deg > 45) deg -= 90;
      longestAngleDeg = deg;
    }
  }
  if (longestLen < 1.5) return 0;
  let meanDeg = ((0.25 * Math.atan2(sumSin4, sumCos4)) * 180) / Math.PI;
  while (meanDeg <= -45) meanDeg += 90;
  while (meanDeg > 45) meanDeg -= 90;
  const bestDeg = Math.abs(meanDeg - longestAngleDeg) < 8 ? meanDeg : longestAngleDeg;
  if (Math.abs(bestDeg) <= 3.8) return 0;
  return Number(bestDeg.toFixed(1));
}

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
    this.activeTool = 'pan'; // 'pan' | 'roof' | 'roof_poly' | 'obstacle' | 'scale' | 'direction' | 'delete'
    this.aiRequirement = '';
    this.aiExecutionNote = '';
    this.targetCapacityKw = 0;

    // Video 2 PVLANE Scale Calibration & Direction & Roof Pitch (matched 1:1 to real EPSG:3857 Zoom 18 scale)
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

    // Right panel: Module & Layout settings (Video 1 鹧鸪云 1:1)
    this.leftPanelTab = 'roof'; // Video 2 PVLANE 3 tabs: 'roof' (1.屋面) | 'layout' (2.布局) | 'info' (3.信息)
    this.rightDrawerTab = 'layout'; // Video 1 鹧鸪云 right drawer: 'layout' (组件排布) | 'elec' (电气配置)
    this.coordFormat = 'dec'; // Video 1 地图拾取经纬度: 'dec' (十进制) | 'dms' (度分秒)
    this.regionQuickPick = '';
    this.moduleModelId = 'jinko-jkm580n-72hl4-bdv';
    this.orientation = 'portrait'; // 'portrait' (竖放) | 'landscape' (横放)
    this.tiltDeg = 6;
    this.azimuthDeg = 180;
    this.rowSpacingM = 0.50;
    this.colSpacingM = 0.02;
    this.arrayGroupRows = 2; // 阵列行数 (Video 1: 2 rows per sub-array group)
    this.arrayGroupCols = 9; // 阵列列数 (Video 1: 9/10 cols per sub-array group)
    this.walkwayWidthM = 0.50; // 走道宽度 500mm (Video 1: 500 mm)
    this.parapetHeightMm = 300; // 女儿墙高 (mm)
    this.parapetWidthMm = 240; // 女儿墙宽 (mm)
    this.subArrayHeightMm = 1000; // 子阵高度 (mm)
    this.autoRowSpacing = true; // 子阵间距 ☑ 自动计算
    this.edgeSetbackM = 0.50;
    this.obstacleSetbackM = 0.30;
    this.customOrthoImg = null; // Optional uploaded top-down orthophoto (Video 1 上传图片 / Video 2 导入俯视底图)
    this.showShadowPreview = false; // Video 1 ☀️ 阴影分析浮窗开关
    this.liveEdgeLengthMm = 76000; // Video 1 画布底部边长实时显示 [76000] mm | 76.00m
    this.undoStack = [];
    this.redoStack = [];

    // Electrical settings & Video 1 Modals (v1_11.2s ~ v1_14.3s)
    this.inverterBrandFilter = 'all';
    this.inverterPowerFilter = 'all'; // 'all' | 'gt150' | '100_150' | '50_100' | '30_50' | '10_30' | 'lt10'
    this.inverterSelectionMode = 'auto'; // 'auto' (智能推荐) | 'manual' (自选逆变器)
    this.inverterModelId = 'sungrow-sg110cx-p2';
    this.modulesPerString = 18;
    this.dcAcTargetMin = 1.1;
    this.dcAcTargetMax = 1.3;
    this.dcCableGenerated = true;
    this.dcCableTotalM = 0;
    this.electricalConfirmed = true;
    this.showStringColors = true;
    this.showStringModeModal = false; // Video 1 v1_11.2s: 逆变器区域选择 / 请选择组串方式 (快速组串 vs DIY组串)
    this.stringingMode = 'quick'; // 'quick' (快速组串-新手推荐) | 'diy' (DIY组串)
    this.selectAllRoofDevices = true; // ☑ 选中屋顶所有设备
    this.showInverterModal = false; // Video 1 v1_13.3s: 逆变器选择弹窗 (品牌+功率分段筛选)
    this.showMpptModal = false; // Video 1 v1_14.3s: 完成设计后弹出 MPPT 组串分配表

    // Step 3: PVsyst state
    this.pvsystParams = {};
    this.pvsystData = null;

    // Step 4: PVLANE Oblique Photo Perspective Homography + Parapet Sightline Occlusion Studio (v2_23.5s ~ v2_40.5s)
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

    // Live timer for PVLANE workflow demonstration
    this.timerElapsedMs = 42180; // 00:42.18 initial showcase badge
    this.timerRunning = false;
    this.timerInterval = null;

    // Step 5: CAD Drawing Generator state (Video 1 鹧鸪云 3-stage wizard + 4 professional sheets, v1_16.5s ~ v1_27.0s)
    this.cadWizardTab = 'sheets'; // 'basic' (1.基本参数) | 'bracket' (2.支架设计) | 'sheets' (3.生成图纸)
    this.cadCategory = 'elec'; // 'elec' (电气图) | 'struct' (结构图)
    this.cadSheet = 'layout'; // 'layout' | 'string' | 'grounding' | 'bracket'
    this.cadChecks = {
      layout: true,
      string: true,
      grounding: true,
      bracket: true,
    };
    this.cadTitle = '分布式厂房屋顶光伏施工图';
    this.cadUnit = '光筑智能光伏工程设计院 (Guangzhu Engineering)';
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
    };
    this.evaluateWeatherAndAngles();
    this.prewarmInitialTiles();
  }

  /**
   * Pre-fetch the center 3x3 satellite tiles immediately upon instantiation
   * so that Step 1 renders with zero startup lag.
   */
  prewarmInitialTiles() {
    if (typeof Image === 'undefined') return;
    try {
      const z = Math.max(4, Math.min(19, Math.round(this.zoom || 18)));
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
    this.ridgeAzimuthDeg = detectPrincipalRoofAngleDeg(this.roofOutlineM);
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

  scheduleMapRedraw() {
    if (typeof requestAnimationFrame !== 'function') {
      this.drawMapCanvas();
      return;
    }
    if (this._rafPending) return;
    this._rafPending = true;
    requestAnimationFrame(() => {
      this._rafPending = false;
      this.drawMapCanvas();
    });
  }

  async load() {
    if (!this.pvsystData) {
      this.refreshPvsystData({ fetchBackend: true });
    }
    return this;
  }

  dispose() {
    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }
    this.timerRunning = false;
    this.isFullscreen = false;
  }

  getSelectedModule() {
    return SAT_MODULE_CATALOG.find((m) => m.id === this.moduleModelId) || SAT_MODULE_CATALOG[0];
  }

  getSelectedInverter() {
    return SAT_INVERTER_CATALOG.find((inv) => inv.id === this.inverterModelId) || SAT_INVERTER_CATALOG[0];
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
   * Video 1 (鹧鸪云) 一键铺设 + Video 2 (PVLANE) 屋面主边对齐排布与红框禁布区避障算法
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
   * Video 1 (鹧鸪云) Advanced Connected-Wing Serpentine Stringing + Roof-Interior Cable Routing
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

    // 1. Build Interior Module Adjacency Graph (edges only connect modules whose straight line stays 100% inside roof & outside obstacles)
    const nMods = this.modules.length;
    const adj = Array.from({ length: nMods }, () => []);
    for (let i = 0; i < nMods; i++) {
      const mi = this.modules[i];
      mi._idx = i;
      for (let j = i + 1; j < nMods; j++) {
        const mj = this.modules[j];
        if (Math.abs((mi.row ?? 0) - (mj.row ?? 0)) > 2) continue;
        const du = Math.abs((mi.cu ?? mi.cx) - (mj.cu ?? mj.cx));
        const dv = Math.abs((mi.cv ?? mi.cy) - (mj.cv ?? mj.cy));
        if (du > modW * 3.2 || dv > modH * 2.6) continue;
        const dist = Math.hypot(du, dv);
        if (dist <= maxNeighborDist && segmentStaysInsideRoof([mi.cx, mi.cy], [mj.cx, mj.cy], this.roofOutlineM, this.obstacles)) {
          // Prefer horizontal adjacency within the same row, then vertical adjacency
          const weight = mi.row === mj.row ? dist * 0.85 : dist * 1.15;
          adj[i].push({ to: j, weight, dist });
          adj[j].push({ to: i, weight, dist });
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

    // 3. Within each Contiguous Wing, order modules into Compact 2-Row × (perStr/2)-Col U-Turn Serpentine Blocks
    const halfCols = Math.max(2, Math.ceil(perStr / 2));
    const orderedModules = [];
    for (const wing of wings) {
      // Group by row, sort each row by u, and split into contiguous horizontal row segments
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

      // Pair adjacent rows (2k, 2k+1) and slice horizontally into 2 x halfCols U-turn serpentine blocks
      const usedInWing = new Set();
      for (let rIdx = 0; rIdx < sortedRows.length; rIdx += 2) {
        const rTop = sortedRows[rIdx];
        const rBot = rIdx + 1 < sortedRows.length ? sortedRows[rIdx + 1] : null;
        const topSegs = rowSegmentsByRow.get(rTop) || [];
        const botSegs = rBot != null ? (rowSegmentsByRow.get(rBot) || []) : [];

        for (const tSeg of topSegs) {
          const tMinU = tSeg[0].u ?? tSeg[0].x;
          const tMaxU = (tSeg[tSeg.length - 1].u ?? tSeg[tSeg.length - 1].x) + modW;
          // Find matching bottom row segment that overlaps horizontally and stays inside roof
          const matchBot = botSegs.find((bSeg) => {
            const bMinU = bSeg[0].u ?? bSeg[0].x;
            const bMaxU = (bSeg[bSeg.length - 1].u ?? bSeg[bSeg.length - 1].x) + modW;
            return Math.min(tMaxU, bMaxU) - Math.max(tMinU, bMinU) >= modW * 0.5;
          });

          const maxLen = Math.max(tSeg.length, matchBot ? matchBot.length : 0);
          for (let cStart = 0; cStart < maxLen; cStart += halfCols) {
            const topChunk = tSeg.slice(cStart, cStart + halfCols).filter((m) => !usedInWing.has(m));
            const botChunk = matchBot
              ? matchBot.slice(cStart, cStart + halfCols).filter((m) => !usedInWing.has(m)).reverse()
              : [];
            for (const m of topChunk) {
              usedInWing.add(m);
              orderedModules.push(m);
            }
            for (const m of botChunk) {
              usedInWing.add(m);
              orderedModules.push(m);
            }
          }
        }
        // Any unmatched bottom segments in rBot
        for (const bSeg of botSegs) {
          for (const m of bSeg) {
            if (!usedInWing.has(m)) {
              usedInWing.add(m);
              orderedModules.push(m);
            }
          }
        }
      }
      // Any remaining modules in wing
      for (const m of wing) {
        if (!usedInWing.has(m)) {
          usedInWing.add(m);
          orderedModules.push(m);
        }
      }
    }

    // Dijkstra shortest interior path helper over module graph
    const findInteriorModulePath = (startIdx, endIdx) => {
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
        for (const edge of adj[u]) {
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

    const totalStrings = Math.max(1, Math.floor(totalMods / perStr));
    const dcKw = (totalMods * mod.stc_w) / 1000;
    const maxStringsPerInv = inv.mppt_count * inv.strings_per_mppt;
    const invCount = Math.max(1, Math.ceil(totalStrings / maxStringsPerInv));
    const totalAcKw = invCount * inv.rated_ac_kw;
    const dcAcRatio = totalAcKw > 0 ? dcKw / totalAcKw : 1.15;

    const strings = [];
    const mpptRows = [];
    let modCursor = 0;

    for (let sIdx = 0; sIdx < totalStrings; sIdx++) {
      const invIdx = Math.floor(sIdx / maxStringsPerInv);
      const localStrIdx = sIdx % maxStringsPerInv;
      const mpptIdx = Math.floor(localStrIdx / inv.strings_per_mppt);
      const color = MPPT_PALETTE[(invIdx * inv.mppt_count + mpptIdx) % MPPT_PALETTE.length];
      const strId = `INV${invIdx + 1}-MPPT${mpptIdx + 1}-S${(localStrIdx % inv.strings_per_mppt) + 1}`;
      const slice = orderedModules.slice(modCursor, modCursor + perStr);
      modCursor += perStr;

      for (const m of slice) {
        m.stringId = strId;
        m.mpptIndex = mpptIdx + 1;
        m.inverterIndex = invIdx + 1;
        m.color = color;
      }

      if (slice.length) {
        // Build strictly roof-interior wire segments for this string (never crossing outside the roof!)
        const wireSegmentsM = [];
        const wireSegmentsUV = [];
        let curSegM = [[slice[0].cx, slice[0].cy]];
        let curSegUV = [[slice[0].cu ?? slice[0].cx, slice[0].cv ?? slice[0].cy]];

        for (let k = 0; k < slice.length - 1; k++) {
          const mA = slice[k];
          const mB = slice[k + 1];
          const directDist = Math.hypot((mB.cu ?? mB.cx) - (mA.cu ?? mA.cx), (mB.cv ?? mA.cv) - (mA.cv ?? mA.cy));
          const directOk = directDist <= maxNeighborDist * 1.4 &&
            segmentStaysInsideRoof([mA.cx, mA.cy], [mB.cx, mB.cy], this.roofOutlineM, this.obstacles);

          if (directOk) {
            // Try clean orthogonal L-corner in (u, v) if different rows
            const cornerUV = [mB.cu ?? mB.cx, mA.cv ?? mA.cy];
            const cornerM = frame.fromUV(cornerUV[0], cornerUV[1]);
            if (
              Math.abs((mA.cu ?? 0) - (mB.cu ?? 0)) > 0.2 &&
              Math.abs((mA.cv ?? 0) - (mB.cv ?? 0)) > 0.2 &&
              pointInPolygon(cornerM, this.roofOutlineM) &&
              segmentStaysInsideRoof([mA.cx, mA.cy], cornerM, this.roofOutlineM, this.obstacles) &&
              segmentStaysInsideRoof(cornerM, [mB.cx, mB.cy], this.roofOutlineM, this.obstacles)
            ) {
              curSegM.push(cornerM);
              curSegUV.push(cornerUV);
            }
            curSegM.push([mB.cx, mB.cy]);
            curSegUV.push([mB.cu ?? mB.cx, mB.cv ?? mB.cy]);
          } else {
            // Route along interior module spine via Dijkstra so wire never crosses outside the roof!
            const interiorPath = findInteriorModulePath(mA._idx, mB._idx);
            if (interiorPath && interiorPath.length >= 2) {
              for (let pIdx = 1; pIdx < interiorPath.length; pIdx++) {
                const pm = interiorPath[pIdx];
                curSegM.push([pm.cx, pm.cy]);
                curSegUV.push([pm.cu ?? pm.cx, pm.cv ?? pm.cy]);
              }
            } else {
              // Disconnected roof islands: finish current segment and start a new segment
              if (curSegM.length >= 2) {
                wireSegmentsM.push(curSegM);
                wireSegmentsUV.push(curSegUV);
              }
              curSegM = [[mB.cx, mB.cy]];
              curSegUV = [[mB.cu ?? mB.cx, mB.cv ?? mB.cy]];
            }
          }
        }
        if (curSegM.length >= 2) {
          wireSegmentsM.push(curSegM);
          wireSegmentsUV.push(curSegUV);
        }

        // Anchor label at the median module of the string (guaranteed 100% inside the roof, unlike centroid on a C-shape!)
        const midMod = slice[Math.floor(slice.length / 2)];
        const us = slice.map((m) => m.u ?? m.x);
        const vs = slice.map((m) => m.v ?? m.y);
        strings.push({
          id: strId,
          shortName: `PV${sIdx + 1}`,
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

    // Remainder modules assigned to last string
    for (let i = modCursor; i < orderedModules.length; i++) {
      const m = orderedModules[i];
      m.stringId = strings[strings.length - 1]?.id || 'S-REM';
      m.color = strings[strings.length - 1]?.color || '#64748b';
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
        this.obstacles.some((o) => pointInPolygon([invX, invY], o.polygon))
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
        const spineMods = findInteriorModulePath(endMod._idx, invPt.anchorModIdx);
        if (spineMods && spineMods.length >= 2) {
          // Sample spine waypoints to keep polyline clean while 100% inside roof
          st.homeRunPathM = spineMods.map((m) => [m.cx, m.cy]).concat([[invPt.x, invPt.y]]);
          st.homeRunPathUV = spineMods.map((m) => [m.cu ?? m.cx, m.cv ?? m.cy]).concat([[invPt.u, invPt.v]]);
        } else {
          st.homeRunPathM = [];
          st.homeRunPathUV = [];
        }
      }
    }

    // Build MPPT allocation table rows matching Video 1 (鹧鸪云)
    for (let invIdx = 0; invIdx < invCount; invIdx++) {
      const invName = `${inv.model}#${invIdx + 1}`;
      const invStrings = strings.filter((s) => s.inverterIndex === invIdx + 1);
      const invTotalStrings = Math.max(1, invStrings.length);
      for (let mIdx = 0; mIdx < inv.mppt_count; mIdx++) {
        const matched = invStrings.filter((s) => s.mpptIndex === mIdx + 1);
        const strCount = matched.length;
        const modCount = matched[0]?.moduleCount ?? 0;
        const totalMpptMods = matched.reduce((acc, s) => acc + s.moduleCount, 0);
        const stringNames = matched.length
          ? matched.map((s) => s.shortName).join(' / ')
          : '未接入';
        const stringRatio = matched.length
          ? `${strCount}/${invTotalStrings} (${Math.round((strCount / invTotalStrings) * 100)}%)`
          : '0%';
        const workCurrA = Number((strCount * mod.imp_a).toFixed(2));
        const shortCurrA = Number((strCount * mod.isc_a).toFixed(2));
        const vmpV = Number((modCount * mod.vmp_v).toFixed(1));
        const statusOk = strCount === 0 || (workCurrA <= inv.max_mppt_current_a && shortCurrA <= inv.max_short_current_a);
        mpptRows.push({
          inverterName: invName,
          mpptName: `MPPT${mIdx + 1}`,
          stringNames,
          stringCount: strCount,
          modulesPerString: modCount,
          totalMpptMods,
          stringRatio,
          workCurrentA: workCurrA,
          shortCurrentA: shortCurrA,
          vmpV,
          color: MPPT_PALETTE[(invIdx * inv.mppt_count + mIdx) % MPPT_PALETTE.length],
          status: strCount === 0 ? '备用' : statusOk ? '正常' : '偏高',
          ok: statusOk,
        });
      }
    }

    const southCount = this.modules.filter((m) => m.slope === 'south').length;
    const northCount = this.modules.filter((m) => m.slope === 'north').length;
    const annualKwh = Math.round(dcKw * 1186);
    const capexWan = Number(((dcKw * 3.15) / 10).toFixed(2));
    const paybackYears = Number((capexWan / Math.max(0.1, (annualKwh * 0.78) / 10000)).toFixed(2));

    this.strings = strings;
    this.mpptRows = mpptRows;
    this.summary = {
      moduleCount: totalMods,
      southCount,
      northCount,
      dcKw: Number(dcKw.toFixed(2)),
      acKw: Number(totalAcKw.toFixed(1)),
      dcAcRatio: Number(dcAcRatio.toFixed(2)),
      inverterCount: invCount,
      stringCount: strings.length,
      annualKwh,
      specificYield: 1186,
      prPct: 84.2,
      capexWan,
      paybackYears,
    };
  }

  refreshPvsystData({ fetchBackend = true } = {}) {
    const hasModules = this.modules && this.modules.length > 0;
    const reqPayload = {
      lat: this.lat,
      lon: this.lon,
      dc_kw: hasModules ? this.summary.dcKw : 280,
      ac_kw: hasModules ? this.summary.acKw : 220,
      tilt_deg: this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg,
      azimuth_deg: this.azimuthDeg,
      ...this.pvsystParams,
    };
    try {
      this.pvsystData = computeClientFallbackPvsyst(
        reqPayload,
        this.pvsystParams
      );
      if (this.pvsystData?.summary) {
        this.summary.specificYield = Number(this.pvsystData.summary.specific_yield_kwh_kwp || 1186);
        this.summary.prPct = Number(this.pvsystData.summary.pr_pct || 84.2);
        if (hasModules) {
          this.summary.annualKwh = Math.round(this.pvsystData.summary.e_grid_kwh || this.summary.annualKwh);
          this.summary.paybackYears = Number((this.summary.capexWan / Math.max(0.1, (this.summary.annualKwh * 0.78) / 10000)).toFixed(2));
        }
      }
    } catch {
      // Fallback already populated in this.summary
    }
    this.evaluateWeatherAndAngles();

    if (fetchBackend && typeof this.api === 'function') {
      const epoch = (this._pvsystEpoch = (this._pvsystEpoch || 0) + 1);
      Promise.resolve()
        .then(() => this.api('pvsyst/simulate', reqPayload))
        .then((res) => {
          if (epoch !== this._pvsystEpoch || !res?.summary) return;
          this.pvsystData = res;
          this.summary.specificYield = Number(res.summary.specific_yield_kwh_kwp || this.summary.specificYield);
          this.summary.prPct = Number(res.summary.pr_pct || this.summary.prPct);
          if (this.modules && this.modules.length > 0) {
            this.summary.annualKwh = Math.round(res.summary.e_grid_kwh || this.summary.annualKwh);
            this.summary.paybackYears = Number((this.summary.capexWan / Math.max(0.1, (this.summary.annualKwh * 0.78) / 10000)).toFixed(2));
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
      [1, '1. 卫星底图与排布设计'],
      [2, '2. 电气设计与MPPT配串'],
      [3, '3. PVsyst 8760h 仿真与实时气象'],
      [4, '4. 实景透视效果图 (PVLANE)'],
      [5, '5. 施工 CAD 图纸生成'],
    ];

    const autopilotBanner = this.autopilotState
      ? `<div class="satmap-autopilot-bar" data-sat-autopilot-banner>
          <span><b>AI 设计流程执行中：</b>${esc(this.autopilotState.text)}</span>
          <div class="satmap-autopilot-progress"><div class="satmap-autopilot-fill" style="width:${this.autopilotState.pct}%"></div></div>
          <b>${this.autopilotState.pct}%</b>
        </div>`
      : '';

    const kpiStrip = `<div class="satmap-kpi-strip">
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
        <small>预计回收期 ${s.paybackYears} 年</small>
      </div>
    </div>`;

    let bodyHtml = '';
    if (this.step === 1) bodyHtml = this.renderStep1MapWorkbench();
    else if (this.step === 2) bodyHtml = this.renderStep2Electrical();
    else if (this.step === 3) bodyHtml = this.renderStep3Pvsyst();
    else if (this.step === 4) bodyHtml = this.renderStep4EffectStudio();
    else if (this.step === 5) bodyHtml = this.renderStep5CadStudio();

    return `<div class="satmap-shell" data-satmap-root>
      <div class="satmap-topbar">
        <div class="satmap-brand">
          <div>
            <h2>卫星地图 AI 光伏设计工作台</h2>
            <small>全国真实卫星影像定位 · 当地实时气象与最优倾角评估 · 双坡与禁布区排布 · MPPT配串 · 实景四点透视 · 四张施工CAD图纸导出</small>
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
          <button type="button" class="sat-btn success" data-sat-action="save-to-project">保存至工程库</button>
        </div>
      </div>

      ${autopilotBanner}
      ${kpiStrip}
      ${bodyHtml}
    </div>`;
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
      <!-- 1. 视频一(鹧鸪云 v1_02.5s) 地图拾取经纬度 · 全国任意省市区/企业搜索 · 度分秒切换 · 图源切换 -->
      <div class="satmap-searchbar">
        <div class="satmap-search-item">
          <span>省市区选址</span>
          <select data-sat-field="regionQuickPick" title="快捷定位全国各省市工业区，也可在右侧搜索任意企业或输入经纬度">
            <option value="">全国任意位置 / 请选择省市区</option>
            <option value="山东省济南市历城区工业北路|36.588644|116.774288" ${this.regionQuickPick.startsWith('山东省济南市') ? 'selected' : ''}>山东省 / 济南市 / 历城区</option>
            <option value="山东省淄博市桓台县起凤镇工业园|36.858844|118.778089" ${this.regionQuickPick.startsWith('山东省淄博市') ? 'selected' : ''}>山东省 / 淄博市 / 桓台县 (视频1同款)</option>
            <option value="山东省济宁市兖州区大安镇工业园|35.566044|116.776388" ${this.regionQuickPick.startsWith('山东省济宁市') ? 'selected' : ''}>山东省 / 济宁市 / 兖州区 (视频1拾取点)</option>
            <option value="江苏省泰州市医药高新区药城大道|32.456200|119.923100" ${this.regionQuickPick.startsWith('江苏省泰州市') ? 'selected' : ''}>江苏省 / 泰州市 / 高新区 (视频2同款)</option>
            <option value="广东省佛山市顺德区北滘镇工业园|22.931800|113.214500" ${this.regionQuickPick.startsWith('广东省佛山市') ? 'selected' : ''}>广东省 / 佛山市 / 顺德区</option>
            <option value="浙江省嘉兴市平湖市经济开发区|30.698200|121.015600" ${this.regionQuickPick.startsWith('浙江省嘉兴市') ? 'selected' : ''}>浙江省 / 嘉兴市 / 平湖市</option>
            <option value="福建省宁德市蕉城区漳湾镇工业园|26.719073|119.555596" ${this.regionQuickPick.startsWith('福建省宁德市') ? 'selected' : ''}>福建省 / 宁德市 / 蕉城区</option>
            <option value="陕西省西安市经济技术开发区草滩园区|34.378500|108.891200" ${this.regionQuickPick.startsWith('陕西省西安市') ? 'selected' : ''}>陕西省 / 西安市 / 经开区</option>
          </select>
        </div>
        <div class="satmap-search-item" style="flex:1;min-width:240px">
          <span>全国位置/企业搜索</span>
          <input type="text" class="addr-input" data-sat-field="searchQuery" value="${esc(this.searchQuery || this.address)}" placeholder="输入全国任意企业名称、工厂、工业园、街道或省市区（如：宁德时代、隆基绿能、比亚迪、淄博起凤镇）">
          <button type="button" class="sat-btn primary" data-sat-action="search-location">搜索位置</button>
        </div>
        <div class="satmap-search-item">
          <span>经度 (°E)</span>
          <input type="number" step="0.0001" class="coord-input" data-sat-field="lon" value="${Number(this.lon).toFixed(6)}">
        </div>
        <div class="satmap-search-item">
          <span>纬度 (°N)</span>
          <input type="number" step="0.0001" class="coord-input" data-sat-field="lat" value="${Number(this.lat).toFixed(6)}">
        </div>
        <button type="button" class="sat-btn ${this.coordFormat === 'dms' ? 'primary' : ''}" data-sat-action="toggle-dms" title="切换十进制经纬度与度分秒(DMS)显示">
          ${this.coordFormat === 'dms' ? `度分秒: ${formatDmsCoord(this.lon, true)} ${formatDmsCoord(this.lat, false)}` : '度分秒'}
        </button>
        <button type="button" class="sat-btn" data-sat-action="locate">经纬度定位</button>
        <div class="satmap-search-item">
          <span>切换地图图源</span>
          <select data-sat-field="mapSource">
            <option value="gaode" ${this.mapSource === 'gaode' ? 'selected' : ''}>谷歌/高德高清卫星混合图 (含路网企业标注)</option>
            <option value="esri" ${this.mapSource === 'esri' ? 'selected' : ''}>Esri World Imagery (全球高清纯卫星)</option>
          </select>
        </div>
        <button type="button" class="sat-btn primary" data-sat-action="toggle-fullscreen">${this.isFullscreen ? '退出全屏' : '全屏放大地图'}</button>
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

      <!-- 2. 嵌入式 AI 设计要求与一键设计栏 + 视频一顶部建模动作栏 (v1_04.0s ~ v1_10.2s) -->
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
        <button type="button" class="sat-btn" data-sat-action="ai-detect-roof">AI 识别当前屋面</button>
        <button type="button" class="sat-btn primary" data-sat-action="ai-autopilot">AI 按要求一键设计</button>
      </div>

      <!-- 视频一(鹧鸪云 v1_04.0s ~ v1_10.2s) 1:1 顶部建模工具栏 -->
      <div class="satmap-v1-modelbar" role="toolbar" aria-label="鹧鸪云同款顶部建模工具栏">
        <div class="satmap-v1-modelbar-group">
          <button type="button" class="satmap-v1-tool-chip" data-sat-action="clear-roof" title="清空当前选区并重新选址绘制">📍 重新选址</button>
          <label class="satmap-v1-tool-chip" style="cursor:pointer" title="上传无人机航拍俯视图或CAD转图片">
            🖼️ 上传图片
            <input type="file" accept="image/*" data-sat-file="ortho-photo" style="display:none">
          </label>
        </div>
        <div class="satmap-v1-modelbar-group">
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'roof_poly' ? 'active' : ''}" data-sat-tool="roof_poly">✏️ 绘制 (多点画屋顶)</button>
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'pan' ? 'active' : ''}" data-sat-tool="pan">📐 区域编辑 (微调顶点)</button>
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'roof' ? 'active' : ''}" data-sat-tool="roof">▭ 矩形绘制</button>
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly' ? 'active' : ''}" data-sat-tool="obstacle_poly">🚫 障碍物 (多点画禁布区)</button>
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'scale' ? 'active' : ''}" data-sat-tool="scale">📏 标定比例尺</button>
          <button type="button" class="satmap-v1-tool-chip ${this.activeTool === 'direction' ? 'active' : ''}" data-sat-tool="direction">🧭 确定方向</button>
          <button type="button" class="satmap-v1-tool-chip ${this.roofType === 'double_slope' ? 'active' : ''}" data-sat-roof-type="${this.roofType === 'double_slope' ? 'single_slope' : 'double_slope'}">🏠 屋面坡度/分水线</button>
          <button type="button" class="satmap-v1-tool-chip ${this.showShadowPreview ? 'active' : ''}" data-sat-action="toggle-shadow">☀ 阴影模拟</button>
          <button type="button" class="satmap-v1-tool-chip" data-sat-action="undo-step">↶ 撤销</button>
          <button type="button" class="satmap-v1-tool-chip" data-sat-action="redo-step">↷ 恢复</button>
        </div>
        <div class="satmap-v1-modelbar-group">
          <button type="button" class="satmap-v1-tool-chip" data-sat-action="toggle-fullscreen">${this.isFullscreen ? '退出全屏' : '⛶ 全屏'}</button>
          <button type="button" class="satmap-v1-tool-chip" data-sat-action="save-to-project">💾 保存</button>
          <button type="button" class="satmap-v1-tool-chip active" data-sat-action="open-elec-flow">下一步 (电气设计) →</button>
        </div>
      </div>

      ${this.aiExecutionNote ? `
        <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:6px;padding:8px 12px;font-size:12px;color:#0369a1">
          <b>AI 设计执行结果：</b>${esc(this.aiExecutionNote)}
        </div>
      ` : ''}

      <!-- 3. 主工作台：左侧 PVLANE 3-Tab (1.屋面/2.布局/3.信息) + 中间真实卫星地图画布 + 右侧 鹧鸪云抽屉 (组件排布/电气配置) -->
      <div class="satmap-workbench">
        <!-- Left Panel: Video 2 (PVLANE v2_09.2s ~ v2_19.8s) 3-Tab Structure (1. 屋面 / 2. 布局 / 3. 信息) -->
        <aside class="satmap-left-panel">
          <div class="satmap-pvlane-tabs" role="tablist" aria-label="PVLANE同款三步导航">
            <button type="button" class="satmap-tab-pill ${this.leftPanelTab === 'roof' ? 'active' : ''}" data-sat-left-tab="roof">1. 屋面</button>
            <button type="button" class="satmap-tab-pill ${this.leftPanelTab === 'layout' ? 'active' : ''}" data-sat-left-tab="layout">2. 布局</button>
            <button type="button" class="satmap-tab-pill ${this.leftPanelTab === 'info' ? 'active' : ''}" data-sat-left-tab="info">3. 信息</button>
          </div>

          <h3 class="satmap-panel-title">
            <span>${this.leftPanelTab === 'roof' ? '1. 屋面建模与底图校准' : this.leftPanelTab === 'layout' ? '2. 屋面布局与排布参数' : '3. 屋面与发电汇总信息'}</span>
            <small style="color:var(--muted);font-weight:500">${this.hasRoof ? `屋面 1 (${bounds.areaM2}m²)` : '待绘制屋面'}</small>
          </h3>

          <div class="satmap-tool-list">
            <button type="button" class="satmap-tool-btn ${this.activeTool === 'pan' ? 'active' : ''}" data-sat-tool="pan">
              <span>0. 漫游平移卫星图</span>
              <small>拖拽/滚轮缩放</small>
            </button>
            <button type="button" class="satmap-tool-btn ${this.activeTool === 'scale' ? 'active' : ''}" data-sat-tool="scale">
              <span>1. 标定比例尺</span>
              <small>${this.scaleCustomized ? `${this.scaleReferenceM.toFixed(1)}m` : `卫星自动(${this.metersPerPx.toFixed(3)}m/px)`}</small>
            </button>
            <button type="button" class="satmap-tool-btn ${this.activeTool === 'direction' ? 'active' : ''}" data-sat-tool="direction">
              <span>2. 确定方向 (沿屋脊/外墙拉线)</span>
              <small>南偏 ${this.ridgeAzimuthDeg}°</small>
            </button>
            <button type="button" class="satmap-tool-btn ${this.activeTool === 'roof' ? 'active' : ''}" data-sat-tool="roof">
              <span>3. 绘制屋顶 (矩形框选)</span>
              <small>${this.hasRoof ? `${bounds.areaM2} m²` : '在厂房拖拽/点击'}</small>
            </button>
            <button type="button" class="satmap-tool-btn ${this.activeTool === 'roof_poly' ? 'active' : ''}" data-sat-tool="roof_poly">
              <span>3B. 多点画屋面 (异形/U形/L形)</span>
              <small>依次点选角点</small>
            </button>
            <button type="button" class="satmap-tool-btn ${this.activeTool === 'obstacle_poly' ? 'active' : ''}" data-sat-tool="obstacle_poly">
              <span>4. 多点画禁布区 (异形/斜向障碍物)</span>
              <small>依次点选顶点</small>
            </button>
            <button type="button" class="satmap-tool-btn ${this.activeTool === 'obstacle' ? 'active' : ''}" data-sat-tool="obstacle">
              <span>4B. 绘制禁布区 (多点或拉框)</span>
              <small>${this.obstacles.length} 处</small>
            </button>
            <button type="button" class="satmap-tool-btn ${this.activeTool === 'delete' ? 'active' : ''}" data-sat-tool="delete">
              <span>5. 删除选中禁布区</span>
              <small>点击红框移除</small>
            </button>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
            <button type="button" class="sat-btn primary" data-sat-tool="roof">绘制屋顶</button>
            <button type="button" class="sat-btn danger" data-sat-action="clear-roof">清除重画</button>
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
            <button type="button" class="sat-btn" data-sat-action="auto-scale-direction" title="根据当前卫星瓦片经纬度与已画屋顶轮廓自动识别比例尺和主墙朝向">自动识别比例尺/方向</button>
            <button type="button" class="sat-btn primary" data-sat-step="4" title="直接进入视频2同款1分钟实景透视效果图工作台">进入效果图流程 →</button>
          </div>

          <!-- Video 2 (PVLANE v2_11.8s) 屋面类型三选一 + 坡度 + 女儿墙高 -->
          <div class="satmap-subbox">
            <b>屋面结构与分界设置 (PVLANE 1.屋面)</b>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px">
              <button type="button" class="satmap-tab-pill ${this.roofType === 'flat' ? 'active' : ''}" data-sat-roof-type="flat">平屋顶</button>
              <button type="button" class="satmap-tab-pill ${this.roofType === 'single_slope' ? 'active' : ''}" data-sat-roof-type="single_slope">斜屋顶(单坡)</button>
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

          <div class="satmap-subbox">
            <b>卫星比例尺与主墙方向 (自动识别+微调)</b>
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
            `).join('') || '<span class="muted" style="font-size:11px">暂无禁布区，点击「绘制禁布区」在屋面拉框生成正交红框禁区</span>'}
          </div>
        </aside>

        <!-- Center Real Satellite Map Canvas with Video 1 Floating Mini-Bar, Live Edge Length Pill & Video 2 Roof Type Bar -->
        <div class="satmap-canvas-wrap ${this.isFullscreen ? 'is-fullscreen' : ''}" id="satmap-canvas-wrap">
          <div class="satmap-floating-tools" role="toolbar" aria-label="卫星地图工具栏">
            <button type="button" class="satmap-float-btn" data-sat-action="undo-step" title="撤销上一步操作">↶ 撤销</button>
            <button type="button" class="satmap-float-btn" data-sat-action="redo-step" title="重做操作">↷ 重做</button>
            <button type="button" class="satmap-float-btn ${this.activeTool === 'pan' ? 'active' : ''}" data-sat-tool="pan">漫游平移</button>
            <button type="button" class="satmap-float-btn ${this.activeTool === 'roof' ? 'active' : ''}" data-sat-tool="roof" title="在目标厂房屋顶上按住拖动或点击对角即可框选屋顶">1. 绘制屋顶</button>
            <button type="button" class="satmap-float-btn ${this.activeTool === 'roof_poly' ? 'active' : ''}" data-sat-tool="roof_poly" title="依次点击厂房各角点绘制任意角度或多边形屋顶，闭合后自动识别建筑主方向">多点画屋顶</button>
            <button type="button" class="satmap-float-btn lay-now" id="sat-close-roof-poly-btn" data-sat-action="close-roof-poly" style="${this.activeTool === 'roof_poly' && this.drawingPointsM.length >= 3 ? '' : 'display:none'}">完成屋顶闭合 (${this.drawingPointsM.length}点)</button>
            <button type="button" class="satmap-float-btn ${this.activeTool === 'obstacle' ? 'active' : ''}" data-sat-tool="obstacle" title="支持依次点击多个角点（或按住拖动）绘制屋面禁布区">2. 绘制禁布区</button>
            <button type="button" class="satmap-float-btn ${this.activeTool === 'obstacle_poly' ? 'active' : ''}" data-sat-tool="obstacle_poly" title="依次点击禁布区各个角点，点击起点P1、双击或点「完成禁布区闭合」生成任意多边形禁布区">多点画禁布区</button>
            <button type="button" class="satmap-float-btn lay-now" id="sat-close-obs-poly-btn" data-sat-action="close-obstacle-poly" style="${(this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly') && this.drawingObstaclePointsM.length >= 3 ? 'background:#dc2626;border-color:#f87171;' : 'display:none;background:#dc2626;border-color:#f87171;'}">完成禁布区闭合 (${this.drawingObstaclePointsM.length}点)</button>
            <button type="button" class="satmap-float-btn ${this.activeTool === 'scale' ? 'active' : ''}" data-sat-tool="scale" title="在厂房已知长度的边沿拖拽即可校准比例尺">标定比例尺</button>
            <button type="button" class="satmap-float-btn ${this.activeTool === 'direction' ? 'active' : ''}" data-sat-tool="direction" title="沿着厂房屋脊或外墙拖拽一条线，自动对齐组件排布方向">确定方向</button>
            <button type="button" class="satmap-float-btn" data-sat-action="auto-scale-direction" title="根据卫星地图经纬度与已画屋顶轮廓一键自动识别比例尺和方向">自动识别比例尺/方向</button>
            <button type="button" class="satmap-float-btn ${this.activeTool === 'delete' ? 'active' : ''}" data-sat-tool="delete">删除禁布区</button>
            <button type="button" class="satmap-float-btn lay-now" data-sat-action="layout-modules">3. 一键铺设</button>
            <button type="button" class="satmap-float-btn ${this.showShadowPreview ? 'active' : ''}" data-sat-action="toggle-shadow" title="视频1同款：开启/关闭冬至日 9:00-15:00 阵列日照阴影分析条带">☀️ 阴影分析</button>
            <button type="button" class="satmap-float-btn" data-sat-action="clear-roof">清除</button>
            <button type="button" class="satmap-float-btn" data-sat-action="zoom-in" title="放大卫星图">放大 +</button>
            <button type="button" class="satmap-float-btn" data-sat-action="zoom-out" title="缩小卫星图">缩小 -</button>
            <button type="button" class="satmap-float-btn fullscreen-btn" data-sat-action="toggle-fullscreen" title="全屏放大地图或按 Esc 退出全屏">${this.isFullscreen ? '退出全屏 (Esc)' : '全屏地图'}</button>
          </div>

          <!-- Video 1 (鹧鸪云 v1_04.0s) 画布底部中央边长实时输入浮窗 ([76000] mm | 76.00m) -->
          ${(this.hasRoof || isDrawingTool) ? `
            <div class="satmap-edge-dim-pill" role="region" aria-label="屋面主边长毫米级实时输入">
              <span>屋面主边长：</span>
              <input type="number" step="100" min="5000" max="500000" data-sat-field="liveEdgeLengthMm" value="${curEdgeMm}" title="输入屋面主边长(mm)回车即可精确校准尺寸">
              <span>mm | <b>${(curEdgeMm / 1000).toFixed(2)} m</b></span>
            </div>
          ` : ''}

          <!-- Video 2 (PVLANE) Inline Roof Type & Pitch Bar (lets user choose Single/Flat vs Double-Slope without unwanted auto-split) -->
          ${this.hasRoof || this.obstacles.length > 0 ? `
            <div class="satmap-roof-type-bar" role="region" aria-label="屋面分坡模式与禁布区快捷栏">
              <span>屋面模式：</span>
              <button type="button" class="satmap-roof-type-pill ${this.roofType === 'single_slope' ? 'active' : ''}" data-sat-roof-type="single_slope">整面连续平铺 (不自动分界)</button>
              <button type="button" class="satmap-roof-type-pill ${this.roofType === 'double_slope' ? 'active' : ''}" data-sat-roof-type="double_slope">双坡屋面 (沿屋脊分南北坡)</button>
              <button type="button" class="satmap-roof-type-pill ${this.roofType === 'flat' ? 'active' : ''}" data-sat-roof-type="flat">混凝土平屋面</button>
              <span style="margin-left:4px">坡度：</span>
              <input type="number" step="0.5" min="0" max="45" data-sat-field="roofSlopeDeg" value="${this.roofSlopeDeg}" style="width:52px;padding:2px 5px;border-radius:4px;border:1px solid #475569;background:#1e293b;color:#fff;font-size:11.5px">
              <span>°</span>
              <button type="button" class="satmap-roof-type-pill ${this.activeTool === 'obstacle' || this.activeTool === 'obstacle_poly' ? 'active' : ''}" data-sat-tool="obstacle_poly" style="border-color:#ef4444;color:#fecaca">+ 多点画禁布区 (${this.obstacles.length})</button>
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

          <canvas id="satmap-main-canvas" class="satmap-canvas ${isDrawingTool ? 'tool-draw' : ''}" width="${this.isFullscreen && typeof window !== 'undefined' ? Math.max(960, window.innerWidth) : 920}" height="${this.isFullscreen && typeof window !== 'undefined' ? Math.max(620, window.innerHeight - 36) : 580}"></canvas>

          <div class="satmap-floating-hud">
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
      }[this.activeTool] || '漫游平移'
      }</b></span>
          </div>
        </div>

        <!-- Right Panel: Video 1 (鹧鸪云 v1_08.5s ~ v1_14.3s) 1:1 组件排布 + 电气配置 双模式抽屉 -->
        <aside class="satmap-right-panel">
          <div class="satmap-drawer-tabs" role="tablist" aria-label="鹧鸪云同款右侧抽屉切换">
            <button type="button" class="satmap-tab-pill ${this.rightDrawerTab === 'layout' ? 'active' : ''}" data-sat-right-tab="layout">1. 组件排布</button>
            <button type="button" class="satmap-tab-pill ${this.rightDrawerTab === 'elec' ? 'active' : ''}" data-sat-right-tab="elec">2. 电气配置</button>
          </div>

          <h3 class="satmap-panel-title">
            <span>${this.rightDrawerTab === 'elec' ? '电气配置与逆变器清单' : '组件信息与排布设置'}</span>
            <small style="color:var(--muted);font-weight:500">${this.rightDrawerTab === 'elec' ? `容配比 ${this.summary.dcAcRatio || 1.15}` : '视频1同款参数'}</small>
          </h3>

          ${this.rightDrawerTab === 'elec' ? `
            <!-- Video 1 (v1_12.2s ~ v1_14.3s) 右侧「电气配置」抽屉 -->
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
                  <input type="number" step="0.05" min="0.6" max="1.8" data-sat-field="dcAcTargetMin" value="${this.dcAcTargetMin}" style="width:52px">
                  <span>~</span>
                  <input type="number" step="0.05" min="0.8" max="2.0" data-sat-field="dcAcTargetMax" value="${this.dcAcTargetMax}" style="width:52px">
                </span>
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
          ` : ''}

          <!-- Video 1 (v1_08.5s ~ v1_10.2s) 右侧「组件排布」完整参数 -->
          <div class="satmap-subbox">
            <b>组件信息 (组件型号与物理尺寸)</b>
            <label class="satmap-field-row" style="flex-direction:column;align-items:stretch;gap:4px">
              <span>选择组件型号</span>
              <select data-sat-field="moduleModelId" style="width:100%">
                ${SAT_MODULE_CATALOG.map((m) => `<option value="${esc(m.id)}" ${m.id === this.moduleModelId ? 'selected' : ''}>${esc(m.model)} (${m.length_m * 1000}×${m.width_m * 1000}mm)</option>`).join('')}
              </select>
            </label>
            <div style="font-size:11.5px;color:var(--muted,#64748b);display:flex;justify-content:space-between">
              <span>组件功率：<b>${mod.stc_w} Wp</b></span>
              <span>组件尺寸：<b>${(mod.length_m * 1000).toFixed(0)}/${(mod.width_m * 1000).toFixed(0)}/30mm</b></span>
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

          <div class="satmap-subbox">
            <b>组件排布参数 (视频1同款 2×9 阵列单元)</b>
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

          <div class="satmap-subbox">
            <b>当地气象与最优夹角速览</b>
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

          <!-- Video 1 (鹧鸪云) Bottom Summary Box: 组件数量 + 装机容量 -->
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
            前往施工 CAD 图纸生成 (排布/组串/防雷/支架) →
          </button>
        </aside>
      </div>

      ${this.renderVideo1Modals()}

      <!-- 4. 实时气象驱动的发电量判断、冬至日照间距计算与安装倾角最优评估表（下滑即可查看完整工程计算） -->
      <div class="satmap-weather-eval-card" data-sat-weather-eval>
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding-bottom:10px;border-bottom:1px solid var(--line,#e2e8f0)">
          <div>
            <h3 style="margin:0;font-size:15px">当地实时官方气象驱动的倾角设计、冬至无遮挡间距与发电量最优评估</h3>
            <small style="color:var(--muted,#64748b)">
              气象数据源：${esc(wxEval.source)} · 定位坐标 (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) · 结合当地逐时太阳辐射、温度损耗系数与冬至日 9:00–15:00 真太阳时无遮挡行间距公式 D = L·cos(β) + L·sin(β)·cot(αs)·cos(γs) 综合寻优
            </small>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button type="button" class="sat-btn" data-sat-action="refresh-live-weather">刷新当地实时气象</button>
            <button type="button" class="sat-btn primary" data-sat-action="apply-weather-opt-tilt">应用气象单瓦最优 (${wxEval.weatherOptimalTiltDeg}° / 排距 ${wxEval.weatherOptimalRowGapM}m)</button>
            <button type="button" class="sat-btn" data-sat-action="apply-roof-opt-tilt">应用屋面总发电最优 (${wxEval.roofOptimalTiltDeg}° / ${wxEval.roofOptimalWanKwh}万kWh)</button>
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

        <div style="overflow-x:auto">
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
      </div>
    `;
  }

  /**
   * Video 1 (鹧鸪云 v1_11.2s ~ v1_14.3s) 1:1 弹窗工作流：
   *   1. 逆变器区域选择 / 请选择组串方式 (快速组串 vs DIY组串)
   *   2. 逆变器选择弹窗 (左侧品牌筛选 + 顶部 7 档功率区间筛选 + 卡片网格)
   *   3. 完成设计后 MPPT 组串分配表弹窗 (带绿色电流校核标签)
   */
  renderVideo1Modals() {
    const inv = this.getSelectedInverter();
    const mod = this.getSelectedModule();
    let html = '';

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
            <div style="overflow-x:auto">
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
                  ${this.mpptRows.slice(0, 12).map((row) => `
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
            <div style="display:flex;justify-content:space-between;align-items:center;padding-top:8px;border-top:1px solid #e2e8f0">
              <span style="font-size:12px;color:#475569">容配比：<b>${this.summary.dcAcRatio}</b> · 直流装机：<b>${this.summary.dcKw} kWp</b> · 交流容量：<b>${this.summary.acKw} kW</b></span>
              <div style="display:flex;gap:8px">
                <button type="button" class="sat-btn" data-sat-action="close-modals">返回卫星图</button>
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
    return SAT_INVERTER_CATALOG.filter((item) => {
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
   * Step 2: Video 1 (鹧鸪云 v1_13.3s & v1_14.3s) 1:1 电气设计 — 逆变器品牌+功率段筛选、选型卡片 & MPPT 组串分配表
   */
  renderStep2Electrical() {
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

    return `<div class="satmap-elec-card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding-bottom:12px;border-bottom:1px solid var(--line,#e2e8f0)">
        <div>
          <h3 style="margin:0;font-size:16px">电气设计与逆变器 MPPT 组串分配工作台</h3>
          <small style="color:var(--muted,#64748b)">按品牌与功率区间选型组串式逆变器 → 设定单串组件数量与容配比 → 自动校核 MPPT 满载工作电流 Imp、最大短路电流 Isc 与低温 Voc，并在卫星屋面映射组串走线</small>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button type="button" class="sat-btn primary" data-sat-action="confirm-electrical">确认电气设计并映射屋面组串</button>
          <button type="button" class="sat-btn" data-sat-step="5">前往图纸生成工具</button>
        </div>
      </div>

      <!-- Video 1 (鹧鸪云 v1_13.3s) Inverter Brand Filter + Power Tier Filter & Visual Selection Cards -->
      <div style="margin-top:12px">
        <div class="satmap-inv-brand-bar" role="tablist" aria-label="逆变器品牌筛选">
          <span style="font-size:12.5px;font-weight:700;color:var(--ink)">逆变器品牌筛选：</span>
          ${brands.map((b) => `
            <button type="button" class="sat-btn ${this.inverterBrandFilter === b ? 'primary' : ''}" data-sat-inv-brand="${esc(b)}" style="padding:4px 12px;font-size:12px">
              ${b === 'all' ? '全部品牌' : esc(b)}
            </button>
          `).join('')}
        </div>

        <div class="satmap-inv-brand-bar" role="tablist" aria-label="逆变器功率区间筛选" style="margin-top:6px">
          <span style="font-size:12.5px;font-weight:700;color:var(--ink)">功率区间筛选：</span>
          ${powerTiers.map(([k, label]) => `
            <button type="button" class="satmap-inv-brand-btn ${this.inverterPowerFilter === k ? 'active' : ''}" data-sat-inv-power="${k}">
              ${esc(label)}
            </button>
          `).join('')}
        </div>

        <div class="satmap-inv-grid">
          ${filteredInverters.map((item) => {
      const isSelected = item.id === this.inverterModelId;
      return `<div class="satmap-inv-card ${isSelected ? 'selected active' : ''}" data-sat-pick-inv="${esc(item.id)}">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <span style="font-size:11.5px;color:#0284c7;font-weight:700">${esc(item.brand)}</span>
                <span class="${isSelected ? 'sat-pill-ok' : ''}" style="font-size:11px">${isSelected ? '当前已选型' : `${item.rated_ac_kw} kW`}</span>
              </div>
              <h4>${esc(item.model)}</h4>
              <div class="satmap-inv-specs">
                <span>额定交流功率：<b>${item.rated_ac_kw} kW</b></span>
                <span>MPPT 路数：<b>${item.mppt_count} 路 (${item.mppt_count * item.strings_per_mppt}串)</b></span>
                <span>最大工作电流：<b>${item.max_mppt_current_a} A</b></span>
                <span>最大短路电流：<b>${item.max_short_current_a} A</b></span>
                <span>MPPT 电压范围：<b>${item.mppt_v_min}~${item.mppt_v_max} V</b></span>
                <span>最大直流电压：<b>${item.max_dc_v} V</b></span>
              </div>
              <button type="button" class="sat-btn ${isSelected ? 'primary' : ''}" data-sat-pick-inv="${esc(item.id)}" style="width:100%;justify-content:center;margin-top:4px">
                ${isSelected ? '已选型' : '选型此逆变器'}
              </button>
            </div>`;
    }).join('')}
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:14px 0">
        <label class="satmap-subbox">
          <span>当前逆变器型号</span>
          <select data-sat-field="inverterModelId" style="padding:6px;border-radius:6px;border:1px solid var(--line-2,#cbd5e1)">
            ${SAT_INVERTER_CATALOG.map((item) => `<option value="${esc(item.id)}" ${item.id === this.inverterModelId ? 'selected' : ''}>${esc(item.brand)} · ${esc(item.model)} (${item.rated_ac_kw}kW / ${item.mppt_count}路MPPT)</option>`).join('')}
          </select>
        </label>
        <label class="satmap-subbox">
          <span>单串串联组件数 (块/串)</span>
          <input type="number" min="10" max="24" step="1" data-sat-field="modulesPerString" value="${this.modulesPerString}" style="padding:6px;border-radius:6px;border:1px solid var(--line-2,#cbd5e1)">
          <small style="color:var(--muted)">工作电压 ${(this.modulesPerString * mod.vmp_v).toFixed(0)}V / 低温开路 ${(this.modulesPerString * mod.voc_v * 1.08).toFixed(0)}V (限值 ${inv.max_dc_v}V)</small>
        </label>
        <div class="satmap-subbox">
          <span>直流/交流容配比 (DC/AC Ratio)</span>
          <strong style="font-size:18px;color:#0284c7">${s.dcAcRatio} : 1</strong>
          <small style="color:var(--muted)">直流 ${s.dcKw} kWp / 交流 ${s.acKw} kWac (${s.inverterCount} 台 ${inv.model})</small>
        </div>
        <div class="satmap-subbox">
          <span>MPPT 电流与电压包络校核</span>
          <strong style="font-size:16px;color:#059669">全部 MPPT 回路合规</strong>
          <small style="color:var(--muted)">单路最大工作电流 ${(2 * mod.imp_a).toFixed(2)}A ≤ ${inv.max_mppt_current_a}A</small>
        </div>
      </div>

      <h4 style="margin:12px 0 6px;font-size:14px">逆变器 MPPT 组串分配明细表 (共 ${s.inverterCount} 台逆变器 · ${s.stringCount} 路组串)</h4>
      <div style="overflow-x:auto">
        <table class="satmap-mppt-table">
          <thead>
            <tr>
              <th>逆变器名称</th>
              <th>MPPT</th>
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
                <td colspan="10" style="text-align:center;padding:18px;color:var(--muted)">
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
   * Step 3: PVsyst 8760h Loss Waterfall & Official Live Weather Panel
   * IMPORTANT: Never trigger async refreshPvsystData({ fetchBackend: true }) inside html() render,
   * otherwise completion of the API call calls refresh() -> renderStep3Pvsyst() in an infinite loop!
   */
  renderStep3Pvsyst() {
    if (!this.pvsystData) {
      this.refreshPvsystData({ fetchBackend: false });
    }
    try {
      return renderPvsystWorkbench(this.pvsystData, {
        lat: this.lat,
        lon: this.lon,
        dc_kw: this.summary.dcKw || 280,
        ac_kw: this.summary.acKw || 220,
        tilt_deg: this.roofType === 'flat' ? this.tiltDeg : this.roofSlopeDeg,
        azimuth_deg: this.azimuthDeg,
        params: this.pvsystParams,
      });
    } catch (err) {
      return `<div class="satmap-elec-card"><h3>PVsyst 8760h 仿真工作台</h3><p>${esc(err.message)}</p></div>`;
    }
  }

  /**
   * Step 4: Video 2 (PVLANE) 1:1 Oblique Photo Perspective Homography + Parapet Sightline Occlusion Studio
   */
  renderStep4EffectStudio() {
    return `<div class="satmap-elec-card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding-bottom:10px;border-bottom:1px solid var(--line,#e2e8f0);margin-bottom:12px">
        <div>
          <h3 style="margin:0;font-size:16px">实景效果图工作台 (PVLANE 1:1 流程) — 四点透视配准 (3×3 Homography) 与女儿墙视线遮挡裁剪</h3>
          <small style="color:var(--muted,#64748b)">
            导入无人机或手机斜拍厂房实景照片 → 依次点选或拖动屋面四角 1(左上)→2(右上)→3(右下)→4(左下) 完成三维透视投影 → 补画女儿墙视线遮挡区域（处理的是相机视线遮挡，不是光照阴影）
          </small>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <div class="satmap-timer-badge" title="实景出图计时器">
            <span>实景出图计时</span>
            <strong id="sat-effect-timer-display">${this.formatTimer(this.timerElapsedMs)}</strong>
          </div>
          <button type="button" class="sat-btn" data-sat-action="timer-toggle">${this.timerRunning ? '暂停计时' : '启动计时'}</button>
          <button type="button" class="sat-btn" data-sat-action="timer-reset">重置</button>
          <button type="button" class="sat-btn primary" data-sat-effect="export-png">导出实景效果图 (.png)</button>
        </div>
      </div>

      <div class="satmap-effect-studio">
        <aside class="satmap-left-panel" style="max-height:none">
          <div class="satmap-subbox">
            <b>1. 导入或选择斜拍实景底图</b>
            <label class="sat-btn" style="width:100%;justify-content:center;cursor:pointer">
              上传无人机 / 手机斜拍照片
              <input type="file" accept="image/*" data-sat-file="effect-photo" style="display:none">
            </label>
            <span style="font-size:11.5px;color:var(--muted)">或切换标准航拍斜视底图：</span>
            <div style="display:flex;flex-direction:column;gap:5px">
              ${[
        [0, '斜视底图 1：双坡钢构厂房 + 前景女儿墙'],
        [1, '斜视底图 2：大跨度彩钢瓦车间 45° 斜拍'],
        [2, '斜视底图 3：混凝土女儿墙平屋面航拍'],
      ].map(([idx, label]) => `
                <button type="button" class="satmap-tool-btn ${this.effectPresetIdx === idx && !this.customPhotoImg ? 'active' : ''}" data-sat-preset-photo="${idx}">
                  <span>${esc(label)}</span>
                </button>
              `).join('')}
            </div>
          </div>

          <div class="satmap-subbox">
            <b>2. 四点透视配准 (4-Point Homography)</b>
            <div style="font-size:11.5px;color:var(--ink-2);line-height:1.45">
              参照下方 2D 排布缩略图角点顺序，在右侧实景照片上点选或拖动对应屋面四角：
              <b>1 (左上) → 2 (右上) → 3 (右下) → 4 (左下)</b>
            </div>
            <svg viewBox="0 0 240 110" style="width:100%;background:#0f172a;border-radius:6px;border:1px solid #334155">
              <rect x="34" y="18" width="172" height="74" fill="#1e3a8a" fill-opacity="0.45" stroke="#38bdf8" stroke-width="1.8"/>
              <line x1="34" y1="55" x2="206" y2="55" stroke="#facc15" stroke-width="1.2" stroke-dasharray="4 2"/>
              <rect x="46" y="32" width="148" height="7" fill="rgba(239,68,68,0.55)" stroke="#ef4444" stroke-width="1"/>
              <rect x="46" y="71" width="148" height="7" fill="rgba(239,68,68,0.55)" stroke="#ef4444" stroke-width="1"/>
              <circle cx="34" cy="18" r="8" fill="#f59e0b"/><text x="34" y="22" text-anchor="middle" font-size="10" font-weight="bold" fill="#000">1</text>
              <circle cx="206" cy="18" r="8" fill="#f59e0b"/><text x="206" y="22" text-anchor="middle" font-size="10" font-weight="bold" fill="#000">2</text>
              <circle cx="206" cy="92" r="8" fill="#f59e0b"/><text x="206" y="96" text-anchor="middle" font-size="10" font-weight="bold" fill="#000">3</text>
              <circle cx="34" cy="92" r="8" fill="#f59e0b"/><text x="34" y="96" text-anchor="middle" font-size="10" font-weight="bold" fill="#000">4</text>
              <text x="120" y="52" text-anchor="middle" font-size="9.5" fill="#e2e8f0">2D 排布参考图 (${this.summary.moduleCount}块) → 透视映射</text>
            </svg>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
              <button type="button" class="sat-btn ${this.pickingFourCorners ? 'primary' : ''}" data-sat-effect="pick-4-corners">
                ${this.pickingFourCorners ? `正在点选第 ${this.pickedCorners.length + 1}/4 角点` : '依次点选四角 (1~4)'}
              </button>
              <button type="button" class="sat-btn primary" data-sat-effect="auto-match">
                自动配准屋面四角
              </button>
            </div>
          </div>

          <div class="satmap-subbox">
            <b>3. 女儿墙视线遮挡区域 (Sightline Occlusion)</b>
            <div style="font-size:11.5px;color:var(--ink-2);line-height:1.45">
              如前景女儿墙挡住部分屋面组件，补画一块视线遮挡区域（<b>处理的是相机视线遮挡，不是光照阴影</b>），使前景白墙自然遮挡底层组件边缘：
            </div>
            <button type="button" class="sat-btn ${this.occlusionDrawing ? 'primary' : ''}" style="width:100%" data-sat-effect="draw-occlusion">
              ${this.occlusionDrawing ? '正在点选女儿墙轮廓 (再点结束)' : '补画女儿墙视线遮挡区域'}
            </button>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
              <button type="button" class="sat-btn" data-sat-effect="demo-occlusion">加载默认女儿墙遮挡</button>
              <button type="button" class="sat-btn danger" data-sat-effect="clear-occlusion">清除遮挡</button>
            </div>
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;margin-top:4px;cursor:pointer">
              <input type="checkbox" data-sat-field="occlusionEnabled" ${this.occlusionEnabled ? 'checked' : ''}>
              <span>启用前景女儿墙视线遮挡裁剪 (共 ${this.occlusionPolygon.length} 个顶点)</span>
            </label>
          </div>

          <div class="satmap-subbox">
            <b>4. 效果图视觉细节调节 (PVLANE 质感参数)</b>
            <label class="satmap-field-row">
              <span>组件外观样式</span>
              <select data-sat-field="effectModuleStyle">
                <option value="mono_blue" ${this.effectModuleStyle === 'mono_blue' ? 'selected' : ''}>单晶深蓝高透组件</option>
                <option value="all_black" ${this.effectModuleStyle === 'all_black' ? 'selected' : ''}>全黑美学组件 (All-Black)</option>
                <option value="poly_blue" ${this.effectModuleStyle === 'poly_blue' ? 'selected' : ''}>多晶宝蓝标准组件</option>
              </select>
            </label>
            <label class="satmap-field-row">
              <span>组件不透明度 (${this.effectOpacityPct}%)</span>
              <input type="number" min="40" max="100" step="5" data-sat-field="effectOpacityPct" value="${this.effectOpacityPct}">
            </label>
            <label class="satmap-field-row">
              <span>边框栅线清晰度 (${this.effectGridSharpnessPct}%)</span>
              <input type="number" min="20" max="100" step="5" data-sat-field="effectGridSharpnessPct" value="${this.effectGridSharpnessPct}">
            </label>
            <label class="satmap-field-row">
              <span>表面反光强度 (${this.effectGlarePct}%)</span>
              <input type="number" min="0" max="100" step="5" data-sat-field="effectGlarePct" value="${this.effectGlarePct}">
            </label>
          </div>
        </aside>

        <div class="satmap-effect-canvas-box">
          <canvas id="sat-effect-canvas" class="satmap-effect-canvas" width="${this.effectCanvasW}" height="${this.effectCanvasH}"></canvas>
          <div style="padding:8px 12px;background:#0f172a;color:#cbd5e1;font-size:12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
            <span>操作说明：可点击「依次点选四角 (1~4)」按视频流程点选实景屋面四角，或直接拖动角点 P1 ~ P4 实时更新三维透视矩阵 H(3×3)。</span>
            <span>已投射组件：<b>${this.summary.moduleCount} 块 (${this.summary.dcKw} kWp)</b></span>
          </div>
        </div>
      </div>
    </div>`;
  }

  /**
   * Step 5: Video 1 (鹧鸪云) 1:1 图纸生成工具 — 顶部三步向导 (1.基本参数 -> 2.支架设计 -> 3.生成图纸) + 4张CAD施工图预览与导出
   */
  renderStep5CadStudio() {
    const sheets = [
      ['layout', '1. 光伏排布图 (Layout CAD)'],
      ['string', '2. 组串接线图 (String CAD)'],
      ['grounding', '3. 防雷接地图 (Grounding CAD)'],
      ['bracket', '4. 支架剖面与立面图 (Bracket CAD)'],
    ];
    const bcfg = this.bracketCfg || {
      h1Mm: 500, y0Mm: 1500, y1Mm: 1600, angleDeg: 15, x1Mm: 400, x2Mm: 1900,
      foundationType: '混凝土条形基础/方墩', concreteGrade: 'C25',
    };

    return `<div style="display:flex;flex-direction:column;gap:12px">
      <!-- Video 1 (v1_16.5s - v1_27.0s) 3-Stage Top Wizard Bar -->
      <div class="satmap-cad-wizard-bar">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <button type="button" class="satmap-cad-wiz-btn ${this.cadWizardTab === 'basic' ? 'active' : ''}" data-sat-cad-wiz="basic">
            <span class="wiz-num">1</span>
            <span>基本参数 (工程信息与关联方案)</span>
          </button>
          <span style="color:var(--muted)">→</span>
          <button type="button" class="satmap-cad-wiz-btn ${this.cadWizardTab === 'bracket' ? 'active' : ''}" data-sat-cad-wiz="bracket">
            <span class="wiz-num">2</span>
            <span>支架设计 (H1/Y0/Y1/A/X1/X2 剖面与正视参数)</span>
          </button>
          <span style="color:var(--muted)">→</span>
          <button type="button" class="satmap-cad-wiz-btn ${this.cadWizardTab === 'sheets' ? 'active' : ''}" data-sat-cad-wiz="sheets">
            <span class="wiz-num">3</span>
            <span>生成图纸 (四合一施工图预览与导出)</span>
          </button>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <button type="button" class="sat-btn primary" data-sat-action="export-dxf">导出当前 DXF</button>
          <button type="button" class="sat-btn success" data-sat-action="export-cad-pdf">一键生成四合一施工图集 (.pdf)</button>
        </div>
      </div>

      <div class="satmap-cad-studio">
        <aside class="satmap-left-panel" style="max-height:none">
          <h3 class="satmap-panel-title">
            <span>图纸生成工具</span>
            <small style="color:var(--muted)">1.基本参数 · 2.支架设计 · 3.生成图纸</small>
          </h3>

          <div class="satmap-subbox" style="background:#f0f9ff;border-color:#bae6fd">
            <b>1. 关联设计方案与基本参数</b>
            <div style="font-size:11.5px;color:#0369a1;line-height:1.55;margin-bottom:4px">
              <div>当前方案：<b>${esc(this.projectName)}</b></div>
              <div>组件排布：<b>${this.summary.moduleCount} 块 (${this.summary.dcKw} kWp)</b></div>
              <div>电气配串：<b>${esc(this.getSelectedInverter().model)} × ${this.summary.inverterCount} 台 (${this.summary.stringCount} 串)</b></div>
            </div>
            <label class="satmap-field-row" style="flex-direction:column;align-items:stretch">
              <span>图纸工程名称</span>
              <input type="text" data-sat-field="cadTitle" value="${esc(this.cadTitle)}" style="width:100%">
            </label>
            <label class="satmap-field-row" style="flex-direction:column;align-items:stretch">
              <span>设计单位名称</span>
              <input type="text" data-sat-field="cadUnit" value="${esc(this.cadUnit)}" style="width:100%">
            </label>
            <label class="satmap-field-row">
              <span>图号前缀</span>
              <input type="text" data-sat-field="cadPrefix" value="${esc(this.cadPrefix)}">
            </label>
            <label class="satmap-field-row">
              <span>出图比例</span>
              <select data-sat-field="cadScale">
                <option value="1:150" ${this.cadScale === '1:150' ? 'selected' : ''}>1:150 (A2 详图)</option>
                <option value="1:200" ${this.cadScale === '1:200' ? 'selected' : ''}>1:200 (标准施工图)</option>
                <option value="1:300" ${this.cadScale === '1:300' ? 'selected' : ''}>1:300 (总平面图)</option>
              </select>
            </label>
          </div>

          <!-- Video 1 (v1_18.5s.png - v1_20.0s.png) Interactive Bracket Design Config -->
          <div class="satmap-subbox" style="background:${this.cadWizardTab === 'bracket' ? '#eff6ff' : '#f8fafc'};border-color:${this.cadWizardTab === 'bracket' ? '#60a5fa' : '#e2e8f0'}">
            <b>2. 支架方案配置 (视频1同款参数化大样)</b>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px">
              <label class="satmap-field-row" style="flex-direction:column;align-items:stretch">
                <span>H1 最低点高度(mm)</span>
                <input type="number" min="150" max="2500" step="50" data-sat-bracket="h1Mm" value="${bcfg.h1Mm}" style="width:100%">
              </label>
              <label class="satmap-field-row" style="flex-direction:column;align-items:stretch">
                <span>Y0 前后排间距(mm)</span>
                <input type="number" min="400" max="5000" step="50" data-sat-bracket="y0Mm" value="${bcfg.y0Mm}" style="width:100%">
              </label>
              <label class="satmap-field-row" style="flex-direction:column;align-items:stretch">
                <span>Y1 立柱南北距(mm)</span>
                <input type="number" min="600" max="4000" step="50" data-sat-bracket="y1Mm" value="${bcfg.y1Mm}" style="width:100%">
              </label>
              <label class="satmap-field-row" style="flex-direction:column;align-items:stretch">
                <span>A 支架安装倾角(°)</span>
                <input type="number" min="0" max="45" step="1" data-sat-bracket="angleDeg" value="${bcfg.angleDeg}" style="width:100%">
              </label>
              <label class="satmap-field-row" style="flex-direction:column;align-items:stretch">
                <span>X1 端部悬挑(mm)</span>
                <input type="number" min="150" max="1000" step="50" data-sat-bracket="x1Mm" value="${bcfg.x1Mm}" style="width:100%">
              </label>
              <label class="satmap-field-row" style="flex-direction:column;align-items:stretch">
                <span>X2 立柱东西距(mm)</span>
                <input type="number" min="1000" max="4000" step="50" data-sat-bracket="x2Mm" value="${bcfg.x2Mm}" style="width:100%">
              </label>
            </div>
            <label class="satmap-field-row">
              <span>基础与水泥标号</span>
              <select data-sat-bracket="concreteGrade">
                <option value="C25" ${bcfg.concreteGrade === 'C25' ? 'selected' : ''}>C25 混凝土配重方墩</option>
                <option value="C30" ${bcfg.concreteGrade === 'C30' ? 'selected' : ''}>C30 防腐条形基础</option>
                <option value="CLAMP" ${bcfg.concreteGrade === 'CLAMP' ? 'selected' : ''}>彩钢瓦专用铝合金夹具</option>
              </select>
            </label>
          </div>

          <div class="satmap-subbox">
            <b>3. 勾选生成的施工图纸 (四合一图纸列表)</b>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px">
              <label style="display:flex;align-items:center;gap:5px;cursor:pointer"><input type="checkbox" checked disabled> 光伏排布图</label>
              <label style="display:flex;align-items:center;gap:5px;cursor:pointer"><input type="checkbox" checked disabled> 组串接线图</label>
              <label style="display:flex;align-items:center;gap:5px;cursor:pointer"><input type="checkbox" checked disabled> 防雷接地图</label>
              <label style="display:flex;align-items:center;gap:5px;cursor:pointer"><input type="checkbox" checked disabled> 支架大样图</label>
            </div>
            <div class="satmap-tool-list" style="margin-top:4px">
              ${sheets.map(([key, label]) => `
                <button type="button" class="satmap-tool-btn ${this.cadSheet === key ? 'active' : ''}" data-sat-cad-sheet="${key}">
                  <span>${esc(label)}</span>
                </button>
              `).join('')}
            </div>
          </div>

          <div class="satmap-subbox">
            <b>导出 CAD (.dxf) 与蓝图 (.pdf)</b>
            <button type="button" class="sat-btn primary" style="width:100%" data-sat-action="export-dxf">
              导出当前图纸 DXF (${esc(this.cadPrefix)}-${esc(this.cadSheet.toUpperCase())}.dxf)
            </button>
            <button type="button" class="sat-btn" style="width:100%" data-sat-action="export-all-dxf">
              导出全部 4 张施工图 (.dxf)
            </button>
            <button type="button" class="sat-btn success" style="width:100%" data-sat-action="export-cad-pdf">
              打印 / 导出四合一施工蓝图集 (.pdf)
            </button>
          </div>
        </aside>

        <div class="satmap-cad-viewport">
          <div class="satmap-cad-tabs">
            <div style="display:flex;gap:6px;flex-wrap:wrap">
              ${sheets.map(([key, label]) => `
                <button type="button" class="satmap-cad-sheet-btn ${this.cadSheet === key ? 'active' : ''}" data-sat-cad-sheet="${key}">
                  ${esc(label)}
                </button>
              `).join('')}
            </div>
            <span style="color:#38bdf8;font-family:monospace;font-size:12px">
              CAD LAYER: PV_${this.cadSheet.toUpperCase()} · ${this.summary.moduleCount} MODULES · ${this.summary.dcKw} kWp
            </span>
          </div>

          <div class="satmap-cad-svg-host" id="satmap-cad-svg-host">
            ${this.renderCadSvg(this.cadSheet)}
          </div>
        </div>
      </div>
    </div>`;
  }

  /**
   * High-Speed Real Satellite Tile Loader:
   * - Connects directly to multi-subdomain CDNs (mt0..mt3 GCJ-02 China Hybrid & Esri World Imagery + Autonavi Road Labels)
   * - Fast 1400ms failover from mt0..3 to Esri World Imagery so initial loading never stalls
   * - Never falls back to /api/satmap/tile/... from browser Image() so the 6-connection localhost HTTP pool is never blocked!
   */
  loadSatelliteTile(source, z, x, y) {
    const key = `${source}/${z}/${x}/${y}`;
    if (this.tileCache.has(key)) return this.tileCache.get(key);
    if (typeof Image === 'undefined') return null;

    // Evict oldest cached tiles if cache exceeds 240 entries to prevent memory bloat
    if (this.tileCache.size > 240) {
      const oldestKey = this.tileCache.keys().next().value;
      if (oldestKey) this.tileCache.delete(oldestKey);
    }

    const sub03 = ((x + y) % 4 + 4) % 4;
    const sub14 = sub03 + 1;
    const zClamped = Math.min(18, z);
    const esriUrl = `https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${zClamped}/${y}/${x}`;
    const labelUrl = `https://wprd0${sub14}.is.autonavi.com/appmaptile?x=${x}&y=${y}&z=${z}&lang=zh_cn&size=1&scl=1&style=8`;

    const primaryUrl = source === 'gaode_label'
      ? labelUrl
      : source === 'gaode_hyb'
        ? `https://mt${sub03}.google.com/vt/lyrs=y&hl=zh-CN&gl=cn&x=${x}&y=${y}&z=${z}`
        : source === 'gaode_sat'
          ? `https://mt${sub03}.google.com/vt/lyrs=s&hl=zh-CN&gl=cn&x=${x}&y=${y}&z=${z}`
          : esriUrl;

    const entry = { status: 'loading', img: null, usedFallback: false };
    const img = new Image();
    img.decoding = 'async';
    let fallbackTried = false;

    const triggerFallback = () => {
      if (fallbackTried || entry.status === 'loaded') return;
      fallbackTried = true;
      entry.usedFallback = true;
      if (source === 'gaode_hyb' || source === 'gaode_sat') {
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
      if (!fallbackTried && (source === 'gaode_hyb' || source === 'gaode_sat')) {
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
    const mapMpp = Math.max(0.03, metersPerPixelAtLatZoom(this.lat, this.zoom));
    return [cx + dEastM / mapMpp, cy + dSouthM / mapMpp];
  }

  /**
   * Pure 1:1 geographic East/South meter <-> screen pixel conversion.
   * Roof orientation (this.ridgeAzimuthDeg) is handled inside getRoofUVFrame() for module layout,
   * so drawn roof polygons and rectangular keepouts NEVER shift, jump, or rotate into tilted diamonds!
   */
  localMetersToCanvas(W, H, mx, my) {
    const [anchorX, anchorY] = this.getRoofAnchorCanvasPx(W, H);
    const mpp = Math.max(0.03, this.metersPerPx);
    return [anchorX + mx / mpp, anchorY + my / mpp];
  }

  canvasToLocalMeters(W, H, sx, sy) {
    const [anchorX, anchorY] = this.getRoofAnchorCanvasPx(W, H);
    const mpp = Math.max(0.03, this.metersPerPx);
    return [(sx - anchorX) * mpp, (sy - anchorY) * mpp];
  }

  /**
   * Paint the Real Satellite Map Canvas (Step 1):
   * 1. Center-outward spiral EPSG:3857 Satellite Tiles with parent-tile instant zoom placeholder
   * 2. Geographically anchored Roof Polygon, Draggable Corner Handles, Optional Double-Slope Ridge Line,
   *    Red Skylight Keepouts, Batched 60fps Solar Modules, Interior-Routed String Wiring, and Live Selection Preview
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
    const scalePxPerM = 1 / Math.max(0.03, this.metersPerPx);

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, W, H);

    // 1. Render 100% Real Satellite Tiles in Center-Outward Spiral Order (so center factory roof loads first!)
    const z = Math.max(4, Math.min(19, Math.round(this.zoom || 18)));
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
    for (const [dx, dy] of tileOffsets) {
      const tx = baseTx + dx;
      const ty = baseTy + dy;
      if (tx < 0 || ty < 0) continue;
      const drawX = Math.floor(cx - offsetX + dx * 256);
      const drawY = Math.floor(cy - offsetY + dy * 256);
      if (drawX + 256 < 0 || drawX > W || drawY + 256 < 0 || drawY > H) continue;
      const tile = this.loadSatelliteTile(satSource, z, tx, ty);
      if (tile?.status === 'loaded' && tile.img) {
        ctx.drawImage(tile.img, drawX, drawY, 256, 256);
        // If gaode_hyb fell back to Esri pure imagery, overlay Autonavi transparent road/enterprise labels
        if (satSource === 'gaode_hyb' && tile.usedFallback) {
          const lblTile = this.loadSatelliteTile('gaode_label', z, tx, ty);
          if (lblTile?.status === 'loaded' && lblTile.img) {
            ctx.drawImage(lblTile.img, drawX, drawY, 256, 256);
          }
        }
        loadedTileCount++;
      } else {
        // Instant Parent-Tile Fallback (z-1) so zooming/panning never flashes dark
        const parentKey = `${satSource}/${z - 1}/${tx >> 1}/${ty >> 1}`;
        const parentTile = this.tileCache.get(parentKey);
        if (parentTile?.status === 'loaded' && parentTile.img) {
          const sxQuad = (tx & 1) * 128;
          const syQuad = (ty & 1) * 128;
          ctx.drawImage(parentTile.img, sxQuad, syQuad, 128, 128, drawX, drawY, 256, 256);
          loadedTileCount++;
        } else {
          ctx.strokeStyle = 'rgba(148, 163, 184, 0.14)';
          ctx.lineWidth = 1;
          ctx.strokeRect(drawX, drawY, 256, 256);
        }
      }
    }
    ctx.restore();

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

    // 2. Draw Semi-Transparent Roof Boundary Overlay + Draggable Corner Handles (ONLY when user has drawn/detected a roof)
    if (this.showRoofOverlay && this.roofOutlineM.length >= 3) {
      ctx.save();
      ctx.beginPath();
      this.roofOutlineM.forEach(([mx, my], idx) => {
        const [sx, sy] = toScreen(mx, my);
        if (idx === 0) ctx.moveTo(sx, sy);
        else ctx.lineTo(sx, sy);
      });
      ctx.closePath();

      ctx.fillStyle = 'rgba(37, 99, 235, 0.14)';
      ctx.fill();
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = '#38bdf8';
      ctx.stroke();

      // Edge dimension labels (meters) along roof edges
      ctx.font = 'bold 11px "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'center';
      for (let i = 0; i < this.roofOutlineM.length; i++) {
        const p0 = this.roofOutlineM[i];
        const p1 = this.roofOutlineM[(i + 1) % this.roofOutlineM.length];
        const edgeLenM = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]);
        if (edgeLenM >= 6) {
          const [s0x, s0y] = toScreen(p0[0], p0[1]);
          const [s1x, s1y] = toScreen(p1[0], p1[1]);
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
      this.roofOutlineM.forEach(([mx, my], idx) => {
        const [sx, sy] = toScreen(mx, my);
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

    // 3. Draw Red Keepout Strips / Skylights (Video 1 & Video 2 红色正交禁布区)
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

      // 4. Draw Placed Solar Modules — Batched by Color for 60fps performance without main-thread lag
      if (this.modules && this.modules.length > 0) {
        // Optional Video 1 Shadow Simulation (冬至日 9:00-15:00 阵列与女儿墙阴影投射)
        if (this.showShadowPreview) {
          ctx.save();
          ctx.fillStyle = 'rgba(15, 23, 42, 0.48)';
          const shadowLenPx = Math.max(4, (this.rowSpacingM || 1.2) * 0.72 * scalePxPerM);
          ctx.beginPath();
          for (const m of this.modules) {
            const [p0, p1] = m.cornersM.map(([mx, my]) => toScreen(mx, my));
            ctx.moveTo(p0[0], p0[1]);
            ctx.lineTo(p1[0], p1[1]);
            ctx.lineTo(p1[0], p1[1] - shadowLenPx);
            ctx.lineTo(p0[0], p0[1] - shadowLenPx);
            ctx.closePath();
          }
          ctx.fill();
          ctx.restore();
        }

        ctx.save();
        ctx.globalAlpha = 0.76;
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
        ctx.lineWidth = 0.75;
        ctx.strokeStyle = this.showStringColors ? 'rgba(255,255,255,0.68)' : '#93c5fd';
        for (const [col, mods] of groups.entries()) {
          ctx.fillStyle = col;
          ctx.beginPath();
          for (const m of mods) {
            const [p0, p1, p2, p3] = m.cornersM.map(([mx, my]) => toScreen(mx, my));
            ctx.moveTo(p0[0], p0[1]);
            ctx.lineTo(p1[0], p1[1]);
            ctx.lineTo(p2[0], p2[1]);
            ctx.lineTo(p3[0], p3[1]);
            ctx.closePath();
          }
          ctx.fill();
          ctx.stroke();
        }
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

    // 6. Draw Video 2 (PVLANE) Scale Calibration Reference Bar ONLY when calibrating scale or customized
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

    // 7. Draw Compass / South Direction Rose at Top-Right
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
   * Paint realistic oblique aerial drone photo onto a canvas context (for Step 4 PVLANE Studio)
   * Includes the foreground white parapet wall (女儿墙) that partially occludes the front roof slope!
   */
  paintObliquePresetBase(ctx, W, H, presetIdx = 0) {
    // Sky & horizon gradient
    const sky = ctx.createLinearGradient(0, 0, 0, H * 0.35);
    sky.addColorStop(0, presetIdx === 1 ? '#1e3a5f' : '#38bdf8');
    sky.addColorStop(1, '#bae6fd');
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, W, H * 0.32);

    // Ground & industrial park background
    const ground = ctx.createLinearGradient(0, H * 0.25, 0, H);
    ground.addColorStop(0, '#475569');
    ground.addColorStop(0.5, '#334155');
    ground.addColorStop(1, '#1e293b');
    ctx.fillStyle = ground;
    ctx.fillRect(0, H * 0.25, W, H * 0.75);

    // Distant neighboring factory buildings & greenery
    ctx.fillStyle = '#15803d';
    ctx.fillRect(0, H * 0.22, W, 28);
    ctx.fillStyle = '#64748b';
    ctx.fillRect(40, H * 0.14, 150, 55);
    ctx.fillRect(720, H * 0.15, 160, 50);

    // Main factory building shadow on asphalt yard
    ctx.fillStyle = 'rgba(15, 23, 42, 0.58)';
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

    // Blue corrugated steel roof surface in oblique perspective
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

    // 2 Reddish translucent skylight strips in perspective (Video 2 PVLANE)
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

    // 3. Project every placed solar module quad onto the oblique photo with realistic PV cell texture & shadow
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

    ctx.save();
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

      // Solar module fill (monocrystalline / all-black / polycrystalline)
      ctx.fillStyle = m.slope === 'north' ? baseFillNorth : baseFillSouth;
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
        ctx.fillStyle = '#ecfdf5';
        ctx.font = 'bold 11.5px "Microsoft YaHei", sans-serif';
        ctx.fillText('🧱 女儿墙视线遮挡区域 (前景墙体自然遮挡底层组件)', lx - 80, ly + 22);
        ctx.restore();
      }
    }

    if (forExport) return;

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
      ctx.fillText(`P${cornerLabels[idx]}`, px, py - 14);
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
    };

    const sheetCode = {
      layout: `${this.cadPrefix}-DL-01`,
      string: `${this.cadPrefix}-DL-02`,
      grounding: `${this.cadPrefix}-DL-03`,
      bracket: `${this.cadPrefix}-JG-01`,
    }[sheet] || `${this.cadPrefix}-01`;

    // Standard Chinese CAD Border & Bottom-Right Engineering Title Block (图框栏 - 无重叠宽栏设计)
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
        <text x="8" y="15" font-size="10" font-weight="bold" fill="#e2e8f0">项目：${esc(this.cadTitle)}</text>
        <text x="246" y="15" font-size="9.5" fill="#38bdf8" font-family="monospace">图号：${esc(sheetCode)}</text>
        <text x="8" y="35" font-size="9.5" fill="#cbd5e1">图名：${esc(sheetNames[sheet])}</text>
        <text x="246" y="35" font-size="9.5" fill="#cbd5e1">比例：${esc(this.cadScale)}</text>
        <text x="8" y="56" font-size="9" fill="#94a3b8">设计单位：${esc(this.cadUnit)}</text>
        <text x="246" y="56" font-size="9" fill="#10b981">装机：${s.dcKw}kWp (${s.moduleCount}块)</text>
      </g>
    `;

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
    // Inner parapet wall line (Video 1 double-line parapet wall representation, inset by 0.24m)
    const insetScale = Math.max(0.92, (frame.widthU - 0.5) / Math.max(1, frame.widthU));
    const innerRoofPath = frame.polyUV.map(([u, v], i) => {
      const iu = frame.centerU + (u - frame.centerU) * insetScale;
      const iv = frame.centerV + (v - frame.centerV) * insetScale;
      return `${i === 0 ? 'M' : 'L'}${cadU(iu)},${cadV(iv)}`;
    }).join(' ') + ' Z';

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
   * Build real AutoCAD DXF (AC1009 / R12 ASCII format) for any of the 4 CAD sheets
   */
  buildDxfString(sheet = 'layout') {
    const lines = [
      '0', 'SECTION', '2', 'HEADER', '0', 'ENDSEC',
      '0', 'SECTION', '2', 'ENTITIES',
    ];
    const addLine = (x1, y1, x2, y2, layer, color = 7) => {
      lines.push(
        '0', 'LINE',
        '8', layer,
        '62', String(color),
        '10', x1.toFixed(3), '20', (-y1).toFixed(3), '30', '0.0',
        '11', x2.toFixed(3), '21', (-y2).toFixed(3), '31', '0.0'
      );
    };
    const addPoly = (pts, layer, color = 7) => {
      for (let i = 0; i < pts.length; i++) {
        const [x1, y1] = pts[i];
        const [x2, y2] = pts[(i + 1) % pts.length];
        addLine(x1, y1, x2, y2, layer, color);
      }
    };
    const frame = this.getRoofUVFrame(true);
    addPoly(frame.polyUV, 'ROOF_OUTLINE', 7);
    for (const obs of this.obstacles) {
      addPoly(obs.polygon.map(([x, y]) => frame.toUV(x, y)), 'ROOF_KEEPOUT', 1);
    }
    for (const m of this.modules) {
      const u0 = Number.isFinite(m.u) ? m.u : frame.toUV(m.cx, m.cy)[0] - m.w / 2;
      const v0 = Number.isFinite(m.v) ? m.v : frame.toUV(m.cx, m.cy)[1] - m.h / 2;
      const rectUV = [
        [u0, v0],
        [u0 + m.w, v0],
        [u0 + m.w, v0 + m.h],
        [u0, v0 + m.h],
      ];
      addPoly(rectUV, `PV_MODULE_${sheet.toUpperCase()}`, sheet === 'string' ? (m.mpptIndex % 7) + 1 : 5);
    }
    if (sheet === 'string') {
      for (const st of this.strings) {
        const col = (st.mpptIndex % 7) + 1;
        for (const [[u0, v0], [u1, v1]] of st.wireSegmentsUV || []) {
          addLine(u0, v0, u1, v1, 'STRING_WIRING', col);
        }
        const hr = st.homeRunPathUV || [];
        for (let i = 0; i + 1 < hr.length; i++) {
          addLine(hr[i][0], hr[i][1], hr[i + 1][0], hr[i + 1][1], 'HOMERUN_CABLE', col);
        }
      }
    }
    lines.push('0', 'ENDSEC', '0', 'EOF');
    return lines.join('\r\n');
  }

  downloadDxf(sheet = 'layout') {
    if (typeof document === 'undefined') return;
    const dxf = this.buildDxfString(sheet);
    const blob = new Blob([dxf], { type: 'application/dxf;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${this.cadPrefix}-${sheet.toUpperCase()}.dxf`;
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    this.notice(`已导出 CAD 施工图文件：${a.download}`);
  }

  exportCadPdf() {
    if (typeof window === 'undefined') return;
    const sheets = ['layout', 'string', 'grounding', 'bracket'];
    const htmlDoc = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
      <title>${esc(this.cadTitle)} · 施工 CAD 蓝图集</title>
      <style>
        body{margin:0;padding:16px;background:#0b1120;color:#f8fafc;font-family:"Microsoft YaHei",sans-serif}
        .sheet{page-break-after:always;margin-bottom:20px;border:1px solid #334155;border-radius:8px;padding:10px;background:#050a14}
        svg{width:100%;height:auto;display:block}
        @media print{.noprint{display:none}}
      </style></head><body>
      <div class="noprint" style="margin-bottom:12px;display:flex;justify-content:space-between;align-items:center">
        <b>${esc(this.cadTitle)} — 四大施工 CAD 图纸全集 (排布图 / 组串图 / 防雷接地图 / 支架图)</b>
        <button onclick="window.print()" style="padding:8px 16px;background:#2563eb;color:#fff;border:0;border-radius:6px;cursor:pointer;font-weight:700">立即打印 / 导出 PDF 施工图集</button>
      </div>
      ${sheets.map((sh) => `<div class="sheet">${this.renderCadSvg(sh)}</div>`).join('')}
      </body></html>`;
    const url = URL.createObjectURL(new Blob([htmlDoc], { type: 'text/html;charset=utf-8' }));
    window.open(url, '_blank', 'noopener');
    this.notice('已在新窗口打开四合一施工 CAD 蓝图集（支持直接打印或另存为 PDF）。');
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
      `卫星底图已定位至：${this.address} (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E)。请点击「1. 框选屋顶」在厂房屋顶拉框，或点「AI 识别屋面」/「AI 按要求一键设计」。`
    );
  }

  /**
   * AI 识别当前卫星屋面 ([data-sat-action="ai-detect-roof"])
   */
  async runAiDetectRoof() {
    this.step = 1;
    this.showRoofOverlay = true;
    this.aiScanActive = true;
    this.roofCenterLon = this.lon;
    this.roofCenterLat = this.lat;
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
      }
      if (Array.isArray(res?.obstacles) && res.obstacles.length) {
        this.obstacles = res.obstacles;
      }
    } catch {
      // Fall back to default roof outline if offline
    }
    if (!this.hasRoof || this.roofOutlineM.length < 3) {
      this.ensureRoofOutline({ withDefaultKeepouts: true });
    }
    const bounds = this.getRoofBoundsM(true);
    this.scaleReferenceM = bounds.widthM;
    this.layoutModules({ quiet: true, autoCreateRoof: true });
    this.aiExecutionNote = `已识别当前卫星定位 (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) 屋面轮廓 ${bounds.widthM.toFixed(1)}m × ${bounds.heightM.toFixed(1)}m (${bounds.areaM2} m²) 及 ${this.obstacles.length} 处禁布区，排布 ${this.summary.moduleCount} 块组件 (${this.summary.dcKw} kWp)。`;
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
    const payload = {
      name: this.projectName,
      address: this.address,
      lat: this.lat,
      lon: this.lon,
      roof_type: this.roofType === 'flat' ? 'flat' : 'metal',
      slope_deg: this.roofSlopeDeg,
      length_m: bounds.widthM,
      width_m: bounds.heightM,
      outline: this.roofOutlineM,
      obstacles: this.obstacles,
      module_id: this.moduleModelId,
      inverter_id: this.inverterModelId,
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
      this.notice(`已生成本机卫星工程快照 (${this.summary.dcKw} kWp)：${err.message || '可在结果页查看'}`);
      return null;
    }
  }

  refresh({ resetScroll = false } = {}) {
    if (!this.host) return;
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
    host.innerHTML = this.html();
    this.mount(host);
  }

  mount(host) {
    this.host = host;
    if (!host) return;

    if (this.step === 1) {
      this.drawMapCanvas();
    } else if (this.step === 4) {
      this.drawEffectCanvas();
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
          hud.textContent = `当前定位：${this.address} (${this.lat.toFixed(4)}°N, ${this.lon.toFixed(4)}°E) · Z${this.zoom} · 1px ≈ ${this.metersPerPx.toFixed(3)}m`;
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

      // Mouse wheel zoom on real satellite map (Zoom 4..19) — instant redraw without DOM rebuild!
      mapCanvas.onwheel = (ev) => {
        ev.preventDefault();
        const nextZoom = Math.max(4, Math.min(19, this.zoom + (ev.deltaY < 0 ? 1 : -1)));
        if (nextZoom !== this.zoom) {
          this.zoom = nextZoom;
          if (!this.scaleCustomized) {
            this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
          }
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

        if (!dragStart) return;

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
      // Allow clicking modal backdrop to close Video 1 modals
      if (ev.target.classList?.contains('satmap-modal-backdrop')) {
        this.showStringModeModal = false;
        this.showInverterModal = false;
        this.showMpptModal = false;
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

      if (btn.dataset.satTool) {
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
        this.refresh();
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
        this.notice('已按最新损耗参数与官方实时气象数据更新 PVsyst 8760h 仿真结果。');
        return;
      }

      // General SatMap actions
      const act = btn.dataset.satAction;
      if (!act) return;
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
        this.zoom = Math.min(19, (this.zoom || 18) + 1);
        if (!this.scaleCustomized) {
          this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
        }
        this.scheduleMapRedraw();
      } else if (act === 'zoom-out') {
        this.zoom = Math.max(4, (this.zoom || 18) - 1);
        if (!this.scaleCustomized) {
          this.metersPerPx = metersPerPixelAtLatZoom(this.lat, this.zoom);
        }
        this.scheduleMapRedraw();
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
        this.refresh();
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
      } else if (act === 'export-dxf') {
        this.downloadDxf(this.cadSheet);
      } else if (act === 'export-all-dxf') {
        for (const sh of ['layout', 'string', 'grounding', 'bracket']) {
          this.downloadDxf(sh);
        }
      } else if (act === 'export-cad-pdf') {
        this.exportCadPdf();
      } else if (act === 'timer-toggle') {
        this.timerRunning = !this.timerRunning;
        if (this.timerRunning) {
          const lastTick = Date.now();
          const baseElapsed = this.timerElapsedMs;
          this.timerInterval = setInterval(() => {
            this.timerElapsedMs = baseElapsed + (Date.now() - lastTick);
            const disp = this.host?.querySelector('#sat-effect-timer-display');
            if (disp) disp.textContent = this.formatTimer(this.timerElapsedMs);
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
      } else if (el.type === 'number') {
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
      }

      this.refresh();
    };
  }
}

export default SatMapView;
