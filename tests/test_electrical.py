"""T06 independent hand values and allocation behavior, without public network."""

import copy
import json

import pytest
import requests

from guangzhu import electrical
from guangzhu.config import DATA_DIR
from guangzhu.models import Design, GzError, LayoutParams, Module, validate_project

TRINA = "trina-tsm-550de19"
RUNERGY = "runergy-hy-wh144p8-550"
SUNGROW = "sungrow-sg100cx-p2"
HUAWEI = "huawei-sun2000-100ktl-m2"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Electrical tests must not use the public network")
    monkeypatch.setattr(requests.Session, "request", unexpected)


@pytest.fixture
def project():
    payload = json.loads((DATA_DIR / "demo/projects/changzhou-demo/project.json").read_text(encoding="utf-8"))
    payload["site"].update(design_temp_min_c=-13.45, design_temp_max_c=42.06)
    payload["equipment"].update(module_id=TRINA, inverter_id=SUNGROW)
    # Synthetic panel grids must lie inside a clear domain now that routes are checked.
    payload['roof'].update(outline=[(0, 0), (100, 0), (100, 120), (0, 120)], obstacles=[], keepouts=[])
    return validate_project(payload)


def design(count, size=None, *, cols=20, tiers=1):
    modules = []
    for i in range(count):
        group, col = divmod(i, cols)
        row, tier = divmod(group, tiers)
        x, y = col * 3, group * 4
        modules.append(Module(id=f"R{row + 1:02}-{tier + 1}-C{col + 1:03}", row=row + 1, tier=tier + 1, col=col + 1,
                              center=(x + 1, y + 1, .3), corners=((x, y, .3), (x + 2, y, .3), (x + 2, y + 2, .3), (x, y + 2, .3)),
                              tilt=25, azimuth=180, orientation="portrait"))
    return Design(params=LayoutParams(), modules=modules, modules_per_string=size)


@pytest.mark.parametrize("module_id,inverter_id,minimum,maximum,hot,voc,vmp_hot,vmp_cold", [
    (TRINA, SUNGROW, 7, 26, 70.81, 830.86275, 533.563472, 714.62136),
    (TRINA, HUAWEI, 8, 26, 70.81, 830.86275, 533.563472, 714.62136),
    (RUNERGY, SUNGROW, 6, 20, 73.31, 1097.77006, 697.303868, 952.13534),
    (RUNERGY, HUAWEI, 6, 20, 73.31, 1097.77006, 697.303868, 952.13534),
])
def test_four_manufacturer_combinations_match_hand_calculation(project, monkeypatch, module_id, inverter_id, minimum, maximum, hot, voc, vmp_hot, vmp_cold):
    # Hand inputs: t=-13.45, tmax=42.06; Trina NOCT43, beta=-.0025,
    # gamma=-.0034; Runergy NOCT45, beta=-.0026, gamma=-.0035; N=20.
    project.equipment.module_id, project.equipment.inverter_id = module_id, inverter_id
    monkeypatch.setattr(electrical, "load_nasa_daily_extremes", lambda *a, **k: pytest.fail("Both overrides must bypass NASA"))
    result = electrical.calculate(project, design(400, 20), offline=True)
    assert result["feasible_range"] == [minimum, maximum]
    assert result["temperature"]["cell_hot_c"] == pytest.approx(hot)
    assert result["voc_cold_v"] == pytest.approx(voc, abs=.00001)
    assert result["vmp_hot_v"] == pytest.approx(vmp_hot, abs=.00001)
    assert result["vmp_cold_v"] == pytest.approx(vmp_cold, abs=.00001)
    assert [round(result[key], 1) for key in ("voc_cold_v", "vmp_hot_v", "vmp_cold_v")] == [round(voc, 1), round(vmp_hot, 1), round(vmp_cold, 1)]
    assert all(check["status"] == "pass" for code, check in result["checks"].items() if code != "E06")
    assert result["checks"]["E06"]["status"] == "pass"


def test_serpentine_alternates_each_row_tier_group_and_keeps_gaps(project):
    option = design(18, 2, cols=3, tiers=2)
    option.modules = [m for m in reversed(option.modules) if m.id != "R01-1-C002"]
    result = electrical.calculate(project, option, offline=True)
    routed = [identifier for string in result["strings"] for identifier in string["module_ids"]] + result["unused_modules"]
    assert routed == ["R01-1-C001", "R01-1-C003", "R01-2-C003", "R01-2-C002", "R01-2-C001",
                      "R02-1-C001", "R02-1-C002", "R02-1-C003", "R02-2-C003", "R02-2-C002", "R02-2-C001",
                      "R03-1-C001", "R03-1-C002", "R03-1-C003", "R03-2-C003", "R03-2-C002", "R03-2-C001"]
    assert result["unused_modules"] == ["R03-2-C001"]
    assert len(set(routed)) == len(option.modules)


