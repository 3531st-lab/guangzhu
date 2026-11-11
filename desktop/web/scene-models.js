// Realistic multi-part 3D procedural models for rooftop obstacles, surrounding buildings/trees,
// and non-factory PV synergy scenarios (livestock/poultry grazing, desert sand-control grid, solar carport EVs).

export function buildObstacleModel(T, { obstacle, data, base, roof, mesh: rawMesh, polygon: rawPolygon, material, detailLine, followRoof, identify }) {
  const mesh = (...args) => identify(rawMesh(...args), 'item', obstacle.id);
  const polygon = (...args) => identify(rawPolygon(...args), 'item', obstacle.id);
  const label = String(obstacle.label ?? obstacle.id ?? '').toLowerCase();
  const elev = roof.type === 'metal' ? data.elevation(obstacle.center ?? obstacle.footprint?.[0] ?? [0, 0]) : 0;

  if (obstacle.kind === 'cylinder') {
    const [cx, cy] = obstacle.center;
    const r = Math.max(0.25, Number(obstacle.radius_m) || 0.8);
    const h = Math.max(0.3, Number(obstacle.height_m) || 1.2);
    const p = data.world([cx, cy, 0]);
    const yBottom = roof.height_m + base + elev;
    const isCoolingTower = label.includes('冷却') || label.includes('cooling') || (r >= 1.35 && h >= 1.6);
    const isChimney = !isCoolingTower && (h >= 1.6 || label.includes('排') || label.includes('烟') || label.includes('塔') || label.includes('筒') || label.includes('scrub'));

    if (isCoolingTower) {
      // Lower water basin
      mesh(new T.CylinderGeometry(r * 1.02, r * 1.04, h * 0.22, 24), material('#475569', { roughness: 0.7 }), [p[0], yBottom + h * 0.11, p[2]]);
      // Blue louver intake band
      mesh(new T.CylinderGeometry(r * 0.97, r * 0.99, h * 0.24, 24), material('#38bdf8', { roughness: 0.5 }), [p[0], yBottom + h * 0.34, p[2]]);
      // Top diffuser fan stack
      mesh(new T.CylinderGeometry(r * 0.62, r * 0.72, h * 0.24, 24), material('#64748b', { roughness: 0.5, metalness: 0.3 }), [p[0], yBottom + h * 0.88, p[2]]);
      // Dark fan hub & blades inside diffuser
      mesh(new T.CylinderGeometry(r * 0.55, r * 0.55, 0.05, 20), material('#1e293b'), [p[0], yBottom + h * 0.99, p[2]]);
      mesh(new T.CylinderGeometry(r * 0.16, r * 0.16, 0.09, 12), material('#0f172a'), [p[0], yBottom + h * 1.01, p[2]]);
      // Main body created last so centered bounding box lookups resolve to main body
      const mainBody = mesh(new T.CylinderGeometry(r * 0.92, r, h * 0.78, 28), material('#cbd5e1', { roughness: 0.55, metalness: 0.15 }), [p[0], yBottom + h * 0.39, p[2]]);
      followRoof(mainBody);
    } else if (isChimney) {
      const stackRadius = Math.max(0.22, r * 0.78);
      // Reinforced pedestal base
      mesh(new T.CylinderGeometry(r * 1.05, r * 1.12, Math.min(0.35, h * 0.18), 20), material('#475569'), [p[0], yBottom + Math.min(0.175, h * 0.09), p[2]]);
      // Flange rings along stack
      for (const frac of [0.32, 0.62, 0.86]) {
        mesh(new T.CylinderGeometry(stackRadius * 1.16, stackRadius * 1.16, 0.07, 24), material('#475569', { metalness: 0.4 }), [p[0], yBottom + h * frac, p[2]]);
      }
      // Conical rain cap at top
      const cap = mesh(new T.ConeGeometry(stackRadius * 1.35, Math.min(0.45, h * 0.16), 24), material('#334155', { metalness: 0.4 }), [p[0], yBottom + h * 0.96, p[2]]);
      cap.position.y = yBottom + h - Math.min(0.22, h * 0.08);
      const mainStack = mesh(new T.CylinderGeometry(stackRadius, stackRadius * 1.06, h * 0.88, 28), material('#94a3b8', { roughness: 0.5, metalness: 0.35 }), [p[0], yBottom + h * 0.44, p[2]]);
      followRoof(mainStack);
    } else {
      // Flashing base plate
      mesh(new T.BoxGeometry(r * 1.85, 0.06, r * 1.85), material('#64748b'), [p[0], yBottom + 0.03, p[2]]);
      // Bulbous turbine dome
      const dome = mesh(new T.SphereGeometry(r * 0.95, 24, 16), material('#e2e8f0', { roughness: 0.32, metalness: 0.55 }), [p[0], yBottom + h * 0.68, p[2]]);
      dome.scale.set(1, Math.max(0.45, (h * 0.58) / (r * 1.9)), 1);
      mesh(new T.CylinderGeometry(r * 1.02, r * 1.02, Math.min(0.12, h * 0.15), 24), material('#cbd5e1', { metalness: 0.5 }), [p[0], yBottom + h * 0.68, p[2]]);
      const mainVent = mesh(new T.CylinderGeometry(r * 0.68, r * 0.68, h * 0.45, 24), material('#94a3b8', { roughness: 0.4, metalness: 0.45 }), [p[0], yBottom + h * 0.225, p[2]]);
      followRoof(mainVent);
    }

    // Wireframe detail lines on top & ladder
    const topZ = base + h + elev + 0.015;
    const ring = [], hub = [];
    for (let i = 0; i <= 16; i++) {
      const a = (i * Math.PI) / 8, c = Math.cos(a), s = Math.sin(a);
      ring.push(data.world([cx + c * r * 0.88, cy + s * r * 0.88, topZ]));
      hub.push(data.world([cx + c * r * 0.32, cy + s * r * 0.32, topZ]));
      if (i < 8 && i % 2 === 0) {
        detailLine([data.world([cx - c * r * 0.88, cy - s * r * 0.88, topZ]), data.world([cx + c * r * 0.88, cy + s * r * 0.88, topZ])]);
      }
    }
    detailLine(ring);
    detailLine(hub);
    if (h >= 1.2 && r >= 0.5) {
      const lx = cx, ly = cy - r - 0.04, bZ = base + elev;
      detailLine([data.world([lx - 0.18, ly, bZ]), data.world([lx - 0.18, ly, topZ])]);
      detailLine([data.world([lx + 0.18, ly, bZ]), data.world([lx + 0.18, ly, topZ])]);
      for (let z = bZ + 0.35; z < topZ - 0.1; z += 0.35) {
        detailLine([data.world([lx - 0.18, ly, z]), data.world([lx + 0.18, ly, z])]);
      }
    }
    return;
  }

  // Polygon obstacles: Skylight, HVAC Chiller Unit, or Elevator/Equipment Penthouse
  const pts = obstacle.footprint ?? [];
  if (pts.length < 3) return;
  const h = Math.max(0.25, Number(obstacle.height_m) || 1.2);
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  const spanX = Math.max(0.6, maxX - minX), spanY = Math.max(0.6, maxY - minY);
  const worldCenter = data.world([cx, cy, 0]);
  const yBottom = roof.height_m + base + (roof.type === 'metal' ? data.elevation([cx, cy]) : 0);

  const isSkylight = label.includes('天窗') || label.includes('采光') || label.includes('排烟窗') || label.includes('skylight') || (pts.length === 4 && h <= 1.05);
  const isPenthouse = !isSkylight && (h >= 2.5 || label.includes('机房') || label.includes('电梯') || label.includes('楼梯') || label.includes('水箱') || label.includes('高跨'));

  if (isSkylight) {
    // Realistic Curbed Glazed Skylight (混凝土/钢构反坎底座 + 蓝透采光玻璃拱顶 + 铝合金窗框肋条)
    const curbH = Math.min(h * 0.52, 0.42);
    const glazingH = Math.max(0.15, h - curbH);
    const isWideX = spanX >= spanY;
    mesh(
      new T.BoxGeometry(isWideX ? spanX * 0.96 : 0.12, 0.08, isWideX ? 0.12 : spanY * 0.96),
      material('#334155'),
      [worldCenter[0], yBottom + h + 0.03, worldCenter[2]]
    );
    polygon(pts, glazingH, roof.height_m + base + curbH, '#60a5fa', { roughness: 0.2, metalness: 0.25 });
    polygon(pts, curbH, roof.height_m + base, '#94a3b8');
  } else if (isPenthouse) {
    // Realistic Rooftop Elevator / Equipment Penthouse (钢筋混凝土机房 + 挑檐顶板 + 防火钢门 + 百叶风口 + 避雷针)
    const wallH = h * 0.92;
    // Overhanging concrete roof slab
    mesh(
      new T.BoxGeometry(spanX + 0.36, Math.max(0.16, h * 0.08), spanY + 0.36),
      material('#64748b'),
      [worldCenter[0], yBottom + h - Math.max(0.08, h * 0.04), worldCenter[2]]
    );
    // Steel access door on south face
    const doorW = Math.min(1.1, spanX * 0.35), doorH = Math.min(2.0, wallH * 0.78);
    const doorPos = data.world([cx - spanX * 0.15, minY - 0.03, 0]);
    mesh(new T.BoxGeometry(doorW, doorH, 0.08), material('#334155', { metalness: 0.4 }), [doorPos[0], yBottom + doorH / 2, doorPos[2]]);
    // Ventilation louver grille next to door
    const louverW = Math.min(1.2, spanX * 0.32), louverH = Math.min(0.8, wallH * 0.32);
    const louverPos = data.world([cx + spanX * 0.22, minY - 0.03, 0]);
    mesh(new T.BoxGeometry(louverW, louverH, 0.08), material('#475569'), [louverPos[0], yBottom + wallH * 0.62, louverPos[2]]);
    // Rooftop lightning rod mast
    mesh(new T.CylinderGeometry(0.03, 0.04, 1.1, 8), material('#475569', { metalness: 0.6 }), [worldCenter[0] + spanX * 0.35, yBottom + h + 0.55, worldCenter[2] - spanY * 0.35]);
    polygon(pts, wallH, roof.height_m + base, '#d6cfc7');
  } else {
    // Realistic Industrial HVAC Chiller / Cleanroom Air Handling Unit (减震槽钢底座 + 镀锌箱体 + 顶部双/多轴流风机罩与扇叶 + 侧面散热翅片百叶)
    const skidH = Math.min(0.18, h * 0.12);
    const bodyH = Math.max(0.25, h * 0.74);
    const fanH = Math.max(0.12, h - skidH - bodyH);
    // Steel skid rails
    mesh(new T.BoxGeometry(spanX * 0.96, skidH, 0.16), material('#1e293b'), [worldCenter[0], yBottom + skidH / 2, worldCenter[2] - spanY * 0.38]);
    mesh(new T.BoxGeometry(spanX * 0.96, skidH, 0.16), material('#1e293b'), [worldCenter[0], yBottom + skidH / 2, worldCenter[2] + spanY * 0.38]);
    // Side dark condenser coil grilles
    mesh(
      new T.BoxGeometry(spanX * 0.84, bodyH * 0.68, spanY + 0.05),
      material('#334155', { roughness: 0.7 }),
      [worldCenter[0], yBottom + skidH + bodyH * 0.52, worldCenter[2]]
    );
    // Top axial exhaust fan shrouds & dark fan rotors
    const longX = spanX >= spanY;
    const longSpan = Math.max(spanX, spanY), shortSpan = Math.min(spanX, spanY);
    const fanCount = Math.max(1, Math.min(4, Math.round(longSpan / Math.max(1.2, shortSpan * 0.95))));
    const fanRadius = Math.min(shortSpan * 0.36, (longSpan / fanCount) * 0.36, 0.85);
    for (let i = 0; i < fanCount; i++) {
      const offset = ((i + 0.5) / fanCount - 0.5) * longSpan * 0.82;
      const fx = longX ? cx + offset : cx;
      const fy = longX ? cy : cy + offset;
      const fp = data.world([fx, fy, 0]);
      // Fan shroud cylinder
      mesh(
        new T.CylinderGeometry(fanRadius, fanRadius * 1.06, fanH, 20),
        material('#475569', { metalness: 0.35 }),
        [fp[0], yBottom + skidH + bodyH + fanH / 2, fp[2]]
      );
      // Dark fan rotor disk & hub
      mesh(
        new T.CylinderGeometry(fanRadius * 0.86, fanRadius * 0.86, 0.04, 16),
        material('#0f172a'),
        [fp[0], yBottom + h - 0.01, fp[2]]
      );
      mesh(
        new T.CylinderGeometry(fanRadius * 0.24, fanRadius * 0.24, 0.07, 12),
        material('#64748b'),
        [fp[0], yBottom + h + 0.01, fp[2]]
      );
    }
    // Main HVAC cabinet created last so centered bounding box lookups resolve to main footprint
    polygon(pts, bodyH, roof.height_m + base + skidH, '#cbd5e1', { roughness: 0.48, metalness: 0.25 });
  }

  // Top outline & skylight mullion lines
  const topPts = [...pts, pts[0]].map(pt =>
    data.world([pt[0], pt[1], base + h + (roof.type === 'metal' ? data.elevation(pt) : 0) + 0.015])
  );
  detailLine(topPts);
  if (pts.length === 4 && h <= 1.05) {
    const [p0, p1, p2, p3] = pts;
    const steps = Math.min(8, Math.max(2, Math.floor(Math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / 1.2)));
    for (let i = 1; i < steps; i++) {
      const t = i / steps;
      const a = [p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t];
      const b = [p3[0] + (p2[0] - p3[0]) * t, p3[1] + (p2[1] - p3[1]) * t];
      const zA = base + h + (roof.type === 'metal' ? data.elevation(a) : 0) + 0.015;
      const zB = base + h + (roof.type === 'metal' ? data.elevation(b) : 0) + 0.015;
      detailLine([data.world([a[0], a[1], zA]), data.world([b[0], b[1], zB])], 0x1e3a8a);
    }
  }
}

