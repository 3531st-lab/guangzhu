import test from 'node:test';
import assert from 'node:assert/strict';
import {defaults, panel, drawing} from '../../desktop/web/installation-edit.js';
import {normalizeScene, pileContact} from '../../desktop/web/scene-data.js';
import {financialForm} from '../../desktop/web/economic-ui.js';

test('installation editor retains explicit zero and distinguishes requested clearance from face height', () => {
  const values = defaults({ground:{road_every:0, fence_setback_m:0}, carport:{tilt_deg:0, clear_height_m:2.2}});
  assert.equal(values.ground.road_every, 0);
  assert.equal(values.ground.fence_setback_m, 0);
  assert.equal(values.carport.tilt_deg, 0);
  assert.equal(values.carport.clear_height_m, 2.2);
  assert.equal(values.carport.structure_depth_m, .3);
  const state = {...values, roofMode:'carport', planes:[]};
  const html = panel(state, [['carport','车棚']], (label, action) => `<button data-action="${action}">${label}</button>`);
  assert.match(html, /2\.4×5\.1m/);
  assert.match(html, /5\.5m/);
  assert.match(html, /保存或删除不会自动重建/);
  assert.match(html, /最低棚面减结构深度/);
  assert.match(html, /data-site-key="tilt_deg"[^>]*value="0"/s);
});

test('deleting a canopy hides only its columns and retains actual clear parking polygons', () => {
  const state = {roofMode:'carport', planes:[{id:2,outline:[[0,0],[2,0],[2,2]]}], carport:{
    bays:[{polygon:[[0,0],[2.4,0],[2.4,5.1],[0,5.1]]}], aisles:[], columns:{1:[[1,1]],2:[[3,3]]},
  }};
  const svg = drawing(state, p => p.join(','), .1);
  assert.doesNotMatch(svg, /cx="1"/);
  assert.match(svg, /cx="3"/);
  assert.match(svg, /2\.4,5\.1/);
});

test('historical installation geometry overrides later template edits for actual scene normalization', () => {
  const snapshot = {type:'carport', height_m:0, outline:[[0,0],[10,0],[10,8],[0,8]],
    planes:[{id:1,outline:[[0,0],[10,0],[10,4],[0,4]],slope_deg:0,slope_azimuth_deg:180,offset_m:2.8}]};
  const changed = {...snapshot, height_m:9, planes:[]};
  const scene = normalizeScene({project:{roof:changed}, design:{version:1,modules:[],installation_roof:snapshot}});
  assert.equal(scene.roof.height_m, 0);
  assert.equal(scene.roof.planes[0].offset_m, 2.8);
  assert.equal(changed.height_m, 9);
});

test('new construction form excludes roof refurbishment and carport does not invent lease income', () => {
  const field = (key, label) => `<input name="${key}" aria-label="${label}">`;
  const toggle = (key, label) => `<label>${label}<input name="${key}"></label>`;
  const ground = financialForm({}, field, toggle, 'ground');
  const carport = financialForm({}, field, toggle, 'carport');
  assert.match(ground, /name="landRent"/);
  assert.doesNotMatch(ground + carport, /name="refurbish"/);
  assert.doesNotMatch(carport, /name="landRent"/);
  assert.match(carport, /未计场地或棚面租金/);
  assert.match(financialForm({}, field, toggle), /name="refurbish"/);
});

test('inclined pile cap meets the displayed module underside without protruding through the front', () => {
  const panel = {center:[1,2,1.5], corners:[[0,0,.5],[2,0,.5],[2,4,2.5],[0,4,2.5]], tilt:Math.atan(.5)*180/Math.PI};
  const contact = pileContact({point:[1,2,0]}, [panel]);
  assert.equal(contact.dx, 0);
  assert.equal(contact.dy, .5);
  assert.ok(Math.abs(contact.inset - .0223606797749979) < 1e-12);
  for (const dy of [-.07,0,.07]) {
    const cap = 1.5 + contact.dy * dy - contact.inset;
    assert.ok(cap < 1.5 + .5 * dy);
  }
});
