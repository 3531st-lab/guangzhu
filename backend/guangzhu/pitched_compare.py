"""Pitched candidates reuse final engineering checks and T17 recommendation rules."""
from . import analysis, layout, project as storage, rules, shading
from .models import GzError


def eligible(planes):
    productive = [p for p in planes if p['dc_kw'] > 0]
    best = max((p['per_kw'] for p in productive), default=0)
    return [p['id'] for p in productive if p['per_kw'] >= best * .95]


def compare(project_id, base, current, *, offline=False):
    from .mcp_actions import _read, _cache_shadows, _comparison_metric, recommend_options
    project = storage.load(project_id)
    active = project.model_copy(deep=True)
    active.roof.keepouts += base.added_keepouts
    site = shading.SiteShading(project, offline=offline)

    def metric(label, design, summary, checked):
        row = _comparison_metric(label, design, summary, checked)
        row.update(align='pitched', tilt_deg=None, planes=sorted({int(m.id.split('-')[0][1:]) for m in design.modules}))
        return row

    def candidate(label, ids):
        design = layout.generate_layout(active, base.params.model_dump() | dict(plane_ids=ids))
        design.version = storage.next_version(project_id)
        design.parent_version = base.version
        design.reason = '坡面三方案：' + label
        design.author = 'agent'
        design.added_keepouts = base.added_keepouts
        design.modules_per_string = base.modules_per_string
        reuse = shading.RemovalShading(project, design, site=site)
        shadows = reuse.analyze(design)
        storage.save_design(project_id, design, offline=offline, shadows=shadows)
        for _ in range(len(design.modules) + 8):
            _cache_shadows(project_id, design, reuse.analyze(design))
            summary = analysis.analyze(project_id, design.version, offline=offline)
            checked = _read(project_id, f'analysis/v{design.version}/rules.json')
            fix = next((r for code in ('G01', 'G03', 'U02', 'U03', 'U05', 'U06', 'S01', 'E08')
                        for r in checked['items'] if r['id'] == code and r['status'] == 'fail' and r['suggestion']), None)
            if fix is None:
                break
            before = design.model_dump(exclude={'created_at', 'version', 'parent_version', 'reason', 'author'})
            operation = fix['suggestion']
            changed = storage.edit_design(project_id, design.version, [operation], label + '：修正' + fix['id'], 'agent', offline=offline)
            design = storage.load_design(project_id, changed['version'])
            after = design.model_dump(exclude={'created_at', 'version', 'parent_version', 'reason', 'author'})
            if operation['op'] == 'set_param':
                reuse = shading.RemovalShading(project, design, site=site)
            if before == after:
                break
        _cache_shadows(project_id, design, reuse.analyze(design))
        summary = analysis.analyze(project_id, design.version, offline=offline)
        checked = _read(project_id, f'analysis/v{design.version}/rules.json')
        return metric(label, design, summary, checked)

    current.update(align='pitched', tilt_deg=None, planes=sorted({int(m.id.split('-')[0][1:]) for m in base.modules}))
    all_faces = candidate('多装', None)
    cash = _read(project_id, f"analysis/v{all_faces['version']}/economics.json")
    selected = eligible(cash['analysis_metadata']['yield_kwh'].get('planes', []))
    if not selected:
        raise GzError('NO_INSTALLABLE_PLANE', '修正后没有可比较的装机坡面', '检查坡面大小、玻璃、避让和硬性规则')
    initial_version = all_faces['version']
    attempts = 0
    while True:
        fastest = candidate('最快回本', selected)
        attempts += 1
        cash = _read(project_id, f"analysis/v{fastest['version']}/economics.json")
        final = eligible(cash['analysis_metadata']['yield_kwh'].get('planes', []))
        if not final:
            raise GzError('NO_INSTALLABLE_PLANE', '最快回本修正后没有装机坡面', '检查最小组串、预算和其他硬性规则')
        if set(final) == set(selected):
            break
        # Only installed faces are re-evaluated. Each repeat removes a face, so it terminates.
        selected = final
    recommended = recommend_options(current, [all_faces, fastest])
    balanced_version = recommended['balanced']['version']
    chosen = next(row for row in (current, all_faces, fastest) if row['version'] == balanced_version)
    balanced = dict(chosen, name='折中')
    result = dict(ok=True, base_version=base.version, current=current, options=[all_faces, fastest, balanced],
                  recommended=recommended, plane_selection=dict(threshold_pct=95, selected=selected,
                      initial_basis_version=initial_version, basis_version=fastest['version'], attempts=attempts),
                  capacity_note='坡面顺坡平铺；最快回本候选按每千瓦净年发电≥最好面95%示意筛选；指标为规则修正后的实算值。')
    if len(analysis.serialized(result).encode('utf-8')) > 1920:
        raise GzError('RESULT_TOO_LARGE', '坡面比较摘要超过2KB', '检查坡面数量和完整比较结果')
    rules.save_result(project_id, base.version, 'compare', result)
    return result