export function buildSurroundingModel(T, { near, data, roof, mesh: rawMesh, polygon: rawPolygon, material, identify }) {
  const mesh = (...args) => identify(rawMesh(...args), 'item', near.id);
  const polygon = (...args) => identify(rawPolygon(...args), 'item', near.id);
  const totalH = Math.max(1.5, Number(roof.height_m || 0) + Number(near.height_m || 2));

  if (near.kind === 'cylinder') {
    // Realistic Multi-Crown 3D Tree (tapered bark trunk + branches + multi-sphere organic green foliage crown)
    const p = data.world(near.center ?? [0, 0]);
    const r = Math.max(0.8, Number(near.radius_m) || 2.0);
    const trunkH = Math.min(totalH * 0.45, Math.max(1.8, totalH - r * 1.3));
    const trunkR = Math.max(0.16, Math.min(0.45, r * 0.16));

    // Tree trunk
    mesh(
      new T.CylinderGeometry(trunkR * 0.7, trunkR * 1.15, trunkH, 12),
      material('#6b4c35', { roughness: 0.9 }),
      [p[0], trunkH / 2, p[2]]
    );

    const crownCenterY = trunkH + (totalH - trunkH) * 0.52;
    const mainCrownR = Math.max(r * 0.85, (totalH - trunkH) * 0.52);

    // Sub-crowns for organic tree silhouette
    const lobes = [
      [-r * 0.42, -r * 0.15, -r * 0.32, 0.62, '#5a8f4e'],
      [r * 0.44, -r * 0.10, r * 0.28, 0.58, '#3f6a37'],
      [-r * 0.22, r * 0.18, r * 0.40, 0.55, '#558749'],
      [r * 0.28, r * 0.22, -r * 0.36, 0.52, '#48753e'],
    ];
    for (const [dx, dy, dz, scale, col] of lobes) {
      mesh(
        new T.DodecahedronGeometry(r * scale, 1),
        material(col, { roughness: 0.85 }),
        [p[0] + dx, Math.min(totalH - r * scale * 0.5, Math.max(trunkH * 0.85, crownCenterY + dy)), p[2] + dz]
      );
    }

    // Main central canopy created last
    const mainCrown = mesh(
      new T.DodecahedronGeometry(mainCrownR, 1),
      material('#4d7c43', { roughness: 0.85 }),
      [p[0], crownCenterY, p[2]]
    );
    mainCrown.scale.set(1, Math.max(0.7, (totalH - trunkH) / (mainCrownR * 1.9)), 1);
    return;
  }

  // Realistic Surrounding Building (multi-story facade with floor bands, window strips & parapet)
  const pts = near.footprint ?? [];
  if (pts.length < 3) return;

  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  const spanX = Math.max(1, maxX - minX), spanY = Math.max(1, maxY - minY);
  const wc = data.world([cx, cy, 0]);

  // Rooftop parapet cap
  mesh(
    new T.BoxGeometry(spanX + 0.24, 0.35, spanY + 0.24),
    material('#8c8275'),
    [wc[0], totalH + 0.175, wc[2]]
  );
  // Multi-story horizontal window bands
  const stories = Math.max(1, Math.min(12, Math.floor(totalH / 3.8)));
  for (let s = 1; s <= stories; s++) {
    const wy = s * 3.6 - 1.2;
    if (wy + 1.1 < totalH) {
      mesh(
        new T.BoxGeometry(spanX * 0.88, 1.15, spanY + 0.08),
        material('#3b5978', { roughness: 0.35, metalness: 0.3 }),
        [wc[0], wy, wc[2]]
      );
    }
  }
  polygon(pts, totalH, 0, '#c8beb2');
}

