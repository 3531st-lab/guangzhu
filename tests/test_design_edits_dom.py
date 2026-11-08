"""Real browser + HTTP: choose, preview, confirm, reflow, cancel and stale guards."""
from test_t16_dom import browser_app  # noqa: F401
from test_design_edits_api import editable_project, edit_client  # noqa: F401
from guangzhu import project as storage


def test_select_lock_reflow_cancel_and_stale_preview(browser_app, editable_project, edit_client, tmp_path):
    page, errors = browser_app
    project = editable_project
    def forward(route):
        request = route.request
        response = edit_client.request(request.method, request.url.split('offline.test',1)[-1],
                                       content=request.post_data_buffer,
                                       headers={'content-type':'application/json'})
        route.fulfill(status=response.status_code, body=response.content, content_type='application/json')
    page.route(f'**/api/projects/{project.id}/**', forward)
    page.goto(f'http://offline.test/#result/{project.id}?version=1')
    page.locator('[data-result-tab="局部修改"]').click()
    first = storage.load_design(project.id,1).modules[0].id
    page.locator(f'[data-edit-module="{first}"]').click()
    page.locator('[data-design-edit="lock"]').click()
    page.locator('.de-preview').wait_for()
    assert storage.next_version(project.id) == 2
    assert '尚未保存' in page.locator('.de-preview').inner_text()
    page.locator('[data-design-edit="apply"]').click()
    page.wait_for_function("testApp.state.result?.version === 2 && document.querySelector('.de-editor')")
    assert storage.load_design(project.id,2).locked_module_ids == [first]
    page.locator('[data-edit-param="orientation"]').select_option('landscape')
    page.locator('[data-design-edit="reflow"]').click()
    page.locator('.de-preview').wait_for()
    assert storage.next_version(project.id) == 3
    preview = page.evaluate('testApp.state.editing.preview.design')
    assert next(m for m in preview['modules'] if m['id'] == first)['corners'] == [list(c) for c in storage.load_design(project.id,2).modules[0].corners]
    page.screenshot(path=str(tmp_path/'partial-reflow-preview.png'))
    page.locator('[data-design-edit="cancel"]').click()
    assert page.locator('.de-preview').count() == 0
    assert storage.next_version(project.id) == 3
    page.locator('[data-design-edit="reflow"]').click()
    page.locator('.de-preview').wait_for()
    # Editing a field invalidates both views; selectable IDs must revert to the saved design.
    page.locator('[data-edit-param="walkway_width_m"]').fill('1.2')
    assert page.locator('.de-preview').count() == 0
    assert set(page.locator('[data-edit-module]').evaluate_all('(els) => els.map(e => e.dataset.editModule)')) == {m.id for m in storage.load_design(project.id,2).modules}
    page.locator('[data-design-edit="reflow"]').click()
    page.locator('.de-preview').wait_for()
    second = storage.load_design(project.id,2).modules[1].id
    storage.edit_design(project.id,2,[dict(op='lock_modules',module_ids=[second])],'另一处人工锁定','user',offline=True)
    page.locator('[data-design-edit="apply"]').click()
    page.locator('[role="alert"]').wait_for()
    assert storage.next_version(project.id) == 4
    assert page.locator('.de-preview').count() == 0
    page.goto(f'http://offline.test/#result/{project.id}?version=3')
    page.wait_for_function("testApp.state.result?.version === 3 && document.querySelector('.de-editor')")
    page.locator('[data-design-edit="undo"]').click()
    page.locator('.de-preview').wait_for()
    page.locator('[data-design-edit="apply"]').click()
    page.wait_for_function("location.hash.includes('version=4')")
    assert storage.load_design(project.id,4).locked_module_ids == [first]
    assert not errors
