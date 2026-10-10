"""Real editor, production geometry in WebGL and printed proposal; no AI calls."""
import json
import os

from playwright.sync_api import sync_playwright

from guangzhu import layout, roofplane
from guangzhu.config import ROOT
from guangzhu.models import Project
from test_roof_editor_dom import editor, click_at
from test_t32_flow import pitched_flow


def assets(tmp_path):
    destination = ROOT / 'reports/assets/T32' if os.environ.get('GUANGZHU_T32_CAPTURE') == '1' else tmp_path
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def test_editor_four_shapes_manual_ridge_and_mixed_material_save(editor, tmp_path):
    page, errors, root = editor
    destination = assets(tmp_path)
    page.locator('[data-re="name"]').fill('T32整栋编辑示意')
    page.locator('[data-re="roofMode"]').select_option('pitched')
    page.locator('[data-re="pitchKind"]').select_option('hip')
    page.wait_for_function("document.querySelectorAll('[data-roof-plane]').length === 4")
    page.screenshot(path=str(destination / 'editor-hip.png'))
    page.locator('[data-re="pitchKind"]').select_option('sawtooth')
    page.locator('[data-re="slope"]').fill('10')
    page.locator('[data-re="toothWidth"]').fill('10')
    page.wait_for_function("document.querySelectorAll('[data-roof-plane]').length === 8")
    page.wait_for_function("document.querySelector('#re-plane-note').textContent.includes('实际 4 齿')")
    assert '9.000 m' in page.locator('#re-plane-note').inner_text()
    page.screenshot(path=str(destination / 'editor-saw.png'))
    page.locator('[data-re="pitchKind"]').select_option('single')
    page.wait_for_function("document.querySelectorAll('[data-roof-plane]').length === 1")
    page.locator('[data-re="pitchKind"]').select_option('gable')
    page.locator('[data-re="slope"]').fill('5')
    page.locator('[data-re-rect="w"]').fill('30')
    page.locator('[data-re-rect="d"]').fill('20')
    page.locator('[data-re-act="ridge"]').click()
    click_at(page, 2, 12)
    click_at(page, 3, 12)
    page.wait_for_function("document.querySelectorAll('[data-roof-plane]').length === 2")
    page.locator('details', has=page.locator('#re-planes')).locator('summary').click()
    page.locator('[data-plane="1"][data-plane-key="material"]').select_option('concrete')
    page.locator('[data-plane="1"][data-plane-key="load_capacity_kn_m2"]').fill('.4')
    page.locator('[data-re="seamSetback"]').fill('.7')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    files = list((root / 'data/my-roofs').glob('*/project.json'))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding='utf-8'))
    assert saved['roof']['type'] == 'pitched' and saved['equipment']['racking'] == 'plane_flush'
    assert saved['roof']['seam_setback_m'] == .7
    assert saved['roof']['planes'][1]['material'] == 'concrete'
    assert saved['roof']['planes'][1]['load_capacity_kn_m2'] == .4
    assert max(p['offset_m'] for p in saved['roof']['planes']) > .3
    page.goto('http://offline.test/#roof/' + files[0].parent.name)
    page.wait_for_function("document.querySelectorAll('[data-roof-plane]').length === 2")
    assert page.locator('[data-re="seamSetback"]').input_value() == '0.7'
    assert not errors


def test_real_whole_building_scenes_and_pdf_tables(pitched_flow, tmp_path):
    destination = assets(tmp_path)
    scene = pitched_flow['scene']
    web = ROOT / 'desktop/web'
    source = '''<html lang="zh"><meta charset="utf-8"><body style="margin:0;background:#f4ece3">
      <h2 style="padding:12px">光筑 · 整栋斜屋面示意 · 真实坡面高度与玻璃面</h2><div id="scene" style="width:1440px;height:800px"></div>
      <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
      <script>const NativeRenderer=THREE.WebGLRenderer;
      THREE.WebGLRenderer=class extends NativeRenderer {
        constructor(...args) {
          super(...args);
          const draw=this.render;
          this.render=(scene,camera)=>{
            window.actualScene=scene;
            window.actualRenderer=this;
            return draw.call(this,scene,camera);
          };
        }
      };</script>
      <script type="module">
      import {createScene} from '/scene.js';
      import {normalizeScene} from '/scene-data.js';
      const input=await (await fetch('/data.json')).json();
      window.geometry=normalizeScene(input);
      window.viewer=createScene(document.querySelector('#scene'));
      window.viewer.setData(input);</script></body></html>'''
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge', headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1440, height=900))
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def respond(route):
            path = route.request.url.split('offline.test')[-1]
            if path == '/':
                route.fulfill(body=source, content_type='text/html')
            elif path == '/data.json':
                route.fulfill(json=scene)
            else:
                file = web / path.lstrip('/')
                route.fulfill(path=str(file)) if file.is_file() else route.abort()
        page.route('**/*', respond)
        page.goto('http://offline.test/')
        page.wait_for_function('window.viewer?.stats().frames > 3')
        assert page.evaluate('window.viewer.stats().roofPlanes') == 2
        assert page.evaluate('window.viewer.stats().panels') == len(scene['design']['modules'])
        normals = page.evaluate('''() => {
          const result={walls:[],roofs:[]};
          window.actualScene.traverse(object => {
            if (!object.geometry?.attributes.normal) return;
            const position=object.geometry.attributes.position, normal=object.geometry.attributes.normal;
            if (object.userData.roofPlane) result.roofs.push(normal.getY(0));
            if (position.count===6 && Math.abs(normal.getY(0))<1e-7 && !object.userData.roofPlane) {
              const x=(position.getX(0)+position.getX(1)+position.getX(2))/3;
              const z=(position.getZ(0)+position.getZ(1)+position.getZ(2))/3;
              result.walls.push(x*normal.getX(0)+z*normal.getZ(0));
            }
          });
          return result;
        }''')
        assert len(normals['roofs']) == 2 and min(normals['roofs']) > 0
        assert len(normals['walls']) == 6 and min(normals['walls']) > 0, normals
        assert page.evaluate('window.actualRenderer.shadowMap.enabled')
        assert page.evaluate('window.actualScene.children.some(o=>o.isDirectionalLight && o.castShadow)')
        page.screenshot(path=str(destination / 'gable-3d.png'))
        record = Project.model_validate_json((ROOT / 'data/demo/projects/pitched-saw-demo/project.json').read_text(encoding='utf-8'))
        design = layout.generate_layout(record, {})
        scene = dict(project=record.model_dump(mode='json'), design=design.model_dump(mode='json'),
                     roof_geometry=roofplane.scene_geometry(record.roof))
        page.reload()
        page.wait_for_function('window.viewer?.stats().frames > 3')
        assert page.evaluate('window.viewer.stats().roofPlanes') == 8
        assert page.evaluate("window.geometry.roof.planes.filter(p=>p.material==='glass').length") == 4
        page.screenshot(path=str(destination / 'saw-3d.png'))
        page.set_content((pitched_flow['assets'] / 'proposal.html').read_text(encoding='utf-8'))
        assert page.locator('section.plane-table').count() == 2
        page.locator('section.plane-table').first.screenshot(path=str(destination / 'proposal-plane-table.png'))
        page.pdf(path=str(destination / 'proposal.pdf'), print_background=True)
        assert (destination / 'proposal.pdf').read_bytes().startswith(b'%PDF')
        assert not errors
        browser.close()
