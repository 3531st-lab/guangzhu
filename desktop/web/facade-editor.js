import {esc} from './data.js';

// Presentation settings are stored with the roof, separately from photovoltaic geometry.
export const facadeDefaults = () => ({enabled:true, wall_material:'metal', wall_color:'#d6dde2',
  trim_color:'#49606c', base_color:'#64717a', door_color:'#3c5969', bay_width_m:6,
  base_height_m:.6, columns:true, window_rows:1, window_width_m:2.4, window_height_m:1.2,
  window_sill_m:3.8, front_edge:null, doors:2, door_width_m:4, door_height_m:4,
  canopy_depth_m:1.8, loading_docks:1, dock_height_m:1.1, personnel_door:true});

export const facadePresets = {
  silver:{label:'银灰厂房', wall_material:'metal', wall_color:'#d6dde2', trim_color:'#49606c', base_color:'#64717a', door_color:'#3c5969'},
  warm:{label:'暖白厂房', wall_material:'concrete', wall_color:'#e9e2d4', trim_color:'#786858', base_color:'#9a8e80', door_color:'#65776c'},
  brick:{label:'红砖厂房', wall_material:'brick', wall_color:'#ad7158', trim_color:'#4b5056', base_color:'#66666a', door_color:'#3d535d'},
  taizhou_pharma:{label:'医药城·洁净厂房', wall_material:'metal', wall_color:'#eef3f7', trim_color:'#1e6b7b', base_color:'#5c7684', door_color:'#255f73', window_rows:2, loading_docks:2, canopy_depth_m:2.4},
  taizhou_shipyard:{label:'靖江海工·重工车间', wall_material:'metal', wall_color:'#cbd6e0', trim_color:'#1f4e78', base_color:'#4a5a68', door_color:'#284b6a', window_rows:2, doors:3, door_width_m:6, door_height_m:5, bay_width_m:8},
  taizhou_watertown:{label:'凤城水乡·青砖黛瓦', wall_material:'brick', wall_color:'#6e767d', trim_color:'#2f353b', base_color:'#454c52', door_color:'#5c3a2e', window_rows:1, loading_docks:0, canopy_depth_m:1.5, bay_width_m:5},
  taizhou_agri:{label:'里下河·生态冷链仓', wall_material:'concrete', wall_color:'#e3e8df', trim_color:'#3b6e52', base_color:'#607365', door_color:'#2f5c44', window_rows:1, loading_docks:3, canopy_depth_m:2.8},
};

export function applyFacadePreset(current, key) {
  const {label, ...colors} = facadePresets[key];
  return {...facadeDefaults(), ...current, ...colors};
}

export function facadeEdges(outline) {
  const signed = outline.reduce((sum, p, i) => {const q=outline[(i+1)%outline.length]; return sum+p[0]*q[1]-q[0]*p[1];},0);
  return outline.map((p,i) => {
    const q=outline[(i+1)%outline.length], dx=q[0]-p[0], dy=q[1]-p[1], side=signed >= 0 ? 1 : -1;
    const bearing=(Math.atan2(side*dy,-side*dx)*180/Math.PI+360)%360;
    const direction=['北','东北','东','东南','南','西南','西','西北'][Math.round(bearing/45)%8];
    const length=Math.hypot(dx,dy);
    return {index:i, length, label:`朝${direction} · ${Number(length.toFixed(2))} m（边 ${i+1}）`};
  });
}

export function facadeFrontOptions(outline, selected) {
  const edges=facadeEdges(outline), longest=edges.reduce((best,edge)=>!best || edge.length>best.length ? edge : best,null);
  return `<option value="" ${selected == null ? 'selected' : ''}>自动 · ${longest ? esc(longest.label) : '最长外墙'}</option>` +
    edges.map(edge=>`<option value="${edge.index}" ${selected === edge.index ? 'selected' : ''}>${esc(edge.label)}</option>`).join('');
}

