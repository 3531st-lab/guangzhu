"""Action acceptance: immutable what-if, traceable options and gated exports."""

import hashlib
import json
import shutil

import pytest
import requests
from scipy.optimize import brentq

from guangzhu import analysis, catalog, electrical, mcp_actions, project as storage, weather, yieldsim
from guangzhu.config import ROOT
from guangzhu.models import Design, GzError, Project


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    # a fresh checkout has no downloaded weather cache: start from the bundled demo weather so the run stays offline
    shutil.copytree(ROOT / "data/demo/weather", tmp_path / "weather-cache")
    monkeypatch.setattr(weather, "CACHE_DIR", tmp_path / "weather-cache")
    def forbidden(*args, **kwargs):
        pytest.fail("MCP acceptance must not access the network")
    monkeypatch.setattr(requests.Session, "request", forbidden)
    return storage.init(ROOT / "data/demo/projects/changzhou-demo")


def call(name, **args):
    return mcp_actions.dispatch("gz_" + name, args)


def files_hash(project_id):
    root = storage._path(project_id)
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}


def test_edit_reports_capacity_from_original_design_statistics_without_recalculation(demo):
    original = storage.load_design(demo.id, 3)
    before = storage._path(demo.id, 'designs/v3.json').read_bytes()
    result = call('edit_design', project_id=demo.id, version=3, reason='组件变更卡片回归',
                  ops=[{'op':'remove_modules','module_ids':[original.modules[0].id]}])
    modified = storage.load_design(demo.id, result['version'])
    assert result['parent_version'] == modified.parent_version == 3
    assert result['reason'] == modified.reason == '组件变更卡片回归'
    assert result['dc_kw_change'] == {'before':original.statistics['dc_kw'], 'after':modified.statistics['dc_kw']}
    assert result['dc_kw_change']['before'] > result['dc_kw_change']['after']
    assert storage._path(demo.id, 'designs/v3.json').read_bytes() == before


@pytest.mark.parametrize("existing_cache", [False, True])
def test_price_what_if_does_not_modify_any_project_file_and_matches_independent_cashflow(demo, existing_cache):
    demo.requirements.structured.ballast_only = True  # No drilling, so the roof keeps an L01 failure for the what-if to carry.
    storage.save(demo)
    baseline = analysis.analyze(demo.id, 3, offline=True)
    saved = storage._path(demo.id, 'analysis/v3/economics.json')
    cash = json.loads(saved.read_text(encoding='utf-8'))
    if not existing_cache:
        saved.unlink()
    before = files_hash(demo.id)
    result = call("analyze", project_id=demo.id, version=3, what_if={"price_change_pct": -10}, offline=True)
    assert files_hash(demo.id) == before
    assert not storage._path(demo.id, "analysis/v3/compare.json").exists()
    assert not storage._path(demo.id, "analysis/v3/crosscheck.json").exists()
    scenario = result["what_if"]
    assert scenario["saved"] is False and scenario["note"] == "此结果未保存"
    assert scenario['hard_failed'] == 1  # The ballast-only L01 overload stays visible in the unsaved scenario.
    assert {row['id'] for row in result['rules']['failed'] if row['level'] == 'hard'} == {'L01'}
    assert {row["id"] for row in scenario["rules"]} == {"U03", "U04"}
    generation, capex = result['yield_kwh']['p50'], cash['capex_cny']
    income = cash['income_breakdown']
    annual = income['self_saving_cny'] * .9 + income['export_cny'] + income['green_cny']
    om = 206250 * (.046 + .01) + capex * .002
    replacement = cash['costs']['replacement_cny']
    flows = [-capex] + [annual * .9945 ** (year - 1) - om - (replacement if year == 13 else 0) for year in range(1, 26)]
    cumulative = -capex
    for year, value in enumerate(flows[1:], 1):
        previous, cumulative = cumulative, cumulative + value
        if previous < 0 <= cumulative:
            expected_payback = year - 1 - previous / value
            break
    expected_irr = 100 * brentq(lambda rate: sum(flow / (1 + rate) ** year for year, flow in enumerate(flows)), 0, 1)
    energy_pv = sum(generation * .9945 ** (year - 1) / 1.06 ** year for year in range(1, 26))
    om_pv = sum((om + (replacement if year == 13 else 0)) / 1.06 ** year for year in range(1, 26))
    assert scenario["payback_years"] == pytest.approx(expected_payback, rel=5e-6)
    assert scenario["irr_pct"] == pytest.approx(expected_irr, rel=5e-6)
    assert scenario["lcoe_cny_kwh"] == pytest.approx((capex + om_pv) / energy_pv, rel=5e-6)
    assert scenario["delta"]["payback_years"] > 0 and scenario["delta"]["irr_pct"] < 0
    if existing_cache:
        assert {key: value for key, value in result.items() if key != "what_if"} == baseline


