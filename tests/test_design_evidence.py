"""Evidence cards report recorded facts without promoting missing data to success."""
import hashlib
import json

import pytest

from guangzhu import api
from test_manual_modules import factory


def write(base, relative, value):
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_missing_evidence_keeps_zero_and_unknown_distinct(factory, tmp_path):
    from guangzhu.design_evidence import capture
    project, design = factory()
    base = tmp_path / 'projects' / project.id
    packet = capture(base, 1)
    assert packet['version'] == 1
    assert packet['model']['modules'] == 0
    assert packet['analysis']['status'] == 'missing'
    assert packet['rules']['hard_failed'] is None
    assert packet['review']['status'] == 'missing'
    assert packet['export']['status'] == 'missing'
    assert packet['usage']['sessions'] == []
    assert packet['usage']['manual_minutes'] is None
    assert packet['assumptions']['load_verified'] is False


def test_sources_and_binding_match_actual_bytes_and_fail_on_changed_inputs(factory, tmp_path):
    from guangzhu.design_evidence import capture
    from guangzhu.analysis_inputs import project_signature
    project, design = factory()
    base = tmp_path / 'projects' / project.id
    design_hash = hashlib.sha256((base / 'designs/v1.json').read_bytes()).hexdigest()
    signature = project_signature(project)
    write(base, 'analysis/v1/shading.json', dict(version=1, modules=[], metadata=dict(
        design_sha256=design_hash, project_inputs_sha256=signature, weather=dict(source='nasa', year=2023))))
    write(base, 'analysis/v1/electrical.json', dict(version=1, strings=[]))
    write(base, 'analysis/v1/structure.json', {})
    write(base, 'analysis/v1/economics.json', dict(analysis_metadata=dict(
        elapsed_seconds=0, design_sha256=design_hash, project_inputs_sha256=signature)))
    write(base, 'analysis/v1/summary.json', dict(version=1, rules=dict(hard_failed=0)))
    write(base, 'analysis/v1/rules.json', dict(items=[dict(id='S01', level='hard', status='fail')], hard_failed=0))
    packet = capture(base, 1)
    assert packet['analysis']['status'] == 'recorded'
    assert packet['analysis']['input_binding'] == 'matched'
    assert packet['analysis']['elapsed_seconds'] == 0
    assert packet['rules']['hard_failed'] == 1  # actual items outrank a stale summary count
    assert packet['rules']['status'] == 'fail'
    assert packet['weather']['year'] == 2023
    assert next(row for row in packet['sources'] if row['path'] == 'designs/v1.json')['sha256'] == design_hash
    changed = json.loads((base / 'project.json').read_text(encoding='utf-8'))
    changed['roof']['height_m'] += 1
    write(base, 'project.json', changed)
    stale = capture(base, 1)
    assert stale['analysis']['status'] == 'stale'
    assert stale['analysis']['input_binding'] == 'mismatch'
    assert stale['rules']['status'] == 'stale'


def test_wrong_version_and_unverified_archive_do_not_count_as_evidence(factory, tmp_path):
    from guangzhu.design_evidence import capture
    project, _ = factory()
    base = tmp_path / 'projects' / project.id
    write(base, 'analysis/v1/shading.json', dict(version=2, metadata={}))
    write(base, 'analysis/v1/rules.json', dict(items=[dict(id='S01', status='pass', level='hard')]))
    assert capture(base, 1)['analysis']['status'] == 'stale'
    archived = capture(base, 1, archive_hashes={})
    assert archived['analysis']['status'] != 'recorded'
    assert archived['rules']['hard_failed'] is None
    assert all(row['integrity'] in ('unverified', 'missing') for row in archived['sources'])


def test_export_manifest_hashes_and_exact_version_reviews(factory, tmp_path):
    from guangzhu.design_evidence import capture
    project, _ = factory()
    base = tmp_path / 'projects' / project.id
    write(base, 'reviews/v1-independent.json', dict(version=1, verdict='approve', reviewer_model='reviewer'))
    write(base, 'reviews/v1-wrong.json', dict(version=2, verdict='approve'))
    output = base / 'exports/v1/layout.dxf'
    output.parent.mkdir(parents=True)
    output.write_text('real drawing contents', encoding='utf-8')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    write(base, 'exports/v1/manifest.json', dict(version=1, files={'layout.dxf': digest}))
    packet = capture(base, 1)
    assert packet['review']['count'] == 1
    assert packet['review']['status'] == 'recorded'  # a review file is not independent-session proof
    assert packet['export']['status'] == 'matched'
    output.write_text('changed', encoding='utf-8')
    assert capture(base, 1)['export']['status'] == 'mismatch'


def test_export_path_cannot_read_outside_its_version_directory(factory, tmp_path):
    from guangzhu.design_evidence import capture
    project, _ = factory()
    base = tmp_path / 'projects' / project.id
    secret = tmp_path / 'private.txt'
    secret.write_text('private', encoding='utf-8')
    write(base, 'exports/v1/manifest.json', dict(version=1, files={'../../../private.txt': 'a' * 64}))
    packet = capture(base, 1)
    assert packet['export']['status'] == 'invalid'
    assert 'private' not in json.dumps(packet['sources'])


def test_session_usage_is_separate_from_this_version_compute_and_manual_cost(factory, tmp_path):
    from guangzhu.design_evidence import capture
    project, _ = factory()
    packet = capture(tmp_path / 'projects' / project.id, 1, usage_by_session={'run1': dict(
        session_id='run1', model_requests=0, started_at='2026-11-03T08:00:00Z', ended_at='2026-11-03T08:01:30Z',
        tokens=dict(input=0, output=None), costs=[dict(currency='USD', micros=0)], billing_complete=False)})
    session = packet['usage']['sessions'][0]
    assert session['elapsed_seconds'] == 90
    assert session['model_requests'] == 0
    assert session['tokens']['output'] is None
    assert session['costs'] == [dict(currency='USD', micros=0)]
    assert session['billing_complete'] is False
    assert packet['usage']['manual_minutes'] is None
    assert '会话' in packet['usage']['note']
