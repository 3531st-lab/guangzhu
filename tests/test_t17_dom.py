"""Real app DOM with offline browser routes and synthetic comparison records."""
import pytest

from test_t16_dom import browser_app


def row(name, version, **changes):
    return dict(name=name, version=version, dc_kw=123.4, payback_years=4.02, irr_pct=15.3,
                hard_pass=True, violated_requirements=[], **changes)


def comparison():
    return dict(ok=True, base_version=3, current=row("当前方案", 3),
                options=[row("多装", 6), row("最快回本", 9), row("折中", 12)],
                recommended=dict(balanced=dict(version=3, why="当前方案年发电最多"),
                                 fast_payback=dict(version=9, why="回本最短")))


def tool(name, seq, value, args=None):
    return dict(kind="tool", name=name, seq=seq, result_seq=seq + 1, session="design-dom", tool_use_id=f"id-{seq}",
                status="completed", isError=False, args_json=args or {}, result_json=value)


VERSIONS = [dict(version=12, parent_version=11, reason="折中：自动修正 E08"),
            dict(version=11, parent_version=3, reason="折中：按 U03 删除 982 块", statistics=dict(module_count=1250)),
            dict(version=6, parent_version=5, reason="多装：自动修正 E08"),
            dict(version=5, parent_version=3, reason="多装：按 U02 删除 7 块", statistics=dict(module_count=400)),
            dict(version=3, parent_version=None, reason="多装：按 U03 删除 8 块", statistics=dict(module_count=1250))]


def progress(page, nodes):
    page.evaluate("""nodes => testApp.bridge.onMessage({type:'gz.progress',session_id:'design-dom',op:'running',nodes})""", nodes)


def live_session(page):
    page.evaluate("""() => {
      const a=testApp, s={id:'design-dom',project:'dom-project',nodes:[],approvals:[],op:'running',
        run:{prefer:'fast_payback',compare:true,review:{enabled:false},export:true}};
      a.state.sessions.set(s.id,s); a.state.design=a.state.active=s.id;
      a.state.form.id='unrelated-form-project'; a.state.form.prefer='balanced'; a.updateRun();
    }""")


def metadata():
    return dict(project_id="dom-project", version=12, selected_version=12, versions=VERSIONS)


@pytest.mark.parametrize("width,height", [(1280, 720), (1536, 834)])
def test_running_four_rows_current_first_and_actual_preference(browser_app, width, height):
    page, errors = browser_app
    page.set_viewport_size(dict(width=width, height=height))
    requests = []
    page.route("**/api/projects/dom-project/result?version=3", lambda route: (
        requests.append(route.request.url), route.fulfill(json=metadata())))
    live_session(page)
    nodes = [tool("gz_compare_options", 1, dict(ok=True, pending=True, job_id="J", tool="gz_compare_options"),
                  dict(project_id="dom-project", base_version=3))]
    progress(page, nodes)
    step = page.locator('[data-step="7"]')
    assert step.locator("tbody tr").count() == 0
    assert requests == []
    nodes += [tool("gz_wait", 3, dict(ok=True, pending=True, job_id="J", tool="gz_compare_options"), dict(job_id="J"))]
    progress(page, nodes)
    assert requests == [] and step.locator("tbody tr").count() == 0
    nodes += [tool("gz_wait", 5, dict(comparison(), job_id="J", tool="gz_compare_options"), dict(job_id="J"))]
    progress(page, nodes)
    page.wait_for_function("document.querySelector('[data-step=\"7\"]').textContent.includes('预算删板后1,250块')", timeout=1500)
    assert page.evaluate("testApp.state.sessions.get('design-dom').result === undefined")
    assert "选定" not in step.inner_text()
    assert "装机上限删板后400块" in step.inner_text()
    nodes += [tool("gz_analyze", 7, dict(ok=True, version=3, rules=dict(hard_failed=0)))]
    progress(page, nodes)
    page.evaluate("testApp.bridge.onMessage({type:'gz.approval',session_id:'design-dom',tool:'gz_export',pending:true})")
    assert step.locator("tbody tr").count() == 4
    assert step.locator("tbody tr").first.inner_text().startswith("当前方案 v3 选定")
    assert "最快回本 v9 推荐" in step.inner_text()
    assert "预算删板后1,250块" in step.inner_text()
    assert step.locator("tbody tr").first.locator("small").count() == 0
    step.locator("details").evaluate("el => el.open=true")
    assert "回本最短" in step.locator("details").inner_text()
    assert step.locator("th:visible").all_text_contents() == ["方案 / 要求", "排法", "装机 kW", "回本 年"]
    cells = [" ".join(value.split()) for value in step.locator("tbody tr").first.locator("td:visible").all_inner_texts()]
    assert len(cells) == 4 and cells[0].startswith("当前方案 v3 选定")
    assert cells[1:] == ["原排法", "123.4", "4.02"]
    bounds = step.locator('.table-scroll').evaluate("el=>({width:el.clientWidth,scroll:el.scrollWidth})")
    assert bounds["width"] >= 190 and bounds["scroll"] <= bounds["width"]
    assert "满足" in step.locator("tbody tr").first.locator("td").first.inner_text()
    assert "人工批准导出等你批准" in page.locator('.banner').inner_text()
    assert page.evaluate("testApp.state.sessions.get('design-dom').result === undefined")
    progress(page, nodes)
    page.wait_for_timeout(50)
    assert len(requests) == 1 and errors == []
    page.route("**/api/runs/finish", lambda route: route.fulfill(json=dict(
        verification=dict(passed=False, checks=[]), result=dict(selected_version=9, versions=[]))))
    page.evaluate("""nodes => testApp.bridge.onMessage({type:'gz.progress',session_id:'design-dom',op:'idle',nodes})""", nodes)
    page.evaluate("testApp.finishSession(testApp.state.sessions.get('design-dom'),true,false)")
    assert "最快回本 v9 选定" in step.inner_text() and "删除 982" not in step.inner_text()
    assert errors == []