def test_summary_requirements_and_fresh_generation_use_existing_contract(demo):
    before = files_hash(demo.id)
    summary = call("project_summary", project_id=demo.id)
    assert summary["roof_bounds_m"] == [0, 0, 60, 36] and summary["roof_area_m2"] == 2160
    assert summary["obstacle_count"] == 2 and summary["keepout_count"] == 1
    assert {item["id"] for item in summary["obstacles"]} == {"stair-1", "tank-1"}
    assert summary["versions"] == ["v1", "v2", "v3"] and summary["modules"] == 375
    assert summary["exported_versions"] == []
    assert files_hash(demo.id) == before
    requirements = call("set_requirements", project_id=demo.id, text="预算10万元，至少300千瓦", structured={"budget_cny_max": 100000, "capacity_kw_min": 300})
    assert len(requirements["contradictions"]) == 2
    assert storage.next_version(demo.id) == 4
    generated = call("generate_layout", project_id=demo.id, params={"tilt_deg": 20})
    design = storage.load_design(demo.id, generated["version"])
    assert generated["version"] == 4 and design.parent_version is None
    assert design.author == "agent" and design.reason == "按参数排板"
    assert all(files_hash(demo.id)[key] == digest for key, digest in before.items() if key.startswith("designs/"))


def test_review_is_append_only_and_exports_reanalyze_before_checking_gate(demo):
    args = dict(project_id=demo.id, version=3, reviewer_model="合成审核员", verdict="approve", findings=[])
    first = call("record_review", **args)
    first_path = storage._path(demo.id, "reviews/" + first["file"].split("/")[-1])
    digest = hashlib.sha256(first_path.read_bytes()).hexdigest()
    second = call("record_review", **args)
    assert first["file"] != second["file"]
    assert hashlib.sha256(first_path.read_bytes()).hexdigest() == digest
    with pytest.raises(GzError) as caught:
        call("export", project_id=demo.id, version=1, offline=True)
    assert caught.value.error_code == "EXPORT_BLOCKED" and "S01" in caught.value.message_zh
    assert not storage._path(demo.id, "exports/v1").exists()
    demo.roof.inverter_positions = [(52, 8)]  # Inside the water tank: no cable reaches it, so E10 blocks the export.
    storage.save(demo)
    with pytest.raises(GzError) as cable_failure:
        call("export", project_id=demo.id, version=3, offline=True)
    assert cable_failure.value.error_code == 'EXPORT_BLOCKED' and 'E10' in cable_failure.value.message_zh
    demo.roof.inverter_positions = [(30, 18)]  # Only this disposable test project changes placement.
    demo.requirements.structured.ballast_only = True  # No drilling: the wind ballast overloads the 0.5 kN/m² roof.
    storage.save(demo)
    with pytest.raises(GzError) as wind_failure:
        call('export', project_id=demo.id, version=3, offline=True)
    assert wind_failure.value.error_code == 'EXPORT_BLOCKED' and 'L01' in wind_failure.value.message_zh
    demo.roof.load_capacity_kn_m2 = 2  # Explicitly sufficient test-only capacity to exercise export immutability.
    storage.save(demo)
    result = call("export", project_id=demo.id, version=3, offline=True)
    root = storage._path(demo.id, "exports/v3")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert len(result["files"]) == 6 and manifest["files"] == result["files"]
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
    assert hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest() == result["manifest_sha256"]
    assert json.loads((root / "rules.json").read_text(encoding="utf-8"))["hard_failed"] == 0
    # A newer unexported comparison candidate must not hide the chosen export.
    call("generate_layout", project_id=demo.id, params={"tilt_deg": 10})
    summary = call("project_summary", project_id=demo.id)
    assert summary["version"] == 4 and summary["exported_versions"] == [3]
    demo.requirements.structured.capacity_kw_min = 1000
    storage.save(demo)
    with pytest.raises(GzError) as caught:
        call("export", project_id=demo.id, version=3, offline=True)
    assert caught.value.error_code == "EXPORT_BLOCKED" and "U01" in caught.value.message_zh


