import test from 'node:test';
import assert from 'node:assert/strict';
import {transformItems,itemBounds} from '../../desktop/web/roofedit-geometry.js';
import {selectObject,normalizeSelection,selectedItems,selectionRefs} from '../../desktop/web/roofedit-selection.js';

const polygon={id:'equipment',kind:'device',label:'L形设备',height:3,plane_id:2,
  points:[[0,0],[4,0],[4,1],[1,1],[1,3],[0,3]]};
const circle={id:'tank',kind:'tank',label:'圆罐',center:[8,3],radius:2,height:4};

test('rigid group move keeps spacing, metadata and the source independent',()=>{
  const source=structuredClone([polygon,circle]);
  const result=transformItems(source,{mode:'move',dx:2.25,dy:-4});
  assert.deepEqual(result[0].points[2],[6.25,-3]);
  assert.deepEqual(result[1].center,[10.25,-1]);
  assert.equal(result[0].plane_id,2);
  assert.equal(result[1].radius,2);
  assert.deepEqual(source,[polygon,circle]);
  result[0].points[0][0]=99;
  assert.equal(source[0].points[0][0],0);
  assert.deepEqual(itemBounds(source),{min:[0,0],max:[10,5],center:[5,2.5]});
});

test('rotation supports concave imported polygons and circles around an explicit pivot',()=>{
  const result=transformItems([polygon,circle],{mode:'rotate',angle:90,pivotX:0,pivotY:0});
  assert.deepEqual(result[0].points,[[0,0],[0,4],[-1,4],[-1,1],[-3,1],[-3,0]]);
  assert.deepEqual(result[1].center,[-3,8]);
  assert.equal(result[1].radius,2);
});

test('each mirror uses the stated axis coordinate and applying it twice restores geometry',()=>{
  for (const mode of ['mirror-x','mirror-y']) {
    const result=transformItems([polygon,circle],{mode,axisValue:5});
    assert.deepEqual(result[1].center,mode==='mirror-x' ? [2,3] : [8,7]);
    assert.deepEqual(transformItems(result,{mode,axisValue:5}),[polygon,circle]);
  }
});

test('invalid, incomplete and ineffective transforms are rejected before mutation',()=>{
  for (const settings of [{mode:'move',dx:0,dy:0},{mode:'move',dx:null,dy:1},{mode:'move',dx:Infinity,dy:1},
    {mode:'rotate',angle:360,pivotX:0,pivotY:0},{mode:'rotate',angle:30,pivotX:NaN,pivotY:0},
    {mode:'mirror-x',axisValue:''},{mode:'scale',dx:1,dy:1}]) assert.throws(()=>transformItems([polygon],settings));
  assert.throws(()=>transformItems([],{mode:'move',dx:1,dy:1}));
});

test('selection toggles by stable ID, cleans deleted objects, and keeps parts single-selected',()=>{
  let selection=selectObject(null,{kind:'item',id:'equipment'});
  selection=selectObject(selection,{kind:'item',id:'tank'},true);
  assert.deepEqual(selectionRefs(selection),[{kind:'item',id:'equipment'},{kind:'item',id:'tank'}]);
  assert.deepEqual(selectedItems(selection,[circle,polygon]),[circle,polygon]);
  assert.deepEqual(normalizeSelection(selection,[polygon]),{kind:'item',ids:['equipment'],active:'equipment'});
  assert.equal(normalizeSelection(selection,[]),null);
  selection=selectObject(selection,{kind:'item',id:'equipment'},true);
  assert.deepEqual(selection.ids,['tank']);
  selection=selectObject(selection,{kind:'part',id:'main'},true);
  assert.deepEqual(selection,{kind:'part',ids:['main'],active:'main'});
  assert.equal(normalizeSelection(selection,[polygon],[]),null);
  assert.deepEqual(normalizeSelection(selection,[],[{id:'main'}]),selection);
});
