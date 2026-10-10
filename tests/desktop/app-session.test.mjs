import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as data from '../../desktop/web/data.js';
import {resolvedTools} from '../../desktop/web/tool-results.js';
import {Setup} from '../../desktop/web/setup.js';
import {computeSteps} from '../../desktop/web/steps.js';
import {ParkQueue} from '../../desktop/web/park-queue.js';
import {ParkView, queueMarkup} from '../../desktop/web/park-view.js';
import {financialForm, financialResult, livestockResult} from '../../desktop/web/economic-ui.js';
import {wiringPanel, wiringDetails} from '../../desktop/web/wiring-ui.js';

// The archived runs these fixtures came from are not part of the public repository; plain stand-ins keep the
// session tests that do not depend on their details, the others are skipped.
const read = (path, standIn) => {
  try { return JSON.parse(readFileSync(new URL('../../'+path,import.meta.url),'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return standIn; throw error; }
};
const failed = read('runs/gz-t14-changzhou-004/verification.json', {passed:false,checks:[],review:{requested:false}});
const failedNodes = read('runs/gz-t14-changzhou-004/timeline.json', {nodes:[]}).nodes;
const checkpoint = read('runs/t10-impossible-004/timeline.json', {nodes:[]}).nodes;
const exported = {kind:'tool',name:'gz_export',status:'completed',result:'{"ok":true,"version":3}'};
const certificate = passed => ({run_id:'archive',verification:{passed,checks:[],review:{requested:false}},result:{selected_version:3},selected_version:3});

async function app({search='',preference=null,fileProgress=null,runsResponse=null,existsResponse=null,setupResponse=null,hash='#run'}={}) {
  const events = {}, elements = new Map(), requests = [], archives = [], selected = new Map();
  const intervals = [];
  let respond = async () => certificate(false);
  // Transport and DOM are inert; execute the actual application handlers without a browser/server.
  class Bridge {
    constructor(frame,onMessage) {this.onMessage=onMessage; this.logs=[]; this.models=[];}
    setAvailable() {}
    setTheme(value) {this.theme=value;}
    send(type,payload,request) {this.logs.push({message:{type,...payload},request});}
  }
  const element = () => ({innerHTML:'',dataset:{},style:{},classList:{toggle(){},add(){},remove(){}},
    append(child){this.appended=child;},contentWindow:{postMessage(){}},
    addEventListener(){},getBoundingClientRect:() => ({left:0,top:0,width:800,height:600})});
  const document = {createElement:element,documentElement:element(),querySelector:selector => selected.get(selector) ?? null,querySelectorAll:() => [],
    getElementById(id) {if (!elements.has(id)) elements.set(id,element()); return elements.get(id);},addEventListener:(type,fn) => {events[type]=fn;}};
  const fetch = async (path,options) => {
    const body = options.body ? JSON.parse(options.body) : null; requests.push({path,body});
    const value = path === '/api/runs/finish' || path.endsWith('/report') ? await respond(body) :
      path === '/api/setup/status' ? await (setupResponse?.() ?? {installation:{installed:false,id:'development'},required:false,ready:true,steps:[]}) :
      path === '/api/runs' ? await (runsResponse?.() ?? {runs:archives}) : path.startsWith('/api/roofs') ? {roofs:[]} :
      path.endsWith('/exists') ? await (existsResponse?.(path) ?? {exists:false}) : path === '/api/brief' ? {brief:'fixture-task',errors:[]} : path.endsWith('/progress') ? fileProgress : {agh:{connected:false}};
    return {ok:true,json:async () => value};
  };
  const globals = {...data,HEAT_COLORS:['red','orange','green'],ParkQueue,ParkView,queueMarkup,
    Bridge,setAghOrigin(){},Setup,computeSteps,resolvedTools,financialForm,financialResult,livestockResult,wiringPanel,wiringDetails,document,fetch,
    location:{hash,search},localStorage:{getItem:key => key==='gz-design-model' ? preference : null,setItem(){}},
    window:{addEventListener(){}},
    matchMedia:() => ({matches:false,addEventListener(){}}),setInterval:fn => intervals.push(fn),clearInterval(){},
    setTimeout(){},clearTimeout(){},requestAnimationFrame:fn => fn()};
  const source = readFileSync(new URL('../../desktop/web/app.js',import.meta.url),'utf8').replace(/^import[\s\S]*?;\r?\n/gm,'');
  const execute = Object.getPrototypeOf(async function(){}).constructor;
  const exposed = 'state,bridge,setup,checkConnection,start,finishSession,render,formPage,activeComputed,startReview,resumeSession,resultPage,resultTitle,'+
    'runPage,replayUsage,stepsMarkup,resultPanel,settings,theme,recordsPage,filesMarkup,openTarget,newPage,selectRoof,guarded,'+
    'parkQueue,requireParkWorkspace';
  const instance = await new execute(...Object.keys(globals),source+'\nreturn {'+exposed+'};')(...Object.values(globals));
  const s = {id:'same-native-session',project:'same-project',nodes:structuredClone(failedNodes),approvals:[{tool:'gz_set_requirements',verdict:'allowed-session'}],op:'idle',run:{review:{enabled:false}},verification:structuredClone(failed)};
  instance.state.sessions.set(s.id,s); instance.state.active=s.id; instance.state.design=s.id; instance.state.final={verification:s.verification}; instance.state.records=archives;
  archives.push({run_id:'earlier-failed-attempt',verification:structuredClone(failed)});
  return {...instance,s,archives,requests,elements,selected,location:globals.location,setResponse:fn => {respond=fn;},
    poll:() => intervals[0](),
    progress:(op,nodes=s.nodes,usage) => instance.bridge.onMessage({type:'gz.progress',session_id:s.id,op,nodes,usage}),
    click:dataset => events.click({target:{closest:() => ({dataset})}}),
    input:(field,value) => events.input({target:{dataset:{field},value}}),
    suggest:() => events.click({target:{closest:() => ({dataset:{suggestion:'0'}})}})};
}

test('queued native workspace conflict holds the persisted item instead of failing into another start', async () => {
  const f = await app();
  const item = {id:'park-item', stage:'design', status:'creating', design_session:'park-native',
    workspace_binding:'a'.repeat(64), spec:{template:'park-template'}};
  f.parkQueue.queue = {items:[item]};
  const events = [];
  f.parkQueue.event = async (action, payload) => {events.push({action, payload});};
  const request = {queue:item.id, run:{review:{enabled:false}}, project:'park-project'};
  f.state.startRequest = request;
  await f.bridge.onMessage({type:'gz.error', code:'WORKSPACE', message:'原工作区不匹配'}, request);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(events[0].action, 'hold');
  assert.equal(item.status, 'creating');
  assert.equal(f.bridge.logs.some(row => row.message.type === 'gz.start'), false);
  f.bridge.workspaceBinding = 'b'.repeat(64);
  assert.throws(() => f.requireParkWorkspace(item), /原工作区关联/);
});

test('archived park design holds a workspace conflict and resumes its fixed reviewer', async () => {
  const f = await app();
  const item = {id:'park-item', stage:'design', status:'running', design_session:f.s.id,
    review_session:'park-fixed-review', workspace_binding:'a'.repeat(64), spec:{id:f.s.project, template:'park-template'}};
  const following = {id:'following', status:'pending', spec:{template:'following-roof'}};
  f.parkQueue.queue = {items:[item, following]};
  const events = [];
  f.parkQueue.event = async (action, payload) => {
    events.push({action, payload});
    if (action === 'review') Object.assign(item, {stage:'review', status:'creating'});
  };
  f.s.nodes = [exported];
  f.s.run = {review:{enabled:true, mode:'independent', model:'agnes-3.0-flash'}};
  f.state.reviewCount = 0;
  f.bridge.ready = true;
  f.bridge.models = [{id:'agnes-3.0-flash', route:'review-route'}];
  f.bridge.workspaceBinding = 'b'.repeat(64);
  f.setResponse(async () => ({...certificate(false), review_prompt:'review archived design',
    verification:{checks:Array.from({length:4}, () => ({passed:true})), review:{requested:true, passed:false}}}));
  await assert.rejects(f.finishSession(f.s), error => error.recoverable === true);
  assert.equal(f.s.result.selected_version, 3);
  assert.deepEqual(events.map(event => event.action), ['hold']);
  assert.equal(item.stage, 'design');
  assert.equal(item.status, 'running');
  assert.equal(f.state.reviewCount, 0);
  assert.equal(f.bridge.logs.some(row => row.message.type === 'gz.start'), false);
  f.bridge.workspaceBinding = item.workspace_binding;
  await f.startReview(f.s);
  assert.deepEqual(events.map(event => event.action), ['hold', 'review']);
  assert.equal(f.parkQueue.item.id, item.id);
  assert.equal(following.status, 'pending');
  const started = f.bridge.logs.filter(row => row.message.type === 'gz.start');
  assert.equal(started.length, 1);
  assert.equal(started[0].message.session_key, item.review_session);
  assert.equal(started[0].message.workspace_binding, item.workspace_binding);
});

function delayedRecords() {
  const pending=[];
  const respond=()=>new Promise((resolve,reject)=>pending.push({resolve,reject}));
  return {pending,respond};
}

const flushRecords=()=>new Promise(setImmediate);
const recordRows=id=>({runs:[{run_id:id,project_id:id,ended_at:'2026-10-03T10:00:00Z'}]});
const requestRecords=(a,kind)=>a.click({action:kind==='manual' ? 'records-refresh' : 'finish-retry'});

for (const [earlier,latest] of [['startup','manual'],['startup','archive'],['manual','manual'],
  ['manual','archive'],['archive','manual']]) {
  test('newer '+latest+' records survive late '+earlier+' response through actual handlers',async()=>{
    const transport=delayedRecords();
    const a=await app({runsResponse:transport.respond});
    a.location.hash='#records';
    await a.render();
    if (earlier!=='startup') {
      transport.pending[0].resolve(recordRows('initial-record'));
      await flushRecords();
    }
    const older=earlier==='startup' ? null : requestRecords(a,earlier);
    await flushRecords();
    const olderResponse=transport.pending.at(-1);
    const newer=requestRecords(a,latest);
    await flushRecords();
    assert.equal(transport.pending.length,earlier==='startup' ? 2 : 3);
    transport.pending.at(-1).resolve(recordRows('newer-record'));
    await newer;
    assert.deepEqual(a.state.records.map(r=>r.run_id),['newer-record']);
    const displayed=a.elements.get('view').innerHTML;
    olderResponse.resolve(recordRows('older-record'));
    await older;
    await flushRecords();
    assert.deepEqual(a.state.records.map(r=>r.run_id),['newer-record']);
    assert.equal(a.elements.get('view').innerHTML,displayed);
  });
}

for (const latest of ['manual','archive']) {
  test('failed latest '+latest+' request keeps stored records and rejects late startup data',async()=>{
    const transport=delayedRecords();
    const a=await app({runsResponse:transport.respond});
    const stored=a.state.records;
    const newer=a.guarded(()=>requestRecords(a,latest))();
    await flushRecords();
    transport.pending[1].reject(new Error('records refresh failed'));
    await newer;
    assert.equal(a.elements.get('notice').textContent,'records refresh failed');
    transport.pending[0].resolve(recordRows('older-record'));
    await flushRecords();
    assert.equal(a.state.records,stored);
    assert.deepEqual(a.state.records.map(r=>r.run_id),['earlier-failed-attempt']);
    assert.equal(a.elements.get('notice').textContent,'records refresh failed');
    if (latest==='archive') assert.equal(a.s.finishError,'records refresh failed');
  });
}

test('archive list response loses ownership when its design resumes',async()=>{
  const transport=delayedRecords();
  const a=await app({runsResponse:transport.respond});
  transport.pending[0].resolve(recordRows('stored-record'));
  await flushRecords();
  const stored=a.state.records;
  const finishing=requestRecords(a,'archive');
  await flushRecords();
  a.resumeSession(a.s);
  transport.pending[1].resolve(recordRows('obsolete-archive-record'));
  await finishing;
  assert.equal(a.state.records,stored);
  assert.deepEqual(a.state.records.map(r=>r.run_id),['stored-record']);
  assert.equal(a.state.final,null);
  assert.equal(a.s.verification,null);
  assert.equal(transport.pending.length,2);
});

for (const page of ['new','records','form','result','replay']) {
  test('first slow records response populates data and respects current '+page+' page',async()=>{
    const transport=delayedRecords();
    const a=await app({runsResponse:transport.respond});
    a.location.hash='#'+page;
    a.state.route=page;
    if (page==='form') {
      const project=read('data/demo/projects/changzhou-demo/project.json');
      a.state.roofs=[{id:'fixture-roof',geometry:project.roof,project,area_m2:3000,dimensions_m:[60,50]}];
      a.selectRoof('fixture-roof');
    }
    if (['new','records','form'].includes(page)) await a.render();
    else a.elements.get('view').innerHTML='existing '+page+' content';
    const displayed=a.elements.get('view').innerHTML;
    transport.pending[0].resolve(recordRows('slow-first-record'));
    await flushRecords();
    assert.deepEqual(a.state.records.map(r=>r.run_id),['slow-first-record']);
    if (['new','records'].includes(page)) assert.match(a.elements.get('view').innerHTML,/slow-first-record/);
    else assert.equal(a.elements.get('view').innerHTML,displayed);
    assert.equal(transport.pending.length,1);
  });
}

test('late startup records do not render when the hash has left the records route',async()=>{
  const transport=delayedRecords();
  const a=await app({runsResponse:transport.respond});
  a.state.route='records';
  a.location.hash='#form';
  const displayed=a.elements.get('view').innerHTML;
  transport.pending[0].resolve(recordRows('slow-first-record'));
  await flushRecords();
  assert.deepEqual(a.state.records.map(r=>r.run_id),['slow-first-record']);
  assert.equal(a.elements.get('view').innerHTML,displayed);
});

test('home groups demos and real roofs while excluding boundary and impossible templates',async () => {
  const a = await app(), project = read('data/demo/projects/changzhou-demo/project.json');
  a.state.roofs = ['demo','real','boundary','impossible'].map(collection => ({
    id: 'roof-' + collection,name: 'name-' + collection,collection,geometry:project.roof,area_m2:3000,dimensions_m:[60,50]
  }));
  a.selectRoof('roof-demo');
  const markup = a.newPage();
  assert.match(markup,/>演示<\/h3>/);
  assert.match(markup,/>真实园区<\/h3>/);
  assert.match(markup,/data-roof="roof-demo" aria-pressed="true"/);
  assert.match(markup,/data-roof="roof-real" aria-pressed="false"/);
  assert.doesNotMatch(markup,/roof-boundary|roof-impossible/);
  a.selectRoof('roof-real');
  assert.match(a.newPage(),/data-roof="roof-real" aria-pressed="true"/);
  assert.equal(a.state.form.template,'roof-real');
});

test('legacy roof without collection remains in demo group and retains the selected template',async () => {
  const a = await app(), project = read('data/demo/projects/changzhou-demo/project.json');
  a.state.roofs = [{id:'changzhou-demo',name:project.name,geometry:project.roof,area_m2:3000,dimensions_m:[60,50]}];
  a.selectRoof('changzhou-demo');
  assert.match(a.newPage(),/data-roof="changzhou-demo" aria-pressed="true"/);
  assert.match(a.newPage(),/rooflist scroll/);
  assert.equal(a.state.form.template,'changzhou-demo');
});

test('eval query exposes and selects boundary/impossible roofs through existing form flow',async () => {
  const a=await app({search:'?eval=1'}), project=read('data/demo/projects/changzhou-demo/project.json');
  assert.ok(a.requests.some(r => r.path==='/api/roofs?all=1'));
  a.state.roofs=['demo','real','boundary','impossible'].map(collection => ({
    id:'roof-'+collection,name:'name-'+collection,collection,geometry:project.roof,area_m2:3000,dimensions_m:[60,50]
  }));
  a.selectRoof('roof-demo');
  assert.match(a.newPage(),/>边界案例<\/h3>/);
  assert.match(a.newPage(),/>做不到案例<\/h3>/);
  for (const collection of ['boundary','impossible']) {
    await a.click({roof:'roof-'+collection});
    assert.equal(a.state.form.template,'roof-'+collection);
    assert.match(a.newPage(),new RegExp('data-roof="roof-'+collection+'" aria-pressed="true"'));
    assert.equal(a.state.form.compare,true);
    assert.equal(a.state.form.review,true);
    assert.equal(a.state.form.exportOn,true);
  }
  const normal=await app({search:'?eval=10'});
  assert.ok(normal.requests.some(r => r.path==='/api/roofs'));
});

test('evaluation start/finish transmit the flag and existing model settings can select Agnes',async () => {
  const agnes={id:'agnes-3.0-flash',route:'agnes',label:'Agnes'}, pro={id:'deepseek-v4-pro',route:'deepseek',label:'Pro'};
  const a=await app({search:'?eval=1',preference:'agnes/agnes-3.0-flash'});
  a.bridge.models=[pro,agnes];
  a.bridge.onMessage({type:'gz.ready'});
  assert.equal(a.state.designModel,agnes);
  a.settings();
  assert.match(a.elements.get('settings-content').innerHTML,/value="agnes\/agnes-3.0-flash" selected/);
  const ordinary=await app();
  ordinary.bridge.models=[agnes,pro];
  ordinary.bridge.onMessage({type:'gz.ready'});
  assert.equal(ordinary.state.designModel,pro);
  a.s.nodes=[];
  await a.finishSession(a.s,true);
  assert.equal(a.requests.find(r => r.path==='/api/runs/finish').body.evaluation,true);
  const project=read('data/demo/projects/changzhou-demo/project.json');
  a.state.roofs=[{id:'roof-boundary',name:'boundary',collection:'boundary',geometry:project.roof,area_m2:3000,dimensions_m:[60,50]}];
  a.selectRoof('roof-boundary');
  a.state.form.id='eval-1003-b01-E-1';
  a.state.form.review=false;
  a.state.form.compare=false;
  a.state.form.exportOn=false;
  a.bridge.ready=true;
  await a.start();
  const message=a.bridge.logs.find(r => r.message.type==='gz.start').message;
  assert.equal(message.evaluation,true);
  assert.equal(message.project_id,'eval-1003-b01-E-1');
  assert.equal(message.design_model,agnes);
});

test('files keep approved hashes separate from post-run report status and HTML fallback',async () => {
  const a = await app();
  const files = {files:{'layout-v2.dxf':'1234567890abcdef','bom-v2.xlsx':'abcdef0123456789'}};
  let markup = a.filesMarkup({files,report:{status:'html-only',files:[{name:'report-v2.html'}],hint:'可用浏览器打印成 PDF'}});
  assert.match(markup,/>12345678</);
  assert.match(markup,/>abcdef01</);
  assert.match(markup,/title="1234567890abcdef"/);
  assert.equal((markup.match(/运行结束后生成/g) ?? []).length,0);
  assert.match(markup,/可用浏览器打印成 PDF/);
  assert.match(markup,/data-action="open-report"/);
  markup = a.filesMarkup({files,report:{status:'error',files:[],error:'方案书生成失败'}});
  assert.match(markup,/方案书生成失败/);
  assert.doesNotMatch(markup,/data-action="open-report"/);
});

test('eligible archive report button only uses the local regeneration endpoint',async () => {
  const a = await app();
  a.archives.push({run_id:'ready-archive',project_id:'old-project',can_report:true,selected_version:2,verification:{checks:[]}});
  a.archives.push({run_id:'incomplete-archive',project_id:'old-project',can_report:false,verification:{checks:[]}});
  const markup = a.recordsPage();
  assert.match(markup,/data-report="ready-archive"/);
  assert.doesNotMatch(markup,/data-report="incomplete-archive"/);
  a.setResponse(async () => ({status:'html-only',hint:'可用浏览器打印成 PDF'}));
  await a.click({report:'ready-archive'});
  assert.deepEqual(a.requests.filter(r => r.path.endsWith('/report')), [{path:'/api/runs/ready-archive/report',body:{}}]);
  assert.equal(a.bridge.logs.length,0);
  assert.equal(a.requests.some(r => r.path.endsWith('/finish')),false);
  assert.equal(a.elements.get('notice').textContent,'可用浏览器打印成 PDF');
});

test('opening a report uses the displayed archive identity, not a stale session or prior result',async () => {
  const a = await app();
  a.state.route = 'result';
  a.state.result = {project_id:'archive-project',selected_version:2,run_id:'archive-run'};
  a.state.final = {run_id:'stale-run'};
  await a.openTarget('report');
  assert.equal(a.requests.at(-1).body.run_id,'archive-run');
  a.state.route = 'run';
  a.s.result = {project_id:'current-project',selected_version:3,run_id:'current-run'};
  await a.openTarget('report');
  assert.equal(a.requests.at(-1).body.run_id,'current-run');
});

test.skip('native followup invalidates a failed current certificate but preserves archived failures, nodes and approvals',async () => {
  const a=await app(), oldNodes=a.s.nodes, approvals=a.s.approvals, archive=JSON.stringify(a.archives);
  assert.match(a.runPage(),/核对未通过/);
  a.progress('running');
  assert.equal(a.s.verification,null); assert.equal(a.state.final,null);
  assert.match(a.runPage(),/运行中/); assert.doesNotMatch(a.runPage(),/核对未通过|已完成/);
  a.state.runTab='核对'; assert.match(a.runPage(),/导出后从执行记录核对/);
  assert.equal(a.s.nodes,oldNodes); assert.equal(a.s.approvals,approvals); assert.equal(JSON.stringify(a.archives),archive);
  a.progress('idle',checkpoint); // A genuine checkpoint stays undecided, not a restored old failure/pass.
  assert.match(a.runPage(),/需要你决定/); assert.equal(a.s.verification,null);
});

test.skip('desktop suggestion also invalidates old pass/results before sending the same-session followup',async () => {
  const a=await app(); a.s.nodes=checkpoint; a.s.verification=certificate(true).verification;
  a.s.result={selected_version:3}; a.state.final=certificate(true); a.s.ended=true;
  await a.suggest();
  assert.equal(a.s.op,'running'); assert.equal(a.s.ended,false); assert.equal(a.s.verification,null);
  assert.equal(a.s.result,null); assert.equal(a.state.final,null);
  assert.doesNotMatch(a.runPage(),/查看结果|已完成|核对未通过/);
  const sent=a.bridge.logs.at(-1).message; assert.equal(sent.type,'gz.followup'); assert.equal(sent.session_id,a.s.id);
  assert.match(sent.text,/^同意建议①：/); assert.equal(a.archives[0].verification.passed,false);
});

test('a continued turn needs a new export and rechecks even if its version equals the earlier export',async () => {
  const a=await app(); a.s.nodes=[exported]; await a.finishSession(a.s);
  assert.equal(a.requests.filter(r => r.path.endsWith('/finish')).length,1);
  a.progress('running'); a.s.op='idle'; await a.finishSession(a.s);
  assert.equal(a.requests.filter(r => r.path.endsWith('/finish')).length,1,'old export must not certify the new turn');
  a.s.nodes=[exported,{...exported}]; await a.finishSession(a.s);
  assert.equal(a.requests.filter(r => r.path.endsWith('/finish')).length,2,'same version still requires a fresh certificate');
  assert.equal(a.s.verification.passed,false,'new failed verification remains failed');
});

test('a finish response for the old turn cannot restore stale verification after native continuation',async () => {
  const a=await app(); let resolve;
  a.setResponse(() => new Promise(done => {resolve=done;}));
  const finishing=a.finishSession(a.s,true);
  a.progress('running'); resolve(certificate(true)); await finishing;
  assert.equal(a.s.verification,null); assert.equal(a.state.final,null);
  assert.match(a.runPage(),/运行中/); assert.equal(a.archives[0].verification.passed,false);
});

test('design, independent review and returning idle projections finish each native session only once',async () => {
  const a=await app();
  a.s.nodes=[exported];
  a.setResponse(async()=>({...certificate(true),verification:{passed:true,checks:[],review:{passed:true,requested:true}}}));
  await a.finishSession(a.s);
  const reviewer={...a.s,id:'independent-review',review:true,nodes:[{
    kind:'tool',name:'gz_record_review',status:'completed',result:'{"ok":true,"file":"review.json"}'
  }]};
  a.state.sessions.set(reviewer.id,reviewer);
  a.s.reviewSession=reviewer.id;
  await a.finishSession(reviewer);
  assert.deepEqual(a.bridge.logs.at(-1).message,{type:'gz.open',session_id:a.s.id});
  a.progress('idle');
  await new Promise(setImmediate);
  a.bridge.onMessage({type:'gz.progress',session_id:reviewer.id,op:'idle',nodes:reviewer.nodes});
  await new Promise(setImmediate);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,2);
  await a.click({action:'finish-retry'});
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,3,'manual retry clears the active session key');
  await a.finishSession(reviewer);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,3,'manual design retry leaves the review key intact');
});

