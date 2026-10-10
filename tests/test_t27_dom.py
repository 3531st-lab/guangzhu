"""T27 visible selection and comparison; offline browser without an AGH instance."""
from test_t16_dom import browser_app


def test_form_defaults_and_comparison_layout_column(browser_app):
    page, errors = browser_app
    page.evaluate("location.hash='#form'")
    page.wait_for_selector('[data-field="text"]')
    assert page.locator('[data-field="moduleId"]').count() == 1
    assert page.evaluate('testApp.state.form.moduleId') == 'trina-tsm-605neg19rc20'
    assert '东西向' in page.locator('.runopts').inner_text()
    html = page.evaluate('''async () => {
        const {comparisonTable, formSpec} = await import('./data.js');
        const row = {name:'多装', version:2, align:'ew', fill_landscape_count:4, dc_kw:12, annual_kwh:13000,
                     payback_years:4, hard_pass:true, violated_requirements:[]};
        if (formSpec(testApp.state.form).equipment.module_id !== 'trina-tsm-605neg19rc20') throw Error('equipment missing');
        const current = {...row, name:'当前方案', version:1, align:'custom', azimuth_deg:200};
        return comparisonTable({current, options:[row], capacity_note:'冬至 10–14 时不挡'}, {});
    }''')
    assert '<th>排法</th>' in html and '东西向' in html and '横放补位 4 块' in html
    assert '朝向 200°' in html
    assert '10–14' in html and not errors
