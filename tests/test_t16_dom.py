"""Actual browser DOM and app handlers; every request is intercepted offline."""
import json
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "desktop/web"


@pytest.fixture
def browser_app(request):
    script = (WEB / "app.js").read_text(encoding="utf-8")
    script += "\nwindow.testApp={state,bridge,setup,checkConnection,render,updateRun,activeComputed,start,finishSession};"
    fake_bridge = """
    export function setAghOrigin() {}
    export class Bridge {
      constructor(frame,onMessage) {this.onMessage=onMessage; this.ready=true; this.models=[]; this.logs=[]; this.frame=frame;}
      setAvailable() {} setTheme() {}
      send(type,payload,request) {this.logs.push({type,...payload,request});}
    }
    """
    project = json.loads((ROOT / "data/demo/projects/changzhou-demo/project.json").read_text(encoding="utf-8"))
    delayed = []
    roof = dict(id="changzhou-demo", name=project["name"], geometry=project["roof"], project=project,
                defaults=dict(capex_cny_per_w=3.71, price_export_cny_kwh=.456), area_m2=2000, dimensions_m=[60, 50])
    responses = {"/api/roofs": {"roofs": [roof]}, "/api/runs": {"runs": []},
                 "/api/setup/status": {"installation": {"installed": False, "id": "development"}, "required": False, "ready": True, "steps": []},
                 "/api/status": {"agh": {"connected": False}}, "/api/brief": {"brief": "offline-brief", "errors": []},
                 "/api/runs/finish": {"run_id": "offline-run", "verification": {"passed": False, "checks": []},
                                      "result": {"version": 1, "selected_version": None}}}
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport=dict(width=1440, height=900))
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def respond(route):
            path = route.request.url.split("offline.test", 1)[-1].split("?", 1)[0]
            if path in responses:
                delayed.append(route) if path == "/api/runs" and getattr(request, "param", None) == "slow" else route.fulfill(
                    json=responses[path])
            elif path.startswith("/api/projects/") and path.endswith("/exists"):
                route.fulfill(json={"exists": False})
            elif path == "/app.js":
                route.fulfill(body=script, content_type="text/javascript")
            elif path == "/bridge.js":
                route.fulfill(body=fake_bridge, content_type="text/javascript")
            elif path == "/scene.js":
                route.fulfill(body="export const createScene = () => ({dispose(){},setData(){},setTheme(){},setSun(){},setMode(){},selectString(){},resetView(){}});",
                              content_type="text/javascript")
            elif path.startswith("/vendor/"):
                route.fulfill(body="", content_type="text/javascript")
            else:
                file = WEB / ("index.html" if path == "/" else path.lstrip("/"))
                if file.is_file():
                    route.fulfill(path=str(file))
                else:
                    route.abort()

        page.route("**/*", respond)
        page.goto("http://offline.test/#new" if getattr(request, "param", None) == "slow" else "http://offline.test/#run",
                  wait_until="commit")
        if getattr(request, "param", None) != "slow":
            page.wait_for_function("Boolean(window.testApp)")
        yield (page, errors, delayed) if getattr(request, "param", None) == "slow" else (page, errors)
        browser.close()


@pytest.mark.parametrize("browser_app", ["slow"], indirect=True)
def test_slow_startup_records_do_not_block_roof_or_replace_form(browser_app):
    page, errors, delayed = browser_app
    page.locator('[data-roof="changzhou-demo"]').wait_for(timeout=1000)
    page.locator('a[href="#form"]').click()
    page.locator('[data-field="text"]').wait_for()
    delayed[0].fulfill(json={"runs": [dict(run_id="late-record", project_id="late-project")]})
    page.wait_for_function("testApp.state.records.length===1")
    assert page.locator('[data-field="text"]').count() == 1 and errors == []


