"""Park ownership, geometry and publication tests; all writes use tmp_path."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import os

import pytest
from pydantic import ValidationError

from guangzhu import park_store as store
from guangzhu.models import Project
from guangzhu.templates import catalog

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path):
    for key in ('low', 'high'):
        value = json.loads((ROOT / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
        value.update(id=key, name=key, designs=[])
        value['roof'].update(outline=[[0, 0], [10, 0], [10, 10], [0, 10]], height_m=10 if key == 'low' else 15,
                             parapet_height_m=0, obstacles=[], keepouts=[])
        store.write(tmp_path / 'data/my-roofs' / key / 'project.json', value)
    return tmp_path


def payload():
    return dict(id='factory', name='测试厂区', buildings=[dict(template='low'), dict(template='high', x_m=20)])


@pytest.mark.parametrize('window', ['copied', 'prepared', 'target-moved', 'published'])
def test_publication_crash_recovery_and_hidden_enumeration(workspace, window):
    store.save(payload(), workspace)
    base = workspace / 'data/parks'
    target = base / 'factory'
    transaction_id = 'a' * 32
    stage, backup = base / ('.stage-' + transaction_id), base / ('.backup-' + transaction_id)
    shutil.copytree(target, stage)
    changed = store.read(stage / 'park.json')
    changed['name'] = '新版本'
    store.write(stage / 'park.json', changed)
    if window != 'copied':
        store.write(base / '.publish-factory.json', dict(id='factory', token=transaction_id))
    if window in ('target-moved', 'published'):
        target.rename(backup)
    if window == 'published':
        stage.rename(target)
    assert 'factory--low' in catalog(root=workspace)
    assert len(store.listing(workspace)) == 1
    assert store.load('factory', workspace).name == ('新版本' if window == 'published' else '测试厂区')
    assert store.load('factory', workspace).buildings[1].x_m == 20
    assert not (base / '.publish-factory.json').exists()


def test_roofs_json_consumption_holds_snapshot_until_paths_are_read(workspace, monkeypatch):
    from guangzhu import api, templates
    store.save(payload(), workspace)
    monkeypatch.setattr(api, 'ROOT', workspace)
    original = templates.catalog
    done = threading.Event()
    writers = []
    changed = payload()
    changed['buildings'][1]['x_m'] = 25
    def lookup(*args, **kwargs):
        result = original(*args, **kwargs)
        if not writers:
            worker = threading.Thread(target=lambda: (store.save(changed, workspace), done.set()))
            writers.append(worker)
            worker.start()
            assert not done.wait(.15)
        return result
    monkeypatch.setattr(templates, 'catalog', lookup)
    roofs = json.loads(api.roofs().body)['roofs']
    writers[0].join(10)
    assert done.is_set()
    low = next(row for row in roofs if row['id'] == 'factory--low')
    assert low['project']['roof']['surroundings'][0]['footprint'][0][0] == 20
    assert store.load('factory', workspace).buildings[1].x_m == 25


def test_other_process_catalog_waits_for_active_publisher(workspace, monkeypatch):
    store.save(payload(), workspace)
    target = workspace / 'data/parks/factory'
    rename = Path.rename
    children = []
    script = """import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'backend'))
from guangzhu.templates import catalog
from guangzhu import park_store as store
root = Path(sys.argv[1])
print('ready', flush=True)
print(len(catalog(root=root)), store.load('factory', root).name, flush=True)
"""
    def paused(path, destination):
        result = rename(path, destination)
        if path == target:
            child = subprocess.Popen([sys.executable, '-c', script, str(workspace)], stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, encoding='utf-8', env=os.environ.copy(),
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            children.append(child)
            assert child.stdout.readline().strip() == 'ready'
            with pytest.raises(subprocess.TimeoutExpired):
                child.wait(timeout=.2)
        return result
    monkeypatch.setattr(Path, 'rename', paused)
    store.save(dict(payload(), name='published name'), workspace)
    output, error = children[0].communicate(timeout=10)
    assert children[0].returncode == 0, error
    assert output.strip() == '4 published name'
    assert store.load('factory', workspace).name == 'published name'


def test_process_exit_releases_lock_and_recovers_old_publication(workspace):
    store.save(payload(), workspace)
    script = """import sys, os, shutil
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'backend'))
from guangzhu import park_store as store
root = Path(sys.argv[1])
with store.transaction(root):
    target = root / 'data/parks/factory'
    transaction_id = 'd' * 32
    shutil.copytree(target, target.parent / ('.stage-' + transaction_id))
    store.write(target.parent / '.publish-factory.json', dict(id='factory', token=transaction_id))
    target.rename(target.parent / ('.backup-' + transaction_id))
    os._exit(23)
"""
    crash = subprocess.run([sys.executable, '-c', script, str(workspace)], env=os.environ.copy(), timeout=10,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert crash.returncode == 23
    recovery = """import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'backend'))
