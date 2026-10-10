// T18: draw a roof, or trace it over an imported image, PDF or DXF; set its city, real data, rooftop equipment and the
// buildings and trees around it. Saved roofs are ordinary roof templates for the one-click design.
// Codex review (R01-R03, R07, R09, R12): shapes stay on the drawing when its scale or north changes; a new drawing needs its outline
// traced or adopted before saving; switching drawing methods never changes the shape; corners can be dragged, added and deleted with
// undo and redo; problems are marked where they are; unsaved edits are kept as a draft.
import { esc, splitter } from "./data.js";
import {isSite, defaults as siteDefaults, panel as sitePanel, drawing as siteDrawing} from './installation-edit.js';

// kind: [button label, roof list, shape, default height above the roof surface in metres, id prefix]
const KINDS = { device: ["屋面设备", "obstacles", "rect", 2.5, "dev"], tank: ["圆形设备", "obstacles", "circle", 3, "tank"],
  keepout: ["禁区", "keepouts", "rect", 0, "zone"], building: ["周边楼", "surroundings", "rect", 12, "bldg"], tree: ["周边树", "surroundings", "circle", 6, "tree"] };
KINDS.skylight = ["采光带", "keepouts", "rect", 0, "sky"];
KINDS.vent = ['通风口', 'keepouts', 'rect', 0, 'vent'];
KINDS.inverter = ["逆变器位置", "inverter_positions", "point", 0, "inv"];
KINDS.grid = ["并网点", "grid_point", "point", 0, "grid"];
KINDS.siteTree = ['场内树木', 'obstacles', 'circle', 6, 'site-tree'];
KINDS.pole = ['场内电杆', 'obstacles', 'circle', 8, 'pole'];
KINDS.house = ['场内小房', 'obstacles', 'rect', 3, 'house'];
const MODES = ["按尺寸画", "描点画", "导入图纸"];
const DXF_UNITS = [[0.001, "毫米"], [0.01, "厘米"], [1, "米"], [0.0254, "英寸"]];
// Everything a draft keeps; the geometry part is what undo and redo step through.
const FIELDS = ["name", "lat", "lon", "height", "parapet", "load", "verified", "outline", "items", "rect", "drawing", "dxf", "basis", "north"];
FIELDS.push("roofMode", "slope", "azimuth", "ridgeMode", "ridge", "building");
FIELDS.push('windCity', 'wind');
FIELDS.push('pitchKind', 'planeMaterial', 'teeth', 'toothWidth', 'glassAngle', 'seamSetback', 'planes', 'planeSource');
FIELDS.push('ground', 'carport');
FIELDS.push('use', 'animal', 'heightEdited', 'groundSunMin');
const GEOMETRY = FIELDS.slice(7);
const round = (v) => Math.round(v * 100) / 100;
const fine = (v) => Math.round(v * 1e9) / 1e9; // drops float noise only, so a turned rectangle reopens with the same size and angle
const num = (v) => (v === "" || v == null ? null : Number(v));
const rad = (deg) => (num(deg) ?? 0) * Math.PI / 180;
const rotate = ([x, y], a) => [x * Math.cos(a) - y * Math.sin(a), x * Math.sin(a) + y * Math.cos(a)];
const scaleOf = (c) => c.distance_m / Math.hypot(c.p2_px[0] - c.p1_px[0], c.p2_px[1] - c.p1_px[1]);
// Same conversion as models.px_to_m: origin at the first calibration point, y up the drawing, then turned so that y points north.
export const toMetres = ([u, v], c) => rotate([(u - c.p1_px[0]) * scaleOf(c), (c.p1_px[1] - v) * scaleOf(c)], rad(c.north_deg)).map(round);
const toPixels = (p, c) => {
  const [x, y] = rotate(p, -rad(c.north_deg));
  return [c.p1_px[0] + x / scaleOf(c), c.p1_px[1] - y / scaleOf(c)];
};
const key = (d) => d && (d.upload || "saved"); // the drawing an outline was traced on or adopted for
const text = (keys) => JSON.stringify(keys.map((k) => ed[k]), (k, v) => (k === "file" ? undefined : v));
let ed, ctx, cities = [], tiltTimer, drag = null, bound = false;
let planeTimer;

