import {esc} from './data.js';

const number = value => Number.isFinite(value) ? value.toLocaleString('zh-CN', {maximumFractionDigits:2}) : '未提供';
const ruleValue = value => Array.isArray(value) ? `[${value.map(number).join(', ')}]` : number(value);
const action = (name, label, disabled = false) => `<button class="btn sm" data-design-edit="${name}" ${disabled ? 'disabled' : ''}>${label}</button>`;

export function newEditState(result) {
  return {key:`${result.project_id}/${result.version}`, selected:new Set(), plane:'', busy:false, preview:null,
    request:null,requestEpoch:0,pendingKind:null,previewAction:null,
    toolMode:'off',snap:{enabled:true,gridM:.1,angleDeg:15,align:true},dragging:false,transformText:'',
    reason:'调整局部组件与排布，保留已锁定设计', detailed:false, region:{x:0,y:0,w:10,h:10},manualMode:'add',picking:false,
    add:{x:null,y:null,plane:'',orientation:result.design?.params?.orientation ?? 'portrait',rotation:0},move:{dx:0,dy:0},rotate:{angle:90},
    params:Object.fromEntries(['orientation','edge_setback_m','walkway_every_n_rows','walkway_width_m']
      .map(key => [key, result.design?.params?.[key]]))};
}

export function invalidateEdit(state) {
  state.requestEpoch=(state.requestEpoch ?? 0)+1;
  state.preview=null;state.request=null;state.previewAction=null;state.error='';
  state.dragging=false;state.transformText='';
  if (state.pendingKind!=='apply') {state.busy=false;state.pendingKind=null;}
}

export function manualUnavailable(result) {
  const roof=result.scene?.project?.roof ?? result.project.roof, params=result.design?.params ?? {};
  if (!['flat','metal','pitched'].includes(roof.type)) return '空地和车棚的支架、基础需要整体联动，暂不支持手动补放、移动或旋转；仍可使用锁定、删除与排布预览。';
  if (params.layout==='ew') return '当前为东西向成对排布，暂不支持手动补放、移动或旋转；仍可使用锁定、删除与排布预览。';
  if ((params.rows_per_rack ?? 1)>1) return '当前为一架多排组件，暂不支持单板手动几何编辑；仍可使用锁定、删除与排布预览。';
  return '';
}

export function editLockedIds(result) {
  const design=result.design ?? {}, planes=new Set(design.locked_plane_ids ?? []);
  return new Set([...(result.locked_modules ?? []),...(design.locked_module_ids ?? []),
    ...(design.modules ?? []).filter(module=>planes.has(Number(/^P(\d+)-/.exec(module.id)?.[1]))).map(module=>module.id)]);
}

export function moduleEditingUnavailable(result,state) {
  const unsupported=manualUnavailable(result);
  if (unsupported) return unsupported;
  const spec=result.scene?.module_transform_spec;
  if (spec?.available!==true) return spec?.reason || '此版本缺少精确组件尺寸，暂不能三维拖动；可继续使用下方数字操作。';
  if (state.snap.enabled && (!Number.isFinite(state.snap.gridM) || state.snap.gridM<=0 ||
      !Number.isFinite(state.snap.angleDeg) || state.snap.angleDeg<=0 || state.snap.angleDeg>180))
    return '请填写大于 0 的网格间距，以及 0° 至 180° 之间的吸附角度。';
  return '';
}

export function moduleEditingOptions(result,state,active=true) {
  return {enabled:active && state.toolMode!=='off' && !moduleEditingUnavailable(result,state),mode:state.toolMode,
    selectedIds:[...state.selected],lockedIds:[...editLockedIds(result)],snap:{...state.snap},
    busy:state.busy || Boolean(state.preview)};
}

