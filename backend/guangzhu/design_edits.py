"""Local, preview-first design editing; candidate calculations never save a design."""
import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from . import project as storage
from .models import Design, GzError, Record

router = APIRouter()
_commit_lock = threading.Lock()


class EditRequest(Record):
    version: int = Field(gt=0, strict=True)
    ops: list[dict] = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=1, max_length=1000)
    detailed: bool = False


class ApplyRequest(EditRequest):
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')


def calculate_impact(project, design, *, geometry_sky=False):
    """Use the production calculation chain in memory, with existing weather only."""
    from . import analysis, shading, electrical, structure, economics, rules
    from .installation import effective
    project = effective(project, design)
    shadow_design = design
    if geometry_sky and not (design.statistics.get('manual_edits') or design.statistics.get('geometry_sky')):
        shadow_design = design.model_copy(deep=True)
        shadow_design.statistics['geometry_sky'] = True
    shadows = shading.analyze_design(project, shadow_design, offline=True)
    electric = electrical.calculate(project, design, offline=True, shadows=shadows)
    load = structure.calculate(project, design)
    energy, generated = analysis.generation(project, design, shadows, electric['dc_kw'], offline=True)
    cash = economics.calculate(project, electric['dc_kw'], energy, design=design, electric=electric, load=load)
    if any(m.phase is not None for m in design.modules):
        from .personal import phase_cash
        phase_cash(project, design, shadows, cash, offline=True)
    checked = rules.evaluate(project, design, shadows, electric, load, cash)
    positions = {module.id: module.corners for module in design.modules}
    cables = {row['id']: row for row in electric.get('cables', {}).get('dc', [])}
    return dict(modules=len(design.modules), dc_kw=electric['dc_kw'], annual_kwh=energy['p50'],
                capex_cny=cash['capex_cny'], payback_years=cash['payback_years'],
                hard_failed=checked['hard_failed'],
                failed=[{k: row.get(k) for k in ('id', 'name_zh', 'level', 'value', 'limit', 'plane', 'evidence', 'hint_zh', 'note')}
                        for row in checked['items'] if row['status'] == 'fail'],
                strings=[dict(row, module_geometry=[positions[mid] for mid in row['module_ids']],
                              cable=cables.get(row['id'])) for row in electric['strings']],
                shading={key: shadows['summary'][key] for key in ('avg_loss_pct', 'max_loss_pct', 'modules_over_threshold')},
                module_shading=shadows['modules'],
                omitted=generated.get('omitted', {}))


def _reply(action):
    from .api import public
    try:
        return public(action())
    except GzError as error:
        status = 409 if error.error_code == 'DESIGN_PREVIEW_STALE' else 422
        return JSONResponse(dict(error_code=error.error_code,
                                 errors=[f'{error.message_zh}。{error.fix_hint}']), status_code=status)


def preview(project_id, payload):
    result = storage.preview_edit(project_id, payload.version, payload.ops, payload.reason, 'user', offline=True)
    candidate = result['design']
    if isinstance(candidate, dict):
        candidate = Design.model_validate(candidate)
    result['design'] = candidate.model_dump(mode='json')
    result['impact'] = dict(available=False, reason='尚未复算发电、造价、回本和组串。')
    if payload.detailed:
        try:
            project = storage.load(project_id)
            original = storage.load_design(project_id, payload.version)
            # Compare both candidates with the same sky-visibility method. A
            # geometry edit must not make a change of approximation look like
            # a physical consequence of the moved module.
            geometric = candidate.statistics.get('manual_edits') or candidate.statistics.get('geometry_sky')
            before = calculate_impact(project, original, geometry_sky=True) if geometric else calculate_impact(project, original)
            after = calculate_impact(project, candidate)
            old = {row['id']: row for row in before.pop('strings')}
            new = {row['id']: row for row in after.pop('strings')}
            old_shading = {row['id']: row['total_loss_pct'] for row in before.pop('module_shading', [])}
            new_shading = {row['id']: row['total_loss_pct'] for row in after.pop('module_shading', [])}
            shade_changes = [dict(id=key, before_loss_pct=old_shading.get(key), after_loss_pct=new_shading.get(key),
                                  delta_loss_pct=new_shading[key] - old_shading[key] if key in old_shading and key in new_shading else None)
                             for key in sorted(old_shading.keys() | new_shading.keys())
                             if key not in old_shading or key not in new_shading or abs(new_shading[key] - old_shading[key]) > 1e-7]
            result['impact'] = dict(available=True, before=before, after=after,
                                   affected_strings=sorted(key for key in old.keys() | new.keys()
                                                           if old.get(key) != new.get(key)),
                                   shading_changes=shade_changes,
                                   note='使用现有天气与同一项目假设复算；属于初步方案估算。' +
                                   ('修改前后均使用实际几何的等亮天空近似。' if geometric else ''))
        except (GzError, ValueError, OSError) as error:
            reason = error.message_zh if isinstance(error, GzError) else str(error)
            result['impact'] = dict(available=False, reason=f'复算未完成：{reason}')
    return result


@router.post('/api/projects/{project_id}/design-edits/preview')
def preview_endpoint(project_id: str, request: Request, payload: EditRequest):
    from .api import local_only
    local_only(request)
    return _reply(lambda: preview(project_id, payload))


@router.post('/api/projects/{project_id}/design-edits/apply')
def apply_endpoint(project_id: str, request: Request, payload: ApplyRequest):
    from .api import local_only
    local_only(request)

    def apply():
        with _commit_lock:
            result = storage.edit_design(project_id, payload.version, payload.ops, payload.reason, 'user',
                                         offline=True, expected_fingerprint=payload.fingerprint)
        result['analysis_complete'] = False
        if payload.detailed:
            from .analysis import analyze
            try:
                result['analysis'] = analyze(project_id, result['version'], offline=True)
                result['analysis_complete'] = True
            except (GzError, ValueError, OSError) as error:
                # The version is already saved. Report this explicitly so a retry cannot duplicate the edit.
                result['analysis_error'] = error.message_zh if isinstance(error, GzError) else str(error)
        return result

    return _reply(apply)
