"""Object diagnostics require matching version evidence and never mutate or save a design."""
from copy import deepcopy

import pytest

from guangzhu.design_diagnostics import build


def module(identifier, x=0):
    return dict(id=identifier, corners=[[x, 0, .3], [x + 1, 0, .3], [x + 1, 2, .3], [x, 2, .3]])


@pytest.fixture
def sample():
    names = ['R01-1-C001', 'R02-1-C001', 'R03-1-C001']
    project = dict(roof=dict(type='flat', planes=[]))
    design = dict(version=4, modules=[module(name, i * 3) for i, name in enumerate(names)])
    rules = dict(items=[dict(id='S01', name_zh='单板遮挡', status='fail', level='hard', value=12, limit=8,
                            unit='%', evidence='最大12%，阈值8%', hint_zh='核对遮挡', source_ref='设计假设')])
    shading = dict(version=4, modules=[dict(id=name, total_loss_pct=value, main_cause='hvac')
                                      for name, value in zip(names, [8, 9, 12])])
    return dict(project=project, design=design, rules=rules, shading=shading,
                source_versions={'rules': 4, 'structure': 4})


def test_shading_uses_actual_threshold_and_explicit_unlocked_ids_without_mutation(sample):
    original = deepcopy(sample)
    result = build(**sample, locked_ids=['R03-1-C001'])
    assert result['available'] and result['version'] == 4
    issue = result['issues'][0]
    assert issue['module_ids'] == ['R02-1-C001', 'R03-1-C001']  # exactly 8% is not over the threshold
    assert issue['locked_module_ids'] == ['R03-1-C001']
    assert issue['fix']['ops'] == [dict(op='remove_modules', module_ids=['R02-1-C001'])]
    assert issue['fix']['retained_locked_ids'] == ['R03-1-C001']
    assert '不保证' in issue['fix']['note']
    assert sample == original


def test_all_shaded_modules_locked_retains_location_but_has_no_repair(sample):
    issue = build(**sample, locked_ids=['R02-1-C001', 'R03-1-C001'])['issues'][0]
    assert issue['located'] and issue['fix'] is None
    assert '全部已锁定' in issue['fix_unavailable_reason']


@pytest.mark.parametrize('version', [3, True, '4', None])
def test_explicit_old_or_invalid_rules_version_cannot_be_replaced_by_path_proof(sample, version):
    sample['rules']['version'] = version
    result = build(**sample)
    assert not result['available'] and result['issues'] == []
    assert '不一致' in result['reason']


def test_unversioned_rules_need_exact_path_proof_and_do_not_inherit_shading_version(sample):
    sample.pop('source_versions')
    result = build(**sample)
    assert not result['available'] and '缺少可核对的版本' in result['reason']


@pytest.mark.parametrize('corrupt', ['old', 'unversioned', 'missing_panel', 'duplicate', 'unknown', 'nonfinite'])
def test_shading_missing_or_inconsistent_evidence_never_creates_location_or_repair(sample, corrupt):
    shading = sample['shading']
    if corrupt == 'old':
        shading['version'] = 3
    elif corrupt == 'unversioned':
        shading.pop('version')
        sample['source_versions']['shading'] = 4  # only rules/load legacy files permit path-only version proof
    elif corrupt == 'missing_panel':
        shading['modules'].pop()
    elif corrupt == 'duplicate':
        shading['modules'][0]['id'] = shading['modules'][1]['id']
    elif corrupt == 'unknown':
        shading['modules'][0]['id'] = 'R99-1-C001'
    else:
        shading['modules'][0]['total_loss_pct'] = float('nan')
    issue = build(**sample)['issues'][0]
    assert not issue['located'] and not issue['module_ids'] and issue['fix'] is None
    assert issue['location_reason']


def test_unused_modules_are_cross_checked_against_real_string_members(sample):
    sample['rules']['items'] = [dict(id='E08', status='fail', value=1, limit=0)]
    sample['electrical'] = dict(version=4, unused_modules=['R03-1-C001'],
        strings=[dict(id='S001', module_ids=['R01-1-C001', 'R02-1-C001'])])
    issue = build(**sample)['issues'][0]
    assert issue['located'] and issue['module_ids'] == ['R03-1-C001'] and issue['fix'] is None
    sample['electrical']['strings'][0]['module_ids'].append('R03-1-C001')
    issue = build(**sample)['issues'][0]
    assert not issue['located'] and not issue['module_ids']
    assert '不一致' in issue['location_reason']