@pytest.mark.parametrize("invalid", ["我的厂房 A", "factory A", "", "_factory"])
def test_invalid_custom_project_id_can_leave_and_return_to_form(browser_app, invalid):
    page, errors = browser_app
    requests = []

    def exists(route):
        from urllib.parse import unquote
        import re
        value = unquote(route.request.url.split("/projects/", 1)[1].rsplit("/exists", 1)[0])
        requests.append(value)
        valid = re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value)
        route.fulfill(status=200 if valid else 400, json={"exists": False} if valid else {"error": "编号不合法"})

    page.route("**/api/projects/*/exists", exists)
    page.wait_for_function("testApp.state.form.template==='changzhou-demo'")
    page.evaluate("location.hash='#form'")
    page.locator('[data-field="id"]').fill(invalid)
    page.evaluate("location.hash='#new'")
    page.locator('a[href="#form"]').click()
    page.locator('[data-field="text"]').wait_for(timeout=1500)
    current = page.locator('[data-field="id"]').input_value()
    assert current.startswith("changzhou-demo-") and current != invalid
    assert invalid not in requests and errors == []


def install_session(page, archive="runs/t10-impossible-004/timeline.json"):
    nodes = json.loads((ROOT / archive).read_text(encoding="utf-8"))["nodes"]
    page.evaluate("""nodes => {
      const a=testApp, s={id:'design-dom',project:'dom-project',nodes,approvals:[],op:'idle',run:{review:{enabled:true}}};
      a.state.sessions.set(s.id,s); a.state.design=a.state.active=s.id; a.updateRun();
    }""", nodes)


@pytest.mark.parametrize("width,height", [(1280, 720), (1440, 900)])
def test_reviewer_subitems_stay_in_step_content_and_preserve_dom(browser_app, width, height):
    page, errors = browser_app
    page.set_viewport_size(dict(width=width, height=height))
    install_session(page)
    page.evaluate("""() => {
      const a=testApp, s=a.state.sessions.get(a.state.design);
      s.run.review.mode='independent';
      const review={id:'review-dom',review:true,project:s.project,op:'running',run:s.run,approvals:[],nodes:[
        {kind:'tool',name:'gz_project_summary',status:'completed',result_json:{ok:true}}
      ]};
      a.state.sessions.set(review.id,review); s.reviewSession=review.id; a.state.active=review.id; a.updateRun();
    }""")
    step = page.locator('[data-step="9"]')
    assert step.locator(":scope > div.muted").count() == 0
    assert step.locator(":scope > div > div.muted").count() == 1
    assert "读项目：完成" in step.inner_text()
    step.scroll_into_view_if_needed()
    bounds = step.evaluate("""el => {
      const box=n=>{const b=n.getBoundingClientRect();return {x:b.x,y:b.y,right:b.right,bottom:b.bottom,width:b.width};};
      window.reviewStep=el; window.reviewTitle=el.querySelector('h4');
      return {step:box(el),title:box(window.reviewTitle),children:box(el.querySelector('.muted')),pill:box(el.querySelector('.pill'))};
    }""")
    assert bounds["title"]["width"] > 120
    assert bounds["title"]["x"] >= bounds["step"]["x"] and bounds["title"]["right"] <= bounds["pill"]["x"]
    assert bounds["children"]["y"] >= bounds["title"]["bottom"]
    assert bounds["children"]["right"] <= bounds["pill"]["x"]
    assert bounds["children"]["bottom"] <= bounds["step"]["bottom"]
    assert bounds["pill"]["right"] <= bounds["step"]["right"]
    step.locator("details").evaluate("el => el.open=true")
    details = step.locator("details").evaluate("el => {const b=el.getBoundingClientRect();return {right:b.right,bottom:b.bottom};}")
    children = step.locator("div.muted").bounding_box()
    assert details["right"] <= bounds["pill"]["x"] and details["bottom"] <= children["y"]
    page.evaluate("""() => {
      testApp.updateRun();
      if (window.reviewStep!==document.querySelector('[data-step="9"]')) throw Error('step replaced');
      if (window.reviewTitle!==window.reviewStep.querySelector('h4')) throw Error('title replaced');
    }""")
    assert step.locator("details").evaluate("el => el.open")
    assert page.locator(".steps [data-step]").count() == 10 and errors == []