function sceneToolsMarkup(result,state) {
  const unavailable=moduleEditingUnavailable(result,state),committing=state.pendingKind==='apply';
  const blocked=[...state.selected].filter(id=>editLockedIds(result).has(id)).length;
  const params=result.design?.params ?? {}, canUnlockDrag=params.layout==='ew' || (params.rows_per_rack ?? 1)>1;
  const text=state.transformText || unavailable || (state.busy ? '正在校验候选位置，请稍候…' : state.preview ?
    '候选尚未保存：确认保存或取消预览后，可继续三维编辑。' : blocked ?
    `选中 ${state.selected.size} 块，其中 ${blocked} 块已锁定；可预览解锁，不能拖动。` : !state.selected.size ?
    (state.toolMode==='off' ? '点击「移动」或「旋转」后，可直接在左侧 3D 画面按住任意光伏板拖拽移动，或先点选组件再调整。' :
    '已开启 3D 直接拖拽：直接在左侧三维画面按住任意未锁定光伏板即可拖动，松开后自动校验并生成预览。') : state.toolMode==='off' ?
    `已选 ${state.selected.size} 块；选择移动或旋转可直接在三维中调整。` :
    `在三维中拖动已选的 ${state.selected.size} 块组件（或直接按住其他组件拖动）；松开后自动校验并生成预览。`);
  return `<section class="de-scene-tools"><h3>三维直接编辑</h3><div class="actions" aria-label="三维组件工具">
    ${[['off','浏览'],['move','移动'],['rotate','旋转']].map(([mode,label])=>`<button class="btn sm" data-design-edit="tool:${mode}" aria-pressed="${state.toolMode===mode}" ${committing || mode!=='off' && unavailable ? 'disabled' : ''}>${label}</button>`).join('')}
    ${canUnlockDrag ? `<button type="button" class="btn sm" data-copilot-act="unlock_3d_drag">🔓 转为单排支架</button>` : ''}</div><fieldset ${committing ? 'disabled' : ''}><div class="de-snap-switches">
      <label><input type="checkbox" data-edit-snap="enabled" ${state.snap.enabled ? 'checked' : ''}> 吸附</label>
      <label><input type="checkbox" data-edit-snap="align" ${state.snap.align ? 'checked' : ''}> 邻板对齐</label></div>
      <div class="grid2"><label class="field"><span>网格间距 / m</span><input type="number" min="0.001" step="any" data-edit-snap="gridM" value="${esc(state.snap.gridM ?? '')}"></label>
      <label class="field"><span>角度吸附 / °</span><input type="number" min="0.1" max="180" step="any" data-edit-snap="angleDeg" value="${esc(state.snap.angleDeg ?? '')}"></label></div></fieldset>
    <p class="de-transform-status" data-edit-transform-status role="status">${esc(text)}</p>
    <p class="muted">Alt 临时关闭吸附 · Esc 取消拖动。松开只生成预览，确认后才保存新版本。</p></section>`;
}

const manualPlanes=result=>{
  const roof=result.scene?.project?.roof ?? result.project.roof, ids=result.design?.params?.plane_ids;
  return (roof.planes ?? []).filter(plane=>plane.material!=='glass' && (!ids || ids.includes(plane.id)));
};
const differentGeometry=(a,b)=>JSON.stringify(a.corners)!==JSON.stringify(b.corners);
export function editDifference(result,state) {
  const before=new Map((result.design?.modules ?? []).map(module=>[module.id,module])), after=new Map((state.preview?.design?.modules ?? result.design?.modules ?? []).map(module=>[module.id,module]));
  return {added:[...after.keys()].filter(id=>!before.has(id)),removed:[...before.keys()].filter(id=>!after.has(id)),
    changed:[...after.keys()].filter(id=>before.has(id) && differentGeometry(before.get(id),after.get(id)))};
}

