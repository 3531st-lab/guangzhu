"""Manual module controls cross real browser, request and versioned geometry boundaries."""
import json

import pytest

from test_t16_dom import browser_app  # noqa: F401
from test_manual_modules import factory  # noqa: F401
from test_design_edits_api import edit_client  # noqa: F401
from test_design_edits_async_dom import SCENE_RECORDER, assert_both_views, geometry
from guangzhu import api, project as storage


@pytest.fixture
def editor_factory(factory, monkeypatch):
    monkeypatch.setattr(api, 'ROOT', storage.PROJECTS_DIR.parent)
    return factory


def open_editor(page, record, edit_client, hold=None, version=1):
    requests = []
    page.route('**/scene.js', lambda route: route.fulfill(body=SCENE_RECORDER, content_type='text/javascript'))

    def forward(route):
        request = route.request
        response = edit_client.request(request.method, request.url.split('offline.test', 1)[-1],
                                       content=request.post_data_buffer, headers={'content-type': 'application/json'})
        requests.append((request.url, request.post_data_json if request.post_data else None))
        if hold is not None and request.url.endswith('/design-edits/preview'):
            hold.append((route, response))
        else:
            route.fulfill(status=response.status_code, body=response.content, content_type='application/json')

    page.route(f'**/api/projects/{record.id}/**', forward)
    page.goto(f'http://offline.test/#result/{record.id}?version={version}')
    page.reload()
    page.locator('[data-result-tab="局部修改"]').click()
    return requests


def commit(page, version):
    candidate = page.evaluate('testApp.state.editing.preview.design')
    page.locator('[data-design-edit="apply"]').click()
    page.wait_for_function(f"testApp.state.result?.version === {version} && document.querySelector('.de-editor') && !testApp.state.editing.preview")
    saved = page.evaluate('testApp.state.result.design')
    assert geometry(saved) == geometry(candidate)
    assert_both_views(page, saved)
    return saved


def test_pick_add_move_rotate_undo_and_lock_preserve_saved_geometry(browser_app, editor_factory, edit_client):
    page, errors = browser_app
    record, initial = editor_factory()
    before = storage._path(record.id, 'designs/v1.json').read_bytes()
    requests = open_editor(page, record, edit_client)
    assert_both_views(page, initial.model_dump(mode='json'))
    page.locator('[data-design-edit="pick-add"]').click()
    point = page.locator('.de-plan').evaluate('''svg=>{const p=svg.createSVGPoint();p.x=8;p.y=-9;
      const q=p.matrixTransform(svg.getScreenCTM());return {x:q.x,y:q.y};}''')
    page.mouse.click(point['x'], point['y'])
    # Native pointer events resolve to CSS pixels; precise numeric entry refines the picked center.
    assert float(page.locator('[data-edit-add="x"]').input_value()) == pytest.approx(8, abs=.15)
    assert float(page.locator('[data-edit-add="y"]').input_value()) == pytest.approx(9, abs=.15)
    page.locator('[data-edit-add="x"]').fill('8')
    page.locator('[data-edit-add="y"]').fill('9')
    page.locator('[data-design-edit="add"]').click()
    page.locator('.de-preview').wait_for()
    preview = page.evaluate('testApp.state.editing.preview.design')
    assert len(preview['modules']) == 1 and preview['modules'][0]['center'][:2] == pytest.approx([8, 9], abs=.001)
    assert storage.next_version(record.id) == 2
    assert page.locator('[data-edit-change="added"]').count() == 1
    placed = commit(page, 2)
    mid = placed['modules'][0]['id']
    page.locator(f'[data-edit-module="{mid}"]').click()
    page.locator('[data-edit-field="manualMode"]').select_option('move')
    page.locator('[data-edit-move="dx"]').fill('2.25')
    page.locator('[data-edit-move="dy"]').fill('-1.5')
    page.locator('[data-design-edit="move"]').click()
    page.locator('.de-preview').wait_for()
    candidate = page.evaluate('testApp.state.editing.preview.design')
    assert candidate['modules'][0]['center'][:2] == pytest.approx([10.25, 7.5], abs=.001)
    assert page.locator('[data-edit-before]').count() == 1
    assert page.locator('[data-edit-change="moved"]').count() == 1
    assert_both_views(page, candidate)
    moved = commit(page, 3)
    page.locator(f'[data-edit-module="{mid}"]').click()
    page.locator('[data-edit-field="manualMode"]').select_option('rotate')
    page.locator('[data-edit-rotate="angle"]').fill('37')
    page.locator('[data-design-edit="rotate"]').click()
    page.locator('.de-preview').wait_for()
    candidate = page.evaluate('testApp.state.editing.preview.design')
    assert candidate['modules'][0]['center'] == pytest.approx(moved['modules'][0]['center'])
    assert candidate['modules'][0]['azimuth'] == pytest.approx(moved['modules'][0]['azimuth'] + 37)
    assert page.locator('[data-edit-change="rotated"]').count() == 1
    rotated = commit(page, 4)
    assert geometry(rotated) != geometry(moved)
    page.locator('[data-design-edit="undo"]').click()
    page.locator('.de-preview').wait_for()
    undone = commit(page, 5)
    assert geometry(undone) == geometry(moved)
    page.locator(f'[data-edit-module="{mid}"]').click()
    page.locator('[data-design-edit="lock"]').click()
    page.locator('.de-preview').wait_for()
    commit(page, 6)
    page.locator(f'[data-edit-module="{mid}"]').click()
    for mode in ['move', 'rotate']:
        page.locator('[data-edit-field="manualMode"]').select_option(mode)
        assert page.locator(f'[data-design-edit="{mode}"]').is_disabled()
    assert page.locator('[data-design-edit="remove"]').is_disabled()
    assert '已锁定' in page.locator('.de-editor').inner_text()
    assert storage._path(record.id, 'designs/v1.json').read_bytes() == before
    ops = [body['ops'][0]['op'] for url, body in requests if url.endswith('/design-edits/preview')]
    assert ops == ['add_modules', 'move_modules', 'rotate_modules', 'undo_last_edit', 'lock_modules']
    assert not errors


