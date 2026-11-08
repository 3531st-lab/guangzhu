import test from 'node:test';
import assert from 'node:assert/strict';
import {transformModuleGeometry,snapModuleMove,snapModuleAngle,surfaceFrame,lockedRegionSegments} from '../../desktop/web/module-transform-geometry.js';

const spec={available:true,length_m:2.4,width_m:1.1,gap_m:.02,lower_edge_m:.3};
const flat={type:'flat',outline:[[0,0],[30,0],[30,20],[0,20]],slope_deg:0,slope_azimuth_deg:180};
const dot=(a,b)=>a.reduce((sum,value,i)=>sum+value*b[i],0);
const near=(a,b)=>assert.ok(Math.abs(a-b)<1e-9,`${a} != ${b}`);
function panel(id,x,y,roof=flat,angle=0) {
  const base={id,center:[x,y,0],corners:[[x-.55,y-1.2,0],[x+.55,y-1.2,0],[x+.55,y+1.2,0],[x-.55,y+1.2,0]],orientation:'portrait',tilt:15,azimuth:180};
  return transformModuleGeometry(base,roof,{mode:'rotate',angle_deg:angle},spec);
}

test('grid snaps the anchor centre and Alt/disabled settings retain the exact pointer displacement',()=>{
  const anchor=panel('one',5.03,7.06),delta={dx_m:.1234,dy_m:-.2345};
  const snapped=snapModuleMove(anchor,[anchor],['one'],flat,spec,delta,{gridM:.1,align:false});
  near(anchor.center[0]+snapped.dx_m,5.2);near(anchor.center[1]+snapped.dy_m,6.8);
  assert.equal(snapped.snap.kind,'grid');
  for(const [settings,alt] of [[{enabled:false},false],[{enabled:true},true]]) {
    const result=snapModuleMove(anchor,[anchor],['one'],flat,spec,delta,settings,alt);
    near(result.dx_m,delta.dx_m);near(result.dy_m,delta.dy_m);assert.equal(result.snap.applied,false);
  }
});

test('alignment places actual panel edges at the catalog installation gap, including rotated panels',()=>{
  for(const angle of [0,37,90]) {
    const anchor=panel('one',8,8,flat,angle);
    const axis=anchor.corners[1].map((v,i)=>(v-anchor.corners[0][i])/spec.width_m);
    const neighbor=panel('two',8+axis[0]*(spec.width_m+spec.gap_m),8+axis[1]*(spec.width_m+spec.gap_m),flat,angle);
    const result=snapModuleMove(anchor,[anchor,neighbor],['one'],flat,spec,{dx_m:.04*axis[0],dy_m:.04*axis[1]},
      {enabled:true,gridM:0,toleranceM:.1});
    const moved=transformModuleGeometry(anchor,flat,{mode:'move',...result},spec);
    const edgeGap=Math.min(...neighbor.corners.map(p=>dot(p,axis)))-Math.max(...moved.corners.map(p=>dot(p,axis)));
    near(edgeGap,spec.gap_m);assert.equal(result.snap.kind,'gap');assert.deepEqual(result.snap.targetIds,['two']);
  }
});

test('a nonparallel neighbor aligns one centre line without grid, edge or gap snapping',()=>{
  const anchor=panel('one',8,8),neighbor=panel('rotated-target',8,12,flat,37);
  const result=snapModuleMove(anchor,[anchor,neighbor],[anchor.id],flat,spec,{dx_m:.06,dy_m:.3},
    {enabled:true,gridM:0,align:true,toleranceM:.12});
  const moved=transformModuleGeometry(anchor,flat,{mode:'move',...result},spec);
  near(moved.center[0],neighbor.center[0]);near(moved.center[1],8.3);
  assert.equal(result.snap.kind,'center');assert.equal(result.snap.applied,true);
  assert.deepEqual(result.snap.targetIds,[neighbor.id]);assert.equal(result.guides.length,1);
  assert.deepEqual(result.guides[0].from,moved.center);assert.deepEqual(result.guides[0].to,neighbor.center);
});

