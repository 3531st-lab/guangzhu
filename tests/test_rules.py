"""T06 hard failures use real layout/electrical/load and executable edits."""

import copy
import json

import pytest
import requests

from guangzhu import electrical, project as storage, rules, structure
from guangzhu.config import DATA_DIR
from guangzhu.layout import generate_layout
from guangzhu.models import LayoutParams, StructuredRequirements, validate_project


@pytest.fixture
def baseline(monkeypatch, tmp_path):
    def unexpected(*args, **kwargs):
        pytest.fail("Rule acceptance tests must stay offline")
    monkeypatch.setattr(requests.Session, "request", unexpected)
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    project = validate_project(json.loads((DATA_DIR / "demo/projects/changzhou-demo/project.json").read_text(encoding="utf-8")))
    project.equipment.inverter_id = "sungrow-sg100cx-p2"
    project.roof.load_capacity_kn_m2 = 2  # Isolate rule contracts from T31's intentional default-roof L01 failure.
    design = generate_layout(project, LayoutParams(walkway_every_n_rows=2))
    assert len(design.modules) == 390
    return project, design


def shadows(design, losses=None):
    losses = losses or {}
    modules = [{"id": m.id, "total_loss_pct": losses.get(m.id, 0)} for m in design.modules]
    return {"version": design.version, "modules": modules,
            "summary": {"avg_loss_pct": sum(m["total_loss_pct"] for m in modules) / len(modules) if modules else 0}}


def evaluate(project, design, shading=None, electric=None):
    return rules.evaluate(project, design, shading or shadows(design),
                          electric or electrical.calculate(project, design, offline=True), structure.calculate(project, design))


def item(result, identifier):
    return next(row for row in result["items"] if row["id"] == identifier)


def failed(result, identifier):
    row = item(result, identifier)
    assert row["status"] == "fail" and row["level"] == "hard", row
    assert row["source_ref"] and row["evidence"] and row["hint_zh"]
    return row


def execute(project, design, operation, shading=None):
    """Exercise gz_edit_design semantics entirely under pytest's temporary root."""
    project = project.model_copy(deep=True)
    project.id = "rule-case-" + operation["op"]
    # Each scenario starts an independent version chain in its own fixture path.
    project.id += "-" + str(len(list(storage.PROJECTS_DIR.glob("*"))))
    project.designs = []
    storage.save(project)
    storage.save_design(project.id, design)
    if shading is not None:
        path = storage._path(project.id, "analysis/v1/shading.json")
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(shading), encoding="utf-8")
    original = storage._path(project.id, "designs/v1.json").read_bytes()
    result = storage.edit_design(project.id, 1, [operation], "执行失败规则的建议", "rule")
    assert result["version"] == 2
    assert storage._path(project.id, "designs/v1.json").read_bytes() == original
    return storage.load_design(project.id, 2)


def translated(module, dx, dy):
    module.center = (module.center[0] + dx, module.center[1] + dy, module.center[2])
    module.corners = tuple((x + dx, y + dy, z) for x, y, z in module.corners)


