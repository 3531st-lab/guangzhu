"""Single source for desktop/CLI task and reviewer text; no model calls."""

import argparse
from decimal import Decimal
import json
import math
import re
import sys
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from .config import ROOT
from .models import Economics, GzError, SiteFacts, StructuredRequirements, project_id
from .sitecheck import flags
from .templates import read_template
from .economic_fields import LABELS, BOOLEANS, RANGES

BRIEF_TEMPLATE = (
    '【光筑任务书 v1｜一键模式】\n'
    '请用 pv-rooftop-design 的一键模式，按本任务书一次做完，中途不要向我提问。缺项用默认值；要求互相矛盾或做不到时，停下并按 Skill 的格式给出放宽建议。\n'
    '全程中文。最终回答和追问的所有数字只照抄本次相关工具返回，不自行推算工具未返回的百分比、增量或差值；不要把 tilt_trials 当方案指标。\n'
    '多朝向发电复核按组照抄；next_group_offset非空时用group_offset续取，直到为空，各页合计均为全设计。\n'
    '风荷载参数未核验时必须照抄示意说明；L01按最不利区，W01按夹具实际布点；不能减小抗风所需压块来消除承重失败。\n'
    '空地和车棚称新建安装面；空地核对G08，车棚核对G09，L01不适用且基础/钢结构须厂家设计。'
    '空地离地、road_every/road_width_m/fence_setback_m可传排板工具；车棚clear_height_m和0–15°倾角可改。\n'
    '最终选定版本须串行：先单独调用 gz_analyze，等待成功结果；再单独调用 gz_crosscheck_yield，等待成功结果；之后才按任务书模式审核或申请 gz_export。不得在同一轮回复并发或批量调用这些工具。\n'
    '检查点：gz_set_requirements 返回 contradictions 非空，立即结束本轮工具调用，禁止再调用任何工具；不能用 gz_set_requirements 试写候选。只在文字里依据本次矛盾提出能解除整组冲突的单项建议，不'
    '编数值。取消冲突下限是合法单项，无需先试保存；依赖该下限的预算不足、屋顶上限冲突同时不成立，其他要求不变。仍有矛盾的候选不得编号为建议；唯一可行候选必须列为建议①，不凑建议②③，无则只说明。建议置前，每条一行、最多三条、合计不超过200字，写原'
    '值/单位；说明后置。工具审批不等于同意放宽要求；只有用户明确同意后才改该项、同步原文和结构化值并重存需求，仍有矛盾必须再停。\n'
    '新项目：{project_id}（屋顶模板 {template}）\n'
    '我的要求：{text}\n'
    '{facts}'
    '建项目时将facts里已填的roof_age_years、transformer_kva传给gz_new_project.facts。峰谷、税和贷款已由工具计算。\n'
    '任务书数据（以此为准）：\n'
    '```json\n'
    '{data}\n'
    '```\n'
    '审核员任务（run.review.enabled 为真时，原样作为 subagent_fork 的 question，只把〔版本〕换成实际版本号）：\n'
    '{review_task}'
)
REVIEW_TEMPLATE = ("你是光筑独立审核员。项目 {project_id}，版本{version}。只调用 gz_project_summary、gz_analyze、"
    "gz_crosscheck_yield 这三个只读工具，各调用一次；复核若有next_group_offset，用group_offset续取全部组；不修改方案，不导出，不调用 gz_record_review。"
    "检查用户要求、硬性规则、发电量复核和经济假设，所有数字都照抄工具结果。最后先用一句话给出结论，再输出一个 json 代码块，"
    '格式为 {{"verdict":"approve 或 revise","findings":[{{"severity":"high、medium 或 low","item":"检查项",'
    '"evidence":"证据，带数字","suggestion":"建议"}}]}}，代码块后面不再写别的。')
