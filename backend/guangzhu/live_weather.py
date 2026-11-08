"""Official real-time & 7-day forecast meteorological and solar irradiance feed.

Retrieves live and 168-hour forecast weather + solar radiation (GHI, DNI, DHI,
2m temperature, relative humidity, cloud cover, 10m wind speed & direction, WMO
weather code) from the Open-Meteo Official Global Meteorological API
(aggregating CMA / ECMWF IFS / GFS / DWD numerical weather prediction models),
computes plane-of-array (POA) irradiance, Faiman cell temperature, and live PV
array output, caches responses on disk with a 30-minute TTL, and falls back
deterministically to cached or TMY-derived profiles when offline.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
import time
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pvlib
import requests

from .config import DATA_DIR
from . import weather as tmy_weather

LIVE_CACHE_DIR = DATA_DIR / "cache" / "live_weather"
LIVE_TTL_SECONDS = 1800  # 30 minutes
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

WMO_WEATHER_LABELS_ZH: dict[int, str] = {
    0: "晴朗少云",
    1: "晴间少云",
    2: "多云间晴",
    3: "阴天",
    45: "有雾",
    48: "雾凇/轻雾",
    51: "零星毛毛雨",
    53: "毛毛雨",
    55: "浓密毛毛雨",
    56: "冻毛毛雨",
    57: "强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "轻微冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "米雪",
    80: "阵雨",
    81: "中阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷阵雨",
    96: "雷阵雨伴冰雹",
    99: "强雷暴伴冰雹",
}


def wmo_code_to_zh(code: int | float | None) -> str:
    """Map WMO synoptic weather code to concise Chinese meteorological label."""
    if code is None or not math.isfinite(float(code)):
        return "多云间晴"
    c = int(round(float(code)))
    if c in WMO_WEATHER_LABELS_ZH:
        return WMO_WEATHER_LABELS_ZH[c]
    if c < 2:
        return "晴朗少云"
    if c <= 4:
        return "多云间晴"
    if c < 50:
        return "薄雾"
    if c < 60:
        return "毛毛雨"
    if c < 70:
        return "小雨"
    if c < 80:
        return "降雪"
    if c < 90:
        return "阵雨"
    return "雷阵雨"


def _validate_coords(lat: float, lon: float) -> tuple[float, float]:
    lat_f, lon_f = float(lat), float(lon)
    if not math.isfinite(lat_f) or not -90.0 <= lat_f <= 90.0:
        raise ValueError("Latitude must be finite and within [-90, 90].")
    if not math.isfinite(lon_f) or not -180.0 <= lon_f <= 180.0:
        raise ValueError("Longitude must be finite and within [-180, 180].")
    return lat_f, lon_f


def _cache_file_for(lat: float, lon: float):
    LIVE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return LIVE_CACHE_DIR / f"live_{lat:.3f}_{lon:.3f}.json"


def _read_cached_payload(lat: float, lon: float, *, ignore_ttl: bool = False) -> dict[str, Any] | None:
    path = _cache_file_for(lat, lon)
    if not path.is_file():
        return None
    try:
        age = time.time() - path.stat().st_mtime
        if not ignore_ttl and age > LIVE_TTL_SECONDS:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "hourly" not in data or "current" not in data:
            return None
        return data
    except (OSError, ValueError, TypeError):
        return None


def _write_cached_payload(lat: float, lon: float, payload: dict[str, Any]) -> None:
    path = _cache_file_for(lat, lon)
    try:
        data = dict(payload)
        data["_cached_at_iso"] = datetime.now(timezone.utc).isoformat()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _compute_poa_and_power_series(
    times_local: pd.DatetimeIndex,
    lat: float,
    lon: float,
    ghi: np.ndarray,
    dni: np.ndarray,
    dhi: np.ndarray,
    temp_c: np.ndarray,
    wind_ms: np.ndarray,
    *,
    dc_kw: float,
    tilt_deg: float,
    azimuth_deg: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute hourly/instantaneous POA (W/m2), Faiman cell temp (°C), and AC power (kW)."""
    ghi = np.clip(np.nan_to_num(np.asarray(ghi, dtype=float), nan=0.0), 0.0, 1450.0)
    dni = np.clip(np.nan_to_num(np.asarray(dni, dtype=float), nan=0.0), 0.0, 1350.0)
    dhi = np.clip(np.nan_to_num(np.asarray(dhi, dtype=float), nan=0.0), 0.0, 1000.0)
    temp_c = np.nan_to_num(np.asarray(temp_c, dtype=float), nan=20.0)
    wind_ms = np.clip(np.nan_to_num(np.asarray(wind_ms, dtype=float), nan=1.8), 0.1, 45.0)

    solar = pvlib.solarposition.get_solarposition(times_local, latitude=lat, longitude=lon)
    zenith = solar["apparent_zenith"].to_numpy(dtype=float)
    s_azimuth = solar["azimuth"].to_numpy(dtype=float)

    dni_extra = pvlib.irradiance.get_extra_radiation(times_local).to_numpy(dtype=float)
    airmass = np.nan_to_num(pvlib.atmosphere.get_relative_airmass(zenith), nan=1.5)

    irrad = pvlib.irradiance.get_total_irradiance(
        surface_tilt=float(tilt_deg),
        surface_azimuth=float(azimuth_deg),
        solar_zenith=zenith,
        solar_azimuth=s_azimuth,
        ghi=ghi,
        dni=dni,
        dhi=dhi,
        dni_extra=dni_extra,
        airmass=airmass,
        albedo=0.22,
        model="isotropic",
    )
    poa = np.nan_to_num(np.asarray(irrad["poa_global"], dtype=float), nan=0.0)
    poa = np.where((ghi <= 0.0) | (zenith >= 91.5), 0.0, np.clip(poa, 0.0, 1500.0))

    # Faiman cell temperature model: T_cell = T_amb + alpha * POA / (Uc + Uv * wind)
    t_cell = temp_c + (0.78 * poa) / (29.0 + 1.2 * wind_ms)

    # Instantaneous AC power model with IAM/soiling, temperature coefficient (-0.30%/°C),
    # bifacial/system factor, and inverter clipping at DC/AC = 1.20
    eff_poa = poa * 0.965 * 1.032  # net after IAM, soiling, and modest bifacial contribution
    temp_factor = np.clip(1.0 - 0.0030 * (t_cell - 25.0), 0.72, 1.12)
    dc_power_kw = float(dc_kw) * (eff_poa / 1000.0) * temp_factor * 0.965
    ac_unclipped_kw = dc_power_kw * 0.984
    ac_cap_kw = float(dc_kw) / 1.15
    ac_power_kw = np.clip(ac_unclipped_kw, 0.0, ac_cap_kw)
    ac_power_kw = np.where(poa < 3.0, 0.0, ac_power_kw)
    return poa, t_cell, ac_power_kw


