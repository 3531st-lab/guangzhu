"""Known v1 task text, deterministic JSON and form/CLI bounds."""

import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from guangzhu import brief


SAMPLES = [
    ('changzhou-demo', '厂房回本', {'payback_years_max': 6, 'walkway_m_min': 1, 'keep_clear_ids': ['sky-1']}),
    ('l-shape', '预算30万元，留通道，不挡天窗', {'budget_cny_max': 300000, 'walkway_m_min': 1, 'keep_clear_ids': ['sky']}),
    ('rotated', '倾角15–20度，留通道，不挡天窗', {'walkway_m_min': 1, 'keep_clear_ids': ['sky-1'], 'tilt_deg_range': [15, 20]}),
]
REVIEW = ('你是光筑独立审核员。项目 {project_id}，版本〔版本〕。只调用 gz_project_summary、gz_analyze、'
          'gz_crosscheck_yield 这三个只读工具，各调用一次；复核若有next_group_offset，用group_offset续取全部组；不修改方案，不导出，不调用 gz_record_review。'
          '检查用户要求、硬性规则、发电量复核和经济假设，所有数字都照抄工具结果。最后先用一句话给出结论，再输出一个 json 代码块，'
          '格式为 {{"verdict":"approve 或 revise","findings":[{{"severity":"high、medium 或 low","item":"检查项",'
          '"evidence":"证据，带数字","suggestion":"建议"}}]}}，代码块后面不再写别的。')


def payload(text):
    return json.loads(text.split('```json\n')[1].split('\n```')[0])


@pytest.mark.parametrize('template,text,structured', SAMPLES)
def test_three_roofs_have_known_data_and_exact_task_text(template,text,structured):
    identifier = template + '-known'
    data = {'brief':'guangzhu.brief/1','project':{'id':identifier,'template':template},
            'requirements':{'text':text,'structured':structured},'economics':{},
            'run':{'max_rounds':6,'compare':True,'prefer':'balanced',
                   'review':{'enabled':True,'model':'agnes-3.0-flash'},'export':True}}
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    expected = ('【光筑任务书 v1｜一键模式】\n'
                '请用 pv-rooftop-design 的一键模式，按本任务书一次做完，中途不要向我提问。缺项用默认值；要求互相矛盾或做不到时，停下并按 Skill 的格式给出放宽建议。\n'
                '全程中文。最终回答和追问的所有数字只照抄本次相关工具返回，不自行推算工具未返回的百分比、增量或差值；不要把 tilt_trials 当方案指标。\n'
                '多朝向发电复核按组照抄；next_group_offset非空时用group_offset续取，直到为空，各页合计均为全设计。\n'
                '风荷载参数未核验时必须照抄示意说明；L01按最不利区，W01按夹具实际布点；不能减小抗风所需压块来消除承重失败。\n'
                '空地和车棚称新建安装面；空地核对G08，车棚核对G09，L01不适用且基础/钢结构须厂家设计。'
                '空地离地、road_every/road_width_m/fence_setback_m可传排板工具；车棚clear_height_m和0–15°倾角可改。\n'
                '最终选定版本须串行：先单独调用 gz_analyze，等待成功结果；再单独调用 gz_crosscheck_yield，等待成功结果；之后才按任务书模式审核或申请 gz_export。不得在同一轮回复并发或批量调用这些工具。\n'
                '检查点：gz_set_requirements 返回 contradictions 非空，立即结束本轮工具调用，禁止再调用任何工具；不能用 gz_set_requirements 试写候选。只在文字里依据本次矛盾提出能解除整组冲突的单项建议，不编数值。取消冲突下限是合法单项，无需先试保存；依赖该下限的预算不足、屋顶上限冲突同时不成立，其他要求不变。仍有矛盾的候选不得编号为建议；唯一可行候选必须列为建议①，不凑建议②③，无则只说明。建议置前，每条一行、最多三条、合计不超过200字，写原值/单位；说明后置。工具审批不等于同意放宽要求；只有用户明确同意后才改该项、同步原文和结构化值并重存需求，仍有矛盾必须再停。\n'
                f'新项目：{identifier}（屋顶模板 {template}）\n我的要求：{text}\n'
                '建项目时将facts里已填的roof_age_years、transformer_kva传给gz_new_project.facts。峰谷、税和贷款已由工具计算。\n'
                '任务书数据（以此为准）：\n'
                f'```json\n{encoded}\n```\n'
                '审核员任务（run.review.enabled 为真时，原样作为 subagent_fork 的 question，只把〔版本〕换成实际版本号）：\n'
                + REVIEW.format(project_id=identifier))
    spec = brief.BriefSpec(template=template,id=identifier,text=text,structured=structured,review_mode='subagent')
    assert brief.render_brief(spec) == expected
    assert brief.render_brief(spec.model_dump()) == expected
    assert brief.render_review(identifier, 7) == REVIEW.format(project_id=identifier).replace('〔版本〕','7')


