"""Offline archive inputs, real API/hash gates and an actual locally printed PDF."""
import hashlib
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
import pypdfium2 as pdfium
import pytest

from guangzhu import api, brief, park, park_report, park_store as store
from test_t29_store import workspace, payload

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {'host':'127.0.0.1:8765', 'origin':'http://127.0.0.1:8765'}
REAL_ENTRIES = api.park_entries


def archive(root, template, serial=1):
    source = store.read(root / 'data/parks/factory/roofs' / ('factory--' + template) / 'project.json')
    source['id'] = 'offline-' + template
    capture = root / 'runs' / ('gz-' + source['id'])
    cash = dict(capex_cny=100, payback_years=2, irr_pct=12, co2_t_per_year=3,
                cashflows=[dict(net_cny=v) for v in [-100, 50, 50, 50]], phases=[dict(capex_cny=10000)])
    summary = dict(modules=2, dc_kw=1.21, electrical=dict(dc_ac_ratio=1.21), yield_kwh=dict(p50=1400))
    design = dict(version=1, modules=[dict(corners=[[1, 1, 0], [2, 1, 0], [2, 3, 0], [1, 3, 0]], phase=1)])
    electrical = dict(inverter_count=1, per_inverter=[dict(inverter=1, inverter_id='offline-1', dc_kw=1.21, dc_ac_ratio=1.21)])
    values = {'project/project.json':source, 'project/analysis/v1/electrical.json':electrical}
    values.update({f'project/exports/v1/{name}.json':value for name, value in
                   [('summary', summary), ('economics', cash), ('design', design)]})
    for name, value in values.items():
        store.write(capture / name, value)
    meta = dict(project_id=source['id'], session='offline-session', ended_at=f'2026-10-06T00:00:0{serial}Z',
                artifacts={name: hashlib.sha256((capture / name).read_bytes()).hexdigest() for name in values})
    return dict(run_id=capture.name, version=1, showcase=False), capture, meta


@pytest.fixture
def parks_api(workspace, monkeypatch):
    monkeypatch.setattr(api, 'ROOT', workspace)
    monkeypatch.setattr(brief, 'ROOT', workspace)
    store.save(dict(payload(), transformer_kva=2, grid_kw=1, budget_cny=100), workspace)
    entries = [archive(workspace, 'low'), archive(workspace, 'high', 2)]
    monkeypatch.setattr(api, 'park_entries', lambda **kwargs: entries)
    monkeypatch.setattr(api, 'run_entries', lambda: [])
    return TestClient(api.app), workspace, entries


def test_named_summary_phases_ac_old_hash_and_api_boundary(parks_api):
    client, root, entries = parks_api
    result = client.get('/api/parks/factory').json()
    assert result['data']['all']['capex_cny'] == 200
    assert result['data']['phase1']['capex_cny'] == 100
    assert result['data']['all']['payback_years'] == 2
    assert result['data']['rated_ac_kw'] == 2
    assert result['data']['inverter_count'] == 2
    assert result['data']['risks'][0]['excess'] == pytest.approx(.4)
    assert result['data']['risks'][1]['excess'] == 1
    assert 'data-building="low"' in result['svg']
    assert client.post('/api/parks/factory/delete', json={}).status_code == 403
    result['park']['name'] = '改名厂区'
    assert client.post('/api/parks/factory/save', json=result['park'], headers=HEADERS).status_code == 200
    assert all('已考虑园区邻楼' in b['result']['shading_note'] for b in client.get('/api/parks/factory').json()['data']['buildings'])
    result['park']['buildings'][1]['x_m'] += 5
    assert client.post('/api/parks/factory/save', json=result['park'], headers=HEADERS).status_code == 200
    assert all('旧园区位置' in b['result']['shading_note'] for b in client.get('/api/parks/factory').json()['data']['buildings'])
    bad = entries[0][1] / 'project/exports/v1/economics.json'
    bad.write_text('{}', encoding='utf-8')
    result = client.get('/api/parks/factory').json()['data']
    assert result['all']['count'] == 1 and result['skipped'] == ['gz-offline-low']


def test_real_pdf_content_open_and_tamper(parks_api, monkeypatch, tmp_path):
    client, root, entries = parks_api
    response = client.post('/api/parks/factory/report', json={}, headers=HEADERS)
    assert response.status_code == 200, response.text
    pdf = park_report.verified_pdf('factory', root)
    document = pdfium.PdfDocument(str(pdf))
    text = '\n'.join(page.get_textpage().get_text_range() for page in document)
    for expected in ['园区总图', '每栋一行', '整体回本', '主要假设', 'gz-offline-low', 'gz-offline-high', '200']:
        assert expected in text
    assert len(document) >= 6
    opened = []
    monkeypatch.setattr(api.os, 'startfile', lambda path: opened.append(path))
    assert client.post('/api/parks/factory/open-report', json={}, headers=HEADERS).status_code == 200
    assert opened == [pdf]
    if os.environ.get('GUANGZHU_T29_CAPTURE') == '1':
        output = ROOT / 'reports/assets/T29'
        (output / 'park-proposal.pdf').write_bytes(pdf.read_bytes())
        (output / 'park-proposal.html').write_bytes(pdf.with_suffix('.html').read_bytes())
        (output / 'park-proposal-manifest.json').write_bytes((pdf.parent / 'manifest.json').read_bytes())
        document[1].render(scale=1.6).to_pil().save(output / 'park-proposal-page.png')
    document.close()
    pdf.write_bytes(b'%PDF-modified')
    assert client.post('/api/parks/factory/open-report', json={}, headers=HEADERS).status_code != 200
    assert len(opened) == 1


