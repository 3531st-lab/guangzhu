import test from 'node:test';
import assert from 'node:assert/strict';
import {diagnosticAction,diagnosticsMarkup} from '../../desktop/web/design-diagnostics.js';

function example() {
  return {version:4,editable:true,locked_modules:['B'],design:{version:4,modules:[{id:'A'},{id:'B'},{id:'C'}]},
    diagnostics:{schema:'guangzhu.design-diagnostics/1',version:4,available:true,issues:[
      {key:'S01:0',rule_id:'S01',title:'单块遮挡',level:'hard',status:'fail',value:12,limit:8,unit:'%',
        evidence:'逐板真实计算',hint:'检查设备位置',source_ref:'示意阈值8%',located:true,location_reason:'',location_note:'',
        module_ids:['A','B'],plane_ids:[],string_ids:[],locked_module_ids:['B'],
        details:[{id:'A',total_loss_pct:9,main_cause:'hvac'},{id:'B',total_loss_pct:12,main_cause:'hvac'}],
        fix:{label:'预览移除1块',ops:[{op:'remove_modules',module_ids:['A']}],reason:'依据v4逐板遮挡',
          retained_locked_ids:['B'],note:'保留已锁定组件；不保证通过。'}}]}};
}

test('locate returns view intent with copied IDs and never changes edit selection or saves',()=>{
  const result=example(), before=structuredClone(result);
  const action=diagnosticAction(result,'S01:0','locate');
  assert.deepEqual(action,{kind:'locate',key:'S01:0',version:4,module_ids:['A','B'],plane_ids:[],string_ids:[],locked_module_ids:['B'],mode:'heat'});
  action.module_ids.pop();
  assert.deepEqual(result,before);
});

test('edit selects only unlocked objects and fix is a detailed preview with explicit IDs',()=>{
  const result=example();
  assert.deepEqual(diagnosticAction(result,'S01:0','edit').module_ids,['A']);
  const fix=diagnosticAction(result,'S01:0','fix');
  assert.deepEqual(fix,{kind:'preview',key:'S01:0',version:4,ops:[{op:'remove_modules',module_ids:['A']}],
    reason:'依据v4逐板遮挡',detailed:true,retained_locked_ids:['B']});
  fix.ops[0].module_ids.push('C');
  assert.deepEqual(result.diagnostics.issues[0].fix.ops[0].module_ids,['A']);
});

test('read-only archive may locate its own version but cannot edit or repair',()=>{
  const result=example();result.editable=false;
  assert.equal(diagnosticAction(result,'S01:0','locate').kind,'locate');
  for (const action of ['edit','fix']) assert.throws(()=>diagnosticAction(result,'S01:0',action),/只读/);
  const html=diagnosticsMarkup(result);
  assert.match(html,/归档记录只读/);
  assert.match(html,/data-diagnostic-action="fix"[^>]*disabled/);
});

test('stale diagnostic or design version removes actions instead of using another version',()=>{
  for (const property of ['diagnostics','design']) {
    const result=example();result[property].version=3;
    assert.throws(()=>diagnosticAction(result,'S01:0','locate'),/版本不一致/);
    const html=diagnosticsMarkup(result);
    assert.match(html,/版本不一致/);assert.doesNotMatch(html,/data-diagnostic-action/);
  }
});

test('late lock information blocks a previously available repair',()=>{
  const result=example();result.locked_modules.push('A');
  assert.throws(()=>diagnosticAction(result,'S01:0','fix'),/全部已锁定/);
  assert.throws(()=>diagnosticAction(result,'S01:0','edit'),/全部已锁定/);
  assert.equal(diagnosticAction(result,'S01:0','locate').kind,'locate');
});

test('repair cannot inject unknown, locked, duplicate or extra operation targets',()=>{
  for (const ids of [['C'],['B'],['A','A'],['A','C']]) {
    const result=example();result.diagnostics.issues[0].fix.ops[0].module_ids=ids;
    assert.throws(()=>diagnosticAction(result,'S01:0','fix'),/一致的修复预览/);
  }
  const result=example();result.diagnostics.issues[0].fix.ops.push({op:'unlock_modules',module_ids:['B']});
  assert.throws(()=>diagnosticAction(result,'S01:0','fix'),/一致的修复预览/);
});

test('missing object evidence keeps rule explanation and has no actionable location',()=>{
  const result=example(), issue=result.diagnostics.issues[0];
  Object.assign(issue,{located:false,module_ids:[],fix:null,location_reason:'当前版本缺少逐板分析'});
  assert.throws(()=>diagnosticAction(result,issue.key,'locate'),/缺少逐板分析/);
  const html=diagnosticsMarkup(result);
  assert.match(html,/当前版本缺少逐板分析/);assert.match(html,/逐板真实计算/);
  assert.doesNotMatch(html,/data-diagnostic-action/);
});

test('markup escapes all evidence, labels and source text',()=>{
  const result=example(), issue=result.diagnostics.issues[0];
  Object.assign(issue,{title:'<img src=x onerror=alert(1)>',evidence:'<script>bad()</script>',source_ref:'x" onclick="bad()',hint:'A & B'});
  issue.fix.label='<b>not markup</b>';
  const html=diagnosticsMarkup(result,{selectedKey:'S01:0'});
  assert.doesNotMatch(html,/<img|<script>|<b>not markup/);
  assert.match(html,/&lt;img/);assert.match(html,/A &amp; B/);assert.match(html,/dd-selected/);
  assert.match(html,/不保证通过/);
});

test('no failures does not claim independent audit or completed delivery',()=>{
  const result=example();result.diagnostics.issues=[];result.diagnostics.reason='没有未通过项；不代表已完成独立审核。';
  const html=diagnosticsMarkup(result);
  assert.match(html,/不代表已完成独立审核/);assert.doesNotMatch(html,/data-diagnostic-action/);
});