def test_compare_options_preserves_requirements_and_version_ancestry(demo):
    demo.requirements.structured.tilt_deg_range = (15, 20)
    storage.save(demo)
    call("analyze", project_id=demo.id, version=3, offline=True)
    original = files_hash(demo.id)
    result = call("compare_options", project_id=demo.id, base_version=3, offline=True)
    assert json.loads(storage._path(demo.id, "analysis/v3/compare.json").read_text(encoding="utf-8")) == result
    assert [row["name"] for row in result["options"]] == ["多装", "最快回本", "折中"]
    assert all("G05" not in option["violated_requirements"] for option in result["options"])
    assert all(15 <= option["tilt_deg"] <= 20 for option in result["options"])
    candidates = result["tilt_trials"]
    assert [row["tilt_deg"] for row in candidates] == [15, 17, 20]
    assert result["site_tilt"]["best"] == 32 and result["site_tilt"]["capacity"] == 15
    assert "candidate_per_kw" not in result
    best = max(candidates, key=lambda row: row["kwh_per_kw"])
    assert result["options"][1]["tilt_deg"] == best["tilt_deg"]
    for option in result["options"]:
        assert option["kwh_per_kw"] == pytest.approx(option["annual_kwh"] / option["dc_kw"], abs=.00005)
        design = storage.load_design(demo.id, option["version"])
        chain = []
        while design.version != 3:
            assert design.author == "agent" and design.parent_version is not None
            chain.append(design.version)
            design = storage.load_design(demo.id, design.parent_version)
        assert chain and len(chain) == len(set(chain))
        rules = json.loads(storage._path(demo.id, f"analysis/v{option['version']}/rules.json").read_text(encoding="utf-8"))
        assert all(row["status"] == "pass" for row in rules["items"] if row["id"] in ("S01", "E08"))
    assert all(files_hash(demo.id)[key] == digest for key, digest in original.items() if key.startswith("designs/"))
    assert storage.load(demo.id).requirements.structured.tilt_deg_range == (15, 20)


