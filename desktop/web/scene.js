import { normalizeScene, panelMatrix, solarPosition, heatColor, stringColor, pileContact } from './scene-data.js';
import { createWiring } from './scene-wiring.js';
import { batchStatic } from './scene-static.js';
import { createFacade, facadeSettings } from './scene-facade.js';
import { normalizeView, viewDirection, sceneFramePoints, resizeCamera, fitCamera, changeProjection } from './scene-camera.js';
import { createModuleTransform } from './scene-module-transform.js';
import { buildObstacleModel, buildSurroundingModel, buildSynergySceneDetails } from './scene-models.js';
import { createSolarPanelTintTexture } from './pro-3d-twin-engine.js';

// A preview may deliberately reuse a version number. Its inherited analyses still
// describe the saved geometry, so version equality alone cannot make them current.
export function normalizeSceneForDisplay(input) {
  const data = normalizeScene(input.edit_preview ? { ...input, shading: null, electrical: null, wind: null } : input);
  const parent = input.parent_design && (input.edit_preview || input.parent_design.version === input.design.parent_version) ? input.parent_design : null;
  const before = new Map((parent?.modules ?? []).map(module => [module.id, module]));
  const samePoint = (a, b) => a?.length === b?.length && a.every((value, axis) => Math.abs(value - b[axis]) <= 1e-7);
  const changed = data.modules.filter(module => {
    const previous = before.get(module.id);
    return previous && (!samePoint(module.center, previous.center) ||
      module.corners.some((point, index) => !samePoint(point, previous.corners[index])));
  });
  const isFullRelayout = !input.edit_preview && input.design?.author === 'agent' && changed.length > 10 && changed.length >= data.modules.length * 0.5;
  const visibleChanged = isFullRelayout ? [] : changed;
  data.changed = new Set(visibleChanged.map(module => module.id));
  data.previousPositions = visibleChanged.map(module => {
    const previous = before.get(module.id);
    return { ...previous, position: data.world(previous.center), points: previous.corners.map(data.world) };
  });
  if (input.edit_preview && parent) {
    const ids = new Set(data.modules.map(module => module.id));
    data.added = new Set(data.modules.filter(module => !before.has(module.id)).map(module => module.id));
    data.removed = parent.modules.filter(module => !ids.has(module.id))
      .map(module => ({ ...module, position: data.world(module.center), points: module.corners.map(data.world) }));
  }
  return data;
}

