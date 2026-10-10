import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {SessionRuns,parseTaskBrief,openSession} from './session-runs.js';
import {replayRows} from './replay.mjs';

test('opening a known design or review restores its own flags; an unknown old session starts with no flags', () => {
  const cache = new SessionRuns();
  const design = {compare:false,export:true,review:{enabled:true,mode:'independent'}};
  const reviewer = {compare:false,export:false,review:{enabled:true,mode:'independent'}};
  cache.start('start-design',design);
  assert.deepEqual(cache.get('old-session'),{});
  cache.accept({re:'start-design',session_id:'design'});
  cache.start('start-review',reviewer);
  assert.deepEqual(cache.get('design'),design);
  cache.accept({re:'start-review',session_id:'reviewer'});
  assert.deepEqual(cache.get('reviewer'),reviewer);
  assert.deepEqual(cache.get('design'),design);
  assert.deepEqual(cache.get('old-session'),{});
  const returned = cache.get('design'); returned.review.mode = 'subagent';
  assert.equal(cache.get('design').review.mode,'independent','caller cannot contaminate cached flags');
});

test('only a matching accepted start transfers run options; failed or unrelated requests do not', () => {
  const cache = new SessionRuns();
  cache.start('pending',{compare:false});
  assert.deepEqual(cache.accept({re:'unrelated',session_id:'old-session'}),{});
  assert.deepEqual(cache.get('old-session'),{});
  cache.reject('pending');
  assert.deepEqual(cache.accept({re:'pending',session_id:'new-session'}),{});
});

test('a reviewer JSON example is not mistaken for a task brief or used to overwrite local review options', () => {
  assert.equal(parseTaskBrief('审核完成后返回：\n```json\n{"verdict":"approve","findings":[]}\n```'),null);
  assert.equal(parseTaskBrief(null),null);
  assert.equal(parseTaskBrief('普通任务文本'),null);
  const task = {brief:'guangzhu.brief/1',project:{id:'test'},run:{compare:false}};
  assert.deepEqual(parseTaskBrief('```json\n'+JSON.stringify(task)+'\n```'),task);
});

test('replay never lends pending options to old-session progress, and retains flags across session switches', () => {
  const row = (direction,message) => ({direction,message,at:'2026-10-02T00:00:00Z'});
  const progress = session_id => row('in',{type:'gz.progress',session_id,op:'idle',nodes:[]});
  const design = {compare:false,export:true,review:{enabled:true,mode:'independent'}};
  const reviewer = {compare:true,export:false,review:{enabled:true,mode:'independent'}};
  const rows = [
    row('out',{type:'gz.start',id:'s1',project_id:'p1',brief:'```json\n'+JSON.stringify({brief:'guangzhu.brief/1',run:design})+'\n```'}),
    progress('old'),
    row('in',{type:'gz.session',id:'ack1',re:'s1',session_id:'design',project_id:'p1'}),
    progress('design'),
    row('local',{type:'run.options',project_id:'review-project',run:reviewer}),
    row('out',{type:'gz.start',id:'s2',project_id:'review-project',brief:'审核完成后返回：\n```json\n{"verdict":"approve","findings":[]}\n```'}),
    progress('design'),
    row('in',{type:'gz.session',id:'ack2',re:'s2',session_id:'reviewer',project_id:'review-project'}),
    progress('reviewer'),
    row('out',{type:'gz.open',id:'open-old',session_id:'old'}),progress('old'),
    row('out',{type:'gz.open',id:'open-design',session_id:'design'}),progress('design'),
  ];
  const sessions = replayRows(rows).sessions;
  assert.deepEqual(sessions.find(s => s.session_id === 'old').run,{});
  assert.deepEqual(sessions.find(s => s.session_id === 'design').run,design);
  assert.deepEqual(sessions.find(s => s.session_id === 'reviewer').run,reviewer);
  assert.equal(sessions.find(s => s.session_id === 'old').steps[6].state,'not_started');
  assert.equal(sessions.find(s => s.session_id === 'design').steps[6].state,'skipped');
  assert.equal(sessions.find(s => s.session_id === 'reviewer').steps[9].state,'skipped');
});

const reopenedRun = {compare:true,export:true,review:{enabled:true,mode:'independent'}};
const generated = '```json\n'+JSON.stringify({brief:'guangzhu.brief/1',project:{id:'t10-reopen'},run:reopenedRun})+'\n```';
const projectProgress = (session_id,project_id) => ({type:'gz.progress',session_id,op:'idle',nodes:[{kind:'tool',name:'mcp_example_gz_new_project',status:'completed',result:JSON.stringify({ok:true,project_id})}]});

