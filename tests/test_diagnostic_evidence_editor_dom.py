"""Current-version diagnostics reach read-only focus, editable selection and explicit previews."""
import json
from pathlib import Path

from test_manual_editor_dom import browser_app, editor_factory, factory, edit_client, open_editor  # noqa: F401
from test_module_gesture_editor_dom import seed
from guangzhu import project as storage


def test_locate_keeps_selection_fix_previews_only_and_evidence_download_matches_saved_version(
        browser_app,editor_factory,edit_client):
    page,errors = browser_app
    record,original,free,locked = seed(editor_factory)
    analysis = storage._path(record.id,'analysis/v3')
    analysis.mkdir(parents=True,exist_ok=True)
    rules = dict(version=3,hard_failed=1,items=[dict(id='S01',name_zh='单板遮挡',status='fail',level='hard',
        value=12,limit=8,unit='%',evidence='显示测试使用同版本逐板记录',hint_zh='核对遮挡组件',source_ref='示意阈值')])
    shading = dict(version=3,modules=[dict(id=free,total_loss_pct=9,main_cause='设备'),dict(id=locked,total_loss_pct=12,main_cause='设备')],
                   summary=dict(avg_loss_pct=10.5,max_loss_pct=12,threshold_pct=8,modules_over_threshold=2))
    (analysis/'rules.json').write_text(json.dumps(rules),encoding='utf-8')
    (analysis/'shading.json').write_text(json.dumps(shading),encoding='utf-8')
    before = storage._path(record.id,'designs/v3.json').read_bytes()
    requests = open_editor(page,record,edit_client,version=3)
    page.locator(f'[data-edit-module="{locked}"]').click()
    page.locator('[data-result-tab="规则"]').click()
    issue = page.locator('[data-diagnostic-issue]').first
    assert '单板遮挡' in issue.inner_text()
    issue.locator('[data-diagnostic-action="locate"]').click()
    assert page.evaluate('[...testApp.state.editing.selected]') == [locked]
    focus = page.evaluate('window.editSceneRecords.at(-1).focus')
    assert set(focus) == {free,locked}
    assert page.evaluate('testApp.state.sceneMode') == 'heat'
    assert not any(path.endswith('/preview') or path.endswith('/apply') for path,_ in requests)
    issue.locator('[data-diagnostic-action="edit"]').click()
    assert page.evaluate('testApp.state.resultTab') == '局部修改'
    assert page.evaluate('[...testApp.state.editing.selected]') == [free]
    assert page.evaluate('testApp.state.editing.toolMode') == 'move'
    assert page.evaluate('window.editSceneRecords.at(-1).focus') == [free]
    page.locator('[data-result-tab="规则"]').click()
    # Model a user-chosen roof-context view. A new focus or a setData without
    # preserveView changes this recorder view, so either regression is observable.
    chosen_view = page.evaluate('''() => {
      const record=window.editSceneRecords.at(-1);
      record.view={projection:'orthographic',position:[16,32,23],target:[13,4,11],zoom:1.35};
      return structuredClone(record.view);
    }''')
    focus_calls = page.evaluate('window.editSceneRecords.at(-1).focusCalls.length')
    page.locator('[data-diagnostic-action="fix"]').click()
    page.locator('.de-preview').wait_for(timeout=120000)
    assert page.evaluate('window.editSceneRecords.at(-1).view') == chosen_view
    assert page.evaluate('window.editSceneRecords.at(-1).focusCalls.length') == focus_calls
    request = next(body for path,body in requests if path.endswith('/preview'))
    assert request['version'] == 3 and request['detailed'] is True
    assert request['ops'] == [dict(op='remove_modules',module_ids=[free])]
    candidate = page.evaluate('testApp.state.editing.preview.design')
    assert [row['id'] for row in candidate['modules']] == [locked]
    assert page.evaluate('testApp.state.editing.preview.impact.available')
    assert storage.next_version(record.id) == 4
    assert not any(path.endswith('/apply') for path,_ in requests)
    # The evidence tab describes the saved version even while an unsaved candidate exists.
    page.locator('[data-result-tab="文件"]').click()
    assert '版本证据 · v3' in page.locator('.design-evidence').inner_text()
    with page.expect_download() as download_info:
        page.locator('[data-action="download-design-evidence"]').click()
    download = download_info.value
    assert download.suggested_filename == f'{record.id}-v3-evidence.json'
    payload = json.loads(Path(download.path()).read_text(encoding='utf-8'))
    assert payload == page.evaluate('testApp.state.result.evidence')
    assert payload['version'] == 3 and payload['model']['modules'] == len(original.modules)
    assert storage._path(record.id,'designs/v3.json').read_bytes() == before
    page.locator('[data-result-tab="局部修改"]').click()
    page.locator('[data-design-edit="cancel"]').click()
    assert page.locator('[data-edit-module]').count() == len(original.modules)
    assert page.evaluate('window.editSceneRecords.at(-1).view') == chosen_view
    assert not errors
