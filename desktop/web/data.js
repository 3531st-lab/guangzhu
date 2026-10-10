import {resolvedTools, sameArguments, toolName} from './tool-results.js';

export const esc = (value) => String(value ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
export const rawValue = (value) => value == null ? "未提供" : typeof value === "object" ? JSON.stringify(value) : String(value);
const words = {
  true: "是",
  false: "否",
  approve: "通过",
  revise: "需修改",
  pass: "通过",
  fail: "未通过",
  warn: "提醒",
  high: "高",
  medium: "中",
  low: "低",
  na: "不适用（没提这项要求）",
  cache: "本地缓存",
  network: "联网获取",
  download: "联网获取",
  "NASA POWER UTC hourly": "NASA POWER（逐小时，UTC）"
};
const fields = { version: "版本", dc_kw: "装机 kW", payback_years: "回本 年", irr_pct: "收益率 %", meets_requirements: "满足要求" };
export function show(value, unit = "") {
  if (value == null) return "未提供";
  if (Array.isArray(value)) return value.length ? value.map((item) => show(item, unit)).join("、") : "无";
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${fields[key] ?? key}：${show(item, fields[key] ?? unit)}`).join("；");
  if (typeof value !== "number") return words[value] ?? String(value);
  if (!Number.isFinite(value)) return "未提供";
  const digits = /kWh|kWh\/m²|kWh\/kWp/.test(unit) ? 0 : /kW|功率|%|收益率/.test(unit) ? 1 : /年|m|米|°/.test(unit) ? 2 : 0;
  return value.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
// Draggable dividers between panes, as in a desktop app. `pane` is the side whose size the CSS variable holds;
// `keep` is what the other side always keeps, so the AGH chat and its approval cards stay reachable.
export const SPLITS = {
  run: {axis:"x", css:"--split-run", pane:"start", size:400, min:260, max:640, keep:440},
  result: {axis:"x", css:"--split-result", pane:"end", size:400, min:380, max:760, keep:440},
  new: {axis:"x", css:"--split-new", pane:"end", size:420, min:320, max:680, keep:480},
  form: {axis:"x", css:"--split-form", pane:"end", size:400, min:320, max:720, keep:420},
  roof: {axis:"x", css:"--split-roof", pane:"end", size:400, min:300, max:640, keep:420},
  park: {axis:"x", css:"--split-park", pane:"start", size:220, min:180, max:420, keep:480},
  queue: {axis:"y", css:"--split-queue", pane:"end", size:240, min:90, max:640, keep:120},
};
export function splitter(key) {
  const rule = SPLITS[key], what = rule.axis === "x" ? "宽度" : "高度";
  return `<div class="splitter ${rule.axis}" data-split="${key}" data-key="split-${key}" role="separator" tabindex="0" aria-orientation="${
    rule.axis === "x" ? "vertical" : "horizontal"}" title="拖动调整${what}，双击恢复" aria-label="拖动调整${what}，双击恢复"></div>`;
}
export const valueMarkup = (value, unit = "", source = "") => `<span title="${esc(source ? source + " · 原值 " + rawValue(value) :
  "原值 " + rawValue(value))}">${esc(show(value, unit))}</span>`;
import {qualified} from './model-choices.js';
export {qualified, modelChoices} from './model-choices.js';
const yes = (value) => value === "1";
const FACTS = [["fLand", "land_type", String], ["fRedline", "within_redline", yes],
  ["fRoof", "roof_type", String], ["fAge", "roof_age_years", Number], ["fCore", "core", String], ["fSky", "skylights", yes],
  ["fOwned", "owned", yes], ["fKva", "transformer_kva", Number], ["fKwh", "monthly_kwh", (value) => Math.round(Number(value) * 1e4)],
  ["fShifts", "shifts", Number], ["fExport", "export_allowed", yes]];  // T22: optional answers before construction; 月用电 is typed in 万度
