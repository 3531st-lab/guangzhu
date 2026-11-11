"""Full production ESM/Three.js/bridge startup and repaired user flows in isolated data.

Browser plugin is not available in this environment; uses installed Playwright Edge.
No app source/import rewriting, scene stubs, real project writes, or model calls.
"""
import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from shapely.geometry import Polygon

from guangzhu import api, layout, project as storage
from guangzhu.config import API_ORIGIN, DATA_DIR, ROOT
from guangzhu.models import Roof

WEB = ROOT / 'desktop/web'


@pytest.fixture
def full_app(tmp_path, monkeypatch):
    shutil.copytree(DATA_DIR / 'demo/projects/changzhou-demo',tmp_path / 'data/demo/projects/changzhou-demo')
    for target in ('guangzhu.api.ROOT','guangzhu.brief.ROOT'):
        monkeypatch.setattr(target,tmp_path)
    monkeypatch.setattr(storage,'PROJECTS_DIR',tmp_path/'projects')
    monkeypatch.setattr(api,'tilt_hint',lambda payload:dict(available=False,hint='隔离测试未计算倾角'))
    data=json.loads((DATA_DIR/'demo/projects/changzhou-demo/project.json').read_text('utf-8'))
    data.update(id='browser-rule-case',designs=[])
    data['roof'].update(outline=[[0,0],[24,0],[24,16],[0,16]],obstacles=[],keepouts=[],surroundings=[])
    record=storage.save(data)
    storage.save_design(record.id,layout.generate_layout(record,{}),offline=True)
    result=api.result_data(record.id,1)
    result['metrics']=result['summary']=dict(dc_kw=100,modules=len(result['design']['modules']),yield_kwh=dict(p50=7800))
    result['scene']['shading']=dict(version=1,summary=dict(avg_loss_pct=80),modules=[])
    result['scene']['electrical']=dict(version=1,strings=[],inverters=[],per_inverter=[],dc_drop_pct_max=0,ac_drop_pct_max=2.88)
    result['economics']=dict(self_use=dict(algorithm='按用电逐时算',effective_ratio=.5,ratio=.5,weighted_price_cny_kwh=.85,
        monthly=[dict(month=i,generation_kwh=i*100,
        self_use_kwh=i*50,export_kwh=i*40,curtailed_kwh=i*10) for i in range(1,13)]))
    result['rules']=dict(hard_failed=0,items=[])
    state=dict(result=result,approval_error=False,approved=False,requests=[],errors=[],console=[],loaded_scripts=[])
    with TestClient(api.app,base_url=API_ORIGIN,headers={'origin':API_ORIGIN}) as backend, sync_playwright() as browser_api:
        browser=browser_api.chromium.launch(channel='msedge',headless=True,args=['--enable-unsafe-swiftshader'])
        page=browser.new_page(viewport=dict(width=1440,height=1000))
        page.set_default_timeout(30000)
        page.on('pageerror',lambda error:state['errors'].append(str(error)))
        page.on('console',lambda message:state['console'].append(dict(type=message.type,text=message.text))
            if message.type in ('warning','error') else None)

        def respond(route):
            request=route.request; url=urlsplit(request.url); path=url.path
            if url.hostname!='localhost':
                route.abort();return
            if path.startswith('/api/'):
                body=request.post_data_json if request.post_data else None
                state['requests'].append((path,body))
                if path=='/api/status': route.fulfill(json=dict(agh=dict(connected=False)));return
                if path=='/api/setup/status':
                    route.fulfill(json=dict(installation=dict(installed=True,id='a'*64),required=True,ready=False,
                        phase='waiting_models',steps=[dict(id='model',status='pending',name='需要模型配置')]));return
                if path=='/api/runs': route.fulfill(json=dict(runs=[]));return
                if path=='/api/projects/local-list': route.fulfill(json=dict(projects=[]));return
                if path=='/api/projects/auto-run':
                    route.fulfill(json=dict(project_id=record.id,final_version=1,hard_failed=0,exported=False,export_status='awaiting_approval'));return
                if path==f'/api/projects/{record.id}/result': route.fulfill(json=state['result']);return
                if path.endswith('/exports/preview'):
                    route.fulfill(json=dict(project_id=record.id,version=1,ready=True,approval_id='single-use-ticket',
                        summary=dict(modules=10,dc_kw=5.5),checks=dict(hard_failed=0,failed_ids=[]),
                        review=dict(status='unverified'),notice='请核对本版本后批准。',files=['layout-v1.dxf','bom-v1.xlsx']));return
                if path.endswith('/exports/approve'):
                    if state['approval_error']:
                        route.fulfill(status=409,json=dict(detail='输入已改变，请重新预检查'))
                    else:
                        state['approved']=True;route.fulfill(json=dict(ok=True,version=1,files=['layout-v1.dxf','bom-v1.xlsx']))
                    return
                if '/download/' in path:
                    if state['approved']: route.fulfill(body=b'approved fixture file',content_type='application/octet-stream')
                    else: route.fulfill(status=409,json=dict(detail='请先预检查并批准导出'))
                    return
                reply=backend.request(request.method,path+('?' + url.query if url.query else ''),content=request.post_data_buffer,
                    headers={'content-type':request.headers.get('content-type','application/json')})
                route.fulfill(status=reply.status_code,body=reply.content,content_type=reply.headers.get('content-type'));return
            file=WEB/('index.html' if path=='/' else path.lstrip('/'))
            if file.is_file():
                if file.suffix=='.js': state['loaded_scripts'].append(file.name)
                route.fulfill(path=str(file))
            else: route.abort()

        page.route('**/*',respond)
        page.goto('http://localhost/#new')
        page.locator('[data-roof="changzhou-demo"]').wait_for()
        try:
            yield page,state,tmp_path
        finally:
            (tmp_path/'browser-state.json').write_text(json.dumps(dict(errors=state['errors'],console=state['console'],url=page.url,
                text=page.locator('body').inner_text(),notice=page.locator('#notice').text_content(),requests=state['requests']),ensure_ascii=False,indent=2),encoding='utf-8')
            page.screenshot(path=str(tmp_path/'browser-final.png'))
            browser.close()