def test_layout_and_shading_hard_failures_have_operations_that_fix_the_target(baseline):
    original_project, original_design = baseline
    covered = set()
    for code in ("G01", "G03", "G04", "G05", "G06", "S01"):
        project, design = original_project.model_copy(deep=True), original_design.model_copy(deep=True)
        losses = {}
        first = design.modules[0]
        if code == "G01":
            translated(first, -first.center[0] - 1, 0)
            expected = {"op": "remove_modules", "module_ids": [first.id]}
        elif code == "G03":
            project.requirements.structured.walkway_m_min = 3
            design.params.walkway_width_m = .4
            expected = {"op": "set_param", "name": "walkway_width_m", "value": 3}
        elif code == "G04":
            translated(first, 22 - first.center[0], 10 - first.center[1])
            expected = {"op": "remove_modules", "where": {"zone_id": "sky-1"}}
        elif code == "G05":
            project.requirements.structured.tilt_deg_range = (10, 20)
            expected = {"op": "set_param", "name": "tilt_deg", "value": 20}
        elif code == "G06":
            project.requirements.structured.edge_setback_m_min = 2
            expected = {"op": "set_param", "name": "edge_setback_m", "value": 2}
        else:
            losses = {first.id: 8.1, design.modules[1].id: 8.0}
            expected = {"op": "remove_modules", "where": {"shading_loss_gt": 8.0}}
        shading = shadows(design, losses)
        row = failed(evaluate(project, design, shading), code)
        assert row["suggestion"] == expected
        if code == "G01":
            assert row["value"] == 1 and row["limit"] == 0
        elif code == "G03":
            assert row["value"] == pytest.approx(2.005,abs=.002) and row["limit"] == 3
        elif code == "G04":
            assert row["value"] == ["sky-1"]
        elif code == "G05":
            assert row["value"] == 25 and row["limit"] == (10, 20)
        elif code == "G06":
            assert row["value"]["edge_setback_m"] == 1 and row["limit"]["edge_setback_m"] == 2
        else:
            assert row["value"] == 8.1 and row["limit"] == 8.0 and "示意" in row["note"]
        repaired = execute(project, design, row["suggestion"], shading)
        assert item(evaluate(project, repaired, shadows(repaired, losses)), code)["status"] == "pass"
        if code == "S01":
            assert first.id not in {m.id for m in repaired.modules}
            assert design.modules[1].id in {m.id for m in repaired.modules}  # Strictly greater than 8%.
        covered.add(code)
    assert covered == {"G01", "G03", "G04", "G05", "G06", "S01"}

    # The other clearance parameter has its own actionable remedy.
    project = original_project.model_copy(deep=True)
    project.requirements.structured.obstacle_clearance_m_min = 1
    row = failed(evaluate(project, original_design), "G06")
    assert row["suggestion"] == {"op": "set_param", "name": "obstacle_clearance_m", "value": 1}
    repaired = execute(project, original_design, row["suggestion"])
    assert item(evaluate(project, repaired), "G06")["status"] == "pass"

    # T27: G02 checks the design's own window; only an actual pitch defect fails.
    crowded = generate_layout(original_project, LayoutParams(walkway_every_n_rows=2, winter_window_hours=(10, 14)))
    assert item(evaluate(original_project, crowded), 'G02')['status'] == 'pass'
    for module in crowded.modules:
        translated(module, 0, -.5 * (module.row - 1))
    row = item(evaluate(original_project, crowded), "G02")
    assert row["status"] == "fail" and row["level"] == "advice" and row["value"] < row["limit"]
    assert row["suggestion"] == {"op": "set_param", "name": "winter_window_hours", "value": [10, 14]}
    assert "2024" in row["note"] and "宜" in row["note"] and "删除" in row["note"]
    repaired = execute(original_project, crowded, row["suggestion"])
    assert item(evaluate(original_project, repaired), "G02")["status"] == "pass"


def test_all_electrical_hard_failures_preserve_real_numbers_and_fixable_suggestions(baseline, monkeypatch):
    project, original = baseline
    covered = set()
    for code, size in (("E01", 27), ("E02", 37), ("E03", 6), ("E04", 29), ("E08", 7)):
        design = original.model_copy(deep=True)
        design.modules_per_string = size
        electric = electrical.calculate(project, design, offline=True)
        row = failed(evaluate(project, design, electric=electric), code)
        assert row["value"] == electric["checks"][code]["value"]
        if code in {"E01", "E02", "E03", "E04"}:
            expected_size = 7 if code == "E03" else 26
            assert row["suggestion"] == {"op": "set_string_size", "modules_per_string": expected_size}
            assert row["limit"] == {"E01": 1100, "E02": 1500, "E03": 180, "E04": 1000}[code]
            assert (row["value"] < row["limit"]) if code == "E03" else (row["value"] > row["limit"])
        elif code == "E08":
            assert row["value"] == 5 and row["limit"] == 0
            assert row["suggestion"] == {"op": "remove_modules", "module_ids": electric["unused_modules"]}
            assert set(electric["unused_modules"]).isdisjoint(i for s in electric["strings"] for i in s["module_ids"])
        if row["suggestion"] is not None:
            repaired = execute(project, design, row["suggestion"])
            assert item(evaluate(project, repaired), code)["status"] == "pass"
        covered.add(code)

    # Simulate a datasheet with unsafe per-MPPT Isc; never alter the CSV.
    catalog = copy.deepcopy(electrical.equipment_catalog())
    catalog["inverters"][project.equipment.inverter_id]["max_short_circuit_current_per_mppt_a"] = .1
    with monkeypatch.context() as patch:
        patch.setattr(electrical, "equipment_catalog", lambda: catalog)
        row = failed(evaluate(project, original), "E05")
    assert row["limit"] == .1 and row["value"] == pytest.approx(18.85936048)
    assert row["suggestion"] is None and "更换型号" in row["hint_zh"] and "每路串数" in row["hint_zh"]
    assert item(evaluate(project, original), "E05")["status"] == "pass"
    covered.add("E05")

    # An explicit 80-module string on a synthetic 25kW device overloads each unit,
    # even though aggregate capacity is safe; the upper bound remains hard.
    catalog = copy.deepcopy(electrical.equipment_catalog())
    catalog['inverters'][project.equipment.inverter_id]['rated_ac_kw'] = 25
    over = original.model_copy(deep=True)
    over.modules_per_string = 80
    with monkeypatch.context() as patch:
        patch.setattr(electrical,'equipment_catalog',lambda:catalog)
        electric = electrical.calculate(project,over,offline=True)
        row = failed(evaluate(project,over,electric=electric),'E07')
    assert row['value']==pytest.approx(214.5/(7*25)) and row['limit']==[1,1.3]
    assert max(r['dc_ac_ratio'] for r in electric['per_inverter'])==pytest.approx(1.76)
    assert row['suggestion'] is None and '更换型号' in row['hint_zh']
    covered.add('E07')

    electric = electrical.calculate(project, original, offline=True)
    # Deliberately attach two unequal strings to one MPPT; precomputed E09 was pass.
    electric['strings'][1]['mppt'] = electric['strings'][0]['mppt']
    electric['strings'][1]['inverter'] = electric['strings'][0]['inverter']
    same_mppt = [s for s in electric["strings"] if (s["inverter"], s["mppt"]) == (1, 1)]
    assert len(same_mppt) == 2 and electric["checks"]["E09"]["status"] == "pass"
    same_mppt[1]["module_ids"].pop()
    row = failed(evaluate(project, original, electric=electric), "E09")
    assert [25, 26] in row["value"]  # Must derive lengths rather than trust the precomputed pass.
    assert row["suggestion"] == {"op": "set_string_size", "modules_per_string": 26}
    repaired = execute(project, original, row["suggestion"])
    assert item(evaluate(project, repaired), "E09")["status"] == "pass"
    covered.add("E09")
    assert covered == {"E01", "E02", "E03", "E04", "E05", "E07", "E08", "E09"}


