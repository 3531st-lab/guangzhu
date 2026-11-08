"""History differences are precise outline annotations, never coplanar filled panels."""
from pathlib import Path

from playwright.sync_api import sync_playwright

from guangzhu import layout, project as storage
from test_design_edits_api import editable_project  # noqa: F401


def test_removed_overlay_keeps_original_edges_without_fill_or_data_mutation(editable_project):
    project = editable_project
    parent = storage.load_design(project.id, 1).model_dump(mode='json')
    candidate = layout.generate_layout(project, {'orientation':'landscape'}).model_dump(mode='json')
    candidate.update(version=2,parent_version=1)
    for i,module in enumerate(candidate['modules']):
        module['id'] = f'reflow-{i}'
    data = dict(project=project.model_dump(mode='json'),design=candidate,parent_design=parent)
    web = Path(__file__).resolve().parents[1] / 'desktop/web'
    source = '''<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/scene.css">
      <div id="scene" style="width:1000px;height:700px"></div>
      <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
      <script>const NativeRenderer=THREE.WebGLRenderer;
      THREE.WebGLRenderer=class extends NativeRenderer {constructor(...args){super(...args);
        const draw=this.render;this.render=(scene,camera)=>{window.actualScene=scene;return draw.call(this,scene,camera);};}};</script>
      <script type="module">import {createScene} from '/scene.js';import {normalizeScene} from '/scene-data.js';
        const input=await(await fetch('/data.json')).json();window.sourceData=input;window.before=JSON.stringify(input);
        window.expected=normalizeScene(input);window.viewer=createScene(document.querySelector('#scene'));viewer.setData(input);
      </script>'''
    with sync_playwright() as automation:
        browser=automation.chromium.launch(channel='msedge',headless=True,args=['--enable-webgl','--use-angle=swiftshader'])
        page=browser.new_page(viewport=dict(width=1100,height=800))
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def respond(route):
            path=route.request.url.split('offline.test',1)[-1]
            if path == '/':
                route.fulfill(body=source,content_type='text/html')
            elif path == '/data.json':
                route.fulfill(json=data)
            else:
                route.fulfill(path=str(web/path.lstrip('/')))
        page.route('**/*',respond)
        page.goto('http://offline.test/')
        page.wait_for_function('window.viewer?.stats().frames > 3')
        facts=page.evaluate('''() => {
          const outlines=[],panels=[];actualScene.traverse(object=>{
            if(object.userData.removedOutlineCount)outlines.push(object);
            if(object.isInstancedMesh)panels.push(object);
          });
          const outline=outlines[0],points=outline?.geometry.attributes.position;
          const expectedPoints=expected.removed.flatMap(module=>module.points.flatMap((point,i)=>[point,module.points[(i+1)%4]]));
          const exact=expectedPoints.every((point,i)=>point.every((value,axis)=>Math.abs(points.array[3*i+axis]-value)<1e-5));
          window.oldOutline=outline;outline.geometry.addEventListener('dispose',()=>window.outlineDisposed=true);
          return {outlines:outlines.length,lineSegments:outline?.isLineSegments,mesh:outline?.isMesh===true,
            depthTest:outline?.material.depthTest,depthWrite:outline?.material.depthWrite,
            count:outline?.userData.removedOutlineCount,vertices:points?.count,exact,
            panelMeshes:panels.length,panels:panels[0]?.count,unchanged:before===JSON.stringify(sourceData)};
        }''')
        assert facts == dict(outlines=1,lineSegments=True,mesh=False,depthTest=False,depthWrite=False,
                             count=len(parent['modules']),vertices=8*len(parent['modules']),exact=True,
                             panelMeshes=1,panels=len(candidate['modules']),unchanged=True)
        assert page.get_by_text(f'红色边框：相对 v1 移除的 {len(parent["modules"])} 块组件').is_visible()
        page.evaluate('viewer.setData({...sourceData,parent_design:null})')
        assert page.evaluate('viewer.stats().removed') == 0
        assert page.evaluate('window.outlineDisposed')
        assert page.get_by_text('红色边框：',exact=False).is_hidden()
        assert page.evaluate('before===JSON.stringify(sourceData)')
        assert not errors
        browser.close()