def test_entire_app_starts_without_model_key_and_export_needs_explicit_version_approval(full_app):
    page,state,tmp=full_app
    assert page.title()=='光筑' and page.locator('.new-grid').is_visible()
    assert {'app.js','roofedit.js','scene.js','bridge.js','engineering-charts.js'} <= set(state['loaded_scripts'])
    page.locator('[data-action="quick-run"]').click()
    page.locator('[data-result-tab="文件"]').wait_for()
    page.locator('[data-result-tab="文件"]').click()
    page.locator('[data-action="preview-export"]').first.wait_for()
    posted=next(body for path,body in state['requests'] if path=='/api/projects/auto-run')
    assert posted['overwrite_existing'] is False and posted['review'] is False
    assert not any(path.endswith('/exports/approve') for path,_ in state['requests'])
    assert page.locator('#scene canvas').count()==1
    page.locator('[data-action="preview-export"]').first.click()
    page.locator('[data-action="approve-export"]').wait_for()
    assert '尚未独立审核' in page.locator('#local-export-panel').inner_text()
    assert not state['approved']
    state['approval_error']=True
    page.locator('[data-action="approve-export"]').click()
    page.get_by_text('输入已改变，请重新预检查',exact=True).wait_for()
    assert page.locator('[data-action="approve-export"]').count()==0 and not state['approved']
    state['approval_error']=False
    page.locator('#local-export-panel [data-action="preview-export"]').click()
    page.locator('[data-action="approve-export"]').click()
    page.get_by_role('heading',name='v1 已确认导出').wait_for()
    assert state['approved']
    assert 'v1 · 已批准导出' in page.locator('.head > div > p').inner_text()
    approvals=[body for path,body in state['requests'] if path.endswith('/exports/approve')]
    assert all(body==dict(version=1,approval_id='single-use-ticket',confirmed=True) for body in approvals)
    with page.expect_download() as downloaded:
        page.locator('#local-export-panel [data-action="download-dxf"]').click()
    assert downloaded.value.suggested_filename.endswith('-layout-v1.dxf')
    page.screenshot(path=str(tmp/'full-app-approved.png'))
    assert not state['errors']


