/**
 * 光筑 (Guangzhu) Engineering-Grade 3D Digital Twin & Physical Ray-Tracing Simulation Engine
 * - Deterministic 3D roof/gable/parapet/obstacle/racking/module geometry synthesis
 * - Exact solar position vector + 12-point sub-cell raycasting + 3-bypass-diode electrical mismatch solver
 * - Procedural high-DPI PBR CanvasTextures (N-type TOPCon half-cut cells, standing-seam metal roof, concrete SBS deck)
 * - Interactive WebGL Three.js 3D viewport with sun-path celestial dome, multi-mode heatmaps, and camera presets
 */

const DEG2RAD = Math.PI / 180;
const RAD2DEG = 180 / Math.PI;

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const finite = (v, fb = 0) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fb;
};

/**
 * Compute exact solar altitude, azimuth (0°=N, 90°=E, 180°=S, 270°=W),
 * and 3D world unit vector in (+X = East, +Y = Up, +Z = South, -Z = North).
 */
export function computeSolarVectorBjt(lat, lon, dateStr = '2026-12-21', hourBjt = 9.5) {
  const safeLat = clamp(finite(lat, 32.48), -66.5, 66.5);
  const safeLon = clamp(finite(lon, 119.92), -180, 180);
  const safeHour = clamp(finite(hourBjt, 12.0), 0, 24);
  const parsed = new Date(`${dateStr}T00:00:00Z`);
  const dayMs = Number.isFinite(parsed.getTime()) ? parsed.getTime() : Date.UTC(2026, 11, 21);
  const year = new Date(dayMs).getUTCFullYear();
  const doy = Math.max(1, Math.min(366, Math.round((dayMs - Date.UTC(year, 0, 0)) / 86400000)));

  const gamma = ((2 * Math.PI) / 365) * (doy - 1 + (safeHour - 12) / 24);
  const eqTimeMin = 229.18 * (
    0.000075 +
    0.001868 * Math.cos(gamma) -
    0.032077 * Math.sin(gamma) -
    0.014615 * Math.cos(2 * gamma) -
    0.040849 * Math.sin(2 * gamma)
  );
  const declRad =
    0.006918 -
    0.399912 * Math.cos(gamma) +
    0.070257 * Math.sin(gamma) -
    0.006758 * Math.cos(2 * gamma) +
    0.000907 * Math.sin(2 * gamma) -
    0.002697 * Math.cos(3 * gamma) +
    0.00148 * Math.sin(3 * gamma);

  const solarTimeMin = safeHour * 60 + eqTimeMin + 4 * safeLon - 480;
  const hourAngleRad = (solarTimeMin / 4 - 180) * DEG2RAD;
  const phiRad = safeLat * DEG2RAD;

  const sinAlt = clamp(
    Math.sin(phiRad) * Math.sin(declRad) + Math.cos(phiRad) * Math.cos(declRad) * Math.cos(hourAngleRad),
    -1,
    1
  );
  const altRad = Math.asin(sinAlt);
  const azRad =
    Math.atan2(
      Math.sin(hourAngleRad),
      Math.cos(hourAngleRad) * Math.sin(phiRad) - Math.tan(declRad) * Math.cos(phiRad)
    ) + Math.PI;

  const altitudeDeg = altRad * RAD2DEG;
  const azimuthDeg = ((azRad * RAD2DEG) % 360 + 360) % 360;
  const cosAlt = Math.cos(altRad);
  // World axes: +X = East, +Y = Up, +Z = South, -Z = North
  const dir = [
    Math.sin(azRad) * cosAlt,
    Math.sin(altRad),
    -Math.cos(azRad) * cosAlt,
  ];

  // Clear-sky Ineichen/Hottel irradiance estimate (W/m²)
  let dniWm2 = 0;
  let dhiWm2 = 0;
  let ghiWm2 = 0;
  if (altitudeDeg > 0.5) {
    const am = 1 / (Math.max(0.02, sinAlt) + 0.50572 * Math.pow(altitudeDeg + 6.07995, -1.6364));
    dniWm2 = 965 * Math.pow(0.78, Math.pow(am, 0.678));
    dhiWm2 = 118 * Math.pow(Math.max(0, sinAlt), 0.66);
    ghiWm2 = dniWm2 * Math.max(0, sinAlt) + dhiWm2;
  }

  return {
    altitudeDeg: Number(altitudeDeg.toFixed(3)),
    azimuthDeg: Number(azimuthDeg.toFixed(3)),
    solarTimeHours: Number((solarTimeMin / 60).toFixed(3)),
    direction: dir,
    dniWm2: Number(dniWm2.toFixed(1)),
    dhiWm2: Number(dhiWm2.toFixed(1)),
    ghiWm2: Number(ghiWm2.toFixed(1)),
  };
}

function distToSegment2D(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lenSq = dx * dx + dy * dy;
  if (lenSq < 1e-9) return Math.hypot(px - x1, py - y1);
  const t = clamp(((px - x1) * dx + (py - y1) * dy) / lenSq, 0, 1);
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

function minDistToPolygonPerimeter(px, py, poly) {
  if (!Array.isArray(poly) || poly.length < 3) return 999;
  let best = Infinity;
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i];
    const b = poly[(i + 1) % poly.length];
    const d = distToSegment2D(px, py, a[0], a[1], b[0], b[1]);
    if (d < best) best = d;
  }
  return best;
}

function inferObstacleHeightM(obs, heightScale = 1.0) {
  const explicit = Number(obs?.height_m ?? obs?.heightM);
  if (Number.isFinite(explicit) && explicit > 0.05) {
    return explicit * heightScale;
  }
  const text = `${obs?.kind || ''} ${obs?.name || ''}`.toLowerCase();
  let base = 1.4;
  if (/电梯|机房|梯间|楼梯|penthouse|stair|elevator/.test(text)) base = 2.9;
  else if (/风机|空调|冷却|冷水|hvac|chiller|fan/.test(text)) base = 2.2;
  else if (/通风|排烟|烟囱|排气|vent|chimney/.test(text)) base = 1.65;
  else if (/采光|天窗|skylight/.test(text)) base = 0.55;
  return Number((base * clamp(finite(heightScale, 1.0), 0.2, 3.0)).toFixed(2));
}

function inferObstacleStyle(obs) {
  const text = `${obs?.kind || ''} ${obs?.name || ''}`.toLowerCase();
  if (/电梯|机房|梯间|楼梯|penthouse|stair|elevator/.test(text)) return 'penthouse';
  if (/风机|空调|冷却|冷水|hvac|chiller|fan/.test(text)) return 'hvac';
  if (/通风|排烟|烟囱|排气|vent|chimney/.test(text)) return 'vent';
  return 'skylight';
}

/**
 * Build exact 3D geometric specification (in world meters centered on roof centroid)
 * from SatMapView / benchmark design state.
 * World coordinate system: +X = East, +Y = Up, +Z = South, -Z = North.
 */
