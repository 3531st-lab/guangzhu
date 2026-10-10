import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {computeSteps} from '../../desktop/web/steps.js';

const tool = (name, data = {ok:true}, status = 'completed') => ({kind:'tool',name:'mcp_guangzhu_df14eb73_'+name,status,result:JSON.stringify(data)});
const text = text => ({kind:'text',text});
const project = tool('gz_new_project',{ok:true,project_id:'t10-example',roof_area_m2:2160,obstacle_count:2,keepout_count:1});
const layout = tool('gz_generate_layout',{ok:true,version:1,modules:400,dc_kw:220});
const analyze = (version,hard_failed) => tool('gz_analyze',{ok:true,version,rules:{passed:hard_failed ? 16 : 22,total:22,hard_failed,failed:hard_failed ? [{id:'S01',value:29,limit:20}] : []}});
const exported = tool('gz_export',{ok:true,files:{'design.json':'a'.repeat(64),'summary.json':'b'.repeat(64)}});
const metric = (result,step,label) => result.steps[step-1].metrics.find(m => m.label === label)?.value;

test('crosscheck details show orientation groups and whole-design totals', () => {
  const result=computeSteps([tool('gz_crosscheck_yield',{ok:true,version:1,differences:[],specific_yield_kwh_kwp:{b:1200},
    groups:[{group:[1,15,90],per_kw:{b:1100}},{group:[2,25,270],per_kw:{b:1300}}],total_kwh:{b:13200}})]);
  assert.deepEqual(metric(result,8,'坡面 1 · 倾角 15° · 朝向 90° kWh/kWp'),{b:1100});
  assert.deepEqual(metric(result,8,'坡面 2 · 倾角 25° · 朝向 270° kWh/kWp'),{b:1300});
  assert.deepEqual(metric(result,8,'全设计合计 kWh'),{b:13200});
});

test.skip('actual S3 projection retains its plan, failed approval, and tool figures without promoting unrelated tools', () => {
  const path = new URL('../../reports/assets/T10-spike/40-S3-after-pending-r2.json',import.meta.url);
  const projection = JSON.parse(fs.readFileSync(path,'utf8'));
  const nodes = projection.nodes.flatMap(n => n.kind === 'assistant' ? [text(n.text)] : n.kind === 'tool' ? [{kind:'tool',name:n.name,status:n.status,result:n.resultPreview}] : n.kind === 'approval' ? [{kind:'approval',tool:n.summary.split(' ')[0],verdict:n.decision?.verdict}] : []);
  const result = computeSteps(nodes,{op:'idle'});
  assert.deepEqual(result.steps.map(s => s.state),['not_started','completed','issue','not_started','not_started','not_started','not_started','not_started','not_started','not_started']);
  assert.ok(result.steps[1].detail.includes('计划一句话'));
  assert.ok(result.lastText.includes('approval rejected'));
  const sample = JSON.parse(nodes.find(n => n.name?.endsWith('_gz_project_summary')).result);
  assert.equal(sample.roof_area_m2,2160);
  assert.equal(computeSteps([...nodes,exported]).warning,'导出没有经过人工批准，这次不能作为 3.1 证据。');
});

