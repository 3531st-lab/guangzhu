"""Generation-model checks use committed real weather and PVGIS recordings."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import pytest
import requests

from guangzhu import catalog, solar, weather, yieldsim
from guangzhu.catalog import load_cec_equipment


LAT, LON, YEAR = 31.81, 119.97, 2023
FIXTURE = Path(__file__).parent / "fixtures" / "pvgis_pvcalc.json"


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(weather, "CACHE_DIR", tmp_path / "weather-cache")
    monkeypatch.setattr(yieldsim, "CACHE_DIR", tmp_path / "yield-cache")
    def unexpected_request(*args, **kwargs):
        pytest.fail("An offline yield test attempted a live network request.")
    monkeypatch.setattr(requests.Session, "request", unexpected_request)


@pytest.fixture
def demo_weather() -> pd.DataFrame:
    df, meta = weather.load_nasa_hourly(LAT, LON, YEAR, offline=True)
    assert meta["used"] == "demo"
    return df


@pytest.fixture
def equipment():
    return load_cec_equipment(offline=True)


@pytest.fixture
def pvgis_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_simple_and_pysam_use_identical_weather_within_five_percent(demo_weather):
    simplified = yieldsim.simulate_pvlib_simple(demo_weather, LAT, LON)
    independent = yieldsim.simulate_pysam(demo_weather, LAT, LON)
    assert abs(simplified["annual_kwh"] - independent["annual_kwh"]) / independent["annual_kwh"] < 0.05
    for result in (simplified, independent):
        assert len(result["monthly_kwh"]) == 12
        assert sum(result["monthly_kwh"]) == pytest.approx(result["annual_kwh"])
        assert result["specific_yield_kwh_kwp"] == result["annual_kwh"]
    assert simplified["metadata"]["inverter_pdc0_w"] == pytest.approx(1000 / 1.2 / 0.96)
    assert independent["metadata"]["timezone_hours"] == 0
    assert independent["metadata"]["minute"] == 30


def test_detailed_runs_real_array_then_normalizes(demo_weather, equipment):
    result = yieldsim.simulate_pvlib_detailed(demo_weather, LAT, LON, equipment=equipment)
    module, inverter, catalog = equipment
    meta = result["metadata"]
    assert meta["array_dc_capacity_kw"] == pytest.approx(module.STC * catalog["series"] * catalog["parallel"] / 1000)
    assert meta["array_dc_capacity_kw"] == pytest.approx(72.6)
    assert meta["array_ac_rating_kw"] == pytest.approx(inverter.Paco / 1000)
    assert meta["noct_c"] == module.T_NOCT == 45.7
    assert result["annual_kwh"] == pytest.approx(meta["array_annual_generated_kwh"] / 72.6)
    assert len(result["monthly_kwh"]) == 12


@pytest.mark.parametrize("chain", ["a", "b", "c"])
def test_full_year_zero_irradiance_generates_zero(chain, demo_weather, equipment):
    dark = demo_weather.copy()
    dark.loc[:, ["ghi", "dni", "dhi"]] = 0
    if chain == "a":
        result = yieldsim.simulate_pvlib_simple(dark, LAT, LON)
    elif chain == "b":
        result = yieldsim.simulate_pvlib_detailed(dark, LAT, LON, equipment=equipment)
    else:
        result = yieldsim.simulate_pysam(dark, LAT, LON)
    assert result["monthly_kwh"] == [0] * 12
    assert result["annual_kwh"] == result["specific_yield_kwh_kwp"] == 0


def test_monthly_aggregation_retains_utc_boundaries_and_clips_consumption():
    times = pd.DatetimeIndex(["2023-01-31T22:00Z", "2023-01-31T23:00Z", "2023-02-01T00:00Z"])
    result = yieldsim._summary([-20, 1000, 2000], times, {})
    assert result["monthly_kwh"][:2] == [1, 2]
    assert result["annual_kwh"] == 3
    assert result["metadata"]["aggregation_timezone"] == "UTC"


def test_pysam_resource_keeps_complete_utc_year_and_middle_of_hour(demo_weather, monkeypatch):
    def group():
        result = SimpleNamespace()
        result.assign = lambda values: result.__dict__.update(values)
        return result
    model = SimpleNamespace(SolarResource=group(), SystemDesign=group(), Shading=group(),
              AdjustmentFactors=group(), Lifetime=group(), Outputs=SimpleNamespace(ac=np.zeros(8760)), execute=lambda: None)
    monkeypatch.setattr(yieldsim, "_pysam_module", lambda: SimpleNamespace(default=lambda name: model))
    yieldsim.simulate_pysam(demo_weather, LAT, LON)
    resource = model.SolarResource.solar_resource_data
    assert resource["tz"] == 0 and set(resource["year"]) == {2023}
    assert len(resource["gh"]) == 8760 and set(resource["minute"]) == {30}
    assert (resource["month"][0], resource["day"][0], resource["hour"][0]) == (1, 1, 0)
    assert (resource["month"][-1], resource["day"][-1], resource["hour"][-1]) == (12, 31, 23)
    assert model.SystemDesign.losses == 14 and model.SystemDesign.system_capacity == 1


def test_pysam_rejects_partial_year_before_native_execution(demo_weather):
    with pytest.raises(ValueError, match="complete UTC calendar year"):
        yieldsim.simulate_pysam(demo_weather.iloc[:48], LAT, LON)


@pytest.mark.parametrize("chain", ["a", "b"])
def test_nonfinite_daytime_poa_is_a_hard_error(chain, demo_weather, equipment, monkeypatch):
    original = solar.poa_irradiance
    def invalid_poa(*args, **kwargs):
        result = original(*args, **kwargs)
        result.loc[result.poa_global.idxmax(), "poa_global"] = np.nan
        return result
    monkeypatch.setattr(solar, "poa_irradiance", invalid_poa)
    with pytest.raises(ValueError, match="nonfinite"):
        if chain == "a":
            yieldsim.simulate_pvlib_simple(demo_weather, LAT, LON)
        else:
            yieldsim.simulate_pvlib_detailed(demo_weather, LAT, LON, equipment=equipment)


def test_real_pvgis_recording_and_offline_demo():
    result = yieldsim.load_pvgis_result(LAT, LON, offline=True)
    assert result["metadata"]["used"] == "demo"
    assert result["annual_kwh"] == 1275.11
    assert len(result["monthly_kwh"]) == 12
    assert result["monthly_kwh"][0] == 98.07
    assert result["metadata"]["pvgis_inputs"]["meteo_data"]["radiation_db"] == "PVGIS-ERA5"
    assert result["metadata"]["data_file_sha256"]
    assert result["metadata"]["request_url"].startswith(yieldsim.PVGIS_URL)


def test_pvgis_download_request_parameters_then_cache(pvgis_payload, monkeypatch):
    urls = []
    def download(url):
        urls.append(url)
        return pvgis_payload
    monkeypatch.setattr(yieldsim, "_download_pvgis", download)
    first = yieldsim.load_pvgis_result(LAT, LON)
    second = yieldsim.load_pvgis_result(LAT, LON)
    assert first["metadata"]["used"] == "download" and second["metadata"]["used"] == "cache"
    assert len(urls) == 1
    query = parse_qs(urlparse(urls[0]).query)
    assert query["raddatabase"] == ["PVGIS-ERA5"] and query["peakpower"] == ["1"]
    assert query["loss"] == ["14.0"] and query["angle"] == ["25"] and query["aspect"] == ["0"]
    assert second["annual_kwh"] == first["annual_kwh"]


@pytest.mark.parametrize("lat,tilt", [(LAT + 1, 25), (LAT, 30)])
def test_pvgis_demo_never_substitutes_another_site_or_orientation(lat, tilt):
    with pytest.raises(ValueError, match="exact-site/orientation"):
        yieldsim.load_pvgis_result(lat, LON, tilt=tilt, offline=True)


def test_pvgis_corrupt_cache_uses_verified_same_site_demo(pvgis_payload, monkeypatch):
    monkeypatch.setattr(yieldsim, "_download_pvgis", lambda url: pvgis_payload)
    result = yieldsim.load_pvgis_result(LAT, LON)
    (yieldsim.CACHE_DIR / result["metadata"]["data_file"]).write_bytes(b"corrupt recorded response")
    returned = yieldsim.load_pvgis_result(LAT, LON, offline=True)
    assert returned["metadata"]["used"] == "demo" and returned["annual_kwh"] == 1275.11


def test_pvgis_requires_twelve_unique_months(pvgis_payload):
    changed = copy.deepcopy(pvgis_payload)
    changed["outputs"]["monthly"]["fixed"].pop()
    with pytest.raises(ValueError, match="Malformed"):
        yieldsim._parse_pvgis_result(changed, {})


@pytest.mark.parametrize('failure',[requests.Timeout,requests.ConnectionError])
def test_online_pvgis_failure_keeps_four_local_chains(failure,monkeypatch,tmp_path):
    def unavailable(*args,**kwargs):
        raise failure('simulated unavailable source')
    monkeypatch.setattr(yieldsim,'_download_pvgis',unavailable)
    monkeypatch.setattr(weather,'_download_json',unavailable)
    monkeypatch.setattr(catalog,'CACHE_DIR',tmp_path/'cec-cache')
    monkeypatch.setattr(catalog,'_download_bytes',unavailable)
    with pytest.raises(yieldsim.MissingPVGISResult):
        yieldsim.load_pvgis_result(LAT,LON,tilt=20,offline=False)
    result=yieldsim.simulate_design_yields(LAT,LON,tilt=20,azimuth=180,loss_percent=14,offline=False)
    assert set(result['results'])=={'a','b','c','b_tmy'}
    assert set(result['omitted'])=={'d'} and '缺PVGIS' in result['omitted']['d']
    assert result['results']['b']['annual_kwh']>0


def test_pvgis_request_budget_fits_agh_call(monkeypatch):
    calls=[]
    def get(url,**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'recorded':True})
    monkeypatch.setattr(requests,'get',get)
    assert yieldsim._download_pvgis('https://example.invalid/recorded')=={'recorded':True}
    assert calls==[{'timeout':(3,15)}]


def test_cli_crosscheck_is_reproducible_offline(tmp_path, capsys):
    figure = tmp_path / "comparison.png"
    code = yieldsim.main(["crosscheck", "--lat", str(LAT), "--lon", str(LON), "--year", str(YEAR),
                          "--tilt", "25", "--azimuth", "180", "--offline", "--figure", str(figure)])
    assert code == 0
    result = json.loads(capsys.readouterr().out)
    assert set(result["results"]) == {"a", "b", "c", "d"}
    assert len(result["pairwise_differences"]) == 6
    assert result["elapsed_compute_seconds"] > 0
    assert '"hourly"' not in json.dumps(result)
    assert figure.is_file() and figure.read_bytes().startswith(b"\x89PNG")
    assert result["results"]["d"]["metadata"]["used"] == "demo"
