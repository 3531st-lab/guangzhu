import {stringColor} from './scene-data.js';

const deviceName = label => label === 'GRID' ? '并网点' : String(label).replace(/^I(\d+)$/, '逆变器$1');

// One merged mesh of thin open cylinders along the given segments; WebGL lines are always 1 px wide, tubes stay visible.
function tubes(T, segments, radius) {
  const positions = [], normals = [], up = new T.Vector3(0, 1, 0);
  for (const [a, b] of segments) {
    const length = a.distanceTo(b);
    if (length < 1e-4) continue;
    const piece = new T.CylinderGeometry(radius, radius, length, 6, 1, true);
    piece.applyMatrix4(new T.Matrix4().compose(a.clone().lerp(b, .5),
      new T.Quaternion().setFromUnitVectors(up, b.clone().sub(a).normalize()), new T.Vector3(1, 1, 1)));
    const flat = piece.toNonIndexed();
    for (const value of flat.attributes.position.array) positions.push(value);
    for (const value of flat.attributes.normal.array) normals.push(value);
    piece.dispose();
    flat.dispose();
  }
  const geometry = new T.BufferGeometry();
  geometry.setAttribute('position', new T.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('normal', new T.Float32BufferAttribute(normals, 3));
  return geometry;
}

function canvasSprite(T, draw, width, height, options) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  draw(canvas.getContext('2d'));
  const texture = new T.CanvasTexture(canvas);
  texture.encoding = T.sRGBEncoding;
  texture.anisotropy = 4;
  return new T.Sprite(new T.SpriteMaterial({map:texture, depthTest:false, ...options}));
}

