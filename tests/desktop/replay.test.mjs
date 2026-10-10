import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {replayEvents,projectReplay} from '../../desktop/web/replay.js';
import {computeSteps} from '../../desktop/web/steps.js';
const timeline = id => JSON.parse(readFileSync(new URL(`../../runs/${id}/timeline.json`,import.meta.url),'utf8'));
test.skip('real tools cannot reveal final output, failure, or completion before result event',() => {
  const raw = timeline('t10-impossible-007'), session = raw.nodes[0].session, events = replayEvents(raw,session);
  for (const [i,event] of events.entries()) {
    if (event.complete || event.node.kind !== 'tool') continue;
    const call = projectReplay(events,i+1).nodes.find(n => n === event.node || n.seq === event.node.seq);
    assert.equal(call.status,'running');
    assert.equal(call.result,'');
    assert.equal(call.ended_at,null);
    const end = events.findIndex(e => e.complete && e.node === event.node);
    if (end >= 0) assert.deepEqual(projectReplay(events,end+1).nodes.find(n => n.seq === event.node.seq),event.node);
  }
  assert.deepEqual(projectReplay(events,events.length).nodes,raw.nodes.filter(n => n.session === session));
});
test('equal timestamps use result seq; absent result stays running; sessions stay separate',() => {
  const t = '2026-10-02T00:00:00Z';
  const tool = {session:'a',kind:'tool',seq:1,ts:t,name:'gz_analyze',status:'completed',result:'{"version":1}',ended_at:t,result_seq:3};
  const raw = {nodes:[tool,{session:'a',kind:'text',seq:2,ts:t,text:'still waiting'},
    {session:'b',kind:'text',seq:1,ts:t,text:'other session'},
    {session:'a',kind:'tool',seq:4,ts:t,name:'gz_export',status:'running',result:''}]};
  const events = replayEvents(raw,'a');
  assert.equal(events.length,4);
  assert.equal(projectReplay(events,2).nodes[0].result,'');
  assert.equal(projectReplay(events,3).nodes[0].result,tool.result);
  assert.equal(projectReplay(events,4).nodes.at(-1).status,'running');
  assert.ok(projectReplay(events,4).nodes.every(n => n.session === 'a'));
});
test.skip('native asked and decided are displayed but only decisions count for export once',() => {
  const raw = timeline('t10-impossible-007'), events = replayEvents(raw,raw.nodes[0].session), p = projectReplay(events,events.length);
  const exported = p.stepsNodes.filter(n => n.kind === 'approval' && n.tool === 'gz_export');
  assert.deepEqual(exported.map(n => n.verdict),['rejected','allowed-once']);
  assert.equal(p.nodes.filter(n => n.kind === 'approval' && n.tool === 'gz_export').length,4);
  const steps = computeSteps(p.stepsNodes,{run:{review:{mode:'independent'}},op:'idle',approvals:p.approvals});
  assert.equal(steps.warning,null);
  assert.equal(steps.steps[9].state,'completed');
  assert.ok(steps.steps.every(s => s.countdown === null),'replay never invents a live countdown');
});
test.skip('followup trial remains unsaved and does not add a design round in final playback',() => {
  const raw = timeline('t10-changzhou-006-followup'), events = replayEvents(raw,raw.nodes[0].session), p = projectReplay(events,events.length);
  const projected = computeSteps(p.stepsNodes,{op:'idle',run:{review:{mode:'independent'}},approvals:p.approvals});
  const regular = p.nodes.filter(n => n.kind === 'tool' && n.name.endsWith('gz_analyze') && n.status === 'completed' && !JSON.parse(n.result).what_if);
  assert.equal(projected.rounds.length,regular.length);
  assert.ok(projected.steps[5].metrics.some(m => m.value === '未保存'));
});

test('negative claim deltas use native sequence with equal timestamps and reveal no future metadata', () => {
  const ts = '2026-10-02T00:00:00Z';
  const deltas = [{seq:9, ts, job_ids:['earlier'], truncated:false}, {seq:15, ts, job_ids:['later'], truncated:false},
    {seq:20, ts, job_ids:[], truncated:true}];
  const tool = {session:'a', kind:'tool', seq:1, ts, name:'gz_analyze', status:'running', result:'', result_seq:null,
    invalid_job_ids:['earlier', 'later'], invalid_jobs_truncated:true, conflict_seq:9, conflict_at:ts, invalid_job_events:deltas};
  const raw = {nodes:[tool, {...tool, session:'b'}]};
  const before = JSON.stringify(raw);
  const events = replayEvents(raw, 'a');
  assert.deepEqual(events.map(e => e.at[1]), [1, 9, 15, 20]);
  const started = projectReplay(events, 1).nodes[0];
  for (const field of ['invalid_job_events', 'invalid_job_ids', 'invalid_jobs_truncated', 'conflict_seq', 'conflict_at']) {
    assert.equal(started[field], undefined);
  }
  const second = projectReplay(events, 2).nodes[0];
  assert.deepEqual(second.invalid_job_ids, ['earlier']);
  assert.deepEqual(second.invalid_job_events, deltas.slice(0, 1));
  assert.equal(second.invalid_jobs_truncated, false);
  const third = projectReplay(events, 3).nodes[0];
  assert.deepEqual(third.invalid_job_ids, ['earlier', 'later']);
  assert.equal(third.invalid_jobs_truncated, false);
  const overflow = projectReplay(events, 4).nodes[0];
  assert.equal(overflow.invalid_jobs_truncated, true);
  assert.deepEqual(overflow.invalid_job_events, deltas);
  assert.equal(JSON.stringify(raw), before);
});