export function formSpec(form, model) {
  const structured = { keep_clear_ids: [...form.keep ?? []] }, economics = {};
  const fields2 = { payback: "payback_years_max", budget: "budget_cny_max", capMin: "capacity_kw_min", capMax: "capacity_kw_max", walkway: "walkway_m_min",
    obstacle: "obstacle_clearance_m_min", edge: "edge_setback_m_min", curtail: 'curtail_pct_max', transformer: 'transformer_kva',
    transformerShare: 'transformer_share', maxHeight: 'max_height_m', phaseKw: 'phase1_kw', phaseBudget: 'phase1_budget_cny' };
  for (const [input, key] of Object.entries(fields2)) if (String(form[input] ?? "").trim()) structured[key] = Number(form[input]) *
    (['budget', 'phaseBudget'].includes(input) ? 1e4 : 1) / (input === 'transformerShare' ? 100 : 1);
  if (form.noExport) structured.export_allowed = false;
  if (form.noDrill) structured.ballast_only = true;
  if (structured.phase1_kw != null && structured.phase1_budget_cny != null) throw new Error('一期装机与一期预算只能填一项');
  if (String(form.tiltMin ?? "").trim() || String(form.tiltMax ?? "").trim()) {
    if (form.tiltMin === "" || form.tiltMax === "") throw new Error("请填写完整倾角范围");
    structured.tilt_deg_range = [Number(form.tiltMin), Number(form.tiltMax)];
  }
  if (form.notes?.trim()) structured.notes = form.notes.trim();
  for (const [input, key] of Object.entries({ priceSelf: "price_self_cny_kwh", selfUse: "self_use_ratio", capex: "capex_cny_per_w", priceExport:
    "price_export_cny_kwh" })) if (String(form[input] ?? "").trim()) economics[key] = Number(form[input]) / (input === "selfUse" ? 100 : 1);
  const financeFields = {landRent: 'land_rent_cny_mu_year', loanRatio: 'loan_ratio', loanRate: 'loan_rate',
    loanYears: 'loan_years', cleaningTimes: 'cleaning_times',
    mechanismShare: 'mechanism_share', mechanismPrice: 'mechanism_price', mechanismYears: 'mechanism_years',
    greenSoldShare: 'green_sold_share', subsidyYear: 'subsidy_year'};
  for (const [input, key] of Object.entries(financeFields)) {
    if (String(form[input] ?? '').trim()) economics[key] = Number(form[input]) /
      (['loanRatio', 'loanRate', 'mechanismShare', 'greenSoldShare'].includes(input) ? 100 : 1);
  }
  for (const [input, key] of [['posttaxPayback', 'posttax_payback'], ['refurbish', 'refurbish'],
    ['taxHoliday', 'tax_holiday_confirmed'], ['publicSubsidy', 'public_subsidy_confirmed']]) {
    if (form[input] != null) economics[key] = Boolean(form[input]);
  }
  if (form.tariffClass) economics.tariff_class = form.tariffClass;
  const facts = Object.fromEntries(FACTS.filter(([input]) => String(form[input] ?? "").trim()).map(([input, key, cast]) => [key, cast(form[input])]));
  const equipment = Object.fromEntries([['module_id', form.moduleId], ['inverter_brand', form.inverterBrand],
    ['inverter_id', form.inverterId]].filter(([, value]) => value));
  return {
    template: form.template,
    id: form.id,
    text: form.text,
    structured,
    economics,
    ...Object.keys(equipment).length ? {equipment} : {},
    ...Object.keys(facts).length ? { facts } : {},
    max_rounds: Number(form.maxRounds),
    compare: form.compare,
    prefer: form.prefer,
    review: form.review,
    review_mode: "independent",
    ...model ? { reviewer_model: model.id } : {},
    export: form.exportOn
  };
}
export function roofSVG(item, labels = false) {
  const roof = item.geometry ?? item.roof ?? item.project?.roof ?? item, points = roof.outline ?? [];
  if (!points.length) return '<span class="muted">没有屋顶几何</span>';
  const near = roof.surroundings ?? [], all = [...points, ...near.flatMap((o) => o.footprint ?? [-1, 1].map((d) => o.center.map((v) => v + d * o.radius_m)))];
  const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
  const x = Math.min(...xs), y = Math.max(...ys), w = Math.max(...xs) - x + 12, h = y - Math.min(...ys) + 12;
  const path = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${p[0] - x + 6},${y - p[1] + 6}`).join(" ") + "Z";
  const label = (shape, point, offset) => labels ? `<text class="lab" x="${point[0] - x + 7}" y="${y - point[1] + offset}">${esc(shape.label)}</text>` : "";
  const keepout = (k) => `<path class="ko" d="${path(k.polygon)}"/>${label(k, k.polygon[0], 4)}`;
  const obstacle = (o) => (o.center ? `<circle class="ob" cx="${o.center[0] - x + 6}" cy="${y - o.center[1] + 6}" r="${o.radius_m}"/>` :
    `<path class="ob" d="${path(o.footprint)}"/>`) + label(o, o.center ?? o.footprint[0], 5);
  const cx = w / 2, cy = h / 2;
  const slope = roof.type === 'metal' ? `<g class="slope-arrow" transform="translate(${cx},${cy}) rotate(${roof.slope_azimuth_deg})">
    <path d="M0 8V-8M0 -8L-2 -4M0 -8L2 -4" stroke="#c87743" stroke-width="1"/></g>` : '';
  const faces = (roof.planes ?? []).map(p => {
    const center = [0,1].map(k => p.outline.reduce((sum, point) => sum + point[k] / p.outline.length, 0));
    const px = center[0] - x + 6, py = y - center[1] + 6;
    return `<path d="${path(p.outline)}" fill="${p.material === 'glass' ? '#9fd6df' : 'none'}" stroke="#718297" stroke-width=".3"/>
      <g transform="translate(${px},${py}) rotate(${p.slope_azimuth_deg})">
      <path d="M0 2V-2M0 -2L-1 -1M0 -2L1 -1" stroke="#c87743" stroke-width=".4"/></g>
      <text x="${px + 1}" y="${py}" font-size="2">P${p.id} ${p.slope_deg}°</text>`;
  }).join('');
  return `<svg class="rsvg" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(item.name)}屋顶轮廓">
    ${near.map((o) => obstacle(o).replace('class="ob"', 'class="near"')).join("")}<path class="shell" d="${path(points)}"/>${(roof.keepouts ?? []).map(keepout).join("")}
    ${faces}${(roof.obstacles ?? []).map(obstacle).join("")}${slope}<text class="north" x="${w - 5}" y="5">↑ N</text></svg>`;
}
export function parkSVG(b) {  // T22: one building's exported layout, north up
  const xs = b.outline.map((p) => p[0]), ys = b.outline.map((p) => p[1]), x = Math.min(...xs) - 2, y = Math.max(...ys) + 2;
  const path = (points) => points.map((p, i) => `${i ? "L" : "M"}${(p[0] - x).toFixed(1)},${(y - p[1]).toFixed(1)}`).join("") + "Z";
  return `<svg class="psvg" viewBox="0 0 ${(Math.max(...xs) - x + 2).toFixed(1)} ${(y - Math.min(...ys) + 2).toFixed(1)}" role="img" aria-label="${
    esc(b.name)}的排板"><path class="shell" d="${path(b.outline)}"/><path class="panels" d="${b.panels.map(path).join("")}"/></svg>`;
}
export function parkTotals(rows) {  // T22: payback from the summed yearly cash flows, the same rule as each building's own
  const sum = (key) => rows.reduce((total, row) => total + (row[key] ?? 0), 0);
  let cumulative = 0, payback = null;
  for (let year = 0; year < Math.max(0, ...rows.map((row) => row.net_cny.length)); year++) {
    const net = rows.reduce((total, row) => total + (row.net_cny[year] ?? 0), 0), before = cumulative;
    cumulative += net;
    if (payback === null && year > 0 && before < 0 && cumulative >= 0) payback = year - 1 - before / net;
  }
  return { count: rows.length, dc_kw: sum("dc_kw"), annual_kwh: sum("annual_kwh"), capex_cny: sum("capex_cny"), co2_t: sum("co2_t"), payback_years: payback };
}
export function parkPlan(buildings, chosen, budget = null, limit = null) {  // fastest payback first; phase one takes what the budget and grid allow
  const picked = buildings.filter((b) => chosen.has(b.run_id)).sort((a, b) => (a.payback_years ?? 1e9) - (b.payback_years ?? 1e9));
  let cost = 0, power = 0;
  const first = picked.filter((b) => {
    const fits = (budget === null || cost + b.capex_cny <= budget) && (limit === null || power + (b.ac_kw ?? 0) <= limit);
    if (fits) [cost, power] = [cost + b.capex_cny, power + (b.ac_kw ?? 0)];
    return fits;
  });
  return { picked, first, all: parkTotals(picked), phase1: parkTotals(first) };
}
export function toolResult(nodes, name) {
  const node = resolvedTools(nodes).filter(n => n.name === name && n.status === 'completed' && !n.pending).at(-1);
  return node?.data?.ok === false ? null : node?.data ?? null;
}
export function runStats(records) {
  const ordinary = records.filter(r => !isEvaluation(r));
  return { all: ordinary.length, evaluation:records.length - ordinary.length,
    passed: ordinary.filter((r) => !isReviewRecord(r) && recordPassed(r)).length, failed: ordinary.filter((r) =>
    !recordUnverified(r) && !recordPassed(r)).length, review: ordinary.filter(isReviewRecord).length };
}
export const isEvaluation = row => typeof row?.evaluation === 'boolean' ? row.evaluation
  : /^eval-\d{4}-[A-Za-z0-9][A-Za-z0-9_-]*$/.test(row?.run_id ?? '') || /(?:^|[/\\])eval-\d{4}(?:[/\\]|$)/.test(row?.directory ?? '');
