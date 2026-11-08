"""Manual geometry must reach shading, load distribution, rules and preview impact."""
import math

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from guangzhu import design_edits, shading, structure
from guangzhu.models import Design, LayoutParams, Module, WindSettings
from guangzhu.manual_rules import winter_module_shadows
from guangzhu.rules import walkway_check
from guangzhu.mcp_server import SCHEMAS
from test_shading_geometry import project, module
from test_structure import project as load_project, two_racks
from test_design_edits_api import editable_project, edit_client, preview_request  # noqa: F401


def test_manual_sky_energy_and_cause_totals_balance_with_real_cached_weather():
    site = load_project()
    site.roof.obstacles, site.roof.keepouts = [], []
    site.roof.parapet_height_m = 1
    design = Design(params=LayoutParams(tilt_deg=0), modules=[module(1,1,1.5,1.5,tilt=0)],
                    statistics={'manual_edits':True, 'partial_reflow':True})
    result = shading.analyze_design(site, design, offline=True)
    row, summary = result['modules'][0], result['summary']
    assert row['diffuse_loss_pct'] > 0
    assert row['total_loss_pct'] == pytest.approx(row['beam_loss_pct'] + row['diffuse_loss_pct'])
    assert sum(summary['source_loss_pct'].values()) == pytest.approx(row['total_loss_pct'])
    assert summary['diffuse_cause_loss_pct']['parapet'] == pytest.approx(row['diffuse_loss_pct'])
    assert result['metadata']['sky_visibility_method'] == 'isotropic_geometry_quadrature'
    assert result['metadata']['sky_visibility_directions'] == 128
    assert 0 < row['total_loss_pct'] < 100
    site.roof.parapet_height_m = 0
    clear = shading.analyze_design(site, design, offline=True)
    assert clear['modules'][0]['total_loss_pct'] == 0


def test_physical_load_uses_rotated_long_edge_and_splits_its_mass_at_the_actual_zone_boundary():
    site = load_project()
    site.roof.outline = [(0,0),(40,0),(40,30),(0,30)]
    site.roof.height_m = 10
    site.roof.wind = WindSettings(basic_pressure_kpa=0)
    long, short, tilt = 2.384, 1.096, 25
    depth, rise = short * math.cos(math.radians(tilt)), short * math.sin(math.radians(tilt))
    # Portrait module rotated 90 degrees within its plane: long side now runs X.
    corners = ((1.5,10,.3),(1.5,10+depth,.3+rise),(1.5+long,10+depth,.3+rise),(1.5+long,10,.3))
    panel = Module(id='R01-1-C001',row=1,tier=1,col=1,center=np.mean(corners,axis=0),
                   corners=corners,tilt=tilt,azimuth=180,orientation='portrait')
    result = structure.calculate(site, Design(params=LayoutParams(), modules=[panel], statistics={'manual_edits':True}))
    assert result['wind']['zone_width_m'] == 2
    assert result['rack_projection_area_m2'] == pytest.approx(long * depth)
    assert result['wind']['zones']['edge']['area_m2'] == pytest.approx(.5 * depth)
    assert result['wind']['zones']['middle']['area_m2'] == pytest.approx((long - .5) * depth)
    assert result['wind']['zones']['edge']['mass_kg'] == pytest.approx(result['mass_kg'] * .5 / long)


def test_retained_manual_layout_followed_by_two_tier_reflow_keeps_both_panel_areas():
    site, design = load_project(), two_racks('portrait', 2)
    site.roof.wind = WindSettings(basic_pressure_kpa=0)
    design.statistics['manual_edits'] = True
    result = structure.calculate(site, design)
    assert result['rack_projection_area_m2'] == pytest.approx(4 * 1.096 * 2.384 * math.cos(math.radians(25)))
    assert result['mass_kg'] == pytest.approx(4 * 34.6)


