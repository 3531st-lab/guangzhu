// T18: draw a roof, or trace it over an imported image, PDF or DXF; set its city, real data, rooftop equipment and the
// buildings and trees around it. Saved roofs are ordinary roof templates for the one-click design.
// Codex review (R01-R03, R07, R09, R12): shapes stay on the drawing when its scale or north changes; a new drawing needs its outline
// traced or adopted before saving; switching drawing methods never changes the shape; corners can be dragged, added and deleted with
// undo and redo; problems are marked where they are; unsaved edits are kept as a draft.
import { esc, splitter } from "./data.js";
import {isSite, defaults as siteDefaults, panel as sitePanel, drawing as siteDrawing} from './installation-edit.js';
import {rectangleInfo, rectanglePoints, editItemGeometry, arrayCopies, snapGeometry, itemBounds, transformItems} from './roofedit-geometry.js';
import {createScene} from './scene.js';
import {facadeDefaults, facadePanel, facadeFrontOptions, applyFacadePreset, facadePreviewText} from './facade-editor.js';
import {normalizeSelection, selectObject, selectionRefs, selectedItems} from './roofedit-selection.js';
import {objectsPanel, transformDefaults, viewTools} from './roofedit-objects.js';
import {parapetPanel, parapetIssues, parapetAction, parapetChange, parapetPlanMarkup,normalizeParapets} from './parapet-editor.js';

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
FIELDS.push('parts');
FIELDS.push('facade');
FIELDS.push('parapetSegments','parapetOutline');
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
let editorScene, editorSceneSignature, editorSceneGeometrySignature;

function disposeRoofPreview() {
  if (editorScene && ed) {
    ed.sceneViewState=editorScene.getViewState?.();
    ed.sceneViewGeometry=editorSceneGeometrySignature;
  }
  editorScene?.dispose();
  editorScene = null;
  editorSceneSignature = null;
  editorSceneGeometrySignature = null;
}

function normalizeEditorSelection() {
  ed.selection=normalizeSelection(ed.selection,ed.items,ed.roofMode==='compound' ? ed.parts : []);
  ed.selectedItem=ed.selection?.kind==='item' ? ed.selection.active : null;
  ed.selectedPart=ed.selection?.kind==='part' ? ed.selection.active : null;
}
function setEditorSelection(ref, extend=false) {
  const before=JSON.stringify(ed.selection);
  ed.selection=ref ? selectObject(ed.selection,ref,extend) : null;
  normalizeEditorSelection();
  if (JSON.stringify(ed.selection)!==before) {
    ed.transformPreview=null;
    ed.transformSettings=transformDefaults(selectedItems(ed.selection,ed.items));
  }
  ed.sel=null;
}
const transformSource=()=>JSON.stringify({selection:ed.selection,items:selectedItems(ed.selection,ed.items)});
function updateObjectsPanel() {
  const host=document.getElementById('re-object-browser');
  if (host) host.outerHTML=objectsPanel(ed,KINDS,pixelMode());
}
function syncObjectFields() {
  for (const button of document.querySelectorAll('[data-object-select]')) {
    button.setAttribute('aria-pressed',String(ed.selection?.kind===button.dataset.objectSelect && ed.selection.ids.includes(button.dataset.objectId)));
    const item=button.dataset.objectSelect==='part' ? ed.parts.find(row=>row.id===button.dataset.objectId) : ed.items.find(row=>row.id===button.dataset.objectId);
    if (item) button.querySelector('span').textContent=item.label;
  }
  for (const row of document.querySelectorAll('[data-item-row]')) row.classList.toggle('selected',ed.selection?.kind==='item' && ed.selection.ids.includes(row.dataset.itemRow));
  for (const input of document.querySelectorAll('[data-object-prop],[data-item-geometry]')) {
    if (input===document.activeElement) continue;
    const item=input.dataset.objectId ? ed.items.find(row=>row.id===input.dataset.objectId) : ed.items[Number(input.dataset.itemGeometry)];
    if (!item) continue;
    const [cx,cy]=centre(item), geometry={cx,cy,...rectangleInfo(item.points),radius:item.radius};
    const value=geometry[input.dataset.objectProp ?? input.dataset.dim];
    if (Number.isFinite(value)) input.value=fine(value);
  }
}
function focusSelection() {
  if (pixelMode()) throw new Error('先标定图纸比例，再定位米制模型对象');
  const refs=selectionRefs(ed.selection);
  if (!refs.length) throw new Error('请先选择要定位的对象');
  if (ed.preview3d) {ed.pendingObjectFocus=true; return syncRoofPreview();}
  const items=selectedItems(ed.selection,ed.items), part=ed.parts.find(row=>ed.selection.kind==='part' && row.id===ed.selection.active);
  const bounds=itemBounds(items.length ? items : part ? [{points:part.outline}] : []);
  if (!bounds) return;
  const svg=document.getElementById('re-svg'), aspect=svg.clientWidth/svg.clientHeight || 1.6;
  const pad=Math.max(bounds.max[0]-bounds.min[0],bounds.max[1]-bounds.min[1],2)*.35;
  let w=Math.max(2,bounds.max[0]-bounds.min[0])+2*pad,h=Math.max(2,bounds.max[1]-bounds.min[1])+2*pad;
  [w,h]=w/h<aspect ? [h*aspect,h] : [w,w/aspect];
  ed.box=[bounds.center[0]-w/2,-bounds.center[1]-h/2,w,h];
  draw();
}
function syncViewTools() {
  const host=document.getElementById('re-view-tools');
  if (!host) return;
  host.hidden=!ed.preview3d;
  const state=editorSceneSignature ? editorScene?.getViewState?.() : null, stats=editorSceneSignature ? editorScene?.stats?.() : null;
  host.querySelectorAll('[data-re-view]').forEach(button=>button.setAttribute('aria-pressed',String(!state?.moved && button.dataset.reView===(stats?.view ?? ed.sceneView ?? 'iso'))));
  const projection=host.querySelector('[data-re-projection]');
  if (projection!==document.activeElement) projection.value=stats?.projection ?? ed.sceneProjection ?? 'perspective';
  host.querySelector('[data-view-selection]').disabled=!selectionRefs(ed.selection).length;
}
const parapetProblems=()=>isSite(ed.roofMode) ? [] : parapetIssues(ed.parapetSegments,ed.outline,ed.parapetOutline);
const sameOutline=(a,b)=>Array.isArray(a) && a.length===b.length && a.every((point,i)=>point.every((value,axis)=>Math.abs(value-b[i][axis])<=1e-7));
const staleParapets=()=>Boolean(ed.parapetSegments?.length && !sameOutline(ed.parapetOutline,ed.outline));
function syncParapetUI() {
  const host=document.getElementById('re-parapets'), status=document.getElementById('re-parapet-issues');
  const issues=parapetProblems();
  if (status) {status.innerHTML=issues.map(issue=>`<p>${esc(issue)}</p>`).join('');status.hidden=!issues.length;}
  if (!host) return;
  const key=JSON.stringify([staleParapets(),ed.outline,pixelMode()]);
  if (host.dataset.geometry && host.dataset.geometry!==key) {
    host.outerHTML=parapetPanel(ed.parapetSegments,ed.outline,{open:ed.parapetsOpen,uniformHeight:num(ed.parapet),stale:staleParapets(),pixelMode:pixelMode()});
    document.getElementById('re-parapets').dataset.geometry=key;
  } else host.dataset.geometry=key;
  syncParapetBusy();
}
function syncParapetBusy() {
  const save=document.querySelector('[data-re-act="save"]');
  if (save) save.disabled=Boolean(ed.parapetPending);
  if (ed.parapetPending) document.querySelectorAll('[data-re-act^="parapet-"]').forEach(button=>{button.disabled=true;});
  const progress=document.getElementById('re-parapet-progress');
  if (progress) {progress.hidden=!ed.parapetPending;progress.textContent=ed.parapetPending ? '正在校验屋顶轮廓并生成女儿墙，请稍候…' : '';}
}
function parapetActionSource(withPlanes) {
  return JSON.stringify({mode:ed.roofMode,outline:ed.roofMode==='compound' ? null : ed.outline,
    parts:ed.roofMode==='compound' ? ed.parts.map(part=>[part.id,part.label,part.kind,part.outline,num(part.eave_height_m),
      part.kind==='gable' ? num(part.slope_deg) : 0,part.material,part.ridge_mode ?? 'long',num(part.load_capacity_kn_m2),part.load_verified ?? null]) : null,
    height:ed.roofMode==='compound' ? null : num(ed.height),settings:pitchedSettings(),planes:withPlanes ? ed.planes : null,
    segments:ed.parapetSegments,parapet:num(ed.parapet)});
}
function remapFacadeEdge(previous, outline) {
  const index=ed.facade.front_edge;
  if (index==null || !previous[index]) return;
  const a=previous[index],b=previous[(index+1)%previous.length],near=(p,q)=>Math.hypot(p[0]-q[0],p[1]-q[1])<1e-7;
  const next=outline.findIndex((p,i)=>{const q=outline[(i+1)%outline.length];return near(a,p) && near(b,q) || near(a,q) && near(b,p);});
  ed.facade.front_edge=next<0 ? null : next;
  if (next<0) ed.facadeMessage='屋顶轮廓已改变，原主立面边已不存在，已恢复自动选择最长外墙。';
}

function syncRoofPreview() {
  const host = document.getElementById('re-3d-host');
  if (!host) return;
  const active = Boolean(ed.preview3d), canvas = host.closest('.re-canvas');
  host.hidden = !active;
  canvas.classList.toggle('is-3d', active);
  document.getElementById('re-svg-host').hidden = active;
  document.querySelector('[data-re-act="plan-view"]').setAttribute('aria-pressed',String(!active));
  document.querySelector('[data-re-act="model-view"]').setAttribute('aria-pressed',String(active));
  document.querySelector('[data-re-act="model-view"]').disabled = pixelMode() || isSite(ed.roofMode);
  const note = document.getElementById('re-3d-note');
  note.hidden = !active;
  if (!active) { ed.previewFront=false; disposeRoofPreview(); syncViewTools(); return; }
  if (!editorScene) {
    ed.sceneNeedsView=true;
    editorScene = createScene(host, {showNavControls: true, onSelectObject(ref,gesture) {
      setEditorSelection(ref,gesture?.extend);
      panel();
    },onSelectRoofPlane(id) {
    const plane = ed.planes.find(row => row.id === id);
    if (!plane?.part_id) return;
    setEditorSelection({kind:'part',id:plane.part_id});
    panel();
  }}); }
  syncViewTools();
  if (ed.previewSource !== planeRequestSource()) {
    note.textContent = `${ed.planeMessage ?? '正在校验屋面…'} ${editorSceneSignature ? '当前画面保留上次有效模型。' : '等待有效屋面数据。'}`;
    return;
  }
  const input = payload(), roof = {...ed.previewRoof,facade:input.roof.facade};
  const scene = {project:{roof,site:input.site}, design:{version:0,modules:[],params:{}},roof_geometry:ed.previewGeometry,
    editor_markers:ed.items.filter(item=>['inverter','grid'].includes(item.kind)).map(item=>({id:item.id,point:item.center}))};
  const signature = JSON.stringify(scene);
  const geometrySignature = JSON.stringify({...scene,project:{...scene.project,roof:{...roof,facade:undefined}}});
  if (editorSceneSignature !== signature) {
    editorScene.setData(scene,{preserveView:Boolean(editorSceneSignature)});
    editorSceneSignature = signature;
    editorSceneGeometrySignature = geometrySignature;
  }
  if (ed.sceneNeedsView) {
    if (ed.sceneViewState && ed.sceneViewGeometry===geometrySignature && editorScene.setViewState) editorScene.setViewState(ed.sceneViewState);
    else {
      editorScene.setProjection?.(ed.sceneProjection ?? 'perspective');
      editorScene.resetView?.(ed.sceneView ?? 'iso');
    }
    ed.sceneNeedsView=false;
  }
  editorScene.highlightRoofPlanes?.(ed.selectedPart ? ed.planes.filter(plane => plane.part_id === ed.selectedPart).map(plane => plane.id) : []);
  editorScene.highlightObjects?.(selectionRefs(ed.selection));
  if (ed.pendingObjectFocus) {editorScene.focusObjects?.(selectionRefs(ed.selection)); ed.pendingObjectFocus=false;}
  if (ed.previewFront) {editorScene.resetView?.('front'); ed.previewFront=false;}
  if (ed.pendingView) {editorScene.resetView?.(ed.pendingView); ed.pendingView=null;}
  syncViewTools();
  const issues=parapetProblems();
  note.textContent = issues.length ? `女儿墙暂不显示：${issues.join(' ')}` :
    `三维建筑预览 · 拖动旋转，滚轮缩放；点击对象可同步选择。 ${facadePreviewText(editorScene.stats?.().facade)}`;
}

