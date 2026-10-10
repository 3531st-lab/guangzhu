import {DATA} from '../extensions/main/client/data.js';
import {TOOL_NAMES} from './logic.js';
import {createEmbeddedTheme} from './theme.js';
import {decode, sameArguments} from '../../../desktop/web/tool-results.js';
import {modelChoices} from '../../../desktop/web/model-choices.js';

const KEY = 'guangzhu.bridge.pending/1';
const TYPES = new Set(['gz.hello','gz.start','gz.followup','gz.cancel','gz.open','gz.theme','gz.registerWorkspace','gz.models','gz.openSettings',
  'gz.saveKey','gz.parkPrompt']);
// 首页 key 栏：key 只经这里交给 AGH 官方配置接口保存，不回传、不记录。
// 键是页面上的服务商名，id 是 AGH 官方 API key 服务商编号（packages/ai/src/adapters/pi/api-key-providers.ts）。
const PROVIDERS = {deepseek:{id:'deepseek',label:'DeepSeek',model:'deepseek-v4-pro'},agnes:{id:'agnes-ai',label:'Agnes',model:'agnes-3.0-flash'},
  openai:{id:'openai',label:'ChatGPT（OpenAI）'},anthropic:{id:'anthropic',label:'Claude（Anthropic）'},google:{id:'google',label:'Gemini（Google）'},
  moonshot:{id:'moonshot',label:'Kimi（Moonshot）'},qwen:{id:'qwen',label:'通义千问'},zai:{id:'zai',label:'智谱 GLM'},
  xai:{id:'xai',label:'Grok（xAI）'},openrouter:{id:'openrouter',label:'OpenRouter'},minimax:{id:'minimax',label:'MiniMax'}};
