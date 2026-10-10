"""Real offline form, park persistence, project transfer and financial display."""
import json
from pathlib import Path

from guangzhu import brief, mcp_actions, park_queue, park_store, project as storage
from test_t16_dom import browser_app
from test_t29_dom import park_browser
from test_t29_api_report import parks_api
from test_t29_store import workspace

ROOT = Path(__file__).resolve().parents[1]



def unfold(page):
    """Result details sit in folded sections; open them all as a reader would before reading the tables."""
    page.wait_for_selector('#result-panel .engineering', state='attached')
    page.evaluate("document.querySelectorAll('details.fold').forEach(d => d.open = true)")

def test_real_park_form_brief_project_economics_roundtrip(park_browser, monkeypatch):
    page, errors, root, _ = park_browser
    page.locator('[data-config="low"]').click()
    page.locator('[data-field="text"]').fill('贷款设计并保留检修通道')
    for key, value in [('loanRatio', '50'), ('loanRate', '5'), ('loanYears', '20'), ('cleaningTimes', '3'),
                       ('fAge', '12'), ('fKva', '315')]:
        page.locator(f'[data-field="{key}"]').fill(value)
    page.locator('[data-field="tariffClass"]').select_option('single100')
    page.locator('[data-field="posttaxPayback"]').check()
    page.locator('[data-action="park-settings-save"]').click()
    page.locator('#park-map').wait_for()
    saved = park_store.load('factory', root).settings['low']
    assert saved['loanRatio'] == '50' and saved['posttaxPayback'] is True
    page.locator('[data-config="low"]').click()
    assert page.locator('[data-field="loanRate"]').input_value() == '5'
    assert page.locator('[data-field="posttaxPayback"]').is_checked()
    page.locator('[data-action="park-settings-save"]').click()
    page.locator('#park-map').wait_for()
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    spec = park_queue.load('factory', root).items[0].spec
    assert spec.economics.loan_ratio == .5 and spec.economics.loan_rate == .05
    assert spec.economics.loan_years == 20 and spec.economics.cleaning_times == 3
    assert spec.economics.posttax_payback is True and spec.economics.tariff_class == 'single100'
    assert spec.facts.roof_age_years == 12 and spec.facts.transformer_kva == 315
    monkeypatch.setattr(mcp_actions, 'ROOT', root)
    monkeypatch.setattr(storage, 'PROJECTS_DIR', root / 'projects')
    mcp_actions._new_project('t30-park-form', spec.template, economics={key: getattr(spec.economics, key) for key in brief.ECONOMICS_FIELDS
                                        if getattr(spec.economics, key) is not None},
                             facts=dict(roof_age_years=spec.facts.roof_age_years, transformer_kva=spec.facts.transformer_kva))
    project = storage.load('t30-park-form')
    assert project.economics.loan_ratio == .5 and project.economics.posttax_payback
    assert project.facts.roof_age_years == 12 and project.park.id == 'factory'
    assert not errors


def test_actual_result_financial_chart_and_source_proposal(browser_app, tmp_path):
    import os
    page, errors = browser_app
    folder = ROOT / 'reports/assets/T30/export'
    context = json.loads((folder / 'context.json').read_text(encoding='utf-8'))
    result = dict(project_id='t30-ui', version=1, project=context['project'], scene={'electrical': context['electrical']},
                  metrics=context['summary'], economics=context['economics'], versions=[], rules={}, selected_version=None)
    page.route('**/api/projects/t30-ui/result*', lambda route: route.fulfill(json=result))
    page.goto('http://offline.test/#result/t30-ui', wait_until='commit')
    unfold(page)
    page.locator('.financial-detail').wait_for()
    panel = page.locator('.financial-detail')
    text = panel.inner_text()
    assert all(term in text for term in ['造价明细', 'CPIA参考2.59', '加权自用电价', '贷款自有资金税后', '屋顶租赁', '380 V'])
    assert panel.locator('svg rect').count() == 576
    capture = folder.parent if os.environ.get('GUANGZHU_T30_CAPTURE') == '1' else tmp_path
    panel.locator('.cost-items').screenshot(path=str(capture / 'cost-ui.png'))
    panel.locator('svg').screenshot(path=str(capture / 'tariff-ui.png'))
    assert not errors
