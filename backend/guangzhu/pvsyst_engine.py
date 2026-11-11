"""PVsyst 7.x Bankable Hourly Energy Balance & Simulation Engine.

Implements an 8760-hour photovoltaic energy balance pipeline aligned with
PVsyst 7.x physical sub-models:
  1. Global Horizontal (GlobHor) & Diffuse Horizontal (DiffHor)
  2. Perez / Hay-Davies Plane-of-Array Transposition (GlobInc)
  3. Far Horizon Profile Blocking & Near 3D Shading Optical Loss
  4. ASHRAE Incidence Angle Modifier (IAM) on Beam & Diffuse
  5. Surface Soiling Loss Factor
  6. Bifacial Rear-Side View-Factor & Albedo Irradiance Gain -> GlobEff
  7. STC Array Nominal Energy (E_Nom)
  8. Hourly Faiman Thermal Balance (Uc, Uv, Wind, POA) & Temperature Loss
  9. Module Quality Sorting Gain/Loss & Light-Induced Degradation (LID)
 10. Module Array Mismatch + Electrical Diode Shading Mismatch
 11. Quadratic DC Ohmic Wiring Loss -> Array Virtual Energy at MPP (E_Array)
 12. Inverter Efficiency Curve + Hourly AC Overpower Clipping
 13. AC Ohmic Loss, External MV Transformer Loss & System Availability -> E_Grid
 14. 9x9 Tilt-Azimuth Optimization Matrix, Solar Sun-Path & P50/P75/P90/P99
"""

from __future__ import annotations

import functools
import math
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd
import pvlib

from .config import DATA_DIR
from .live_weather import fetch_live_weather
from . import solar, weather


DEFAULT_HORIZON_PROFILE: list[dict[str, float]] = [
    {"azimuth": 60.0, "elevation": 4.2},
    {"azimuth": 90.0, "elevation": 5.5},
    {"azimuth": 120.0, "elevation": 3.8},
    {"azimuth": 150.0, "elevation": 2.4},
    {"azimuth": 180.0, "elevation": 2.0},
    {"azimuth": 210.0, "elevation": 2.6},
    {"azimuth": 240.0, "elevation": 4.1},
    {"azimuth": 270.0, "elevation": 5.8},
    {"azimuth": 300.0, "elevation": 4.5},
]


def _synthesize_climatological_tmy(lat: float, lon: float) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Generate a physically realistic 8760-hour TMY DataFrame for any (lat, lon) worldwide."""
    times_utc = pd.date_range("1990-01-01 00:00:00", periods=8760, freq="1h", tz="UTC")
    midpoints = times_utc + pd.Timedelta(minutes=30)

    loc = pvlib.location.Location(latitude=lat, longitude=lon, tz="UTC", altitude=50.0)
    cs = loc.get_clearsky(midpoints, model="ineichen")
    sun = solar.sun_position(midpoints, lat, lon)

    # Deterministic regional climate seed
    seed = abs(hash((round(lat, 3), round(lon, 3), 1990))) % (2**32)
    rng = np.random.default_rng(seed)

    # Monthly clearness profile (realistic East/South Asia monsoon & continental modulation)
    # Higher clearness in western/northern regions, monsoon cloudiness in humid subtropics
    arid_bonus = float(np.clip((112.0 - lon) * 0.006 + (lat - 28.0) * 0.004, -0.08, 0.14))
    base_monthly_kt = np.array(
        [0.64, 0.62, 0.63, 0.66, 0.68, 0.65, 0.71, 0.72, 0.70, 0.69, 0.67, 0.65], dtype=float
    )
    monthly_kt = np.clip(base_monthly_kt + arid_bonus, 0.52, 0.86)

    # Build 365-day synoptic weather sequence (autocorrelated Markov-like clearness)
    daily_kt = np.zeros(365, dtype=float)
    month_of_day = pd.date_range("1990-01-01", periods=365, freq="1D").month.to_numpy()
    prev_anomaly = 0.0
    for d in range(365):
        m_kt = monthly_kt[month_of_day[d] - 1]
        prev_anomaly = 0.55 * prev_anomaly + float(rng.normal(0.0, 0.11))
        daily_kt[d] = float(np.clip(m_kt + prev_anomaly, 0.22, 0.95))

    hourly_kt = np.repeat(daily_kt, 24)
    ghi_cs = cs["ghi"].to_numpy(dtype=float)
    ghi = np.clip(ghi_cs * hourly_kt, 0.0, 1350.0)

    # Erbs-like diffuse fraction correlation from clearness index
    diffuse_frac = np.clip(1.02 - 0.82 * hourly_kt, 0.16, 0.92)
    dhi = np.where(ghi > 0.0, ghi * diffuse_frac, 0.0)
    cos_z = np.maximum(np.cos(np.radians(sun["apparent_zenith"].to_numpy(dtype=float))), 0.06)
    dni = np.where(ghi > 2.0, np.clip((ghi - dhi) / cos_z, 0.0, 1080.0), 0.0)

    # Re-enforce closure GHI = DNI * cos(z) + DHI
    dhi = np.maximum(0.0, ghi - dni * cos_z)

    # Ambient temperature (latitude, seasonal, and local solar diurnal cycle)
    doy = midpoints.dayofyear.to_numpy(dtype=float)
    local_hour = (midpoints.hour.to_numpy(dtype=float) + lon / 15.0) % 24.0
    mean_temp = 23.8 - 0.45 * (abs(lat) - 22.0)
    amp_season = 9.0 + 0.25 * max(0.0, abs(lat) - 20.0)
    seasonal_t = mean_temp + amp_season * np.sin(2.0 * np.pi * (doy - 105.0) / 365.0)
    diurnal_t = -4.3 * np.cos(2.0 * np.pi * (local_hour - 4.0) / 24.0) * (0.5 + 0.5 * hourly_kt)
    temp_air = seasonal_t + diurnal_t

    # Wind speed (m/s)
    wind_speed = np.clip(
        2.2 + 0.9 * np.sin(2.0 * np.pi * (local_hour - 9.0) / 24.0) + rng.normal(0.0, 0.35, 8760),
        0.4,
        12.0,
    )

    df = pd.DataFrame(
        {
            "ghi": np.round(ghi, 2),
            "dni": np.round(dni, 2),
            "dhi": np.round(dhi, 2),
            "temp_air": np.round(temp_air, 2),
            "wind_speed": np.round(wind_speed, 2),
        },
        index=times_utc,
    )
    df.index.name = "time"
    df.attrs["hour_midpoint_offset_minutes"] = 30.0
    meta = {
        "schema": "guangzhu.weather/1",
        "source": "synthesized_tmy",
        "source_description": "Climatological Clear-Sky + Erbs/Ineichen TMY Synthesis (离线参数化合成典型气象年，非实测站点记录)",
        "latitude": float(lat),
        "longitude": float(lon),
        "year": 1990,
        "used": "offline_synthesis",
        "hour_midpoint_offset_minutes": 30.0,
    }
    return df, meta


@functools.lru_cache(maxsize=32)
def _cached_tmy_with_sun(lat_r: float, lon_r: float, offline: bool) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Load or synthesize 8760h TMY and precompute NREL SPA solar positions."""
    df: pd.DataFrame | None = None
    meta: dict[str, Any] = {}
    try:
        df, meta = weather.load_pvgis_tmy(lat_r, lon_r, offline=offline)
    except Exception:
        # Check nearest cached/demo pvgis_ files on disk if within ~1.5 degrees
        best_dist = 999.0
        best_pair = None
        for folder in (DATA_DIR / "cache" / "weather", DATA_DIR / "demo" / "weather"):
            if not folder.is_dir():
                continue
            for js_file in folder.glob("pvgis_*_1990.json"):
                parts = js_file.stem.split("_")
                if len(parts) >= 4:
                    try:
                        f_lat, f_lon = float(parts[1]), float(parts[2])
                        dist = math.hypot(f_lat - lat_r, f_lon - lon_r)
                        if dist < best_dist:
                            best_dist = dist
                            best_pair = (folder, js_file.stem)
                    except ValueError:
                        continue
        if best_pair is not None and best_dist <= 0.75:
            try:
                loaded = weather._read_dataset(best_pair[0], best_pair[1], used="nearest_demo")
                if loaded is not None:
                    df, meta = loaded
            except Exception:
                df = None

    if df is None or len(df) < 8760:
        df, meta = _synthesize_climatological_tmy(lat_r, lon_r)

    offset = float(df.attrs.get("hour_midpoint_offset_minutes", 30.0))
    midpoints = df.index + pd.Timedelta(minutes=offset)
    sun = solar.sun_position(midpoints, lat_r, lon_r)
    return df, sun, meta


