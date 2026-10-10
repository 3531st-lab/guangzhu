"""Offline, independent answers for cashflow, provenance and requirement checks."""

import copy
import csv
import math

import pytest

from guangzhu import economics
from guangzhu.models import Economics, GzError, StructuredRequirements


@pytest.fixture
def params():
    return dict(capex_cny_per_w=1, om_cny_per_w_year=0, price_self_cny_kwh=1,
                price_export_cny_kwh=.4, self_use_ratio=1, discount_rate=.06,
                degradation_annual_pct=0, lifetime_years=25, emission_factor_kgco2_kwh=.6,
                national_emission_factor_kgco2_kwh=.5, design_system_loss_pct=11.42)


@pytest.fixture
def catalog(params, monkeypatch):
    records = {key: dict(zip(economics.CSV_COLUMNS, (key, key, str(value), "测试单位", "已查证",
               "测试来源", "https://example.test/source", "2026-01-01", "2026-10-01", "测试用已查证参数")), value=float(value))
               for key, value in params.items()}
    records.update(emc_discount={'value': .15}, roof_rent_cny_m2_year={'value': 5})
    monkeypatch.setattr(economics, "load_assumptions", lambda: copy.deepcopy(records))
    return records


def test_independent_annuity_answer(params):
    result = economics.cashflow_model(1000, 200000, params)
    # Independently evaluate the 25-year annuity and bisect its IRR.
    present_value = 200000 * (1 - 1.06 ** -25) / .06
    low, high = .1, .3
    for _ in range(80):
        midpoint = (low + high) / 2
        if 200000 * (1 - (1 + midpoint) ** -25) / midpoint > 1000000:
            low = midpoint
        else:
            high = midpoint
    assert result["payback_years"] == 5
    assert result["irr_pct"] == pytest.approx((low + high) * 50, rel=.005)
    assert result["npv_cny"] == pytest.approx(present_value - 1000000, rel=.005)
    assert result["profit_cny"] == 4000000
    assert result["lcoe_cny_kwh"] == pytest.approx(1000000 / present_value)
    assert result["dynamic_payback_years"] == pytest.approx(6 - result["cashflows"][6]["cumulative_discounted_cny"] / result["cashflows"][7]["discounted_cny"])
    assert len(result["cashflows"]) == 26


def test_optional_note_is_not_required_for_user_economic_override(catalog):
    supplied=Economics(capex_cny_per_w=2.6)
    params,sources=economics.resolve_parameters({'economics':supplied})
    assert params['capex_cny_per_w']==2.6
    assert sources['capex_cny_per_w']['basis']=='project.economics'
    assert sources['capex_cny_per_w']['状态']=='示意'
    assert sources['price_export_cny_kwh']['basis']=='assumptions.csv'


def test_first_year_degradation_om_and_fractional_payback(params):
    result = economics.cashflow_model(1000, 250000, params | {"degradation_annual_pct": 10, "om_cny_per_w_year": .025})
    first, second = result["cashflows"][1:3]
    assert first["generation_kwh"] == 250000  # No second initial-light-loss deduction.
    assert second["generation_kwh"] == 225000
    assert first["self_use_kwh"] + first["export_kwh"] == first["generation_kwh"]
    assert first["income_cny"] == 250000 and first["om_cny"] == 25000 and first["net_cny"] == 225000
    year = math.ceil(result["payback_years"])
    before, after = result["cashflows"][year - 1:year + 1]
    assert result["payback_years"] == pytest.approx(year - 1 - before["cumulative_cny"] / after["net_cny"])
    assert second["discounted_cny"] == pytest.approx(second["net_cny"] / 1.06 ** 2)
    assert second["cumulative_discounted_cny"] == pytest.approx(-1000000 + first["discounted_cny"] + second["discounted_cny"])


def test_no_sign_change_and_no_recovery(params):
    loss = economics.cashflow_model(1000, 0, params | {"om_cny_per_w_year": .1})
    assert loss["irr_pct"] is None and loss["payback_years"] is None and loss["dynamic_payback_years"] is None
    assert loss["lcoe_cny_kwh"] is None
    free = economics.cashflow_model(1000, 200000, params | {"capex_cny_per_w": 0})
    assert free["irr_pct"] is None and free["payback_years"] == 0
    low_income = economics.cashflow_model(1000, 30000, params)
    assert low_income["irr_pct"] < 0 and low_income["payback_years"] is None
    irr = low_income["irr_pct"] / 100
    assert math.fsum(row["net_cny"] / (1 + irr) ** row["year"] for row in low_income["cashflows"]) == pytest.approx(0, abs=1e-5)


