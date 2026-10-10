import {resolvedTools, pendingLabel} from './tool-results.js';
import {comparisonTable} from './data.js';

export const STEP_TITLES = ["建项目", "看项目、定计划", "记要求", "取天气", "排板", "分析与自改", "三方案", "发电复核", "独立审核", "人工批准导出"];
const GROUPS = [["gz_new_project"], ["gz_project_summary"], ["gz_set_requirements"], ["gz_fetch_weather"], ["gz_generate_layout"], [ "gz_analyze",
  "gz_edit_design" ], ["gz_compare_options"], ["gz_crosscheck_yield"], ["subagent_fork", "gz_record_review"], ["gz_export"]];
const parse = (value) => {
  try {
    return typeof value === "string" ? JSON.parse(value) : value;
  } catch {
    return null;
  }
};
const object = (value) => value && typeof value === "object" && !Array.isArray(value);
const nameOf = (value) => GROUPS.flat().find((name) => value === name || value?.endsWith("_" + name));
const metric = (label, value) => ({ label, value });
const shown = (value) => value == null ? "未提供" : value;
const completed = (node) => node?.status === "completed" && !node.pending && node.data?.ok !== false;
const failed = (node) => !node?.pending && (["failed", "cancelled", "error"].includes(node?.status) || node?.data?.ok === false);
const trial = (data) => data?.what_if?.saved === false ? data.what_if : null;
function details(name, data) {
  const d = data ?? {}, rules = d.rules ?? {};
  const differences = Array.isArray(d.differences) ? d.differences : [], maximum = (rows) => rows.length && rows.every((r) =>
    Number.isFinite(r.difference_kwh_kwp)) ? Math.max(...rows.map((r) => Math.abs(r.difference_kwh_kwp))) : undefined;
  switch (name) {
    case "gz_new_project":
      return [metric("项目", d.project_id), metric("屋顶面积 m²", d.roof_area_m2), metric("障碍物", d.obstacle_count), metric("禁区", d.keepout_count)];
    case "gz_set_requirements":
      return [metric("保存的结构化字段（含说明）", object(d.requirements?.structured) ? Object.keys(d.requirements.structured).length : undefined), metric("矛盾项",
        d.contradictions)];
    case "gz_fetch_weather":
      return [metric("全年水平面辐射 kWh/m²", d.annual_ghi_kwh_m2), metric("命中缓存", d.cache_hit), metric("天气来源", d.source), metric("取得方式", d.used)];
    case "gz_generate_layout":
      return [metric("版本", d.version), metric("组件数", d.modules), metric("装机 kW", d.dc_kw)];
    case "gz_analyze":
      return [metric(trial(d) ? "基准规则通过" : "规则通过", `${shown(rules.passed)}/${shown(rules.total)}`), metric("硬性不通过", (trial(d) ?? rules).hard_failed),
        ...trial(d) ? [metric("试算状态", "未保存")] : []];
    case "gz_edit_design":
      return [metric("版本", d.version), metric("修改", d.summary)];
    case "gz_compare_options":
      return (d.options ?? []).map((o) => metric(o.name, { version: o.version, dc_kw: o.dc_kw, payback_years: o.payback_years, irr_pct: o.irr_pct,
        meets_requirements: typeof o.hard_pass === "boolean" && Array.isArray(o.violated_requirements) ? o.hard_pass && !o.violated_requirements.length :
        undefined }));
    case "gz_crosscheck_yield":
      return [
        ...(d.groups ?? []).map(g => metric(`坡面 ${g.group[0]} · 倾角 ${g.group[1]}° · 朝向 ${g.group[2]}° kWh/kWp`, g.per_kw)),
        ...(d.total_kwh ? [metric("全设计合计 kWh", d.total_kwh)] : []),
        metric("各链 kWh/kWp", d.specific_yield_kwh_kwp),
        metric("全部链最大差（含天气来源差） kWh/kWp", maximum(differences)),
        metric("同 NASA 天气 a/b/c 最大差 kWh/kWp", maximum(differences.filter((r) => ["a", "b", "c"].includes(r.left) && ["a", "b", "c"].includes(r.right))))
      ];
    case "gz_record_review":
      return [metric("审核记录", d.file)];
    case "gz_export":
      return [metric("清单文件数", object(d.files) ? Object.keys(d.files).length : undefined), metric("sha256 前8位", object(d.files) ?
        Object.fromEntries(Object.entries(d.files).map(([k, v]) => [k, String(v).slice(0, 8)])) : undefined), metric( "manifest sha256 前8位",
          d.manifest_sha256?.slice(0, 8) )];
    default:
      return [];
  }
}
export function computeSteps(nodes = [], options = {}) {
  const { run = {}, op = "running", approvals = [], now = null } = options;
  const tools = resolvedTools(nodes).map(n => ({...n, index:n.call_index, name:nameOf(n.name)})).filter(n => n.name);
  const firstRequirements = tools.find((n) => n.name === "gz_set_requirements")?.index ?? nodes.length;
  const analyses = tools.filter(n => n.name === 'gz_analyze' && completed(n) && !trial(n.data)).filter((n, index, all) =>
    !n.wait_ids.length || !all.slice(0, index).some(p => p.session === n.session && p.result_seq === n.result_seq));
  const plan = nodes.slice(0, firstRequirements).filter((n) => n.kind === "text" && /计划/.test(n.text ?? "")).at(-1)?.text;
  const states = new Map();
  for (const event of approvals) states.set(nameOf(event.tool), event);
  const steps = GROUPS.map((names, index) => {
    const calls = tools.filter((n) => names.includes(n.name) && (index !== 1 || n.index < firstRequirements));
    const last = calls.at(-1), waiting = names.map((n) => states.get(n)).find((a) => a?.pending &&
      !(completed(last) && Date.parse(last.ended_at) >= a.received_at));
    const skipped = index === 6 && run.compare === false || index === 8 && run.review?.enabled === false || index === 9 && run.export === false;
    let state = !last ? "not_started" : failed(last) ? "issue" : completed(last) ? "completed" : "running";
    if (index === 0 && completed(last) && last.data?.ok !== true) state = "issue";
    if (index === 1 && completed(last) && !plan) state = firstRequirements < nodes.length ? "issue" : "running";
    if (index === 5 && completed(last) && (last.name === "gz_edit_design" || (trial(last.data) ??
      last.data?.rules)?.hard_failed > 0)) state = op === 'idle' ? 'issue' : 'running';
    if (index === 8 && completed(last) && (last.name !== "gz_record_review" || run.review?.mode !== "independent" && !calls.some((n) =>
      n.name === "subagent_fork" && completed(n) && n.index < last.index))) state = "running";
    if (waiting) state = "running";
    if (skipped && !calls.length && !waiting) state = "skipped";
    const metrics = last?.pending ? [metric('状态', pendingLabel(last.data))] : last?.data ? details(last.name, last.data) : [];
    const warnings = [
      ...last?.data?.contradictions ?? [],
      ...Object.entries(last?.data?.omitted ?? {}).map(([chain, reason]) => `缺链 ${chain}：${reason}`),
      ...last?.data?.note ? [last.data.note] : []
    ];
    const comparison = index === 6 && completed(last) ? last.data : null;
    const candidates = [comparison?.current, ...comparison?.options ?? []].filter(Boolean).map(row => row.version);
    const selected = options.selected_version ?? tools.filter(n => n.index > last?.index && completed(n) &&
      ['gz_analyze', 'gz_crosscheck_yield', 'gz_export'].includes(n.name) && !trial(n.data) && candidates.includes(n.data?.version)).at(-1)?.data?.version;
    return {
      number: index + 1,
      title: STEP_TITLES[index],
      state,
      metrics,
      comparison: comparison ? comparisonTable(comparison, {...options, run, selected_version:selected}) : null,
      detail: last?.pending ? pendingLabel(last.data) : index === 1 ? plan ?? "" : index === 6 && failed(last)
        ? last.data?.message_zh ?? (/Request timed out/i.test(last.result ?? '') ? '超时' : '未提供失败原因')
        : index === 5 && state === 'running' && completed(last)
          ? `修改中（第 ${Math.max(1, analyses.length)} 轮）`
          : index === 8 && run.review?.mode === "independent" ? "独立审核；本页仅显示当前会话的证据，设计与审核须分别查看。"
          : comparison?.recommended?.[run.prefer ?? 'balanced']?.why ?? "",
      warnings,
      waiting: Boolean(waiting),
      countdown: waiting && Number.isFinite(now) && Number.isFinite(waiting.received_at) ? Math.min(60, Math.max( 0,
        60 - Math.floor((now - waiting.received_at) / 1e3) )) : null,
      raw: last?.result ?? ""
    };
  });
  const rounds = analyses.map((n) => ({ version: n.data?.version, passed:
    n.data?.rules?.passed, total: n.data?.rules?.total, hard_failed: n.data?.rules?.hard_failed, failed: n.data?.rules?.failed ?? [] }));
  steps[5].rounds = rounds;
  const record = tools.filter((n) => n.name === "gz_record_review" && completed(n)).at(-1), fork = tools.filter((n) => n.name === "subagent_fork" &&
    completed(n) && n.index < (record?.index ?? Infinity)).at(-1);
  const reviewText = typeof fork?.result === "string" ? fork.result : JSON.stringify(fork?.result ?? "");
  const review = parse([...reviewText.matchAll(/```json\s*\n?([\s\S]*?)\n?```/g)].at(-1)?.[1]);
  if (record && review && ["approve", "revise"].includes(review.verdict) && Array.isArray(review.findings)) {
    steps[8].metrics.push(metric( "审核员结论", review.verdict ), metric("审核员问题数", review.findings.length));
    steps[8].warnings.push("是否原样记录审核结论，以执行记录核对为准。");
  } else if (record) steps[8].metrics.push(metric("审核结论", "未提供（待执行记录核对）"), metric("问题数", undefined));
  const exported = tools.filter((n) => n.name === "gz_export" && completed(n));
  const used = new Set(), unapproved = exported.some((call) => {
    const end = tools.find((n) => n.index > call.index)?.index ?? nodes.length;
    const declarations = nodes.slice(call.index + 1, end).filter(n => n.kind === 'approval' && !n.pending && nameOf(n.tool) === 'gz_export');
    const decisions = declarations.filter(n => (!call.wait_ids.length && !Object.hasOwn(n, 'tool_use_id')
      || !!n.tool_use_id && n.tool_use_id === call.tool_use_id)
      && (!Number.isInteger(call.initial.result_seq) || call.seq < n.seq && n.seq < call.initial.result_seq));
    const signal = approvals.find((a) => !used.has(a) && nameOf(a.tool) === "gz_export" && a.pending && Number.isFinite(a.received_at) &&
      Date.parse(call.started_at) <= a.received_at && a.received_at <= Date.parse(call.ended_at));
    if (signal) used.add(signal);
    if (decisions.length !== declarations.length) return true;
    return decisions.length ? decisions.length !== 1 || decisions[0].verdict !== "allowed-once" : call.wait_ids.length > 0 || !signal;
  });
  const warning = unapproved ? "导出没有经过人工批准，这次不能作为 3.1 证据。" : null;
  const lastText = nodes.filter((n) => n.kind === "text" && n.text).at(-1)?.text ?? "";
  const stopped = op === "idle" && !exported.length;
  const suggestionText = lastText.replace(/\*\*|__/g, "");
  const suggestions = stopped ? [...suggestionText.matchAll(/(?:^|\n)[ \t]*(?:(?:[-*+]|\d+[.)、])[ \t]+)?建议([①②③])[ \t]*[：:]?[ \t]*([^\n]+)/g)].map((m) =>
    ({ number: m[1], text: m[2].trim() })).filter((s) => s.text) : [];
  if (stopped && !suggestions.length) {
    let underHeading = false;
    for (const line of lastText.split(/\r?\n/)) {
      const heading = line.replace(/\*\*|__/g, "").trim().replace(/^#{1,6}[ \t]+/, "");
      if (/^(?:放宽)?建议(?:（[^（）]*）|\([^()]*\))?[：:]?$/.test(heading)) {
        underHeading = true;
        continue;
      }
      if (!line.trim()) continue;
      const item = line.match(/^[ \t]*([①②③])[ \t]*[：:、.]?[ \t]*(\S.*)$/);
      if (underHeading && item) suggestions.push({ number: item[1], text: item[2].trim() });
      else underHeading = false;
    }
  }
  return { steps, rounds, warning, lastText, stopped, suggestions };
}
