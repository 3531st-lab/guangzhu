import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {batchStatic} from '../../desktop/web/scene-static.js';

test('static batching preserves transformed faces and disconnected line segments', () => {
  const context = {};
  runInNewContext(readFileSync(new URL('../../desktop/web/vendor/three.min.js', import.meta.url), 'utf8'), context);
  const T = context.THREE, group = new T.Group();
  function triangle() {
    const geometry = new T.BufferGeometry();
    geometry.setAttribute('position', new T.Float32BufferAttribute([0,0,0,1,0,0,0,1,0], 3));
    geometry.computeVertexNormals();
    const mesh = new T.Mesh(geometry, new T.MeshStandardMaterial({color:0xff0000}));
    group.add(mesh);
    return mesh;
  }
  triangle().position.set(2, 0, 0);
  const second = triangle();
  second.position.set(0, 3, 0);
  second.rotation.z = Math.PI / 2;
  const roof = triangle();
  roof.userData.roofPlane = 1;
  for (const points of [[[0,0,0],[1,0,0],[1,1,0]], [[5,0,0],[6,0,0]]]) {
    group.add(new T.Line(new T.BufferGeometry().setFromPoints(points.map(p => new T.Vector3(...p))), new T.LineBasicMaterial()));
  }
  batchStatic(T, group);
  assert.equal(group.children.length, 3);
  assert.ok(group.children.includes(roof));
  const merged = group.children.find(o => o.isMesh && o !== roof);
  const expected = [2,0,0,3,0,0,2,1,0,0,3,0,0,4,0,-1,3,0];
  Array.from(merged.geometry.attributes.position.array).forEach((v, i) => assert.ok(Math.abs(v - expected[i]) < 1e-6));
  const lines = group.children.find(o => o.isLineSegments);
  assert.deepEqual(Array.from(lines.geometry.attributes.position.array), [0,0,0,1,0,0,1,0,0,1,1,0,5,0,0,6,0,0]);
});