@pytest.mark.parametrize("size,failed", [(1, {"E03"}), (80, {"E01", "E02", "E04"})])
def test_explicit_unsafe_string_size_returns_numeric_rule_evidence(project, size, failed):
    result = electrical.calculate(project, design(400, size), offline=True)
    assert result["modules_per_string"] == size
    for code in failed:
        check = result["checks"][code]
        assert check["status"] == "fail" and check["evidence"] and check["source_ref"]
        assert isinstance(check["value"], (int, float))


def test_default_minimizes_string_count_and_balances_lengths(project):
    result = electrical.calculate(project, design(376), offline=True)
    # Candidate N=23..26 has 8, 16, 1, 12 remaining modules, respectively.
    assert [376 % n for n in range(23, 27)] == [8, 16, 1, 12]
    assert result["modules_per_string"] == 26 and result["string_count"] == 15
    assert result["modules_per_string_short"] == 25
    assert result["unused_modules"] == [] and result["inverter_count"] == 2
    assert result["checks"]["E08"]["status"] == "pass"
    complete = electrical.calculate(project, design(375), offline=True)
    assert complete["modules_per_string"] == 25 and complete["unused_modules"] == []
    assert all(check["status"] == "pass" for check in complete["checks"].values())
    assert electrical.calculate(project, design(400), offline=True)["modules_per_string"] == 25
    explicit = electrical.calculate(project, design(376, 26), offline=True)
    assert explicit["string_count"] == 15 and len(explicit["unused_modules"]) == 0
    assert explicit["checks"]["E08"]["status"] == "pass"
    assert explicit["dc_kw"] == pytest.approx(206.8)
    assert explicit["connected_dc_kw"] == pytest.approx(206.8)


@pytest.mark.parametrize("size,strings,remainder", [(25, 15, 1), (8, 47, 0)])
def test_explicit_size_has_priority_over_the_longest_four(project, size, strings, remainder):
    result = electrical.calculate(project, design(376, size), offline=True)
    assert result["modules_per_string"] == size
    assert result["string_count"] == strings and len(result["unused_modules"]) == remainder


def test_default_tied_remainder_prefers_larger_size(project):
    # Both 24 and 26 divide 312; 26 wins among the four longest feasible sizes.
    result = electrical.calculate(project, design(312), offline=True)
    assert result["modules_per_string"] == 26 and result["unused_modules"] == []


def test_longest_candidate_window_respects_feasible_minimum(project, monkeypatch):
    catalog = copy.deepcopy(electrical.equipment_catalog())
    catalog["inverters"][SUNGROW]["mppt_min_v"] = 650
    monkeypatch.setattr(electrical, "equipment_catalog", lambda: catalog)
    result = electrical.calculate(project, design(336), offline=True)
    # N=24 divides 336, but the feasible range starts at 25.
    assert result["feasible_range"] == [25, 26]
    assert result["modules_per_string"] == 26 and result["modules_per_string_short"] == 25
    assert result['unused_modules'] == []
    assert result["checks"]["E03"]["status"] == "pass"


def test_fifteen_strings_form_contiguous_balanced_groups_and_single_mppts(project):
    result = electrical.calculate(project, design(375, 25), offline=True)
    assert result["inverter_count"] == 2
    assert [r["strings_count"] for r in result["per_inverter"]] == [8, 7]
    # Review fix: each inverter takes one block of neighbouring strings (short DC runs), not every other string.
    assert [s["inverter"] for s in result["strings"]] == [1] * 8 + [2] * 7
    assert [s["mppt"] for s in result["strings"]] == list(range(1, 9)) + list(range(1, 8))
    assert [r["dc_kw"] for r in result["per_inverter"]] == pytest.approx([110, 96.25])
    assert [r["dc_ac_ratio"] for r in result["per_inverter"]] == pytest.approx([110 / 99.99, 96.25 / 99.99])
    assert result["checks"]["E06"]["status"] == "pass"
    assert result["checks"]["E07"]["status"] == "pass"
    assert result["checks"]["E07"]["per_inverter"] == result["per_inverter"]
    assert "第1台：200块" in result["checks"]["E07"]["evidence"]
    assert "第2台：175块" in result["checks"]["E07"]["evidence"]
    assert result["per_inverter"][1]["mppt_assignments"][0] == {"mppt": 1, "string_ids": ["S009"]}
    assert all(r["strings"] <= 1 for r in result["mppt_currents"])


