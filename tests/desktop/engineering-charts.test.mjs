import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {lossMetricsMarkup,monthlyEnergy,monthlyYieldMarkup} from '../../desktop/web/engineering-charts.js';

test('every browser module parses as ESM, including the full roof editor imported by app', () => {
  const directory=fileURLToPath(new URL('../../desktop/web/',import.meta.url));
  const script=`const fs=require('fs'),vm=require('vm'),path=require('path');
    for(const file of fs.readdirSync(process.argv[1]).filter(f=>f.endsWith('.js')))
      new vm.SourceTextModule(fs.readFileSync(path.join(process.argv[1],file),'utf8'),{identifier:file});`;
  const checked=spawnSync(process.execPath,['--experimental-vm-modules','-e',script,directory],{encoding:'utf8'});
  assert.equal(checked.status,0,checked.stderr);
});

test('loss diagnostics retain real zeros and high shading without invented energy stages', () => {
  for(const loss of [0,80]) {
    const html=lossMetricsMarkup({scene:{shading:{summary:{avg_loss_pct:loss}},electrical:{dc_drop_pct_max:0,ac_drop_pct_max:2.88}}});
    assert.match(html,new RegExp(`data-loss-metric="年度平均遮挡损失">${loss}%`));
    assert.match(html,/data-loss-metric="直流最大线路电压降">0%/);
    assert.match(html,/2.88%/);
    assert.doesNotMatch(html,/2\.1|PVsyst|6\.8/);
  }
  assert.match(lossMetricsMarkup({}),/未计算/);
  assert.match(lossMetricsMarkup({evidence:{analysis:{status:'stale'}}}),/需要重新计算/);
});

const months=Array.from({length:12},(_,i)=>({month:i+1,generation_kwh:(i+1)*100,
  self_use_kwh:(i+1)*50,export_kwh:(i+1)*40,curtailed_kwh:(i+1)*10}));
const result=()=>({metrics:{yield_kwh:{p50:7800}},economics:{self_use:{monthly:structuredClone(months),algorithm:'按用电逐时算'}}});

test('monthly chart uses actual month totals and distinguishes exported from curtailed energy', () => {
  const original=result(),data=monthlyEnergy(original);
  assert.equal(data.total,7800);assert.deepEqual(data.rows,months);
  const html=monthlyYieldMarkup(original);
  assert.match(html,/12月弃电 120 kWh/);assert.match(html,/1月自用 50 kWh/);assert.match(html,/按用电逐时算/);
  const changed=result();changed.economics.self_use.monthly.reverse();
  assert.equal(monthlyYieldMarkup(changed),html);
  assert.equal(original.economics.self_use.monthly[0].month,1);
});

test('missing, invalid and mismatched monthly inputs remain uncomputed instead of being apportioned', () => {
  assert.match(monthlyYieldMarkup({metrics:{yield_kwh:{p50:100000}}}),/未保存逐月/);
  const mismatch=result();mismatch.economics.self_use.monthly[0].self_use_kwh=75;
  assert.match(monthlyEnergy(mismatch).reason,/不一致/);
  const annual=result();annual.metrics.yield_kwh.p50=5000;
  assert.match(monthlyEnergy(annual).reason,/年发电不一致/);
  const partial=result();partial.economics.self_use.monthly.pop();assert.match(monthlyEnergy(partial).reason,/不完整/);
  const fallback={economics:{analysis_metadata:{yield_kwh:{monthly_kwh:months.map(row=>({month:row.month,ac_kwh:row.generation_kwh}))}}}};
  assert.equal(monthlyEnergy(fallback).detailed,false);assert.match(monthlyYieldMarkup(fallback),/未计算逐月自用/);
});
