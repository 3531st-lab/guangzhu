import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {resolvedTools, pendingLabel} from '../../desktop/web/tool-results.js';
import {inferRequirements, formSpec, beijingTime, runStats, isEvaluation, recoveryDescription, toolResult,
  withVerifiedReview} from '../../desktop/web/data.js';
import {computeSteps} from '../../desktop/web/steps.js';
import {projectReplay, replayEvents} from '../../desktop/web/replay.js';
import {progressNodes} from '../../agh-plugin/guangzhu-studio/src/bridge.js';
import {cardData, TOOL_NAMES} from '../../agh-plugin/guangzhu-studio/src/logic.js';
import {DATA} from '../../agh-plugin/guangzhu-studio/extensions/main/client/data.js';

const time = seq => new Date(Date.UTC(2026, 9, 3, 14, 20, seq)).toISOString();
const node = (name, seq, data, args = {}, session = 'a') => ({kind:'tool', name, session, seq, result_seq:seq + 1,
  tool_use_id:'id-' + seq, args_json:args, result_json:data, result:JSON.stringify(data), status:'completed', isError:false,
  started_at:time(seq), ts:time(seq), ended_at:time(seq + 1)});
const pending = (seq = 1, args = {version:3}, job = 'J', name = 'gz_export') =>
  node(name, seq, {ok:true, pending:true, job_id:job, tool:name, elapsed_s:80, stage:'正在算「最快回本」（2/3）'}, args);
const wait = (seq = 5, job = 'J', tool = 'gz_export', value = {ok:true, version:3}) =>
  node('gz_wait', seq, {...value, job_id:job, tool}, {job_id:job});

test('latest validated pending wait advances display while original identity and completion remain unchanged', () => {
  const original = pending(1, {version:3}, 'J', 'gz_compare_options');
  original.result_json = {...original.result_json, elapsed_s:40, stage:'正在算（1/3）'};
  original.result = JSON.stringify(original.result_json);
  const progress = wait(5, 'J', original.name, {ok:true, pending:true, elapsed_s:81, stage:'正在算（3/3）'});
  const later = wait(7, 'J', original.name, {ok:true, pending:true, elapsed_s:120, stage:'正在汇总'});
  const source = [original, later, progress], before = JSON.stringify(source);
  for (const [nodes, expected] of [[[original], original], [[original, progress], progress], [source, later]]) {
    const row = resolvedTools(nodes)[0];
    assert.deepEqual(row.data, expected.result_json);
    assert.deepEqual(row.result_json, row.data);
    assert.deepEqual(JSON.parse(row.result), row.data);
    for (const key of ['tool_use_id', 'seq', 'result_seq', 'started_at', 'ended_at', 'args_json']) {
      assert.deepEqual(row[key], original[key], key);
    }
    assert.equal(row.initial.tool_use_id, original.tool_use_id);
    assert.deepEqual(row.initial.result_json, original.result_json);
    assert.equal(row.completion, null);
    assert.equal(row.completion_index, null);
    assert.equal(row.pending, true);
    assert.equal(toolResult(nodes, original.name), null);
  }
  assert.equal(JSON.stringify(source), before);
  const final = wait(9, 'J', original.name, {ok:true, options:[]});
  const row = resolvedTools([...source, final])[0];
  assert.deepEqual(row.data, {ok:true, options:[]});
  assert.equal(row.pending, false);
  assert.equal(row.completion.tool_use_id, final.tool_use_id);
  assert.equal(row.result_seq, final.result_seq);
});

test('projected pending wait updates original plugin card and desktop step without completing either', () => {
  const native = (name, seq, value, args) => ({kind:'tool', name, toolUseId:'native-' + seq, seq, resultSeq:seq + 1,
    status:'completed', startedAt:time(seq), endedAt:time(seq + 1),
    argsPreview:JSON.stringify(args), resultPreview:JSON.stringify(value)});
  const original = native('gz_compare_options', 1, {ok:true, pending:true, job_id:'J', tool:'gz_compare_options',
    elapsed_s:40, stage:'正在算（1/3）'}, {version:3});
  const progress = native('gz_wait', 5, {ok:true, pending:true, job_id:'J', tool:'gz_compare_options',
    elapsed_s:81, stage:'正在算（3/3）'}, {job_id:'J'});
  const nodes = progressNodes({sessionId:'a', nodes:[original, progress]});
  const card = cardData(original, nodes), step = computeSteps(nodes).steps[6];
  const label = '计算中 · 已用 1 分 21 秒 · 正在算（3/3）';
  assert.equal(card.metrics[0].value, label);
  assert.equal(card.pending, true);
  assert.equal(card.status, 'running');
  assert.equal(card.tool, original.name);
  assert.equal(step.detail, label);
  assert.equal(step.metrics[0].value, label);
  assert.equal(step.state, 'running');
  assert.deepEqual(JSON.parse(step.raw), progressNodes({sessionId:'a', nodes:[progress]})[0].result_json);
  const events = replayEvents({nodes:nodes.map(n => ({...n, ts:n.started_at}))}, 'a');
  assert.equal(computeSteps(projectReplay(events, 3).nodes).steps[6].detail, '计算中 · 已用 40 秒 · 正在算（1/3）');
  assert.equal(computeSteps(projectReplay(events, 4).nodes).steps[6].detail, label);
});

