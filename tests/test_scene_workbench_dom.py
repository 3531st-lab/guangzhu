"""Real WebGL standard views, semantic picking and authoritative parapet gaps."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from guangzhu.config import DATA_DIR
from guangzhu.models import Roof
from guangzhu.roofplane import scene_geometry


def test_standard_views_pick_objects_and_show_exact_segmented_parapets(tmp_path):
    base = json.loads((DATA_DIR / 'demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    common = dict(parapet_height_m=2, load_capacity_kn_m2=1,
                  parapet_segments=[dict(edge_index=0, start_ratio=.1, end_ratio=.3, height_m=1.2),
                                    dict(edge_index=0, start_ratio=.65, end_ratio=.9, height_m=1.8)],
                  obstacles=[dict(id='device', label='设备', kind='prism', height_m=2, footprint=[[2, 2], [4, 2], [4, 4], [2, 4]])],
                  keepouts=[dict(id='skylight', label='采光口', polygon=[[14, 2], [17, 2], [17, 4], [14, 4]])])
    roofs = [Roof(type='pitched', parts=[
        dict(id='hall', label='高脊车间', kind='gable', outline=[[0, 0], [30, 0], [30, 20], [0, 20]], eave_height_m=5, slope_deg=30),
        dict(id='annex', label='附楼', kind='flat', outline=[[30, 0], [40, 0], [40, 20], [30, 20]], eave_height_m=3),
    ], **common)]
    roofs += [Roof(type=kind, height_m=5, outline=[[0, 0], [30, 0], [30, 20], [0, 20]],
                   **(dict(slope_deg=12, slope_azimuth_deg=180) if kind == 'metal' else {}), **common) for kind in ('flat', 'metal')]
    fixtures = [dict(project={**base, 'roof': roof.model_dump(mode='json')}, design=dict(version=1, modules=[], params={}),
                     roof_geometry=scene_geometry(roof), editor_markers=[dict(id='inverter-location', point=[20, 15])]) for roof in roofs]
    web = Path(__file__).resolve().parents[1] / 'desktop/web'
    html = '''<!doctype html><meta charset="utf-8"><title>Modeling workbench</title><style>body{margin:0}#scene{width:1000px;height:700px}</style>
      <div id="scene"></div><script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
      <script>const NativeRenderer=THREE.WebGLRenderer;
      THREE.WebGLRenderer=class extends NativeRenderer {constructor(...args){super(...args);const draw=this.render;
        this.render=(scene,camera)=>{window.actualScene=scene;window.actualCamera=camera;return draw.call(this,scene,camera);};}};</script>
      <script type="module">import {createScene} from '/scene.js';import {normalizeScene} from '/scene-data.js';
        window.fixtures=await(await fetch('/data.json')).json();window.original=JSON.stringify(fixtures);window.hits=[];
        window.makeViewer=()=>createScene(document.querySelector('#scene'),{onSelectObject:(value,gesture)=>{hits.push(value);window.lastGesture=gesture;}});
        window.viewer=makeViewer();window.show=index=>{window.current=fixtures[index];window.normalized=normalizeScene(current);viewer.setData(current);};show(0);
        window.projectPoint=(x,y,z)=>{const p=new THREE.Vector3(...normalized.world([x,y,z ?? normalized.elevation([x,y])]));p.project(actualCamera);
          const bounds=document.querySelector('#scene canvas').getBoundingClientRect();return {x:bounds.x+(p.x+1)*bounds.width/2,y:bounds.y+(1-p.y)*bounds.height/2};};
      </script>'''
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge', headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1100, height=800))
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def respond(route):
            path = route.request.url.split('workbench.test', 1)[-1]
            if path == '/':
                route.fulfill(body=html, content_type='text/html')
            elif path == '/data.json':
                route.fulfill(json=fixtures)
            else:
                route.fulfill(path=str(web / path.lstrip('/')))

        page.route('**/*', respond)
        page.goto('http://workbench.test/')
        page.wait_for_function('window.viewer?.stats().frames>3')
        for projection in ('perspective', 'orthographic'):
            page.evaluate('projection=>viewer.setProjection(projection)', projection)
            for view in ('iso', 'top', 'north', 'east', 'south', 'west'):
                page.evaluate('view=>viewer.resetView(view)', view)
                page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                facts = page.evaluate('''() => {
                  const points=current.roof_geometry.faces.flatMap(face=>face.points).concat(current.roof_geometry.parapets.flat());
                  const inside=points.every(p=>{const q=new THREE.Vector3(...normalized.world(p)).project(actualCamera);
                    return Math.abs(q.x)<.86 && Math.abs(q.y)<.86 && q.z>=-1 && q.z<=1;});
                  const outside=points.map(p=>new THREE.Vector3(...normalized.world(p)).project(actualCamera).toArray()).filter(p=>Math.abs(p[0])>=.86||Math.abs(p[1])>=.86||p[2]<-1||p[2]>1);
                  return {inside,outside,state:viewer.getViewState(),orthographic:actualCamera.isOrthographicCamera===true,projection:viewer.stats().projection};
                }''')
                assert facts['inside'], (projection, view, facts)
                assert facts['orthographic'] == (projection == 'orthographic')
            page.evaluate("viewer.resetView('top')")
            page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
            for x, y, expected in ((3, 3, dict(kind='item', id='device')), (15.5, 3, dict(kind='item', id='skylight')),
                                    (12, 15, dict(kind='part', id='hall')), (20, 15, dict(kind='item', id='inverter-location'))):
                where = page.evaluate('p=>projectPoint(...p)', [x, y])
                count = page.evaluate('hits.length')
                page.mouse.click(where['x'], where['y'])
                if page.evaluate('hits.length') == count:
                    debug = page.evaluate('''point=>{
                      const bounds=document.querySelector('#scene canvas').getBoundingClientRect(),ray=new THREE.Raycaster();
                      ray.setFromCamera(new THREE.Vector2((point.x-bounds.x)/bounds.width*2-1,-(point.y-bounds.y)/bounds.height*2+1),actualCamera);
                      return {state:viewer.getViewState(),errors:window.hits,intersections:ray.intersectObjects(actualScene.children,true).slice(0,4).map(hit=>({distance:hit.distance,type:hit.object.type,data:hit.object.userData}))};
                    }''', where)
                    assert False, (projection, expected, where, debug)
                assert page.evaluate('hits.at(-1)') == expected
        where = page.evaluate('projectPoint(3,3)')
        page.keyboard.down('Control')
        page.mouse.click(where['x'], where['y'])
        page.keyboard.up('Control')
        assert page.evaluate('lastGesture.extend') is True
        assert page.evaluate('hits.at(-1)') == dict(kind='item', id='device')
        assert page.evaluate('''() => {let marker;actualScene.traverse(object=>{if(object.userData.editorMarker)marker=object;});return marker&&!marker.castShadow&&!marker.receiveShadow;}''')
        page.evaluate("viewer.highlightObjects([{kind:'item',id:'device'}])")
        assert page.evaluate('''() => {let found=false;actualScene.traverse(object=>{if(object.userData.sceneObject?.id==='device')found=object.material.emissive.getHex()!==0;});return found;}''')
        page.evaluate("viewer.focusObjects([{kind:'item',id:'device'}])")
        assert page.evaluate('viewer.stats().view') == 'selected'
        assert page.evaluate('viewer.getViewState().target[0]') < -10
        page.evaluate("viewer.resetView('south')")
        where = page.evaluate('projectPoint(12,0,2-current.project.roof.height_m)')
        count = page.evaluate('hits.length')
        page.mouse.click(where['x'], where['y'])
        assert page.evaluate('hits.length') == count, 'decorative wall panels cannot masquerade as roof selections'
        for index, fixture in enumerate(fixtures):
            page.evaluate('show', index)
            page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
            facts = page.evaluate('''() => {
              const walls=[];actualScene.traverse(object=>{if(object.userData.parapet)walls.push(object);});
              const expected=current.roof_geometry.parapets.map(face=>[0,2,1,0,3,2].flatMap(i=>normalized.world(face[i])));
              return {count:walls.length,exact:walls.every((object,i)=>Array.from(object.geometry.attributes.position.array).every((value,j)=>Math.abs(value-expected[i][j])<1e-5)),
                shadows:walls.every(object=>object.castShadow&&object.receiveShadow)};
            }''')
            assert facts == dict(count=len(fixture['roof_geometry']['parapets']), exact=True, shadows=True)
            page.evaluate('''() => {const empty=structuredClone(current);empty.roof_geometry.parapets=[];viewer.setData(empty);}''')
            assert page.evaluate('viewer.stats().parapets') == 0
        page.evaluate("show(0);viewer.setProjection('orthographic');viewer.resetView('iso')")
        page.mouse.move(500, 350)
        page.mouse.down()
        page.mouse.move(570, 380, steps=5)
        page.mouse.up()
        page.evaluate('window.savedView=viewer.getViewState();viewer.dispose();viewer=makeViewer();viewer.setData(current);viewer.setViewState(savedView)')
        restored = page.evaluate('viewer.getViewState()')
        saved = page.evaluate('savedView')
        assert restored['projection'] == saved['projection'] == 'orthographic'
        for key in ('position', 'target'):
            assert all(abs(a - b) < 1e-7 for a, b in zip(restored[key], saved[key]))
        assert restored['verticalSpan'] == saved['verticalSpan'] and restored['zoom'] == saved['zoom']
        page.locator('#scene').evaluate("element=>{element.style.width='680px';element.style.height='500px';}")
        page.wait_for_function('Math.abs(actualCamera.right/actualCamera.top-680/500)<1e-6')
        assert page.evaluate('original===JSON.stringify(fixtures)')
        page.screenshot(path=str(tmp_path / 'modeling-workbench.png'))
        assert not errors
        browser.close()
