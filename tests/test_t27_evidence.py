"""Real offline T27 calculations and UI captures; normal test runs use tmp_path."""
import json
import os

from playwright.sync_api import sync_playwright
from openpyxl import load_workbook

from guangzhu import analysis, layout, mcp_actions, project as storage
from guangzhu.config import ROOT
from guangzhu.report.deliverables import write_deliverables
from guangzhu.report.figures import plan
from guangzhu.report.view import render


def test_real_calculations_three_views_and_module_comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    assets = ROOT / 'reports/assets/T27' if os.environ.get('T27_CAPTURE') == '1' else tmp_path / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    p = storage.init(ROOT / 'data/demo/projects/changzhou-demo', 't27-evidence')
    p.roof.outline = [(0, 0), (24, 0), (24, 18), (0, 18)]
    p.roof.obstacles = []
    p.roof.keepouts = []
    p.roof.parapet_height_m = 0
    p.equipment.module_id = 'trina-tsm-605neg19rc20'
    storage.save(p)
    d = layout.generate_layout(p, dict(layout='ew', fill_landscape=True))
    storage.save_design(p.id, d)
    summary = analysis.analyze(p.id, 1, offline=True)
    comparison = mcp_actions._compare_options(p.id, 1, offline=True)
    context = dict(project=p.model_dump(mode='json'), design=d.model_dump(mode='json'), summary=summary, version=1,
                   compare=comparison, facts={}, review=None, approval=None, sessions=[], requirements=[], verification={},
                   sources={}, versions=[], relaxations=[], history=[], run={}, generated_at='2026-10-06T00:00:00+08:00',
                   run_id='T27-offline-no-AI', project_id=p.id, crosscheck=None)
    context.update({name: mcp_actions._read(p.id, f'analysis/v1/{name}.json')
                    for name in ['electrical', 'shading', 'structure', 'rules', 'economics']})
    html = render(context)
    assert '东西向' in html and '补位' in html and layout.CAPACITY_NOTE in html and '605 W' in html
    write_deliverables(p.id, 1, assets)
    book = load_workbook(assets / 'bom-v1.xlsx')
    assert any('东西向压载支架' in str(row) for row in book['材料清单'].values)
    scene = {key: context[key] for key in ('project', 'design', 'shading', 'electrical')}
    pocket = p.model_copy(deep=True)
    pocket.equipment.module_id = 'trina-tsm-550de19'
    pocket.roof.outline = [(0, 0), (8, 0), (8, 1.4), (4, 1.4), (4, 6), (0, 6)]
    filled = layout.generate_layout(pocket, dict(tilt_deg=10, edge_setback_m=0, fill_landscape=True))
    assert filled.statistics['fill_landscape_count'] == 1
    drawing = plan(dict(project=pocket.model_dump(), design=filled.model_dump(), shading=dict(modules=[])))
    web = ROOT / 'desktop/web'
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge', headless=True, args=['--enable-webgl', '--use-angle=swiftshader'])
        page = browser.new_page(viewport=dict(width=1440, height=900))
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        source = '''<html lang="zh"><meta charset="utf-8"><link rel="stylesheet" href="/styles.css">
            <body style="padding:28px;background:#f4ece3"><h2>离线工程验收 · T27</h2><main id="content"></main>
            <script src="/vendor/three.min.js"></script><script src="/vendor/OrbitControls.min.js"></script>
            <script type="module">import {createScene} from '/scene.js';
            import {comparisonTable} from '/data.js';
            window.showTable=compare=>document.querySelector('#content').innerHTML=comparisonTable(compare);
            window.showScene=data=>{
            document.querySelector('#content').innerHTML='<div id="scene" style="height:750px"></div>';
            window.viewer=createScene(document.querySelector('#scene'));
            window.viewer.setData(data);
            };
            </script></body></html>'''
        def route(request):
            path = request.request.url.split('offline.test')[-1]
            if path == '/':
                request.fulfill(body=source, content_type='text/html')
            else:
                file = web / path.lstrip('/')
                request.fulfill(path=str(file)) if file.is_file() else request.abort()
        page.route('**/*', route)
        page.goto('http://offline.test/')
        page.wait_for_function('Boolean(window.showTable)')
        page.evaluate('showTable', comparison)
        assert page.locator('th', has_text='排法').count() == 1
        assert '冬至 10–14' in page.inner_text('body')
        page.screenshot(path=str(assets / 'comparison.png'))
        page.evaluate('showScene', scene)
        page.wait_for_function('window.viewer?.stats().frames > 3')
        assert page.evaluate('window.viewer.stats().panels') == len(d.modules)
        page.screenshot(path=str(assets / 'ew-scene.png'))
        page.evaluate('window.viewer.dispose()')
        page.locator('#content').evaluate('(element, svg) => element.innerHTML=svg',
                                         '<h3>横放补位 1 块 · 同底边、上缘更低</h3>' + str(drawing))
        page.locator('#content svg').evaluate('''svg => {
            svg.style.height="680px";
            svg.style.width="100%";
        }''')
        page.screenshot(path=str(assets / 'landscape-fill.png'))
        page.set_content(html)
        page.pdf(path=str(assets / 'proposal.pdf'), print_background=True)
        page.locator('section.options').screenshot(path=str(assets / 'proposal-comparison.png'))
        assert not errors
        browser.close()
    (assets / 'scene.json').write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding='utf-8')
    (assets / 'comparison.json').write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding='utf-8')
    numbers = []
    for index, identifier in enumerate(['trina-tsm-550de19', 'trina-tsm-605neg19rc20', 'jinko-jkm605n-66hl4m-bdv']):
        project = storage.init(ROOT / 'data/demo/projects/changzhou-demo', f't27-module-{index}')
        project.equipment.module_id = identifier
        storage.save(project)
        design = layout.generate_layout(project, {})
        storage.save_design(project.id, design)
        value = analysis.analyze(project.id, 1, offline=True)
        numbers.append(dict(module_id=identifier, modules=len(design.modules), dc_kw=value['dc_kw'],
                            annual_kwh=value['yield_kwh']['p50'], payback_years=value['economics']['payback_years']))
    (assets / 'module-comparison.json').write_text(json.dumps(numbers, ensure_ascii=False, indent=2), encoding='utf-8')
    assert len({row['annual_kwh'] for row in numbers}) == 3
