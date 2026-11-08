"""Manual previews show exact before/after geometry without borrowing saved analyses."""
import copy
import math
from pathlib import Path

from playwright.sync_api import sync_playwright


def test_manual_preview_has_exact_outlines_picking_and_clean_analysis_state():
    def panel(identifier, x, y):
        return dict(id=identifier, center=[x, y, .6], corners=[[x-1, y-.5, .3], [x+1, y-.5, .3],
                    [x+1, y+.5, .9], [x-1, y+.5, .9]], tilt=31, azimuth=180, orientation='landscape')

    parent = dict(version=4, modules=[panel('move', 3, 4), panel('rotate', 10, 6),
                                    panel('remove', 18, 4), panel('keep', 18, 10)])
    moved, rotated = copy.deepcopy(parent['modules'][:2])
    for point in [moved['center'], *moved['corners']]:
        point[0] += 2
        point[1] += 1
    for point in rotated['corners']:
        x, y = point[0]-10, point[1]-6
        point[:2] = [10+x*math.cos(.7)-y*math.sin(.7), 6+x*math.sin(.7)+y*math.cos(.7)]
    # Deliberately reuse the saved version number: identity must not revive stale heat/string/wind data.
    candidate = dict(version=4, parent_version=4,
                     modules=[moved, rotated, parent['modules'][3], panel('add', 10, 11)])
    project = dict(site=dict(lat=31.8, lon=119.9), roof=dict(type='flat', height_m=5, parapet_height_m=0,
                   outline=[[0, 0], [24, 0], [24, 16], [0, 16]], obstacles=[], keepouts=[]))
    data = dict(project=project, design=candidate, parent_design=parent, edit_preview=True,
                shading=dict(version=4, modules=[dict(id=m['id'], total_loss_pct=8) for m in candidate['modules']]),
                electrical=dict(version=4, strings=[dict(id='stale-string', module_ids=[m['id'] for m in candidate['modules']])]),
                wind=dict(version=4, modules=[dict(id=m['id'], zone='corner') for m in candidate['modules']]))
    web = Path(__file__).resolve().parents[1] / 'desktop/web'
    html = '''<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/scene.css">
      <div id="scene" style="width:1000px;height:700px"></div>
      <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
      <script>const NativeRenderer=THREE.WebGLRenderer;
      THREE.WebGLRenderer=class extends NativeRenderer {constructor(...args){super(...args);const draw=this.render;
        this.render=(scene,camera)=>{window.actualScene=scene;window.actualCamera=camera;return draw.call(this,scene,camera);};}};</script>
      <script type="module">import {createScene,normalizeSceneForDisplay} from '/scene.js';
        window.sourceData=await(await fetch('/data.json')).json();window.before=JSON.stringify(sourceData);
        window.expected=normalizeSceneForDisplay(sourceData);window.picked=[];
        window.viewer=createScene(document.querySelector('#scene'),{onSelectModule:id=>picked.push(id),onInspect:value=>window.inspected=value});
        viewer.setMode('heat');viewer.setData(sourceData);viewer.setProjection('orthographic');viewer.resetView('top');
        window.panelMesh=()=>{let found;actualScene.traverse(object=>{if(object.isInstancedMesh)found=object;});return found;};
        window.where=id=>{const m=expected.modules.find(m=>m.id===id),p=new THREE.Vector3(...m.position).project(actualCamera);
          const bounds=document.querySelector('#scene canvas').getBoundingClientRect();return {x:bounds.x+(p.x+1)*bounds.width/2,y:bounds.y+(1-p.y)*bounds.height/2};};
      </script>'''
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge', headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1100, height=800))
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def respond(route):
            path = route.request.url.split('manual-scene.test', 1)[-1]
            if path == '/':
                route.fulfill(body=html, content_type='text/html')
            elif path == '/data.json':
                route.fulfill(json=data)
            else:
                route.fulfill(path=str(web/path.lstrip('/')))

        page.route('**/*', respond)
        page.goto('http://manual-scene.test/')
        page.wait_for_function('window.viewer?.stats().frames>3')
        facts = page.evaluate('''() => {
          const outlines={};actualScene.traverse(object=>{
            for(const kind of ['removed','previous','candidate'])if(object.userData[kind+'OutlineCount'])outlines[kind]=object;
          });
          const expectedRows={removed:expected.removed,previous:expected.previousPositions,
            candidate:expected.modules.filter(m=>expected.changed.has(m.id)||expected.added.has(m.id))};
          const exact=Object.entries(expectedRows).every(([kind,modules])=>{
            const values=modules.flatMap(module=>module.points.flatMap((point,i)=>[...point,...module.points[(i+1)%4]]));
            return values.every((value,i)=>Math.abs(outlines[kind].geometry.attributes.position.array[i]-value)<1e-5);
          });
          const panel=panelMesh(),matrix=new THREE.Matrix4(),cornerOrder=[[-.5,0,.5],[.5,0,.5],[.5,0,-.5],[-.5,0,-.5]];
          const panelExact=expected.modules.every((module,i)=>{panel.getMatrixAt(i,matrix);return cornerOrder.every((p,j)=>{
            const actual=new THREE.Vector3(...p).applyMatrix4(matrix).toArray();
            return actual.every((value,axis)=>Math.abs(value-module.points[j][axis])<1e-5);
          });});
          window.outlineDisposed=false;outlines.previous.geometry.addEventListener('dispose',()=>window.outlineDisposed=true);
          return {counts:Object.fromEntries(Object.entries(outlines).map(([kind,object])=>[kind,object.userData[kind+'OutlineCount']])),
            annotationOnly:Object.values(outlines).every(object=>object.isLineSegments&&!object.castShadow&&!object.material.depthTest&&!object.material.depthWrite),
            exact,panelExact,unchanged:before===JSON.stringify(sourceData),material:panel.material.type,
            cables:viewer.stats().cableRoutes,changed:viewer.stats().changed,preview:viewer.stats().preview};
        }''')
        assert facts == dict(counts=dict(removed=1, previous=2, candidate=3), annotationOnly=True,
                             exact=True, panelExact=True, unchanged=True, material='MeshStandardMaterial',
                             cables=0, changed=2, preview=True)
        assert page.get_by_text('候选预览 · 尚未保存', exact=False).is_visible()
        # Highlight expiry and a requested analysis mode cannot turn preview geometry into stale heat.
        page.wait_for_timeout(1700)
        page.evaluate("viewer.setMode('wiring')")
        color = page.evaluate('''() => {const color=new THREE.Color();panelMesh().getColorAt(0,color);return color.toArray();}''')
        expected_color = page.evaluate("new THREE.Color('#4fc58a').convertSRGBToLinear().toArray()")
        assert all(abs(a-b) < 1e-6 for a, b in zip(color, expected_color))
        where = page.evaluate("where('move')")
        page.mouse.click(where['x'], where['y'])
        assert page.evaluate('picked.at(-1)') == 'move'
        assert page.evaluate('inspected.loss===null&&inspected.string===null&&inspected.voltages===null')
        page.evaluate("viewer.setMode('heat');viewer.setData({...sourceData,edit_preview:false,design:sourceData.parent_design,parent_design:null})")
        page.wait_for_function('window.outlineDisposed')
        assert page.evaluate('viewer.stats().preview') is False
        assert page.evaluate('viewer.stats().changed') == 0
        assert page.evaluate('panelMesh().material.type') == 'MeshBasicMaterial'
        assert page.get_by_text('候选预览 · 尚未保存', exact=False).is_hidden()
        assert page.evaluate('before===JSON.stringify(sourceData)')
        assert not errors
        browser.close()