export function designEditPlan(result, state) {
  const roof = result.scene?.project?.roof ?? result.project.roof, design = state.preview?.design ?? result.design;
  const xs = roof.outline.map(p => p[0]), ys = roof.outline.map(p => p[1]);
  const [x,y,w,h] = [Math.min(...xs)-1,-Math.max(...ys)-1,Math.max(...xs)-Math.min(...xs)+2,Math.max(...ys)-Math.min(...ys)+2];
  const points = rows => rows.map(p => `${p[0]},${-p[1]}`).join(' ');
  const locked = new Set(state.preview?.changes?.locked ?? [...editLockedIds(result)]), planes = new Set(design.locked_plane_ids ?? []);
  const changes=editDifference(result,state), added=new Set(changes.added), changed=new Set(changes.changed), removed=new Set(changes.removed);
  const changeKind=state.previewAction==='move' ? 'moved' : state.previewAction==='rotate' ? 'rotated' : 'changed';
  const target=state.manualMode==='add' && Number.isFinite(state.add?.x) && Number.isFinite(state.add?.y), cross=Math.max(w,h)*.012;
  return `<svg class="de-plan${state.picking ? ' de-picking' : ''}" viewBox="${x} ${y} ${w} ${h}" aria-label="组件选择平面图">
    <polygon points="${points(roof.outline)}" fill="var(--bg, #f2ede5)" stroke="#95897a" stroke-width=".12"/>
    ${(roof.planes ?? []).map(plane=>`<polygon class="de-roof-plane" points="${points(plane.outline)}"><title>P${plane.id}${plane.part_id ? ' / '+esc(plane.part_id) : ''}</title></polygon>`).join('')}
    ${[...(roof.keepouts ?? []),...(design.added_keepouts ?? [])].map(zone=>`<polygon class="de-keepout" points="${points(zone.polygon)}"><title>${esc(zone.label ?? zone.id)}</title></polygon>`).join('')}
    ${(roof.obstacles ?? []).map(obstacle=>obstacle.kind==='cylinder' ? `<circle class="de-obstacle" cx="${obstacle.center[0]}" cy="${-obstacle.center[1]}" r="${obstacle.radius_m}"><title>${esc(obstacle.label ?? obstacle.id)}</title></circle>` :
      `<polygon class="de-obstacle" points="${points(obstacle.footprint)}"><title>${esc(obstacle.label ?? obstacle.id)}</title></polygon>`).join('')}
    ${(design.locked_regions ?? []).map(r => `<polygon points="${points(r.polygon)}" fill="#d7993533" stroke="#d79935" stroke-width=".15"/>`).join('')}
    ${(state.preview ? result.design.modules : []).filter(module=>changed.has(module.id) || removed.has(module.id)).map(module=>
      `<polygon class="de-before ${removed.has(module.id) ? 'de-removed' : ''}" data-edit-before="${esc(module.id)}" points="${points(module.corners)}"><title>${esc(module.id)} · ${removed.has(module.id) ? '将删除' : '修改前位置'}</title></polygon>`).join('')}
    ${design.modules.map(m => `<polygon data-edit-module="${esc(m.id)}" data-edit-change="${added.has(m.id) ? 'added' : changed.has(m.id) ? changeKind : ''}" points="${points(m.corners)}"
      fill="${state.selected.has(m.id) ? '#299b82' : locked.has(m.id) || planes.has(Number(m.id.split('-')[0].slice(1))) ? '#cf943b' : '#29476c'}"
      stroke="#fff" stroke-width=".07"><title>${esc(m.id)}${added.has(m.id) ? ' · 新增' : changed.has(m.id) ? changeKind==='moved' ? ' · 移动后' : changeKind==='rotated' ? ' · 旋转后' : ' · 几何已变化' : ''}</title></polygon>`).join('')}
    ${target ? `<g class="de-add-target" pointer-events="none"><path d="M${state.add.x-cross} ${-state.add.y}h${cross*2}M${state.add.x} ${-state.add.y-cross}v${cross*2}"/><circle cx="${state.add.x}" cy="${-state.add.y}" r="${cross*.35}"/><title>待补放中心 X=${state.add.x}，Y=${state.add.y}；实际组件以服务器预览为准</title></g>` : ''}</svg>`;
}

