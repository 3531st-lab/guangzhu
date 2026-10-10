"""Proposal display preserves archived precision, evidence, and unknown values."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
from html import unescape
from pathlib import Path
import re

import pytest

from guangzhu.report.archive import load_archive
from guangzhu.report.view import beijing_time, fmt, render, rule_value, source_value

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def archive():
    context = load_archive(ROOT / "runs/gz-t14-impossible-001")
    context.update(generated_at="2026-10-03T23:00:00+08:00", regenerated=True)
    return context


def sections(context):
    return re.findall(r'<section[^>]*>(.*?)</section>', render(context), re.S)


def test_noncontiguous_inverter_strings_are_listed_without_false_interval(archive):
    context = deepcopy(archive)
    context['electrical']['per_inverter'][0]['string_ids'] = ['S001', 'S003', 'S005']
    page = next(part for part in sections(context) if '逆变器分配' in part)
    assert 'S001、S003、S005' in page and 'S001–S005' not in page


def test_grouped_crosscheck_report_lists_each_orientation(archive):
    context = deepcopy(archive)
    context['crosscheck'] = dict(specific_yield_kwh_kwp={'b': 1200}, groups=[
        dict(group=[1, 15, 90], per_kw={'b': 1100}), dict(group=[2, 25, 270], per_kw={'b': 1300})])
    page = next(part for part in sections(context) if '各朝向发电复核' in part)
    assert '坡面1 / 15° / 朝向90°' in page and '坡面2 / 25° / 朝向270°' in page
    assert '1,100' in page and '1,300' in page


TITLES = ['一页结论', '三方案对比', '屋顶与排布', '发电量与复核', '遮挡与损失', '电气与组串', '逆变器分配', '承重核对',
          '回报与敏感性', '减碳估算', '开工前要核实的事', '22条规则清单', '假设与来源', '独立审核', '执行记录与交付']


def section(pages, title):
    """T20: sections flow and may be added, so tests find a section by its heading."""
    return next(page for page in pages if f'data-topic="{title}"' in page)


def plain(value):
    return unescape(re.sub(r'<[^>]+>', '', str(value)))


@pytest.mark.parametrize("unit,value,shown", [("kN/㎡", 0.26761411044448696, "0.27 kN/㎡"),
    ("kN/平方米", 0.5, "0.50 kN/平方米"), ("m²", 123.455, "123.46 m²"), ("°", 3.5, "3.50 °")])
def test_square_units_and_angles_keep_two_decimals_and_original_title(unit, value, shown):
    assert plain(fmt(value, unit)) == shown
    assert f'title="原值 {value}"' in fmt(value, unit)


def test_compound_values_propagate_precision_and_infer_units_from_field_suffixes():
    assert plain(fmt({"range": [1.25, 2.5]}, "%", 2)) == "range 1.25 %；2.50 %"
    assert plain(fmt({"edge_setback_m": 0.555, "tilt_deg": 3.5})) == "边距 0.56 m；倾角 3.50 °"
    assert plain(fmt({"nested": {"gap_m": 0.555}}, digits=3)) == "nested gap_m 0.555 m"
    assert fmt("advice") == "建议"


def test_real_l01_and_clearance_rules_keep_their_archived_values(archive):
    rules = {row["id"]: row for row in archive["rules"]["items"]}
    assert plain(rule_value(rules["L01"], "value")) == "0.27 kN/㎡"
    assert plain(rule_value(rules["L01"], "limit")) == "0.50 kN/㎡"
    for field in ["value", "limit"]:
        markup = rule_value(rules["G06"], field)
        for key, value in rules["G06"][field].items():
            if value is not None:
                expected = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                label = {"edge_setback_m": "边距", "obstacle_clearance_m": "障碍物间距"}[key]
                assert f'{label} {expected:.2f} m' in plain(markup)
                assert f'title="原值 {value}"' in markup


def test_e07_precision_matches_in_requirements_electrical_and_full_rules(archive):
    context = deepcopy(archive)
    row = next(row for row in context["rules"]["items"] if row["id"] == "E07")
    row["source_type"] = "用户要求"
    pages = sections(context)
    assert [re.search(r'<h1 data-topic="(.*?)">', page)[1] for page in pages[1:]] == TITLES
    for title in ['一页结论', '电气与组串', '22条规则清单']:
        assert f'title="原值 {row["value"]}">0.14</span>' in section(pages, title)
        assert 'title="原值 1.0">1.00</span>' in section(pages, title)
        assert 'title="原值 1.3">1.30</span>' in section(pages, title)
    assert "建议 / 未通过" in plain(section(pages, '22条规则清单'))


def test_cover_and_electrical_paragraph_numbers_use_raw_titles(archive):
    pages = sections(archive)
    for key in ["lat", "lon"]:
        value = archive["project"]["site"][key]
        assert str(fmt(value, "°")) in pages[0]
    electrical, page = archive["electrical"], section(pages, '电气与组串')
    from guangzhu.electrical import labels
    assert labels(electrical)[0] in page
    assert str(fmt(electrical["dc_ac_ratio"], digits=2)) in page


def test_missing_review_is_explicit_on_cover_and_review_page(archive):
    context = deepcopy(archive)
    context["review"] = None
    pages = sections(context)
    for page in [pages[0], section(pages, '独立审核')]:
        assert "本归档未提供独立审核原文" in page
    assert "光筑 Agent 生成 · Agnes 独立审核" not in pages[0]


@pytest.mark.parametrize("failure", ["verdict", "verification"])
def test_failed_review_is_explicit_without_rewriting_findings(archive, failure):
    context = deepcopy(archive)
    if failure == "verdict":
        context["review"]["verdict"] = "revise"
    else:
        context["verification"]["review"]["passed"] = False
    pages = sections(context)
    review = section(pages, '独立审核')
    reason = '审核员要求修改' if failure == 'verdict' else '审核记录核对没通过'
    assert f"审核未通过（{reason}）" in pages[0] and f"审核未通过（{reason}）" in review
    for finding in context["review"]["findings"]:
        for value in finding.values():
            assert value in plain(review)


def test_execution_lists_both_actual_ledger_paths_and_unknown_costs(archive):
    context = deepcopy(archive)
    for session in context["sessions"]:
        session.update(costs=[], billing_complete=False, missing_costs=None)
    page = section(sections(context), '执行记录与交付')
    paths = [path for path in context["sources"] if path.endswith("ledger.agnes.jsonl")]
    assert len(paths) == 2 and any(path.startswith("reviews/") for path in paths)
    assert all(context["run_id"] + "/" + path in page for path in paths)
    assert "未知（未提供费用记录）" in page
    assert "已知小计" not in page and "0.000000" not in page


@pytest.mark.parametrize("complete", [True, False])
def test_known_zero_cost_is_distinct_from_an_unknown_cost(archive, complete):
    context = deepcopy(archive)
    for session in context["sessions"]:
        session.update(costs=[dict(currency="USD", micros=0)], billing_complete=complete, missing_costs=0 if complete else 1)
    page = section(sections(context), '执行记录与交付')
    assert 'title="原值 0">0.000000</span> USD' in page
    assert ("0不表示免费" if complete else "已知小计，另有缺额") in plain(page)
    assert "未知（未提供费用记录）" not in page


def test_relaxation_consent_is_preserved_once_and_untrusted_text_stays_escaped(archive):
    context = deepcopy(archive)
    consent = context["relaxations"][0]["consent"][0]["text"]
    context["project"]["name"] = '<script>alert("project")</script>'
    context["review"]["findings"][0]["item"] = '<img src=x onerror="alert(1)">'
    document = render(context)
    assert plain(document).count(consent) == 1
    assert "<script>" not in document and "<img src=x" not in document
    assert "&lt;script&gt;" in document and "&lt;img src=x" in document


def test_real_source_parameters_follow_units_and_keep_unscaled_raw_values():
    context = load_archive(ROOT / "runs/gz-t14-changzhou-005")
    economy = context["economics"]
    expected = dict(capex_cny_per_w="2.590 元/W", om_cny_per_w_year="0.046 元/(W·年)",
        price_self_cny_kwh="0.650 元/kWh", price_export_cny_kwh="0.391 元/kWh", self_use_ratio="80.0 %",
        discount_rate="6.0 %", degradation_annual_pct="0.55 %", lifetime_years="25 年",
        emission_factor_kgco2_kwh="0.5827 kgCO₂/kWh", design_system_loss_pct="11.42 %",
        national_emission_factor_kgco2_kwh="0.5306 kgCO₂/kWh")
    page = section(sections(context), '假设与来源')
    for key, shown in expected.items():
        original = economy["params"][key]
        markup = source_value(original, economy["source"][key]["单位"])
        assert plain(markup) == shown
        assert f'title="原值 {original}"' in markup
        assert str(markup) in page


def test_source_title_survives_without_url_and_archive_is_unchanged():
    context = load_archive(ROOT / "runs/gz-t14-changzhou-005")
    before = deepcopy(context)
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', section(sections(context), '假设与来源'), re.S)
    sources = context["economics"]["source"]
    without_url = [source for source in sources.values() if source["来源标题"] and not source["链接"]]
    assert len(without_url) == 4
    for source in without_url:
        row = next(row for row in rows if source["中文名"] in plain(row))
        assert source["来源标题"] in plain(row)
        assert "<a " not in row
    assert context == before


def test_non_url_source_title_is_escaped_and_absent_source_stays_unknown(archive):
    context = deepcopy(archive)
    source = next(iter(context["economics"]["source"].values()))
    source.update({"来源标题": "<script>local source</script>", "链接": ""})
    page = section(sections(context), '假设与来源')
    assert "&lt;script&gt;local source&lt;/script&gt;" in page
    assert "<script>" not in page
    source["来源标题"] = ""
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', section(sections(context), '假设与来源'), re.S)
    row = next(row for row in rows if source["中文名"] in plain(row))
    assert "未提供" in plain(row)


@pytest.mark.parametrize("value,expected", [
    ("2026-10-03T07:03:30.405Z", "2026-10-03 15:03（北京时间）"),
    ("2026-10-03T15:31:42.187978+08:00", "2026-10-03 15:31（北京时间）"),
    ("2026-10-02T23:03:30-08:00", "2026-10-03 15:03（北京时间）"),
    (None, "未提供"), ("bad", "未提供"), ("2026-10-03T07:03:00", "未提供时区")])
def test_timestamp_requires_timezone_and_converts_to_beijing(value, expected):
    assert beijing_time(value) == expected


def test_e09_only_summarizes_uniform_strings_and_keeps_nonuniform_lengths():
    rule = dict(id="E09", value=[[26, 26], [26]], limit=26, unit="块/串")
    assert plain(rule_value(rule, "value")) == "3 串，均为 26 块/串"
    assert plain(rule_value(rule, "limit")) == "26 块/串"
    rule["value"] = [[25, 26], [26]]
    assert plain(rule_value(rule, "value")) == "25 块/串；26 块/串；26 块/串"
    rule["value"] = []
    assert rule_value(rule, "value") == "无"


def test_public_mapping_keeps_review_findings_and_original_context():
    context = load_archive(ROOT / "runs/gz-t11-changzhou-006")
    context.update(generated_at="2026-10-03T15:31:42.187978+08:00", regenerated=True)
    before = deepcopy(context)
    pages = sections(context)
    review = section(pages, '独立审核')
    public = plain("".join(page for page in pages if page != review))
    assert not re.search(r"requirements\.|roof\.|_m：|allowed-|任务卡|T04|T05|\d{4}-\d{2}-\d{2}T\d{2}:", public)
    assert "五链年发电复核范围（不是置信区间）" in plain(section(pages, '一页结论'))
    assert "本项另按厂家规格书检查" in plain(section(pages, '电气与组串'))
    assert "16 串，均为 26 块/串" in plain(section(pages, '电气与组串'))
    for label in ["NASA POWER 2023 · pvlib 简化", "NASA POWER 2023 · CEC 详细", "NASA POWER 2023 · PySAM PVWatts",
                  "ERA5 TMY · CEC 详细", "ERA5 多年 · PVGIS PVcalc"]:
        assert label in plain(section(pages, '发电量与复核'))
    assert "屋面资料：示意荷载（待结构核定）" in public and "光筑排板规则" in public and "光筑遮挡规则" in public
    for row in context["review"]["findings"]:
        assert fmt(row["severity"]) in plain(review)
        for key in ["item", "evidence", "suggestion"]:
            assert row[key] in plain(review)
    assert re.search(r"审核记录核对（[^）]*）：通过", plain(review))
    assert "仅允许这次 · 2026-10-03 15:03（北京时间）" in plain(section(pages, '执行记录与交付'))
    assert context == before



@pytest.mark.parametrize("verified", [False, True])
def test_codex_r10_the_roof_load_is_called_verified_only_when_the_user_confirmed_it(verified):
    context = load_archive(ROOT / "runs/gz-t11-changzhou-006")
    context.update(generated_at="2026-10-03T15:31:42.187978+08:00", regenerated=True)
    context["project"]["roof"]["load_verified"] = verified
    pages = sections(context)
    load, rules = plain(section(pages, "承重核对")), plain(section(pages, "22条规则清单"))
    everything = plain("".join(pages))
    if verified:
        assert "屋面核定值" in load and "示意" not in load and "屋面资料：核定荷载" in rules and "附加荷载不超屋面核定值" in rules
    else:
        assert "屋面允许值（示意，待结构核定）" in load and "施工前必须请结构工程师复核" in load
        assert "附加荷载不超屋面示意值（待结构核定）" in rules and "屋面资料：示意荷载（待结构核定）" in rules
        assert "核定值" not in everything and "核定荷载" not in everything


def test_codex_r11_yearly_yield_is_a_base_year_estimate_and_never_a_bare_p50():
    context = load_archive(ROOT / "runs/gz-t11-changzhou-006")
    context.update(generated_at="2026-10-03T15:31:42.187978+08:00", regenerated=True)
    pages = sections(context)
    assert "基准年发电估算" in plain(section(pages, "一页结论"))
    yearly = plain(section(pages, "发电量与复核"))
    assert "基准年估算" in yearly and "NASA POWER 2023" in yearly and "不是概率意义上的 P50" in yearly
    assert all(line.count("P50") == line.count("不是概率意义上的 P50") for line in plain("".join(pages)).splitlines())

def test_requirement_table_lists_only_what_the_owner_asked_for(archive):
    # T20: requirements the owner never mentioned are counted in one line instead of rows of "不适用".
    asked = [r for r in archive["rules"]["items"] if r["source_type"] == "用户要求"]
    shown = [r for r in asked if r["status"] != "na"]
    page = section(sections(archive), '一页结论')
    assert len(re.findall(r'<tr>', page)) == len(shown) + 1
    assert (f'其余 {len(asked) - len(shown)} 项要求没有提' in page) is (len(shown) < len(asked))


def test_electrical_evidence_is_short_and_inverters_get_their_own_table(archive):
    pages = sections(archive)
    rows = {plain(row).split()[0]: plain(row) for row in re.findall(r'<tr>(.*?)</tr>', section(pages, '电气与组串'), re.S)}
    assert 'MPPT' not in rows['E07'] and '（每台分配见下表）' in rows['E07']
    lengths = {len(row['module_ids']) for row in archive["electrical"]["strings"]}
    if len(lengths) == 1:
        assert f'{len(archive["electrical"]["strings"])} 串，每串都是 {lengths.pop()} 块' in rows['E09']
    allocation = section(pages, '逆变器分配')
    assert len(re.findall(r'<tr>', allocation)) == len(archive["electrical"]["per_inverter"]) + 1


def test_wind_zone_table_shows_empty_zones_and_anchored_supports_plainly(monkeypatch):
    from guangzhu.report import wind as section
    monkeypatch.setattr(section, 'plan', lambda *args, **kwargs: '')
    zone = lambda label, modules, blocks, kg, **extra: dict(label=label, modules=modules, ballast_blocks=blocks, ballast_kg=kg,
                                                             pressure_kpa_range=[.38, .5], blocks_range=[blocks // max(modules, 1)] * 2,
                                                             load_kn_m2=.147, **extra)
    wind = dict(city=dict(city='常州', selection='示意', distance_km=.3, standard='GB50009', table='E.5', page='未核验', url='https://example.org'),
                basic_pressure_kpa=.4, zone_width_m=1.8, zone_note='', height_note='', method='', note='示意', anchor_note='',
                zones=dict(corner=zone('角部', 0, 0, 0), edge=zone('边部', 20, 0, 0, anchors=40), middle=zone('中部', 10, 30, 600)),
                assumptions=dict(block_kg=20), anchor_count=40, anchored_modules=20, missing='', modules=[],
                factor_source=dict(title='GB55001', url='https://example.org', published='', accessed=''))
    pages = []
    section.pages(dict(structure=dict(wind=wind), project=dict(roof=dict(type='flat'))), lambda *args, **kwargs: pages.append(args), fmt)
    title, _, rows, headers = pages[0][:4]
    assert title == '风荷载与分区压块' and headers[:2] == ['分区', '组件'] and headers[-1] == '锚栓'
    assert rows[0] == ('角部', 0, '—', '—', '—', '—', '—')  # no panel there: dashes, not computed zeros
    assert rows[1][3:5] == ('改锚栓', '—') and rows[1][-1] == 40
    assert rows[2][3] == '3块（60kg）' and unescape(re.sub('<[^>]+>', '', str(rows[2][4]))) == '30块 / 600 kg'
