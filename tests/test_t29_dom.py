"""Real browser UI; local API and native bridge signals remain strictly offline."""
import hashlib
import json
import os
import shutil

import pytest

from guangzhu import api, park_queue, park_store as store
from test_t16_dom import browser_app
from test_t29_api_report import parks_api, ROOT, HEADERS
from test_t29_store import workspace


@pytest.fixture
def park_browser(browser_app, parks_api, monkeypatch):
    page, errors = browser_app
    client, root, entries = parks_api
    archived = {}
    state = dict(fail_finish=False, hard_failure=False, archive_visible=False)
    def record(path):
        return archived[path.name]
    monkeypatch.setattr(api, 'record', record)
    def route(request):
        path = request.request.url.split('offline.test', 1)[1]
        if path.startswith(('/api/status', '/api/setup/', '/api/tilt')) or path.endswith('/tilt'):
            return request.fulfill(json=dict(agh=dict(connected=False), required=False, ready=True, available=False,
                                            installation=dict(installed=False, id='development'), steps=[]))
        if path == '/api/runs':
            return request.fulfill(json=dict(runs=[]))
        if path.startswith('/api/runs/gz-'):
            if state['archive_visible'] and path.rsplit('/', 1)[-1] in archived:
                capture, meta, verification = archived[path.rsplit('/', 1)[-1]]
                return request.fulfill(json=dict(verification=verification, timeline=dict(nodes=[])))
            return request.fulfill(status=404, json=dict(error='offline archive detail not requested'))
        if path == '/api/runs/finish':
            if state['fail_finish']:
                return request.fulfill(status=400, json=dict(error='离线模拟归档失败'))
            body = request.request.post_data_json
            item = park_queue.current(park_queue.load('factory', root))
            original = entries[0] if item.spec.template.endswith('--low') else entries[1]
            row, capture, metadata = original
            source = store.read(capture / 'project/project.json')
            source['id'] = item.spec.id
            store.write(capture / 'project/project.json', source)
            meta = dict(metadata, session=item.design_session, project_id=item.spec.id)
            meta['artifacts']['project/project.json'] = hashlib.sha256((capture / 'project/project.json').read_bytes()).hexdigest()
            review = body.get('review_session_id') is not None
            if review:
                meta.update(review_session_id=item.review_session, review_capture='reviews/offline')
            checks = [dict(stage=name, passed=not state['hard_failure']) for name in ['任务规划', '能力调用', '反馈处理', '结果验证']]
            verification = dict(passed=not state['hard_failure'], checks=checks, verified_exports=[dict(version=1)] if item.spec.export else [],
                                review=dict(requested=item.spec.review, passed=review))
            archived['gz-' + item.spec.id] = (capture, meta, verification)
            return request.fulfill(json=dict(run_id='gz-' + item.spec.id, selected_version=1 if item.spec.export else None,
                verification=verification, usage_by_session={}, review_prompt='离线审核',
                result=dict(project_id=item.spec.id, version=1, selected_version=1)))
        response = client.request(request.request.method, path, json=request.request.post_data_json
                                  if request.request.method == 'POST' else None, headers=HEADERS)
        request.fulfill(status=response.status_code, body=response.content, content_type='application/json')
    page.route('**/api/**', route)
    page.add_init_script("""Object.defineProperty(window, 'testApp', {configurable:true, set(value) {
      value.bridge.workspaceBinding='a'.repeat(64);
      Object.defineProperty(window, 'testApp', {value, writable:true, configurable:true});
    }});""")
    page.goto('http://offline.test/#park')
    page.locator('#park-map').wait_for()
    page.evaluate("""() => {
      const design={id:'offline-design',route:'offline'}, review={id:'agnes-3.0-flash',route:'offline'};
      testApp.bridge.models=[design,review];
      testApp.bridge.workspaceBinding='a'.repeat(64);
      testApp.state.designModel=design;
      testApp.state.reviewModel=review;
    }""")
    return page, errors, root, state


