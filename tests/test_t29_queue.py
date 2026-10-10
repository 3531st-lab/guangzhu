"""Real persistent FIFO with simulated archive outcomes, never model calls."""
import shutil

from fastapi.testclient import TestClient
import pytest

from guangzhu import api, brief, park_queue as queue, park_store as store
from test_t29_store import workspace, payload


@pytest.fixture
def fifo(workspace, monkeypatch):
    monkeypatch.setattr(brief, 'ROOT', workspace)
    store.save(payload(), workspace)
    outcomes = {'design':True, 'final':'completed'}
    verify = lambda item, final: outcomes['final' if final else 'design']

    def event(operation, **extra):
        state = queue.load('factory', workspace)
        active = queue.current(state)
        data = dict(revision=state.revision, item=active.id if active else None, **extra)
        return queue.action('factory', operation, data, verify, workspace)

    specs = [dict(spec=dict(template='factory--' + key, id='placeholder', text='按条件设计'),
                  design_model='offline-model', workspace_binding='a' * 64)
             for key in ('low', 'high')]
    event('create', items=specs)
    return workspace, event, outcomes


def test_fifo_pause_restart_review_gate_and_failure(fifo):
    root, event, outcomes = fifo
    event('pause')
    with pytest.raises(ValueError):
        event('claim')
    event('resume')
    event('claim')
    event('sending')
    event('approval')
    restarted = queue.load('factory', root)
    assert restarted.items[0].status == 'approval'
    assert restarted.items[1].status == 'pending'
    outcomes['final'] = None
    with pytest.raises(ValueError):
        event('finish')
    event('review')
    assert queue.current(queue.load('factory', root)).stage == 'review'
    event('sending')
    event('running')
    outcomes['final'] = 'failed'
    event('finish')
    assert queue.current(queue.load('factory', root)).spec.template == 'factory--high'
    event('claim')
    assert queue.load('factory', root).items[1].status == 'creating'


def test_dispatch_uncertainty_never_becomes_resend(fifo):
    root, event, outcomes = fifo
    event('claim')
    event('sending')
    event('error', reason='连接中断，发送结果不明')
    assert queue.current(queue.load('factory', root)).status == 'reconcile'
    with pytest.raises(ValueError):
        event('sending')
    with pytest.raises(ValueError):
        event('claim')
    event('running')
    event('skip')
    assert queue.current(queue.load('factory', root)).status == 'cancelling'
    with pytest.raises(ValueError):
        event('claim')
    event('observed')
    event('cancel_requested')
    event('cancelled')
    assert queue.current(queue.load('factory', root)).spec.template == 'factory--high'


def test_stale_event_and_safe_creation_failure(fifo):
    root, event, outcomes = fifo
    first = queue.current(queue.load('factory', root))
    event('claim')
    event('error', reason='模型未配置；尚未发送任务书')
    state = queue.load('factory', root)
    with pytest.raises(ValueError, match='当前厂房'):
        queue.action('factory', 'running', dict(revision=state.revision, item=first.id), lambda *_:True, root)
    with pytest.raises(ValueError, match='刷新'):
        queue.action('factory', 'claim', dict(revision=0, item=queue.current(state).id), lambda *_:True, root)
    event('skip')
    assert queue.current(queue.load('factory', root)) is None


def test_review_export_switches_preserved(fifo):
    root, event, outcomes = fifo
    event('skip')
    event('skip')
    spec = dict(template='factory--low', id='draft', text='先设计，不导出', review=False, export=False)
    event('create', items=[dict(spec=spec, design_model='offline', workspace_binding='a' * 64)])
    item = queue.current(queue.load('factory', root))
    assert not item.spec.review and not item.spec.export


def test_cancel_requires_persisted_request_and_started_evidence(fifo):
    root, event, outcomes = fifo
    event('claim')
    event('sending')
    event('skip')
    with pytest.raises(ValueError):
        event('cancelled')
    event('cancel_requested')
    with pytest.raises(ValueError):
        event('cancelled')
    restored = queue.current(queue.load('factory', root))
    assert restored.cancel_requested and not restored.started
    event('observed')
    event('cancelled')
    assert queue.load('factory', root).items[0].status == 'skipped'


def test_the_owner_can_abandon_a_stuck_batch_and_start_again(fifo):
    root, event, outcomes = fifo
    event('claim')
    event('sending')
    event('skip')  # waiting for a cancel confirmation that may never come (e.g. the app was upgraded meanwhile)
    with pytest.raises(ValueError):
        event('create', items=[dict(spec=dict(template='factory--low', id='placeholder', text='重新开始'),
                                    design_model='offline-model', workspace_binding='b' * 64)])
    with pytest.raises(ValueError):  # only the current building's event counts
        queue.action('factory', 'abandon', dict(revision=queue.load('factory', root).revision, item='not-current'), lambda *a: None, root)
    event('abandon')
    rows = queue.load('factory', root).items
    assert [row.status for row in rows] == ['skipped', 'skipped'] and all('放弃' in row.reason for row in rows)
    assert queue.current(queue.load('factory', root)) is None
    event('create', items=[dict(spec=dict(template='factory--low', id='placeholder', text='重新开始'),
                                design_model='offline-model', workspace_binding='b' * 64)])
    assert queue.current(queue.load('factory', root)).status == 'pending'


def test_taking_a_building_out_after_the_batch_ended_keeps_the_park_page_working(fifo, monkeypatch):
    root, event, outcomes = fifo
    event('abandon')
    monkeypatch.setattr(api, 'ROOT', root)
    client = TestClient(api.app)
    shutil.rmtree(root / 'data/parks/factory/roofs/factory--high')  # how the previous version left it: the queue still names the removed building
    assert client.get('/api/parks').status_code == 200 and len(queue.load('factory', root).items) == 2
    before = queue.load('factory', root).revision
    store.save(dict(payload(), buildings=[dict(template='low')]), root)
    state = queue.load('factory', root)
    assert state.items == [] and state.revision == before + 1
    assert client.get('/api/parks').status_code == 200 and client.get('/api/parks/factory').json()['queue']['items'] == []
    event('create', items=[dict(spec=dict(template='factory--low', id='placeholder', text='重新开始'),
                                design_model='offline-model', workspace_binding='b' * 64)])
    assert queue.current(queue.load('factory', root)).spec.template == 'factory--low'