function pitchedSettings() {
  return {kind:ed.pitchKind, slope_deg:num(ed.slope), azimuth_deg:num(ed.azimuth), material:ed.planeMaterial,
    ridge_mode:ed.ridgeMode, ridge:ed.pitchKind === 'gable' ? ed.ridge : null, teeth:num(ed.teeth),
    tooth_width_m:num(ed.toothWidth), glass_deg:num(ed.glassAngle)};
}
function planeSource() {
  if (ed.roofMode === 'compound') return JSON.stringify(ed.parts);
  return JSON.stringify([ed.outline, pitchedSettings()]);
}
function planeRequest(ignoreParapets=false) {
  const roof = payload().roof, facade = {...roof.facade};
  // The compound outline is rebuilt by the server. Validate the requested edge after receiving it.
  if (ed.roofMode === 'compound' && ed.planeSource !== planeSource()) facade.front_edge = null;
  const deferWalls=ed.parapetSegments?.length && (parapetProblems().length || ed.roofMode==='compound' && ed.planeSource!==planeSource());
  const walls=ignoreParapets || deferWalls ? {parapet_height_m:0} : {parapet_height_m:roof.parapet_height_m,
    ...(ed.parapetSegments!=null ? {parapet_segments:ed.parapetSegments} : {})};
  const objects = {obstacles:roof.obstacles, keepouts:roof.keepouts, ...walls, facade};
  if (ed.roofMode === 'compound') return {parts:ed.parts,...objects};
  if (ed.roofMode!=='pitched') {
    const value={...roof,...walls,facade};
    if (ignoreParapets || deferWalls) delete value.parapet_segments;
    return {roof:value};
  }
  return {outline:ed.outline, settings:pitchedSettings(), height_m:num(ed.height),
    planes:ed.planeSource === planeSource() ? ed.planes : null,...objects};
}
// Appearance changes can reuse validated roof geometry and update the scene immediately.
const requestSource=request=>JSON.stringify(request.roof ? {roof:{...request.roof,facade:undefined}} : {...request,facade:undefined});
const planeRequestSource=()=>requestSource(planeRequest());
const wallRequestSource=request=>{const value=request.roof ?? request;return JSON.stringify([value.parapet_height_m,value.parapet_segments]);};
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
  if (isSite(ed.roofMode) || pixelMode() || problems(ed.outline).length) return;
  const request = planeRequest(), signature = planeRequestSource(), state = ed;
  if (ed.previewRequested === signature) return;
  ed.previewRequested = signature;
  ed.planeMessage = '正在校验屋面…';
  const pendingNote = document.getElementById('re-plane-note');
  if (pendingNote) pendingNote.textContent = ed.planeMessage;
  clearTimeout(planeTimer);
  planeTimer = setTimeout(async () => {
    try {
      const value = await ctx.post('roof-planes', request);
      if (ed !== state || planeRequestSource() !== signature) return;
      if (value.planes) ed.planes = value.planes;
      if (ed.roofMode === 'compound') {
        ed.parts = value.parts;
        ed.outline = value.outline;
        ed.height = value.height_m;
      }
      syncFacadeFront();
      ed.planeSource = planeSource();
      const desired=planeRequest(), repeatWalls=wallRequestSource(request)!==wallRequestSource(desired);
      ed.previewRequested = repeatWalls ? signature : requestSource(desired);
      ed.previewRoof = value.roof;
      ed.previewGeometry = value.geometry;
      ed.previewSource = ed.previewRequested;
      ed.planeMessage = ed.roofMode === 'compound' ? `已校验 ${ed.parts.length} 个屋顶部分、${ed.planes.length} 个安装面；${value.geometry?.step_walls?.length ? '高低跨竖墙已生成。' : '公共边和高度已校验。'}` :
        value.actual_teeth ? `实际 ${value.actual_teeth} 齿，等分齿宽 ${value.actual_pitch_m.toFixed(3)} m` : ed.roofMode==='pitched' ? '坡面拼接已通过2厘米检查' : '屋顶几何已更新';
      const host = document.getElementById('re-planes');
      if (host) host.innerHTML = planeRows();
      draw();
      keepDraft();
    } catch (error) {
      if (ed === state) ed.planeMessage = error.message;
    }
    const note = document.getElementById('re-plane-note');
    if (note && ed === state) note.textContent = ed.planeMessage;
    if (ed === state) syncRoofPreview();
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
  disposeRoofPreview();
  const p = row?.project, r = p?.roof, zone = (o, kind) => ({ id: o.id, kind: o.preset ?? kind,
    preset: o.preset, clearance: o.clearance_m ?? '', label: o.label, height: o.height_m ?? 0, plane_id:o.plane_id ?? null,
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
    planes:structuredClone(r?.planes ?? []), parts:structuredClone(r?.parts ?? []), facade:{...facadeDefaults(),...r?.facade},
    parapetSegments:normalizeParapets(r?.parapet_segments ?? null), parapetOutline:r?.parapet_segments != null ? structuredClone(r.outline) : null,
    selection:null,objectsOpen:true});
  if (r?.type === 'pitched') {
    Object.assign(ed, {roofMode:'pitched', slope:pitch.slope_deg ?? r.planes[0].slope_deg,
      azimuth:pitch.azimuth_deg ?? 180, ridgeMode:pitch.ridge_mode ?? 'long', ridge:pitch.ridge ?? null});
  }
  if (ed.parts.length) ed.roofMode = 'compound';
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
  <button class="btn" data-re-act="export-roof-dxf">📥 导出CAD(DXF)</button>
  <button class="btn" data-re-act="save-and-run">⚡ 保存并一键出3D方案</button>
  <button class="btn primary" data-re-act="save">保存屋顶</button></div></div>
  <div class="re-layout" id="roofedit"><div class="card re-canvas"><div id="re-svg-host"></div><div id="re-3d-host" hidden></div>
  <div class="re-view-toggle seg"><button data-re-act="plan-view" aria-pressed="true">二维编辑</button><button data-re-act="model-view" aria-pressed="false">三维建筑</button></div>
  ${viewTools()}
  <span id="re-3d-note" class="re-preview-note" hidden></span><span class="re-north">北 ↑</span><span class="re-scale" id="re-scale"></span>
  <span class="re-tools"><button data-re-act="undo" title="撤销（Ctrl+Z）">↶</button><button data-re-act="redo" title="重做（Ctrl+Y）">↷</button>
  <label title="关掉后可以点在任意位置，适合描密集的转角"><input type="checkbox" data-re-check="snap"> 对齐 0.5 米</label>
  <label title="捕捉邻近端点、中点和边线；拖动时排除自身"><input type="checkbox" data-re-check="geometrySnap"> 几何吸附</label></span>
  <span class="re-zoom"><button data-re-zoom="-1" title="缩小（也可以用滚轮）">－</button><button data-re-zoom="0" title="整个屋顶放进窗口">适合</button>
  <button data-re-zoom="1" title="放大">＋</button></span></div>${splitter("roof")}<div class="re-panel scroll" id="re-panel"></div></div>`;
}
export function mountRoofEditor(context) {
  ctx = context;
  const root = document.getElementById("roofedit"), host = document.getElementById("re-svg-host");
  root.parentElement.addEventListener("click", guard(onClick));
  root.addEventListener("input", guard(onInput));
  root.addEventListener("change", guard(onChange));
  root.addEventListener('focusin',onEditorFocus);
  root.addEventListener('toggle', e => {
    if (e.target.id === 're-facade') ed.facadeOpen=e.target.open;
    if (e.target.id === 're-object-browser') ed.objectsOpen=e.target.open;
    if (e.target.id === 're-parapets') ed.parapetsOpen=e.target.open;
    if (e.target.dataset.itemTools!=null) {
      const id=ed.items[Number(e.target.dataset.itemTools)]?.id;
      if (e.target.open) ed.openItemTools=id;
      else if (ed.openItemTools===id) ed.openItemTools=null;
    }
  },true);
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
function onEditorFocus(event) {
  const el=event.target;
  if (el.matches('[data-re-rect],[data-vx],[data-vy],[data-len],[data-item],[data-item-geometry],[data-object-prop],[data-part],[data-part-dim],[data-facade],[data-parapet-row],[data-re=north],[data-re=roofMode]')) record();
  const itemIndex=el.dataset.item ?? el.dataset.itemGeometry, partIndex=el.dataset.part ?? el.dataset.partDim;
  if (itemIndex!=null && ed.items[Number(itemIndex)]) setEditorSelection({kind:'item',id:ed.items[Number(itemIndex)].id});
  else if (partIndex!=null && ed.parts[Number(partIndex)]) setEditorSelection({kind:'part',id:ed.parts[Number(partIndex)].id});
  else return;
  updateObjectsPanel();
  draw();
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
export function leaveRoofEditor() {
  const allowed = !leaving() || confirm("这个屋顶还没保存。离开后，没保存的修改会留作草稿，下次打开时可以恢复。确定离开？");
  if (allowed) disposeRoofPreview();
  return allowed;
}

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
  Object.assign(ed, { tool: null, clicks: [], sel: null, arrayPreview:null,transformPreview:null });
  normalizeEditorSelection();
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
    it.radius, it.center[1] - it.radius], [it.center[0] + it.radius, it.center[1] + it.radius]]),
    ...(ed.transformPreview?.items ?? []).flatMap(it=>it.points ?? [[it.center[0]-(it.radius ?? 0),it.center[1]-(it.radius ?? 0)],[it.center[0]+(it.radius ?? 0),it.center[1]+(it.radius ?? 0)]]),
    ...(ed.dxf?.outlines.flatMap((o) => o.points.map(dxfPoint)) ?? [])]
    .concat(ed.roofMode === 'compound' ? ed.parts.flatMap(part => part.outline) : []).map(([x, y]) => [x, -y]));
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
  normalizeEditorSelection();
  if (ed.transformPreview && ed.transformPreview.source!==transformSource()) ed.transformPreview=null;
  if (!ed.transformPreview) {
    document.querySelectorAll('[data-re-act="transform-apply"],[data-re-act="transform-cancel"]').forEach(button=>button.remove());
    const help=document.querySelector('.re-transform > p:last-child');
    if (help) help.textContent='先预览，确认后应用。旋转中心默认取所选对象整体包围框中心。';
  }
  syncFacadeFront();
  syncParapetUI();
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
    if (['pitched', 'compound'].includes(ed.roofMode) && ed.planeSource === planeSource()) {
      for (const p of ed.planes) {
        const color = p.material === 'glass' ? '#79bfd0' : p.material === 'concrete' ? '#d1c5b5' : '#cad4df';
        out.push(`<polygon data-roof-plane="${p.id}" ${p.part_id ? `data-roof-part="${esc(p.part_id)}"` : ''} points="${p.outline.map(pt).join(' ')}"
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
  if (!px && ed.roofMode === 'compound') {
    for (const part of ed.parts) {
      const center = roofCentroid(part.outline), selected = part.id === ed.selectedPart;
      out.push(`<polygon class="re-part-outline${selected ? ' selected' : ''}" data-roof-part="${esc(part.id)}" points="${part.outline.map(pt).join(' ')}"/>`);
      out.push(`<text x="${center[0]}" y="${-center[1] + u * 20}" font-size="${u * 12}" text-anchor="middle">${esc(part.label)} · 檐高 ${part.eave_height_m} m</text>`);
    }
  }
  ed.dxf?.outlines.forEach((o, i) => ed.dxf.used.includes(i) || out.push(`<polygon class="re-cand" data-cand="${i}" points="${o.points.map((p) => pt(dxfPoint(p))).join(" ")}"><title>CAD 图层 ${esc(o.layer ?? "0")} · 识别建议：${esc(o.label_hint ?? o.role_hint ?? "图形")}</title></polygon>`));
  ed.dxf?.circles?.forEach((c) => {
    const center = dxfPoint(c.center), r = round((c.radius ?? 1) * ed.dxf.scale);
    out.push(`<circle class="re-cand" cx="${center[0]}" cy="${-center[1]}" r="${r}"><title>CAD 圆 (${esc(c.layer ?? "0")}) · 识别建议：${esc(c.label_hint ?? "圆形构件")}</title></circle>`);
  });
  (px || choosing ? [] : ed.items).forEach((it, i) => {
    const [cx, cy] = centre(it);
    const selected=ed.selection?.kind==='item' && ed.selection.ids.includes(it.id);
    const shapeClass = KINDS[it.kind][2] === "point" ? "re-electrical" : "re-" + it.kind;
    const labelY = -cy - (shapeClass === "re-electrical" ? 10 * u : 0);
    out.push(it.center ? `<circle class="${shapeClass}${selected ? ' re-selected-object' : ''}" data-shape="${i}" cx="${cx}" cy="${-cy}" r="${it.radius || 5 * u}"/>` :
      `<polygon class="re-${it.kind}${selected ? ' re-selected-object' : ''}" data-shape="${i}"
      points="${it.points.map(pt).join(" ")}"/>`,
      `<text x="${round(cx)}" y="${round(labelY)}" font-size="${round(u * 12)}" text-anchor="middle">${esc(it.label)}</text>`);
  });
  for (const item of ed.arrayPreview?.items ?? []) {
    const [cx, cy] = centre(item);
    out.push(item.center ? `<circle class="re-array-preview" cx="${cx}" cy="${-cy}" r="${item.radius || 5 * u}"/>` :
      `<polygon class="re-array-preview" points="${item.points.map(pt).join(' ')}"/>`);
  }
  for (const item of ed.transformPreview?.items ?? []) {
    const [cx,cy]=centre(item);
    out.push(item.center ? `<circle class="re-transform-preview" cx="${cx}" cy="${-cy}" r="${item.radius || 5*u}"/>` :
      `<polygon class="re-transform-preview" points="${item.points.map(pt).join(' ')}"/>`);
  }
  if (!px && !parapetProblems().length) out.push(parapetPlanMarkup(ed.parapetSegments,ed.outline,u));
  if (ed.snapHint && !px) {
    const p = ed.snapHint.point;
    out.push(`<circle class="re-snap-hint" cx="${p[0]}" cy="${-p[1]}" r="${u * 6}"/><text x="${p[0] + u * 9}" y="${-p[1] - u * 9}" font-size="${u * 12}">${ed.snapHint.kind}</text>`);
  }
  const last = ed.clicks.at(-1), hover = ed.tool && !px ? ed.hover : null;
  if (tracing && last) out.push(`<polyline class="re-trace" points="${[...ed.clicks, ...(hover ? [hover] : [])].map(pt).join(" ")}"/>`);
  if (tracing && last && hover) out.push(`<text class="re-len" x="${round((last[0] + hover[0]) / 2)}" y="${round(-(last[1] + hover[1]) / 2 - u * 8)}"
    font-size="${round(u * 12)}" text-anchor="middle">${round(Math.hypot(hover[0] - last[0], hover[1] - last[1]))} m</text>`);
  ed.clicks.forEach((p, i) => out.push(`<circle class="re-dot${tracing && !i && ed.clicks.length > 2 ? " first" : ""}" cx="${p[0]}" cy="${px ? p[1] : -p[1]}"
    r="${round(u * (tracing && !i ? 6 : 4))}"/>`));
  if (!px && !choosing && !tracing && ed.mode && ed.roofMode !== 'compound' && ed.outline.length) {
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
  const geometrySnap = document.querySelector('[data-re-check="geometrySnap"]');
  if (geometrySnap) geometrySnap.checked = Boolean(ed.geometrySnap);
  if (ed.roofMode === 'compound') {
    const datum = document.querySelector('[data-re="height"]');
    if (datum) datum.value = ed.height;
  }
  for (const input of document.querySelectorAll("#re-panel [data-vx],#re-panel [data-vy],#re-panel [data-len]")) { // keep the table in step while dragging
    const o = ed.outline, i = Number(input.dataset.vx ?? input.dataset.vy ?? input.dataset.len), q = o[(i + 1) % o.length];
    if (input !== document.activeElement && o[i]) input.value = round(input.dataset.len ? Math.hypot(q[0] - o[i][0], q[1] - o[i][1]) : o[i][input.dataset.vx ? 0 : 1]);
  }
  syncObjectFields();
  syncRoofPreview();
}
function sizeText() {
  if (ed.outline.length < 3) return "还没有外形";
  const xs = ed.outline.map((p) => p[0]), ys = ed.outline.map((p) => p[1]);
  const gross = area(ed.outline);
  const blocked = (ed.items ?? []).filter((it) => ["obstacles", "keepouts"].includes(KINDS[it.kind]?.[1]))
    .reduce((s, it) => s + (it.points ? area(it.points) : Math.PI * (it.radius || 0) ** 2), 0);
  const perim = 2 * (Math.max(...xs) - Math.min(...xs) + Math.max(...ys) - Math.min(...ys));
  const net = Math.max(0, gross - blocked - Math.max(15, perim * 0.6));
  const mods = Math.max(0, Math.floor((net * 0.56) / 2.58));
  const kwp = round(mods * 0.58);
  const wanKwh = round((kwp * 1.12) / 10);
  return `${gross.toLocaleString("zh-CN", { maximumFractionDigits: 1 })} m² · ${round(Math.max(...xs) - Math.min(...xs))} × ${round(Math.max(...ys) - Math.min(...ys))} m · 预估可装 ~${mods} 块（~${kwp} kWp · 年发 ~${wanKwh} 万度）`;
}

function field(key, label, unit, value, attr = "data-re", disabled = false) {
  return `<label class="field"><span>${label}</span><span class="inbox"><input ${attr}="${key}" type="number" step="any" value="${esc(value ?? "")}" ${disabled ?
    "disabled" : ""}><span>${unit}</span></span></label>`;
}
const button = (label, act, cls = "") => `<button class="btn sm ${cls}" data-re-act="${act}">${label}</button>`;
const when = (at) => new Date(at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
function syncFacadeFront() {
  if (!ed || isSite(ed.roofMode)) return;
  ed.facade ??= facadeDefaults();
  if (ed.facade.front_edge != null && ed.facade.front_edge >= ed.outline.length) {
    ed.facade.front_edge = null;
    ed.facadeMessage = '屋顶轮廓已改变，原主立面边已不存在，已恢复自动选择最长外墙。';
  }
  const selector = document.querySelector('[data-facade="front_edge"]');
  if (selector) {
    const options = facadeFrontOptions(ed.outline,ed.facade.front_edge);
    if (selector.dataset.source !== options) {selector.innerHTML=options; selector.dataset.source=options;}
  }
  const warning = document.getElementById('re-facade-warning');
  if (warning) {warning.textContent=ed.facadeMessage ?? ''; warning.hidden=!ed.facadeMessage;}
}
function panel() {
  const host = document.getElementById("re-panel");
  if (!host) return;
  normalizeEditorSelection();
  const city = cities.find((c) => c.lat === num(ed.lat) && c.lon === num(ed.lon));
  const options = ["江苏", "其他"].map((group) => `<optgroup label="${group === "江苏" ? "江苏" : "各省会和直辖市"}">${cities.filter((c) => (c.province === "江苏") === (group === "江苏"))
    .map((c) => `<option value="${esc(c.name)}" ${c === city ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</optgroup>`).join("");
  host.innerHTML = `${ed.draft ? `<div class="card re-draft"><span>有一份 ${esc(when(ed.draft.at))} 没保存的修改</span>${button("恢复", "draft-restore", "primary")}${button("丢掉",
    "draft-drop")}</div>` : ""}${objectsPanel(ed,KINDS,pixelMode())}<section class="card re-step"><h3><b>1</b>位置</h3><label class="field"><span>城市（经纬度来自 OpenStreetMap）</span>
    <select id="re-city" class="sel"><option value="">${city ? "" : "自己填经纬度"}</option>${options}</select></label>
    <div class="re-adds" aria-label="泰州特色片区快捷定位">${[['cmc','医药城·高新区'],['watertown','海陵·凤城河老街'],['shipyard','靖江·沿江海工带'],['lixiahe','兴化·里下河农业带']].map(([k,label])=>`<button type="button" class="btn sm" data-re-act="tz-zone-${k}">📍 ${label}</button>`).join('')}</div>
    <div class="grid2">${field("lat", "纬度", "°N", ed.lat)}${field("lon", "经度", "°E", ed.lon)}</div><p id="re-tilt" class="muted re-note">${esc(ed.tilt)}</p></section>
  <section class="card re-step"><h3><b>2</b>外形</h3>${ed.roofMode === 'compound' ? compoundPanel() : `<div class="seg">${MODES.map((m, i) => `<button data-re-mode="${i}" aria-pressed="${ed.mode === i}" ${pixelMode() &&
    i !== 2 ? 'disabled title="先给图纸定比例"' : ""}>${m}</button>`).join("")}</div>${[rectPanel, pointPanel, importPanel][ed.mode]()}`}<div id="re-problems" class="re-bad"></div></section>
  <section class="card re-step"><h3><b>3</b>障碍和遮挡</h3><div class="re-adds">${Object.entries(KINDS).map(([k, [label]]) =>
    `<button class="btn sm" data-re-tool="${k}" aria-pressed="${ed.tool === k}">＋ ${label}</button>`).join("")}</div>
    ${!pixelMode() && !isSite(ed.roofMode) ? `<div class="re-adds" aria-label="泰州典型屋顶构件一键布设">${[['pharma','医药城洁净机组群'],['ship','海工屋脊气楼群'],['cold','里下河冷链冷机群']].map(([k,label])=>`<button type="button" class="btn sm" data-re-act="tz-pack-${k}">＋ ${label}</button>`).join('')}</div>` : ''}
    <p class="muted re-note">${ed.tool && ed.tool !== "outline" ? (KINDS[ed.tool][2] === "point" ? "点一下放置；并网点只保留一个。" :
    KINDS[ed.tool][2] === "rect" ? "在左边图上点两下：先点一个角，再点对角。" : "在左边图上点两下：先点圆心，再点边上一点。") :
      "屋面设备、天窗等禁区会躲开不排；屋顶外的楼和树按高出屋面多少米算阴影。放好后可以在图上拖动。"}</p>
    <div class="re-items">${ed.items.map(itemRow).join("")}</div></section>
  <section class="card re-step"><h3><b>4</b>安装面数据</h3><label class="field"><span>安装面名称</span><span class="inbox">
    <input data-re="name" maxlength="40" value="${esc(ed.name)}" placeholder="例如：常州某厂 5 号厂房"></span></label>
    ${isSite(ed.roofMode) ? `<p>平坦地坪基准0米；基础与钢结构须厂家设计。<b id="re-size">${sizeText()}</b></p>` :
    `<div class="grid2">${field("height", ed.roofMode === 'flat' ? "屋面离地高度" : ed.roofMode === 'compound' ? "最低檐口基准（各部分单独设置）" : "檐口（最低边）离地高度", "m", ed.height, 'data-re', ed.roofMode === 'compound')}
    ${field("parapet", "女儿墙高度（没有填 0）", "m", ed.parapet)}
    ${field("load", "允许附加荷载", "kN/m²", ed.load)}<div class="field"><span>面积和外形尺寸</span><b id="re-size" class="re-size">${sizeText()}</b></div></div>
    <label class="toggle"><span>荷载经过结构核定（有计算书或厂方书面确认）</span>
      <input type="checkbox" data-re-check="verified" ${ed.verified ? "checked" : ""}></label>`}
    ${metalPanel()}${usePanel()}${windPanel()}<p class="muted re-note">结构输入须现场核实，示意量不能代替施工设计。</p></section>
    ${aiDesignPanel()}
    ${isSite(ed.roofMode) ? '' : parapetPanel(ed.parapetSegments,ed.outline,{open:ed.parapetsOpen,uniformHeight:num(ed.parapet),stale:staleParapets(),pixelMode:pixelMode()})+
      '<p id="re-parapet-progress" class="muted re-note" role="status" hidden></p><div id="re-parapet-issues" class="re-bad" role="alert" hidden></div>'+facadePanel(ed.facade,ed.outline,ed.facadeOpen,ed.facadeMessage)}`;
  draw();
}
function aiDesignPanel() {
  ed.aiDesign ??= {
    module_id: 'trina-tsm-605neg19rc20',
    inverter_id: '',
    layout_algo: 'auto_pareto',
    string_algo: 'shadow_clustered',
    routing_algo: 'astar_2opt',
    dc_cable_family: 'PV1-F',
    ac_cable_family: 'ZR-YJV22',
  };
  const ai = ed.aiDesign;
  const opt = (rows, val) => rows.map(([v, t]) => `<option value="${esc(v)}" ${v === val ? 'selected' : ''}>${esc(t)}</option>`).join('');
  return `<section class="card re-step"><h3><b>5</b>本机规则设计设置（排布 · 组串 · 避障布线 · 风荷载）</h3>
    <p class="muted re-note">保存屋顶后运行确定性排布与工程计算；查看规则结果和数据来源后，可预览并确认导出。</p>
    <label class="field"><span>光伏组件型号（与设备目录一致）</span><select data-ai-design="module_id">${opt((ctx.modules ?? []).map(row => [row.id, `${row.model}${row.model_status === 'proxy' ? '（代理模型；参数待核实）' : row.parameter_status === 'unverified' ? '（参数待核实）' : ''}`]), ai.module_id)}</select></label>
    <label class="field"><span>组串式逆变器</span><select data-ai-design="inverter_id">${opt([['','按规则与容配比选择'],...(ctx.inverters ?? []).map(row => [row.id, `${row.model}${row.parameter_status === 'unverified' ? '（参数待核实）' : ''}`])], ai.inverter_id)}</select></label>
    <div class="grid2">
      <label class="field"><span>三维排版算法</span><select data-ai-design="layout_algo">${opt([
        ['auto_pareto', '候选排布比较（按规则与经济指标选择）'],
        ['winter_solstice', '冬至9–15时间窗排距计算（仍需遮挡复核）'],
        ['edge_orthogonal', '顺边正交网格'],
        ['ew_dense', '10°东西向双坡排布'],
      ], ai.layout_algo)}</select></label>
      <label class="field"><span>MPPT 组串与走线算法</span><select data-ai-design="routing_algo">${opt([
        ['astar_2opt', '正交避障 + 候选较短走线'],
        ['shadow_clustered', '按遮挡差异比较组串连接'],
      ], ai.routing_algo)}</select></label>
      <label class="field"><span>直流光伏线缆型号</span><select data-ai-design="dc_cable_family">${opt([
        ['PV1-F', 'PV1-F 1×4/6/10mm² 镀锡铜芯光伏线'],
        ['H1Z2Z2-K', 'H1Z2Z2-K 1×4/6/10mm² 欧标双绝缘耐候线'],
      ], ai.dc_cable_family)}</select></label>
      <label class="field"><span>交流并网电缆型号</span><select data-ai-design="ac_cable_family">${opt([
        ['ZR-YJV22', 'ZR-YJV22 阻燃铜芯钢带铠装电缆'],
        ['ZR-YJV', 'ZR-YJV 阻燃交联聚乙烯铜芯电缆'],
        ['YJLH22', 'YJLH22 稀土铝合金铠装电力电缆'],
      ], ai.ac_cable_family)}</select></label>
    </div>
    <div class="re-row">${button('保存并运行本机规则设计', 'save-and-run', 'primary')}</div></section>`;
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
    ['compound', '组合屋顶（平顶＋双坡 / 高低跨）'],
    ['ground', '空地（新建安装）'], ['carport', '停车场车棚（新建安装）'],
    ['metal-single', '彩钢瓦单坡（兼容）'], ['metal-gable', '彩钢瓦双坡（拆成两个，兼容）']];
  if (ed.roofMode === 'pitched') return pitchedPanel(modes);
  if (ed.roofMode === 'compound') return `<label class="field">屋面类型<select data-re="roofMode">${modes.map(([v, label]) =>
    `<option value="${v}" ${v === ed.roofMode ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
    ${field('seamSetback','公共边两侧退让（示意）','m',ed.seamSetback)}
    <p>各部分的檐高、材料、坡度在第2步设置。设备须落在一个完整坡面内，高低跨竖墙参与遮挡计算。</p>`;
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
function compoundPanel() {
  const option = (rows, value) => rows.map(([v, label]) => `<option value="${v}" ${v === value ? 'selected' : ''}>${label}</option>`).join('');
  return `<p class="muted re-note">各部分须沿边相接，不能重叠或悬空。先建立主厂房，再添加附楼；点击图上的屋面可定位到对应设置。</p>
    <div class="re-row">${button('添加平顶附楼', 'part-flat')}${button('添加双坡部分', 'part-gable')}</div>
    ${ed.parts.map((part, i) => {
      const rect = rectangleInfo(part.outline), center = centre({points:part.outline});
      const dimensions = rect ?? {cx:center[0], cy:center[1]};
      const dimRows = [...(rect ? [['w','长'],['d','宽']] : []), ['cx','中心X 向东'], ['cy','中心Y 向北'], ...(rect ? [['turn','旋转角 °']] : [])];
      return `<fieldset class="re-part${ed.selectedPart === part.id ? ' selected' : ''}" data-part-row="${esc(part.id)}"><legend>${esc(part.label)}</legend>
        <label class="field">名称<input data-part="${i}" data-part-key="label" maxlength="40" value="${esc(part.label)}"></label>
        <label class="field">屋型<select data-part="${i}" data-part-key="kind">${option([['flat','平顶'],['gable','双坡']],part.kind)}</select></label>
        <div class="grid2">${dimRows.map(([key,label]) => `<label class="field">${label}${key === 'turn' ? '' : ' m'}<input type="number" step="any"
          data-part-dim="${i}" data-dim="${key}" value="${round(dimensions[key])}" ${['w','d'].includes(key) ? 'min="0.01"' : ''} required></label>`).join('')}
          <label class="field">檐口离地高度 m<input data-part="${i}" data-part-key="eave_height_m" type="number" min="0.01" step="any" required value="${part.eave_height_m}"></label>
          ${part.kind === 'gable' ? `<label class="field">坡度 °<input data-part="${i}" data-part-key="slope_deg" type="number" min="0.01" max="89" step="any" required value="${part.slope_deg}"></label>` : ''}</div>
        ${!rect ? '<p>保留导入的非矩形轮廓；此处可整体移动，切回普通屋顶可编辑角点。</p>' : ''}
        <label class="field">材料<select data-part="${i}" data-part-key="material">${option([['metal','彩钢瓦'],['concrete','混凝土']],part.material)}</select></label>
        ${part.kind === 'gable' ? `<label class="field">屋脊<select data-part="${i}" data-part-key="ridge_mode">${option([['long','沿长边'],['short','沿短边']],part.ridge_mode ?? 'long')}</select></label>` : ''}
        <label class="field">允许附加荷载 kN/m²（空则继承整栋）<input data-part="${i}" data-part-key="load_capacity_kn_m2" type="number" min="0.01" step="any" value="${part.load_capacity_kn_m2 ?? ''}"></label>
        <label class="field">荷载依据<select data-part="${i}" data-part-key="load_verified">${option([['','继承整栋'],['true','结构核定'],['false','示意待核定']],String(part.load_verified ?? ''))}</select></label>
        ${ed.parts.length > 1 ? button('删除这一部分', `part-delete-${i}`, 'ghost') : ''}</fieldset>`;
    }).join('')}<p id="re-plane-note" role="status">${esc(ed.planeMessage ?? '正在校验组合屋面…')}</p>`;
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
  <div class="re-adds" aria-label="参数化厂房轮廓模板">${[['rect','▭ 标准矩形'],['l','▛ L型厂房'],['u','⨆ U型围合'],['t','⊤ T型车间'],['courtyard','回 江南天井院落']].map(([k,t]) => button(t, `shape-${k}`)).join("")}${button("十字检修通道", "cad-walkway-cross")}</div>
  <p class="muted re-note">改数字左边马上变。厂房不是正南正北摆的，就填旋转角；也可一键生成 L/U/T 型或江南天井院落。</p>`;
}
const tracing = () => `<p class="re-live">正在画：已点 ${ed.clicks.length} 个角。点回第一个角（绿点）或按 Enter 闭合；Backspace 撤销上一点；Esc 取消，原来的外形不变。
  按住 Shift 画横平竖直或 45° 的边。</p><div class="re-row">${button("完成外形", "close", "primary")}${button("撤销上一点", "undo")}${button("取消", "cancel")}</div>`;
function pointPanel() {
  if (ed.tool === "outline") return tracing();
  return `<p class="muted re-note">点「${ed.outline.length ? "重新画外形" : "开始画外形"}」，在左边依次点屋顶的每个角。画好后直接拖角点改位置；点边中间的小圆点加一个角；
  选中角按 Delete 删除；也可以在下表里改坐标或边长。滚轮缩放，拖空白处平移。</p><div class="re-row">${button(ed.outline.length ? "重新画外形" : "开始画外形", "trace",
    "primary")}${button("📐 90°直角正交规整", "cad-ortho")}${button("十字检修通道", "cad-walkway-cross")}</div>${table()}`;
}
function table() {
  const o = ed.outline, n = o.length;
  return n ? `<div class="re-vertices"><span></span><span>x 向东 m</span><span>y 向北 m</span><span>到下一角 m</span><span></span>${o.map(([x, y], i) =>
    `<span class="${ed.sel === i ? "on" : ""}">角 ${i + 1}</span><input data-vx="${i}" type="number" step="any" value="${round(x)}"><input data-vy="${i}" type="number" step="any"
    value="${round(y)}"><input data-len="${i}" type="number" step="any" min="0" value="${round(Math.hypot(o[(i + 1) % n][0] - x, o[(i + 1) % n][1] - y))}">
    <span class="re-vacts"><button data-re-ins="${i}" title="在这条边中间加一个角">＋</button><button data-re-del="${i}" title="删掉这个角">×</button></span>`).join("")}</div>` : "";
}
function dxfLayerSummary() {
  if (!ed.dxf?.outlines?.length) return '';
  const disabled = new Set(ed.dxf.disabledLayers ?? []);
  const roleLabel = { roof: '🏛 屋顶外轮廓', skylight: '🌤 采光天窗/气楼', device: '⚙️ 屋顶设备障碍', tank: '🛢 冷却塔/圆罐', keepout: '🚧 检修通道/禁区', building: '🏢 周边高楼遮挡', tree: '🌳 周边树木遮挡' };
  const map = new Map();
  for (const o of ed.dxf.outlines) {
    const layer = o.layer || '0';
    const cur = map.get(layer) ?? { layer, role: o.role_hint || 'keepout', height: o.height_hint || 0, count: 0 };
    cur.count++;
    map.set(layer, cur);
  }
  for (const c of ed.dxf.circles ?? []) {
    const layer = c.layer || '0';
    const cur = map.get(layer) ?? { layer, role: c.role_hint || 'tank', height: c.height_hint || 2.8, count: 0 };
    cur.count++;
    map.set(layer, cur);
  }
  const rows = [...map.values()].map(r => `<label style="display:flex;align-items:center;justify-content:space-between;gap:6px;padding:3px 6px;border-bottom:1px solid rgba(128,128,128,0.15);font-size:12px">
    <span><input type="checkbox" data-dxf-layer="${esc(r.layer)}" ${disabled.has(r.layer) ? '' : 'checked'}> <b class="mono">${esc(r.layer)}</b></span>
    <span>${esc(roleLabel[r.role] ?? '🚧 禁区')} · ${r.count}处${r.height > 0 ? ` · 高${r.height}m` : ''}</span>
  </label>`).join('');
  return `<div class="card" style="margin:6px 0;padding:6px 8px"><b style="font-size:12px">📋 CAD 图层语义智能识别清单（可勾选要导入的图层）</b><div>${rows}</div></div>`;
}
function importPanel() {
  const d = ed.drawing, c = d?.calibration, north = field("north", "图上的北方向（从图纸正上方顺时针量，看指北针）", "°", ed.north);
  const dxfRoleBar = `<div class="re-adds" aria-label="CAD图层点选转换类型">${[['auto','✨ 按图层名称匹配'],['keepout','禁区'],['device','屋顶设备'],['skylight','采光天窗'],['building','周边高楼']].map(([k,t]) =>
    `<button type="button" class="btn sm${(ed.dxfRole ?? 'auto') === k ? ' primary' : ''}" data-re-act="dxf-role-${k}">${t}</button>`).join("")}</div>`;
  const steps = ed.tool === "outline" ? tracing() : ed.dxf?.picked != null ? `<p class="muted re-note">外轮廓选好了。图里其他闭合图形点一下即按所选类型加入（或直接点「按图层名称转换剩余图形」一键转换全部设备、气楼与冷却塔）。</p>${dxfLayerSummary()}${dxfRoleBar}<div class="re-row">${button("按图层名称转换剩余图形", "dxf-auto-build")}${button("按图层转换并运行规则设计", "dxf-auto-run", "primary")}${button("完成", "dxf-done")}</div>` : ed.dxf ? `<p class="muted re-note">已解析 ${ed.dxf.outlines.length} 个闭合多段线${ed.dxf.circles?.length ? `、${ed.dxf.circles.length} 个圆形构件` : ""}。可点选屋顶外轮廓，或直接点「按 CAD 图层名称辅助建模」自动完成外轮廓＋障碍物＋天窗＋周边楼宇建模！</p>${dxfLayerSummary()}<div class="re-row">${button("按 CAD 图层名称辅助建模", "dxf-auto-build", "primary")}${button("转换图纸并运行规则设计", "dxf-auto-run", "primary")}</div><label class="field"><span>图纸单位</span><select id="re-unit" class="sel">${DXF_UNITS.map(([s, n]) =>
    `<option value="${s}" ${s === ed.dxf.scale ? "selected" : ""}>${n}</option>`).join("")}</select></label>${north}` : !d ? `<p class="muted re-note">建筑图、结构图、卫星截图、AutoCAD DXF 图纸都行。图片和 PDF 先定比例再描边；CAD 的 DXF 支持图层语义自动成模。</p>` : !c ? `<p class="muted re-note">第 1 步定比例：在图上点两个知道实际距离的点（比如屋顶两端，或标了尺寸的两点）。
    已点 ${ed.clicks.length} 个。${d.previous ? "重新定比例后，屋顶、设备和周边楼树会跟着图纸一起缩放，位置不变。" : ""}</p>${ed.clicks.length === 2 ? `${field("distance",
    "这两点实际相距", "m", ed.distance)}${north}<div class="re-row">${button("确定比例", "calibrate", "primary")}${button("重新点", "reclick")}</div>` : ""}${d.previous ?
    `<div class="re-row">${button("取消，用原来的比例", "keep-scale")}</div>` : ""}` : `<p class="muted re-note">比例已定（1 米 ≈ ${round(1 / scaleOf(c))} 像素）。${ed.basis ===
    key(d) ? "屋顶外形已对好这张图，可以直接拖角点微调。" : "第 2 步：点「开始描边」，沿屋顶外边依次点每个角。如果左边虚线的外形已经和图对上，点「沿用现在的外形」。"}</p>
    <div class="re-row">${button(ed.basis === key(d) ? "重新描边" : "开始描边", "trace", "primary")}${ed.basis !== key(d) && ed.outline.length ? button("沿用现在的外形",
    "adopt") : ""}${button("重新定比例", "recalibrate")}</div>${north}${table()}`;
  return `<div class="re-row"><label class="btn sm">选择图纸（图片、PDF、DXF）<input id="re-file" type="file" accept=".png,.jpg,.jpeg,.bmp,.webp,.pdf,.dxf" hidden></label>
  ${d?.pages > 1 ? `<label class="re-page">第 <input id="re-page" type="number" min="1" max="${d.pages}" value="${d.page}"> 页，共 ${d.pages} 页</label>` : ""}${d ?
    button("去掉图纸", "drop", "ghost") : ""}</div>
  <div class="re-adds" aria-label="CAD演示样图">${[['cmc','📐 医药城洁净厂房.dxf'],['shipyard','📐 靖江海工车间.dxf'],['watertown','📐 三水湾展馆.dxf']].map(([k,t]) => button(t, `sample-dxf-${k}`)).join("")}</div>${steps}`;
}
function itemRow(it, i) {
  const rect = rectangleInfo(it.points), [cx, cy] = centre(it), isPoint = KINDS[it.kind][2] === 'point';
  const geometry = {cx, cy, ...rect, radius:it.radius};
  const array = ed.arraySettings?.[it.id] ?? {count:6, spacing:8, direction:0};
  const rows = [['cx','中心X 向东 m'],['cy','中心Y 向北 m'], ...(rect ? [['w','长度 m'],['d','宽度 m'],['turn','旋转角 °']] :
    it.center && !isPoint ? [['radius','半径 m']] : [])];
  return `<div class="re-item${ed.selection?.kind==='item' && ed.selection.ids.includes(it.id) ? ' selected' : ''}" data-item-row="${esc(it.id)}"><span class="chip line">${KINDS[it.kind][0]}</span><input data-item="${i}" data-key="label" maxlength="30" value="${esc(it.label)}" aria-label="名称">
  ${KINDS[it.kind][1] === 'keepouts' ? `<label>避让m<input data-item="${i}" data-key="clearance" type="number"
    min="0" step="any" value="${esc(it.clearance ?? '')}" placeholder="${ed.use === 'barn' && it.preset ? 1 : '默认'}"></label>` :
    KINDS[it.kind][2] === "point" ? "<span></span>" : `<span class="inbox"><input data-item="${i}" data-key="height"
    type="number" step="any" value="${esc(it.height)}" aria-label="高出屋面"><span>m 高</span></span>`}
  <button class="btn sm ghost" data-re-remove="${i}" aria-label="删除">删除</button>
  <details class="re-item-tools" ${ed.openItemTools === it.id ? 'open' : ''} data-item-tools="${i}"><summary>精确尺寸 / 复制阵列</summary>
    ${pixelMode() ? '<p class="muted">先给图纸定比例，再修改位置、尺寸或复制阵列。</p>' : ''}<fieldset class="re-item-metric" ${pixelMode() ? 'disabled' : ''}>
    <div class="grid2">${rows.map(([key,label]) => `<label class="field">${label}<input data-item-geometry="${i}" data-dim="${key}"
      type="number" step="any" required value="${round(geometry[key])}" ${['w','d','radius'].includes(key) ? 'min="0.01"' : ''}></label>`).join('')}</div>
    ${['pitched','compound'].includes(ed.roofMode) && ['obstacles','keepouts'].includes(KINDS[it.kind][1]) ? `<label class="field">所属坡面<select data-item="${i}" data-key="plane_id">
      <option value="">按位置确定</option>${ed.planes.map(p => `<option value="${p.id}" ${it.plane_id === p.id ? 'selected' : ''}>P${p.id}${p.part_id ? ' / ' + esc(ed.parts.find(part => part.id === p.part_id)?.label ?? p.part_id) : ''}</option>`).join('')}</select></label>` : ''}
    ${it.kind !== 'grid' ? `<button class="btn sm" data-re-act="copy-${i}">复制一份（向东）</button>
    <div class="grid2"><label class="field">阵列总数（含原件）<input data-array="${i}" data-array-key="count" type="number" min="2" max="100" step="1" value="${esc(array.count)}"></label>
      <label class="field">中心间距 m<input data-array="${i}" data-array-key="spacing" type="number" min="0.01" step="any" value="${esc(array.spacing)}"></label>
      <label class="field">方向 °（0东 / 90北）<input data-array="${i}" data-array-key="direction" type="number" step="any" value="${esc(array.direction)}"></label></div>
    <div class="re-row">${button('预览阵列',`array-preview-${i}`)}${ed.arrayPreview?.index === i ? button('应用阵列',`array-apply-${i}`,'primary') + button('取消预览','array-cancel') : ''}</div>
    ${ed.arrayPreview?.index === i ? `<p>虚线为将新增的 ${ed.arrayPreview.items.length} 个对象，应用后可一步撤销。</p>` : ''}` : ''}
  </fieldset></details></div>`;
}

function point(event, straight = false) {
  const svg = document.getElementById("re-svg"), p = svg.createSVGPoint();
  [p.x, p.y] = [event.clientX, event.clientY];
  const q = p.matrixTransform(svg.getScreenCTM().inverse()), prev = ed.tool === "outline" && ed.clicks.at(-1);
  if (pixelMode()) return [round(q.x), round(q.y)];
  let [x, y] = [q.x, -q.y];
  ed.snapHint = null;
  if (straight && prev) { // Shift: the new edge runs east-west, north-south or at 45 degrees
    const a = Math.round(Math.atan2(y - prev[1], x - prev[0]) / (Math.PI / 4)) * Math.PI / 4, r = Math.hypot(x - prev[0], y - prev[1]);
    [x, y] = [prev[0] + r * Math.cos(a), prev[1] + r * Math.sin(a)];
  }
  if (ed.geometrySnap && !straight) {
    const polygons = [...(drag?.vertex == null ? [ed.outline] : []), ...ed.items.filter((it, i) => i !== drag?.item && !drag?.ids?.includes(it.id)).map(it => it.points ?? [it.center]),
      ...(ed.roofMode === 'compound' ? ed.parts.map(part => part.outline) : []), ...(ed.tool === 'outline' ? [ed.clicks] : [])];
    const hit = snapGeometry([x,y], polygons, Math.min(1, 9 * unit()), drag?.vertex != null ? ed.outline[drag.vertex] : null);
    if (hit) { ed.snapHint = hit; return hit.point; }
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
    setEditorSelection({kind:'item',id:`${prefix}-${n}`});
    return;
  }
  if (shape === "circle" ? radius <= 0 : area(points) <= 0) throw new Error("两下点在了同一处，换个位置再点");
  ed.items.push({ id: `${prefix}-${n}`, kind, label: `${label}${n}`, height,
    ...(ed.use === 'barn' && ['vent','skylight'].includes(kind) ? {preset:kind} : {}),
    ...(shape === "circle" ? { center: a, radius } : { points }) });
  setEditorSelection({kind:'item',id:`${prefix}-${n}`});
}
function pick(index) {
  record();
  const o = ed.dxf.outlines[index], points = o.points.map(dxfPoint);
  if (ed.dxf.picked == null) {
    Object.assign(ed, { outline: points, dxf: { ...ed.dxf, picked: index } });
  } else {
    const chosen = (ed.dxfRole && ed.dxfRole !== "auto") ? ed.dxfRole : (o.role_hint && o.role_hint !== "roof" ? o.role_hint : "keepout");
    const kind = KINDS[chosen] ? chosen : "keepout";
    addItem(kind, points.slice(0, 2), points);
    const added = ed.items.at(-1);
    if (added) {
      if (o.label_hint) added.label = o.label_hint;
      if (o.height_hint > 0 && KINDS[kind][1] !== "keepouts") added.height = o.height_hint;
    }
  }
  ed.dxf.used.push(index);
}
function dxfAutoBuild() {
  if (!ed.dxf?.outlines?.length) throw new Error("请先载入 DXF 图纸");
  record();
  const disabled = new Set(ed.dxf.disabledLayers ?? []);
  let roofIdx = ed.dxf.picked;
  if (roofIdx == null) {
    const byLayer = ed.dxf.outlines.findIndex((o) => o.role_hint === "roof" && !disabled.has(o.layer || "0"));
    roofIdx = byLayer >= 0 ? byLayer : 0;
    ed.outline = ed.dxf.outlines[roofIdx].points.map(dxfPoint);
    ed.dxf.picked = roofIdx;
    if (!ed.dxf.used.includes(roofIdx)) ed.dxf.used.push(roofIdx);
  }
  ed.dxf.outlines.forEach((o, i) => {
    if (i === roofIdx || ed.dxf.used.includes(i) || disabled.has(o.layer || "0")) return;
    const points = o.points.map(dxfPoint);
    const role = (o.role_hint && o.role_hint !== "roof") ? o.role_hint : "keepout";
    const kind = KINDS[role] ? role : "keepout";
    try {
      addItem(kind, points.slice(0, 2), points);
      const added = ed.items.at(-1);
      if (added) {
        if (o.label_hint) added.label = `${o.label_hint}${i}`;
        if (o.height_hint > 0 && KINDS[kind][1] !== "keepouts") added.height = o.height_hint;
      }
      ed.dxf.used.push(i);
    } catch { /* ignore degenerate polygon */ }
  });
  (ed.dxf.circles ?? []).forEach((c, idx) => {
    if (disabled.has(c.layer || "0")) return;
    const center = dxfPoint(c.center), r = round(Math.max(0.5, (c.radius ?? 1) * ed.dxf.scale));
    const role = c.role_hint === "tree" ? "tree" : "tank";
    const [label, , , defaultH, prefix] = KINDS[role];
    const n = 1 + Math.max(0, ...ed.items.filter((it) => it.id.startsWith(prefix + "-")).map((it) => Number(it.id.split("-")[1]) || 0));
    ed.items.push({ id: `${prefix}-${n}`, kind: role, label: `${c.label_hint ?? label}${idx + 1}`, height: c.height_hint || defaultH, center, radius: r });
  });
  ed.dxf = null;
  ed.box = null;
  ctx.notice("✨ 已按 CAD 图层名称匹配外轮廓与已勾选图层对象；请核实类型、尺寸和高度后保存");
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
  const next = structuredClone({outline:ed.outline, items:ed.items, planes:ed.planes, carport:ed.carport, parts:ed.parts});
  next.outline = next.outline.map(f);
  next.parts = next.parts.map(part => ({...part, outline:part.outline.map(f)}));
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
function beginCompound(previousMode) {
  if (pixelMode()) throw new Error('先给图纸定比例，再建立组合屋顶');
  if (problems(ed.outline).length) throw new Error('先完成有效的主屋顶外形，再建立组合屋顶');
  if (!ed.parts.length) ed.parts = [{id:'part-1', label:'主厂房', outline:structuredClone(ed.outline),
    kind:previousMode === 'flat' ? 'flat' : 'gable', eave_height_m:Math.max(1,num(ed.height) ?? 10),
    slope_deg:num(ed.slope) > 0 ? num(ed.slope) : 5, material:previousMode === 'flat' ? 'concrete' : 'metal', ridge_mode:'long'}];
  ed.tool = null;
  ed.clicks = [];
  ed.planeSource = null;
  ed.box = null;
}
function addPart(kind) {
  const source = ed.parts.at(-1), rect = rectangleInfo(source.outline);
  const xs = source.outline.map(point => point[0]), ys = source.outline.map(point => point[1]);
  const anchor = rect ?? {w:Math.max(...xs)-Math.min(...xs), d:Math.max(...ys)-Math.min(...ys), turn:0, cx:(Math.max(...xs)+Math.min(...xs))/2, cy:(Math.max(...ys)+Math.min(...ys))/2};
  const w = Math.min(15,anchor.w), d = Math.min(12,anchor.d), angle = rad(anchor.turn), offset = (anchor.w + w) / 2;
  let n = 1;
  while (ed.parts.some(part => part.id === `part-${n}`)) n++;
  record();
  ed.parts.push({id:`part-${n}`, label:`${kind === 'flat' ? '附楼' : '双坡部分'}${n}`,
    outline:rectanglePoints({...anchor,w,d,cx:anchor.cx+offset*Math.cos(angle),cy:anchor.cy+offset*Math.sin(angle)}),
    kind, eave_height_m:Math.max(1,source.eave_height_m-3), slope_deg:5, material:kind === 'flat' ? 'concrete' : 'metal', ridge_mode:'long'});
  setEditorSelection({kind:'part',id:`part-${n}`});
  ed.box = null;
}
function addCopies(source, copies) {
  const ids = new Set(ed.items.map(item => item.id));
  for (const item of copies) {
    let n = 1;
    while (ids.has(`${source.id}-copy-${n}`)) n++;
    item.id = `${source.id}-copy-${n}`;
    item.label = `${source.label} 副本${n}`.slice(0,30);
    item.plane_id = null;
    ids.add(item.id);
    ed.items.push(item);
  }
}
async function onClick(event) {
  if (event.target.closest("#re-svg-host")) return;
  const choice=event.target.closest('[data-object-select]');
  if (choice) {
    setEditorSelection({kind:choice.dataset.objectSelect,id:choice.dataset.objectId},event.ctrlKey || event.metaKey);
    return panel();
  }
  const el = event.target.closest("[data-re-act],[data-re-mode],[data-re-tool],[data-re-remove],[data-re-ins],[data-re-del],[data-re-zoom],[data-re-view]");
  if (!el) return;
  const act = el.dataset.reAct, d = ed.drawing;
  if (pixelMode() && ['copy-','array-preview-','array-apply-'].some(prefix=>act?.startsWith(prefix))) throw new Error('先标定图纸比例，再复制或阵列米制对象');
  if (act?.startsWith('parapet-')) {
    if (pixelMode()) throw new Error('先标定图纸比例，再编辑女儿墙');
    if (ed.parapetPending) throw new Error('女儿墙正在生成，请稍候');
    if (staleParapets() && (act==='parapet-add' || act.startsWith('parapet-delete-'))) throw new Error(parapetProblems()[0]);
    if (act==='parapet-custom' || act==='parapet-reset') {
      const state=ed, request=planeRequest(true), withPlanes=request.planes!=null, source=parapetActionSource(withPlanes);
      ed.parapetPending=true;
      syncParapetBusy();
      const task=ctx.post('roof-planes',request).then(result=>{
        if (state!==ed || source!==parapetActionSource(withPlanes)) throw new Error('屋顶已改变，请重新按当前轮廓生成女儿墙');
        record();
        const outline=result.outline ?? result.roof.outline;
        remapFacadeEdge(ed.outline,outline);
        ed.outline=structuredClone(outline);
        ed.rect=asRect(ed.outline) ?? ed.rect;
        if (result.planes) ed.planes=result.planes;
        if (ed.roofMode==='compound') Object.assign(ed,{parts:result.parts,height:result.height_m});
        ed.planeSource=planeSource();
        const value=parapetAction(act,ed.parapetSegments,ed.outline,num(ed.parapet));
        Object.assign(ed,{parapetSegments:value.segments,parapetOutline:value.anchor,parapetsOpen:true,previewRequested:null});
        refresh();
      });
      ed.parapetTask=task;
      try {await task;} finally {
        state.parapetPending=false;state.parapetTask=null;
        if (state===ed) {panel();syncParapetBusy();}
      }
      return;
    } else record();
    const value=parapetAction(act,ed.parapetSegments,ed.outline,num(ed.parapet));
    Object.assign(ed,{parapetSegments:value.segments,parapetOutline:value.anchor,parapetsOpen:true});
    ed.previewRequested=null;
    return refresh();
  }
  if (el.dataset.reView || act==='view-fit') {
    if (el.dataset.reView) {
      ed.sceneProjection='orthographic';
      editorScene?.setProjection?.('orthographic');
    }
    ed.sceneView=el.dataset.reView ?? ed.sceneView ?? 'iso';
    ed.pendingView=ed.sceneView;
    editorScene?.resetView?.(ed.sceneView);
    return syncRoofPreview();
  }
  if (act==='object-focus') return focusSelection();
  if (act==='object-clear') {setEditorSelection(null); return panel();}
  if (act==='object-properties') {
    const selection=ed.selection;
    if (!selection) throw new Error('请先选择对象');
    if (selection.kind==='item') {
      ed.openItemTools=selection.active;
      panel();
      document.querySelector(`[data-item-row="${CSS.escape(selection.active)}"]`)?.scrollIntoView({block:'center'});
    } else document.querySelector(`[data-part-row="${CSS.escape(selection.active)}"]`)?.scrollIntoView({block:'center'});
    return;
  }
  if (act==='object-delete') {
    const ids=new Set(selectedItems(ed.selection,ed.items).map(item=>item.id));
    if (!ids.size) throw new Error('请选择要删除的设备、禁区或周边对象');
    record();
    ed.items=ed.items.filter(item=>!ids.has(item.id));
    setEditorSelection(null);
    return refresh();
  }
  if (act==='transform-preview') {
    if (pixelMode()) throw new Error('先标定图纸比例，再使用米制精确变换');
    const originals=selectedItems(ed.selection,ed.items), settings={...transformDefaults(originals),...ed.transformSettings};
    const invalid=[...document.querySelectorAll('[data-transform]')].find(input=>!input.validity.valid);
    if (invalid) {invalid.reportValidity(); throw new Error('请填写完整、有效的变换尺寸');}
    if (settings.copy && originals.some(item=>item.kind==='grid')) throw new Error('并网点只能保留一个，不能生成副本');
    const items=transformItems(originals,settings);
    ed.transformPreview={source:transformSource(),items,copy:settings.copy};
    ed.preview3d=false;
    ed.box=null;
    return panel();
  }
  if (act==='transform-apply') {
    const preview=ed.transformPreview;
    if (!preview || preview.source!==transformSource()) throw new Error('对象或选择已改变，请重新预览变换');
    record();
    if (preview.copy) {
      const ids=[];
      for (const item of preview.items) {
        addCopies(ed.items.find(row=>row.id===item.id),[item]);
        ids.push(item.id);
      }
      ed.selection={kind:'item',ids,active:ids.at(-1)};
    } else {
      const byId=new Map(preview.items.map(item=>[item.id,item]));
      ed.items=ed.items.map(item=>byId.get(item.id) ?? item);
    }
    ed.transformPreview=null;
    ed.transformSettings=transformDefaults(selectedItems(ed.selection,ed.items));
    return refresh();
  }
  if (act==='transform-cancel') {ed.transformPreview=null; return panel();}
  if (act === 'facade-front-view') {
    if (pixelMode()) throw new Error('先完成屋顶定标，再查看厂房主立面');
    ed.preview3d=true;
    ed.previewFront=true;
    return draw();
  }
  if (act === 'facade-reset' || act?.startsWith('facade-preset-')) {
    record();
    ed.facade = act === 'facade-reset' ? facadeDefaults() : applyFacadePreset(ed.facade,act.slice(14));
    ed.facadeMessage = '';
    return refresh();
  }
  if (act?.startsWith('tz-zone-')) {
    record();
    ed.lat = 32.46;
    ed.lon = 119.92;
    ed.windCity = '泰州';
    const presetMap = {cmc:'taizhou_pharma', watertown:'taizhou_watertown', shipyard:'taizhou_shipyard', lixiahe:'taizhou_agri'};
    const pKey = presetMap[act.slice(8)];
    if (pKey) ed.facade = applyFacadePreset(ed.facade, pKey);
    tilt();
    return refresh();
  }
  if (act?.startsWith('tz-pack-')) {
    if (!ed.outline.length) throw new Error('先画好屋顶轮廓再放置构件群');
    record();
    const [cx, cy] = roofCentroid(ed.outline);
    const nextNum = prefix => 1 + Math.max(0, ...ed.items.filter(it => it.id.startsWith(prefix + '-')).map(it => Number(it.id.split('-')[1]) || 0));
    const rectPts = (x, y, w, d) => [[round(x-w/2), round(y-d/2)], [round(x+w/2), round(y-d/2)], [round(x+w/2), round(y+d/2)], [round(x-w/2), round(y+d/2)]];
    const kind = act.slice(8), addedIds = [];
    if (kind === 'pharma') {
      const d1 = `dev-${nextNum('dev')}`, t1 = `tank-${nextNum('tank')}`, z1 = `zone-${nextNum('zone')}`;
      ed.items.push(
        {id:d1, kind:'device', label:'GMP洁净空调机组', height:2.6, points:rectPts(cx-4, cy+2, 5.6, 2.8)},
        {id:t1, kind:'tank', label:'酸雾洗涤塔', height:3.2, center:[round(cx+4.5), round(cy+2)], radius:1.5},
        {id:z1, kind:'keepout', label:'洁净风管检修区', height:0, points:rectPts(cx, cy-2.2, 8.0, 1.5)}
      );
      addedIds.push(d1, t1, z1);
    } else if (kind === 'ship') {
      const s1 = `sky-${nextNum('sky')}`, d1 = `dev-${nextNum('dev')}`, d2 = `dev-${nextNum('dev')+1}`;
      ed.items.push(
        {id:s1, kind:'skylight', label:'海工屋脊通风气楼', height:0, points:rectPts(cx, cy, 12.0, 2.2)},
        {id:d1, kind:'device', label:'车间排烟风机A', height:1.8, points:rectPts(cx-8, cy+3.2, 2.2, 2.2)},
        {id:d2, kind:'device', label:'车间排烟风机B', height:1.8, points:rectPts(cx+8, cy+3.2, 2.2, 2.2)}
      );
      addedIds.push(s1, d1, d2);
    } else if (kind === 'cold') {
      const t1 = `tank-${nextNum('tank')}`, t2 = `tank-${nextNum('tank')+1}`, d1 = `dev-${nextNum('dev')}`;
      ed.items.push(
        {id:t1, kind:'tank', label:'蒸发式冷凝器1', height:2.8, center:[round(cx-3.2), round(cy+1.5)], radius:1.4},
        {id:t2, kind:'tank', label:'蒸发式冷凝器2', height:2.8, center:[round(cx+3.2), round(cy+1.5)], radius:1.4},
        {id:d1, kind:'device', label:'冷链融霜阀站', height:2.0, points:rectPts(cx, cy-2.2, 3.6, 2.0)}
      );
      addedIds.push(t1, t2, d1);
    }
    if (addedIds.length) ed.selection = {kind:'item', ids:addedIds, active:addedIds.at(-1)};
    return refresh();
  }
  if (act === 'plan-view' || act === 'model-view') {
    if (act === 'model-view' && (pixelMode() || isSite(ed.roofMode))) throw new Error('先完成屋顶定标，空地和车棚请在设计结果中查看三维');
    ed.preview3d = act === 'model-view';
    return draw();
  }
  if (act === 'part-flat' || act === 'part-gable') { addPart(act.slice(5)); return refresh(); }
  if (act?.startsWith('part-delete-')) {
    if (ed.parts.length <= 1) throw new Error('至少保留一个屋顶部分');
    record();
    ed.parts.splice(Number(act.slice(12)),1);
    ed.box = null;
    return refresh();
  }
  if (act?.startsWith('copy-')) {
    const item = ed.items[Number(act.slice(5))], bounds = item.points?.map(point => point[0]);
    const spacing = bounds ? Math.max(...bounds)-Math.min(...bounds)+1 : 2*(item.radius ?? 0)+1;
    record();
    addCopies(item, arrayCopies(item,2,spacing,0));
    ed.arrayPreview = null;
    return refresh();
  }
  if (act?.startsWith('array-preview-')) {
    const index = Number(act.slice(14)), source = ed.items[index], settings = {};
    document.querySelectorAll(`[data-array="${index}"]`).forEach(input => {settings[input.dataset.arrayKey] = num(input.value);});
    const items = arrayCopies(source,settings.count,settings.spacing,settings.direction);
    ed.arrayPreview = {index, source:JSON.stringify(source), items};
    setEditorSelection({kind:'item',id:source.id});
    ed.openItemTools=source.id;
    return refresh();
  }
  if (act?.startsWith('array-apply-')) {
    const index = Number(act.slice(12)), preview = ed.arrayPreview, source = ed.items[index];
    if (preview?.index !== index || preview.source !== JSON.stringify(source)) throw new Error('对象已改变，请重新预览阵列');
    record();
    addCopies(source,preview.items);
    ed.arrayPreview = null;
    return refresh();
  }
  if (act === 'array-cancel') { ed.arrayPreview = null; return refresh(); }
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
  else if (act?.startsWith("shape-")) {
    record();
    const w = Math.max(12, num(ed.rect.w) ?? 60), d0 = Math.max(10, num(ed.rect.d) ?? 36), turn = rad(num(ed.rect.turn) ?? 0);
    const kind = act.slice(6);
    const rot = (pts) => pts.map((p) => rotate(p, turn).map(round));
    if (kind === "rect") {
      ed.outline = rectangle(ed.rect);
    } else if (kind === "l") {
      const w2 = round(w * 0.55), d2 = round(d0 * 0.52);
      ed.outline = rot([[0, 0], [w, 0], [w, d2], [w2, d2], [w2, d0], [0, d0]]);
    } else if (kind === "u") {
      const wing = round(w * 0.28), baseD = round(d0 * 0.42);
      ed.outline = rot([[0, 0], [w, 0], [w, d0], [w - wing, d0], [w - wing, baseD], [wing, baseD], [wing, d0], [0, d0]]);
    } else if (kind === "t") {
      const stem = round(w * 0.44), x1 = round((w - stem) / 2), x2 = round((w + stem) / 2), barD = round(d0 * 0.52);
      ed.outline = rot([[x1, 0], [x2, 0], [x2, d0 - barD], [w, d0 - barD], [w, d0], [0, d0], [0, d0 - barD], [x1, d0 - barD]]);
    } else if (kind === "courtyard") {
      ed.outline = rectangle(ed.rect);
      const cw = round(Math.max(6, w * 0.28)), cd = round(Math.max(5, d0 * 0.28));
      const x1 = round((w - cw) / 2), y1 = round((d0 - cd) / 2);
      const pts = rot([[x1, y1], [x1 + cw, y1], [x1 + cw, y1 + cd], [x1, y1 + cd]]);
      addItem("skylight", pts.slice(0, 2), pts);
      const added = ed.items.at(-1);
      if (added) added.label = "江南天井采光院";
    }
    ed.box = null;
    ctx.notice(`已生成参数化厂房轮廓（${ed.outline.length} 角点）`);
  } else if (act === "cad-ortho") {
    if (ed.outline.length < 4) throw new Error("至少 4 个角才能做 90° 正交规整");
    record();
    const pts = ed.outline.map((p) => [...p]);
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i], b = pts[(i + 1) % pts.length];
      if (Math.abs(b[0] - a[0]) >= Math.abs(b[1] - a[1])) b[1] = a[1];
      else b[0] = a[0];
    }
    ed.outline = pts.map(([x, y]) => [round(x), round(y)]);
    ctx.notice("已对屋顶外轮廓执行 90° 正交直角规整");
  } else if (act === "cad-walkway-cross") {
    if (ed.outline.length < 3) throw new Error("请先画好屋顶外轮廓");
    const owner = ed, before = JSON.stringify(ed.outline);
    const result = await ctx.post('roof-tools/cross-walkways', {outline:ed.outline,width_m:1,setback_m:1.2});
    if (ed !== owner || before !== JSON.stringify(ed.outline)) throw new Error('屋顶轮廓已改变，请重新生成通道');
    if (result.polygons?.length) {
      record();
      result.polygons.forEach((points,index) => {
        addItem('keepout',points.slice(0,2),points);
        ed.items.at(-1).label = `检修通道${index+1}（宽${result.width_m}m）`;
      });
    }
    ctx.notice(result.note);
  } else if (act?.startsWith("sample-dxf-")) {
    const preset = act.slice(11);
    ctx.notice("正在加载多图层 CAD 演示样图…");
    const data = await ctx.post("drawings/sample-dxf", { preset });
    record();
    const extent = Math.max(...data.outlines.flatMap((o) => o.points.flat().map(Math.abs)));
    Object.assign(ed, {
      dxf: { outlines: data.outlines, circles: data.circles ?? [], scale: data.scale ?? (extent > 2000 ? 0.001 : 1), used: [] },
      drawing: null, basis: null, mode: 2, clicks: [], tool: null, sel: null, box: null, snap: false, north: 0,
    });
    if (!ed.name || ed.name.includes("新建")) {
      const names = { cmc: "泰州医药城洁净车间CAD导入", shipyard: "靖江海工车间CAD导入", watertown: "凤城河三水湾展馆CAD导入" };
      ed.name = names[preset] ?? ed.name;
    }
    ctx.notice(`已载入 CAD 样图「${data.filename}」（含 ${data.outlines.length} 个闭合多段线、${(data.circles ?? []).length} 个圆形构件），可点「按 CAD 图层名称辅助建模」`);
  } else if (act === "dxf-auto-build") {
    dxfAutoBuild();
  } else if (act === "dxf-auto-run") {
    if (ed.dxf) dxfAutoBuild();
    return save(true);
  } else if (act?.startsWith("dxf-role-")) {
    ed.dxfRole = act.slice(9);
  } else if (act === "export-roof-dxf") {
    if (ed.outline.length < 3) throw new Error("请先画好屋顶轮廓再导出 CAD");
    const res = await ctx.post("my-roofs/export-dxf", payload());
    const blob = new Blob([res.content], { type: "application/dxf;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = res.filename || "roof.dxf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    ctx.notice(`已导出分层 AutoCAD 图纸：${res.filename}`);
    return;
  } else if (act === "dxf-done") ed.dxf = null;
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
  } else if (act === "save") return save(false);
  else if (act === "save-and-run") return save(true);
  else if (act === "delete") return remove();
  refresh();
}
function down(e) {
  const t = e.target;
  drag = { x: e.clientX, y: e.clientY, k: unit(), box: [...ed.box], target: t, pan: e.button !== 0 };
  if (!drag.pan && !ed.tool && !pixelMode()) {
    if (t.dataset.v) {
      setEditorSelection(null);
      record();
      drag.vertex = ed.sel = Number(t.dataset.v);
    } else if (t.dataset.mid) drag.vertex = insertCorner(Number(t.dataset.mid));
    else if (t.dataset.shape) {
      const item=ed.items[Number(t.dataset.shape)], extend=e.ctrlKey || e.metaKey;
      if (extend || ed.selection?.kind!=='item' || !ed.selection.ids.includes(item.id)) setEditorSelection({kind:'item',id:item.id},extend);
      ed.openItemTools=item.id;
      if (extend) drag.selectionOnly=true;
      else {
      record();
      Object.assign(drag, {item:Number(t.dataset.shape),ids:[...ed.selection.ids],at:point(e),originals:structuredClone(selectedItems(ed.selection,ed.items))});
      }
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
    if (drag.selectionOnly) return;
    if (drag.vertex != null) ed.outline[drag.vertex] = point(e);
    else if (drag.item != null) {
      const p=point(e),dx=p[0]-drag.at[0],dy=p[1]-drag.at[1];
      const moved=dx || dy ? transformItems(drag.originals,{mode:'move',dx,dy}) : structuredClone(drag.originals);
      const byId=new Map(moved.map(item=>[item.id,item]));
      ed.items=ed.items.map(item=>byId.get(item.id) ?? item);
    } else ed.box = [drag.box[0] - dx * drag.k, drag.box[1] - dy * drag.k, drag.box[2], drag.box[3]];
  } else if (!ed.tool) return;
  draw();
}
function up(e) {
  const d = drag;
  drag = null;
  if (!d) return;
  if (d.selectionOnly) return panel();
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
    if (target.dataset.roofPart) {
      setEditorSelection({kind:'part',id:target.dataset.roofPart});
      panel();
      return;
    }
    setEditorSelection(null);
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
  else if (k === "Escape") {
    if (ed.transformPreview) ed.transformPreview=null;
    else {Object.assign(ed,{tool:null,clicks:[],sel:null}); setEditorSelection(null);}
  }
  else if (["Delete", "Backspace"].includes(k) && ed.sel != null) {
    e.preventDefault();
    removeCorner(ed.sel);
  } else if (["Delete","Backspace"].includes(k) && ed.selection?.kind==='item') {
    record();
    ed.items=ed.items.filter(item=>!ed.selection.ids.includes(item.id));
    setEditorSelection(null);
  } else return;
  e.preventDefault();
  refresh();
}
function onInput(event) {
  const el = event.target, value = el.value, o = ed.outline;
  if (el.dataset.parapetRow!=null) {
    if (pixelMode() || staleParapets()) throw new Error('先完成图纸标定并按当前轮廓重新生成女儿墙');
    if (!el.validity.valid || value==='') return;
    ed.parapetSegments=parapetChange(ed.parapetSegments,Number(el.dataset.parapetRow),el.dataset.parapetKey,value,ed.outline);
    if (el.dataset.parapetKey==='edge_index') {
      const host=document.getElementById('re-parapets');
      host.outerHTML=parapetPanel(ed.parapetSegments,ed.outline,{open:true,uniformHeight:num(ed.parapet),pixelMode:false});
    }
    draw();
    return keepDraft();
  }
  if (el.dataset.transform) {
    if (el.type==='checkbox') return;
    const key=el.dataset.transform, items=selectedItems(ed.selection,ed.items);
    ed.transformSettings={...transformDefaults(items),...ed.transformSettings,[key]:key==='mode' ? value : num(value)};
    ed.transformPreview=null;
    if (key==='mode') {
      const bounds=itemBounds(items);
      if (value.startsWith('mirror')) {
        ed.transformSettings.axisValue=(bounds?.max[value==='mirror-x' ? 0 : 1] ?? 0)+1;
        ed.transformSettings.copy=items.every(item=>item.kind!=='grid');
      }
      updateObjectsPanel();
    }
    return draw();
  }
  if (el.dataset.objectProp) {
    if (pixelMode()) throw new Error('先标定图纸比例，再修改米制属性');
    if (!el.validity.valid || num(value)==null) return;
    const index=ed.items.findIndex(item=>item.id===el.dataset.objectId);
    if (index<0) throw new Error('找不到这个对象，请重新选择');
    ed.items[index]=editItemGeometry(ed.items[index],el.dataset.objectProp,num(value));
    ed.arrayPreview=null;
    draw();
    return keepDraft();
  }
  if (el.dataset.reProjection!=null) {
    ed.sceneProjection=value;
    editorScene?.setProjection?.(value);
    return syncViewTools();
  }
  if (el.dataset.facade) {
    if (el.type === 'checkbox' || !el.validity.valid) return;
    const key=el.dataset.facade;
    ed.facade[key] = el.type === 'number' || ['front_edge','window_rows'].includes(key) ? num(value) : value;
    if (key === 'front_edge') {ed.facadeMessage=''; syncFacadeFront();}
    const code=document.querySelector(`[data-facade-color-text="${key}"]`);
    if (code) code.textContent=value;
    syncRoofPreview();
    return keepDraft();
  }
  if (el.dataset.array != null) {
    const id = ed.items[Number(el.dataset.array)].id;
    ed.arraySettings ??= {};
    ed.arraySettings[id] ??= {count:6,spacing:8,direction:0};
    ed.arraySettings[id][el.dataset.arrayKey] = value;
    ed.arrayPreview = null;
    return draw();
  }
  if (el.dataset.itemGeometry != null) {
    if (pixelMode()) throw new Error('先标定图纸比例，再修改米制位置与尺寸');
    const index = Number(el.dataset.itemGeometry);
    if (!el.validity.valid || num(value) == null) return;
    ed.items[index] = editItemGeometry(ed.items[index],el.dataset.dim,num(value));
    ed.arrayPreview = null;
    draw();
    return keepDraft();
  }
  if (el.dataset.partDim != null) {
    const part = ed.parts[Number(el.dataset.partDim)], value = num(el.value);
    if (!el.validity.valid || value == null) return;
    const item = editItemGeometry({points:part.outline},el.dataset.dim,value);
    part.outline = item.points;
    ed.box = null;
    draw();
    return keepDraft();
  }
  if (el.dataset.part != null) {
    const part = ed.parts[Number(el.dataset.part)], key = el.dataset.partKey;
    part[key] = ['label','kind','material','ridge_mode'].includes(key) ? value :
      key === 'load_verified' ? value === '' ? null : value === 'true' : num(value);
    if (key === 'kind') return refresh();
    draw();
    return keepDraft();
  }
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
  if (el.dataset.aiDesign) {
    ed.aiDesign ??= {};
    ed.aiDesign[el.dataset.aiDesign] = value;
    return;
  }
  if (el.dataset.wind) {
    if (value === '') delete ed.wind[el.dataset.wind];
    else ed.wind[el.dataset.wind] = el.dataset.wind === 'roughness' ? value : num(value);
    return keepDraft();
  }
  if (el.dataset.re) {
    const previousMode = ed.roofMode;
    if (el.dataset.re === 'roofMode' && value === 'compound') beginCompound(previousMode);
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
      if (!['metal-single','metal-gable','pitched','compound'].includes(value) && ed.use === 'barn') ed.use = '';
      Object.assign(ed, { parapet: value === "flat" ? 1 : 0, load: value === "flat" ? 0.5 : 0.3 });
      if (isSite(value)) ed.height = 0;
      else if (Number(ed.height) === 0) ed.height = 10;
      if (isSite(value)) ed.preview3d = false;
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
  } else if (el.dataset.item) {
    ed.items[Number(el.dataset.item)][el.dataset.key] = el.dataset.key === 'plane_id' ? num(value) : value;
    ed.arrayPreview = null;
  }
  else return;
  draw();
  keepDraft();
}
async function onChange(event) {
  const el = event.target;
  if (el.dataset.transform==='copy') {
    ed.transformSettings={...transformDefaults(selectedItems(ed.selection,ed.items)),...ed.transformSettings,copy:el.checked};
    ed.transformPreview=null;
    return draw();
  }
  if (el.dataset.facade && el.type === 'checkbox') {
    ed.facade[el.dataset.facade]=el.checked;
    if (el.dataset.facade === 'enabled') return refresh();
    syncRoofPreview();
    return keepDraft();
  }
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
  if (el.dataset.dxfLayer && ed.dxf) {
    const set = new Set(ed.dxf.disabledLayers ?? []);
    if (el.checked) set.delete(el.dataset.dxfLayer);
    else set.add(el.dataset.dxfLayer);
    ed.dxf.disabledLayers = [...set];
    return draw();
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
    Object.assign(ed, { dxf: { outlines: data.outlines, circles: data.circles ?? [], scale: data.scale ?? (extent > 2000 ? 0.001 : 1), used: [] }, drawing: null, basis: null });
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
  const zone = (it) => ({ id: it.id, label: it.label,
    ...(['obstacles','keepouts'].includes(KINDS[it.kind][1]) && ['pitched','compound'].includes(ed.roofMode) && it.plane_id != null ? {plane_id:it.plane_id} : {}),
    ...(KINDS[it.kind][1] === "keepouts" ? { polygon: it.points,
    ...(it.preset ? {preset:it.preset} : {}), ...(num(it.clearance) != null ? {clearance_m:num(it.clearance)} : {}) } : {
    kind: it.center ? "cylinder" : "prism",
    height_m: num(it.height), ...(it.center ? { center: it.center, radius_m: it.radius } : { footprint: it.points }) }) });
  const list = (name) => ed.items.filter((it) => KINDS[it.kind][1] === name).map(zone);
  return { id: ed.id, name: ed.name, roof_mode: ed.roofMode, ridge_mode: ed.ridgeMode,
    ridge: ed.roofMode === 'metal-gable' ? ed.ridge ?? defaultRidge() : null,
    site: { lat: num(ed.lat), lon: num(ed.lon), ...(ed.windCity ? {wind_city:ed.windCity} : {}) },
    roof: { type: isSite(ed.roofMode) ? ed.roofMode : ['pitched','compound'].includes(ed.roofMode) ? 'pitched' : ed.roofMode === "flat" ? "flat" : "metal",
    ...(!isSite(ed.roofMode) ? {facade:ed.facade} : {}),
    ...(!isSite(ed.roofMode) && ed.parapetSegments!=null ? {parapet_segments:ed.parapetSegments} : {}),
    ...(Object.keys(ed.wind).length ? {wind:ed.wind} : {}),
    ...(ed.use ? {use:ed.use} : {}),
    ...(ed.use === 'grazing' ? {animal:ed.animal,
      ...(num(ed.groundSunMin) != null ? {ground_sun_min_pct:num(ed.groundSunMin)} : {})} : {}),
    ...(ed.roofMode === 'compound' ? {parts:ed.parts, planes:ed.planes, seam_setback_m:num(ed.seamSetback)} :
      ed.roofMode === 'pitched' ? {pitched:pitchedSettings(), planes:ed.planes, seam_setback_m:num(ed.seamSetback)} :
      isSite(ed.roofMode) ? {[ed.roofMode]:ed[ed.roofMode], ...(ed.roofMode === 'carport' ? {planes:ed.planes} : {})} :
      ed.roofMode === "flat" ? {} : { slope_deg: num(ed.slope), slope_azimuth_deg: num(ed.azimuth),
      ...(ed.building ? { building: ed.building } : {}) }),
    outline: ed.outline, height_m: num(ed.height),
    ...(list("inverter_positions").length ? {inverter_positions: ed.items.filter(it => it.kind === "inverter").map(it => it.center)} : {}),
    ...(ed.items.some(it => it.kind === "grid") ? {grid_point: ed.items.find(it => it.kind === "grid").center} : {}),
    parapet_height_m: num(ed.parapet), load_capacity_kn_m2: num(ed.load), load_verified: ed.verified, obstacles: list("obstacles"), keepouts: list("keepouts"),
    surroundings: list("surroundings") }, underlay: ed.drawing?.calibration ? { upload: ed.drawing.upload, calibration: ed.drawing.calibration } : null };
}
async function save(quickRun = false) {
  if (ed.parapetTask) await ed.parapetTask;
  const invalid = [...document.querySelectorAll('[data-item-geometry],[data-object-prop],[data-part],[data-part-dim],[data-facade],[data-parapet-row]')].find(input => !input.validity.valid);
  if (invalid) { invalid.reportValidity(); throw new Error('请补全有效的位置、尺寸、屋面与厂房外观参数后再保存'); }
  if (ed.tool === "outline") throw new Error("外形还没闭合：点回第一个角，或按「完成外形」（Esc 取消）");
  if (ed.dxf && ed.dxf.picked == null) {
    if (quickRun) dxfAutoBuild();
    else throw new Error("先在左边点选 DXF 里的屋顶外轮廓，或点「按 CAD 图层名称辅助建模」");
  }
  if (pixelMode()) throw new Error("图纸还没定比例：先在图上点两个点并填实际距离，或点「去掉图纸」");
  if (ed.drawing && ed.basis !== key(ed.drawing)) throw new Error("新导入的图纸还没描屋顶外边：点「开始描边」沿屋顶边点一圈，或确认虚线外形对得上后点「沿用现在的外形」");
  const bad = problems(ed.outline);
  if (bad.length) throw new Error(bad[0].text);
  if (ed.transformPreview) throw new Error('请先应用或取消精确变换预览，再保存屋顶');
  if (parapetProblems().length) throw new Error(parapetProblems()[0]);
  if (['pitched','compound'].includes(ed.roofMode)) {
    const value = await ctx.post('roof-planes', planeRequest());
    ed.planes = value.planes;
    if (ed.roofMode === 'compound') Object.assign(ed,{parts:value.parts,outline:value.outline,height:value.height_m});
    syncFacadeFront();
    ed.planeSource = planeSource();
    if (parapetProblems().length) throw new Error(parapetProblems()[0]);
  }
  const reply = await ctx.post("my-roofs", payload());
  ed.clean = text(FIELDS);
  forget();
  ctx.notice("屋顶已保存");
  if (quickRun && ctx.quickRunRoof) {
    await ctx.quickRunRoof(reply.id, {
      ...(ed.aiDesign ?? {}),
      wind_roughness: ed.wind?.roughness || 'B',
      wind_pressure_kpa: num(ed.wind?.basic_pressure_kpa),
    });
    return;
  }
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
