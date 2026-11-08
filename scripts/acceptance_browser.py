"""Record the installed application's real HTTP UI against an explicit QA installation.

No routes, API responses, application sources, or browser JavaScript are replaced.
The video is Playwright's original-speed browser viewport recording. Credentials are
never entered, and no other desktop windows are recorded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import time
import traceback
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit
from urllib.request import urlopen
import zipfile

from playwright.sync_api import sync_playwright


IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}')
EMBEDDED_FONTS = [('Noto Serif SC', '900', 'NotoSerifSC-900-guangzhu.woff2', '光筑'),
                  ('IBM Plex Mono', '400', 'IBMPlexMono-Regular.woff2', '12345')]
RESPONSIVE_VIEWPORTS = [(1440, 900), (1366, 768), (390, 844)]
RESPONSIVE_RESTORE_VIEWPORT = dict(width=1440, height=900)
RESPONSIVE_CONTROLS = [
    ('preview-export', '.head [data-action="preview-export"]'),
    ('download-dxf', '.head [data-action="download-dxf"]'),
    ('download-xlsx', '.head [data-action="download-xlsx"]'),
    ('module', '#copilot-module'), ('inverter', '#copilot-inverter'),
    ('dc-cable', '#copilot-dc-cable'), ('ac-cable', '#copilot-ac-cable'),
    ('wind-roughness', '#copilot-wind-roughness'),
    ('apply-equipment', '[data-action="copilot-apply-equipment"]'),
    ('rule-input', '#copilot-input'), ('rule-send', '[data-action="copilot-send"]'),
]


def public_url(url):
    """Keep resource paths and version numbers, never arbitrary query parameters."""
    value = urlsplit(url)
    version = parse_qs(value.query).get('version', [''])[0]
    query = f'version={version}' if version.isdigit() else ''
    return urlunsplit((value.scheme, value.netloc, value.path, query, ''))


def read_json(base, path):
    with urlopen(base + '/api/' + path, timeout=60) as response:
        return json.load(response)


def projects_from_args(args):
    selected = {}
    if args.receipt:
        receipt = json.loads(args.receipt.read_text(encoding='utf-8-sig'))
        for row in receipt.get('cases', []):
            if row.get('project_id'):
                selected[row['project_id']] = row.get('final_version') or row.get('initial_version')
    for value in args.project:
        identifier, separator, version = value.partition(':')
        selected[identifier] = int(version) if separator else None
    if not selected and not args.run_template and not args.fonts_only:
        raise ValueError('Provide --receipt, --project id[:version], --run-template, or --fonts-only.')
    for identifier, version in selected.items():
        if not IDENTIFIER.fullmatch(identifier) or version is not None and (type(version) is not int or version < 1):
            raise ValueError(f'Invalid QA project/version: {identifier}:{version}')
    return selected


class Recorder:
    def __init__(self, page, output, evidence):
        self.page, self.output, self.evidence = page, output, evidence
        self.current = 'startup'
        page.on('pageerror', lambda error: evidence['pageerrors'].append(dict(step=self.current, message=str(error))))
        page.on('requestfailed', lambda request: evidence['requestfailed'].append(
            dict(step=self.current, url=public_url(request.url), error=request.failure)))
        page.on('response', self.response)
        page.on('console', lambda message: evidence['console'].append(dict(step=self.current, type=message.type, text=message.text))
                if message.type in ('warning', 'error') else None)

    def response(self, response):
        if any(urlsplit(response.url).path.endswith('/' + font[2]) for font in EMBEDDED_FONTS):
            self.evidence['font_responses'].append(dict(step=self.current, url=public_url(response.url), status=response.status))
        if response.status >= 400:
            self.evidence['http_errors'].append(dict(step=self.current, url=public_url(response.url), status=response.status))

    def screenshot(self, name):
        filename = self.output / f'{name}.png'
        # A short real pause keeps each stable state legible in the unretimed video.
        self.page.wait_for_timeout(800)
        self.page.screenshot(path=str(filename))
        self.evidence['screenshots'].append(str(filename))

    def step(self, name, action):
        self.current = name
        start = time.monotonic()
        print(f'START {name}', flush=True)
        try:
            detail = action() or {}
            row = dict(name=name, passed=True, **detail)
        except Exception as error:
            row = dict(name=name, passed=False, error=f'{type(error).__name__}: {error}', traceback=traceback.format_exc())
            try:
                row['failure_state'] = dict(route_hash=urlsplit(self.page.url).fragment,
                    subtitles=self.page.locator('.head > div > p').all_text_contents())
            except Exception as state_error:
                row['state_error'] = str(state_error)
            try:
                self.screenshot(f'FAILED-{name}')
            except Exception as screenshot_error:
                row['screenshot_error'] = str(screenshot_error)
        row['elapsed_seconds'] = round(time.monotonic() - start, 3)
        self.evidence['checks'].append(row)
        self.save()
        print(('PASS ' if row['passed'] else 'FAIL ') + name, flush=True)
        return row

    def save(self):
        (self.output / 'browser-acceptance.json').write_text(
            json.dumps(self.evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def wait_canvas(page):
    canvas = page.locator('#scene canvas')
    canvas.wait_for()
    page.wait_for_function("(() => {const c=document.querySelector('#scene canvas');return c && c.width>200 && c.height>100;})()")
    page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
    assert page.locator('#scene-retry').is_hidden(), 'The production renderer showed its retry state.'
    return canvas.bounding_box()


def number(text):
    return float(text.replace(',', '').replace('%', '').strip())


def result_header_pattern(identifier, version):
    # Status text may precede vN (unexported) or follow it (historical/exported).
    # Match the exact project first; only then accept an independent version token.
    return re.compile(rf'^{re.escape(identifier)} · .*?(?<![A-Za-z0-9_])v{version}(?![A-Za-z0-9_])')


def wait_result_header(page, identifier, version):
    """Hash navigation retains the old DOM until its new result request completes."""
    pattern = result_header_pattern(identifier, version)
    header = page.locator('.head > div > p').filter(has_text=pattern)
    header.wait_for()
    actual = header.inner_text()
    assert pattern.search(actual), f'Expected {identifier} v{version}, got {actual!r}.'
    return actual


def verify_embedded_fonts(page, evidence, expected_origin):
    """Load the iframe's real declared font faces and inspect their actual responses."""
    diagnostic = {}
    evidence['font_diagnostics'].append(diagnostic)
    page.locator('#agh').wait_for(state='attached')
    page.wait_for_function("document.querySelector('#agh')?.src.startsWith('http://127.0.0.1:')")
    frame = page.locator('#agh').element_handle().content_frame()
    assert frame is not None, 'The actual AGH iframe has no content frame.'

    def snapshot():
        state = dict(url=public_url(frame.url))
        try:
            state['iframe'] = page.locator('#agh').evaluate('''node => ({src:node.src,
                visibility:getComputedStyle(node).visibility,hostVisibility:getComputedStyle(node.parentElement).visibility,
                hostClass:node.parentElement.className,box:node.getBoundingClientRect().toJSON()})''')
            state['document'] = frame.evaluate('''() => ({readyState:document.readyState,visibilityState:document.visibilityState,
                fonts:Array.from(document.fonts).map(face=>({family:face.family,status:face.status,weight:face.weight})),
                stylesheets:Array.from(document.styleSheets).map(sheet=>sheet.href)})''')
        except Exception as error:
            state['inspection_error'] = f'{type(error).__name__}: {error}'
        return state

    diagnostic['before'] = snapshot()
    try:
        frame.wait_for_url(re.compile(rf'^{re.escape(expected_origin)}(?:/|$)'), wait_until='domcontentloaded')
        # The real AGH iframe is parked with visibility:hidden on the home screen.
        # Browser rAF may pause there, so font registration must use timer polling.
        frame.wait_for_function('''families => families.every(family =>
            Array.from(document.fonts).some(face => face.family.replaceAll('"','').replaceAll("'",'') === family))''',
            arg=[font[0] for font in EMBEDDED_FONTS], polling=100)
        diagnostic['registered'] = snapshot()
        diagnostic['animation_frame_probe'] = frame.evaluate('''() => new Promise(resolve => {
            const started=performance.now(); let request;
            const timer=setTimeout(()=>{cancelAnimationFrame(request);resolve({raf_fired:false,elapsed_ms:performance.now()-started});},250);
            request=requestAnimationFrame(()=>{clearTimeout(timer);resolve({raf_fired:true,elapsed_ms:performance.now()-started});});
        })''')
    except Exception:
        diagnostic['failure'] = snapshot()
        raise
    actual = urlsplit(frame.url)
    origin = urlunsplit((actual.scheme, actual.netloc, '', '', ''))
    assert origin == expected_origin, (origin, expected_origin)
    loaded = frame.evaluate('''async specs => {
        const results=[];
        for (const [family, weight, filename, sample] of specs) {
            const faces=await document.fonts.load(`${weight} 22px "${family}"`, sample);
            results.push({family,weight,filename,count:faces.length,statuses:faces.map(face=>face.status),
                checked:document.fonts.check(`${weight} 22px "${family}"`,sample)});
        }
        return results;
    }''', EMBEDDED_FONTS)
    for row in loaded:
        assert row['count'] > 0 and row['checked'] and all(state == 'loaded' for state in row['statuses']), row
        expected_url = origin + '/skins/guangzhu/assets/' + row['filename']
        replies = [response for response in evidence['font_responses'] if response['url'] == expected_url]
        assert replies and all(response['status'] == 200 for response in replies), (expected_url, replies)
    diagnostic['after'] = snapshot()
    return dict(origin=origin, fonts=loaded)


