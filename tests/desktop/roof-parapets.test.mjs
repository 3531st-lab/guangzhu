import test from 'node:test';
import assert from 'node:assert/strict';
import {parapetInfo} from '../../desktop/web/roof-parapets.js';
import {inferRequirements} from '../../desktop/web/data.js';

test('segmented and empty parapets never borrow the legacy uniform height',()=>{
  const roof={parapet_height_m:2,parapet_segments:[{height_m:.5},{height_m:1.5},{height_m:0}]};
  assert.deepEqual(parapetInfo(roof),{segmented:true,cap:null,label:'2 段 · 0.5–1.5 m'});
  assert.deepEqual(parapetInfo({...roof,parapet_segments:[]}),{segmented:true,cap:null,label:'无女儿墙'});
  assert.equal(parapetInfo({parapet_height_m:1.2}).cap,1.2);
});
test('natural-language parapet limits require an explicit number for segmented roofs',()=>{
  const roof={parapet_height_m:2,parapet_segments:[{height_m:1.5}]};
  const inferred=inferRequirements('不能高出女儿墙',{keep:[]},roof);
  assert.equal(inferred.form.maxHeight,undefined);
  assert.match(inferred.summary,/填写“组件最高点”/);
  const explicit=inferRequirements('不能高出女儿墙',{keep:[],maxHeight:.8},roof);
  assert.equal(explicit.form.maxHeight,.8);
  assert.equal(inferRequirements('不能高出女儿墙',{keep:[]},{parapet_height_m:1}).form.maxHeight,1);
});