test('pending progress cannot cross wrong job, session, tool, unpaired or conflicting identities', () => {
  const original = pending(), progress = wait(5, 'J', 'gz_export', {ok:true, pending:true, elapsed_s:81, stage:'stage3'});
  const failures = [
    [original, {...progress, args_json:{job_id:'wrong'}}],
    [original, {...progress, result_json:{...progress.result_json, job_id:'wrong'}}],
    [original, {...progress, session:'other'}],
    [original, {...progress, result_json:{...progress.result_json, tool:'gz_analyze'}}],
    [original, {...progress, result_seq:progress.seq}],
    [original, {...progress, tool_use_id:null}],
    [original, {...progress, args_json:null, args:'broken'}],
    [original, {...progress, result_json:{...progress.result_json, ok:false}}],
    [original, {...progress, isError:true}],
    [original, progress, {...wait(7, 'J', 'gz_export', progress.result_json), tool_use_id:progress.tool_use_id}],
    [original, pending(3, {version:4}), progress],
    [original, pending(3, {version:3}, 'J', 'gz_analyze'), progress],
    [original, {...original}, progress],
    [original, {...node('gz_analyze', 3, {}), invalid_job_ids:['J']}, progress]
  ];
  for (const source of failures) {
    const before = JSON.stringify(source), row = resolvedTools(source)[0];
    assert.deepEqual(row.data, row.invalid ? null : original.result_json, JSON.stringify(source));
    assert.equal(row.pending, true);
    assert.equal(JSON.stringify(source), before);
  }
});

test('cancelled wait preserves latest successful pending progress and original export approval identity', () => {
  const original = {...pending(), result_seq:4}, progress = wait(5, 'J', 'gz_export',
    {ok:true, pending:true, elapsed_s:81, stage:'正在汇总'});
  const aborted = {...wait(7), result_json:null, result:'aborted', result_code:'CANCELLED', status:'cancelled', isError:true};
  const approval = {kind:'approval', tool:'gz_export', seq:2, tool_use_id:original.tool_use_id,
    verdict:'allowed-once', args_json:{version:3}};
  const source = [original, approval, progress, aborted], before = JSON.stringify(source);
  const row = resolvedTools(source)[0];
  assert.deepEqual(row.data, progress.result_json);
  assert.equal(row.pending, true);
  assert.equal(row.completion, null);
  assert.equal(row.result_seq, original.result_seq);
  assert.deepEqual(row.wait_ids, [progress.tool_use_id, aborted.tool_use_id]);
  assert.equal(computeSteps(source).steps[9].detail, '计算中 · 已用 1 分 21 秒 · 正在汇总');
  assert.equal(computeSteps(source).warning, null);
  const final = wait(9);
  assert.equal(computeSteps([...source, final]).warning, null);
  assert.match(computeSteps([original, {...approval, tool_use_id:progress.tool_use_id}, progress, aborted, final]).warning,
    /没有经过人工批准/);
  assert.equal(JSON.stringify(source), before);
});

test('pending association preserves identity, completion position, original timing and untouched evidence', () => {
  const original = pending(), final = wait(), source = [original, final], before = JSON.stringify(source);
  const row = resolvedTools(source)[0];
  assert.equal(row.tool_use_id, original.tool_use_id);
  assert.deepEqual(row.initial.result_json, original.result_json);
  assert.equal(row.initial.ended_at, original.ended_at);
  assert.equal(row.ended_at, final.ended_at);
  assert.equal(row.result_seq, final.result_seq);
  assert.equal(row.call_index, 0);
  assert.equal(row.completion_index, 1);
  assert.deepEqual(row.wait_ids, [final.tool_use_id]);
  assert.deepEqual(row.data, {ok:true, version:3});
  assert.equal(JSON.stringify(source), before);
  assert.equal(toolResult([original], 'gz_export'), null);
  assert.deepEqual(toolResult(source, 'gz_export'), {ok:true, version:3});
  assert.equal(resolvedTools([final]).length, 0);
  assert.equal(resolvedTools(source.slice(1)).length, 0);
  assert.equal(resolvedTools(source).filter(r => r.completion_index >= 1).length, 1);
  const direct = {...node('gz_edit_design', 1, {ok:true, version:3}), args_json:null, args:'{"ops":['};
  assert.deepEqual(toolResult([direct], 'gz_edit_design'), {ok:true, version:3});
  assert.equal(resolvedTools([{...original, args_json:null, args:'{"ops":['}, final])[0].pending, true);
});