const identifier = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value);
const toolName = name => typeof name === 'string' && (name === 'subagent_fork' || TOOL_NAMES.some(t => name === t || name.endsWith('_'+t)));
const safe = value => String(value ?? '').replace(/[A-Z]:[\\/]+Users[\\/]+[^\s"'<>]*/gi,'[本机目录]')
  .replace(/\b(?:sk|ghp|gho|xox[baprs])[-_][A-Za-z0-9_-]{16,}\b/g,'[已隐藏]')
  .replace(/("(?:api[_-]?key|access_token|refresh_token|authorization|password|secret|token)"\s*:\s*")[^"]*/gi,'$1[已隐藏]');
const modelRef = value => typeof value === 'string' && value.length > 0 && value.length <= 256 && !/[\r\n]/.test(value) && safe(value) === value;
function preview(value) {
  let text = '', size = 0;
  const body = structured(value);
  const source = typeof value === 'string' && value.length > 65536 ? '[工具正文超过结构化上限]' : body == null ? safe(value) : JSON.stringify(body);
  for (const char of source) {
    size += new TextEncoder().encode(char).length;
    if (size > 2048) break;
    text += char;
  }
  return text;
}
// Full association bodies remain bounded and use the same privacy filtering as previews.
function structured(value) {
  if (typeof value !== 'string' || value.length > 65536) return null;
  const clean = data => Array.isArray(data) ? data.map(clean) : data && typeof data === 'object'
    ? Object.fromEntries(Object.entries(data).filter(([key]) => !/headers?|authorization|api[_-]?key|password|secret|.*token/i.test(key))
      .map(([key, item]) => [key, clean(item)])) : typeof data === 'string' ? safe(data) : data;
  const data = clean(decode(value));
  return new TextEncoder().encode(JSON.stringify(data)).length <= 65536 ? data : null;
}
export function progressNodes(timeline) {
  const spans = new Map();
  const walk = node => {
    if (!node) return;
    if (node.toolUseId) spans.set(node.toolUseId,node);
    (node.children ?? []).forEach(walk);
  };
  (timeline.turns ?? []).forEach(turn => walk(turn.trace));
  return [...(timeline.nodes ?? [])].sort((a,b) => a.seq-b.seq).flatMap(node => {
    if (node.kind === 'tool' && toolName(node.name)) {
      const span = spans.get(node.toolUseId) ?? node;
      return [{kind:'tool',name:node.name,status:node.status,
        session:identifier(timeline.sessionId) ? timeline.sessionId : null,seq:node.seq,
        tool_use_id:identifier(node.toolUseId) ? node.toolUseId : null,args:preview(node.argsPreview),args_json:structured(node.argsPreview),
        result_seq:node.resultSeq ?? null,result_json:structured(node.resultPreview),isError:['failed','error','cancelled'].includes(node.status),
        result_code:typeof span.error?.code === 'string' ? safe(span.error.code) : null,
        started_at:span.startedAt ?? null,ended_at:span.endedAt ?? null,
        result:node.name === 'subagent_fork' ? safe(node.resultPreview) : preview(node.resultPreview)}];
    }
    if (node.kind === 'assistant') return [{kind:'text',seq:node.seq,session:identifier(timeline.sessionId) ? timeline.sessionId : null,
      text:Array.from(safe(node.text)).slice(0,300).join('')}];
    const tool = node.summary?.split(' ')[0];
    if (node.kind !== 'approval' || !['decided', 'expired'].includes(node.state) || !toolName(tool)) return [];
    const args = structured(node.summary.slice(tool.length).trim());
    const candidates = (timeline.nodes ?? []).filter(n => n.kind === 'tool' && n.name === tool && n.seq < node.requestSeq
      && (n.resultSeq == null || node.requestSeq < n.resultSeq) && sameArguments(structured(n.argsPreview), args));
    const call = candidates.length === 1 ? candidates[0] : null;
    const unique = call && identifier(call.toolUseId) && timeline.nodes.filter(n => n.toolUseId === call.toolUseId).length === 1;
    return [{kind:'approval',tool,verdict:node.decision?.verdict,via:node.decision?.via,seq:node.seq,
      session:identifier(timeline.sessionId) ? timeline.sessionId : null,tool_use_id:unique ? call.toolUseId : null,args_json:args}];
  });
}
// Only numeric usage and validated timestamps may leave the AGH projection.
export function progressUsage(projection) {
  const turns = (projection.turns ?? []).filter(t => !t.inherited && t.usage);
  const calls = new Map();
  if (!turns.length) return null;
  for (const turn of turns) for (const call of turn.usage.calls ?? []) if (typeof call.id === 'string') calls.set(call.id,call);
  const rows = [...calls.values()];
  const finite = n => typeof n === 'number' && Number.isFinite(n) && n >= 0;
  const sum = values => values.every(finite) ? values.reduce((a,b) => a+b,0) : null;
  const stamp = value => typeof value === 'string' && /^\d{4}-\d\d-\d\dT[\d:.]+Z$/.test(value) && Number.isFinite(Date.parse(value)) ? value : null;
  const amounts = rows.map(c => c.billing?.source === 'estimated' ? c.billing.usdMicros : null);
  const known = amounts.filter(finite);
  const token = key => {
    if (key === 'reasoning' && !turns.every(t => t.usage.reasoningComplete === true)) return null;
    return sum(rows.length ? rows.map(c => c.tokens?.[key]) : turns.map(t => t.usage.totals?.[key]));
  };
  return {session_id:identifier(projection.sessionId) ? projection.sessionId : null,
    started_at:stamp(turns[0].startedAt),ended_at:projection.opState == null ? stamp(turns.at(-1).endedAt) : null,
    model_requests:null,recorded_model_calls:rows.filter(c => c.purpose === 'inference').length,
    tokens:Object.fromEntries(['input','output','cacheRead','cacheWrite','reasoning'].map(key => [key,token(key)])),
    costs:known.length ? [{currency:'USD',micros:sum(known)}] : [],missing_costs:amounts.length-known.length,
    billing_complete:rows.length > 0 && known.length === rows.length && turns.every(t => t.usage.billingComplete === true)};
}
export async function configuredModels(ctx, preference, reviewPreference) {
  const snapshot = await ctx.agnes.config.get();
  const apis = await ctx.agnes.apis();
  if (snapshot?.profile !== 'local-dev' || !Array.isArray(snapshot.accounts) || !Array.isArray(apis?.profile?.models)) {
    throw new Error('CONFIG');
  }
  const valid = model => modelRef(model?.id) && modelRef(model?.route);
  if (apis.profile.models.length > 1024 || !apis.profile.models.every(valid)) throw new Error('CONFIG');
  for (const account of snapshot.accounts) {
    if (typeof account.enabled !== 'boolean' || typeof account.credentialConfigured !== 'boolean' || !modelRef(account.route) ||
        !Array.isArray(account.models) || !account.models.every(model => modelRef(model?.id))) throw new Error('CONFIG');
  }
  const models = apis.profile.models.filter(model => snapshot.accounts.some(account => account.enabled && account.credentialConfigured &&
    account.route === model.route && account.models.some(row => row.id === model.id)))
    .map(({id,route,label}) => ({id,route,name:modelRef(label) ? label : id}));
  const choices = modelChoices(models.map(model => ({...model,label:model.name})), preference, reviewPreference);
  const reference = model => model ? {id:model.id,route:model.route} : null;
  return {profile:snapshot.profile,design:reference(choices.design),review:reference(choices.review),models,
    designConfigured:!!choices.design,reviewConfigured:!!choices.review};
}
export function createBridge(ctx, win = window) {
  let hello, peer, peerOrigin, serial = 0, timer, last = 0, reading = false, dirty = false, stopped = false, starting = false, pendingTool = '';
  let currentNodes = [], installation = null, workspaceId = null;
  const listeners = new Set(), seen = new Set(), theme = createEmbeddedTheme(win);
  const emit = (type, fields, re = hello) => {
    if (!stopped && hello && peer !== win) peer.postMessage({v:1,type,id:`gz-${Date.now()}-${++serial}`,re,...fields},peerOrigin);
  };
  const errors = {
    WORKSPACE:'未找到已登记的 guangzhu 工作区',MODEL:'模型不可用',BUSY:'已有会话正在运行',SESSION:'当前会话不匹配',
    PROMPT:'消息未能发送，请在 AGH 中检查会话',START:'会话建立失败',INVALID:'请求内容不完整',OPEN:'会话未找到',READY:'模型清单读取失败',CONFIG:'无法读取模型配置，请在官方设置检查权限后重新检查',
    SETTINGS:'无法打开设置，请在内嵌 AGH 侧栏点击设置',KEY_FORMAT:'key 的格式不对，请检查是否复制完整',
    KEY_REJECTED:'key 没通过验证：可能填错了，或者网络连不上服务商',KEY_SAVE:'AGH 没能保存 key，请重试',
  };
  const fail = (re,code,association = {}) => emit('gz.error',{code,message:errors[code] ?? 'AGH 操作失败',...association},re);
  const snapshot = () => ctx.session.getSnapshot();
  const normalized = path => /^[A-Za-z]:/.test(path) ? path.replaceAll('\\', '/').replace(/\/+$/, '').toLowerCase() : path;
  const workspaceBinding = async () => {
    const workspace = (await ctx.agnes.workspace.list()).items.find(row => installation ?
      row.workspaceId === workspaceId && row.available === true : row.name === 'guangzhu' && row.available !== false);
    if (!workspace?.path) throw new Error('workspace unavailable');
    // The AGH workspace alone (id and folder): an upgrade changes the build but not the install folder, so a park batch survives it
    const value = JSON.stringify([workspace.workspaceId ?? null, normalized(workspace.path)]);
    const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
    return {cwd:workspace.path, fingerprint:[...new Uint8Array(digest)].map(n => n.toString(16).padStart(2, '0')).join('')};
  };
  const read = async () => {
    timer = undefined;
    if (stopped || !hello || reading) return;
    reading = true;
    dirty = false;
    last = Date.now();
    const session_id = snapshot();
    try {
      const result = await ctx.session.projection.read();
      if (result.status === 'available' && snapshot() === session_id) {
        currentNodes = progressNodes(result.value);
        listeners.forEach(fn => fn());
        emit('gz.progress',{session_id,op:result.value.opState == null ? 'idle' : 'running',
          started:result.value.sessionId === session_id && (result.value.turns ?? []).some(turn => !turn.inherited),
          nodes:currentNodes,usage:progressUsage(result.value)});
      }
    }
    catch { /* A session switch may briefly have no projection. */ }
    finally {
      reading = false;
      if (dirty) schedule();
    }
  };
  const schedule = () => {
    dirty = true;
    if (!timer && !reading && !stopped) timer = win.setTimeout(read,Math.max(0,250-(Date.now()-last)));
  };
  const resume = () => {
    if (!hello || !ctx.session.handle) return;
    let record;
    try {record = JSON.parse(win.sessionStorage.getItem(KEY));}
    catch {
      win.sessionStorage.removeItem(KEY);
      return;
    }
    if (!record || record.session_id !== snapshot() || (record.installation_id ?? null) !== installation ||
        installation && record.workspace_id !== workspaceId) return;
    // Claim before invoking prompt: reloads or duplicate subscription notifications cannot send twice.
    win.sessionStorage.setItem(KEY+'.sent',JSON.stringify({re:record.re,session_id:record.session_id,project_id:record.project_id,
      installation_id:installation,workspace_id:workspaceId}));
    win.sessionStorage.removeItem(KEY);
    try {
      if (record.brief !== null) Promise.resolve(ctx.session.commands.prompt(record.brief)).catch(() => fail(record.re,'PROMPT'));
      emit('gz.session',{session_id:record.session_id,project_id:record.project_id},record.re);
      schedule();
    }
    catch {fail(record.re,'PROMPT');}
  };
  const navigate = session_id => {
    const url = new URL(win.location.href);
    url.searchParams.set('session',session_id);
    win.location.assign(url.href);
  };
  const receive = async event => {
    const m = event.data;
    if (win.parent === win || event.source !== win.parent || !DATA.desktopOrigins.includes(event.origin)) return;
    if (!m || m.v !== 1 || !TYPES.has(m.type) || !identifier(m.id) || safe(m.id) !== m.id) return;
    if (m.type === 'gz.hello') {
      if (m.app !== 'guangzhu-desktop') return;
      if (m.installation_id != null && !/^[a-f0-9]{64}$/.test(m.installation_id)) return;
      installation = m.installation_id ?? null;
      workspaceId = m.workspace_id ?? null;
      hello = m.id;
      peer = event.source;
      peerOrigin = event.origin;
      win.document.documentElement.setAttribute('data-gz-embedded','');
      theme.apply(win.document.documentElement.classList.contains('dark') ? 'dark' : 'light');
      try {
        const source = installation ? (await configuredModels(ctx).catch(() => ({models:[]})))
          .models.map(model => ({...model,label:model.name})) :
          (await ctx.agnes.apis()).profile.models ?? [];
        const models = source.map(({id,route,label}) => ({id:safe(id),route:safe(route),label:safe(label ?? id)}));
        const binding = await workspaceBinding().catch(() => null);
        emit('gz.ready',{models,workspace_binding:binding?.fingerprint ?? null},m.id);
        if (pendingTool) emit('gz.approval',{session_id:snapshot(),tool:pendingTool,pending:true});
        resume();
        schedule();
      } catch {fail(m.id,'READY');}
      return;
    }
    if (!hello || event.source !== peer || event.origin !== peerOrigin || seen.has(m.id)) return;
    seen.add(m.id);
    if (m.type === 'gz.theme') return theme.apply(m.theme);
    if (m.type === 'gz.openSettings') {
      const button = win.document.getElementById('settings');
      if (!button || button.disabled || button.getAttribute('aria-disabled') === 'true') return fail(m.id,'SETTINGS');
      button.click();
      return emit('gz.settings',{opened:true},m.id);
    }
    if (m.type === 'gz.saveKey') {
      const provider = Object.hasOwn(PROVIDERS,m.provider) ? PROVIDERS[m.provider] : null, key = typeof m.key === 'string' ? m.key.trim() : '';
      if (!provider || !/^[!-~]{8,4096}$/.test(key)) return fail(m.id,'KEY_FORMAT');
      try {
        const tested = await ctx.agnes.config.test({providerId:provider.id,apiKey:key});
        if (tested?.verified !== true || !tested.models?.length) return fail(m.id,'KEY_REJECTED');
        const model = (tested.models.find(row => row.id === provider.model) ?? tested.models[0]).id;
        const before = await ctx.agnes.config.get();
        await ctx.agnes.config.save({providerId:provider.id,apiKey:key,model,accountId:'gz-' + m.provider,label:provider.label + '（光筑）',
          enabled:true,makeDefault:m.provider === 'deepseek' || !before?.defaultAccountId});
        return emit('gz.keySaved',{provider:m.provider,model},m.id);
      } catch {return fail(m.id,'KEY_SAVE');}
    }
    if (['gz.registerWorkspace','gz.models'].includes(m.type)) {
      const association = {operation_id:m.operation_id,installation_id:m.installation_id};
      if (!installation || m.installation_id !== installation || !/^[a-f0-9]{32}$/.test(m.operation_id) ||
          typeof m.path !== 'string' || m.path.length > 4096 || /[\r\n]/.test(m.path)) return fail(m.id,'INVALID',association);
      try {
        const rows = m.type === 'gz.registerWorkspace' ? [(await ctx.agnes.workspace.add(m.path)).workspace] :
          (await ctx.agnes.workspace.list()).items;
        const workspace = rows.find(row => row.path === m.path && row.available === true && /^[a-f0-9]{64}$/.test(row.workspaceId));
        if (!workspace || m.type === 'gz.models' && workspace.workspaceId !== m.workspace_id) return fail(m.id,'WORKSPACE',association);
        workspaceId = workspace.workspaceId;
        const fields = m.type === 'gz.registerWorkspace' ?
          {workspace:{path:workspace.path,workspaceId,available:true}} : {metadata:await configuredModels(ctx,m.preference,m.review_preference)};
        // the first opening after an install says hello before the workspace is known; a park batch needs this binding
        const binding = await workspaceBinding().catch(() => null);
        return emit('gz.setup',{...association,...fields,workspace_binding:binding?.fingerprint ?? null},m.id);
      } catch {return fail(m.id,m.type === 'gz.models' ? 'CONFIG' : 'WORKSPACE',association);}
    }
    if (m.type === 'gz.start') {
      if (starting) return fail(m.id,'BUSY');
      const validProject = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(m.project_id ?? '') && safe(m.project_id) === m.project_id;
      const validBrief = m.brief === null || typeof m.brief === 'string' && m.brief.length > 0 && m.brief.length <= 50000;
      if (!validProject || m.workspace !== 'guangzhu' || !validBrief || !modelRef(m.design_model?.id) || !modelRef(m.design_model?.route)) {
        return fail(m.id,'INVALID');
      }
      if (installation && (m.installation_id !== installation || m.workspace_id !== workspaceId)) return fail(m.id,'WORKSPACE');
      starting = true;
      try {
        const pending = JSON.parse(win.sessionStorage.getItem(KEY) ?? 'null');
        const previous = JSON.parse(win.sessionStorage.getItem(KEY+'.sent') ?? 'null');
        if (pending?.re === m.id && (pending.installation_id ?? null) === installation &&
            (!installation || pending.workspace_id === workspaceId)) return resume();
        if (previous?.re === m.id && (previous.installation_id ?? null) === installation &&
            (!installation || previous.workspace_id === workspaceId)) {
          return emit('gz.session',{session_id:previous.session_id,project_id:previous.project_id},m.id);
        }
        const current = await ctx.session.projection.read();
        if (current.value?.opState != null) return fail(m.id,'BUSY');
        const models = (await ctx.agnes.apis()).profile.models ?? [];
        if (!models.some(row => row.id === m.design_model.id && row.route === m.design_model.route)) return fail(m.id,'MODEL');
        if (installation) {
          const metadata = await configuredModels(ctx);
          if (!metadata.models.some(model => model.id === m.design_model.id && model.route === m.design_model.route)) return fail(m.id,'MODEL');
        }
        const workspace = (await ctx.agnes.workspace.list()).items.find(row => installation ?
          row.workspaceId === workspaceId && row.available === true : row.name === m.workspace && row.available !== false);
        if (!workspace) return fail(m.id,'WORKSPACE');
        if (m.session_key != null && (!/^park-(design|review)-[a-f0-9]{32}$/.test(m.session_key) || m.brief !== null)) {
          return fail(m.id,'INVALID');
        }
        if (m.session_key && m.workspace_binding !== (await workspaceBinding()).fingerprint) return fail(m.id,'WORKSPACE');
        const session = await ctx.agnes.session.new({cwd:workspace.path,sessionKey:m.session_key ?? win.crypto.randomUUID()});
        await session.setModel({slot:'primary',route:m.design_model.route,model:m.design_model.id});
        await ctx.agnes.session.rename(session.id,m.evaluation === true ? m.project_id : '光筑 · '+m.project_id);
        win.sessionStorage.setItem(KEY,JSON.stringify({re:m.id,brief:m.brief,session_id:session.id,project_id:m.project_id,
          installation_id:installation,workspace_id:workspaceId}));
        navigate(session.id);
      } catch {fail(m.id,'START');}
      finally {starting = false;}
      return;
    }
    if (!identifier(m.session_id)) return fail(m.id,'INVALID');
    if (m.type === 'gz.open') {
      try {
        const binding = m.workspace_binding ? await workspaceBinding() : null;
        if (binding && binding.fingerprint !== m.workspace_binding) return fail(m.id,'WORKSPACE');
        let cursor, found = false;
        do {
          const page = await ctx.agnes.session.list({q:{prefix:m.session_id,...binding ? {cwd:binding.cwd} : {}},
            limit:500,...cursor ? {cursor} : {}});
          found = page.items.some(row => row.sessionId === m.session_id && (!binding || normalized(row.cwd ?? '') === normalized(binding.cwd)));
          cursor = page.next;
        } while (!found && cursor);
        if (found) navigate(m.session_id);
        else fail(m.id,'OPEN');
      } catch {fail(m.id,'OPEN');}
      return;
    }
    if (m.session_id !== snapshot() || !ctx.session.handle) return fail(m.id,'SESSION');
    try {
      if (m.workspace_binding && m.workspace_binding !== (await workspaceBinding()).fingerprint) return fail(m.id,'WORKSPACE');
      if (m.type === 'gz.cancel') await ctx.session.commands.cancel();
      else if (m.type === 'gz.parkPrompt' && /^park-(design|review)-[a-f0-9]{32}$/.test(m.session_id) &&
          typeof m.text === 'string' && m.text.trim() && m.text.length <= 50000) await ctx.session.commands.prompt(m.text);
      else if (m.type === 'gz.followup' && typeof m.text === 'string' && m.text.trim() && m.text.length <= 10000) {
        await ctx.session.commands.prompt(m.text);
      }
      else fail(m.id,'INVALID');
    } catch {fail(m.id,'PROMPT');}
  };
  win.addEventListener('message',receive);
  const off = ctx.session.projection.subscribe(schedule);
  const switched = ctx.session.subscribe(() => {
    resume();
    schedule();
  });
  return {getPending:() => pendingTool,getNodes:() => currentNodes,
    subscribe(fn) {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    approval(tool,pending,session_id = snapshot()) {
      if (!toolName(tool)) return;
      pendingTool = pending ? tool : '';
      listeners.forEach(fn => fn());
      emit('gz.approval',{session_id,tool,pending});
    },
    dispose() {
      stopped = true;
      win.clearTimeout(timer);
      win.removeEventListener('message',receive);
      off();
      switched();
      theme.dispose();
      win.document.documentElement.removeAttribute('data-gz-embedded');
    }};
}
