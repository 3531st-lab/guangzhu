"""T19: buildings and trees off the roof are validated, cast annual shadows and appear in drawings."""
import copy
import json
from pathlib import Path

import pytest

from guangzhu.layout import generate_layout
from guangzhu.models import GzError, LayoutParams, validate_project
from guangzhu.report.figures import plan
from guangzhu.shading import analyze_design
from guangzhu.templates import catalog

ROOT = Path(__file__).resolve().parents[1]
DEMO = json.loads((ROOT / "data/demo/projects/south-tower/project.json").read_text(encoding="utf-8"))


def without_surroundings(payload):
    return dict(payload, roof=dict(payload["roof"], surroundings=[]))


@pytest.mark.parametrize("change,code", [
    (dict(footprint=[[10, -5], [20, -5], [20, 5], [10, 5]]), "SURROUNDING_ON_ROOF"),
    (dict(id="stair-1"), "ZONE_ID_DUPLICATE")])
def test_surroundings_stay_off_the_roof_and_keep_their_own_ids(change, code):
    payload = copy.deepcopy(DEMO)
    payload["roof"]["surroundings"][0].update(change)
    with pytest.raises(GzError) as error:
        validate_project(payload)
    assert error.value.error_code == code


def test_roofs_without_surroundings_serialize_exactly_as_before():
    assert "surroundings" in json.loads(validate_project(DEMO).model_dump_json())["roof"]
    assert "surroundings" not in json.loads(validate_project(without_surroundings(DEMO)).model_dump_json())["roof"]
    assert "south-tower" in catalog()


def test_a_tower_to_the_south_shades_the_southern_modules_and_is_reported_separately():
    project, plain = validate_project(DEMO), validate_project(without_surroundings(DEMO))
    design = generate_layout(project, LayoutParams())
    shaded, clear = analyze_design(project, design, offline=True), analyze_design(plain, design, offline=True)
    assert "surroundings" not in clear["summary"]["source_loss_pct"]
    assert shaded["summary"]["source_loss_pct"]["surroundings"] > 1
    assert shaded["summary"]["modules_over_threshold"] > clear["summary"]["modules_over_threshold"] + 20
    centers = {m.id: m.center for m in design.modules}
    worse = [centers[a["id"]] for a, b in zip(shaded["modules"], clear["modules"]) if a["total_loss_pct"] > b["total_loss_pct"] + 3]
    assert worse and all(y < 18 for x, y, *_ in worse)  # only the roof's southern half, next to the tower and the tree
    assert any(x < 30 for x, *_ in worse) and any(x > 44 for x, *_ in worse)


def test_plan_widens_to_show_surroundings():
    data = dict(project=DEMO, design=dict(modules=[]), shading=dict(modules=[]), electrical={})
    figure = str(plan(data))
    assert figure.count("#cfc6bb") == 2 and "香樟树" in figure and "周边建筑：浅灰" in figure
    assert int(figure.split('viewBox="0 0 700 ')[1].split('"')[0]) > 34 + 36 * 640 / 60 + 56
