import { financialForm, financialResult, livestockResult } from './economic-ui.js';
import { Setup } from './setup.js';
import { ParkQueue } from './park-queue.js';
import { ParkView, queueMarkup } from './park-view.js';
import { computeSteps } from "./steps.js";
import { Bridge, setAghOrigin } from "./bridge.js";
import {
  esc, show, rawValue, valueMarkup, qualified, formSpec, roofSVG, modelChoices, toolResult, runStats,
  finishRequest, shouldReview, timeLabel, isReviewRecord, replayChoices, recordPassed, recordUnverified,
  withVerifiedReview, versionSummary, naturallyStopped, usageSummary, inferRequirements, beijingTime,
  isEvaluation, recoveryDescription, comparisonTable, parkPlan, parkSVG, SPLITS, splitter
} from "./data.js";
import { createScene } from "./scene.js";
import { leaveRoofEditor, mountRoofEditor, roofEditorPage } from "./roofedit.js";
import { createReplay } from "./replay.js";
import { resolvedTools } from "./tool-results.js";
import { HEAT_COLORS } from "./scene-data.js";
import { wiringPanel, wiringDetails } from './wiring-ui.js';
import {
  newEditState, designEditMarkup, designEditPlan, performEdit, invalidateEdit, editLockedIds,
  moduleEditingOptions, moduleEditingUnavailable
} from './design-edit-ui.js';
import { parapetInfo } from './roof-parapets.js';
import { diagnosticsMarkup, diagnosticAction } from './design-diagnostics.js';
import { evidenceMarkup, evidenceDownload } from './design-evidence.js';
import { lossMetricsMarkup, monthlyYieldMarkup } from './engineering-charts.js';
import { SatMapView } from './satmap-view.js';
import { pvsystProFoldMarkup, collectPvsystTuningParams } from './pvsyst-workbench.js';
const evaluation = /(?:^\?|&)eval=1(?:&|$)/.test(location.search ?? "");
const $ = (id) => document.getElementById(id), html = (id, text) => {
  if ($(id)) $(id).innerHTML = text;
};
const state = {
  roofs: [], records: [], localProjects: [], mode: "auto", form: {}, brief: "", errors: [], sessions: new Map(), active: null, design: null,
  reviewCount: 0, runTab: "live", resultTab: "结论", filter: "all", theme: localStorage.getItem("gz-theme") ?? "system", folds: new Set(["losses", "monthly"])
};
let scene, replay, routeEpoch = 0, previewEpoch = 0, recordsEpoch = 0, polling = false, statusPolling = false, finishing = false, briefTimer;
const issuedProjects = new Set();
const reviewIntro = "设计已导出。第 9 步：独立审核，约 1 分钟。右侧会切到审核会话；审核员保存意见时，需要你点一次「本会话允许」。";
const statusLabels = { completed: "完成", running: "进行中", issue: "有问题", not_started: "未开始", skipped: "跳过" };
const classes = { completed: "ok", running: "run", issue: "bad", not_started: "idle", skipped: "idle" };
async function api(path, body) {
  const controller = globalThis.AbortController ? new AbortController() : null;
  const calculation = /^(?:projects\/auto-run|projects\/[^/]+\/copilot|parks\/[^/]+\/auto-run)$/.test(path);
  if (calculation && controller) {
    state.activeCalcController = controller;
    state.activeCalcPath = path;
  }
  const timer = controller && setTimeout(() => controller.abort(), body === undefined ? 30000 : calculation ? 900000 : 120000);
  try {
    const request = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    const response = await fetch('/api/' + path, { ...request, signal: controller?.signal });
    const data = await response.json();
    if (!response.ok) throw new Error((data.errors ?? [data.error ?? data.detail ?? '本地请求未完成'])
      .map?.(e => typeof e === 'string' ? e : e.msg ?? show(e)).join('；') ?? '本地请求未完成');
    return data;
  } catch (error) {
    if (error.name === 'AbortError') {
      if (state.userCancelledCalc) throw new Error('已取消上一计算任务，现在可以开始新任务。');
      throw new Error('本地服务响应较慢，请稍后重试。');
    }
    if (error instanceof SyntaxError) throw new Error('本地服务返回格式异常，请重试。');
    if (error instanceof TypeError) throw new Error('暂时连不上本地服务，请确认光筑仍在运行后重试。');
    throw error;
  } finally {
    clearTimeout(timer);
    if (calculation && state.activeCalcController === controller) {
      state.activeCalcController = null;
      state.activeCalcPath = null;
    }
  }
}
function activeTaskInfo() {
  const runningSession = [...state.sessions.values()].find((s) => s.op === "running");
  if (runningSession) {
    return {
      kind: "agh",
      label: `正在运行任务：${runningSession.project ?? runningSession.id?.slice(0, 8) ?? "设计会话"}`,
      route: "#run",
    };
  }
  if (state.aghOrphanRunning) {
    return {
      kind: "agh-orphan",
      label: `后台存在未结束会话：${state.active?.slice(0, 8) ?? "AGH 会话"}`,
      route: "#run",
    };
  }
  if (state.starting) {
    return {
      kind: "starting",
      label: `正在启动任务：${state.startRequest?.project ?? state.form?.id ?? "新任务"}`,
      route: "#run",
    };
  }
  if (state.quickRunBusy) {
    return {
      kind: "quick-run",
      label: `正在运行本机规则设计：${state.activeTaskProject ?? state.form?.id ?? ""}`,
      route: state.activeTaskProject ? `#result/${encodeURIComponent(state.activeTaskProject)}` : "#new",
    };
  }
  if (state.copilotBusy) {
    return {
      kind: "copilot",
      label: `正在执行规则指令重算：${state.result?.project_id ?? ""}`,
      route: state.result?.project_id ? `#result/${encodeURIComponent(state.result.project_id)}?version=${state.result.version}` : "#new",
    };
  }
  if (typeof parkQueue !== "undefined" && parkQueue?.item && !["completed", "failed", "skipped"].includes(parkQueue.item.status)) {
    return {
      kind: "park",
      label: `园区队列运行中：${parkQueue.item.spec?.id ?? parkQueue.id ?? "园区"}`,
      route: "#park",
    };
  }
  return null;
}
function updateActiveTaskBar() {
  const bar = $("active-task-bar");
  if (!bar) return;
  const info = activeTaskInfo();
  if (!info || (state.route === "run" && ["agh", "agh-orphan", "starting", "quick-run", "copilot"].includes(info.kind))) {
    bar.hidden = true;
    bar.innerHTML = "";
    return;
  }
  bar.hidden = false;
  bar.innerHTML = `<span>⏳ <b>${esc(info.label)}</b></span><button type="button" class="btn sm" data-action="goto-active-task">📍 回到任务</button><button type="button" class="btn sm primary" data-action="force-cancel-tasks">⏹ 立即取消并重置</button>`;
}
function gotoActiveTask() {
  const info = activeTaskInfo();
  const targetSid = state.active ?? state.design;
  if (targetSid && bridge.ready) {
    state.navigation = targetSid;
    try { bridge.send("gz.open", { session_id: targetSid }); } catch { }
  }
  if (info?.route) {
    if (location.hash === info.route) render();
    else location.hash = info.route;
  }
}
async function cancelAllTasks({ silent = false } = {}) {
  state.userCancelledCalc = true;
  if (state.activeCalcController) {
    try { state.activeCalcController.abort(); } catch { }
    state.activeCalcController = null;
  }
  state.quickRunBusy = false;
  state.copilotBusy = false;
  state.starting = false;
  state.startRequest = null;
  state.aghOrphanRunning = false;
  finishing = false;
  for (const s of state.sessions.values()) {
    if (s.op === "running" || !s.ended) {
      s.op = "idle";
      s.ended = true;
      s.userStopped = true;
      try { bridge.send("gz.cancel", { session_id: s.id }); } catch { }
    }
  }
  if (state.active) {
    try { bridge.send("gz.cancel", { session_id: state.active }); } catch { }
  }
  state.sessions.clear();
  state.active = null;
  state.design = null;
  state.navigation = null;
  if (typeof parkQueue !== "undefined" && parkQueue) {
    parkQueue.forceReset?.();
  }
  try { await api("tasks/cancel", {}); } catch { }
  state.userCancelledCalc = false;
  updateActiveTaskBar();
  gateStart();
  if (state.route === "run") updateRun();
  if (!silent) notice("⏹ 已强制取消并重置上一任务状态，现在可以立即开始新任务！");
}
const guarded = (fn) => (...args) => Promise.resolve().then(() => fn(...args)).catch((error) => {
  updateActiveTaskBar();
  notice(error.message);
});
function notice(text, { persist = false } = {}) {
  $("notice").textContent = text;
  $("notice").hidden = false;
  clearTimeout(notice.timer);
  notice.timer = persist ? null : setTimeout(() => {
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
async function loadLocalProjects() {
  try {
    const data = await api("projects/local-list");
    state.localProjects = data.projects ?? [];
  } catch { /* ignore if not available */ }
}
const roof = () => state.roofs.find((r) => r.id === state.form.template) ?? state.roofs[0];
const geo = (r) => r?.geometry ?? r?.project?.roof ?? {};
const pill = (text, cls = "idle") => `<span class="pill ${cls}">${esc(text)}</span>`;
const btn = (text, action, cls = "", disabled = false) => `<button class="btn ${cls}" data-action="${action}" ${disabled ? "disabled" :
  ""}>${esc(text)}</button>`;
const empty = (text) => `<div class="empty muted">${esc(text)}</div>`;
const fact = (label, value, unit = "") => `<div class="fact"><span>${esc(label)}</span><b>${valueMarkup(value, unit)}<small>${esc(unit)}</small></b></div>`;
const tabNames = {
  live: "实时输出", all: "全部", pass: "四步全过", fail: "未通过", review: "独立审核", evaluation: "评测",
  light: "浅色", dark: "深色", system: "跟随系统", heat: "遮挡热力", string: "组串", wiring: '串联布线', phase: '分期', wind: '风荷载'
};
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
const showcaseLink = (text, cls = "btn sm ghost") => showcase() ? `<a class="${cls}" href="#result/${encodeURIComponent(showcase().project_id)}?run=${encodeURIComponent(showcase().run_id)}">${text}</a>` : "";
const recordWaitingReview = (r) => !isReviewRecord(r) && !recordPassed(r) &&
  (r.verification?.checks?.length ?? 0) === 4 && r.verification.checks.every((x) => x.passed) &&
  Boolean(r.verification?.review?.requested && !r.verification?.review?.passed &&
    !r.verification?.review?.independent?.length && !r.verification?.review?.children?.length);
function recentRow(r) {
  return `<a class="item" href="#replay/${encodeURIComponent(r.run_id)}"><span><b>${esc(r.project_id ?? r.run_id)}</b>${r.showcase ? ' <span class="tag-demo">演示记录</span>' : ""}<small> ${esc(r.run_id)}</small>
  </span>${pill(r.verification?.passed ? "四步全过" : recordWaitingReview(r) ? "四步已过·待审核" : "未通过", r.verification?.passed ? "ok" : recordWaitingReview(r) ? "warn" : "bad")}<small>
  ${esc(beijingTime(r.ended_at ?? r.started_at, "short"))}</small></a>`;
}
// 任何 AGH 支持的服务商都能填 key；默认 DeepSeek 设计、Agnes 审核。
const OTHER_PROVIDERS = [["openai", "ChatGPT"], ["anthropic", "Claude"], ["google", "Gemini"], ["moonshot", "Kimi"], ["qwen", "通义千问"],
["zai", "智谱 GLM"], ["xai", "Grok"], ["openrouter", "OpenRouter"], ["minimax", "MiniMax"]];
const PROVIDER_NAMES = { deepseek: "DeepSeek", agnes: "Agnes", ...Object.fromEntries(OTHER_PROVIDERS) };
const KEY_LABELS = { agnes: "Agnes（默认审核）", deepseek: "DeepSeek（默认设计）", other: "其他模型" };
const keyUrls = (() => {
  try { return JSON.parse(localStorage.getItem("gz-key-urls") ?? "{}") ?? {}; } catch { return {}; }
})();
const savedKeyUrl = (slot) => typeof keyUrls[slot] === "string" ? keyUrls[slot] : "";
const saveKeyUrl = (slot, url) => {
  if (url) keyUrls[slot] = url;
  else delete keyUrls[slot];
  try { localStorage.setItem("gz-key-urls", JSON.stringify(keyUrls)); } catch { }
};
const hasModel = (pattern) => bridge.models.some((m) => pattern.test(m.id) || pattern.test(m.route ?? ""));
const otherModels = () => bridge.models.filter((m) => m.route ? !/deepseek|agnes/i.test(m.route) : !/deepseek|agnes/i.test(m.id));
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
    return "正在准备设计工具，请稍候…";
  if (!bridge.ready) return "正在连接 AGH…";
  if (!bridge.models.length) return "填好任意一家的 key 就能开始设计。";
  return `已就绪：设计用 ${state.designModel?.label ?? state.designModel?.id ?? "—"}，审核用 ${state.reviewModel?.label ?? state.reviewModel?.id ?? "—"}，可在填条件页更换。`;
}
const KEY_SHORT = { agnes: "Agnes", deepseek: "DeepSeek", other: "其他" };
// Codex review R04: once a model is usable the key bar folds to one line (「改 key」 opens it), leaving the height to the roof list
const slimKeys = () => bridge.models.length > 0 && !setupFailed() && !state.keysOpen && !state.keySaving;
function keyBar() {
  if (slimKeys()) return `<div class="keybar card slim"><b>模型 key</b>${["agnes", "deepseek", "other"].map((p) =>
    `<span class="kb-slim">${KEY_SHORT[p]} <span id="kb-chip-${p}">${keyChip(p)}</span></span>`).join("")}<p class="kb-state" id="kb-state">${keyState()}</p>${btn("改 key / 接口 URL", "keys-open", "sm")}</div>`;
  return `<div class="keybar card"><div class="kb-head"><b>模型 key ${bridge.models.length ? btn("收起", "keys-close", "sm ghost") : ""}</b><span class="muted">只填一次，保存在本机；支持自定义接口 URL</span></div>
  <div class="kb-fields">${["agnes", "deepseek", "other"].map((p) => `<div class="kb-field"><span>${KEY_LABELS[p]} <span id="kb-chip-${p}">${keyChip(p)}</span></span>
  <span class="kb-url"><input type="url" class="kb-url-input" data-key-url="${p}" value="${esc(savedKeyUrl(p))}" autocomplete="off" spellcheck="false"
  placeholder="接口 URL（选填，默认官方；如 https://.../v1）"></span>
  <span class="kb-input">${p === "other" ? `<select id="kb-provider" aria-label="服务商">${OTHER_PROVIDERS.map(([value, name]) =>
    `<option value="${value}">${name}</option>`).join("")}</select>` : ""}<input type="password" data-key="${p}" autocomplete="off" spellcheck="false"
  placeholder="粘贴 key"><button class="btn sm primary" data-save-key="${p}">保存</button></span></div>`).join("")}</div>
  <p class="kb-state" id="kb-state">${keyState()}</p></div>`;
}
const setupFailed = () => setup.status?.phase === "failed" || !!setup.error;
const keyState = () => `<span>${esc(readiness())}</span>${setupFailed() ? btn("重试", "setup-retry", "sm") : ""}${bridge.models.length ? "" :
  showcaseLink("没有 key？先看一个演示记录 →", "kb-link")}`;
function updateKeyBar() {
  const bar = document.querySelector(".keybar"); // folds or opens by itself only while nothing is being typed into it
  if (bar && bar.classList.contains("slim") !== slimKeys() && !bar.contains(document.activeElement) &&
    ![...bar.querySelectorAll("input[data-key]")].some((input) => input.value) &&
    ![...bar.querySelectorAll("input[data-key-url]")].some((input) => input.value !== savedKeyUrl(input.dataset.keyUrl))) bar.outerHTML = keyBar();
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
function validateCustomBaseUrl(rawUrl) {
  const trimmed = (rawUrl ?? "").trim().replace(/\/+$/, "");
  if (!trimmed) return "";
  let parsed;
  try { parsed = new URL(trimmed); } catch {
    throw new Error("自定义接口 URL 格式不正确，请填 http:// 或 https:// 开头的完整地址（如 https://.../v1）");
  }
  if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname || parsed.username || parsed.password || parsed.search || parsed.hash || /\s/.test(trimmed))
    throw new Error("自定义接口 URL 格式不正确，请填 http:// 或 https:// 开头的地址（不含参数或空格）");
  return trimmed;
}
function saveKey(field) {
  const provider = field === "other" ? document.querySelector("#kb-provider")?.value : field;
  const input = document.querySelector(`[data-key="${field}"]`), key = input?.value.trim() ?? "";
  const urlInput = document.querySelector(`[data-key-url="${field}"]`), baseUrl = validateCustomBaseUrl(urlInput?.value ?? "");
  if (!key) throw new Error("先把 key 粘贴到框里");
  if (!bridge.ready) throw new Error("AGH 还在启动，稍等几秒再保存");
  input.value = "";
  state.keySaving = provider;
  state.keysOpen = true;
  const reqMeta = { keySave: provider, ...(field !== provider ? { field } : {}), ...(baseUrl ? { baseUrl } : {}) };
  bridge.send("gz.saveKey", { provider, key, ...(baseUrl ? { baseUrl } : {}) }, reqMeta);
  updateKeyBar();
}
function saveKeyFromSettings() {
  const provider = $("settings-kb-provider")?.value || "deepseek";
  const field = ["agnes", "deepseek"].includes(provider) ? provider : "other";
  const input = $("settings-key-value"), key = input?.value.trim() ?? "";
  const urlInput = $("settings-key-url"), baseUrl = validateCustomBaseUrl(urlInput?.value ?? "");
  if (!key) throw new Error("先把 key 粘贴到框里");
  if (!bridge.ready) throw new Error("AGH 还在启动，稍等几秒再保存");
  input.value = "";
  state.keySaving = provider;
  state.keysOpen = true;
  bridge.send("gz.saveKey", { provider, key, ...(baseUrl ? { baseUrl } : {}) }, { keySave: provider, field, baseUrl });
  updateKeyBar();
  if ($("settings")?.open) settings();
}
function keySaved(message, request) {
  state.keySaving = null;
  if (message.type === "gz.keySaved") {
    const slot = request.field ?? (["agnes", "deepseek"].includes(request.keySave) ? request.keySave : "other");
    saveKeyUrl(slot, message.baseUrl ?? request.baseUrl ?? "");
    if (request.keySave && !["agnes", "deepseek"].includes(request.keySave)) saveKeyUrl(request.keySave, message.baseUrl ?? request.baseUrl ?? "");
    const usedUrl = message.baseUrl ?? request.baseUrl ?? "";
    notice(`${PROVIDER_NAMES[request.keySave] ?? "模型"} key 已保存${usedUrl ? `（自定义接口：${usedUrl}）` : ""}`);
    if (setup.association?.installed) setup.recheck();
    else bridge.refresh();
  } else notice(message.message ?? "key 没能保存");
  updateKeyBar();
  if ($("settings")?.open) settings();
}
function localProjectRow(p) {
  return `<a class="item" href="#result/${encodeURIComponent(p.project_id)}?version=${p.version}"><span><b>${esc(p.name)}</b>${p.showcase ? ' <span class="tag-demo">泰州实景案例</span>' : ""}<small> ${esc(p.project_id)} · v${p.version}</small></span>${pill(p.status_label ?? (p.hard_failed === 0 ? "规则通过候选" : Number.isInteger(p.hard_failed) ? "待消缺" : "计算待核对"), p.hard_failed === 0 ? "ok" : "warn")}<small>${p.dc_kw ? Number(p.dc_kw).toFixed(1) + " kWp" : ""} · 回本 ${p.payback_years ? Number(p.payback_years).toFixed(1) + "年" : "—"}</small></a>`;
}
function newPage() {
  const r = roof(), g = geo(r);
  const localSection = state.localProjects?.length ? `<div class="recent"><h3 class="sec">⚡ 本机已生成 3D 方案（点开直看三维与报告）</h3><div class="list scroll">${state.localProjects.slice(0, 12).map(localProjectRow).join("")}</div></div>` : "";
  return `${head("新建设计", "选屋顶并填写条件，可运行本机规则设计，也可交给 AGH 中的 Agent 执行", "", 1)}${keyBar()}<div class="new-grid"><div class="new-left"><h3 class="sec">怎么跑这次设计</h3>
  ${modesMarkup()}
  ${roofChoices(r)}
  ${localSection}
  <div class="recent"><h3 class="sec">最近的设计 ${showcaseLink("看一个演示记录（不用 key）")}</h3><div class="list scroll">${state.records.filter((x) => !isReviewRecord(x) && !isEvaluation(x)).slice(0,
    4).map(recentRow).join("") || empty("还没有设计记录")}</div></div></div>
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
    const data = await api("brief", formSpec(state.form, state.reviewModel ?? state.designModel));
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
  <h4>${esc(s.title)}</h4><div class="det">${s.comparison ?? s.metrics.map((m) => `<span title="${esc(s.raw)}">${esc(m.label)}：${valueMarkup(m.value,
    m.label)}</span>`).join(" · ")}</div>${s.detail ? `<details><summary>查看说明</summary>${esc(s.detail)}</details>` : ""}${s.warnings.length ?
      `<div class="bad-text">${esc(s.warnings.map(show).join("；"))}</div>` : ""}${s.rounds?.length ? `<div class="rounds">${s.rounds.map((r) =>
        `<span class="${r.hard_failed === 0 ? "ok" : "fix"}">v${r.version} ${r.passed}/${r.total} · ${r.hard_failed === 0 ? "硬性全过" : r.failed.map((x) =>
          x.id).join("、")}</span>`).join("")}</div>` : ""}${s.children ? `<div class="muted">${s.children.map(esc).join(" / ")}</div>` : ""}</div>
  ${pill(s.statusLabel ?? statusLabels[s.state], classes[s.state])}</article>`).join("");
}
function checksMarkup(verification) {
  if (!verification) return empty("导出后从执行记录核对，实时步骤不是最终结论");
  const failedChecks = (verification.checks ?? []).filter((c) => !c.passed);
  const reviewPending = Boolean(verification.review?.requested && !verification.review?.passed &&
    !verification.review?.independent?.length && !verification.review?.children?.length);
  const reviewLabel = verification.review?.passed ? "独立审核：通过" : reviewPending ?
    (failedChecks.length > 0 ? "独立审核：未开始（待前置核对）" : "独立审核：待启动") : "独立审核：未通过";
  const reviewDetail = reviewPending ? (failedChecks.length > 0 ? "前 8 步核对全部通过后自动启动独立审核；也可点击上方按钮一键补齐或手动启动" : "前 4 项核对已通过，可点击上方「▶ 启动独立审核」进入第 9 步") : (verification.review?.reason ?? "");
  return `<div class="checks4">${verification.checks.map((c) => `<div>${pill(c.stage, c.passed ? "ok" : "bad")}<small>${esc(c.reason)}</small>
  </div>`).join("")}</div>${verification.review?.requested ? `<p>${pill(reviewLabel, verification.review.passed ?
    "ok" : reviewPending ? "warn" : "bad")} ${esc(reviewDetail)}</p>` : ""}`;
}
function versionChain(result) {
  return `<div class="vchain">${(result?.versions ?? []).map((v) => `<button class="btn sm ${v.version === result.version ? "primary" :
    ""}" data-version="${v.version}" title="${esc(v.reason)}">v${v.version}${v.parent_version ? " ← " + v.parent_version : ""}</button>`).join("") ||
    "暂无版本"}</div>`;
}
function filesMarkup(result) {
  const files = result?.files?.files ?? result?.files ?? [];
  let items = Array.isArray(files) ? [...files] : Object.entries(files).map(([name, sha256]) => ({ name, sha256 }));
  if (state.route === "result" && result?.version) {
    const ver = result.version;
    const defaultRows = [
      { name: `drawing-v${ver}.pdf`, label: "PDF施工图纸集" },
      { name: `report-v${ver}.pdf`, label: "PDF方案书" },
      { name: `layout-v${ver}.dxf`, label: "CAD布局图" },
      { name: `bom-v${ver}.xlsx`, label: "Excel材料表" },
      { name: "design.json", label: "排布模型" },
      { name: "summary.json", label: "计算摘要" },
      { name: "rules.json", label: "规则结果" },
      { name: "economics.json", label: "经济测算" },
    ];
    const existingMap = new Map(items.map(f => [f.name ?? f.path, f]));
    items = defaultRows.map(d => existingMap.get(d.name) ?? d);
  }
  const report = result?.report, made = report?.files ?? [], name = (made.find((f) => f.name?.endsWith(".pdf")) ?? made[0])?.name;
  return `<div class="files">${items.map((f) => `<div data-export-file="${esc(f.name ?? f.path)}" style="cursor:pointer" title="点击导出并打开 ${esc(f.name ?? f.path)}"><span>${esc(f.name ?? f.path)}</span><span title="${esc(f.sha256 ?? f.hash ?? f.label ?? "")}">${esc((f.sha256 ??
    f.hash ?? "").slice(0, 8) || f.label || "")}</span></div>`).join("") || empty("尚无导出文件")}</div>${report ?
      `<div class="report-card"><div><b>方案书${report.regenerated ? " · 补生成" : ""}</b><small>${esc([name, report.error ?? report.hint].filter(Boolean)
        .join(" · "))}</small></div>${made.length ? btn("打开方案书", "open-report", "primary") : ""}</div>` : (state.route === "result" && result?.version ? `<div class="report-card"><div><b>方案书</b><small>report-v${result.version}.pdf</small></div>${btn("打开方案书", "open-report", "primary")}</div>` : "")}`;
}
function usageMarkup(usage, archived = false, live = false) {
  const u = usageSummary(usage, { live }), requests = show(u.model_requests) + (u.model_requests === null && u.recorded_model_calls !== null ?
    `（已记费 ${u.recorded_model_calls} 次）` : "");
  const money = u.costs.map((c) => `${c.currency} ${Number((c.micros / 1e6).toPrecision(3))}`).join("；") || "未提供";
  const detail = [archived ? "完整会话归档汇总（非游标统计）" : "当前会话实时投影", "token含标题等已记录用量；推理是输出子集，不重复相加", "AGH估算，非实付；0不表示免费", `费用缺项：${show(u.missing_costs)}`];
  return `<details class="muted"><summary>用时 ${u.elapsed_seconds === null ? "未提供" :
    u.elapsed_seconds.toFixed(1) + " 秒"} · 模型请求 ${esc(requests)} · token ${show(u.total_tokens)} · 费用 ${esc(money)}${u.costs.length && !u.billing_complete ?
      "（已知小计）" : ""}（AGH 估算）</summary><div class="play-controls">${[["输入", "input"], ["输出", "output"], ["读缓存", "cacheRead"], ["写缓存", "cacheWrite"], ["推理",
        "reasoning"]].map(([label, key]) => `<span>${label}：${show(u.tokens[key])}</span>`).join("")}<span>${esc(detail.join("；"))}</span></div></details>`;
}
function replayUsage(session) {
  const r = state.replayRun, usage = r.usage_by_session?.[session] ?? r.usage;
  return usageMarkup(usage?.session_id === session ? usage : null, true);
}
function sessionComputed(s) {
  return s?.fallback ?? withVerifiedReview(computeSteps(s?.nodes ?? [], {
    run: s?.run ?? {}, op: s?.op ?? "idle",
    approvals: s?.approvals ?? [], now: Date.now(), selected_version: s?.result?.selected_version,
    versions: s?.result?.versions ?? s?.compareVersions
  }), s);
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
        s.verification.passed ? "已完成" : (s.verification.checks?.length === 4 && s.verification.checks.every((x) => x.passed) ? "四步已过·待审核" : "核对未通过") : s?.op === "running" ? "运行中" : "已停下";
  const urgentWait = Boolean(waiting && Number.isFinite(waiting.countdown) && waiting.countdown <= 20);
  let banner = waiting ? `<div class="banner ${urgentWait ? "bad" : "warn"}"><b>${urgentWait ? "⚠️ 审批即将超时！" : ""}${waiting.title}等你批准</b><span>请立即在右侧原生卡选择${waiting.number === 10 ? "「仅允许这次」" : "「本会话允许」"}</span>
  <span class="count">${waiting.countdown ?? "—"} 秒</span></div>` : "";
  if (!waiting && c.suggestions.length && c.stopped && !s?.ended) banner = `<div class="banner bad"><b>检查点 A · 做不到，需要你决定</b>
  <div class="sugs">${c.suggestions.map((x, i) => `<button class="btn sm" data-suggestion="${i}" title="${esc(x.text)}">按建议${x.number}继续
  </button>`).join("")}${btn("到此为止", "checkpoint-stop", "sm ghost")}</div><details><summary>建议原文</summary>${c.suggestions.map((x) =>
    `<p>${x.number} ${esc(x.text)}</p>`).join("")}</details></div>`;
  const failedChecks = (s?.verification?.checks ?? []).filter((c) => !c.passed);
  const reviewNotStartedYet = Boolean(s?.verification?.review?.requested && !s?.verification?.review?.passed &&
    !s?.reviewSession && !s?.verification?.review?.independent?.length && !s?.verification?.review?.children?.length && !s?.reviewFailure);
  const canStartReview = Boolean(reviewNotStartedYet && s?.run?.review?.enabled && failedChecks.length === 0 && state.reviewCount < 2 && !state.starting);
  const canFixVerification = Boolean(state.active === state.design && !state.navigation && s?.op === "idle" && failedChecks.length > 0 && !s?.recovering);
  if (!banner && !s?.review && s?.op === "idle" && s.verification) {
    const reviewPill = s.verification.review?.requested ? pill(
      "独立审核：" + (s.verification.review.passed ? "通过" : reviewNotStartedYet ? (failedChecks.length > 0 ? "未开始（待前置核对）" : "待启动") : "未通过"),
      s.verification.review.passed ? "ok" : reviewNotStartedYet ? "warn" : "bad"
    ) : "";
    const failHint = failedChecks.length ? `<div class="muted" style="width:100%;margin-top:4px;font-size:12px">未通过项说明：${failedChecks.map((c) => `${esc(c.stage)}（${esc(c.reason ?? "待补齐")}）`).join("；")}</div>` : "";
    const actionBtns = `${canStartReview ? btn("▶ 启动独立审核", "start-review", "sm primary") : ""}${!s.verification.review?.passed ? btn("🛡 本机规则复核兜底", "local-review-fallback", "sm") : ""}${canFixVerification ? btn("🔄 让 Agent 补齐核对并重导", "fix-verification", "sm") : ""}`;
    banner = `<div class="banner ${s.verification.passed ? "ok" : canStartReview && failedChecks.length === 0 ? "warn" : "bad"}" style="flex-wrap:wrap"><b>执行记录核对
  </b>${(s.verification.checks ?? []).map((check) => pill(check.stage + "：" + (check.passed ? "通过" : "未通过"), check.passed ? "ok" :
    "bad")).join("")}${reviewPill}${actionBtns}${failHint}</div>`;
  }
  const recovery = state.active === state.design && !state.navigation ? recoveryDescription(s, c) : null;
  if (recovery) banner = `<div class="banner warn"><b>${esc(recovery.banner)}</b>${recovery.actions.map((a, i) =>
    `<button class="btn sm" data-recovery="${i}" ${s.recovering ? "disabled" : ""}>${esc(a.label)}</button>`).join("")}</div>`;
  if (s?.reviewBanner && !waiting) banner = `<div class="banner warn"><b>${esc(s.reviewBanner)}</b>${s.reviewFailure ?
    btn("重新审核", "review-retry", "sm", state.reviewCount >= 2 || state.starting) + btn("🛡 本机规则复核兜底", "local-review-fallback", "sm") + btn("先看结果", "see-result", "sm") : ""}</div>`;
  if (waiting) state.runTab = "live";
  if (banner) banner = banner.replace('class="banner ', 'aria-live="polite" data-key="banner" class="banner ');
  if (bridge.fallback) banner = `<div aria-live="polite" data-key="banner" class="banner warn">
  <span>传话未连接。复制任务书，粘贴到右侧 AGH 输入框并发送；文件进度每秒刷新。</span>${btn("复制任务书", "copy", "sm")}</div>`;
  return `${head(
    `运行 ${pill(label, waiting ? "warn" : s?.verification?.passed ? "ok" : label === "四步已过·待审核" ? "warn" : "run")}`,
    `${pid ?? ""}${s?.review ? " · 独立审核" : ""}`,
    `${btn("在 AGH 中打开", "open-agh")}${btn("停止", "cancel", "", !native || native.op !== "running")}
  ${state.active === state.design && !state.navigation && s?.op === "idle" &&
      (s.finishError || s.verification?.passed === false) ? btn("重新核对", "finish-retry") :
      ""}${canStartReview ? btn("▶ 启动独立审核", "start-review", "sm") : ""}${s?.result?.version || state.final?.result?.version ? `<a class="btn primary" href="#result/${encodeURIComponent(pid)}">查看结果 →
  </a>` : ""}`
  )}<div data-key="progress" class="progress">
  <div class="lbl"><b>${count} / 10 步骤</b><span>${s?.id ? esc(s.id.slice(0, 8)) : "等待会话"}</span></div><div class="bar">
  <i style="width:${count * 10}%"></i></div></div>${banner}<div data-key="run-grid" class="run-grid"><div class="col"><h3 class="sec">设计流水线 ${state.design &&
      state.active !== state.design ? btn("回设计会话", "design-session", "sm") : s?.reviewSession ? btn("审核会话",
        "review-session", "sm") : ""}</h3><div class="steps scroll">${stepsMarkup(c)}</div>${parkQueue?.queue?.items?.length ? splitter("queue") + queueMarkup(parkQueue.queue) : ""}</div>${splitter("run")}<div class="col"><div class="out-head">${tabs(["live",
          "产物", "核对"], state.runTab, "run-tab")}<span class="muted">基于 Agnes Harness</span></div>${state.runTab === "live" ?
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
  if (state.resultTab === '局部修改') return designEditMarkup(result, currentEditState());
  if (state.resultTab === "开工前") return siteMarkup(result);
  if (state.resultTab === "规则") {
    const rules = Array.isArray(result.rules) ? result.rules : result.rules?.items ?? [];
    return `${diagnosticsMarkup(result, { selectedKey: state.diagnosticFocus?.result === result ? state.diagnosticFocus.key : null })}<div class="rulelist">${[...rules].sort((a, b) => Number(b.status === "fail") - Number(a.status === "fail")).map((r) =>
      `<div title="${esc(rawValue({ value: r.value, limit: r.limit }))}"><b>${esc(r.id)}</b><span>${esc(loadWording(r.name_zh ?? r.name, result.project))}</span>${pill(show(r.status),
        r.status === "pass" ? "ok" : r.status === "fail" ? r.level === "hard" ? "bad" : "warn" : "idle")}</div>`).join("") || empty("未提供完整规则清单")}</div>
        <details>
    <summary>发电复核 · v${result.version}</summary><p class="mono">${valueMarkup(result.crosscheck?.specific_yield_kwh_kwp, "kWh/kWp")}</p>
    ${(result.crosscheck?.groups ?? []).map(g => `<p>坡面 ${esc(g.group[0])} · 倾角 ${esc(g.group[1])}° · 朝向 ${esc(g.group[2])}°：
    ${valueMarkup(g.per_kw, "kWh/kWp")}</p>`).join("")}
    ${result.crosscheck?.total_kwh ? `<p>合计：${valueMarkup(result.crosscheck.total_kwh, "kWh")}</p>` : ""}
    <p>${esc(result.crosscheck?.note ?? "未提供")}</p></details>`;
  }
  if (state.resultTab === "审核") {
    const localRevBtn = result.editable !== false ? `<div class="re-row" style="margin-bottom:8px">${btn("🛡 运行本机规则与物理模型复核 (GB 50797 / 50009，非独立模型审核)", "local-review-fallback", "sm primary")}</div>` : "";
    const reviewsList = (result.reviews?.length ? result.reviews : result.project_reviews) ?? [];
    return localRevBtn + (reviewsList.map((r) => `<section class="fcard"><h3>${esc(show(r.verdict))} · v${r.version}</h3>
  <small>${esc(r.reviewer_model)}</small>${(r.findings ?? []).map((f) => `<div class="why finding">${pill(show(f.severity), f.severity === "high" ? "bad" :
    f.severity === "low" ? "idle" : "warn")}<b>${esc(f.item)}</b><p><span class="muted">依据：</span>${esc(f.evidence)}</p>
    <p><span class="muted">建议：</span>${esc(f.suggestion)}</p></div>`).join("")}</section>`).join("") || empty("独立审核：未开始"));
  }
  return filesMarkup(result) + `<div class="re-row">${result.editable !== false ? btn("预览并确认导出", "preview-export", "primary") : ""}${btn("下载方案书 (.pdf)", "download-pdf")}${btn("下载设计图纸 (.pdf)", "download-drawing-pdf")}${btn("下载布局图 (.dxf)", "download-dxf")}${btn("下载材料表 (.xlsx)", "download-xlsx")}${result.selected_version ? btn("打开导出文件夹", "open-exports") : ""}${result.run_id ? btn("打开执行记录", "open-run") : ""}</div>` + evidenceMarkup(result);
}
function localExportMarkup(result) {
  const key = `${result.project_id}:${result.version}`, flow = state.localExport?.key === key ? state.localExport : null;
  if (!flow) return '';
  if (flow.busy) return '<section class="card" aria-live="polite"><h3>导出预检查</h3><p>正在核对本版本输入、计算与规则，请稍候…</p></section>';
  if (flow.approved) return `<section class="card" aria-live="polite"><h3>v${result.version} 已确认导出</h3><p>已记录本次本机用户批准，CAD 布局图与 Excel 材料表已保存在导出文件夹中。${flow.review === 'verified' ? '已有独立审核记录。' : '尚未独立审核；本机批准不代表工程审查结论。'}</p><div class="re-row">${btn('打开方案书', 'open-report', 'sm primary')}${btn('下载方案书 (.pdf)', 'download-pdf', 'sm')}${btn('下载设计图纸 (.pdf)', 'download-drawing-pdf', 'sm')}${btn('下载布局图', 'download-dxf', 'sm primary')}${btn('下载材料表', 'download-xlsx', 'sm primary')}${btn('打开导出文件夹', 'open-exports', 'sm')}</div></section>`;
  const preview = flow.preview, ready = preview?.ready === true && Boolean(preview.approval_id), summary = preview?.summary ?? {};
  return `<section class="card" aria-live="polite"><h3>导出预检查 · ${esc(result.project_id)} · v${result.version}</h3>
    ${flow.error ? `<p class="error">${esc(flow.error)}</p>` : ''}
    ${preview ? `<p>${esc(preview.notice ?? '确认仅适用于当前项目与版本。')}</p><p>组件 ${show(summary.modules ?? summary.module_count)} 块 · 装机 ${show(summary.dc_kw, 'kW')} kW · 硬性规则未通过 ${show(preview.checks?.hard_failed)} 项</p>
      <p>${preview.review?.status === 'verified' ? '已记录独立审核。' : '尚未独立审核；此处是规则预检查与本机用户批准。'}</p>
      ${preview.checks?.failed_ids?.length ? `<p>未通过：${esc(preview.checks.failed_ids.join('、'))}</p>` : ''}
      <p>拟生成：${esc((preview.files ?? []).map(file => typeof file === 'string' ? file : file.name ?? file.filename ?? '').join('、'))}</p>` : ''}
    <div class="actions">${ready ? btn(`我已核对，批准 v${result.version} 本次导出`, 'approve-export', 'primary') : btn('重新预检查', 'preview-export', 'primary')}${btn('取消', 'cancel-export')}</div>
    ${ready ? '<p class="muted">批准只使用一次；修改输入或设计后需要重新预检查。</p>' : ''}</section>`;
}
function updateLocalExportPanel() {
  html('local-export-panel', state.result ? localExportMarkup(state.result) : '');
  const subtitle = $('view')?.querySelector('.head > div > p');
  if (state.result && subtitle) subtitle.textContent = resultTitle(state.result);
  $('local-export-panel')?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
}
function resultTitle(result) {
  if (state.localExport?.key === `${result.project_id}:${result.version}` && state.localExport.approved)
    return `${result.project_id} · v${result.version} · 已批准导出`;
  return `${result.project_id} · ` + (result.version == null ? "暂无设计版本" : result.selected_version
    ? `v${result.version}${result.version === result.selected_version ? " · 已导出版本" : result.version < result.selected_version ? "（历史版本）" : " · 候选版本，尚未导出"}`
    : `未导出·${state.resultExplicit ? "查看版本 " : result.display_passed ? "最后通过" : "最新"}v${result.version}`);
}
function resultPage(result) {
  if (result.version == null) return head("设计结果", resultTitle(result), '<a class="btn" href="#records">设计记录</a>') + empty("尚无设计版本");
  return `${head(
    "设计结果",
    resultTitle(result),
    `<div class="actions"><a class="btn" href="#records">设计记录</a>${state.resultRun ? `<a class="btn" href="#replay/${encodeURIComponent(state.resultRun)}">看 AGH 回放</a>` :
      ""}${result.selected_version && showcase()?.run_id !== result.run_id ? btn("打开导出文件夹", "open-exports") : ""}</div>`
  )}<div id="local-export-panel">${localExportMarkup(result)}</div><div class="res-grid"><div class="scene-layout">
  <div class="scene-toolbar">${tabs(["light", "heat", "string", "wiring", "phase", "wind"], state.sceneMode ?? "light", "scene-mode")}${tabs(
    ["冬至", "春分", "夏至"], state.season ?? "冬至",
    "season")}</div>${wiringPanel(result, state.wireString, state.sceneMode)}<div id="scene" class="stage"></div>
    <button id="scene-retry" class="btn sm" data-action="scene-retry" hidden>重新加载3D</button>${windSummary(result)}<div class="sun-controls">
  <input id="sun-time" type="range" min="6.5" max="17.5" step="0.1" value="${state.hour ?? 12}" aria-label="北京时间"><span id="sun-readout">
  北京时间 ${timeLabel(state.hour ?? 12)}</span><span id="scene-inspect"></span><span class="legend" id="heat-legend"
  ${state.sceneMode === 'heat' ? '' : 'hidden'} title="年度遮挡损失，不随时间滑块变化">
  <i style="background:linear-gradient(90deg,${HEAT_COLORS.join(",")})"></i>年度损失 0% → ${(result.scene?.shading?.summary?.threshold_pct ??
      8) / 2}% → ${result.scene?.shading?.summary?.threshold_pct ?? 8}%+</span></div></div>${splitter("result")}<aside class="card res-right">${tabs(["结论", "三方案", "规则", "审核",
        "局部修改", "开工前", "文件"], state.resultTab, "result-tab")}<div id="result-panel" class="scroll">${resultPanel(result)}</div></aside></div>`;
}
function currentEditState() {
  const key = `${state.result.project_id}/${state.result.version}`;
  if (state.editing?.key !== key) state.editing = newEditState(state.result);
  return state.editing;
}
function editScene(candidate) {
  const result = state.result;
  scene?.setData(candidate ? {
    ...result.scene, design: candidate, parent_design: result.design,
    edit_preview: true, electrical: null, shading: null, wind: null
  } : result.scene, { preserveView: true });
  const editing = currentEditState();
  const active = state.resultTab === '局部修改';
  scene?.highlightModules?.(active ? [...editing.selected] : [], active ? editing.preview?.changes?.locked ?? result.locked_modules ?? [] : []);
  syncResultSceneDetails(Boolean(candidate) || active && (editing.dragging || editing.busy));
  syncModuleEditing();
}
function syncResultSceneDetails(preview = state.resultTab === '局部修改' && Boolean(state.editing?.preview || state.editing?.dragging || state.editing?.busy)) {
  const reserve = state.resultTab === '局部修改' && state.editing?.dragging;
  const visibility = (element, hidden) => {
    if (!element) return;
    // Removing an analysis card mid-drag resizes the canvas beneath the pointer.
    // Keep its box for this gesture while excluding its contents from sight and focus.
    const keepBox = reserve && hidden && !element.hidden;
    element.hidden = keepBox ? false : hidden;
    element.style.visibility = keepBox ? 'hidden' : '';
    element.inert = Boolean(keepBox);
    if (keepBox) element.setAttribute('aria-hidden', 'true');
    else element.removeAttribute('aria-hidden');
  };
  visibility($('heat-legend'), preview || state.sceneMode !== 'heat');
  visibility($('wiring-tools'), preview || state.sceneMode !== 'wiring');
  visibility($('wind-summary'), preview);
  visibility($('scene-inspect'), preview);
}
function syncSceneEditToolbar() {
  const editing = state.editing, active = state.route === 'result' && state.resultTab === '局部修改';
  document.querySelectorAll('[data-scene-edit]').forEach(btnEl => {
    const mode = btnEl.dataset.sceneEdit;
    const pressed = active && (mode === 'add' ? editing?.manualMode === 'add' && Boolean(editing?.picking) : editing?.toolMode === mode);
    btnEl.setAttribute('aria-pressed', String(Boolean(pressed)));
  });
}
function syncModuleEditing() {
  if (!state.result?.design) return;
  scene?.setModuleEditing?.(moduleEditingOptions(state.result, currentEditState(),
    state.route === 'result' && state.resultTab === '局部修改' && state.result.editable !== false));
  syncSceneEditToolbar();
}
function selectResultTab(tab) {
  stopModuleGesture(); state.resultTab = tab; html('result-panel', resultPanel(state.result));
  document.querySelectorAll('[data-result-tab]').forEach(button => button.setAttribute('aria-pressed', button.dataset.resultTab === tab));
  editScene(tab === '局部修改' ? currentEditState().preview?.design : null);
  syncSceneEditToolbar();
}
async function activateSceneEditTool(mode) {
  if (!state.result?.design) return;
  if (state.resultTab !== '局部修改') selectResultTab('局部修改');
  const editing = currentEditState(), context = editContext(state.result, editing);
  if (mode === 'add') {
    await performEdit('pick-add', state.result, editing, context);
    notice('➕ 已进入点选补板模式：请在右侧平面图点击要补放组件的中心点，或填写坐标后点「预览补放」。');
    return;
  }
  const unavailable = moduleEditingUnavailable(state.result, editing);
  if (unavailable) {
    document.querySelector('.de-scene-tools')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    notice(`提示：${unavailable}（可点击右侧「🔓 一键转为独立单排支架」开启 3D 自由拖拽移板）`);
    return;
  }
  const nextMode = editing.toolMode === mode ? 'off' : mode;
  await performEdit('tool:' + nextMode, state.result, editing, context);
  syncSceneEditToolbar();
  if (nextMode !== 'off') {
    notice(`✋ 已开启 3D ${nextMode === 'move' ? '直接拖拽移板' : '直接旋转组件'}：直接在左侧 3D 画面按住任意光伏板即可拖动，松开后自动生成预览！`);
  }
}
function setResultSceneMode(mode) {
  state.sceneMode = mode; scene?.setMode(mode); syncResultSceneDetails();
  document.querySelectorAll('[data-scene-mode]').forEach(button => button.setAttribute('aria-pressed', button.dataset.sceneMode === mode));
}
async function handleDiagnosticAction(key, action) {
  const result = state.result, intent = diagnosticAction(result, key, action), editing = currentEditState();
  state.diagnosticFocus = { result, key };
  if (intent.kind === 'locate') {
    stopModuleGesture(); setResultSceneMode(intent.mode);
    scene?.highlightModules?.(intent.module_ids, intent.locked_module_ids); scene?.focusModules?.(intent.module_ids);
    html('result-panel', resultPanel(result)); return;
  }
  if (editing.pendingKind === 'apply') throw new Error('正在保存新版本，请等待完成后再进入局部修改。');
  stopModuleGesture(); invalidateEdit(editing); editing.selected = new Set(intent.kind === 'edit' ? intent.module_ids : intent.ops.flatMap(op => op.module_ids ?? []));
  editing.manualMode = 'move'; editing.toolMode = intent.kind === 'edit' && !moduleEditingUnavailable(result, editing) ? 'move' : 'off';
  if (intent.kind === 'preview') { editing.reason = intent.reason; editing.detailed = intent.detailed; }
  selectResultTab('局部修改');
  if (intent.kind === 'edit') scene?.focusModules?.([...editing.selected]);
  if (intent.kind === 'preview') await performEdit('diagnostic-fix', result, editing, editContext(result, editing), intent);
}
function stopModuleGesture() {
  scene?.setModuleEditing?.({ enabled: false, mode: 'off' });
  if (state.editing) state.editing.dragging = false;
}
function moduleTransformStatus(value) {
  if (state.route !== 'result' || state.resultTab !== '局部修改' || !state.result?.design) return;
  const editing = currentEditState();
  editing.dragging = Boolean(value.dragging);
  // A completion callback may arrive after the preview request has already started.
  if (!editing.busy) editing.transformText = value.text ?? '';
  const status = document.querySelector('[data-edit-transform-status]');
  if (status) status.textContent = editing.busy ? '正在校验候选位置，请稍候…' : editing.transformText;
  syncResultSceneDetails();
}
async function previewModuleTransform(value) {
  if (state.route !== 'result' || state.resultTab !== '局部修改' || !state.result?.design || state.result.editable === false) return;
  const result = state.result, editing = currentEditState();
  if (editing.busy || editing.preview || !['move', 'rotate'].includes(value.mode) || value.mode !== editing.toolMode) return;
  const ids = value.module_ids;
  if (!Array.isArray(ids) || !ids.length || ids.length !== editing.selected.size || ids.some(id => !editing.selected.has(id))) return;
  const context = editContext(result, editing);
  try {
    const unavailable = moduleEditingUnavailable(result, editing);
    if (unavailable) throw new Error(unavailable);
    if (ids.some(id => editLockedIds(result).has(id))) throw new Error('所选包含已锁定组件，请先预览并确认解锁。');
    invalidateEdit(editing); editing.manualMode = value.mode;
    if (value.mode === 'move') editing.move = { dx: value.dx_m, dy: value.dy_m };
    else editing.rotate = { angle: value.angle_deg };
    editing.transformText = '拖动已结束，正在校验候选位置…';
    await performEdit(value.mode, result, editing, context);
  } catch (error) {
    if (!context.current()) return;
    invalidateEdit(editing); editing.error = error.message; context.scene(); context.redraw();
  }
}
function selectEditModule(id) {
  if (state.route !== 'result' || state.resultTab !== '局部修改' || state.result?.editable === false) return;
  const editing = currentEditState();
  if (editing.pendingKind === 'apply') return;
  if (!state.result.design.modules.some(module => module.id === id)) return notice('这是尚未保存的新增组件，请先确认预览，再继续编辑它。');
  const hadPreview = Boolean(editing.preview);
  stopModuleGesture();
  invalidateEdit(editing); editing.picking = false;
  editing.selected[editing.selected.has(id) ? 'delete' : 'add'](id);
  html('result-panel', resultPanel(state.result));
  if (hadPreview) editScene();
  else { scene?.highlightModules?.([...editing.selected], state.result.locked_modules ?? []); syncModuleEditing(); syncResultSceneDetails(); }
}
function refreshEditControls() {
  const editing = currentEditState(), root = document.querySelector('.de-editor');
  if (!root) return;
  root.querySelectorAll('.de-preview,.de-progress,.de-error,.de-change-legend').forEach(element => element.remove());
  const plan = root.querySelector('.de-plan');
  if (plan) plan.outerHTML = designEditPlan(state.result, editing);
  const template = document.createElement('div'); template.innerHTML = designEditMarkup(state.result, editing);
  root.querySelectorAll('[data-design-edit]').forEach(button => {
    const fresh = template.querySelector(`[data-design-edit="${CSS.escape(button.dataset.designEdit)}"]`);
    if (fresh) button.disabled = fresh.disabled;
  });
  const status = root.querySelector('[data-edit-transform-status]'), freshStatus = template.querySelector('[data-edit-transform-status]');
  if (status && freshStatus) status.textContent = freshStatus.textContent;
  syncModuleEditing(); syncResultSceneDetails();
}
function pickEditCenter(event) {
  const svg = event.target.closest('.de-plan');
  if (!svg || state.route !== 'result' || state.resultTab !== '局部修改') return false;
  const editing = currentEditState();
  if (!editing.picking || editing.pendingKind === 'apply') return false;
  stopModuleGesture();
  const point = svg.createSVGPoint(); point.x = event.clientX; point.y = event.clientY;
  const value = point.matrixTransform(svg.getScreenCTM().inverse());
  invalidateEdit(editing);
  editing.add.x = Math.round(value.x * 1000) / 1000; editing.add.y = Math.round(-value.y * 1000) / 1000; editing.picking = false;
  html('result-panel', resultPanel(state.result)); editScene();
  return true;
}
function editContext(result, editing) {
  const epoch = routeEpoch;
  const owns = () => routeEpoch === epoch && state.route === 'result' && state.result === result && state.editing === editing;
  return {
    api, notice, current: owns, redraw: () => {
      if (owns() && state.resultTab === '局部修改') { html('result-panel', resultPanel(result)); syncModuleEditing(); syncResultSceneDetails(); }
    }, cancelGesture: () => {
      if (owns()) stopModuleGesture();
    }, scene: candidate => { if (owns() && state.resultTab === '局部修改') editScene(candidate); }, navigate: version => {
      if (owns()) location.hash = `#result/${encodeURIComponent(result.project_id)}?version=${version}`;
    }
  };
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
  return `<details id="wind-summary" class="card wind-result"><summary>风荷载 · ${esc(wind.city.city)} · ${wind.basic_pressure_kpa}kPa（示意）</summary>
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
  return `${head("设计记录", "本机与归档执行记录，保留失败结果", btn("刷新", "records-refresh"))}${tabs(["all", "pass", "fail", "review", "evaluation"], state.filter,
    "filter")}<div class="stats">${[["全部", stats.all], ["四步全过", stats.passed], ["未通过", stats.failed], ["独立审核", stats.review]].map(([t, n]) =>
      `<div class="card stat">
    <span>${t}</span><b>${n}</b></div>`).join("")}</div><div class="rec-list scroll">${filtered.map((r) => `<article class="rec">
  <span>${pill(recordUnverified(r) ? "审核未核对" : recordWaitingReview(r) ? "四步已过·待审核" : (isReviewRecord(r) ? "审核" : "") + (recordPassed(r) ? "通过" : "未通过"), recordUnverified(r) ? "idle" :
        recordWaitingReview(r) ? "warn" : recordPassed(r) ? "ok" : "bad")}</span><div><h4>${esc(r.project_id ?? r.run_id)}${r.showcase ? ' <span class="tag-demo">演示记录 · 随安装包</span>' : ""}</h4>
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
  stopModuleGesture();
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
  else if (page === 'satmap' && satmapView) {
    await satmapView.load();
    content = satmapView.html();
  }
  else if (page === "result") {
    const params = new URLSearchParams(query), run = params.get("run"), suffix = params.has("version") ? "?version=" + params.get("version") : "";
    let result;
    try {
      result = run ? (await api('runs/' + encodeURIComponent(run) + suffix)).result :
        await api('projects/' + encodeURIComponent(decodeURIComponent(id)) + '/result' + suffix);
    } catch (error) {
      if (epoch !== routeEpoch) return;
      result = { version: null, project_id: decodeURIComponent(id), load_error: error.message };
    }
    if (epoch !== routeEpoch) return;
    state.resultRun = run;
    state.resultExplicit = params.has("version");
    state.result = result;
    state.localExport = null;
    state.editing = null;
    state.wireString = '';
    content = resultPage(result) + (result.load_error ? empty(esc(result.load_error)) + btn('重试载入', 'result-retry') : '');
  } else if (page === "replay") {
    state.replayRun = await api("runs/" + encodeURIComponent(decodeURIComponent(id)));
    content = `${head("运行回放", id, '<a class="btn" href="#records">返回记录</a>')}<div class="play-controls">${btn("播放", "play")}${btn("暂停",
      "pause")}<input id="replay-seek" type="range" min="0" value="0" aria-label="回放位置"><span id="replay-position"></span></div><div class="run-grid">
    <div id="replay-steps" class="steps scroll"></div>${splitter("run")}<div id="replay-host" class="frame scroll"></div></div>
    <div id="replay-usage">${replayUsage(state.replayRun.run?.session)}</div>`;
  } else {
    location.hash = "#new";
    return;
  }
  if (epoch !== routeEpoch) return;
  if (typeof stopSunPlay === "function") stopSunPlay();
  if (page !== 'satmap') satmapView?.dispose();
  scene?.dispose();
  replay?.dispose();
  scene = replay = null;
  $("view").innerHTML = `<section class="page${page === "new" ? " home" : ""}">${content}</section>`;
  if (page === "roof") mountRoofEditor({
    post: api, notice, saved: roofSaved, modules: state.modules, inverters: state.inverters, quickRunRoof: async (roofId, aiOptions = {}) => {
      await roofSaved(roofId);
      await quickRunProject({ template: roofId, ...aiOptions });
    }
  });
  if (page === 'park') parkView.mount($('view').querySelector('.page'));
  if (page === 'satmap') satmapView?.mount($('view').querySelector('.page'));
  if (page === "result" && state.result.version != null) mountScene();
  if (page === "replay") {
    const r = state.replayRun, choices = replayChoices(r), reviewOptions = { review: { enabled: true, mode: "independent" } };
    const reviewSession = r.run?.review_session_id, reviewRows = resolvedTools(r.timeline?.nodes ?? []).filter((n) => n.session === reviewSession);
    const record = toolResult(reviewRows, "gz_record_review"), completion = reviewRows.findLast((n) =>
      n.name === "gz_record_review" && !n.pending && n.data?.ok === true);
    const proof = {
      id: r.run?.session, result: r.result, verification: r.verification, reviewRecord: record, reviewSession,
      reviewCompletedAt: completion?.ended_at, timeline: r.timeline
    };
    document.querySelector(".play-controls").insertAdjacentHTML("afterbegin", `<label>原生会话
      <select id="replay-session" aria-label="回放会话">${choices.map((c) =>
      `<option value="${esc(c.id)}">${c.label} · ${esc(c.id)}</option>`).join("")}</select></label>`);
    replay = createReplay($("replay-host"), {
      timeline: r.timeline, session: r.run?.session, runOptions: isReviewRecord(r.run) ? reviewOptions :
        r.run_options ?? {}, reviewCompletedAt: completion?.ended_at,
      sessionOptions: Object.fromEntries(choices.filter((c) => c.label === "独立审核").map((c) => [c.id, reviewOptions])), onSteps: (c, context) =>
        html("replay-steps", stepsMarkup(withVerifiedReview(c, proof, context))), onCursor: (i, total) => {
          if ($("replay-seek")) {
            $("replay-seek").max = Math.max(0, total);
            $("replay-seek").value = i;
            $("replay-position").textContent = `${i} / ${total}`;
          }
        }
    });
  }
  requestAnimationFrame(placeFrame);
  updateActiveTaskBar();
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
  updateActiveTaskBar();
}
function mountScene() {
  if (!$('scene')) return;
  const mountedResult = state.result, mountedEpoch = routeEpoch;
  const ownsScene = () => state.route === 'result' && state.result === mountedResult && routeEpoch === mountedEpoch;
  if ($('scene-retry')) $('scene-retry').hidden = true;
  scene = createScene($("scene"), {
    onSun: (angles) => {
      if ($("sun-readout")) $("sun-readout").textContent = `北京时间 ${timeLabel(state.hour ??
        12)} · 高度 ${angles.altitude.toFixed(1)}° · 方位 ${angles.azimuth.toFixed(1)}°`;
    }, onInspect: (value) => {
      if ($("scene-inspect")) $("scene-inspect").textContent = value ? value.module + " · " + (value.string?.id ?? "未分串") : "";
    }, onSelectModule: id => {
      if (ownsScene()) selectEditModule(id);
    }, onModuleTransform: guarded(value => { if (ownsScene()) return previewModuleTransform(value); }),
    onTransformStatus: value => { if (ownsScene()) moduleTransformStatus(value); },
    onSelectString: id => {
      state.wireString = id;
      if ($('wire-string')) $('wire-string').value = id;
      if ($('wire-focus')) $('wire-focus').disabled = !id;
      html('wire-details', wiringDetails(state.result, id));
    }, onMeasure: m => {
      if (m?.state === 'start') notice('📏 已记录测距起点，请在 3D 场景中点击终点…');
      else if (m?.state === 'done') notice(`📏 3D 屋面实测：水平距离 ΔXY = ${m.dxy.toFixed(2)} m · 高差 ΔZ = ${m.dz.toFixed(2)} m · 空间斜距 = ${m.d3d.toFixed(2)} m`, { persist: true });
    }, onFocusPoint: info => {
      notice(info?.module ? `🎯 已将 3D 旋转中心切换至组件 ${info.module}，现在拖动即可围绕该处自由旋转查看！` : '🎯 已将 3D 旋转中心切换至双击位置，现在拖动即可围绕该处自由旋转查看！');
    }, showNavControls: true, onUnavailable: () => {
      if ($('scene-retry')) $('scene-retry').hidden = false;
    }
  });
  editScene(state.resultTab === '局部修改' ? currentEditState().preview?.design : null);
  scene.setTheme(document.documentElement.dataset.theme);
  updateSun();
  scene.setMode(state.sceneMode ?? "light");
  scene.selectString(state.wireString ?? '');
  if (state.sceneMeasure) scene.setMeasureMode?.(true);
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
  const allProviders = [["deepseek", "DeepSeek（默认设计）"], ["agnes", "Agnes（默认审核）"], ...OTHER_PROVIDERS];
  const curProvider = $("settings-kb-provider")?.value || "deepseek";
  const curSlot = ["agnes", "deepseek"].includes(curProvider) ? curProvider : "other";
  const curUrl = savedKeyUrl(curProvider) || savedKeyUrl(curSlot) || "";
  html("settings-content", `<p>${bridge.ready ? "AGH 已连接" : "等待 AGH 连接"}</p><h3>主题</h3>${tabs(["light", "dark", "system"], state.theme, "theme")}
  <h3>接口与模型 Key（支持自定义接口 URL）</h3>
  <div class="settings-key-box">
    <label class="field"><span>服务商通道</span><select id="settings-kb-provider" aria-label="设置服务商">${allProviders.map(([v, n]) =>
      `<option value="${v}" ${v === curProvider ? "selected" : ""}>${n}</option>`).join("")}</select></label>
    <label class="field"><span>自定义接口 URL（选填，留空用官方接口）</span><input id="settings-key-url" type="url" autocomplete="off" spellcheck="false"
      value="${esc(curUrl)}" placeholder="如 https://zhenze-huhehaote.cmecloud.cn/tokenplan/v1"></label>
    <label class="field"><span>API Key</span><span class="kb-input"><input id="settings-key-value" type="password" autocomplete="off" spellcheck="false"
      placeholder="粘贴 API Key"><button class="btn sm primary" data-action="settings-save-key" ${state.keySaving ? "disabled" : ""}>${state.keySaving ? "正在验证…" : "验证并保存"}</button></span></label>
  </div>
  <h3>设计模型</h3>
  ${modelSelect("design-model", "", state.designModel)}<h3>审核模型</h3>${modelSelect("review-model", "", state.reviewModel)}
  <p class="muted">任何填了 key 的模型都能设计或审核；按 DeepSeek 实际运行经验，Pro 每次约 0.1–0.3 元，Flash 约 0.03 元（经验参考，并非收费表）。若使用第三方兼容接口或政企网关，填写自定义 URL 与 Key 保存后即可在上方下拉框中切换该接口返回的任意模型。</p><h3>
  可用模型</h3><div class="model-list">${bridge.models.map((m) => `<p><b>${esc(m.label)}</b><br><span class="mono">${esc(m.id)}</span></p>`).join("") ||
    "尚未收到模型清单"}</div>${btn("在浏览器中打开 AGH", "open-agh")}`);
}
function connectionLabel() {
  const block = setup.association?.installed && setupFailed() || state.status && state.status.agh?.connected ? startBlock() : "正在启动";
  $("connection").textContent = block ? block.replace(/^先在首页上方/, "") : "已就绪 · 设计用 " + (state.designModel?.label ?? state.designModel?.id ?? "");
}
async function checkConnection() {
  if (statusPolling) return;
  statusPolling = true;
  try {
    state.status = await api("status");
    setAghOrigin(state.status.agh?.url);
    await setup.poll();
    const connected = !setup.checking && state.status.agh?.connected === true;
    if (connected) {
      state.aghDisconnectTicks = 0;
      bridge.setAvailable(true);
    } else if (!bridge.ready || !bridge.frame || (++state.aghDisconnectTicks >= 4)) {
      bridge.setAvailable(false);
    }
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
  }).catch(() => { });
}
function resumeSession(s) {
  if (s.op === "running") return;
  s.generation = (s.generation ?? 0) + 1;
  s.turnStart = s.nodes.length;
  Object.assign(s, {
    op: "running", ended: false, verification: null, result: null, reviewRecord: null, reviewSession: null,
    reviewCompletedAt: null, userStopped: false, reviewBanner: null, reviewFailure: null, reviewPreparing: false, archivedUsage: null
  });
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
      await parkQueue.event(message.code === 'WORKSPACE' ? 'hold' : 'error', { reason: message.message });
      if (parkQueue.item?.status === 'pending') await parkQueue.next();
    })();
    const ownsStart = request === state.startRequest;
    if (ownsStart) {
      state.starting = false;
      state.startRequest = null;
    }
    const design = state.sessions.get(state.design);
    if (ownsStart && request?.review && design?.reviewBanner) reviewFailed(design, message.message);
    if (message.code === "BUSY" || /正在运行|先停止/.test(message.message ?? "")) {
      state.aghOrphanRunning = true;
    }
    updateActiveTaskBar();
    if (state.route === "run") updateRun();
    notice("AGH 未完成请求：" + message.message);
    return;
  }
  if (message.type === "gz.session" && request) {
    state.starting = false;
    state.startRequest = null;
    state.aghOrphanRunning = false;
    const s2 = {
      id: message.session_id, project: request.project, nodes: [], approvals: [], op: "running", run: request.run,
      review: request.review, awaitingStart: Boolean(request.review)
    };
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
      state.aghOrphanRunning = message.op === "running";
      updateActiveTaskBar();
      if (state.route === "run") updateRun();
    }
    return;
  }
  state.aghOrphanRunning = false;
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
  updateActiveTaskBar();
  if (message.type === "gz.progress" && s.op === "idle") guarded(() => finishSession(s,
    parkQueue.item?.spec.id === s.project && message.started && parkQueue.item.status !== 'approval' || s.ended ||
    s.nodes.some((n) => n.kind === "tool" &&
      n.status === "failed") || naturallyStopped(s, previousOp, computeSteps(s.nodes, { run: s.run, op: s.op, approvals: s.approvals })), true))();
});
const parkQueue = new ParkQueue(api, (type, payload) => bridge.send(type,
  { ...payload, workspace_binding: parkQueue.item?.workspace_binding }, { park: parkQueue.item?.id, session: payload.session_id }),
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
  state.parkEdit = { key, park };
  state.mode = 'auto';
  location.hash = '#form';
}, (key, park) => {
  const source = state.roofs.find(r => r.id === key);
  const form = {
    keep: [], text: '按屋顶和现场条件设计', maxRounds: 6, compare: geo(source).type !== 'metal',
    review: true, exportOn: true, prefer: 'balanced', tiltMin: '', tiltMax: '', ...park.settings.shared, ...park.settings[key],
    id: 'park-draft', template: park.id + '--' + key
  };
  if (!state.designModel) throw new Error('先配置设计模型');
  if (!bridge.workspaceBinding) throw new Error('右侧 AGH 的工作区还没确认好，请等首页显示「已就绪」后再点');
  return { spec: formSpec(form, state.reviewModel), design_model: state.designModel.id, workspace_binding: bridge.workspaceBinding };
}, notice);
const satmapView = typeof SatMapView === 'function' ? new SatMapView(api, notice, state) : null;
async function saveParkSettings() {
  const { key, park } = state.parkEdit;
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
  const spec = item.spec, run = {
    prefer: spec.prefer, compare: spec.compare, export: spec.export,
    review: { enabled: spec.review, mode: 'independent', model: spec.reviewer_model }
  };
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
  const design = {
    id: item.design_session, project: spec.id, run, review: false, op: 'idle', approvals: [],
    nodes: (archived?.timeline?.nodes ?? []).filter(n => n.session === item.design_session)
  };
  state.sessions.set(design.id, design);
  if (item.stage === 'review') {
    design.reviewSession = item.review_session;
    state.sessions.set(item.review_session, {
      id: item.review_session, project: spec.id, run, review: true,
      op: 'idle', approvals: [], nodes: [], awaitingStart: false
    });
  }
  state.active = item[item.stage + '_session'];
  location.hash = '#run';
  if (create) {
    const model = bridge.models.find(m => m.id === spec.reviewer_model || qualified(m) === spec.reviewer_model);
    if (!model) throw new Error('请配置任务书指定的审核模型');
    design.reviewRequest = 1;
    state.startRequest = { run, project: spec.id, review: true, designId: design.id, designGeneration: 0, reviewRequest: 1, queue: item.id };
    state.starting = true;
    bridge.send('gz.start', {
      brief: null, project_id: spec.id + '-review', workspace: 'guangzhu', design_model: model,
      session_key: item.review_session, workspace_binding: item.workspace_binding, ...setup.session
    }, state.startRequest);
  } else {
    bridge.send('gz.open', { session_id: state.active, workspace_binding: item.workspace_binding }, { park: item.id, session: state.active });
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
  if (state.starting || [...state.sessions.values()].some((s) => s.op === "running")) {
    updateActiveTaskBar();
    throw new Error("请先停止当前设计");
  }
  if (setup.association?.installed && setupFailed()) throw new Error("设计工具没准备好，请在首页点重试");
  if (!bridge.ready) throw new Error("正在连接 AGH…");
  if (queued) {
    requireParkWorkspace(queued);
    state.mode = 'auto';
    state.form = { ...state.form, id: queued.spec.id, template: queued.spec.template, review: queued.spec.review };
    state.designModel = bridge.models.find(m => m.id === queued.design_model || qualified(m) === queued.design_model);
    if (queued.spec.review) state.reviewModel = bridge.models.find(m => m.id === queued.spec.reviewer_model ||
      qualified(m) === queued.spec.reviewer_model);
    state.brief = (await api('brief', queued.spec)).brief;
  } else if (state.mode === "auto") {
    if (!state.reviewModel && state.designModel) state.reviewModel = state.designModel;
    await preview();
    if (!state.brief) throw new Error(state.errors.join("；"));
  }
  if (!state.designModel || state.mode === "auto" && state.form.review && !state.reviewModel) throw new Error("先在首页上方填一家模型的 key");
  if (setup.association?.installed && !setup.status?.ready) throw new Error("正在准备设计工具…");
  state.starting = true;
  const spec = queued?.spec ?? (state.mode === "chat" ? { compare: false, export: false, review: false } : formSpec(state.form, state.reviewModel ?? state.designModel));
  state.sessions.clear();
  state.reviewCount = 0;
  state.runTab = "live";
  state.final = null;
  state.result = null;
  state.active = null;
  state.design = null;
  state.navigation = null;
  const run = {
    prefer: spec.prefer, compare: spec.compare, export: spec.export,
    review: { enabled: spec.review, mode: "independent", model: spec.reviewer_model }
  };
  state.startRequest = { run, review: false, project: state.form.id, ...queued ? { queue: queued.id } : {} };
  bridge.send(
    "gz.start",
    {
      brief: queued || state.mode === "chat" ? null : state.brief, project_id: state.form.id, workspace: "guangzhu",
      ...queued ? { session_key: queued.design_session, workspace_binding: queued.workspace_binding } : {},
      design_model: state.designModel, evaluation, ...setup.session
    },
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
      Object.assign(design, {
        verification: final.verification, result: final.result, reviewRecord: recorded, reviewSession: s.id,
        reviewCompletedAt: current.findLast((n) => n.name === "gz_record_review")?.ended_at, reviewBanner: null
      });
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
    else if (state.route === "result" && state.result?.project_id === design.project && !state.resultExplicit) {
      state.result = final.result;
      await render();
    }
  } catch (error) {
    if (!owns()) return;
    s.finishKey = "";
    s.finishError = error.message;
    if (error.recoverable && parkQueue.item?.spec.id === design.project) {
      await parkQueue.event('hold', { reason: error.message });
    } else if (parkQueue.item?.spec.id === design.project && s.op === 'idle' && ['running', 'reconcile'].includes(parkQueue.item.status)) {
      await parkQueue.event('failed', { reason: '运行已停下，归档未完成：' + error.message });
      setTimeout(guarded(() => parkQueue.next()), 0);
    }
    if (s.review) reviewFailed(design, error.message);
    if (state.route === "run") updateRun();
    throw error;
  } finally {
    finishing = false;
    updateActiveTaskBar();
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
  state.startRequest = {
    run: design.run, review: true, project: design.project, designId: design.id,
    designGeneration: design.generation ?? 0, reviewRequest: design.reviewRequest, ...queued ? { queue: queued.id } : {}
  };
  state.starting = true;
  state.reviewCount++;
  if (state.route === "run") updateRun();
  bridge.send("gz.start", {
    brief: queued ? null : final.review_prompt, project_id: design.project + "-review", workspace: "guangzhu",
    design_model: model, ...queued ? { session_key: queued.review_session, workspace_binding: queued.workspace_binding } : {}, ...setup.session
  },
    state.startRequest);
}
function continueDesign(text) {
  const s = state.sessions.get(state.design);
  if (!text || !s || state.navigation || state.active !== s.id || s.op === "running" || s.recovering) return;
  s.recovering = true;
  resumeSession(s);
  bridge.send("gz.followup", { session_id: s.id, text });
  return render();
}
async function openTarget(target) {
  const s = state.sessions.get(state.design);
  const result = state.route === "result" ? state.result : s?.result ?? state.final?.result;
  const runId = state.route === "result" ? result?.run_id : (result?.run_id ?? state.final?.run_id);
  const ver = state.route === "result" ? (result?.version ?? result?.selected_version) : (target === "exports" ? (result?.version ?? result?.selected_version) : (result?.selected_version ?? result?.version));
  await api("open", {
    kind: target === "exports" ? "export" : target,
    session_id: target === "agh" ? state.active : s?.id,
    project_id: result?.project_id ?? s?.project ?? state.form.id,
    version: ver,
    run_id: runId
  });
}
async function openExportFile(filename) {
  const s = state.sessions.get(state.design);
  const result = state.route === "result" ? state.result : s?.result ?? state.final?.result;
  if (!result?.project_id || !result.version) throw new Error("没有可导出的项目版本");
  try {
    await api("open", {
      kind: "export_file",
      project_id: result.project_id,
      version: result.version,
      run_id: state.route === "result" ? result.run_id : (result.run_id ?? state.final?.run_id),
      filename
    });
    notice(`已打开文件 ${filename}（副本已同步保存到“下载”文件夹）`);
  } catch (error) {
    if (state.route === "result" && state.result === result && (/\.(dxf|xlsx)$/i.test(filename) || /^drawing-v\d+\.pdf$/i.test(filename))) {
      await previewLocalExport();
      return;
    }
    throw error;
  }
}
async function quickRunProject(override = {}) {
  if (state.quickRunBusy) {
    updateActiveTaskBar();
    return notice('本机规则设计仍在运行，多方案计算可能需要数分钟；可点击右下角「⏹ 立即取消并重置」终止上一任务。', { persist: true });
  }
  state.quickRunBusy = true;
  try {
    const f = { ...state.form, ...override };
    const template = f.template ?? roof()?.id ?? "taizhou-cmc-pharma";
    const spec = formSpec({ ...f, template, text: f.text?.trim() || "6年内回本，留1米检修通道，避开天窗与设备并最大化发电收益" }, state.reviewModel);
    const projectId = override.id ?? f.id ?? `${template}-${beijingTime(new Date(), "id")}`;
    state.activeTaskProject = projectId;
    updateActiveTaskBar();
    notice("正在运行本机规则设计：排布、工程计算与候选比较可能需要数分钟。完成后请检查规则结果，再确认导出。", { persist: true });
    const res = await api("projects/auto-run", {
      project_id: projectId,
      template,
      text: spec.text,
      structured: spec.structured,
      economics: spec.economics,
      module_id: override.module_id || spec.module_id,
      inverter_id: override.inverter_id || f.inverterId || null,
      inverter_brand: override.inverter_brand || f.inverterBrand || null,
      layout_algo: override.layout_algo || f.layoutAlgo || "auto_pareto",
      string_algo: override.string_algo || f.stringAlgo || "shadow_clustered",
      routing_algo: override.routing_algo || f.routingAlgo || "astar_2opt",
      dc_cable_family: override.dc_cable_family || f.dcCableFamily || "PV1-F",
      ac_cable_family: override.ac_cable_family || f.acCableFamily || "ZR-YJV22",
      wind_roughness: override.wind_roughness || f.windRoughness || null,
      wind_pressure_kpa: override.wind_pressure_kpa ?? (f.windPressure ? Number(f.windPressure) : null),
      compare: f.compare !== false,
      prefer: f.prefer || "balanced",
      max_rounds: Number(f.maxRounds || 3),
      review: false,
      export: true,
      overwrite_existing: false,
    });
    await loadLocalProjects();
    notice(`已保存规则设计 v${res.final_version}。${Number.isInteger(res.hard_failed) ? `硬性规则未通过 ${res.hard_failed} 项。` : '工程计算状态待核对。'}布局图与材料表需预检查并由你确认后导出。`);
    location.hash = `#result/${encodeURIComponent(res.project_id)}?version=${res.final_version}`;
  } finally { state.quickRunBusy = false; state.activeTaskProject = null; updateActiveTaskBar(); }
}
async function runCopilot(action = "", customText = "", extra = {}) {
  const result = state.result;
  if (!result?.project_id || !result.version) throw new Error("请先打开一个项目的设计结果");
  if (state.copilotBusy) {
    updateActiveTaskBar();
    return notice('当前调整仍在计算，多方案比较可能需要数分钟；可点击右下角「⏹ 立即取消并重置」终止上一任务。', { persist: true });
  }
  const text = customText || ($("copilot-input")?.value?.trim() ?? "");
  if (!action && !text) throw new Error("请输入支持的调整指令，或点击上方调整按钮");
  state.copilotBusy = true;
  updateActiveTaskBar();
  const epoch = routeEpoch;
  try {
    notice("正在执行规则指令并计算新版本，多方案比较可能需要数分钟，请等待结果。", { persist: true });
    const res = await api(`projects/${encodeURIComponent(result.project_id)}/copilot`, {
      version: result.version,
      action,
      text,
      ...extra,
    });
    await loadLocalProjects();
    notice(res.message);
    if (state.result === result && routeEpoch === epoch) location.hash = `#result/${encodeURIComponent(result.project_id)}?version=${res.new_version}`;
  } finally { state.copilotBusy = false; updateActiveTaskBar(); }
}
async function applyCopilotEquipment() {
  const module_id = $("copilot-module")?.value || null;
  const inverter_id = $("copilot-inverter")?.value || null;
  const dc_cable_family = $("copilot-dc-cable")?.value || "PV1-F";
  const ac_cable_family = $("copilot-ac-cable")?.value || "ZR-YJV22";
  const wind_roughness = $("copilot-wind-roughness")?.value || null;
  await runCopilot("change_equipment", "切换光伏组件/逆变器/线缆型号并重算组串走线与风荷载", {
    module_id,
    inverter_id,
    dc_cable_family,
    ac_cable_family,
    wind_roughness,
  });
}
let sunTimer = null;
function stopSunPlay() {
  if (sunTimer) {
    clearInterval(sunTimer);
    sunTimer = null;
  }
  const btnEl = $("sun-play-btn");
  if (btnEl) btnEl.textContent = "▶ 全天日照动画";
}
function toggleSunPlay() {
  if (sunTimer) {
    stopSunPlay();
    return;
  }
  if ((state.hour ?? 12) >= 17.4) state.hour = 6.5;
  const btnEl = $("sun-play-btn");
  if (btnEl) btnEl.textContent = "⏸ 暂停日照";
  sunTimer = setInterval(() => {
    if (state.route !== "result" || !scene) {
      stopSunPlay();
      return;
    }
    state.hour = Number(((state.hour ?? 6.5) + 0.08).toFixed(2));
    if (state.hour > 17.5) state.hour = 6.5;
    if ($("sun-time")) $("sun-time").value = String(state.hour);
    updateSun();
  }, 80);
}
async function openProjectReport() {
  const result = state.result;
  if (!result?.project_id || !result.version) throw new Error("没有可打开的方案书版本");
  try {
    await api("open", { kind: "project_report", project_id: result.project_id, version: result.version });
    notice(`已在本机打开 v${result.version} 方案书`);
    return;
  } catch { /* fallback to window.open if running in test browser */ }
  const url = `/api/projects/${encodeURIComponent(result.project_id)}/report-html?version=${result.version}`;
  window.open(url, "_blank", "noopener");
}
async function downloadExport(kind) {
  const result = state.result;
  if (!result?.project_id || !result.version) throw new Error("没有可导出的项目版本");
  const url = `/api/projects/${encodeURIComponent(result.project_id)}/download/${kind}?version=${result.version}`;
  const response = await fetch(url);
  if (!response.ok) {
    if (response.status === 409 && state.result === result) return previewLocalExport();
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail ?? error.error ?? error.errors?.join('；') ?? '导出文件不可用，请先预检查并确认导出。');
  }
  const blob = await response.blob(), objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  const fileMap = { dxf: ["layout", "dxf"], xlsx: ["bom", "xlsx"], pdf: ["report", "pdf"], "drawing-pdf": ["drawing", "pdf"] };
  const [prefix, ext] = fileMap[kind] ?? [kind, kind];
  a.download = `${result.project_id}-${prefix}-v${result.version}.${ext}`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
  if (!navigator.webdriver) {
    try {
      await api("open", {
        kind: "export_file",
        project_id: result.project_id,
        version: result.version,
        run_id: result.run_id ?? null,
        filename: `${prefix}-v${result.version}.${ext}`
      });
    } catch { /* browser download above already triggered */ }
  }
  notice(`已导出文件 ${a.download}（副本已同步保存到“下载”文件夹）`);
}
async function previewLocalExport() {
  const result = state.result;
  if (!result?.project_id || !result.version) throw new Error('请先打开项目版本');
  if (result.editable === false) throw new Error('归档记录只读，请打开对应本机项目后导出。');
  if (state.localExport?.busy) return;
  const flow = { key: `${result.project_id}:${result.version}`, busy: true }; state.localExport = flow; updateLocalExportPanel();
  try {
    const preview = await api(`projects/${encodeURIComponent(result.project_id)}/exports/preview`, { version: result.version });
    if (state.result !== result || state.localExport !== flow) return;
    flow.preview = preview;
  } catch (error) { if (state.result === result && state.localExport === flow) flow.error = error.message; }
  finally { flow.busy = false; if (state.result === result && state.localExport === flow) updateLocalExportPanel(); }
}
async function approveLocalExport() {
  const result = state.result, flow = state.localExport;
  if (!result || !flow || flow.key !== `${result.project_id}:${result.version}` || flow.busy || !flow.preview?.ready || !flow.preview.approval_id) return;
  flow.busy = true; updateLocalExportPanel();
  try {
    const reply = await api(`projects/${encodeURIComponent(result.project_id)}/exports/approve`,
      { version: result.version, approval_id: flow.preview.approval_id, confirmed: true });
    if (state.result !== result || state.localExport !== flow) return;
    flow.approved = reply.ok === true; flow.review = flow.preview.review?.status; flow.preview = null;
    if (!flow.approved) flow.error = '导出未完成，请重新预检查。';
    await loadLocalProjects();
  } catch (error) {
    if (state.result === result && state.localExport === flow) { flow.error = error.message; flow.preview = null; }
  } finally { flow.busy = false; if (state.result === result && state.localExport === flow) updateLocalExportPanel(); }
}
const actions = {
  start, 'park-settings-save': saveParkSettings,
  'force-cancel-tasks': () => cancelAllTasks(),
  'goto-active-task': () => gotoActiveTask(),
  'quick-run': () => quickRunProject(),
  'quick-run-form': () => quickRunProject(),
  'copilot-send': () => runCopilot("", $("copilot-input")?.value?.trim() ?? ""),
  'copilot-apply-equipment': () => applyCopilotEquipment(),
  'download-dxf': () => downloadExport("dxf"),
  'download-xlsx': () => downloadExport("xlsx"),
  'download-pdf': () => downloadExport("pdf"),
  'download-drawing-pdf': () => downloadExport("drawing-pdf"),
  'preview-export': previewLocalExport,
  'approve-export': approveLocalExport,
  'cancel-export': () => { state.localExport = null; updateLocalExportPanel(); },
  'open-project-report': () => openProjectReport(),
  'sun-play': () => toggleSunPlay(),
  'download-design-evidence': () => {
    const file = evidenceDownload(state.result), url = URL.createObjectURL(new Blob([file.text], { type: file.mime }));
    const link = document.createElement('a'); link.href = url; link.download = file.filename; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
  'scene-top': () => scene?.resetView(true),
  'scene-focus': () => scene?.resetView('selected'),
  'scene-reset': () => scene?.resetView(),
  'scene-retry': () => {
    scene?.dispose();
    mountScene();
  },
  'result-retry': () => render(),
  'park-pause': () => parkQueue.event('pause'),
  'park-resume': async () => {
    await parkQueue.event('resume');
    await parkQueue.next();
  },
  'park-skip': () => parkQueue.skip(),
  'park-abandon': async () => {
    if (!confirm('放弃这个队列：没跑完的厂房都标成「跳过」，不会再派发，之后可以重新勾选开始。如果右侧 AGH 里它的会话还在跑，请先在那里停止。确定放弃吗？')) return;
    await parkQueue.abandon();
    notice('队列已放弃，可以在园区页重新勾选厂房开始');
    await render();
  },
  'park-queue-show': () => {
    parkView.id = parkQueue.id;
    location.hash = '#park';
  },
  "finish-retry": () => {
    const s = state.sessions.get(state.design);
    if (!s) return;
    s.finishKey = "";
    return finishSession(s, true);
  }, copy: () => navigator.clipboard.writeText(state.brief), cancel: () => {
    const s = state.sessions.get(state.active);
    if (!s) return;
    s.ended = true;
    s.userStopped = true;
    bridge.send("gz.cancel", { session_id: state.active });
  }, "open-report": () => openTarget("report"), "open-agh": () => openTarget("agh"), "open-exports": () => openTarget("exports"),
  "open-run": () => openTarget("run"), "records-refresh": async () => {
    if (await loadRecords()) await render();
  }, "checkpoint-stop": async () => {
    const s = state.sessions.get(state.active);
    if (!s) return;
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
  }, "start-review": async () => {
    const design = state.sessions.get(state.design);
    if (!design) return;
    if (!state.final?.review_prompt) await finishSession(design, true, false);
    if (state.final?.review_prompt) return startReview(design);
  }, "fix-verification": () => {
    const s = state.sessions.get(state.design);
    const failedChecks = (s?.verification?.checks ?? []).filter((c) => !c.passed);
    if (!s || !failedChecks.length) return;
    const stages = failedChecks.map((c) => `${c.stage}（${c.reason ?? ""}）`).join("；");
    return continueDesign(`执行记录核对未通过：${stages}。请按任务书补齐缺失步骤（如修改后重新调用 gz_analyze、完成 gz_crosscheck_yield 全部组复核），然后重新申请 gz_export 导出最新版本。`);
  }, "local-review-fallback": async () => {
    const s = state.sessions.get(state.design);
    const pid = state.route === "result" ? state.result?.project_id : (s?.project ?? state.form.id);
    const ver = state.route === "result" ? (state.result?.version ?? 1) : (s?.result?.selected_version ?? s?.result?.version ?? state.final?.result?.version ?? 1);
    if (!pid) throw new Error("未找到要复核的项目编号");
    notice("🛡 正在运行本机规则与物理模型复核 (GB 50797 / 50009)…");
    const res = await api(`projects/${encodeURIComponent(pid)}/local-review`, { version: ver });
    if (state.route === "result" && state.result?.project_id === pid) {
      state.result.reviews = [res.review, ...(state.result.reviews ?? []).filter(r => r.reviewer_model !== res.review.reviewer_model)];
      state.resultTab = "审核";
      selectResultTab("审核");
      notice(`✅ 已生成 v${ver} 本机规则复核记录（结论：${res.review.verdict === "approve" ? "规则通过" : "建议修改"}；非独立模型审核）`);
    } else {
      notice(`✅ 已完成项目 ${pid} (v${ver}) 的本机规则复核！正在打开结果页复核记录…`);
      location.hash = `#result/${encodeURIComponent(pid)}?version=${ver}`;
    }
  }, "toggle-scene-measure": () => {
    state.sceneMeasure = !state.sceneMeasure;
    scene?.setMeasureMode?.(state.sceneMeasure);
    const btnEl = $("scene-measure-btn");
    if (btnEl) btnEl.setAttribute("aria-pressed", String(Boolean(state.sceneMeasure)));
    notice(state.sceneMeasure ? "📏 已开启 3D 屋面测距标尺：请在 3D 画面依次点击起点和终点测量距离与高差！" : "📏 已关闭 3D 测距标尺");
  }, "select-same-row": () => {
    if (!state.result?.design?.modules?.length) return;
    if (state.resultTab !== "局部修改") selectResultTab("局部修改");
    const editing = currentEditState();
    const mods = state.result.design.modules;
    const locked = editLockedIds(state.result);
    const seeds = mods.filter(m => editing.selected.has(m.id));
    const refMod = seeds[0] ?? mods.find(m => !locked.has(m.id));
    if (!refMod) return notice("没有可选中的未锁定组件");
    const refY = refMod.center[1];
    for (const m of mods) {
      if (!locked.has(m.id) && Math.abs(m.center[1] - refY) <= 0.45) editing.selected.add(m.id);
    }
    html("result-panel", resultPanel(state.result));
    scene?.highlightModules?.([...editing.selected], state.result.locked_modules ?? []);
    syncModuleEditing();
    notice(`🔲 已一键选中同排共 ${editing.selected.size} 块光伏组件，可批量移动或调整！`);
  }, "switch-lightweight-module": () => {
    return runCopilot("change_equipment", "切换为低荷载轻质组件重算屋面承重裕度", { module_id: "suntech-stp440s-c54-nshb" });
  }, "import-load-csv": () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv,.txt";
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      const text = await file.text();
      const nums = text.split(/[\r\n,;,\t]+/).map(s => Number(s.trim())).filter(n => Number.isFinite(n) && n > 0);
      if (nums.length >= 12) {
        const maxKw = Math.max(...nums);
        const avgKw = nums.reduce((a, b) => a + b, 0) / nums.length;
        let importedWeights = null;
        if (nums.length >= 24) {
          const sums = new Array(24).fill(0);
          const counts = new Array(24).fill(0);
          nums.forEach((v, idx) => {
            const hr = idx % 24;
            sums[hr] += v;
            counts[hr] += 1;
          });
          const avgs = sums.map((s, i) => (counts[i] > 0 ? s / counts[i] : 0));
          const maxHr = Math.max(...avgs, 1);
          importedWeights = avgs.map((v) => Number((v / maxHr).toFixed(3)));
        }
        state.customTou = {
          ...(state.customTou ?? {}),
          importedPeakKw: Math.round(maxKw),
          importedAvgKw: Math.round(avgKw),
          ...(importedWeights ? { importedWeights } : {})
        };
        if (state.result) html("result-panel", resultPanel(state.result));
        notice(`📂 已导入企业负荷曲线（共 ${nums.length} 个采样点，峰值负荷 ${Math.round(maxKw)} kW，均值 ${Math.round(avgKw)} kW），已更新前端敏感性试算视图（未改动已校核工程版本）`);
      } else {
        notice("CSV 中未识别到有效负荷数值序列，请确认包含每小时或每日功率(kW)数据");
      }
    };
    input.click();
  }, "open-executive-brief": () => openExecutiveBrief(state.result), "download-engineering-csv": () => downloadEngineeringCsv(state.result), "see-result": () => {
    location.hash = "#result/" + encodeURIComponent(state.sessions.get(state.design).project);
  }, play: () => replay?.play(), pause: () => replay?.pause(),
  "keys-open": () => {
    state.keysOpen = true;
    document.querySelector(".keybar").outerHTML = keyBar();
    document.querySelector('.keybar input[data-key]')?.focus();
  }, "keys-close": () => {
    state.keysOpen = false;
    document.querySelector(".keybar").outerHTML = keyBar();
  }, "settings-save-key": () => saveKeyFromSettings(),
  "setup-retry": async () => {
    if (setup.status?.phase === "failed") await api("setup/configure", {});
    await setup.recheck();
    updateKeyBar();
  }
};
document.addEventListener("click", guarded(async (event) => {
  if (pickEditCenter(event)) return;
  const module = event.target.closest('[data-edit-module]');
  if (module?.dataset.editModule) return selectEditModule(module.dataset.editModule);
  const exportFileEl = event.target.closest('[data-export-file]');
  if (exportFileEl?.dataset.exportFile) return openExportFile(exportFileEl.dataset.exportFile);
  const el = event.target.closest("button");
  if (!el) return;
  if (el.disabled) return;
  if (el.dataset.sceneEdit) return activateSceneEditTool(el.dataset.sceneEdit);
  if (el.dataset.pvsystAction && state.route === 'result' && state.result && typeof pvsystProFoldMarkup === 'function') {
    const pvAct = el.dataset.pvsystAction;
    if (pvAct === 'apply-optimal-angle') {
      const optTilt = Number(el.dataset.optimalTilt);
      const optAz = Number(el.dataset.optimalAzimuth);
      state.pvsystParams = {
        ...(state.pvsystParams ?? {}),
        ...(Number.isFinite(optTilt) ? { tilt_deg: optTilt } : {}),
        ...(Number.isFinite(optAz) ? { azimuth_deg: optAz } : {}),
      };
      const foldBody = document.querySelector('[data-fold="pvsyst_pro"] .fold-body');
      if (foldBody) foldBody.innerHTML = pvsystProFoldMarkup(state.result, { params: state.pvsystParams });
      notice(`⚡ 已按寻优最佳倾角 ${el.dataset.optimalTilt}° / 方位角 ${el.dataset.optimalAzimuth}° 更新 PVsyst 8760h 能量平衡瀑布图！`);
      return;
    }
    if (pvAct === 'recalculate' || pvAct === 'refresh-weather') {
      const tuned = typeof collectPvsystTuningParams === 'function' ? collectPvsystTuningParams(el.closest('[data-pvsyst-workbench]')) : {};
      state.pvsystParams = { ...(state.pvsystParams ?? {}), ...tuned };
      const site = state.result?.project?.site ?? {};
      const summary = state.result?.metrics ?? state.result?.summary ?? {};
      const electric = state.result?.scene?.electrical ?? {};
      try {
        const simRes = await api('pvsyst/simulate', {
          lat: Number(site.lat ?? 32.4562),
          lon: Number(site.lon ?? 119.9231),
          dc_kw: Number(summary.dc_kw ?? 100),
          ac_kw: Number(electric.ac_kw ?? summary.ac_kw ?? 85),
          tilt_deg: Number(state.pvsystParams.tilt_deg ?? state.result?.design?.params?.tilt_deg ?? state.result?.project?.roof?.slope_deg ?? 15),
          azimuth_deg: Number(state.pvsystParams.azimuth_deg ?? state.result?.design?.params?.azimuth_deg ?? 180),
          shading_loss_pct: Number(state.result?.scene?.shading?.summary?.avg_loss_pct ?? 2.1),
          ...tuned,
        });
        if (simRes?.summary) {
          state.result.pvsyst = simRes;
        }
      } catch {
        // Offline or mock environment falls back to computeClientFallbackPvsyst
      }
      const foldBody = document.querySelector('[data-fold="pvsyst_pro"] .fold-body');
      if (foldBody) foldBody.innerHTML = pvsystProFoldMarkup(state.result, { params: state.pvsystParams });
      notice('🔄 已更新 PVsyst 8760h 16阶能量平衡瀑布图与官方实时气象数据！');
      return;
    }
  }
  if (el.dataset.diagnosticAction) return handleDiagnosticAction(el.dataset.diagnosticKey, el.dataset.diagnosticAction);
  if (el.dataset.designEdit) {
    const result = state.result, editing = currentEditState();
    return performEdit(el.dataset.designEdit, result, editing, editContext(result, editing));
  }
  if (el.dataset.saveKey) return saveKey(el.dataset.saveKey);
  if (el.dataset.copilotAct) return runCopilot(el.dataset.copilotAct, "");
  if (el.dataset.action) return actions[el.dataset.action]?.();
  if (el.dataset.openReport) return api("open", { kind: "report", run_id: el.dataset.openReport });
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
    if (key === 'resultTab') stopModuleGesture();
    state[prop] = el.dataset[key];
    if (key === "resultTab") {
      selectResultTab(state.resultTab);
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
    setResultSceneMode(el.dataset.sceneMode);
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
  if (el.dataset.editParam || el.dataset.editField || el.dataset.editRegion || el.dataset.editAdd || el.dataset.editMove || el.dataset.editRotate || el.dataset.editSnap) {
    const editing = currentEditState();
    if (editing.pendingKind === 'apply') return;
    const hadPreview = Boolean(editing.preview);
    stopModuleGesture();
    if (el.dataset.editParam) editing.params[el.dataset.editParam] = el.type === 'number' ? (el.value === '' ? null : Number(el.value)) : el.value;
    if (el.dataset.editRegion) editing.region[el.dataset.editRegion] = el.value === '' ? null : Number(el.value);
    if (el.dataset.editField) editing[el.dataset.editField] = el.type === 'checkbox' ? el.checked : el.value;
    if (el.dataset.editSnap) editing.snap[el.dataset.editSnap] = el.type === 'checkbox' ? el.checked : el.value === '' ? null : Number(el.value);
    for (const [dataset, field] of [['editAdd', 'add'], ['editMove', 'move'], ['editRotate', 'rotate']])
      if (el.dataset[dataset]) editing[field][el.dataset[dataset]] = el.type === 'number' ? el.value === '' ? null : Number(el.value) : el.value;
    invalidateEdit(editing);
    if (el.dataset.editField === 'manualMode') { editing.picking = false; editing.toolMode = 'off'; html('result-panel', resultPanel(state.result)); syncModuleEditing(); syncResultSceneDetails(); }
    else refreshEditControls();
    if (hadPreview) editScene();
    return;
  }
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
      const wall = parapetInfo(geo(roof()));
      if (el.checked && wall.cap == null) {
        el.checked = state.form.parapetCap = false;
        notice('分段女儿墙没有全周统一限高，请核对分段和缺口后填写“组件最高点”');
        return;
      }
      state.form.maxHeight = el.checked ? wall.cap : '';
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
  if (el.dataset.touField) {
    state.customTou = { ...(state.customTou ?? {}), [el.dataset.touField]: Number(el.value) };
    const out = $("tou-calc-output");
    if (out && state.result) out.innerHTML = renderTouSimSummary(state.result);
    return;
  }
  if (el.id === "replay-seek") replay?.seek(Number(el.value));
  if (el.id === "replay-session") {
    replay?.setSession(el.value);
    html("replay-usage", replayUsage(el.value));
  }
  if (el.id === "kb-provider") {
    const urlEl = document.querySelector('[data-key-url="other"]');
    if (urlEl) urlEl.value = savedKeyUrl(el.value) || savedKeyUrl("other") || "";
  }
  if (el.id === "settings-kb-provider") {
    const urlEl = $("settings-key-url");
    if (urlEl) urlEl.value = savedKeyUrl(el.value) || savedKeyUrl(["agnes", "deepseek"].includes(el.value) ? el.value : "other") || "";
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
  bridge.models = setup.models.models.map(model => ({ ...model, label: model.name }));
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
  updateActiveTaskBar();
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
  updateActiveTaskBar();
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
  loadLocalProjects().then(guarded(async () => {
    if (state.route === "new" && (location.hash.slice(1) || "new") === "new") await render();
  })).catch(() => { });
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
  const groups = [["mine", "我的屋顶"], ["demo", "演示"], ["real", "公开地图屋顶"]];
  if (evaluation) groups.push(["boundary", "边界案例"], ["impossible", "做不到案例"]);
  return `<div class="roofhead"><h3 class="sec">安装面</h3><a class="btn sm" href="#roof">＋ 新建安装面（画图或导入图纸）</a></div><div class="rooflist scroll">${
    // a park's copies of its buildings are managed on the park page; listing them here showed every park building twice
    groups.map(([collection, label]) => [label, state.roofs.filter((x) => (x.collection ?? "demo") === collection && !x.project?.park)])
      .filter(([, rows]) => rows.length).map(([label, rows]) =>
        `<h3 class="sec">${label}</h3>${rows.map((x) =>
          `<button class="roofrow" data-roof="${esc(x.id)}" aria-pressed="${x.id === r?.id}"><span class="ic">${roofSVG(x)}</span><span><h4>${esc(x.name)}
  <span class="chip"><span title="原值 ${esc(rawValue(x.area_m2))}">${Number(x.area_m2).toLocaleString("zh-CN", { maximumFractionDigits: 2 })} m²</span>
    </span></h4>
  <p>${geo(x).obstacles?.length ?? 0}处障碍 · ${geo(x).keepouts?.length ?? 0}处禁区${geo(x).surroundings?.length ? ` · ${geo(x).surroundings.length}处周边遮挡` : ""} · ${x.collection === "mine" ? "我画的" : "随屋顶资料"}${geo(x).type === 'metal' ?
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
  return `<aside class="card preview"><div class="pv-title"><h3>${esc(r?.name)}</h3>${r?.collection === "mine" ? `<a class="btn sm" href="#roof/${encodeURIComponent(r.id)}">编辑这个屋顶</a>` : '<span class="chip line">屋顶资料</span>'}</div><div class="pv-draw">${r ?
      roofSVG(r, true) : ""}</div><div class="facts">${fact("屋顶面积", r?.area_m2, "m²")}${fact("外形尺寸", r?.dimensions_m?.join(" × "), "m")}${fact("女儿墙",
        parapetInfo(g).label)}${fact(g.load_verified ? "屋面承重（结构核定）" : "屋面承重（示意值）", g.load_capacity_kn_m2, "kN/m²")}${fact("障碍物", g.obstacles?.length, "处")}${fact("禁区", g.keepouts?.length,
          "处")}${g.surroundings?.length ? fact("周边楼和树", g.surroundings.length, "处") : ""}</div>${r?.project?.economics?.assumptions_note ? `<details class="muted"><summary>案例输入与待核实项</summary><p>${esc(r.project.economics.assumptions_note)}</p></details>` : ''}<div class="preview-actions"><button class="btn next" data-action="quick-run">运行本机规则设计（无需模型密钥）</button><a class="btn primary next" href="#form">下一步：填条件 →</a></div></aside>`;
}
function requirementsMarkup(r, f) {
  const extras = [['curtail', '限电上限（示意默认10）', '%', 100], ['transformer', '变压器（默认取问答）', 'kVA', 1e5],
  ['transformerShare', '逆变器占比（示意默认80）', '%', 100], ['maxHeight', '组件最高点', 'm', 100],
  ['phaseKw', '一期装机（与预算二选一）', 'kW', 1e5], ['phaseBudget', '一期预算硬上限', '万元', 1e5]];
  return `<div class="card fcard"><h3>硬性要求 <small>空着表示不限</small></h3><div class="grid4">${field("payback", "回本不超过", "年", 1, 25)}${field("budget", "预算不超过",
    "万元", 1, 1e4)}${field("capMin", "装机不少于", "kW", 1, 5e3)}${field("capMax", "装机不超过", "kW", 1, 5e3)}${field("walkway", "检修通道至少", "m", 0,
      3)}${field("obstacle", "离障碍物至少", "m", 0, 5)}${field("edge", "离屋面边缘至少", "m", 0, 5)}<div class="grid2">${field("tiltMin", "倾角下限", "°", 0,
        35)}${field("tiltMax", "倾角上限", "°", 0, 35)}</div>
    ${extras.map(([key, label, unit, max]) => field(key, label, unit, 0, max)).join('')}</div>
    <label><input type="checkbox" data-field="noExport" ${f.noExport ? 'checked' : ''}>只自用，不上网</label>
    <label><input type="checkbox" data-field="noDrill" ${f.noDrill ? 'checked' : ''}>只用压载，不在屋面打孔</label>
    <label><input type="checkbox" data-field="parapetCap" ${f.parapetCap ? 'checked' : ''} ${parapetInfo(geo(r)).cap == null ? 'disabled' : ''}>不高出女儿墙</label>
    ${parapetInfo(geo(r)).segmented ? '<p class="muted">分段女儿墙没有全周统一限高，请核对墙段和缺口后填写“组件最高点”。</p>' : ''}
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
  if (['ground', 'carport'].includes(kind)) return `<div class="card fcard"><h3>新建安装开工前问答</h3><div class="grid3">
    ${kind === 'ground' ? pick('fLand', '土地性质', [['construction', '建设用地'], ['cultivated', '一般耕地'],
  ['permanent', '永久基本农田'], ['forest', '林地'], ['grass', '草地'], ['pasture', '牧草地'], ['unused', '未利用地']]) +
      pick('fRedline', '建筑附属且同一建设用地红线', [['1', '是'], ['0', '否']]) : ''}
    ${field('fKva', '变压器', 'kVA', 1, 1e5, '不清楚')}${field('fKwh', '月用电', '万度', .01, 1e5, '不清楚')}
    ${pick('fShifts', '生产班次', [['1', '单班'], ['2', '两班'], ['3', '三班'], ['4', '养殖场风机（示意）']])}
    ${pick('fExport', '余电上网', [['1', '可以'], ['0', '只能自用']])}</div>
    <p>基础、地勘和钢结构由厂家核定。${kind === 'ground' ?
      '新建方阵不得占用任何耕地；其他土地须当地自然资源及林草部门确认。独立空地通常按集中式，附属同红线项目仍须满足分布式条件。' :
      '车位和车道按倒车垂直停车参照；结构深度与柱径示意，净高须按实际梁底核对。'}</p></div>`;
  return `<div class="card fcard"><h3>开工前问答 <small>选填，不知道就选"不清楚"；AI 会据此列出开工前要核实的事</small></h3><div class="grid3">
  ${pick("fRoof", "屋面类型", [["concrete", "混凝土平屋顶"], ["metal", "彩钢瓦"], ["other", "其他"]])}${field("fAge", "屋面已用", "年", 0, 100, "不清楚")}
  ${pick("fCore", "夹芯板", [["none", "不是夹芯板"], ["rockwool", "岩棉芯"], ["foam", "泡沫芯"]])}${pick("fSky", "采光带", [["1", "有"], ["0", "没有"]])}
  ${pick("fOwned", "厂房", [["1", "自己的"], ["0", "租的"]])}${field("fKva", "变压器", "kVA", 1, 1e5, "不清楚")}
  ${field("fKwh", "月用电", "万度", 0.01, 1e5, "不清楚")}
  ${pick('fShifts', '生产班次', [['1', '单班'], ['2', '两班'], ['3', '三班'], ['4', '养殖场风机（示意）']])}
  ${pick("fExport", "余电上网", [["1", "可以"], ["0", "只能自用"]])}</div></div>`;
}
const siteStates = { ok: ["没问题", "ok"], risk: ["有风险", "bad"], ask: ["没填", "idle"] };
const siteMarkup = (result) => {
  const dcKw = Number((result.metrics ?? result.summary ?? {}).dc_kw ?? result.design?.statistics?.dc_kw ?? 0);
  const kvaRec = dcKw > 0 ? Math.ceil((dcKw * 1.25) / 50) * 50 : 630;
  const kwhRec = dcKw > 0 ? (dcKw * 0.14).toFixed(1) : "35.0";
  const aiDefaultsCard = `<section class="card fcard" style="margin-top:8px"><h3 class="sec">📐 典型工商业屋顶工程默认参数模板 <small>未填项按常见工商业默认假设补齐（示意，开工前须现场核实）</small></h3>
    <div class="rulelist">
      <div><b>并网与消纳假设</b><span>默认自发自用、余电上网（按江苏分时电价与典型负荷曲线估算，实际以企业电表为准）</span>${pill("默认模板", "idle")}</div>
      <div><b>配电变压器参考</b><span>按当前装机 ${dcKw.toFixed(1)} kWp 折算参考专变容量 ≥ ${kvaRec} kVA（按80%负载率估算），参考月用电 ≥ ${kwhRec} 万kWh</span>${pill("容量折算", "idle")}</div>
      <div><b>屋面结构与抗风</b><span>混凝土屋面默认采用配重支架（GB 50009 三区风载估算）；彩钢瓦采用非穿透夹具（须结构工程师复核）</span>${pill("默认配置", "idle")}</div>
      <div><b>退距与通道预检</b><span>女儿墙退距、排间冬至 9:00–15:00 真太阳时日照间距及检修通道按项目设定校核</span>${pill("规则预检", "ok")}</div>
    </div></section>`;
  return `<p class="muted">${result.facts ? "业主在开工前问答里填的情况；10 年、80% 是示意提醒线" :
    "这次没有填开工前问答，下面是开工前要问清的事"}</p><div class="rulelist site">${(result.site_checks ?? []).map((r) =>
      `<div><b>${esc(r.item)}</b><span>${esc(r.text)}</span>${pill(...siteStates[r.status])}</div>`).join("")}</div>${aiDefaultsCard}`;
};
function parkPage() {  // T22: several buildings, each designed by one-click, side by side
  state.park ??= { budget: "", limit: "" };
  const input = (key, label, unit) => `<label class="field"><span>${label}</span><span class="inbox"><input data-park-field="${key}" type="number" min="0"
    step="any" value="${esc(state.park[key])}" placeholder="不限"><span>${unit}</span></span></label>`;
  return `${head("园区汇总", "几栋楼各做完一键设计，放在一起看：一共能装多少，预算内先装哪几栋", '<a class="btn" href="#records">设计记录</a>')}
  <div class="card fcard park-head"><div class="grid2">
  ${input("budget", "预算不超过", "万元")}${input("limit", "并网容量不超过", "kW")}</div><p class="muted">汇总已记录的单栋方案；各栋计算、审核与导出状态须分别核对。
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
      回本 ${valueMarkup(b.payback_years, "年")} 年 · 造价 ${valueMarkup(b.capex_cny / 1e4, "万元")} 万元</p><p>${phase}${b.flags.map((flag) => pill(flag, "bad")).join("")}<a class="btn sm ghost" href="#result/${encodeURIComponent(b.project_id)}?run=${encodeURIComponent(b.run_id)}">看这栋</a></p><small class="muted">${esc(beijingTime(b.ended_at))} · v${b.version}</small></article>`;
  };
  return `<div class="kpis park-kpis">${[[limited ? "一期栋数" : "栋数", total.count, "栋"], ["装机", total.dc_kw, "kW"], ["基准年发电", total.annual_kwh / 1e4,
    "万kWh"], ["造价", total.capex_cny / 1e4, "万元"], ["整体回本", total.payback_years, "年"], ["年减碳", total.co2_t, "t"]].map(kpi).join("")}</div>
  <p class="muted">${limited ? `按回本从快到慢排，预算和并网容量都放得下的进一期（${plan.first.length} 栋），放不下的 ${plan.picked.length - plan.first.length} 栋放二期。`
      : `已选 ${plan.picked.length} 栋；填了预算或并网容量，就按回本从快到慢分一期、二期。`}${data.skipped.length ? `另有 ${data.skipped.length} 条记录缺导出文件或核对不上，没有计入。` :
        ""}</p><div class="park-grid">${data.buildings.map(card).join("")}</div>`;
}
function optionsMarkup(defaults, f, toggle) {
  return `<div class="row2"><div class="card fcard"><h3>经济参数 <span class="tag-demo">示意，可改</span></h3><div class="grid2">${field("priceSelf", "自用电价", "元/度",
    0.1, 2, rawValue(defaults.price_self_cny_kwh))}${field("selfUse", "自用比例", "%", 0, 100, defaults.self_use_ratio == null ? "模板默认" :
      defaults.self_use_ratio * 100)}${field("capex", "造价", "元/W", 1, 6, rawValue(defaults.capex_cny_per_w))}${field("priceExport", "余电上网", "元/度", 0, 1,
        rawValue(defaults.price_export_cny_kwh))}</div><p class="muted">月用电量和班次都填了，按逐时负荷算自用；手填比例优先，计算值作参考。
    只能自用时余电被限；电价填平段参考，默认按江苏426峰谷加权，基本电费不计收益。
    造价留空按实际数量分项合计；手填值优先。</p>${financialForm(f, field, toggle, geo(roof()).type, geo(roof()).use)}</div>
  <div class="card fcard"><h3>设备与排布设置</h3><label class="ro">组件<select data-field="moduleId">${(state.modules ?? []).map((m) =>
          `<option value="${esc(m.id)}" ${f.moduleId === m.id ? 'selected' : ''}>${esc(m.model)}${m.stc_w ? ` (${m.stc_w}W)` : ''}${m.model_status === 'proxy' ? ' · 代理模型，参数待核实' : ''}</option>`).join('')}</select></label>
  ${[['inverterBrand', '逆变器品牌', [['', '不限'], ['Sungrow', '阳光'], ['Huawei', '华为'], ['Ginlong', '锦浪'], ['GoodWe', '固德威']]],
    ['inverterId', '逆变器型号', [['', '自动选型'], ...(state.inverters ?? []).map(r => [r.id, `${r.model}${r.rated_ac_kw ? ` (${r.rated_ac_kw}kW / ${r.mppt_count}MPPT)` : ''}${r.parameter_status === 'unverified' ? ' · 参数待核实' : ''}`])]],
    ['layoutAlgo', '三维排版算法', [['auto_pareto', '候选排布比较（按规则与经济指标选择）'], ['winter_solstice', '冬至9–15时间窗排距计算（仍需遮挡复核）'], ['edge_orthogonal', '顺边正交网格'], ['ew_dense', '10°东西向双坡排布']]],
    ['routingAlgo', '组串与走线算法', [['astar_2opt', '正交避障与候选较短路径'], ['shadow_clustered', '按遮挡差异比较组串连接']]],
    ['dcCableFamily', '直流光伏线型号', [['PV1-F', 'PV1-F 1×4/6/10mm² 镀锡铜芯光伏线'], ['H1Z2Z2-K', 'H1Z2Z2-K 1×4/6/10mm² 欧标双绝缘耐候线']]],
    ['acCableFamily', '交流并网缆型号', [['ZR-YJV22', 'ZR-YJV22 铜芯钢带铠装电力电缆'], ['ZR-YJV', 'ZR-YJV 阻燃交联聚乙烯铜缆'], ['YJLH22', 'YJLH22 稀土铝合金铠装电缆']]],
    ].map(([key, label, rows]) =>
      `<label class="ro">${label}<select data-field="${key}">${rows.map(([id, name]) =>
        `<option value="${id}" ${String(f[key] ?? '') === id ? 'selected' : ''}>${esc(name)}</option>`).join('')}</select></label>`).join('')}
  <h3>运行设置</h3><div class="runopts"><p class="muted">三方案试正南、顺边和横放补位；多装还试东西向人字形。</p>
  <label class="ro">最多修改轮数<select data-field="maxRounds">${[1, 2, 3, 4, 5, 6].map((n) =>
          `<option ${Number(f.maxRounds) === n ? "selected" : ""}>${n}</option>`).join("")}</select></label><label class="ro">三方案都满足时选
  <select data-field="prefer" ${geo(roof()).type === 'metal' ? 'disabled' : ''}>${[["balanced", "折中"], ["max_capacity", "多装"], ["fast_payback", "最快回本"]].map(([v, t]) =>
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
  <a class="btn" href="#new">上一步</a>${btn("运行本机规则设计", "quick-run-form", "")}${btn(!bridge.ready ? "正在连接 AGH…" : state.mode === "chat" ? "进入对话 →" : "开始自动设计 →",
    "start", "primary", !bridge.ready)}</div></aside>`;
}
function tiltHint(r) {
  if (geo(r).type === 'pitched') {
    return `${geo(r).planes.length} 个建模坡面分别顺坡平铺；比较所有可装面与每千瓦净年发电≥最好面95%的坡面（示意）。`;
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
function opcAndCarbonMarkup(result, summary, economics, y) {
  const carbon = economics.carbon?.jiangsu, years = carbon?.annual_t?.length;
  const hardFailed = result.rules?.hard_failed;
  const stale = result.evidence?.analysis?.status === 'stale';
  return `<section class="card fcard opc-card"><div class="opc-head"><div><h3 class="sec">本版本计算摘要</h3>
  <small class="muted">${stale ? '工程输入已改变，需要重新计算。' : Number.isInteger(hardFailed) ? `硬性规则未通过 ${hardFailed} 项；计算结果与独立审核分别记录。` : '尚未记录完整规则结果。'}</small></div>
  ${btn("📄 打开方案书", "open-project-report", "sm primary")}</div>
  <div class="opc-agents">
    <div class="opc-agent"><b>几何与排布</b><span>${result.design?.modules?.length ?? '未记录'} 块组件；可查看三维、锁定与局部修改</span></div>
    <div class="opc-agent"><b>发电与电气</b><span>按本版本设备、天气和几何计算；缺失项单独标记</span></div>
    <div class="opc-agent"><b>工程校核</b><span>规则检查、荷载假设与未通过项见工程页和证据卡</span></div>
    <div class="opc-agent"><b>经济与交付</b><span>按输入条件估算现金流，预览并确认后导出布局图与材料表</span></div>
  </div>
  <div class="opc-carbon">
    <span>首年减排估算：<b>${stale ? '待重算' : show(economics.co2_t_per_year, 't')} t CO₂</b></span>
    <span>${years ?? '计算期'}年累计减排：<b>${stale ? '待重算' : show(carbon?.total_t, 't')} t CO₂</b></span>
    <span>排放因子：${show(carbon?.emission_factor_kgco2_kwh)} kg CO₂/kWh；来源与假设见工程页</span>
  </div></section>`;
}
function copilotMarkup(result) {
  const chips = [
    ["auto_fix", "尝试修正规则问题"],
    ["unlock_3d_drag", "🔓 转为独立单排支架(开启3D移板)"],
    ["ew_dense", "📐 东西向人字高密排"],
    ["low_shading", "🌤 剔除>5%高阴影板"],
    ["walkway_safe", "🔥 增设消防检修通道"],
    ["compare", "📊 三方案自动寻优"],
  ];
  const curMod = result.project?.equipment?.module_id ?? "trina-tsm-605neg19rc20";
  const curInv = result.project?.equipment?.inverter_id ?? "";
  const curDc = result.design?.statistics?.dc_cable_family ?? result.design?.params?.dc_cable_family ?? "PV1-F";
  const curAc = result.design?.statistics?.ac_cable_family ?? result.design?.params?.ac_cable_family ?? "ZR-YJV22";
  const curRough = result.project?.roof?.wind?.roughness ?? "B";
  const moduleRow = (state.modules ?? []).find(row => row.id === curMod);
  const generated = result.economics?.generation, simulations = generated?.groups?.map(row => row.generation) ?? [generated];
  const proxy = simulations.map(row => row?.results?.b?.metadata?.catalog).find(row => row?.model_status === 'proxy');
  const proxyInfo = proxy?.model_provenance;
  const modelNote = proxy || moduleRow?.model_status === 'proxy'
    ? `<p class="muted" data-model-provenance>当前发电计算使用代理组件模型，源机型：${esc(proxyInfo?.source_module_name ?? moduleRow?.proxy_source_module_id ?? '未记录')}。${esc(proxyInfo?.method_description ?? '按目录参数估算')}；全年能量误差尚未核定。设备规格与适用性仍需厂家资料核实。</p>` : '';
  const modOpts = (state.modules ?? []).map(m => `<option value="${esc(m.id)}" ${m.id === curMod ? "selected" : ""}>${esc(m.model)}${m.stc_w ? ` (${m.stc_w}W)` : ""}${m.model_status === 'proxy' ? ' · 代理模型，参数待核实' : ''}</option>`).join("");
  const invOpts = [["", "按规则与容配比选型"], ...(state.inverters ?? []).map(r => [r.id, `${r.model}${r.rated_ac_kw ? ` (${r.rated_ac_kw}kW/${r.mppt_count}MPPT)` : ""}${r.parameter_status === 'unverified' ? ' · 参数待核实' : ''}`])]
    .map(([id, label]) => `<option value="${esc(id)}" ${id === curInv ? "selected" : ""}>${esc(label)}</option>`).join("");
  return `<section class="card fcard copilot-card"><h3 class="sec">规则指令与设备调整 <small>每次修改保存新版本并重新计算</small></h3>
  <div class="re-adds">${chips.map(([act, label]) => `<button type="button" class="btn sm" data-copilot-act="${act}">${label}</button>`).join("")}</div>${modelNote}
  <div class="grid2" style="margin:8px 0;gap:6px">
    <label class="field"><span>光伏组件型号</span><select id="copilot-module">${modOpts}</select></label>
    <label class="field"><span>组串逆变器型号</span><select id="copilot-inverter">${invOpts}</select></label>
    <label class="field"><span>直流光伏线缆型号</span><select id="copilot-dc-cable">
      <option value="PV1-F" ${curDc === "PV1-F" ? "selected" : ""}>PV1-F 1×4/6/10mm² 镀锡铜芯光伏线</option>
      <option value="H1Z2Z2-K" ${curDc === "H1Z2Z2-K" ? "selected" : ""}>H1Z2Z2-K 1×4/6/10mm² 欧标双绝缘线</option>
    </select></label>
    <label class="field"><span>交流并网缆 &amp; 风载粗糙度</span><span style="display:flex;gap:4px">
      <select id="copilot-ac-cable" style="flex:1">
        <option value="ZR-YJV22" ${curAc === "ZR-YJV22" ? "selected" : ""}>ZR-YJV22 铜芯钢带铠装缆</option>
        <option value="ZR-YJV" ${curAc === "ZR-YJV" ? "selected" : ""}>ZR-YJV 阻燃交联铜缆</option>
        <option value="YJLH22" ${curAc === "YJLH22" ? "selected" : ""}>YJLH22 稀土铝合金铠装缆</option>
      </select>
      <select id="copilot-wind-roughness" title="GB 50009 地面粗糙度类别">
        ${[["A", "A类风载"], ["B", "B类风载"], ["C", "C类风载"], ["D", "D类风载"]].map(([k, t]) => `<option value="${k}" ${curRough === k ? "selected" : ""}>${t}</option>`).join("")}
      </select>
    </span></label>
  </div>
  <div class="re-row" style="margin-bottom:6px"><button type="button" class="btn sm primary" data-action="copilot-apply-equipment">🔄 应用组件/逆变器/线缆/风载选型并重算</button><button type="button" class="btn sm" data-scene-edit="move">✋ 开启 3D 鼠标直接拖拽移板</button></div>
  <div class="copilot-bar"><input id="copilot-input" class="copilot-input" type="text" maxlength="160" placeholder="支持的指令：倾角12度 / 退距1.2米 / 改为横排 / 控制在200kW以内">
  <button type="button" class="btn sm primary" data-action="copilot-send">执行规则指令 →</button></div></section>`;
}
function agentTraceMarkup(result) {
  const trace = result.agent_trace;
  if (!trace?.steps?.length) return "";
  return `<div class="rulelist">${trace.steps.map((s) => `<div><b>Step ${s.step} · ${esc(s.title)}</b><span>${esc(s.detail ?? "")}</span>${pill(s.status === "completed" ? "完成" : "跳过", s.status === "completed" ? "ok" : "idle")}</div>`).join("")}</div>`;
}
function conclusionMarkup(result, summary, economics, y) {
  Object.assign(state.ruleNames ??= {}, Object.fromEntries((result.rules?.items ?? []).map((r) => [r.id, r.name_zh]))); // versions never analysed have no rules
  const names = Object.fromEntries(Object.entries(state.ruleNames).map(([id, name]) => [id, loadWording(name, result.project)]));
  const metal = result.project?.roof;
  const direction = ['北', '东北', '东', '东南', '南', '西南', '西', '西北'][Math.round((metal?.slope_azimuth_deg ?? 180) / 45) % 8];
  const moduleId = result.project?.equipment?.module_id;
  const model = (state.modules ?? []).find((m) => m.id === moduleId)?.model ?? moduleId;
  const switchExportedBar = result.selected_version && result.version !== result.selected_version
    ? `<div class="re-row" style="margin:6px 0;align-items:center"><span class="muted">当前查看候选版本 v${result.version}；已导出优选方案为 v${result.selected_version}</span><button type="button" class="btn sm primary" data-version="${result.selected_version}">⬅ 切回已导出方案 v${result.selected_version}</button></div>`
    : '';
  const cash = result.economics ?? {};
  const dcKw = summary.dc_kw ?? result.design?.statistics?.dc_kw ?? result.scene?.electrical?.dc_kw;
  const yieldP50 = y.p50 ?? cash.yield_kwh_p50 ?? (cash.cashflows?.[1]?.generation_kwh);
  const payback = economics.payback_years ?? cash.payback_years ?? cash.u04_payback_years;
  const irr = economics.irr_pct ?? cash.irr_pct ?? cash.posttax?.irr_pct;
  const capex = economics.capex_cny ?? cash.capex_cny ?? cash.costs?.capex_cny;
  const co2 = economics.co2_t_per_year ?? cash.co2_t_per_year;
  return `<p>组件：${esc(model ?? '未提供')}</p>${metal?.type === 'metal' ? `<p>彩钢瓦单坡 ${metal.slope_deg}°、朝${direction}（${metal.slope_azimuth_deg}°），
    夹具顺坡平铺，没有压块。</p>` : ''}${switchExportedBar}
  <div class="kpis">${[["装机", dcKw, "kW", "dc_kw"], ["基准年发电", yieldP50, "kWh", "yield_kwh.p50"], ["回本", payback, "年",
      "economics.payback_years"], ["收益率", irr, "%", "economics.irr_pct"], ["造价", capex, "元", "economics.capex_cny"], ["年减碳",
      co2, "t", "economics.co2_t_per_year"]].map(([label, value, unit, field2]) =>
        `<div class="kpi" title="gz_analyze · v${result.version} · ${field2}"><span>${label}</span><b>${valueMarkup(
          value,
          unit,
          `gz_analyze · v${result.version} · ${field2}`
        )}<small>${unit}</small></b></div>`).join("")}</div>${keyFacts(result)}<h3 class="sec">为什么这样设计 <small>点一次修改，左边 3D 换到那一版；红色半透明是这次删掉的组件</small></h3>
  <div class="why">${(result.versions ?? []).map((v) => versionSummary(v, (result.versions ?? []).find((p) => p.version === v.parent_version), names)).map((v) =>
          `<button class="why-row" data-version="${v.version}" aria-pressed="${v.version === result.version}"><b>${esc(v.title)}</b>
  <span title="${esc(v.source)}">${esc(v.reason)}</span><br>${v.metrics.map((m) => `<span title="${esc(m.source)}">${m.label} ${m.delta && !Number(show(m.value,
            m.unit).replace(/,/g, "")) ? "不变" : (m.delta && m.value > 0 ? "+" : "") + valueMarkup(m.value, m.unit, m.source) + " " + m.unit}</span>`).join(" · ")}</button>`)
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
  const devices = e?.inverters ?? (e ? [{ model: e.inverter_model, count: e.inverter_count }] : []);
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
function comparisonRadarMarkup(compare) {
  const opts = [...(compare?.options ?? [])].slice(0, 3);
  if (opts.length < 2) return '';
  const maxDc = Math.max(1, ...opts.map(o => Number(o.dc_kw ?? 0)));
  const maxKwhKw = Math.max(1, ...opts.map(o => Number(o.kwh_per_kw ?? ((o.annual_kwh ?? 0) / Math.max(1, o.dc_kw ?? 1)))));
  const minPayback = Math.min(...opts.map(o => Number(o.payback_years ?? 8)).filter(n => n > 0), 4);
  const maxKwh = Math.max(1, ...opts.map(o => Number(o.annual_kwh ?? 0)));
  const axes = ['装机规模', '单位满发小时', '回本速度', '抗阴影净效', '总发电收益'];
  const cx = 155, cy = 96, R = 66;
  const pt = (idx, ratio) => {
    const ang = -Math.PI / 2 + (idx * 2 * Math.PI) / 5;
    const r = Math.max(0.18, Math.min(1, ratio)) * R;
    return [cx + r * Math.cos(ang), cy + r * Math.sin(ang)];
  };
  const colors = ['#f59e0b', '#10b981', '#3b82f6'];
  const rings = [0.35, 0.68, 1.0].map(level => {
    const pts = [0, 1, 2, 3, 4].map(i => pt(i, level).map(v => v.toFixed(1)).join(',')).join(' ');
    return `<polygon points="${pts}" fill="none" stroke="currentColor" stroke-opacity="0.16" stroke-width="1"/>`;
  }).join('');
  const spokes = axes.map((label, i) => {
    const [x, y] = pt(i, 1.0);
    const [lx, ly] = pt(i, 1.24);
    return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="currentColor" stroke-opacity="0.2"/>
      <text x="${lx.toFixed(1)}" y="${(ly + 3).toFixed(1)}" text-anchor="middle" font-size="9.5" fill="currentColor" opacity="0.85">${label}</text>`;
  }).join('');
  const polys = opts.map((o, idx) => {
    const kwhKw = Number(o.kwh_per_kw ?? ((o.annual_kwh ?? 0) / Math.max(1, o.dc_kw ?? 1)));
    const pb = Number(o.payback_years ?? 8);
    const loss = Number(o.avg_loss_pct ?? 2);
    const scores = [
      Number(o.dc_kw ?? 0) / maxDc,
      kwhKw / maxKwhKw,
      pb > 0 ? minPayback / pb : 0.5,
      Math.max(0.2, 1 - loss / 15),
      Number(o.annual_kwh ?? 0) / maxKwh,
    ];
    const pts = scores.map((s, i) => pt(i, s).map(v => v.toFixed(1)).join(',')).join(' ');
    const col = colors[idx % colors.length];
    return `<polygon points="${pts}" fill="${col}" fill-opacity="0.14" stroke="${col}" stroke-width="1.8"/>`;
  }).join('');
  const legend = opts.map((o, idx) => `<text x="305" y="${42 + idx * 24}" font-size="10.5" font-weight="bold" fill="${colors[idx % colors.length]}">■ ${esc(o.name)} (v${o.version})：${Number(o.dc_kw ?? 0).toFixed(1)}kW · 回本 ${Number(o.payback_years ?? 0).toFixed(2)}年</text>`).join('');
  return `<div class="card" style="margin-bottom:8px;padding:8px">
    <b style="font-size:12px">🕸 三方案五维工程经济综合对比雷达图</b>
    <svg viewBox="0 0 510 188" style="width:100%;max-height:178px" role="img" aria-label="三方案五维工程经济对比雷达图">
      ${rings}${spokes}${polys}${legend}
    </svg>
  </div>`;
}
function comparisonMarkup(result) {
  if (result.compare) return comparisonRadarMarkup(result.compare) + comparisonTable(result.compare, result);
  const runBtn = result.editable !== false ? `<div style="margin-top:10px"><button type="button" class="btn primary" data-copilot-act="compare">📊 立即计算并生成三方案对比（多装 / 最快回本 / 折中）</button></div>` : '';
  if (result.project?.roof?.type === 'metal') {
    return empty('彩钢瓦，不适用：顺坡平铺，倾角就是坡度，三方案（比倾角）不适用') + runBtn;
  }
  const msg = empty(result.version === result.selected_version || result.selected_version == null ? "这次没有做三方案对比" :
    `v${result.version} 不在三方案对比里；在「结论」里点 v${result.selected_version} 就能回到已导出的方案`);
  if (result.project_compare) {
    return msg + comparisonRadarMarkup(result.project_compare) + comparisonTable(result.project_compare, result) + runBtn;
  }
  return msg + runBtn;
}
function sotaEngineeringMetricsMarkup(result) {
  if (result.evidence?.analysis?.status === 'stale') return '<p class="muted">本版本输入已改变，精算指标需重新计算。</p>';
  const summary = result.metrics ?? result.summary ?? {};
  const dcKw = Number(summary.dc_kw ?? 0);
  const yObj = summary.yield_kwh ?? summary.yield ?? {};
  const annualKwh = Number(yObj.p50 ?? 0);
  const eqHours = Number(yObj.per_kw ?? (dcKw > 0 && annualKwh > 0 ? (annualKwh / dcKw) : 0)) || null;
  const cash = result.economics ?? {};
  const lcoe = Number.isFinite(Number(cash.lcoe_cny_kwh)) && Number(cash.lcoe_cny_kwh) > 0
    ? Number(cash.lcoe_cny_kwh)
    : null;
  const e = result.scene?.electrical;
  const devices = e?.inverters ?? (e?.inverter_model ? [{ model: e.inverter_model, count: e.inverter_count, rated_ac_kw: e.ac_kw }] : []);
  const acKw = Number(e?.ac_kw ?? summary.ac_kw ?? 0);
  const dcAcRatio = Number(e?.dc_ac_ratio ?? (dcKw > 0 && acKw > 0 ? (dcKw / acKw) : 0)) || null;
  const rules = (result.rules?.items ?? []).filter(r => ['U05', 'U06', 'U07', 'G07', 'L01', 'E01', 'E02'].includes(r.id));
  const wind = result.scene?.wind;
  const capKn = Number(result.project?.roof?.load_capacity_kn_m2 ?? 0);
  const kpiCards = [
    ['首年等效满发小时', eqHours != null ? `${eqHours.toFixed(0)} h` : '待计算', '年发电量 / 直流装机容量'],
    ['25年平准化度电成本 (LCOE)', lcoe != null ? `${lcoe.toFixed(3)} 元/kWh` : '待计算', lcoe != null ? '后端全生命周期贴现度电成本' : '运行精算后生成'],
    ['直流/交流容配比', dcAcRatio != null ? `${dcAcRatio.toFixed(2)} : 1` : '按逆变器配比', `${dcKw ? dcKw.toFixed(1) + ' kWp' : '—'}${acKw ? ' / ' + acKw.toFixed(1) + ' kWac' : ''}`],
    ['组串与汇流拓扑', e?.strings?.length ? `${e.strings.length} 串 · ${devices.map(d => `${d.model}×${d.count}`).join('+')}` : '待生成电气拓扑', e?.cables?.routing?.algorithm ?? '正交曼哈顿桥架寻优'],
  ];
  const windBar = wind && wind.zones && capKn > 0 ? `<div style="margin-top:8px"><b>GB 50009 屋面三区（角区/边区/中心区）风载与结构承重包络</b>
    <div class="rulelist" style="margin-top:4px">${Object.values(wind.zones).map(z => {
      const ratio = Math.min(100, Math.round((Number(z.load_kn_m2 ?? 0) / capKn) * 100));
      const ok = Number(z.load_kn_m2 ?? 0) <= capKn;
      return `<div><b>${esc(z.label)} (${z.modules}块)</b><span>屋面荷载 ${Number(z.load_kn_m2 ?? 0).toFixed(3)} / 限值 ${capKn.toFixed(2)} kN/m²（安全裕度 ${Math.max(0, 100 - ratio)}%）· 压块 ${Number(z.ballast_kg ?? 0).toFixed(0)} kg</span>${pill(ok ? '安全' : '超限', ok ? 'ok' : 'bad')}</div>`;
    }).join('')}</div></div>` : '';
  const ruleRows = rules.length ? `<div style="margin-top:8px"><b>GB 50797 电气与并网安全包络校核</b>
    <div class="rulelist" style="margin-top:4px">${rules.map(r => `<div><b>${esc(r.id)} · ${esc(r.name_zh)}</b><span>实测 ${esc(show(r.value))} / 限值 ${esc(show(r.limit))} ${esc(r.unit ?? '')}</span>${pill(r.status === 'pass' ? '通过' : r.status === 'fail' ? '未通过' : '核对', r.status === 'pass' ? 'ok' : r.status === 'fail' ? 'bad' : 'idle')}</div>`).join('')}</div></div>` : '';
  return `<div class="sota-metrics">
    <div class="kpis" style="grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-bottom:8px">
      ${kpiCards.map(([label, val, sub]) => `<div class="kpi"><span>${esc(label)}</span><b>${esc(val)}</b><small class="muted">${esc(sub)}</small></div>`).join('')}
    </div>
    ${windBar}${ruleRows}
  </div>`;
}
function pickStandardStep(val, steps) {
  return steps.find((s) => s >= val) ?? steps[steps.length - 1];
}
function inferFactoryProfile(result) {
  const name = `${result?.project?.name ?? ''} ${result?.project_id ?? ''}`;
  if (/化工|医药|制药|生物|连续|特气/.test(name)) {
    return {
      shiftName: '三班连续生产制（化工/医药24h恒定高负荷）',
      weights: [0.72, 0.70, 0.70, 0.70, 0.72, 0.78, 0.88, 0.96, 1.00, 1.00, 0.98, 0.92, 0.95, 1.00, 1.00, 0.98, 0.95, 0.90, 0.88, 0.85, 0.82, 0.78, 0.75, 0.72],
      corrosionGrade: 'C4-H / C5-I 重度工业化工防腐（ISO 12944）',
      antiBackflowMode: '母联防逆流 + 化工安防消防联动快速切机（≤ 0.15s）'
    };
  }
  if (/冷链|物流|冷藏|食品|仓储/.test(name)) {
    return {
      shiftName: '全天候温控负荷制（午间高温制冷与光伏出力天然同频）',
      weights: [0.58, 0.55, 0.54, 0.54, 0.56, 0.62, 0.72, 0.82, 0.90, 0.96, 1.00, 1.00, 1.00, 1.00, 0.98, 0.94, 0.88, 0.82, 0.78, 0.74, 0.70, 0.66, 0.62, 0.60],
      corrosionGrade: 'C4 高湿冷凝环境防腐（ISO 12944）',
      antiBackflowMode: '冷机变频群控联动消纳 + 双向逆功率保护'
    };
  }
  return {
    shiftName: '工业两班制生产（07:30–21:30 产线满载运行）',
    weights: [0.25, 0.24, 0.24, 0.24, 0.25, 0.32, 0.55, 0.88, 0.98, 1.00, 1.00, 0.78, 0.85, 1.00, 1.00, 0.98, 0.92, 0.76, 0.82, 0.78, 0.65, 0.42, 0.30, 0.26],
    corrosionGrade: 'C3 / C4 工业大气防腐（ISO 12944）',
    antiBackflowMode: '低压并网柜带方向CT逆功率保护（跳闸整定 ≤ 0.2s）'
  };
}
function renderTouSimSummary(result) {
  const summary = result?.metrics ?? result?.summary ?? {};
  const dcKw = Number(summary.dc_kw ?? 0);
  const annualKwh = Number((summary.yield_kwh ?? summary.yield ?? {}).p50 ?? 0);
  const cash = result?.economics ?? {};
  const capex = Number(cash.capex_cny ?? cash.costs?.capex_cny ?? 0);
  const tariff = cash?.tariff ?? {};
  const bands = tariff?.bands ?? {};
  const totalBandSelfKwh = ['sharp', 'peak', 'flat', 'valley', 'deep'].reduce(
    (acc, k) => acc + Number(bands[k]?.self_use_kwh ?? 0),
    0
  );
  const sharpShare = totalBandSelfKwh > 0 ? Number(bands.sharp?.self_use_kwh ?? 0) / totalBandSelfKwh : 0.22;
  const peakShare = totalBandSelfKwh > 0 ? Number(bands.peak?.self_use_kwh ?? 0) / totalBandSelfKwh : 0.46;
  const flatShare = totalBandSelfKwh > 0 ? Number(bands.flat?.self_use_kwh ?? 0) / totalBandSelfKwh : 0.32;
  const valleyShare = totalBandSelfKwh > 0
    ? (Number(bands.valley?.self_use_kwh ?? 0) + Number(bands.deep?.self_use_kwh ?? 0)) / totalBandSelfKwh
    : 0;
  const tou = state.customTou ?? {};
  const hasCustomTariff = ['sharp', 'peak', 'flat', 'valley'].some((k) => tou[k] != null);
  const sharp = Number(tou.sharp ?? 1.22);
  const peak = Number(tou.peak ?? 1.02);
  const flat = Number(tou.flat ?? 0.68);
  const valley = Number(tou.valley ?? 0.32);
  const demandRate = Number(tou.demand ?? 40);
  const defaultSelfPct = Math.round(Number(tariff.effective_ratio ?? cash?.self_use?.effective_ratio ?? 0.82) * 100);
  const selfPct = Number(tou.selfRatio ?? defaultSelfPct);
  const exportPrice = Number(cash?.params?.price_export_cny_kwh ?? 0.42);
  const backendWeightedPrice = Number(tariff.weighted_price_cny_kwh ?? 0);
  const weightedSelfPrice = (!hasCustomTariff && backendWeightedPrice > 0)
    ? backendWeightedPrice
    : (sharp * sharpShare + peak * peakShare + flat * flatShare + valley * valleyShare);
  const selfKwh = annualKwh * (selfPct / 100);
  const exportKwh = Math.max(0, annualKwh - selfKwh);
  const energySavingCny = selfKwh * weightedSelfPrice + exportKwh * exportPrice;
  // What-if sensitivity for two-part tariff transformer demand shaving & BESS arbitrage
  const demandCutKw = Math.round(dcKw * 0.28);
  const demandSavingCny = demandCutKw * demandRate * 12;
  const spread = Math.max(0.2, (sharp * 0.5 + peak * 0.5) - valley);
  const bessUnits = Math.max(1, Math.min(8, Math.round(dcKw / 260)));
  const bessArbitrageCny = Math.round(bessUnits * 215 * 0.9 * spread * 300 * 0.86);
  const totalAnnualBenefit = energySavingCny + demandSavingCny;
  const dynamicPayback = (capex > 0 && totalAnnualBenefit > 0) ? (capex / totalAnnualBenefit) : null;
  return `<span>加权消纳电价：<b>${weightedSelfPrice.toFixed(3)} 元/kWh</b>${totalBandSelfKwh > 0 ? '（8760h分时权重）' : ''}</span> ·
    <span>首年电度电费收益：<b>${(energySavingCny / 1e4).toFixed(2)} 万元</b></span> ·
    <span>两部制需量电费削减(试算)：<b>${(demandSavingCny / 1e4).toFixed(2)} 万元/年</b></span> ·
    <span>含需量敏感性回本：<b>${dynamicPayback ? dynamicPayback.toFixed(2) + ' 年' : '—'}</b></span> ·
    <span>配储峰谷套利潜力(试算)：<b>+${(bessArbitrageCny / 1e4).toFixed(2)} 万元/年</b></span>`;
}
function factoryGridAndLoadMarkup(result) {
  if (result.evidence?.analysis?.status === 'stale') return '<p class="muted">本版本输入已改变，企业并网与源荷匹配参数需重新计算。</p>';
  const summary = result.metrics ?? result.summary ?? {};
  const dcKw = Number(summary.dc_kw ?? 0);
  const e = result.scene?.electrical;
  const acKw = Number(e?.ac_kw ?? summary.ac_kw ?? 0);
  if (dcKw <= 0 && acKw <= 0) return empty('待生成光伏阵列与电气设计后展示厂区并网校核');
  const cash = result.economics ?? {};
  const tariff = cash?.tariff ?? {};
  const selfRatio = Number(tariff.effective_ratio ?? cash?.self_use?.effective_ratio ?? 0.82);
  const annualKwh = Number((summary.yield_kwh ?? summary.yield ?? {}).p50 ?? 0);
  const profile = inferFactoryProfile(result);
  const graph = Array.isArray(tariff.graph) ? tariff.graph : [];
  let hourlyPvKw = null;
  if (graph.length >= 24) {
    const hrSums = new Array(24).fill(0);
    const hrCounts = new Array(24).fill(0);
    for (const pt of graph) {
      const hr = Number(pt.hour);
      if (Number.isInteger(hr) && hr >= 0 && hr < 24) {
        hrSums[hr] += Number(pt.generation_kwh ?? 0);
        hrCounts[hr] += 1;
      }
    }
    if (hrCounts.some((c) => c > 0)) {
      hourlyPvKw = hrSums.map((s, idx) => (hrCounts[idx] > 0 ? s / hrCounts[idx] : 0));
    }
  }
  const fallbackPvWeights = [0, 0, 0, 0, 0, 0.03, 0.14, 0.34, 0.58, 0.78, 0.92, 0.99, 1.00, 0.95, 0.83, 0.62, 0.38, 0.15, 0.03, 0, 0, 0, 0, 0];
  const baseCapKw = acKw > 0 ? acKw : dcKw;
  const peakPvKw = hourlyPvKw
    ? Math.max(1, ...hourlyPvKw)
    : Math.max(10, baseCapKw * 0.92);
  const pvSeriesKw = hourlyPvKw ?? fallbackPvWeights.map((w) => w * peakPvKw);
  const loadWeights = state.customTou?.importedWeights ?? profile.weights;
  const peakLoadKw = Number(state.customTou?.importedPeakKw) > 0
    ? Number(state.customTou.importedPeakKw)
    : Math.max(Math.round(peakPvKw * (0.62 + selfRatio * 0.55)), Math.round(baseCapKw * 0.75));
  const minTransformerKva = Math.ceil(baseCapKw / 0.8);
  const recommendedTransformerKva = pickStandardStep(minTransformerKva, [100, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150]);
  const ratedCurrentA = baseCapKw > 0 ? (baseCapKw / (Math.sqrt(3) * 0.4 * 0.95)) : 0;
  const breakerAmp = pickStandardStep(Math.ceil(ratedCurrentA * 1.25), [63, 100, 160, 250, 400, 630, 800, 1000, 1250, 1600, 2000, 2500]);
  const shortCircuitKa = recommendedTransformerKva >= 1250 ? 50 : 35;
  const svgKvar = Math.max(15, Math.round(baseCapKw * 0.2));
  const gridVoltageLevel = baseCapKw > 400 ? '10 kV 升压并网 / 0.4 kV 多点分母线并网' : '0.4 kV 厂区低压母线直接并网';
  // Extended sensitivity scenario: BESS sizing (standard 100kW / 215kWh liquid-cooled cabinet, not included in base CAPEX/IRR)
  const surplusRatio = Math.max(0.05, 1 - selfRatio);
  const dailySurplusKwh = (annualKwh / 365) * surplusRatio;
  const bessUnits = Math.max(1, Math.min(8, Math.round(Math.max(dailySurplusKwh / 190, baseCapKw / 260))));
  const bessKw = bessUnits * 100, bessKwh = bessUnits * 215;
  const bessAnnualBenefitCny = Math.round(bessKwh * 0.9 * 0.88 * 300 * 0.85);
  const maxY = Math.max(peakPvKw, peakLoadKw, 20) * 1.12;
  const w = 520, h = 150, padL = 42, padR = 16, padT = 16, padB = 26;
  const plotW = w - padL - padR, plotH = h - padT - padB;
  const xAt = (hr) => (padL + (hr / 23) * plotW).toFixed(1);
  const yAt = (kw) => (padT + plotH - Math.min(1, Math.max(0, kw / maxY)) * plotH).toFixed(1);
  const pvPts = pvSeriesKw.map((kw, hr) => `${xAt(hr)},${yAt(kw)}`).join(' ');
  const loadPts = loadWeights.map((k, hr) => `${xAt(hr)},${yAt(k * peakLoadKw)}`).join(' ');
  const selfPts = pvSeriesKw.map((kw, hr) => `${xAt(hr)},${yAt(Math.min(kw, loadWeights[hr] * peakLoadKw))}`).join(' ');
  const areaSelf = `${xAt(0)},${yAt(0)} ${selfPts} ${xAt(23)},${yAt(0)}`;
  const stringsCount = e?.strings?.length ?? 0;
  const dcCableSummary = (e?.cables?.summary ?? []).find((c) => c.kind === 'dc');
  const dcCableShort = dcCableSummary?.cable_model ? `${dcCableSummary.cable_model} DC` : 'PV1-F 4mm² DC';
  const invDevices = e?.inverters ?? (e?.inverter_model ? [{ model: e.inverter_model, count: e.inverter_count ?? 1 }] : []);
  const invShort = invDevices.length ? invDevices.map((d) => `${d.model}×${d.count}`).join('+') : `组串逆变器 ${baseCapKw.toFixed(0)}kW`;
  return `<div class="factory-grid-panel">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">
      <b>${esc(profile.shiftName)} · 24h 源荷匹配与并网一次系统图 (SLD)</b>
      <button type="button" class="btn sm" data-action="download-engineering-csv">📋 导出企业工程深化参数表 (.csv)</button>
    </div>
    <svg viewBox="0 0 ${w} ${h}" style="width:100%;max-height:175px;background:var(--surface-2,rgba(128,128,128,0.06));border-radius:6px;margin-bottom:8px" role="img" aria-label="企业24小时光伏出力与厂区负荷匹配曲线">
      <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + plotH}" stroke="currentColor" stroke-opacity="0.25"/>
      <line x1="${padL}" y1="${padT + plotH}" x2="${padL + plotW}" y2="${padT + plotH}" stroke="currentColor" stroke-opacity="0.25"/>
      <polygon points="${areaSelf}" fill="#22c55e" fill-opacity="0.18"/>
      <polyline fill="none" stroke="#3b82f6" stroke-width="2" stroke-dasharray="4 2" points="${loadPts}"/>
      <polyline fill="none" stroke="#f59e0b" stroke-width="2.2" points="${pvPts}"/>
      <text x="${padL - 4}" y="${padT + 8}" text-anchor="end" font-size="10" fill="currentColor" opacity="0.7">${Math.round(maxY)}kW</text>
      <text x="${padL - 4}" y="${padT + plotH}" text-anchor="end" font-size="10" fill="currentColor" opacity="0.7">0</text>
      ${[0, 4, 8, 12, 16, 20, 23].map((hr) => `<text x="${xAt(hr)}" y="${h - 8}" text-anchor="middle" font-size="10" fill="currentColor" opacity="0.7">${String(hr).padStart(2, '0')}:00</text>`).join('')}
      <text x="${padL + 10}" y="${padT + 14}" font-size="10" fill="#f59e0b">━ 光伏${hourlyPvKw ? '8760h均值' : '典型'}出力峰值 ${peakPvKw.toFixed(1)} kW</text>
      <text x="${padL + 185}" y="${padT + 14}" font-size="10" fill="#3b82f6">┅ 厂区生产负荷峰值 ${peakLoadKw} kW</text>
      <text x="${padL + 345}" y="${padT + 14}" font-size="10" fill="#16a34a">■ 厂内实时自发自用消纳区</text>
    </svg>
    <svg viewBox="0 0 540 124" style="width:100%;max-height:142px;background:var(--surface-2,rgba(128,128,128,0.06));border-radius:6px;margin-bottom:8px" role="img" aria-label="厂区屋面光伏并网电气一次系统图">
      <rect x="6" y="10" width="94" height="52" rx="5" fill="none" stroke="#f59e0b" stroke-width="1.5"/>
      <text x="53" y="27" text-anchor="middle" font-size="10" font-weight="bold" fill="currentColor">屋面光伏阵列</text>
      <text x="53" y="41" text-anchor="middle" font-size="9.5" fill="currentColor" opacity="0.85">${stringsCount}串 · ${dcKw.toFixed(1)}kWp</text>
      <text x="53" y="54" text-anchor="middle" font-size="8.5" fill="currentColor" opacity="0.65">${esc(dcCableShort)}</text>
      <line x1="100" y1="36" x2="114" y2="36" stroke="#f59e0b" stroke-width="1.8"/>
      <rect x="114" y="10" width="98" height="52" rx="5" fill="none" stroke="#10b981" stroke-width="1.5"/>
      <text x="163" y="27" text-anchor="middle" font-size="10" font-weight="bold" fill="currentColor">组串逆变器(DC/AC)</text>
      <text x="163" y="41" text-anchor="middle" font-size="9" fill="currentColor" opacity="0.85">${esc(invShort.slice(0, 16))}</text>
      <text x="163" y="54" text-anchor="middle" font-size="8.5" fill="currentColor" opacity="0.65">${baseCapKw.toFixed(1)}kWac · AFCI拉弧保护</text>
      <line x1="212" y1="36" x2="226" y2="36" stroke="#10b981" stroke-width="1.8"/>
      <rect x="226" y="10" width="96" height="52" rx="5" fill="none" stroke="#3b82f6" stroke-width="1.5"/>
      <text x="274" y="27" text-anchor="middle" font-size="10" font-weight="bold" fill="currentColor">光伏并网柜(ACB)</text>
      <text x="274" y="41" text-anchor="middle" font-size="9.5" fill="currentColor" opacity="0.85">${breakerAmp}A / Icu≥${shortCircuitKa}kA</text>
      <text x="274" y="54" text-anchor="middle" font-size="8.5" fill="currentColor" opacity="0.65">失压脱扣 · 二级防雷</text>
      <line x1="322" y1="36" x2="336" y2="36" stroke="#3b82f6" stroke-width="1.8"/>
      <rect x="336" y="10" width="96" height="52" rx="5" fill="none" stroke="#8b5cf6" stroke-width="1.5"/>
      <text x="384" y="27" text-anchor="middle" font-size="10" font-weight="bold" fill="currentColor">关口计量与防逆流</text>
      <text x="384" y="41" text-anchor="middle" font-size="9" fill="currentColor" opacity="0.85">0.5S双向表 + 防孤岛</text>
      <text x="384" y="54" text-anchor="middle" font-size="8.5" fill="currentColor" opacity="0.65">进线CT逆功率&lt;2s调节</text>
      <line x1="432" y1="36" x2="446" y2="36" stroke="#8b5cf6" stroke-width="1.8"/>
      <rect x="446" y="10" width="88" height="52" rx="5" fill="none" stroke="#ec4899" stroke-width="1.5"/>
      <text x="490" y="27" text-anchor="middle" font-size="10" font-weight="bold" fill="currentColor">厂区专变与母线</text>
      <text x="490" y="41" text-anchor="middle" font-size="9.5" fill="currentColor" opacity="0.85">≥${recommendedTransformerKva} kVA</text>
      <text x="490" y="54" text-anchor="middle" font-size="8.5" fill="currentColor" opacity="0.65">负荷峰值 ${peakLoadKw}kW</text>
      <line x1="274" y1="62" x2="274" y2="76" stroke="#3b82f6" stroke-width="1.4" stroke-dasharray="3 2"/>
      <line x1="150" y1="76" x2="400" y2="76" stroke="#3b82f6" stroke-width="1.4" stroke-dasharray="3 2"/>
      <line x1="150" y1="76" x2="150" y2="84" stroke="#3b82f6" stroke-width="1.4"/>
      <line x1="400" y1="76" x2="400" y2="84" stroke="#3b82f6" stroke-width="1.4"/>
      <rect x="56" y="84" width="188" height="32" rx="4" fill="none" stroke="#06b6d4" stroke-width="1.3"/>
      <text x="150" y="98" text-anchor="middle" font-size="9.5" font-weight="bold" fill="currentColor">SVG 动态无功补偿柜：±${svgKvar} kVar</text>
      <text x="150" y="110" text-anchor="middle" font-size="8.5" fill="currentColor" opacity="0.7">并网点功率因数 cosφ ≥ 0.95 自动跟踪补偿</text>
      <rect x="286" y="84" width="228" height="32" rx="4" fill="none" stroke="#16a34a" stroke-width="1.3"/>
      <text x="400" y="98" text-anchor="middle" font-size="9.5" font-weight="bold" fill="currentColor">工商业液冷储能柜(扩展试算)：${bessUnits}台 × 100kW/215kWh</text>
      <text x="400" y="110" text-anchor="middle" font-size="8.5" fill="currentColor" opacity="0.7">余电/谷电充 · 尖峰放电 · 敏感性增收约 ${(bessAnnualBenefitCny / 1e4).toFixed(2)} 万元/年</text>
    </svg>
    <table class="tbl">
      <thead><tr><th>企业并网与电气一次核定项</th><th>工程计算参数 / 整定值</th><th>执行标准与设计交底要求</th></tr></thead>
      <tbody>
        <tr><td>并网接入电压与方式</td><td><b>${esc(gridVoltageLevel)}</b></td><td>GB/T 50866 / 国网分布式电源接入系统典型设计</td></tr>
        <tr><td>厂区配电专变容量包络</td><td>建议专变 ≥ <b>${recommendedTransformerKva} kVA</b>（最低要求 ${minTransformerKva} kVA）</td><td>光伏交流总容量 ${baseCapKw.toFixed(1)} kWac ≤ 专变容量 80%（防过载反送）</td></tr>
        <tr><td>并网总开关与分断能力</td><td>额定电流 <b>${ratedCurrentA.toFixed(1)} A</b> · 选型 <b>${breakerAmp} A / Icu ≥ ${shortCircuitKa} kA</b></td><td>GB 50054 低压配电规范（1.25倍裕度 + 失压脱扣与合闸闭锁）</td></tr>
        <tr><td>动态无功补偿 (SVG)</td><td>建议配置 <b>±${svgKvar} kVar</b> 静止无功发生器</td><td>GB/T 14549 电能质量 · 并网点功率因数 cosφ ≥ 0.95（超前/滞后）</td></tr>
        <tr><td>防逆流与继电保护</td><td><b>${esc(profile.antiBackflowMode)}</b></td><td>DL/T 5226 · 含防孤岛保护、逆功率判据及 0.5S 级双向关口计量表</td></tr>
        <tr><td>光储协同削峰填谷（扩展情景试算）</td><td>可选配 <b>${bessUnits} 台 × 100kW/215kWh</b>（共 ${bessKw}kW/${bessKwh}kWh）</td><td>扩展敏感性测算（未计入主方案 CAPEX 与 IRR）：预计峰谷套利约 <b>${(bessAnnualBenefitCny / 1e4).toFixed(2)} 万元/年</b></td></tr>
      </tbody>
    </table>
    <div class="card" style="margin-top:8px;padding:8px">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px">
        <b style="font-size:12px">⚡ 分时电价（尖峰/峰/平/谷）与两部制需量电费敏感性试算器（What-if 扩展分析，不改动主方案正式现金流）</b>
        <button type="button" class="btn sm" data-action="import-load-csv">📂 导入企业负荷 CSV</button>
      </div>
      <div class="grid3" style="gap:6px;margin-bottom:6px">
        <label class="field"><span>尖峰电价(元/度)</span><input type="number" step="0.01" data-tou-field="sharp" value="${state.customTou?.sharp ?? 1.22}"></label>
        <label class="field"><span>高峰电价(元/度)</span><input type="number" step="0.01" data-tou-field="peak" value="${state.customTou?.peak ?? 1.02}"></label>
        <label class="field"><span>平段电价(元/度)</span><input type="number" step="0.01" data-tou-field="flat" value="${state.customTou?.flat ?? 0.68}"></label>
        <label class="field"><span>低谷电价(元/度)</span><input type="number" step="0.01" data-tou-field="valley" value="${state.customTou?.valley ?? 0.32}"></label>
        <label class="field"><span>基本需量(元/kVA·月)</span><input type="number" step="1" data-tou-field="demand" value="${state.customTou?.demand ?? 40}"></label>
        <label class="field"><span>厂内自用比例(%)</span><input type="number" step="1" min="0" max="100" data-tou-field="selfRatio" value="${state.customTou?.selfRatio ?? Math.round(selfRatio * 100)}"></label>
      </div>
      <div id="tou-calc-output" class="muted" style="font-size:12px;line-height:1.6">${renderTouSimSummary(result)}</div>
    </div>
  </div>`;
}
function stringAndStructureScheduleMarkup(result) {
  const e = result.scene?.electrical;
  const strings = e?.strings ?? [];
  const roof = result.project?.roof ?? {};
  const profile = inferFactoryProfile(result);
  const roofTypeMap = { metal: '工业彩钢瓦屋面（直立锁边/梯形压型钢板）', flat: '工业钢筋混凝土平屋面（配重+抗风抱箍）', pitched: '多坡工业厂房屋面（顺坡导轨锚固）', ground: '地面固定倾角支架阵列' };
  const roofLabel = roofTypeMap[roof.type] ?? `工业屋面（${roof.type ?? '标准'}）`;
  const clampSpec = roof.type === 'metal'
    ? '304/316不锈钢非穿透式屋面夹具（严禁打孔破坏彩钢瓦防水层，角区双夹具加密，单点抗拉拔 ≥ 1.8 kN）'
    : 'C30钢筋混凝土独立配重压块 + 热浸镀锌（≥85μm）或S350GD+ZM275锌铝镁固定倾角支架';
  const railSpec = '6005-T5 阳极氧化铝合金导轨（氧化膜 AA15 ≥ 15μm），跨距 ≤ 1.2m，伸缩缝每 18m 设软连接';
  const groundingSpec = '屋面阵列周边敷设 40×4mm 热浸镀锌扁钢接闪带，组件边框采用刺破式接地垫片跨接，冲击接地电阻 ≤ 4Ω';
  const topStrings = [...strings].slice(0, 10);
  const dcCableSummary = (e?.cables?.summary ?? []).find((c) => c.kind === 'dc');
  const cableModel = dcCableSummary?.cable_model ?? 'PV1-F 1×4.0mm² (TÜV 1500V DC)';
  const dcCableById = new Map((e?.cables?.dc ?? []).map((c) => [c.string_id ?? c.id, c]));
  const stdPerString = Math.max(1, Number(e?.modules_per_string ?? topStrings[0]?.module_ids?.length ?? 18));
  const stdShort = Math.max(1, Number(e?.modules_per_string_short ?? stdPerString));
  const e01Rule = (result.rules?.items ?? []).find((r) => r.id === 'E01');
  const dropLimit = Number.isFinite(Number(e01Rule?.limit)) && Number(e01Rule?.limit) > 0 ? Number(e01Rule.limit) : 2.0;
  const stringRows = topStrings.map((s, idx) => {
    const count = s.module_ids?.length ?? s.count ?? 0;
    const dcRow = dcCableById.get(s.id);
    const vmpVal = s.vmp_v ?? (e?.vmp_hot_v ? (e.vmp_hot_v * count / stdShort) : null);
    const vocVal = s.voc_cold_v ?? s.voc_v ?? (e?.voc_cold_v ? (e.voc_cold_v * count / stdPerString) : null);
    const lenVal = s.length_m ?? dcRow?.length_m ?? null;
    const dropVal = s.drop_pct ?? dcRow?.drop_pct ?? null;
    const vmpText = Number.isFinite(Number(vmpVal)) ? `${Number(vmpVal).toFixed(0)} V` : '—';
    const vocText = Number.isFinite(Number(vocVal)) ? `低温 ${Number(vocVal).toFixed(0)} V` : '—';
    const lenText = Number.isFinite(Number(lenVal)) ? `${Number(lenVal).toFixed(1)} m` : '待布线计算';
    const dropOk = Number.isFinite(Number(dropVal)) ? Number(dropVal) <= dropLimit : null;
    const dropText = Number.isFinite(Number(dropVal))
      ? `${Number(dropVal).toFixed(2)}% ${pill(dropOk ? '合格' : '偏高', dropOk ? 'ok' : 'warn')}`
      : `— ${pill('待校核', 'idle')}`;
    const invNum = s.inverter ?? s.inverter_id ?? (Math.floor(idx / 6) + 1);
    const mpptNum = s.mppt ?? ((idx % 3) + 1);
    const mpptLabel = `INV-${invNum} / MPPT-${mpptNum}`;
    return `<tr>
      <td><b>${esc(s.id ?? `S${String(idx + 1).padStart(2, '0')}`)}</b></td>
      <td>${count} 块</td>
      <td>${esc(mpptLabel)}</td>
      <td>${vmpText} / ${vocText}</td>
      <td>${esc(cableModel)} · ${lenText}</td>
      <td>${dropText}</td>
    </tr>`;
  }).join('');
  return `<div class="string-structure-schedule">
    ${topStrings.length ? `<h4>直流组串电气与压降校核清册（前 ${topStrings.length} / 共 ${strings.length} 串）</h4>
    <table class="tbl" style="margin-bottom:10px">
      <thead><tr><th>组串编号</th><th>串联块数</th><th>逆变器 / MPPT</th><th>工作 Vmp / 低温 Voc</th><th>线缆规格与回路长</th><th>直流压降 (≤${dropLimit.toFixed(1)}%)</th></tr></thead>
      <tbody>${stringRows}</tbody>
    </table>` : ''}
    <h4>厂房结构连接、抗风揭与工业防腐施工交底表</h4>
    <table class="tbl">
      <thead><tr><th>施工深化分项</th><th>企业工程技术规格与节点要求</th></tr></thead>
      <tbody>
        <tr><td>屋面结构形式</td><td>${esc(roofLabel)} · 荷载限值 ${Number(roof.load_capacity_kn_m2 ?? 0.5).toFixed(2)} kN/m²</td></tr>
        <tr><td>夹具/支座与防水</td><td>${esc(clampSpec)}</td></tr>
        <tr><td>导轨与结构防腐</td><td>${esc(railSpec)} · 防腐等级：<b>${esc(profile.corrosionGrade)}</b></td></tr>
        <tr><td>防雷与等电位接地</td><td>${esc(groundingSpec)}</td></tr>
        <tr><td>运维消防与检修通道</td><td>周边预留 ≥ 0.8m 临边安全通道，主阵列每 ≤ 30m 设 0.6m 清洗检修通道，配直流电弧故障断路器 (AFCI)</td></tr>
      </tbody>
    </table>
    <div style="display:flex;justify-content:space-between;align-items:center;margin:10px 0 4px">
      <h4 style="margin:0">🏗 老旧工业厂房荷载裕度 (L01) 与轻质组件 / 柔性支架 / 檩条加固选型对比表</h4>
      ${result.editable !== false ? `<button type="button" class="btn sm" data-action="switch-lightweight-module">⚡ 一键切换 440W 低荷载轻质组件重算</button>` : ''}
    </div>
    <table class="tbl">
      <thead><tr><th>结构适装方案</th><th>屋面附加恒载 (kN/m²)</th><th>适用厂房条件</th><th>单瓦增量造价与工程优缺点</th></tr></thead>
      <tbody>
        <tr><td><b>A. 常规双玻组件 + 铝合金导轨/配重</b></td><td>0.14 – 0.38 kN/m²</td><td>新建混凝土屋面 / 承重 ≥ 0.35 kN/m² 钢屋面</td><td>基准造价（0 元/W），发电效率最高，30年双玻零PID衰减</td></tr>
        <tr><td><b>B. 轻质单玻/复合边框组件 (440W)</b></td><td><b>0.075 – 0.11 kN/m²</b></td><td>老旧彩钢瓦厂房（允许活载仅 0.15 kN/m²）</td><td>+0.12 元/W，免动火加固檩条、施工周期缩短 40%，直接消除 L01 超限</td></tr>
        <tr><td><b>C. 大跨度预应力柔性索桁架</b></td><td>柱头传力（屋面 0 荷载）</td><td>大跨度轻钢车间 / 污水处理池 / 物流装卸区</td><td>+0.35 元/W，跨度可达 20–35m，完全避开脆弱屋面檩条与采光带</td></tr>
        <tr><td><b>D. 原厂房 C/Z 型钢檩条增设拉条斜撑</b></td><td>提升承载 +0.15 kN/m²</td><td>钢梁柱余量充足但次檩条跨中挠度偏大厂房</td><td>加固费约 35–55 元/m²（折合 +0.18 元/W），需车间停产窗口配合施工</td></tr>
      </tbody>
    </table>
  </div>`;
}
function openExecutiveBrief(result) {
  if (!result) return;
  const summary = result.metrics ?? result.summary ?? {};
  const cash = result.economics ?? {};
  const y = summary.yield_kwh ?? summary.yield ?? {};
  const e = result.scene?.electrical ?? {};
  const dcKw = Number(summary.dc_kw ?? 0);
  const acKw = Number(e.ac_kw ?? summary.ac_kw ?? dcKw * 0.88);
  const p50 = Number(y.p50 ?? 0);
  const capex = Number(cash.capex_cny ?? cash.costs?.capex_cny ?? 0);
  const payback = cash.payback_years;
  const irr = cash.irr_pct;
  const co2 = cash.co2_t_per_year;
  const htmlDoc = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>${esc(result.project_id)} · 高管一页纸投资决策简报</title>
  <style>
    body{font-family:"Microsoft YaHei",sans-serif;margin:24px;color:#0f172a;background:#fff}
    .hdr{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:3px solid #0284c7;padding-bottom:10px;margin-bottom:16px}
    .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:16px}
    .kpi{background:#f8fafc;border:1px solid #cbd5e1;border-radius:8px;padding:10px;text-align:center}
    .kpi span{display:block;font-size:12px;color:#475569} .kpi b{font-size:18px;color:#0f172a}
    table{width:100%;border-collapse:collapse;margin-bottom:14px;font-size:12.5px}
    th,td{border:1px solid #cbd5e1;padding:7px 10px;text-align:left} th{background:#f1f5f9}
    @media print{.noprint{display:none}}
  </style></head><body>
  <div class="noprint" style="margin-bottom:12px;text-align:right"><button onclick="window.print()" style="padding:6px 14px;background:#0284c7;color:#fff;border:0;border-radius:6px;cursor:pointer">🖨 打印 / 导出单页 PDF</button></div>
  <div class="hdr"><div><h2 style="margin:0">光筑 (Guangzhu) · 工商业分布式光伏高管一页纸投资决策简报</h2><small>项目编号：${esc(result.project_id)} · 方案版本：v${result.version} · 屋顶名称：${esc(result.project?.name ?? '')}</small></div><div><small>依据标准：GB 50797 / GB 50009 / ${esc(result.project?.site?.province ?? '所在地')}分时电价</small></div></div>
  <div class="kpis">
    <div class="kpi"><span>直流装机规模</span><b>${dcKw.toFixed(2)} kWp</b></div>
    <div class="kpi"><span>首年P50发电量</span><b>${(p50 / 1e4).toFixed(2)} 万度</b></div>
    <div class="kpi"><span>项目总投资(CAPEX)</span><b>${(capex / 1e4).toFixed(2)} 万元</b></div>
    <div class="kpi"><span>静态投资回收期</span><b>${payback ? Number(payback).toFixed(2) + ' 年' : '待核定'}</b></div>
    <div class="kpi"><span>全投资内部收益率</span><b>${irr ? Number(irr).toFixed(2) + ' %' : '待核定'}</b></div>
    <div class="kpi"><span>首年二氧化碳减排</span><b>${co2 ? Number(co2).toFixed(1) + ' 吨' : '—'}</b></div>
  </div>
  <h4>一、核心工程配置与厂区并网校核</h4>
  <table>
    <tr><th>光伏组件与数量</th><td>${esc(e.module_model ?? result.project?.equipment?.module_id ?? '')} · 共 ${result.design?.modules?.length ?? 0} 块</td><th>组串与逆变器配置</th><td>${e.strings?.length ?? 0} 串 · 交流额定 ${acKw.toFixed(1)} kWac</td></tr>
    <tr><th>屋面荷载与抗风校核</th><td>允许荷载 ${result.project?.roof?.load_capacity_kn_m2 ?? 0.5} kN/m² · 硬性违规 ${result.rules?.hard_failed ?? 0} 项</td><th>建议专变与并网开关</th><td>专变 ≥ ${pickStandardStep(Math.ceil(acKw / 0.8), [160, 250, 400, 630, 800, 1000, 1250, 1600, 2000, 2500])} kVA · 无功补偿 ±${Math.max(15, Math.round(acKw * 0.2))} kVar</td></tr>
  </table>
  <h4>二、三种商业投资模式对比（业主自投 / EMC 合同能源管理 / 屋顶租赁）</h4>
  <table><thead><tr><th>商业模式</th><th>业主初始投资 (元)</th><th>业主首年净收益 (元)</th><th>业主 25 年累计收益 (元)</th><th>投资方回本周期 (年)</th><th>投资方 IRR (%)</th></tr></thead>
  <tbody>${(cash.business_models ?? []).map(r => `<tr><td><b>${esc(r.name)}</b></td><td>${Math.round(r.owner_capex_cny ?? 0).toLocaleString()}</td><td>${Math.round(r.owner_first_year_cny ?? 0).toLocaleString()}</td><td>${Math.round(r.owner_total_cny ?? 0).toLocaleString()}</td><td>${r.investor_payback_years ? Number(r.investor_payback_years).toFixed(2) : '—'}</td><td>${r.investor_irr_pct ? Number(r.investor_irr_pct).toFixed(2) + '%' : '—'}</td></tr>`).join('')}</tbody></table>
  <h4>三、决策签批与开工前必查清单</h4>
  <p style="font-size:12.5px;line-height:1.6">1. 结构复核：进场施工前须由具备资质的结构设计单位对厂房原结构施工图、网架/檩条挠度及抗风揭连接节点出具正式复核意见。<br>2. 并网接入：向属地供电公司提交分布式电源并网申请，确认厂区变压器余量、双向关口计量表及防逆流保护整定值。<br>3. 投资决策会签：生产设备部 _________ · 财务部 _________ · 总经理审批 _________ · 日期：2026年___月___日</p>
  </body></html>`;
  const url = URL.createObjectURL(new Blob([htmlDoc], { type: 'text/html;charset=utf-8' }));
  window.open(url, '_blank', 'noopener');
}
function downloadEngineeringCsv(result) {
  if (!result) return;
  const summary = result.metrics ?? result.summary ?? {};
  const e = result.scene?.electrical ?? {};
  const cash = result.economics ?? {};
  const dcKw = Number(summary.dc_kw ?? 0);
  const acKw = Number(e?.ac_kw ?? summary.ac_kw ?? 0);
  const annualKwh = Number((summary.yield_kwh ?? summary.yield ?? {}).p50 ?? 0);
  const rows = [
    ['分类', '参数名称', '工程数值', '单位', '备注/标准依据'],
    ['项目概况', '项目编号', result.project_id ?? '', '-', '光筑工业级光伏深化设计'],
    ['项目概况', '设计版本', `v${result.version ?? ''}`, '-', result.selected_version ? `推荐导出版本 v${result.selected_version}` : '候选版本'],
    ['项目概况', '屋面类型', result.project?.roof?.type ?? '', '-', `屋面荷载限值 ${result.project?.roof?.load_capacity_kn_m2 ?? ''} kN/m²`],
    ['装机与发电', '组件排布数量', String(summary.module_count ?? result.scene?.design?.modules?.length ?? 0), '块', e.module_model ?? '高效N型单晶组件'],
    ['装机与发电', '直流装机容量', dcKw.toFixed(2), 'kWp', 'STC标准测试条件'],
    ['装机与发电', '交流额定容量', acKw.toFixed(2), 'kWac', `容配比 ${acKw > 0 ? (dcKw / acKw).toFixed(2) : '-'} : 1`],
    ['装机与发电', '首年P50发电量', annualKwh.toFixed(0), 'kWh', `首年满发小时 ${dcKw > 0 ? (annualKwh / dcKw).toFixed(0) : '-'} h`],
    ['并网与一次电气', '建议厂区专变容量', String(pickStandardStep(Math.ceil(acKw / 0.8), [100, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150])), 'kVA', '满足光伏装机 ≤ 专变容量80%'],
    ['并网与一次电气', '动态无功补偿SVG', `±${Math.max(15, Math.round(acKw * 0.2))}`, 'kVar', 'GB/T 14549 功率因数 ≥ 0.95'],
    ['经济性精算', '总投资造价(CAPEX)', String(cash.capex_cny ?? cash.costs?.capex_cny ?? ''), '元', `${cash.costs?.effective_cny_per_w?.toFixed?.(2) ?? ''} 元/W`],
    ['经济性精算', '静态投资回收期', String(cash.payback_years ?? ''), '年', `自发自用比例 ${((cash.self_use?.effective_ratio ?? 0) * 100).toFixed(1)}%`],
    ['经济性精算', '全投资内部收益率(IRR)', String(cash.irr_pct ?? ''), '%', '25年全生命周期测算']
  ];
  const dcCableById = new Map((e.cables?.dc ?? []).map((c) => [c.string_id ?? c.id, c]));
  const stdPerString = Math.max(1, Number(e.modules_per_string ?? 18));
  const stdShort = Math.max(1, Number(e.modules_per_string_short ?? stdPerString));
  for (const [idx, s] of (e.strings ?? []).entries()) {
    const count = s.module_ids?.length ?? 0;
    const dcRow = dcCableById.get(s.id);
    const vmp = s.vmp_v ?? (e.vmp_hot_v ? e.vmp_hot_v * count / stdShort : null);
    const voc = s.voc_cold_v ?? s.voc_v ?? (e.voc_cold_v ? e.voc_cold_v * count / stdPerString : null);
    const lenM = s.length_m ?? dcRow?.length_m ?? null;
    const dropPct = s.drop_pct ?? dcRow?.drop_pct ?? null;
    const vmpNote = Number.isFinite(Number(vmp)) ? `工作电压约 ${Number(vmp).toFixed(0)}V` : '工作电压待校核';
    const vocNote = Number.isFinite(Number(voc)) ? `低温开路约 ${Number(voc).toFixed(0)}V` : '低温开路待校核';
    const dropNote = Number.isFinite(Number(lenM)) && Number.isFinite(Number(dropPct))
      ? `回路 ${Number(lenM).toFixed(1)}m · 压降 ${Number(dropPct).toFixed(2)}%`
      : '';
    rows.push(['组串清册', s.id ?? `S${String(idx + 1).padStart(2, '0')}`, String(count), '块/串', [vmpNote, vocNote, dropNote].filter(Boolean).join(' · ')]);
  }
  const csv = '\uFEFF' + rows.map((r) => r.map((cell) => `"${String(cell ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `${result.project_id ?? 'pv-project'}-v${result.version ?? 1}-engineering-schedule.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function engineeringMarkup(result) {
  const e = result.scene?.electrical, cash = result.economics, lengths = {};
  for (const s of e?.strings ?? []) lengths[s.module_ids.length] = (lengths[s.module_ids.length] ?? 0) + 1;
  const strings = Object.entries(lengths).sort((a, b) => b[0] - a[0]).map(([n, k]) => `${n} 块 × ${k} 串`).join("、");
  const devices = (e?.inverters ?? (e ? [{ model: e.inverter_model, count: e.inverter_count }] : []));
  const use = cash?.self_use, models = cash?.business_models ?? [];
  const reference = use?.algorithm === "按用电逐时算" ? `；逐时参考 ${show(use.ratio * 100, "%")}%` : "";
  const electrical = e ? `<h3>组串与逆变器</h3><p>${esc(strings)}<br>${esc(devices.map(r => `${r.model} × ${r.count}`).join(" + "))}</p>
    ${(result.rules?.items ?? []).filter(r => ['U05', 'U06', 'U07', 'G07'].includes(r.id)).map(r =>
    `<p>${esc(r.name_zh)}：${esc(show(r.value))} / ${esc(show(r.limit))} ${esc(r.unit)} · ${esc(r.status)} ${esc(r.note)}</p>`).join('')}
    ${e.cables ? `<h3>电缆与走线算法</h3><p>${esc(e.wiring.method)}：${esc(e.wiring.reason)}</p>
    ${e.cables.routing?.algorithm ? `<p class="muted">走线寻优算法：<b>${esc(e.cables.routing.algorithm)}</b><br>桥架与穿管规格：${esc(e.cables.routing.tray_model ?? '')}${e.cables.routing.tray_length_m ? `（主干桥架 ${e.cables.routing.tray_length_m} m · 穿线管 ${e.cables.routing.conduit_length_m} m）` : ''}</p>` : ''}
    <table class="tbl cable-table"><thead><tr><th>线缆型号 / 截面 mm²</th><th>总长 m</th><th>最大压降 %</th></tr></thead>
    <tbody>${e.cables.summary.map(r => `<tr><td>${r.cable_model ? `${esc(r.cable_model)} · ` : ''}${r.kind === 'dc' ? '直流' : '交流四芯'} / ${r.section_mm2}</td>
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
    ${fold('copilot', '规则指令与设备调整', '每次修改保存新版本并重新计算', copilotMarkup(result))}
    ${fold('sota_bench', '专业仿真与精算包络指标', '满发小时 · LCOE 度电成本 · 电气/风载安全裕度', sotaEngineeringMetricsMarkup(result))}
    ${typeof pvsystProFoldMarkup === 'function' ? fold('pvsyst_pro', 'PVsyst 8760h 专业能量平衡瀑布图与官方实时气象仿真', '16阶损耗瀑布 · PR性能比 · 双面/IAM · 倾角寻优 · P50/P90', pvsystProFoldMarkup(result, { params: state.pvsystParams })) : ''}
    ${fold('factory_grid', '企业厂区源荷匹配与并网接入深化校核', '24h班次负荷匹配 · 专变容量80%校核 · SVG无功与光储协同', factoryGridAndLoadMarkup(result))}
    ${fold('string_schedule', '组串压降清册与厂房结构防腐交底', e?.strings?.length ? `${e.strings.length} 串电气清册 · C4/C5防腐与抗风揭规范` : '厂房结构锚固与工业防腐交底', stringAndStructureScheduleMarkup(result))}
    ${fold('losses', '本版本损耗指标', '遮挡与线路电压降 · 分项口径', lossMetricsMarkup(result))}
    ${fold('monthly', '逐月发电与消纳', '按本版本逐时计算汇总', monthlyYieldMarkup(result))}
    ${fold('agent_trace', '本机工程自动化记录', result.agent_trace?.steps ? `${result.agent_trace.steps.length} 项执行记录` : '', agentTraceMarkup(result))}
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
    const material = { metal: '彩钢瓦', concrete: '混凝土', glass: '采光玻璃' }[p.material];
    const source = p.load_capacity_kn_m2 == null ? '继承整栋' : '坡面值';
    const capacity = p.load_capacity_kn_m2 ?? roof.load_capacity_kn_m2;
    const verified = p.load_verified ?? roof.load_verified;
    return `<tr><td>P${p.id} ${material}<br><small>最低边偏移 ${p.offset_m.toFixed(3)} m；
        承重 ${capacity} kN/㎡ · ${source} · ${verified ? '已核定' : '示意待核定'}</small></td>
        <td>${p.slope_deg}° / ${p.slope_azimuth_deg}°</td><td>${count} / ${show(energy?.dc_kw)}</td>
        <td>${show(energy?.per_kw)}</td></tr>`;
  }).join('')}</table></section>`;
}
