"""A completed save must not hijack a newer result navigation while its GET is pending."""
from test_manual_editor_dom import browser_app, editor_factory, factory, edit_client, open_editor  # noqa: F401
from test_module_gesture_editor_dom import seed, transform


def test_saved_old_result_does_not_replace_newer_pending_version_navigation(browser_app, editor_factory, edit_client):
    page, errors = browser_app
    record, _, free, _ = seed(editor_factory)
    open_editor(page, record, edit_client, version=3)
    held_apply, held_navigation = [], []

    def hold(route, target):
        request = route.request
        response = edit_client.request(request.method, request.url.split('offline.test', 1)[-1],
                                       content=request.post_data_buffer, headers={'content-type': 'application/json'})
        assert response.status_code == 200, response.text
        target.append((route, response))

    page.route(f'**/api/projects/{record.id}/design-edits/apply', lambda route: hold(route, held_apply))
    page.route(f'**/api/projects/{record.id}/result?version=1', lambda route: hold(route, held_navigation))
    page.locator(f'[data-edit-module="{free}"]').click()
    page.locator('[data-design-edit="tool:move"]').click()
    transform(page, 'move', [free], dx_m=.6, dy_m=.4)
    page.locator('.de-preview').wait_for()
    page.locator('[data-design-edit="apply"]').click()
    page.wait_for_function('testApp.state.editing.pendingKind==="apply"')
    page.wait_for_timeout(100)
    assert len(held_apply) == 1
    destination = f'#result/{record.id}?version=1'
    page.evaluate('hash=>location.hash=hash', destination)
    page.wait_for_timeout(100)
    assert len(held_navigation) == 1
    # The new route has begun but the screen still contains the previous result.
    assert page.evaluate('testApp.state.result.version') == 3
    route, response = held_apply.pop()
    route.fulfill(status=response.status_code, body=response.content, content_type='application/json')
    page.wait_for_timeout(150)
    assert page.evaluate('location.hash') == destination
    route, response = held_navigation.pop()
    route.fulfill(status=response.status_code, body=response.content, content_type='application/json')
    page.wait_for_function('testApp.state.result.version===1')
    assert page.evaluate('location.hash') == destination
    assert not errors
