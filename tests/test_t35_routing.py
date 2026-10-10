"""Independent path geometry and electrical quantity checks for the presentation upgrade."""
import math

import pytest
from shapely.geometry import LineString, Polygon

from guangzhu import cables, electrical
from guangzhu.models import Keepout, Obstacle
from guangzhu.wirepaths import Planner, distance
from test_electrical import project, design


def clean(project, size=100):
    project.roof.outline = [(0, 0), (size, 0), (size, size), (0, size)]
    project.roof.obstacles = []
    project.roof.keepouts = []
    project.roof.inverter_positions = [(0, 0)]
    project.roof.grid_point = (20, 30)
    return project


def test_rectilinear_detour_has_hand_shortest_length_and_stays_inside(project):
    clean(project, 10)
    project.roof.keepouts = [Keepout(id='zone', label='禁区', polygon=[(4, 4), (6, 4), (6, 6), (4, 6)])]
    planner = Planner(project.roof, design(0))
    path = planner.xy((2, 5), (8, 5))
    assert distance(path) == pytest.approx(8)
    assert Polygon(project.roof.outline).covers(LineString(path))
    assert LineString(path).intersection(Polygon(project.roof.keepouts[0].polygon).buffer(-1e-7)).is_empty
    assert distance(planner.xy((8, 5), (2, 5))) == 8


def test_concave_roof_and_unreachable_endpoints(project):
    clean(project)
    project.roof.outline = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]
    planner = Planner(project.roof, design(0))
    path = planner.xy((9, 2), (2, 9))
    assert distance(path) == 14
    assert planner.domain.covers(LineString(path))
    assert planner.xy((9, 2), (8, 8)) is None
    # A keepout band from wall to wall is crossed on a cable tray (penalised, never impossible); equipment still blocks.
    project.roof.keepouts = [Keepout(id='barrier', label='隔断', polygon=[(0, 3), (10, 3), (10, 4), (0, 4)])]
    crossing = Planner(project.roof, design(0))
    path = crossing.xy((2, 2), (2, 8))
    assert distance(path) == 6 and crossing.crossing(path) == pytest.approx(1)
    project.roof.keepouts = []
    project.roof.obstacles = [Obstacle(id='wall', label='设备墙', kind='prism', height_m=2, footprint=[(0, 3), (10, 3), (10, 4), (0, 4)])]
    blocked = Planner(project.roof, design(0))
    assert blocked.xy((2, 2), (2, 8)) is None


def test_candidate_saves_wire_without_changing_string_members(project):
    clean(project)
    option = design(4)
    for panel, xy in zip(option.modules, [(2, 2), (8, 8), (2, 8), (8, 2)]):
        panel.center = (*xy, .3)
    ids = [m.id for m in option.modules]
    selected = Planner(project.roof, option).optimize(ids, [0, 0])
    assert selected['original']['length'] == 44
    assert selected['length'] == 32
    assert selected['changed'] and set(selected['ids']) == set(ids)
    assert ids == [m.id for m in option.modules]


def test_electrical_loop_quantity_voltage_drop_and_blocked_path(project):
    clean(project)
    option = design(25, 25, cols=25)
    result = electrical.calculate(project, option, offline=True)
    dc = result['cables']['dc'][0]
    assert dc['route_m'] == distance(dc['route_3d']) == 148
    assert dc['length_m'] == pytest.approx(162.8)
    assert dc['section_mm2'] == 6 and dc['routing_status'] == 'ok'
    module = electrical.equipment_catalog()['modules'][project.equipment.module_id]
    assert dc['drop_pct'] == pytest.approx(.0244125 * 162.8 * module['imp_a'] / (6 * 25 * module['vmp_v']) * 100)
    assert result['checks']['E10']['status'] == 'pass'
    ac = result['cables']['ac'][0]
    assert ac['route_m'] == distance(ac['route_3d'])
    assert ac['length_m'] == 50 + project.roof.height_m + 5
    assert ac['conductor_m'] == 4 * ac['length_m']
    project.roof.inverter_positions = [(101, 0)]
    invalid = electrical.calculate(project, option, offline=True)
    assert invalid['checks']['E10']['status'] == 'fail'
    assert invalid['cables']['dc'][0]['routing_status'] == 'blocked'
    assert invalid['cables']['dc'][0]['route'] == []
    assert invalid['cables']['routing']['saved_dc_m'] is None


@pytest.mark.parametrize('fault', ['blocked', 'E10', 'E11'])
def test_shadow_candidate_cannot_replace_feasible_wiring_with_failure(project, monkeypatch, fault):
    clean(project)
    project.roof.inverter_positions = [(40, 0)]
    option = design(100, 25, cols=10)
    shadows = dict(version=1, modules=[dict(id=m.id, total_loss_pct=6 if m.col <= 5 else 0) for m in option.modules])
    assert electrical.calculate(project, option, offline=True, shadows=shadows)['wiring']['method'] == '按阴影接'
    original, calls = cables.calculate, []
    def failed_candidate(*args):
        value = original(*args)
        calls.append(value)
        if len(calls) == 2:
            if fault == 'blocked':
                value['cables']['routing']['blocked_routes'] = 1
            else:
                value['checks'][fault]['status'] = 'fail'
        return value
    monkeypatch.setattr(cables, 'calculate', failed_candidate)
    result = electrical.calculate(project, option, offline=True, shadows=shadows)
    assert len(calls) == 2 and result['wiring']['method'] == '按位置接'
    assert result['cables']['routing']['blocked_routes'] == 0
    assert result['checks']['E10']['status'] == result['checks']['E11']['status'] == 'pass'


@pytest.mark.parametrize('kind', ['barn', 'grazing', 'carport'])
def test_new_roof_routes_preserve_members_and_real_3d_lengths(kind):
    from guangzhu.config import ROOT
    from guangzhu import layout
    from guangzhu.models import Project
    record = Project.model_validate_json((ROOT / f'data/demo/projects/{kind}-demo/project.json').read_bytes())
    option = layout.generate_layout(record, {})
    result = electrical.calculate(record, option, offline=True)
    ids = [mid for row in result['strings'] for mid in row['module_ids']]
    assert len(ids) == len(set(ids))
    assert set(ids) | set(result['unused_modules']) == {m.id for m in option.modules}
    for row in result['cables']['dc']:
        if row['routing_status'] == 'ok':
            assert row['route_m'] == pytest.approx(distance(row['route_3d']))
            assert row['length_m'] == pytest.approx(row['route_m'] * 1.1)
            assert math.isfinite(row['drop_pct'])
    assert result['checks']['E09']['status'] == 'pass'


def test_slanted_corridor_falls_back_to_a_diagonal_run(project):
    # A narrow wing at 45° has no horizontal/vertical path at all; the run follows the wing instead of failing.
    clean(project)
    project.roof.outline = [(0, 0), (1, 0), (11, 10), (10, 10)]
    planner = Planner(project.roof, design(0))
    path = planner.xy((.5, .2), (10.5, 9.8))
    assert path is not None and Polygon(project.roof.outline).buffer(1e-6).covers(LineString(path))
    assert distance(path) == pytest.approx(math.dist((.5, .2), (10.5, 9.8)))