@pytest.mark.parametrize("width,height", [(1280, 720), (1536, 834)])
def test_result_rows_marks_requirements_and_legacy(browser_app, width, height):
    page, errors = browser_app
    page.set_viewport_size(dict(width=width, height=height))
    compare = comparison()
    compare["options"][0]["violated_requirements"] = ["U03", "U02", "G03"]
    compare["options"][1]["hard_pass"] = False
    result = dict(project_id="dom-project", version=12, selected_version=12, compare=compare, versions=VERSIONS,
                  run=dict(prefer="balanced"), scene={})
    page.route("**/api/projects/dom-project/result", lambda route: route.fulfill(json=result))
    page.evaluate("testApp.state.resultTab='三方案'; location.hash='#result/dom-project'")
    page.locator("#result-panel tbody tr").first.wait_for()
    panel = page.locator("#result-panel")
    assert panel.locator("tbody tr").count() == 4
    assert panel.inner_text().count("选定") == 1 and panel.inner_text().count("推荐") == 1
    for phrase in ["超预算", "装机超上限", "通道不够", "硬性规则未过", "预算删板后1,250块"]:
        assert phrase in panel.inner_text()
    bounds = panel.locator('.table-scroll').evaluate("el=>({width:el.clientWidth,scroll:el.scrollWidth})")
    assert bounds["scroll"] <= bounds["width"]
    assert panel.locator("tbody tr").first.locator("small").count() == 0
    compare.pop("current")
    compare.pop("recommended")
    page.evaluate("testApp.render()")
    page.wait_for_function("document.querySelectorAll('#result-panel tbody tr').length===3")
    assert "当前方案" not in panel.inner_text()
    assert errors == []


@pytest.mark.parametrize("missing_base", [False, True])
def test_legacy_comparison_never_inherits_parent_budget_reason(browser_app, missing_base):
    page, errors = browser_app
    compare = comparison()
    compare.pop("current")
    if missing_base:
        compare.pop("base_version")
    versions = [dict(version=6, parent_version=3, reason="多装"),
                dict(version=3, parent_version=2, reason="E08,S01,U03", statistics=dict(module_count=1250)),
                dict(version=2, parent_version=3, reason="初稿")]
    result = dict(project_id="dom-project", version=12, selected_version=12, compare=compare, versions=versions, scene={})
    page.route("**/api/projects/dom-project/result", lambda route: route.fulfill(json=result))
    page.evaluate("testApp.state.resultTab='三方案'; location.hash='#result/dom-project'")
    page.locator("#result-panel tbody tr").first.wait_for()
    assert page.locator("#result-panel tbody small").count() == 0 and errors == []  # header units are <small>; rows carry no inherited reason