test('task and finish packets expose reviewer ID without the account route',async () => {
  const model={id:'agnes-3.0-flash',route:'account-private-route',label:'Agnes'};
  const form={id:'id-only-review',template:'l-shape',text:'保留通道',keep:[],maxRounds:6,review:true,exportOn:true};
  const before=structuredClone(model), spec=data.formSpec(form,model);
  const finish=data.finishRequest({id:'native-design',project:form.id,nodes:[exported]},null,model);
  assert.equal(spec.reviewer_model,model.id);
  assert.equal(finish.reviewer_model,model.id);
  assert.doesNotMatch(JSON.stringify({spec,finish}),/account-private-route/);
  assert.deepEqual(model,before);
});

for (const declared of ['agnes-3.0-flash','account-old-route/agnes-3.0-flash']) {
  test('review creation resolves the current public route for '+declared,async () => {
    const a=await app(), current={id:'agnes-3.0-flash',route:'account-current-route',label:'Agnes'};
    a.s.nodes=[exported];
    a.s.run={review:{enabled:true,mode:'independent',model:declared}};
    const original=structuredClone(a.s.run);
    a.state.reviewCount=0;
    a.state.reviewModel={id:'another-agnes',route:'stale-default-route'};
    a.bridge.ready=true;
    a.bridge.models=[a.state.reviewModel,current];
    a.setResponse(async () => ({...certificate(false),review_prompt:'reviewer_model=agnes-3.0-flash',
      verification:{checks:Array.from({length:4},()=>({passed:true})),review:{requested:true,passed:false}}}));
    await a.finishSession(a.s);
    assert.equal(a.requests.find(r=>r.path==='/api/runs/finish').body.reviewer_model,current.id);
    const created=a.bridge.logs.find(r=>r.message.type==='gz.start').message;
    assert.equal(created.design_model,current);
    assert.equal(created.design_model.route,'account-current-route');
    assert.equal(created.brief,'reviewer_model=agnes-3.0-flash');
    assert.deepEqual(a.s.run,original,'legacy stored run options are not rewritten');
  });
}

