import test from 'node:test';
import assert from 'node:assert/strict';
import {newEditState,editOperation,editDifference,designEditPlan,designEditMarkup,performEdit,invalidateEdit,moduleEditingOptions,moduleEditingUnavailable} from '../../desktop/web/design-edit-ui.js';

const panel=(id,x=3)=>({id,center:[x+1,4,1],corners:[[x,3,1],[x+2,3,1],[x+2,5,1],[x,5,1]],orientation:'portrait'});
function result() {
  return {project_id:'manual-fixture',version:1,project:{roof:{type:'flat',outline:[[0,0],[30,0],[30,20],[0,20]],keepouts:[]}},
    design:{modules:[panel('M001'),panel('M002',10)],params:{orientation:'portrait',layout:'south',rows_per_rack:1,
      edge_setback_m:.5,walkway_every_n_rows:0,walkway_width_m:1},statistics:{dc_kw:1.1}}};
}
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const candidate=(r,label)=>({design:{...r.design,modules:[panel(label)]},fingerprint:label,summary:label,changes:{locked:[]}});

test('manual operations use explicit units, centered placements and per-panel clockwise angles',()=>{
  const r=result(),s=newEditState(r);s.add={x:7.25,y:8.5,orientation:'landscape',rotation:37,plane:''};
  assert.deepEqual(editOperation('add',s,r),[{op:'add_modules',placements:[{center:[7.25,8.5],orientation:'landscape',rotation_deg:37}]}]);
  s.selected=new Set(['M002','M001']);s.move={dx:-1.2,dy:.75};s.rotate.angle=-23;
  assert.deepEqual(editOperation('move',s,r),[{op:'move_modules',module_ids:['M002','M001'],dx_m:-1.2,dy_m:.75}]);
  assert.deepEqual(editOperation('rotate',s,r),[{op:'rotate_modules',module_ids:['M002','M001'],angle_deg:-23}]);
  for(const value of [null,NaN,Infinity]) {s.add.x=value;assert.throws(()=>editOperation('add',s,r),/中心/);}
  s.move={dx:0,dy:0};assert.throws(()=>editOperation('move',s,r),/不能同时/);
  for(const angle of [0,360,-360,361,NaN]) {s.rotate.angle=angle;assert.throws(()=>editOperation('rotate',s,r),/旋转角/);}
});

test('pitched placement requires a usable selected plane and manual unsupported modes stay disabled',()=>{
  const r=result(),s=newEditState(r);r.project.roof={...r.project.roof,type:'pitched',planes:[{id:1,material:'metal'},{id:2,material:'glass'},{id:3,material:'metal'}]};
  r.design.params.plane_ids=[1,2];s.add={x:7,y:8,orientation:'portrait',rotation:0,plane:''};
  for(const plane of ['',2,3]) {s.add.plane=plane;assert.throws(()=>editOperation('add',s,r),/可安装/);}
  s.add.plane='1';assert.equal(editOperation('add',s,r)[0].placements[0].plane_id,1);
  r.project.roof.type='ground';assert.throws(()=>editOperation('add',s,r),/空地和车棚/);
  r.project.roof.type='flat';r.design.params.layout='ew';assert.throws(()=>editOperation('add',s,r),/东西向/);
  r.design.params.layout='south';r.design.params.rows_per_rack=2;assert.throws(()=>editOperation('add',s,r),/一架多排/);
});

test('module, plane and resolved region locks reject whole selected batches before preview',()=>{
  const r=result(),s=newEditState(r);r.design.modules.push(panel('P3-M001',20));
  r.design.locked_module_ids=['M001'];r.design.locked_plane_ids=[3];r.locked_modules=['M002'];
  for(const id of ['M001','M002','P3-M001']) {
    s.selected=new Set([id]);s.move.dx=1;
    for(const action of ['move','rotate','remove']) assert.throws(()=>editOperation(action,s,r),/已锁定/);
  }
});

test('plan compares stable IDs by corners and displays both saved and locally added exclusion zones',()=>{
  const r=result(),s=newEditState(r);r.project.roof.keepouts=[{id:'roof-no-go',polygon:[[1,1],[2,1],[2,2]]}];
  r.design.added_keepouts=[{id:'manual-no-go',label:'新增检修区',polygon:[[5,6],[8,6],[8,8]]}];
  s.preview={design:{...r.design,modules:[panel('M001',4),panel('M003',14)]}};s.previewAction='move';
  assert.deepEqual(editDifference(r,s),{added:['M003'],removed:['M002'],changed:['M001']});
  const html=designEditPlan(r,s);
  assert.match(html,/data-edit-before="M001"/);assert.match(html,/data-edit-before="M002"/);
  assert.match(html,/data-edit-change="moved"/);assert.match(html,/data-edit-change="added"/);
  assert.match(html,/新增检修区/);assert.match(html,/roof-no-go/);assert.equal((html.match(/class="de-keepout"/g)??[]).length,2);
});

test('detailed preview renders shading differences without inventing absent values',()=>{
  const r=result(),s=newEditState(r),metrics={annual_kwh:100,capex_cny:200,payback_years:3,hard_failed:0,failed:[],shading:{avg_loss_pct:1,max_loss_pct:2,modules_over_threshold:0}};
  s.preview={...candidate(r,'M001'),impact:{available:true,before:metrics,after:metrics,affected_strings:[],note:'fixed fixture',
    shading_changes:[{id:'M003',before_loss_pct:null,after_loss_pct:1.5,delta_loss_pct:null}]}};
  const html=designEditMarkup(r,s);assert.match(html,/平均遮挡损失/);assert.match(html,/逐组件遮挡变化/);
  assert.match(html,/<td>M003<\/td><td>—<\/td><td>1.5<\/td><td>—<\/td>/);
});

