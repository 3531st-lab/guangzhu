import {computeSteps} from './steps.js';
import {beijingTime} from './data.js';

const stamp = node => [Date.parse(node.ts) || 0,Number(node.seq) || 0];
const compare = (a,b) => a[0]-b[0] || a[1]-b[1];
export function replayEvents(timeline, session) {
  const nodes = (timeline?.nodes ?? timeline ?? []).filter(node => node.session === session);
  return nodes.flatMap(node => {
    const events = [{node,at:stamp(node)}];
    if (node.kind === 'tool' && node.ended_at && Number.isFinite(node.result_seq)) {
      events.push({node,complete:true,at:[Date.parse(node.ended_at),node.result_seq]});
    }
    const evidence = node.invalid_job_events ?? (node.conflict_at && Number.isInteger(node.conflict_seq)
      ? [{seq:node.conflict_seq, ts:node.conflict_at, job_ids:node.invalid_job_ids ?? [], truncated:!!node.invalid_jobs_truncated}] : []);
    for (const conflict of evidence) if (conflict.ts && Number.isInteger(conflict.seq)) events.push({node, conflict, at:stamp(conflict)});
    return events;
  }).sort((a,b) => compare(a.at,b.at));
}
export function projectReplay(events, cursor) {
  const begun = new Set(), complete = new Set(), conflicts = new Map();
  for (const event of events.slice(0,cursor)) {
    if (event.conflict) conflicts.set(event.node, [...conflicts.get(event.node) ?? [], event.conflict]);
    else (event.complete ? complete : begun).add(event.node);
  }
  const future = new Set(['result_json', 'resultPreview', 'result_code', 'data', 'initial', 'completion', 'completion_index', 'wait_ids', 'isError']);
  const negative = ['invalid_job_events', 'invalid_job_ids', 'invalid_jobs_truncated', 'conflict_seq', 'conflict_at'];
  const nodes = [...begun].map(node => {
    const projected = node.kind === 'tool' && !complete.has(node)
      ? {...Object.fromEntries(Object.entries(node).filter(([key]) => !future.has(key))),
        result:'', status:'running', ended_at:null, result_seq:null} : {...node};
    for (const field of negative) delete projected[field];
    const evidence = conflicts.get(node);
    if (evidence) {
      projected.invalid_job_ids = evidence.flatMap(e => e.job_ids).sort();
      projected.invalid_jobs_truncated = evidence.some(e => e.truncated);
      projected.conflict_seq = evidence[0].seq;
      projected.conflict_at = evidence[0].ts;
      if (node.invalid_job_events) projected.invalid_job_events = evidence;
    }
    return projected;
  });
  const approvals = nodes.filter(n => n.kind === 'approval').map(n => ({...n,received_at:Date.parse(n.ts)}));
  return {nodes,stepsNodes:nodes.filter(n => n.kind !== 'approval' || !n.pending),approvals};
}
const labels = {allowed:'已批准','allowed-once':'仅本次批准','allowed-session':'本会话批准',rejected:'已拒绝',completed:'已完成',running:'执行中',error:'执行失败',cancelled:'已取消'};
const toolNames = {gz_new_project:'创建项目',gz_project_summary:'读取项目',gz_set_requirements:'保存需求',gz_fetch_weather:'获取天气',gz_generate_layout:'生成排布',
  gz_analyze:'分析设计',gz_edit_design:'修改设计',gz_compare_options:'比较方案',gz_crosscheck_yield:'发电复核',gz_record_review:'保存审核',gz_export:'导出方案'};
