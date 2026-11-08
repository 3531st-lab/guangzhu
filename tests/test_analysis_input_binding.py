"""A saved design does not make changed roof/weather/economic inputs identical."""
import json

from guangzhu import analysis, project as storage
from test_manual_modules import factory, add


def test_input_signature_tracks_engine_revision_and_catalog_content(factory, monkeypatch, tmp_path):
    from guangzhu import analysis_inputs
    project, _ = factory()
    monkeypatch.setattr(analysis_inputs, 'CATALOG_DIR', tmp_path)
    cable = tmp_path / 'cables.csv'
    cable.write_text('id,ampacity\nexample,210\n', encoding='utf-8')
    before = analysis_inputs.project_signature(project)
    cable.write_text('id,ampacity\nexample,190\n', encoding='utf-8')
    after = analysis_inputs.project_signature(project)
    assert after != before
    monkeypatch.setattr(analysis_inputs, 'ENGINE_REVISION', 'next-reviewed-engine')
    assert analysis_inputs.project_signature(project) != after


def test_engineering_input_signature_ignores_version_registry_but_tracks_real_inputs(factory):
    from guangzhu.analysis_inputs import project_signature
    project, _ = factory()
    before = project_signature(project)
    metadata_only = project.model_copy(deep=True)
    metadata_only.designs.append('v99.json')
    metadata_only.name = '不同展示名称'
    assert project_signature(metadata_only) == before
    for field, value in [('height_m', 12), ('parapet_height_m', 2), ('load_capacity_kn_m2', .25)]:
        changed = project.model_copy(deep=True)
        setattr(changed.roof, field, value)
        assert project_signature(changed) != before
    changed = project.model_copy(deep=True)
    changed.site.lat += .1
    assert project_signature(changed) != before


def test_analysis_reuses_only_same_design_and_current_input_signature(factory):
    project, blank = factory()
    design = add(project, blank, [dict(center=[6, 7]), dict(center=[14, 7]), dict(center=[22, 7]),
                                  dict(center=[6, 13]), dict(center=[14, 13]), dict(center=[22, 13])])
    version = design.version
    analysis.analyze(project.id, version, offline=True)
    directory = storage._path(project.id, f'analysis/v{version}')
    first = json.loads((directory / 'economics.json').read_text(encoding='utf-8'))
    signature = first['analysis_metadata']['project_inputs_sha256']
    analysis.analyze(project.id, version, offline=True)
    again = json.loads((directory / 'economics.json').read_text(encoding='utf-8'))
    assert again['analysis_metadata']['shading_reused'] is True
    changed = storage.load(project.id)
    changed.roof.parapet_height_m = 3
    storage.save(changed)
    analysis.analyze(project.id, version, offline=True)
    final = json.loads((directory / 'economics.json').read_text(encoding='utf-8'))
    shadows = json.loads((directory / 'shading.json').read_text(encoding='utf-8'))
    assert final['analysis_metadata']['shading_reused'] is False
    assert final['analysis_metadata']['project_inputs_sha256'] != signature
    assert shadows['metadata']['project_inputs_sha256'] == final['analysis_metadata']['project_inputs_sha256']
    completion = json.loads((directory / 'completion.json').read_text(encoding='utf-8'))
    assert completion['version'] == version
    assert completion['project_inputs_sha256'] == final['analysis_metadata']['project_inputs_sha256']
    from guangzhu.design_evidence import capture
    before = capture(directory.parents[1], version)
    assert before['analysis']['completion_status'] == 'matched'
    # If only one output is changed (e.g. an interrupted rewrite), the old
    # completion manifest must not promote the mixed files to a current result.
    checked = json.loads((directory / 'rules.json').read_text(encoding='utf-8'))
    checked['items'][0]['status'] = 'pass' if checked['items'][0]['status'] != 'pass' else 'fail'
    (directory / 'rules.json').write_text(json.dumps(checked), encoding='utf-8')
    stale = capture(directory.parents[1], version)
    assert stale['analysis']['completion_status'] == 'mismatch'
    assert stale['analysis']['status'] == stale['rules']['status'] == 'stale'
