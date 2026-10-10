"""T12 fixed OSM selection; rebuild frozen owner requirements, witnesses and proofs from definitions."""

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random

import requests
from shapely import affinity
from shapely.geometry import Polygon, box

ROOT = Path(__file__).resolve().parents[1]
ROOFS = ROOT / "data/roofs"
URL = "https://overpass-api.de/api/interpreter"
QUERY = ('[out:json][timeout:25][maxsize:67108864];(way[building~"^(industrial|warehouse|factory)$"](31.55,119.80,31.80,120.08);'
         'node[place=city][name~"^(南京|无锡|徐州|常州|苏州|南通|连云港|淮安|盐城|扬州|镇江|泰州|宿迁)市?$"]'
         '(30.70,116.30,35.20,121.95););out geom;')


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def metric(element):
    points = element["geometry"]
    lat = sum(p["lat"] for p in points[:-1]) / (len(points) - 1)
    lon = sum(p["lon"] for p in points[:-1]) / (len(points) - 1)
    scale = math.pi * 6378137 / 180
    raw = Polygon([((p["lon"] - lon) * scale * math.cos(math.radians(lat)), (p["lat"] - lat) * scale) for p in points])
    outline = raw.simplify(0.3, preserve_topology=True)
    outline = affinity.translate(outline, -outline.centroid.x, -outline.centroid.y)
    return raw, outline, round(lat, 2), round(lon, 2)


def select(elements):
    candidates = []
    for element in sorted(elements, key=lambda item: item["id"]):
        points = element["geometry"]
        if points[0] != points[-1]:
            continue
        raw, outline, lat, lon = metric(element)
        rectangle = outline.minimum_rotated_rectangle
        corners = list(rectangle.exterior.coords)
        edges = [(math.dist(a, b), a, b) for a, b in zip(corners, corners[1:])]
        length, a, b = max(edges, key=lambda edge: edge[0])
        angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
        aspect = length / min(edge[0] for edge in edges)
        if not raw.is_valid or not 1500 <= raw.area <= 15000 or aspect > 6 or len(outline.exterior.coords) > 13:
            continue
        if abs(outline.area / raw.area - 1) > 0.01:
            continue
        candidates.append((element, outline, lat, lon, min(angle, 180 - angle) >= 15, outline.area / rectangle.area < 0.98))
    chosen = []
    for category, quota in ((4, 3), (5, 3), (None, 6)):
        eligible = [row for row in candidates if row not in chosen and (category is None or row[category])]
        if len(eligible) < quota:
            raise ValueError("Fixed selection quotas cannot be met; do not change rules after acquisition")
        chosen.extend(eligible[:quota])
    return chosen


def devices(outline, seed, count=None):
    rng = random.Random(20261003 + seed)
    amount = count or max(1, math.ceil(outline.area / 3000))
    obstacles, keepouts, used = [], [], []
    xmin, ymin, xmax, ymax = outline.bounds
    for index in range(amount * 3):
        for attempt in range(10000):
            x, y = rng.uniform(xmin, xmax), rng.uniform(ymin, ymax)
            shape = box(x - 2, y - 2, x + 2, y + 2)
            if outline.buffer(-2).covers(shape) and not any(shape.buffer(2).intersects(other) for other in used):
                break
        else:
            raise ValueError("Device placement exhausted")
        used.append(shape)
        polygon = [[round(x, 3), round(y, 3)] for x, y in list(shape.exterior.coords)[:-1]]
        label = ("楼梯间", "空调外机", "天窗")[index % 3] + "（示意）"
        if index % 3 == 2:
            keepouts.append(dict(id=f"sky-{index // 3 + 1}", label=label, polygon=polygon))
        else:
            obstacles.append(dict(id=f"device-{index + 1}", label=label, kind="prism", footprint=polygon, height_m=3.2 if index % 3 == 0 else 1))
    return obstacles, keepouts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    if args.download:
        response = requests.get(URL, params={"data": QUERY}, headers={"User-Agent": "Guangzhu-T12-offline-dataset/1"}, timeout=120)
        response.raise_for_status()
        payload = response.json()
        fetched = datetime.now(timezone.utc).isoformat()
        elements = [dict(type=e["type"], id=e["id"], geometry=e["geometry"], tags={k: v for k, v in e.get("tags", {}).items()
                         if k in ("building", "height", "building:levels")}) for e in payload["elements"] if e["type"] == "way"]
        write(ROOFS / "osm-raw.json", dict(url=URL, query=QUERY, fetched_at=fetched, response_sha256=hashlib.sha256(response.content).hexdigest(),
              osm_timestamp=payload["osm3s"]["timestamp_osm_base"], elements=elements))
        write(ROOT / "data/cache/t12-osm-cities.json", [e for e in payload["elements"] if e["type"] == "node"])
    selected = select(json.loads((ROOFS / "osm-raw.json").read_text(encoding="utf-8"))["elements"])
    definitions = json.loads((ROOT / "eval/definitions.json").read_text(encoding="utf-8"))
    base = json.loads((ROOT / "data/demo/projects/changzhou-demo/project.json").read_text(encoding="utf-8"))
    for definition in definitions:
        case = definition["case"]
        project = copy.deepcopy(base)
        project.update(id=case["template"], name=definition["name"], collection=case["collection"], requirements={}, designs=[])
        if case["collection"] == "real":
            element, outline, lat, lon, tilted, irregular = selected[definition["selection_index"]]
            project["site"].update(lat=lat, lon=lon)
            project["roof"]["outline"] = [[round(x, 3), round(y, 3)] for x, y in list(outline.exterior.coords)[:-1]]
            tags = element["tags"]
            project["roof"]["height_m"] = float(tags.get("height", str(float(tags.get("building:levels", 0)) * 4.5 or 10)).rstrip(" m"))
            project["roof"]["obstacles"], project["roof"]["keepouts"] = devices(outline, element["id"])
        project["roof"].update(definition.get("roof", {}))
        write(ROOFS / case["template"] / "project.json", project)
    write(ROOT / "eval/cases.json", [definition["case"] for definition in definitions])


if __name__ == "__main__":
    main()
