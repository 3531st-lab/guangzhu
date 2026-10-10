import test from 'node:test';
import assert from 'node:assert/strict';
import * as data from '../../desktop/web/data.js';
import {computeSteps} from '../../desktop/web/steps.js';
// Units in the header are <small>; an inherited deletion reason would show up as <small> inside the rows.
const rows = html => html.split('<tbody>')[1] ?? '';

const row = (name, version, changes = {}) => ({name, version, dc_kw:100, payback_years:4, irr_pct:15,
  hard_pass:true, violated_requirements:[], ...changes});
const comparison = () => ({ok:true, base_version:3, current:row('当前方案', 3), options:[row('多装', 6), row('最快回本', 9), row('折中', 12)],
  recommended:{max_capacity:{version:6, why:'装机最多'}, fast_payback:{version:9, why:'回本最短'}, balanced:{version:3, why:'年发电最多'}}});
const tool = (name, seq, result, args = {}) => ({kind:'tool', name, seq, result_seq:seq + 1, session:'design', tool_use_id:'id-' + seq,
  status:'completed', isError:false, args_json:args, result_json:result, result:JSON.stringify(result)});
const versions = [{version:12,parent_version:11,reason:'折中：自动修正 E08'},
  {version:11,parent_version:3,reason:'折中：按 U03 删除 982 块',statistics:{module_count:1250}},
  {version:3,parent_version:null,reason:'多装：按 U03 删除 8 块',statistics:{module_count:1250}}];

function table(compare, selected, prefer = 'balanced') {
  assert.equal(typeof data.comparisonTable, 'function', 'results and step 7 must share one real HTML table helper');
  return data.comparisonTable(compare, {selected_version:selected, versions, run:{prefer}});
}

test('four actual rows current first selected/recommended marks and ancestor deletion reason', () => {
  const html = table(comparison(), 3);
  assert.equal((html.match(/<tbody>[\s\S]*<\/tbody>/)?.[0].match(/<tr/g) ?? []).length, 4);
  assert.ok(html.indexOf('当前方案') < html.indexOf('多装'));
  assert.equal((html.match(/选定/g) ?? []).length, 1);
  assert.equal((html.match(/推荐/g) ?? []).length, 0);
  assert.ok(html.includes('预算删板后1,250块'));
  assert.ok(!html.includes('多装：') && !html.includes('E08') && !html.includes('S01') && !html.includes('U03'));
  assert.ok(!html.match(/<tr[^>]*><td>当前方案[^<]*(?:<br><small>)/));
  const other = table(comparison(), 12, 'fast_payback');
  assert.equal((other.match(/推荐/g) ?? []).length, 1);
  assert.ok(other.includes('最快回本 v9 推荐'));
});

test('Chinese unmet requirements hard-failure fallback and escaped reasons', () => {
  const compare = comparison();
  compare.options[0].violated_requirements = ['U03', 'U02', 'G03'];
  compare.options[1].hard_pass = false;
  const html = table(compare, null);
  for (const phrase of ['超预算', '装机超上限', '通道不够', '硬性规则未过']) assert.ok(html.includes(phrase));
  versions[1].reason += '<script>oops</script>';
  assert.ok(!table(compare, null).includes('<script>'));
  versions[1].reason = '折中：按 U03 删除 982 块';
});

test('legacy archives retain three rows without exceptions', () => {
  const html = table({options:comparison().options}, 12);
  assert.equal((html.match(/<tbody>[\s\S]*<\/tbody>/)?.[0].match(/<tr/g) ?? []).length, 3);
  assert.ok(!html.includes('当前方案'));
});

test('current and legacy candidates cannot inherit base or ordinary parent budget edits even without base_version', () => {
  const inherited = [{version:6,parent_version:3,reason:'多装'},
    {version:3,parent_version:2,reason:'E08,S01,U03',statistics:{module_count:1250}},
    {version:2,parent_version:3,reason:'初稿'}];
  for (const base_version of [3, undefined]) {
    const compare = {...comparison(), base_version};
    assert.ok(!rows(data.comparisonTable(compare, {versions:inherited})).includes('<small>'));
    delete compare.current;
    assert.ok(!rows(data.comparisonTable(compare, {versions:inherited})).includes('<small>'));
  }
});

test('own deletion counts are plain Chinese; missing metadata and ancestor cycles remain safe', () => {
  for (const [code,label] of [['U03','预算'], ['U02','装机上限']]) {
    const own = [{version:6,parent_version:5,reason:'多装：自动修正 E08'},
      {version:5,parent_version:6,reason:`多装：按 ${code} 删除 982 块`,statistics:{module_count:1250}}];
    for (const base_version of [3, undefined]) {
      assert.ok(data.comparisonTable({...comparison(),base_version}, {versions:own}).includes(`${label}删板后1,250块`));
    }
    delete own[1].statistics;
    assert.ok(!rows(data.comparisonTable(comparison(), {versions:own})).includes('<small>'));
  }
});

