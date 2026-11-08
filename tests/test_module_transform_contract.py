"""3D gestures use the same catalogue and physical geometry as saved edits."""
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from guangzhu import api, layout, project as storage
from test_manual_modules import factory, add


@pytest.mark.parametrize('kind', ['flat', 'metal', 'pitched'])
def test_live_scene_exposes_exact_catalogue_without_changing_files(factory, tmp_path, monkeypatch, kind):
    project, design = factory(kind)
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    base = tmp_path / 'projects' / project.id
    before = {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in base.rglob('*') if p.is_file()}
    response = TestClient(api.app).get(f'/api/projects/{project.id}/result?version={design.version}')
    assert response.status_code == 200, response.text
    spec = response.json()['scene']['module_transform_spec']
    module, gap, lower = layout._catalog(project, design.params)
    assert spec == dict(available=True, length_m=float(module['length_m']), width_m=float(module['width_m']),
                        gap_m=gap, lower_edge_m=lower)
    after = {p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in base.rglob('*') if p.is_file()}
    assert before == after


def test_unsupported_rack_spec_cannot_enable_free_single_module_gesture(factory, tmp_path, monkeypatch):
    project, _ = factory(rows_per_rack=2)
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    response = TestClient(api.app).get(f'/api/projects/{project.id}/result?version=1')
    assert response.status_code == 200, response.text
    spec = response.json()['scene']['module_transform_spec']
    assert spec['available'] is False
    assert '双排' in spec['reason']
    assert 'length_m' not in spec


def test_summary_only_legacy_design_remains_readable_with_gesture_disabled(factory, tmp_path, monkeypatch):
    project, _ = factory()
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    api.evidence.write_json(storage._path(project.id, 'designs/v1.json'), dict(version=1, modules=[dict(id='legacy')]))
    response = TestClient(api.app).get(f'/api/projects/{project.id}/result?version=1')
    assert response.status_code == 200, response.text
    spec = response.json()['scene']['module_transform_spec']
    assert spec['available'] is False
    assert '完整' in spec['reason']


@pytest.mark.parametrize('kind,center,plane', [('flat', [10, 8], None), ('metal', [10, 8], None),
                                            ('pitched', [8, 8], 1)])
@pytest.mark.parametrize('orientation', ['portrait', 'landscape'])
def test_browser_ghost_matches_backend_after_move_and_repeated_rotation(factory, kind, center, plane, orientation):
    """Cross-language comparison catches sign, datum, slope and catalogue errors."""
    from guangzhu import manual_modules
    project, blank = factory(kind)
    placement = dict(center=center, orientation=orientation, rotation_deg=23)
    if plane is not None:
        placement['plane_id'] = plane
    design = add(project, blank, [placement])
    spec = manual_modules.transform_spec(project, design)
    operations = [dict(mode='move', dx_m=.37123, dy_m=-.61854), dict(mode='rotate', angle_deg=37),
                  dict(mode='rotate', angle_deg=-151), dict(mode='rotate', angle_deg=180),
                  dict(mode='move', dx_m=-.21357, dy_m=.31789)]
    expected = []
    for operation in operations:
        op = dict(op='move_modules' if operation['mode'] == 'move' else 'rotate_modules',
                  module_ids=[design.modules[0].id], **{k: v for k, v in operation.items() if k != 'mode'})
        design, _ = manual_modules.apply(project, design, op)
        expected.append(design.modules[0].model_dump(mode='json'))
    original = storage.load_design(project.id, 2).modules[0].model_dump(mode='json')
    root = Path(__file__).resolve().parents[1]
    script = """
import {transformModuleGeometry} from './desktop/web/module-transform-geometry.js';
let input='';for await(const chunk of process.stdin) input+=chunk;
const {module,roof,spec,operations}=JSON.parse(input);let current=module;const result=[];
for(const operation of operations) {current=transformModuleGeometry(current,roof,operation,spec);result.push(current);}
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=root,
                            input=json.dumps(dict(module=original, roof=project.roof.model_dump(mode='json'),
                                                  spec=spec, operations=operations)),
                            encoding='utf-8', capture_output=True, check=True, timeout=20)
    actual = json.loads(result.stdout)
    for browser, server in zip(actual, expected, strict=True):
        for field in ('center', 'corners', 'tilt', 'azimuth'):
            np.testing.assert_allclose(browser[field], server[field], atol=1e-9, rtol=0)