def test_mppt_currents_and_minimum_inverter_count_include_ac_policy(project):
    result = electrical.calculate(project, design(400, 20), offline=True)
    assert result["inverter_count"] == 2  # One device fits strings but exceeds 1.3 DC/AC.
    assert result["mppt_currents"][0]["string_ids"] == ["S001"]
    assert result["mppt_currents"][0]["working_a"] == pytest.approx(17.4)
    assert result["mppt_currents"][0]["short_a"] == pytest.approx(18.85936048)
    assert result["strings"][0]["inverter"] == 1 and result["strings"][0]["mppt"] == 1
    assert all(item["strings"] <= 2 and item["short_a"] <= item["short_limit_a"] for item in result["mppt_currents"])
    assert result["dc_ac_ratio"] == pytest.approx(220 / 199.98)


def test_each_inverter_fills_every_mppt_once_before_second_strings(project):
    plan = design(376, 8)
    result = electrical.calculate(project, plan, offline=True)
    assert result["inverter_count"] == 2
    assert [r["strings_count"] for r in result["per_inverter"]] == [24, 23]
    # Review fix: the first inverter takes the first 40 m band of the 60 m rows (short DC runs), not every other string.
    centers = {m.id: m.center[0] for m in plan.modules}
    first = [s for s in result["strings"] if s["inverter"] == 1]
    assert all(sum(centers[i] for i in s["module_ids"]) / len(s["module_ids"]) < 40 for s in first)
    per_mppt = {unit: sorted(len(r["string_ids"]) for r in result["mppt_currents"] if r["inverter"] == unit) for unit in (1, 2)}
    assert per_mppt == {1: [2] * 12, 2: [1] + [2] * 11}  # every MPPT gets one string before any gets a second
    assert result["mppt_currents"][0]["string_ids"] == ["S001", "S013"]
    assert result["mppt_currents"][0]["working_a"] == pytest.approx(34.8)
    assert result["mppt_currents"][0]["short_a"] == pytest.approx(37.71872096)
    assert result["checks"]["E05"]["status"] == "pass"
    assert result["checks"]["E06"]["status"] == "fail"
    assert result["checks"]["E07"]["status"] == "pass"


def test_per_inverter_ratio_increases_minimum_units_when_aggregate_initially_passes(project, monkeypatch):
    catalog = copy.deepcopy(electrical.equipment_catalog())
    catalog["inverters"][SUNGROW]["rated_ac_kw"] = 80
    monkeypatch.setattr(electrical, "equipment_catalog", lambda: catalog)
    # Initial two devices give aggregate 1.289, but the 8-string unit is 1.375.
    assert 375 * .55 / (2 * 80) == pytest.approx(1.2890625)
    assert 8 * 25 * .55 / 80 > 1.3
    result = electrical.calculate(project, design(375, 25), offline=True)
    assert result["inverter_count"] == 3  # Smallest count that makes every unit safe.
    assert [r["strings_count"] for r in result["per_inverter"]] == [5, 5, 5]
    assert [r["dc_ac_ratio"] for r in result["per_inverter"]] == pytest.approx([.859375] * 3)
    assert result["checks"]["E07"]["status"] == "fail"  # Undersizing is an economic reminder.
    assert result["checks"]["E07"]["level"] == "advice"
    assert result["candidates"][0]["hard_failures"] == 0
    assert result["checks"]["E07"]["value"] == pytest.approx(.859375)


def test_oversized_single_string_keeps_per_inverter_failure_even_if_aggregate_passes(project, monkeypatch):
    catalog = copy.deepcopy(electrical.equipment_catalog())
    catalog["inverters"][SUNGROW]["rated_ac_kw"] = 25
    monkeypatch.setattr(electrical, "equipment_catalog", lambda: catalog)
    result = electrical.calculate(project, design(100, 80), offline=True)
    assert result["inverter_count"] == 2 and result["dc_ac_ratio"] == pytest.approx(1.1)
    assert [r["strings_count"] for r in result["per_inverter"]] == [1, 0]
    assert [r["dc_ac_ratio"] for r in result["per_inverter"]] == pytest.approx([1.76, 0])
    assert result["checks"]["E07"]["status"] == "fail"
    assert result["checks"]["E07"]["level"] == "hard"
    assert "仍不能满足" in result["checks"]["E07"]["evidence"]
    assert result["candidates"][0]["failed_checks"]


