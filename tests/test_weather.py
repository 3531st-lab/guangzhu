"""Weather adapters are tested with recorded official responses and no network."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import pytest
import requests

from guangzhu import weather

DOWNLOAD_JSON = weather._download_json  # Retain the real adapter before the no-network fixture replaces it.


FIXTURES = Path(__file__).parent / "fixtures"
LAT, LON, YEAR = 31.81, 119.97, 2023


@pytest.fixture
def nasa_payload() -> dict:
    return json.loads((FIXTURES / "nasa_48h.json").read_text(encoding="utf-8"))


@pytest.fixture
def pvgis_payload() -> dict:
    return json.loads((FIXTURES / "pvgis_48h.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request) -> None:
    monkeypatch.setattr(weather, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(weather, "DEMO_DIR", tmp_path / "demo")
    if request.node.get_closest_marker("network") is None:
        def disconnected(url: str):
            raise requests.ConnectionError("simulated disconnected network")
        def unexpected_network(*args, **kwargs):
            pytest.fail("An unmarked weather test attempted a real network request.")
        monkeypatch.setattr(requests.Session, "request", unexpected_network)
        monkeypatch.setattr(weather, "_download_json", disconnected)


def save_sample(source: str, payload: dict, directory: Path, *, lat=LAT, lon=LON, year=None):
    year = (YEAR if source == "nasa" else weather.TMY_YEAR) if year is None else year
    df = weather._parse_nasa_payload(payload) if source == "nasa" else weather._parse_pvgis_payload(payload)
    meta = weather._metadata(source, lat, lon, year, df, "https://example.invalid/recorded-response", payload)
    result = weather._write_dataset(directory, weather._cache_key(source, lat, lon, year), df, meta)
    return df, result


def test_nasa_parses_recorded_values_and_utc(nasa_payload: dict) -> None:
    df = weather._parse_nasa_payload(nasa_payload)
    assert len(df) == 48 and list(df.columns) == weather.COLUMNS
    assert str(df.index.tz) == "UTC"
    assert df.index[0] == pd.Timestamp("2023-01-01T00:00:00Z")
    assert (df.index.to_series().diff().iloc[1:] == pd.Timedelta(hours=1)).all()
    assert df.attrs["hour_midpoint_offset_minutes"] == 30
    raw = nasa_payload["properties"]["parameter"]
    for original, normalized in weather.NASA_PARAMETERS.items():
        assert df.iloc[0][normalized] == raw[original]["2023010100"]


@pytest.mark.parametrize("source", ["nasa", "pvgis"])
def test_fill_value_becomes_missing(source: str, nasa_payload: dict, pvgis_payload: dict) -> None:
    payload = copy.deepcopy(nasa_payload if source == "nasa" else pvgis_payload)
    if source == "nasa":
        for name in weather.NASA_PARAMETERS:
            values = payload["properties"]["parameter"][name]
            values[next(iter(values))] = -999
        df = weather._parse_nasa_payload(payload)
    else:
        for name in weather.PVGIS_PARAMETERS:
            payload["outputs"]["tmy_hourly"][0][name] = -999
        df = weather._parse_pvgis_payload(payload)
    assert df.isna().sum().to_dict() == {column: 1 for column in weather.COLUMNS}
    assert not (df == -999).any().any()


def test_nasa_rejects_local_solar_time(nasa_payload: dict) -> None:
    payload = copy.deepcopy(nasa_payload)
    payload["header"]["time_standard"] = "LST"
    with pytest.raises(weather.WeatherDataError, match="UTC"):
        weather._parse_nasa_payload(payload)


def test_pvgis_normalizes_year_preserves_offset_and_original_months(pvgis_payload: dict) -> None:
    df = weather._parse_pvgis_payload(pvgis_payload)
    assert len(df) == 48 and list(df.columns) == weather.COLUMNS
    assert str(df.index.tz) == "UTC"
    assert df.index[0] == pd.Timestamp("1990-01-01T00:00:00Z")
    assert set(df.index.year) == {1990}
    assert df.iloc[0].to_dict() == pytest.approx({"ghi": 37.1, "dni": 0, "dhi": 37.1, "temp_air": 4.22, "wind_speed": 2.69})
    meta = weather._metadata("pvgis", LAT, LON, 1990, df, "recorded", pvgis_payload)
    assert meta["months_selected"] == pvgis_payload["outputs"]["months_selected"]
    assert meta["irradiance_time_offset"] == 0.5
    assert df.attrs["hour_midpoint_offset_minutes"] == 30


def test_download_then_cache_never_calls_network_again(nasa_payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def download(url: str):
        calls.append(url)
        return nasa_payload
    monkeypatch.setattr(weather, "_download_json", download)
    first, meta = weather.load_nasa_hourly(LAT, LON, YEAR)
    assert meta["used"] == "download" and len(calls) == 1
    query = parse_qs(urlparse(calls[0]).query)
    assert query["time-standard"] == ["UTC"] and query["community"] == ["RE"]
    assert query["format"] == ["JSON"]
    assert query["parameters"] == [",".join(weather.NASA_PARAMETERS)]
    second, cache_meta = weather.load_nasa_hourly(LAT, LON, YEAR)
    assert cache_meta["used"] == "cache" and len(calls) == 1
    pd.testing.assert_frame_equal(first, second, check_freq=False)
    assert second.attrs["hour_midpoint_offset_minutes"] == 30
    contents = (weather.CACHE_DIR / meta["data_file"]).read_bytes()
    assert hashlib.sha256(contents).hexdigest() == meta["data_file_sha256"]
    assert cache_meta["download_time"] == meta["download_time"]


def test_pvgis_requests_era5_and_roundtrips_metadata(pvgis_payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    urls = []
    def download(url: str):
        urls.append(url)
        return pvgis_payload
    monkeypatch.setattr(weather, "_download_json", download)
    df, meta = weather.load_pvgis_tmy(LAT, LON)
    assert parse_qs(urlparse(urls[0]).query)["raddatabase"] == ["PVGIS-ERA5"]
    cached, cached_meta = weather.load_pvgis_tmy(LAT, LON, offline=True)
    pd.testing.assert_frame_equal(df, cached, check_freq=False)
    assert cached_meta["months_selected"] == meta["months_selected"]
    assert cached_meta["used"] == "cache" and cached.attrs["hour_midpoint_offset_minutes"] == 30


@pytest.mark.parametrize("offline", [False, True])
@pytest.mark.parametrize("source", ["nasa", "pvgis"])
def test_disconnected_or_offline_uses_exact_demo(source: str, offline: bool, nasa_payload: dict, pvgis_payload: dict) -> None:
    payload = nasa_payload if source == "nasa" else pvgis_payload
    expected, meta = save_sample(source, payload, weather.DEMO_DIR)
    if source == "nasa":
        actual, returned = weather.load_nasa_hourly(LAT, LON, YEAR, offline=offline)
    else:
        actual, returned = weather.load_pvgis_tmy(LAT, LON, offline=offline)
    pd.testing.assert_frame_equal(expected, actual, check_freq=False)
    assert returned["used"] == "demo" and returned["data_file_sha256"] == meta["data_file_sha256"]
    assert actual.attrs["hour_midpoint_offset_minutes"] == 30


def test_cache_precedes_demo(nasa_payload: dict) -> None:
    save_sample("nasa", nasa_payload, weather.CACHE_DIR)
    save_sample("nasa", nasa_payload, weather.DEMO_DIR)
    _, meta = weather.load_nasa_hourly(LAT, LON, YEAR, offline=True)
    assert meta["used"] == "cache"


def test_offline_never_attempts_network(nasa_payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    save_sample("nasa", nasa_payload, weather.DEMO_DIR)
    def unexpected_download(url: str):
        pytest.fail("Offline loading attempted a download.")
    monkeypatch.setattr(weather, "_download_json", unexpected_download)
    _, meta = weather.load_nasa_hourly(LAT, LON, YEAR, offline=True)
    assert meta["used"] == "demo"


@pytest.mark.parametrize("lat,year", [(LAT + 1, YEAR), (LAT, YEAR + 1)])
def test_demo_never_substitutes_other_site_or_year(lat: float, year: int, nasa_payload: dict) -> None:
    save_sample("nasa", nasa_payload, weather.DEMO_DIR)
    with pytest.raises(weather.WeatherDataError, match="no matching site/year"):
        weather.load_nasa_hourly(lat, LON, year, offline=True)


def test_corrupt_cache_falls_back_to_verified_demo(nasa_payload: dict) -> None:
    _, meta = save_sample("nasa", nasa_payload, weather.CACHE_DIR)
    save_sample("nasa", nasa_payload, weather.DEMO_DIR)
    (weather.CACHE_DIR / meta["data_file"]).write_bytes(b"corrupted compressed dataset")
    _, returned = weather.load_nasa_hourly(LAT, LON, YEAR, offline=True)
    assert returned["used"] == "demo" and "checksum" in returned["fallback_reason"]


def test_demo_metadata_must_match_requested_key(nasa_payload: dict) -> None:
    df, meta = save_sample("nasa", nasa_payload, weather.DEMO_DIR)
    key = weather._cache_key("nasa", LAT, LON, YEAR)
    meta["latitude"] = LAT + 1
    weather._write_dataset(weather.DEMO_DIR, key, df, meta)
    with pytest.raises(weather.WeatherDataError, match="metadata does not match"):
        weather.load_nasa_hourly(LAT, LON, YEAR, offline=True)


def test_qc_uses_midpoint_and_reports_signed_absolute_residuals(nasa_payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    df = weather._parse_nasa_payload(nasa_payload)
    df.loc[:, ["ghi", "dni", "dhi"]] = [110.0, 100.0, 50.0]
    seen = []
    def solar(times, lat, lon):
        seen.append(times)
        return pd.DataFrame({"zenith": np.full(len(times), 60.0)}, index=times)
    monkeypatch.setattr(weather.pvlib.solarposition, "get_solarposition", solar)
    qc = weather.weather_qc(df, LAT, LON)
    assert seen[0].equals(df.index + pd.Timedelta(minutes=30))
    assert qc["rows"] == 48 and qc["hourly_continuous"]
    assert qc["missing_counts"] == dict.fromkeys(weather.COLUMNS, 0)
    assert qc["closure_residual_w_m2"]["signed"] == pytest.approx({"median": 10, "p95": 10})
    assert qc["closure_residual_w_m2"]["absolute"] == pytest.approx({"median": 10, "p95": 10})
    assert qc["annual_ghi_kwh_m2"] == pytest.approx(48 * 110 / 1000)
    json.dumps(qc, allow_nan=False)


def test_qc_reports_ranges_missing_and_extreme_temperatures(nasa_payload: dict) -> None:
    df = weather._parse_nasa_payload(nasa_payload)
    df.loc[df.index[0], "ghi"] = 1500
    df.loc[df.index[1], "dni"] = 1400
    df.loc[df.index[2], "dhi"] = df.loc[df.index[2], "ghi"] + 51
    df.loc[df.index[3], "temp_air"] = -41
    df.loc[df.index[4], "temp_air"] = 56
    df.loc[df.index[5], "wind_speed"] = np.nan
    qc = weather.weather_qc(df, LAT, LON)
    assert qc["range_violations"] == {"ghi": 1, "dni": 1, "dhi_gt_ghi_plus_50": 1, "temp_air": 2}
    assert qc["missing_counts"]["wind_speed"] == 1
    assert qc["temp_air_min_c"] == -41 and qc["temp_air_max_c"] == 56


def test_cli_offline_includes_quality_json(nasa_payload: dict, capsys: pytest.CaptureFixture) -> None:
    save_sample("nasa", nasa_payload, weather.DEMO_DIR)
    assert weather.main(["fetch", "--source", "nasa", "--lat", str(LAT), "--lon", str(LON), "--year", str(YEAR), "--offline"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["metadata"]["used"] == "demo" and output["qc"]["rows"] == 48


@pytest.mark.parametrize("lat,lon", [(91, LON), (LAT, 181), (float("nan"), LON)])
def test_invalid_site_is_rejected(lat: float, lon: float) -> None:
    with pytest.raises(ValueError):
        weather.load_pvgis_tmy(lat, lon, offline=True)


def test_weather_http_has_one_attempt_and_short_timeout(monkeypatch):
    seen={}
    class Session:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def mount(self,prefix,adapter):seen['retry_total']=adapter.max_retries.total
        def get(self,url,**kwargs):
            seen.update(kwargs)
            return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'recorded':True})
    monkeypatch.setattr(requests,'Session',Session)
    assert DOWNLOAD_JSON('https://example.invalid/recorded')=={'recorded':True}
    assert seen=={'retry_total':0,'timeout':(3,15)}


@pytest.mark.network
@pytest.mark.parametrize("source", ["nasa", "pvgis"])
def test_live_public_source(source: str) -> None:
    df, meta = weather.load_nasa_hourly(LAT, LON, YEAR) if source == "nasa" else weather.load_pvgis_tmy(LAT, LON)
    assert len(df) == 8760 and meta["used"] == "download"
    assert str(df.index.tz) == "UTC" and df.isna().sum().sum() == 0
