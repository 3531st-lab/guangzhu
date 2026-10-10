"""Offline official astronomy regression and evidence/collection safeguards."""
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
import requests

from guangzhu.layout import true_solar_times
from scripts import check_official_sun as check


@pytest.fixture(scope="module")
def comparisons():
    return check.compare()


def test_comparison_is_offline(monkeypatch, comparisons):
    def forbidden(*args, **kwargs):
        pytest.fail("Official reference regression must not make network requests")
    monkeypatch.setattr(requests, "get", forbidden)
    assert check.compare() == comparisons


def test_usno_complete_raw_bytes_hashes_and_echoed_requests():
    manifest = json.loads((check.DATA / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 41
    assert len({item["file"] for item in manifest}) == 41
    for item in manifest:
        raw = (check.DATA / item["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        assert pd.Timestamp(item["collected_at"]).tz is not None
        url = urlparse(item["url"])
        assert url.scheme == "https" and url.hostname == "aa.usno.navy.mil"
        query = parse_qs(url.query)
        assert query["coords"] == ["31.81,119.97"]
        payload = json.loads(raw)
        assert "error" not in payload
        assert payload["geometry"]["coordinates"] == [119.97, 31.81]
        props = payload["properties"] if item["kind"] == "celnav" else payload["properties"]["data"]
        date = f"{props['year']:04d}-{props['month']:02d}-{props['day']:02d}"
        assert query["date"] == [date]
        if item["kind"] == "celnav":
            assert props["tz"] == 0
            echoed = pd.Timestamp(f"{date}T{props['time']}Z")
            assert echoed == pd.Timestamp(item["instant"])
        else:
            assert props["tz"] == 8 and not props["isdst"]
            assert date == item["date"]


def test_required_hourly_and_true_solar_instants_are_present():
    manifest = json.loads((check.DATA / "manifest.json").read_text(encoding="utf-8"))
    instants = {pd.Timestamp(x["instant"]) for x in manifest if x["kind"] == "celnav"}
    expected = set()
    for date in ("2025-12-21", "2026-03-20", "2026-06-21"):
        for hour in range(8, 17):
            expected.add((pd.Timestamp(date, tz="Asia/Shanghai") + pd.Timedelta(hours=hour)).tz_convert("UTC"))
    expected.update(true_solar_times(119.97, [9, 15]).round("us"))
    assert instants == expected and len(instants) == 29
    assert {x["date"] for x in manifest if x["kind"] == "rstt"} == {f"2026-{month:02d}-21" for month in range(1, 13)}


def test_sun_angles_and_one_metre_shadows_meet_fixed_thresholds(comparisons):
    assert len(comparisons["sun"]) == 29
    for row in comparisons["sun"]:
        assert row[3] <= 0.05, row
        assert row[6] <= 0.05, row
        if row[2] >= 10:
            assert row[9] <= 0.5, row
        assert 0 <= row[10] < 360 and 0 <= row[11] < 360
        assert row[-1], row


def test_usno_monthly_rise_set_meet_one_minute(comparisons):
    assert len(comparisons["usno"]) == 12
    for row in comparisons["usno"]:
        assert max(row[4], row[7]) <= 1, row
        assert row[-1], row


def test_weather_evidence_has_thirteen_unique_cities_per_day_and_osm_points(comparisons):
    cities = json.loads((check.DATA / "cities.json").read_text(encoding="utf-8"))
    assert len(cities) == 13
    assert {item["code"] for item in cities} == {f"10119{number:02d}01" for number in range(1, 14)}
    nodes = json.loads((check.DATA / "osm-cities.json").read_text(encoding="utf-8"))["elements"]
    nodes = {node["id"]: node for node in nodes if node["type"] == "node"}
    for city in cities:
        node = nodes[city["osm_id"]]
        assert node["tags"]["place"] == "city"
        assert (city["lat"], city["lon"]) == (node["lat"], node["lon"])
    snapshots = sorted(check.DATA.glob("weather-*.json"))
    assert snapshots
    complete = 0
    for path in snapshots:
        items = json.loads(path.read_text(encoding="utf-8"))
        # A failed day keeps its single original attempt record (reports/assets/T12/sun-official.md); it has no times and is never compared.
        failed = len(items) == 1 and "sunrise" not in items[0] and "sunset" not in items[0]
        complete += not failed
        assert failed or len({item["code"] for item in items}) == len(items) == 13
        for item in items:
            assert item["date"] in path.name
            assert pd.Timestamp(item["collected_at"]).tz_convert("Asia/Shanghai").date().isoformat() == item["date"]
            assert set(item) <= {"city", "code", "url", "lat", "lon", "osm_id", "date", "collected_at",
                                 "sunrise", "sunset", "method", "page_date", "source_ref"}
            assert item["url"] == f"https://www.weather.com.cn/weather1d/{item['code']}.shtml"
            assert item["page_date"] == item["date"]
            assert failed or "sunrise" in item and "sunset" in item
    assert complete and len(comparisons["weather"]) == complete * 13
    for row in comparisons["weather"]:
        assert max(row[4], row[7]) <= 2, row
        assert row[-1], row


def weather_directory(tmp_path, monkeypatch):
    city = dict(city="fixture", code="101190101", lat=32.0, lon=118.8, osm_id=1,
                url="https://www.weather.com.cn/weather1d/101190101.shtml")
    (tmp_path / "cities.json").write_text(json.dumps([city]), encoding="utf-8")
    monkeypatch.setattr(check, "DATA", tmp_path)
    date = pd.Timestamp.now(tz="Asia/Shanghai").date().isoformat()
    return date, tmp_path / f"weather-{date}.json"


def test_weather_once_per_actual_beijing_date(tmp_path, monkeypatch):
    date, path = weather_directory(tmp_path, monkeypatch)
    response = requests.Response()
    response.status_code = 200
    response._content = f"{date} {int(date[-2:])}日白天 日出 <span>05:59</span> 日落 <span>17:49</span>".encode()
    calls = []
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: calls.append(args) or response)
    check.collect_weather()
    check.collect_weather()
    assert len(calls) == 1
    item = json.loads(path.read_text(encoding="utf-8"))[0]
    assert (item["sunrise"], item["sunset"]) == ("05:59", "17:49")
    assert item["date"] == date


@pytest.mark.parametrize("status", [200, 403])
def test_stale_or_blocked_weather_is_recorded_without_retry_or_bypass(tmp_path, monkeypatch, status):
    date, path = weather_directory(tmp_path, monkeypatch)
    wrong_day = int(date[-2:]) % 28 + 1
    response = requests.Response()
    response.status_code = status
    response._content = f"{wrong_day}日白天 日出 05:59 日落 17:49".encode()
    calls = []
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: calls.append(args) or response)
    with pytest.raises((AssertionError, requests.HTTPError)):
        check.collect_weather()
    check.collect_weather()
    assert len(calls) == 1
    assert "sunrise" not in json.loads(path.read_text(encoding="utf-8"))[0]


def test_report_preserves_every_point_and_explicit_failures(tmp_path, monkeypatch):
    report = tmp_path / "sun.md"
    report.write_text("context\n<!-- comparison -->\n", encoding="utf-8")
    monkeypatch.setattr(check, "REPORT", report)
    row = ["retained-failure", 1, 2, 1, 3, 4, 1, 5, 6, 20, 183, 184, False]
    monkeypatch.setattr(check, "compare", lambda: {"sun": [row], "usno": [], "weather": []})
    monkeypatch.setattr("sys.argv", ["check_official_sun.py"])
    check.main()
    text = report.read_text(encoding="utf-8")
    assert "retained-failure" in text and "False" in text and "0/1" in text
