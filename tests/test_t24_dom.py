"""Real browser screenshots and DOM checks for the T24 editor, scene and proposal."""
import json
import math
from pathlib import Path

from playwright.sync_api import sync_playwright

from guangzhu.config import ROOT
from test_roof_editor_dom import editor, click_at
from test_t24 import ASSETS, WRITE_EVIDENCE, offline_flow


def test_concave_hull_ridge_preview_is_the_saved_direction(editor):
    page, errors, root = editor
    points = [(0, 2), (1, 2), (1, 1), (2, 1), (2, 0), (3, 0), (3, 1), (4, 1), (4, 2), (5, 2),
              (5, 3), (4, 3), (4, 4), (3, 4), (3, 5), (2, 5), (2, 4), (1, 4), (1, 3), (0, 3)]
    payload = dict(name='凹阶梯屋顶', site=dict(lat=31.81, lon=119.97), roof=dict(
        outline=[[x * 10, y * 10] for x, y in points], height_m=9, parapet_height_m=0,
        load_capacity_kn_m2=.3, obstacles=[], keepouts=[]))
    reply = page.evaluate('''async payload => (await fetch('/api/my-roofs', {
        method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(payload)})).json()''', payload)
    page.goto('http://offline.test/#roof/' + reply['id'])
    page.reload()
    page.wait_for_selector('[data-re="roofMode"]')
    page.wait_for_function("document.querySelector('[data-re=\"name\"]').value === '凹阶梯屋顶'")
    page.select_option('[data-re="roofMode"]', 'metal-gable')
    first = page.locator('.re-ridge').get_attribute('points')
    page.select_option('[data-re="ridgeMode"]', 'short')
    last = page.locator('.re-ridge').get_attribute('points')
    assert first != last
    a, b = [[float(v) for v in point.split(',')] for point in last.split()]
    dx, dy = b[0] - a[0], a[1] - b[1]
    assert abs(abs(dx) - abs(dy)) < .001
    expected = math.degrees(math.atan2(-dy, dx)) % 360
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    records = [json.loads(file.read_text(encoding='utf-8')) for file in (root / 'data/my-roofs').glob('*/project.json')]
    metal = [p for p in records if p['roof']['type'] == 'metal']
    assert len(metal) == 2
    actual = sorted(round(p['roof']['slope_azimuth_deg'], 6) for p in metal)
    assert actual == sorted([round(expected, 6), round((expected + 180) % 360, 6)])
    assert not errors


def test_irregular_roof_default_ridge_long_short_and_single_slope(editor):
    page, errors, root = editor
    page.click('[data-re-mode="1"]')
    page.click('[data-re-act="trace"]')
    for p in [(0, 0), (60, 0), (50, 30), (10, 30)]:
        click_at(page, *p)
    page.click('[data-re-act="close"]')
    page.select_option('[data-re="roofMode"]', 'metal-gable')
    long_line = page.locator('.re-ridge').get_attribute('points')
    assert long_line and len(long_line.split()) == 2
    page.select_option('[data-re="ridgeMode"]', 'short')
    short_line = page.locator('.re-ridge').get_attribute('points')
    assert short_line != long_line and len(short_line.split()) == 2
    page.select_option('[data-re="roofMode"]', 'metal-single')
    for angle in range(0, 360, 45):
        page.click(f'[data-re-act="azimuth-{angle}"]')
        assert page.input_value('[data-re="azimuth"]') == str(angle)
    page.click('[data-re-act="azimuth-0"]')
    page.fill('[data-re="name"]', '梯形北坡')
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    saved = list((root / 'data/my-roofs').glob('*/project.json'))
    assert len(saved) == 1
    p = json.loads(saved[0].read_text(encoding='utf-8'))
    assert p['roof']['slope_azimuth_deg'] == 0 and p['roof']['slope_deg'] == 5
    page.route('**/api/projects/*/exists', lambda route: route.fulfill(json=dict(exists=False)))
    page.click(f'[data-roof="{p["id"]}"]')
    page.locator('a[href="#form"]').click()
    page.wait_for_selector('[data-field="tiltMin"]')
    for field in ['tiltMin', 'tiltMax', 'prefer', 'compare']:
        assert page.locator(f'[data-field="{field}"]').is_disabled()
    assert '倾角等于坡度 5°' in page.locator('#tilt-hint').inner_text()
    assert page.evaluate('window.testApp.state.form.compare') is False
    page.fill('[data-field="text"]', '按彩钢瓦顺坡平铺')
    page.wait_for_function("document.querySelector('#brief-pre').textContent.includes('\"compare\":false')")
    assert not errors


