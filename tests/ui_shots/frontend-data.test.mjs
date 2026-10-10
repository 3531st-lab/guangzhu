import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {formSpec,roofSVG,toolResult,finishRequest,shouldReview,runStats,timeLabel,esc,show,isReviewRecord,replayChoices,recordPassed,recordUnverified,withVerifiedReview,versionSummary,naturallyStopped} from '../../desktop/web/data.js';
import {acceptMessage,AGH_ORIGIN} from '../../desktop/web/bridge.js';
import {computeSteps} from '../../desktop/web/steps.js';
const model = {id:'agnes-3.0-flash',route:'example-route'};
const form = {id:'test-roof',template:'l-shape',text:'预算5万元，保留通道',keep:['sky'],maxRounds:6,compare:true,review:true,exportOn:true,prefer:'balanced',tiltMin:'',tiltMax:''};
const read = file => JSON.parse(fs.readFileSync(new URL('../../'+file,import.meta.url),'utf8'));
function readArtifact(base,capture,relative) {
  assert.ok(capture,'run.json must identify the exact capture');
  const metadata = read(base+capture+'/run.json'), url = new URL('../../'+base+capture+'/'+relative,import.meta.url);
  assert.ok(fs.existsSync(url),`Missing archived fixture: ${base+capture+'/'+relative}`);
  const bytes = fs.readFileSync(url);
  assert.equal(createHash('sha256').update(bytes).digest('hex'),metadata.artifacts[relative],`Archived bytes must match run.json: ${relative}`);
  return JSON.parse(bytes.toString('utf8'));
}

