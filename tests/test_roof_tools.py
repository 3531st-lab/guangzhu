"""Editor corridor geometry must remain inside real concave roof footprints."""
import pytest
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union

from guangzhu.models import Roof
from guangzhu.roof_tools import CrossWalkwaysRequest, cross_walkways


OUTLINES = [
    [[0,0],[60,0],[60,36],[0,36]],
    [[0,0],[60,0],[60,18.72],[33,18.72],[33,36],[0,36]],
    [[0,0],[60,0],[60,36],[43.2,36],[43.2,15.12],[16.8,15.12],[16.8,36],[0,36]],
    [[16.8,0],[43.2,0],[43.2,17.28],[60,17.28],[60,36],[0,36],[0,17.28],[16.8,17.28]],
]


@pytest.mark.parametrize('outline', OUTLINES)
@pytest.mark.parametrize('angle', [0, 37])
def test_corridors_are_contained_and_can_be_saved_for_rectangle_l_u_t(outline, angle):
    polygon = affinity.rotate(Polygon(outline), angle, origin=(0,0))
    boundary = [list(point) for point in list(polygon.exterior.coords)[:-1]]
    result = cross_walkways(CrossWalkwaysRequest(outline=boundary, width_m=1, setback_m=1.2))
    assert result['polygons']
    generated = unary_union([Polygon(points) for points in result['polygons']])
    assert generated.is_valid and generated.area > 10
    assert polygon.covers(generated)
    assert generated.difference(polygon.buffer(-1.2 + 1e-7)).area < 1e-7
    roof = Roof.model_validate(dict(type='flat', outline=boundary, height_m=10,
        parapet_height_m=0, load_capacity_kn_m2=.5,
        keepouts=[dict(id=f'walkway-{i}',label='检修通道',polygon=points) for i,points in enumerate(result['polygons'])]))
    assert len(roof.keepouts) == len(result['polygons'])
    assert '连通性' in result['note']


def test_no_room_after_setback_does_not_invent_corridors():
    result = cross_walkways(CrossWalkwaysRequest(outline=[[0,0],[2,0],[2,1],[0,1]]))
    assert result['polygons'] == [] and '没有' in result['note']


def test_api_corridor_helper_is_local_and_does_not_save_files(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from guangzhu import api
    from guangzhu.config import API_ORIGIN
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    with TestClient(api.app, base_url=API_ORIGIN) as client:
        body = dict(outline=OUTLINES[2])
        reply = client.post('/api/roof-tools/cross-walkways',json=body,headers={'origin':API_ORIGIN})
        assert reply.status_code == 200, reply.text
        assert reply.json()['polygons']
        assert client.post('/api/roof-tools/cross-walkways',json=body,headers={'origin':'https://elsewhere.test'}).status_code==403
    assert list(tmp_path.iterdir()) == []
