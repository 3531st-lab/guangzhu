"""Synthetic copies of verified archives exercise page 3 and SHA ancestry."""
import hashlib
import json
import re
import pytest

from guangzhu.report.archive import load_archive
from guangzhu.report.view import render
from test_report_archive import archive, pending_archive, read, write


@pytest.fixture
def comparison_archive(archive):
    meta = read(archive / "run.json")
    capture = archive / meta["capture"]
    ledger = capture / "ledger.agnes.jsonl"
    events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    calls = {e["data"].get("toolUseId"): e for e in events if e["type"] == "tool/call"}
    for event in events:
        call = calls.get(event["data"].get("toolUseId"))
        if event["type"] == "tool/result" and call and call["data"]["name"].endswith("gz_compare_options"):
            result = json.loads(event["data"]["content"][0]["text"])
            result["current"] = dict(result["options"][0], name="当前方案", version=result["base_version"])
            result["recommended"] = {key: dict(version=3 if key == "balanced" else 9, why="测试推荐原因")
                                     for key in ("max_capacity", "fast_payback", "balanced")}
            result["options"][0]["violated_requirements"] = ["U03", "U02", "G03"]
            result["options"][1]["hard_pass"] = False
            event["data"]["content"][0]["text"] = json.dumps(result, ensure_ascii=False)
    ledger.write_text(''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in events), encoding="utf-8")
    for version, changes in [(12, dict(parent_version=11, reason="折中：自动修正 E08")),
                             (11, dict(parent_version=3, reason="折中：按 U03 删除 982 块"))]:
        path = capture / f"project/designs/v{version}.json"
        design = read(path) | changes
        write(path, design)
        manifest = read(capture / "run.json")
        manifest["artifacts"][path.relative_to(capture).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        write(capture / "run.json", manifest)
    return archive


def page3(context):
    context = dict(context, generated_at="2026-10-04T00:00:00+00:00")
    return re.findall(r'<section[^>]*>(.*?)</section>', render(context), re.S)[2]


def test_verified_candidate_ancestors_and_four_page_rows(comparison_archive):
    context = load_archive(comparison_archive)
    assert any(row["version"] == 11 for row in context.get("versions", [])), "read ancestors through verified artifacts"
    html = page3(context)
    assert html.count('<tr>') == 5
    assert html.index("当前方案") < html.index("多装")
    assert html.count("选定") == 1 and html.count("推荐") == 1
    count = next(row['statistics']['module_count'] for row in context['versions'] if row['version'] == 11)
    assert f"预算删板后{count:,}块" in html
    assert not any(code in html for code in ("E08", "S01", "U03"))
    assert "多装：" not in html and "折中：" not in html
    for phrase in ["超预算", "装机超上限", "通道不够", "硬性规则未过"]:
        assert phrase in html


def test_current_selected_mark_excludes_recommendation(comparison_archive):
    context = load_archive(comparison_archive)
    context["version"] = context["compare"]["current"]["version"]
    html = page3(context)
    assert "当前方案 · v3 选定" in html
    assert "推荐" not in html


def test_tampered_ancestor_is_rejected(comparison_archive):
    meta = read(comparison_archive / "run.json")
    path = comparison_archive / meta["capture"] / "project/designs/v11.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="SHA"):
        load_archive(comparison_archive)


def test_new_comparison_pending_wait_preserves_original_export_approval(comparison_archive):
    before = load_archive(comparison_archive)
    pending_archive(comparison_archive, {"gz_compare_options", "gz_export"})
    after = load_archive(comparison_archive)
    assert after["compare"] == before["compare"]
    assert after["approval"]["verdict"] == "allowed-once"
    assert page3(after).count('<tr>') == 5


def test_old_archives_page3_stays_three_rows(archive):
    context = load_archive(archive)
    assert page3(context).count('<tr>') == 4
    assert "当前方案" not in page3(context)


@pytest.mark.parametrize("missing_base", [False, True])
def test_current_and_old_candidates_never_inherit_parent_budget_reason(comparison_archive, missing_base):
    context = load_archive(comparison_archive)
    context['versions'] = [dict(version=6, parent_version=3, reason="多装"),
                           dict(version=3, parent_version=2, reason="E08,S01,U03", statistics=dict(module_count=1250)),
                           dict(version=2, parent_version=3, reason="初稿")]
    if missing_base:
        context['compare'].pop('base_version')
    assert '<small>' not in page3(context)
    context['compare'].pop('current')
    assert '<small>' not in page3(context)


@pytest.mark.parametrize("missing_base", [False, True])
@pytest.mark.parametrize("code,label", [("U03", "预算"), ("U02", "装机上限")])
def test_own_budget_capacity_notes_use_saved_count_and_cycle_protection(comparison_archive, missing_base, code, label):
    context = load_archive(comparison_archive)
    context['versions'] = [dict(version=6, parent_version=5, reason="多装：自动修正 E08"),
                           dict(version=5, parent_version=6, reason=f"多装：按 {code} 删除 982 块", statistics=dict(module_count=1250)),
                           dict(version=3, parent_version=None, reason="多装：按 U03 删除 1 块", statistics=dict(module_count=1250))]
    if missing_base:
        context['compare'].pop('base_version')
    html = page3(context)
    assert html.count('<small>') == 1 and f'{label}删板后1,250块' in html
    assert not any(value in html for value in ('E08', 'U02', 'U03', '多装：'))
    context['versions'][1].pop('statistics')
    assert '<small>' not in page3(context)
