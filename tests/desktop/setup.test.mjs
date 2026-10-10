import test from 'node:test';
import assert from 'node:assert/strict';
import {Setup} from '../../desktop/web/setup.js';
import * as bridgeModule from '../../desktop/web/bridge.js';
const {Bridge, setAghOrigin} = bridgeModule, currentOrigin = () => bridgeModule.AGH_ORIGIN;
const installation = {installed:true,id:'a'.repeat(64),root:'C:\\安装',build:'build'};
const operation = 'b'.repeat(32), workspace_id = 'c'.repeat(64);
const status = (phase='waiting_workspace') => ({installation,operation_id:operation,phase,busy:false,ready:phase==='ready',workspace_id,
  steps:Array.from({length:7},(_,i) => ({number:i+1,state:i===5 ? 'waiting' : 'ready',reason:'可读原因',action:'下一步'}))});
function fixture(initial=status()) {
  let data=initial, changed=0, refresh=0;
  const calls=[], messages=[];
  const api=async (path,body) => {calls.push({path,body}); return structuredClone(data);};
  const bridge={available:true,ready:true,send:(type,payload,context) => messages.push({type,payload,context}),refresh:() => {refresh++; bridge.ready=false;}};
  const setup=new Setup(api,bridge,() => {changed++;});
  return {setup,bridge,calls,messages,set:dataValue => {data=dataValue;},get changed(){return changed;},get refresh(){return refresh;}};
}

test('the page never starts configuration by itself and only reads status while the launcher configures',async () => {
  for (const phase of ['unconfigured','configuring','failed']) {
    const f=fixture({...status(phase),operation_id:phase==='unconfigured' ? null : operation});
    await f.setup.poll();
    await f.setup.poll();
    assert.deepEqual(f.calls.map(c => c.path),['setup/status','setup/status']);
    assert.equal(f.messages.length,0);
    assert.equal(f.refresh,0);
    assert.equal('begin' in f.setup || 'markup' in f.setup || 'mount' in f.setup,false);
  }
});

test('existing operation reload refreshes once then registers exact root after fresh handshake',async () => {
  const f=fixture();
  await f.setup.poll();
  await f.setup.poll();
  assert.equal(f.refresh,1);
  assert.equal(f.messages.length,0);
  f.bridge.ready=true;
  await f.setup.receive({type:'gz.ready'});
  await f.setup.poll();
  assert.equal(f.messages.length,1);
  assert.equal(f.messages[0].type,'gz.registerWorkspace');
  assert.equal(f.messages[0].payload.path,installation.root);
  assert.equal(f.messages[0].payload.operation_id,operation);
  assert.equal(f.calls.some(c => c.path==='setup/configure'),false);
});

test('stale and duplicate setup replies cannot repeat completion or override a newer operation',async () => {
  const f=fixture();
  await f.setup.poll();
  f.bridge.ready=true;
  f.setup.advance();
  const request=f.messages[0].context;
  const response={type:'gz.setup',installation_id:installation.id,operation_id:operation,
    workspace:{path:installation.root,workspaceId:workspace_id,available:true}};
  await f.setup.receive({...response,operation_id:'d'.repeat(32)},request);
  assert.equal(f.calls.some(c => c.path==='setup/complete'),false);
  await f.setup.receive(response,request);
  await f.setup.receive(response,request);
  assert.equal(f.calls.filter(c => c.path==='setup/complete').length,1);
  f.setup.consumed.clear();
  let complete;
  f.setup.api=() => new Promise(resolve => {complete=resolve;});
  const previous=f.setup.receive(response,request);
  f.setup.status={...status(),operation_id:'e'.repeat(32)};
  complete(status());
  await previous;
  assert.equal(f.setup.status.operation_id,'e'.repeat(32));
});

