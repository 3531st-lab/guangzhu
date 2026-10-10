"""Large-roof advice stays bounded while preserving the original deletion set."""

import hashlib
import json
import math
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from guangzhu import analysis, code_identity, layout, mcp_actions, mcp_server, project as storage, shading
from guangzhu.config import ROOT
from guangzhu.models import GzError, StructuredRequirements


def large_roof(tmp_path, monkeypatch, rule, requirements, capex=None):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    project = storage.init(ROOT / 'data/demo/projects/changzhou-demo', 'large-' + rule)
    project.roof.outline = [(0, 0), (100, 0), (100, 130), (0, 130)]
    project.roof.obstacles = []
    project.roof.keepouts = []
    project.requirements.structured = StructuredRequirements(**requirements)
    project.economics.capex_cny_per_w = capex
    storage.save(project)
    first = layout.generate_layout(project, {})
    storage.save_design(project.id, first)
    assert first.statistics['roof_area_m2'] == 13000
    losses = {module.id: index % 5 for index, module in enumerate(first.modules)}
    def controlled_shading(project_id, version, **kwargs):
        design = storage.load_design(project_id, version)
        values = [dict(id=module.id, total_loss_pct=losses[module.id]) for module in design.modules]
        result = dict(version=version, modules=values, metadata={}, summary=dict(avg_loss_pct=
                      sum(row['total_loss_pct'] for row in values) / len(values), modules_over_threshold=0, threshold_pct=8))
        path = storage._path(project_id, f'analysis/v{version}/shading.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result), encoding='utf-8')
        return result
    monkeypatch.setattr(shading, 'analyze', controlled_shading)
    return project, first, losses


@pytest.mark.parametrize('rule,requirements', [('U02', {'capacity_kw_max': 120}), ('U03', {'budget_cny_max': 330000})])
def test_large_roof_one_advice_meets_limit_without_id_expansion(tmp_path, monkeypatch, rule, requirements):
    # This original one-step arithmetic contract assumes a linear, explicitly supplied total price.
    project, first, losses = large_roof(tmp_path, monkeypatch, rule, requirements, capex=2.59)
    response = mcp_server.call('gz_analyze', dict(project_id=project.id, version=1, offline=True))
    assert response.is_error is False
    assert len(response.content[0].text.encode()) <= 2048
    summary = json.loads(response.content[0].text)
    checked = json.loads(storage._path(project.id, 'analysis/v1/rules.json').read_text(encoding='utf-8'))
    failed = next(row for row in checked['items'] if row['id'] == rule)
    assert failed['status'] == 'fail'
    count = math.ceil((failed['value'] - failed['limit']) / (failed['value'] / len(first.modules)))
    operation = dict(op='remove_modules', where=dict(worst_count=count))
    assert failed['suggestion'] == operation and operation in summary['suggestions']
    assert count > 500
    args = dict(project_id=project.id, version=1, reason=rule, ops=[operation])
    Draft202012Validator(mcp_server.SCHEMAS['gz_edit_design']).validate(args)
    result = mcp_actions.dispatch('gz_edit_design', args)
    second = storage.load_design(project.id, result['version'])
    expected = set(sorted(losses, key=lambda identifier: (-losses[identifier], identifier))[:count])
    assert {module.id for module in first.modules} - {module.id for module in second.modules} == expected
    following = analysis.analyze(project.id, second.version, offline=True)
    assert len(analysis.serialized(following).encode()) <= 2048
    checked = json.loads(storage._path(project.id, f'analysis/v{second.version}/rules.json').read_text(encoding='utf-8'))
    assert next(row for row in checked['items'] if row['id'] == rule)['status'] == 'pass'
    print(json.dumps(dict(rule=rule, area_m2=13000, modules=len(first.modules), removed=count,
                          initial_bytes=len(response.content[0].text.encode()), final_bytes=len(analysis.serialized(following).encode()),
                          remaining=len(second.modules))))


def test_itemized_budget_estimate_requires_bounded_actual_requotes(tmp_path, monkeypatch):
    budget = 330000
    project, current, losses = large_roof(tmp_path, monkeypatch, 'U03', dict(budget_cny_max=budget))
    assert project.economics.capex_cny_per_w is None
    quotes = []
    for attempt in range(4):
        response = mcp_server.call('gz_analyze', dict(project_id=project.id, version=current.version, offline=True))
        assert response.is_error is False and len(response.content[0].text.encode()) <= 2048
        folder = storage._path(project.id, f'analysis/v{current.version}')
        cash = json.loads((folder / 'economics.json').read_text(encoding='utf-8'))
        checked = json.loads((folder / 'rules.json').read_text(encoding='utf-8'))
        row = next(item for item in checked['items'] if item['id'] == 'U03')
        actual_cost = math.fsum(item['subtotal_cny'] for item in cash['costs']['items'])
        quotes.append(dict(attempt=attempt + 1, modules=len(current.modules), capex_cny=actual_cost, status=row['status']))
        keys = {item['key'] for item in cash['costs']['items']}
        quotes[-1]['cost_items_cny'] = {key: math.fsum(item['subtotal_cny'] for item in cash['costs']['items'] if item['key'] == key)
                                      for key in sorted(keys)}
        assert row['value'] == pytest.approx(actual_cost)
        assert cash['capex_cny'] == pytest.approx(actual_cost)
        # Wind ballast and electrical re-selection make individual deletions non-monotonic; every quote remains real.
        assert math.isfinite(actual_cost) and actual_cost > 0
        assert not cash['costs']['manual_override']
        assert '估算' in row['evidence'] and '须重新核价' in row['evidence']
        if attempt == 0:  # the full roof is over budget; since anchors replaced heavy ballast one requote may already suffice
            assert actual_cost > budget and row['status'] == 'fail'
        if row['status'] == 'pass':
            assert actual_cost <= budget and current.modules
            break
        assert actual_cost > budget
        count = math.ceil((actual_cost - budget) / (actual_cost / len(current.modules)))
        operation = dict(op='remove_modules', where=dict(worst_count=count))
        assert row['suggestion'] == operation
        available = {module.id for module in current.modules}
        expected = set(sorted(available, key=lambda identifier: (-losses[identifier], identifier))[:count])
        args = dict(project_id=project.id, version=current.version, reason='实际分项复算预算', ops=[operation])
        Draft202012Validator(mcp_server.SCHEMAS['gz_edit_design']).validate(args)
        changed = mcp_actions.dispatch('gz_edit_design', args)
        current = storage.load_design(project.id, changed['version'])
        assert available - {module.id for module in current.modules} == expected
    else:
        pytest.fail('The documented itemized fixture must reach its original budget within four actual quotes')
    print(json.dumps(dict(budget=budget, quotes=quotes)))


def test_worst_count_overlapping_operations_use_original_ranking(source):
    identifier, first, path, shadows = source
    shadows['modules'][0]['total_loss_pct'] = 9
    shadows['modules'][1]['total_loss_pct'] = 9
    path.write_text(json.dumps(shadows), encoding='utf-8')
    ranked = sorted(shadows['modules'], key=lambda row: (-row['total_loss_pct'], row['id']))
    result = storage.edit_design(identifier, 1, [dict(op='remove_modules', where=dict(shading_loss_gt=8)),
                                dict(op='remove_modules', where=dict(worst_count=2))], 'same original set', 'rule')
    edited = storage.load_design(identifier, result['version'])
    assert {module.id for module in edited.removed_modules} == {row['id'] for row in ranked[:2]}
    assert len(edited.modules) == 1


@pytest.mark.parametrize('count', [0, -1, 4, True, 1.5, None, '1'])
def test_worst_count_rejects_invalid_input(source, count):
    identifier, first, path, shadows = source
    args = dict(project_id=identifier, version=1, reason='invalid', ops=[dict(op='remove_modules', where=dict(worst_count=count))])
    with pytest.raises(GzError) as caught:
        storage.edit_design(identifier, 1, args['ops'], args['reason'], 'rule')
    assert caught.value.error_code == 'DESIGN_EDIT_INVALID' and storage.next_version(identifier) == 2


def test_worst_count_requires_original_analysis_and_rejects_repacked_selection(source):
    identifier, first, path, shadows = source
    operation = dict(op='remove_modules', where=dict(worst_count=2))
    path.unlink()
    with pytest.raises(GzError) as caught:
        storage.edit_design(identifier, 1, [operation], 'missing', 'rule')
    assert caught.value.error_code == 'ANALYSIS_MISSING'
    path.write_text(json.dumps(shadows | {'version': 2}), encoding='utf-8')
    with pytest.raises(GzError) as caught:
        storage.edit_design(identifier, 1, [operation], 'wrong version', 'rule')
    assert caught.value.error_code == 'ANALYSIS_INVALID'
    with pytest.raises(GzError) as caught:
        storage.edit_design(identifier, 1, [dict(op='set_param', name='tilt_deg', value=15), operation], 'repacked', 'rule')
    assert caught.value.error_code == 'DESIGN_EDIT_DEPENDENCY' and storage.next_version(identifier) == 2


def test_identity_changes_for_code_but_allows_appended_experience(tmp_path, monkeypatch):
    monkeypatch.setattr(code_identity, 'ROOT', tmp_path)
    source = tmp_path / 'backend/guangzhu/example.py'
    source.parent.mkdir(parents=True)
    source.write_text('value = 1\n', encoding='utf-8', newline='\n')
    skill = tmp_path / '.agh/skills/pv-rooftop-design/SKILL.md'
    skill.parent.mkdir(parents=True)
    skill.write_text('unchanged rules\n', encoding='utf-8')
    commands = []
    def git(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(stdout='a' * 40 if 'rev-parse' in command else '')
    monkeypatch.setattr(code_identity.subprocess, 'run', git)
    frozen = dict(code_identity.CODE_IDENTITY)
    before = code_identity.current_identity()
    assert before['commit'] == 'a' * 40 and before['dirty'] is False
    expected = hashlib.sha256(b'backend/guangzhu/example.py\0value = 1\n\0').hexdigest()
    assert before['source_sha256'] == expected
    skill.write_text('unchanged rules\n\n## 经验\n\n- model experience\n', encoding='utf-8')
    after = code_identity.current_identity()
    assert after['skill_rules_sha256'] == before['skill_rules_sha256']
    assert after['source_sha256'] == before['source_sha256']
    source.write_text('value = 2\n', encoding='utf-8')
    assert code_identity.current_identity()['source_sha256'] != before['source_sha256']
    assert code_identity.CODE_IDENTITY == frozen
    assert all('.agh/skills' not in command for command in commands)


from test_shading_edit import source