test('unequal panel widths align their same-side edges while centres and installation gaps stay distinct',()=>{
  const anchor=panel('one',8,8),neighbor=transformModuleGeometry({...panel('wide-target',8.65,12),orientation:'landscape'},flat,{mode:'move',dx_m:0,dy_m:0},spec);
  const result=snapModuleMove(anchor,[anchor,neighbor],[anchor.id],flat,spec,{dx_m:.06,dy_m:.3},
    {enabled:true,gridM:0,align:true,toleranceM:.12});
  const moved=transformModuleGeometry(anchor,flat,{mode:'move',...result},spec);
  near(Math.min(...moved.corners.map(p=>p[0])),Math.min(...neighbor.corners.map(p=>p[0])));
  near(moved.center[1],8.3);assert.ok(Math.abs(moved.center[0]-neighbor.center[0])>.5);
  assert.equal(result.snap.kind,'edge');assert.equal(result.snap.applied,true);
  assert.deepEqual(result.snap.targetIds,[neighbor.id]);assert.equal(result.guides.length,1);
  assert.deepEqual(result.guides[0].from,moved.center);assert.deepEqual(result.guides[0].to,neighbor.center);
});

test('slope alignment uses the true plane distance and never targets another face or selected panel',()=>{
  const plane={id:1,slope_deg:35,slope_azimuth_deg:180,offset_m:1.5,outline:flat.outline};
  const roof={type:'pitched',planes:[plane,{...plane,id:2,offset_m:4}]};
  const frame=surfaceFrame(plane),anchor=panel('P1-R1-C1',8,8,roof);
  const target=panel('P1-R2-C1',8+frame.uphill[0]*(spec.length_m+spec.gap_m),8+frame.uphill[1]*(spec.length_m+spec.gap_m),roof);
  const delta={dx_m:.04*frame.uphill[0],dy_m:.04*frame.uphill[1]};
  const settings={gridM:0,toleranceM:.1};
  const result=snapModuleMove(anchor,[anchor,target],['P1-R1-C1'],roof,spec,delta,settings);
  const moved=transformModuleGeometry(anchor,roof,{mode:'move',...result},spec);
  const gap=Math.min(...target.corners.map(p=>dot(p,frame.uphill)))-Math.max(...moved.corners.map(p=>dot(p,frame.uphill)));
  near(gap,spec.gap_m);
  for(const [neighbor,selected] of [[{...target,id:'P2-R2-C1'},[anchor.id]],[target,[anchor.id,target.id]]]) {
    const free=snapModuleMove(anchor,[anchor,neighbor],selected,roof,spec,delta,settings);
    near(free.dx_m,delta.dx_m);near(free.dy_m,delta.dy_m);assert.equal(free.snap.applied,false);
  }
});

test('rotation normalizes wraparound and validates snapping intervals without changing source geometry',()=>{
  assert.equal(snapModuleAngle(359,{angleDeg:15}).angle_deg,0);
  assert.equal(snapModuleAngle(-37,{angleDeg:15}).angle_deg,-30);
  assert.equal(snapModuleAngle(37,{angleDeg:15},true).angle_deg,37);
  assert.equal(snapModuleAngle(37,{angleDeg:0}).snap.applied,false);
  const source=panel('one',5,5),copy=structuredClone(source);
  assert.equal(transformModuleGeometry(source,flat,{mode:'move',dx_m:1,dy_m:2},{}),null);
  transformModuleGeometry(source,flat,{mode:'rotate',angle_deg:37},spec);
  assert.deepEqual(source,copy);
});

test('lock outlines split at height steps and roof gaps without drawing false diagonal connections',()=>{
  const roof={type:'pitched',planes:[
    {id:1,outline:[[0,0],[5,0],[5,8],[0,8]],offset_m:2,slope_deg:0,slope_azimuth_deg:180},
    {id:2,outline:[[5,0],[10,0],[10,8],[5,8]],offset_m:6,slope_deg:30,slope_azimuth_deg:180},
  ]};
  const lines=lockedRegionSegments(roof,[[2,2],[8,2],[8,6],[2,6]]);
  assert.equal(lines.length,6);
  const low=lines.filter(line=>line.every(p=>p[0]<=5));
  assert.equal(low.length,3);assert.ok(low.flat().every(p=>p[2]===2));
  const high=lines.filter(line=>line.every(p=>p[0]>=5));
  assert.equal(high.length,3);
  high.flat().forEach(p=>near(p[2],6+p[1]*Math.tan(Math.PI/6)));
  assert.ok(lines.every(([a,b])=>Math.hypot(a[0]-b[0],a[1]-b[1])>0),'no vertical connector at the height step');
  roof.planes[1].outline=[[6,0],[10,0],[10,8],[6,8]];
  const gaps=lockedRegionSegments(roof,[[2,2],[8,2],[8,6],[2,6]]);
  assert.ok(gaps.every(line=>line.every(p=>p[0]<=5)||line.every(p=>p[0]>=6)));
});
