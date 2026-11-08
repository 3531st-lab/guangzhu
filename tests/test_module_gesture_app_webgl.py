"""Real pointer drag in the production app reaches preview, explicit save and undo."""
from pathlib import Path
import hashlib
import json

import pytest
from playwright.sync_api import sync_playwright

from test_manual_editor_dom import editor_factory, factory, edit_client  # noqa: F401
from test_module_gesture_editor_dom import seed
from test_design_edits_async_dom import geometry
from guangzhu import analysis, project as storage


@pytest.mark.parametrize('display_mode', ['light', 'wiring'])
def test_real_drag_keeps_selection_previews_once_and_can_save_then_undo(editor_factory,edit_client,tmp_path,display_mode):
    record, original, free, locked = seed(editor_factory)
    # A production result includes computed wind/electrical cards. Hiding them
    # must not resize the live canvas and cancel or distort an active gesture.
    analysis.analyze(record.id, original.version, offline=True)
    web = Path(__file__).resolve().parents[1]/'desktop/web'
    app = (web/'app.js').read_text(encoding='utf-8')+'\nwindow.testApp={state,get scene(){return scene;}};'
    instrument = '''<script>const NativeRenderer=THREE.WebGLRenderer;
      THREE.WebGLRenderer=class extends NativeRenderer {constructor(...args){super(...args);const draw=this.render;
        this.render=(scene,camera)=>{window.actualScene=scene;window.actualCamera=camera;return draw.call(this,scene,camera);};}};</script>'''
    html = (web/'index.html').read_text(encoding='utf-8').replace('<script type="module" src="/app.js">',instrument+'<script type="module" src="/app.js">')
    fake_bridge = '''export function setAghOrigin(){} export class Bridge {
      constructor(frame,onMessage){this.frame=frame;this.onMessage=onMessage;this.ready=true;this.models=[];this.logs=[];}
      setAvailable(){} setTheme(){} send(){}
    }'''
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge',headless=True,args=['--enable-webgl','--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1600,height=1000))
        errors,requests = [],[]
        page.on('pageerror',lambda error:errors.append(str(error)))

        def respond(route):
            request = route.request
            path = request.url.split('gesture-app.test',1)[-1]
            fixtures = {'/api/roofs':{'roofs':[]},'/api/runs':{'runs':[]},'/api/status':{'agh':{'connected':False}},
                        '/api/setup/status':{'installation':{'installed':False,'id':'development'},'required':False,'ready':True,'steps':[]}}
            if path in fixtures:
                route.fulfill(json=fixtures[path])
            elif path.startswith('/api/'):
                response = edit_client.request(request.method,path,content=request.post_data_buffer,headers={'content-type':'application/json'})
                requests.append((path,request.post_data_json if request.post_data else None))
                route.fulfill(status=response.status_code,body=response.content,content_type='application/json')
            elif path == '/':
                route.fulfill(body=html,content_type='text/html')
            elif path == '/app.js':
                route.fulfill(body=app,content_type='text/javascript')
            elif path == '/bridge.js':
                route.fulfill(body=fake_bridge,content_type='text/javascript')
            else:
                target = web/path.lstrip('/')
                route.fulfill(path=str(target)) if target.is_file() else route.abort()

        page.route('**/*',respond)
        page.goto(f'http://gesture-app.test/#result/{record.id}?version=3')
        page.locator('[data-result-tab="局部修改"]').click()
        page.wait_for_function('testApp.scene?.stats().frames>3')
        page.evaluate("testApp.scene.setProjection('orthographic');testApp.scene.resetView('top')")
        page.evaluate('''async()=>{
          const {normalizeScene}=await import('/scene-data.js');
          window.projectPoint=point=>{const normalized=normalizeScene(testApp.state.result.scene);
            const p=new THREE.Vector3(...normalized.world(point)).project(actualCamera),box=document.querySelector('#scene canvas').getBoundingClientRect();
            return {x:box.x+(p.x+1)*box.width/2,y:box.y+(1-p.y)*box.height/2};};
        }''')
        page.locator(f'[data-edit-module="{free}"]').click()
        page.locator('[data-design-edit="tool:move"]').click()
        page.locator('[data-edit-snap="align"]').uncheck()
        page.locator(f'[data-scene-mode="{display_mode}"]').click()
        page.wait_for_function('testApp.scene.stats().moduleEditing.handles===1')
        page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        assert page.locator('#wind-summary').is_visible()
        assert page.locator('#wiring-tools').is_visible() == (display_mode == 'wiring')
        center = list(original.modules[0].center)
        start = page.evaluate('projectPoint',center)
        end = page.evaluate('projectPoint',[center[0]+.64,center[1]+.36,center[2]])
        camera = page.evaluate('testApp.scene.getViewState()')
        canvas_box = page.locator('#scene canvas').bounding_box()
        page.mouse.move(start['x'],start['y'])
        page.mouse.down()
        page.mouse.move(end['x'],end['y'],steps=6)
        assert page.evaluate('testApp.state.editing.dragging')
        assert page.evaluate('testApp.scene.stats().moduleEditing.ghostPanels') == 1
        assert page.locator('#scene canvas').bounding_box() == pytest.approx(canvas_box, abs=1e-6)
        during_camera = page.evaluate('testApp.scene.getViewState()')
        for field in ('position', 'target', 'zoom', 'verticalSpan'):
            assert during_camera[field] == pytest.approx(camera[field], abs=1e-6)
        assert page.locator('#wind-summary').is_hidden()
        assert page.locator('#wiring-tools').is_hidden()
        assert page.locator('#heat-legend').is_hidden()
        page.mouse.up()
        page.locator('.de-preview').wait_for()
        previews = [body for path,body in requests if path.endswith('/preview')]
        assert len(previews) == 1
        operation = previews[0]['ops'][0]
        assert operation['op'] == 'move_modules' and operation['module_ids'] == [free]
        assert operation['dx_m'] == pytest.approx(.6,abs=1e-6)
        assert operation['dy_m'] == pytest.approx(.4,abs=1e-6)
        assert operation['dx_m']/.1 == pytest.approx(round(operation['dx_m']/.1))
        assert operation['dy_m']/.1 == pytest.approx(round(operation['dy_m']/.1))
        assert page.evaluate('[...testApp.state.editing.selected]') == [free]
        assert page.evaluate('testApp.scene.stats().moduleEditing.ghostPanels') == 0
        after_camera = page.evaluate('testApp.scene.getViewState()')
        assert after_camera['position'] == pytest.approx(camera['position'],abs=1e-6)
        assert after_camera['target'] == pytest.approx(camera['target'],abs=1e-6)
        candidate = page.evaluate('testApp.state.editing.preview.design')
        page.locator('[data-design-edit="apply"]').click()
        page.wait_for_function('testApp.state.result?.version===4 && !testApp.state.editing.preview')
        assert geometry(page.evaluate('testApp.state.result.design')) == geometry(candidate)
        page.locator('[data-design-edit="undo"]').click()
        page.locator('.de-preview').wait_for()
        page.locator('[data-design-edit="apply"]').click()
        page.wait_for_function('testApp.state.result?.version===5 && !testApp.state.editing.preview')
        assert geometry(page.evaluate('testApp.state.result.design')) == geometry(original.model_dump(mode='json'))
        # A protected panel remains selectable for unlocking, but cannot start a drag.
        page.locator(f'[data-edit-module="{locked}"]').click()
        page.locator('[data-design-edit="tool:move"]').click()
        page.evaluate("testApp.scene.setProjection('orthographic');testApp.scene.resetView('top')")
        point = page.evaluate('projectPoint',list(original.modules[1].center))
        count = len([path for path,_ in requests if path.endswith('/preview')])
        page.mouse.move(point['x'],point['y'])
        page.mouse.down()
        page.mouse.move(point['x']+25,point['y']+10,steps=3)
        page.mouse.up()
        assert page.evaluate('testApp.scene.stats().moduleEditing.ghostPanels') == 0
        assert len([path for path,_ in requests if path.endswith('/preview')]) == count
        assert not errors
        page.screenshot(path=str(tmp_path/'manual-gesture-app.png'))
        browser.close()