def current(root):
    return park_queue.current(park_queue.load('factory', root))


def opened(page):
    page.evaluate("""() => {
      const b=testApp.bridge, m=b.logs.filter(m=>m.type==='gz.start').at(-1);
      b.onMessage({type:'gz.session',session_id:m.session_key},m.request);
    }""")
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.parkPrompt' && m.session_id===testApp.state.active)")


def progress(page, op, review=False, export=True):
    page.evaluate("""({op,review,exported}) => {
      const a=testApp, s=a.state.sessions.get(a.state.active);
      const node=review ? {name:'gz_record_review',result_json:{ok:true,file:'v1-review.json',verdict:'approve'}} :
        {name:'gz_export',result_json:{ok:true,version:1}};
      a.bridge.onMessage({type:'gz.progress',session_id:s.id,op,started:true,
        nodes:exported ? [{kind:'tool',status:'completed',...node}] : []});
    }""", dict(op=op, review=review, exported=export))


def test_legacy_summary_link_keeps_parent_navigation_and_returns_to_named_park(park_browser):
    page, errors, _, _ = park_browser
    park_tab = page.locator('.navtabs a[href="#park"]')
    assert park_tab.get_attribute('aria-current') == 'page'
    page.get_by_role('link', name='已有设计汇总').click()
    page.wait_for_function("testApp.state.route === 'park-legacy'")
    assert park_tab.get_attribute('aria-current') == 'page'
    page.locator('.navtabs a[href="#records"]').click()
    page.locator('.navtabs a[href="#records"][aria-current="page"]').wait_for()
    park_tab.click()
    page.locator('#park-map').wait_for()
    assert park_tab.get_attribute('aria-current') == 'page'
    assert page.locator('[data-pselect]').input_value() == 'factory'
    assert errors == []


def test_map_edit_settings_and_owned_delete(park_browser):
    page, errors, root, _ = park_browser
    page.locator('[data-pfield="name"]').fill('离线验收厂区')
    page.locator('[data-paction="save"]').click()
    page.wait_for_function("document.querySelector('[data-pselect]').selectedOptions[0].textContent==='离线验收厂区'")
    group = page.locator('[data-building="high"] polygon').first.bounding_box()
    page.mouse.move(group['x'] + group['width'] / 2, group['y'] + group['height'] / 2)
    page.mouse.down()
    page.mouse.move(group['x'] + group['width'] / 2 + 40, group['y'] + group['height'] / 2, steps=4)
    page.mouse.up()
    page.wait_for_timeout(200)
    assert store.load('factory', root).buildings[1].x_m > 20
    page.locator('[data-rotate="high"]').fill('10')
    page.locator('[data-rotate="high"]').press('Tab')
    page.wait_for_timeout(200)
    assert store.load('factory', root).buildings[1].rotation_deg == 10
    page.locator('[data-config="shared"]').click()
    page.locator('[data-field="text"]').fill('保留检修通道，离线条件验收')
    page.locator('[data-action="park-settings-save"]').click()
    page.locator('#park-map').wait_for()
    assert store.load('factory', root).settings['shared']['text'] == '保留检修通道，离线条件验收'
    page.locator('[data-config="low"]').click()
    page.locator('[data-field="fKwh"]').fill('20')
    page.locator('[data-action="park-settings-save"]').click()
    page.locator('#park-map').wait_for()
    assert store.load('factory', root).settings['low']['fKwh'] == '20'
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('[data-paction="delete"]').click()
    page.wait_for_function("!document.querySelector('#park-map')")
    assert (root / 'data/my-roofs/low/project.json').exists()
    assert not errors