def test_online_timeout_keeps_crosscheck_analysis_and_comparison_usable(demo,monkeypatch,tmp_path):
    def unavailable(*args,**kwargs):
        raise requests.Timeout('simulated unavailable source')
    monkeypatch.setattr(weather,'CACHE_DIR',tmp_path/'weather-cache')
    monkeypatch.setattr(yieldsim,'CACHE_DIR',tmp_path/'yield-cache')
    # Keep the missing-PVGIS recovery case independent of newly prefetched roof angles.
    monkeypatch.setattr(yieldsim,'DEMO_DIR',tmp_path/'no-pvgis-demo')
    monkeypatch.setattr(catalog,'CACHE_DIR',tmp_path/'cec-cache')
    monkeypatch.setattr(weather,'_download_json',unavailable)
    monkeypatch.setattr(yieldsim,'_download_pvgis',unavailable)
    monkeypatch.setattr(catalog,'_download_bytes',unavailable)
    # A small real roof keeps this recovery test independent of the demo's timed
    # 390-module performance test, while running all four local yield chains.
    demo.id='timeout-small'; demo.designs=[]
    demo.roof.outline=[(0,0),(20,0),(20,18),(0,18)]
    demo.roof.obstacles=[]; demo.roof.keepouts=[]
    demo.requirements.structured.keep_clear_ids=[]
    storage.save(demo)
    version=call('generate_layout',project_id=demo.id,params={'tilt_deg':20})['version']
    crosscheck=call('crosscheck_yield',project_id=demo.id,version=version,offline=False)
    assert json.loads(storage._path(demo.id, f"analysis/v{version}/crosscheck.json").read_text(encoding="utf-8")) == crosscheck
    assert crosscheck['ok'] is True and set(crosscheck['specific_yield_kwh_kwp'])=={'a','b','c','b_tmy'}
    assert '缺PVGIS' in crosscheck['omitted']['d']
    checked=call('analyze',project_id=demo.id,version=version,offline=False)
    assert checked['ok'] is True and checked['yield_kwh']['p50']>0
    assert checked['yield_kwh']['omitted']=={'d':'缺PVGIS'}
    assert len(analysis.serialized(checked).encode('utf-8'))<=2048
    comparison=call('compare_options',project_id=demo.id,base_version=version,offline=False)
    assert comparison['ok'] is True and len(comparison['options'])==3
    assert all(option['annual_kwh']>0 for option in comparison['options'])


def test_uncached_what_if_uses_installed_dc_for_incomplete_v1_without_writes(demo):
    design=storage.load_design(demo.id,1)
    demo.equipment.inverter_id = 'sungrow-sg100cx-p2'
    design.modules_per_string=7  # 390 panels leave 5: a 6-panel short string is below the feasible minimum.
    # An imported legacy record may contain a connected-capacity statistic; the
    # module count and catalog are the authoritative installed DC capacity.
    design.statistics['dc_kw']=206.25
    demo.id='legacy-v1'; demo.designs=[]
    storage.save(demo); storage.save_design(demo.id,design)
    electric=electrical.calculate(demo,design,offline=True)
    assert electric['dc_kw']==214.5 and electric['connected_dc_kw']==211.75 and len(electric['unused_modules'])==5
    before=files_hash(demo.id)
    scenario=call('analyze',project_id=demo.id,version=1,what_if={'price_change_pct':0},offline=True)
    assert files_hash(demo.id)==before and scenario['what_if']['saved'] is False
    baseline=call('analyze',project_id=demo.id,version=1,offline=True)
    def engineering(value):
        result = json.loads(json.dumps({key: item for key, item in value.items() if key != 'what_if'}))
        for row in result['rules']['failed']:
            row.pop('name_zh', None)
            row.pop('hint_zh', None)
        # The larger what-if reply may list removals as lossless id ranges to stay under 2 KB; compare the same form.
        result['suggestions'] = [analysis._compact_removal(op) for op in result['suggestions']]
        result.pop('suggestions_format', None)
        return result
    assert engineering(scenario) == engineering(baseline)
    assert len(analysis.serialized(scenario).encode('utf-8')) + 128 <= 2048
    assert baseline['dc_kw']==214.5
    assert baseline['yield_kwh']['p50']==pytest.approx(214.5*baseline['yield_kwh']['per_kw'],abs=.02)
    assert all(value==0 for value in scenario['what_if']['delta'].values())