const element = (tag,text) => {
  const e = document.createElement(tag);
  if (text != null) e.textContent = text;
  return e;
};
function original(card,label,text) {
  if (!text) return;
  const details = element('details');
  details.append(element('summary',label),element('pre',typeof text === 'string' ? text : JSON.stringify(text,null,2)));
  card.append(details);
}
function render(node,renderTool) {
  const card = element('article');
  card.className = 'replay-entry';
  card.dataset.status = node.status ?? '';
  card.dataset.verdict = node.verdict ?? '';
  if (node.kind === 'review-complete') {
    card.append(element('small', `${beijingTime(node.ts)} · 回放里程碑`), element('strong', '独立审核完成（见审核会话）'));
    return card;
  }
  card.append(element('small',`${beijingTime(node.ts)} · 记录 ${node.seq}`));
  if (node.kind === 'text') {
    card.append(element('strong','Agent'),element('p',node.text));
    return card;
  }
  if (node.kind === 'approval') {
    card.append(element('strong',`${node.tool} · ${node.pending ? '申请审批（历史）' : labels[node.verdict] ?? node.verdict ?? '无决定记录'}`));
    return card;
  }
  if (node.kind === 'tool') {
    const name = Object.keys(toolNames).find(key => node.name === key || node.name?.endsWith('_'+key));
    card.append(element('strong',`${toolNames[name] ?? node.name} · ${labels[node.status] ?? node.status}`));
    if (renderTool) {
      const custom = renderTool(node);
      if (custom) card.append(custom);
    }
    else if (node.result) for (const step of computeSteps([node]).steps) {
      for (const metric of step.metrics) {
        const value = metric.value == null ? '未提供' : typeof metric.value === 'object' ? JSON.stringify(metric.value) : metric.value;
        card.append(element('p',`${metric.label}：${value}`));
      }
      for (const warning of step.warnings) card.append(element('p',String(warning)));
    }
    original(card,'查看调用参数',node.args);
    original(card,'查看原始返回',node.result);
    return card;
  }
  card.append(element('p',node.kind === 'child' ? `子会话${node.phase === 'ended' ? '结束' : '开始'} · ${node.session}` : node.kind));
  return card;
}
export function createReplay(container, options = {}) {
  const timeline = options.timeline ?? {nodes:[]}, all = timeline.nodes ?? timeline;
  const sessions = [...new Set(all.map(n => n.session).filter(Boolean))];
  const eventsFor = id => {
    const events = replayEvents(timeline, id), time = Date.parse(options.reviewCompletedAt);
    if (id === options.session && Number.isFinite(time) && time >= (events.at(-1)?.at[0] ?? 0))
      events.push({node:{kind:'review-complete', session:id, ts:options.reviewCompletedAt, seq:0}, at:[time,0]});
    return events;
  };
  let session = options.session ?? sessions[0], events = eventsFor(session), cursor = 0, timer, disposed = false;
  container.classList.add('replay-list');
  function pause() {
    clearInterval(timer);
    timer = null;
  }
  function seek(value) {
    if (disposed) return;
    cursor = Math.max(0,Math.min(events.length,Math.trunc(Number(value)||0)));
    const projection = projectReplay(events,cursor), fragment = document.createDocumentFragment();
    for (const node of projection.nodes) fragment.append(render(node,options.renderTool));
    if (!projection.nodes.length) fragment.append(element('p','从第一条执行记录开始回放。'));
    container.replaceChildren(fragment);
    const run = session === (options.session ?? sessions[0]) ? options.runOptions ?? {} : options.sessionOptions?.[session] ?? {};
    options.onSteps?.(computeSteps(projection.stepsNodes,{run,op:cursor === events.length ? 'idle' : 'running',approvals:projection.approvals}),
      {session, cursor, total:events.length, at:events[cursor - 1]?.at ?? null, nodes:projection.nodes});
    options.onCursor?.(cursor,events.length);
    container.scrollTop = container.scrollHeight;
    if (cursor === events.length) pause();
    return projection;
  }
  seek(0);
  return {seek,pause,sessions,get length() {return events.length;},
    play() {
      pause();
      if (cursor === events.length) seek(0);
      timer = setInterval(() => seek(cursor+1),650);
    },
    setSession(value) {
      pause();
      session = value;
      events = eventsFor(session);
      seek(0);
    },
    dispose() {
      disposed = true;
      pause();
      container.replaceChildren();
    }};
}
