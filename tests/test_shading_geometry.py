"""T05 geometric acceptance with synthetic scenes, without network access."""

import json
import math
from pathlib import Path

import numpy as np
import pytest
from shapely.geometry import Point

from guangzhu.layout import row_spacing, true_solar_times
from guangzhu.models import Design, GzError, LayoutParams, Module, validate_project
from guangzhu.shading_geometry import beam_fractions, build_scene, pole_shadow, ray_hits, sample_points, shadow_polygons, sun_vector
from guangzhu.solar import sun_position


def project(obstacles=(), parapet=0):
    payload = json.loads((Path(__file__).parent / 'fixtures/roofs/symmetric.json').read_text(encoding='utf-8'))
    payload['roof'].update(outline=[[-100, -100], [100, -100], [100, 100], [-100, 100]],
                           parapet_height_m=parapet, obstacles=list(obstacles), keepouts=[])
    return validate_project(payload)


def prism(width, depth, height, identifier='box'):
    return dict(id=identifier, label=identifier, kind='prism', height_m=height,
                footprint=[[-width / 2, -depth / 2], [width / 2, -depth / 2],
                           [width / 2, depth / 2], [-width / 2, depth / 2]])


def module(row, col, x, y, width=1.096, length=2.384, tilt=25):
    beta = math.radians(tilt)
    corners = np.array([[x, y, .3], [x + width, y, .3],
                        [x + width, y + length * math.cos(beta), .3 + length * math.sin(beta)],
                        [x, y + length * math.cos(beta), .3 + length * math.sin(beta)]])
    return Module(id=f'R{row:02d}-1-C{col:03d}', row=row, col=col, tier=1, corners=corners,
                  center=corners.mean(axis=0), tilt=tilt, azimuth=180, orientation='portrait')


def test_thin_pole_shadow_cap_center_matches_three_spa_instants():
    scene = build_scene(project([prism(.05, .05, 3, 'pole')]), Design(params=LayoutParams()))
    evidence = []
    for clock in ['09:00', '12:00', '15:00']:
        stamp = f'2025-12-21T{clock}+08:00'
        prediction = pole_shadow(31.81, 119.97, stamp, 3)
        bearing = math.radians(prediction['shadow_direction_deg'])
        direction = np.array([math.sin(bearing), math.cos(bearing)])
        boundary = np.asarray(shadow_polygons(scene, stamp)['pole'].exterior.coords[:-1])
        far_cap = boundary[boundary @ direction >= (boundary @ direction).max() - math.sqrt(2) * .05 - 1e-7]
        distances = np.linalg.norm(far_cap[:, None] - far_cap[None, :], axis=2)
        a, b = np.unravel_index(distances.argmax(), distances.shape)
        tip = (far_cap[a] + far_cap[b]) / 2
        length = np.linalg.norm(tip)
        angle = math.degrees(math.atan2(tip[0], tip[1])) % 360
        length_error = abs(length / prediction['shadow_length_m'] - 1)
        angle_error = abs((angle - prediction['shadow_direction_deg'] + 180) % 360 - 180)
        assert length_error < .01 and angle_error < .1
        evidence.append(dict(clock=clock, length_m=length, length_relative_error=length_error, direction_error_deg=angle_error))
    print('T05 pole:', json.dumps(evidence))
    for bad_time, bad_height in [('nonsense', 1), ('2025-12-21T12:00', 1), ('2025-12-21T12:00+08:00', 0)]:
        with pytest.raises(GzError):
            pole_shadow(31.81, 119.97, bad_time, bad_height)


