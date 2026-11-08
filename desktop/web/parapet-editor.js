import {esc} from './data.js';
import {facadeEdges} from './facade-editor.js';

const EPS = 1e-7;
export const normalizeParapets = segments => segments == null ? null :
  segments.map(row => ({start_ratio:0,end_ratio:1,...row}));
const lengthOf = (outline, index) => {
  const a = outline[index], b = outline[(index + 1) % outline.length];
  return a && b ? Math.hypot(b[0] - a[0], b[1] - a[1]) : 0;
};
const sameOutline = (a, b) => Array.isArray(a) && a.length === b.length &&
  a.every((p, i) => p.length === 2 && p.every((v, axis) => Math.abs(v - b[i][axis]) <= EPS));

export function parapetIssues(segments, outline, anchor) {
  if (segments == null || Array.isArray(segments) && !segments.length) return [];
  if (!Array.isArray(segments)) return ['女儿墙分段数据无效，请重新生成。'];
  segments = normalizeParapets(segments);
  if (!sameOutline(anchor, outline)) return ['屋顶轮廓已变更，原女儿墙边号不再可靠。请按当前轮廓重新生成，或恢复全周统一高度。'];
  const issues = [];
  if (segments.length > 256) issues.push('最多支持 256 段女儿墙。');
  segments.forEach((segment, index) => {
    const {edge_index:edge, start_ratio:start, end_ratio:end, height_m:height} = segment;
    if (!Number.isInteger(edge) || edge < 0 || edge >= outline.length || lengthOf(outline, edge) < EPS)
      issues.push(`第 ${index + 1} 段的外墙边不存在。`);
    if (![start,end,height].every(Number.isFinite) || start < 0 || end > 1 || start >= end || height < 0 || height > 3)
      issues.push(`第 ${index + 1} 段须位于墙边以内，起点小于终点，高度为 0 至 3 m。`);
    if (segments.slice(0,index).some(other => other.edge_index === edge && Math.min(end,other.end_ratio) > Math.max(start,other.start_ratio)))
      issues.push(`第 ${index + 1} 段与同一墙边的已有段重叠。`);
  });
  return issues;
}

function allEdges(outline, height) {
  if (!Number.isFinite(height) || height < 0 || height > 3) throw new Error('全周女儿墙高度须为 0 至 3 m');
  if (outline.length < 3) throw new Error('请先完成屋顶轮廓');
  return outline.map((_, edge_index) => ({edge_index,start_ratio:0,end_ratio:1,height_m:height}));
}

// Return a new value; the editor owns the single undo transaction for each action.
export function parapetAction(action, segments, outline, uniformHeight) {
  segments = normalizeParapets(segments);
  const anchor = structuredClone(outline);
  if (action === 'parapet-uniform') return {segments:null,anchor:null};
  if (action === 'parapet-none') return {segments:[],anchor};
  if (action === 'parapet-custom' || action === 'parapet-reset') return {segments:allEdges(outline,uniformHeight),anchor};
  if (action.startsWith('parapet-delete-')) {
    const index = Number(action.slice('parapet-delete-'.length));
    if (!Array.isArray(segments) || !Number.isInteger(index) || index < 0 || index >= segments.length) throw new Error('找不到这段女儿墙');
    return {segments:segments.filter((_,i) => i !== index),anchor};
  }
  if (action !== 'parapet-add') throw new Error('未知的女儿墙操作');
  if (!Array.isArray(segments)) throw new Error('请先切换到分段编辑');
  if (!Number.isFinite(uniformHeight) || uniformHeight < 0 || uniformHeight > 3) throw new Error('请先填写 0 至 3 m 的全周女儿墙高度，作为新增段的初始高度');
  if (segments.length >= 256) throw new Error('最多支持 256 段女儿墙');
  for (let edge = 0; edge < outline.length; edge++) {
    const ranges = segments.filter(row => row.edge_index === edge).toSorted((a,b) => a.start_ratio - b.start_ratio);
    let start = 0;
    for (const range of [...ranges,{start_ratio:1,end_ratio:1}]) {
      if (range.start_ratio - start > EPS) return {segments:[...structuredClone(segments),
        {edge_index:edge,start_ratio:start,end_ratio:range.start_ratio,height_m:uniformHeight}],anchor};
      start = Math.max(start,range.end_ratio);
    }
  }
  throw new Error('各边已全部覆盖。先缩短或删除一段，再在空缺处添加。');
}

