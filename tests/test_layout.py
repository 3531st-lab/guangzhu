"""T04 acceptance checks use synthetic roofs and the task's hand calculation."""

import json
import math
from pathlib import Path
import time

import numpy as np
from shapely.geometry import Polygon

from guangzhu.layout import generate_layout, row_spacing, usable_geometry
from guangzhu.models import LayoutParams, obstacle_polygon, validate_project


ROOT = Path(__file__).resolve().parents[1]


def fixture_project(name):
    return validate_project(json.loads((ROOT / 'tests/fixtures/roofs' / (name + '.json')).read_text(encoding='utf-8')))


def test_south_spacing_matches_all_twelve_hand_answers():
    for latitude in [20, 31.81, 40]:
        coefficient = (0.707 * math.tan(math.radians(latitude)) + 0.4338) / (0.707 - 0.4338 * math.tan(math.radians(latitude)))
        for tilt in [15, 25]:
            for length in [2.384, 2 * 1.096 + 0.02]:
                expected = length * (math.cos(math.radians(tilt)) + math.sin(math.radians(tilt)) * coefficient)
                actual = row_spacing(latitude, 119.97, tilt, length)['row_spacing_m']
                assert abs(actual / expected - 1) < 0.01
    assert row_spacing(31.81,119.97,0,2.384)['row_spacing_m'] == 2.384


def test_every_module_on_three_roofs_respects_all_clearances():
    for name in ['l_shape','rotated','symmetric']:
        project, params = fixture_project(name), LayoutParams()
        design = generate_layout(project,params)
        geometry = usable_geometry(project,params)
        assert design.modules
        for module in design.modules:
            footprint=Polygon(np.array(module.corners)[:,:2])
            assert geometry['usable'].buffer(0.001).covers(footprint)
            roof=Polygon(project.roof.outline)
            assert roof.buffer(0.001).covers(footprint)
            assert footprint.distance(roof.boundary)>=params.edge_setback_m-0.001
            for obstacle in project.roof.obstacles:
                assert footprint.distance(obstacle_polygon(obstacle))>=params.obstacle_clearance_m-0.001
            for zone in project.roof.keepouts:
                assert footprint.distance(Polygon(zone.polygon))>=params.keepout_clearance_m-0.001
        assert sum(design.statistics['rejected_positions'].values()) == len(design.statistics['rejected_candidates'])
        assert all(item['reason'] in design.statistics['rejected_positions'] for item in design.statistics['rejected_candidates'])


def test_east_west_mirror_counts_and_deterministic_serialization():
    project = fixture_project('symmetric')
    left = generate_layout(project,LayoutParams(azimuth_deg=160))
    right = generate_layout(project,LayoutParams(azimuth_deg=200))
    assert len(left.modules) == len(right.modules)
    repeated = generate_layout(project,LayoutParams(azimuth_deg=160))
    assert left.model_dump(exclude={'created_at'}) == repeated.model_dump(exclude={'created_at'})


def test_two_tiers_have_correct_orientation_corners_and_row_column_ids():
    project = fixture_project('symmetric')
    params=LayoutParams(orientation='landscape',rows_per_rack=2,walkway_every_n_rows=2,walkway_width_m=2)
    design=generate_layout(project,params)
    by_rack={}
    for module in design.modules:
        by_rack.setdefault((module.row,module.col),[]).append(module)
        assert module.id == f'R{module.row:02d}-{module.tier}-C{module.col:03d}'
        corners=np.array(module.corners)
        np.testing.assert_allclose(np.linalg.norm(corners[1]-corners[0]),2.384,atol=0.002)
        np.testing.assert_allclose(np.linalg.norm(corners[3]-corners[0]),1.096,atol=0.002)
        assert all(float(value)==round(float(value),3) for value in corners.flat)
    for modules in by_rack.values():
        assert sorted(m.tier for m in modules)==[1,2]
        lower,upper=sorted(modules,key=lambda m:m.tier)
        np.testing.assert_allclose(np.linalg.norm(np.array(lower.corners[3])-np.array(upper.corners[0])),0.02,atol=0.002)
    rows=sorted({module.row for module in design.modules})
    starts={row:min(m.corners[0][1] for m in design.modules if m.row==row) for row in rows}
    projected= (2*1.096+0.02)*math.cos(math.radians(25))
    for index,(a,b) in enumerate(zip(rows,rows[1:]),start=1):
        if index % 2 == 0:
            assert starts[b]-starts[a]-projected >= 2-0.002


def test_demo_generation_under_one_second():
    payload=json.loads((ROOT/'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    project=validate_project(payload)
    started=time.perf_counter()
    result=generate_layout(project,LayoutParams())
    assert result.modules and time.perf_counter()-started<1
