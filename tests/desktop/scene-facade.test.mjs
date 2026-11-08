import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {createFacade,planFacade} from '../../desktop/web/scene-facade.js';
import {applyFacadePreset,facadePresets} from '../../desktop/web/facade-editor.js';
import {normalizeScene} from '../../desktop/web/scene-data.js';

const factory = (extra={}) => ({type:'flat',outline:[[0,0],[60,0],[60,30],[0,30]],height_m:9,...extra});
const overlaps = (a,b) => a.segment===b.segment && a.x<b.x+b.width && b.x<a.x+a.width && a.z<b.z+b.height && b.z<a.z+a.height;
function checkPlacement(plan) {
  for(const o of [...plan.openings,...plan.windows]) {
    const s=plan.segments[o.segment];
    assert.ok(o.x>=0 && o.x+o.width<=s.length);
    const height=x=>s.heights[0]+(s.heights[1]-s.heights[0])*x/s.length;
    assert.ok(o.z>=0 && o.z+o.height<Math.min(height(o.x),height(o.x+o.width)));
  }
  const openings=[...plan.openings,...plan.windows];
  assert.ok(openings.every((a,i)=>openings.slice(i+1).every(b=>!overlaps(a,b))));
}

test('legacy factory immediately receives real exterior details without changing source data',()=>{
  const roof=factory(),before=JSON.stringify(roof),plan=planFacade(roof);
  assert.equal(plan.counts.front_edge,0);
  assert.equal(plan.counts.doors,2);
  assert.equal(plan.counts.loading_docks,1);
  assert.equal(plan.counts.personnel_doors,1);
  assert.equal(plan.counts.canopies,3);
  assert.ok(plan.counts.windows>20);
  assert.equal(plan.counts.segments,4);
  checkPlacement(plan);
  assert.equal(JSON.stringify(roof),before);
});

test('disabled facade, ground and carport produce no decorative geometry',()=>{
  for(const roof of [factory({facade:{enabled:false}}),factory({type:'ground'}),factory({type:'carport'})]) {
    const plan=planFacade(roof);
    assert.equal(plan.counts.enabled,false);
    assert.deepEqual(plan.segments,[]);
    assert.deepEqual(plan.openings,[]);
  }
});

test('explicit zero-based front edge and two window rows are respected',()=>{
  const plan=planFacade(factory({height_m:12,facade:{front_edge:2,window_rows:2,columns:false}}));
  assert.equal(plan.counts.front_edge,2);
  assert.equal(plan.counts.columns,0);
  assert.ok(plan.openings.every(o=>plan.segments[o.segment].edge===2));
  assert.ok(new Set(plan.windows.map(w=>w.z)).size>=2);
  checkPlacement(plan);
});

test('short low walls adapt openings and skip windows that cannot fit',()=>{
  const plan=planFacade(factory({outline:[[0,0],[3,0],[3,2],[0,2]],height_m:2.5}));
  assert.equal(plan.counts.windows,0);
  assert.equal(plan.counts.doors,0);
  assert.equal(plan.counts.loading_docks,0);
  checkPlacement(plan);
});

test('the full validated door width range including one metre remains renderable',()=>{
  for(const door_width_m of [1,1.1,4,8]) {
    const plan=planFacade(factory({facade:{door_width_m}}));
    assert.equal(plan.counts.doors,2);
    assert.equal(plan.counts.loading_docks,1);
    assert.equal(plan.counts.personnel_doors,1);
    checkPlacement(plan);
  }
});

test('metal wall tops follow the actual single slope',()=>{
  const roof=factory({type:'metal',slope_deg:12,slope_azimuth_deg:180}),data=normalizeScene({project:{roof},design:{version:1,modules:[]}});
  const plan=planFacade(roof,null,data.elevation);
  assert.ok(plan.segments.some(s=>Math.abs(s.heights[0]-s.heights[1])>1));
  checkPlacement(plan);
});

test('high and low compound boundary segments stay separate; internal step walls are excluded',()=>{
  const roof=factory({type:'pitched',height_m:5,outline:[[0,0],[30,0],[30,10],[0,10]],facade:{front_edge:0}});
  const boundary=[[0,0,4],[20,0,4],[20,0,0],[30,0,0],[30,10,0],[20,10,0],[20,10,4],[0,10,4],[0,0,4]];
  const geometry={boundary,step_walls:[[[20,0,0],[20,10,0],[20,10,4],[20,0,4]]]};
  const plan=planFacade(roof,geometry);
  assert.equal(plan.segments.length,6);
  assert.ok(plan.segments.every(s=>s.edge!==undefined && (s.a[0]!==20 || s.b[0]!==20)));
  assert.deepEqual(plan.segments.filter(s=>s.edge===0).map(s=>s.heights),[[9,9],[5,5]]);
  checkPlacement(plan);
});