test('missing declared review model retains the archive and never starts a substitute',async () => {
  const a=await app();
  a.s.nodes=[exported];
  a.s.run={review:{enabled:true,mode:'independent',model:'agnes-3.0-flash'}};
  a.state.reviewCount=0;
  a.state.reviewModel={id:'another-agnes',route:'fallback-route'};
  a.bridge.ready=true;
  a.bridge.models=[a.state.reviewModel];
  a.setResponse(async () => ({...certificate(false),review_prompt:'reviewer_model=agnes-3.0-flash',
    verification:{checks:Array.from({length:4},()=>({passed:true})),review:{requested:true,passed:false}}}));
  await assert.rejects(a.finishSession(a.s),/找不到任务书指定的审核模型/);
  assert.equal(a.requests.find(r=>r.path==='/api/runs/finish').body.reviewer_model,'agnes-3.0-flash');
  assert.equal(a.s.result.selected_version,3);
  assert.equal(a.state.reviewCount,0);
  assert.ok(!a.bridge.logs.some(r=>r.message.type==='gz.start'));
});

test('failed finish request clears only its session key and allows retry',async () => {
  const a=await app();
  a.s.nodes=[exported];
  a.setResponse(async()=>{throw new Error('temporary archive failure');});
  await assert.rejects(a.finishSession(a.s),/temporary archive failure/);
  assert.equal(a.s.finishKey,'');
  a.setResponse(async()=>certificate(false));
  await a.finishSession(a.s);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,2);
  await a.finishSession(a.s);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,2);
});

test.skip('run footer switches matching live projection to exported usage and discards stale archive on continuation',async () => {
  const a=await app(), p=read('reports/assets/T10-spike/40-S3-after-pending-r2.json');
  const live={session_id:a.s.id,started_at:p.turns[0].startedAt,ended_at:p.turns[0].endedAt,model_requests:null,recorded_model_calls:4,tokens:p.usage.totals,costs:[{currency:'USD',micros:1946}],billing_complete:true,missing_costs:0};
  a.progress('running',a.s.nodes,{...live,session_id:'other-review'});
  assert.match(a.runPage(),/模型请求 未提供 · token 未提供 · 费用 未提供/);
  a.progress('running',a.s.nodes,live);
  assert.match(a.runPage(),/模型请求 未提供（已记费 4 次） · token 75,224 · 费用 USD 0.00195/);
  assert.match(a.runPage(),/AGH估算，非实付；0不表示免费/);
  const run=read('runs/gz-t14-changzhou-005/run.json'), archived={...run,session_id:a.s.id};
  a.setResponse(async () => ({...certificate(false),usage_by_session:{[a.s.id]:archived}}));
  a.s.nodes=[...a.s.nodes,exported]; a.s.op='idle'; await a.finishSession(a.s);
  assert.match(a.runPage(),/用时 82.9 秒 · 模型请求 16 · token 334,544 · 费用 未提供/);
  assert.match(a.runPage(),/完整会话归档汇总/);
  a.progress('running',a.s.nodes,live);
  assert.equal(a.s.archivedUsage,null); assert.match(a.runPage(),/token 75,224/);
});

test.skip('replay totals stay scoped to the selected complete session and never substitute design statistics for review',async () => {
  const a=await app(), design=read('runs/gz-t14-changzhou-005/run.json');
  const review=read('runs/gz-t14-changzhou-005/'+design.review_capture+'/run.json');
  a.state.replayRun={run:design,usage_by_session:{[design.session]:{...design,session_id:design.session},[review.session]:{...review,session_id:review.session}}};
  assert.match(a.replayUsage(design.session),/模型请求 16 · token 334,544/);
  assert.match(a.replayUsage(review.session),/模型请求 5 · token 100,352/);
  assert.match(a.replayUsage(review.session),/完整会话归档汇总（非游标统计）/);
  assert.match(a.replayUsage('unrecorded'),/模型请求 未提供 · token 未提供 · 费用 未提供/);
  a.state.replayRun.usage_by_session[review.session]={...design,session_id:design.session};
  assert.match(a.replayUsage(review.session),/模型请求 未提供 · token 未提供 · 费用 未提供/,'a mismatched map value must not leak design totals');
  a.state.replayRun={run:design,usage:null,usage_by_session:{}};
  assert.match(a.replayUsage(design.session),/模型请求 未提供 · token 未提供 · 费用 未提供/,'an API-rejected association must not fall back to metadata');
});

test('unavailable exported usage replaces live totals with unknown rather than retaining a live estimate',async () => {
  const a=await app(); a.s.usage={session_id:a.s.id,model_requests:20};
  a.setResponse(async () => ({...certificate(false),usage:null,usage_by_session:{}}));
  await a.finishSession(a.s,true);
  assert.match(a.runPage(),/模型请求 未提供 · token 未提供 · 费用 未提供/);
  assert.match(a.runPage(),/完整会话归档汇总/);
});

