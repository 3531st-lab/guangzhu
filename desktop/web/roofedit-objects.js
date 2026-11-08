import {esc} from './data.js';
import {rectangleInfo,itemCenter,itemBounds} from './roofedit-geometry.js';
import {selectedItems} from './roofedit-selection.js';

export function transformDefaults(items) {
  const bounds=itemBounds(items), center=bounds?.center ?? [0,0];
  return {mode:'move',dx:5,dy:0,angle:90,pivotX:center[0],pivotY:center[1],axisValue:(bounds?.max[0] ?? 0)+1,copy:false};
}

export function objectsPanel(ed, kinds, pixelMode) {
  const parts=ed.roofMode==='compound' ? ed.parts : [], selection=ed.selection;
  const items=selectedItems(selection,ed.items), active=items.find(item=>item.id===selection?.active);
  const part=parts.find(row=>selection?.kind==='part' && row.id===selection.active);
  const groups=[['建筑部分',parts.map(row=>({kind:'part',id:row.id,label:row.label,type:row.kind==='flat' ? '平顶' : '双坡'}))],
    ...[['屋面设备','obstacles'],['禁区与采光带','keepouts'],['周边建筑与树木','surroundings'],['电气位置','electrical']].map(([title,list])=>
      [title,ed.items.filter(item=>list==='electrical' ? ['inverter_positions','grid_point'].includes(kinds[item.kind][1]) : kinds[item.kind][1]===list)
        .map(item=>({kind:'item',id:item.id,label:item.label,type:kinds[item.kind][0]}))])];
  const listing=groups.filter(([,rows])=>rows.length).map(([title,rows])=>`<div class="re-object-group"><h4>${title}<small>${rows.length}</small></h4>
    ${rows.map(row=>`<button type="button" class="re-object-entry" data-object-select="${row.kind}" data-object-id="${esc(row.id)}"
      aria-pressed="${selection?.kind===row.kind && selection.ids.includes(row.id)}"><span>${esc(row.label)}</span><small>${row.type}</small></button>`).join('')}</div>`).join('');
  const title=part ? part.label : items.length>1 ? `已选择 ${items.length} 个对象` : active?.label;
  const shape=active && rectangleInfo(active.points), center=active && itemCenter(active);
  const fields=active && items.length===1 ? [['cx','中心 X（m）',center[0]],['cy','中心 Y（m）',center[1]],
    ...(shape ? [['w','长（m）',shape.w],['d','宽（m）',shape.d],['turn','旋转角（°）',shape.turn]] :
      active.center && kinds[active.kind][2]!=='point' ? [['radius','半径（m）',active.radius]] : [])] : [];
  const setting={...transformDefaults(items),...ed.transformSettings}, preview=ed.transformPreview;
  const number=(key,label,value)=>`<label class="field"><span>${label}</span><input type="number" step="any" required data-transform="${key}" value="${esc(value ?? '')}"></label>`;
  const canCopy=items.every(item=>item.kind!=='grid');
  return `<details class="card re-objects" id="re-object-browser" ${ed.objectsOpen===false ? '' : 'open'}><summary><span>建模对象</span><small>${parts.length} 个建筑部分 · ${ed.items.length} 个对象</small></summary>
    <div class="re-objects-body"><nav class="re-object-list" aria-label="建模对象列表">${listing || '<p class="muted">绘制设备、采光带或添加建筑部分后，可在此选择和精确编辑。</p>'}</nav>
    <p class="muted re-object-help">点击列表或图中对象选择；Ctrl／⌘ 点击可多选设备、禁区与周边对象。</p>
    ${title ? `<section class="re-object-inspector"><div class="re-object-heading"><strong>${esc(title)}</strong><button type="button" class="btn sm" data-re-act="object-clear">取消选择</button></div>
      <div class="re-row"><button type="button" class="btn sm" data-re-act="object-focus" ${pixelMode ? 'disabled' : ''}>定位对象</button>${items.length<=1 ? '<button type="button" class="btn sm" data-re-act="object-properties">更多属性</button>' : ''}
      ${items.length ? '<button type="button" class="btn sm ghost" data-re-act="object-delete">删除选中</button>' : ''}</div>
      ${pixelMode ? '<p class="re-object-warning">图纸尚未标定；先完成比例标定，再使用米制属性与精确变换。</p>' : fields.length ? `<div class="grid2">${fields.map(([key,label,value])=>`<label class="field"><span>${label}</span><input type="number" step="any" required data-object-prop="${key}" data-object-id="${esc(active.id)}" value="${esc(Number(value.toFixed(6)))}" ${['w','d','radius'].includes(key) ? 'min="0.01"' : ''}></label>`).join('')}</div>` :
        part ? `<p class="muted">${part.kind==='flat' ? '平顶' : '双坡'} · 檐口 ${esc(part.eave_height_m)} m。点击“更多属性”编辑位置、尺寸与屋面参数。</p>` : ''}
      ${items.length && !pixelMode ? `<div class="re-transform"><h4>精确变换</h4><label class="field"><span>方式</span><select data-transform="mode">${[['move','相对移动'],['rotate','绕点旋转'],['mirror-x','左右镜像（轴 X = 指定值）'],['mirror-y','上下镜像（轴 Y = 指定值）']].map(([value,label])=>`<option value="${value}" ${setting.mode===value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <div class="grid2">${setting.mode==='move' ? number('dx','ΔX 向东（m）',setting.dx)+number('dy','ΔY 向北（m）',setting.dy) : setting.mode==='rotate' ?
          number('angle','逆时针转角（°）',setting.angle)+number('pivotX','旋转中心 X（m）',setting.pivotX)+number('pivotY','旋转中心 Y（m）',setting.pivotY) :
          number('axisValue',setting.mode==='mirror-x' ? '镜像轴 X（m）' : '镜像轴 Y（m）',setting.axisValue)}</div>
        <label class="toggle"><span>保留原对象，生成副本</span><input type="checkbox" data-transform="copy" ${setting.copy && canCopy ? 'checked' : ''} ${canCopy ? '' : 'disabled'}></label>
        ${canCopy ? '' : '<p class="muted">并网点保持唯一，当前选择仅可变换原对象。</p>'}
        <div class="re-row"><button type="button" class="btn sm" data-re-act="transform-preview">预览变换</button>${preview ? '<button type="button" class="btn sm primary" data-re-act="transform-apply">应用变换</button><button type="button" class="btn sm" data-re-act="transform-cancel">取消预览</button>' : ''}</div>
        <p class="muted">${preview ? `二维虚线为${preview.copy ? '新增' : '变换后'}的 ${preview.items.length} 个对象；应用后可一步撤销。` : '先预览，确认后应用。旋转中心默认取所选对象整体包围框中心。'}</p></div>` : ''}
    </section>` : '<p class="muted">未选择对象。选择不会改变模型或产生未保存修改。</p>'}</div></details>`;
}

export function viewTools() {
  return `<div class="re-view-tools" id="re-view-tools" hidden aria-label="三维标准视图">
    <div class="re-view-presets">${[['iso','轴测'],['top','俯视'],['front','主立面'],['north','北'],['east','东'],['south','南'],['west','西']].map(([key,label])=>`<button type="button" data-re-view="${key}" title="${['iso','top','front'].includes(key) ? label : label+'立面'}">${label}</button>`).join('')}</div>
    <select data-re-projection aria-label="投影方式"><option value="perspective">透视</option><option value="orthographic">正交</option></select>
    <button type="button" data-re-act="view-fit">适合全部</button><button type="button" data-re-act="object-focus" data-view-selection>定位选中</button>
  </div>`;
}
