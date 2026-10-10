"""T22: the owner's answers before construction become eight plain checks that travel with the record into the result page and the
proposal, and the finished designs of several buildings are read back from their verified exports for the park view."""
import json
from pathlib import Path
import re
import shutil

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from guangzhu import api, park, sitecheck
from guangzhu.brief import BriefSpec, render_brief
from guangzhu.config import API_ORIGIN, API_PORT
from guangzhu.models import SiteFacts
from guangzhu.report.archive import load_archive
from guangzhu.report.view import render

ROOT = Path(__file__).resolve().parents[1]
RISKY = dict(roof_type="metal", roof_age_years=12, core="foam", skylights=True, owned=False, transformer_kva=150, monthly_kwh=10000, shifts=1,
             export_allowed=False)
GOOD = dict(roof_type="concrete", roof_age_years=3, core="rockwool", skylights=False, owned=True, transformer_kva=400, monthly_kwh=30000,
            shifts=2, export_allowed=True)
SUMMARY = dict(dc_kw=228.8, electrical=dict(dc_ac_ratio=1.1441), yield_kwh=dict(p50=258175.3483))  # exported v12 of gz-t11-changzhou-006
PARAMS = dict(self_use_ratio=0.8, price_export_cny_kwh=0.391)
ITEMS = ["屋面类型", "屋面年限", "夹芯板", "采光带", "厂房产权", "变压器", "用电量", "余电上网"]


def texts(facts, summary=SUMMARY, params=PARAMS):
    return {row["item"]: (row["status"], row["text"]) for row in sitecheck.rows(facts, summary, params)}


def test_blank_answers_are_eight_questions_to_ask():
    rows = sitecheck.rows(None, SUMMARY, PARAMS)
    assert [r["item"] for r in rows] == ITEMS + ['并网电压'] and {r["status"] for r in rows} == {"ask"}
    assert texts(None)["用电量"][1] == "账里的自用比例 80% 是估的，填了月用电量才能看合不合理"
    assert texts(None)["变压器"][1] == "问厂里电工变压器多大：逆变器合计不能超过变压器能接的量"
    assert sitecheck.flags(None) == dict(risk=[], ask=ITEMS)


def test_risky_answers_name_each_risk_with_numbers_from_the_version():
    rows = texts(RISKY)
    assert {rows[item][0] for item in ITEMS} == {"risk"}
    assert rows['并网电压'][0] == 'ask' and '380 V' in rows['并网电压'][1]
    assert rows["屋面类型"][1].startswith("彩钢瓦屋面：本方案按混凝土平屋顶压块算，彩钢瓦要顺坡平铺、用夹具")
    assert rows["屋面年限"][1].startswith("屋面已用 12 年：光伏要用 25 年（到时屋面 37 年），先查防水和锈蚀")
    assert rows["变压器"][1] == "逆变器超过变压器：逆变器合计 200 kW，是变压器 150 kVA 的 133%，接不进去，要减装机或给变压器扩容"
    assert rows["用电量"][1] == ("自用比例偏高：光伏一年约发 25.8 万度，是工厂一年用电（12.0 万度）的 215%；自用比例最多约 46%，账里按 80% 算，"
                              "回本会变长；单班按周一至周六8–17时生产，其余时段按20%示意负荷；余电上网或被限")
    assert rows["余电上网"][1] == "只能自用不上网：要装防逆流，用不完的电被限掉；账里有 20% 的电按上网算了收入，实际拿不到，回本会变长"
    # Before any design exists only the answers themselves can be judged.
    assert sitecheck.flags(RISKY) == dict(risk=["彩钢瓦屋面", "屋面已用 12 年", "泡沫芯夹芯板", "有采光带", "厂房是租的", "只能自用不上网"], ask=[])
    assert texts(RISKY, {}, {})["变压器"] == ("ok", "变压器 150 kVA，方案出来后对照逆变器容量")


