"""Local, single-use approval is bound to the exact version and computed inputs."""
import hashlib
import json

from fastapi.testclient import TestClient
import pytest

from guangzhu import analysis, api, mcp_actions, project as storage
from guangzhu.config import API_ORIGIN
from guangzhu.report import view
from test_manual_modules import factory, add  # noqa: F401


@pytest.fixture
def local_case(factory, tmp_path, monkeypatch):
    record, blank = factory()
    design = add(record, blank, [dict(center=[7, 7]), dict(center=[15, 7]), dict(center=[23, 7]),
                                 dict(center=[7, 15]), dict(center=[15, 15]), dict(center=[23, 15])])
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    with TestClient(api.app, base_url=API_ORIGIN, headers={'origin': API_ORIGIN}) as client:
        yield record, design, client


def prepare(record, design, client):
    response = client.post(f'/api/projects/{record.id}/exports/preview', json=dict(version=design.version))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['ready'] is True, result
    assert result['review']['status'] == 'unverified'
    return result


def test_missing_download_has_clear_error_and_never_generates_files(local_case, monkeypatch):
    record, design, client = local_case
    monkeypatch.setattr(mcp_actions, '_export', lambda *_a, **_k: pytest.fail('GET cannot export'))
    for kind in ('dxf', 'xlsx', 'drawing-pdf'):
        response = client.get(f'/api/projects/{record.id}/download/{kind}?version={design.version}')
        assert response.status_code == 409, (kind, response.text)
        assert '批准' in response.text
    assert not storage._path(record.id, 'exports').exists()