def _synthesize_offline_payload(lat: float, lon: float) -> dict[str, Any]:
    """Synthesize a physically realistic 7-day hourly + current meteorological payload from TMY/clear-sky."""
    now_sh = datetime.now(SHANGHAI_TZ).replace(minute=0, second=0, microsecond=0)
    start_day = now_sh.replace(hour=0)
    hourly_index = pd.date_range(start=start_day, periods=168, freq="1h", tz=SHANGHAI_TZ)

    # Try loading local cached/demo PVGIS TMY first if available for exact site
    tmy_df = None
    try:
        tmy_df, _ = tmy_weather.load_pvgis_tmy(lat, lon, offline=True)
    except Exception:
        tmy_df = None

    rng = np.random.default_rng(abs(hash((round(lat, 3), round(lon, 3), start_day.timetuple().tm_yday))) % (2**32))

    if tmy_df is not None and len(tmy_df) >= 8760:
        # Map each hour in hourly_index to its corresponding hour-of-year in TMY (converted from UTC)
        tmy_sh = tmy_df.copy()
        tmy_sh.index = tmy_sh.index.tz_convert(SHANGHAI_TZ)
        lookup = {(ts.month, ts.day, ts.hour): row for ts, row in tmy_sh.iterrows()}
        ghi_list, dni_list, dhi_list, temp_list, wind_list, cloud_list, code_list, rh_list = (
            [], [], [], [], [], [], [], []
        )
        for ts in hourly_index:
            key = (ts.month, min(ts.day, 28) if ts.month == 2 else ts.day, ts.hour)
            row = lookup.get(key)
            if row is not None:
                g = float(max(0.0, row["ghi"]))
                dn = float(max(0.0, row["dni"]))
                dh = float(max(0.0, row["dhi"]))
                ta = float(row["temp_air"])
                ws = float(max(0.4, row["wind_speed"]))
            else:
                g, dn, dh, ta, ws = 0.0, 0.0, 0.0, 22.0, 2.2
            # Estimate cloud cover from clearness ratio
            cloud = float(np.clip((dh / max(g, 1.0)) * 75.0 if g > 25.0 else 25.0, 5.0, 95.0))
            w_code = 0 if cloud < 22 else (1 if cloud < 45 else (2 if cloud < 72 else 3))
            rh = float(np.clip(58.0 + 0.25 * cloud - 0.6 * (ta - 20.0), 30.0, 92.0))
            ghi_list.append(round(g, 1))
            dni_list.append(round(dn, 1))
            dhi_list.append(round(dh, 1))
            temp_list.append(round(ta, 1))
            wind_list.append(round(ws, 2))
            cloud_list.append(round(cloud, 0))
            code_list.append(int(w_code))
            rh_list.append(round(rh, 0))
    else:
        # Synthesize from pvlib clear-sky Ineichen model + latitude climatology
        loc = pvlib.location.Location(latitude=lat, longitude=lon, tz="Asia/Shanghai", altitude=50.0)
        cs = loc.get_clearsky(hourly_index + pd.Timedelta(minutes=30), model="ineichen")
        day_of_year = hourly_index.dayofyear.to_numpy(dtype=float)
        hour_of_day = hourly_index.hour.to_numpy(dtype=float)

        # Synoptic 7-day weather wave
        daily_clearness = np.array([0.88, 0.92, 0.76, 0.64, 0.84, 0.90, 0.81])
        hourly_clearness = np.repeat(daily_clearness, 24)
        cloud_cover = np.clip((1.0 - hourly_clearness) * 180.0 + rng.normal(0.0, 4.0, 168), 5.0, 95.0)

        ghi_arr = cs["ghi"].to_numpy(dtype=float) * hourly_clearness
        dhi_frac = np.clip(0.18 + 0.55 * (1.0 - hourly_clearness), 0.15, 0.85)
        dhi_arr = ghi_arr * dhi_frac
        solar = pvlib.solarposition.get_solarposition(hourly_index + pd.Timedelta(minutes=30), lat, lon)
        cos_z = np.maximum(np.cos(np.radians(solar["apparent_zenith"].to_numpy(dtype=float))), 0.06)
        dni_arr = np.where(ghi_arr > 5.0, np.clip((ghi_arr - dhi_arr) / cos_z, 0.0, 1050.0), 0.0)

        # Latitude & seasonal temperature profile
        mean_annual_temp = 24.5 - 0.42 * (abs(lat) - 20.0)
        seasonal_swing = 8.5 + 0.22 * max(0.0, abs(lat) - 20.0)
        seasonal_temp = mean_annual_temp + seasonal_swing * np.sin(2.0 * np.pi * (day_of_year - 105.0) / 365.0)
        diurnal_temp = -4.2 * np.cos(2.0 * np.pi * (hour_of_day - 4.0) / 24.0)
        temp_arr = seasonal_temp + diurnal_temp

        wind_arr = np.clip(2.1 + 1.1 * np.sin(2.0 * np.pi * (hour_of_day - 8.0) / 24.0), 0.8, 6.5)
        rh_arr = np.clip(62.0 - 1.4 * diurnal_temp + 0.18 * cloud_cover, 32.0, 92.0)
        code_arr = np.where(
            cloud_cover < 20.0, 0, np.where(cloud_cover < 45.0, 1, np.where(cloud_cover < 75.0, 2, 3))
        )

        ghi_list = np.round(ghi_arr, 1).tolist()
        dni_list = np.round(dni_arr, 1).tolist()
        dhi_list = np.round(dhi_arr, 1).tolist()
        temp_list = np.round(temp_arr, 1).tolist()
        wind_list = np.round(wind_arr, 2).tolist()
        cloud_list = np.round(cloud_cover, 0).tolist()
        code_list = [int(x) for x in code_arr.tolist()]
        rh_list = np.round(rh_arr, 0).tolist()

    # Select current hour (if night-time in offline fallback, pick midday snapshot if current GHI == 0 so UI preview is informative, or keep current hour if daytime)
    cur_idx = int(np.clip(now_sh.hour, 0, 23))
    if ghi_list[cur_idx] < 15.0:
        cur_idx = 13  # 13:00 CST representative solar hour for offline fallback

    time_strs = [ts.strftime("%Y-%m-%dT%H:%M") for ts in hourly_index]
    return {
        "latitude": lat,
        "longitude": lon,
        "timezone": "Asia/Shanghai",
        "current_units": {"wind_speed_10m": "m/s"},
        "hourly_units": {"wind_speed_10m": "m/s"},
        "current": {
            "time": time_strs[cur_idx],
            "temperature_2m": temp_list[cur_idx],
            "relative_humidity_2m": rh_list[cur_idx],
            "weather_code": code_list[cur_idx],
            "cloud_cover": cloud_list[cur_idx],
            "wind_speed_10m": wind_list[cur_idx],
            "wind_direction_10m": 155.0,
            "shortwave_radiation": ghi_list[cur_idx],
            "direct_normal_irradiance": dni_list[cur_idx],
            "diffuse_radiation": dhi_list[cur_idx],
        },
        "hourly": {
            "time": time_strs,
            "temperature_2m": temp_list,
            "relative_humidity_2m": rh_list,
            "cloud_cover": cloud_list,
            "wind_speed_10m": wind_list,
            "shortwave_radiation": ghi_list,
            "direct_normal_irradiance": dni_list,
            "diffuse_radiation": dhi_list,
        },
    }