def test_normal_fifo_approval_restart_review_pause_failure(park_browser):
    page, errors, root, state = park_browser
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    first = current(root)
    assert first.status == 'creating'
    opened(page)
    assert current(root).status == 'sending'
    page.evaluate("testApp.bridge.onMessage({type:'gz.approval',session_id:testApp.state.active,tool:'gz_export',pending:true})")
    page.wait_for_function("document.querySelector('#park-queue-display').textContent.includes('等待原生批准')")
    assert current(root).status == 'approval'
    page.goto('http://offline.test/#park')
    page.reload()
    page.locator('[data-paction="resume"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.open')")
    assert page.evaluate("testApp.bridge.logs.filter(m=>['gz.start','gz.parkPrompt'].includes(m.type)).length") == 0
    page.evaluate("""() => {
      const d={id:'offline-design',route:'offline'}, r={id:'agnes-3.0-flash',route:'offline'};
      testApp.bridge.models=[d,r];
      testApp.state.designModel=d;
      testApp.state.reviewModel=r;
      testApp.bridge.onMessage({type:'gz.approval',session_id:testApp.state.active,tool:'gz_export',pending:false});
    }""")
    progress(page, 'running')
    progress(page, 'idle')
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start' && m.session_key.startsWith('park-review-'))")
    assert current(root).stage == 'review' and current(root).id == first.id
    opened(page)
    progress(page, 'running', review=True)
    page.locator('[data-action="park-pause"]').click()
    page.wait_for_function("document.querySelector('#park-queue-display').textContent.includes('已暂停')")
    progress(page, 'idle', review=True)
    page.wait_for_function("document.querySelector('#park-queue-display').textContent.includes('已结束')")
    assert current(root).status == 'pending'
    # the passed review leaves the AGH panel where it is: going back to the design would race the next building's new session
    assert page.evaluate("testApp.bridge.logs.filter(m=>m.type==='gz.open').length") == 1
    page.locator('[data-action="park-resume"]').click()
    page.wait_for_function("testApp.bridge.logs.filter(m=>m.type==='gz.start').length===2")
    opened(page)
    state['fail_finish'] = True
    progress(page, 'running')
    progress(page, 'idle')
    page.wait_for_function("document.querySelector('#park-queue-display').textContent.includes('归档未完成')")
    assert current(root) is None
    assert [item.status for item in park_queue.load('factory', root).items] == ['completed', 'failed']
    assert not errors


def test_demo_and_queue_screenshots_are_opt_in(park_browser):
    page, errors, root, _ = park_browser
    for key in ('07', '09', '10', '11'):
        shutil.copytree(ROOT / 'data/roofs' / ('t12-real-' + key), root / 'data/roofs' / ('t12-real-' + key))
    shutil.copy2(ROOT / 'data/roofs/osm-raw.json', root / 'data/roofs/osm-raw.json')
    page.locator('[data-paction="demo"]').click()
    page.wait_for_function("document.querySelectorAll('#park-map [data-building]').length===4")
    if os.environ.get('GUANGZHU_T29_CAPTURE') == '1':
        output = ROOT / 'reports/assets/T29'
        page.locator('.park-editor').screenshot(path=str(output / 'park-map.png'))
        (output / 'demo-park.json').write_text(json.dumps(store.load('wujin-demo', root).model_dump(), ensure_ascii=False, indent=2), encoding='utf-8')
    page.locator('[data-pselect]').select_option('factory')
    page.wait_for_function("document.querySelectorAll('#park-map [data-building]').length===2")
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    opened(page)
    page.evaluate("testApp.bridge.onMessage({type:'gz.approval',session_id:testApp.state.active,tool:'gz_export',pending:true})")
    page.wait_for_function("document.querySelector('#park-queue-display').textContent.includes('等待原生批准')")
    if os.environ.get('GUANGZHU_T29_CAPTURE') == '1':
        page.locator('#park-queue-display').evaluate("el => el.insertAdjacentHTML('afterbegin','<p>离线模拟审批信号，未调用真实模型</p>')")
        page.locator('#park-queue-display').screenshot(path=str(ROOT / 'reports/assets/T29/batch-queue.png'))
    assert not errors


