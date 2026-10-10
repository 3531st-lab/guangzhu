"""T23 condition/result/proposal DOM checks, all requests intercepted offline."""
import copy
import json

from guangzhu import brief, economics, electrical
from guangzhu.config import ROOT
from guangzhu.report.archive import load_archive
from guangzhu.report.view import render
from test_t16_dom import browser_app  # noqa: F401
from test_t23 import factory



def unfold(page):
    """Result details sit in folded sections; open them all as a reader would before reading the tables."""
    page.wait_for_selector('#result-panel .engineering', state='attached')
    page.evaluate("document.querySelectorAll('details.fold').forEach(d => d.open = true)")

def test_load_answers_condition_dom(browser_app):
    page, errors = browser_app
    captured = []
    def reply(route):
        spec = json.loads(route.request.post_data)
        captured.append(spec)
        route.fulfill(json={'brief': brief.render_brief(spec) if spec.get('text') else '', 'errors': []})
    page.route('**/api/brief', reply)
    page.goto('http://offline.test/#form', wait_until='commit')
    page.wait_for_selector('[data-field="fKwh"]')
    page.fill('[data-field="text"]', '按工厂用电算')
    page.fill('[data-field="fKwh"]', '1.2')
    page.select_option('[data-field="fShifts"]', '2')
    page.select_option('[data-field="fExport"]', '0')
    page.wait_for_function("document.querySelector('#brief-pre').textContent.includes('\"shifts\":2')")
    data = json.loads(page.text_content('#brief-pre').split('```json\n')[1].split('\n```')[0])
    assert data['economics'] == dict(monthly_kwh=12000, shifts=2, price_export_cny_kwh=0)
    assert '手填比例优先' in page.locator('body').inner_text()
    assert not errors


def test_result_and_proposal_show_mix_reference_and_three_models(browser_app):
    page, errors = browser_app
    context = load_archive(ROOT / 'runs/gz-t14-impossible-001')
    p = factory()
    p.economics.monthly_kwh, p.economics.shifts, p.economics.self_use_ratio = 1e9, 1, .7
    p.economics.price_export_cny_kwh = 0
    energy = dict(p50=150000, low=140000, high=160000, hourly=dict(utc=['2023-01-02T00:00:00+00:00'], kwh=[150000]))
    cash = economics.calculate(p, 100, energy)
    el = copy.deepcopy(context['electrical'])
    identifiers = [m['id'] for m in context['design']['modules']]
    el['strings'] = [dict(id='S001', module_ids=identifiers[:26]), dict(id='S002', module_ids=identifiers[:25])]
    el['inverters'] = [dict(model='SG125CX-P2', count=1), dict(model='SG50CX-P2', count=1)]
    result = dict(project_id='t23-dom', version=1, project=context['project'], scene={'electrical': el},
                  metrics=context['summary'], economics=cash, versions=[], rules={}, selected_version=None)
    page.route('**/api/projects/t23-dom/result*', lambda route: route.fulfill(json=result))
    page.goto('http://offline.test/#result/t23-dom', wait_until='commit')
    unfold(page)
    page.wait_for_selector('.business-models')
    text = page.text_content('#result-panel')
    assert '26 块 × 1 串、25 块 × 1 串' in text and 'SG125CX-P2 × 1 + SG50CX-P2 × 1' in text
    assert '手填比例优先' in text and '逐时参考 100.0%' in text and '余电收入 0 元' in text and '用不完的电被限掉' not in text
    assert page.locator('.business-models tbody tr').count() == 3 and not errors
    context['economics'], context['electrical'] = cash, el
    page.set_content(render(context))
    business = page.locator('section.business.newpage')
    assert business.locator('tbody tr').count() == 3
    assert '逐时参考 100.0%' in business.inner_text() and '允许物理上网；当前余电售电价为0元' in business.inner_text()
    p.economics.monthly_kwh = None
    result['economics'] = economics.calculate(p, 100, energy)
    page.reload(wait_until='commit')
    unfold(page)
    page.wait_for_selector('.business-models')
    assert '手填比例均摊到各小时' in page.text_content('#result-panel') and '逐时参考' not in page.text_content('#result-panel')
    context['economics'] = result['economics']
    page.set_content(render(context))
    assert '手填比例均摊到各小时' in page.locator('section.business').inner_text()
    assert '逐时参考' not in page.locator('section.business').inner_text()
    p.economics.monthly_kwh, p.economics.self_use_ratio = 1, None
    context['economics'] = economics.calculate(p, 100, energy)
    assert context['economics']['payback_years'] is None
    page.set_content(render(context))
    assert '无可算差值（基准或情景未回本）' in page.locator('body').inner_text()
    assert page.locator('section.business tbody tr').count() == 3