function previewMarkup(result, state) {
  const p = state.preview;
  if (!p) return '<p class="muted">先预览，确认后才会生成新版本。原版本始终保留。</p>';
  const original = result.design, changes=editDifference(result,state), added=changes.added.length,removed=changes.removed.length;
  const changedLabel=state.previewAction==='move' ? '移动' : state.previewAction==='rotate' ? '旋转' : '位置／朝向变化';
  const impact = p.impact;
  return `<section class="fcard de-preview"><h3>修改预览 · 尚未保存</h3><p>${esc(p.summary ?? '')}</p>
    <p>组件 ${original.modules.length} → ${p.design.modules.length}；新增 ${added}，移除 ${removed}，${changedLabel} ${changes.changed.length}。
    装机 ${number(original.statistics?.dc_kw)} → ${number(p.design.statistics?.dc_kw)} kWp。</p>
    ${impact?.available ? `<table><thead><tr><th>指标</th><th>修改前</th><th>修改后</th></tr></thead><tbody>
      ${[['annual_kwh','年发电 / kWh'],['capex_cny','造价 / 元'],['payback_years','静态回本 / 年'],['hard_failed','硬性规则未通过']]
        .map(([key,label]) => `<tr><td>${label}</td><td>${number(impact.before[key])}</td><td>${number(impact.after[key])}</td></tr>`).join('')}
        ${[['avg_loss_pct','平均遮挡损失 / %'],['max_loss_pct','最大遮挡损失 / %'],['modules_over_threshold','遮挡超阈值组件 / 块']].map(([key,label])=>
          `<tr><td>${label}</td><td>${number(impact.before.shading?.[key])}</td><td>${number(impact.after.shading?.[key])}</td></tr>`).join('')}
      </tbody></table><p>受影响组串 ${impact.affected_strings.length} 个。${esc(impact.note)}</p>
      ${impact.after.failed.map(row => `<p class="muted">${esc(row.id)} · ${esc(row.name_zh)}：${ruleValue(row.value)} / ${ruleValue(row.limit)}${row.hint_zh ? `<br>${esc(row.hint_zh)}` : ''}</p>`).join('')}`
      : `<p>${esc(impact?.reason ?? '发电、造价、回本及组串尚未复算。')}</p>`}
    ${impact?.available && impact.shading_changes?.length ? `<details class="de-shading-changes"><summary>逐组件遮挡变化 · ${impact.shading_changes.length} 块</summary>
      <p>显示前 ${Math.min(50,impact.shading_changes.length)} 块；“—”表示该版本没有此组件。</p><table><thead><tr><th>组件</th><th>原损失 %</th><th>新损失 %</th><th>变化百分点</th></tr></thead><tbody>
      ${impact.shading_changes.slice(0,50).map(row=>`<tr><td>${esc(row.id)}</td><td>${row.before_loss_pct==null ? '—' : number(row.before_loss_pct)}</td><td>${row.after_loss_pct==null ? '—' : number(row.after_loss_pct)}</td><td>${row.delta_loss_pct==null ? '—' : number(row.delta_loss_pct)}</td></tr>`).join('')}</tbody></table></details>` : ''}
    <p>保存的是待审核设计；通过工程校核后才能申请导出。</p>
    <div class="actions">${action('apply','确认并保存新版本',state.busy)}${action('cancel','取消预览',state.pendingKind==='apply')}</div></section>`;
}

