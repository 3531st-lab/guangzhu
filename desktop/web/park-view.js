import { esc, cleanRoofLabel, valueMarkup, splitter } from './data.js';
import { mountParkScene3D } from './park-scene-3d.js';

const terminal = item => ['completed', 'failed', 'skipped'].includes(item.status);
const labels = {
  pending: '等待', creating: '准备会话', sending: '已派发，待确认', running: '运行中', approval: '等待原生批准',
  cancelling: '等待取消确认；尚未开始的空闲不能证明派发已结束', reconcile: '需核对原会话', completed: '已结束', failed: '失败', skipped: '已跳过'
};
export function queueMarkup(queue) {
  if (!queue?.items.length) return '';
  return `<div id="park-queue-display" data-key="parkqueue" class="card"><h3>厂房队列${queue.paused ? ' · 已暂停后续派发' : ''}</h3>
    <p>每栋导出请在右侧点击「仅允许这次」。</p><button class="btn sm" data-action="park-queue-show">回到运行园区</button>
    <button class="btn sm" data-action="park-pause">暂停后续</button><button class="btn sm" data-action="park-resume">继续 / 恢复</button>
    <button class="btn sm" data-action="park-skip">跳过当前栋</button>${queue.items.some(item => !['completed', 'failed', 'skipped'].includes(item.status)) ?
      '<button class="btn sm" data-action="park-abandon">放弃这个队列</button>' : ''}<ol>${queue.items.map(item => `<li>${esc(item.spec.template)} · ${item.stage === 'review' ? '独立审核' : '设计'} · ${labels[item.status]}
    ${esc(item.reason)}</li>`).join('')}</ol></div>`;
}
const PARK_PRESETS = {
  standard: {
    label: '标准工商业园区配置',
    module_id: 'trina-tsm-605neg19rc20',
    inverter_brand: 'Huawei',
    layout_algo: 'auto_pareto',
    prefer: 'balanced',
    dc_cable_family: 'PV1-F',
    ac_cable_family: 'ZR-YJV22',
    payback_years_max: '',
    price_self_cny_kwh: '0.82',
    monthly_kwh_wan: '12',
    shifts: 'two',
    transformer_kva: 1600,
    grid_kw: 1200,
    budget_cny: 3200000,
  },
  max_cap: {
    label: '高收益满铺配置',
    module_id: 'tongwei-twmnd-72hs620',
    inverter_brand: 'Sungrow',
    layout_algo: 'ew_dense',
    prefer: 'max_capacity',
    dc_cable_family: 'PV1-F',
    ac_cable_family: 'ZR-YJV22',
    payback_years_max: '',
    price_self_cny_kwh: '0.85',
    monthly_kwh_wan: '18',
    shifts: 'continuous',
    transformer_kva: 2500,
    grid_kw: 2000,
    budget_cny: 5000000,
  },
  fast_payback: {
    label: '快回本稳健配置',
    module_id: 'longi-lr5-72htd-580m',
    inverter_brand: 'Ginlong',
    layout_algo: 'winter_solstice',
    prefer: 'fast_payback',
    dc_cable_family: 'PV1-F',
    ac_cable_family: 'ZR-YJV22',
    payback_years_max: '4.5',
    price_self_cny_kwh: '0.88',
    monthly_kwh_wan: '15',
    shifts: 'continuous',
    transformer_kva: 1250,
    grid_kw: 1000,
    budget_cny: 2600000,
  },
  lightweight: {
    label: '轻质低荷载配置',
    module_id: 'suntech-stp440s-c54-nshb',
    inverter_brand: 'GoodWe',
    layout_algo: 'edge_orthogonal',
    prefer: 'balanced',
    dc_cable_family: 'PV1-F',
    ac_cable_family: 'ZR-YJV',
    payback_years_max: '',
    price_self_cny_kwh: '0.80',
    monthly_kwh_wan: '10',
    shifts: 'two',
    transformer_kva: 1250,
    grid_kw: 1000,
    budget_cny: 2400000,
  },
};

