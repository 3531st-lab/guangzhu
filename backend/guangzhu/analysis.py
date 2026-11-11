"""Run versioned engineering and economic calculations with a compact summary."""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from . import project as storage, shading, electrical, structure, rules, economics, yieldsim
from .models import GzError
from .runtime_diagnostics import stage
from . import orientation
from .wind import facts as wind_facts


def serialized(summary):
    return json.dumps(summary,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def _compact_removal(op):
    ids=op.get('module_ids')
    if op.get('op')!='remove_modules' or not ids or any('..' in value for value in ids):return op
    groups,encoded={},[]
    for value in ids:
        match=re.fullmatch(r'(.*?)(\d+)',value)
        if match:groups.setdefault((match[1],len(match[2])),[]).append(int(match[2]))
        else:encoded.append(value)
    for (prefix,width),values in sorted(groups.items()):
        values=sorted(values); start=end=values[0]
        def interval(first,last):
            a,b=prefix+str(first).zfill(width),prefix+str(last).zfill(width)
            return a if first==last else a+'..'+b
        for value in values[1:]:
            if value==end+1:end=value
            else:encoded.append(interval(start,end)); start=end=value
        encoded.append(interval(start,end))
    compact=dict(op=op['op'],module_id_ranges=encoded)
    return compact if len(serialized(compact))<len(serialized(op)) else op


def _summary(design,shadows,electric,load,cash,yield_kwh,checked,*,omitted=None):
    round_value=lambda value:round(value,4) if isinstance(value,(float,int)) else value
    fields=lambda obj,keys:{key:round_value(obj[key]) for key in keys}
    result=dict(ok=True,version=design.version,modules=len(design.modules),dc_kw=round_value(electric['dc_kw']),
                yield_kwh=fields(yield_kwh,['p50','low','high','per_kw'])|dict(omitted={key:'缺PVGIS' if key=='d' else '缺链' for key in (omitted or {})}),
                shading=fields(shadows['summary'],['avg_loss_pct','modules_over_threshold','threshold_pct']),
                electrical=fields(electric,['modules_per_string','voc_cold_v','vmp_hot_v','dc_ac_ratio','dc_drop_pct_max','ac_drop_pct_max']),
                load=fields(load,['added_kn_m2','capacity_kn_m2']), wind=wind_facts(load.get('wind'), design.version),
                economics=fields(cash,['capex_cny','payback_years','irr_pct','lcoe_cny_kwh','co2_t_per_year']),
                rules=dict(total=checked['total'],passed=checked['passed'],
                           hard_failed=sum(item['level']=='hard' and item['status']=='fail' for item in checked['items']),failed=[]),suggestions=[])
    result['electrical'].update(voc_limit_v=electric['checks']['E01']['limit'],mppt_min_v=electric['checks']['E03']['limit'])
    result['electrical']['rated_ac_kw'] = cash.get('costs', {}).get('rated_ac_kw')
    transformer = next((r for r in checked['items'] if r['id'] == 'U06'), None)
    if transformer is not None:
        result['electrical']['rated_ac_kw'] = transformer['value']
    if 'modules_per_string_short' in electric:
        result['electrical']['modules_per_string_short'] = electric['modules_per_string_short']
    if cash.get('self_use', {}).get('algorithm') == '按用电逐时算':
        result['economics']['self_use_ratio'] = round_value(cash['params']['self_use_ratio'])
    if cash.get('u04_basis') == '税后':
        result['economics'].update(payback_basis='税后', required_payback_years=round_value(cash['u04_payback_years']))
    if 'governing_plane' in load:
        result['load']['governing_plane'] = load['governing_plane']
    if load.get('livestock'):
        usage = load['livestock']
        result['use'] = usage['title']
        if usage['use'] == 'grazing':
            result['ground_sun_pct'] = round_value(usage['ground_light']['sun_pct'])
    for item in checked['items']:
        if item['status']!='fail':continue
        failed={key:item[key] for key in ['id','level','name_zh','value','limit','hint_zh']}
        if 'plane' in item:
            failed['plane'] = item['plane']
        failed['value']=round_value(failed['value'])
        if len(result['rules']['failed'])<8:result['rules']['failed'].append(failed)
    met=[dict(id=item['id'],name_zh=item['name_zh'],value=len(item['value']) if isinstance(item['value'],list) else round_value(item['value']),
              limit=round_value(item['limit']),unit=item['unit']) for item in checked['items']
         if item.get('source_type')=='用户要求' and item.get('category') in ('requirement','economics') and item['status']=='pass']
    if met:result['rules']['met']=met  # each owner requirement with its value, so the agent and the reviewer can confirm it
    param_only=any(item['level']=='hard' and item['status']=='fail' and (item['suggestion'] or {}).get('op')=='set_param' for item in checked['items'])
    for item in checked['items']:
        op=item['suggestion']
        if item['level']!='hard' or item['status']!='fail' or op is None or op in result['suggestions']:continue
        if param_only and op.get('op')!='set_param':continue
        if len(result['suggestions'])==5:break
        result['suggestions'].append(op)
    return fit_summary(result)


def fit_summary(result, budget=1920):
    """Keep engineering facts/actions; only redundant display text may be omitted."""
    if len(serialized(result).encode('utf-8')) > budget:
        result['suggestions']=[_compact_removal(op) for op in result['suggestions']]
        if any('module_id_ranges' in op for op in result['suggestions']):
            result['suggestions_format']='module_id_ranges 的 a..b 为同前缀末尾数字区间（含端点），保留零填充；展开成 module_ids 后一次提交完整建议，勿将压缩字段传入 ops。'
    if len(serialized(result).encode('utf-8')) > budget:
        result['rules'].pop('met', None)  # passed requirements stay in rules.json
    if len(serialized(result).encode('utf-8')) > budget:
        for failed in result['rules']['failed']:
            failed.pop('hint_zh', None)
    if len(serialized(result).encode('utf-8')) > budget:
        for failed in result['rules']['failed']:
            failed.pop('name_zh', None)
    if len(serialized(result).encode('utf-8')) > budget:
        raise GzError('RESULT_TOO_LARGE','分析摘要无法无损压到2KB，未省略规则或修改建议','停止操作，检查分析摘要长度')
    return result


def _monthly_generation(energy):
    """Persist local-month totals from the same shaded AC series used by economics."""
    hourly = energy['hourly']
    months = [dict(month=month, ac_kwh=0.0) for month in range(1, 13)]
    for timestamp, value in zip(hourly['utc'], hourly['kwh'], strict=True):
        stamp = datetime.fromisoformat(timestamp).astimezone(timezone(timedelta(hours=8)))
        months[stamp.month - 1]['ac_kwh'] += value
    energy['monthly_kwh'] = months
    energy['monthly_basis'] = 'b链逐时交流发电，已按当前遮挡模型扣减；按北京时间汇总，不是实测发电'
    return energy


def generation(project,design,shadows,dc_kw,*,offline=False):
    design = next(orientation.views(design))[1] if len(orientation.groups(design)) == 1 else design
    if len(orientation.groups(design)) > 1 or project.roof.type == 'pitched' and design.modules:
        losses = {row['id']: row['total_loss_pct'] for row in shadows['modules']}
        energy, records, omitted = dict(p50=0.0, low=0.0, high=0.0), [], {}
        for identity, view, result in orientation.simulations(project, design, offline=offline):
            capacity = dc_kw * len(view.modules) / len(design.modules)
            multiplier = capacity * (1 - sum(losses[m.id] for m in view.modules) / len(view.modules) / 100)
            specific = {key: row['specific_yield_kwh_kwp'] for key, row in result['results'].items()}
            for name, value in dict(p50=specific['b'], low=min(specific.values()), high=max(specific.values())).items():
                energy[name] += value * multiplier
            hourly = result['results']['b']['hourly']
            total = energy.setdefault('hourly', dict(utc=hourly['utc'], kwh=[0.0] * len(hourly['kwh'])))
            if total['utc'] != hourly['utc']:
                raise ValueError('Orientation hourly timestamps differ')
            total['kwh'] = [a + b * multiplier for a, b in zip(total['kwh'], hourly['kwh'])]
            records.append(dict(group=identity, dc_kw=capacity, generation=result))
            if project.roof.type == 'pitched':
                energy.setdefault('planes', []).append(dict(id=identity[0], dc_kw=capacity,
                    p50=specific['b'] * multiplier, per_kw=specific['b'] * multiplier / capacity if capacity else 0,
                    shading_pct=100 * (1 - multiplier / capacity) if capacity else 0))
            omitted.update(result['omitted'])
        energy['per_kw'] = energy['p50'] / dc_kw if dc_kw else 0.0
        return _monthly_generation(energy), dict(groups=records, omitted=omitted)
    loss=economics.load_assumptions()['design_system_loss_pct']['value']
    p_lat = getattr(project.site, 'weather_proxy_lat', None)
    p_lon = getattr(project.site, 'weather_proxy_lon', None)
    proxy = (p_lat, p_lon) if p_lat is not None and p_lon is not None else None
    result=yieldsim.simulate_design_yields(
        project.site.lat,project.site.lon,tilt=design.params.tilt_deg,
        azimuth=design.params.azimuth_deg,loss_percent=loss,offline=offline,
        module_id=project.equipment.module_id,
        weather_proxy=proxy,weather_proxy_note=getattr(project.site, 'weather_proxy_note', None),
    )
    specific={key:value['specific_yield_kwh_kwp'] for key,value in result['results'].items()}
    multiplier=dc_kw*(1-shadows['summary']['avg_loss_pct']/100)
    energy=dict(p50=specific['b']*multiplier,low=min(specific.values())*multiplier,high=max(specific.values())*multiplier,
                per_kw=specific['b']*(1-shadows['summary']['avg_loss_pct']/100))
    hourly = result['results']['b']['hourly']
    energy['hourly'] = dict(utc=hourly['utc'], kwh=[value * multiplier for value in hourly['kwh']])
    return _monthly_generation(energy),result


def analyze(project_id,version,*,offline=False):
    started=time.perf_counter()
    with stage("analysis.load"):
        project,design=storage.load(project_id),storage.load_design(project_id,version)
    from .analysis_inputs import project_signature, write_completion, engine_inputs
    input_hash = project_signature(project)
    from .installation import effective
    project = effective(project, design)
    path=storage._path(project_id,f'analysis/v{version}/shading.json')
    design_hash=hashlib.sha256(storage._path(project_id,f'designs/v{version}.json').read_bytes()).hexdigest()
    shadow_bytes = path.read_bytes() if path.exists() else None
    shadows=json.loads(shadow_bytes) if shadow_bytes is not None else None
    shadow_metadata = shadows.get('metadata') if isinstance(shadows, dict) else None
    reused=bool(isinstance(shadow_metadata, dict) and shadows.get('version')==version
                and shadow_metadata.get('design_sha256')==design_hash and shadow_metadata.get('project_inputs_sha256')==input_hash)
    with stage("analysis.shading"):
        if not reused:
            shadows=shading.analyze(project_id,version,offline=offline)
            shadow_bytes = (json.dumps(shadows, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    with stage("analysis.electrical"):
        electric=electrical.calculate(project,design,offline=offline,shadows=shadows)
    with stage("analysis.structure"):
        load=structure.calculate(project,design)
    assumptions=economics.load_assumptions()
    with stage("analysis.yield"):
        energy,generated=generation(project,design,shadows,electric['dc_kw'],offline=offline)
    with stage("analysis.economics"):
        cash=economics.calculate(project,electric['dc_kw'],energy,design=design,electric=electric,load=load)
        if any(m.phase is not None for m in design.modules):
            from .personal import phase_cash
            phase_cash(project, design, shadows, cash, offline=offline)
    with stage("analysis.rules"):
        checked=rules.evaluate(project,design,shadows,electric,load,cash)
    summary=_summary(design,shadows,electric,load,cash,energy,checked,omitted=generated['omitted'])
    cash['generation'] = yieldsim.without_hourly(generated)
    cash['analysis_metadata']=dict(elapsed_seconds=time.perf_counter()-started,shading_reused=reused,design_sha256=design_hash,
                                   calculation_engine=engine_inputs(),
                                   project_inputs_sha256=input_hash, completion_required=True,
                                   system_loss_source=assumptions['design_system_loss_pct'],
                                   yield_kwh=yieldsim.without_hourly(energy),
                                   interval_note='五条链天气与模型差异范围，非统计概率置信区间；p50字段沿用旧名，是基准年估算（b链：NASA POWER 2023天气+CEC详细模型），不是概率P50')
    with stage("analysis.save"):
        output_hashes = {'shading.json': hashlib.sha256(shadow_bytes).hexdigest()}
        for name,result in [('electrical',electric),('structure',load),('economics',cash),('rules',checked)]:
            output_hashes[name + '.json'] = hashlib.sha256((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode('utf-8')).hexdigest()
            rules.save_result(project_id,version,name,result)
        path=storage._path(project_id,f'analysis/v{version}/summary.json')
        summary_text = serialized(summary) + '\n'
        path.write_text(summary_text,encoding='utf-8',newline='\n')
        output_hashes['summary.json'] = hashlib.sha256(summary_text.encode('utf-8')).hexdigest()
        write_completion(path.parent, version, design_hash, input_hash, expected_hashes=output_hashes)
    return summary


def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run']);parser.add_argument('--project',required=True)
    parser.add_argument('--version',required=True,type=int);parser.add_argument('--offline',action='store_true')
    args=parser.parse_args(argv)
    try:
        result=analyze(args.project,args.version,offline=args.offline)
        cash=json.loads(storage._path(args.project,f'analysis/v{args.version}/economics.json').read_text(encoding='utf-8'))
        economics.plot(cash,storage._path(args.project,f'analysis/v{args.version}/tornado.png'),storage._path(args.project,f'analysis/v{args.version}/cashflow.png'))
        print(serialized(result));return 0
    except GzError as error:
        print(serialized(error.as_dict()));return 1
    except (OSError,ValueError,RuntimeError) as error:
        print(serialized(GzError('ANALYSIS_FAILED','综合分析的数据或结果文件不正确','检查天气、设备、经济假设和项目版本').as_dict()));return 1


if __name__=='__main__':raise SystemExit(main())
