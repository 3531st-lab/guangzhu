import test from 'node:test';
import assert from 'node:assert/strict';
import {formSpec, inferRequirements} from '../../desktop/web/data.js';
import {financialResult} from '../../desktop/web/economic-ui.js';

test('T30 explicit natural language maps financial fields without replacing hand entries', () => {
  const text = '贷款比例50%，年利率5%，贷款20年，每年清洗3次，按税后看回本，装之前翻新';
  const result = inferRequirements(text, {keep: [], loanRate: 4}, {});
  assert.equal(result.form.loanRatio, 50);
  assert.equal(result.form.loanRate, 4);
  assert.equal(result.form.loanYears, 20);
  assert.equal(result.form.cleaningTimes, 3);
  const spec = formSpec(result.form);
  assert.deepEqual(spec.economics, {loan_ratio: .5, loan_rate: .04, loan_years: 20,
    cleaning_times: 3, posttax_payback: true, refurbish: true});
});

test('T30 no loan or tax selection remains absent; zero rate and false remain deliberate inputs', () => {
  assert.deepEqual(formSpec({keep: []}).economics, {});
  const result = formSpec({keep: [], loanRatio: '50', loanRate: '0', posttaxPayback: false, tariffClass: 'two_part'});
  assert.deepEqual(result.economics, {loan_ratio: .5, loan_rate: 0, posttax_payback: false, tariff_class: 'two_part'});
  assert.equal(financialResult({capex_cny: 100}), '');
});
