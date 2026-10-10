import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createBridge,configuredModels,progressNodes,progressUsage} from '../src/bridge.js';
import {DATA} from '../extensions/main/client/data.js';

const tick = ms => new Promise(resolve => setTimeout(resolve,ms));
test.skip('usage follows the real AGH projection, includes title tokens and deduplicates calls', () => {
  const real = JSON.parse(fs.readFileSync(new URL('../../../reports/assets/T10-spike/40-S3-after-pending-r2.json',import.meta.url),'utf8'));
  const usage = progressUsage({...real,turns:[...real.turns,real.turns[0],{...real.turns[0],inherited:true}]});
  assert.equal(usage.session_id,real.sessionId);
  assert.deepEqual(usage.tokens,real.turns[0].usage.totals);
  assert.deepEqual(usage.costs,[{currency:'USD',micros:1946}]);
  assert.equal(usage.recorded_model_calls,4); assert.equal(usage.model_requests,null);
  assert.equal(usage.billing_complete,true); assert.equal(usage.missing_costs,0);
  assert.equal(usage.started_at,real.turns[0].startedAt); assert.equal(usage.ended_at,real.turns[0].endedAt);
  assert.equal(progressUsage({...real,opState:{}}).ended_at,null);
});
test('usage never transmits credentials, invented numbers or an absent estimate as zero', () => {
  const unsafe = {sessionId:'C:/Users/example',opState:{},turns:[{startedAt:'Bearer example',usage:{billingComplete:true,calls:[
    {id:'known',purpose:'inference',tokens:{input:2,output:3,cacheRead:0,cacheWrite:0,reasoning:1},billing:{source:'estimated',usdMicros:4,apiKey:'must-not-transmit'}},
    {id:'missing',purpose:'inference',tokens:{input:'secret',output:0},billing:null}]}}]};
  const usage = progressUsage(unsafe);
  assert.equal(usage.session_id,null); assert.equal(usage.started_at,null); assert.equal(usage.tokens.input,null);
  assert.equal(usage.billing_complete,false); assert.equal(usage.missing_costs,1);
  assert.deepEqual(usage.costs,[{currency:'USD',micros:4}]);
  assert.ok(!JSON.stringify(usage).includes('secret')); assert.ok(!JSON.stringify(usage).includes('must-not-transmit'));
  assert.equal(progressUsage({turns:[]}),null);
});
const makeStorage = () => {const rows = new Map(); return {getItem:key => rows.get(key) ?? null,setItem:(key,value) => rows.set(key,value),removeItem:key => rows.delete(key),rows};};
function fixture(storage = makeStorage(), initial) {
  let current = initial, receive, sessionKey = 0;
  const messages = [], calls = [], subscriptions = new Set(), switched = new Set(), attributes = new Map();
  const styles = new Map(), priorities = new Map(), classes = new Set(), themeEvents = [], local = makeStorage();
  const root = {
    setAttribute:(name,value) => attributes.set(name,value),
    removeAttribute:name => attributes.delete(name),
    classList:{contains:name => classes.has(name),toggle:(name,on) => on ? classes.add(name) : classes.delete(name)},
    style:{
      getPropertyValue:name => styles.get(name) ?? '',
      getPropertyPriority:name => priorities.get(name) ?? '',
      setProperty:(name,value,priority='') => {styles.set(name,value); priorities.set(name,priority);},
      removeProperty:name => {styles.delete(name); priorities.delete(name);},
    },
  };
  const model = {id:'deepseek-flash',route:'route-design',label:'设计模型',apiKey:'must-never-leave-sdk'};
  const state = {timeline:{opState:null,nodes:[],turns:[]},models:[model],workspaces:[{name:'guangzhu',path:'C:\\Users\\local-user\\projects\\guangzhu',available:true}]};
  const win = {setTimeout,clearTimeout,sessionStorage:storage,parent:{postMessage:(data,origin) => messages.push({data,origin})},
    crypto:{randomUUID:() => '00000000-0000-4000-8000-'+String(++sessionKey).padStart(12,'0')},
    location:{href:'http://127.0.0.1:4177/?skin=guangzhu',assign:url => calls.push(['navigate',url])},
    document:{documentElement:root},localStorage:local,
    StorageEvent:class {constructor(type,fields){this.type=type; Object.assign(this,fields);}},
    dispatchEvent:event => {
      themeEvents.push(event);
      state.repaintTheme?.(event);
    },
    addEventListener:(name,fn) => {assert.equal(name,'message'); receive = fn;},removeEventListener:() => {receive = undefined;}};
  const ctx = {agnes:{apis:async () => ({profile:{models:state.models}}),workspace:{list:async () => ({items:state.workspaces})},
    session:{new:async options => {calls.push(['new',options]); return {id:'session-created',setModel:async value => calls.push(['model',value]),prompt:() => {throw new Error('must use host handle');}};},
      rename:async (...args) => calls.push(['rename',...args]),list:async () => ({items:[{sessionId:'session-existing'}]})}},
    session:{getSnapshot:() => current,handle:initial ? {} : undefined,
      subscribe:fn => {switched.add(fn); return () => switched.delete(fn);},
      projection:{read:async () => ({status:current ? 'available' : 'unavailable',value:current ? state.timeline : undefined}),subscribe:fn => {subscriptions.add(fn); return () => subscriptions.delete(fn);}},
      commands:{prompt:value => {calls.push(['prompt',value]); return Promise.resolve();},cancel:async () => calls.push(['cancel'])}}};
  const bridge = createBridge(ctx,win), send = (type,fields = {},extra = {}) => receive({source:win.parent,origin:DATA.desktopOrigins[0],data:{v:1,type,id:type,...fields},...extra});
  return {ctx,win,state,messages,calls,attributes,storage,bridge,send,styles,classes,themeEvents,local,
    hello:() => send('gz.hello',{app:'guangzhu-desktop'}),
    switchTo(id) {current = id; ctx.session.handle = {}; switched.forEach(fn => fn());},
    update() {subscriptions.forEach(fn => fn());}};
}
const start = {brief:'【光筑任务书 v1】\n完整原文\n<b>&',project_id:'t10-project',workspace:'guangzhu',design_model:{id:'deepseek-flash',route:'route-design'}};

