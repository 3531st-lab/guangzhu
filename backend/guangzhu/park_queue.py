"""Durable FIFO identities; prompt delivery is deliberately not retried."""
from typing import Literal
import uuid

from pydantic import Field

from .brief import BriefSpec
from .config import ROOT
from .models import Record
from . import park_store as store

TERMINAL = ('completed', 'failed', 'skipped')


class Item(Record):
    id: str
    spec: BriefSpec
    design_model: str = Field(min_length=1, max_length=256)
    design_session: str
    review_session: str
    snapshot: str
    stage: Literal['design', 'review'] = 'design'
    status: Literal['pending', 'creating', 'sending', 'running', 'approval', 'cancelling', 'reconcile', 'completed', 'failed', 'skipped'] = 'pending'
    reason: str = Field(default='', max_length=500)
    started: bool = False
    cancel_requested: bool = False
    workspace_binding: str = Field(default='', pattern=r'^(?:[a-f0-9]{64})?$')


class Queue(Record):
    revision: int = Field(default=0, ge=0)
    paused: bool = False
    items: list[Item] = Field(default_factory=list, max_length=100)


def load(identifier, root=ROOT):
    with store.transaction(root):
        store.recover(root)
        path = store.folder(identifier, root) / 'queue.json'
        return Queue.model_validate(store.read(path), context={'stored': True}) if path.exists() else Queue()


def current(queue):
    return next((item for item in queue.items if item.status not in TERMINAL), None)


def action(identifier, operation, payload, verify, root=ROOT):
    with store.transaction(root):
        park = store.load(identifier, root)
        queue = load(identifier, root)
        if set(payload) - {'revision', 'items', 'item', 'reason'} or payload.get('revision') != queue.revision:
            raise ValueError('队列已变更，请刷新后再操作')
        item = current(queue)
        if operation == 'create':
            if item or not payload.get('items'):
                raise ValueError('请先完成现有队列，并选择厂房')
            values = []
            for row in payload['items']:
                if set(row) != {'spec', 'design_model', 'workspace_binding'} or not row['workspace_binding']:
                    raise ValueError('队列只保存任务书及模型编号')
                token = uuid.uuid4().hex
                spec = BriefSpec.model_validate(dict(row['spec'], id='park-' + token))
                if spec.template not in {park.id + '--' + b.template for b in park.buildings}:
                    raise ValueError('队列模板不属于当前园区')
                if spec.review and spec.review_mode != 'independent':
                    raise ValueError('启用审核时沿用正常独立审核链')
                source = store.read(store.folder(identifier, root) / 'roofs' / spec.template / 'project.json')
                values.append(Item(id=token, spec=spec, design_model=row['design_model'], snapshot=source['park']['snapshot'],
                                   workspace_binding=row['workspace_binding'],
                                   design_session='park-design-' + token, review_session='park-review-' + token))
            if len({item.spec.template for item in values}) != len(values):
                raise ValueError('同栋不能重复入队')
            queue.items = values
            queue.paused = False
        elif operation in ('pause', 'resume'):
            queue.paused = operation == 'pause'
        elif operation == 'abandon':  # the owner gives up the rest of this batch: nothing is sent again, a new batch can start
            if item is None or payload.get('item') != item.id:
                raise ValueError('事件不属于当前厂房')
            for row in queue.items:
                if row.status not in TERMINAL:
                    row.status, row.reason = 'skipped', '已放弃这个队列，没有再派发'
            queue.paused = False
        else:
            if item is None or payload.get('item') != item.id:
                raise ValueError('事件不属于当前厂房')
            if operation == 'claim' and item.status == 'pending' and not queue.paused:
                for other in store.listing(root):
                    active = current(load(other['id'], root))
                    if other['id'] != identifier and active and active.status != 'pending':
                        raise ValueError('另一园区有运行待结束，不能并行派发')
                item.status = 'creating'
            elif operation == 'sending' and item.status == 'creating':
                item.status = 'sending'
            elif operation in ('running', 'approval') and item.status in ('sending', 'running', 'approval', 'reconcile'):
                item.status = operation
            elif operation == 'review' and item.stage == 'design' and item.status in ('running', 'approval', 'reconcile'):
                if verify(item, False) is not True:
                    raise ValueError('设计归档尚未通过四步和导出校验')
                item.stage, item.status = 'review', 'creating'
                item.started, item.cancel_requested = False, False
            elif operation == 'finish':
                if item.status in ('pending', 'creating', 'cancelling'):
                    raise ValueError('尚无可以结束的已派发任务')
                outcome = verify(item, True)
                if outcome not in ('completed', 'failed'):
                    raise ValueError('独立审核及最终归档尚未完成')
                item.status = outcome
            elif operation == 'skip':
                item.status = 'skipped' if item.status == 'pending' else 'cancelling'
                item.cancel_requested = False
            elif operation == 'observed' and item.status not in ('pending', 'creating'):
                item.started = True
            elif operation == 'cancel_requested' and item.status == 'cancelling':
                item.cancel_requested = True
            elif operation == 'cancelled' and item.status == 'cancelling' and item.started and item.cancel_requested:
                item.status = 'skipped'
            elif operation == 'error':
                item.status = 'failed' if item.status == 'creating' else 'reconcile'
            elif operation == 'hold':
                pass
            elif operation == 'failed' and item.status in ('running', 'reconcile'):
                item.status = 'failed'
            else:
                raise ValueError('队列状态不允许此操作；不会重新发送不确定的任务书')
            item.reason = str(payload.get('reason', '四步核对或独立审核未通过' if operation == 'finish' and item.status == 'failed' else ''))[:500]
        queue.revision += 1
        result = queue.model_dump(mode='json')
        store.write(store.folder(identifier, root) / 'queue.json', result)
        return result