test('synthetic complete workflow covers ten steps, repeat analysis rounds, and review JSON', () => {
  const nodes = [project,tool('gz_project_summary'),text('计划：保存需求、排板、验证后导出。'),
    tool('gz_set_requirements',{ok:true,requirements:{structured:{walkway_m_min:1,payback_years_max:6,keep_clear_ids:['sky-1']}},contradictions:[]}),
    tool('gz_fetch_weather',{ok:true,annual_ghi_kwh_m2:1262.735,cache_hit:false}),layout,analyze(1,1),
    tool('gz_edit_design',{ok:true,version:2,summary:'按 S01 调整'}),analyze(2,0),
    tool('gz_compare_options',{ok:true,options:[{name:'折中',version:2,dc_kw:220,payback_years:4.83,irr_pct:17.64,hard_pass:true,violated_requirements:[]}]}),
    tool('gz_crosscheck_yield',{ok:true,specific_yield_kwh_kwp:{a:1038.562,b:1029.44},differences:[{left:'a',right:'b',difference_kwh_kwp:9.122}]}),
    {kind:'tool',name:'subagent_fork',status:'completed',result:'结论：同意。\n```json\n{"verdict":"approve","findings":[]}\n```'},
    tool('gz_record_review',{ok:true,file:'projects/t10-example/reviews/1.json'}),
    exported,{kind:'approval',tool:'gz_export',verdict:'allowed-once'}];
  const result = computeSteps(nodes,{op:'idle'});
  assert.deepEqual(result.steps.map(s => s.state),Array(10).fill('completed'));
  assert.equal(metric(result,1,'屋顶面积 m²'),2160);
  assert.equal(metric(result,3,'保存的结构化字段（含说明）'),3);
  assert.equal(metric(result,4,'全年水平面辐射 kWh/m²'),1262.735);
  assert.equal(metric(result,5,'装机 kW'),220);
  assert.equal(metric(result,7,'折中').payback_years,4.83);
  assert.equal(metric(result,8,'全部链最大差（含天气来源差） kWh/kWp'),9.122);
  assert.equal(metric(result,9,'审核员结论'),'approve');
  assert.equal(metric(result,9,'审核员问题数'),0);
  assert.equal(metric(result,10,'清单文件数'),2);
  assert.deepEqual(metric(result,10,'sha256 前8位'),{'design.json':'aaaaaaaa','summary.json':'bbbbbbbb'});
  assert.deepEqual(result.rounds.map(r => [r.version,r.passed,r.total,r.hard_failed]),[[1,16,22,1],[2,22,22,0]]);
  assert.equal(result.warning,null);
});

test('no waiting signal and no allowed-once approval produces a red export warning', () => {
  const timed = {...exported,started_at:'2026-10-02T00:00:00Z',ended_at:'2026-10-02T00:01:00Z'};
  assert.match(computeSteps([exported]).warning,/不能作为 3.1 证据/);
  assert.equal(computeSteps([timed],{approvals:[{tool:'gz_export',pending:true,received_at:Date.parse('2026-10-02T00:00:01Z')},{tool:'gz_export',pending:false}]}).warning,null);
  assert.equal(computeSteps([exported,{kind:'approval',tool:'mcp_guangzhu_df14eb73_gz_export',verdict:'allowed-once'}]).warning,null);
  assert.ok(computeSteps([timed,{kind:'approval',tool:'gz_export',verdict:'allowed-session'}],{approvals:[{tool:'gz_export',pending:true,received_at:Date.parse('2026-10-02T00:00:01Z')}]}).warning);
  assert.equal(computeSteps([tool('gz_export',{},'running')]).warning,null);
});

test('each export needs its own approval; old, future, ambiguous and wrong-tool evidence cannot transfer', () => {
  const decision = {kind:'approval',tool:'gz_export',verdict:'allowed-once'};
  const first = {...exported,started_at:'2026-10-02T00:00:00Z',ended_at:'2026-10-02T00:01:00Z'};
  const second = {...exported,started_at:'2026-10-02T00:02:00Z',ended_at:'2026-10-02T00:03:00Z'};
  const signal = {tool:'gz_export',pending:true,received_at:Date.parse('2026-10-02T00:00:20Z')};
  assert.ok(computeSteps([first,decision,second]).warning,'first decision cannot approve a second export');
  assert.equal(computeSteps([first,decision,second,decision]).warning,null);
  assert.ok(computeSteps([first,second],{approvals:[signal]}).warning,'one pending signal cannot approve two calls');
  assert.equal(computeSteps([first,second],{approvals:[signal,{...signal,received_at:Date.parse('2026-10-02T00:02:20Z')}]}).warning,null);
  assert.ok(computeSteps([first,second],{approvals:[{...signal,received_at:Date.parse('2026-10-02T00:02:20Z')}]}).warning,'future approval cannot hide the first unapproved export');
  assert.ok(computeSteps([decision,first]).warning,'projection approvals precede results but follow their tool call');
  assert.ok(computeSteps([first,decision,decision]).warning,'ambiguous duplicate approvals require ledger checking');
  assert.ok(computeSteps([first,{...decision,tool:'gz_set_requirements'}]).warning);
  assert.ok(computeSteps([first],{approvals:[{tool:'gz_export',pending:true}]}).warning,'missing timestamps cannot be treated as historical authorization');
  assert.equal(computeSteps([first],{approvals:[signal]}).steps[9].state,'completed','stale pending after tool end cannot reset completed status');
});