test('park creation reuses its native key and prompt dispatch remains a separate guarded action', async () => {
  const key = 'park-design-' + 'a'.repeat(32);
  const f = fixture();
  await f.hello();
  const binding = f.messages.find(row => row.data.type === 'gz.ready').data.workspace_binding;
  await f.send('gz.start', {...start, brief:null, session_key:key, workspace_binding:binding});
  assert.equal(f.calls.find(row => row[0] === 'new')[1].sessionKey, key);
  assert.equal(f.calls.some(row => row[0] === 'prompt'), false);
  f.switchTo(key);
  await f.send('gz.parkPrompt', {session_id:key, text:'持久派发的完整任务书', workspace_binding:binding});
  assert.deepEqual(f.calls.filter(row => row[0] === 'prompt'), [['prompt', '持久派发的完整任务书']]);
  f.switchTo('ordinary');
  await f.send('gz.parkPrompt', {id:'invalid-park', session_id:'ordinary', text:'拒绝'});
  assert.equal(f.messages.at(-1).data.code, 'INVALID');
  f.bridge.dispose();
});

test('park recovery searches all native list pages and matches the exact session ID', async () => {
  const f = fixture();
  const key = 'park-design-' + 'b'.repeat(32);
  const seen = [];
  const cwd = f.state.workspaces[0].path;
  f.ctx.agnes.session.list = async query => {
    seen.push(query);
    return query.cursor ? {items:[{sessionId:key, cwd}]} : {items:[{sessionId:key + '-other', cwd}], next:'page-two'};
  };
  await f.hello();
  const binding = f.messages.find(row => row.data.type === 'gz.ready').data.workspace_binding;
  await f.send('gz.open', {session_id:key, workspace_binding:binding});
  assert.deepEqual(seen, [{q:{prefix:key, cwd}, limit:500}, {q:{prefix:key, cwd}, limit:500, cursor:'page-two'}]);
  assert.ok(f.calls.some(row => row[0] === 'navigate' && row[1].includes('session=' + key)));
  assert.equal(f.calls.some(row => row[0] === 'new' || row[0] === 'prompt'), false);
  f.bridge.dispose();
});

test('park recovery refuses changed workspaces and wrong cwd rows without leaking paths', async () => {
  const f = fixture();
  const key = 'park-design-' + 'c'.repeat(32);
  await f.hello();
  const binding = f.messages.find(row => row.data.type === 'gz.ready').data.workspace_binding;
  assert.match(binding, /^[a-f0-9]{64}$/);
  f.ctx.agnes.session.list = async () => ({items:[{sessionId:key, cwd:'C:/another-workspace'}]});
  await f.send('gz.open', {session_id:key, workspace_binding:binding});
  assert.equal(f.calls.some(row => row[0] === 'navigate'), false);
  f.state.workspaces[0].path = 'C:/changed-workspace';
  await f.send('gz.open', {id:'changed-open', session_id:key, workspace_binding:binding});
  assert.equal(f.messages.at(-1).data.code, 'WORKSPACE');
  await f.send('gz.start', {...start, id:'changed-create', brief:null, session_key:key, workspace_binding:binding});
  assert.equal(f.messages.at(-1).data.code, 'WORKSPACE');
  assert.equal(f.calls.some(row => row[0] === 'new' || row[0] === 'navigate'), false);
  assert.ok(!JSON.stringify(f.messages).includes('C:/changed-workspace'));
  assert.ok(!JSON.stringify(f.messages).includes('local-user'));
  f.bridge.dispose();
});

test('evaluation title equals the validated project id only for an explicit boolean flag', async () => {
  for (const evaluation of [true,false,undefined,'true']) {
    const f=fixture();
    await f.hello();
    const project_id='eval-1003-r01-C-1';
    await f.send('gz.start',{...start,brief:null,project_id,evaluation});
    assert.deepEqual(f.calls.find(row => row[0]==='rename'),
      ['rename','session-created',evaluation===true ? project_id : '光筑 · '+project_id]);
    assert.equal(f.calls.some(row => row[0]==='prompt'),false);
    f.bridge.dispose();
  }
  const f=fixture();
  await f.hello();
  await f.send('gz.start',{...start,brief:null,project_id:'../eval-1003-r01-C-1',evaluation:true});
  assert.equal(f.calls.some(row => row[0]==='new'),false);
  f.bridge.dispose();
});

test('embedded themes use the shipped skin on cold storage, notify AGH and never navigate', async () => {
  const tokens=JSON.parse(fs.readFileSync(new URL('../extensions/main/skins/agnes.client.json',import.meta.url))).skins[0].tokens;
  const f=fixture();
  f.win.document.documentElement.style.setProperty('--agnes-brand-primary','#prior','important');
  await f.hello();
  for (const [name,modes] of Object.entries(tokens)) assert.equal(f.styles.get(name),modes.light);
  for (const mode of ['dark','light']) {
    await f.send('gz.theme',{id:'theme-'+mode,theme:mode});
    for (const [name,modes] of Object.entries(tokens)) assert.equal(f.styles.get(name),modes[mode]);
    assert.equal(f.styles.get('--agnes-text-emphasis'),mode === 'dark' ? '#e08c55' : '#c87743');
    assert.equal(f.classes.has('dark'),mode==='dark');
    assert.equal(f.local.getItem('agnes-theme'),mode);
    assert.equal(f.themeEvents.at(-1).type,'storage');
    assert.equal(f.themeEvents.at(-1).key,'agnes-theme');
  }
  assert.equal(f.calls.length,0,'theme cannot navigate, prompt, cancel or create sessions');
  f.bridge.dispose();
  assert.deepEqual([...f.styles],[['--agnes-brand-primary','#prior']]);
  assert.equal(f.win.document.documentElement.style.getPropertyPriority('--agnes-brand-primary'),'important');
});