def test_local_approval_generates_valid_package_once_and_download_checks_hash(local_case):
    record, design, client = local_case
    prepared = prepare(record, design, client)
    assert not storage._path(record.id, f'exports/v{design.version}').exists()
    payload = dict(version=design.version, approval_id=prepared['approval_id'], confirmed=True)
    rejected = client.post(f'/api/projects/{record.id}/exports/approve', json=payload | dict(confirmed=False))
    assert rejected.status_code == 400  # Existing API validation convention; explicit confirmation is required.
    response = client.post(f'/api/projects/{record.id}/exports/approve', json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['approval']['kind'] == 'local-user' and result['approval']['status'] == 'approved-once'
    assert result['version'] == design.version
    from openpyxl import load_workbook
    from guangzhu.local_exports import export_evidence
    base = storage._path(record.id)
    assert export_evidence(base, design.version)['status'] == 'verified'
    electric = json.loads((base / f'analysis/v{design.version}/electrical.json').read_text(encoding='utf-8'))
    economy = json.loads((base / f'analysis/v{design.version}/economics.json').read_text(encoding='utf-8'))
    book = load_workbook(base / f'exports/v{design.version}/bom-v{design.version}.xlsx', data_only=True)
    materials = list(book['材料清单'].values)
    cable_rows = [row for row in materials[1:] if row[0] in ('直流电缆', '交流电缆')]
    assert len(cable_rows) == len(electric['cables']['summary'])
    for cable in electric['cables']['summary']:
        row = next(row for row in cable_rows if row[11] == cable['cable_id'])
        priced = next(item for item in economy['costs']['items'] if item.get('cable_id') == cable['cable_id'])
        assert row[2] == cable['cable_model'] and cable['material'] in row[7]
        assert row[8] == pytest.approx(cable['unit_price_cny_m'])
        assert row[9] == pytest.approx(priced['subtotal_cny'])
    response = client.get(f'/api/projects/{record.id}/download/dxf?version={design.version}')
    assert response.status_code == 200
    expected = result['files'][f'layout-v{design.version}.dxf']
    assert hashlib.sha256(response.content).hexdigest() == expected
    report = client.get(f'/api/projects/{record.id}/report-html?version={design.version}')
    assert '本地用户已批准一次初步方案文件导出' in report.text
    project = storage.load(record.id)
    project.economics.price_self_cny_kwh = .91
    storage.save(project)
    analysis.analyze(record.id, design.version, offline=True)
    report = client.get(f'/api/projects/{record.id}/report-html?version={design.version}')
    assert '候选方案；尚未批准导出' in report.text
    assert '本地用户已批准一次初步方案文件导出' not in report.text
    replay = client.post(f'/api/projects/{record.id}/exports/approve', json=payload)
    assert replay.status_code == 409
    target = storage._path(record.id, f'exports/v{design.version}/layout-v{design.version}.dxf')
    target.write_bytes(target.read_bytes() + b'\nchanged')
    assert client.get(f'/api/projects/{record.id}/download/dxf?version={design.version}').status_code == 409


@pytest.mark.parametrize('changed', ['project', 'analysis'])
def test_approval_rejects_changed_inputs_or_analysis(local_case, changed):
    record, design, client = local_case
    prepared = prepare(record, design, client)
    if changed == 'project':
        project = storage.load(record.id)
        project.roof.load_capacity_kn_m2 = .4
        storage.save(project)
    else:
        path = storage._path(record.id, f'analysis/v{design.version}/rules.json')
        path.write_bytes(path.read_bytes() + b'\n')
    response = client.post(f'/api/projects/{record.id}/exports/approve', json=dict(
        version=design.version, approval_id=prepared['approval_id'], confirmed=True))
    assert response.status_code == 409, response.text
    assert not storage._path(record.id, 'exports').exists()


def test_hard_failure_preview_cannot_issue_an_approval(local_case):
    record, design, client = local_case
    project = storage.load(record.id)
    project.requirements.structured.capacity_kw_min = 100
    storage.save(project)
    response = client.post(f'/api/projects/{record.id}/exports/preview', json=dict(version=design.version))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['ready'] is False and not result.get('approval_id')
    assert result['checks']['hard_failed'] > 0
    assert not storage._path(record.id, 'exports').exists()


def test_legacy_json_only_package_is_preserved_and_cannot_promise_missing_cad(local_case):
    record, design, client = local_case
    analysis.analyze(record.id, design.version, offline=True)
    base = storage._path(record.id)
    folder = base / f'exports/v{design.version}'
    folder.mkdir(parents=True)
    files = {}
    for name in ('design', 'summary', 'rules', 'economics'):
        source = base / (f'designs/v{design.version}.json' if name == 'design'
                         else f'analysis/v{design.version}/{name}.json')
        target = folder / f'{name}.json'
        target.write_bytes(source.read_bytes())
        files[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    (folder / 'manifest.json').write_text(json.dumps(dict(version=design.version, files=files)), encoding='utf-8')
    before = {path.name: path.read_bytes() for path in folder.iterdir()}
    result = client.post(f'/api/projects/{record.id}/exports/preview', json=dict(version=design.version)).json()
    assert result['ready'] is False and result['approval_id'] is None
    assert '历史导出包' in result['reason']
    assert {path.name: path.read_bytes() for path in folder.iterdir()} == before


def test_report_uses_requested_version_and_only_matching_unverified_reviews(local_case, monkeypatch):
    record, design, client = local_case
    analysis.analyze(record.id, design.version, offline=True)
    next_design = design.model_copy(deep=True)
    next_design.version, next_design.parent_version = 3, design.version
    storage.save_design(record.id, next_design, offline=True)
    analysis.analyze(record.id, 3, offline=True)
    folder = storage._path(record.id, 'exports/v3')
    folder.mkdir(parents=True)
    (folder / 'manifest.json').write_text(json.dumps(dict(version=3, files={})), encoding='utf-8')
    mcp_actions._record_review(record.id, 3, 'other-version-review', 'approve', [])
    mcp_actions._record_review(record.id, design.version, 'unverified-review', 'approve', [])
    captured = {}

    def capture(context):
        captured.update(context)
        return '<html><body>context probe</body></html>'

    monkeypatch.setattr(view, 'render', capture)
    response = client.get(f'/api/projects/{record.id}/report-html?version={design.version}')
    assert response.status_code == 200, response.text
    assert captured['version'] == design.version
    assert captured['design']['version'] == design.version
    assert captured['review'] is None
    assert captured['review_mode'] == 'none'
    assert captured['verification'].get('passed') is not True
    assert captured['evidence']['analysis']['completion_status'] == 'matched'


def test_actual_candidate_report_is_honest_and_stale_analysis_is_not_reused(local_case):
    record, design, client = local_case
    analysis.analyze(record.id, design.version, offline=True)
    mcp_actions._record_review(record.id, design.version, 'guangzhu-agent-auditor', 'approve', [])
    response = client.get(f'/api/projects/{record.id}/report-html?version={design.version}')
    assert response.status_code == 200, response.text
    assert '候选方案' in response.text and '尚未独立审核' in response.text
    assert '审核员结论通过' not in response.text and '设计院级' not in response.text
    assert '共 18 页' not in response.text
    project = storage.load(record.id)
    project.roof.parapet_height_m = 2
    storage.save(project)
    response = client.get(f'/api/projects/{record.id}/report-html?version={design.version}')
    assert response.status_code == 200
    assert '需要重新计算' in response.text
    assert '基准年发电估算' not in response.text


def test_default_result_honors_valid_local_selection_and_ignores_missing_versions(local_case):
    record, design, _client = local_case
    newer = design.model_copy(deep=True)
    newer.version, newer.parent_version = 3, design.version
    storage.save_design(record.id, newer, offline=True)
    choice = storage._path(record.id, 'local-selection.json')
    choice.write_text(json.dumps(dict(version=design.version, source='rule-auto')), encoding='utf-8')
    selected = api.result_data(record.id)
    assert selected['version'] == design.version
    assert selected['selected_version'] is None  # A local choice is not an export or approval.
    assert api.result_data(record.id, 3)['version'] == 3
    for invalid in (999, True, '2'):
        choice.write_text(json.dumps(dict(version=invalid)), encoding='utf-8')
        assert api.result_data(record.id)['version'] == 3


def test_local_report_only_uses_matching_hashed_independent_snapshot(local_case):
    from guangzhu.analysis_inputs import project_signature
    from guangzhu.report.local import _verified_review
    record, design, _client = local_case
    base = storage._path(record.id)
    result = dict(project_id=record.id, version=design.version, design=json.loads(design.model_dump_json()),
        run_id='verified-run', verification=dict(review=dict(passed=True, mode='independent', versions=[design.version])),
        evidence=dict(analysis=dict(project_inputs_sha256=project_signature(record.model_dump(mode='json')))))
    assert _verified_review(base, result) is None
    run = base.parent.parent / 'runs/verified-run'
    captured = run / 'reviews/source'
    files = {'project/project.json': record.model_dump(mode='json'),
             f'project/designs/v{design.version}.json': result['design'],
             f'project/reviews/v{design.version}-source.json': dict(version=design.version, verdict='revise', reviewer_model='independent')}
    hashes = {}
    for name, value in files.items():
        path = captured / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (captured / 'run.json').write_text(json.dumps(dict(project_id=record.id, artifacts=hashes)), encoding='utf-8')
    (run / 'run.json').write_text(json.dumps(dict(review_capture='reviews/source')), encoding='utf-8')
    assert _verified_review(base, result)['verdict'] == 'revise'
    altered = dict(result, design=dict(result['design'], reason='changed since review'))
    assert _verified_review(base, altered) is None
    altered = dict(result, evidence=dict(analysis=dict(project_inputs_sha256='0' * 64)))
    assert _verified_review(base, altered) is None
    path = captured / f'project/reviews/v{design.version}-source.json'
    path.write_bytes(path.read_bytes() + b' ')
    assert _verified_review(base, result) is None
