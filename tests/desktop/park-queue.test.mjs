import test from 'node:test';
import assert from 'node:assert/strict';
import {ParkQueue} from '../../desktop/web/park-queue.js';

test('persist sending before the native prompt, never resend after reload', async () => {
  const events = [], item = {id:'item', stage:'design', status:'creating', design_session:'known-session'};
  let disk = {revision:0, paused:false, items:[item]};
  const api = async (path, body) => {
    if (path.endsWith('/prompt')) return {brief:'完整任务书'};
    if (path.endsWith('/sending')) {
      assert.equal(body.revision, disk.revision);
      disk = {...disk, revision:1, items:[{...item, status:'sending'}]};
      events.push('persist');
    }
    return structuredClone(disk);
  };
  const queue = new ParkQueue(api, () => events.push('prompt'), () => events.push('create'), () => events.push('restore'));
  await queue.load('park');
  await queue.opened('known-session');
  assert.deepEqual(events, ['persist', 'prompt']);
  const reopened = new ParkQueue(api, () => events.push('duplicate'), () => events.push('create'), () => events.push('restore'));
  await reopened.load('park');
  await reopened.opened('known-session');
  await reopened.next();
  assert.deepEqual(events, ['persist', 'prompt', 'restore']);
});

test('late previous-session progress cannot complete or advance a new item', async () => {
  const queue = new ParkQueue(() => {throw Error('must not mutate');}, () => {}, () => {}, () => {});
  queue.queue = {items:[{id:'new', status:'running', stage:'design', design_session:'new-session'}]};
  await queue.observe({type:'gz.progress', session_id:'old-session', op:'idle', started:true});
  assert.equal(queue.item.id, 'new');
});

test('crash windows before creation reuse identity, after dispatch only reconcile', async () => {
  for (const status of ['creating', 'sending', 'running', 'approval', 'reconcile', 'cancelling']) {
    const calls = [];
    const item = {id:'fixed', stage:'design', status, design_session:'fixed-native-id'};
    const queue = new ParkQueue(async () => ({revision:2, items:[item]}), () => calls.push('prompt'),
      value => calls.push(['create', value.design_session]), value => calls.push(['open', value.design_session]));
    await queue.load('park');
    await queue.next();
    assert.deepEqual(calls, [[status === 'creating' ? 'create' : 'open', 'fixed-native-id']]);
  }
});

test('late prompt preparation cannot send to a changed stage or skipped item', async () => {
  let prepared;
  const calls = [];
  const item = {id:'one', stage:'design', status:'creating', design_session:'design'};
  const queue = new ParkQueue(() => new Promise(resolve => {prepared = resolve;}), () => calls.push('sent'), () => {}, () => {});
  queue.id = 'park';
  queue.queue = {items:[item]};
  const pending = queue.opened('design');
  queue.queue = {items:[{...item, stage:'review'}]};
  prepared({brief:'stale design prompt'});
  await pending;
  assert.deepEqual(calls, []);
});

test('unacknowledged delivery failure stays persisted and never gets another prompt', async () => {
  let disk = {revision:0, items:[{id:'one', stage:'design', status:'creating', design_session:'native'}]};
  const api = async path => {
    if (path.endsWith('/prompt')) return {brief:'brief'};
    if (path.endsWith('/sending')) disk = {...disk, items:[{...disk.items[0], status:'sending'}]};
    return structuredClone(disk);
  };
  const queue = new ParkQueue(api, () => {throw Error('transport lost');}, () => {}, () => {});
  await queue.load('park');
  await assert.rejects(queue.opened('native'), /transport lost/);
  assert.equal(disk.items[0].status, 'sending');
  await queue.opened('native');
});

test('initial empty idle after unknown dispatch sends cancel but cannot advance', async () => {
  const sent = [], dispatched = [];
  let disk = {revision:1, items:[{id:'one', status:'cancelling', stage:'design', design_session:'native'},
    {id:'two', status:'pending', stage:'design', design_session:'next'}]};
  const queue = new ParkQueue(async (path) => {
    const operation = path.split('/').at(-1);
    if (operation === 'cancel_requested') disk.items[0].cancel_requested = true;
    if (operation === 'observed') disk.items[0].started = true;
    if (operation === 'cancelled') disk.items[0].status = 'skipped';
    if (operation === 'claim') disk.items[1].status = 'creating';
    return structuredClone(disk);
  }, type => sent.push(type), item => dispatched.push(item.id), () => {});
  await queue.load('park');
  await queue.observe({type:'gz.progress', session_id:'native', op:'idle', started:false});
  assert.equal(queue.item.status, 'cancelling');
  assert.deepEqual(sent, ['gz.cancel']);
  assert.deepEqual(dispatched, []);
  await queue.observe({type:'gz.progress', session_id:'native', op:'running', started:true});
  assert.deepEqual(sent, ['gz.cancel', 'gz.cancel']);
  await queue.observe({type:'gz.progress', session_id:'native', op:'idle', started:true});
  assert.deepEqual(dispatched, ['two']);
});
