"""Actual form persistence and result DOM; WebGL evidence is tested separately."""
import json
import os

from guangzhu.config import ROOT
from test_t16_dom import browser_app
from test_roof_editor_dom import editor


def test_wind_inputs_preserve_zero_city_and_clamp_settings(editor):
    page, errors, root = editor
    page.locator('.wind-input summary').click()
    page.locator('[data-re="name"]').fill('T31风参数验收')
    page.locator('[data-re="windCity"]').select_option(label='南京')
    page.locator('[data-wind="basic_pressure_kpa"]').fill('0')
    page.locator('[data-wind="roughness"]').select_option('C')
    page.locator('[data-re="roofMode"]').select_option('metal-single')
    page.locator('.wind-input summary').click()
    page.locator('[data-wind="clamp_capacity_kn"]').fill('1.1')
    page.locator('[data-wind="seam_azimuth_deg"]').fill('0')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    paths = list((root / 'data/my-roofs').glob('*/project.json'))
    assert len(paths) == 1
    saved = json.loads(paths[0].read_text(encoding='utf-8'))
    assert saved['site']['wind_city'] == '南京'
    values = saved['roof']['wind']
    assert values['basic_pressure_kpa'] == 0 and values['roughness'] == 'C'
    assert values['clamp_capacity_kn'] == 1.1 and values['seam_azimuth_deg'] == 0
    page.goto('http://offline.test/#roof/' + paths[0].parent.name)
    page.locator('.wind-input summary').click()
    assert page.locator('[data-wind="basic_pressure_kpa"]').input_value() == '0'
    assert page.locator('[data-re="windCity"]').input_value() == '南京'
    assert not errors


def test_result_uses_actual_wind_and_rejects_stale_version(browser_app, tmp_path):
    page, errors = browser_app
    folder = ROOT / 'reports/assets/T31/export'
    context = json.loads((folder / 'context.json').read_text(encoding='utf-8'))
    scene = json.loads((folder / 'scene.json').read_text(encoding='utf-8'))
    result = dict(project_id='t31-ui', version=1, project=context['project'], scene=scene,
                  metrics=context['summary'], economics=context['economics'], versions=[], rules={}, selected_version=None)
    page.route('**/api/projects/t31-ui/result*', lambda route: route.fulfill(json=result))
    page.goto('http://offline.test/#result/t31-ui', wait_until='commit')
    page.locator('.wind-result summary').click()
    text = page.locator('.wind-result').inner_text()
    assert all(term in text for term in ['不能代替结构计算', '缺GB50009', '角部', '边部', '中部'])
    assert 'L01 通过' in text and '屋面容量 3 kN/m²' in text
    assert page.locator('[data-scene-mode="wind"]').count() == 1
    capture = folder if os.environ.get('T31_CAPTURE') == '1' else tmp_path
    page.locator('.wind-result').screenshot(path=str(capture / 'wind-result-ui.png'))
    result['project']['roof']['load_capacity_kn_m2'] = .5
    page.reload()
    page.locator('.wind-result summary').click()
    assert 'L01 未通过' in page.locator('.wind-result').inner_text()
    result['scene']['wind']['version'] = 2
    page.reload()
    page.wait_for_selector('#scene')
    assert page.locator('.wind-result').count() == 0
    assert '旧记录不代表抗风已通过' in page.locator('body').inner_text()
    assert not errors