from guangzhu import park_store as store
from guangzhu.templates import catalog
root = Path(sys.argv[1])
assert len(catalog(root=root)) == 4
assert store.load('factory', root).name == '测试厂区'
"""
    result = subprocess.run([sys.executable, '-c', recovery, str(workspace)], env=os.environ.copy(), timeout=10,
                            capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert result.returncode == 0, result.stderr.decode('utf-8')
    assert not (workspace / 'data/parks/.publish-factory.json').exists()


def test_mcp_template_copy_holds_the_same_publication_boundary(workspace, monkeypatch):
    from guangzhu import mcp_actions, project
    source = workspace / 'data/my-roofs/low'
    value = store.read(source / 'project.json')
    value['roof']['underlay'] = dict(image='roof.png', calibration=dict(p1_px=[0, 0], p2_px=[10, 0], distance_m=10))
    store.write(source / 'project.json', value)
    (source / 'roof.png').write_bytes(b'offline-underlay-fixture')
    store.save(payload(), workspace)
    monkeypatch.setattr(mcp_actions, 'ROOT', workspace)
    monkeypatch.setattr(project, 'PROJECTS_DIR', workspace / 'projects')
    original = project.init
    done = threading.Event()
    workers = []
    def consume(source, identifier):
        changed = payload()
        changed['buildings'][1]['x_m'] = 25
        worker = threading.Thread(target=lambda: (store.save(changed, workspace), done.set()))
        workers.append(worker)
        worker.start()
        assert not done.wait(.15)
        return original(source, identifier)
    monkeypatch.setattr(project, 'init', consume)
    mcp_actions._new_project('snapshot-copy', 'factory--low')
    workers[0].join(10)
    assert done.is_set()
    assert project.load('snapshot-copy').roof.surroundings[0].footprint[0][0] == 20
    assert (workspace / 'projects/snapshot-copy/underlay/roof.png').read_bytes() == b'offline-underlay-fixture'
    assert store.load('factory', workspace).buildings[1].x_m == 25


def test_neighbours_originals_and_delete(workspace):
    original = workspace / 'data/my-roofs/low/project.json'
    before = original.read_bytes()
    store.save(payload(), workspace)
    path = catalog(root=workspace)['factory--low']
    roof = store.read(path)['roof']
    assert roof['surroundings'][0]['height_m'] == 5
    assert roof['surroundings'][0]['footprint'] == [[20, 0], [30, 0], [30, 10], [20, 10]]
    assert not store.read(catalog(root=workspace)['factory--high'])['roof'].get('surroundings')
    assert original.read_bytes() == before
    assert store.load('factory', workspace).name == '测试厂区'
    store.delete('factory', workspace)
    assert original.read_bytes() == before


def test_rotation_and_preserved_tree(workspace):
    path = workspace / 'data/my-roofs/low/project.json'
    value = store.read(path)
    value['roof']['surroundings'] = [dict(id='tree', label='原树', kind='cylinder', height_m=2, center=[-5, -5], radius_m=1)]
    store.write(path, value)
    data = payload()
    data['buildings'][0]['rotation_deg'] = 90
    store.save(data, workspace)
    result = store.read(catalog(root=workspace)['factory--low'])
    assert result['roof']['surroundings'][0]['id'] == 'tree'
    neighbour = result['roof']['surroundings'][1]
    assert neighbour['footprint'][0] == pytest.approx([0, -20])
    assert Project.model_validate(result).park.id == 'factory'


@pytest.mark.parametrize('change', [dict(id='../escape'), dict(grid_kw=-1), dict(transformer_kva=0), dict(name='')])
def test_validation(workspace, change):
    with pytest.raises(Exception):
        store.save(dict(payload(), **change), workspace)
    assert not (workspace / 'data/parks/factory').exists()


def test_duplicate_nonfinite_and_failed_save(workspace):
    data = payload()
    data['buildings'].append(dict(template='low'))
    with pytest.raises(ValidationError):
        store.save(data, workspace)
    store.save(payload(), workspace)
    before = (workspace / 'data/parks/factory/park.json').read_bytes()
    data = payload()
    data['buildings'][0]['x_m'] = float('nan')
    with pytest.raises(ValidationError):
        store.save(data, workspace)
    data = payload()
    data['buildings'][1]['x_m'] = 1
    with pytest.raises(Exception):
        store.save(data, workspace)
    assert (workspace / 'data/parks/factory/park.json').read_bytes() == before


def test_no_anchor_places_apart_and_queue_freezes(workspace):
    result = store.place(store.Park.model_validate(payload()), workspace)
    assert result.origin is None
    assert result.buildings[1].x_m - result.buildings[0].x_m >= 30
    store.save(result.model_dump(), workspace)
    store.write(workspace / 'data/parks/factory/queue.json', dict(items=[dict(status='awaiting_approval')]))
    with pytest.raises(ValueError, match='冻结'):
        store.save(payload(), workspace)
    with pytest.raises(ValueError, match='冻结'):
        store.delete('factory', workspace)


def test_real_osm_positions_without_rounded_site(tmp_path):
    for key in ('t12-real-07', 't12-real-09', 't12-real-10', 't12-real-11'):
        shutil.copytree(ROOT / 'data/roofs' / key, tmp_path / 'data/roofs' / key)
    shutil.copy2(ROOT / 'data/roofs/osm-raw.json', tmp_path / 'data/roofs/osm-raw.json')
    park = store.demo(tmp_path)
    by_id = {b['template']: b for b in park['buildings']}
    assert by_id['t12-real-09']['x_m'] == pytest.approx(-11.087441, abs=.01)
    assert by_id['t12-real-09']['y_m'] == pytest.approx(-164.383439, abs=.01)
    assert by_id['t12-real-11']['y_m'] == pytest.approx(-55.743917, abs=.01)
    assert len(catalog(root=tmp_path)) == 8
