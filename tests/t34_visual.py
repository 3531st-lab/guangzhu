"""Real WebGL and rendered PDF captures of the production scene/report."""
from playwright.sync_api import sync_playwright
import pypdfium2 as pdfium

from guangzhu.config import ROOT


def capture(data):
    destination, scene = data['assets'], data['scene']
    title = '养殖场棚顶' if data['kind'] == 'barn' else '牧光互补 · 养羊'
    source = '''<html lang="zh"><meta charset="utf-8"><body style="margin:0;background:#f4ece3">
      <h2>光筑 · TITLE（示意）</h2><div id="scene" style="width:1440px;height:800px"></div>
      <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
      <script>const NativeRenderer=THREE.WebGLRenderer;
      THREE.WebGLRenderer=class extends NativeRenderer {
        constructor(...args) {
          super(...args);
          window.actualRenderer=this;
        }
      };</script><script type="module">
      import {createScene} from '/scene.js';
      import {normalizeScene} from '/scene-data.js';
      const input=await (await fetch('/data.json')).json();
      window.geometry=normalizeScene(input);
      window.viewer=createScene(document.querySelector('#scene'));
      window.viewer.setData(input);</script></body></html>'''.replace('TITLE', title)
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
        assert page.evaluate('window.actualRenderer.info.render.triangles > 0')
        page.screenshot(path=str(destination / (data['kind'] + '-3d.png')))
        page.set_content((destination / 'proposal.html').read_text(encoding='utf-8'))
        page.pdf(path=str(destination / 'proposal.pdf'), print_background=True)
        assert not errors
        browser.close()
    document = pdfium.PdfDocument(str(destination / 'proposal.pdf'))
    selected = next((i for i in range(len(document)) if title.split(' · ')[0] + '与采用参数' in
                     document[i].get_textpage().get_text_range()), 0)
    document[selected].render(scale=1.5).to_pil().save(destination / 'proposal-page.png')
    document.close()