test('every mismatched job/tool/session/identity and conflicting group remains pending', () => {
  const failures = [
    [pending(), wait(5, 'wrong')],
    [pending(), {...wait(), args_json:{job_id:'wrong'}}],
    [pending(), wait(5, 'J', 'gz_analyze')],
    [pending(), {...wait(), session:'other'}],
    [pending(), wait(5, 'J', 'gz_export', {ok:false, code:'JOB_UNKNOWN'})],
    [pending(), {...wait(), result_json:{ok:false, code:'JOB_UNKNOWN'}}],
    [pending(), pending(3, {version:4}), wait()],
    [pending(), pending(3, {version:3}, 'J', 'gz_analyze'), wait()],
    [pending(), wait(), wait(7, 'J', 'gz_export', {ok:true, version:4})],
    [pending(), wait(), {...wait(7), tool_use_id:'id-5'}],
    [pending(), {...pending(3), tool_use_id:'id-1'}, wait()],
    [pending(), {...wait(), result_seq:4}],
    [pending(), {...wait(), args_json:null, args:'not json'}],
    [{...pending(), session:null}, wait()],
    [{...pending(), result_json:{...pending().result_json, tool:'gz_analyze'}}, wait()],
    [pending(), {...node('gz_analyze', 3, {ok:true, job_id:'J'}), tool_use_id:'id-3'},
      {...pending(4, {}, 'J', 'gz_analyze'), tool_use_id:'id-3'}, wait(7)]
  ];
  for (const source of failures) {
    const rows = resolvedTools(source);
    assert.ok(rows.every(r => r.pending || !r.data || r.data.ok === false), JSON.stringify(source));
    assert.equal(toolResult(source, 'gz_export'), null);
  }
  const error = wait(5, 'J', 'gz_export', {ok:false, message_zh:'计算失败'});
  assert.equal(resolvedTools([pending(), error])[0].data.ok, false);
});

test('same argument retries retain each original and choose only a subsequent earliest formal wait', () => {
  const source = [pending(), wait(3), pending(5), wait(7), wait(9)];
  const rows = resolvedTools(source);
  assert.deepEqual(rows.map(r => r.tool_use_id), ['id-1', 'id-5']);
  assert.deepEqual(rows.map(r => r.result_seq), [4, 8]);
  assert.deepEqual(rows.map(r => r.wait_ids), [['id-3', 'id-7', 'id-9'], ['id-7', 'id-9']]);
  assert.deepEqual(rows.map(r => r.initial.result_seq), [2, 6]);
});

test('export wait completion still requires the original exact once approval', () => {
  const original = {...pending(), result_seq:4, ended_at:time(4)}, final = wait(), approval = {kind:'approval', tool:'gz_export', seq:2,
    tool_use_id:original.tool_use_id, verdict:'allowed-once', args_json:{version:3}};
  assert.equal(computeSteps([original, approval, final], {op:'idle'}).warning, null);
  for (const changed of [{...approval, tool_use_id:final.tool_use_id}, {...approval, tool_use_id:null},
    {...approval, verdict:'allowed-session'}, {...approval, seq:6}]) {
    assert.match(computeSteps([original, changed, final], {op:'idle'}).warning, /没有经过人工批准/);
  }
  assert.equal(computeSteps([final], {op:'idle'}).steps[9].state, 'not_started');
  const direct = node('gz_export', 1, {ok:true, version:3});
  assert.match(computeSteps([direct, {...approval, tool_use_id:null}], {approvals:[
    {tool:'gz_export', pending:true, received_at:Date.parse(time(1))}]}).warning, /没有经过人工批准/);
});

test('plugin pending is Chinese and isolated final wait only renders its actual tool card', () => {
  assert.ok(TOOL_NAMES.includes('gz_wait'));
  for (const name of ['gz_compare_options', 'gz_wait']) {
    const card = cardData({name, status:'completed', resultPreview:JSON.stringify(pending().result_json)});
    assert.equal(card.pending, true);
    assert.equal(card.status, 'running');
    assert.equal(card.fallback, false);
    assert.equal(card.metrics[0].value, '计算中 · 已用 1 分 20 秒 · 正在算「最快回本」（2/3）');
  }
  const files = {'manifest.json':'a'.repeat(64)};
  const card = cardData({name:'gz_wait', status:'completed', resultPreview:JSON.stringify({ok:true,
    tool:'gz_export', job_id:'J', version:3, directory:'output/v3', files})});
  assert.equal(card.family, 'export');
  assert.equal(card.fallback, false);
  const original = pending(), final = wait(5, 'J', 'gz_export', {ok:true, version:3, directory:'output/v3', files});
  const resolved = cardData({name:'gz_export', toolUseId:original.tool_use_id,
    status:'completed', resultPreview:original.result}, [original, final]);
  assert.equal(resolved.family, 'export');
  assert.equal(resolved.pending, undefined);
  assert.equal(pendingLabel({elapsed_s:3}), '计算中 · 已用 3 秒');
  assert.equal(cardData({name:'gz_wait', status:'completed', resultPreview:'broken'}).fallback, true);
});

