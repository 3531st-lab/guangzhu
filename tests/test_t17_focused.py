"""T17 isolated contract tests; real physics evidence is owned by a separate driver."""
import json
import pytest

from guangzhu import analysis, electrical, layout, mcp_actions, orientation, project as storage, rules, structure
from guangzhu.config import ROOT
from guangzhu.models import GzError, validate_project


def candidate(version, dc=100, payback=4, energy=100000, **changes):
    return dict(name=f"方案{version}", version=version, dc_kw=dc, payback_years=payback,
                annual_kwh=energy, hard_pass=True, violated_requirements=[], **changes)


def recommend(current, options):
    function = getattr(mcp_actions, "recommend_options", None)
    assert callable(function), "T17 must expose a pure recommendation function"
    return function(current, options)


def test_recommendations_sort_metrics_and_filter_failures():
    current = candidate(3, 90, 4, 100000)
    options = [candidate(6, 120, 4.2, 130000), candidate(9, 100, 4, 120000), candidate(12, 110, 4.21, 150000)]
    result = recommend(current, options)
    assert {key: row["version"] for key, row in result.items()} == dict(max_capacity=6, fast_payback=9, balanced=6)
    options[0]["violated_requirements"] = ["U03"]
    options[1]["hard_pass"] = False
    result = recommend(current, options)
    assert result["balanced"]["version"] == 3
    assert result["max_capacity"]["version"] == 12


def test_recommendations_ties_current_and_lower_version():
    current = candidate(3)
    assert all(row["version"] == 3 for row in recommend(current, [candidate(6), candidate(9)]).values())
    current["hard_pass"] = False
    assert all(row["version"] == 6 for row in recommend(current, [candidate(9), candidate(6)]).values())


@pytest.mark.parametrize("payback", [None, 0])
def test_recommendations_unknown_and_zero_payback(payback):
    current = candidate(3, payback=payback)
    result = recommend(current, [candidate(6, payback=payback, energy=120000)])
    assert result["balanced"]["version"] == 6
    assert "Infinity" not in json.dumps(result, allow_nan=False)
    if payback is None:
        assert all("未算出" in row["why"] for row in result.values())
        assert "回本最短" not in result["fast_payback"]["why"]


def test_no_eligible_and_only_current():
    current = candidate(3)
    failed = candidate(6)
    failed["violated_requirements"] = ["L01"]
    assert all(row["version"] == 3 for row in recommend(current, [failed]).values())
    current["hard_pass"] = False
    assert all(row == dict(version=3, why="三套都不满足要求，沿用当前方案") for row in recommend(current, [failed]).values())


def source_project():
    return validate_project(json.loads((ROOT / "data/demo/projects/changzhou-demo/project.json").read_text(encoding="utf-8")))


def shadow(design):
    modules = [dict(id=m.id, total_loss_pct=0) for m in design.modules]
    return dict(version=design.version, modules=modules, summary=dict(avg_loss_pct=0, max_loss_pct=0), metadata={})


@pytest.mark.parametrize("orientation,tiers,azimuth", [("portrait", 1, 180), ("landscape", 2, 155)])
def test_shared_walkway_helper_matches_authoritative_rule(orientation, tiers, azimuth):
    project = source_project()
    project.requirements.structured.walkway_m_min = 2
    helper = getattr(rules, "walkway_check", None)
    assert callable(helper), "G03 geometry must be shared with compare"
    for every, width in [(0, 1), (1, 1), (1, 2), (999, 1)]:
        design = layout.generate_layout(project, dict(orientation=orientation, rows_per_rack=tiers,
                                       azimuth_deg=azimuth, walkway_every_n_rows=every, walkway_width_m=width))
        checked = rules.evaluate(project, design, shadow(design), electrical.calculate(project, design, offline=True),
                                 structure.calculate(project, design))
        row = next(item for item in checked["items"] if item["id"] == "G03")
        geometry = helper(project, design)
        assert geometry["value"] == row["value"]
        assert geometry["suggestion"] == row["suggestion"]
        assert geometry["status"] == row["status"]


