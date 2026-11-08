"""A late preview must never replace another tab's saved result or leave stale plan geometry."""
import math

from test_t16_dom import browser_app  # noqa: F401
from test_design_edits_api import editable_project, edit_client  # noqa: F401
from guangzhu import project as storage


SCENE_RECORDER = '''
export function createScene(host,callbacks={}) {
  const initialView={projection:'perspective',position:[12,24,16],target:[10,0,10],zoom:1};
  const record={data:null,calls:[],disposed:false,callbacks,editing:null,editingCalls:[],highlight:null,focus:null,mode:null,
    focusCalls:[],view:structuredClone(initialView)};
  (window.editSceneRecords ??= []).push(record);
  const noop=()=>{};
  return {dispose(){record.disposed=true;},setData(value,options={}){
    record.data=structuredClone(value);
    record.calls.push(structuredClone(value));
    if (!options.preserveView) record.view=structuredClone(initialView);
  },setModuleEditing(value){record.editing=structuredClone(value);record.editingCalls.push(structuredClone(value));},
  setTheme:noop,setSun:noop,setMode(value){record.mode=value;},selectString:noop,resetView:noop,
  highlightModules(ids,locked){record.highlight={ids:[...ids],locked:[...locked]};},focusModules(ids){
    record.focus=[...ids];record.focusCalls.push([...ids]);
    const target=record.data?.design?.modules.find(module=>ids.includes(module.id))?.center ?? [0,0,0];
    record.view={...record.view,target:[...target],zoom:2};
  }};
}
'''


def geometry(design):
    return {module['id']: module['corners'] for module in design['modules']}


def assert_scene(page, expected):
    actual = page.evaluate('window.editSceneRecords.filter(record=>!record.disposed).at(-1).data.design')
    assert actual['version'] == expected['version']
    assert geometry(actual) == geometry(expected)


def assert_both_views(page, expected):
    assert_scene(page, expected)
    rows = page.locator('[data-edit-module]').evaluate_all(r'''elements => elements.map(element => ({
      id:element.dataset.editModule,
      corners:element.getAttribute('points').trim().split(/\s+/).map(pair=>pair.split(',').map(Number))
    }))''')
    assert len(rows) == len(expected['modules'])
    assert {row['id'] for row in rows} == set(geometry(expected))
    by_id = geometry(expected)
    for row in rows:
        for actual, wanted in zip(row['corners'], by_id[row['id']], strict=True):
            assert math.isclose(actual[0], wanted[0], abs_tol=1e-9)
            assert math.isclose(actual[1], -wanted[1], abs_tol=1e-9)


def test_late_reflow_stays_in_edit_tab_and_cancel_parameter_change_save_keep_views_consistent(
        browser_app, editable_project, edit_client):
    page, errors = browser_app
    project = editable_project
    pending, options = [], {'hold':True}
    original = storage.load_design(project.id, 1).model_dump(mode='json')
    page.route('**/scene.js', lambda route: route.fulfill(body=SCENE_RECORDER,content_type='text/javascript'))

    def forward(route):
        request = route.request
        response = edit_client.request(request.method,request.url.split('offline.test',1)[-1],
                                       content=request.post_data_buffer,headers={'content-type':'application/json'})
        if request.url.endswith('/design-edits/preview') and options['hold']:
            pending.append((route,response))
            page.evaluate('window.editPreviewHeld=true')
        else:
            route.fulfill(status=response.status_code,body=response.content,content_type='application/json')

    page.route(f'**/api/projects/{project.id}/**',forward)
    # Reload imports the recording scene instead of the fixture's generic scene stub.
    page.goto(f'http://offline.test/#result/{project.id}?version=1')
    page.reload()
    page.locator('[data-result-tab="局部修改"]').click()
    assert_both_views(page, original)
    page.locator('[data-edit-param="orientation"]').select_option('landscape')
    page.locator('[data-design-edit="reflow"]').click()
    page.wait_for_function('window.editPreviewHeld === true')
    assert pending and page.evaluate('testApp.state.editing.busy')
    page.locator('[data-result-tab="结论"]').click()
    assert_scene(page, original)
    before_calls = page.evaluate('window.editSceneRecords.at(-1).calls.length')
    route,response = pending.pop()
    assert response.status_code == 200, response.text
    route.fulfill(status=response.status_code,body=response.content,content_type='application/json')
    page.wait_for_function('testApp.state.editing.preview !== null && !testApp.state.editing.busy')
    assert page.evaluate('testApp.state.resultTab') == '结论'
    assert page.locator('.de-editor').count() == 0
    assert_scene(page, original)
    assert page.evaluate('window.editSceneRecords.at(-1).calls.length') == before_calls
    assert storage.next_version(project.id) == 2

    candidate = page.evaluate('testApp.state.editing.preview.design')
    assert geometry(candidate) != geometry(original)
    page.locator('[data-result-tab="局部修改"]').click()
    assert_both_views(page, candidate)
    page.locator('[data-design-edit="cancel"]').click()
    assert page.locator('.de-preview').count() == 0
    assert_both_views(page, original)

    options['hold'] = False
    page.locator('[data-design-edit="reflow"]').click()
    page.locator('.de-preview').wait_for()
    assert_both_views(page,page.evaluate('testApp.state.editing.preview.design'))
    page.locator('[data-edit-param="walkway_width_m"]').fill('1.2')
    assert page.locator('.de-preview').count() == 0
    assert page.locator('[data-edit-param="walkway_width_m"]').input_value() == '1.2'
    assert_both_views(page, original)

    page.locator('[data-design-edit="reflow"]').click()
    page.locator('.de-preview').wait_for()
    candidate = page.evaluate('testApp.state.editing.preview.design')
    assert_both_views(page, candidate)
    page.locator('[data-design-edit="apply"]').click()
    page.wait_for_function("testApp.state.result?.version === 2 && document.querySelector('.de-editor') && !testApp.state.editing.preview")
    saved = storage.load_design(project.id, 2).model_dump(mode='json')
    assert geometry(saved) == geometry(candidate)
    assert_both_views(page, saved)
    assert storage.next_version(project.id) == 3
    assert not errors