export function createWiring(T, data, host) {
  const layer = new T.Group(), labels = new T.Group(), routes = [], devices = [];
  host.add(layer);
  layer.add(labels);
  let chosen = '', enabled = false, ac = true;
  const world = p => new T.Vector3(...data.world(p));
  const valid = points => Array.isArray(points) && points.every(p => Array.isArray(p) && p.length >= 3 && p.every(Number.isFinite));
  const cables = data.electrical?.cables;
  const strings = new Map((data.electrical?.strings ?? []).map(s => [s.id, s]));
  const modules = new Map(data.modules.map(m => [m.id, m]));
  const keep = [];
  function clearLabels() {
    for (const object of [...labels.children]) {
      object.traverse(child => {
        child.geometry?.dispose();
        child.material?.map?.dispose();
        child.material?.dispose();
      });
      labels.remove(object);
    }
  }
  // Connection order: small round badges that fit inside one module, so neighbours never overlap.
  function badge(text, position, ring) {
    const sprite = canvasSprite(T, ctx => {
      ctx.beginPath();
      ctx.arc(32, 32, 27, 0, Math.PI * 2);
      ctx.fillStyle = '#fffefa';
      ctx.fill();
      ctx.lineWidth = 5;
      ctx.strokeStyle = ring;
      ctx.stroke();
      ctx.fillStyle = '#1d2733';
      ctx.font = `bold ${text.length > 2 ? 22 : 28}px "Microsoft YaHei UI", sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, 32, 34);
    }, 64, 64);
    sprite.position.copy(position);
    sprite.scale.set(.78, .78, 1);
    sprite.renderOrder = 12;
    labels.add(sprite);
  }
  // Device names keep the same on-screen size at any zoom (sizeAttenuation off), anchored above the box.
  function nameTag(text, position) {
    const font = 'bold 30px "Microsoft YaHei UI", sans-serif';
    const probe = document.createElement('canvas').getContext('2d');
    probe.font = font;
    const width = Math.ceil(probe.measureText(text).width) + 44;
    const sprite = canvasSprite(T, ctx => {
      ctx.fillStyle = '#24303d';
      ctx.beginPath();
      ctx.moveTo(10, 4); ctx.lineTo(width - 10, 4); ctx.quadraticCurveTo(width - 4, 4, width - 4, 10);
      ctx.lineTo(width - 4, 46); ctx.quadraticCurveTo(width - 4, 52, width - 10, 52);
      ctx.lineTo(10, 52); ctx.quadraticCurveTo(4, 52, 4, 46); ctx.lineTo(4, 10); ctx.quadraticCurveTo(4, 4, 10, 4);
      ctx.fill();
      ctx.fillStyle = '#e08a4f';
      ctx.fillRect(4, 10, 6, 36);
      ctx.fillStyle = '#ffffff';
      ctx.font = font;
      ctx.textBaseline = 'middle';
      ctx.fillText(text, 22, 29);
    }, width, 56, {sizeAttenuation:false});
    sprite.center.set(.5, -.15);
    sprite.position.copy(position);
    sprite.scale.set(.04 * width / 56, .04, 1);
    sprite.renderOrder = 13;
    labels.add(sprite);
  }
  for (const kind of ['dc', 'ac']) {
    for (const row of cables?.[kind] ?? []) {
      const points = row.route_3d ?? row.route?.map(p => [p[0], p[1], data.elevation(p)]);
      if (row.routing_status === 'blocked' || !valid(points) || points.length < 2) continue;
      const positions = points.map(p => world([p[0], p[1], p[2] + .08]));
      const segments = positions.slice(1).map((p, i) => [positions[i], p]);
      const base = kind === 'dc' ? new T.Color(stringColor(row.id)).offsetHSL(0, .05, -.16) : new T.Color('#0b8f7c');
      const object = new T.Mesh(tubes(T, segments, kind === 'dc' ? .045 : .09),
        new T.MeshBasicMaterial({color:base.convertSRGBToLinear(), depthTest:false, transparent:true, opacity:.92}));
      object.renderOrder = kind === 'dc' ? 8 : 9;
      layer.add(object);
      keep.push(object);
      routes.push({object, row, kind, positions, segments});
    }
  }
  for (const row of cables?.positions ?? []) {
    if (!Array.isArray(row.point) || !row.point.every(Number.isFinite)) continue;
    const height = ['ground', 'carport'].includes(data.roof.type) ? 0 : data.elevation(row.point);
    const grid = row.label === 'GRID';
    const position = world([...row.point, height + (grid ? .45 : .4)]);
    const object = new T.Mesh(grid ? new T.CylinderGeometry(.42, .42, .9, 20) : new T.BoxGeometry(1.1, .8, .5),
      new T.MeshBasicMaterial({color:new T.Color(grid ? '#0b8f7c' : '#2f3d4c').convertSRGBToLinear(), depthTest:false}));
    object.position.copy(position);
    object.renderOrder = 10;
    const trim = new T.Mesh(new T.BoxGeometry(grid ? .86 : 1.14, .12, grid ? .86 : .54),
      new T.MeshBasicMaterial({color:new T.Color('#e08a4f').convertSRGBToLinear(), depthTest:false}));
    trim.position.copy(position).add(new T.Vector3(0, grid ? .46 : .41, 0));
    trim.renderOrder = 11;
    layer.add(object, trim);
    keep.push(object, trim);
    devices.push({row, position, object, trim});
  }
  function update() {
    layer.visible = enabled;
    clearLabels();
    if (!enabled) return;
    const string = strings.get(chosen);
    for (const item of routes) {
      item.object.visible = item.kind === 'ac' ? ac && (!string || item.row.id === 'I' + string.inverter) : !chosen;
      if (item.kind !== 'dc' || item.row.id !== chosen) continue;
      const bold = new T.Mesh(tubes(T, item.segments, .075),
        new T.MeshBasicMaterial({color:new T.Color('#ed581d').convertSRGBToLinear(), depthTest:false}));
      bold.renderOrder = 9;
      labels.add(bold);
      for (const [a, b] of item.segments.filter(([a, b]) => a.distanceTo(b) > .6).filter((_, i) => i % 2 === 0)) {
        const direction = b.clone().sub(a).normalize();
        const size = Math.min(.7, a.distanceTo(b) * .45);
        const arrow = new T.ArrowHelper(direction, a.clone().lerp(b, .5).sub(direction.clone().multiplyScalar(size / 2)), size,
          0x7a2a08, size * .7, size * .55);
        for (const object of [arrow.line, arrow.cone]) {
          object.material.depthTest = false;
          object.renderOrder = 10;
        }
        labels.add(arrow);
      }
    }
    const ring = string ? new T.Color(stringColor(string.id)).offsetHSL(0, .05, -.16).getStyle() : '#1d2733';
    for (const [index, id] of (string?.module_ids ?? []).entries()) {
      const module = modules.get(id);
      if (!module) continue;
      badge(String(index + 1), new T.Vector3(...module.position).add(new T.Vector3(0, .12, 0)), ring);
    }
    const colocated = new Map();
    for (const {row, position, object, trim} of devices) {
      object.visible = trim.visible = !string || row.label === 'I' + string.inverter || row.label === 'GRID' && ac;
      if (!object.visible) continue;
      const key = position.toArray().map(n => n.toFixed(2)).join(',');
      if (!colocated.has(key)) colocated.set(key, {names:[], position});
      colocated.get(key).names.push(deviceName(row.label));
    }
    for (const {names, position} of colocated.values()) nameTag(names.join(' / '), position.clone().add(new T.Vector3(0, .7, 0)));
  }
  return {
    setMode(mode) {
      const next = mode === 'wiring';
      if (next === enabled) return;
      enabled = next;
      update();
    },
    select(id = '', showAC = ac) {
      chosen = strings.has(id) ? id : '';
      ac = showAC;
      update();
      return chosen;
    },
    // Everything the camera should frame when one string is focused: its modules, its route and its inverter.
    focus(id = chosen) {
      const string = strings.get(id);
      if (!string) return [];
      const points = string.module_ids.flatMap(mid => modules.get(mid)?.points ?? []).map(p => new T.Vector3(...p));
      for (const item of routes) if (item.kind === 'dc' && item.row.id === id) points.push(...item.positions);
      for (const device of devices) if (device.row.label === 'I' + string.inverter) points.push(device.position.clone());
      return points;
    },
    stats:() => ({routes:routes.length, selected:chosen, visible:layer.visible, devices:devices.length}),
  };
}
