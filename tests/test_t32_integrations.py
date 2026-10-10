"""Frozen T31 coordinates, real mixed phases, park identity and immutable scene reads."""
import hashlib
import json
import math
from pathlib import Path
from shutil import copytree

import pytest
import requests
from fastapi.testclient import TestClient

from guangzhu import analysis, api, costs, electrical, layout, park, park_store, roofplane, structure
from guangzhu import project as storage, mcp_actions
from guangzhu.config import ROOT
from guangzhu.models import Project, StructuredRequirements
from test_t32_engineering import project


def test_matched_one_metre_seam_keeps_all_960_t31_centres_and_corners():
    record = Project.model_validate_json((ROOT / 'data/demo/projects/pitched-gable-demo/project.json').read_text(encoding='utf-8'))
    record.roof.seam_setback_m = 1
    design = layout.generate_layout(record, {})
    assert len(design.modules) == 960 and design.statistics['dc_kw'] == 528
    # Independent Root reference pinned to T31 00605c30, with original north XY already at y18..36.
    hashes = {180: 'a1ca6a97c9922981154307a0dd1e42dd59ca237d3bcbac74620d54996d51fd18',
              0: 'd80b6a9e87c29512d7d7ff78911a7893e2405f379fd0c83a8409198047c61276'}
    for azimuth, expected in hashes.items():
        members = [m for m in design.modules if m.azimuth == azimuth]
        points = sorted([[m.center, m.corners] for m in members])
        assert len(members) == 480
        assert hashlib.sha256(json.dumps(points, separators=(',', ':')).encode()).hexdigest() == expected
    record.roof.seam_setback_m = .5
    default = layout.generate_layout(record, {})
    assert default.statistics['seam_setback_m'] == .5
    assert default.statistics['usable_area_m2'] > design.statistics['usable_area_m2']


def test_preview_invalid_input_is_a_recoverable_422():
    client = TestClient(api.app, base_url='http://127.0.0.1:8765', headers={'origin': 'http://127.0.0.1:8765'})
    assert client.post('/api/roof-planes', json={}).status_code == 422


def test_pitched_is_one_park_building_and_neighbour_uses_actual_maximum(tmp_path):
    high = project('hip', slope_deg=30)
    high.id, high.name, high.roof.height_m = 'high', '整栋四坡示意', 9
    low = project('single')
    low.id, low.name, low.roof.height_m = 'low', '较低单坡示意', 5
    for value in (high, low):
        park_store.write(tmp_path / 'data/my-roofs' / value.id / 'project.json', value.model_dump(mode='json'))
    saved = park_store.save(dict(id='t32-park', name='整栋园区示意', buildings=[dict(template='high'), dict(template='low', x_m=50)]), tmp_path)
    assert len(saved['buildings']) == 2
    folder = tmp_path / 'data/parks/t32-park/roofs'
    copies = list(folder.glob('*/project.json'))
    assert len(copies) == 2
    record = Project.model_validate_json((folder / 't32-park--low/project.json').read_text(encoding='utf-8'))
    neighbour = next(o for o in record.roof.surroundings if o.id == 'park-high')
    assert neighbour.height_m == pytest.approx(9 + 10 * math.tan(math.pi / 6) - 5)
    assert '最高屋面棱柱保守示意' in neighbour.label
    assert len(Project.model_validate_json((folder / 't32-park--high/project.json').read_text(encoding='utf-8')).roof.planes) == 4


@pytest.fixture
def mixed_phase(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path / 'projects')
    monkeypatch.setattr(requests.Session, 'request', lambda *a, **k: pytest.fail('T32 must remain offline'))
    storage.init(ROOT / 'data/demo/projects/changzhou-demo', 't32-mixed')
    record = project()
    record.id = 't32-mixed'
    record.roof.load_capacity_kn_m2 = 3
    record.roof.planes[1].material = 'concrete'
    record.roof.planes[1].load_capacity_kn_m2 = .4
    record.roof.planes[1].load_verified = True
    record.requirements.structured = StructuredRequirements(phase1_budget_cny=90000)
    record.equipment.inverter_id = None
    storage.save(record)
    mcp_actions._generate_layout(record.id, {}, offline=True)
    summary = analysis.analyze(record.id, 1, offline=True)
    design = storage.load_design(record.id, 1)
    values = {name: mcp_actions._read(record.id, f'analysis/v1/{name}.json')
              for name in ('electrical', 'economics', 'structure', 'rules')}
    return record, design, summary, values, tmp_path


