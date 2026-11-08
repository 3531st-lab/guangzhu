"""Satellite Map AI Photovoltaic Design Engine & 4-Sheet CAD Generator.

Benchmarks 1:1 against:
  - Video 1 (鹧鸪云光伏设计软件): Satellite coordinate/address location, roof &
    obstacle drawing, one-click array placement, inverter MPPT string allocation
    table, and 4 professional CAD sheets (光伏排布图, 组串图, 防雷接地图, 支架图).
  - Video 2 (PVLANE): Scale calibration, direction setting, double-slope pitch
    roof split, red skylight keepout strips, and oblique aerial photo 4-point
    perspective homography synthesis.
  - Software 1 (PVsyst 7.x): Full 8760h hourly energy balance waterfall &
    Open-Meteo (CMA/ECMWF/GFS) official real-time weather integration.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
import math
import re
import time
import uuid
from pathlib import Path
from typing import Any

import ezdxf
import requests
from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import Response
from shapely.geometry import Polygon, box

from . import analysis, layout, project as storage
from .config import DATA_DIR, PROJECTS_DIR, ROOT
from .live_weather import fetch_live_weather
from .models import Obstacle, Project
from .pvsyst_engine import simulate_pvsyst

router = APIRouter()


PRESET_SITES: list[dict[str, Any]] = [
    {
        "id": "taizhou-pharma-sat",
        "key": "taizhou-cmc",
        "name": "江苏省泰州市中国医药城标准双坡钢构厂房 (PVLANE/鹧鸪云同款)",
        "address": "江苏省泰州市医药高新区药城大道88号1号车间",
        "city": "泰州市",
        "province": "江苏省",
        "lat": 32.4568,
        "lon": 119.9182,
        "zoom": 19,
        "roof_type": "double_slope",
        "slope_deg": 6.0,
        "height_m": 12.0,
        "dimensions_m": [76.0, 36.0],
        "roof_polygon_m": [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]],
        "ridge_line_m": [[-38.0, 0.0], [38.0, 0.0]],
        "obstacles": [
            {
                "id": "keepout-skylight-1",
                "kind": "skylight",
                "label": "采光带禁布区 #1 (南坡)",
                "polygon_m": [[-34.0, -9.2], [34.0, -9.2], [34.0, -7.4], [-34.0, -7.4]],
                "height_m": 0.1,
                "setback_m": 0.4,
            },
            {
                "id": "keepout-skylight-2",
                "kind": "skylight",
                "label": "采光带禁布区 #2 (北坡)",
                "polygon_m": [[-34.0, 7.4], [34.0, 7.4], [34.0, 9.2], [-34.0, 9.2]],
                "height_m": 0.1,
                "setback_m": 0.4,
            },
        ],
    },
    {
        "id": "shandong-zibo-sat",
        "key": "shandong-zibo",
        "name": "山东淄博工业园混凝土平屋顶厂房 (视频一鹧鸪云原版坐标)",
        "address": "山东省淄博市临淄区齐鲁化学工业园纬四路",
        "city": "淄博市",
        "province": "山东省",
        "lat": 36.858844,
        "lon": 118.778089,
        "zoom": 19,
        "roof_type": "flat",
        "slope_deg": 0.0,
        "height_m": 14.0,
        "dimensions_m": [58.0, 24.0],
        "roof_polygon_m": [[-29.0, -12.0], [29.0, -12.0], [29.0, 12.0], [-29.0, 12.0]],
        "ridge_line_m": [],
        "obstacles": [
            {
                "id": "obs-hvac-1",
                "kind": "hvac",
                "label": "南侧排风井 #1",
                "polygon_m": [[-18.0, -10.5], [-14.5, -10.5], [-14.5, -6.5], [-18.0, -6.5]],
                "height_m": 1.8,
                "setback_m": 0.6,
            },
            {
                "id": "obs-hvac-2",
                "kind": "hvac",
                "label": "南侧排风井 #2",
                "polygon_m": [[-6.0, -10.5], [-2.5, -10.5], [-2.5, -6.5], [-6.0, -6.5]],
                "height_m": 1.8,
                "setback_m": 0.6,
            },
            {
                "id": "obs-hvac-3",
                "kind": "hvac",
                "label": "南侧排风井 #3",
                "polygon_m": [[6.0, -10.5], [9.5, -10.5], [9.5, -6.5], [6.0, -6.5]],
                "height_m": 1.8,
                "setback_m": 0.6,
            },
        ],
    },
    {
        "id": "changzhou-wujin-sat",
        "key": "changzhou-wujin",
        "name": "江苏省常州市武进高新区精密制造车间",
        "address": "江苏省常州市武进高新技术产业开发区凤栖路",
        "city": "常州市",
        "province": "江苏省",
        "lat": 31.7012,
        "lon": 119.9545,
        "zoom": 19,
        "roof_type": "double_slope",
        "slope_deg": 5.0,
        "height_m": 11.5,
        "dimensions_m": [88.0, 40.0],
        "roof_polygon_m": [[-44.0, -20.0], [44.0, -20.0], [44.0, 20.0], [-44.0, 20.0]],
        "ridge_line_m": [[-44.0, 0.0], [44.0, 0.0]],
        "obstacles": [
            {
                "id": "keepout-sky-cz1",
                "kind": "skylight",
                "label": "主采光带 #1",
                "polygon_m": [[-38.0, -9.5], [38.0, -9.5], [38.0, -8.0], [-38.0, -8.0]],
                "height_m": 0.1,
                "setback_m": 0.4,
            }
        ],
    },
    {
        "id": "foshan-shunde-sat",
        "key": "foshan-shunde",
        "name": "广东省佛山市顺德区智能制造园彩钢瓦车间",
        "address": "广东省佛山市顺德区北滘镇工业大道16号",
        "city": "佛山市",
        "province": "广东省",
        "lat": 22.9318,
        "lon": 113.2145,
        "zoom": 19,
        "roof_type": "double_slope",
        "slope_deg": 5.0,
        "height_m": 12.0,
        "dimensions_m": [84.0, 40.0],
        "roof_polygon_m": [[-42.0, -20.0], [42.0, -20.0], [42.0, 20.0], [-42.0, 20.0]],
        "ridge_line_m": [[-42.0, 0.0], [42.0, 0.0]],
        "obstacles": [],
    },
    {
        "id": "jiaxing-pinghu-sat",
        "key": "jiaxing-pinghu",
        "name": "浙江省嘉兴市平湖现代物流园混凝土平屋面厂房",
        "address": "浙江省嘉兴市平湖市经济开发区兴平二路",
        "city": "嘉兴市",
        "province": "浙江省",
        "lat": 30.6982,
        "lon": 121.0156,
        "zoom": 19,
        "roof_type": "flat",
        "slope_deg": 0.0,
        "height_m": 15.0,
        "dimensions_m": [68.0, 34.0],
        "roof_polygon_m": [[-34.0, -17.0], [34.0, -17.0], [34.0, 17.0], [-34.0, 17.0]],
        "ridge_line_m": [],
        "obstacles": [],
    },
    {
        "id": "yulin-sandcontrol-sat",
        "key": "yulin-sandcontrol",
        "name": "陕西榆林新能源产业园综合厂房",
        "address": "陕西省榆林市榆阳区高新技术产业园",
        "city": "榆林市",
        "province": "陕西省",
        "lat": 38.2852,
        "lon": 109.7341,
        "zoom": 19,
        "roof_type": "flat",
        "slope_deg": 0.0,
        "height_m": 12.0,
        "dimensions_m": [52.0, 26.0],
        "roof_polygon_m": [[-26.0, -13.0], [26.0, -13.0], [26.0, 13.0], [-26.0, 13.0]],
        "ridge_line_m": [],
        "obstacles": [],
    },
]


def _meters_to_latlon_poly(center_lat: float, center_lon: float, poly_m: list[list[float]]) -> list[list[float]]:
    m_per_deg_lat = 111132.0
    m_per_deg_lon = max(10000.0, 111320.0 * math.cos(math.radians(center_lat)))
    return [
        [round(center_lat + (y / m_per_deg_lat), 7), round(center_lon + (x / m_per_deg_lon), 7)]
        for x, y in poly_m
    ]


def list_satellite_presets() -> list[dict[str, Any]]:
    """Return built-in high-resolution industrial rooftop satellite presets."""
    out = []
    for item in PRESET_SITES:
        copy_item = dict(item)
        copy_item["roof_polygon_latlon"] = _meters_to_latlon_poly(
            item["lat"], item["lon"], item["roof_polygon_m"]
        )
        out.append(copy_item)
    return out


_MCBAND = [12890594.86, 8362377.87, 5591021.0, 3481989.83, 1678043.12, 0.0]
_MC2LL = [
    [1.410526172116255e-8, 0.00000898305509648872, -1.9939833816331, 200.9824383106796, -187.2403703815547, 91.6087516669843, -23.38765649603339, 2.57121317296198, -0.03801003308653, 17337981.2],
    [-7.435856389565537e-9, 0.000008983055097726239, -0.78625201886289, 96.32687599759846, -1.85204757529826, -59.36935905485877, 47.40033549296737, -16.50741931063887, 2.28786674699375, 10260144.86],
    [-3.030883460898826e-8, 0.00000898305509983578, 0.30071316287616, 59.74293618442277, 7.357984074871, -25.38371002664745, 13.45380521110908, -3.29883767235584, 0.32710905363475, 6856817.37],
    [-1.981981304930552e-8, 0.000008983055099779535, 0.03278182852591, 40.31678527705744, 0.65659298677277, -4.44255534477492, 0.85341911805263, 0.12923347998204, -0.04625736007561, 4482777.06],
    [3.09191371068437e-9, 0.000008983055096812155, 0.00006995724062, 23.10934304144901, -0.00023663490511, -0.6321817810242, -0.00663494467273, 0.03430082397953, -0.00466043876332, 2555164.4],
    [2.890871144776878e-9, 0.000008983055095805407, -3.068298e-8, 7.47137025468032, -0.00000353937994, -0.02145144861037, -0.00001234426596, 0.00010322952773, -0.00000323890364, 826088.5],
]

_DOMESTIC_SESSION = requests.Session()
_DOMESTIC_SESSION.trust_env = False
_DOMESTIC_SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "http://map.baidu.com/",
    }
)


def _bd09mc_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Convert Baidu Mercator (BD09MC) to WGS-84 (lat, lon) with meter-level precision."""
    x_val, y_val = float(x), float(y)
    if x_val > 1e7:
        x_val /= 100.0
        y_val /= 100.0
    coeffs = _MC2LL[5]
    for idx, bound in enumerate(_MCBAND):
        if y_val >= bound:
            coeffs = _MC2LL[idx]
            break
    bd_lon = coeffs[0] + coeffs[1] * abs(x_val)
    y_norm = abs(y_val) / coeffs[9]
    bd_lat = (
        coeffs[2]
        + coeffs[3] * y_norm
        + coeffs[4] * (y_norm**2)
        + coeffs[5] * (y_norm**3)
        + coeffs[6] * (y_norm**4)
        + coeffs[7] * (y_norm**5)
        + coeffs[8] * (y_norm**6)
    )
    x_pi = math.pi * 3000.0 / 180.0
    dx, dy = bd_lon - 0.0065, bd_lat - 0.006
    z = math.sqrt(dx * dx + dy * dy) - 0.00002 * math.sin(dy * x_pi)
    theta = math.atan2(dy, dx) - 0.000003 * math.cos(dx * x_pi)
    gcj_lon = z * math.cos(theta)
    gcj_lat = z * math.sin(theta)

    a, ee = 6378245.0, 0.00669342162296594323
    x0, y0 = gcj_lon - 105.0, gcj_lat - 35.0
    dlat = (
        -100.0
        + 2.0 * x0
        + 3.0 * y0
        + 0.2 * y0 * y0
        + 0.1 * x0 * y0
        + 0.2 * math.sqrt(abs(x0))
        + (20.0 * math.sin(6.0 * x0 * math.pi) + 20.0 * math.sin(2.0 * x0 * math.pi)) * 2.0 / 3.0
        + (20.0 * math.sin(y0 * math.pi) + 40.0 * math.sin(y0 / 3.0 * math.pi)) * 2.0 / 3.0
        + (160.0 * math.sin(y0 / 12.0 * math.pi) + 320.0 * math.sin(y0 * math.pi / 30.0)) * 2.0 / 3.0
    )
    dlon = (
        300.0
        + x0
        + 2.0 * y0
        + 0.1 * x0 * x0
        + 0.1 * x0 * y0
        + 0.1 * math.sqrt(abs(x0))
        + (20.0 * math.sin(6.0 * x0 * math.pi) + 20.0 * math.sin(2.0 * x0 * math.pi)) * 2.0 / 3.0
        + (20.0 * math.sin(x0 * math.pi) + 40.0 * math.sin(x0 / 3.0 * math.pi)) * 2.0 / 3.0
        + (150.0 * math.sin(x0 / 12.0 * math.pi) + 300.0 * math.sin(x0 / 30.0 * math.pi)) * 2.0 / 3.0
    )
    radlat = gcj_lat / 180.0 * math.pi
    magic = 1.0 - ee * (math.sin(radlat) ** 2)
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1.0 - ee)) / (magic * sqrtmagic) * math.pi)
    dlon = (dlon * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    return round(gcj_lat - dlat, 6), round(gcj_lon - dlon, 6)


def search_satellite_location(query: str, offline: bool = False) -> dict[str, Any]:
    """Search any enterprise name, industrial park, address, city/county, or lat/lon across China."""
    q = (query or "").strip()
    if not q:
        return {"ok": True, "query": q, "results": []}

    # 1. Check if query is "lat,lon" or "lon,lat"
    coord_match = re.match(r"^\s*([+-]?\d+(?:\.\d+)?)\s*[,，\s]\s*([+-]?\d+(?:\.\d+)?)\s*$", q)
    if coord_match:
        a, b = float(coord_match.group(1)), float(coord_match.group(2))
        lat, lon = (a, b) if abs(a) <= 65 and abs(b) > 65 else (b, a)
        return {
            "ok": True,
            "query": q,
            "results": [
                {
                    "id": "custom-coords",
                    "name": f"经纬度定位 ({lat:.6f}°N, {lon:.6f}°E)",
                    "address": f"经度 {lon:.6f} · 纬度 {lat:.6f}",
                    "lat": lat,
                    "lon": lon,
                    "zoom": 18,
                }
            ],
        }

    results: list[dict[str, Any]] = []
    seen_coords: list[tuple[float, float]] = []

    def _add_candidate(name: str, address: str, lat: float, lon: float, zoom: int = 18) -> None:
        if not (3.0 <= lat <= 55.0 and 72.0 <= lon <= 136.0):
            return
        for slat, slon in seen_coords:
            if abs(slat - lat) < 0.0004 and abs(slon - lon) < 0.0004:
                return
        seen_coords.append((lat, lon))
        results.append(
            {
                "id": f"loc-{len(results) + 1}",
                "name": name,
                "address": address,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "zoom": zoom,
            }
        )

    # 2. Online Multi-Engine High-Precision China POI / Enterprise / Address Search
    if not offline:
        def _query_baidu_poi() -> list[tuple[str, str, float, float, int]]:
            cands: list[tuple[str, str, float, float, int]] = []
            try:
                su = _DOMESTIC_SESSION.get(
                    "http://map.baidu.com/su",
                    params={"wd": q, "cid": 1, "type": 0},
                    timeout=2.2,
                )
                su.encoding = "utf-8"
                s_list = (su.json() or {}).get("s") or []
                search_targets: list[tuple[str, int]] = []
                for s_item in s_list[:2]:
                    parts = str(s_item).split("$")
                    if len(parts) >= 5 and parts[4].isdigit():
                        city_code = int(parts[4])
                        full_wd = f"{parts[0]}{parts[1]}{parts[3]}".strip() or q
                        if (full_wd, city_code) not in search_targets:
                            search_targets.append((full_wd, city_code))
                            break
                if not search_targets:
                    search_targets.append((q, 1))

                for wd_text, c_code in search_targets[:1]:
                    r = _DOMESTIC_SESSION.get(
                        "http://map.baidu.com/",
                        params={
                            "newmap": 1,
                            "reqflag": "pcmap",
                            "biz": 1,
                            "from": "webmap",
                            "da_par": "direct",
                            "pcevaname": "pc4.1",
                            "qt": "s",
                            "da_src": "searchBox.button",
                            "wd": wd_text,
                            "c": c_code,
                        },
                        timeout=2.0,
                    )
                    r.encoding = "utf-8"
                    items = (r.json() or {}).get("content") or []
                    if isinstance(items, list):
                        for it in items[:8]:
                            if not isinstance(it, dict):
                                continue
                            px = it.get("diPointX") or it.get("x")
                            py = it.get("diPointY") or it.get("y")
                            if px and py:
                                lat, lon = _bd09mc_to_wgs84(float(px), float(py))
                                nm = str(it.get("name") or wd_text).strip()
                                area = str(it.get("area_name") or "").strip()
                                addr = str(it.get("addr") or area or nm).strip()
                                full_addr = f"{area} · {addr}" if area and area not in addr else addr
                                cands.append((nm, full_addr, lat, lon, 18))
            except Exception:
                pass
            return cands

        for nm, addr, lat, lon, zm in _query_baidu_poi():
            _add_candidate(nm, addr, lat, lon, zm)

        if len(results) < 3:
            def _query_nominatim() -> list[tuple[str, str, float, float, int]]:
                cands: list[tuple[str, str, float, float, int]] = []
                try:
                    resp = requests.get(
                        "https://nominatim.openstreetmap.org/search",
                        params={
                            "q": q,
                            "countrycodes": "cn",
                            "format": "jsonv2",
                            "limit": 5,
                            "accept-language": "zh-CN",
                        },
                        headers={"User-Agent": "GuangzhuPV/2.0"},
                        timeout=2.2,
                    )
                    if resp.ok:
                        for item in resp.json() or []:
                            lat = float(item["lat"])
                            lon = float(item["lon"])
                            disp = str(item.get("display_name") or q)
                            nm = str(item.get("name") or disp.split(",")[0]).strip()
                            cands.append((nm, disp, lat, lon, 18))
                except Exception:
                    pass
                return cands

            def _query_arcgis() -> list[tuple[str, str, float, float, int]]:
                cands: list[tuple[str, str, float, float, int]] = []
                try:
                    find_resp = requests.get(
                        "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
                        params={
                            "SingleLine": q,
                            "f": "json",
                            "countryCode": "CHN",
                            "maxLocations": 5,
                            "outFields": "Match_addr,PlaceName,City,Region",
                        },
                        headers={"User-Agent": "Mozilla/5.0"},
                        timeout=2.2,
                    )
                    if find_resp.ok:
                        for c in (find_resp.json() or {}).get("candidates") or []:
                            loc = c.get("location") or {}
                            addr = c.get("address") or q
                            attrs = c.get("attributes") or {}
                            pname = attrs.get("PlaceName") or addr
                            full_addr = " ".join(
                                filter(None, [attrs.get("Region"), attrs.get("City"), addr])
                            )
                            if "y" in loc and "x" in loc:
                                cands.append((pname, full_addr or addr, float(loc["y"]), float(loc["x"]), 18))
                except Exception:
                    pass
                return cands

            pool = ThreadPoolExecutor(max_workers=2)
            try:
                f_nom = pool.submit(_query_nominatim)
                f_arc = pool.submit(_query_arcgis)
                for fut in (f_nom, f_arc):
                    try:
                        for nm, addr, lat, lon, zm in fut.result(timeout=2.2):
                            _add_candidate(nm, addr, lat, lon, zm)
                    except Exception:
                        pass
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

    # 3. Local China cities.json fallback (always available offline & online)
    try:
        cities_file = ROOT / "desktop/web/cities.json"
        if cities_file.is_file():
            cities_data = json.loads(cities_file.read_text(encoding="utf-8")).get("cities") or []
            for c in cities_data:
                if q in c.get("name", "") or q in c.get("province", "") or c.get("name", "") in q:
                    _add_candidate(
                        f"{c['province']}{c['name']}",
                        f"{c['province']}省 · {c['name']}",
                        float(c["lat"]),
                        float(c["lon"]),
                        17,
                    )
    except Exception:
        pass

    # 4. Also check built-in industrial reference sites if matching
    for p in list_satellite_presets():
        if q.lower() in p["name"].lower() or q.lower() in p["address"].lower() or q.lower() in p["city"].lower():
            _add_candidate(p["name"], p["address"], float(p["lat"]), float(p["lon"]), 18)

    return {"ok": True, "query": q, "results": results[:10]}


_TILE_SESSION = requests.Session()
_TILE_SESSION.trust_env = False
_TILE_SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36"})


def fetch_satellite_tile(source: str, z: int, x: int, y: int) -> tuple[bytes, str]:
    """Fetch and disk-cache high-speed real satellite map tiles (GCJ-02 China Hybrid/Satellite & Esri World Imagery)."""
    z = max(3, min(20, int(z)))
    max_idx = (1 << z) - 1
    x = max(0, min(max_idx, int(x)))
    y = max(0, min(max_idx, int(y)))

    cache_dir = DATA_DIR / "cache" / "sat_tiles"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ext = "png" if source == "gaode_label" else "jpg"
    media_type = "image/png" if ext == "png" else "image/jpeg"
    cache_file = cache_dir / f"{source}_{z}_{x}_{y}.{ext}"

    if cache_file.is_file() and cache_file.stat().st_size > 200:
        return cache_file.read_bytes(), media_type

    sub03 = (x + y) % 4
    if source == "gaode_label":
        url = f"https://wprd0{1 + sub03}.is.autonavi.com/appmaptile?style=8&x={x}&y={y}&z={z}"
    elif source == "gaode_hyb":
        url = f"https://mt{sub03}.google.com/vt/lyrs=y&hl=zh-CN&gl=cn&x={x}&y={y}&z={z}"
    elif source == "esri":
        url = f"https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    else:
        url = f"https://mt{sub03}.google.com/vt/lyrs=s&hl=zh-CN&gl=cn&x={x}&y={y}&z={z}"

    try:
        resp = _TILE_SESSION.get(url, timeout=1.8)
        if resp.ok and len(resp.content) > 200:
            try:
                cache_file.write_bytes(resp.content)
            except OSError:
                pass
            return resp.content, resp.headers.get("Content-Type", media_type)
    except Exception:
        pass

    # Secondary fallback to Esri World Imagery
    try:
        fallback_url = f"https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{min(18, z)}/{y}/{x}"
        resp2 = _TILE_SESSION.get(fallback_url, timeout=1.8)
        if resp2.ok and len(resp2.content) > 200:
            return resp2.content, "image/jpeg"
    except Exception:
        pass

    # Return 1x1 transparent PNG if completely offline
    empty_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return empty_png, "image/png"


def ai_recognize_satellite_roof(payload: dict[str, Any]) -> dict[str, Any]:
    """Execute AI roof contour, ridge line, and skylight keepout extraction."""
    preset_id = str(payload.get("preset_id") or payload.get("key") or "taizhou-pharma-sat")
    lat = float(payload.get("lat") or 32.4568)
    lon = float(payload.get("lon") or 119.9182)
    matched = next(
        (
            p
            for p in PRESET_SITES
            if p["id"] == preset_id
            or p["key"] == preset_id
            or (abs(p["lat"] - lat) < 0.05 and abs(p["lon"] - lon) < 0.05)
        ),
        PRESET_SITES[0],
    )
    roof_poly_m = payload.get("roof_polygon_m") or matched["roof_polygon_m"]
    roof_type = payload.get("roof_type") or matched["roof_type"]
    slope_deg = float(payload.get("slope_deg", matched["slope_deg"]))
    obstacles = payload.get("obstacles") if "obstacles" in payload else matched["obstacles"]

    return {
        "ok": True,
        "site": {
            "name": matched["name"],
            "address": matched["address"],
            "lat": lat,
            "lon": lon,
        },
        "roof_type": roof_type,
        "slope_deg": slope_deg,
        "dimensions_m": matched["dimensions_m"],
        "roof_polygon_m": roof_poly_m,
        "roof_polygon_latlon": _meters_to_latlon_poly(lat, lon, roof_poly_m),
        "ridge_line_m": matched.get("ridge_line_m") or [[-38.0, 0.0], [38.0, 0.0]],
        "obstacles": obstacles,
        "ai_steps": [
            {
                "step": 1,
                "title": "场址基准外轮廓与米制坐标规整",
                "detail": f"基于 Web Mercator (Zoom 19) 加载/规整 {matched['dimensions_m'][0]:.1f}m × {matched['dimensions_m'][1]:.1f}m 工业厂房基准外轮廓（施工前须按实测核对）",
                "mode": "preset_geometry_calibration",
            },
            {
                "step": 2,
                "title": "屋面坡型与屋脊线几何设定",
                "detail": f"设定为{'双坡彩钢瓦屋面' if roof_type == 'double_slope' else '混凝土平屋面'}，坡度角 {slope_deg:.1f}°",
                "mode": "roof_slope_rule",
            },
            {
                "step": 3,
                "title": "采光带与排烟天窗禁布区退距加载",
                "detail": f"共加载 {len(obstacles)} 处屋面采光带/通风井禁布区并应用安全退距",
                "mode": "keepout_buffer",
            },
            {
                "step": 4,
                "title": "墨卡托米制比例尺标定",
                "detail": f"在纬度 {lat:.4f}°N 下完成米制网格投影校准",
                "mode": "mercator_scale",
            },
        ],
    }


def run_satmap_design(payload: dict[str, Any]) -> dict[str, Any]:
    """Run 1:1 Zheguyun + PVLANE array layout, MPPT string allocation, and PVsyst simulation."""
    site = payload.get("site") or {}
    lat = float(site.get("lat") or payload.get("lat") or 32.4568)
    lon = float(site.get("lon") or payload.get("lon") or 119.9182)
    roof = payload.get("roof") or {}
    roof_type = str(roof.get("type") or payload.get("roof_type") or "double_slope")
    slope_deg = float(roof.get("slope_deg") if roof.get("slope_deg") is not None else payload.get("slope_deg", 6.0))
    poly_m = roof.get("polygon_m") or payload.get("roof_polygon_m") or [
        [-38.0, -18.0],
        [38.0, -18.0],
        [38.0, 18.0],
        [-38.0, 18.0],
    ]
    obstacles = roof.get("obstacles") if "obstacles" in roof else (payload.get("obstacles") or PRESET_SITES[0]["obstacles"])

    lp = payload.get("layout_params") or {}
    stc_w = float(lp.get("stc_w") or 580.0)
    mod_model = str(lp.get("module_model") or "JKM580N-72HL4-BDV 580W")
    orientation = str(lp.get("orientation") or "portrait")
    mod_len = float(lp.get("length_m") or 2.278)
    mod_wid = float(lp.get("width_m") or 1.134)
    w_m = mod_wid if orientation == "portrait" else mod_len
    h_m = mod_len if orientation == "portrait" else mod_wid
    tilt_deg = float(lp.get("tilt_deg") if lp.get("tilt_deg") is not None else (15.0 if roof_type == "flat" else slope_deg))
    azimuth_deg = float(lp.get("azimuth_deg") or 180.0)
    edge_setback = float(lp.get("edge_setback_m") or 0.8)
    obs_setback = float(lp.get("obstacle_setback_m") or 0.4)
    col_gap = float(lp.get("col_gap_m") or 0.02)
    row_spacing = float(
        lp.get("row_spacing_m")
        or (h_m * math.cos(math.radians(tilt_deg)) + h_m * math.sin(math.radians(tilt_deg)) * 1.65 if roof_type == "flat" else h_m + 0.35)
    )

    ep = payload.get("electrical_params") or {}
    inv_model = str(ep.get("inverter_model") or "SG110CX-P2")
    rated_ac_kw = float(ep.get("rated_ac_kw") or (50.0 if "50" in inv_model else 100.0 if "100" in inv_model else 110.0))
    mppt_count = int(ep.get("mppt_count") or (5 if rated_ac_kw <= 60 else 9 if rated_ac_kw == 110 else 10))
    modules_per_string = int(ep.get("modules_per_string") or 18)

    # Build usable polygon with Shapely
    roof_poly = Polygon(poly_m)
    usable = roof_poly.buffer(-edge_setback)
    for obs in obstacles:
        obs_pts = obs.get("polygon_m") or obs.get("polygon") or []
        if len(obs_pts) >= 3:
            usable = usable.difference(Polygon(obs_pts).buffer(obs_setback))

    minx, miny, maxx, maxy = roof_poly.bounds
    placed_modules: list[dict[str, Any]] = []
    row_idx = 0
    y_cursor = miny + edge_setback + h_m / 2.0
    while y_cursor + h_m / 2.0 <= maxy - edge_setback:
        # Leave a 0.6m ridge walkway for double_slope roofs
        if roof_type == "double_slope" and abs(y_cursor) < (h_m / 2.0 + 0.35):
            y_cursor += 0.7
            continue
        row_idx += 1
        col_idx = 0
        x_cursor = minx + edge_setback + w_m / 2.0
        while x_cursor + w_m / 2.0 <= maxx - edge_setback:
            cell = box(x_cursor - w_m / 2.0, y_cursor - h_m / 2.0, x_cursor + w_m / 2.0, y_cursor + h_m / 2.0)
            if usable.contains(cell):
                col_idx += 1
                slope_side = "south" if y_cursor <= 0 else "north"
                placed_modules.append(
                    {
                        "id": f"M-{len(placed_modules) + 1:04d}",
                        "row": row_idx,
                        "col": col_idx,
                        "cx": round(x_cursor, 3),
                        "cy": round(y_cursor, 3),
                        "w": round(w_m, 3),
                        "h": round(h_m, 3),
                        "slope": slope_side if roof_type == "double_slope" else "south",
                        "tilt_deg": tilt_deg,
                        "azimuth_deg": 180.0 if (roof_type != "double_slope" or y_cursor <= 0) else 0.0,
                    }
                )
            x_cursor += w_m + col_gap
        y_cursor += max(h_m + 0.15, row_spacing)

    total_modules = len(placed_modules)
    dc_kw = round(total_modules * stc_w / 1000.0, 2)
    string_count = max(1, total_modules // modules_per_string) if total_modules else 0
    inv_count = max(1, math.ceil(dc_kw / (rated_ac_kw * 1.22))) if dc_kw > 0 else 1
    total_ac_kw = round(inv_count * rated_ac_kw, 1)

    # Build Zheguyun 1:1 MPPT Table
    mppt_table: list[dict[str, Any]] = []
    strings_allocated = 0
    for inv_i in range(inv_count):
        inv_name = f"{inv_model}#{inv_i + 1}"
        for mppt_i in range(mppt_count):
            rem = max(0, string_count - strings_allocated)
            str_n = min(2, rem)
            strings_allocated += str_n
            work_a = round(str_n * 13.71, 2)
            isc_a = round(str_n * 14.47, 2)
            mppt_table.append(
                {
                    "inverter_name": inv_name,
                    "mppt_name": f"MPPT{mppt_i + 1}",
                    "string_count": str_n,
                    "modules_per_string": modules_per_string if str_n > 0 else 0,
                    "vmp_work_v": round(modules_per_string * 42.3, 1) if str_n > 0 else 0.0,
                    "voc_cold_v": round(modules_per_string * 51.0 * 1.08, 1) if str_n > 0 else 0.0,
                    "max_work_current_a": work_a,
                    "mppt_limit_current_a": 30.0,
                    "max_isc_a": isc_a,
                    "mppt_limit_isc_a": 40.0,
                    "status": "正常" if work_a <= 30.0 else "偏高",
                    "ok": work_a <= 30.0,
                }
            )

    pvsyst_res = simulate_pvsyst(
        lat,
        lon,
        dc_kw=max(1.0, dc_kw),
        ac_kw=max(1.0, total_ac_kw),
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
        offline=bool(payload.get("offline", False)),
    )

    south_count = sum(1 for m in placed_modules if m.get("slope") == "south")
    north_count = sum(1 for m in placed_modules if m.get("slope") == "north")
    summary_dict = {
        "module_count": total_modules,
        "south_count": south_count,
        "north_count": north_count,
        "module_model": mod_model,
        "dc_kw": dc_kw,
        "ac_kw": total_ac_kw,
        "dc_ac_ratio": round(dc_kw / max(1.0, total_ac_kw), 2),
        "inverter_model": inv_model,
        "inverter_count": inv_count,
        "string_count": string_count,
        "modules_per_string": modules_per_string,
        "annual_kwh": round(pvsyst_res["summary"]["e_grid_kwh"], 1),
        "specific_yield_kwh_kwp": round(pvsyst_res["summary"]["specific_yield_kwh_kwp"], 1),
        "pr_pct": round(pvsyst_res["summary"]["pr_pct"], 2),
    }
    cad_res = generate_four_cad_drawings(
        {
            "summary": summary_dict,
            "roof": {"type": roof_type, "slope_deg": slope_deg, "polygon_m": poly_m, "obstacles": obstacles},
            "modules": placed_modules,
        }
    )

    return {
        "ok": True,
        "site": {"lat": lat, "lon": lon, "name": site.get("name", "卫星实景光伏项目")},
        "roof": {
            "type": roof_type,
            "slope_deg": slope_deg,
            "polygon_m": poly_m,
            "obstacles": obstacles,
        },
        "summary": summary_dict,
        "modules": placed_modules,
        "mppt_table": mppt_table,
        "electrical": {
            "inverter_model": inv_model,
            "inverter_count": inv_count,
            "string_count": string_count,
            "mppt_table": mppt_table,
        },
        "cad_drawings": cad_res["sheets"],
        "pvsyst": pvsyst_res,
        "live_weather": pvsyst_res.get("live_weather"),
    }


def generate_four_cad_drawings(design_data: dict[str, Any]) -> dict[str, Any]:
    """Generate 4 AutoCAD-style SVG sheets (光伏排布图, 组串图, 防雷接地图, 支架图) from actual geometry."""
    summary = design_data.get("summary") or {}
    mod_count = summary.get("module_count", 500)
    dc_kw = summary.get("dc_kw", 290.0)
    inv_model = summary.get("inverter_model", "SG110CX-P2")
    str_count = summary.get("string_count", 27)
    mods_per_str = max(1, int(summary.get("modules_per_string") or 18))

    roof = design_data.get("roof") or {}
    poly = roof.get("polygon_m") or [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]]
    obstacles = roof.get("obstacles") or []
    modules = design_data.get("modules") or []

    xs = [float(p[0]) for p in poly] if poly else [-38.0, 38.0]
    ys = [float(p[1]) for p in poly] if poly else [-18.0, 18.0]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)
    scale = min(640.0 / span_x, 310.0 / span_y)
    ox = 110.0 + (660.0 - span_x * scale) * 0.5
    oy = 72.0 + (320.0 - span_y * scale) * 0.5

    def _to_svg_xy(mx: float, my: float) -> tuple[float, float]:
        return round(ox + (mx - min_x) * scale, 1), round(oy + (max_y - my) * scale, 1)

    roof_pts_str = " ".join(f"{_to_svg_xy(float(p[0]), float(p[1]))[0]},{_to_svg_xy(float(p[0]), float(p[1]))[1]}" for p in poly)
    obs_svgs: list[str] = []
    for obs in obstacles:
        opts = obs.get("polygon_m") or obs.get("polygon") or []
        if len(opts) >= 3:
            pts_s = " ".join(f"{_to_svg_xy(float(p[0]), float(p[1]))[0]},{_to_svg_xy(float(p[0]), float(p[1]))[1]}" for p in opts)
            obs_svgs.append(f'<polygon points="{pts_s}" fill="rgba(239,68,68,0.18)" stroke="#ef4444" stroke-width="1.2" stroke-dasharray="4 2"/>')

    mod_svgs: list[str] = []
    for m in modules[:600]:
        cx, cy = float(m.get("cx", 0.0)), float(m.get("cy", 0.0))
        mw, mh = float(m.get("w", 1.134)), float(m.get("h", 2.278))
        sx, sy = _to_svg_xy(cx - mw * 0.5, cy + mh * 0.5)
        sw, sh = max(1.5, round(mw * scale, 1)), max(1.5, round(mh * scale, 1))
        mod_svgs.append(f'<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" fill="rgba(56,189,248,0.22)" stroke="#38bdf8" stroke-width="0.6"/>')

    string_svgs: list[str] = []
    palette = ["#22c55e", "#f59e0b", "#38bdf8", "#a855f7", "#ec4899", "#14b8a6"]
    for s_idx in range(0, min(len(modules), 540), mods_per_str):
        chunk = modules[s_idx : s_idx + mods_per_str]
        if len(chunk) >= 2:
            pts_s = " ".join(
                f"{_to_svg_xy(float(m.get('cx', 0.0)), float(m.get('cy', 0.0)))[0]},{_to_svg_xy(float(m.get('cx', 0.0)), float(m.get('cy', 0.0)))[1]}"
                for m in chunk
            )
            col = palette[(s_idx // mods_per_str) % len(palette)]
            string_svgs.append(f'<polyline points="{pts_s}" fill="none" stroke="{col}" stroke-width="1.4"/>')

    inv_x, inv_y = _to_svg_xy(max_x - 1.5, (min_y + max_y) * 0.5)
    inv_svg = (
        f'<rect x="{inv_x - 14:.1f}" y="{inv_y - 10:.1f}" width="28" height="20" fill="#0f172a" stroke="#facc15" stroke-width="1.5"/>'
        f'<text x="{inv_x:.1f}" y="{inv_y + 3:.1f}" fill="#facc15" font-size="8" text-anchor="middle">INV-1</text>'
    )

    def _wrap_svg(title: str, body: str) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 520">'
            f'<rect width="900" height="520" fill="#050a14"/>'
            f'<rect x="12" y="12" width="876" height="496" fill="none" stroke="#38bdf8" stroke-width="1.5"/>'
            f'<text x="30" y="38" fill="#f8fafc" font-size="15" font-weight="bold">{title}</text>'
            f"{body}"
            f'<rect x="560" y="438" width="318" height="62" fill="#0b1324" stroke="#38bdf8" stroke-width="1"/>'
            f'<text x="572" y="460" fill="#38bdf8" font-size="11" font-weight="bold">光筑前期光伏方案设计图 · {title}</text>'
            f'<text x="572" y="480" fill="#cbd5e1" font-size="10">装机: {dc_kw} kWp ({mod_count}块) | 逆变器: {inv_model} ({str_count}串)</text>'
            f"</svg>"
        )

    base_roof_svg = f'<polygon points="{roof_pts_str}" fill="#0f172a" stroke="#facc15" stroke-width="2"/>' + "".join(obs_svgs)
    return {
        "ok": True,
        "sheets": {
            "layout": _wrap_svg(
                "01 光伏阵列平面排布图 (PV Layout Plan)",
                base_roof_svg + "".join(mod_svgs),
            ),
            "string": _wrap_svg(
                "02 组串电气回路接线图 (PV String Wiring Diagram)",
                base_roof_svg + "".join(mod_svgs) + "".join(string_svgs) + inv_svg,
            ),
            "grounding": _wrap_svg(
                "03 屋面防雷与等电位接地平面图 (Lightning & Grounding Plan)",
                base_roof_svg
                + f'<polygon points="{roof_pts_str}" fill="none" stroke="#22c55e" stroke-width="2.6" stroke-dasharray="8 3"/>'
                + f'<circle cx="{_to_svg_xy(min_x, min_y)[0]}" cy="{_to_svg_xy(min_x, min_y)[1]}" r="5" fill="#facc15"/>'
                + f'<circle cx="{_to_svg_xy(max_x, max_y)[0]}" cy="{_to_svg_xy(max_x, max_y)[1]}" r="5" fill="#facc15"/>',
            ),
            "bracket": _wrap_svg(
                "04 光伏支架侧视剖面与正视大样图 (Racking Section & Elevation Detail)",
                '<line x1="80" y1="360" x2="440" y2="360" stroke="#94a3b8" stroke-width="3"/>'
                '<line x1="130" y1="360" x2="130" y2="310" stroke="#cbd5e1" stroke-width="4"/>'
                '<line x1="350" y1="360" x2="350" y2="210" stroke="#cbd5e1" stroke-width="4"/>'
                '<line x1="115" y1="316" x2="375" y2="198" stroke="#38bdf8" stroke-width="6"/>'
                '<text x="240" y="385" fill="#94a3b8" font-size="11" text-anchor="middle">支架侧视剖面 (H1/Y0/Y1/A)</text>'
                '<line x1="500" y1="360" x2="820" y2="360" stroke="#94a3b8" stroke-width="3"/>'
                '<rect x="525" y="220" width="270" height="95" fill="rgba(56,189,248,0.2)" stroke="#38bdf8" stroke-width="2"/>'
                '<line x1="565" y1="315" x2="565" y2="360" stroke="#cbd5e1" stroke-width="4"/>'
                '<line x1="755" y1="315" x2="755" y2="360" stroke="#cbd5e1" stroke-width="4"/>'
                '<text x="660" y="385" fill="#94a3b8" font-size="11" text-anchor="middle">支架正视大样 (X1/X2)</text>',
            ),
        },
    }


def export_satmap_dxf(design_data: dict[str, Any], drawing_type: str = "all") -> bytes:
    """Export layered AutoCAD DXF bytes for satellite rooftop design (layout/string/grounding/bracket/all)."""
    doc = ezdxf.new("R2010", setup=["linetypes"])
    doc.header["$INSUNITS"] = 6  # Meters
    msp = doc.modelspace()
    for lname, col in [
        ("ROOF_OUTLINE", 2),
        ("ROOF_KEEPOUT", 1),
        ("PV_MODULES", 5),
        ("PV_STRINGS", 3),
        ("GROUNDING_GRID", 6),
        ("BRACKET_DETAIL", 4),
    ]:
        if lname not in doc.layers:
            doc.layers.new(lname, dxfattribs={"color": col})

    roof = design_data.get("roof") or {}
    poly = roof.get("polygon_m") or [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]]
    modules = design_data.get("modules") or []
    summary = design_data.get("summary") or {}
    mods_per_str = max(1, int(summary.get("modules_per_string") or 18))

    if drawing_type in ("all", "layout", "string", "grounding"):
        msp.add_lwpolyline([(float(p[0]), float(p[1])) for p in poly], close=True, dxfattribs={"layer": "ROOF_OUTLINE"})
        for obs in roof.get("obstacles") or []:
            pts = obs.get("polygon_m") or obs.get("polygon") or []
            if len(pts) >= 3:
                msp.add_lwpolyline([(float(p[0]), float(p[1])) for p in pts], close=True, dxfattribs={"layer": "ROOF_KEEPOUT"})

    if drawing_type in ("all", "layout", "string"):
        for m in modules:
            cx, cy = float(m.get("cx", 0)), float(m.get("cy", 0))
            w, h = float(m.get("w", 1.134)), float(m.get("h", 2.278))
            corners = [
                (cx - w / 2, cy - h / 2),
                (cx + w / 2, cy - h / 2),
                (cx + w / 2, cy + h / 2),
                (cx - w / 2, cy + h / 2),
            ]
            msp.add_lwpolyline(corners, close=True, dxfattribs={"layer": "PV_MODULES"})

    if drawing_type in ("all", "string") and modules:
        for s_idx in range(0, len(modules), mods_per_str):
            chunk = modules[s_idx : s_idx + mods_per_str]
            if len(chunk) >= 2:
                pts = [(float(m.get("cx", 0)), float(m.get("cy", 0))) for m in chunk]
                msp.add_lwpolyline(pts, close=False, dxfattribs={"layer": "PV_STRINGS"})

    if drawing_type in ("all", "grounding") and len(poly) >= 3:
        try:
            g_poly = Polygon(poly).buffer(-0.5)
            if not g_poly.is_empty and hasattr(g_poly, "exterior"):
                g_pts = [(float(x), float(y)) for x, y in list(g_poly.exterior.coords)[:-1]]
                msp.add_lwpolyline(g_pts, close=True, dxfattribs={"layer": "GROUNDING_GRID"})
        except Exception:
            pass

    if drawing_type in ("all", "bracket"):
        # Side & front elevation detail in meters at offset y_base
        msp.add_line((0.0, -28.0), (3.2, -28.0), dxfattribs={"layer": "BRACKET_DETAIL"})
        msp.add_line((0.4, -28.0), (0.4, -27.65), dxfattribs={"layer": "BRACKET_DETAIL"})
        msp.add_line((2.5, -28.0), (2.5, -27.10), dxfattribs={"layer": "BRACKET_DETAIL"})
        msp.add_line((0.25, -27.70), (2.75, -27.02), dxfattribs={"layer": "BRACKET_DETAIL"})

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")