@pytest.mark.parametrize('review,export', [(False, True), (False, False), (True, False)])
def test_original_review_export_switches_reach_terminal(park_browser, review, export):
    page, errors, root, _ = park_browser
    saved = store.load('factory', root).model_dump()
    saved['settings'] = dict(shared=dict(review=review, exportOn=export))
    store.save(saved, root)
    page.reload()
    page.locator('#park-map').wait_for()
    page.evaluate("""() => {
      const model={id:'offline-design',route:'offline'};
      const reviewer={id:'agnes-3.0-flash',route:'offline'};
      testApp.bridge.models=[model,reviewer];
      testApp.state.designModel=model;
      testApp.state.reviewModel=reviewer;
    }""")
    page.locator('[data-pick="high"]').uncheck()
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    opened(page)
    progress(page, 'running', export=export)
    progress(page, 'idle', export=export)
    for _ in range(100):  # archive and queue writes take longer on a busy machine
        if current(root) is None:
            break
        page.wait_for_timeout(100)
    assert current(root) is None, (park_queue.load('factory', root).model_dump(),
                                  page.locator('#park-queue-display').inner_text(),
                                  page.evaluate("[...testApp.state.sessions.values()]"))
    assert current(root) is None
    assert page.evaluate("testApp.bridge.logs.filter(m=>m.type==='gz.start').length") == 1
    assert not errors


def test_skip_cancel_ack_and_park_selection_binding(park_browser):
    page, errors, root, _ = park_browser
    saved = store.load('factory', root).model_dump()
    saved.update(id='other', name='另一园区')
    store.save(saved, root)
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    opened(page)
    first = current(root)
    progress(page, 'running')
    page.evaluate("location.hash='#park'")
    page.locator('[data-pselect]').select_option('other')
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("document.body.textContent.includes('另一园区队列尚未结束')")
    assert not park_queue.load('other', root).items
    assert current(root).id == first.id
    page.locator('[data-pselect]').select_option('factory')
    page.locator('[data-paction="skip"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.open')")
    progress(page, 'running')
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.cancel')")
    assert current(root).status == 'cancelling'
    assert page.evaluate("testApp.bridge.logs.filter(m=>m.type==='gz.start').length") == 1
    progress(page, 'idle')
    page.wait_for_function("testApp.bridge.logs.filter(m=>m.type==='gz.start').length===2")
    assert current(root).id != first.id
    assert park_queue.load('factory', root).items[0].status == 'skipped'
    assert not errors


def test_hard_failed_design_advances_without_review(park_browser):
    page, errors, root, state = park_browser
    state['hard_failure'] = True
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    opened(page)
    progress(page, 'running')
    progress(page, 'idle')
    page.wait_for_function("testApp.bridge.logs.filter(m=>m.type==='gz.start').length===2")
    assert park_queue.load('factory', root).items[0].status == 'failed'
    assert current(root).spec.template.endswith('--high')
    assert page.evaluate("testApp.bridge.logs.every(m=>!m.session_key?.startsWith('park-review-'))")
    assert not errors


