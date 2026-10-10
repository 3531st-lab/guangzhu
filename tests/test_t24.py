"""T24 real offline tool flow, planar geometry and split-roof acceptance."""
import copy
import json
import math
import os
from pathlib import Path

import numpy as np
import pytest
import requests
from shapely.geometry import Polygon

from guangzhu import analysis, brief, layout, mcp_actions, models, myroofs, project, shading, sitecheck, structure
from guangzhu.config import ROOT
from guangzhu.roofplane import elevation
from guangzhu.shading_geometry import build_scene, ray_hits, sample_points, sun_vector
from guangzhu.report.view import render

ASSETS = ROOT / 'reports/assets/T24'
WRITE_EVIDENCE = os.environ.get('GUANGZHU_WRITE_EVIDENCE') == '1'  # a normal test run never rewrites committed evidence


def metal(azimuth=180, slope=5):
    payload = json.loads((ROOT / 'data/demo/projects/metal-demo-s/project.json').read_text(encoding='utf-8'))
    payload['roof'].update(slope_deg=slope, slope_azimuth_deg=azimuth)
    return models.validate_project(payload)


@pytest.mark.parametrize('azimuth', [0, 90, 180, 360])
@pytest.mark.parametrize('slope', [1, 5, 30])
def test_plane_numeric_acceptance_and_fixed_ai_parameters(azimuth, slope):
    p = metal(azimuth, slope)
    design = layout.generate_layout(p, dict(tilt_deg=15, azimuth_deg=200, rows_per_rack=2, winter_window_hours=[0, 1]))
    assert design.modules
    assert design.params.tilt_deg == slope and design.params.azimuth_deg == azimuth
    assert design.params.rows_per_rack == 1 and design.params.winter_window_hours == (9, 15)
    assert design.statistics['row_spacing_m'] == pytest.approx(2.384 * math.cos(math.radians(slope)) + .02)
    for module in design.modules:
        for x, y, z in module.corners:
            assert z - elevation(p.roof, [x, y]) == pytest.approx(.1, abs=1e-8)
        assert abs(module.corners[3][2] - module.corners[0][2]) == pytest.approx(2.384 * math.sin(math.radians(slope)), abs=1e-8)
    if slope == 5:
        assert round(design.statistics['row_spacing_m'], 3) == 2.395
        assert round(abs(design.modules[0].corners[3][2] - design.modules[0].corners[0][2]), 3) == .208
        assert round(structure.calculate(p, design)['added_kn_m2'], 3) == .119
    walked = layout.generate_layout(p, dict(walkway_every_n_rows=2, walkway_width_m=1))
    assert len(walked.modules) < len(design.modules)


