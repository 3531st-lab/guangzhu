"""Independent T32 geometry oracles; no product output constructs an expected answer."""
import math

import pytest
from shapely.affinity import rotate, translate
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from guangzhu import models, roofplane


@pytest.mark.parametrize('angle', [0, 37])
@pytest.mark.parametrize('depth', [.03, 20])
@pytest.mark.parametrize('offset, valid', [(0, True), (1, False)])
def test_nonparallel_narrow_wedge_still_requires_matching_heights(angle, depth, offset, valid):
    outline = list(box(0, 0, 40, depth).exterior.coords)[:-1]
    shapes = [box(0, 0, 20, depth), Polygon([(20.001, 0), (40, 0), (40, depth), (20.019, depth)])]
    boundary = list(rotate(Polygon(outline), angle, origin=(0, 0)).exterior.coords)[:-1]
    planes = [dict(id=i + 1, outline=list(rotate(shape, angle, origin=(0, 0)).exterior.coords)[:-1],
                   slope_deg=1, slope_azimuth_deg=(180 - angle) % 360, offset_m=offset if i else 0)
              for i, shape in enumerate(shapes)]
    if valid:
        value = roof(planes, boundary)
        assert roofplane.seams(value)
    else:
        with pytest.raises(models.GzError, match='高度'):
            roof(planes, boundary)


def generated(kind, outline=None, **settings):
    assert callable(getattr(roofplane, 'generate', None)), 'T32 needs a shared real roof-plane generator'
    return roofplane.generate(outline or list(box(0, 0, 20, 10).exterior.coords)[:-1], dict(kind=kind, **settings))


def roof(planes, outline=None):
    return models.Roof(type='pitched', outline=outline or list(box(0, 0, 20, 10).exterior.coords)[:-1],
                       height_m=9, parapet_height_m=0, load_capacity_kn_m2=.5, planes=planes)


def test_hip_hand_areas_ridge_heights_and_square_degeneracy():
    value = roof(generated('hip', slope_deg=30)['planes'])
    shapes = [Polygon(p.outline) for p in value.planes]
    assert sorted(p.area for p in shapes) == pytest.approx([25, 25, 75, 75])
    assert unary_union(shapes).area == pytest.approx(200)
    assert sorted(p.area / math.cos(math.pi / 6) for p in shapes) == pytest.approx(
        [28.867513459481287, 28.867513459481287, 86.60254037844386, 86.60254037844386])
    assert roofplane.elevation(value, [5, 5]) == pytest.approx(2.886751345948129)
    assert roofplane.elevation(value, [15, 5]) == pytest.approx(2.886751345948129)
    square = list(box(0, 0, 10, 10).exterior.coords)[:-1]
    result = roof(generated('hip', square, slope_deg=30)['planes'], square)
    assert len(result.planes) == 4
    assert all(len(p.outline) == 3 for p in result.planes)
    assert all(Polygon(p.outline).area == pytest.approx(25) for p in result.planes)


def test_gable_manual_offcenter_and_matched_t24_height():
    outline = list(box(0, 0, 100, 36).exterior.coords)[:-1]
    value = roof(generated('gable', outline, slope_deg=5)['planes'], outline)
    assert len(value.planes) == 2
    assert all(Polygon(p.outline).area == pytest.approx(1800) for p in value.planes)
    assert value.height_m + roofplane.elevation(value, [50, 18]) == pytest.approx(10.574795943466633)
    outline = list(box(0, 0, 30, 20).exterior.coords)[:-1]
    value = roof(generated('gable', outline, slope_deg=5, ridge=[[2, 12], [3, 12]])['planes'], outline)
    assert sorted(p.offset_m for p in value.planes) == pytest.approx([0, .34995465410369603])
    assert roofplane.elevation(value, [15, 12]) == pytest.approx(1.0498639623110881)
    with pytest.raises(models.GzError):
        generated('gable', outline, ridge=[[0, 0], [0, 0]])


def test_saw_real_sloped_glass_closure_and_actual_width():
    outline = list(box(0, 0, 30, 40).exterior.coords)[:-1]
    result = generated('sawtooth', outline, slope_deg=10, glass_deg=70, teeth=4, azimuth_deg=180)
    value = roof(result['planes'], outline)
    assert len(value.planes) == 8
    assert result['actual_teeth'] == 4 and result['actual_pitch_m'] == pytest.approx(10)
    for p in value.planes:
        width = Polygon(p.outline).bounds[3] - Polygon(p.outline).bounds[1]
        assert width == pytest.approx(.6030737921409166 if p.material == 'glass' else 9.396926207859083)
        assert max(roofplane.plane_elevation(p, xy) for xy in p.outline) == pytest.approx(1.6569316261720375)
    adjusted = generated('sawtooth', outline, tooth_width_m=11, slope_deg=10, glass_deg=70)
    assert adjusted['actual_teeth'] == 4 and adjusted['actual_pitch_m'] == pytest.approx(10)


@pytest.mark.parametrize('delta,valid', [(0, True), (.019, True), (.021, False), (.038, False), (-.019, True), (-.021, False)])
@pytest.mark.parametrize('angle', [0, 37])
def test_metric_seam_tolerance_not_area_or_double_buffer(delta, valid, angle):
    transform = lambda shape: translate(rotate(shape, angle, origin=(0, 0)), 13, -7)
    outline = list(transform(box(0, 0, 40, 20)).exterior.coords)[:-1]
    parts = [box(0, 0, 20 - delta / 2, 20), box(20 + delta / 2, 0, 40, 20)]
    planes = [dict(id=i + 1, outline=list(transform(p).exterior.coords)[:-1], slope_deg=1,
                   slope_azimuth_deg=(180 - angle) % 360, offset_m=0, material='metal') for i, p in enumerate(parts)]
    if valid:
        assert len(roof(planes, outline).planes) == 2
    else:
        with pytest.raises(models.GzError, match='2厘米'):
            roof(planes, outline)


@pytest.mark.parametrize('height,valid', [(.019, True), (.021, False)])
def test_common_edge_height_is_independent_from_coverage(height, valid):
    planes = [dict(id=i + 1, outline=list(box(i * 10, 0, (i + 1) * 10, 10).exterior.coords)[:-1],
                   slope_deg=1, slope_azimuth_deg=180, offset_m=height * i, material='metal') for i in range(2)]
    if valid:
        roof(planes)
    else:
        with pytest.raises(models.GzError, match='高度'):
            roof(planes)


def test_cross_valley_obstacle_minimum_occurs_at_new_intersection_vertices():
    planes = [dict(id=1, outline=[[0, 0], [10, 0], [10, 10], [0, 10]], slope_deg=30,
                   slope_azimuth_deg=90, offset_m=0, material='metal'),
              dict(id=2, outline=[[10, 0], [20, 0], [20, 10], [10, 10]], slope_deg=30,
                   slope_azimuth_deg=270, offset_m=0, material='concrete')]
    value = roof(planes)
    footprint = Polygon([(7, 2), (13, 2), (13, 8), (7, 8)])
    assert min(roofplane.elevation(value, p) for p in footprint.exterior.coords) > 1
    assert roofplane.minimum(value, footprint) == pytest.approx(0)