@pytest.mark.parametrize('stage', ['design', 'review'])
def test_archive_commit_before_queue_commit_reconciles_on_reopen(park_browser, stage):
    page, errors, root, state = park_browser
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    opened(page)
    first = current(root)
    progress(page, 'running')
    progress(page, 'idle')
    page.wait_for_function("testApp.bridge.logs.some(m=>m.session_key?.startsWith('park-review-'))")
    if stage == 'review':
        opened(page)
        progress(page, 'running', review=True)
        page.locator('[data-action="park-pause"]').click()
        page.wait_for_function("document.querySelector('#park-queue-display').textContent.includes('已暂停')")
        progress(page, 'idle', review=True)
        page.wait_for_function("document.querySelector('#park-queue-display').textContent.includes('已结束')")
    saved = park_queue.load('factory', root).model_dump(mode='json')
    saved['items'][0].update(stage=stage, status='running')
    store.write(root / 'data/parks/factory/queue.json', saved)
    state['archive_visible'] = True
    page.goto('http://offline.test/#park')
    page.reload()
    page.locator('#park-map').wait_for()
    page.evaluate("""() => {
      const design={id:'offline-design',route:'offline'}, review={id:'agnes-3.0-flash',route:'offline'};
      testApp.bridge.models=[design,review];
      testApp.state.designModel=design;
      testApp.state.reviewModel=review;
    }""")
    page.locator('[data-paction="resume"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    key = page.evaluate("testApp.bridge.logs.find(m=>m.type==='gz.start').session_key")
    assert key == (first.review_session if stage == 'design' else current(root).design_session)
    assert key != first.design_session
    assert page.evaluate("testApp.bridge.logs.every(m=>m.type!=='gz.parkPrompt')")
    assert not errors


def test_unknown_dispatch_idle_cannot_acknowledge_cancel(park_browser):
    page, errors, root, state = park_browser
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    opened(page)
    first = current(root)
    page.locator('[data-action="park-skip"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.open')")
    page.evaluate("testApp.bridge.onMessage({type:'gz.progress',session_id:testApp.state.active,op:'idle',started:false,nodes:[]})")
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.cancel')")
    assert current(root).id == first.id and current(root).status == 'cancelling'
    assert not current(root).started and current(root).cancel_requested
    assert page.evaluate("testApp.bridge.logs.filter(m=>m.type==='gz.start').length") == 1
    progress(page, 'running')
    page.wait_for_function("testApp.bridge.logs.filter(m=>m.type==='gz.cancel').length===2")
    progress(page, 'idle')
    page.wait_for_function("testApp.bridge.logs.filter(m=>m.type==='gz.start').length===2")
    assert park_queue.load('factory', root).items[0].status == 'skipped'
    assert not errors


def test_archived_design_skip_opens_native_session_without_starting_review(park_browser):
    page, errors, root, state = park_browser
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    opened(page)
    progress(page, 'running')
    progress(page, 'idle')
    page.wait_for_function("testApp.bridge.logs.some(m=>m.session_key?.startsWith('park-review-'))")
    queue = park_queue.load('factory', root).model_dump(mode='json')
    queue['items'][0].update(stage='design', status='running')
    store.write(root / 'data/parks/factory/queue.json', queue)
    state['archive_visible'] = True
    page.goto('http://offline.test/#park')
    page.reload()
    page.locator('[data-paction="skip"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.open')")
    assert current(root).status == 'cancelling'
    assert page.evaluate("testApp.bridge.logs.every(m=>m.type!=='gz.start')")
    assert not errors


def test_shared_load_roundtrip_per_building_overrides_and_workspace_conflict(park_browser):
    page, errors, root, state = park_browser
    page.locator('[data-config="shared"]').click()
    page.locator('[data-field="text"]').fill('各栋按共享月用电条件设计')
    page.locator('[data-field="fKwh"]').fill('12')
    page.locator('[data-field="fShifts"]').select_option('2')
    assert page.locator('[data-field="fOwned"]').count() == 0
    assert page.get_by_text('以下作为每栋厂房的假设', exact=False).count() == 1
    page.locator('[data-action="park-settings-save"]').click()
    page.locator('#park-map').wait_for()
    page.locator('[data-config="shared"]').click()
    assert page.locator('[data-field="fKwh"]').input_value() == '12'
    assert page.locator('[data-field="fShifts"]').input_value() == '2'
    page.locator('[data-action="park-settings-save"]').click()
    page.locator('#park-map').wait_for()
    page.locator('[data-config="high"]').click()
    page.locator('[data-field="fKwh"]').fill('4')
    page.locator('[data-field="fAge"]').fill('0')
    page.locator('[data-field="fShifts"]').select_option('')
    page.locator('[data-field="fOwned"]').select_option('0')
    page.locator('[data-action="park-settings-save"]').click()
    page.locator('#park-map').wait_for()
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    rows = park_queue.load('factory', root).items
    assert rows[0].spec.facts.monthly_kwh == 120000 and rows[0].spec.facts.shifts == 2
    assert rows[1].spec.facts.monthly_kwh == 40000 and rows[1].spec.facts.owned is False
    assert rows[1].spec.facts.roof_age_years == 0 and rows[1].spec.facts.shifts is None
    opened(page)
    page.goto('http://offline.test/#park')
    page.reload()
    page.locator('#park-map').wait_for()
    page.evaluate("testApp.bridge.workspaceBinding='b'.repeat(64)")
    page.locator('[data-paction="resume"]').click()
    page.wait_for_function("document.body.textContent.includes('原工作区关联与当前连接不一致')")
    assert page.evaluate("testApp.bridge.logs.every(m=>!['gz.open','gz.start','gz.parkPrompt'].includes(m.type))")
    assert current(root).status == 'sending'
    assert not errors


def test_finished_design_workspace_conflict_holds_then_resumes_same_review(park_browser):
    page, errors, root, state = park_browser
    state['archive_visible'] = True
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    opened(page)
    first = current(root)
    progress(page, 'running')
    page.evaluate("testApp.bridge.workspaceBinding='b'.repeat(64)")
    progress(page, 'idle')
    page.wait_for_function("document.querySelector('#park-queue-display').textContent.includes('原工作区关联')")
    assert current(root).id == first.id and current(root).stage == 'design'
    assert current(root).status == 'running'
    assert page.evaluate("testApp.bridge.logs.filter(m=>m.type==='gz.start').length") == 1
    page.evaluate("testApp.bridge.workspaceBinding='a'.repeat(64)")
    page.locator('[data-action="park-resume"]').click()
    page.wait_for_function("testApp.bridge.logs.filter(m=>m.type==='gz.start').length===2")
    assert current(root).id == first.id and current(root).stage == 'review'
    assert page.evaluate("testApp.bridge.logs.filter(m=>m.type==='gz.start').at(-1).session_key") == first.review_session
    assert park_queue.load('factory', root).items[1].status == 'pending'
    assert not errors


def test_park_queue_leaves_the_agh_chat_reachable_and_its_divider_drags(park_browser):
    page, errors, root, state = park_browser
    page.set_viewport_size(dict(width=1536, height=842))  # the window the user tried this in
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    opened(page)
    page.evaluate("location.hash='#run'")
    page.wait_for_selector('.col > #park-queue-display')  # the queue shares the steps column, not the chat's height
    height = lambda selector: page.locator(selector).bounding_box()['height']
    rects = lambda: page.evaluate("['iframe-slot', 'agh-dock'].map(id => {const r = document.getElementById(id).getBoundingClientRect();"
                                  " return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];})")
    assert height('.col > #park-queue-display') == pytest.approx(240, abs=1) and height('#iframe-slot') >= 400
    handle = page.locator('.splitter[data-split="queue"]').bounding_box()
    x, y = handle['x'] + handle['width'] / 2, handle['y'] + handle['height'] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y - 60, steps=4)
    page.mouse.up()
    assert height('.col > #park-queue-display') == pytest.approx(300, abs=2)
    page.mouse.move(x, y - 60)
    page.mouse.down()
    page.mouse.move(x, y - 700, steps=6)  # the steps above always keep some room
    page.mouse.up()
    assert height('.col > .steps') >= 119 and page.evaluate("JSON.parse(localStorage.getItem('gz-split')).queue") > 300
    column = page.locator('.splitter[data-split="run"]').bounding_box()
    page.mouse.move(column['x'] + column['width'] / 2, column['y'] + 200)
    page.mouse.down()
    page.mouse.move(column['x'] + column['width'] / 2 + 100, column['y'] + 200, steps=4)  # a wider steps and queue column
    page.mouse.up()
    slot, dock = rects()
    assert slot == dock and page.locator('.run-grid > .col').first.bounding_box()['width'] == pytest.approx(500, abs=2)
    page.locator('.splitter[data-split="queue"]').dblclick()
    page.locator('.splitter[data-split="run"]').dblclick()
    assert height('.col > #park-queue-display') == pytest.approx(240, abs=1) and page.evaluate("localStorage.getItem('gz-split')") == '{}'
    assert not errors


