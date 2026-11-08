"""Production app handlers connect scene gestures to authoritative preview/apply/undo."""
import pytest

from test_manual_editor_dom import browser_app, editor_factory, factory, edit_client, open_editor, commit  # noqa: F401
from test_design_edits_async_dom import assert_both_views, geometry
from guangzhu import project as storage


def seed(editor_factory):
    record, initial = editor_factory()
    placed = storage.edit_design(record.id, initial.version, [dict(op='add_modules',placements=[
        dict(center=[8,8]),dict(center=[18,8])])], '设置手动编辑测试', 'user', offline=True)
    modules = storage.load_design(record.id, placed['version']).modules
    locked = storage.edit_design(record.id, placed['version'], [dict(op='lock_modules',module_ids=[modules[1].id])],
                                 '固定第二块组件', 'user', offline=True)
    return record, storage.load_design(record.id, locked['version']), modules[0].id, modules[1].id


def transform(page, mode, ids, **values):
    page.evaluate('''value=>{
      const callbacks=window.editSceneRecords.filter(record=>!record.disposed).at(-1).callbacks;
      callbacks.onTransformStatus({text:'拖动测试',dragging:true});
      void callbacks.onModuleTransform(value);
      callbacks.onTransformStatus({text:'松开，等待预览',dragging:false});
    }''', dict(mode=mode,module_ids=ids,snap=dict(enabled=True,gridM=.1,angleDeg=15,align=True,applied=True),**values))


def test_scene_callback_previews_precise_move_and_rotate_then_saves_and_undoes_with_locks(
        browser_app, editor_factory, edit_client):
    page, errors = browser_app
    record, original, free, locked = seed(editor_factory)
    requests = open_editor(page, record, edit_client, version=3)
    assert page.locator('.de-scene-tools').is_visible()
    page.locator(f'[data-edit-module="{locked}"]').click()
    page.locator('[data-design-edit="tool:move"]').click()
    config = page.evaluate('window.editSceneRecords.at(-1).editing')
    assert config['selectedIds'] == [locked] and locked in config['lockedIds']
    transform(page, 'move', [locked], dx_m=.6, dy_m=.4)
    page.locator('.de-error').wait_for()
    assert '已锁定' in page.locator('.de-error').inner_text()
    assert not any(url.endswith('/preview') for url, _ in requests)
    page.locator(f'[data-edit-module="{locked}"]').click()
    page.locator(f'[data-edit-module="{free}"]').click()
    page.locator('[data-edit-snap="gridM"]').fill('0.2')
    page.locator('[data-edit-snap="angleDeg"]').fill('30')
    page.locator('[data-edit-snap="align"]').uncheck()
    assert page.evaluate('window.editSceneRecords.at(-1).editing.snap') == dict(enabled=True,gridM=.2,angleDeg=30,align=False)
    transform(page, 'move', [free], dx_m=.6, dy_m=.4)
    page.locator('.de-preview').wait_for()
    assert page.locator('[data-edit-move="dx"]').input_value() == '0.6'
    assert page.locator('[data-edit-move="dy"]').input_value() == '0.4'
    candidate = page.evaluate('testApp.state.editing.preview.design')
    assert candidate['modules'][0]['center'][:2] == pytest.approx([8.6,8.4])
    assert page.evaluate('[...testApp.state.editing.selected]') == [free]
    assert page.evaluate('window.editSceneRecords.at(-1).editing.busy')
    assert_both_views(page,candidate)
    assert storage.next_version(record.id) == 4
    moved = commit(page,4)
    page.locator(f'[data-edit-module="{free}"]').click()
    page.locator('[data-design-edit="tool:rotate"]').click()
    transform(page, 'rotate', [free], angle_deg=30)
    page.locator('.de-preview').wait_for()
    assert page.locator('[data-edit-rotate="angle"]').input_value() == '30'
    rotated = commit(page,5)
    assert geometry(rotated) != geometry(moved)
    page.locator('[data-design-edit="undo"]').click()
    page.locator('.de-preview').wait_for()
    undone = commit(page,6)
    assert geometry(undone) == geometry(moved)
    assert undone['locked_module_ids'] == [locked]
    assert geometry(storage.load_design(record.id,3).model_dump(mode='json')) == geometry(original.model_dump(mode='json'))
    assert not errors