def test_integer_keys_order_empty_fields_and_json_stringify_number_spelling():
    spec = brief.BriefSpec(template='changzhou-demo',id='n',text='一' * 200,
        structured={'notes':'','payback_years_max':6.0,'budget_cny_max':300000.0,'keep_clear_ids':[]},
        economics={'price_export_cny_kwh':0,'price_self_cny_kwh':0.65,'self_use_ratio':1e-7,'capex_cny_per_w':2.6},
        review=False,export=False,max_rounds=1,prefer='fast_payback')
    rendered = brief.render_brief(spec)
    data = payload(rendered)
    assert list(data) == ['brief','project','requirements','economics','run']
    assert list(data['requirements']['structured']) == ['budget_cny_max','payback_years_max']
    assert list(data['economics']) == ['capex_cny_per_w','self_use_ratio','price_self_cny_kwh','price_export_cny_kwh']
    assert '6.0' not in rendered and '300000.0' not in rendered
    assert '"self_use_ratio":1e-7' in rendered
    assert data['run']['review']['enabled'] is False and data['run']['export'] is False


@pytest.mark.parametrize('change', [
    {'id':'../bad'}, {'template':'not-existing'}, {'text':''}, {'text':' '}, {'text':'一' * 201},
    {'max_rounds':0}, {'max_rounds':7}, {'max_rounds':True}, {'prefer':'auto'},
    {'structured':{'payback_years_max':.9}}, {'structured':{'budget_cny_max':9999}},
    {'structured':{'capacity_kw_min':5001}}, {'structured':{'capacity_kw_min':20,'capacity_kw_max':10}},
    {'structured':{'walkway_m_min':3.01}}, {'structured':{'edge_setback_m_min':5.01}},
    {'structured':{'tilt_deg_range':[20,15]}}, {'structured':{'keep_clear_ids':['unknown']}},
    {'structured':{'notes':'一'*201}}, {'economics':{'price_self_cny_kwh':.09}},
    {'economics':{'capex_cny_per_w':6.1}}, {'economics':{'self_use_ratio':1.01}},
    {'economics':{'discount_rate':.06}}, {'economics':{'price_export_cny_kwh':float('nan')}},
    {'structured':None}, {'structured':[]}, {'structured':{'notes':7}},
    {'structured':{'tilt_deg_range':20}}, {'structured':{'walkway_m_min':True}},
    {'economics':{'unknown':None}},
    {'compare':'yes'}, {'review':1}, {'export':'false'}, {'review_mode':'unknown'},
])
def test_invalid_input_is_rejected(change):
    with pytest.raises((ValidationError, ValueError)):
        brief.BriefSpec(**({'template':'changzhou-demo','id':'valid','text':'需要设计'} | change))


def test_cli_converts_budget_and_percentage_without_creating_a_project(capsys):
    assert brief.main(['--template','changzhou-demo','--id','cli-known','--text','需要设计',
                       '--budget','30','--self-use','80','--walkway','0','--keep','sky-1',
                       '--tilt','0','35','--no-review','--no-export']) == 0
    data = payload(capsys.readouterr().out)
    assert data['requirements']['structured'] == {'budget_cny_max':300000,'walkway_m_min':0,
                                                'keep_clear_ids':['sky-1'],'tilt_deg_range':[0,35]}
    assert data['economics'] == {'self_use_ratio':.8}
    assert data['run']['review']['enabled'] is False and data['run']['export'] is False


def test_cli_invalid_values_have_nonzero_exit(capsys):
    assert brief.main(['--template','changzhou-demo','--id','cli-bad','--text','需求','--payback','26']) == 1
    assert '任务书' in capsys.readouterr().err


