import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {Bridge,AGH_ORIGIN} from '../../desktop/web/bridge.js';

test('cold AGH startup waits for real availability, reuses one frame, and never starts a model', t => {
  const previous = globalThis.window;
  globalThis.window = {addEventListener(){},removeEventListener(){}};
  const loads = [], sent = [], listeners = {}, received = [];
  const frame = {contentWindow:{postMessage(message,origin){sent.push({message,origin});}},addEventListener(name,fn){listeners[name]=fn;},set src(value){loads.push(value);}};
  const bridge = new Bridge(frame,message => received.push(message));
  t.after(() => {bridge.dispose(); if (previous === undefined) delete globalThis.window; else globalThis.window=previous;});
  const ready = () => bridge.receive({origin:AGH_ORIGIN,source:frame.contentWindow,data:{v:1,id:'ready',type:'gz.ready',models:[{id:'example-model'}]}});
  assert.equal(loads.length,0,'about:blank must not try a server that is still starting');
  bridge.setAvailable(false); bridge.hello(); ready();
  assert.equal(sent.length,0); assert.equal(bridge.ready,false,'stale ready cannot override the health probe');
  bridge.setAvailable(true);
  assert.deepEqual(loads,[AGH_ORIGIN+'/']);
  listeners.load(); bridge.setAvailable(true); bridge.setAvailable(true);
  assert.equal(loads.length,1,'repeated healthy probes do not reload a pending document');
  ready(); assert.equal(bridge.ready,true); assert.equal(received.length,1);
  bridge.setAvailable(true); listeners.error(); bridge.setAvailable(true);
  assert.equal(loads.length,1,'a live ready session is never refreshed by retries or route-independent probes');
  bridge.setAvailable(false);
  assert.equal(bridge.ready,false); assert.deepEqual(bridge.models,[]);
  ready(); assert.equal(bridge.ready,false);
  bridge.setAvailable(true); assert.equal(loads.length,2,'a real server restart permits loading the same frame again');
  listeners.error(); bridge.setAvailable(true);
  assert.equal(loads.length,3,'an explicit frame load failure can retry while not ready');
  listeners.load(); bridge.setAvailable(true); bridge.hello();
  assert.equal(loads.length,3,'no ready without a frame error may mean a disabled plugin; do not destroy manual fallback');
  assert.ok(sent.length > 0); assert.ok(sent.every(x => x.message.type === 'gz.hello' && x.origin === AGH_ORIGIN));
});

test('the persistent iframe has no eager AGH source before availability is known', () => {
  const html = fs.readFileSync(new URL('../../desktop/web/index.html',import.meta.url),'utf8');
  const frame = html.match(/<iframe\b[^>]*\bid="agh"[^>]*>/g);
  assert.equal(frame.length,1); assert.doesNotMatch(frame[0],/\bsrc\s*=/);
});

test('theme waits for the trusted ready document, survives re-handshake and does not reload a running frame', t => {
  const previous=globalThis.window;
  globalThis.window={addEventListener(){},removeEventListener(){}};
  const sent=[], loads=[], listeners={};
  const frame={
    contentWindow:{postMessage:(message,origin) => sent.push({message,origin})},
    addEventListener:(name,fn) => {listeners[name]=fn;},
    set src(value){loads.push(value);},
  };
  const bridge=new Bridge(frame,() => {});
  t.after(() => {
    bridge.dispose();
    if (previous === undefined) delete globalThis.window;
    else globalThis.window=previous;
  });
  bridge.setTheme?.('dark');
  assert.equal(sent.length,0);
  bridge.setAvailable(true);
  listeners.load();
  const ready={origin:AGH_ORIGIN,source:frame.contentWindow,data:{v:1,id:'ready',type:'gz.ready'}};
  bridge.receive({...ready,source:{}});
  assert.equal(sent.filter(x => x.message.type==='gz.theme').length,0);
  bridge.receive(ready);
  assert.deepEqual(sent.at(-1),{message:{v:1,type:'gz.theme',id:sent.at(-1).message.id,theme:'dark'},origin:AGH_ORIGIN});
  bridge.setTheme('light');
  assert.equal(sent.at(-1).message.theme,'light');
  const count=sent.length;
  bridge.setTheme('system');
  assert.equal(sent.length,count);
  listeners.load();
  bridge.receive(ready);
  assert.equal(sent.at(-1).message.theme,'light');
  assert.deepEqual(loads,[AGH_ORIGIN+'/']);
  assert.ok(sent.every(x => ['gz.hello','gz.theme'].includes(x.message.type)));
});
