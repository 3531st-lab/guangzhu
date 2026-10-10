"""Custom API captures retain the CLI defaults and remain under runs/."""
from pathlib import Path
import pytest

from scripts import agh_export_run as exporter


@pytest.fixture
def export_stub(tmp_path, monkeypatch):
    monkeypatch.setenv("AGH_HOME", "never-created")
    fixture = Path(__file__).parent / "fixtures/ledger/合成-完整.agnes.jsonl"
    called = []
    def ledger(session, path, executable, **kw):
        called.append(session)
        path.write_bytes(fixture.read_bytes())
        return exporter.read_events(path)
    monkeypatch.setattr(exporter, "export_ledger", ledger)
    return tmp_path, called


def test_explicit_nested_destination_and_max_project_id(export_stub):
    root, called = export_stub
    project = "x" * 64
    destination = root / "runs" / ("gz-" + project) / "captures/first"
    result = exporter.export_run("session", project, "gz-" + project, root=root, destination=destination, with_children=True)
    assert result == destination and (result / "run.json").is_file()
    with pytest.raises(FileExistsError):
        exporter.export_run("session", project, "gz-" + project, root=root, destination=destination)
    assert called == ["session"]


@pytest.mark.parametrize("destination", ["../escape", "../../escape", "outside-absolute"])
def test_destination_cannot_escape_runs(export_stub, destination):
    root, called = export_stub
    destination = root / "outside" if destination == "outside-absolute" else destination
    with pytest.raises(ValueError, match="目录"):
        exporter.export_run("session", "project", "gz-project", root=root, destination=destination)
    assert called == [] and not (root / "outside").exists()


def test_default_cli_still_rejects_long_run_id(export_stub):
    root, called = export_stub
    with pytest.raises(ValueError, match="64"):
        exporter.export_run("session", "project", "x" * 65, root=root)
    assert called == []
