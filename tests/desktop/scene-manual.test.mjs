import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeSceneForDisplay} from '../../desktop/web/scene.js';
import {panelMatrix} from '../../desktop/web/scene-data.js';

const project={roof:{type:'flat',height_m:5,outline:[[0,0],[24,0],[24,16],[0,16]],parapet_height_m:0}};
const panel=(id,x,y)=>({id,center:[x,y,.6],corners:[[x-1,y-.5,.3],[x+1,y-.5,.3],[x+1,y+.5,.9],[x-1,y+.5,.9]],tilt:31,azimuth:180,orientation:'landscape'});
const translate=(module,dx,dy)=>({...module,center:module.center.map((v,i)=>v+(i===0?dx:i===1?dy:0)),
  corners:module.corners.map(p=>p.map((v,i)=>v+(i===0?dx:i===1?dy:0)))});
const rotate=(module,angle,normal=[0,0,1])=>({...module,corners:module.corners.map(point=>{
  const v=point.map((value,i)=>value-module.center[i]),cos=Math.cos(angle),sin=Math.sin(angle);
  const dot=v.reduce((sum,value,i)=>sum+value*normal[i],0);
  const cross=[normal[1]*v[2]-normal[2]*v[1],normal[2]*v[0]-normal[0]*v[2],normal[0]*v[1]-normal[1]*v[0]];
  return v.map((value,i)=>module.center[i]+value*cos+cross[i]*sin+normal[i]*dot*(1-cos));
})});
const parent={version:4,modules:[panel('move',3,4),panel('rotate',10,6),panel('remove',18,4),panel('keep',18,10)]};
const design={version:5,parent_version:4,modules:[translate(parent.modules[0],2,1),rotate(parent.modules[1],.7),parent.modules[3],panel('add',10,11)]};

test('manual scene differences retain both exact before and after geometry without mutating either version',()=>{
  const input={project,design,parent_design:parent},original=JSON.stringify(input),data=normalizeSceneForDisplay(input);
  assert.deepEqual([...data.changed],['move','rotate']);assert.deepEqual([...data.added],['add']);
  assert.deepEqual(data.removed.map(m=>m.id),['remove']);
  for(const module of data.previousPositions) assert.deepEqual(module.points,parent.modules.find(m=>m.id===module.id).corners.map(data.world));
  assert.equal(JSON.stringify(input),original);
  const unrelated=normalizeSceneForDisplay({...input,parent_design:{...parent,version:2}});
  assert.equal(unrelated.changed.size,0);assert.equal(unrelated.added.size,0);assert.equal(unrelated.removed.length,0);
});

test('preview never borrows analysis even when its version number matches; cancel restores saved analyses',()=>{
  const shading={version:4,modules:[{id:'keep',total_loss_pct:8}]};
  const electrical={version:4,strings:[{id:'S1',module_ids:['keep']}]},wind={version:4,modules:[{id:'keep',zone:'edge'}]};
  const input={project,design:{...design,version:4},parent_design:parent,shading,electrical,wind,edit_preview:true};
  const before=JSON.stringify(input),data=normalizeSceneForDisplay(input);
  assert.ok(data.modules.every(m=>m.loss===null&&m.string===null&&m.wind===null));
  assert.equal(data.electrical,null);assert.equal(data.wind,null);assert.equal(data.shading,null);
  assert.deepEqual([...data.changed],['move','rotate']);assert.equal(data.added.size,1);assert.equal(data.removed.length,1);
  assert.equal(JSON.stringify(input),before);
  const saved=normalizeSceneForDisplay({...input,design:parent,parent_design:null,edit_preview:false});
  const kept=saved.modules.find(m=>m.id==='keep');
  assert.equal(kept.loss,8);assert.equal(kept.string.id,'S1');assert.equal(kept.wind.zone,'edge');
  assert.equal(saved.changed.size,0);assert.equal(saved.previousPositions.length,0);
});

test('panel boxes follow arbitrary rigid yaw and in-plane rotation through all four true 3D corners',()=>{
  const original=panel('slope',10,6),length=Math.hypot(0,-.6,1),normal=[0,-.6/length,1/length];
  for(const module of [translate(original,3,-2),rotate(original,.73),rotate(original,1.13,normal)]) {
    const data=normalizeSceneForDisplay({project,design:{version:1,modules:[module]}}),view=data.modules[0],matrix=panelMatrix(view);
    for(const [index,[x,z]] of [[-.5,.5],[.5,.5],[.5,-.5],[-.5,-.5]].entries()) {
      for(let axis=0;axis<3;axis++) {
        const actual=matrix[axis]*x+matrix[8+axis]*z+matrix[12+axis];
        assert.ok(Math.abs(actual-view.points[index][axis])<1e-10);
      }
    }
  }
});

test('unchanged corners ignore sub-micrometre normalization noise and metadata-only changes',()=>{
  const unchanged={...parent,version:5,parent_version:4,modules:parent.modules.map(m=>({...m,phase:2}))};
  unchanged.modules[0]=translate(unchanged.modules[0],1e-9,0);
  const data=normalizeSceneForDisplay({project,design:unchanged,parent_design:parent});
  assert.equal(data.changed.size,0);assert.equal(data.previousPositions.length,0);
});