def test_run_dom_survives_ten_seconds_messages_and_slow_checkpoint_click(browser_app):
    page, errors = browser_app
    install_session(page)
    page.evaluate("""() => {
      window.original={view:document.querySelector('#view'),page:document.querySelector('#view>.page'),
        steps:document.querySelector('.steps'),button:document.querySelector('[data-suggestion="0"]'),
        details:[document.querySelector('.steps details'),document.querySelector('.sugs+details')],iframe:document.querySelector('#agh')};
      original.steps.scrollTop=240; original.details.forEach(d=>d.open=true);
      window.scrollPosition=original.steps.scrollTop;
      window.updates=0;
      window.progressTimer=setInterval(()=>{
        const a=testApp,s=a.state.sessions.get(a.state.design);
        a.bridge.onMessage({type:'gz.progress',session_id:s.id,op:'idle',nodes:s.nodes}); updates++;
      },100);
    }""")
    started = time.monotonic()
    page.wait_for_timeout(10050)
    assert time.monotonic() - started >= 10
    identity = page.evaluate("""() => ({count:updates,scroll:original.steps.scrollTop,position:scrollPosition,
      stable:original.page===document.querySelector('#view>.page') && original.steps===document.querySelector('.steps') &&
      original.button===document.querySelector('[data-suggestion="0"]') && original.iframe===document.querySelector('#agh'),
      open:original.details.every(d=>d.open && d.isConnected)})""")
    assert identity["count"] >= 90 and identity["stable"] and identity["open"]
    assert identity["scroll"] == identity["position"] > 0
    button = page.locator('[data-suggestion="0"]')
    button.scroll_into_view_if_needed()
    box = button.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(650)
    assert page.evaluate("original.button===document.querySelector('[data-suggestion=\"0\"]')")
    page.mouse.up()
    page.wait_for_function("testApp.bridge.logs.some(m=>m.type==='gz.followup')")
    page.evaluate("clearInterval(progressTimer)")
    follows = page.evaluate("testApp.bridge.logs.filter(m=>m.type==='gz.followup')")
    assert len(follows) == 1 and follows[0]["session_id"] == "design-dom"
    assert follows[0]["text"].startswith("同意建议①：")
    assert errors == []


def test_countdown_changes_text_without_replacing_live_buttons_or_details(browser_app):
    page, errors = browser_app
    install_session(page, "runs/gz-t14-changzhou-004/timeline.json")
    page.evaluate("""() => {
      const a=testApp,s=a.state.sessions.get(a.state.design);
      s.op='running'; s.nodes=[]; s.approvals=[{tool:'gz_export',pending:true,received_at:Date.now()-1000}];
      a.state.runTab='产物'; a.updateRun();
      window.clock={count:document.querySelector('.count'),cancel:document.querySelector('[data-action="cancel"]')};
    }""")
    old = page.locator(".count").inner_text()
    page.wait_for_function("old => document.querySelector('.count').textContent !== old", arg=old, timeout=7000)
    assert page.locator(".count").inner_text() != old
    assert page.evaluate("clock.count===document.querySelector('.count') && clock.cancel===document.querySelector('[data-action=\"cancel\"]')")
    assert page.locator('[data-run-tab="live"]').get_attribute("aria-pressed") == "true"
    assert errors == []


def test_phrase_updates_inputs_keep_buttons_and_preserves_textarea_cursor(browser_app):
    page, errors = browser_app
    page.evaluate("location.hash='#form'")
    field = page.locator('[data-field="text"]')
    field.wait_for()
    page.locator('[data-field="payback"]').fill("9")
    field.fill("6年回本，留2米的检修道，别挡天窗，造价每瓦4元")
    field.evaluate("el=>{el.focus();el.setSelectionRange(6,6);}")
    page.evaluate("""() => {
      window.textInput=document.querySelector('[data-field="text"]');
      textInput.dispatchEvent(new Event('input',{bubbles:true}));
    }""")
    assert page.locator('[data-field="payback"]').input_value() == "9"
    assert page.locator('[data-field="walkway"]').input_value() == "2"
    assert page.locator('[data-field="capex"]').input_value() == "4"
    assert page.locator('[data-field="budget"]').input_value() == ""
    assert page.evaluate("textInput===document.querySelector('[data-field=\"text\"]') && textInput.selectionStart===6 && document.activeElement===textInput")
    assert "已有值优先" in page.locator("#recognized").inner_text()
    assert page.locator('[data-keep][aria-pressed="true"]').count() > 0
    assert page.locator('[data-field="priceExport"]').get_attribute("placeholder") == "0.456"
    assert page.locator('[data-field="priceExport"]').input_value() == ""
    assert errors == []

