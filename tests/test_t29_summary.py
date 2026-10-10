"""Frozen actual equipment arithmetic and T22 cashflow boundaries."""
import pytest
from guangzhu import park


def test_unrounded_per_unit_ac_and_phases_not_double_counted():
    units = [dict(inverter=i, dc_kw=dc, dc_ac_ratio=dc / ac) for i, dc, ac in [(1, 72.6, 60), (2, 36.3, 30)]]
    electric = dict(per_inverter=units, inverter_count=2, phases=[dict(per_inverter=units)])
    assert park.actual_ac(electric) == dict(inverter_count=2, rated_ac_kw=90)


@pytest.mark.parametrize('value', [0, -1, None, True, float('nan'), float('inf')])
def test_invalid_evidence_is_unknown(value):
    with pytest.raises(ValueError):
        park.actual_ac(dict(inverter_count=1, per_inverter=[dict(inverter=1, dc_kw=10, dc_ac_ratio=value)]))


def test_whole_building_cashflows_once():
    rows = [dict(dc_kw=1, annual_kwh=2, capex_cny=3, co2_t=4, net_cny=flow)
            for flow in ([-100, 70, 70], [-100, 30, 30, 60])]
    result = park.total(rows)
    assert result['net_cny'] == [-200, 100, 100, 60]
    assert result['payback_years'] == 2
    assert park.total([])['payback_years'] is None
    assert park.total([dict(rows[0], net_cny=[0, 1])])['payback_years'] is None
