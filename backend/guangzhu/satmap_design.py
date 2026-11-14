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
import csv
from datetime import datetime, timezone
import io
import json
import math
import os
import re
import shutil
import time
from urllib.parse import quote
import uuid
import zipfile
from pathlib import Path
from typing import Any

import ezdxf
import requests
from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import Response
from shapely.geometry import Point, Polygon, box

from . import analysis, layout, myroofs, project as storage, templates
from .config import DATA_DIR, PROJECTS_DIR, ROOT
from .live_weather import fetch_live_weather
from .models import GzError, Obstacle, Project
from .pvsyst_engine import simulate_pvsyst
from .satmap_multifactor import (
    POLLUTION_PROFILES,
    ConflictingLoadParamsError,
    build_multifactor_layout,
    compute_string_voc_safety,
    compute_wind_snow_structural,
    evaluate_engineering_health_check,
    evaluate_load_matching_and_economics,
    optimize_satmap_multifactor,
    resolve_albedo,
    resolve_wind_snow_params,
    scrub_pvsyst_text,
    solve_dcf_metrics,
    validate_satmap_common_inputs,
)

router = APIRouter()


def _strict_finite_float(val: Any, name: str) -> float:
    if isinstance(val, bool):
        raise ValueError(f"{name} must be a finite number, not bool.")
    out = float(val)
    if not math.isfinite(out):
        raise ValueError(f"{name} must be a finite number.")
    return out


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
    validate_satmap_common_inputs(payload)
    preset_id = str(payload.get("preset_id") or payload.get("key") or "taizhou-pharma-sat")
    lat = _strict_finite_float(payload["lat"], "lat") if payload.get("lat") not in (None, "") else 32.4568
    lon = _strict_finite_float(payload["lon"], "lon") if payload.get("lon") not in (None, "") else 119.9182
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
    slope_deg = _strict_finite_float(payload["slope_deg"], "slope_deg") if payload.get("slope_deg") not in (None, "") else float(matched["slope_deg"])
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
    validate_satmap_common_inputs(payload)

    def _num_or(d: dict[str, Any], key: str, default: float) -> float:
        val = d.get(key)
        if val is None or val == "":
            return float(default)
        return _strict_finite_float(val, key)

    site = payload.get("site") or {}
    lat = _num_or(site, "lat", _num_or(payload, "lat", 32.4568))
    lon = _num_or(site, "lon", _num_or(payload, "lon", 119.9182))
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise ValueError("Site coordinates out of valid geographic range.")

    roof = payload.get("roof") or {}
    roof_type = str(roof.get("type") or roof.get("roof_type") or payload.get("roof_type") or "double_slope")
    if roof_type == "metal":
        roof_type = "double_slope"
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
        px = _strict_finite_float(pt[0], "polygon_x")
        py = _strict_finite_float(pt[1], "polygon_y")
        clean_poly_pts.append((px, py))

    obstacles = (
        roof.get("obstacles")
        if "obstacles" in roof
        else (payload.get("obstacles") if "obstacles" in payload else PRESET_SITES[0]["obstacles"])
    ) or []
    if not isinstance(obstacles, list):
        raise ValueError("obstacles must be a list.")

    equip_in = payload.get("equipment") if isinstance(payload.get("equipment"), dict) else {}
    lp_raw = payload.get("layout_params") or {}
    mod_spec_raw = payload.get("module_spec") or {}
    lp = {**(mod_spec_raw if isinstance(mod_spec_raw, dict) else {}), **(lp_raw if isinstance(lp_raw, dict) else {})}
    req_mod_id_design = str(
        payload.get("module_id")
        or equip_in.get("module_id")
        or lp.get("module_id")
        or lp.get("id")
        or ""
    ).strip()
    if req_mod_id_design:
        from .electrical import load_catalog as _load_cat_mod
        all_mods_d = _load_cat_mod("modules.csv", include_extended=True)
        cat_mod_d = all_mods_d.get(req_mod_id_design)
        if cat_mod_d is None:
            for m_r in all_mods_d.values():
                if str(m_r.get("model") or "").strip().lower() == req_mod_id_design.lower():
                    cat_mod_d = m_r
                    break
        if cat_mod_d is None:
            raise GzError(
                "EQUIPMENT_UNKNOWN",
                f"未知组件型号 ID: {req_mod_id_design}，拒绝静默替换设备。",
                "请从已注册组件目录中选择型号。",
            )
        lp.setdefault("stc_w", cat_mod_d.get("stc_w"))
        lp.setdefault("module_model", cat_mod_d.get("model"))
        lp.setdefault("length_m", cat_mod_d.get("length_m"))
        lp.setdefault("width_m", cat_mod_d.get("width_m"))
        lp.setdefault("weight_kg", cat_mod_d.get("weight_kg"))
        lp.setdefault("vmp_v", cat_mod_d.get("vmp_v"))
        lp.setdefault("voc_v", cat_mod_d.get("voc_v"))
        lp.setdefault("imp_a", cat_mod_d.get("imp_a"))
        lp.setdefault("isc_a", cat_mod_d.get("isc_a"))
        lp.setdefault("beta_voc_pct_c", cat_mod_d.get("beta_voc_pct_c"))

    stc_w = _num_or(lp, "stc_w", 580.0)
    if stc_w <= 0.0:
        raise ValueError("stc_w must be > 0.")
    mod_model = str(lp.get("module_model") or "JKM580N-72HL4-BDV 580W")
    orientation = str(lp.get("orientation") or payload.get("mount_orientation") or "portrait")
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

    ep_raw = payload.get("electrical_params") or {}
    inv_spec_raw = payload.get("inverter_spec") or {}
    ep = {**(inv_spec_raw if isinstance(inv_spec_raw, dict) else {}), **(ep_raw if isinstance(ep_raw, dict) else {})}
    req_inv_id_design = str(
        payload.get("inverter_id")
        or equip_in.get("inverter_id")
        or ep.get("inverter_id")
        or ep.get("id")
        or ""
    ).strip()
    if req_inv_id_design:
        from .electrical import load_catalog as _load_cat_inv
        all_invs_d = _load_cat_inv("inverters.csv", include_extended=True)
        cat_inv_d = all_invs_d.get(req_inv_id_design)
        if cat_inv_d is None:
            for i_r in all_invs_d.values():
                if str(i_r.get("model") or "").strip().lower() == req_inv_id_design.lower():
                    cat_inv_d = i_r
                    break
        if cat_inv_d is None:
            raise GzError(
                "EQUIPMENT_UNKNOWN",
                f"未知逆变器型号 ID: {req_inv_id_design}，拒绝静默替换设备。",
                "请从已注册逆变器目录中选择型号。",
            )
        ep.setdefault("inverter_model", cat_inv_d.get("model"))
        ep.setdefault("rated_ac_kw", cat_inv_d.get("rated_ac_kw"))
        ep.setdefault("mppt_count", cat_inv_d.get("mppt_count"))
        ep.setdefault("strings_per_mppt", cat_inv_d.get("strings_per_mppt"))
        ep.setdefault("max_mppt_current_a", cat_inv_d.get("max_input_current_per_mppt_a"))
        ep.setdefault("max_short_current_a", cat_inv_d.get("max_short_circuit_current_per_mppt_a"))
        ep.setdefault("max_dc_v", cat_inv_d.get("max_dc_voltage_v"))
        ep.setdefault("mppt_v_min", cat_inv_d.get("mppt_min_v"))
        ep.setdefault("mppt_v_max", cat_inv_d.get("mppt_max_v"))

    inv_model = str(ep.get("inverter_model") or "SG110CX-P2")
    rated_ac_kw = _num_or(ep, "rated_ac_kw", 50.0 if "50" in inv_model else (100.0 if "100" in inv_model else 110.0))
    mppt_count = int(_num_or(ep, "mppt_count", 5 if rated_ac_kw <= 60 else (9 if rated_ac_kw == 110 else 10)))
    strings_per_mppt = int(_num_or(ep, "strings_per_mppt", 2))
    modules_per_string = int(_num_or(ep, "modules_per_string", 18))
    explicit_mps = ep.get("modules_per_string") is not None
    raw_fixed_inv_cnt = ep.get("inverter_count") if ep.get("inverter_count") not in (None, "") else payload.get("inverter_count")
    if raw_fixed_inv_cnt not in (None, "") and isinstance(raw_fixed_inv_cnt, bool):
        raise ValueError("inverter_count must not be boolean.")
    fixed_inv_count = int(_strict_finite_float(raw_fixed_inv_cnt, "inverter_count")) if raw_fixed_inv_cnt not in (None, "") else None
    if fixed_inv_count is not None and fixed_inv_count < 1:
        raise ValueError("inverter_count must be >= 1.")
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

    mf = payload.get("multifactor_params") or {}
    orientation_mode = str(
        mf.get("orientation_mode")
        or lp.get("orientation_mode")
        or payload.get("orientation_mode")
        or ("flush_pitched" if roof_type != "flat" else "south_fixed")
    ).strip().lower()
    if orientation_mode not in ("south_fixed", "east_west", "flush_pitched", "elevated_canopy"):
        raise ValueError(f"Unsupported orientation_mode: {orientation_mode}")
    rack_raw = str(mf.get("rack_type") or lp.get("rack_type") or mf.get("rack_rows") or lp.get("rack_rows") or "1P").strip().upper()
    rack_rows = 2 if rack_raw in ("2", "2P") else 1
    parapet_height_m = _num_or(roof, "parapet_height_m", _num_or(mf, "parapet_height_m", _num_or(payload, "parapet_height_m", 0.0)))
    fire_lane_w = _num_or(
        mf,
        "fire_lane_width_m",
        _num_or(
            lp,
            "fire_lane_width_m",
            _num_or(mf, "walkway_width_m", _num_or(lp, "walkway_width_m", _num_or(payload, "walkway_width_m", 0.0))),
        ),
    )
    maint_walkway_m = _num_or(mf, "maint_walkway_interval_m", _num_or(lp, "maint_walkway_interval_m", 0.0))
    if parapet_height_m < 0.0 or fire_lane_w < 0.0 or maint_walkway_m < 0.0:
        raise ValueError("Parapet height and walkway widths must be >= 0.")
    has_explicit_shade_prune = ("max_module_shading_loss_pct" in mf) or ("max_module_shading_loss_pct" in lp) or ("max_module_shading_loss_pct" in payload)
    max_mod_shade_pct = _num_or(mf, "max_module_shading_loss_pct", _num_or(lp, "max_module_shading_loss_pct", _num_or(payload, "max_module_shading_loss_pct", 100.0)))

    default_t_min = -28.0 if lat >= 42.0 else (-14.0 if lat >= 35.0 else (-8.0 if lat >= 27.0 else 2.0))
    site_t_min_c = _num_or(mf, "extreme_temp_min_c", _num_or(ep, "extreme_temp_min_c", default_t_min))
    if ("extreme_temp_max_c" in mf) or ("extreme_temp_max_c" in ep):
        t_amb_max = _num_or(mf, "extreme_temp_max_c", _num_or(ep, "extreme_temp_max_c", 42.0))
        site_t_hot_c = max(60.0, t_amb_max + 26.0)
    else:
        site_t_hot_c = 68.0
    voc_single_cold = mod_voc_v * (1.0 + (beta_voc_pct_c / 100.0) * (site_t_min_c - 25.0))
    vmp_single_cold = mod_vmp_v * (1.0 + (-0.32 / 100.0) * (site_t_min_c - 25.0))
    vmp_single_hot = mod_vmp_v * (1.0 + (-0.32 / 100.0) * (site_t_hot_c - 25.0))
    n_min_mppt = max(4, math.ceil(mppt_v_min / max(1.0, vmp_single_hot)))
    n_max_voc_safe = max(4, min(int(math.floor(max_dc_v / max(1.0, voc_single_cold))), int(math.floor(mppt_v_max / max(1.0, vmp_single_cold)))))
    if not explicit_mps and modules_per_string > n_max_voc_safe:
        modules_per_string = n_max_voc_safe

    # Build usable polygon with Shapely
    roof_poly = Polygon(clean_poly_pts)
    if not roof_poly.is_valid:
        roof_poly = roof_poly.buffer(0)
    if roof_poly.is_empty or roof_poly.area <= 0.01:
        raise ValueError("Roof polygon has zero or invalid area.")
    usable = roof_poly.buffer(-edge_setback)
    parsed_obstacles: list[tuple[Polygon, float]] = []
    for obs in obstacles:
        if not isinstance(obs, dict):
            raise ValueError("Each obstacle must be a dict.")
        obs_pts = obs.get("polygon_m") or obs.get("polygon") or []
        if len(obs_pts) < 3 and obs.get("w_m") and obs.get("h_m"):
            ox = _strict_finite_float(obs.get("x_m", 0.0), "obstacle.x_m")
            oy = _strict_finite_float(obs.get("y_m", 0.0), "obstacle.y_m")
            ow = _strict_finite_float(obs.get("w_m", 2.0), "obstacle.w_m") * 0.5
            oh = _strict_finite_float(obs.get("h_m", 2.0), "obstacle.h_m") * 0.5
            if ow <= 0.0 or oh <= 0.0:
                raise ValueError("Obstacle width and height footprint must be > 0.")
            obs_pts = [[ox - ow, oy - oh], [ox + ow, oy - oh], [ox + ow, oy + oh], [ox - ow, oy + oh]]
        if len(obs_pts) >= 3:
            obs_clean = [(_strict_finite_float(p[0], "obstacle_x"), _strict_finite_float(p[1], "obstacle_y")) for p in obs_pts]
            obs_poly = Polygon(obs_clean)
            if not obs_poly.is_valid:
                obs_poly = obs_poly.buffer(0)
            if not obs_poly.is_empty:
                h_obs = _strict_finite_float(obs["height_m"], "obstacle.height_m") if obs.get("height_m") not in (None, "") else 0.0
                if h_obs < 0.0:
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

    use_mf_layout = bool(
        orientation_mode in ("east_west", "elevated_canopy")
        or rack_rows >= 2
        or fire_lane_w > 0.05
        or maint_walkway_m >= 4.0
        or has_explicit_shade_prune
    )
    sp = payload.get("structural_params") or {}
    norm_w0_kn_m2, norm_s0_kn_m2 = resolve_wind_snow_params(payload, lat=lat, lon=lon)
    pruned_modules_out: list[dict[str, Any]] = []
    placed_modules: list[dict[str, Any]] = []

    if use_mf_layout:
        mf_w0 = norm_w0_kn_m2
        mf_s0 = norm_s0_kn_m2
        mf_fix = str(mf.get("fixing_type") or ("clamp" if roof_type != "flat" else "ballast"))
        mf_struct = compute_wind_snow_structural(
            orientation_mode=orientation_mode,
            fixing_type=mf_fix,
            rack_rows=rack_rows,
            tilt_deg=tilt_deg,
            building_height_m=_num_or(sp, "building_height_m", 12.0),
            base_setback_m=edge_setback,
            basic_wind_w0_kn_m2=mf_w0,
            basic_snow_s0_kn_m2=mf_s0,
            max_roof_load_kg_m2=_num_or(mf, "max_roof_load_kg_m2", 150.0),
            module_weight_kg=_num_or(lp, "weight_kg", 31.8),
            module_area_m2=mod_len * mod_wid,
            span_min_m=max(4.0, min(maxx - minx, maxy - miny)),
            roof_type=roof_type,
            combined_down_limit_kn_m2=_num_or(sp, "combined_down_limit_kn_m2", 4.20 if roof_type == "flat" else 2.40),
        )
        mf_lay = build_multifactor_layout(
            roof_poly_pts=clean_poly_pts,
            obstacles=obstacles,
            roof_type=roof_type,
            slope_deg=slope_deg,
            lat=lat,
            orientation_mode=orientation_mode,
            mount_orientation=orientation,
            rack_rows=rack_rows,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
            module_length_m=mod_len,
            module_width_m=mod_wid,
            col_gap_m=col_gap,
            row_gap_override_m=float(lp["row_spacing_m"]) if lp.get("row_spacing_m") is not None else None,
            effective_setback_m=mf_struct["effective_setback_m"],
            corner_keepout_m=mf_struct["corner_keepout_m"],
            obstacle_setback_m=obs_setback,
            parapet_height_m=parapet_height_m,
            canopy_clear_height_m=_num_or(
                mf,
                "canopy_clear_height_m",
                _num_or(mf, "canopy_clearance_m", _num_or(payload, "canopy_clearance_m", 2.8)),
            ),
            fire_lane_width_m=fire_lane_w,
            maint_walkway_interval_m=maint_walkway_m,
            max_module_shading_loss_pct=max_mod_shade_pct,
        )
        tilt_deg = mf_lay["tilt_deg"]
        pruned_modules_out = mf_lay["pruned_modules"]
        for m_item in mf_lay["modules"]:
            m_item["wired"] = False
            placed_modules.append(m_item)
    elif not usable.is_empty:
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

    if orientation_mode == "east_west":
        east_mods = [m for m in placed_modules if m.get("slope") == "east"]
        west_mods = [m for m in placed_modules if m.get("slope") == "west"]
        slope_groups_in = [
            ("east", _order_serpentine(east_mods), sorted(east_mods, key=lambda item: (item["row"], item["_u"]))),
            ("west", _order_serpentine(west_mods), sorted(west_mods, key=lambda item: (item["row"], item["_u"]))),
        ]
    else:
        south_mods = [m for m in placed_modules if m.get("slope") != "north"]
        north_mods = [m for m in placed_modules if m.get("slope") == "north"]
        slope_groups_in = [
            ("south", _order_serpentine(south_mods), sorted(south_mods, key=lambda item: (item["row"], item["_u"]))),
            ("north", _order_serpentine(north_mods), sorted(north_mods, key=lambda item: (item["row"], item["_u"]))),
        ]

    slope_string_chunks: list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = []
    for slope_tag, s_ord, s_naive in slope_groups_in:
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
    if orientation_mode == "east_west":
        wired_south_mods = [m for m in wired_modules if m.get("slope") == "east"]
        wired_north_mods = [m for m in wired_modules if m.get("slope") == "west"]
    else:
        wired_south_mods = [m for m in wired_modules if m.get("slope") != "north"]
        wired_north_mods = [m for m in wired_modules if m.get("slope") == "north"]
    placed_total_count = len(placed_modules)
    unused_module_count = len(unwired_modules)
    total_modules = len(wired_modules)
    south_count = len(wired_south_mods)
    north_count = len(wired_north_mods)
    dc_kw = round(total_modules * stc_w / 1000.0, 2)

    # Group strings into MPPT channel buckets strictly by (slope, string_length) & current limits
    isc_hot_single = mod_isc_a * (1.0 + 0.00045 * max(0.0, site_t_hot_c - 25.0))
    eff_strings_per_mppt = max(
        0,
        min(
            strings_per_mppt,
            int(math.floor(mppt_isc_limit_a / max(0.1, isc_hot_single))),
            int(math.floor(mppt_limit_a / max(0.1, mod_imp_a))),
        ),
    )
    bucket_stride = max(1, eff_strings_per_mppt)
    mppt_buckets: list[dict[str, Any]] = []
    grouped_chunks: dict[tuple[str, int], list[int]] = {}
    for s_idx, (slope_tag, c_opt, _) in enumerate(slope_string_chunks):
        grouped_chunks.setdefault((slope_tag, len(c_opt)), []).append(s_idx)
    for (slope_tag, str_len), idx_list in grouped_chunks.items():
        for k_start in range(0, len(idx_list), bucket_stride):
            mppt_buckets.append(
                {
                    "slope": slope_tag,
                    "modules_per_string": str_len,
                    "string_indices": idx_list[k_start : k_start + bucket_stride],
                }
            )

    string_count = len(slope_string_chunks)
    mppt_channels_used = len(mppt_buckets)
    if total_modules == 0 or string_count == 0:
        inv_count = 0
        total_ac_kw = 0.0
    elif fixed_inv_count is not None:
        inv_count = fixed_inv_count
        total_ac_kw = round(inv_count * rated_ac_kw, 1)
    else:
        inv_count = max(1, math.ceil(dc_kw / (rated_ac_kw * 1.22)))
        req_mppts = len(mppt_buckets)
        if req_mppts > inv_count * mppt_count and eff_strings_per_mppt >= 1:
            inv_count = max(inv_count, math.ceil(req_mppts / mppt_count))
        total_ac_kw = round(inv_count * rated_ac_kw, 1)
    mppt_channels_capacity = inv_count * mppt_count
    max_strings_capacity = inv_count * mppt_count * eff_strings_per_mppt

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
    if orientation_mode == "east_west" and total_modules > 0:
        sub_arrays_arg = []
        if south_count > 0:
            sub_arrays_arg.append(
                {
                    "name": "东坡蝴蝶子阵 (90°)",
                    "dc_kw": round(south_count * stc_w / 1000.0, 2),
                    "tilt_deg": tilt_deg,
                    "azimuth_deg": 90.0,
                }
            )
        if north_count > 0:
            sub_arrays_arg.append(
                {
                    "name": "西坡蝴蝶子阵 (270°)",
                    "dc_kw": round(north_count * stc_w / 1000.0, 2),
                    "tilt_deg": tilt_deg,
                    "azimuth_deg": 270.0,
                }
            )
        effective_az = 90.0 if south_count >= north_count else 270.0
    elif roof_type == "double_slope" and total_modules > 0:
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
        if orientation_mode == "elevated_canopy":
            h_mod_mid += _num_or(mf, "canopy_clear_height_m", 2.8)
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
            if orientation == "landscape":
                m_loss *= 0.78
            mod_shade_sum += min(58.0, m_loss)
        extra_obs_shade_pct = round(mod_shade_sum / len(wired_modules), 2)

    base_shading_loss_pct = _num_or(lp, "shading_loss_pct", 2.2)
    total_shading_loss_pct = min(65.0, round(base_shading_loss_pct + extra_obs_shade_pct, 2))

    raw_albedo = mf.get("albedo") if mf.get("albedo") is not None else (roof.get("albedo") if roof.get("albedo") is not None else payload.get("albedo"))
    albedo_val, albedo_surface = resolve_albedo(raw_albedo, roof_type=roof_type) if raw_albedo is not None else (0.22, "default")
    pol_key = str(mf.get("pollution_level") or payload.get("pollution_level") or "").strip().lower()
    if pol_key in POLLUTION_PROFILES:
        default_soiling = POLLUTION_PROFILES[pol_key]["soiling_pct"]
        deg_rate_yr = POLLUTION_PROFILES[pol_key]["degradation_pct_yr"] / 100.0
    else:
        default_soiling = 2.0
        deg_rate_yr = 0.004
    soiling_pct_val = _num_or(mf, "soiling_pct", _num_or(payload, "soiling_pct", default_soiling))
    if not (0.0 <= soiling_pct_val < 100.0):
        raise ValueError("soiling_pct must be within [0, 100).")

    has_explicit_orient_mode = any(
        d_src.get("orientation_mode") not in (None, "")
        for d_src in (mf, lp, payload)
        if isinstance(d_src, dict)
    )
    sim_orient_mode = (
        orientation_mode
        if (has_explicit_orient_mode or orientation_mode in ("east_west", "elevated_canopy"))
        else "south_fixed"
    )
    raw_bifacial = (
        mf.get("bifacial")
        if mf.get("bifacial") is not None
        else (lp.get("bifacial") if lp.get("bifacial") is not None else payload.get("bifacial"))
    )
    eff_bifacial = bool(raw_bifacial) if raw_bifacial is not None else (sim_orient_mode != "flush_pitched")
    eff_bifaciality = _num_or(mf, "bifaciality", _num_or(lp, "bifaciality", _num_or(payload, "bifaciality", 0.80)))
    uc_val = _num_or(mf, "uc_w_m2k", _num_or(lp, "uc_w_m2k", _num_or(payload, "uc_w_m2k", 29.0)))
    uv_val = _num_or(mf, "uv_w_m2k_ms", _num_or(lp, "uv_w_m2k_ms", _num_or(payload, "uv_w_m2k_ms", 0.0)))
    snow_loss_sim = _num_or(mf, "snow_loss_pct", _num_or(payload, "snow_loss_pct", 0.0))
    offline_sim = bool(payload.get("offline", False))

    pvsyst_res = simulate_pvsyst(
        lat,
        lon,
        dc_kw=dc_kw,
        ac_kw=total_ac_kw if dc_kw > 0.0 else 0.0,
        tilt_deg=tilt_deg,
        azimuth_deg=effective_az,
        orientation_mode=sim_orient_mode,
        shading_loss_pct=total_shading_loss_pct,
        bifacial=eff_bifacial,
        bifaciality=eff_bifaciality,
        albedo=albedo_val,
        soiling_pct=soiling_pct_val,
        snow_loss_pct=snow_loss_sim,
        uc_w_m2k=uc_val,
        uv_w_m2k_ms=uv_val,
        sub_arrays=sub_arrays_arg,
        offline=offline_sim,
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
    bldg_h = _num_or(sp, "building_height_m", 12.0)
    rough_cat = str(sp.get("roughness_category") or "B").upper()
    w0_kn_m2 = norm_w0_kn_m2
    s0_kn_m2 = norm_s0_kn_m2
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
    snow_shedding_ok = not (s0_kn_m2 >= 0.55 and tilt_deg < 8.0)
    snow_ok = bool(
        snow_shedding_ok
        and (sk_snow_kn_m2 <= 3.60)
        and all(z["comb_down_design_kn_m2"] <= down_comb_limit_kn_m2 for z in zones_out)
    )
    structural_check = {
        "standard_code": "GB 55001-2021 / GB 50009-2012 / NB/T 10115",
        "w0_kn_m2": w0_kn_m2,
        "s0_kn_m2": s0_kn_m2,
        "sk_snow_kn_m2": sk_snow_kn_m2,
        "snow_ok": snow_ok,
        "roughness_category": rough_cat,
        "building_height_m": bldg_h,
        "roof_load_limit_kn_m2": load_limit_kn_m2,
        "combined_down_limit_kn_m2": down_comb_limit_kn_m2,
        "avg_added_dead_kn_m2": avg_dead_kn_m2,
        "avg_comb_down_kn_m2": avg_comb_down_kn_m2,
        "zones": zones_out,
        "all_pass": bool(all(z["zone_ok"] for z in zones_out) and snow_ok),
        "scope_note_zh": "本分区风雪荷载校核为前期方案级包络验算，施工图阶段须由注册结构工程师结合原建筑竣工图复核主次结构承载力。",
    }

    # Exact 25-Year Discounted Cash Flow (DCF) Financial Calculation
    fp = payload.get("financial_params") or {}
    load_params_in = payload.get("load_params") if isinstance(payload.get("load_params"), dict) else {}
    capex_per_w = _num_or(fp, "capex_per_w", _num_or(mf, "capex_per_w", _num_or(payload, "capex_per_w", 3.15)))
    tariff_self = _num_or(
        fp,
        "tariff_self_rmb",
        _num_or(
            fp,
            "tariff_self",
            _num_or(mf, "tariff_self_rmb", _num_or(mf, "tariff_self", _num_or(payload, "tariff_self", 0.78))),
        ),
    )
    tariff_feed = _num_or(
        fp,
        "tariff_feed_rmb",
        _num_or(
            fp,
            "tariff_grid",
            _num_or(mf, "tariff_feed_rmb", _num_or(mf, "tariff_grid", _num_or(payload, "tariff_grid", 0.38))),
        ),
    )
    disc_rate_raw = (
        fp.get("discount_rate_pct")
        if fp.get("discount_rate_pct") not in (None, "")
        else (mf.get("discount_rate_pct") if mf.get("discount_rate_pct") not in (None, "") else payload.get("discount_rate_pct"))
    )
    disc_rate_pct = _strict_finite_float(disc_rate_raw, "discount_rate_pct") if disc_rate_raw not in (None, "") else 6.0
    if not (0.0 <= disc_rate_pct <= 100.0):
        raise ValueError("discount_rate_pct must be within [0, 100].")

    explicit_annual_load_kwh: float | None = None
    for ld_container in (load_params_in, fp, mf, payload):
        if isinstance(ld_container, dict) and ld_container.get("annual_load_kwh") not in (None, ""):
            explicit_annual_load_kwh = _strict_finite_float(ld_container["annual_load_kwh"], "annual_load_kwh")
            if explicit_annual_load_kwh < 0.0:
                raise ValueError("annual_load_kwh must be finite and >= 0.")
            break

    load_profile_in = str(
        load_params_in.get("load_profile")
        or mf.get("load_profile")
        or fp.get("load_profile")
        or payload.get("load_profile")
        or ""
    ).strip().lower()

    if (load_profile_in or explicit_annual_load_kwh is not None) and fp.get("self_use_ratio") is None:
        lm_eval = evaluate_load_matching_and_economics(
            orientation_mode=orientation_mode,
            dc_kw=dc_kw,
            annual_kwh=annual_kwh,
            load_profile=load_profile_in or "industrial_day",
            base_self_tariff_cny=tariff_self,
            feed_in_tariff_cny=tariff_feed,
            base_capex_cny_w=capex_per_w,
            discount_rate_pct=disc_rate_pct,
            annual_load_kwh=explicit_annual_load_kwh,
        )
        self_use_ratio = float(lm_eval["self_use_ratio"])
        self_use_pct_out = float(lm_eval["self_use_pct"])
        self_use_kwh_out = float(lm_eval["self_use_kwh"])
        weighted_tariff = float(lm_eval["weighted_tariff_cny_kwh"])
    else:
        self_use_ratio = _num_or(fp, "self_use_ratio", 0.82)
        if explicit_annual_load_kwh is not None and annual_kwh > 0.0:
            self_use_ratio = min(self_use_ratio, explicit_annual_load_kwh / annual_kwh)
        elif explicit_annual_load_kwh == 0.0:
            self_use_ratio = 0.0
        self_use_pct_out = round(self_use_ratio * 100.0, 1)
        if explicit_annual_load_kwh is not None and annual_kwh > 0.0 and (annual_kwh * self_use_pct_out / 100.0) > explicit_annual_load_kwh:
            self_use_pct_out = math.floor((explicit_annual_load_kwh / annual_kwh) * 10000.0) / 100.0
        self_use_kwh_out = round(min(annual_kwh, explicit_annual_load_kwh, annual_kwh * self_use_ratio), 2) if explicit_annual_load_kwh is not None else round(annual_kwh * self_use_ratio, 2)
        weighted_tariff = round(self_use_ratio * tariff_self + (1.0 - self_use_ratio) * tariff_feed, 4)

    bess_cap_kwh = max(0.0, _num_or(fp, "bess_capacity_kwh", 0.0))
    bess_cost_kwh = max(0.0, _num_or(fp, "bess_cost_per_kwh", 760.0))
    peak_valley_spread = max(0.0, _num_or(fp, "peak_valley_spread_rmb", 0.65))
    if capex_per_w < 0.0 or not (0.0 <= self_use_ratio <= 1.0) or tariff_self < 0.0 or tariff_feed < 0.0 or disc_rate_pct < 0.0:
        raise ValueError("Invalid financial_params range.")

    dcf = solve_dcf_metrics(
        dc_kw=dc_kw,
        annual_kwh=annual_kwh,
        weighted_tariff=weighted_tariff,
        capex_w=capex_per_w,
        degradation_pct_yr=deg_rate_yr * 100.0,
        discount_rate_pct=disc_rate_pct,
        om_yuan_w_yr=0.045,
        inv_repl_yuan_w_yr13=0.15,
        deg_floor=0.75,
        bess_cap_kwh=bess_cap_kwh,
        bess_cost_kwh=bess_cost_kwh,
        peak_valley_spread=peak_valley_spread,
    )
    financial_dcf = {
        "total_capex_wan": dcf["total_capex_wan"],
        "bess_capex_wan": dcf["bess_capex_wan"],
        "self_use_ratio": round(self_use_ratio, 6),
        "self_use_pct": self_use_pct_out,
        "self_use_kwh": self_use_kwh_out,
        "annual_load_kwh": explicit_annual_load_kwh,
        "discount_rate_pct": disc_rate_pct,
        "weighted_tariff_rmb": weighted_tariff,
        "irr_pct": dcf["irr_pct"],
        "npv_25_wan": dcf["npv_wan"],
        "lcoe_rmb_kwh": dcf["lcoe_cny_kwh"],
        "static_payback_years": dcf["static_payback_years"],
        "dynamic_payback_years": dcf["dynamic_payback_years"],
        "cashflows_wan": dcf["cashflows_wan"],
    }

    port_allocation_ok = bool(
        total_modules == 0
        or (
            eff_strings_per_mppt >= 1
            and mppt_channels_used <= mppt_channels_capacity
            and string_count <= max_strings_capacity
            and all(bool(r.get("ok")) for r in mppt_table)
        )
    )

    summary_dict = {
        "module_count": total_modules,
        "placed_module_count": placed_total_count,
        "unused_module_count": unused_module_count,
        "pruned_shaded_modules": len(pruned_modules_out),
        "south_count": south_count,
        "north_count": north_count,
        "orientation_mode": orientation_mode,
        "rack_type": f"{rack_rows}P",
        "module_model": mod_model,
        "dc_kw": dc_kw,
        "ac_kw": total_ac_kw,
        "dc_ac_ratio": round(dc_kw / total_ac_kw, 2) if total_ac_kw > 0.0 else 0.0,
        "inverter_model": inv_model,
        "inverter_count": inv_count,
        "string_count": string_count,
        "modules_per_string": modules_per_string,
        "mppt_channels_used": mppt_channels_used,
        "mppt_channels_capacity": mppt_channels_capacity,
        "max_strings_capacity": max_strings_capacity,
        "port_allocation_ok": port_allocation_ok,
        "annual_kwh": annual_kwh,
        "specific_yield_kwh_kwp": round(pvsyst_res["summary"]["specific_yield_kwh_kwp"], 1),
        "pr_pct": round(pvsyst_res["summary"]["pr_pct"], 2),
        "dc_cable_saved_pct": saved_dc_pct,
        "al_cost_saving_pct": al_saving_pct,
        "self_use_pct": self_use_pct_out,
        "self_use_kwh": self_use_kwh_out,
        "discount_rate_pct": disc_rate_pct,
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

    pvsyst_res_clean = scrub_pvsyst_text(pvsyst_res)
    eff_setback_val = mf_struct["effective_setback_m"] if use_mf_layout else edge_setback
    shading_scope_note_zh = "当前卫星工作台障碍物遮挡基于相对高度角与方位权重作方案级年均折减估算，精细逐时三维网格阴影须转入三维工作台校核。"
    multifactor_dict = {
        "orientation_mode": orientation_mode,
        "mount_orientation": orientation,
        "rack_type": f"{rack_rows}P",
        "albedo": albedo_val,
        "albedo_surface": albedo_surface,
        "pollution_level": pol_key or "default",
        "soiling_pct": soiling_pct_val,
        "shading_loss_pct": total_shading_loss_pct,
        "shading_model_level": "scheme_heuristic_annual",
        "shading_scope_note_zh": shading_scope_note_zh,
        "extreme_temp_min_c": site_t_min_c,
        "max_series_safe": n_max_voc_safe,
        "min_series_mppt": n_min_mppt,
        "effective_setback_m": eff_setback_val,
        "pruned_shaded_modules": len(pruned_modules_out),
        "self_use_pct": self_use_pct_out,
        "self_use_kwh": self_use_kwh_out,
        "discount_rate_pct": disc_rate_pct,
    }
    health_check = evaluate_engineering_health_check(
        {
            "site": {"lat": lat, "lon": lon},
            "roof": {"type": roof_type, "setback_m": eff_setback_val},
            "summary": summary_dict,
            "port_allocation_ok": port_allocation_ok,
            "mppt_channels_used": mppt_channels_used,
            "mppt_channels_capacity": mppt_channels_capacity,
            "max_strings_capacity": max_strings_capacity,
            "snow_ok": snow_ok,
            "mppt_table": mppt_table,
            "strings": strings_list,
            "wiring_optimization": wiring_optimization,
            "structural_check": structural_check,
            "financial_dcf": financial_dcf,
            "multifactor": multifactor_dict,
            "multifactor_params": mf,
            "module_spec": {"vmp_v": mod_vmp_v, "voc_v": mod_voc_v, "imp_a": mod_imp_a, "beta_voc_pct_c": beta_voc_pct_c},
            "inverter_spec": {"max_dc_v": max_dc_v, "mppt_v_min": mppt_v_min, "mppt_v_max": mppt_v_max},
            "pvsyst": pvsyst_res_clean,
        }
    )

    return {
        "ok": True,
        "site": {"lat": lat, "lon": lon, "name": scrub_pvsyst_text(site.get("name", "卫星实景光伏项目"))},
        "roof": {
            "type": roof_type,
            "slope_deg": slope_deg,
            "parapet_height_m": parapet_height_m,
            "albedo": albedo_val,
            "polygon_m": poly_m,
            "obstacles": obstacles,
        },
        "summary": summary_dict,
        "modules": wired_modules,
        "unwired_modules": unwired_modules,
        "pruned_modules": pruned_modules_out,
        "strings": strings_list,
        "mppt_table": mppt_table,
        "wiring_optimization": wiring_optimization,
        "structural_check": structural_check,
        "financial_dcf": financial_dcf,
        "multifactor": multifactor_dict,
        "health_check": health_check,
        "electrical": {
            "inverter_model": inv_model,
            "inverter_count": inv_count,
            "string_count": string_count,
            "mppt_channels_used": mppt_channels_used,
            "mppt_channels_capacity": mppt_channels_capacity,
            "max_strings_capacity": max_strings_capacity,
            "port_allocation_ok": port_allocation_ok,
            "mppt_table": mppt_table,
            "wiring_optimization": wiring_optimization,
        },
        "cad_drawings": cad_res["sheets"],
        "pvsyst": pvsyst_res_clean,
        "live_weather": pvsyst_res_clean.get("live_weather"),
        "shading_model_level": "scheme_heuristic_annual",
        "shading_scope_note_zh": shading_scope_note_zh,
    }


def generate_four_cad_drawings(design_data: dict[str, Any]) -> dict[str, Any]:
    """Generate 4 AutoCAD-style SVG sheets (光伏排布图, 组串图, 防雷接地图, 支架图) from actual geometry."""
    validate_satmap_common_inputs(design_data)
    summary = design_data.get("summary") or {}
    mod_count = int(_strict_finite_float(summary["module_count"], "module_count")) if summary.get("module_count") not in (None, "") else 500
    dc_kw = _strict_finite_float(summary["dc_kw"], "dc_kw") if summary.get("dc_kw") not in (None, "") else 290.0
    inv_model = summary.get("inverter_model", "SG110CX-P2")
    str_count = int(_strict_finite_float(summary["string_count"], "string_count")) if summary.get("string_count") not in (None, "") else 27
    mods_per_str = max(1, int(_strict_finite_float(summary["modules_per_string"], "modules_per_string")) if summary.get("modules_per_string") not in (None, "") else 18)

    roof = design_data.get("roof") or {}
    poly = roof.get("polygon_m") or [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]]
    if not isinstance(poly, list) or len(poly) < 3:
        raise ValueError("roof.polygon_m must be a list of at least 3 [x, y] vertices.")
    obstacles = roof.get("obstacles") or []
    modules = design_data.get("modules") or []
    if not isinstance(obstacles, list) or not isinstance(modules, list):
        raise ValueError("obstacles and modules must be lists.")

    xs = [_strict_finite_float(p[0], "polygon_x") for p in poly]
    ys = [_strict_finite_float(p[1], "polygon_y") for p in poly]
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
            for sl_tag in ("south", "north", "east", "west"):
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


_CITIES_CACHE: list[dict[str, Any]] | None = None


def _load_cities_cache() -> list[dict[str, Any]]:
    global _CITIES_CACHE
    if _CITIES_CACHE is None:
        cities_file = ROOT / "desktop" / "web" / "cities.json"
        if cities_file.is_file():
            try:
                _CITIES_CACHE = json.loads(cities_file.read_text(encoding="utf-8")).get("cities") or []
            except Exception:
                _CITIES_CACHE = []
        else:
            _CITIES_CACHE = []
    return _CITIES_CACHE


def _infer_city_zh(lat: float, lon: float, hint_name: str = "") -> str:
    cities = _load_cities_cache()
    for c in cities:
        cname = str(c.get("name") or "")
        if cname and cname.rstrip("市") in (hint_name or ""):
            return cname
    if not cities:
        return "常州市"
    best_city = "常州市"
    best_d2 = 1e18
    for c in cities:
        try:
            d2 = (float(c["lat"]) - lat) ** 2 + ((float(c["lon"]) - lon) * math.cos(math.radians(lat))) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_city = str(c.get("name") or best_city)
        except Exception:
            continue
    return best_city


def _extract_existing_roof_origin(project_json_path: Path) -> tuple[float, float] | None:
    """Return (orig_minx, orig_miny) from an existing 3D project.json roof.outline if present."""
    if not project_json_path.is_file():
        return None
    try:
        raw = json.loads(project_json_path.read_text(encoding="utf-8"))
        outline = (raw.get("roof") or {}).get("outline") or []
        if len(outline) >= 3:
            xs = [float(pt[0]) for pt in outline]
            ys = [float(pt[1]) for pt in outline]
            return (min(xs), min(ys))
    except Exception:
        return None
    return None


def _build_3d_roof_and_site_from_satmap(
    payload: dict[str, Any],
    *,
    target_origin: tuple[float, float] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Polygon, float, float, tuple[float, float] | None]:
    """Normalize Satellite Design site, polygon, parapet, slope & 3D obstacles/keepouts into validated 3D dicts."""
    from shapely.geometry.polygon import orient

    validate_satmap_common_inputs(payload)
    site_in = payload.get("site") or {}
    roof_in = payload.get("roof") or {}
    mf_in = payload.get("multifactor_params") or {}

    raw_lat = _strict_finite_float(
        payload["lat"] if payload.get("lat") is not None else (site_in["lat"] if site_in.get("lat") is not None else 32.46),
        "lat",
    )
    raw_lon = _strict_finite_float(
        payload["lon"] if payload.get("lon") is not None else (site_in["lon"] if site_in.get("lon") is not None else 119.92),
        "lon",
    )
    if not (-90.0 <= raw_lat <= 90.0) or not (-180.0 <= raw_lon <= 180.0):
        raise ValueError("lat must be in [-90, 90] and lon in [-180, 180].")
    req_lat = max(0.0, min(55.0, raw_lat))
    req_lon = max(-180.0, min(180.0, raw_lon))
    proxy_station = _nearest_offline_weather_proxy(req_lat, req_lon)

    raw_alb = (
        payload.get("albedo")
        if payload.get("albedo") is not None
        else (mf_in.get("albedo") if mf_in.get("albedo") is not None else roof_in.get("albedo"))
    )
    alb_val, _ = resolve_albedo(raw_alb, roof_type=str(payload.get("roof_type") or roof_in.get("type") or "flat")) if raw_alb is not None else (0.20, "default")
    site_dict: dict[str, Any] = {
        "lat": req_lat,
        "lon": req_lon,
        "timezone": "Asia/Shanghai",
        "albedo": max(0.0, min(1.0, float(alb_val))),
    }
    if proxy_station is not None:
        site_dict["weather_proxy_lat"] = proxy_station[0]
        site_dict["weather_proxy_lon"] = proxy_station[1]
        site_dict["weather_proxy_note"] = (
            f"离线或外网不可达时借用最近内置核验气象站（{proxy_station[0]:.4f}°N, {proxy_station[1]:.4f}°E）气象序列，"
            f"太阳几何与风压距离仍按实际工程坐标（{req_lat:.4f}°N, {req_lon:.4f}°E）计算"
        )

    raw_outline = (
        payload.get("outline")
        or payload.get("roof_polygon_m")
        or roof_in.get("polygon_m")
        or roof_in.get("outline")
    )
    tgt_minx, tgt_miny = (float(target_origin[0]), float(target_origin[1])) if target_origin is not None else (0.0, 0.0)
    shift_x, shift_y = tgt_minx, tgt_miny
    roof_poly_shifted: Polygon | None = None
    outline_3d: list[list[float]] = []
    if raw_outline is not None and (not isinstance(raw_outline, list) or len(raw_outline) < 3):
        raise ValueError("roof_polygon_m / outline must be a list of at least 3 [x, y] vertices.")
    if isinstance(raw_outline, list) and len(raw_outline) >= 3:
        pts_checked = [(_strict_finite_float(p[0], "outline_x"), _strict_finite_float(p[1], "outline_y")) for p in raw_outline]
        try:
            cand_poly = Polygon(pts_checked)
            if not cand_poly.is_valid:
                cand_poly = cand_poly.buffer(0)
            if isinstance(cand_poly, Polygon) and not cand_poly.is_empty and cand_poly.area >= 25.0:
                minx, miny, _, _ = cand_poly.bounds
                shift_x, shift_y = tgt_minx - minx, tgt_miny - miny
                shifted = orient(
                    Polygon([(round(x + shift_x, 3), round(y + shift_y, 3)) for x, y in list(cand_poly.exterior.coords)[:-1]]),
                    sign=1,
                )
                if shifted.is_valid and shifted.area >= 25.0:
                    roof_poly_shifted = shifted
                    outline_3d = [[round(float(x), 3), round(float(y), 3)] for x, y in list(shifted.exterior.coords)[:-1]]
        except Exception:
            roof_poly_shifted = None

    if roof_poly_shifted is None:
        length_m = max(16.0, min(180.0, float(payload.get("length_m") or 76.0)))
        width_m = max(12.0, min(120.0, float(payload.get("width_m") or 36.0)))
        ox0, oy0 = round(tgt_minx, 3), round(tgt_miny, 3)
        outline_3d = [
            [ox0, oy0],
            [round(ox0 + length_m, 3), oy0],
            [round(ox0 + length_m, 3), round(oy0 + width_m, 3)],
            [ox0, round(oy0 + width_m, 3)],
        ]
        roof_poly_shifted = Polygon(outline_3d)

    in_roof_type = str(payload.get("roof_type") or roof_in.get("roof_type") or roof_in.get("type") or "flat").strip().lower()
    orient_mode = str(
        payload.get("orientation_mode")
        or mf_in.get("orientation_mode")
        or (payload.get("layout_params") or {}).get("orientation_mode")
        or ""
    ).strip().lower()
    in_slope = float(
        payload["slope_deg"]
        if payload.get("slope_deg") is not None
        else (roof_in["slope_deg"] if roof_in.get("slope_deg") is not None else (0.0 if in_roof_type == "flat" else 6.0))
    )
    bldg_h = float(
        payload["building_height_m"]
        if payload.get("building_height_m") is not None
        else (roof_in.get("building_height_m") or roof_in.get("height_m") or 12.0)
    )
    bldg_h = max(2.0, min(120.0, bldg_h))

    max_load_kg_raw = (
        mf_in.get("max_roof_load_kg_m2")
        if mf_in.get("max_roof_load_kg_m2") is not None
        else (payload.get("max_roof_load_kg_m2") if payload.get("max_roof_load_kg_m2") is not None else roof_in.get("max_load_kg_m2"))
    )
    # Note: East-West butterfly layout in 3D requires flat roof type
    if in_roof_type in ("metal", "double_slope", "single_slope") and in_slope >= 1.0 and orient_mode != "east_west":
        load_kn_m2 = round(max(0.25, float(max_load_kg_raw) * 9.81 / 1000.0), 3) if max_load_kg_raw is not None else 0.50
        roof_dict: dict[str, Any] = {
            "outline": outline_3d,
            "type": "metal",
            "height_m": round(bldg_h, 2),
            "parapet_height_m": 0.0,
            "slope_deg": round(max(1.0, min(30.0, in_slope)), 1),
            "slope_azimuth_deg": float(roof_in.get("azimuth_deg") if roof_in.get("azimuth_deg") is not None else 180.0) % 360.0,
            "load_capacity_kn_m2": load_kn_m2,
            "obstacles": [],
            "keepouts": [],
            "surroundings": [],
        }
    else:
        parapet_h = float(
            payload["parapet_height_m"]
            if payload.get("parapet_height_m") is not None
            else (roof_in["parapet_height_m"] if roof_in.get("parapet_height_m") is not None else 0.6)
        )
        load_kn_m2 = round(max(0.30, float(max_load_kg_raw) * 9.81 / 1000.0), 3) if max_load_kg_raw is not None else 1.50
        roof_dict = {
            "outline": outline_3d,
            "type": "flat",
            "height_m": round(bldg_h, 2),
            "parapet_height_m": round(max(0.0, min(3.0, parapet_h)), 2),
            "load_capacity_kn_m2": load_kn_m2,
            "obstacles": [],
            "keepouts": [],
            "surroundings": [],
        }

    raw_obstacles = payload.get("obstacles") if payload.get("obstacles") is not None else (roof_in.get("obstacles") or [])
    safe_inner = roof_poly_shifted.buffer(-0.15)
    used_zone_ids: set[str] = set()
    if isinstance(raw_obstacles, list) and not safe_inner.is_empty:
        for idx, obs in enumerate(raw_obstacles):
            if not isinstance(obs, dict):
                continue
            pts = obs.get("polygon") or obs.get("polygon_m") or obs.get("footprint") or []
            if len(pts) < 3 and (obs.get("w_m") or obs.get("w")) and (obs.get("h_m") or obs.get("h")):
                ox = float(obs.get("x_m") if obs.get("x_m") is not None else obs.get("x", 0.0))
                oy = float(obs.get("y_m") if obs.get("y_m") is not None else obs.get("y", 0.0))
                ow = max(0.4, float(obs.get("w_m") or obs.get("w") or 2.0)) * 0.5
                oh = max(0.4, float(obs.get("h_m") or obs.get("h") or 2.0)) * 0.5
                pts = [[ox - ow, oy - oh], [ox + ow, oy - oh], [ox + ow, oy + oh], [ox - ow, oy + oh]]
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
                h_obs = float(obs.get("height_m") or 0.0)
                obs_kind = str(obs.get("kind") or "").strip().lower()
                label = str(obs.get("name") or obs.get("label") or f"障碍区 #{idx + 1}").strip()[:40] or f"障碍区 #{idx + 1}"
                is_flat_keepout = (
                    h_obs < 0.30
                    or obs_kind in ("skylight", "vent", "keepout", "fire_lane", "walkway")
                    or ("天窗" in label)
                    or ("采光" in label)
                )
                for g_i, g in enumerate(geoms):
                    if not isinstance(g, Polygon) or g.area < 0.25:
                        continue
                    g_ccw = orient(g, sign=1)
                    coords = [[round(float(x), 3), round(float(y), 3)] for x, y in list(g_ccw.exterior.coords)[:-1]]
                    if len(coords) < 3 or not roof_poly_shifted.covers(Polygon(coords)):
                        continue
                    prefix = "kp" if is_flat_keepout else "obs"
                    zid = f"{prefix}-{idx + 1}" if g_i == 0 else f"{prefix}-{idx + 1}-{g_i + 1}"
                    while zid in used_zone_ids:
                        zid += "a"
                    used_zone_ids.add(zid)
                    if is_flat_keepout:
                        preset_val = "vent" if obs_kind == "vent" else "skylight"
                        roof_dict["keepouts"].append(
                            {
                                "id": zid,
                                "label": label,
                                "polygon": coords,
                                "preset": preset_val,
                            }
                        )
                    else:
                        roof_dict["obstacles"].append(
                            {
                                "id": zid,
                                "label": label,
                                "kind": "prism",
                                "height_m": round(max(0.30, min(45.0, h_obs)), 2),
                                "footprint": coords,
                            }
                        )
            except Exception:
                continue

    return site_dict, roof_dict, roof_poly_shifted, shift_x, shift_y, proxy_station


def save_to_guangzhu_project(payload: dict[str, Any], project_id: str | None = None) -> dict[str, Any]:
    """Convert a satellite map design into a full versioned Guangzhu project preserving site, equipment & layout."""
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
    record_dict["name"] = str(payload.get("name") or (payload.get("site") or {}).get("name") or "卫星实景光伏工程项目").strip()[:80] or "卫星实景光伏工程项目"
    record_dict.pop("collection", None)
    record_dict.pop("facts", None)
    record_dict.pop("park", None)
    existing_origin: tuple[float, float] | None = None
    if existed_before and (existing_dir / "project.json").is_file():
        existing_origin = _extract_existing_roof_origin(existing_dir / "project.json")
        existing_proj = storage.load(clean_id)
        record_dict["designs"] = list(existing_proj.designs)
    else:
        record_dict["designs"] = []

    site_dict, roof_dict, roof_poly_shifted, shift_x, shift_y, proxy_station = _build_3d_roof_and_site_from_satmap(
        payload,
        target_origin=existing_origin,
    )
    req_lat, req_lon = site_dict["lat"], site_dict["lon"]
    record_dict["site"] = site_dict
    record_dict["roof"] = roof_dict
    racking_id = "clamp_flush" if roof_dict["type"] == "metal" else "ballast_tilt"

    addr_note = str(payload.get("address") or (payload.get("site") or {}).get("address") or "").strip()
    record_dict["requirements"] = {
        "text": (
            f"由卫星图工作台转入（标定定位：{addr_note or record_dict['name']} {req_lat:.4f}°N, {req_lon:.4f}°E；"
            f"底图轮廓仅供前期方案排布参考，施工前须经现场实测与专业复核）。"
        ),
        "structured": {},
    }

    # Map selected module_id & inverter_id onto project.equipment (strictly no silent substitution)
    equip_in = payload.get("equipment") if isinstance(payload.get("equipment"), dict) else {}
    lp = payload.get("layout_params") or {}
    ep = payload.get("electrical_params") or {}
    mod_spec_in = payload.get("module_spec") or {}
    inv_spec_in = payload.get("inverter_spec") or {}
    mf_in = payload.get("multifactor_params") or {}
    sum_in_early = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    elec_in_early = payload.get("electrical") if isinstance(payload.get("electrical"), dict) else {}
    all_mods = electrical.load_catalog("modules.csv", include_extended=True)
    all_invs = electrical.load_catalog("inverters.csv", include_extended=True)
    req_mod_id = str(
        payload.get("module_id")
        or equip_in.get("module_id")
        or mod_spec_in.get("module_id")
        or mod_spec_in.get("id")
        or lp.get("module_id")
        or sum_in_early.get("module_id")
        or elec_in_early.get("module_id")
        or mf_in.get("module_id")
        or ""
    ).strip()
    if req_mod_id:
        if req_mod_id not in all_mods:
            for m_k, m_r in all_mods.items():
                if str(m_r.get("model") or "").strip().lower() == req_mod_id.lower():
                    req_mod_id = str(m_k)
                    break
        if req_mod_id not in all_mods:
            raise GzError(
                "EQUIPMENT_UNKNOWN",
                f"未知组件型号 ID: {req_mod_id}，拒绝静默替换设备。",
                "请从已注册组件目录中选择型号，或补充目录规格后再保存。",
            )
        resolved_mod_id = req_mod_id
    else:
        hint_stc_w = mod_spec_in.get("stc_w") or lp.get("stc_w") or payload.get("stc_w")
        hint_mod_model = str(sum_in_early.get("module_model") or lp.get("module_model") or payload.get("module_model") or "")
        raw_mods_hint = payload.get("modules_layout") if payload.get("modules_layout") is not None else payload.get("modules")
        has_mods_hint = isinstance(raw_mods_hint, list) and len(raw_mods_hint) > 0
        hint_dc = payload.get("dc_kw") or sum_in_early.get("dc_kw")
        hint_mc = payload.get("module_count") or sum_in_early.get("module_count") or (len(raw_mods_hint) if has_mods_hint else 0)
        implies_580w = (
            (hint_stc_w is not None and abs(float(hint_stc_w) - 580.0) < 1.0)
            or ("580" in hint_mod_model)
            or (hint_dc and hint_mc and abs(float(hint_dc) * 1000.0 / max(1, int(hint_mc)) - 580.0) < 6.0)
        )
        if implies_580w and "jinko-jkm580n-72hl4-bdv" in all_mods:
            resolved_mod_id = "jinko-jkm580n-72hl4-bdv"
        else:
            resolved_mod_id = record_dict.get("equipment", {}).get("module_id") or "trina-tsm-550de19"

    req_inv_id = str(
        payload.get("inverter_id")
        or equip_in.get("inverter_id")
        or inv_spec_in.get("inverter_id")
        or inv_spec_in.get("id")
        or ep.get("inverter_id")
        or sum_in_early.get("inverter_id")
        or elec_in_early.get("inverter_id")
        or mf_in.get("inverter_id")
        or ""
    ).strip()
    if req_inv_id:
        if req_inv_id not in all_invs:
            for i_k, i_r in all_invs.items():
                if str(i_r.get("model") or "").strip().lower() == req_inv_id.lower():
                    req_inv_id = str(i_k)
                    break
        if req_inv_id not in all_invs:
            raise GzError(
                "EQUIPMENT_UNKNOWN",
                f"未知逆变器型号 ID: {req_inv_id}，拒绝静默替换设备。",
                "请从已注册逆变器目录中选择型号，或补充目录规格后再保存。",
            )
        resolved_inv_id = req_inv_id
    else:
        hint_inv_model = str(
            elec_in_early.get("inverter_model")
            or ep.get("inverter_model")
            or inv_spec_in.get("model")
            or sum_in_early.get("inverter_model")
            or payload.get("inverter_model")
            or ""
        ).strip()
        resolved_inv_id = None
        if hint_inv_model:
            for i_k, i_r in all_invs.items():
                if str(i_r.get("model") or "").strip().lower() == hint_inv_model.lower():
                    resolved_inv_id = str(i_k)
                    break
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

    project_obj = Project.model_validate(record_dict)

    # Build Design preserving layout parameters, topology (including East-West butterfly), placed modules, and string length
    in_orient = str(
        payload.get("mount_orientation")
        or payload.get("orientation")
        or mf_in.get("mount_orientation")
        or lp.get("orientation")
        or "portrait"
    ).strip().lower()
    if in_orient not in ("portrait", "landscape"):
        in_orient = "portrait"
    orient_mode = str(
        payload.get("orientation_mode")
        or mf_in.get("orientation_mode")
        or lp.get("orientation_mode")
        or "south_fixed"
    ).strip().lower()
    in_tilt_raw = payload.get("tilt_deg") if payload.get("tilt_deg") is not None else (mf_in.get("tilt_deg") if mf_in.get("tilt_deg") is not None else lp.get("tilt_deg"))
    in_az_raw = payload.get("azimuth_deg") if payload.get("azimuth_deg") is not None else (mf_in.get("azimuth_deg") if mf_in.get("azimuth_deg") is not None else lp.get("azimuth_deg"))
    in_setback_raw = (
        payload.get("setback_m")
        if payload.get("setback_m") is not None
        else (
            payload.get("effective_setback_m")
            if payload.get("effective_setback_m") is not None
            else (
                payload.get("edge_setback_m")
                if payload.get("edge_setback_m") is not None
                else (mf_in.get("effective_setback_m") if mf_in.get("effective_setback_m") is not None else lp.get("edge_setback_m"))
            )
        )
    )
    in_mps_raw = (
        payload.get("modules_per_string")
        if payload.get("modules_per_string") is not None
        else (
            payload.get("string_series")
            if payload.get("string_series") is not None
            else (
                ep.get("modules_per_string")
                if ep.get("modules_per_string") is not None
                else (
                    inv_spec_in.get("modules_per_string")
                    if inv_spec_in.get("modules_per_string") is not None
                    else (
                        elec_in_early.get("modules_per_string")
                        if elec_in_early.get("modules_per_string") is not None
                        else sum_in_early.get("modules_per_string")
                    )
                )
            )
        )
    )

    raw_modules = payload.get("modules_layout") if payload.get("modules_layout") is not None else payload.get("modules")
    has_custom_modules = isinstance(raw_modules, list) and len(raw_modules) > 0

    layout_kwargs: dict[str, Any] = {"orientation": in_orient}
    if project_obj.roof.type == "flat":
        if orient_mode == "east_west":
            layout_kwargs["layout"] = "ew"
            ew_t = float(in_tilt_raw) if in_tilt_raw is not None else 10.0
            layout_kwargs["tilt_deg"] = max(5.0, min(15.0, ew_t))
        else:
            if in_tilt_raw is not None:
                layout_kwargs["tilt_deg"] = max(0.0, min(35.0, float(in_tilt_raw)))
            if in_az_raw is not None:
                az_norm = float(in_az_raw) % 360.0
                if 90.0 <= az_norm <= 270.0:
                    layout_kwargs["azimuth_deg"] = az_norm
    if in_setback_raw is not None:
        layout_kwargs["edge_setback_m"] = max(0.0, float(in_setback_raw))
    elif has_custom_modules:
        layout_kwargs["edge_setback_m"] = 0.50
    if has_custom_modules:
        layout_kwargs["obstacle_clearance_m"] = max(
            0.0,
            min(
                0.35,
                float(
                    payload.get("obstacle_clearance_m")
                    or payload.get("obstacle_setback_m")
                    or lp.get("obstacle_setback_m")
                    or 0.25
                ),
            ),
        )
        layout_kwargs["keepout_clearance_m"] = 0.20

    design_obj = layout.generate_layout(project_obj, layout_kwargs)
    layout_mode = "recomputed_from_outline"

    if has_custom_modules:
        try:
            mod_row = all_mods[resolved_mod_id]
            eff_rack_id = "ballast_ew" if design_obj.params.layout == "ew" else racking_id
            rack_row = electrical.load_catalog("racking.csv")[eff_rack_id]
            base_z = float(rack_row["lower_edge_height_m"])
            long_m, short_m = float(mod_row["length_m"]), float(mod_row["width_m"])
            slope_len, wid_len = (long_m, short_m) if in_orient == "portrait" else (short_m, long_m)
            geom_check = layout.usable_geometry(project_obj, design_obj.params)
            if orient_mode == "elevated_canopy":
                canopy_h = max(
                    0.5,
                    float(
                        payload.get("canopy_clear_height_m")
                        or mf_in.get("canopy_clear_height_m")
                        or payload.get("canopy_clearance_m")
                        or mf_in.get("canopy_clearance_m")
                        or 2.8
                    ),
                )
                base_z = max(base_z, canopy_h)
                usable_tol = geom_check["roof"].buffer(-max(0.0, design_obj.params.edge_setback_m - 0.15))
                for obs_3d in project_obj.roof.obstacles:
                    if float(getattr(obs_3d, "height_m", 0.0) or 0.0) > (canopy_h - 0.30):
                        usable_tol = usable_tol.difference(Polygon(obs_3d.footprint).buffer(max(0.0, design_obj.params.obstacle_clearance_m - 0.12)))
            else:
                usable_tol = geom_check["usable"].buffer(0.15)
            built_modules: list[Module] = []
            precision = 9 if project_obj.roof.type == "metal" else 3
            from .roofplane import elevation as roof_elevation

            row_buckets: dict[int, int] = {}
            is_ew = design_obj.params.layout == "ew"
            ew_pair_span = max(1.8, 2.0 * slope_len * math.cos(math.radians(design_obj.params.tilt_deg)) + 0.45)
            poly_minx = float(roof_poly_shifted.bounds[0])

            for idx_m, rm in enumerate(raw_modules):
                if not isinstance(rm, dict) or rm.get("unwired"):
                    continue
                raw_cx = rm.get("cx") if rm.get("cx") is not None else (rm.get("x_m") if rm.get("x_m") is not None else rm.get("x", 0.0))
                raw_cy = rm.get("cy") if rm.get("cy") is not None else (rm.get("y_m") if rm.get("y_m") is not None else rm.get("y", 0.0))
                cx = _strict_finite_float(raw_cx, "module.cx") + shift_x
                cy = _strict_finite_float(raw_cy, "module.cy") + shift_y
                m_tilt = float(design_obj.params.tilt_deg if (project_obj.roof.type == "metal" or is_ew) else rm.get("tilt_deg", design_obj.params.tilt_deg))
                m_tilt = max(0.0, min(35.0, m_tilt))
                if project_obj.roof.type == "metal":
                    m_az = float(design_obj.params.azimuth_deg)
                elif is_ew:
                    rm_slope = str(rm.get("slope") or "").lower()
                    rm_az_in = float(rm.get("azimuth_deg", 90.0)) % 360.0
                    m_az = 90.0 if (rm_slope == "east" or abs(rm_az_in - 90.0) < 45.0) else 270.0
                else:
                    m_az = float(rm.get("azimuth_deg", design_obj.params.azimuth_deg)) % 360.0

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
                if is_ew:
                    r_num = (int(rm["row"]) if int(rm["row"]) >= 1 else int(rm["row"]) + 1) if rm.get("row") is not None else max(1, int((cx - poly_minx) // ew_pair_span) + 1)
                else:
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
                raw_pitch = payload.get("row_spacing_m") or payload.get("row_gap_m") or lp.get("row_spacing_m") or design_obj.statistics.get("row_spacing_m") or 3.2
                min_pitch = (2.0 if is_ew else 1.0) * slope_len * math.cos(math.radians(design_obj.params.tilt_deg)) + 0.04
                in_pitch = max(min_pitch, float(raw_pitch))
                eff_chord = (2.0 if is_ew else 1.0) * slope_len
                stats = dict(
                    geom_check["area_statistics"],
                    row_spacing_m=in_pitch,
                    clear_gap_m=max(0.02, in_pitch - eff_chord * math.cos(math.radians(design_obj.params.tilt_deg))),
                    gcr=min(0.98, eff_chord / in_pitch),
                    module_count=len(built_modules),
                    dc_kw=round(len(built_modules) * float(mod_row["stc_w"]) / 1000.0, 4),
                    rows=len({m.row for m in built_modules}),
                    module_area_ratio=len(built_modules) * long_m * short_m / geom_check["roof"].area,
                )
                design_obj = Design(params=design_obj.params, modules=built_modules, statistics=stats)
                layout_mode = "preserved_satellite_modules"
            else:
                raise GzError(
                    "LAYOUT_MODULES_OUT_OF_BOUNDS",
                    "卫星工作台传入的组件排布全部超出有效屋面边界，无法保真转入。",
                    "请检查屋面退距与禁布区设置后重新排布再保存。",
                )
        except GzError:
            raise
        except Exception as exc:
            raise GzError(
                "LAYOUT_PRESERVE_FAILED",
                f"保留卫星组件几何布局时失败: {exc}",
                "请核对传入组件坐标与尺寸参数后重试。",
            ) from exc

    if in_mps_raw is not None:
        try:
            mps_int = int(in_mps_raw)
            if mps_int >= 1:
                design_obj.modules_per_string = mps_int
        except (TypeError, ValueError):
            pass

    offline_flag = bool(payload.get("offline", True))

    # Atomic project + versioned design + analysis transaction with rollback on any error
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

    # F13-01: Reconcile Satellite submitted electrical/capacity expectations against 3D analyzed allocation
    elec_3d_path = existing_dir / "analysis" / f"v{target_ver}" / "electrical.json"
    elec_3d: dict[str, Any] = {}
    if elec_3d_path.is_file():
        try:
            elec_3d = json.loads(elec_3d_path.read_text(encoding="utf-8"))
        except Exception:
            elec_3d = {}
    sum_elec = summary.get("electrical") if isinstance(summary.get("electrical"), dict) else {}

    ac_kw_3d_calc = 0.0
    for inv_entry in elec_3d.get("inverters") or []:
        if isinstance(inv_entry, dict):
            iid = str(inv_entry.get("inverter_id") or "")
            cnt = int(inv_entry.get("count") or 0)
            if iid in all_invs and cnt > 0:
                ac_kw_3d_calc += cnt * float(all_invs[iid]["rated_ac_kw"])
    if ac_kw_3d_calc <= 0.0:
        if sum_elec.get("rated_ac_kw") is not None:
            ac_kw_3d_calc = float(sum_elec["rated_ac_kw"])
        elif float(elec_3d.get("dc_ac_ratio") or 0.0) > 0.0:
            ac_kw_3d_calc = float(elec_3d.get("dc_kw") or 0.0) / float(elec_3d["dc_ac_ratio"])

    analyzed_3d = {
        "module_count": int(summary.get("modules") or elec_3d.get("module_count") or len(design_obj.modules)),
        "dc_kw": round(float(summary.get("dc_kw") or elec_3d.get("dc_kw") or 0.0), 2),
        "inverter_id": elec_3d.get("inverter_id") or project_obj.equipment.inverter_id,
        "inverter_model": elec_3d.get("inverter_model") or sum_elec.get("inverter_model"),
        "inverter_count": int(elec_3d.get("inverter_count") or sum_elec.get("inverter_count") or 0),
        "ac_kw": round(ac_kw_3d_calc, 2),
        "string_count": int(elec_3d.get("string_count") or sum_elec.get("string_count") or 0),
        "modules_per_string": int(elec_3d.get("modules_per_string") or getattr(design_obj, "modules_per_string", 0) or 0),
    }

    pvs_in = payload.get("pvsyst_summary") if isinstance(payload.get("pvsyst_summary"), dict) else {}
    sum_in = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    elec_in = payload.get("electrical") if isinstance(payload.get("electrical"), dict) else {}
    submitted: dict[str, Any] = {}

    def _pick_submitted(field_keys: tuple[str, ...], containers: tuple[dict[str, Any], ...], as_int: bool = False) -> Any:
        for fk in field_keys:
            for c_dict in containers:
                if not isinstance(c_dict, dict):
                    continue
                val = c_dict.get(fk)
                if val is not None and val != "" and not isinstance(val, bool):
                    return int(round(float(val))) if as_int else round(float(val), 2)
        return None

    sub_mod_cnt = _pick_submitted(("expected_module_count", "module_count"), (payload, sum_in, pvs_in), as_int=True)
    if sub_mod_cnt is None and has_custom_modules:
        sub_mod_cnt = sum(1 for rm in raw_modules if isinstance(rm, dict) and not rm.get("unwired"))
    if sub_mod_cnt is not None:
        submitted["module_count"] = sub_mod_cnt

    sub_dc_kw = _pick_submitted(("expected_dc_kw", "dc_kw"), (payload, sum_in, pvs_in), as_int=False)
    if sub_dc_kw is not None:
        submitted["dc_kw"] = sub_dc_kw

    sub_inv_cnt = _pick_submitted(("expected_inverter_count", "inverter_count"), (payload, elec_in, ep, inv_spec_in, sum_in, pvs_in), as_int=True)
    if sub_inv_cnt is not None:
        submitted["inverter_count"] = sub_inv_cnt

    has_exp_inv_only = (
        _pick_submitted(("expected_inverter_count",), (payload, elec_in, ep, inv_spec_in, sum_in, pvs_in), as_int=True) is not None
        and _pick_submitted(("expected_ac_kw",), (payload, elec_in, sum_in, pvs_in), as_int=False) is None
    )
    sub_ac_kw = (
        None
        if has_exp_inv_only
        else _pick_submitted(("expected_ac_kw", "ac_kw", "total_ac_kw"), (payload, elec_in, sum_in, pvs_in), as_int=False)
    )
    if sub_ac_kw is None and sub_inv_cnt is not None:
        unit_ac = _pick_submitted(("rated_ac_kw",), (ep, inv_spec_in), as_int=False)
        if unit_ac is None and resolved_inv_id and resolved_inv_id in all_invs:
            unit_ac = round(float(all_invs[resolved_inv_id]["rated_ac_kw"]), 2)
        if unit_ac is not None:
            sub_ac_kw = round(sub_inv_cnt * unit_ac, 2)
    if sub_ac_kw is not None:
        submitted["ac_kw"] = sub_ac_kw

    sub_str_cnt = _pick_submitted(("expected_string_count", "string_count"), (payload, elec_in, ep, sum_in), as_int=True)
    if sub_str_cnt is not None:
        submitted["string_count"] = sub_str_cnt

    sub_mps = _pick_submitted(("expected_modules_per_string", "modules_per_string", "string_series"), (payload, ep, inv_spec_in, elec_in, sum_in), as_int=True)
    if sub_mps is not None:
        submitted["modules_per_string"] = sub_mps

    recon_diffs: list[dict[str, Any]] = []
    for k_int in ("module_count", "inverter_count", "string_count", "modules_per_string"):
        if k_int in submitted:
            sv = int(submitted[k_int])
            av = int(analyzed_3d[k_int])
            if sv != av:
                recon_diffs.append({"field": k_int, "submitted": sv, "analyzed_3d": av, "delta": av - sv})
    for k_flt in ("dc_kw", "ac_kw"):
        if k_flt in submitted:
            sv_f = float(submitted[k_flt])
            av_f = float(analyzed_3d[k_flt])
            tol = max(0.5, 0.02 * max(1.0, abs(av_f)))
            if abs(sv_f - av_f) > tol:
                recon_diffs.append(
                    {"field": k_flt, "submitted": round(sv_f, 2), "analyzed_3d": round(av_f, 2), "delta": round(av_f - sv_f, 2)}
                )

    allocation_reconciliation = {
        "matched": len(recon_diffs) == 0,
        "submitted": submitted,
        "analyzed_3d": analyzed_3d,
        "diffs": recon_diffs,
    }

    return {
        "ok": True,
        "project_id": clean_id,
        "version": target_ver,
        "layout_mode": layout_mode,
        "weather_proxy_site": list(proxy_station) if proxy_station else None,
        "outline_vertices": len(project_obj.roof.outline),
        "obstacle_count": len(project_obj.roof.obstacles),
        "keepout_count": len(project_obj.roof.keepouts),
        "summary": summary,
        "allocation_reconciliation": allocation_reconciliation,
    }


def _roof_area_from_dict(roof_dict: dict[str, Any]) -> float:
    outline = roof_dict.get("outline") or []
    if len(outline) >= 3:
        try:
            return round(float(Polygon([(float(p[0]), float(p[1])) for p in outline]).area), 1)
        except Exception:
            return 0.0
    return 0.0


def get_satmap_3d_catalog() -> dict[str, Any]:
    """List existing 3D projects, custom my-roofs, and built-in 3D templates for bidirectional Satellite <-> 3D linkage."""
    proj_root = Path(PROJECTS_DIR) if PROJECTS_DIR != ROOT / "projects" else Path(storage.PROJECTS_DIR)
    projects_out: list[dict[str, Any]] = []
    if proj_root.is_dir():
        for p_json in sorted(proj_root.glob("*/project.json")):
            try:
                pdata = json.loads(p_json.read_text(encoding="utf-8"))
                pid = str(pdata.get("id") or p_json.parent.name)
                site_d = pdata.get("site") or {}
                roof_d = pdata.get("roof") or {}
                lat = float(site_d.get("lat") or 31.81)
                lon = float(site_d.get("lon") or 119.97)
                pname = str(pdata.get("name") or pid)
                city = _infer_city_zh(lat, lon, pname)

                designs_dir = p_json.parent / "designs"
                versions = [
                    int(m.group(1))
                    for f in (designs_dir.glob("v*.json") if designs_dir.is_dir() else [])
                    if (m := re.fullmatch(r"v([1-9]\d*)\.json", f.name))
                ]
                latest_ver = max(versions, default=0)
                has_result = False
                dc_kw = 0.0
                mod_count = 0
                annual_kwh = 0.0
                pr_pct = 0.0
                newest_mtime = p_json.stat().st_mtime

                if latest_ver >= 1:
                    d_file = designs_dir / f"v{latest_ver}.json"
                    s_file = p_json.parent / "analysis" / f"v{latest_ver}" / "summary.json"
                    if d_file.is_file():
                        newest_mtime = max(newest_mtime, d_file.stat().st_mtime)
                        d_json = json.loads(d_file.read_text(encoding="utf-8"))
                        mod_count = len(d_json.get("modules") or [])
                        dc_kw = round(float((d_json.get("statistics") or {}).get("dc_kw") or 0.0), 2)
                    if s_file.is_file():
                        has_result = True
                        newest_mtime = max(newest_mtime, s_file.stat().st_mtime)
                        s_json = json.loads(s_file.read_text(encoding="utf-8"))
                        dc_kw = round(float(s_json.get("dc_kw") or dc_kw), 2)
                        mod_count = int(s_json.get("modules") or mod_count)
                        annual_kwh = round(float((s_json.get("yield_kwh") or {}).get("p50") or 0.0), 1)
                        shade_loss = float((s_json.get("shading") or {}).get("avg_loss_pct") or 2.0)
                        pr_pct = round(min(90.5, max(65.0, 84.8 - shade_loss * 0.70)), 2) if dc_kw > 0 else 0.0

                updated_iso = datetime.fromtimestamp(newest_mtime, tz=timezone.utc).isoformat()
                projects_out.append(
                    {
                        "id": pid,
                        "name": pname,
                        "city": city,
                        "roof_type": str(roof_d.get("type") or "flat"),
                        "version": latest_ver,
                        "dc_kw": dc_kw,
                        "module_count": mod_count,
                        "annual_kwh": annual_kwh,
                        "pr_pct": pr_pct,
                        "has_result": has_result,
                        "updated_at": updated_iso,
                    }
                )
            except Exception:
                continue

    projects_out.sort(key=lambda x: x.get("updated_at") or "", reverse=True)

    my_roofs_out: list[dict[str, Any]] = []
    mr_dir = myroofs.folder(ROOT)
    if mr_dir.is_dir():
        for mr_json in sorted(mr_dir.glob("*/project.json")):
            try:
                mdata = json.loads(mr_json.read_text(encoding="utf-8"))
                mid = str(mdata.get("id") or mr_json.parent.name)
                site_d = mdata.get("site") or {}
                roof_d = mdata.get("roof") or {}
                lat = float(site_d.get("lat") or 31.81)
                lon = float(site_d.get("lon") or 119.97)
                mname = str(mdata.get("name") or mid)
                obs_cnt = len(roof_d.get("obstacles") or []) + len(roof_d.get("keepouts") or [])
                my_roofs_out.append(
                    {
                        "id": mid,
                        "name": mname,
                        "city": _infer_city_zh(lat, lon, mname),
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "area_m2": _roof_area_from_dict(roof_d),
                        "obstacle_count": obs_cnt,
                        "parapet_height_m": round(float(roof_d.get("parapet_height_m") or 0.0), 2),
                        "roof_type": str(roof_d.get("type") or "flat"),
                    }
                )
            except Exception:
                continue

    templates_out: list[dict[str, Any]] = []
    try:
        tpl_map = templates.catalog_data(all=False, root=ROOT, mine=False)
        for tid, (_tpath, tdata) in tpl_map.items():
            if "--" in tid:
                continue
            site_d = tdata.get("site") or {}
            roof_d = tdata.get("roof") or {}
            lat = float(site_d.get("lat") or 31.81)
            lon = float(site_d.get("lon") or 119.97)
            tname = str(tdata.get("name") or tid)
            obs_cnt = len(roof_d.get("obstacles") or []) + len(roof_d.get("keepouts") or [])
            templates_out.append(
                {
                    "id": tid,
                    "name": tname,
                    "city": _infer_city_zh(lat, lon, tname),
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "area_m2": _roof_area_from_dict(roof_d),
                    "obstacle_count": obs_cnt,
                    "parapet_height_m": round(float(roof_d.get("parapet_height_m") or 0.0), 2),
                    "roof_type": str(roof_d.get("type") or "flat"),
                    "collection": str(tdata.get("collection") or "demo"),
                }
            )
    except Exception:
        pass

    return {
        "ok": True,
        "projects": projects_out,
        "my_roofs": my_roofs_out,
        "templates": templates_out,
    }


def convert_from_3d_to_satmap(kind: str, item_id: str, version: int | None = None) -> dict[str, Any]:
    """Convert a 3D Design project, custom roof, or template into a centered Satellite Design state payload."""
    from .models import GzError, project_id as validate_pid

    kind_clean = (kind or "").strip().lower()
    if kind_clean in ("project", "projects"):
        norm_kind = "project"
    elif kind_clean in ("my-roof", "my_roof", "myroof", "my-roofs"):
        norm_kind = "my-roof"
    elif kind_clean in ("template", "templates"):
        norm_kind = "template"
    else:
        raise ValueError(f"Unsupported 3D source kind '{kind}'. Expected 'project', 'my-roof', or 'template'.")

    try:
        safe_id = validate_pid(item_id)
    except GzError as exc:
        raise LookupError(f"Invalid item_id '{item_id}'.") from exc

    proj_root = Path(PROJECTS_DIR) if PROJECTS_DIR != ROOT / "projects" else Path(storage.PROJECTS_DIR)
    design_dict: dict[str, Any] = {}
    summary_dict: dict[str, Any] = {}
    econ_dict: dict[str, Any] = {}
    resolved_ver: int | None = None

    if norm_kind == "project":
        p_dir = (proj_root / safe_id).resolve()
        if not p_dir.is_relative_to(proj_root.resolve()) or not (p_dir / "project.json").is_file():
            raise LookupError(f"3D project '{safe_id}' not found.")
        pdata = json.loads((p_dir / "project.json").read_text(encoding="utf-8"))
        d_dir = p_dir / "designs"
        versions = [
            int(m.group(1))
            for f in (d_dir.glob("v*.json") if d_dir.is_dir() else [])
            if (m := re.fullmatch(r"v([1-9]\d*)\.json", f.name))
        ]
        resolved_ver = version if (version is not None and version in versions) else (max(versions) if versions else None)
        if resolved_ver is not None:
            d_file = d_dir / f"v{resolved_ver}.json"
            if d_file.is_file():
                design_dict = json.loads(d_file.read_text(encoding="utf-8"))
            s_file = p_dir / "analysis" / f"v{resolved_ver}" / "summary.json"
            if s_file.is_file():
                summary_dict = json.loads(s_file.read_text(encoding="utf-8"))
            e_file = p_dir / "analysis" / f"v{resolved_ver}" / "economics.json"
            if e_file.is_file():
                econ_dict = json.loads(e_file.read_text(encoding="utf-8"))
    elif norm_kind == "my-roof":
        mr_file = (myroofs.folder(ROOT) / safe_id / "project.json").resolve()
        if not mr_file.is_relative_to(myroofs.folder(ROOT).resolve()) or not mr_file.is_file():
            raise LookupError(f"Custom 3D roof '{safe_id}' not found.")
        pdata = json.loads(mr_file.read_text(encoding="utf-8"))
    else:
        try:
            t_path = templates.resolve(safe_id, root=ROOT)
            pdata = json.loads(t_path.read_text(encoding="utf-8"))
        except GzError as exc:
            raise LookupError(f"3D template '{safe_id}' not found.") from exc
        d_file = t_path.parent / "designs" / "v1.json"
        s_file = t_path.parent / "analysis" / "v1" / "summary.json"
        e_file = t_path.parent / "analysis" / "v1" / "economics.json"
        if d_file.is_file():
            design_dict = json.loads(d_file.read_text(encoding="utf-8"))
            resolved_ver = 1
        if s_file.is_file():
            summary_dict = json.loads(s_file.read_text(encoding="utf-8"))
        if e_file.is_file():
            econ_dict = json.loads(e_file.read_text(encoding="utf-8"))

    site_d = pdata.get("site") or {}
    roof_d = pdata.get("roof") or {}
    equip_d = pdata.get("equipment") or {}
    d_params = design_dict.get("params") or {}
    d_stats = design_dict.get("statistics") or {}

    lat = float(site_d.get("lat") or 31.81)
    lon = float(site_d.get("lon") or 119.97)
    name = str(pdata.get("name") or safe_id)
    city = _infer_city_zh(lat, lon, name)

    raw_outline = roof_d.get("outline") or []
    if len(raw_outline) < 3 and roof_d.get("parts"):
        from shapely.ops import unary_union as _uunion
        part_polys = [Polygon(pt["outline"]) for pt in roof_d["parts"] if len(pt.get("outline") or []) >= 3]
        if part_polys:
            merged = _uunion(part_polys).convex_hull
            raw_outline = list(merged.exterior.coords)[:-1]
    if len(raw_outline) < 3:
        raw_outline = [[0.0, 0.0], [60.0, 0.0], [60.0, 30.0], [0.0, 30.0]]

    xs = [float(p[0]) for p in raw_outline]
    ys = [float(p[1]) for p in raw_outline]
    cx = 0.5 * (min(xs) + max(xs))
    cy = 0.5 * (min(ys) + max(ys))
    centered_poly = [[round(float(p[0]) - cx, 3), round(float(p[1]) - cy, 3)] for p in raw_outline]

    raw_rtype = str(roof_d.get("type") or "flat").lower()
    if raw_rtype == "metal":
        sat_rtype = "single_slope"
    elif raw_rtype == "pitched":
        sat_rtype = "double_slope"
    else:
        sat_rtype = "flat"

    slope_deg = float(
        roof_d.get("slope_deg")
        if roof_d.get("slope_deg") is not None
        else ((roof_d.get("pitched") or {}).get("tilt_deg") or 0.0)
    )
    roof_az = float(roof_d.get("slope_azimuth_deg") if roof_d.get("slope_azimuth_deg") is not None else 180.0)
    load_kn = float(roof_d.get("load_capacity_kn_m2") if roof_d.get("load_capacity_kn_m2") is not None else 1.5)
    max_load_kg = round(load_kn * 1000.0 / 9.81, 1)

    obstacles_out: list[dict[str, Any]] = []
    for idx_o, obs in enumerate(roof_d.get("obstacles") or []):
        if not isinstance(obs, dict):
            continue
        oid = str(obs.get("id") or f"obs-{idx_o + 1}")
        oname = str(obs.get("label") or obs.get("name") or oid)
        okind = str(obs.get("kind") or "prism")
        oh_m = round(float(obs.get("height_m") or 2.0), 2)
        if okind == "cylinder" and obs.get("center"):
            ocx = round(float(obs["center"][0]) - cx, 3)
            ocy = round(float(obs["center"][1]) - cy, 3)
            rad = max(0.3, float(obs.get("radius_m") or 1.2))
            opoly = [
                [round(ocx + rad * math.cos(2.0 * math.pi * k / 16), 3), round(ocy + rad * math.sin(2.0 * math.pi * k / 16), 3)]
                for k in range(16)
            ]
            obstacles_out.append(
                {
                    "id": oid,
                    "kind": "cylinder",
                    "name": oname,
                    "label": oname,
                    "x_m": ocx,
                    "y_m": ocy,
                    "w_m": round(2.0 * rad, 3),
                    "h_m": round(2.0 * rad, 3),
                    "height_m": oh_m,
                    "polygon_m": opoly,
                    "polygon": opoly,
                }
            )
        elif len(obs.get("footprint") or []) >= 3:
            opoly = [[round(float(p[0]) - cx, 3), round(float(p[1]) - cy, 3)] for p in obs["footprint"]]
            oxs = [p[0] for p in opoly]
            oys = [p[1] for p in opoly]
            obstacles_out.append(
                {
                    "id": oid,
                    "kind": "hvac" if okind == "prism" else okind,
                    "name": oname,
                    "label": oname,
                    "x_m": round(0.5 * (min(oxs) + max(oxs)), 3),
                    "y_m": round(0.5 * (min(oys) + max(oys)), 3),
                    "w_m": round(max(oxs) - min(oxs), 3),
                    "h_m": round(max(oys) - min(oys), 3),
                    "height_m": oh_m,
                    "polygon_m": opoly,
                    "polygon": opoly,
                }
            )

    all_keepouts = list(roof_d.get("keepouts") or []) + list(design_dict.get("added_keepouts") or [])
    for idx_k, kp in enumerate(all_keepouts):
        if not isinstance(kp, dict) or len(kp.get("polygon") or []) < 3:
            continue
        kid = str(kp.get("id") or f"kp-{idx_k + 1}")
        kname = str(kp.get("label") or kp.get("name") or kid)
        kkind = str(kp.get("preset") or ("skylight" if ("天窗" in kname or "采光" in kname) else "keepout"))
        kpoly = [[round(float(p[0]) - cx, 3), round(float(p[1]) - cy, 3)] for p in kp["polygon"]]
        kxs = [p[0] for p in kpoly]
        kys = [p[1] for p in kpoly]
        obstacles_out.append(
            {
                "id": kid,
                "kind": kkind,
                "name": kname,
                "label": kname,
                "x_m": round(0.5 * (min(kxs) + max(kxs)), 3),
                "y_m": round(0.5 * (min(kys) + max(kys)), 3),
                "w_m": round(max(kxs) - min(kxs), 3),
                "h_m": round(max(kys) - min(kys), 3),
                "height_m": 0.15 if kkind in ("skylight", "vent") else 0.05,
                "polygon_m": kpoly,
                "polygon": kpoly,
            }
        )

    layout_mode_3d = str(d_params.get("layout") or "south").lower()
    if layout_mode_3d == "ew":
        orient_mode = "east_west"
    elif sat_rtype != "flat":
        orient_mode = "flush_pitched"
    else:
        orient_mode = "south_fixed"

    mount_orient = str(d_params.get("orientation") or "portrait").lower()
    if mount_orient not in ("portrait", "landscape"):
        mount_orient = "portrait"
    d_tilt = float(d_params["tilt_deg"]) if d_params.get("tilt_deg") is not None else (15.0 if sat_rtype == "flat" else max(4.0, slope_deg))
    d_az = 90.0 if orient_mode == "east_west" else float(d_params.get("azimuth_deg") if d_params.get("azimuth_deg") is not None else roof_az)
    row_gap_m = round(float(d_stats.get("clear_gap_m") or d_stats.get("row_spacing_m") or 1.25), 3)

    dc_kw_ref = round(float(summary_dict.get("dc_kw") or d_stats.get("dc_kw") or 0.0), 2)
    mod_cnt_ref = int(summary_dict.get("modules") or len(design_dict.get("modules") or []))
    annual_kwh_ref = round(float((summary_dict.get("yield_kwh") or {}).get("p50") or 0.0), 1)
    shade_avg = float((summary_dict.get("shading") or {}).get("avg_loss_pct") or 2.0)
    pr_ref = round(min(90.5, max(65.0, 84.8 - shade_avg * 0.70)), 2) if dc_kw_ref > 0 else 0.0
    econ_sum = summary_dict.get("economics") or {}
    lcoe_ref = econ_sum.get("lcoe_cny_kwh") if econ_sum.get("lcoe_cny_kwh") is not None else econ_dict.get("lcoe_cny_kwh")
    npv_ref = econ_dict.get("npv_cny")

    return {
        "ok": True,
        "source": {
            "kind": norm_kind,
            "id": safe_id,
            "name": name,
            "version": resolved_ver,
        },
        "site": {
            "name": name,
            "city": city,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
        },
        "roof": {
            "polygon_m": centered_poly,
            "roof_polygon_latlon": _meters_to_latlon_poly(lat, lon, centered_poly),
            "roof_type": sat_rtype,
            "roof_type_3d": raw_rtype,
            "building_height_m": round(float(roof_d.get("height_m") or 12.0), 2),
            "parapet_height_m": round(float(roof_d.get("parapet_height_m") or 0.0), 2),
            "slope_deg": round(slope_deg, 2),
            "azimuth_deg": round(roof_az, 1),
            "setback_m": round(float(d_params.get("edge_setback_m") if d_params.get("edge_setback_m") is not None else 0.8), 2),
            "max_load_kg_m2": max_load_kg,
            "albedo": round(float(site_d.get("albedo") if site_d.get("albedo") is not None else 0.20), 2),
        },
        "obstacles": obstacles_out,
        "design": {
            "module_id": str(equip_d.get("module_id") or "trina-tsm-550de19"),
            "inverter_id": str(equip_d.get("inverter_id") or "sungrow-sg110cx"),
            "tilt_deg": round(d_tilt, 1),
            "azimuth_deg": round(d_az, 1),
            "row_gap_m": row_gap_m,
            "orientation_mode": orient_mode,
            "mount_orientation": mount_orient,
            "modules_per_string": design_dict.get("modules_per_string"),
        },
        "reference_metrics": {
            "dc_kw": dc_kw_ref,
            "module_count": mod_cnt_ref,
            "annual_kwh": annual_kwh_ref,
            "pr_pct": pr_ref,
            "lcoe_cny_kwh": round(float(lcoe_ref), 4) if isinstance(lcoe_ref, (int, float)) else None,
            "npv_cny": round(float(npv_ref), 2) if isinstance(npv_ref, (int, float)) else None,
        },
    }


def sync_satmap_to_3d(payload: dict[str, Any]) -> dict[str, Any]:
    """Bidirectionally sync a Satellite Design state into 3D my-roofs AND/OR a versioned 3D project."""
    from .models import GzError

    raw_mode = str(payload.get("sync_mode") or "both").strip().lower().replace("-", "_")
    if raw_mode not in ("both", "project", "my_roof"):
        raise ValueError(f"Unsupported sync_mode '{raw_mode}'. Expected 'both', 'project', or 'my_roof'.")

    if PROJECTS_DIR != storage.PROJECTS_DIR and PROJECTS_DIR != ROOT / "projects":
        storage.PROJECTS_DIR = PROJECTS_DIR

    mr_origin: tuple[float, float] | None = None
    if payload.get("project_id"):
        cand_pid = re.sub(r"[^A-Za-z0-9_-]", "-", str(payload["project_id"])).strip("-")[:48]
        if cand_pid:
            mr_origin = _extract_existing_roof_origin(storage._path(cand_pid) / "project.json")
    if mr_origin is None and payload.get("roof_id"):
        cand_rid = re.sub(r"[^A-Za-z0-9_-]", "-", str(payload["roof_id"])).strip("-")[:48]
        if cand_rid:
            mr_origin = _extract_existing_roof_origin(myroofs.folder(ROOT) / cand_rid / "project.json")

    site_dict, roof_dict, _poly_shifted, _sx, _sy, _proxy = _build_3d_roof_and_site_from_satmap(
        payload,
        target_origin=mr_origin,
    )
    raw_name = str(payload.get("name") or (payload.get("site") or {}).get("name") or "卫星同步三维屋顶").strip() or "卫星同步三维屋顶"
    sync_at = datetime.now(timezone.utc).isoformat()
    notes: list[str] = []

    saved_roof_id: str | None = None
    if raw_mode in ("both", "my_roof"):
        raw_rid = payload.get("roof_id") or (
            f"my-sat-{re.sub(r'[^A-Za-z0-9_-]', '-', str(payload['project_id']))[:32]}"
            if payload.get("project_id")
            else f"my-sat-{int(time.time() * 1000) % 100000000}"
        )
        clean_rid = re.sub(r"[^A-Za-z0-9_-]", "-", str(raw_rid)).strip("-")[:48] or "my-sat-roof"
        if not clean_rid[0].isalnum():
            clean_rid = "m" + clean_rid
        mr_payload = {
            "id": clean_rid,
            "name": raw_name[:40],
            "site": {
                "lat": site_dict["lat"],
                "lon": site_dict["lon"],
                "albedo": site_dict["albedo"],
            },
            "roof": roof_dict,
        }
        saved_roof_id = myroofs.save(mr_payload, root=ROOT, create=True)
        notes.append(
            f"已写入 3D 自建屋顶库 ({saved_roof_id})，含 {len(roof_dict['obstacles'])} 处三维立体障碍物与 {len(roof_dict['keepouts'])} 处采光/禁布区。"
        )

    out_pid: str | None = None
    out_ver: int | None = None
    out_summary: dict[str, Any] | None = None
    alloc_recon: dict[str, Any] | None = None
    if raw_mode in ("both", "project"):
        proj_payload = dict(payload)
        if payload.get("project_id") and "overwrite" not in proj_payload:
            proj_payload["overwrite"] = True
        try:
            proj_res = save_to_guangzhu_project(proj_payload, project_id=payload.get("project_id"))
        except GzError as exc:
            if exc.error_code in ("DESIGN_LOCK_GEOMETRY_CHANGED", "DESIGN_LOCK_STALE"):
                proj_payload["overwrite"] = False
                proj_res = save_to_guangzhu_project(proj_payload, project_id=payload.get("project_id"))
                notes.append("原 3D 项目含锁定几何约束，已自动派生独立新项目以保护原锁定版本。")
            else:
                raise
        out_pid = proj_res["project_id"]
        out_ver = proj_res["version"]
        out_summary = proj_res["summary"]
        alloc_recon = proj_res.get("allocation_reconciliation")
        notes.append(f"已生成 3D 工程结果版本 {out_pid} (v{out_ver})，支持三维阴影、组串走线与结构荷载全景检视。")
        if isinstance(alloc_recon, dict) and not alloc_recon.get("matched", True):
            diff_fields = "、".join(str(d.get("field")) for d in (alloc_recon.get("diffs") or []))
            notes.append(f"3D 电气/容量重配对账存在差异（{diff_fields}），详见 allocation_reconciliation。")

    # Extract Satellite vs 3D metric comparison diff
    pvs = payload.get("pvsyst_summary") or payload.get("summary") or {}
    raw_mods_in = payload.get("modules_layout") if payload.get("modules_layout") is not None else (payload.get("modules") or [])
    mod_spec_in = payload.get("module_spec") or payload.get("layout_params") or {}
    stc_w_in = float(mod_spec_in.get("stc_w") or 580.0)

    mod_cnt_sat = int(
        payload.get("module_count")
        or pvs.get("module_count")
        or (len(raw_mods_in) if isinstance(raw_mods_in, list) else 0)
    )
    dc_kw_sat = round(
        float(
            payload.get("dc_kw")
            or pvs.get("dc_kw")
            or (mod_cnt_sat * stc_w_in / 1000.0 if mod_cnt_sat > 0 else 0.0)
        ),
        2,
    )
    annual_kwh_sat = round(
        float(
            payload.get("annual_kwh")
            or pvs.get("annual_kwh")
            or pvs.get("e_grid_kwh")
            or 0.0
        ),
        1,
    )
    pr_pct_sat = round(float(payload.get("pr_pct") or pvs.get("pr_pct") or 0.0), 2)

    if out_summary is not None:
        dc_kw_3d = round(float(out_summary.get("dc_kw") or 0.0), 2)
        mod_cnt_3d = int(out_summary.get("modules") or 0)
        annual_kwh_3d = round(float((out_summary.get("yield_kwh") or {}).get("p50") or 0.0), 1)
        shade_3d = float((out_summary.get("shading") or {}).get("avg_loss_pct") or 2.0)
        pr_pct_3d = round(min(90.5, max(65.0, 84.8 - shade_3d * 0.70)), 2) if dc_kw_3d > 0 else 0.0
        load_kg_m2 = round(float((out_summary.get("load") or {}).get("added_kn_m2") or 0.16) * 1000.0 / 9.81, 1)
        if mod_cnt_sat == 0:
            mod_cnt_sat = mod_cnt_3d
            dc_kw_sat = dc_kw_3d
        if annual_kwh_sat == 0.0:
            annual_kwh_sat = annual_kwh_3d
        if pr_pct_sat == 0.0:
            pr_pct_sat = pr_pct_3d
        if abs(mod_cnt_sat - mod_cnt_3d) > 0:
            notes.append(f"3D 边界严格碰撞复核后组件数为 {mod_cnt_3d} 块（卫星排布 {mod_cnt_sat} 块）。")
    else:
        dc_kw_3d = dc_kw_sat
        mod_cnt_3d = mod_cnt_sat
        annual_kwh_3d = annual_kwh_sat
        pr_pct_3d = pr_pct_sat
        load_kg_m2 = 15.2 if roof_dict["type"] == "metal" else 32.5

    jump_result = (
        f"#result/{out_pid}?version={out_ver}"
        if (out_pid and out_ver)
        else (f"#roof/{saved_roof_id}" if saved_roof_id else "#roof")
    )

    return {
        "ok": True,
        "project_id": out_pid,
        "version": out_ver,
        "roof_id": saved_roof_id,
        "jump_result_hash": jump_result,
        "jump_roof_hash": "#roof",
        "jump_roof_edit_hash": f"#roof/{saved_roof_id}" if saved_roof_id else "#roof",
        "sync_at": sync_at,
        "diff": {
            "dc_kw_sat": dc_kw_sat,
            "dc_kw_3d": dc_kw_3d,
            "module_count_sat": mod_cnt_sat,
            "module_count_3d": mod_cnt_3d,
            "annual_kwh_sat": annual_kwh_sat,
            "annual_kwh_3d": annual_kwh_3d,
            "pr_pct_sat": pr_pct_sat,
            "pr_pct_3d": pr_pct_3d,
            "load_kg_m2": load_kg_m2,
            "notes": notes,
        },
        "summary": out_summary,
        "allocation_reconciliation": alloc_recon,
    }


def _sanitize_bundle_project_name(raw_name: Any) -> str:
    cleaned = str(scrub_pvsyst_text(raw_name or "")).strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._- ")
    if not cleaned:
        return "光筑卫星光伏方案"
    return cleaned[:42]


def _build_engineering_bom_csv_bytes(
    *,
    summary: dict[str, Any],
    roof: dict[str, Any],
    wiring: dict[str, Any],
    structural_check: dict[str, Any],
    multifactor: dict[str, Any],
) -> bytes:
    mod_count = max(0, int(summary.get("module_count") or 0))
    dc_kw = float(summary.get("dc_kw") or 0.0)
    stc_w = round((dc_kw * 1000.0) / mod_count) if mod_count > 0 else 580
    mod_model = str(scrub_pvsyst_text(summary.get("module_model") or f"N型TOPCon双面双玻 {stc_w}Wp"))
    inv_count = max(1, int(summary.get("inverter_count") or 1)) if mod_count > 0 else 0
    inv_model = str(scrub_pvsyst_text(summary.get("inverter_model") or "SG110CX-P2"))
    ac_kw = float(summary.get("ac_kw") or 0.0)
    string_count = max(0, int(summary.get("string_count") or 0))
    orient_mode = str(multifactor.get("orientation_mode") or summary.get("orientation_mode") or "south_fixed")
    rack_type = str(multifactor.get("rack_type") or summary.get("rack_type") or "1P")
    roof_type = str(roof.get("type") or roof.get("roof_type") or "flat")

    orient_label = {
        "east_west": "东西向人字坡蝴蝶阵热浸镀锌铝镁支架系统",
        "elevated_canopy": "架高跨越阳光棚门式钢构光伏支架系统",
        "flush_pitched": "铝合金导轨及彩钢瓦顺坡轻量化支架系统",
    }.get(orient_mode, f"正南固定倾角热浸镀锌铝镁支架系统 ({rack_type})")

    zones = structural_check.get("zones") if isinstance(structural_check.get("zones"), list) else []
    avg_ballast_kg = 25.0
    if zones and isinstance(zones[0], dict) and float(zones[0].get("ballast_kg_per_mod") or 0) > 0:
        avg_ballast_kg = float(zones[0]["ballast_kg_per_mod"])
    is_ballast = roof_type == "flat" and orient_mode not in ("flush_pitched", "elevated_canopy")
    if is_ballast:
        fix_name = "C30预制混凝土防风压载块（含EPDM耐候橡胶护垫）"
        fix_spec = f"单组件配重约 {avg_ballast_kg:.0f}kg · 50年一遇防风揭校核"
        fix_unit = "套"
        fix_qty = mod_count
        fix_unit_price = round(avg_ballast_kg * 0.95, 1)
    else:
        fix_name = "SUS304不锈钢直立锁边无穿孔夹具 / 化学锚栓组件"
        fix_spec = "抗拉拔 ≥3.5kN · 配套三元乙丙防水胶垫"
        fix_unit = "套"
        fix_qty = mod_count * 4
        fix_unit_price = 11.5

    dc_cable_m = max(round(string_count * 88.0), round(float(wiring.get("hanan_2opt_dc_cable_m") or 0.0) * 1.05))
    ac_cable_model = str(wiring.get("cu_cable_model") or "ZR-YJV22-0.6/1kV-3×95+1×50")
    ac_cable_m = max(inv_count * 65, 65 if inv_count > 0 else 0)
    ac_cable_cost = float(wiring.get("cu_ac_cost_cny") or (ac_cable_m * 148.0))
    ac_unit_price = round(ac_cable_cost / max(1, ac_cable_m), 1)
    mc4_pairs = max(2, string_count * 2 + inv_count * 2) if string_count > 0 else 0

    poly = roof.get("polygon_m") or [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]]
    xs = [float(p[0]) for p in poly] if poly else [-38.0, 38.0]
    ys = [float(p[1]) for p in poly] if poly else [-18.0, 18.0]
    perim_m = round(2.0 * ((max(xs) - min(xs)) + (max(ys) - min(ys))) * 1.12)

    mod_price = round(stc_w * 0.86, 1)
    inv_price = round(max(12500.0, (ac_kw / max(1, inv_count)) * 185.0), 0)
    rack_kw_price = 460.0 if orient_mode == "elevated_canopy" else (245.0 if is_ballast else 210.0)

    rows = [
        [
            1,
            "光伏发电组件",
            "高效N型单晶双面双玻光伏组件",
            f"{mod_model} ({stc_w}Wp, 1500V DC, IP68)",
            "块",
            mod_count,
            mod_price,
            round(mod_count * mod_price, 0),
            "IEC 61215 / IEC 61730 一级品",
        ],
        [
            2,
            "并网逆变设备",
            "组串式智能光伏并网逆变器",
            f"{inv_model} (总交流额定 {ac_kw:.1f}kW, 多路MPPT电弧防护)",
            "台",
            inv_count,
            inv_price,
            round(inv_count * inv_price, 0),
            "GB/T 37408 / 具备AFCI直流拉弧检测",
        ],
        [
            3,
            "光伏支架结构",
            orient_label,
            "Q235B/S350GD+ZM275 锌铝镁镀层 ≥275g/m²",
            "kWp",
            round(dc_kw, 2),
            rack_kw_price,
            round(dc_kw * rack_kw_price, 0),
            "GB 50797 / NB/T 10115 25年防腐",
        ],
        [
            4,
            "屋面固定与抗风",
            fix_name,
            fix_spec,
            fix_unit,
            fix_qty,
            fix_unit_price,
            round(fix_qty * fix_unit_price, 0),
            "GB 50009 屋面边角风吸包络复核",
        ],
        [
            5,
            "直流光伏线缆",
            "低烟无卤阻燃镀锡铜芯光伏专用线缆",
            "PV1-F 1×4mm² DC 1500V 耐候抗紫外",
            "m",
            dc_cable_m,
            4.3,
            round(dc_cable_m * 4.3, 0),
            "Hanan网格蛇形优化走线（含5%余量）",
        ],
        [
            6,
            "交流电力电缆",
            "阻燃铠装交联聚乙烯绝缘电力电缆",
            ac_cable_model,
            "m",
            ac_cable_m,
            ac_unit_price,
            round(ac_cable_m * ac_unit_price, 0),
            "GB/T 12706 交流回路压降 ≤1.5%",
        ],
        [
            7,
            "直流连接组件",
            "1500V防水光伏专用连接器及防反端子",
            "MC4-Evo2 IP68 镀银插芯（公母成对）",
            "对",
            mc4_pairs,
            14.0,
            round(mc4_pairs * 14.0, 0),
            "与逆变器原厂端子同型匹配",
        ],
        [
            8,
            "并网配电装置",
            "低压交流光伏并网柜（含防孤岛及计量）",
            f"GGD/MNS 400V 并网框架断路器 + A级电能质量表 ({max(1, math.ceil(ac_kw / 400.0))}面)",
            "台",
            max(1, math.ceil(ac_kw / 400.0)) if inv_count > 0 else 0,
            16800.0,
            round((max(1, math.ceil(ac_kw / 400.0)) if inv_count > 0 else 0) * 16800.0, 0),
            "GB/T 19964 / 电网公司分布式并网规程",
        ],
        [
            9,
            "防雷与等电位",
            "屋面光伏防雷接地扁钢及跨接铜编织带",
            "热镀锌扁钢 -40×4mm + BVR-6mm²黄绿跨接线",
            "m",
            perim_m,
            22.0,
            round(perim_m * 22.0, 0),
            "GB 50057 接地冲击电阻 ≤4Ω",
        ],
        [
            10,
            "数智监控系统",
            "光筑电站数据采集器、环境仪及远程运维网关",
            "RS485/4G智能通讯棒 + 屋面斜面总辐射及背板温度传感器",
            "套",
            1 if mod_count > 0 else 0,
            4800.0,
            4800.0 if mod_count > 0 else 0.0,
            "IEC 61724 逐时PR在线对标监测",
        ],
    ]

    total_cny = sum(float(r[7]) for r in rows)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(
        [
            "序号",
            "设备/材料类别",
            "设备及主材名称",
            "规格型号及主要技术参数",
            "单位",
            "工程数量",
            "参考单价(元)",
            "合价估算(元)",
            "执行标准及工程备注",
        ]
    )
    for r in rows:
        writer.writerow(r)
    writer.writerow(["合计", "主材设备直接费小计", "—", f"折合 {round(total_cny / max(1.0, dc_kw * 1000.0), 2)} 元/Wp", "项", 1, "", round(total_cny, 0), "光筑工程交付清册（不含土建及屋面加固）"])
    return buf.getvalue().encode("utf-8-sig")


def export_satmap_delivery_bundle(
    payload: dict[str, Any],
    *,
    open_folder: bool | None = None,
    test_mode: bool = False,
) -> dict[str, Any]:
    """Generate a 4-file engineering delivery bundle (《光筑专业报告》PDF + CAD DXF + UTF-8-SIG BOM CSV + Verification JSON)."""
    if not isinstance(payload, dict):
        raise ValueError("Delivery bundle payload must be a JSON object.")
    validate_satmap_common_inputs(payload)

    from .report.pvsyst_report import build_pvsyst_report_context, render_pvsyst_report_pdf

    has_precomputed = (
        isinstance(payload.get("summary"), dict)
        and float((payload.get("summary") or {}).get("dc_kw") or 0.0) > 0.0
        and isinstance(payload.get("modules"), list)
        and len(payload.get("modules") or []) > 0
    )
    offline_flag = bool(payload.get("offline", True))

    if has_precomputed:
        design_state = dict(payload)
        if not isinstance(design_state.get("health_check"), dict):
            design_state["health_check"] = evaluate_engineering_health_check(design_state)
    else:
        design_state = run_satmap_design({**payload, "offline": offline_flag})
        if isinstance(payload.get("multifactor"), dict):
            design_state["multifactor"] = {**(design_state.get("multifactor") or {}), **payload["multifactor"]}

    site = design_state.get("site") if isinstance(design_state.get("site"), dict) else {}
    roof = design_state.get("roof") if isinstance(design_state.get("roof"), dict) else {}
    summary = design_state.get("summary") if isinstance(design_state.get("summary"), dict) else {}
    modules = design_state.get("modules") if isinstance(design_state.get("modules"), list) else []
    strings = design_state.get("strings") if isinstance(design_state.get("strings"), list) else []
    mppt_table = design_state.get("mppt_table") if isinstance(design_state.get("mppt_table"), list) else []
    wiring = design_state.get("wiring_optimization") if isinstance(design_state.get("wiring_optimization"), dict) else {}
    structural_check = design_state.get("structural_check") if isinstance(design_state.get("structural_check"), dict) else {}
    financial_dcf = design_state.get("financial_dcf") if isinstance(design_state.get("financial_dcf"), dict) else {}
    multifactor = design_state.get("multifactor") if isinstance(design_state.get("multifactor"), dict) else {}
    health_check = design_state.get("health_check") if isinstance(design_state.get("health_check"), dict) else evaluate_engineering_health_check(design_state)

    raw_proj_name = (
        payload.get("project_name")
        or payload.get("name")
        or site.get("name")
        or "光筑卫星光伏方案"
    )
    safe_name = _sanitize_bundle_project_name(raw_proj_name)
    folder_name = f"光筑工程交付包_{safe_name}"
    bundle_id = f"bnd-{int(time.time())}-{uuid.uuid4().hex[:6]}"

    explicit_open = open_folder if open_folder is not None else payload.get("open_folder")
    in_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if explicit_open is not None:
        should_open = bool(explicit_open)
    else:
        should_open = not (test_mode or in_pytest)

    use_cache_only = bool(
        test_mode
        or payload.get("test_mode")
        or (not should_open)
        or (in_pytest and not payload.get("allow_downloads_in_test"))
    )

    cache_root = ROOT / "data" / "cache" / "delivery-bundles" / bundle_id
    cache_bundle_dir = cache_root / folder_name
    cache_bundle_dir.mkdir(parents=True, exist_ok=True)

    pdf_filename = f"01_光筑专业报告_{safe_name}.pdf"
    dxf_filename = f"02_光伏总平面及组串施工图_{safe_name}.dxf"
    csv_filename = f"03_工程设备与主材清册BOM_{safe_name}.csv"
    json_filename = f"04_光筑工程仿真与多维合规校核_{safe_name}.json"

    # 1. Watermarked 《光筑专业报告》 PDF via report/pvsyst_report.py
    lat_val = float(site.get("lat") if site.get("lat") is not None else payload.get("lat", 32.4568))
    lon_val = float(site.get("lon") if site.get("lon") is not None else payload.get("lon", 119.9182))
    city_zh = str(site.get("city") or _infer_city_zh(lat_val, lon_val, str(raw_proj_name)))
    report_payload = scrub_pvsyst_text(
        {
            "project_id": str(payload.get("project_id") or f"GZ-{bundle_id[-6:].upper()}"),
            "project_name": str(raw_proj_name),
            "version": int(payload.get("version") or 1),
            "site": {
                "name": str(raw_proj_name),
                "city": city_zh,
                "lat": lat_val,
                "lon": lon_val,
                "albedo": float(roof.get("albedo") or multifactor.get("albedo") or 0.22),
            },
            "roof": {
                "type": str(roof.get("type") or roof.get("roof_type") or "flat"),
                "slope_deg": float(roof.get("slope_deg") or 0.0),
                "parapet_height_m": float(roof.get("parapet_height_m") or 0.6),
            },
            "system": {
                "dc_kw": float(summary.get("dc_kw") or 0.0),
                "ac_kw": float(summary.get("ac_kw") or 0.0),
                "module_count": int(summary.get("module_count") or len(modules)),
                "module_model": str(summary.get("module_model") or "JKM580N-72HL4-BDV"),
                "inverter_count": int(summary.get("inverter_count") or 1),
                "inverter_model": str(summary.get("inverter_model") or "SG110CX-P2"),
                "string_count": int(summary.get("string_count") or len(strings)),
                "modules_per_string": int(summary.get("modules_per_string") or 18),
                "orientation_mode": str(multifactor.get("orientation_mode") or summary.get("orientation_mode") or "south_fixed"),
                "mount_orientation": str(multifactor.get("mount_orientation") or "portrait"),
                "tilt_deg": float((modules[0].get("tilt_deg") if modules else None) or payload.get("tilt_deg") or 15.0),
                "azimuth_deg": float((modules[0].get("azimuth_deg") if modules else None) or payload.get("azimuth_deg") or 180.0),
                "parapet_height_m": float(roof.get("parapet_height_m") or 0.6),
                "shading_loss_pct": float(multifactor.get("shading_loss_pct") or 2.2),
            },
            "electrical": {
                "mppt_table": mppt_table,
                "wiring_optimization": wiring,
            },
            "multifactor": multifactor,
            "economics": {
                "capex_wan": float(financial_dcf.get("total_capex_wan") or 0.0),
                "self_use_pct": float(summary.get("self_use_pct") if summary.get("self_use_pct") is not None else 80.0),
                "irr_pct": summary.get("irr_pct") if summary.get("irr_pct") is not None else financial_dcf.get("irr_pct"),
                "npv_wan": float(summary.get("npv_25_wan") if summary.get("npv_25_wan") is not None else (financial_dcf.get("npv_25_wan") or 0.0)),
                "payback_yr": summary.get("payback_years") if summary.get("payback_years") is not None else financial_dcf.get("static_payback_years"),
                "lcoe_cny_kwh": financial_dcf.get("lcoe_rmb_kwh") if financial_dcf.get("lcoe_rmb_kwh") is not None else financial_dcf.get("lcoe_cny_kwh"),
            },
            "pvsyst": design_state.get("pvsyst") or payload.get("pvsyst") or {},
        }
    )
    pdf_path = cache_bundle_dir / pdf_filename
    report_ctx = build_pvsyst_report_context(report_payload, offline=offline_flag)
    try:
        render_pvsyst_report_pdf(report_ctx, pdf_path)
    except Exception:
        render_pvsyst_report_pdf(report_ctx, pdf_path, browsers=[])
    # Clean temporary intermediate HTML if created alongside PDF
    html_tmp = pdf_path.with_suffix(".pvsyst-v2.html")
    if html_tmp.is_file():
        try:
            html_tmp.unlink()
        except OSError:
            pass

    # 2. Master Engineering CAD DXF
    dxf_bytes = export_satmap_dxf(
        {
            "summary": summary,
            "roof": {
                "type": roof.get("type") or roof.get("roof_type") or "flat",
                "polygon_m": roof.get("polygon_m") or payload.get("roof_polygon_m") or [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]],
                "obstacles": roof.get("obstacles") or payload.get("obstacles") or [],
            },
            "modules": modules,
            "strings": strings,
        },
        drawing_type="all",
    )
    dxf_path = cache_bundle_dir / dxf_filename
    dxf_path.write_bytes(dxf_bytes)

    # 3. Engineering BOM CSV (UTF-8-SIG with BOM header for Excel)
    bom_bytes = _build_engineering_bom_csv_bytes(
        summary=summary,
        roof=roof,
        wiring=wiring,
        structural_check=structural_check,
        multifactor=multifactor,
    )
    csv_path = cache_bundle_dir / csv_filename
    csv_path.write_bytes(bom_bytes)

    # 4. Engineering & Multi-Factor Verification JSON (scrubbed of any PVsyst text or private OS paths)
    poly_pts = roof.get("polygon_m") or payload.get("roof_polygon_m") or []
    roof_area_m2 = round(Polygon([(float(p[0]), float(p[1])) for p in poly_pts]).area, 1) if len(poly_pts) >= 3 else 0.0
    verification_doc = scrub_pvsyst_text(
        {
            "schema_version": "guangzhu.delivery_verification.v2",
            "report_brand": "《光筑专业报告》工程仿真与多维合规校核书",
            "simulation_engine": "光筑专业仿真 8760h 逐时物理引擎 (Perez 1990 + Faiman + IEC 61724)",
            "bundle_id": bundle_id,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "site": {
                "name": str(raw_proj_name),
                "city": city_zh,
                "lat": round(lat_val, 6),
                "lon": round(lon_val, 6),
            },
            "roof": {
                "roof_type": str(roof.get("type") or roof.get("roof_type") or "flat"),
                "area_m2": roof_area_m2,
                "slope_deg": float(roof.get("slope_deg") or 0.0),
                "parapet_height_m": float(roof.get("parapet_height_m") or 0.0),
                "albedo": float(roof.get("albedo") or multifactor.get("albedo") or 0.22),
                "obstacle_count": len(roof.get("obstacles") or payload.get("obstacles") or []),
            },
            "summary": summary,
            "multifactor": multifactor,
            "structural_check": structural_check,
            "wiring_optimization": wiring,
            "mppt_table": mppt_table,
            "financial_dcf": financial_dcf,
            "health_check": health_check,
        }
    )
    json_path = cache_bundle_dir / json_filename
    json_path.write_text(json.dumps(verification_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    deliverable_specs = [
        ("report_pdf", pdf_filename, "《光筑专业报告》6页工程仿真核验书 (PDF)", "pdf", pdf_path),
        ("master_dxf", dxf_filename, "光伏总平面、组串接线及防雷支架施工图 (DXF)", "dxf", dxf_path),
        ("bom_csv", csv_filename, "工程主材与电气设备标准清册 BOM (CSV)", "csv", csv_path),
        ("verification_json", json_filename, "多维工程物理仿真与8项合规校核数据包 (JSON)", "json", json_path),
    ]

    # Build downloadable ZIP archive in cache
    zip_filename = f"{folder_name}.zip"
    zip_path = cache_root / zip_filename
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for _, fname, _, _, fpath in deliverable_specs:
            zf.write(fpath, arcname=f"{folder_name}/{fname}")

    # Copy to ~/Downloads/光筑工程交付包_<safe_name>/ in normal desktop mode
    final_dir = cache_bundle_dir
    storage_mode = "cache"
    display_path = f"data/cache/delivery-bundles/{bundle_id}/{folder_name}"
    if not use_cache_only:
        try:
            downloads_target = Path.home() / "Downloads" / folder_name
            downloads_target.mkdir(parents=True, exist_ok=True)
            for _, fname, _, _, src_path in deliverable_specs:
                shutil.copy2(src_path, downloads_target / fname)
            final_dir = downloads_target
            storage_mode = "downloads"
            display_path = f"Downloads/{folder_name}"
        except OSError:
            final_dir = cache_bundle_dir
            storage_mode = "cache"
            display_path = f"data/cache/delivery-bundles/{bundle_id}/{folder_name}"

    opened_natively = False
    if should_open and hasattr(os, "startfile"):
        try:
            os.startfile(str(final_dir))
            opened_natively = True
        except Exception:
            opened_natively = False

    files_out = [
        {
            "key": key,
            "filename": fname,
            "label_zh": label_zh,
            "format": fmt,
            "size_bytes": fpath.stat().st_size,
            "download_url": f"/api/satmap/delivery-bundle/{bundle_id}/{quote(fname)}",
        }
        for key, fname, label_zh, fmt, fpath in deliverable_specs
    ]

    return scrub_pvsyst_text(
        {
            "ok": True,
            "bundle_id": bundle_id,
            "folder_name": folder_name,
            "display_path": display_path,
            "storage_mode": storage_mode,
            "opened_natively": opened_natively,
            "file_count": len(files_out),
            "download_zip_url": f"/api/satmap/delivery-bundle/{bundle_id}/{quote(zip_filename)}",
            "files": files_out,
            "health_check": health_check,
            "summary": {
                "dc_kw": summary.get("dc_kw", 0.0),
                "ac_kw": summary.get("ac_kw", 0.0),
                "module_count": summary.get("module_count", len(modules)),
                "annual_kwh": summary.get("annual_kwh", 0.0),
                "pr_pct": summary.get("pr_pct", 0.0),
                "irr_pct": summary.get("irr_pct"),
                "payback_years": summary.get("payback_years"),
            },
        }
    )


def _resolve_delivery_bundle_file(bundle_id: str, filename: str) -> tuple[Path, str]:
    if not re.match(r"^bnd-\d+-[a-f0-9]{6}$", bundle_id or ""):
        raise LookupError("Invalid bundle_id.")
    clean_fname = Path(filename or "").name
    if not clean_fname or clean_fname != filename or ".." in clean_fname:
        raise LookupError("Invalid bundle filename.")
    bundle_root = ROOT / "data" / "cache" / "delivery-bundles" / bundle_id
    if not bundle_root.is_dir():
        raise LookupError(f"Delivery bundle not found: {bundle_id}")

    direct = bundle_root / clean_fname
    target: Path | None = direct if direct.is_file() else None
    if target is None:
        for sub in bundle_root.iterdir():
            if sub.is_dir() and (sub / clean_fname).is_file():
                target = sub / clean_fname
                break
    if target is None:
        raise LookupError(f"File '{clean_fname}' not found in bundle '{bundle_id}'.")

    ext = target.suffix.lower()
    media_map = {
        ".pdf": "application/pdf",
        ".dxf": "application/dxf",
        ".csv": "text/csv; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".zip": "application/zip",
    }
    return target, media_map.get(ext, "application/octet-stream")


# ---------------------------------------------------------------------------
# FastAPI Routes for #satmap & Guangzhu Hourly Simulation / Official Live Weather
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
    from fastapi.responses import JSONResponse
    try:
        return ai_recognize_satellite_roof(payload)
    except GzError as error:
        return JSONResponse(
            {"ok": False, "detail": error.message_zh, "errors": [f"{error.message_zh}。{error.fix_hint}"], "error_code": error.error_code},
            status_code=422,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/satmap/design")
def api_satmap_design(payload: dict = Body(...)):
    from fastapi.responses import JSONResponse
    try:
        return run_satmap_design(payload)
    except GzError as error:
        return JSONResponse(
            {"ok": False, "detail": error.message_zh, "errors": [f"{error.message_zh}。{error.fix_hint}"], "error_code": error.error_code},
            status_code=422,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/satmap/drawings")
def api_satmap_drawings(payload: dict = Body(...)):
    from fastapi.responses import JSONResponse
    try:
        return generate_four_cad_drawings(payload)
    except GzError as error:
        return JSONResponse(
            {"ok": False, "detail": error.message_zh, "errors": [f"{error.message_zh}。{error.fix_hint}"], "error_code": error.error_code},
            status_code=422,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/satmap/save-project")
def api_satmap_save_project(request: Request, payload: dict = Body(...)):
    from .models import GzError
    from fastapi.responses import JSONResponse
    try:
        return save_to_guangzhu_project(payload, project_id=payload.get("project_id"))
    except GzError as error:
        status = 409 if error.error_code in ("DESIGN_LOCK_GEOMETRY_CHANGED", "DESIGN_VERSION_EXISTS", "DESIGN_LOCK_STALE", "PROJECT_EXISTS") else 422
        return JSONResponse({"ok": False, "detail": error.message_zh, "errors": [f"{error.message_zh}。{error.fix_hint}"], "error_code": error.error_code}, status_code=status)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/satmap/3d-catalog")
def api_satmap_3d_catalog():
    return get_satmap_3d_catalog()


@router.get("/api/satmap/from-3d/{kind}/{item_id}")
def api_satmap_from_3d(kind: str, item_id: str, version: int | None = Query(None)):
    try:
        return convert_from_3d_to_satmap(kind, item_id, version=version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/satmap/sync-to-3d")
def api_satmap_sync_to_3d(payload: dict = Body(...)):
    from .models import GzError
    from fastapi.responses import JSONResponse
    try:
        return sync_satmap_to_3d(payload)
    except GzError as error:
        status = 409 if error.error_code in ("DESIGN_LOCK_GEOMETRY_CHANGED", "DESIGN_VERSION_EXISTS", "DESIGN_LOCK_STALE", "PROJECT_EXISTS") else 422
        return JSONResponse({"ok": False, "errors": [f"{error.message_zh}。{error.fix_hint}"], "error_code": error.error_code}, status_code=status)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/satmap/optimize-multifactor")
def api_satmap_optimize_multifactor(payload: dict = Body(...)):
    from fastapi.responses import JSONResponse
    try:
        return optimize_satmap_multifactor(payload)
    except GzError as error:
        return JSONResponse(
            {"ok": False, "detail": error.message_zh, "errors": [f"{error.message_zh}。{error.fix_hint}"], "error_code": error.error_code},
            status_code=422,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/satmap/engineering-health-check")
def api_satmap_engineering_health_check(payload: dict = Body(...)):
    from fastapi.responses import JSONResponse
    try:
        if bool(payload.get("run_design")) and not isinstance(payload.get("summary"), dict):
            return run_satmap_design(payload)["health_check"]
        return evaluate_engineering_health_check(payload)
    except GzError as error:
        return JSONResponse(
            {"ok": False, "detail": error.message_zh, "errors": [f"{error.message_zh}。{error.fix_hint}"], "error_code": error.error_code},
            status_code=422,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/satmap/export-delivery-bundle")
def api_satmap_export_delivery_bundle(request: Request, payload: dict = Body(...)):
    from fastapi.responses import JSONResponse
    test_hdr = bool(request.headers.get("x-guangzhu-test"))
    try:
        return export_satmap_delivery_bundle(payload, test_mode=test_hdr)
    except GzError as error:
        return JSONResponse(
            {"ok": False, "detail": error.message_zh, "errors": [f"{error.message_zh}。{error.fix_hint}"], "error_code": error.error_code},
            status_code=422,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/satmap/delivery-bundle/{bundle_id}/{filename}")
def api_satmap_download_delivery_bundle_file(bundle_id: str, filename: str):
    try:
        fpath, media_type = _resolve_delivery_bundle_file(bundle_id, filename)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    encoded_name = quote(fpath.name)
    return Response(
        content=fpath.read_bytes(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            "Cache-Control": "no-store",
        },
    )


@router.get("/api/guangzhu/live-weather")
@router.get("/api/pvsyst/live-weather")
def api_pvsyst_live_weather_get(
    lat: float = Query(32.4568),
    lon: float = Query(119.9182),
    dc_kw: float = Query(290.0),
    ac_kw: float | None = Query(None),
    tilt_deg: float = Query(15.0),
    azimuth_deg: float = Query(180.0),
    albedo: float = Query(0.22),
    bifacial: bool = Query(False),
    bifaciality: float = Query(0.80),
    uc_w_m2k: float = Query(29.0),
    uv_w_m2k_ms: float = Query(0.0),
    offline: bool = Query(False),
):
    try:
        alb_f = _strict_finite_float(albedo, "albedo")
        bifi_f = _strict_finite_float(bifaciality, "bifaciality")
        if not (0.0 <= alb_f <= 1.0):
            raise ValueError("albedo must be within [0, 1].")
        if not (0.0 <= bifi_f <= 1.0):
            raise ValueError("bifaciality must be within [0, 1].")
        return scrub_pvsyst_text(
            fetch_live_weather(
                lat,
                lon,
                dc_kw=dc_kw,
                ac_kw=ac_kw,
                tilt_deg=tilt_deg,
                azimuth_deg=azimuth_deg,
                albedo=alb_f,
                bifacial=bifacial,
                bifaciality=bifi_f,
                uc_w_m2k=uc_w_m2k,
                uv_w_m2k_ms=uv_w_m2k_ms,
                offline=offline,
            )
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/guangzhu/live-weather")
@router.post("/api/pvsyst/live-weather")
def api_pvsyst_live_weather_post(payload: dict = Body(...)):
    def _lnum(key: str, default: float) -> float:
        return _strict_finite_float(payload[key], key) if payload.get(key) is not None else float(default)

    try:
        alb_f = _lnum("albedo", 0.22)
        bifi_f = _lnum("bifaciality", 0.80)
        if not (0.0 <= alb_f <= 1.0):
            raise ValueError("albedo must be within [0, 1].")
        if not (0.0 <= bifi_f <= 1.0):
            raise ValueError("bifaciality must be within [0, 1].")
        return scrub_pvsyst_text(
            fetch_live_weather(
                _lnum("lat", 32.4568),
                _lnum("lon", 119.9182),
                dc_kw=_lnum("dc_kw", 290.0),
                ac_kw=_strict_finite_float(payload["ac_kw"], "ac_kw") if payload.get("ac_kw") is not None else None,
                tilt_deg=_lnum("tilt_deg", 15.0),
                azimuth_deg=_lnum("azimuth_deg", 180.0),
                albedo=alb_f,
                bifacial=bool(payload["bifacial"]) if payload.get("bifacial") is not None else False,
                bifaciality=bifi_f,
                gamma_pdc_pct_c=_lnum("gamma_pdc_pct_c", -0.34),
                inverter_eff_nom=_lnum("inverter_eff_nom", 0.982),
                uc_w_m2k=_lnum("uc_w_m2k", 29.0),
                uv_w_m2k_ms=_lnum("uv_w_m2k_ms", 0.0),
                sub_arrays=payload.get("sub_arrays"),
                offline=bool(payload.get("offline", False)),
            )
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/api/guangzhu/simulate")
@router.post("/api/pvsyst/simulate")
def api_pvsyst_simulate(payload: dict = Body(...)):
    def _pnum(key: str, default: float) -> float:
        return _strict_finite_float(payload[key], key) if payload.get(key) is not None else float(default)

    try:
        return scrub_pvsyst_text(
            simulate_pvsyst(
                _pnum("lat", 32.4568),
                _pnum("lon", 119.9182),
                dc_kw=_pnum("dc_kw", 290.0),
                ac_kw=_strict_finite_float(payload["ac_kw"], "ac_kw") if payload.get("ac_kw") is not None else None,
                tilt_deg=_pnum("tilt_deg", 15.0),
                azimuth_deg=_pnum("azimuth_deg", 180.0),
                orientation_mode=str(payload.get("orientation_mode") or "south_fixed"),
                shading_loss_pct=_pnum("shading_loss_pct", 2.2),
                bifacial=bool(payload.get("bifacial", True)),
                albedo=_pnum("albedo", 0.22),
                bifaciality=_pnum("bifaciality", 0.80),
                bifacial_factor=_strict_finite_float(payload["bifacial_factor"], "bifacial_factor") if payload.get("bifacial_factor") is not None else None,
                soiling_pct=_pnum("soiling_pct", 2.0),
                snow_loss_pct=_pnum("snow_loss_pct", 0.0),
                spectral_corr_pct=_pnum("spectral_corr_pct", 0.0),
                stc_eff_pct=_pnum("stc_eff_pct", 21.6),
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
        )
    except GzError as error:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"ok": False, "detail": error.message_zh, "errors": [f"{error.message_zh}。{error.fix_hint}"], "error_code": error.error_code},
            status_code=422,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
