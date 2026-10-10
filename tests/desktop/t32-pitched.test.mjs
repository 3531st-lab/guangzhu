import test from 'node:test';
import assert from 'node:assert/strict';
import {pitchedHeight, normalizeScene} from '../../desktop/web/scene-data.js';
import {roofSVG, comparisonTable} from '../../desktop/web/data.js';

const roof = {type:'pitched', height_m:9, outline:[[0,0],[20,0],[20,10],[0,10]], planes:[
  {id:1, outline:[[0,0],[20,0],[20,5],[0,5]], slope_deg:30, slope_azimuth_deg:180, offset_m:0, material:'metal'},
  {id:2, outline:[[0,5],[20,5],[20,10],[0,10]], slope_deg:30, slope_azimuth_deg:0, offset_m:0, material:'glass'},
]};
test('real ridge height, both eaves and glass boundary are preserved in normalized scene', () => {
  assert.ok(Math.abs(pitchedHeight(roof, [10,5]) - 2.886751345948129) < 1e-10);
  assert.ok(Math.abs(pitchedHeight(roof, [10,0])) < 1e-10);
  assert.ok(Math.abs(pitchedHeight(roof, [10,10])) < 1e-10);
  const scene = normalizeScene({project:{roof}, design:{version:1, modules:[]}});
  assert.equal(scene.roof.planes.length, 2);
  assert.ok(Math.abs(scene.world([10,5,scene.elevation([10,5])])[1] - 11.886751345948129) < 1e-10);
  const svg = roofSVG({name:'整栋', geometry:roof});
  assert.match(svg, /P1 30°/);
  assert.match(svg, /P2 30°/);
  assert.match(svg, /#9fd6df/);
});
test('pitched comparison renders used faces without an invented common tilt', () => {
  const row = {name:'多装', version:2, tilt_deg:null, dc_kw:100, annual_kwh:100000, kwh_per_kw:1000,
    capex_cny:300000, payback_years:5, irr_pct:15, avg_loss_pct:0, hard_pass:true, violated_requirements:[], align:'pitched', planes:[1,3]};
  const html = comparisonTable({options:[row], recommended:{balanced:{version:2, why:'示意'}}});
  assert.match(html, /顺坡 P1、P3/);
  assert.doesNotMatch(html, /25°/);
});