export function buildSatmap3DGeometrySpec(state = {}) {
  const rawOutline = Array.isArray(state.roofOutlineM) && state.roofOutlineM.length >= 3
    ? state.roofOutlineM
    : [[-38, -18], [38, -18], [38, 18], [-38, 18]];

  const xs = rawOutline.map((p) => finite(p[0]));
  const ys = rawOutline.map((p) => finite(p[1]));
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const centerX = (minX + maxX) * 0.5;
  const centerY = (minY + maxY) * 0.5;
  const widthM = Math.max(4, maxX - minX);
  const depthM = Math.max(4, maxY - minY);
  const spanM = Math.max(16, widthM, depthM);

  const buildingHeightM = clamp(finite(state.buildingHeightM, 12.0), 3.0, 80.0);
  const roofType = state.roofType || 'single_slope'; // 'flat' | 'double_slope' | 'single_slope'
  const roofSlopeDeg = roofType === 'flat' ? 0 : clamp(finite(state.roofSlopeDeg, 6), 0, 45);
  const roofSlopeRad = roofSlopeDeg * DEG2RAD;
  const tiltDeg = roofType === 'flat' ? clamp(finite(state.tiltDeg, 15), 0, 60) : roofSlopeDeg;
  const azimuthDeg = finite(state.azimuthDeg, 180);
  const ridgeAzimuthDeg = finite(state.ridgeAzimuthDeg, 0);
  const ridgeRad = ridgeAzimuthDeg * DEG2RAD;

  const uAxis = [Math.cos(ridgeRad), Math.sin(ridgeRad)];
  const vAxis = [-Math.sin(ridgeRad), Math.cos(ridgeRad)]; // Points South when ridgeAzimuthDeg = 0
  const projU = (mx, my) => (mx - centerX) * uAxis[0] + (my - centerY) * uAxis[1];
  const projV = (mx, my) => (mx - centerX) * vAxis[0] + (my - centerY) * vAxis[1];

  const vCoords = rawOutline.map(([mx, my]) => projV(mx, my));
  const uCoords = rawOutline.map(([mx, my]) => projU(mx, my));
  const vMin = Math.min(...vCoords);
  const vMax = Math.max(...vCoords);
  const uMin = Math.min(...uCoords);
  const uMax = Math.max(...uCoords);
  const midV = (vMin + vMax) * 0.5;
  const halfSpanV = Math.max(0.5, (vMax - vMin) * 0.5);
  const fullSpanV = Math.max(1.0, vMax - vMin);

  const roofElevationAt = (mx, my) => {
    if (roofType === 'flat' || roofSlopeDeg <= 0.05) return buildingHeightM;
    const v = projV(mx, my);
    if (roofType === 'double_slope') {
      const distFromRidge = Math.min(halfSpanV, Math.abs(v - midV));
      return buildingHeightM + (halfSpanV - distFromRidge) * Math.tan(roofSlopeRad);
    }
    // single_slope: slopes downward toward South (+v) so main array faces South
    const riseFromSouthEave = clamp(vMax - v, 0, fullSpanV);
    return buildingHeightM + riseFromSouthEave * Math.tan(roofSlopeRad);
  };

  const ridgePeakY = roofType === 'double_slope'
    ? buildingHeightM + halfSpanV * Math.tan(roofSlopeRad)
    : roofType === 'single_slope'
      ? buildingHeightM + fullSpanV * Math.tan(roofSlopeRad)
      : buildingHeightM;

  const parapetHeightM = roofType === 'flat'
    ? clamp(finite(state.parapetHeightMm, 500) / 1000, 0, 2.8)
    : clamp(finite(state.parapetHeightMm, 0) / 1000, 0, 2.0) * (state.forceParapetOnMetal ? 1 : 0);
  const parapetWidthM = clamp(finite(state.parapetWidthMm, 240) / 1000, 0.12, 0.6);
  const obstacleHeightScale = clamp(finite(state.obstacleHeightScale, 1.0), 0.25, 2.5);

  // GB 50009 / GB 55001 roof wind zone width `a`
  const windEdgeBandM = Math.max(1.5, Math.min(0.1 * Math.min(widthM, depthM), 0.4 * buildingHeightM, 5.0));

  const toWorld = (mx, my, yUp = 0) => [mx - centerX, yUp, my - centerY];
  const outlineWorld2D = rawOutline.map(([mx, my]) => [mx - centerX, my - centerY]);

  // Build 3D PV modules
  const rawModules = Array.isArray(state.modules) ? state.modules : [];
  const subArrayClearM = roofType === 'flat'
    ? clamp((finite(state.subArrayHeightMm, 350) / 1000) * 0.28, 0.16, 0.85)
    : 0.11;

  // Map module id -> string info
  const stringByModId = new Map();
  const rawStrings = Array.isArray(state.strings) ? state.strings : [];
  rawStrings.forEach((st, sIdx) => {
    const mods = Array.isArray(st.modules) ? st.modules : [];
    for (const m of mods) {
      if (m?.id) stringByModId.set(m.id, { ...st, stringIndex: sIdx });
    }
  });

  const modules3d = rawModules.map((m, idx) => {
    const cx = finite(m.cx, 0);
    const cy = finite(m.cy, 0);
    const modW = Math.max(0.5, finite(m.w, 1.134));
    const modH = Math.max(0.5, finite(m.h, 2.278));
    const slopeTag = roofType === 'double_slope' ? (m.slope || (projV(cx, cy) < midV ? 'north' : 'south')) : 'south';

    // Determine physical module tilt & down-slope horizontal unit vector in (X=East, Z=South)
    let modTiltDeg = tiltDeg;
    let downSlopeXZ = [vAxis[0], vAxis[1]]; // Default: faces South (+vAxis)
    if (roofType === 'flat') {
      modTiltDeg = clamp(finite(state.tiltDeg, 15), 0, 60);
      const azRad = ((azimuthDeg - ridgeAzimuthDeg) * DEG2RAD) + ridgeRad;
      downSlopeXZ = [Math.sin(azRad), -Math.cos(azRad)];
    } else if (roofType === 'double_slope') {
      modTiltDeg = roofSlopeDeg;
      downSlopeXZ = slopeTag === 'north' ? [-vAxis[0], -vAxis[1]] : [vAxis[0], vAxis[1]];
    } else {
      modTiltDeg = roofSlopeDeg;
      downSlopeXZ = [vAxis[0], vAxis[1]];
    }

    const beta = modTiltDeg * DEG2RAD;
    const cosB = Math.cos(beta);
    const sinB = Math.sin(beta);

    // 3D right-handed orthonormal frame for module:
    // rightVec: horizontal along panel width, upSlopeVec: from lower front edge to higher rear edge, normalVec: outward cell face
    const dNorm = Math.hypot(downSlopeXZ[0], downSlopeXZ[1]) || 1;
    const dx0 = downSlopeXZ[0] / dNorm;
    const dx1 = downSlopeXZ[1] / dNorm;
    const rightVec = [dx1, 0, -dx0];
    const upSlopeVec = [-dx0 * cosB, sinB, -dx1 * cosB];
    const normalVec = [dx0 * sinB, cosB, dx1 * sinB];

    const baseRoofY = roofElevationAt(cx, cy);
    // Center Y lifts so the lower front edge stays `subArrayClearM` above the local roof plane
    const halfRise = roofType === 'flat' ? 0.5 * modH * sinB : 0;
    const modCenterY = baseRoofY + subArrayClearM + halfRise;
    const wx = cx - centerX;
    const wz = cy - centerY;
    const center3d = [wx, modCenterY, wz];

    // 4 true 3D corners: [NW/rear-left, NE/rear-right, SE/front-right, SW/front-left]
    const hw = modW * 0.5;
    const hh = modH * 0.5;
    const cornerSigns = [
      [-hw, +hh],
      [+hw, +hh],
      [+hw, -hh],
      [-hw, -hh],
    ];
    const corners3d = cornerSigns.map(([su, sv]) => [
      center3d[0] + rightVec[0] * su + upSlopeVec[0] * sv,
      center3d[1] + rightVec[1] * su + upSlopeVec[1] * sv,
      center3d[2] + rightVec[2] * su + upSlopeVec[2] * sv,
    ]);

    // Wind zone classification per GB 55001 / GB 50009
    const edgeDist = minDistToPolygonPerimeter(cx, cy, rawOutline);
    let minVertexDist = Infinity;
    for (const [vx, vy] of rawOutline) {
      const vd = Math.hypot(cx - vx, cy - vy);
      if (vd < minVertexDist) minVertexDist = vd;
    }
    const windZone = minVertexDist <= windEdgeBandM * 1.45
      ? 'corner'
      : edgeDist <= windEdgeBandM
        ? 'edge'
        : 'interior';

    const cxs = corners3d.map((p) => p[0]);
    const cys = corners3d.map((p) => p[1]);
    const czs = corners3d.map((p) => p[2]);
    const stInfo = stringByModId.get(m.id) || null;

    return {
      id: m.id || `M-${String(idx + 1).padStart(3, '0')}`,
      index: idx,
      row: m.row ?? 0,
      col: m.col ?? 0,
      slope: slopeTag,
      w: modW,
      h: hh * 2,
      tiltDeg: Number(modTiltDeg.toFixed(1)),
      azimuthDeg: slopeTag === 'north'
        ? Number((((ridgeAzimuthDeg + 360) % 360)).toFixed(1))
        : Number((((roofType === 'flat' ? azimuthDeg : ridgeAzimuthDeg + 180) % 360 + 360) % 360).toFixed(1)),
      center3d,
      baseRoofY,
      rightVec,
      upSlopeVec,
      normalVec,
      corners3d,
      windZone,
      stringId: stInfo?.id || m.stringId || null,
      stringColor: stInfo?.color || m.color || '#2563eb',
      inverterIndex: stInfo?.inverterIndex ?? m.inverterIndex ?? 0,
      mpptIndex: stInfo?.mpptIndex ?? m.mpptIndex ?? 0,
      aabb: {
        minX: Math.min(...cxs),
        maxX: Math.max(...cxs),
        minY: Math.min(...cys),
        maxY: Math.max(...cys),
        minZ: Math.min(...czs),
        maxZ: Math.max(...czs),
      },
    };
  });

  // Build 3D Parapet Wall Quads for raycasting & rendering
  const parapetQuads = [];
  if (parapetHeightM > 0.03) {
    for (let i = 0; i < rawOutline.length; i++) {
      const [ax, ay] = rawOutline[i];
      const [bx, by] = rawOutline[(i + 1) % rawOutline.length];
      if (Math.hypot(bx - ax, by - ay) < 0.05) continue;
      const za = roofElevationAt(ax, ay);
      const zb = roofElevationAt(bx, by);
      const p0 = toWorld(ax, ay, za);
      const p1 = toWorld(bx, by, zb);
      const p2 = toWorld(bx, by, zb + parapetHeightM);
      const p3 = toWorld(ax, ay, za + parapetHeightM);
      parapetQuads.push({
        kind: 'parapet',
        corners: [p0, p1, p2, p3],
        aabb: {
          minX: Math.min(p0[0], p1[0]),
          maxX: Math.max(p0[0], p1[0]),
          minY: Math.min(za, zb),
          maxY: Math.max(za, zb) + parapetHeightM,
          minZ: Math.min(p0[2], p1[2]),
          maxZ: Math.max(p0[2], p1[2]),
        },
      });
    }
  }

  // Build 3D Rooftop Obstacles
  const rawObstacles = Array.isArray(state.obstacles) ? state.obstacles : [];
  const obstacles3d = rawObstacles
    .filter((o) => Array.isArray(o?.polygon) && o.polygon.length >= 3)
    .map((obs, idx) => {
      const poly = obs.polygon;
      const oxs = poly.map((p) => finite(p[0]));
      const oys = poly.map((p) => finite(p[1]));
      const ocx = (Math.min(...oxs) + Math.max(...oxs)) * 0.5;
      const ocy = (Math.min(...oys) + Math.max(...oys)) * 0.5;
      const baseY = roofElevationAt(ocx, ocy);
      const heightM = inferObstacleHeightM(obs, obstacleHeightScale);
      const style = inferObstacleStyle(obs);
      const worldPoly2D = poly.map(([px, py]) => [px - centerX, py - centerY]);
      const sideQuads = [];
      const minBaseY = Math.min(...poly.map(([px, py]) => roofElevationAt(px, py))) - 0.15;
      const topY = baseY + heightM;

      for (let i = 0; i < poly.length; i++) {
        const [ax, ay] = poly[i];
        const [bx, by] = poly[(i + 1) % poly.length];
        if (Math.hypot(bx - ax, by - ay) < 0.05) continue;
        const p0 = toWorld(ax, ay, minBaseY);
        const p1 = toWorld(bx, by, minBaseY);
        const p2 = toWorld(bx, by, topY);
        const p3 = toWorld(ax, ay, topY);
        sideQuads.push({
          kind: 'obstacle',
          corners: [p0, p1, p2, p3],
          aabb: {
            minX: Math.min(p0[0], p1[0]),
            maxX: Math.max(p0[0], p1[0]),
            minY: minBaseY,
            maxY: topY,
            minZ: Math.min(p0[2], p1[2]),
            maxZ: Math.max(p0[2], p1[2]),
          },
        });
      }

      return {
        id: obs.id || `obs-${idx + 1}`,
        name: obs.name || `障碍物 #${idx + 1}`,
        style,
        heightM,
        baseY,
        topY,
        center3d: [ocx - centerX, baseY + heightM * 0.5, ocy - centerY],
        worldPoly2D,
        sideQuads,
        aabb: {
          minX: Math.min(...oxs) - centerX,
          maxX: Math.max(...oxs) - centerX,
          minY: minBaseY,
          maxY: topY,
          minZ: Math.min(...oys) - centerY,
          maxZ: Math.max(...oys) - centerY,
        },
      };
    });

  // Build 3D Inverters & DC Cable Tray Routes
  const inverters3d = (Array.isArray(state.inverterPointsM) ? state.inverterPointsM : []).map((inv, idx) => {
    const ix = finite(inv.x, 0);
    const iy = finite(inv.y, 0);
    const baseY = roofElevationAt(ix, iy);
    return {
      index: inv.index ?? idx,
      label: inv.label || `NB#${idx + 1}`,
      position3d: [ix - centerX, baseY + 0.65, iy - centerY],
      baseY,
    };
  });

  const cableTrays3d = rawStrings
    .filter((st) => Array.isArray(st.homeRunPathM) && st.homeRunPathM.length >= 2)
    .map((st) => ({
      id: st.id,
      color: st.color || '#f59e0b',
      points3d: st.homeRunPathM.map(([px, py]) => [px - centerX, roofElevationAt(px, py) + 0.08, py - centerY]),
    }));

  return {
    centerX,
    centerY,
    widthM,
    depthM,
    spanM,
    buildingHeightM,
    ridgePeakY,
    roofType,
    roofSlopeDeg,
    tiltDeg,
    azimuthDeg,
    ridgeAzimuthDeg,
    uAxis,
    vAxis,
    uMin,
    uMax,
    vMin,
    vMax,
    midV,
    halfSpanV,
    parapetHeightM,
    parapetWidthM,
    windEdgeBandM,
    outlineWorld2D,
    rawOutline,
    roofElevationAt,
    toWorld,
    modules3d,
    parapetQuads,
    obstacles3d,
    inverters3d,
    cableTrays3d,
    bessPowerKw: Math.max(0, finite(state.bessPowerKw, 0)),
    bessCapacityKwh: Math.max(0, finite(state.bessCapacityKwh, 0)),
    moduleStcW: clamp(finite(state.moduleStcW, 580), 250, 850),
  };
}

/**
 * Fast Möller–Trumbore ray-triangle intersection for a 3D quad [p0, p1, p2, p3].
 */