test('a late review archive cannot replace the resumed design session live usage',async () => {
  const a=await app(); let resolve;
  const reviewer={...a.s,id:'independent-review',review:true,nodes:[{kind:'tool',name:'gz_record_review',status:'completed',result:'{"ok":true,"file":"review.json"}'}]};
  a.state.sessions.set(reviewer.id,reviewer);
  a.s.reviewSession=reviewer.id;
  a.setResponse(() => new Promise(done => {resolve=done;}));
  const pending=a.finishSession(reviewer);
  a.progress('running',a.s.nodes,{session_id:a.s.id,model_requests:null,recorded_model_calls:2});
  resolve({...certificate(false),usage_by_session:{[a.s.id]:{session_id:a.s.id,model_requests:16},[reviewer.id]:{session_id:reviewer.id,model_requests:5}}});
  await pending;
  assert.equal(a.s.archivedUsage,null);
  assert.equal(reviewer.archivedUsage,undefined);
  assert.match(a.runPage(),/模型请求 未提供（已记费 2 次）/);
});


test('rendered numbers are rounded by unit and keep raw values in hover text',async () => {
  const a=await app();
  const result={version:3,metrics:{dc_kw:123.45,yield_kwh:{p50:258175.3483},economics:{payback_years:4.1566,irr_pct:12.345,capex_cny:50000}},
    versions:[{version:3,reason:'调整排距',statistics:{row_spacing_m:4.166027133447441}}]};
  const html=a.resultPanel(result);
  for (const [raw,display] of [[123.45,'123.5'],[258175.3483,'258,175'],[4.1566,'4.16'],[12.345,'12.3'],[4.166027133447441,'4.17']]) {
    assert.ok(html.includes('原值 '+raw+'"'));
    assert.ok(html.includes('>'+display+'</span>'));
  }
  const markup=a.stepsMarkup(computeSteps([
    {kind:'tool',name:'gz_fetch_weather',status:'completed',result:JSON.stringify({annual_ghi_kwh_m2:1359.53341,cache_hit:true})},
    {kind:'tool',name:'gz_set_requirements',status:'completed',result:JSON.stringify({contradictions:[]})}
  ],{op:'idle'}));
  assert.match(markup,/>1,360<\/span>/);
  assert.match(markup,/原值 true"[^>]*>是<\/span>/);
  assert.match(markup,/原值 \[\]"[^>]*>无<\/span>/);
});

test('settings describe empirical Pro and Flash costs and forward the effective theme',async () => {
  const a=await app();
  a.bridge.models=[{id:'deepseek-v4-pro',label:'Pro'},{id:'deepseek-flash',label:'Flash'}];
  a.settings();
  const settings=a.elements.get('settings-content').innerHTML;
  assert.match(settings,/Pro 每次约 0.1–0.3 元，Flash 约 0.03 元/);
  assert.match(settings,/DeepSeek 实际运行经验/);
  assert.match(settings,/id="review-model"/);
  assert.match(settings,/并非收费表/);
  a.state.theme='dark';
  a.theme();
  assert.equal(a.bridge.theme,'dark');
  a.state.theme='system';
  a.theme();
  assert.equal(a.bridge.theme,'light');
});


test('rule hover and yield chain values retain their exact original precision',async () => {
  const a=await app();
  a.state.resultTab='规则';
  const html=a.resultPanel({version:3,rules:[{id:'G1',status:'pass',value:4.166027133447441,limit:4.165}],
    crosscheck:{specific_yield_kwh_kwp:{a:1359.53341,b:1357.7}}});
  assert.ok(html.includes('&quot;value&quot;:4.166027133447441,&quot;limit&quot;:4.165'));
  assert.ok(html.includes('原值 {&quot;a&quot;:1359.53341,&quot;b&quot;:1357.7}'));
  assert.ok(html.includes('>a：1,360；b：1,358</span>'));
});

test('unconnected start preserves the task and form route, and chat ignores hidden reviewer settings',async () => {
  const a=await app(); a.state.form={id:'offline',template:'roof',text:'6年回本',review:true,keep:[]};
  a.state.route='form'; a.state.brief='saved-task';
  a.state.roofs=[{id:'roof',geometry:read('data/demo/projects/changzhou-demo/project.json').roof}];
  await assert.rejects(a.start(),/正在连接 AGH/);
  assert.equal(a.state.brief,'saved-task'); assert.equal(a.state.route,'form');
  assert.equal(a.bridge.logs.length,0);
  assert.match(a.formPage(),/data-action="start" disabled/);
  a.state.mode='chat'; a.bridge.ready=true; a.state.designModel={id:'designer'}; a.state.reviewModel=null;
  a.state.sessions.clear();
  const before=a.requests.length;
  await a.start();
  assert.equal(a.requests.slice(before).some(r=>r.path==='/api/brief'),false);
  assert.equal(a.bridge.logs.at(-1).message.brief,null);
  assert.match(a.formPage(),/需求请在右侧 AGH 里直接说/);
  assert.doesNotMatch(a.formPage(),/data-field="(?:payback|budget|capex|text|maxRounds)"/);
});

const recoveryFixtures=[
  {tool:'gz_analyze',via:'timeout',label:'重新申请',banner:'综合分析的审批 60 秒没点，AGH 自动拒绝了。',
    text:'刚才gz_analyze的审批超时了。请按原参数重新调用它，我会马上批准；然后按一键模式继续，直到申请导出。'},
  ...['timeout','sync','callback'].map(via=>({tool:'gz_export',via,label:'重新申请导出',
    banner:via==='timeout' ? '导出没有批准（超时）。' : '导出审批没通过。',text:'请重新申请导出版本 v2，我会点「仅允许这次」。'}))
];
for (const fixture of recoveryFixtures) test('recovery sends exact same-design followup once for '+fixture.tool+'/'+fixture.via,async () => {
  const a=await app();
  a.s.nodes=[{kind:'tool',name:fixture.tool,seq:1,args_json:{version:2},status:'failed'},
    {kind:'approval',tool:fixture.tool,seq:2,verdict:'rejected',via:fixture.via,args_json:{version:2}}];
  a.s.op='idle'; a.s.verification=null;
  assert.ok(a.runPage().includes(fixture.banner));
  assert.ok(a.runPage().includes(fixture.label));
  await Promise.all([a.click({recovery:'0'}),a.click({recovery:'0'})]);
  assert.deepEqual(a.bridge.logs.map(r=>r.message),[{type:'gz.followup',session_id:a.s.id,text:fixture.text}]);
  assert.equal(a.s.verification,null); assert.equal(a.s.turnStart,2);
});

test('stopped, compare failure and ordinary idle recovery sends each exact fixed sentence',async () => {
  const a=await app(), continuation='继续一键模式，从上一步接着做，不要重复已完成的步骤，直到申请导出。';
  for (const fixture of [{stopped:true,text:continuation},{text:continuation},
    {error:'算不出可用方案',text:'请按原参数重新调用三方案，然后继续。'},
    {error:'Request timed out',index:'1',text:'三方案没做完，跳过三方案，用最后通过的版本继续完成复核、审核和导出。'}]) {
    a.s.nodes=fixture.error?[{kind:'tool',name:'gz_compare_options',status:'failed',
      result_json:{ok:false,message_zh:fixture.error}}]:[{kind:'text',text:'还需要继续完成'}];
    a.s.op='idle'; a.s.recovering=false; a.s.userStopped=fixture.stopped; a.s.turnStart=0;
    const markup=a.runPage();
    assert.match(markup,fixture.stopped?/你停止了这次运行/:fixture.error?/三方案没算出来/:/Agent 停下了/);
    await a.click({recovery:fixture.index??'0'});
    assert.equal(a.bridge.logs.at(-1).message.text,fixture.text);
  }
});

for (const reason of ['user cancel','Agent stopped','step limit']) {
  test('idle pending comparison resumes the original job after '+reason,async () => {
    const a=await app(), args={project_id:a.s.project}, text='继续一键模式，从上一步接着做，不要重复已完成的步骤，直到申请导出。';
    const nodes=[{kind:'tool',session:a.s.id,name:'gz_compare_options',seq:1,result_seq:2,tool_use_id:'compare',
      args_json:args,status:'completed',result_json:{ok:true,pending:true,job_id:'original-job',tool:'gz_compare_options'}}];
    if (reason==='Agent stopped') nodes.push({kind:'text',text:'稍后继续取回三方案'});
    a.progress('running',nodes);
    assert.doesNotMatch(a.runPage(),/data-recovery=/);
    if (reason==='user cancel') {
      await a.click({action:'cancel'});
      assert.deepEqual(a.bridge.logs.at(-1).message,{type:'gz.cancel',session_id:a.s.id});
    }
    a.progress('idle',nodes);
    await new Promise(setImmediate);
    const markup=a.runPage();
    assert.match(markup,reason==='user cancel'?/你停止了这次运行。/:/Agent 停下了：/);
    assert.match(markup,/<button[^>]*data-recovery="0"[^>]*>继续完成<\/button>/);
    assert.equal(a.activeComputed().steps[6].state,'running');
    assert.doesNotMatch(markup,/三方案没算出来/);
    await Promise.all([a.click({recovery:'0'}),a.click({recovery:'0'})]);
    assert.deepEqual(a.bridge.logs.map(r=>r.message),[
      ...reason==='user cancel'?[{type:'gz.cancel',session_id:a.s.id}]:[],{type:'gz.followup',session_id:a.s.id,text}]);
    assert.equal(a.state.design,a.s.id);
    assert.equal(a.state.active,a.s.id);
    assert.equal(a.state.sessions.size,1);
    assert.equal(a.s.nodes,nodes);
    assert.equal(resolvedTools(a.s.nodes)[0].pending,true);
    assert.doesNotMatch(a.runPage(),/data-recovery=/);
    const completed={kind:'tool',session:a.s.id,name:'gz_wait',seq:4,result_seq:5,tool_use_id:'retrieve',
      args_json:{job_id:'original-job'},status:'completed',result_json:{ok:true,job_id:'original-job',tool:'gz_compare_options',options:[]}};
    a.progress('running',[...nodes,completed]);
    assert.equal(a.activeComputed().steps[6].state,'completed');
    assert.equal(a.s.nodes.filter(n=>n.name==='gz_compare_options').length,1);
  });
}

for (const active of [null,'unknown-native']) {
  test('production file progress poll renders left pipeline without design identity: '+active,async () => {
    const a=await app({fileProgress:{steps:Array.from({length:10},()=>({status:'completed'}))}});
    a.state.sessions.clear();
    a.state.design=null;
    a.state.active=active;
    a.state.form.id='file-project';
    a.bridge.fallback=true;
    assert.equal(a.activeComputed().steps.filter(s=>s.state==='completed').length,0);
    await a.poll();
    assert.ok(a.requests.some(r=>r.path==='/api/projects/file-project/progress'));
    assert.equal(a.state.design,null);
    assert.equal(a.state.active,'file-progress');
    assert.equal(a.activeComputed().steps.filter(s=>s.state==='completed').length,10);
    const markup=a.elements.get('view').appended.innerHTML;
    assert.match(markup,/10 \/ 10 步骤/);
    assert.match(markup,/文件进度；不代表原生执行顺序已核对/);
    assert.match(markup,/文件进度每秒刷新/);
  });
}

test('file poll during linked review preserves native design left pipeline',async () => {
  const a=await app({fileProgress:{steps:Array.from({length:10},()=>({status:'completed'}))}});
  a.s.nodes=[exported];
  a.s.run.review={enabled:true,mode:'independent'};
  const before=a.activeComputed().steps.map(s=>s.state);
  const reviewer={id:'linked-review',review:true,nodes:[],op:'running',run:a.s.run};
  a.s.reviewSession=reviewer.id;
  a.state.sessions.set(reviewer.id,reviewer);
  a.state.active=reviewer.id;
  a.state.form.id=a.s.project;
  a.bridge.fallback=true;
  await a.poll();
  assert.equal(reviewer.fallback.steps.filter(s=>s.state==='completed').length,10);
  assert.deepEqual(a.activeComputed().steps.slice(0,8).map(s=>s.state),before.slice(0,8));
  assert.equal(a.activeComputed().steps[9].state,before[9]);
  assert.equal(a.state.design,a.s.id);
});

test('review keeps design steps, exposes only linked reviewer and blocks design recovery until native design returns',async () => {
  const a=await app(); a.s.nodes=[exported]; a.s.run.review={enabled:true,model:'agnes-3.0-flash'};
  const before=a.activeComputed().steps.map(s=>s.state);
  const reviewer={id:'linked-review',review:true,project:a.s.project,nodes:[],approvals:[],op:'running',run:a.s.run};
  a.state.sessions.set(reviewer.id,reviewer); a.s.reviewSession=reviewer.id; a.state.active=reviewer.id;
  a.state.sessions.set('unrelated',{...reviewer,id:'unrelated',project:'elsewhere'});
  for (const name of ['gz_project_summary','gz_analyze','gz_crosscheck_yield','gz_record_review']) {
    reviewer.nodes.push({kind:'tool',name,status:'completed',result_json:{ok:true,version:3}});
    const c=a.activeComputed();
    assert.deepEqual(c.steps.slice(0,8).map(s=>s.state),before.slice(0,8));
    assert.equal(c.steps[9].state,before[9]); assert.equal(c.steps[8].children.length,4);
    assert.equal(c.steps[8].children[0],'读项目：完成');
  }
  reviewer.approvals=[{tool:'gz_record_review',pending:true,received_at:Date.now()}];
  a.state.runTab='产物';
  assert.match(a.runPage(),/等你批准/); assert.equal(a.state.runTab,'live');
  await a.click({recovery:'0'}); assert.equal(a.bridge.logs.length,0);
  await a.click({action:'review-session'});
  assert.equal(a.bridge.logs.at(-1).message.session_id,reviewer.id);
  a.s.reviewSession=null;
  assert.doesNotMatch(a.runPage(),/data-action="review-session"/);
});

test('manual recheck never launches review, review retry has two total attempts and failure leaves results available',async () => {
  const a=await app(), model={id:'agnes-3.0-flash'};
  a.s.nodes=[exported]; a.s.run.review={enabled:true,model:model.id}; a.bridge.ready=true; a.bridge.models=[model];
  a.setResponse(async()=>({...certificate(false),review_prompt:'offline-review',
    verification:{passed:false,checks:Array.from({length:4},()=>({passed:true})),review:{requested:true,passed:false}}}));
  await a.click({action:'finish-retry'});
  assert.equal(a.bridge.logs.filter(r=>r.message.type==='gz.start').length,0);
  await a.startReview(a.s);
  assert.match(a.runPage(),/设计已导出。第 9 步：独立审核，约 1 分钟/);
  assert.equal(a.state.reviewCount,1);
  a.bridge.onMessage({type:'gz.error',message:'审核保存被拒绝'},a.bridge.logs.at(-1).request);
  assert.equal(a.state.starting,false);
  assert.equal(a.s.reviewFailure,'审核保存被拒绝');
  assert.match(a.runPage(),/data-action="review-retry"/);
  await a.click({action:'review-retry'});
  a.bridge.onMessage({type:'gz.error',message:'审核保存被拒绝'},a.bridge.logs.at(-1).request);
  assert.equal(a.state.starting,false);
  await a.startReview(a.s);
  assert.equal(a.bridge.logs.filter(r=>r.message.type==='gz.start').length,2);
  assert.equal(a.state.reviewCount,2);
  assert.match(a.runPage(),/审核保存被拒绝/); assert.match(a.runPage(),/重新审核/); assert.match(a.runPage(),/先看结果/);
});

test('records eval isolation, BJT, parent review identity and report actions retain row identity',async () => {
  const a=await app();
  a.state.records=[{run_id:'ordinary',project_id:'normal',started_at:'2026-10-03T14:20:07.725Z',display_version:4},
    {run_id:'eval-1003-b01-E-1',project_id:'evaluation-roof'},
    {run_id:'opaque-review',project_id:'normal',kind:'review',parent_run_id:'ordinary',report:{files:[{name:'x.pdf'}]},can_report:true}];
  let markup=a.recordsPage();
  assert.doesNotMatch(markup,/evaluation-roof/); assert.match(markup,/2026-10-03 22:20/);
  assert.match(markup,/审核·ordinary/); assert.match(markup,/data-open-report="opaque-review"/);
  assert.match(markup,/<button[^>]*data-report="opaque-review"[^>]*>重新生成方案书<\/button>/);
  assert.match(markup,/href="#result\/normal\?run=ordinary"/);
  assert.doesNotMatch(a.newPage(),/evaluation-roof/);
  a.state.filter='evaluation'; markup=a.recordsPage();
  assert.match(markup,/evaluation-roof/); assert.doesNotMatch(markup,/opaque-review|>normal</);
  a.state.final={run_id:'stale'}; await a.click({openReport:'opaque-review'});
  assert.deepEqual(a.requests.at(-1),{path:'/api/open',body:{kind:'report',run_id:'opaque-review'}});
});

test('unexported titles distinguish latest, last passed and empty without export folders',async () => {
  const a=await app();
  for (const [version,passed,label] of [[4,true,'未导出·最后通过v4'],[5,false,'未导出·最新v5'],[null,false,'暂无设计版本']]) {
    const result={project_id:'p',version,display_passed:passed,selected_version:null};
    assert.match(a.resultPage(result),new RegExp(label));
    assert.doesNotMatch(a.resultPage(result),/vnull|data-action="open-exports"/);
  }
});

test('resumed pending export is certified from full-session wait completion owned by new turn',async () => {
  const a=await app(), args={project_id:a.s.project,version:2};
  a.s.nodes=[{kind:'tool',session:a.s.id,name:'gz_export',seq:1,result_seq:2,tool_use_id:'e',args_json:args,status:'completed',
    result_json:{ok:true,pending:true,job_id:'j',tool:'gz_export'}}];
  a.s.turnStart=1;
  a.s.nodes.push({kind:'tool',session:a.s.id,name:'gz_wait',seq:3,tool_use_id:'w',args_json:{job_id:'j'},status:'completed',
    result_json:{ok:true,version:2,job_id:'j',tool:'gz_export'},result_seq:4});
  await a.finishSession(a.s);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,1);
  assert.equal(a.requests.find(r=>r.path==='/api/runs/finish').body.export_version,2);
});

test('design recovery waits for the matching native progress after open navigation',async () => {
  const a=await app(); a.s.nodes=[{kind:'text',text:'停下'}]; a.s.verification=null;
  a.state.active='native-review';
  await a.click({action:'design-session'});
  assert.equal(a.state.active,'native-review'); assert.equal(a.state.navigation,a.s.id);
  await a.click({recovery:'0'});
  assert.equal(a.bridge.logs.filter(r=>r.message.type==='gz.followup').length,0);
  a.progress('idle');
  assert.equal(a.state.navigation,null); assert.equal(a.state.active,a.s.id);
  await a.click({recovery:'0'});
  assert.equal(a.bridge.logs.filter(r=>r.message.type==='gz.followup').length,1);
});

test('automatic review follows a fresh export even when ordinary stop also requires forced archiving',async () => {
  const a=await app(), model={id:'agnes-3.0-flash'};
  a.bridge.ready=true; a.bridge.models=[model]; a.s.run.review={enabled:true,model:model.id};
  a.s.nodes=[exported,{kind:'text',text:'已经完成'}];
  a.setResponse(async()=>({...certificate(false),review_prompt:'review',
    verification:{checks:Array.from({length:4},()=>({passed:true})),review:{requested:true,passed:false}}}));
  await a.finishSession(a.s,true,true);
  assert.equal(a.bridge.logs.filter(r=>r.message.type==='gz.start').length,1);
});

test('a prior design finish response cannot overwrite a newly started design with the same generation',async () => {
  const a=await app(); let resolve;
  a.s.nodes=[exported];
  a.setResponse(()=>new Promise(done=>{resolve=done;}));
  const pending=a.finishSession(a.s);
  const next={id:'new-design',project:'new-project',nodes:[],approvals:[],op:'running',run:{review:{enabled:false}}};
  a.state.sessions.set(next.id,next); a.state.design=a.state.active=next.id; a.state.final=null;
  resolve(certificate(true)); await pending;
  assert.equal(a.state.final,null); assert.equal(next.verification,undefined);
  assert.equal(a.bridge.logs.length,0);
});

function linkedReviewer(a,id='review-old',op='idle') {
  const reviewer={id,review:true,project:a.s.project,run:a.s.run,op,approvals:[],nodes:[{
    kind:'tool',name:'gz_record_review',status:'completed',result_json:{ok:true,file:id+'.json',verdict:'approve'}
  }]};
  a.state.sessions.set(id,reviewer);
  a.s.reviewSession=id;
  return reviewer;
}

test('new reviewer ignores inbox-only idle until actual running and archives completed evidence once',async()=>{
  const a=await app(), model={id:'agnes-3.0-flash'};
  a.s.nodes=[exported]; a.s.run.review={enabled:true,model:model.id};
  a.bridge.ready=true; a.bridge.models=[model];
  a.state.final={...certificate(false),review_prompt:'review-fixture'};
  await a.startReview(a.s);
  a.bridge.onMessage({type:'gz.session',session_id:'fresh-review'},a.bridge.logs.at(-1).request);
  const reviewer=a.state.sessions.get('fresh-review'), banner=a.s.reviewBanner;
  const progress=(op,nodes)=>a.bridge.onMessage({type:'gz.progress',session_id:reviewer.id,op,nodes});
  progress('idle',[]);
  await flushRecords();
  assert.equal(a.s.reviewFailure,null);
  assert.equal(a.s.reviewBanner,banner);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,0);
  assert.equal(reviewer.op,'running');
  progress('idle',[]);
  progress('running',[]);
  const nodes=['gz_project_summary','gz_analyze','gz_crosscheck_yield','gz_record_review'].map(name=>({
    kind:'tool',name,status:'completed',result_json:{ok:true,version:3,file:'review.json',verdict:'approve'}
  }));
  progress('running',nodes);
  assert.equal(a.activeComputed().steps[8].children[0],'读项目：完成');
  assert.equal(computeSteps(nodes).steps[1].state,'running','design summary still requires a plan');
  a.setResponse(async()=>({...certificate(true),verification:{checks:[],review:{passed:true}}}));
  progress('idle',nodes);
  await flushRecords();
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,1);
  assert.equal(a.requests.at(-2).body.review_session_id,reviewer.id);
  assert.equal(a.s.verification.review.passed,true);
  assert.equal(a.s.reviewBanner,null);
  progress('idle',nodes);
  await flushRecords();
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,1);
});

