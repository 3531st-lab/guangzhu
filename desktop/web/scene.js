import {normalizeScene,panelMatrix,solarPosition,heatColor,stringColor,pileContact} from './scene-data.js';
import {createWiring} from './scene-wiring.js';
import {batchStatic} from './scene-static.js';

export function createScene(container, options = {}) {
  const T = globalThis.THREE, canvas = document.createElement('canvas'), note = document.createElement('div');
  container.classList.add('scene-view'); note.className = 'scene-note'; note.hidden = true;
  container.replaceChildren(canvas,note);
  let renderer, disposed = false, data, panels, group, mode = 'light', theme = 'light', frame, highlight, draws = 0;
  let date = `${new Date().getFullYear()}-12-21`, hour = 12, sunValue, needsShadow = true;
  let wiring, windZones, selectedString = '', pointerStart, view = false, moved = false;
  function unavailable(message = '此设备无法显示 3D。设计指标和文件仍可查看。') {
    note.textContent = message; note.hidden = false; note.className = 'scene-unavailable'; canvas.hidden = true;
    options.onUnavailable?.(message);
  }
  const noop = () => {}, fallback = {setData:noop,setMode:noop,setSun:noop,setTheme:noop,selectString:noop,resetView:noop,
    stats:() => ({available:false}),dispose:() => container.replaceChildren()};
  if (!T?.OrbitControls) {unavailable(); return fallback;}
  try {
    const context = canvas.getContext('webgl2',{antialias:true}) || canvas.getContext('webgl',{antialias:true});
    if (!context) {unavailable(); return fallback;}
    renderer = new T.WebGLRenderer({canvas,context,antialias:true});
  } catch {unavailable(); return fallback;}
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1,2)); renderer.outputEncoding = T.sRGBEncoding;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFSoftShadowMap; renderer.shadowMap.autoUpdate = false;
  const scene = new T.Scene(), camera = new T.PerspectiveCamera(42,1,.1,2000);
  const controls = new T.OrbitControls(camera,canvas); controls.enableDamping = true; controls.maxPolarAngle = Math.PI*.48;
  const ambient = new T.HemisphereLight(0xffffff,0x6f675b,.6), sun = new T.DirectionalLight(0xffefcf,1.1);
  sun.castShadow = true; sun.shadow.mapSize.set(2048,2048); sun.shadow.normalBias = .025; sun.shadow.bias = -.0002;
  scene.add(ambient,sun,sun.target);
  const raycaster = new T.Raycaster(), pointer = new T.Vector2();
  const linear = color => new T.Color(color).convertSRGBToLinear();
  const material = (color,extra={}) => new T.MeshStandardMaterial({color:linear(color),roughness:.78,...extra});
  function mesh(geometry,mat,position=[0,0,0]) {
    const object = new T.Mesh(geometry,mat); object.position.fromArray(position); object.castShadow = true; object.receiveShadow = true; group.add(object); return object;
  }
  function release() {
    if (!group) return;
    group.traverse(object => {
      object.geometry?.dispose();
      const mats = Array.isArray(object.material) ? object.material : [object.material];
      for (const mat of mats) {mat?.map?.dispose(); mat?.dispose();}
      for (const mat of object.userData.panelMaterials ?? []) if (!mats.includes(mat)) mat.dispose();
    });
    scene.remove(group);
    group = null;
    panels = null;
    wiring = null;
    windZones = null;
    renderer.renderLists.dispose();
  }
  function polygon(points,height,base,color,extra={}) {
    if (!points?.length) return;
    const shape = new T.Shape(points.map(([x,y]) => new T.Vector2(x-data.center[0],y-data.center[1])));
    const geometry = new T.ExtrudeGeometry(shape,{depth:height,bevelEnabled:false}); geometry.rotateX(-Math.PI/2);
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
    return mesh(geometry,material(color,extra),[0,base,0]);
  }
  function surface(points, color, extra = {}, wall = false) {
    const triangles = wall ? [[0,2,1],[0,3,2]] : T.ShapeUtils.triangulateShape(points.map(p => new T.Vector2(p[0], p[1])), []);
    const coordinates = triangles.flatMap(indices => indices.flatMap(i => data.world(points[i])));
    const geometry = new T.BufferGeometry();
    geometry.setAttribute('position', new T.Float32BufferAttribute(coordinates, 3));
    geometry.computeVertexNormals();
    return mesh(geometry, material(color, {side:T.FrontSide, ...extra}));
  }
  function instances(modules,ghost=false) {
    if (!modules.length) return null;
    const object = new T.InstancedMesh(new T.BoxGeometry(1,1,1),material(ghost ? '#d1493f' : '#ffffff',ghost ? {transparent:true,opacity:.38,depthWrite:false} : {roughness:.45}),modules.length);
    if (!ghost) object.userData.panelMaterials = [object.material,new T.MeshBasicMaterial({color:0xffffff})];
    modules.forEach((module,i) => object.setMatrixAt(i,new T.Matrix4().fromArray(panelMatrix(module))));
    object.castShadow = !ghost; object.receiveShadow = !ghost; object.frustumCulled = false; group.add(object); return object;
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
    wiring?.setMode(mode);
    if (!panels) return;
    panels.material = panels.userData.panelMaterials[mode === 'light' ? 0 : 1];
    data.modules.forEach((m,i) => {
      const color = flash && data.added.has(m.id) ? '#4fc58a' : mode === 'heat' ? heatColor(m.loss,data.threshold) : mode === 'string' ? stringColor(m.string?.id) : theme === 'dark' ? '#3b5f9c' : '#1f3a66';
      const windColor = {corner:'#c94e42', edge:'#d79935', middle:'#368c90'}[m.wind?.zone] ?? '#777777';
      const wireColor = selectedString && m.string?.id !== selectedString ? '#afb4b9' : stringColor(m.string?.id);
      const finalColor = mode === 'wiring' ? wireColor : mode === 'wind' ? windColor :
        mode === 'phase' && m.phase ? (m.phase === 1 ? '#2a9d63' : '#c87743') : color;
      panels.setColorAt(i, linear(finalColor));
    });
    if (windZones) windZones.visible = mode === 'wind';
    if (mode === 'wind') {
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
  function setSun(nextDate=date,nextHour=hour) {
    date = nextDate; hour = Number(nextHour);
    if (!data) return;
    sunValue = solarPosition(data.project.site.lat,data.project.site.lon,date,hour);
    sun.position.fromArray(sunValue.direction).multiplyScalar(data.span*2).add(sun.target.position);
    sun.intensity = sunValue.altitude > 0 ? 1.1 : 0; needsShadow = true; options.onSun?.(sunValue); return sunValue;
  }
  function setTheme(value) {
    theme = value || (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
    scene.background = new T.Color(theme === 'dark' ? '#171411' : '#f4ece3');
    if (group) for (const object of group.children) if (object.userData.surface) object.material.color.copy(linear(theme === 'dark' ? '#51463b' : '#d8cbbb'));
    recolor();
  }
  function setData(input) {
    if (disposed) return;
    clearTimeout(highlight); release(); note.hidden = true; canvas.hidden = false;
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
    data = normalizeScene(input); group = new T.Group(); scene.add(group);
    const {roof,span} = data, ground = mesh(new T.PlaneGeometry(span*5,span*5),material('#d8cbbb'));
    ground.rotation.x = -Math.PI/2; ground.position.y = -.03; ground.userData.surface = true;
    if (['ground','carport'].includes(roof.type)) {
      const facts = input.facilities;
      if (!facts) {
        unavailable('此记录缺少新建场地实体，请重新打开记录。');
        return;
      }
      const line = (points, color) => group.add(new T.Line(
        new T.BufferGeometry().setFromPoints(points.map(p => new T.Vector3(...data.world(p)))),
        new T.LineBasicMaterial({color})));
      for (const road of facts.roads ?? []) polygon(road, .015, .01, '#b0aca2');
      for (const fence of facts.fence ?? []) {
        line(fence.map(p => [...p, 1.5]), 0x6b7861);
        line(fence.map(p => [...p, .1]), 0x6b7861);
        for (const p of fence) line([[...p,0],[...p,1.5]], 0x6b7861);
      }
      const byId = new Map(data.modules.map(panel => [panel.id, panel]));
      for (const pile of facts.piles ?? []) {
        const p = data.world(pile.point), height = pile.top_m;
        const contact = pileContact(pile, pile.modules.map(id => byId.get(id)).filter(Boolean));
        const geometry = new T.CylinderGeometry(.07,.07,height,12), vertices = geometry.attributes.position;
        for (let i = 0; i < vertices.count; i++) {
          if (vertices.getY(i) > 0) {
            const delta = contact.dx * vertices.getX(i) - contact.dy * vertices.getZ(i) - contact.inset;
            vertices.setY(i, vertices.getY(i) + delta);
          }
        }
        geometry.computeVertexNormals();
        mesh(geometry,material('#77858b'),[p[0],height/2,p[2]]);
        if (pile.rail) line(pile.rail, 0x899397);
      }
      if (roof.type === 'ground') {
        for (const panel of data.modules) line([panel.corners[0], panel.corners[3]], 0x899397);
      }
      for (const face of facts.faces ?? []) surface(face.points, '#aab8c8', {side:T.DoubleSide});
      for (const beam of facts.beams ?? []) {
        const bottom = beam.points.map(p => [p[0], p[1], p[2] - beam.depth_m]);
        surface(bottom, '#77858b', {side:T.DoubleSide});
        for (let i = 0; i < bottom.length; i++) {
          const j = (i + 1) % bottom.length;
          surface([bottom[i], bottom[j], beam.points[j], beam.points[i]], '#77858b', {side:T.DoubleSide}, true);
        }
      }
      for (const column of facts.columns ?? []) {
        const p = data.world(column.point), height = column.top_m;
        mesh(new T.CylinderGeometry(.1,.1,height,16),material('#77858b'),[p[0],height/2,p[2]]);
      }
      for (const bay of facts.bays ?? []) line([...bay.polygon,bay.polygon[0]].map(p => [...p,.025]), 0xffffff);
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
            glass ? {transparent:true, opacity:.48, depthWrite:false, side:T.DoubleSide} : {});
        object.userData.roofPlane = face.id;
        const border = [...face.points, face.points[0]].map(p => new T.Vector3(...data.world(p)));
        group.add(new T.Line(new T.BufferGeometry().setFromPoints(border), new T.LineBasicMaterial({color:0x526174})));
      }
      for (const wall of geometry.walls) surface(wall, '#d8cbbb', {}, true).userData.surface = true;
      for (let i = 0; roof.parapet_height_m && i < geometry.boundary.length - 1; i++) {
        const a = geometry.boundary[i], b = geometry.boundary[i + 1];
          surface([[...a.slice(0,2),a[2]+roof.parapet_height_m],[...b.slice(0,2),b[2]+roof.parapet_height_m],b,a], '#c3b7a8', {}, true);
      }
      for (const points of geometry.keepouts) surface(points, '#60a5b5', {transparent:true, opacity:.62});
    } else if (!['ground','carport'].includes(roof.type)) polygon(roof.outline,roof.height_m,0,'#d8cbbb').userData.surface = true;
    for (let i=0;roof.parapet_height_m && roof.type !== 'pitched' && i<roof.outline.length;i++) {
      const a = data.world(roof.outline[i]), b = data.world(roof.outline[(i+1)%roof.outline.length]), length = Math.hypot(b[0]-a[0],b[2]-a[2]);
      const wall = mesh(new T.BoxGeometry(length,roof.parapet_height_m,.22),material('#c3b7a8'),[(a[0]+b[0])/2,roof.height_m+roof.parapet_height_m/2,(a[2]+b[2])/2]);
      wall.rotation.y = -Math.atan2(b[2]-a[2],b[0]-a[0]);
      followRoof(wall);
    }
    for (const obstacle of roof.obstacles ?? []) {
      const base = roof.type === 'pitched' ? input.roof_geometry.obstacle_bases[obstacle.id] : 0;
      if (obstacle.kind === 'cylinder') {
        const p = data.world(obstacle.center);
        p[1] += obstacle.height_m/2 + base;
        followRoof(mesh(new T.CylinderGeometry(obstacle.radius_m,obstacle.radius_m,obstacle.height_m,32),material('#bcae9b'),p));
      }
      else polygon(obstacle.footprint,obstacle.height_m,roof.height_m + base,'#bcae9b');
    }
    for (const near of roof.surroundings ?? []) { // T19: buildings and trees stand on the ground and rise above the roof
      const height = roof.height_m+near.height_m, p = data.world(near.center ?? [0,0]);
      if (near.kind === 'cylinder') mesh(new T.CylinderGeometry(near.radius_m,near.radius_m,height,32),material('#9fb08f'),[p[0],height/2,p[2]]);
      else polygon(near.footprint,height,0,'#b9ada0');
    }
    if (roof.type !== 'pitched') {
      for (const area of [...(roof.keepouts ?? []),...(data.design.added_keepouts ?? [])]) {
        polygon(area.polygon,.025,roof.height_m+.02,'#60a5b5',{transparent:true,opacity:.62});
      }
    }
    batchStatic(T, group);
    // Wind mode shows where the corner and edge zones lie on the deck (often left empty by the setback); kept out of the static batch.
    windZones = new T.Group();
    for (const [zone, color] of data.wind && roof.type !== 'pitched' ? [['corner', '#c94e42'], ['edge', '#d79935']] : []) {
      const shape = data.wind.regions?.[zone];
      for (const rings of shape?.type === 'MultiPolygon' ? shape.coordinates : shape?.type === 'Polygon' ? [shape.coordinates] : []) {
        const area = polygon(rings[0], .02, roof.height_m + .03, color, {transparent:true, opacity:.5, depthWrite:false});
        if (area) { area.castShadow = false; group.remove(area); windZones.add(area); }
      }
    }
    group.add(windZones);
    panels = instances(data.modules);
    instances(data.removed,true);
    recolor(true);
    if (data.project.requirements?.structured?.max_height_m != null) {
      const points = [...roof.outline, roof.outline[0]].map(p =>
        new T.Vector3(...data.world([p[0], p[1], data.elevation(p) + roof.parapet_height_m])));
      group.add(new T.Line(new T.BufferGeometry().setFromPoints(points), new T.LineBasicMaterial({color: 0xd1493f, depthTest: false})));
    }
    wiring = createWiring(T, data, group);
    selectedString = wiring.select(selectedString);
    highlight = setTimeout(() => recolor(),1500);
    const north = new T.ArrowHelper(new T.Vector3(0,0,-1),new T.Vector3(-span*.58,.1,span*.4),span*.18,0xc87743,span*.045,span*.025); group.add(north);
    const labelCanvas = document.createElement('canvas'); labelCanvas.width = 64; labelCanvas.height = 64;
    const ctx = labelCanvas.getContext('2d'); ctx.font = 'bold 44px sans-serif'; ctx.fillStyle = '#c87743'; ctx.textAlign = 'center'; ctx.fillText('N',32,48);
    const label = new T.Sprite(new T.SpriteMaterial({map:new T.CanvasTexture(labelCanvas),depthTest:false})); label.position.set(-span*.58,1,span*.17); label.scale.set(3,3,1); group.add(label);
    resetView();
    controls.minDistance = Math.max(2, span*.04); controls.maxDistance = span*5; sun.target.position.copy(controls.target);
    Object.assign(sun.shadow.camera,{left:-span,right:span,top:span,bottom:-span,near:.1,far:span*5}); sun.shadow.camera.updateProjectionMatrix();
    setTheme(theme); recolor(true); setSun();
  }
  function inspect(event) {
    if (!panels || canvas.hidden) return;
    const rect = canvas.getBoundingClientRect(); pointer.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);
    raycaster.setFromCamera(pointer,camera); const hit = raycaster.intersectObject(panels)[0], m = hit && data.modules[hit.instanceId];
    note.hidden = !m; note.className = 'scene-note';
    if (!m) {options.onInspect?.(null); return;}
    const e = data.electrical, info = {module:m.id,version:data.design.version,loss:m.loss,string:m.string,voltages:e ? {voc_cold_v:e.voc_cold_v,vmp_hot_v:e.vmp_hot_v} : null};
    const num = value => Number.isFinite(value) ? value.toFixed(2) : '未提供';
    const cable = e?.cables?.dc?.find(row => row.id === m.string?.id);
    note.textContent = `${m.id} · v${data.design.version}\n年度遮挡损失 ${num(m.loss)}%\n` +
      (m.string ? `${m.string.id} · MPPT ${m.string.mppt} · 串工作${num(cable?.voltage_v)}V · 压降${num(cable?.drop_pct)}%` : '未接入组串或缺少电气数据');
    options.onInspect?.(info);
  }
  const leave = () => {note.hidden = true; options.onInspect?.(null);};
  const lost = event => {event.preventDefault(); cancelAnimationFrame(frame); unavailable('3D 显示已中断，请重新打开结果页。设计数据仍可查看。');};
  const restored = () => {
    if (disposed || !data) return;
    canvas.hidden = false;
    note.className = 'scene-note';
    note.hidden = true;
    needsShadow = true;
    cancelAnimationFrame(frame);
    draw();
  };
  const down = event => { pointerStart = [event.clientX, event.clientY]; };
  const select = event => {
    if (mode !== 'wiring' || !panels || canvas.hidden || !pointerStart) return;
    if (Math.hypot(event.clientX - pointerStart[0], event.clientY - pointerStart[1]) > 4) return;
    inspect(event);
    const hit = raycaster.intersectObject(panels)[0];
    const id = hit && data.modules[hit.instanceId]?.string?.id;
    if (id) {
      selectString(id);
      options.onSelectString?.(id);
    }
  };
  function selectString(id = '', ac = true) {
    selectedString = wiring?.select(id, ac) ?? '';
    recolor();
  }
  // Frame the given points from a fixed direction: search the camera distance until they just fill the canvas.
  function frameView(points, direction, margin, center) {
    const box = new T.Box3().setFromPoints(points), target = center ?? box.getCenter(new T.Vector3());
    const unit = direction.clone().normalize(), size = Math.max(box.getSize(new T.Vector3()).length(), 5);
    const bounds = distance => {
      camera.position.copy(target).addScaledVector(unit, distance);
      camera.lookAt(target);
      camera.updateMatrixWorld();
      const range = [Infinity, -Infinity, Infinity, -Infinity];
      for (const point of points) {
        const p = point.clone().project(camera);
        if (p.z > 1) return null;
        range[0] = Math.min(range[0], p.x); range[1] = Math.max(range[1], p.x);
        range[2] = Math.min(range[2], p.y); range[3] = Math.max(range[3], p.y);
      }
      return range;
    };
    const extent = distance => {
      const range = bounds(distance);
      return range ? Math.max(...range.map(Math.abs)) : Infinity;
    };
    let far = size * 6;
    // Perspective makes near corners spread more, so re-centre the projected box on the canvas a few times.
    for (let pass = 0; pass < 3; pass++) {
      let near = size * .05;
      far = size * 6;
      for (let i = 0; i < 28; i++) {
        const middle = (near + far) / 2;
        if (extent(middle) > margin) near = middle;
        else far = middle;
      }
      const range = bounds(far);
      if (!range) break;
      const half = Math.tan(camera.fov * Math.PI / 360) * far;
      const right = new T.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
      const up = new T.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
      target.addScaledVector(right, (range[0] + range[1]) / 2 * half * camera.aspect).addScaledVector(up, (range[2] + range[3]) / 2 * half);
    }
    camera.position.copy(target).addScaledVector(unit, far);
    controls.target.copy(target);
    controls.update();
  }
  function resetView(top = false) {
    if (!data) return;
    view = top;
    moved = false;
    const {roof} = data;
    camera.updateProjectionMatrix();
    if (top === 'selected') {
      const points = wiring?.focus(selectedString) ?? [];
      if (points.length) frameView(points, new T.Vector3(.5, 1.35, .85), .78);
      return;
    }
    const outline = roof.outline.map(p => [...p, data.elevation(p)]);
    const rim = roof.type === 'pitched' ? 0 : roof.parapet_height_m ?? 0;
    const points = outline.flatMap(p => [data.world([p[0], p[1], p[2] + rim]), data.world([p[0], p[1], -roof.height_m])]);
    const step = Math.ceil(data.modules.length / 150);
    data.modules.forEach((module, i) => { if (i % step === 0) points.push(...module.points); });
    const sample = points;
    frameView(sample.map(p => new T.Vector3(...p)), top ? new T.Vector3(0, 1, .001) : new T.Vector3(.7, 1, .85), top ? .84 : .9);
  }
  canvas.addEventListener('pointermove',inspect); canvas.addEventListener('pointerleave',leave); canvas.addEventListener('webglcontextlost',lost);
  canvas.addEventListener('webglcontextrestored', restored);
  canvas.addEventListener('pointerdown', down);
  canvas.addEventListener('click', select);
  // Until the user turns the view, keep the chosen framing when the canvas changes size (e.g. the wiring bar opens).
  controls.addEventListener('start', () => { moved = true; });
  const resize = new ResizeObserver(() => {
    const {width,height} = container.getBoundingClientRect();
    if (width && height) {
      renderer.setSize(width,height,false); camera.aspect = width/height; camera.updateProjectionMatrix();
      if (data && !moved) resetView(view);
    }
  });
  resize.observe(container);
  function draw() {
    if (disposed) return;
    frame = requestAnimationFrame(draw);
    if (!document.hidden && container.clientWidth && container.clientHeight && !canvas.hidden) {
      controls.update(); renderer.shadowMap.needsUpdate = needsShadow;
      renderer.render(scene,camera); needsShadow = false; draws++;
    }
  }
  setTheme(); draw();
  return {setData,setSun,setTheme,selectString,resetView,setMode(value) {
    mode = value;
    recolor();
  },
    stats:() => ({available:!canvas.hidden,frames:draws,panels:data?.modules.length ?? 0,removed:data?.removed.length ?? 0,
      roofPlanes:group?.children.filter(object => object.userData.roofPlane != null).length ?? 0,
      cableRoutes:wiring?.stats().routes ?? 0, selectedString,
      drawCalls:renderer.info.render.calls,geometries:renderer.info.memory.geometries,textures:renderer.info.memory.textures,sun:sunValue}),
    dispose() {
      if (disposed) return;
      disposed = true; cancelAnimationFrame(frame); clearTimeout(highlight); resize.disconnect();
      controls.dispose(); release(); sun.shadow.map?.dispose(); renderer.dispose();
      canvas.removeEventListener('pointermove',inspect); canvas.removeEventListener('pointerleave',leave); canvas.removeEventListener('webglcontextlost',lost);
      canvas.removeEventListener('webglcontextrestored', restored);
      canvas.removeEventListener('pointerdown', down);
      canvas.removeEventListener('click', select);
      renderer.forceContextLoss();
      container.replaceChildren();
    }};
}
