"""T07 complete offline demo, engineering/economic rules and compact contract."""

import hashlib
import json
import re
import time
import pytest
import requests
from guangzhu import analysis,economics,electrical,project as storage,rules,structure
from guangzhu.config import ROOT
from guangzhu.models import GzError


def expand_suggestion(operation):
    if 'module_id_ranges' not in operation:
        return operation
    ids = []
    for interval in operation['module_id_ranges']:
        if '..' not in interval:
            ids.append(interval)
            continue
        first, last = interval.split('..')
        a, b = re.fullmatch(r'(.*?)(\d+)', first), re.fullmatch(r'(.*?)(\d+)', last)
        assert a[1] == b[1] and len(a[2]) == len(b[2]) and int(a[2]) <= int(b[2])
        ids.extend(a[1] + str(i).zfill(len(a[2])) for i in range(int(a[2]), int(b[2]) + 1))
    return {'op': operation['op'], 'module_ids': ids}


def test_compact_ids_preserve_gaps_prefixes_and_numeric_width():
    ids = ['R01-C001', 'R01-C002', 'R01-C004', 'R02-C003', 'R02-C004', 'R02-C005',
           'R02-C009', 'R02-C010', 'R02-C011', 'R03-C01', 'R03-C02', 'R03-C003', 'named-id']
    encoded = analysis._compact_removal({'op':'remove_modules', 'module_ids':ids})
    decoded = expand_suggestion(encoded)['module_ids']
    assert len(decoded) == len(ids) and set(decoded) == set(ids)
    assert 'R01-C003' not in decoded and 'R03-C03' not in decoded


def test_tight_budget_keeps_full_actionable_advice_and_converges_with_existing_edits(demo):
    from guangzhu.layout import generate_layout
    project = storage.init(ROOT/'data/demo/projects/l-shape')
    project.economics.capex_cny_per_w = 2.59  # Keep this removal/compactness fixture at its stated synthetic cost.
    project.roof.load_capacity_kn_m2 = 3  # Isolate actionable budget edits; original 0.5 L01 failure is covered below.
    project.requirements.structured.budget_cny_max = 50_000
    project.requirements.structured.capacity_kw_min = None
    storage.save(project)
    storage.save_design(project.id, generate_layout(project, {}))
    saw_compression = False
    for version in range(1, 8):
        summary = analysis.analyze(project.id, version, offline=True)
        checked = json.loads(storage._path(project.id, f'analysis/v{version}/rules.json').read_text(encoding='utf-8'))
        assert {row['id'] for row in summary['rules']['failed']} == {row['id'] for row in checked['items'] if row['status']=='fail'}
        assert len(analysis.serialized(summary).encode('utf-8')) <= 2048
        if not summary['rules']['hard_failed']:
            assert summary['economics']['capex_cny'] <= 50_000 and saw_compression
            return
        original = [row['suggestion'] for row in checked['items'] if row['level']=='hard' and row['status']=='fail' and row['suggestion']]
        expanded = [expand_suggestion(op) for op in summary['suggestions']]
        assert len(expanded) == len(original)
        for op in expanded:
            assert any(op == actual or op['op'] == actual['op'] == 'remove_modules' and
                       set(op.get('module_ids', [])) == set(actual.get('module_ids', [])) and
                       op.get('where') == actual.get('where') for actual in original)
        compressed = any('module_id_ranges' in op for op in summary['suggestions'])
        saw_compression |= compressed or any('worst_count' in op.get('where', {}) for op in expanded)
        if compressed:
            assert 'module_ids' in summary['suggestions_format'] and '含端点' in summary['suggestions_format']
        assert version < 7, 'existing operations must meet budget within six edits'
        storage.edit_design(project.id, version, expanded, '按真实 S01/E08/U03 建议修复', 'agent')


@pytest.fixture
def demo(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'PROJECTS_DIR',tmp_path/'projects')
    def forbidden(*args,**kwargs):
        pytest.fail('T07 acceptance must work without network')
    monkeypatch.setattr(requests.Session,'request',forbidden)
    project=storage.init(ROOT/'data/demo/projects/changzhou-demo')
    return project,storage.load_design(project.id,3)