for (const terminal of ['empty','failed','text','stopped','unobserved']) test('actual reviewer terminal '+terminal+' still exposes recovery',async()=>{
  const a=await app(), model={id:'agnes-3.0-flash'};
  a.s.nodes=[exported]; a.s.run.review={enabled:true,model:model.id};
  a.bridge.ready=true; a.bridge.models=[model];
  a.state.final={...certificate(false),review_prompt:'review-fixture'};
  await a.startReview(a.s);
  a.bridge.onMessage({type:'gz.session',session_id:'failed-review'},a.bridge.logs.at(-1).request);
  if (terminal==='stopped') await a.click({action:'cancel'});
  if (terminal==='empty') a.bridge.onMessage({type:'gz.progress',session_id:'failed-review',op:'running',nodes:[]});
  const nodes=['empty','stopped','unobserved'].includes(terminal) ? [] : terminal==='text' ? [{kind:'text',text:'审核遇到错误'}] : [
    {kind:'tool',name:'gz_project_summary',status:'failed',result_json:{ok:false,message_zh:'审核遇到错误'}}];
  a.bridge.onMessage({type:'gz.progress',session_id:'failed-review',op:'idle',nodes,started:terminal==='unobserved'});
  await flushRecords();
  assert.ok(a.s.reviewFailure);
  assert.match(a.runPage(),/data-action="review-retry"/);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,1);
});

