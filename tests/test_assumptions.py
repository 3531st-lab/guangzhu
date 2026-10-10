"""T07 input provenance and optional economic overrides, without network calls."""

import csv
import math
from datetime import date

import pytest
from pydantic import ValidationError

from guangzhu.config import DATA_DIR
from guangzhu.models import Economics


def assumptions():
    with (DATA_DIR / "catalog/assumptions.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ["key", "中文名", "数值", "单位", "状态", "来源标题", "链接", "发布日期", "访问日期", "备注"]
        rows = list(reader)
    assert len(rows) == len({row["key"] for row in rows})
    return {row["key"]: row for row in rows}


def test_default_catalog_contract_and_sources():
    rows = assumptions()
    assert set(rows) == {
        "capex_cny_per_w", "om_cny_per_w_year", "price_self_cny_kwh", "price_export_cny_kwh",
        "self_use_ratio", "discount_rate", "degradation_annual_pct", "lifetime_years",
        "emission_factor_kgco2_kwh", "national_emission_factor_kgco2_kwh", "design_system_loss_pct",
        "load_workdays_per_week", "load_single_shift_start", "load_single_shift_end", "load_double_shift_end",
        "load_idle_ratio", "self_use_degradation_fixed", "emc_discount", "roof_rent_cny_m2_year",
    }
    for row in rows.values():
        assert row["状态"] in {"已查证", "示意"}
        assert row["来源标题"] and row["中文名"] and row["单位"] and row["备注"]
        assert math.isfinite(float(row["数值"]))
        new = row['key'].startswith(('load_', 'emc_', 'roof_rent_', 'self_use_degradation_'))
        assert date.fromisoformat(row["访问日期"]) == (date(2026, 10, 5) if new else date(2026, 10, 1))
        if row["状态"] == "已查证":
            assert row["链接"].startswith("https://") and row["发布日期"]
    for key in ["price_self_cny_kwh", "price_export_cny_kwh", "self_use_ratio", "discount_rate"]:
        assert rows[key]["状态"] == "示意"
    assert "2026年10月" in rows["price_self_cny_kwh"]["备注"]
    assert "新建" in rows["price_export_cny_kwh"]["备注"]


def test_verified_known_values_and_loss_without_shading():
    rows = assumptions()
    known = {"capex_cny_per_w": 2.59, "om_cny_per_w_year": 0.046,
             "emission_factor_kgco2_kwh": 0.5827, "national_emission_factor_kgco2_kwh": 0.5306,
             "degradation_annual_pct": 0.55, "lifetime_years": 25}
    for key, value in known.items():
        assert float(rows[key]["数值"]) == value
        assert rows[key]["状态"] == "已查证"
    expected = 100 * (1 - math.prod([0.98, 1, 0.98, 0.98, 0.995, 0.985, 0.99, 1, 0.97]))
    assert float(rows["design_system_loss_pct"]["数值"]) == pytest.approx(expected, abs=1e-12)
    assert expected == pytest.approx(11.42, abs=0.005)


def test_economics_accepts_omitted_or_null_fields_and_keeps_valid_overrides():
    omitted = Economics()
    nulls = Economics.model_validate({name: None for name in Economics.model_fields})
    assert all(value is None for value in omitted.model_dump().values())
    assert omitted == nulls
    supplied = Economics(capex_cny_per_w=2.6, self_use_ratio=0, discount_rate=0,
                         degradation_annual_pct=0.55, emission_factor_kgco2_kwh=0.5827)
    assert supplied.capex_cny_per_w == 2.6 and supplied.self_use_ratio == 0
    assert supplied.discount_rate == 0 and supplied.degradation_annual_pct == 0.55


@pytest.mark.parametrize("field,value", [("capex_cny_per_w", -1), ("self_use_ratio", 1.01),
    ("discount_rate", 1), ("lifetime_years", 0), ("degradation_annual_pct", 100),
    ("emission_factor_kgco2_kwh", -0.01), ("price_export_cny_kwh", float("nan"))])
def test_optional_fields_still_validate_supplied_ranges(field, value):
    with pytest.raises(ValidationError):
        Economics.model_validate({field: value})
