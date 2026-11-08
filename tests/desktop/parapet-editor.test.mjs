import test from 'node:test';
import assert from 'node:assert/strict';
import {parapetAction,parapetChange,parapetIssues,parapetPanel,parapetPlanMarkup} from '../../desktop/web/parapet-editor.js';

const outline=[[0,0],[20,0],[20,10],[0,10]];
test('uniform, custom, and empty modes remain distinct; actions do not mutate source',()=>{
  const value=parapetAction('parapet-custom',null,outline,1.2);
  assert.equal(value.segments.length,4);
  assert.throws(()=>parapetAction('parapet-add',[],outline,null),/初始高度/);
  assert.throws(()=>parapetAction('parapet-add',[],outline,4),/初始高度/);
  assert.deepEqual(value.segments[0],{edge_index:0,start_ratio:0,end_ratio:1,height_m:1.2});
  assert.notEqual(value.anchor,outline);
  assert.deepEqual(parapetAction('parapet-none',value.segments,outline,1).segments,[]);
  assert.equal(parapetAction('parapet-uniform',value.segments,outline,1).segments,null);
  assert.equal(value.segments.length,4);
});
test('metre edits create a precise gap and add fills that gap without overlap',()=>{
  const value=parapetAction('parapet-custom',null,outline,1);
  const edited=parapetChange(value.segments,0,'start_m','5',outline);
  assert.equal(edited[0].start_ratio,.25);
  assert.equal(value.segments[0].start_ratio,0);
  const added=parapetAction('parapet-add',edited,outline,1.5);
  assert.deepEqual(added.segments.at(-1),{edge_index:0,start_ratio:0,end_ratio:.25,height_m:1.5});
  assert.deepEqual(parapetIssues(added.segments,outline,added.anchor),[]);
  assert.throws(()=>parapetAction('parapet-add',added.segments,outline,1),/全部覆盖/);
});
test('outline changes invalidate edge references but absence of walls is safe',()=>{
  const value=parapetAction('parapet-custom',null,outline,1);
  const changed=outline.map(([x,y])=>[x+1,y]);
  assert.match(parapetIssues(value.segments,changed,value.anchor)[0],/轮廓已变更/);
  assert.deepEqual(parapetIssues([],changed,value.anchor),[]);
  assert.deepEqual(parapetIssues(null,changed,null),[]);
  const reset=parapetAction('parapet-reset',value.segments,changed,1);
  assert.deepEqual(parapetIssues(reset.segments,changed,reset.anchor),[]);
});
test('validation blocks overlap, reversed intervals, missing edges, and nonfinite values',()=>{
  const row={edge_index:0,start_ratio:0,end_ratio:.6,height_m:1};
  assert.match(parapetIssues([row,{...row,start_ratio:.5,end_ratio:1}],outline,outline)[0],/重叠/);
  assert.match(parapetIssues([{...row,start_ratio:.7}],outline,outline)[0],/起点/);
  assert.match(parapetIssues([{...row,edge_index:99}],outline,outline)[0],/不存在/);
  assert.match(parapetIssues([{...row,height_m:Infinity}],outline,outline)[0],/高度/);
  assert.throws(()=>parapetChange([row],0,'height_m','',outline),/有效/);
  assert.match(parapetIssues([{...row,end_ratio:.5},{...row,start_ratio:.499999999,end_ratio:1}],outline,outline)[0],/重叠/);
});
test('legal defaults and decimal metre edits preserve exact adjacent endpoints',()=>{
  assert.deepEqual(parapetIssues([{edge_index:0,height_m:1}],outline,outline),[]);
  const rows=[{edge_index:0,start_ratio:0,end_ratio:1/3,height_m:1},
    {edge_index:0,start_ratio:1/3,end_ratio:1,height_m:1}];
  const edited=parapetChange(rows,1,'start_m','6.666666667',outline);
  assert.equal(edited[1].start_ratio,rows[0].end_ratio);
  assert.deepEqual(parapetIssues(edited,outline,outline),[]);
});
test('display uses metre distances and plan overlay follows roof north convention',()=>{
  const rows=[{edge_index:1,start_ratio:.2,end_ratio:.8,height_m:1.5}];
  const html=parapetPanel(rows,outline,{open:true,stale:true});
  assert.match(html,/保存前必须处理/);
  assert.match(html,/data-parapet-key="start_m" value="2"/);
  assert.match(html,/data-parapet-key="end_m" value="8"/);
  assert.match(parapetPlanMarkup(rows,outline,.1),/x1="20" y1="-2" x2="20" y2="-8"/);
  assert.doesNotMatch(parapetPlanMarkup([{...rows[0],height_m:0}],outline,.1),/<line/);
});
