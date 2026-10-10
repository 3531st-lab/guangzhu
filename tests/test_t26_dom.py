"""T26 real offline DOM evidence; committed screenshots require explicit capture."""
import json
import os
from pathlib import Path

from guangzhu.config import ROOT
from test_roof_editor_dom import editor, click_at, saved
from test_t26 import cable_context
from test_t16_dom import browser_app
from test_roof_editor_fixes import drag



def unfold(page):
    """Result details sit in folded sections; open them all as a reader would before reading the tables."""
    page.wait_for_selector('#result-panel .engineering', state='attached')
    page.evaluate("document.querySelectorAll('details.fold').forEach(d => d.open = true)")

def assets(tmp_path):
    directory = ROOT / 'reports/assets/T26' if os.environ.get('GUANGZHU_T26_CAPTURE') == '1' else tmp_path
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_electrical_point_editor_round_trip_undo_and_grid_replacement(editor, tmp_path):
    page, errors, root = editor
    for tool, point in [('inverter', (2, 4)), ('inverter', (40, 4)), ('grid', (0, 10)), ('grid', (0, 20))]:
        page.click(f'[data-re-tool="{tool}"]')
        click_at(page, *point)
    assert page.locator('.re-item').count() == 3
    page.click('[data-re-act="undo"]')
    page.click('[data-re-act="redo"]')
    assert page.locator('.re-electrical').count() == 3
    assert page.locator('.re-electrical').first.evaluate('e => getComputedStyle(e).fill') == 'rgb(200, 119, 67)'
    assert page.locator('.re-electrical').first.evaluate('e => getComputedStyle(e).stroke') == 'rgb(255, 255, 255)'
    drag(page, (2, 4), (4, 6))
    drag(page, (0, 20), (5, 20))
    page.fill('[data-re="name"]', '电缆位置验收')
    page.screenshot(path=str(assets(tmp_path) / 'editor.png'))
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    project, folder = saved(root)
    assert project['roof']['inverter_positions'] == [[4, 6], [40, 4]]
    assert project['roof']['grid_point'] == [5, 20]
    assert project['roof']['obstacles'] == []
    page.evaluate(f"location.hash = '#roof/{folder.name}'")
    page.wait_for_selector('[data-re-tool="inverter"]')
    assert page.locator('.re-item').count() == 3
    page.click('[data-re-remove="2"]')
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    assert 'grid_point' not in saved(root)[0]['roof']
    assert not errors


def test_proposal_and_string_scene(cable_context, tmp_path):
    from playwright.sync_api import sync_playwright
    from guangzhu.report.view import render
    directory = assets(tmp_path)
    c = cable_context
    with sync_playwright() as driver:
        browser = driver.chromium.launch(channel='msedge', headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1440, height=900))
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        html = '''<meta charset="utf-8"><body style="margin:0"><div id="scene" style="width:1440px;height:900px"></div>
            <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
            <script type="module">import {createScene} from '/scene.js';
            window.viewer=createScene(document.querySelector('#scene'));
            viewer.setData(await (await fetch('/data.json')).json());viewer.setMode('string');</script>'''
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
        assert page.evaluate('viewer.stats().cableRoutes') == len(c['electrical']['cables']['dc']) + len(c['electrical']['cables']['ac'])
        page.screenshot(path=str(directory / 'string-scene.png'))
        page.set_content(render(c))
        page.locator('section.cables').screenshot(path=str(directory / 'proposal-cables.png'))
        assert page.locator('section.cables tbody tr').count() == len(c['electrical']['cables']['summary'])
        assert not errors
        browser.close()


def test_result_cable_table(browser_app, cable_context, tmp_path):
    page, errors = browser_app
    c = cable_context
    result = dict(project_id=c['project_id'], version=1, project=c['project'], scene={'electrical': c['electrical']},
                  metrics=c['summary'], economics=c['economics'], versions=[], rules={}, selected_version=None)
    page.route('**/api/projects/t26-offline/result*', lambda route: route.fulfill(json=result))
    page.goto('http://offline.test/#result/t26-offline', wait_until='commit')
    unfold(page)
    page.wait_for_selector('.cable-table')
    assert page.locator('.cable-table tbody tr').count() == len(c['electrical']['cables']['summary'])
    assert '示意，按现场改' in page.locator('#result-panel').inner_text()
    page.locator('.engineering').screenshot(path=str(assets(tmp_path) / 'result-cables.png'))
    assert not errors