def test_version_product_uses_archived_run_and_version_for_data_scene_and_file_open(browser_app):
    page, errors = browser_app
    install_session(page)
    requests = []
    result = dict(project_id="dom-project", run_id="archive-run", version=4, selected_version=3,
                  scene={}, metrics={}, versions=[dict(version=3), dict(version=4)], files={})

    def archived(route):
        requests.append(dict(url=route.request.url, body=route.request.post_data_json))
        route.fulfill(json={"result": result} if "/runs/" in route.request.url else {"ok": True})

    page.route("**/api/runs/archive-run*", archived)
    page.route("**/api/open", archived)
    page.evaluate("""result => {
      const a=testApp,s=a.state.sessions.get(a.state.design);
      s.result=result; a.state.runTab='产物'; a.updateRun();
    }""", result)
    page.locator('[data-version="4"]').click()
    page.wait_for_url("**#result/dom-project?version=4&run=archive-run")
    page.wait_for_function("testApp.state.result?.version===4")
    assert requests[0]["url"].endswith("/api/runs/archive-run?version=4")
    assert "v4" in page.locator(".head p").inner_text()
    page.locator('[data-action="open-exports"]').click()
    page.wait_for_timeout(100)
    assert requests[-1]["body"] == dict(kind="export", session_id="design-dom", project_id="dom-project", version=4, run_id="archive-run")
    assert errors == []


def test_unexported_default_and_explicit_version_titles_follow_the_route(browser_app):
    page, errors = browser_app
    requests = []

    def unexported(route):
        url = route.request.url
        requests.append(url)
        version = int(url.split("version=", 1)[1]) if "version=" in url else 3
        result = dict(project_id="dom-project", run_id="archive-run", version=version, selected_version=None,
                      display_passed=True, scene={}, metrics={}, versions=[dict(version=1), dict(version=3)], files={})
        route.fulfill(json={"result": result} if "/runs/" in url else result)

    page.route("**/api/runs/archive-run*", unexported)
    page.route("**/api/projects/dom-project/result*", unexported)
    for prefix in ["#result/dom-project?run=archive-run", "#result/dom-project"]:
        page.evaluate("hash => {location.hash=hash;}", prefix)
        page.wait_for_function("testApp.state.result?.version===3 && !testApp.state.resultExplicit")
        assert "未导出·最后通过v3" in page.locator(".head p").inner_text()
        for version in [1, 3]:
            separator = "&" if "?" in prefix else "?"
            page.evaluate("hash => {location.hash=hash;}", f"{prefix}{separator}version={version}")
            page.wait_for_function(f"testApp.state.result?.version==={version} && testApp.state.resultExplicit")
            title = page.locator(".head p").inner_text()
            assert f"未导出·查看版本 v{version}" in title
            assert "最后通过" not in title and "最新" not in title
            assert page.locator('[data-action="open-exports"]').count() == 0
    assert len(requests) == 6
    assert errors == []


