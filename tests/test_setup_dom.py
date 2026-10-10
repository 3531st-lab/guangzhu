"""Home-page key bar and background setup in a real browser with fully intercepted local transport."""
import pytest
from test_t16_dom import browser_app


def setup_status(phase='configuring', ready=False, error=None):
    status = dict(installation=dict(installed=True, id='a' * 64, root='C:\\安装光筑', build='build'), required=True,
                  ready=ready, busy=phase == 'configuring', phase=phase, operation_id='c' * 32, workspace_id='b' * 64,
                  steps=[dict(number=i + 1, state='ready' if ready or i != 5 else 'waiting', reason='公开原因', action='') for i in range(7)])
    if error:
        status['error'] = error
    return status


def installed(page, status, configure=None):
    page.route('**/api/setup/status', lambda route: route.fulfill(json=status))
    page.route('**/api/status', lambda route: route.fulfill(json={'agh': {'connected': True, 'url': 'http://127.0.0.1:4178'}}))
    if configure:
        page.route('**/api/setup/configure', configure)
    page.evaluate("location.hash='#new'")
    page.reload(wait_until='commit')
    page.wait_for_function("Boolean(window.testApp)")
    page.wait_for_selector('.keybar')


def test_installed_home_shows_the_key_bar_and_progress_never_a_setup_page(browser_app):
    page, errors = browser_app
    installed(page, setup_status())
    assert page.locator('input[data-key="agnes"][type="password"]').count() == 1
    assert page.locator('input[data-key="deepseek"][type="password"]').count() == 1
    page.wait_for_function("document.getElementById('kb-state').textContent.includes('正在准备设计工具')")
    text = page.locator('#view').inner_text()
    assert '开始配置' not in text and '实例目录' not in text and 'Python' not in text
    assert page.locator('.steps').count() == 0
    page.evaluate("location.hash='#setup'")
    page.wait_for_function("location.hash==='#new'")
    page.evaluate("location.hash='#form'")
    page.wait_for_selector('[data-field="budget"]')
    assert errors == []


def test_saving_a_key_sends_it_once_clears_the_box_and_reports_the_result(browser_app):
    page, errors = browser_app
    status = setup_status('waiting_models')
    installed(page, status)
    page.locator('input[data-key="agnes"]').fill('placeholder-key-for-browser-test')
    page.locator('[data-save-key="agnes"]').click()
    sent = page.evaluate("testApp.bridge.logs.filter(row => row.type==='gz.saveKey')")
    assert len(sent) == 1 and sent[0]['provider'] == 'agnes' and sent[0]['key'] == 'placeholder-key-for-browser-test'
    assert page.locator('input[data-key="agnes"]').input_value() == ''
    assert '正在验证' in page.locator('#kb-chip-agnes').inner_text()
    polls = page.evaluate("performance.getEntriesByType('resource').length")
    page.evaluate("testApp.bridge.onMessage({type:'gz.keySaved',provider:'agnes',model:'agnes-3.0-flash'},{keySave:'agnes'})")
    page.wait_for_function("document.getElementById('notice').textContent.includes('Agnes key 已保存')")
    assert '正在验证' not in page.locator('#kb-chip-agnes').inner_text()
    page.locator('[data-save-key="deepseek"]').click()
    page.wait_for_function("document.getElementById('notice').textContent.includes('先把 key 粘贴到框里')")
    assert len(page.evaluate("testApp.bridge.logs.filter(row => row.type==='gz.saveKey')")) == 1
    assert polls >= 0 and errors == []


def test_a_half_typed_key_survives_background_status_polls(browser_app):
    page, errors = browser_app
    status = setup_status()
    installed(page, status)
    box = page.locator('input[data-key="deepseek"]')
    box.fill('half-typed')
    box.focus()
    status.update(phase='waiting_models', busy=False)
    page.evaluate('testApp.checkConnection()')
    page.evaluate('testApp.setup.poll()')
    assert box.input_value() == 'half-typed'
    assert page.evaluate("document.activeElement.dataset.key") == 'deepseek'
    assert errors == []


def test_failed_setup_shows_the_reason_and_retry_restarts_configuration(browser_app):
    page, errors = browser_app
    status = setup_status('failed', error='端口 4178 被别的程序占用，请关闭它后重新打开光筑')
    bodies = []
    def configure(route):
        bodies.append(route.request.post_data_json)
        status.update(phase='configuring', busy=True)
        status.pop('error', None)
        route.fulfill(json=status)
    installed(page, status, configure)
    page.wait_for_function("document.getElementById('kb-state').textContent.includes('被别的程序占用')")
    page.locator('[data-action="setup-retry"]').click()
    page.wait_for_function("document.getElementById('kb-state').textContent.includes('正在准备设计工具')")
    assert bodies == [{}]
    assert errors == []



def test_codex_r05_a_bridge_error_while_registering_stays_visible_and_retry_sends_it_once_more(browser_app):
    page, errors = browser_app
    configured = []
    status = setup_status('waiting_workspace')
    installed(page, status, lambda route: (configured.append(1), route.fulfill(json=status)))
    sent = "testApp.bridge.logs.filter(row => row.type==='gz.registerWorkspace').length"
    page.wait_for_function(sent + " === 1")
    page.evaluate("""() => {const row = testApp.bridge.logs.find(r => r.type==='gz.registerWorkspace');
      testApp.bridge.onMessage({type:'gz.error', installation_id:row.installation_id, operation_id:row.operation_id, message:'工作区目录不可写'}, row.request);}""")
    page.wait_for_function("document.getElementById('kb-state').textContent.includes('工作区目录不可写')")
    page.wait_for_timeout(2500)
    assert '工作区目录不可写' in page.locator('#kb-state').inner_text() and page.evaluate(sent) == 1
    assert '没准备好' in page.locator('#connection').inner_text()
    page.locator('[data-action="setup-retry"]').click()
    page.wait_for_function(sent + " === 2")
    page.wait_for_function("!document.getElementById('kb-state').textContent.includes('工作区目录不可写')")
    assert page.locator('[data-action="setup-retry"]').count() == 0
    page.wait_for_timeout(2500)
    assert page.evaluate(sent) == 2 and configured == []
    assert errors == []

@pytest.mark.parametrize('width,height', [(1536, 834), (1366, 700), (1280, 680)])
def test_key_bar_fits_common_laptop_windows_without_sideways_scrolling(browser_app, width, height):
    page, errors = browser_app
    page.set_viewport_size(dict(width=width, height=height))
    installed(page, setup_status('waiting_models'))
    bar = page.locator('.keybar').bounding_box()
    assert bar['x'] >= 0 and bar['x'] + bar['width'] <= width
    for provider in ('agnes', 'deepseek', 'other'):
        box = page.locator(f'input[data-key="{provider}"]').bounding_box()
        assert box['width'] >= 180 and box['x'] + box['width'] <= width
    assert page.evaluate("document.querySelector('.page').scrollWidth <= document.querySelector('.page').clientWidth")
    assert errors == []