def test_winter_ray_check_detects_shading_between_same_numbered_rows():
    receiver = module(1, 1, 0, 2, width=1, length=2, tilt=25)
    blocker = module(1, 2, -1, 0, width=3, length=2, tilt=25)
    design = Design(params=LayoutParams(), modules=[receiver,blocker], statistics={'manual_edits':True})
    blocked = winter_module_shadows(project(), design)
    assert receiver.id in blocked
    moved = design.model_copy(deep=True)
    moved.modules[1].corners = tuple((x+30,y,z) for x,y,z in blocker.corners)
    assert not winter_module_shadows(project(), moved)


def test_requested_manual_walkway_is_unverified_not_implicitly_passing():
    site, design = project(), Design(params=LayoutParams(), statistics={'manual_edits':True})
    assert walkway_check(site, design)['status'] == 'na'
    site.requirements.structured.walkway_m_min = .8
    result = walkway_check(site, design)
    assert result['status'] == 'fail' and result['value'] is None
    assert '连续检修通道' in result['evidence'] and result['suggestion'] is None


def test_preview_recomputes_before_with_same_geometry_method_and_lists_all_affected_panels(editable_project, edit_client, monkeypatch):
    calls = []
    def calculated(project, design, *, geometry_sky=False):
        calls.append((bool(design.statistics.get('manual_edits')), geometry_sky))
        return dict(strings=[], module_shading=[dict(id='retained', total_loss_pct=3 if design.version==1 else 1)],
                    shading=dict(avg_loss_pct=3 if design.version==1 else 1, max_loss_pct=3, modules_over_threshold=0))
    monkeypatch.setattr(design_edits, 'calculate_impact', calculated)
    original_preview = design_edits.storage.preview_edit
    def manual(*args, **kwargs):
        result = original_preview(*args, **kwargs)
        result['design']['statistics']['manual_edits'] = True
        return result
    monkeypatch.setattr(design_edits.storage, 'preview_edit', manual)
    response = edit_client.post(f'/api/projects/{editable_project.id}/design-edits/preview',
                                json=preview_request(editable_project) | {'detailed':True})
    assert response.status_code == 200
    assert calls == [(False, True), (True, False)]
    assert response.json()['impact']['shading_changes'] == [dict(id='retained',before_loss_pct=3,after_loss_pct=1,delta_loss_pct=-2)]
    assert 'manual_edits' not in design_edits.storage.load_design(editable_project.id,1).statistics


def test_using_same_sky_method_preserves_original_walkway_rule_status(editable_project):
    site = editable_project.model_copy(deep=True)
    site.requirements.structured.walkway_m_min = .6
    original = design_edits.storage.load_design(site.id, 1)
    assert walkway_check(site, original)['status'] == 'pass'
    before = design_edits.calculate_impact(site, original, geometry_sky=True)
    assert 'G03' not in {row['id'] for row in before['failed']}
    changed = original.model_copy(deep=True)
    changed.statistics['manual_edits'] = True
    after = design_edits.calculate_impact(site, changed)
    assert 'G03' in {row['id'] for row in after['failed']}
    assert '通行路径验证' in next(row['hint_zh'] for row in after['failed'] if row['id'] == 'G03')
    assert before['shading'] == after['shading']
    assert 'manual_edits' not in original.statistics


def test_mcp_cannot_smuggle_manual_ui_operations_or_lock_bypass_fields():
    validator = Draft202012Validator(SCHEMAS['gz_edit_design'])
    request = dict(project_id='roof',version=1,reason='校正组件',preview=True)
    for operation in [dict(op='add_modules',placements=[dict(center=[-2,4],plane_id=1,rotation_deg=30)]),
                      dict(op='move_modules',module_ids=['P1-R01-1-C001'],dx_m=-2,dy_m=3),
                      dict(op='rotate_modules',module_ids=['R01-1-C001'],angle_deg=-90)]:
        assert not validator.is_valid(request | {'ops':[operation]})
        assert not validator.is_valid(request | {'ops':[operation | {'ignore_locks':True}]})
    assert validator.is_valid(request | {'ops':[dict(op='reflow_unlocked',params={'orientation':'portrait'})]})
    assert not validator.is_valid(request | {'ops':[dict(op='reflow_unlocked',params={'orientation':'portrait'},ignore_locks=True)]})