def test_rectangular_shadow_area_matches_three_analytic_values():
    width, depth, height = 4, 2, 3
    scene = build_scene(project([prism(width, depth, height)]), Design(params=LayoutParams()))
    evidence = []
    for clock in ['09:00', '12:00', '15:00']:
        stamp = f'2025-12-21T{clock}+08:00'
        sun = pole_shadow(31.81, 119.97, stamp, height)
        alpha, bearing = np.radians([sun['sun_elevation_deg'], sun['sun_azimuth_deg']])
        expected = width * depth + height / np.tan(alpha) * (depth * abs(np.sin(bearing)) + width * abs(np.cos(bearing)))
        actual = shadow_polygons(scene, stamp)['box'].area
        assert abs(actual / expected - 1) < .02
        evidence.append(dict(clock=clock, calculated_m2=actual, analytic_m2=expected))
    print('T05 rectangle:', json.dumps(evidence))
    concave = dict(id='concave', label='concave', kind='prism', height_m=.1,
                   footprint=[[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]])
    shadow = shadow_polygons(build_scene(project([concave]), Design(params=LayoutParams())), '2025-12-21T12:00+08:00')['concave']
    assert not shadow.covers(Point(3, 3))
    assert shadow.convex_hull.area > shadow.area + 1


def test_t04_winter_spacing_passes_window_and_shades_bottom_at_eight():
    pitch = row_spacing(31.81, 119.97, 25, 2.384)['row_spacing_m']
    modules = [module(row, col, (col - 11) * 1.116, (row - 1) * pitch)
               for row in [1, 2] for col in range(1, 22)]
    design = Design(params=LayoutParams(), modules=modules)
    scene = build_scene(project(), design)
    points = sample_points(design)
    owners = np.broadcast_to(np.arange(len(modules))[:, None, None], points.shape[:-1])
    times = true_solar_times(119.97, [9 + 5 / 60, 14 + 55 / 60, 8])
    positions = sun_position(times, 31.81, 119.97)
    evidence = []
    for index, (hour, sun) in enumerate(zip([9 + 5 / 60, 14 + 55 / 60, 8], positions.itertuples())):
        hits = ray_hits(scene, points, sun_vector(sun.elevation, sun.azimuth), owners)[28:35]
        if index < 2:
            assert not (hits != '').any()
        else:
            assert (hits[:, :, 0] == 'front_row').all()
        evidence.append(dict(true_solar_hour=hour, elevation_deg=sun.elevation, blocked_points=int((hits != '').sum())))
    print('T05 T04 rows:', json.dumps(evidence))


def test_horizontal_bottom_shadow_respects_portrait_landscape_and_cause_votes():
    hits = np.full((2, 3, 3), '', dtype=object)
    hits[:, :, 0] = 'wall'
    fraction, shares = beam_fractions(hits, ['landscape', 'portrait'])
    np.testing.assert_allclose(fraction, [1 / 3, 1])
    np.testing.assert_allclose(shares['wall'], fraction)
    hits = np.array([[['b', 'a', ''], ['b', 'b', 'a'], ['', '', '']]], dtype=object)
    fraction, shares = beam_fractions(hits, ['portrait'])
    np.testing.assert_allclose(fraction, [2 / 3])
    np.testing.assert_allclose(shares['a'], [1 / 3])
    np.testing.assert_allclose(shares['b'], [1 / 3])


def test_clear_roof_is_zero_and_wall_at_noon_blocks_entire_module():
    design = Design(params=LayoutParams(), modules=[module(1, 1, -.5, 2)])
    points = sample_points(design)
    owners = np.zeros(points.shape[:-1], dtype=int)
    vector = sun_vector(35, 180)
    clear = ray_hits(build_scene(project(), design), points, vector, owners)
    np.testing.assert_allclose(beam_fractions(clear, ['portrait'])[0], [0])
    wall = prism(10, .1, 10, 'high-wall')
    blocked = ray_hits(build_scene(project([wall]), design), points, vector, owners)
    assert (blocked == 'high-wall').all()
    np.testing.assert_allclose(beam_fractions(blocked, ['portrait'])[0], [1])
    far_wall = prism(10, .1, 20, 'far-wall')
    far_wall['footprint'] = [[x, y - 1] for x, y in far_wall['footprint']]
    nearest = ray_hits(build_scene(project([far_wall, wall]), design), points, vector, owners)
    assert (nearest == 'high-wall').all()
    cylinder = dict(id='cylinder', label='cylinder', kind='cylinder', height_m=1, center=[0, 0], radius_m=1)
    cylinder_scene = build_scene(project([cylinder]), Design(params=LayoutParams()))
    assert len(cylinder_scene.faces) == 33 and len(cylinder_scene.faces[0]) == 32
