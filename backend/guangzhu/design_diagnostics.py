"""Locate saved rule failures using evidence from exactly the displayed design version."""
import math
import re


SCHEMA = 'guangzhu.design-diagnostics/1'
SOURCE_NAMES = dict(rules='规则', shading='遮挡', electrical='电气', structure='结构')


def record(value):
    return value.model_dump(mode='json') if hasattr(value, 'model_dump') else value if isinstance(value, dict) else {}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def source(name, value, version, source_versions):
    """Unversioned legacy rules/load files require the caller's exact vN path proof."""
    data = record(value)
    if not data:
        return None, None, f'此版本缺少{SOURCE_NAMES[name]}分析。'
    declared = [data['version']] if 'version' in data else []
    if name == 'structure' and isinstance(data.get('wind'), dict) and 'version' in data['wind']:
        declared.append(data['wind']['version'])
    path_version = source_versions.get(name) if name in ('rules', 'structure') else None
    proof = [*declared, *([path_version] if path_version is not None else [])]
    observed = declared[0] if declared else path_version
    if not proof:
        return None, None, f'{SOURCE_NAMES[name]}分析缺少可核对的版本来源。'
    if any(type(number) is not int or number != version for number in proof):
        return None, observed, f'{SOURCE_NAMES[name]}分析与当前 v{version} 不一致，未用于定位。'
    return data, version, ''


def ids(values, available):
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        return None
    if len(set(values)) != len(values) or not set(values) <= available:
        return None
    return values


def indexed(rows, key='id'):
    if not isinstance(rows, list) or any(not isinstance(row, dict) or key not in row for row in rows):
        return None
    identifiers = [row[key] for row in rows]
    if any(not isinstance(value, (str, int)) or isinstance(value, bool) for value in identifiers):
        return None
    if len(set(identifiers)) != len(identifiers):
        return None
    return {row[key]: row for row in rows}


def panel_geometry(module):
    corners = module.get('corners')
    return (isinstance(corners, (list, tuple)) and len(corners) == 4
            and all(isinstance(point, (list, tuple)) and len(point) == 3 and all(finite(v) for v in point)
                    for point in corners))


def shade_issue(issue, data, modules, locked, version):
    rows = indexed(data.get('modules'))
    limit = issue['limit']
    if rows is None or set(rows) != modules or not finite(limit) or any(not finite(row.get('total_loss_pct')) for row in rows.values()):
        return '逐板遮挡证据或规则阈值不完整，无法可靠定位全部超阈值组件。'
    selected = [row for row in rows.values() if row['total_loss_pct'] > limit]
    if not selected:
        return '此版本逐板遮挡记录未发现与失败规则对应的超阈值组件。'
    issue['module_ids'] = sorted(row['id'] for row in selected)
    issue['details'] = [dict(id=row['id'], total_loss_pct=row['total_loss_pct'],
                             main_cause=row.get('main_cause')) for row in selected]
    editable = sorted(set(issue['module_ids']) - locked)
    protected = sorted(set(issue['module_ids']) & locked)
    if editable:
        issue['fix'] = dict(label=f'预览移除 {len(editable)} 块未锁定超阈值组件',
            ops=[dict(op='remove_modules', module_ids=editable)],
            reason=f'依据 v{version} 的 S01 逐板遮挡结果，预览移除未锁定的超阈值组件',
            retained_locked_ids=protected,
            note=f'仍保留 {len(protected)} 块已锁定超阈值组件；需重新校核装机、电气、遮挡和收益，不保证全部规则通过。')
    else:
        issue['fix_unavailable_reason'] = '超阈值组件全部已锁定；不会自动解锁或移除。'
    return ''


def unused_issue(issue, data, modules):
    selected = ids(data.get('unused_modules'), modules)
    strings = indexed(data.get('strings'))
    if selected is None or strings is None or not selected:
        return '此版本缺少完整且有效的未接线组件清单。'
    connected = set()
    for row in strings.values():
        members = ids(row.get('module_ids'), modules)
        if members is None:
            return '组串成员证据不完整，无法核对未接线组件。'
        if connected.intersection(members):
            return '同一组件出现在多个组串中，无法可靠核对未接线清单。'
        connected.update(members)
    if set(selected) & connected or set(selected) | connected != modules:
        return '未接线清单与本版本组串成员不一致，未用于定位。'
    if finite(issue['value']) and issue['value'] != len(selected):
        return '规则中的未接线数量与组件清单不一致，未用于定位。'
    issue['module_ids'] = sorted(selected)
    return ''


def cable_issue(issue, data, modules):
    cables = record(data.get('cables'))
    rows, strings = indexed(cables.get('dc')), indexed(data.get('strings'))
    if rows is None or strings is None:
        return '此版本缺少完整的直流线路及组串成员证据。'
    failed = [row for row in rows.values() if row.get('feasible') is False]
    if not failed:
        return '此版本没有明确标为失败的直流线路，不能仅凭最大压降猜测故障位置。'
    selected = set()
    for row in failed:
        members = ids(strings.get(row['id'], {}).get('module_ids'), modules)
        if not members:
            return '失败线路无法对应到本版本的完整组串成员。'
        selected.update(members)
    issue['module_ids'] = sorted(selected)
    issue['string_ids'] = sorted(row['id'] for row in failed)
    issue['details'] = [dict(id=row['id'], drop_pct=row.get('drop_pct'),
                             routing_status=row.get('routing_status'), feasible=False) for row in failed]
    return ''