def test_gable_editor_save_cross_ridge_and_independent_edit(editor, tmp_path):
    shots = ASSETS if WRITE_EVIDENCE else tmp_path  # committed evidence changes only on request
    page, errors, root = editor
    page.select_option('[data-re="roofMode"]', 'metal-gable')
    page.fill('[data-re="name"]', '双坡验收示意')
    assert page.input_value('[data-re="parapet"]') == '0'
    assert page.input_value('[data-re="load"]') == '0.3'
    page.click('[data-re-tool="skylight"]')
    click_at(page, 20, 10)
    click_at(page, 21, 25)
    page.click('[data-re-act="save"]')
    page.wait_for_function("document.body.textContent.includes('请分成两个')")
    assert not list((root / 'data/my-roofs').glob('*/project.json'))
    page.click('[data-re-remove="0"]')
    page.click('[data-re-tool="skylight"]')
    click_at(page, 20, 1)
    click_at(page, 21, 16)
    shots.mkdir(parents=True, exist_ok=True)
    page.wait_for_function("document.getElementById('notice').hidden")
    page.locator('[data-re="roofMode"]').scroll_into_view_if_needed()
    page.screenshot(path=str(shots / 'gable-editor.png'))
    assert page.locator('.re-ridge').count() == 1
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    files = list((root / 'data/my-roofs').glob('*/project.json'))
    assert len(files) == 2
    records = [json.loads(file.read_text(encoding='utf-8')) for file in files]
    assert {p['roof']['slope_azimuth_deg'] for p in records} == {0, 180}
    south = next(p for p in records if p['roof']['slope_azimuth_deg'] == 180)
    page.click(f'[data-roof="{south["id"]}"]')
    page.locator('a[href^="#roof/"]').click()
    page.fill('[data-re="slope"]', '6')
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    edited = json.loads(next(file for file in files if file.parent.name == south['id']).read_text(encoding='utf-8'))
    assert edited['roof']['building'] == '双坡验收示意' and edited['roof']['slope_deg'] == 6
    assert not errors


def test_real_scene_and_proposal_screenshots(offline_flow, tmp_path):
    shots = ASSETS if WRITE_EVIDENCE else tmp_path
    contents, scene = offline_flow
    web = ROOT / 'desktop/web'
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge', headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1440, height=900))
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        source = '''<html lang="zh"><meta charset="utf-8"><body style="margin:0;background:#f4ece3">
            <h2 style="padding:16px">常州彩钢瓦南坡示意 · 5° · 夹具顺坡平铺</h2>
            <div id="scene" style="width:1440px;height:780px"></div>
            <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
            <script type="module">import {createScene} from '/scene.js';
            import {normalizeScene} from '/scene-data.js';
            const input=await (await fetch('/data.json')).json();
            window.geometry=normalizeScene(input);
            window.viewer=createScene(document.querySelector('#scene'));
            window.viewer.setData(input);</script></body></html>'''

        def route(request):
            path = request.request.url.split('offline.test')[-1]
            if path == '/':
                request.fulfill(body=source, content_type='text/html')
            elif path == '/data.json':
                request.fulfill(json=scene)
            else:
                file = web / path.lstrip('/')
                request.fulfill(path=str(file)) if file.is_file() else request.abort()

        page.route('**/*', route)
        page.goto('http://offline.test/')
        page.wait_for_function('window.viewer?.stats().frames > 3')
        assert page.evaluate('window.viewer.stats().panels') == len(scene['design']['modules'])
        heights = page.evaluate('window.geometry.roof.outline.map(p=>window.geometry.elevation(p))')
        assert max(heights) > 1.5 and min(heights) == 0
        first = page.evaluate('window.geometry.modules[0]')
        assert first['position'][1] == scene['design']['modules'][0]['center'][2] + 9
        page.screenshot(path=str(shots / 'sloped-scene.png'))
        page.set_content(contents)
        page.locator('section.layout').screenshot(path=str(shots / 'proposal-page.png'))
        page.pdf(path=str(shots / 'proposal.pdf'), print_background=True)
        assert '夹具顺坡平铺，没有压块' in page.locator('section.layout').inner_text()
        assert '朝南（180°）' in page.locator('section.layout').inner_text()
        assert not errors
        browser.close()
