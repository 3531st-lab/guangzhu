"""Read-only, version-specific facts for an engineering demonstration.

Presence, input binding, file integrity and independent approval are distinct.
This packet deliberately never infers an Agent success rate or a human cost.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .analysis_inputs import ANALYSIS_FILES, project_signature
from .models import GzError


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def _record(value):
    return value if isinstance(value, dict) else {}


def _rows(value):
    return value if isinstance(value, list) else []


def _elapsed(start, end):
    try:
        first, last = (datetime.fromisoformat(value.replace('Z', '+00:00')) for value in (start, end))
        return _number((last - first).total_seconds()) if first.tzinfo and last.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def _usage(records, error):
    sessions = []
    for key, value in sorted(_record(records).items()):
        if not isinstance(value, dict) or value.get('session_id') != key:
            continue
        sessions.append(dict(session_id=key, model_requests=_number(value.get('model_requests')),
            elapsed_seconds=_elapsed(value.get('started_at'), value.get('ended_at')),
            tokens={field: _number(_record(value.get('tokens')).get(field))
                    for field in ('input', 'output', 'cacheRead', 'cacheWrite', 'reasoning')},
            costs=[dict(currency=row['currency'], micros=row['micros']) for row in _rows(value.get('costs'))
                   if isinstance(row, dict) and isinstance(row.get('currency'), str) and _number(row.get('micros')) is not None],
            billing_complete=value.get('billing_complete') is True,
            missing_costs=_number(value.get('missing_costs'))))
    return dict(sessions=sessions, manual_minutes=None, failure_count=None, retry_count=None,
                note='用量来自关联的原生会话，可能覆盖多个版本；会话时长不是纯模型耗时，也不是人工工时。缺失费用不按零处理。',
                error=error)


def capture(base, version, *, archive_hashes=None, usage_by_session=None, usage_error=None, additional_reviews=()):
    """Capture fixed files under one project, never mutate or follow manifest escapes."""
    if type(version) is not int or version < 1:
        return dict(schema='guangzhu.design-evidence/1', available=False, reason='尚无可核对的设计版本。')
    base = Path(base).resolve()
    sources = []

    def source(relative, *, kind='record', expected=None, source_base=base, source_hashes=archive_hashes, prefix=''):
        path = source_base / relative
        row = dict(path=prefix + relative, kind=kind, integrity='missing', sha256=None, bytes=None)
        try:
            path.resolve().relative_to(source_base.resolve())
            if not path.is_file():
                sources.append(row)
                return None
            raw = path.read_bytes()
        except (ValueError, OSError):
            row['integrity'] = 'invalid'
            sources.append(row)
            return None
        digest = hashlib.sha256(raw).hexdigest()
        row.update(sha256=digest, bytes=len(raw), integrity='recorded')
        if source_hashes is not None:
            claimed = _record(source_hashes).get('project/' + relative)
            row['integrity'] = 'unverified' if claimed is None else 'verified' if claimed == digest else 'mismatch'
        if expected is not None:
            row['manifest_match'] = expected == digest
            if expected != digest and source_hashes is None:
                row['integrity'] = 'mismatch'
        sources.append(row)
        if row['integrity'] not in ('recorded', 'verified'):
            return None
        if kind == 'output':
            return row
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            row['integrity'] = 'invalid'
            return None
        if not isinstance(value, dict):
            row['integrity'] = 'invalid'
            return None
        return value

    project = source('project.json') or {}
    design_path = f'designs/v{version}.json'
    design = source(design_path) or {}
    analyses = {name: source(f'analysis/v{version}/{name}.json')
                for name in ('summary', 'shading', 'electrical', 'structure', 'economics', 'rules')}
    completion = source(f'analysis/v{version}/completion.json')
    reviews, seen_reviews = [], set()
    locations = [dict(base=base, hashes=archive_hashes, prefix=''), *additional_reviews]
    for location in locations:
        review_base = Path(location['base']).resolve()
        for path in sorted((review_base / 'reviews').glob(f'v{version}-*.json')):
            relative = path.relative_to(review_base).as_posix()
            review = source(relative, source_base=review_base, source_hashes=location.get('hashes', {}),
                            prefix=location.get('prefix', 'review-archive/'))
            if review and review.get('version') == version:
                identity = json.dumps(review, sort_keys=True, ensure_ascii=False)
                if identity not in seen_reviews:
                    seen_reviews.add(identity)
                    reviews.append({key: review.get(key) for key in ('version', 'verdict', 'reviewer_model', 'created_at')} |
                                   dict(source=location.get('prefix', '') + relative))

    manifest = source(f'exports/v{version}/manifest.json')
    export = dict(status='missing', count=0,
                  note='文件摘要一致仅证明文件与清单相符；导出批准和独立审核须另看原生执行记录。')
    if manifest:
        files = manifest.get('files')
        if manifest.get('version') != version or not isinstance(files, dict) or not files:
            export['status'] = 'invalid'
        else:
            export['status'] = 'matched'
            sanitized = archive_hashes is not None and bool(manifest.get('snapshot_note'))
            for name, digest in files.items():
                relative = Path(name)
                if (relative.is_absolute() or relative.drive or '..' in relative.parts
                        or not isinstance(digest, str) or len(digest) != 64
                        or any(c not in '0123456789abcdef' for c in digest)):
                    export['status'] = 'invalid'
                    continue
                row = source(f'exports/v{version}/{relative.as_posix()}', kind='output', expected=digest)
                export['count'] += 1
                if row is None and export['status'] != 'invalid':
                    export['status'] = 'mismatch'
                elif row is not None and row.get('manifest_match') is False and export['status'] not in ('invalid', 'mismatch'):
                    export['status'] = 'snapshot' if sanitized else 'mismatch'
            if export['status'] == 'snapshot':
                export['note'] = '这是已核验的脱敏归档快照；清单保留原始导出摘要，当前快照不能证明原件摘要一致。'

    design_digest = next((row['sha256'] for row in sources if row['path'] == design_path), None)
    try:
        input_digest = project_signature(project)
    except (ValueError, TypeError, GzError):
        input_digest = None
    mismatched_version = design.get('version') != version or any(
        row is not None and row.get('version', version) != version for row in analyses.values())
    binding, notes = 'unrecorded', []
    metadata = [_record(_record(analyses.get('shading')).get('metadata')),
                _record(_record(analyses.get('economics')).get('analysis_metadata'))]
    if any(row.get('design_sha256') and row['design_sha256'] != design_digest for row in metadata):
        binding = 'mismatch'
        notes.append('计算记录的组件几何摘要与当前设计文件不符。')
    if any(row.get('project_inputs_sha256') and row['project_inputs_sha256'] != input_digest for row in metadata):
        binding = 'mismatch'
        notes.append('项目工程输入已经变化，记录需要重新计算。')
    elif binding != 'mismatch' and all(row.get('project_inputs_sha256') == input_digest and
            row.get('design_sha256') == design_digest for row in metadata) and input_digest and design_digest:
        binding = 'matched'
    if binding == 'unrecorded':
        notes.append('历史记录未完整保存输入签名，无法证明其与当前输入完全一致。')
    completed = 'unrecorded'
    if completion is not None:
        actual = {row['path'].rsplit('/', 1)[-1]: row for row in sources
                  if row['path'].startswith(f'analysis/v{version}/') and row['path'].rsplit('/', 1)[-1] in ANALYSIS_FILES}
        declared = _record(completion.get('files'))
        complete = (completion.get('schema') == 'guangzhu.analysis-completion/1' and type(completion.get('version')) is int
                    and completion['version'] == version and completion.get('design_sha256') == design_digest
                    and completion.get('project_inputs_sha256') == input_digest and bool(input_digest) and bool(design_digest)
                    and set(declared) == set(ANALYSIS_FILES)
                    and all(actual[name]['integrity'] in ('recorded', 'verified')
                            and declared[name] == actual[name]['sha256'] for name in ANALYSIS_FILES))
        completed = 'matched' if complete else 'mismatch'
    elif any(row['path'] == f'analysis/v{version}/completion.json' and row['integrity'] != 'missing' for row in sources):
        completed = 'mismatch'
    elif metadata[1].get('completion_required') is True:
        completed = 'mismatch'
    if completed == 'mismatch':
        notes.append('综合计算完成清单与文件不一致，可能有中断写入或事后变更；请重新计算。')
    elif completed == 'unrecorded':
        notes.append('旧记录没有整套计算的完成清单，单份签名不能证明全部输出来自同一次完成的计算。')
    missing = [name for name, value in analyses.items() if value is None]
    stale = mismatched_version or binding == 'mismatch' or completed == 'mismatch'
    if mismatched_version:
        notes.append('记录中的版本号与所查看版本不一致。')
    status = 'stale' if stale else 'missing' if len(missing) == len(analyses) else 'partial' if missing else 'recorded'
    rule_data = analyses.get('rules') or {}
    items = rule_data.get('items')
    usable_rules = isinstance(items, list) and all(isinstance(row, dict) for row in items)
    applicable = [row for row in items if row.get('status') in ('pass', 'fail')] if usable_rules else []
    failed = [row for row in applicable if row.get('status') == 'fail' and row.get('level') == 'hard']
    hard_applicable = [row for row in applicable if row.get('level') == 'hard']
    unknown = [row for row in items if row.get('level') not in ('hard', 'advice') or
               row.get('status') not in ('pass', 'fail', 'na')] if usable_rules else []
    rule_status = ('stale' if stale else 'missing' if not usable_rules else 'fail' if failed
                   else 'unknown' if unknown or not hard_applicable else 'pass')
    roof = _record(project.get('roof'))
    weather = _record(metadata[0].get('weather'))
    return dict(schema='guangzhu.design-evidence/1', available=bool(design), project_id=project.get('id'), version=version,
        captured_at=datetime.now(timezone.utc).isoformat(),
        model=dict(modules=len(design['modules']) if isinstance(design.get('modules'), list) else None,
                   parent_version=design.get('parent_version'), reason=design.get('reason'),
                   created_at=design.get('created_at'), manual_edits=_record(design.get('statistics')).get('manual_edits') is True),
        assumptions=dict(name=project.get('name'), roof_type=roof.get('type'), site=project.get('site'),
                         load_capacity_kn_m2=roof.get('load_capacity_kn_m2'), load_verified=roof.get('load_verified') is True,
                         plane_loads=[dict(id=p.get('id'), capacity_kn_m2=p.get('load_capacity_kn_m2'),
                                           verified=p.get('load_verified')) for p in _rows(roof.get('planes')) if isinstance(p, dict)],
                         equipment=project.get('equipment'), requirements=project.get('requirements'),
                         economics_note=_record(project.get('economics')).get('assumptions_note')),
        analysis=dict(status=status, input_binding=binding, missing=missing, notes=notes,
                      completion_status=completed,
                      elapsed_seconds=_number(metadata[1].get('elapsed_seconds')) if not stale else None,
                      project_inputs_sha256=input_digest, design_sha256=design_digest),
        rules=dict(status=rule_status, hard_failed=len(failed) if usable_rules and not stale and (failed or not unknown and hard_applicable) else None,
                   unknown_count=len(unknown) if usable_rules and not stale else None,
                   applicable=len(applicable) if usable_rules and not stale else None,
                   failed_ids=[row.get('id') for row in failed] if not stale else []),
        weather={key: weather.get(key) for key in ('source', 'source_description', 'year', 'used', 'data_file_sha256')},
        review=dict(status='recorded' if reviews else 'missing', count=len(reviews), records=reviews,
                    note='此处列出同版本审核文件；是否由独立会话完成，以原生执行记录核对为准。'),
        export=export, sources=sources, usage=_usage(usage_by_session, usage_error),
        note='此卡记录当前版本的可复查事实，不代表施工批准、参赛资格、获奖概率或新的智能体评测成绩。')