def test_offline_complete_analysis_recalculates_shading_under_ten_seconds(demo):
    project,design=demo
    assert project.economics.capex_cny_per_w is None
    assert project.economics.om_cny_per_w_year is None
    original=hashlib.sha256(storage._path(project.id,'designs/v3.json').read_bytes()).hexdigest()
    started=time.perf_counter()
    summary=analysis.analyze(project.id,3,offline=True)
    elapsed=time.perf_counter()-started
    assert elapsed<10
    assert set(summary) == {'ok', 'version', 'modules', 'dc_kw', 'yield_kwh', 'shading', 'electrical', 'load',
                            'wind', 'economics', 'rules', 'suggestions'}
    assert summary['ok'] and summary['version']==3 and summary['modules']==375 and summary['dc_kw']==206.25
    assert set(summary['yield_kwh'])=={'p50','low','high','per_kw','omitted'}
    assert summary['yield_kwh']['omitted']=={}
    assert summary['yield_kwh']['low']<=summary['yield_kwh']['p50']<=summary['yield_kwh']['high']
    assert set(summary['electrical'])=={'modules_per_string','modules_per_string_short','voc_cold_v','voc_limit_v','vmp_hot_v',
                                       'mppt_min_v','dc_ac_ratio','dc_drop_pct_max','ac_drop_pct_max','rated_ac_kw'}
    assert len(analysis.serialized(summary).encode('utf-8'))<=2048
    directory=storage._path(project.id,'analysis/v3')
    assert {p.name for p in directory.glob('*.json')}=={'shading.json','electrical.json','structure.json','economics.json','rules.json','summary.json'}
    assert json.loads((directory/'summary.json').read_text(encoding='utf-8'))==summary
    assert [(row['id'],row['value'],row['limit']) for row in summary['rules']['met']]==[('G03',summary['rules']['met'][0]['value'],1),('G04',0,0),
                                                                                       ('U04',summary['economics']['payback_years'],6)]
    assert summary['rules']['met'][0]['value']>=1 and summary['rules']['met'][0]['unit']=='m'  # the reviewer can confirm the walkway and the skylight
    cash=json.loads((directory/'economics.json').read_text(encoding='utf-8'))
    assert cash['analysis_metadata']['shading_reused'] is False
    assert cash['params']['capex_cny_per_w'] == cash['costs']['effective_cny_per_w']
    assert cash['params']['om_cny_per_w_year'] == .046
    assert cash['capex_cny'] == pytest.approx(sum(r['subtotal_cny'] for r in cash['costs']['items']))
    assert cash['operating_costs']['base_om_cny'] == pytest.approx(206250 * .046)
    assert cash['cashflows'][1]['om_cny'] == pytest.approx(206250 * (.046 + .01) + cash['capex_cny'] * .002)
    assert cash['source']['capex_cny_per_w']['basis'] == 'costs.csv'
    assert cash['source']['capex_cny_per_w']['状态'] == '示意'
    assert cash['source']['om_cny_per_w_year']['状态'] == '已查证'
    for key in ('price_self_cny_kwh','price_export_cny_kwh','self_use_ratio','discount_rate'):
        assert cash['source'][key]['状态']=='示意'
    loss=economics.load_assumptions()['design_system_loss_pct']['value']
    assert round(loss,2)==11.42
    results=cash['generation']['results']
    assert set(results)=={'a','b','c','b_tmy','d'}
    assert all(r['metadata']['loss_percent']==pytest.approx(loss) for r in results.values())
    ratio=1-summary['shading']['avg_loss_pct']/100
    assert summary['yield_kwh']['p50']==pytest.approx(results['b']['specific_yield_kwh_kwp']*206.25*ratio,rel=1e-6)
    full_rules=json.loads((directory/'rules.json').read_text(encoding='utf-8'))
    # The demo roof cannot carry the wind ballast, so its racks are anchored (L01 passes); cables cross the skylight on trays.
    assert full_rules['total'] == 25 and full_rules['hard_failed'] == 0
    assert '锚栓' in json.loads((directory/'structure.json').read_text(encoding='utf-8'))['evidence']
    assert {'U03','U04'}<={row['id'] for row in full_rules['items']}
    assert len(summary['rules']['failed'])<=8
    assert summary['yield_kwh']['per_kw']==pytest.approx(summary['yield_kwh']['p50']/206.25,abs=.0001)
    assert len(summary['suggestions'])<=5
    again=analysis.analyze(project.id,3,offline=True)
    assert again==summary
    assert json.loads((directory/'economics.json').read_text(encoding='utf-8'))['analysis_metadata']['shading_reused'] is True
    assert hashlib.sha256(storage._path(project.id,'designs/v3.json').read_bytes()).hexdigest()==original


