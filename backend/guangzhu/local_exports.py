"""Explicit local approval for one immutable, version-bound preliminary export.

This is a user's approval to create files, not an independent engineering review.
AGH keeps its own approval/verification path. Reading or downloading never exports.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator

from . import analysis, mcp_actions, project as storage
from .analysis_inputs import ANALYSIS_FILES
from .design_evidence import capture
from .models import GzError, Record
from .park_store import transaction

router = APIRouter()
NOTICE = '这是初步方案文件导出；规则预检查不能代替独立工程审核、现场核定或施工批准。'


def _review_status(base, version):
    """Return local review status; loose files in reviews/ are never promoted to verified independent review."""
    reviews_dir = Path(base) / 'reviews'
    has_local_rule = False
    has_loose_review = False
    if reviews_dir.is_dir():
        for path in sorted(reviews_dir.glob(f'v{version}-*.json'), reverse=True):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if data.get('version') != version:
                    continue
                model_name = str(data.get('reviewer_model') or '')
                is_local = (
                    data.get('review_kind') == 'local_rule'
                    or path.name.endswith('-local-rule-engine.json')
                    or model_name.startswith('local-rule-engine')
                )
                if is_local:
                    has_local_rule = True
                else:
                    has_loose_review = True
            except (OSError, ValueError, KeyError):
                continue
    if has_loose_review:
        return dict(status='unverified', reason='已记录本地审核文件，但未绑定独立会话执行账本，不作为已核验独立审核')
    if has_local_rule:
        return dict(status='unverified', reason='已记录本机规则复核；本地导出不证明已完成独立模型工程审核')
    return dict(status='unverified', reason='本地导出不证明已完成独立工程审核')


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.approval-', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            json.dump(value, output, ensure_ascii=False, sort_keys=True, allow_nan=False)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def export_evidence(base, version):
    """Validate package hashes and a local approval receipt without global roots."""
    base = Path(base).resolve()
    result = dict(status='missing', version=version, files={}, approval=None, manifest_sha256=None,
                  reason='尚无已生成的导出包；请先预览并批准导出。')
    if type(version) is not int or version < 1:
        return result
    directory = (base / f'exports/v{version}').resolve()
    if not directory.is_relative_to(base):
        return result | dict(status='invalid', reason='导出目录超出项目范围。')
    manifest_path = directory / 'manifest.json'
    if not manifest_path.is_file():
        return result
    try:
        manifest = _read(manifest_path)
        files = manifest.get('files')
        required = {'design.json', 'summary.json', 'rules.json', 'economics.json'}
        full = required | {f'layout-v{version}.dxf', f'bom-v{version}.xlsx'}
        if manifest.get('version') != version or not isinstance(files, dict) or set(files) not in (required, full):
            raise ValueError('导出清单版本或文件集合不完整')
        for name, digest in files.items():
            target = (directory / name).resolve()
            if not target.is_relative_to(directory) or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
                raise ValueError('导出文件路径或摘要不正确')
            if _digest(target) != digest:
                raise ValueError('导出文件与清单摘要不符')
        result.update(status='unverified', files=files, manifest_sha256=_digest(manifest_path),
                      reason='文件摘要一致；本地未记录单次批准，AGH 批准须另看原生执行证据。')
        receipt_path = directory / 'approval.json'
        if receipt_path.is_file():
            receipt = _read(receipt_path)
            identifier = receipt.get('approval_id', '')
            if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
                raise ValueError('批准编号不正确')
            ticket_path = (base / f'approvals/export-{identifier}.json').resolve()
            if not ticket_path.is_relative_to(base):
                raise ValueError('批准记录路径不正确')
            ticket = _read(ticket_path)
            if (receipt.get('kind') != 'local-user' or receipt.get('status') != 'approved-once'
                    or receipt.get('version') != version or receipt.get('manifest_sha256') != result['manifest_sha256']
                    or ticket.get('status') != 'consumed' or ticket.get('version') != version
                    or ticket.get('receipt_sha256') != _digest(receipt_path)
                    or ticket.get('fingerprint') != receipt.get('fingerprint')):
                raise ValueError('批准回执与此版本导出包不匹配')
            result.update(status='verified', approval=receipt, reason='本地用户已明确批准此版本的一次初步方案导出。')
        return result
    except (OSError, ValueError, TypeError, KeyError) as error:
        return result | dict(status='invalid', approval=None, reason=f'导出包核验失败：{error}')


def _snapshot(base, version):
    evidence = capture(base, version)
    state = evidence.get('analysis', {})
    if (state.get('status') != 'recorded' or state.get('input_binding') != 'matched'
            or state.get('completion_status') != 'matched'):
        raise GzError('LOCAL_EXPORT_STALE', '设计、工程输入或完整计算记录需要重新计算', '重新预览导出后再批准')
    checked = evidence.get('rules', {})
    values = dict(version=version, design_sha256=state['design_sha256'],
                  project_inputs_sha256=state['project_inputs_sha256'],
                  files={name: _digest(Path(base) / f'analysis/v{version}/{name}') for name in ANALYSIS_FILES})
    fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return fingerprint, values, evidence, checked


def _existing_matches(base, version):
    existing = export_evidence(base, version)
    if existing['status'] == 'missing':
        return
    if existing['status'] == 'invalid':
        raise GzError('EXPORT_INVALID', existing['reason'], '保留原文件，创建新方案版本再导出')
    if not {f'layout-v{version}.dxf', f'bom-v{version}.xlsx'} <= set(existing['files']):
        raise GzError('EXPORT_VERSION_CHANGED', '此版本是仅含计算 JSON 的历史导出包；不能覆盖补写 CAD 或材料表',
                      '保留历史包，创建新方案版本并计算后再预览导出')
    sources = dict(design=f'designs/v{version}.json', summary=f'analysis/v{version}/summary.json',
                   rules=f'analysis/v{version}/rules.json', economics=f'analysis/v{version}/economics.json')
    if any(existing['files'].get(name + '.json') != _digest(Path(base) / source) for name, source in sources.items()):
        raise GzError('EXPORT_VERSION_CHANGED', '此版本已有不同内容的导出包，不能覆盖历史文件', '创建新方案版本并计算后再导出')


def preview_export(project_id, version):
    base = storage._path(project_id)
    storage.load_design(project_id, version)
    with transaction(base):
        try:
            try:
                _snapshot(base, version)
            except GzError:
                analysis.analyze(project_id, version, offline=True)
            fingerprint, inputs, evidence, checked = _snapshot(base, version)
            _existing_matches(base, version)
        except (GzError, OSError, ValueError) as error:
            reason = error.message_zh if isinstance(error, GzError) else str(error)
            return dict(project_id=project_id, version=version, ready=False, approval_id=None, summary={},
                        checks=dict(status='unavailable', hard_failed=None, failed_ids=[]),
                        review=dict(status='unverified'), notice=NOTICE, reason=reason, files=[])
        ready = checked.get('status') == 'pass' and checked.get('hard_failed') == 0
        result = dict(project_id=project_id, version=version, ready=ready, approval_id=None,
                      summary=_read(base / f'analysis/v{version}/summary.json'), checks=checked,
                      review=dict(status='unverified', reason='本地导出不证明已完成独立工程审核'),
                      notice=NOTICE, reason='' if ready else '硬性规则未通过或存在未知检查结果，请先修改并复算。',
                      files=[f'layout-v{version}.dxf', f'bom-v{version}.xlsx', 'design.json',
                             'summary.json', 'rules.json', 'economics.json', 'manifest.json'])
        if ready:
            identifier = uuid4().hex
            expires = datetime.now(timezone.utc) + timedelta(minutes=20)
            ticket = dict(approval_id=identifier, project_id=project_id, version=version, status='pending',
                          fingerprint=fingerprint, inputs=inputs, expires_at=expires.isoformat(), notice=NOTICE)
            _write(base / f'approvals/export-{identifier}.json', ticket)
            result.update(approval_id=identifier, expires_at=ticket['expires_at'])
        return result


def approve_export(project_id, version, approval_id):
    base = storage._path(project_id)
    ticket_path = base / f'approvals/export-{approval_id}.json'
    with transaction(base):
        try:
            ticket = _read(ticket_path)
        except (OSError, ValueError) as error:
            raise GzError('LOCAL_EXPORT_STALE', '找不到有效的导出预览', '重新预览后批准') from error
        if ticket.get('project_id') != project_id or ticket.get('version') != version:
            raise GzError('LOCAL_EXPORT_STALE', '批准内容与当前项目或版本不符', '重新预览后批准')
        if ticket.get('status') != 'pending':
            raise GzError('LOCAL_EXPORT_USED', '这次导出批准已经使用或失败', '下载已生成文件，或重新预览导出')
        if datetime.now(timezone.utc) >= datetime.fromisoformat(ticket['expires_at']):
            raise GzError('LOCAL_EXPORT_STALE', '导出预览已过期', '重新预览后批准')
        fingerprint, inputs, _evidence, checked = _snapshot(base, version)
        if fingerprint != ticket['fingerprint'] or checked.get('status') != 'pass':
            raise GzError('LOCAL_EXPORT_STALE', '预览后设计、输入或计算记录已经改变', '重新预览后批准')
        _existing_matches(base, version)
        ticket['status'] = 'executing'
        _write(ticket_path, ticket)
        try:
            result = mcp_actions._export(project_id, version, offline=True, recalculate=False)
            # Refuse to certify a package if another writer changed its source meanwhile.
            if _snapshot(base, version)[0] != fingerprint:
                raise GzError('LOCAL_EXPORT_STALE', '导出期间计算记录已经改变', '保留文件，创建新版本并重新核对')
            receipt = dict(kind='local-user', status='approved-once', approval_id=approval_id,
                           project_id=project_id, version=version, approved_at=datetime.now(timezone.utc).isoformat(),
                           fingerprint=fingerprint, design_sha256=inputs['design_sha256'],
                           project_inputs_sha256=inputs['project_inputs_sha256'],
                           manifest_sha256=result['manifest_sha256'], notice=NOTICE)
            receipt_path = base / f'exports/v{version}/approval.json'
            _write(receipt_path, receipt)
            ticket.update(status='consumed', receipt_sha256=_digest(receipt_path))
            _write(ticket_path, ticket)
            return result | dict(project_id=project_id, approval=receipt, review=_review_status(base, version))
        except Exception as error:
            ticket.update(status='failed', error=str(error))
            _write(ticket_path, ticket)
            raise


class ExportPreview(Record):
    version: int = Field(gt=0, strict=True)


class ExportApproval(ExportPreview):
    approval_id: str = Field(pattern='^[a-f0-9]{32}$')
    confirmed: bool = Field(strict=True)

    @field_validator('confirmed')
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError('需要明确批准此版本的这一次导出')
        return value


def _reply(callback):
    from .api import public
    try:
        return public(callback())
    except GzError as error:
        status = 409 if error.error_code in ('LOCAL_EXPORT_STALE', 'LOCAL_EXPORT_USED', 'EXPORT_VERSION_CHANGED', 'EXPORT_INVALID') else 422
        return JSONResponse(dict(error_code=error.error_code, errors=[f'{error.message_zh}。{error.fix_hint}']), status_code=status)


@router.post('/api/projects/{project_id}/exports/preview')
def preview_endpoint(project_id: str, request: Request, payload: ExportPreview):
    from .api import local_only
    local_only(request)
    return _reply(lambda: preview_export(project_id, payload.version))


@router.post('/api/projects/{project_id}/exports/approve')
def approve_endpoint(project_id: str, request: Request, payload: ExportApproval):
    from .api import local_only
    local_only(request)
    return _reply(lambda: approve_export(project_id, payload.version, payload.approval_id))
