"""Exercise the production renderer's facade lifecycle and camera in real WebGL."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from guangzhu.config import DATA_DIR
from guangzhu.layout import generate_layout
from guangzhu.models import Project, Roof, Requirements
from guangzhu.roofplane import scene_geometry


def test_facade_styles_preserve_view_theme_geometry_and_release_gpu_resources():
    project = Project.model_validate(json.loads((DATA_DIR / 'demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8')))
    project.requirements = Requirements()
    project.equipment.racking = 'plane_flush'
    project.roof = Roof(type='pitched', parts=[
        dict(id='hall', label='车间', kind='gable', outline=[[0, 0], [30, 0], [30, 16], [0, 16]], eave_height_m=9, slope_deg=10),
        dict(id='annex', label='附楼', kind='flat', outline=[[30, 0], [38, 0], [38, 16], [30, 16]], eave_height_m=5),
    ], parapet_height_m=0, load_capacity_kn_m2=1)
    design = generate_layout(project, {})
    data = dict(project=project.model_dump(mode='json'), design=design.model_dump(mode='json'), roof_geometry=scene_geometry(project.roof))
    web = Path(__file__).resolve().parents[1] / 'desktop/web'
    html = '''<!doctype html><meta charset="utf-8"><title>Facade WebGL regression</title>
      <div id="scene" style="width:1000px;height:700px"></div>
      <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
      <script>const NativeRenderer=THREE.WebGLRenderer;
      THREE.WebGLRenderer=class extends NativeRenderer {constructor(...args){super(...args);
        const draw=this.render;this.render=(scene,camera)=>{window.actualScene=scene;window.actualCamera=camera;return draw.call(this,scene,camera);};}};</script>
      <script type="module">import {createScene} from '/scene.js';
        window.sourceData=await(await fetch('/data.json')).json();window.before=JSON.stringify(sourceData);
        window.viewer=createScene(document.querySelector('#scene'));viewer.setData(sourceData);
      </script>'''
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge', headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1100, height=800))
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def respond(route):
            path = route.request.url.split('facade.test', 1)[-1]
            if path == '/':
                route.fulfill(body=html, content_type='text/html')
            elif path == '/data.json':
                route.fulfill(json=data)
            else:
                route.fulfill(path=str(web / path.lstrip('/')))

        page.route('**/*', respond)
        page.goto('http://facade.test/')
        page.wait_for_function('window.viewer?.stats().frames > 3')
        original = page.evaluate('viewer.stats()')
        assert original['available'] and original['facade']['windows'] > 0
        assert original['facade']['doors'] == 2 and original['facade']['loading_docks'] == 1
        assert original['panels'] == len(design.modules) and original['roofPlanes'] == len(project.roof.planes)
        assert page.evaluate('''() => {
          const group=actualScene.getObjectByName('factory-facade');
          window.oldFacade=group;window.facadeDisposed=0;window.expectedDisposals=group.children.length;
          for(const object of group.children)object.geometry.addEventListener('dispose',()=>facadeDisposed++);
          window.originalColors=group.children.map(object=>object.material.color.getHex());
          viewer.setTheme('dark');
          return JSON.stringify(originalColors)===JSON.stringify(group.children.map(object=>object.material.color.getHex()));
        }''')
        page.evaluate("viewer.resetView('front')")
        page.wait_for_timeout(150)
        assert page.evaluate('''() => {
          const outline=sourceData.project.roof.outline,edge=viewer.stats().facade.front_edge,a=outline[edge],b=outline[(edge+1)%outline.length];
          const length=Math.hypot(b[0]-a[0],b[1]-a[1]),out=new THREE.Vector3((b[1]-a[1])/length,0,(b[0]-a[0])/length);
          const direction=actualCamera.getWorldDirection(new THREE.Vector3());
          window.cameraPosition=actualCamera.position.toArray();window.cameraRotation=actualCamera.quaternion.toArray();
          return direction.dot(out)<-.9 && Math.abs(direction.y)<.4;
        }''')
        for style in ('brick', 'concrete', 'metal'):
            page.evaluate('''style => {
              const candidate=structuredClone(sourceData);candidate.project.roof.facade={wall_material:style};
              viewer.setData(candidate,{preserveView:true});
            }''', style)
            page.wait_for_function('style=>viewer.stats().facade.wall_material===style', arg=style)
            assert page.evaluate('JSON.stringify(actualCamera.position.toArray())===JSON.stringify(cameraPosition)')
            assert page.evaluate('JSON.stringify(actualCamera.quaternion.toArray())===JSON.stringify(cameraRotation)')
        page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        # Restoring the original material must restore the same resource footprint.
        final = page.evaluate('viewer.stats()')
        assert final['geometries'] == original['geometries']
        assert final['textures'] == original['textures']
        assert final['facade'] == original['facade']
        assert page.evaluate('facadeDisposed===expectedDisposals')
        assert page.evaluate('before===JSON.stringify(sourceData)')
        assert page.evaluate('actualScene.getObjectByName("factory-facade")!==oldFacade')
        page.evaluate('''() => {
          window.finalDisposed=0;const group=actualScene.getObjectByName('factory-facade');
          window.finalExpected=group.children.length;
          for(const object of group.children)object.geometry.addEventListener('dispose',()=>finalDisposed++);
          viewer.dispose();
        }''')
        assert page.evaluate('finalDisposed===finalExpected')
        assert page.locator('#scene canvas').count() == 0
        assert not errors
        browser.close()
