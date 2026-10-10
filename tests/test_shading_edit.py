"""遮挡阈值编辑使用原版本分析，严格比较并拒绝损坏结果。"""

import copy
import hashlib
import json

import pytest

from guangzhu import layout, project as storage
from guangzhu.config import DATA_DIR
from guangzhu.layout import generate_layout
from guangzhu.models import GzError, LayoutParams


@pytest.fixture
def source(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    payload = json.loads((DATA_DIR / "demo/projects/changzhou-demo/project.json").read_text(encoding="utf-8"))
    payload["designs"] = []
    project = storage.save(payload)
    design = generate_layout(project, LayoutParams())
    design.modules = design.modules[:3]
    design.statistics.update(module_count=3, dc_kw=1.65)
    storage.save_design(project.id, design)
    analysis = {"version": 1, "modules": [{"id": m.id, "total_loss_pct": loss} for m, loss in zip(design.modules, (8.0, 8.1, 1.0))], "metadata": {}, "summary": {}}
    path = storage._path(project.id, "analysis/v1/shading.json")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(analysis), encoding="utf-8")
    return project.id, design, path, analysis


def test_threshold_strict_comparison_precedence_parent_immutability(source, monkeypatch):
    identifier, first, path, analysis = source
    original = storage._path(identifier, "designs/v1.json").read_bytes()
    storage.edit_design(identifier, 1, [{"op": "set_string_size", "modules_per_string": 20}], "已有分支", "rule")
    ops = [{"op": "remove_modules", "module_ids": [first.modules[2].id]},
           {"op": "remove_modules", "module_ids": [first.modules[0].id], "where": {"shading_loss_gt": 8, "zone_id": "不存在"}}]
    result = storage.edit_design(identifier, 1, ops, "遮挡过高", "agent")
    third = storage.load_design(identifier, result["version"])
    assert result["version"] == 3 and third.parent_version == 1
    assert [m.id for m in third.modules] == [first.modules[0].id]
    assert {m.id for m in third.removed_modules} == {first.modules[1].id, first.modules[2].id}
    assert all(m.reason == "遮挡过高" for m in third.removed_modules)
    assert "组件 3 → 1" in result["summary"] and third.statistics["dc_kw"] == pytest.approx(0.55)
    assert storage._path(identifier, "designs/v1.json").read_bytes() == original
    assert json.loads(path.read_text(encoding="utf-8")) == analysis
    for threshold, expected in ((0, []), (100, [m.id for m in first.modules])):
        edited = storage.edit_design(identifier, 1, [{"op": "remove_modules", "where": {"shading_loss_gt": threshold}}], "边界阈值", "rule")
        assert [m.id for m in storage.load_design(identifier, edited["version"]).modules] == expected
    second_analysis = copy.deepcopy(analysis)
    second_analysis["version"] = 2
    for item, loss in zip(second_analysis["modules"], (1.0, 2.0, 9.0)):
        item["total_loss_pct"] = loss
    second_path = storage._path(identifier, "analysis/v2/shading.json")
    second_path.parent.mkdir(parents=True)
    second_path.write_text(json.dumps(second_analysis), encoding="utf-8")
    monkeypatch.setattr(layout, "generate_layout", lambda active, params: first.model_copy(deep=True, update={"params": params}))
    root=storage._path(identifier)
    hashes=lambda:{str(file.relative_to(root)):hashlib.sha256(file.read_bytes()).hexdigest() for file in root.rglob('*') if file.is_file()}
    before=hashes()
    assert storage.next_version(identifier)==6
    with pytest.raises(GzError) as caught:
        storage.edit_design(identifier, 2, [{"op": "set_param", "name": "tilt_deg", "value": 15},
                            {"op": "remove_modules", "where": {"shading_loss_gt": 8}}], "同版本分析", "agent")
    assert caught.value.error_code=='DESIGN_EDIT_DEPENDENCY'
    assert caught.value.message_zh=='改参数会重新排板，请先单独改参数并重新分析，再删组件'
    assert hashes()==before and storage.next_version(identifier)==6


def test_threshold_missing_invalid_analysis_and_finite_input(source):
    identifier, first, path, analysis = source
    original = storage._path(identifier, "designs/v1.json").read_bytes()
    ops = [{"op": "remove_modules", "where": {"shading_loss_gt": 8}}]
    path.unlink()
    with pytest.raises(GzError) as caught:
        storage.edit_design(identifier, 1, ops, "遮挡过高", "agent")
    assert caught.value.error_code == "ANALYSIS_MISSING"
    assert caught.value.fix_hint == "先对该版本运行遮挡分析"
    bad_records = ["{", "[]", "null"]
    for update in ({"version": 2}, {"version": True}, {"modules": None},
                   {"modules": analysis["modules"][:-1]}, {"modules": analysis["modules"] * 2},
                   {"modules": [None]}, {"modules": [{"id": "wrong", "total_loss_pct": 0}]}):
        bad_records.append(json.dumps(analysis | update))
    for loss in (None, "0", True, float("nan"), float("inf"), -1, 101):
        invalid = copy.deepcopy(analysis)
        invalid["modules"][0]["total_loss_pct"] = loss
        bad_records.append(json.dumps(invalid))
    for contents in bad_records:
        path.write_text(contents, encoding="utf-8")
        with pytest.raises(GzError) as caught:
            storage.edit_design(identifier, 1, ops, "遮挡过高", "agent")
        assert caught.value.error_code == "ANALYSIS_INVALID"
    path.write_bytes(b"\xff")
    with pytest.raises(GzError) as caught:
        storage.edit_design(identifier, 1, ops, "遮挡过高", "agent")
    assert caught.value.error_code == "ANALYSIS_INVALID"
    path.write_text(json.dumps(analysis), encoding="utf-8")
    for threshold in (None, "8", True, float("nan"), float("inf"), float("-inf"), -0.1, 100.1):
        with pytest.raises(GzError) as caught:
            storage.edit_design(identifier, 1, [{"op": "remove_modules", "where": {"shading_loss_gt": threshold}}], "遮挡过高", "agent")
        assert caught.value.error_code == "DESIGN_EDIT_INVALID"
    assert storage.next_version(identifier) == 2
    assert storage._path(identifier, "designs/v1.json").read_bytes() == original