INDEPENDENT_BRIEF_TEMPLATE = BRIEF_TEMPLATE.replace(
    "新项目：", "独立审核模式：本设计会话不创建或调用任何审核员，禁止所有 subagent_* 工具（包括 subagent_fork、subagent_spawn、subagent_collect），不调用 gz_record_review。"
    "按正常设计流程先申请导出，导出完成后结束本设计会话；run.export=false 时完成设计后结束。外部桌面软件之后另建 Agnes 原生会话执行审核，本设计会话不等待审核结果。\n新项目：").replace(
    "审核员任务（run.review.enabled 为真时，原样作为 subagent_fork 的 question，只把〔版本〕换成实际版本号）：",
    "独立审核任务（以下仅供外部桌面软件发送到后续独立审核会话，本设计会话不得执行；run.review.enabled 为真时发送，只换〔版本〕）：")
STRUCTURED_FIELDS = tuple(StructuredRequirements.model_fields)
ECONOMICS_FIELDS = ("capex_cny_per_w", "self_use_ratio", "price_self_cny_kwh", "price_export_cny_kwh") + tuple(LABELS)
FIELD_RANGES = {
    "budget_cny_max": (10000, 100000000), "payback_years_max": (1, 25),
    "capacity_kw_min": (1, 5000), "capacity_kw_max": (1, 5000), "walkway_m_min": (0, 3),
    "obstacle_clearance_m_min": (0, 5), "edge_setback_m_min": (0, 5), "tilt_deg_range": (0, 35),
    "price_self_cny_kwh": (.1, 2), "self_use_ratio": (0, 1), "capex_cny_per_w": (1, 6),
    "price_export_cny_kwh": (0, 1), "max_rounds": (1, 6), "text": (1, 200), "notes": (0, 200)}
FIELD_RANGES.update(RANGES)
CLI_FIELDS = {
    "payback": "payback_years_max", "budget": "budget_cny_max", "capacity-min": "capacity_kw_min",
    "capacity-max": "capacity_kw_max", "walkway": "walkway_m_min", "obstacle-clearance": "obstacle_clearance_m_min",
    "edge-setback": "edge_setback_m_min", "price-self": "price_self_cny_kwh", "self-use": "self_use_ratio",
    "capex": "capex_cny_per_w", "price-export": "price_export_cny_kwh"}
FIELD_RANGES.update(curtail_pct_max=(0, 100), transformer_kva=(.01, 100000), transformer_share=(.001, 1),
                    max_height_m=(0, 100), phase1_kw=(.001, 100000), phase1_budget_cny=(.01, 1e9))


def check_equipment(value):
    """The chosen module, inverter and brand exist in the catalogue and agree; also used when a project is created."""
    from .electrical import load_catalog
    if set(value) - {'module_id', 'inverter_id', 'inverter_brand'}:
        raise ValueError('设备字段不支持')
    for key, file in [('module_id', 'modules.csv'), ('inverter_id', 'inverters.csv')]:
        if key in value and value[key] not in load_catalog(file):
            raise ValueError('设备型号不在目录中')
    brand = value.get('inverter_brand')
    if brand and (brand not in ('Sungrow', 'Huawei') or value.get('inverter_id') and
                  load_catalog('inverters.csv')[value['inverter_id']]['manufacturer'] != brand):
        raise ValueError('逆变器品牌与型号不匹配')


def stored(info):
    """A park queue's task book was checked when it was queued; a building removed later or an upgrade must not make the saved queue unreadable."""
    return (info.context or {}).get('stored') is True


class BriefSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    template: str
    id: str
    text: str = Field(min_length=1, max_length=200)
    structured: StructuredRequirements = Field(default_factory=StructuredRequirements)
    economics: Economics = Field(default_factory=Economics)
    equipment: dict[str, str] | None = None
    facts: SiteFacts | None = None  # T22: optional answers before construction
    max_rounds: int = Field(default=6, ge=1, le=6, strict=True)
    compare: bool = Field(default=True, strict=True)
    prefer: Literal["balanced", "max_capacity", "fast_payback"] = "balanced"
    review: bool = Field(default=True, strict=True)
    review_mode: Literal["subagent", "independent"] = "independent"
    reviewer_model: str = Field(default="agnes-3.0-flash", min_length=1)
    export: bool = Field(default=True, strict=True)

    @field_validator('equipment')
    @classmethod
    def selected_module(cls, value, info):
        if value is not None and not stored(info):
            check_equipment(value)
        return value

    @field_validator("structured", "economics", mode="before")
    @classmethod
    def form_bounds(cls, value, info):
        if stored(info): return value
        if not isinstance(value, (dict, BaseModel)): raise ValueError("任务书字段须为对象")
        value = value.model_dump() if isinstance(value, BaseModel) else dict(value)
        model = StructuredRequirements if info.field_name == "structured" else Economics
        if set(value) - model.model_fields.keys(): raise ValueError("任务书字段不支持")
        value = {key: item for key, item in value.items() if item not in (None, "", [])}
        for key, item in value.items():
            if key in ('export_allowed', 'ballast_only') or key in BOOLEANS:
                if type(item) is not bool:
                    raise ValueError('余电上网、只用压载等开关须为布尔值')
                continue
            if key in ("keep_clear_ids", "notes") and info.field_name == "structured":
                if key == "notes" and (not isinstance(item, str) or len(item) > 200): raise ValueError("补充说明最多200字")
                continue
            if key not in (STRUCTURED_FIELDS if info.field_name == "structured" else ECONOMICS_FIELDS):
                raise ValueError("任务书字段不支持")
            if key == 'tariff_class':
                if item not in ('two_part', 'single100', 'single_small'):
                    raise ValueError('电价类别不正确')
                continue
            numbers = item if key == "tilt_deg_range" else [item]
            if not isinstance(numbers, (list, tuple)): raise ValueError("倾角须为两个数值")
            low, high = FIELD_RANGES[key]
            if any(type(number) not in (int, float) or not math.isfinite(number)
                   or not low <= number <= high for number in numbers):
                raise ValueError("任务书数值超出表单范围")
            if key == "tilt_deg_range" and (len(numbers) != 2 or numbers[0] > numbers[1]):
                raise ValueError("倾角须从小到大")
        return value

    @model_validator(mode="after")
    def template_and_order(self, info):
        if stored(info): return self
        try:
            project_id(self.id)
            template = read_template(self.template, root=ROOT)['roof']
        except GzError as error: raise ValueError(error.message_zh) from error
        if not self.text.strip():
            raise ValueError("模板不存在或需求为空")
        if template["type"] == "metal":
            self.compare = False
        zones = {row["id"] for row in template.get("obstacles", []) + template.get("keepouts", [])}
        if not set(self.structured.keep_clear_ids) <= zones: raise ValueError("留空编号不在模板中")
        low, high = self.structured.capacity_kw_min, self.structured.capacity_kw_max
        if low is not None and high is not None and low > high: raise ValueError("装机下限不能超过上限")
        return self


