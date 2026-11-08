"""Monthly charts must reconcile to the simulated year, using local month boundaries."""
import copy
from pathlib import Path

import pytest

from guangzhu import analysis, economic_analysis, layout, tariff
from guangzhu.models import Project


def project():
    record = Project.model_validate_json((Path(__file__).parents[1] / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    record.economics.self_use_ratio = .5
    return record


def energy():
    # UTC 16:00 is the start of the next day/month in China.
    return dict(p50=40., low=40., high=40., per_kw=40., hourly=dict(
        utc=['2023-01-31T15:00:00+00:00', '2023-01-31T16:00:00+00:00',
             '2023-02-28T16:00:00+00:00'], kwh=[10., 20., 10.]))


def test_generation_months_use_local_time_and_include_shading(monkeypatch):
    record = project()
    design = layout.generate_layout(record, {})
    sample = energy()
    generated = dict(results={'b': dict(specific_yield_kwh_kwp=40., hourly=sample['hourly'])}, omitted={})
    monkeypatch.setattr(analysis.yieldsim, 'simulate_design_yields', lambda *a, **kw: copy.deepcopy(generated))
    actual, _ = analysis.generation(record, design, dict(summary=dict(avg_loss_pct=25)), 2., offline=True)
    months = actual['monthly_kwh']
    assert len(months) == 12
    assert [row['ac_kwh'] for row in months[:3]] == pytest.approx([15., 30., 15.])
    assert sum(row['ac_kwh'] for row in months) == pytest.approx(actual['p50'])


def test_tariff_months_reconcile_and_repricing_updates_manual_self_use():
    record = project()
    actual = tariff.integrate(record, energy(), .5, .7)
    assert [row['generation_kwh'] for row in actual['monthly'][:3]] == [10., 20., 10.]
    assert sum(row['self_use_kwh'] for row in actual['monthly']) == pytest.approx(actual['self_use_kwh'])
    record.economics.self_use_ratio = .25
    repriced = tariff.reprice(record, actual, .8)
    assert [row['self_use_kwh'] for row in repriced['monthly'][:3]] == [2.5, 5., 2.5]
    assert sum(row['self_use_kwh'] for row in repriced['monthly']) == pytest.approx(repriced['self_use_kwh'])
    assert actual['monthly'][0]['self_use_kwh'] == 5.


@pytest.mark.parametrize('allow_export', [True, False])
def test_economics_monthly_energy_balance_respects_no_export(allow_export):
    record = project()
    record.requirements.structured.export_allowed = allow_export
    result = economic_analysis.calculate(record, 1., energy(), sensitivity=False)
    use = result['self_use']
    assert use['algorithm'] == '手填比例均摊到各小时'
    for row in use['monthly']:
        assert row['generation_kwh'] == pytest.approx(row['self_use_kwh'] + row['export_kwh'] + row['curtailed_kwh'])
        if not allow_export:
            assert row['export_kwh'] == 0
    for field in ('self_use_kwh', 'export_kwh', 'curtailed_kwh'):
        assert sum(row[field] for row in use['monthly']) == pytest.approx(use[field])


def test_missing_hourly_does_not_invent_monthly_distribution():
    record = project()
    values = energy()
    values.pop('hourly')
    result = economic_analysis.calculate(record, 1., values, sensitivity=False)
    assert result['self_use'].get('monthly') is None
