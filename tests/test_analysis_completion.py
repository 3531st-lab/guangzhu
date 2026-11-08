"""Independent publication-failure and interleaving checks for analysis evidence."""
import hashlib
import json

import pytest

from guangzhu import analysis, analysis_inputs, project as storage
from guangzhu.design_evidence import capture
from test_manual_modules import add, factory  # noqa: F401


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def completed_inputs(factory, tmp_path):
    project, _ = factory()
    base = tmp_path / 'projects' / project.id
    directory = base / 'analysis/v1'
    directory.mkdir(parents=True, exist_ok=True)
    design_hash = digest(base / 'designs/v1.json')
    input_hash = analysis_inputs.project_signature(project)
    expected = {}
    for name in analysis_inputs.ANALYSIS_FILES:
        result = dict(version=1)
        binding = dict(design_sha256=design_hash, project_inputs_sha256=input_hash)
        if name == 'shading.json':
            result['metadata'] = binding
        if name == 'economics.json':
            result['analysis_metadata'] = binding | dict(completion_required=True)
        if name == 'rules.json':
            result['items'] = [dict(id='G01', level='hard', status='pass')]
        path = directory / name
        path.write_text(json.dumps(result), encoding='utf-8')
        expected[name] = digest(path)
    return base, directory, design_hash, input_hash, expected


def test_modern_outputs_without_completion_cannot_claim_current_rule_success(completed_inputs):
    base, directory, _, _, _ = completed_inputs
    packet = capture(base, 1)
    assert packet['analysis']['input_binding'] == 'matched'
    assert packet['analysis']['completion_status'] == 'mismatch'
    assert packet['analysis']['status'] == packet['rules']['status'] == 'stale'
    assert packet['rules']['hard_failed'] is None
    # True historical files remain explicitly unknown about batch completeness.
    path = directory / 'economics.json'
    legacy = json.loads(path.read_text(encoding='utf-8'))
    legacy['analysis_metadata'].pop('completion_required')
    path.write_text(json.dumps(legacy), encoding='utf-8')
    assert capture(base, 1)['analysis']['completion_status'] == 'unrecorded'


def test_another_writer_cannot_publish_mixed_outputs_as_its_own_complete_batch(completed_inputs):
    base, directory, design_hash, input_hash, expected = completed_inputs
    analysis_inputs.write_completion(directory, 1, design_hash, input_hash, expected_hashes=expected)
    previous = (directory / 'completion.json').read_bytes()
    assert capture(base, 1)['analysis']['completion_status'] == 'matched'
    # Writer B replaces one physical result after A wrote and hashed its output.
    (directory / 'structure.json').write_text(json.dumps(dict(version=1, added_kn_m2=999)), encoding='utf-8')
    with pytest.raises(ValueError):
        analysis_inputs.write_completion(directory, 1, design_hash, input_hash, expected_hashes=expected)
    assert (directory / 'completion.json').read_bytes() == previous
    assert not list(directory.glob('.completion-*.tmp'))
    packet = capture(base, 1)
    assert packet['analysis']['completion_status'] == 'mismatch'
    assert packet['analysis']['status'] == packet['rules']['status'] == 'stale'


def test_atomic_replace_failure_preserves_previous_manifest_and_removes_temporary(completed_inputs, monkeypatch):
    base, directory, design_hash, input_hash, expected = completed_inputs
    analysis_inputs.write_completion(directory, 1, design_hash, input_hash, expected_hashes=expected)
    previous = (directory / 'completion.json').read_bytes()
    path = directory / 'electrical.json'
    path.write_text(json.dumps(dict(version=1, dc_kw=100)), encoding='utf-8')
    next_expected = expected | {'electrical.json': digest(path)}

    def fail_replace(*_args):
        raise OSError('injected atomic replacement failure')

    monkeypatch.setattr(analysis_inputs.os, 'replace', fail_replace)
    with pytest.raises(OSError, match='injected'):
        analysis_inputs.write_completion(directory, 1, design_hash, input_hash, expected_hashes=next_expected)
    assert (directory / 'completion.json').read_bytes() == previous
    assert not list(directory.glob('.completion-*.tmp'))
    assert capture(base, 1)['analysis']['status'] == 'stale'


def test_reused_shading_keeps_original_json_bytes_in_the_completion_manifest(factory, monkeypatch):
    project, blank = factory()
    design = add(project, blank, [dict(center=[6, 7]), dict(center=[14, 7]), dict(center=[22, 7]),
                                  dict(center=[6, 13]), dict(center=[14, 13]), dict(center=[22, 13])])
    analysis.analyze(project.id, design.version, offline=True)
    directory = storage._path(project.id, f'analysis/v{design.version}')
    path = directory / 'shading.json'
    shading = json.loads(path.read_text(encoding='utf-8'))
    original_bytes = ('\n' + json.dumps(shading, ensure_ascii=False, indent=4) + '\n\n').encode('utf-8')
    path.write_bytes(original_bytes)

    def unexpected_recalculation(*_args, **_kwargs):
        pytest.fail('Identical shading inputs should reuse the cached result regardless of JSON whitespace')

    monkeypatch.setattr(analysis.shading, 'analyze', unexpected_recalculation)
    analysis.analyze(project.id, design.version, offline=True)
    assert path.read_bytes() == original_bytes
    cash = json.loads((directory / 'economics.json').read_text(encoding='utf-8'))
    assert cash['analysis_metadata']['shading_reused'] is True
    completion = json.loads((directory / 'completion.json').read_text(encoding='utf-8'))
    assert completion['files']['shading.json'] == hashlib.sha256(original_bytes).hexdigest()
    assert capture(directory.parents[1], design.version)['analysis']['completion_status'] == 'matched'
