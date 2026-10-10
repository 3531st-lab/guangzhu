import {computeSteps} from '/desktop/web/steps.js';
import {SessionRuns,parseTaskBrief,openSession} from '/session-runs.js';

const AGH_ORIGIN = 'http://127.0.0.1:4177';
const $ = id => document.getElementById(id);
const stamp = () => new Date().toISOString().replace(/[-:.TZ]/g,'');
const state = {models:[],ready:false,session_id:'',project_id:'',nodes:[],approvals:[],op:'idle',run:{},logs:[],logName:'t10-embed-'+stamp(),sequence:0};
const incoming = new Set(['gz.ready','gz.session','gz.progress','gz.approval','gz.error']);
const labels = {not_started:'未开始',running:'进行中',completed:'完成',issue:'有问题',skipped:'跳过'};
let diskQueue = Promise.resolve(), lastProgress = '', generatedBrief = '';
const sessionRuns = new SessionRuns();

async function post(path, payload) {
  const response = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? '请求失败');
  return data;
}
function status(text) {$('status').textContent = text;}
function safe(value) {
  return JSON.parse(JSON.stringify(value).replace(/[A-Z]:\\+(?:Users|Documents and Settings)\\+[^\\"\s]+/gi,'%USERPROFILE%').replace(/\bsk-[A-Za-z0-9_-]{8,}\b/g,'[REDACTED]'));
}
function log(direction, message, note = '') {
  const row = {at:new Date().toISOString(),direction,message:safe(message),...(note ? {note} : {})};
  state.logs.push(row);
  $('log-count').textContent = state.logs.length;
  const summary = message.type === 'gz.progress' ? {type:message.type,id:message.id,re:message.re,session_id:message.session_id,op:message.op,nodes:message.nodes?.length} : message;
  $('messages').textContent = state.logs.slice(-80).map(r => `${r.at} ${r.direction} ${r.message.type}${r.note ? ' '+r.note : ''}`).join('\n')+'\n\n最近消息\n'+JSON.stringify(safe(summary),null,2);
  const name = state.logName;
  diskQueue = diskQueue.then(() => post('/api/log',{name,data:row})).then(result => {$('disk').textContent = '已保存 '+result.saved;}).catch(error => {$('disk').textContent = '落盘失败：'+error.message;});
}
function send(type, payload = {}) {
  const message = {v:1,type,id:'h-'+Date.now()+'-'+(++state.sequence),...payload};
  log('out',message);
  $('agh').contentWindow.postMessage(message,AGH_ORIGIN);
  return message.id;
}
function updateModels(models) {
  if (JSON.stringify(models) === JSON.stringify(state.models)) return;
  state.models = models;
  const design = $('design-model'), review = $('review-model');
  design.replaceChildren(); review.replaceChildren();
  models.forEach((m,index) => {
    design.add(new Option(`${m.label ?? m.id} (${m.id})`,String(index)));
    review.add(new Option(`${m.label ?? m.id} (${m.id})`,m.route ? m.route+'/'+m.id : m.id));
  });
  const ds = models.findIndex(m => /deepseek/i.test(m.id+' '+m.label));
  const ag = models.findIndex(m => /agnes/i.test(m.id+' '+m.label));
  if (ds >= 0) design.value = String(ds);
  if (ag >= 0) review.selectedIndex = ag;
  if (!models.length) {design.add(new Option('无可用模型','')); review.add(new Option('agnes-3.0-flash','agnes-3.0-flash'));}
  $('start').disabled = !models.length;
}
function format(value) {return typeof value === 'object' ? JSON.stringify(value,null,2) : value == null ? '未提供' : String(value);}
function draw() {
  const computed = computeSteps(state.nodes,{run:state.run,op:state.op,approvals:state.approvals,now:Date.now()});
  state.computed = computed;
  $('steps').replaceChildren(...computed.steps.map(step => {
    const row = document.createElement('li'); row.className = step.state;
    const title = document.createElement('strong'); title.textContent = `${step.number}. ${step.title}`;
    const label = document.createElement('span'); label.className = 'state'; label.textContent = labels[step.state];
    row.append(title,label);
    const add = (text, cls = 'metric') => {const p = document.createElement('div'); p.className = cls; p.textContent = text; row.append(p);};
    if (step.waiting) add(`等你批准${step.countdown === null ? '' : ' · '+step.countdown+' 秒'}`,'waiting');
    if (step.detail) add(step.detail,'detail');
    step.metrics.forEach(item => add(item.label+'：'+format(item.value)));
    step.warnings.forEach(item => add(format(item),'contradiction'));
    step.rounds?.forEach((r,i) => add(`${i+1}. v${r.version ?? '?'} ${r.passed ?? '?'}/${r.total ?? '?'} · ${r.hard_failed === 0 ? '硬性规则全过' : r.failed.map(f => f.id).join('、')}`,'round'));
    if (step.raw && !step.metrics.length && !step.detail) add(step.raw.slice(0,200),'detail');
    return row;
  }));
  $('warning').hidden = !computed.warning;
  $('warning').textContent = computed.warning ?? '';
  const checkpoint = $('checkpoint'); checkpoint.replaceChildren();
  if (computed.stopped && state.session_id) {
    const text = document.createElement('p'); text.textContent = 'Agent 已停下\n'+computed.lastText; checkpoint.append(text);
    computed.suggestions.forEach(s => {const button = document.createElement('button'); button.textContent = '按建议'+s.number+'继续'; button.onclick = () => followup(`同意建议${s.number}：${s.text}。按一键模式继续，直到申请导出`); checkpoint.append(button);});
    if (computed.suggestions.length) {const stop = document.createElement('button'); stop.textContent = '到此为止'; stop.onclick = () => {log('local',{type:'checkpoint.stop',session_id:state.session_id}); status('本次标记为做不到；未发送消息。');}; checkpoint.append(stop);}
  }
}
window.addEventListener('message', event => {
  if (event.origin !== AGH_ORIGIN || event.source !== $('agh').contentWindow) return;
  const msg = event.data;
  if (!msg || msg.v !== 1 || typeof msg.id !== 'string' || !incoming.has(msg.type)) return;
  log('in',msg);
  if (msg.type === 'gz.ready') {
    state.ready = true; $('connection').textContent = '插件已连接'; updateModels(msg.models ?? []);
  } else if (msg.type === 'gz.session') {
    if (state.session_id !== msg.session_id) {state.nodes = []; state.approvals = [];}
    state.session_id = msg.session_id; state.project_id = msg.project_id; state.run = sessionRuns.accept(msg); $('session').value = msg.session_id; $('stop').disabled = false;
    status('会话就绪：'+msg.session_id);
  } else if (msg.type === 'gz.progress') {
    if (!state.session_id || msg.session_id !== state.session_id) return;
    state.nodes = msg.nodes ?? []; state.op = msg.op;
    const restored = sessionRuns.confirmOpen(msg);
    if (restored) {state.run = restored.run; state.project_id = restored.project_id; log('local',{type:'run.restored',...restored});}
    lastProgress = msg.id;
  } else if (msg.type === 'gz.approval') {
    if (!state.session_id || msg.session_id !== state.session_id) return;
    state.approvals.push({...msg,received_at:Date.now()});
  } else if (msg.type === 'gz.error') {sessionRuns.reject(msg.re); status(msg.code+'：'+msg.message);}
  draw();
});
function hello() {if (!state.ready) send('gz.hello',{app:'guangzhu-desktop'});}
$('agh').addEventListener('load',() => {state.ready = false; $('connection').textContent = '等候插件握手'; hello();});
setInterval(hello,1000);
setInterval(draw,1000);

async function generate() {
  const result = await post('/api/brief',{sample:$('sample').value,id:$('project').value,reviewer_model:$('review-model').value,review_mode:$('review-mode').value});
  $('brief').value = generatedBrief = result.brief;
  log('local',{type:'brief.generated',project_id:result.project_id,command:result.command});
  status('任务书已由 python -m guangzhu.brief 生成。');
}
function guarded(action) {return () => Promise.resolve().then(action).catch(error => status(error.message));}
$('generate').onclick = guarded(generate);
$('sample').onchange = () => {$('project').value = 't10-'+$('sample').value+'-'+stamp().slice(4,14);};
$('start').onclick = guarded(() => {
  const model = state.models[Number($('design-model').value)];
  if (!model) throw new Error('还没有可用的设计模型');
  const brief = $('conversation').checked ? null : $('brief').value;
  if (brief !== null && !brief.trim()) throw new Error('先生成任务书');
  if (!/^t10-[A-Za-z0-9_-]+$/.test($('project').value)) throw new Error('项目编号须以 t10- 开头');
  const parsed = parseTaskBrief(brief);
  if (parsed && parsed.project.id !== $('project').value) throw new Error('项目编号和任务书不一致，请重新生成');
  state.run = parsed?.run ?? {review:{enabled:true,mode:$('review-mode').value}}; state.session_id = ''; state.nodes = []; state.approvals = []; state.op = brief ? 'running' : 'idle';
  log('local',{type:'run.options',project_id:$('project').value,run:state.run});
  const request = send('gz.start',{brief,project_id:$('project').value,workspace:'guangzhu',design_model:{id:model.id,route:model.route}});
  sessionRuns.start(request,state.run);
  $('setup').open = false; draw();
});
function followup(text = $('followup').value) {
  if (!state.session_id || !text.trim()) throw new Error('需要会话编号与追问文本');
  state.op = 'running'; send('gz.followup',{session_id:state.session_id,text}); draw();
}
$('send-followup').onclick = guarded(() => followup());
$('stop').onclick = () => send('gz.cancel',{session_id:state.session_id});
$('open').onclick = () => {
  state.session_id = $('session').value.trim(); state.nodes = []; state.approvals = [];
  state.run = openSession(sessionRuns,send,{sessionId:state.session_id,generatedBrief,currentBrief:$('brief').value,projectId:$('project').value},log);
};
$('compact').onchange = () => document.querySelector('main').classList.toggle('compact',$('compact').checked);
$('comparison').onclick = () => {$('followup').value = '给我三套方案比一比。';};
$('price').onclick = () => {$('followup').value = '电价降 10% 呢？';};
$('multiline').onclick = () => {$('followup').value = '这是普通多行消息。\n第二行保持原样。\n\n空行之后仍然保持原样。请只回答“收到”。';};
$('html-text').onclick = () => {$('followup').value = '请原样显示这些字符：<b>不是粗体</b> & <script>不是脚本</script>。';};
$('unknown').onclick = () => send('gz.unknown-test',{note:'S9：应被丢弃，不应收到 re 对应的回应'});
$('wrong-origin').onclick = () => {
  const id = 'wrong-origin-'+stamp();
  const payload = {v:1,type:'gz.hello',id,app:'guangzhu-desktop'};
  const probe = document.createElement('iframe'); probe.hidden = true; probe.setAttribute('sandbox','allow-scripts');
  probe.srcdoc = '<script>parent.frames[0].postMessage('+JSON.stringify(payload)+',"'+AGH_ORIGIN+'");<\/script>';
  log('probe',payload,'来自 sandbox iframe 的 null origin；插件应丢弃');
  document.body.append(probe); setTimeout(() => probe.remove(),3000);
};
$('error-test').onclick = () => {
  const model = state.models[Number($('design-model').value)];
  if (!model) return status('先等待模型清单');
  send('gz.start',{brief:null,project_id:'t10-error-probe',workspace:'t10-workspace-that-does-not-exist',design_model:{id:model.id,route:model.route}});
};
$('save').onclick = guarded(async () => {
  await diskQueue;
  const result = await post('/api/save',{name:state.logName,data:{...state,lastProgress,exported_at:new Date().toISOString()}});
  status('已导出 '+result.saved);
});
$('reset-log').onclick = () => {state.logName='t10-embed-'+stamp(); state.logs=[]; $('messages').textContent=''; $('log-count').textContent='0'; status('已新建日志段 '+state.logName);};
window.harness = {state,computeSteps,send,followup,generate};
const presets = await (await fetch('/api/presets')).json();
presets.forEach(p => $('sample').add(new Option(p.label,p.id)));
$('sample').onchange();
await generate().catch(error => status(error.message));
draw(); hello();
