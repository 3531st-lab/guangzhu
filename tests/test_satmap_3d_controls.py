"""Regression coverage for real DOM data attributes containing a digit segment."""
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

WEB = Path(__file__).resolve().parents[1] / 'desktop/web'


def test_satellite_three_dimensional_toolbar_dispatches_real_dom_clicks():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page()

        def route(req):
            url = urlsplit(req.request.url)
            if url.hostname != 'offline.test':
                req.abort()
            elif url.path == '/':
                req.fulfill(body='<html><body><main id="view"></main></body></html>', content_type='text/html')
            else:
                file = WEB / url.path.lstrip('/')
                if file.is_file():
                    req.fulfill(path=str(file))
                else:
                    req.abort()

        page.route('**/*', route)
        page.goto('http://offline.test/')
        page.evaluate("""async () => {
            const {SatMapView} = await import('/satmap-view.js');
            const v = new SatMapView(async () => ({}), () => {}, {});
            const host = document.querySelector('#view');
            v.mount(host);
            v.is3D = true;
            host.innerHTML = v.html();
            window.testView = v;
            window.patches = [];
            window.cameras = [];
            v.twin3d = {
                available: true,
                setSimConfig: patch => window.patches.push(patch),
                setCameraPreset: preset => window.cameras.push(preset),
            };
        }""")
        for mode in ['irradiance', 'diode', 'wiring', 'wind', 'realistic']:
            page.locator(f'[data-sat-3d-mode="{mode}"]').click()
            assert page.evaluate('window.testView.sim3dMode') == mode
            assert page.evaluate('window.patches.at(-1)') == {'displayMode': mode}
            assert page.locator('[data-sat-3d-mode].active').get_attribute('data-sat-3d-mode') == mode
        for date in ['2026-03-21', '2026-06-21', '2026-12-21']:
            page.locator(f'[data-sat-3d-date="{date}"]').click()
            assert page.evaluate('window.testView.sim3dDateStr') == date
            assert page.evaluate('window.patches.at(-1)') == {'dateStr': date}
            assert page.locator('[data-sat-3d-date].active').get_attribute('data-sat-3d-date') == date
        for preset in ['south', 'walkway', 'street', 'top', 'iso']:
            page.locator(f'[data-sat-3d-cam="{preset}"]').click()
            assert page.evaluate('window.testView.sim3dCam') == preset
            assert page.evaluate('window.cameras.at(-1)') == preset
            assert page.locator('[data-sat-3d-cam].active').get_attribute('data-sat-3d-cam') == preset
        browser.close()
