"""Real WebGL pointer capture, drag, rotation, snapping and cancellation."""
from pathlib import Path

import numpy as np
import pytest
from playwright.sync_api import sync_playwright

from test_manual_modules import factory, add  # noqa: F401
from guangzhu import manual_modules
from guangzhu.roofplane import scene_geometry


def test_three_dimensional_gestures_submit_once_cancel_cleanly_and_preserve_view():
    web = Path(__file__).resolve().parents[1]/'desktop/web'
    html = '''<!doctype html><meta charset="utf-8"><div id="scene" style="width:1000px;height:700px"></div>
      <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
      <script>const Native=THREE.WebGLRenderer;THREE.WebGLRenderer=class extends Native {constructor(...args){super(...args);const render=this.render;
        this.render=(scene,camera)=>{window.actualScene=scene;window.actualCamera=camera;return render.call(this,scene,camera);};}};</script>
      <script type="module">import {createScene} from '/scene.js';import {transformModuleGeometry} from '/module-transform-geometry.js';
        const roof={type:'flat',height_m:5,parapet_height_m:0,outline:[[0,0],[24,0],[24,16],[0,16]],obstacles:[],keepouts:[]};
        const spec={available:true,length_m:2.4,width_m:1.1,gap_m:.02,lower_edge_m:.3};
        const base=(id,x,y)=>({id,center:[x,y,.6],corners:[[x-.55,y-1.2,.3],[x+.55,y-1.2,.3],[x+.55,y+1.2,.9],[x-.55,y+1.2,.9]],orientation:'portrait',tilt:15,azimuth:180});
        const modules=[base('one',5,5),base('two',10,5),base('neighbor',15,10)].map(m=>transformModuleGeometry(m,roof,{mode:'move',dx_m:0,dy_m:0},spec));
        window.input={project:{site:{lat:31.8,lon:119.9},roof},design:{version:1,modules},module_transform_spec:spec,
          shading:{version:1,modules:modules.map(m=>({id:m.id,total_loss_pct:8}))}};
        window.original=JSON.stringify(input);window.events=[];window.statuses=[];window.picks=[];
        window.viewer=createScene(document.querySelector('#scene'),{onModuleTransform:value=>events.push(value),onTransformStatus:value=>statuses.push(value),onSelectModule:id=>picks.push(id)});
        viewer.setData(input);viewer.setProjection('orthographic');viewer.resetView('top');viewer.setMode('heat');
        window.configure=(value={})=>viewer.setModuleEditing({enabled:true,mode:'move',busy:false,selectedIds:['one'],lockedIds:[],snap:{enabled:true,gridM:.1,angleDeg:15,align:false},...value});configure();
        window.point=(x,y,z)=>{const p=new THREE.Vector3(x-12,5+z,-(y-8)).project(actualCamera);const r=document.querySelector('canvas').getBoundingClientRect();return {x:r.x+(p.x+1)*r.width/2,y:r.y+(1-p.y)*r.height/2};};
        window.position=id=>{const m=input.design.modules.find(m=>m.id===id);return point(...m.center);};
        window.handle=()=>{let object;actualScene.traverse(o=>{if(o.userData.moduleTransformHandle)object=o;});return object;};
        window.ringPoint=angle=>{const h=handle(),p=new THREE.Vector3(Math.cos(angle)*h.geometry.parameters.radius,Math.sin(angle)*h.geometry.parameters.radius,0).applyMatrix4(h.matrixWorld).project(actualCamera);
          const r=document.querySelector('canvas').getBoundingClientRect();return {x:r.x+(p.x+1)*r.width/2,y:r.y+(1-p.y)*r.height/2};};
      </script>'''
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge', headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1100, height=800))
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def respond(route):
            path = route.request.url.split('transform.test', 1)[-1]
            if path == '/':
                route.fulfill(body=html, content_type='text/html')
            else:
                route.fulfill(path=str(web/path.lstrip('/')))

        page.route('**/*', respond)
        page.goto('http://transform.test/')
        page.wait_for_function('viewer.stats().frames>3&&viewer.stats().moduleEditing.handles===1')
        camera = page.evaluate('viewer.getViewState()')
        start = page.evaluate("position('one')")
        end = page.evaluate('point(6.04,5.64,input.design.modules[0].center[2])')
        page.mouse.move(start['x'], start['y'])
        page.mouse.down()
        page.mouse.move(end['x'], end['y'], steps=5)
        assert page.evaluate('viewer.stats().moduleEditing.dragging')
        assert page.evaluate('viewer.stats().moduleEditing.ghostPanels') == 1
        assert page.evaluate('''() => {let panel;actualScene.traverse(o=>{if(o.isInstancedMesh&&!o.userData.moduleTransform)panel=o;});return panel.material.type;}''') == 'MeshStandardMaterial'
        during = page.evaluate('viewer.getViewState()')
        assert during['position'] == pytest.approx(camera['position'], abs=1e-6)
        assert during['target'] == pytest.approx(camera['target'], abs=1e-6)
        assert during['moved'] == camera['moved']
        page.mouse.up()
        assert page.evaluate('events.length') == 1
        operation = page.evaluate('events[0]')
        assert abs(operation['dx_m']-1) < 1e-6 and abs(operation['dy_m']-.6) < 1e-6
        assert operation['module_ids'] == ['one'] and operation['snap']['kind'] == 'grid'
        assert page.evaluate('picks.length') == 0
        assert page.evaluate('viewer.stats().moduleEditing.ghostPanels') == 0
        assert page.evaluate('JSON.stringify(input)===original')
        # Alt disables grid snap, and both selected panels retain one shared delta.
        page.evaluate("configure({selectedIds:['one','two']})")
        page.keyboard.down('Alt')
        page.mouse.move(start['x'], start['y'])
        page.mouse.down()
        page.mouse.move(end['x'], end['y'], steps=3)
        assert page.evaluate('viewer.stats().moduleEditing.ghostPanels') == 2
        page.mouse.up()
        page.keyboard.up('Alt')
        operation = page.evaluate('events.at(-1)')
        assert operation['module_ids'] == ['one', 'two']
        assert abs(operation['dx_m']-1.04) < .002 and not operation['snap']['applied']
        # Esc, pointercancel and window blur all cancel without a server request.
        for cancel in ('escape', 'pointercancel', 'blur', 'busy', 'selection', 'mode', 'disabled'):
            page.evaluate('configure()')
            page.mouse.move(start['x'], start['y'])
            page.mouse.down()
            page.mouse.move(end['x'], end['y'], steps=3)
            assert page.evaluate('viewer.stats().moduleEditing.dragging')
            if cancel == 'escape':
                page.keyboard.press('Escape')
            elif cancel == 'pointercancel':
                page.evaluate("document.querySelector('canvas').dispatchEvent(new PointerEvent('pointercancel',{pointerId:1,bubbles:true}))")
            elif cancel == 'blur':
                page.evaluate("window.dispatchEvent(new Event('blur'))")
            else:
                page.evaluate({'busy': 'configure({busy:true})', 'selection': "configure({selectedIds:['two']})",
                               'mode': "configure({mode:'rotate'})", 'disabled': 'configure({enabled:false})'}[cancel])
            page.mouse.up()
            assert page.evaluate('events.length') == 2
            assert not page.evaluate('viewer.stats().moduleEditing.dragging')
            assert page.evaluate('viewer.stats().moduleEditing.ghostPanels') == 0
        page.evaluate("configure({mode:'rotate'})")
        page.evaluate('new Promise(resolve=>requestAnimationFrame(resolve))')
        a, b = page.evaluate('ringPoint(0)'), page.evaluate('ringPoint(Math.PI/4)')
        page.mouse.move(a['x'], a['y'])
        page.mouse.down()
        page.mouse.move(b['x'], b['y'], steps=8)
        assert page.evaluate('viewer.stats().moduleEditing.dragging')
        page.mouse.up()
        assert page.evaluate('events.length') == 3
        assert abs(abs(page.evaluate('events.at(-1).angle_deg'))-45) < 1e-6
        # Locking or invalidating a gesture disposes temporary meshes and restores controls.
        page.evaluate("configure({lockedIds:['one']})")
        assert not page.evaluate('viewer.stats().moduleEditing.enabled')
        page.mouse.move(start['x'], start['y'])
        page.mouse.down()
        page.mouse.move(end['x'], end['y'], steps=3)
        page.mouse.up()
        assert page.evaluate('events.length') == 3
        page.evaluate('configure()')
        page.mouse.move(start['x'], start['y'])
        page.mouse.down()
        page.mouse.move(end['x'], end['y'], steps=3)
        page.evaluate('viewer.setData(input,{preserveView:true})')
        page.mouse.up()
        assert page.evaluate('events.length') == 3
        assert page.evaluate('viewer.stats().moduleEditing.ghostPanels') == 0
        # A real drag whose final grid position is unchanged does not request a preview.
        page.evaluate('configure({snap:{enabled:true,gridM:1,angleDeg:15,align:false}})')
        tiny = page.evaluate('point(5.15,5.15,input.design.modules[0].center[2])')
        page.mouse.move(start['x'], start['y'])
        page.mouse.down()
        page.mouse.move(tiny['x'], tiny['y'], steps=3)
        page.mouse.up()
        assert page.evaluate('events.length') == 3
        assert '位置未改变' in page.evaluate('statuses.at(-1).text')
        # An available flag cannot turn a partial legacy catalog into approximate geometry.
        for spec in (None, dict(available=False, reason='规格不可用'), dict(available=True, length_m=2.4)):
            page.evaluate('spec=>{viewer.setData({...input,module_transform_spec:spec},{preserveView:true});configure();}', spec)
            assert not page.evaluate('viewer.stats().moduleEditing.enabled')
            assert page.evaluate('viewer.stats().moduleEditing.handles') == 0
            page.mouse.move(start['x'], start['y'])
            page.mouse.down()
            page.mouse.move(end['x'], end['y'], steps=3)
            page.mouse.up()
            assert page.evaluate('events.length') == 3
        page.evaluate('viewer.setData(input,{preserveView:true});configure()')
        # A selected panel behind real equipment is not draggable through that equipment.
        # The explicit overlay handle remains interactive, so hit the panel away from its handle.
        page.evaluate('''() => {const cover={id:'cover',kind:'box',height_m:4,footprint:[[4,4],[6,4],[6,7],[4,7]]};
          viewer.setData({...input,project:{...input.project,roof:{...input.project.roof,obstacles:[cover]}}},{preserveView:true});configure();}''')
        blocked_start = page.evaluate('point(5,5.8,input.design.modules[0].center[2])')
        blocked_end = page.evaluate('point(6,5.8,input.design.modules[0].center[2])')
        page.mouse.move(blocked_start['x'], blocked_start['y'])
        page.mouse.down()
        page.mouse.move(blocked_end['x'], blocked_end['y'], steps=3)
        assert not page.evaluate('viewer.stats().moduleEditing.dragging')
        page.mouse.up()
        assert page.evaluate('events.length') == 3
        page.evaluate('value=>viewer.setViewState(value)', camera)
        page.evaluate("actualScene.traverse(object=>{if(object.userData.sceneObject?.id==='cover')object.visible=false;})")
        page.mouse.move(blocked_start['x'], blocked_start['y'])
        page.mouse.down()
        page.mouse.move(blocked_end['x'], blocked_end['y'], steps=3)
        assert page.evaluate('viewer.stats().moduleEditing.dragging')
        page.mouse.up()
        assert page.evaluate('events.length') == 4
        page.evaluate('''() => {viewer.setData({...input,design:{...input.design,locked_regions:[{id:'empty',polygon:[[6,3],[9,3],[9,7],[6,7]]}]}},{preserveView:true});configure();}''')
        assert page.evaluate('viewer.stats().moduleEditing.lockedRegionSegments') == 4
        assert page.evaluate('''() => {let border;actualScene.traverse(o=>{if(o.userData.moduleTransform==='locked-regions')border=o;});
          return border.isLineSegments&&border.material.type==='LineDashedMaterial'&&!border.material.depthTest;}''')
        page.evaluate('configure({enabled:false})')
        assert page.evaluate('viewer.stats().moduleEditing.lockedRegionSegments') == 0
        page.evaluate('viewer.setData(input,{preserveView:true});configure()')
        # Rule targeting preserves projection and never mutates edit selection.
        page.evaluate("viewer.focusModules(['two'])")
        focused = page.evaluate('viewer.getViewState()')
        assert focused['projection'] == 'orthographic' and focused['view'] == 'selected'
        footprint = page.evaluate('''() => {const r=document.querySelector('canvas').getBoundingClientRect(),p=input.design.modules[1].corners.map(c=>point(...c));
          return {width:(Math.max(...p.map(p=>p.x))-Math.min(...p.map(p=>p.x)))/r.width,
            height:(Math.max(...p.map(p=>p.y))-Math.min(...p.map(p=>p.y)))/r.height,
            surrounding:[[7,2],[13,2],[13,8],[7,8]].map(([x,y])=>point(x,y,0)).every(p=>p.x>=r.x&&p.x<=r.right&&p.y>=r.y&&p.y<=r.bottom)};}''')
        assert max(footprint['width'], footprint['height']) < .4
        assert footprint['surrounding'], 'single-panel focus must retain three metres of surrounding roof'
        page.evaluate("viewer.focusModules(['missing'])")
        assert page.evaluate('viewer.getViewState()') == focused
        page.evaluate("viewer.focusModules(['one','two'])")
        assert page.evaluate('''() => {const r=document.querySelector('canvas').getBoundingClientRect();return input.design.modules.slice(0,2)
          .flatMap(m=>m.corners).map(c=>point(...c)).every(p=>p.x>r.x&&p.x<r.right&&p.y>r.y&&p.y<r.bottom);}''')
        # An undo/restored version can have historical parent differences. A new
        # gesture must show only its own before/after outlines, not that older turn.
        page.evaluate('''async()=>{const {transformModuleGeometry}=await import('/module-transform-geometry.js');
          const previous=transformModuleGeometry(input.design.modules[0],input.project.roof,{mode:'rotate',angle_deg:45},input.module_transform_spec);
          window.historical={...input,design:{...input.design,version:2,parent_version:1},
            parent_design:{...input.design,modules:[previous,...input.design.modules.slice(1)]}};
          viewer.setData(historical);viewer.resetView('top');configure();
          window.historyLines=()=>{const rows=[];actualScene.traverse(o=>{if(o.userData.previousOutlineCount||o.userData.candidateOutlineCount)rows.push(o);});return rows;};}''')
        assert page.evaluate('historyLines().length') == 2
        assert page.evaluate('historyLines().every(line=>line.visible)')
        history_start = page.evaluate("position('one')")
        history_end = page.evaluate('point(6,5.6,input.design.modules[0].center[2])')
        page.mouse.move(history_start['x'], history_start['y'])
        page.mouse.down()
        page.mouse.move(history_end['x'], history_end['y'], steps=3)
        assert page.evaluate('viewer.stats().moduleEditing.dragging')
        assert page.evaluate('historyLines().every(line=>!line.visible)')
        assert page.locator('#scene .scene-note').nth(1).is_hidden()
        page.keyboard.press('Escape')
        page.mouse.up()
        assert page.evaluate('historyLines().every(line=>line.visible)')
        assert page.locator('#scene .scene-note').nth(1).is_visible()
        page.evaluate('viewer.dispose()')
        assert page.locator('#scene canvas').count() == 0
        assert not errors
        browser.close()


