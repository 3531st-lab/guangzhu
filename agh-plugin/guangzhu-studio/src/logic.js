import {DATA} from '../extensions/main/client/data.js';
import {decode, pendingLabel, resolvedTools, toolName} from '../../../desktop/web/tool-results.js';

const object = v => v && typeof v === 'object' && !Array.isArray(v);
const number = v => typeof v === 'number' && Number.isFinite(v);
const present = v => v !== null && v !== undefined && v !== '' && !(Array.isArray(v) && !v.length);
const id = s => typeof s === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(s);
const requireValue = (condition, message) => {
  if (!condition) throw new Error(message);
};
const num = (value, unit = '') => value === null ? '无结果' : `${value}${unit}`;
const metric = (label, value) => ({label, value});
const onlyKeys = (value,keys) => Object.keys(value).every(key => keys.includes(key));
const fields = (value,keys,check = number) => keys.every(key => check(value[key]));
const nullableNumber = value => value === null || number(value);

export function requirementTags(data) {
  const s = data.requirements.structured;
  const template = DATA.templates.find(t => t.id === data.project.template);
  const labels = {budget_cny_max:['预算 ≤ ',' 元'],payback_years_max:['回本 ≤ ',' 年'],capacity_kw_min:['装机 ≥ ',' kW'],capacity_kw_max:['装机 ≤ ',' kW'],
    walkway_m_min:['通道 ≥ ',' m'],obstacle_clearance_m_min:['离障碍 ≥ ',' m'],edge_setback_m_min:['离屋面边缘 ≥ ',' m']};
  const tags = Object.entries(labels).filter(([key]) => present(s[key])).map(([key,[before,after]]) => before+s[key]+after);
  if (s.tilt_deg_range) tags.push(`倾角 ${s.tilt_deg_range[0]}–${s.tilt_deg_range[1]}°`);
  const keepoutLabel = id => [...template?.obstacles ?? [],...template?.keepouts ?? []].find(zone => zone.id === id)?.label ?? id;
  if (s.keep_clear_ids?.length) tags.push('避开 '+s.keep_clear_ids.map(keepoutLabel).join('、'));
  if (object(data.facts)) tags.push(`开工前问答 ${Object.keys(data.facts).length} 项`);
  return tags;
}

export function parseUser(block) {
  const contents = Array.isArray(block?.content) ? block.content : [];
  const texts = contents.filter(p => p.type === 'text' && typeof p.text === 'string').map(p => p.text);
  const counts = {}, labels = {image:'图片',audio:'音频',video:'视频',file:'文件'};
  for (const part of contents) if (part.type !== 'text') {
    const label = labels[part.type] ?? '非文字内容';
    counts[label] = (counts[label] ?? 0)+1;
  }
  const plain = {kind:'plain',texts,text:texts.join(''),nonText:Object.entries(counts).map(([label,count]) => ({label,count}))};
  if (!/^【光筑任务书(?:[ \t]|】)/.test(texts[0] ?? '')) return plain;
  try {
    const source = texts[0].match(/```json\s*\n([\s\S]*?)\n```/);
    const data = source && JSON.parse(source[1]);
    requireValue(object(data) && data.brief === 'guangzhu.brief/1', '不是任务书');
    requireValue(onlyKeys(data,['brief','project','requirements','economics','facts','run']), '不是任务书');  // T22: optional facts
    requireValue(object(data.project) && object(data.requirements?.structured) && object(data.economics), '任务书不完整');
    requireValue(data.facts === undefined || object(data.facts), '任务书不完整');
    requireValue(object(data.run) && object(data.run.review), '任务书不完整');
    const r = data.run, review = r.review;
    requireValue(onlyKeys(data.project,['id','template']) && onlyKeys(data.requirements,['text','structured']), '未知字段');
    requireValue(onlyKeys(r,['max_rounds','compare','prefer','review','export']) && onlyKeys(review,['enabled','model','mode']), '未知字段');
    requireValue(id(data.project.id) && id(data.project.template) && typeof data.requirements.text === 'string', '项目或要求无效');
    requireValue(Number.isInteger(r.max_rounds) && r.max_rounds >= 1 && r.max_rounds <= 6 && typeof review.model === 'string', '运行设置无效');
    const template = DATA.templates.find(t => t.id === data.project.template);
    requireValue(['compare','export'].every(k => typeof r[k] === 'boolean') && typeof review.enabled === 'boolean', '任务书不完整');
    // Roofs the user drew in the desktop app (T18) are not bundled with the plugin.
    return {...plain,kind:'brief',data,title:'光筑任务书 v1',projectId:data.project.id,roofName:template?.name ?? '自建屋顶',tags:requirementTags(data)};
  } catch {return plain;}
}