@pytest.mark.parametrize("archived", [False, True])
@pytest.mark.parametrize("passed", [False, True])
def test_default_result_history_click_uses_explicit_titles_and_keeps_archive_identity(browser_app, archived, passed):
    page, errors = browser_app
    requests = []

    def result_response(route):
        url = route.request.url
        requests.append(url)
        version = int(url.split("version=", 1)[1]) if "version=" in url else 3
        result = dict(project_id="dom-project", run_id="archive-run" if archived else None,
                      version=version, selected_version=None, display_passed=passed, scene={}, metrics={},
                      versions=[dict(version=1), dict(version=3)], files={})
        route.fulfill(json={"result": result} if archived else result)

    page.route("**/api/runs/archive-run*", result_response)
    page.route("**/api/projects/dom-project/result*", result_response)
    prefix = "#result/dom-project" + ("?run=archive-run" if archived else "")
    page.evaluate("hash => {location.hash=hash;}", prefix)
    page.wait_for_function("testApp.state.result?.version===3 && !testApp.state.resultExplicit")
    default_title = "未导出·最后通过v3" if passed else "未导出·最新v3"
    assert default_title in page.locator(".head p").inner_text()
    for version in [1, 3]:
        page.locator(f'.vchain [data-version="{version}"]').click()  # T21: the change list above it opens versions too
        page.wait_for_function(f"testApp.state.result?.version==={version}")
        title = page.locator(".head p").inner_text()
        assert f"未导出·查看版本 v{version}" in title
        assert "最后通过" not in title and "最新" not in title
        assert page.evaluate("testApp.state.resultExplicit")
        assert page.evaluate("testApp.state.resultRun") == ("archive-run" if archived else None)
        assert page.locator('[data-action="open-exports"]').count() == 0
    path = "/api/runs/archive-run" if archived else "/api/projects/dom-project/result"
    assert len(requests) == 3
    assert all(path in url for url in requests)
    assert requests[-2].endswith("?version=1") and requests[-1].endswith("?version=3")
    assert errors == []


def test_replay_step_nine_waits_for_formal_review_time_and_derived_tail_does_not_mutate_ledger(browser_app):
    page, errors = browser_app
    time0, time1, time2 = "2026-10-03T14:20:00Z", "2026-10-03T14:20:01Z", "2026-10-03T14:21:00Z"
    nodes = [dict(kind="text", session="design", seq=1, ts=time0, text="设计已导出"),
             dict(kind="tool", session="reviewer", name="gz_record_review", tool_use_id="save", seq=2, result_seq=3,
                  ts=time1, ended_at=time1, status="completed", args_json=dict(project_id="p", version=3),
                  result_json=dict(ok=True, pending=True, job_id="review-job", tool="gz_record_review")),
             dict(kind="tool", session="reviewer", name="gz_wait", tool_use_id="wait", seq=4, result_seq=5,
                  ts=time1, ended_at=time2, status="completed", args_json=dict(job_id="review-job"),
                  result_json=dict(ok=True, job_id="review-job", tool="gz_record_review", version=3, file="reviews/v3.json"))]
    result = dict(project_id="p", version=3, selected_version=3,
                  review_files={"v3.json": dict(version=3, findings=[], verdict="approve")})
    record = dict(run=dict(session="design", review_session_id="reviewer"), timeline=dict(nodes=nodes), result=result,
                  verification=dict(review=dict(passed=True, independent=[dict(passed=True, session="reviewer", versions=[3])])), usage={})
    before = json.dumps(record, sort_keys=True)
    page.route("**/api/runs/replay-proof", lambda route: route.fulfill(json=record))
    page.evaluate("location.hash='#replay/replay-proof'")
    page.locator("#replay-seek").wait_for()
    assert page.locator("#replay-seek").get_attribute("max") == "2"
    page.locator("#replay-seek").evaluate("el=>{el.value=1;el.dispatchEvent(new Event('input',{bubbles:true}));}")
    assert "完成（见审核会话）" not in page.locator("#replay-steps").inner_text()
    page.locator("#replay-seek").evaluate("el=>{el.value=2;el.dispatchEvent(new Event('input',{bubbles:true}));}")
    assert "完成（见审核会话）" in page.locator("#replay-steps").inner_text()
    assert "独立审核完成（见审核会话）" in page.locator("#replay-host").inner_text()
    assert "回放里程碑" in page.locator("#replay-host").inner_text()
    assert "记录 0" not in page.locator("#replay-host").inner_text()
    assert json.dumps(record, sort_keys=True) == before
    assert page.evaluate("testApp.state.replayRun.timeline.nodes.length") == 3
    assert errors == []
