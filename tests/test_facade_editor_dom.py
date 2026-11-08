"""Factory appearance edits through real controls, draft state and the save API."""
import os
from pathlib import Path

from test_roof_editor_dom import editor, saved  # noqa: F401


def open_facade(page):
    panel = page.locator('#re-facade')
    if panel.get_attribute('open') is None:
        panel.locator('summary').click()


def test_facade_controls_save_reopen_and_undo_as_one_preset(editor):
    page, errors, root = editor
    open_facade(page)
    page.locator('[data-re-act="facade-preset-brick"]').click()
    assert page.locator('[data-facade="wall_material"]').input_value() == 'brick'
    assert page.locator('[data-facade="wall_color"]').input_value() == '#ad7158'
    page.locator('[data-re-act="undo"]').click()
    assert page.locator('[data-facade="wall_material"]').input_value() == 'metal'
    assert page.locator('[data-facade="wall_color"]').input_value() == '#d6dde2'
    page.locator('[data-re-act="redo"]').click()
    page.locator('[data-facade="front_edge"]').select_option('1')
    assert '朝东' in page.locator('[data-facade="front_edge"] option:checked').text_content()
    assert '36 m' in page.locator('[data-facade="front_edge"] option:checked').text_content()
    page.locator('[data-facade="doors"]').fill('3')
    page.locator('[data-facade="window_rows"]').select_option('2')
    page.locator('[data-facade="window_sill_m"]').fill('2.8')
    page.locator('[data-facade="canopy_depth_m"]').fill('2.4')
    page.locator('[data-facade="personnel_door"]').uncheck()
    page.locator('[data-facade="columns"]').uncheck()
    page.locator('[data-re="name"]').fill('厂房建筑外观编辑')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    project, folder = saved(root)
    facade = project['roof']['facade']
    assert facade['wall_material'] == 'brick' and facade['wall_color'] == '#ad7158'
    assert (facade['front_edge'], facade['doors'], facade['window_rows']) == (1, 3, 2)
    assert (facade['window_sill_m'], facade['canopy_depth_m']) == (2.8, 2.4)
    assert facade['personnel_door'] is False and facade['columns'] is False
    page.goto('http://offline.test/#roof/' + folder.name)
    page.wait_for_selector('#re-facade')
    open_facade(page)
    assert page.locator('[data-facade="doors"]').input_value() == '3'
    assert page.locator('[data-facade="front_edge"]').input_value() == '1'
    assert not page.locator('[data-facade="columns"]').is_checked()
    page.locator('[data-re-act="facade-reset"]').click()
    assert page.locator('[data-facade="doors"]').input_value() == '2'
    page.locator('[data-re-act="undo"]').click()
    assert page.locator('[data-facade="doors"]').input_value() == '3'
    assert not errors


def test_facade_draft_restore_and_nonbuilding_modes(editor):
    page, errors, root = editor
    open_facade(page)
    page.locator('[data-re-act="facade-preset-warm"]').click()
    page.locator('[data-facade="loading_docks"]').fill('3')
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('.head a[href="#new"]').click()
    page.wait_for_function("location.hash === '#new'")
    page.goto('http://offline.test/#roof')
    page.wait_for_selector('[data-re-act="draft-restore"]')
    page.locator('[data-re-act="draft-restore"]').click()
    open_facade(page)
    assert page.locator('[data-facade="loading_docks"]').input_value() == '3'
    assert page.locator('[data-facade="wall_material"]').input_value() == 'concrete'
    page.locator('[data-re="roofMode"]').select_option('ground')
    assert page.locator('#re-facade').count() == 0
    page.locator('[data-re="roofMode"]').select_option('carport')
    assert page.locator('#re-facade').count() == 0
    page.locator('[data-re="roofMode"]').select_option('flat')
    open_facade(page)
    assert page.locator('[data-facade="loading_docks"]').input_value() == '3'
    assert not errors