function rayHitsTriangle(ox, oy, oz, dx, dy, dz, a, b, c, maxDist = 250) {
  const e1x = b[0] - a[0], e1y = b[1] - a[1], e1z = b[2] - a[2];
  const e2x = c[0] - a[0], e2y = c[1] - a[1], e2z = c[2] - a[2];
  const hx = dy * e2z - dz * e2y;
  const hy = dz * e2x - dx * e2z;
  const hz = dx * e2y - dy * e2x;
  const det = e1x * hx + e1y * hy + e1z * hz;
  if (det > -1e-7 && det < 1e-7) return false;
  const invDet = 1.0 / det;
  const sx = ox - a[0], sy = oy - a[1], sz = oz - a[2];
  const u = invDet * (sx * hx + sy * hy + sz * hz);
  if (u < 0 || u > 1) return false;
  const qx = sy * e1z - sz * e1y;
  const qy = sz * e1x - sx * e1z;
  const qz = sx * e1y - sy * e1x;
  const v = invDet * (dx * qx + dy * qy + dz * qz);
  if (v < 0 || u + v > 1) return false;
  const t = invDet * (e2x * qx + e2y * qy + e2z * qz);
  return t > 0.035 && t < maxDist;
}

function rayHitsAabb(ox, oy, oz, invDx, invDy, invDz, box) {
  const tx1 = (box.minX - ox) * invDx;
  const tx2 = (box.maxX - ox) * invDx;
  let tmin = Math.min(tx1, tx2);
  let tmax = Math.max(tx1, tx2);

  const ty1 = (box.minY - oy) * invDy;
  const ty2 = (box.maxY - oy) * invDy;
  tmin = Math.max(tmin, Math.min(ty1, ty2));
  tmax = Math.min(tmax, Math.max(ty1, ty2));

  const tz1 = (box.minZ - oz) * invDz;
  const tz2 = (box.maxZ - oz) * invDz;
  tmin = Math.max(tmin, Math.min(tz1, tz2));
  tmax = Math.min(tmax, Math.max(tz1, tz2));

  return tmax >= Math.max(0.03, tmin);
}

function rayHitsQuad(ox, oy, oz, dx, dy, dz, corners) {
  return (
    rayHitsTriangle(ox, oy, oz, dx, dy, dz, corners[0], corners[1], corners[2]) ||
    rayHitsTriangle(ox, oy, oz, dx, dy, dz, corners[0], corners[2], corners[3])
  );
}

/**
 * Deterministic 3D Ray-Tracing Sub-Cell & 3-Bypass-Diode Shading Solver.
 * Subdivides each PV module into 3 bypass-diode substrings × 4 sample cells = 12 3D sample points,
 * casting solar rays against 3D parapet walls, rooftop obstacles, gable roof ridge, and adjacent PV rows.
 */
export function compute3DPhysicalShading(specOrState, {
  lat = 32.48,
  lon = 119.92,
  dateStr = '2026-12-21',
  hourBjt = 9.5,
  albedo = 0.22,
} = {}) {
  const spec = specOrState?.modules3d ? specOrState : buildSatmap3DGeometrySpec(specOrState);
  const solar = computeSolarVectorBjt(lat, lon, dateStr, hourBjt);
  const mods = spec.modules3d;
  const nMods = mods.length;

  if (nMods === 0 || solar.altitudeDeg <= 0.5) {
    return {
      solar,
      solarAltDeg: solar.altitudeDeg,
      solarAzDeg: solar.azimuthDeg,
      sunUp: solar.altitudeDeg > 0.5,
      moduleCount: nMods,
      shadedModuleCount: 0,
      diodeActivatedCount: 0,
      linearBeamShadePct: 0,
      electricalShadeLossPct: 0,
      avgPoaWm2: 0,
      unshadedPoaWm2: 0,
      instantDcPowerKw: 0,
      modules: mods.map((m) => ({
        id: m.id,
        linearShadeFrac: 0,
        elecLossFrac: 0,
        bypassedDiodes: 0,
        poaWm2: 0,
      })),
    };
  }

  const [dx, dy, dz] = solar.direction;
  const invDx = Math.abs(dx) > 1e-8 ? 1 / dx : 1e8;
  const invDy = Math.abs(dy) > 1e-8 ? 1 / dy : 1e8;
  const invDz = Math.abs(dz) > 1e-8 ? 1 / dz : 1e8;

  // Collect all static occluder quads (parapets + obstacle walls)
  const staticQuads = [...spec.parapetQuads];
  for (const obs of spec.obstacles3d) {
    for (const q of obs.sideQuads) staticQuads.push(q);
  }

  // Pre-filter candidate neighbor modules that can cast inter-row shadows (only higher top edge & within 12m)
  const hasTiltedInterRow = spec.roofType === 'flat' && spec.tiltDeg >= 3;
  const SUB_U = [-0.33, 0, 0.33]; // 3 bypass-diode substrings across module width/columns
  const SUB_V = [-0.375, -0.125, 0.125, 0.375]; // 4 vertical cell samples along slope

  let sumUnshadedBeam = 0;
  let sumLinearShadedBeam = 0;
  let sumUnshadedPoa = 0;
  let sumActualElecPoa = 0;
  let shadedModuleCount = 0;
  let diodeActivatedCount = 0;

  const moduleResults = new Array(nMods);

  for (let i = 0; i < nMods; i++) {
    const m = mods[i];
    const [nx, ny, nz] = m.normalVec;
    const cosTheta = Math.max(0, nx * dx + ny * dy + nz * dz);
    const skyDiffuse = solar.dhiWm2 * 0.5 * (1 + ny);
    const groundRefl = solar.ghiWm2 * albedo * 0.5 * (1 - ny);
    const diffusePlusRefl = skyDiffuse + groundRefl;
    const unshadedBeam = solar.dniWm2 * cosTheta;
    const unshadedPoa = unshadedBeam + diffusePlusRefl;

    if (cosTheta <= 0.008 || unshadedBeam <= 1.0) {
      sumUnshadedPoa += unshadedPoa;
      sumActualElecPoa += diffusePlusRefl;
      moduleResults[i] = {
        id: m.id,
        linearShadeFrac: cosTheta <= 0.008 ? 1 : 0,
        elecLossFrac: 0,
        bypassedDiodes: 0,
        poaWm2: Number(diffusePlusRefl.toFixed(1)),
      };
      continue;
    }

    // Candidate neighbor modules for inter-row shading
    const neighborCandidates = [];
    if (hasTiltedInterRow) {
      const mcx = m.center3d[0];
      const mcy = m.aabb.minY;
      const mcz = m.center3d[2];
      for (let j = 0; j < nMods; j++) {
        if (j === i || mods[j].row === m.row) continue;
        const mj = mods[j];
        if (mj.aabb.maxY <= mcy + 0.02) continue;
        const ddx = mj.center3d[0] - mcx;
        const ddz = mj.center3d[2] - mcz;
        if (ddx * ddx + ddz * ddz > 110) continue; // >10.5m away cannot shade standard roof tilt
        if (ddx * dx + ddz * dz <= 0) continue; // Behind the solar ray
        neighborCandidates.push(mj);
      }
    }

    let totalHits = 0;
    let bypassedDiodes = 0;
    const hw = m.w;
    const hh = m.h;
    const [cx, cy, cz] = m.center3d;
    const [rx, ry, rz] = m.rightVec;
    const [ux, uy, uz] = m.upSlopeVec;

    for (let sIdx = 0; sIdx < 3; sIdx++) {
      const su = SUB_U[sIdx] * hw;
      let subHits = 0;
      for (let vIdx = 0; vIdx < 4; vIdx++) {
        const sv = SUB_V[vIdx] * hh;
        const ox = cx + rx * su + ux * sv + nx * 0.03;
        const oy = cy + ry * su + uy * sv + ny * 0.03;
        const oz = cz + rz * su + uz * sv + nz * 0.03;

        let blocked = false;
        // 1. Check static 3D parapet walls & rooftop obstacles
        for (let qIdx = 0; qIdx < staticQuads.length; qIdx++) {
          const q = staticQuads[qIdx];
          if (q.aabb.maxY <= oy) continue;
          if (!rayHitsAabb(ox, oy, oz, invDx, invDy, invDz, q.aabb)) continue;
          if (rayHitsQuad(ox, oy, oz, dx, dy, dz, q.corners)) {
            blocked = true;
            break;
          }
        }

        // 2. Check double-slope ridge self-obstruction if on opposite slope at very low sun
        if (!blocked && spec.roofType === 'double_slope' && spec.roofSlopeDeg >= 4) {
          // Ray point at central ridge plane
          const ridgeDist = (spec.midV - ((ox * spec.vAxis[0]) + (oz * spec.vAxis[1]))) /
            (dx * spec.vAxis[0] + dz * spec.vAxis[1] || 1e-8);
          if (ridgeDist > 0.2 && ridgeDist < spec.spanM) {
            const rayYAtRidge = oy + dy * ridgeDist;
            if (rayYAtRidge < spec.ridgePeakY - 0.02) {
              blocked = true;
            }
          }
        }

        // 3. Check front-row PV modules (inter-row shading)
        if (!blocked && neighborCandidates.length > 0) {
          for (let k = 0; k < neighborCandidates.length; k++) {
            const mj = neighborCandidates[k];
            if (!rayHitsAabb(ox, oy, oz, invDx, invDy, invDz, mj.aabb)) continue;
            if (rayHitsQuad(ox, oy, oz, dx, dy, dz, mj.corners3d)) {
              blocked = true;
              break;
            }
          }
        }

        if (blocked) subHits++;
      }
      totalHits += subHits;
      if (subHits >= 1) bypassedDiodes++;
    }

    const linearShadeFrac = totalHits / 12;
    // Non-linear 3-bypass-diode MPP retention factor on beam irradiance
    const beamElecRemain = bypassedDiodes === 0
      ? 1.0
      : bypassedDiodes === 1
        ? Math.min(1 - linearShadeFrac, 0.63)
        : bypassedDiodes === 2
          ? Math.min(1 - linearShadeFrac, 0.29)
          : 0.0;

    const poaElec = unshadedBeam * beamElecRemain + diffusePlusRefl;
    const elecLossFrac = unshadedPoa > 1 ? clamp((unshadedPoa - poaElec) / unshadedPoa, 0, 1) : 0;

    if (linearShadeFrac > 0.001) shadedModuleCount++;
    if (bypassedDiodes > 0) diodeActivatedCount++;

    sumUnshadedBeam += unshadedBeam;
    sumLinearShadedBeam += unshadedBeam * linearShadeFrac;
    sumUnshadedPoa += unshadedPoa;
    sumActualElecPoa += poaElec;

    moduleResults[i] = {
      id: m.id,
      linearShadeFrac: Number(linearShadeFrac.toFixed(3)),
      elecLossFrac: Number(elecLossFrac.toFixed(3)),
      bypassedDiodes,
      poaWm2: Number(poaElec.toFixed(1)),
    };
  }

  const linearBeamShadePct = sumUnshadedBeam > 1
    ? (sumLinearShadedBeam / sumUnshadedBeam) * 100
    : 0;
  const electricalShadeLossPct = sumUnshadedPoa > 1
    ? ((sumUnshadedPoa - sumActualElecPoa) / sumUnshadedPoa) * 100
    : 0;
  const avgPoaWm2 = sumActualElecPoa / nMods;
  const unshadedPoaWm2 = sumUnshadedPoa / nMods;
  const totalDcKw = (nMods * spec.moduleStcW) / 1000;
  const instantDcPowerKw = totalDcKw * (avgPoaWm2 / 1000) * 0.88;

  return {
    solar,
    solarAltDeg: solar.altitudeDeg,
    solarAzDeg: solar.azimuthDeg,
    sunUp: true,
    moduleCount: nMods,
    shadedModuleCount,
    diodeActivatedCount,
    linearBeamShadePct: Number(linearBeamShadePct.toFixed(2)),
    electricalShadeLossPct: Number(electricalShadeLossPct.toFixed(2)),
    avgPoaWm2: Number(avgPoaWm2.toFixed(1)),
    unshadedPoaWm2: Number(unshadedPoaWm2.toFixed(1)),
    instantDcPowerKw: Number(instantDcPowerKw.toFixed(2)),
    modules: moduleResults,
  };
}

