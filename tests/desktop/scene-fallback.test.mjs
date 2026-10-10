import test from 'node:test';
import assert from 'node:assert/strict';
import {createScene} from '../../desktop/web/scene.js';

test('missing WebGL gives a usable explanation without constructing a renderer',() => {
  let rendererCalls=0, notice='';
  const previous={document:globalThis.document,THREE:globalThis.THREE};
  globalThis.document={createElement:() => ({getContext:() => null})};
  globalThis.THREE={OrbitControls(){},WebGLRenderer(){rendererCalls++;throw Error('must not construct');}};
  const host={classList:{add(){}},replaceChildren(...items){this.children=items;}};
  try {
    const scene=createScene(host,{onUnavailable:value => {notice=value;}});
    assert.equal(scene.stats().available,false); assert.equal(rendererCalls,0);
    assert.match(notice,/无法显示 3D/); assert.equal(host.children[0].hidden,true);
    for(const method of ['setData','setSun','setTheme','setMode']) assert.doesNotThrow(() => scene[method]({}));
    scene.dispose(); assert.deepEqual(host.children,[]);
  } finally {globalThis.document=previous.document;globalThis.THREE=previous.THREE;}
});