export function buildSynergySceneDetails(T, { input, data, roof, mesh, material }) {
  const pid = String(input.project?.id ?? '').toLowerCase();
  const pname = String(input.project?.name ?? '');
  const albedo = Number(input.project?.site?.albedo ?? 0.2);

  if (roof.type === 'ground') {
    const isDesert = albedo >= 0.28 || pid.includes('desert') || pid.includes('sand') || pname.includes('防沙') || pname.includes('治沙') || pname.includes('荒漠');
    const isGrazing = roof.use === 'grazing' || pid.includes('grazing') || pid.includes('poultry') || pid.includes('lixiahe') || pname.includes('牧光') || pname.includes('家禽') || pname.includes('禽');

    const xs = roof.outline.map(p => p[0]), ys = roof.outline.map(p => p[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);

    if (isDesert) {
      // Northwest Desert Sand-Control Straw Checkerboard Grid (西北防沙治沙 1.5m×1.5m 草方格固沙网格与沙生灌木)
      const step = 3.0;
      for (let x = minX + 1.5; x <= maxX - 1.5; x += step) {
        const pMid = data.world([x, (minY + maxY) / 2, 0]);
        mesh(new T.BoxGeometry(0.08, 0.12, (maxY - minY) * 0.92), material('#b58938'), [pMid[0], 0.06, pMid[2]]);
      }
      for (let y = minY + 1.5; y <= maxY - 1.5; y += step) {
        const pMid = data.world([(minX + maxX) / 2, y, 0]);
        mesh(new T.BoxGeometry((maxX - minX) * 0.92, 0.12, 0.08), material('#b58938'), [pMid[0], 0.06, pMid[2]]);
      }
      // Desert shrubs (沙柳/梭梭) inside checkerboards
      for (let x = minX + 3; x < maxX - 3; x += 6) {
        for (let y = minY + 3; y < maxY - 3; y += 6) {
          const sp = data.world([x, y, 0]);
          mesh(new T.DodecahedronGeometry(0.32, 0), material('#6d8c54'), [sp[0], 0.25, sp[2]]);
        }
      }
    } else if (isGrazing) {
      // Agrivoltaics / Poultry & Sheep Synergy (禽畜牧光互补：板下散养湖羊、泰州麻鸭/家禽群与饮水饲喂槽)
      const spanX = maxX - minX, spanY = maxY - minY;
      // Livestock watering trough
      const tp = data.world([minX + spanX * 0.18, minY + spanY * 0.15, 0]);
      mesh(new T.BoxGeometry(2.8, 0.42, 0.75), material('#64748b'), [tp[0], 0.21, tp[2]]);
      mesh(new T.BoxGeometry(2.6, 0.08, 0.58), material('#38bdf8'), [tp[0], 0.41, tp[2]]);

      // Flock of sheep & poultry along inter-row corridors
      for (let i = 0; i < 10; i++) {
        const fx = minX + spanX * (0.22 + ((i * 0.17) % 0.62));
        const fy = minY + spanY * (0.20 + (Math.floor(i / 3) * 0.22));
        const ap = data.world([fx, fy, 0]);
        if (i % 2 === 0) {
          // 3D Sheep (湖羊)
          mesh(new T.BoxGeometry(0.85, 0.52, 0.46), material('#f8fafc'), [ap[0], 0.48, ap[2]]);
          mesh(new T.BoxGeometry(0.32, 0.30, 0.28), material('#cbd5e1'), [ap[0] + 0.48, 0.62, ap[2]]);
          for (const [lx, lz] of [[-0.28, -0.15], [0.28, -0.15], [-0.28, 0.15], [0.28, 0.15]]) {
            mesh(new T.CylinderGeometry(0.05, 0.04, 0.32, 6), material('#475569'), [ap[0] + lx, 0.16, ap[2] + lz]);
          }
        } else {
          // 3D Poultry / Waterfowl (泰州里下河麻鸭/生态家禽)
          mesh(new T.SphereGeometry(0.24, 10, 8), material('#d97706'), [ap[0], 0.26, ap[2]]);
          mesh(new T.SphereGeometry(0.13, 8, 8), material('#92400e'), [ap[0] + 0.20, 0.42, ap[2]]);
        }
      }
    }
  } else if (roof.type === 'carport') {
    // Solar Carport EV Vehicles & Charging Bollards
    const bays = input.facilities?.bays ?? [];
    bays.slice(0, 8).forEach((bay, idx) => {
      if (idx % 2 === 1 || !bay.polygon || bay.polygon.length < 4) return;
      const bx = bay.polygon.reduce((s, p) => s + p[0], 0) / bay.polygon.length;
      const by = bay.polygon.reduce((s, p) => s + p[1], 0) / bay.polygon.length;
      const cp = data.world([bx, by, 0]);
      const carColors = ['#2563eb', '#f8fafc', '#475569', '#0d9488'];
      const col = carColors[idx % carColors.length];
      // Lower car chassis
      mesh(new T.BoxGeometry(1.82, 0.68, 4.35), material(col, { roughness: 0.35, metalness: 0.4 }), [cp[0], 0.52, cp[2]]);
      // Upper cabin greenhouse
      mesh(new T.BoxGeometry(1.56, 0.56, 2.35), material('#1e293b', { roughness: 0.2, metalness: 0.5 }), [cp[0], 1.08, cp[2] - 0.15]);
      // EV Charging post at bay head
      mesh(new T.BoxGeometry(0.28, 1.35, 0.22), material('#10b981'), [cp[0] + 1.05, 0.68, cp[2] - 2.35]);
    });
  } else if (roof.type === 'flat' && Array.isArray(data.modules) && data.modules.length > 0) {
    // Flat concrete roof 3D hot-dip galvanized racking posts + C30 concrete ballast piers
    const stride = data.modules.length > 360 ? 2 : 1;
    const postMat = material('#94a3b8', { roughness: 0.38, metalness: 0.68 });
    const ballastMat = material('#78716c', { roughness: 0.9, metalness: 0.05 });
    const cornerBallastMat = material('#c94e42', { roughness: 0.85, metalness: 0.08 });
    for (let i = 0; i < data.modules.length; i += stride) {
      const m = data.modules[i];
      if (!Array.isArray(m.points) || m.points.length < 4) continue;
      const [p0, p1, p2, p3] = m.points;
      const eFront = [(p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5, (p0[2] + p1[2]) * 0.5];
      const eRear = [(p2[0] + p3[0]) * 0.5, (p2[1] + p3[1]) * 0.5, (p2[2] + p3[2]) * 0.5];
      const frontSupport = [eFront[0] * 0.8 + eRear[0] * 0.2, eFront[1] * 0.8 + eRear[1] * 0.2, eFront[2] * 0.8 + eRear[2] * 0.2];
      const rearSupport = [eFront[0] * 0.2 + eRear[0] * 0.8, eFront[1] * 0.2 + eRear[1] * 0.8, eFront[2] * 0.2 + eRear[2] * 0.8];
      const deckY = roof.height_m;
      const isCorner = m.wind?.zone === 'corner';
      for (const pt of [frontSupport, rearSupport]) {
        const clearance = pt[1] - deckY;
        if (clearance < 0.08) continue;
        const legH = Math.max(0.04, clearance - 0.025);
        const ballastH = Math.min(0.14, Math.max(0.03, clearance * 0.5));
        mesh(new T.BoxGeometry(0.045, legH, 0.045), postMat, [pt[0], deckY + legH * 0.5, pt[2]]);
        mesh(
          new T.BoxGeometry(isCorner ? 0.40 : 0.32, ballastH, 0.22),
          isCorner ? cornerBallastMat : ballastMat,
          [pt[0], deckY + ballastH * 0.5, pt[2]]
        );
      }
    }
  }
}