test('theme messages require the trusted parent handshake and a concrete light or dark value', async () => {
  const f=fixture();
  await f.send('gz.theme',{theme:'dark'});
  assert.equal(f.styles.size,0);
  await f.hello();
  const before=JSON.stringify([...f.styles]), count=f.themeEvents.length;
  await f.send('gz.theme',{id:'theme-origin',theme:'dark'},{origin:'http://evil.example'});
  await f.send('gz.theme',{id:'theme-source',theme:'dark'},{source:{}});
  await f.send('gz.theme',{id:'theme-version',theme:'dark',v:2});
  for (const theme of ['system','Dark',null,{}]) await f.send('gz.theme',{id:'bad-'+String(theme),theme});
  assert.equal(JSON.stringify([...f.styles]),before);
  assert.equal(f.themeEvents.length,count);
  f.bridge.dispose();
});

test('blocked preference storage cannot prevent immediate embedded styling', async () => {
  const f=fixture();
  f.win.localStorage.setItem=() => {throw new Error('storage blocked');};
  await f.hello();
  await f.send('gz.theme',{theme:'dark'});
  assert.equal(f.styles.get('--agnes-bg-page'),'#171411');
  assert.equal(f.classes.has('dark'),true);
  f.bridge.dispose();
});

test('disposal repaints a previously cached light skin in the current dark preference', async () => {
  const f=fixture();
  const root=f.win.document.documentElement;
  const cached={light:'#ffffff',dark:'#080808'};
  root.style.setProperty('--agnes-bg-page',cached.light);
  f.state.repaintTheme=event => {
    assert.equal(event.key,'agnes-theme');
    const mode=f.local.getItem('agnes-theme');
    root.classList.toggle('dark',mode==='dark');
    root.style.setProperty('--agnes-bg-page',cached[mode]);
  };
  await f.hello();
  await f.send('gz.theme',{theme:'dark'});
  assert.equal(f.styles.get('--agnes-bg-page'),'#171411','embedded tokens win after the official repaint');
  const before=f.themeEvents.length;
  f.bridge.dispose();
  assert.equal(f.local.getItem('agnes-theme'),'dark');
  assert.equal(f.classes.has('dark'),true);
  assert.equal(f.styles.get('--agnes-bg-page'),cached.dark,'restored light inline values must not override the current theme');
  assert.equal(f.themeEvents.length,before+1);
});

