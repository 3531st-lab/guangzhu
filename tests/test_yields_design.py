"""Design loss and weather comparisons use recorded real inputs, without network."""

from __future__ import annotations

import hashlib
import json
import math
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from guangzhu import weather, yieldsim
from guangzhu.config import ROOT


LAT, LON = 31.81, 119.97
DESIGN_LOSS = 100 * (1 - math.prod(1 - value / 100 for value in [2, 0, 2, 2, .5, 1.5, 1, 0, 3]))
GOLDEN = ROOT / "reports" / "assets" / "T03-crosscheck.json"
GOLDEN_SHA256 = "94b1373bb5752ea5bfc46fc2b55102bc4db7dcd488f6180e052374983a17a326"


@pytest.fixture(autouse=True)
def no_network_or_machine_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(weather, "CACHE_DIR", tmp_path / "weather-cache")
    monkeypatch.setattr(yieldsim, "CACHE_DIR", tmp_path / "yield-cache")
    def unexpected_request(*args, **kwargs):
        pytest.fail("A design yield test attempted a live network request.")
    monkeypatch.setattr(requests.Session, "request", unexpected_request)


def design_result():
    return yieldsim.simulate_design_yields(LAT, LON, tilt=25, azimuth=180,
                                           loss_percent=DESIGN_LOSS, offline=True)


def test_default_14_crosscheck_exactly_matches_locked_t03(tmp_path):
    recorded = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = yieldsim.crosscheck(LAT, LON, 2023, offline=True, figure_path=tmp_path / "monthly.png")
    for key in ("a", "b", "c", "d"):
        assert actual["results"][key]["annual_kwh"] == recorded["results"][key]["annual_kwh"]
        assert actual["results"][key]["monthly_kwh"] == recorded["results"][key]["monthly_kwh"]
        assert actual["results"][key]["metadata"]["loss_percent"] == 14
    assert hashlib.sha256(GOLDEN.read_bytes()).hexdigest() == GOLDEN_SHA256


def test_design_uses_one_loss_and_distinguishes_weather_from_model():
    result = design_result()
    expected = {"a": 1144.3132004740964, "b": 1171.3572461345543, "c": 1150.268323575136,
                "b_tmy": 1363.317908698877, "d": 1313.39}
    assert set(result["results"]) == set(expected)
    assert result["omitted"] == {}
    for key, specific_yield in expected.items():
        item = result["results"][key]
        assert item["specific_yield_kwh_kwp"] == specific_yield
        assert item["metadata"]["loss_percent"] == DESIGN_LOSS
        assert len(item["monthly_kwh"]) == 12
    assert result["weather_metadata"]["nasa"]["year"] == 2023
    tmy_meta = result["weather_metadata"]["pvgis_tmy"]
    assert tmy_meta["source"] == "pvgis" and len(tmy_meta["months_selected"]) == 12
    assert result["results"]["b"]["metadata"]["model"] == result["results"]["b_tmy"]["metadata"]["model"]
    assert result["results"]["b"]["metadata"]["weather_source"] == "NASA POWER 2023"
    assert result["results"]["b_tmy"]["metadata"]["weather_source"] == "PVGIS ERA5 TMY"
    assert "reference array inverter" in result["comparison_metadata"]["inverter_approximation"]


def test_design_pvgis_record_matches_committed_v3_and_uses_separate_loss_key(monkeypatch):
    design_file = "data/demo/projects/changzhou-demo/designs/v3.json"
    params = json.loads((ROOT / design_file).read_text(encoding="utf-8"))["params"]
    result = yieldsim.load_pvgis_result(LAT, LON, tilt=params["tilt_deg"], azimuth=params["azimuth_deg"],
                                      loss=DESIGN_LOSS, offline=True)
    meta = result["metadata"]
    assert meta["used"] == "demo" and meta["design_version"] == 3
    assert meta["design_file"] == design_file
    assert "_loss11.418206895118011" in meta["data_file"]
    assert result["metadata"]["pvgis_inputs"]["pv_module"]["system_loss"] == DESIGN_LOSS
    query = parse_qs(urlparse(meta["request_url"]).query)
    assert float(query["loss"][0]) == DESIGN_LOSS
    assert float(query["angle"][0]) == params["tilt_deg"] and float(query["aspect"][0]) == params["azimuth_deg"] - 180
    payload = json.loads((yieldsim.DEMO_DIR / meta["data_file"]).read_text(encoding="utf-8"))
    urls = []
    def download(url):
        urls.append(url)
        return payload
    monkeypatch.setattr(yieldsim, "_download_pvgis", download)
    downloaded = yieldsim.load_pvgis_result(LAT, LON, loss=DESIGN_LOSS)
    assert float(parse_qs(urlparse(urls[0]).query)["loss"][0]) == DESIGN_LOSS
    assert downloaded["annual_kwh"] == result["annual_kwh"]
    assert yieldsim.load_pvgis_result(LAT, LON, offline=True)["annual_kwh"] == 1275.11


def test_offline_missing_d_is_explicitly_omitted(monkeypatch, tmp_path):
    monkeypatch.setattr(yieldsim, "DEMO_DIR", tmp_path / "empty-demo")
    result = design_result()
    assert set(result["results"]) == {"a", "b", "c", "b_tmy"}
    assert "No matching PVGIS result" in result["omitted"]["d"]


def test_corrupt_d_without_verified_fallback_is_a_hard_error(monkeypatch, tmp_path):
    monkeypatch.setattr(yieldsim, "DEMO_DIR", tmp_path / "empty-demo")
    yieldsim.CACHE_DIR.mkdir()
    key = yieldsim._pvgis_key(LAT, LON, 25, 180, DESIGN_LOSS)
    (yieldsim.CACHE_DIR / (key + ".json")).write_bytes(b"corrupt PVGIS response")
    with pytest.raises(ValueError, match="cached calculation is invalid") as error:
        design_result()
    assert not isinstance(error.value, yieldsim.MissingPVGISResult)


@pytest.mark.parametrize("loss", [float("nan"), -1, 100])
def test_design_rejects_invalid_system_loss(loss):
    with pytest.raises(ValueError, match="System loss"):
        yieldsim.simulate_design_yields(LAT, LON, tilt=25, azimuth=180, loss_percent=loss, offline=True)
