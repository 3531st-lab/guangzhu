"""Bundled examples are reproducible and never replace a user's edited park."""
import json
from pathlib import Path
import shutil

from guangzhu.models import Project
from guangzhu import park_store, setup

ROOT = Path(__file__).parents[1]


def test_case_notes_match_inputs_and_do_not_claim_real_customers():
    catalogue = json.loads((ROOT / 'data/demo/cases.json').read_text(encoding='utf-8'))
    assert len(catalogue['cases']) == 4
    for case in catalogue['cases']:
        project = Project.model_validate_json((ROOT / 'data/demo/projects' / case['id'] / 'project.json').read_text(encoding='utf-8'))
        assert case['synthetic'] is True and '合成' not in project.name
        assert project.economics.self_use_ratio is None
        assert project.economics.monthly_kwh == case['monthly_load_kwh']
        assert project.economics.shifts == case['shifts']
        assert '不是该建筑测绘坐标' in project.economics.assumptions_note


def test_fresh_seed_has_neighbors_and_second_install_preserves_edits(tmp_path):
    catalogue = json.loads((ROOT / 'data/demo/cases.json').read_text(encoding='utf-8'))
    for case in catalogue['cases']:
        shutil.copytree(ROOT / 'data/demo/projects' / case['id'], tmp_path / 'data/demo/projects' / case['id'])
    seed = tmp_path / 'data/demo/park-seeds/taizhou-cmc-demo'
    seed.mkdir(parents=True)
    shutil.copyfile(ROOT / 'data/parks/taizhou-cmc-demo/park.json', seed / 'park.json')
    assert setup.seed_examples(tmp_path) == ['taizhou-cmc-demo']
    saved = park_store.load('taizhou-cmc-demo', tmp_path)
    assert len(saved.buildings) == 4
    roofs = list((tmp_path / 'data/parks/taizhou-cmc-demo/roofs').glob('*/project.json'))
    assert len(roofs) == 4
    assert all(Project.model_validate_json(p.read_text(encoding='utf-8')).park for p in roofs)
    file = tmp_path / 'data/parks/taizhou-cmc-demo/park.json'
    content = file.read_text(encoding='utf-8').replace('泰州产业场景组合园区', '用户修改的名称')
    file.write_text(content, encoding='utf-8')
    assert setup.seed_examples(tmp_path) == []
    assert file.read_text(encoding='utf-8') == content
