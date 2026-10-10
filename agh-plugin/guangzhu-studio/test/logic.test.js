import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {DATA} from '../extensions/main/client/data.js';
import {parseUser,roofGeometry,cardData} from '../src/logic.js';
const user = (...content) => ({kind:'user',content});
const text = text => ({type:'text',text});
const specimens = [
  {template:'changzhou-demo',id:'brief-changzhou',text:'6 年内回本，留1米通道',structured:{payback_years_max:6,walkway_m_min:1,keep_clear_ids:['sky-1']}},
  {template:'l-shape',id:'brief-l-shape',text:'预算30万元',structured:{budget_cny_max:300000,walkway_m_min:1,keep_clear_ids:['sky']}},
  {template:'rotated',id:'brief-rotated',text:'倾角15–20度',structured:{tilt_deg_range:[15,20],walkway_m_min:1,keep_clear_ids:['sky-1']}}
];
const repositoryRoot = fileURLToPath(new URL('../../../', import.meta.url));
function pythonExecutable(root = repositoryRoot, env = process.env) {
  if (env.GUANGZHU_TEST_PYTHON) return env.GUANGZHU_TEST_PYTHON;
  const candidates = ['.venv/Scripts/python.exe', '.venv/bin/python'].map(relative => path.join(root, relative));
  return candidates.find(candidate => fs.existsSync(candidate)) ?? 'python';
}
function pythonBrief(spec, env = process.env) {
  const code = [
    'import json,sys',
    'from guangzhu.brief import render_brief',
    "sys.stdin.reconfigure(encoding='utf8')",
    "sys.stdout.buffer.write(render_brief(json.load(sys.stdin)).encode('utf8'))"
  ].join('\n');
  const result = spawnSync(pythonExecutable(repositoryRoot, env), ['-c', code], {
    cwd: repositoryRoot,
    input: JSON.stringify(spec),
    encoding: 'utf8',
    env: {...env, PYTHONPATH: path.join(repositoryRoot, 'backend')}
  });
  assert.equal(result.status, 0, result.error?.message ?? result.stderr);
  return result.stdout;
}
const briefs = specimens.map(spec => pythonBrief(spec));
test('Python selection supports both repository venv layouts, explicit override, and system fallback', t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'guangzhu-python-selection-'));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  assert.equal(pythonExecutable(root, {}), 'python');
  for (const relative of ['.venv/bin/python', '.venv/Scripts/python.exe']) {
    const executable = path.join(root, relative);
    fs.mkdirSync(path.dirname(executable), {recursive: true});
    fs.writeFileSync(executable, '');
    assert.equal(pythonExecutable(root, {}), executable);
  }
  assert.equal(pythonExecutable(root, {GUANGZHU_TEST_PYTHON: 'chosen-python'}), 'chosen-python');
});
test('repository or configured Python handles task books despite PATH Python lacking pydantic', t => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'guangzhu-python-path-'));
  t.after(() => fs.rmSync(temporary, {recursive: true, force: true}));
  const setup = spawnSync(pythonExecutable(), ['-m', 'venv', '--without-pip', temporary], {encoding: 'utf8'});
  assert.equal(setup.status, 0, setup.error?.message ?? setup.stderr);
  const scripts = path.join(temporary, process.platform === 'win32' ? 'Scripts' : 'bin');
  const executable = path.join(scripts, process.platform === 'win32' ? 'python.exe' : 'python');
  const env = {...process.env};
  if (pythonExecutable(repositoryRoot, {}) !== 'python') {
    delete env.GUANGZHU_TEST_PYTHON;
  } else {
    const selected = spawnSync(pythonExecutable(), ['-c', "import sys; sys.stdout.buffer.write(sys.executable.encode('utf8'))"], {encoding: 'utf8'});
    assert.equal(selected.status, 0, selected.stderr);
    env.GUANGZHU_TEST_PYTHON = selected.stdout.trim();
  }
  const pathKey = Object.keys(env).find(key => key.toLowerCase() === 'path') ?? 'PATH';
  env[pathKey] = scripts + path.delimiter + (env[pathKey] ?? '');
  const missing = spawnSync('python', ['-c', 'import pydantic'], {encoding: 'utf8', env});
  assert.notEqual(missing.status, 0);
  assert.match(missing.stderr, /No module named ['"]pydantic['"]/);
  assert.equal(pythonBrief(specimens[0], env), briefs[0]);
  env.GUANGZHU_TEST_PYTHON = executable;
  assert.throws(() => pythonBrief(specimens[0], env), /No module named ['"]pydantic['"]/);
});
test('three Python-generated task books parse with factual tags and verbatim expandable text', () => {
  for (let i=0;i<briefs.length;i++) {
    const parsed=parseUser(user(text(briefs[i])));
    assert.equal(parsed.kind,'brief'); assert.equal(parsed.projectId,specimens[i].id);
    assert.equal(parsed.text,briefs[i]); assert.ok(parsed.tags.includes('通道 ≥ 1 m'));
    assert.ok(parsed.tags.some(tag=>tag.startsWith('避开 ') && !tag.includes('sky')));
  }
  assert.ok(parseUser(user(text(briefs[0]))).tags.includes('回本 ≤ 6 年'));
  assert.ok(parseUser(user(text(briefs[1]))).tags.includes('预算 ≤ 300000 元'));
  assert.ok(parseUser(user(text(briefs[2]))).tags.includes('倾角 15–20°'));
});
test('ordinary/malformed messages retain all text and empty lines, HTML stays plain, images counted', () => {
  for (const value of ['第一行\n\n第三行','<b>不是粗体</b> & 原样保留','前缀\n'+briefs[0],'【光筑任务书 v1】\n```json\n坏数据\n```']) {
    const parsed=parseUser(user(text(value))); assert.equal(parsed.kind,'plain'); assert.equal(parsed.text,value); assert.deepEqual(parsed.texts,[value]);
  }
  const mixed=parseUser(user(text('第一段\n\n'),{type:'image'},{type:'image'},{type:'audio'},text('<b>&')));
  assert.deepEqual(mixed.texts,['第一段\n\n','<b>&']); assert.deepEqual(mixed.nonText,[{label:'图片',count:2},{label:'音频',count:1}]);
  assert.equal(parseUser(user(text('普通'),text(briefs[0]))).kind,'plain');
  for (const mutate of [d=>d.brief='wrong',d=>delete d.economics,d=>delete d.requirements.structured,d=>d.run.max_rounds=7,d=>d.project.template='bad id!',d=>d.run.review.model=0,d=>d.unknown=true]) {
    const data=JSON.parse(briefs[0].split('```json\n')[1].split('\n```')[0]); mutate(data);
    const value='【光筑任务书 v1】\n```json\n'+JSON.stringify(data)+'\n```', parsed=parseUser(user(text(value)));
    assert.equal(parsed.kind,'plain'); assert.equal(parsed.text,value);
  }
  // T18: a roof the user drew in the desktop app is not bundled with the plugin, yet its task book is still a brief card.
  const own=JSON.parse(briefs[0].split('```json\n')[1].split('\n```')[0]); own.project.template='my-1005-153012';
  const card=parseUser(user(text('【光筑任务书 v1】\n```json\n'+JSON.stringify(own)+'\n```')));
  assert.equal(card.kind,'brief'); assert.equal(card.roofName,'自建屋顶'); assert.ok(card.tags.includes('避开 sky-1'));
  // T22: the owner's answers before construction ride along as an optional object and are counted on the card.
  const asked=JSON.parse(briefs[0].split('```json\n')[1].split('\n```')[0]);
  asked.facts={roof_type:'metal',monthly_kwh:15000,export_allowed:false};
  const answered=parseUser(user(text('【光筑任务书 v1】\n```json\n'+JSON.stringify(asked)+'\n```')));
  assert.equal(answered.kind,'brief'); assert.ok(answered.tags.includes('开工前问答 3 项'));
  asked.facts='彩钢瓦';
  assert.equal(parseUser(user(text('【光筑任务书 v1】\n```json\n'+JSON.stringify(asked)+'\n```'))).kind,'plain');
});
test('T23 load and shifts remain a normal task book card', () => {
  const value = pythonBrief({...specimens[0], facts: {monthly_kwh: 12000, shifts: 2, export_allowed: false}});
  const parsed = parseUser(user(text(value)));
  assert.equal(parsed.kind, 'brief');
  assert.equal(parsed.text, value);
  const data = JSON.parse(value.split('```json\n')[1].split('\n```')[0]);
  assert.deepEqual(data.economics, {monthly_kwh: 12000, shifts: 2, price_export_cny_kwh: 0});
});

test('all evaluation task books use native brief cards with original obstacle labels', () => {
  const cases = JSON.parse(fs.readFileSync(path.join(repositoryRoot, 'eval/cases.json'), 'utf8'));
  for (const item of cases) {
    const spec = Object.fromEntries(['id', 'template', 'text', 'structured', 'economics'].map(key => [key, item[key]]));
    const brief = pythonBrief(spec);
    const parsed = parseUser(user(text(brief)));
    assert.equal(parsed.kind, 'brief', item.id);
    assert.equal(parsed.projectId, item.id);
    assert.equal(parsed.text, brief);
    const roof = DATA.templates.find(row => row.id === item.template);
    assert.equal(parsed.roofName, roof.name);
    for (const id of item.structured.keep_clear_ids ?? []) {
      const zone = [...roof.obstacles, ...roof.keepouts].find(row => row.id === id);
      assert.ok(parsed.tags.some(tag => tag.includes(zone.label)));
    }
  }
});
test('all roof geometries include original complete obstacle shapes, north points up', () => {
  for (const template of DATA.templates) {
    const drawn = roofGeometry(template);
    assert.equal(drawn.obstacles.length,template.obstacles.length);
    assert.equal(drawn.keepouts.length,template.keepouts.length);
    for (const zone of template.obstacles) {
      const shape = drawn.obstacles.find(z => z.id === zone.id);
      assert.equal(shape.label,zone.label);
      if (zone.kind === 'cylinder') assert.deepEqual(shape.circle,{cx:zone.center[0],cy:-zone.center[1],r:zone.radius_m});
      else assert.ok(shape.path.includes(`${zone.footprint[0][0]} ${-zone.footprint[0][1]}`));
    }
    assert.ok(drawn.outline.includes(' Z'));
    assert.equal(drawn.viewBox.split(' ').length,4);
    assert.ok(!('modules' in drawn));
  }
  assert.equal(roofGeometry('l-shape').outline.split('L').length,6);
  assert.equal(roofGeometry('unknown'),null);
});

// The archived runs these tests replay are not part of the public repository; their tests are skipped there.
const archived = relative => fs.existsSync(new URL('../../../'+relative,import.meta.url));
function realBlocks(relative) {
  if (!archived(relative)) return [];
  const events = fs.readFileSync(new URL('../../../'+relative,import.meta.url),'utf8').trim().split('\n').map(JSON.parse), calls = new Map();
  const blocks=[];
  for (const event of events) {
    if (event.type === 'tool/call') calls.set(event.data.toolUseId,{...event.data,seq:event.seq});
    if (event.type === 'tool/result' && !event.data.isError) {
      const call=calls.get(event.data.toolUseId);
      if (call?.name.includes('_gz_')) blocks.push({name:call.name,status:'completed',seq:call.seq,resultSeq:event.seq,argsPreview:JSON.stringify(call.args),resultPreview:event.data.content.filter(p => p.type === 'text').map(p => p.text).join('')});
    }
  }
  return blocks;
}
const blocks = realBlocks('runs/t09-changzhou-008/ledger.agnes.jsonl');

test('orientation crosscheck shows every returned group and full design totals', () => {
  const result={ok:true,version:1,specific_yield_kwh_kwp:{b:1200},differences:[],omitted:{},total_kwh:{b:13200},
    groups:[{group:[1,15,90],kw:5.5,per_kw:{b:1100}},{group:[2,25,270],kw:5.5,per_kw:{b:1300}}],
    group_offset:0,next_group_offset:null,total_groups:2};
  const card=cardData({name:'gz_crosscheck_yield',status:'completed',resultPreview:JSON.stringify(result)});
  assert.equal(card.fallback,false);
  assert.deepEqual(card.table.rows,[['1 / 15 / 90','b',1100],['2 / 25 / 270','b',1300]]);
  assert.ok(card.metrics.some(m => m.label === '全设计各链发电合计' && m.value.includes('13200')));
});
test.skip('actual T09 results render all six tool families and generic cards without guessed field names', () => {
  const seen=new Set();
  for (const block of blocks) {
    const card=cardData(block); assert.equal(card.fallback,false,block.name); seen.add(card.family);
    assert.ok(card.metrics.length || card.table?.rows.length);
    if (card.family === 'layout') assert.ok(!card.templateId && !card.geometry && !card.modules);
    if (card.tool === 'gz_edit_design') assert.equal(card.metrics.find(m => m.label === '修改原因').value,JSON.parse(block.argsPreview).reason);
  }
  assert.deepEqual([...seen].sort(),['analysis','compare','crosscheck','export','generic','layout','project']);
});

test('tool results truncated or semantically broken fall back completely to at most 20 raw lines', () => {
  for (const block of blocks) {
    const d=JSON.parse(block.resultPreview);
    for (const resultPreview of [block.resultPreview.slice(0,-1),'null','{}',JSON.stringify({...d,ok:false}),'x\n'.repeat(50)]) {
      const card=cardData({...block,resultPreview});
      assert.equal(card.fallback,true); assert.deepEqual(card.metrics,[]); assert.equal(card.table,undefined); assert.ok(card.raw.split('\n').length <= 20);
    }
  }
  const pending=cardData({name:'mcp_guangzhu_df14eb73_gz_analyze',status:'awaiting_approval'});
  assert.equal(pending.fallback,false); assert.ok(pending.warnings.includes('等待你在下方审批'));
});

test('empty and whitespace completed previews always show a nonempty fallback', () => {
  for (const resultPreview of ['', ' \n\t']) {
    const card=cardData({name:'gz_analyze',status:'completed',resultPreview});
    assert.equal(card.fallback,true); assert.ok(card.raw.trim());
  }
  assert.equal(cardData({name:'gz_analyze',status:'completed',resultPreview:'',summary:'原工具摘要'}).raw,'原工具摘要');
});

test.skip('edit capacity copies optional before/after fields while old ledgers stay truthful', () => {
  const original=blocks.find(b => b.name.endsWith('_gz_edit_design')), data=JSON.parse(original.resultPreview);
  const old=cardData(original); assert.equal(old.fallback,false);
  assert.equal(old.metrics.find(m => m.label==='装机变化'),undefined);
  const card=cardData({...original,resultPreview:JSON.stringify({...data,dc_kw_change:{before:218.9,after:211.2}})});
  assert.equal(card.metrics.find(m => m.label==='装机变化').value,'218.9 → 211.2 kW');
  assert.equal(card.metrics.find(m => m.label==='变化').value,data.summary);
});

test.skip('real long edit arguments clipped by AGH retain returned parent/reason and old incomplete previews say unknown', () => {
  const original=realBlocks('runs/t10-impossible-006/ledger.agnes.jsonl').find(b => b.seq===206);
  const args=JSON.parse(original.argsPreview), result=JSON.parse(original.resultPreview);
  const canonical=JSON.stringify(Object.fromEntries(Object.entries(args).sort(([a],[b]) => a.localeCompare(b))));
  assert.equal(args.ops[0].module_ids.length,245); assert.ok(canonical.length > 2048);
  const clipped={...original,argsPreview:canonical.slice(0,2048)};
  assert.throws(() => JSON.parse(clipped.argsPreview));
  const old=cardData(clipped);
  assert.equal(old.metrics.find(m => m.label==='版本').value,'未知父版本 → v2');
  assert.equal(old.metrics.find(m => m.label==='修改原因').value,'未知（参数预览不完整）');
  const returned={...result,parent_version:args.version,reason:args.reason};
  for (const argsPreview of [clipped.argsPreview,JSON.stringify({version:99,reason:'过时预览'})]) {
    const card=cardData({...original,argsPreview,resultPreview:JSON.stringify(returned)});
    assert.equal(card.metrics.find(m => m.label==='版本').value,'v1 → v2');
    assert.equal(card.metrics.find(m => m.label==='修改原因').value,'U03;E08');
    assert.equal(card.metrics.find(m => m.label==='装机变化').value,'154 → 19.25 kW');
    assert.equal(card.metrics.find(m => m.label==='变化').value,result.summary);
  }
});

test.skip('saved-false what-if shows actual recalculated cash, no accidental saved claim', () => {
  const original=blocks.find(b => b.name.endsWith('_gz_analyze')), data=JSON.parse(original.resultPreview);
  const card=cardData({...original,resultPreview:JSON.stringify({...data,what_if:{saved:false,payback_years:4.9,irr_pct:18.3,hard_failed:1,rules:[{id:'U04',status:'fail',value:4.9,limit:4}]}})});
  assert.equal(card.fallback,false); assert.ok(card.warnings.some(s => s.includes('试算，未保存')));
  assert.equal(card.metrics.find(m => m.label === '回本').value,'4.9 年');
  assert.equal(card.metrics.find(m => m.label === '硬性不通过').value,1);
  assert.deepEqual(card.table.rows,[['U04','不通过','4.9','4']]);
  const actual=realBlocks('runs/t09-followups-008/ledger.agnes.jsonl').find(b => JSON.parse(b.resultPreview).what_if);
  const real=cardData(actual); assert.equal(real.fallback,false);
  assert.equal(real.metrics.find(m => m.label === '回本').value,'4.418306 年');
  assert.deepEqual(real.table.rows[0],['U04','通过','4.418305827309669','6']);
});

test.skip('rule colors follow hard failure, advice failure, or pass without changing numbers', () => {
  const original=blocks.find(b => b.name.endsWith('_gz_analyze')), data=JSON.parse(original.resultPreview);
  for (const [hard,failed,tone] of [[1,[{id:'U03',name_zh:'预算',value:50,limit:40}],'danger'],[0,[{id:'E07',name_zh:'配比',value:.5,limit:1}],'warning'],[0,[],'success']]) {
    const result={...data,rules:{...data.rules,passed:13,total:22,hard_failed:hard,failed}};
    const card=cardData({...original,resultPreview:JSON.stringify(result)});
    assert.equal(card.metrics[0].value,'13/22'); assert.equal(card.metrics[0].tone,tone);
    assert.equal(card.metrics[1].value,hard); assert.equal(card.metrics[1].tone,hard ? 'danger' : 'success');
  }
  const result={...data,rules:{...data.rules,hard_failed:0,failed:[]},what_if:{saved:false,payback_years:4.9,irr_pct:18.3,hard_failed:1,rules:[]}};
  const card=cardData({...original,resultPreview:JSON.stringify(result)});
  assert.equal(card.metrics[0].label,'基准规则通过'); assert.equal(card.metrics[0].tone,'success');
  assert.equal(card.metrics[1].tone,'danger');
});