test('an earlier rejected attempt does not taint a later independently approved successful export', () => {
  const rejected = {kind:'approval',tool:'gz_export',verdict:'rejected'};
  const allowed = {...rejected,verdict:'allowed-once'};
  assert.equal(computeSteps([tool('gz_export',{ok:false},'failed'),rejected,exported,allowed]).warning,null);
});

test('missing contract fields remain unknown instead of claiming zero requirements, files, or satisfied constraints', () => {
  assert.equal(metric(computeSteps([tool('gz_set_requirements')]),3,'保存的结构化字段（含说明）'),undefined);
  assert.equal(metric(computeSteps([tool('gz_export')]),10,'清单文件数'),undefined);
  assert.equal(metric(computeSteps([tool('gz_compare_options',{ok:true,options:[{name:'missing',hard_pass:true}]})]),7,'missing').meets_requirements,undefined);
  assert.equal(metric(computeSteps([tool('gz_record_review',{ok:true,file:'projects/example/reviews/v1.json'})]),9,'问题数'),undefined);
});

test('independent review still reports failed or running record operations and never fills a separate design session', () => {
  const options = {run:{review:{enabled:true,mode:'independent'}}};
  assert.equal(computeSteps([tool('gz_record_review',{ok:false},'failed')],options).steps[8].state,'issue');
  assert.equal(computeSteps([tool('gz_record_review',{},'running')],options).steps[8].state,'running');
  assert.equal(computeSteps([layout,analyze(1,0)],options).steps[8].state,'not_started');
});

test('pending native approval drives the matching step and a bounded countdown', () => {
  const options = {now:62_000,approvals:[{tool:'mcp_guangzhu_df14eb73_gz_export',pending:true,received_at:5_000}]};
  const step = computeSteps([] ,options).steps[9];
  assert.equal(step.state,'running'); assert.equal(step.waiting,true); assert.equal(step.countdown,3);
  assert.equal(computeSteps([],{...options,now:70_000}).steps[9].countdown,0);
  assert.equal(computeSteps([],{approvals:[...options.approvals,{tool:'gz_export',pending:false}]}).steps[9].waiting,false);
});

test('plan must precede first requirements call, failure overrides completion, disabled optional steps skip', () => {
  assert.equal(computeSteps([tool('gz_project_summary'),tool('gz_set_requirements'),text('计划迟到了')]).steps[1].state,'issue');
  assert.equal(computeSteps([tool('gz_new_project',{ok:false,error:'PROJECT_EXISTS'})]).steps[0].state,'issue');
  assert.equal(computeSteps([tool('gz_new_project',{})]).steps[0].state,'issue');
  assert.equal(computeSteps([tool('gz_fetch_weather',{},'failed')]).steps[3].state,'issue');
  const disabled = computeSteps([],{run:{compare:false,review:{enabled:false},export:false}});
  assert.deepEqual([disabled.steps[6].state,disabled.steps[8].state,disabled.steps[9].state],['skipped','skipped','skipped']);
  const modifying = computeSteps([analyze(1,1)],{op:'running'}).steps[5];
  assert.equal(modifying.state,'running');
  assert.equal(modifying.detail,'修改中（第 1 轮）');
  assert.equal(computeSteps([analyze(1,1)],{op:'idle'}).steps[5].state,'issue');
  assert.equal(computeSteps([tool('gz_analyze',{ok:false},'failed')],{op:'running'}).steps[5].state,'issue');
  assert.equal(computeSteps([analyze(1,1),tool('gz_edit_design',{ok:true,version:2})]).steps[5].state,'running');
});