export function roofGeometry(template) {
  const row = typeof template === 'string' ? DATA.templates.find(t => t.id === template) : template;
  if (!row?.outline?.length) return null;
  const xs = row.outline.map(p => p[0]), ys = row.outline.map(p => -p[1]), pad = Math.max(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys))*.06;
  const path = points => points.map(([x,y],i) => `${i ? 'L' : 'M'}${x} ${-y}`).join(' ')+' Z';
  const zone = z => ({id:z.id,label:z.label,...(z.kind === 'cylinder'
    ? {circle:{cx:z.center[0],cy:-z.center[1],r:z.radius_m}} : {path:path(z.footprint ?? z.polygon)})});
  return {viewBox:[Math.min(...xs)-pad,Math.min(...ys)-pad,Math.max(...xs)-Math.min(...xs)+2*pad,Math.max(...ys)-Math.min(...ys)+2*pad].join(' '),
    outline:path(row.outline),obstacles:row.obstacles.map(zone),keepouts:row.keepouts.map(zone)};
}

const TITLES = {gz_new_project:'建项目',gz_project_summary:'项目摘要',gz_set_requirements:'保存要求',gz_fetch_weather:'取天气',gz_generate_layout:'排板',
  gz_edit_design:'修改方案',gz_analyze:'综合分析',gz_compare_options:'三方案对比',gz_crosscheck_yield:'发电复核',gz_record_review:'保存审核',
  gz_export:'导出',gz_wait:'等待计算'};