test('bridge ignores untrusted origins/sources, unknown types, wrong version and standalone mode', async () => {
  const f = fixture();
  await f.send('gz.hello',{app:'guangzhu-desktop'},{origin:'http://evil.example'});
  await f.send('gz.hello',{app:'guangzhu-desktop'},{source:{}});
  await f.send('gz.unknown',{});
  await f.send('gz.hello',{app:'guangzhu-desktop',v:2});
  await f.send('gz.start',start);
  assert.equal(f.messages.length,0); assert.equal(f.calls.length,0); assert.equal(f.attributes.size,0);
  f.win.parent = f.win; await f.hello(); assert.equal(f.messages.length,0);
  f.bridge.dispose();
});
test('hello publishes only public model fields and enables embedding; disposal restores it', async () => {
  const f = fixture(); await f.hello();
  const ready = f.messages.find(m => m.data.type === 'gz.ready');
  assert.equal(ready.origin,DATA.desktopOrigins[0]); assert.equal(ready.data.re,'gz.hello');
  assert.deepEqual(ready.data.models,[{id:'deepseek-flash',route:'route-design',label:'设计模型'}]);
  assert.ok(f.attributes.has('data-gz-embedded')); assert.equal(JSON.stringify(f.messages).includes('must-never-leave-sdk'),false);
  f.bridge.dispose(); assert.equal(f.attributes.size,0);
});
test('start creates workspace session, sets primary model/title, navigates, then host sends text once', async () => {
  const f = fixture(); await f.hello(); await f.send('gz.start',start);
  assert.deepEqual(f.calls.slice(0,3),[['new',{cwd:f.state.workspaces[0].path,sessionKey:'00000000-0000-4000-8000-000000000001'}],['model',{slot:'primary',route:'route-design',model:'deepseek-flash'}],['rename','session-created','光筑 · t10-project']]);
  assert.ok(f.calls[3][1].includes('session=session-created')); assert.ok(f.calls[3][1].includes('skin=guangzhu'));
  assert.equal(f.calls.filter(c => c[0] === 'prompt').length,0);
  f.bridge.dispose();
  const loaded = fixture(f.storage,'session-created'); await loaded.hello(); loaded.switchTo('session-created'); await loaded.hello();
  assert.deepEqual(loaded.calls.filter(c => c[0] === 'prompt'),[['prompt',start.brief]]);
  const result = loaded.messages.find(m => m.data.type === 'gz.session').data;
  assert.equal(result.re,'gz.start'); assert.equal(result.project_id,'t10-project');
  assert.equal(f.storage.getItem('guangzhu.bridge.pending/1'),null);
  assert.equal(JSON.stringify([...f.storage.rows]).includes('完整原文'),false);
  await loaded.send('gz.start',start); assert.equal(loaded.calls.filter(c => c[0] === 'new').length,0);
  assert.ok(!JSON.stringify(loaded.messages).includes('local-user')); loaded.bridge.dispose();
});
test('dialogue start with null brief only opens a session; cancel/followup use current host handle', async () => {
  const f = fixture(); await f.hello(); await f.send('gz.start',{...start,brief:null}); f.switchTo('session-created');
  assert.equal(f.calls.filter(c => c[0] === 'prompt').length,0);
  await f.send('gz.followup',{session_id:'another',text:'wrong'});
  assert.equal(f.messages.at(-1).data.code,'SESSION');
  await f.send('gz.followup',{id:'follow-2',session_id:'session-created',text:'同意建议①：原文'});
  await f.send('gz.cancel',{session_id:'session-created'});
  assert.deepEqual(f.calls.slice(-2),[['prompt','同意建议①：原文'],['cancel']]); f.bridge.dispose();
});
test('duplicate start during reload cannot acknowledge until the host session handle is ready', async () => {
  const first = fixture(); await first.hello(); await first.send('gz.start',start); first.bridge.dispose();
  const loading = fixture(first.storage); await loading.hello(); await loading.send('gz.start',start);
  assert.equal(loading.messages.filter(m => m.data.type === 'gz.session').length,0);
  assert.equal(loading.calls.length,0);
  loading.switchTo('session-created');
  assert.deepEqual(loading.calls,[['prompt',start.brief]]);
  assert.equal(loading.messages.filter(m => m.data.type === 'gz.session').length,1); loading.bridge.dispose();
});
test('each independent start passes a fresh UUID exactly like the official web new-session flow', async () => {
  const f = fixture(); await f.hello();
  await f.send('gz.start',{...start,id:'new-1',brief:null}); f.switchTo('session-created');
  await f.send('gz.start',{...start,id:'new-2',brief:null});
  const created = f.calls.filter(call => call[0] === 'new').map(call => call[1]);
  assert.equal(created.length,2);
  assert.ok(created.every(row => /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$/.test(row.sessionKey)));
  assert.notEqual(created[0].sessionKey,created[1].sessionKey); f.bridge.dispose();
});
test('start errors are correlated, bounded and do not expose raw SDK errors or paths', async () => {
  for (const [change,code] of [[f => f.state.workspaces = [],'WORKSPACE'],[f => f.state.models = [],'MODEL'],
    [f => {f.ctx.agnes.workspace.list = async () => {throw new Error('C:\\Users\\hidden sk-private-dont-send-this-secret');};},'START'],
    [f => {f.switchTo('busy'); f.state.timeline.opState = {};},'BUSY']]) {
    const f = fixture(); change(f); await f.hello(); await f.send('gz.start',start);
    const error = f.messages.filter(m => m.data.type === 'gz.error').at(-1).data;
    assert.equal(error.code,code); assert.equal(error.re,'gz.start'); assert.ok(!JSON.stringify(error).includes('hidden')); f.bridge.dispose();
  }
});
test('open validates existence before navigating and all ten protocol message types are covered', async () => {
  const f = fixture(undefined,'session-current'); await f.hello();
  await f.send('gz.open',{session_id:'missing'}); assert.equal(f.messages.at(-1).data.code,'OPEN');
  await f.send('gz.open',{id:'open-2',session_id:'session-existing'});
  assert.ok(f.calls.at(-1)[1].includes('session=session-existing'));
  f.bridge.approval('mcp_guangzhu_df14eb73_gz_export',true); f.bridge.approval('mcp_guangzhu_df14eb73_gz_export',false);
  assert.deepEqual(f.messages.filter(m => m.data.type === 'gz.approval').map(m => m.data.pending),[true,false]);
  assert.equal(f.bridge.getPending(),''); await tick(20);
  assert.equal(f.messages.find(m => m.data.type === 'gz.progress').data.op,'idle'); f.bridge.dispose();
});
test.skip('projection adapter keeps only tools/text/decided approvals in sequence with byte limits and real timing', () => {
  const fixture = JSON.parse(fs.readFileSync(new URL('../../../reports/assets/T10-spike/40-S3-after-pending-r2.json',import.meta.url),'utf8'));
  const nodes = progressNodes(fixture);
  assert.ok(nodes.some(n => n.kind === 'approval')); assert.ok(nodes.some(n => n.kind === 'tool' && n.started_at));
  assert.ok(nodes.every(n => ['tool','text','approval'].includes(n.kind))); assert.ok(!JSON.stringify(nodes).includes('skill_read'));
  const secret = 'example-token', privatePath = 'C:\\Users\\example\\private', long = '汉😀'.repeat(1500);
  const custom = progressNodes({nodes:[{kind:'assistant',seq:2,text:JSON.stringify({authorization:secret})+' '+privatePath+' '+long},
    {kind:'tool',seq:1,name:'gz_analyze',status:'completed',resultPreview:JSON.stringify({api_key:secret,path:privatePath,text:long})},
    {kind:'tool',seq:3,name:'subagent_fork',resultPreview:long},
    {kind:'approval',seq:4,state:'pending',summary:'gz_export {}'}]});
  assert.equal(custom[0].kind,'tool'); assert.ok(new TextEncoder().encode(custom[0].result).length <= 2048);
  assert.ok(Array.from(custom[1].text).length <= 300); assert.equal(custom[2].result,long);
  assert.ok(!JSON.stringify(custom).includes(secret)); assert.ok(!JSON.stringify(custom).includes('example'));
});
test('projection updates are throttled, final change retained, and no timer publishes after disposal', async () => {
  const f = fixture(undefined,'session-current'); await f.hello(); await tick(10);
  for (let i = 0; i < 10; i++) f.update();
  f.state.timeline = {opState:{},nodes:[{kind:'assistant',seq:1,text:'最新进度'}]};
  await tick(280);
  const progress = f.messages.filter(m => m.data.type === 'gz.progress');
  assert.equal(progress.length,2); assert.equal(progress.at(-1).data.nodes[0].text,'最新进度'); assert.equal(progress.at(-1).data.op,'running');
  f.update(); f.bridge.dispose(); const count = f.messages.length; await tick(260); assert.equal(f.messages.length,count);
});