test('step 7 uses formal pending/wait comparison preference and later selected evidence', () => {
  const pending = tool('gz_compare_options', 1, {ok:true,pending:true,job_id:'J',tool:'gz_compare_options'}, {base_version:3});
  const wait = tool('gz_wait', 3, {...comparison(),job_id:'J',tool:'gz_compare_options'}, {job_id:'J'});
  let computed = computeSteps([pending], {run:{prefer:'fast_payback'}});
  assert.equal(computed.steps[6].state, 'running');
  assert.ok(!computed.steps[6].comparison);
  computed = computeSteps([pending, wait, tool('gz_analyze', 5, {ok:true,version:3,rules:{hard_failed:0}})],
    {run:{prefer:'fast_payback'}, versions});
  assert.equal(computed.steps[6].state, 'completed');
  assert.ok(computed.steps[6].comparison.includes('当前方案 v3 选定'));
  assert.ok(computed.steps[6].comparison.includes('最快回本 v9 推荐'));
  assert.ok(computed.steps[6].detail.includes('回本最短'));
  assert.equal(computeSteps([], {run:{compare:false}}).steps[6].state, 'skipped');
});

test('Codex E3: options open their own version and show yield, shading, requirement margins and why one is picked', () => {
  const compare = comparison();
  Object.assign(compare.options[0], {annual_kwh:283791.6533, avg_loss_pct:0.67, capex_cny:666666, payback_years:6.3, dc_kw:257.4});
  const html = data.comparisonTable(compare, {selected_version:3, version:6, versions, run:{prefer:'balanced'},
    project:{requirements:{structured:{payback_years_max:6, budget_cny_max:600000, capacity_kw_min:200}}}});
  assert.equal((html.match(/class="pick-option" data-version="\d+"/g) ?? []).length, 4);
  assert.match(html, /data-version="6" aria-pressed="true"/);
  assert.ok(html.includes('>28.4<') && html.includes('原值 283791.6533 kWh') && html.includes('0.7') && html.includes('年发电 <small>万kWh</small>') && html.includes('遮挡 <small>%</small>'));
  assert.ok(html.includes('回本超出 0.3 年 · 预算超出 6.7 万元 · 装机下限余 57.4 kW'));
  assert.ok(html.includes('回本余 2 年') && html.includes('按「折中」选 v3：年发电最多'));
  assert.equal((html.match(/推荐/g) ?? []).length, 0);
});

test('Codex E2: a saved change names its rules in Chinese and shows what it did against its parent', () => {
  const parent = {version:1, statistics:{module_count:390, dc_kw:214.5}, metrics:{annual_kwh:247624.2, payback_years:4.0546}};
  const child = {version:2, parent_version:1, reason:'按 S01 删除 14 块，再修 E08', statistics:{module_count:376, dc_kw:206.8},
    metrics:{annual_kwh:240169.7, payback_years:4.0283}};
  const summary = data.versionSummary(child, parent, {S01:'单块遮挡不超阈值', E08:'全部组件接入组串'});
  assert.equal(summary.reason, '按单块遮挡不超阈值（S01）删除 14 块，再修全部组件接入组串（E08）');
  const reasonOf = (reason, names) => data.versionSummary({...child, reason}, parent, names).reason;
  assert.equal(reasonOf('E08,S01, U03', {E08:'全部组件接入组串', S01:'单块遮挡不超阈值', U03:'造价不超预算'}),
    '全部组件接入组串（E08）、单块遮挡不超阈值（S01）、造价不超预算（U03）');
  assert.equal(reasonOf('E08,X99 按 S01, U03 删', {E08:'组串', S01:'遮挡'}), '组串（E08）,X99 按 遮挡（S01）, U03 删');
  assert.equal(reasonOf('按 S01 删除 1,234 块', {}), '按 S01 删除 1,234 块');
  assert.deepEqual(summary.metrics.map(m => [m.label, Math.round(m.value * 100) / 100]),
    [['组件变化', -14], ['装机变化', -7.7], ['基准年发电变化', -7454.5], ['回本变化', -0.03]]);
  assert.deepEqual(data.versionSummary({...child, metrics:null}, parent).metrics.map(m => m.label), ['组件变化', '装机变化']);
  assert.deepEqual(data.versionSummary(parent).metrics.map(m => m.label), ['组件', '装机', '排距']);
});

test('Codex E3: a requirement the owner never gave is not treated as zero', () => {
  const compare = comparison();
  compare.options[0].capex_cny = 666666;
  const html = data.comparisonTable(compare, {project:{requirements:{structured:{budget_cny_max:null, payback_years_max:6}}}});
  assert.ok(!html.includes('预算') && html.includes('回本余 2 年'));
});