for (const status of ['failed','running']) test('reviewer summary '+status+' supersedes its earlier success',async()=>{
  const a=await app(), reviewer=linkedReviewer(a,'review-summary','running');
  reviewer.nodes=[{kind:'tool',name:'gz_project_summary',status:'completed',result_json:{ok:true}},
    {kind:'tool',name:'gz_project_summary',status,result_json:status==='failed' ? {ok:false} : null}];
  assert.equal(a.activeComputed().steps[8].children[0],status==='failed' ? '读项目：有问题' : '读项目：进行中');
});

test('an old reviewer cannot archive while the linked new reviewer is running',async () => {
  const a=await app(), old=linkedReviewer(a);
  const current=linkedReviewer(a,'review-new','running');
  a.state.active=current.id;
  await a.finishSession(old);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,0);
  assert.equal(a.s.reviewSession,current.id);
  assert.equal(a.state.active,current.id);
  assert.equal(a.bridge.logs.length,0);
});

test('a late review response is isolated as soon as retry starts before gz.session',async () => {
  const a=await app(), old=linkedReviewer(a), model={id:'agnes-3.0-flash'};
  a.s.nodes=[exported];
  a.s.run.review={enabled:true,model:model.id};
  a.state.final={...certificate(false),review_prompt:'review-new'};
  a.state.reviewCount=1;
  a.bridge.ready=true;
  a.bridge.models=[model];
  let resolve;
  a.setResponse(()=>new Promise(done=>{resolve=done;}));
  const pending=a.finishSession(old);
  await a.startReview(a.s);
  const currentFinal=a.state.final, banner=a.s.reviewBanner;
  resolve({...certificate(true),verification:{review:{passed:true}}});
  await pending;
  await new Promise(setImmediate);
  assert.equal(a.state.final,currentFinal);
  assert.equal(a.s.reviewBanner,banner);
  assert.equal(a.s.reviewSession,null);
  assert.equal(a.bridge.logs.filter(r=>r.message.type==='gz.open').length,0);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,1);
});

test('a review archive error after design resume cannot restore failure or retry UI',async () => {
  const a=await app(), old=linkedReviewer(a);
  let reject;
  a.setResponse(()=>new Promise((_,fail)=>{reject=fail;}));
  const pending=a.finishSession(old);
  a.resumeSession(a.s);
  reject(new Error('stale archive failure'));
  const error=await pending.catch(error=>error);
  assert.equal(a.s.reviewBanner,null);
  assert.equal(a.s.reviewFailure,null);
  assert.equal(a.s.reviewSession,null);
  assert.equal(a.state.final,null);
  assert.equal(old.finishError,undefined);
  assert.doesNotMatch(a.runPage(),/stale archive failure|data-action="review-retry"/);
  assert.equal(error,undefined);
});

test('a stale review request releases archiving for the current idle reviewer',async () => {
  const a=await app(), old=linkedReviewer(a);
  let resolve;
  a.setResponse(()=>new Promise(done=>{resolve=done;}));
  const pending=a.finishSession(old);
  const current=linkedReviewer(a,'review-new');
  await a.finishSession(current);
  const final={...certificate(true),verification:{review:{passed:true}}};
  a.setResponse(async()=>final);
  resolve(final);
  await pending;
  await new Promise(setImmediate);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,2);
  assert.equal(a.s.reviewSession,current.id);
  assert.equal(current.verification,final.verification);
  assert.equal(old.verification,undefined);
  assert.equal(a.bridge.logs.filter(r=>r.message.type==='gz.open').length,1);
});

test('a pending old review cannot overwrite a newly linked running reviewer',async () => {
  const a=await app(), old=linkedReviewer(a);
  let resolve;
  a.setResponse(()=>new Promise(done=>{resolve=done;}));
  const pending=a.finishSession(old);
  const current=linkedReviewer(a,'review-new','running');
  a.state.active=current.id;
  a.s.reviewBanner='new review running';
  const verification=a.s.verification;
  resolve({...certificate(true),verification:{review:{passed:true}}});
  await pending;
  assert.equal(a.s.reviewSession,current.id);
  assert.equal(a.s.verification,verification);
  assert.equal(a.s.reviewBanner,'new review running');
  assert.equal(a.state.active,current.id);
  assert.equal(current.verification,undefined);
  assert.equal(a.bridge.logs.length,0);
});

test('current review archive failure can retry and then return the passed design',async () => {
  const a=await app(), reviewer=linkedReviewer(a);
  a.setResponse(async()=>{throw new Error('current archive failure');});
  await assert.rejects(a.finishSession(reviewer),/current archive failure/);
  assert.equal(reviewer.finishKey,'');
  assert.equal(reviewer.finishError,'current archive failure');
  assert.match(a.runPage(),/current archive failure/);
  assert.match(a.runPage(),/重新审核/);
  const final={...certificate(true),verification:{review:{passed:true}}};
  a.setResponse(async()=>final);
  await a.finishSession(reviewer);
  assert.equal(a.s.verification,final.verification);
  assert.equal(reviewer.finishError,null);
  assert.equal(a.s.reviewBanner,null);
  assert.deepEqual(a.bridge.logs.at(-1).message,{type:'gz.open',session_id:a.s.id});
});

test('late review error after retry starts cannot replace its banner or clear startup',async () => {
  const a=await app(), old=linkedReviewer(a), model={id:'agnes-3.0-flash'};
  a.s.run.review={enabled:true,model:model.id};
  a.state.final={...certificate(false),review_prompt:'review-new'};
  a.state.reviewCount=1;
  a.bridge.ready=true;
  a.bridge.models=[model];
  let reject;
  a.setResponse(()=>new Promise((_,fail)=>{reject=fail;}));
  const pending=a.guarded(()=>a.finishSession(old))();
  await new Promise(setImmediate);
  a.elements.set('notice',{textContent:'current notice'});
  await a.startReview(a.s);
  const request=a.bridge.logs.at(-1).request, banner=a.s.reviewBanner;
  reject(new Error('old error'));
  await pending;
  assert.equal(a.s.reviewBanner,banner);
  assert.equal(a.s.reviewFailure,null);
  assert.equal(a.state.starting,true);
  assert.equal(a.elements.get('notice').textContent,'current notice');
  a.bridge.onMessage({type:'gz.session',session_id:'review-new'},request);
  assert.equal(a.s.reviewSession,'review-new');
  assert.equal(a.state.active,'review-new');
  assert.equal(a.state.starting,false);
});

test('review startup callbacks from a resumed design cannot restore an old session or error',async () => {
  const a=await app(), model={id:'agnes-3.0-flash'};
  a.s.run.review={enabled:true,model:model.id};
  a.state.final={...certificate(false),review_prompt:'review-old'};
  a.bridge.ready=true;
  a.bridge.models=[model];
  await a.startReview(a.s);
  const request=a.bridge.logs.at(-1).request;
  a.resumeSession(a.s);
  assert.equal(a.state.starting,false);
  a.bridge.onMessage({type:'gz.session',session_id:'stale-review'},request);
  a.bridge.onMessage({type:'gz.error',message:'stale startup'},request);
  assert.equal(a.s.reviewSession,null);
  assert.equal(a.s.reviewBanner,null);
  assert.equal(a.state.active,a.s.id);
  assert.equal(a.state.sessions.has('stale-review'),false);
  a.s.op='idle';
  a.state.mode='chat';
  a.state.designModel=model;
  await a.start();
  const next=a.bridge.logs.at(-1).request;
  assert.equal(next.review,false);
  assert.equal(a.state.starting,true);
  a.bridge.onMessage({type:'gz.session',session_id:'next-design'},next);
  assert.equal(a.state.starting,false);
  await assert.rejects(a.start(),/请先停止当前设计/);
});

