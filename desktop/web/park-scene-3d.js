// Interactive 3D Industrial Park Digital Twin Scene Viewer (#park-scene-3d)
// Renders all buildings in the park at their real (x_m, y_m, rotation_deg) coordinates,
// with 3D building facades, parapets, realistic rooftop obstacles, park roads/trees/substation,
// and all designed 3D solar arrays across the entire park (before and after design).

function transformPt([x, y], b) {
  const rad = ((Number(b.rotation_deg) || 0) * Math.PI) / 180;
  const c = Math.cos(rad), s = Math.sin(rad);
  return [c * x - s * y + (Number(b.x_m) || 0), s * x + c * y + (Number(b.y_m) || 0)];
}

export function mountParkScene3D(container, current, options = {}) {
  if (!container || !current?.data) return { dispose() { } };
  const T = globalThis.THREE;
  if (!T?.OrbitControls) {
    container.innerHTML = '<div class="muted" style="padding:16px">当前环境未加载 WebGL 3D 引擎，请使用上方 2D 园区总图查看。</div>';
    return { dispose() { } };
  }

  const canvas = document.createElement('canvas');
  canvas.style.width = '100%';
  canvas.style.height = '100%';
  canvas.style.display = 'block';
  canvas.tabIndex = 0;
  canvas.style.outline = 'none';
  const hud = document.createElement('div');
  hud.className = 'park-3d-hud';
  hud.style.cssText = 'position:absolute;left:12px;bottom:10px;background:rgba(15,23,42,0.82);color:#f8fafc;padding:6px 12px;border-radius:8px;font-size:12px;pointer-events:none;';
  container.style.position = 'relative';
  container.replaceChildren(canvas, hud);

  let renderer;
  try {
    const context = canvas.getContext('webgl2', { antialias: true }) || canvas.getContext('webgl', { antialias: true });
    if (!context) throw new Error('no webgl');
    renderer = new T.WebGLRenderer({ canvas, context, antialias: true });
  } catch {
    container.innerHTML = '<div class="muted" style="padding:16px">此设备暂不支持 WebGL 园区 3D 沙盘，请查看 2D 园区平面图。</div>';
    return { dispose() { } };
  }

  renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, 2));
  renderer.outputEncoding = T.sRGBEncoding;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = T.PCFSoftShadowMap;

  const scene = new T.Scene();
  const isDark = document.documentElement.dataset.theme === 'dark';
  scene.background = new T.Color(isDark ? '#141820' : '#eaf1f8');

  const camera = new T.PerspectiveCamera(42, 1, 0.5, 4000);
  const controls = new T.OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enablePan = true;
  controls.panSpeed = 1.45;
  controls.screenSpacePanning = false;
  controls.maxPolarAngle = Math.PI / 2 - 0.02;

  const ambient = new T.HemisphereLight(0xffffff, 0x64748b, 0.68);
  const sun = new T.DirectionalLight(0xfff4d6, 1.15);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  scene.add(ambient, sun, sun.target);

  const linear = col => new T.Color(col).convertSRGBToLinear();
  const mat = (col, extra = {}) => new T.MeshStandardMaterial({ color: linear(col), roughness: 0.72, ...extra });

  const buildings = current.data.buildings ?? [];
  const allPts = [];
  for (const b of buildings) {
    for (const pt of b.roof?.outline ?? []) {
      allPts.push(transformPt(pt, b));
    }
  }
  if (!allPts.length) allPts.push([0, 0], [80, 60]);
  const xs = allPts.map(p => p[0]), ys = allPts.map(p => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const centerX = (minX + maxX) / 2, centerY = (minY + maxY) / 2;
  const span = Math.max(60, maxX - minX, maxY - minY);

  const world = ([x, y, z = 0]) => [x - centerX, z, -(y - centerY)];
  const group = new T.Group();
  scene.add(group);

  function addMesh(geometry, materialObj, pos = [0, 0, 0]) {
    const m = new T.Mesh(geometry, materialObj);
    m.position.fromArray(pos);
    m.castShadow = true;
    m.receiveShadow = true;
    group.add(m);
    return m;
  }

  function addExtrudedPolygon(points2d, height, baseZ, colorHex, extra = {}) {
    if (!points2d || points2d.length < 3) return null;
    const shape = new T.Shape(points2d.map(([x, y]) => new T.Vector2(x - centerX, y - centerY)));
    const geom = new T.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false });
    geom.rotateX(-Math.PI / 2);
    return addMesh(geom, mat(colorHex, extra), [0, baseZ, 0]);
  }

  // Park ground & internal roads
  const ground = addMesh(new T.PlaneGeometry(span * 3.2, span * 3.2), mat(isDark ? '#27303f' : '#dce5dc'));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.05;

  // Park road grid
  addMesh(new T.BoxGeometry(span * 1.35, 0.04, 7.5), mat('#64748b'), [0, 0.01, span * 0.42]);
  addMesh(new T.BoxGeometry(7.5, 0.04, span * 1.25), mat('#64748b'), [-span * 0.48, 0.01, 0]);

  // Central Park 10kV/35kV Box Substation (园区总并网变电站)
  const subX = -span * 0.42, subZ = span * 0.36;
  addMesh(new T.BoxGeometry(8.5, 3.4, 5.2), mat('#cbd5e1', { metalness: 0.25 }), [subX, 1.7, subZ]);
  addMesh(new T.BoxGeometry(8.9, 0.3, 5.6), mat('#1e3a8a'), [subX, 3.5, subZ]);

  // Perimeter 3D trees around park road
  for (let i = 0; i < 12; i++) {
    const tx = -span * 0.55 + (i / 11) * span * 1.1;
    const tz = span * 0.49;
    addMesh(new T.CylinderGeometry(0.22, 0.32, 2.4, 8), mat('#6b4c35'), [tx, 1.2, tz]);
    addMesh(new T.DodecahedronGeometry(1.65, 1), mat('#4d7c43'), [tx, 3.4, tz]);
  }

  let totalPanels = 0;
  let designedCount = 0;
  const colorByPhase = options.colorByPhase !== false;
  const buildingMeshes = [];
  const buildingTargets = [];

  for (const b of buildings) {
    const roof = b.roof ?? {};
    const h = Math.max(3, Number(roof.height_m) || 10);
    const parapetH = Number(roof.parapet_height_m) || 0.5;
    const transformedOutline = (roof.outline ?? []).map(pt => transformPt(pt, b));
    if (transformedOutline.length < 3) continue;

    const bMesh = addExtrudedPolygon(transformedOutline, h, 0, '#d8cfc4');
    if (bMesh) {
      bMesh.userData.buildingTemplate = b.template;
      bMesh.userData.buildingName = b.name;
      buildingMeshes.push(bMesh);
    }

    // Parapet walls
    for (let i = 0; parapetH > 0 && i < transformedOutline.length; i++) {
      const a = world([...transformedOutline[i], 0]);
      const c = world([...transformedOutline[(i + 1) % transformedOutline.length], 0]);
      const len = Math.hypot(c[0] - a[0], c[2] - a[2]);
      const wall = addMesh(
        new T.BoxGeometry(len, parapetH, 0.24),
        mat('#b8afa3'),
        [(a[0] + c[0]) / 2, h + parapetH / 2, (a[2] + c[2]) / 2]
      );
      wall.rotation.y = -Math.atan2(c[2] - a[2], c[0] - a[0]);
    }

    // Pitched / Sawtooth / Skylight Roof Planes (3D sloped roof surfaces)
    if (Array.isArray(roof.planes) && roof.planes.length > 0) {
      for (const pl of roof.planes) {
        const poly = pl.polygon ?? [];
        if (poly.length < 3) continue;
        const tiltRad = ((Number(pl.tilt_deg) || 0) * Math.PI) / 180;
        const azRad = ((Number(pl.azimuth_deg) || 180) * Math.PI) / 180;
        const downSlope = [Math.sin(azRad), -Math.cos(azRad)];
        const proj = poly.map(([px, py]) => px * downSlope[0] + py * downSlope[1]);
        const maxProj = Math.max(...proj);
        const eaveZ = Number(pl.eave_height_m) || h;
        const pts3d = poly.map(([px, py], idx) => {
          const z = eaveZ + Math.max(0, maxProj - proj[idx]) * Math.tan(tiltRad);
          const [tx, ty] = transformPt([px, py], b);
          return world([tx, ty, z + 0.06]);
        });
        const posArr = [];
        for (let i = 1; i < pts3d.length - 1; i++) {
          posArr.push(...pts3d[0], ...pts3d[i], ...pts3d[i + 1]);
        }
        const pGeom = new T.BufferGeometry();
        pGeom.setAttribute('position', new T.Float32BufferAttribute(posArr, 3));
        pGeom.computeVertexNormals();
        const surfColor = pl.surface === 'glass' ? '#7ec8f2' : pl.surface === 'metal' ? '#607d94' : '#cbd5e1';
        const pMat = mat(surfColor, {
          side: T.DoubleSide,
          roughness: pl.surface === 'glass' ? 0.2 : 0.55,
          metalness: pl.surface === 'metal' ? 0.35 : 0.15,
          transparent: pl.surface === 'glass',
          opacity: pl.surface === 'glass' ? 0.72 : 1.0,
        });
        const pMesh = addMesh(pGeom, pMat, [0, 0, 0]);
        pMesh.userData.buildingTemplate = b.template;
        pMesh.userData.buildingName = b.name;
        buildingMeshes.push(pMesh);
      }
    }

    // Rooftop obstacles (HVAC, skylights, exhaust stacks, penthouses)
    for (const obs of roof.obstacles ?? []) {
      const oh = Math.max(0.4, Number(obs.height_m) || 1.5);
      if (obs.kind === 'cylinder' && obs.center) {
        const tc = transformPt(obs.center, b);
        const wp = world([tc[0], tc[1], 0]);
        const r = Math.max(0.4, Number(obs.radius_m) || 0.9);
        addMesh(new T.CylinderGeometry(r * 0.85, r, oh, 18), mat('#94a3b8', { metalness: 0.3 }), [wp[0], h + oh / 2, wp[2]]);
        addMesh(new T.ConeGeometry(r * 1.1, 0.35, 18), mat('#334155'), [wp[0], h + oh + 0.15, wp[2]]);
      } else if (obs.footprint?.length >= 3) {
        const tfp = obs.footprint.map(pt => transformPt(pt, b));
        const isSkylight = oh <= 1.05 || String(obs.label ?? '').includes('天窗');
        addExtrudedPolygon(tfp, oh, h, isSkylight ? '#60a5fa' : '#cbd5e1', {
          roughness: isSkylight ? 0.25 : 0.5,
          metalness: 0.25,
        });
      }
    }

    // Designed PV Modules on this building (supports both 3D corners and 2D corners)
    const panels3d = b.result?.panels_3d;
    const panels = (panels3d?.length ? panels3d : b.result?.panels) ?? [];
    if (panels.length > 0) {
      designedCount++;
      totalPanels += panels.length;
      const phase = b.result?.park_phase;
      const panelColor = colorByPhase
        ? (phase === 1 ? '#059669' : phase === 2 ? '#d97706' : '#1e3a8a')
        : '#1e3a8a';
      const panelMat = mat(panelColor, { roughness: 0.35, metalness: 0.35 });

      const inst = new T.InstancedMesh(new T.BoxGeometry(1, 0.08, 1), panelMat, panels.length);
      inst.castShadow = true;
      inst.receiveShadow = true;
      panels.forEach((corners, idx) => {
        const tc = corners.map(pt => [...transformPt([pt[0], pt[1]], b), pt[2]]);
        const cx = tc.reduce((s, p) => s + p[0], 0) / tc.length;
        const cy = tc.reduce((s, p) => s + p[1], 0) / tc.length;
        const hasZ = Number.isFinite(tc[0]?.[2]);
        const cz = hasZ ? (tc.reduce((s, p) => s + p[2], 0) / tc.length + 0.18) : (h + 0.48);
        const wp = world([cx, cy, cz]);
        const w = Math.max(0.8, Math.hypot(tc[1][0] - tc[0][0], tc[1][1] - tc[0][1]));
        const d = Math.max(0.8, Math.hypot(tc[3][0] - tc[0][0], tc[3][1] - tc[0][1], hasZ ? (tc[3][2] - tc[0][2]) : 0));
        const yaw = -Math.atan2(-(tc[1][1] - tc[0][1]), tc[1][0] - tc[0][0]);
        const dz = hasZ ? (tc[2][2] - tc[0][2]) : 0;
        const pitch = hasZ ? Math.asin(Math.max(-0.85, Math.min(0.85, dz / Math.max(0.8, d)))) : 0.22;
        const dummy = new T.Object3D();
        dummy.position.set(wp[0], wp[1], wp[2]);
        dummy.rotation.y = yaw;
        dummy.rotation.x = pitch;
        dummy.scale.set(w, 1, d);
        dummy.updateMatrix();
        inst.setMatrixAt(idx, dummy.matrix);
      });
      group.add(inst);
    }

    // Floating 3D Building Label Sprite
    const bxs = transformedOutline.map(p => p[0]), bys = transformedOutline.map(p => p[1]);
    const bcx = (Math.min(...bxs) + Math.max(...bxs)) / 2;
    const bcy = (Math.min(...bys) + Math.max(...bys)) / 2;
    const bSpan = Math.max(24, Math.max(...bxs) - Math.min(...bxs), Math.max(...bys) - Math.min(...bys));
    const bWorldCenter = world([bcx, bcy, h * 0.55]);
    buildingTargets.push({
      template: b.template,
      name: b.name || b.template,
      center: bWorldCenter,
      roofY: h,
      span: bSpan,
      result: b.result || null,
    });
    const labelPos = world([bcx, bcy, h + 5.5]);
    const lc = document.createElement('canvas');
    lc.width = 384;
    lc.height = 96;
    const ctx = lc.getContext('2d');
    ctx.fillStyle = 'rgba(15, 23, 42, 0.86)';
    ctx.fillRect(8, 8, 368, 80);
    ctx.strokeStyle = b.result ? (b.result.park_phase === 1 ? '#10b981' : '#f59e0b') : '#64748b';
    ctx.lineWidth = 4;
    ctx.strokeRect(8, 8, 368, 80);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 24px "Microsoft YaHei", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(String(b.name || b.template).slice(0, 14), 192, 42);
    ctx.fillStyle = '#93c5fd';
    ctx.font = '20px "Microsoft YaHei", sans-serif';
    const subText = b.result
      ? `${Number(b.result.dc_kw || 0).toFixed(1)} kWp · ${b.result.park_phase === 1 ? '一期优先' : '二期扩建'} · 回本${Number(b.result.payback_years || 0).toFixed(1)}年`
      : `檐高 ${h}m · 待运行批量设计`;
    ctx.fillText(subText, 192, 72);
    const sprite = new T.Sprite(new T.SpriteMaterial({ map: new T.CanvasTexture(lc), depthTest: false }));
    sprite.position.set(labelPos[0], labelPos[1], labelPos[2]);
    sprite.scale.set(Math.max(14, span * 0.14), Math.max(3.5, span * 0.035), 1);
    group.add(sprite);
  }

  const groundPlane = new T.Plane(new T.Vector3(0, 1, 0), -4);
  let glideTarget = null;
  let glideCamOffset = null;

  function updateHud(extraMsg = '') {
    const baseText = `园区 3D 全景数字孪生沙盘 · 共 ${buildings.length} 栋厂房（已出方案 ${designedCount} 栋 / 合计 ${totalPanels} 块光伏板）· 按住厂房旋转 / 按住地面或右键滑动平移 / 滚轮指哪缩哪`;
    hud.textContent = extraMsg ? `${baseText} · ${extraMsg}` : baseText;
  }

  function cursorWorldPoint(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    pointer.set(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects([...buildingMeshes, ground], false)[0];
    if (hit?.point) return { point: hit.point.clone(), object: hit.object };
    const fallbackPt = new T.Vector3();
    groundPlane.constant = -Math.max(0, controls.target.y);
    if (raycaster.ray.intersectPlane(groundPlane, fallbackPt)) {
      return { point: fallbackPt, object: null };
    }
    return null;
  }

  function startGlideTo(targetPt, desiredDistance = null) {
    const offset = camera.position.clone().sub(controls.target);
    if (desiredDistance != null && offset.length() > 1e-3) {
      offset.setLength(Math.max(12, Math.min(span * 4, desiredDistance)));
    }
    glideTarget = new T.Vector3(
      Math.max(-span * 1.6, Math.min(span * 1.6, targetPt.x)),
      Math.max(0.5, Math.min(45, targetPt.y)),
      Math.max(-span * 1.6, Math.min(span * 1.6, targetPt.z))
    );
    glideCamOffset = offset;
  }

  function focusBuilding(tpl) {
    const item = buildingTargets.find(b => b.template === tpl);
    if (!item) return;
    const [tx, ty, tz] = item.center;
    const curDist = camera.position.distanceTo(controls.target);
    const targetDist = Math.min(curDist, Math.max(36, item.span * 1.25));
    startGlideTo(new T.Vector3(tx, ty, tz), targetDist);
    updateHud(`已聚焦【${item.name}】`);
  }

  function setCameraView(preset = 'iso') {
    glideTarget = null;
    glideCamOffset = null;
    controls.target.set(0, 4, 0);
    if (preset === 'top') {
      camera.position.set(0, span * 1.45, 0.01);
    } else if (preset === 'south') {
      camera.position.set(0, span * 0.48, span * 1.15);
    } else {
      camera.position.set(span * 0.72, span * 0.68, span * 0.88);
    }
    controls.minDistance = 5;
    controls.maxDistance = span * 6;
    controls.update();
    updateHud();
  }

  setCameraView('iso');
  sun.position.set(span * 0.8, span * 1.4, span * 0.6);
  Object.assign(sun.shadow.camera, { left: -span, right: span, top: span, bottom: -span, near: 1, far: span * 4 });
  sun.shadow.camera.updateProjectionMatrix();

  const raycaster = new T.Raycaster(), pointer = new T.Vector2();
  let downPt = null;
  canvas.addEventListener('pointerdown', e => {
    downPt = [e.clientX, e.clientY];
    glideTarget = null;
    glideCamOffset = null;
    if (e.button === 0 && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
      const rect = canvas.getBoundingClientRect();
      if (rect.width && rect.height) {
        pointer.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
        raycaster.setFromCamera(pointer, camera);
        const bldgHit = raycaster.intersectObjects(buildingMeshes, false)[0];
        if (bldgHit) {
          if (T.MOUSE) controls.mouseButtons.LEFT = T.MOUSE.ROTATE;
          const tpl = bldgHit.object?.userData?.buildingTemplate;
          const item = tpl && buildingTargets.find(b => b.template === tpl);
          if (item) {
            const bPt = new T.Vector3(...item.center);
            if (bPt.distanceTo(controls.target) > span * 0.22) {
              const delta = bPt.clone().sub(controls.target).multiplyScalar(0.42);
              delta.y = 0;
              controls.target.add(delta);
              camera.position.add(delta);
            }
          }
        } else {
          // Pressing and sliding on ground / road / blank space slides (pans) the 3D park directly
          if (T.MOUSE) controls.mouseButtons.LEFT = T.MOUSE.PAN;
        }
      }
    }
  }, { capture: true });

  // Single-click any building or ground spot: smoothly glide the 3D rotation center to that building/spot
  canvas.addEventListener('click', e => {
    if (!downPt || Math.hypot(e.clientX - downPt[0], e.clientY - downPt[1]) > 5) return;
    const hit = cursorWorldPoint(e.clientX, e.clientY);
    if (!hit) return;
    const tpl = hit.object?.userData?.buildingTemplate;
    if (tpl) {
      focusBuilding(tpl);
    } else if (hit.point) {
      startGlideTo(new T.Vector3(hit.point.x, Math.max(2, controls.target.y), hit.point.z));
    }
  });

  // Double-click a building to enter its single-building 3D workbench, or double-click ground to zoom in there
  canvas.addEventListener('dblclick', e => {
    const hit = cursorWorldPoint(e.clientX, e.clientY);
    if (!hit) return;
    const tpl = hit.object?.userData?.buildingTemplate;
    if (tpl && options.onSelectBuilding) {
      options.onSelectBuilding(tpl);
    } else if (hit.point) {
      const curDist = camera.position.distanceTo(controls.target);
      startGlideTo(hit.point, Math.max(18, curDist * 0.62));
    }
  });

  // Direct mouse-wheel zoom-to-cursor + horizontal touchpad slide
  canvas.addEventListener('wheel', e => {
    glideTarget = null;
    glideCamOffset = null;
    if (Math.abs(e.deltaX) > Math.abs(e.deltaY) && Math.abs(e.deltaX) > 2) {
      const forward = new T.Vector3();
      camera.getWorldDirection(forward);
      forward.y = 0;
      if (forward.lengthSq() > 1e-4) {
        forward.normalize();
        const right = new T.Vector3().crossVectors(forward, new T.Vector3(0, 1, 0)).normalize();
        const step = Math.max(0.05, camera.position.distanceTo(controls.target) * 0.0015) * e.deltaX;
        const delta = right.multiplyScalar(step);
        controls.target.add(delta);
        camera.position.add(delta);
      }
      return;
    }
    const hit = cursorWorldPoint(e.clientX, e.clientY);
    if (e.deltaY < 0 && hit?.point) {
      const shift = hit.point.clone().sub(controls.target).multiplyScalar(0.28);
      shift.y = (Math.max(2, Math.min(25, hit.point.y)) - controls.target.y) * 0.25;
      controls.target.add(shift);
      camera.position.add(shift);
    } else if (e.deltaY > 0) {
      const dist = camera.position.distanceTo(controls.target);
      if (dist > span * 0.75) {
        const home = new T.Vector3(0, 4, 0);
        const shift = home.sub(controls.target).multiplyScalar(0.16);
        controls.target.add(shift);
        camera.position.add(shift);
      }
    }
  }, { passive: true });

  let disposed = false, raf = null;
  const resize = new ResizeObserver(() => {
    const { width, height } = container.getBoundingClientRect();
    if (width && height) {
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }
  });
  resize.observe(container);

  function animate() {
    if (disposed) return;
    raf = requestAnimationFrame(animate);
    if (glideTarget && glideCamOffset) {
      controls.target.lerp(glideTarget, 0.2);
      const desiredCam = glideTarget.clone().add(glideCamOffset);
      camera.position.lerp(desiredCam, 0.2);
      if (controls.target.distanceTo(glideTarget) < 0.15) {
        glideTarget = null;
        glideCamOffset = null;
      }
    }
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  return {
    setCameraView,
    focusBuilding,
    dispose() {
      if (disposed) return;
      disposed = true;
      cancelAnimationFrame(raf);
      resize.disconnect();
      controls.dispose();
      renderer.dispose();
    },
  };
}