test('keyless models keep step6 waiting; rechecks after saving a key are read-only model requests',async () => {
  const f=fixture(status('waiting_models'));
  await f.setup.poll();
  assert.equal(f.refresh,0);
  assert.equal(f.messages[0].type,'gz.models');
  const metadata={profile:'local-dev',designConfigured:false,reviewConfigured:false,design:null,review:null,models:[]};
  await f.setup.receive({type:'gz.setup',installation_id:installation.id,operation_id:operation,metadata},f.messages[0].context);
  assert.equal(f.setup.status.ready,false);
  assert.deepEqual(f.calls.find(c => c.path==='setup/models').body,{operation_id:operation,metadata});
  await f.setup.recheck();
  assert.equal(f.messages.filter(m => m.type==='gz.models').length,2);
  assert.equal(f.messages.some(m => m.type==='gz.registerWorkspace'),false);
  assert.equal(f.calls.some(c => c.path==='setup/configure'),false);
});

test('a ready installation keeps its association when a later poll reports waiting models',async () => {
  const f=fixture(status('ready'));
  await f.setup.poll();
  f.set(status('waiting_models'));
  await f.setup.poll();
  assert.deepEqual(f.setup.session,{installation_id:installation.id,workspace_id});
});

test('actual desktop Bridge drops old handshake and clears correlated setup entries on both success and failure',t => {
  const previous=globalThis.window;
  globalThis.window={addEventListener(){},removeEventListener(){}};
  const sent=[],received=[];
  const frame={contentWindow:{postMessage:m => sent.push(m)},addEventListener(){},src:''};
  const bridge=new Bridge(frame,(message,request) => received.push({message,request}));
  t.after(() => {bridge.dispose(); globalThis.window=previous;});
  bridge.installation=installation.id;
  bridge.setAvailable(true);
  bridge.hello();
  const ready={v:1,id:'ready',type:'gz.ready',re:sent.at(-1).id};
  const receive=data => bridge.receive({origin:currentOrigin(),source:frame.contentWindow,data});
  receive(ready);
  assert.equal(bridge.ready,true);
  const old=ready.re;
  bridge.refresh();
  bridge.hello();
  receive({...ready,re:old});
  assert.equal(bridge.ready,false);
  receive({...ready,re:sent.at(-1).id});
  assert.equal(bridge.ready,true);
  for (const type of ['gz.setup','gz.error']) {
    const id=bridge.send('gz.models',{},{setup:true});
    receive({v:1,id:'reply-'+type,type,re:id,metadata:{private:'must-not-log'}});
    assert.equal(bridge.requests.has(id),false);
  }
  assert.equal(bridge.workspaceBinding,null);
  receive({v:1,id:'stray',type:'gz.setup',re:'never-sent',workspace_binding:'e'.repeat(64)});
  assert.equal(bridge.workspaceBinding,null,'only a reply to our own setup request counts');
  const models=bridge.send('gz.models',{},{setup:true});
  receive({v:1,id:'with-binding',type:'gz.setup',re:models,workspace_binding:'f'.repeat(64)});
  assert.equal(bridge.workspaceBinding,'f'.repeat(64),'the first opening after an install gets the park binding here');
  assert.equal(JSON.stringify(bridge.logs).includes('must-not-log'),false);
  const id=bridge.send('gz.saveKey',{provider:'agnes',key:'placeholder-secret-for-test'},{keySave:'agnes'});
  assert.equal(sent.at(-1).key,'placeholder-secret-for-test');
  assert.equal(JSON.stringify(bridge.logs).includes('placeholder-secret-for-test'),false);
  assert.deepEqual(bridge.logs.at(-1).message,{type:'gz.saveKey',provider:'agnes'});
  receive({v:1,id:'saved',type:'gz.keySaved',re:id,provider:'agnes',model:'agnes-3.0-flash'});
  assert.equal(bridge.requests.has(id),false);
  assert.equal(received.at(-1).message.type,'gz.keySaved');
  assert.deepEqual(received.at(-1).request,{keySave:'agnes'});
});


test('unknown installation status is refused and the next poll recovers without configuring',async () => {
  const f=fixture({installation:{id:'unknown'},required:false,ready:true,steps:[]});
  await f.setup.poll();
  assert.equal(f.setup.checking,true);
  assert.match(f.setup.error,/无法读取准备进度/);
  f.set(status('unconfigured'));
  await f.setup.recheck();
  assert.equal(f.setup.checking,false);
  assert.equal(f.calls.some(c => c.path==='setup/configure'),false);
});