function pitchedSettings() {
  return {kind:ed.pitchKind, slope_deg:num(ed.slope), azimuth_deg:num(ed.azimuth), material:ed.planeMaterial,
    ridge_mode:ed.ridgeMode, ridge:ed.pitchKind === 'gable' ? ed.ridge : null, teeth:num(ed.teeth),
    tooth_width_m:num(ed.toothWidth), glass_deg:num(ed.glassAngle)};
}
function planeSource() {
  return JSON.stringify([ed.outline, pitchedSettings()]);
}
function planeRequest() {
  return {outline:ed.outline, settings:pitchedSettings(), height_m:num(ed.height),
    planes:ed.planeSource === planeSource() ? ed.planes : null};
}
function planeHeightText(plane) {
  const azimuth = rad(plane.slope_azimuth_deg);
  const stations = plane.outline.map(([x, y]) => -x * Math.sin(azimuth) - y * Math.cos(azimuth));
  const low = Number(ed.height) + plane.offset_m;
  const high = low + (Math.max(...stations) - Math.min(...stations)) * Math.tan(rad(plane.slope_deg));
  return `离地最低 ${low.toFixed(3)} m / 最高 ${high.toFixed(3)} m`;
}
function planeRows() {
  if (ed.planeSource !== planeSource()) return '<p>正在生成实际坡面…</p>';
  const materials = [['metal', '彩钢瓦'], ['concrete', '混凝土'], ['glass', '采光玻璃（不装）']];
  return ed.planes.map((p, i) => `<fieldset><legend>P${p.id}</legend>
    <label class="field">材料<select data-plane="${i}" data-plane-key="material">${materials.map(([v, label]) =>
      `<option value="${v}" ${p.material === v ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
    <div class="grid2">${[['slope_deg','坡度 °'],['slope_azimuth_deg','下行朝向 °'],['offset_m','最低边偏移 m'],
      ['load_capacity_kn_m2','承重 kN/㎡（空则继承整栋）']].map(([key, label]) =>
      `<label class="field">${label}<input type="number" step="any" data-plane="${i}" data-plane-key="${key}"
      value="${esc(p[key] ?? '')}"></label>`).join('')}</div>
    <label class="field">承重来源<select data-plane="${i}" data-plane-key="load_verified">
      ${[['','继承整栋'],['true','结构核定'],['false','示意待核定']].map(([v, label]) =>
        `<option value="${v}" ${String(p.load_verified ?? '') === v ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
    <p>最低边偏移 ${p.offset_m.toFixed(3)} m；檐口基准 ${Number(ed.height).toFixed(2)} m；${planeHeightText(p)}。
      ${p.material === 'concrete' ? '固定导轨与锚固件：抗拔、防水须专项复核。' : ''}</p></fieldset>`).join('');
}
function updatePlanePreview() {
  if (ed.roofMode !== 'pitched' || pixelMode() || problems(ed.outline).length) return;
  const request = planeRequest(), signature = JSON.stringify(request), state = ed;
  if (ed.previewRequested === signature) return;
  ed.previewRequested = signature;
  clearTimeout(planeTimer);
  planeTimer = setTimeout(async () => {
    try {
      const value = await ctx.post('roof-planes', request);
      if (ed !== state || JSON.stringify(planeRequest()) !== signature) return;
      ed.planes = value.planes;
      ed.planeSource = planeSource();
      ed.previewRequested = JSON.stringify(planeRequest());
      ed.planeMessage = value.actual_teeth ? `实际 ${value.actual_teeth} 齿，等分齿宽 ${value.actual_pitch_m.toFixed(3)} m` : '坡面拼接已通过2厘米检查';
      const host = document.getElementById('re-planes');
      if (host) host.innerHTML = planeRows();
      draw();
      keepDraft();
    } catch (error) {
      if (ed === state) ed.planeMessage = error.message;
    }
    const note = document.getElementById('re-plane-note');
    if (note && ed === state) note.textContent = ed.planeMessage;
  }, 220);
}

function rectangle({ w, d, turn, cx, cy }) {
  const [W, D] = [num(w) ?? 0, num(d) ?? 0], [X, Y] = [cx ?? W / 2, cy ?? D / 2];
  return [[-W / 2, -D / 2], [W / 2, -D / 2], [W / 2, D / 2], [-W / 2, D / 2]].map((p) => rotate(p, rad(turn))).map(([x, y]) => [fine(x + X), fine(y + Y)]);
}
function asRect(o) { // length, width, turn and centre of a rectangular outline; null for any other shape
  const e = o.map((p, i) => [o[(i + 1) % o.length][0] - p[0], o[(i + 1) % o.length][1] - p[1]]), len = e.map((v) => Math.hypot(...v));
  if (o.length !== 4 || len.some((l) => l < 0.01) || e.some((v, i) => Math.abs(v[0] * e[(i + 1) % 4][0] + v[1] * e[(i + 1) % 4][1]) > 1e-3 * len[i] *
    len[(i + 1) % 4])) return null;
  let [w, d, t] = [len[0], len[1], Math.atan2(e[0][1], e[0][0]) * 180 / Math.PI];
  while (t > 45) [w, d, t] = [d, w, t - 90];
  while (t <= -45) [w, d, t] = [d, w, t + 90];
  return { w: round(w), d: round(d), turn: round(t), cx: o.reduce((s, p) => s + p[0] / 4, 0), cy: o.reduce((s, p) => s + p[1] / 4, 0) };
}
function area(points) {
  return Math.abs(points.reduce((sum, [x, y], i) => sum + x * points[(i + 1) % points.length][1] - points[(i + 1) % points.length][0] * y, 0)) / 2;
}
function roofCentroid(points) {
  let mass = 0, x = 0, y = 0;
  points.forEach((a, i) => {
    const b = points[(i + 1) % points.length], cross = a[0] * b[1] - b[0] * a[1];
    mass += cross;
    x += (a[0] + b[0]) * cross;
    y += (a[1] + b[1]) * cross;
  });
  return mass ? [x / (3 * mass), y / (3 * mass)] : [0, 0];
}
function defaultRidge() {
  let best;
  const sorted = [...ed.outline].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const turn = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const half = points => {
    const hull = [];
    for (const p of points) {
      while (hull.length >= 2 && turn(hull.at(-2), hull.at(-1), p) <= 0) {
        hull.pop();
      }
      hull.push(p);
    }
    return hull.slice(0, -1);
  };
  const hull = [...half(sorted), ...half([...sorted].reverse())];
  hull.forEach((p, i) => {
    const q = hull[(i + 1) % hull.length], angle = Math.atan2(q[1] - p[1], q[0] - p[0]);
    const local = ed.outline.map(p => rotate(p, -angle)), xs = local.map(p => p[0]), ys = local.map(p => p[1]);
    const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
    if (!best || w * h < best.area - 1e-8) {
      best = { area: w * h, w, h, angle };
    }
  });
  if (!best) {
    return [];
  }
  const alongW = (best.w >= best.h) !== (ed.ridgeMode === 'short');
  const angle = best.angle + (alongW ? 0 : Math.PI / 2), span = Math.max(best.w, best.h), c = roofCentroid(ed.outline);
  return [-1, 1].map(sign => [c[0] + sign * span / 2 * Math.cos(angle), c[1] + sign * span / 2 * Math.sin(angle)]);
}
function cross(a, b, c, d) { // where segments ab and cd meet, or null
  const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]], den = r[0] * s[1] - r[1] * s[0];
  if (Math.abs(den) < 1e-12) return null;
  const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den, u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
  return t >= 0 && t <= 1 && u >= 0 && u <= 1 ? [a[0] + t * r[0], a[1] + t * r[1]] : null;
}
function problems(o) { // what is wrong with an outline, and where, so it can be fixed without redrawing
  const n = o.length, at = (i) => o[i % n], corner = (i) => `角 ${i % n + 1}`, out = [];
  if (n < 3) return [{ text: "外形至少要 3 个角" }];
  o.forEach((p, i) => Math.hypot(p[0] - at(i + 1)[0], p[1] - at(i + 1)[1]) < 0.01 && out.push({ text: `${corner(i)}和${corner(i + 1)}重合了：删掉其中一个`, at: p }));
  for (let i = 0; i < n; i++) {
    for (let j = i + 2; j < n - (i === 0); j++) {
      const x = cross(at(i), at(i + 1), at(j), at(j + 1));
      if (x) out.push({ at: x, text: `第 ${i + 1} 条边（${corner(i)}→${corner(i + 1)}）和第 ${j + 1} 条边（${corner(j)}→${corner(j + 1)}）交叉了：拖动角点把它们分开` });
    }
  }
  if (!out.length && area(o) < 0.01) out.push({ text: "外形面积是 0：这些角在一条直线上" });
  return out;
}
function load(row) {
  const p = row?.project, r = p?.roof, zone = (o, kind) => ({ id: o.id, kind: o.preset ?? kind,
    preset: o.preset, clearance: o.clearance_m ?? '', label: o.label, height: o.height_m ?? 0,
    ...(o.kind === "cylinder" ? { center: o.center, radius: o.radius_m } : { points: o.footprint ?? o.polygon }) });
  const drawing = r?.underlay ? { url: `/api/my-roofs/${encodeURIComponent(row.id)}/underlay?v=${Date.now()}`, upload: "", calibration: r.underlay.calibration } : null;
  ed = { id: row?.id ?? null, name: p?.name ?? "", lat: p?.site.lat ?? 31.8123, lon: p?.site.lon ?? 119.9692, height: r?.height_m ?? 10,
    windCity:p?.site.wind_city ?? '', wind:{...(r?.wind ?? {})},
    parapet: r?.parapet_height_m ?? 1, load: r?.load_capacity_kn_m2 ?? 0.5, verified: r?.load_verified ?? false, outline: (r?.outline ?? []).map((q) => [...q]),
    items: JSON.parse(JSON.stringify([...(r?.obstacles ?? []).map((o) => zone(o, o.kind === "cylinder" ? "tank" : "device")),
      ...(r?.keepouts ?? []).map((k) => zone(k, "keepout")), ...(r?.surroundings ?? []).map((o) => zone(o, o.kind === "cylinder" ? "tree" : "building"))])),
    rect: asRect(r?.outline ?? []) ?? { w: 60, d: 36, turn: 0 }, drawing, dxf: null, basis: key(drawing), north: drawing?.calibration.north_deg ?? 0,
    mode: drawing ? 2 : !r || asRect(r.outline) ? 0 : 1, snap: !drawing, tool: null, clicks: [], sel: null, box: null, tilt: "", distance: "", past: [], future: [] };
  Object.assign(ed, { roofMode: r?.type === "metal" ? "metal-single" : "flat", slope: r?.slope_deg ?? 5,
    azimuth: r?.slope_azimuth_deg ?? 180, ridgeMode: "long", ridge: null, building: r?.building });
  const pitch = r?.pitched ?? {};
  Object.assign(ed, {pitchKind:pitch.kind ?? 'gable', planeMaterial:pitch.material ?? 'metal', teeth:pitch.teeth ?? 4,
    toothWidth:pitch.tooth_width_m ?? '', glassAngle:pitch.glass_deg ?? 70, seamSetback:r?.seam_setback_m ?? .5,
    planes:structuredClone(r?.planes ?? [])});
  if (r?.type === 'pitched') {
    Object.assign(ed, {roofMode:'pitched', slope:pitch.slope_deg ?? r.planes[0].slope_deg,
      azimuth:pitch.azimuth_deg ?? 180, ridgeMode:pitch.ridge_mode ?? 'long', ridge:pitch.ridge ?? null});
  }
  ed.planeSource = planeSource();
  Object.assign(ed, siteDefaults(r));
  Object.assign(ed, {use:r?.use ?? '', animal:r?.animal ?? 'sheep', groundSunMin:r?.ground_sun_min_pct ?? '',
    heightEdited:r?.ground?.lower_edge_m != null});
  if (isSite(r?.type)) ed.roofMode = r.type;
  for (const [kind, points] of [["inverter", r?.inverter_positions ?? []], ["grid", r?.grid_point ? [r.grid_point] : []]]) {
    points.forEach((center, i) => ed.items.push({kind, center, radius: 0, height: 0, id: `${kind}-${i}`, label: KINDS[kind][0]}));
  }
  if (!r) ed.outline = rectangle(ed.rect);
  ed.clean = text(FIELDS);
  ed.draft = readDraft();
  if (drawing) measure(drawing);
}
function measure(drawing) {
  const image = new Image();
  image.onload = () => {
    const clean = ed.clean === text(FIELDS);
    Object.assign(drawing, { width: image.naturalWidth, height: image.naturalHeight });
    if (clean) ed.clean = text(FIELDS);
    ed.box = null;
    draw();
  };
  image.src = drawing.url;
}
const pixelMode = () => Boolean(ed.drawing && !ed.drawing.calibration);
const dxfOrigin = () => [0, 1].map((k) => Math.min(...ed.dxf.outlines.flatMap((o) => o.points.map((p) => p[k]))));
const dxfPoint = (p) => rotate([0, 1].map((k) => (p[k] - dxfOrigin()[k]) * ed.dxf.scale), rad(ed.north)).map(round);
const centre = (it) => it.center ?? [0, 1].map((k) => it.points.reduce((s, p) => s + p[k], 0) / it.points.length);
const unit = () => 1 / (document.getElementById("re-svg")?.getScreenCTM()?.a || 1); // one screen pixel on the canvas

export function roofEditorPage(row) {
  load(row);
  return `<div class="head"><div><h1>${ed.id ? "编辑屋顶" : "新建屋顶"}</h1><p>画出屋顶，填好位置和真实数据；保存后在首页"我的屋顶"里，可以直接一键设计</p></div>
  <div class="re-actions"><a class="btn" href="#new">取消</a>${ed.id ? '<button class="btn" data-re-act="delete">删除这个屋顶</button>' : ""}
  <button class="btn primary" data-re-act="save">保存屋顶</button></div></div>
  <div class="re-layout" id="roofedit"><div class="card re-canvas"><div id="re-svg-host"></div><span class="re-north">北 ↑</span><span class="re-scale" id="re-scale"></span>
  <span class="re-tools"><button data-re-act="undo" title="撤销（Ctrl+Z）">↶</button><button data-re-act="redo" title="重做（Ctrl+Y）">↷</button>
  <label title="关掉后可以点在任意位置，适合描密集的转角"><input type="checkbox" data-re-check="snap"> 对齐 0.5 米</label></span>
  <span class="re-zoom"><button data-re-zoom="-1" title="缩小（也可以用滚轮）">－</button><button data-re-zoom="0" title="整个屋顶放进窗口">适合</button>
  <button data-re-zoom="1" title="放大">＋</button></span></div>${splitter("roof")}<div class="re-panel scroll" id="re-panel"></div></div>`;
}
export function mountRoofEditor(context) {
  ctx = context;
  const root = document.getElementById("roofedit"), host = document.getElementById("re-svg-host");
  root.parentElement.addEventListener("click", guard(onClick));
  root.addEventListener("input", guard(onInput));
  root.addEventListener("change", guard(onChange));
  root.addEventListener("focusin", (e) => e.target.matches("[data-re-rect],[data-vx],[data-vy],[data-len],[data-item],[data-re=north]") && record());
  host.addEventListener("pointerdown", guard(down));
  host.addEventListener("pointermove", guard(move));
  host.addEventListener("pointerup", guard(up));
  host.addEventListener("wheel", wheel, { passive: false });
  host.addEventListener("contextmenu", (e) => e.preventDefault());
  if (!bound) {
    bound = true;
    document.addEventListener("keydown", guard(onKey));
    addEventListener("beforeunload", (e) => leaving() && e.preventDefault());
  }
  fetch("/cities.json").then((r) => r.json()).then((data) => {
    cities = data.cities;
    panel();
  }).catch(() => {});
  panel();
  tilt();
}
// Runs at once, so a handler can still cancel the browser's default action; errors become a notice.
const guard = (fn) => (event) => {
  try {
    Promise.resolve(fn(event)).catch((error) => ctx.notice(error.message));
  } catch (error) {
    ctx.notice(error.message);
  }
};
const leaving = () => Boolean(ed && document.getElementById("roofedit") && text(FIELDS) !== ed.clean);
export const leaveRoofEditor = () => !leaving() || confirm("这个屋顶还没保存。离开后，没保存的修改会留作草稿，下次打开时可以恢复。确定离开？");

function record() { // remember the shapes before an edit, for undo
  const now = text(GEOMETRY);
  if (ed.past.at(-1) !== now) ed.past.push(now);
  ed.future = [];
}
function restore(from, to) {
  const now = text(GEOMETRY), file = ed.drawing?.file, upload = ed.drawing?.upload;
  let state = from.pop();
  while (state === now && from.length) state = from.pop();
  if (!state || state === now) return;
  to.push(now);
  JSON.parse(state).forEach((v, i) => (ed[GEOMETRY[i]] = v));
  if (ed.drawing && ed.drawing.upload === upload) ed.drawing.file = file; // a PDF can still change page after undo
  Object.assign(ed, { tool: null, clicks: [], sel: null });
}
const undo = () => (ed.tool === "outline" && ed.clicks.length ? ed.clicks.pop() : restore(ed.past, ed.future));
const redo = () => restore(ed.future, ed.past);
const draftKey = () => "gz.roof.draft." + (ed.id ?? "new");
function keepDraft() { // unsaved edits survive leaving the page or closing the app
  try {
    if (text(FIELDS) === ed.clean) localStorage.removeItem(draftKey());
    else localStorage.setItem(draftKey(), JSON.stringify({ at: Date.now(), state: text(FIELDS) }));
  } catch { /* storage blocked: undo and the leave prompt still work */ }
  ed.draft = null;
  document.querySelector(".re-draft")?.remove();
}
function readDraft() {
  try {
    const draft = JSON.parse(localStorage.getItem(draftKey()) ?? "null");
    return draft?.state && draft.state !== ed.clean ? draft : null;
  } catch {
    return null;
  }
}
const forget = () => {
  try { localStorage.removeItem(draftKey()); } catch { /* nothing kept */ }
};
function refresh() {
  panel();
  keepDraft();
}

function fit(svg) { // a view of the whole roof, its drawing and its surroundings, shaped like the canvas
  const d = ed.drawing, px = pixelMode(), pts = (px ? [[0, 0], [d.width ?? 100, d.height ?? 100]] : [...ed.outline, ...ed.clicks, ...(d?.calibration && d.width ?
    [[0, 0], [d.width, 0], [0, d.height], [d.width, d.height]].map((p) => toMetres(p, d.calibration)) : []), ...ed.items.flatMap((it) => it.points ?? [[it.center[0] -
    it.radius, it.center[1] - it.radius], [it.center[0] + it.radius, it.center[1] + it.radius]]), ...(ed.dxf?.outlines.flatMap((o) => o.points.map(dxfPoint)) ?? [])]
    .map(([x, y]) => [x, -y]));
  if (!pts.length) pts.push([0, -36], [60, 0]);
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]), [lx, hx, ly, hy] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const pad = Math.max(hx - lx, hy - ly, 10) * (px ? 0.04 : 0.3), aspect = (svg.clientHeight && svg.clientWidth / svg.clientHeight) || 1.6;
  let [w, h] = [Math.max(hx - lx, 10) + 2 * pad, Math.max(hy - ly, 10) + 2 * pad];
  [w, h] = w / h < aspect ? [h * aspect, h] : [w, w / aspect];
  ed.box = [(lx + hx - w) / 2, (ly + hy - h) / 2, w, h];
}
function zoom(f, [cx, cy] = [ed.box[0] + ed.box[2] / 2, ed.box[1] + ed.box[3] / 2]) {
  const [x0, y0, w, h] = ed.box;
  if (w * f >= 2 && w * f <= 1e5) ed.box = [cx - (cx - x0) * f, cy - (cy - y0) * f, w * f, h * f];
}
function draw() {
  updatePlanePreview();
  const host = document.getElementById("re-svg-host");
  if (!host || !ed) return;
  if (!document.getElementById("re-svg")) host.innerHTML = '<svg id="re-svg" role="img" aria-label="屋顶画布，北向上"><g id="re-image"></g><g id="re-grid"></g><g id="re-fg"></g></svg>';
  const svg = document.getElementById("re-svg"), px = pixelMode(), d = ed.drawing, pt = (p) => `${round(p[0])},${round(px ? p[1] : -p[1])}`;
  if (!ed.box) fit(svg);
  svg.setAttribute("viewBox", ed.box.join(" "));
  const [x0, y0, w, h] = ed.box, u = unit(), out = [], lines = [], tracing = ed.tool === "outline", choosing = ed.dxf && ed.dxf.picked == null;
  const s = d?.calibration ? scaleOf(d.calibration) : 1, image = d?.width && (px || d.calibration) ? `<g transform="rotate(${px ? 0 : -(num(d.calibration.north_deg) ??
    0)})"><image href="${esc(d.url)}" x="${px ? 0 : -d.calibration.p1_px[0] * s}" y="${px ? 0 : -d.calibration.p1_px[1] * s}" width="${d.width * s}"
    height="${d.height * s}" opacity="${px ? 1 : 0.55}"/></g>` : "";
  if (svg.dataset.image !== image) { // the drawing changes rarely: leave it alone while dragging
    document.getElementById("re-image").innerHTML = image;
    svg.dataset.image = image;
  }
  const step = [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000].find((g) => w / g <= 30) ?? 2000;
  for (let x = Math.ceil(x0 / step) * step; !px && x < x0 + w; x += step) lines.push(`M${round(x)} ${round(y0)}V${round(y0 + h)}`);
  for (let y = Math.ceil(y0 / step) * step; !px && y < y0 + h; y += step) lines.push(`M${round(x0)} ${round(y)}H${round(x0 + w)}`);
  document.getElementById("re-grid").innerHTML = lines.length ? `<path class="re-grid" d="${lines.join("")}"/>` : "";
  const stale = ed.drawing && ed.basis !== key(ed.drawing), bad = tracing || px ? [] : problems(ed.outline);
  if (!px && !choosing && !tracing && ed.outline.length) out.push(`<polygon class="re-roof${stale ? " stale" : ""}" points="${ed.outline.map(pt).join(" ")}"/>`);
  if (!px) out.push(siteDrawing(ed, pt, u));
  if (!px && ed.roofMode !== "flat") {
    const c = roofCentroid(ed.outline);
    out.push('<defs><marker id="re-slope" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">');
    out.push('<path d="M0 0L10 5L0 10Z" fill="#c87743"/></marker></defs>');
    const arrow = (start, a, label = `坡度 ${ed.slope}°`) => {
      const end = [start[0] + Math.sin(a) * u * 65, start[1] + Math.cos(a) * u * 65];
      out.push(`<path d="M${pt(start)}L${pt(end)}" stroke="#c87743" stroke-width="${u * 3}" marker-end="url(#re-slope)"/>`);
      out.push(`<text x="${start[0]}" y="${-start[1] - u * 10}" font-size="${u * 14}">${esc(label)}</text>`);
    };
    if (ed.roofMode === 'metal-single') {
      arrow(c, rad(ed.azimuth));
    }
    if (ed.roofMode === 'pitched' && ed.planeSource === planeSource()) {
      for (const p of ed.planes) {
        const color = p.material === 'glass' ? '#79bfd0' : p.material === 'concrete' ? '#d1c5b5' : '#cad4df';
        out.push(`<polygon data-roof-plane="${p.id}" points="${p.outline.map(pt).join(' ')}"
          fill="${color}" fill-opacity=".55" stroke="#596574" stroke-width="${u * 2}"/>`);
      }
      for (const p of ed.planes) {
        const center = roofCentroid(p.outline), angle = rad(p.slope_azimuth_deg);
        if (p.material === 'glass') {
          center[0] += Math.cos(angle) * u * 85;
          center[1] -= Math.sin(angle) * u * 85;
        }
        arrow(center, angle, `P${p.id} ${p.slope_deg}°${p.material === 'glass' ? ' 玻璃' : ''}`);
      }
    }
    if (ed.roofMode === "metal-gable") {
      const ridge = ed.ridge ?? defaultRidge();
      out.push(`<polyline class="re-ridge" points="${ridge.map(pt).join(" ")}" stroke="#c87743" stroke-width="${u * 3}"/>`);
      if (ridge.length === 2) {
        const angle = Math.atan2(ridge[1][1] - ridge[0][1], ridge[1][0] - ridge[0][0]);
        for (const sign of [-1, 1]) {
          arrow([c[0] - Math.sin(angle) * u * 30 * sign, c[1] + Math.cos(angle) * u * 30 * sign],
            Math.atan2(-Math.sin(angle) * sign, Math.cos(angle) * sign));
        }
      }
    }
  }
  ed.dxf?.outlines.forEach((o, i) => ed.dxf.used.includes(i) || out.push(`<polygon class="re-cand" data-cand="${i}" points="${o.points.map((p) => pt(dxfPoint(p))).join(" ")}"/>`));
  (px || choosing ? [] : ed.items).forEach((it, i) => {
    const [cx, cy] = centre(it);
    const shapeClass = KINDS[it.kind][2] === "point" ? "re-electrical" : "re-" + it.kind;
    const labelY = -cy - (shapeClass === "re-electrical" ? 10 * u : 0);
    out.push(it.center ? `<circle class="${shapeClass}" data-shape="${i}" cx="${cx}" cy="${-cy}" r="${it.radius || 5 * u}"/>` :
      `<polygon class="re-${it.kind}" data-shape="${i}"
      points="${it.points.map(pt).join(" ")}"/>`,
      `<text x="${round(cx)}" y="${round(labelY)}" font-size="${round(u * 12)}" text-anchor="middle">${esc(it.label)}</text>`);
  });
  const last = ed.clicks.at(-1), hover = ed.tool && !px ? ed.hover : null;
  if (tracing && last) out.push(`<polyline class="re-trace" points="${[...ed.clicks, ...(hover ? [hover] : [])].map(pt).join(" ")}"/>`);
  if (tracing && last && hover) out.push(`<text class="re-len" x="${round((last[0] + hover[0]) / 2)}" y="${round(-(last[1] + hover[1]) / 2 - u * 8)}"
    font-size="${round(u * 12)}" text-anchor="middle">${round(Math.hypot(hover[0] - last[0], hover[1] - last[1]))} m</text>`);
  ed.clicks.forEach((p, i) => out.push(`<circle class="re-dot${tracing && !i && ed.clicks.length > 2 ? " first" : ""}" cx="${p[0]}" cy="${px ? p[1] : -p[1]}"
    r="${round(u * (tracing && !i ? 6 : 4))}"/>`));
  if (!px && !choosing && !tracing && ed.mode && ed.outline.length) {
    ed.outline.forEach((p, i) => {
      const q = ed.outline[(i + 1) % ed.outline.length];
      out.push(`<circle class="re-mid" data-mid="${i}" cx="${(p[0] + q[0]) / 2}" cy="${-(p[1] + q[1]) / 2}" r="${round(u * 4)}"><title>拖动或点一下，在这里加一个角</title></circle>`);
    });
    ed.outline.forEach((p, i) => out.push(`<rect class="re-h${ed.sel === i ? " on" : ""}" data-v="${i}" x="${p[0] - u * 5}" y="${-p[1] - u * 5}" width="${u * 10}"
      height="${u * 10}"><title>角 ${i + 1}：拖动改位置；选中后按 Delete 删除</title></rect>`));
  }
  bad.forEach((b) => b.at && out.push(`<circle class="re-bad" cx="${b.at[0]}" cy="${-b.at[1]}" r="${round(u * 8)}"/>`));
  document.getElementById("re-fg").innerHTML = out.join("");
  document.getElementById("re-scale").textContent = px ? "图纸原图（还没定比例）" : `每格 ${step} 米`;
  const size = document.getElementById("re-size"), list = document.getElementById("re-problems"), snap = document.querySelector('[data-re-check="snap"]');
  if (size) size.textContent = sizeText();
  if (list) list.innerHTML = bad.map((b) => `<p>⚠ ${esc(b.text)}</p>`).join("");
  if (snap) snap.checked = ed.snap;
  for (const input of document.querySelectorAll("#re-panel [data-vx],#re-panel [data-vy],#re-panel [data-len]")) { // keep the table in step while dragging
    const o = ed.outline, i = Number(input.dataset.vx ?? input.dataset.vy ?? input.dataset.len), q = o[(i + 1) % o.length];
    if (input !== document.activeElement && o[i]) input.value = round(input.dataset.len ? Math.hypot(q[0] - o[i][0], q[1] - o[i][1]) : o[i][input.dataset.vx ? 0 : 1]);
  }
}
function sizeText() {
  if (ed.outline.length < 3) return "还没有外形";
  const xs = ed.outline.map((p) => p[0]), ys = ed.outline.map((p) => p[1]);
  return `${area(ed.outline).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} m² · ${round(Math.max(...xs) - Math.min(...xs))} × ${round(Math.max(...ys) - Math.min(...ys))} m`;
}