def _numbers(value):
    if isinstance(value, dict): return {key: _numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [_numbers(item) for item in value]
    return int(value) if type(value) is float and value.is_integer() else value


def _json_number(match):
    token = match.group(1)
    if token is None: return match.group()
    if "e" in token and Decimal("1e-6") <= abs(Decimal(token)) < Decimal("1e21"):
        return format(Decimal(token), "f")
    return re.sub(r"e([+-])0+(\d+)", r"e\1\2", token)


def render_review(identifier, version="〔版本〕"):
    return REVIEW_TEMPLATE.format(project_id=project_id(identifier), version=version)


def site_line(facts, roof_type="flat", roof=None):
    """T22: the answers as one plain line, so the AI copies its eighth part instead of judging raw fields (a blank is not a no)."""
    found = flags(facts, roof_type, roof)
    return f"开工前问答——要当心：{'、'.join(found['risk']) or '无'}；没填：{'、'.join(found['ask']) or '无'}（第八段照抄这两项，不改写、不推断）\n"


def render_brief(spec) -> str:
    spec = spec if isinstance(spec, BriefSpec) else BriefSpec.model_validate(spec)
    fields = lambda model, order: {key: getattr(model, key) for key in order if getattr(model, key) not in (None, "", [])}
    structured = fields(spec.structured, STRUCTURED_FIELDS)
    if "budget_cny_max" in structured: structured["budget_cny_max"] = math.floor(structured["budget_cny_max"] + .5)
    answers = spec.facts.model_dump() if spec.facts else {}
    economy = fields(spec.economics, ECONOMICS_FIELDS)
    if answers.get("monthly_kwh") is not None and answers.get("shifts") is not None:
        economy.update(monthly_kwh=answers["monthly_kwh"], shifts=answers["shifts"])
    if answers.get("export_allowed") is False:
        economy["price_export_cny_kwh"] = 0
        structured.setdefault('export_allowed', False)
    if answers.get('transformer_kva') is not None:
        structured.setdefault('transformer_kva', answers['transformer_kva'])
    data = dict(brief="guangzhu.brief/1", project=dict(id=spec.id, template=spec.template),
        requirements=dict(text=spec.text, structured=structured), economics=economy,
        **(dict(equipment=spec.equipment) if spec.equipment else {}),
        **({"facts": answers} if answers else {}),
        run=dict(max_rounds=spec.max_rounds, compare=spec.compare, prefer=spec.prefer,
                 review=dict(enabled=spec.review, model=spec.reviewer_model), export=spec.export))
    if spec.review_mode == "independent": data["run"]["review"]["mode"] = "independent"
    encoded = json.dumps(_numbers(data), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    encoded = re.sub(r'"(?:\\.|[^"\\])*"|(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)', _json_number, encoded)
    template = INDEPENDENT_BRIEF_TEMPLATE if spec.review_mode == "independent" else BRIEF_TEMPLATE
    roof = read_template(spec.template, root=ROOT)['roof']
    roof_type = roof['type']
    return template.format(project_id=spec.id, template=spec.template, text=spec.text,
        facts=site_line(spec.facts, roof_type, roof) if answers or roof_type == "metal" or roof.get('use') else "",
        data=encoded, review_task=render_review(spec.id) if spec.review_mode == "subagent" else
        f"审核模式：项目 {spec.id}，版本〔版本〕。用 gz_project_summary、gz_analyze、gz_crosscheck_yield 审核，"
        f"再用 gz_record_review 保存 verdict、findings，reviewer_model 填 {spec.reviewer_model}。只用这四个工具，不修改方案、不导出。")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("template", "id", "text"): parser.add_argument("--" + name, required=True)
    for name in CLI_FIELDS: parser.add_argument("--" + name, dest=name, type=float)
    parser.add_argument("--keep", nargs="+", action="extend", default=[])
    parser.add_argument("--tilt", nargs=2, type=float); parser.add_argument("--notes")
    parser.add_argument("--max-rounds", type=int, default=6)
    parser.add_argument("--prefer", choices=("balanced", "max_capacity", "fast_payback"), default="balanced")
    parser.add_argument("--reviewer-model", default="agnes-3.0-flash")
    parser.add_argument("--review-mode", choices=("subagent", "independent"), default="independent")
    for name in ("compare", "review", "export"): parser.add_argument("--no-" + name, dest=name, action="store_false")
    args = vars(parser.parse_args(argv))
    structured = dict(keep_clear_ids=args.pop("keep"), tilt_deg_range=args.pop("tilt"), notes=args.pop("notes"))
    economics = {}
    for option, key in CLI_FIELDS.items():
        value = args.pop(option)
        if value is not None:
            value = value * 10000 if option == "budget" else value / 100 if option == "self-use" else value
            (economics if key in ECONOMICS_FIELDS else structured)[key] = value
    try: print(render_brief(BriefSpec(**args, structured=structured, economics=economics))); return 0
    except (ValidationError, ValueError, GzError): print("任务书字段、模板或数值范围不正确", file=sys.stderr); return 1


if __name__ == "__main__": raise SystemExit(main())