def test_full_result_shows_real_loss_and_months_and_explicit_missing_state(full_app):
    page,state,tmp=full_app
    page.goto('http://localhost/#result/browser-rule-case?version=1')
    page.locator('[data-fold="losses"]').wait_for()
    page.locator('[data-fold="monthly"]').wait_for()
    assert page.locator('[data-loss-metric="年度平均遮挡损失"]').inner_text()=='80%'
    assert page.locator('[data-loss-metric="直流最大线路电压降"]').inner_text()=='0%'
    assert '12月弃电 120 kWh' in page.locator('.monthly-svg').text_content()
    assert 'PVsyst' not in page.locator('#view').inner_text()
    page.locator('[data-fold="monthly"]').scroll_into_view_if_needed()
    page.screenshot(path=str(tmp/'full-app-months.png'))
    state['result']['economics']={}
    page.reload()
    page.locator('[data-fold="monthly"]').wait_for()
    assert '未保存逐月计算结果' in page.locator('[data-energy-unavailable]').inner_text()
    assert not state['errors']


def test_full_park_route_creates_isolated_park_and_adds_roof(full_app):
    page,state,tmp=full_app
    page.locator('.navtabs a[href="#park"]').click()
    page.locator('[data-paction="new"]').wait_for()
    page.once('dialog',lambda dialog:dialog.accept('隔离园区浏览器验收'))
    page.locator('[data-paction="new"]').click()
    page.locator('[data-pfield="name"]').wait_for()
    assert page.locator('[data-pfield="name"]').input_value()=='隔离园区浏览器验收'
    page.locator('[data-source]').select_option('changzhou-demo')
    page.locator('[data-paction="add"]').click()
    page.locator('[data-pick="changzhou-demo"]').wait_for()
    assert '尚无可核验结果' in page.locator('.park-editor').inner_text()
    assert page.locator('[data-paction="auto-run"]').is_enabled()
    assert list((tmp/'data/parks').glob('*/park.json'))
    page.screenshot(path=str(tmp/'full-app-park.png'))
    assert not state['errors']


@pytest.mark.parametrize('shape,turn',[('l',0),('u',0),('t',37)])
def test_full_editor_concave_corridor_save_and_reopen(full_app,shape,turn):
    page,state,tmp=full_app
    page.locator('a[href="#roof"]').click()
    page.locator('[data-re-rect="w"]').fill('60')
    page.locator('[data-re-rect="d"]').fill('36')
    page.locator('[data-re-rect="turn"]').fill(str(turn))
    page.locator(f'[data-re-act="shape-{shape}"]').click()
    page.locator('[data-re-act="cad-walkway-cross"]').first.click()
    page.wait_for_function("document.querySelectorAll('.re-item').length>0")
    page.locator('[data-re="name"]').fill(f'隔离浏览器{shape}型通道')
    page.locator('[data-re-act="save"]').click()
    page.wait_for_url('**/#new')
    files=list((tmp/'data/my-roofs').glob('*/project.json'))
    assert len(files)==1
    saved=json.loads(files[0].read_text('utf-8'))
    validated=Roof.model_validate(saved['roof']);outline=Polygon(validated.outline)
    assert validated.keepouts and all(outline.covers(Polygon(row.polygon)) for row in validated.keepouts)
    page.goto(f'http://localhost/#roof/{files[0].parent.name}')
    page.locator('[data-re="name"]').wait_for()
    assert page.locator('.re-item').count()==len(validated.keepouts)
    assert not state['errors']


def test_full_innovation_lab_route_tabs_env_toggle_and_satmap_handoff(full_app):
    page,state,tmp=full_app
    page.locator('.navtabs a[href="#lab"]').click()
    page.locator('[data-lab-tab="pareto"]').wait_for()
    assert page.locator('[data-lab-tab]').count()==3
    page.locator('[data-lab-tab="bess-carbon"]').click()
    page.locator('[data-lab-env-mode="ccer"]').wait_for()
    gec_text=page.locator('#view').inner_text()
    page.locator('[data-lab-env-mode="ccer"]').click()
    ccer_text=page.locator('#view').inner_text()
    assert gec_text!=ccer_text
    page.locator('[data-lab-tab="benchmark"]').click()
    page.locator('[data-lab-load-case="TZ-01"]').first.wait_for()
    bench_text=page.locator('#view').inner_text()
    assert '某厂' not in bench_text
    assert '5.12%' in bench_text and '0.7%' in bench_text
    page.locator('[data-lab-load-case="TZ-01"]').first.click()
    page.wait_for_url('**/#satmap')
    page.locator('.satmap-shell').wait_for()
    page.screenshot(path=str(tmp/'full-app-lab-to-satmap.png'))
    assert not state['errors']

