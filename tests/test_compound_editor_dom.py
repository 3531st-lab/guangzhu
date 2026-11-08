"""Compound roof and precise object editing through the real save/preview API."""
import math
import os
from pathlib import Path

from test_roof_editor_dom import editor, click_at, saved  # noqa: F401


def capture(page, name):
    if os.environ.get('GUANGZHU_UPGRADE_CAPTURE') != '1':
        return
    destination = Path(__file__).resolve().parents[1] / 'output/competition-upgrade'
    destination.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(destination / name))


def test_compound_gable_and_lower_flat_annex_roundtrip(editor):
    page, errors, root = editor
    page.locator('[data-re="roofMode"]').select_option('pitched')
    page.wait_for_function("document.querySelectorAll('[data-roof-plane]').length === 2")
    page.locator('[data-re="roofMode"]').select_option('compound')
    page.locator('[data-re-act="part-flat"]').click()
    page.wait_for_function("document.querySelectorAll('[data-roof-plane]').length === 3")
    page.locator('[data-part="0"][data-part-key="eave_height_m"]').fill('11')
    page.locator('[data-part="1"][data-part-key="eave_height_m"]').fill('6')
    page.locator('[data-part="1"][data-part-key="label"]').fill('低跨附楼')
    page.locator('[data-part-row="part-1"]').scroll_into_view_if_needed()
    page.wait_for_function("document.querySelector('#re-plane-note').textContent.includes('已校验')")
    capture(page, 'compound-roof-editor.png')
    page.locator('[data-re="name"]').fill('组合厂房演示')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    project, folder = saved(root)
    roof = project['roof']
    assert roof['type'] == 'pitched' and len(roof['parts']) == 2 and len(roof['planes']) == 3
    assert roof['height_m'] == 6
    assert {part['eave_height_m'] for part in roof['parts']} == {6,11}
    assert roof['parts'][1]['label'] == '低跨附楼'
    page.goto('http://offline.test/#roof/' + folder.name)
    page.wait_for_function("document.querySelector('[data-re=roofMode]')?.value === 'compound'")
    assert page.locator('[data-part="1"][data-part-key="label"]').input_value() == '低跨附楼'
    assert page.locator('[data-part="1"][data-part-key="eave_height_m"]').input_value() == '6'
    assert not errors


def test_array_preview_apply_undo_and_precise_size_are_saved(editor):
    page, errors, root = editor
    page.locator('[data-re-tool="skylight"]').click()
    click_at(page,4,4)
    click_at(page,6,5)
    page.locator('[data-item-tools="0"] summary').click()
    page.locator('[data-item-geometry="0"][data-dim="w"]').fill('3')
    page.locator('[data-item-geometry="0"][data-dim="turn"]').fill('30')
    page.locator('[data-array="0"][data-array-key="count"]').fill('6')
    page.locator('[data-array="0"][data-array-key="spacing"]').fill('8')
    page.locator('[data-re-act="array-preview-0"]').click()
    assert page.locator('.re-array-preview').count() == 5
    assert page.locator('.re-item').count() == 1
    capture(page, 'skylight-array-preview.png')
    page.locator('[data-re-act="array-apply-0"]').click()
    assert page.locator('.re-item').count() == 6
    page.locator('[data-re-act="undo"]').click()
    assert page.locator('.re-item').count() == 1
    page.locator('[data-re-act="redo"]').click()
    assert page.locator('.re-item').count() == 6
    page.locator('[data-re="name"]').fill('六天窗精确阵列')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    roof = saved(root)[0]['roof']
    zones = roof['keepouts']
    assert len(zones) == len({zone['id'] for zone in zones}) == 6
    assert math.isclose(math.dist(zones[0]['polygon'][0], zones[0]['polygon'][1]),3,abs_tol=1e-8)
    for i, zone in enumerate(zones):
        assert math.isclose(sum(p[0] for p in zone['polygon']) / 4, 5 + 8*i,abs_tol=1e-8)
    assert not errors


def test_invalid_part_dimensions_and_overlapping_roofs_do_not_save(editor):
    page, errors, root = editor
    page.locator('[data-re="roofMode"]').select_option('compound')
    page.locator('[data-re-act="part-flat"]').click()
    page.locator('[data-re="name"]').fill('重叠拒绝保存')
    page.locator('[data-part-dim="1"][data-dim="cx"]').fill('30')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("document.querySelector('#notice').textContent.includes('重叠')")
    assert not list((root / 'data/my-roofs').glob('*/project.json'))
    page.locator('[data-part-dim="1"][data-dim="w"]').fill('')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("document.querySelector('#notice').textContent.includes('补全有效')")
    assert page.evaluate('location.hash').startswith('#roof')
    assert not errors


