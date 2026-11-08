"""Current-version candidate reports, with no invented review or approval evidence."""
from datetime import datetime, timezone
import hashlib
from html import escape
import json

from ..electrical import load_catalog
from ..local_exports import export_evidence, _snapshot


def _verified_review(base, result):
    """Use the verified reviewer snapshot, never a loose local review filename."""
    proof = (result.get('verification') or {}).get('review', {})
    version = result['version']
    if (proof.get('passed') is not True or proof.get('mode') != 'independent'
            or version not in proof.get('versions', []) or not result.get('run_id')):
        return None
    try:
        run_root = (base.parent.parent / 'runs').resolve()
        run = (run_root / result['run_id']).resolve()
        if not run.is_relative_to(run_root):
            return None
        parent = json.loads((run / 'run.json').read_text(encoding='utf-8'))
        captured = (run / parent['review_capture']).resolve()
        if not captured.is_relative_to(run):
            return None
        metadata = json.loads((captured / 'run.json').read_text(encoding='utf-8'))
        if metadata.get('project_id') != result['project_id']:
            return None

        def original(relative):
            path = (captured / relative).resolve()
            if not path.is_relative_to(captured):
                return None
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != metadata.get('artifacts', {}).get(relative):
                return None
            return json.loads(raw)

        from ..analysis_inputs import project_signature
        archived_project = original('project/project.json')
        archived_design = original(f'project/designs/v{version}.json')
        if (not archived_project or archived_design != result['design']
                or project_signature(archived_project) != result['evidence']['analysis']['project_inputs_sha256']):
            return None
        rows = [original(path.relative_to(captured).as_posix()) for path in
                sorted((captured / 'project/reviews').glob(f'v{version}-*.json'))]
        return next((row for row in reversed(rows) if row and row.get('version') == version), None)
    except (OSError, ValueError, TypeError, KeyError):
        return None


def render_report(base, result):
    from . import view
    version = result['version']
    evidence = result.get('evidence', {})
    state = evidence.get('analysis', {})
    if (state.get('status') != 'recorded' or state.get('input_binding') != 'matched'
            or state.get('completion_status') != 'matched'):
        return ('<!doctype html><html lang="zh"><meta charset="utf-8"><title>方案待计算</title><body>'
                f'<h1>{escape(result["project"]["name"])} · v{version}</h1>'
                '<h2>候选方案需要重新计算</h2><p>当前设计、工程输入或完整计算记录缺失／不匹配。'
                '请重新计算此版本，再查看方案指标；尚未独立审核，也未批准导出。</p>'
                + ''.join(f'<p>{escape(str(note))}</p>' for note in state.get('notes', [])) + '</body></html>')

    def read(relative, default=None):
        path = base / relative
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default

    project, design = result['project'], result['design']
    review_proof = (result.get('verification') or {}).get('review', {})
    review = _verified_review(base, result)
    exported = export_evidence(base, version)
    local_approval = exported.get('approval') if exported['status'] == 'verified' else None
    if local_approval and local_approval.get('fingerprint') != _snapshot(base, version)[0]:
        local_approval = None
    module = load_catalog('modules.csv', include_extended=True).get(project['equipment']['module_id'], {})
    electric = result['scene'].get('electrical', {})
    inverter_id = electric.get('inverter_id') or project['equipment'].get('inverter_id')
    inverter = load_catalog('inverters.csv', include_extended=True).get(inverter_id, {})
    context = dict(project=project, project_id=result['project_id'], run_id=result.get('run_id') or '', version=version,
                   generated_at=datetime.now(timezone.utc).isoformat(), design=design, summary=result.get('summary') or {},
                   economics=result.get('economics') or {}, rules=result.get('rules') or {},
                   shading=result['scene'].get('shading') or {},
                   electrical=electric, structure=read(f'analysis/v{version}/structure.json', {}),
                   crosscheck=result.get('crosscheck'), compare=result.get('compare'), module=module, inverter=inverter,
                   versions=[read(f'designs/v{row["version"]}.json') for row in result.get('versions', [])],
                   facts=project.get('facts'), requirements=[project.get('requirements') or {'text': ''}],
                   sessions=[], sources=[], review=review, review_mode='independent' if review else 'none',
                   verification=dict(review=review_proof) if review else dict(passed=None, checks=[]),
                   local_workflow=True, local_approval=local_approval, evidence=evidence,
                   manifest=read(f'exports/v{version}/manifest.json', dict(version=version, files={})))
    content = view.render(context)
    toolbar = ('<style>@media print{.gz-report-toolbar{display:none}}.gz-report-toolbar{padding:12px;'
               'background:#173f35;color:white;position:sticky;top:0;z-index:9999}</style>'
               '<div class="gz-report-toolbar"><strong>光筑 · 初步方案报告</strong> · '
               f'{escape(project["name"])} · v{version} '
               '<button onclick="window.print()">打印 / 保存 PDF</button></div>')
    return content.replace('<body>', '<body>' + toolbar, 1)