test('form converts only entered values, keeps a zero setback and zero self-use, and never changes the input', () => {
  const values = {...form,budget:'5',edge:'0',selfUse:'0',priceSelf:'0.65',walkway:'',notes:'提示'}, before = structuredClone(values);
  const spec = formSpec(values,model);
  assert.deepEqual(values,before);
  assert.deepEqual(spec.structured,{keep_clear_ids:['sky'],budget_cny_max:50000,edge_setback_m_min:0,notes:'提示'});
  assert.deepEqual(spec.economics,{self_use_ratio:0,price_self_cny_kwh:.65});
  assert.equal(spec.review_mode,'independent');
  assert.equal(spec.reviewer_model,'agnes-3.0-flash');
  assert.equal(spec.review,true);
});
test('partial tilt range is rejected instead of silently writing zero', () => {
  assert.throws(() => formSpec({...form,tiltMin:'15'},model),/完整倾角/);
  assert.deepEqual(formSpec({...form,tiltMin:'15',tiltMax:'20'},model).structured.tilt_deg_range,[15,20]);
  assert.ok(!Object.hasOwn(formSpec(form,undefined),'reviewer_model'),'offline fallback lets the Python template supply its declared default');
});
test('real rotated roof SVG preserves actual polygon and blockers, and escapes labels', () => {
  const project = read('data/demo/projects/rotated/project.json');
  const svg = roofSVG({name:'<script>bad</script>',project},true);
  assert.ok(svg.includes('&lt;script&gt;bad&lt;/script&gt;'));
  assert.ok(!svg.includes('<script>'));
  assert.equal((svg.match(/class="ob"/g) ?? []).length,project.roof.obstacles.length);
  assert.equal((svg.match(/class="ko"/g) ?? []).length,project.roof.keepouts.length);
  assert.match(svg,/viewBox="0 0 80\.694282 66\.350143"/);
});
test('bridge accepts only the actual iframe origin/source, known protocol, and usable progress shape', () => {
  const source = {}, message = {v:1,id:'progress-1',type:'gz.progress',op:'idle',nodes:[],session_id:'s'};
  assert.equal(acceptMessage({origin:AGH_ORIGIN,source,data:message},source),message);
  assert.equal(acceptMessage({origin:'null',source,data:message},source),null);
  assert.equal(acceptMessage({origin:AGH_ORIGIN,source:{},data:message},source),null);
  assert.equal(acceptMessage({origin:AGH_ORIGIN,source,data:{...message,type:'gz.unknown'}},source),null);
  assert.equal(acceptMessage({origin:AGH_ORIGIN,source,data:{...message,nodes:{}}},source),null);
});
test.skip('finish preserves the actual successful export version across an independent reviewer session', () => {
  const nodes = read('runs/t10-impossible-007/timeline.json').nodes;
  const design = {id:'design',project:'t10-impossible-007',nodes};
  assert.equal(toolResult(nodes,'gz_export').version,6);
  assert.deepEqual(finishRequest(design,{id:'review'},model),{session_id:'design',project_id:'t10-impossible-007',export_version:6,review_session_id:'review',reviewer_model:'agnes-3.0-flash'});
  assert.equal(toolResult([{kind:'tool',name:'gz_export',status:'failed',result:'{"ok":false}'}],'gz_export'),null);
});
test.skip('independent review starts only after all four real design checks, respects off and attempt limit, and never recurses from review', () => {
  const session = {review:false,run:{review:{enabled:true}}};
  const verification = read('runs/t10-impossible-007/verification.json');
  const result = {selected_version:6,verification:{...verification,review:{requested:true,passed:false}}};
  assert.equal(shouldReview(session,result,0),true);
  assert.equal(shouldReview(session,{...result,verification:read('runs/t10-impossible-006/verification.json')},0),false);
  assert.equal(shouldReview({...session,review:true},result,1),false);
  assert.equal(shouldReview({...session,run:{review:{enabled:false}}},result,0),false);
  assert.equal(shouldReview(session,result,2),false);
  assert.equal(shouldReview(session,{...result,verification},1),false,'returning to the verified design cannot start a second review');
});
test.skip('records preserve both real passes and failures, and time fractions render Beijing HH:mm', () => {
  const records = ['t10-impossible-007','t10-impossible-006','t10-impossible-007-review'].map(run_id => ({run_id,verification:read('runs/'+run_id+'/verification.json')}));
  assert.equal(records[2].verification.review.passed,null,'legacy design-oriented checks are not an independent-review verdict');
  assert.equal(recordUnverified(records[2]),true);
  assert.deepEqual(runStats(records),{all:3,evaluation:0,passed:1,failed:1,review:1});
  const evaluations = records.map(r => ({...r,evaluation:true}));
  assert.deepEqual(runStats([...records,...evaluations]),{all:3,evaluation:3,passed:1,failed:1,review:1});
  assert.equal(timeLabel(12.1),'12:06'); assert.equal(timeLabel(6.5),'06:30');
  assert.equal(esc('<b>"&'), '&lt;b&gt;&quot;&amp;');
});
test('nested review records never count as four-step design passes and retain failed opinions', () => {
  const good = {run_id:'opaque-stable-id',kind:'review',verification:{passed:false,review:{passed:true}}};
  const bad = {...good,run_id:'another-stable-id',verification:{passed:false,review:{passed:false}}};
  assert.equal(isReviewRecord(good),true); assert.equal(recordPassed(good),true); assert.equal(recordPassed(bad),false);
  assert.deepEqual(runStats([good,bad]),{all:2,evaluation:0,passed:0,failed:1,review:2});
  const design = {run_id:'gz-review-roof',kind:'design',verification:{passed:true}};
  assert.equal(isReviewRecord(design),false);
  assert.deepEqual(runStats([design,good,bad]),{all:3,evaluation:0,passed:1,failed:1,review:2});
  assert.equal(isReviewRecord({run_id:'legacy-review-003'}),true);
  const unknown = {...good,verification:{scope:'independent-review',passed:null,review:{passed:null,state:'unverified'}}};
  assert.equal(recordUnverified(unknown),true); assert.equal(recordPassed(unknown),false);
  assert.deepEqual(runStats([design,good,bad,unknown]),{all:4,evaluation:0,passed:1,failed:1,review:3});
  assert.equal(recordUnverified({...unknown,verification:{passed:false,review:{passed:null}}}),true,'explicit unknown review cannot fall back to a failed design certificate');
  assert.equal(recordUnverified(good),false); assert.equal(recordUnverified(bad),false);
});
test.skip('replay choices use real ledger sessions and only linked metadata labels independent review', () => {
  const design = read('runs/t10-impossible-007/run.json'), reviewer = read('runs/t10-impossible-007-review-003/run.json');
  const nodes = [...read('runs/t10-impossible-007/timeline.json').nodes,...read('runs/t10-impossible-007-review-003/timeline.json').nodes];
  const record = {run:{...design,review_session_id:reviewer.session},timeline:{nodes}};
  const choices = replayChoices(record);
  assert.equal(choices.find(c => c.id === design.session).label,'设计会话');
  assert.equal(choices.find(c => c.id === reviewer.session).label,'独立审核');
  assert.equal(choices.length,new Set(nodes.map(n => n.session)).size);
  assert.equal(replayChoices({run:{...reviewer,kind:'review'},timeline:read('runs/t10-impossible-007-review-003/timeline.json')})[0].label,'独立审核');
});
test.skip('actual CZ003 design gains only the verified matching independent review step without mixing native tool nodes', () => {
  const base = 'runs/gz-t14-changzhou-003/', meta = read(base+'run.json');
  const nodes = read(base+meta.capture+'/timeline.json').nodes, beforeNodes = JSON.stringify(nodes);
  const reviewNodes = read(base+meta.review_capture+'/timeline.json').nodes;
  const reviewRecord = toolResult(reviewNodes,'gz_record_review'), saved = readArtifact(base,meta.review_capture,'project/reviews/'+reviewRecord.file.split('/').at(-1));
  const run = {review:{enabled:true,mode:'independent'}}, computed = computeSteps(nodes,{run,op:'idle'});
  const session = {run,review:false,reviewRecord,reviewSession:meta.review_session_id,verification:read(base+'verification.json'),result:{version:12,selected_version:12,review_files:{[reviewRecord.file.split('/').at(-1)]:saved}}};
  assert.equal(computed.steps.filter(s => s.state === 'completed').length,9);
  const actual = withVerifiedReview(computed,session);
  assert.equal(actual.steps.filter(s => s.state === 'completed').length,10);
  assert.deepEqual(actual.steps[8].metrics.map(m => m.value),['approve',5,reviewRecord.file]);
  assert.deepEqual(JSON.parse(actual.steps[8].raw),saved);
  assert.match(actual.steps[8].detail,new RegExp(meta.review_session_id));
  assert.equal(computed.steps[8].state,'not_started'); assert.equal(JSON.stringify(nodes),beforeNodes);
  for (const variant of [{review:true},{reviewSession:'wrong-session'},{reviewRecord:{...reviewRecord,version:11}},{result:{...session.result,selected_version:11}},{result:{...session.result,review_files:{}}},{verification:{review:{...session.verification.review,passed:false}}}]) {
    assert.equal(withVerifiedReview(computed,{...session,...variant}),computed);
  }
});
test.skip('actual CZ003 version reasons show three original scalar facts, never rejected-candidate logs', () => {
  const base = 'runs/gz-t14-changzhou-003/', meta = read(base+'run.json');
  for (const number of [1,2,3,12]) {
    const design = readArtifact(base,meta.capture,`project/designs/v${number}.json`), actual = versionSummary(design);
    assert.deepEqual(actual.metrics.map(m => m.value),[design.statistics.module_count,design.statistics.dc_kw,design.statistics.row_spacing_m]);
    assert.equal(actual.reason,design.reason);
    assert.ok(actual.metrics.every(m => m.source.startsWith(`designs/v${number}.json · statistics.`)));
    assert.ok(!JSON.stringify(actual).includes('rejected_candidates'));
    assert.ok((actual.title+actual.reason+actual.metrics.map(m => m.label+String(m.value)+m.unit).join(' · ')).length <= 120);
  }
  assert.equal(versionSummary(readArtifact(base,meta.capture,'project/designs/v1.json')).title,'开始 → v1');
  assert.throws(() => readArtifact(base,meta.capture,'project/designs/absent-fixture.json'),/Missing archived fixture/);
  const missing = versionSummary({version:1});
  assert.equal(missing.reason,'未提供'); assert.deepEqual(missing.metrics.map(m => show(m.value)),['未提供','未提供','未提供']);
});
test.skip('actual CZ004 natural stop archives incomplete design but initial idle, approvals and checkpoints do not', () => {
  const base = 'runs/gz-t14-changzhou-004/', meta = read(base+'run.json'), nodes = read(base+meta.capture+'/timeline.json').nodes;
  const session = {nodes,op:'idle',review:false}, computed = computeSteps(nodes,{op:'idle'});
  assert.equal(nodes.at(-1).seq,94); assert.equal(toolResult(nodes,'gz_export'),null);
  assert.equal(naturallyStopped(session,'running',computed),true);
  assert.equal(naturallyStopped(session,'idle',computed),false);
  assert.equal(naturallyStopped({...session,nodes:[]},'running',computed),false);
  assert.equal(naturallyStopped({...session,op:'running'},'running',computed),false);
  assert.equal(naturallyStopped(session,'running',{...computed,steps:computed.steps.map((s,i) => ({...s,waiting:i===2}))}),false);
  const checkpointNodes = read('runs/t10-impossible-004/timeline.json').nodes;
  const checkpoint = computeSteps(checkpointNodes,{op:'idle'});
  assert.ok(checkpoint.suggestions.length > 0);
  assert.equal(naturallyStopped({nodes:checkpointNodes,op:'idle'},'running',checkpoint),false);
});