test('public projection retains bounded full bodies after preview truncation and removes private fields', () => {
  const original = pending().result_json;
  const body = {filler:'汉'.repeat(1000), headers:{authorization:'Bearer example-token'}, secret:'example-secret',
    path:'C:\\Users\\private-user\\location', ...original};
  const native = {kind:'tool', name:'gz_export', toolUseId:'original', seq:1, resultSeq:2,
    argsPreview:'{"version":3}', resultPreview:JSON.stringify(body), status:'completed'};
  assert.ok(new TextEncoder().encode(native.resultPreview).length > 2048);
  const p = progressNodes({sessionId:'a', nodes:[native]})[0];
  assert.ok(new TextEncoder().encode(p.result).length <= 2048);
  assert.equal(p.result_json.job_id, 'J');
  assert.equal(p.result_json.filler, body.filler);
  assert.equal(Object.hasOwn(p.result_json, 'secret'), false);
  assert.equal(Object.hasOwn(p.result_json, 'headers'), false);
  assert.ok(!JSON.stringify(p).includes(body.secret));
  assert.ok(!JSON.stringify(p).includes(body.headers.authorization));
  assert.ok(!JSON.stringify(p).includes('private-user'));
  const short = progressNodes({sessionId:'a', nodes:[{...native,
    resultPreview:JSON.stringify({ok:true, secret:'example-secret', headers:{custom:'must-hide'}, ...original})}]})[0];
  assert.ok(!JSON.stringify(short).includes('must-hide'));
  assert.equal(short.result_json.job_id, 'J');
  assert.equal(short.result, JSON.stringify(short.result_json));
  assert.equal(Object.hasOwn(short.result_json, 'secret'), false);
  assert.equal(Object.hasOwn(short.result_json, 'headers'), false);
  assert.ok(!JSON.stringify(short).includes('example-secret'));
  const final = {...native, name:'gz_wait', toolUseId:'wait', seq:5, resultSeq:6,
    argsPreview:'{"job_id":"J"}', resultPreview:JSON.stringify(wait().result_json)};
  assert.equal(resolvedTools(progressNodes({sessionId:'a', nodes:[native, final]}))[0].pending, false);
  const excessive = {...native, resultPreview:JSON.stringify({filler:'x'.repeat(65537), ...original})};
  assert.equal(progressNodes({sessionId:'a', nodes:[excessive]})[0].result_json, null);
});

test.skip('approval projection uses real fields and never invents identity for ambiguous originals', () => {
  const real = JSON.parse(readFileSync(new URL('../../reports/assets/T10-spike/40-S3-after-pending-r2.json', import.meta.url)));
  const p = progressNodes(real), approval = p.find(n => n.kind === 'approval');
  const call = p.find(n => n.kind === 'tool' && n.name === approval.tool && n.seq < approval.seq);
  assert.equal(approval.via, 'sync');
  assert.equal(approval.tool_use_id, call.tool_use_id);
  assert.equal(call.session, real.sessionId);
  assert.equal(call.result_seq, real.nodes.find(n => n.toolUseId === call.tool_use_id).resultSeq);
  const native = {kind:'tool', name:'gz_export', toolUseId:'one', seq:1, resultSeq:5, argsPreview:'{"version":3}'};
  const decision = {kind:'approval', seq:3, requestSeq:2, state:'decided', summary:'gz_export {"version":3}',
    decision:{verdict:'rejected', via:'timeout'}};
  assert.equal(progressNodes({sessionId:'a', nodes:[native, decision]}).at(-1).tool_use_id, 'one');
  assert.equal(progressNodes({sessionId:'a', nodes:[native, {...native, toolUseId:'two'}, decision]}).at(-1).tool_use_id, null);
});

test('native expired approval projection preserves timeout identity through desktop recovery',()=>{
  for (const name of ['gz_analyze','gz_export']) {
    const native={kind:'tool',name,toolUseId:'expired-call',seq:1,resultSeq:5,status:'failed',
      argsPreview:'{"project_id":"synthetic-project","version":3}',resultPreview:'{"ok":false,"code":"APPROVAL_REJECTED"}'};
    const expired={kind:'approval',seq:3,requestSeq:2,state:'expired',risk:'high',options:[],expiresAt:time(3),
      summary:name+' '+native.argsPreview,decision:{verdict:'rejected',via:'timeout'}};
    const nodes=progressNodes({sessionId:'native-session',nodes:[native,expired]});
    const approval=nodes.find(n=>n.kind==='approval');
    assert.ok(approval);
    assert.equal(approval.session,'native-session');
    assert.equal(approval.tool_use_id,native.toolUseId);
    assert.equal(approval.via,'timeout');
    assert.equal(approval.seq,expired.seq);
    assert.deepEqual(approval.args_json,{project_id:'synthetic-project',version:3});
    const recovery=recoveryDescription({id:'native-session',op:'idle',nodes},{});
    assert.equal(recovery.banner,name==='gz_export' ? '导出没有批准（超时）。' : '综合分析的审批 60 秒没点，AGH 自动拒绝了。');
    assert.equal(recovery.actions[0].label,name==='gz_export' ? '重新申请导出' : '重新申请');
    const ambiguous=progressNodes({sessionId:'native-session',nodes:[native,{...native,toolUseId:'second'},expired]});
    assert.equal(ambiguous.find(n=>n.kind==='approval').tool_use_id,null);
    assert.equal(progressNodes({sessionId:'native-session',nodes:[native,{...expired,state:'pending'}]}).length,1);
  }
});

test('all 24 original sentences infer actual structured and economic oracle fields from real roof labels', () => {
  const cases = JSON.parse(readFileSync(new URL('../../eval/cases.json', import.meta.url)));
  assert.equal(cases.length, 24);
  for (const row of cases) {
    const roof = DATA.templates.find(t => t.id === row.template);
    assert.ok(roof, row.template);
    const inferred = inferRequirements(row.text, {keep:[], tiltMin:'', tiltMax:''}, roof);
    const spec = formSpec(inferred.form);
    const named = text => roof.keepouts.filter(zone => text.includes(zone.label.replace(/[（(].*?[）)]/g, ''))).map(zone => zone.id);
    const expected = {keep_clear_ids:[], ...row.structured};
    if (row.structured.keep_clear_ids?.length) expected.keep_clear_ids = named(row.text);
    assert.ok((row.structured.keep_clear_ids ?? []).every(id => expected.keep_clear_ids.includes(id)), row.id);
    assert.deepEqual(spec.structured, expected, row.id);
    assert.deepEqual(spec.economics, row.economics, row.id);
  }
});