def test_good_answers_pass_and_the_reminder_line_is_marked_illustrative():
    rows = texts(GOOD)
    assert {rows[item][0] for item in ITEMS} == {"ok"}
    assert rows['并网电压'][0] == 'ask' and '阈值示意' in rows['并网电压'][1]
    assert rows["变压器"][1] == "逆变器合计 200 kW，是变压器 400 kVA 的 50%"
    assert rows["用电量"][1] == "光伏一年约发 25.8 万度，是工厂一年用电（36.0 万度）的 72%"
    assert rows["余电上网"][1] == "可以余电上网；新建项目的上网电价按市场价，账里的 0.391 元/度是占位"
    assert texts(dict(GOOD, transformer_kva=240))["变压器"] == (
        "risk", "逆变器接近变压器容量：逆变器合计 200 kW，是变压器 240 kVA 的 83%，要问供电公司能接多少（80% 是示意提醒线）")


def brief_text(**changes):
    return render_brief(dict(template="changzhou-demo", id="t22-brief", text="6 年回本", **changes))


def payload(text):
    return json.loads(text.split("```json\n")[1].split("\n```")[0])


def test_brief_carries_answers_only_when_some_were_given():
    plain = brief_text()
    assert '"facts"' not in plain and brief_text(facts={}) == plain
    data = payload(brief_text(facts=RISKY))
    assert list(data) == ["brief", "project", "requirements", "economics", "facts", "run"] and data["facts"] == RISKY
    # The AI copies one ready line: on 10/6 it read the raw fields itself and took the blank 余电上网 for "只能自用".
    real = dict(roof_type="concrete", roof_age_years=12, core="none", skylights=True, owned=False, transformer_kva=630, monthly_kwh=30000, shifts=1)
    lines = brief_text(facts=real).split("\n")
    assert lines[lines.index("我的要求：6 年回本") + 1] == "开工前问答——要当心：屋面已用 12 年、有采光带、厂房是租的；没填：余电上网（第八段照抄这两项，不改写、不推断）"
    assert "要当心：彩钢瓦屋面、屋面已用 12 年、泡沫芯夹芯板、有采光带、厂房是租的、只能自用不上网；没填：无（" in brief_text(facts=RISKY)
    assert "开工前问答——要当心：无；没填：无（" in brief_text(facts=GOOD) and "开工前问答" not in plain
    with pytest.raises(ValidationError):
        BriefSpec(template="changzhou-demo", id="t22-brief", text="6 年回本", facts=dict(roof_type="wood"))
    client = TestClient(api.app, base_url=f"http://127.0.0.1:{API_PORT}", headers={"origin": API_ORIGIN})
    reply = client.post("/api/brief", json=dict(template="changzhou-demo", id="t22-brief-api", text="6 年回本", facts=dict(shifts=5)))  # 4 = continuous, since T23
    assert reply.status_code == 422 and reply.json()["errors"] == ["请检查开工前问答的格式和范围"]


def ledger(path, *messages):
    events = [dict(seq=1, id="start", type="session/start", data=dict(key="session"))]
    events += [dict(seq=index, id=f"m{index}", type="user/message", data=dict(content=[dict(type="text", text=text)]))
               for index, text in enumerate(messages, 2)]
    path.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n", encoding="utf-8")
    return path


def test_answers_in_the_sent_brief_reach_the_record(tmp_path):
    assert api.brief_facts(ledger(tmp_path / "a.jsonl", brief_text(facts=RISKY))) == SiteFacts(**RISKY).model_dump()
    assert api.brief_facts(ledger(tmp_path / "b.jsonl", brief_text())) is None
    assert api.brief_facts(ledger(tmp_path / "c.jsonl", "继续")) is None
    broken = brief_text(facts=RISKY).replace('"roof_type":"metal"', '"roof_type":"wood"')
    assert api.brief_facts(ledger(tmp_path / "d.jsonl", broken)) is None