@pytest.mark.parametrize('existing_cache',[False,True])
def test_missing_pvgis_what_if_preserves_notice_numeric_baseline_and_all_files(demo,monkeypatch,existing_cache):
    def unavailable(*args,**kwargs):
        raise yieldsim.MissingPVGISResult('recorded unavailable exact-site result')
    monkeypatch.setattr(yieldsim,'load_pvgis_result',unavailable)
    if existing_cache:
        baseline=call('analyze',project_id=demo.id,version=3,offline=True)
        # Existing T08 caches had the notice in generation but not the compact
        # summary. The what-if must recover it without rewriting that cache.
        summary_path=storage._path(demo.id,'analysis/v3/summary.json')
        legacy=json.loads(summary_path.read_text(encoding='utf-8'))
        legacy['yield_kwh'].pop('omitted',None)
        summary_path.write_text(json.dumps(legacy),encoding='utf-8')
    before=files_hash(demo.id)
    scenario=call('analyze',project_id=demo.id,version=3,what_if={'price_change_pct':-10},offline=True)
    assert files_hash(demo.id)==before
    assert scenario['yield_kwh']['omitted']=={'d':'缺PVGIS'}
    assert scenario['what_if']['saved'] is False and scenario['what_if']['delta']['payback_years']>0
    if not existing_cache:
        baseline=call('analyze',project_id=demo.id,version=3,offline=True)
    assert {key:value for key,value in scenario.items() if key!='what_if'}==baseline
    cash=json.loads(storage._path(demo.id,'analysis/v3/economics.json').read_text(encoding='utf-8'))
    assert cash['generation']['omitted']=={'d':'缺PVGIS：recorded unavailable exact-site result'}
    assert set(cash['generation']['results'])=={'a','b','c','b_tmy'}
    values=[row['specific_yield_kwh_kwp'] for row in cash['generation']['results'].values()]
    shadows=json.loads(storage._path(demo.id,'analysis/v3/shading.json').read_text(encoding='utf-8'))
    multiplier=baseline['dc_kw']*(1-shadows['summary']['avg_loss_pct']/100)
    assert baseline['yield_kwh']['low']==pytest.approx(min(values)*multiplier,abs=.002)
    assert baseline['yield_kwh']['high']==pytest.approx(max(values)*multiplier,abs=.002)


@pytest.mark.parametrize("template", ["changzhou-demo", "l-shape", "rotated"])
def test_new_project_copies_template_without_history_or_requirements(demo, template):
    source = ROOT / "data/demo/projects" / template
    original = storage._read(source / "project.json", Project)
    before = {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob("*") if p.is_file()}
    result = call("new_project", project_id="fresh-" + template, template=template)
    created = storage.load(result["project_id"])
    assert result["created"] and result["version"] is None and result["versions"] == []
    assert result["exported_versions"] == [] and result["latest_analysis"] is None
    assert created.requirements.text == "" and created.requirements.structured.model_dump(exclude_none=True) == {"keep_clear_ids": []}
    assert created.roof == original.roof
    assert created.site == original.site and created.equipment == original.equipment
    assert created.economics == original.economics
    assert set(files_hash(created.id)) == {"project.json"}
    assert before == {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob("*") if p.is_file()}


def test_new_project_economics_are_validated_before_writes_and_note_preserves_source(demo):
    changes = dict(price_self_cny_kwh=.9, self_use_ratio=.7, capex_cny_per_w=3, price_export_cny_kwh=.4)
    call("new_project", project_id="brief-economics", template="changzhou-demo", economics=changes)
    created = storage.load("brief-economics")
    original = storage.load(demo.id).economics
    assert all(getattr(created.economics, key) == value for key, value in changes.items())
    assert created.economics.om_cny_per_w_year == original.om_cny_per_w_year
    assert created.economics.assumptions_note.startswith(original.assumptions_note)
    assert "任务书覆盖：自用电价（元/度）=0.9；自用比例=0.7；造价（元/W）=3；余电上网电价（元/度）=0.4" in created.economics.assumptions_note
    before = files_hash(created.id)
    with pytest.raises(GzError, match="该项目已存在") as caught:
        call("new_project", project_id=created.id, template="changzhou-demo", economics=dict(price_self_cny_kwh=.8))
    assert caught.value.error_code == "PROJECT_EXISTS" and files_hash(created.id) == before
    for changes in (dict(self_use_ratio=1.1), dict(capex_cny_per_w=-1), dict(unknown=1)):
        with pytest.raises(GzError) as caught:
            call("new_project", project_id="invalid-economics", template="changzhou-demo", economics=changes)
        assert caught.value.error_code == "ECONOMICS_INVALID"
        assert not storage._path("invalid-economics").exists()