export const TOOL_NAMES = Object.keys(TITLES);
export function cardData(block, nodes = []) {
  const linked = block?.toolUseId && resolvedTools(nodes).find(n => n.tool_use_id === block.toolUseId && n.wait_ids.length);
  if (linked) block = {...block, resultPreview:JSON.stringify(linked.data), status:linked.status};
  const d = decode(block?.resultPreview), args = decode(block?.argsPreview) ?? {};
  const native = toolName(block?.name);
  const tool = native === 'gz_wait' && !d?.pending && TOOL_NAMES.includes(d?.tool) && d.tool !== 'gz_wait' ? d.tool : native;
  const raw = String(block?.resultPreview || block?.summary || '未提供工具结果').split('\n').slice(0,20).join('\n');
  const card = {tool,family:'generic',title:TITLES[tool] ?? '工具结果',status:block?.status,
    raw:raw.trim() ? raw : '未提供工具结果',fallback:false,metrics:[],warnings:[]};
  if (block?.status === 'awaiting_approval') card.warnings.push('等待你在下方审批');
  if (d?.ok === true && d.pending === true) {
    card.status = 'running';
    card.pending = true;
    card.metrics = [metric('状态', pendingLabel(d))];
    return card;
  }
  if (!block?.resultPreview && ['planned','running','awaiting_approval'].includes(block?.status)) {
    card.metrics.push(metric('状态',block.summary ?? '等待工具结果'));
    return card;
  }
  const valid = condition => requireValue(condition,'工具结果不完整');
  try {
    valid(tool && object(d) && d.ok === true);
    if (['gz_new_project','gz_project_summary'].includes(tool)) {
      valid(number(d.roof_area_m2) && number(d.obstacle_count) && number(d.keepout_count) && (d.version === null || Number.isInteger(d.version)));
      card.family='project';
      card.templateId=DATA.templates.find(t => t.id === args.template || t.name === d.name)?.id;
      card.metrics=[metric('屋顶面积',num(d.roof_area_m2,' m²')),metric('障碍物',d.obstacle_count),metric('禁区',d.keepout_count),
        metric('当前版本',d.version === null ? '尚未排板' : 'v'+d.version)];
    } else if (['gz_generate_layout','gz_edit_design'].includes(tool)) {
      valid(Number.isInteger(d.version) && (tool === 'gz_generate_layout' ? number(d.modules) && number(d.dc_kw) : typeof d.summary === 'string'));
      const parent=d.parent_version ?? args.version;
      card.family='layout';
      const version = tool === 'gz_edit_design' ? `${Number.isInteger(parent) ? 'v'+parent : '未知父版本'} → v${d.version}` : `v${d.version}`;
      card.metrics=[metric('版本',version)];
      if (tool === 'gz_generate_layout') card.metrics.push(metric('组件',num(d.modules,' 块')),metric('装机',num(d.dc_kw,' kW')));
      else card.metrics.push(metric('变化',d.summary),metric('修改原因',d.reason ?? args.reason ?? '未知（参数预览不完整）'));
      if (number(d.dc_kw_change?.before) && number(d.dc_kw_change?.after)) {
        card.metrics.push(metric('装机变化',`${d.dc_kw_change.before} → ${d.dc_kw_change.after} kW`));
      }
    } else if (tool === 'gz_analyze') {
      valid(object(d.rules) && fields(d.rules,['passed','total','hard_failed']) && Array.isArray(d.rules.failed) && object(d.economics));
      valid(d.rules.failed.every(r => typeof r.id === 'string' && typeof r.name_zh === 'string' && 'value' in r && 'limit' in r));
      valid(fields(d.economics,['payback_years','irr_pct'],nullableNumber));
      const cash=d.what_if ?? d.economics;
      valid(fields(cash,['payback_years','irr_pct'],nullableNumber));
      card.family='analysis';
      card.metrics=[metric(d.what_if ? '基准规则通过' : '规则通过',`${d.rules.passed}/${d.rules.total}`),
        metric('硬性不通过',d.what_if?.hard_failed ?? d.rules.hard_failed),
        metric('回本',num(cash.payback_years,' 年')),metric('收益率',num(cash.irr_pct,'%'))];
      card.metrics[0].tone=d.rules.hard_failed > 0 ? 'danger' : d.rules.failed.length ? 'warning' : 'success';
      card.metrics[1].tone=card.metrics[1].value > 0 ? 'danger' : 'success';
      card.table={columns:['编号','规则','数值','限值'],rows:d.rules.failed.slice(0,3).map(r => [r.id,r.name_zh,String(r.value),String(r.limit)])};
      if (d.what_if) {
        valid(d.what_if.saved === false && number(d.what_if.hard_failed) && Array.isArray(d.what_if.rules));
        valid(d.what_if.rules.every(r => typeof r.id === 'string' && typeof r.status === 'string' && 'value' in r && 'limit' in r));
        card.warnings.push('试算，未保存；规则通过数为基准版本');
        card.table={columns:['编号','试算结果','数值','限值'],rows:d.what_if.rules.map(r => [
          r.id,{pass:'通过',fail:'不通过',na:'不适用'}[r.status] ?? r.status,String(r.value),String(r.limit)])};
      }
    } else if (tool === 'gz_compare_options') {
      valid(Array.isArray(d.options) && d.options.length === 3);
      valid(d.options.every(o => typeof o.name === 'string' && fields(o,['dc_kw','annual_kwh','avg_loss_pct','version'])
        && fields(o,['payback_years','irr_pct'],nullableNumber) && typeof o.hard_pass === 'boolean' && Array.isArray(o.violated_requirements)));
      card.family='compare';
      card.table={columns:['方案','版本','装机 kW','年发电 kWh','回本 年','收益率 %','遮挡 %','满足要求'],rows:d.options.map(o => [
        o.name,'v'+o.version,o.dc_kw,o.annual_kwh,num(o.payback_years),num(o.irr_pct),o.avg_loss_pct,
        o.hard_pass && !o.violated_requirements.length ? '是' : '否：'+o.violated_requirements.join('、')])};
    } else if (tool === 'gz_crosscheck_yield') {
      valid(object(d.specific_yield_kwh_kwp) && Object.keys(d.specific_yield_kwh_kwp).length);
      valid(Object.values(d.specific_yield_kwh_kwp).every(number) && Array.isArray(d.differences) && object(d.omitted));
      valid(d.differences.every(r => typeof r.left === 'string' && typeof r.right === 'string' && number(r.difference_kwh_kwp)));
      card.family='crosscheck';
      card.table={columns:['链','每千瓦发电量 kWh/kW'],rows:Object.entries(d.specific_yield_kwh_kwp)};
      if (d.groups) card.table={columns:['坡面 / 倾角 / 朝向','链','每千瓦发电量 kWh/kW'],
        rows:d.groups.flatMap(g => Object.entries(g.per_kw).map(([chain,value]) => [g.group.join(' / '),chain,value]))};
      if (d.total_kwh) card.metrics.push(metric('全设计各链发电合计',JSON.stringify(d.total_kwh),' kWh'));
      const abc=d.differences.filter(r => ['a','b','c'].includes(r.left) && ['a','b','c'].includes(r.right));
      if (d.differences.length) card.metrics.push(metric('全部链最大差（含天气来源差）',num(Math.max(...d.differences.map(r => Math.abs(r.difference_kwh_kwp))),' kWh/kW')));
      if (abc.length) card.metrics.push(metric('同 NASA 天气 a/b/c 最大差',num(Math.max(...abc.map(r => Math.abs(r.difference_kwh_kwp))),' kWh/kW')));
      card.warnings=Object.entries(d.omitted).map(([key,reason]) => `缺链 ${key}：${reason}`);
      if (d.note) card.warnings.push(d.note);
    } else if (tool === 'gz_export') {
      valid(Number.isInteger(d.version) && typeof d.directory === 'string' && object(d.files) && Object.keys(d.files).length);
      valid(Object.values(d.files).every(v => typeof v === 'string' && /^[a-f0-9]{64}$/i.test(v)));
      card.family='export';
      card.table={columns:['文件','sha256 前8位'],rows:Object.entries(d.files).map(([name,sha]) => [name,sha.slice(0,8)])};
      card.metrics=[metric('版本','v'+d.version),metric('目录',d.directory)];
    } else {
      let summary;
      if (tool === 'gz_set_requirements') {
        valid(object(d.requirements?.structured) && Array.isArray(d.contradictions));
        summary=`已保存 ${Object.keys(d.requirements.structured).length} 条结构化要求；矛盾 ${d.contradictions.length} 项`;
      } else if (tool === 'gz_fetch_weather') {
        valid(number(d.annual_ghi_kwh_m2) && typeof d.cache_hit === 'boolean');
        summary=`全年水平面辐射 ${d.annual_ghi_kwh_m2} kWh/m²；${d.cache_hit ? '命中缓存' : '联网取得'}`;
      } else {
        valid(typeof d.file === 'string');
        summary=`审核保存到 ${d.file}`;
      }
      card.metrics=[metric('摘要',summary)];
      if (d.contradictions?.length) card.warnings.push(...d.contradictions.map(String));
    }
  } catch {
    card.fallback=true;
    card.metrics=[];
    delete card.table;
    delete card.templateId;
  }
  return card;
}