test('real sentences, synonyms, hand filled zero and text edits conservatively preserve fields', () => {
  for (const text of ['6年回本', '6年内回本']) assert.equal(inferRequirements(text, {}, {}).form.payback, 6);
  for (const text of ['留2米的检修道', '检修通道至少2米', '通道留2米', '留2米走道']) {
    assert.equal(inferRequirements(text, {}, {}).form.walkway, 2);
  }
  const form = {payback:0, budget:88, selfUse:0, keep:['manual']};
  const roof = {obstacles:[{id:'s', label:'楼梯间（示意）'}, {id:'a', label:'空调外机（示意）'}],
    keepouts:[{id:'x', label:'天窗（示意）'}, {id:'y', label:'天窗（示意）'}]};
  const inferred = inferRequirements('6年回本，预算最多60万元，自用比例100%，别挡天窗，避开楼梯间，空调外机不要动。', form, roof);
  assert.equal(inferred.form.payback, 0);
  assert.equal(inferred.form.budget, 88);
  assert.equal(inferred.form.selfUse, 0);
  assert.deepEqual(inferred.form.keep.sort(), ['a', 'manual', 's', 'x', 'y']);
  assert.match(inferred.summary, /已有值优先/);
  assert.deepEqual(form, {payback:0, budget:88, selfUse:0, keep:['manual']});
  const first = inferRequirements('6年回本', {}, {}).form;
  assert.equal(inferRequirements('5年回本', first, {}).form.payback, 6);
  assert.equal(inferRequirements('造价每瓦4元', {}, {}).form.budget, undefined);
  assert.deepEqual(inferRequirements('设备周边留2米', {}, roof).form.keep, []);
});

test('Beijing outputs are exact across midnight and host time zones', () => {
  const input = '2026-10-03T14:20:07.725Z';
  assert.deepEqual(['full', 'short', 'id'].map(style => beijingTime(input, style)),
    ['2026-10-03 22:20', '10-03 22:20', '1003-2220']);
  assert.equal(beijingTime('2026-10-03T17:20:00Z'), '2026-10-04 01:20');
  assert.equal(beijingTime(null), '未提供');
  for (const tz of ['America/Los_Angeles', 'UTC', 'Asia/Tokyo']) {
    const source = `import {beijingTime} from './desktop/web/data.js'; console.log(beijingTime('${input}'));`;
    const result = spawnSync(process.execPath, ['--input-type=module', '-e', source], {encoding:'utf8', env:{...process.env, TZ:tz}});
    assert.equal(result.status, 0);
    assert.equal(result.stdout.trim(), '2026-10-03 22:20');
  }
});

test('evaluation stays in independent count and explicit false overrides legacy names', () => {
  const rows = [{run_id:'design', passed:true}, {run_id:'failed', passed:false}, {kind:'review', verification:{passed:true}},
    {run_id:'eval-1003-r01-C-1', passed:false}, {run_id:'other', directory:'runs/eval-1003/file', passed:true}];
  assert.deepEqual(runStats(rows), {all:3, passed:1, failed:1, review:1, evaluation:2});
  assert.equal(isEvaluation({run_id:'eval-1003-r01', evaluation:false}), false);
  assert.equal(isEvaluation({run_id:'unevaluated'}), false);
});