def test_a_batch_stuck_after_an_upgrade_can_be_abandoned_and_started_again(park_browser):
    page, errors, root, state = park_browser
    page.locator('[data-paction="start"]').click()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.start')")
    opened(page)
    page.goto('http://offline.test/#park')
    page.reload()
    page.locator('#park-map').wait_for()
    page.evaluate("testApp.bridge.workspaceBinding='b'.repeat(64)")  # what an old build's binding looked like after an upgrade
    page.locator('[data-paction="resume"]').click()
    page.wait_for_function("document.body.textContent.includes('放弃这个队列')")
    sent = "testApp.bridge.logs.filter(m=>['gz.start','gz.open','gz.parkPrompt'].includes(m.type)).length"
    assert page.evaluate(sent) == 0  # since the reload: the mismatch dispatches nothing
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('[data-action="park-abandon"]').click()
    page.wait_for_function("document.body.textContent.includes('队列已放弃')")
    assert [item.status for item in park_queue.load('factory', root).items] == ['skipped', 'skipped']
    assert page.evaluate(sent) == 0  # abandoning sends nothing either
    page.locator('#park-map').wait_for()
    page.evaluate("""() => {
      const d={id:'offline-design',route:'offline'}, r={id:'agnes-3.0-flash',route:'offline'};
      Object.assign(testApp.bridge, {models:[d,r]});
      Object.assign(testApp.state, {designModel:d, reviewModel:r});
    }""")
    page.locator('[data-paction="start"]').click()  # a fresh batch on the current connection
    page.wait_for_function("testApp.bridge.logs.filter(m=>m.type==='gz.start').length===1")
    assert current(root).workspace_binding == 'b' * 64 and current(root).status in ('creating', 'sending')
    assert not errors