def download_export(page, output, kind, identifier, version):
    """Click the real download control and retain the browser's downloaded bytes."""
    with page.expect_download(timeout=120000) as pending:
        page.locator(f'#local-export-panel [data-action="download-{kind}"]').click()
    downloaded = pending.value
    failure = downloaded.failure()
    assert failure is None, failure
    expected = f'{identifier}-{"layout" if kind == "dxf" else "bom"}-v{version}.{kind}'
    assert downloaded.suggested_filename == expected
    destination = output / 'downloads' / expected
    destination.parent.mkdir(parents=True, exist_ok=True)
    downloaded.save_as(str(destination))
    contents = destination.read_bytes()
    assert contents, f'The {kind} download was empty.'
    if kind == 'xlsx':
        with zipfile.ZipFile(destination) as workbook:
            assert workbook.testzip() is None
            assert 'xl/workbook.xml' in workbook.namelist()
    else:
        assert b'SECTION' in contents and b'EOF' in contents, 'The downloaded file is not a DXF document.'
    return dict(kind=kind, path=str(destination), filename=expected, bytes=len(contents),
                sha256=hashlib.sha256(contents).hexdigest())


def verify_months(page, result):
    fold = page.locator('[data-fold="monthly"]')
    fold.wait_for()
    if not fold.evaluate('(node)=>node.open'):
        fold.locator('summary').first.click()
    fold.scroll_into_view_if_needed()
    if result.get('evidence', {}).get('analysis', {}).get('status') == 'stale':
        assert fold.locator('[data-energy-unavailable]').count() == 1
        return dict(state='stale-shown')
    economics = result.get('economics') or {}
    monthly = (economics.get('self_use') or {}).get('monthly')
    detailed = isinstance(monthly, list)
    if not detailed:
        monthly = economics.get('analysis_metadata', {}).get('yield_kwh', {}).get('monthly_kwh')
    if not isinstance(monthly, list):
        assert fold.locator('[data-energy-unavailable]').count() == 1
        return dict(state='missing-shown')
    assert len(monthly) == 12, 'The installed calculation did not record twelve months.'
    columns = ['generation_kwh', 'self_use_kwh', 'export_kwh', 'curtailed_kwh'] if detailed else ['ac_kwh']
    rows = fold.locator('tbody tr')
    assert rows.count() == 12
    for index, expected in enumerate(sorted(monthly, key=lambda row: row['month'])):
        cells = rows.nth(index).locator('td').all_text_contents()
        assert int(cells[0]) == expected['month']
        for actual, key in zip(cells[1:], columns):
            assert math.isclose(number(actual), expected[key], abs_tol=.011), (index + 1, key, actual, expected[key])
    total = sum(row[columns[0]] for row in monthly)
    annual = ((result.get('metrics') or result.get('summary') or {}).get('yield_kwh') or {}).get('p50')
    if isinstance(annual, (int, float)):
        assert math.isclose(total, annual, rel_tol=1e-6, abs_tol=.001), (total, annual)
    return dict(state='twelve-actual-months', total_kwh=total, detailed=detailed)