def test_real_drag_into_locked_empty_region_is_rejected_without_changing_files_or_view(editor_factory, edit_client):
    record, original, free, locked = seed(editor_factory)
    folder = storage._path(record.id)

    def hashes():
        return {path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(folder.rglob('*')) if path.is_file()}

    operation = dict(op='move_modules', module_ids=[free], dx_m=4, dy_m=6)
    request = dict(version=original.version, ops=[operation], reason='证明目标空白本可安装', detailed=False)
    initial_files = hashes()
    allowed = edit_client.post(f'/api/projects/{record.id}/design-edits/preview', json=request)
    assert allowed.status_code == 200, allowed.text
    allowed_module = next(module for module in allowed.json()['design']['modules'] if module['id'] == free)
    assert allowed_module['center'][:2] == pytest.approx([12, 14])
    assert hashes() == initial_files, 'the unlocked precondition preview must be read-only'
    lock = storage.edit_design(record.id, original.version, [dict(op='lock_region', id='empty-space',
        polygon=[[10,12],[14,12],[14,16],[10,16]])], '锁定可安装空白作为明确保留区', 'user', offline=True)
    saved = storage.load_design(record.id, lock['version'])
    assert geometry(saved.model_dump(mode='json')) == geometry(original.model_dump(mode='json'))
    before = hashes()
    design_path = f'designs/v{saved.version}.json'
    web = Path(__file__).resolve().parents[1]/'desktop/web'
    app = (web/'app.js').read_text(encoding='utf-8')+'\nwindow.testApp={state,get scene(){return scene;}};'
    instrument = '''<script>const NativeRenderer=THREE.WebGLRenderer;
      THREE.WebGLRenderer=class extends NativeRenderer {constructor(...args){super(...args);const draw=this.render;
        this.render=(scene,camera)=>{window.actualScene=scene;window.actualCamera=camera;return draw.call(this,scene,camera);};}};</script>'''
    html = (web/'index.html').read_text(encoding='utf-8').replace('<script type="module" src="/app.js">',instrument+'<script type="module" src="/app.js">')
    bridge = '''export function setAghOrigin(){} export class Bridge {
      constructor(){this.ready=true;this.models=[];this.logs=[];}setAvailable(){} setTheme(){} send(){throw Error('No model call is allowed');}}'''
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge',headless=True,args=['--enable-webgl','--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1600,height=1000))
        errors, requests = [], []
        page.on('pageerror',lambda error:errors.append(str(error)))

        def respond(route):
            incoming = route.request
            path = incoming.url.split('locked-region.test',1)[-1]
            fixtures = {'/api/roofs':{'roofs':[]},'/api/runs':{'runs':[]},'/api/status':{'agh':{'connected':False}},
                        '/api/setup/status':{'installation':{'installed':False,'id':'development'},'required':False,'ready':True,'steps':[]}}
            if path in fixtures:
                route.fulfill(json=fixtures[path])
            elif path.startswith('/api/'):
                response = edit_client.request(incoming.method,path,content=incoming.post_data_buffer,headers={'content-type':'application/json'})
                requests.append(dict(path=path,method=incoming.method,status=response.status_code,
                                     body=incoming.post_data_json if incoming.post_data else None,response=response.json()))
                route.fulfill(status=response.status_code,body=response.content,content_type='application/json')
            elif path == '/':
                route.fulfill(body=html,content_type='text/html')
            elif path == '/app.js':
                route.fulfill(body=app,content_type='text/javascript')
            elif path == '/bridge.js':
                route.fulfill(body=bridge,content_type='text/javascript')
            else:
                target = web/path.lstrip('/')
                route.fulfill(path=str(target)) if target.is_file() else route.abort()

        page.route('**/*',respond)
        page.goto(f'http://locked-region.test/#result/{record.id}?version={saved.version}')
        page.locator('[data-result-tab="局部修改"]').click()
        page.wait_for_function('testApp.scene?.stats().frames>3')
        assert free not in page.evaluate('testApp.state.result.locked_modules')
        page.evaluate("testApp.scene.setProjection('orthographic');testApp.scene.resetView('top')")
        page.evaluate('''async()=>{const {normalizeScene}=await import('/scene-data.js');
          window.projectPoint=point=>{const data=normalizeScene(testApp.state.result.scene),p=new THREE.Vector3(...data.world(point)).project(actualCamera),r=document.querySelector('#scene canvas').getBoundingClientRect();
            return {x:r.x+(p.x+1)*r.width/2,y:r.y+(1-p.y)*r.height/2};};}''')
        page.locator(f'[data-edit-module="{free}"]').click()
        page.locator('[data-design-edit="tool:move"]').click()
        page.locator('[data-edit-snap="align"]').uncheck()
        page.wait_for_function('testApp.scene.stats().moduleEditing.handles===1')
        page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
        assert page.evaluate('testApp.scene.stats().moduleEditing.lockedRegionSegments') == 4
        camera = page.evaluate('testApp.scene.getViewState()')
        canvas_box = page.locator('#scene canvas').bounding_box()
        start = page.evaluate('projectPoint',list(saved.modules[0].center))
        end = page.evaluate('projectPoint',allowed_module['center'])
        page.mouse.move(start['x'],start['y'])
        page.mouse.down()
        page.mouse.move(end['x'],end['y'],steps=12)
        assert page.evaluate('testApp.state.editing.dragging')
        assert page.evaluate('testApp.scene.stats().moduleEditing.ghostPanels') == 1
        assert page.locator('#scene canvas').bounding_box() == pytest.approx(canvas_box, abs=1e-6)
        assert not any(row['method']=='POST' for row in requests), 'a drag must not preview before pointer release'
        page.mouse.up()
        page.locator('.de-error').wait_for()
        edits = [row for row in requests if row['method']=='POST']
        assert len(edits) == 1 and edits[0]['path'].endswith('/design-edits/preview')
        rejected = edits[0]
        assert rejected['body']['ops'] == [operation], 'the lock is the only difference from the successful precondition'
        assert rejected['status'] == 422 and rejected['response']['error_code'] == 'DESIGN_LOCK_CONFLICT'
        assert '锁定区域' in page.locator('.de-error').inner_text()
        assert page.locator('.de-preview').count() == 0
        assert page.locator('[data-design-edit="apply"]').count() == 0
        assert page.evaluate('[...testApp.state.editing.selected]') == [free]
        assert not page.evaluate('testApp.state.editing.busy || testApp.state.editing.dragging || testApp.state.editing.preview')
        assert page.evaluate('testApp.state.editing.request') is None
        facts = page.evaluate('testApp.scene.stats()')
        assert not facts['preview'] and facts['moduleEditing']['ghostPanels'] == 0
        assert facts['moduleEditing']['handles'] == 1 and facts['moduleEditing']['lockedRegionSegments'] == 4
        assert geometry(page.evaluate('testApp.state.result.design')) == geometry(saved.model_dump(mode='json'))
        after_camera = page.evaluate('testApp.scene.getViewState()')
        for field in ('position','target','zoom','verticalSpan'):
            assert after_camera[field] == pytest.approx(camera[field], abs=1e-6)
        assert storage.next_version(record.id) == saved.version+1
        after = hashes()
        assert after == before, 'failed lock preview must preserve every design, project and analysis file byte'
        assert not errors
        print('LOCKED_REGION_PROOF '+json.dumps(dict(unlocked_preview_status=allowed.status_code,locked_preview_status=rejected['status'],
            error_code=rejected['response']['error_code'],version=saved.version,next_version=storage.next_version(record.id),
            checked_files=len(before),files_unchanged=before==after,design_sha256_before=before[design_path],design_sha256_after=after[design_path],
            operation=rejected['body']['ops'][0],selected_ids=[free],camera_unchanged=True,ghost_panels=0,candidate_cleared=True,
            preview_requests=1,apply_requests=0,page_errors=errors),ensure_ascii=False))
        browser.close()