def test_ratio_lower_warning_and_aggregate_upper_failure_have_distinct_levels(baseline):
    project,original=baseline
    smaller=original.model_copy(deep=True)
    smaller.modules=smaller.modules[:280]
    smaller.modules_per_string=20
    electric=electrical.calculate(project,smaller,offline=True)
    checked=evaluate(project,smaller,electric=electric)
    warning=item(checked,'E07')
    assert warning['value']==pytest.approx(154/199.98) and warning['status']=='fail' and warning['level']=='advice'
    assert checked['hard_failed']==0 and checked['warnings']==1
    assert '逆变器容量偏大' in warning['hint_zh'] and '更小功率' in warning['hint_zh']
    # Exercise a deliberately unsafe aggregate diagnosis returned by an upstream
    # electrical check; a lower-bound warning must never define the upper policy.
    electric['checks']['E07'].update(value=1.4,status='fail',level='hard')
    upper=item(evaluate(project,smaller,electric=electric),'E07')
    assert upper['value']==1.4 and upper['level']=='hard' and upper['status']=='fail'


def test_load_capacity_limits_na_advice_summary_traceability_and_purity(baseline):
    project, design = baseline
    low_roof = project.model_copy(deep=True)
    low_roof.roof.load_capacity_kn_m2 = .1
    row = failed(evaluate(low_roof, design), "L01")
    # Review fix: ballast would overload this roof, so the racks are anchored; module and rack (34.6 kg) alone still exceed 0.1.
    assert row["value"] == pytest.approx(34.6 * .00981 / 2.3680589896677295) and row["limit"] == .1
    assert row["suggestion"] is None and "不能减少抗风所需压块" in row["hint_zh"] and "复核" in row["hint_zh"]

    lower = project.model_copy(deep=True)
    lower.requirements.structured.capacity_kw_min = 215
    row = failed(evaluate(lower, design), "U01")
    assert row["value"] == 214.5 and row["limit"] == 215 and row["suggestion"] is None
    assert "倾角" in row["hint_zh"] and "横放" in row["hint_zh"]

    upper = project.model_copy(deep=True)
    upper.requirements.structured.capacity_kw_max = 212.8
    losses = {m.id: loss for m, loss in zip(design.modules[:4], (5, 7, 6, 4))}
    row = failed(evaluate(upper, design, shadows(design, losses)), "U02")
    assert row["value"] == 214.5 and row["limit"] == 212.8
    expected_ids = [design.modules[i].id for i in (1, 2, 0, 3)]
    assert row["suggestion"] == {"op": "remove_modules", "where": {"worst_count": len(expected_ids)}}
    repaired = execute(upper, design, row["suggestion"], shadows(design, losses))
    assert item(evaluate(upper, repaired), "U02")["status"] == "pass"
    assert {m.id for m in design.modules} - {m.id for m in repaired.modules} == set(expected_ids)
    assert len(repaired.modules) == 386 and 387 * .55 > 212.8  # Delete exactly the necessary number.

    # No user requirements means na, not pass; 4% is advice-only shading loss.
    unconstrained = project.model_copy(deep=True)
    unconstrained.requirements.structured = StructuredRequirements()
    # Explicit short-string override still exercises advice-only double-string current.
    design = design.model_copy(deep=True)
    design.modules = design.modules[:384]
    design.modules_per_string = 8
    design.statistics.update(module_count=384, dc_kw=211.2)
    shading = shadows(design, {m.id: 4 for m in design.modules})
    electric, load = electrical.calculate(unconstrained, design, offline=True), structure.calculate(unconstrained, design)
    before = (unconstrained.model_dump(mode="json"), design.model_dump(mode="json"), copy.deepcopy(shading), copy.deepcopy(electric), copy.deepcopy(load))
    result = rules.evaluate(unconstrained, design, shading, electric, load)
    assert result == rules.evaluate(unconstrained, design, shading, electric, load)
    assert before == (unconstrained.model_dump(mode="json"), design.model_dump(mode="json"), shading, electric, load)
    assert {row["id"] for row in result["items"] if row["status"] == "na"} == {"G03", "G04", "G05", "G06", "U01", "U02", 'W01'}
    # Review fix: inverter blocks and on-roof placement keep these 8-module strings within the 2% DC drop.
    assert {row["id"] for row in result["items"] if row["status"] == "fail"} == {"E06", "S02"}
    assert {key: result[key] for key in ("total", "passed", "hard_failed", "warnings", "na")} == {
        "total": 23, "passed": 14, "hard_failed": 0, "warnings": 2, "na": 7}
    assert item(result, "E06")["value"] == pytest.approx(34.8) and item(result, "E06")["limit"] == 30
    assert item(result, "S02")["value"] == 4 and item(result, "S02")["limit"] == 3
    assert item(result, "S01")["status"] == "pass" and item(result, "S02")["suggestion"] is None
    fields = {"id", "name_zh", "category", "source_type", "source_ref", "level", "status", "value", "limit", "unit", "evidence", "suggestion", "hint_zh", "note"}
    for row in result["items"]:
        assert fields <= row.keys() and row["source_ref"] and row["evidence"]
        assert row["source_type"] in {"用户要求", "国家标准", "厂家规格书", "行业做法", "设计假设"}
        assert row["category"] in {"layout", "shading", "electrical", "structure", "requirement", "economics"}
    categories = [(r["status"], r["level"]) for r in result["items"]]
    assert categories[:2] == [("fail", "advice"), ("fail", "advice")]
    assert all(status == "pass" for status, _ in categories[2:16])
    assert all(status == "na" for status, _ in categories[16:])
    # Hard failures must sort before advice, which precedes passing/na rules.
    hard_result = evaluate(low_roof, design, shading)
    assert hard_result['items'][0]['id'] == 'L01' and hard_result["hard_failed"] == 1
    assert [r['level'] for r in hard_result['items'][1:3]] == ['advice', 'advice'] and hard_result["warnings"] == 2


