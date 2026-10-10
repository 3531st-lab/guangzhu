import {financialForm, financialResult, livestockResult} from './economic-ui.js';
import { Setup } from './setup.js';
import { ParkQueue } from './park-queue.js';
import { ParkView, queueMarkup } from './park-view.js';
import { computeSteps } from "./steps.js";
import { Bridge, setAghOrigin } from "./bridge.js";
import {esc, show, rawValue, valueMarkup, qualified, formSpec, roofSVG, modelChoices, toolResult, runStats,
  finishRequest, shouldReview, timeLabel, isReviewRecord, replayChoices, recordPassed, recordUnverified,
  withVerifiedReview, versionSummary, naturallyStopped, usageSummary, inferRequirements, beijingTime,
  isEvaluation, recoveryDescription, comparisonTable, parkPlan, parkSVG, SPLITS, splitter} from "./data.js";
import { createScene } from "./scene.js";
import { leaveRoofEditor, mountRoofEditor, roofEditorPage } from "./roofedit.js";
import { createReplay } from "./replay.js";
import { resolvedTools } from "./tool-results.js";
import { HEAT_COLORS } from "./scene-data.js";
import {wiringPanel, wiringDetails} from './wiring-ui.js';
const evaluation = /(?:^\?|&)eval=1(?:&|$)/.test(location.search ?? "");
const $ = (id) => document.getElementById(id), html = (id, text) => {
  if ($(id)) $(id).innerHTML = text;
};
const state = { roofs: [], records: [], mode: "auto", form: {}, brief: "", errors: [], sessions: new Map(), active: null, design: null,
  reviewCount: 0, runTab: "live", resultTab: "结论", filter: "all", theme: localStorage.getItem("gz-theme") ?? "system", folds: new Set() };
let scene, replay, routeEpoch = 0, previewEpoch = 0, recordsEpoch = 0, polling = false, statusPolling = false, finishing = false, briefTimer;
const issuedProjects = new Set();
const reviewIntro = "设计已导出。第 9 步：独立审核，约 1 分钟。右侧会切到审核会话；审核员保存意见时，需要你点一次「本会话允许」。";
const statusLabels = { completed: "完成", running: "进行中", issue: "有问题", not_started: "未开始", skipped: "跳过" };
const classes = { completed: "ok", running: "run", issue: "bad", not_started: "idle", skipped: "idle" };
async function api(path, body) {
  const controller = globalThis.AbortController ? new AbortController() : null;
  const timer = controller && setTimeout(() => controller.abort(), body === undefined ? 30000 : 120000);
  try {
    const request = body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)};
    const response = await fetch('/api/' + path, {...request, signal:controller?.signal});
    const data = await response.json();
    if (!response.ok) throw new Error((data.errors ?? [data.error ?? data.detail ?? '本地请求未完成'])
      .map?.(e => typeof e === 'string' ? e : e.msg ?? show(e)).join('；') ?? '本地请求未完成');
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('本地服务响应较慢，请稍后重试。');
    if (error instanceof SyntaxError) throw new Error('本地服务返回格式异常，请重试。');
    if (error instanceof TypeError) throw new Error('暂时连不上本地服务，请确认光筑仍在运行后重试。');
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
const guarded = (fn) => (...args) => Promise.resolve().then(() => fn(...args)).catch((error) => notice(error.message));
function notice(text) {
  $("notice").textContent = text;
  $("notice").hidden = false;
  clearTimeout(notice.timer);
  notice.timer = setTimeout(() => {
    $("notice").hidden = true;
  }, 7e3);
}
const recentSort = (rows) => rows.sort((a, b) => (b.ended_at ?? b.started_at ?? "").localeCompare(a.ended_at ?? a.started_at ?? ""));
async function loadRecords(owns = () => true) {
  const epoch = ++recordsEpoch, data = await api("runs");
  if (epoch !== recordsEpoch || !owns()) return false;
  state.records = recentSort(data.runs ?? []);
  return true;
}
const roof = () => state.roofs.find((r) => r.id === state.form.template) ?? state.roofs[0];
const geo = (r) => r?.geometry ?? r?.project?.roof ?? {};
const pill = (text, cls = "idle") => `<span class="pill ${cls}">${esc(text)}</span>`;
const btn = (text, action, cls = "", disabled = false) => `<button class="btn ${cls}" data-action="${action}" ${disabled ? "disabled" :
  ""}>${esc(text)}</button>`;
const empty = (text) => `<div class="empty muted">${esc(text)}</div>`;
const fact = (label, value, unit = "") => `<div class="fact"><span>${esc(label)}</span><b>${valueMarkup(value, unit)}<small>${esc(unit)}</small></b></div>`;
const tabNames = { live: "实时输出", all: "全部", pass: "四步全过", fail: "未通过", review: "独立审核", evaluation: "评测",
  light: "浅色", dark: "深色", system: "跟随系统", heat: "遮挡热力", string: "组串", wiring:'串联布线', phase: '分期', wind: '风荷载' };
const tabs = (values, current, key) => `<div class="seg">${values.map((v) =>
  `<button data-${key}="${esc(v)}" aria-pressed="${current === v}">${esc(key === "scene-mode" && v === "light" ? "光影" : tabNames[v] ??
    v)}</button>`).join("")}</div>`;
function head(title, subtitle, actions = "", step = 0) {
  return `<div class="head"><div><h1>${title}</h1><p>${esc(subtitle)}</p></div>${actions || `<ol class="stepper">${["选屋顶", "填条件", "运行", "结果"].map((s, i) =>
    `<li class="${i + 1 === step ? "on" : i + 1 < step ? "done" : ""}"><b>${i + 1}</b>${s}</li>`).join("")}</ol>`}</div>`;
}
function selectRoof(id) {
  state.parkEdit = null;
  const r = state.roofs.find((x) => x.id === id);
  if (!r) return;
  state.form = {
    template: id,
    id: `${id}-${beijingTime(new Date(), "id")}`,
    text: "",
    keep: [],
    notes: "",
    maxRounds: 6,
    compare: geo(r).type !== 'metal',
    review: true,
    exportOn: true,
    prefer: "balanced",
    moduleId: 'trina-tsm-605neg19rc20',
    inverterModels: Object.fromEntries((state.inverters ?? []).map(r => [r.model, r.id])),
    tiltMin: "",
    tiltMax: ""
  };
  state.brief = "";
  state.recognized = "";
  state.unrecognized = false;
  state.errors = [];
}
// Codex review E1: the real run shipped with the app opens without a key: its result, 3D, AGH replay and proposal
const showcase = () => state.records.find((r) => r.showcase && r.project_id);
const showcaseLink = (text, cls = "btn sm ghost") => showcase() ? `<a class="${cls}" href="#result/${encodeURIComponent(showcase().project_id)}?run=${
  encodeURIComponent(showcase().run_id)}">${text}</a>` : "";
function recentRow(r) {
  return `<a class="item" href="#replay/${encodeURIComponent(r.run_id)}"><span><b>${esc(r.project_id ?? r.run_id)}</b>${r.showcase ? ' <span class="tag-demo">真实案例</span>' : ""}<small> ${esc(r.run_id)}</small>
  </span>${pill(r.verification?.passed ? "四步全过" : "未通过", r.verification?.passed ? "ok" : "bad")}<small>
  ${esc(beijingTime(r.ended_at ?? r.started_at, "short"))}</small></a>`;
}
// 任何 AGH 支持的服务商都能填 key；默认 DeepSeek 设计、Agnes 审核。
const OTHER_PROVIDERS = [["openai", "ChatGPT"], ["anthropic", "Claude"], ["google", "Gemini"], ["moonshot", "Kimi"], ["qwen", "通义千问"],
  ["zai", "智谱 GLM"], ["xai", "Grok"], ["openrouter", "OpenRouter"], ["minimax", "MiniMax"]];
const PROVIDER_NAMES = { deepseek: "DeepSeek", agnes: "Agnes", ...Object.fromEntries(OTHER_PROVIDERS) };
const KEY_LABELS = { agnes: "Agnes（默认审核）", deepseek: "DeepSeek（默认设计）", other: "其他模型" };
const hasModel = (pattern) => bridge.models.some((m) => pattern.test(m.id));
const otherModels = () => bridge.models.filter((m) => !/deepseek|agnes/i.test(m.id));
function keyChip(provider) {
  if (state.keySaving === provider || provider === "other" && state.keySaving && !["deepseek", "agnes"].includes(state.keySaving))
    return pill("正在验证…", "run");
  if (provider === "other") return otherModels().length ? pill(`已有 ${otherModels().length} 个可选`, "ok") : pill("可选", "idle");
  return hasModel(provider === "deepseek" ? /deepseek/i : /agnes/i) ? pill("已可用", "ok") : pill("没填", "idle");
}
function readiness() {
  const phase = setup.status?.phase, installed = setup.association?.installed;
  if (!state.status) return "正在连接光筑后台…";
  if (installed && phase === "failed") return `设计工具没准备好：${setup.status.error ?? "未知原因"}`;
  if (setup.error) return `设计工具没准备好：${setup.error}`;
  if (!state.status.agh?.connected || installed && ["unconfigured", "configuring", "waiting_workspace", "configuring_skill"].includes(phase))
    return "正在准备设计工具（第一次打开约 20 秒）…";
  if (!bridge.ready) return "正在连接 AGH…";
  if (!bridge.models.length) return "填好任意一家的 key 就能开始设计。";
  return `已就绪：设计用 ${state.designModel?.label ?? state.designModel?.id ?? "—"}，审核用 ${state.reviewModel?.label ?? state.reviewModel?.id ?? "—"}，可在填条件页更换。`;
}
const KEY_SHORT = { agnes: "Agnes", deepseek: "DeepSeek", other: "其他" };
// Codex review R04: once a model is usable the key bar folds to one line (「改 key」 opens it), leaving the height to the roof list
const slimKeys = () => bridge.models.length > 0 && !setupFailed() && !state.keysOpen && !state.keySaving;
function keyBar() {
  if (slimKeys()) return `<div class="keybar card slim"><b>模型 key</b>${["agnes", "deepseek", "other"].map((p) =>
    `<span class="kb-slim">${KEY_SHORT[p]} <span id="kb-chip-${p}">${keyChip(p)}</span></span>`).join("")}<p class="kb-state" id="kb-state">${
    keyState()}</p>${btn("改 key", "keys-open", "sm")}</div>`;
  return `<div class="keybar card"><div class="kb-head"><b>模型 key ${bridge.models.length ? btn("收起", "keys-close", "sm ghost") : ""}</b><span class="muted">只填一次，保存在本机，光筑不会把它发给别人</span></div>
  <div class="kb-fields">${["agnes", "deepseek", "other"].map((p) => `<label class="kb-field"><span>${KEY_LABELS[p]} <span id="kb-chip-${p}">${keyChip(p)}</span></span>
  <span class="kb-input">${p === "other" ? `<select id="kb-provider" aria-label="服务商">${OTHER_PROVIDERS.map(([value, name]) =>
    `<option value="${value}">${name}</option>`).join("")}</select>` : ""}<input type="password" data-key="${p}" autocomplete="off" spellcheck="false"
  placeholder="粘贴 key"><button class="btn sm primary" data-save-key="${p}">保存</button></span></label>`).join("")}</div>
  <p class="kb-state" id="kb-state">${keyState()}</p></div>`;
}
const setupFailed = () => setup.status?.phase === "failed" || !!setup.error;
const keyState = () => `<span>${esc(readiness())}</span>${setupFailed() ? btn("重试", "setup-retry", "sm") : ""}${bridge.models.length ? "" :
  showcaseLink("没有 key？先看一个真实案例 →", "kb-link")}`;