def test_failed_dc_routes_use_feasibility_and_resolve_complete_string_members(sample):
    sample['rules']['items'] = [dict(id='E10', status='fail', value=2.5, limit=2, unit='%')]
    sample['electrical'] = dict(version=4,
        strings=[dict(id=f'S00{i + 1}', module_ids=[f'R0{i + 1}-1-C001']) for i in range(3)],
        cables=dict(dc=[dict(id='S001', feasible=True, drop_pct=.4, routing_status='ok'),
                        dict(id='S002', feasible=False, drop_pct=1, routing_status='blocked'),
                        dict(id='S003', feasible=False, drop_pct=2.5, routing_status='ok')]))
    issue = build(**sample)['issues'][0]
    assert issue['located'] and issue['module_ids'] == ['R02-1-C001', 'R03-1-C001']
    assert issue['string_ids'] == ['S002', 'S003'] and issue['fix'] is None
    sample['electrical']['strings'].pop()
    issue = build(**sample)['issues'][0]
    assert not issue['located'] and not issue['module_ids'] and not issue['string_ids']


def test_dc_failure_without_explicit_route_evidence_is_not_guessed(sample):
    sample['rules']['items'] = [dict(id='E10', status='fail', value=10, limit=2)]
    sample['electrical'] = dict(version=4, strings=[], cables=dict(dc=[dict(id='S001', drop_pct=10)]))
    issue = build(**sample)['issues'][0]
    assert not issue['located'] and '不能仅凭最大压降' in issue['location_reason']


def test_load_failure_locates_only_the_evidenced_plane_and_preserves_plane_lock(sample):
    sample['project']['roof'] = dict(type='pitched', planes=[dict(id=1), dict(id=2)])
    sample['design']['modules'] = [module('P1-R01-1-C001'), module('P2-R01-1-C001', 3), module('P2-R02-1-C001', 6)]
    sample['design']['locked_plane_ids'] = [2]
    sample['rules']['items'] = [dict(id='L01', status='fail', plane=2, value=.8, limit=.5)]
    sample['structure'] = dict(wind=dict(version=4), planes=[dict(id=1, status='pass', added_kn_m2=.3, capacity_kn_m2=.5),
        dict(id=2, status='fail', added_kn_m2=.8, capacity_kn_m2=.5, verified=False)])
    issue = build(**sample)['issues'][0]
    assert issue['plane_ids'] == [2]
    assert issue['module_ids'] == ['P2-R01-1-C001', 'P2-R02-1-C001']
    assert issue['locked_module_ids'] == issue['module_ids']
    assert issue['fix'] is None and '不能证明某个锚点失效' in issue['location_note']
    sample['structure']['wind']['version'] = 3
    issue = build(**sample)['issues'][0]
    assert not issue['located'] and '不一致' in issue['location_reason']


def test_load_without_specific_plane_and_other_rules_keep_explanation_without_guessing(sample):
    sample['rules']['items'] = [dict(id='L01', status='fail', value=1, limit=.5),
                               dict(id='G03', status='fail', evidence='实际连续通道待核对', hint_zh='人工核对路径')]
    sample['structure'] = dict(added_kn_m2=1, capacity_kn_m2=.5)
    result = build(**sample)
    assert len(result['issues']) == 2
    assert all(not row['located'] and row['fix'] is None for row in result['issues'])
    assert result['issues'][1]['evidence'] == '实际连续通道待核对'
    assert result['issues'][1]['hint'] == '人工核对路径'


def test_lean_archive_without_real_geometry_does_not_pretend_objects_are_locatable(sample):
    sample['design']['modules'][0].pop('corners')
    result = build(**sample)
    assert not result['available'] and '完整组件几何' in result['reason']


def test_successful_rules_are_not_reported_as_failures_or_an_export_approval(sample):
    sample['rules']['items'][0]['status'] = 'pass'
    result = build(**sample)
    assert result['available'] and not result['issues']
    assert '不代表' in result['reason']