test('started reflects only current projection own turns even when running was missed and output is empty',async()=>{
  const f=fixture(undefined,'session-current');
  f.state.timeline={sessionId:'session-current',opState:null,nodes:[{kind:'user',seq:1,text:'inbox'}],turns:[]};
  await f.hello(); await tick(280);
  const last=()=>f.messages.filter(m=>m.data.type==='gz.progress').at(-1).data;
  assert.equal(last().started,false);
  f.state.timeline.turns=[{inherited:true,startedAt:'2026-10-04T00:00:01Z',trace:{children:[]}}];
  f.update(); await tick(280);
  assert.equal(last().started,false);
  f.state.timeline.turns.push({inherited:false,startedAt:'2026-10-04T00:00:02Z',endedAt:'2026-10-04T00:00:03Z',trace:{children:[]}});
  f.update(); await tick(280);
  assert.equal(last().started,true);
  assert.equal(last().op,'idle');
  assert.deepEqual(last().nodes,[]);
  assert.equal(last().usage,null);
  f.state.timeline.sessionId='other-session';
  f.update(); await tick(280);
  assert.equal(last().started,false);
  f.bridge.dispose();
});

const installationId='a'.repeat(64), installedWorkspace='b'.repeat(64), setupOperation='c'.repeat(32);
const installedHello=f => f.send('gz.hello',{app:'guangzhu-desktop',installation_id:installationId,workspace_id:installedWorkspace});
const setupFields={installation_id:installationId,operation_id:setupOperation,path:'C:\\光筑安装',workspace_id:installedWorkspace};
function alternateConfiguredFixture() {
  const f=installedFixture(), accounts=[];
  f.state.models=[];
  for (const id of ['deepseek-v4-pro','agnes-3.0-flash']) {
    for (const [suffix,enabled,credentialConfigured] of [['disabled',false,true],['keyless',true,false],['configured',true,true],['chosen',true,true]]) {
      const route=id+'-'+suffix;
      f.state.models.push({id,route,label:id+' '+suffix,provider:'private-provider'});
      accounts.push({route,enabled,credentialConfigured,models:[{id}],accountId:'private-id',label:'private-label',apiKey:'private-key'});
    }
  }
  f.ctx.agnes.config.get=async () => ({profile:'local-dev',accounts});
  return f;
}

test('actual configuredModels filters exact account pairs before defaults and public projection',async t => {
  const f=alternateConfiguredFixture();
  t.after(() => f.bridge.dispose());
  const metadata=await configuredModels(f.ctx);
  const expected=f.state.models.filter(row => /configured|chosen/.test(row.route)).map(({id,route,label}) => ({id,route,name:label}));
  assert.deepEqual(metadata.models,expected);
  assert.deepEqual(metadata.design,{id:'deepseek-v4-pro',route:'deepseek-v4-pro-configured'});
  assert.deepEqual(metadata.review,{id:'agnes-3.0-flash',route:'agnes-3.0-flash-configured'});
  assert.equal(metadata.designConfigured,true);
  assert.equal(metadata.reviewConfigured,true);
  assert.doesNotMatch(JSON.stringify(metadata),/private-|provider|accountId|apiKey/);
});

for (const suffix of ['chosen','keyless','disabled','absent']) {
  test('installed models bridge uses the qualified design preference when usable, otherwise the default ('+suffix+')',async t => {
    const f=alternateConfiguredFixture();
    t.after(() => f.bridge.dispose());
    await installedHello(f);
    const preference='deepseek-v4-pro-'+suffix+'/deepseek-v4-pro';
    await f.send('gz.models',{...setupFields,preference});
    const metadata=f.messages.findLast(row => row.data.type==='gz.setup').data.metadata;
    assert.deepEqual(metadata.design,{id:'deepseek-v4-pro',route:'deepseek-v4-pro-'+(suffix==='chosen' ? 'chosen' : 'configured')});
    assert.equal(metadata.designConfigured,true);
    assert.equal(metadata.reviewConfigured,true);
    assert.deepEqual(metadata.models,(await configuredModels(f.ctx)).models);
    assert.equal(f.calls.some(row => row[0]==='new'),false);
  });
}

test('legacy unqualified design preference resolves an exact configured id and route',async t => {
  const f=alternateConfiguredFixture();
  t.after(() => f.bridge.dispose());
  const metadata=await configuredModels(f.ctx,'deepseek-v4-pro');
  assert.deepEqual(metadata.design,{id:'deepseek-v4-pro',route:'deepseek-v4-pro-configured'});
  assert.equal(metadata.designConfigured,true);
});

