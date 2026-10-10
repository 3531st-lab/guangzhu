import test from 'node:test';
import assert from 'node:assert/strict';
import {inferRequirements, formSpec} from '../../desktop/web/data.js';

const roof = {geometry:{parapet_height_m:1.2}};
const base = {keep:[], inverterModels:{'SUN2000-100KTL-M2':'huawei-sun2000-100ktl-m2'}};
for (const [text, key, expected] of [
  ['只自用', 'noExport', true], ['装防逆流，不上网', 'noExport', true],
  ['限电不超过5%', 'curtail', 5], ['限电最多8%', 'curtail', 8],
  ['变压器800千伏安', 'transformer', 800], ['变压器容量为600kVA', 'transformer', 600],
  ['不超过变压器的70%', 'transformerShare', 70], ['变压器容量的80%', 'transformerShare', 80],
  ['不能高出女儿墙', 'maxHeight', 1.2], ['最高1.4米', 'maxHeight', 1.4],
  ['限高为0.9米', 'maxHeight', .9], ['分两期，一期先装200千瓦', 'phaseKw', 200],
  ['一期装100千瓦左右', 'phaseKw', 100], ['一期预算50万', 'phaseBudget', 50],
  ['一期投资为60万元', 'phaseBudget', 60], ['用华为逆变器', 'inverterBrand', 'Huawei'],
  ['逆变器用阳光', 'inverterBrand', 'Sungrow'], ['组件用天合N型', 'moduleId', 'trina-tsm-605neg19rc20'],
  ['组件用晶科 N 型', 'moduleId', 'jinko-jkm605n-66hl4m-bdv'],
  ['指定 SUN2000-100KTL-M2', 'inverterId', 'huawei-sun2000-100ktl-m2']]) {
  test('T28 recognition: ' + text, () => {
    const result = inferRequirements(text, base, roof);
    assert.equal(result.form[key], expected);
    assert.ok(result.recognized.length);
    if (key === 'inverterId') assert.equal(result.unknown, '');
    if (key.startsWith('phase')) {
      assert.equal(result.form.budget, undefined);
      assert.equal(result.form.capMax, undefined);
    }
  });
}
test('T28 total and phase budgets remain separate; explicit values win', () => {
  for (const text of ['总预算100万，一期预算50万', '一期预算50万总预算100万']) {
    const {form} = inferRequirements(text, base, roof);
    assert.equal(form.budget, 100);
    assert.equal(form.phaseBudget, 50);
    const spec = formSpec(form);
    assert.equal(spec.structured.budget_cny_max, 1000000);
    assert.equal(spec.structured.phase1_budget_cny, 500000);
  }
  const result = inferRequirements('最高1.4米，用华为逆变器', {...base,maxHeight:1,inverterBrand:'Sungrow',inverterBrandPicked:true}, roof);
  assert.equal(result.form.maxHeight, 1);
  assert.equal(result.form.inverterBrand, 'Sungrow');
  assert.throws(() => formSpec({...base, phaseKw:20, phaseBudget:10}), /只能填一项/);
});

test('recognized device digits do not hide other unknown numbers and labels are readable', () => {
  const inferred = inferRequirements('指定 SUN2000-100KTL-M2，预算百万，只自用，用华为逆变器', base, roof);
  assert.equal(inferred.unknown, '预算百万');
  const readable = inferRequirements('只自用，用华为逆变器', base, roof);
  assert.match(readable.summary, /只自用不上网：是/);
  assert.match(readable.summary, /逆变器品牌：华为/);
});