test('malformed previews stay visible and no metric is invented', () => {
  const node = {kind:'tool',name:'gz_analyze',status:'completed',result:'{"ok":true,"rules":'};
  const result = computeSteps([node]);
  assert.deepEqual(result.steps[5].metrics,[]);
  assert.equal(result.steps[5].raw,node.result);
  assert.equal(result.rounds[0].version,undefined);
});

test('checkpoint suggestions retain literal numbers and followup text; running sessions do not show buttons', () => {
  const nodes = [text('要求做不到。\n建议①：预算提高到 96 万元。\n建议②：装机下限调低到 15.62 千瓦。\n建议③：取消预算上限。')];
  const stopped = computeSteps(nodes,{op:'idle'});
  assert.deepEqual(stopped.suggestions,[{number:'①',text:'预算提高到 96 万元。'},{number:'②',text:'装机下限调低到 15.62 千瓦。'},{number:'③',text:'取消预算上限。'}]);
  assert.equal(stopped.stopped,true);
  assert.deepEqual(computeSteps(nodes,{op:'running'}).suggestions,[]);
});

test.skip('real impossible002 Markdown labels do not leak into the selected suggestion', () => {
  const path = new URL('../../runs/t10-impossible-002/ledger.agnes.jsonl',import.meta.url);
  const event = fs.readFileSync(path,'utf8').trim().split(/\r?\n/).map(JSON.parse).find(e => e.seq === 92);
  const original = event.data.content.filter(b => b.type === 'text').map(b => b.text).join('');
  const preview = Array.from(original).slice(0,300).join('');
  const result = computeSteps([text(preview)],{op:'idle'});
  assert.equal(result.suggestions[0].text,'把装机下限从 300 千瓦 改为 154 千瓦（本屋顶物理上限），预算上限 50000 元 不动。');
  assert.deepEqual(result.suggestions.map(s => s.number),['①','②']);
  assert.ok(result.suggestions.every(s => !s.text.includes('**') && !s.text.endsWith('-')));
});

test('short suggestions stay within the preview, with explanation excluded and all digits unchanged', () => {
  const original = '**建议①**：取消装机下限 300 千瓦，其余要求不变。\n- **建议②**：保留 6 年回本要求。\n3. __建议③__：保留 1.25 米通道。\n\n说明：以上只是格式测试，不判定建议可行性。';
  assert.ok(Array.from(original).length <= 200);
  assert.deepEqual(computeSteps([text(original)],{op:'idle'}).suggestions,[
    {number:'①',text:'取消装机下限 300 千瓦，其余要求不变。'},
    {number:'②',text:'保留 6 年回本要求。'},
    {number:'③',text:'保留 1.25 米通道。'}]);
});

test.skip('real impossible006 heading scopes its circled suggestion without changing the text or numbers', () => {
  const path = new URL('../../reports/assets/T10-spike/messages/t10-embed-20261002180949913.messages.jsonl',import.meta.url);
  const messages = fs.readFileSync(path,'utf8').trim().split(/\r?\n/).map(JSON.parse).map(row => row.message);
  const progress = messages.find(m => m.type === 'gz.progress' && m.op === 'idle' && m.nodes.some(n => n.text?.includes('**建议（唯一可行候选）**')));
  assert.ok(progress);
  const result = computeSteps(progress.nodes,{op:progress.op});
  const expected = '取消装机下限（原值：装机不少于 300 千瓦 / 300 kW）。该下限同时造成两条矛盾：预算 50000 元低于所需 777000 元、装机 300 千瓦超过屋顶上限 154 千瓦。取消后两条冲突同时不成立，其余要求（预算 ≤50000 元）不变。';
  assert.deepEqual(result.suggestions,[{number:'①',text:expected}]);
  assert.deepEqual(computeSteps(progress.nodes,{op:'running'}).suggestions,[]);
});