test('recovery matrix uses exact wording, rejected version, current turn and successful retry', () => {
  const stopped = nodes => ({id:'a', op:'idle', nodes, turnStart:0});
  const rejection = {kind:'approval', tool:'gz_analyze', seq:3, verdict:'rejected', via:'timeout', args_json:{version:3}};
  assert.deepEqual(recoveryDescription(stopped([rejection]), {}), {banner:'综合分析的审批 60 秒没点，AGH 自动拒绝了。',
    actions:[{label:'重新申请', text:'刚才gz_analyze的审批超时了。请按原参数重新调用它，我会马上批准；然后按一键模式继续，直到申请导出。'}]});
  for (const via of ['timeout', 'sync', 'callback']) {
    const result = recoveryDescription(stopped([{...rejection, tool:'gz_export', via, args_json:{version:3}},
      node('gz_analyze', 4, {ok:true, version:99}, {version:99})]), {});
    assert.equal(result.banner, via === 'timeout' ? '导出没有批准（超时）。' : '导出审批没通过。');
    assert.deepEqual(result.actions, [{label:'重新申请导出', text:'请重新申请导出版本 v3，我会点「仅允许这次」。'}]);
  }
  const fail = node('gz_compare_options', 4, {ok:false, message_zh:'方案失败'});
  assert.deepEqual(recoveryDescription(stopped([fail]), {}).actions, [
    {label:'重试三方案', text:'请按原参数重新调用三方案，然后继续。'},
    {label:'跳过三方案，继续完成', text:'三方案没做完，跳过三方案，用最后通过的版本继续完成复核、审核和导出。'}]);
  assert.equal(recoveryDescription(stopped([fail]), {}).banner, '三方案没算出来：方案失败。');
  const timeout = {...fail, result_json:null, result:'Request timed out', status:'error'};
  assert.equal(recoveryDescription(stopped([timeout]), {}).banner, '三方案没算出来：超时。');
  const quiet = {...stopped([]), idleSince:1000};  // AGH looked idle while the model was still thinking before its first word
  assert.equal(recoveryDescription(quiet, {}, 6000), null);
  assert.match(recoveryDescription(quiet, {}, 21001).banner, /模型没有回话/);
  assert.match(recoveryDescription(stopped([]), {}).banner, /模型没有回话/);  // a stop seen only afterwards is shown at once
  const ordinary = recoveryDescription(stopped([]), {lastText:'停下'});
  assert.equal(ordinary.banner, 'Agent 停下了：停下');
  assert.equal(ordinary.actions[0].text, '继续一键模式，从上一步接着做，不要重复已完成的步骤，直到申请导出。');
  assert.equal(recoveryDescription({...stopped([]), userStopped:true}, {}).banner, '你停止了这次运行。');
  assert.equal(recoveryDescription(stopped([rejection]), {suggestions:[{}]}), null);
  assert.equal(recoveryDescription({op:'idle', nodes:[]}, {}), null);
  assert.deepEqual(recoveryDescription(stopped([pending()]), {}).actions, ordinary.actions);
  assert.equal(recoveryDescription({...stopped([pending()]), op:'running'}, {}), null);
  assert.equal(recoveryDescription(stopped([rejection,pending()]), {}).banner, '综合分析的审批 60 秒没点，AGH 自动拒绝了。');
  assert.equal(recoveryDescription(stopped([pending()]), {suggestions:[{}]}), null);
  assert.equal(recoveryDescription(stopped([rejection]), {steps:[{waiting:true}]}), null);
  assert.equal(recoveryDescription(stopped([{...rejection, tool:'gz_export', via:undefined}]), {}).banner,
    '导出没有批准（原因未记录）。');
  assert.match(recoveryDescription({...stopped([rejection]), turnStart:1}, {}).banner, /Agent 停下了/);
  assert.match(recoveryDescription(stopped([rejection, node('gz_analyze', 5, {ok:true}, {version:3})]), {}).banner, /Agent 停下了/);
});

test('step ownership ignores later summaries, pending is running, modification becomes issue only when stopped', () => {
  const source = [node('gz_project_summary', 1, {ok:true}), {kind:'text', text:'计划：先读摘要。'},
    node('gz_set_requirements', 5, {ok:true}), node('gz_project_summary', 9, {ok:false}),
    node('gz_analyze', 11, {ok:true, rules:{hard_failed:1, passed:1, total:2}})];
  const running = computeSteps(source);
  assert.equal(running.steps[1].state, 'completed');
  assert.equal(running.steps[5].state, 'running');
  assert.equal(running.steps[5].detail, '修改中（第 1 轮）');
  assert.equal(computeSteps(source, {op:'idle'}).steps[5].state, 'issue');
  assert.equal(computeSteps([pending(1, {}, 'J', 'gz_compare_options')]).steps[6].state, 'running');
  assert.equal(computeSteps([node('gz_compare_options', 1, {ok:false, message_zh:'计算失败'})]).steps[6].detail, '计算失败');
  const retried = [pending(1, {}, 'J', 'gz_analyze'), pending(3, {}, 'J', 'gz_analyze'),
    wait(5, 'J', 'gz_analyze', {ok:true, version:3, rules:{hard_failed:0}})];
  assert.equal(computeSteps(retried).rounds.length, 1);
});

test('replay hides all structured formal evidence until result sequence is reached', () => {
  const original = pending(), final = wait(), timeline = {nodes:[original, final]};
  const events = replayEvents(timeline, 'a');
  const begun = projectReplay(events, 1).nodes[0];
  assert.equal(begun.result, '');
  assert.equal(begun.result_json, undefined);
  assert.equal(toolResult([begun], 'gz_export'), null);
  const beforeFinal = projectReplay(events, 3);
  assert.equal(toolResult(beforeFinal.nodes, 'gz_export'), null);
  const afterFinal = projectReplay(events, 4);
  assert.deepEqual(toolResult(afterFinal.nodes, 'gz_export'), {ok:true, version:3});
});

test('hidden duplicate result claims poison association only after the conflict event', () => {
  const ambiguous = {...node('gz_analyze', 3, {}), result_seq:null, ended_at:null, status:'running',
    invalid_job_ids:['J'], invalid_jobs_truncated:false, conflict_seq:9, conflict_at:time(9)};
  const source = [pending(), ambiguous, wait()];
  assert.equal(resolvedTools(source)[0].pending, true);
  const events = replayEvents({nodes:source}, 'a');
  const prior = projectReplay(events, events.length - 1).nodes;
  assert.equal(prior.find(n => n.seq === 3).invalid_job_ids, undefined);
  assert.equal(resolvedTools(prior)[0].pending, false);
  const after = projectReplay(events, events.length).nodes;
  assert.deepEqual(after.find(n => n.seq === 3).invalid_job_ids, ['J']);
  assert.equal(resolvedTools(after)[0].pending, true);
  assert.equal(resolvedTools([pending(), {...ambiguous, invalid_job_ids:[], invalid_jobs_truncated:true}, wait()])[0].pending, true);
});

