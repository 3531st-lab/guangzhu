import {esc} from './data.js';

export const isSite = mode => ['ground', 'carport'].includes(mode);
export function defaults(roof = {}) {
  return {
    ground: {...{lower_edge_m:.5, road_every:4, road_width_m:4, fence_setback_m:2}, ...roof.ground},
    carport: {...{direction_deg:null, bay_rows:2, column_rows:1, clear_height_m:2.5, structure_depth_m:.3,
      structural_strip_m:.6, tilt_deg:5, facing:'south', bays:[], aisles:[], strips:[], columns:{}}, ...roof.carport},
  };
}
export function panel(state, modes, button) {
  const kind = state.roofMode, values = state[kind];
  const input = (key, label, unit, min, max) => `<label class="field">${label} (${unit})
    <input data-site="${kind}" data-site-key="${key}" type="number" step="any" min="${min}" max="${max}"
      value="${esc(values[key] ?? '')}" aria-label="${label}"></label>`;
  const choice = (key, label, choices) => `<label class="field">${label}<select data-site="${kind}" data-site-key="${key}">
    ${choices.map(([v, text]) => `<option value="${v}" ${values[key] === v ? 'selected' : ''}>${text}</option>`).join('')}</select></label>`;
  const select = `<label class="field">安装场地<select data-re="roofMode">${modes.map(([v, label]) =>
    `<option value="${v}" ${kind === v ? 'selected' : ''}>${label}</option>`).join('')}</select></label>`;
  if (kind === 'ground') return select + `<p>新建地面安装，地坪为0米。桩基须勘察与厂家设计。</p><div class="grid2">
    ${input('lower_edge_m','组件最低边离地','m',.3,3)}${input('road_every','每几架行留道路','行，0关闭',0,100)}
    ${input('road_width_m','道路净宽（示意）','m',.1,30)}${input('fence_setback_m','围栏退让（示意）','m',0,20)}</div>
    <p>新增方阵不得占用任何耕地；须核实土地权属、用途、林草和生态管控。独立空地通常按集中式管理，不能自动视作分布式。</p>`;
  const plane = (p, index) => `<fieldset><legend>车棚 P${p.id}</legend><div class="grid2">${[
    ['slope_deg','倾角0–15°'], ['slope_azimuth_deg','下坡朝向0–360°'], ['offset_m','最低棚面高度 m']
  ].map(([key, label]) => `<label class="field">${label}<input type="number" step="any" data-canopy="${index}"
      data-canopy-key="${key}" value="${p[key]}"></label>`).join('')}</div>
    <label class="field">棚面角点（x,y 米；每行一个点）<textarea data-canopy="${index}" data-canopy-key="outline"
      rows="4">${esc(p.outline.map(q => q.join(',')).join('\n'))}</textarea></label>
    ${button('删除此棚，保留车位', 'canopy-delete-' + p.id)}</fieldset>`;
  return select + `<p>新建停车棚。小型车倒车垂直停车净位2.4×5.1m，净车道5.5m；与墙距、正向停车不同。</p><div class="grid2">
    ${input('direction_deg','车位排方向（空值沿长边）','°',0,360)}
    ${choice('bay_rows','每棚车位排数',[[1,'单排'],[2,'双排背靠背']])}
    ${choice('column_rows','立柱行数',[[1,'单排柱'],[2,'双排柱']])}
    ${choice('facing','棚面朝向',[['south','朝南'],['row','沿车位排']])}
    ${input('clear_height_m','目标梁底净高（示意）','m',0,10)}${input('tilt_deg','棚面倾角','°',0,15)}
    ${input('structure_depth_m','竖向结构深度（示意）','m',.01,2)}${input('structural_strip_m','立柱预留带宽（示意）','m',.4,3)}</div>
    ${button('按当前设置重新生成车位和棚面', 'parking-build')}
    <p>生成会替换现有棚面；保存或删除不会自动重建。${values.bays.length}个净车位，${state.planes.length}个棚。
    实际净高=最低棚面减结构深度；2.2m为适用车库项目参照，开放棚适用性待设计确认。柱径0.2m与布点仅示意。</p>
    ${state.planes.map(plane).join('')}`;
}

export function drawing(state, point, width) {
  if (state.roofMode !== 'carport') return '';
  const polygon = (points, color, fill = 'none') => `<polygon points="${points.map(point).join(' ')}"
    fill="${fill}" fill-opacity=".18" stroke="${color}" stroke-width="${width}"/>`;
  return state.planes.map(p => polygon(p.outline, '#4479a5', '#4479a5')).join('') +
    state.carport.bays.map(p => polygon(p.polygon, '#729451')).join('') +
    state.carport.aisles.map(p => polygon(p.polygon, '#c98d40')).join('') +
    Object.entries(state.carport.columns).filter(([id]) => state.planes.some(p => p.id === Number(id)))
      .flatMap(([, points]) => points.map(p => `<circle cx="${p[0]}" cy="${-p[1]}" r=".1" fill="#764a35"/>`)).join('');
}
