"""Segment edits must survive the real API and agree with the preview geometry."""
import pytest

from test_roof_editor_dom import editor, saved  # noqa: F401


def open_parapets(page):
    panel = page.locator('#re-parapets')
    if panel.get_attribute('open') is None:
        panel.locator('summary').click()


def field(page, row, key):
    return page.locator(f'[data-parapet-row="{row}"][data-parapet-key="{key}"]')


def test_partial_wall_metres_save_reopen_undo_and_empty_override(editor):
    from urllib.parse import urlsplit
    from fastapi.testclient import TestClient
    from guangzhu import api
    from guangzhu.config import API_ORIGIN

    page, errors, root = editor
    # The editor fixture normally stops at #new; #form also checks project-ID availability.
    backend = TestClient(api.app, base_url=API_ORIGIN, headers={'origin': API_ORIGIN})
    availability_requests = []
    def forward_availability(route):
        path = urlsplit(route.request.url).path
        reply = backend.get(path)
        availability_requests.append(path)
        route.fulfill(status=reply.status_code, body=reply.content, content_type=reply.headers.get('content-type'))
    page.route('**/api/projects/*/exists', forward_availability)
    open_parapets(page)
    page.locator('[data-re-act="parapet-custom"]').click()
    field(page, 0, 'start_m').fill('6')
    field(page, 0, 'end_m').fill('12')
    field(page, 0, 'height_m').fill('1.5')
    page.locator('[data-re="name"]').fill('有检修缺口的分段女儿墙')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    project, folder = saved(root)
    row = project['roof']['parapet_segments'][0]
    assert row == dict(edge_index=0, start_ratio=.1, end_ratio=.2, height_m=1.5)
    page.wait_for_selector('.preview .facts')
    assert '4 段' in page.locator('.preview .facts').text_content()
    page.locator('.preview a[href="#form"]').click()
    page.wait_for_selector('[data-field="parapetCap"]')
    assert availability_requests
    assert page.locator('[data-field="parapetCap"]').is_disabled()
    assert '分段女儿墙没有全周统一限高' in page.locator('#view').text_content()
    page.goto('http://offline.test/#roof/' + folder.name)
    page.wait_for_selector('#re-parapets')
    open_parapets(page)
    assert float(field(page, 0, 'start_m').input_value()) == 6
    field(page, 0, 'height_m').fill('2')
    page.locator('[data-re-act="undo"]').click()
    open_parapets(page)
    assert float(field(page, 0, 'height_m').input_value()) == 1.5
    page.locator('[data-re-act="parapet-none"]').click()
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    project, _ = saved(root)
    assert project['roof']['parapet_segments'] == []
    assert project['roof']['parapet_height_m'] == 1  # empty list must override this legacy default
    assert not errors


def test_empty_default_height_does_not_create_invalid_wall_or_break_panel(editor):
    page, errors, root = editor
    open_parapets(page)
    page.locator('[data-re-act="parapet-none"]').click()
    page.locator('[data-re="parapet"]').fill('')
    page.locator('[data-re-act="parapet-add"]').click()
    page.wait_for_function("document.querySelector('#notice').textContent.includes('初始高度')")
    assert page.locator('.re-parapet-row').count() == 0
    page.locator('[data-re="parapet"]').fill('1')
    page.locator('[data-re-act="parapet-add"]').click()
    assert page.locator('.re-parapet-row').count() == 1
    assert not errors


def test_outline_change_requires_explicit_rebuild_before_save(editor):
    page, errors, root = editor
    open_parapets(page)
    page.locator('[data-re-act="parapet-custom"]').click()
    page.locator('[data-re-rect="w"]').fill('80')
    page.locator('[data-re="name"]').fill('轮廓改动不可错配旧墙')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("document.querySelector('#notice').textContent.includes('轮廓')")
    assert not list((root / 'data/my-roofs').glob('*/project.json'))
    open_parapets(page)
    page.locator('[data-re-act="parapet-reset"]').click()
    assert float(field(page, 0, 'end_m').input_value()) == 80
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    project, _ = saved(root)
    assert len(project['roof']['parapet_segments']) == 4
    assert not errors


def test_overlapping_or_reversed_wall_segments_do_not_save(editor):
    page, errors, root = editor
    open_parapets(page)
    page.locator('[data-re-act="parapet-custom"]').click()
    field(page, 1, 'edge_index').select_option('0')
    page.locator('[data-re="name"]').fill('重叠分段必须报错')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("document.querySelector('#notice').textContent.includes('重叠')")
    assert not list((root / 'data/my-roofs').glob('*/project.json'))
    field(page, 1, 'edge_index').select_option('1')
    field(page, 0, 'start_m').fill('40')
    field(page, 0, 'end_m').fill('20')
    page.locator('[data-re-act="save"]').click()
    assert not list((root / 'data/my-roofs').glob('*/project.json'))
    assert not errors


def test_flat_preview_uses_backend_segment_geometry(editor):
    page, errors, root = editor
    source = '''export function createScene(){return {
      dispose(){},highlightRoofPlanes(){},resetView(){},
      setData(data){window.parapetPreview=structuredClone(data);},stats(){return {};}
    };}'''
    page.route('**/scene.js', lambda route: route.fulfill(body=source, content_type='text/javascript'))
    page.reload()
    page.wait_for_selector('#re-parapets')
    open_parapets(page)
    page.locator('[data-re-act="parapet-none"]').click()
    page.locator('[data-re-act="parapet-add"]').click()
    field(page, 0, 'start_m').fill('6')
    field(page, 0, 'end_m').fill('12')
    field(page, 0, 'height_m').fill('1.5')
    page.locator('[data-re-act="model-view"]').click()
    page.wait_for_function('window.parapetPreview?.roof_geometry?.parapets?.length === 1')
    faces = page.evaluate('window.parapetPreview.roof_geometry.parapets')
    assert len(faces) == 1
    # The authoritative points are in metres relative to the roof height, not ground.
    points = faces[0] if isinstance(faces[0], list) else faces[0]['points']
    assert sorted({point[0] for point in points}) == pytest.approx([6,12])
    assert {point[1] for point in points} == {0}
    assert sorted({point[2] for point in points}) == pytest.approx([0,1.5])
    assert not errors
