import {esc, show} from './data.js';

export const economicInputs = [
  ['landRent', '空地年度地租', '元/亩·年', 0, 100000, '800，示意；仅空地消费'],
  ['loanRatio', '贷款比例', '%', 0, 99, '不贷款'], ['loanRate', '贷款年利率', '%', 0, 100, 'LPR 3.50，2026-09-20'],
  ['loanYears', '贷款年限', '年', 1, 25, '20'], ['cleaningTimes', '每年清洗', '次', 0, 365, '2，示意'],
  ['mechanismShare', '已获配机制电量占余电', '%', 0, 90, '0，资格未确认'],
  ['mechanismPrice', '已获配机制电价', '元/度', 0, 2, '按正式入选结果'],
  ['mechanismYears', '机制执行年限', '年', 1, 25, '按入选结果'],
  ['greenSoldShare', '余电已随绿电出售', '%', 0, 100, '0'], ['subsidyYear', '奖励到账年', '年', 1, 25, '1']
];

export function financialForm(f, field, toggle, kind = 'flat', use = null) {
  const choices = [['', '按容量推断（示意）'], ['two_part', '两部制'], ['single100', '单一制≥100kVA'], ['single_small', '单一制<100kVA']];
  const fields = economicInputs.filter(args => args[0] !== 'landRent' || kind === 'ground');
  return `<div class="grid2">${fields.map(args => field(...(args[0] === 'cleaningTimes' && use === 'barn' ?
    [...args.slice(0, 5), '4，养殖场示意默认；手填优先'] : args))).join('')}</div>
    ${kind === 'carport' ? '<p>未提供车棚租赁合同，合作情景未计场地或棚面租金；实际租金及税费待核定。</p>' : ''}
    <label>购电类别<select data-field="tariffClass">${choices.map(([key, label]) =>
      `<option value="${key}" ${f.tariffClass === key ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
    ${toggle('posttaxPayback', '按税后看回本要求')}${['ground','carport'].includes(kind) ? '' : toggle('refurbish', '安装前翻新屋面')}
    <details><summary>已核实的资格（未确认请留空）</summary>
    ${toggle('taxHoliday', '已确认本项目满足三免三减半资格')}
    <p>内部自建自用不适用；具体主体和项目资格须核实。</p>
    ${toggle('publicSubsidy', '已确认常州公共机构奖励全部条件')}
    <p>常发改〔2025〕212号：公共机构、上一年并网审核通过、无重复支持，信用安全环保合格，才计一次性0.3元/W。</p></details>`;
}

export function tariffGraph(graph) {
  const max = Math.max(1, ...graph.map(r => r.generation_kwh));
  const panels = [['price_cny_kwh', '分时电价 元/度', 2], ['generation_kwh', '光伏出力 kWh/小时', max]];
  return `<svg viewBox="0 0 720 440" role="img" style="width:100%" aria-label="全年分时电价和光伏出力，月内同小时平均">
    ${panels.map(([key, label, scale], index) => `<text x="65" y="${20 + index * 210}" fill="currentColor">
    ${label}（浅色 0 → 深色 ${scale.toFixed(2)}）</text>
    ${graph.map(r => `<rect x="${65 + r.hour * 25}" y="${30 + index * 210 + (r.month - 1) * 13}"
      width="24" height="12" fill="${index ? '#d37a32' : '#287b91'}" opacity="${.08 + .92 * Math.min(1, r[key] / scale)}">
      <title>${r.month}月${r.hour}时：${r[key].toFixed(3)}</title></rect>`).join('')}
    ${[1, 6, 12].map(m => `<text x="25" y="${40 + index * 210 + (m - 1) * 13}" fill="currentColor">${m}月</text>`).join('')}
    ${[0, 6, 12, 18, 23].map(h => `<text x="${65 + h * 25}" y="${204 + index * 210}" fill="currentColor">${h}时</text>`).join('')}`
    ).join('')}</svg>`;
}

export function financialResult(cash) {
  if (!cash?.costs) return '';
  const c = cash.costs, t = cash.tariff;
  const decimal = (value, digits = 2) => Number(value).toLocaleString('zh-CN', {maximumFractionDigits: digits});
  const rows = [['自投税前', cash], ['自投税后', cash.posttax]];
  if (cash.loan) rows.push(['贷款自有资金税前', cash.loan.pretax], ['贷款自有资金税后', cash.loan.posttax]);
  const names = {self_saving_cny: '自用节省', export_cny: '余电收入', green_cny: '绿证', subsidy_cny: '补贴', mechanism_adjustment_cny: '机制差价'};
  return `<section class="financial-detail"><h3>造价明细</h3><p>合计 ${show(c.capex_cny)} 元，折合 ${c.effective_cny_per_w.toFixed(3)} 元/W；
    CPIA参考2.59元/W。${esc(c.note)}</p><table class="tbl cost-items" style="table-layout:fixed;width:100%;word-break:break-word">
    <tr><th style="width:34%">项目</th><th>数量</th><th>单价元</th><th>小计元</th></tr>
    ${c.items.filter(r => r.quantity).map(r => `<tr><td>${esc(r.name)}（${esc(r.source['状态'])}）</td><td>${decimal(r.quantity, 1)}
    <span class="cost-unit">${esc(r.unit)}</span></td>
    <td>${decimal(r.unit_price_cny, 3)}</td><td>${decimal(r.subtotal_cny, 0)}</td></tr>`).join('')}</table>
    <h3>电价与收益</h3><p>加权自用电价 ${t.weighted_price_cny_kwh.toFixed(4)} 元/度。${esc(t.note)}</p>
    ${tariffGraph(t.graph)}<p>月内同小时平均示意；图不表示逐日实测。${esc(Object.entries(cash.income_breakdown).map(([k, v]) =>
      `${names[k]} ${show(v)} 元`).join('；'))}</p><p>预计核发 ${show(cash.certificates.issued_estimate)} 张，
    可交易估算 ${show(cash.certificates.tradable_estimate)} 张；${esc(cash.certificates.note)}</p>
    <h3>税和贷款</h3><p>回本要求按${cash.u04_basis}；未贷款指标始终并列显示。${cash.loan ?
      `自有初投 ${show(cash.loan.initial_equity_cny)} 元；利率 ${(cash.loan.rate * 100).toFixed(2)}%。` : '未填写贷款比例，未计贷款。'}</p>
    <table class="tbl"><tr><th>口径</th><th>回本年</th><th>收益率%</th><th>累计净收益元</th></tr>${rows.map(([name, r]) =>
      `<tr><td>${name}</td><td>${show(r.payback_years, '年')}</td><td>${show(r.irr_pct, '%')}</td><td>${show(r.profit_cny)}</td></tr>`).join('')}</table>
    <table class="tbl"><tr><th>投资方式</th><th>投资方税后回本年</th><th>税后收益率%</th><th>业主首年税后元</th></tr>
    ${cash.business_models.map(r => `<tr><td>${r.name}</td><td>${show(r.investor_posttax_payback_years, '年')}</td>
      <td>${show(r.investor_posttax_irr_pct, '%')}</td><td>${show(r.owner_posttax_first_year_cny)}</td></tr>`).join('')}</table>
    <p>并网建议：${esc(c.grid_voltage)}；${esc(c.grid_note)}</p><details><summary>税费、运维与资格假设</summary>
    ${cash.assumptions.map(n => `<p>${esc(n)}</p>`).join('')}<p>${esc(cash.subsidy.note)}</p>
    <p>基础运维 ${show(cash.operating_costs.base_om_cny)} 元/年；保险 ${show(cash.operating_costs.insurance_cny)} 元/年；
    清洗 ${show(cash.operating_costs.cleaning_cny)} 元/年；第13年更换 ${show(cash.operating_costs.replacement_cny)} 元。</p>
    ${cash.operating_costs.cleaning_basis ? `<p>${esc(cash.operating_costs.cleaning_basis)}</p>` : ''}
    ${cash.operating_costs.weeding ? `<p>${esc(cash.operating_costs.weeding.note)}；年节约
      ${show(cash.operating_costs.weeding.saving_cny)} 元。保险、清洗、更换、地租及偿债不减免。</p>` : ''}</details></section>`;
}

export function livestockResult(value) {
  if (!value) return '';
  if (value.use === 'barn') return `<section class="card"><h3>${esc(value.title)}</h3><p>${esc(value.corrosion)}</p>
    <p>${esc(value.fan_note)}</p><p>${value.keepouts.map(k => `${esc(k.label)}：避让${k.clearance_m}米`).join('；')}</p></section>`;
  const light = value.ground_light;
  return `<section class="card"><h3>牧光互补 · ${value.animal === 'cow' ? '牛' : '羊'}</h3>
    <p>真实最低边 ${show(value.actual_min_m)} m；牲畜示意最低 ${value.animal_min_m} m。
    地面平均受光 ${show(light.sun_pct)}%，要求 ${value.required_sun_pct}%。</p><p>${esc(light.method)}</p>
    <p>${esc(value.land_note)}</p><p>${esc(value.protection_note)}</p></section>`;
}