function manualMarkup(result,state) {
  const unavailable=manualUnavailable(result), roof=result.scene?.project?.roof ?? result.project.roof;
  const committing=state.pendingKind==='apply', blocked=[...state.selected].filter(id=>editLockedIds(result).has(id));
  const numeric=(group,key,label,value,limits='')=>`<label class="field"><span>${label}</span><input type="number" required step="any" data-edit-${group}="${key}" value="${esc(value ?? '')}" ${limits}></label>`;
  return `<section class="de-manual"><h3>手动组件</h3>${unavailable ? `<p class="de-unavailable">${esc(unavailable)}</p>` : ''}
    <fieldset ${committing || unavailable ? 'disabled' : ''}><label class="field"><span>操作</span><select data-edit-field="manualMode">
      ${[['add','补放组件'],['move','移动所选'],['rotate','旋转所选']].map(([key,label])=>`<option value="${key}" ${state.manualMode===key ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
      ${state.manualMode==='add' ? `<div class="actions">${action('pick-add',state.picking ? '退出点选中心' : '在平面图点选中心')}</div>
        <p class="muted">${state.picking ? '现在点击上方平面图设置中心点；十字仅表示中心，组件实际轮廓以预览为准。' : '可点选中心或输入坐标；使用本项目的组件规格。'}</p>
        <div class="grid2">${numeric('add','x','中心 X 向东 / m',state.add.x)}${numeric('add','y','中心 Y 向北 / m',state.add.y)}
        <label class="field"><span>组件方向</span><select data-edit-add="orientation"><option value="portrait" ${state.add.orientation==='portrait' ? 'selected' : ''}>竖排</option><option value="landscape" ${state.add.orientation==='landscape' ? 'selected' : ''}>横排</option></select></label>
        ${numeric('add','rotation','顺时针旋转 / °',state.add.rotation,'min="-360" max="360"')}</div>
        ${roof.type==='pitched' ? `<label class="field"><span>所属安装面（必选）</span><select data-edit-add="plane"><option value="">请选择安装面</option>${manualPlanes(result).map(plane=>
          `<option value="${plane.id}" ${Number(state.add.plane)===plane.id ? 'selected' : ''}>P${plane.id}${plane.part_id ? ' · '+esc((roof.parts ?? []).find(part=>part.id===plane.part_id)?.label ?? plane.part_id) : ''} · ${plane.slope_deg}°</option>`).join('')}</select></label>` : ''}
        <p>${action('add','预览补放',state.busy)}</p>` :
      state.manualMode==='move' ? `<p>选中 ${state.selected.size} 块，按屋顶平面坐标一起平移；坡屋面保持各自所属安装面。</p><div class="grid2">${numeric('move','dx','ΔX 向东 / m',state.move.dx)}${numeric('move','dy','ΔY 向北 / m',state.move.dy)}</div>
        <p>${action('move','预览移动',state.busy || !state.selected.size || blocked.length>0)}</p>` :
        `<p>选中 ${state.selected.size} 块，各板绕自身中心旋转；正角为顺时针。${roof.type==='flat' ? '保持支架倾角，组件朝向同步改变。' : '坡屋面内转动，保持屋面法向。'}</p>${numeric('rotate','angle','顺时针旋转 / °',state.rotate.angle,'min="-360" max="360"')}
        <p>${action('rotate','预览旋转',state.busy || !state.selected.size || blocked.length>0)}</p>`}
      ${state.manualMode!=='add' && blocked.length ? `<p class="de-lock-note">所选中有 ${blocked.length} 块受组件、屋面或区域锁保护。先预览并确认解锁，再移动或旋转。</p>` : ''}
      <p class="muted">预览会检查屋边、设备、禁区、板间距和锁定；勾选下方详细复算可比较遮挡与发电。</p>
    </fieldset></section>`;
}

export function designEditMarkup(result, state) {
  if (result.editable === false) return '<p>这是归档运行的证据副本。请打开本机项目的设计结果进行修改。</p>';
  if (!result.design) return '<p>此版本缺少可编辑的组件数据。</p>';
  const planes = result.project.roof.planes ?? [], disabled = state.pendingKind==='apply', locked=editLockedIds(result);
  const selectedLocked=[...state.selected].filter(id=>locked.has(id)).length;
  const numeric = (key,label,min=0,step='any') => `<label class="field">${label}<input type="number" data-edit-param="${key}" min="${min}" step="${step}" value="${esc(state.params[key] ?? '')}"></label>`;
  return `<div class="de-editor"><h3>局部组件编辑</h3><p>点平面图或三维组件切换选择。绿色为选中，金色为锁定。</p>
    ${sceneToolsMarkup(result,state)}
    ${designEditPlan(result,state)}<p>已选 ${state.selected.size} 块 · 组件锁 ${(result.design.locked_module_ids ?? []).length} 块
      · 屋面锁 ${(result.design.locked_plane_ids ?? []).length} 个 · 区域锁 ${(result.design.locked_regions ?? []).length} 个</p>
    ${state.preview ? '<div class="de-change-legend"><span class="added">新增</span><span class="moved">移动后</span><span class="rotated">旋转后</span><span class="before">旧位置</span><span class="removed">删除</span></div>' : ''}
    ${manualMarkup(result,state)}<h3>锁定与局部重排</h3>
    <fieldset ${disabled ? 'disabled' : ''}><div class="actions">${action('select-all','全选')}${action('clear','清空选择')}
      ${action('lock','预览锁定所选',state.busy || !state.selected.size)}${action('unlock','预览解锁所选',state.busy || !state.selected.size)}${action('remove','预览删除所选',state.busy || !state.selected.size || selectedLocked>0)}</div>
    ${selectedLocked ? `<p class="de-lock-note">所选中有 ${selectedLocked} 块已锁定；解锁确认前不能删除或修改其几何。</p>` : ''}
    ${planes.length ? `<label class="field">按屋面锁定<select data-edit-field="plane"><option value="">选择屋面</option>${planes.map(p =>
      `<option value="P${p.id}" ${state.plane === `P${p.id}` ? 'selected' : ''}>P${p.id}${p.part_id ? ` · ${esc(p.part_id)}` : ''}</option>`).join('')}</select></label>
      <div class="actions">${action('lock-plane','预览锁定屋面',state.busy)}${action('unlock-plane','预览解锁屋面',state.busy)}</div>` : ''}
    <details><summary>按矩形区域锁定</summary><div class="grid2">${[['x','左下角 X / m'],['y','左下角 Y / m'],['w','宽 / m'],['h','深 / m']].map(([key,label]) =>
      `<label class="field">${label}<input type="number" step="any" data-edit-region="${key}" value="${state.region[key]}"></label>`).join('')}</div>
      ${action('lock-region','预览锁定区域',state.busy)}${(result.design.locked_regions ?? []).map(r => `<p>${esc(r.id)} ${action('unlock-region:'+r.id,'预览解锁',state.busy)}</p>`).join('')}</details>
    <h3>其余区域的排布参数</h3><div class="grid2"><label class="field">组件方向<select data-edit-param="orientation">
      <option value="portrait" ${state.params.orientation === 'portrait' ? 'selected' : ''}>竖排</option><option value="landscape" ${state.params.orientation === 'landscape' ? 'selected' : ''}>横排</option></select></label>
      ${numeric('edge_setback_m','距屋边 / m')}${numeric('walkway_every_n_rows','每几排留通道（0 为不增加）',0,1)}${numeric('walkway_width_m','通道宽 / m')}</div>
    <label class="field">修改原因<input data-edit-field="reason" value="${esc(state.reason)}" maxlength="1000"></label>
    <label><input type="checkbox" data-edit-field="detailed" ${state.detailed ? 'checked' : ''}> 详细复算遮挡、发电、造价、回本和组串（使用现有天气，耗时较长）</label>
    <p>${action('reflow','预览局部重排',state.busy)}</p></fieldset>
    ${state.busy ? `<div class="de-progress"><p role="status">${disabled ? '正在保存新版本，请稍候…' : '正在计算预览，可修改参数或取消这次请求。'}</p>${disabled ? '' : action('cancel','取消这次预览')}</div>` : ''}${state.error ? `<p class="de-error" role="alert">${esc(state.error)}</p>` : ''}
    ${previewMarkup(result,state)}${result.design.parent_version ? `<p>${action('undo','预览撤销上次修改',state.busy)}</p>` : ''}
    <details><summary>查看原版本</summary><p>切换历史版本只改变查看内容；撤销会在确认后另存新版本。</p>
    ${(result.versions ?? []).map(v => `<button class="btn sm" data-version="${v.version}">v${v.version}</button>`).join(' ')}</details></div>`;
}

export function editOperation(actionName, state, result) {
  const selected = [...state.selected];
  if (actionName === 'undo') return [{op:'undo_last_edit'}];
  if (['add','move','rotate'].includes(actionName)) {
    const unavailable=manualUnavailable(result);
    if (unavailable) throw new Error(unavailable);
    if (actionName==='add') {
      const {x,y,plane,orientation,rotation}=state.add, roof=result.scene?.project?.roof ?? result.project.roof;
      if (![x,y].every(Number.isFinite)) throw new Error('请先点选补放中心，或填写有效的 X、Y 坐标。');
      if (!['portrait','landscape'].includes(orientation)) throw new Error('请选择竖排或横排。');
      if (!Number.isFinite(rotation) || rotation < -360 || rotation > 360) throw new Error('补放旋转角须为 -360° 至 360° 的有限数值。');
      const placement={center:[x,y],orientation,rotation_deg:rotation};
      if (roof.type==='pitched') {
        const id=Number(plane);
        if (!Number.isInteger(id) || !manualPlanes(result).some(row=>row.id===id)) throw new Error('请为补放组件选择可安装的屋面。');
        placement.plane_id=id;
      }
      return [{op:'add_modules',placements:[placement]}];
    }
    if (!selected.length) throw new Error('请先选择要修改的组件。');
    if (selected.some(id=>editLockedIds(result).has(id))) throw new Error('所选包含已锁定组件，请先预览并确认解锁。');
    if (actionName==='move') {
      const {dx,dy}=state.move;
      if (![dx,dy].every(Number.isFinite) || dx===0 && dy===0) throw new Error('请填写有效的 ΔX、ΔY，且不能同时为 0。');
      return [{op:'move_modules',module_ids:selected,dx_m:dx,dy_m:dy}];
    }
    const angle=state.rotate.angle;
    if (!Number.isFinite(angle) || angle < -360 || angle > 360 || angle%360===0) throw new Error('旋转角须在 -360° 至 360° 之间，且须产生实际转动。');
    return [{op:'rotate_modules',module_ids:selected,angle_deg:angle}];
  }
  if (['lock','unlock','remove'].includes(actionName)) {
    if (!selected.length) throw new Error('请先选择组件。');
    if (actionName==='remove' && selected.some(id=>editLockedIds(result).has(id))) throw new Error('所选包含已锁定组件，请先预览并确认解锁。');
    return [{op:{lock:'lock_modules',unlock:'unlock_modules',remove:'remove_modules'}[actionName],module_ids:selected}];
  }
  if (['lock-plane','unlock-plane'].includes(actionName)) {
    if (!state.plane) throw new Error('请先选择屋面。');
    return [{op:actionName === 'lock-plane' ? 'lock_plane' : 'unlock_plane',plane_id:Number(state.plane.slice(1))}];
  }
  if (actionName.startsWith('unlock-region:')) return [{op:'unlock_region',id:actionName.slice('unlock-region:'.length)}];
  if (actionName === 'lock-region') {
    const {x,y,w,h} = state.region;
    if (![x,y,w,h].every(Number.isFinite) || w <= 0 || h <= 0) throw new Error('区域坐标须为数值，宽和深须大于 0。');
    const ids = new Set((result.design.locked_regions ?? []).map(r => r.id));
    let serial = 1;
    while (ids.has(`manual-${serial}`)) serial++;
    return [{op:'lock_region',id:`manual-${serial}`,polygon:[[x,y],[x+w,y],[x+w,y+h],[x,y+h]]}];
  }
  if (actionName === 'reflow') {
    if (!['edge_setback_m','walkway_every_n_rows','walkway_width_m'].every(key => Number.isFinite(state.params[key]) && state.params[key] >= 0)
      || !Number.isInteger(state.params.walkway_every_n_rows)) throw new Error('请填写非负排布参数，排数须为整数。');
    return [{op:'reflow_unlocked',params:{...state.params}}];
  }
  throw new Error('未知修改操作。');
}

export async function performEdit(actionName, result, state, context, explicitRequest=null) {
  if (state.pendingKind==='apply') return;
  if (actionName.startsWith('tool:')) {
    const mode=actionName.slice(5);
    if (!['off','move','rotate'].includes(mode)) return;
    if (mode!=='off' && moduleEditingUnavailable(result,state)) throw new Error(moduleEditingUnavailable(result,state));
    context.cancelGesture?.();invalidateEdit(state);state.toolMode=mode;state.picking=false;
    if (mode!=='off') state.manualMode=mode;
    context.redraw();context.scene();return;
  }
  if (actionName === 'select-all' || actionName === 'clear') {
    context.cancelGesture?.();
    invalidateEdit(state);
    state.selected = new Set(actionName === 'select-all' ? result.design.modules.map(m => m.id) : []);
    state.picking=false;context.redraw(); context.scene(); return;
  }
  if (actionName === 'cancel') {context.cancelGesture?.();invalidateEdit(state);state.picking=false;context.redraw();context.scene();return;}
  if (actionName==='pick-add') {
    if (manualUnavailable(result)) throw new Error(manualUnavailable(result));
    context.cancelGesture?.();invalidateEdit(state);state.manualMode='add';state.toolMode='off';state.picking=!state.picking;
    context.redraw();context.scene();
    if (state.picking && globalThis.document) {
      const rp = globalThis.document.getElementById?.('result-panel');
      if (rp) rp.scrollTop = 0;
    }
    return;
  }
  if (state.busy) return;
  if (explicitRequest && (!Array.isArray(explicitRequest.ops) || !explicitRequest.ops.length ||
      explicitRequest.version!==result.version)) throw new Error('修复预览与当前设计版本不一致，请重新查看规则。');
  const request = actionName === 'apply' ? state.request : explicitRequest ? {version:result.version,
    ops:structuredClone(explicitRequest.ops),reason:String(explicitRequest.reason ?? '').trim(),detailed:explicitRequest.detailed===true} :
    {version:result.version,ops:editOperation(actionName,state,result),reason:state.reason.trim(),detailed:state.detailed};
  if (!request?.reason) throw new Error('请填写本次修改原因。');
  if (actionName === 'apply' && !state.preview) return;
  context.cancelGesture?.();
  const token=++state.requestEpoch, current=()=>state.requestEpoch===token;
  const fingerprint=state.preview?.fingerprint;
  if (actionName!=='apply') {state.preview=null;state.request=null;state.previewAction=null;context.scene();}
  state.busy = true; state.pendingKind=actionName==='apply' ? 'apply' : 'preview';state.picking=false;state.error = '';state.transformText='';context.redraw();
  try {
    const path = `projects/${encodeURIComponent(result.project_id)}/design-edits/`;
    if (actionName === 'apply') {
      const saved = await context.api(path+'apply',{...request,fingerprint});
      if (!current() || context.current?.()===false) return;
      state.preview = null;state.request=null;
      context.notice(`已保存 v${saved.version}。${saved.analysis_complete ? '已完成复算，请查看规则。' : saved.analysis_error ? '复算未完成：'+saved.analysis_error : '发电与经济指标待复算。'}`);
      context.navigate(saved.version);
    } else {
      const response = await context.api(path+'preview',request);
      if (!current() || context.current?.()===false) return;
      state.preview=response;
      state.request = request;
      state.previewAction=actionName;
      state.transformText='';
      context.scene(state.preview.design);
    }
  } catch (error) {
    if (!current() || context.current?.()===false) return;
    state.preview = null;state.request=null;state.previewAction=null;state.error = error.message; context.scene();
  } finally {
    if (current()) {state.busy=false;state.pendingKind=null;context.redraw();}
  }
}