def test_manual_inputs_and_cancel_keep_late_previews_out_of_both_views(browser_app, editor_factory, edit_client):
    page, errors = browser_app
    record, initial = editor_factory()
    pending = []
    open_editor(page, record, edit_client, hold=pending)
    original = initial.model_dump(mode='json')
    page.locator('[data-edit-add="x"]').fill('7')
    page.locator('[data-edit-add="y"]').fill('8')
    page.locator('[data-design-edit="add"]').click()
    page.wait_for_function('testApp.state.editing.busy')
    page.locator('[data-edit-add="x"]').fill('11')
    assert not page.evaluate('testApp.state.editing.busy')
    page.locator('[data-design-edit="add"]').click()
    page.wait_for_function('testApp.state.editing.busy')
    assert len(pending) == 2
    route, response = pending.pop()
    assert response.status_code == 200, response.text
    route.fulfill(status=response.status_code, body=response.content, content_type='application/json')
    page.locator('.de-preview').wait_for()
    latest = page.evaluate('testApp.state.editing.preview.design')
    assert latest['modules'][0]['center'][:2] == pytest.approx([11, 8])
    assert_both_views(page, latest)
    route, response = pending.pop()
    assert response.status_code == 200, response.text
    route.fulfill(status=response.status_code, body=response.content, content_type='application/json')
    page.wait_for_timeout(100)
    assert_both_views(page, latest)
    page.locator('[data-design-edit="cancel"]').click()
    assert_both_views(page, original)
    page.locator('[data-design-edit="add"]').click()
    page.wait_for_function('testApp.state.editing.busy')
    page.locator('[data-design-edit="cancel"]').click()
    assert_both_views(page, original)
    route, response = pending.pop()
    route.fulfill(status=response.status_code, body=response.content, content_type='application/json')
    page.wait_for_timeout(100)
    assert page.locator('.de-preview').count() == 0
    assert page.evaluate('testApp.state.editing.preview') is None
    assert_both_views(page, original)
    assert storage.next_version(record.id) == 2
    assert not errors


def test_candidate_hides_saved_wind_and_wiring_across_scene_modes_and_restores_on_cancel(
        browser_app, editor_factory, edit_client):
    page, errors = browser_app
    record, _ = editor_factory()
    analysis = storage._path(record.id, 'analysis/v1')
    analysis.mkdir(parents=True, exist_ok=True)
    wind = dict(version=1,city=dict(city='原版本风荷载',distance_km=0,selection='fixture'),basic_pressure_kpa=.4,
                worst_zone='middle',zones=dict(middle=dict(label='中部',load_kn_m2=.2,modules=0,ballast_blocks=0,ballast_kg=0)),
                clamp_required=0,clamp_count=0,clamp_failed=0,missing='仅供原版本显示测试',note='')
    electrical = dict(version=1,strings=[dict(id='S-old',module_ids=['old'],inverter=1,mppt=1)],
                      wiring=dict(method='fixture',reason='保存版本显示检查'),
                      cables=dict(total_length_m=20,routing=dict(saved_dc_m=1,blocked_routes=0),summary=[],positions=[],notes=[]))
    (analysis / 'structure.json').write_text(json.dumps(dict(wind=wind)), encoding='utf-8')
    (analysis / 'electrical.json').write_text(json.dumps(electrical), encoding='utf-8')
    response = edit_client.get(f'/api/projects/{record.id}/result?version=1')
    assert response.status_code == 200, response.text
    open_editor(page, record, edit_client)
    page.locator('[data-scene-mode="wiring"]').click()
    assert page.locator('#wiring-tools').is_visible()
    assert page.locator('#wind-summary').is_visible()
    page.locator('#wind-summary').evaluate('element=>element.open=true')
    assert 'L01 通过' in page.locator('#wind-summary').inner_text()
    page.locator('[data-edit-add="x"]').fill('8')
    page.locator('[data-edit-add="y"]').fill('9')
    page.locator('[data-design-edit="add"]').click()
    page.locator('.de-preview').wait_for()
    for mode in ['light', 'wind', 'heat', 'wiring']:
        page.locator(f'[data-scene-mode="{mode}"]').click()
        assert page.locator('#wind-summary').is_hidden()
        assert page.locator('#wiring-tools').is_hidden()
        assert page.locator('#heat-legend').is_hidden()
    # Returning to the original result tab restores its evidence; entering preview hides it again.
    page.locator('[data-result-tab="结论"]').click()
    assert page.locator('#wind-summary').is_visible()
    assert page.locator('#wiring-tools').is_visible()
    page.locator('[data-result-tab="局部修改"]').click()
    assert page.locator('#wind-summary').is_hidden()
    assert page.locator('#wiring-tools').is_hidden()
    page.locator('[data-design-edit="cancel"]').click()
    assert page.locator('#wind-summary').is_visible()
    assert page.locator('#wind-summary').evaluate('element=>element.open')
    assert page.locator('#wiring-tools').is_visible()
    assert 'S-old' in page.locator('#wire-string').inner_text()
    assert not errors
