"""Real offline installation smoke and cleanup failure behavior."""
import pytest
import requests
from guangzhu import analysis, project as storage
from guangzhu.selfcheck import offline_analysis


@pytest.mark.parametrize("failure", [None, "analysis failed"])
def test_offline_analysis_cleans_only_owned_project(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path)
    existing = tmp_path / "user-project"
    existing.mkdir()
    (existing / "keep").write_text("user data", encoding="utf-8")
    def forbidden(*args, **kwargs):
        pytest.fail("offline installation check attempted a network request")
    monkeypatch.setattr(requests.Session, "request", forbidden)
    if failure:
        def fail(*args, **kwargs):
            raise RuntimeError(failure)
        monkeypatch.setattr(analysis, "analyze", fail)
    result = offline_analysis()
    assert result["passed"] is (failure is None)
    if failure:
        assert "analysis failed" in result["failures"][0]
    else:
        assert result["summary"]["ok"] and result["pysam_kwh"] > 0
    assert list(tmp_path.iterdir()) == [existing]
    assert (existing / "keep").read_text(encoding="utf-8") == "user data"


def test_offline_analysis_cleans_partial_initialization(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path)
    def fail(source, identifier):
        (tmp_path / identifier).mkdir()
        raise OSError("initialization failed")
    monkeypatch.setattr(storage, "init", fail)
    result = offline_analysis()
    assert not result["passed"] and "initialization failed" in result["failures"][0]
    assert not list(tmp_path.iterdir())