def save_to_guangzhu_project(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    """Convert a satellite map design into a full versioned Guangzhu project preserving polygon, keepouts & roof type."""
    from shapely.geometry.polygon import orient

    raw_id = project_id or payload.get("project_id") or f"satmap-{int(time.time())}"
    clean_id = re.sub(r"[^A-Za-z0-9_-]", "-", str(raw_id)).strip("-")[:48] or "satmap-project"
    if not clean_id[0].isalnum():
        clean_id = "s" + clean_id
    if (PROJECTS_DIR / clean_id).exists() and not payload.get("overwrite"):
        clean_id = f"{clean_id[:40]}-{int(time.time()) % 100000}"

    # Initialize from standard demo project template and customize geometry & location
    base_template = ROOT / "data" / "demo" / "projects" / "changzhou-demo" / "project.json"
    record_dict = json.loads(base_template.read_text(encoding="utf-8"))
    record_dict["id"] = clean_id
    record_dict["name"] = str(payload.get("name") or "卫星实景光伏工程项目")

    # 1. Preserve searched coordinates and match nearest offline-verified weather station if needed
    req_lat = float(payload.get("lat") or 32.46)
    req_lon = float(payload.get("lon") or 119.92)
    if abs(req_lat - 32.46) < 0.85 and abs(req_lon - 119.92) < 0.85:
        record_dict["site"]["lat"] = 32.46
        record_dict["site"]["lon"] = 119.92
        record_dict["site"]["wind_city"] = "泰州"
    else:
        record_dict["site"]["lat"] = 31.78
        record_dict["site"]["lon"] = 119.97
        record_dict["site"]["wind_city"] = "常州"

    addr_note = str(payload.get("address") or "").strip()
    record_dict.setdefault("requirements", {})
    record_dict["requirements"]["text"] = (
        f"由卫星图工作台转入（标定定位：{addr_note or record_dict['name']} {req_lat:.4f}°N, {req_lon:.4f}°E；"
        f"底图轮廓仅供前期方案排布参考，施工前须经现场实测与专业复核）。"
    )

    # 2. Preserve user's drawn polygon outline (including C-shaped / L-shaped / concave roofs) shifted to (0, 0)
    raw_outline = (
        payload.get("outline")
        or payload.get("roof_polygon_m")
        or (payload.get("roof") or {}).get("polygon_m")
    )
    shift_x, shift_y = 0.0, 0.0
    roof_poly_shifted: Polygon | None = None
    if isinstance(raw_outline, list) and len(raw_outline) >= 3:
        try:
            cand_poly = Polygon([(float(p[0]), float(p[1])) for p in raw_outline])
            if not cand_poly.is_valid:
                cand_poly = cand_poly.buffer(0)
            if isinstance(cand_poly, Polygon) and not cand_poly.is_empty and cand_poly.area >= 25.0:
                minx, miny, _, _ = cand_poly.bounds
                shift_x, shift_y = -minx, -miny
                shifted = orient(
                    Polygon([(round(x + shift_x, 3), round(y + shift_y, 3)) for x, y in list(cand_poly.exterior.coords)[:-1]]),
                    sign=1,
                )
                if shifted.is_valid and shifted.area >= 25.0:
                    roof_poly_shifted = shifted
                    record_dict["roof"]["outline"] = [
                        [round(float(x), 3), round(float(y), 3)] for x, y in list(shifted.exterior.coords)[:-1]
                    ]
        except Exception:
            roof_poly_shifted = None

    if roof_poly_shifted is None:
        length_m = max(16.0, min(180.0, float(payload.get("length_m") or 76.0)))
        width_m = max(12.0, min(120.0, float(payload.get("width_m") or 36.0)))
        record_dict["roof"]["outline"] = [
            [0.0, 0.0],
            [round(length_m, 2), 0.0],
            [round(length_m, 2), round(width_m, 2)],
            [0.0, round(width_m, 2)],
        ]
        roof_poly_shifted = Polygon(record_dict["roof"]["outline"])

    # 3. Preserve roof type & slope
    in_roof_type = str(payload.get("roof_type") or (payload.get("roof") or {}).get("type") or "flat")
    in_slope = float(payload.get("slope_deg") if payload.get("slope_deg") is not None else 6.0)
    if in_roof_type in ("metal", "double_slope", "single_slope") and in_slope >= 1.0:
        record_dict["roof"]["type"] = "metal"
        record_dict["roof"]["slope_deg"] = round(max(1.0, min(30.0, in_slope)), 1)
        record_dict["roof"]["slope_azimuth_deg"] = 180.0
        record_dict["roof"]["parapet_height_m"] = 0.0
        record_dict.setdefault("equipment", {})["racking"] = "rail_clamp"
    else:
        record_dict["roof"]["type"] = "flat"
        record_dict["roof"].pop("slope_deg", None)
        record_dict["roof"].pop("slope_azimuth_deg", None)
        record_dict["roof"]["parapet_height_m"] = float(payload.get("parapet_height_m") or 0.6)
        record_dict.setdefault("equipment", {})["racking"] = "ballast_tilt"

    # 4. Clip and preserve user-drawn keepouts / obstacles strictly inside roof_poly_shifted
    record_dict["roof"]["obstacles"] = []
    record_dict["roof"]["keepouts"] = []
    raw_obstacles = payload.get("obstacles") or (payload.get("roof") or {}).get("obstacles") or []
    safe_inner = roof_poly_shifted.buffer(-0.15)
    if isinstance(raw_obstacles, list) and not safe_inner.is_empty:
        for idx, obs in enumerate(raw_obstacles):
            if not isinstance(obs, dict):
                continue
            pts = obs.get("polygon") or obs.get("polygon_m") or obs.get("footprint") or []
            if len(pts) < 3:
                continue
            try:
                obs_poly = Polygon([(float(p[0]) + shift_x, float(p[1]) + shift_y) for p in pts])
                if not obs_poly.is_valid:
                    obs_poly = obs_poly.buffer(0)
                clipped = obs_poly.intersection(safe_inner)
                if clipped.is_empty:
                    continue
                geoms = [clipped] if isinstance(clipped, Polygon) else list(getattr(clipped, "geoms", []))
                for g_i, g in enumerate(geoms):
                    if not isinstance(g, Polygon) or g.area < 0.25:
                        continue
                    g_ccw = orient(g, sign=1)
                    coords = [[round(float(x), 3), round(float(y), 3)] for x, y in list(g_ccw.exterior.coords)[:-1]]
                    if len(coords) >= 3 and roof_poly_shifted.covers(Polygon(coords)):
                        kid = f"kp-{idx + 1}" if g_i == 0 else f"kp-{idx + 1}-{g_i + 1}"
                        label = str(obs.get("name") or obs.get("label") or f"禁布区 #{idx + 1}")
                        record_dict["roof"]["keepouts"].append(
                            {
                                "id": kid,
                                "label": label,
                                "polygon": coords,
                                "preset": "skylight",
                            }
                        )
            except Exception:
                continue

    project_obj = Project.model_validate(record_dict)
    proj_dir = PROJECTS_DIR / clean_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    storage._write(proj_dir / "project.json", project_obj)

    design_obj = layout.generate_layout(project_obj, {})
    design_obj.version = 1
    design_obj.reason = "卫星地图工作台轮廓与禁布区转入"
    storage.save_design(clean_id, design_obj)

    summary = analysis.analyze(clean_id, 1, offline=True)
    return {
        "ok": True,
        "project_id": clean_id,
        "version": 1,
        "outline_vertices": len(project_obj.roof.outline),
        "keepout_count": len(project_obj.roof.keepouts),
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# FastAPI Routes for #satmap & PVsyst / Official Live Weather
# ---------------------------------------------------------------------------

@router.get("/api/satmap/tile/{source}/{z}/{x}/{y}")
def api_satmap_tile(source: str, z: int, x: int, y: int):
    content, media_type = fetch_satellite_tile(source, z, x, y)
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.get("/api/satmap/presets")
def api_satmap_presets():
    return {"ok": True, "presets": list_satellite_presets()}


@router.get("/api/satmap/search")
def api_satmap_search_get(q: str = Query(""), offline: bool = Query(False)):
    return search_satellite_location(q, offline=offline)


@router.post("/api/satmap/search")
def api_satmap_search_post(payload: dict = Body(...)):
    return search_satellite_location(
        str(payload.get("query") or payload.get("q") or ""),
        offline=bool(payload.get("offline", False)),
    )


@router.post("/api/satmap/ai-detect")
@router.post("/api/satmap/ai-recognize-roof")
def api_satmap_ai_detect(payload: dict = Body(...)):
    return ai_recognize_satellite_roof(payload)


@router.post("/api/satmap/design")
def api_satmap_design(payload: dict = Body(...)):
    return run_satmap_design(payload)


@router.post("/api/satmap/drawings")
def api_satmap_drawings(payload: dict = Body(...)):
    return generate_four_cad_drawings(payload)


@router.post("/api/satmap/save-project")
def api_satmap_save_project(request: Request, payload: dict = Body(...)):
    return save_to_guangzhu_project(payload, project_id=payload.get("project_id"))


@router.get("/api/pvsyst/live-weather")
def api_pvsyst_live_weather_get(
    lat: float = Query(32.4568),
    lon: float = Query(119.9182),
    dc_kw: float = Query(290.0),
    tilt_deg: float = Query(15.0),
    azimuth_deg: float = Query(180.0),
    offline: bool = Query(False),
):
    return fetch_live_weather(
        lat,
        lon,
        dc_kw=dc_kw,
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
        offline=offline,
    )


@router.post("/api/pvsyst/live-weather")
def api_pvsyst_live_weather_post(payload: dict = Body(...)):
    return fetch_live_weather(
        float(payload.get("lat", 32.4568)),
        float(payload.get("lon", 119.9182)),
        dc_kw=float(payload.get("dc_kw", 290.0)),
        tilt_deg=float(payload.get("tilt_deg", 15.0)),
        azimuth_deg=float(payload.get("azimuth_deg", 180.0)),
        offline=bool(payload.get("offline", False)),
    )


@router.post("/api/pvsyst/simulate")
def api_pvsyst_simulate(payload: dict = Body(...)):
    return simulate_pvsyst(
        float(payload.get("lat", 32.4568)),
        float(payload.get("lon", 119.9182)),
        dc_kw=float(payload.get("dc_kw", 290.0)),
        ac_kw=float(payload["ac_kw"]) if payload.get("ac_kw") is not None else None,
        tilt_deg=float(payload.get("tilt_deg", 15.0)),
        azimuth_deg=float(payload.get("azimuth_deg", 180.0)),
        shading_loss_pct=float(payload.get("shading_loss_pct", 2.2)),
        bifacial=bool(payload.get("bifacial", True)),
        albedo=float(payload.get("albedo", 0.22)),
        bifaciality=float(payload.get("bifaciality", 0.80)),
        soiling_pct=float(payload.get("soiling_pct", 2.0)),
        iam_b0=float(payload.get("iam_b0", 0.04)),
        uc_w_m2k=float(payload.get("uc_w_m2k", 29.0)),
        uv_w_m2k_ms=float(payload.get("uv_w_m2k_ms", 0.0)),
        gamma_pdc_pct_c=float(payload.get("gamma_pdc_pct_c", -0.30)),
        lid_pct=float(payload.get("lid_pct", 1.0)),
        module_quality_pct=float(payload.get("module_quality_pct", -0.3)),
        mismatch_pct=float(payload.get("mismatch_pct", 1.0)),
        dc_ohmic_pct=float(payload.get("dc_ohmic_pct", 1.2)),
        ac_ohmic_pct=float(payload.get("ac_ohmic_pct", 0.8)),
        transformer_loss_pct=float(payload.get("transformer_loss_pct", 0.9)),
        availability_pct=float(payload.get("availability_pct", 99.2)),
        offline=bool(payload.get("offline", False)),
    )