def test_compound_live_webgl_preview_follows_heights_selection_and_disposes(editor):
    page, errors, root = editor
    web = Path(__file__).resolve().parents[1] / 'desktop/web'

    # Replace only this test's scene/vendor stubs with the production WebGL code.
    # The wrapper observes disposal; geometry and rendering still run unchanged.
    source = (web / 'scene.js').read_text(encoding='utf-8').replace('export function createScene(', 'function productionScene(')
    source = source.replace('renderer.render(scene,camera);', 'renderer.render(scene,camera); globalThis.testRenderedRoof = {scene,camera,renderer};')
    source += '''\nexport function createScene(...args) {
      const scene = productionScene(...args), entry = {scene,disposed:false}, dispose = scene.dispose;
      scene.dispose = () => {entry.disposed=true; dispose();};
      (window.previewInstances ??= []).push(entry);
      return scene;
    }'''
    page.route('**/scene.js', lambda route: route.fulfill(body=source, content_type='text/javascript'))
    page.route('**/vendor/*.js', lambda route: route.fulfill(path=str(web / 'vendor' / route.request.url.rsplit('/',1)[-1])))
    page.reload()
    page.wait_for_selector('[data-re="roofMode"]')
    page.locator('[data-re="roofMode"]').select_option('pitched')
    page.wait_for_function("document.querySelectorAll('[data-roof-plane]').length === 2")
    page.locator('[data-re="roofMode"]').select_option('compound')
    page.locator('[data-re-act="part-flat"]').click()
    page.locator('[data-part="0"][data-part-key="eave_height_m"]').fill('11')
    page.locator('[data-part="1"][data-part-key="eave_height_m"]').fill('6')
    click_at(page,15,5)
    page.locator('[data-re-act="model-view"]').click()
    page.wait_for_function("window.previewInstances?.at(-1).scene.stats().roofPlanes === 3 && window.previewInstances.at(-1).scene.stats().frames > 3")
    assert page.locator('#re-svg-host').is_hidden()
    assert page.evaluate('window.previewInstances.at(-1).scene.stats().available')
    assert page.evaluate('window.previewInstances.at(-1).scene.stats().selectedRoofPlanes') == [1,2]
    roof_heights = '''() => {
      const heights=[];
      window.testRenderedRoof.scene.traverse(object => {
        if (object.userData.roofPlane != null) {
          const values=object.geometry.attributes.position;
          heights.push({id:object.userData.roofPlane,low:Math.min(...Array.from({length:values.count},(_,i)=>values.getY(i)))});
        }
      });
      return heights.sort((a,b)=>a.id-b.id);
    }'''
    page.wait_for_function(f'({roof_heights})()[0]?.low === 11')
    assert [row['low'] for row in page.evaluate(roof_heights)] == [11,11,6]
    page.locator('[data-part="0"][data-part-key="eave_height_m"]').fill('13')
    page.wait_for_function(f'({roof_heights})()[0]?.low === 13')
    assert [row['low'] for row in page.evaluate(roof_heights)] == [13,13,6]
    point = page.evaluate('''() => {
      const {camera,renderer}=window.testRenderedRoof;
      const p=new THREE.Vector3(30,6,0).project(camera), bounds=renderer.domElement.getBoundingClientRect();
      return [bounds.left+(p.x+1)*bounds.width/2,bounds.top+(1-p.y)*bounds.height/2];
    }''')
    page.mouse.click(*point)
    page.wait_for_function("window.previewInstances.at(-1).scene.stats().selectedRoofPlanes.includes(3)")
    assert page.locator('[data-part-row="part-2"]').evaluate("element => element.classList.contains('selected')")
    capture(page, 'compound-roof-3d.png')
    page.locator('[data-re-act="plan-view"]').click()
    assert page.evaluate('window.previewInstances.at(-1).disposed')
    assert page.locator('#re-3d-host canvas').count() == 0
    page.locator('[data-re-act="model-view"]').click()
    page.wait_for_function('window.previewInstances.length === 2 && window.previewInstances[1].scene.stats().roofPlanes === 3')
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('.head a[href="#new"]').click()
    page.wait_for_function("location.hash === '#new'")
    assert page.evaluate('window.previewInstances.every(entry => entry.disposed)')
    assert not errors