def test_budget_and_payback_rules_with_real_edit_suggestions(demo):
    project,design=demo
    project.requirements.structured.budget_cny_max=500_000
    project.requirements.structured.payback_years_max=3
    # This budget case deliberately uses a synthetic price, independent of the demo defaults.
    project.economics.capex_cny_per_w=2.6
    shadows={'modules':[{'id':m.id,'total_loss_pct':0} for m in design.modules],'summary':{'avg_loss_pct':0}}
    electric=electrical.calculate(project,design,offline=True); load=structure.calculate(project,design)
    cash={'capex_cny':536250,'params':{'capex_cny_per_w':2.6},'payback_years':5.5}
    result=rules.evaluate(project,design,shadows,electric,load,cash)
    by_id={r['id']:r for r in result['items']}
    assert by_id['U03']['status']==by_id['U04']['status']=='fail'
    assert by_id['U03']['value']==536250 and by_id['U03']['limit']==500000
    assert by_id['U04']['value']==5.5 and by_id['U04']['limit']==3
    assert by_id['U04']['suggestion'] is None and by_id['U04']['hint_zh']
    operation=by_id['U03']['suggestion']; assert operation['op']=='remove_modules'
    count=operation['where']['worst_count']
    module_count=len(design.modules)
    assert count==26
    assert (module_count-count)*550*2.6<=500000<(module_count+1-count)*550*2.6
    storage.save(project)
    path=storage._path(project.id,'analysis/v3/shading.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(shadows | {'version':3}),encoding='utf-8')
    version=storage.edit_design(project.id,3,[operation],'预算规则修复','rule')['version']
    smaller=storage.load_design(project.id,version)
    cash=economics.calculate(project,len(smaller.modules)*.55,{'p50':230000,'low':220000,'high':250000})
    new_rules=rules.evaluate(project,smaller,shadows,electrical.calculate(project,smaller,offline=True),structure.calculate(project,smaller),cash)
    assert next(row for row in new_rules['items'] if row['id']=='U03')['status']=='pass'
    project.requirements.structured.budget_cny_max=None; project.requirements.structured.payback_years_max=None
    result=rules.evaluate(project,design,shadows,electric,load,cash)
    assert all(r['status']=='na' for r in result['items'] if r['id'] in ['U03','U04'])


@pytest.mark.parametrize('omitted',[{}, {'d':'缺PVGIS：未找到匹配场址、倾角和系统损失的缓存；Timeout'}])
def test_summary_keeps_eight_failure_five_advice_caps_without_byte_based_loss(demo,omitted):
    project,design=demo
    electric=electrical.calculate(project,design,offline=True); load=structure.calculate(project,design)
    cash={'capex_cny':537680,'payback_years':5,'irr_pct':18,'lcoe_cny_kwh':.2,'co2_t_per_year':100}
    shadows={'summary':{'avg_loss_pct':1,'modules_over_threshold':0,'threshold_pct':8}}
    checked={'total':22,'passed':0,'items':[dict(id=f'X{i}',name_zh='测试失败规则',value=i,limit=0,hint_zh='调整参数后重新分析',level='hard',status='fail',suggestion={'op':'set_string_size','modules_per_string':i+1}) for i in range(15)]}
    summary=analysis._summary(design,shadows,electric,load,cash,{'p50':230000,'low':220000,'high':250000,'per_kw':1112},checked,omitted=omitted)
    assert len(summary['rules']['failed'])==8 and len(summary['suggestions'])==5
    assert summary['rules']['hard_failed']==15 and len(analysis.serialized(summary).encode('utf-8'))<=2048
    assert summary['suggestions']==[row['suggestion'] for row in checked['items'][:5]]
    assert len(checked['items'])==15 and all(row['suggestion'] for row in checked['items'])
    checked['items'][0]['value']='uncompressible-'*200
    with pytest.raises(GzError) as error:
        analysis._summary(design,shadows,electric,load,cash,{'p50':230000,'low':220000,'high':250000,'per_kw':1112},checked)
    assert error.value.error_code=='RESULT_TOO_LARGE'


def test_rotated_real_suggestions_can_be_executed_together(demo):
    from guangzhu.layout import generate_layout
    rotated=storage.init(ROOT/'data/demo/projects/rotated')
    storage.save_design(rotated.id,generate_layout(rotated,{}))
    original=storage._path(rotated.id,'designs/v1.json').read_bytes()
    summary=analysis.analyze(rotated.id,1,offline=True)
    assert {'G05','S01'}<={item['id'] for item in summary['rules']['failed']}
    assert summary['suggestions']==[{'op':'set_param','name':'tilt_deg','value':20}]
    edited=storage.edit_design(rotated.id,1,summary['suggestions'],'合并分析返回的G05建议','agent')
    design=storage.load_design(rotated.id,edited['version'])
    assert design.version==2 and design.parent_version==1 and design.params.tilt_deg==20
    assert storage._path(rotated.id,'designs/v1.json').read_bytes()==original
    again=analysis.analyze(rotated.id,2,offline=True)
    assert 'G05' not in {item['id'] for item in again['rules']['failed']}


def test_multiple_parameter_suggestions_filter_old_component_operations(demo):
    project,design=demo
    electric=electrical.calculate(project,design,offline=True); load=structure.calculate(project,design)
    cash={'capex_cny':534187.5,'payback_years':4,'irr_pct':24,'lcoe_cny_kwh':.22,'co2_t_per_year':100}
    ops=[{'op':'remove_modules','module_ids':[design.modules[0].id]},
         {'op':'set_param','name':'tilt_deg','value':20}, {'op':'set_param','name':'edge_setback_m','value':2}]
    checked={'total':3,'passed':0,'items':[dict(id=f'X{i}',name_zh='测试规则',value=1,limit=0,hint_zh='',level='hard',status='fail',suggestion=op) for i,op in enumerate(ops)]}
    summary=analysis._summary(design,{'summary':{'avg_loss_pct':0,'modules_over_threshold':0,'threshold_pct':8}},electric,load,cash,
                              {'p50':230000,'low':220000,'high':250000,'per_kw':1112},checked)
    assert summary['suggestions']==ops[1:]
