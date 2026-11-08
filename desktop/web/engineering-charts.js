import {esc} from './data.js';

const finite = value => typeof value === 'number' && Number.isFinite(value);
const number = value => finite(value) ? value.toLocaleString('zh-CN',{maximumFractionDigits:2}) : '未计算';
const stale = result => result.evidence?.analysis?.status === 'stale';
const missing = message => `<p class="muted" data-energy-unavailable>${esc(message)}</p>`;

// These are separate diagnostics, not additive stages of an energy balance.
export function lossMetricsMarkup(result) {
  if (stale(result)) return missing('本版本输入已改变，损耗指标需要重新计算。');
  const shading = result.scene?.shading?.summary, electric = result.scene?.electrical;
  const rows = [
    ['年度平均遮挡损失',shading?.avg_loss_pct,'实际几何遮挡模型的年度汇总'],
    ['直流最大线路电压降',electric?.dc_drop_pct_max,'最不利直流线路的设计工况'],
    ['交流最大线路电压降',electric?.ac_drop_pct_max,'最不利交流线路的设计工况'],
  ];
  return `<div class="loss-metrics"><p class="muted">读取本版本的遮挡与电气计算。最大电压降不是全年线损，这些指标不能相加为总发电损失。</p>
    <table class="tbl"><thead><tr><th>指标</th><th>计算值</th><th>口径</th></tr></thead><tbody>${rows.map(([label,value,basis]) =>
      `<tr><td>${esc(label)}</td><td data-loss-metric="${esc(label)}">${number(value)}${finite(value)?'%':''}</td><td>${esc(basis)}</td></tr>`).join('')}</tbody></table>
    <p class="muted">未单独计算温升、积尘、失配和转换损失的逐项能量平衡；未计算 PR，不以固定百分比代替。</p></div>`;
}

export function monthlyEnergy(result) {
  if (stale(result)) return {reason:'本版本输入已改变，逐月发电需要重新计算。'};
  const actual = result.economics?.self_use?.monthly;
  const fallback = result.economics?.analysis_metadata?.yield_kwh?.monthly_kwh;
  const detailed = Array.isArray(actual), source = detailed ? actual : fallback;
  if (!Array.isArray(source)) return {reason:'本版本未保存逐月计算结果，请重新计算；不会按固定比例分配全年发电。'};
  const rows = source.map(row => ({month:row.month,generation_kwh:detailed?row.generation_kwh:row.ac_kwh,
    ...detailed ? {self_use_kwh:row.self_use_kwh,export_kwh:row.export_kwh,curtailed_kwh:row.curtailed_kwh} : {}}));
  const keys = detailed ? ['generation_kwh','self_use_kwh','export_kwh','curtailed_kwh'] : ['generation_kwh'];
  if (rows.length !== 12 || new Set(rows.map(row=>row.month)).size !== 12 || rows.some(row =>
      !Number.isInteger(row.month) || row.month < 1 || row.month > 12 || keys.some(key=>!finite(row[key]) || row[key]<0)))
    return {reason:'逐月计算记录不完整或含无效值，请重新计算。'};
  if (detailed && rows.some(row => Math.abs(row.generation_kwh-row.self_use_kwh-row.export_kwh-row.curtailed_kwh) > Math.max(.001,row.generation_kwh*1e-6)))
    return {reason:'逐月发电与自用、上网、弃电合计不一致，请重新计算。'};
  const summary = result.metrics ?? result.summary ?? {}, annual = (summary.yield_kwh ?? summary.yield ?? {}).p50;
  const total = rows.reduce((sum,row)=>sum+row.generation_kwh,0);
  if (finite(annual) && Math.abs(annual-total)>Math.max(.001,Math.abs(annual)*1e-6))
    return {reason:'逐月汇总与本版本年发电不一致，请重新计算。'};
  return {rows:rows.sort((a,b)=>a.month-b.month),detailed,total,
    algorithm:result.economics?.self_use?.algorithm ?? '未记录用电口径'};
}

export function monthlyYieldMarkup(result) {
  const data = monthlyEnergy(result);
  if (data.reason) return missing(data.reason);
  const {rows,detailed} = data, maximum = Math.max(...rows.map(row=>row.generation_kwh),1);
  const bands = detailed ? [['self_use_kwh','自用','#159573'],['export_kwh','上网','#397fd0'],['curtailed_kwh','弃电','#bd8241']] :
    [['generation_kwh','发电','#397fd0']];
  return `<div class="monthly-box"><p class="muted">按本版本逐时结果汇总（北京时间），全年合计 ${number(data.total)} kWh。
    ${detailed ? `用电口径：${esc(data.algorithm)}。` : '未计算逐月自用、上网与弃电分配。'}</p>
    <p class="muted">${bands.map(([,label,color])=>`<span style="color:${color}">■ ${label}</span>`).join('　')} · 单位：kWh</p>
    <svg viewBox="0 0 520 165" class="monthly-svg" role="img" aria-label="本版本逐月发电计算结果">
    ${rows.map((row,i)=>{const x=18+i*41;let top=128;return `<g>${bands.map(([key,label,color])=>{
      const height=row[key]/maximum*105;top-=height;
      return `<rect x="${x}" y="${top}" width="24" height="${height}" fill="${color}"><title>${row.month}月${label} ${number(row[key])} kWh</title></rect>`;
    }).join('')}<text x="${x+12}" y="${top-4}" font-size="9" text-anchor="middle" fill="currentColor">${number(row.generation_kwh/1000)}千</text>
      <text x="${x+12}" y="146" font-size="10" text-anchor="middle" fill="currentColor">${row.month}月</text></g>`;}).join('')}</svg>
    <details><summary>查看逐月数值与合计</summary><table class="tbl"><thead><tr><th>月份</th><th>发电 kWh</th>${detailed?'<th>自用 kWh</th><th>上网 kWh</th><th>弃电 kWh</th>':''}</tr></thead>
    <tbody>${rows.map(row=>`<tr><td>${row.month}</td><td>${number(row.generation_kwh)}</td>${detailed?['self_use_kwh','export_kwh','curtailed_kwh'].map(key=>`<td>${number(row[key])}</td>`).join(''):''}</tr>`).join('')}</tbody></table></details></div>`;
}
