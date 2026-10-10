import {esc} from './data.js';

const num = value => Number.isFinite(value) ? value.toLocaleString('zh-CN', {maximumFractionDigits:2}) : '未提供';
export function electricalFor(result) {
  const electrical = result.scene?.electrical;
  return electrical?.version === result.version ? electrical : null;
}
export function wiringDetails(result, id = '') {
  const e = electricalFor(result), cable = e?.cables;
  if (!cable) return '此版本缺少线路数据；可继续查看方案书和设计指标。';
  const row = cable.dc?.find(r => r.id === id), string = e.strings?.find(s => s.id === id);
  if (row && string) return `${esc(id)} · ${string.module_ids.length}块 · I${esc(string.inverter)} / MPPT ${esc(string.mppt)} · ` +
    `${num(row.length_m)}m（含富余） · ${num(row.voltage_v)}V · 压降${num(row.drop_pct)}%` +
    (row.routing_status === 'blocked' ? ' · 线路不可达，调整设备位置' : '');
  const routing = cable.routing;
  if (!routing) return '历史简化线路：未核验绕障碍；颜色对应组串，青绿线为交流。';
  const saving = routing.saved_dc_m == null ? '存在不可达路径，不能比较节线量' : routing.saved_dc_m > .01 ?
    `比原顺序节省直流${num(routing.saved_dc_m)}m` : '本次未找到更短路线';
  return `${e.strings?.length ?? 0}串 · 线路合计${num(cable.total_length_m)}m · ${saving}` +
    (routing.blocked_routes ? ` · ${routing.blocked_routes}条不可达` : ' · 候选较短方案，施工前核实');
}
export function wiringPanel(result, id = '', mode = 'light') {
  const e = electricalFor(result), strings = e?.strings ?? [];
  const active = strings.some(s => s.id === id) ? id : '';
  return `<div class="wiring-tools" id="wiring-tools" ${mode === 'wiring' ? '' : 'hidden'}>
    <div class="wire-controls"><label>查看组串<select id="wire-string" ${strings.length ? '' : 'disabled'}>
    <option value="">全部线路</option>${strings.map(s => `<option value="${esc(s.id)}" ${s.id === active ? 'selected' : ''}>
    ${esc(s.id)} · I${esc(s.inverter)} / MPPT ${esc(s.mppt)}</option>`).join('')}</select></label>
    <label><input id="wire-ac" type="checkbox" checked>交流线路</label>
    <button class="btn sm" id="wire-focus" data-action="scene-focus" ${active ? '' : 'disabled'}>聚焦本串</button>
    <button class="btn sm" data-action="scene-top">全景俯视</button><button class="btn sm" data-action="scene-reset">复位</button></div>
    <p id="wire-details" aria-live="polite">${wiringDetails(result, active)}</p>
    <small>点组件选中整串；序号和箭头是连接顺序，不是电流；线路抬高只为看清。</small></div>`;
}