test('later duplicate declarations and overflow cannot revoke an earlier owned completion', () => {
  for (const overflow of [false, true]) {
    const ambiguous = {...node('gz_analyze', 3, {}), result_seq:null, ended_at:null, status:'running',
      invalid_job_ids:overflow ? ['K'] : ['K', 'J'], invalid_jobs_truncated:overflow, conflict_seq:9, conflict_at:time(9),
      invalid_job_events:[{seq:9, ts:time(9), job_ids:['K'], truncated:false},
        {seq:15, ts:time(15), job_ids:overflow ? [] : ['J'], truncated:overflow}]};
    const source = [pending(), ambiguous, wait()];
    const before = JSON.stringify(source);
    const events = replayEvents({nodes:source}, 'a');
    const second = events.findIndex(event => event.at[1] === 9);
    assert.ok(second >= 0);
    assert.equal(resolvedTools(projectReplay(events, second + 1).nodes)[0].pending, false);
    assert.equal(resolvedTools(projectReplay(events, events.length).nodes)[0].pending, true);
    assert.equal(events.at(-1).at[1], 15);
    assert.equal(resolvedTools(source)[0].pending, true);
    assert.equal(JSON.stringify(source), before);
  }
});

test('verified reviewer completion does not appear before the replay reaches its timestamp', () => {
  const computed = {steps:[{number:9, state:'not_started'}]};
  const saved = {version:3, findings:[], verdict:'approve'};
  const session = {id:'a', reviewSession:'reviewer', reviewCompletedAt:time(9), reviewRecord:{version:3, file:'reviews/v3.json'},
    result:{version:3, selected_version:3, review_files:{'v3.json':saved}},
    verification:{review:{passed:true, independent:[{passed:true, session:'reviewer', versions:[3]}]}}};
  assert.equal(withVerifiedReview(computed, session, {session:'a', at:[Date.parse(time(8)), 99]}), computed);
  assert.equal(withVerifiedReview(computed, session, {session:'a', at:null}), computed);
  assert.equal(withVerifiedReview(computed, session, {session:'reviewer', at:[Date.parse(time(10)), 99]}), computed);
  assert.equal(withVerifiedReview(computed, {...session, reviewCompletedAt:null}, {session:'a', at:[Date.parse(time(10)), 99]}), computed);
  const verified = withVerifiedReview(computed, session, {session:'a', at:[Date.parse(time(9)), 99]});
  assert.equal(verified.steps[0].state, 'completed');
  assert.equal(verified.steps[0].statusLabel, '完成（见审核会话）');
});

test('native CANCELLED wait remains an interrupted transport and permits an owned resumed completion', () => {
  const aborted = {...wait(3), result_json:null, result:'aborted: Request timed out', result_code:'CANCELLED',
    status:'cancelled', isError:true};
  const source = [pending(), aborted, wait(5)];
  const row = resolvedTools(source)[0];
  assert.equal(row.pending, false);
  assert.equal(row.result_seq, 6);
  assert.deepEqual(row.wait_ids, ['id-3', 'id-5']);
  assert.equal(resolvedTools(source.slice(0, 2))[0].pending, true);
  assert.equal(resolvedTools(source.slice(0, 2))[0].completion, null);
  for (const changed of [{...aborted, result_code:'OTHER'}, {...aborted, result_code:null},
    {...aborted, args_json:{job_id:'wrong'}, result_json:{job_id:'J'}}, {...aborted, result_json:{job_id:'wrong'}},
    {...aborted, result_json:{tool:'gz_analyze'}}, {...aborted, isError:false}]) {
    assert.equal(resolvedTools([pending(), changed, wait(5)])[0].pending, true);
  }
  assert.equal(resolvedTools([pending(), aborted, {...aborted, seq:4, result_seq:5}, wait(7)])[0].pending, true);
  const native = {kind:'tool', name:'gz_wait', toolUseId:'cancel', seq:3, resultSeq:4, status:'cancelled',
    argsPreview:'{"job_id":"J"}', resultPreview:'aborted: Request timed out'};
  const p = progressNodes({sessionId:'a', nodes:[native], turns:[{trace:{toolUseId:'cancel', error:{code:'CANCELLED'}}}]})[0];
  assert.equal(p.result_code, 'CANCELLED');
  assert.equal(progressNodes({sessionId:'a', nodes:[native]})[0].result_code, null);
  const events = replayEvents({nodes:source}, 'a');
  assert.equal(projectReplay(events, 3).nodes.at(-1).result_code, undefined);
  assert.equal(projectReplay(events, 4).nodes.at(-1).result_code, 'CANCELLED');
});


