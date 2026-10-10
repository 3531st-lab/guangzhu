"""Layered what-if reuse retains demand, site, tariff and source invalidation."""
import json

import pytest

from guangzhu import analysis, economics, mcp_actions, project as storage, shading
from guangzhu.config import DATA_DIR


@pytest.mark.parametrize('changed', ['site', 'monthly', 'class', 'qualification', 'source', 'tariff_source',
                                   'missing_proof', 'shadow_version', 'shadow_hash'])
def test_changed_energy_inputs_cold_recompute_without_writes(tmp_path, monkeypatch, changed):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    project = storage.init(DATA_DIR / 'demo/projects/changzhou-demo')
    project.site.design_temp_min_c = -13.45
    project.site.design_temp_max_c = 42.06
    storage.save(project)
    energy = dict(p50=200000, low=180000, high=220000, per_kw=1000,
                  hourly=dict(utc=['2023-07-15T06:00:00+00:00'], kwh=[200000]))
    monkeypatch.setattr(analysis, 'generation', lambda *a, **k: (energy, dict(omitted={})))
    analysis.analyze(project.id, 3, offline=True)
    folder = storage._path(project.id, 'analysis/v3')
    shadows = json.loads((folder / 'shading.json').read_text(encoding='utf-8'))
    if changed == 'site':
        project.site.lat += .1
    elif changed == 'monthly':
        project.economics.monthly_kwh = 12000
        project.economics.shifts = 2
    elif changed == 'class':
        project.economics.tariff_class = 'two_part'
    elif changed == 'qualification':
        project.requirements.structured.transformer_kva = 315
    elif changed == 'source':
        rows = economics.load_assumptions()
        rows['design_system_loss_pct']['备注'] += '来源修订'
        monkeypatch.setattr(economics, 'load_assumptions', lambda: rows)
    elif changed == 'tariff_source':
        from guangzhu import config, tariff
        catalog = tmp_path / 'catalog'
        catalog.mkdir()
        text = (DATA_DIR / 'catalog/tou-jiangsu.csv').read_text(encoding='utf-8-sig')
        (catalog / 'tou-jiangsu.csv').write_text(text.replace('426', '426修订'), encoding='utf-8')
        monkeypatch.setattr(config, 'DATA_DIR', tmp_path)
        monkeypatch.setattr(tariff, 'DATA_DIR', tmp_path)
    elif changed.startswith('shadow_'):
        bad = json.loads(json.dumps(shadows))
        if changed == 'shadow_version':
            bad['version'] = 99
        else:
            bad['metadata']['design_sha256'] = '0' * 64
        (folder / 'shading.json').write_text(json.dumps(bad), encoding='utf-8')
    else:
        path = folder / 'economics.json'
        cash = json.loads(path.read_text(encoding='utf-8'))
        cash.pop('energy_fingerprint')
        path.write_text(json.dumps(cash), encoding='utf-8')
    storage.save(project)
    calls = []
    def fresh_shading(current, *args, **kwargs):
        assert current.model_dump() == project.model_dump()
        calls.append('shading')
        return shadows
    def fresh_generation(current, *args, **kwargs):
        assert current.model_dump() == project.model_dump()
        calls.append('generation')
        return energy, dict(omitted={})
    monkeypatch.setattr(shading, 'analyze_design', fresh_shading)
    monkeypatch.setattr(analysis, 'generation', fresh_generation)
    root = storage._path(project.id)
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = mcp_actions._what_if(project.id, 3, {}, True)
    assert calls == ['shading', 'generation']
    assert result['what_if']['saved'] is False
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