@pytest.mark.parametrize('maximum',[False,True])
@pytest.mark.parametrize('phase_field', ['phase1_kw', 'phase1_budget_cny'])
def test_all_form_ranges_accept_endpoints_and_model_dump_roundtrip(maximum, phase_field):
    structured = {key: values[maximum] for key, values in brief.FIELD_RANGES.items()
                  if key in brief.STRUCTURED_FIELDS and key != 'tilt_deg_range' and key != 'notes'}
    structured.pop('phase1_budget_cny' if phase_field == 'phase1_kw' else 'phase1_kw')
    structured['tilt_deg_range'] = [0,35]
    structured['notes'] = '注' * 200
    economics = {key: brief.FIELD_RANGES[key][maximum] for key in brief.ECONOMICS_FIELDS if key in brief.FIELD_RANGES}
    economics.update(loan_years=25, green_sold_share=0, tariff_class='two_part', posttax_payback=maximum)
    spec = brief.BriefSpec(template='changzhou-demo',id='x'*64,text='需求',structured=structured,economics=economics)
    rendered = brief.render_brief(spec)
    assert brief.render_brief(spec.model_dump()) == rendered
    assert payload(rendered)['requirements']['structured'] == structured


@pytest.mark.parametrize('maximum', [False, True])
def test_brief_rejects_simultaneous_phase_targets_at_endpoints(maximum):
    structured = {key: brief.FIELD_RANGES[key][maximum] for key in ('phase1_kw', 'phase1_budget_cny')}
    with pytest.raises(ValidationError, match='一期装机与一期预算只能填一项'):
        brief.BriefSpec(template='changzhou-demo', id='phase-conflict', text='需求', structured=structured)


def test_fixed_notation_matches_javascript_near_small_ratio_threshold():
    spec = brief.BriefSpec(template='changzhou-demo',id='ratio',text='需求',economics={'self_use_ratio':1e-6})
    assert '"self_use_ratio":0.000001' in brief.render_brief(spec)


def test_independent_design_defers_all_reviewer_work_until_external_session_after_export():
    rendered = brief.render_brief(brief.BriefSpec(template='changzhou-demo', id='fallback', text='需求', review_mode='independent'))
    assert payload(rendered)['run']['review']['mode'] == 'independent'
    instruction = rendered.split('任务书数据')[0]
    assert '本设计会话不创建或调用任何审核员' in instruction
    assert '所有 subagent_* 工具' in instruction
    assert 'subagent_fork、subagent_spawn、subagent_collect' in instruction
    assert '先申请导出，导出完成后结束本设计会话' in instruction
    assert '外部桌面软件之后另建 Agnes 原生会话' in instruction
    assert '以下仅供外部桌面软件发送到后续独立审核会话，本设计会话不得执行' in rendered


@pytest.mark.parametrize('mode', [None, 'independent', 'subagent'])
def test_cli_review_default_and_explicit_legacy_mode_match_model(mode, capsys):
    fields = dict(template='changzhou-demo', id='review-default', text='需要设计')
    arguments = ['--template', fields['template'], '--id', fields['id'], '--text', fields['text']]
    if mode is not None:
        arguments += ['--review-mode', mode]
        fields['review_mode'] = mode
    assert brief.main(arguments) == 0
    rendered = capsys.readouterr().out.rstrip('\r\n')
    spec = brief.BriefSpec(**fields)
    assert spec.review_mode == (mode or 'independent')
    assert rendered == brief.render_brief(spec)
    assert payload(rendered)['run']['review'].get('mode', 'subagent') == (mode or 'independent')


@pytest.mark.parametrize('template,identifier,text,flags', [
    ('changzhou-demo', 't10-changzhou-example', '6 年内回本，留 1 米检修通道，别挡天窗',
     ['--payback', '6', '--walkway', '1', '--keep', 'sky-1']),
    ('l-shape', 't10-lshape-example', '总预算最多 30 万元，要留 1 米检修通道，别挡天窗',
     ['--budget', '30', '--walkway', '1', '--keep', 'sky']),
    ('rotated', 't10-rotated-example', '组件倾角必须在 15–20 度之间，要留 1 米检修通道，别挡天窗',
     ['--tilt', '15', '20', '--walkway', '1', '--keep', 'sky-1']),
])
def test_documented_samples_are_current_cli_default_output(template, identifier, text, flags, capsys):
    assert brief.main(['--template', template, '--id', identifier, '--text', text, *flags]) == 0
    rendered = capsys.readouterr().out.rstrip('\r\n')
    document = (Path(__file__).resolve().parents[1] / 'docs/agh-prompts.md').read_text(encoding='utf-8')
    sample = document.split(f'### {template}\n', 1)[1].split('````text\n', 1)[1].split('\n````', 1)[0]
    assert sample == rendered
    assert payload(sample)['run']['review']['mode'] == 'independent'