export function createScene(container, options = {}) {
  const T = globalThis.THREE, canvas = document.createElement('canvas'), note = document.createElement('div'), differenceNote = document.createElement('div');
  container.classList.add('scene-view'); note.className = 'scene-note'; note.hidden = true;
  differenceNote.className = 'scene-note'; differenceNote.hidden = true;
  container.replaceChildren(canvas, note, differenceNote);
  let renderer, disposed = false, data, panels, group, mode = 'light', theme = 'light', frame, highlight, draws = 0;
  let date = `${new Date().getFullYear()}-12-21`, hour = 12, sunValue, needsShadow = true;
  let wiring, windZones, facade, moduleTransform, selectedString = '', pointerStart, view = 'iso', moved = false, focusedModuleIds = [];
  let modelMeshes = [];
  let selectedModules = new Set();
  let lockedModules = new Set();
  let selectedRoofPlanes = new Set();
  let selectedObjects = new Map();
  let measureMode = false, measureStart = null, measureLine = null;
  function unavailable(message = '此设备无法显示 3D。设计指标和文件仍可查看。') {
    moduleTransform?.cancel();
    note.textContent = message; note.hidden = false; note.className = 'scene-unavailable'; canvas.hidden = true;
    options.onUnavailable?.(message);
  }
  const noop = () => { }, fallback = {
    setData: noop, setMode: noop, setSun: noop, setTheme: noop, selectString: noop, highlightModules: noop, highlightRoofPlanes: noop,
    highlightObjects: noop, focusObjects: noop, focusModules: noop, setModuleEditing: noop, setMeasureMode: noop, setProjection: noop, getViewState: () => null, setViewState: noop, resetView: noop,
    panBy: noop, setNavMode: noop, getNavMode: () => 'orbit',
    stats: () => ({ available: false }), dispose: () => container.replaceChildren()
  };
  if (!T?.OrbitControls) { unavailable(); return fallback; }
  try {
    const context = canvas.getContext('webgl2', { antialias: true }) || canvas.getContext('webgl', { antialias: true });
    if (!context) { unavailable(); return fallback; }
    renderer = new T.WebGLRenderer({ canvas, context, antialias: true });
  } catch { unavailable(); return fallback; }
  differenceNote.style.top = '12px'; differenceNote.style.bottom = 'auto';
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2)); renderer.outputEncoding = T.sRGBEncoding;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFSoftShadowMap; renderer.shadowMap.autoUpdate = false;
  const scene = new T.Scene();
  let camera = new T.PerspectiveCamera(42, 1, .1, 2000);
  const controls = new T.OrbitControls(camera, canvas); controls.enableDamping = true; controls.maxPolarAngle = Math.PI / 2;
  controls.enablePan = true; controls.panSpeed = 1.45; controls.screenSpacePanning = false;
  let navMode = 'orbit';
  function setNavMode(nextMode = 'orbit') {
    navMode = nextMode === 'pan' ? 'pan' : 'orbit';
    if (T.MOUSE) {
      controls.mouseButtons = {
        LEFT: navMode === 'pan' ? T.MOUSE.PAN : T.MOUSE.ROTATE,
        MIDDLE: T.MOUSE.DOLLY,
        RIGHT: T.MOUSE.PAN,
      };
    }
  }
  function getNavMode() { return navMode; }
  function panBy(dx, dz) {
    if (!data) return;
    const forward = new T.Vector3();
    camera.getWorldDirection(forward);
    forward.y = 0;
    if (forward.lengthSq() < 1e-4) forward.set(0, 0, -1);
    forward.normalize();
    const right = new T.Vector3().crossVectors(forward, new T.Vector3(0, 1, 0)).normalize();
    const step = Math.max(2.5, Math.min(25, camera.position.distanceTo(controls.target) * 0.18));
    const delta = new T.Vector3().addScaledVector(right, dx * step).addScaledVector(forward, dz * step);
    camera.position.add(delta);
    controls.target.add(delta);
    moved = true;
    controls.update();
  }
  const ambient = new T.HemisphereLight(0xffffff, 0x6f675b, .6), sun = new T.DirectionalLight(0xffefcf, 1.1);
  sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); sun.shadow.normalBias = .025; sun.shadow.bias = -.0002;
  scene.add(ambient, sun, sun.target);
  const raycaster = new T.Raycaster(), pointer = new T.Vector2();
  const linear = color => new T.Color(color).convertSRGBToLinear();
  const material = (color, extra = {}) => new T.MeshStandardMaterial({ color: linear(color), roughness: .78, ...extra });
  function mesh(geometry, mat, position = [0, 0, 0]) {
    const object = new T.Mesh(geometry, mat); object.position.fromArray(position); object.castShadow = true; object.receiveShadow = true; group.add(object); return object;
  }
  function release() {
    if (!group) return;
    group.traverse(object => {
      object.geometry?.dispose();
      const mats = Array.isArray(object.material) ? object.material : [object.material];
      for (const mat of mats) { mat?.map?.dispose(); mat?.dispose(); }
      for (const mat of object.userData.panelMaterials ?? []) if (!mats.includes(mat)) mat.dispose();
    });
    scene.remove(group);
    group = null;
    panels = null;
    wiring = null;
    windZones = null;
    facade = null;
    modelMeshes = [];
    renderer.renderLists.dispose();
  }
  function polygon(points, height, base, color, extra = {}) {
    if (!points?.length) return;
    const shape = new T.Shape(points.map(([x, y]) => new T.Vector2(x - data.center[0], y - data.center[1])));
    const geometry = new T.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false }); geometry.rotateX(-Math.PI / 2);
    if (data.roof.type === 'metal' && (base >= data.roof.height_m || height === data.roof.height_m)) {
      const vertices = geometry.attributes.position;
      for (let i = 0; i < vertices.count; i++) {
        if (base || vertices.getY(i) > 0) {
          const p = [vertices.getX(i) + data.center[0], -vertices.getZ(i) + data.center[1]];
          vertices.setY(i, vertices.getY(i) + data.elevation(p));
        }
      }
      geometry.computeVertexNormals();
    }
    return mesh(geometry, material(color, extra), [0, base, 0]);
  }
  function surface(points, color, extra = {}, wall = false) {
    const triangles = wall ? (points.length === 3 ? [[0, 2, 1]] : [[0, 2, 1], [0, 3, 2]]) :
      T.ShapeUtils.triangulateShape(points.map(p => new T.Vector2(p[0], p[1])), []);
    const coordinates = triangles.flatMap(indices => indices.flatMap(i => data.world(points[i])));
    const geometry = new T.BufferGeometry();
    geometry.setAttribute('position', new T.Float32BufferAttribute(coordinates, 3));
    geometry.computeVertexNormals();
    return mesh(geometry, material(color, { side: T.FrontSide, ...extra }));
  }
  function instances(modules) {
    if (!modules.length) return null;
    const panelTex = createSolarPanelTintTexture(T);
    const stdMat = material('#ffffff', { roughness: .26, metalness: .28, ...(panelTex ? { map: panelTex } : {}) });
    const flatMat = new T.MeshBasicMaterial({ color: 0xffffff, ...(panelTex ? { map: panelTex } : {}) });
    const object = new T.InstancedMesh(new T.BoxGeometry(1, 1, 1), stdMat, modules.length);
    object.userData.panelMaterials = [stdMat, flatMat];
    modules.forEach((module, i) => object.setMatrixAt(i, new T.Matrix4().fromArray(panelMatrix(module))));
    object.castShadow = true; object.receiveShadow = true; object.frustumCulled = false; group.add(object); return object;
  }
  function moduleOutlines(modules, color, kind) {
    if (!modules.length) return;
    // Exact parent-version edges, with no translucent faces competing with current panel depth.
    // Treat them as an annotation overlay so crossing current panels never creates z-fighting.
    const vertices = modules.flatMap(module => module.points.flatMap((point, i) => [...point, ...module.points[(i + 1) % 4]]));
    const geometry = new T.BufferGeometry();
    geometry.setAttribute('position', new T.Float32BufferAttribute(vertices, 3));
    const object = new T.LineSegments(geometry, new T.LineBasicMaterial({ color: linear(color), transparent: true, opacity: .9, depthTest: false, depthWrite: false }));
    object.userData[kind + 'OutlineCount'] = modules.length;
    object.renderOrder = 10;
    group.add(object);
  }
  function showDifferences() {
    moduleOutlines(data.removed, '#d1493f', 'removed');
    moduleOutlines(data.previousPositions, '#e99b34', 'previous');
    const current = data.modules.filter(module => data.changed.has(module.id) || data.edit_preview && data.added.has(module.id));
    moduleOutlines(current, '#39cf87', 'candidate');
    const labels = [];
    if (data.edit_preview) {
      labels.push('候选预览 · 尚未保存；年度热力、组串和风荷载暂不显示');
      if (data.added.size) labels.push(`绿色边框：新增 ${data.added.size} 块`);
    }
    if (data.changed.size) labels.push(`绿色边框：移动/旋转后的 ${data.changed.size} 块；橙色边框：原位置`);
    if (data.removed.length) labels.push(`红色边框：相对 v${data.parent_design.version} 移除的 ${data.removed.length} 块组件`);
    differenceNote.textContent = labels.join('\n');
    differenceNote.hidden = !labels.length;
  }
  function followRoof(object) {
    if (data.roof.type !== 'metal') {
      return;
    }
    object.updateMatrixWorld();
    const vertices = object.geometry.attributes.position, p = new T.Vector3();
    for (let i = 0; i < vertices.count; i++) {
      p.fromBufferAttribute(vertices, i).applyMatrix4(object.matrixWorld);
      vertices.setY(i, vertices.getY(i) + data.elevation([p.x + data.center[0], data.center[1] - p.z]));
    }
    object.geometry.computeVertexNormals();
  }
  function recolor(flash = false) {
    const dragging = Boolean(moduleTransform?.isDragging());
    const displayMode = data?.edit_preview || dragging ? 'light' : mode;
    for (const object of group?.children ?? []) if (['removed', 'previous', 'candidate'].some(kind => object.userData[kind + 'OutlineCount'])) object.visible = !dragging;
    differenceNote.hidden = !data || dragging || !differenceNote.textContent;
    wiring?.setMode(displayMode);
    if (!panels) return;
    panels.material = panels.userData.panelMaterials[displayMode === 'light' ? 0 : 1];
    data.modules.forEach((m, i) => {
      const editing = data.edit_preview && (data.added.has(m.id) || data.changed.has(m.id));
      const color = editing || flash && data.added.has(m.id) ? '#4fc58a' : displayMode === 'heat' ? heatColor(m.loss, data.threshold) : displayMode === 'string' ? stringColor(m.string?.id) : theme === 'dark' ? '#3b5f9c' : '#1f3a66';
      const windColor = { corner: '#c94e42', edge: '#d79935', middle: '#368c90' }[m.wind?.zone] ?? '#777777';
      const wireColor = selectedString && m.string?.id !== selectedString ? '#afb4b9' : stringColor(m.string?.id);
      const finalColor = displayMode === 'wiring' ? wireColor : displayMode === 'wind' ? windColor :
        displayMode === 'phase' && m.phase ? (m.phase === 1 ? '#2a9d63' : '#c87743') : color;
      panels.setColorAt(i, linear(selectedModules.has(m.id) ? '#299b82' : lockedModules.has(m.id) ? '#cf943b' : finalColor));
    });
    if (windZones) windZones.visible = displayMode === 'wind';
    if (displayMode === 'wind') {
      const zones = data.wind?.zones ?? {}, count = key => zones[key]?.modules ?? 0;
      note.textContent = data.wind ? `角区（红）${count('corner')} 块 · 边区（黄）${count('edge')} 块 · 中区（青）${count('middle')} 块` +
        (data.wind.anchor_count ? `；${data.wind.anchored_modules} 块改用 ${data.wind.anchor_count} 个锚栓` : '') + '；示意，施工前结构复核' :
        '此版本未计算风荷载';
      note.hidden = false;
    } else {
      note.hidden = true;
    }
    panels.instanceColor.needsUpdate = true;
  }
  function setSun(nextDate = date, nextHour = hour) {
    date = nextDate; hour = Number(nextHour);
    if (!data) return;
    sunValue = solarPosition(data.project.site.lat, data.project.site.lon, date, hour);
    sun.position.fromArray(sunValue.direction).multiplyScalar(data.span * 2).add(sun.target.position);
    sun.intensity = sunValue.altitude > 0 ? 1.1 : 0; needsShadow = true; options.onSun?.(sunValue); return sunValue;
  }
  function setTheme(value) {
    theme = value || (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
    scene.background = new T.Color(theme === 'dark' ? '#171411' : '#f4ece3');
    if (group) for (const object of group.children) if (object.userData.surface) object.material.color.copy(linear(theme === 'dark' ? '#51463b' : '#d8cbbb'));
    recolor();
  }
  function highlightRoofPlanes(ids = []) {
    selectedRoofPlanes = new Set(ids);
    highlightSelections();
  }
  const objectKey = value => `${value.kind}/${value.id}`;
  function identify(object, kind, id) {
    if (object && id != null) object.userData.sceneObject = { kind, id };
    return object;
  }
  function highlightSelections() {
    for (const object of group?.children ?? []) {
      if (object.userData.roofPlane == null && !object.userData.sceneObject) continue;
      const chosen = selectedRoofPlanes.has(object.userData.roofPlane) || object.userData.sceneObject && selectedObjects.has(objectKey(object.userData.sceneObject));
      object.material.emissive?.copy(linear(chosen ? '#66300c' : '#000000'));
    }
  }
  function highlightObjects(values = []) {
    selectedObjects = new Map(values.filter(value => ['item', 'part'].includes(value?.kind) && value.id != null).map(value => [objectKey(value), value]));
    highlightSelections();
  }
  function setData(input, { preserveView = false } = {}) {
    if (disposed) return;
    const retainView = preserveView && !!data;
    moduleTransform?.setData(null);
    clearTimeout(highlight); release(); note.hidden = true; differenceNote.hidden = true; canvas.hidden = false;
    note.className = 'scene-note';
    if (!input?.project?.roof?.outline?.length || !input?.design?.modules) {
      data = null; unavailable('此记录缺少屋顶或组件几何，暂不能显示 3D。'); return;
    }
    const valid = p => Array.isArray(p) && p.length >= 3 && p.every(Number.isFinite);
    if (!Array.isArray(input.design.modules) || input.design.modules.some(m =>
      !valid(m.center) || m.corners?.length !== 4 || !m.corners.every(valid))) {
      data = null;
      unavailable('此版本组件几何不完整，请换一个版本；设计指标和文件仍可查看。');
      return;
    }
    data = normalizeSceneForDisplay(input); group = new T.Group(); scene.add(group);
    focusedModuleIds = focusedModuleIds.filter(id => data.modules.some(module => module.id === id));
    const { roof, span } = data, ground = mesh(new T.PlaneGeometry(span * 5, span * 5), material('#d8cbbb'));
    ground.rotation.x = -Math.PI / 2; ground.position.y = -.03; ground.userData.surface = true;
    if (['ground', 'carport'].includes(roof.type)) {
      const facts = input.facilities;
      if (!facts) {
        unavailable('此记录缺少新建场地实体，请重新打开记录。');
        return;
      }
      const line = (points, color) => group.add(new T.Line(
        new T.BufferGeometry().setFromPoints(points.map(p => new T.Vector3(...data.world(p)))),
        new T.LineBasicMaterial({ color })));
      for (const road of facts.roads ?? []) polygon(road, .015, .01, '#b0aca2');
      for (const fence of facts.fence ?? []) {
        line(fence.map(p => [...p, 1.5]), 0x6b7861);
        line(fence.map(p => [...p, .1]), 0x6b7861);
        for (const p of fence) line([[...p, 0], [...p, 1.5]], 0x6b7861);
      }
      const byId = new Map(data.modules.map(panel => [panel.id, panel]));
      for (const pile of facts.piles ?? []) {
        const p = data.world(pile.point), height = pile.top_m;
        const contact = pileContact(pile, pile.modules.map(id => byId.get(id)).filter(Boolean));
        const geometry = new T.CylinderGeometry(.07, .07, height, 12), vertices = geometry.attributes.position;
        for (let i = 0; i < vertices.count; i++) {
          if (vertices.getY(i) > 0) {
            const delta = contact.dx * vertices.getX(i) - contact.dy * vertices.getZ(i) - contact.inset;
            vertices.setY(i, vertices.getY(i) + delta);
          }
        }
        geometry.computeVertexNormals();
        mesh(geometry, material('#77858b'), [p[0], height / 2, p[2]]);
        if (pile.rail) line(pile.rail, 0x899397);
      }
      if (roof.type === 'ground') {
        for (const panel of data.modules) line([panel.corners[0], panel.corners[3]], 0x899397);
      }
      for (const face of facts.faces ?? []) surface(face.points, '#aab8c8', { side: T.DoubleSide });
      for (const beam of facts.beams ?? []) {
        const bottom = beam.points.map(p => [p[0], p[1], p[2] - beam.depth_m]);
        surface(bottom, '#77858b', { side: T.DoubleSide });
        for (let i = 0; i < bottom.length; i++) {
          const j = (i + 1) % bottom.length;
          surface([bottom[i], bottom[j], beam.points[j], beam.points[i]], '#77858b', { side: T.DoubleSide }, true);
        }
      }
      for (const column of facts.columns ?? []) {
        const p = data.world(column.point), height = column.top_m;
        mesh(new T.CylinderGeometry(.1, .1, height, 16), material('#77858b'), [p[0], height / 2, p[2]]);
      }
      for (const bay of facts.bays ?? []) line([...bay.polygon, bay.polygon[0]].map(p => [...p, .025]), 0xffffff);
    }
    if (roof.type === 'pitched') {
      const geometry = input.roof_geometry;
      if (!geometry) {
        unavailable('此记录缺少整栋坡面渲染数据，请重新打开该设计记录。');
        return;
      }
      for (const face of geometry.faces) {
        const glass = face.material === 'glass';
        const object = surface(face.points, glass ? '#70bfd1' : face.material === 'concrete' ? '#c9bcac' : '#aab8c8',
          glass ? { transparent: true, opacity: .48, depthWrite: false, side: T.DoubleSide } : {});
        object.userData.roofPlane = face.id;
        if (face.part_id != null) identify(object, 'part', face.part_id);
        const border = [...face.points, face.points[0]].map(p => new T.Vector3(...data.world(p)));
        group.add(new T.Line(new T.BufferGeometry().setFromPoints(border), new T.LineBasicMaterial({ color: 0x526174 })));
      }
      const exterior = facadeSettings(roof);
      for (const wall of geometry.walls) {
        const object = surface(wall, exterior.enabled ? exterior.wall_color : '#d8cbbb', { side: T.DoubleSide }, true);
        object.userData.buildingWall = true;
        if (!exterior.enabled) object.userData.surface = true;
      }
      if (geometry.keepout_faces) {
        for (const face of geometry.keepout_faces) identify(surface(face.points, '#60a5b5', { transparent: true, opacity: .62 }), 'item', face.id);
      } else for (const points of geometry.keepouts) surface(points, '#60a5b5', { transparent: true, opacity: .62 });
    } else if (!['ground', 'carport'].includes(roof.type)) polygon(roof.outline, roof.height_m, 0, '#d8cbbb').userData.surface = true;
    if (Object.prototype.hasOwnProperty.call(input.roof_geometry ?? {}, 'parapets')) {
      // An empty authoritative list means real gaps/no walls; never rebuild a full perimeter.
      for (const face of input.roof_geometry.parapets) {
        surface(face, '#c3b7a8', { side: T.DoubleSide }, true).userData.parapet = true;
      }
    } else if (roof.type === 'pitched') {
      const boundary = input.roof_geometry.boundary;
      for (let i = 0; roof.parapet_height_m && i < boundary.length - 1; i++) {
        const a = boundary[i], b = boundary[i + 1];
        if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-9) continue;
        surface([a, b, [...b.slice(0, 2), b[2] + roof.parapet_height_m], [...a.slice(0, 2), a[2] + roof.parapet_height_m]],
          '#c3b7a8', { side: T.DoubleSide }, true).userData.parapet = true;
      }
    } else for (let i = 0; roof.parapet_height_m && i < roof.outline.length; i++) {
      const a = data.world(roof.outline[i]), b = data.world(roof.outline[(i + 1) % roof.outline.length]), length = Math.hypot(b[0] - a[0], b[2] - a[2]);
      const wall = mesh(new T.BoxGeometry(length, roof.parapet_height_m, .22), material('#c3b7a8'), [(a[0] + b[0]) / 2, roof.height_m + roof.parapet_height_m / 2, (a[2] + b[2]) / 2]);
      wall.rotation.y = -Math.atan2(b[2] - a[2], b[0] - a[0]); wall.userData.parapet = true; followRoof(wall);
    }
    const detailLine = (points, color = 0x5c5248) => group.add(new T.Line(
      new T.BufferGeometry().setFromPoints(points.map(p => new T.Vector3(...p))),
      new T.LineBasicMaterial({ color })));
    for (const obstacle of roof.obstacles ?? []) {
      const base = roof.type === 'pitched' ? input.roof_geometry.obstacle_bases[obstacle.id] : 0;
      buildObstacleModel(T, { obstacle, data, base, roof, mesh, polygon, material, detailLine, followRoof, identify });
    }
    for (const near of roof.surroundings ?? []) { // T19: buildings and trees stand on the ground and rise above the roof
      buildSurroundingModel(T, { near, data, roof, mesh, polygon, material, identify });
    }
    buildSynergySceneDetails(T, { input, data, roof, mesh, material });
    if (roof.type !== 'pitched') {
      for (const area of [...(roof.keepouts ?? []), ...(data.design.added_keepouts ?? [])]) {
        identify(polygon(area.polygon, .025, roof.height_m + .02, '#60a5b5', { transparent: true, opacity: .62 }), 'item', area.id);
      }
    }
    // Editor-only point identities do not exist in the persisted coordinate arrays.
    // These small location symbols are pickable annotations, with no physical shadows.
    for (const marker of input.editor_markers ?? []) {
      if (!Array.isArray(marker.point) || marker.point.length !== 2 || !marker.point.every(Number.isFinite)) continue;
      const radius = Math.max(.18, Math.min(.6, span * .006));
      const position = data.world([...marker.point, data.elevation(marker.point) + radius + .025]);
      const object = identify(mesh(new T.SphereGeometry(radius, 12, 8), material('#e8b548'), position), 'item', marker.id);
      object.castShadow = false; object.receiveShadow = false; object.userData.editorMarker = true;
    }
    facade = createFacade(T, data, input.roof_geometry);
    group.add(facade.group);
    batchStatic(T, group);
    // Snapshot physical surfaces before adding analysis overlays and direction labels.
    // Transparent roof glazing is physical; keepout paint and point markers are not.
    group.traverse(object => {
      if (object.isMesh && !object.userData.editorMarker &&
        (!object.material?.transparent || object.userData.roofPlane != null)) modelMeshes.push(object);
    });
    // Wind mode shows where the corner and edge zones lie on the deck (often left empty by the setback); kept out of the static batch.
    windZones = new T.Group();
    for (const [zone, color] of data.wind && roof.type !== 'pitched' ? [['corner', '#c94e42'], ['edge', '#d79935']] : []) {
      const shape = data.wind.regions?.[zone];
      for (const rings of shape?.type === 'MultiPolygon' ? shape.coordinates : shape?.type === 'Polygon' ? [shape.coordinates] : []) {
        const area = polygon(rings[0], .02, roof.height_m + .03, color, { transparent: true, opacity: .5, depthWrite: false });
        if (area) { area.castShadow = false; group.remove(area); windZones.add(area); }
      }
    }
    group.add(windZones);
    panels = instances(data.modules);
    showDifferences();
    recolor(true);
    if (data.project.requirements?.structured?.max_height_m != null) {
      const points = [...roof.outline, roof.outline[0]].map(p =>
        new T.Vector3(...data.world([p[0], p[1], data.elevation(p) + roof.parapet_height_m])));
      group.add(new T.Line(new T.BufferGeometry().setFromPoints(points), new T.LineBasicMaterial({ color: 0xd1493f, depthTest: false })));
    }
    wiring = createWiring(T, data, group);
    selectedString = wiring.select(selectedString);
    highlight = setTimeout(() => recolor(), 1500);
    const north = new T.ArrowHelper(new T.Vector3(0, 0, -1), new T.Vector3(-span * .58, .1, span * .4), span * .18, 0xc87743, span * .045, span * .025); group.add(north);
    const labelCanvas = document.createElement('canvas'); labelCanvas.width = 64; labelCanvas.height = 64;
    const ctx = labelCanvas.getContext('2d'); ctx.font = 'bold 44px sans-serif'; ctx.fillStyle = '#c87743'; ctx.textAlign = 'center'; ctx.fillText('N', 32, 48);
    const label = new T.Sprite(new T.SpriteMaterial({ map: new T.CanvasTexture(labelCanvas), depthTest: false })); label.position.set(-span * .58, 1, span * .17); label.scale.set(3, 3, 1); group.add(label);
    if (!retainView) resetView();
    sun.target.position.copy(controls.target);
    Object.assign(sun.shadow.camera, { left: -span, right: span, top: span, bottom: -span, near: .1, far: span * 5 }); sun.shadow.camera.updateProjectionMatrix();
    setTheme(theme); recolor(true); setSun(); highlightRoofPlanes([...selectedRoofPlanes]);
    moduleTransform?.setData(data);
  }
  function inspect(event) {
    if (!panels || canvas.hidden || moduleTransform?.isDragging()) return;
    const rect = canvas.getBoundingClientRect(); pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, camera); const hit = raycaster.intersectObject(panels)[0], m = hit && data.modules[hit.instanceId];
    note.hidden = !m; note.className = 'scene-note';
    if (!m) { options.onInspect?.(null); return; }
    const e = data.electrical, info = { module: m.id, version: data.design.version, loss: m.loss, string: m.string, voltages: e ? { voc_cold_v: e.voc_cold_v, vmp_hot_v: e.vmp_hot_v } : null };
    const num = value => Number.isFinite(value) ? value.toFixed(2) : '未提供';
    const cable = e?.cables?.dc?.find(row => row.id === m.string?.id);
    note.textContent = `${m.id} · ${data.edit_preview ? '候选预览' : 'v' + data.design.version}\n` +
      (data.edit_preview ? '当前预览未显示年度遮挡结果\n' : `年度遮挡损失 ${num(m.loss)}%\n`) +
      (m.string ? `${m.string.id} · MPPT ${m.string.mppt} · 串工作${num(cable?.voltage_v)}V · 压降${num(cable?.drop_pct)}%` : '未接入组串或缺少电气数据');
    options.onInspect?.(info);
  }
  const leave = () => { note.hidden = true; options.onInspect?.(null); };
  const lost = event => { event.preventDefault(); moduleTransform?.setData(null); cancelAnimationFrame(frame); unavailable('3D 显示已中断，请重新打开结果页。设计数据仍可查看。'); };
  const restored = () => {
    if (disposed || !data) return;
    canvas.hidden = false;
    note.className = 'scene-note';
    note.hidden = true;
    needsShadow = true;
    moduleTransform?.setData(data);
    cancelAnimationFrame(frame);
    draw();
  };
  const down = event => {
    pointerStart = [event.clientX, event.clientY];
    const editMode = moduleTransform?.stats()?.mode;
    if (options.showNavControls && data && !canvas.hidden && event.button === 0 && !event.shiftKey && !event.ctrlKey && !event.metaKey && !measureMode && !moduleTransform?.isDragging() && !['move', 'rotate'].includes(editMode)) {
      const rect = canvas.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
        raycaster.setFromCamera(pointer, camera);
        const targets = [];
        if (panels) targets.push(panels);
        for (const m of modelMeshes) targets.push(m);
        const hit = raycaster.intersectObjects(targets, false)[0];
        if (hit && !hit.object?.userData?.surface) {
          if (T.MOUSE) controls.mouseButtons.LEFT = T.MOUSE.ROTATE;
        } else {
          if (T.MOUSE) controls.mouseButtons.LEFT = T.MOUSE.PAN;
        }
      }
    }
  };
  const select = event => {
    if (!data || canvas.hidden || !pointerStart) return;
    if (Math.hypot(event.clientX - pointerStart[0], event.clientY - pointerStart[1]) > 4) return;
    inspect(event);
    const rect = canvas.getBoundingClientRect();
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const meshes = [];
    group.traverse(object => {
      if (!object.isMesh) return;
      for (let parent = object; parent; parent = parent.parent) if (!parent.visible) return;
      meshes.push(object);
    });
    const hit = raycaster.intersectObjects(meshes, false)[0];
    if (measureMode && hit?.point) {
      if (!measureStart) {
        measureStart = hit.point.clone();
        if (measureLine && group) { group.remove(measureLine); measureLine = null; }
        options.onMeasure?.({ state: 'start' });
      } else {
        const p1 = measureStart, p2 = hit.point.clone();
        const dxy = Math.hypot(p2.x - p1.x, p2.z - p1.z), dz = Math.abs(p2.y - p1.y), d3d = p1.distanceTo(p2);
        if (measureLine && group) group.remove(measureLine);
        const geom = new T.BufferGeometry().setFromPoints([p1.clone().add(new T.Vector3(0, 0.08, 0)), p2.clone().add(new T.Vector3(0, 0.08, 0))]);
        measureLine = new T.Line(geom, new T.LineBasicMaterial({ color: 0x06b6d4, depthTest: false }));
        measureLine.renderOrder = 20;
        group?.add(measureLine);
        measureStart = null;
        options.onMeasure?.({ state: 'done', dxy, dz, d3d });
      }
      return;
    }
    const module = hit?.object === panels && data.modules[hit.instanceId];
    if (module) options.onSelectModule?.(module.id);
    else if (hit?.object.userData.sceneObject && options.onSelectObject) {
      options.onSelectObject({ ...hit.object.userData.sceneObject }, { extend: Boolean(event.ctrlKey || event.metaKey) });
    } else if (hit?.object.userData.roofPlane != null) {
      options.onSelectRoofPlane?.(hit.object.userData.roofPlane);
    }
    if (mode !== 'wiring' || data.edit_preview) return;
    const id = module?.string?.id;
    if (id) {
      selectString(id);
      options.onSelectString?.(id);
    }
  };
  function selectString(id = '', ac = true) {
    selectedString = wiring?.select(id, ac) ?? '';
    recolor();
  }
  function frameView(points, direction, margin = .86) {
    fitCamera(T, camera, controls, points, direction, margin);
  }
  function focusObjects(values = [...selectedObjects.values()]) {
    if (!data || !group) return;
    const keys = new Set(values.map(objectKey)), points = [];
    group.updateMatrixWorld(true);
    group.traverse(object => {
      if (!object.userData.sceneObject || !keys.has(objectKey(object.userData.sceneObject))) return;
      const position = object.geometry?.attributes.position;
      if (position) for (let i = 0; i < position.count; i++) points.push(new T.Vector3().fromBufferAttribute(position, i).applyMatrix4(object.matrixWorld));
    });
    for (const value of values) if (value.kind === 'part') {
      const part = data.roof.parts?.find(part => part.id === value.id);
      for (const p of part?.outline ?? []) points.push(new T.Vector3(...data.world([p[0], p[1], -data.roof.height_m])));
    }
    if (!points.length) return;
    const direction = camera.position.clone().sub(controls.target).normalize();
    frameView(points, direction, .78); view = 'selected'; moved = false;
  }
  function focusModules(ids = []) {
    if (!data) return;
    const selected = new Set(ids), modules = data.modules.filter(module => selected.has(module.id));
    if (!modules.length) return;
    moduleTransform?.cancel();
    focusedModuleIds = modules.map(module => module.id);
    const corners = modules.flatMap(module => module.corners), xs = corners.map(point => point[0]), ys = corners.map(point => point[1]);
    const points = modules.flatMap(module => module.points);
    // Keep nearby roof/equipment context when locating a single failed panel.
    // The padding is in site metres and follows the roof's actual elevation.
    for (const x of [Math.min(...xs) - 3, Math.max(...xs) + 3]) for (const y of [Math.min(...ys) - 3, Math.max(...ys) + 3])
      points.push(data.world([x, y, data.elevation([x, y])]));
    frameView(points, camera.position.clone().sub(controls.target).normalize(), .78);
    view = 'selected'; moved = false;
  }
  function resetView(value = false) {
    view = normalizeView(value); moved = false;
    if (!data) return;
    moduleTransform?.cancel();
    if (view === 'selected') {
      if (focusedModuleIds.length) { focusModules(focusedModuleIds); return; }
      if (selectedObjects.size) { focusObjects(); return; }
      const points = wiring?.focus(selectedString) ?? [];
      if (points.length) frameView(points, new T.Vector3(.5, 1.35, .85), .78);
      return;
    }
    frameView(sceneFramePoints(data), viewDirection(T, view, data.roof, facade?.stats().front_edge ?? 0), view === 'iso' ? .9 : .84);
  }
  function setProjection(value) {
    moduleTransform?.cancel();
    camera = changeProjection(T, camera, controls, value);
  }
  function getViewState() {
    return {
      projection: camera.isOrthographicCamera ? 'orthographic' : 'perspective', view, position: camera.position.toArray(),
      target: controls.target.toArray(), zoom: camera.zoom, verticalSpan: camera.isOrthographicCamera ? camera.top - camera.bottom : null, moved
    };
  }
  function setViewState(value) {
    const vector = p => Array.isArray(p) && p.length === 3 && p.every(Number.isFinite);
    if (!data || !value || !vector(value.position) || !vector(value.target) || !Number.isFinite(value.zoom) || value.zoom <= 0) return;
    if (Math.hypot(...value.position.map((p, i) => p - value.target[i])) < .001) return;
    setProjection(value.projection);
    const damping = controls.enableDamping; controls.enableDamping = false; controls.update(); controls.enableDamping = damping;
    camera.position.fromArray(value.position); controls.target.fromArray(value.target); camera.zoom = value.zoom;
    if (camera.isOrthographicCamera && Number.isFinite(value.verticalSpan) && value.verticalSpan > 0) {
      camera.top = value.verticalSpan / 2; camera.bottom = -value.verticalSpan / 2;
      const { width, height } = container.getBoundingClientRect(); resizeCamera(camera, width || 1, height || 1);
    }
    const distance = camera.position.distanceTo(controls.target);
    controls.maxDistance = Math.max(controls.maxDistance, distance * 2); camera.far = Math.max(camera.far, distance * 3);
    view = normalizeView(value.view); moved = Boolean(value.moved); camera.updateProjectionMatrix(); controls.update(); camera.updateMatrixWorld();
  }
  const dblclick = event => {
    if (!data || canvas.hidden || measureMode || moduleTransform?.isDragging()) return;
    const rect = canvas.getBoundingClientRect();
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const meshes = [];
    if (panels) meshes.push(panels);
    group?.traverse(object => {
      if (!object.isMesh) return;
      for (let parent = object; parent; parent = parent.parent) if (!parent.visible) return;
      meshes.push(object);
    });
    const hit = raycaster.intersectObjects(meshes, false)[0];
    if (!hit?.point) return;
    const targetPoint = hit.point.clone();
    const offset = camera.position.clone().sub(controls.target);
    const curDist = offset.length();
    const desiredDist = Math.max(8, Math.min(curDist, Math.max(14, data.span * 0.48)));
    if (curDist > 1e-3) offset.multiplyScalar(desiredDist / curDist);
    controls.target.copy(targetPoint);
    camera.position.copy(targetPoint).add(offset);
    moved = true;
    controls.update();
    const mod = hit.object === panels ? data.modules[hit.instanceId] : null;
    options.onFocusPoint?.({ point: targetPoint, module: mod?.id ?? null });
  };
  const onWheel = event => {
    if (!options.showNavControls || !data || canvas.hidden || moduleTransform?.isDragging()) return;
    if (event.clientX <= 0 && event.clientY <= 0) return;
    if (Math.abs(event.deltaX) > Math.abs(event.deltaY) && Math.abs(event.deltaX) > 2) {
      panBy(event.deltaX * 0.015, 0);
      return;
    }
    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const targets = [];
    if (panels) targets.push(panels);
    for (const m of modelMeshes) targets.push(m);
    const hit = raycaster.intersectObjects(targets, false)[0];
    let hitPt = hit?.point?.clone() ?? null;
    if (!hitPt) {
      const groundPlane = new T.Plane(new T.Vector3(0, 1, 0), -Math.max(0, controls.target.y));
      const fallback = new T.Vector3();
      if (raycaster.ray.intersectPlane(groundPlane, fallback)) hitPt = fallback;
    }
    if (event.deltaY < 0 && hitPt) {
      const shift = hitPt.clone().sub(controls.target).multiplyScalar(0.26);
      shift.y *= 0.35;
      controls.target.add(shift);
      camera.position.add(shift);
      moved = true;
    } else if (event.deltaY > 0) {
      const dist = camera.position.distanceTo(controls.target);
      if (dist > data.span * 0.85) {
        const home = new T.Vector3(0, (data.roof?.height_m ?? 6) * 0.5, 0);
        const shift = home.sub(controls.target).multiplyScalar(0.15);
        controls.target.add(shift);
        camera.position.add(shift);
        moved = true;
      }
    }
  };
  const onKeyDown = event => {
    if (!options.showNavControls || !data || canvas.hidden || document.hidden) return;
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || document.activeElement?.isContentEditable) return;
    if (event.target?.closest?.('.splitter')) return;
    const key = event.key.toLowerCase();
    if (key === 'w' || event.key === 'ArrowUp') { event.preventDefault(); panBy(0, 1); }
    else if (key === 's' || event.key === 'ArrowDown') { event.preventDefault(); panBy(0, -1); }
    else if (key === 'a' || event.key === 'ArrowLeft') { event.preventDefault(); panBy(-1, 0); }
    else if (key === 'd' || event.key === 'ArrowRight') { event.preventDefault(); panBy(1, 0); }
  };
  moduleTransform = createModuleTransform(T, {
    canvas, scene, controls, getCamera: () => camera, getPanels: () => panels, getModelMeshes: () => [panels, ...modelMeshes],
    onTransform: value => options.onModuleTransform?.(value), onSelect: (id, meta) => options.onSelectModule?.(id, meta),
    onStatus: value => { note.hidden = true; recolor(); options.onTransformStatus?.(value); }
  });
  canvas.addEventListener('pointermove', inspect); canvas.addEventListener('pointerleave', leave); canvas.addEventListener('webglcontextlost', lost);
  canvas.addEventListener('webglcontextrestored', restored);
  canvas.addEventListener('pointerdown', down, { capture: true });
  canvas.addEventListener('click', select);
  canvas.addEventListener('dblclick', dblclick);
  canvas.addEventListener('wheel', onWheel, { passive: true });
  if (options.showNavControls) window.addEventListener('keydown', onKeyDown);
  // Until the user turns the view, keep the chosen framing when the canvas changes size (e.g. the wiring bar opens).
  controls.addEventListener('start', () => { moved = true; });
  const resize = new ResizeObserver(() => {
    const { width, height } = container.getBoundingClientRect();
    if (width && height) {
      renderer.setSize(width, height, false); resizeCamera(camera, width, height);
      if (data && !moved) resetView(view);
    }
  });
  resize.observe(container);
  function draw() {
    if (disposed) return;
    frame = requestAnimationFrame(draw);
    if (data && !document.hidden && container.clientWidth && container.clientHeight && !canvas.hidden) {
      if (!moduleTransform?.isDragging()) controls.update(); renderer.shadowMap.needsUpdate = needsShadow;
      renderer.render(scene,camera); needsShadow = false; draws++;
    }
  }
  setTheme(); draw();
  return {
    setData, setSun, setTheme, selectString, resetView, setProjection, getViewState, setViewState, highlightRoofPlanes, highlightObjects, focusObjects, focusModules,
    panBy, setNavMode, getNavMode,
    setModuleEditing: value => moduleTransform?.configure(value), setMeasureMode(enabled) {
      measureMode = Boolean(enabled);
      measureStart = null;
      if (!measureMode && measureLine && group) { group.remove(measureLine); measureLine = null; }
    }, highlightModules(ids = [], locked = []) {
      selectedModules = new Set(ids); lockedModules = new Set(locked); recolor();
    }, setMode(value) {
      mode = value;
      recolor();
    },
    stats: () => ({
      available: !canvas.hidden, frames: draws, panels: data?.modules.length ?? 0, removed: data?.removed.length ?? 0,
      changed: data?.changed.size ?? 0, added: data?.added.size ?? 0, preview: Boolean(data?.edit_preview),
      moduleEditing: moduleTransform?.stats() ?? null,
      roofPlanes: group?.children.filter(object => object.userData.roofPlane != null).length ?? 0,
      cableRoutes: wiring?.stats().routes ?? 0, selectedString, selectedRoofPlanes: [...selectedRoofPlanes],
      facade: facade?.stats() ?? null,
      view, projection: camera.isOrthographicCamera ? 'orthographic' : 'perspective', selectedObjects: [...selectedObjects.values()],
      parapets: group?.children.filter(object => object.userData.parapet).length ?? 0,
      drawCalls: renderer.info.render.calls, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures, sun: sunValue
    }),
    dispose() {
      if (disposed) return;
      disposed = true; cancelAnimationFrame(frame); clearTimeout(highlight); resize.disconnect();
      moduleTransform?.dispose(); controls.dispose(); release(); sun.shadow.map?.dispose(); renderer.dispose();
      canvas.removeEventListener('pointermove', inspect); canvas.removeEventListener('pointerleave', leave); canvas.removeEventListener('webglcontextlost', lost);
      canvas.removeEventListener('webglcontextrestored', restored);
      canvas.removeEventListener('pointerdown', down, { capture: true });
      canvas.removeEventListener('click', select);
      canvas.removeEventListener('dblclick', dblclick);
      canvas.removeEventListener('wheel', onWheel);
      if (options.showNavControls) window.removeEventListener('keydown', onKeyDown);
      renderer.forceContextLoss();
      container.replaceChildren();
    }
  };
}