/**
 * Integrate 3D raycasted shading across representative seasonal trajectories
 * (Winter Solstice Dec 21, Equinox Mar 21, Summer Solstice Jun 21) to yield
 * bankable annual optical & bypass-diode electrical shading losses.
 */
export function computeAnnual3DShadingSummary(specOrState, { lat = 32.48, lon = 119.92 } = {}) {
  const spec = specOrState?.modules3d ? specOrState : buildSatmap3DGeometrySpec(specOrState);
  const nMods = spec.modules3d.length;
  if (nMods === 0) {
    return {
      annualLinearLossPct: 0,
      annualElectricalLossPct: 0,
      winter9to15PassPct: 100,
      moduleAnnualLossPct: [],
    };
  }

  const seasons = [
    { date: '2026-12-21', weight: 0.25 },
    { date: '2026-03-21', weight: 0.50 },
    { date: '2026-06-21', weight: 0.25 },
  ];
  const hours = [8.0, 9.5, 11.0, 13.0, 14.5, 16.0];

  let weightedUnshaded = 0;
  let weightedLinearLost = 0;
  let weightedElecLost = 0;
  const modWeightedUnshaded = new Float64Array(nMods);
  const modWeightedLost = new Float64Array(nMods);

  let winterChecks = 0;
  let winterPass = 0;

  for (const s of seasons) {
    for (const hr of hours) {
      const snap = compute3DPhysicalShading(spec, { lat, lon, dateStr: s.date, hourBjt: hr });
      if (!snap.sunUp || snap.unshadedPoaWm2 <= 5) continue;
      const w = s.weight * snap.unshadedPoaWm2;
      weightedUnshaded += w;
      weightedLinearLost += w * (snap.linearBeamShadePct / 100) * 0.72;
      weightedElecLost += w * (snap.electricalShadeLossPct / 100);

      for (let i = 0; i < nMods; i++) {
        modWeightedUnshaded[i] += s.weight * snap.unshadedPoaWm2;
        modWeightedLost[i] += s.weight * snap.unshadedPoaWm2 * snap.modules[i].elecLossFrac;
      }

      if (s.date === '2026-12-21' && hr >= 9.0 && hr <= 15.0) {
        winterChecks += nMods;
        winterPass += nMods - snap.diodeActivatedCount;
      }
    }
  }

  const annualLinearLossPct = weightedUnshaded > 1
    ? clamp((weightedLinearLost / weightedUnshaded) * 100, 0, 45)
    : 0;
  const annualElectricalLossPct = weightedUnshaded > 1
    ? clamp((weightedElecLost / weightedUnshaded) * 100, 0, 55)
    : 0;
  const winter9to15PassPct = winterChecks > 0
    ? (winterPass / winterChecks) * 100
    : 100;

  const moduleAnnualLossPct = Array.from({ length: nMods }, (_, i) =>
    modWeightedUnshaded[i] > 1
      ? Number(((modWeightedLost[i] / modWeightedUnshaded[i]) * 100).toFixed(2))
      : 0
  );

  return {
    annualLinearLossPct: Number(annualLinearLossPct.toFixed(2)),
    annualElectricalLossPct: Number(annualElectricalLossPct.toFixed(2)),
    winter9to15PassPct: Number(winter9to15PassPct.toFixed(1)),
    moduleAnnualLossPct,
  };
}

/* ============================================================================
 * Procedural High-DPI PBR Canvas Textures (Cached per THREE instance)
 * ========================================================================== */

export function createSolarPanelTintTexture(T) {
  if (!T || typeof T.CanvasTexture !== 'function' || typeof document === 'undefined') return null;
  const c = document.createElement('canvas');
  if (!c) return null;
  c.width = 256;
  c.height = 512;
  const ctx = typeof c.getContext === 'function' ? c.getContext('2d') : null;
  if (!ctx || typeof ctx.fillRect !== 'function') return null;

  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, 256, 512);
  ctx.strokeStyle = '#e2e8f0';
  ctx.lineWidth = 12;
  ctx.strokeRect(6, 6, 244, 500);
  ctx.fillStyle = '#dbe4f0';
  ctx.fillRect(12, 12, 232, 488);
  const cols = 6, rows = 20;
  const cw = 232 / cols, ch = 488 / rows;
  ctx.strokeStyle = 'rgba(255,255,255,0.58)';
  for (let i = 0; i <= cols; i++) {
    ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(12 + i * cw, 12); ctx.lineTo(12 + i * cw, 500); ctx.stroke();
  }
  for (let j = 0; j <= rows; j++) {
    ctx.lineWidth = j === 10 ? 2.8 : 1.15;
    ctx.beginPath(); ctx.moveTo(12, 12 + j * ch); ctx.lineTo(244, 12 + j * ch); ctx.stroke();
  }
  const tex = new T.CanvasTexture(c);
  tex.anisotropy = 4;
  tex.needsUpdate = true;
  return tex;
}

const textureCacheByThree = new WeakMap();

export function getProceduralPvTextures(T) {
  if (!T || typeof T.CanvasTexture !== 'function' || typeof document === 'undefined') return null;
  if (textureCacheByThree.has(T)) return textureCacheByThree.get(T);

  const makeCanvas = (w, h) => {
    const c = document.createElement('canvas');
    if (!c) return null;
    c.width = w;
    c.height = h;
    const ctx = typeof c.getContext === 'function' ? c.getContext('2d') : null;
    if (!ctx || typeof ctx.fillRect !== 'function') return null;
    return { c, ctx };
  };

  // 1. High-DPI N-Type TOPCon Bifacial Half-Cut Solar Panel Texture (512 x 1024)
  let solarPanelMap = null;
  const sp = makeCanvas(512, 1024);
  if (sp) {
    const { c, ctx } = sp;
    // Anodized silver-aluminum outer frame
    ctx.fillStyle = '#cbd5e1';
    ctx.fillRect(0, 0, 512, 1024);
    ctx.fillStyle = '#94a3b8';
    ctx.fillRect(10, 10, 492, 1004);
    // Deep anti-reflective monocrystalline silicon glass field
    const grad = typeof ctx.createLinearGradient === 'function'
      ? ctx.createLinearGradient(0, 0, 512, 1024)
      : null;
    if (grad) {
      grad.addColorStop(0, '#0c2242');
      grad.addColorStop(0.48, '#15396d');
      grad.addColorStop(0.52, '#102c54');
      grad.addColorStop(1, '#091a34');
      ctx.fillStyle = grad;
    } else {
      ctx.fillStyle = '#123260';
    }
    ctx.fillRect(18, 18, 476, 988);

    // 6 columns x 22 rows half-cut cells + central split ribbon
    const cols = 6;
    const rows = 22;
    const padX = 22;
    const padY = 22;
    const innerW = 512 - padX * 2;
    const innerH = 1024 - padY * 2;
    const cellW = innerW / cols;
    const cellH = innerH / rows;

    // Subtle cell gap matrix
    ctx.strokeStyle = 'rgba(186, 214, 247, 0.34)';
    ctx.lineWidth = 2.0;
    for (let i = 0; i <= cols; i++) {
      const x = padX + i * cellW;
      ctx.beginPath();
      ctx.moveTo(x, padY);
      ctx.lineTo(x, 1024 - padY);
      ctx.stroke();
    }
    for (let j = 0; j <= rows; j++) {
      const y = padY + j * cellH;
      ctx.strokeStyle = j === rows / 2 ? 'rgba(226, 232, 240, 0.72)' : 'rgba(186, 214, 247, 0.28)';
      ctx.lineWidth = j === rows / 2 ? 4.2 : 1.6;
      ctx.beginPath();
      ctx.moveTo(padX, y);
      ctx.lineTo(512 - padX, y);
      ctx.stroke();
    }

    // MBB silver micro-busbars + monocrystalline wafer corner chamfers
    ctx.strokeStyle = 'rgba(226, 238, 255, 0.20)';
    ctx.lineWidth = 1.0;
    for (let i = 0; i < cols; i++) {
      const cx0 = padX + i * cellW;
      for (let b = 1; b <= 5; b++) {
        const bx = cx0 + (b / 6) * cellW;
        ctx.beginPath();
        ctx.moveTo(bx, padY);
        ctx.lineTo(bx, 1024 - padY);
        ctx.stroke();
      }
    }
    ctx.fillStyle = 'rgba(226, 232, 240, 0.55)';
    for (let i = 1; i < cols; i++) {
      for (let j = 1; j < rows; j++) {
        if (j === rows / 2) continue;
        const ix = padX + i * cellW;
        const iy = padY + j * cellH;
        ctx.fillRect(ix - 2.2, iy - 2.2, 4.4, 4.4);
      }
    }

    solarPanelMap = new T.CanvasTexture(c);
    if ('colorSpace' in solarPanelMap && T.SRGBColorSpace) {
      solarPanelMap.colorSpace = T.SRGBColorSpace;
    }
    solarPanelMap.anisotropy = 8;
    solarPanelMap.needsUpdate = true;
  }

  // 2. White-base Solar Cell Texture (for tinting with InstancedMesh instanceColor in light/heat modes!)
  let solarPanelTintableMap = null;
  const spt = makeCanvas(256, 512);
  if (spt) {
    const { c, ctx } = spt;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, 256, 512);
    // Bright metallic border
    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 12;
    ctx.strokeRect(6, 6, 244, 500);
    // Subtle cell grid in neutral grey so multiplying by #1f3a66 or heatColor keeps crisp cell detail!
    ctx.fillStyle = '#dbe4f0';
    ctx.fillRect(12, 12, 232, 488);
    const cols = 6, rows = 20;
    const cw = 232 / cols, ch = 488 / rows;
    ctx.strokeStyle = 'rgba(255,255,255,0.52)';
    ctx.lineWidth = 1.4;
    for (let i = 0; i <= cols; i++) {
      ctx.beginPath(); ctx.moveTo(12 + i * cw, 12); ctx.lineTo(12 + i * cw, 500); ctx.stroke();
    }
    for (let j = 0; j <= rows; j++) {
      ctx.lineWidth = j === 10 ? 2.6 : 1.1;
      ctx.beginPath(); ctx.moveTo(12, 12 + j * ch); ctx.lineTo(244, 12 + j * ch); ctx.stroke();
    }
    solarPanelTintableMap = new T.CanvasTexture(c);
    solarPanelTintableMap.anisotropy = 4;
    solarPanelTintableMap.needsUpdate = true;
  }

  // 3. Standing-Seam Corrugated Metal Roof Texture (512 x 512, Repeating)
  let metalRoofMap = null;
  const mr = makeCanvas(512, 512);
  if (mr) {
    const { c, ctx } = mr;
    ctx.fillStyle = '#cfd8e3';
    ctx.fillRect(0, 0, 512, 512);
    for (let x = 0; x < 512; x += 32) {
      ctx.fillStyle = '#dce4ee';
      ctx.fillRect(x, 0, 14, 512);
      ctx.fillStyle = '#b4c0cf';
      ctx.fillRect(x + 14, 0, 5, 512);
      ctx.fillStyle = '#8e9db0';
      ctx.fillRect(x + 19, 0, 3, 512);
    }
    ctx.strokeStyle = 'rgba(100,116,139,0.22)';
    ctx.lineWidth = 2;
    for (let y = 0; y < 512; y += 128) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(512, y); ctx.stroke();
    }
    metalRoofMap = new T.CanvasTexture(c);
    if (T.RepeatWrapping) {
      metalRoofMap.wrapS = T.RepeatWrapping;
      metalRoofMap.wrapT = T.RepeatWrapping;
    }
    metalRoofMap.repeat.set(8, 8);
    metalRoofMap.needsUpdate = true;
  }

  // 4. Concrete SBS Waterproof Membrane Roof Texture (512 x 512, Repeating)
  let concreteRoofMap = null;
  const cr = makeCanvas(512, 512);
  if (cr) {
    const { c, ctx } = cr;
    ctx.fillStyle = '#c8c4bc';
    ctx.fillRect(0, 0, 512, 512);
    for (let i = 0; i < 420; i++) {
      const gx = (i * 73) % 512;
      const gy = (i * 137) % 512;
      ctx.fillStyle = i % 2 === 0 ? 'rgba(255,255,255,0.08)' : 'rgba(71,85,105,0.08)';
      ctx.fillRect(gx, gy, 8, 8);
    }
    ctx.strokeStyle = 'rgba(100, 96, 88, 0.34)';
    ctx.lineWidth = 2;
    for (let x = 0; x <= 512; x += 128) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 512); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, x); ctx.lineTo(512, x); ctx.stroke();
    }
    concreteRoofMap = new T.CanvasTexture(c);
    if (T.RepeatWrapping) {
      concreteRoofMap.wrapS = T.RepeatWrapping;
      concreteRoofMap.wrapT = T.RepeatWrapping;
    }
    concreteRoofMap.repeat.set(6, 6);
    concreteRoofMap.needsUpdate = true;
  }

  const bundle = { solarPanelMap, solarPanelTintableMap, metalRoofMap, concreteRoofMap };
  textureCacheByThree.set(T, bundle);
  return bundle;
}