def test_mixed_phase_budget_cash_actual_sites_and_workbook_are_one_quantity_contract(mixed_phase):
    from openpyxl import load_workbook
    from guangzhu.report.deliverables import write_deliverables
    record, design, summary, values, temporary = mixed_phase
    cash, full = values['economics'], values['structure']
    assert summary['rules']['hard_failed'] == 0
    assert {m.phase for m in design.modules} == {1, 2}
    selected = [m.model_copy(update=dict(phase=None)) for m in design.modules if m.phase == 1]
    standalone = design.model_copy(update=dict(modules=selected))
    first_load = structure.calculate(record, standalone)
    first_electric = electrical.calculate(record, standalone, offline=True)
    quote = costs.itemized(record, len(selected) * .55, standalone, first_electric, first_load)
    assert design.statistics['phasing']['achieved_cny'] == pytest.approx(quote['capex_cny'])
    assert cash['phases'][0]['capex_cny'] == pytest.approx(quote['capex_cny'])
    assert quote['capex_cny'] <= 90000
    assert cash['phase_cashflows']['first'][0]['net_cny'] == pytest.approx(-quote['capex_cny'])
    full_first = [r for r in full['wind']['modules'] if r['phase'] == 1]
    actual = lambda rows: {r['id']: [list(p) for p in r.get('clamps', {}).get('points', [])] for r in rows}
    assert actual(full_first) == actual(first_load['wind']['modules']) == actual(cash['first_phase_wind']['modules'])
    assert full['ballast_mass_kg'] == 0
    inherited, own = full['planes']
    assert inherited['capacity_source'] == '继承整栋' and own['capacity_source'] == '坡面值' and own['verified']
    assert own['capacity_kn_m2'] == .4
    write_deliverables(record.id, 1, temporary)
    book = load_workbook(temporary / 'bom-v1.xlsx', data_only=True)
    quantities = list(book['分期材料'].values)[1:]
    for phase in (1, 2):
        for plane in record.roof.planes:
            rows = [r for r in full['wind']['modules'] if r['phase'] == phase and r['plane'] == plane.id]
            suffix = '抗风夹具' if plane.material == 'metal' else '锚固件'
            expected = sum(r['clamps']['adopted'] if plane.material == 'metal' else r['anchors'] for r in rows)
            assert sum(r[3] for r in quantities if r[0] == phase and r[1] == f'P{plane.id} {suffix}') == expected
    assert not any('压块' in r[1] for r in quantities)
    prices = list(book['坡面造价'].values)[1:]
    assert math.fsum(r[5] for r in prices) == pytest.approx(cash['capex_cny'])
    book.close()


def test_snapshot_replays_all_faces_after_live_roof_changes(mixed_phase, monkeypatch):
    record, design, summary, values, temporary = mixed_phase
    monkeypatch.setattr(api, 'ROOT', temporary)
    source = storage._path(record.id)
    capture = temporary / 'runs/gz-t32-snapshot'
    copytree(source, capture / 'project')
    artifacts = {p.relative_to(capture).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (capture / 'project').rglob('*.json')}
    park_store.write(capture / 'run.json', dict(project_id=record.id, artifacts=artifacts))
    api.snapshot_scene(capture, record.id)
    before = api.result_data(record.id, 1, capture)['scene']
    assert len(before['roof_geometry']['faces']) == 2
    record.roof.height_m += 7
    storage.save(record)
    after = api.result_data(record.id, 1, capture)['scene']
    live = api.result_data(record.id, 1)['scene']
    assert before == after
    assert live['project']['roof']['height_m'] == before['project']['roof']['height_m'] + 7
    assert all(m['id'].startswith('P') for m in after['design']['modules'])


def test_face_rule_failures_keep_their_actual_plane_and_capacity(mixed_phase):
    from guangzhu import rules, mcp_server, wind
    record, design, summary, values, temporary = mixed_phase
    record.roof.planes[1].load_capacity_kn_m2 = .01
    load = structure.calculate(record, design)
    shadows = mcp_actions._read(record.id, 'analysis/v1/shading.json')
    checked = rules.evaluate(record, design, shadows, values['electrical'], load, values['economics'])
    by_face = {r['plane']: r for r in checked['items'] if r['id'] == 'L01'}
    assert by_face[1]['status'] == 'pass' and by_face[2]['status'] == 'fail'
    assert by_face[2]['limit'] == .01 and load['governing_plane'] == 2
    storage.save(record)
    reply = mcp_server.call('gz_analyze', dict(project_id=record.id, version=1, offline=True))
    assert not reply.is_error
    result = json.loads(reply.content[0].text)
    assert result['load']['governing_plane'] == 2
    failures = [r for r in result['rules']['failed'] if r['id'] == 'L01']
    assert len(failures) == 1 and failures[0]['plane'] == 2 and failures[0]['limit'] == .01
    assert result['rules']['hard_failed'] == checked['hard_failed']
    assert result['wind'] == wind.facts(load['wind'], 1) and result['wind']['note'] == wind.NOTE
    actions = [r['suggestion'] for r in checked['items'] if r['level'] == 'hard' and r['status'] == 'fail' and r['suggestion']]
    assert result['suggestions'] == actions
    assert len(reply.content[0].text.encode('utf-8')) + 128 <= 2048
    wrapped = mcp_server.JobQueue.response(dict(result, tool='gz_analyze', job_id='t32-face-failure-envelope'))
    assert len(wrapped.content[0].text.encode('utf-8')) <= 2048
    changed = design.model_copy(deep=True)
    panel = next(m for m in changed.modules if m.id.startswith('P1-'))
    panel.corners = tuple((x, y + 10, z) for x, y, z in panel.corners)
    checked = rules.evaluate(record, changed, shadows, values['electrical'], load, values['economics'])
    wrong = next(r for r in checked['items'] if r['id'] == 'G01' and r['plane'] == 1)
    assert wrong['status'] == 'fail' and panel.id in wrong['suggestion']['module_ids']