test('review phrases accept spaces, Chinese one through ten, MW and budget without 元', () => {
  const phrases = [
    ['装机不超过120kW','capMax',120],['装机不超过 120 kW','capMax',120],['容量上限800kW','capMax',800],
    ['最多装800千瓦','capMax',800],['装 1MW 左右','capMax',1000],['装机 1 MW 以内','capMax',1000],
    ['预算180万','budget',180],['预算不超过180万','budget',180],['投资控制在200万元以内','budget',200],
    ['回收期不超过6年','payback',6],['六年回本','payback',6],['回本期5.5年以内','payback',5.5],
    ['至少装500kW','capMin',500],['装机不少于500kW','capMin',500],['离女儿墙至少1米','edge',1],
    ['自发自用比例 80%','selfUse',80],['6 年内回本，留 1 米检修通道，别挡天窗','payback',6],
    ['6 年内回本，留 1 米检修通道，别挡天窗','walkway',1],['预算 1800000 元','budget',180]
  ];
  for (const [text,key,value] of phrases) {
    assert.equal(inferRequirements(text, {}, {}).form[key],value,text);
    assert.equal(inferRequirements(text, {[key]:0}, {}).form[key],0,'entered zero has precedence');
  }
  for (const [i,n] of [...'一二三四五六七八九十'].entries()) {
    for (const [text,key] of [[n+' 年内回本','payback'],['留 '+n+' 米检修通道','walkway'],
      ['预算 '+n+' 万','budget'],['装机至少 '+n+' MW','capMin']]) {
      assert.equal(inferRequirements(text,{},{}).form[key],(i+1)*(key==='capMin' ? 1000 : 1),text);
    }
  }
  assert.equal(inferRequirements('造价每瓦4元', {}, {}).form.budget,undefined);
  const unknown=inferRequirements('每天3人值班，风速要求 8 米/秒',{},{});
  assert.equal(unknown.summary,'这几处没认出来：每天3人值班；风速要求 8 米/秒，请填到下面的栏里');
  assert.equal(inferRequirements('尽量多装',{},{}).unknown,'');
});

test('尽量多装 and the eval phrasings pick 多装 unless picked by hand; removing the words undoes only the automatic pick', () => {
  for (const text of ['尽量多装，6 年内回本', '预算内尽量铺满', '本期尽量铺满预算', '尽量利用不规则屋面', '尽可能多装']) {
    const inferred = inferRequirements(text, {prefer:'balanced'}, {});
    assert.equal(inferred.form.prefer, 'max_capacity', text);
    assert.match(inferred.summary, /三方案都满足时选：多装/, text);
  }
  const auto = inferRequirements('尽量多装', {prefer:'balanced'}, {}).form;
  assert.equal(inferRequirements('6年回本', auto, {}).form.prefer, 'balanced');
  const kept = inferRequirements('尽量多装', {prefer:'fast_payback', preferPicked:true}, {});
  assert.equal(kept.form.prefer, 'fast_payback');
  assert.match(kept.summary, /三方案都满足时选：最快回本（已选的优先）/);
  assert.equal(inferRequirements('6年回本', {prefer:'max_capacity'}, {}).form.prefer, 'max_capacity', 'not switched by the words, so not undone');
  assert.equal(inferRequirements('不用装满，6年回本', {prefer:'balanced'}, {}).form.prefer, 'balanced');
  assert.equal(inferRequirements('尽量多装，回本五点五年', {}, {}).unknown, '回本五点五年', 'the switch does not hide a number left unread');
  const cases = JSON.parse(readFileSync(new URL('../../eval/cases.json', import.meta.url)));
  const most = cases.filter(row => /尽量/.test(row.text));
  assert.equal(most.length, 12);
  assert.ok(most.every(row => inferRequirements(row.text, {keep:[]}, {}).form.prefer === 'max_capacity'));
});

test('whole Chinese numeral tokens infer one through ninety-nine without concatenating digits', () => {
  for (const [text,key,value] of [['预算十五万','budget',15],['预算三十万','budget',30],['十二年回本','payback',12]]) {
    assert.equal(inferRequirements(text,{},{}).form[key],value,text);
    assert.equal(inferRequirements(text,{[key]:0},{}).form[key],0,'entered zero has precedence');
  }
  const digits='零一二三四五六七八九';
  for (let value=1;value<100;value++) {
    const tens=Math.floor(value/10), units=value%10;
    const token=value<10 ? digits[value] : (tens>1 ? digits[tens] : '')+'十'+(units ? digits[units] : '');
    for (const [text,key,scale] of [[`预算 ${token} 万`,'budget',1],[`${token} 年内回本`,'payback',1],
      [`装机至少 ${token} MW`,'capMin',1000],[`装 ${token} 千瓦 左右`,'capMax',1],[`留 ${token} 米检修通道`,'walkway',1]]) {
      const inferred=inferRequirements(text,{},{});
      assert.equal(inferred.form[key],value*scale,text);
      assert.equal(inferred.unknown,'',text);
    }
  }
});

test('unsupported complete numeral tokens never infer a partial or concatenated constraint', () => {
  const tokens=['零','〇','两','廿','壹拾伍','百','百万','一百二十','一万五','一亿三十','十二点五','十二.五','十十',
    '一二','一十零','三0','0三','一百20','1万五','一万5','1.2.3','.5','5.','十五百','百十五','十二点5'];
  for (const token of tokens) {
    for (const text of [`预算 ${token} 万`,`${token} 年回本`,`${token} 米检修通道`,`装机至少 ${token} MW`]) {
      const inferred=inferRequirements(text,{},{});
      assert.deepEqual(inferred.form,{keep:[]},text);
      assert.equal(inferred.unknown,text,text);
      assert.equal(inferred.summary,`这几处没认出来：${text}，请填到下面的栏里`,text);
    }
  }
  const text='预算 百万，别挡天窗';
  const inferred=inferRequirements(text,{}, {keepouts:[{id:'sky',label:'天窗'}]});
  assert.deepEqual(inferred.form,{keep:['sky']});
  assert.equal(inferred.unknown,'预算 百万');
  assert.equal(inferRequirements('预算1.5万元，装机至少0.3MW，5.5年回本',{},{}).form.budget,1.5);
});
