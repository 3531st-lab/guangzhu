"""CAD object selection and precise transforms through the actual editor and save API."""
import math
from pathlib import Path

from PIL import Image

from test_roof_editor_dom import editor, click_at, saved  # noqa: F401


def add_device(page, a, b):
    page.locator('[data-re-tool="device"]').click()
    click_at(page, *a)
    click_at(page, *b)


def select(page, item_id, *, extend=False):
    page.locator(f'[data-object-select="item"][data-object-id="{item_id}"]').click(modifiers=['Control'] if extend else [])


def points(page, index):
    return page.locator(f'#re-svg polygon[data-shape="{index}"]').evaluate("element => element.getAttribute('points').trim().split(/\\s+/).map(p=>p.split(',').map(Number)).map(([x,y])=>[x,-y])")


def test_object_list_multiselect_move_preview_cancel_apply_undo_and_roundtrip(editor):
    page, errors, root = editor
    add_device(page, (2, 2), (4, 4))
    add_device(page, (8, 2), (10, 4))
    select(page, 'dev-1')
    select(page, 'dev-2', extend=True)
    assert page.locator('#re-object-browser [aria-pressed="true"]').count() == 2
    assert page.locator('#re-svg .re-selected-object').count() == 2
    original = [points(page, index) for index in range(2)]
    page.locator('[data-transform="dx"]').fill('3')
    page.locator('[data-transform="dy"]').fill('4')
    page.locator('[data-re-act="transform-preview"]').click()
    assert page.locator('.re-transform-preview').count() == 2
    assert [points(page, index) for index in range(2)] == original
    page.locator('[data-re-act="transform-cancel"]').click()
    assert page.locator('.re-transform-preview').count() == 0
    assert [points(page, index) for index in range(2)] == original
    page.locator('[data-re-act="transform-preview"]').click()
    page.locator('[data-re-act="transform-apply"]').click()
    expected = [[[x + 3, y + 4] for x, y in polygon] for polygon in original]
    assert [points(page, index) for index in range(2)] == expected
    page.locator('[data-re-act="undo"]').click()
    assert [points(page, index) for index in range(2)] == original
    page.locator('[data-re-act="redo"]').click()
    assert [points(page, index) for index in range(2)] == expected
    page.locator('[data-re="name"]').fill('多对象精确移动')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    project, folder = saved(root)
    assert [item['footprint'] for item in project['roof']['obstacles']] == expected
    page.goto('http://offline.test/#roof/' + folder.name)
    page.wait_for_selector('[data-object-id="dev-1"]')
    select(page, 'dev-1')
    page.locator('#re-object-browser [data-re-act="object-focus"]').click()
    assert page.evaluate("localStorage.getItem('gz.roof.draft.'+location.hash.split('/')[1])") is None
    dialogs = []
    page.on('dialog', lambda dialog: (dialogs.append(dialog.message), dialog.accept()))
    page.locator('.head a[href="#new"]').click()
    page.wait_for_function("location.hash === '#new'")
    assert not dialogs and not errors


def test_rotate_about_point_mirror_copy_delete_and_inspector_sync(editor):
    page, errors, root = editor
    add_device(page, (2, 2), (4, 4))
    select(page, 'dev-1')
    page.locator('[data-transform="mode"]').select_option('rotate')
    page.locator('[data-transform="angle"]').fill('90')
    page.locator('[data-transform="pivotX"]').fill('10')
    page.locator('[data-transform="pivotY"]').fill('10')
    page.locator('[data-re-act="transform-preview"]').click()
    page.locator('[data-re-act="transform-apply"]').click()
    assert points(page, 0) == [[18, 2], [18, 4], [16, 4], [16, 2]]
    assert page.locator('[data-object-prop="cx"]').input_value() == '17'
    page.locator('[data-object-prop="w"]').fill('3')
    assert page.locator('[data-item-geometry="0"][data-dim="w"]').input_value() == '3'
    page.locator('[data-transform="mode"]').select_option('mirror-x')
    page.locator('[data-transform="axisValue"]').fill('25')
    assert page.locator('[data-transform="copy"]').is_checked()
    page.locator('[data-re-act="transform-preview"]').click()
    page.locator('[data-re-act="transform-apply"]').click()
    assert page.locator('.re-item').count() == 2
    assert page.locator('[data-object-select="item"][aria-pressed="true"]').get_attribute('data-object-id') == 'dev-1-copy-1'
    assert page.locator('[data-object-prop="cx"]').input_value() == '33'
    page.locator('[data-re-act="undo"]').click()
    assert page.locator('.re-item').count() == 1
    assert page.locator('[data-object-select="item"][aria-pressed="true"]').count() == 0
    page.locator('[data-re-act="redo"]').click()
    select(page, 'dev-1-copy-1')
    page.locator('[data-re-act="object-delete"]').click()
    assert page.locator('.re-item').count() == 1
    page.locator('[data-re-act="undo"]').click()
    assert page.locator('.re-item').count() == 2
    page.locator('[data-re="name"]').fill('旋转镜像建模')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    obstacles = saved(root)[0]['roof']['obstacles']
    assert len({item['id'] for item in obstacles}) == 2
    assert math.isclose(math.dist(obstacles[0]['footprint'][0], obstacles[0]['footprint'][1]), 3)
    assert not errors


