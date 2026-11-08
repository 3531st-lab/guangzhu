import test from 'node:test';
import assert from 'node:assert/strict';
import {evidenceMarkup,evidenceDownload} from '../../desktop/web/design-evidence.js';

const packet=()=>({version:4,evidence:{schema:'guangzhu.design-evidence/1',available:true,project_id:'demo',version:4,
  model:{modules:0,parent_version:3},assumptions:{name:'<img src=x onerror=alert(1)>',load_verified:false},
  analysis:{status:'recorded',elapsed_seconds:0,input_binding:'unrecorded'},rules:{status:'fail',hard_failed:1,applicable:5},
  review:{status:'missing',count:0},export:{status:'missing',count:0},sources:[{path:'designs/v4.json',integrity:'recorded',sha256:'a'.repeat(64)}],
  usage:{note:'原生会话',sessions:[{session_id:'s',model_requests:0,elapsed_seconds:null,tokens:{input:0,output:null},costs:[],billing_complete:false}]}}});

test('evidence distinguishes actual zero, unknown usage and unsupported input binding',()=>{
  const html=evidenceMarkup(packet());
  assert.match(html,/0 块组件/);assert.match(html,/计算耗时：0 秒/);assert.match(html,/0 \/ 未记录/);
  assert.match(html,/历史记录缺少完整输入签名/);assert.match(html,/费用记录不完整/);
  assert.doesNotMatch(html,/<img/);assert.match(html,/&lt;img/);
});
test('a packet from another version cannot render or download as current evidence',()=>{
  const result=packet();result.version=5;
  assert.match(evidenceMarkup(result),/尚无可核对/);
  assert.throws(()=>evidenceDownload(result),/当前版本/);
});
test('download preserves full hashes, failed state and null fields without mutating source',()=>{
  const result=packet(),original=structuredClone(result),file=evidenceDownload(result);
  assert.equal(file.filename,'demo-v4-evidence.json');assert.equal(file.mime,'application/json;charset=utf-8');
  assert.deepEqual(JSON.parse(file.text),result.evidence);assert.deepEqual(result,original);
  assert.equal(JSON.parse(file.text).sources[0].sha256.length,64);
});