for (const nextKind of ['design','review']) test('stale review callbacks cannot unlock a newer '+nextKind+' startup',async () => {
  const a=await app(), model={id:'agnes-3.0-flash'};
  a.s.run.review={enabled:true,model:model.id};
  a.state.final={...certificate(false),review_prompt:'review-old'};
  a.bridge.ready=true;
  a.bridge.models=[model];
  await a.startReview(a.s);
  const stale=a.bridge.logs.at(-1).request;
  a.resumeSession(a.s);
  a.s.op='idle';
  a.state.final={...certificate(false),review_prompt:'review-new'};
  if (nextKind==='design') {
    a.state.mode='chat';
    a.state.designModel=model;
    await a.start();
  } else await a.startReview(a.s);
  const current=a.bridge.logs.at(-1).request;
  const banner=a.s.reviewBanner;
  assert.notEqual(current,stale);
  a.bridge.onMessage({type:'gz.session',session_id:'stale-review'},stale);
  a.bridge.onMessage({type:'gz.error',message:'stale startup'},stale);
  a.bridge.onMessage({type:'gz.error',message:'late followup'});
  assert.equal(a.state.starting,true);
  assert.equal(a.s.reviewFailure,null);
  assert.equal(a.s.reviewBanner,banner);
  a.bridge.onMessage({type:'gz.error',message:'late open'},{project:a.s.project});
  assert.equal(a.state.starting,true);
  assert.equal(a.s.reviewFailure,null);
  assert.equal(a.s.reviewBanner,banner);
  assert.equal(a.state.sessions.has('stale-review'),false);
  await assert.rejects(a.start(),/请先停止当前设计/);
  const count=a.bridge.logs.length;
  await a.startReview(a.s);
  assert.equal(a.bridge.logs.length,count);
  a.bridge.onMessage({type:'gz.session',session_id:'current-'+nextKind},current);
  assert.equal(a.state.starting,false);
  assert.equal(a.state.active,'current-'+nextKind);
  if (nextKind==='review') {
    assert.equal(a.state.sessions.get(a.s.reviewSession).op,'running');
    a.bridge.onMessage({type:'gz.error',message:'late running followup'});
    a.bridge.onMessage({type:'gz.error',message:'late running open'},{project:a.s.project});
    assert.equal(a.s.reviewFailure,null);
    assert.equal(a.s.reviewBanner,banner);
    assert.match(a.runPage(),/设计已导出。第 9 步：独立审核，约 1 分钟/);
    assert.doesNotMatch(a.runPage(),/data-action="review-retry"/);
    assert.equal(a.bridge.logs.length,count);
  }
  await assert.rejects(a.start(),/请先停止当前设计/);
});

test('detached reviewer idle ends its lifecycle without changing current UI or archiving',async () => {
  const a=await app(), old=linkedReviewer(a,'old-running','running');
  a.resumeSession(a.s);
  const current=linkedReviewer(a,'current-running','running');
  a.state.active=current.id;
  a.s.reviewBanner='current banner';
  a.s.verification={passed:false};
  a.state.final={run_id:'current-archive'};
  a.state.route='run';
  const snapshot=JSON.stringify({final:a.state.final,verification:a.s.verification,records:a.state.records});
  const ui=a.elements.get('view').innerHTML;
  a.bridge.onMessage({type:'gz.progress',session_id:old.id,op:'idle',nodes:[]});
  await new Promise(setImmediate);
  assert.equal(old.op,'idle');
  assert.equal(a.state.active,current.id);
  assert.equal(a.s.reviewSession,current.id);
  assert.equal(a.s.reviewBanner,'current banner');
  assert.equal(a.elements.get('view').innerHTML,ui);
  assert.equal(JSON.stringify({final:a.state.final,verification:a.s.verification,records:a.state.records}),snapshot);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,0);
  assert.equal(a.bridge.logs.length,0);
  await assert.rejects(a.start(),/请先停止当前设计/);
  a.s.op=current.op='idle';
  a.state.mode='chat';
  a.state.designModel={id:'designer'};
  a.bridge.ready=true;
  await a.start();
  assert.equal(a.bridge.logs.at(-1).request.review,false);
});

test('explicit unexported v1 and v3 titles describe the chosen version',async () => {
  const a=await app();
  a.state.resultExplicit=true;
  for (const version of [1,3]) {
    for (const display_passed of [false,true]) {
      const result={project_id:'p',version,display_passed,selected_version:null,versions:[{version:1},{version:3}]};
      assert.match(a.resultTitle(result),new RegExp('未导出·查看版本 v'+version));
      assert.doesNotMatch(a.resultTitle(result),/最后通过|最新/);
    }
  }
});


test.skip('idle reviewer stays neutral throughout three-second finish and goes directly to 10/10',async()=>{
  const a=await app(), base='runs/gz-t14-changzhou-003/', meta=read(base+'run.json');
  a.s.nodes=read(base+meta.capture+'/timeline.json').nodes;
  a.s.verification=null; a.s.run={review:{enabled:true}};
  const reviewNodes=read(base+meta.review_capture+'/timeline.json').nodes;
  const record=data.toolResult(reviewNodes,'gz_record_review');
  const saved=read(base+meta.review_capture+'/project/reviews/'+record.file.split('/').at(-1));
  const reviewer={id:meta.review_session_id,review:true,op:'running',nodes:reviewNodes,run:a.s.run,approvals:[]};
  a.state.sessions.set(reviewer.id,reviewer); a.s.reviewSession=reviewer.id;
  const final={verification:read(base+'verification.json'),result:{version:12,selected_version:12,
    review_files:{[record.file.split('/').at(-1)]:saved}}};
  a.setResponse(async()=>{await new Promise(resolve=>setTimeout(resolve,3000));return final;});
  const progress=()=>a.bridge.onMessage({type:'gz.progress',session_id:reviewer.id,op:'idle',nodes:reviewNodes});
  progress();
  for (let i=0;i<6;i++) {
    await new Promise(resolve=>setTimeout(resolve,400));
    progress();
    assert.match(a.runPage(),/审核员已结束，正在核对审核记录/);
    assert.doesNotMatch(a.runPage(),/审核未通过|重新审核|独立审核停下了/);
    await a.click({action:'review-retry'});
    assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,1);
    assert.equal(a.bridge.logs.filter(r=>r.message.type==='gz.start').length,0);
  }
  await new Promise(resolve=>setTimeout(resolve,800));
  assert.equal(a.activeComputed().steps.filter(s=>s.state==='completed').length,10);
  assert.doesNotMatch(a.runPage(),/审核未通过|重新审核/);
});

test('export shows review preparation before archive wait starts',async()=>{
  const a=await app(); let resolve;
  a.s.nodes=[exported]; a.s.verification=null; a.s.run.review={enabled:true};
  a.setResponse(()=>new Promise(done=>{resolve=done;}));
  const pending=a.finishSession(a.s);
  assert.match(a.runPage(),/准备独立审核/);
  assert.match(a.runPage(),/设计已导出。第 9 步：独立审核/);
  assert.doesNotMatch(a.runPage(),/已停下|重新审核/);
  resolve(certificate(false));await pending;
});

test('second same-roof entry without reselecting replaces issued ID with minute suffix',async()=>{
  const a=await app(), project=read('data/demo/projects/changzhou-demo/project.json');
  a.state.roofs=[{id:'changzhou-demo',name:project.name,geometry:project.roof}];
  a.selectRoof('changzhou-demo');
  const original=a.state.form.id;
  a.s.op='idle';a.state.designModel={id:'deepseek-v4-pro'};a.state.form.review=false;a.bridge.ready=true;
  await a.start();
  a.state.starting=false;
  a.location.hash='#new';await a.render();
  a.location.hash='#form';await a.render();
  assert.equal(a.state.form.id,original+'-2');
  assert.equal(a.state.form.template,'changzhou-demo');
  await a.start();a.state.starting=false;
  a.location.hash='#new';await a.render();a.location.hash='#form';await a.render();
  assert.equal(a.state.form.id,original+'-3');
});

test('existing disk ID changes and late concurrent form responses cannot overwrite a newer selection',async()=>{
  const deferred=[];
  const a=await app({existsResponse:()=>new Promise(resolve=>deferred.push(resolve))});
  const project=read('data/demo/projects/changzhou-demo/project.json');
  a.state.roofs=['roof-a','roof-b'].map(id=>({id,name:id,geometry:project.roof}));
  a.selectRoof('roof-a');const first=a.state.form.id;
  a.location.hash='#form';const old=a.render();await flushRecords();
  a.selectRoof('roof-b');const current=a.state.form.id;
  const newer=a.render();await flushRecords();
  deferred[1]({exists:false});await newer;
  deferred[0]({exists:false});await old;
  assert.equal(a.state.form.id,current);assert.notEqual(a.state.form.id,first);
  a.location.hash='#new';await a.render();
  a.location.hash='#form';const disk=a.render();await flushRecords();
  deferred[2]({exists:true});await flushRecords();
  deferred[3]({exists:true});await flushRecords();
  deferred[4]({exists:false});await disk;
  assert.equal(a.state.form.id,current+'-2');
});

test('unrecognized numeric snippets use amber wording in rendered form',async()=>{
  const a=await app();a.state.roofs=[{id:'roof',name:'roof',geometry:{outline:[]}}];
  a.selectRoof('roof');a.state.form.text='每天3人值班';a.state.mode='auto';
  const inference=data.inferRequirements(a.state.form.text,a.state.form,{});
  a.state.recognized=inference.summary;a.state.unrecognized=Boolean(inference.unknown);
  assert.match(a.formPage(),/class="recognition-warning">这几处没认出来：每天3人值班，请填到下面的栏里/);
});

test('production input handler renders correct Chinese tens and original unsupported-token warnings',async()=>{
  const a=await app();
  a.state.roofs=[{id:'roof',name:'roof',geometry:{outline:[]}}];
  a.state.mode='auto';
  for (const [text,key,value] of [['预算十五万','budget',15],['预算三十万','budget',30],['十二年回本','payback',12]]) {
    a.selectRoof('roof');
    a.input('text',text);
    assert.equal(a.state.form[key],value);
    assert.match(a.formPage(),new RegExp(`data-field="${key}"[^>]*value="${value}"`));
    assert.equal(a.state.unrecognized,false);
  }
  for (const text of ['预算 百万','十二点五 年回本','一万5 米检修通道','预算 一万五 元','廿年回本']) {
    a.selectRoof('roof');
    a.input('text',text);
    assert.equal(a.state.form.budget ?? '','');
    assert.equal(a.state.form.payback ?? '','');
    assert.equal(a.state.form.walkway ?? '','');
    assert.equal(a.state.unrecognized,true);
    assert.ok(a.formPage().includes(`class="recognition-warning">这几处没认出来：${text}，请填到下面的栏里`));
    assert.equal(a.elements.get('recognized').textContent,`这几处没认出来：${text}，请填到下面的栏里`);
  }
});