def test_an_unreadable_park_says_so_on_the_page_and_can_be_retried(park_browser):
    page, errors, root, _ = park_browser
    broken = dict(on=True)

    def parks(route):
        if broken['on']:
            return route.fulfill(status=400, json=dict(errors=['输入编号、文件或数据格式不正确']))
        route.fallback()
    page.route('**/api/parks', parks)
    page.evaluate("location.hash = '#records'")
    page.wait_for_function("!document.getElementById('park-map')")
    page.evaluate("location.hash = '#park'")  # used to leave the previous page in place with only a toast
    page.wait_for_function("document.querySelector('.page').textContent.includes('园区没能打开：输入编号、文件或数据格式不正确')")
    broken['on'] = False
    page.locator('[data-action="result-retry"]').click()
    page.locator('#park-map').wait_for()
    assert not errors


def test_the_home_list_does_not_repeat_a_parks_buildings(park_browser):
    page, errors, root, _ = park_browser
    page.reload()  # load the roof list from the park workspace, not the page's first offline list
    page.wait_for_function("Boolean(window.testApp)")
    page.evaluate("location.hash = '#new'")
    page.wait_for_function("document.querySelectorAll('.roofrow').length >= 2")
    shown = page.evaluate("[...document.querySelectorAll('.roofrow')].map(b => b.dataset.roof)")
    assert {'low', 'high'} <= set(shown) and not [roof for roof in shown if '--' in roof], shown  # the park's copies stay on the park page
    assert not errors