def test_snap_and_tool_changes_cancel_late_gesture_requests_and_tab_disables_gestures(
        browser_app, editor_factory, edit_client):
    page, errors = browser_app
    record, original, free, _ = seed(editor_factory)
    pending = []
    open_editor(page,record,edit_client,hold=pending,version=3)
    page.locator(f'[data-edit-module="{free}"]').click()
    page.locator('[data-design-edit="tool:move"]').click()
    transform(page,'move',[free],dx_m=.6,dy_m=.4)
    page.wait_for_function('testApp.state.editing.busy')
    page.locator('[data-edit-snap="gridM"]').fill('0.5')
    assert not page.evaluate('testApp.state.editing.busy')
    assert page.evaluate('window.editSceneRecords.at(-1).editing.snap.gridM') == .5
    route,response = pending.pop()
    route.fulfill(status=response.status_code,body=response.content,content_type='application/json')
    page.wait_for_timeout(100)
    assert page.locator('.de-preview').count() == 0
    assert_both_views(page,original.model_dump(mode='json'))
    transform(page,'move',[free],dx_m=1,dy_m=0)
    page.wait_for_function('testApp.state.editing.busy')
    page.locator('[data-design-edit="tool:rotate"]').click()
    route,response = pending.pop()
    route.fulfill(status=response.status_code,body=response.content,content_type='application/json')
    page.wait_for_timeout(100)
    assert page.locator('.de-preview').count() == 0
    assert page.evaluate('testApp.state.editing.toolMode') == 'rotate'
    page.locator('[data-result-tab="结论"]').click()
    assert page.evaluate('window.editSceneRecords.at(-1).editing.enabled') is False
    page.locator('[data-result-tab="局部修改"]').click()
    assert page.evaluate('window.editSceneRecords.at(-1).editing.enabled') is True
    page.evaluate('window.oldModuleCallbacks=window.editSceneRecords.at(-1).callbacks')
    page.evaluate("location.hash='#records'")
    page.wait_for_function("testApp.state.route==='records'")
    assert page.evaluate('window.editSceneRecords.at(-1).editing.enabled') is False
    page.evaluate(f"location.hash='#result/{record.id}?version=3'")
    page.locator(f'[data-edit-module="{free}"]').click()
    page.locator('[data-design-edit="tool:move"]').click()
    page.evaluate('''id=>{oldModuleCallbacks.onTransformStatus({text:'过期场景',dragging:true});
      void oldModuleCallbacks.onModuleTransform({mode:'move',module_ids:[id],dx_m:1,dy_m:0});}''',free)
    page.wait_for_timeout(100)
    assert page.evaluate('testApp.state.editing.dragging') is False
    assert page.evaluate('testApp.state.editing.busy') is False
    assert not pending
    assert storage.next_version(record.id) == 4
    assert not errors


def test_rejected_drag_restores_saved_geometry_and_shows_the_authoritative_reason(
        browser_app,editor_factory,edit_client):
    page,errors = browser_app
    record,original,free,_ = seed(editor_factory)
    requests = open_editor(page,record,edit_client,version=3)
    page.locator(f'[data-edit-module="{free}"]').click()
    page.locator('[data-design-edit="tool:move"]').click()
    transform(page,'move',[free],dx_m=100,dy_m=0)
    page.locator('.de-error').wait_for()
    message = page.locator('.de-error').inner_text()
    assert any(word in message for word in ('屋面','边界','越界')), message
    assert page.locator('.de-preview').count() == 0
    assert page.evaluate('testApp.state.editing.busy') is False
    assert page.evaluate('testApp.state.editing.dragging') is False
    assert_both_views(page,original.model_dump(mode='json'))
    assert len([path for path,_ in requests if path.endswith('/preview')]) == 1
    assert storage.next_version(record.id) == 4
    assert not errors