test('installed hello publishes only configured public model routes',async t => {
  const f=alternateConfiguredFixture();
  t.after(() => f.bridge.dispose());
  await installedHello(f);
  const models=f.messages.find(row => row.data.type==='gz.ready').data.models;
  const expected=(await configuredModels(f.ctx)).models.map(({id,route,name}) => ({id,route,label:name}));
  assert.deepEqual(models,expected);
  assert.doesNotMatch(JSON.stringify(models),/private-|provider|accountId|apiKey/);
});
function installedFixture() {
  const f=fixture();
  f.state.models=[{id:'deepseek-v4-pro',route:'design-route',label:'DeepSeek'},
    {id:'agnes-3.0-flash',route:'review-route',label:'Agnes'}, {id:'agnes-3.0-flash',route:'other-route',label:'Agnes'}];
  f.state.workspaces=[{name:'guangzhu',path:'C:\\另一个同名工作区',available:true,workspaceId:'d'.repeat(64)},
    {name:'guangzhu',path:setupFields.path,available:true,workspaceId:installedWorkspace}];
  f.ctx.agnes.config={get:async () => ({profile:'local-dev',configured:true,accounts:[
    {route:'design-route',enabled:true,credentialConfigured:true,models:[{id:'deepseek-v4-pro'}],accountId:'private-account'},
    {route:'review-route',enabled:true,credentialConfigured:false,models:[{id:'agnes-3.0-flash'}],baseUrl:'private-url'}]})};
  f.ctx.agnes.workspace.add=async path => {f.calls.push(['add',path]); return {workspace:f.state.workspaces[1]};};
  return f;
}

test('authorized installed registration uses exact root once and public workspace projection only',async t => {
  const f=installedFixture();
  t.after(() => f.bridge.dispose());
  await installedHello(f);
  await f.send('gz.registerWorkspace',setupFields);
  await f.send('gz.registerWorkspace',setupFields);
  assert.deepEqual(f.calls.filter(row => row[0]==='add'),[['add',setupFields.path]]);
  const response=f.messages.find(row => row.data.type==='gz.setup').data;
  assert.deepEqual(response.workspace,{path:setupFields.path,workspaceId:installedWorkspace,available:true});
  assert.equal(response.operation_id,setupOperation);
  assert.equal(response.installation_id,installationId);
  assert.equal(f.calls.some(row => row[0]==='new'),false);
});

test('the first opening after an install learns the park workspace binding from the setup replies',async t => {
  const f=installedFixture(), known=installedFixture();
  t.after(() => {f.bridge.dispose(); known.bridge.dispose();});
  await f.send('gz.hello',{app:'guangzhu-desktop',installation_id:installationId,workspace_id:null});  // configuring: no workspace yet
  assert.equal(f.messages.find(row => row.data.type==='gz.ready').data.workspace_binding,null);
  await f.send('gz.registerWorkspace',setupFields);
  await f.send('gz.models',setupFields);
  await installedHello(known);
  const expected=known.messages.find(row => row.data.type==='gz.ready').data.workspace_binding;
  assert.match(expected,/^[a-f0-9]{64}$/);
  assert.deepEqual(f.messages.filter(row => row.data.type==='gz.setup').map(row => row.data.workspace_binding),[expected,expected]);
});

test('config projection treats each selected model route independently and sends no account DTO',async t => {
  const f=installedFixture();
  t.after(() => f.bridge.dispose());
  await installedHello(f);
  await f.send('gz.models',setupFields);
  const metadata=f.messages.findLast(row => row.data.type==='gz.setup').data.metadata;
  assert.equal(metadata.designConfigured,true);
  assert.equal(metadata.reviewConfigured,true,'any configured model may review when Agnes is absent');
  assert.deepEqual(metadata.review,{id:'deepseek-v4-pro',route:'design-route'});
  assert.deepEqual(metadata.models,[{id:'deepseek-v4-pro',route:'design-route',name:'DeepSeek'}]);
  assert.deepEqual(Object.keys(metadata).sort(),['design','designConfigured','models','profile','review','reviewConfigured']);
  assert.equal(JSON.stringify(metadata).includes('private-'),false);
  assert.equal(metadata.models.every(row => Object.keys(row).sort().join(',')==='id,name,route'),true);
});

for (const invalid of ['denied','malformed','array-only']) test('installed model metadata remains unavailable for '+invalid,async t => {
  const f=installedFixture();
  t.after(() => f.bridge.dispose());
  f.ctx.agnes.config.get=async () => {
    if (invalid==='denied') throw new Error('raw private error');
    return invalid==='array-only' ? {models:f.state.models} : {profile:'local-dev',accounts:[{route:'review-route',enabled:'yes'}]};
  };
  await installedHello(f);
  const ready=f.messages.find(row => row.data.type==='gz.ready');
  assert.ok(ready,'metadata denial must retain the transport/settings handshake');
  assert.deepEqual(ready.data.models,[]);
  let settingsClicks=0;
  f.win.document.getElementById=id => id==='settings' ? {getAttribute:() => null,click:() => {settingsClicks++;}} : null;
  await f.send('gz.openSettings');
  assert.equal(settingsClicks,1);
  assert.equal(f.messages.at(-1).data.type,'gz.settings');
  await f.send('gz.models',setupFields);
  assert.equal(f.messages.some(row => row.data.type==='gz.setup'),false);
  const error=f.messages.at(-1).data;
  assert.equal(error.type,'gz.error');
  assert.equal(error.code,'CONFIG');
  assert.equal(error.operation_id,setupOperation);
  assert.equal(error.installation_id,installationId);
  assert.equal(JSON.stringify(error).includes('raw private'),false);
  assert.equal(f.calls.some(row => row[0]==='new'),false);
});

