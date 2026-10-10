"""Roof validation, calibration, immutable versions and the four edit operations."""

import copy
import json
import shutil
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from guangzhu import project as storage
from guangzhu.config import DATA_DIR
from guangzhu.models import Design, GzError, LayoutParams, Module, Project, StructuredRequirements, obstacle_polygon, px_to_m, validate_project, validated


@pytest.fixture
def payload():
    record = json.loads((DATA_DIR / "demo/projects/changzhou-demo/project.json").read_text(encoding="utf-8"))
    record["designs"] = []  # These cases start with an empty project, rather than the demo's version chain.
    return record


@pytest.fixture
def local_project(payload, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    return storage.save(payload)


def test_roof_validation_and_normalization(payload):
    invalid = [
        ({"outline": [[0, 0], [1, 1]]}, "ROOF_POLYGON_INVALID"),
        ({"outline": [[0, 0], [3, 3], [0, 3], [3, 0]]}, "ROOF_POLYGON_INVALID"),
        ({"outline": [[0, 0], [1, 1], [2, 2]]}, "ROOF_POLYGON_INVALID"),
        ({"height_m": 0}, "ROOF_HEIGHT_INVALID"),
        ({"parapet_height_m": 3.1}, "PARAPET_HEIGHT_INVALID"),
        ({"load_capacity_kn_m2": 0}, "ROOF_LOAD_INVALID"),
        ({"keepouts": [{"id": "outside", "label": "屋顶外禁区", "polygon": [[59, 1], [61, 1], [61, 2], [59, 2]]}]}, "KEEPOUT_OUTSIDE_ROOF"),
        ({"obstacles": [{"id": "outside", "label": "屋顶外水箱", "kind": "cylinder", "center": [59, 10], "radius_m": 2, "height_m": 1}]}, "OBSTACLE_OUTSIDE_ROOF"),
        ({"obstacles": [{"id": "bad", "label": "零高水箱", "kind": "cylinder", "center": [10, 10], "radius_m": 1, "height_m": 0}]}, "OBSTACLE_HEIGHT_INVALID"),
    ]
    for roof_update, code in invalid:
        candidate = copy.deepcopy(payload)
        candidate["roof"].update(roof_update)
        with pytest.raises(GzError) as caught:
            validate_project(candidate)
        error = caught.value.as_dict()
        assert error["ok"] is False and error["error_code"] == code
        assert set(error) == {"ok", "error_code", "message_zh", "fix_hint"}
        assert any("\u4e00" <= c <= "\u9fff" for c in error["message_zh"])
        assert any("\u4e00" <= c <= "\u9fff" for c in error["fix_hint"])
    payload["roof"]["outline"].reverse()
    payload["roof"]["obstacles"][0]["footprint"].reverse()
    payload["roof"]["keepouts"][0]["polygon"].reverse()
    roof = validate_project(payload).roof
    assert Polygon(roof.outline).exterior.is_ccw
    assert obstacle_polygon(roof.obstacles[0]).exterior.is_ccw
    assert Polygon(roof.keepouts[0].polygon).exterior.is_ccw
    assert len(obstacle_polygon(roof.obstacles[1]).exterior.coords) == 33


def test_calibration_and_schema(payload):
    calibration = {"p1_px": [10, 20], "p2_px": [310, 420], "distance_m": 50}
    assert px_to_m([[10, 20], [110, 120]], calibration) == [[0, 0], [10, -10]]
    assert px_to_m([[310, 420]], calibration) == [[30, -40]]
    for update in ({"p2_px": [10, 20]}, {"distance_m": 0}):
        with pytest.raises(GzError) as caught:
            px_to_m([[0, 0]], calibration | update)
        assert caught.value.error_code == "CALIBRATION_INVALID"
    params = LayoutParams.model_json_schema()["properties"]
    assert params["tilt_deg"]["minimum"] == 0 and params["tilt_deg"]["exclusiveMaximum"] == 90
    assert params["azimuth_deg"]["minimum"] == 0
    assert params["rows_per_rack"]["maximum"] == 2
    legacy_keys = {"tilt_deg", "azimuth_deg", "orientation", "rows_per_rack", "edge_setback_m", "obstacle_clearance_m",
                   "keepout_clearance_m", "walkway_every_n_rows", "walkway_width_m", "winter_window_hours"}
    assert set(params) == legacy_keys | {"align", "layout", "fill_landscape", "surface", "plane_ids",
                                         'lower_edge_m', 'clear_height_m', 'road_every', 'road_width_m', 'fence_setback_m',
                                         'extra_row_gap_m'}  # T34 grazing: wider aisles between rows
    assert params["align"]["anyOf"] == [{"enum": ["south", "edge"], "type": "string"}, {"type": "null"}]
    assert params["align"]["default"] is None
    assert params["layout"]["enum"] == ["rows", "ew"] and params["layout"]["default"] == "rows"
    assert params["fill_landscape"]["type"] == "boolean" and params["fill_landscape"]["default"] is False
    assert params["surface"]["type"] == "boolean" and params["surface"]["default"] is False
    assert params["plane_ids"]["anyOf"] == [{"items": {"type": "integer"}, "type": "array"}, {"type": "null"}]
    assert params["plane_ids"]["default"] is None
    assert set(LayoutParams().model_dump()) == legacy_keys
    assert set(LayoutParams(align=None, layout="rows", fill_landscape=False).model_dump()) == legacy_keys
    assert LayoutParams(surface=False, plane_ids=None).model_dump() == LayoutParams().model_dump()
    selected = LayoutParams(align="edge", layout="ew", fill_landscape=True).model_dump()
    assert {key: selected[key] for key in ("align", "layout", "fill_landscape")} == {
        "align": "edge", "layout": "ew", "fill_landscape": True}
    surface = LayoutParams(surface=True, plane_ids=[1, 3], tilt_deg=45).model_dump()
    assert {key: surface[key] for key in ("surface", "plane_ids", "tilt_deg")} == {
        "surface": True, "plane_ids": [1, 3], "tilt_deg": 45}
    assert validated(LayoutParams, {"tilt_deg": 35}, "LAYOUT_PARAMS_INVALID").tilt_deg == 35
    legacy_requirements = {'budget_cny_max', 'payback_years_max', 'capacity_kw_min', 'capacity_kw_max', 'walkway_m_min',
                           'obstacle_clearance_m_min', 'edge_setback_m_min', 'keep_clear_ids', 'tilt_deg_range', 'notes'}
    assert set(StructuredRequirements.model_fields) == legacy_requirements | {
        'export_allowed', 'curtail_pct_max', 'transformer_kva', 'transformer_share', 'max_height_m', 'phase1_kw', 'phase1_budget_cny',
        'ballast_only'}  # the owner forbids drilling: flat racks keep their ballast instead of anchors
    assert set(StructuredRequirements().model_dump()) == legacy_requirements
    assert validate_project(payload).model_dump(by_alias=True)["schema"] == "guangzhu.project/1"
    assert Project.model_json_schema()["additionalProperties"] is False
    for update in ({"tilt_deg": 36}, {"azimuth_deg": -1}, {"orientation": "diagonal"}, {"rows_per_rack": 3},
                   {"edge_setback_m": -1}, {"winter_window_hours": [15, 9]}, {"align": "north"}, {"layout": "diagonal"}):
        with pytest.raises(GzError):
            validated(LayoutParams, update, "LAYOUT_PARAMS_INVALID")
    for update in ({"surface": True, "tilt_deg": 90}, {"surface": True, "tilt_deg": -1}, {"plane_ids": []}, {"plane_ids": [0]}):
        with pytest.raises(GzError):
            validated(LayoutParams, update, "LAYOUT_PARAMS_INVALID")


def test_init_storage_and_immutability(payload, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    source = tmp_path / "source"
    source.mkdir()
    (source / "project.json").write_text(json.dumps(payload), encoding="utf-8")
    (source / "underlay.png").write_bytes(b"test-underlay")
    stored = storage.init(source)
    assert storage.load(stored.id) == stored
    assert (tmp_path / "projects" / stored.id / "underlay.png").read_bytes() == b"test-underlay"
    design = Design(params=LayoutParams())
    storage.save_design(stored.id, design)
    path = tmp_path / "projects" / stored.id / "designs/v1.json"
    original = path.read_bytes()
    with pytest.raises(GzError, match="不能覆盖") as caught:
        storage.save_design(stored.id, {"version": 1, "invalid": "field"})
    assert caught.value.error_code == "DESIGN_VERSION_EXISTS"
    assert path.read_bytes() == original and storage.next_version(stored.id) == 2
    assert storage.load(stored.id).designs == ["v1"]
    with pytest.raises(GzError) as caught:
        storage.save_design(stored.id, Design(version=3, params=LayoutParams()))
    assert caught.value.error_code == "DESIGN_VERSION_INVALID"
    for bad in ("../other", "..", "a/b", "a\\b", "", "CON:bad"):
        with pytest.raises(GzError) as caught:
            storage.load(bad)
        assert caught.value.error_code == "PROJECT_ID_INVALID"


def test_demo_init_copies_versions_and_preserves_parent_bytes(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    source = DATA_DIR / "demo/projects/changzhou-demo"
    originals = {version: (source / f"designs/v{version}.json").read_bytes() for version in (1, 2, 3)}
    stored = storage.init(source)
    assert stored.designs == ["v1", "v2", "v3"]
    assert storage.load(stored.id) == stored
    assert storage.next_version(stored.id) == 4
    for version, count in ((1, 390), (2, 376), (3, 375)):
        assert storage._path(stored.id, f"designs/v{version}.json").read_bytes() == originals[version]
        design = storage.load_design(stored.id, version)
        assert design.version == version and len(design.modules) == count
        assert design.parent_version == (version - 1 if version > 1 else None)
    parent = storage.load_design(stored.id, 3)
    result = storage.edit_design(stored.id, 3, [{"op": "remove_modules", "module_ids": [parent.modules[-1].id]}],
                                 "初始化后的独立编辑", "user")
    child = storage.load_design(stored.id, result["version"])
    assert result["version"] == 4 and child.parent_version == 3
    assert len(child.modules) == 374
    assert storage.load(stored.id).designs == ["v1", "v2", "v3", "v4"]
    assert storage.next_version(stored.id) == 5
    for version, contents in originals.items():
        assert storage._path(stored.id, f"designs/v{version}.json").read_bytes() == contents
        assert (source / f"designs/v{version}.json").read_bytes() == contents


def test_init_new_id_starts_without_previous_run_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    source = tmp_path / "source"
    shutil.copytree(DATA_DIR / "demo/projects/changzhou-demo", source)
    for relative in ("analysis/v3/result.json", "reviews/review.json", "exports/report.pdf", "weather.json"):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"previous-run-artifact")
    originals = {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()}
    template = storage._read(source / "project.json", Project)
    legacy = storage.init(source)
    legacy_dir = tmp_path / "projects" / legacy.id
    legacy_originals = {path.relative_to(legacy_dir): path.read_bytes() for path in legacy_dir.rglob("*") if path.is_file()}

    stored = storage.init(source, identifier="changzhou-r2")

    assert stored.id == "changzhou-r2" and stored.designs == []
    assert stored.requirements.text == "" and stored.requirements.structured == StructuredRequirements()
    assert stored.roof == template.roof and stored.site == template.site
    assert stored.equipment == template.equipment and stored.economics == template.economics
    assert storage.load(stored.id) == stored and storage.next_version(stored.id) == 1
    assert sorted(path.relative_to(tmp_path / "projects/changzhou-r2").as_posix()
                  for path in (tmp_path / "projects/changzhou-r2").rglob("*") if path.is_file()) == ["project.json"]
    storage.save_design(stored.id, Design(params=LayoutParams()))
    assert storage.load(stored.id).designs == ["v1"] and storage.next_version(stored.id) == 2
    assert {path.relative_to(legacy_dir): path.read_bytes() for path in legacy_dir.rglob("*") if path.is_file()} == legacy_originals
    assert {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()} == originals


def test_init_new_id_cli_preserves_underlay_and_refuses_overwrite(payload, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    source = tmp_path / "source"
    source.mkdir()
    payload["roof"]["underlay"] = {"image": "underlay.png", "calibration": {
        "p1_px": [0, 0], "p2_px": [100, 0], "distance_m": 10}}
    (source / "project.json").write_text(json.dumps(payload), encoding="utf-8")
    (source / "underlay.png").write_bytes(b"roof-image")
    source_originals = {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()}
    arguments = ["init", "--from", str(source), "--id", "changzhou-r2"]

    assert storage.main(arguments) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "project_id": "changzhou-r2"}
    destination = tmp_path / "projects/changzhou-r2"
    assert (destination / "underlay/underlay.png").read_bytes() == b"roof-image"
    assert storage.load("changzhou-r2").roof.underlay.image == "underlay/underlay.png"
    originals = {path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()}
    assert storage.main(arguments) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "PROJECT_EXISTS"
    assert {path.relative_to(destination): path.read_bytes() for path in destination.rglob("*") if path.is_file()} == originals
    assert {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()} == source_originals
    assert not (tmp_path / "projects/changzhou-demo").exists()


@pytest.mark.parametrize("source_image", ["images/roof.png", "designs/v1.json"])
def test_init_new_id_nested_underlay_stays_out_of_run_directories(source_image, payload, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    source = tmp_path / "source"
    (source / source_image).parent.mkdir(parents=True)
    # File contents are deliberately opaque: the import does not inspect image MIME.
    (source / source_image).write_bytes(b"referenced-underlay")
    payload["designs"] = ["v1"]
    payload["roof"]["underlay"] = {"image": source_image, "calibration": {
        "p1_px": [0, 0], "p2_px": [100, 0], "distance_m": 10}}
    (source / "project.json").write_text(json.dumps(payload), encoding="utf-8")
    source_originals = {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()}

    stored = storage.init(source, identifier="changzhou-r2")

    image = "underlay/" + Path(source_image).name
    assert stored.roof.underlay.image == image
    assert stored.roof.underlay.calibration == validated(Project, payload).roof.underlay.calibration
    assert storage.load(stored.id) == stored and storage.next_version(stored.id) == 1
    destination = tmp_path / "projects/changzhou-r2"
    assert (destination / image).read_bytes() == b"referenced-underlay"
    assert not (destination / "designs").exists() and stored.designs == []
    assert {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()} == source_originals


@pytest.mark.parametrize("identifier", ["../other", "..", "a/b", "a\\b", "", "CON:bad"])
def test_init_new_id_rejects_invalid_identifier(identifier, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    with pytest.raises(GzError) as caught:
        storage.init(DATA_DIR / "demo/projects/changzhou-demo", identifier=identifier)
    assert caught.value.error_code == "PROJECT_ID_INVALID"
    assert not (tmp_path / "projects").exists()


def test_init_new_id_rejects_underlay_outside_source(payload, monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    source = tmp_path / "source"
    source.mkdir()
    (tmp_path / "outside.png").write_bytes(b"outside-image")
    payload["roof"]["underlay"] = {"image": "../outside.png", "calibration": {
        "p1_px": [0, 0], "p2_px": [100, 0], "distance_m": 10}}
    (source / "project.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GzError) as caught:
        storage.init(source, identifier="changzhou-r2")
    assert caught.value.error_code == "PROJECT_INIT_FAILED"
    assert not (tmp_path / "projects/changzhou-r2").exists()


def test_init_new_id_underlay_cannot_overwrite_another_project(payload, monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    monkeypatch.setattr(storage, "PROJECTS_DIR", projects_dir)
    source = tmp_path / "source"
    source.mkdir()
    (source / "underlay.png").write_bytes(b"new-roof-image")
    other_project = projects_dir / "source"
    other_project.mkdir(parents=True)
    old_image = other_project / "underlay.png"
    old_image.write_bytes(b"other-project-image")
    payload["roof"]["underlay"] = {"image": "../source/underlay.png", "calibration": {
        "p1_px": [0, 0], "p2_px": [100, 0], "distance_m": 10}}
    (source / "project.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(GzError) as caught:
        storage.init(source, identifier="changzhou-r2")

    assert caught.value.error_code == "PROJECT_INIT_FAILED"
    assert old_image.read_bytes() == b"other-project-image"
    assert (source / "underlay.png").read_bytes() == b"new-roof-image"
    assert not (projects_dir / "changzhou-r2").exists()


def test_four_edits_create_versions_and_preserve_parent(local_project, tmp_path):
    from guangzhu.layout import generate_layout
    first = generate_layout(local_project, LayoutParams())
    storage.save_design(local_project.id, first)
    original = storage._path(local_project.id, "designs/v1.json").read_bytes()
    removed_id = first.modules[0].id
    result = storage.edit_design(local_project.id, 1, [{"op": "remove_modules", "module_ids": [removed_id]}], "检修位置", "user")
    second = storage.load_design(local_project.id, result["version"])
    assert len(second.modules) == len(first.modules) - 1
    assert second.removed_modules[0].id == removed_id and second.removed_modules[0].reason == "检修位置"
    assert second.parent_version == 1 and "检修位置" in result["summary"]
    result = storage.edit_design(local_project.id, 2, [{"op": "set_string_size", "modules_per_string": 20}], "电气预设", "agent")
    third = storage.load_design(local_project.id, result["version"])
    assert third.modules_per_string == 20 and third.modules == second.modules
    target = third.modules[len(third.modules) // 2]
    polygon = [[p[0], p[1]] for p in target.corners]
    result = storage.edit_design(local_project.id, 3, [{"op": "add_keepout", "polygon": polygon, "label": "检修禁区"}], "留检修位置", "user")
    fourth = storage.load_design(local_project.id, result["version"])
    assert len(fourth.modules) < len(third.modules) and len(fourth.added_keepouts) == 1
    assert all(m in third.modules for m in fourth.modules)
    assert fourth.statistics["module_count"] == len(fourth.modules)
    assert fourth.statistics["usable_area_m2"] < third.statistics["usable_area_m2"]
    result = storage.edit_design(local_project.id, 4, [{"op": "set_param", "name": "tilt_deg", "value": 15}], "调整倾角", "rule")
    fifth = storage.load_design(local_project.id, result["version"])
    assert fifth.params.tilt_deg == 15 and fifth.parent_version == 4
    assert fifth.added_keepouts == fourth.added_keepouts and fifth.modules_per_string == 20
    assert fifth.removed_modules == [] and "删除记录已重置" in result["summary"]
    assert len(storage.load(local_project.id).roof.keepouts) == 1
    assert storage._path(local_project.id, "designs/v1.json").read_bytes() == original


def test_remove_by_obstacle_and_keepout(local_project):
    modules = [Module(id=f"R01-1-C{i:03}", row=1, tier=1, col=i, center=(x + 0.5, y + 0.5, 0.3),
                      corners=((x, y, 0.3), (x + 1, y, 0.3), (x + 1, y + 1, 0.3), (x, y + 1, 0.3)),
                      tilt=0, azimuth=180, orientation="portrait")
               for i, (x, y) in enumerate([(10, 27), (21.5, 5), (30, 5)], 1)]
    storage.save_design(local_project.id, Design(params=LayoutParams(), modules=modules, statistics={"module_count": 3, "dc_kw": 1.65, "module_area_ratio": 0.003}))
    result = storage.edit_design(local_project.id, 1, [{"op": "remove_modules", "where": {"zone_id": "stair-1"}}, {"op": "remove_modules", "where": {"zone_id": "sky-1"}}], "移除区域组件", "rule")
    design = storage.load_design(local_project.id, result["version"])
    assert [m.id for m in design.modules] == [modules[2].id]
    assert len(design.removed_modules) == 2
    assert design.statistics["dc_kw"] == pytest.approx(0.55)
    with pytest.raises(GzError) as caught:
        storage.edit_design(local_project.id, 2, [{"op": "remove_modules", "where": {"shading_loss_gt": 8}}], "损失过高", "agent")
    assert caught.value.error_code == "ANALYSIS_MISSING"
    assert caught.value.fix_hint == "先对该版本运行遮挡分析"
    assert storage.next_version(local_project.id) == 3


@pytest.mark.parametrize('selector', [{'module_ids':['R01-1-C001']}, {'where':{'shading_loss_gt':8}}])
def test_parameter_change_rejects_old_component_dependencies_without_saving(local_project,selector):
    from guangzhu.layout import generate_layout
    storage.save_design(local_project.id,generate_layout(local_project,{}))
    original=storage._path(local_project.id,'designs/v1.json').read_bytes()
    project_bytes=storage._path(local_project.id,'project.json').read_bytes()
    with pytest.raises(GzError) as caught:
        storage.edit_design(local_project.id,1,[{'op':'set_param','name':'tilt_deg','value':20},
                            {'op':'remove_modules',**selector}],'旧组件删除组合','agent')
    assert caught.value.error_code=='DESIGN_EDIT_DEPENDENCY'
    assert caught.value.message_zh=='改参数会重新排板，请先单独改参数并重新分析，再删组件'
    assert storage.next_version(local_project.id)==2
    assert storage._path(local_project.id,'designs/v1.json').read_bytes()==original
    assert storage._path(local_project.id,'project.json').read_bytes()==project_bytes


def test_parameter_change_keeps_zone_and_new_keepout_operations_valid(local_project):
    from guangzhu.layout import generate_layout
    first=generate_layout(local_project,{})
    storage.save_design(local_project.id,first)
    polygon=[list(p[:2]) for p in first.modules[0].corners]
    result=storage.edit_design(local_project.id,1,[{'op':'set_param','name':'tilt_deg','value':15},
             {'op':'add_keepout','polygon':polygon,'label':'新增检修区'},
             {'op':'remove_modules','where':{'zone_id':'sky-1'}},
             {'op':'remove_modules','where':{'zone_id':'edit-v2-2'}}],'调整并保持禁区','agent')
    design=storage.load_design(local_project.id,result['version'])
    assert design.version==2 and design.parent_version==1 and design.params.tilt_deg==15
    assert len(design.added_keepouts)==1 and design.added_keepouts[0].id=='edit-v2-2'