def test_catalog_loading_and_rejection(params, monkeypatch, tmp_path):
    path = tmp_path / "assumptions.csv"
    monkeypatch.setattr(economics, "ASSUMPTIONS_PATH", path)
    with pytest.raises(GzError, match="缺失"):
        economics.load_assumptions()
    rows = [dict(zip(economics.CSV_COLUMNS, (key, key, str(value), "单位", "已查证", "来源", "https://example.test", "2026-01-01", "2026-10-01", ""))) for key, value in params.items()]
    def write():
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=economics.CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    write()
    actual = economics.load_assumptions()
    assert actual["discount_rate"]["value"] == .06 and actual["discount_rate"]["链接"] == "https://example.test"
    rows[0]["访问日期"] = ""
    write()
    with pytest.raises(GzError):
        economics.load_assumptions()
    rows[0]["状态"] = "示意"
    write()
    assert economics.load_assumptions()[rows[0]["key"]]["状态"] == "示意"


def test_overrides_traceability_sensitivity_carbon_and_purity(catalog):
    project = {"economics": {"self_use_ratio": .95, "price_export_cny_kwh": None, "assumptions_note": "示意，业主可改"}}
    from guangzhu.models import Project
    from guangzhu.config import ROOT
    project = Project.model_validate_json((ROOT / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8')).model_copy(
        update=dict(economics=Economics(**project['economics'], capex_cny_per_w=1)))
    before = copy.deepcopy(project)
    result = economics.calculate(project, 1000, dict(p50=200000, low=180000, high=220000))
    assert project == before and result["params"]["self_use_ratio"] == .95
    override, fallback = result["source"]["self_use_ratio"], result["source"]["price_export_cny_kwh"]
    assert override["状态"] == "示意" and "可改" in override["备注"]
    assert override["来源标题"] == "用户项目参数" and override["链接"] == ""
    assert override["default_source"] == catalog["self_use_ratio"]
    assert fallback["basis"] == "assumptions.csv" and fallback["value"] == .4
    assert len(result["sensitivity"]) == 8
    shares = [row["value"] for row in result["sensitivity"] if row["variable"] == "self_use_ratio"]
    assert shares == pytest.approx([.85, 1])
    for row in result["sensitivity"]:
        assert row["delta_payback_years"] == pytest.approx(row["payback_years"] - result["payback_years"])
        assert row["delta_irr_pct"] == pytest.approx(row["irr_pct"] - result["irr_pct"])
    assert result["carbon"]["jiangsu"]["annual_t"][0] == {"year": 1, "co2_t": 120}
    assert result["carbon"]["jiangsu"]["total_t"] == 3000
    assert result["carbon"]["national"]["total_t"] == 2500
    assert result["co2_t_per_year"] == 120 and any("逆变器更换" in note for note in result["assumptions"])


@pytest.mark.parametrize("req,limits,fragment", [
    ({"capacity_kw_min": 20, "capacity_kw_max": 10}, {}, "大于上限"),
    ({"capacity_kw_min": 20, "budget_cny_max": 19999}, {}, "20000元"),
    ({"capacity_kw_min": 20}, {"max_capacity_kw": 10}, "屋顶"),
    ({"payback_years_max": 4}, {"best_payback_years": 5}, "最快"),
])
def test_four_requirement_contradictions(catalog, req, limits, fragment):
    result = economics.check_requirements_consistency(StructuredRequirements(**req), {"economics": {"capex_cny_per_w": 1}}, **limits)
    assert len(result["contradictions"]) == 1 and fragment in result["contradictions"][0]


def test_missing_requirements_are_advice_and_boundaries_pass(catalog):
    result = economics.check_requirements_consistency({}, {"economics": {}})
    assert len(result["missing"]) == 3 and result["contradictions"] == []
    result = economics.check_requirements_consistency(dict(capacity_kw_min=20, capacity_kw_max=20,
             budget_cny_max=20000, payback_years_max=5), {"economics": {"capex_cny_per_w": 1}},
             max_capacity_kw=20, best_payback_years=5)
    assert result == {"missing": [], "contradictions": []}


def test_plots_exist_and_mark_interpolated_payback(catalog, tmp_path, monkeypatch):
    import matplotlib.axes
    annotations = []
    original = matplotlib.axes.Axes.annotate
    def record(axis, text, xy, *args, **kwargs):
        annotations.append((text, xy))
        return original(axis, text, xy, *args, **kwargs)
    monkeypatch.setattr(matplotlib.axes.Axes, "annotate", record)
    from guangzhu.models import Project
    from guangzhu.config import ROOT
    project = Project.model_validate_json((ROOT / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    project.economics = Economics(capex_cny_per_w=1)
    result = economics.calculate(project, 1000, dict(p50=200000, low=180000, high=220000))
    tornado, cashflow = tmp_path / "tornado.png", tmp_path / "cashflow.png"
    economics.plot(result, tornado, cashflow)
    assert tornado.read_bytes().startswith(b"\x89PNG") and cashflow.read_bytes().startswith(b"\x89PNG")
    assert any("Cumulative payback" in text and xy == (result["payback_years"], 0) for text, xy in annotations)
    assert any("Discounted cumulative payback" in text and xy == (result["dynamic_payback_years"], 0) for text, xy in annotations)