@pytest.mark.parametrize('kind', ['metal', 'pitched'])
def test_slope_pointer_planes_and_ring_ghost_match_authoritative_backend(factory, kind):
    project, blank = factory(kind)
    placement = dict(center=[8, 8], rotation_deg=23)
    if kind == 'pitched':
        placement['plane_id'] = 1
    design = add(project, blank, [placement])
    spec = manual_modules.transform_spec(project, design)
    data = dict(project=project.model_dump(mode='json'), design=design.model_dump(mode='json'), module_transform_spec=spec,
                roof_geometry=scene_geometry(project.roof))
    web = Path(__file__).resolve().parents[1]/'desktop/web'
    html = '''<!doctype html><meta charset="utf-8"><div id="scene" style="width:1000px;height:700px"></div>
      <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
      <script>const Native=THREE.WebGLRenderer;THREE.WebGLRenderer=class extends Native {constructor(...args){super(...args);const render=this.render;
        this.render=(scene,camera)=>{window.actualScene=scene;window.actualCamera=camera;return render.call(this,scene,camera);};}};</script>
      <script type="module">import {createScene} from '/scene.js';import {normalizeScene} from '/scene-data.js';
        window.input=await(await fetch('/data.json')).json();window.expected=normalizeScene(input);window.events=[];
        window.viewer=createScene(document.querySelector('#scene'),{onModuleTransform:value=>events.push(value)});
        viewer.setData(input);viewer.setProjection('orthographic');viewer.resetView('top');
        window.configure=mode=>viewer.setModuleEditing({enabled:true,mode,selectedIds:[input.design.modules[0].id],lockedIds:[],snap:{enabled:false}});configure('move');
        window.screen=p=>{const q=new THREE.Vector3(...p).project(actualCamera),r=document.querySelector('canvas').getBoundingClientRect();
          return {x:r.x+(q.x+1)*r.width/2,y:r.y+(1-q.y)*r.height/2};};
        window.point=p=>screen(expected.world(p));
        window.ringPoint=angle=>{let h;actualScene.traverse(o=>{if(o.userData.moduleTransformHandle)h=o;});
          return screen(new THREE.Vector3(Math.cos(angle)*h.geometry.parameters.radius,Math.sin(angle)*h.geometry.parameters.radius,0).applyMatrix4(h.matrixWorld).toArray());};
        window.ghostCorners=()=>{let outline;actualScene.traverse(o=>{if(o.userData.moduleTransform==='new-position')outline=o;});
          const p=outline.geometry.attributes.position;return [0,2,4,6].map(i=>[p.getX(i)+expected.center[0],expected.center[1]-p.getZ(i),p.getY(i)-expected.roof.height_m]);};
      </script>'''
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge', headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1100, height=800))
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))

        def respond(route):
            path = route.request.url.split('slope-transform.test', 1)[-1]
            if path == '/':
                route.fulfill(body=html, content_type='text/html')
            elif path == '/data.json':
                route.fulfill(json=data)
            else:
                route.fulfill(path=str(web/path.lstrip('/')))

        page.route('**/*', respond)
        page.goto('http://slope-transform.test/')
        page.wait_for_function('viewer.stats().frames>3&&viewer.stats().moduleEditing.handles===1')
        page.evaluate('viewer.focusModules([input.design.modules[0].id])')
        footprint = page.evaluate('''() => {const r=document.querySelector('canvas').getBoundingClientRect(),p=input.design.modules[0].corners.map(point);
          return Math.max((Math.max(...p.map(p=>p.x))-Math.min(...p.map(p=>p.x)))/r.width,
            (Math.max(...p.map(p=>p.y))-Math.min(...p.map(p=>p.y)))/r.height);}''')
        assert footprint < .4, 'sloped-panel focus must retain roof context before a direct edit'
        move = dict(op='move_modules', module_ids=[design.modules[0].id], dx_m=.413, dy_m=.627)
        moved, _ = manual_modules.apply(project, design, move)
        start = page.evaluate('point(input.design.modules[0].center)')
        end = page.evaluate('p=>point(p)', moved.modules[0].center)
        page.mouse.move(start['x'], start['y'])
        page.mouse.down()
        page.mouse.move(end['x'], end['y'], steps=5)
        assert page.evaluate('viewer.stats().moduleEditing.dragging')
        np.testing.assert_allclose(page.evaluate('ghostCorners()'), moved.modules[0].corners, atol=3e-6, rtol=0)
        page.mouse.up()
        operation = page.evaluate('events[0]')
        assert operation['dx_m'] == pytest.approx(.413, abs=1e-5)
        assert operation['dy_m'] == pytest.approx(.627, abs=1e-5)
        page.evaluate("configure('rotate')")
        page.evaluate('new Promise(resolve=>requestAnimationFrame(resolve))')
        a, b = page.evaluate('ringPoint(0)'), page.evaluate('ringPoint(Math.PI/3)')
        page.mouse.move(a['x'], a['y'])
        page.mouse.down()
        page.mouse.move(b['x'], b['y'], steps=8)
        assert page.evaluate('viewer.stats().moduleEditing.dragging')
        angle = page.evaluate('viewer.stats().moduleEditing.operation.angle_deg')
        assert angle == pytest.approx(-60, abs=3e-5)
        rotated, _ = manual_modules.apply(project, design, dict(op='rotate_modules', module_ids=move['module_ids'], angle_deg=angle))
        np.testing.assert_allclose(page.evaluate('ghostCorners()'), rotated.modules[0].corners, atol=3e-6, rtol=0)
        page.mouse.up()
        assert page.evaluate('events.length') == 2
        # Same-face alignment follows the actual rotated panel edge and true mounting gap.
        module = design.modules[0]
        width = np.linalg.norm(np.subtract(module.corners[1], module.corners[0]))
        axis = np.subtract(module.corners[1], module.corners[0])/width
        neighbor = dict(center=[float(module.center[i]+axis[i]*(width+spec['gap_m']+1)) for i in range(2)], rotation_deg=23)
        if kind == 'pitched':
            neighbor['plane_id'] = 1
        adjacent = add(project, design, [neighbor])
        page.evaluate('value=>{input=value;viewer.setData(input,{preserveView:true});configure("move");viewer.setModuleEditing({snap:{enabled:true,gridM:0,align:true}});}',
                      {**data, 'design': adjacent.model_dump(mode='json')})
        almost, _ = manual_modules.apply(project, adjacent, dict(op='move_modules', module_ids=move['module_ids'],
                                                                 dx_m=float(axis[0]*.95), dy_m=float(axis[1]*.95)))
        start = page.evaluate('point(input.design.modules[0].center)')
        end = page.evaluate('p=>point(p)', almost.modules[0].center)
        page.mouse.move(start['x'], start['y'])
        page.mouse.down()
        page.mouse.move(end['x'], end['y'], steps=5)
        snapped = page.evaluate('viewer.stats().moduleEditing.operation')
        assert snapped['snap']['kind'] == 'gap'
        assert snapped['dx_m'] == pytest.approx(axis[0], abs=1e-5)
        assert snapped['dy_m'] == pytest.approx(axis[1], abs=1e-5)
        page.mouse.up()
        assert page.evaluate('events.length') == 3
        page.evaluate('viewer.dispose()')
        assert not errors
        browser.close()