def test_result_page_and_proposal_check_the_answers_against_the_exported_version(monkeypatch):
    original = api.record
    monkeypatch.setattr(api, "record", lambda folder: (lambda c, m, v: (c, dict(m, facts=RISKY), v))(*original(folder)))
    result = api.result_data("t11-changzhou-006", folder=api.run_folder("gz-t11-changzhou-006"))
    assert result["facts"] == RISKY and [r["item"] for r in result["site_checks"]] == ITEMS + ['并网电压']
    assert {r["item"]: r["text"] for r in result["site_checks"]} == {item: text for item, (_, text) in texts(RISKY).items()}
    plain = original(api.run_folder("gz-t11-changzhou-006"))
    assert "facts" not in plain[1]
    context = load_archive(ROOT / "runs/gz-t11-changzhou-006")
    context.update(generated_at="2026-10-06T00:00:00+08:00", regenerated=True, facts=RISKY)
    page = re.search(r'<h1 data-topic="开工前要核实的事">实施前核实清单</h1>(.*?)</section>', render(context), re.S)[1]
    assert page.count("有风险") == 8 and "彩钢瓦屋面" in page and "是变压器 150 kVA 的 133%" in page and "示意提醒线" in page
    context["facts"] = None
    page = re.search(r'<h1 data-topic="开工前要核实的事">实施前核实清单</h1>(.*?)</section>', render(context), re.S)[1]
    assert page.count("没填") >= 8 and "这次没有填开工前问答" in page


def entry(run_id, folder=None, showcase=False, facts=None):
    folder = folder or ROOT / "runs" / run_id
    meta, verification = (json.loads((folder / name).read_text(encoding="utf-8")) for name in ("run.json", "verification.json"))
    return dict(run_id=run_id, version=verification["verified_exports"][-1]["version"], showcase=showcase), folder / meta["capture"], dict(meta, **(
        dict(facts=facts) if facts else {}))


def test_park_reads_verified_exports_ticks_the_newest_run_per_roof_and_skips_tampered_ones(tmp_path):
    copy = tmp_path / "gz-t14-lshape-001"
    shutil.copytree(ROOT / "runs/gz-t14-lshape-001", copy)
    summary = next(copy.glob("captures/*/project/exports/v3/summary.json"))
    summary.write_text(summary.read_text(encoding="utf-8") + " ", encoding="utf-8")
    result = park.overview([entry("gz-t11-changzhou-006", facts=RISKY), entry("gz-changzhou-demo-1004-1514"),
                            entry("gz-t14-lshape-001"), entry("showcase-copy", ROOT / "runs/gz-t14-lshape-001", showcase=True),
                            entry("tampered", copy)])
    assert result["skipped"] == ["tampered"]
    rows = {row["run_id"]: row for row in result["buildings"]}
    assert {key: row["default"] for key, row in rows.items()} == {
        "gz-t11-changzhou-006": False, "gz-changzhou-demo-1004-1514": True, "gz-t14-lshape-001": True, "showcase-copy": False}
    demo, lshape = rows["gz-changzhou-demo-1004-1514"], rows["gz-t14-lshape-001"]
    assert (demo["version"], demo["dc_kw"], demo["modules"], len(demo["panels"]), demo["capex_cny"]) == (12, 228.8, 416, 416, 592592.0)
    assert demo["payback_years"] == 4.15658298371715 and abs(demo["ac_kw"] - 228.8 / 1.1441) < 1e-9 and len(demo["net_cny"]) == 26
    assert (lshape["version"], lshape["dc_kw"], lshape["payback_years"]) == (3, 114.4, 4.014880218445176)
    assert rows["gz-t11-changzhou-006"]["flags"] == sitecheck.flags(RISKY)["risk"] and demo["flags"] == []


def test_park_api_lists_only_verified_design_exports():
    client = TestClient(api.app, base_url=f"http://127.0.0.1:{API_PORT}", headers={"origin": API_ORIGIN})
    data = client.get("/api/park").json()
    runs = {row["run_id"] for row in data["buildings"]}
    assert {"gz-t11-changzhou-006", "gz-changzhou-demo-1004-1514", "gz-t14-lshape-001", "gz-t17-real04-1004-1657"} <= runs
    assert not any(run.startswith("eval-") or "review" in run and not run.startswith("gz-") for run in runs)
    assert "gz-t17-real12-1004-1638" not in runs  # stopped before export