@pytest.fixture
def comparison(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    project = source_project()
    project.id, project.designs = "focused-t17", []
    project.economics.capex_cny_per_w = 3
    project.roof.outline = [(0, 0), (24, 0), (24, 24), (0, 24)]
    project.roof.obstacles, project.roof.keepouts = [], []
    project.requirements.structured.keep_clear_ids = []
    project.requirements.structured.walkway_m_min = None
    storage.save(project)
    base = layout.generate_layout(project, dict(tilt_deg=25))
    storage.save_design(project.id, base)
    calls = []

    class Reuse:
        def __init__(self, p, design, **kwargs):
            if p.requirements.structured.walkway_m_min:
                checked = rules.evaluate(p, design, shadow(design), electrical.calculate(p, design, offline=True),
                                         structure.calculate(p, design))
                assert next(row for row in checked["items"] if row["id"] == "G03")["status"] != "fail"

        def analyze(self, design):
            return shadow(design)

    def analyzed(project_id, version, **kwargs):
        calls.append(version)
        design = storage.load_design(project_id, version)
        p = storage.load(project_id)
        dc = electrical.calculate(p, design, offline=True)["dc_kw"]
        unit = p.economics.capex_cny_per_w
        cash = dict(capex_cny=dc * 1000 * unit, params=dict(capex_cny_per_w=unit), payback_years=4, irr_pct=15)
        checked = rules.evaluate(p, design, shadow(design), electrical.calculate(p, design, offline=True),
                                 structure.calculate(p, design), cash)
        summary = dict(version=version, dc_kw=dc, yield_kwh=dict(p50=dc * 1000), economics=cash, shading=dict(avg_loss_pct=0))
        rules.save_result(project_id, version, "summary", summary)
        rules.save_result(project_id, version, "rules", checked)
        return summary

    monkeypatch.setattr(mcp_actions.weather, "load_nasa_hourly", lambda *a, **kw: (None, {}))
    monkeypatch.setattr(mcp_actions, "load_cec_equipment", lambda **kw: None)
    monkeypatch.setattr(mcp_actions.shading, "SiteShading", lambda *a, **kw: None)
    monkeypatch.setattr(mcp_actions.shading, "RemovalShading", Reuse)
    monkeypatch.setattr(mcp_actions.yieldsim, "simulate_pvlib_detailed", lambda *a, **kw: dict(specific_yield_kwh_kwp=1000 + kw["tilt"]))
    monkeypatch.setattr(mcp_actions, "irradiation_by_tilt", lambda *a, **kw: {angle: 1000 + angle for angle in range(36)})
    monkeypatch.setattr(analysis, "analyze", analyzed)
    analyzed(project.id, 1)
    calls.clear()
    return project, calls


@pytest.mark.parametrize("bounds,capacity,balanced,trials", [((15, 25), 15, 20, [19, 22, 25]),
                                                         ((15.2, 15.4), 15.2, 15.2, [15.2]),
                                                         ((20, 30), 20, 25, [24, 27, 30])])
def test_tilt_bounds_current_cache_and_stable_dedup(comparison, bounds, capacity, balanced, trials):
    project, calls = comparison
    project.requirements.structured.tilt_deg_range = bounds
    storage.save(project)
    result = mcp_actions._compare_options(project.id, 1, offline=True)
    assert result["options"][0]["tilt_deg"] == capacity
    assert result["options"][2]["tilt_deg"] == balanced
    assert [row["tilt_deg"] for row in result["tilt_trials"]] == trials
    assert all(bounds[0] <= row["tilt_deg"] <= bounds[1] for row in result["options"])
    assert result["current"]["version"] == 1 and 1 not in calls
    assert len(analysis.serialized(result).encode("utf-8")) <= 2048


def test_missing_current_analysis_is_explicit(comparison):
    project, _ = comparison
    storage._path(project.id, "analysis/v1/summary.json").unlink()
    with pytest.raises(GzError, match="分析"):
        mcp_actions._compare_options(project.id, 1, offline=True)


def test_geometry_precedes_shading_and_repairs_have_normal_parents(comparison):
    project, _ = comparison
    project.requirements.structured.walkway_m_min = 2
    storage.save(project)
    result = mcp_actions._compare_options(project.id, 1, offline=True)
    repaired = 0
    for row in result["options"]:
        assert "G03" not in row["violated_requirements"]
        design = storage.load_design(project.id, row["version"])
        reasons = []
        while design.version != 1:
            assert design.author == "agent"
            reasons.append(design.reason)
            original = design
            design = storage.load_design(project.id, design.parent_version)
        # The stored initial candidate preserves its own layout, azimuth and winter window.
        checks = [rules.walkway_check(project, view) for _, view in orientation.views(original)]
        if any(check["status"] == "fail" for check in checks):
            repaired += 1
            assert any("G03" in reason for reason in reasons)
    assert repaired > 0


def test_upper_and_budget_sequential_deletion_do_not_overdelete(comparison):
    project, _ = comparison
    project.requirements.structured.capacity_kw_max = 60
    project.requirements.structured.budget_cny_max = 60 * 1000 * project.economics.capex_cny_per_w
    storage.save(project)
    result = mcp_actions._compare_options(project.id, 1, offline=True)
    for row in result["options"]:
        assert row["dc_kw"] <= 60
        assert row["dc_kw"] > 40
        assert not set(row["violated_requirements"]) & {"U02", "U03"}
        design = storage.load_design(project.id, row["version"])
        while design.version != 1:
            if "U02" in design.reason or "U03" in design.reason:
                parent = storage.load_design(project.id, design.parent_version)
                assert f"删除 {len(parent.modules) - len(design.modules)} 块" in design.reason
            design = storage.load_design(project.id, design.parent_version)


def test_unsuggestible_user_and_hard_failures_remain_visible(comparison):
    project, _ = comparison
    project.requirements.structured.capacity_kw_max = 60
    project.requirements.structured.payback_years_max = 3
    project.roof.load_capacity_kn_m2 = .01
    storage.save(project)
    result = mcp_actions._compare_options(project.id, 1, offline=True)
    assert all(row["hard_pass"] is False and {"L01", "U04"} <= set(row["violated_requirements"]) for row in result["options"])


def test_walkway_one_row_is_not_a_fake_failure():
    project = source_project()
    design = layout.generate_layout(project, dict(tilt_deg=25))
    design.modules = [m for m in design.modules if m.row == min(m.row for m in design.modules)]
    project.requirements.structured.walkway_m_min = 2
    assert rules.walkway_check(project, design)["status"] == "na"
    assert rules.walkway_check(project, design)["note"] == "只有一排，没有排间通道"


def test_fastest_loss_filter_has_matching_shading_after_budget_pruning(comparison):
    project, _ = comparison
    project.requirements.structured.budget_cny_max = 20 * 1000 * project.economics.capex_cny_per_w
    storage.save(project)
    result = mcp_actions._compare_options(project.id, 1, offline=True)
    fastest = result["options"][1]
    assert fastest["capex_cny"] <= project.requirements.structured.budget_cny_max
    design = storage.load_design(project.id, fastest["version"])
    reasons = []
    while design.version != 1:
        reasons.append(design.reason)
        if "移除遮挡大于3%" in design.reason:
            shade = json.loads(storage._path(project.id, f"analysis/v{design.parent_version}/shading.json").read_text(encoding="utf-8"))
            parent = storage.load_design(project.id, design.parent_version)
            assert shade["version"] == parent.version
            assert {row["id"] for row in shade["modules"]} == {m.id for m in parent.modules}
        design = storage.load_design(project.id, design.parent_version)
    assert any("U03" in reason for reason in reasons)