def test_data_and_flat_compatibility():
    original = json.loads((ROOT / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    flat = models.validate_project(original)
    assert not {'slope_deg', 'slope_azimuth_deg', 'building'} & flat.roof.model_dump().keys()
    with pytest.raises(models.GzError, match='场址或组件角度'):
        layout.generate_layout(flat, dict(azimuth_deg=0))
    for p in [flat, metal()]:
        p.equipment.racking = 'clamp_flush' if p.roof.type == 'flat' else 'ballast_tilt'
        with pytest.raises(models.GzError) as caught:
            models.validate_project(p)
        assert caught.value.error_code == 'RACK_TYPE_INVALID'
    for change in [dict(slope_deg=0), dict(slope_deg=31), dict(slope_azimuth_deg=-1), dict(slope_azimuth_deg=361), dict(slope_deg=None)]:
        p = metal().model_dump(by_alias=True)
        p['roof'].update(change)
        with pytest.raises(models.GzError):
            models.validate_project(p)


def test_shading_obstacle_base_tracks_slope_and_blocks_northern_modules():
    p = metal()
    p.roof.obstacles = [models.Obstacle(id='tall', label='高障碍物', kind='prism', height_m=8,
                                     footprint=[[40, 3], [45, 3], [45, 5], [40, 5]])]
    design = layout.generate_layout(p, {})
    scene = build_scene(p, design)
    assert scene.faces[0][0, 2] == pytest.approx(elevation(p.roof, [40, 3]) + 8)
    points = sample_points(design)
    owners = np.broadcast_to(np.arange(len(design.modules))[:, None, None], points.shape[:-1])
    hits = ray_hits(scene, points, sun_vector(25, 180), owners)
    north = [i for i, module in enumerate(design.modules) if module.center[1] > 5]
    assert (hits[north] == 'tall').any()
    calculated = shading.analyze_design(p, design, offline=True)
    assert calculated['metadata']['sky_masking_fraction'] == 0
    assert all(row['diffuse_loss_pct'] == 0 for row in calculated['modules'])


def split_payload():
    return dict(name='厂房示意', site=dict(lat=31.81, lon=119.97), roof_mode='metal-gable', roof=dict(
        type='metal', outline=[[0, 0], [100, 0], [100, 36], [0, 36]], slope_deg=5, slope_azimuth_deg=180,
        height_m=9, parapet_height_m=0, load_capacity_kn_m2=.3, obstacles=[], keepouts=[], surroundings=[]))


@pytest.mark.parametrize('ridge', [None, [[45, 18], [55, 18]]])
def test_gable_split_defaults_and_extended_short_hand_line(tmp_path, ridge):
    from shutil import copytree
    copytree(ROOT / 'data/demo/projects/changzhou-demo', tmp_path / 'data/demo/projects/changzhou-demo')
    payload = split_payload()
    payload['ridge'] = ridge
    payload['roof']['keepouts'] = [dict(id='sky', label='采光带', polygon=[[20, 1], [21, 1], [21, 16], [20, 16]])]
    first = myroofs.save(payload, tmp_path)
    files = list((tmp_path / 'data/my-roofs').glob('*/project.json'))
    roofs = [json.loads(file.read_text(encoding='utf-8')) for file in files]
    assert len(roofs) == 2 and first in [p['id'] for p in roofs]
    assert {p['roof']['slope_azimuth_deg'] for p in roofs} == {0, 180}
    assert {p['name'] for p in roofs} == {'厂房示意（南坡）', '厂房示意（北坡）'}
    assert all(p['roof']['building'] == '厂房示意' for p in roofs)
    assert all(Polygon(p['roof']['outline']).area == 1800 for p in roofs)
    assert sum(len(p['roof']['keepouts']) for p in roofs) == 1
    myroofs.delete(first, tmp_path)
    assert len(list((tmp_path / 'data/my-roofs').glob('*/project.json'))) == 1
    payload['roof']['keepouts'][0]['polygon'] = [[20, 10], [21, 10], [21, 25], [20, 25]]
    before = set((tmp_path / 'data/my-roofs').glob('*'))
    with pytest.raises(models.GzError, match='请分成两个'):
        myroofs.save(payload, tmp_path)
    assert set((tmp_path / 'data/my-roofs').glob('*')) == before
    payload['roof']['keepouts'][0]['polygon'] = [[20, 10], [21, 10], [21, 18], [20, 18]]
    myroofs.save(payload, tmp_path)
    payload['roof']['keepouts'][0]['polygon'] = [[120, 10], [121, 10], [121, 18], [120, 18]]
    with pytest.raises(models.GzError) as caught:
        myroofs.save(payload, tmp_path)
    assert caught.value.error_code == 'KEEPOUT_OUTSIDE_ROOF'
    payload['roof']['keepouts'] = []
    for invalid in [[[1, 2]], [[1, 2], [float('nan'), 5]], [[1], [2]], ['bad', [1, 2]]]:
        with pytest.raises(models.GzError):
            myroofs.save(dict(payload, ridge=invalid), tmp_path)


@pytest.fixture(scope='module')
def offline_flow(tmp_path_factory):
    from unittest.mock import patch
    temporary = tmp_path_factory.mktemp('t24-tools')
    with patch.object(project, 'PROJECTS_DIR', temporary / 'projects'):
        with patch.object(requests.Session, 'request', side_effect=AssertionError('T24禁止联网')):
            created = mcp_actions._new_project('t24-offline', 'metal-demo-s')
            assert created['roof_type'] == 'metal'
            mcp_actions._set_requirements('t24-offline', '按彩钢瓦顺坡平铺', {})
            generated = mcp_actions._generate_layout('t24-offline', {})
            assert generated['mount'] == 'flush' and generated['tilt_deg'] == 5
            summary = mcp_actions._analyze('t24-offline', 1, offline=True)
            assert summary['ok'] and summary['rules']['hard_failed'] == 0
            checked = json.loads(project._path('t24-offline', 'analysis/v1/rules.json').read_text(encoding='utf-8'))
            assert all(row['status'] == 'na' for row in checked['items'] if row['id'] in {'G02', 'G05'})
            for name in ['tilt_deg', 'azimuth_deg', 'rows_per_rack', 'winter_window_hours']:
                with pytest.raises(models.GzError) as caught:
                    mcp_actions._edit_design('t24-offline', 1, '测试', [dict(op='set_param', name=name, value=10)])
                assert caught.value.error_code == 'METAL_PARAM_FIXED'
            with pytest.raises(models.GzError) as caught:
                mcp_actions._compare_options('t24-offline', 1, offline=True)
            assert caught.value.error_code == 'COMPARE_NOT_APPLICABLE'
            exported = mcp_actions._export('t24-offline', 1, offline=True)
            assert exported['ok'] and 'bom-v1.xlsx' in exported['files']
            from shutil import copyfile
            from openpyxl import load_workbook
            evidence = ASSETS if WRITE_EVIDENCE else temporary / 'evidence'
            target = evidence / 'exports'
            target.mkdir(parents=True, exist_ok=True)
            for filename in [*exported['files'], 'manifest.json']:
                copyfile(project._path('t24-offline', 'exports/v1/' + filename), target / filename)
            book = load_workbook(target / 'bom-v1.xlsx', read_only=True)
            materials = list(book['材料清单'].values)[1:]
            purchases = list(book['造价明细'].values)[1:]
            clamp = next(row for row in materials if row[0] == '抗风夹具')
            assert clamp[2] == '示意通用设计容量' and clamp[4:6] == (2607, '个')
            assert clamp[8:10] == (5, 13035)
            rail = next(row for row in materials if row[0] == '彩钢瓦导轨连接件（示意）')
            assert rail[4:6] == (480, '套') and rail[8:10] == (45, 21600)
            clamp_purchase = next(row for row in purchases if row[0] == '抗风夹具')
            assert clamp_purchase[1:5] == (2607, '个', 5, 13035)
            ballast_purchase = next(row for row in purchases if row[0] == '压块')
            assert ballast_purchase[1] == ballast_purchase[4] == 0
            assert not any('压块' in str(row[0]) for row in materials)
            load = json.loads(project._path('t24-offline', 'analysis/v1/structure.json').read_text(encoding='utf-8'))
            assert load['ballast_mass_kg'] == load['wind']['ballast_blocks'] == 0
            assert all(row['ballast_kg'] == row['ballast_blocks'] == 0 for row in load['wind']['modules'])
            assert load['wind']['clamp_count'] == clamp[4] and load['wind']['clamp_failed'] == 0
            book.close()
            context = dict(project=project.load('t24-offline').model_dump(by_alias=True), summary=summary,
                           design=project.load_design('t24-offline', 1).model_dump(mode='json'), version=1, compare=None, facts=dict(roof_type='metal'))
            for key, filename in [('rules', 'rules'), ('economics', 'economics'), ('electrical', 'electrical'),
                                  ('shading', 'shading'), ('structure', 'structure')]:
                context[key] = json.loads(project._path('t24-offline', f'analysis/v1/{filename}.json').read_text(encoding='utf-8'))
            context.update(review=None, approval=None, sessions=[], requirements=[dict(text='按彩钢瓦顺坡平铺')],
                           verification={}, sources={}, versions=[], relaxations=[], history=[], run={},
                           generated_at='2026-10-06T00:00:00+08:00', run_id='T24-offline-no-AI', project_id='t24-offline')
            context['crosscheck'] = mcp_actions._crosscheck_yield('t24-offline', 1, offline=True)
            contents = render(context)
            assert '预算5万元' not in contents and '同意取消' not in contents
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / 'proposal.html').write_text(contents, encoding='utf-8')
            (evidence / 'tool-flow.json').write_text(json.dumps(dict(created=created, layout=generated, analysis=summary,
                export=exported), ensure_ascii=False, indent=2), encoding='utf-8')
            scene = dict(project=context['project'], design=context['design'], shading=context['shading'], electrical=context['electrical'])
            yield contents, scene


def test_offline_flow_report_and_brief(offline_flow):
    contents, scene = offline_flow
    assert '彩钢瓦单坡 5°' in contents and '没有压块' in contents and '彩钢瓦，不适用' in contents
    assert '坡度 5°' in contents and '另一坡面单独设计' in contents
    assert '未提供 AI 会话、AGH 执行记录、导出批准和独立审核证据' in contents
    data = brief.render_brief(dict(template='metal-demo-s', id='metal-brief', text='彩钢瓦', compare=True))
    assert '"compare":false' in data
    for answer, expected in [('metal', 'ok'), ('concrete', 'risk'), (None, 'ask')]:
        assert sitecheck.rows(dict(roof_type=answer), roof_type='metal')[0]['status'] == expected