def test_pdf_failure_does_not_publish_latest(parks_api, monkeypatch):
    client, root, entries = parks_api
    monkeypatch.setattr(park_report, 'render_pdf', lambda *args: dict(status='html-only'))
    assert client.post('/api/parks/factory/report', json={}, headers=HEADERS).status_code != 200
    assert not (root / 'data/parks/factory/reports/latest.json').exists()


def test_cost_complete_sessions_currency_and_missing(monkeypatch, tmp_path):
    folders = [tmp_path / 'one', tmp_path / 'two']
    usages = {folders[0]: {'a':dict(billing_complete=True, costs=[dict(currency='USD', micros=100000)]),
                          'b':dict(billing_complete=True, costs=[dict(currency='USD', micros=200000)])},
              folders[1]: {'c':dict(billing_complete=True, costs=[dict(currency='USD', micros=500000)])}}
    monkeypatch.setattr(api, 'run_entries', lambda: [(p.name, p, 'design') for p in folders])
    monkeypatch.setattr(api, 'record', lambda p: (p, dict(ended_at=p.name), {}))
    monkeypatch.setattr(api, 'run_usage', lambda p: usages[p])
    assert api.park_cost() == dict(currency='USD', per_building=.4, samples=2)
    usages[folders[1]]['c']['costs'][0]['currency'] = 'CNY'
    assert api.park_cost() is None
    usages[folders[1]]['c']['billing_complete'] = False
    assert api.park_cost() == dict(currency='USD', per_building=.3, samples=1)
    usages[folders[0]]['a']['billing_complete'] = False
    assert api.park_cost() is None


def test_two_real_legacy_roofs_match_normalized_identity(tmp_path):
    import shutil
    for key in ('changzhou-demo', 'l-shape'):
        shutil.copytree(ROOT / 'data/demo/projects' / key, tmp_path / 'data/demo/projects' / key)
    saved = store.save(dict(id='legacy', name='旧记录核对', buildings=[dict(template=key, x_m=index * 100)
                       for index, key in enumerate(('changzhou-demo', 'l-shape'))]), tmp_path)
    entries = []
    for identifier, version in [('gz-t11-changzhou-006', 12), ('gz-t14-lshape-001', 3)]:
        capture, meta, verification = api.record(ROOT / 'runs' / identifier)
        assert all(check['passed'] for check in verification['checks'])
        entries.append((dict(run_id=identifier, version=version, showcase=False), capture, meta))
    rows = park.named(store.Park.model_validate(saved), entries, tmp_path)
    old = park.overview(entries)['buildings']
    assert rows['all'] == park.total(old)
    assert rows['all']['count'] == 2
    assert all(b['result']['shading_note'] == '原模板设计，未自动考虑园区邻楼' for b in rows['buildings'])


@pytest.mark.parametrize('state,accepted', [('pending', False), ('failed', False), ('wrong-version', False), ('passed', True), ('legacy', True)])
def test_named_final_review_gate_and_pdf_keeps_legacy_api(parks_api, monkeypatch, state, accepted):
    client, root, entries = parks_api
    monkeypatch.setattr(api, 'park_entries', REAL_ENTRIES)
    monkeypatch.setattr(api, 'run_entries', lambda: [(row['run_id'], capture, 'design') for row, capture, meta in entries])
    for row, capture, meta in entries:
        review = dict(requested=state != 'legacy', passed=state in ('passed', 'wrong-version'), mode='independent',
                      independent=[] if state == 'pending' else [dict(passed=state != 'failed', versions=[2 if state == 'wrong-version' else 1])])
        verification = dict(checks=[dict(passed=True)] * 4, verified_exports=[dict(version=1)], review=review,
                            passed=state in ('passed', 'wrong-version', 'legacy'))
        store.write(capture / 'run.json', meta)
        store.write(capture / 'verification.json', verification)
    assert len(client.get('/api/park').json()['buildings']) == 2
    assert client.get('/api/parks/factory').json()['data']['all']['count'] == (2 if accepted else 0)
    if state == 'failed':
        result = client.post('/api/parks/factory/report', json={}, headers=HEADERS)
        assert result.status_code == 200
        pdf = park_report.verified_pdf('factory', root)
        manifest = store.read(pdf.parent / 'manifest.json')
        assert manifest['data']['all']['count'] == 0
        assert all(b['result'] is None for b in manifest['data']['buildings'])


def test_tied_payback_uses_t22_name_order_for_phase_one(parks_api):
    client, root, entries = parks_api
    path = entries[1][1] / 'project/exports/v1/summary.json'
    summary = store.read(path)
    summary['dc_kw'] = 1.1
    store.write(path, summary)
    entries[1][2]['artifacts']['project/exports/v1/summary.json'] = hashlib.sha256(path.read_bytes()).hexdigest()
    old = park.overview(entries)['buildings']
    old_first = sorted(old, key=lambda row: row['payback_years'])[0]
    data = client.get('/api/parks/factory').json()['data']
    chosen = [b['name'] for b in data['buildings'] if b['result']['park_phase'] == 1]
    assert chosen == [old_first['name']] == ['high']
    assert data['phase1'] == park.total([old_first])