def test_unknown_template_lists_at_most_ten_choices_without_creating_project(demo, monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_actions, "ROOT", tmp_path)
    templates = tmp_path / "data/demo/projects"
    for number in range(12):
        directory = templates / f"roof-{number:02}"
        directory.mkdir(parents=True)
        (directory / "project.json").write_text("{}", encoding="utf-8")
    with pytest.raises(GzError) as caught:
        call("new_project", project_id="unknown-template", template="missing")
    assert caught.value.error_code == "TEMPLATE_NOT_FOUND"
    assert caught.value.fix_hint == "可用模板：" + "、".join(f"roof-{number:02}" for number in range(10))
    assert not storage._path("unknown-template").exists()


def test_missing_pvgis_keeps_all_l_shape_v2_failures_and_budget_repair(demo, monkeypatch):
    l_shape = storage.init(ROOT / "data/demo/projects/l-shape")
    l_shape.economics.capex_cny_per_w = 2.59  # Keep the archived cable/suggestion fixture price explicit.
    storage.save(l_shape)
    for version in (1, 2):
        recorded = storage._read(ROOT / f"runs/t09-l-shape-001/project/designs/v{version}.json", Design)
        storage.save_design(l_shape.id, recorded)
    baseline = call("analyze", project_id=l_shape.id, version=2, offline=True)
    long_reason = "缺PVGIS：" + "未找到匹配场址、倾角和系统损失的缓存；" * 5 + "Timeout"
    def unavailable(*args, **kwargs):
        raise yieldsim.MissingPVGISResult(long_reason.removeprefix("缺PVGIS："))
    monkeypatch.setattr(yieldsim, "load_pvgis_result", unavailable)
    result = call("analyze", project_id=l_shape.id, version=2, offline=True)
    assert result["yield_kwh"]["omitted"] == {"d": "缺PVGIS"}
    assert [row["id"] for row in result["rules"]["failed"]] == [row["id"] for row in baseline["rules"]["failed"]]
    assert result["suggestions"] == baseline["suggestions"] and len(result["suggestions"]) == 1
    assert any(op.get("where", {}).get("worst_count") == 53 for op in result["suggestions"])
    assert len(analysis.serialized(result).encode("utf-8")) <= 2048
    cash = json.loads(storage._path(l_shape.id, "analysis/v2/economics.json").read_text(encoding="utf-8"))
    assert cash["generation"]["omitted"] == {"d": long_reason}
    crosscheck = call("crosscheck_yield", project_id=l_shape.id, version=2, offline=True)
    assert crosscheck["omitted"] == {"d": long_reason}


def test_a_capacity_floor_is_judged_by_what_the_max_capacity_option_reaches(demo):
    """The default layout is not the most a roof takes (a lower tilt fits more), so only a floor beyond the 多装 option is impossible."""
    from guangzhu import layout
    ceiling = lambda message: float(message.split('最多可装的')[1].split('千瓦')[0])
    default = layout.generate_layout(storage.load(demo.id), {}).statistics['dc_kw']
    [message] = mcp_actions._set_requirements(demo.id, '装机不少于500千瓦', {'capacity_kw_min': 500}, offline=True)['contradictions']
    assert default + 20 < ceiling(message) < 500 and ceiling(message) == int(ceiling(message))  # rounded down: a suggestion built on it can be met
    reachable = int(default) + 10
    assert mcp_actions._set_requirements(demo.id, f'装机不少于{reachable}千瓦', {'capacity_kw_min': reachable}, offline=True)['contradictions'] == []
    [narrower] = mcp_actions._set_requirements(demo.id, '留1米通道，装机不少于500千瓦', {'capacity_kw_min': 500, 'walkway_m_min': 1},
                                               offline=True)['contradictions']
    assert default <= ceiling(narrower) < ceiling(message)
