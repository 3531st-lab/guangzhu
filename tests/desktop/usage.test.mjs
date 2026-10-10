import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as data from '../../desktop/web/data.js';
const read = path => JSON.parse(readFileSync(new URL('../../'+path,import.meta.url),'utf8'));
const summary = (...args) => data.usageSummary?.(...args);

test.skip('real projection totals retain titles and identify recorded inference calls without inventing requests',() => {
  const p=read('reports/assets/T10-spike/40-S3-after-pending-r2.json');
  const calls=p.turns.flatMap(t => t.usage.calls).filter(c => !c.adjustment);
  assert.equal(calls.filter(c => c.purpose === 'title').length,1);
  const input={session_id:p.sessionId,started_at:p.turns[0].startedAt,ended_at:p.turns.at(-1).endedAt,model_requests:null,recorded_model_calls:new Set(calls.filter(c => c.purpose === 'inference').map(c => c.id)).size,tokens:p.usage.totals,costs:[{currency:'USD',micros:p.usage.cost.usdMicros}],billing_complete:p.usage.billingComplete,missing_costs:0};
  assert.deepEqual(summary(input),{elapsed_seconds:65.586,model_requests:null,recorded_model_calls:4,tokens:{input:2702,output:586,cacheRead:71936,cacheWrite:0,reasoning:0},total_tokens:75224,costs:[{currency:'USD',micros:1946}],billing_complete:true,missing_costs:0});
});

test.skip('archived request/token/time values use frozen run metadata and do not add reasoning twice',() => {
  const run=read('runs/gz-t14-changzhou-005/run.json'), actual=summary(run);
  assert.equal(actual?.model_requests,16); assert.equal(actual?.elapsed_seconds,82.882);
  assert.equal(actual?.total_tokens,334544); assert.equal(actual?.tokens.reasoning,709);
  assert.deepEqual(actual?.tokens,run.tokens); assert.deepEqual(actual?.costs,[],'run without billing cannot become zero dollars');
});

test('unknown and malformed values remain unknown, real zeros survive, currencies remain separate',() => {
  const unknown=summary(null);
  assert.equal(unknown?.elapsed_seconds,null); assert.equal(unknown?.model_requests,null); assert.equal(unknown?.total_tokens,null);
  assert.equal(unknown?.missing_costs,null); assert.equal(unknown?.billing_complete,false); assert.deepEqual(unknown?.costs,[]);
  const value=summary({tokens:{input:0,output:0,cacheRead:0,cacheWrite:0,reasoning:0},model_requests:0,costs:[{currency:'USD',micros:0},{currency:'CNY',micros:2000000}],billing_complete:false,missing_costs:1});
  assert.equal(value?.model_requests,0); assert.equal(value?.total_tokens,0);
  assert.deepEqual(value?.costs,[{currency:'USD',micros:0},{currency:'CNY',micros:2000000}]); assert.equal(value?.billing_complete,false);
  const bad=summary({model_requests:'16',tokens:{input:null,output:-1,cacheRead:Infinity,cacheWrite:0},costs:[{currency:'USD',micros:null}],missing_costs:'0'});
  assert.equal(bad?.model_requests,null); assert.equal(bad?.total_tokens,null); assert.equal(bad?.missing_costs,null); assert.deepEqual(bad?.costs,[]);
});

test('elapsed duration advances only for explicitly live sessions and never becomes negative',() => {
  const value={started_at:'2026-10-02T20:00:00.000Z'}, now=Date.parse('2026-10-02T20:00:02.125Z');
  assert.equal(summary(value,{live:true,now})?.elapsed_seconds,2.125);
  assert.equal(summary(value,{live:false,now})?.elapsed_seconds,null);
  assert.equal(summary({...value,ended_at:'bad'},{live:true,now})?.elapsed_seconds,null);
  assert.equal(summary({...value,ended_at:'2026-10-02T19:59:59Z'})?.elapsed_seconds,null);
});