def test_facade_front_edge_resets_when_compound_outline_shrinks(editor):
    page, errors, root = editor
    page.locator('[data-re="roofMode"]').select_option('compound')
    page.locator('[data-re-act="part-flat"]').click()
    # A centred annex gives an eight-edge outer boundary, then removing it leaves four.
    page.locator('[data-part-dim="1"][data-dim="d"]').fill('18')
    page.wait_for_function("document.querySelectorAll('[data-facade=front_edge] option').length === 9")
    open_facade(page)
    page.locator('[data-facade="front_edge"]').select_option('7')
    page.locator('[data-re-act="part-delete-1"]').click()
    page.wait_for_function("document.querySelectorAll('[data-facade=front_edge] option').length === 5")
    assert page.locator('[data-facade="front_edge"]').input_value() == ''
    assert '已恢复自动选择' in page.locator('#re-facade-warning').text_content()
    page.locator('[data-re="name"]').fill('主立面自动恢复')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    assert saved(root)[0]['roof']['facade']['front_edge'] is None
    assert not errors


def test_facade_preview_is_live_preserves_view_and_does_not_rebuild_roof_geometry(editor):
    page, errors, root = editor
    source = '''export function createScene(){return {
      dispose(){}, highlightRoofPlanes(){},resetView(mode){window.previewView=mode;},
      setData(data,options){window.previewData=structuredClone(data); (window.previewCalls??=[]).push(options);},
      stats(){const f=window.previewData.project.roof.facade; return {facade:{enabled:f.enabled,
        windows:12,doors:Math.min(2,f.doors),personnel_doors:1,loading_docks:1,canopies:f.canopy_depth_m>0?3:0}};}
    };}'''
    page.route('**/scene.js', lambda route: route.fulfill(body=source, content_type='text/javascript'))
    page.reload()
    page.wait_for_selector('[data-re="roofMode"]')
    page.locator('[data-re="roofMode"]').select_option('pitched')
    page.wait_for_function("document.querySelectorAll('[data-roof-plane]').length === 2")
    page.locator('[data-re-act="model-view"]').click()
    page.wait_for_function('Boolean(window.previewData?.roof_geometry)')
    geometry = page.evaluate('JSON.stringify(window.previewData.roof_geometry)')
    requests = []
    page.on('request', lambda request: requests.append(request.url) if '/api/roof-planes' in request.url else None)
    open_facade(page)
    page.locator('[data-re-act="facade-front-view"]').click()
    assert page.evaluate('window.previewView') == 'front'
    page.locator('[data-re-act="facade-preset-brick"]').click()
    page.wait_for_function("window.previewData.project.roof.facade.wall_material === 'brick'")
    page.locator('[data-facade="doors"]').fill('6')
    page.locator('[data-facade="canopy_depth_m"]').fill('0')
    assert page.evaluate('window.previewData.project.roof.facade.doors') == 6
    assert '卷帘门 2 樘' in page.locator('#re-3d-note').text_content()
    assert '雨棚 0 处' in page.locator('#re-3d-note').text_content()
    assert page.evaluate('window.previewCalls.slice(1).every(call => call.preserveView)')
    assert page.evaluate('JSON.stringify(window.previewData.roof_geometry)') == geometry
    assert not requests
    page.locator('[data-facade="enabled"]').uncheck()
    assert '建筑细节已关闭' in page.locator('#re-3d-note').text_content()
    assert page.locator('[data-facade="doors"]').is_disabled()
    page.locator('[data-re-act="undo"]').click()
    assert page.locator('[data-facade="enabled"]').is_checked()
    assert not errors


def test_invalid_facade_values_block_save(editor):
    page, errors, root = editor
    open_facade(page)
    page.locator('[data-facade="doors"]').fill('7')
    page.locator('[data-re="name"]').fill('非法外观参数不保存')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("document.querySelector('#notice').textContent.includes('厂房外观参数')")
    assert not list((root / 'data/my-roofs').glob('*/project.json'))
    page.locator('[data-facade="doors"]').fill('2')
    page.locator('[data-facade="window_width_m"]').fill('')
    page.locator('[data-re-act="save"]').click()
    assert not list((root / 'data/my-roofs').glob('*/project.json'))
    assert not errors


