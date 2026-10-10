"""Eleven queued JSON tools and a read-only waiter over the official MCP SDK."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Lock
from time import monotonic
from uuid import uuid4

import anyio
from jsonschema import Draft202012Validator
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from . import runtime_diagnostics as diagnostics

PROJECTS_OVERRIDE, OFFLINE_MODE = None, False
WAIT_SECONDS, REUSE_SECONDS = 40, 600
# UUID and fixed tool names add at most this many UTF-8 bytes to a saved result.
WAIT_METADATA_BYTES = 128


def obj(properties, required=()):
    return dict(type="object", properties=properties, required=list(required), additionalProperties=False)


def number(low=0, high=None, *, integer=False, nullable=False):
    kind = "integer" if integer else "number"
    return dict(type=[kind, "null"] if nullable else kind, minimum=low, **({} if high is None else dict(maximum=high)))


STRING = dict(type="string")
PID = dict(type="string", pattern="^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", maxLength=64)
VERSION = number(1, integer=True)
OFFLINE = dict(type="boolean", default=False)
def pair(item, nullable=False):
    return dict(type=["array", "null"] if nullable else "array", items=item, minItems=2, maxItems=2)


PARAMS = dict(tilt_deg=number(0, 35), azimuth_deg=number(90, 270),
              lower_edge_m=number(.3, 3), clear_height_m=number(0, 10), extra_row_gap_m=number(0, 30),
              road_every=number(integer=True), road_width_m=number(.1), fence_setback_m=number(),
              plane_ids=dict(type='array', items=number(1, integer=True), minItems=1),
              surface=dict(type='boolean', const=False),
              align=dict(type='string', enum=['south', 'edge']), layout=dict(type='string', enum=['rows', 'ew']),
              fill_landscape=dict(type='boolean'),
              orientation=dict(type="string", enum=["landscape", "portrait"]), rows_per_rack=number(1, 2, integer=True),
              edge_setback_m=number(), obstacle_clearance_m=number(), keepout_clearance_m=number(),
              walkway_every_n_rows=number(integer=True), walkway_width_m=number(), winter_window_hours=pair(number(0, 24)))
REQUIREMENTS = {key: number(nullable=True) for key in ("budget_cny_max", "capacity_kw_min", "capacity_kw_max",
                "walkway_m_min", "obstacle_clearance_m_min", "edge_setback_m_min")}
REQUIREMENTS.update(payback_years_max=dict(type=["number", "null"], exclusiveMinimum=0),
                    keep_clear_ids=dict(type="array", items=STRING), tilt_deg_range=pair(number(0, 35), True),
                    notes=dict(type=["string", "null"]))
WHERE = {key: obj({key: value}, [key]) for key, value in dict(
    shading_loss_gt=number(0, 100), zone_id=STRING, worst_count=VERSION).items()}
REQUIREMENTS.update(export_allowed=dict(type=['boolean', 'null']), ballast_only=dict(type=['boolean', 'null']),
                    curtail_pct_max=number(0, 100, nullable=True),
                    transformer_kva=number(.01, nullable=True), transformer_share=number(.001, 1, nullable=True),
                    max_height_m=number(nullable=True), phase1_kw=number(.001, nullable=True), phase1_budget_cny=number(.01, nullable=True))
OPS = [obj(dict(op=dict(type="string", const="remove_modules"), **props), ["op", *props]) for props in
       (dict(module_ids=dict(type="array", items=STRING)), dict(where=dict(oneOf=list(WHERE.values()))))]
parameter_op = obj(dict(op=dict(type='string', const='set_param'), name=dict(type='string'), value={}), ['op', 'name', 'value'])
parameter_op['oneOf'] = [dict(properties=dict(name=dict(const=name), value=value)) for name, value in PARAMS.items()]
OPS.append(parameter_op)
OPS += [obj(dict(op=dict(type="string", const="set_string_size"), modules_per_string=VERSION), ["op", "modules_per_string"]),
        obj(dict(op=dict(type="string", const="add_keepout"), polygon=dict(type="array", items=pair(dict(type="number")), minItems=3),
                 label=STRING, preset=dict(type='string', enum=['vent','skylight']), clearance_m=number()), ["op", "polygon", "label"])]
SCHEMAS = {
    "gz_wait": obj(dict(job_id=STRING), ["job_id"]),
    "gz_project_summary": obj(dict(project_id=PID), ["project_id"]),
    "gz_set_requirements": obj(dict(project_id=PID, text=STRING, structured=obj(REQUIREMENTS)), ["project_id", "text", "structured"]),
    "gz_fetch_weather": obj(dict(project_id=PID, source=dict(type="string", enum=["nasa_hourly", "pvgis_tmy"]),
                                 year=dict(type="integer", minimum=1981, maximum=2100, default=2023), offline=OFFLINE), ["project_id", "source"]),
    "gz_generate_layout": obj(dict(project_id=PID, params=obj(PARAMS)), ["project_id", "params"]),
    "gz_analyze": obj(dict(project_id=PID, version=VERSION, offline=OFFLINE, what_if=obj(dict(
        capex_change_pct=number(-50, 50), price_change_pct=number(-50, 50), self_use_ratio=number(0, 1),
        price_export_cny_kwh=number(0, 2)))), ["project_id", "version"]),
    "gz_edit_design": obj(dict(project_id=PID, version=VERSION, reason=dict(type="string", minLength=1),
                               ops=dict(type="array", minItems=1, items=dict(oneOf=OPS))), ["project_id", "version", "reason", "ops"]),
    "gz_compare_options": obj(dict(project_id=PID, base_version=VERSION, offline=OFFLINE), ["project_id", "base_version"]),
    "gz_crosscheck_yield": obj(dict(project_id=PID, version=VERSION, offline=OFFLINE, group_offset=number(integer=True)), ["project_id", "version"]),
    "gz_record_review": obj(dict(project_id=PID, version=VERSION, reviewer_model=dict(type="string", minLength=1),
        verdict=dict(type="string", enum=["approve", "revise"]), findings=dict(type="array", items=obj(dict(
            severity=dict(type="string", enum=["high", "medium", "low"]), item=STRING, evidence=STRING, suggestion=STRING),
            ["severity", "item", "evidence", "suggestion"]))), ["project_id", "version", "reviewer_model", "verdict", "findings"]),
    "gz_export": obj(dict(project_id=PID, version=VERSION, offline=OFFLINE), ["project_id", "version"]),
    "gz_new_project": obj(dict(project_id=PID, template=PID, equipment=obj(dict(module_id=STRING, inverter_id=STRING,
        inverter_brand=dict(type='string', enum=['Sungrow', 'Huawei']))), economics=obj(dict(
        price_self_cny_kwh=number(.1, 2), self_use_ratio=number(0, 1), capex_cny_per_w=number(1, 6),
        price_export_cny_kwh=number(0, 1), monthly_kwh=number(1), shifts=dict(type="integer", minimum=1, maximum=4)))),
        ["project_id", "template"]),
}
from .economic_fields import schemas as economic_schemas
SCHEMAS['gz_new_project']['properties']['economics']['properties'].update(economic_schemas())
SCHEMAS['gz_new_project']['properties']['facts'] = obj(dict(roof_age_years=number(0, 100), transformer_kva=number(1, 100000)))
SCHEMAS['gz_new_project']['properties']['facts']['properties'].update(
    land_type=dict(type='string', enum=['construction', 'cultivated', 'permanent', 'forest', 'grass', 'unused']),
    within_redline=dict(type='boolean'))

DESCRIPTIONS = {
    "gz_wait": "只读：等待已有后台计算，未完成时继续调用，完成时返回原工具结果。",
    "gz_project_summary": "返回摘要及已导出版本列表；版本、组件数、装机指最新版本，可能是对比候选。只读（只写可重算的缓存）。",
    "gz_set_requirements": "保存需求原话与结构化值，返回缺项及矛盾。",
    "gz_fetch_weather": "分析前取天气，返回条数、缺失、辐射、气温和来源。只读（只写可重算的缓存）。",
    "gz_generate_layout": "首次/重新排板，返回新增版本、组件数、装机和行距。",
    "gz_analyze": "分析/what_if（未保存）；返回规则及建议，rules.met是已满足的业主要求及实际值，yield_kwh.p50是基准年发电估算（NASA POWER 2023天气b链），不是概率P50。按suggestions_format完整展开区间为module_ids。只读（只写可重算的缓存）。",
    "gz_edit_design": "按分析建议修正时用；返回新增版本及变化，reason填写规则编号。",
    "gz_compare_options": "保存三方案；current是已有分析的当前方案；recommended按偏好给版本和理由。保留各方案违反要求；"
                          "tilt_trials仅挑最快回本倾角，不是方案指标；site_tilt是按当地天气算的最佳、多装、折中倾角及每千瓦损失；"
                          "kwh_per_kw单位kWh/kW。",
    "gz_crosscheck_yield": "复核五链；多朝向逐组及全设计合计。next_group_offset非空时用group_offset续取，数字照抄。只读（只写可重算的缓存）。",
    "gz_record_review": "设计会话原样保存独立审核员JSON，只新增审核意见并返回文件。",
    "gz_export": "硬性规则通过且用户批准后用；重新分析并导出JSON，返回文件及sha256。",
    "gz_new_project": "一键开始按模板建空项目并写经济参数，返回摘要与代码身份；已有编号拒绝覆盖。",
}
READONLY = {"gz_project_summary", "gz_fetch_weather", "gz_analyze", "gz_crosscheck_yield", "gz_wait"}
VALIDATORS = {name: Draft202012Validator(schema) for name, schema in SCHEMAS.items()}
TOOLS = [types.Tool(name=name, description=DESCRIPTIONS[name], inputSchema=schema,
         annotations=types.ToolAnnotations(readOnlyHint=name in READONLY, destructiveHint=False)) for name, schema in SCHEMAS.items()]


def call(name, arguments):
    with diagnostics.call_record(name, arguments):
        return _call(name, arguments)


def _call(name, arguments):
    from .models import GzError
    try:
        if name not in VALIDATORS:
            raise GzError("TOOL_UNKNOWN", "工具名称不正确", "使用tools/list中的十二个光筑工具")
        json.dumps(arguments, allow_nan=False)
        if not VALIDATORS[name].is_valid(arguments):
            raise GzError("INPUT_INVALID", "工具参数字段、类型或范围不正确", "按工具inputSchema填写，不传额外字段")
        with diagnostics.stage("tool.imports"):
            from . import mcp_actions, project as storage
        if PROJECTS_OVERRIDE is not None:
            storage.PROJECTS_DIR = PROJECTS_OVERRIDE
        if OFFLINE_MODE:
            import requests
            def forbidden(*args, **kwargs):
                raise GzError("NETWORK_DISABLED", "离线验证禁止网络请求", "使用仓库中的天气缓存")
            requests.Session.request = forbidden
            if name in {'gz_set_requirements', 'gz_generate_layout', 'gz_edit_design'}:
                arguments = dict(arguments, offline=True)
        with diagnostics.stage("tool.dispatch"):
            result = mcp_actions.dispatch(name, arguments)
        payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(payload.encode("utf-8")) > 2048:
            raise GzError("RESULT_TOO_LARGE", "结果超过摘要大小限制", "缩短需求或问题清单，完整数据见项目文件")
        return types.CallToolResult(content=[types.TextContent(type="text", text=payload)], isError=False)
    except GzError as error:
        result = error.as_dict()
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 1800:
            result = GzError(error.error_code, "数据未通过校验", "检查参数和项目文件后重试").as_dict()
    except Exception:
        result = GzError("TOOL_FAILED", "工具无法完成，请检查输入和本地数据", "核对项目编号、版本和离线缓存；不要使用Python报错作为结果").as_dict()
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, separators=(",", ":")))], isError=True)


class JobQueue:
    def __init__(self):
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.lock = Lock()
        self.jobs = {}

    def run(self, job, arguments):
        with self.lock:
            job["started"] = monotonic()
        try:
            result = call(job["tool"], arguments)
            with self.lock:
                job["reusable"] &= not result.is_error and json.loads(result.content[0].text).get("ok") is True
            return result
        finally:
            with self.lock:
                job["finished"] = monotonic()

    async def request(self, name, arguments):
        try:
            key = (name, json.dumps(arguments, sort_keys=True, allow_nan=False))
            valid = name in VALIDATORS and VALIDATORS[name].is_valid(arguments)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            return _call(name, arguments)
        with self.lock:
            now = monotonic()
            if name == "gz_wait":
                job = self.jobs.get(arguments["job_id"])
            else:
                job = next((j for j in self.jobs.values() if j["key"] == key and j["reusable"] and
                            (j["finished"] is None or now - j["finished"] < REUSE_SECONDS)), None)
                if job is None:
                    writes = name in {"gz_new_project", "gz_set_requirements", "gz_generate_layout", "gz_edit_design", "gz_compare_options"}
                    summary_changed = name == "gz_export" or (name == "gz_analyze" and arguments.get("what_if") is None)
                    # Invalidate at submission so a read cannot skip an earlier queued write.
                    for previous in self.jobs.values():
                        if previous["project_id"] == arguments["project_id"] and (writes or
                                summary_changed and previous["tool"] == "gz_project_summary"):
                            previous["reusable"] = False
                    job = dict(id=uuid4().hex, tool=name, key=key, submitted=now, started=None, finished=None,
                               project_id=arguments["project_id"], reusable=True)
                    self.jobs[job["id"]] = job
                    job["future"] = self.pool.submit(self.run, job, json.loads(json.dumps(arguments)))
        if job is None:
            from .models import GzError
            error = GzError("JOB_UNKNOWN", "后台计算记录已失效，请按原参数重新调用原工具", "按原参数重新调用原工具")
            return self.response(error.as_dict(), True)
        deadline = monotonic() + WAIT_SECONDS
        while not job["future"].done() and monotonic() < deadline:
            await anyio.sleep(min(.05, max(0, deadline - monotonic())))
        if job["future"].done():
            result = job["future"].result()
            if name != "gz_wait":
                return result
            value = json.loads(result.content[0].text)
            value.update(tool=job["tool"], job_id=job["id"])
            return self.response(value, result.is_error)
        with self.lock:
            stage = diagnostics.current_stage() if job["started"] is not None and job["finished"] is None else "正在准备/计算，请稍候"
            if job["started"] is None:
                stage = "排队中，等待前面的计算完成"
        return self.response(dict(ok=True, pending=True, job_id=job["id"], tool=job["tool"],
            elapsed_s=round(monotonic() - job["submitted"], 1), stage=stage,
            next=f'立即调用 gz_wait，参数 {{"job_id":"{job["id"]}"}}；不要结束回复，不要重新调用本工具'))

    @staticmethod
    def response(value, error=False):
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return types.CallToolResult(content=[types.TextContent(type="text", text=payload)], isError=error)


async def serve():
    queue = JobQueue()
    async def list_tools(context, params):
        return types.ListToolsResult(tools=TOOLS)
    async def call_tool(context, params):
        return await queue.request(params.name, params.arguments if params.arguments is not None else {})
    server = Server("guangzhu", version="T08", on_list_tools=list_tools, on_call_tool=call_tool)
    try:
        async with stdio_server() as (reader, writer):
            await server.run(reader, writer, server.create_initialization_options())
    finally:
        queue.pool.shutdown(wait=False)


def main():
    global PROJECTS_OVERRIDE, OFFLINE_MODE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects-dir", type=Path, help="隔离验证使用的项目根目录")
    parser.add_argument("--offline", action="store_true", help="验证模式：禁止网络请求")
    args = parser.parse_args()
    PROJECTS_OVERRIDE = args.projects_dir.resolve() if args.projects_dir else None
    OFFLINE_MODE = args.offline
    diagnostics.startup()
    from . import mcp_actions, project as storage
    directory = PROJECTS_OVERRIDE or storage.PROJECTS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    (directory / '.mcp-startup.json').write_text(json.dumps(mcp_actions.CODE_IDENTITY), encoding='utf-8')
    anyio.run(serve)


if __name__ == "__main__":
    main()
