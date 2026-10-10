"""Render production scene and proposal with a real WebGL browser, never a scene stub."""
from playwright.sync_api import sync_playwright

from guangzhu.config import ROOT


def capture(data):
    destination, scene = data['assets'], data['scene']
    source = '''<html lang="zh"><meta charset="utf-8"><body style="margin:0;background:#f4ece3">
      <h2>光筑 · INSTALLATION_TITLE（示意）</h2><div id="scene" style="width:1440px;height:800px"></div>
      <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
      <script>const NativeRenderer=THREE.WebGLRenderer;
      THREE.WebGLRenderer=class extends NativeRenderer {
        constructor(...args) {
          super(...args);
          window.actualRenderer=this;
        }
      };
      const NativeControls=THREE.OrbitControls;
      THREE.OrbitControls=class extends NativeControls {
        constructor(...args) {
          super(...args);
          window.actualControls=this;
        }
      };</script><script type="module">
      import {createScene} from '/scene.js';
      import {normalizeScene} from '/scene-data.js';
      const input=await (await fetch('/data.json')).json();
      window.geometry=normalizeScene(input);
      window.viewer=createScene(document.querySelector('#scene'));
      window.viewer.setData(input);</script></body></html>'''
    source = source.replace('INSTALLATION_TITLE', '空地光伏' if data['kind'] == 'ground' else '车棚光伏')
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge', headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1440, height=900))
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def respond(route):
            path = route.request.url.split('offline.test')[-1]
            if path == '/':
                route.fulfill(body=source, content_type='text/html')
            elif path == '/data.json':
                route.fulfill(json=scene)
            else:
                file = ROOT / 'desktop/web' / path.lstrip('/')
                route.fulfill(path=str(file)) if file.is_file() else route.abort()
        page.route('**/*', respond)
        page.goto('http://offline.test/')
        page.wait_for_function('window.viewer?.stats().frames > 3')
        assert page.evaluate('window.viewer.stats().panels') == len(scene['design']['modules'])
        assert page.evaluate('window.actualRenderer.getContext() instanceof WebGL2RenderingContext')
        assert page.evaluate('window.actualRenderer.info.render.triangles > 0')
        assert page.evaluate('window.geometry.roof.height_m') == 0
        page.screenshot(path=str(destination / (data['kind'] + '-3d.png')))
        page.evaluate('''() => {
          const controls=window.actualControls;
          const point=window.geometry.modules[0].corners[0];
          const target=window.geometry.world(point);
          controls.minDistance=1;
          controls.target.set(...target);
          controls.object.position.set(target[0]+9,target[1]+2,target[2]+12);
          controls.update();
        }''')
        page.wait_for_function('window.viewer.stats().frames > 10')
        page.screenshot(path=str(destination / (data['kind'] + '-detail.png')))
        if data.get('visual_only'):
            assert not errors
            browser.close()
            return
        page.set_content((destination / 'proposal.html').read_text(encoding='utf-8'))
        page.locator('section').first.screenshot(path=str(destination / 'proposal-page.png'))
        page.pdf(path=str(destination / 'proposal.pdf'), print_background=True)
        assert (destination / 'proposal.pdf').read_bytes().startswith(b'%PDF')
        assert not errors
        browser.close()
