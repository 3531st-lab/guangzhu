import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {normalizeScene,panelMatrix,solarPosition,heatColor,stringColor,HEAT_COLORS} from '../../desktop/web/scene-data.js';
// Immutable, committed formal-run captures; never use ignored live projects or newest-version discovery.
const captures = {
  'gz-t14-changzhou-005':['789a0536aba73d176558','a6e2b20e5f63546f404a217aeaa42d5d2e03972a4c201dce0d8e56a58d0f5ac5'],
  'gz-t14-lshape-001':['c18e712b53f1c60a9796','942cfc86f181bd8d66092c7cb8640902d852c10784037639ae6875e997c9214d'],
  'gz-t14-rotated-002':['16d0b3d9402c8dcc025d','b305059edee8bdcf15138549f5646c5c11afa595ed59634ab2211cbdb7d0ba41'],
};
function checkedJson(path,sha) {
  const bytes = readFileSync(new URL('../../'+path,import.meta.url));
  assert.equal(createHash('sha256').update(bytes).digest('hex'),sha,path+' original SHA');
  return JSON.parse(bytes.toString('utf8'));
}
function original(id,path) {
  const [capture,sha] = captures[id], base = `runs/${id}/captures/${capture}/`;
  const manifest = checkedJson(base+'run.json',sha), key = 'project/'+path;
  assert.ok(manifest.artifacts[key],key+' is listed in the frozen manifest');
  return checkedJson(base+key,manifest.artifacts[key]);
}
const scene = (id,version=1) => {
  const design = original(id,`designs/v${version}.json`);
  assert.equal(design.version,version,'selected version is exact');
  const parent_design = design.parent_version ? original(id,`designs/v${design.parent_version}.json`) : null;
  if (parent_design) assert.equal(parent_design.version,design.parent_version,'actual parent version is exact');
  return {project:original(id,'project.json'),design,parent_design};
};
for (const id of Object.keys(captures)) test.skip(id+' exact panel corners retain roof-relative height and orientation',() => {
  const raw = scene(id), data = normalizeScene(raw);
  assert.equal(data.modules.length,raw.design.modules.length);
  for (const module of data.modules) {
    const matrix = panelMatrix(module);
    for (const [i,[x,z]] of [[-.5,.5],[.5,.5],[.5,-.5],[-.5,-.5]].entries()) {
      const actual = [0,1,2].map(k => matrix[k]*x+matrix[8+k]*z+matrix[12+k]);
      actual.forEach((v,k) => assert.ok(Math.abs(v-module.points[i][k]) < .002,`${module.id} corner ${i} axis ${k}`));
    }
    assert.equal(module.position[1],raw.project.roof.height_m+module.center[2]);
    assert.ok(matrix[5] > 0,'display panel normal points up');
  }
  assert.deepEqual(data.roof.obstacles,raw.project.roof.obstacles);
  assert.deepEqual(data.roof.keepouts,raw.project.roof.keepouts);
});
test.skip('difference uses actual parent IDs rather than cumulative removed_modules or version minus one',() => {
  assert.equal(normalizeScene(scene('gz-t14-changzhou-005',3)).removed.length,1);
  const raw = scene('gz-t14-changzhou-005',12), data = normalizeScene(raw);
  assert.equal(raw.design.removed_modules.length,19); assert.equal(data.removed.length,6);
  const nonAdjacent = {...raw,design:{...raw.design,version:90,parent_version:11}};
  assert.equal(normalizeScene(nonAdjacent).removed.length,6);
  assert.equal(normalizeScene({...raw,parent_design:{...raw.parent_design,version:9}}).removed.length,0);
  assert.equal(normalizeScene({...raw,parent_design:null}).added.size,0);
});
test.skip('heat and string joins retain actual annual losses and design voltages, missing data stays unknown',() => {
  const raw = scene('gz-t14-changzhou-005',12);
  raw.shading = original('gz-t14-changzhou-005','analysis/v12/shading.json');
  raw.electrical = original('gz-t14-changzhou-005','analysis/v12/electrical.json');
  assert.equal(raw.shading.version,12); assert.equal(raw.electrical.version,12);
  const data = normalizeScene(raw), sorted = [...raw.shading.modules].sort((a,b) => a.total_loss_pct-b.total_loss_pct);
  for (const sample of [sorted[0],sorted[Math.floor(sorted.length/2)],sorted.at(-1)]) {
    const panel = data.modules.find(m => m.id === sample.id);
    assert.equal(panel.loss,sample.total_loss_pct);
    assert.equal(heatColor(panel.loss,data.threshold),heatColor(sample.total_loss_pct,raw.shading.summary.threshold_pct));
  }
  for (const string of raw.electrical.strings) for (const id of string.module_ids) assert.equal(data.modules.find(m => m.id === id).string.id,string.id);
  assert.equal(new Set(raw.electrical.strings.map(s => stringColor(s.id))).size,raw.electrical.strings.length,'each actual string has its own stable color');
  assert.equal(data.electrical.voc_cold_v,1080.1215750000001);
  assert.equal(data.electrical.vmp_hot_v,693.6325136);
  assert.equal(heatColor(0),HEAT_COLORS[0]); assert.equal(heatColor(4),HEAT_COLORS[1]); assert.equal(heatColor(8),HEAT_COLORS[2]);
  assert.equal(heatColor(null),'#998e83'); assert.equal(stringColor(null),'#998e83');
  const wrong = normalizeScene({...raw,shading:{...raw.shading,version:1},electrical:{...raw.electrical,version:1}});
  assert.ok(wrong.modules.every(m => m.loss === null && m.string === null)); assert.equal(wrong.electrical,null);
});
test('solar coordinates match independent existing SPA references within one degree across seasons',() => {
  // backend guangzhu.solar.sun_position; timezone Asia/Shanghai, lat31.81 lon119.97.
  const samples = [['2026-12-21',9,20.2767538155,136.7281863805],['2026-12-21',12,34.750402384,180.5529363981],['2026-12-21',15,19.6948761299,224.0143957688],['2026-03-20',12,57.9602310309,176.3910738413],['2026-06-21',12,81.6173629046,177.0651122871]];
  for (const [date,hour,alt,az] of samples) {
    const value = solarPosition(31.81,119.97,date,hour);
    assert.ok(Math.abs(value.altitude-alt) < 1); assert.ok(Math.abs(value.azimuth-az) < 1);
    assert.ok(Math.abs(Math.hypot(...value.direction)-1)<1e-12);
  }
  const noon = solarPosition(31.81,119.97,'2026-12-21',12);
  assert.ok(noon.direction[2] > 0,'sun south (+Z): projected ground shadow points north (-Z)');
  assert.ok(solarPosition(31.81,119.97,'2026-12-21',6.5).altitude < 0);
  assert.notEqual(solarPosition(31.81,100,'2026-12-21',12).azimuth,noon.azimuth,'longitude is not hardcoded');
  assert.notEqual(solarPosition(40,119.97,'2026-12-21',12).altitude,noon.altitude,'latitude is not hardcoded');
});