test('failed engineering rules retain numeric ranges and actionable hints',()=>{
  const r=result(),s=newEditState(r),metrics={failed:[],shading:{}};
  s.preview={...candidate(r,'M001'),impact:{available:true,before:metrics,after:{...metrics,failed:[
    {id:'E07',name_zh:'容配比',value:.07,limit:[1,1.3]},
    {id:'G03',name_zh:'连续通道',value:null,limit:null,hint_zh:'请核对实际连续通道 <1m>'}]},affected_strings:[]}};
  const html=designEditMarkup(r,s);assert.match(html,/E07 · 容配比：0.07 \/ \[1, 1.3\]/);
  assert.match(html,/请核对实际连续通道 &lt;1m&gt;/);
});

test('cancel and superseding inputs invalidate late successful and failed preview responses',async()=>{
  const r=result(),s=newEditState(r),first=deferred(),second=deferred(),scene=[];let calls=0;
  const context={api:()=>++calls===1?first.promise:second.promise,redraw(){},scene:value=>scene.push(value),current:()=>true};
  s.add={x:7,y:8,orientation:'portrait',rotation:0};
  const one=performEdit('add',r,s,context);assert.equal(s.busy,true);
  await performEdit('cancel',r,s,context);assert.equal(s.busy,false);
  s.add.x=9;const two=performEdit('add',r,s,context);const wanted=candidate(r,'newest');
  second.resolve(wanted);await two;assert.equal(s.preview,wanted);
  first.reject(new Error('old request failed'));await one;
  assert.equal(s.preview,wanted);assert.equal(s.error,'');assert.equal(scene.at(-1),wanted.design);
  invalidateEdit(s);assert.equal(s.preview,null);assert.equal(s.request,null);
});

test('save holds mutations, uses the preview fingerprint and navigates only the owning result',async()=>{
  const r=result(),s=newEditState(r),saved=deferred(),requests=[],navigated=[];
  s.preview=candidate(r,'fingerprint-A');s.request={version:1,ops:[{op:'lock_modules',module_ids:['M001']}],reason:'reviewed'};
  const context={api:(path,request)=>{requests.push({path,request});return saved.promise;},redraw(){},scene(){},notice(){},navigate:version=>navigated.push(version),current:()=>true};
  const work=performEdit('apply',r,s,context);assert.equal(s.pendingKind,'apply');
  await performEdit('cancel',r,s,context);await performEdit('select-all',r,s,context);await performEdit('apply',r,s,context);
  assert.equal(s.selected.size,0);assert.equal(requests.length,1);assert.equal(requests[0].request.fingerprint,'fingerprint-A');
  saved.resolve({version:2});await work;assert.deepEqual(navigated,[2]);assert.equal(s.pendingKind,null);
});

test('3D tools require authoritative dimensions, retain locks and suspend during server preview',()=>{
  const r=result(),s=newEditState(r);s.toolMode='move';s.selected.add('M001');
  assert.equal(moduleEditingOptions(r,s).enabled,false);assert.match(moduleEditingUnavailable(r,s),/精确组件尺寸/);
  r.scene={module_transform_spec:{available:true,length_m:2.2,width_m:1.1,gap_m:.03,lower_edge_m:.3}};
  r.design.locked_module_ids=['M002'];
  assert.deepEqual(moduleEditingOptions(r,s),{enabled:true,mode:'move',selectedIds:['M001'],lockedIds:['M002'],
    snap:{enabled:true,gridM:.1,angleDeg:15,align:true},busy:false});
  s.preview=candidate(r,'M001');assert.equal(moduleEditingOptions(r,s).busy,true);
  assert.equal(moduleEditingOptions(r,s,false).enabled,false);
  s.snap.gridM=0;assert.equal(moduleEditingOptions(r,s).enabled,false);assert.match(moduleEditingUnavailable(r,s),/网格间距/);
  s.snap.enabled=false;assert.equal(moduleEditingOptions(r,s).enabled,true);
});

test('tool changes cancel gestures and invalidate in-flight candidates without changing selection',async()=>{
  const r=result(),s=newEditState(r),pending=deferred();r.scene={module_transform_spec:{available:true}};
  s.selected.add('M001');s.move.dx=.5;let cancels=0;
  const context={api:()=>pending.promise,redraw(){},scene(){},cancelGesture(){cancels++;}};
  const work=performEdit('move',r,s,context);
  await performEdit('tool:rotate',r,s,context);
  assert.equal(s.toolMode,'rotate');assert.equal(s.manualMode,'rotate');assert.deepEqual([...s.selected],['M001']);
  assert.equal(s.busy,false);assert.ok(cancels>=2);
  pending.resolve(candidate(r,'late'));await work;assert.equal(s.preview,null);
});

test('diagnostic operations preview exactly their version and retain a fingerprint for explicit save',async()=>{
  const r=result(),s=newEditState(r),requests=[],request={version:1,ops:[{op:'remove_modules',module_ids:['M001']}],reason:'逐板遮挡证据',detailed:true};
  const context={api:async(path,body)=>{requests.push({path,body});return candidate(r,'diagnostic');},redraw(){},scene(){}};
  await performEdit('diagnostic-fix',r,s,context,request);
  assert.equal(requests.length,1);assert.match(requests[0].path,/preview$/);assert.deepEqual(requests[0].body,request);
  request.ops[0].module_ids.push('M002');assert.deepEqual(s.request.ops[0].module_ids,['M001']);
  await assert.rejects(performEdit('diagnostic-fix',r,newEditState(r),context,{...request,version:0}),/版本不一致/);
});