def test_canvas_ctrl_selection_and_invalid_transform_do_not_mutate(editor):
    page, errors, root = editor
    add_device(page, (2, 2), (4, 4))
    add_device(page, (8, 2), (10, 4))
    select(page, 'dev-1')
    page.keyboard.down('Control')
    click_at(page, 9, 3)
    page.keyboard.up('Control')
    assert page.locator('#re-svg .re-selected-object').count() == 2
    before = [points(page, i) for i in range(2)]
    page.locator('[data-transform="dx"]').fill('')
    page.locator('[data-re-act="transform-preview"]').click()
    page.wait_for_function("document.querySelector('#notice').textContent.includes('有效的变换尺寸')")
    assert page.locator('.re-transform-preview').count() == 0
    assert [points(page, i) for i in range(2)] == before
    assert not errors


def test_uncalibrated_drawing_hides_metre_transforms(editor, tmp_path):
    page, errors, root = editor
    add_device(page, (2, 2), (4, 4))
    image_path = tmp_path / 'unscaled.png'
    Image.new('RGB', (240, 160), 'white').save(image_path)
    page.locator('[data-re-mode="2"]').click()
    page.set_input_files('#re-file', str(image_path))
    page.wait_for_function("document.querySelector('#re-scale').textContent.includes('还没定比例')")
    select(page, 'dev-1')
    assert page.locator('[data-object-prop]').count() == 0
    assert page.locator('[data-transform]').count() == 0
    assert page.locator('#re-object-browser [data-re-act="object-focus"]').is_disabled()
    assert page.locator('[data-item-geometry="0"][data-dim="cx"]').is_disabled()
    assert '先完成比例标定' in page.locator('.re-object-warning').text_content()
    assert not errors


def test_real_webgl_object_picking_standard_views_and_view_restore(editor):
    page, errors, root = editor
    web = Path(__file__).resolve().parents[1] / 'desktop/web'
    source = (web / 'scene.js').read_text(encoding='utf-8').replace('export function createScene(', 'function productionScene(')
    source = source.replace('renderer.render(scene,camera);', 'renderer.render(scene,camera); window.modelRendered={scene,camera,renderer};')
    source += '''\nexport function createScene(...args){
      const api=productionScene(...args), dispose=api.dispose;
      api.dispose=()=>{window.disposedModelView=api.getViewState();dispose();};
      return window.modelLive=api;
    }'''
    page.route('**/scene.js', lambda route: route.fulfill(body=source, content_type='text/javascript'))
    page.route('**/vendor/*.js', lambda route: route.fulfill(path=str(web / 'vendor' / route.request.url.rsplit('/', 1)[-1])))
    page.reload()
    page.wait_for_selector('[data-re-tool="device"]')
    add_device(page, (8, 8), (12, 12))
    add_device(page, (30, 8), (34, 12))
    page.locator('[data-re-act="model-view"]').click()
    page.wait_for_function('window.modelLive?.stats().frames > 3')
    assert page.evaluate('window.modelLive.stats().projection') == 'perspective'
    page.locator('[data-re-view="top"]').click()
    assert page.evaluate('window.modelLive.stats().projection') == 'orthographic'
    assert page.evaluate('window.modelLive.stats().view') == 'top'
    page.wait_for_function("window.modelRendered.camera.isOrthographicCamera === true")

    def screen_point(item_id):
        return page.evaluate('''id => {
          const {scene,camera,renderer}=window.modelRendered;
          camera.updateMatrixWorld(true);
          let target; scene.traverse(object=>{if(object.userData.sceneObject?.id===id) target=object;});
          const center=new THREE.Box3().setFromObject(target).getCenter(new THREE.Vector3()).project(camera);
          const bounds=renderer.domElement.getBoundingClientRect();
          return [bounds.left+(center.x+1)*bounds.width/2,bounds.top+(1-center.y)*bounds.height/2];
        }''', item_id)

    for index, item_id in enumerate(['dev-1', 'dev-2']):
        point = screen_point(item_id)
        assert all(math.isfinite(value) for value in point)
        if index:
            page.keyboard.down('Control')
        page.mouse.click(*point)
        if index:
            page.keyboard.up('Control')
    assert page.locator('[data-object-select="item"][aria-pressed="true"]').count() == 2
    assert {row['id'] for row in page.evaluate('window.modelLive.stats().selectedObjects')} == {'dev-1', 'dev-2'}
    page.locator('[data-re-view="north"]').click()
    assert page.evaluate('window.modelLive.stats().view') == 'north'
    assert page.evaluate('window.modelLive.stats().projection') == 'orthographic'
    page.locator('[data-re-projection]').select_option('perspective')
    assert page.evaluate('window.modelLive.stats().projection') == 'perspective'
    page.locator('[data-re-view="iso"]').click()
    assert page.evaluate('window.modelLive.stats().projection') == 'orthographic'
    box = page.locator('#re-3d-host canvas').bounding_box()
    page.mouse.move(box['x'] + box['width'] * .55, box['y'] + box['height'] * .55)
    page.mouse.down()
    page.mouse.move(box['x'] + box['width'] * .62, box['y'] + box['height'] * .6, steps=8)
    page.mouse.up()
    page.locator('[data-re-act="plan-view"]').click()
    assert page.locator('#re-3d-host canvas').count() == 0
    before = page.evaluate('window.disposedModelView')
    page.locator('[data-re-act="model-view"]').click()
    page.wait_for_function('window.modelLive.stats().frames > 2')
    after = page.evaluate('window.modelLive.getViewState()')
    assert after['projection'] == before['projection']
    for key in ['position', 'target']:
        assert max(abs(a - b) for a, b in zip(before[key], after[key])) < 1e-6
    assert not errors