def test_existing_row_gaps_count_as_walkways_and_single_row_is_na(baseline):
    project,_=baseline
    design=generate_layout(project,LayoutParams(walkway_every_n_rows=0))
    row=item(evaluate(project,design),'G03')
    assert row['status']=='pass' and row['value']==pytest.approx(2.005,abs=.002)
    assert row['suggestion'] is None and '前后排最小净距' in row['evidence'] and '≥ 要求 1 m' in row['evidence']
    design.modules=[m for m in design.modules if m.row==1]
    row=item(evaluate(project,design),'G03')
    assert row['status']=='na' and row['note']=='只有一排，没有排间通道'


def test_walkways_use_actual_selected_gaps_instead_of_parameter_width(baseline):
    import math
    project,design=baseline
    design=design.model_copy(deep=True)
    design.modules=[m for m in design.modules if m.row<=3]
    projected=2.384*math.cos(math.radians(25))
    front={r:next(m.corners[0][1] for m in design.modules if m.row==r) for r in (1,2,3)}
    # Two real gaps: 0.5m after row1, 1.5m after row2. Only the latter is designated.
    positions={1:front[1],2:front[1]+projected+.5,3:front[1]+2*projected+2}
    for module in design.modules:translated(module,0,positions[module.row]-front[module.row])
    design.params.walkway_every_n_rows=2
    design.params.walkway_width_m=.1
    row=item(evaluate(project,design),'G03')
    assert row['status']=='pass' and row['value']==pytest.approx(1.5,abs=.002)
    design.params.walkway_every_n_rows=0
    row=failed(evaluate(project,design),'G03')
    assert row['value']==pytest.approx(.5,abs=.002) and row['limit']==1