test('authoritative review failure survives repeated idle progress without returning to neutral',async()=>{
  const a=await app(), reviewer=linkedReviewer(a,'failed-repeat');
  a.setResponse(async()=>({...certificate(false),verification:{review:{passed:false}}}));
  a.bridge.onMessage({type:'gz.progress',session_id:reviewer.id,op:'idle',nodes:reviewer.nodes});
  await flushRecords();
  assert.match(a.runPage(),/重新审核/);
  a.bridge.onMessage({type:'gz.progress',session_id:reviewer.id,op:'idle',nodes:reviewer.nodes});
  await flushRecords();
  assert.match(a.runPage(),/重新审核/);
  assert.doesNotMatch(a.runPage(),/审核员已结束，正在核对审核记录/);
  assert.equal(a.requests.filter(r=>r.path==='/api/runs/finish').length,1);
});


test('installed setup never takes over the page; key bar shows progress, start waits, polls keep the active form',async () => {
  const installation={installed:true,id:'a'.repeat(64),root:'C:\\安装',build:'build'};
  let status={installation,required:true,ready:false,phase:'configuring',operation_id:'c'.repeat(32),workspace_id:'b'.repeat(64),
    busy:true,steps:Array.from({length:7},(_,i) => ({number:i+1,state:'waiting',reason:'正在准备',action:''}))};
  const a=await app({hash:'#new',setupResponse:() => status});
  await a.render();
  assert.equal(a.state.route,'new');
  const home=a.elements.get('view').innerHTML;
  assert.match(home,/data-key="agnes"/);
  assert.match(home,/data-key="deepseek"/);
  assert.match(home,/type="password"/);
  assert.match(home,/正在准备设计工具/);
  assert.doesNotMatch(home,/开始配置|实例目录|工作区目录|Python/);
  assert.equal(a.requests.some(row => row.path==='/api/setup/configure'),false);
  a.location.hash='#setup';
  await a.render();
  assert.equal(a.location.hash,'#new');
  a.state.roofs=[{id:'roof',name:'roof',geometry:{outline:[]}}];
  a.state.form={id:'installed-form',template:'roof',budget:'12',review:true};
  a.bridge.ready=true;
  a.state.designModel=a.state.reviewModel={id:'agnes-3.0-flash',route:'r'};
  await assert.rejects(a.start(),/正在准备设计工具/);
  a.location.hash='#form';
  await a.render();
  const form=a.state.form, sessions=a.state.sessions, html=a.elements.get('view').innerHTML;
  status={...status,busy:false,phase:'waiting_models'};
  await a.setup.poll();
  assert.equal(a.location.hash,'#form');
  assert.equal(a.elements.get('view').innerHTML,html);
  assert.equal(a.state.form,form);
  assert.equal(a.state.sessions,sessions);
});

test('home key bar sends the typed key once to the plugin, clears the box and reports the result',async () => {
  const a=await app({hash:'#new'});
  a.bridge.ready=true;
  a.bridge.refresh=() => {a.refreshed=(a.refreshed ?? 0)+1;};
  const box={value:'  placeholder-key-for-test  '};
  a.selected.set('[data-key="agnes"]',box);
  await a.click({saveKey:'agnes'});
  const sent=a.bridge.logs.filter(row => row.message.type==='gz.saveKey');
  assert.equal(sent.length,1);
  assert.deepEqual(sent[0].message,{type:'gz.saveKey',provider:'agnes',key:'placeholder-key-for-test'});
  assert.deepEqual(sent[0].request,{keySave:'agnes'});
  assert.equal(box.value,'');
  assert.equal(a.state.keySaving,'agnes');
  a.bridge.onMessage({type:'gz.keySaved',provider:'agnes',model:'agnes-3.0-flash'},{keySave:'agnes'});
  assert.equal(a.state.keySaving,null);
  assert.equal(a.refreshed,1);
  assert.match(a.elements.get('notice').textContent,/Agnes key 已保存/);
  await a.click({saveKey:'deepseek'});
  assert.equal(a.bridge.logs.filter(row => row.message.type==='gz.saveKey').length,1,'empty box sends nothing');
  assert.match(a.elements.get('notice').textContent,/先把 key 粘贴到框里/);
  a.selected.set('[data-key="deepseek"]',{value:'another-placeholder'});
  await a.click({saveKey:'deepseek'});
  a.bridge.onMessage({type:'gz.error',code:'KEY_REJECTED',message:'key 没通过验证'},{keySave:'deepseek'});
  assert.equal(a.state.keySaving,null);
  assert.match(a.elements.get('notice').textContent,/key 没通过验证/);
  assert.equal(a.refreshed,1);
});

test('actual installed setup completion retains verified public design and review display names',async () => {
  const installation={installed:true,id:'a'.repeat(64),root:'C:\\安装',build:'build'};
  const operation_id='c'.repeat(32), workspace_id='b'.repeat(64);
  const status={installation,operation_id,workspace_id,required:true,ready:true,phase:'ready',busy:false,steps:[]};
  const a=await app({setupResponse:() => status});
  await a.setup.poll();
  const models=[{id:'deepseek-v4-pro',route:'selected-design',name:'配置的 DeepSeek 设计'},
    {id:'agnes-3.0-flash',route:'selected-review',name:'配置的 Agnes 审核'},
    {id:'agnes-3.0-flash',route:'other-review',name:'不能显示的同名模型'}];
  const metadata={profile:'local-dev',designConfigured:true,reviewConfigured:true,models,
    design:{id:models[0].id,route:models[0].route},review:{id:models[1].id,route:models[1].route}};
  a.setup.api=async () => status;
  assert.deepEqual(a.bridge.models,[]);
  await a.setup.receive({type:'gz.setup',installation_id:installation.id,operation_id,metadata},
    {setup:true,key:installation.id+':'+operation_id,type:'gz.models'});
  assert.deepEqual(a.bridge.models,models.map(model => ({...model,label:model.name})));
  assert.equal(a.state.designModel.label,models[0].name);
  assert.equal(a.state.reviewModel.label,models[1].name);
  assert.equal(a.state.reviewModel.route,'selected-review');
  a.state.roofs=[{id:'roof',name:'roof',geometry:{outline:[]}}];
  a.state.form.template='roof';
  const markup=a.formPage();
  assert.match(markup,/设计：配置的 DeepSeek 设计/);
  assert.match(markup,/审核：配置的 Agnes 审核/);
  const summary=markup.slice(markup.indexOf('<div class="ready muted"'));
  assert.doesNotMatch(summary.slice(0,summary.indexOf('</div>')),/等待模型清单|未选审核模型|不能显示的同名模型/);
  assert.match(markup,/id="form-design-model"/);
  assert.match(markup,/id="form-review-model"/);
  a.bridge.models=[];
  a.bridge.onMessage({type:'gz.ready'});
  assert.equal(a.state.designModel.label,models[0].name);
  assert.equal(a.state.reviewModel.label,models[1].name);
  assert.equal(a.state.reviewModel.route,'selected-review');
  assert.deepEqual(a.bridge.models,models.map(model => ({...model,label:model.name})));
  a.bridge.ready=true;
  a.s.nodes=[exported];
  a.s.run={review:{enabled:true,mode:'independent',model:'selected-review/agnes-3.0-flash'}};
  a.state.final={review_prompt:'review after configuring keys'};
  await a.startReview(a.s);
  const created=a.bridge.logs.find(row => row.message.type==='gz.start').message;
  assert.equal(created.design_model.route,'selected-review');
  assert.equal(created.design_model.label,models[1].name);
  assert.equal(created.workspace_id,workspace_id);
});

test('installed review started from an ID-only task book finds the configured route (10/4 user run regression)',async () => {
  const installation={installed:true,id:'a'.repeat(64),root:'C:\\安装',build:'build'};
  const status={installation,required:true,ready:true,phase:'ready',operation_id:'b'.repeat(32),workspace_id:'c'.repeat(64),steps:[]};
  const a=await app({setupResponse:() => status});
  await a.setup.poll();
  const agnes={id:'agnes-3.0-flash',route:'account-gz-agnes',label:'Agnes 3.0 Flash'};
  a.bridge.ready=true;
  a.bridge.models=[{id:'deepseek-v4-pro',route:'account-gz-deepseek',label:'DeepSeek'},agnes];
  a.state.reviewModel=agnes;
  a.s.nodes=[exported];
  a.s.run={review:{enabled:true,mode:'independent',model:'agnes-3.0-flash'}};
  a.state.final={review_prompt:'review this installed design'};
  await a.startReview(a.s);
  const created=a.bridge.logs.find(row => row.message.type==='gz.start').message;
  assert.deepEqual(created.design_model,agnes);
  assert.equal(a.s.reviewFailure,null);
});

test('any configured model can design or review; preferences pick them and defaults stay DeepSeek and Agnes',async () => {
  const models=[{id:'gpt-5',route:'account-gz-openai',label:'GPT-5'},{id:'claude-sonnet-5',route:'account-gz-anthropic',label:'Claude'},
    {id:'deepseek-v4-pro',route:'account-gz-deepseek',label:'DeepSeek'},{id:'agnes-3.0-flash',route:'account-gz-agnes',label:'Agnes'}];
  assert.deepEqual(data.modelChoices(models),{design:models[2],review:models[3]});
  assert.deepEqual(data.modelChoices(models,'account-gz-anthropic/claude-sonnet-5','account-gz-openai/gpt-5'),{design:models[1],review:models[0]});
  assert.deepEqual(data.modelChoices(models.slice(0,2)),{design:models[0],review:models[0]});
  assert.deepEqual(data.modelChoices([models[3]]),{design:models[3],review:models[3]});
});

test('installed independent review keeps the qualified route and installation workspace association',async () => {
  const installation={installed:true,id:'a'.repeat(64),root:'C:\\安装',build:'build'};
  const status={installation,required:true,ready:true,phase:'ready',operation_id:'b'.repeat(32),workspace_id:'c'.repeat(64),steps:[]};
  const a=await app({setupResponse:() => status});
  const wrong={id:'agnes-3.0-flash',route:'account-other-route'}, exact={id:'agnes-3.0-flash',route:'account-review-route'};
  a.bridge.ready=true;
  a.bridge.models=[wrong,exact];
  a.s.run={review:{enabled:true,mode:'independent',model:'account-review-route/agnes-3.0-flash'}};
  a.state.final={review_prompt:'review this installed design'};
  await a.startReview(a.s);
  const created=a.bridge.logs.find(row => row.message.type==='gz.start').message;
  assert.equal(created.design_model,exact);
  assert.equal(created.installation_id,installation.id);
  assert.equal(created.workspace_id,status.workspace_id);
});