test('installed design and review sessions resolve exact workspace ID and exact configured route',async t => {
  const f=installedFixture();
  t.after(() => f.bridge.dispose());
  f.ctx.agnes.config.get=async () => ({profile:'local-dev',accounts:[
    {route:'design-route',enabled:true,credentialConfigured:true,models:[{id:'deepseek-v4-pro'}]},
    {route:'review-route',enabled:true,credentialConfigured:true,models:[{id:'agnes-3.0-flash'}]}]});
  await installedHello(f);
  for (const [id,route,project_id] of [['deepseek-v4-pro','design-route','installed-design'],['agnes-3.0-flash','review-route','installed-review']]) {
    await f.send('gz.start',{...start,brief:null,project_id,installation_id:installationId,workspace_id:installedWorkspace,
      design_model:{id,route},id:'start-'+project_id});
  }
  assert.deepEqual(f.calls.filter(row => row[0]==='new').map(row => row[1].cwd),[setupFields.path,setupFields.path]);
  assert.deepEqual(f.calls.filter(row => row[0]==='model').map(row => row[1].route),['design-route','review-route']);
  await f.send('gz.start',{...start,brief:null,installation_id:installationId,workspace_id:installedWorkspace,
    design_model:{id:'agnes-3.0-flash',route:'other-route'},id:'wrong-route'});
  assert.equal(f.calls.filter(row => row[0]==='new').length,2);
  assert.equal(f.messages.at(-1).data.code,'MODEL');
  await f.send('gz.start',{...start,brief:null,installation_id:installationId,workspace_id:'d'.repeat(64),id:'wrong-workspace'});
  assert.equal(f.calls.filter(row => row[0]==='new').length,2);
  assert.equal(f.messages.at(-1).data.code,'WORKSPACE');
});

test('pending navigation cannot resume another installation or workspace',async t => {
  const storage=makeStorage();
  storage.setItem('guangzhu.bridge.pending/1',JSON.stringify({re:'start-old',session_id:'session-existing',project_id:'old',brief:'must-not-send',
    installation_id:'e'.repeat(64),workspace_id:installedWorkspace}));
  const f=fixture(storage,'session-existing');
  t.after(() => f.bridge.dispose());
  await installedHello(f);
  assert.equal(f.calls.some(row => row[0]==='prompt'),false);
  assert.equal(f.messages.some(row => row.data.type==='gz.session'),false);
  const record=JSON.parse(storage.getItem('guangzhu.bridge.pending/1'));
  record.installation_id=installationId;
  record.workspace_id='f'.repeat(64);
  storage.setItem('guangzhu.bridge.pending/1',JSON.stringify(record));
  f.switchTo('session-existing');
  assert.equal(f.calls.some(row => row[0]==='prompt'),false);
  record.workspace_id=installedWorkspace;
  storage.setItem('guangzhu.bridge.pending/1',JSON.stringify(record));
  f.switchTo('session-existing');
  f.switchTo('session-existing');
  assert.deepEqual(f.calls.filter(row => row[0]==='prompt'),[['prompt','must-not-send']]);
});

test('official settings adapter checks the actual enabled host button and gives plain fallback',async t => {
  const f=fixture();
  t.after(() => f.bridge.dispose());
  await f.hello();
  let button=null, clicked=0;
  f.win.document.getElementById=id => {assert.equal(id,'settings'); return button;};
  await f.send('gz.openSettings');
  assert.equal(f.messages.at(-1).data.code,'SETTINGS');
  button={disabled:true,getAttribute:() => null,click:() => clicked++};
  await f.send('gz.openSettings',{id:'settings-disabled'});
  assert.equal(clicked,0);
  button.disabled=false;
  await f.send('gz.openSettings',{id:'settings-enabled'});
  assert.equal(clicked,1);
  assert.equal(f.messages.at(-1).data.type,'gz.settings');
});

test('previous sent acknowledgement cannot adopt a session from another installed association',async t => {
  const f=installedFixture();
  t.after(() => f.bridge.dispose());
  const re='installed-new-request';
  f.storage.setItem('guangzhu.bridge.pending/1.sent',JSON.stringify({re,session_id:'session-foreign',project_id:'foreign',
    installation_id:'e'.repeat(64),workspace_id:installedWorkspace}));
  await installedHello(f);
  await f.send('gz.start',{...start,brief:null,id:re,installation_id:installationId,workspace_id:installedWorkspace,
    design_model:{id:'deepseek-v4-pro',route:'design-route'}});
  assert.equal(f.calls.filter(row => row[0]==='new').length,1);
  assert.equal(f.messages.some(row => row.data.session_id==='session-foreign'),false);
});

function keyFixture(t) {
  const f=fixture(), saved=[], tested=[];
  f.ctx.agnes.config={
    get:async () => ({profile:'local-dev',accounts:[],defaultAccountId:null}),
    test:async input => {tested.push(input); return f.state.testResult ?? {verified:true,models:[{id:'agnes-3.0-flash',name:'Agnes 3.0 Flash'}]};},
    save:async input => {saved.push(input); if (f.state.saveError) throw new Error('raw sdk failure with '+input.apiKey); return {};}};
  t.after(() => f.bridge.dispose());
  return {...f,saved,tested};
}
const replies=f => f.messages.map(row => JSON.stringify(row.data)).join('\n');

test('saveKey tests then saves the key through the official config API and never echoes it',async t => {
  const f=keyFixture(t);
  await f.hello();
  await f.send('gz.saveKey',{provider:'agnes',key:'  placeholder-agnes-key  '});
  assert.deepEqual(f.tested,[{providerId:'agnes-ai',apiKey:'placeholder-agnes-key'}]);
  assert.deepEqual(f.saved,[{providerId:'agnes-ai',apiKey:'placeholder-agnes-key',model:'agnes-3.0-flash',accountId:'gz-agnes',
    label:'Agnes（光筑）',enabled:true,makeDefault:true}]);
  const reply=f.messages.findLast(row => row.data.re==='gz.saveKey');
  assert.deepEqual({type:reply.data.type,provider:reply.data.provider,model:reply.data.model},
    {type:'gz.keySaved',provider:'agnes',model:'agnes-3.0-flash'});
  assert.doesNotMatch(replies(f),/placeholder-agnes-key/);
});