def test_legacy_brief_evidence_retains_only_documented_t25_t30_t31_t33_prompt_additions():
    path = Path(__file__).resolve().parents[1] / 'reports/assets/T14-r1/kernel/brief-before.json'
    for row in json.loads(path.read_text(encoding='utf-8')):
        actual = brief.render_brief(row['spec'])
        actual = actual.replace('多朝向发电复核按组照抄；next_group_offset非空时用group_offset续取，直到为空，各页合计均为全设计。\n', '')
        actual = actual.replace('各调用一次；复核若有next_group_offset，用group_offset续取全部组；', '各调用一次；')
        actual = actual.replace('建项目时将facts里已填的roof_age_years、transformer_kva传给gz_new_project.facts。峰谷、税和贷款已由工具计算。\n', '')
        actual = actual.replace('风荷载参数未核验时必须照抄示意说明；L01按最不利区，W01按夹具实际布点；不能减小抗风所需压块来消除承重失败。\n', '')
        actual = actual.replace('空地和车棚称新建安装面；空地核对G08，车棚核对G09，L01不适用且基础/钢结构须厂家设计。'
                                '空地离地、road_every/road_width_m/fence_setback_m可传排板工具；车棚clear_height_m和0–15°倾角可改。\n', '')
        assert actual == row['output']


@pytest.mark.parametrize('mode', ['subagent', 'independent'])
@pytest.mark.parametrize('template,text,structured', SAMPLES)
def test_checkpoint_filters_whole_constraint_set_before_numbering_without_changing_requirements(mode,template,text,structured):
    rendered = brief.render_brief(brief.BriefSpec(template=template,id='checkpoint-generic',text=text,
                                                structured=structured,review_mode=mode))
    instruction = rendered.split('新项目：')[0]
    for requirement in ('能解除整组冲突', '依赖该下限的预算不足、屋顶上限冲突同时不成立',
                        '不得编号为建议', '唯一可行候选必须列为建议①', '不凑建议②③', '仍有矛盾必须再停'):
        assert requirement in instruction
    assert payload(rendered)['requirements'] == {'text':text,'structured':structured}
    assert not any(test_value in instruction for test_value in ('50000', '777000', '300 千瓦', '154 千瓦', 'l-shape'))


@pytest.mark.parametrize('mode', ['subagent', 'independent'])
def test_checkpoint_ends_tool_phase_until_explicit_requirement_consent(mode):
    from guangzhu.config import ROOT
    rendered=brief.render_brief(brief.BriefSpec(template='rotated',id='stop-write',text='保留原要求',review_mode=mode))
    instruction=rendered.split('新项目：')[0]
    skill=(ROOT/'.agh/skills/pv-rooftop-design/SKILL.md').read_text(encoding='utf-8')
    checkpoint=skill.split('3. ',1)[1].split('\n4. ',1)[0]
    for content in (instruction,checkpoint):
        for constraint in ('contradictions 非空', '立即结束本轮工具调用', '禁止再调用任何工具',
                           '不能用 gz_set_requirements 试写候选', '只在文字里', '无需先试保存',
                           '用户明确同意后', '工具审批不等于同意放宽要求'):
            assert constraint in content
    assert payload(rendered)['requirements']['structured']=={}


@pytest.mark.parametrize('mode', ['subagent', 'independent'])
def test_selected_version_analysis_and_crosscheck_wait_for_results_before_export(mode):
    from guangzhu.config import ROOT
    rendered=brief.render_brief(brief.BriefSpec(template='rotated',id='serial-final',text='保留原要求',review_mode=mode))
    skill=(ROOT/'.agh/skills/pv-rooftop-design/SKILL.md').read_text(encoding='utf-8')
    for content in (rendered.split('新项目：')[0],skill.split('6. ',1)[1].split('\n7. ',1)[0]):
        assert '先单独调用 gz_analyze，等待成功结果；再单独调用 gz_crosscheck_yield，等待成功结果' in content
        assert '之后才按任务书模式审核或申请 gz_export' in content
        assert '不得在同一轮回复并发或批量调用这些工具' in content
    assert payload(rendered)['requirements']=={'text':'保留原要求','structured':{}}
