import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {show,rawValue,valueMarkup,modelChoices} from '../../desktop/web/data.js';
const units={roof_area_m2:'m²',dc_kw:'kW','economics.payback_years':'年','economics.irr_pct':'%',annual_ghi_kwh_m2:'kWh/m²'};

test.skip('forty native display values match independent Decimal rounding and preserve raw hover text',()=>{
  const input=JSON.parse(readFileSync(new URL('../../reports/assets/T14-r1/frontend/rounding-inputs.json',import.meta.url),'utf8'));
  assert.equal(input.rows.length,40);
  for(const row of input.rows) {
    const unit=units[row.field]??row.unit;
    assert.equal(show(row.raw_value,unit),row.expected_display,`${row.run_id}/${row.section}/${row.field}`);
    assert.match(valueMarkup(row.raw_value,unit),new RegExp('原值 '+String(row.raw_value).replace(/[.]/g,'\\.')));
  }
});

test('display preserves missing and raw values while translating booleans, lists and option measurements',()=>{
  assert.equal(show(null),'未提供');
  assert.equal(show(0,'kW'),'0.0');
  assert.equal(show(1.25,'kW'),'1.3');
  assert.equal(show(4.165,'m'),'4.17');
  assert.equal(show(true),'是');
  assert.equal(show(false),'否');
  assert.equal(show([]),'无');
  assert.equal(rawValue([]),'[]');
  assert.equal(rawValue(true),'true');
  assert.equal(show({dc_kw:123.45,payback_years:4.1566,meets_requirements:false}),'装机 kW：123.5；回本 年：4.16；满足要求：否');
  assert.match(valueMarkup('<script>'),/&lt;script&gt;/);
});

test('default Pro permits an available saved Flash choice and safely falls back when it disappears',()=>{
  const pro={id:'deepseek-v4-pro',route:'a'},flash={id:'deepseek-flash',route:'a'},review={id:'agnes'};
  assert.equal(modelChoices([flash,pro,review]).design,pro);
  assert.equal(modelChoices([flash,pro,review],'a/deepseek-flash').design,flash);
  assert.equal(modelChoices([pro,review],'a/deepseek-flash').design,pro);
  assert.equal(modelChoices([flash,pro,review]).review,review);
});