test('after refresh open sends only gz.open and restores independent mode after matching session and project evidence', () => {
  const refreshed = new SessionRuns(), sent = [], logged = [];
  const options = {sessionId:'original',projectId:'t10-reopen',generatedBrief:generated,currentBrief:generated};
  assert.deepEqual(openSession(refreshed,(...args) => sent.push(args),options,(...args) => logged.push(args)),{});
  assert.deepEqual(sent,[['gz.open',{session_id:'original'}]],'no task brief or followup is sent');
  assert.equal(refreshed.confirmOpen(projectProgress('unrelated','t10-reopen')),null);
  assert.deepEqual(refreshed.get('original'),{});
  const restored = refreshed.confirmOpen(projectProgress('original','t10-reopen'));
  assert.deepEqual(restored,{session_id:'original',project_id:'t10-reopen',run:reopenedRun});
  assert.deepEqual(refreshed.get('original'),reopenedRun);
  assert.equal(logged[0][1].type,'run.open-options');
  assert.ok(!JSON.stringify(logged).includes('```'),'no task body or projection is persisted');
});

test('reopened project mismatch, ambiguous project evidence, and edited or unmatched generated brief cannot restore options', () => {
  for (const change of [{currentBrief:generated+' edited'},{projectId:'t10-other'},{generatedBrief:''}]) {
    const cache = new SessionRuns();
    openSession(cache,() => {},{sessionId:'old',projectId:'t10-reopen',generatedBrief:generated,currentBrief:generated,...change});
    assert.equal(cache.confirmOpen(projectProgress('old','t10-reopen')),null);
    assert.deepEqual(cache.get('old'),{});
  }
  for (const projects of [['t10-wrong'],['t10-reopen','t10-other']]) {
    const cache = new SessionRuns();
    openSession(cache,() => {},{sessionId:'old',projectId:'t10-reopen',generatedBrief:generated,currentBrief:generated});
    assert.equal(cache.confirmOpen({session_id:'old',nodes:projects.flatMap(p => projectProgress('old',p).nodes)}),null);
    assert.deepEqual(cache.get('old'),{});
    assert.equal(cache.confirmOpen(projectProgress('old','t10-reopen')),null,'rejected candidate cannot revive later');
  }
});

test('a reloaded log replays the verified open metadata without a start or prompt message', () => {
  const rows = [], cache = new SessionRuns(), row = (direction,message) => rows.push({at:'2026-10-02T00:00:00Z',direction,message});
  openSession(cache,(type,message) => row('out',{type,...message}),{sessionId:'old',projectId:'t10-reopen',generatedBrief:generated,currentBrief:generated},row);
  row('in',projectProgress('old','t10-reopen'));
  const replayed = replayRows(rows).sessions[0];
  assert.deepEqual(replayed.run,reopenedRun);
  assert.equal(replayed.session_id,'old');
  assert.ok(rows.every(r => !['gz.start','gz.followup'].includes(r.message.type)));
});

test.skip('real impossible006 reload restores its own independent metadata and sends suggestion one only after the UI click', () => {
  const load = name => fs.readFileSync(new URL('../../reports/assets/T10-spike/messages/'+name+'.messages.jsonl',import.meta.url),'utf8').trim().split(/\r?\n/).map(JSON.parse);
  const before = load('t10-embed-20261002180949913');
  const after = load('t10-embed-20261002182306140').filter(r => r.at <= '2026-10-02T18:24:30.000Z');
  const session = '0b2a312a-b620-4cf6-b807-551fa7f36d81';
  const start = before.find(r => r.direction === 'out' && r.message.type === 'gz.start').message;
  const originalRun = parseTaskBrief(start.brief).run;
  assert.equal(start.design_model.id,'deepseek-v4-pro');
  assert.equal(start.project_id,'t10-impossible-006');
  assert.ok(before.some(r => r.message.type === 'gz.session' && r.message.re === start.id && r.message.session_id === session));
  const restored = after.find(r => r.message.type === 'run.restored');
  assert.equal(restored.at,'2026-10-02T18:24:00.170Z');
  assert.equal(restored.message.session_id,session);
  assert.equal(restored.message.project_id,start.project_id);
  assert.deepEqual(restored.message.run,originalRun);
  const checkpoint = replayRows(after.filter(r => r.at < '2026-10-02T18:24:29.484Z'),session).sessions[0];
  assert.deepEqual(checkpoint.run,originalRun);
  assert.equal(checkpoint.run.review.mode,'independent');
  assert.equal(checkpoint.suggestions.length,1);
  const actions = after.filter(r => r.direction === 'out' && ['gz.open','gz.start','gz.followup'].includes(r.message.type));
  assert.deepEqual(actions.map(r => r.message.type),['gz.open','gz.followup']);
  assert.ok(actions.every(r => r.message.session_id === session));
  assert.equal(actions[1].at,'2026-10-02T18:24:29.484Z');
  assert.equal(actions[1].message.text,`同意建议①：${checkpoint.suggestions[0].text}。按一键模式继续，直到申请导出`);
});