@pytest.mark.parametrize("width", [1280, 1536])
@pytest.mark.parametrize("surface", ["live", "result"])
def test_requirement_text_fits_actual_comparison_view_without_horizontal_scroll(browser_app, width, surface):
    page, errors = browser_app
    page.set_viewport_size(dict(width=width, height=834))
    compare = comparison()
    compare['options'][0]['violated_requirements'] = ['U03', 'U02', 'G03']
    if surface == 'live':
        page.route("**/api/projects/dom-project/result?version=3", lambda route: route.fulfill(json={'versions': []}))
        live_session(page)
        progress(page, [tool("gz_compare_options", 1, compare, dict(project_id="dom-project", base_version=3))])
        table = page.locator('[data-step="7"] .table-scroll')
    else:
        result = dict(project_id="dom-project", version=12, compare=compare, versions=[], scene={})
        page.route("**/api/projects/dom-project/result", lambda route: route.fulfill(json=result))
        page.evaluate("testApp.state.resultTab='三方案'; location.hash='#result/dom-project'")
        table = page.locator('#result-panel .table-scroll')
    table.locator('tbody tr').first.wait_for()
    bounds = table.evaluate("""el => {
      const container=el.getBoundingClientRect();
      const cells=[...el.querySelectorAll('tbody td')].map(cell=>{
        const text=document.createRange(); text.selectNodeContents(cell);
        return [...text.getClientRects()].every(r=>r.left>=container.left && r.right<=container.right);
      });
      return {width:el.clientWidth,scroll:el.scrollWidth,readable:cells.every(Boolean)};
    }""")
    assert bounds['scroll'] <= bounds['width'] and bounds['readable']
    assert '满足' in table.inner_text() and '超预算' in table.inner_text()
    assert errors == []


@pytest.mark.parametrize("superseded", ["session", "design", "project", "generation", "comparison"])
def test_late_metadata_is_ignored(browser_app, superseded):
    page, errors = browser_app
    delayed = []
    page.route("**/api/projects/dom-project/result?version=3", lambda route: delayed.append(route))
    live_session(page)
    nodes = [tool("gz_compare_options", 1, comparison(), dict(project_id="dom-project", base_version=3))]
    progress(page, nodes)
    page.wait_for_function("testApp.state.sessions.get('design-dom').compareKey != null", timeout=1500)
    page.wait_for_timeout(30)
    assert len(delayed) == 1
    if superseded == "comparison":
        nodes += [tool("gz_compare_options", 3, dict(ok=True, pending=True, job_id="next", tool="gz_compare_options"),
                       dict(project_id="dom-project", base_version=3))]
        progress(page, nodes)
    else:
        page.evaluate("""kind => {
          const a=testApp,s=a.state.sessions.get('design-dom');
          if(kind==='project') s.project='other-project';
          if(kind==='generation') s.generation=1;
          if(kind==='session') a.state.sessions.set(s.id,{...s,compareVersions:null});
          if(kind==='design') a.state.design='next-design';
        }""", superseded)
    delayed[0].fulfill(json=metadata())
    page.wait_for_timeout(80)
    assert not page.evaluate("Boolean(testApp.state.sessions.get('design-dom').compareVersions)")
    assert "删除 982" not in page.locator('[data-step="7"]').inner_text()
    assert errors == []


def test_failed_metadata_request_does_not_block_design_or_retry_forever(browser_app):
    page, errors = browser_app
    requests = []
    page.route("**/api/projects/dom-project/result?version=3", lambda route: (
        requests.append(route.request.url), route.fulfill(status=503, json=dict(error="offline metadata"))))
    live_session(page)
    nodes = [tool("gz_compare_options", 1, comparison(), dict(project_id="dom-project", base_version=3))]
    progress(page, nodes)
    page.wait_for_function("testApp.state.sessions.get('design-dom').compareKey != null", timeout=1500)
    page.wait_for_timeout(80)
    nodes += [tool("gz_analyze", 3, dict(ok=True, version=9, rules=dict(hard_failed=0)))]
    progress(page, nodes)
    progress(page, nodes)
    page.wait_for_timeout(80)
    step = page.locator('[data-step="7"]')
    assert step.locator("tbody tr").count() == 4 and "最快回本 v9 选定" in step.inner_text()
    assert "删除 982" not in step.inner_text() and len(requests) == 1
    assert page.evaluate("testApp.state.sessions.get('design-dom').op === 'running'") and errors == []


def test_compare_false_uses_existing_skipped_dom(browser_app):
    page, errors = browser_app
    page.evaluate("""() => {
      const a=testApp, s={id:'design-dom',project:'dom-project',nodes:[],approvals:[],op:'running',
        run:{compare:false,review:{enabled:false},export:false}};
      a.state.sessions.set(s.id,s); a.state.design=a.state.active=s.id; a.updateRun();
    }""")
    step = page.locator('[data-step="7"]')
    assert "跳过" in step.inner_text() and step.locator("tbody tr").count() == 0
    assert errors == []