export function facadePanel(value, outline, open=false, message='') {
  const f={...facadeDefaults(), ...value};
  const check=(key,label)=>`<label class="toggle"><span>${label}</span><input type="checkbox" data-facade="${key}" ${f[key] ? 'checked' : ''}></label>`;
  const number=(key,label,min,max,step=.1)=>`<label class="field"><span>${label}</span><input type="number" data-facade="${key}" required min="${min}" max="${max}" step="${step}" value="${esc(f[key] ?? '')}"></label>`;
  const color=(key,label)=>`<label class="re-facade-color"><span>${label}</span><input type="color" data-facade="${key}" value="${esc(f[key])}"><code data-facade-color-text="${key}">${esc(f[key])}</code></label>`;
  return `<details class="card re-facade" id="re-facade" ${open ? 'open' : ''}><summary><span>厂房外观</span><small>墙面 · 门窗 · 雨棚 · 装卸口</small></summary>
    <div class="re-facade-body">${check('enabled','显示建筑细节')}
      <button type="button" class="btn sm" data-re-act="facade-front-view">查看主立面</button>
      <fieldset class="re-facade-settings" ${f.enabled ? '' : 'disabled'}>
        <div class="re-facade-presets">${Object.entries(facadePresets).map(([key,preset])=>`<button type="button" class="btn sm" data-re-act="facade-preset-${key}"><i style="background:${preset.wall_color};border-color:${preset.trim_color}"></i>${preset.label}</button>`).join('')}</div>
        <label class="field"><span>墙面材质</span><select data-facade="wall_material">${[['metal','金属压型板'],['concrete','混凝土'],['brick','砖墙']].map(([key,label])=>`<option value="${key}" ${f.wall_material===key ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <div class="re-facade-colors">${color('wall_color','墙面')}${color('trim_color','立柱／收边')}${color('base_color','勒脚')}${color('door_color','门体')}</div>
        <div class="grid2">${number('bay_width_m','柱距／窗带间距（m）',2,20)}${number('base_height_m','勒脚高度（m，0 为关闭）',0,2)}</div>${check('columns','显示立柱')}
        <h4>窗带</h4><label class="field"><span>窗带排数</span><select data-facade="window_rows">${[0,1,2].map(n=>`<option value="${n}" ${f.window_rows===n ? 'selected' : ''}>${n === 0 ? '关闭窗带' : n+' 排'}</option>`).join('')}</select></label>
        <div class="grid2">${number('window_width_m','单窗宽度（m）',.4,8)}${number('window_height_m','单窗高度（m）',.3,3)}${number('window_sill_m','首排窗台高度（m）',.5,12)}</div>
        <h4>入口与装卸</h4><label class="field"><span>主立面（朝向为外墙向外方向）</span><select data-facade="front_edge">${facadeFrontOptions(outline,f.front_edge)}</select></label>
        <p class="re-facade-warning" id="re-facade-warning" ${message ? '' : 'hidden'}>${esc(message)}</p>
        <div class="grid2">${number('doors','卷帘门数量',0,6,1)}${number('loading_docks','装卸口数量',0,4,1)}${number('door_width_m','门／装卸口宽度（m）',1,8)}${number('door_height_m','门／装卸口高度（m）',2,8)}${number('canopy_depth_m','雨棚出挑（m，0 为关闭）',0,4)}${number('dock_height_m','装卸台高度（m）',.3,1.6)}</div>
        ${check('personnel_door','设置人行门')}
        <p class="muted">细节随墙长与净高适配；空间不足时自动减少或略去。</p>
      </fieldset>
      <button type="button" class="btn sm" data-re-act="facade-reset">恢复默认外观</button>
      <p class="muted">建筑外观为示意，不参与光伏遮挡、结构、发电与造价校核。</p>
    </div></details>`;
}

export function facadePreviewText(stats) {
  if (!stats) return '';
  if (!stats.enabled) return '建筑细节已关闭。';
  return `已按墙长与净高适配：窗 ${stats.windows} 扇、卷帘门 ${stats.doors} 樘、人行门 ${stats.personnel_doors} 樘、装卸口 ${stats.loading_docks} 处、雨棚 ${stats.canopies} 处。`;
}