test('the AGH origin follows the backend status and rejects anything but a local port',() => {
  setAghOrigin('http://127.0.0.1:4178');
  assert.equal(currentOrigin(),'http://127.0.0.1:4178');
  for (const bad of ['http://localhost:4178','https://127.0.0.1:4178','http://127.0.0.1:4178/x','http://evil.example:4178',undefined]) {
    setAghOrigin(bad);
    assert.equal(currentOrigin(),'http://127.0.0.1:4178');
  }
  setAghOrigin('http://127.0.0.1:4177');
});

test('browser reload retains once-only refresh for the authoritative operation',async t => {
  const previous=globalThis.sessionStorage, rows=new Map();
  globalThis.sessionStorage={getItem:key => rows.get(key) ?? null,setItem:(key,value) => rows.set(key,value)};
  t.after(() => {globalThis.sessionStorage=previous;});
  const first=fixture();
  await first.setup.poll();
  assert.equal(first.refresh,1);
  const reloaded=fixture();
  await reloaded.setup.poll();
  assert.equal(reloaded.refresh,0);
  assert.equal(reloaded.messages[0].type,'gz.registerWorkspace');
  assert.equal(reloaded.calls.some(c => c.path==='setup/configure'),false);
});

test('Codex R05: a bridge error or a missing reply stays on screen until retry, and a retry sends each step exactly once more',async () => {
  const f=fixture();
  await f.setup.poll();
  assert.equal(f.refresh,1);
  f.setup.pending.at-=61e3;
  await f.setup.poll();
  assert.match(f.setup.error,/AGH 重新连接，1 分钟没有回应/);
  await f.setup.recheck();
  assert.equal(f.refresh,2);
  assert.equal(f.setup.error,'');
  f.bridge.ready=true;
  await f.setup.receive({type:'gz.ready'});
  assert.equal(f.messages.length,1);
  const first=f.messages[0].context;
  await f.setup.receive({type:'gz.error',installation_id:installation.id,operation_id:operation,message:'工作区目录不可写'},first);
  assert.equal(f.setup.error,'工作区目录不可写');
  for (let i=0;i<3;i++) await f.setup.poll();
  assert.equal(f.messages.length,1);
  assert.equal(f.setup.error,'工作区目录不可写');
  await f.setup.recheck();
  assert.equal(f.setup.error,'');
  assert.deepEqual(f.messages.map(m => m.type),['gz.registerWorkspace','gz.registerWorkspace']);
  const ok={type:'gz.setup',installation_id:installation.id,operation_id:operation,workspace:{path:installation.root,workspaceId:workspace_id,available:true}};
  f.set(status('waiting_models'));
  await f.setup.receive(ok,f.messages[1].context);
  await f.setup.receive(ok,first);
  assert.equal(f.calls.filter(c => c.path==='setup/complete').length,1);
  await f.setup.poll();
  assert.equal(f.messages.filter(m => m.type==='gz.models').length,1);
  f.setup.pending.at-=61e3;
  await f.setup.poll();
  assert.match(f.setup.error,/AGH 读取模型清单，1 分钟没有回应/);
  await f.setup.poll();
  assert.equal(f.messages.filter(m => m.type==='gz.models').length,1);
  await f.setup.recheck();
  assert.equal(f.messages.filter(m => m.type==='gz.models').length,2);
  const metadata={profile:'local-dev',designConfigured:true,reviewConfigured:false,design:null,review:null,models:[]};
  await f.setup.receive({type:'gz.setup',installation_id:installation.id,operation_id:operation,metadata},f.messages.at(-1).context);
  assert.equal(f.setup.error,'');
  assert.equal(f.setup.pending,null);
  assert.equal(f.calls.some(c => c.path==='setup/configure'),false);
});

test('Codex R05: a failed save after the bridge answered asks for a retry instead of waiting forever',async () => {
  const f=fixture(status('waiting_models'));
  await f.setup.poll();
  f.setup.api=async path => {if (path==='setup/models') throw new Error('后台没响应'); return status('waiting_models');};
  await f.setup.receive({type:'gz.setup',installation_id:installation.id,operation_id:operation,metadata:{models:[]}},f.messages[0].context);
  assert.match(f.setup.error,/请在首页点重试/);
  await f.setup.poll();
  assert.match(f.setup.error,/请在首页点重试/);
  assert.equal(f.messages.length,1);
});
