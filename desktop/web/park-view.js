import {esc, valueMarkup, splitter} from './data.js';

const terminal = item => ['completed', 'failed', 'skipped'].includes(item.status);
const labels = {pending:'等待', creating:'准备会话', sending:'已派发，待确认', running:'运行中', approval:'等待原生批准',
  cancelling:'等待取消确认；尚未开始的空闲不能证明派发已结束', reconcile:'需核对原会话', completed:'已结束', failed:'失败', skipped:'已跳过'};
export function queueMarkup(queue) {
  if (!queue?.items.length) return '';
  return `<div id="park-queue-display" data-key="parkqueue" class="card"><h3>厂房队列${queue.paused ? ' · 已暂停后续派发' : ''}</h3>
    <p>每栋导出请在右侧点击「仅允许这次」。</p><button class="btn sm" data-action="park-queue-show">回到运行园区</button>
    <button class="btn sm" data-action="park-pause">暂停后续</button><button class="btn sm" data-action="park-resume">继续 / 恢复</button>
    <button class="btn sm" data-action="park-skip">跳过当前栋</button>${queue.items.some(item => !['completed', 'failed', 'skipped'].includes(item.status)) ?
      '<button class="btn sm" data-action="park-abandon">放弃这个队列</button>' : ''}<ol>${
    queue.items.map(item => `<li>${esc(item.spec.template)} · ${item.stage === 'review' ? '独立审核' : '设计'} · ${labels[item.status]}
    ${esc(item.reason)}</li>`).join('')}</ol></div>`;
}
export class ParkView {
  constructor(api, queue, configure, buildSpec, notice) {
    Object.assign(this, {api, queue, configure, buildSpec, notice, id:null, parks:[], selected:new Set()});
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
    const options = this.parks.map(p => `<option value="${esc(p.id)}" ${p.id === this.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('');
    const button = (action, text) => `<button class="btn sm" data-paction="${action}">${text}</button>`;
    const side = `<aside class="card"><h2>园区</h2><select data-pselect><option value="">选择园区</option>${options}</select>
      ${button('new', '新建园区')}${button('demo', '载入武进示意园区')}<a class="btn sm" href="#park-legacy">已有设计汇总</a></aside>`;
    if (!this.current) return `<div class="park-editor">${side}${splitter('park')}<p>新建园区，加入我的屋顶或演示屋顶。</p></div>`;
    const {park, data, svg} = this.current;
    const field = (key, label, unit) => `<label>${label}<input data-pfield="${key}" value="${esc(park[key] ?? '')}"/>${unit}</label>`;
    const sources = this.roofs.filter(r => !r.project?.park && !park.buildings.some(b => b.template === r.id));
    const rows = data.buildings.map(b => `<tr><td><input type="checkbox" data-pick="${esc(b.template)}" checked>${esc(b.name)}</td>
      <td>${b.roof.height_m} m</td><td>${valueMarkup(b.result?.dc_kw, 'kW')}</td><td>${valueMarkup(b.result?.capex_cny, '元')}</td>
      <td>${valueMarkup(b.result?.payback_years, '年')}</td><td>${b.result?.park_phase ?? '—'}</td>
      <td><input type="number" data-rotate="${esc(b.template)}" value="${b.rotation_deg}" min="-360" max="360" aria-label="旋转角度"></td>
      <td><button data-config="${esc(b.template)}">条件与开工问答</button><button data-remove="${esc(b.template)}">移出</button></td></tr>
      <tr><td colspan="8">${esc(b.result?.shading_note ?? '尚无核验设计')} · ${esc(b.result?.run_id ?? '')}
      ${b.result?.ac_missing ?? ''}</td></tr>`).join('');
    const totals = [['装机', data.all.dc_kw, 'kW'], ['年发电', data.all.annual_kwh, 'kWh'], ['造价', data.all.capex_cny, '元'],
      ['整体回本', data.all.payback_years, '年'], ['年减碳', data.all.co2_t, 't'], ['逆变器', data.inverter_count, '台'],
      ['实际额定 AC', data.rated_ac_kw, 'kW']].map(([label, value, unit]) => `<span>${label} ${valueMarkup(value, unit)} ${unit}</span>`).join(' · ');
    const risks = data.risks.map(r => `${r.label}：${r.limit == null ? '未填' : r.excess == null ? '无法核定' :
      r.excess > 1e-9 ? `有风险，超 ${r.excess.toFixed(3)} kW` : '未超出'}`).join('；');
    const cost = this.current.cost;
    const estimate = cost ? `每栋约 ${cost.per_building.toFixed(4)} ${cost.currency}，按最近 ${cost.samples} 次完整 AGH 费用记录估算；非账单。` :
      '暂无可靠模型费估计；缺额、没有记录或币种混合时不填0，不换算人民币。';
    return `<div class="park-editor">${side}${splitter('park')}<main><div class="card">${field('name', '名称', '')}
      ${field('transformer_kva', '变压器', 'kVA')}${field('grid_kw', '并网限制', 'kW')}${field('budget_cny', '预算', '元')}
      ${button('save', '保存')}${button('delete', '删除园区')}${button('place', '按原始坐标摆放')}
      <select data-source>${sources.map(r => `<option value="${esc(r.id)}">${esc(r.name)}</option>`).join('')}</select>${button('add', '加入厂房')}
      <p>拖动楼栋移动，表格修改转角。北向上；OSM 使用原始坐标，无地理锚点的自画屋顶摆在空处。</p>
      <p>武进示意园区采用 real-07、09、10、11：相邻且外形相近，不证明同属一家公司；高度和女儿墙为示意。</p>${svg}</div>
      <div class="card"><p>${totals}</p>${['posttax', 'equity'].map(key => data.all[key] ?
        `<p>${key === 'posttax' ? '税后整体' : '贷款权益税后'}回本 ${valueMarkup(data.all[key].payback_years, '年')} 年；
        收益率 ${valueMarkup(data.all[key].irr_pct, '%')} %</p>` :
        data.all[key + '_note'] ? `<p>${esc(data.all[key + '_note'])}</p>` : '').join('')}<p>${risks}</p><p>额定 AC 由归档电气文件每台直流容量和未舍入容配比还原。</p>
      <p>园区按整栋回本顺序分期，沿 T22 预算和兼容 AC 阈值；屋顶内分期不重复相加。蓝色一期，棕色二期。</p>
      <table class="tbl"><thead><tr><th>厂房</th><th>高度</th><th>装机</th><th>造价</th><th>回本</th><th>期次</th><th>转角°</th><th>设置</th></tr></thead>
      <tbody>${rows}</tbody></table><button data-config="shared">共享条件与运行设置</button>
      <p>共 ${park.buildings.length} 栋，可勾选子集。${esc(estimate)}</p>
      ${button('start', '一键设计勾选厂房')}${button('pause', '暂停后续')}${button('resume', '继续 / 恢复')}${button('skip', '跳过当前栋')}
      ${button('report', '生成园区方案书')}${button('open-report', '打开园区方案书')}</div>${
      queueMarkup(this.id === this.queue.id ? this.queue.queue : this.current.queue)}</main></div>`;
  }
  async save() {
    try { await this.api(`parks/${this.id}/save`, this.current.park); }
    finally { await this.refresh(); }
  }
  async refresh() {
    await this.load();
    this.host.innerHTML = this.html();
    this.mount(this.host);
  }
  mount(host) {
    this.host = host;
    const guard = fn => event => Promise.resolve().then(() => fn(event)).catch(e => this.notice(e.message));
    host.onclick = guard(async event => {
      const el = event.target.closest('button');
      if (!el) return;
      if (el.dataset.config) return this.configure(el.dataset.config, this.current.park);
      if (el.dataset.remove) {
        this.current.park.buildings = this.current.park.buildings.filter(b => b.template !== el.dataset.remove);
        delete this.current.park.settings[el.dataset.remove];
        return this.save();
      }
      const action = el.dataset.paction;
      if (!action) return;
      if (['start', 'pause', 'resume', 'skip'].includes(action) && this.id !== this.queue.id) await this.queue.load(this.id);
      if (action === 'new') {
        const name = prompt('园区名称');
        if (!name?.trim()) return;
        this.id = 'park-' + crypto.randomUUID().slice(0, 8);
        await this.api(`parks/${this.id}/save`, {id:this.id, name, buildings:[]});
      } else if (action === 'demo') {
        this.id = 'wujin-demo';
        if (!this.parks.some(p => p.id === this.id)) await this.api(`parks/${this.id}/demo`, {});
      } else if (action === 'delete') {
        if (!confirm('删除园区及其队列和方案书？原屋顶、单栋项目和设计记录保留。')) return;
        await this.api(`parks/${this.id}/delete`, {});
      } else if (action === 'save') return this.save();
      else if (action === 'place' || action === 'add') {
        if (action === 'add') {
          const template = host.querySelector('[data-source]').value;
          if (!template) return;
          this.current.park.buildings.push({template, x_m:0, y_m:0, rotation_deg:0});
        }
        this.current.park = await this.api(`parks/${this.id}/place`, this.current.park);
        return this.save();
      } else if (action === 'start') {
        const keys = [...host.querySelectorAll('[data-pick]:checked')].map(el => el.dataset.pick);
        this.notice(`本次共 ${keys.length} 栋；` + (this.current.cost ?
          `每栋约 ${this.current.cost.per_building.toFixed(4)} ${this.current.cost.currency}（最近完整记录估算）` : '暂无可靠模型费估计'));
        const items = keys.map(key => this.buildSpec(key, this.current.park));
        await this.queue.event('create', {items});
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
      if (el.dataset.pfield) this.current.park[el.dataset.pfield] = el.dataset.pfield === 'name' ? el.value : el.value === '' ? null : Number(el.value);
      if (el.dataset.rotate) {
        this.current.park.buildings.find(b => b.template === el.dataset.rotate).rotation_deg = Number(el.value);
        return this.save();
      }
    });
    const svg = host.querySelector('#park-map');
    if (!svg) return;
    let drag;
    const point = event => new DOMPoint(event.clientX, event.clientY).matrixTransform(svg.getScreenCTM().inverse());
    svg.onpointerdown = event => {
      const group = event.target.closest('[data-building]');
      if (!group) return;
      drag = {group, start:point(event), building:this.current.park.buildings.find(b => b.template === group.dataset.building)};
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