def verify_responsive_result(page, record, base_url, identifier, requested):
    """Measure the installed UI and exercise fields without submitting another calculation."""
    suffix = f'?version={requested}' if requested else ''
    result = read_json(base_url, f'projects/{quote(identifier)}/result{suffix}')
    version = result['version']
    assert result['project_id'] == identifier and type(version) is int and version > 0
    assert result['design']['version'] == version and result.get('editable') is not False
    detail = dict(project_id=identifier, version=version, viewports=[],
                  activation='Buttons use Playwright trial clicks; selects and input are changed then restored.',
                  restore_viewport=RESPONSIVE_RESTORE_VIEWPORT.copy())
    record.evidence.setdefault('responsive_diagnostics', []).append(detail)
    try:
        page.goto(base_url + f'/#result/{quote(identifier)}?version={version}', wait_until='domcontentloaded')
        wait_result_header(page, identifier, version)
        page.locator('[data-result-tab="结论"]').click()
        wait_canvas(page)
        page.locator('[data-scene-mode="wiring"]').click()
        for width, height in RESPONSIVE_VIEWPORTS:
            prefix = f'10-responsive-{width}x{height}'
            row = dict(width=width, height=height, passed=False, controls=[], select_roundtrips=[])
            detail['viewports'].append(row)
            try:
                page.set_viewport_size(dict(width=width, height=height))
                wait_canvas(page)
                page.evaluate("scrollTo(0,0);document.querySelector('#result-panel').scrollTop=0")
                row['geometry'] = page.evaluate('''selectors => {
                    const measure = el => {
                        if (!el) return null;
                        const r=el.getBoundingClientRect(), c=getComputedStyle(el);
                        return {tag:el.tagName.toLowerCase(),id:el.id,class:el.getAttribute('class'),
                            rect:Object.fromEntries(['left','right','top','width','height'].map(key=>
                                [key,Math.round(r[key]*100)/100])),
                            clientWidth:el.clientWidth,scrollWidth:el.scrollWidth,
                            grid:c.gridTemplateColumns,minWidth:c.minWidth,overflowX:c.overflowX};
                    };
                    return {innerWidth,innerHeight,scrollWidth:document.documentElement.scrollWidth,
                        scrollHeight:document.documentElement.scrollHeight,
                        panels:Object.fromEntries(['.head .actions','.res-right','#result-panel','.copilot-card','.engineering']
                            .map(selector=>[selector,measure(document.querySelector(selector))])),
                        controls:Object.fromEntries(selectors.map(([name,selector])=>
                            [name,measure(document.querySelector(selector))]))};
                }''', RESPONSIVE_CONTROLS)
                record.screenshot(prefix + '-window')
                full_page = record.output / f'{prefix}-full-page.png'
                page.screenshot(path=str(full_page), full_page=True)
                record.evidence['screenshots'].append(str(full_page))
                geometry = row['geometry']
                assert geometry['innerWidth'] == width and geometry['innerHeight'] == height, geometry
                assert geometry['scrollWidth'] <= geometry['innerWidth'] + 1, geometry
                if width > 1000:
                    assert geometry['scrollHeight'] <= geometry['innerHeight'] + 1, geometry
                for name in ('#result-panel', '.copilot-card'):
                    panel = geometry['panels'][name]
                    assert panel and panel['scrollWidth'] <= panel['clientWidth'] + 1, (name, panel)
                for name, selector in RESPONSIVE_CONTROLS:
                    measured = geometry['controls'][name]
                    assert measured and measured['rect']['left'] >= -1 and measured['rect']['right'] <= width + 1, (name, measured)
                    control = page.locator(selector)
                    assert control.count() == 1 and control.is_visible() and control.is_enabled(), name
                    control.click(trial=True)
                    row['controls'].append(dict(name=name, visible=True, enabled=True, actionable=True))
                for name, selector in RESPONSIVE_CONTROLS:
                    if name not in ('module', 'inverter', 'dc-cable', 'ac-cable', 'wind-roughness'):
                        continue
                    control = page.locator(selector)
                    initial = control.input_value()
                    options = control.locator('option').evaluate_all('(nodes)=>nodes.filter(node=>!node.disabled).map(node=>node.value)')
                    alternative = next((value for value in options if value != initial), initial)
                    try:
                        control.select_option(alternative)
                        assert control.input_value() == alternative, name
                    finally:
                        control.select_option(initial)
                    assert control.input_value() == initial, name
                    row['select_roundtrips'].append(dict(name=name, original=initial, selected=alternative, restored=True))
                command = page.locator('#copilot-input')
                original = command.input_value()
                try:
                    command.fill('倾角12度')
                    assert command.input_value() == '倾角12度'
                finally:
                    command.fill(original)
                row['input_restored'] = command.input_value() == original
                assert row['input_restored']
                page.locator('#copilot-module').scroll_into_view_if_needed()
                record.screenshot(prefix + '-equipment-controls')
                page.locator('[data-action="copilot-send"]').scroll_into_view_if_needed()
                record.screenshot(prefix + '-command-controls')
                row['passed'] = True
            except Exception as error:
                row['error'] = f'{type(error).__name__}: {error}'
                try:
                    record.screenshot(prefix + '-FAILED')
                except Exception as screenshot_error:
                    row['screenshot_error'] = str(screenshot_error)
                raise
            finally:
                geometry_file = record.output / f'{prefix}-geometry.json'
                row['geometry_file'] = str(geometry_file)
                geometry_file.write_text(json.dumps(row, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                record.save()
    finally:
        page.set_viewport_size(RESPONSIVE_RESTORE_VIEWPORT.copy())
        page.evaluate("scrollTo(0,0);const panel=document.querySelector('#result-panel');if(panel)panel.scrollTop=0")
        detail['restored_viewport'] = page.viewport_size
        record.save()
    return detail


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8766')
    parser.add_argument('--installation-root', required=True, type=Path, help='Exact isolated QA installation served by this URL')
    parser.add_argument('--receipt', type=Path, help='acceptance_demo.py JSON receipt')
    parser.add_argument('--project', action='append', default=[], help='QA project id[:version]; repeat for multiple cases')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--park', help='Optional named QA park to open after the park list')
    parser.add_argument('--save-roof', action='store_true', help='Save one new QA U-shaped roof into the verified QA installation')
    parser.add_argument('--run-template', help='Select this saved QA roof on the real home page, run rules, approve exports, download DXF/XLSX and reload')
    parser.add_argument('--run-timeout-seconds', type=int, default=1200, help='Maximum wait for the real rule calculation (default: 1200)')
    parser.add_argument('--fonts-only', action='store_true', help='Inspect only home and actual embedded fonts; do not run projects, park or roof editing')
    args = parser.parse_args()
    if args.fonts_only and (args.receipt or args.project or args.run_template or args.save_roof or args.park):
        parser.error('--fonts-only cannot be combined with project, calculation, park or roof-edit arguments.')
    if args.run_template and not IDENTIFIER.fullmatch(args.run_template):
        parser.error('--run-template must be a saved roof identifier.')
    if args.run_timeout_seconds < 1:
        parser.error('--run-timeout-seconds must be positive.')
    selected = projects_from_args(args)
    args.base_url = args.base_url.rstrip('/')
    origin = urlsplit(args.base_url)
    if origin.scheme != 'http' or origin.hostname != '127.0.0.1' or origin.path or origin.query:
        parser.error('--base-url must use the app\'s 127.0.0.1 HTTP origin without a path or query.')
    args.installation_root = args.installation_root.resolve(strict=True)
    manifest = args.installation_root / 'build-manifest.json'
    if not manifest.is_file():
        parser.error('--installation-root is not an installed package (build-manifest.json missing).')
    status = read_json(args.base_url, 'status')
    agh_origin = (status.get('agh', {}).get('url') or '').rstrip('/')
    installation = status.get('installation') or {}
    if not installation.get('installed') or Path(installation.get('root', '')).resolve() != args.installation_root:
        parser.error('The live service does not identify the requested QA installation.')
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if installation.get('build') != digest:
        parser.error('The live service and QA build manifest do not match.')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    evidence = dict(schema='guangzhu.browser-acceptance/1', started_at=datetime.now(timezone.utc).isoformat(),
        base_url=args.base_url, installation=installation, projects=selected, viewport=dict(width=1600, height=1000),
        recording='original-speed Playwright viewport; headless Edge; no desktop capture',
        source_or_api_replacement=False, run_template=args.run_template, checks=[], pageerrors=[], requestfailed=[],
        http_errors=[], console=[], screenshots=[], downloads=[], ui_transactions=[], font_responses=[], font_diagnostics=[])
    with sync_playwright() as automation:
        browser = automation.chromium.launch(channel='msedge', headless=True, args=['--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport=evidence['viewport'], record_video_dir=str(args.output / 'video'),
                                      record_video_size=evidence['viewport'], accept_downloads=True)
        page = context.new_page()
        video = page.video
        page.set_default_timeout(45000)
        page.set_default_navigation_timeout(60000)
        record = Recorder(page, args.output, evidence)

        def home():
            page.goto(args.base_url + '/#new', wait_until='domcontentloaded')
            page.locator('.roofrow').first.wait_for()
            assert page.title() == '光筑'
            assert page.locator('[data-action="quick-run"]').is_enabled()
            assert page.locator('.preview a[href="#form"]').is_visible()
            record.screenshot('01-home')
            return dict(title=page.title(), roof_count=page.locator('.roofrow').count())
        record.step('home', home)
        record.step('embedded-fonts', lambda: verify_embedded_fonts(page, evidence, agh_origin))

        responsive_target = None
        if args.run_template:
            def quick_run_and_export():
                page.goto(args.base_url + '/#new', wait_until='domcontentloaded')
                roof = page.locator(f'[data-roof="{args.run_template}"]')
                roof.wait_for()
                roof.click()
                assert roof.get_attribute('aria-pressed') == 'true'
                roof_label = roof.inner_text()
                record.screenshot('01a-quick-run-selected-roof')
                timeout = args.run_timeout_seconds * 1000
                with page.expect_response(lambda response: response.request.method == 'POST'
                                          and urlsplit(response.url).path == '/api/projects/auto-run', timeout=timeout) as pending:
                    page.locator('[data-action="quick-run"]').click()
                response = pending.value
                submitted = response.request.post_data_json
                assert submitted['template'] == args.run_template
                assert submitted['overwrite_existing'] is False and submitted['review'] is False
                evidence['ui_transactions'].append(dict(action='quick-run', status=response.status,
                                                         path=urlsplit(response.url).path, template=submitted['template']))
                assert response.status == 200, f'Rule run returned HTTP {response.status}.'
                completed = response.json()
                identifier, version = completed['project_id'], completed['final_version']
                assert IDENTIFIER.fullmatch(identifier) and type(version) is int and version > 0
                expected_hash = f'#result/{quote(identifier)}?version={version}'
                page.wait_for_url(lambda url: urlsplit(url).fragment == expected_hash[1:], timeout=timeout)
                page.locator('[data-result-tab="结论"]').wait_for()
                wait_result_header(page, identifier, version)
                canvas = wait_canvas(page)
                result = read_json(args.base_url, f'projects/{quote(identifier)}/result?version={version}')
                assert result['project_id'] == identifier and result['version'] == version
                assert result['design']['version'] == version and result['design']['modules']
                design_hash = hashlib.sha256(json.dumps(result['design'], sort_keys=True).encode()).hexdigest()
                record.screenshot('01b-quick-run-result')

                export_prefix = f'/api/projects/{identifier}/exports/'
                with page.expect_response(lambda response: response.request.method == 'POST'
                                          and urlsplit(response.url).path == export_prefix + 'preview', timeout=timeout) as pending:
                    page.locator('[data-action="preview-export"]').first.click()
                response = pending.value
                evidence['ui_transactions'].append(dict(action='preview-export', status=response.status,
                                                         path=urlsplit(response.url).path, version=version))
                assert response.status == 200, f'Export preview returned HTTP {response.status}.'
                preview = response.json()
                assert preview.get('ready') is True and preview.get('approval_id'), 'Export precheck did not authorize an approval.'
                approve = page.locator('#local-export-panel [data-action="approve-export"]')
                approve.wait_for()
                assert f'v{version}' in approve.inner_text()
                record.screenshot('01c-export-precheck')
                with page.expect_response(lambda response: response.request.method == 'POST'
                                          and urlsplit(response.url).path == export_prefix + 'approve', timeout=timeout) as pending:
                    approve.click()
                response = pending.value
                evidence['ui_transactions'].append(dict(action='approve-export', status=response.status,
                                                         path=urlsplit(response.url).path, version=version))
                assert response.status == 200, f'Export approval returned HTTP {response.status}.'
                approved = response.json()
                assert approved.get('ok') is True and approved['version'] == version
                assert approved['approval']['kind'] == 'local-user' and approved['approval']['status'] == 'approved-once'
                assert response.request.post_data_json['confirmed'] is True
                page.get_by_role('heading', name=f'v{version} 已确认导出', exact=True).wait_for()
                assert f'v{version} · 已批准导出' in page.locator('.head > div > p').inner_text()
                record.screenshot('01d-export-approved')
                downloads = []
                for kind in ('dxf', 'xlsx'):
                    artifact = download_export(page, args.output, kind, identifier, version)
                    export_name = f'{"layout" if kind == "dxf" else "bom"}-v{version}.{kind}'
                    assert artifact['sha256'] == approved['files'][export_name], 'The download differs from its approved export manifest.'
                    downloads.append(artifact)
                    evidence['downloads'].append(artifact)
                    record.save()
                record.screenshot('01e-files-downloaded')

                page.reload(wait_until='domcontentloaded')
                page.locator('[data-result-tab="结论"]').wait_for()
                assert urlsplit(page.url).fragment == expected_hash[1:]
                wait_result_header(page, identifier, version)
                wait_canvas(page)
                reloaded = read_json(args.base_url, f'projects/{quote(identifier)}/result?version={version}')
                assert reloaded['project_id'] == identifier and reloaded['version'] == version
                assert hashlib.sha256(json.dumps(reloaded['design'], sort_keys=True).encode()).hexdigest() == design_hash
                record.screenshot('01f-same-version-reloaded')
                return dict(template_id=args.run_template, roof_label=roof_label, project_id=identifier, version=version,
                            modules=len(result['design']['modules']), canvas=canvas, design_sha256=design_hash,
                            reload_same_version=True, download_files=[row['filename'] for row in downloads])
            quick_run_check = record.step('quick-run-and-export', quick_run_and_export)
            if quick_run_check['passed']:
                responsive_target = (quick_run_check['project_id'], quick_run_check['version'])

        for index, (identifier, requested) in enumerate(selected.items(), 1):
            prefix = f'{index + 1:02}-{identifier}'

            def result_flow(identifier=identifier, requested=requested, prefix=prefix):
                suffix = f'?version={requested}' if requested else ''
                result = read_json(args.base_url, f'projects/{quote(identifier)}/result{suffix}')
                version = result['version']
                assert type(version) is int and version > 0
                assert result['project_id'] == identifier and result['design']['version'] == version
                page.goto(args.base_url + f'/#result/{quote(identifier)}?version={version}', wait_until='domcontentloaded')
                page.locator('[data-result-tab="结论"]').wait_for()
                wait_result_header(page, identifier, version)
                canvas = wait_canvas(page)
                record.screenshot(prefix + '-result-3d')
                page.locator('[data-scene-mode="heat"]').click()
                assert page.locator('[data-scene-mode="heat"]').get_attribute('aria-pressed') == 'true'
                wait_canvas(page)
                record.screenshot(prefix + '-heat')
                page.locator('[data-scene-mode="light"]').click()
                actual = result.get('scene') or {}
                expected_losses = [('年度平均遮挡损失', (actual.get('shading') or {}).get('summary', {}).get('avg_loss_pct')),
                    ('直流最大线路电压降', (actual.get('electrical') or {}).get('dc_drop_pct_max')),
                    ('交流最大线路电压降', (actual.get('electrical') or {}).get('ac_drop_pct_max'))]
                if result.get('evidence', {}).get('analysis', {}).get('status') != 'stale':
                    for label, expected in expected_losses:
                        cell = page.locator(f'[data-loss-metric="{label}"]')
                        if isinstance(expected, (int, float)):
                            assert math.isclose(number(cell.inner_text()), expected, abs_tol=.011)
                months = verify_months(page, result)
                record.screenshot(prefix + '-monthly')
                alternatives = [row['version'] for row in result.get('versions', []) if row.get('version') != version]
                history = None
                if alternatives:
                    history = min(alternatives)
                    page.locator(f'[data-version="{history}"]').first.click()
                    page.wait_for_function('(version)=>new URLSearchParams(location.hash.split("?")[1]).get("version")===String(version)', arg=history)
                    wait_result_header(page, identifier, history)
                    wait_canvas(page)
                    record.screenshot(prefix + '-historical-version')
                response = page.goto(args.base_url + f'/api/projects/{quote(identifier)}/report-html?version={version}',
                                     wait_until='domcontentloaded')
                assert response and response.status == 200
                toolbar = page.locator('.gz-report-toolbar')
                toolbar.wait_for()
                assert f'v{version}' in toolbar.inner_text() and result['project']['name'] in toolbar.inner_text()
                assert '当前设计、工程输入或完整计算记录缺失' not in page.locator('body').inner_text()
                record.screenshot(prefix + '-report')
                return dict(project_id=identifier, version=version, historical_version=history,
                            modules=len(result['design']['modules']), canvas=canvas, monthly=months, report_status=response.status)
            record.step(prefix, result_flow)

        def parks():
            page.goto(args.base_url + '/#park', wait_until='domcontentloaded')
            page.locator('[data-paction="new"]').wait_for()
            if args.park:
                page.locator('[data-pselect]').select_option(args.park)
                page.locator('[data-pfield="name"]').wait_for()
            assert '园区没能打开' not in page.locator('#view').inner_text()
            record.screenshot('90-park')
            return dict(park=args.park, body_characters=len(page.locator('#view').inner_text()))
        if not args.fonts_only:
            record.step('park', parks)

        def editor():
            page.goto(args.base_url + '/#roof', wait_until='domcontentloaded')
            page.locator('#re-svg').wait_for()
            page.locator('[data-re-rect="w"]').fill('60')
            page.locator('[data-re-rect="d"]').fill('36')
            page.locator('[data-re-rect="turn"]').fill('37')
            page.locator('[data-re-act="shape-u"]').click()
            page.locator('[data-re-act="cad-walkway-cross"]').first.click()
            page.wait_for_function("document.querySelectorAll('.re-item').length>0")
            record.screenshot('91-roof-editor-u-corridors')
            detail = dict(shape='u', rotation_deg=37, corridor_objects=page.locator('.re-item').count(), saved=False)
            if args.save_roof:
                name = 'QA浏览器验收-' + datetime.now().strftime('%H%M%S')
                page.locator('[data-re="name"]').fill(name)
                page.locator('[data-re-act="save"]').click()
                page.wait_for_url('**/#new')
                page.locator('.roofrow').filter(has_text=name).click()
                page.locator('.preview a[href^="#roof/"]').click()
                page.locator('[data-re="name"]').wait_for()
                assert page.locator('[data-re="name"]').input_value() == name
                detail.update(saved=True, roof_name=name, url=public_url(page.url))
                record.screenshot('92-roof-saved-reopened')
            return detail
        if not args.fonts_only:
            record.step('roof-editor', editor)
            def responsive_result():
                target = responsive_target or next(iter(selected.items()), None)
                assert target is not None, 'No completed quick-run or explicitly selected QA result is available.'
                return verify_responsive_result(page, record, args.base_url, *target)
            record.step('responsive-result', responsive_result)
        context.close()
        if video:
            video_path = args.output / 'acceptance-original-speed.webm'
            video.save_as(str(video_path))
            evidence['video'] = str(video_path)
        browser.close()
        local_origins = [args.base_url] + ([agh_origin] if agh_origin else [])
        app_errors = [row for row in evidence['http_errors'] if any(row['url'].startswith(origin + '/') for origin in local_origins)]
        failed_local_requests = [row for row in evidence['requestfailed'] if any(row['url'].startswith(origin + '/') for origin in local_origins)
                                 and row['error'] != 'net::ERR_ABORTED']
        evidence['passed'] = all(row['passed'] for row in evidence['checks']) and not evidence['pageerrors'] and not app_errors and not failed_local_requests
        evidence['finished_at'] = datetime.now(timezone.utc).isoformat()
        evidence['network_note'] = 'All request failures are recorded; aborted navigation requests are not automatically treated as application failures.'
        record.save()
    print(json.dumps(dict(passed=evidence['passed'], checks=len(evidence['checks']),
                         receipt=str(args.output / 'browser-acceptance.json'), video=evidence.get('video')), ensure_ascii=False))
    return 0 if evidence['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