test('saveKey keeps DeepSeek as the default account and Agnes as an extra account',async t => {
  const f=keyFixture(t);
  f.ctx.agnes.config.get=async () => ({profile:'local-dev',accounts:[],defaultAccountId:'gz-deepseek'});
  f.state.testResult={verified:true,models:[{id:'deepseek-flash',name:'Flash'},{id:'deepseek-v4-pro',name:'Pro'}]};
  await f.hello();
  await f.send('gz.saveKey',{provider:'deepseek',key:'placeholder-deepseek-key'});
  assert.equal(f.saved.at(-1).model,'deepseek-v4-pro');
  assert.equal(f.saved.at(-1).makeDefault,true);
  f.state.testResult={verified:true,models:[{id:'agnes-3.0-flash',name:'Flash'}]};
  await f.send('gz.saveKey',{provider:'agnes',key:'placeholder-agnes-key'},{data:{v:1,type:'gz.saveKey',id:'second',provider:'agnes',
    key:'placeholder-agnes-key'}});
  assert.equal(f.saved.at(-1).makeDefault,false);
});

test('saveKey refuses malformed keys, unverified keys and SDK failures with fixed messages',async t => {
  const f=keyFixture(t);
  await f.hello();
  for (const [id,key] of [['short','abc'],['space','has space inside key'],['other','x'.repeat(5000)]]) {
    await f.send('gz.saveKey',{provider:'agnes',key},{data:{v:1,type:'gz.saveKey',id,provider:'agnes',key}});
    assert.equal(f.messages.findLast(row => row.data.re===id).data.code,'KEY_FORMAT');
  }
  await f.send('gz.saveKey',{provider:'unknown',key:'placeholder-agnes-key'},{data:{v:1,type:'gz.saveKey',id:'provider',provider:'unknown',
    key:'placeholder-agnes-key'}});
  assert.equal(f.messages.findLast(row => row.data.re==='provider').data.code,'KEY_FORMAT');
  assert.equal(f.tested.length,0);
  f.state.testResult={verified:false,models:[{id:'agnes-3.0-flash',name:'Flash'}]};
  await f.send('gz.saveKey',{provider:'agnes',key:'placeholder-wrong-key'},{data:{v:1,type:'gz.saveKey',id:'wrong',provider:'agnes',
    key:'placeholder-wrong-key'}});
  assert.equal(f.messages.findLast(row => row.data.re==='wrong').data.code,'KEY_REJECTED');
  assert.equal(f.saved.length,0);
  f.state.testResult=undefined;
  f.state.saveError=true;
  await f.send('gz.saveKey',{provider:'agnes',key:'placeholder-failing-key'},{data:{v:1,type:'gz.saveKey',id:'failing',provider:'agnes',
    key:'placeholder-failing-key'}});
  assert.equal(f.messages.findLast(row => row.data.re==='failing').data.code,'KEY_SAVE');
  assert.doesNotMatch(replies(f),/placeholder-|raw sdk failure/);
});

test('both local desktop origins are accepted and replies go back to the one that said hello',async t => {
  const f=keyFixture(t);
  const installed=DATA.desktopOrigins[1];
  assert.deepEqual(DATA.desktopOrigins,['http://127.0.0.1:8765','http://127.0.0.1:8766']);
  await f.send('gz.hello',{app:'guangzhu-desktop'},{origin:installed,data:{v:1,type:'gz.hello',id:'hello-installed',app:'guangzhu-desktop'}});
  const ready=f.messages.find(row => row.data.type==='gz.ready');
  assert.equal(ready.origin,installed);
  await f.send('gz.saveKey',{},{origin:'http://127.0.0.1:9999',data:{v:1,type:'gz.saveKey',id:'foreign',provider:'agnes',key:'placeholder-agnes-key'}});
  await f.send('gz.saveKey',{},{origin:DATA.desktopOrigins[0],data:{v:1,type:'gz.saveKey',id:'other-desktop',provider:'agnes',
    key:'placeholder-agnes-key'}});
  assert.equal(f.tested.length,0);
  assert.equal(f.messages.some(row => ['foreign','other-desktop'].includes(row.data.re)),false);
});

test('with only an Agnes key configured the design model falls back to Agnes',async t => {
  const f=keyFixture(t);
  f.state.models=[{id:'agnes-3.0-flash',route:'account-gz-agnes',label:'Agnes 3.0 Flash'}];
  f.ctx.agnes.config.get=async () => ({profile:'local-dev',accounts:[{route:'account-gz-agnes',enabled:true,credentialConfigured:true,
    models:[{id:'agnes-3.0-flash'}]}]});
  const metadata=await configuredModels(f.ctx);
  assert.deepEqual(metadata.design,{id:'agnes-3.0-flash',route:'account-gz-agnes'});
  assert.deepEqual(metadata.review,{id:'agnes-3.0-flash',route:'account-gz-agnes'});
  assert.equal(metadata.designConfigured,true);
  assert.equal(metadata.reviewConfigured,true);
});

test('an upgrade (new build, so a new installation id) keeps the park binding of the same install folder and workspace', async () => {
  const bindings = [];
  for (const id of [installationId, 'e'.repeat(64)]) {
    const f = installedFixture();
    await f.send('gz.hello', {app:'guangzhu-desktop', installation_id:id, workspace_id:installedWorkspace});
    bindings.push(f.messages.find(row => row.data.type === 'gz.ready').data.workspace_binding);
    f.bridge.dispose();
  }
  assert.match(bindings[0], /^[a-f0-9]{64}$/);
  assert.equal(bindings[1], bindings[0]);  // a park batch running before the upgrade can still be resumed or skipped
});
