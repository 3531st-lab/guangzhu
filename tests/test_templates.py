"""T12 shared catalog boundaries and prefetch use isolated templates and fake loaders."""
import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from guangzhu import api, brief, mcp_actions, project as storage, templates
from guangzhu.config import ROOT
from guangzhu.models import GzError, Project


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    raw = json.loads((ROOT / "data/demo/projects/changzhou-demo/project.json").read_text(encoding="utf-8"))
    records = {}
    for identifier, collection in [("changzhou-demo", None), ("l-shape", None), ("rotated", None),
                                   ("eval-real", "real"), ("eval-boundary", "boundary"), ("eval-impossible", "impossible")]:
        record = dict(raw, id=identifier)
        if collection:
            record["collection"] = collection
            record["site"] = dict(raw["site"], lat=31.8, lon=119.98)
        directory = tmp_path / ("data/roofs" if collection else "data/demo/projects") / identifier
        directory.mkdir(parents=True)
        (directory / "project.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        records[identifier] = record
    for module in (api, brief, mcp_actions):
        monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    return tmp_path, records


def test_default_catalog_and_api_hide_evaluation_only_roofs_but_all_resolves_them(isolated):
    root, records = isolated
    public_ids = ["changzhou-demo", "l-shape", "rotated", "eval-real"]
    assert list(templates.catalog(root=root)) == public_ids
    assert set(templates.catalog(all=True, root=root)) == set(records)
    client = TestClient(api.app)
    public = client.get("/api/roofs").json()["roofs"]
    assert [row["id"] for row in public] == public_ids
    assert [row["collection"] for row in public] == ["demo", "demo", "demo", "real"]
    assert {row["id"] for row in client.get("/api/roofs?all=1").json()["roofs"]} == set(records)
    for identifier, record in records.items():
        assert json.loads(templates.resolve(identifier, root=root).read_text(encoding="utf-8")) == record
        assert Project.model_validate(record).collection == record.get("collection")


@pytest.mark.parametrize("collection", ["real", "boundary", "impossible"])
def test_brief_and_mcp_can_create_evaluation_roofs_with_complete_original_geometry(isolated, collection):
    root, records = isolated
    identifier = "eval-" + collection
    record = records[identifier]
    selected = brief.BriefSpec(template=identifier, id="new-" + collection, text="留检修通道",
                               structured={"keep_clear_ids": [record["roof"]["keepouts"][0]["id"]]})
    assert identifier in brief.render_brief(selected)
    result = mcp_actions._new_project(selected.id, selected.template)
    created = storage.load(result["project_id"])
    assert created.collection == collection
    assert created.roof == Project.model_validate(record).roof
    assert created.designs == [] and created.requirements.text == ""
    assert sorted(path.name for path in storage._path(created.id).iterdir()) == ["project.json"]


def test_duplicate_ids_fail_before_public_filtering_or_any_project_write(isolated):
    root, _ = isolated
    duplicate = root / "data/roofs/changzhou-demo/project.json"
    duplicate.parent.mkdir()
    duplicate.write_text('{"collection":"impossible"}', encoding="utf-8")
    for lookup in (lambda: templates.catalog(root=root), lambda: templates.catalog(all=True, root=root),
                   lambda: templates.resolve("eval-real", root=root),
                   lambda: mcp_actions._new_project("duplicate-target", "eval-real")):
        with pytest.raises(GzError) as error:
            lookup()
        assert error.value.error_code == "TEMPLATE_DUPLICATE"
    assert TestClient(api.app).get("/api/roofs").status_code == 400
    assert not (root / "projects").exists()


def test_collection_rejects_unknown_values_and_lookup_rejects_path_traversal(isolated):
    root, records = isolated
    with pytest.raises(ValidationError):
        Project.model_validate(dict(records["eval-real"], collection="secret"))
    with pytest.raises(GzError) as error:
        templates.resolve("../eval-real", root=root)
    assert error.value.error_code == "PROJECT_ID_INVALID"


def test_build_keeps_legacy_ids_and_includes_hidden_templates_for_native_brief_cards(isolated, monkeypatch):
    root, records = isolated
    builder = script("build_agh_plugin")
    monkeypatch.setattr(builder, "ROOT", root)
    rows = builder.make_data()["templates"]
    assert [row["id"] for row in rows[:3]] == ["changzhou-demo", "l-shape", "rotated"]
    assert {row["id"] for row in rows} == set(records)
    assert next(row for row in rows if row["id"] == "eval-real")["outline"] == records["eval-real"]["roof"]["outline"]
    duplicate = root / "data/roofs/rotated/project.json"
    duplicate.parent.mkdir()
    duplicate.write_text("{}", encoding="utf-8")
    with pytest.raises(GzError):
        builder.make_data()


def test_prefetch_reads_all_collections_and_deduplicates_each_site_and_angle(isolated, monkeypatch):
    root, _ = isolated
    prefetch = script("pvgis_prefetch")
    monkeypatch.setattr(prefetch, "ROOT", root)
    calls = []

    def hourly(lat, lon, year, *, offline):
        calls.append(("nasa", lat, lon, year, offline))
        return None, {"source": "nasa"}

    def tmy(lat, lon, *, offline):
        calls.append(("tmy", lat, lon, offline))
        return None, {"source": "tmy"}

    def extremes(lat, lon, *, start_year, end_year, offline):
        calls.append(("extremes", lat, lon, start_year, end_year, offline))
        return {"metadata": {"source": "daily"}}

    def yield_result(lat, lon, *, tilt, azimuth, loss, offline):
        calls.append(("yield", lat, lon, tilt, azimuth, loss, offline))
        return {"annual_kwh": 1000, "metadata": {"source": "pvgis"}}

    monkeypatch.setattr(prefetch.weather, "load_nasa_hourly", hourly)
    monkeypatch.setattr(prefetch.weather, "load_pvgis_tmy", tmy)
    monkeypatch.setattr(prefetch.weather, "load_nasa_daily_extremes", extremes)
    monkeypatch.setattr(prefetch.yieldsim, "load_pvgis_result", yield_result)
    result = prefetch.prefetch(offline=True)
    assert result["model_requests"] == 0 and result["agh_modified"] is False
    assert len(result["weather"]) == 2 and len(result["records"]) == 16
    assert {row["tilt"] for row in result["records"]} == set(range(0, 36, 5))
    assert len(calls) == len(set(calls)) == 22
    assert all(call[-1] is True for call in calls)
    assert all(call[3] == 2023 for call in calls if call[0] == "nasa")
    assert all(call[3:5] == (1996, 2025) for call in calls if call[0] == "extremes")


def test_smoke_accepts_a_hidden_template_and_copies_it_to_owned_scratch(isolated, monkeypatch):
    root, records = isolated
    smoke = script("mcp_smoke")
    monkeypatch.setattr(smoke, "ROOT", root)
    copied = []

    async def fake_run(projects, **kwargs):
        copied.append(json.loads((projects / "eval-impossible/project.json").read_text(encoding="utf-8")))
        return {"tools": [], "handshake_seconds": 0}

    monkeypatch.setattr(smoke, "run", fake_run)
    assert smoke.main(["--project", "eval-impossible", "--handshakes", "1"]) == 0
    assert copied == [records["eval-impossible"]]
    assert not list((root / ".pytest_cache").glob("t10-stdio-*"))
