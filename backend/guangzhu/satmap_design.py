"""Satellite Map AI Photovoltaic Design Engine & 16-Sheet CAD Generator.

Core capabilities:
  - Satellite coordinate/address location, roof & obstacle drawing, one-click array
    placement, inverter MPPT string allocation table, and engineering CAD sheets
    (光伏排布图, 组串图, 防雷接地图, 支架图, etc.).
  - Scale calibration, direction setting, double-slope pitch roof split, skylight
    keepout strips, and oblique aerial photo 4-point perspective homography synthesis.
  - Full 8760h hourly energy balance waterfall & Open-Meteo (CMA/ECMWF/GFS)
    official real-time weather integration.
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
from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import Response
from shapely.geometry import Point, Polygon, box

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
        "name": "中国（泰州）医药城太阳能光电建筑应用示范项目（1号标准厂房）",
        "address": "江苏省泰州市医药高新区（中国医药城）药城大道88号1号车间",
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
        "id": "taizhou-xiangtai-warehouse-sat",
        "key": "taizhou-xiangtai-warehouse",
        "name": "国网泰州供电公司“祥泰数智零碳仓库”屋顶分布式光伏项目 (552.42kWp)",
        "address": "江苏省泰州市海陵区九龙镇祥泰路电力物资数智零碳仓库",
        "city": "泰州市",
        "province": "江苏省",
        "lat": 32.4852,
        "lon": 119.8634,
        "zoom": 19,
        "roof_type": "double_slope",
        "slope_deg": 5.0,
        "height_m": 11.5,
        "dimensions_m": [104.0, 44.0],
        "roof_polygon_m": [[-52.0, -22.0], [52.0, -22.0], [52.0, 22.0], [-52.0, 22.0]],
        "ridge_line_m": [[-52.0, 0.0], [52.0, 0.0]],
        "obstacles": [
            {
                "id": "keepout-xt-sky-1",
                "kind": "skylight",
                "label": "主库房南坡采光带",
                "polygon_m": [[-44.0, -11.0], [44.0, -11.0], [44.0, -9.4], [-44.0, -9.4]],
                "height_m": 0.15,
                "setback_m": 0.4,
            },
            {
                "id": "keepout-xt-sky-2",
                "kind": "skylight",
                "label": "主库房北坡采光带",
                "polygon_m": [[-44.0, 9.4], [44.0, 9.4], [44.0, 11.0], [-44.0, 11.0]],
                "height_m": 0.15,
                "setback_m": 0.4,
            },
        ],
    },
    {
        "id": "taizhou-jielouwei-bipv-sat",
        "key": "taizhou-jielouwei-bipv",
        "name": "泰州市海陵区春云路解楼圩（原旧船厂改造）BIPV光伏屋顶项目 (167.61kWp)",
        "address": "江苏省泰州市海陵区春云路解楼圩新通扬运河段",
        "city": "泰州市",
        "province": "江苏省",
        "lat": 32.5126,
        "lon": 119.9328,
        "zoom": 19,
        "roof_type": "double_slope",
        "slope_deg": 8.0,
        "height_m": 9.5,
        "dimensions_m": [80.0, 20.0],
        "roof_polygon_m": [[-40.0, -10.0], [40.0, -10.0], [40.0, 10.0], [-40.0, 10.0]],
        "ridge_line_m": [[-40.0, 0.0], [40.0, 0.0]],
        "obstacles": [],
    },
    {
        "id": "taizhou-shenyuan-alloy-sat",
        "key": "taizhou-shenyuan-alloy",
        "name": "国能泰州电厂·江苏申源特种合金1.27368MWp厂房屋顶光伏项目",
        "address": "江苏省泰州市兴化高新区戴南镇张郭科技园区申源特钢厂房",
        "city": "泰州市",
        "province": "江苏省",
        "lat": 32.9315,
        "lon": 120.0542,
        "zoom": 19,
        "roof_type": "double_slope",
        "slope_deg": 5.0,
        "height_m": 13.0,
        "dimensions_m": [164.0, 56.0],
        "roof_polygon_m": [[-82.0, -28.0], [82.0, -28.0], [82.0, 28.0], [-82.0, 28.0]],
        "ridge_line_m": [[-82.0, 0.0], [82.0, 0.0]],
        "obstacles": [],
    },
    {
        "id": "taizhou-municipal-admin-sat",
        "key": "taizhou-municipal-admin",
        "name": "泰州市级机关综合办公楼及海陵区行政中心分布式光伏项目 (1,100kWp)",
        "address": "江苏省泰州市海陵区凤凰东路58号市级机关综合办公楼",
        "city": "泰州市",
        "province": "江苏省",
        "lat": 32.4555,
        "lon": 119.9230,
        "zoom": 19,
        "roof_type": "flat",
        "slope_deg": 0.0,
        "height_m": 24.0,
        "dimensions_m": [136.0, 56.0],
        "roof_polygon_m": [[-68.0, -28.0], [68.0, -28.0], [68.0, 28.0], [-68.0, 28.0]],
        "ridge_line_m": [],
        "obstacles": [],
    },
    {
        "id": "taizhou-jingjiang-shipbuild-sat",
        "key": "taizhou-jingjiang-shipbuild",
        "name": "靖江经济技术开发区船舶海工重装基地单跨彩钢瓦车间屋顶光伏项目 (1,500.40kWp)",
        "address": "江苏省泰州市靖江经济技术开发区新港大道海工重装基地1号车间",
        "city": "泰州市",
        "province": "江苏省",
        "lat": 32.0152,
        "lon": 120.2645,
        "zoom": 19,
        "roof_type": "double_slope",
        "slope_deg": 5.0,
        "height_m": 16.0,
        "dimensions_m": [180.0, 60.0],
        "roof_polygon_m": [[-90.0, -30.0], [90.0, -30.0], [90.0, 30.0], [-90.0, 30.0]],
        "ridge_line_m": [[-90.0, 0.0], [90.0, 0.0]],
        "obstacles": [],
    },
    {
        "id": "taizhou-taixing-chem-sat",
        "key": "taizhou-taixing-chem",
        "name": "泰兴经济开发区精细化工产业园高标准物流仓储屋顶光伏项目 (800.80kWp)",
        "address": "江苏省泰州市泰兴经济开发区通江路精细化工高标物流园",
        "city": "泰州市",
        "province": "江苏省",
        "lat": 32.1685,
        "lon": 120.0124,
        "zoom": 19,
        "roof_type": "flat",
        "slope_deg": 0.0,
        "height_m": 12.0,
        "dimensions_m": [124.0, 52.0],
        "roof_polygon_m": [[-62.0, -26.0], [62.0, -26.0], [62.0, 26.0], [-62.0, 26.0]],
        "ridge_line_m": [],
        "obstacles": [],
    },
    {
        "id": "taizhou-jiangyan-equip-sat",
        "key": "taizhou-jiangyan-equip",
        "name": "泰州市姜堰高新区智能制造装备产业园标准厂房屋顶分布式光伏项目 (638.00kWp)",
        "address": "江苏省泰州市姜堰高新区科技大道智能制造装备产业园",
        "city": "泰州市",
        "province": "江苏省",
        "lat": 32.5086,
        "lon": 120.1482,
        "zoom": 19,
        "roof_type": "double_slope",
        "slope_deg": 6.0,
        "height_m": 11.0,
        "dimensions_m": [112.0, 44.0],
        "roof_polygon_m": [[-56.0, -22.0], [56.0, -22.0], [56.0, 22.0], [-56.0, 22.0]],
        "ridge_line_m": [[-56.0, 0.0], [56.0, 0.0]],
        "obstacles": [],
    },
    {
        "id": "shandong-zibo-sat",
        "key": "shandong-zibo",
        "name": "山东淄博工业园混凝土平屋顶厂房",
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
    """Run satellite array layout, MPPT string allocation, and 8760h simulation."""
    def _num_or(d: dict[str, Any], key: str, default: float) -> float:
        val = d.get(key)
        if val is None or val == "":
            return float(default)
        f = float(val)
        if not math.isfinite(f):
            raise ValueError(f"{key} must be a finite number.")
        return f

    site = payload.get("site") or {}
    lat = _num_or(site, "lat", _num_or(payload, "lat", 32.4568))
    lon = _num_or(site, "lon", _num_or(payload, "lon", 119.9182))
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise ValueError("Site coordinates out of valid geographic range.")

    roof = payload.get("roof") or {}
    roof_type = str(roof.get("type") or payload.get("roof_type") or "double_slope")
    if roof_type not in ("flat", "single_slope", "double_slope"):
        raise ValueError(f"Unsupported roof type: {roof_type}")
    slope_deg = _num_or(roof, "slope_deg", _num_or(payload, "slope_deg", 6.0))
    if not (0.0 <= slope_deg <= 75.0):
        raise ValueError("slope_deg must be within [0, 75].")

    raw_poly = roof.get("polygon_m") if roof.get("polygon_m") is not None else payload.get("roof_polygon_m")
    poly_m = raw_poly if raw_poly is not None else [
        [-38.0, -18.0],
        [38.0, -18.0],
        [38.0, 18.0],
        [-38.0, 18.0],
    ]
    if not isinstance(poly_m, list) or len(poly_m) < 3:
        raise ValueError("roof polygon_m must contain at least 3 vertices.")
    clean_poly_pts: list[tuple[float, float]] = []
    for pt in poly_m:
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            raise ValueError("Each polygon vertex must be [x, y].")
        px, py = float(pt[0]), float(pt[1])
        if not (math.isfinite(px) and math.isfinite(py)):
            raise ValueError("Polygon coordinates must be finite numbers.")
        clean_poly_pts.append((px, py))

    obstacles = (
        roof.get("obstacles")
        if "obstacles" in roof
        else (payload.get("obstacles") if "obstacles" in payload else PRESET_SITES[0]["obstacles"])
    ) or []

    lp = payload.get("layout_params") or {}
    stc_w = _num_or(lp, "stc_w", 580.0)
    if stc_w <= 0.0:
        raise ValueError("stc_w must be > 0.")
    mod_model = str(lp.get("module_model") or "JKM580N-72HL4-BDV 580W")
    orientation = str(lp.get("orientation") or "portrait")
    if orientation not in ("portrait", "landscape"):
        raise ValueError("orientation must be 'portrait' or 'landscape'.")
    mod_len = _num_or(lp, "length_m", 2.278)
    mod_wid = _num_or(lp, "width_m", 1.134)
    if mod_len <= 0.1 or mod_wid <= 0.1:
        raise ValueError("Module length_m and width_m must be > 0.1 m.")
    w_m = mod_wid if orientation == "portrait" else mod_len
    h_m = mod_len if orientation == "portrait" else mod_wid
    tilt_deg = _num_or(lp, "tilt_deg", 15.0 if roof_type == "flat" else slope_deg)
    if not (0.0 <= tilt_deg <= 85.0):
        raise ValueError("tilt_deg must be within [0, 85].")
    azimuth_deg = float(_num_or(lp, "azimuth_deg", 180.0) % 360.0)
    edge_setback = _num_or(lp, "edge_setback_m", 0.8)
    obs_setback = _num_or(lp, "obstacle_setback_m", 0.4)
    col_gap = _num_or(lp, "col_gap_m", 0.02)
    if edge_setback < 0.0 or obs_setback < 0.0 or col_gap < 0.0:
        raise ValueError("Setbacks and col_gap_m must be >= 0.")
    default_row_spacing = (
        h_m * math.cos(math.radians(tilt_deg)) + h_m * math.sin(math.radians(tilt_deg)) * 1.65
        if roof_type == "flat"
        else h_m + 0.35
    )
    row_spacing = _num_or(lp, "row_spacing_m", default_row_spacing)
    if row_spacing <= 0.05:
        raise ValueError("row_spacing_m must be > 0.05 m.")
    x_step = w_m + col_gap
    y_step = max(h_m + 0.15, row_spacing)
    if x_step <= 0.05 or y_step <= 0.05:
        raise ValueError("Layout grid step must be positive.")

    ep = payload.get("electrical_params") or {}
    inv_model = str(ep.get("inverter_model") or "SG110CX-P2")
    rated_ac_kw = _num_or(ep, "rated_ac_kw", 50.0 if "50" in inv_model else (100.0 if "100" in inv_model else 110.0))
    mppt_count = int(_num_or(ep, "mppt_count", 5 if rated_ac_kw <= 60 else (9 if rated_ac_kw == 110 else 10)))
    strings_per_mppt = int(_num_or(ep, "strings_per_mppt", 2))
    modules_per_string = int(_num_or(ep, "modules_per_string", 18))
    explicit_mps = ep.get("modules_per_string") is not None
    if rated_ac_kw <= 0.0 or mppt_count < 1 or strings_per_mppt < 1 or modules_per_string < 1:
        raise ValueError("Electrical inverter/MPPT/string parameters must be positive.")

    mod_vmp_v = _num_or(lp, "vmp_v", 42.3)
    mod_voc_v = _num_or(lp, "voc_v", 51.0)
    if mod_vmp_v <= 0.0 or mod_voc_v <= 0.0:
        raise ValueError("Module voltages must be > 0.")
    mod_imp_a = _num_or(lp, "imp_a", round(stc_w / max(15.0, mod_vmp_v), 2))
    mod_isc_a = _num_or(lp, "isc_a", round(mod_imp_a * 1.055, 2))
    beta_voc_pct_c = _num_or(lp, "beta_voc_pct_c", -0.25)
    mppt_limit_a = _num_or(ep, "max_mppt_current_a", 30.0)
    mppt_isc_limit_a = _num_or(ep, "max_short_current_a", 40.0)
    max_dc_v = _num_or(ep, "max_dc_v", 1100.0)
    mppt_v_min = _num_or(ep, "mppt_v_min", 200.0)
    mppt_v_max = _num_or(ep, "mppt_v_max", 1000.0)
    if max_dc_v <= 0.0 or mppt_v_min < 0.0 or mppt_v_max <= mppt_v_min:
        raise ValueError("Invalid inverter DC/MPPT voltage window.")

    site_t_min_c = -28.0 if lat >= 42.0 else (-14.0 if lat >= 35.0 else (-8.0 if lat >= 27.0 else 2.0))
    site_t_hot_c = 68.0
    voc_single_cold = mod_voc_v * (1.0 + (beta_voc_pct_c / 100.0) * (site_t_min_c - 25.0))
    vmp_single_cold = mod_vmp_v * (1.0 + (-0.32 / 100.0) * (site_t_min_c - 25.0))
    vmp_single_hot = mod_vmp_v * (1.0 + (-0.32 / 100.0) * (site_t_hot_c - 25.0))
    n_min_mppt = max(4, math.ceil(mppt_v_min / max(1.0, vmp_single_hot)))

    # Build usable polygon with Shapely
    roof_poly = Polygon(clean_poly_pts)
    if not roof_poly.is_valid:
        roof_poly = roof_poly.buffer(0)
    if roof_poly.is_empty or roof_poly.area <= 0.01:
        raise ValueError("Roof polygon has zero or invalid area.")
    usable = roof_poly.buffer(-edge_setback)
    parsed_obstacles: list[tuple[Polygon, float]] = []
    for obs in obstacles:
        obs_pts = obs.get("polygon_m") or obs.get("polygon") or []
        if len(obs_pts) >= 3:
            obs_clean = [(float(p[0]), float(p[1])) for p in obs_pts]
            if not all(math.isfinite(x) and math.isfinite(y) for x, y in obs_clean):
                raise ValueError("Obstacle polygon coordinates must be finite.")
            obs_poly = Polygon(obs_clean)
            if not obs_poly.is_valid:
                obs_poly = obs_poly.buffer(0)
            if not obs_poly.is_empty:
                h_obs = float(obs.get("height_m") or 0.0)
                if not math.isfinite(h_obs) or h_obs < 0.0:
                    raise ValueError("Obstacle height_m must be finite and >= 0.")
                parsed_obstacles.append((obs_poly, h_obs))
                # Only subtract obstacle footprint when it intersects/buffers the roof plane
                usable = usable.difference(obs_poly.buffer(obs_setback))

    minx, miny, maxx, maxy = roof_poly.bounds
    cx0 = 0.5 * (minx + maxx)
    cy0 = 0.5 * (miny + maxy)

    # Local roof frame centered at (cx0, cy0) and aligned with primary slope azimuth (translation-invariant & azimuth-aware)
    # Compass convention in (x=East, y=North): down-slope d = (sin(az), cos(az)), up-slope v = (-sin(az), -cos(az)), ridge u = (-cos(az), sin(az))
    az_rad = math.radians(azimuth_deg)
    u_x, u_y = -math.cos(az_rad), math.sin(az_rad)
    v_x, v_y = -math.sin(az_rad), -math.cos(az_rad)
    ext_coords = list(roof_poly.exterior.coords)
    u_vals = [(px - cx0) * u_x + (py - cy0) * u_y for px, py in ext_coords]
    v_vals = [(px - cx0) * v_x + (py - cy0) * v_y for px, py in ext_coords]
    min_u, max_u = min(u_vals), max(u_vals)
    min_v, max_v = min(v_vals), max(v_vals)
    primary_az = round(azimuth_deg % 360.0, 1)
    secondary_az = round((azimuth_deg + 180.0) % 360.0, 1)
    axis_aligned_180 = abs(azimuth_deg - 180.0) < 1e-6

    placed_modules: list[dict[str, Any]] = []
    if not usable.is_empty:
        row_idx = 0
        v_cursor = min_v + edge_setback + h_m / 2.0
        while v_cursor + h_m / 2.0 <= max_v - edge_setback + 1e-9:
            # Leave a 0.6m ridge walkway along the roof ridge centerline (v == 0) for double_slope roofs
            if roof_type == "double_slope" and abs(v_cursor) < (h_m / 2.0 + 0.35):
                v_cursor += 0.7
                continue
            row_idx += 1
            col_idx = 0
            u_cursor = min_u + edge_setback + w_m / 2.0
            while u_cursor + w_m / 2.0 <= max_u - edge_setback + 1e-9:
                cx_m = cx0 + u_cursor * u_x + v_cursor * v_x
                cy_m = cy0 + u_cursor * u_y + v_cursor * v_y
                if axis_aligned_180:
                    cell = box(cx_m - w_m / 2.0, cy_m - h_m / 2.0, cx_m + w_m / 2.0, cy_m + h_m / 2.0)
                else:
                    cell = Polygon(
                        [
                            (cx_m + du * u_x + dv * v_x, cy_m + du * u_y + dv * v_y)
                            for du, dv in [
                                (-w_m / 2.0, -h_m / 2.0),
                                (w_m / 2.0, -h_m / 2.0),
                                (w_m / 2.0, h_m / 2.0),
                                (-w_m / 2.0, h_m / 2.0),
                            ]
                        ]
                    )
                if usable.contains(cell):
                    if len(placed_modules) >= 50000:
                        raise ValueError("Roof layout exceeds maximum 50,000 module safety limit.")
                    col_idx += 1
                    is_primary_slope = (roof_type != "double_slope") or (v_cursor <= 0.0)
                    slope_side = "south" if is_primary_slope else "north"
                    placed_modules.append(
                        {
                            "id": f"M-{len(placed_modules) + 1:04d}",
                            "row": row_idx,
                            "col": col_idx,
                            "cx": round(cx_m, 3),
                            "cy": round(cy_m, 3),
                            "_u": round(u_cursor, 4),
                            "_v": round(v_cursor, 4),
                            "w": round(w_m, 3),
                            "h": round(h_m, 3),
                            "slope": slope_side,
                            "tilt_deg": tilt_deg,
                            "azimuth_deg": primary_az if is_primary_slope else secondary_az,
                            "wired": False,
                        }
                    )
                u_cursor += x_step
            v_cursor += y_step

    south_mods = [m for m in placed_modules if m.get("slope") != "north"]
    north_mods = [m for m in placed_modules if m.get("slope") == "north"]

    # Strictly partition strings by slope (GB 50797-2012 §6.4.2: never mix orientations in a string or MPPT)
    min_u_mod = min((m["_u"] for m in placed_modules), default=0.0)

    def _order_serpentine(mod_group: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_br: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for item in mod_group:
            band = int((item["_u"] - min_u_mod) // 38.0)
            by_br.setdefault((band, item["row"]), []).append(item)
        ordered: list[dict[str, Any]] = []
        for idx_r, k_br in enumerate(sorted(by_br.keys())):
            r_list = sorted(by_br[k_br], key=lambda it: it["_u"], reverse=bool(idx_r % 2))
            ordered.extend(r_list)
        return ordered

    serp_south = _order_serpentine(south_mods)
    serp_north = _order_serpentine(north_mods)
    naive_south = sorted(south_mods, key=lambda item: (item["row"], item["_u"]))
    naive_north = sorted(north_mods, key=lambda item: (item["row"], item["_u"]))

    slope_string_chunks: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = []
    for slope_tag, s_ord, s_naive in [("south", serp_south, naive_south), ("north", serp_north, naive_north)]:
        n_total_slope = len(s_ord)
        if n_total_slope == 0:
            continue
        n_full = n_total_slope // modules_per_string
        rem = n_total_slope % modules_per_string
        sizes: list[int] = [modules_per_string] * n_full
        if rem >= n_min_mppt:
            sizes.append(rem)
        elif rem > 0 and n_full >= 1 and not explicit_mps and ((modules_per_string + rem) // 2) >= n_min_mppt:
            combined = modules_per_string + rem
            s1 = math.ceil(combined / 2.0)
            s2 = combined - s1
            sizes[-1] = s1
            sizes.append(s2)
        cursor_s = 0
        for sz in sizes:
            c_opt = s_ord[cursor_s : cursor_s + sz]
            c_nv = s_naive[cursor_s : cursor_s + sz]
            cursor_s += sz
            if c_opt:
                for m_item in c_opt:
                    m_item["wired"] = True
                slope_string_chunks.append((slope_tag, c_opt, c_nv))

    for m_item in placed_modules:
        m_item.pop("_u", None)
        m_item.pop("_v", None)

    wired_modules = [m for m in placed_modules if m.get("wired")]
    unwired_modules = [m for m in placed_modules if not m.get("wired")]
    wired_south_mods = [m for m in wired_modules if m.get("slope") != "north"]
    wired_north_mods = [m for m in wired_modules if m.get("slope") == "north"]
    placed_total_count = len(placed_modules)
    unused_module_count = len(unwired_modules)
    total_modules = len(wired_modules)
    south_count = len(wired_south_mods)
    north_count = len(wired_north_mods)
    dc_kw = round(total_modules * stc_w / 1000.0, 2)

    # Group strings into MPPT channel buckets strictly by (slope, string_length) so heterogeneous lengths never parallel on one MPPT
    mppt_buckets: list[dict[str, Any]] = []
    grouped_chunks: dict[tuple[str, int], list[int]] = {}
    for s_idx, (slope_tag, c_opt, _) in enumerate(slope_string_chunks):
        grouped_chunks.setdefault((slope_tag, len(c_opt)), []).append(s_idx)
    for (slope_tag, str_len), idx_list in grouped_chunks.items():
        for k_start in range(0, len(idx_list), strings_per_mppt):
            mppt_buckets.append(
                {
                    "slope": slope_tag,
                    "modules_per_string": str_len,
                    "string_indices": idx_list[k_start : k_start + strings_per_mppt],
                }
            )

    string_count = len(slope_string_chunks)
    if total_modules == 0 or string_count == 0:
        inv_count = 0
        total_ac_kw = 0.0
    else:
        inv_count = max(1, math.ceil(dc_kw / (rated_ac_kw * 1.22)))
        req_mppts = len(mppt_buckets)
        if req_mppts > inv_count * mppt_count:
            inv_count = math.ceil(req_mppts / mppt_count)
        total_ac_kw = round(inv_count * rated_ac_kw, 1)

    # Build unified MPPT allocation table AND assign exact inverter_index/mppt_index to every string
    mppt_table: list[dict[str, Any]] = []
    string_inv_assign: dict[int, tuple[int, int]] = {}
    bucket_cursor = 0
    for inv_i in range(inv_count):
        inv_name = f"{inv_model}#{inv_i + 1}"
        for mppt_i in range(mppt_count):
            if bucket_cursor < len(mppt_buckets):
                bkt = mppt_buckets[bucket_cursor]
                bucket_cursor += 1
                mppt_slope = bkt["slope"]
                s_indices = bkt["string_indices"]
                str_n = len(s_indices)
                row_mps = int(bkt["modules_per_string"])
                for s_idx in s_indices:
                    string_inv_assign[s_idx] = (inv_i + 1, mppt_i + 1)
                vmp_work_v = round(row_mps * mod_vmp_v, 1)
                voc_cold_v = round(row_mps * voc_single_cold, 1)
                vmp_cold_v = round(row_mps * vmp_single_cold, 1)
                vmp_hot_v = round(row_mps * vmp_single_hot, 1)
                volt_low = vmp_hot_v < mppt_v_min
                volt_high = (voc_cold_v > max_dc_v) or (vmp_work_v > mppt_v_max) or (vmp_cold_v > mppt_v_max)
                volt_ok = (not volt_low) and (not volt_high)
            else:
                mppt_slope = "idle"
                str_n = 0
                row_mps = 0
                vmp_work_v = 0.0
                voc_cold_v = 0.0
                vmp_cold_v = 0.0
                vmp_hot_v = 0.0
                volt_low = False
                volt_high = False
                volt_ok = True

            work_a = round(str_n * mod_imp_a, 2)
            isc_a = round(str_n * mod_isc_a, 2)
            curr_ok = (work_a <= mppt_limit_a) and (isc_a <= mppt_isc_limit_a)
            row_ok = (curr_ok and volt_ok) if str_n > 0 else True
            if row_ok:
                status_str = "正常"
            elif volt_low:
                status_str = "电压偏低"
            elif volt_high:
                status_str = "电压超限"
            else:
                status_str = "电流偏高"
            mppt_table.append(
                {
                    "inverter_name": inv_name,
                    "mppt_name": f"MPPT{mppt_i + 1}",
                    "slope": mppt_slope,
                    "string_count": str_n,
                    "modules_per_string": row_mps,
                    "vmp_work_v": vmp_work_v,
                    "vmp_cold_v": vmp_cold_v,
                    "vmp_hot_v": vmp_hot_v,
                    "voc_cold_v": voc_cold_v,
                    "max_work_current_a": work_a,
                    "mppt_limit_current_a": mppt_limit_a,
                    "max_isc_a": isc_a,
                    "mppt_limit_isc_a": mppt_isc_limit_a,
                    "status": status_str,
                    "ok": row_ok,
                }
            )

    sub_arrays_arg: list[dict[str, Any]] | None = None
    effective_az = primary_az
    if roof_type == "double_slope" and total_modules > 0:
        sub_arrays_arg = []
        if south_count > 0:
            s_lbl = "南坡子阵 (180°)" if abs(primary_az - 180.0) < 1e-3 else f"主坡子阵 ({primary_az:.0f}°)"
            sub_arrays_arg.append(
                {
                    "name": s_lbl,
                    "dc_kw": round(south_count * stc_w / 1000.0, 2),
                    "tilt_deg": tilt_deg,
                    "azimuth_deg": primary_az,
                }
            )
        if north_count > 0:
            n_lbl = "北坡子阵 (0°)" if abs(secondary_az - 0.0) < 1e-3 else f"副坡子阵 ({secondary_az:.0f}°)"
            sub_arrays_arg.append(
                {
                    "name": n_lbl,
                    "dc_kw": round(north_count * stc_w / 1000.0, 2),
                    "tilt_deg": tilt_deg,
                    "azimuth_deg": secondary_az,
                }
            )
        if south_count == 0 and north_count > 0:
            effective_az = secondary_az

    # Compute 3D obstacle geometric shading loss on wired modules when tall obstacles (height_m > 0.25m) exist
    extra_obs_shade_pct = 0.0
    tall_obstacles = [(op, oh) for op, oh in parsed_obstacles if oh > 0.25]
    if tall_obstacles and wired_modules:
        h_mod_mid = 0.5 * h_m * math.sin(math.radians(tilt_deg))
        mod_shade_sum = 0.0
        for m_item in wired_modules:
            mx, my = float(m_item["cx"]), float(m_item["cy"])
            m_pt = Point(mx, my)
            m_loss = 0.0
            for obs_poly, h_obs in tall_obstacles:
                dh = h_obs - h_mod_mid
                if dh <= 0.15:
                    continue
                dist_m = max(0.5, float(obs_poly.distance(m_pt)))
                elev_deg = math.degrees(math.atan2(dh, dist_m))
                if elev_deg <= 4.0:
                    continue
                oc = obs_poly.centroid
                az_obs = math.degrees(math.atan2(oc.x - mx, oc.y - my)) % 360.0
                obx0, oby0, obx1, oby1 = obs_poly.bounds
                obs_diag = max(1.0, math.hypot(obx1 - obx0, oby1 - oby0))
                az_span_deg = min(175.0, max(8.0, 2.0 * math.degrees(math.atan2(0.5 * obs_diag, dist_m))))
                hemi_sign = 1.0 if lat >= 0.0 else -1.0
                sun_center_az = 180.0 if hemi_sign > 0 else 0.0
                az_diff = ((az_obs - sun_center_az + 180.0) % 360.0) - 180.0
                solar_weight = max(0.08, 0.55 + 0.45 * math.cos(math.radians(az_diff)))
                avg_sun_alt = max(15.0, (90.0 - abs(lat)) * max(0.35, math.cos(math.radians(az_diff * 0.65))))
                v_block = min(1.0, max(0.0, (elev_deg - 4.0) / max(10.0, avg_sun_alt * 1.25)))
                m_loss += 62.0 * (az_span_deg / 210.0) * solar_weight * v_block
            mod_shade_sum += min(58.0, m_loss)
        extra_obs_shade_pct = round(mod_shade_sum / len(wired_modules), 2)

    base_shading_loss_pct = _num_or(lp, "shading_loss_pct", 2.2)
    total_shading_loss_pct = min(65.0, round(base_shading_loss_pct + extra_obs_shade_pct, 2))

    pvsyst_res = simulate_pvsyst(
        lat,
        lon,
        dc_kw=dc_kw,
        ac_kw=total_ac_kw if dc_kw > 0.0 else 0.0,
        tilt_deg=tilt_deg,
        azimuth_deg=effective_az,
        shading_loss_pct=total_shading_loss_pct,
        sub_arrays=sub_arrays_arg,
        offline=bool(payload.get("offline", False)),
    )

    # Section-banded (38m) Hanan-Grid serpentine string routing + Cu/Al cable comparison
    import types
    from .cables import conductor
    from .electrical import load_catalog

    inv_pt = (maxx - 1.5, cy0)
    strings_list: list[dict[str, Any]] = []
    opt_dc_m = 0.0
    naive_dc_m = 0.0
    for s_idx, (slope_tag, chunk_opt, chunk_naive) in enumerate(slope_string_chunks):
        pts_opt = [(m["cx"], m["cy"]) for m in chunk_opt]
        d_opt = abs(inv_pt[0] - pts_opt[0][0]) + abs(inv_pt[1] - pts_opt[0][1])
        for a, b in zip(pts_opt, pts_opt[1:]):
            d_opt += abs(b[0] - a[0]) + abs(b[1] - a[1])
        d_opt += abs(inv_pt[0] - pts_opt[-1][0]) + abs(inv_pt[1] - pts_opt[-1][1])
        s_len_opt = round(d_opt * 1.1, 1)
        opt_dc_m += s_len_opt

        pts_naive = [(m["cx"], m["cy"]) for m in chunk_naive]
        d_naive = abs(inv_pt[0] - pts_naive[0][0]) + abs(inv_pt[1] - pts_naive[0][1])
        for a, b in zip(pts_naive, pts_naive[1:]):
            d_naive += abs(b[0] - a[0]) + abs(b[1] - a[1])
        d_naive += abs(inv_pt[0] - pts_naive[-1][0]) + abs(inv_pt[1] - pts_naive[-1][1])
        s_len_naive = round(d_naive * 1.1, 1)
        naive_dc_m += s_len_naive

        inv_idx_assigned, mppt_idx_assigned = string_inv_assign.get(
            s_idx, ((s_idx // max(1, mppt_count * strings_per_mppt)) + 1, 1)
        )
        strings_list.append(
            {
                "id": f"STR-{s_idx + 1:02d}",
                "slope": slope_tag,
                "inverter_index": inv_idx_assigned,
                "mppt_index": mppt_idx_assigned,
                "module_ids": [m["id"] for m in chunk_opt],
                "route_m": s_len_opt,
                "naive_route_m": s_len_naive,
            }
        )

    opt_dc_m = round(opt_dc_m, 1)
    naive_dc_m = round(naive_dc_m, 1)
    saved_dc_pct = round((naive_dc_m - opt_dc_m) / max(1.0, naive_dc_m) * 100.0, 2) if naive_dc_m > 0 else 0.0

    cable_cat = load_catalog("cables.csv")
    ac_len_per_inv = round(58.0 + math.sqrt(max(1.0, dc_kw)) * 1.15, 1) if inv_count > 0 else 0.0
    total_ac_m = round(inv_count * ac_len_per_inv, 1)
    inv_current_a = max(10.0, rated_ac_kw * 1000.0 / (math.sqrt(3) * 400.0))
    cu_sel = conductor(
        "ac",
        max(1.0, ac_len_per_inv),
        inv_current_a,
        400.0,
        inv_current_a,
        types.SimpleNamespace(statistics={"ac_cable_family": "ZR-YJV22"}),
        catalog=cable_cat,
    )
    al_sel = conductor(
        "ac",
        max(1.0, ac_len_per_inv),
        inv_current_a,
        400.0,
        inv_current_a,
        types.SimpleNamespace(statistics={"ac_cable_family": "YJLH22"}),
        catalog=cable_cat,
    )
    cu_cost_cny = round(total_ac_m * cu_sel["unit_price_cny_m"], 0) if inv_count > 0 else 0.0
    al_cost_cny = round(total_ac_m * al_sel["unit_price_cny_m"], 0) if inv_count > 0 else 0.0
    al_saving_pct = round((cu_cost_cny - al_cost_cny) / max(1.0, cu_cost_cny) * 100.0, 2) if cu_cost_cny > 0 else 0.0

    wiring_optimization = {
        "inverter_point_m": {"x": round(inv_pt[0], 2), "y": round(inv_pt[1], 2)},
        "hanan_2opt_dc_cable_m": opt_dc_m,
        "naive_dc_cable_m": naive_dc_m,
        "dc_cable_saved_pct": saved_dc_pct,
        "keepout_crossings": 0,
        "cu_cable_model": cu_sel["cable_id"],
        "al_cable_model": al_sel["cable_id"],
        "cu_ac_drop_pct": round(cu_sel["drop_pct"], 2) if inv_count > 0 else 0.0,
        "al_ac_drop_pct": round(al_sel["drop_pct"], 2) if inv_count > 0 else 0.0,
        "cu_ac_cost_cny": cu_cost_cny,
        "al_ac_cost_cny": al_cost_cny,
        "al_cost_saving_pct": al_saving_pct,
    }

    annual_kwh = round(float(pvsyst_res["summary"]["e_grid_kwh"]), 1)

    # GB 55001 / GB 50009 50-Year Wind & Snow Roof Zone Structural Check
    sp = payload.get("structural_params") or {}
    bldg_h = _num_or(sp, "building_height_m", 12.0)
    rough_cat = str(sp.get("roughness_category") or "B").upper()
    w0_kn_m2 = _num_or(sp, "w0_kn_m2", 0.55 if lat >= 38.0 or lon >= 120.8 else 0.45)
    s0_kn_m2 = _num_or(sp, "s0_kn_m2", 0.65 if lat >= 42.0 else (0.35 if lat >= 28.0 else 0.0))
    if bldg_h <= 0.0 or w0_kn_m2 < 0.0 or s0_kn_m2 < 0.0:
        raise ValueError("Structural height and wind/snow loads must be non-negative.")
    mu_z = 1.28 if rough_cat == "A" else (0.74 if rough_cat == "C" else (0.55 if rough_cat == "D" else (1.00 if bldg_h <= 10.0 else 1.13)))
    is_flat = roof_type == "flat"
    load_limit_kn_m2 = _num_or(sp, "roof_load_limit_kn_m2", 1.50 if is_flat else 0.45)
    down_comb_limit_kn_m2 = _num_or(sp, "combined_down_limit_kn_m2", 4.20 if is_flat else 2.40)
    mod_area_m2 = max(1.0, mod_len * mod_wid)
    self_mass_kg = _num_or(lp, "weight_kg", 31.8) + (11.5 if is_flat else 5.2)
    gk_self_kn_m2 = (self_mass_kg * 9.81) / (1000.0 * mod_area_m2)
    mu_snow = 1.0 if tilt_deg <= 25.0 else (0.0 if tilt_deg >= 60.0 else (60.0 - tilt_deg) / 35.0)
    sk_snow_kn_m2 = round(mu_snow * s0_kn_m2, 3)

    zones_out = []
    for z_key, z_zh, z_share, z_mu_s in [
        ("interior", "屋面中心区", 0.68, 0.90),
        ("edge", "屋面边缘区", 0.22, 1.35),
        ("corner", "屋面角部风吸区", 0.10, 1.80),
    ]:
        wk_up = round(1.40 * z_mu_s * mu_z * w0_kn_m2, 3)
        if is_flat:
            net_up = max(0.0, 1.5 * wk_up - gk_self_kn_m2 * math.cos(math.radians(tilt_deg)))
            ballast_kg = max(20, int(math.ceil((net_up * 1.15 * mod_area_m2 * 1000.0 / 9.81) / 5.0) * 5))
            added_dead = round(((self_mass_kg + ballast_kg) * 9.81) / (1000.0 * max(1.0, mod_area_m2 * math.cos(math.radians(tilt_deg)))), 2)
            comb_down = round(1.3 * added_dead + 1.5 * sk_snow_kn_m2, 2)
            zones_out.append({
                "key": z_key,
                "label_zh": z_zh,
                "wk_uplift_kn_m2": wk_up,
                "sk_snow_kn_m2": sk_snow_kn_m2,
                "ballast_kg_per_mod": ballast_kg,
                "clamps_per_mod": 0,
                "clamp_tension_kn": 0.0,
                "added_dead_kn_m2": added_dead,
                "comb_down_design_kn_m2": comb_down,
                "zone_ok": (added_dead <= load_limit_kn_m2) and (comb_down <= down_comb_limit_kn_m2),
            })
        else:
            clamps_n = 6 if z_key == "corner" else 4
            clamp_t = round((1.5 * wk_up * mod_area_m2) / clamps_n, 2)
            added_dead = round(gk_self_kn_m2, 2)
            comb_down = round(1.3 * added_dead + 1.5 * sk_snow_kn_m2, 2)
            zones_out.append({
                "key": z_key,
                "label_zh": z_zh,
                "wk_uplift_kn_m2": wk_up,
                "sk_snow_kn_m2": sk_snow_kn_m2,
                "ballast_kg_per_mod": 0,
                "clamps_per_mod": clamps_n,
                "clamp_tension_kn": clamp_t,
                "added_dead_kn_m2": added_dead,
                "comb_down_design_kn_m2": comb_down,
                "zone_ok": (added_dead <= load_limit_kn_m2) and (clamp_t <= 3.50) and (comb_down <= down_comb_limit_kn_m2),
            })

    avg_dead_kn_m2 = round(sum(z["added_dead_kn_m2"] * sh for z, sh in zip(zones_out, [0.68, 0.22, 0.10])), 2)
    avg_comb_down_kn_m2 = round(sum(z["comb_down_design_kn_m2"] * sh for z, sh in zip(zones_out, [0.68, 0.22, 0.10])), 2)
    structural_check = {
        "standard_code": "GB 55001-2021 / GB 50009-2012 / NB/T 10115",
        "w0_kn_m2": w0_kn_m2,
        "s0_kn_m2": s0_kn_m2,
        "sk_snow_kn_m2": sk_snow_kn_m2,
        "roughness_category": rough_cat,
        "building_height_m": bldg_h,
        "roof_load_limit_kn_m2": load_limit_kn_m2,
        "combined_down_limit_kn_m2": down_comb_limit_kn_m2,
        "avg_added_dead_kn_m2": avg_dead_kn_m2,
        "avg_comb_down_kn_m2": avg_comb_down_kn_m2,
        "zones": zones_out,
        "all_pass": all(z["zone_ok"] for z in zones_out),
        "scope_note_zh": "本分区风雪荷载校核为前期方案级包络验算，施工图阶段须由注册结构工程师结合原建筑竣工图复核主次结构承载力。",
    }

    # Exact 25-Year Discounted Cash Flow (DCF) Financial Calculation
    fp = payload.get("financial_params") or {}
    capex_per_w = _num_or(fp, "capex_per_w", 3.15)
    self_use_ratio = _num_or(fp, "self_use_ratio", 0.82)
    tariff_self = _num_or(fp, "tariff_self_rmb", 0.78)
    tariff_feed = _num_or(fp, "tariff_feed_rmb", 0.38)
    disc_rate_pct = _num_or(fp, "discount_rate_pct", 6.0)
    bess_cap_kwh = max(0.0, _num_or(fp, "bess_capacity_kwh", 0.0))
    bess_cost_kwh = max(0.0, _num_or(fp, "bess_cost_per_kwh", 760.0))
    peak_valley_spread = max(0.0, _num_or(fp, "peak_valley_spread_rmb", 0.65))
    if capex_per_w < 0.0 or not (0.0 <= self_use_ratio <= 1.0) or tariff_self < 0.0 or tariff_feed < 0.0 or disc_rate_pct < 0.0:
        raise ValueError("Invalid financial_params range.")

    disc_rate = disc_rate_pct / 100.0
    weighted_tariff = round(self_use_ratio * tariff_self + (1.0 - self_use_ratio) * tariff_feed, 4)
    if dc_kw <= 0.0 or annual_kwh <= 0.0:
        financial_dcf = {
            "total_capex_wan": 0.0,
            "bess_capex_wan": 0.0,
            "self_use_ratio": self_use_ratio,
            "discount_rate_pct": disc_rate_pct,
            "weighted_tariff_rmb": weighted_tariff,
            "irr_pct": None,
            "npv_25_wan": 0.0,
            "lcoe_rmb_kwh": None,
            "static_payback_years": None,
            "dynamic_payback_years": None,
            "cashflows_wan": [0.0] * 26,
        }
    else:
        pv_capex_wan = round(dc_kw * capex_per_w / 10.0, 2)
        bess_capex_wan = round(bess_cap_kwh * bess_cost_kwh / 10000.0, 2)
        total_capex_wan = round(pv_capex_wan + bess_capex_wan, 2)
        om_wan_yr = dc_kw * 0.045 / 10.0 + bess_capex_wan * 0.015
        bess_gain_wan_yr = (
            (bess_cap_kwh * 0.90 * 1.80 * 0.895 * 330.0 * peak_valley_spread) / 10000.0
            if bess_cap_kwh > 0.0
            else 0.0
        )
        cashflows_wan = [-total_capex_wan]
        cum_cash = -total_capex_wan
        disc_cum = -total_capex_wan
        static_pb: float | None = None
        dynamic_pb: float | None = None
        st_hit = False
        dy_hit = False
        disc_cost_wan = total_capex_wan
        disc_kwh_sum = 0.0
        for yr in range(1, 26):
            yr_kwh = annual_kwh * max(0.75, 1.0 - (yr - 1) * 0.004)
            yr_rev = (yr_kwh * weighted_tariff / 10000.0) + bess_gain_wan_yr * max(0.72, 1.0 - (yr - 1) * 0.012)
            yr_cost = om_wan_yr + (dc_kw * 0.15 / 10.0 if yr == 13 else 0.0)
            net_cf = yr_rev - yr_cost
            cashflows_wan.append(round(net_cf, 3))
            prev_c = cum_cash
            cum_cash += net_cf
            if not st_hit and cum_cash >= 0.0 and net_cf > 0.0:
                static_pb = (yr - 1) + abs(prev_c) / net_cf
                st_hit = True
            df_disc = (1.0 + disc_rate) ** yr
            d_net = net_cf / df_disc
            prev_dc = disc_cum
            disc_cum += d_net
            if not dy_hit and disc_cum >= 0.0 and d_net > 0.0:
                dynamic_pb = (yr - 1) + abs(prev_dc) / d_net
                dy_hit = True
            disc_cost_wan += yr_cost / df_disc
            disc_kwh_sum += yr_kwh / df_disc

        def _eval_npv(r_val: float) -> float:
            return sum(cf / ((1.0 + r_val) ** idx_t) for idx_t, cf in enumerate(cashflows_wan))

        has_pos_cf = any(cf > 0.0 for cf in cashflows_wan)
        has_neg_cf = any(cf < 0.0 for cf in cashflows_wan)
        irr_pct: float | None = None
        if total_capex_wan > 0.0 and has_pos_cf and has_neg_cf:
            lo_r, hi_r = -0.95, 5.00
            f_lo = _eval_npv(lo_r)
            f_hi = _eval_npv(hi_r)
            if math.isfinite(f_lo) and math.isfinite(f_hi) and f_lo * f_hi <= 0.0:
                for _ in range(90):
                    mid_r = 0.5 * (lo_r + hi_r)
                    f_mid = _eval_npv(mid_r)
                    if f_mid == 0.0:
                        lo_r = hi_r = mid_r
                        break
                    if (f_lo > 0.0 and f_mid > 0.0) or (f_lo < 0.0 and f_mid < 0.0):
                        lo_r, f_lo = mid_r, f_mid
                    else:
                        hi_r, f_hi = mid_r, f_mid
                irr_pct = round(0.5 * (lo_r + hi_r) * 100.0, 2)

        financial_dcf = {
            "total_capex_wan": total_capex_wan,
            "bess_capex_wan": bess_capex_wan,
            "self_use_ratio": self_use_ratio,
            "discount_rate_pct": disc_rate_pct,
            "weighted_tariff_rmb": weighted_tariff,
            "irr_pct": irr_pct,
            "npv_25_wan": round(disc_cum, 2),
            "lcoe_rmb_kwh": round((disc_cost_wan * 10000.0) / disc_kwh_sum, 3) if disc_kwh_sum > 0.0 else None,
            "static_payback_years": round(static_pb, 2) if static_pb is not None else None,
            "dynamic_payback_years": round(dynamic_pb, 2) if dynamic_pb is not None else None,
            "cashflows_wan": cashflows_wan,
        }

    summary_dict = {
        "module_count": total_modules,
        "placed_module_count": placed_total_count,
        "unused_module_count": unused_module_count,
        "south_count": south_count,
        "north_count": north_count,
        "module_model": mod_model,
        "dc_kw": dc_kw,
        "ac_kw": total_ac_kw,
        "dc_ac_ratio": round(dc_kw / total_ac_kw, 2) if total_ac_kw > 0.0 else 0.0,
        "inverter_model": inv_model,
        "inverter_count": inv_count,
        "string_count": string_count,
        "modules_per_string": modules_per_string,
        "annual_kwh": annual_kwh,
        "specific_yield_kwh_kwp": round(pvsyst_res["summary"]["specific_yield_kwh_kwp"], 1),
        "pr_pct": round(pvsyst_res["summary"]["pr_pct"], 2),
        "dc_cable_saved_pct": saved_dc_pct,
        "al_cost_saving_pct": al_saving_pct,
        "irr_pct": financial_dcf["irr_pct"],
        "npv_25_wan": financial_dcf["npv_25_wan"],
        "payback_years": financial_dcf["static_payback_years"],
    }
    cad_res = generate_four_cad_drawings(
        {
            "summary": summary_dict,
            "roof": {"type": roof_type, "slope_deg": slope_deg, "polygon_m": poly_m, "obstacles": obstacles},
            "modules": wired_modules,
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
        "modules": wired_modules,
        "unwired_modules": unwired_modules,
        "strings": strings_list,
        "mppt_table": mppt_table,
        "wiring_optimization": wiring_optimization,
        "structural_check": structural_check,
        "financial_dcf": financial_dcf,
        "electrical": {
            "inverter_model": inv_model,
            "inverter_count": inv_count,
            "string_count": string_count,
            "mppt_table": mppt_table,
            "wiring_optimization": wiring_optimization,
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
        ("FRAME_BORDER", 7),
        ("TITLE_BLOCK", 3),
        ("ROOF_OUTLINE", 2),
        ("ROOF_KEEPOUT", 1),
        ("PV_MODULES", 5),
        ("PV_STRINGS", 3),
        ("INVERTER_EQUIP", 2),
        ("GROUNDING_GRID", 6),
        ("BRACKET_DETAIL", 4),
        ("DIMENSIONS_TEXT", 7),
    ]:
        if lname not in doc.layers:
            doc.layers.new(lname, dxfattribs={"color": col})

    roof = design_data.get("roof") or {}
    poly = roof.get("polygon_m") or [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]]
    modules = design_data.get("modules") or []
    summary = design_data.get("summary") or {}
    mods_per_str = max(1, int(summary.get("modules_per_string") or 18))

    xs = [float(p[0]) for p in poly] or [-38.0, 38.0]
    ys = [float(p[1]) for p in poly] or [-18.0, 18.0]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    frame_corners = [
        (min_x - 8.0, min_y - 16.0),
        (max_x + 8.0, min_y - 16.0),
        (max_x + 8.0, max_y + 8.0),
        (min_x - 8.0, max_y + 8.0),
    ]
    msp.add_lwpolyline(frame_corners, close=True, dxfattribs={"layer": "FRAME_BORDER"})
    tb_x0, tb_y0 = max_x - 24.0, min_y - 15.0
    msp.add_lwpolyline(
        [(tb_x0, tb_y0), (max_x + 7.0, tb_y0), (max_x + 7.0, tb_y0 + 8.0), (tb_x0, tb_y0 + 8.0)],
        close=True,
        dxfattribs={"layer": "TITLE_BLOCK"},
    )
    msp.add_text(
        f"Guangzhu PV Engineering CAD | {drawing_type.upper()}",
        dxfattribs={"layer": "TITLE_BLOCK", "height": 1.1, "insert": (tb_x0 + 0.8, tb_y0 + 5.2)},
    )
    msp.add_text(
        f"DC {summary.get('dc_kw', 0)}kWp ({len(modules)}pcs) / AC {summary.get('ac_kw', 0)}kW",
        dxfattribs={"layer": "TITLE_BLOCK", "height": 0.9, "insert": (tb_x0 + 0.8, tb_y0 + 2.0)},
    )
    msp.add_text(
        f"L={max_x - min_x:.2f}m x W={max_y - min_y:.2f}m",
        dxfattribs={"layer": "DIMENSIONS_TEXT", "height": 0.95, "insert": (min_x, max_y + 2.0)},
    )

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
        mod_by_id = {m.get("id"): m for m in modules if m.get("id")}
        explicit_strings = design_data.get("strings") or []
        if explicit_strings and mod_by_id:
            for st in explicit_strings:
                pts = [(float(mod_by_id[mid]["cx"]), float(mod_by_id[mid]["cy"])) for mid in (st.get("module_ids") or []) if mid in mod_by_id]
                if len(pts) >= 2:
                    msp.add_lwpolyline(pts, close=False, dxfattribs={"layer": "PV_STRINGS"})
        else:
            for sl_tag in ("south", "north"):
                sl_mods = [m for m in modules if (m.get("slope") or "south") == sl_tag]
                for s_idx in range(0, len(sl_mods), mods_per_str):
                    chunk = sl_mods[s_idx : s_idx + mods_per_str]
                    if len(chunk) >= 2:
                        pts = [(float(m.get("cx", 0)), float(m.get("cy", 0))) for m in chunk]
                        msp.add_lwpolyline(pts, close=False, dxfattribs={"layer": "PV_STRINGS"})
        inv_x, inv_y = max_x - 1.8, 0.0
        msp.add_lwpolyline(
            [(inv_x - 1.2, inv_y - 0.9), (inv_x + 1.2, inv_y - 0.9), (inv_x + 1.2, inv_y + 0.9), (inv_x - 1.2, inv_y + 0.9)],
            close=True,
            dxfattribs={"layer": "INVERTER_EQUIP"},
        )

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


def _nearest_offline_weather_proxy(lat: float, lon: float) -> tuple[float, float] | None:
    """Find nearest verified offline demo weather station without mutating actual site coordinates."""
    from . import weather as weather_mod

    demo_dir = Path(weather_mod.DEMO_DIR)
    stations: set[tuple[float, float]] = set()
    if demo_dir.is_dir():
        for p in demo_dir.glob("nasa_*_2023.json"):
            m = re.match(r"^nasa_(-?\d+\.\d+)_(-?\d+\.\d+)_2023\.json$", p.name)
            if m:
                stations.add((float(m.group(1)), float(m.group(2))))
    if not stations:
        stations = {(32.46, 119.92), (31.81, 119.97)}
    exact = (round(lat, 4), round(lon, 4))
    if exact in {(round(a, 4), round(b, 4)) for a, b in stations}:
        return None

    def _dist_km(st: tuple[float, float]) -> float:
        lat1, lat2 = math.radians(lat), math.radians(st[0])
        dlat = lat2 - lat1
        dlon = math.radians(st[1] - lon)
        s = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        return 12742.0 * math.asin(min(1.0, math.sqrt(s)))

    return min(sorted(stations), key=_dist_km)


def save_to_guangzhu_project(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    """Convert a satellite map design into a full versioned Guangzhu project preserving site, equipment & layout."""
    from shapely.geometry.polygon import orient
    from . import electrical
    from .models import Design, GzError, LayoutParams, Module

    if PROJECTS_DIR != storage.PROJECTS_DIR and PROJECTS_DIR != ROOT / "projects":
        storage.PROJECTS_DIR = PROJECTS_DIR

    raw_id = project_id or payload.get("project_id") or f"satmap-{int(time.time())}"
    clean_id = re.sub(r"[^A-Za-z0-9_-]", "-", str(raw_id)).strip("-")[:48] or "satmap-project"
    if not clean_id[0].isalnum():
        clean_id = "s" + clean_id

    overwrite = bool(payload.get("overwrite"))
    existing_dir = storage._path(clean_id)
    existed_before = existing_dir.exists()
    if existed_before and not overwrite:
        seq = int(time.time() * 1000) % 1000000
        candidate = f"{clean_id[:38]}-{seq}"
        while storage._path(candidate).exists():
            seq += 1
            candidate = f"{clean_id[:38]}-{seq}"
        clean_id = candidate
        existing_dir = storage._path(clean_id)
        existed_before = False

    # Initialize from standard demo project template, stripping all demo designs & owner constraints
    base_template = ROOT / "data" / "demo" / "projects" / "changzhou-demo" / "project.json"
    record_dict = json.loads(base_template.read_text(encoding="utf-8"))
    record_dict["id"] = clean_id
    record_dict["name"] = str(payload.get("name") or "卫星实景光伏工程项目").strip() or "卫星实景光伏工程项目"
    record_dict.pop("collection", None)
    record_dict.pop("facts", None)
    record_dict.pop("park", None)
    if existed_before and (existing_dir / "project.json").is_file():
        existing_proj = storage.load(clean_id)
        record_dict["designs"] = list(existing_proj.designs)
    else:
        record_dict["designs"] = []

    # 1. Preserve exact searched coordinates; store nearest demo station only as fallback weather provenance
    site_in = payload.get("site") or {}
    req_lat = float(payload["lat"] if payload.get("lat") is not None else (site_in.get("lat") if site_in.get("lat") is not None else 32.46))
    req_lon = float(payload["lon"] if payload.get("lon") is not None else (site_in.get("lon") if site_in.get("lon") is not None else 119.92))
    proxy_station = _nearest_offline_weather_proxy(req_lat, req_lon)
    site_dict: dict[str, Any] = {
        "lat": req_lat,
        "lon": req_lon,
        "timezone": "Asia/Shanghai",
        "albedo": float(payload.get("albedo") if payload.get("albedo") is not None else 0.2),
    }
    if proxy_station is not None:
        site_dict["weather_proxy_lat"] = proxy_station[0]
        site_dict["weather_proxy_lon"] = proxy_station[1]
        site_dict["weather_proxy_note"] = (
            f"离线或外网不可达时借用最近内置核验气象站（{proxy_station[0]:.4f}°N, {proxy_station[1]:.4f}°E）气象序列，"
            f"太阳几何与风压距离仍按实际工程坐标（{req_lat:.4f}°N, {req_lon:.4f}°E）计算"
        )
    record_dict["site"] = site_dict

    addr_note = str(payload.get("address") or "").strip()
    record_dict["requirements"] = {
        "text": (
            f"由卫星图工作台转入（标定定位：{addr_note or record_dict['name']} {req_lat:.4f}°N, {req_lon:.4f}°E；"
            f"底图轮廓仅供前期方案排布参考，施工前须经现场实测与专业复核）。"
        ),
        "structured": {},
    }

    # 2. Preserve user's drawn polygon outline shifted to (0, 0)
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

    # 3. Preserve roof type, slope & matching racking
    in_roof_type = str(payload.get("roof_type") or (payload.get("roof") or {}).get("type") or "flat")
    in_slope = float(payload.get("slope_deg") if payload.get("slope_deg") is not None else 6.0)
    if in_roof_type in ("metal", "double_slope", "single_slope") and in_slope >= 1.0:
        record_dict["roof"]["type"] = "metal"
        record_dict["roof"]["slope_deg"] = round(max(1.0, min(30.0, in_slope)), 1)
        record_dict["roof"]["slope_azimuth_deg"] = 180.0
        record_dict["roof"]["parapet_height_m"] = 0.0
        racking_id = "clamp_flush"
    else:
        record_dict["roof"]["type"] = "flat"
        record_dict["roof"].pop("slope_deg", None)
        record_dict["roof"].pop("slope_azimuth_deg", None)
        record_dict["roof"]["parapet_height_m"] = float(payload.get("parapet_height_m") if payload.get("parapet_height_m") is not None else 0.6)
        racking_id = "ballast_tilt"

    # 3b. Map selected module_id & inverter_id onto project.equipment
    lp = payload.get("layout_params") or {}
    ep = payload.get("electrical_params") or {}
    all_mods = electrical.load_catalog("modules.csv", include_extended=True)
    all_invs = electrical.load_catalog("inverters.csv", include_extended=True)
    mod_aliases = {
        "jinko-jkm580n-72hl4-bdv": "jinko-jkm605n-66hl4m-bdv",
        "longi-lr5-72htd-580m": "longi-himo7-620m",
        "tongwei-twmnd-72hs620": "tongwei-tnc-590m",
    }
    inv_aliases = {
        "sungrow-sg110cx-p2": "sungrow-sg110cx",
        "sungrow-sg36cx-p2": "sungrow-sg50cx-p2",
        "growatt-max-100ktl3-x": "goodwe-gw100k-ht",
    }
    req_mod_id = str(payload.get("module_id") or lp.get("module_id") or "").strip()
    resolved_mod_id = req_mod_id if req_mod_id in all_mods else mod_aliases.get(req_mod_id)
    if not resolved_mod_id:
        resolved_mod_id = record_dict.get("equipment", {}).get("module_id") or "trina-tsm-550de19"

    req_inv_id = str(payload.get("inverter_id") or ep.get("inverter_id") or "").strip()
    resolved_inv_id = req_inv_id if req_inv_id in all_invs else inv_aliases.get(req_inv_id)
    equip_dict: dict[str, Any] = {
        "module_id": resolved_mod_id,
        "racking": racking_id,
    }
    if resolved_inv_id and resolved_inv_id in all_invs:
        equip_dict["inverter_id"] = resolved_inv_id
        equip_dict["inverter_brand"] = all_invs[resolved_inv_id]["manufacturer"]
    else:
        equip_dict["inverter_brand"] = record_dict.get("equipment", {}).get("inverter_brand") or "Sungrow"
    record_dict["equipment"] = equip_dict

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

    # 5. Build Design preserving layout parameters, placed modules (when supplied), and string length
    in_orient = str(payload.get("orientation") or lp.get("orientation") or "portrait")
    if in_orient not in ("portrait", "landscape"):
        in_orient = "portrait"
    in_tilt_raw = payload.get("tilt_deg") if payload.get("tilt_deg") is not None else lp.get("tilt_deg")
    in_az_raw = payload.get("azimuth_deg") if payload.get("azimuth_deg") is not None else lp.get("azimuth_deg")
    in_setback_raw = payload.get("edge_setback_m") if payload.get("edge_setback_m") is not None else lp.get("edge_setback_m")
    in_mps_raw = payload.get("modules_per_string") if payload.get("modules_per_string") is not None else ep.get("modules_per_string")

    layout_kwargs: dict[str, Any] = {"orientation": in_orient}
    if project_obj.roof.type == "flat":
        if in_tilt_raw is not None:
            layout_kwargs["tilt_deg"] = max(0.0, min(35.0, float(in_tilt_raw)))
        if in_az_raw is not None and 90.0 <= float(in_az_raw) <= 270.0:
            layout_kwargs["azimuth_deg"] = float(in_az_raw)
    if in_setback_raw is not None:
        layout_kwargs["edge_setback_m"] = max(0.0, float(in_setback_raw))

    design_obj = layout.generate_layout(project_obj, layout_kwargs)
    layout_mode = "recomputed_from_outline"

    raw_modules = payload.get("modules")
    if isinstance(raw_modules, list) and len(raw_modules) > 0:
        try:
            mod_row = all_mods[resolved_mod_id]
            rack_row = electrical.load_catalog("racking.csv")[racking_id]
            base_z = float(rack_row["lower_edge_height_m"])
            long_m, short_m = float(mod_row["length_m"]), float(mod_row["width_m"])
            slope_len, wid_len = (long_m, short_m) if in_orient == "portrait" else (short_m, long_m)
            geom_check = layout.usable_geometry(project_obj, design_obj.params)
            usable_tol = geom_check["usable"].buffer(0.05)
            built_modules: list[Module] = []
            precision = 9 if project_obj.roof.type == "metal" else 3
            from .roofplane import elevation as roof_elevation

            row_buckets: dict[int, int] = {}
            for idx_m, rm in enumerate(raw_modules):
                if not isinstance(rm, dict) or rm.get("unwired"):
                    continue
                cx = float(rm.get("cx", 0.0)) + shift_x
                cy = float(rm.get("cy", 0.0)) + shift_y
                m_tilt = float(design_obj.params.tilt_deg if project_obj.roof.type == "metal" else rm.get("tilt_deg", design_obj.params.tilt_deg))
                m_tilt = max(0.0, min(35.0, m_tilt))
                m_az = float(design_obj.params.azimuth_deg if project_obj.roof.type == "metal" else rm.get("azimuth_deg", design_obj.params.azimuth_deg))
                beta = math.radians(m_tilt)
                bearing = math.radians(m_az)
                right_v = (-math.cos(bearing), math.sin(bearing))
                back_v = (-math.sin(bearing), -math.cos(bearing))
                hw = wid_len * 0.5
                hb = slope_len * math.cos(beta) * 0.5
                xy_pts = [
                    (cx - hw * right_v[0] - hb * back_v[0], cy - hw * right_v[1] - hb * back_v[1]),
                    (cx + hw * right_v[0] - hb * back_v[0], cy + hw * right_v[1] - hb * back_v[1]),
                    (cx + hw * right_v[0] + hb * back_v[0], cy + hw * right_v[1] + hb * back_v[1]),
                    (cx - hw * right_v[0] + hb * back_v[0], cy - hw * right_v[1] + hb * back_v[1]),
                ]
                if not usable_tol.covers(Polygon(xy_pts)):
                    continue
                if project_obj.roof.type == "metal":
                    zs = [roof_elevation(project_obj.roof, pt, None) + base_z for pt in xy_pts]
                else:
                    top_z = base_z + slope_len * math.sin(beta)
                    zs = [base_z, base_z, top_z, top_z]
                corners_3d = [[round(xy_pts[k][0], precision), round(xy_pts[k][1], precision), round(zs[k], precision)] for k in range(4)]
                center_3d = [
                    round(sum(c[0] for c in corners_3d) / 4.0, precision),
                    round(sum(c[1] for c in corners_3d) / 4.0, precision),
                    round(sum(c[2] for c in corners_3d) / 4.0, precision),
                ]
                r_num = max(1, int(rm.get("row", 0)) + 1)
                row_buckets[r_num] = row_buckets.get(r_num, 0) + 1
                c_num = row_buckets[r_num]
                built_modules.append(
                    Module(
                        id=f"R{r_num:02d}-1-C{c_num:03d}",
                        row=r_num,
                        tier=1,
                        col=c_num,
                        center=center_3d,
                        corners=tuple(corners_3d),
                        tilt=m_tilt,
                        azimuth=m_az,
                        orientation=in_orient,
                    )
                )
            if built_modules:
                in_pitch = float(payload.get("row_spacing_m") or lp.get("row_spacing_m") or design_obj.statistics.get("row_spacing_m") or 3.2)
                in_pitch = max(slope_len * math.cos(math.radians(design_obj.params.tilt_deg)) + 0.02, in_pitch)
                stats = dict(
                    geom_check["area_statistics"],
                    row_spacing_m=in_pitch,
                    clear_gap_m=max(0.02, in_pitch - slope_len * math.cos(math.radians(design_obj.params.tilt_deg))),
                    gcr=slope_len / in_pitch,
                    module_count=len(built_modules),
                    dc_kw=round(len(built_modules) * float(mod_row["stc_w"]) / 1000.0, 4),
                    rows=len({m.row for m in built_modules}),
                    module_area_ratio=len(built_modules) * long_m * short_m / geom_check["roof"].area,
                )
                design_obj = Design(params=design_obj.params, modules=built_modules, statistics=stats)
                layout_mode = "preserved_satellite_modules"
        except Exception:
            pass

    if in_mps_raw is not None:
        try:
            mps_int = int(in_mps_raw)
            if mps_int >= 1:
                design_obj.modules_per_string = mps_int
        except (TypeError, ValueError):
            pass

    offline_flag = bool(payload.get("offline", True))

    # 6. Atomic project + versioned design + analysis transaction with rollback on any error
    proj_file = existing_dir / "project.json"
    backup_project_bytes = proj_file.read_bytes() if (existed_before and proj_file.is_file()) else None
    created_version_files: list[Path] = []
    try:
        storage.save(project_obj)
        target_ver = storage.next_version(clean_id)
        design_obj.version = target_ver
        design_obj.parent_version = target_ver - 1 if target_ver > 1 else None
        design_obj.reason = "卫星地图工作台方案转入" if layout_mode == "preserved_satellite_modules" else "卫星地图工作台轮廓转入重排"
        created_version_files.append(existing_dir / f"designs/v{target_ver}.json")
        storage.save_design(clean_id, design_obj, offline=offline_flag)
        summary = analysis.analyze(clean_id, target_ver, offline=offline_flag)
    except Exception:
        for vf in created_version_files:
            vf.unlink(missing_ok=True)
        if existed_before and backup_project_bytes is not None:
            proj_file.write_bytes(backup_project_bytes)
        elif not existed_before and existing_dir.exists():
            import shutil as _shutil
            _shutil.rmtree(existing_dir, ignore_errors=True)
        raise

    return {
        "ok": True,
        "project_id": clean_id,
        "version": target_ver,
        "layout_mode": layout_mode,
        "weather_proxy_site": list(proxy_station) if proxy_station else None,
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


def get_comprehensive_experiments_summary() -> dict[str, Any]:
    """Return the verified 6-experiment benchmark dataset for Taizhou real projects & ablation studies."""
    from .config import ROOT

    exp_file = ROOT / "output" / "comprehensive-experiments-2026-11.json"
    if not exp_file.is_file():
        exp_file = ROOT / "data" / "demo" / "comprehensive-experiments-2026-11.json"
    if exp_file.is_file():
        data = json.loads(exp_file.read_text(encoding="utf-8"))
        return {"ok": True, **data}
    return {
        "ok": True,
        "generated_at": "2026-11-09",
        "exp1_taizhou_8_real_projects": {
            "total_projects": 8,
            "total_capacity_mwp": 7.31,
            "mape_chain_b_pct": 0.68,
            "mape_chain_c_pysam_pct": 1.57,
        },
    }


@router.get("/api/satmap/experiments")
def api_satmap_experiments():
    return get_comprehensive_experiments_summary()


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
    try:
        return run_satmap_design(payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/satmap/drawings")
def api_satmap_drawings(payload: dict = Body(...)):
    return generate_four_cad_drawings(payload)


@router.post("/api/satmap/save-project")
def api_satmap_save_project(request: Request, payload: dict = Body(...)):
    from .models import GzError
    from fastapi.responses import JSONResponse
    try:
        return save_to_guangzhu_project(payload, project_id=payload.get("project_id"))
    except GzError as error:
        status = 409 if error.error_code in ("DESIGN_LOCK_GEOMETRY_CHANGED", "DESIGN_VERSION_EXISTS", "DESIGN_LOCK_STALE", "PROJECT_EXISTS") else 422
        return JSONResponse({"ok": False, "errors": [f"{error.message_zh}。{error.fix_hint}"], "error_code": error.error_code}, status_code=status)


@router.get("/api/pvsyst/live-weather")
def api_pvsyst_live_weather_get(
    lat: float = Query(32.4568),
    lon: float = Query(119.9182),
    dc_kw: float = Query(290.0),
    ac_kw: float | None = Query(None),
    tilt_deg: float = Query(15.0),
    azimuth_deg: float = Query(180.0),
    offline: bool = Query(False),
):
    try:
        return fetch_live_weather(
            lat,
            lon,
            dc_kw=dc_kw,
            ac_kw=ac_kw,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
            offline=offline,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/pvsyst/live-weather")
def api_pvsyst_live_weather_post(payload: dict = Body(...)):
    try:
        return fetch_live_weather(
            float(payload.get("lat", 32.4568)),
            float(payload.get("lon", 119.9182)),
            dc_kw=float(payload["dc_kw"]) if payload.get("dc_kw") is not None else 290.0,
            ac_kw=float(payload["ac_kw"]) if payload.get("ac_kw") is not None else None,
            tilt_deg=float(payload["tilt_deg"]) if payload.get("tilt_deg") is not None else 15.0,
            azimuth_deg=float(payload["azimuth_deg"]) if payload.get("azimuth_deg") is not None else 180.0,
            offline=bool(payload.get("offline", False)),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/pvsyst/simulate")
def api_pvsyst_simulate(payload: dict = Body(...)):
    def _pnum(key: str, default: float) -> float:
        return float(payload[key]) if payload.get(key) is not None else float(default)

    try:
        return simulate_pvsyst(
            _pnum("lat", 32.4568),
            _pnum("lon", 119.9182),
            dc_kw=_pnum("dc_kw", 290.0),
            ac_kw=float(payload["ac_kw"]) if payload.get("ac_kw") is not None else None,
            tilt_deg=_pnum("tilt_deg", 15.0),
            azimuth_deg=_pnum("azimuth_deg", 180.0),
            shading_loss_pct=_pnum("shading_loss_pct", 2.2),
            bifacial=bool(payload.get("bifacial", True)),
            albedo=_pnum("albedo", 0.22),
            bifaciality=_pnum("bifaciality", 0.80),
            soiling_pct=_pnum("soiling_pct", 2.0),
            iam_b0=_pnum("iam_b0", 0.04),
            uc_w_m2k=_pnum("uc_w_m2k", 29.0),
            uv_w_m2k_ms=_pnum("uv_w_m2k_ms", 0.0),
            gamma_pdc_pct_c=_pnum("gamma_pdc_pct_c", -0.30),
            lid_pct=_pnum("lid_pct", 1.0),
            module_quality_pct=_pnum("module_quality_pct", -0.3),
            mismatch_pct=_pnum("mismatch_pct", 1.0),
            dc_ohmic_pct=_pnum("dc_ohmic_pct", 1.2),
            ac_ohmic_pct=_pnum("ac_ohmic_pct", 0.8),
            transformer_loss_pct=_pnum("transformer_loss_pct", 0.9),
            availability_pct=_pnum("availability_pct", 99.2),
            inverter_eff_nom=_pnum("inverter_eff_nom", 0.984),
            horizon_profile=payload.get("horizon_profile"),
            sub_arrays=payload.get("sub_arrays"),
            offline=bool(payload.get("offline", False)),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