test.skip('real impossible006 selects the final actual plan before requirements, not the earlier promise of a plan', () => {
  const path = new URL('../../reports/assets/T10-spike/messages/t10-embed-20261002180949913.messages.jsonl',import.meta.url);
  const messages = fs.readFileSync(path,'utf8').trim().split(/\r?\n/).map(JSON.parse).map(row => row.message);
  const progress = messages.find(m => m.type === 'gz.progress' && m.op === 'idle' && m.nodes.some(n => n.text?.includes('**建议（唯一可行候选）**')));
  const expected = '计划：先保存需求（预算 5 万元、装机 ≥300 kW），取 nasa_hourly 天气，生成初稿并分析；按硬性规则建议修正；通过后做三方案对比并选满足全部要求的版本；再分析并发电复核；最后申请导出。审核为 independent 模式，本设计会话不创建审核员、不调用 gz_record_review、禁用 subagent_*。现在保存需求。';
  assert.ok(progress.nodes.some(n => n.text === '项目已创建。按流程先查项目摘要（用于取边界/留空编号），再说明计划。'));
  assert.equal(computeSteps(progress.nodes,{op:progress.op}).steps[1].detail,expected);
  assert.equal(computeSteps([...progress.nodes,text('计划：保存需求之后的文字不能替换初始计划。')],{op:'idle'}).steps[1].detail,expected);
});

test('circled lines require a suggestion heading and stop before explanation sections', () => {
  for (const heading of ['**说明**','## 原因','建议需要继续研究']) {
    assert.deepEqual(computeSteps([text(`${heading}\n\n① 预算 50000 元。`)],{op:'idle'}).suggestions,[]);
  }
  assert.deepEqual(computeSteps([text('① 没有标题。')],{op:'idle'}).suggestions,[]);
  const scoped = '## 建议\n\n① 保留 1.25 米通道。\n② 保留 6 年回本要求。\n\n**说明**\n\n③ 此处是原因，不能点击。';
  assert.deepEqual(computeSteps([text(scoped)],{op:'idle'}).suggestions,[
    {number:'①',text:'保留 1.25 米通道。'},{number:'②',text:'保留 6 年回本要求。'}]);
  const direct = scoped+'\n建议①：保留原格式建议 9。';
  assert.deepEqual(computeSteps([text(direct)],{op:'idle'}).suggestions,[{number:'①',text:'保留原格式建议 9。'}]);
});

test('computeSteps never mutates nodes, run flags, or approval history', () => {
  const nodes = [project,layout,analyze(1,0)], options = {run:{compare:false},approvals:[]};
  const before = JSON.stringify({nodes,options});
  computeSteps(nodes,options);
  assert.equal(JSON.stringify({nodes,options}),before);
});

test('unsaved what-if shows its own failed-rule count without adding a design round', () => {
  const trial = tool('gz_analyze',{ok:true,version:11,rules:{passed:16,total:22,hard_failed:0,failed:[]},
    what_if:{saved:false,hard_failed:1,rules:[{id:'U03',status:'fail',value:6.5,limit:6}]}});
  const result = computeSteps([analyze(11,0),trial],{op:'idle'});
  assert.equal(result.steps[5].state,'issue');
  assert.equal(metric(result,6,'试算状态'),'未保存');
  assert.equal(metric(result,6,'基准规则通过'),'16/22');
  assert.equal(metric(result,6,'硬性不通过'),1);
  assert.equal(result.rounds.length,1);
  assert.equal(result.rounds[0].hard_failed,0);
  assert.equal(computeSteps([trial]).rounds.length,0);
});