function heatIrradianceHex(poaWm2, maxPoa = 950) {
  const t = clamp(poaWm2 / Math.max(200, maxPoa), 0, 1);
  // Deep indigo (shaded) -> cyan -> emerald -> warm gold -> solar orange-red (high POA)
  const stops = [
    [30, 58, 138],
    [14, 165, 233],
    [16, 185, 129],
    [245, 158, 11],
    [239, 68, 68],
  ];
  const scaled = t * (stops.length - 1);
  const idx = Math.min(stops.length - 2, Math.floor(scaled));
  const f = scaled - idx;
  const rgb = stops[idx].map((v, k) => Math.round(v + (stops[idx + 1][k] - v) * f));
  return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2];
}

/**
 * Mount an interactive WebGL Three.js Engineering 3D Digital Twin inside `container`.
 */
export function mountSatmap3DTwin(container, initialState = {}, callbacks = {}) {
  const T = globalThis.THREE;
  if (!container) return null;
  container.replaceChildren();

  const canvas = document.createElement('canvas');
  canvas.className = 'satmap-3d-webgl-canvas';
  canvas.style.cssText = 'width:100%;height:100%;display:block;outline:none;cursor:grab';
  const renderFallback = () => {
    container.replaceChildren();
    const fallback = document.createElement('div');
    fallback.style.cssText = 'padding:28px;color:#e2e8f0;background:#0f172a;height:100%;display:flex;align-items:center;justify-content:center;font-size:13px';
    fallback.textContent = '当前运行环境未启用硬件三维渲染上下文，三维物理阴影核算引擎仍可在后台正常计算。';
    container.append(fallback);
    return {
      available: false,
      updateState() {},
      setSimConfig() {},
      setCameraPreset() {},
      capturePng: () => null,
      getShadingSnapshot: () => compute3DPhysicalShading(initialState, initialState),
      dispose() { container.replaceChildren(); },
    };
  };

  if (!T?.WebGLRenderer || !T?.OrbitControls) {
    return renderFallback();
  }

  let renderer = null;
  try {
    const glOpts = { antialias: true, preserveDrawingBuffer: true };
    const gl = typeof canvas.getContext === 'function'
      ? (canvas.getContext('webgl2', glOpts) || canvas.getContext('webgl', glOpts))
      : null;
    if (!gl) return renderFallback();
    renderer = new T.WebGLRenderer({
      canvas,
      context: gl,
      antialias: true,
      preserveDrawingBuffer: true,
    });
  } catch {
    return renderFallback();
  }

  // Hover / Inspector Floating Tooltip inside 3D viewport
  const tooltip = document.createElement('div');
  tooltip.className = 'satmap-3d-tooltip';
  tooltip.hidden = true;
  tooltip.style.cssText = [
    'position:absolute', 'left:14px', 'bottom:44px', 'z-index:16', 'pointer-events:none',
    'background:rgba(15,23,42,0.92)', 'color:#f8fafc', 'border:1px solid rgba(56,189,248,0.45)',
    'border-radius:8px', 'padding:8px 12px', 'font-size:11.5px', 'line-height:1.5',
    'box-shadow:0 8px 24px rgba(0,0,0,0.38)', 'max-width:340px', 'backdrop-filter:blur(6px)',
  ].join(';');

  container.style.position = 'relative';
  container.append(canvas, tooltip);
  renderer.setPixelRatio(Math.min(typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.autoUpdate = false;
  if (T.PCFSoftShadowMap) renderer.shadowMap.type = T.PCFSoftShadowMap;
  let needsShadow = true;
  let needsRender = true;
  if ('outputColorSpace' in renderer && T.SRGBColorSpace) {
    renderer.outputColorSpace = T.SRGBColorSpace;
  } else if ('outputEncoding' in renderer && T.sRGBEncoding) {
    renderer.outputEncoding = T.sRGBEncoding;
  }
  if (T.ACESFilmicToneMapping) {
    renderer.toneMapping = T.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
  }

  const scene = new T.Scene();
  scene.background = new T.Color(0xdbeafe);
  if (T.FogExp2) scene.fog = new T.FogExp2(0xdbeafe, 0.0014);

  const camera = new T.PerspectiveCamera(44, 1.6, 0.4, 2400);
  const controls = new T.OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.maxPolarAngle = Math.PI * 0.492;
  controls.screenSpacePanning = true;
  controls.addEventListener?.('change', () => { needsRender = true; });

  // Sky Hemisphere + Ambient + Sun Directional Shadow Light
  const hemiLight = new T.HemisphereLight(0xf0f9ff, 0x94a3b8, 0.82);
  const fillLight = new T.DirectionalLight(0xe0f2fe, 0.28);
  fillLight.position.set(-80, 90, -70);
  const sunLight = new T.DirectionalLight(0xfffbeb, 1.55);
  sunLight.castShadow = true;
  sunLight.shadow.mapSize.set(2048, 2048);
  sunLight.shadow.bias = -0.00035;
  sunLight.shadow.normalBias = 0.025;
  scene.add(hemiLight, fillLight, sunLight, sunLight.target);

  const textures = getProceduralPvTextures(T);
  const worldGroup = new T.Group();
  const dynamicSunGroup = new T.Group();
  scene.add(worldGroup, dynamicSunGroup);

  let currentSpec = null;
  let currentShading = null;
  let currentAnnual = null;
  let panelInstancedMesh = null;
  let sunOrbMesh = null;
  let sunRayLine = null;
  let stateRef = { ...initialState };
  let simCfg = {
    dateStr: initialState.simDateStr || '2026-12-21',
    hourBjt: finite(initialState.simHourBjt, 9.5),
    displayMode: initialState.simDisplayMode || 'realistic', // 'realistic' | 'irradiance' | 'diode' | 'wiring' | 'wind'
    showSunDome: initialState.showSunDome !== false,
    showRacking: initialState.showRacking !== false,
    playing: false,
  };

  function disposeGroup(grp) {
    for (const child of [...grp.children]) {
      grp.remove(child);
      child.traverse?.((obj) => {
        if (obj.geometry) obj.geometry.dispose();
        if (Array.isArray(obj.material)) {
          obj.material.forEach((mt) => mt?.dispose?.());
        } else if (obj.material) {
          // Do not dispose shared cached textures
          obj.material.dispose?.();
        }
      });
    }
  }

  function buildBuildingAndArrayGeometry() {
    disposeGroup(worldGroup);
    panelInstancedMesh = null;

    currentSpec = buildSatmap3DGeometrySpec(stateRef);
    const sp = currentSpec;
    const span = sp.spanM;

    // 1. Ground Campus Environment, Asphalt Apron & Subtle Engineering Grid
    const groundRadius = Math.max(160, span * 3.4);
    const groundMesh = new T.Mesh(
      new T.PlaneGeometry(groundRadius * 2, groundRadius * 2),
      new T.MeshStandardMaterial({ color: 0xd6dce5, roughness: 0.94, metalness: 0.02 })
    );
    groundMesh.rotation.x = -Math.PI / 2;
    groundMesh.position.y = -0.04;
    groundMesh.receiveShadow = true;
    worldGroup.add(groundMesh);

    // Asphalt Perimeter Apron around factory
    const apronW = sp.widthM + 22;
    const apronD = sp.depthM + 22;
    const apronMesh = new T.Mesh(
      new T.PlaneGeometry(apronW, apronD),
      new T.MeshStandardMaterial({ color: 0x475569, roughness: 0.88, metalness: 0.05 })
    );
    apronMesh.rotation.x = -Math.PI / 2;
    apronMesh.position.y = -0.01;
    apronMesh.receiveShadow = true;
    worldGroup.add(apronMesh);

    if (T.GridHelper) {
      const grid = new T.GridHelper(Math.round(span * 2.6), Math.max(12, Math.round(span / 4)), 0x94a3b8, 0xcbd5e1);
      grid.position.y = 0.01;
      worldGroup.add(grid);
    }

    // Cardinal Compass Rose & North Arrow
    const compassR = span * 0.68;
    const northArrow = new T.ArrowHelper(
      new T.Vector3(0, 0, -1),
      new T.Vector3(-span * 0.62, 0.25, span * 0.48),
      Math.max(5, span * 0.14),
      0xef4444,
      Math.max(1.5, span * 0.035),
      Math.max(1.0, span * 0.022)
    );
    worldGroup.add(northArrow);

    // 2. Industrial Building Body (Exact Extruded Concave/Convex Polygon + Architectural Facade Details)
    const shape = new T.Shape();
    sp.outlineWorld2D.forEach(([wx, wz], idx) => {
      // Shape in (X, -Z) so rotation.x = -PI/2 maps (sx, sy, sz) -> (wx, sz_up, wz)
      if (idx === 0) shape.moveTo(wx, -wz);
      else shape.lineTo(wx, -wz);
    });
    shape.closePath();

    // Base building volume up to eave height `buildingHeightM`
    const bldgGeom = new T.ExtrudeGeometry(shape, { depth: sp.buildingHeightM, bevelEnabled: false });
    const wallMat = new T.MeshStandardMaterial({ color: 0xe2e8f0, roughness: 0.76, metalness: 0.12 });
    const roofDeckMat = sp.roofType === 'flat'
      ? new T.MeshStandardMaterial({
          color: 0xcbd5e1,
          map: textures?.concreteRoofMap || null,
          roughness: 0.88,
          metalness: 0.05,
        })
      : new T.MeshStandardMaterial({
          color: 0xdbeafe,
          map: textures?.metalRoofMap || null,
          roughness: 0.52,
          metalness: 0.34,
        });

    const bldgMesh = new T.Mesh(bldgGeom, [roofDeckMat, wallMat]);
    bldgMesh.rotation.x = -Math.PI / 2;
    bldgMesh.castShadow = true;
    bldgMesh.receiveShadow = true;
    worldGroup.add(bldgMesh);

    // Concrete plinth & ribbon windows + rolling shutter doors along exterior building walls
    const plinthMat = new T.MeshStandardMaterial({ color: 0x64748b, roughness: 0.9 });
    const glassBandMat = new T.MeshStandardMaterial({ color: 0x1e3a5f, roughness: 0.18, metalness: 0.65 });
    const doorMat = new T.MeshStandardMaterial({ color: 0x334155, roughness: 0.55, metalness: 0.4 });
    for (let i = 0; i < sp.outlineWorld2D.length; i++) {
      const [ax, az] = sp.outlineWorld2D[i];
      const [bx, bz] = sp.outlineWorld2D[(i + 1) % sp.outlineWorld2D.length];
      const segLen = Math.hypot(bx - ax, bz - az);
      if (segLen < 4) continue;
      const midX = (ax + bx) * 0.5;
      const midZ = (az + bz) * 0.5;
      const yaw = -Math.atan2(bz - az, bx - ax);

      // Concrete base plinth
      const plinth = new T.Mesh(new T.BoxGeometry(segLen + 0.1, 1.1, 0.16), plinthMat);
      plinth.position.set(midX, 0.55, midZ);
      plinth.rotation.y = yaw;
      worldGroup.add(plinth);

      // Industrial ribbon windows
      if (sp.buildingHeightM >= 5.5 && segLen >= 10) {
        const winBand = new T.Mesh(new T.BoxGeometry(segLen * 0.84, 1.35, 0.14), glassBandMat);
        winBand.position.set(midX, sp.buildingHeightM * 0.66, midZ);
        winBand.rotation.y = yaw;
        worldGroup.add(winBand);
      }

      // Industrial rolling shutter door on longest South/East edges
      if (segLen >= 22 && sp.buildingHeightM >= 5.0 && i % 2 === 0) {
        const doorW = Math.min(4.8, segLen * 0.18);
        const doorH = Math.min(4.2, sp.buildingHeightM * 0.48);
        const door = new T.Mesh(new T.BoxGeometry(doorW, doorH, 0.22), doorMat);
        door.position.set(midX, doorH * 0.5, midZ);
        door.rotation.y = yaw;
        worldGroup.add(door);
      }
    }

    // 3. Sloped Roof Deck & Gable Wedge (when `double_slope` or `single_slope` has roofSlopeDeg > 0.2°)
    if (sp.roofType !== 'flat' && sp.roofSlopeDeg > 0.2) {
      const slopeRad = sp.roofSlopeDeg * DEG2RAD;
      const uLen = Math.max(4, sp.uMax - sp.uMin);
      const ridgeRad = sp.ridgeAzimuthDeg * DEG2RAD;
      const deckGroup = new T.Group();
      deckGroup.rotation.y = -ridgeRad;

      const deckThickOffset = 0.08 * Math.cos(slopeRad);
      if (sp.roofType === 'double_slope') {
        const slopeHyp = sp.halfSpanV / Math.max(0.5, Math.cos(slopeRad));
        const ridgeRise = sp.halfSpanV * Math.tan(slopeRad);
        // North & South sloped standing-seam metal decks (top surface aligned to roofElevationAt)
        for (const sign of [-1, 1]) {
          const deck = new T.Mesh(new T.BoxGeometry(uLen + 0.3, 0.16, slopeHyp + 0.2), roofDeckMat);
          deck.position.set(
            (sp.uMin + sp.uMax) * 0.5,
            sp.buildingHeightM + ridgeRise * 0.5 - deckThickOffset,
            sp.midV + sign * sp.halfSpanV * 0.5
          );
          deck.rotation.x = sign * slopeRad;
          deck.castShadow = true;
          deck.receiveShadow = true;
          deckGroup.add(deck);
        }
        // 3D Ridge Cap + Central Green FRP Inspection Walkway
        const ridgeCap = new T.Mesh(
          new T.BoxGeometry(uLen + 0.4, 0.14, 0.55),
          new T.MeshStandardMaterial({ color: 0x475569, roughness: 0.4, metalness: 0.55 })
        );
        ridgeCap.position.set((sp.uMin + sp.uMax) * 0.5, sp.buildingHeightM + ridgeRise + 0.05, sp.midV);
        deckGroup.add(ridgeCap);

        const walkwayMat = new T.MeshStandardMaterial({ color: 0x10b981, roughness: 0.65, metalness: 0.1 });
        for (const sign of [-1, 1]) {
          const walk = new T.Mesh(new T.BoxGeometry(uLen * 0.96, 0.05, 0.45), walkwayMat);
          walk.position.set((sp.uMin + sp.uMax) * 0.5, sp.buildingHeightM + ridgeRise - 0.04, sp.midV + sign * 0.55);
          deckGroup.add(walk);
        }

        // Gable triangular end walls at uMin and uMax
        const gableShape = new T.Shape();
        gableShape.moveTo(-sp.halfSpanV, 0);
        gableShape.lineTo(sp.halfSpanV, 0);
        gableShape.lineTo(0, ridgeRise);
        gableShape.closePath();
        const gableGeom = new T.ExtrudeGeometry(gableShape, { depth: 0.24, bevelEnabled: false });
        for (const uEnd of [sp.uMin, sp.uMax - 0.24]) {
          const gable = new T.Mesh(gableGeom, wallMat);
          gable.rotation.y = Math.PI / 2;
          gable.position.set(uEnd, sp.buildingHeightM, sp.midV);
          gable.castShadow = true;
          gable.receiveShadow = true;
          deckGroup.add(gable);
        }
      } else {
        // Single-slope South-facing metal roof deck + watertight North upper wall & East/West gable wedges
        const fullV = Math.max(2, sp.vMax - sp.vMin);
        const slopeHyp = fullV / Math.max(0.5, Math.cos(slopeRad));
        const totalRise = fullV * Math.tan(slopeRad);
        const uMid = (sp.uMin + sp.uMax) * 0.5;
        const deck = new T.Mesh(new T.BoxGeometry(uLen + 0.3, 0.16, slopeHyp + 0.2), roofDeckMat);
        deck.position.set(uMid, sp.buildingHeightM + totalRise * 0.5 - deckThickOffset, sp.midV);
        deck.rotation.x = slopeRad;
        deck.castShadow = true;
        deck.receiveShadow = true;
        deckGroup.add(deck);

        // North high fascia wall closing the single-slope wedge
        const northWall = new T.Mesh(new T.BoxGeometry(uLen, totalRise, 0.24), wallMat);
        northWall.position.set(uMid, sp.buildingHeightM + totalRise * 0.5, sp.vMin + 0.12);
        northWall.castShadow = true;
        northWall.receiveShadow = true;
        deckGroup.add(northWall);

        // North ridge flashing trim cap
        const northCap = new T.Mesh(
          new T.BoxGeometry(uLen + 0.4, 0.12, 0.42),
          new T.MeshStandardMaterial({ color: 0x475569, roughness: 0.4, metalness: 0.55 })
        );
        northCap.position.set(uMid, sp.buildingHeightM + totalRise + 0.04, sp.vMin + 0.08);
        deckGroup.add(northCap);

        // Right-triangle gable end walls at uMin and uMax (rotation.y = +PI/2 maps sx -> -z)
        const wedgeShape = new T.Shape();
        wedgeShape.moveTo(-sp.halfSpanV, 0);
        wedgeShape.lineTo(sp.halfSpanV, 0);
        wedgeShape.lineTo(sp.halfSpanV, totalRise);
        wedgeShape.closePath();
        const wedgeGeom = new T.ExtrudeGeometry(wedgeShape, { depth: 0.24, bevelEnabled: false });
        for (const uEnd of [sp.uMin, sp.uMax - 0.24]) {
          const wedge = new T.Mesh(wedgeGeom, wallMat);
          wedge.rotation.y = Math.PI / 2;
          wedge.position.set(uEnd, sp.buildingHeightM, sp.midV);
          wedge.castShadow = true;
          wedge.receiveShadow = true;
          deckGroup.add(wedge);
        }
      }
      worldGroup.add(deckGroup);
    }

    // 4. 3D Perimeter Parapet Walls + Concrete Coping Cap
    if (sp.parapetHeightM > 0.03) {
      const parapetMat = new T.MeshStandardMaterial({ color: 0xcbd5e1, roughness: 0.82 });
      const copingMat = new T.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.65 });
      for (let i = 0; i < sp.rawOutline.length; i++) {
        const [ax, ay] = sp.rawOutline[i];
        const [bx, by] = sp.rawOutline[(i + 1) % sp.rawOutline.length];
        const len = Math.hypot(bx - ax, by - ay);
        if (len < 0.1) continue;
        const wxA = ax - sp.centerX, wzA = ay - sp.centerY;
        const wxB = bx - sp.centerX, wzB = by - sp.centerY;
        const baseY = sp.roofElevationAt((ax + bx) * 0.5, (ay + by) * 0.5);
        const yaw = -Math.atan2(wzB - wzA, wxB - wxA);

        const wall = new T.Mesh(new T.BoxGeometry(len + sp.parapetWidthM, sp.parapetHeightM, sp.parapetWidthM), parapetMat);
        wall.position.set((wxA + wxB) * 0.5, baseY + sp.parapetHeightM * 0.5, (wzA + wzB) * 0.5);
        wall.rotation.y = yaw;
        wall.castShadow = true;
        wall.receiveShadow = true;
        worldGroup.add(wall);

        const coping = new T.Mesh(new T.BoxGeometry(len + sp.parapetWidthM + 0.06, 0.06, sp.parapetWidthM + 0.08), copingMat);
        coping.position.set((wxA + wxB) * 0.5, baseY + sp.parapetHeightM + 0.03, (wzA + wzB) * 0.5);
        coping.rotation.y = yaw;
        coping.castShadow = true;
        worldGroup.add(coping);
      }
    }

    // 5. Realistic 3D Rooftop Obstacles (Skylights, HVAC Chillers, Ventilation Stacks, Elevator Penthouses)
    for (const obs of sp.obstacles3d) {
      const oShape = new T.Shape();
      obs.worldPoly2D.forEach(([wx, wz], idx) => {
        if (idx === 0) oShape.moveTo(wx, -wz);
        else oShape.lineTo(wx, -wz);
      });
      oShape.closePath();

      const extrudeDepth = obs.topY - obs.aabb.minY;
      const oGeom = new T.ExtrudeGeometry(oShape, { depth: extrudeDepth, bevelEnabled: false });
      const oMat = obs.style === 'skylight'
        ? new T.MeshStandardMaterial({
            color: 0x7dd3fc,
            roughness: 0.18,
            metalness: 0.25,
            transparent: true,
            opacity: 0.78,
          })
        : obs.style === 'hvac'
          ? new T.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.42, metalness: 0.52 })
          : new T.MeshStandardMaterial({ color: 0xd1d5db, roughness: 0.78, metalness: 0.12 });

      const oMesh = new T.Mesh(oGeom, oMat);
      oMesh.rotation.x = -Math.PI / 2;
      oMesh.position.y = obs.aabb.minY;
      oMesh.castShadow = true;
      oMesh.receiveShadow = true;
      worldGroup.add(oMesh);

      // Extra mechanical detail on HVAC / Vent obstacles (axial fan shroud)
      if (obs.style === 'hvac' || obs.style === 'vent') {
        const fanRadius = Math.min(0.85, Math.max(0.32, (obs.aabb.maxX - obs.aabb.minX) * 0.18));
        const shroud = new T.Mesh(
          new T.CylinderGeometry(fanRadius, fanRadius * 1.05, 0.32, 20),
          new T.MeshStandardMaterial({ color: 0x334155, roughness: 0.45, metalness: 0.6 })
        );
        shroud.position.set(obs.center3d[0], obs.topY + 0.16, obs.center3d[2]);
        shroud.castShadow = true;
        worldGroup.add(shroud);
      }
    }

    // 6. High-Detail 3D PV Modules (InstancedMesh) + 3D Racking Rails, Tilt Triangles & Concrete Ballast Blocks
    if (sp.modules3d.length > 0) {
      const nMods = sp.modules3d.length;
      const boxGeom = new T.BoxGeometry(1, 1, 1);
      const useRealisticTex = simCfg.displayMode === 'realistic';
      const panelMat = new T.MeshStandardMaterial({
        color: 0xffffff,
        map: useRealisticTex
          ? (textures?.solarPanelMap || textures?.solarPanelTintableMap || null)
          : (textures?.solarPanelTintableMap || null),
        roughness: useRealisticTex ? 0.22 : 0.34,
        metalness: useRealisticTex ? 0.38 : 0.18,
      });

      panelInstancedMesh = new T.InstancedMesh(boxGeom, panelMat, nMods);
      panelInstancedMesh.castShadow = true;
      panelInstancedMesh.receiveShadow = true;

      const mat4 = new T.Matrix4();
      const rackPostGeom = new T.BoxGeometry(0.05, 1, 0.05);
      const ballastGeom = new T.BoxGeometry(0.38, 0.16, 0.26);
      const clampGeom = new T.BoxGeometry(0.08, 0.10, 0.08);
      const steelMat = new T.MeshStandardMaterial({ color: 0x94a3b8, roughness: 0.36, metalness: 0.72 });
      const ballastNormMat = new T.MeshStandardMaterial({ color: 0x78716c, roughness: 0.92, metalness: 0.04 });
      const ballastCornerMat = new T.MeshStandardMaterial({ color: 0xd97706, roughness: 0.85, metalness: 0.08 });

      // Instanced racking & ballast for ultra-smooth 60fps even at 800+ modules!
      const flatRackCount = sp.roofType === 'flat' && simCfg.showRacking ? nMods * 2 : 0;
      const metalClampCount = sp.roofType !== 'flat' && simCfg.showRacking ? nMods * 2 : 0;
      const postInst = flatRackCount > 0 ? new T.InstancedMesh(rackPostGeom, steelMat, flatRackCount) : null;
      const ballastInst = flatRackCount > 0 ? new T.InstancedMesh(ballastGeom, ballastNormMat, flatRackCount) : null;
      const clampInst = metalClampCount > 0 ? new T.InstancedMesh(clampGeom, steelMat, metalClampCount) : null;
      const dummy = new T.Object3D();

      for (let i = 0; i < nMods; i++) {
        const m = sp.modules3d[i];
        const [rx, ry, rz] = m.rightVec;
        const [nx, ny, nz] = m.normalVec;
        const [ux, uy, uz] = m.upSlopeVec;
        const [cx, cy, cz] = m.center3d;
        const sx = m.w;
        const sy = 0.04; // 40mm anodized aluminum frame thickness
        const sz = m.h;

        // Basis columns: X -> rightVec*w, Y -> normalVec*0.04, Z -> -upSlopeVec*h (so top +Y gets solarPanelMap!)
        mat4.set(
          rx * sx, nx * sy, -ux * sz, cx,
          ry * sx, ny * sy, -uy * sz, cy,
          rz * sx, nz * sy, -uz * sz, cz,
          0, 0, 0, 1
        );
        panelInstancedMesh.setMatrixAt(i, mat4);

        if (postInst && ballastInst) {
          // Rear high post & front low post + concrete ballast pier
          for (let leg = 0; leg < 2; leg++) {
            const sv = leg === 0 ? m.h * 0.34 : -m.h * 0.34;
            const lx = cx + ux * sv;
            const lyTop = cy + uy * sv - 0.02;
            const lz = cz + uz * sv;
            const legH = Math.max(0.08, lyTop - m.baseRoofY);

            dummy.position.set(lx, m.baseRoofY + legH * 0.5, lz);
            dummy.scale.set(1, legH, 1);
            dummy.rotation.set(0, 0, 0);
            dummy.updateMatrix();
            postInst.setMatrixAt(i * 2 + leg, dummy.matrix);

            // C30 Concrete Ballast Pier (heavier/wider in GB 55001 corner/edge wind zone!)
            const bScale = m.windZone === 'corner' ? 1.45 : m.windZone === 'edge' ? 1.2 : 1.0;
            dummy.position.set(lx, m.baseRoofY + 0.08 * bScale, lz);
            dummy.scale.set(bScale, bScale, bScale);
            dummy.rotation.set(0, -sp.ridgeAzimuthDeg * DEG2RAD, 0);
            dummy.updateMatrix();
            ballastInst.setMatrixAt(i * 2 + leg, dummy.matrix);
            ballastInst.setColorAt(
              i * 2 + leg,
              new T.Color(m.windZone === 'corner' ? 0xef4444 : m.windZone === 'edge' ? 0xf59e0b : 0x78716c)
            );
          }
        } else if (clampInst) {
          for (let leg = 0; leg < 2; leg++) {
            const sv = leg === 0 ? m.h * 0.32 : -m.h * 0.32;
            dummy.position.set(cx + ux * sv, cy + uy * sv - 0.05, cz + uz * sv);
            dummy.scale.set(1, 1, 1);
            dummy.rotation.set(0, -sp.ridgeAzimuthDeg * DEG2RAD, 0);
            dummy.updateMatrix();
            clampInst.setMatrixAt(i * 2 + leg, dummy.matrix);
          }
        }
      }

      panelInstancedMesh.instanceMatrix.needsUpdate = true;
      worldGroup.add(panelInstancedMesh);
      if (postInst) {
        postInst.castShadow = true;
        postInst.instanceMatrix.needsUpdate = true;
        worldGroup.add(postInst);
      }
      if (ballastInst) {
        ballastInst.castShadow = true;
        ballastInst.receiveShadow = true;
        ballastInst.instanceMatrix.needsUpdate = true;
        if (ballastInst.instanceColor) ballastInst.instanceColor.needsUpdate = true;
        worldGroup.add(ballastInst);
      }
      if (clampInst) {
        clampInst.instanceMatrix.needsUpdate = true;
        worldGroup.add(clampInst);
      }
    }

    // 7. 3D String Inverters, Galvanized DC Cable Trays & Ground BESS + Grid-Tie Station
    const invBodyMat = new T.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.32, metalness: 0.25 });
    const invScreenMat = new T.MeshStandardMaterial({ color: 0x0ea5e9, emissive: 0x0284c7, emissiveIntensity: 0.35 });
    for (const inv of sp.inverters3d) {
      const [ix, iy, iz] = inv.position3d;
      const chassis = new T.Mesh(new T.BoxGeometry(1.05, 0.72, 0.36), invBodyMat);
      chassis.position.set(ix, iy, iz);
      chassis.castShadow = true;
      worldGroup.add(chassis);

      const led = new T.Mesh(new T.BoxGeometry(0.28, 0.14, 0.38), invScreenMat);
      led.position.set(ix, iy + 0.1, iz);
      worldGroup.add(led);

      const stand = new T.Mesh(
        new T.BoxGeometry(0.85, Math.max(0.3, iy - inv.baseY), 0.12),
        new T.MeshStandardMaterial({ color: 0x475569, metalness: 0.6, roughness: 0.4 })
      );
      stand.position.set(ix, inv.baseY + (iy - inv.baseY) * 0.5, iz - 0.14);
      worldGroup.add(stand);
    }

    // DC Cable Trays along home-run paths
    if (simCfg.displayMode === 'wiring' || sp.cableTrays3d.length <= 40) {
      for (const tray of sp.cableTrays3d) {
        const pts = tray.points3d.map((p) => new T.Vector3(p[0], p[1], p[2]));
        const lineMat = new T.LineBasicMaterial({
          color: simCfg.displayMode === 'wiring' ? new T.Color(tray.color) : new T.Color(0x64748b),
        });
        const line = new T.Line(new T.BufferGeometry().setFromPoints(pts), lineMat);
        worldGroup.add(line);
      }
    }

    // Ground-level Grid-Tie Cabinet & Optional Liquid-Cooled BESS Container
    const stationX = sp.widthM * 0.5 + 4.2;
    const gridCab = new T.Mesh(
      new T.BoxGeometry(2.2, 2.3, 1.4),
      new T.MeshStandardMaterial({ color: 0xcbd5e1, roughness: 0.48, metalness: 0.35 })
    );
    gridCab.position.set(stationX, 1.15, 0);
    gridCab.castShadow = true;
    worldGroup.add(gridCab);

    if (sp.bessCapacityKwh > 0) {
      const bessLen = Math.min(6.2, Math.max(2.6, sp.bessCapacityKwh / 180));
      const bessBox = new T.Mesh(
        new T.BoxGeometry(2.4, 2.6, bessLen),
        new T.MeshStandardMaterial({ color: 0xf1f5f9, roughness: 0.36, metalness: 0.32 })
      );
      bessBox.position.set(stationX, 1.3, 4.2);
      bessBox.castShadow = true;
      worldGroup.add(bessBox);

      const bessStripe = new T.Mesh(
        new T.BoxGeometry(2.44, 0.28, bessLen * 0.96),
        new T.MeshStandardMaterial({ color: 0x10b981, roughness: 0.3 })
      );
      bessStripe.position.set(stationX, 2.1, 4.2);
      worldGroup.add(bessStripe);
    }

    // 8. Celestial 3D Sun-Path Dome Arcs (Winter Solstice, Equinox, Summer Solstice)
    disposeGroup(dynamicSunGroup);
    if (simCfg.showSunDome) {
      const domeR = Math.max(28, compassR * 1.12);
      const arcSpecs = [
        { date: '2026-12-21', color: 0x3b82f6 }, // Winter Solstice
        { date: '2026-03-21', color: 0x10b981 }, // Equinox
        { date: '2026-06-21', color: 0xf59e0b }, // Summer Solstice
      ];
      for (const arc of arcSpecs) {
        const arcPts = [];
        for (let hr = 5.5; hr <= 18.5; hr += 0.25) {
          const sv = computeSolarVectorBjt(stateRef.lat, stateRef.lon, arc.date, hr);
          if (sv.altitudeDeg > 0) {
            arcPts.push(new T.Vector3(
              sv.direction[0] * domeR,
              sp.buildingHeightM * 0.35 + sv.direction[1] * domeR,
              sv.direction[2] * domeR
            ));
          }
        }
        if (arcPts.length >= 2) {
          const arcLine = new T.Line(
            new T.BufferGeometry().setFromPoints(arcPts),
            new T.LineBasicMaterial({ color: arc.color, transparent: true, opacity: 0.55 })
          );
          dynamicSunGroup.add(arcLine);
        }
      }

      sunOrbMesh = new T.Mesh(
        new T.SphereGeometry(Math.max(1.1, span * 0.026), 20, 20),
        new T.MeshBasicMaterial({ color: 0xfbbf24 })
      );
      dynamicSunGroup.add(sunOrbMesh);

      sunRayLine = new T.Line(
        new T.BufferGeometry().setFromPoints([new T.Vector3(), new T.Vector3(0, sp.buildingHeightM, 0)]),
        new T.LineBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.68 })
      );
      dynamicSunGroup.add(sunRayLine);
    } else {
      sunOrbMesh = null;
      sunRayLine = null;
    }

    currentAnnual = computeAnnual3DShadingSummary(sp, { lat: stateRef.lat, lon: stateRef.lon });
    updateSunAndColors();
  }

  function updateSunAndColors() {
    if (!currentSpec) return;
    const sp = currentSpec;
    currentShading = compute3DPhysicalShading(sp, {
      lat: stateRef.lat,
      lon: stateRef.lon,
      dateStr: simCfg.dateStr,
      hourBjt: simCfg.hourBjt,
    });

    const { solar, sunUp } = currentShading;
    const sunDist = Math.max(45, sp.spanM * 1.65);
    const [dx, dy, dz] = solar.direction;

    if (sunUp) {
      sunLight.intensity = clamp(0.55 + Math.sin(solar.altitudeDeg * DEG2RAD) * 1.35, 0.45, 1.75);
      sunLight.position.set(dx * sunDist, sp.buildingHeightM + dy * sunDist, dz * sunDist);
      sunLight.target.position.set(0, sp.buildingHeightM * 0.6, 0);
      sunLight.target.updateMatrixWorld();
      const frustum = Math.max(24, sp.spanM * 0.95);
      Object.assign(sunLight.shadow.camera, {
        left: -frustum,
        right: frustum,
        top: frustum,
        bottom: -frustum,
        near: 1,
        far: sunDist * 3.2,
      });
      sunLight.shadow.camera.updateProjectionMatrix();
      scene.background = new T.Color(solar.altitudeDeg < 12 ? 0xfde68a : 0xdbeafe);
    } else {
      sunLight.intensity = 0.08;
      sunLight.position.set(0, sp.spanM * 1.4, sp.spanM * 0.5);
      scene.background = new T.Color(0x1e293b);
    }

    // Update 3D Celestial Sun Orb & Ray Line
    if (sunOrbMesh && sunRayLine) {
      const domeR = Math.max(28, sp.spanM * 0.68 * 1.12);
      sunOrbMesh.visible = sunUp;
      sunRayLine.visible = sunUp;
      if (sunUp) {
        const sx = dx * domeR;
        const sy = sp.buildingHeightM * 0.35 + dy * domeR;
        const sz = dz * domeR;
        sunOrbMesh.position.set(sx, sy, sz);
        sunRayLine.geometry.setFromPoints([
          new T.Vector3(sx, sy, sz),
          new T.Vector3(0, sp.ridgePeakY, 0),
        ]);
      }
    }

    // Recolor PV InstancedMesh according to active engineering display mode
    if (panelInstancedMesh) {
      const mode = simCfg.displayMode;
      const useRealMap = mode === 'realistic';
      const targetMap = useRealMap
        ? (textures?.solarPanelMap || textures?.solarPanelTintableMap || null)
        : (textures?.solarPanelTintableMap || null);
      if (panelInstancedMesh.material.map !== targetMap) {
        panelInstancedMesh.material.map = targetMap;
        panelInstancedMesh.material.roughness = useRealMap ? 0.22 : 0.34;
        panelInstancedMesh.material.metalness = useRealMap ? 0.38 : 0.18;
        panelInstancedMesh.material.needsUpdate = true;
      }

      const col = new T.Color();
      for (let i = 0; i < sp.modules3d.length; i++) {
        const m = sp.modules3d[i];
        const sh = currentShading.modules[i];
        if (mode === 'realistic') {
          // Subtle darkening on shaded panels even in PBR realistic mode
          const shadeDim = sh && sh.linearShadeFrac > 0.05 ? 1 - 0.32 * sh.linearShadeFrac : 1.0;
          col.setRGB(shadeDim, shadeDim, shadeDim);
        } else if (mode === 'irradiance') {
          col.setHex(heatIrradianceHex(sh?.poaWm2 ?? 0, Math.max(450, currentShading.unshadedPoaWm2)));
        } else if (mode === 'diode') {
          const d = sh?.bypassedDiodes ?? 0;
          col.setHex(d === 0 ? 0x10b981 : d === 1 ? 0xf59e0b : d === 2 ? 0xf97316 : 0xef4444);
        } else if (mode === 'wiring') {
          col.set(m.stringColor || '#2563eb');
        } else if (mode === 'wind') {
          col.setHex(m.windZone === 'corner' ? 0xef4444 : m.windZone === 'edge' ? 0xf59e0b : 0x0ea5e9);
        } else {
          col.setHex(0xffffff);
        }
        panelInstancedMesh.setColorAt(i, col);
      }
      if (panelInstancedMesh.instanceColor) {
        panelInstancedMesh.instanceColor.needsUpdate = true;
      }
    }

    callbacks.onShadingUpdate?.({
      shading: currentShading,
      annual: currentAnnual,
      simCfg: { ...simCfg },
    });
    needsShadow = true;
    needsRender = true;
  }

  function setCameraPreset(preset = 'iso') {
    if (!currentSpec) return;
    const sp = currentSpec;
    const span = sp.spanM;
    const targetY = sp.buildingHeightM * 0.72;
    controls.target.set(0, targetY, 0);

    if (preset === 'top') {
      camera.position.set(0, sp.ridgePeakY + span * 1.28, 0.05);
    } else if (preset === 'south') {
      camera.position.set(0, sp.buildingHeightM + span * 0.52, span * 1.12);
    } else if (preset === 'walkway') {
      // Eye-level roof O&M inspection viewpoint right on the roof edge!
      controls.target.set(0, sp.ridgePeakY + 0.4, 0);
      camera.position.set(-sp.widthM * 0.36, sp.ridgePeakY + 2.1, sp.depthM * 0.44);
    } else if (preset === 'street') {
      // Human eye-level street/campus perspective looking up at the factory & BESS
      controls.target.set(0, sp.buildingHeightM * 0.65, 0);
      camera.position.set(sp.widthM * 0.78, 2.4, sp.depthM * 0.92);
    } else {
      camera.position.set(span * 0.74, sp.buildingHeightM + span * 0.62, span * 0.88);
    }
    controls.minDistance = 2.5;
    controls.maxDistance = span * 6;
    controls.update();
    needsRender = true;
  }

  // Interactive Raycasted Module Hover Inspector
  const raycaster = new T.Raycaster();
  const pointer = new T.Vector2();
  const windLabels = { corner: '角部高压区 (加密抗风)', edge: '周边边缘区', interior: '屋面内部标准区' };

  const onPointerMove = (ev) => {
    if (!panelInstancedMesh || !currentSpec || !currentShading) return;
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    pointer.set(
      ((ev.clientX - rect.left) / rect.width) * 2 - 1,
      -((ev.clientY - rect.top) / rect.height) * 2 + 1
    );
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObject(panelInstancedMesh, false)[0];
    if (hit && hit.instanceId != null && currentSpec.modules3d[hit.instanceId]) {
      const m = currentSpec.modules3d[hit.instanceId];
      const sh = currentShading.modules[hit.instanceId];
      const annLoss = currentAnnual?.moduleAnnualLossPct?.[hit.instanceId] ?? 0;
      const slopeText = m.slope === 'north' ? '北坡子阵' : '南坡/主阵';
      const diodeText = (sh?.bypassedDiodes ?? 0) > 0
        ? `⚠️ 已触发 ${sh.bypassedDiodes}/3 组旁路二极管`
        : '✅ 三组旁路二极管全导通无遮挡';
      tooltip.hidden = false;
      tooltip.innerHTML = [
        `<b>组件 ${m.id}</b> · ${slopeText}（倾角 ${m.tiltDeg}° / 方位 ${m.azimuthDeg}°）`,
        `组串归属：${m.stringId || '待分配'} · 抗风分区：${windLabels[m.windZone] || m.windZone}`,
        `实时斜面辐照：<b>${sh?.poaWm2 ?? 0} W/m²</b> · 几何遮挡率：<b>${((sh?.linearShadeFrac ?? 0) * 100).toFixed(1)}%</b>`,
        `${diodeText} · 全年阴影失配：<b>${annLoss}%</b>`,
      ].join('<br>');
    } else {
      tooltip.hidden = true;
    }
  };
  const onPointerLeave = () => { tooltip.hidden = true; };
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerleave', onPointerLeave);

  let disposed = false;
  let rafId = null;
  let lastFrameTs = 0;

  const resizeObserver = typeof ResizeObserver !== 'undefined'
    ? new ResizeObserver(() => {
        const { width, height } = container.getBoundingClientRect();
        if (width > 0 && height > 0) {
          renderer.setSize(width, height, false);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
          needsRender = true;
        }
      })
    : null;
  resizeObserver?.observe(container);

  // Initial sizing & scene build
  const initRect = container.getBoundingClientRect();
  const initW = Math.max(320, initRect.width || 920);
  const initH = Math.max(240, initRect.height || 580);
  renderer.setSize(initW, initH, false);
  camera.aspect = initW / initH;
  camera.updateProjectionMatrix();

  buildBuildingAndArrayGeometry();
  setCameraPreset('iso');

  function animate(ts = 0) {
    if (disposed) return;
    rafId = requestAnimationFrame(animate);
    if (simCfg.playing) {
      const dtSec = lastFrameTs ? Math.min(0.1, (ts - lastFrameTs) / 1000) : 0.016;
      let nextHr = simCfg.hourBjt + dtSec * 1.45; // Smooth full-day sweep in ~8.5 seconds
      if (nextHr > 18.2) nextHr = 6.5;
      simCfg.hourBjt = Number(nextHr.toFixed(2));
      updateSunAndColors();
    }
    lastFrameTs = ts;
    controls.update();
    if (needsRender || simCfg.playing) {
      renderer.shadowMap.needsUpdate = needsShadow;
      renderer.render(scene, camera);
      needsShadow = false;
      needsRender = false;
    }
  }
  animate();

  return {
    available: true,
    updateState(nextState = {}, { keepCamera = true } = {}) {
      stateRef = { ...stateRef, ...nextState };
      buildBuildingAndArrayGeometry();
      if (!keepCamera) setCameraPreset('iso');
    },
    setSimConfig(patch = {}) {
      const rebuildNeeded =
        ('showSunDome' in patch && patch.showSunDome !== simCfg.showSunDome) ||
        ('showRacking' in patch && patch.showRacking !== simCfg.showRacking) ||
        ('displayMode' in patch && patch.displayMode === 'wiring' && simCfg.displayMode !== 'wiring');
      Object.assign(simCfg, patch);
      if (rebuildNeeded) buildBuildingAndArrayGeometry();
      else updateSunAndColors();
    },
    getSimConfig: () => ({ ...simCfg }),
    setCameraPreset,
    getShadingSnapshot: () => ({
      shading: currentShading,
      annual: currentAnnual,
      spec: currentSpec,
    }),
    capturePng() {
      renderer.render(scene, camera);
      return typeof canvas.toDataURL === 'function' ? canvas.toDataURL('image/png') : null;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      if (rafId != null) cancelAnimationFrame(rafId);
      resizeObserver?.disconnect();
      canvas.removeEventListener('pointermove', onPointerMove);
      canvas.removeEventListener('pointerleave', onPointerLeave);
      controls.dispose();
      disposeGroup(worldGroup);
      disposeGroup(dynamicSunGroup);
      sunLight.shadow.map?.dispose?.();
      renderer.dispose();
      container.replaceChildren();
    },
  };
}