def _request_open_meteo(lat: float, lon: float) -> dict[str, Any]:
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "current": (
            "temperature_2m,relative_humidity_2m,weather_code,cloud_cover,"
            "wind_speed_10m,wind_direction_10m,shortwave_radiation,"
            "direct_normal_irradiance,diffuse_radiation"
        ),
        "hourly": (
            "temperature_2m,relative_humidity_2m,cloud_cover,wind_speed_10m,"
            "shortwave_radiation,direct_normal_irradiance,diffuse_radiation"
        ),
        "timezone": "Asia/Shanghai",
        "forecast_days": 7,
    }
    response = requests.get(OPEN_METEO_URL, params=params, timeout=4.0)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or "current" not in payload or "hourly" not in payload:
        raise ValueError("Malformed Open-Meteo response payload.")
    return payload


def fetch_live_weather(
    lat: float,
    lon: float,
    *,
    dc_kw: float = 100.0,
    tilt_deg: float = 15.0,
    azimuth_deg: float = 180.0,
    offline: bool = False,
) -> dict[str, Any]:
    """Fetch official real-time & 7-day forecast weather + solar irradiance with disk cache and TMY fallback."""
    lat, lon = _validate_coords(lat, lon)
    dc_kw = float(max(0.1, dc_kw))
    tilt_deg = float(np.clip(tilt_deg, 0.0, 90.0))
    azimuth_deg = float(azimuth_deg % 360.0)

    payload: dict[str, Any] | None = None
    mode = "live_official_api"
    station_note = "Open-Meteo Official Global NWP (CMA GRAPES / ECMWF IFS / NOAA GFS 实时同化气象场)"

    if not offline:
        cached = _read_cached_payload(lat, lon, ignore_ttl=False)
        if cached is not None:
            payload = cached
            mode = "cached_official_api"
            station_note = "本地 30 分钟缓存 · Open-Meteo 官方气象同化场 (CMA / ECMWF / GFS)"
        else:
            try:
                payload = _request_open_meteo(lat, lon)
                _write_cached_payload(lat, lon, payload)
                mode = "live_official_api"
            except Exception:
                payload = None

    if payload is None:
        # Try expired disk cache before synthesizing TMY fallback
        cached_any = _read_cached_payload(lat, lon, ignore_ttl=True)
        if cached_any is not None and not offline:
            payload = cached_any
            mode = "cached_official_api"
            station_note = "离线缓存回退 · Open-Meteo 官方气象同化场 (CMA / ECMWF / GFS)"
        else:
            payload = _synthesize_offline_payload(lat, lon)
            mode = "offline_tmy_fallback"
            station_note = "离线典型气象年 (PVGIS/NASA TMY + Ineichen 晴空大气模型) 物理合成场"

    # Unit conversion for wind speed (Open-Meteo defaults to km/h unless wind_speed_unit=ms)
    cur_wind_unit = str(payload.get("current_units", {}).get("wind_speed_10m", "km/h")).lower()
    hr_wind_unit = str(payload.get("hourly_units", {}).get("wind_speed_10m", cur_wind_unit)).lower()
    cur_wind_scale = (1.0 / 3.6) if "km" in cur_wind_unit else 1.0
    hr_wind_scale = (1.0 / 3.6) if "km" in hr_wind_unit else 1.0

    hourly = payload["hourly"]
    h_times_raw = hourly["time"]
    h_times = pd.to_datetime(h_times_raw).tz_localize(
        SHANGHAI_TZ, nonexistent="shift_forward", ambiguous="NaT"
    )
    h_ghi = np.asarray(hourly.get("shortwave_radiation", [0.0] * len(h_times)), dtype=float)
    h_dni = np.asarray(hourly.get("direct_normal_irradiance", [0.0] * len(h_times)), dtype=float)
    h_dhi = np.asarray(hourly.get("diffuse_radiation", [0.0] * len(h_times)), dtype=float)
    h_temp = np.asarray(hourly.get("temperature_2m", [20.0] * len(h_times)), dtype=float)
    h_rh = np.asarray(hourly.get("relative_humidity_2m", [60.0] * len(h_times)), dtype=float)
    h_cloud = np.asarray(hourly.get("cloud_cover", [25.0] * len(h_times)), dtype=float)
    h_wind = np.asarray(hourly.get("wind_speed_10m", [2.0] * len(h_times)), dtype=float) * hr_wind_scale

    h_poa, h_tcell, h_ac_kw = _compute_poa_and_power_series(
        h_times + pd.Timedelta(minutes=30),
        lat,
        lon,
        h_ghi,
        h_dni,
        h_dhi,
        h_temp,
        h_wind,
        dc_kw=dc_kw,
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
    )

    # Current conditions
    cur = payload["current"]
    cur_time_str = str(cur.get("time") or h_times_raw[0])
    try:
        cur_ts = pd.Timestamp(cur_time_str)
        if cur_ts.tzinfo is None:
            cur_ts = cur_ts.tz_localize(SHANGHAI_TZ)
        else:
            cur_ts = cur_ts.tz_convert(SHANGHAI_TZ)
    except Exception:
        cur_ts = h_times[0]

    cur_temp = float(cur.get("temperature_2m", 22.0))
    cur_rh = float(cur.get("relative_humidity_2m", 58.0))
    cur_wind_ms = float(cur.get("wind_speed_10m", 2.0)) * cur_wind_scale
    cur_wind_dir = float(cur.get("wind_direction_10m", 160.0))
    cur_cloud = float(cur.get("cloud_cover", 20.0))
    cur_code = int(cur.get("weather_code", 1))
    cur_ghi = float(max(0.0, cur.get("shortwave_radiation", 0.0)))
    cur_dni = float(max(0.0, cur.get("direct_normal_irradiance", 0.0)))
    cur_dhi = float(max(0.0, cur.get("diffuse_radiation", 0.0)))

    cur_poa_arr, cur_tcell_arr, cur_ac_arr = _compute_poa_and_power_series(
        pd.DatetimeIndex([cur_ts]),
        lat,
        lon,
        np.array([cur_ghi]),
        np.array([cur_dni]),
        np.array([cur_dhi]),
        np.array([cur_temp]),
        np.array([cur_wind_ms]),
        dc_kw=dc_kw,
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
    )
    cur_poa = float(cur_poa_arr[0])
    cur_tcell = float(cur_tcell_arr[0])
    cur_power_kw = float(cur_ac_arr[0])
    cur_spec_w_kwp = float((cur_power_kw / dc_kw) * 1000.0) if dc_kw > 0 else 0.0

    # Build 7-day daily summary
    df_hourly = pd.DataFrame(
        {
            "time_str": h_times_raw,
            "date": [str(t)[:10] for t in h_times_raw],
            "hour": [int(str(t)[11:13]) if len(str(t)) >= 13 else 0 for t in h_times_raw],
            "ghi": h_ghi,
            "dni": h_dni,
            "dhi": h_dhi,
            "poa": h_poa,
            "temp_c": h_temp,
            "rh_pct": h_rh,
            "cloud": h_cloud,
            "wind_ms": h_wind,
            "ac_kw": h_ac_kw,
        }
    )

    daily_7d: list[dict[str, Any]] = []
    for date_str, grp in df_hourly.groupby("date", sort=True):
        if len(daily_7d) >= 7:
            break
        day_grp = grp[(grp["hour"] >= 8) & (grp["hour"] <= 17)]
        mean_cloud = float(day_grp["cloud"].mean()) if len(day_grp) > 0 else float(grp["cloud"].mean())
        if mean_cloud < 20.0:
            d_code = 0
        elif mean_cloud < 48.0:
            d_code = 1
        elif mean_cloud < 75.0:
            d_code = 2
        else:
            d_code = 3

        ghi_kwh = float(grp["ghi"].sum() / 1000.0)
        poa_kwh = float(grp["poa"].sum() / 1000.0)
        pred_kwh = float(grp["ac_kw"].sum())
        spec_kwh = float(pred_kwh / dc_kw) if dc_kw > 0 else 0.0

        daily_7d.append(
            {
                "date": str(date_str),
                "weather_code": int(d_code),
                "weather_label_zh": wmo_code_to_zh(d_code),
                "temp_min_c": round(float(grp["temp_c"].min()), 1),
                "temp_max_c": round(float(grp["temp_c"].max()), 1),
                "ghi_kwh_m2": round(ghi_kwh, 2),
                "poa_kwh_m2": round(poa_kwh, 2),
                "predicted_kwh": round(pred_kwh, 1),
                "specific_kwh_kwp": round(spec_kwh, 2),
                "wind_max_ms": round(float(grp["wind_ms"].max()), 1),
            }
        )

    # Build 48-hour forecast window (starting at beginning of today so two full diurnal cycles are always visible)
    hourly_48h: list[dict[str, Any]] = []
    n_hours = min(48, len(df_hourly))
    for idx in range(n_hours):
        row = df_hourly.iloc[idx]
        hourly_48h.append(
            {
                "time": str(row["time_str"]),
                "ghi_wm2": round(float(row["ghi"]), 1),
                "dni_wm2": round(float(row["dni"]), 1),
                "dhi_wm2": round(float(row["dhi"]), 1),
                "poa_wm2": round(float(row["poa"]), 1),
                "temp_c": round(float(row["temp_c"]), 1),
                "wind_speed_ms": round(float(row["wind_ms"]), 2),
                "cloud_cover_pct": round(float(row["cloud"]), 0),
                "ac_kw": round(float(row["ac_kw"]), 2),
            }
        )

    return {
        "ok": True,
        "location": {
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "timezone": "Asia/Shanghai",
        },
        "provenance": {
            "source": (
                "Open-Meteo Official Meteorological Feed (CMA / ECMWF / GFS)"
                if mode in ("live_official_api", "cached_official_api")
                else "Offline TMY / Clear-Sky Fallback (Open-Meteo / CMA / PVGIS 离线合成兜底)"
            ),
            "mode": mode,
            "fetched_at": str(payload.get("_cached_at_iso") or datetime.now(timezone.utc).isoformat()),
            "station_note": station_note,
        },
        "current": {
            "time": cur_time_str,
            "temp_c": round(cur_temp, 1),
            "rh_pct": round(cur_rh, 0),
            "wind_speed_ms": round(cur_wind_ms, 2),
            "wind_dir_deg": round(cur_wind_dir, 0),
            "cloud_cover_pct": round(cur_cloud, 0),
            "weather_code": int(cur_code),
            "weather_label_zh": wmo_code_to_zh(cur_code),
            "ghi_wm2": round(cur_ghi, 1),
            "dni_wm2": round(cur_dni, 1),
            "dhi_wm2": round(cur_dhi, 1),
            "poa_wm2": round(cur_poa, 1),
            "t_cell_c": round(cur_tcell, 1),
            "live_power_kw": round(cur_power_kw, 2),
            "live_specific_w_kwp": round(cur_spec_w_kwp, 1),
        },
        "daily_7d": daily_7d,
        "hourly_48h": hourly_48h,
    }