def load_issue(issue, data, project, design, modules):
    plane = issue.get('plane')
    roof = record(design.get('installation_roof')) or record(project.get('roof'))
    planes, loads = indexed(roof.get('planes')), indexed(data.get('planes'))
    if type(plane) is not int or planes is None or plane not in planes:
        return '该荷载结论没有可核对的具体坡面，暂不定位到单块组件或结构连接点。'
    if loads is None or plane not in loads or loads[plane].get('status') != 'fail':
        return '此版本缺少与该规则一致的坡面荷载失败记录。'
    selected = sorted(mid for mid in modules if re.match(rf'^P{plane}-', mid))
    if not selected:
        return '当前设计中没有该失败坡面的组件，无法建立可靠定位。'
    row = loads[plane]
    issue.update(module_ids=selected, plane_ids=[plane], details=[dict(id=plane,
        added_kn_m2=row.get('added_kn_m2'), capacity_kn_m2=row.get('capacity_kn_m2'),
        worst_zone=row.get('worst_zone'), verified=row.get('verified'))])
    issue['location_note'] = '定位表示该坡面承担这些组件；整面荷载结论不能证明某个锚点失效，仍须结构专业复核。'
    return ''


def build(project, design, rules=None, shading=None, electrical=None, structure=None, locked_ids=(), *, source_versions=None):
    """Return read-only diagnostics and an optional preview operation, never save or recalculate."""
    project, design = record(project), record(design)
    version = design.get('version')
    result = dict(schema=SCHEMA, version=version, available=False, reason='', source_versions={}, issues=[])
    if type(version) is not int or version < 1:
        result['reason'] = '未提供完整设计版本，无法关联分析。'
        return result
    module_rows = indexed(design.get('modules'))
    if module_rows is None or any(not isinstance(mid, str) or not panel_geometry(row) for mid, row in module_rows.items()):
        result['reason'] = '此设计缺少完整组件几何，无法可靠定位。'
        return result
    modules = set(module_rows)
    locked = {mid for mid in locked_ids if isinstance(mid, str)} & modules
    # Direct IDs and plane locks are also visible in lean public records. Region
    # membership is supplied by the caller's authoritative design_locks.locked_ids.
    locked.update(set(design.get('locked_module_ids', [])) & modules)
    locked_planes = set(design.get('locked_plane_ids', []))
    locked.update(mid for mid in modules if (match := re.match(r'^P(\d+)-', mid)) and int(match[1]) in locked_planes)
    loaded, reasons = {}, {}
    for name, value in dict(rules=rules, shading=shading, electrical=electrical, structure=structure).items():
        loaded[name], result['source_versions'][name], reasons[name] = source(name, value, version, source_versions or {})
    current_rules = loaded['rules']
    if current_rules is None:
        result['reason'] = reasons['rules']
        return result
    rows = current_rules.get('items')
    if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get('id'), str)
                                        or not row['id'] or row.get('status') not in ('pass', 'fail', 'na') for row in rows):
        result['reason'] = '当前版本规则明细不完整。'
        return result
    result['available'] = True
    for index, rule in enumerate(rows):
        if rule.get('status') != 'fail':
            continue
        identifier = rule.get('id', '')
        issue = dict(key=f'{identifier}:{index}', rule_id=identifier, title=rule.get('name_zh', identifier),
                     level=rule.get('level', 'advice'), status='fail', value=rule.get('value'),
                     limit=rule.get('limit'), unit=rule.get('unit', ''), evidence=rule.get('evidence', ''),
                     hint=rule.get('hint_zh', ''), source_ref=rule.get('source_ref', ''),
                     plane=rule.get('plane'), located=False, location_reason='', location_note='',
                     module_ids=[], plane_ids=[], string_ids=[], locked_module_ids=[], details=[], fix=None,
                     fix_unavailable_reason='')
        name = {'S01': 'shading', 'E08': 'electrical', 'E10': 'electrical', 'L01': 'structure'}.get(identifier)
        if name is None:
            issue['location_reason'] = '本规则尚无可核对的对象定位；请结合数值、依据和建议处理。'
        elif loaded[name] is None:
            issue['location_reason'] = reasons[name]
        elif identifier == 'S01':
            issue['location_reason'] = shade_issue(issue, loaded[name], modules, locked, version)
        elif identifier == 'E08':
            issue['location_reason'] = unused_issue(issue, loaded[name], modules)
        elif identifier == 'E10':
            issue['location_reason'] = cable_issue(issue, loaded[name], modules)
        else:
            issue['location_reason'] = load_issue(issue, loaded[name], project, design, modules)
        issue['located'] = bool(issue['module_ids'] or issue['plane_ids'] or issue['string_ids']) and not issue['location_reason']
        issue['locked_module_ids'] = sorted(set(issue['module_ids']) & locked)
        result['issues'].append(issue)
    if not result['issues']:
        result['reason'] = '此版本规则清单没有未通过项；不代表已完成独立审核或批准交付。'
    return result