export function parapetChange(segments, index, key, raw, outline) {
  if (!Array.isArray(segments) || !segments[index]) throw new Error('找不到这段女儿墙');
  if (raw == null || String(raw).trim() === '' || !Number.isFinite(Number(raw))) throw new Error('请填写有效的女儿墙尺寸');
  const value = Number(raw), result = normalizeParapets(segments), row = result[index], length = lengthOf(outline,row.edge_index);
  if (key === 'edge_index') {
    if (!Number.isInteger(value) || value < 0 || value >= outline.length) throw new Error('请选择有效的外墙边');
    row.edge_index = value;
  } else if (key === 'start_m' || key === 'end_m') {
    if (length < EPS) throw new Error('当前墙边长度无效');
    const ratio = value / length;
    // Preserve exact shared endpoints when decimal metre display introduces sub-nanometre noise.
    const ends = [0,1,...result.filter((other,i) => i !== index && other.edge_index === row.edge_index)
      .flatMap(other => [other.start_ratio,other.end_ratio])];
    row[key === 'start_m' ? 'start_ratio' : 'end_ratio'] = ends.find(end => Math.abs(end-ratio)*length <= 1e-8) ?? ratio;
  } else if (key === 'height_m') row.height_m = value;
  else throw new Error('未知的女儿墙属性');
  return result;
}

export function parapetPanel(segments, outline, {open=false,uniformHeight=1,stale=false,pixelMode=false} = {}) {
  const custom = segments != null, rows = Array.isArray(segments) ? normalizeParapets(segments) : [], edges = facadeEdges(outline);
  const label = !custom ? `全周 · ${uniformHeight} m` : rows.length ? `${rows.length} 段` : '无女儿墙';
  const number = (index,key,title,value,max) => `<label class="field"><span>${title}</span><input type="number" required min="0" max="${max}" step="any" data-parapet-row="${index}" data-parapet-key="${key}" value="${esc(Number.isFinite(value) ? Number(value.toFixed(9)) : '')}"></label>`;
  return `<details class="card re-parapets" id="re-parapets" ${open ? 'open' : ''}><summary><span>女儿墙分段</span><small>${esc(label)}</small></summary>
    <div class="re-parapets-body"><p>沿外墙边设置起止距离与高度，空缺处不生成墙。分段会参与三维遮挡计算。</p>
    ${pixelMode ? '<p class="re-parapets-warning">先标定图纸比例，再编辑米制女儿墙尺寸。</p>' : ''}
    <fieldset ${pixelMode ? 'disabled' : ''}><div class="re-parapets-actions">
      <button type="button" class="btn sm" data-re-act="parapet-uniform" aria-pressed="${!custom}">全周统一</button>
      <button type="button" class="btn sm" data-re-act="parapet-custom" ${custom ? 'disabled' : ''}>分段编辑</button>
      <button type="button" class="btn sm" data-re-act="parapet-none">无女儿墙</button></div>
    ${stale ? '<p class="re-parapets-warning" role="alert">屋顶轮廓已变更，请按当前轮廓重新生成后校对每段；保存前必须处理。</p>' : ''}
    ${custom ? `<div class="re-parapets-actions"><button type="button" class="btn sm" data-re-act="parapet-add" ${stale ? 'disabled' : ''}>在空缺处添加</button><button type="button" class="btn sm" data-re-act="parapet-reset">按当前轮廓重新生成</button></div>
      <fieldset ${stale ? 'disabled' : ''}>${rows.map((row,index) => {
        const length=lengthOf(outline,row.edge_index);
        return `<div class="re-parapet-row"><div class="re-parapet-heading"><strong>第 ${index+1} 段</strong><button type="button" class="btn sm" data-re-act="parapet-delete-${index}" aria-label="删除第 ${index+1} 段女儿墙">删除</button></div>
          <label class="field"><span>外墙边</span><select data-parapet-row="${index}" data-parapet-key="edge_index">${edges.map(edge => `<option value="${edge.index}" ${edge.index===row.edge_index ? 'selected' : ''}>${esc(edge.label)}</option>`).join('')}</select></label>
          <div class="grid2">${number(index,'start_m','起点距边首（m）',row.start_ratio*length,length)}${number(index,'end_m','终点距边首（m）',row.end_ratio*length,length)}${number(index,'height_m','墙高（m）',row.height_m,3)}</div></div>`;
      }).join('') || '<p class="muted">当前没有女儿墙。点击“在空缺处添加”创建。</p>'}</fieldset>` : '<p class="muted">使用上方“女儿墙高度”作为全周高度。切换分段编辑后可单独留出缺口。</p>'}
    </fieldset><p class="muted">距离按二维平面投影计量，方向沿轮廓顶点顺序；墙底跟随实际屋面高程。高度为 0 时不生成墙。</p></div></details>`;
}

export function parapetPlanMarkup(segments, outline, unit) {
  if (!Array.isArray(segments) || !Number.isFinite(unit) || unit <= 0) return '';
  return `<g class="re-parapet-overlay" pointer-events="none">${normalizeParapets(segments).map((row,index) => {
    if (row.height_m <= 0 || !outline[row.edge_index]) return '';
    const a=outline[row.edge_index], b=outline[(row.edge_index+1)%outline.length];
    const point=t=>[a[0]+(b[0]-a[0])*t,-a[1]-(b[1]-a[1])*t], start=point(row.start_ratio),end=point(row.end_ratio);
    return `<line class="re-parapet-line" x1="${start[0]}" y1="${start[1]}" x2="${end[0]}" y2="${end[1]}" stroke-width="${3*unit}"><title>第 ${index+1} 段女儿墙 · ${esc(row.height_m)} m</title></line>`;
  }).join('')}</g>`;
}
