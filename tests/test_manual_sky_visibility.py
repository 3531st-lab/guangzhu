"""Irregular placement uses physical sky visibility, independently of row labels."""
import numpy as np
import pytest

from guangzhu.models import Design, LayoutParams
from guangzhu.shading_geometry import build_scene, sample_points, ray_hits
from guangzhu.sky_visibility import sky_visibility
from test_shading_geometry import project, module


def visibility(site, design, **options):
    points = sample_points(design)
    owners = np.broadcast_to(np.arange(len(design.modules))[:, None, None], points.shape[:-1])
    return sky_visibility(design, build_scene(site, design), points, owners, **options)


@pytest.mark.parametrize('tilt', [0, 25, 60])
def test_isolated_panel_has_full_sky_even_after_translation(tilt):
    panel = module(1, 1, -2, -2, tilt=min(tilt, 35))
    if tilt > 35:
        # A steep physical surface is valid with a roof-plane identifier.
        panel = panel.model_copy(update={'id': 'P1-R01-1-C001'})
        angle = np.radians(tilt)
        panel.corners = ((0, 0, .3), (1, 0, .3), (1, np.cos(angle), .3 + np.sin(angle)), (0, np.cos(angle), .3 + np.sin(angle)))
        panel.tilt = tilt
    design = Design(params=LayoutParams(), modules=[panel], statistics={'manual_edits': True})
    fraction, shares = visibility(project(), design)
    assert fraction.tolist() == [0] and shares == {}
    panel.corners = tuple(tuple(np.asarray(point) + [15, 21, 0]) for point in panel.corners)
    assert visibility(project(), design)[0].tolist() == [0]


def test_wall_covering_one_sky_hemisphere_blocks_exactly_half_horizontal_irradiance():
    # All sampled eastern sky rays hit this near, high wall; western rays are open.
    wall = dict(id='east-wall', label='东侧墙', kind='prism', height_m=100,
                footprint=[[1,-90],[2,-90],[2,90],[1,90]])
    panel = module(1, 1, -.5, -.5, width=1, length=1, tilt=0)
    design = Design(params=LayoutParams(), modules=[panel])
    fraction, shares = visibility(project([wall]), design)
    assert fraction[0] == pytest.approx(.5, abs=1e-12)
    assert shares['east-wall'][0] == pytest.approx(.5, abs=1e-12)
    assert visibility(project(), design)[0][0] == 0


def test_foreign_orientation_and_same_row_panels_still_block_the_receiver():
    receiver = module(1, 1, 0, 0, width=1, length=1, tilt=0)
    blocker = module(1, 2, -5, -5, width=12, length=12, tilt=0)
    blocker.corners = tuple((x, y, z + 1) for x, y, z in blocker.corners)
    blocker.azimuth = 90
    complete = Design(params=LayoutParams(), modules=[receiver, blocker])
    full_scene, full_points = build_scene(project(), complete), sample_points(complete)
    full_owners = np.broadcast_to(np.arange(2)[:, None, None], full_points.shape[:-1])
    def across_groups(unused_scene, unused_points, vector, unused_owners):
        return ray_hits(full_scene, full_points, vector, full_owners)[:1]
    group = complete.model_copy(update={'modules': [receiver]})
    fraction, shares = visibility(project(), group, hits=across_groups)
    assert fraction[0] > .9
    assert shares['front_row'][0] == fraction[0]
    renamed = group.model_copy(deep=True)
    renamed.modules[0].row = 99
    renamed.modules[0].id = 'R99-1-C001'
    np.testing.assert_array_equal(visibility(project(), renamed, hits=across_groups)[0], fraction)


def test_receiver_cosine_changes_when_the_physical_panel_turns_towards_wall():
    wall = dict(id='east-wall', label='东侧墙', kind='prism', height_m=100,
                footprint=[[3,-90],[4,-90],[4,90],[3,90]])
    panel = module(1, 1, -.5, -.5, width=1, length=1, tilt=30)
    design = Design(params=LayoutParams(), modules=[panel])
    south = visibility(project([wall]), design)[0][0]
    matrix = np.array([[0,-1,0],[1,0,0],[0,0,1]])
    panel.corners = tuple(map(tuple, np.asarray(panel.corners) @ matrix.T))
    panel.azimuth = 90
    east = visibility(project([wall]), design)[0][0]
    assert south == pytest.approx(.5, abs=1e-12)
    assert .6 < east < 1


def test_empty_design_has_no_visibility_losses():
    fraction, shares = visibility(project(), Design(params=LayoutParams()))
    assert fraction.size == 0 and shares == {}