export class ParkView {
  constructor(api, queue, configure, buildSpec, notice) {
    Object.assign(this, {
      api, queue, configure, buildSpec, notice, id: null, parks: [], selected: new Set(),
      scene3d: null,
      colorByPhase: true,
      parkSunDate: '2026-12-21',
      parkSunHour: 10.0,
      batch: {
        preset_key: 'standard',
        module_id: 'trina-tsm-605neg19rc20',
        inverter_brand: 'Huawei',
        layout_algo: 'auto_pareto',
        prefer: 'balanced',
        dc_cable_family: 'PV1-F',
        ac_cable_family: 'ZR-YJV22',
        payback_years_max: '',
        price_self_cny_kwh: '0.82',
        monthly_kwh_wan: '12',
        shifts: 'two',
        compare: true,
      },
    });
  }
  async load() {
    this.parks = await this.api('parks');
    const active = this.parks.find(p => p.queue_active);
    if (!this.queue.id && active) await this.queue.load(active.id);
    if (!this.parks.some(p => p.id === this.id)) this.id = this.parks[0]?.id;
    this.current = this.id ? await this.api('parks/' + this.id) : null;
    if (this.id && (!this.queue.item || this.id === this.queue.id)) await this.queue.load(this.id);
  }
  html() {
    const options = this.parks.map(p => `<option value="${esc(p.id)}" ${p.id === this.id ? 'selected' : ''}>${esc(cleanRoofLabel(p.name))}</option>`).join('');
    const button = (action, text, cls = '') => `<button class="btn sm ${cls}" data-paction="${action}">${text}</button>`;
    const side = `<aside class="card"><h2>园区</h2><select data-pselect><option value="">选择园区</option>${options}</select>
      ${button('new', '新建园区')}${button('taizhou-demo', '载入泰州中国医药城产业园')}${button('demo', '载入武进工业园区')}<a class="btn sm" href="#park-legacy">已有设计汇总</a></aside>`;
    if (!this.current) return `<div class="park-editor">${side}${splitter('park')}<p>新建园区，加入我的屋顶或演示屋顶。</p></div>`;
    const { park, data, svg } = this.current;
    const field = (key, label, unit) => `<label class="park-field-inline"><span>${label}</span><input data-pfield="${key}" value="${esc(cleanRoofLabel(park[key] ?? ''))}"/>${unit ? `<small>${unit}</small>` : ''}</label>`;
    const sources = this.roofs.filter(r => !r.project?.park && !park.buildings.some(b => b.template === r.id));
    const roofTypeLabel = { flat: '混凝土平屋顶', metal: '彩钢瓦屋面', pitched: '多坡屋面', ground: '地面阵列', carport: '光伏车棚' };
    const phaseBadge = phase => phase === 1
      ? '<span class="park-phase-pill phase-1">1 · 一期优先</span>'
      : phase === 2
        ? '<span class="park-phase-pill phase-2">2 · 二期扩建</span>'
        : '<span class="park-phase-pill phase-none">— 待设计</span>';
    const rows = data.buildings.map(b => `<tr class="park-bldg-row"><td><label class="park-bldg-check"><input type="checkbox" data-pick="${esc(b.template)}" checked><span><b>${esc(cleanRoofLabel(b.name))}</b><small>${esc(roofTypeLabel[b.roof?.type] || b.roof?.type || '屋顶')}</small></span></label></td>
      <td>${b.roof.height_m} m</td><td>${valueMarkup(b.result?.dc_kw, 'kW')}</td><td>${valueMarkup(b.result?.capex_cny, '元')}</td>
      <td>${valueMarkup(b.result?.payback_years, '年')}</td><td>${phaseBadge(b.result?.park_phase)}</td>
      <td><input type="number" data-rotate="${esc(b.template)}" value="${b.rotation_deg}" min="-360" max="360" aria-label="旋转角度" style="width:68px"></td>
      <td class="park-row-actions">${b.result?.project_id ? `<a class="btn sm primary" href="#result/${esc(b.result.project_id)}${b.result.version ? `?version=${encodeURIComponent(b.result.version)}` : ''}">查看单栋3D</a> ` : ''}<button class="btn sm" data-config="${esc(b.template)}">条件与开工问答</button><button class="btn sm" data-remove="${esc(b.template)}">移出</button></td></tr>
      <tr class="park-bldg-meta"><td colspan="8">${esc(b.result?.status_label ?? '尚无可核验结果')} · ${esc(b.result?.shading_note ?? '尚无核验设计')} · ${esc(b.result?.run_id ?? '')}
      ${b.result?.ac_missing ?? ''}</td></tr>`).join('');
    const totals = [['装机', data.all.dc_kw, 'kW'], ['年发电', data.all.annual_kwh, 'kWh'], ['造价', data.all.capex_cny, '元'],
    ['整体回本', data.all.payback_years, '年'], ['年减碳', data.all.co2_t, 't'], ['逆变器', data.inverter_count, '台'],
    ['实际额定 AC', data.rated_ac_kw, 'kW']].map(([label, value, unit]) => `<span>${label} ${valueMarkup(value, unit)} ${unit}</span>`).join(' · ');
    const risks = data.risks.map(r => `${cleanRoofLabel(r.label)}：${r.limit == null ? '未填' : r.excess == null ? '无法核定' :
      r.excess > 1e-9 ? `有风险，超 ${r.excess.toFixed(3)} kW` : '未超出'}`).join('；');
    const riskPills = data.risks.map(r => {
      const state = r.limit == null ? 'neutral' : r.excess == null ? 'neutral' : r.excess > 1e-9 ? 'warn' : 'ok';
      const text = r.limit == null ? '上限未填' : r.excess == null ? '待核定' : r.excess > 1e-9 ? `超限 ${r.excess.toFixed(1)} kW` : `合规 (≤${r.limit}kW)`;
      return `<span class="park-risk-pill ${state}">${esc(cleanRoofLabel(r.label))}：${esc(text)}</span>`;
    }).join('');
    const kpiStrip = `<div class="park-kpi-grid">
      <div class="park-kpi-card"><span>全园直流总装机</span><strong>${valueMarkup(data.all.dc_kw, 'kW')} <small>kW</small></strong><small>一期优先 ${valueMarkup(data.phase1.dc_kw, 'kW')} kW · 已设计 ${data.all.count}/${data.buildings.length} 栋</small></div>
      <div class="park-kpi-card"><span>首年总发电估算</span><strong>${valueMarkup(data.all.annual_kwh, 'kWh')} <small>kWh</small></strong><small>一期年发电 ${valueMarkup(data.phase1.annual_kwh, 'kWh')} kWh</small></div>
      <div class="park-kpi-card"><span>工程总投资估算</span><strong>${valueMarkup(data.all.capex_cny, '元')} <small>元</small></strong><small>一期造价 ${valueMarkup(data.phase1.capex_cny, '元')} 元</small></div>
      <div class="park-kpi-card"><span>整体静态回收期</span><strong>${valueMarkup(data.all.payback_years, '年')} <small>年</small></strong><small>一期回本 ${valueMarkup(data.phase1.payback_years, '年')} 年 · 现金流叠加插值</small></div>
      <div class="park-kpi-card"><span>碳减排与逆变配置</span><strong>${valueMarkup(data.all.co2_t, 't')} <small>tCO₂/年</small></strong><small>逆变器 ${valueMarkup(data.inverter_count, '台')} 台 · 额定AC ${valueMarkup(data.rated_ac_kw, 'kW')} kW</small></div>
      <div class="park-kpi-card"><span>专变与并网容量校核</span><div class="park-risk-stack">${riskPills}</div><small>变压器×0.8 为工程经验参考上限</small></div>
    </div>`;
    const cost = this.current.cost;
    const estimate = cost ? `每栋约 ${cost.per_building.toFixed(4)} ${cost.currency}，按最近 ${cost.samples} 次完整 AGH 费用记录估算；非账单。` :
      '暂无可靠模型费估计；缺额、没有记录或币种混合时不填0，不换算人民币。';
    const b = this.batch;
    const presetBtn = (key, icon, text) => `<button class="btn sm ${b.preset_key === key ? 'primary' : ''}" data-paction="preset-${key}">${icon} ${text}</button>`;
    const batchPanel = `<div class="card" style="margin-bottom:10px" id="park-oneclick-panel">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px">
        <div>
          <h3 style="margin:0">⚡ 园区一键设置与批量工程配置中心</h3>
          <small style="color:var(--muted)">一键预设园区专变/并网/预算约束、统一组件与逆变器选型、负荷电价及全园邻楼 3D 遮挡坐标</small>
        </div>
        <div class="re-row" style="margin:0;gap:6px;flex-wrap:wrap">
          ${presetBtn('standard', '⚡', '一键标准工商业配置')}
          ${presetBtn('max_cap', '💰', '一键高收益满铺配置')}
          ${presetBtn('fast_payback', '⏱️', '一键快回本稳健配置')}
          ${presetBtn('lightweight', '🪶', '一键轻质低荷载配置')}
          ${button('toggle-pick-all', '☑️ 全选/反选厂房')}
        </div>
      </div>
      <div class="re-row" style="margin:6px 0 8px;gap:8px;flex-wrap:wrap;align-items:center">
        ${button('apply-oneclick-setup', '✅ 一键应用设置并同步园区3D坐标', 'primary')}
        ${button('oneclick-setup-and-run', '🚀 一键设置并立即全园排板计算', 'primary')}
        ${button('reset-designs', '🧹 清空园区已有排板')}
        <span style="font-size:12px;color:var(--muted)">自动补齐专变/并网/预算约束并同步邻楼 3D 遮挡。</span>
      </div>
      <details class="satmap-acc-card" style="margin-top:4px">
        <summary>
          <span>展开批量设备、电价与电缆细项设置 (8项)</span>
          <small>按需微调</small>
        </summary>
        <div class="satmap-acc-body">
          <div class="grid4" style="gap:8px">
        <label class="field"><span>统一光伏组件选型</span><select data-pbatch="module_id">
          ${[
        ['trina-tsm-605neg19rc20', '天合光能 Vertex N 605W (N型双玻)'],
        ['longi-lr5-72htd-580m', '隆基绿能 Hi-MO 7 580W (HPDC双玻)'],
        ['jinko-jkm585n-72hl4-bdv', '晶科能源 Tiger Neo 585W (N型TOPCon)'],
        ['tongwei-twmnd-72hs620', '通威太阳能 TWMND-72HS 620W'],
        ['astronergy-chsm72n-dg-590', '正泰新能 ASTRO N5 590W'],
        ['canadian-cs6w-555ms', '阿特斯 HiKu6 555W'],
        ['suntech-stp440s-c54-nshb', '尚德电力 440W (低荷载轻质屋顶专用)'],
      ].map(([k, t]) => `<option value="${k}" ${b.module_id === k ? 'selected' : ''}>${t}</option>`).join('')}
        </select></label>
        <label class="field"><span>统一逆变器品牌</span><select data-pbatch="inverter_brand">
          ${[
        ['', '自动匹配最优容配比'],
        ['Huawei', '华为数字能源 (SUN2000)'],
        ['Sungrow', '阳光电源 (SG系列)'],
        ['Ginlong', '锦浪科技 (GCI系列)'],
        ['GoodWe', '固德威 (GW系列)'],
        ['Sineng', '上能电气 (SN系列)'],
        ['Chint', '正泰电源 (CPS系列)'],
      ].map(([k, t]) => `<option value="${k}" ${b.inverter_brand === k ? 'selected' : ''}>${t}</option>`).join('')}
        </select></label>
        <label class="field"><span>三维批量排版算法</span><select data-pbatch="layout_algo">
          ${[
        ['auto_pareto', '多目标帕累托自动寻优 (推荐)'],
        ['winter_solstice', '冬至 9:00-15:00 真太阳时零遮挡排距'],
        ['edge_orthogonal', '顺屋脊正交高密网格排布'],
        ['ew_dense', '10° 东西向人字形高密度排布'],
      ].map(([k, t]) => `<option value="${k}" ${b.layout_algo === k ? 'selected' : ''}>${t}</option>`).join('')}
        </select></label>
        <label class="field"><span>三方案决策偏好 &amp; 目标回本</span><span style="display:flex;gap:4px">
          <select data-pbatch="prefer" style="flex:1">
            <option value="balanced" ${b.prefer === 'balanced' ? 'selected' : ''}>折中优选</option>
            <option value="max_capacity" ${b.prefer === 'max_capacity' ? 'selected' : ''}>最大装机</option>
            <option value="fast_payback" ${b.prefer === 'fast_payback' ? 'selected' : ''}>最快回本</option>
          </select>
          <input type="number" data-pbatch="payback_years_max" placeholder="回本上限(年)" min="1" max="20" step="0.5" value="${esc(b.payback_years_max)}" style="width:95px">
        </span></label>
        <label class="field"><span>统一加权自用电价 (元/度)</span><input type="number" data-pbatch="price_self_cny_kwh" min="0.1" max="3.0" step="0.01" value="${esc(b.price_self_cny_kwh)}" placeholder="0.82"></label>
        <label class="field"><span>单栋月均用电量 (万度/月)</span><input type="number" data-pbatch="monthly_kwh_wan" min="0.5" max="500" step="0.5" value="${esc(b.monthly_kwh_wan)}" placeholder="12"></label>
        <label class="field"><span>统一厂房生产班次</span><select data-pbatch="shifts">
          <option value="day" ${b.shifts === 'day' ? 'selected' : ''}>白班单班 (8:00-17:30)</option>
          <option value="two" ${b.shifts === 'two' ? 'selected' : ''}>两班制生产 (含周末轮休)</option>
          <option value="continuous" ${b.shifts === 'continuous' ? 'selected' : ''}>三班24h连续生产</option>
        </select></label>
        <label class="field"><span>统一交直流电缆选型</span><span style="display:flex;gap:4px">
          <select data-pbatch="dc_cable_family" style="flex:1">
            <option value="PV1-F" ${b.dc_cable_family === 'PV1-F' ? 'selected' : ''}>直流 PV1-F</option>
            <option value="H1Z2Z2-K" ${b.dc_cable_family === 'H1Z2Z2-K' ? 'selected' : ''}>直流 H1Z2Z2-K</option>
          </select>
          <select data-pbatch="ac_cable_family" style="flex:1">
            <option value="ZR-YJV22" ${b.ac_cable_family === 'ZR-YJV22' ? 'selected' : ''}>交流 ZR-YJV22</option>
            <option value="ZR-YJV" ${b.ac_cable_family === 'ZR-YJV' ? 'selected' : ''}>交流 ZR-YJV</option>
            <option value="YJLH22" ${b.ac_cable_family === 'YJLH22' ? 'selected' : ''}>铝合金 YJLH22</option>
          </select>
        </span></label>
          </div>
        </div>
      </details>
    </div>`;

    return `<div class="park-editor">${side}${splitter('park')}<main>
      ${kpiStrip}
      <div class="card"><div class="park-toolbar-row">${field('name', '名称', '')}
      ${field('transformer_kva', '变压器', 'kVA')}${field('grid_kw', '并网限制', 'kW')}${field('budget_cny', '预算', '元')}
      ${button('save', '保存', 'primary')}${button('place', '按原始坐标摆放')}${button('sync-neighbors', '🏢 一键同步邻楼3D遮挡')}${button('delete', '删除园区')}
      <span class="park-add-group"><select data-source>${sources.map(r => `<option value="${esc(r.id)}">${esc(cleanRoofLabel(r.name))}</option>`).join('')}</select>${button('add', '加入厂房')}</span></div>
      <p style="margin:6px 0 8px;color:var(--ink-2);font-size:13px">拖动下方左侧 2D 平面图楼栋可调整园区相对位置，右侧 3D 园区全景沙盘实时联动显示真实三维园区建筑、障碍物与设计后的全园区光伏阵列（点击 3D 楼栋可直达单栋精细工作台）。</p>
      <div class="grid2" style="gap:12px;align-items:stretch">
        <div class="park-pane-box">
          <div class="park-pane-head"><h4 style="margin:0">📐 园区 2D 总平面布置与拖拽定位图</h4><small>鼠标拖拽屋面可移动坐标</small></div>
          <div class="park-map-wrap">${svg}</div>
        </div>
        <div class="park-pane-box">
          <div class="park-pane-head">
            <h4 style="margin:0">🌐 真实园区 3D 全景数字孪生沙盘</h4>
            <div class="re-row" style="margin:0;flex-wrap:wrap;gap:4px">
              ${button('3d-iso', '🏛 鸟瞰')}
              ${button('3d-top', '⬇ 顶视')}
              ${button('3d-south', '☀ 南向')}
              ${button('3d-color', this.colorByPhase ? '🎨 分期着色' : '🎨 实景深蓝')}
              ${button('3d-sun-play', '▶ 日照动画')}
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:8px;padding:4px 8px;font-size:11.5px;background:var(--well,#f8fafc);border-radius:6px;margin-bottom:6px">
            <select data-psun-date style="padding:2px 6px;border-radius:4px;font-size:11.5px">
              <option value="2026-12-21" ${this.parkSunDate === '2026-12-21' ? 'selected' : ''}>冬至日 (12-21)</option>
              <option value="2026-03-21" ${this.parkSunDate === '2026-03-21' ? 'selected' : ''}>春分日 (03-21)</option>
              <option value="2026-06-21" ${this.parkSunDate === '2026-06-21' ? 'selected' : ''}>夏至日 (06-21)</option>
            </select>
            <span>时刻</span>
            <input type="range" min="6.5" max="17.8" step="0.1" value="${this.parkSunHour}" data-psun-hour style="flex:1">
            <b id="park-sun-hour-label" style="font-family:monospace;min-width:42px">${String(Math.floor(this.parkSunHour)).padStart(2, '0')}:${String(Math.round((this.parkSunHour % 1) * 60)).padStart(2, '0')}</b>
          </div>
          <div id="park-scene-3d" style="width:100%;height:340px;border-radius:10px;overflow:hidden;border:1px solid var(--line,#cbd5e1)"></div>
        </div>
      </div></div>
      ${batchPanel}
      <div class="card"><p>${totals}</p>${['posttax', 'equity'].map(key => data.all[key] ?
      `<p>${key === 'posttax' ? '税后整体' : '贷款权益税后'}回本 ${valueMarkup(data.all[key].payback_years, '年')} 年；
        收益率 ${valueMarkup(data.all[key].irr_pct, '%')} %</p>` :
      data.all[key + '_note'] ? `<p>${esc(data.all[key + '_note'])}</p>` : '').join('')}<p>${risks}</p><p>额定 AC 由归档电气文件每台直流容量和未舍入容配比还原。</p>
      <p>园区按整栋回本顺序分期，沿 T22 预算和兼容 AC 阈值；屋顶内分期不重复相加。绿色/蓝色一期，橙色/棕色二期。</p>
      <table class="tbl park-bldg-table"><thead><tr><th>厂房</th><th>高度</th><th>装机</th><th>造价</th><th>回本</th><th>期次</th><th>转角°</th><th>设置</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <div class="park-actions-bar">
        ${button('auto-run', '⚡ 批量运行本机规则设计（含邻楼3D遮挡与三方案）', 'primary')}
        ${button('approve-exports', '✅ 确认并批准勾选厂房导出')}
        ${button('report', '📄 生成园区方案书')}
        ${button('open-report', '📖 打开园区方案书')}
        <button class="btn sm" data-config="shared">共享条件与运行设置</button>
        ${button('start', '一键设计勾选厂房')}
        ${button('pause', '暂停后续')}
        ${button('resume', '继续 / 恢复')}
        ${button('skip', '跳过当前栋')}
      </div>
      <p style="margin-top:6px;font-size:12.5px;color:var(--muted)">共 ${park.buildings.length} 栋，可勾选子集。${esc(estimate)}</p>
      </div>${queueMarkup(this.id === this.queue.id ? this.queue.queue : this.current.queue)}</main></div>`;
  }
  async applyOneClickSetup(host, { quiet = false, forceConstraints = false } = {}) {
    if (!this.current?.park) return [];
    const park = this.current.park;
    const preset = PARK_PRESETS[this.batch.preset_key] || PARK_PRESETS.standard;
    if (forceConstraints || !park.transformer_kva) park.transformer_kva = preset.transformer_kva;
    if (forceConstraints || !park.grid_kw) park.grid_kw = preset.grid_kw;
    if (forceConstraints || !park.budget_cny) park.budget_cny = preset.budget_cny;

    const hadBuildingsInitially = park.buildings.length > 0;
    if (!park.buildings.length && Array.isArray(this.roofs) && this.roofs.length) {
      const defaults = ['taizhou-cmc-pharma', 'taizhou-shipbuilding-workshop', 'taizhou-watertown-pavilion', 'taizhou-lixiahe-coldchain']
        .filter(id => this.roofs.some(r => r.id === id));
      const picks = defaults.length ? defaults : this.roofs.filter(r => !r.project?.park).slice(0, 4).map(r => r.id);
      for (const template of picks) {
        park.buildings.push({ template, x_m: 0, y_m: 0, rotation_deg: 0 });
      }
    }

    const allPickBoxes = [...host.querySelectorAll('[data-pick]')];
    let keys = [...host.querySelectorAll('[data-pick]:checked')].map(el => el.dataset.pick);
    if (!keys.length) {
      if (hadBuildingsInitially && allPickBoxes.length > 0) {
        if (!quiet) {
          this.notice('请至少勾选一栋厂房后再应用配置或运行批量设计');
        }
        return [];
      }
      keys = park.buildings.map(b => b.template);
    }

    const originCount = park.buildings.filter(b => Math.abs(b.x_m || 0) < 1e-3 && Math.abs(b.y_m || 0) < 1e-3).length;
    if (park.buildings.length > 1 && originCount > 1) {
      const placed = await this.api(`parks/${this.id}/place`, park);
      park.buildings = placed.buildings || park.buildings;
      if (placed.origin) park.origin = placed.origin;
    }

    const shiftCode = { day: '1', two: '2', continuous: '3', '1': '1', '2': '2', '3': '3' }[this.batch.shifts] || '2';
    const sharedForm = {
      ...(park.settings?.shared ?? {}),
      presetKey: this.batch.preset_key || 'standard',
      moduleId: this.batch.module_id || 'trina-tsm-605neg19rc20',
      inverterBrand: this.batch.inverter_brand || '',
      layoutAlgo: this.batch.layout_algo || 'auto_pareto',
      prefer: this.batch.prefer || 'balanced',
      payback: this.batch.payback_years_max || '',
      priceSelf: this.batch.price_self_cny_kwh || '0.82',
      fKwh: this.batch.monthly_kwh_wan || '12',
      fShifts: shiftCode,
      dcCableFamily: this.batch.dc_cable_family || 'PV1-F',
      acCableFamily: this.batch.ac_cable_family || 'ZR-YJV22',
      compare: true,
      fRoof: this.batch.preset_key === 'lightweight' ? 'metal' : 'concrete',
      fAge: '5',
      fCore: 'rockwool',
      fSky: '1',
      fOwned: '1',
      fExport: '1',
    };
    park.settings = park.settings || {};
    park.settings.shared = sharedForm;
    for (const tpl of keys) {
      const roofKind = this.roofs?.find(r => r.id === tpl)?.geometry?.type;
      park.settings[tpl] = {
        ...(park.settings[tpl] ?? {}),
        ...sharedForm,
        fRoof: roofKind === 'metal' ? 'metal' : roofKind === 'flat' ? 'concrete' : roofKind ? 'other' : sharedForm.fRoof,
      };
    }
    await this.api(`parks/${this.id}/save`, park);
    if (!quiet) {
      this.notice(`⚡ 已一键应用【${preset.label}】到 ${keys.length} 栋厂房（专变 ${park.transformer_kva}kVA / 并网 ${park.grid_kw}kW / 预算 ${(park.budget_cny / 10000).toFixed(0)}万），并完成全园 3D 邻楼遮挡同步！`);
    }
    return keys;
  }
  async save() {
    try { await this.api(`parks/${this.id}/save`, this.current.park); }
    finally { await this.refresh(); }
  }
  async refresh() {
    this.scene3d?.dispose();
    this.scene3d = null;
    await this.load();
    this.host.innerHTML = this.html();
    this.mount(this.host);
  }
  mount(host) {
    this.host = host;
    this.scene3d?.dispose();
    const container3d = host.querySelector('#park-scene-3d');
    if (container3d && this.current) {
      this.scene3d = mountParkScene3D(container3d, this.current, {
        colorByPhase: this.colorByPhase,
        sunDate: this.parkSunDate,
        sunHour: this.parkSunHour,
        onSunTick: ({ hourBjt }) => {
          this.parkSunHour = hourBjt;
          const slider = host.querySelector('[data-psun-hour]');
          if (slider) slider.value = String(hourBjt);
          const lbl = host.querySelector('#park-sun-hour-label');
          if (lbl) lbl.textContent = `${String(Math.floor(hourBjt)).padStart(2, '0')}:${String(Math.round((hourBjt % 1) * 60)).padStart(2, '0')}`;
        },
        onSelectBuilding: tpl => {
          const b = this.current?.data?.buildings?.find(x => x.template === tpl);
          if (b?.result?.project_id) {
            location.hash = `#result/${encodeURIComponent(b.result.project_id)}${b.result.version ? `?version=${b.result.version}` : ''}`;
          } else {
            this.notice(`已选中【${b?.name || tpl}】：尚未生成方案，请点击下方「⚡ 批量运行本机规则设计」生成园区 3D 排布！`);
          }
        },
      });
    }
    const guard = fn => event => Promise.resolve().then(() => fn(event)).catch(e => this.notice(e.message));
    host.onclick = guard(async event => {
      const el = event.target.closest('button');
      if (!el) return;
      if (el.dataset.focusBldg) {
        this.scene3d?.focusBuilding?.(el.dataset.focusBldg);
        return;
      }
      if (el.dataset.config) return this.configure(el.dataset.config, this.current.park);
      if (el.dataset.remove) {
        this.current.park.buildings = this.current.park.buildings.filter(b => b.template !== el.dataset.remove);
        delete this.current.park.settings[el.dataset.remove];
        return this.save();
      }
      const action = el.dataset.paction;
      if (!action) return;
      if (action === '3d-iso') { this.scene3d?.setCameraView('iso'); return; }
      if (action === '3d-top') { this.scene3d?.setCameraView('top'); return; }
      if (action === '3d-south') { this.scene3d?.setCameraView('south'); return; }
      if (action === '3d-sun-play') {
        const playing = this.scene3d?.toggleSunPlay?.();
        el.textContent = playing ? '⏸ 暂停日照' : '▶ 日照动画';
        return;
      }
      if (action === '3d-color') {
        this.colorByPhase = !this.colorByPhase;
        await this.refresh();
        return;
      }
      if (action.startsWith('preset-')) {
        const key = action.slice(7);
        const preset = PARK_PRESETS[key];
        if (!preset) return;
        this.batch = {
          ...this.batch,
          preset_key: key,
          module_id: preset.module_id,
          inverter_brand: preset.inverter_brand,
          layout_algo: preset.layout_algo,
          prefer: preset.prefer,
          dc_cable_family: preset.dc_cable_family,
          ac_cable_family: preset.ac_cable_family,
          payback_years_max: preset.payback_years_max,
          price_self_cny_kwh: preset.price_self_cny_kwh,
          monthly_kwh_wan: preset.monthly_kwh_wan,
          shifts: preset.shifts,
        };
        await this.applyOneClickSetup(host, { quiet: false, forceConstraints: true });
        return this.refresh();
      }
      if (action === 'toggle-pick-all') {
        const boxes = [...host.querySelectorAll('[data-pick]')];
        const allChecked = boxes.every(b => b.checked);
        boxes.forEach(b => { b.checked = !allChecked; });
        this.notice(!allChecked ? `已全选全部 ${boxes.length} 栋厂房` : '已取消勾选，请按需勾选目标厂房');
        return;
      }
      if (action === 'apply-oneclick-setup') {
        await this.applyOneClickSetup(host, { quiet: false });
        return this.refresh();
      }
      if (['start', 'pause', 'resume', 'skip'].includes(action) && this.id !== this.queue.id) await this.queue.load(this.id);
      if (action === 'new') {
        const name = prompt('园区名称');
        if (!name?.trim()) return;
        this.id = 'park-' + crypto.randomUUID().slice(0, 8);
        await this.api(`parks/${this.id}/save`, { id: this.id, name, buildings: [] });
      } else if (action === 'demo' || action === 'taizhou-demo') {
        this.id = action === 'taizhou-demo' ? 'taizhou-cmc-demo' : 'wujin-demo';
        await this.api(`parks/${this.id}/demo`, {});
      } else if (action === 'reset-designs') {
        await this.api(`parks/${this.id}/reset-designs`, {});
        this.notice('🧹 已清空当前园区所有厂房的排板结果，可重新设置参数并运行设计。');
      } else if (action === 'delete') {
        if (!confirm('删除园区及其队列和方案书？原屋顶、单栋项目和设计记录保留。')) return;
        await this.api(`parks/${this.id}/delete`, {});
      } else if (action === 'save') return this.save();
      else if (action === 'sync-neighbors') {
        await this.api(`parks/${this.id}/save`, this.current.park);
        const blds = this.current.data?.buildings ?? [];
        const heights = blds.map(b => `${b.name}(${b.roof?.height_m ?? 10}m)`).join('、');
        this.notice(`🏢 已同步园区 ${blds.length} 栋厂房的相对 3D 坐标与檐口高差（${heights}）：邻楼 3D 遮挡棱柱已自动注入各厂房周边遮挡物清单！`);
        return this.refresh();
      } else if (action === 'place' || action === 'add') {
        if (action === 'add') {
          const template = host.querySelector('[data-source]').value;
          if (!template) return;
          this.current.park.buildings.push({ template, x_m: 0, y_m: 0, rotation_deg: 0 });
        }
        this.current.park = await this.api(`parks/${this.id}/place`, this.current.park);
        return this.save();
      } else if (action === 'auto-run' || action === 'oneclick-setup-and-run') {
        const keys = await this.applyOneClickSetup(host, { quiet: true });
        if (!keys.length) return this.notice('请至少勾选或添加一栋厂房');
        const shiftMap = { day: 1, two: 2, continuous: 3 };
        this.notice(`正在为勾选的 ${keys.length} 栋厂房一键运行园区规则设计（含邻楼3D遮挡、批量选型与三方案比选），请稍候…`, { persist: true });
        const res = await this.api(`parks/${this.id}/auto-run`, {
          templates: keys,
          ...this.batch,
          payback_years_max: this.batch.payback_years_max !== '' ? Number(this.batch.payback_years_max) : null,
          price_self_cny_kwh: this.batch.price_self_cny_kwh !== '' ? Number(this.batch.price_self_cny_kwh) : null,
          monthly_kwh: this.batch.monthly_kwh_wan !== '' ? Number(this.batch.monthly_kwh_wan) * 10000 : null,
          shifts: shiftMap[this.batch.shifts] ?? null,
        });
        this.notice(`✅ 已完成全园区 ${res.count || keys.length} 栋厂房的一键设计与分期测算（候选状态）！如需纳入正式园区方案书，请点击「✅ 确认并批准勾选厂房导出」或进入单栋页核对后批准导出。`);
      } else if (action === 'approve-exports') {
        const picked = new Set([...host.querySelectorAll('[data-pick]:checked')].map(el => el.dataset.pick));
        const candidates = (this.current?.data?.buildings ?? []).filter(b => picked.has(b.template) && b.result?.project_id && b.result?.version);
        if (!candidates.length) return this.notice('勾选厂房尚无已生成的候选方案，请先运行设计');
        const summaryLines = candidates.map(b => `${b.name} (${b.result.project_id} · v${b.result.version} · ${Number(b.result.dc_kw ?? 0).toFixed(1)}kW)`).join('\n');
        if (!confirm(`这是初步方案文件导出；规则预检查不能代替独立工程审核、现场核定或施工批准。\n\n确认批准以下 ${candidates.length} 栋厂房的当前版本导出？\n${summaryLines}`)) return;
        let approvedCount = 0;
        for (const b of candidates) {
          const pid = encodeURIComponent(b.result.project_id);
          const ver = b.result.version;
          const prev = await this.api(`projects/${pid}/exports/preview`, { version: ver });
          if (prev?.ready && prev?.approval_id) {
            await this.api(`projects/${pid}/exports/approve`, { version: ver, approval_id: prev.approval_id, confirmed: true });
            approvedCount++;
          }
        }
        this.notice(`✅ 已明确批准 ${approvedCount}/${candidates.length} 栋厂房的方案导出！现在可生成包含已批准厂房的正式园区方案书。`);
      } else if (action === 'start') {
        const keys = [...host.querySelectorAll('[data-pick]:checked')].map(el => el.dataset.pick);
        this.notice(`本次共 ${keys.length} 栋；` + (this.current.cost ?
          `每栋约 ${this.current.cost.per_building.toFixed(4)} ${this.current.cost.currency}（最近完整记录估算）` : '暂无可靠模型费估计'));
        const items = keys.map(key => this.buildSpec(key, this.current.park));
        await this.queue.event('create', { items });
        return this.queue.next();
      } else if (action === 'pause' || action === 'resume') {
        await this.queue.event(action);
        if (action === 'resume') return this.queue.next();
      } else if (action === 'skip') return this.queue.skip();
      else if (action === 'report' || action === 'open-report') {
        await this.api(`parks/${this.id}/${action}`, {});
        this.notice(action === 'report' ? '园区方案书已生成' : '已打开园区方案书');
      }
      await this.refresh();
    });
    host.onchange = guard(async event => {
      const el = event.target;
      if (el.hasAttribute('data-pselect')) {
        this.id = el.value;
        return this.refresh();
      }
      if (el.hasAttribute('data-psun-date')) {
        this.parkSunDate = el.value;
        this.scene3d?.setSunTime?.(this.parkSunDate, this.parkSunHour);
        return;
      }
      if (el.hasAttribute('data-psun-hour')) {
        this.parkSunHour = Number(el.value);
        this.scene3d?.setSunTime?.(this.parkSunDate, this.parkSunHour);
        return;
      }
      if (el.dataset.pbatch) {
        this.batch[el.dataset.pbatch] = el.type === 'checkbox' ? el.checked : el.value;
        return;
      }
      if (el.dataset.pfield) this.current.park[el.dataset.pfield] = el.dataset.pfield === 'name' ? el.value : el.value === '' ? null : Number(el.value);
      if (el.dataset.rotate) {
        this.current.park.buildings.find(b => b.template === el.dataset.rotate).rotation_deg = Number(el.value);
        return this.save();
      }
    });
    host.oninput = event => {
      const el = event.target;
      if (el?.hasAttribute?.('data-psun-hour')) {
        this.parkSunHour = Number(el.value);
        this.scene3d?.setSunTime?.(this.parkSunDate, this.parkSunHour);
      }
    };
    const svg = host.querySelector('#park-map');
    if (!svg) return;
    let drag;
    const point = event => new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
    svg.onpointerdown = event => {
      const group = event.target.closest('[data-building]');
      if (!group) return;
      drag = { group, start: point(event), building: this.current.park.buildings.find(b => b.template === group.dataset.building) };
      svg.setPointerCapture(event.pointerId);
    };
    svg.onpointermove = event => {
      if (!drag) return;
      const next = point(event);
      drag.group.setAttribute('transform', `translate(${next.x - drag.start.x},${next.y - drag.start.y})`);
    };
    svg.onpointerup = guard(async event => {
      if (!drag) return;
      const next = point(event), moving = drag;
      drag = null;
      moving.building.x_m += next.x - moving.start.x;
      moving.building.y_m -= next.y - moving.start.y;
      await this.save();
    });
    svg.onpointercancel = () => { drag = null; };
  }
}
