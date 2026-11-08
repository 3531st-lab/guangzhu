import test from 'node:test';
import assert from 'node:assert/strict';
import {rectangleInfo, rectanglePoints, editItemGeometry, arrayCopies, snapGeometry} from '../../desktop/web/roofedit-geometry.js';

const skylight = {id:'sky-1', label:'天窗', kind:'skylight', points:[[1,2],[5,2],[5,4],[1,4]]};
const near = (a,b) => assert.ok(Math.abs(a-b) < 1e-8, `${a} != ${b}`);

test('precise rotated rectangles preserve dimensions and centroid through independent changes', () => {
  let item = editItemGeometry(skylight,'turn',37);
  item = editItemGeometry(item,'w',7.25);
  item = editItemGeometry(item,'cy',-12.75);
  const rect = rectangleInfo(item.points);
  near(rect.w,7.25); near(rect.d,2); near(rect.turn,37); near(rect.cx,3); near(rect.cy,-12.75);
  assert.deepEqual(skylight.points,[[1,2],[5,2],[5,4],[1,4]]);
  assert.throws(() => editItemGeometry(item,'w',0),/长宽/);
  assert.throws(() => editItemGeometry(item,'cx',Infinity),/有效数字/);
});

test('six-item eight-metre array has five independent copies and includes original in total', () => {
  const copies = arrayCopies(skylight,6,8,90);
  assert.equal(copies.length,5);
  near(rectangleInfo(copies[4].points).cy,43);
  near(rectangleInfo(copies[0].points).cx,3);
  copies[0].points[0][0] = 500;
  assert.equal(skylight.points[0][0],1);
  assert.equal(copies[1].points[0][0],1);
  for (const args of [[1,8,0],[101,8,0],[2.5,8,0],[6,0,0],[6,8,NaN]]) assert.throws(() => arrayCopies(skylight,...args));
});

test('snapping prioritizes vertices then midpoints then finite edge projections', () => {
  const roof = rectanglePoints({w:20,d:10,cx:10,cy:5});
  assert.equal(snapGeometry([.08,.05],[roof],.2).kind,'端点');
  assert.deepEqual(snapGeometry([9.95,.05],[roof],.2).point,[10,0]);
  const edge = snapGeometry([6,.05],[roof],.2);
  assert.equal(edge.kind,'边线'); assert.deepEqual(edge.point,[6,0]);
  assert.equal(snapGeometry([30,20],[roof],.2),null);
});