test('gable ends retain ridge breakpoints, including rotated and clockwise outlines',()=>{
  const rotate=([x,y,z])=>[(x-y)/Math.sqrt(2)+100,(x+y)/Math.sqrt(2)-80,z];
  const base=[[0,0,0],[20,0,0],[20,5,3],[20,10,0],[0,10,0],[0,5,3],[0,0,0]];
  for(const reverse of [false,true]) {
    let outline=[[0,0],[20,0],[20,10],[0,10]].map(p=>rotate([...p,0]).slice(0,2));
    let boundary=base.map(rotate);
    if(reverse) {outline.reverse();boundary.reverse();}
    const plan=planFacade(factory({type:'pitched',outline}),{boundary});
    assert.equal(plan.segments.length,6);
    assert.ok(plan.segments.some(s=>s.heights[0]===12 || s.heights[1]===12));
    const center=rotate([10,5,0]);
    for(const s of plan.segments) {
      const outward=(s.a[0]+s.b[0])/2-center[0], north=(s.a[1]+s.b[1])/2-center[1];
      assert.ok(outward*s.n[0]+north*s.n[1]>0);
    }
    checkPlacement(plan);
  }
});

test('L-shaped courtyard canopies project outward and narrow courtyards cap the depth',()=>{
  const outline=[[0,0],[20,0],[20,20],[11,20],[11,5],[9,5],[9,20],[0,20]];
  const plan=planFacade(factory({outline,facade:{front_edge:3,canopy_depth_m:4,doors:2,loading_docks:0,personnel_door:false}}));
  assert.ok(plan.openings.length);
  assert.ok(plan.openings.every(o=>o.canopy_depth>0 && o.canopy_depth<2));
  assert.ok(plan.openings.every(o=>plan.segments[o.segment].n[0]===-1));
  checkPlacement(plan);
});

test('narrow courtyard excludes docks whose apron or rubber buffers would cross the opposite wall',()=>{
  const outline=[[0,0],[20,0],[20,20],[10.4,20],[10.4,5],[9.6,5],[9.6,20],[0,20]];
  const plan=planFacade(factory({outline,facade:{front_edge:3,doors:0,loading_docks:1,personnel_door:false}}));
  assert.equal(plan.counts.loading_docks,0);
  assert.equal(plan.counts.canopies,0);
});

test('all facade styles batch to bounded finite meshes and dispose independently',()=>{
  const context={};runInNewContext(readFileSync(new URL('../../desktop/web/vendor/three.min.js',import.meta.url),'utf8'),context);
  const T=context.THREE;
  for(const wall_material of ['metal','concrete','brick']) {
    const data=normalizeScene({project:{roof:factory({facade:{wall_material}})},design:{version:1,modules:[]}});
    const facade=createFacade(T,data),group=facade.group;
    assert.equal(facade.stats().wall_material,wall_material);
    assert.ok(group.children.length<=14);
    assert.ok(group.children.some(o=>o.isLineSegments));
    let disposed=0;
    for(const o of group.children) {
      assert.ok(!o.userData.surface);
      assert.ok(Array.from(o.geometry.attributes.position.array).every(Number.isFinite));
      o.geometry.addEventListener('dispose',()=>disposed++);
      o.geometry.dispose();o.material.dispose();
    }
    assert.equal(disposed,group.children.length);
  }
  const data=normalizeScene({project:{roof:factory({outline:[[0,0],[10000,0],[10000,6000],[0,6000]],height_m:1000,
    facade:{wall_material:'brick',window_rows:0,columns:false}})},design:{version:1,modules:[]}});
  const huge=createFacade(T,data);
  assert.ok(huge.group.children.filter(o=>o.isLineSegments).reduce((sum,o)=>sum+o.geometry.attributes.position.count,0)<100000);
  for(const key of ['taizhou_pharma','taizhou_shipyard','taizhou_watertown','taizhou_agri']) {
    assert.ok(facadePresets[key]?.label);
    const preset=applyFacadePreset({},key);
    const presetScene=normalizeScene({project:{roof:factory({facade:preset})},design:{version:1,modules:[]}});
    const built=createFacade(T,presetScene);
    assert.ok(built.group.children.length<=14);
  }
});
