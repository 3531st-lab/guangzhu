"""Preview/apply crosses the real storage, layout and HTTP boundaries."""
import json

import pytest
from fastapi.testclient import TestClient

from guangzhu import api, layout, project as storage
from guangzhu.config import API_ORIGIN, API_PORT, DATA_DIR


@pytest.fixture
def editable_project(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    payload = json.loads((DATA_DIR / 'demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    payload.update(id='manual-edit', designs=[])
    payload['roof'].update(outline=[[0,0],[24,0],[24,16],[0,16]], obstacles=[], keepouts=[], surroundings=[])
    project = storage.save(payload)
    storage.save_design(project.id, layout.generate_layout(project, {}), offline=True)
    return project


@pytest.fixture
def edit_client():
    with TestClient(api.app, base_url=API_ORIGIN, headers={'origin':API_ORIGIN}) as client:
        yield client


def preview_request(project):
    first = storage.load_design(project.id, 1).modules[0].id
    return dict(version=1, ops=[dict(op='lock_modules', module_ids=[first])], reason='东侧已确定，先锁定')


def test_preview_is_read_only_commit_is_versioned_and_replay_is_stale(editable_project, edit_client):
    project, client = editable_project, edit_client
    path = f'/api/projects/{project.id}/design-edits/'
    payload = preview_request(project)
    before = storage._path(project.id, 'project.json').read_bytes()
    response = client.post(path+'preview', json=payload)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview['impact']['available'] is False
    assert storage.next_version(project.id) == 2
    assert storage._path(project.id, 'project.json').read_bytes() == before
    commit = client.post(path+'apply', json=payload | dict(fingerprint=preview['fingerprint']))
    assert commit.status_code == 200, commit.text
    assert commit.json()['version'] == 2
    saved = storage.load_design(project.id, 2)
    assert saved.locked_module_ids == payload['ops'][0]['module_ids']
    assert saved.parent_version == 1
    replay = client.post(path+'apply', json=payload | dict(fingerprint=preview['fingerprint']))
    assert replay.status_code in (409, 422)
    assert storage.next_version(project.id) == 3
    forbidden = client.post(path+'preview', json=payload, headers={'origin':'https://elsewhere.test'})
    assert forbidden.status_code == 403


def test_detail_failure_is_explicit_and_never_reuses_old_metrics(editable_project, edit_client, monkeypatch):
    from guangzhu import design_edits
    def unavailable(*args):
        raise ValueError('missing weather fixture')
    monkeypatch.setattr(design_edits, 'calculate_impact', unavailable)
    response = edit_client.post(f'/api/projects/{editable_project.id}/design-edits/preview',
                                json=preview_request(editable_project) | dict(detailed=True))
    assert response.status_code == 200
    impact = response.json()['impact']
    assert impact['available'] is False and 'missing weather' in impact['reason']
    assert 'before' not in impact and 'after' not in impact
    assert storage.next_version(editable_project.id) == 2


def test_real_detailed_preview_calculates_both_designs_without_saving(editable_project, edit_client):
    payload = dict(version=1, ops=[dict(op='reflow_unlocked', params={'orientation':'landscape'})],
                   reason='比较横排对工程与投资的影响', detailed=True)
    response = edit_client.post(f'/api/projects/{editable_project.id}/design-edits/preview', json=payload)
    assert response.status_code == 200, response.text
    impact = response.json()['impact']
    assert impact['available'], impact
    assert impact['before']['annual_kwh'] > 0 and impact['after']['annual_kwh'] > 0
    assert impact['before']['capex_cny'] > 0 and impact['after']['capex_cny'] > 0
    assert isinstance(impact['after']['hard_failed'], int)
    assert storage.next_version(editable_project.id) == 2
    assert not storage._path(editable_project.id, 'analysis/v2').exists()


def test_string_geometry_change_counts_even_when_member_ids_are_unchanged(editable_project, edit_client, monkeypatch):
    from guangzhu import design_edits
    def impact(project, design):
        return dict(strings=[dict(id='S001', module_ids=['same-panel'],
                                 cable={'length_m':100 if design.version == 1 else 102})])
    monkeypatch.setattr(design_edits, 'calculate_impact', impact)
    payload = preview_request(editable_project) | dict(detailed=True)
    response = edit_client.post(f'/api/projects/{editable_project.id}/design-edits/preview',json=payload)
    assert response.status_code == 200
    assert response.json()['impact']['affected_strings'] == ['S001']
