"""Independent regressions for incomplete records and native archived evidence."""
import hashlib
import json

from guangzhu import api
from guangzhu import project as storage
from guangzhu.analysis_inputs import project_signature
from guangzhu.design_evidence import capture
from test_api import local, payload  # noqa: F401
from test_design_evidence import write
from test_manual_modules import add, factory  # noqa: F401


def test_unknown_hard_rule_cannot_be_promoted_by_a_passing_advice(factory, tmp_path):
    project, _ = factory()
    base = tmp_path / 'projects' / project.id
    write(base, 'analysis/v1/rules.json', dict(items=[
        dict(id='G01', level='hard', status='unknown'),
        dict(id='S02', level='advice', status='pass')]))
    packet = capture(base, 1)
    assert packet['rules']['status'] == 'unknown'
    assert packet['rules']['hard_failed'] is None


def test_historical_null_metadata_does_not_break_the_version_result(factory, tmp_path):
    project, _ = factory()
    base = tmp_path / 'projects' / project.id
    write(base, 'analysis/v1/shading.json', dict(version=1, metadata=None))
    write(base, 'analysis/v1/economics.json', dict(analysis_metadata=None))
    packet = capture(base, 1)
    assert packet['available'] is True
    assert packet['analysis']['input_binding'] == 'unrecorded'
    assert packet['analysis']['elapsed_seconds'] is None
    assert packet['weather']['source'] is None


def test_sanitized_export_preserves_archive_integrity_without_claiming_original_match(factory, tmp_path):
    project, _ = factory()
    base = tmp_path / 'projects' / project.id
    actual = write(base, 'exports/v1/economics.json', dict(cost='redacted'))
    original = hashlib.sha256(b'original export economics').hexdigest()
    write(base, 'exports/v1/manifest.json', dict(version=1, files={'economics.json': original},
        snapshot_note='files.sha256属于原导出件；脱敏快照的实际SHA256以run.json的artifacts为准。'))
    archive_hashes = {'project/' + path.relative_to(base).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in base.rglob('*') if path.is_file()}
    packet = capture(base, 1, archive_hashes=archive_hashes)
    source = next(row for row in packet['sources'] if row['path'] == 'exports/v1/economics.json')
    assert source['sha256'] == actual
    assert source['integrity'] == 'verified'
    assert source['manifest_match'] is False
    assert packet['export']['status'] == 'snapshot'
    # A real change to the sanitized artifact must still fail archive integrity.
    write(base, 'exports/v1/economics.json', dict(cost='changed after capture'))
    changed = capture(base, 1, archive_hashes=archive_hashes)
    assert changed['export']['status'] == 'mismatch'


def test_separate_review_capture_is_in_evidence_and_tampered_review_is_excluded(local):
    client, root, project, _, _ = local
    assert client.post('/api/runs/finish', json=payload()).status_code == 200
    review = dict(version=2, verdict='approve', reviewer_model='agnes-3.0-flash', findings=[])
    api.evidence.write_json(project / 'reviews/v2-independent.json', review)
    response = client.post('/api/runs/finish', json=payload(review_session_id='review-session'))
    assert response.status_code == 200, response.text
    result = response.json()['result']
    assert result['reviews'] == [review]
    assert result['evidence']['review']['status'] == 'recorded'
    assert result['evidence']['review']['count'] == 1
    assert result['evidence']['review']['records'][0]['verdict'] == 'approve'
    folder = root / 'runs/gz-changzhou-demo'
    meta = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
    captured = folder / meta['review_capture'] / 'project/reviews/v2-independent.json'
    api.evidence.write_json(captured, review | dict(verdict='changed'))
    after = client.get('/api/runs/gz-changzhou-demo').json()['result']['evidence']
    assert after['review']['status'] == 'missing'
    assert after['review']['count'] == 0


def test_result_disables_diagnostic_fixes_after_engineering_inputs_change(factory, tmp_path, monkeypatch):
    project, blank = factory()
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    design = add(project, blank, [dict(center=[6, 7])])
    base = tmp_path / 'projects' / project.id
    version = design.version
    digest = hashlib.sha256((base / f'designs/v{version}.json').read_bytes()).hexdigest()
    metadata = dict(design_sha256=digest, project_inputs_sha256=project_signature(project))
    write(base, f'analysis/v{version}/shading.json', dict(version=version, metadata=metadata,
        modules=[dict(id=design.modules[0].id, total_loss_pct=9, main_cause='obstacle')]))
    write(base, f'analysis/v{version}/economics.json', dict(analysis_metadata=metadata))
    write(base, f'analysis/v{version}/rules.json', dict(items=[
        dict(id='S01', level='hard', status='fail', value=9, limit=8)]))
    current = api.result_data(project.id, version)
    assert current['diagnostics']['available'] is True
    assert current['diagnostics']['issues'][0]['fix'] is not None
    changed = storage.load(project.id)
    changed.roof.height_m += 1
    storage.save(changed)
    stale = api.result_data(project.id, version)
    assert stale['evidence']['analysis']['status'] == 'stale'
    assert stale['diagnostics']['available'] is False
    assert stale['diagnostics']['issues'] == []
