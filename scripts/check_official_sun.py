"""Collect official sun fixtures once, then reproduce all comparisons offline."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

import pandas as pd
import requests
from scipy.optimize import brentq

from guangzhu.solar import sun_position

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/field/sun-official"
REPORT = ROOT / "reports/assets/T12/sun-official.md"


def events(date, lat, lon):
    start = pd.Timestamp(date, tz="Asia/Shanghai")
    def elevation(seconds):
        stamp = start + pd.Timedelta(seconds=seconds)
        return sun_position([stamp], lat, lon).elevation.iloc[0] + 0.8333
    return [brentq(elevation, low, low + 43200) / 60 for low in (0, 43200)]


def compare():
    rows = {"sun": [], "usno": [], "weather": []}
    for item in json.loads((DATA / "manifest.json").read_text(encoding="utf-8")):
        payload = json.loads((DATA / item["file"]).read_text(encoding="utf-8"))
        lon, lat = payload["geometry"]["coordinates"]
        if item["kind"] == "celnav":
            official = next(x for x in payload["properties"]["data"] if x["object"] == "Sun")["almanac_data"]
            sun = sun_position([pd.Timestamp(item["instant"])], lat, lon).iloc[0]
            ours, reference = [1 / math.tan(math.radians(x)) for x in (sun.elevation, official["hc"])]
            angle = abs((sun.azimuth - official["zn"] + 180) % 360 - 180)
            length = abs(ours / reference - 1) * 100
            passed = abs(sun.elevation - official["hc"]) <= 0.05 and angle <= 0.05
            passed = passed and (official["hc"] < 10 or length <= 0.5)
            rows["sun"].append([item["label"], sun.elevation, official["hc"], abs(sun.elevation - official["hc"]),
                                sun.azimuth, official["zn"], angle, ours, reference, length,
                                (sun.azimuth + 180) % 360, (official["zn"] + 180) % 360, passed])
        else:
            times = {x["phen"]: x["time"] for x in payload["properties"]["data"]["sundata"]}
            append_events(rows["usno"], item["date"], "常州", lat, lon, [times["Rise"], times["Set"]], 1)
    for path in sorted(DATA.glob("weather-*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            if "sunrise" in item:
                append_events(rows["weather"], item["date"], item["city"], item["lat"], item["lon"],
                              [item["sunrise"], item["sunset"]], 2)
    return rows


def append_events(rows, date, city, lat, lon, reference, limit):
    ours = events(date, lat, lon)
    minutes = [int(value[:2]) * 60 + int(value[3:]) for value in reference]
    errors = [abs(value - expected) for value, expected in zip(ours, minutes)]
    clocks = [str(pd.Timedelta(minutes=value)).split()[-1][:8] for value in ours]
    rows.append([date, city, clocks[0], reference[0], errors[0], clocks[1], reference[1], errors[1], max(errors) <= limit])


def collect_weather():
    now = pd.Timestamp.now(tz="UTC")
    date = now.tz_convert("Asia/Shanghai").date().isoformat()
    path = DATA / f"weather-{date}.json"
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    for city in json.loads((DATA / "cities.json").read_text(encoding="utf-8")):
        if any(item["code"] == city["code"] for item in saved):
            continue
        item = dict(city, date=date, collected_at=pd.Timestamp.now(tz="UTC").isoformat(), method="http", page_date=date)
        saved.append(item)
        path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        response = requests.get(item["url"], timeout=45)
        response.raise_for_status()
        text = response.content.decode("utf-8")
        assert date in text and int(re.search(r"(\d+)日白天", text)[1]) == int(date[-2:]), "Weather page is stale"
        item.update({key: re.search(label + r".*?(\d\d:\d\d)", text, re.S)[1]
                     for key, label in (("sunrise", "日出"), ("sunset", "日落"))})
        path.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch-usno", action="store_true")
    parser.add_argument("--collect-weather", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    if args.fetch_usno:
        for item in manifest:
            if (DATA / item["file"]).exists():
                continue
            response = requests.get(item["url"], timeout=45)
            response.raise_for_status()
            assert "error" not in response.json(), response.text
            (DATA / item["file"]).write_bytes(response.content)
            item.update(sha256=hashlib.sha256(response.content).hexdigest(), collected_at=pd.Timestamp.now(tz="UTC").isoformat())
            (DATA / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(item["file"], flush=True)
    if args.collect_weather:
        collect_weather()
    columns = {"sun": ["时刻", "高度光筑°", "高度USNO°", "高度差°", "方位光筑°", "方位USNO°", "方位差°",
                       "影长光筑m", "影长USNOm", "影长差%", "影向光筑°", "影向USNO°", "合格"],
               "usno": ["日期", "城市", "日出光筑", "日出官方", "差min", "日落光筑", "日落官方", "差min", "合格"]}
    columns["weather"] = columns["usno"]
    rows = compare()
    prefix = REPORT.read_text(encoding="utf-8").split("<!-- comparison -->")[0]
    tables = []
    for key, values in rows.items():
        lines = pd.DataFrame(values, columns=columns[key]).to_csv(index=False, sep="|", float_format="%.5f").splitlines()
        lines.insert(1, "|".join("---" for _ in columns[key]))
        title = f"\n## {key}（{sum(row[-1] for row in values)}/{len(values)} 合格）\n\n"
        tables.append(title + "\n".join("|" + line + "|" for line in lines))
    REPORT.write_text(prefix + "<!-- comparison -->\n" + "\n".join(tables) + "\n", encoding="utf-8")
    print({key: [sum(row[-1] for row in value), len(value)] for key, value in rows.items()})


if __name__ == "__main__":
    main()
