"""Real local browser T28 acceptance; screenshots only captured on explicit request."""
import json
import os

from guangzhu.config import ROOT
from test_t16_dom import browser_app
from test_t28 import owner, phase_context


def assets(tmp_path):
    directory = ROOT / 'reports/assets/T28' if os.environ.get('GUANGZHU_T28_CAPTURE') == '1' else tmp_path
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_new_requirement_form_recognition_and_brief_payload(browser_app, tmp_path):
    page, errors = browser_app
    requests = []
    def preview(route):
        requests.append(route.request.post_data_json)
        route.fulfill(json=dict(brief='T28离线任务书预览', errors=[]))
    page.route('**/api/brief', preview)
    page.evaluate("location.hash='#form'")
    page.locator('[data-field="text"]').fill('只自用，限电不超过5%，变压器800千伏安，不超过变压器的70%，一期预算50万，用华为逆变器')
    page.wait_for_function("testApp.state.form.phaseBudget===50")
    assert page.locator('[data-field="noExport"]').is_checked()
    assert page.locator('[data-field="budget"]').input_value() == ''
    assert page.locator('[data-field="transformer"]').input_value() == '800'
    assert page.locator('[data-field="inverterBrand"]').input_value() == 'Huawei'
    page.locator('[data-field="parapetCap"]').check()
    assert page.locator('[data-field="maxHeight"]').input_value() == '1'
    page.wait_for_timeout(450)
    spec = requests[-1]
    assert spec['structured']['phase1_budget_cny'] == 500000 and spec['structured']['max_height_m'] == 1
    assert spec['structured']['export_allowed'] is False and spec['structured']['transformer_share'] == .7
    assert spec['equipment']['inverter_brand'] == 'Huawei'
    assert '一期预算' in page.locator('#recognized').inner_text()
    assert '只自用不上网：是' in page.locator('#recognized').inner_text()
    assert '逆变器品牌：华为' in page.locator('#recognized').inner_text()
    page.screenshot(path=str(assets(tmp_path) / 'requirements-form.png'), full_page=True)
    assert not errors


def test_phase_proposal_layout_and_real_three_scene(phase_context, tmp_path):
    from playwright.sync_api import sync_playwright
    from guangzhu.report.view import render
    from guangzhu.layout import plot_layout
    from guangzhu.models import Project, Design
    c, directory = phase_context, assets(tmp_path)
    plot_layout(Project.model_validate(c['project']), Design.model_validate(c['design']), directory / 'phase-layout.png')
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel='msedge', headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1440, height=900))
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        html = '''<meta charset="utf-8"><body style="margin:0"><div id="scene" style="width:1440px;height:900px"></div>
            <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
            <script type="module">import {createScene} from '/scene.js';
            window.viewer=createScene(document.querySelector('#scene'));
            viewer.setData(await (await fetch('/data.json')).json());viewer.setMode('phase');</script>'''
        def reply(route):
            path = route.request.url.split('offline.test')[-1]
            if path == '/':
                route.fulfill(body=html, content_type='text/html')
            elif path == '/data.json':
                route.fulfill(json={key: c[key] for key in ['project', 'design', 'electrical', 'shading']})
            else:
                file = ROOT / 'desktop/web' / path.lstrip('/')
                route.fulfill(path=str(file)) if file.is_file() else route.abort()
        page.route('**/*', reply)
        page.goto('http://offline.test/')
        page.wait_for_function('window.viewer?.stats().frames > 3 && viewer.stats().panels > 0')
        assert page.evaluate('viewer.stats().panels') == len(c['design']['modules'])
        page.screenshot(path=str(directory / 'phase-scene.png'))
        page.set_content(render(c))
        assert page.locator('section.phases tbody tr').count() == 3
        page.locator('section.phases').screenshot(path=str(directory / 'proposal-phases.png'))
        assert '一期绿色' in page.locator('section.phases').inner_text()
        assert not errors
        browser.close()
    if os.environ.get('GUANGZHU_T28_CAPTURE') == '1':
        from guangzhu.report.deliverables import write_deliverables
        write_deliverables(c['project_id'], 1, directory)
        (directory / 'proposal.html').write_text(render(c), encoding='utf-8')
        (directory / 'phase-context.json').write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding='utf-8')


def test_result_phase_and_height_rows(browser_app, phase_context):
    page, errors = browser_app
    c = phase_context
    result = dict(project_id=c['project_id'], version=1, project=c['project'], scene=dict(electrical=c['electrical']),
                  metrics=c['summary'], economics=c['economics'], versions=[], rules=c['rules'], selected_version=None)
    page.route('**/api/projects/t28-test/result*', lambda route: route.fulfill(json=result))
    page.goto('http://offline.test/#result/t28-test', wait_until='commit')
    page.wait_for_selector('.engineering')
    page.evaluate("document.querySelectorAll('details.fold').forEach(d => d.open = true)")
    assert '两期合计' in page.locator('.engineering').inner_text()
    assert '组件最高点' in page.locator('.engineering').inner_text()
    assert not errors