@pytest.mark.parametrize('count',[104,280,350,520])
def test_ratio_below_one_is_only_advice_with_current_hundred_kw_catalog(project,count):
    result=electrical.calculate(project,design(count),offline=True)
    check=result['checks']['E07']
    assert result['dc_ac_ratio']<1 and check['status']=='fail' and check['level']=='advice'
    assert '更小功率的型号' in check['hint_zh']
    assert all(row['dc_ac_ratio']<=1.3 for row in result['per_inverter'])
    assert result['candidates'][0]['hard_failures']==sum(row['status']=='fail' for code,row in result['checks'].items() if code not in ('E06','E07'))


def test_auto_selection_prioritizes_hard_checks_over_target_distance(project, monkeypatch):
    catalog = copy.deepcopy(electrical.equipment_catalog())
    catalog['inverters'] = {key: catalog['inverters'][key] for key in (HUAWEI, SUNGROW)}
    catalog["inverters"][HUAWEI].update(rated_ac_kw=220 / 2 / 1.2, max_short_circuit_current_per_mppt_a=10)
    monkeypatch.setattr(electrical, "equipment_catalog", lambda: catalog)
    project.equipment.inverter_id = None
    result = electrical.calculate(project, design(400, 20), offline=True)
    assert result["inverter_id"] == SUNGROW
    rejected = next(c for c in result["candidates"] if c["inverter_id"] == HUAWEI)
    assert rejected["dc_ac_ratio"] == pytest.approx(1.2) and "E05" in rejected["failed_checks"]
    assert result["selection_reason"]
    catalog["inverters"][SUNGROW]["max_short_circuit_current_per_mppt_a"] = 10
    diagnosis = electrical.calculate(project, design(400, 20), offline=True)
    assert diagnosis["checks"]["E05"]["status"] == "fail" and diagnosis["candidates"]


def test_temperature_override_precedence_and_offline_nasa_metadata(project, monkeypatch):
    called = []
    def extremes(*args, **kwargs):
        called.append((args, kwargs))
        return dict(temp_min_c=-13.45, temp_max_c=42.06, min_date="2010-02-13", max_date="2022-08-22",
                    start_year=1996, end_year=2025, metadata={"data_file_sha256": "fixture"})
    monkeypatch.setattr(electrical, "load_nasa_daily_extremes", extremes)
    project.site.design_temp_max_c = None
    result = electrical.calculate(project, design(400, 20), offline=True)
    assert called[0][1] == {"start_year": 1996, "end_year": 2025, "offline": True}
    assert result["temperature"]["min_source"] == "用户覆盖"
    assert result["temperature"]["max_source"] == "NASA POWER 1996–2025"
    assert result["temperature"]["nasa"]["max_date"] == "2022-08-22"


def test_results_are_deterministic_and_catalog_missing_noct_is_explicit(project, monkeypatch):
    option = design(376)
    original = option.model_dump(mode="json")
    first = electrical.calculate(project, option, offline=True)
    assert first == electrical.calculate(project, option, offline=True)
    assert option.model_dump(mode="json") == original
    catalog = electrical.equipment_catalog()
    catalog["modules"][TRINA]["noct_c"] = "规格书未给出"
    monkeypatch.setattr(electrical, "equipment_catalog", lambda: catalog)
    with pytest.raises(GzError) as caught:
        electrical.calculate(project, option, offline=True)
    assert caught.value.error_code == "EQUIPMENT_PARAMETER_MISSING" and "noct_c" in caught.value.message_zh


@pytest.mark.parametrize("low,high", [(60, None), (None, -20)])
def test_partial_override_must_still_be_ordered_after_nasa_merge(project, low, high):
    project.site.design_temp_min_c, project.site.design_temp_max_c = low, high
    with pytest.raises(GzError) as caught:
        electrical.calculate(project, design(400, 20), offline=True)
    assert caught.value.error_code == "DESIGN_TEMPERATURE_INVALID"


def test_committed_nasa_extremes_drive_default_design_temperature(project):
    project.site.design_temp_min_c = project.site.design_temp_max_c = None
    result = electrical.calculate(project, design(400, 20), offline=True)
    temperature = result["temperature"]
    assert temperature["temp_min_c"] == -13.45 and temperature["temp_max_c"] == 42.06
    assert temperature["nasa"]["min_date"] == "2010-02-13"
    assert temperature["nasa"]["max_date"] == "2022-08-22"
    assert temperature["cell_hot_c"] == pytest.approx(70.81)