export function beijingTime(value, style = 'full') {
  if (value == null || value === '') return '未提供';
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '未提供';
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Shanghai', year:'numeric',
    month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', hourCycle:'h23'}).formatToParts(date).map(p => [p.type, p.value]));
  const {year, month, day, hour, minute} = parts;
  return style === 'id' ? `${month}${day}-${hour}${minute}` : `${style === 'short' ? '' : year + '-'}${month}-${day} ${hour}:${minute}`;
}
export function inferRequirements(text, form, roof) {
  const next = {...form, keep:[...form.keep ?? []]}, recognized = [];
  let unknownText = text;
  const numerals = '零〇一二三四五六七八九十百千万亿兆两廿卅卌点壹贰叁肆伍陆柒捌玖拾佰仟';
  const number = `(?<![\\d.${numerals}])(\\d+(?:\\.\\d+)?)(?![\\d.${numerals.replace('万', '')}]|万[\\d.${numerals}])`;
  const parsed = text.replace(/\s+/g, '').replace(/千伏安/g, 'kVA').replace(/千瓦/g, 'kW').replace(new RegExp(`[\\d.${numerals}]+`, 'g'), token => {
    const match = token.match(/^([一二三四五六七八九]|[一二三四五六七八九]?十[一二三四五六七八九]?)(万)?$/);
    if (!match) return token;
    const digits = '零一二三四五六七八九', [tens, units] = match[1].split('十');
    const value = units === undefined ? digits.indexOf(tens) : (tens ? digits.indexOf(tens) : 1) * 10 + (units ? digits.indexOf(units) : 0);
    return value + (match[2] ?? '');
  }).replace(/1期/g, '一期').replace(/2期/g, '二期').replace(new RegExp(`${number}MW`, 'gi'), (_, n) => Number(n) * 1000 + 'kW')
    .replace(new RegExp(`(\\d)万(?!元|[\\d.${numerals}])`, 'g'), '$1万元');
  const specs = [
    ['payback', '回本上限', `${number}年(?:内)?回本|(?:回本期?|回收期)(?:不超过|最多)?${number}年`],
    ['budget', '预算万元', `(?:预算|投资|资金)(?:控制在|最多|不超过|上限|为|是)?${number}(万)?元`],
    ['capMin', '装机下限', `(?:装机|装)?(?:至少|不少于)(?:装)?${number}kW`],
    ['capMax', '装机上限', `(?:装机|容量)?(?:不超过|上限|最多)(?:装)?${number}kW|(?:装机|容量|装)${number}kW(?:左右|以内)`],
    ['walkway', '检修通道', `(?:检修通道|检修道|通道|走道)(?:至少|留)?${number}米|${number}米(?:的)?(?:检修通道|检修道|通道|走道)`],
    ['edge', '屋边距', `(?:屋边|边缘|离女儿墙)(?:至少|留)?${number}米|${number}米(?:屋)?边距`],
    ['obstacle', '障碍间距', `设备周边(?:至少|留)?${number}米`],
    ['capex', '造价元/W', `造价每瓦${number}元`],
    ['selfUse', '自用比例%', `(?:自发自用|自用)比例${number}%`],
    ['priceSelf', '自用电价元/度', `自用电价每度${number}元`],
    ['loanRatio', '贷款比例%', `贷款比例${number}%`],
    ['loanRate', '贷款年利率%', `(?:贷款)?年利率${number}%`],
    ['loanYears', '贷款年限', `贷款${number}年`],
    ['cleaningTimes', '年清洗次数', `每年清洗${number}次`],
    ['priceExport', '余电电价元/度', `(?:余电上网|余电电价|上网电价)(?:每度)?${number}元`]
  ];
  const fill = (key, label, value) => {
    const existing = String(next[key] ?? '').trim() !== '';
    if (!existing) next[key] = value;
    const shown = typeof next[key] === 'boolean' ? (next[key] ? '是' : '否') : next[key];
    recognized.push(`${label}：${shown}${existing ? '（已有值优先）' : ''}`);
  };
  for (const [key, label, pattern] of specs) {
    const total = parsed.replace(/一期(?:先装|装|容量|先|预算|投资)(?:为|不超过)?[\d.]+(?:万元|元|kW)(?:左右|以内)?/gi, '');
    const match = total.match(new RegExp(pattern, 'i'));
    if (!match) continue;
    const value = Number(match[1] ?? match[2]);
    fill(key, label, key === 'budget' && !match[2] ? value / 1e4 : value);
  }
  const tilt = parsed.match(new RegExp(`倾角${number}(?:到${number})?度`));
  if (tilt) {
    fill('tiltMin', '倾角下限', Number(tilt[1]));
    fill('tiltMax', '倾角上限', Number(tilt[2] ?? tilt[1]));
  }
  for (const [key, label, pattern] of [
    ['curtail', '限电上限%', `限电(?:不超过|最多|上限)?${number}%`],
    ['transformer', '变压器kVA', `变压器(?:容量)?(?:为|是)?${number}kVA`],
    ['transformerShare', '变压器比例%', `(?:变压器的?|变压器容量的)${number}%`],
    ['maxHeight', '最高点m', `(?:最高|限高)(?:不超过|为)?${number}(?:米|m)`],
    ['phaseKw', '一期kW', `一期(?:先装|装|容量|先)?${number}kW`],
    ['phaseBudget', '一期预算万元', `一期(?:预算|投资)(?:为|不超过)?${number}万(?:元)?`]]) {
    const match = parsed.match(new RegExp(pattern, 'i'));
    if (match) fill(key, label, Number(match[1]));
  }
  if (/按税后(?:看)?回本/.test(parsed)) fill('posttaxPayback', '按税后看回本', true);
  if (/装之前翻新/.test(parsed)) fill('refurbish', '装之前翻新', true);
  const numerical = recognized.length;
  if (/不上网|只自用|装防逆流/.test(parsed)) fill('noExport', '只自用不上网', true);
  if (/不(?:能|许|准)?打孔|按压载|只用压载|压载支架安装|不(?:能)?破坏防水/.test(parsed)) fill('noDrill', '只用压载、不打孔', true);
  if (/不(?:能)?高出女儿墙|不超过女儿墙/.test(parsed)) fill('maxHeight', '女儿墙限高m', (roof?.geometry ?? roof?.roof ?? roof)?.parapet_height_m);
  const pickEquipment = (key, label, value) => {
    if (!next[key + 'Picked']) next[key] = value;
    const shown = {Huawei:'华为', Sungrow:'阳光'}[next[key]] ?? next[key];
    recognized.push(`${label}：${shown}${next[key + 'Picked'] ? '（已有值优先）' : ''}`);
  };
  for (const [name, brand] of [['华为', 'Huawei'], ['阳光', 'Sungrow']])
    if (new RegExp(`${name}.*逆变器|逆变器.*${name}`).test(parsed)) pickEquipment('inverterBrand', '逆变器品牌', brand);
  for (const [pattern, id] of [['天合.*N型', 'trina-tsm-605neg19rc20'], ['晶科.*N型', 'jinko-jkm605n-66hl4m-bdv']])
    if (new RegExp(pattern, 'i').test(parsed)) pickEquipment('moduleId', '组件型号', id);
  for (const [model, id] of Object.entries(form.inverterModels ?? {})) {
    if (parsed.toLowerCase().includes(model.toLowerCase())) {
      pickEquipment('inverterId', '逆变器型号', id);
      unknownText = unknownText.replace(new RegExp(model.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'), '');
    }
  }
  const geometry = roof?.geometry ?? roof?.roof ?? roof ?? {};
  for (const zone of [...geometry.obstacles ?? [], ...geometry.keepouts ?? []]) {
    const label = zone.label?.replace(/[（(].*?[）)]/g, '').trim();
    if (!label || !text.split(/[，。；;、]/).some(part => part.includes(label) && /避开|别挡|不要动|留空|采光|必须避/.test(part))) continue;
    next.keep = [...new Set([...next.keep, zone.id])];
    recognized.push('必须避开：' + label);
  }
  // 10/6: 尽量多装 / 尽量铺满 / 尽量利用屋面 means 多装 when all three plans meet the hard limits; a hand pick stays, removing the words undoes the switch
  if (/尽(?:量|可能)(?:多装|多铺|装满|铺满|利用)|越多越好|能装多少装多少/.test(parsed)) {
    if (!next.preferPicked) [next.prefer, next.preferAuto] = ['max_capacity', true];
    recognized.push(`三方案都满足时选：${PREFER[next.prefer] ?? next.prefer}${next.preferPicked ? '（已选的优先）' : ''}`);
  } else if (next.preferAuto) [next.prefer, next.preferAuto] = ['balanced', false];
  const unknown = !numerical ? unknownText.split(/[，。；;、]/).filter(part => new RegExp(`[\\d${numerals}]`).test(part)).join('；') : '';
  return {form:next, summary:unknown ? `这几处没认出来：${unknown}，请填到下面的栏里` : [...new Set(recognized)].join('；'), recognized, unknown};
}
export function recoveryDescription(session, computed, now = Date.now()) {
  if (!session?.id || session.review || session.op !== 'idle' || computed?.suggestions?.length || computed?.steps?.some(s => s.waiting)) return null;
  const tools = resolvedTools(session.nodes);
  const rejected = session.nodes.slice(session.turnStart ?? 0).filter(n => n.kind === 'approval' && n.verdict === 'rejected').filter(n =>
    !tools.some(t => t.seq > n.seq && t.name === toolName(n.tool) && t.data?.ok === true && !t.pending
      && sameArguments(t.args_json, n.args_json))).at(-1);
  const labels = {gz_new_project:'建项目', gz_set_requirements:'保存要求', gz_fetch_weather:'取天气', gz_generate_layout:'排板',
    gz_edit_design:'修改方案', gz_analyze:'综合分析', gz_compare_options:'三方案对比', gz_record_review:'保存审核'};
  const action = (label, text) => ({label, text});
  if (toolName(rejected?.tool) === 'gz_export') {
    const version = rejected.args_json?.version;
    const reason = rejected.via === 'timeout' ? '超时' : '原因未记录';
    return {banner:['sync', 'callback'].includes(rejected.via) ? '导出审批没通过。' : `导出没有批准（${reason}）。`,
      actions:Number.isInteger(version) ? [action('重新申请导出', `请重新申请导出版本 v${version}，我会点「仅允许这次」。`)] : []};
  }
  if (rejected) {
    const tool = toolName(rejected.tool), label = labels[tool] ?? tool;
    return {banner:rejected.via === 'timeout' ? `${label}的审批 60 秒没点，AGH 自动拒绝了。` : `${label}的审批没通过。`,
      actions:[action('重新申请', rejected.via === 'timeout'
        ? `刚才${tool}的审批超时了。请按原参数重新调用它，我会马上批准；然后按一键模式继续，直到申请导出。`
        : `请按原参数重新调用 ${tool}，我会批准；然后按一键模式继续，直到申请导出。`)]};
  }
  if (toolResult(session.nodes, 'gz_export')) return null;
  const comparison = tools.filter(t => t.name === 'gz_compare_options').at(-1);
  if (!tools.some(t => t.pending) && comparison && (comparison.data?.ok === false || ['failed', 'error'].includes(comparison.status))) {
    const reason = comparison.data?.message_zh ?? (/Request timed out/i.test(comparison.result ?? '') ? '超时' : '未提供失败原因');
    return {banner:`三方案没算出来：${reason}。`, actions:[action('重试三方案', '请按原参数重新调用三方案，然后继续。'),
      action('跳过三方案，继续完成', '三方案没做完，跳过三方案，用最后通过的版本继续完成复核、审核和导出。')]};
  }
  const said = (computed?.lastText ?? '').trim(), output = n => ['text', 'tool'].includes(n.kind), nodes = session.nodes ?? [];
  // AGH can look idle for a few seconds while the model is still thinking before its first word; only a long silence is a stop
  if (!nodes.some(output) && !session.userStopped && now - (session.idleSince ?? 0) < 20000) return null;
  return {banner:session.userStopped ? '你停止了这次运行。' : said ? `Agent 停下了：${said.slice(0, 60)}` : nodes.slice(session.turnStart ?? 0).some(output) ?
    'Agent 停下了：这一轮没说原因就结束了；点「继续完成」从上一步接着做。' :
    'Agent 停下了：模型没有回话，多半是网络连不上模型服务商（检查代理）或 key 失效；网络好了点「继续完成」。',
    actions:[action('继续完成', '继续一键模式，从上一步接着做，不要重复已完成的步骤，直到申请导出。')]};
}
export const isReviewRecord = (row) => row?.kind ? row.kind === "review" : row?.review === true || !!row?.run_id?.includes("review");
export const recordUnverified = (row) => isReviewRecord(row) && (row.verification?.review?.state === "unverified" ||
  row.verification?.review?.passed === null ||
  row.verification?.scope === "independent-review" && row.verification?.passed == null);
export const recordPassed = (row) => !recordUnverified(row) && (isReviewRecord(row) ? (row.verification?.review?.passed ??
  row.verification?.passed) === true :
  row.passed === true || row.verification?.passed === true);
export function replayChoices(record) {
  const primary = record.run?.session, reviewer = record.run?.review_session_id;
  return [...new Set([primary, ...(record.timeline?.nodes ?? []).map((n) => n.session)])].filter(Boolean).map((id) => ({ id, label: id === reviewer ||
    id === primary && isReviewRecord(record.run) ? "独立审核" : id === primary ? "设计会话" : "原生会话" }));
}
export function withVerifiedReview(computed, session, replayContext = null) {
  if (replayContext) {
    if (session?.id && replayContext.session !== session.id) return computed;
    const completed = session?.reviewCompletedAt ?? session?.timeline?.nodes?.filter(n => n.kind === 'tool'
      && n.session === session.reviewSession && toolName(n.name) === 'gz_record_review' && n.status === 'completed').at(-1)?.ended_at;
    if (!Number.isFinite(Date.parse(completed)) || !replayContext.at || replayContext.at[0] < Date.parse(completed)) return computed;
  }
  const result = session?.result, record = session?.reviewRecord, version = result?.selected_version, proof = session?.verification?.review;
  const saved = result?.review_files?.[record?.file?.split("/").at(-1)];
  if (session?.review || session?.run?.review?.enabled === false || proof?.passed !== true || !saved || version !== result.version ||
    record.version !== version || saved.version !== version || !Array.isArray(saved.findings) || !proof.independent?.some((r) => r.passed &&
      r.session === session.reviewSession && r.versions?.includes(version))) return computed;
  const metrics = [{ label: "审核结论", value: saved.verdict }, { label: "问题数", value: saved.findings.length }, { label: "审核记录", value: record.file }];
  return { ...computed, steps: computed.steps.map((s) => s.number === 9 ? {
    ...s,
    state: "completed",
    statusLabel: "完成（见审核会话）",
    waiting: false,
    countdown: null,
    metrics,
    raw: JSON.stringify(saved),
    detail: `来源：已核对独立会话 ${session.reviewSession}；gz_record_review → ${record.file}；v${version}。审核意见原文可在审核会话和结果页查看。`
  } : s) };
}
// Codex review E2: a saved change in plain Chinese (rule codes get their names) and, against its parent, the change in modules, capacity,
// base-year yield and payback. A run of named codes such as "E08,S01" becomes one Chinese list, without the spaces around it.
export function versionSummary(version, parent = null, names = {}) {
  const raw = version.reason || "未提供", source = `designs/v${version.version}.json`, of = (v, field) => v?.metrics?.[field] ?? v?.statistics?.[field];
  const named = (code) => names[code] ? `${names[code]}（${code}）` : code;
  const reason = raw.replace(/\s*\b[GSELU]\d{2}\b(?:\s*[,，、]\s*[GSELU]\d{2}\b)*\s*/g, (run) => {
    const codes = run.match(/[GSELU]\d{2}/g);
    return codes.every((code) => names[code]) ? codes.map(named).join("、") : run.replace(/[GSELU]\d{2}/g, named);
  });
  const changes = [["组件", "module_count", "块"], ["装机", "dc_kw", "kW"], ["基准年发电", "annual_kwh", "kWh"], ["回本", "payback_years", "年"]].map(([label,
    field, unit]) => ({ label: label + "变化", unit, delta: true, value: of(version, field) - of(parent, field), source: `${source} 与 v${parent?.version} 相比` }));
  return { version: version.version, title: `${version.parent_version == null ? "开始" : "v" + version.parent_version} → v${version.version}`, reason: reason.length > 60 ?
    reason.slice( 0, 60 ) + "…" : reason, source: `${source} · reason：${raw}`, metrics: parent ? changes.filter((m) => Number.isFinite(m.value)) : [["组件", "module_count", "块"], ["装机", "dc_kw", "kW"], ["排距",
    "row_spacing_m", "m"]].map(([
    label,
    field,
    unit
  ]) => ({ label, unit, value: Number.isFinite(version.statistics?.[field]) ? version.statistics[field] : undefined, source:
    `${source} · statistics.${field}` })) };
}
// Codex review E3: each option opens its own layout in 3D, with yield, shading, how far it is from each requirement and why it is picked.
const PREFER = {max_capacity:'多装', fast_payback:'最快回本', balanced:'折中'};
function room(o, need = {}) {
  const fmt = (v) => Math.abs(v).toLocaleString('zh-CN', {maximumFractionDigits:1});
  return [['回本', need.payback_years_max, o.payback_years, '年'], ['预算', need.budget_cny_max == null ? null : need.budget_cny_max / 1e4, o.capex_cny / 1e4, '万元'],
    ['装机上限', need.capacity_kw_max, o.dc_kw, 'kW'], ['装机下限', need.capacity_kw_min, o.dc_kw, 'kW', true]]
    .filter(([, limit, value]) => Number.isFinite(limit) && Number.isFinite(value)).map(([name, limit, value, unit, low]) =>
      `${name}${(low ? value >= limit : value <= limit) ? '余' : '超出'} ${fmt(value - limit)} ${unit}`).join(' · ');
}
export function comparisonTable(compare, result = {}) {
  const options = [...compare?.current ? [compare.current] : [], ...compare?.options ?? []];
  const prefer = result.run?.prefer ?? 'balanced', recommended = compare?.recommended?.[prefer]?.version;
  const labels = {G03:'通道不够', G04:'留空区域被占用', G05:'倾角超范围', G06:'避让距离不足', L01:'承重超限',
    U01:'装机不足', U02:'装机超上限', U03:'超预算', U04:'回本超限'};
  const versions = new Map((result.versions ?? []).map(v => [v.version, v]));
  const rows = options.map(o => {
    const mark = o.version === result.selected_version ? '选定' : o.version === recommended ? '推荐' : '';
    let ancestor = o === compare.current ? null : versions.get(o.version), reason = '', visited = new Set();
    while (ancestor && ancestor.version !== compare.base_version && !visited.has(ancestor.version)) {
      visited.add(ancestor.version);
      const cut = /^(?:多装|最快回本|折中)：按 (U02|U03) 删除 \d+ 块$/.exec(ancestor.reason ?? ''), count = ancestor.statistics?.module_count;
      if (cut && Number.isInteger(count)) reason ||= `${cut[1] === 'U03' ? '预算' : '装机上限'}删板后${count.toLocaleString('zh-CN')}块`;
      ancestor = versions.get(ancestor.parent_version);
    }
    const status = (o.violated_requirements ?? []).map(id => labels[id] ?? id).join('、') || (o.hard_pass === true ? '满足' : '硬性规则未过');
    const tilt = o.align === 'pitched' ? '' : Number.isFinite(o.tilt_deg) ? `${o.tilt_deg}° · ` : '';
    const margin = room(o, result.project?.requirements?.structured);
    return `<tr class="${mark === '选定' ? 'pick' : ''}"><td><button class="pick-option" data-version="${o.version}" aria-pressed="${o.version === result.version}" ` +
      `title="在 3D 里看这个方案">${esc(`${o.name} v${o.version}${mark ? ' ' + mark : ''}`)}</button><br>${esc(tilt + status)}` +
      `${reason ? '<br><small>' + esc(reason) + '</small>' : ''}${o.fill_landscape_count ? `<br><small>横放补位 ${o.fill_landscape_count} 块</small>` : ''}` +
      `${margin ? '<br><span class="muted">' + esc(margin) + '</span>' : ''}</td>` +
      `<td>${esc(o.align === 'pitched' ? '顺坡 ' + o.planes.map(p => 'P' + p).join('、') :
        ({south:'正南', edge:'顺边', ew:'东西向', custom:`朝向 ${o.azimuth_deg}°`})[o.align] ?? '原排法')}</td>` +
      `<td>${valueMarkup(o.dc_kw, 'kW')}</td><td class="wide"><span title="原值 ${esc(rawValue(o.annual_kwh))} kWh">${Number.isFinite(o.annual_kwh) ?
        (o.annual_kwh / 1e4).toFixed(1) : '未提供'}</span></td><td>${valueMarkup(o.payback_years, '年')}</td>` +
      `<td class="wide">${valueMarkup(o.avg_loss_pct, '%')}</td></tr>`;
  });
  const pick = compare?.recommended?.[prefer], why = pick ? `<p class="muted tilt-note">按「${PREFER[prefer] ?? prefer}」选 v${pick.version}：${esc(pick.why)}。` +
    '点方案名，左边 3D 换成那个方案的排布。</p>' : '';
  return '<div class="table-scroll"><table class="tbl compare-table"><thead><tr><th>方案 / 要求</th><th>排法</th><th>装机 <small>kW</small></th>' +
    '<th class="wide" title="基准年发电">年发电 <small>万kWh</small></th><th>回本 <small>年</small></th><th class="wide">遮挡 <small>%</small></th></tr></thead><tbody>' +
    rows.join('') +
    '</tbody></table></div>' + why + tiltNote(compare?.site_tilt) +
    (compare?.capacity_note ? `<p class="muted">${esc(compare.capacity_note)}。多装按候选装机量选择。</p>` : '');
}
// T19：三套方案的倾角怎么来的，一句话写清楚。
export function tiltNote(site) {
  if (!site || !Number.isFinite(site.best)) return '';
  return `<p class="muted tilt-note">倾角按当地全年天气定：成排参考最佳 ${site.best}°；多装参考 ${site.capacity}°（每千瓦少 ${site.loss_pct?.capacity}%），` +
    `折中参考 ${site.balanced}°（少 ${site.loss_pct?.balanced}%）。实际排法和倾角见表，东西向另算发电。</p>`;
}
export function naturallyStopped(session, previousOp, computed) {
  const last = session.nodes?.at(-1);
  return !session.review && previousOp === "running" && session.op === "idle" && last?.kind === "text" && !!last.text?.trim() && toolResult( session.nodes,
    "gz_new_project" )?.ok === true && !session.nodes.some((n) => n.kind === "tool" && n.status === "running") && !computed.steps.some((s) => s.waiting) &&
    !computed.suggestions.length;
}
export function finishRequest(design, review, model) {
  return {
    session_id: design.id,
    project_id: design.project,
    export_version: toolResult(design.nodes, "gz_export")?.version,
    reviewer_model: model?.id ?? "",
    ...review ? { review_session_id: review.id } : {}
  };
}
export function shouldReview(session, result, count) {
  return !session.review && session.run.review?.enabled && !!result.selected_version && result.verification?.checks?.length === 4 &&
    result.verification.checks.every((c) => c.passed) && result.verification.review?.passed !== true && count < 2;
}
export function timeLabel(hour) {
  const minutes = Math.round(Number(hour) * 60);
  return String(Math.floor(minutes / 60)).padStart(2, "0") + ":" + String(minutes % 60).padStart(2, "0");
}
export function usageSummary(value, { live = false, now = Date.now() } = {}) {
  const u = value ?? {}, number = (n) => Number.isFinite(n) && n >= 0 ? n : null;
  const tokens = Object.fromEntries(["input", "output", "cacheRead", "cacheWrite", "reasoning"].map((k) => [k, number(u.tokens?.[k])]));
  const parts = ["input", "output", "cacheRead", "cacheWrite"].map((k) => tokens[k]);
  const start = Date.parse(u.started_at), end = u.ended_at == null && live ? now : Date.parse(u.ended_at);
  const costs = (Array.isArray(u.costs) ? u.costs : []).filter((c) => typeof c?.currency === "string" && c.currency && number(c.micros) !== null).map((c) =>
    ({ currency: c.currency, micros: c.micros }));
  return {
    elapsed_seconds: Number.isFinite(start) && Number.isFinite(end) && end >= start ? (end - start) / 1e3 : null,
    model_requests: number(u.model_requests),
    recorded_model_calls: number(u.recorded_model_calls),
    tokens,
    total_tokens: parts.every((n) => n !== null) ? parts.reduce((a, b) => a + b, 0) : null,
    costs,
    billing_complete: u.billing_complete === true && costs.length > 0,
    missing_costs: number(u.missing_costs)
  };
}