function field(key, label, unit, value, attr = "data-re", disabled = false) {
  return `<label class="field"><span>${label}</span><span class="inbox"><input ${attr}="${key}" type="number" step="any" value="${esc(value ?? "")}" ${disabled ?
    "disabled" : ""}><span>${unit}</span></span></label>`;
}
const button = (label, act, cls = "") => `<button class="btn sm ${cls}" data-re-act="${act}">${label}</button>`;
const when = (at) => new Date(at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
function panel() {
  const host = document.getElementById("re-panel");
  if (!host) return;
  const city = cities.find((c) => c.lat === num(ed.lat) && c.lon === num(ed.lon));
  const options = ["江苏", "其他"].map((group) => `<optgroup label="${group === "江苏" ? "江苏" : "各省会和直辖市"}">${cities.filter((c) => (c.province === "江苏") === (group === "江苏"))
    .map((c) => `<option value="${esc(c.name)}" ${c === city ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</optgroup>`).join("");
  host.innerHTML = `${ed.draft ? `<div class="card re-draft"><span>有一份 ${esc(when(ed.draft.at))} 没保存的修改</span>${button("恢复", "draft-restore", "primary")}${button("丢掉",
    "draft-drop")}</div>` : ""}<section class="card re-step"><h3><b>1</b>位置</h3><label class="field"><span>城市（经纬度来自 OpenStreetMap）</span>
    <select id="re-city" class="sel"><option value="">${city ? "" : "自己填经纬度"}</option>${options}</select></label>
    <div class="grid2">${field("lat", "纬度", "°N", ed.lat)}${field("lon", "经度", "°E", ed.lon)}</div><p id="re-tilt" class="muted re-note">${esc(ed.tilt)}</p></section>
  <section class="card re-step"><h3><b>2</b>外形</h3><div class="seg">${MODES.map((m, i) => `<button data-re-mode="${i}" aria-pressed="${ed.mode === i}" ${pixelMode() &&
    i !== 2 ? 'disabled title="先给图纸定比例"' : ""}>${m}</button>`).join("")}</div>${[rectPanel, pointPanel, importPanel][ed.mode]()}<div id="re-problems" class="re-bad"></div></section>
  <section class="card re-step"><h3><b>3</b>障碍和遮挡</h3><div class="re-adds">${Object.entries(KINDS).map(([k, [label]]) =>
    `<button class="btn sm" data-re-tool="${k}" aria-pressed="${ed.tool === k}">＋ ${label}</button>`).join("")}</div>
    <p class="muted re-note">${ed.tool && ed.tool !== "outline" ? (KINDS[ed.tool][2] === "point" ? "点一下放置；并网点只保留一个。" :
    KINDS[ed.tool][2] === "rect" ? "在左边图上点两下：先点一个角，再点对角。" : "在左边图上点两下：先点圆心，再点边上一点。") :
      "屋面设备、天窗等禁区会躲开不排；屋顶外的楼和树按高出屋面多少米算阴影。放好后可以在图上拖动。"}</p>
    <div class="re-items">${ed.items.map(itemRow).join("")}</div></section>
  <section class="card re-step"><h3><b>4</b>安装面数据</h3><label class="field"><span>安装面名称</span><span class="inbox">
    <input data-re="name" maxlength="40" value="${esc(ed.name)}" placeholder="例如：常州某厂 5 号厂房"></span></label>
    ${isSite(ed.roofMode) ? `<p>平坦地坪基准0米；基础与钢结构须厂家设计。<b id="re-size">${sizeText()}</b></p>` :
    `<div class="grid2">${field("height", ed.roofMode === 'flat' ? "屋面离地高度" : "檐口（最低边）离地高度", "m", ed.height)}
    ${field("parapet", "女儿墙高度（没有填 0）", "m", ed.parapet)}
    ${field("load", "允许附加荷载", "kN/m²", ed.load)}<div class="field"><span>面积和外形尺寸</span><b id="re-size" class="re-size">${sizeText()}</b></div></div>
    <label class="toggle"><span>荷载经过结构核定（有计算书或厂方书面确认）</span>
      <input type="checkbox" data-re-check="verified" ${ed.verified ? "checked" : ""}></label>`}
    ${metalPanel()}${usePanel()}${windPanel()}<p class="muted re-note">结构输入须现场核实，示意量不能代替施工设计。</p></section>`;
  draw();
}
function windPanel() {
  const fields = [['basic_pressure_kpa', '50年基本风压', 'kPa', '按城市示意值'],
    ['friction', '滑移摩擦系数', '', .5], ['block_kg', '单块压块质量', 'kg', 15]];
  if (isSite(ed.roofMode)) fields.splice(1);
  if (!isSite(ed.roofMode) && ed.roofMode !== 'flat') fields.push(['clamp_capacity_kn', '单夹具设计抗拔力', 'kN', .8],
    ['seam_spacing_m', '板缝间距', 'm', .5], ['seam_azimuth_deg', '板缝朝向', '°', '默认顺坡'],
    ['seam_offset_m', '板缝偏移', 'm', 0], ['clamp_min_spacing_m', '夹具最小安装距离', 'm', .2],
    ['clamp_max_spacing_m', '夹具最大允许间距', 'm', 1.2], ['clamp_edge_m', '夹具离组件边缘', 'm', .1]);
  const citiesOptions = cities.filter(c => c.province === '江苏').map(c =>
    `<option ${ed.windCity === c.name ? 'selected' : ''}>${esc(c.name)}</option>`).join('');
  return `<details class="wind-input"><summary>风荷载参数（示意，现场复核）</summary><p>缺标准原表，不能代替结构计算。</p>
    <label>风压城市<select data-re="windCity"><option value="">最近市中心推定（非行政归属）</option>${citiesOptions}</select></label>
    <label>粗糙度<select data-wind="roughness">${['A', 'B', 'C', 'D'].map(v =>
    `<option ${(ed.wind.roughness ?? 'B') === v ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
    <p>默认B，工业区可能C；外省请按当地复核值填写。板缝偏移以屋顶坐标原点为基准。</p><div class="grid2">${fields.map(([key, label, unit, value]) =>
    `<label class="field">${label}（示意）<input data-wind="${key}" type="number" step="any"
    value="${esc(ed.wind[key] ?? '')}" placeholder="${esc(value)}">${unit}</label>`).join('')}</div></details>`;
}
function usePanel() {
  const allowed = ed.roofMode === 'ground' ? 'grazing' : ['metal-single','metal-gable','pitched'].includes(ed.roofMode) ? 'barn' : '';
  if (!allowed) return '';
  const title = allowed === 'barn' ? '养殖场棚顶' : '牧光互补';
  return `<label>用途<select data-re="use"><option value="">普通用途</option>
    <option value="${allowed}" ${ed.use === allowed ? 'selected' : ''}>${title}</option></select></label>
    ${ed.use === 'barn' ? '<p>通风口、采光带预设默认四周避让1米，可逐个改为0；防腐夹具导轨及清洗默认值均为示意。</p>' : ''}
    ${ed.use === 'grazing' ? `<label>牲畜<select data-re="animal">
    <option value="sheep" ${ed.animal === 'sheep' ? 'selected' : ''}>羊（示意最低1.5米）</option>
    <option value="cow" ${ed.animal === 'cow' ? 'selected' : ''}>牛（示意最低2.5米）</option></select></label>
    ${field('groundSunMin','地面全年平均受光比例下限（示意，缺省50）','%',ed.groundSunMin)}
    <p>已保存或手填的最低边高度保持原值；低于牲畜示意高度会报G08。牧草地须核实用地手续，不得占耕地和基本草原。</p>` : ''}`;
}
function metalPanel() {
  const modes = [['flat', '混凝土平屋顶'], ['pitched', '斜屋面整栋（单/双/四坡/锯齿）'],
    ['ground', '空地（新建安装）'], ['carport', '停车场车棚（新建安装）'],
    ['metal-single', '彩钢瓦单坡（兼容）'], ['metal-gable', '彩钢瓦双坡（拆成两个，兼容）']];
  if (ed.roofMode === 'pitched') return pitchedPanel(modes);
  if (isSite(ed.roofMode)) return sitePanel(ed, modes, button);
  return `<label class="field">屋面类型<select data-re="roofMode">${modes.map(([v, t]) =>
    `<option value="${v}" ${ed.roofMode === v ? "selected" : ""}>${t}</option>`).join("")}</select></label>${ed.roofMode === "flat" ? "" :
    `${field("slope", "坡度（1–30°）", "°", ed.slope)}${ed.roofMode === 'metal-single' ?
    `${field("azimuth", "顺坡下行朝向（0–360°）", "°", ed.azimuth)}
    <div class="seg">${["北", "东北", "东", "东南", "南", "西南", "西", "西北"].map((t, i) =>
      button(t, "azimuth-" + i * 45)).join("")}</div>` : '<p>坡向由屋脊自动确定。</p>'}${ed.roofMode === "metal-gable" ?
      `<label class="field">屋脊<select data-re="ridgeMode"><option value="long">沿长边中心</option>
      <option value="short" ${ed.ridgeMode === "short" ? "selected" : ""}>沿短边中心</option></select></label>
      ${button("手画屋脊（点两个点）", "ridge")}<p>跨屋脊的设备和采光带请分成两个；两坡独立保存。</p>` : ""}`}`;
}
function pitchedPanel(modes) {
  const options = (rows, value) => rows.map(([v, label]) => `<option value="${v}" ${v === value ? 'selected' : ''}>${label}</option>`).join('');
  return `<label class="field">屋面类型<select data-re="roofMode">${options(modes, ed.roofMode)}</select></label>
    <label class="field">整栋屋型<select data-re="pitchKind">${options([
      ['single','单坡'],['gable','双坡'],['hip','四坡（矩形）'],['sawtooth','锯齿形']], ed.pitchKind)}</select></label>
    <label class="field">默认安装面材料<select data-re="planeMaterial">${options([
      ['metal','彩钢瓦'],['concrete','混凝土']], ed.planeMaterial)}</select></label>
    ${field('slope','安装面坡度（大于0、小于90）','°',ed.slope)}
    ${['single','sawtooth'].includes(ed.pitchKind) ? field('azimuth','顺坡下行方向','°',ed.azimuth) : ''}
    ${ed.pitchKind === 'gable' ? `<label class="field">屋脊<select data-re="ridgeMode">
      ${options([['long','沿长边居中'],['short','沿短边居中']], ed.ridgeMode)}</select></label>
      ${button('手画屋脊（点两个点）','ridge')}<p>偏心屋脊保持共面接缝，较短一侧檐边自动抬高，见逐面偏移。</p>` : ''}
    ${ed.pitchKind === 'sawtooth' ? `${field('teeth','齿数','',ed.teeth)}${field('toothWidth','齿宽（可空，优先于齿数）','m',ed.toothWidth)}
      ${field('glassAngle','陡玻璃面角度','°',ed.glassAngle)}` : ''}
    ${field('seamSetback','屋脊/斜脊/天沟两侧退让（示意）','m',ed.seamSetback)}
    <p id="re-plane-note">${esc(ed.planeMessage ?? '各面共用一个檐口基准，保存前检查2厘米拼接容差。')}</p>
    <details><summary>逐面材料、角度与承重</summary><div id="re-planes">${planeRows()}</div></details>`;
}
function rectPanel() {
  const free = ed.outline.length > 0 && !asRect(ed.outline);
  return `${free ? `<p class="re-warn">现在的外形不是矩形（${ed.outline.length} 个角），改尺寸前不会动它。要换成矩形就点下面的按钮，原来的外形可以按 ↶ 撤销恢复。</p>
  <div class="re-row">${button("换成矩形", "to-rect")}</div>` : ""}<div class="grid2">${field("w", "长（东西向）", "m", ed.rect.w, "data-re-rect", free)}${field("d",
    "宽（南北向）", "m", ed.rect.d, "data-re-rect", free)}${field("turn", "整体旋转（逆时针为正）", "°", ed.rect.turn, "data-re-rect", free)}</div>
  <p class="muted re-note">改数字左边马上变。厂房不是正南正北摆的，就填旋转角。</p>`;
}
const tracing = () => `<p class="re-live">正在画：已点 ${ed.clicks.length} 个角。点回第一个角（绿点）或按 Enter 闭合；Backspace 撤销上一点；Esc 取消，原来的外形不变。
  按住 Shift 画横平竖直或 45° 的边。</p><div class="re-row">${button("完成外形", "close", "primary")}${button("撤销上一点", "undo")}${button("取消", "cancel")}</div>`;
function pointPanel() {
  if (ed.tool === "outline") return tracing();
  return `<p class="muted re-note">点「${ed.outline.length ? "重新画外形" : "开始画外形"}」，在左边依次点屋顶的每个角。画好后直接拖角点改位置；点边中间的小圆点加一个角；
  选中角按 Delete 删除；也可以在下表里改坐标或边长。滚轮缩放，拖空白处平移。</p><div class="re-row">${button(ed.outline.length ? "重新画外形" : "开始画外形", "trace",
    "primary")}</div>${table()}`;
}
function table() {
  const o = ed.outline, n = o.length;
  return n ? `<div class="re-vertices"><span></span><span>x 向东 m</span><span>y 向北 m</span><span>到下一角 m</span><span></span>${o.map(([x, y], i) =>
    `<span class="${ed.sel === i ? "on" : ""}">角 ${i + 1}</span><input data-vx="${i}" type="number" step="any" value="${round(x)}"><input data-vy="${i}" type="number" step="any"
    value="${round(y)}"><input data-len="${i}" type="number" step="any" min="0" value="${round(Math.hypot(o[(i + 1) % n][0] - x, o[(i + 1) % n][1] - y))}">
    <span class="re-vacts"><button data-re-ins="${i}" title="在这条边中间加一个角">＋</button><button data-re-del="${i}" title="删掉这个角">×</button></span>`).join("")}</div>` : "";
}
function importPanel() {
  const d = ed.drawing, c = d?.calibration, north = field("north", "图上的北方向（从图纸正上方顺时针量，看指北针）", "°", ed.north);
  const steps = ed.tool === "outline" ? tracing() : ed.dxf?.picked != null ? `<p class="muted re-note">外轮廓选好了。图里其他闭合图形如果是天窗、设备基础这类不能放板的地方，
    点一下就设为禁区；没有就点「完成」。</p><div class="re-row">${button("完成", "dxf-done", "primary")}</div>` : ed.dxf ? `<p class="muted re-note">左边是图里所有闭合多段线
    （按面积从大到小，最多 30 个；圆弧已按弧线算进去）。先点屋顶外轮廓。</p><label class="field"><span>图纸单位</span><select id="re-unit" class="sel">${DXF_UNITS.map(([s, n]) =>
    `<option value="${s}" ${s === ed.dxf.scale ? "selected" : ""}>${n}</option>`).join("")}</select></label>${north}` : !d ? `<p class="muted re-note">建筑图、结构图、卫星截图都行。
    图片和 PDF 先定比例再描边；CAD 的 DXF 直接点选外轮廓。</p>` : !c ? `<p class="muted re-note">第 1 步定比例：在图上点两个知道实际距离的点（比如屋顶两端，或标了尺寸的两点）。
    已点 ${ed.clicks.length} 个。${d.previous ? "重新定比例后，屋顶、设备和周边楼树会跟着图纸一起缩放，位置不变。" : ""}</p>${ed.clicks.length === 2 ? `${field("distance",
    "这两点实际相距", "m", ed.distance)}${north}<div class="re-row">${button("确定比例", "calibrate", "primary")}${button("重新点", "reclick")}</div>` : ""}${d.previous ?
    `<div class="re-row">${button("取消，用原来的比例", "keep-scale")}</div>` : ""}` : `<p class="muted re-note">比例已定（1 米 ≈ ${round(1 / scaleOf(c))} 像素）。${ed.basis ===
    key(d) ? "屋顶外形已对好这张图，可以直接拖角点微调。" : "第 2 步：点「开始描边」，沿屋顶外边依次点每个角。如果左边虚线的外形已经和图对上，点「沿用现在的外形」。"}</p>
    <div class="re-row">${button(ed.basis === key(d) ? "重新描边" : "开始描边", "trace", "primary")}${ed.basis !== key(d) && ed.outline.length ? button("沿用现在的外形",
    "adopt") : ""}${button("重新定比例", "recalibrate")}</div>${north}${table()}`;
  return `<div class="re-row"><label class="btn sm">选择图纸（图片、PDF、DXF）<input id="re-file" type="file" accept=".png,.jpg,.jpeg,.bmp,.webp,.pdf,.dxf" hidden></label>
  ${d?.pages > 1 ? `<label class="re-page">第 <input id="re-page" type="number" min="1" max="${d.pages}" value="${d.page}"> 页，共 ${d.pages} 页</label>` : ""}${d ?
    button("去掉图纸", "drop", "ghost") : ""}</div>${steps}`;
}
function itemRow(it, i) {
  return `<div class="re-item"><span class="chip line">${KINDS[it.kind][0]}</span><input data-item="${i}" data-key="label" maxlength="30" value="${esc(it.label)}" aria-label="名称">
  ${KINDS[it.kind][1] === 'keepouts' ? `<label>避让m<input data-item="${i}" data-key="clearance" type="number"
    min="0" step="any" value="${esc(it.clearance ?? '')}" placeholder="${ed.use === 'barn' && it.preset ? 1 : '默认'}"></label>` :
    KINDS[it.kind][2] === "point" ? "<span></span>" : `<span class="inbox"><input data-item="${i}" data-key="height"
    type="number" step="any" value="${esc(it.height)}" aria-label="高出屋面"><span>m 高</span></span>`}
  <button class="btn sm ghost" data-re-remove="${i}" aria-label="删除">删除</button></div>`;
}

function point(event, straight = false) {
  const svg = document.getElementById("re-svg"), p = svg.createSVGPoint();
  [p.x, p.y] = [event.clientX, event.clientY];
  const q = p.matrixTransform(svg.getScreenCTM().inverse()), prev = ed.tool === "outline" && ed.clicks.at(-1);
  if (pixelMode()) return [round(q.x), round(q.y)];
  let [x, y] = [q.x, -q.y];
  if (straight && prev) { // Shift: the new edge runs east-west, north-south or at 45 degrees
    const a = Math.round(Math.atan2(y - prev[1], x - prev[0]) / (Math.PI / 4)) * Math.PI / 4, r = Math.hypot(x - prev[0], y - prev[1]);
    [x, y] = [prev[0] + r * Math.cos(a), prev[1] + r * Math.sin(a)];
  }
  const snap = ed.snap ? 0.5 : 0.01;
  return [round(Math.round(x / snap) * snap), round(Math.round(y / snap) * snap)];
}
function addItem(kind, [a, b], points = [a, [b[0], a[1]], b, [a[0], b[1]]]) {
  const [label, , shape, height, prefix] = KINDS[kind], n = 1 + Math.max(0, ...ed.items.filter((it) => it.id.startsWith(prefix + "-")).map((it) => Number(it.id.split("-")[1]) || 0));
  const radius = round(Math.hypot(b[0] - a[0], b[1] - a[1]));
  if (shape === "point") {
    if (kind === "grid") ed.items = ed.items.filter(it => it.kind !== "grid");
    ed.items.push({id: `${prefix}-${n}`, kind, label, center: a, radius: 0, height: 0});
    return;
  }
  if (shape === "circle" ? radius <= 0 : area(points) <= 0) throw new Error("两下点在了同一处，换个位置再点");
  ed.items.push({ id: `${prefix}-${n}`, kind, label: `${label}${n}`, height,
    ...(ed.use === 'barn' && ['vent','skylight'].includes(kind) ? {preset:kind} : {}),
    ...(shape === "circle" ? { center: a, radius } : { points }) });
}
function pick(index) {
  record();
  const points = ed.dxf.outlines[index].points.map(dxfPoint);
  if (ed.dxf.picked == null) Object.assign(ed, { outline: points, dxf: { ...ed.dxf, picked: index } });
  else addItem("keepout", points.slice(0, 2), points);
  ed.dxf.used.push(index);
}
function insertCorner(i) { // a new corner in the middle of the edge after corner i
  record();
  const [a, b] = [ed.outline[i], ed.outline[(i + 1) % ed.outline.length]];
  ed.outline.splice(i + 1, 0, [round((a[0] + b[0]) / 2), round((a[1] + b[1]) / 2)]);
  return (ed.sel = i + 1);
}
function removeCorner(i) {
  if (ed.outline.length <= 3) throw new Error("外形至少要 3 个角，不能再删了");
  record();
  ed.outline.splice(i, 1);
  ed.sel = null;
}
function closeOutline() {
  const bad = problems(ed.clicks);
  if (bad.length) throw new Error(`${bad[0].text}（还在画，可以按 Backspace 撤销上一点）`);
  record();
  Object.assign(ed, { outline: ed.clicks, clicks: [], tool: null, sel: null, basis: key(ed.drawing) });
}
function retransform(from, to) { // keep every shape on the same spot of the drawing when its scale, origin or north changes
  const k = scaleOf(to) / scaleOf(from);
  const f = (p) => {
    if (ed.roofMode !== 'carport') return toMetres(toPixels(p, from), to);
    const [u, v] = toPixels(p, from);
    return rotate([(u - to.p1_px[0]) * scaleOf(to), (to.p1_px[1] - v) * scaleOf(to)], rad(to.north_deg)).map(fine);
  };
  const next = structuredClone({outline:ed.outline, items:ed.items, planes:ed.planes, carport:ed.carport});
  next.outline = next.outline.map(f);
  for (const item of next.items) {
    if (item.center) Object.assign(item, {center:f(item.center), radius:round(item.radius * k)});
    else item.points = item.points.map(f);
  }
  if (ed.roofMode === 'carport') {
    const a = f([0,0]), b = f([1,0]), turn = Math.atan2(b[1]-a[1], b[0]-a[0]) * 180 / Math.PI;
    for (const plane of next.planes) {
      plane.outline = plane.outline.map(f);
      plane.slope_azimuth_deg = (plane.slope_azimuth_deg - turn + 360) % 360;
    }
    for (const key of ['bays','aisles','strips']) for (const item of next.carport[key]) item.polygon = item.polygon.map(f);
    for (const key of Object.keys(next.carport.columns)) next.carport.columns[key] = next.carport.columns[key].map(f);
    if (next.carport.direction_deg != null) next.carport.direction_deg = (next.carport.direction_deg + turn + 360) % 360;
  }
  Object.assign(ed, next);
}
async function onClick(event) {
  if (event.target.closest("#re-svg-host")) return;
  const el = event.target.closest("[data-re-act],[data-re-mode],[data-re-tool],[data-re-remove],[data-re-ins],[data-re-del],[data-re-zoom]");
  if (!el) return;
  const act = el.dataset.reAct, d = ed.drawing;
  if (act?.startsWith("azimuth-")) {
    ed.azimuth = Number(act.slice(8));
    return refresh();
  }
  if (act === "ridge") {
    Object.assign(ed, { tool: "ridge", clicks: [] });
    return draw();
  }
  if (el.dataset.reZoom) {
    const z = Number(el.dataset.reZoom);
    z ? zoom(z > 0 ? 2 / 3 : 1.5) : (ed.box = null);
    return draw();
  }
  if (el.dataset.reMode) { // only shows another way of drawing: the shape stays as it is
    Object.assign(ed, { mode: Number(el.dataset.reMode), tool: null, clicks: [], sel: null });
    if (ed.mode === 0 && !ed.outline.length) {
      record();
      ed.outline = rectangle(ed.rect);
    } else if (ed.mode === 0) ed.rect = asRect(ed.outline) ?? ed.rect;
  } else if (el.dataset.reTool) {
    if (ed.tool === "outline") throw new Error("先完成或取消正在画的外形");
    Object.assign(ed, { tool: ed.tool === el.dataset.reTool ? null : el.dataset.reTool, clicks: [], sel: null });
  } else if (el.dataset.reRemove) {
    record();
    ed.items.splice(Number(el.dataset.reRemove), 1);
  } else if (el.dataset.reIns) insertCorner(Number(el.dataset.reIns));
  else if (el.dataset.reDel) removeCorner(Number(el.dataset.reDel));
  else if (act === "dxf-done") ed.dxf = null;
  else if (act === "trace") Object.assign(ed, { tool: "outline", clicks: [], sel: null });
  else if (act === "close") closeOutline();
  else if (act === "cancel") Object.assign(ed, { tool: null, clicks: [] });
  else if (act === "undo") undo();
  else if (act === "redo") redo();
  else if (act === "reclick") ed.clicks = [];
  else if (act === "recalibrate") {
    record();
    Object.assign(d, { previous: d.calibration, calibration: null });
    Object.assign(ed, { clicks: [], tool: null, box: null });
  } else if (act === "keep-scale") {
    Object.assign(d, { calibration: d.previous, previous: null });
    Object.assign(ed, { clicks: [], box: null });
  } else if (act === "calibrate") {
    if (!(num(ed.distance) > 0)) throw new Error("填这两点的实际距离（米）");
    record();
    const calibration = { p1_px: ed.clicks[0], p2_px: ed.clicks[1], distance_m: num(ed.distance), north_deg: num(ed.north) ?? 0 };
    if (d.previous) retransform(d.previous, calibration);
    Object.assign(d, { calibration, previous: null });
    Object.assign(ed, { clicks: [], box: null });
  } else if (act === "adopt") {
    record();
    ed.basis = key(d);
  } else if (act === "drop") {
    record();
    Object.assign(ed, { drawing: null, basis: null, box: null, clicks: [], tool: null });
  } else if (act === "to-rect") {
    record();
    ed.outline = rectangle(ed.rect);
  } else if (act === "draft-restore") {
    record();
    JSON.parse(ed.draft.state).forEach((v, i) => (ed[FIELDS[i]] = v));
    Object.assign(ed, { draft: null, box: null, tool: null, clicks: [], sel: null });
    if (ed.drawing && !ed.drawing.width) measure(ed.drawing);
    tilt();
  } else if (act === "draft-drop") {
    forget();
    ed.draft = null;
  } else if (act === 'parking-build') {
    record();
    const body = payload().roof;
    const result = await ctx.post('parking', {outline:ed.outline, settings:ed.carport,
      obstacles:body.obstacles, keepouts:body.keepouts});
    Object.assign(ed, result);
  } else if (act?.startsWith('canopy-delete-')) {
    record();
    ed.planes = ed.planes.filter(p => p.id !== Number(act.slice(14)));
  } else if (act === "save") return save();
  else if (act === "delete") return remove();
  refresh();
}
function down(e) {
  const t = e.target;
  drag = { x: e.clientX, y: e.clientY, k: unit(), box: [...ed.box], target: t, pan: e.button !== 0 };
  if (!drag.pan && !ed.tool && !pixelMode()) {
    if (t.dataset.v) {
      record();
      drag.vertex = ed.sel = Number(t.dataset.v);
    } else if (t.dataset.mid) drag.vertex = insertCorner(Number(t.dataset.mid));
    else if (t.dataset.shape) {
      record();
      Object.assign(drag, { item: Number(t.dataset.shape), at: point(e), orig: JSON.stringify(ed.items[Number(t.dataset.shape)]) });
    }
  }
  e.currentTarget.setPointerCapture(e.pointerId);
  draw();
}
function move(e) {
  if (!ed?.box) return;
  if (ed.tool) ed.hover = point(e, e.shiftKey);
  if (drag) {
    const [dx, dy] = [e.clientX - drag.x, e.clientY - drag.y];
    drag.moved ||= Math.hypot(dx, dy) > 4;
    if (!drag.moved) return ed.tool && draw();
    if (drag.vertex != null) ed.outline[drag.vertex] = point(e);
    else if (drag.item != null) {
      const it = ed.items[drag.item], o = JSON.parse(drag.orig), p = point(e), shift = ([x, y]) => [round(x + p[0] - drag.at[0]), round(y + p[1] - drag.at[1])];
      it.center ? (it.center = shift(o.center)) : (it.points = o.points.map(shift));
    } else ed.box = [drag.box[0] - dx * drag.k, drag.box[1] - dy * drag.k, drag.box[2], drag.box[3]];
  } else if (!ed.tool) return;
  draw();
}
function up(e) {
  const d = drag;
  drag = null;
  if (!d) return;
  if (d.vertex != null || d.item != null) return refresh(); // a corner or item was dragged, inserted or picked
  if (d.moved || d.pan) return draw();
  canvasClick(e, d.target);
}
function wheel(e) {
  e.preventDefault();
  if (!ed?.box) return;
  const svg = document.getElementById("re-svg"), p = svg.createSVGPoint();
  [p.x, p.y] = [e.clientX, e.clientY];
  const q = p.matrixTransform(svg.getScreenCTM().inverse());
  zoom(Math.exp(Math.max(-0.5, Math.min(0.5, e.deltaY * 0.0015))), [q.x, q.y]);
  draw();
}
function canvasClick(e, target) {
  if (target.dataset.cand) {
    pick(Number(target.dataset.cand));
    return refresh();
  }
  const p = point(e, e.shiftKey), last = ed.clicks.at(-1);
  if (pixelMode()) {
    if (ed.clicks.length < 2) ed.clicks.push(p);
    return refresh();
  }
  if (!ed.tool) {
    ed.sel = null;
    return refresh();
  }
  if (KINDS[ed.tool]?.[2] === "point") {
    record();
    addItem(ed.tool, [p, p]);
    ed.tool = null;
    return refresh();
  }
  if (last && last[0] === p[0] && last[1] === p[1]) return;
  if (ed.tool === "outline") {
    const first = ed.clicks[0];
    if (ed.clicks.length > 2 && Math.hypot(p[0] - first[0], p[1] - first[1]) < 10 * unit()) closeOutline();
    else ed.clicks.push(p);
    return refresh();
  }
  ed.clicks.push(p);
  if (ed.tool === "ridge" && ed.clicks.length === 2) {
    Object.assign(ed, { ridge: ed.clicks, clicks: [], tool: null });
    return refresh();
  }
  if (ed.clicks.length === 2) {
    const [kind, clicks] = [ed.tool, ed.clicks];
    Object.assign(ed, { clicks: [], tool: null });
    record();
    addItem(kind, clicks);
    return refresh();
  }
  draw();
}
function onKey(e) {
  if (!ed || !document.getElementById("roofedit") || e.target.closest?.("input, select, textarea")) return;
  const k = e.key, tracing = ed.tool === "outline";
  if ((e.ctrlKey || e.metaKey) && /^[zy]$/i.test(k)) (/y/i.test(k) || e.shiftKey ? redo : undo)();
  else if (tracing && k === "Enter") closeOutline();
  else if (tracing && k === "Backspace") ed.clicks.pop();
  else if (k === "Escape") Object.assign(ed, { tool: null, clicks: [], sel: null });
  else if (["Delete", "Backspace"].includes(k) && ed.sel != null) {
    e.preventDefault();
    removeCorner(ed.sel);
  } else return;
  e.preventDefault();
  refresh();
}
function onInput(event) {
  const el = event.target, value = el.value, o = ed.outline;
  if (el.dataset.plane != null) {
    const key = el.dataset.planeKey;
    ed.planes[Number(el.dataset.plane)][key] = key === 'material' ? value :
      key === 'load_verified' ? value === '' ? null : value === 'true' : num(value);
    draw();
    return keepDraft();
  }
  if (el.dataset.site) {
    const key = el.dataset.siteKey;
    ed[el.dataset.site][key] = key === 'facing' ? value : num(value);
    if (el.dataset.site === 'ground' && key === 'lower_edge_m') ed.heightEdited = true;
    return keepDraft();
  }
  if (el.dataset.canopy != null) {
    const key = el.dataset.canopyKey;
    ed.planes[Number(el.dataset.canopy)][key] = key === 'outline' ?
      value.trim().split(/\n/).map(line => line.split(',').map(Number)) : num(value);
    draw();
    return keepDraft();
  }
  if (el.dataset.wind) {
    if (value === '') delete ed.wind[el.dataset.wind];
    else ed.wind[el.dataset.wind] = el.dataset.wind === 'roughness' ? value : num(value);
    return keepDraft();
  }
  if (el.dataset.re) {
    ed[el.dataset.re] = value;
    if (['use','animal'].includes(el.dataset.re)) {
      if (ed.use === 'grazing' && !ed.heightEdited) ed.ground.lower_edge_m = ed.animal === 'cow' ? 2.5 : 1.5;
      return refresh();
    }
    if (el.dataset.re === "ridgeMode") {
      ed.ridge = null;
    }
    if (el.dataset.re === "roofMode") {
      if (value !== 'ground' && ed.use === 'grazing') ed.use = '';
      if (!['metal-single','metal-gable','pitched'].includes(value) && ed.use === 'barn') ed.use = '';
      Object.assign(ed, { parapet: value === "flat" ? 1 : 0, load: value === "flat" ? 0.5 : 0.3 });
      if (isSite(value)) ed.height = 0;
      else if (Number(ed.height) === 0) ed.height = 10;
      return refresh();
    }
    if (['pitchKind', 'planeMaterial'].includes(el.dataset.re)) return refresh();
    if (["lat", "lon"].includes(el.dataset.re)) tilt();
  } else if (el.dataset.reRect) {
    ed.rect[el.dataset.reRect] = value;
    Object.assign(ed, { outline: rectangle(ed.rect), box: null });
  } else if (el.dataset.vx || el.dataset.vy) o[Number(el.dataset.vx ?? el.dataset.vy)][el.dataset.vx ? 0 : 1] = num(value) ?? 0;
  else if (el.dataset.len) { // a new edge length moves the next corner along the same edge
    const i = Number(el.dataset.len), [a, b] = [o[i], o[(i + 1) % o.length]], t = num(value) / Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (t > 0 && Number.isFinite(t)) o[(i + 1) % o.length] = [round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t)];
  } else if (el.dataset.item) ed.items[Number(el.dataset.item)][el.dataset.key] = value;
  else return;
  draw();
  keepDraft();
}
async function onChange(event) {
  const el = event.target;
  if (el.id === "re-city") {
    const city = cities.find((c) => c.name === el.value);
    if (!city) return;
    Object.assign(ed, { lat: city.lat, lon: city.lon, windCity:city.province === '江苏' ? city.name : '' });
    refresh();
    return tilt();
  }
  if (el.dataset.reCheck) {
    ed[el.dataset.reCheck] = el.checked;
    return keepDraft();
  }
  if (el.id === "re-unit") {
    ed.dxf.scale = Number(el.value);
    return draw();
  }
  if (el.dataset.re === "north" && ed.drawing?.calibration) { // the shapes turn with the drawing; no panel redraw, so the next click still lands
    const calibration = { ...ed.drawing.calibration, north_deg: num(ed.north) ?? 0 };
    retransform(ed.drawing.calibration, calibration);
    Object.assign(ed.drawing, { calibration });
    ed.box = null;
    draw();
    return keepDraft();
  }
  if (el.id === "re-file" && el.files[0]) await upload(el.files[0], 1);
  if (el.id === "re-page") {
    if (!ed.drawing.file) throw new Error("换页要先重新选一次这份 PDF");
    await upload(ed.drawing.file, Math.min(Math.max(1, Math.round(num(el.value) ?? 1)), ed.drawing.pages));
  }
}
async function upload(file, page) {
  ctx.notice("正在读图纸…");
  const response = await fetch(`/api/drawings?name=${encodeURIComponent(file.name)}&page=${page}`, { method: "POST", body: file });
  const data = await response.json();
  if (!response.ok) throw new Error((data.errors ?? ["图纸没导入成功"]).join("；"));
  record();
  if (data.kind === "dxf") {
    const extent = Math.max(...data.outlines.flatMap((o) => o.points.flat().map(Math.abs)));
    Object.assign(ed, { dxf: { outlines: data.outlines, scale: data.scale ?? (extent > 2000 ? 0.001 : 1), used: [] }, drawing: null, basis: null });
  } else {
    Object.assign(ed, { dxf: null, drawing: { url: `/api/drawings/${data.upload}`, upload: data.upload, width: data.width, height: data.height,
      pages: data.pages, page, file, calibration: null } });
  }
  Object.assign(ed, { mode: 2, clicks: [], tool: null, sel: null, box: null, snap: false, north: 0 });
  ctx.notice(data.kind === "dxf" ? `读到 ${data.outlines.length} 个闭合图形，点选屋顶外轮廓` : ed.outline.length ?
    "图纸已导入：先定比例，再沿图描屋顶外边（原来的外形用虚线显示，对得上可以点「沿用现在的外形」，也可以按 ↶ 撤销导入）" : "图纸已导入，先定比例");
  refresh();
}
function tilt() {
  clearTimeout(tiltTimer);
  const [lat, lon] = [num(ed.lat), num(ed.lon)], show = (text) => {
    ed.tilt = text; // kept in the state too, so a panel redraw while waiting shows it
    const note = document.getElementById("re-tilt");
    if (note) note.textContent = text;
  };
  if (!(lat >= 0 && lat <= 55 && lon >= -180 && lon <= 180)) return show("纬度要在 0 到 55 度之间，经度在 -180 到 180 度之间");
  show("正在按当地全年天气算最佳倾角…");
  tiltTimer = setTimeout(async () => {
    const r = await fetch(`/api/tilt?lat=${lat}&lon=${lon}`).then((x) => x.json()).catch(() => ({}));
    if (lat === num(ed.lat) && lon === num(ed.lon)) show(r.available ? `本地最佳倾角 ${r.best}°；尽量多装用 ${r.capacity}°，折中用 ${r.balanced}°` +
      `（每千瓦少发约 ${r.loss_pct.balanced}%）。开始设计时按这个算。` : r.hint ?? "开始设计后按当地天气计算倾角");
  }, 500);
}
function payload() {
  const zone = (it) => ({ id: it.id, label: it.label, ...(KINDS[it.kind][1] === "keepouts" ? { polygon: it.points,
    ...(it.preset ? {preset:it.preset} : {}), ...(num(it.clearance) != null ? {clearance_m:num(it.clearance)} : {}) } : {
    kind: it.center ? "cylinder" : "prism",
    height_m: num(it.height), ...(it.center ? { center: it.center, radius_m: it.radius } : { footprint: it.points }) }) });
  const list = (name) => ed.items.filter((it) => KINDS[it.kind][1] === name).map(zone);
  return { id: ed.id, name: ed.name, roof_mode: ed.roofMode, ridge_mode: ed.ridgeMode,
    ridge: ed.roofMode === 'metal-gable' ? ed.ridge ?? defaultRidge() : null,
    site: { lat: num(ed.lat), lon: num(ed.lon), ...(ed.windCity ? {wind_city:ed.windCity} : {}) },
    roof: { type: isSite(ed.roofMode) ? ed.roofMode : ed.roofMode === 'pitched' ? 'pitched' : ed.roofMode === "flat" ? "flat" : "metal",
    ...(Object.keys(ed.wind).length ? {wind:ed.wind} : {}),
    ...(ed.use ? {use:ed.use} : {}),
    ...(ed.use === 'grazing' ? {animal:ed.animal,
      ...(num(ed.groundSunMin) != null ? {ground_sun_min_pct:num(ed.groundSunMin)} : {})} : {}),
    ...(ed.roofMode === 'pitched' ? {pitched:pitchedSettings(), planes:ed.planes, seam_setback_m:num(ed.seamSetback)} :
      isSite(ed.roofMode) ? {[ed.roofMode]:ed[ed.roofMode], ...(ed.roofMode === 'carport' ? {planes:ed.planes} : {})} :
      ed.roofMode === "flat" ? {} : { slope_deg: num(ed.slope), slope_azimuth_deg: num(ed.azimuth),
      ...(ed.building ? { building: ed.building } : {}) }),
    outline: ed.outline, height_m: num(ed.height),
    ...(list("inverter_positions").length ? {inverter_positions: ed.items.filter(it => it.kind === "inverter").map(it => it.center)} : {}),
    ...(ed.items.some(it => it.kind === "grid") ? {grid_point: ed.items.find(it => it.kind === "grid").center} : {}),
    parapet_height_m: num(ed.parapet), load_capacity_kn_m2: num(ed.load), load_verified: ed.verified, obstacles: list("obstacles"), keepouts: list("keepouts"),
    surroundings: list("surroundings") }, underlay: ed.drawing?.calibration ? { upload: ed.drawing.upload, calibration: ed.drawing.calibration } : null };
}
async function save() {
  if (ed.tool === "outline") throw new Error("外形还没闭合：点回第一个角，或按「完成外形」（Esc 取消）");
  if (ed.dxf && ed.dxf.picked == null) throw new Error("先在左边点选 DXF 里的屋顶外轮廓");
  if (pixelMode()) throw new Error("图纸还没定比例：先在图上点两个点并填实际距离，或点「去掉图纸」");
  if (ed.drawing && ed.basis !== key(ed.drawing)) throw new Error("新导入的图纸还没描屋顶外边：点「开始描边」沿屋顶边点一圈，或确认虚线外形对得上后点「沿用现在的外形」");
  const bad = problems(ed.outline);
  if (bad.length) throw new Error(bad[0].text);
  if (ed.roofMode === 'pitched') {
    const value = await ctx.post('roof-planes', planeRequest());
    ed.planes = value.planes;
    ed.planeSource = planeSource();
  }
  const reply = await ctx.post("my-roofs", payload());
  ed.clean = text(FIELDS);
  forget();
  ctx.notice("屋顶已保存");
  await ctx.saved(reply.id);
}
async function remove() {
  if (!confirm(`删除「${ed.name}」后不能恢复（用它做过的设计记录还在）。确定删除？`)) return;
  await ctx.post(`my-roofs/${encodeURIComponent(ed.id)}/delete`, {});
  forget();
  ed.clean = text(FIELDS);
  ctx.notice("屋顶已删除");
  await ctx.saved(null);
}
