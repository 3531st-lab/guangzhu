"""Daily design temperatures verify the full calendar and exact provenance offline."""

import copy
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
import requests
from pydantic import ValidationError

from guangzhu import weather
from guangzhu.models import GzError, Site

DEMO = weather.DEMO_DIR
KEY = "nasa_daily_31.8100_119.9700_1996_2025"


@pytest.fixture(autouse=True)
def storage(monkeypatch):
    with TemporaryDirectory() as directory:
        monkeypatch.setattr(weather, "CACHE_DIR", Path(directory) / "cache")
        monkeypatch.setattr(weather, "DEMO_DIR", Path(directory) / "demo")
        def no_network(*args, **kwargs):
            pytest.fail("Daily tests must not use the network.")
        monkeypatch.setattr(requests.Session, "request", no_network)
        monkeypatch.setattr(weather, "_download_json", no_network)
        yield


def sample():
    dates = pd.date_range("2024-01-01", "2024-12-31").strftime("%Y%m%d")
    minimum, maximum = dict.fromkeys(dates, 5.0), dict.fromkeys(dates, 25.0)
    minimum["20240229"], maximum["20240715"] = -12.3, 42.1
    return {"header": {"fill_value": -999, "time_standard": "LST"},
            "properties": {"parameter": {"T2M_MIN": minimum, "T2M_MAX": maximum}}}


def test_download_cache_exact_calendar_and_checksum(monkeypatch):
    urls = []
    def download(url):
        urls.append(url)
        return sample()
    monkeypatch.setattr(weather, "_download_json", download)
    result = weather.load_nasa_daily_extremes(31.81, 119.97, start_year=2024, end_year=2024)
    assert {k: result[k] for k in ("temp_min_c", "temp_max_c", "min_date", "max_date")} == {
        "temp_min_c": -12.3, "temp_max_c": 42.1, "min_date": "2024-02-29", "max_date": "2024-07-15"}
    query = parse_qs(urlparse(urls[0]).query)
    assert query["parameters"] == ["T2M_MIN,T2M_MAX"] and query["community"] == ["RE"]
    assert query["start"] == ["20240101"] and query["end"] == ["20241231"]
    assert query["time-standard"] == ["LST"] and query["format"] == ["JSON"]
    meta = result["metadata"]
    assert meta["used"] == "download" and meta["row_count"] == 366
    assert hashlib.sha256((weather.CACHE_DIR / meta["data_file"]).read_bytes()).hexdigest() == meta["data_file_sha256"]
    cached = weather.load_nasa_daily_extremes(31.81, 119.97, start_year=2024, end_year=2024)
    assert cached["metadata"]["used"] == "cache" and len(urls) == 1
    assert cached["temp_min_c"] == result["temp_min_c"] and cached["max_date"] == result["max_date"]


def test_real_thirty_year_demo_offline_failure_and_integrity(monkeypatch):
    weather.DEMO_DIR.mkdir(parents=True)
    for suffix in (".json", ".csv.gz"):
        shutil.copyfile(DEMO / (KEY + suffix), weather.DEMO_DIR / (KEY + suffix))
    load = lambda **kwargs: weather.load_nasa_daily_extremes(31.81, 119.97, start_year=1996, end_year=2025, **kwargs)
    result = load(offline=True)
    assert (result["temp_min_c"], result["min_date"], result["temp_max_c"], result["max_date"]) == (-13.45, "2010-02-13", 42.06, "2022-08-22")
    assert result["metadata"]["row_count"] == 10958 and result["metadata"]["used"] == "demo"
    assert result["metadata"]["data_file_sha256"] == "1c095117c00460dd91896160a7de20824f94aa981f3de85bcb00b44bdda6f1d9"
    def disconnected(url):
        raise requests.ConnectionError("recorded disconnect")
    monkeypatch.setattr(weather, "_download_json", disconnected)
    assert "recorded disconnect" in load()["metadata"]["fallback_reason"]
    weather.CACHE_DIR.mkdir(parents=True)
    shutil.copyfile(weather.DEMO_DIR / (KEY + ".json"), weather.CACHE_DIR / (KEY + ".json"))
    (weather.CACHE_DIR / (KEY + ".csv.gz")).write_bytes(b"corrupt")
    assert "checksum" in load(offline=True)["metadata"]["fallback_reason"]
    for lat, start in ((31.82, 1996), (31.81, 1997)):
        with pytest.raises(weather.WeatherDataError, match="no matching site/year range"):
            weather.load_nasa_daily_extremes(lat, 119.97, start_year=start, end_year=2025, offline=True)
    path = weather.DEMO_DIR / (KEY + ".json")
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["latitude"] = 32.81
    path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(weather.WeatherDataError, match="metadata does not match"):
        load(offline=True)


@pytest.mark.parametrize("fault", ["missing_date", "fill", "infinite", "reversed", "time_standard"])
def test_bad_daily_data_rejected_with_clear_reason(monkeypatch, fault):
    payload = copy.deepcopy(sample())
    values = payload["properties"]["parameter"]
    if fault == "missing_date":
        for column in values.values():
            del column["20240229"]
        reason = "dates are missing"
    elif fault == "time_standard":
        payload["header"]["time_standard"] = "UTC"
        reason = "requested LST"
    else:
        values["T2M_MIN"]["20240229"] = {"fill": -999, "infinite": float("inf"), "reversed": 60}[fault]
        reason = "minimum exceeds" if fault == "reversed" else "temperatures are missing"
    monkeypatch.setattr(weather, "_download_json", lambda url: payload)
    with pytest.raises(weather.WeatherDataError, match=reason):
        weather.load_nasa_daily_extremes(31.81, 119.97, start_year=2024, end_year=2024)
    assert not weather.CACHE_DIR.exists()


def test_site_temperature_defaults_bounds_and_order():
    site = Site(lat=31.81, lon=119.97)
    assert site.design_temp_min_c is None and site.design_temp_max_c is None
    assert Site(lat=31.81, lon=119.97, design_temp_min_c=-15.5, design_temp_max_c=41.5).design_temp_min_c == -15.5
    for kwargs in ({"design_temp_min_c": -101}, {"design_temp_max_c": 71}, {"design_temp_min_c": float("nan")},
                   {"design_temp_min_c": 30, "design_temp_max_c": 20}):
        with pytest.raises((ValidationError, GzError)):
            Site(lat=31.81, lon=119.97, **kwargs)