function updateKeyBar() {
  const bar = document.querySelector(".keybar"); // folds or opens by itself only while nothing is being typed into it
  if (bar && bar.classList.contains("slim") !== slimKeys() && !bar.contains(document.activeElement) &&
    ![...bar.querySelectorAll("input")].some((input) => input.value)) bar.outerHTML = keyBar();
  for (const p of ["agnes", "deepseek", "other"]) html(`kb-chip-${p}`, keyChip(p));
  const el = $("kb-state"); // redrawn only when it changes, so a click on 重试 is never lost to the once-a-second refresh
  if (el && (el.firstElementChild?.textContent !== readiness() || !!el.querySelector("button") !== setupFailed() || !!el.querySelector("a") !==
    !!(showcase() && !bridge.models.length))) el.innerHTML = keyState();
}
function startBlock() {
  if (setup.association?.installed && setupFailed()) return "设计工具没准备好，请在首页点重试";
  if (!bridge.ready) return "正在连接 AGH…";
  if (!state.designModel || state.mode === "auto" && state.form.review && !state.reviewModel) return "先在首页上方填一家模型的 key";
  if (setup.association?.installed && !setup.status?.ready) return "正在准备设计工具…";
  return "";
}
function saveKey(field) {
  const provider = field === "other" ? document.querySelector("#kb-provider")?.value : field;
  const input = document.querySelector(`[data-key="${field}"]`), key = input?.value.trim() ?? "";
  if (!key) throw new Error("先把 key 粘贴到框里");
  if (!bridge.ready) throw new Error("AGH 还在启动，稍等几秒再保存");
  input.value = "";
  state.keySaving = provider;
  state.keysOpen = true;
  bridge.send("gz.saveKey", { provider, key }, { keySave: provider });
  updateKeyBar();
}
function keySaved(message, request) {
  state.keySaving = null;
  if (message.type === "gz.keySaved") {
    notice(`${PROVIDER_NAMES[request.keySave] ?? "模型"} key 已保存`);
    if (setup.association?.installed) setup.recheck();
    else bridge.refresh();
  } else notice(message.message ?? "key 没能保存");
  updateKeyBar();
}
function newPage() {
  const r = roof(), g = geo(r);
  return `${head("新建设计", "选一栋屋顶，填好条件，Agent 在 AGH 里一次做完", "", 1)}${keyBar()}<div class="new-grid"><div class="new-left"><h3 class="sec">怎么跑这次设计</h3>
  ${modesMarkup()}
  ${roofChoices(r)}
  <div class="recent"><h3 class="sec">最近的设计 ${showcaseLink("看一个真实案例（不用 key）")}</h3><div class="list scroll">${state.records.filter((x) => !isReviewRecord(x) && !isEvaluation(x)).slice( 0,
    4 ).map(recentRow).join("") || empty("还没有设计记录")}</div></div></div>
  ${splitter("new")}${roofPreview(r, g)}</div>`;
}
function field(key, label, unit, min, max, placeholder = "不限") {
  return `<label class="field"><span>${label}</span><span class="inbox">
  <input data-field="${key}" type="number" step="any" min="${min}" max="${max}" value="${esc(state.form[key] ?? "")}" placeholder="${esc(placeholder)}"
    ${['tiltMin', 'tiltMax'].includes(key) && ['metal', 'pitched'].includes(geo(roof()).type) ? 'disabled' : ''}>
  <span>${unit}</span></span></label>`;
}
function formPage() {
  const r = roof(), f = state.form, defaults = r?.defaults ?? {};
  if (state.mode === "chat") return head("进入对话", r?.name ?? "", "", 2) +
    `<div class="form-grid"><p>需求请在右侧 AGH 里直接说</p>${splitter("form")}${briefMarkup(r, f)}</div>`;
  const toggle = (key, text) => `<label class="toggle ro"><span>${text}</span><input type="checkbox" data-field="${key}"
    ${key === 'compare' && geo(r).type === 'metal' ? 'disabled' : ''} ${f[key] ? "checked" : ""}></label>`;
  return `${state.parkEdit ? btn('保存园区条件并返回', 'park-settings-save') : ''}${head(
    '<a class="btn sm ghost" href="#new">← 选屋顶</a>填写条件',
    `${r?.name ?? ""} · ${state.mode === "auto" ? "一键模式" : "对话模式"}`,
    "",
    2
  )}<div class="form-grid"><div class="form-left scroll">
  <div class="card fcard"><h3>一句话需求 <small>必填，用你自己的话说</small></h3>
  <textarea class="area" data-field="text" rows="2" maxlength="200" placeholder="6 年内回本，留 1 米检修通道，别挡天窗">${esc(f.text)}</textarea>
  <p id="recognized" class="${state.unrecognized ? 'recognition-warning' : 'muted'}">${esc(state.recognized ?? "")}</p></div>
  ${requirementsMarkup(r, f)}
  ${factsMarkup(f)}
  ${optionsMarkup(defaults, f, toggle)}</div>
  ${splitter("form")}${briefMarkup(r, f)}</div>`;
}
async function preview() {
  if (state.mode === "chat") return;
  const epoch = ++previewEpoch;
  try {
    const data = await api("brief", formSpec(state.form, state.reviewModel));
    if (epoch !== previewEpoch) return;
    state.brief = data.brief;
    state.errors = data.errors ?? [];
  } catch (error) {
    if (epoch !== previewEpoch) return;
    state.brief = "";
    state.errors = [error.message];
  }
  if ($("brief-pre")) $("brief-pre").textContent = state.brief || "请补全有效条件";
  if ($("brief-errors")) $("brief-errors").textContent = state.errors.join("；");
}
function stepsMarkup(computed) {
  return computed.steps.map((s) => `<article data-step="${s.number}" class="step ${s.state}">
  <span class="ic">${s.state === "completed" ? "✓" : s.number}</span><div>
  <h4>${esc(s.title)}</h4><div class="det">${s.comparison ?? s.metrics.map((m) => `<span title="${esc(s.raw)}">${esc(m.label)}：${valueMarkup( m.value,
    m.label )}</span>`).join(" · ")}</div>${s.detail ? `<details><summary>查看说明</summary>${esc(s.detail)}</details>` : ""}${s.warnings.length ?
    `<div class="bad-text">${esc(s.warnings.map(show).join("；"))}</div>` : ""}${s.rounds?.length ? `<div class="rounds">${s.rounds.map((r) =>
    `<span class="${r.hard_failed === 0 ? "ok" : "fix"}">v${r.version} ${r.passed}/${r.total} · ${r.hard_failed === 0 ? "硬性全过" : r.failed.map((x) =>
      x.id).join("、")}</span>`).join("")}</div>` : ""}${s.children ? `<div class="muted">${s.children.map(esc).join(" / ")}</div>` : ""}</div>
  ${pill(s.statusLabel ?? statusLabels[s.state], classes[s.state])}</article>`).join("");
}
function checksMarkup(verification) {
  if (!verification) return empty("导出后从执行记录核对，实时步骤不是最终结论");
  return `<div class="checks4">${verification.checks.map((c) => `<div>${pill(c.stage, c.passed ? "ok" : "bad")}<small>${esc(c.reason)}</small>
  </div>`).join("")}</div>${verification.review?.requested ? `<p>${pill("独立审核：" + (verification.review.passed ? "通过" : "未通过"), verification.review.passed ?
    "ok" : "warn")} ${esc(verification.review.reason ?? "")}</p>` : ""}`;
}
function versionChain(result) {
  return `<div class="vchain">${(result?.versions ?? []).map((v) => `<button class="btn sm ${v.version === result.version ? "primary" :
    ""}" data-version="${v.version}" title="${esc(v.reason)}">v${v.version}${v.parent_version ? " ← " + v.parent_version : ""}</button>`).join("") ||
    "暂无版本"}</div>`;
}
function filesMarkup(result) {
  const files = result?.files?.files ?? result?.files ?? [];
  const items = Array.isArray(files) ? files : Object.entries(files).map(([name, sha256]) => ({ name, sha256 }));
  const report = result?.report, made = report?.files ?? [], name = (made.find((f) => f.name?.endsWith(".pdf")) ?? made[0])?.name;
  return `<div class="files">${items.map((f) => `<div><span>${esc(f.name ?? f.path)}</span><span title="${esc(f.sha256 ?? f.hash)}">${esc((f.sha256 ??
    f.hash ?? "").slice(0, 8))}</span></div>`).join("") || empty("尚无导出文件")}</div>${report ?
    `<div class="report-card"><div><b>方案书${report.regenerated ? " · 补生成" : ""}</b><small>${esc([name, report.error ?? report.hint].filter(Boolean)
      .join(" · "))}</small></div>${made.length ? btn("打开方案书", "open-report", "primary") : ""}</div>` : ""}`;
}
function usageMarkup(usage, archived = false, live = false) {
  const u = usageSummary(usage, { live }), requests = show(u.model_requests) + (u.model_requests === null && u.recorded_model_calls !== null ?
    `（已记费 ${u.recorded_model_calls} 次）` : "");
  const money = u.costs.map((c) => `${c.currency} ${Number((c.micros / 1e6).toPrecision(3))}`).join("；") || "未提供";
  const detail = [archived ? "完整会话归档汇总（非游标统计）" : "当前会话实时投影", "token含标题等已记录用量；推理是输出子集，不重复相加", "AGH估算，非实付；0不表示免费", `费用缺项：${show(u.missing_costs)}`];
  return `<details class="muted"><summary>用时 ${u.elapsed_seconds === null ? "未提供" :
    u.elapsed_seconds.toFixed(1) + " 秒"} · 模型请求 ${esc(requests)} · token ${show(u.total_tokens)} · 费用 ${esc(money)}${u.costs.length && !u.billing_complete ?
    "（已知小计）" : ""}（AGH 估算）</summary><div class="play-controls">${[["输入", "input"], ["输出", "output"], ["读缓存", "cacheRead"], ["写缓存", "cacheWrite"], [ "推理",
      "reasoning" ]].map(([label, key]) => `<span>${label}：${show(u.tokens[key])}</span>`).join("")}<span>${esc(detail.join("；"))}</span></div></details>`;
}
function replayUsage(session) {
  const r = state.replayRun, usage = r.usage_by_session?.[session] ?? r.usage;
  return usageMarkup(usage?.session_id === session ? usage : null, true);
}
function sessionComputed(s) {
  return s?.fallback ?? withVerifiedReview(computeSteps(s?.nodes ?? [], {run:s?.run ?? {}, op:s?.op ?? "idle",
    approvals:s?.approvals ?? [], now:Date.now(), selected_version:s?.result?.selected_version,
    versions:s?.result?.versions ?? s?.compareVersions}), s);
}
function activeComputed() {
  const design = state.sessions.get(state.design) ?? (state.active === "file-progress" ? state.sessions.get(state.active) : null),
    c = sessionComputed(design), review = state.sessions.get(design?.reviewSession);
  if (!review || c.steps[8].state === "completed") {
    if (!review && c.steps[8].state === "not_started") c.steps[8].statusLabel = "独立审核：未开始";
    return c;
  }
  const r = sessionComputed(review), numbers = [2, 6, 8, 9], names = ["读项目", "复核分析", "发电复核", "保存审核意见"];
  const summary = resolvedTools(review.nodes).findLast((n) => n.name === "gz_project_summary");
  if (summary?.status === "completed" && !summary.pending && summary.data?.ok === true) r.steps[1].state = "completed";
  const step = c.steps[8];
  step.children = numbers.map((n, i) => names[i] + (r.steps[n - 1].waiting ? "（等你批准）" : "：" + statusLabels[r.steps[n - 1].state]));
  step.state = design.reviewFailure ? "issue" : "running";
  step.statusLabel = design.reviewFailure ? "审核未通过" : review.op === "running" ? "独立审核中" : "正在核对审核记录";
  return c;
}
function runPage() {
  const s = state.sessions.get(state.design), native = state.sessions.get(state.active), pid = s?.project ?? state.form.id,
    review = state.sessions.get(s?.reviewSession), c = activeComputed(), waiting = sessionComputed(native).steps.find((x) => x.waiting),
    count = c.steps.filter((x) => ["completed", "skipped"].includes(x.state)).length;
  const label = !s ? "未开始" : s.reviewPreparing || state.starting && state.final ? "准备独立审核" :
    review?.op === "idle" && !s.reviewFailure && !s.verification?.review?.passed ? "正在核对审核记录" : waiting ? "等你批准" : review?.op === "running" ? "独立审核中" :
    c.suggestions.length && c.stopped ? "需要你决定" : s?.verification ?
    s.verification.passed ? "已完成" : "核对未通过" : s?.op === "running" ? "运行中" : "已停下";
  let banner = waiting ? `<div class="banner warn"><b>${waiting.title}等你批准</b><span>在右侧原生卡选择${waiting.number === 10 ? "「仅允许这次」" : "「本会话允许」"}</span>
  <span class="count">${waiting.countdown ?? "—"} 秒</span></div>` : "";
  if (!waiting && c.suggestions.length && c.stopped && !s?.ended) banner = `<div class="banner bad"><b>检查点 A · 做不到，需要你决定</b>
  <div class="sugs">${c.suggestions.map((x, i) => `<button class="btn sm" data-suggestion="${i}" title="${esc(x.text)}">按建议${x.number}继续
  </button>`).join("")}${btn("到此为止", "checkpoint-stop", "sm ghost")}</div><details><summary>建议原文</summary>${c.suggestions.map((x) =>
    `<p>${x.number} ${esc(x.text)}</p>`).join("")}</details></div>`;
  if (!banner && !s?.review && s?.op === "idle" && s.verification) banner = `<div class="banner ${s.verification.passed ? "ok" : "bad"}"><b>执行记录核对
  </b>${(s.verification.checks ?? []).map((check) => pill(check.stage + "：" + (check.passed ? "通过" : "未通过"), check.passed ? "ok" :
    "bad")).join("")}${s.verification.review?.requested ? pill("独立审核：" + (s.verification.review.passed ? "通过" : "未通过"), s.verification.review.passed ?
    "ok" : "bad") : ""}</div>`;
  const recovery = state.active === state.design && !state.navigation ? recoveryDescription(s, c) : null;
  if (recovery) banner = `<div class="banner warn"><b>${esc(recovery.banner)}</b>${recovery.actions.map((a, i) =>
    `<button class="btn sm" data-recovery="${i}" ${s.recovering ? "disabled" : ""}>${esc(a.label)}</button>`).join("")}</div>`;
  if (s?.reviewBanner && !waiting) banner = `<div class="banner warn"><b>${esc(s.reviewBanner)}</b>${s.reviewFailure ?
    btn("重新审核", "review-retry", "sm", state.reviewCount >= 2 || state.starting) + btn("先看结果", "see-result", "sm") : ""}</div>`;
  if (waiting) state.runTab = "live";
  if (banner) banner = banner.replace('class="banner ', 'aria-live="polite" data-key="banner" class="banner ');
  if (bridge.fallback) banner = `<div aria-live="polite" data-key="banner" class="banner warn">
  <span>传话未连接。复制任务书，粘贴到右侧 AGH 输入框并发送；文件进度每秒刷新。</span>${btn("复制任务书", "copy", "sm")}</div>`;
  return `${head(
    `运行 ${pill(label, waiting ? "warn" : s?.verification?.passed ? "ok" : "run")}`,
    `${pid ?? ""}${s?.review ? " · 独立审核" : ""}`,
    `${btn("在 AGH 中打开", "open-agh")}${btn("停止", "cancel", "", !native || native.op !== "running")}
  ${state.active === state.design && !state.navigation && s?.op === "idle" &&
      (s.finishError || s.verification?.passed === false) ? btn("重新核对", "finish-retry") :
      ""}${s?.result?.version || state.final?.result?.version ? `<a class="btn primary" href="#result/${encodeURIComponent(pid)}">查看结果 →
  </a>` : ""}`
  )}<div data-key="progress" class="progress">
  <div class="lbl"><b>${count} / 10 步骤</b><span>${s?.id ? esc(s.id.slice(0, 8)) : "等待会话"}</span></div><div class="bar">
  <i style="width:${count * 10}%"></i></div></div>${banner}<div data-key="run-grid" class="run-grid"><div class="col"><h3 class="sec">设计流水线 ${state.design &&
    state.active !== state.design ? btn("回设计会话", "design-session", "sm") : s?.reviewSession ? btn( "审核会话",
      "review-session", "sm" ) : ""}</h3><div class="steps scroll">${stepsMarkup(c)}</div>${parkQueue.queue?.items.length ? splitter("queue") + queueMarkup(parkQueue.queue) : ""}</div>${
    splitter("run")}<div class="col"><div class="out-head">${tabs( ["live",
      "产物", "核对"], state.runTab, "run-tab" )}<span class="muted">基于 Agnes Harness</span></div>${state.runTab === "live" ?
    '<div class="frame"><div class="frame-hint">设计工具选「本会话允许」；导出只选「仅允许这次」。</div><div id="iframe-slot"></div></div>' :
    `<div class="prods">${state.runTab === "产物" ? versionChain(s?.result ?? state.final?.result) + filesMarkup(s?.result ?? state.final?.result) :
    checksMarkup(s?.verification ?? state.final?.verification)}</div>`}</div></div>${usageMarkup(
      native?.archivedUsage ?? native?.usage, Boolean(native?.archivedUsage), native?.op === "running")}`;
}
// Codex review R10: a roof load nobody confirmed is a placeholder, so it is never called 核定
const loadWording = (text, project) => project?.roof?.load_verified ? text : String(text ?? "").replace("屋面核定值", "屋面示意值（待结构核定）");
function resultPanel(result) {
  const summary = result.metrics ?? result.summary ?? {}, economics = summary.economics ?? {}, y = summary.yield_kwh ?? summary.yield ?? {};
  if (state.resultTab === "结论") return conclusionMarkup(result, summary, economics, y);
  if (state.resultTab === "三方案") return comparisonMarkup(result);
  if (state.resultTab === "开工前") return siteMarkup(result);
  if (state.resultTab === "规则") {
    const rules = Array.isArray(result.rules) ? result.rules : result.rules?.items ?? [];
    return `<div class="rulelist">${[...rules].sort((a, b) => Number(b.status === "fail") - Number(a.status === "fail")).map((r) =>
      `<div title="${esc(rawValue({ value: r.value, limit: r.limit }))}"><b>${esc(r.id)}</b><span>${esc(loadWording(r.name_zh ?? r.name, result.project))}</span>${pill( show(r.status),
        r.status === "pass" ? "ok" : r.status === "fail" ? r.level === "hard" ? "bad" : "warn" : "idle" )}</div>`).join("") || empty("未提供完整规则清单")}</div>
        <details>
    <summary>发电复核 · v${result.version}</summary><p class="mono">${valueMarkup(result.crosscheck?.specific_yield_kwh_kwp,"kWh/kWp")}</p>
    ${(result.crosscheck?.groups ?? []).map(g => `<p>坡面 ${esc(g.group[0])} · 倾角 ${esc(g.group[1])}° · 朝向 ${esc(g.group[2])}°：
    ${valueMarkup(g.per_kw,"kWh/kWp")}</p>`).join("")}
    ${result.crosscheck?.total_kwh ? `<p>合计：${valueMarkup(result.crosscheck.total_kwh,"kWh")}</p>` : ""}
    <p>${esc(result.crosscheck?.note ?? "未提供")}</p></details>`;
  }
  if (state.resultTab === "审核") return (result.reviews ?? []).map((r) => `<section class="fcard"><h3>${esc(show(r.verdict))} · v${r.version}</h3>
  <small>${esc(r.reviewer_model)}</small>${(r.findings ?? []).map((f) => `<div class="why finding">${pill(show(f.severity), f.severity === "high" ? "bad" :
    f.severity === "low" ? "idle" : "warn")}<b>${esc(f.item)}</b><p><span class="muted">依据：</span>${esc(f.evidence)}</p>
    <p><span class="muted">建议：</span>${esc(f.suggestion)}</p></div>`).join("")}</section>`).join("") || empty("独立审核：未开始");
  return filesMarkup(result) + (result.selected_version ? btn("打开导出文件夹", "open-exports") : "") + btn("打开执行记录", "open-run");
}
function resultTitle(result) {
  return `${result.project_id} · ` + (result.version == null ? "暂无设计版本" : result.selected_version
    ? `v${result.version}${result.version === result.selected_version ? " · 已导出版本" : "（历史版本）"}`
    : `未导出·${state.resultExplicit ? "查看版本 " : result.display_passed ? "最后通过" : "最新"}v${result.version}`);
}
function resultPage(result) {
  if (result.version == null) return head("设计结果", resultTitle(result), '<a class="btn" href="#records">设计记录</a>') + empty("尚无设计版本");
  return `${head(
    "设计结果",
    resultTitle(result),
    `<div class="actions"><a class="btn" href="#records">设计记录</a>${state.resultRun ? `<a class="btn" href="#replay/${encodeURIComponent(state.resultRun)}">看 AGH 回放</a>` :
      ""}${result.selected_version && showcase()?.run_id !== result.run_id ? btn("打开导出文件夹", "open-exports") : ""}</div>`
  )}<div class="res-grid"><div class="scene-layout">
  <div class="scene-toolbar">${tabs(["light", "heat", "string", "wiring", "phase", "wind"], state.sceneMode ?? "light", "scene-mode")}${tabs(
    ["冬至", "春分", "夏至"], state.season ?? "冬至",
    "season" )}</div>${wiringPanel(result, state.wireString, state.sceneMode)}<div id="scene" class="stage"></div>
    <button id="scene-retry" class="btn sm" data-action="scene-retry" hidden>重新加载3D</button>${windSummary(result)}<div class="sun-controls">
  <input id="sun-time" type="range" min="6.5" max="17.5" step="0.1" value="${state.hour ?? 12}" aria-label="北京时间"><span id="sun-readout">
  北京时间 ${timeLabel(state.hour ?? 12)}</span><span id="scene-inspect"></span><span class="legend" id="heat-legend"
  ${state.sceneMode === 'heat' ? '' : 'hidden'} title="年度遮挡损失，不随时间滑块变化">
  <i style="background:linear-gradient(90deg,${HEAT_COLORS.join(",")})"></i>年度损失 0% → ${(result.scene?.shading?.summary?.threshold_pct ??
    8) / 2}% → ${result.scene?.shading?.summary?.threshold_pct ?? 8}%+</span></div></div>${splitter("result")}<aside class="card res-right">${tabs( ["结论", "三方案", "规则", "审核",
      "开工前", "文件"], state.resultTab, "result-tab" )}<div id="result-panel" class="scroll">${resultPanel(result)}</div></aside></div>`;
}
function windSummary(result) {
  const wind = result.scene?.wind;
  if (!wind || wind.version !== result.version) return '<p class="muted">此版本未计算风荷载，旧记录不代表抗风已通过。</p>';
  const worst = wind.zones[wind.worst_zone];
  const capacity = result.project.roof.load_capacity_kn_m2;
  const loadStatus = worst.load_kn_m2 <= capacity ? '通过' : '未通过';
  const faceLoads = result.project.roof.type === 'pitched' ? (result.rules?.items ?? []).filter(r => r.id === 'L01') : null;
  const loadText = faceLoads ? faceLoads.map(r => `P${r.plane} ${show(r.value)} / ${show(r.limit)} kN/m² · ${r.status}`).join('；') :
    `最不利${worst.label} ${worst.load_kn_m2.toFixed(3)} kN/m²；屋面容量 ${capacity} kN/m²。`;
  const status = faceLoads ? faceLoads.length ? faceLoads.every(r => r.status === 'pass') ? '通过' : '未通过' : '未核对' : loadStatus;
  const anchored = Boolean(wind.anchor_count);
  const rows = Object.values(wind.zones).map(r => `<tr><td>${esc(r.label)}</td><td>${r.modules}</td>
    <td>${r.ballast_blocks}</td><td>${Number(r.ballast_kg).toFixed(0)}</td><td>${Number(r.load_kn_m2).toFixed(3)}</td>
    ${anchored ? `<td>${r.anchors ?? 0}</td>` : ''}</tr>`).join('');
  const anchorText = anchored ? `<p>${wind.anchored_modules}块组件的支架压块后超过屋面承重，改用${wind.anchor_count}个锚栓固定。
    ${esc(wind.anchor_note)}</p>` : '';
  return `<details class="card wind-result"><summary>风荷载 · ${esc(wind.city.city)} · ${wind.basic_pressure_kpa}kPa（示意）</summary>
    <p>${esc(wind.note)}</p><p>${esc(wind.city.selection)}；距市中心${wind.city.distance_km.toFixed(1)}km</p>
    <p><b>L01 ${status}</b> · ${esc(loadText)}</p>${anchorText}
    <table><tr><th>分区</th><th>组件数(块)</th><th>压块数(个)</th><th>压块质量(kg)</th><th>区荷载(kN/m²)</th>
    ${anchored ? '<th>锚栓(个)</th>' : ''}</tr>${rows}</table>
    <p>夹具需求${wind.clamp_required}个；实际布点${wind.clamp_count}个；未通过组件${wind.clamp_failed}块。</p>
    <p>${esc(wind.missing)}</p></details>`;
}
function recordsPage() {
  const stats = runStats(state.records.filter((r) => !r.showcase)), rows = state.records.filter((r) => isEvaluation(r) === (state.filter === "evaluation")),
    filtered = rows.filter((r) => state.filter === "all" || state.filter === "evaluation" || state.filter === "pass" && !isReviewRecord(r) &&
    recordPassed(r) || state.filter === "fail" && !recordUnverified(r) && !recordPassed(r) || state.filter === "review" && isReviewRecord(r));
  return `${head("设计记录", "全部真实运行，失败记录也保留", btn("刷新", "records-refresh"))}${tabs( ["all", "pass", "fail", "review", "evaluation"], state.filter,
    "filter" )}<div class="stats">${[["全部", stats.all], ["四步全过", stats.passed], ["未通过", stats.failed], ["独立审核", stats.review]].map(([t, n]) =>
    `<div class="card stat">
    <span>${t}</span><b>${n}</b></div>`).join("")}</div><div class="rec-list scroll">${filtered.map((r) => `<article class="rec">
  <span>${pill(recordUnverified(r) ? "审核未核对" : (isReviewRecord(r) ? "审核" : "") + (recordPassed(r) ? "通过" : "未通过"), recordUnverified(r) ? "idle" :
    recordPassed(r) ? "ok" : "bad")}</span><div><h4>${esc(r.project_id ?? r.run_id)}${r.showcase ? ' <span class="tag-demo">真实案例 · 随安装包</span>' : ""}</h4>
  <p>${esc(isReviewRecord(r) && r.parent_run_id ? "审核·" + r.parent_run_id : r.run_id)}</p>
  ${r.module_model ? `<small>组件：${esc(r.module_model)}</small>` : ''}</div>
  <span class="mono">${esc(beijingTime(r.ended_at ?? r.started_at))}</span><span>${isReviewRecord(r) ? "独立审核" :
    (r.verification?.checks?.filter((x) => x.passed).length ?? 0) + "/4"}</span><div class="actions">
  <a class="btn sm" href="#replay/${encodeURIComponent(r.run_id)}">回放</a>${r.display_version || r.selected_version ?
    `<a class="btn sm" href="#result/${encodeURIComponent(r.project_id)}?run=${encodeURIComponent(r.run_id)}">结果</a>` : ""}
  ${r.report?.files?.length ? `<button class="btn sm" data-open-report="${esc(r.run_id)}">打开方案书</button>` : ""}${r.can_report ?
    `<button class="btn sm" data-report="${esc(r.run_id)}">${r.report?.files?.length ? "重新生成方案书" : "生成方案书"}</button>` : ""}</div></article>`).join("") ||
    empty("没有符合条件的记录")}</div>`;
}
async function render() {
  if (location.hash === "#setup") {
    location.hash = "#new";
    return;
  }
  if (state.route === "run" && (location.hash.slice(1).split("?")[0] || "new") === "run") return updateRun();
  const epoch = ++routeEpoch;
  const [path, query] = (location.hash.slice(1) || "new").split("?"), [page, id] = path.split("/");
  state.route = page;
  if (page !== "new") state.keysOpen = false;
  $("agh-dock").classList.add("parked");
  const navPage = page === 'park-legacy' ? 'park' : page;
  document.querySelectorAll(".navtabs a").forEach((a) => a.setAttribute("aria-current", a.hash === "#" + navPage ? "page" : "false"));
  let content;
  if (page === "new") content = newPage();
  else if (page === "form") {
    const form = state.form, original = form.id, base = `${form.template}-${beijingTime(new Date(), 'id')}`;
    let candidate = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(original ?? '') ? original : base, suffix = 1;
    while (issuedProjects.has(candidate) || (await api('projects/' + encodeURIComponent(candidate) + '/exists')).exists) {
      candidate = base + (suffix === 1 ? '' : '-' + suffix);
      suffix++;
    }
    if (epoch !== routeEpoch || form !== state.form || form.id !== original) return;
    form.id = candidate;
    content = formPage();
    if (state.mode === "auto") setTimeout(() => preview(), 0);
  } else if (page === "run") content = runPage();
  else if (page === "roof") content = roofEditorPage(state.roofs.find((x) => x.collection === "mine" && x.id === decodeURIComponent(id ?? "")));
  else if (page === "records") content = recordsPage();
  else if (page === "park-legacy") {
    state.parkData = await api("park");
    content = parkPage();
  }
  else if (page === 'park') {
    try {
      await parkView.load();
      parkView.roofs = state.roofs;
      content = parkView.html();
    } catch (error) {  // an unreadable park says why on the page itself instead of the tab not opening
      if (epoch !== routeEpoch) return;
      content = head('园区', '') + empty('园区没能打开：' + error.message) + btn('重试载入', 'result-retry');
    }
  }
  else if (page === "result") {
    const params = new URLSearchParams(query), run = params.get("run"), suffix = params.has("version") ? "?version=" + params.get("version") : "";
    let result;
    try {
      result = run ? (await api('runs/' + encodeURIComponent(run) + suffix)).result :
        await api('projects/' + encodeURIComponent(decodeURIComponent(id)) + '/result' + suffix);
    } catch (error) {
      if (epoch !== routeEpoch) return;
      result = {version:null, project_id:decodeURIComponent(id), load_error:error.message};
    }
    if (epoch !== routeEpoch) return;
    state.resultRun = run;
    state.resultExplicit = params.has("version");
    state.result = result;
    state.wireString = '';
    content = resultPage(result) + (result.load_error ? empty(esc(result.load_error)) + btn('重试载入', 'result-retry') : '');
  } else if (page === "replay") {
    state.replayRun = await api("runs/" + encodeURIComponent(decodeURIComponent(id)));
    content = `${head("运行回放", id, '<a class="btn" href="#records">返回记录</a>')}<div class="play-controls">${btn("播放", "play")}${btn( "暂停",
      "pause" )}<input id="replay-seek" type="range" min="0" value="0" aria-label="回放位置"><span id="replay-position"></span></div><div class="run-grid">
    <div id="replay-steps" class="steps scroll"></div>${splitter("run")}<div id="replay-host" class="frame scroll"></div></div>
    <div id="replay-usage">${replayUsage(state.replayRun.run?.session)}</div>`;
  } else {
    location.hash = "#new";
    return;
  }
  if (epoch !== routeEpoch) return;
  scene?.dispose();
  replay?.dispose();
  scene = replay = null;
  $("view").innerHTML = `<section class="page${page === "new" ? " home" : ""}">${content}</section>`;
  if (page === "roof") mountRoofEditor({ post: api, notice, saved: roofSaved });
  if (page === 'park') parkView.mount($('view').querySelector('.page'));
  if (page === "result" && state.result.version != null) mountScene();
  if (page === "replay") {
    const r = state.replayRun, choices = replayChoices(r), reviewOptions = { review: { enabled: true, mode: "independent" } };
    const reviewSession = r.run?.review_session_id, reviewRows = resolvedTools(r.timeline?.nodes ?? []).filter((n) => n.session === reviewSession);
    const record = toolResult(reviewRows, "gz_record_review"), completion = reviewRows.findLast((n) =>
      n.name === "gz_record_review" && !n.pending && n.data?.ok === true);
    const proof = {id:r.run?.session, result:r.result, verification:r.verification, reviewRecord:record, reviewSession,
      reviewCompletedAt:completion?.ended_at, timeline:r.timeline};
    document.querySelector(".play-controls").insertAdjacentHTML("afterbegin", `<label>原生会话
      <select id="replay-session" aria-label="回放会话">${choices.map((c) =>
      `<option value="${esc(c.id)}">${c.label} · ${esc(c.id)}</option>`).join("")}</select></label>`);
    replay = createReplay($("replay-host"), { timeline: r.timeline, session: r.run?.session, runOptions: isReviewRecord(r.run) ? reviewOptions :
      r.run_options ?? {}, reviewCompletedAt:completion?.ended_at,
      sessionOptions: Object.fromEntries(choices.filter((c) => c.label === "独立审核").map((c) => [c.id, reviewOptions])), onSteps: (c, context) =>
      html("replay-steps", stepsMarkup(withVerifiedReview(c, proof, context))), onCursor: (i, total) => {
      if ($("replay-seek")) {
        $("replay-seek").max = Math.max(0, total);
        $("replay-seek").value = i;
        $("replay-position").textContent = `${i} / ${total}`;
      }
    } });
  }
  requestAnimationFrame(placeFrame);
}
function patchChildren(parent, fresh) {
  const identity = (node) => node.nodeType === 1 ? [node.tagName, node.id || node.dataset.key || node.dataset.step ||
    node.dataset.action || node.dataset.runTab || (node.dataset.version ? "version" + node.dataset.version : "") ||
    (node.dataset.suggestion != null ? "suggestion" + node.dataset.suggestion : "") ||
    (node.dataset.recovery != null ? "recovery" + node.dataset.recovery : "") || node.className].join(":") : "text";
  const pool = [...parent.childNodes], used = new Set();
  for (const next of [...fresh.childNodes]) {
    const old = pool.find((node) => !used.has(node) && identity(node) === identity(next));
    const node = old ?? next.cloneNode(true);
    if (old) {
      if (old.nodeType === 3) {
        if (old.nodeValue !== next.nodeValue) old.nodeValue = next.nodeValue;
      } else {
        for (const attr of [...old.attributes]) if (attr.name !== "open" && !next.hasAttribute(attr.name)) old.removeAttribute(attr.name);
        for (const attr of [...next.attributes]) if (attr.name !== "open" && old.getAttribute(attr.name) !== attr.value)
          old.setAttribute(attr.name, attr.value);
        patchChildren(old, next);
      }
    }
    const anchor = parent.childNodes[used.size];
    if (anchor !== node) parent.insertBefore(node, anchor ?? null);
    used.add(node);
  }
  for (const old of pool) if (!used.has(old)) old.remove();
}
function updateRun() {
  const fresh = document.createElement("section");
  fresh.className = "page";
  fresh.innerHTML = runPage();
  const page = $("view").firstElementChild;
  if (page) patchChildren(page, fresh);
  else $("view").append(fresh);
  placeFrame();
}
function mountScene() {
  if (!$('scene')) return;
  if ($('scene-retry')) $('scene-retry').hidden = true;
  scene = createScene($("scene"), { onSun: (angles) => {
    if ($("sun-readout")) $("sun-readout").textContent = `北京时间 ${timeLabel(state.hour ??
      12)} · 高度 ${angles.altitude.toFixed(1)}° · 方位 ${angles.azimuth.toFixed(1)}°`;
  }, onInspect: (value) => {
    if ($("scene-inspect")) $("scene-inspect").textContent = value ? value.module + " · " + (value.string?.id ?? "未分串") : "";
  }, onSelectString:id => {
    state.wireString = id;
    if ($('wire-string')) $('wire-string').value = id;
    if ($('wire-focus')) $('wire-focus').disabled = !id;
    html('wire-details', wiringDetails(state.result, id));
  }, onUnavailable:() => {
    if ($('scene-retry')) $('scene-retry').hidden = false;
  } });
  scene.setData(state.result.scene);
  scene.setTheme(document.documentElement.dataset.theme);
  updateSun();
  scene.setMode(state.sceneMode ?? "light");
  scene.selectString(state.wireString ?? '');
}
function updateSun() {
  scene?.setSun(`${(new Date()).getFullYear()}-${{ "冬至": "12-21", "春分": "03-20", "夏至": "06-21" }[state.season ?? "冬至"]}`,
    Number(state.hour ?? 12));
}
function placeFrame() {
  const slot = $("iframe-slot"), dock = $("agh-dock");
  dock.classList.toggle("parked", !slot);
  if (slot) {
    const r = slot.getBoundingClientRect();
    Object.assign(dock.style, { left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px" });
  }
}
function theme() {
  const effective = state.theme === "system" ? matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light" : state.theme;
  document.documentElement.dataset.theme = effective;
  localStorage.setItem("gz-theme", state.theme);
  scene?.setTheme(effective);
  bridge.setTheme(effective);
}
function settings() {
  html("settings-content", `<p>${bridge.ready ? "AGH 已连接" : "等待 AGH 连接"}</p><h3>主题</h3>${tabs(["light", "dark", "system"], state.theme, "theme")}<h3>设计模型</h3>
  ${modelSelect("design-model", "", state.designModel)}<h3>审核模型</h3>${modelSelect("review-model", "", state.reviewModel)}
  <p class="muted">任何填了 key 的模型都能设计或审核。DeepSeek 实际运行经验：Pro 每次约 0.1–0.3 元，Flash 约 0.03 元；并非收费表，实际费用以各家账单为准。</p><h3>
  可用模型</h3><div class="model-list">${bridge.models.map((m) => `<p><b>${esc(m.label)}</b><br><span class="mono">${esc(m.id)}</span></p>`).join("") ||
    "尚未收到模型清单"}</div>${btn("在浏览器中打开 AGH", "open-agh")}`);
}
function connectionLabel() {
  const block = state.status && state.status.agh?.connected ? startBlock() : "正在启动";
  $("connection").textContent = block ? block.replace(/^先在首页上方/, "") : "已就绪 · 设计用 " + (state.designModel?.label ?? state.designModel?.id ?? "");
}
async function checkConnection() {
  if (statusPolling) return;
  statusPolling = true;
  try {
    state.status = await api("status");
    setAghOrigin(state.status.agh?.url);
    await setup.poll();
    bridge.setAvailable(!setup.checking && state.status.agh?.connected === true);
    setup.advance();
  } catch {
    state.status = null;
  } finally {
    statusPolling = false;
    connectionLabel();
    updateKeyBar();
    gateStart();
  }
}
function gateStart() {
  const startButton = document.querySelector('[data-action="start"]'), block = startBlock();
  if (startButton) {
    startButton.disabled = !!block;
    startButton.textContent = block || (state.mode === "chat" ? "进入对话 →" : "开始自动设计 →");
  }
}
function loadComparisonReasons(s) {
  const compare = resolvedTools(s.nodes).findLast(n => n.name === 'gz_compare_options');
  const project = s.project, generation = s.generation ?? 0;
  const key = JSON.stringify([project, generation, compare?.tool_use_id, compare?.seq, compare?.result_seq, compare?.args_json, compare?.data]);
  if (s.review || state.design !== s.id || s.compareKey === key) return;
  s.compareKey = key;
  s.compareVersions = null;
  if (compare?.status !== 'completed' || compare.pending || compare.isError || compare.data?.ok !== true) return;
  if (compare.args_json?.project_id !== project || !Number.isInteger(compare.data.base_version) || compare.data.base_version < 1) return;
  const owns = () => state.design === s.id && state.sessions.get(s.id) === s && s.project === project &&
    (s.generation ?? 0) === generation && s.compareKey === key;
  api('projects/' + encodeURIComponent(project) + '/result?version=' + compare.data.base_version).then(data => {
    if (!owns() || data.project_id !== project) return;
    s.compareVersions = Array.isArray(data.versions) ? data.versions : [];
    if (state.route === 'run') updateRun();
  }).catch(() => {});
}
function resumeSession(s) {
  if (s.op === "running") return;
  s.generation = (s.generation ?? 0) + 1;
  s.turnStart = s.nodes.length;
  Object.assign(s, {op:"running", ended:false, verification:null, result:null, reviewRecord:null, reviewSession:null,
    reviewCompletedAt:null, userStopped:false, reviewBanner:null, reviewFailure:null, reviewPreparing:false, archivedUsage:null});
  if (!s.review) {
    if (state.startRequest?.review && state.startRequest.designId === s.id) {
      state.starting = false;
      state.startRequest = null;
    }
    state.final = null;
    state.result = null;
  }
}
const bridge = new Bridge($("agh"), async (message, request) => {
  if (request?.keySave) return keySaved(message, request);
  if (request?.setup) return guarded(() => setup.receive(message, request))();
  if (request?.setupSettings && message.type === "gz.error") return notice(message.message);
  if (message.type === "gz.ready") {
    setup.receive(message);
    const choices = modelChoices(bridge.models, localStorage.getItem("gz-design-model"), localStorage.getItem("gz-review-model"));
    state.designModel ??= choices.design;
    state.reviewModel ??= choices.review;
    if (setup.association?.installed) syncSetupModels();
    connectionLabel();
    updateKeyBar();
    gateStart();
    if (state.route === "form") guarded(preview)();
    return;
  }
  const detached = state.sessions.get(message.session_id);
  if (detached?.review && detached.id !== state.sessions.get(state.design)?.reviewSession) {
    if (message.type === "gz.progress" && message.op === "idle") detached.op = "idle";
    return;
  }
  if (request?.run && request !== state.startRequest && ["gz.session", "gz.error"].includes(message.type)) return;
  if (request?.review && (request.designId !== state.design || request.designGeneration !==
    (state.sessions.get(state.design)?.generation ?? 0) || request.reviewRequest !== state.sessions.get(state.design)?.reviewRequest)) return;
  if (message.type === "gz.error") {
    if (request?.park && (request.park !== parkQueue.item?.id || request.session !==
      parkQueue.item?.[parkQueue.item.stage + '_session'])) return;
    if (request?.park || request?.queue) guarded(async () => {
      await parkQueue.event(message.code === 'WORKSPACE' ? 'hold' : 'error', {reason:message.message});
      if (parkQueue.item?.status === 'pending') await parkQueue.next();
    })();
    const ownsStart = request === state.startRequest;
    if (ownsStart) {
      state.starting = false;
      state.startRequest = null;
    }
    const design = state.sessions.get(state.design);
    if (ownsStart && request?.review && design?.reviewBanner) reviewFailed(design, message.message);
    if (state.route === "run") updateRun();
    notice("AGH 未完成请求：" + message.message);
    return;
  }
  if (message.type === "gz.session" && request) {
    state.starting = false;
    state.startRequest = null;
    const s2 = { id: message.session_id, project: request.project, nodes: [], approvals: [], op: "running", run: request.run,
      review: request.review, awaitingStart: Boolean(request.review) };
    state.sessions.set(s2.id, s2);
    state.active = s2.id;
    state.navigation = null;
    if (!s2.review) state.design = s2.id;
    else state.sessions.get(state.design).reviewSession = s2.id;
    if (request.queue) guarded(() => parkQueue.opened(s2.id))();
  }
  if (parkQueue.item?.status === 'cancelling' && message.session_id === parkQueue.item[parkQueue.item.stage + '_session']) {
    const cancelling = state.sessions.get(message.session_id);
    if (cancelling && message.type === 'gz.progress') cancelling.op = message.op;
    return guarded(() => parkQueue.observe(message))();
  }
  if (parkQueue.item && message.session_id === parkQueue.item[parkQueue.item.stage + '_session']) {
    await guarded(() => parkQueue.observe(message))();
  }
  const s = state.sessions.get(message.session_id);
  if (!s) {
    if (message.type === "gz.progress") {
      state.active = message.session_id;
      if (state.route === "run") updateRun();
    }
    return;
  }
  const previousOp = s.op;
  if (message.type === "gz.progress" && s.review && s.awaitingStart && !s.ended) {
    if (message.op === "idle" && message.started !== true && !(message.nodes ?? []).some((n) => ["text", "tool"].includes(n.kind))) return;
    s.awaitingStart = false;
  }
  if (message.type === "gz.progress") {
    state.active = s.id;
    if (state.navigation === s.id) state.navigation = null;
  }
  if (message.type === "gz.progress") {
    if (message.op === "running") resumeSession(s);
    s.recovering = false;
    s.nodes = message.nodes ?? [];
    s.op = message.op;
    s.idleSince = s.op === "idle" ? s.idleSince ?? Date.now() : null;
    loadComparisonReasons(s);
    if (s.review && s.op === 'idle' && !s.verification && !s.finishError) {
      const design = state.sessions.get(state.design);
      design.reviewFailure = null;
      design.reviewBanner = '审核员已结束，正在核对审核记录（约 10 秒）';
    }
    s.usage = message.usage?.session_id === s.id ? message.usage : null;
  }
  if (message.type === "gz.approval") s.approvals.push({ ...message, received_at: Date.now() });
  if (state.route === "run") {
    updateRun();
  }
  if (message.type === "gz.progress" && s.op === "idle") guarded(() => finishSession(s,
    parkQueue.item?.spec.id === s.project && message.started && parkQueue.item.status !== 'approval' || s.ended ||
    s.nodes.some((n) => n.kind === "tool" &&
    n.status === "failed") || naturallyStopped(s, previousOp, computeSteps(s.nodes, { run: s.run, op: s.op, approvals: s.approvals })), true))();
});
const parkQueue = new ParkQueue(api, (type, payload) => bridge.send(type,
  {...payload, workspace_binding:parkQueue.item?.workspace_binding}, {park:parkQueue.item?.id, session:payload.session_id}),
  item => item.stage === 'review' ? restorePark(item, true) : start(item), item => restorePark(item));
parkQueue.changed = () => {
  if (state.route === 'run') updateRun();
  else if (state.route === 'park' && parkView.id === parkQueue.id) {
    const slot = document.getElementById('park-queue-display');
    if (slot) slot.outerHTML = queueMarkup(parkQueue.queue);
  }
};
const parkView = new ParkView(api, parkQueue, async (key, park) => {
  state.roofs = (await api('roofs')).roofs;
  const template = key === 'shared' ? park.buildings[0]?.template : key;
  if (!template) throw new Error('请先加入厂房');
  selectRoof(park.id + '--' + template);
  Object.assign(state.form, park.settings.shared ?? {}, key === 'shared' ? {} : park.settings[key] ?? {});
  state.parkEdit = {key, park};
  state.mode = 'auto';
  location.hash = '#form';
}, (key, park) => {
  const source = state.roofs.find(r => r.id === key);
  const form = {keep:[], text:'按屋顶和现场条件设计', maxRounds:6, compare:geo(source).type !== 'metal',
    review:true, exportOn:true, prefer:'balanced', tiltMin:'', tiltMax:'', ...park.settings.shared, ...park.settings[key],
    id:'park-draft', template:park.id + '--' + key};
  if (!state.designModel) throw new Error('先配置设计模型');
  if (!bridge.workspaceBinding) throw new Error('右侧 AGH 的工作区还没确认好，请等首页显示「已就绪」后再点');
  return {spec:formSpec(form, state.reviewModel), design_model:state.designModel.id, workspace_binding:bridge.workspaceBinding};
}, notice);
async function saveParkSettings() {
  const {key, park} = state.parkEdit;
  await preview();
  if (!state.brief) throw new Error(state.errors.join('；'));
  park.settings[key] = Object.fromEntries(Object.entries(state.form).filter(([field]) =>
    !['id', 'template', 'inverterModels'].includes(field) &&
    (key !== 'shared' || !field.startsWith('f') || ['fKwh', 'fShifts'].includes(field))));
  await api(`parks/${park.id}/save`, park);
  state.parkEdit = null;
  location.hash = '#park';
}
async function restorePark(item, create = false) {
  requireParkWorkspace(item);
  const spec = item.spec, run = {prefer:spec.prefer, compare:spec.compare, export:spec.export,
    review:{enabled:spec.review, mode:'independent', model:spec.reviewer_model}};
  state.sessions.clear();
  state.design = item.design_session;
  state.reviewCount = item.stage === 'review' ? 1 : 0;
  state.starting = false;
  let archived = null;
  try { archived = await api('runs/gz-' + spec.id); } catch { /* No archive before the first normal finish. */ }
  if (archived && !create && item.status !== 'cancelling') {
    try {
      await parkQueue.event('finish');
      return setTimeout(guarded(() => parkQueue.next()), 0);
    } catch { /* A design-only archive still needs its configured review. */ }
    if (item.stage === 'design' && spec.review && archived.verification?.verified_exports?.length) {
      await parkQueue.event('review');
      return restorePark(parkQueue.item, true);
    }
  }
  const design = {id:item.design_session, project:spec.id, run, review:false, op:'idle', approvals:[],
    nodes:(archived?.timeline?.nodes ?? []).filter(n => n.session === item.design_session)};
  state.sessions.set(design.id, design);
  if (item.stage === 'review') {
    design.reviewSession = item.review_session;
    state.sessions.set(item.review_session, {id:item.review_session, project:spec.id, run, review:true,
      op:'idle', approvals:[], nodes:[], awaitingStart:false});
  }
  state.active = item[item.stage + '_session'];
  location.hash = '#run';
  if (create) {
    const model = bridge.models.find(m => m.id === spec.reviewer_model || qualified(m) === spec.reviewer_model);
    if (!model) throw new Error('请配置任务书指定的审核模型');
    design.reviewRequest = 1;
    state.startRequest = {run, project:spec.id, review:true, designId:design.id, designGeneration:0, reviewRequest:1, queue:item.id};
    state.starting = true;
    bridge.send('gz.start', {brief:null, project_id:spec.id + '-review', workspace:'guangzhu', design_model:model,
      session_key:item.review_session, workspace_binding:item.workspace_binding, ...setup.session}, state.startRequest);
  } else {
    bridge.send('gz.open', {session_id:state.active, workspace_binding:item.workspace_binding}, {park:item.id, session:state.active});
    notice('恢复原会话；若发送状态不明，请核对原会话，不会重发任务书。每栋导出仍需原生批准。');
  }
}
function requireParkWorkspace(item) {
  if (!item.workspace_binding || item.workspace_binding !== bridge.workspaceBinding) {
    const error = new Error('队列原工作区关联与当前连接不一致，没有再派发；不想继续这一批，就点「放弃这个队列」再重新开始');
    error.recoverable = true;
    throw error;
  }
}
async function start(queued = null) {
  if (!queued && state.parkEdit) return saveParkSettings();
  if (state.starting || [...state.sessions.values()].some((s) => s.op === "running")) throw new Error("请先停止当前设计");
  if (setup.association?.installed && setupFailed()) throw new Error("设计工具没准备好，请在首页点重试");
  if (!bridge.ready) throw new Error("正在连接 AGH…");
  if (queued) {
    requireParkWorkspace(queued);
    state.mode = 'auto';
    state.form = {...state.form, id:queued.spec.id, template:queued.spec.template, review:queued.spec.review};
    state.designModel = bridge.models.find(m => m.id === queued.design_model || qualified(m) === queued.design_model);
    if (queued.spec.review) state.reviewModel = bridge.models.find(m => m.id === queued.spec.reviewer_model ||
      qualified(m) === queued.spec.reviewer_model);
    state.brief = (await api('brief', queued.spec)).brief;
  } else if (state.mode === "auto") {
    await preview();
    if (!state.brief) throw new Error(state.errors.join("；"));
  }
  if (!state.designModel || state.mode === "auto" && state.form.review && !state.reviewModel) throw new Error("先在首页上方填一家模型的 key");
  if (setup.association?.installed && !setup.status?.ready) throw new Error("正在准备设计工具…");
  state.starting = true;
  const spec = queued?.spec ?? (state.mode === "chat" ? {compare:false, export:false, review:false} : formSpec(state.form, state.reviewModel));
  state.sessions.clear();
  state.reviewCount = 0;
  state.runTab = "live";
  state.final = null;
  state.result = null;
  state.active = null;
  state.design = null;
  state.navigation = null;
  const run = {prefer:spec.prefer, compare:spec.compare, export:spec.export,
    review:{enabled:spec.review, mode:"independent", model:spec.reviewer_model}};
  state.startRequest = { run, review: false, project: state.form.id, ...queued ? {queue:queued.id} : {} };
  bridge.send(
    "gz.start",
    { brief: queued || state.mode === "chat" ? null : state.brief, project_id: state.form.id, workspace: "guangzhu",
      ...queued ? {session_key:queued.design_session, workspace_binding:queued.workspace_binding} : {},
      design_model: state.designModel, evaluation, ...setup.session },
    state.startRequest
  );
  issuedProjects.add(state.form.id);
  location.hash = "#run";
}
async function finishSession(s, force = false, autoReview = !force) {
  if (!s?.id || !state.design) return;
  const designId = state.design, design = state.sessions.get(designId);
  if (!design) return;
  const current = resolvedTools(s.nodes).filter((n) => n.completion_index >= (s.turnStart ?? 0)),
    exported = toolResult(current, "gz_export"), recorded = toolResult(current, "gz_record_review"),
    generation = s.generation ?? 0, designGeneration = design.generation ?? 0, reviewRequest = design.reviewRequest;
  const owns = () => designId === state.design && generation === (s.generation ?? 0) &&
    designGeneration === (design.generation ?? 0) && (!s.review || design.reviewSession === s.id && design.reviewRequest === reviewRequest);
  if (!owns() || finishing || s.op === "running" || !s.review && !exported && !force) return;
  const key = s.id + ":" + generation + ":" + (exported?.version ?? recorded?.file ?? "review-idle");
  if (key === s.finishKey) return;
  finishing = true;
  s.finishKey = key;
  if (!s.review && autoReview && exported && design.run.review?.enabled && state.reviewCount === 0) {
    design.reviewPreparing = true;
    design.reviewBanner = reviewIntro;
    if (state.route === 'run') updateRun();
  }
  try {
    const reviewId = (state.sessions.get(state.design)?.run.review?.model ?? state.reviewModel?.id)?.split("/").at(-1);
    const final = await api("runs/finish", { ...finishRequest(state.sessions.get(state.design), s.review ? s : null, { id: reviewId }), evaluation });
    if (!owns()) return;
    await loadRecords(owns);
    if (!owns()) return;
    for (const id of new Set([s.id, state.design])) {
      const target = state.sessions.get(id), usage = final.usage_by_session?.[id];
      if (target && target.op !== "running") target.archivedUsage = usage?.session_id === id ? usage : {};
    }
    s.verification = final.verification;
    s.result = final.result;
    state.final = final;
    if (s.review) {
      Object.assign(design, {verification:final.verification, result:final.result, reviewRecord:recorded, reviewSession:s.id,
        reviewCompletedAt:current.findLast((n) => n.name === "gz_record_review")?.ended_at, reviewBanner:null});
      if (final.verification.review?.passed !== true) reviewFailed(design, recorded?.verdict === "revise" ? "审核员要求修改方案" : "审核未核对通过");
      // a park batch goes straight on to the next building; going back to the design here would race that building's new session
      if (final.verification.review?.passed === true && parkQueue.item?.spec.id !== design.project) {
        state.navigation = design.id;
        bridge.send("gz.open", { session_id: design.id });
      }
    }
    s.finishError = null;
    if (autoReview && state.reviewCount === 0 && exported && shouldReview(s, final, state.reviewCount)) await startReview(s);
    else if (parkQueue.item?.spec.id === design.project && (s.review || parkQueue.item.stage === 'design')) {
      await parkQueue.event('finish');
      setTimeout(guarded(() => parkQueue.next()), 0);
    }
    if (state.route === "run") await render();
  } catch (error) {
    if (!owns()) return;
    s.finishKey = "";
    s.finishError = error.message;
    if (error.recoverable && parkQueue.item?.spec.id === design.project) {
      await parkQueue.event('hold', {reason:error.message});
    } else if (parkQueue.item?.spec.id === design.project && s.op === 'idle' && ['running', 'reconcile'].includes(parkQueue.item.status)) {
      await parkQueue.event('failed', {reason:'运行已停下，归档未完成：' + error.message});
      setTimeout(guarded(() => parkQueue.next()), 0);
    }
    if (s.review) reviewFailed(design, error.message);
    if (state.route === "run") updateRun();
    throw error;
  } finally {
    finishing = false;
    if (owns() && design.reviewPreparing) {
      design.reviewPreparing = false;
      if (!design.reviewFailure) design.reviewBanner = null;
      if (state.route === 'run') updateRun();
    }
    if (!owns()) {
      const next = state.sessions.get(state.design), target = state.sessions.get(next?.reviewSession) ?? next;
      if (target?.op === "idle" && !(state.starting && !next?.reviewSession)) guarded(() => finishSession(target))();
    }
  }
}
function reviewFailed(design, reason) {
  design.reviewFailure = reason;
  design.reviewBanner = "独立审核停下了：" + reason;
}
async function startReview(design) {
  if (state.starting || state.reviewCount >= 2 || !bridge.ready) return;
  const final = state.final, modelRef = design.run.review.model;
  // The task book carries only the reviewer's model ID (account routes stay out of the ledger); find its configured route here.
  const id = modelRef?.split("/").at(-1);
  const model = bridge.models.find((m) => qualified(m) === modelRef) ?? (state.reviewModel?.id === id ? state.reviewModel : null) ??
    bridge.models.find((m) => m.id === id);
  if (!final?.review_prompt || !model) {
    reviewFailed(design, "找不到任务书指定的审核模型，请在 AGH 配置后重新审核");
    throw new Error(design.reviewFailure);
  }
  const queued = parkQueue.item?.spec.id === design.project ? parkQueue.item : null;
  if (queued) requireParkWorkspace(queued);
  if (queued) await parkQueue.event('review');
  design.reviewFailure = null;
  design.reviewPreparing = false;
  design.reviewSession = null;
  design.reviewRequest = (design.reviewRequest ?? 0) + 1;
  design.reviewBanner = reviewIntro;
  state.runTab = "live";
  state.startRequest = {run:design.run, review:true, project:design.project, designId:design.id,
    designGeneration:design.generation ?? 0, reviewRequest:design.reviewRequest, ...queued ? {queue:queued.id} : {}};
  state.starting = true;
  state.reviewCount++;
  if (state.route === "run") updateRun();
  bridge.send("gz.start", {brief:queued ? null : final.review_prompt, project_id:design.project + "-review", workspace:"guangzhu",
    design_model:model, ...queued ? {session_key:queued.review_session, workspace_binding:queued.workspace_binding} : {}, ...setup.session},
    state.startRequest);
}
function continueDesign(text) {
  const s = state.sessions.get(state.design);
  if (!text || !s || state.navigation || state.active !== s.id || s.op === "running" || s.recovering) return;
  s.recovering = true;
  resumeSession(s);
  bridge.send("gz.followup", {session_id:s.id, text});
  return render();
}
async function openTarget(target) {
  const s = state.sessions.get(state.design);
  const result = state.route === "result" ? state.result : s?.result ?? state.final?.result;
  await api("open", {
    kind: target === "exports" ? "export" : target,
    session_id: target === "agh" ? state.active : s?.id,
    project_id: result?.project_id ?? s?.project ?? state.form.id,
    version: target === "exports" ? result?.version : result?.selected_version,
    run_id: result?.run_id ?? state.final?.run_id
  });
}
const actions = { start, 'park-settings-save':saveParkSettings,
  'scene-top':() => scene?.resetView(true),
  'scene-focus':() => scene?.resetView('selected'),
  'scene-reset':() => scene?.resetView(),
  'scene-retry':() => {
    scene?.dispose();
    mountScene();
  },
  'result-retry':() => render(),
  'park-pause':() => parkQueue.event('pause'),
  'park-resume':async () => {
    await parkQueue.event('resume');
    await parkQueue.next();
  },
  'park-skip':() => parkQueue.skip(),
  'park-abandon':async () => {
    if (!confirm('放弃这个队列：没跑完的厂房都标成「跳过」，不会再派发，之后可以重新勾选开始。如果右侧 AGH 里它的会话还在跑，请先在那里停止。确定放弃吗？')) return;
    await parkQueue.abandon();
    notice('队列已放弃，可以在园区页重新勾选厂房开始');
    await render();
  },
  'park-queue-show':() => {
    parkView.id = parkQueue.id;
    location.hash = '#park';
  },
  "finish-retry": () => {
  const s = state.sessions.get(state.design);
  if (s) {
    s.finishKey = "";
  }
  return finishSession(s, true);
}, copy: () => navigator.clipboard.writeText(state.brief), cancel: () => {
  const s = state.sessions.get(state.active);
  s.ended = true;
  s.userStopped = true;
  bridge.send("gz.cancel", { session_id: state.active });
}, "open-report": () => openTarget("report"), "open-agh": () => openTarget("agh"), "open-exports": () => openTarget("exports"),
"open-run": () => openTarget("run"), "records-refresh": async () => {
  if (await loadRecords()) await render();
}, "checkpoint-stop": async () => {
  const s = state.sessions.get(state.active);
  s.ended = true;
  await finishSession(s, true);
  return render();
}, "review-session": () => {
  const s = state.sessions.get(state.sessions.get(state.design)?.reviewSession);
  if (s) {
    state.navigation = s.id;
    bridge.send("gz.open", { session_id: s.id });
  }
  return render();
}, "design-session": () => {
  state.navigation = state.design;
  bridge.send("gz.open", { session_id: state.design });
  return render();
}, "review-retry": () => {
  const design = state.sessions.get(state.design);
  if (design?.reviewFailure) return startReview(design);
}, "see-result": () => {
  location.hash = "#result/" + encodeURIComponent(state.sessions.get(state.design).project);
}, play: () => replay?.play(), pause: () => replay?.pause(),
"keys-open": () => {
  state.keysOpen = true;
  document.querySelector(".keybar").outerHTML = keyBar();
  document.querySelector('.keybar input[data-key]')?.focus();
}, "keys-close": () => {
  state.keysOpen = false;
  document.querySelector(".keybar").outerHTML = keyBar();
},
"setup-retry": async () => {
  if (setup.status?.phase === "failed") await api("setup/configure", {});
  await setup.recheck();
  updateKeyBar();
} };
document.addEventListener("click", guarded(async (event) => {
  const el = event.target.closest("button");
  if (!el) return;
  if (el.disabled) return;
  if (el.dataset.saveKey) return saveKey(el.dataset.saveKey);
  if (el.dataset.action) return actions[el.dataset.action]?.();
  if (el.dataset.openReport) return api("open", {kind:"report", run_id:el.dataset.openReport});
  if (el.dataset.recovery != null) {
    const recovery = recoveryDescription(state.sessions.get(state.design), activeComputed());
    return continueDesign(recovery?.actions[Number(el.dataset.recovery)]?.text);
  }
  if (el.dataset.report) {
    el.disabled = true;
    try {
      const report = await api("runs/" + encodeURIComponent(el.dataset.report) + "/report", {});
      notice(report.error ?? report.hint ?? "方案书已生成");
      return actions["records-refresh"]();
    } finally {
      el.disabled = false;
    }
  }
  if (el.dataset.roof) {
    selectRoof(el.dataset.roof);
    return render();
  }
  if (el.dataset.mode) {
    state.mode = el.dataset.mode;
    return render();
  }
  if (el.dataset.keep) {
    const k = el.dataset.keep;
    state.form.keep = state.form.keep.includes(k) ? state.form.keep.filter((x) => x !== k) : [...state.form.keep, k];
    el.setAttribute("aria-pressed", state.form.keep.includes(k));
    return preview();
  }
  if (el.dataset.suggestion != null) {
    const choice = activeComputed().suggestions[Number(el.dataset.suggestion)];
    return continueDesign(`同意建议${choice.number}：${choice.text}。按一键模式继续，直到申请导出`);
  }
  for (const [key, prop] of [["runTab", "runTab"], ["resultTab", "resultTab"], ["filter", "filter"]]) if (el.dataset[key]) {
    state[prop] = el.dataset[key];
    if (key === "resultTab") {
      html("result-panel", resultPanel(state.result));
      el.parentNode.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", b === el));
      return;
    }
    return render();
  }
  if (el.dataset.version) {
    if (state.route !== "result") {
      const s = state.sessions.get(state.design), result = s?.result ?? state.final?.result;
      location.hash = "#result/" + encodeURIComponent(s?.project ?? state.form.id) + "?version=" + el.dataset.version +
        (result?.run_id ? "&run=" + encodeURIComponent(result.run_id) : "");
      return;
    }
    location.hash = '#result/' + encodeURIComponent(state.result.project_id) + '?version=' + encodeURIComponent(el.dataset.version) +
      (state.resultRun ? '&run=' + encodeURIComponent(state.resultRun) : '');
    return;
  }
  if (el.dataset.theme) {
    state.theme = el.dataset.theme;
    theme();
    settings();
  }
  if (el.dataset.sceneMode) {
    state.sceneMode = el.dataset.sceneMode;
    scene?.setMode(state.sceneMode);
    if ($('wiring-tools')) $('wiring-tools').hidden = state.sceneMode !== 'wiring';
    if ($('heat-legend')) $('heat-legend').hidden = state.sceneMode !== 'heat';
  }
  if (el.dataset.season) {
    state.season = el.dataset.season;
    updateSun();
  }
  if (el.dataset.sceneMode || el.dataset.season) el.parentNode.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", b === el));
}));
// Folded result sections stay as the reader left them when the panel is redrawn (toggle does not bubble).
document.addEventListener("toggle", (event) => {
  const key = event.target?.dataset?.fold;
  if (key) state.folds[event.target.open ? "add" : "delete"](key);
}, true);
document.addEventListener("input", (event) => {
  const el = event.target;
  if (el.id === 'wire-string' || el.id === 'wire-ac') {
    state.wireString = $('wire-string')?.value ?? '';
    if ($('wire-focus')) $('wire-focus').disabled = !state.wireString;
    scene?.selectString(state.wireString, $('wire-ac')?.checked ?? true);
    html('wire-details', wiringDetails(state.result, state.wireString));
  }
  if (el.dataset.park || el.dataset.parkField) {  // T22: ticking a building or typing a budget re-plans the park
    if (el.dataset.park) state.park.on[el.checked ? "add" : "delete"](el.dataset.park);
    else state.park[el.dataset.parkField] = el.value;
    return html("park-body", parkBody());
  }
  if (el.dataset.field) {
    state.form[el.dataset.field] = el.type === "checkbox" ? el.checked : el.value;
    if (['moduleId', 'inverterBrand', 'inverterId'].includes(el.dataset.field)) state.form[el.dataset.field + 'Picked'] = true;
    if (el.dataset.field === 'parapetCap') {
      state.form.maxHeight = el.checked ? geo(roof()).parapet_height_m : '';
      document.querySelector('[data-field="maxHeight"]').value = state.form.maxHeight;
    }
    if (el.dataset.field === "prefer") Object.assign(state.form, { preferPicked: true, preferAuto: false });  // a hand pick beats 尽量多装
    if (el.dataset.field === "text") {
      const inferred = inferRequirements(el.value, state.form, roof());
      state.form = inferred.form;
      state.recognized = inferred.summary;
      state.unrecognized = Boolean(inferred.unknown);
      document.querySelectorAll("[data-field]").forEach((input) => {
        if (input !== el && input.dataset.field in state.form) {
          input[input.type === 'checkbox' ? 'checked' : 'value'] = state.form[input.dataset.field];
        }
      });
      document.querySelectorAll("[data-keep]").forEach((button) => button.setAttribute("aria-pressed", state.form.keep.includes(button.dataset.keep)));
      if ($("recognized")) {
        $("recognized").textContent = inferred.summary;
        $("recognized").className = inferred.unknown ? 'recognition-warning' : 'muted';
      }
    }
    clearTimeout(briefTimer);
    briefTimer = setTimeout(preview, 250);
  }
  if (el.id === "sun-time") {
    state.hour = Number(el.value);
    updateSun();
  }
  if (el.id === "replay-seek") replay?.seek(Number(el.value));
  if (el.id === "replay-session") {
    replay?.setSession(el.value);
    html("replay-usage", replayUsage(el.value));
  }
  if (["design-model", "form-design-model", "review-model", "form-review-model"].includes(el.id)) {
    const review = el.id.includes("review"), chosen = bridge.models.find((m) => qualified(m) === el.value);
    if (!chosen) return;
    state[review ? "reviewModel" : "designModel"] = chosen;
    localStorage.setItem(review ? "gz-review-model" : "gz-design-model", el.value);
    setup[review ? "reviewPreference" : "preference"] = el.value;
    if (setup.association?.installed) guarded(() => setup.recheck())();
    updateKeyBar();
    if (state.route === "form" && review) guarded(preview)();
  }
});
function syncSetupModels() {
  if (!setup.models) return;
  bridge.models = setup.models.models.map(model => ({...model, label:model.name}));
  const resolve = ref => bridge.models.find(model => model.id === ref?.id && model.route === ref?.route) ?? null;
  state.designModel = resolve(setup.models.design);
  state.reviewModel = resolve(setup.models.review);
}
const setup = new Setup(api, bridge, () => {
  syncSetupModels();
  connectionLabel();
  updateKeyBar();
  gateStart();
});
setup.preference = localStorage.getItem("gz-design-model") ?? "";
setup.reviewPreference = localStorage.getItem("gz-review-model") ?? "";
$("settings-open").onclick = () => {
  settings();
  $("settings").showModal();
};
$("settings-close").onclick = () => $("settings").close();
let shownHash = location.hash; // the roof editor asks before unsaved edits are left behind
window.addEventListener("hashchange", guarded(() => {
  if (state.route === "roof" && location.hash !== shownHash && !leaveRoofEditor()) return history.replaceState(null, "", shownHash || "#new");
  shownHash = location.hash;
  return render();
}));
window.addEventListener("resize", placeFrame);
window.addEventListener("scroll", placeFrame, true);
// Dividers between panes: drag, arrow keys (Shift for bigger steps) or a double click back to the default; kept for next time
const splitSizes = (() => {
  try { return JSON.parse(localStorage.getItem("gz-split") ?? "{}") ?? {}; } catch { return {}; }
})();
function applySplit(key, px) {
  if (px == null) delete splitSizes[key];
  else splitSizes[key] = Math.round(px);
  if (px == null) document.documentElement.style.removeProperty(SPLITS[key].css);
  else document.documentElement.style.setProperty(SPLITS[key].css, Math.round(px) + "px");
}
const saveSplits = () => {
  try { localStorage.setItem("gz-split", JSON.stringify(splitSizes)); } catch { /* a remembered size is only a convenience */ }
};
for (const [key, px] of Object.entries(splitSizes)) if (SPLITS[key] && Number.isFinite(px)) applySplit(key, px);
function splitBounds(handle) {
  const key = handle.dataset.split, rule = SPLITS[key], measure = (el) => el?.getBoundingClientRect()[rule.axis === "x" ? "width" : "height"] ?? 0;
  const pane = rule.pane === "start" ? handle.previousElementSibling : handle.nextElementSibling;
  const other = rule.pane === "start" ? handle.nextElementSibling : handle.previousElementSibling;
  const size = measure(pane);
  return { key, rule, size, max: Math.max(rule.min, Math.min(rule.max, size + measure(other) - rule.keep)) };
}
function resizeSplit({ key, rule, max }, px) {
  applySplit(key, Math.min(max, Math.max(rule.min, px)));
  placeFrame();
}
let splitDrag = null;
const endSplit = () => {
  if (!splitDrag) return;
  splitDrag = null;
  document.body.classList.remove("splitting", "cols", "rows");
  document.querySelectorAll(".splitter.active").forEach((el) => el.classList.remove("active"));
  saveSplits();
};
document.addEventListener("pointerdown", (event) => {
  const handle = event.target.closest?.(".splitter");
  if (!handle || event.button !== 0) return;
  event.preventDefault();
  const axis = SPLITS[handle.dataset.split].axis;
  splitDrag = { ...splitBounds(handle), from: axis === "x" ? event.clientX : event.clientY };
  try { handle.setPointerCapture(event.pointerId); } catch { /* the window listeners below still follow the pointer */ }
  handle.classList.add("active");
  document.body.classList.add("splitting", axis === "x" ? "cols" : "rows");
});
window.addEventListener("pointermove", (event) => {
  if (!splitDrag) return;
  const moved = (splitDrag.rule.axis === "x" ? event.clientX : event.clientY) - splitDrag.from;
  resizeSplit(splitDrag, splitDrag.size + (splitDrag.rule.pane === "start" ? moved : -moved));
});
window.addEventListener("pointerup", endSplit);
window.addEventListener("pointercancel", endSplit);
document.addEventListener("dblclick", (event) => {
  const handle = event.target.closest?.(".splitter");
  if (!handle) return;
  applySplit(handle.dataset.split, null);
  saveSplits();
  placeFrame();
});
document.addEventListener("keydown", (event) => {
  const handle = event.target.closest?.(".splitter"), rule = SPLITS[handle?.dataset.split];
  const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -1, ArrowDown: 1 }[event.key];
  if (!rule || !step || ["ArrowLeft", "ArrowRight"].includes(event.key) !== (rule.axis === "x")) return;
  event.preventDefault();
  const bounds = splitBounds(handle);
  resizeSplit(bounds, bounds.size + (rule.pane === "start" ? step : -step) * (event.shiftKey ? 96 : 24));
  saveSplits();
});
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", theme);
setInterval(guarded(async () => {
  await checkConnection();
  if (bridge.fallback && state.form.id && !polling && state.route === "run") {
    polling = true;
    try {
      const p = await api("projects/" + encodeURIComponent(state.form.id) + "/progress");
      let s = state.sessions.get(state.active);
      if (!s) {
        s = { nodes: [], run: {}, op: "idle", project: state.form.id };
        state.active = "file-progress";
        state.sessions.set(state.active, s);
      }
      const c = computeSteps(p.nodes ?? [], { op: "idle" });
      s.fallback = { ...c, steps: c.steps.map((x, i) => ({ ...x, state: p.steps[i]?.status ?? x.state, detail: "文件进度；不代表原生执行顺序已核对" })) };
    } finally {
      polling = false;
    }
  }
  if (state.route === "run") {
    updateRun();
  }
}), 1e3);
theme();
try {
  loadRecords().then(guarded(async (loaded) => {
    if (loaded && ["new", "records"].includes(state.route) && (location.hash.slice(1) || "new") === state.route) await render();
  })).catch((error) => notice(error.message));
  const results = await Promise.allSettled([api(evaluation ? "roofs?all=1" : "roofs"), checkConnection()]);
  state.roofs = results[0].value?.roofs ?? [];
  state.modules = results[0].value?.modules ?? [];
  state.inverters = results[0].value?.inverters ?? [];
  if (state.roofs.length) selectRoof(state.roofs[0].id);
  await render();
} catch (error) {
  notice(error.message);
}
function modesMarkup() {
  return `<div class="modes">${[["auto", "一键模式", "填好条件，Agent 按步骤完成设计"], ["chat", "对话模式", "在 AGH 中自由描述需求"]].map(([m, t, d]) =>
    `<button class="mode" data-mode="${m}" aria-pressed="${state.mode === m}"><h4>${t}${state.mode === m ? "<em>已选</em>" : ""}</h4><ul><li>${d}</li>
  <li>${m === "auto" ? "分析、修改、对比、复核、申请导出" : "使用同一套光筑工具与原生审批"}</li><li>${m === "auto" ? "做不到时停下给放宽建议 · 用时以执行记录为准" : "由你决定下一步，过程自动留下记录"}</li></ul>
  </button>`).join("")}</div>`;
}
function roofChoices(r) {
  const groups = [["mine", "我的屋顶"], ["demo", "演示"], ["real", "真实园区"]];
  if (evaluation) groups.push(["boundary", "边界案例"], ["impossible", "做不到案例"]);
  return `<div class="roofhead"><h3 class="sec">安装面</h3><a class="btn sm" href="#roof">＋ 新建安装面（画图或导入图纸）</a></div><div class="rooflist scroll">${
    // a park's copies of its buildings are managed on the park page; listing them here showed every park building twice
    groups.map(([collection, label]) => [label, state.roofs.filter((x) => (x.collection ?? "demo") === collection && !x.project?.park)])
      .filter(([, rows]) => rows.length).map(([label, rows]) =>
    `<h3 class="sec">${label}</h3>${rows.map((x) =>
    `<button class="roofrow" data-roof="${esc(x.id)}" aria-pressed="${x.id === r?.id}"><span class="ic">${roofSVG(x)}</span><span><h4>${esc(x.name)}
  <span class="chip"><span title="原值 ${esc(rawValue(x.area_m2))}">${Number(x.area_m2).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} m²</span>
    </span></h4>
  <p>${geo(x).obstacles?.length ?? 0}处障碍 · ${geo(x).keepouts?.length ?? 0}处禁区${geo(x).surroundings?.length ? ` · ${geo(x).surroundings.length}处周边遮挡` : ""} · ${
    x.collection === "mine" ? "我画的" : "随屋顶资料"}${geo(x).type === 'metal' ?
      ` · 彩钢瓦 ${geo(x).slope_deg}° · 朝${['北', '东北', '东', '东南', '南', '西南', '西', '西北'][Math.round(geo(x).slope_azimuth_deg / 45) % 8]}` : ''}</p></span>
  <span class="radio"></span></button>`).join("")}`).join("")}</div>`;
}
async function roofSaved(id) {
  const catalog = await api(evaluation ? "roofs?all=1" : "roofs");
  state.roofs = catalog.roofs;
  state.modules = catalog.modules ?? [];
  state.inverters = catalog.inverters ?? [];
  selectRoof(id ?? state.roofs[0]?.id);
  location.hash = "#new";
}
function roofPreview(r, g) {
  return `<aside class="card preview"><div class="pv-title"><h3>${esc(r?.name)}</h3>${r?.collection === "mine" ? `<a class="btn sm" href="#roof/${
    encodeURIComponent(r.id)}">编辑这个屋顶</a>` : '<span class="chip line">屋顶资料</span>'}</div><div class="pv-draw">${r ?
    roofSVG(r, true) : ""}</div><div class="facts">${fact("屋顶面积", r?.area_m2, "m²")}${fact( "外形尺寸", r?.dimensions_m?.join(" × "), "m" )}${fact("女儿墙",
      g.parapet_height_m, "m")}${fact(g.load_verified ? "屋面承重（结构核定）" : "屋面承重（示意值）", g.load_capacity_kn_m2, "kN/m²")}${fact( "障碍物", g.obstacles?.length, "处" )}${fact("禁区", g.keepouts?.length,
      "处")}${g.surroundings?.length ? fact("周边楼和树", g.surroundings.length, "处") : ""}</div><a class="btn primary next" href="#form">下一步：填条件 →</a></aside>`;
}
function requirementsMarkup(r, f) {
  const extras = [['curtail', '限电上限（示意默认10）', '%', 100], ['transformer', '变压器（默认取问答）', 'kVA', 1e5],
    ['transformerShare', '逆变器占比（示意默认80）', '%', 100], ['maxHeight', '组件最高点', 'm', 100],
    ['phaseKw', '一期装机（与预算二选一）', 'kW', 1e5], ['phaseBudget', '一期预算硬上限', '万元', 1e5]];
  return `<div class="card fcard"><h3>硬性要求 <small>空着表示不限</small></h3><div class="grid4">${field("payback", "回本不超过", "年", 1, 25)}${field( "budget", "预算不超过",
    "万元", 1, 1e4 )}${field("capMin", "装机不少于", "kW", 1, 5e3)}${field("capMax", "装机不超过", "kW", 1, 5e3)}${field("walkway", "检修通道至少", "m", 0,
    3)}${field( "obstacle", "离障碍物至少", "m", 0, 5 )}${field("edge", "离屋面边缘至少", "m", 0, 5)}<div class="grid2">${field("tiltMin", "倾角下限", "°", 0,
    35)}${field("tiltMax", "倾角上限", "°", 0, 35)}</div>
    ${extras.map(([key, label, unit, max]) => field(key, label, unit, 0, max)).join('')}</div>
    <label><input type="checkbox" data-field="noExport" ${f.noExport ? 'checked' : ''}>只自用，不上网</label>
    <label><input type="checkbox" data-field="noDrill" ${f.noDrill ? 'checked' : ''}>只用压载，不在屋面打孔</label>
    <label><input type="checkbox" data-field="parapetCap" ${f.parapetCap ? 'checked' : ''}>不高出女儿墙</label>
  <div class="keeps"><span class="muted">必须避开</span>${[...geo(r).obstacles ?? [], ...geo(r).keepouts ?? []].map((o) =>
    `<button class="keep" data-keep="${esc(o.id)}" aria-pressed="${f.keep.includes(o.id)}">${esc(o.label)} <span class="mono">${esc(o.id)}</span>
  </button>`).join("")}</div><label class="field"><span>补充说明</span><input data-field="notes" maxlength="200" value="${esc(f.notes)}"></label></div>`;
}
function factsMarkup(f) {  // T22: answers before construction, all optional
  const pick = (key, label, options) => `<label class="field"><span>${label}</span><select data-field="${key}">${[["", "不清楚"], ...options].map(([value,
    text]) => `<option value="${value}" ${String(f[key] ?? "") === value ? "selected" : ""}>${text}</option>`).join("")}</select></label>`;
  if (state.parkEdit?.key === 'shared') return `<div class="card fcard"><h3>每栋共享的用电假设</h3>
    <p>以下作为每栋厂房的假设，不是园区总负荷；各栋可覆盖。其他开工问答请按栋填写。</p><div class="grid3">
    ${field('fKwh', '每栋月用电', '万度', 0.01, 1e5, '不清楚')}
    ${pick('fShifts', '每栋生产班次', [['1', '单班'], ['2', '两班'], ['3', '三班'], ['4', '养殖场风机（示意）']])}</div></div>`;
  const kind = geo(roof()).type;
  if (['ground','carport'].includes(kind)) return `<div class="card fcard"><h3>新建安装开工前问答</h3><div class="grid3">
    ${kind === 'ground' ? pick('fLand','土地性质', [['construction','建设用地'],['cultivated','一般耕地'],
      ['permanent','永久基本农田'],['forest','林地'],['grass','草地'],['pasture','牧草地'],['unused','未利用地']]) +
      pick('fRedline','建筑附属且同一建设用地红线', [['1','是'],['0','否']]) : ''}
    ${field('fKva','变压器','kVA',1,1e5,'不清楚')}${field('fKwh','月用电','万度',.01,1e5,'不清楚')}
    ${pick('fShifts','生产班次',[['1','单班'],['2','两班'],['3','三班'],['4','养殖场风机（示意）']])}
    ${pick('fExport','余电上网',[['1','可以'],['0','只能自用']])}</div>
    <p>基础、地勘和钢结构由厂家核定。${kind === 'ground' ?
      '新建方阵不得占用任何耕地；其他土地须当地自然资源及林草部门确认。独立空地通常按集中式，附属同红线项目仍须满足分布式条件。' :
      '车位和车道按倒车垂直停车参照；结构深度与柱径示意，净高须按实际梁底核对。'}</p></div>`;
  return `<div class="card fcard"><h3>开工前问答 <small>选填，不知道就选"不清楚"；AI 会据此列出开工前要核实的事</small></h3><div class="grid3">
  ${pick("fRoof", "屋面类型", [["concrete", "混凝土平屋顶"], ["metal", "彩钢瓦"], ["other", "其他"]])}${field("fAge", "屋面已用", "年", 0, 100, "不清楚")}
  ${pick("fCore", "夹芯板", [["none", "不是夹芯板"], ["rockwool", "岩棉芯"], ["foam", "泡沫芯"]])}${pick("fSky", "采光带", [["1", "有"], ["0", "没有"]])}
  ${pick("fOwned", "厂房", [["1", "自己的"], ["0", "租的"]])}${field("fKva", "变压器", "kVA", 1, 1e5, "不清楚")}
  ${field("fKwh", "月用电", "万度", 0.01, 1e5, "不清楚")}
  ${pick('fShifts', '生产班次', [['1','单班'],['2','两班'],['3','三班'],['4','养殖场风机（示意）']])}
  ${pick("fExport", "余电上网", [["1", "可以"], ["0", "只能自用"]])}</div></div>`;
}
const siteStates = { ok: ["没问题", "ok"], risk: ["有风险", "bad"], ask: ["没填", "idle"] };
const siteMarkup = (result) => `<p class="muted">${result.facts ?"业主在开工前问答里填的情况；10 年、80% 是示意提醒线" :
  "这次没有填开工前问答，下面是开工前要问清的事"}</p><div class="rulelist site">${(result.site_checks ?? []).map((r) =>
  `<div><b>${esc(r.item)}</b><span>${esc(r.text)}</span>${pill(...siteStates[r.status])}</div>`).join("")}</div>`;
function parkPage() {  // T22: several buildings, each designed by one-click, side by side
  state.park ??= { budget: "", limit: "" };
  const input = (key, label, unit) => `<label class="field"><span>${label}</span><span class="inbox"><input data-park-field="${key}" type="number" min="0"
    step="any" value="${esc(state.park[key])}" placeholder="不限"><span>${unit}</span></span></label>`;
  return `${head("园区汇总", "几栋楼各做完一键设计，放在一起看：一共能装多少，预算内先装哪几栋", '<a class="btn" href="#records">设计记录</a>')}
  <div class="card fcard park-head"><div class="grid2">
  ${input("budget", "预算不超过", "万元")}${input("limit", "并网容量不超过", "kW")}</div><p class="muted">每栋都是 AI 一键设计、四步核对通过的导出方案，数字从导出文件读取。
  楼和楼之间的遮挡没有自动算：高楼挡矮楼，要在矮楼的"周边楼"里画上。</p></div><div id="park-body" class="park-body scroll">${parkBody()}</div>`;
}
function parkBody() {
  const data = state.parkData, number = (value) => String(value ?? "").trim() === "" ? null : Number(value);
  if (!data.buildings.length) return empty("还没有能汇总的设计：先在「新建设计」里给每栋楼各做一次一键设计（四步全过、已导出）");
  const auto = new Set(data.buildings.filter((b) => b.default).map((b) => b.run_id)), before = state.park.auto ?? new Set();
  state.park.on ??= new Set();  // a design finished since the last visit is ticked, one replaced by a newer design of its roof is not; hand picks stay
  for (const id of before) if (!auto.has(id)) state.park.on.delete(id);
  for (const id of auto) if (!before.has(id)) state.park.on.add(id);
  state.park.auto = auto;
  const budget = number(state.park.budget), limit = number(state.park.limit), limited = budget !== null || limit !== null;
  const plan = parkPlan(data.buildings, state.park.on, budget === null ? null : budget * 1e4, limit), total = limited ? plan.phase1 : plan.all;
  const kpi = ([label, value, unit]) => `<div class="kpi"><span>${label}</span><b>${valueMarkup(value, unit)}<small>${unit}</small></b></div>`;
  const card = (b) => {
    const on = plan.picked.includes(b), phase = !on ? pill("没选") : plan.first.includes(b) ? pill("一期", "ok") : pill("二期", "warn");
    return `<article class="card park-card${on ? "" : " off"}"><label><input type="checkbox" data-park="${esc(b.run_id)}" ${on ? "checked" : ""}>
    <b>${esc(b.name)}</b></label><p>${esc(b.building ?? '')}</p>${parkSVG(b)}<p>${valueMarkup(b.dc_kw, "kW")} kW ·
      回本 ${valueMarkup(b.payback_years, "年")} 年 · 造价 ${
      valueMarkup(b.capex_cny / 1e4, "万元")} 万元</p><p>${phase}${b.flags.map((flag) => pill(flag, "bad")).join("")}<a class="btn sm ghost" href="#result/${
      encodeURIComponent(b.project_id)}?run=${encodeURIComponent(b.run_id)}">看这栋</a></p><small class="muted">${esc(beijingTime(b.ended_at))} · v${
      b.version}</small></article>`;
  };
  return `<div class="kpis park-kpis">${[[limited ? "一期栋数" : "栋数", total.count, "栋"], ["装机", total.dc_kw, "kW"], ["基准年发电", total.annual_kwh / 1e4,
    "万kWh"], ["造价", total.capex_cny / 1e4, "万元"], ["整体回本", total.payback_years, "年"], ["年减碳", total.co2_t, "t"]].map(kpi).join("")}</div>
  <p class="muted">${limited ? `按回本从快到慢排，预算和并网容量都放得下的进一期（${plan.first.length} 栋），放不下的 ${plan.picked.length - plan.first.length} 栋放二期。`
    : `已选 ${plan.picked.length} 栋；填了预算或并网容量，就按回本从快到慢分一期、二期。`}${data.skipped.length ? `另有 ${data.skipped.length} 条记录缺导出文件或核对不上，没有计入。` :
    ""}</p><div class="park-grid">${data.buildings.map(card).join("")}</div>`;
}
function optionsMarkup(defaults, f, toggle) {
  return `<div class="row2"><div class="card fcard"><h3>经济参数 <span class="tag-demo">示意，可改</span></h3><div class="grid2">${field( "priceSelf", "自用电价", "元/度",
    0.1, 2, rawValue(defaults.price_self_cny_kwh) )}${field("selfUse", "自用比例", "%", 0, 100, defaults.self_use_ratio == null ? "模板默认" :
    defaults.self_use_ratio * 100)}${field("capex", "造价", "元/W", 1, 6, rawValue(defaults.capex_cny_per_w))}${field( "priceExport", "余电上网", "元/度", 0, 1,
    rawValue(defaults.price_export_cny_kwh) )}</div><p class="muted">月用电量和班次都填了，按逐时负荷算自用；手填比例优先，计算值作参考。
    只能自用时余电被限；电价填平段参考，默认按江苏426峰谷加权，基本电费不计收益。
    造价留空按实际数量分项合计；手填值优先。</p>${financialForm(f, field, toggle, geo(roof()).type, geo(roof()).use)}</div>
  <div class="card fcard"><h3>设备</h3><label class="ro">组件<select data-field="moduleId">${(state.modules ?? []).map((m) =>
    `<option value="${esc(m.id)}" ${f.moduleId === m.id ? 'selected' : ''}>${esc(m.model)}</option>`).join('')}</select></label>
  ${[['inverterBrand', '逆变器品牌', [['', '不限'], ['Sungrow', '阳光'], ['Huawei', '华为']]],
    ['inverterId', '逆变器型号', [['', '自动选型'], ...(state.inverters ?? []).map(r => [r.id, r.model])]]].map(([key, label, rows]) =>
    `<label class="ro">${label}<select data-field="${key}">${rows.map(([id, name]) =>
      `<option value="${id}" ${f[key] === id ? 'selected' : ''}>${esc(name)}</option>`).join('')}</select></label>`).join('')}
  <h3>运行设置</h3><div class="runopts"><p class="muted">三方案试正南、顺边和横放补位；多装还试东西向人字形。</p>
  <label class="ro">最多修改轮数<select data-field="maxRounds">${[1, 2, 3, 4, 5, 6].map((n) =>
    `<option ${Number(f.maxRounds) === n ? "selected" : ""}>${n}</option>`).join("")}</select></label><label class="ro">三方案都满足时选
  <select data-field="prefer" ${geo(roof()).type === 'metal' ? 'disabled' : ''}>${
    [["balanced", "折中"], ["max_capacity", "多装"], ["fast_payback", "最快回本"]].map(([v, t]) =>
    `<option value="${v}" ${f.prefer === v ? "selected" : ""}>${t}</option>`).join("")}</select></label>${modelSelect("form-design-model", "设计模型",
      state.designModel)}${modelSelect("form-review-model", "审核模型", state.reviewModel)}${toggle("compare", "三方案对比")}${toggle("review",
      "独立审核")}${toggle("exportOn", "结束时申请导出")}</div></div></div>`;
}
function modelSelect(id, label, current) {
  const select = `<select id="${id}">${bridge.models.map((m) => `<option value="${esc(qualified(m))}" ${qualified(m) === qualified(current) ?
    "selected" : ""}>${esc(m.label ?? m.id)}</option>`).join("") || '<option value="">先在首页填 key</option>'}</select>`;
  return label ? `<label class="ro">${label}${select}</label>` : select;
}
function briefMarkup(r, f) {
  return `<aside class="card form-right"><div class="mini-roof"><span class="ic">${roofSVG(r)}</span><div><h4>${esc(r?.name)}</h4>
  <p>${valueMarkup(r?.area_m2, "m²")} m² · ${valueMarkup(r?.project?.site?.lat, "°")}°N</p><p id="tilt-hint" class="muted tilt-hint">${tiltHint(r)}</p>
  <label class="field"><span>项目编号</span>
  <input data-field="id" maxlength="64" value="${esc(f.id)}"></label></div></div><div class="brief-box" ${state.mode === "chat" ? "hidden" : ""}>
  <header>任务书预览 <small>将原样发给 Agent</small></header>
  <pre id="brief-pre">${esc(state.brief || "填写需求后自动生成")}</pre></div><div id="brief-errors" class="bad-text">${esc(state.errors.join("；"))}</div>
  <div class="ready muted" ${state.mode === "chat" ? "hidden" : ""}>设计：${esc(state.designModel?.label ?? "等待模型清单")}<br>
  审核：${esc(state.reviewModel?.label ?? "未选审核模型")}</div><div class="go">
  <a class="btn" href="#new">上一步</a>${btn(!bridge.ready ? "正在连接 AGH…" : state.mode === "chat" ? "进入对话 →" : "开始自动设计 →",
    "start", "primary", !bridge.ready)}</div></aside>`;
}
function tiltHint(r) {
  if (geo(r).type === 'pitched') {
    return `${geo(r).planes.length} 个真实坡面分别顺坡平铺；比较所有可装面与每千瓦净年发电≥最好面95%的坡面（示意）。`;
  }
  if (geo(r).type === 'metal') {
    return `彩钢瓦顺坡平铺，倾角等于坡度 ${geo(r).slope_deg}°；三方案不适用`;
  }
  const id = r?.id, hint = id ? state.tiltHints?.[id] : null;
  if (!id) return "";
  if (hint === undefined) {
    state.tiltHints = { ...state.tiltHints, [id]: null };
    api("roofs/" + encodeURIComponent(id) + "/tilt").catch(() => ({})).then((value) => {
      state.tiltHints[id] = value ?? {};
      html("tilt-hint", tiltHint(r));
    });
  }
  if (!hint) return "正在按当地全年天气算最佳倾角…";
  if (!hint.available) return hint.hint ?? "开始设计后按当地天气计算倾角";
  return `纬度 ${Number(hint.lat).toFixed(1)}°：按当地全年天气，最佳倾角 ${hint.best}°；折中用 ${hint.balanced}°，每千瓦只少约 ${hint.loss_pct?.balanced}%，` +
    `同样屋顶大约能多排 ${hint.more_rows_pct}% 的板。`;
}
function conclusionMarkup(result, summary, economics, y) {
  Object.assign(state.ruleNames ??= {}, Object.fromEntries((result.rules?.items ?? []).map((r) => [r.id, r.name_zh]))); // versions never analysed have no rules
  const names = Object.fromEntries(Object.entries(state.ruleNames).map(([id, name]) => [id, loadWording(name, result.project)]));
  const metal = result.project?.roof;
  const direction = ['北', '东北', '东', '东南', '南', '西南', '西', '西北'][Math.round((metal?.slope_azimuth_deg ?? 180) / 45) % 8];
  const moduleId = result.project?.equipment?.module_id;
  const model = (state.modules ?? []).find((m) => m.id === moduleId)?.model ?? moduleId;
  return `<p>组件：${esc(model ?? '未提供')}</p>${metal?.type === 'metal' ? `<p>彩钢瓦单坡 ${metal.slope_deg}°、朝${direction}（${metal.slope_azimuth_deg}°），
    夹具顺坡平铺，没有压块。</p>` : ''}
  <div class="kpis">${[["装机", summary.dc_kw, "kW", "dc_kw"], ["基准年发电", y.p50, "kWh", "yield_kwh.p50"], [ "回本", economics.payback_years, "年",
    "economics.payback_years" ], ["收益率", economics.irr_pct, "%", "economics.irr_pct"], ["造价", economics.capex_cny, "元", "economics.capex_cny"], [ "年减碳",
    economics.co2_t_per_year, "t", "economics.co2_t_per_year" ]].map(([label, value, unit, field2]) =>
    `<div class="kpi" title="gz_analyze · v${result.version} · ${field2}"><span>${label}</span><b>${valueMarkup(
    value,
    unit,
    `gz_analyze · v${result.version} · ${field2}`
  )}<small>${unit}</small></b></div>`).join("")}</div>${keyFacts(result)}<h3 class="sec">为什么这样设计 <small>点一次修改，左边 3D 换到那一版；红色半透明是这次删掉的组件</small></h3>
  <div class="why">${(result.versions ?? []).map((v) => versionSummary(v, (result.versions ?? []).find((p) => p.version === v.parent_version), names)).map((v) =>
    `<button class="why-row" data-version="${v.version}" aria-pressed="${v.version === result.version}"><b>${esc(v.title)}</b>
  <span title="${esc(v.source)}">${esc(v.reason)}</span><br>${v.metrics.map((m) => `<span title="${esc(m.source)}">${m.label} ${m.delta && !Number(show(m.value,
    m.unit).replace(/,/g, "")) ? "不变" : (m.delta && m.value > 0 ? "+" : "") + valueMarkup( m.value, m.unit, m.source ) + " " + m.unit}</span>`).join(" · ")}</button>`)
    .join("") || empty("该版本未记录修改理由")}</div><h3 class="sec">版本链</h3>${versionChain(result)}${engineeringMarkup(result)}`;
}
// The handful of engineering facts a reader wants before any table: what is installed, how it is wired and fixed.
function keyFacts(result) {
  const e = result.scene?.electrical, cash = result.economics, wind = result.scene?.wind, lengths = {};
  for (const s of e?.strings ?? []) lengths[s.module_ids.length] = (lengths[s.module_ids.length] ?? 0) + 1;
  const rows = [];
  if (e?.strings?.length) {
    rows.push(['组串', `${e.strings.length} 串：` + Object.entries(lengths).sort((a, b) => b[0] - a[0]).map(([n, k]) => `${n}块×${k}`).join('、')]);
  }
  const devices = e?.inverters ?? (e ? [{model: e.inverter_model, count: e.inverter_count}] : []);
  if (devices.length) rows.push(['逆变器', devices.map(r => `${r.model} × ${r.count}`).join(' + ')]);
  const total = kind => (e?.cables?.[kind] ?? []).reduce((sum, r) => sum + (r.length_m ?? 0), 0);
  if (e?.cables) {
    rows.push(['电缆', `直流 ${show(total('dc'), 'm')} m、交流 ${show(total('ac'), 'm')} m；最大压降 ` +
      `${show(e.dc_drop_pct_max, '%')}% / ${show(e.ac_drop_pct_max, '%')}%`]);
  }
  if (wind?.version === result.version) {
    rows.push(['固定', wind.anchor_count ? `${wind.anchored_modules} 块改用锚栓（${wind.anchor_count} 个，示意）` :
      wind.clamp_count ? `夹具 ${wind.clamp_count} 个` : `压块 ${show(wind.ballast_mass_kg / 1000, 't')} 吨`]);
  }
  if (cash?.self_use) {
    rows.push(['用电', `自用 ${show(cash.self_use.effective_ratio * 100, '%')}%，加权电价 ${cash.self_use.weighted_price_cny_kwh.toFixed(3)} 元/度（示意）`]);
  }
  return rows.length ? `<dl class="key-facts">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : '';
}
function fold(key, title, note, body) {
  if (!body) return '';
  return `<details class="fold" data-fold="${key}" ${state.folds?.has(key) ? 'open' : ''}><summary><span>${title}</span>
    <small>${esc(note ?? '')}</small></summary><div class="fold-body">${body}</div></details>`;
}
function comparisonMarkup(result) {
  if (result.project?.roof?.type === 'metal') {
    return empty('彩钢瓦，不适用：顺坡平铺，倾角就是坡度，三方案（比倾角）不适用');
  }
  if (!result.compare) return empty(result.version === result.selected_version || result.selected_version == null ? "这次没有做三方案对比" :
    `v${result.version} 不在三方案对比里；在「结论」里点 v${result.selected_version} 就能回到已导出的方案`);
  return comparisonTable(result.compare, result);
}
function engineeringMarkup(result) {
  const e = result.scene?.electrical, cash = result.economics, lengths = {};
  for (const s of e?.strings ?? []) lengths[s.module_ids.length] = (lengths[s.module_ids.length] ?? 0) + 1;
  const strings = Object.entries(lengths).sort((a, b) => b[0] - a[0]).map(([n, k]) => `${n} 块 × ${k} 串`).join("、");
  const devices = (e?.inverters ?? (e ? [{model: e.inverter_model, count: e.inverter_count}] : []));
  const use = cash?.self_use, models = cash?.business_models ?? [];
  const reference = use?.algorithm === "按用电逐时算" ? `；逐时参考 ${show(use.ratio * 100, "%")}%` : "";
  const electrical = e ? `<h3>组串与逆变器</h3><p>${esc(strings)}<br>${esc(devices.map(r => `${r.model} × ${r.count}`).join(" + "))}</p>
    ${(result.rules?.items ?? []).filter(r => ['U05', 'U06', 'U07', 'G07'].includes(r.id)).map(r =>
      `<p>${esc(r.name_zh)}：${esc(show(r.value))} / ${esc(show(r.limit))} ${esc(r.unit)} · ${esc(r.status)} ${esc(r.note)}</p>`).join('')}
    ${e.cables ? `<h3>电缆</h3><p>${esc(e.wiring.method)}：${esc(e.wiring.reason)}</p>
    <table class="tbl cable-table"><thead><tr><th>类型 / 截面 mm²</th><th>总长 m</th><th>最大压降 %</th></tr></thead>
    <tbody>${e.cables.summary.map(r => `<tr><td>${r.kind === 'dc' ? '直流' : '交流四芯'} / ${r.section_mm2}</td>
    <td>${r.length_m.toFixed(1)}</td><td>${r.drop_pct_max.toFixed(2)}</td></tr>`).join('')}</tbody></table>
    <p>${esc(e.cables.positions.map(r => `${r.label === 'GRID' ? '并网点' : r.label.replace(/^I/, '逆变器')} (${r.point.map(v => v.toFixed(1))
      .join(', ')})：${r.note}`).join('；'))}</p>
    <details><summary>计算与敷设条件（示意）</summary>${e.cables.notes.map(n => `<p>${esc(n)}</p>`).join('')}</details>` : ''}` : '';
  const phases = cash?.phases ? `<p>一期绿色；二期橙色。${esc(cash.phase_note)}</p><table class="phase-table">
      <tr><th>阶段</th><th>造价元</th><th>回本年</th><th>全期净收益元</th></tr>${cash.phases.map(r =>
        `<tr>${[[r.name], [r.capex_cny], [r.payback_years, '年'], [r.profit_cny]].map(([v, unit]) => `<td>${esc(show(v, unit))}</td>`).join('')}</tr>`
        ).join('')}</table>` : '';
  const money = cash?.costs ? `${use ? `<p>${esc(use.algorithm)}：自用比例 ${show(use.effective_ratio * 100, "%")}%${reference}
    ${use.manual_override ? "（手填比例优先）" : ""}；自用电价 ${use.weighted_price_cny_kwh.toFixed(3)} 元/度（示意）</p>` : ""}
    ${financialResult(cash)}${cash?.self_use?.curtailed_kwh > 0 ? "<p>余电已按0元算：装防逆流，用不完的电被限掉，余电收入0元。</p>" : ""}` : '';
  const business = models.length ? `<p>折扣15%、租金5元/m²·年为示意；规则预算和回本按自投。</p>
    <table class="business-models"><thead><tr>${["方式", "业主投资 元", "首年 元", "25年合计 元", "投资方回本 年", "收益率 %"].map(t =>
      `<th>${t}</th>`).join("")}</tr></thead><tbody>${models.map(r => `<tr>${[[r.name], [r.owner_capex_cny], [r.owner_first_year_cny],
      [r.owner_total_cny], [r.investor_payback_years, '年'], [r.investor_irr_pct, '%']].map(([v, unit]) => `<td>${esc(show(v, unit))}</td>`).join("")}</tr>`)
      .join("")}</tbody></table>` : "";
  const capex = cash?.costs ? `${show(cash.costs.capex_cny / 1e4, '万元')} 万元 · ${cash.costs.effective_cny_per_w.toFixed(2)} 元/W` : '';
  const livestock = result.scene?.livestock;
  return `<section class="engineering"><h3 class="sec">工程与经济明细 <small>点开查看计算过程和表格</small></h3>
    ${fold('plane', '整栋坡面', `${result.project?.roof?.planes?.length ?? 0} 个面`, planeMarkup(result))}
    ${fold('electrical', '组串、逆变器与电缆', e?.cables ? `${e.strings?.length ?? 0} 串 · 最大压降 ${show(e.dc_drop_pct_max, '%')}%` : '', electrical)}
    ${fold('phases', '分期建设', cash?.phases ? `${cash.phases.length} 期` : '', phases)}
    ${fold('money', '造价、电价与税费', capex, money)}
    ${fold('livestock', livestock?.use === 'barn' ? '养殖棚说明' : '牧光互补', '', livestockResult(livestock))}
    ${fold('business', '三种投资方式', models.length ? `自投回本 ${show(cash?.payback_years, '年')} 年` : '', business)}
    </section>`;
}
function planeMarkup(result) {
  const roof = result.project?.roof;
  if (roof?.type !== 'pitched') return '';
  const yields = result.economics?.analysis_metadata?.yield_kwh?.planes ?? [];
  return `<section class="plane-result"><h3>整栋坡面</h3><p>各面共用檐口基准 ${roof.height_m} m；接缝退让
    ${roof.seam_setback_m ?? .5} m（示意）。玻璃不排板。固定导轨与锚固抗拔、防水须专项复核。</p>
    <table class="tbl"><tr><th>坡面 / 材料</th><th>坡度 / 下行朝向</th><th>块数 / kW</th><th>净 kWh/kW</th></tr>
    ${roof.planes.map(p => {
      const energy = yields.find(r => r.id === p.id), prefix = `P${p.id}-`;
      const count = (result.scene?.design?.modules ?? []).filter(m => m.id.startsWith(prefix)).length;
      const material = {metal:'彩钢瓦', concrete:'混凝土', glass:'采光玻璃'}[p.material];
      const source = p.load_capacity_kn_m2 == null ? '继承整栋' : '坡面值';
      const capacity = p.load_capacity_kn_m2 ?? roof.load_capacity_kn_m2;
      const verified = p.load_verified ?? roof.load_verified;
      return `<tr><td>P${p.id} ${material}<br><small>最低边偏移 ${p.offset_m.toFixed(3)} m；
        承重 ${capacity} kN/㎡ · ${source} · ${verified ? '已核定' : '示意待核定'}</small></td>
        <td>${p.slope_deg}° / ${p.slope_azimuth_deg}°</td><td>${count} / ${show(energy?.dc_kw)}</td>
        <td>${show(energy?.per_kw)}</td></tr>`;
    }).join('')}</table></section>`;
}
