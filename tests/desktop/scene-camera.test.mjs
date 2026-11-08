import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {normalizeView,viewDirection,sceneFramePoints,fitCamera,resizeCamera,changeProjection} from '../../desktop/web/scene-camera.js';
import {normalizeScene} from '../../desktop/web/scene-data.js';

const context={};runInNewContext(readFileSync(new URL('../../desktop/web/vendor/three.min.js',import.meta.url),'utf8'),context);
const T=context.THREE;
const controls=camera=>({object:camera,target:new T.Vector3(),update(){},enableDamping:true});
const point=(camera,p)=>new T.Vector3(...p).project(camera);
const roof={type:'flat',height_m:5,outline:[[0,0],[30,0],[30,20],[0,20]],parapet_height_m:2};

test('named views use true metre/world cardinal axes and retain legacy aliases',()=>{
  assert.equal(normalizeView(true),'top');assert.equal(normalizeView(false),'iso');assert.equal(normalizeView('isometric'),'iso');
  for(const [name,expected] of Object.entries({north:[0,0,-1],east:[1,0,0],south:[0,0,1],west:[-1,0,0]})) {
    assert.deepEqual(Array.from(viewDirection(T,name,roof).toArray()),expected);
  }
  assert.ok(viewDirection(T,'front',roof,0).dot(new T.Vector3(0,0,1))>.999);
  assert.ok(viewDirection(T,'back',roof,0).dot(new T.Vector3(0,0,-1))>.999);
  assert.ok(viewDirection(T,'left',roof,0).dot(new T.Vector3(-1,0,0))>.999);
});

test('framing includes an empty model interior ridge and authoritative parapet peaks',()=>{
  const input={project:{roof},design:{version:1,modules:[]},roof_geometry:{faces:[{points:[[0,0,0],[30,0,0],[15,10,18]]}],parapets:[[[0,0,0],[3,0,0],[3,0,3],[0,0,3]]]}};
  const data=normalizeScene(input),points=sceneFramePoints(data);
  assert.equal(Math.max(...points.map(p=>p[1])),23);
  assert.ok(points.some(p=>p[1]===8));
  for(const projection of ['orthographic','perspective']) for(const view of ['iso','top','north','east','south','west']) {
    const camera=projection==='orthographic'?new T.OrthographicCamera(-1.6,1.6,1,-1,.01,1000):new T.PerspectiveCamera(42,1.6,.01,1000);
    fitCamera(T,camera,controls(camera),points,viewDirection(T,view,roof),.84);
    for(const p of points) {
      const q=point(camera,p);
      assert.ok(Math.abs(q.x)<.85 && Math.abs(q.y)<.85 && q.z>=-1 && q.z<=1,`${projection}/${view}: ${q.toArray()}`);
    }
  }
  const empty=normalizeScene({...input,roof_geometry:{faces:[],parapets:[]}});
  assert.equal(Math.max(...sceneFramePoints(empty).map(p=>p[1])),5,'explicit no-wall geometry cannot revive legacy full-height parapets');
});

test('orthographic objects retain equal apparent size at different depths',()=>{
  const orthographic=new T.OrthographicCamera(-10,10,10,-10,.01,100);
  orthographic.position.set(0,0,30);orthographic.lookAt(0,0,0);orthographic.updateMatrixWorld();
  const width=(camera,z)=>point(camera,[2,0,z]).x-point(camera,[0,0,z]).x;
  assert.ok(Math.abs(width(orthographic,0)-width(orthographic,10))<1e-12);
  const perspective=new T.PerspectiveCamera(42,1,.01,100);perspective.position.copy(orthographic.position);perspective.lookAt(0,0,0);perspective.updateMatrixWorld();
  assert.ok(width(perspective,10)>width(perspective,0)*1.4);
});

test('projection switching preserves target-plane scale including orthographic zoom',()=>{
  const camera=new T.PerspectiveCamera(42,1.5,.01,1000),orbit=controls(camera);
  camera.position.set(0,0,30);camera.lookAt(orbit.target);camera.updateMatrixWorld();
  assert.equal(changeProjection(T,camera,orbit,'perspective'),camera,'choosing the current projection is a no-op');
  const original=point(camera,[2,0,0]).x;
  const orthographic=changeProjection(T,camera,orbit,'orthographic');
  assert.equal(changeProjection(T,orthographic,orbit,'orthographic'),orthographic);
  assert.ok(orthographic.isOrthographicCamera);
  assert.ok(Math.abs(point(orthographic,[2,0,0]).x-original)<1e-12);
  orthographic.zoom=2;orthographic.updateProjectionMatrix();
  const scaled=point(orthographic,[2,0,0]).x,perspective=changeProjection(T,orthographic,orbit,'perspective');
  assert.ok(perspective.isPerspectiveCamera && orbit.object===perspective);
  assert.ok(Math.abs(point(perspective,[2,0,0]).x-scaled)<1e-12);
});

test('resize keeps vertical orthographic scale and screen pixels square',()=>{
  const camera=new T.OrthographicCamera(-10,10,10,-10,.01,100);
  camera.position.set(0,0,30);camera.lookAt(0,0,0);camera.updateMatrixWorld();
  resizeCamera(camera,1200,600);
  assert.equal(camera.top-camera.bottom,20);assert.equal(camera.right-camera.left,40);
  const horizontal=(point(camera,[1,0,0]).x-point(camera,[0,0,0]).x)*600;
  const vertical=(point(camera,[0,1,0]).y-point(camera,[0,0,0]).y)*300;
  assert.ok(Math.abs(horizontal-vertical)<1e-12);
});