def test_factory_facade_controls_drive_real_webgl_and_keep_orbit(editor):
    page, errors, root = editor
    web = Path(__file__).resolve().parents[1] / 'desktop/web'
    source = (web / 'scene.js').read_text(encoding='utf-8').replace('export function createScene(', 'function productionScene(')
    source = source.replace('renderer.render(scene,camera);', 'renderer.render(scene,camera); window.facadeRendered={scene,camera,renderer};')
    source += '''\nexport function createScene(...args){
      const api=productionScene(...args), setData=api.setData;
      api.setData=(...values)=>{
        const before=window.facadeRendered?.camera.position.toArray();
        const value=setData(...values);
        window.facadeCameraUpdate={before,after:window.facadeRendered?.camera.position.toArray(),options:values[1]};
        return value;
      };
      return window.facadeLive=api;
    }'''
    page.route('**/scene.js', lambda route: route.fulfill(body=source, content_type='text/javascript'))
    page.route('**/vendor/*.js', lambda route: route.fulfill(path=str(web / 'vendor' / route.request.url.rsplit('/',1)[-1])))
    page.reload()
    page.wait_for_selector('[data-re="roofMode"]')
    page.locator('[data-re="roofMode"]').select_option('pitched')
    page.wait_for_function("document.querySelectorAll('[data-roof-plane]').length === 2")
    page.locator('[data-re="roofMode"]').select_option('compound')
    page.locator('[data-re-act="part-flat"]').click()
    page.wait_for_function("document.querySelector('#re-plane-note').textContent.includes('已校验')")
    open_facade(page)
    page.locator('[data-re-act="facade-front-view"]').click()
    page.wait_for_function('window.facadeLive?.stats().facade?.windows > 0 && window.facadeLive.stats().frames > 3')
    stats = page.evaluate('window.facadeLive.stats().facade')
    assert stats['doors'] > 0 and stats['loading_docks'] > 0
    box = page.locator('#re-3d-host canvas').bounding_box()
    page.mouse.move(box['x'] + box['width'] * .5, box['y'] + box['height'] * .5)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] * .58, box['y'] + box['height'] * .52, steps=10)
    page.mouse.up()
    start = page.evaluate('window.facadeLive.stats().frames')
    page.wait_for_function('(start) => window.facadeLive.stats().frames > start + 100', arg=start)
    open_facade(page)
    page.locator('[data-re-act="facade-preset-brick"]').click()
    page.wait_for_function("window.facadeLive.stats().facade.wall_material === 'brick'")
    assert page.evaluate('''() => {
      const group=window.facadeRendered.scene.getObjectByName('factory-facade');
      return group.children.some(object => object.material?.color.clone().convertLinearToSRGB().getHexString()==='ad7158');
    }''')
    camera_update = page.evaluate('window.facadeCameraUpdate')
    assert camera_update['options']['preserveView'] is True
    assert camera_update['before'] == camera_update['after']
    page.locator('[data-facade="window_rows"]').select_option('0')
    assert page.evaluate('window.facadeLive.stats().facade.windows') == 0
    page.locator('[data-facade="enabled"]').uncheck()
    assert page.evaluate('window.facadeLive.stats().facade.enabled') is False
    assert page.evaluate("window.facadeRendered.scene.getObjectByName('factory-facade').children.length") == 0
    page.locator('[data-re-act="undo"]').click()
    assert page.evaluate('window.facadeLive.stats().facade.enabled') is True
    page.locator('[data-re-act="facade-preset-silver"]').click()
    page.locator('[data-facade="window_rows"]').select_option('1')
    page.locator('[data-re-act="facade-front-view"]').click()
    page.locator('#re-facade summary').scroll_into_view_if_needed()
    if os.environ.get('GUANGZHU_FACADE_CAPTURE') == '1':
        destination = Path(__file__).resolve().parents[1] / 'output/competition-upgrade'
        destination.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(destination / 'factory-facade-editor.png'))
    assert not errors