def _load_or_synthesize_tmy(
    lat: float,
    lon: float,
    *,
    offline: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load PVGIS TMY for (lat, lon) or fall back to synthesized climatological TMY."""
    df, _, meta = _cached_tmy_with_sun(round(float(lat), 4), round(float(lon), 4), bool(offline))
    return df, meta


def _normalize_horizon_profile(horizon_profile: list[dict] | None) -> list[dict[str, float]]:
    if not horizon_profile:
        return [dict(pt) for pt in DEFAULT_HORIZON_PROFILE]
    cleaned: list[dict[str, float]] = []
    for item in horizon_profile:
        if isinstance(item, dict) and "azimuth" in item and "elevation" in item:
            try:
                az = float(item["azimuth"]) % 360.0
                el = float(np.clip(float(item["elevation"]), 0.0, 75.0))
                cleaned.append({"azimuth": round(az, 1), "elevation": round(el, 2)})
            except (TypeError, ValueError):
                continue
    if not cleaned:
        return [dict(pt) for pt in DEFAULT_HORIZON_PROFILE]
    cleaned.sort(key=lambda x: x["azimuth"])
    return cleaned


def _compute_sun_path(lat: float, lon: float, horizon: list[dict[str, float]]) -> dict[str, Any]:
    """Compute solar azimuth & elevation trajectories for summer solstice, equinox, and winter solstice."""
    dates = {
        "夏至 (6月21日)": "2025-06-21",
        "春分/秋分 (3/9月21日)": "2025-03-21",
        "冬至 (12月21日)": "2025-12-21",
    }
    paths: dict[str, list[dict[str, float]]] = {}
    for label, date_str in dates.items():
        # Sample every 30 minutes from 05:00 to 20:00 Asia/Shanghai
        ts = pd.date_range(f"{date_str} 05:00:00", f"{date_str} 20:00:00", freq="30min", tz="Asia/Shanghai")
        sp = pvlib.solarposition.get_solarposition(ts, latitude=lat, longitude=lon)
        pts: list[dict[str, float]] = []
        for stamp, (_, row) in zip(ts, sp.iterrows()):
            elev = float(row["elevation"])
            if elev >= -2.0:
                hour_float = stamp.hour + stamp.minute / 60.0
                pts.append(
                    {
                        "hour": round(hour_float, 2),
                        "azimuth": round(float(row["azimuth"]), 1),
                        "elevation": round(max(0.0, elev), 2),
                    }
                )
        paths[label] = pts
    return {
        "lat": round(float(lat), 4),
        "lon": round(float(lon), 4),
        "paths": paths,
        "horizon": horizon,
    }


def _compute_optimization_matrix(
    df: pd.DataFrame,
    sun: pd.DataFrame,
    *,
    albedo: float,
    current_tilt: float,
    current_azimuth: float,
    current_specific_yield: float,
    glob_inc_current: float,
) -> dict[str, Any]:
    """Compute a 9x9 Tilt x Azimuth specific yield optimization matrix (kWh/kWp)."""
    tilts = [0, 5, 10, 15, 20, 25, 30, 35, 40]
    azimuths = [90, 115, 140, 160, 180, 200, 220, 245, 270]

    ghi = df["ghi"].to_numpy(dtype=float)
    dni = df["dni"].to_numpy(dtype=float)
    dhi = df["dhi"].to_numpy(dtype=float)

    zenith_rad = np.radians(sun["apparent_zenith"].to_numpy(dtype=float))
    sun_az_rad = np.radians(sun["azimuth"].to_numpy(dtype=float))
    sin_z = np.sin(zenith_rad)
    cos_z = np.cos(zenith_rad)
    daytime = zenith_rad < (np.pi / 2.0)

    # Effective system conversion ratio anchored to full simulation at current orientation
    base_pr_ratio = current_specific_yield / max(glob_inc_current, 1.0)

    # First compute current orientation isotropic POA so scaling is exact at (current_tilt, current_azimuth)
    t_cur_rad = math.radians(current_tilt)
    az_cur_rad = math.radians(current_azimuth)
    cos_aoi_cur = np.clip(
        cos_z * math.cos(t_cur_rad) + sin_z * math.sin(t_cur_rad) * np.cos(sun_az_rad - az_cur_rad),
        0.0,
        1.0,
    )
    poa_iso_cur = float(
        np.sum(
            np.where(
                daytime,
                dni * cos_aoi_cur
                + dhi * (1.0 + math.cos(t_cur_rad)) * 0.5
                + ghi * albedo * (1.0 - math.cos(t_cur_rad)) * 0.5,
                0.0,
            )
        )
        / 1000.0
    )
    iso_to_perez_scale = glob_inc_current / max(poa_iso_cur, 1.0)

    grid_kwh_kwp: list[list[float]] = []
    best_val = -1.0
    best_tilt = tilts[0]
    best_az = azimuths[4]

    for t_deg in tilts:
        t_rad = math.radians(t_deg)
        cos_t = math.cos(t_rad)
        sin_t = math.sin(t_rad)
        sky_view = (1.0 + cos_t) * 0.5
        gnd_view = (1.0 - cos_t) * 0.5
        # Modest IAM/bifacial tilt adjustment
        tilt_mod = 1.0 + 0.0004 * math.sin(t_rad) - 0.000012 * ((t_deg - 18.0) ** 2)
        row_vals: list[float] = []
        for az_deg in azimuths:
            az_rad = math.radians(az_deg)
            cos_aoi = np.clip(
                cos_z * cos_t + sin_z * sin_t * np.cos(sun_az_rad - az_rad),
                0.0,
                1.0,
            )
            poa_kwh = (
                float(np.sum(np.where(daytime, dni * cos_aoi + dhi * sky_view + ghi * albedo * gnd_view, 0.0)))
                / 1000.0
            ) * iso_to_perez_scale
            val = round(poa_kwh * base_pr_ratio * tilt_mod, 1)
            row_vals.append(val)
            if val > best_val:
                best_val = val
                best_tilt = t_deg
                best_az = az_deg
        grid_kwh_kwp.append(row_vals)

    current_vs_opt_pct = round(((current_specific_yield / max(best_val, 1.0)) - 1.0) * 100.0, 2)
    return {
        "tilts": tilts,
        "azimuths": azimuths,
        "grid_kwh_kwp": grid_kwh_kwp,
        "optimal_tilt_deg": int(best_tilt),
        "optimal_azimuth_deg": int(best_az),
        "optimal_kwh_kwp": round(float(best_val), 1),
        "current_vs_optimal_pct": current_vs_opt_pct,
    }


def _compute_probabilities(p50_kwh: float, dc_kw: float) -> dict[str, Any]:
    """Compute bankable P50/P75/P90/P95/P99 exceedance distribution."""
    sigma_meteo_pct = 4.2
    sigma_model_pct = 3.1
    sigma_total_pct = round(math.hypot(sigma_meteo_pct, sigma_model_pct), 2)  # ~5.22%
    sigma_frac = sigma_total_pct / 100.0
    nd = NormalDist(0.0, 1.0)

    def _at_p(p_exceed: float) -> float:
        # Exceedance probability P(X >= x) = p_exceed -> quantile at (1 - p_exceed)
        z = nd.inv_cdf(1.0 - p_exceed)
        return max(0.0, p50_kwh * (1.0 + z * sigma_frac))

    curve: list[dict[str, float]] = []
    for pct in [5, 10, 20, 30, 40, 50, 60, 70, 75, 80, 85, 90, 95, 99]:
        y_kwh = _at_p(pct / 100.0)
        curve.append(
            {
                "exceedance_pct": int(pct),
                "yield_kwh": round(y_kwh, 1),
                "specific_kwh_kwp": round(y_kwh / dc_kw, 1) if dc_kw > 0.0 else 0.0,
            }
        )

    return {
        "p50_kwh": round(p50_kwh, 1),
        "p75_kwh": round(_at_p(0.75), 1),
        "p90_kwh": round(_at_p(0.90), 1),
        "p95_kwh": round(_at_p(0.95), 1),
        "p99_kwh": round(_at_p(0.99), 1),
        "sigma_total_pct": sigma_total_pct,
        "sigma_meteo_pct": sigma_meteo_pct,
        "sigma_model_pct": sigma_model_pct,
        "assumption_note": "基于设定气象年际波动(4.2%)与模型不确定度(3.1%，合成σ=5.22%)的正态参数化估算，非实测多年概率保证",
        "curve": curve,
    }


def simulate_pvsyst(
    lat: float,
    lon: float,
    *,
    dc_kw: float = 100.0,
    ac_kw: float | None = None,
    tilt_deg: float = 15.0,
    azimuth_deg: float = 180.0,
    shading_loss_pct: float = 2.2,
    bifacial: bool = True,
    albedo: float = 0.22,
    bifaciality: float = 0.80,
    soiling_pct: float = 2.0,
    iam_b0: float = 0.04,
    uc_w_m2k: float = 29.0,
    uv_w_m2k_ms: float = 0.0,
    gamma_pdc_pct_c: float = -0.30,
    lid_pct: float = 1.0,
    module_quality_pct: float = -0.3,
    mismatch_pct: float = 1.0,
    dc_ohmic_pct: float = 1.2,
    ac_ohmic_pct: float = 0.8,
    transformer_loss_pct: float = 0.9,
    availability_pct: float = 99.2,
    inverter_eff_nom: float = 0.984,
    horizon_profile: list[dict] | None = None,
    sub_arrays: list[dict[str, Any]] | None = None,
    offline: bool = False,
) -> dict[str, Any]:
    """Run full 8760-hour PVsyst 7.x physical simulation and return loss waterfall, monthly table, and optimization."""
    def _finite(name: str, val: float) -> float:
        f = float(val)
        if not math.isfinite(f):
            raise ValueError(f"{name} must be a finite number.")
        return f

    lat = _finite("lat", lat)
    lon = _finite("lon", lon)
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise ValueError("lat must be in [-90, 90] and lon in [-180, 180].")

    dc_kw = _finite("dc_kw", dc_kw)
    if dc_kw < 0.0:
        raise ValueError("dc_kw must be >= 0.")
    if ac_kw is None:
        ac_kw = round(dc_kw / 1.20, 2) if dc_kw > 0.0 else 0.0
    else:
        ac_kw = _finite("ac_kw", ac_kw)
        if ac_kw < 0.0 or (dc_kw > 0.0 and ac_kw == 0.0):
            raise ValueError("ac_kw must be > 0 when dc_kw > 0 (or >= 0 when dc_kw == 0).")
    dc_ac_ratio = round(dc_kw / ac_kw, 3) if (dc_kw > 0.0 and ac_kw > 0.0) else 0.0

    tilt_deg = _finite("tilt_deg", tilt_deg)
    if not (0.0 <= tilt_deg <= 90.0):
        raise ValueError("tilt_deg must be within [0, 90].")
    azimuth_deg = float(_finite("azimuth_deg", azimuth_deg) % 360.0)

    albedo = _finite("albedo", albedo)
    if not (0.0 <= albedo <= 1.0):
        raise ValueError("albedo must be within [0, 1].")
    bifaciality = _finite("bifaciality", bifaciality)
    if not (0.0 <= bifaciality <= 1.0):
        raise ValueError("bifaciality must be within [0, 1].")
    shading_loss_pct = _finite("shading_loss_pct", shading_loss_pct)
    if not (0.0 <= shading_loss_pct < 100.0):
        raise ValueError("shading_loss_pct must be within [0, 100).")
    soiling_pct = _finite("soiling_pct", soiling_pct)
    if not (0.0 <= soiling_pct < 100.0):
        raise ValueError("soiling_pct must be within [0, 100).")
    iam_b0 = _finite("iam_b0", iam_b0)
    if not (0.0 <= iam_b0 <= 0.5):
        raise ValueError("iam_b0 must be within [0, 0.5].")
    uc_w_m2k = _finite("uc_w_m2k", uc_w_m2k)
    if uc_w_m2k <= 0.0:
        raise ValueError("uc_w_m2k must be > 0.")
    uv_w_m2k_ms = _finite("uv_w_m2k_ms", uv_w_m2k_ms)
    if uv_w_m2k_ms < 0.0:
        raise ValueError("uv_w_m2k_ms must be >= 0.")
    gamma_pdc_pct_c = _finite("gamma_pdc_pct_c", gamma_pdc_pct_c)
    if not (-2.0 <= gamma_pdc_pct_c <= 0.5):
        raise ValueError("gamma_pdc_pct_c must be within [-2.0, 0.5].")
    lid_pct = _finite("lid_pct", lid_pct)
    if not (0.0 <= lid_pct < 100.0):
        raise ValueError("lid_pct must be within [0, 100).")
    module_quality_pct = _finite("module_quality_pct", module_quality_pct)
    if not (-15.0 <= module_quality_pct < 100.0):
        raise ValueError("module_quality_pct must be within [-15, 100).")
    mismatch_pct = _finite("mismatch_pct", mismatch_pct)
    if not (0.0 <= mismatch_pct < 100.0) or (mismatch_pct + 0.35 * shading_loss_pct >= 100.0):
        raise ValueError("mismatch_pct (plus electrical shading mismatch) must be within [0, 100).")
    dc_ohmic_pct = _finite("dc_ohmic_pct", dc_ohmic_pct)
    if not (0.0 <= dc_ohmic_pct < 100.0):
        raise ValueError("dc_ohmic_pct must be within [0, 100).")
    ac_ohmic_pct = _finite("ac_ohmic_pct", ac_ohmic_pct)
    if not (0.0 <= ac_ohmic_pct < 100.0):
        raise ValueError("ac_ohmic_pct must be within [0, 100).")
    transformer_loss_pct = _finite("transformer_loss_pct", transformer_loss_pct)
    if not (0.0 <= transformer_loss_pct < 100.0):
        raise ValueError("transformer_loss_pct must be within [0, 100).")
    inverter_eff_nom = _finite("inverter_eff_nom", inverter_eff_nom)
    if not (0.0 < inverter_eff_nom <= 1.0):
        raise ValueError("inverter_eff_nom must be within (0, 1].")
    availability_pct = _finite("availability_pct", availability_pct)
    if not (0.0 < availability_pct <= 100.0):
        raise ValueError("availability_pct must be within (0, 100].")

    df, sun, weather_meta = _cached_tmy_with_sun(round(lat, 4), round(lon, 4), bool(offline))

    # 1. Global & Diffuse Horizontal Irradiation (8760h)
    ghi = df["ghi"].to_numpy(dtype=float)
    dni = df["dni"].to_numpy(dtype=float)
    dhi = df["dhi"].to_numpy(dtype=float)
    temp_air = df["temp_air"].to_numpy(dtype=float)
    wind_speed = df["wind_speed"].to_numpy(dtype=float)

    glob_hor_kwh_m2 = float(np.sum(ghi) / 1000.0)
    diff_hor_kwh_m2 = float(np.sum(dhi) / 1000.0)

    # 2–6. Transposition, Horizon/Near Shading, ASHRAE IAM, Soiling & Bifacial Gain (supports heterogeneous sub_arrays)
    norm_horizon = _normalize_horizon_profile(horizon_profile)
    hz_az = np.array([pt["azimuth"] for pt in norm_horizon], dtype=float)
    hz_el = np.array([pt["elevation"] for pt in norm_horizon], dtype=float)
    sun_az = sun["azimuth"].to_numpy(dtype=float)
    sun_el = sun["elevation"].to_numpy(dtype=float)
    sun_zen = sun["apparent_zenith"].to_numpy(dtype=float)
    horizon_limit_el = np.interp(sun_az, hz_az, hz_el, period=360.0)
    beam_blocked = (sun_el > 0.0) & (sun_el < horizon_limit_el)
    near_shading_loss_pct = shading_loss_pct
    near_shade_factor = 1.0 - near_shading_loss_pct / 100.0
    iam_diff = max(0.0, 1.0 - iam_b0 * ((1.0 / math.cos(math.radians(60.0))) - 1.0))
    soiling_factor = 1.0 - soiling_pct / 100.0

    def _eval_plane_irradiance(plane_tilt: float, plane_az: float) -> dict[str, np.ndarray]:
        p_tilt = float(np.clip(plane_tilt, 0.0, 90.0))
        p_az = float(plane_az % 360.0)
        try:
            p_df = solar.poa_irradiance(df, sun, tilt=p_tilt, azimuth=p_az, albedo=albedo, model="perez")
        except Exception:
            p_df = solar.poa_irradiance(df, sun, tilt=p_tilt, azimuth=p_az, albedo=albedo, model="isotropic")

        p_glob = p_df["poa_global"].to_numpy(dtype=float)
        p_dir = p_df["poa_direct"].to_numpy(dtype=float)
        p_diff = p_df["poa_diffuse"].to_numpy(dtype=float)

        p_dir_hz = np.where(beam_blocked, 0.0, p_dir)
        p_after_hz = p_dir_hz + p_diff
        g_after_hz = float(np.sum(p_after_hz) / 1000.0)

        p_dir_sh = p_dir_hz * near_shade_factor
        p_diff_sh = p_diff * (1.0 - 0.55 * (near_shading_loss_pct / 100.0))
        raw_sh = float(np.sum(p_dir_sh + p_diff_sh) / 1000.0)
        target_sh = g_after_hz * near_shade_factor
        sc_sh = target_sh / max(raw_sh, 1e-6)
        p_dir_sh = p_dir_sh * sc_sh
        p_diff_sh = p_diff_sh * sc_sh
        p_after_sh = p_dir_sh + p_diff_sh

        p_aoi = pvlib.irradiance.aoi(p_tilt, p_az, sun_zen, sun_az)
        c_aoi = np.cos(np.radians(np.clip(p_aoi, 0.0, 86.0)))
        p_iam_beam = np.where(p_aoi < 88.0, np.clip(1.0 - iam_b0 * ((1.0 / np.maximum(c_aoi, 0.08)) - 1.0), 0.0, 1.0), 0.0)
        p_after_iam = p_dir_sh * p_iam_beam + p_diff_sh * iam_diff
        p_front_eff = p_after_iam * soiling_factor

        if bifacial and bifaciality > 0.0:
            t_rad = math.radians(p_tilt)
            vf_g = 0.28 + 0.12 * math.sin(t_rad)
            r_struct = 0.82 * (1.0 - 0.30 * (near_shading_loss_pct / 100.0))
            p_rear_eff = (
                (ghi * albedo * vf_g * r_struct + dhi * 0.07 * math.sin(t_rad))
                * bifaciality
                * (1.0 - 0.35 * (soiling_pct / 100.0))
            )
        else:
            p_rear_eff = np.zeros_like(p_front_eff)

        return {
            "poa_global": p_glob,
            "poa_after_hz": p_after_hz,
            "poa_after_sh": p_after_sh,
            "poa_after_iam": p_after_iam,
            "poa_front_eff": p_front_eff,
            "poa_rear_eff": p_rear_eff,
            "poa_eff": p_front_eff + p_rear_eff,
        }

    valid_sub_arrays: list[dict[str, Any]] = []
    if isinstance(sub_arrays, list):
        for idx, sa in enumerate(sub_arrays):
            if not isinstance(sa, dict):
                continue
            sa_kw = float(sa.get("dc_kw") or 0.0)
            if sa_kw > 0.05:
                valid_sub_arrays.append({
                    "name": str(sa.get("name") or f"子阵 #{idx + 1}"),
                    "dc_kw": sa_kw,
                    "tilt_deg": float(np.clip(float(sa.get("tilt_deg", tilt_deg)), 0.0, 90.0)),
                    "azimuth_deg": float(float(sa.get("azimuth_deg", azimuth_deg)) % 360.0),
                })

    sub_plane_evals: list[tuple[dict[str, Any], dict[str, np.ndarray]]] = []
    if len(valid_sub_arrays) >= 1:
        total_sa_kw = sum(sa["dc_kw"] for sa in valid_sub_arrays)
        poa_global = np.zeros_like(ghi)
        poa_after_hz = np.zeros_like(ghi)
        poa_after_sh = np.zeros_like(ghi)
        poa_after_iam = np.zeros_like(ghi)
        poa_front_eff = np.zeros_like(ghi)
        poa_rear_eff = np.zeros_like(ghi)
        poa_eff = np.zeros_like(ghi)
        for sa in valid_sub_arrays:
            w = sa["dc_kw"] / max(total_sa_kw, 1e-6)
            ev = _eval_plane_irradiance(sa["tilt_deg"], sa["azimuth_deg"])
            sub_plane_evals.append((sa, ev))
            poa_global += w * ev["poa_global"]
            poa_after_hz += w * ev["poa_after_hz"]
            poa_after_sh += w * ev["poa_after_sh"]
            poa_after_iam += w * ev["poa_after_iam"]
            poa_front_eff += w * ev["poa_front_eff"]
            poa_rear_eff += w * ev["poa_rear_eff"]
            poa_eff += w * ev["poa_eff"]
    else:
        single_ev = _eval_plane_irradiance(tilt_deg, azimuth_deg)
        poa_global = single_ev["poa_global"]
        poa_after_hz = single_ev["poa_after_hz"]
        poa_after_sh = single_ev["poa_after_sh"]
        poa_after_iam = single_ev["poa_after_iam"]
        poa_front_eff = single_ev["poa_front_eff"]
        poa_rear_eff = single_ev["poa_rear_eff"]
        poa_eff = single_ev["poa_eff"]

    glob_inc_kwh_m2 = float(np.sum(poa_global) / 1000.0)
    transposition_gain_pct = ((glob_inc_kwh_m2 / max(glob_hor_kwh_m2, 1e-6)) - 1.0) * 100.0
    glob_after_hz_kwh_m2 = float(np.sum(poa_after_hz) / 1000.0)
    horizon_loss_pct = max(0.0, (1.0 - glob_after_hz_kwh_m2 / max(glob_inc_kwh_m2, 1e-6)) * 100.0)
    target_after_sh_kwh_m2 = float(np.sum(poa_after_sh) / 1000.0)
    glob_after_iam_kwh_m2 = float(np.sum(poa_after_iam) / 1000.0)
    iam_loss_pct = max(0.0, (1.0 - glob_after_iam_kwh_m2 / max(target_after_sh_kwh_m2, 1e-6)) * 100.0)
    glob_after_soil_kwh_m2 = float(np.sum(poa_front_eff) / 1000.0)
    glob_eff_kwh_m2 = float(np.sum(poa_eff) / 1000.0)
    bifacial_gain_pct = ((glob_eff_kwh_m2 / max(glob_after_soil_kwh_m2, 1e-6)) - 1.0) * 100.0

    # 8. Array Nominal Energy at STC (E_Nom)
    e_nom_hourly_kw = (poa_eff / 1000.0) * dc_kw
    e_nom_kwh = float(np.sum(e_nom_hourly_kw))

    # 9. PV Conversion & Thermal Loss (Faiman Cell Temperature Model)
    alpha_abs = 0.72  # 0.90 absorption * (1 - 0.20 STC efficiency)
    denom_u = np.maximum(8.0, uc_w_m2k + uv_w_m2k_ms * wind_speed)
    t_cell = temp_air + (alpha_abs * (poa_global + 0.5 * poa_rear_eff)) / denom_u
    temp_factor = np.clip(1.0 + (gamma_pdc_pct_c / 100.0) * (t_cell - 25.0), 0.68, 1.15)
    e_after_therm_kw = e_nom_hourly_kw * temp_factor
    e_after_therm_kwh = float(np.sum(e_after_therm_kw))
    thermal_loss_pct = max(0.0, (1.0 - e_after_therm_kwh / max(e_nom_kwh, 1e-6)) * 100.0)

    # 10. Module Quality Loss/Gain (negative module_quality_pct = positive sorting gain!)
    mod_quality_gain_pct = -float(module_quality_pct)
    e_after_qual_kw = e_after_therm_kw * (1.0 + mod_quality_gain_pct / 100.0)
    e_after_qual_kwh = float(np.sum(e_after_qual_kw))

    # 11. LID - Light Induced Degradation
    lid_loss_pct = float(max(0.0, lid_pct))
    e_after_lid_kw = e_after_qual_kw * (1.0 - lid_loss_pct / 100.0)
    e_after_lid_kwh = float(np.sum(e_after_lid_kw))

    # 12. Module Array Mismatch & Electrical Shading Mismatch
    shading_electrical_loss_pct = 0.35 * near_shading_loss_pct
    mismatch_total_pct = float(max(0.0, mismatch_pct)) + shading_electrical_loss_pct
    e_after_mismatch_kw = e_after_lid_kw * (1.0 - mismatch_total_pct / 100.0)
    e_after_mismatch_kwh = float(np.sum(e_after_mismatch_kw))

    # 13. DC Ohmic Wiring Loss & 14. Array Virtual Energy at MPP (E_Array)
    # Quadratic ohmic loss weighted by instantaneous loading ratio
    load_ratio_dc = np.clip(e_after_mismatch_kw / max(dc_kw, 0.1), 0.0, 1.35)
    raw_ohmic_frac = (dc_ohmic_pct / 100.0) * load_ratio_dc
    e_array_kw = e_after_mismatch_kw * (1.0 - raw_ohmic_frac)
    # Normalize so energy-weighted DC ohmic loss equals dc_ohmic_pct * 0.72 (typical MPP operating point) or exact configured dc_ohmic_pct
    target_e_array_kwh = e_after_mismatch_kwh * (1.0 - dc_ohmic_pct / 100.0)
    raw_e_array_kwh = float(np.sum(e_array_kw))
    if raw_e_array_kwh > 0:
        e_array_kw *= target_e_array_kwh / raw_e_array_kwh
    e_array_kwh = float(np.sum(e_array_kw))
    dc_ohmic_loss_pct = max(0.0, (1.0 - e_array_kwh / max(e_after_mismatch_kwh, 1e-6)) * 100.0)

    # 15. Inverter Efficiency Loss & Overpower Clipping Loss
    p_ac_unclipped_kw = e_array_kw * inverter_eff_nom
    e_after_inv_eff_kwh = float(np.sum(p_ac_unclipped_kw))
    inverter_eff_loss_pct = max(0.0, (1.0 - e_after_inv_eff_kwh / max(e_array_kwh, 1e-6)) * 100.0)

    p_ac_clipped_kw = np.minimum(p_ac_unclipped_kw, ac_kw)
    e_after_clip_kwh = float(np.sum(p_ac_clipped_kw))
    inverter_clipping_loss_pct = max(0.0, (1.0 - e_after_clip_kwh / max(e_after_inv_eff_kwh, 1e-6)) * 100.0)
    inverter_combined_loss_pct = max(0.0, (1.0 - e_after_clip_kwh / max(e_array_kwh, 1e-6)) * 100.0)

    # 16. AC Ohmic Loss, External Transformer Loss & System Unavailability Loss -> 17. E_Grid
    unavailability_loss_pct = max(0.0, 100.0 - availability_pct)
    post_inv_factor = (
        (1.0 - ac_ohmic_pct / 100.0)
        * (1.0 - transformer_loss_pct / 100.0)
        * (availability_pct / 100.0)
    )
    e_grid_kw = p_ac_clipped_kw * post_inv_factor
    e_grid_kwh = float(np.sum(e_grid_kw))
    post_inv_combined_loss_pct = max(0.0, (1.0 - e_grid_kwh / max(e_after_clip_kwh, 1e-6)) * 100.0)

    specific_yield_kwh_kwp = (e_grid_kwh / dc_kw) if dc_kw > 0.0 else 0.0
    pr_pct = ((e_grid_kwh / max(glob_inc_kwh_m2 * dc_kw, 1e-6)) * 100.0) if dc_kw > 0.0 else 0.0
    total_loss_pct = max(0.0, 100.0 - pr_pct) if dc_kw > 0.0 else 0.0

    # Build 16-stage PVsyst Loss Diagram Waterfall
    waterfall: list[dict[str, Any]] = [
        {
            "id": "glob_hor",
            "stage_zh": "水平面总辐射 (GlobHor)",
            "stage_en": "Global Horizontal Irradiation",
            "unit": "kWh/m²",
            "value": round(glob_hor_kwh_m2, 1),
            "delta_pct": 0.0,
            "kind": "base",
        },
        {
            "id": "glob_inc",
            "stage_zh": "倾角平面入射辐射 (GlobInc)",
            "stage_en": "Global Incident in Coll. Plane",
            "unit": "kWh/m²",
            "value": round(glob_inc_kwh_m2, 1),
            "delta_pct": round(transposition_gain_pct, 2),
            "kind": "gain" if transposition_gain_pct >= 0 else "loss",
        },
        {
            "id": "horizon_shading",
            "stage_zh": "远方天际线遮挡损失 (Far Horizon)",
            "stage_en": "Far Horizon Shading",
            "unit": "kWh/m²",
            "value": round(glob_after_hz_kwh_m2, 1),
            "delta_pct": round(-horizon_loss_pct, 2),
            "kind": "loss",
        },
        {
            "id": "near_shading",
            "stage_zh": "近处三维几何遮挡损失 (Near Shadings)",
            "stage_en": "Near Shadings: Irradiance Loss",
            "unit": "kWh/m²",
            "value": round(target_after_sh_kwh_m2, 1),
            "delta_pct": round(-near_shading_loss_pct, 2),
            "kind": "loss",
        },
        {
            "id": "iam_loss",
            "stage_zh": "入射角光学反射损失 (IAM Factor)",
            "stage_en": "IAM Factor on Global",
            "unit": "kWh/m²",
            "value": round(glob_after_iam_kwh_m2, 1),
            "delta_pct": round(-iam_loss_pct, 2),
            "kind": "loss",
        },
        {
            "id": "soiling_loss",
            "stage_zh": "组件表面灰尘遮蔽损失 (Soiling)",
            "stage_en": "Soiling Loss Factor",
            "unit": "kWh/m²",
            "value": round(glob_after_soil_kwh_m2, 1),
            "delta_pct": round(-soiling_pct, 2),
            "kind": "loss",
        },
        {
            "id": "glob_eff",
            "stage_zh": "双面背面增益后有效辐射 (GlobEff)",
            "stage_en": "Effective Irradiance on Collectors",
            "unit": "kWh/m²",
            "value": round(glob_eff_kwh_m2, 1),
            "delta_pct": round(bifacial_gain_pct, 2),
            "kind": "gain" if bifacial_gain_pct > 0 else "subtotal",
        },
        {
            "id": "e_nom",
            "stage_zh": "STC 标准条件阵列标称电量 (E_Nom)",
            "stage_en": "Array Nominal Energy at STC",
            "unit": "kWh",
            "value": round(e_nom_kwh, 0),
            "delta_pct": 0.0,
            "kind": "subtotal",
        },
        {
            "id": "thermal_loss",
            "stage_zh": "光伏组件工作温度损失 (Thermal Loss)",
            "stage_en": "PV Loss due to Temperature",
            "unit": "kWh",
            "value": round(e_after_therm_kwh, 0),
            "delta_pct": round(-thermal_loss_pct, 2),
            "kind": "loss",
        },
        {
            "id": "module_quality",
            "stage_zh": "组件铭牌正公差品质增益 (Module Quality)",
            "stage_en": "Module Quality Loss/Gain",
            "unit": "kWh",
            "value": round(e_after_qual_kwh, 0),
            "delta_pct": round(mod_quality_gain_pct, 2),
            "kind": "gain" if mod_quality_gain_pct >= 0 else "loss",
        },
        {
            "id": "lid_loss",
            "stage_zh": "首年光致衰减损失 (LID)",
            "stage_en": "LID - Light Induced Degradation",
            "unit": "kWh",
            "value": round(e_after_lid_kwh, 0),
            "delta_pct": round(-lid_loss_pct, 2),
            "kind": "loss",
        },
        {
            "id": "mismatch_loss",
            "stage_zh": "组件阵列及阴影二极管电气失配 (Mismatch)",
            "stage_en": "Module Array & Electrical Shading Mismatch",
            "unit": "kWh",
            "value": round(e_after_mismatch_kwh, 0),
            "delta_pct": round(-mismatch_total_pct, 2),
            "kind": "loss",
        },
        {
            "id": "dc_ohmic_loss",
            "stage_zh": "直流侧线缆欧姆热损耗 (DC Ohmic)",
            "stage_en": "Ohmic Wiring Loss (DC)",
            "unit": "kWh",
            "value": round(e_array_kwh, 0),
            "delta_pct": round(-dc_ohmic_loss_pct, 2),
            "kind": "loss",
        },
        {
            "id": "e_array",
            "stage_zh": "阵列最大功率点虚拟电量 (E_Array)",
            "stage_en": "Array Virtual Energy at MPP",
            "unit": "kWh",
            "value": round(e_array_kwh, 0),
            "delta_pct": 0.0,
            "kind": "subtotal",
        },
        {
            "id": "inverter_loss",
            "stage_zh": "逆变器转换及容配比削峰损耗 (Inverter + Clip)",
            "stage_en": "Inverter Loss & Overpower Clipping",
            "unit": "kWh",
            "value": round(e_after_clip_kwh, 0),
            "delta_pct": round(-inverter_combined_loss_pct, 2),
            "kind": "loss",
        },
        {
            "id": "e_grid",
            "stage_zh": "交流线损/箱变/可用率后并网电量 (E_Grid)",
            "stage_en": "Energy Injected into Grid",
            "unit": "kWh",
            "value": round(e_grid_kwh, 0),
            "delta_pct": round(-post_inv_combined_loss_pct, 2),
            "kind": "final",
        },
    ]

    # Monthly Balances Table (Months 1..12 matching PVsyst "Balances and main results")
    months = df.index.month.to_numpy()
    monthly_balances: list[dict[str, Any]] = []
    for m in range(1, 13):
        mask = months == m
        m_gh = float(np.sum(ghi[mask]) / 1000.0)
        m_dh = float(np.sum(dhi[mask]) / 1000.0)
        m_ta = float(np.mean(temp_air[mask])) if np.any(mask) else 20.0
        m_gi = float(np.sum(poa_global[mask]) / 1000.0)
        m_ge = float(np.sum(poa_eff[mask]) / 1000.0)
        m_ea = float(np.sum(e_array_kw[mask]))
        m_eg = float(np.sum(e_grid_kw[mask]))
        m_pr = ((m_eg / max(m_gi * dc_kw, 1e-6)) * 100.0) if dc_kw > 0.0 else 0.0
        monthly_balances.append(
            {
                "month": int(m),
                "glob_hor": round(m_gh, 1),
                "diff_hor": round(m_dh, 1),
                "t_amb": round(m_ta, 1),
                "glob_inc": round(m_gi, 1),
                "glob_eff": round(m_ge, 1),
                "e_array": round(m_ea, 0),
                "e_grid": round(m_eg, 0),
                "pr_pct": round(m_pr, 1),
            }
        )

    optimization_matrix = _compute_optimization_matrix(
        df,
        sun,
        albedo=albedo,
        current_tilt=tilt_deg,
        current_azimuth=azimuth_deg,
        current_specific_yield=specific_yield_kwh_kwp,
        glob_inc_current=glob_inc_kwh_m2,
    )
    sun_path = _compute_sun_path(lat, lon, norm_horizon)
    probabilities = _compute_probabilities(e_grid_kwh, dc_kw)
    live_weather_data = fetch_live_weather(
        lat,
        lon,
        dc_kw=dc_kw,
        ac_kw=ac_kw,
        tilt_deg=tilt_deg,
        azimuth_deg=azimuth_deg,
        offline=offline,
    )

    sub_arrays_summary: list[dict[str, Any]] = []
    if len(sub_plane_evals) >= 1:
        raw_eff_kw_sum = sum(
            float(np.sum(ev["poa_eff"]) / 1000.0) * sa["dc_kw"]
            for sa, ev in sub_plane_evals
        )
        for sa, ev in sub_plane_evals:
            sa_glob_inc = float(np.sum(ev["poa_global"]) / 1000.0)
            sa_glob_eff = float(np.sum(ev["poa_eff"]) / 1000.0)
            sa_trans_pct = ((sa_glob_inc / max(glob_hor_kwh_m2, 1e-6)) - 1.0) * 100.0
            sa_share = (sa_glob_eff * sa["dc_kw"]) / max(raw_eff_kw_sum, 1e-6)
            sa_grid_kwh = e_grid_kwh * sa_share
            sa_spec = sa_grid_kwh / max(sa["dc_kw"], 1e-6)
            sub_arrays_summary.append({
                "name": sa["name"],
                "dc_kw": round(sa["dc_kw"], 2),
                "tilt_deg": round(sa["tilt_deg"], 1),
                "azimuth_deg": round(sa["azimuth_deg"], 1),
                "glob_inc_kwh_m2": round(sa_glob_inc, 1),
                "transposition_gain_pct": round(sa_trans_pct, 2),
                "specific_yield_kwh_kwp": round(sa_spec, 1),
                "e_grid_kwh": round(sa_grid_kwh, 0),
            })

    return {
        "ok": True,
        "weather_metadata": weather_meta,
        "summary": {
            "dc_kw": round(dc_kw, 2),
            "ac_kw": round(ac_kw, 2),
            "dc_ac_ratio": dc_ac_ratio,
            "glob_hor_kwh_m2": round(glob_hor_kwh_m2, 1),
            "diff_hor_kwh_m2": round(diff_hor_kwh_m2, 1),
            "glob_inc_kwh_m2": round(glob_inc_kwh_m2, 1),
            "glob_eff_kwh_m2": round(glob_eff_kwh_m2, 1),
            "e_nom_kwh": round(e_nom_kwh, 0),
            "e_array_kwh": round(e_array_kwh, 0),
            "e_grid_kwh": round(e_grid_kwh, 0),
            "specific_yield_kwh_kwp": round(specific_yield_kwh_kwp, 1),
            "pr_pct": round(pr_pct, 2),
            "transposition_gain_pct": round(transposition_gain_pct, 2),
            "bifacial_gain_pct": round(bifacial_gain_pct, 2),
            "thermal_loss_pct": round(thermal_loss_pct, 2),
            "iam_loss_pct": round(iam_loss_pct, 2),
            "soiling_loss_pct": round(soiling_pct, 2),
            "horizon_loss_pct": round(horizon_loss_pct, 2),
            "shading_optical_loss_pct": round(near_shading_loss_pct, 2),
            "shading_electrical_loss_pct": round(shading_electrical_loss_pct, 2),
            "dc_ohmic_loss_pct": round(dc_ohmic_loss_pct, 2),
            "inverter_eff_loss_pct": round(inverter_eff_loss_pct, 2),
            "clipping_loss_pct": round(inverter_clipping_loss_pct, 2),
            "ac_ohmic_loss_pct": round(ac_ohmic_pct, 2),
            "transformer_loss_pct": round(transformer_loss_pct, 2),
            "unavailability_loss_pct": round(unavailability_loss_pct, 2),
            "total_loss_pct": round(total_loss_pct, 2),
        },
        "waterfall": waterfall,
        "monthly_balances": monthly_balances,
        "optimization_matrix": optimization_matrix,
        "sun_path": sun_path,
        "probabilities": probabilities,
        "live_weather": live_weather_data,
        "sub_arrays_summary": sub_arrays_summary,
    }
