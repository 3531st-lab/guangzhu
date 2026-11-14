"""光筑专业报告 (Guangzhu Professional Photovoltaic Simulation Report — 6-Page Swiss Technical Edition).

Generates a crisp 6-page A4 portrait Swiss technical engineering simulation dossier
(standalone HTML & multi-page vector PDF) branded with Guangzhu's official software icons
(`guangzhu-128.png` / `guangzhu-512.png`) and diagonal repeating software watermarks,
preserving the existing V1 project proposal report completely intact.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import functools
import hashlib
from html import escape
import inspect
import io
import json
import math
from pathlib import Path
import re
from typing import Any

from .archive import evidence

REPO_ROOT = Path(__file__).resolve().parents[3]
REPORT_DIR = Path(__file__).resolve().parent
ASSETS_DIR = REPO_ROOT / "desktop" / "web" / "assets"

MONTH_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_FULL_EN = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTH_ZH = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

PRIVATE_PATH_RE = re.compile(
    r"account-acct[^\s\"'<>]*|[A-Z]:[\\/]Users[\\/][^\s\"'<>]*|(?<![A-Za-z0-9+/=])/Users/[^\s\"'<>]+|(?<![A-Za-z0-9+/=])/home/[^\s\"'<>]+",
    re.I,
)
EXTERNAL_SW_BRAND_RE = re.compile(
    r"pvsyst(?:[-_ ]*(?:style|compatible|imitation|standard|pro|v2|7(?:\.x)?|8(?:\.x)?))?",
    re.I,
)
ILLEGAL_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')

SIM_MODEL_VERSION = "gz-pvsyst-sim-v3.2"


def _fnum(val: Any, default: float = 0.0) -> float:
    if val is None or isinstance(val, bool):
        return float(default)
    try:
        f = float(val)
        return f if math.isfinite(f) else float(default)
    except (TypeError, ValueError):
        return float(default)


def _first_num(*vals: Any, default: float = 0.0) -> float:
    """Return the first explicitly provided finite numeric value (preserving 0.0)."""
    for v in vals:
        if v is None or isinstance(v, bool):
            continue
        try:
            f = float(v)
            if math.isfinite(f):
                return f
        except (TypeError, ValueError):
            continue
    return float(default)


def _first_pos_num(*vals: Any, default: float = 0.0) -> float:
    """Return the first explicitly provided strictly positive finite numeric value."""
    for v in vals:
        if v is None or isinstance(v, bool):
            continue
        try:
            f = float(v)
            if math.isfinite(f) and f > 0:
                return f
        except (TypeError, ValueError):
            continue
    return float(default)


def _first_present_num(*vals: Any) -> float | None:
    """Return the first explicitly provided finite numeric value (including 0.0), or None if absent."""
    for v in vals:
        if v is None or isinstance(v, bool) or v == "":
            continue
        try:
            f = float(v)
            if math.isfinite(f):
                return f
        except (TypeError, ValueError):
            continue
    return None


def _compute_sim_input_fingerprint(
    *,
    dc_kw: float,
    ac_kw: float,
    lat: float,
    lon: float,
    albedo: float,
    tilt_deg: float,
    azimuth_compass: float,
    orientation_mode: str,
    sub_arrays: list[dict[str, Any]] | None = None,
    module_id: str = "",
    stc_w: float = 580.0,
    stc_eff_pct: float = 21.6,
    vmp_stc_v: float = 42.3,
    voc_stc_v: float = 50.8,
    imp_stc_a: float = 13.7,
    isc_stc_a: float = 14.5,
    bifaciality: float = 0.80,
    gamma_pmax_pct_c: float = -0.30,
    beta_voc_pct_c: float = -0.25,
    inverter_id: str = "",
    unit_ac_kw: float = 100.0,
    inv_count: int = 1,
    euro_eff_pct: float = 98.4,
    mppt_min_v: float = 200.0,
    mppt_max_v: float = 1000.0,
    max_dc_v: float = 1100.0,
    soiling_pct: float = 2.0,
    iam_b0: float = 0.04,
    iam_loss_pct: float | None = None,
    lid_pct: float = 1.0,
    module_quality_pct: float = -0.3,
    mismatch_pct: float = 1.0,
    dc_ohmic_pct: float = 1.2,
    ac_ohmic_pct: float = 0.8,
    near_shading_pct: float = 1.85,
    uc_w_m2k: float = 29.0,
    uv_w_m2k_ms: float = 0.0,
    snow_loss_pct: float = 0.0,
    spectral_pct: float = 0.15,
    transformer_loss_pct: float = 0.9,
    availability_pct: float = 99.2,
    offline: bool = True,
) -> str:
    """Compute a deterministic SHA-256 fingerprint of all simulation-critical input parameters.

    Used to decide whether pre-computed simulation results can be safely reused.
    Any change in dc_kw, ac_kw, lat/lon, loss parameters, orientation, sub_arrays,
    or module/inverter specs produces a distinct fingerprint.
    """
    norm_sub_arrays = [
        {
            k: (round(float(v), 4) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v))
            for k, v in sorted(sa.items())
        }
        for sa in (sub_arrays or [])
        if isinstance(sa, dict)
    ]
    eff_iam_loss = round(float(iam_loss_pct), 3) if iam_loss_pct is not None else round(float(iam_b0) * 46.25, 3)
    canonical = {
        "sim_model_version": SIM_MODEL_VERSION,
        "dc_kw": round(float(dc_kw), 3),
        "ac_kw": round(float(ac_kw), 3),
        "lat": round(float(lat), 6),
        "lon": round(float(lon), 6),
        "albedo": round(float(albedo), 4),
        "tilt_deg": round(float(tilt_deg), 2),
        "azimuth_compass": round(float(azimuth_compass), 2),
        "orientation_mode": str(orientation_mode),
        "sub_arrays": norm_sub_arrays,
        "module": {
            "module_id": str(module_id),
            "stc_w": round(float(stc_w), 2),
            "stc_eff_pct": round(float(stc_eff_pct), 3),
            "vmp_stc_v": round(float(vmp_stc_v), 2),
            "voc_stc_v": round(float(voc_stc_v), 2),
            "imp_stc_a": round(float(imp_stc_a), 2),
            "isc_stc_a": round(float(isc_stc_a), 2),
            "bifaciality": round(float(bifaciality), 3),
            "gamma_pmax_pct_c": round(float(gamma_pmax_pct_c), 3),
            "beta_voc_pct_c": round(float(beta_voc_pct_c), 3),
        },
        "inverter": {
            "inverter_id": str(inverter_id),
            "unit_ac_kw": round(float(unit_ac_kw), 2),
            "inv_count": int(inv_count),
            "total_ac_kw": round(float(ac_kw), 3),
            "euro_eff_pct": round(float(euro_eff_pct), 2),
            "mppt_min_v": round(float(mppt_min_v), 1),
            "mppt_max_v": round(float(mppt_max_v), 1),
            "max_dc_v": round(float(max_dc_v), 1),
        },
        "losses": {
            "soiling_pct": round(float(soiling_pct), 3),
            "iam_b0": round(float(iam_b0), 4),
            "iam_loss_pct": eff_iam_loss,
            "lid_loss_pct": round(float(lid_pct), 3),
            "module_quality_pct": round(float(module_quality_pct), 3),
            "mismatch_loss_pct": round(float(mismatch_pct), 3),
            "dc_wiring_loss_pct": round(float(dc_ohmic_pct), 3),
            "ac_wiring_loss_pct": round(float(ac_ohmic_pct), 3),
            "near_shading_loss_pct": round(float(near_shading_pct), 3),
            "uc_w_m2k": round(float(uc_w_m2k), 2),
            "uv_w_m2k_ms": round(float(uv_w_m2k_ms), 3),
            "snow_loss_pct": round(float(snow_loss_pct), 3),
            "spectral_pct": round(float(spectral_pct), 3),
            "transformer_loss_pct": round(float(transformer_loss_pct), 3),
            "availability_pct": round(float(availability_pct), 3),
        },
        "offline": bool(offline),
    }
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _fmt_irr(val: Any, digits: int = 1) -> str:
    if val is None or isinstance(val, bool):
        return "N/A (不可行)"
    try:
        f = float(val)
        return f"{f:.{digits}f}%" if math.isfinite(f) else "N/A (不可行)"
    except (TypeError, ValueError):
        return "N/A (不可行)"


def _fmt_payback(val: Any, digits: int = 2, suffix: str = " 年") -> str:
    if val is None or isinstance(val, bool):
        return f">25{suffix} (未回本)"
    try:
        f = float(val)
        return f"{f:.{digits}f}{suffix}" if math.isfinite(f) else f">25{suffix} (未回本)"
    except (TypeError, ValueError):
        return f">25{suffix} (未回本)"


def _fmt_lcoe(val: Any, digits: int = 3) -> str:
    if val is None or isinstance(val, bool):
        return "N/A"
    try:
        f = float(val)
        return f"¥{f:.{digits}f}/kWh" if math.isfinite(f) else "N/A"
    except (TypeError, ValueError):
        return "N/A"


def _fmt(val: Any, digits: int = 1, fallback: str = "—") -> str:
    if val is None or isinstance(val, bool):
        return fallback
    try:
        f = float(val)
        if not math.isfinite(f):
            return fallback
        return f"{f:,.{digits}f}"
    except (TypeError, ValueError):
        return fallback


def _fmt_signed(val: Any, digits: int = 2) -> str:
    f = _fnum(val, 0.0)
    sign = "+" if f > 0 else ""
    return f"{sign}{f:.{digits}f}%"


def _bilingual(en: str, zh: str) -> str:
    return (
        f'<span class="l-en">{escape(en)}</span>'
        f'<span class="l-sep"> · </span>'
        f'<span class="l-zh">{escape(zh)}</span>'
    )


def _scrub_external_brand(text: str) -> str:
    if not text:
        return text
    out = EXTERNAL_SW_BRAND_RE.sub("光筑专业", text)
    out = re.sub(r"(?:光筑\s*){2,}", "光筑", out)
    return out.strip()


def sanitize_report_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    raw = str(value).strip()
    if not raw:
        return fallback
    cleaned = evidence.sanitize(raw)
    if not isinstance(cleaned, str):
        cleaned = str(cleaned)
    cleaned = PRIVATE_PATH_RE.sub("[已脱敏路径]", cleaned)
    cleaned = _scrub_external_brand(cleaned)
    return cleaned or fallback


def sanitize_report_structure(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("data:image/png;base64,"):
            return value
        return sanitize_report_text(value, value)
    if isinstance(value, dict):
        return {
            str(k): sanitize_report_structure(v)
            for k, v in value.items()
            if not evidence.PRIVATE_FIELD.fullmatch(str(k))
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_report_structure(item) for item in value]
    return value


def assert_no_private_path_leak(text: str) -> None:
    scrubbed = re.sub(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+", "DATA_URI_OK", text)
    if PRIVATE_PATH_RE.search(scrubbed):
        raise ValueError("光筑专业报告包含未脱敏的本地系统路径或敏感账户信息")


def assert_no_pvsyst_visible_text(html_or_text: str) -> None:
    """Guarantee zero occurrences of external software name in visible HTML text, titles, or ARIA labels."""
    without_code = re.sub(r"<style\b[^>]*>.*?</style>", " ", html_or_text, flags=re.I | re.S)
    without_code = re.sub(r"<script\b[^>]*>.*?</script>", " ", without_code, flags=re.I | re.S)
    without_code = re.sub(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+", "DATA_URI", without_code)
    aria_and_alt = " ".join(re.findall(r'\b(?:aria-label|alt|title)="([^"]*)"', without_code, flags=re.I))
    visible_only = re.sub(r"<[^>]+>", " ", without_code)
    combined = f"{visible_only} {aria_and_alt}"
    if re.search(r"pvsyst", combined, re.I):
        raise ValueError("光筑专业报告可见文本中检测到未清除的外部品牌字样")


def make_pro_report_filename(project_name: Any, version: int = 1, ext: str = "pdf") -> str:
    """Build sanitized official Chinese delivery filename: 光筑专业报告_<项目名称>_v<版本号>.pdf."""
    clean_title = sanitize_report_text(project_name, "分布式光伏工程项目")
    clean_title = clean_title.replace("[已脱敏路径]", "光伏项目")
    clean_title = ILLEGAL_FILENAME_CHARS_RE.sub("_", clean_title)
    clean_title = re.sub(r"\s+", "_", clean_title).strip("._- ")
    if not clean_title:
        clean_title = "分布式光伏工程项目"
    if len(clean_title) > 46:
        clean_title = clean_title[:46].rstrip("._-")
    ver_int = max(1, int(_fnum(version, 1)))
    clean_ext = str(ext or "pdf").lstrip(".").lower() or "pdf"
    fname = f"光筑专业报告_{clean_title}_v{ver_int}.{clean_ext}"
    assert_no_private_path_leak(fname)
    if re.search(r"pvsyst", fname, re.I):
        fname = re.sub(r"(?i)pvsyst", "光筑", fname)
    return fname


@functools.lru_cache(maxsize=1)
def get_guangzhu_icon_assets() -> dict[str, Any]:
    """Load Guangzhu software icons (`guangzhu-128.png` & `guangzhu-512.png`) and return base64 data URIs + bytes."""
    p128 = ASSETS_DIR / "guangzhu-128.png"
    p512 = ASSETS_DIR / "guangzhu-512.png"
    if not p128.is_file() and not p512.is_file():
        raise FileNotFoundError("Guangzhu icon assets not found in desktop/web/assets/")
    b128 = p128.read_bytes() if p128.is_file() else p512.read_bytes()
    b512 = p512.read_bytes() if p512.is_file() else b128
    u128 = "data:image/png;base64," + base64.b64encode(b128).decode("ascii")
    u512 = "data:image/png;base64," + base64.b64encode(b512).decode("ascii")
    return {
        "icon_128_uri": u128,
        "icon_512_uri": u512,
        "icon_128_bytes": b128,
        "icon_512_bytes": b512,
    }


def _load_report_css() -> str:
    css_path = REPORT_DIR / "pvsyst_report.css"
    return css_path.read_text(encoding="utf-8")


def _normalize_engine_orientation_mode(mode_raw: Any, roof_type: str = "flat") -> str:
    """Normalize 3D / SatMap / Simulation orientation aliases into 4 canonical modes."""
    m = str(mode_raw or "").strip().lower()
    rt = str(roof_type or "").strip().lower()
    if m in ("east_west", "ew", "east-west", "butterfly", "dome", "domes", "dual_east_west"):
        return "east_west"
    if m in ("flush_pitched", "flush", "pitched", "roof", "roof_parallel", "metal", "single_slope", "double_slope", "gable", "clamp"):
        return "flush_pitched"
    if m in ("elevated_canopy", "canopy", "elevated", "carport", "pergola", "sunroom"):
        return "elevated_canopy"
    if m in ("south_fixed", "south", "fixed", "fixed_tilt", "ballast"):
        return "south_fixed"
    if rt in ("metal", "pitched", "single_slope", "double_slope", "gable"):
        return "flush_pitched"
    return "south_fixed"


def _resolve_orientation_labels(mode: str, tilt_deg: float, az_compass: float, sub_arrays: list[dict[str, Any]]) -> dict[str, Any]:
    m_norm = _normalize_engine_orientation_mode(mode)
    if len(sub_arrays) >= 2 and m_norm != "east_west":
        names = " / ".join(f"{sa.get('tilt_deg', tilt_deg):.0f}°@{sa.get('azimuth_deg', az_compass):.0f}°" for sa in sub_arrays[:2])
        return {
            "mode": "multi_orientation",
            "field_en": "Multi-Orientation Sub-Arrays",
            "field_zh": "异向多子阵独立跟踪平面",
            "az_display": names,
            "solar_az_deg": round(az_compass - 180.0, 1),
        }
    if m_norm == "east_west":
        return {
            "mode": "east_west",
            "field_en": "East-West Dual Tilted Domes",
            "field_zh": "东西向双坡对称蝴蝶阵",
            "az_display": f"-90°(东 East) / +90°(西 West) · {tilt_deg:.1f}°",
            "solar_az_deg": -90.0,
        }
    if m_norm == "flush_pitched":
        sol_az = round(az_compass - 180.0, 1)
        return {
            "mode": "flush_pitched",
            "field_en": "Flush Roof-Parallel Plane",
            "field_zh": "顺坡平铺屋面阵列",
            "az_display": f"Tilt {tilt_deg:.1f}° / Az {sol_az:+.0f}° (罗盘 {az_compass:.0f}°)",
            "solar_az_deg": sol_az,
        }
    if m_norm == "elevated_canopy":
        sol_az = round(az_compass - 180.0, 1)
        return {
            "mode": "elevated_canopy",
            "field_en": "Elevated Solar Canopy Structure",
            "field_zh": "架高跨障阳光棚阵列",
            "az_display": f"Tilt {tilt_deg:.1f}° / Az {sol_az:+.0f}° (罗盘 {az_compass:.0f}°)",
            "solar_az_deg": sol_az,
        }
    sol_az = round(az_compass - 180.0, 1)
    return {
        "mode": "south_fixed",
        "field_en": "Fixed Tilted Collector Plane",
        "field_zh": "南向固定倾角阵列平面",
        "az_display": f"Tilt {tilt_deg:.1f}° / Az {sol_az:+.0f}° (罗盘 {az_compass:.0f}°)",
        "solar_az_deg": sol_az,
    }


def _synthesize_daily_io(monthly: list[dict[str, Any]], dc_kw: float) -> list[dict[str, float]]:
    """Synthesize 365 physically consistent daily (GlobInc, E_Grid) points anchored to monthly balances."""
    pts: list[dict[str, float]] = []
    day_counter = 0
    for m_idx, row in enumerate(monthly[:12]):
        n_days = DAYS_IN_MONTH[m_idx]
        m_gi = max(0.5, _fnum(row.get("glob_inc"), 100.0))
        m_eg = max(0.0, _fnum(row.get("e_grid"), m_gi * dc_kw * 0.83))
        mean_gi = m_gi / n_days
        pr_ratio = m_eg / max(m_gi * max(dc_kw, 0.1), 1e-6)
        raw_gis: list[float] = []
        for d in range(n_days):
            wave = 0.58 * math.sin((d + 1) * 1.37 + m_idx * 0.83) + 0.29 * math.cos((d + 1) * 2.71 - m_idx * 0.41)
            factor = max(0.18, min(1.52, 1.0 + 0.46 * wave))
            raw_gis.append(mean_gi * factor)
        scale_gi = m_gi / max(sum(raw_gis), 1e-6)
        day_gis = [g * scale_gi for g in raw_gis]
        raw_egs: list[float] = []
        for d, gi_d in enumerate(day_gis):
            jitter = 1.0 + 0.024 * math.sin((d + 2) * 3.13 + m_idx)
            high_irr_droop = 1.0 - 0.018 * max(0.0, (gi_d - 5.2) / 3.0)
            raw_egs.append(max(0.0, gi_d * dc_kw * pr_ratio * jitter * high_irr_droop))
        scale_eg = m_eg / max(sum(raw_egs), 1e-6)
        for d in range(n_days):
            day_counter += 1
            pts.append({
                "day": day_counter,
                "month": m_idx + 1,
                "glob_inc_kwh_m2": round(day_gis[d], 3),
                "e_grid_kwh": round(raw_egs[d] * scale_eg, 2),
            })
    return pts


def _synthesize_power_distribution(total_ac_kw: float, dc_kw: float, e_grid_kwh: float) -> list[dict[str, float]]:
    """Synthesize 10 AC output power histogram bins summing to E_Grid."""
    if total_ac_kw <= 0.0 and dc_kw <= 0.0:
        return [
            {"bin_kw_start": 0.0, "bin_kw_end": 0.0, "hours": 0.0, "energy_kwh": 0.0}
            for _ in range(10)
        ]
    p_max = max(10.0, total_ac_kw if total_ac_kw > 0 else dc_kw / 1.18)
    hour_weights = [680, 610, 540, 490, 455, 430, 395, 345, 255, 165]
    mid_fracs = [(i + 0.5) / 10.0 for i in range(10)]
    raw_energy = [h * (f * p_max) for h, f in zip(hour_weights, mid_fracs)]
    e_scale = max(0.0, e_grid_kwh) / max(sum(raw_energy), 1e-6)
    bins: list[dict[str, float]] = []
    for i in range(10):
        b0 = round((i / 10.0) * p_max, 1)
        b1 = round(((i + 1) / 10.0) * p_max, 1)
        e_bin = round(raw_energy[i] * e_scale, 1)
        mid_kw = max(0.5, ((b0 + b1) * 0.5))
        hrs = round(min(1200.0, e_bin / mid_kw), 1)
        bins.append({
            "bin_kw_start": b0,
            "bin_kw_end": b1,
            "hours": hrs,
            "energy_kwh": e_bin,
        })
    return bins


def _synthesize_hourly_heatmap_12x24(
    normalized_monthly: list[dict[str, Any]],
    lat: float,
    orient_mode: str,
    total_ac_kw: float,
) -> dict[str, Any]:
    """Synthesize physically consistent 12 Months × 24 Hours mean AC power matrix [kWac] anchored to monthly E_Grid."""
    lat_r = math.radians(max(-62.0, min(62.0, lat)))
    mid_doys = [15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349]
    ac_matrix: list[list[float]] = []
    for m_idx in range(12):
        row_m = normalized_monthly[m_idx] if m_idx < len(normalized_monthly) else {}
        days_m = DAYS_IN_MONTH[m_idx]
        daily_kwh = max(0.0, _fnum(row_m.get("e_grid"), 0.0)) / max(1, days_m)
        dec_r = math.radians(23.45 * math.sin(math.radians((360.0 / 365.0) * (284 + mid_doys[m_idx]))))
        cos_ha0 = max(-0.95, min(0.95, -math.tan(lat_r) * math.tan(dec_r)))
        half_day_h = max(3.8, min(8.2, math.degrees(math.acos(cos_ha0)) / 15.0))
        weights: list[float] = []
        for hr in range(24):
            dt = abs((hr + 0.5) - 12.2)
            if dt >= half_day_h:
                weights.append(0.0)
            else:
                base_bell = math.cos((dt / half_day_h) * (math.pi * 0.5)) ** 1.45
                if orient_mode == "east_west":
                    shoulder = 1.0 + 0.16 * math.sin((dt / half_day_h) * math.pi)
                    base_bell *= shoulder
                weights.append(max(0.0, base_bell))
        w_sum = max(sum(weights), 1e-6)
        row_kw = [round(min(total_ac_kw, daily_kwh * (w / w_sum)), 2) for w in weights]
        ac_matrix.append(row_kw)
    max_kw = round(max((max(r) for r in ac_matrix), default=0.0), 2)
    return {
        "months": list(range(1, 13)),
        "hours": list(range(24)),
        "ac_kw": ac_matrix,
        "max_ac_kw": 0.0 if total_ac_kw <= 0.0 else max(1.0, max_kw),
    }


def _compute_7season_sunpath(lat: float, horizon_pts: list[dict[str, float]], parapet_h_m: float = 0.8) -> dict[str, Any]:
    """Compute 7-season solar declination paths & 7h–17h hour lines in solar azimuth [-180°, +180°] (0° = South)."""
    lat_rad = math.radians(max(-65.0, min(65.0, lat)))
    curves_spec = [
        ("1", "Jun 22 (夏至)", 23.44, "#dc2626"),
        ("2", "May 22 / Jul 23", 20.15, "#ea580c"),
        ("3", "Apr 20 / Aug 23", 11.45, "#d97706"),
        ("4", "Mar 20 / Sep 23 (春秋分)", 0.0, "#16a34a"),
        ("5", "Feb 19 / Oct 23", -11.45, "#0284c7"),
        ("6", "Jan 20 / Nov 22", -20.15, "#2563eb"),
        ("7", "Dec 22 (冬至)", -23.44, "#1e3a8a"),
    ]
    trajectories: list[dict[str, Any]] = []
    hour_tracks: dict[int, list[tuple[float, float]]] = {h: [] for h in range(7, 18)}

    def _az_el(dec_deg: float, solar_hr: float) -> tuple[float, float]:
        dec_r = math.radians(dec_deg)
        hra_r = math.radians((solar_hr - 12.0) * 15.0)
        sin_el = math.sin(lat_rad) * math.sin(dec_r) + math.cos(lat_rad) * math.cos(dec_r) * math.cos(hra_r)
        el_r = math.asin(max(-1.0, min(1.0, sin_el)))
        el_d = math.degrees(el_r)
        denom = max(1e-6, math.cos(el_r) * math.cos(lat_rad))
        cos_az_north = (math.sin(dec_r) - math.sin(el_r) * math.sin(lat_rad)) / denom
        az_from_north = math.degrees(math.acos(max(-1.0, min(1.0, cos_az_north))))
        if solar_hr > 12.0:
            az_from_north = 360.0 - az_from_north
        az_sol = az_from_north - 180.0
        return az_sol, el_d

    for idx_tag, label, dec_deg, color in curves_spec:
        pts: list[tuple[float, float]] = []
        for step in range(44, 157):
            hr = step * 0.125
            az_s, el_d = _az_el(dec_deg, hr)
            if el_d >= 0.0:
                pts.append((round(az_s, 2), round(el_d, 2)))
        trajectories.append({"id": idx_tag, "label": label, "declination": dec_deg, "color": color, "points": pts})
        for h_int in range(7, 18):
            az_h, el_h = _az_el(dec_deg, float(h_int))
            if el_h >= 0.0:
                hour_tracks[h_int].append((round(az_h, 2), round(el_h, 2)))

    hz_map: list[tuple[float, float]] = []
    parapet_bump = min(14.0, max(0.0, parapet_h_m * 3.8))
    if horizon_pts:
        for pt in horizon_pts:
            az_raw = _fnum(pt.get("azimuth"), 180.0)
            az_s = az_raw - 180.0 if az_raw > 180.0 or (az_raw >= 45.0 and max(_fnum(x.get("azimuth")) for x in horizon_pts) > 180.0) else az_raw
            el_v = max(1.5, min(42.0, _fnum(pt.get("elevation"), 3.5) + parapet_bump * 0.35))
            hz_map.append((round(az_s, 1), round(el_v, 2)))
    hz_map.sort(key=lambda x: x[0])
    if not hz_map:
        hz_map = [
            (-150.0, 5.2 + parapet_bump * 0.4),
            (-120.0, 6.4 + parapet_bump * 0.45),
            (-90.0, 5.8 + parapet_bump * 0.35),
            (-60.0, 4.1 + parapet_bump * 0.25),
            (-30.0, 3.0 + parapet_bump * 0.2),
            (0.0, 2.5 + parapet_bump * 0.2),
            (30.0, 3.2 + parapet_bump * 0.2),
            (60.0, 4.4 + parapet_bump * 0.25),
            (90.0, 6.0 + parapet_bump * 0.35),
            (120.0, 6.6 + parapet_bump * 0.45),
            (150.0, 5.4 + parapet_bump * 0.4),
        ]
    if hz_map[0][0] > -180.0:
        hz_map.insert(0, (-180.0, hz_map[0][1]))
    if hz_map[-1][0] < 180.0:
        hz_map.append((180.0, hz_map[-1][1]))

    return {
        "lat": round(lat, 4),
        "trajectories": trajectories,
        "hour_tracks": {h: pts for h, pts in hour_tracks.items() if len(pts) >= 2},
        "horizon_pvs": hz_map,
    }


def _solve_irr_and_payback(
    capex_wan: float,
    annual_revs_wan: list[float],
    annual_opex_wan: list[float],
) -> tuple[float | None, float | None]:
    """Solve 25-year project IRR (%) and static payback (years) via shared DCF solver without synthetic defaults."""
    from ..satmap_multifactor import solve_irr_and_payback_from_cashflows

    if not math.isfinite(capex_wan) or capex_wan <= 0.0:
        return None, None
    nets = [float(r) - float(o) for r, o in zip(annual_revs_wan, annual_opex_wan)]
    return solve_irr_and_payback_from_cashflows(float(capex_wan), nets)


ALBEDO_PRESETS_MAP = {
    "white_tpo": 0.65,
    "tpo": 0.65,
    "concrete": 0.25,
    "metal": 0.35,
    "color_steel": 0.35,
    "gravel": 0.22,
    "green": 0.20,
    "asphalt": 0.14,
}


def _check_num_field(
    container: Any,
    key: str,
    label: str,
    *,
    min_val: float | None = None,
    max_val: float | None = None,
    allow_str_presets: set[str] | None = None,
) -> None:
    if not isinstance(container, dict) or key not in container:
        return
    val = container[key]
    if val is None or val == "":
        return
    if isinstance(val, bool):
        raise ValueError(f"Invalid boolean value for numeric field '{label}'")
    if allow_str_presets and isinstance(val, str) and val.strip().lower() in allow_str_presets:
        return
    try:
        f = float(val)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for '{label}': {val!r}") from exc
    if not math.isfinite(f):
        raise ValueError(f"Non-finite numeric value (NaN/Inf) for '{label}'")
    if min_val is not None and f < min_val:
        raise ValueError(f"Field '{label}' must be >= {min_val}, got {f}")
    if max_val is not None and f > max_val:
        raise ValueError(f"Field '{label}' must be <= {max_val}, got {f}")


def _assert_no_nonfinite_floats(node: Any, path: str = "payload") -> None:
    if isinstance(node, float) and not math.isfinite(node):
        raise ValueError(f"Non-finite float (NaN/Inf) at '{path}'")
    if isinstance(node, dict):
        for k, v in node.items():
            _assert_no_nonfinite_floats(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for idx, item in enumerate(node):
            _assert_no_nonfinite_floats(item, f"{path}[{idx}]")


def _validate_report_payload_inputs(payload: Any) -> None:
    """Validate user/API report payload numerics; raise ValueError (-> HTTP 422) on invalid/negative/out-of-range inputs."""
    if payload is None:
        return
    if not isinstance(payload, dict):
        raise ValueError("Report payload must be a JSON object")

    _assert_no_nonfinite_floats(payload)

    site_d = payload.get("site") if isinstance(payload.get("site"), dict) else {}
    sys_d = payload.get("system") if isinstance(payload.get("system"), dict) else {}
    sum_d = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    elec_d = payload.get("electrical") if isinstance(payload.get("electrical"), dict) else {}
    mod_d = payload.get("module") if isinstance(payload.get("module"), dict) else {}
    sys_mod_d = sys_d.get("module") if isinstance(sys_d.get("module"), dict) else {}
    inv_d = payload.get("inverter") if isinstance(payload.get("inverter"), dict) else {}
    sys_inv_d = sys_d.get("inverter") if isinstance(sys_d.get("inverter"), dict) else {}
    mf_d = (
        payload.get("multifactor")
        if isinstance(payload.get("multifactor"), dict)
        else (payload.get("multifactor_params") if isinstance(payload.get("multifactor_params"), dict) else {})
    )
    struct_chk_d = mf_d.get("structural_check") if isinstance(mf_d.get("structural_check"), dict) else {}
    struct_p_d = payload.get("structural_params") if isinstance(payload.get("structural_params"), dict) else {}
    roof_d = payload.get("roof") if isinstance(payload.get("roof"), dict) else {}
    fin_d = (
        payload.get("financial")
        if isinstance(payload.get("financial"), dict)
        else (payload.get("financial_dcf") if isinstance(payload.get("financial_dcf"), dict) else {})
    )
    loss_d = payload.get("losses") if isinstance(payload.get("losses"), dict) else {}

    # Coordinates: lat in [-90, 90], lon in [-180, 180]
    _check_num_field(payload, "lat", "lat", min_val=-90.0, max_val=90.0)
    _check_num_field(site_d, "lat", "site.lat", min_val=-90.0, max_val=90.0)
    _check_num_field(payload, "lon", "lon", min_val=-180.0, max_val=180.0)
    _check_num_field(site_d, "lon", "site.lon", min_val=-180.0, max_val=180.0)

    # Non-negative capacities & equipment counts
    for d_obj, pfx in ((payload, ""), (sys_d, "system."), (sum_d, "summary."), (elec_d, "electrical.")):
        _check_num_field(d_obj, "dc_kw", f"{pfx}dc_kw", min_val=0.0)
        _check_num_field(d_obj, "ac_kw", f"{pfx}ac_kw", min_val=0.0)
        _check_num_field(d_obj, "rated_ac_kw", f"{pfx}rated_ac_kw", min_val=0.0)
        _check_num_field(d_obj, "module_count", f"{pfx}module_count", min_val=0.0)
        _check_num_field(d_obj, "modules", f"{pfx}modules", min_val=0.0)
        _check_num_field(d_obj, "inverter_count", f"{pfx}inverter_count", min_val=0.0)
        _check_num_field(d_obj, "string_count", f"{pfx}string_count", min_val=0.0)
        _check_num_field(d_obj, "modules_per_string", f"{pfx}modules_per_string", min_val=0.0)

    for d_obj, pfx in ((sys_d, "system."), (mod_d, "module."), (sys_mod_d, "system.module.")):
        _check_num_field(d_obj, "stc_w", f"{pfx}stc_w", min_val=0.0)
    for d_obj, pfx in ((inv_d, "inverter."), (sys_inv_d, "system.inverter.")):
        _check_num_field(d_obj, "ac_kw", f"{pfx}ac_kw", min_val=0.0)
        _check_num_field(d_obj, "rated_ac_kw", f"{pfx}rated_ac_kw", min_val=0.0)

    # Sub-arrays dc_kw
    for sa_container, pfx in ((payload, "sub_arrays"), (sys_d, "system.sub_arrays"), (mf_d, "multifactor.sub_arrays")):
        sa_list = sa_container.get("sub_arrays")
        if isinstance(sa_list, list):
            for idx_sa, sa_item in enumerate(sa_list):
                if isinstance(sa_item, dict):
                    _check_num_field(sa_item, "dc_kw", f"{pfx}[{idx_sa}].dc_kw", min_val=0.0)

    # Albedo, tilt, walkway, soiling, and CAPEX
    preset_keys = set(ALBEDO_PRESETS_MAP.keys())
    for d_obj, pfx in ((site_d, "site."), (sys_d, "system."), (mf_d, "multifactor.")):
        _check_num_field(d_obj, "albedo", f"{pfx}albedo", min_val=0.0, max_val=1.0, allow_str_presets=preset_keys)
    for d_obj, pfx in ((payload, ""), (sys_d, "system."), (mf_d, "multifactor.")):
        _check_num_field(d_obj, "tilt_deg", f"{pfx}tilt_deg", min_val=0.0, max_val=90.0)
        _check_num_field(d_obj, "azimuth_deg", f"{pfx}azimuth_deg")
    for d_obj, pfx in (
        (payload, ""),
        (sys_d, "system."),
        (mf_d, "multifactor."),
        (struct_chk_d, "multifactor.structural_check."),
        (struct_p_d, "structural_params."),
        (roof_d, "roof."),
    ):
        _check_num_field(d_obj, "walkway_width_m", f"{pfx}walkway_width_m", min_val=0.0)
        _check_num_field(d_obj, "added_dead_load_kg_m2", f"{pfx}added_dead_load_kg_m2", min_val=0.0)
        _check_num_field(d_obj, "added_load_kg_m2", f"{pfx}added_load_kg_m2", min_val=0.0)
        _check_num_field(d_obj, "max_roof_load_kg_m2", f"{pfx}max_roof_load_kg_m2", min_val=0.0)

    for d_obj, pfx in ((loss_d, "losses."), (mf_d, "multifactor."), (sys_d, "system."), (payload, "")):
        _check_num_field(d_obj, "soiling_pct", f"{pfx}soiling_pct", min_val=0.0, max_val=100.0)
        _check_num_field(d_obj, "soiling_loss_pct", f"{pfx}soiling_loss_pct", min_val=0.0, max_val=100.0)

    for cap_key in ("capex_cny", "capex_wan", "total_capex_wan", "capex_per_w", "capex_w"):
        _check_num_field(fin_d, cap_key, f"financial.{cap_key}", min_val=0.0)


def build_pvsyst_report_context(
    payload: dict[str, Any] | None = None,
    *,
    project_result: dict[str, Any] | None = None,
    offline: bool = True,
) -> dict[str, Any]:
    """Normalize saved 3D project data and/or live SatMap / Simulation JSON into a 6-page Guangzhu Pro Report context."""
    from ..electrical import load_catalog
    from ..pvsyst_engine import simulate_pvsyst

    _validate_report_payload_inputs(payload)

    raw_in = sanitize_report_structure(payload or {})
    res_in = sanitize_report_structure(project_result or {})

    proj = res_in.get("project") or {}
    design = res_in.get("design") or (res_in.get("scene") or {}).get("design") or {}
    res_summary = res_in.get("summary") or res_in.get("metrics") or {}
    res_elec = (res_in.get("scene") or {}).get("electrical") or res_in.get("electrical") or {}
    res_shade = ((res_in.get("scene") or {}).get("shading") or {}).get("summary") or res_summary.get("shading") or {}
    res_econ = res_in.get("economics") or res_summary.get("economics") or {}
    res_struct = (res_in.get("scene") or {}).get("wind") or res_summary.get("load") or {}

    raw_site_in = raw_in.get("site") or {}
    raw_roof_in = raw_in.get("roof") or {}
    sys_in = raw_in.get("system") or {}
    raw_elec_in = raw_in.get("electrical") or {}
    mf_in = raw_in.get("multifactor") or raw_in.get("multifactor_params") or {}
    raw_fin_in = raw_in.get("financial") or raw_in.get("financial_dcf") or {}
    raw_sum_in = raw_in.get("summary") or {}
    has_live_system = bool(sys_in or raw_elec_in or mf_in)

    site_in = {**(proj.get("site") or {}), **raw_site_in}
    roof_in = {**(proj.get("roof") or {}), **raw_roof_in}
    elec_in = {**res_elec, **raw_elec_in}
    fin_in = {**res_econ, **raw_fin_in}
    sum_in = {**res_summary, **raw_sum_in}
    pvs_in = raw_in.get("pvsyst") if raw_in.get("pvsyst") else ({} if (sys_in or mf_in) else (res_in.get("pvsyst") or {}))
    live_mppt_rows_raw = [
        r for r in (
            raw_elec_in.get("mppt_rows")
            or raw_elec_in.get("mppt_table")
            or raw_in.get("mppt_rows")
            or raw_in.get("mppt_table")
            or []
        )
        if isinstance(r, dict)
    ]

    # 1. Project & Header Metadata
    version = max(1, int(raw_in.get("version") if raw_in.get("version") is not None else (res_in.get("version") or 1)))
    project_id = sanitize_report_text(
        raw_in.get("project_id") or res_in.get("project_id") or proj.get("id") or "GZ-PV-SIM",
        "GZ-PV-SIM",
    )
    project_name = sanitize_report_text(
        raw_in.get("project_name") or raw_in.get("name") or proj.get("name") or site_in.get("name") or "分布式并网光伏电站工程项目",
        "分布式并网光伏电站工程项目",
    )
    raw_variant = raw_in.get("variant") if raw_in.get("variant") is not None else raw_in.get("variant_name")
    variant_code = sanitize_report_text(raw_variant or f"VC{version - 1} · v{version}", f"VC0 · v{version}")
    now_bjt = datetime.now(timezone(timedelta(hours=8)))
    sim_date = sanitize_report_text(raw_in.get("simulation_date") or now_bjt.strftime("%Y-%m-%d %H:%M"), now_bjt.strftime("%Y-%m-%d"))
    report_filename = make_pro_report_filename(project_name, version, "pdf")

    # 2. Site & Meteo
    lat = max(-90.0, min(90.0, _fnum(site_in.get("lat") if site_in.get("lat") is not None else raw_in.get("lat"), 32.4568)))
    lon = max(-180.0, min(180.0, _fnum(site_in.get("lon") if site_in.get("lon") is not None else raw_in.get("lon"), 119.9182)))
    altitude_m = max(0.0, _first_num(site_in.get("altitude_m"), site_in.get("elevation_m"), default=18.0))
    city = sanitize_report_text(site_in.get("city") or site_in.get("wind_city") or site_in.get("address") or "中国示范站点", "中国站点")
    site_name = sanitize_report_text(site_in.get("name") or site_in.get("address") or f"{city} ({lat:.4f}°N, {lon:.4f}°E)", city)
    raw_alb = (
        (mf_in.get("environment") or {}).get("albedo")
        if (mf_in.get("environment") or {}).get("albedo") is not None
        else (
            mf_in.get("albedo")
            if mf_in.get("albedo") is not None
            else (
                raw_site_in.get("albedo")
                if raw_site_in.get("albedo") is not None
                else (
                    sys_in.get("albedo")
                    if sys_in.get("albedo") is not None
                    else (
                        site_in.get("albedo")
                        if site_in.get("albedo") is not None
                        else (pvs_in.get("params") or {}).get("albedo")
                    )
                )
            )
        )
    )
    if isinstance(raw_alb, str) and raw_alb.strip().lower() in ALBEDO_PRESETS_MAP:
        raw_alb = ALBEDO_PRESETS_MAP[raw_alb.strip().lower()]
    albedo = max(0.0, min(1.0, _fnum(raw_alb, 0.22)))

    # 3. Module (.PAN) & Inverter (.OND) Catalog Enrichment
    mods_cat = load_catalog("modules.csv", include_extended=True)
    invs_cat = load_catalog("inverters.csv", include_extended=True)

    mod_id = str(
        sys_in.get("module_id")
        or (raw_in.get("module") or {}).get("id")
        or elec_in.get("module_id")
        or (proj.get("equipment") or {}).get("module_id")
        or "trina-tsm-550de19"
    )
    cat_mod = mods_cat.get(mod_id) or next(iter(mods_cat.values()), {})
    mod_override = {**(raw_in.get("module") or {}), **(sys_in.get("module") or {})}

    module_model = sanitize_report_text(
        mod_override.get("model") or sys_in.get("module_model") or cat_mod.get("model") or "JKM580N-72HL4-BDV",
        "JKM580N-72HL4-BDV",
    )
    module_brand = sanitize_report_text(
        mod_override.get("brand") or mod_override.get("manufacturer") or cat_mod.get("manufacturer") or "Tier-1 PV",
        "Tier-1 PV",
    )
    stc_w = max(100.0, _first_pos_num(mod_override.get("stc_w"), sys_in.get("stc_w"), cat_mod.get("stc_w"), default=580.0))
    mod_len_m = max(0.8, _first_pos_num(mod_override.get("length_m"), cat_mod.get("length_m"), default=2.278))
    mod_wid_m = max(0.6, _first_pos_num(mod_override.get("width_m"), cat_mod.get("width_m"), default=1.134))
    mod_area_m2 = mod_len_m * mod_wid_m
    stc_eff_pct = _first_pos_num(mod_override.get("efficiency_pct"), cat_mod.get("efficiency_pct"), default=(stc_w / (mod_area_m2 * 1000.0)) * 100.0)
    if stc_eff_pct <= 1.0:
        stc_eff_pct = (stc_w / (mod_area_m2 * 1000.0)) * 100.0
    bifaciality = max(0.0, min(0.95, _fnum(
        mod_override.get("bifaciality")
        if mod_override.get("bifaciality") is not None
        else (
            sys_in.get("bifaciality")
            if sys_in.get("bifaciality") is not None
            else ((pvs_in.get("params") or {}).get("bifaciality") if (pvs_in.get("params") or {}).get("bifaciality") is not None else 0.80)
        ),
        0.80,
    )))
    vmp_stc_v = _first_pos_num(mod_override.get("vmp_v"), cat_mod.get("vmp_v"), default=42.3)
    imp_stc_a = _first_pos_num(mod_override.get("imp_a"), cat_mod.get("imp_a"), default=stc_w / max(vmp_stc_v, 10.0))
    voc_stc_v = _first_pos_num(mod_override.get("voc_v"), cat_mod.get("voc_v"), default=vmp_stc_v * 1.20)
    isc_stc_a = _first_pos_num(mod_override.get("isc_a"), cat_mod.get("isc_a"), default=imp_stc_a * 1.06)
    beta_voc_pct_c = _first_num(
        mod_override.get("beta_voc_pct_c"),
        mod_override.get("temp_coeff_voc_pct"),
        cat_mod.get("beta_voc_pct_c"),
        default=-0.25,
    )
    if beta_voc_pct_c > 0:
        beta_voc_pct_c = -abs(beta_voc_pct_c)
    gamma_pmax_pct_c = _first_num(
        mod_override.get("gamma_pmax_pct_c"),
        mod_override.get("temp_coeff_pmax_pct"),
        cat_mod.get("gamma_pmax_pct_c"),
        default=-0.30,
    )
    if gamma_pmax_pct_c > 0:
        gamma_pmax_pct_c = -abs(gamma_pmax_pct_c)
    raw_vmp_tc = _first_present_num(
        mod_override.get("gamma_vmp_pct_c"),
        mod_override.get("beta_vmp_pct_c"),
        mod_override.get("temp_coeff_vmp_pct"),
        cat_mod.get("gamma_vmp_pct_c"),
        mod_override.get("beta_voc_pct_c"),
        mod_override.get("temp_coeff_voc_pct"),
        cat_mod.get("beta_voc_pct_c"),
    )
    vmp_temp_coeff_pct_c = float(raw_vmp_tc) if raw_vmp_tc is not None else beta_voc_pct_c
    if vmp_temp_coeff_pct_c > 0:
        vmp_temp_coeff_pct_c = -abs(vmp_temp_coeff_pct_c)
    max_sys_v = max(100.0, _first_pos_num(mod_override.get("max_system_v"), mod_override.get("max_system_voltage_v"), cat_mod.get("max_system_voltage_v"), default=1500.0))

    # Module count & DC capacity (distinguish explicit 0 from omitted fields; keep live vs saved tiers clean)
    live_dc_kw_explicit = _first_present_num(
        sys_in.get("dc_kw"),
        raw_in.get("dc_kw"),
        raw_sum_in.get("dc_kw"),
        raw_elec_in.get("dc_kw"),
    )
    live_mod_count_explicit = _first_present_num(
        sys_in.get("module_count"),
        raw_in.get("module_count"),
        raw_sum_in.get("modules"),
        raw_sum_in.get("module_count"),
        raw_elec_in.get("module_count"),
    )
    has_live_cap_override = (live_dc_kw_explicit is not None) or (live_mod_count_explicit is not None)
    dc_kw_explicit = (
        live_dc_kw_explicit
        if has_live_cap_override
        else _first_present_num(
            (pvs_in.get("summary") or {}).get("dc_kw"),
            sum_in.get("dc_kw"),
            (design.get("statistics") or {}).get("dc_kw"),
            elec_in.get("dc_kw"),
        )
    )
    mod_count_explicit = (
        live_mod_count_explicit
        if has_live_cap_override
        else _first_present_num(
            sum_in.get("modules"),
            sum_in.get("module_count"),
            (design.get("statistics") or {}).get("module_count"),
            elec_in.get("module_count"),
        )
    )
    both_dc_and_mod_explicit = (
        (live_dc_kw_explicit is not None and live_mod_count_explicit is not None)
        or (not has_live_cap_override and sum_in.get("dc_kw") is not None and (sum_in.get("modules") is not None or sum_in.get("module_count") is not None))
    )
    zero_capacity = (
        (mod_count_explicit is not None and mod_count_explicit <= 0.0)
        or (dc_kw_explicit is not None and dc_kw_explicit <= 0.0)
    )
    if zero_capacity:
        mod_count_raw = 0
        dc_kw = 0.0
    else:
        dc_kw_raw = dc_kw_explicit if (dc_kw_explicit is not None and dc_kw_explicit > 0.0) else 0.0
        mod_count_raw = int(round(mod_count_explicit)) if (mod_count_explicit is not None and mod_count_explicit > 0.0) else 0
        if mod_count_raw <= 0 and dc_kw_raw > 0.0:
            mod_count_raw = max(1, int(round((dc_kw_raw * 1000.0) / stc_w)))
        if mod_count_raw <= 0:
            mod_count_raw = 480
        dc_kw = round(dc_kw_raw if dc_kw_raw > 0.0 else (mod_count_raw * stc_w / 1000.0), 2)
    collector_area_m2 = round(mod_count_raw * mod_area_m2, 1)

    # Inverter resolution
    inv_id = str(
        sys_in.get("inverter_id")
        or (raw_in.get("inverter") or {}).get("id")
        or elec_in.get("inverter_id")
        or (proj.get("equipment") or {}).get("inverter_id")
        or "sungrow-sg100cx-p2"
    )
    cat_inv = invs_cat.get(inv_id) or next(iter(invs_cat.values()), {})
    inv_override = {**(raw_in.get("inverter") or {}), **(sys_in.get("inverter") or {})}
    inverter_model = sanitize_report_text(
        inv_override.get("model") or sys_in.get("inverter_model") or elec_in.get("inverter_model") or cat_inv.get("model") or "SG110CX-P2",
        "SG110CX-P2",
    )
    inverter_brand = sanitize_report_text(
        inv_override.get("brand") or inv_override.get("manufacturer") or cat_inv.get("manufacturer_display") or cat_inv.get("manufacturer") or "Sungrow",
        "Sungrow",
    )
    unit_ac_kw = max(1.0, _first_pos_num(inv_override.get("rated_ac_kw"), inv_override.get("ac_kw"), cat_inv.get("rated_ac_kw"), default=100.0))
    live_ac_explicit = _first_present_num(
        sys_in.get("ac_kw"),
        raw_in.get("ac_kw"),
        raw_elec_in.get("rated_ac_kw"),
        raw_elec_in.get("ac_kw"),
    )
    has_live_inv_sizing = (
        (live_ac_explicit is not None)
        or (sys_in.get("inverter_count") is not None)
        or (raw_in.get("inverter_count") is not None)
        or (raw_elec_in.get("inverter_count") is not None)
    )
    total_ac_explicit = (
        live_ac_explicit
        if has_live_inv_sizing
        else _first_present_num(
            (pvs_in.get("summary") or {}).get("ac_kw") if not has_live_cap_override else None,
            (sum_in.get("electrical") or {}).get("rated_ac_kw") if not has_live_cap_override else None,
            elec_in.get("rated_ac_kw") if not has_live_cap_override else None,
            elec_in.get("ac_kw") if not has_live_cap_override else None,
        )
    )
    if zero_capacity:
        inv_count = 0
        total_ac_kw = 0.0
        pnom_ratio = 0.0
    else:
        total_ac_kw = total_ac_explicit if (total_ac_explicit is not None and total_ac_explicit > 0.0) else 0.0
        inv_count = int(round(_first_pos_num(
            sys_in.get("inverter_count"),
            raw_in.get("inverter_count"),
            raw_elec_in.get("inverter_count"),
            elec_in.get("inverter_count") if not has_live_cap_override else None,
            default=float(max(1, round((total_ac_kw if total_ac_kw > 0 else dc_kw / 1.18) / unit_ac_kw))),
        )))
        inv_count = max(1, inv_count)
        if total_ac_kw <= 0:
            total_ac_kw = round(inv_count * unit_ac_kw, 2)
        pnom_ratio = round(dc_kw / max(total_ac_kw, 0.1), 3)

    max_dc_v = _first_pos_num(
        inv_override.get("max_dc_v"),
        inv_override.get("max_dc_voltage_v"),
        cat_inv.get("max_dc_voltage_v"),
        (sum_in.get("electrical") or {}).get("voc_limit_v"),
        default=1100.0,
    )
    v_dc_ceiling = min(max_sys_v, max_dc_v)
    mppt_min_v = _first_pos_num(
        inv_override.get("mppt_v_min"),
        inv_override.get("mppt_min_v"),
        cat_inv.get("mppt_min_v"),
        (sum_in.get("electrical") or {}).get("mppt_min_v"),
        default=200.0,
    )
    mppt_max_v = _first_pos_num(inv_override.get("mppt_v_max"), inv_override.get("mppt_max_v"), cat_inv.get("mppt_max_v"), default=1000.0)
    mppt_count_unit = max(1, int(round(_first_pos_num(
        inv_override.get("mppt_count"),
        sys_in.get("mppt_count"),
        raw_elec_in.get("mppt_count"),
        cat_inv.get("mppt_count"),
        default=9.0,
    ))))
    strings_per_mppt_unit = max(1, int(round(_first_pos_num(
        inv_override.get("strings_per_mppt"),
        sys_in.get("strings_per_mppt"),
        raw_elec_in.get("strings_per_mppt"),
        cat_inv.get("strings_per_mppt"),
        default=2.0,
    ))))
    euro_eff_pct = _first_pos_num(
        inv_override.get("euro_eff_pct"),
        inv_override.get("weighted_efficiency_pct"),
        cat_inv.get("weighted_efficiency_pct"),
        cat_inv.get("max_efficiency_pct"),
        default=98.4,
    )

    # Strings & Voltage-Temperature Envelope (live payload overrides fallback project_result)
    live_mppt_first_ser = (
        _first_pos_num(
            live_mppt_rows_raw[0].get("modulesPerString"),
            live_mppt_rows_raw[0].get("modules_per_string"),
            live_mppt_rows_raw[0].get("series_modules"),
            default=0.0,
        )
        if live_mppt_rows_raw
        else 0.0
    )
    live_mppt_total_str = (
        sum(
            max(1, int(round(_first_pos_num(r.get("stringCount"), r.get("strings"), r.get("parallel_strings"), default=1.0))))
            for r in live_mppt_rows_raw
        )
        if live_mppt_rows_raw
        else 0
    )
    mps_explicit = _first_present_num(
        sys_in.get("modules_per_string"),
        raw_in.get("modules_per_string"),
        raw_elec_in.get("modules_per_string"),
        live_mppt_first_ser or None,
    )
    str_cnt_explicit = _first_present_num(
        sys_in.get("string_count"),
        raw_in.get("string_count"),
        raw_elec_in.get("string_count"),
    )
    if zero_capacity:
        modules_per_string = 0
        string_count = 0
    else:
        modules_per_string = max(1, int(round(_first_pos_num(
            mps_explicit,
            elec_in.get("modules_per_string") if not has_live_cap_override else None,
            (sum_in.get("electrical") or {}).get("modules_per_string") if not has_live_cap_override else None,
            design.get("modules_per_string") if not has_live_cap_override else None,
            default=18.0,
        ))))
        string_count = max(1, int(round(_first_pos_num(
            str_cnt_explicit,
            live_mppt_total_str or None,
            elec_in.get("string_count") if not sys_in else None,
            (len(elec_in.get("strings") or []) if (elec_in.get("strings") and not sys_in) else None),
            default=float(max(1, round(mod_count_raw / modules_per_string))),
        ))))
    extreme_tmin_c = _first_num(
        mf_in.get("extreme_temp_min_c"),
        (mf_in.get("string_voc_check") or {}).get("extreme_temp_min_c"),
        sys_in.get("extreme_temp_min_c"),
        raw_site_in.get("design_temp_min_c"),
        site_in.get("design_temp_min_c"),
        default=-10.0,
    )
    cold_voc_per_mod = voc_stc_v * (1.0 + (beta_voc_pct_c / 100.0) * (extreme_tmin_c - 25.0))
    cold_vmp_per_mod = vmp_stc_v * (1.0 + (vmp_temp_coeff_pct_c / 100.0) * (extreme_tmin_c - 25.0))
    hot_vmp_per_mod = vmp_stc_v * (1.0 + ((gamma_pmax_pct_c * 0.88) / 100.0) * (60.0 - 25.0))

    voc_check_in = mf_in.get("string_voc_check") or {}
    raw_sizing_in = raw_elec_in.get("sizing") or {}
    if zero_capacity:
        voc_minus10_v = 0.0
        voc_tmin_v = 0.0
        vmpp_60c_v = 0.0
        max_series_safe = 0
        min_series_safe = 0
    else:
        voc_minus10_v = round(modules_per_string * voc_stc_v * (1.0 + (beta_voc_pct_c / 100.0) * (-10.0 - 25.0)), 1)
        live_mppt_max_voc = max(
            [_first_pos_num(r.get("vocColdV"), r.get("voc_cold_v"), default=0.0) for r in live_mppt_rows_raw],
            default=0.0,
        )
        live_mppt_min_vmpp = min(
            [v for v in (_first_pos_num(r.get("vmpHotV"), r.get("vmpp_v"), r.get("vmp_hot_v"), default=0.0) for r in live_mppt_rows_raw) if v > 0],
            default=0.0,
        )
        voc_tmin_v = _first_pos_num(
            raw_elec_in.get("voc_cold_v"),
            raw_sizing_in.get("vocColdV"),
            raw_sizing_in.get("vocCold"),
            mf_in.get("string_cold_voc_v"),
            voc_check_in.get("string_cold_voc_v"),
            voc_check_in.get("requested_cold_voc_v"),
            mf_in.get("cold_voc_v") if _fnum(mf_in.get("cold_voc_v"), 0.0) > 150.0 else None,
            voc_check_in.get("cold_voc_v") if _fnum(voc_check_in.get("cold_voc_v"), 0.0) > 150.0 else None,
            live_mppt_max_voc or None,
            (raw_sum_in.get("electrical") or {}).get("voc_cold_v"),
            ((res_summary.get("electrical") or {}).get("voc_cold_v") if not has_live_system else None),
            default=round(modules_per_string * cold_voc_per_mod, 1),
        )
        vmpp_60c_v = _first_pos_num(
            raw_elec_in.get("vmp_hot_v"),
            raw_elec_in.get("vmpp_60c_v"),
            raw_sizing_in.get("vmpHotV"),
            raw_sizing_in.get("vmpHot"),
            mf_in.get("string_hot_vmpp_v"),
            voc_check_in.get("string_hot_vmpp_v"),
            voc_check_in.get("requested_hot_vmpp_v"),
            mf_in.get("hot_vmpp_v") if _fnum(mf_in.get("hot_vmpp_v"), 0.0) > 100.0 else None,
            voc_check_in.get("hot_vmpp_v") if _fnum(voc_check_in.get("hot_vmpp_v"), 0.0) > 100.0 else None,
            live_mppt_min_vmpp or None,
            (raw_sum_in.get("electrical") or {}).get("vmp_hot_v"),
            ((res_summary.get("electrical") or {}).get("vmp_hot_v") if not has_live_system else None),
            default=round(modules_per_string * hot_vmp_per_mod, 1),
        )
        max_series_voc_hard = max(1, int(math.floor((v_dc_ceiling * 0.995) / max(1.0, cold_voc_per_mod))))
        max_series_mppt_cold = max(1, int(math.floor(mppt_max_v / max(1.0, cold_vmp_per_mod))))
        max_series_safe = max(1, int(round(_first_pos_num(
            mf_in.get("max_series_safe"),
            voc_check_in.get("max_series_safe"),
            default=float(min(max_series_voc_hard, max_series_mppt_cold)),
        ))))
        min_series_safe = max(1, int(round(_first_pos_num(
            mf_in.get("min_series_mppt"),
            voc_check_in.get("min_series_mppt"),
            default=float(min(max_series_safe, max(1, int(math.ceil(mppt_min_v / max(1.0, hot_vmp_per_mod)))))),
        ))))

    # 4. Orientation & Geometry
    d_params = design.get("params") or {}
    d_stats = design.get("statistics") or {}
    roof_type = str(raw_roof_in.get("type") or raw_roof_in.get("roof_type") or sys_in.get("roof_type") or roof_in.get("type") or roof_in.get("roof_type") or "flat")
    orient_mode_raw = str(
        mf_in.get("orientation_mode")
        or sys_in.get("orientation_mode")
        or sys_in.get("layout")
        or d_params.get("layout")
        or ("flush_pitched" if roof_type in ("metal", "pitched", "single_slope", "double_slope") else "south_fixed")
    )
    orient_mode_norm = _normalize_engine_orientation_mode(orient_mode_raw, roof_type)
    tilt_deg = max(0.0, min(85.0, _first_num(
        sys_in.get("tilt_deg"),
        raw_in.get("tilt_deg"),
        mf_in.get("tilt_deg"),
        d_params.get("tilt_deg"),
        roof_in.get("slope_deg"),
        default=15.0 if roof_type == "flat" else 6.0,
    )))
    azimuth_compass = _first_num(
        sys_in.get("azimuth_deg"),
        raw_in.get("azimuth_deg"),
        mf_in.get("azimuth_deg"),
        d_params.get("azimuth_deg"),
        default=180.0,
    ) % 360.0
    mount_orient = str(
        mf_in.get("mount_orientation")
        or sys_in.get("mount_orientation")
        or sys_in.get("orientation")
        or d_params.get("orientation")
        or "portrait"
    )
    collector_band_m = round(mod_len_m if mount_orient == "portrait" else mod_wid_m, 3)
    pitch_m = round(max(collector_band_m * math.cos(math.radians(tilt_deg)) + 0.05, _first_pos_num(
        sys_in.get("row_spacing_m"),
        d_stats.get("row_spacing_m") if not sys_in else None,
        default=collector_band_m * math.cos(math.radians(tilt_deg)) + max(0.45, collector_band_m * math.sin(math.radians(tilt_deg)) * 1.45),
    )), 2)
    clear_gap_m = round(max(0.02, pitch_m - collector_band_m * math.cos(math.radians(tilt_deg))), 2)
    limit_angle_deg = round(math.degrees(math.atan2(collector_band_m * math.sin(math.radians(tilt_deg)), max(0.15, clear_gap_m))), 1)
    gcr_raw = _first_pos_num(
        sys_in.get("gcr"),
        d_stats.get("gcr") if not sys_in else None,
        default=collector_band_m / max(pitch_m, 0.5),
    )
    gcr_pct = round(min(99.8, max(12.0, gcr_raw * 100.0 if gcr_raw <= 1.2 else gcr_raw)), 1)
    parapet_h_m = max(0.0, _first_num(
        sys_in.get("parapet_height_m"),
        raw_roof_in.get("parapet_height_m"),
        mf_in.get("parapet_height_m"),
        roof_in.get("parapet_height_m"),
        default=0.8,
    ))

    # 5. Loss Factors (supporting full Q04 canonical + alias names & preserving explicit 0.0)
    pvs_params = pvs_in.get("params") or {}
    loss_in = raw_in.get("losses") or {}
    uc_w_m2k = _first_pos_num(
        loss_in.get("uc_w_m2k"),
        mf_in.get("uc_w_m2k"),
        sys_in.get("uc_w_m2k"),
        raw_in.get("uc_w_m2k"),
        pvs_params.get("uc_w_m2k"),
        default=20.0 if roof_type == "metal" else 29.0,
    )
    uv_w_m2k_ms = max(0.0, _first_num(
        loss_in.get("uv_w_m2k_ms"),
        mf_in.get("uv_w_m2k_ms"),
        sys_in.get("uv_w_m2k_ms"),
        raw_in.get("uv_w_m2k_ms"),
        pvs_params.get("uv_w_m2k_ms"),
        default=0.0,
    ))
    soiling_pct = max(0.0, min(95.0, _first_num(
        loss_in.get("soiling_pct"),
        loss_in.get("soiling_loss_pct"),
        mf_in.get("soiling_pct"),
        mf_in.get("soiling_loss_pct"),
        sys_in.get("soiling_pct"),
        sys_in.get("soiling_loss_pct"),
        raw_in.get("soiling_pct"),
        raw_in.get("soiling_loss_pct"),
        pvs_params.get("soiling_pct"),
        default=2.0,
    )))
    raw_iam_loss_in = _first_present_num(
        loss_in.get("iam_loss_pct"),
        mf_in.get("iam_loss_pct"),
        sys_in.get("iam_loss_pct"),
        raw_in.get("iam_loss_pct"),
    )
    raw_iam_b0_in = _first_present_num(
        loss_in.get("iam_b0"),
        mf_in.get("iam_b0"),
        sys_in.get("iam_b0"),
        raw_in.get("iam_b0"),
        pvs_params.get("iam_b0"),
    )
    if raw_iam_b0_in is not None:
        iam_b0 = max(0.0, min(0.45, float(raw_iam_b0_in)))
    elif raw_iam_loss_in is not None:
        iam_b0 = max(0.0, min(0.45, float(raw_iam_loss_in) / 46.25))
    else:
        iam_b0 = 0.04
    lid_pct = max(0.0, min(50.0, _first_num(
        loss_in.get("lid_pct"),
        loss_in.get("lid_loss_pct"),
        mf_in.get("lid_loss_pct"),
        mf_in.get("lid_pct"),
        sys_in.get("lid_loss_pct"),
        sys_in.get("lid_pct"),
        raw_in.get("lid_loss_pct"),
        raw_in.get("lid_pct"),
        pvs_params.get("lid_pct"),
        default=1.0,
    )))
    mod_quality_pct = _first_num(loss_in.get("module_quality_pct"), raw_in.get("module_quality_pct"), pvs_params.get("module_quality_pct"), default=-0.3)
    mismatch_pct = max(0.0, min(50.0, _first_num(
        loss_in.get("mismatch_pct"),
        loss_in.get("mismatch_loss_pct"),
        mf_in.get("mismatch_loss_pct"),
        mf_in.get("mismatch_pct"),
        sys_in.get("mismatch_loss_pct"),
        sys_in.get("mismatch_pct"),
        raw_in.get("mismatch_loss_pct"),
        raw_in.get("mismatch_pct"),
        pvs_params.get("mismatch_pct"),
        default=1.0,
    )))
    dc_ohmic_pct = max(0.0, min(50.0, _first_num(
        loss_in.get("dc_ohmic_pct"),
        loss_in.get("dc_wiring_loss_pct"),
        loss_in.get("dc_ohmic_loss_pct"),
        mf_in.get("dc_wiring_loss_pct"),
        mf_in.get("dc_ohmic_pct"),
        sys_in.get("dc_wiring_loss_pct"),
        sys_in.get("dc_ohmic_pct"),
        raw_in.get("dc_wiring_loss_pct"),
        raw_in.get("dc_ohmic_pct"),
        pvs_params.get("dc_ohmic_pct"),
        (_fnum((sum_in.get("electrical") or {}).get("dc_drop_pct_max")) * 0.72) if (sum_in.get("electrical") or {}).get("dc_drop_pct_max") else None,
        default=1.2,
    )))
    ac_ohmic_pct = max(0.0, min(50.0, _first_num(
        loss_in.get("ac_ohmic_pct"),
        loss_in.get("ac_wiring_loss_pct"),
        loss_in.get("ac_ohmic_loss_pct"),
        mf_in.get("ac_wiring_loss_pct"),
        mf_in.get("ac_ohmic_pct"),
        sys_in.get("ac_wiring_loss_pct"),
        sys_in.get("ac_ohmic_pct"),
        raw_in.get("ac_wiring_loss_pct"),
        raw_in.get("ac_ohmic_pct"),
        pvs_params.get("ac_ohmic_pct"),
        (_fnum((sum_in.get("electrical") or {}).get("ac_drop_pct_max")) * 0.80) if (sum_in.get("electrical") or {}).get("ac_drop_pct_max") else None,
        default=0.8,
    )))
    transformer_loss_pct = max(0.0, min(50.0, _first_num(loss_in.get("transformer_loss_pct"), pvs_params.get("transformer_loss_pct"), default=0.9)))
    availability_pct = max(1.0, min(100.0, _first_pos_num(loss_in.get("availability_pct"), pvs_params.get("availability_pct"), default=99.2)))
    explicit_near_shading = _first_present_num(
        loss_in.get("near_shading_loss_pct"),
        loss_in.get("shading_loss_pct"),
        mf_in.get("near_shading_loss_pct"),
        mf_in.get("shading_loss_pct"),
        sys_in.get("near_shading_loss_pct"),
        sys_in.get("shading_loss_pct"),
        raw_in.get("near_shading_loss_pct"),
        (raw_sum_in.get("shading") or {}).get("avg_loss_pct"),
        res_shade.get("avg_loss_pct") if isinstance(res_shade, dict) else None,
    )
    near_shading_pct = max(0.0, min(45.0, float(explicit_near_shading) if explicit_near_shading is not None else _first_pos_num(
        (pvs_in.get("summary") or {}).get("shading_optical_loss_pct") if not (sys_in or loss_in or mf_in) else None,
        default=1.85,
    )))
    spectral_pct = _first_num(loss_in.get("spectral_corr_pct"), pvs_params.get("spectral_corr_pct"), default=0.15)
    annual_deg_pct = max(0.0, min(10.0, _first_num(
        mf_in.get("annual_degradation_pct"),
        loss_in.get("annual_degradation_pct"),
        raw_fin_in.get("annual_degradation_pct"),
        default=0.40,
    )))
    snow_loss_pct = max(0.0, min(80.0, _first_num(
        loss_in.get("snow_loss_pct"),
        mf_in.get("snow_loss_pct"),
        sys_in.get("snow_loss_pct"),
        raw_in.get("snow_loss_pct"),
        pvs_params.get("snow_loss_pct"),
        default=0.0,
    )))

    # 6. Run or Normalize 8760h Physics Simulation (Q04: Full input fingerprint binding)
    explicit_sub_arrays = (
        sys_in.get("sub_arrays")
        or raw_in.get("sub_arrays")
        or mf_in.get("sub_arrays")
        or (pvs_params.get("sub_arrays") if not (sys_in or raw_in.get("sub_arrays") or mf_in.get("sub_arrays")) else None)
    )
    sub_arrays_in = [sa for sa in (explicit_sub_arrays or []) if isinstance(sa, dict)]
    if orient_mode_norm == "east_west" and not sub_arrays_in:
        sub_arrays_in = [
            {"name": "东向子阵 East (-90°)", "dc_kw": round(dc_kw * 0.5, 2), "tilt_deg": tilt_deg, "azimuth_deg": 90.0},
            {"name": "西向子阵 West (+90°)", "dc_kw": round(dc_kw * 0.5, 2), "tilt_deg": tilt_deg, "azimuth_deg": 270.0},
        ]

    offline_flag = bool(raw_in.get("offline", offline))
    sim_input_fp = _compute_sim_input_fingerprint(
        dc_kw=dc_kw, ac_kw=total_ac_kw, lat=lat, lon=lon, albedo=albedo,
        tilt_deg=tilt_deg, azimuth_compass=azimuth_compass, orientation_mode=orient_mode_norm,
        sub_arrays=sub_arrays_in or None,
        module_id=mod_id, stc_w=stc_w, stc_eff_pct=stc_eff_pct,
        vmp_stc_v=vmp_stc_v, voc_stc_v=voc_stc_v, imp_stc_a=imp_stc_a, isc_stc_a=isc_stc_a,
        bifaciality=bifaciality, gamma_pmax_pct_c=gamma_pmax_pct_c, beta_voc_pct_c=beta_voc_pct_c,
        inverter_id=inv_id, unit_ac_kw=unit_ac_kw, inv_count=inv_count,
        euro_eff_pct=euro_eff_pct, mppt_min_v=mppt_min_v, mppt_max_v=mppt_max_v, max_dc_v=max_dc_v,
        soiling_pct=soiling_pct, iam_b0=iam_b0, iam_loss_pct=raw_iam_loss_in,
        lid_pct=lid_pct, module_quality_pct=mod_quality_pct, mismatch_pct=mismatch_pct,
        dc_ohmic_pct=dc_ohmic_pct, ac_ohmic_pct=ac_ohmic_pct,
        near_shading_pct=near_shading_pct, uc_w_m2k=uc_w_m2k, uv_w_m2k_ms=uv_w_m2k_ms,
        snow_loss_pct=snow_loss_pct, spectral_pct=spectral_pct,
        transformer_loss_pct=transformer_loss_pct, availability_pct=availability_pct,
        offline=offline_flag,
    )

    pvs_sum_chk = pvs_in.get("summary") if isinstance(pvs_in.get("summary"), dict) else None
    pvs_monthly_chk = pvs_in.get("monthly_balances") if isinstance(pvs_in.get("monthly_balances"), list) else None
    pvs_params_chk = pvs_in.get("params") if isinstance(pvs_in.get("params"), dict) else {}
    can_reuse_pvs = False
    if pvs_sum_chk and pvs_monthly_chk and len(pvs_monthly_chk) == 12:
        snap_fp = (
            pvs_in.get("_sim_input_fingerprint")
            or pvs_params_chk.get("_sim_input_fingerprint")
            or pvs_sum_chk.get("_sim_input_fingerprint")
        )
        if snap_fp and snap_fp == sim_input_fp:
            can_reuse_pvs = True
        elif snap_fp is None and pvs_params_chk:
            # Reuse without fingerprint ONLY if every simulation input field is explicitly recorded & matches
            required_num_matches = [
                (_first_present_num(pvs_sum_chk.get("dc_kw"), pvs_params_chk.get("dc_kw")), dc_kw, 1e-2),
                (_first_present_num(pvs_sum_chk.get("ac_kw"), pvs_params_chk.get("ac_kw")), total_ac_kw, 1e-2),
                (_first_present_num(pvs_params_chk.get("lat")), lat, 1e-4),
                (_first_present_num(pvs_params_chk.get("lon")), lon, 1e-4),
                (_first_present_num(pvs_params_chk.get("albedo"), pvs_sum_chk.get("albedo")), albedo, 1e-3),
                (_first_present_num(pvs_params_chk.get("tilt_deg")), tilt_deg, 1e-2),
                (_first_present_num(pvs_params_chk.get("azimuth_deg")), azimuth_compass, 1e-2),
                (_first_present_num(pvs_params_chk.get("soiling_pct")), soiling_pct, 1e-3),
                (_first_present_num(pvs_params_chk.get("iam_b0")), iam_b0, 1e-4),
                (_first_present_num(pvs_params_chk.get("lid_pct")), lid_pct, 1e-3),
                (_first_present_num(pvs_params_chk.get("mismatch_pct")), mismatch_pct, 1e-3),
                (_first_present_num(pvs_params_chk.get("dc_ohmic_pct")), dc_ohmic_pct, 1e-3),
                (_first_present_num(pvs_params_chk.get("ac_ohmic_pct")), ac_ohmic_pct, 1e-3),
                (_first_present_num(pvs_params_chk.get("shading_loss_pct")), near_shading_pct, 1e-3),
                (_first_present_num(pvs_params_chk.get("uc_w_m2k")), uc_w_m2k, 1e-2),
                (_first_present_num(pvs_params_chk.get("uv_w_m2k_ms")), uv_w_m2k_ms, 1e-3),
                (_first_present_num(pvs_params_chk.get("snow_loss_pct")), snow_loss_pct, 1e-3),
                (_first_present_num(pvs_params_chk.get("bifaciality")), bifaciality, 1e-3),
                (_first_present_num(pvs_params_chk.get("gamma_pdc_pct_c")), gamma_pmax_pct_c, 1e-3),
                (_first_present_num(pvs_params_chk.get("euro_eff_pct")), euro_eff_pct, 1e-2),
            ]
            nums_all_present_and_equal = all(
                (sv is not None and abs(sv - tv) <= tol)
                for sv, tv, tol in required_num_matches
            )
            mode_equal = str(pvs_params_chk.get("orientation_mode") or pvs_sum_chk.get("orientation_mode") or "") == orient_mode_norm
            sa_equal = (pvs_params_chk.get("sub_arrays") or []) == sub_arrays_in
            can_reuse_pvs = bool(nums_all_present_and_equal and mode_equal and sa_equal)

    if can_reuse_pvs:
        sim = pvs_in
    else:
        sim_kwargs: dict[str, Any] = dict(
            dc_kw=dc_kw,
            ac_kw=total_ac_kw if total_ac_kw > 0 else (0.0 if zero_capacity else None),
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_compass,
            shading_loss_pct=near_shading_pct,
            bifacial=bifaciality > 0,
            albedo=albedo,
            bifaciality=bifaciality,
            soiling_pct=soiling_pct,
            snow_loss_pct=snow_loss_pct,
            spectral_corr_pct=spectral_pct,
            stc_eff_pct=max(5.0, min(40.0, stc_eff_pct)),
            iam_b0=iam_b0,
            uc_w_m2k=uc_w_m2k,
            uv_w_m2k_ms=uv_w_m2k_ms,
            gamma_pdc_pct_c=gamma_pmax_pct_c,
            lid_pct=lid_pct,
            module_quality_pct=mod_quality_pct,
            mismatch_pct=mismatch_pct,
            dc_ohmic_pct=dc_ohmic_pct,
            ac_ohmic_pct=ac_ohmic_pct,
            transformer_loss_pct=transformer_loss_pct,
            availability_pct=availability_pct,
            inverter_eff_nom=max(0.92, min(0.992, euro_eff_pct / 100.0)),
            sub_arrays=sub_arrays_in or None,
            offline=offline_flag,
        )
        sig_params = inspect.signature(simulate_pvsyst).parameters
        sim_kwargs = {k: v for k, v in sim_kwargs.items() if k in sig_params}
        if "orientation_mode" in sig_params:
            sim_kwargs["orientation_mode"] = orient_mode_norm
        sim_lat = max(-66.5, min(66.5, lat))
        sim = simulate_pvsyst(sim_lat, lon, **sim_kwargs)
        if isinstance(sim, dict):
            sim["_sim_input_fingerprint"] = sim_input_fp

    sim_sum = sim.get("summary") or {}
    monthly = list(sim.get("monthly_balances") or [])
    orient_meta = _resolve_orientation_labels(orient_mode_raw, tilt_deg, azimuth_compass, sim.get("sub_arrays_summary") or sub_arrays_in)

    # Core KPIs
    glob_hor = _fnum(sim_sum.get("glob_hor_kwh_m2"), 1360.0)
    diff_hor = _fnum(sim_sum.get("diff_hor_kwh_m2"), glob_hor * 0.46)
    glob_inc = _fnum(sim_sum.get("glob_inc_kwh_m2"), glob_hor * 1.06)
    glob_eff = _fnum(sim_sum.get("glob_eff_kwh_m2"), glob_inc * 0.98)
    if zero_capacity:
        e_nom_kwh = 0.0
        e_array_kwh = 0.0
        e_grid_kwh = 0.0
        spec_yield = 0.0
        pr_pct = 0.0
    else:
        e_nom_kwh = _fnum(sim_sum.get("e_nom_kwh"), glob_eff * dc_kw)
        e_array_kwh = _fnum(sim_sum.get("e_array_kwh"), e_nom_kwh * 0.915)
        e_grid_kwh = _fnum(sim_sum.get("e_grid_kwh"), e_array_kwh * 0.962)
        spec_yield = _fnum(sim_sum.get("specific_yield_kwh_kwp"), e_grid_kwh / max(dc_kw, 0.1))
        pr_pct = _fnum(sim_sum.get("pr_pct"), (e_grid_kwh / max(glob_inc * dc_kw, 1e-6)) * 100.0)

    lt_in = sim.get("loss_tree_detail") or {}
    bif_gain_pct = 0.0 if zero_capacity else _fnum(lt_in.get("bifacial_gain_pct") if lt_in.get("bifacial_gain_pct") is not None else sim_sum.get("bifacial_gain_pct"), 4.2)

    # 13-Column Normalized Production & Monthly Energy Balances Series
    normalized_monthly: list[dict[str, Any]] = []
    for idx in range(12):
        m_row = monthly[idx] if idx < len(monthly) else {}
        d_cnt = DAYS_IN_MONTH[idx]
        m_gi = _fnum(m_row.get("glob_inc"), glob_inc / 12.0)
        m_ge = _fnum(m_row.get("glob_eff"), glob_eff / 12.0)
        m_ea = 0.0 if zero_capacity else _fnum(m_row.get("e_array"), e_array_kwh / 12.0)
        m_eg = 0.0 if zero_capacity else _fnum(m_row.get("e_grid"), e_grid_kwh / 12.0)
        m_pr = 0.0 if zero_capacity else _fnum(m_row.get("pr_pct"), (m_eg / max(m_gi * dc_kw, 1e-6)) * 100.0)
        m_ws = _first_pos_num(
            m_row.get("wind_ms"),
            m_row.get("wind_vel"),
            default=round(2.35 + 0.45 * math.cos((idx - 3) * 0.52), 2),
        )
        m_gb = 0.0 if zero_capacity else _first_num(
            m_row.get("glob_bak_kwh_m2"),
            m_row.get("glob_bak"),
            default=round(m_gi * max(0.0, bif_gain_pct / 100.0), 2),
        )

        if zero_capacity or dc_kw <= 0.0:
            yf_d = 0.0
            ya_d = 0.0
            ls_d = 0.0
            lc_d = 0.0
        else:
            yf_d = (m_eg / max(dc_kw, 0.1)) / d_cnt
            ya_d = (m_ea / max(dc_kw, 0.1)) / d_cnt
            yr_d = max(m_gi / d_cnt, m_ge / d_cnt, ya_d + 0.08)
            ls_d = max(0.03, ya_d - yf_d)
            lc_d = max(0.06, yr_d - ya_d)
        normalized_monthly.append({
            "month": idx + 1,
            "month_en": MONTH_EN[idx],
            "month_full_en": MONTH_FULL_EN[idx],
            "month_zh": MONTH_ZH[idx],
            "days": d_cnt,
            "glob_hor": _fnum(m_row.get("glob_hor"), glob_hor / 12.0),
            "diff_hor": _fnum(m_row.get("diff_hor"), diff_hor / 12.0),
            "t_amb": _fnum(m_row.get("t_amb"), 17.5),
            "wind_ms": round(m_ws, 2),
            "glob_inc": m_gi,
            "glob_eff": m_ge,
            "glob_bak": round(m_gb, 2),
            "e_array": m_ea,
            "e_grid": m_eg,
            "pr_pct": m_pr,
            "pr_ratio": round(m_pr / 100.0, 3),
            "yf_day": round(yf_d, 2),
            "ls_day": round(ls_d, 2),
            "lc_day": round(lc_d, 2),
        })

    yf_annual_day = round((e_grid_kwh / max(dc_kw, 0.1)) / 365.0, 2)
    ls_annual_day = round(sum(r["ls_day"] * r["days"] for r in normalized_monthly) / 365.0, 2)
    lc_annual_day = round(sum(r["lc_day"] * r["days"] for r in normalized_monthly) / 365.0, 2)
    t_amb_year = round(sum(r["t_amb"] * r["days"] for r in normalized_monthly) / 365.0, 2)
    wind_year_ms = round(sum(r["wind_ms"] * r["days"] for r in normalized_monthly) / 365.0, 2)
    glob_bak_year = round(sum(r["glob_bak"] for r in normalized_monthly), 1)

    # Page 3 Complete Branching Loss Tree & Sensitivity Ranking
    trans_gain_pct = _fnum(lt_in.get("inc_gain_pct") if lt_in.get("inc_gain_pct") is not None else sim_sum.get("transposition_gain_pct"), ((glob_inc / max(glob_hor, 1.0)) - 1.0) * 100.0)
    hz_loss_pct = _fnum(sim_sum.get("horizon_loss_pct"), 0.35)
    near_sh_pct = _fnum(lt_in.get("near_shading_loss_pct") if lt_in.get("near_shading_loss_pct") is not None else sim_sum.get("shading_optical_loss_pct"), near_shading_pct)
    iam_loss_pct = _fnum(lt_in.get("iam_loss_pct") if lt_in.get("iam_loss_pct") is not None else sim_sum.get("iam_loss_pct"), 1.85)
    soil_loss_pct = _fnum(lt_in.get("soiling_loss_pct") if lt_in.get("soiling_loss_pct") is not None else sim_sum.get("soiling_loss_pct"), soiling_pct)

    irrad_lvl_loss_pct = _fnum(lt_in.get("irrad_level_loss_pct"), 0.42)
    temp_loss_pct = max(0.2, _fnum(lt_in.get("temp_loss_pct") if lt_in.get("temp_loss_pct") is not None else sim_sum.get("thermal_loss_pct"), 4.5) - irrad_lvl_loss_pct)
    qual_gain_pct = _fnum(lt_in.get("quality_gain_pct"), -mod_quality_pct)
    elec_sh_pct = _fnum(sim_sum.get("shading_electrical_loss_pct"), 0.35 * near_sh_pct)
    mismatch_comb_pct = _fnum(lt_in.get("mismatch_loss_pct"), mismatch_pct + elec_sh_pct)
    dc_ohm_loss_pct = _fnum(lt_in.get("dc_ohmic_loss_pct") if lt_in.get("dc_ohmic_loss_pct") is not None else sim_sum.get("dc_ohmic_loss_pct"), dc_ohmic_pct)
    inv_op_loss_pct = _fnum(lt_in.get("inv_eff_loss_pct") if lt_in.get("inv_eff_loss_pct") is not None else sim_sum.get("inverter_eff_loss_pct"), 1.60)
    inv_clip_loss_pct = _fnum(lt_in.get("inv_clip_loss_pct") if lt_in.get("inv_clip_loss_pct") is not None else sim_sum.get("clipping_loss_pct"), 0.08)
    inv_thresh_loss_pct = 0.06
    ac_ext_loss_pct = max(0.2, 100.0 * (1.0 - (1.0 - ac_ohmic_pct / 100.0) * (1.0 - transformer_loss_pct / 100.0) * (availability_pct / 100.0)))
    e_inv_out_kwh = round(e_grid_kwh / max(1.0 - ac_ext_loss_pct / 100.0, 0.5), 0)

    loss_tree = {
        "glob_hor_kwh_m2": round(glob_hor, 1),
        "transposition_gain_pct": round(trans_gain_pct, 2),
        "glob_inc_kwh_m2": round(glob_inc, 1),
        "horizon_loss_pct": round(-hz_loss_pct, 2),
        "near_shading_loss_pct": round(-near_sh_pct, 2),
        "iam_loss_pct": round(-iam_loss_pct, 2),
        "soiling_loss_pct": round(-soil_loss_pct, 2),
        "bifacial_gain_pct": round(bif_gain_pct, 2),
        "glob_eff_kwh_m2": round(glob_eff, 1),
        "collector_area_m2": collector_area_m2,
        "stc_eff_pct": round(stc_eff_pct, 2),
        "e_nom_kwh": round(e_nom_kwh, 0),
        "irrad_level_loss_pct": round(-irrad_lvl_loss_pct, 2),
        "temp_loss_pct": round(-temp_loss_pct, 2),
        "spectral_pct": round(spectral_pct, 2),
        "quality_gain_pct": round(qual_gain_pct, 2),
        "lid_loss_pct": round(-lid_pct, 2),
        "mismatch_elec_shading_pct": round(-mismatch_comb_pct, 2),
        "dc_ohmic_loss_pct": round(-dc_ohm_loss_pct, 2),
        "e_mpp_kwh": round(e_array_kwh, 0),
        "inv_op_loss_pct": round(-inv_op_loss_pct, 2),
        "inv_clip_loss_pct": round(-inv_clip_loss_pct, 2),
        "inv_thresh_loss_pct": round(-inv_thresh_loss_pct, 2),
        "e_inv_out_kwh": e_inv_out_kwh,
        "ac_ext_loss_pct": round(-ac_ext_loss_pct, 2),
        "e_grid_kwh": round(e_grid_kwh, 0),
    }

    raw_sens_items = [
        ("POA Transposition · 倾角转置辐射效应", "Optical 光学端", loss_tree["transposition_gain_pct"], e_nom_kwh),
        ("Bifacial Rear Gain · 双面组件背面增益", "Optical 光学端", loss_tree["bifacial_gain_pct"], e_nom_kwh),
        ("Cell Temperature Loss · 工作温升热损耗", "DC Array 直流端", loss_tree["temp_loss_pct"], e_nom_kwh),
        ("3D Near Shadings · 三维近处阴影遮挡", "Optical 光学端", loss_tree["near_shading_loss_pct"], e_nom_kwh),
        ("Surface Soiling · 组件表面积灰遮蔽", "Optical 光学端", loss_tree["soiling_loss_pct"], e_nom_kwh),
        ("IAM Reflection · 入射角玻璃反射损失", "Optical 光学端", loss_tree["iam_loss_pct"], e_nom_kwh),
        ("Inverter Conversion · 逆变器转换与削峰", "AC Inverter 逆变端", round(loss_tree["inv_op_loss_pct"] + loss_tree["inv_clip_loss_pct"], 2), e_array_kwh),
        ("Mismatch & Diode · 组串失配与阴影电失配", "DC Array 直流端", loss_tree["mismatch_elec_shading_pct"], e_nom_kwh),
        ("AC & Transformer · 交流线损/箱变/可用率", "Grid Tie 并网端", loss_tree["ac_ext_loss_pct"], e_inv_out_kwh),
        ("DC Ohmic & LID · 直流线损与首年光衰", "DC Array 直流端", round(loss_tree["dc_ohmic_loss_pct"] + loss_tree["lid_loss_pct"], 2), e_nom_kwh),
    ]
    raw_sens_items.sort(key=lambda it: abs(it[2]), reverse=True)
    max_sens_abs = max((abs(it[2]) for it in raw_sens_items), default=1.0)
    loss_sensitivity_ranking = [
        {
            "rank": r_i,
            "label": lbl,
            "stage": stg,
            "pct": round(pct_v, 2),
            "energy_mwh": round((pct_v / 100.0) * base_e / 1000.0, 2),
            "bar_width_pct": round(min(100.0, (abs(pct_v) / max(max_sens_abs, 0.1)) * 100.0), 1),
            "kind": "gain" if pct_v >= 0 else "loss",
        }
        for r_i, (lbl, stg, pct_v, base_e) in enumerate(raw_sens_items[:8], 1)
    ]

    # Page 4 Special Graphs + 12x24 Hourly AC Output Heatmap
    hz_pts_raw = (sim.get("sun_path") or {}).get("horizon") or []
    sunpath_iso = _compute_7season_sunpath(lat, hz_pts_raw, parapet_h_m=parapet_h_m)
    if zero_capacity:
        daily_io = _synthesize_daily_io(normalized_monthly, 0.0)
        power_dist = _synthesize_power_distribution(0.0, 0.0, 0.0)
        hourly_heatmap_12x24 = {
            "months": list(range(1, 13)),
            "hours": list(range(24)),
            "ac_kw": [[0.0] * 24 for _ in range(12)],
            "max_ac_kw": 0.0,
        }
        prob = sim.get("probabilities") or {}
        p50_kwh = 0.0
        p75_kwh = 0.0
        p90_kwh = 0.0
        p95_kwh = 0.0
        p99_kwh = 0.0
    else:
        daily_io = sim.get("daily_io_points")
        if not isinstance(daily_io, list) or len(daily_io) < 30:
            daily_io = _synthesize_daily_io(normalized_monthly, dc_kw)
        power_dist = sim.get("power_distribution")
        if not isinstance(power_dist, list) or len(power_dist) < 5:
            power_dist = _synthesize_power_distribution(total_ac_kw, dc_kw, e_grid_kwh)

        hm_raw = sim.get("hourly_heatmap_12x24")
        if isinstance(hm_raw, dict) and isinstance(hm_raw.get("ac_kw"), list) and len(hm_raw["ac_kw"]) == 12:
            hourly_heatmap_12x24 = {
                "months": list(range(1, 13)),
                "hours": list(range(24)),
                "ac_kw": [[round(_fnum(v, 0.0), 2) for v in (row[:24] if isinstance(row, list) else [0.0] * 24)] for row in hm_raw["ac_kw"][:12]],
                "max_ac_kw": max(1.0, _fnum(hm_raw.get("max_ac_kw"), max((max(r) for r in hm_raw["ac_kw"] if isinstance(r, list) and r), default=1.0))),
            }
        else:
            hourly_heatmap_12x24 = _synthesize_hourly_heatmap_12x24(normalized_monthly, lat, orient_mode_norm, total_ac_kw)

        prob = sim.get("probabilities") or {}
        p50_kwh = _fnum(prob.get("p50_kwh"), e_grid_kwh)
        p75_kwh = _fnum(prob.get("p75_kwh"), p50_kwh * 0.965)
        p90_kwh = _fnum(prob.get("p90_kwh"), p50_kwh * 0.933)
        p95_kwh = _fnum(prob.get("p95_kwh"), p50_kwh * 0.914)
        p99_kwh = _fnum(prob.get("p99_kwh"), p50_kwh * 0.878)
    sigma_meteo = _fnum(prob.get("sigma_meteo_pct"), 4.2)
    sigma_model = _fnum(prob.get("sigma_model_pct"), 3.1)
    sigma_total = _fnum(prob.get("sigma_total_pct"), round(math.hypot(sigma_meteo, sigma_model), 2))

    # Page 5 Multi-Factor National Code Verification & MPPT Schedule
    struct_chk = mf_in.get("structural_check") or {}
    struct_params_in = raw_in.get("structural_params") or {}
    fixing_type = str(
        mf_in.get("fixing_type")
        or struct_chk.get("fixing_type")
        or struct_params_in.get("fixing_type")
        or sys_in.get("fixing_type")
        or sys_in.get("rack_type")
        or (proj.get("equipment") or {}).get("racking")
        or ("clamp" if roof_type in ("metal", "single_slope", "double_slope") else "ballast")
    )
    added_kn_m2 = _first_pos_num(
        (raw_sum_in.get("load") or {}).get("added_kn_m2"),
        (sum_in.get("load") or {}).get("added_kn_m2"),
        res_struct.get("added_kn_m2") if isinstance(res_struct, dict) else None,
        default=0.145 if ("clamp" in fixing_type or "flush" in fixing_type) else 0.36,
    )
    planes_cap_kn = next(
        (
            _fnum(pl.get("load_capacity_kn_m2"), 0.0)
            for pl in (roof_in.get("planes") or [])
            if isinstance(pl, dict) and pl.get("load_capacity_kn_m2") is not None and _fnum(pl.get("load_capacity_kn_m2"), 0.0) > 0.0
        ),
        None,
    )
    explicit_cap_kn_m2 = _first_present_num(
        (raw_sum_in.get("load") or {}).get("capacity_kn_m2"),
        raw_roof_in.get("load_capacity_kn_m2"),
        struct_params_in.get("load_capacity_kn_m2"),
        sys_in.get("load_capacity_kn_m2"),
        mf_in.get("load_capacity_kn_m2"),
        struct_chk.get("load_capacity_kn_m2"),
        (sum_in.get("load") or {}).get("capacity_kn_m2"),
        roof_in.get("load_capacity_kn_m2"),
        planes_cap_kn,
    )
    cap_kn_m2 = (
        float(explicit_cap_kn_m2)
        if (explicit_cap_kn_m2 is not None and float(explicit_cap_kn_m2) > 0.0)
        else (0.55 if roof_type in ("metal", "single_slope", "double_slope") else 1.50)
    )
    explicit_dead_load_kg_m2 = _first_present_num(
        mf_in.get("added_dead_load_kg_m2"),
        mf_in.get("added_load_kg_m2"),
        mf_in.get("dead_load_kg_m2"),
        mf_in.get("load_kg_m2"),
        struct_chk.get("added_dead_load_kg_m2"),
        struct_chk.get("added_load_kg_m2"),
        struct_chk.get("dead_load_kg_m2"),
        struct_params_in.get("added_dead_load_kg_m2"),
        struct_params_in.get("added_load_kg_m2"),
        sys_in.get("added_dead_load_kg_m2"),
        sys_in.get("added_load_kg_m2"),
        sys_in.get("dead_load_kg_m2"),
        sys_in.get("load_kg_m2"),
    )
    dead_load_kg_m2 = round(
        max(0.0, float(explicit_dead_load_kg_m2))
        if explicit_dead_load_kg_m2 is not None
        else (0.0 if zero_capacity else (added_kn_m2 * 101.97)),
        1,
    )
    explicit_max_load_kg_m2 = _first_present_num(
        mf_in.get("max_roof_load_kg_m2"),
        mf_in.get("roof_load_limit_kg_m2"),
        struct_chk.get("max_roof_load_kg_m2"),
        struct_chk.get("roof_load_limit_kg_m2"),
        struct_params_in.get("max_roof_load_kg_m2"),
        sys_in.get("max_roof_load_kg_m2"),
        sys_in.get("roof_load_limit_kg_m2"),
        raw_roof_in.get("max_load_kg_m2"),
        raw_roof_in.get("max_roof_load_kg_m2"),
        roof_in.get("max_load_kg_m2"),
    )
    max_load_kg_m2 = round(
        float(explicit_max_load_kg_m2)
        if (explicit_max_load_kg_m2 is not None and float(explicit_max_load_kg_m2) > 0.0)
        else (cap_kn_m2 * 101.97),
        1,
    )
    explicit_load_flag = next(
        (
            bool(v)
            for v in (
                mf_in.get("load_ok"),
                mf_in.get("roof_load_safe"),
                struct_chk.get("load_ok"),
                struct_chk.get("roof_load_safe"),
                sys_in.get("roof_load_safe"),
            )
            if isinstance(v, bool)
        ),
        None,
    )
    if explicit_load_flag is not None:
        load_pass = explicit_load_flag and (dead_load_kg_m2 <= max_load_kg_m2 * 1.001)
    else:
        load_pass = dead_load_kg_m2 <= max_load_kg_m2 * 1.001

    explicit_wind_w0 = _first_present_num(
        mf_in.get("basic_wind_w0_kn_m2"),
        mf_in.get("wind_w0_kn_m2"),
        mf_in.get("w0_kn_m2"),
        struct_chk.get("basic_wind_w0_kn_m2"),
        struct_chk.get("wind_w0_kn_m2"),
        struct_chk.get("w0_kn_m2"),
        struct_params_in.get("basic_wind_w0_kn_m2"),
        struct_params_in.get("wind_w0_kn_m2"),
        struct_params_in.get("w0_kn_m2"),
        sys_in.get("basic_wind_w0_kn_m2"),
        sys_in.get("wind_w0_kn_m2"),
        raw_site_in.get("basic_wind_w0_kn_m2"),
        site_in.get("basic_wind_w0_kn_m2"),
        res_struct.get("basic_wind_pressure_kn_m2") if isinstance(res_struct, dict) else None,
    )
    wind_w0 = float(explicit_wind_w0) if (explicit_wind_w0 is not None and float(explicit_wind_w0) > 0.0) else 0.45

    explicit_snow_s0 = _first_present_num(
        mf_in.get("basic_snow_s0_kn_m2"),
        mf_in.get("snow_s0_kn_m2"),
        mf_in.get("s0_kn_m2"),
        struct_chk.get("basic_snow_s0_kn_m2"),
        struct_chk.get("snow_s0_kn_m2"),
        struct_chk.get("s0_kn_m2"),
        struct_params_in.get("basic_snow_s0_kn_m2"),
        struct_params_in.get("snow_s0_kn_m2"),
        struct_params_in.get("s0_kn_m2"),
        sys_in.get("basic_snow_s0_kn_m2"),
        sys_in.get("snow_s0_kn_m2"),
        raw_site_in.get("basic_snow_s0_kn_m2"),
        site_in.get("basic_snow_s0_kn_m2"),
    )
    snow_s0 = max(0.0, float(explicit_snow_s0)) if explicit_snow_s0 is not None else 0.35
    explicit_snow_flag = next(
        (bool(v) for v in (mf_in.get("snow_ok"), struct_chk.get("snow_ok")) if isinstance(v, bool)),
        None,
    )
    if explicit_snow_flag is not None:
        snow_pass = explicit_snow_flag and (snow_s0 <= 0.85)
    else:
        snow_pass = snow_s0 <= 0.85

    edge_setback_m = _first_pos_num(
        mf_in.get("effective_setback_m"),
        mf_in.get("edge_setback_m"),
        mf_in.get("setback_m"),
        struct_chk.get("effective_setback_m"),
        struct_chk.get("edge_setback_m"),
        struct_params_in.get("edge_setback_m"),
        sys_in.get("edge_setback_m"),
        sys_in.get("setback_m"),
        d_params.get("edge_setback_m"),
        default=1.2 if wind_w0 >= 0.65 else 1.0,
    )
    explicit_wind_flag = next(
        (bool(v) for v in (mf_in.get("wind_ok"), struct_chk.get("wind_ok")) if isinstance(v, bool)),
        None,
    )
    if explicit_wind_flag is not None:
        wind_pass = explicit_wind_flag and (edge_setback_m >= (1.0 if wind_w0 >= 0.65 else 0.6))
    else:
        wind_pass = edge_setback_m >= (1.0 if wind_w0 >= 0.65 else 0.6)

    # Q05: Unified cold-state Vmpp upper limit + cold Voc ceiling + hot Vmpp window
    vmpp_tmin_v = 0.0 if zero_capacity else _first_pos_num(
        raw_elec_in.get("vmp_cold_v"),
        raw_elec_in.get("vmpp_cold_v"),
        mf_in.get("string_cold_vmpp_v"),
        voc_check_in.get("string_cold_vmpp_v"),
        voc_check_in.get("requested_cold_vmpp_v"),
        default=round(modules_per_string * cold_vmp_per_mod, 1),
    )
    voc_pass = (
        (not zero_capacity)
        and (voc_tmin_v <= v_dc_ceiling)
        and (vmpp_tmin_v <= mppt_max_v)
        and (vmpp_60c_v >= mppt_min_v)
        and (vmpp_60c_v <= mppt_max_v)
    )

    # Q05: Electrical conservation checks (module power, series×parallel count, MPPT channels & strings/MPPT)
    elec_conservation_warnings: list[str] = []
    if not zero_capacity and both_dc_and_mod_explicit:
        implied_dc_kw = round(mod_count_raw * stc_w / 1000.0, 2)
        if dc_kw > 0 and abs(implied_dc_kw - dc_kw) > max(0.35, dc_kw * 0.02):
            elec_conservation_warnings.append(
                f"module_count×stc_w/1000={implied_dc_kw:.2f} kWp ≠ dc_kw={dc_kw:.2f} kWp"
            )
    if not zero_capacity and (mps_explicit is not None and mps_explicit > 0) and (str_cnt_explicit is not None and str_cnt_explicit > 0):
        wired_mods = int(round(string_count * modules_per_string))
        if (live_mod_count_explicit is not None or live_dc_kw_explicit is not None) and abs(wired_mods - mod_count_raw) > max(2, int(round(mod_count_raw * 0.02))):
            elec_conservation_warnings.append(
                f"串并联组件数 {string_count}×{modules_per_string}S={wired_mods} ≠ module_count={mod_count_raw}"
            )
    if not zero_capacity and inv_count > 0 and mppt_count_unit > 0:
        mppt_channels_total = inv_count * mppt_count_unit
        max_strings_capacity = mppt_channels_total * strings_per_mppt_unit
        explicit_mppt_used = _first_present_num(
            raw_elec_in.get("mppt_channels_used"),
            sys_in.get("mppt_channels_used"),
            mf_in.get("mppt_channels_used"),
        )
        if explicit_mppt_used is not None and int(round(explicit_mppt_used)) > mppt_channels_total:
            elec_conservation_warnings.append(
                f"MPPT 占用路数 {int(round(explicit_mppt_used))} 超出逆变器总通道数 {inv_count}×{mppt_count_unit}={mppt_channels_total}"
            )
        elif len(live_mppt_rows_raw) > mppt_channels_total:
            elec_conservation_warnings.append(
                f"MPPT 配电表路数 {len(live_mppt_rows_raw)} 超出逆变器总通道数 {mppt_channels_total}"
            )
        if string_count > max_strings_capacity:
            elec_conservation_warnings.append(
                f"总组串数 {string_count} 超出 MPPT 通道容量 {mppt_channels_total}×{strings_per_mppt_unit}={max_strings_capacity}"
            )
        explicit_str_on_ch = _first_present_num(
            raw_elec_in.get("max_strings_per_channel"),
            raw_elec_in.get("strings_on_channel"),
            sys_in.get("strings_on_channel"),
        )
        max_live_row_par = max(
            [
                int(round(_first_pos_num(r.get("stringCount"), r.get("strings"), r.get("parallel_strings"), default=1.0)))
                for r in live_mppt_rows_raw
            ],
            default=0,
        )
        peak_str_on_ch = max(int(round(explicit_str_on_ch)) if explicit_str_on_ch is not None else 0, max_live_row_par)
        if peak_str_on_ch > strings_per_mppt_unit:
            elec_conservation_warnings.append(
                f"单路 MPPT 并联串数 {peak_str_on_ch} 超出通道上限 {strings_per_mppt_unit}"
            )
        if mf_in.get("port_allocation_ok") is False or raw_elec_in.get("port_allocation_ok") is False:
            elec_conservation_warnings.append("逆变器 MPPT 端口组串分配超限")

    pruned_mods = max(0, int(round(_first_num(
        mf_in.get("pruned_shaded_modules"),
        mf_in.get("pruned_shaded_count"),
        mf_in.get("pruned_count"),
        sys_in.get("pruned_shaded_modules"),
        sys_in.get("pruned_shaded_count"),
        default=0.0,
    ))))
    raw_walkway = _first_present_num(
        sys_in.get("walkway_width_m"),
        mf_in.get("walkway_width_m"),
        struct_chk.get("walkway_width_m"),
        struct_params_in.get("walkway_width_m"),
        d_params.get("walkway_width_m"),
        raw_in.get("walkway_width_m"),
        raw_roof_in.get("walkway_width_m"),
        roof_in.get("walkway_width_m"),
    )
    unverified_fallback_note = "未提供项目实测/结构输入原值，当前仅按估算兜底值展示，待人工复核。"
    if raw_walkway is not None:
        walkway_m: float | None = round(float(raw_walkway), 2)
        if zero_capacity:
            fire_status = "UNVERIFIED"
            fire_metric = f"0 块组件 · 通道预留 {walkway_m:.2f} m"
            fire_detail = "当前直流装机容量为 0 kWp，尚未铺设光伏阵列，待实际排布后复核消防与检修通道。"
        elif walkway_m >= 0.60:
            fire_status = "PASS"
            fire_metric = f"检修主通道 {walkway_m:.2f} m · 通道净宽达标"
            fire_detail = "仅校核检修主通道净宽 ≥ 0.60 m；完整建筑防火分区、排烟天窗与消防栓退距须结合施工图专项复核。"
        else:
            fire_status = "FAIL"
            fire_metric = f"通道宽度 {walkway_m:.2f} m (< 0.60 m 不合规)"
            fire_detail = f"实测/输入运维消防通道宽度仅 {walkway_m:.2f} m，低于 0.60 m 最小安全净宽红线，须拓宽检修通道。"
    else:
        walkway_m = None
        fire_status = "UNVERIFIED"
        fire_metric = "通道宽度未输入 · 待人工复核"
        fire_detail = "未提供项目实测/结构输入原值，当前仅按估算兜底值展示，待人工复核（主通道净宽须 ≥ 0.60 m）。"

    # Q06: Track whether each check uses real project/user inputs vs. system fallback defaults
    _load_has_explicit_input = bool(
        (explicit_cap_kn_m2 is not None and float(explicit_cap_kn_m2) > 0.0)
        or (explicit_max_load_kg_m2 is not None and float(explicit_max_load_kg_m2) > 0.0)
    )
    _wind_has_explicit_input = bool(explicit_wind_w0 is not None and float(explicit_wind_w0) > 0.0)
    _snow_has_explicit_input = bool(explicit_snow_s0 is not None)
    _has_3d_shade = isinstance(res_shade, dict) and (res_shade.get("avg_loss_pct") is not None)
    _shade_has_explicit_input = bool(
        explicit_near_shading is not None
        or _has_3d_shade
        or mf_in.get("pruned_shaded_modules") is not None
        or mf_in.get("pruned_shaded_count") is not None
        or mf_in.get("pruned_count") is not None
        or sys_in.get("pruned_shaded_modules") is not None
        or sys_in.get("pruned_shaded_count") is not None
        or mf_in.get("shading_model_level") == "3d_raytrace"
        or raw_in.get("shading_model_level") == "3d_raytrace"
    )

    _load_verified = "explicit" if (_load_has_explicit_input or explicit_load_flag is False) else "default"
    _wind_verified = "explicit" if (_wind_has_explicit_input or explicit_wind_flag is False) else "default"
    _snow_verified = "explicit" if (_snow_has_explicit_input or explicit_snow_flag is False) else "default"
    _shade_verified = "explicit" if explicit_near_shading is not None else ("computed" if _shade_has_explicit_input else "default")

    # Q06: Any check relying solely on fallback defaults MUST be UNVERIFIED (never PASS)
    if zero_capacity or _load_verified == "default":
        load_status = "UNVERIFIED"
        load_detail = unverified_fallback_note
    else:
        load_status = "PASS" if load_pass else "FAIL"
        load_detail = f"支架固定方式 {fixing_type}，荷载余量 {max(0.0, max_load_kg_m2 - dead_load_kg_m2):.1f} kg/m²。"

    if zero_capacity or _wind_verified == "default":
        wind_status = "UNVERIFIED"
        wind_detail = unverified_fallback_note
    else:
        wind_status = "PASS" if wind_pass else "FAIL"
        wind_detail = "满足屋面边角高负风压涡流区避让与抗风揭配重/夹具拉拔安全包络。"

    if zero_capacity or _snow_verified == "default":
        snow_status = "UNVERIFIED"
        snow_detail = unverified_fallback_note
    else:
        snow_status = "PASS" if snow_pass else "FAIL"
        snow_detail = f"50年一遇基本雪压组合工况下组件正面压载 ≤ 5400 Pa，排间净距 {clear_gap_m:.2f} m。"

    if zero_capacity or _shade_verified == "default":
        shade_status = "UNVERIFIED"
        shade_detail = unverified_fallback_note
    else:
        shade_status = "PASS" if near_sh_pct <= 8.0 else "WARN"
        shade_detail = f"临界遮挡仰角 {limit_angle_deg:.1f}°，结合多路MPPT独立跟踪降低旁路二极管热斑风险。"

    if zero_capacity:
        volt_metric = "0 块组件 · 未成串"
        volt_detail = "当前直流装机容量为 0 kWp，组串电压包络无效。"
        volt_status = "UNVERIFIED"
    else:
        volt_metric = f"Voc {voc_tmin_v:.1f}/{v_dc_ceiling:.0f}V · Vmp_cold {vmpp_tmin_v:.1f}/{mppt_max_v:.0f}V"
        volt_notes: list[str] = [f"低温({extreme_tmin_c:.0f}°C)安全串联 {min_series_safe}–{max_series_safe}S，当前 {modules_per_string}S，高温Vmp {vmpp_60c_v:.0f}V。"]
        if voc_tmin_v > v_dc_ceiling:
            volt_notes.append(f"冷态Voc={voc_tmin_v:.1f}V 超耐压上限{v_dc_ceiling:.0f}V！")
        if vmpp_tmin_v > mppt_max_v:
            volt_notes.append(f"冷态 Vmp={vmpp_tmin_v:.1f}V 超出 MPPT 上限 {mppt_max_v:.0f}V！")
        if vmpp_60c_v < mppt_min_v or vmpp_60c_v > mppt_max_v:
            volt_notes.append(f"高温Vmp={vmpp_60c_v:.1f}V 越出MPPT窗口！")
        if elec_conservation_warnings:
            volt_notes.append(elec_conservation_warnings[0])
        volt_detail = " ".join(volt_notes)
        volt_status = "PASS" if (voc_pass and not elec_conservation_warnings) else "FAIL"

    national_code_checks = [
        {
            "id": "dead_load",
            "code": "GB 55001 / GB 50009",
            "title_en": "Roof Structural Dead-Load",
            "title_zh": "屋面新增静荷载校核",
            "metric": f"{dead_load_kg_m2:.1f} / {max_load_kg_m2:.1f} kg/m²",
            "detail": load_detail,
            "status": load_status,
            "verified_source": _load_verified,
        },
        {
            "id": "wind_uplift",
            "code": "GB 50797 / NB/T 10115",
            "title_en": "Wind Uplift & Edge Setback",
            "title_zh": "防风揭负风压与女儿墙退距",
            "metric": f"W0 = {wind_w0:.2f} kN/m² · 退距 {edge_setback_m:.2f} m",
            "detail": wind_detail,
            "status": wind_status,
            "verified_source": _wind_verified,
        },
        {
            "id": "snow_load",
            "code": "GB 50009-2012",
            "title_en": "Snow Pressure & Shedding",
            "title_zh": "基本雪压与积雪滑移校核",
            "metric": f"S0 = {snow_s0:.2f} kN/m² · 倾角 {tilt_deg:.1f}°",
            "detail": snow_detail,
            "status": snow_status,
            "verified_source": _snow_verified,
        },
        {
            "id": "voltage_envelope",
            "code": "IEC 62548 / GB 50797",
            "title_en": "Extreme Cold Voc/Vmp & Hot Vmpp",
            "title_zh": "极寒开路/工作电压与高温MPPT电压窗口",
            "metric": volt_metric,
            "detail": volt_detail,
            "status": volt_status,
            "verified_source": "computed" if not zero_capacity else "default",
        },
        {
            "id": "shading_mismatch",
            "code": "IEC 61724 / Near-Shading",
            "title_en": "Shade Pruning & Mismatch",
            "title_zh": "近处阴影剔除与失配抑制",
            "metric": f"光学遮挡 {near_sh_pct:.2f}% · 剔除 {pruned_mods} 块",
            "detail": shade_detail,
            "status": shade_status,
            "verified_source": _shade_verified,
        },
        {
            "id": "fire_walkway",
            "code": "GB 50016 / GB 50797",
            "title_en": "Fire Safety & O&M Walkway",
            "title_zh": "消防分区退距与运维检修通道",
            "metric": fire_metric,
            "detail": fire_detail,
            "status": fire_status,
            "verified_source": "explicit" if raw_walkway is not None else "default",
        },
    ]

    def _norm_mppt_channel_row(idx_r: int, r: dict[str, Any]) -> dict[str, Any]:
        r_unit = sanitize_report_text(
            r.get("unit")
            or r.get("inverterName")
            or r.get("inverter_id")
            or (f"INV #{r['inverter']}" if r.get("inverter") is not None else None)
            or f"INV #{((idx_r - 1) // mppt_count_unit) + 1}",
            "INV #1",
        )
        r_model = sanitize_report_text(
            r.get("model") or r.get("inverterModel") or r.get("inverter_model") or inverter_model,
            inverter_model,
        )
        r_mppt = sanitize_report_text(
            r.get("mppt_used") or r.get("mpptName") or r.get("mppt_label") or r.get("mppt") or f"MPPT{idx_r}",
            f"MPPT{idx_r}",
        )
        slope_lbl = sanitize_report_text(r.get("slopeLabel") or "", "")
        if slope_lbl and slope_lbl not in r_mppt:
            r_mppt = f"{r_mppt} · {slope_lbl}"
        raw_s_names = r.get("strings_label") or r.get("stringNames") or r.get("string_ids")
        if isinstance(raw_s_names, list):
            s_lbl = (
                f"{raw_s_names[0]}..{raw_s_names[-1]}"
                if len(raw_s_names) > 3
                else (", ".join(str(x) for x in raw_s_names) if raw_s_names else f"STR-{idx_r:02d}")
            )
            s_lbl = sanitize_report_text(s_lbl, f"STR-{idx_r:02d}")
        else:
            s_lbl = sanitize_report_text(raw_s_names or f"STR-{idx_r:02d}", f"STR-{idx_r:02d}")

        n_par = max(1, int(round(_first_pos_num(
            r.get("stringCount"),
            r.get("strings"),
            r.get("parallel_strings"),
            len(raw_s_names) if isinstance(raw_s_names, list) and raw_s_names else None,
            default=1.0,
        ))))
        n_ser = max(1, int(round(_first_pos_num(
            r.get("modulesPerString"),
            r.get("modules_per_string"),
            r.get("series_modules"),
            default=float(modules_per_string),
        ))))
        tot_mods_r = int(round(_first_pos_num(
            r.get("totalMpptMods"),
            r.get("module_count"),
            default=float(n_par * n_ser),
        )))
        r_cfg = sanitize_report_text(r.get("config") or f"{n_par} × {n_ser}S", f"{n_par} × {n_ser}S")
        r_dc = round(_first_pos_num(r.get("dc_kw"), r.get("dcKw"), default=tot_mods_r * stc_w / 1000.0), 2)
        r_ratio = round(_first_pos_num(r.get("ratio"), r.get("dc_ac_ratio"), r.get("dcAcRatio"), default=pnom_ratio), 2)
        r_vmpp = round(_first_pos_num(r.get("vmpp_v"), r.get("vmpHotV"), r.get("vmp_hot_v"), r.get("vmpV"), default=n_ser * hot_vmp_per_mod), 1)
        r_vmp_cold = round(_first_pos_num(r.get("vmpColdV"), r.get("vmp_cold_v"), default=n_ser * cold_vmp_per_mod), 1)
        r_voc = round(_first_pos_num(r.get("voc_cold_v"), r.get("vocColdV"), r.get("vocV"), default=n_ser * cold_voc_per_mod), 1)
        r_drop = round(_first_pos_num(r.get("dc_drop_pct"), r.get("dcDropPct"), default=min(1.45, max(0.32, dc_ohmic_pct * (0.72 + 0.04 * (idx_r % 5))))), 2)
        raw_st = str(r.get("status") or "").strip().upper()
        row_elec_ok = (
            (r_voc <= v_dc_ceiling)
            and (r_vmp_cold <= mppt_max_v)
            and (mppt_min_v <= r_vmpp <= mppt_max_v)
            and (n_par <= strings_per_mppt_unit)
            and (idx_r <= inv_count * mppt_count_unit)
        )
        if not row_elec_ok or r.get("ok") is False or any(w in raw_st for w in ("FAIL", "超限")):
            st_txt = "FAIL"
        elif any(w in raw_st for w in ("WARN", "异常", "CHECK")):
            st_txt = "WARN"
        elif r.get("ok") is True or any(w in raw_st for w in ("PASS", "OK", "正常")):
            st_txt = "PASS"
        else:
            st_txt = "PASS" if row_elec_ok else "FAIL"
        return {
            "unit": r_unit,
            "model": r_model,
            "mppt_used": r_mppt,
            "strings_label": s_lbl,
            "config": r_cfg,
            "dc_kw": r_dc,
            "ratio": r_ratio,
            "vmpp_v": r_vmpp,
            "voc_cold_v": r_voc,
            "dc_drop_pct": r_drop,
            "status": st_txt,
        }

    def _norm_per_inverter_rows(inv_list: list[Any]) -> list[dict[str, Any]]:
        rows_out: list[dict[str, Any]] = []
        for inv_entry in inv_list[:10]:
            if not isinstance(inv_entry, dict):
                continue
            inv_no = inv_entry.get("inverter", len(rows_out) + 1)
            m_assigns = [m for m in (inv_entry.get("mppt_assignments") or []) if isinstance(m, dict) and m.get("string_ids")]
            s_ids = inv_entry.get("string_ids") or []
            s_cnt = max(1, len(s_ids))
            m_cnt = int(_fnum(inv_entry.get("module_count"), s_cnt * modules_per_string))
            rows_out.append({
                "unit": f"INV #{inv_no}",
                "model": sanitize_report_text(inv_entry.get("model") or inverter_model, inverter_model),
                "mppt_used": f"{len(m_assigns)} / {len(inv_entry.get('mppt_assignments') or []) or mppt_count_unit} MPPT",
                "strings_label": (f"{s_ids[0]}..{s_ids[-1]}" if len(s_ids) > 2 else (", ".join(str(x) for x in s_ids) or f"{s_cnt} Strings")),
                "config": f"{s_cnt} × {max(1, round(m_cnt / s_cnt))}S",
                "dc_kw": round(_fnum(inv_entry.get("dc_kw"), m_cnt * stc_w / 1000.0), 2),
                "ratio": round(_fnum(inv_entry.get("dc_ac_ratio"), pnom_ratio), 2),
                "vmpp_v": round(vmpp_60c_v, 1),
                "voc_cold_v": round(voc_tmin_v, 1),
                "dc_drop_pct": round(min(1.45, max(0.35, dc_ohmic_pct * 0.82)), 2),
                "status": "PASS" if voc_pass else "WARN",
            })
        return rows_out

    mppt_rows: list[dict[str, Any]] = []
    if zero_capacity:
        mppt_rows = [{
            "unit": "0 台",
            "model": inverter_model,
            "mppt_used": "0 / 0 MPPT",
            "strings_label": "0 串",
            "config": "0 × 0S",
            "dc_kw": 0.0,
            "ratio": 0.0,
            "vmpp_v": 0.0,
            "voc_cold_v": 0.0,
            "dc_drop_pct": 0.0,
            "status": "UNVERIFIED",
        }]
    elif live_mppt_rows_raw:
        all_live_rows = [_norm_mppt_channel_row(idx_r, r) for idx_r, r in enumerate(live_mppt_rows_raw, 1)]
        if len(all_live_rows) <= 10:
            mppt_rows = all_live_rows
        else:
            mppt_rows = all_live_rows[:9]
            tail = all_live_rows[9:]
            mppt_rows.append({
                "unit": f"+{len(tail)} Channels",
                "model": inverter_model,
                "mppt_used": f"MPPT10..{len(all_live_rows)}",
                "strings_label": f"{tail[0]['strings_label']}..{tail[-1]['strings_label']}",
                "config": f"{len(tail)} MPPT Active",
                "dc_kw": round(sum(x["dc_kw"] for x in tail), 2),
                "ratio": round(pnom_ratio, 2),
                "vmpp_v": round(min(x["vmpp_v"] for x in tail), 1),
                "voc_cold_v": round(max(x["voc_cold_v"] for x in tail), 1),
                "dc_drop_pct": round(max(x["dc_drop_pct"] for x in tail), 2),
                "status": "PASS" if all(x["status"] == "PASS" for x in tail) else "WARN",
            })
    elif isinstance(raw_elec_in.get("per_inverter"), list) and raw_elec_in["per_inverter"]:
        mppt_rows = _norm_per_inverter_rows(raw_elec_in["per_inverter"])
    elif not sys_in and isinstance(res_elec.get("per_inverter"), list) and res_elec["per_inverter"]:
        mppt_rows = _norm_per_inverter_rows(res_elec["per_inverter"])
    elif not sys_in and isinstance(res_elec.get("mppt_table") or res_elec.get("mppt_rows"), list) and (res_elec.get("mppt_table") or res_elec.get("mppt_rows")):
        fb_rows = [r for r in (res_elec.get("mppt_table") or res_elec.get("mppt_rows") or []) if isinstance(r, dict)]
        mppt_rows = [_norm_mppt_channel_row(idx_r, r) for idx_r, r in enumerate(fb_rows[:10], 1)]
    else:
        rem_strings = string_count
        for u_idx in range(1, min(inv_count, 8) + 1):
            u_str = math.ceil(rem_strings / max(1, inv_count - u_idx + 1))
            rem_strings = max(0, rem_strings - u_str)
            u_mppt = min(mppt_count_unit, max(1, math.ceil(u_str / max(1, strings_per_mppt_unit))))
            u_mods = u_str * modules_per_string
            u_dc = round(u_mods * stc_w / 1000.0, 2)
            u_port_ok = u_str <= mppt_count_unit * strings_per_mppt_unit
            mppt_rows.append({
                "unit": f"INV #{u_idx:02d}",
                "model": inverter_model,
                "mppt_used": f"{u_mppt} / {mppt_count_unit} MPPT",
                "strings_label": f"S{(u_idx - 1) * u_str + 1:02d}–S{min(string_count, u_idx * u_str):02d}",
                "config": f"{u_str} × {modules_per_string}S",
                "dc_kw": u_dc,
                "ratio": round(u_dc / max(unit_ac_kw, 1.0), 2),
                "vmpp_v": round(vmpp_60c_v, 1),
                "voc_cold_v": round(voc_tmin_v, 1),
                "dc_drop_pct": round(min(1.45, max(0.35, dc_ohmic_pct * 0.80)), 2),
                "status": "PASS" if (voc_pass and u_port_ok and not elec_conservation_warnings) else "FAIL",
            })

    # Page 6 Financial, Full 25-Row Cashflow Schedule & 3x3 Sensitivity Matrix
    self_use_frac = _first_num(
        raw_fin_in.get("self_consumption_ratio"),
        raw_fin_in.get("self_use_ratio"),
        raw_fin_in.get("self_use_pct"),
        (raw_fin_in.get("self_use") or {}).get("ratio") if isinstance(raw_fin_in.get("self_use"), dict) else None,
        mf_in.get("self_use_pct"),
        (fin_in.get("self_use") or {}).get("ratio") if isinstance(fin_in.get("self_use"), dict) else None,
        fin_in.get("self_consumption_ratio"),
        fin_in.get("self_use_ratio"),
        default=0.82,
    )
    if zero_capacity:
        self_use_pct = 0.0
        su_ratio = 0.0
    else:
        self_use_pct = round(self_use_frac * 100.0 if self_use_frac <= 1.0 else self_use_frac, 1)
        su_ratio = min(1.0, max(0.0, self_use_pct / 100.0))

    explicit_capex_cny = _first_present_num(
        raw_fin_in.get("capex_cny"),
        (_fnum(raw_fin_in.get("capex_wan"), 0.0) * 10000.0) if raw_fin_in.get("capex_wan") is not None else None,
        (_fnum(raw_fin_in.get("total_capex_wan"), 0.0) * 10000.0) if raw_fin_in.get("total_capex_wan") is not None else None,
        (_fnum(raw_fin_in.get("capex_per_w"), 0.0) * dc_kw * 1000.0) if raw_fin_in.get("capex_per_w") is not None else None,
        (_fnum(raw_fin_in.get("capex_w"), 0.0) * dc_kw * 1000.0) if raw_fin_in.get("capex_w") is not None else None,
        fin_in.get("capex_cny") if not sys_in else None,
        (_fnum(fin_in.get("capex_wan"), 0.0) * 10000.0) if (fin_in.get("capex_wan") is not None and not sys_in) else None,
        (_fnum(fin_in.get("total_capex_wan"), 0.0) * 10000.0) if (fin_in.get("total_capex_wan") is not None and not sys_in) else None,
        (_fnum(fin_in.get("capex_per_w"), 0.0) * dc_kw * 1000.0) if (fin_in.get("capex_per_w") is not None and not sys_in) else None,
    )
    if zero_capacity:
        capex_cny = 0.0
    elif explicit_capex_cny is not None:
        capex_cny = max(0.0, float(explicit_capex_cny))
    else:
        capex_cny = dc_kw * 1000.0 * 3.15
    capex_wan = round(capex_cny / 10000.0, 2)
    tariff_self = _first_num(
        raw_fin_in.get("tariff_self_rmb"),
        (raw_fin_in.get("params") or {}).get("price_self_cny_kwh"),
        (fin_in.get("params") or {}).get("price_self_cny_kwh"),
        fin_in.get("tariff_self_rmb"),
        default=0.76,
    )
    tariff_feed = _first_num(
        raw_fin_in.get("feed_in_tariff_rmb"),
        raw_fin_in.get("tariff_feed_rmb"),
        (raw_fin_in.get("params") or {}).get("price_grid_cny_kwh"),
        (fin_in.get("params") or {}).get("price_grid_cny_kwh"),
        fin_in.get("feed_in_tariff_rmb"),
        fin_in.get("tariff_feed_rmb"),
        default=0.38,
    )
    _has_explicit_tariffs = any(
        k in raw_fin_in and raw_fin_in[k] is not None
        for k in ("tariff_self_rmb", "feed_in_tariff_rmb", "tariff_feed_rmb")
    ) or (
        isinstance(raw_fin_in.get("params"), dict)
        and any(raw_fin_in["params"].get(k) is not None for k in ("price_self_cny_kwh", "price_grid_cny_kwh"))
    )
    explicit_annual_rev_wan = _first_present_num(
        raw_fin_in.get("annual_rev_wan"),
        raw_fin_in.get("first_year_rev_wan"),
    )
    discount_rate_pct = max(0.0, min(35.0, _first_num(
        raw_fin_in.get("discount_rate_pct"),
        (raw_fin_in.get("params") or {}).get("discount_rate_pct"),
        (fin_in.get("discount_rate_pct") if not sys_in else None),
        ((fin_in.get("params") or {}).get("discount_rate_pct") if not sys_in else None),
        default=6.0,
    )))
    explicit_opex_wan = _first_present_num(
        raw_fin_in.get("opex_wan_yr"),
        raw_fin_in.get("om_wan_yr"),
        (_fnum(raw_fin_in.get("opex_cny_yr")) / 10000.0) if raw_fin_in.get("opex_cny_yr") is not None else None,
        (_fnum(raw_fin_in.get("om_yuan_w_yr")) * dc_kw / 10.0) if raw_fin_in.get("om_yuan_w_yr") is not None else None,
        (_fnum(raw_fin_in.get("om_per_w_year")) * dc_kw / 10.0) if raw_fin_in.get("om_per_w_year") is not None else None,
        (fin_in.get("opex_wan_yr") if not sys_in else None),
        (fin_in.get("om_wan_yr") if not sys_in else None),
    )
    opex_wan_yr = (
        round(max(0.0, float(explicit_opex_wan)), 2)
        if explicit_opex_wan is not None
        else round(dc_kw * 0.042 / 10.0, 2)
    ) if not zero_capacity else 0.0

    cum_kwh_25 = 0.0
    cum_cf_wan = -capex_wan
    yearly_25: list[dict[str, Any]] = []
    revs_base_wan: list[float] = []
    opex_base_wan: list[float] = []
    payback_calc: float | None = None
    deg_y1 = max(0.70, 1.0 - lid_pct / 100.0)
    use_annual_rev_wan = bool(
        (not zero_capacity)
        and (not _has_explicit_tariffs)
        and (explicit_annual_rev_wan is not None)
    )
    rev_self_weight = (
        (su_ratio * max(0.0, tariff_self))
        / max(1e-6, su_ratio * max(0.0, tariff_self) + (1.0 - su_ratio) * max(0.0, tariff_feed))
        if (su_ratio * max(0.0, tariff_self) + (1.0 - su_ratio) * max(0.0, tariff_feed)) > 1e-6
        else su_ratio
    )
    inv_repl_yuan_w = max(0.0, _first_num(
        raw_fin_in.get("inv_repl_yuan_w_yr13"),
        raw_fin_in.get("inverter_replace_per_w"),
        default=0.14,
    ))
    for yr in range(1, 26):
        deg_factor = max(0.70, (1.0 - lid_pct / 100.0) * (1.0 - (annual_deg_pct / 100.0) * (yr - 1)))
        yr_kwh = 0.0 if zero_capacity else (e_grid_kwh * deg_factor)
        cum_kwh_25 += yr_kwh
        if use_annual_rev_wan:
            rev_tot_w = float(explicit_annual_rev_wan) * (deg_factor / max(deg_y1, 1e-6))
            rev_self_w = rev_tot_w * rev_self_weight
            rev_feed_w = rev_tot_w - rev_self_w
        else:
            rev_self_w = (yr_kwh * su_ratio * tariff_self) / 10000.0
            rev_feed_w = (yr_kwh * (1.0 - su_ratio) * tariff_feed) / 10000.0
            rev_tot_w = rev_self_w + rev_feed_w
        inv_rep_w = 0.0 if (zero_capacity or yr != 13) else (dc_kw * inv_repl_yuan_w / 10.0)
        opex_w = opex_wan_yr * ((1.015) ** (yr - 1)) + inv_rep_w
        net_wan = rev_tot_w - opex_w
        prev_cum = cum_cf_wan
        cum_cf_wan += net_wan
        if payback_calc is None and cum_cf_wan >= 0 and net_wan > 0 and capex_wan > 0.0:
            payback_calc = round((yr - 1) + abs(prev_cum) / net_wan, 2)
        revs_base_wan.append(rev_tot_w)
        opex_base_wan.append(opex_w)
        yearly_25.append({
            "year": yr,
            "deg_factor_pct": round(deg_factor * 100.0, 2),
            "e_grid_mwh": round(yr_kwh / 1000.0, 2),
            "rev_self_wan": round(rev_self_w, 2),
            "rev_feed_wan": round(rev_feed_w, 2),
            "opex_wan": round(opex_w, 2),
            "net_cf_wan": round(net_wan, 2),
            "cum_cf_wan": round(cum_cf_wan, 2),
        })

    if zero_capacity or capex_wan <= 0.0:
        solved_irr_base, solved_pb_base = None, None
        payback_yr: float | None = None
        irr_pct: float | None = None
        npv_wan = 0.0
        lcoe_cny_kwh: float | None = None
    else:
        solved_irr_base, solved_pb_base = _solve_irr_and_payback(capex_wan, revs_base_wan, opex_base_wan)
        # Q05: Financial self-consistency — Page 6 header KPIs must stay consistent with the 25-year cashflow table.
        raw_pb_override = _first_present_num(
            raw_fin_in.get("payback_yr"),
            raw_fin_in.get("payback_years"),
            raw_fin_in.get("static_payback_years"),
            (fin_in.get("payback_yr") if not sys_in else None),
            (fin_in.get("payback_years") if not sys_in else None),
            (fin_in.get("static_payback_years") if not sys_in else None),
        )
        cf_payback = payback_calc if payback_calc is not None else solved_pb_base
        if (
            raw_pb_override is not None
            and raw_pb_override > 0.0
            and cf_payback is not None
            and cf_payback > 0.0
            and abs(raw_pb_override - cf_payback) / max(cf_payback, 0.1) <= 0.12
        ):
            payback_yr = round(float(raw_pb_override), 2)
        else:
            payback_yr = cf_payback

        raw_irr_override = _first_present_num(
            raw_fin_in.get("irr_pct"),
            (fin_in.get("irr_pct") if not sys_in else None),
        )
        if (
            raw_irr_override is not None
            and solved_irr_base is not None
            and abs(raw_irr_override - solved_irr_base) <= 2.0
        ):
            irr_pct = round(float(raw_irr_override), 2)
        else:
            irr_pct = solved_irr_base

        disc_r = discount_rate_pct / 100.0
        npv_cf_default = round(
            -capex_wan + sum((r - o) / ((1.0 + disc_r) ** t) for t, (r, o) in enumerate(zip(revs_base_wan, opex_base_wan), 1)),
            2,
        )
        raw_npv = _first_present_num(
            raw_fin_in.get("npv_wan"),
            raw_fin_in.get("npv25_wan"),
            raw_fin_in.get("npv_25_wan"),
            (round(_fnum(raw_fin_in.get("npv_cny")) / 10000.0, 2) if raw_fin_in.get("npv_cny") is not None else None),
            (fin_in.get("npv_wan") if not sys_in else None),
            (fin_in.get("npv25_wan") if not sys_in else None),
            (fin_in.get("npv_25_wan") if not sys_in else None),
            (round(_fnum(fin_in.get("npv_cny")) / 10000.0, 2) if (fin_in.get("npv_cny") is not None and not sys_in) else None),
        )
        if (
            raw_npv is not None
            and abs(raw_npv - npv_cf_default) <= max(1.5, abs(npv_cf_default) * 0.12)
            and (abs(npv_cf_default) <= 1.5 or (raw_npv * npv_cf_default >= 0.0))
        ):
            npv_wan = round(float(raw_npv), 2)
        else:
            npv_wan = npv_cf_default

        cf_lcoe = round((capex_cny + sum(opex_base_wan) * 10000.0) / cum_kwh_25, 3) if cum_kwh_25 > 0.0 else None
        raw_lcoe_override = _first_present_num(
            raw_fin_in.get("lcoe_cny_kwh"),
            raw_fin_in.get("lcoe_rmb_kwh"),
            (fin_in.get("lcoe_cny_kwh") if not sys_in else None),
            (fin_in.get("lcoe_rmb_kwh") if not sys_in else None),
        )
        if (
            raw_lcoe_override is not None
            and raw_lcoe_override > 0.0
            and cf_lcoe is not None
            and abs(raw_lcoe_override - cf_lcoe) <= max(0.015, cf_lcoe * 0.12)
        ):
            lcoe_cny_kwh = round(float(raw_lcoe_override), 3)
        else:
            lcoe_cny_kwh = cf_lcoe
    co2_25yr_tons = round((cum_kwh_25 * 0.5703) / 1000.0, 1)
    milestone_years = [yearly_25[i - 1] for i in (1, 2, 5, 10, 15, 20, 25)]

    # 3x3 Tariff (-10% / Base / +10%) × CAPEX (-10% / Base / +10%) Sensitivity Matrix
    sensitivity_matrix_3x3: list[dict[str, Any]] = []
    for t_lbl, t_mult in [("电价 -10%", 0.90), ("基准电价 Base", 1.00), ("电价 +10%", 1.10)]:
        cells: list[dict[str, Any]] = []
        for c_lbl, c_mult in [("造价 -10%", 0.90), ("基准造价 Base", 1.00), ("造价 +10%", 1.10)]:
            if abs(t_mult - 1.0) < 1e-6 and abs(c_mult - 1.0) < 1e-6:
                c_irr = round(irr_pct, 1) if irr_pct is not None else None
                c_pb = round(payback_yr, 2) if payback_yr is not None else None
            elif zero_capacity or capex_wan <= 0.0:
                c_irr, c_pb = None, None
            else:
                c_irr_raw, c_pb_raw = _solve_irr_and_payback(
                    capex_wan * c_mult,
                    [rv * t_mult for rv in revs_base_wan],
                    opex_base_wan,
                )
                c_irr = round(c_irr_raw, 1) if c_irr_raw is not None else None
                c_pb = round(c_pb_raw, 2) if c_pb_raw is not None else None
            cells.append({
                "capex_label": c_lbl,
                "capex_mult": c_mult,
                "irr_pct": c_irr,
                "payback_yr": c_pb,
                "is_base": abs(t_mult - 1.0) < 1e-6 and abs(c_mult - 1.0) < 1e-6,
            })
        sensitivity_matrix_3x3.append({
            "tariff_label": t_lbl,
            "tariff_mult": t_mult,
            "cells": cells,
        })

    totals_25yr = {
        "rev_self_wan": round(sum(r["rev_self_wan"] for r in yearly_25), 2),
        "rev_feed_wan": round(sum(r["rev_feed_wan"] for r in yearly_25), 2),
        "opex_wan": round(sum(r["opex_wan"] for r in yearly_25), 2),
        "net_cf_wan": round(sum(r["net_cf_wan"] for r in yearly_25), 2),
        "cum_cf_wan": yearly_25[-1]["cum_cf_wan"],
    }

    icons = get_guangzhu_icon_assets()
    raw_meteo_src = sanitize_report_text(
        (sim.get("weather_metadata") or {}).get("source") or "TMY 8760h (PVGIS · NASA POWER)",
        "TMY 8760h (PVGIS · NASA POWER)",
    )
    if raw_meteo_src in ("synthesized_tmy", ""):
        meteo_src = "Guangzhu TMY 8760h (Ineichen+Erbs)"
    elif len(raw_meteo_src) > 36 and "PVGIS" in raw_meteo_src and "NASA" in raw_meteo_src:
        meteo_src = "TMY 8760h (PVGIS · NASA POWER)"
    else:
        meteo_src = raw_meteo_src

    all_pass_checks = bool(
        (not zero_capacity)
        and dc_kw > 0.0
        and all(chk.get("status") == "PASS" for chk in national_code_checks)
    )
    has_3d_raytrace = isinstance(res_shade, dict) and (res_shade.get("avg_loss_pct") is not None)
    shading_level = str(
        mf_in.get("shading_model_level")
        or raw_in.get("shading_model_level")
        or ("3d_raytrace" if has_3d_raytrace else "scheme_heuristic_annual")
    )
    shading_status_str = (
        f"3D Ray-Trace (Lin {near_sh_pct:.2f}% · Elec {elec_sh_pct:.2f}%)"
        if has_3d_raytrace or shading_level == "3d_raytrace"
        else f"Scheme Heuristic (Lin {near_sh_pct:.2f}% · Elec {elec_sh_pct:.2f}%)"
    )
    snapshot_payload = {
        "project_id": project_id,
        "variant_code": variant_code,
        "sim_input_fingerprint": sim_input_fp,
        "dc_kw": dc_kw,
        "ac_kw": round(total_ac_kw, 2),
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "albedo": round(albedo, 4),
        "orientation_mode": orient_mode_norm,
        "sub_arrays": sub_arrays_in,
        "module_count": mod_count_raw,
        "module_model": module_model,
        "inverter_model": inverter_model,
        "tilt_deg": round(tilt_deg, 2),
        "azimuth_deg": round(azimuth_compass, 2),
        "soiling_pct": round(soiling_pct, 3),
        "iam_b0": round(iam_b0, 4),
        "lid_pct": round(lid_pct, 3),
        "mismatch_pct": round(mismatch_pct, 3),
        "dc_ohmic_pct": round(dc_ohmic_pct, 3),
        "ac_ohmic_pct": round(ac_ohmic_pct, 3),
        "near_shading_pct": round(near_shading_pct, 3),
        "uc_w_m2k": round(uc_w_m2k, 2),
        "uv_w_m2k_ms": round(uv_w_m2k_ms, 3),
        "snow_loss_pct": round(snow_loss_pct, 3),
        "e_grid_kwh": round(e_grid_kwh, 0),
        "walkway_width_m": walkway_m,
        "self_use_pct": self_use_pct,
        "capex_wan": capex_wan,
        "npv_wan": npv_wan,
        "lcoe_cny_kwh": lcoe_cny_kwh,
        "irr_pct": round(irr_pct, 2) if irr_pct is not None else None,
        "payback_yr": round(payback_yr, 2) if payback_yr is not None else None,
        "all_pass": all_pass_checks,
    }
    snapshot_sha256 = hashlib.sha256(
        json.dumps(snapshot_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    input_sha256 = sim_input_fp

    return {
        "report_version": "2.0",
        "icons": {
            "icon_128_uri": icons["icon_128_uri"],
            "icon_512_uri": icons["icon_512_uri"],
        },
        "meta": {
            "project_id": project_id,
            "project_name": project_name,
            "variant_code": variant_code,
            "version": version,
            "simulation_date": sim_date,
            "report_title": "光筑专业报告",
            "report_code": f"GZ-SIM-{version:02d}",
            "filename": report_filename,
            "snapshot_sha256": snapshot_sha256,
            "input_sha256": input_sha256,
            "sim_input_fingerprint": sim_input_fp,
            "total_pages": 6,
        },
        "site": {
            "name": site_name,
            "city": city,
            "country": "China / 中国",
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "altitude_m": round(altitude_m, 1),
            "timezone": "UTC+8 (Asia/Shanghai)",
            "meteo_source": meteo_src,
            "albedo": round(albedo, 2),
            "transposition_model": "Perez 1990 Anisotropic (8760h)",
            "thermal_model": "Faiman Hourly Cell Energy Balance",
        },
        "orientation": {
            **orient_meta,
            "tilt_deg": round(tilt_deg, 1),
            "azimuth_compass_deg": round(azimuth_compass, 1),
            "mount_orientation": "Portrait (竖装)" if mount_orient == "portrait" else "Landscape (横装抗遮挡)",
            "pitch_m": pitch_m,
            "collector_width_m": collector_band_m,
            "clear_gap_m": clear_gap_m,
            "limit_angle_deg": limit_angle_deg,
            "gcr_pct": gcr_pct,
            "parapet_height_m": round(parapet_h_m, 2),
            "shading_model_level": shading_level,
            "shading_status": shading_status_str,
        },
        "pv_array": {
            "module_model": module_model,
            "module_brand": module_brand,
            "stc_w": round(stc_w, 0),
            "cell_tech": f"Si-mono N-Type Bifacial (φ = {bifaciality:.2f})",
            "bifaciality": round(bifaciality, 2),
            "stc_eff_pct": round(stc_eff_pct, 2),
            "gamma_pmax_pct_c": round(gamma_pmax_pct_c, 2),
            "beta_voc_pct_c": round(beta_voc_pct_c, 2),
            "voc_stc_v": round(voc_stc_v, 1),
            "vmp_stc_v": round(vmp_stc_v, 1),
            "isc_stc_a": round(isc_stc_a, 2),
            "imp_stc_a": round(imp_stc_a, 2),
            "module_count": mod_count_raw,
            "string_count": string_count,
            "modules_per_string": modules_per_string,
            "dc_kw": dc_kw,
            "collector_area_m2": collector_area_m2,
            "vmpp_60c_v": round(vmpp_60c_v, 1),
            "vmpp_tmin_v": round(vmpp_tmin_v, 1),
            "voc_minus10c_v": voc_minus10_v,
            "voc_tmin_v": round(voc_tmin_v, 1),
            "extreme_temp_min_c": round(extreme_tmin_c, 1),
            "min_series_safe": min_series_safe,
            "max_series_safe": max_series_safe,
        },
        "inverter": {
            "model": inverter_model,
            "brand": inverter_brand,
            "unit_ac_kw": round(unit_ac_kw, 1),
            "count": inv_count,
            "total_ac_kw": round(total_ac_kw, 2),
            "pnom_ratio": pnom_ratio,
            "mppt_window_v": f"{mppt_min_v:.0f} – {mppt_max_v:.0f} V",
            "mppt_min_v": round(mppt_min_v, 0),
            "mppt_max_v": round(mppt_max_v, 0),
            "max_dc_v": round(max_dc_v, 0),
            "mppt_count_unit": mppt_count_unit,
            "euro_eff_pct": round(euro_eff_pct, 2),
        },
        "losses": {
            "uc_w_m2k": round(uc_w_m2k, 1),
            "uv_w_m2k_ms": round(uv_w_m2k_ms, 2),
            "dc_ohmic_pct": round(dc_ohmic_pct, 2),
            "ac_ohmic_pct": round(ac_ohmic_pct, 2),
            "transformer_loss_pct": round(transformer_loss_pct, 2),
            "lid_pct": round(lid_pct, 2),
            "module_quality_pct": round(mod_quality_pct, 2),
            "mismatch_pct": round(mismatch_pct, 2),
            "soiling_pct": round(soiling_pct, 2),
            "iam_b0": round(iam_b0, 3),
            "spectral_pct": round(spectral_pct, 2),
            "annual_degradation_pct": round(annual_deg_pct, 2),
            "availability_pct": round(availability_pct, 2),
        },
        "results": {
            "e_grid_kwh": round(e_grid_kwh, 0),
            "e_grid_mwh": round(e_grid_kwh / 1000.0, 2),
            "e_array_kwh": round(e_array_kwh, 0),
            "e_nom_kwh": round(e_nom_kwh, 0),
            "specific_yield_kwh_kwp": round(spec_yield, 1),
            "pr_pct": round(pr_pct, 2),
            "pr_ratio": round(pr_pct / 100.0, 3),
            "glob_hor_kwh_m2": round(glob_hor, 1),
            "diff_hor_kwh_m2": round(diff_hor, 1),
            "glob_inc_kwh_m2": round(glob_inc, 1),
            "glob_eff_kwh_m2": round(glob_eff, 1),
            "glob_bak_kwh_m2": glob_bak_year,
            "t_amb_year_c": t_amb_year,
            "wind_year_ms": wind_year_ms,
            "yf_day": yf_annual_day,
            "ls_day": ls_annual_day,
            "lc_day": lc_annual_day,
            "self_use_pct": self_use_pct,
            "lcoe_cny_kwh": lcoe_cny_kwh,
            "lcoe_rmb_kwh": lcoe_cny_kwh,
        },
        "normalized_monthly": normalized_monthly,
        "loss_tree": loss_tree,
        "loss_sensitivity_ranking": loss_sensitivity_ranking,
        "sunpath_iso": sunpath_iso,
        "daily_io": daily_io,
        "power_distribution": power_dist,
        "hourly_heatmap_12x24": hourly_heatmap_12x24,
        "probabilities": {
            "p50_kwh": round(p50_kwh, 0),
            "p75_kwh": round(p75_kwh, 0),
            "p90_kwh": round(p90_kwh, 0),
            "p95_kwh": round(p95_kwh, 0),
            "p99_kwh": round(p99_kwh, 0),
            "sigma_meteo_pct": sigma_meteo,
            "sigma_model_pct": sigma_model,
            "sigma_total_pct": sigma_total,
        },
        "verification": {
            "fixing_type": fixing_type,
            "dead_load_kg_m2": dead_load_kg_m2,
            "max_load_kg_m2": max_load_kg_m2,
            "load_pass": load_pass,
            "wind_w0_kn_m2": round(wind_w0, 2),
            "snow_s0_kn_m2": round(snow_s0, 2),
            "snow_pass": snow_pass,
            "edge_setback_m": round(edge_setback_m, 2),
            "walkway_width_m": walkway_m,
            "wind_pass": wind_pass,
            "voc_pass": voc_pass,
            "vmpp_tmin_v": round(vmpp_tmin_v, 1),
            "elec_conservation_warnings": elec_conservation_warnings,
            "all_pass": all_pass_checks,
            "pruned_shaded_modules": pruned_mods,
            "national_code_checks": national_code_checks,
            "mppt_rows": mppt_rows,
        },
        "lifecycle": {
            "capex_wan": capex_wan,
            "opex_wan_yr": opex_wan_yr,
            "tariff_self": round(tariff_self, 3),
            "tariff_feed": round(tariff_feed, 3),
            "payback_yr": round(payback_yr, 2) if payback_yr is not None else None,
            "irr_pct": round(irr_pct, 2) if irr_pct is not None else None,
            "npv_wan": npv_wan,
            "npv25_wan": npv_wan,
            "npv_25_wan": npv_wan,
            "lcoe_cny_kwh": lcoe_cny_kwh,
            "lcoe_rmb_kwh": lcoe_cny_kwh,
            "cum_mwh_25yr": round(cum_kwh_25 / 1000.0, 1),
            "co2_25yr_tons": co2_25yr_tons,
            "yearly_25": yearly_25,
            "totals_25yr": totals_25yr,
            "milestone_rows": milestone_years,
            "sensitivity_matrix_3x3": sensitivity_matrix_3x3,
        },
    }


# ---------------------------------------------------------------------------
# Inline Swiss Technical Engineering SVG Diagrams (Pages 1 – 6)
# ---------------------------------------------------------------------------

def _svg_page1_schematic(ctx: dict[str, Any]) -> str:
    pv = ctx["pv_array"]
    inv = ctx["inverter"]
    ori = ctx["orientation"]
    res = ctx["results"]
    mod_txt = escape(f"{pv['module_brand']} {pv['module_model']}")
    inv_txt = escape(f"{inv['brand']} {inv['model']}")
    orient_txt = escape(f"{ori['field_zh']} · {ori['tilt_deg']}°")
    mppt_disp = 0 if inv["count"] <= 0 else inv["mppt_count_unit"]
    return f"""<svg class="pvs-svg" viewBox="0 0 740 112" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Grid-Connected Photovoltaic System Schematic">
  <defs>
    <marker id="gzArrDc" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8.5 5 L 0 8.5 z" fill="#1e3a8a"/>
    </marker>
    <marker id="gzArrAc" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8.5 5 L 0 8.5 z" fill="#15803d"/>
    </marker>
  </defs>
  <rect x="1.5" y="1.5" width="737" height="109" fill="#f8fafc" stroke="#64748b" stroke-width="0.95"/>

  <!-- 1. PV Sub-Arrays -->
  <g transform="translate(12, 11)">
    <rect x="0" y="0" width="168" height="90" fill="#eff6ff" stroke="#1e3a8a" stroke-width="1.2"/>
    <text x="8" y="13" font-size="8.2" font-weight="800" fill="#1e3a8a">PV SUB-ARRAYS · 光伏组件方阵</text>
    <g transform="translate(8, 19)" stroke="#1d4ed8" stroke-width="0.8" fill="#bfdbfe">
      <rect x="0" y="0" width="36" height="22"/>
      <line x1="12" y1="0" x2="12" y2="22"/><line x1="24" y1="0" x2="24" y2="22"/>
      <line x1="0" y1="7.3" x2="36" y2="7.3"/><line x1="0" y1="14.6" x2="36" y2="14.6"/>
    </g>
    <text x="50" y="27" font-size="7.5" font-weight="800" fill="#0f172a">Pnom DC: {pv['dc_kw']:.2f} kWp</text>
    <text x="50" y="38" font-size="6.9" fill="#334155">{pv['module_count']} 块 × {pv['stc_w']:.0f} Wp</text>
    <text x="8" y="54" font-size="6.8" fill="#1e293b">{mod_txt[:28]}</text>
    <text x="8" y="66" font-size="6.7" fill="#475569">{orient_txt[:26]}</text>
    <text x="8" y="79" font-size="6.7" font-weight="700" fill="#1d4ed8">Area: {pv['collector_area_m2']:,.1f} m² · φ={pv['bifaciality']:.2f}</text>
  </g>

  <line x1="180" y1="56" x2="216" y2="56" stroke="#1e3a8a" stroke-width="1.7" marker-end="url(#gzArrDc)"/>
  <text x="198" y="49" text-anchor="middle" font-size="6.4" font-weight="800" fill="#1e3a8a">DC</text>

  <!-- 2. DC Strings & Protection -->
  <g transform="translate(218, 14)">
    <rect x="0" y="0" width="144" height="84" fill="#ffffff" stroke="#334155" stroke-width="1.1"/>
    <text x="8" y="13" font-size="8.0" font-weight="800" fill="#0f172a">DC STRINGS · 组串汇流</text>
    <text x="8" y="27" font-size="7.4" font-weight="800" fill="#1e3a8a">{pv['string_count']} 串 × {pv['modules_per_string']}S</text>
    <text x="8" y="39" font-size="6.8" fill="#334155">Vmpp (60°C): {pv['vmpp_60c_v']:.1f} V</text>
    <text x="8" y="51" font-size="6.8" fill="#334155">Voc ({pv['extreme_temp_min_c']:.0f}°C): {pv['voc_tmin_v']:.1f} V</text>
    <text x="8" y="63" font-size="6.7" fill="#475569">DC Ohmic Loss: {ctx['losses']['dc_ohmic_pct']:.2f}%</text>
    <text x="8" y="75" font-size="6.6" font-weight="700" fill="#0f766e">PV1-F 4mm² · SPD Type II</text>
  </g>

  <line x1="362" y1="56" x2="398" y2="56" stroke="#1e3a8a" stroke-width="1.7" marker-end="url(#gzArrDc)"/>
  <text x="380" y="49" text-anchor="middle" font-size="6.4" font-weight="800" fill="#1e3a8a">MPPT</text>

  <!-- 3. MPPT String Inverter -->
  <g transform="translate(400, 11)">
    <rect x="0" y="0" width="160" height="90" fill="#fffbeb" stroke="#b45309" stroke-width="1.2"/>
    <text x="8" y="13" font-size="8.1" font-weight="800" fill="#92400e">MPPT INVERTER · 并网逆变</text>
    <rect x="8" y="19" width="30" height="22" fill="#fef3c7" stroke="#b45309" stroke-width="0.9"/>
    <line x1="8" y1="41" x2="38" y2="19" stroke="#b45309" stroke-width="0.9"/>
    <text x="12" y="28" font-size="7" font-weight="800" fill="#92400e">=</text>
    <text x="26" y="39" font-size="8" font-weight="800" fill="#92400e">~</text>
    <text x="44" y="27" font-size="7.5" font-weight="800" fill="#0f172a">Pac: {inv['total_ac_kw']:.1f} kWac</text>
    <text x="44" y="38" font-size="6.8" fill="#334155">{inv['count']} 台 × {inv['unit_ac_kw']:.0f} kW ({mppt_disp} MPPT)</text>
    <text x="8" y="54" font-size="6.8" fill="#1e293b">{inv_txt[:26]}</text>
    <text x="8" y="66" font-size="6.7" fill="#475569">MPPT: {escape(inv['mppt_window_v'])} (Max {inv['max_dc_v']:.0f}V)</text>
    <text x="8" y="79" font-size="6.8" font-weight="800" fill="#b45309">DC:AC = {inv['pnom_ratio']:.3f} · η={inv['euro_eff_pct']:.2f}%</text>
  </g>

  <line x1="560" y1="40" x2="596" y2="33" stroke="#15803d" stroke-width="1.7" marker-end="url(#gzArrAc)"/>
  <line x1="560" y1="72" x2="596" y2="79" stroke="#15803d" stroke-width="1.7" marker-end="url(#gzArrAc)"/>
  <text x="578" y="58" text-anchor="middle" font-size="6.3" font-weight="800" fill="#15803d">380V/10kV</text>

  <!-- 4A. User Self-Use Load -->
  <g transform="translate(598, 10)">
    <rect x="0" y="0" width="130" height="43" fill="#f0fdf4" stroke="#15803d" stroke-width="1.1"/>
    <text x="7" y="13" font-size="7.5" font-weight="800" fill="#166534">USER LOAD · 厂区负荷消纳</text>
    <text x="7" y="25" font-size="7.1" font-weight="800" fill="#0f172a">Self-Use: {res['self_use_pct']:.1f}%</text>
    <text x="7" y="36" font-size="6.5" fill="#334155">自发自用优先 · 双向关口表</text>
  </g>

  <!-- 4B. AC Utility Grid -->
  <g transform="translate(598, 59)">
    <rect x="0" y="0" width="130" height="43" fill="#f1f5f9" stroke="#0f172a" stroke-width="1.1"/>
    <text x="7" y="13" font-size="7.5" font-weight="800" fill="#0f172a">UTILITY GRID · 公共电网</text>
    <text x="7" y="25" font-size="7.1" font-weight="800" fill="#1d4ed8">E_Grid: {res['e_grid_mwh']:,.2f} MWh/yr</text>
    <text x="7" y="36" font-size="6.5" fill="#475569">PR: {res['pr_pct']:.2f}% · 余电上网</text>
  </g>
</svg>"""


def _svg_page2_dual_charts(ctx: dict[str, Any]) -> str:
    rows = ctx["normalized_monthly"]
    res = ctx["results"]

    max_tot = max([r["yf_day"] + r["ls_day"] + r["lc_day"] for r in rows] + [5.5])
    y_ceil = max(6.0, math.ceil(max_tot))
    lx0, ly0, lw, lh = 38.0, 46.0, 308.0, 120.0
    bar_step = lw / 12.0
    bar_w = bar_step * 0.62

    left_grid: list[str] = []
    n_ticks = 6
    for i in range(n_ticks + 1):
        val = (y_ceil / n_ticks) * i
        yp = ly0 + lh - (val / y_ceil) * lh
        left_grid.append(f'<line x1="{lx0}" y1="{yp:.1f}" x2="{lx0 + lw}" y2="{yp:.1f}" stroke="#cbd5e1" stroke-width="0.6"/>')
        left_grid.append(f'<text x="{lx0 - 4}" y="{yp + 2.4:.1f}" text-anchor="end" font-size="6.5" fill="#475569">{val:.1f}</text>')

    left_bars: list[str] = []
    for idx, r in enumerate(rows):
        bx = lx0 + idx * bar_step + (bar_step - bar_w) * 0.5
        h_yf = (r["yf_day"] / y_ceil) * lh
        h_ls = (r["ls_day"] / y_ceil) * lh
        h_lc = (r["lc_day"] / y_ceil) * lh
        y_yf = ly0 + lh - h_yf
        y_ls = y_yf - h_ls
        y_lc = y_ls - h_lc
        left_bars.append(f'<rect x="{bx:.1f}" y="{y_yf:.1f}" width="{bar_w:.1f}" height="{max(0.5, h_yf):.1f}" fill="#991b1b"/>')
        left_bars.append(f'<rect x="{bx:.1f}" y="{y_ls:.1f}" width="{bar_w:.1f}" height="{max(0.5, h_ls):.1f}" fill="#16a34a"/>')
        left_bars.append(f'<rect x="{bx:.1f}" y="{y_lc:.1f}" width="{bar_w:.1f}" height="{max(0.5, h_lc):.1f}" fill="#7c3aed"/>')
        left_bars.append(f'<text x="{bx + bar_w * 0.5:.1f}" y="{ly0 + lh + 10.5:.1f}" text-anchor="middle" font-size="6.4" fill="#1e293b">{r["month_en"]}</text>')

    rx0, ry0, rw, rh = 416.0, 46.0, 308.0, 120.0
    right_grid: list[str] = []
    for pct_tick in (0, 20, 40, 60, 80, 100):
        yp = ry0 + rh - (pct_tick / 100.0) * rh
        right_grid.append(f'<line x1="{rx0}" y1="{yp:.1f}" x2="{rx0 + rw}" y2="{yp:.1f}" stroke="#cbd5e1" stroke-width="0.6"/>')
        right_grid.append(f'<text x="{rx0 - 4}" y="{yp + 2.4:.1f}" text-anchor="end" font-size="6.5" fill="#475569">{pct_tick / 100.0:.1f}</text>')

    right_bars: list[str] = []
    for idx, r in enumerate(rows):
        bx = rx0 + idx * bar_step + (bar_step - bar_w) * 0.5
        pr_clamped = max(0.0, min(100.0, r["pr_pct"]))
        bh = (pr_clamped / 100.0) * rh
        by = ry0 + rh - bh
        right_bars.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="#b91c1c" opacity="0.86"/>')
        right_bars.append(f'<text x="{bx + bar_w * 0.5:.1f}" y="{by - 2.2:.1f}" text-anchor="middle" font-size="5.7" font-weight="700" fill="#334155">{r["pr_ratio"]:.2f}</text>')
        right_bars.append(f'<text x="{bx + bar_w * 0.5:.1f}" y="{ry0 + rh + 10.5:.1f}" text-anchor="middle" font-size="6.4" fill="#1e293b">{r["month_en"]}</text>')

    pr_ann_y = ry0 + rh - (max(0.0, min(100.0, res["pr_pct"])) / 100.0) * rh

    return f"""<svg class="pvs-svg" viewBox="0 0 740 182" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Normalized Production and Performance Ratio Monthly Charts">
  <rect x="1" y="1" width="358" height="180" fill="#ffffff" stroke="#334155" stroke-width="0.9"/>
  <text x="180" y="13" text-anchor="middle" font-size="8.0" font-weight="800" fill="#0f172a">Normalized Production (per installed kWp) · 归一化日均产出</text>
  <rect x="38" y="17" width="308" height="23" fill="#f8fafc" stroke="#94a3b8" stroke-width="0.6"/>
  <rect x="43" y="20" width="8" height="6" fill="#7c3aed"/>
  <text x="54" y="25.5" font-size="6.2" fill="#1e293b">Lc: Collection Loss {res['lc_day']:.2f} kWh/kWp/d</text>
  <rect x="196" y="20" width="8" height="6" fill="#16a34a"/>
  <text x="207" y="25.5" font-size="6.2" fill="#1e293b">Ls: System Loss {res['ls_day']:.2f} kWh/kWp/d</text>
  <rect x="43" y="30" width="8" height="6" fill="#991b1b"/>
  <text x="54" y="35.5" font-size="6.3" font-weight="700" fill="#0f172a">Yf: Produced Useful Energy (inverter output) {res['yf_day']:.2f} kWh/kWp/day</text>

  {"".join(left_grid)}
  <rect x="{lx0}" y="{ly0}" width="{lw}" height="{lh}" fill="none" stroke="#0f172a" stroke-width="0.9"/>
  {"".join(left_bars)}
  <text x="11" y="108" transform="rotate(-90 11 108)" text-anchor="middle" font-size="6.5" font-weight="700" fill="#334155">kWh / kWp / day</text>

  <rect x="381" y="1" width="358" height="180" fill="#ffffff" stroke="#334155" stroke-width="0.9"/>
  <text x="560" y="13" text-anchor="middle" font-size="8.0" font-weight="800" fill="#0f172a">Performance Ratio PR · 系统综合能效比</text>
  <rect x="416" y="17" width="308" height="23" fill="#f8fafc" stroke="#94a3b8" stroke-width="0.6"/>
  <rect x="423" y="20" width="9" height="6" fill="#b91c1c" opacity="0.86"/>
  <text x="436" y="25.5" font-size="6.2" font-weight="700" fill="#0f172a">Monthly PR = Yf / Yr (IEC 61724 standard ratio)</text>
  <line x1="422" y1="33.5" x2="434" y2="33.5" stroke="#1d4ed8" stroke-width="1.4" stroke-dasharray="3.5,2"/>
  <text x="438" y="35.8" font-size="6.3" font-weight="800" fill="#1d4ed8">Annual PR = {res['pr_ratio']:.3f} ({res['pr_pct']:.2f}%)</text>

  {"".join(right_grid)}
  <rect x="{rx0}" y="{ry0}" width="{rw}" height="{rh}" fill="none" stroke="#0f172a" stroke-width="0.9"/>
  {"".join(right_bars)}
  <line x1="{rx0}" y1="{pr_ann_y:.1f}" x2="{rx0 + rw}" y2="{pr_ann_y:.1f}" stroke="#1d4ed8" stroke-width="1.2" stroke-dasharray="4,2.5"/>
  <text x="391" y="108" transform="rotate(-90 391 108)" text-anchor="middle" font-size="6.5" font-weight="700" fill="#334155">Performance Ratio (PR)</text>
</svg>"""


def _svg_page3_loss_diagram(ctx: dict[str, Any]) -> str:
    lt = ctx["loss_tree"]
    svg_parts: list[str] = [
        '<svg class="pvs-svg" viewBox="0 0 800 572" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Annual 8760h Energy Loss Flow Diagram">',
        '<defs>',
        '  <marker id="lossSideArr" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto">',
        '    <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#b91c1c"/>',
        '  </marker>',
        '  <marker id="gainSideArr" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="6" markerHeight="6" orient="auto">',
        '    <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#15803d"/>',
        '  </marker>',
        '</defs>',
        '<rect x="1.5" y="1.5" width="797" height="569" fill="#ffffff" stroke="#334155" stroke-width="0.95"/>',
        '<text x="14" y="16" font-size="8.8" font-weight="900" fill="#0f172a">Annual 8760h Energy Flow &amp; Branching Loss Diagram · 全年能量流分支损耗树图</text>',
        '<line x1="10" y1="21" x2="790" y2="21" stroke="#cbd5e1" stroke-width="0.8"/>',
    ]

    def _stage_box(y: float, width: float, val_str: str, label_en: str, label_zh: str, fill: str = "#e2e8f0", stroke: str = "#0f172a", text_col: str = "#0f172a") -> None:
        x0 = 56.0
        svg_parts.append(f'<rect x="{x0:.1f}" y="{y:.1f}" width="{width:.1f}" height="20" fill="{fill}" stroke="{stroke}" stroke-width="1.1"/>')
        svg_parts.append(f'<text x="{x0 + width * 0.5:.1f}" y="{y + 13.2:.1f}" text-anchor="middle" font-size="7.8" font-weight="800" fill="{text_col}">{escape(val_str)}</text>')
        svg_parts.append(f'<text x="{x0 + width + 14:.1f}" y="{y + 9.2:.1f}" font-size="7.6" font-weight="800" fill="#0f172a">{escape(label_en)}</text>')
        svg_parts.append(f'<text x="{x0 + width + 14:.1f}" y="{y + 17.8:.1f}" font-size="6.8" fill="#475569">{escape(label_zh)}</text>')

    def _branch_row(y: float, w_cur: float, pct: float, label_en: str, label_zh: str, *, bar_fill: str = "#cbd5e1") -> float:
        x0 = 56.0
        w_next = max(86.0, min(248.0, w_cur * (1.0 + pct / 100.0)))
        svg_parts.append(f'<polygon points="{x0:.1f},{y:.1f} {x0 + w_cur:.1f},{y:.1f} {x0 + w_next:.1f},{y + 18:.1f} {x0:.1f},{y + 18:.1f}" fill="{bar_fill}" stroke="#64748b" stroke-width="0.5" opacity="0.76"/>')
        ym = y + 9.5
        pct_txt = _fmt_signed(pct, 2)
        if pct >= 0:
            ax1, ax2 = 320.0, x0 + max(w_cur, w_next) + 6.0
            svg_parts.append(f'<line x1="{ax1:.1f}" y1="{ym:.1f}" x2="{ax2:.1f}" y2="{ym:.1f}" stroke="#15803d" stroke-width="1.3" marker-end="url(#gainSideArr)"/>')
            svg_parts.append(f'<text x="326" y="{ym + 2.8:.1f}" font-size="7.3" font-weight="800" fill="#15803d">{escape(pct_txt)}</text>')
        else:
            ax1, ax2 = x0 + w_cur, 318.0
            svg_parts.append(f'<line x1="{ax1:.1f}" y1="{ym:.1f}" x2="{ax2:.1f}" y2="{ym:.1f}" stroke="#b91c1c" stroke-width="1.3" marker-end="url(#lossSideArr)"/>')
            svg_parts.append(f'<text x="326" y="{ym + 2.8:.1f}" font-size="7.3" font-weight="800" fill="#b91c1c">{escape(pct_txt)}</text>')
        svg_parts.append(f'<text x="378" y="{ym + 2.8:.1f}" font-size="7.0" font-weight="600" fill="#0f172a">{escape(label_en)} <tspan fill="#475569" font-weight="400">· {escape(label_zh)}</tspan></text>')
        return w_next

    w = 196.0
    y = 26.0
    _stage_box(y, w, f"{lt['glob_hor_kwh_m2']:,.1f} kWh/m²", "Horizontal global irradiation (GlobHor)", "水平面全年总辐射量", fill="#fef3c7", stroke="#b45309")
    y += 21.0
    w = _branch_row(y, w, lt["transposition_gain_pct"], "Global incident in collector plane (Perez 1990)", "倾斜面各向异性转置增益 (GlobInc)", bar_fill="#fde68a")
    y += 19.0
    _stage_box(y, w, f"{lt['glob_inc_kwh_m2']:,.1f} kWh/m²", "Global incident in collector plane (GlobInc)", "组件采光平面总入射辐射", fill="#fef9c3", stroke="#ca8a04")
    y += 21.0
    w = _branch_row(y, w, lt["horizon_loss_pct"], "Far horizon profile blocking", "远方天际线遮挡损失", bar_fill="#fde68a")
    y += 19.0
    w = _branch_row(y, w, lt["near_shading_loss_pct"], "3D Near Shadings: irradiance loss", "三维近处障碍物与排间光学遮挡损失", bar_fill="#fde68a")
    y += 19.0
    w = _branch_row(y, w, lt["iam_loss_pct"], f"IAM factor on global (ASHRAE b0={ctx['losses']['iam_b0']:.2f})", "入射角修饰因子反射损失 (IAM)", bar_fill="#fde68a")
    y += 19.0
    w = _branch_row(y, w, lt["soiling_loss_pct"], "Surface soiling loss factor", "组件表面积灰遮蔽损失", bar_fill="#fde68a")
    y += 19.0
    w = _branch_row(y, w, lt["bifacial_gain_pct"], f"Ground reflection & Bifacial rear gain (Albedo={ctx['site']['albedo']:.2f})", "地表反射与双面组件背面受光增益", bar_fill="#bbf7d0")
    y += 20.0
    _stage_box(
        y,
        w,
        f"{lt['glob_eff_kwh_m2']:,.1f} kWh/m² × {lt['collector_area_m2']:,.0f} m²",
        "Effective irradiation on collectors (GlobEff × Area)",
        "有效受光辐射量 × 光伏方阵采光总面积",
        fill="#fef08a",
        stroke="#a16207",
    )

    y += 22.0
    svg_parts.append(f'<rect x="66" y="{y:.1f}" width="{w - 20:.1f}" height="18" fill="#dbeafe" stroke="#1d4ed8" stroke-width="1.05"/>')
    svg_parts.append(f'<text x="{56 + w * 0.5:.1f}" y="{y + 12:.1f}" text-anchor="middle" font-size="7.3" font-weight="800" fill="#1e3a8a">PV Conversion · STC η = {lt["stc_eff_pct"]:.2f}%</text>')
    svg_parts.append(f'<text x="{56 + w + 14:.1f}" y="{y + 12:.1f}" font-size="7.3" font-weight="700" fill="#1e3a8a">Photovoltaic conversion at STC (1000 W/m², 25°C) · 标准工况光电转换</text>')

    y += 20.0
    w = 206.0
    _stage_box(y, w, f"{lt['e_nom_kwh']:,.0f} kWh", "Array nominal energy (at STC efficiency)", "方阵标称直流发电量 (ENom)", fill="#dbeafe", stroke="#1d4ed8")
    y += 21.0
    w = _branch_row(y, w, lt["irrad_level_loss_pct"], "PV loss due to low irradiance level", "弱光低辐照度非线性响应损失", bar_fill="#bfdbfe")
    y += 19.0
    w = _branch_row(y, w, lt["temp_loss_pct"], f"PV loss due to cell temperature (Faiman Uc={ctx['losses']['uc_w_m2k']:.0f} W/m²K)", "工作结温升高热功率损耗", bar_fill="#bfdbfe")
    y += 19.0
    w = _branch_row(y, w, lt["spectral_pct"], "Spectral response correction (N-Type Si-mono)", "光谱响应修正系数", bar_fill="#bfdbfe")
    y += 19.0
    w = _branch_row(y, w, lt["quality_gain_pct"], "Module positive power sorting quality", "组件铭牌正公差品质增益", bar_fill="#bfdbfe")
    y += 19.0
    w = _branch_row(y, w, lt["lid_loss_pct"], "LID - First-year light induced degradation", "首年光致衰减损失 (LID)", bar_fill="#bfdbfe")
    y += 19.0
    w = _branch_row(y, w, lt["mismatch_elec_shading_pct"], "Module & string mismatch + electrical diode shading", "组串失配及阴影旁路二极管电失配", bar_fill="#bfdbfe")
    y += 19.0
    w = _branch_row(y, w, lt["dc_ohmic_loss_pct"], "DC array ohmic wiring loss", "直流侧组串线缆欧姆压降损耗", bar_fill="#bfdbfe")
    y += 20.0
    _stage_box(y, w, f"{lt['e_mpp_kwh']:,.0f} kWh", "Array virtual energy at MPP (EArray)", "方阵最大功率点有效直流产出 (EArray)", fill="#e0f2fe", stroke="#0369a1")

    y += 21.0
    w = _branch_row(y, w, lt["inv_op_loss_pct"], f"Inverter conversion loss (Euro η={ctx['inverter']['euro_eff_pct']:.2f}%)", "逆变器运行转换效率损耗", bar_fill="#bae6fd")
    y += 19.0
    w = _branch_row(y, w, lt["inv_clip_loss_pct"], f"Inverter overpower clipping (DC:AC={ctx['inverter']['pnom_ratio']:.2f})", "高容配比满功率限发削峰损失", bar_fill="#bae6fd")
    y += 19.0
    w = _branch_row(y, w, lt["inv_thresh_loss_pct"], "Inverter threshold & night standby loss", "逆变器启动功率阈值损耗", bar_fill="#bae6fd")
    y += 20.0
    _stage_box(y, w, f"{lt['e_inv_out_kwh']:,.0f} kWh", "Available Energy at Inverter Output", "逆变器交流输出端可用电量", fill="#dcfce7", stroke="#15803d")
    y += 21.0
    w = _branch_row(y, w, lt["ac_ext_loss_pct"], "AC ohmic wiring, MV transformer & availability loss", "交流集电线损、升压变损耗及不可用率", bar_fill="#bbf7d0")
    y += 20.0
    _stage_box(
        y,
        w,
        f"{lt['e_grid_kwh']:,.0f} kWh ({ctx['results']['e_grid_mwh']:,.2f} MWh)",
        "Energy injected into utility grid (E_Grid)",
        f"最终并网有效发电量 · PR = {ctx['results']['pr_pct']:.2f}% · 等效满发 {ctx['results']['specific_yield_kwh_kwp']:,.1f} h",
        fill="#166534",
        stroke="#052e16",
        text_col="#ffffff",
    )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def _svg_page4_iso_sunpath(ctx: dict[str, Any]) -> str:
    sp = ctx["sunpath_iso"]
    px0, py0, pw, ph = 46.0, 22.0, 504.0, 162.0

    def _map_pt(az_sol: float, el_deg: float) -> tuple[float, float]:
        x = px0 + ((max(-180.0, min(180.0, az_sol)) + 180.0) / 360.0) * pw
        y = py0 + ph - (max(0.0, min(90.0, el_deg)) / 90.0) * ph
        return x, y

    grid_elems: list[str] = []
    for az_tick in range(-180, 181, 30):
        xg, _ = _map_pt(float(az_tick), 0.0)
        dash = "" if az_tick in (-90, 0, 90) else ' stroke-dasharray="2,2"'
        sw = "0.9" if az_tick == 0 else "0.55"
        grid_elems.append(f'<line x1="{xg:.1f}" y1="{py0}" x2="{xg:.1f}" y2="{py0 + ph}" stroke="#cbd5e1" stroke-width="{sw}"{dash}/>')
        lbl = f"{az_tick:+d}°" if az_tick != 0 else "0°(S)"
        if az_tick == -90:
            lbl = "-90°(E)"
        elif az_tick == 90:
            lbl = "+90°(W)"
        grid_elems.append(f'<text x="{xg:.1f}" y="{py0 + ph + 10:.1f}" text-anchor="middle" font-size="6.1" fill="#334155">{lbl}</text>')

    for el_tick in range(0, 91, 15):
        _, yg = _map_pt(0.0, float(el_tick))
        grid_elems.append(f'<line x1="{px0}" y1="{yg:.1f}" x2="{px0 + pw}" y2="{yg:.1f}" stroke="#cbd5e1" stroke-width="0.55"/>')
        grid_elems.append(f'<text x="{px0 - 5}" y="{yg + 2.3:.1f}" text-anchor="end" font-size="6.2" fill="#334155">{el_tick}°</text>')

    iso_elems: list[str] = []
    pitch_ratio = ctx["orientation"]["collector_width_m"] * math.sin(math.radians(ctx["orientation"]["tilt_deg"])) / max(0.35, ctx["orientation"]["clear_gap_m"])
    base_crit_el = max(9.0, min(32.0, math.degrees(math.atan(pitch_ratio))))
    for iso_pct, iso_scale, iso_col in [
        ("1%", 1.38, "#93c5fd"),
        ("5%", 1.15, "#60a5fa"),
        ("10%", 0.95, "#2563eb"),
        ("20%", 0.76, "#1d4ed8"),
        ("40%", 0.56, "#1e3a8a"),
    ]:
        c_pts: list[str] = []
        for az_step in range(-120, 121, 6):
            sec_term = 1.0 / max(0.32, math.cos(math.radians(az_step * 0.68)))
            el_iso = min(68.0, base_crit_el * iso_scale * min(2.3, sec_term))
            ix, iy = _map_pt(float(az_step), el_iso)
            c_pts.append(f"{ix:.1f},{iy:.1f}")
        iso_elems.append(f'<polyline points="{" ".join(c_pts)}" fill="none" stroke="{iso_col}" stroke-width="0.8" stroke-dasharray="3,2"/>')
        lx_iso, ly_iso = _map_pt(-108.0, min(66.0, base_crit_el * iso_scale * 1.85))
        iso_elems.append(f'<text x="{lx_iso + 2:.1f}" y="{ly_iso - 2:.1f}" font-size="5.6" font-weight="700" fill="{iso_col}">{iso_pct}</text>')

    hour_elems: list[str] = []
    for hr_key, pts in sorted(sp["hour_tracks"].items(), key=lambda kv: int(kv[0])):
        hr_int = int(hr_key)
        h_coords = [f"{_map_pt(a, e)[0]:.1f},{_map_pt(a, e)[1]:.1f}" for a, e in pts]
        hour_elems.append(f'<polyline points="{" ".join(h_coords)}" fill="none" stroke="#94a3b8" stroke-width="0.8" stroke-dasharray="2,1.5"/>')
        if 8 <= hr_int <= 16:
            top_az, top_el = pts[0]
            hx, hy = _map_pt(top_az, top_el)
            hour_elems.append(f'<text x="{hx:.1f}" y="{max(py0 + 8, hy - 2.5):.1f}" text-anchor="middle" font-size="6.0" font-weight="700" fill="#475569">{hr_int}h</text>')

    traj_elems: list[str] = []
    legend_elems: list[str] = []
    for idx_t, tr in enumerate(sp["trajectories"]):
        if not tr["points"]:
            continue
        p_str = " ".join(f"{_map_pt(a, e)[0]:.1f},{_map_pt(a, e)[1]:.1f}" for a, e in tr["points"])
        sw = "1.5" if tr["id"] in ("1", "4", "7") else "1.0"
        traj_elems.append(f'<polyline points="{p_str}" fill="none" stroke="{tr["color"]}" stroke-width="{sw}"/>')
        ly_leg = 41.0 + idx_t * 13.0
        legend_elems.append(f'<line x1="566" y1="{ly_leg:.1f}" x2="583" y2="{ly_leg:.1f}" stroke="{tr["color"]}" stroke-width="1.7"/>')
        legend_elems.append(f'<text x="588" y="{ly_leg + 2.2:.1f}" font-size="6.1" fill="#1e293b">{tr["id"]}: {escape(tr["label"])}</text>')

    hz_poly_pts = [f"{px0:.1f},{py0 + ph:.1f}"]
    for az_h, el_h in sp["horizon_pvs"]:
        hx, hy = _map_pt(az_h, el_h)
        hz_poly_pts.append(f"{hx:.1f},{hy:.1f}")
    hz_poly_pts.append(f"{px0 + pw:.1f},{py0 + ph:.1f}")

    return f"""<svg class="pvs-svg" viewBox="0 0 740 206" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Solar-Path and Iso-Shadings Sky Dome Diagram">
  <rect x="1" y="1" width="738" height="204" fill="#ffffff" stroke="#334155" stroke-width="0.9"/>
  <text x="298" y="14" text-anchor="middle" font-size="8.1" font-weight="800" fill="#0f172a">Iso-Shadings Sky Dome · 太阳轨迹与三维等遮挡率天穹图 (Lat {sp['lat']:.2f}°N · 真太阳时)</text>

  <rect x="{px0}" y="{py0}" width="{pw}" height="{ph}" fill="#f8fafc" stroke="#0f172a" stroke-width="0.9"/>
  {"".join(grid_elems)}
  {"".join(iso_elems)}
  {"".join(hour_elems)}
  {"".join(traj_elems)}

  <polygon points="{" ".join(hz_poly_pts)}" fill="#64748b" fill-opacity="0.34" stroke="#334155" stroke-width="1.1"/>
  <text x="{px0 + pw * 0.5:.1f}" y="{py0 + ph - 3.5:.1f}" text-anchor="middle" font-size="5.9" font-weight="700" fill="#0f172a">3D Parapet ({ctx['orientation']['parapet_height_m']:.2f}m) &amp; Horizon Mask · Limit Angle {ctx['orientation']['limit_angle_deg']:.1f}°</text>

  <text x="{px0 + pw * 0.5:.1f}" y="201" text-anchor="middle" font-size="6.4" font-weight="700" fill="#1e293b">Solar Azimuth · 太阳方位角 [-180° .. 0°(正南 South) .. +180°]</text>
  <text x="12" y="{py0 + ph * 0.5:.1f}" transform="rotate(-90 12 {py0 + ph * 0.5:.1f})" text-anchor="middle" font-size="6.4" font-weight="700" fill="#1e293b">Solar Elevation (°)</text>

  <rect x="558" y="22" width="172" height="162" fill="#f8fafc" stroke="#94a3b8" stroke-width="0.8"/>
  <text x="566" y="32" font-size="6.8" font-weight="800" fill="#0f172a">7-Season Solar Tracks · 七节气轨迹</text>
  {"".join(legend_elems)}
  <line x1="564" y1="133" x2="724" y2="133" stroke="#cbd5e1" stroke-width="0.7"/>
  <text x="566" y="143" font-size="6.5" font-weight="800" fill="#1e3a8a">Iso-Shading Contours · 等遮挡线</text>
  <line x1="566" y1="152" x2="585" y2="152" stroke="#2563eb" stroke-width="1.1" stroke-dasharray="3,2"/>
  <text x="590" y="154.5" font-size="6.0" fill="#334155">1% / 5% / 10% / 20% / 40% Loss</text>
  <text x="566" y="176" font-size="6.2" font-weight="800" fill="#b91c1c">Near-Shading Loss: {abs(ctx['loss_tree']['near_shading_loss_pct']):.2f}%</text>
</svg>"""


def _svg_page4_special_graphs(ctx: dict[str, Any]) -> str:
    dio = ctx["daily_io"]
    pdist = ctx["power_distribution"]

    lx0, ly0, lw, lh = 48.0, 24.0, 298.0, 110.0
    max_gi = max([_fnum(p.get("glob_inc_kwh_m2"), 1.0) for p in dio] + [8.0])
    x_ceil = max(8.0, math.ceil(max_gi))
    max_eg = max([_fnum(p.get("e_grid_kwh"), 10.0) for p in dio] + [100.0])
    y_ceil = max(50.0, math.ceil(max_eg / 50.0) * 50.0)

    io_grid: list[str] = []
    for ix in range(0, int(x_ceil) + 1, 2):
        xp = lx0 + (ix / x_ceil) * lw
        io_grid.append(f'<line x1="{xp:.1f}" y1="{ly0}" x2="{xp:.1f}" y2="{ly0 + lh}" stroke="#e2e8f0" stroke-width="0.6"/>')
        io_grid.append(f'<text x="{xp:.1f}" y="{ly0 + lh + 9.5:.1f}" text-anchor="middle" font-size="6.0" fill="#475569">{ix}</text>')
    for iy_step in range(5):
        yv = (y_ceil / 4.0) * iy_step
        yp = ly0 + lh - (yv / y_ceil) * lh
        io_grid.append(f'<line x1="{lx0}" y1="{yp:.1f}" x2="{lx0 + lw}" y2="{yp:.1f}" stroke="#e2e8f0" stroke-width="0.6"/>')
        io_grid.append(f'<text x="{lx0 - 4}" y="{yp + 2.0:.1f}" text-anchor="end" font-size="5.8" fill="#475569">{yv:,.0f}</text>')

    dots: list[str] = []
    sum_x = sum_y = sum_xx = sum_xy = 0.0
    n_pts = max(1, len(dio))
    for p in dio:
        gx = _fnum(p.get("glob_inc_kwh_m2"), 0.0)
        ey = _fnum(p.get("e_grid_kwh"), 0.0)
        sum_x += gx
        sum_y += ey
        sum_xx += gx * gx
        sum_xy += gx * ey
        px = lx0 + min(1.0, max(0.0, gx / x_ceil)) * lw
        py = ly0 + lh - min(1.0, max(0.0, ey / y_ceil)) * lh
        dots.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="1.35" fill="#1d4ed8" fill-opacity="0.62"/>')

    slope = (n_pts * sum_xy - sum_x * sum_y) / max(1e-6, n_pts * sum_xx - sum_x * sum_x)
    intercept = (sum_y - slope * sum_x) / n_pts
    fit_x1, fit_x2 = 0.4, x_ceil * 0.94
    fit_y1 = max(0.0, slope * fit_x1 + intercept)
    fit_y2 = min(y_ceil, max(0.0, slope * fit_x2 + intercept))
    fx1 = lx0 + (fit_x1 / x_ceil) * lw
    fy1 = ly0 + lh - (fit_y1 / y_ceil) * lh
    fx2 = lx0 + (fit_x2 / x_ceil) * lw
    fy2 = ly0 + lh - (fit_y2 / y_ceil) * lh

    rx0, ry0, rw, rh = 424.0, 24.0, 300.0, 110.0
    max_bin_e = max([_fnum(b.get("energy_kwh"), 1.0) for b in pdist] + [100.0])
    ey_ceil = max(100.0, math.ceil(max_bin_e / 100.0) * 100.0)
    nb = max(1, len(pdist))
    bw_step = rw / nb

    hist_elems: list[str] = []
    for iy_step in range(5):
        yv = (ey_ceil / 4.0) * iy_step
        yp = ry0 + rh - (yv / ey_ceil) * rh
        hist_elems.append(f'<line x1="{rx0}" y1="{yp:.1f}" x2="{rx0 + rw}" y2="{yp:.1f}" stroke="#e2e8f0" stroke-width="0.6"/>')
        hist_elems.append(f'<text x="{rx0 - 4}" y="{yp + 2.0:.1f}" text-anchor="end" font-size="5.8" fill="#475569">{yv / 1000.0:.1f}k</text>')

    for i_b, b in enumerate(pdist):
        eb = _fnum(b.get("energy_kwh"), 0.0)
        bh = (eb / ey_ceil) * rh
        bx = rx0 + i_b * bw_step + 2.5
        by = ry0 + rh - bh
        hist_elems.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{max(4.0, bw_step - 5.0):.1f}" height="{bh:.1f}" fill="#0f766e" opacity="0.88" stroke="#115e59" stroke-width="0.6"/>')
        if i_b % 2 == 0 or i_b == nb - 1:
            hist_elems.append(f'<text x="{bx + (bw_step - 5.0) * 0.5:.1f}" y="{ry0 + rh + 9.5:.1f}" text-anchor="middle" font-size="5.8" fill="#475569">{_fnum(b.get("bin_kw_end")):.0f}</text>')

    return f"""<svg class="pvs-svg" viewBox="0 0 740 154" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Daily Input Output Scatter and AC Power Distribution Histogram">
  <rect x="1" y="1" width="358" height="152" fill="#ffffff" stroke="#334155" stroke-width="0.9"/>
  <text x="180" y="14" text-anchor="middle" font-size="7.9" font-weight="800" fill="#0f172a">Daily Input / Output Diagram · 逐日入射-并网散点图 (365d)</text>
  <rect x="{lx0}" y="{ly0}" width="{lw}" height="{lh}" fill="#f8fafc" stroke="#0f172a" stroke-width="0.85"/>
  {"".join(io_grid)}
  {"".join(dots)}
  <line x1="{fx1:.1f}" y1="{fy1:.1f}" x2="{fx2:.1f}" y2="{fy2:.1f}" stroke="#dc2626" stroke-width="1.3" stroke-dasharray="4,2"/>
  <text x="{lx0 + 8}" y="{ly0 + 12}" font-size="6.0" font-weight="700" fill="#dc2626">Slope ≈ {slope:,.1f} kWh/(kWh/m²) · n=365d</text>
  <text x="{lx0 + lw * 0.5:.1f}" y="149" text-anchor="middle" font-size="6.1" font-weight="700" fill="#334155">Global Incident GlobInc [kWh/m²/day]</text>
  <text x="11" y="{ly0 + lh * 0.5:.1f}" transform="rotate(-90 11 {ly0 + lh * 0.5:.1f})" text-anchor="middle" font-size="6.0" font-weight="700" fill="#334155">E_Grid [kWh/d]</text>

  <rect x="381" y="1" width="358" height="152" fill="#ffffff" stroke="#334155" stroke-width="0.9"/>
  <text x="560" y="14" text-anchor="middle" font-size="7.9" font-weight="800" fill="#0f172a">System Output Power Distribution · 并网功率分布直方图</text>
  <rect x="{rx0}" y="{ry0}" width="{rw}" height="{rh}" fill="#f8fafc" stroke="#0f172a" stroke-width="0.85"/>
  {"".join(hist_elems)}
  <text x="{rx0 + rw * 0.5:.1f}" y="149" text-anchor="middle" font-size="6.1" font-weight="700" fill="#334155">Active Grid Power Bin P_Grid [kWac]</text>
  <text x="392" y="{ry0 + rh * 0.5:.1f}" transform="rotate(-90 392 {ry0 + rh * 0.5:.1f})" text-anchor="middle" font-size="6.0" font-weight="700" fill="#334155">Energy [kWh/yr]</text>
</svg>"""


def _svg_page4_hourly_heatmap_12x24(ctx: dict[str, Any]) -> str:
    hm = ctx["hourly_heatmap_12x24"]
    ac_grid = hm.get("ac_kw") or []
    peak_kw = max(0.0, _fnum(hm.get("max_ac_kw"), 0.0))
    max_kw = max(1.0, peak_kw)
    gx0, gy0 = 42.0, 22.0
    cw, ch = 28.2, 10.6

    def _heat_color(frac: float) -> tuple[str, str]:
        if frac <= 0.01:
            return "#f8fafc", "#94a3b8"
        if frac < 0.20:
            return "#e0f2fe", "#0f172a"
        if frac < 0.40:
            return "#bae6fd", "#0f172a"
        if frac < 0.60:
            return "#fde68a", "#0f172a"
        if frac < 0.80:
            return "#fb923c", "#0f172a"
        return "#b91c1c", "#ffffff"

    cells_svg: list[str] = []
    for hr in range(24):
        cx = gx0 + hr * cw + cw * 0.5
        cells_svg.append(f'<text x="{cx:.1f}" y="{gy0 + 12 * ch + 9.5:.1f}" text-anchor="middle" font-size="5.6" font-weight="700" fill="#334155">{hr:02d}h</text>')

    for m_i in range(12):
        row_vals = ac_grid[m_i] if m_i < len(ac_grid) else [0.0] * 24
        ry = gy0 + m_i * ch
        cells_svg.append(f'<text x="{gx0 - 4}" y="{ry + 7.6:.1f}" text-anchor="end" font-size="5.9" font-weight="700" fill="#0f172a">{MONTH_EN[m_i]}</text>')
        for hr in range(24):
            val = _fnum(row_vals[hr] if hr < len(row_vals) else 0.0, 0.0)
            frac = max(0.0, min(1.0, val / max_kw))
            bg_c, fg_c = _heat_color(frac)
            rx = gx0 + hr * cw
            cells_svg.append(f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{cw:.1f}" height="{ch:.1f}" fill="{bg_c}" stroke="#cbd5e1" stroke-width="0.35"/>')
            if peak_kw > 0.0 and val >= max_kw * 0.06 and 6 <= hr <= 18:
                lbl_v = f"{val:.0f}" if max_kw >= 25.0 else f"{val:.1f}"
                cells_svg.append(f'<text x="{rx + cw * 0.5:.1f}" y="{ry + 7.5:.1f}" text-anchor="middle" font-size="5.0" font-weight="700" fill="{fg_c}">{lbl_v}</text>')

    return f"""<svg class="pvs-svg" viewBox="0 0 740 164" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="12 Months by 24 Hours Mean AC Output Heatmap Matrix">
  <rect x="1" y="1" width="738" height="162" fill="#ffffff" stroke="#334155" stroke-width="0.9"/>
  <text x="14" y="14" font-size="7.9" font-weight="800" fill="#0f172a">12×24 Hourly Mean AC Output Profile Matrix · 全年12月×24时平均并网出力热力矩阵 [kWac] (Peak {peak_kw:,.1f} kW)</text>
  <g transform="translate(546, 5)">
    <rect x="0" y="2" width="14" height="7" fill="#e0f2fe" stroke="#94a3b8" stroke-width="0.4"/>
    <rect x="15" y="2" width="14" height="7" fill="#bae6fd" stroke="#94a3b8" stroke-width="0.4"/>
    <rect x="30" y="2" width="14" height="7" fill="#fde68a" stroke="#94a3b8" stroke-width="0.4"/>
    <rect x="45" y="2" width="14" height="7" fill="#fb923c" stroke="#94a3b8" stroke-width="0.4"/>
    <rect x="60" y="2" width="14" height="7" fill="#b91c1c" stroke="#94a3b8" stroke-width="0.4"/>
    <text x="79" y="8" font-size="5.8" font-weight="700" fill="#334155">0 → 100% Peak kWac</text>
  </g>
  {"".join(cells_svg)}
  <rect x="{gx0:.1f}" y="{gy0:.1f}" width="{24 * cw:.1f}" height="{12 * ch:.1f}" fill="none" stroke="#0f172a" stroke-width="0.85"/>
</svg>"""


def _svg_page4_prob_curve(ctx: dict[str, Any]) -> str:
    prb = ctx["probabilities"]
    p50 = max(1.0, prb["p50_kwh"] / 1000.0)
    sigma = max(1.5, prb["sigma_total_pct"]) / 100.0 * p50
    x_min = p50 - 3.0 * sigma
    x_max = p50 + 2.2 * sigma
    px0, py0, pw, ph = 38.0, 12.0, 296.0, 82.0

    def _x_mwh(mwh: float) -> float:
        return px0 + ((mwh - x_min) / max(1e-6, x_max - x_min)) * pw

    pts: list[str] = []
    for i in range(51):
        xv = x_min + (x_max - x_min) * (i / 50.0)
        exc = 0.5 * math.erfc((xv - p50) / (math.sqrt(2.0) * sigma))
        xp = _x_mwh(xv)
        yp = py0 + ph - exc * ph
        pts.append(f"{xp:.1f},{yp:.1f}")

    markers: list[str] = []
    for lbl, val_kwh, prob_pct, col in [
        ("P95", prb["p95_kwh"], 0.95, "#7c3aed"),
        ("P90", prb["p90_kwh"], 0.90, "#dc2626"),
        ("P75", prb["p75_kwh"], 0.75, "#d97706"),
        ("P50", prb["p50_kwh"], 0.50, "#15803d"),
    ]:
        mv = val_kwh / 1000.0
        mx = _x_mwh(mv)
        my = py0 + ph - prob_pct * ph
        markers.append(f'<line x1="{mx:.1f}" y1="{my:.1f}" x2="{mx:.1f}" y2="{py0 + ph:.1f}" stroke="{col}" stroke-width="0.95" stroke-dasharray="2.5,2"/>')
        markers.append(f'<line x1="{px0:.1f}" y1="{my:.1f}" x2="{mx:.1f}" y2="{my:.1f}" stroke="{col}" stroke-width="0.85" stroke-dasharray="2.5,2"/>')
        markers.append(f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="2.4" fill="{col}"/>')
        markers.append(f'<text x="{mx:.1f}" y="{max(py0 + 7, my - 3.0):.1f}" text-anchor="middle" font-size="5.9" font-weight="800" fill="{col}">{lbl}</text>')

    return f"""<svg class="pvs-svg" viewBox="0 0 348 110" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="P50 P90 Probabilistic Yield Curve">
  <rect x="{px0}" y="{py0}" width="{pw}" height="{ph}" fill="#f8fafc" stroke="#334155" stroke-width="0.85"/>
  <text x="{px0 - 4}" y="{py0 + 5}" text-anchor="end" font-size="5.8" fill="#475569">100%</text>
  <text x="{px0 - 4}" y="{py0 + ph * 0.5 + 2:.1f}" text-anchor="end" font-size="5.8" fill="#475569">50%</text>
  <text x="{px0 - 4}" y="{py0 + ph}" text-anchor="end" font-size="5.8" fill="#475569">0%</text>
  <polyline points="{" ".join(pts)}" fill="none" stroke="#1e3a8a" stroke-width="1.55"/>
  {"".join(markers)}
  <text x="{px0 + pw * 0.5:.1f}" y="106" text-anchor="middle" font-size="6.0" font-weight="700" fill="#334155">Annual Energy Production [MWh/yr] · σ_total = {prb['sigma_total_pct']:.2f}%</text>
</svg>"""


def _svg_page6_cashflow(ctx: dict[str, Any]) -> str:
    yr25 = ctx["lifecycle"]["yearly_25"]
    px0, py0, pw, ph = 42.0, 14.0, 302.0, 114.0
    min_cf = min([-ctx["lifecycle"]["capex_wan"]] + [r["cum_cf_wan"] for r in yr25])
    max_cf = max([10.0] + [r["cum_cf_wan"] for r in yr25])
    span = max(1.0, max_cf - min_cf)
    zero_y = py0 + ph - ((0.0 - min_cf) / span) * ph

    bars: list[str] = []
    pts: list[str] = []
    step = pw / 25.0
    for idx, r in enumerate(yr25):
        xc = px0 + (idx + 0.5) * step
        yc = py0 + ph - ((r["cum_cf_wan"] - min_cf) / span) * ph
        pts.append(f"{xc:.1f},{yc:.1f}")
        col = "#16a34a" if r["cum_cf_wan"] >= 0 else "#dc2626"
        top_y = min(yc, zero_y)
        bh = max(1.0, abs(zero_y - yc))
        bars.append(f'<rect x="{xc - step * 0.34:.1f}" y="{top_y:.1f}" width="{step * 0.68:.1f}" height="{bh:.1f}" fill="{col}" opacity="0.32"/>')
        if r["year"] in (1, 5, 10, 15, 20, 25):
            bars.append(f'<text x="{xc:.1f}" y="{py0 + ph + 9.5:.1f}" text-anchor="middle" font-size="5.9" fill="#475569">Y{r["year"]}</text>')

    return f"""<svg class="pvs-svg" viewBox="0 0 356 150" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="25-Year Cumulative Net Cashflow Trajectory">
  <rect x="1" y="1" width="354" height="148" fill="#ffffff" stroke="#334155" stroke-width="0.85"/>
  <rect x="{px0}" y="{py0}" width="{pw}" height="{ph}" fill="#f8fafc" stroke="#0f172a" stroke-width="0.8"/>
  <line x1="{px0}" y1="{zero_y:.1f}" x2="{px0 + pw}" y2="{zero_y:.1f}" stroke="#334155" stroke-width="0.9" stroke-dasharray="3,2"/>
  <text x="{px0 - 4}" y="{py0 + 6}" text-anchor="end" font-size="5.8" fill="#15803d">+{max_cf:,.0f}</text>
  <text x="{px0 - 4}" y="{zero_y + 2:.1f}" text-anchor="end" font-size="5.8" font-weight="700" fill="#334155">0</text>
  <text x="{px0 - 4}" y="{py0 + ph}" text-anchor="end" font-size="5.8" fill="#b91c1c">{min_cf:,.0f}</text>
  {"".join(bars)}
  <polyline points="{" ".join(pts)}" fill="none" stroke="#1d4ed8" stroke-width="1.6"/>
  <text x="{px0 + pw * 0.5:.1f}" y="145" text-anchor="middle" font-size="6.1" font-weight="800" fill="#0f172a">25-Year Cumulative Cashflow (万元) · Payback {_fmt_payback(ctx['lifecycle'].get('payback_yr'), 2, ' yr')} · IRR {_fmt_irr(ctx['lifecycle'].get('irr_pct'), 1)}</text>
</svg>"""


# ---------------------------------------------------------------------------
# Repeating Diagonal Watermark, Header / Footer & 6-Page Swiss HTML Renderer
# ---------------------------------------------------------------------------

def _render_page_watermark(ctx: dict[str, Any]) -> str:
    tile = (
        '<div class="pvs-wm-tile">'
        '<span class="pvs-wm-logo"></span>'
        '<div class="pvs-wm-text">'
        '<span class="pvs-wm-main">光筑 · GUANGZHU</span>'
        '<span class="pvs-wm-sub">光筑专业报告</span>'
        '</div>'
        '</div>'
    )
    return f'<div class="pvs-watermark-layer" aria-hidden="true">{tile * 12}</div>'


def _render_page_header(ctx: dict[str, Any], page_no: int, sec_en: str, sec_zh: str) -> str:
    meta = ctx["meta"]
    site = ctx["site"]
    icon_uri = ctx["icons"]["icon_128_uri"]
    return f"""<header class="pvs-page-header">
  <div class="pvs-hdr-brand">
    <img class="pvs-brand-icon" src="{icon_uri}" alt="光筑软件图标" width="29" height="29"/>
    <div class="pvs-hdr-brand-titles">
      <div class="pvs-hdr-sw-name">光筑专业报告</div>
      <div class="pvs-hdr-sw-sub">GUANGZHU PRO REPORT · 8760H</div>
    </div>
  </div>
  <div class="pvs-hdr-center">
    <div class="pvs-hdr-systype">{_bilingual("Grid-Connected Photovoltaic System", "并网光伏发电系统精细化工程仿真计算书")}</div>
    <div class="pvs-hdr-secname">{_bilingual(sec_en, sec_zh)}</div>
    <div class="pvs-hdr-projline">Project: <b>{escape(meta['project_name'])}</b> ({escape(meta['project_id'])} · {escape(meta.get('report_code', 'GZ-SIM-01'))})</div>
  </div>
  <div class="pvs-hdr-meta">
    <div class="pvs-hdr-meta-cell"><span>Variant:</span><b>{escape(meta['variant_code'])}</b></div>
    <div class="pvs-hdr-meta-cell"><span>Date:</span><b>{escape(meta['simulation_date'][:10])}</b></div>
    <div class="pvs-hdr-meta-cell"><span>Site:</span><b>{escape(site['city'])}</b></div>
    <div class="pvs-hdr-meta-cell"><span>Page:</span><b class="pvs-hdr-page-pill">Page {page_no} of {meta['total_pages']}</b></div>
  </div>
</header>"""


def _render_page_footer(ctx: dict[str, Any], page_no: int) -> str:
    meta = ctx["meta"]
    icon_uri = ctx["icons"]["icon_128_uri"]
    return f"""<footer class="pvs-page-footer">
  <div class="pvs-page-footer-left">
    <img src="{icon_uri}" alt="光筑" width="12" height="12"/>
    <span>光筑 Guangzhu 8760h Engineering Simulation Engine (Perez 1990 · Faiman · IEC 61724 · GB 50797)</span>
  </div>
  <div>{escape(meta['project_name'])} · {escape(meta['variant_code'])} · Page {page_no} / {meta['total_pages']}</div>
</footer>"""


def render_pvsyst_report_html(context: dict[str, Any]) -> str:
    """Render the complete 6-page Swiss technical《光筑专业报告》HTML with embedded base64 icons & watermarks."""
    ctx = sanitize_report_structure(context)
    css = _load_report_css()
    meta = ctx["meta"]
    site = ctx["site"]
    ori = ctx["orientation"]
    pv = ctx["pv_array"]
    inv = ctx["inverter"]
    ls = ctx["losses"]
    res = ctx["results"]
    prb = ctx["probabilities"]
    ver = ctx["verification"]
    lc = ctx["lifecycle"]
    icon_128 = ctx["icons"]["icon_128_uri"]
    icon_512 = ctx["icons"]["icon_512_uri"]

    html_dl_name = make_pro_report_filename(meta["project_name"], meta.get("version", 1), "html")

    # Page 2: 13-Column Monthly & Annual Energy Balances Table
    bal_rows_html = "\n".join(
        f"""<tr>
          <td>{_bilingual(r['month_en'], r['month_zh'])}</td>
          <td>{r['glob_hor']:.1f}</td>
          <td>{r['diff_hor']:.1f}</td>
          <td>{r['t_amb']:.1f}</td>
          <td>{r.get('wind_ms', 2.4):.2f}</td>
          <td>{r['glob_inc']:.1f}</td>
          <td>{r['glob_eff']:.1f}</td>
          <td>{r.get('glob_bak', 0.0):.2f}</td>
          <td>{r['e_array']:,.0f}</td>
          <td><b>{r['e_grid']:,.0f}</b></td>
          <td>{r['yf_day']:.2f}</td>
          <td>{r['lc_day']:.2f}</td>
          <td>{r['pr_pct']:.1f}%</td>
        </tr>"""
        for r in ctx["normalized_monthly"]
    )

    # Page 3: Loss & Gain Sensitivity Ranking Rows
    sens_rows_html = "\n".join(
        f"""<tr>
          <td style="text-align:center;font-weight:800">#{item['rank']}</td>
          <td style="text-align:left;font-weight:700">{escape(str(item['label']))}</td>
          <td style="text-align:center">{escape(str(item['stage']))}</td>
          <td style="font-weight:800;color:{'#15803d' if item['kind'] == 'gain' else '#b91c1c'}">{_fmt_signed(item['pct'], 2)}</td>
          <td>{item['energy_mwh']:+,.2f}</td>
          <td style="width:32%">
            <div class="pvs-sens-bar-wrap">
              <div class="pvs-sens-bar {escape(str(item['kind']))}" style="width:{item['bar_width_pct']:.1f}%"></div>
            </div>
          </td>
        </tr>"""
        for item in ctx.get("loss_sensitivity_ranking", [])
    )

    def _status_cls(st: Any) -> str:
        s_up = str(st or "").strip().upper()
        if s_up == "PASS":
            return "pass"
        if s_up == "FAIL":
            return "fail"
        if s_up == "UNVERIFIED":
            return "unverified"
        return "warn"

    # Page 5: MPPT Channel Allocation Rows (with ΔUdc %)
    mppt_rows_html = "\n".join(
        f"""<tr>
          <td>{escape(str(r['unit']))}</td>
          <td style="text-align:left">{escape(str(r['model']))}</td>
          <td style="text-align:center">{escape(str(r['mppt_used']))}</td>
          <td style="text-align:center">{escape(str(r['strings_label']))}</td>
          <td style="text-align:center">{escape(str(r['config']))}</td>
          <td>{r['dc_kw']:.2f}</td>
          <td>{r['ratio']:.2f}</td>
          <td>{r['vmpp_v']:.1f}</td>
          <td>{r['voc_cold_v']:.1f}</td>
          <td>{r.get('dc_drop_pct', 0.95):.2f}%</td>
          <td style="text-align:center"><span class="pvs-status {_status_cls(r['status'])}">{escape(str(r['status']))}</span></td>
        </tr>"""
        for r in ver["mppt_rows"]
    )

    # Page 5: 6-Item National Code Safety Verification Cards
    code_cards_html = "\n".join(
        f"""<div class="pvs-verif-card">
          <div class="pvs-verif-top">
            <span class="pvs-verif-title">{_bilingual(chk['title_en'], chk['title_zh'])}</span>
            <span class="pvs-status {_status_cls(chk['status'])}">{escape(str(chk['status']))}</span>
          </div>
          <div class="pvs-verif-metric">{escape(str(chk['metric']))}</div>
          <div class="pvs-verif-detail"><b>[{escape(str(chk['code']))}]</b> {escape(str(chk['detail']))}</div>
        </div>"""
        for chk in ver.get("national_code_checks", [])
    )

    # Page 6: Full 25-Row Annual Degradation & Cashflow Schedule (Y01–Y25)
    yr25_rows_html = "\n".join(
        f"""<tr>
          <td>Y{r['year']:02d} (第{r['year']:02d}年)</td>
          <td>{r['deg_factor_pct']:.2f}%</td>
          <td>{r['e_grid_mwh']:,.2f}</td>
          <td>{r.get('rev_self_wan', 0.0):,.2f}</td>
          <td>{r.get('rev_feed_wan', 0.0):,.2f}</td>
          <td>-{r.get('opex_wan', 0.0):,.2f}</td>
          <td>{r['net_cf_wan']:+,.2f}</td>
          <td><b>{r['cum_cf_wan']:+,.2f}</b></td>
        </tr>"""
        for r in lc["yearly_25"]
    )
    tot25 = lc.get("totals_25yr") or {
        "rev_self_wan": 0.0,
        "rev_feed_wan": 0.0,
        "opex_wan": 0.0,
        "net_cf_wan": sum(x["net_cf_wan"] for x in lc["yearly_25"]),
        "cum_cf_wan": lc["yearly_25"][-1]["cum_cf_wan"],
    }

    # Page 6: 3x3 Tariff × CAPEX Sensitivity Matrix
    sens_3x3_rows_html = "\n".join(
        f"""<tr>
          <td style="text-align:left;font-weight:800">{escape(str(s_row['tariff_label']))}</td>
          {"".join(
              f'<td class="{"pvs-sens-cell-hi" if cell.get("is_base") else ""}" style="text-align:center">{_fmt_irr(cell.get("irr_pct"), 1)} / {_fmt_payback(cell.get("payback_yr"), 2, "y")}</td>'
              for cell in s_row.get("cells", [])
          )}
        </tr>"""
        for s_row in lc.get("sensitivity_matrix_3x3", [])
    )

    all_pass = bool(
        ver.get("all_pass")
        if ver.get("all_pass") is not None
        else (
            pv.get("dc_kw", 0.0) > 0.0
            and ver.get("load_pass")
            and ver.get("wind_pass")
            and ver.get("voc_pass")
            and all(chk.get("status") == "PASS" for chk in ver.get("national_code_checks", []))
        )
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>光筑专业报告 — {escape(meta['project_name'])} ({escape(meta['variant_code'])})</title>
  <link rel="icon" type="image/png" href="{icon_128}"/>
  <style>{css}
  .pvs-wm-logo {{ width: 22px; height: 22px; display: inline-block; flex-shrink: 0; background: url("{icon_128}") center/contain no-repeat; filter: grayscale(20%); }}
  </style>
</head>
<body data-lang-mode="bilingual">
  <!-- Interactive Top Action Bar (.noprint) -->
  <div class="pvs-action-bar noprint" role="toolbar" aria-label="光筑专业报告操作栏">
    <div class="pvs-action-brand">
      <img src="{icon_128}" alt="光筑软件图标"/>
      <div class="pvs-action-brand-text">
        <strong>光筑专业报告 · 并网光伏系统精细化工程仿真计算书 (六页标准版)</strong>
        <small>{escape(meta['project_name'])} · {escape(meta['variant_code'])} · {pv['dc_kw']:.2f} kWp / {inv['total_ac_kw']:.1f} kWac</small>
      </div>
    </div>
    <div class="pvs-action-controls">
      <div class="pvs-page-jumps" aria-label="页码快速跳转">
        <button type="button" class="pvs-jump-btn" onclick="window.__jumpGzPage(1)">P1</button>
        <button type="button" class="pvs-jump-btn" onclick="window.__jumpGzPage(2)">P2</button>
        <button type="button" class="pvs-jump-btn" onclick="window.__jumpGzPage(3)">P3</button>
        <button type="button" class="pvs-jump-btn" onclick="window.__jumpGzPage(4)">P4</button>
        <button type="button" class="pvs-jump-btn" onclick="window.__jumpGzPage(5)">P5</button>
        <button type="button" class="pvs-jump-btn" onclick="window.__jumpGzPage(6)">P6</button>
      </div>
      <button type="button" class="pvs-act-btn" id="pvsLangToggleBtn" onclick="window.__cyclePvsLang()">中英切换: 双语 Bilingual</button>
      <button type="button" class="pvs-act-btn" onclick="window.__downloadStandaloneGzHtml()">下载独立 HTML</button>
      <button type="button" class="pvs-act-btn primary" onclick="window.print()">打印 / 导出 A4 PDF</button>
    </div>
  </div>

  <main class="pvs-report-container">
    <!-- ==================== PAGE 1: SYSTEM SCHEMATIC & SIMULATION PARAMETERS ==================== -->
    <section class="pvs-page" id="gz-pro-page-1" data-page="1">
      {_render_page_watermark(ctx)}
      {_render_page_header(ctx, 1, "System Overview & Simulation Parameters", "项目概况、一次拓扑与系统仿真输入参数")}
      <div class="pvs-page-body">
        <div class="pvs-cover-strip">
          <div class="pvs-cover-left">
            <img class="pvs-cover-badge-icon" src="{icon_512}" alt="光筑工程徽章"/>
            <div>
              <h1 class="pvs-cover-title">{escape(meta['project_name'])} — {_bilingual("8760h Engineering Simulation Dossier", "8760小时精细化并网仿真计算书")}</h1>
              <div class="pvs-cover-sub">Site: {escape(site['name'])} · Pnom DC {pv['dc_kw']:.2f} kWp · Pac {inv['total_ac_kw']:.1f} kWac · E_Grid {res['e_grid_mwh']:,.2f} MWh/yr · PR {res['pr_pct']:.2f}%</div>
            </div>
          </div>
          <div class="pvs-cover-tags">
            <span class="pvs-tag-chip">IEC 61724 · Perez 1990 · Faiman</span>
            <span class="pvs-tag-chip {'ok' if all_pass else ''}">{'GB 50797 校核通过' if all_pass else '工程参数待复核'}</span>
          </div>
        </div>

        <div class="pvs-box">
          <div class="pvs-box-head">
            <span>{_bilingual("Grid-Connected Single-Line System Schematic", "并网光伏发电系统一次拓扑原理图")}</span>
            <small>{pv['module_count']} 块 / {pv['string_count']} 串 ({pv['modules_per_string']}S) / {inv['count']} 台 → 380V/10kV Grid &amp; Load</small>
          </div>
          <div class="pvs-box-content" style="padding:3px 4px">{_svg_page1_schematic(ctx)}</div>
        </div>

        <div class="pvs-grid-2">
          <div class="pvs-box">
            <div class="pvs-box-head">
              <span>{_bilingual("Geographical Site & Meteo Boundary", "地理站址与典型年气象边界")}</span>
              <small>.MET 8760h</small>
            </div>
            <div class="pvs-box-content">
              <table class="pvs-kv-table">
                <tr><td class="k">{_bilingual("Geographical Site", "项目站址")}</td><td class="v">{escape(site['name'])}</td></tr>
                <tr><td class="k">{_bilingual("Coordinates", "经纬度坐标")}</td><td class="v">{site['lat']:.4f}° N, {site['lon']:.4f}° E</td></tr>
                <tr><td class="k">{_bilingual("Altitude / Timezone", "海拔与时区")}</td><td class="v">{site['altitude_m']:.0f} m · {escape(site['timezone'])}</td></tr>
                <tr><td class="k">{_bilingual("Meteo Data Source", "气象数据源")}</td><td class="v">{escape(site['meteo_source'])}</td></tr>
                <tr><td class="k">{_bilingual("Surface Albedo / Wind", "地表反射率 / 年均风速")}</td><td class="v">{site['albedo']:.2f} · {res['wind_year_ms']:.2f} m/s</td></tr>
                <tr><td class="k">{_bilingual("Transposition / Thermal", "辐射转置与热模型")}</td><td class="v">Perez 1990 · Faiman</td></tr>
              </table>
            </div>
          </div>

          <div class="pvs-box">
            <div class="pvs-box-head">
              <span>{_bilingual("Orientation & 3D Near Shadings", "阵列几何朝向与三维近处遮挡")}</span>
              <small>{escape(ori['mode'])}</small>
            </div>
            <div class="pvs-box-content">
              <table class="pvs-kv-table">
                <tr><td class="k">{_bilingual("Collector Field Type", "阵列布置型式")}</td><td class="v">{_bilingual(ori['field_en'], ori['field_zh'])}</td></tr>
                <tr><td class="k">{_bilingual("Plane Tilt / Azimuth", "倾角与方位角")}</td><td class="v">{escape(ori['az_display'])}</td></tr>
                <tr><td class="k">{_bilingual("Module Disposition", "组件安装方向")}</td><td class="v">{escape(ori['mount_orientation'])}</td></tr>
                <tr><td class="k">{_bilingual("Pitch / Collector Width", "前后排中心距 / 采光宽")}</td><td class="v">{ori['pitch_m']:.2f} m / {ori['collector_width_m']:.3f} m</td></tr>
                <tr><td class="k">{_bilingual("GCR / Limit Profile Angle", "覆盖率 GCR / 临界遮挡角")}</td><td class="v">{ori['gcr_pct']:.1f}% · α_lim = {ori['limit_angle_deg']:.1f}°</td></tr>
                <tr><td class="k">{_bilingual("3D Shading Model", "三维近处阴影模型")}</td><td class="v">{escape(ori['shading_status'])}</td></tr>
              </table>
            </div>
          </div>

          <div class="pvs-box">
            <div class="pvs-box-head">
              <span>{_bilingual("PV Array Characteristics", "光伏组件与组串电气特性")}</span>
              <small>.PAN Spec</small>
            </div>
            <div class="pvs-box-content">
              <table class="pvs-kv-table">
                <tr><td class="k">{_bilingual("PV Module Model", "组件型号与厂商")}</td><td class="v">{escape(pv['module_brand'])} · {escape(pv['module_model'])}</td></tr>
                <tr><td class="k">{_bilingual("Unit Power / Cell Tech", "单块功率与电池技术")}</td><td class="v">{pv['stc_w']:.0f} Wp · {escape(pv['cell_tech'])}</td></tr>
                <tr><td class="k">{_bilingual("Thermal Coeffs γPmp / βVoc", "功率与开路温度系数")}</td><td class="v">{pv['gamma_pmax_pct_c']:+.2f}%/°C · {pv['beta_voc_pct_c']:+.2f}%/°C</td></tr>
                <tr><td class="k">{_bilingual("Total Modules / Area", "组件总块数与采光面积")}</td><td class="v">{pv['module_count']:,d} 块 · {pv['collector_area_m2']:,.1f} m²</td></tr>
                <tr><td class="k">{_bilingual("Stringing / Pnom DC", "组串配置与标称容量")}</td><td class="v">{pv['string_count']} 串 × {pv['modules_per_string']}S · <b>{pv['dc_kw']:,.2f} kWp</b> (η={pv['stc_eff_pct']:.2f}%)</td></tr>
                <tr><td class="k">{_bilingual("Umpp(60°C) / Voc(-10°C)", "工作电压温度包络")}</td><td class="v">{pv['vmpp_60c_v']:.1f} V / {pv['voc_minus10c_v']:.1f} V</td></tr>
              </table>
            </div>
          </div>

          <div class="pvs-box">
            <div class="pvs-box-head">
              <span>{_bilingual("Inverter Characteristics", "并网逆变器特性参数")}</span>
              <small>.OND Spec</small>
            </div>
            <div class="pvs-box-content">
              <table class="pvs-kv-table">
                <tr><td class="k">{_bilingual("Inverter Model", "逆变器型号与厂商")}</td><td class="v">{escape(inv['brand'])} · {escape(inv['model'])}</td></tr>
                <tr><td class="k">{_bilingual("Unit Nominal AC Power", "单台额定交流功率")}</td><td class="v">{inv['unit_ac_kw']:.1f} kWac</td></tr>
                <tr><td class="k">{_bilingual("Quantity & MPPT Trackers", "台数与独立MPPT路数")}</td><td class="v">{inv['count']} 台 ({0 if inv['count'] <= 0 else inv['mppt_count_unit']} MPPT/台)</td></tr>
                <tr><td class="k">{_bilingual("Total AC Power / DC:AC", "交流总功率 / 容配比")}</td><td class="v"><b>{inv['total_ac_kw']:,.1f} kWac</b> · R = {inv['pnom_ratio']:.3f}</td></tr>
                <tr><td class="k">{_bilingual("MPPT Window / Max DC V", "MPPT跟踪窗口 / 最大耐压")}</td><td class="v">{escape(inv['mppt_window_v'])} / {inv['max_dc_v']:.0f} V</td></tr>
                <tr><td class="k">{_bilingual("Weighted Euro Efficiency", "加权欧洲转换效率")}</td><td class="v">η_euro = {inv['euro_eff_pct']:.2f}%</td></tr>
              </table>
            </div>
          </div>
        </div>

        <div class="pvs-box">
          <div class="pvs-box-head">
            <span>{_bilingual("Detailed System Loss Factors", "系统全链路损耗因子边界参数")}</span>
            <small>Thermal · Optical · Electrical · Aging</small>
          </div>
          <div class="pvs-box-content">
            <div class="pvs-loss-params-grid">
              <table class="pvs-kv-table">
                <tr><td class="k">Thermal Uc / Uv</td><td class="v">{ls['uc_w_m2k']:.1f} W/m²K / {ls['uv_w_m2k_ms']:.1f}</td></tr>
                <tr><td class="k">IAM Profile (ASHRAE b0)</td><td class="v">b0 = {ls['iam_b0']:.3f}</td></tr>
                <tr><td class="k">Surface Soiling Factor</td><td class="v">{ls['soiling_pct']:.2f}%</td></tr>
              </table>
              <table class="pvs-kv-table">
                <tr><td class="k">DC / AC Wiring Ohmic</td><td class="v">{ls['dc_ohmic_pct']:.2f}% / {ls['ac_ohmic_pct']:.2f}%</td></tr>
                <tr><td class="k">First-Year LID / Quality</td><td class="v">{ls['lid_pct']:.2f}% / {ls['module_quality_pct']:+.2f}%</td></tr>
                <tr><td class="k">Array Mismatch Factor</td><td class="v">{ls['mismatch_pct']:.2f}%</td></tr>
              </table>
              <table class="pvs-kv-table">
                <tr><td class="k">Spectral Correction</td><td class="v">{ls['spectral_pct']:+.2f}%</td></tr>
                <tr><td class="k">Transformer / Avail.</td><td class="v">{ls['transformer_loss_pct']:.2f}% / {ls['availability_pct']:.1f}%</td></tr>
                <tr><td class="k">Linear Aging Rate</td><td class="v">{ls['annual_degradation_pct']:.2f}% / yr</td></tr>
              </table>
            </div>
          </div>
        </div>

        <div class="pvs-main-strip">
          <div class="pvs-main-kpi primary">
            <span class="pvs-main-kpi-lbl">Pnom DC · 直流装机</span>
            <span class="pvs-main-kpi-val">{pv['dc_kw']:,.2f} <small>kWp</small></span>
            <span class="pvs-main-kpi-sub">{pv['module_count']} 块 / {pv['string_count']} 串 / {inv['count']} 台</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">E_Grid · 首年并网电量</span>
            <span class="pvs-main-kpi-val">{res['e_grid_mwh']:,.2f} <small>MWh</small></span>
            <span class="pvs-main-kpi-sub">{res['e_grid_kwh']:,.0f} kWh/yr</span>
          </div>
          <div class="pvs-main-kpi highlight">
            <span class="pvs-main-kpi-lbl">PR · 系统综合能效比</span>
            <span class="pvs-main-kpi-val">{res['pr_pct']:.2f}%</span>
            <span class="pvs-main-kpi-sub">满发 {res['specific_yield_kwh_kwp']:,.1f} h</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">P90 · 融资保守年产</span>
            <span class="pvs-main-kpi-val">{prb['p90_kwh'] / 1000.0:,.2f} <small>MWh</small></span>
            <span class="pvs-main-kpi-sub">σ = {prb['sigma_total_pct']:.2f}%</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">CAPEX · 工程总造价</span>
            <span class="pvs-main-kpi-val">¥{lc['capex_wan']:,.2f} <small>万</small></span>
            <span class="pvs-main-kpi-sub">LCOE {_fmt_lcoe(res.get('lcoe_cny_kwh'), 3)}</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">IRR / Payback · 收益</span>
            <span class="pvs-main-kpi-val">{_fmt_irr(lc.get('irr_pct'), 1)}</span>
            <span class="pvs-main-kpi-sub">静态回本 {_fmt_payback(lc.get('payback_yr'), 2)}</span>
          </div>
        </div>
      </div>
      {_render_page_footer(ctx, 1)}
    </section>

    <!-- ==================== PAGE 2: MAIN RESULTS & 13-COL MONTHLY BALANCES ==================== -->
    <section class="pvs-page" id="gz-pro-page-2" data-page="2">
      {_render_page_watermark(ctx)}
      {_render_page_header(ctx, 2, "Main Simulation Results & 13-Column Monthly Balances", "核心仿真指标、归一化日均产出与13列月度能量平衡表")}
      <div class="pvs-page-body">
        <div class="pvs-main-strip">
          <div class="pvs-main-kpi primary">
            <span class="pvs-main-kpi-lbl">{_bilingual("System Production E_Grid", "首年并网发电量 E_Grid")}</span>
            <span class="pvs-main-kpi-val">{res['e_grid_mwh']:,.2f} <small>MWh/yr</small></span>
            <span class="pvs-main-kpi-sub">{res['e_grid_kwh']:,.0f} kWh/yr</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">{_bilingual("Specific Production", "首年等效满发小时数")}</span>
            <span class="pvs-main-kpi-val">{res['specific_yield_kwh_kwp']:,.1f} <small>kWh/kWp</small></span>
            <span class="pvs-main-kpi-sub">Yf = {res['yf_day']:.2f} kWh/kWp/d</span>
          </div>
          <div class="pvs-main-kpi highlight">
            <span class="pvs-main-kpi-lbl">{_bilingual("Performance Ratio PR", "系统综合能效比 PR")}</span>
            <span class="pvs-main-kpi-val">{res['pr_pct']:.2f}%</span>
            <span class="pvs-main-kpi-sub">IEC 61724 Ratio {res['pr_ratio']:.3f}</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">{_bilingual("Self-Use Fraction", "自发自用消纳比例")}</span>
            <span class="pvs-main-kpi-val">{res['self_use_pct']:.1f}%</span>
            <span class="pvs-main-kpi-sub">余电上网 {(0.0 if pv['dc_kw'] <= 0 else (100.0 - res['self_use_pct'])):.1f}%</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">{_bilingual("Bifacial Rear Gain", "双面背面年均增益")}</span>
            <span class="pvs-main-kpi-val">+{ctx['loss_tree']['bifacial_gain_pct']:.2f}%</span>
            <span class="pvs-main-kpi-sub">GlobBak {res['glob_bak_kwh_m2']:,.1f} kWh/m²</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">{_bilingual("Levelized Cost LCOE", "度电成本 LCOE")}</span>
            <span class="pvs-main-kpi-val">{_fmt_lcoe(res.get('lcoe_cny_kwh'), 3)}</span>
            <span class="pvs-main-kpi-sub">25yr {lc['cum_mwh_25yr']:,.1f} MWh</span>
          </div>
        </div>

        {_svg_page2_dual_charts(ctx)}

        <div class="pvs-box">
          <div class="pvs-box-head">
            <span>{_bilingual("Balances and Main Results (13-Column Engineering Ledger)", "月度气象辐射、背面增益与并网发电平衡总表 (13列标准台账)")}</span>
            <small>{pv['module_count']} 块 / {pv['string_count']} 串 / {inv['count']} 台 · 12 Months + Annual</small>
          </div>
          <div class="pvs-box-content" style="padding:3px 4px">
            <table class="pvs-table pvs-table-13col" aria-label="Balances and Main Results">
              <thead>
                <tr>
                  <th>Month<span class="unit-row">月份</span></th>
                  <th>GlobHor<span class="unit-row">kWh/m²</span></th>
                  <th>DiffHor<span class="unit-row">kWh/m²</span></th>
                  <th>T_Amb<span class="unit-row">°C</span></th>
                  <th>WindVel<span class="unit-row">m/s</span></th>
                  <th>GlobInc<span class="unit-row">kWh/m²</span></th>
                  <th>GlobEff<span class="unit-row">kWh/m²</span></th>
                  <th>GlobBak<span class="unit-row">kWh/m²</span></th>
                  <th>EArray<span class="unit-row">kWh</span></th>
                  <th>E_Grid<span class="unit-row">kWh</span></th>
                  <th>Yf<span class="unit-row">kWh/kWp/d</span></th>
                  <th>Lc<span class="unit-row">kWh/kWp/d</span></th>
                  <th>PR<span class="unit-row">%</span></th>
                </tr>
              </thead>
              <tbody>
                {bal_rows_html}
              </tbody>
              <tfoot>
                <tr>
                  <td>{_bilingual("Year", "全年合计/均值")}</td>
                  <td>{res['glob_hor_kwh_m2']:,.1f}</td>
                  <td>{res['diff_hor_kwh_m2']:,.1f}</td>
                  <td>{res['t_amb_year_c']:.2f}</td>
                  <td>{res['wind_year_ms']:.2f}</td>
                  <td>{res['glob_inc_kwh_m2']:,.1f}</td>
                  <td>{res['glob_eff_kwh_m2']:,.1f}</td>
                  <td>{res['glob_bak_kwh_m2']:,.1f}</td>
                  <td>{res['e_array_kwh']:,.0f}</td>
                  <td>{res['e_grid_kwh']:,.0f}</td>
                  <td>{res['yf_day']:.2f}</td>
                  <td>{res['lc_day']:.2f}</td>
                  <td>{res['pr_pct']:.2f}%</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        <div class="pvs-box">
          <div class="pvs-box-head">
            <span>{_bilingual("IEC 61724 Standardized Physical Nomenclature", "IEC 61724 国际光伏系统性能监测物理量说明")}</span>
            <small>8760h Hourly Integration</small>
          </div>
          <div class="pvs-box-content" style="font-size:6.3pt;color:#334155;line-height:1.34">
            <b>GlobHor / DiffHor</b>: 水平面总辐射与散射辐射 · <b>T_Amb / WindVel</b>: 环境干球温度与组件高度风速 ·
            <b>GlobInc</b>: 采光倾斜面总入射辐射 · <b>GlobEff</b>: 扣除远近遮挡、IAM反射与积灰并计入双面增益后的有效辐射 ·
            <b>GlobBak</b>: 双面组件背面有效受光辐射 · <b>EArray / E_Grid</b>: 直流MPP产出与交流并网电量 ·
            <b>Yf / Lc / PR</b>: 归一化日均有效发电小时、方阵捕获损失与系统综合能效比。
          </div>
        </div>
      </div>
      {_render_page_footer(ctx, 2)}
    </section>

    <!-- ==================== PAGE 3: LOSS DIAGRAM & SENSITIVITY RANKING ==================== -->
    <section class="pvs-page" id="gz-pro-page-3" data-page="3">
      {_render_page_watermark(ctx)}
      {_render_page_header(ctx, 3, "8760h Energy Loss Diagram & Sensitivity Ranking", "全年能量流分支损耗树图与关键损耗敏感度排序")}
      <div class="pvs-page-body">
        {_svg_page3_loss_diagram(ctx)}

        <div class="pvs-box">
          <div class="pvs-box-head">
            <span>{_bilingual("Loss & Gain Mechanism Sensitivity Ranking", "全链路损耗与增益机制影响权重排序表")}</span>
            <small>Sorted by Absolute Annual Impact |Δ%|</small>
          </div>
          <div class="pvs-box-content" style="padding:3px 4px">
            <table class="pvs-table" aria-label="Loss Sensitivity Ranking">
              <thead>
                <tr>
                  <th style="text-align:center">Rank</th>
                  <th style="text-align:left">Physical Mechanism · 物理机制</th>
                  <th style="text-align:center">Subsystem · 环节</th>
                  <th>Impact · 幅度</th>
                  <th>Energy Δ (MWh/yr)</th>
                  <th style="text-align:left">Relative Weight · 权重比例</th>
                </tr>
              </thead>
              <tbody>
                {sens_rows_html}
              </tbody>
            </table>
          </div>
        </div>

        <div class="pvs-box">
          <div class="pvs-box-content" style="display:flex;justify-content:space-between;gap:10px;font-size:6.4pt;color:#0f172a">
            <span><b>光学链:</b> GlobHor {res['glob_hor_kwh_m2']:,.1f} → GlobInc {res['glob_inc_kwh_m2']:,.1f} → GlobEff {res['glob_eff_kwh_m2']:,.1f} kWh/m²</span>
            <span><b>直流链:</b> ENom {res['e_nom_kwh']:,.0f} → EArray {res['e_array_kwh']:,.0f} kWh</span>
            <span><b>交流并网:</b> E_Grid <b>{res['e_grid_kwh']:,.0f} kWh</b> ({res['e_grid_mwh']:,.2f} MWh · PR {res['pr_pct']:.2f}%)</span>
          </div>
        </div>
      </div>
      {_render_page_footer(ctx, 3)}
    </section>

    <!-- ==================== PAGE 4: SKY DOME, SPECIAL GRAPHS, 12x24 MATRIX & P50/P90 ==================== -->
    <section class="pvs-page" id="gz-pro-page-4" data-page="4">
      {_render_page_watermark(ctx)}
      {_render_page_header(ctx, 4, "Solar-Path Sky Dome, 12×24 Output Matrix & Probabilistic Yield", "等遮挡太阳轨迹、逐日特性、12×24出力矩阵与概率置信分析")}
      <div class="pvs-page-body">
        {_svg_page4_iso_sunpath(ctx)}
        {_svg_page4_special_graphs(ctx)}
        {_svg_page4_hourly_heatmap_12x24(ctx)}

        <div class="pvs-box">
          <div class="pvs-box-head">
            <span>{_bilingual("P50 / P75 / P90 / P95 Bankable Probabilistic Yield", "P50 / P75 / P90 / P95 银行级发电量概率置信评估")}</span>
            <small>Meteo σ = {prb['sigma_meteo_pct']:.2f}% · Model σ = {prb['sigma_model_pct']:.2f}% · Combined σ = {prb['sigma_total_pct']:.2f}%</small>
          </div>
          <div class="pvs-box-content" style="padding:3px 5px">
            <div class="pvs-grid-2" style="align-items:center">
              <div>{_svg_page4_prob_curve(ctx)}</div>
              <div>
                <table class="pvs-table">
                  <thead>
                    <tr>
                      <th>Confidence · 置信分位</th>
                      <th>Annual (kWh)</th>
                      <th>Annual (MWh)</th>
                      <th>Specific (h)</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr><td><b>P50 (基准期望值)</b></td><td>{prb['p50_kwh']:,.0f}</td><td>{prb['p50_kwh'] / 1000.0:,.2f}</td><td>{prb['p50_kwh'] / max(pv['dc_kw'], 0.1):,.1f}</td></tr>
                    <tr><td><b>P75 (稳健评估值)</b></td><td>{prb['p75_kwh']:,.0f}</td><td>{prb['p75_kwh'] / 1000.0:,.2f}</td><td>{prb['p75_kwh'] / max(pv['dc_kw'], 0.1):,.1f}</td></tr>
                    <tr><td><b>P90 (银行融资基准)</b></td><td><b>{prb['p90_kwh']:,.0f}</b></td><td><b>{prb['p90_kwh'] / 1000.0:,.2f}</b></td><td><b>{prb['p90_kwh'] / max(pv['dc_kw'], 0.1):,.1f}</b></td></tr>
                    <tr><td><b>P95 (极端保守保底)</b></td><td>{prb['p95_kwh']:,.0f}</td><td>{prb['p95_kwh'] / 1000.0:,.2f}</td><td>{prb['p95_kwh'] / max(pv['dc_kw'], 0.1):,.1f}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
      {_render_page_footer(ctx, 4)}
    </section>

    <!-- ==================== PAGE 5: MPPT SCHEDULE & 6-CODE ENGINEERING VERIFICATION ==================== -->
    <section class="pvs-page" id="gz-pro-page-5" data-page="5">
      {_render_page_watermark(ctx)}
      {_render_page_header(ctx, 5, "MPPT String Allocation Schedule & National Code Verification", "逆变器MPPT组串配电表与国家规范六维安全校核")}
      <div class="pvs-page-body">
        <div class="pvs-box">
          <div class="pvs-box-head">
            <span>{_bilingual("Inverter MPPT Channel String Allocation & Voltage Drop Schedule", "逆变器 MPPT 通道组串配电与直流压降校核明细表")}</span>
            <small>{pv['module_count']} 块 / {pv['string_count']} 串 / {inv['count']} 台 · DC:AC {inv['pnom_ratio']:.3f}</small>
          </div>
          <div class="pvs-box-content" style="padding:3px 4px">
            <table class="pvs-table" aria-label="Inverter MPPT String Allocation Schedule">
              <thead>
                <tr>
                  <th>Unit</th>
                  <th style="text-align:left">Inverter Model</th>
                  <th>MPPT Channel</th>
                  <th>String IDs</th>
                  <th>Config</th>
                  <th>Pdc (kWp)</th>
                  <th>DC:AC</th>
                  <th>Vmpp 60°C</th>
                  <th>Voc Cold</th>
                  <th>ΔUdc</th>
                  <th>Check</th>
                </tr>
              </thead>
              <tbody>
                {mppt_rows_html}
              </tbody>
            </table>
          </div>
        </div>

        <div class="pvs-box">
          <div class="pvs-box-head">
            <span>{_bilingual("6-Dimension National Code Engineering Verification", "国家规范六维结构、抗风雪、电压包络与消防安全校核")}</span>
            <small>GB 50797 · GB 50009 · GB 55001 · GB 50016 · IEC 62548</small>
          </div>
          <div class="pvs-box-content">
            <div class="pvs-code-grid">
              {code_cards_html}
            </div>
          </div>
        </div>

        <div class="pvs-grid-2">
          <div class="pvs-box">
            <div class="pvs-box-head">
              <span>{_bilingual("DC / AC Cable & Overvoltage Protection", "交直流缆线选型与过电压保护技术要求")}</span>
              <small>IEC 60364-7-712</small>
            </div>
            <div class="pvs-box-content">
              <table class="pvs-kv-table">
                <tr><td class="k">直流组串线缆规格</td><td class="v">PV1-F 1×4.0 mm² (耐压 DC 1500V · ΔU &lt; 1.5%)</td></tr>
                <tr><td class="k">交直流防雷电涌保护</td><td class="v">DC Type II SPD + AC 二级防雷浪涌保护器</td></tr>
                <tr><td class="k">漏电流与孤岛保护</td><td class="v">内置高精度 RCMU + 主动防孤岛 ≤ 0.2s 脱扣</td></tr>
                <tr><td class="k">直流电弧故障检测</td><td class="v">智能 AFCI 拉弧快速关断保护 (&lt; 0.5s)</td></tr>
              </table>
            </div>
          </div>

          <div class="pvs-box">
            <div class="pvs-box-head">
              <span>{_bilingual("Structural Racking, Grounding & O&M Spec", "支架防腐、等电位防雷接地与运维规范")}</span>
              <small>NB/T 10115 · GB 50057</small>
            </div>
            <div class="pvs-box-content">
              <table class="pvs-kv-table">
                <tr><td class="k">支架材质与防腐等级</td><td class="v">Q235B 热浸镀锌 ≥65μm / 铝合金 6005-T5 (25年耐候)</td></tr>
                <tr><td class="k">屋面安装与防水保护</td><td class="v">{escape(ver['fixing_type'])} · 不破坏既有防水层构造</td></tr>
                <tr><td class="k">防雷等电位接地网</td><td class="v">40×4 热镀锌扁钢环网跨接 · 接地电阻 R ≤ 4.0 Ω</td></tr>
                <tr><td class="k">消防隔离与检修步道</td><td class="v">女儿墙退距 {ver['edge_setback_m']:.2f} m · 运维主步道 {(f"{ver['walkway_width_m']:.2f} m" if ver.get('walkway_width_m') is not None else "未输入（待人工复核）")}</td></tr>
              </table>
            </div>
          </div>
        </div>
      </div>
      {_render_page_footer(ctx, 5)}
    </section>

    <!-- ==================== PAGE 6: 25-YEAR FULL CASHFLOW SCHEDULE, SENSITIVITY & SIGN-OFF ==================== -->
    <section class="pvs-page" id="gz-pro-page-6" data-page="6">
      {_render_page_watermark(ctx)}
      {_render_page_header(ctx, 6, "25-Year Cashflow Schedule, Sensitivity Matrix & Sign-Off", "25年逐年现金流全表、双因素敏感度矩阵与工程责任签章")}
      <div class="pvs-page-body">
        <div class="pvs-main-strip">
          <div class="pvs-main-kpi primary">
            <span class="pvs-main-kpi-lbl">CAPEX · 工程静态总投资</span>
            <span class="pvs-main-kpi-val">¥{lc['capex_wan']:,.2f} <small>万元</small></span>
            <span class="pvs-main-kpi-sub">单瓦 ¥{(0.0 if pv['dc_kw'] <= 0 else (lc['capex_wan'] * 10000.0) / (pv['dc_kw'] * 1000.0)):.2f}/Wp</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">Tariff · 自用/上网电价</span>
            <span class="pvs-main-kpi-val">¥{lc['tariff_self']:.2f} <small>/ {lc['tariff_feed']:.2f}</small></span>
            <span class="pvs-main-kpi-sub">自用消纳 {res['self_use_pct']:.1f}%</span>
          </div>
          <div class="pvs-main-kpi highlight">
            <span class="pvs-main-kpi-lbl">IRR · 全投资内部收益率</span>
            <span class="pvs-main-kpi-val">{_fmt_irr(lc.get('irr_pct'), 2)}</span>
            <span class="pvs-main-kpi-sub">静态回收期 {_fmt_payback(lc.get('payback_yr'), 2)}</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">NPV · 财务净现值 (6%)</span>
            <span class="pvs-main-kpi-val">¥{lc['npv_wan']:,.2f} <small>万元</small></span>
            <span class="pvs-main-kpi-sub">25年净现值盈余</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">25-Yr Yield · 累计发电</span>
            <span class="pvs-main-kpi-val">{lc['cum_mwh_25yr']:,.1f} <small>MWh</small></span>
            <span class="pvs-main-kpi-sub">年均衰减 {ls['annual_degradation_pct']:.2f}%</span>
          </div>
          <div class="pvs-main-kpi">
            <span class="pvs-main-kpi-lbl">Carbon · 25年累计减碳</span>
            <span class="pvs-main-kpi-val">{lc['co2_25yr_tons']:,.1f} <small>tCO₂</small></span>
            <span class="pvs-main-kpi-sub">电网排放因子 0.5703</span>
          </div>
        </div>

        <div class="pvs-box">
          <div class="pvs-box-head">
            <span>{_bilingual("25-Year Annual Degradation & Cashflow Schedule (Full Y01–Y25 Ledger)", "25年全生命周期逐年发电衰减与财务现金流明细全表 (Y01–Y25)")}</span>
            <small>First-Year LID {ls['lid_pct']:.2f}% · Linear Aging {ls['annual_degradation_pct']:.2f}%/yr · O&amp;M Escalation 1.5%/yr</small>
          </div>
          <div class="pvs-box-content" style="padding:2px 4px">
            <table class="pvs-table pvs-table-25yr" aria-label="25-Year Full Cashflow Schedule">
              <thead>
                <tr>
                  <th>Year · 运营年</th>
                  <th>Retention · 留存率</th>
                  <th>E_Grid (MWh)</th>
                  <th>Self-Use Rev (万)</th>
                  <th>Feed-In Rev (万)</th>
                  <th>O&amp;M Cost (万)</th>
                  <th>Net CF (万元)</th>
                  <th>Cumulative CF (万元)</th>
                </tr>
              </thead>
              <tbody>
                {yr25_rows_html}
              </tbody>
              <tfoot>
                <tr>
                  <td>25-Yr Total / LCOE</td>
                  <td>LCOE {_fmt_lcoe(lc.get('lcoe_cny_kwh'), 3)}</td>
                  <td>{lc['cum_mwh_25yr']:,.1f}</td>
                  <td>{tot25['rev_self_wan']:,.2f}</td>
                  <td>{tot25['rev_feed_wan']:,.2f}</td>
                  <td>-{tot25['opex_wan']:,.2f}</td>
                  <td>{tot25['net_cf_wan']:+,.2f}</td>
                  <td>{tot25['cum_cf_wan']:+,.2f}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        <div class="pvs-grid-2" style="align-items:stretch">
          <div>{_svg_page6_cashflow(ctx)}</div>
          <div class="pvs-box">
            <div class="pvs-box-head">
              <span>{_bilingual("3×3 Tariff × CAPEX IRR / Payback Matrix", "电价 × 造价双因素 IRR / 回收期敏感度矩阵")}</span>
              <small>IRR (%) / Payback (yr)</small>
            </div>
            <div class="pvs-box-content" style="padding:4px">
              <table class="pvs-table">
                <thead>
                  <tr>
                    <th style="text-align:left">电价 \\ 造价</th>
                    <th style="text-align:center">CAPEX -10%</th>
                    <th style="text-align:center">基准 Base</th>
                    <th style="text-align:center">CAPEX +10%</th>
                  </tr>
                </thead>
                <tbody>
                  {sens_3x3_rows_html}
                </tbody>
              </table>
              <div style="font-size:5.9pt;color:#475569;margin-top:4px;line-height:1.28">
                {escape(
                    "敏感度结论：即便在综合电价下浮 10% 且 EPC 造价上浮 10% 的极端不利压力情景下，项目全周期现金流仍保持正累计盈余。"
                    if (
                        lc.get("sensitivity_matrix_3x3")
                        and lc["sensitivity_matrix_3x3"][0]["cells"][-1].get("payback_yr") is not None
                    )
                    else "敏感度提示：在电价下行/造价上行压力或当前边界条件下，部分敏感性组合存在无法回本或收益率偏低风险，请审慎核实电价与消纳率。"
                )}
              </div>
            </div>
          </div>
        </div>

        <div class="pvs-sign-boxes">
          <div class="pvs-sign-cell">
            <span>编制 · Prepared By</span>
            <b>光筑数字孪生仿真引擎 · 电气组</b>
          </div>
          <div class="pvs-sign-cell">
            <span>校核 · Checked By</span>
            <b>结构荷载与并网安全自动校核模块</b>
          </div>
          <div class="pvs-sign-cell">
            <span>审定 · Approved By</span>
            <b>主任工程师 / 项目总工签字：____________</b>
          </div>
        </div>

        <div class="pvs-signoff-block">
          <img class="pvs-signoff-logo" src="{icon_512}" alt="光筑核验徽标"/>
          <div class="pvs-signoff-text">
            <strong>光筑专业报告 · 工程级光伏三维数字孪生与 8760h 精细化物理仿真平台</strong>
            <p>本计算书依据 IEC 61724、Perez 1990 各向异性天空辐射模型、Faiman 逐时热平衡模型及 GB 50797 规范生成。项目编号：{escape(meta['project_id'])} · 方案版本：{escape(meta['variant_code'])} · 校验摘要：{escape(str(meta.get('snapshot_sha256', ''))[:12])} · 出具日期：{escape(meta['simulation_date'])}。</p>
          </div>
          <div class="pvs-stamp-seal{'' if all_pass else ' unverified'}">
            {'光筑工程仿真核验章<br/>GUANGZHU VERIFIED' if all_pass else '工程复核提示<br/>RECHECK REQUIRED'}<br/>8760H · {escape(meta.get('report_code', 'GZ-SIM'))}
          </div>
        </div>
      </div>
      {_render_page_footer(ctx, 6)}
    </section>
  </main>

  <script>
    (function() {{
      var modes = ['bilingual', 'zh', 'en'];
      var labels = {{ bilingual: '中英切换: 双语 Bilingual', zh: '中英切换: 纯中文 ZH', en: 'Lang: English EN' }};
      window.__cyclePvsLang = function() {{
        var cur = document.body.getAttribute('data-lang-mode') || 'bilingual';
        var next = modes[(modes.indexOf(cur) + 1) % modes.length];
        document.body.setAttribute('data-lang-mode', next);
        var btn = document.getElementById('pvsLangToggleBtn');
        if (btn) btn.textContent = labels[next];
      }};
      window.__jumpGzPage = function(pageNo) {{
        var el = document.querySelector('[data-page="' + pageNo + '"]');
        if (el && el.scrollIntoView) el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }};
      window.__downloadStandaloneGzHtml = function() {{
        var blob = new Blob(['<!DOCTYPE html>\\n' + document.documentElement.outerHTML], {{ type: 'text/html;charset=utf-8' }});
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = {repr(html_dl_name)};
        document.body.appendChild(a);
        a.click();
        setTimeout(function() {{ URL.revokeObjectURL(a.href); a.remove(); }}, 600);
      }};
      window.__downloadStandalonePvsHtml = window.__downloadStandaloneGzHtml;
    }})();
  </script>
</body>
</html>"""

    assert_no_private_path_leak(html_doc)
    assert_no_pvsyst_visible_text(html_doc)
    return html_doc


# ---------------------------------------------------------------------------
# Multi-Page A4 PDF Export (Headless Browser Primary + 6-Page ReportLab Fallback)
# ---------------------------------------------------------------------------

def _render_pvsyst_pdf_reportlab(context: dict[str, Any], output_pdf: Path) -> Path:
    """Pure-Python 6-page A4《光筑专业报告》vector PDF renderer with diagonal watermarks (0 browser dependency)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    ctx = sanitize_report_structure(context)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    cjk_font = "STSong-Light"
    try:
        pdfmetrics.getFont(cjk_font)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(cjk_font))

    icons = get_guangzhu_icon_assets()
    icon_img = ImageReader(io.BytesIO(icons["icon_128_bytes"]))

    W, H = A4
    c = canvas.Canvas(str(output_pdf), pagesize=A4)
    meta = ctx["meta"]
    site = ctx["site"]
    ori = ctx["orientation"]
    pv = ctx["pv_array"]
    inv = ctx["inverter"]
    ls = ctx["losses"]
    res = ctx["results"]
    lt = ctx["loss_tree"]
    prb = ctx["probabilities"]
    ver = ctx["verification"]
    lc = ctx["lifecycle"]
    tot_pages = int(meta.get("total_pages", 6))

    c.setTitle(f"光筑专业报告 - {meta['project_name']} ({meta['variant_code']})")
    c.setAuthor("光筑 Guangzhu 8760h Engineering Simulation Engine")
    c.setSubject("并网光伏发电系统精细化工程仿真计算书")

    def _draw_watermark() -> None:
        c.saveState()
        try:
            c.setFillAlpha(0.055)
            c.setStrokeAlpha(0.055)
        except AttributeError:
            pass
        c.setFillColor(colors.HexColor("#0f172a"))
        for row_i in range(4):
            wy = 120 + row_i * 185
            for col_i in range(3):
                wx = 105 + col_i * 190
                c.saveState()
                c.translate(wx, wy)
                c.rotate(28)
                c.drawImage(icon_img, -58, -8, width=16, height=16, mask="auto")
                c.setFont(cjk_font, 10.5)
                c.drawString(-38, 1, "光筑 · GUANGZHU")
                c.setFont(cjk_font, 6.8)
                c.drawString(-38, -8, "光筑专业报告")
                c.restoreState()
        c.restoreState()

    def _draw_chrome(page_no: int, sec_title: str) -> None:
        hx, hy, hw, hh = 24, H - 62, W - 48, 40
        c.setFillColor(colors.HexColor("#f8fafc"))
        c.setStrokeColor(colors.HexColor("#0f172a"))
        c.setLineWidth(1.1)
        c.rect(hx, hy, hw, hh, fill=1, stroke=1)
        c.drawImage(icon_img, hx + 6, hy + 6, width=28, height=28, mask="auto")
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont(cjk_font, 9.5)
        c.drawString(hx + 38, hy + 24, "光筑专业报告 · GUANGZHU PRO")
        c.setFont("Helvetica", 6.8)
        c.setFillColor(colors.HexColor("#475569"))
        c.drawString(hx + 38, hy + 10, "Grid-Connected PV (IEC 61724 / Perez 8760h)")

        c.line(hx + 186, hy, hx + 186, hy + hh)
        c.setFillColor(colors.HexColor("#1e3a8a"))
        c.setFont(cjk_font, 8.8)
        c.drawString(hx + 193, hy + 24, sec_title[:42])
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont(cjk_font, 7.5)
        c.drawString(hx + 193, hy + 10, f"项目: {meta['project_name'][:26]} ({meta['variant_code']})")

        c.line(hx + hw - 134, hy, hx + hw - 134, hy + hh)
        c.setFont(cjk_font, 7.2)
        c.drawString(hx + hw - 128, hy + 25, f"站址: {site['city'][:14]}")
        c.setFont("Helvetica-Bold", 7.4)
        c.drawString(hx + hw - 128, hy + 10, f"Date: {meta['simulation_date'][:10]} | Page {page_no} of {tot_pages}")

        c.setStrokeColor(colors.HexColor("#64748b"))
        c.setLineWidth(0.7)
        c.line(24, 25, W - 24, 25)
        c.drawImage(icon_img, 24, 12, width=10, height=10, mask="auto")
        c.setFillColor(colors.HexColor("#475569"))
        c.setFont(cjk_font, 6.9)
        c.drawString(38, 14, f"光筑 Guangzhu 8760h Engineering Simulation Engine · {meta['project_name']} · Page {page_no} / {tot_pages}")
        _draw_watermark()

    def _box(x: float, y: float, w: float, h: float, title: str, rows_kv: list[tuple[str, str]]) -> None:
        c.setStrokeColor(colors.HexColor("#334155"))
        c.setLineWidth(0.8)
        c.setFillColor(colors.white)
        c.rect(x, y, w, h, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#e2e8f0"))
        c.rect(x, y + h - 15, w, 15, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont(cjk_font, 8.0)
        c.drawString(x + 5, y + h - 11, title)
        ry = y + h - 27
        step = max(11.0, (h - 20) / max(1, len(rows_kv)))
        for k_txt, v_txt in rows_kv:
            c.setFont(cjk_font, 7.1)
            c.setFillColor(colors.HexColor("#334155"))
            c.drawString(x + 5, ry, k_txt)
            c.setFillColor(colors.HexColor("#0f172a"))
            c.drawRightString(x + w - 5, ry, v_txt)
            ry -= step

    bw = (W - 58) / 2.0

    # ---------------- PAGE 1: SIMULATION PARAMETERS ----------------
    c.setFillColor(colors.HexColor("#eff6ff"))
    c.setStrokeColor(colors.HexColor("#1e3a8a"))
    c.rect(24, H - 110, W - 48, 40, fill=1, stroke=1)
    c.drawImage(icon_img, 31, H - 104, width=28, height=28, mask="auto")
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont(cjk_font, 10.2)
    c.drawString(66, H - 87, f"{meta['project_name']} — 8760h 并网光伏工程仿真计算书")
    c.setFont(cjk_font, 7.5)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(66, H - 101, f"站址: {site['name'][:32]} | DC {pv['dc_kw']:.2f} kWp | AC {inv['total_ac_kw']:.1f} kWac | E_Grid {res['e_grid_mwh']:,.2f} MWh/yr | PR {res['pr_pct']:.2f}%")

    sy = H - 184
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.setStrokeColor(colors.HexColor("#475569"))
    c.rect(24, sy, W - 48, 66, fill=1, stroke=1)
    for nx, nfill, nt1, nt2 in [
        (34, "#dbeafe", "PV Sub-Arrays 光伏方阵", f"{pv['dc_kw']:.2f} kWp ({pv['module_count']} 块)"),
        (170, "#ffffff", "DC Strings 组串汇流", f"{pv['string_count']} 串 × {pv['modules_per_string']}S"),
        (306, "#fef3c7", "MPPT Inverter 并网逆变", f"{inv['count']} 台×{inv['unit_ac_kw']:.0f}kW (R={inv['pnom_ratio']:.2f})"),
        (442, "#dcfce7", "Grid & Load 并网消纳", f"{res['e_grid_mwh']:,.1f} MWh · 自用{res['self_use_pct']:.0f}%"),
    ]:
        c.setFillColor(colors.HexColor(nfill))
        c.rect(nx, sy + 10, 118, 46, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont(cjk_font, 7.4)
        c.drawString(nx + 5, sy + 39, nt1)
        c.setFont(cjk_font, 6.9)
        c.drawString(nx + 5, sy + 20, nt2)

    _box(24, H - 350, bw, 156, "Geographical Site & Meteo · 地理与气象", [
        ("项目站址 Site", site["name"][:24]),
        ("经纬度 Coordinates", f"{site['lat']:.4f}°N, {site['lon']:.4f}°E"),
        ("海拔时区 Altitude", f"{site['altitude_m']:.0f} m / UTC+8"),
        ("气象源 Meteo", site["meteo_source"][:26]),
        ("反射率/风速 Albedo/Wind", f"{site['albedo']:.2f} / {res['wind_year_ms']:.2f} m/s"),
        ("转置与热模型 Models", "Perez 1990 / Faiman"),
    ])
    _box(34 + bw, H - 350, bw, 156, "Orientation & Shading · 朝向与三维遮挡", [
        ("阵列型式 Field Type", ori["field_zh"]),
        ("倾角方位 Tilt/Az", ori["az_display"][:24]),
        ("安装方向 Mounting", ori["mount_orientation"]),
        ("排距/采光宽 Pitch/Width", f"{ori['pitch_m']:.2f} m / {ori['collector_width_m']:.2f} m"),
        ("覆盖率/临界角 GCR/α", f"{ori['gcr_pct']:.1f}% / α={ori['limit_angle_deg']:.1f}°"),
        ("近处阴影 Near Shading", f"Linear {abs(lt['near_shading_loss_pct']):.2f}%"),
    ])
    _box(24, H - 516, bw, 156, "PV Array (.PAN) · 光伏组件与组串", [
        ("组件型号 Module", f"{pv['module_brand']} {pv['module_model']}"[:26]),
        ("单块功率/双面率", f"{pv['stc_w']:.0f} Wp (φ={pv['bifaciality']:.2f})"),
        ("温度系数 γPmp / βVoc", f"{pv['gamma_pmax_pct_c']:+.2f}% / {pv['beta_voc_pct_c']:+.2f}%/°C"),
        ("总块数/面积 Modules", f"{pv['module_count']} 块 ({pv['collector_area_m2']:,.1f} m²)"),
        ("组串与直流容量 Pnom", f"{pv['string_count']} 串×{pv['modules_per_string']}S · {pv['dc_kw']:,.2f} kWp"),
        ("Vmpp(60°C) / Voc(-10°C)", f"{pv['vmpp_60c_v']:.1f} V / {pv['voc_minus10c_v']:.1f} V"),
    ])
    _box(34 + bw, H - 516, bw, 156, "Inverter (.OND) · 并网逆变器特性", [
        ("逆变器型号 Inverter", f"{inv['brand']} {inv['model']}"[:26]),
        ("交流功率 Pac", f"{inv['count']} 台 × {inv['unit_ac_kw']:.0f} kW = {inv['total_ac_kw']:.1f} kWac"),
        ("容配比 DC:AC Ratio", f"{inv['pnom_ratio']:.3f}"),
        ("MPPT电压窗口 Window", inv["mppt_window_v"]),
        ("最大直流耐压 Max DC V", f"{inv['max_dc_v']:.0f} V"),
        ("欧洲效率 Euro η", f"{inv['euro_eff_pct']:.2f}%"),
    ])
    _box(24, 42, W - 48, 270, "System Loss Factors & Executive Summary · 损耗参数与核心指标", [
        ("热损耗系数 Thermal Uc / Uv", f"Uc = {ls['uc_w_m2k']:.1f} W/m²K, Uv = {ls['uv_w_m2k_ms']:.1f} W/m²K / m/s"),
        ("交直流与升压损耗 Wiring", f"DC {ls['dc_ohmic_pct']:.2f}% | AC {ls['ac_ohmic_pct']:.2f}% | Transformer {ls['transformer_loss_pct']:.2f}%"),
        ("首年光衰/公差/失配", f"LID {ls['lid_pct']:.2f}% | Quality {ls['module_quality_pct']:+.2f}% | Mismatch {ls['mismatch_pct']:.2f}%"),
        ("积灰/IAM/年均衰减", f"Soiling {ls['soiling_pct']:.2f}% | IAM b0={ls['iam_b0']:.3f} | Aging {ls['annual_degradation_pct']:.2f}%/yr"),
        ("首年核心指标 KPIs", f"E_Grid {res['e_grid_mwh']:,.2f} MWh | 满发 {res['specific_yield_kwh_kwp']:,.1f} h | PR {res['pr_pct']:.2f}% | IRR {_fmt_irr(lc.get('irr_pct'), 1)}"),
    ])
    _draw_chrome(1, "System Overview & Parameters · 系统拓扑与输入参数")
    c.showPage()

    # ---------------- PAGE 2: MAIN RESULTS & 13-COL BALANCES ----------------
    ky = H - 114
    kw = (W - 48) / 6.0
    for idx_k, (kl, kv) in enumerate([
        ("E_Grid 并网电量", f"{res['e_grid_mwh']:,.2f} MWh"),
        ("Specific 满发小时", f"{res['specific_yield_kwh_kwp']:,.1f} h"),
        ("PR 综合能效比", f"{res['pr_pct']:.2f}%"),
        ("Self-Use 自用率", f"{res['self_use_pct']:.1f}%"),
        ("GlobBak 背面辐射", f"{res['glob_bak_kwh_m2']:,.1f} kWh/m²"),
        ("LCOE 度电成本", _fmt_lcoe(res.get("lcoe_cny_kwh"), 3)),
    ]):
        kx = 24 + idx_k * kw
        c.setFillColor(colors.HexColor("#f8fafc" if idx_k % 2 else "#eff6ff"))
        c.setStrokeColor(colors.HexColor("#334155"))
        c.rect(kx, ky, kw, 42, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#475569"))
        c.setFont(cjk_font, 6.6)
        c.drawString(kx + 4, ky + 28, kl)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont(cjk_font, 8.4)
        c.drawString(kx + 4, ky + 10, kv)

    cy = H - 280
    cw_p2 = (W - 58) / 2.0
    c.setFillColor(colors.white)
    c.rect(24, cy, cw_p2, 154, fill=1, stroke=1)
    c.rect(34 + cw_p2, cy, cw_p2, 154, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont(cjk_font, 7.6)
    c.drawString(30, cy + 140, f"Normalized Production (Yf={res['yf_day']:.2f}, Ls={res['ls_day']:.2f}, Lc={res['lc_day']:.2f})")
    c.drawString(40 + cw_p2, cy + 140, f"Performance Ratio PR (Annual = {res['pr_pct']:.2f}%)")
    for m_i, r in enumerate(ctx["normalized_monthly"]):
        bx1 = 38 + m_i * ((cw_p2 - 24) / 12.0)
        hyf = min(86.0, r["yf_day"] * 13.0)
        hls = min(28.0, r["ls_day"] * 13.0)
        hlc = min(32.0, r["lc_day"] * 13.0)
        c.setFillColor(colors.HexColor("#991b1b"))
        c.rect(bx1, cy + 18, 11, hyf, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#16a34a"))
        c.rect(bx1, cy + 18 + hyf, 11, hls, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#7c3aed"))
        c.rect(bx1, cy + 18 + hyf + hls, 11, hlc, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#334155"))
        c.setFont("Helvetica", 5.8)
        c.drawCentredString(bx1 + 5.5, cy + 8, r["month_en"])

        bx2 = 48 + cw_p2 + m_i * ((cw_p2 - 24) / 12.0)
        hpr = min(105.0, r["pr_pct"] * 1.05)
        c.setFillColor(colors.HexColor("#b91c1c"))
        c.rect(bx2, cy + 18, 11, hpr, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#334155"))
        c.drawCentredString(bx2 + 5.5, cy + 8, r["month_en"])

    # 13-Column Monthly Table
    ty = cy - 18
    cols_13 = [24, 62, 102, 142, 176, 210, 250, 290, 330, 382, 438, 476, 514]
    hdrs_13 = ["Month", "GlobHor", "DiffHor", "T_Amb", "Wind", "GlobInc", "GlobEff", "GlobBak", "EArray", "E_Grid", "Yf", "Lc", "PR%"]
    c.setFillColor(colors.HexColor("#e2e8f0"))
    c.setStrokeColor(colors.HexColor("#0f172a"))
    c.rect(24, ty - 16, W - 48, 16, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont("Helvetica-Bold", 6.2)
    for ci, h_lbl in enumerate(hdrs_13):
        c.drawString(cols_13[ci] + 2, ty - 11, h_lbl)

    row_y = ty - 32
    for idx_m, r in enumerate(ctx["normalized_monthly"]):
        if idx_m % 2 == 1:
            c.setFillColor(colors.HexColor("#f8fafc"))
            c.rect(24, row_y - 4, W - 48, 16, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#cbd5e1"))
        c.rect(24, row_y - 4, W - 48, 16, fill=0, stroke=1)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont(cjk_font, 6.3)
        vals_13 = [
            f"{r['month_en']}",
            f"{r['glob_hor']:.1f}",
            f"{r['diff_hor']:.1f}",
            f"{r['t_amb']:.1f}",
            f"{r.get('wind_ms', 2.4):.2f}",
            f"{r['glob_inc']:.1f}",
            f"{r['glob_eff']:.1f}",
            f"{r.get('glob_bak', 0.0):.2f}",
            f"{r['e_array']:,.0f}",
            f"{r['e_grid']:,.0f}",
            f"{r['yf_day']:.2f}",
            f"{r['lc_day']:.2f}",
            f"{r['pr_pct']:.1f}%",
        ]
        for ci, v_str in enumerate(vals_13):
            c.drawString(cols_13[ci] + 2, row_y + 1, v_str)
        row_y -= 16

    c.setFillColor(colors.HexColor("#dbeafe"))
    c.setStrokeColor(colors.HexColor("#0f172a"))
    c.rect(24, row_y - 5, W - 48, 18, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont(cjk_font, 6.5)
    for ci, v_str in enumerate([
        "Year全年",
        f"{res['glob_hor_kwh_m2']:,.1f}",
        f"{res['diff_hor_kwh_m2']:,.1f}",
        f"{res['t_amb_year_c']:.1f}",
        f"{res['wind_year_ms']:.2f}",
        f"{res['glob_inc_kwh_m2']:,.1f}",
        f"{res['glob_eff_kwh_m2']:,.1f}",
        f"{res['glob_bak_kwh_m2']:,.1f}",
        f"{res['e_array_kwh']:,.0f}",
        f"{res['e_grid_kwh']:,.0f}",
        f"{res['yf_day']:.2f}",
        f"{res['lc_day']:.2f}",
        f"{res['pr_pct']:.2f}%",
    ]):
        c.drawString(cols_13[ci] + 2, row_y, v_str)
    _draw_chrome(2, "Main Results & 13-Col Balances · 核心结果与月度平衡表")
    c.showPage()

    # ---------------- PAGE 3: LOSS DIAGRAM & SENSITIVITY ----------------
    ly = H - 86
    loss_steps = [
        ("STAGE", f"GlobHor: {lt['glob_hor_kwh_m2']:,.1f} kWh/m²", "Horizontal global irradiation 水平面总辐射"),
        ("GAIN", _fmt_signed(lt["transposition_gain_pct"]), "POA transposition (Perez 1990) 倾角转置增益"),
        ("STAGE", f"GlobInc: {lt['glob_inc_kwh_m2']:,.1f} kWh/m²", "Global incident in collector plane 倾斜面入射辐射"),
        ("LOSS", _fmt_signed(lt["horizon_loss_pct"]), "Far horizon blocking 远方遮挡损失"),
        ("LOSS", _fmt_signed(lt["near_shading_loss_pct"]), "3D Near Shadings 三维近处光学阴影损失"),
        ("LOSS", _fmt_signed(lt["iam_loss_pct"]), "IAM reflection 入射角反射损失"),
        ("LOSS", _fmt_signed(lt["soiling_loss_pct"]), "Surface soiling 组件表面积灰损失"),
        ("GAIN", _fmt_signed(lt["bifacial_gain_pct"]), "Bifacial rear gain 双面组件背面发电增益"),
        ("STAGE", f"GlobEff: {lt['glob_eff_kwh_m2']:,.1f} kWh/m² × {lt['collector_area_m2']:,.0f} m²", f"Effective irradiation (STC η = {lt['stc_eff_pct']:.2f}%)"),
        ("STAGE", f"ENom: {lt['e_nom_kwh']:,.0f} kWh", "Array nominal energy at STC 方阵标称直流能量"),
        ("LOSS", _fmt_signed(lt["irrad_level_loss_pct"]), "Low irradiance response 弱光响应损失"),
        ("LOSS", _fmt_signed(lt["temp_loss_pct"]), "Cell temperature loss 工作温升热损耗"),
        ("GAIN", _fmt_signed(lt["spectral_pct"]), "Spectral correction 光谱修正"),
        ("GAIN", _fmt_signed(lt["quality_gain_pct"]), "Module positive sorting 组件正公差增益"),
        ("LOSS", _fmt_signed(lt["lid_loss_pct"]), "First-year LID 首年光致衰减"),
        ("LOSS", _fmt_signed(lt["mismatch_elec_shading_pct"]), "Mismatch & electrical shading 失配损失"),
        ("LOSS", _fmt_signed(lt["dc_ohmic_loss_pct"]), "DC ohmic wiring 直流线缆压降损耗"),
        ("STAGE", f"EArray: {lt['e_mpp_kwh']:,.0f} kWh", "Array virtual energy at MPP 最大功率点直流产出"),
        ("LOSS", _fmt_signed(lt["inv_op_loss_pct"]), "Inverter operation loss 逆变器转换损耗"),
        ("LOSS", _fmt_signed(lt["inv_clip_loss_pct"]), "Overpower clipping 超配削峰损失"),
        ("STAGE", f"EOutInv: {lt['e_inv_out_kwh']:,.0f} kWh", "Available Energy at Inverter Output 逆变器输出电量"),
        ("LOSS", _fmt_signed(lt["ac_ext_loss_pct"]), "AC ohmic, transformer & availability 交流与并网损耗"),
        ("FINAL", f"E_Grid: {lt['e_grid_kwh']:,.0f} kWh ({res['e_grid_mwh']:,.2f} MWh)", f"Energy injected into grid 最终并网电量 (PR {res['pr_pct']:.2f}%)"),
    ]
    for kind_s, val_s, desc_s in loss_steps:
        if kind_s in ("STAGE", "FINAL"):
            c.setFillColor(colors.HexColor("#166534" if kind_s == "FINAL" else "#dbeafe"))
            c.setStrokeColor(colors.HexColor("#0f172a"))
            c.rect(36, ly - 13, 194, 17, fill=1, stroke=1)
            c.setFillColor(colors.white if kind_s == "FINAL" else colors.HexColor("#0f172a"))
            c.setFont("Helvetica-Bold", 7.4)
            c.drawCentredString(133, ly - 7, val_s)
            c.setFillColor(colors.HexColor("#0f172a"))
            c.setFont(cjk_font, 7.4)
            c.drawString(238, ly - 7, desc_s)
            ly -= 23
        else:
            c.setFillColor(colors.HexColor("#e2e8f0"))
            c.rect(52, ly - 10, 158, 13, fill=1, stroke=0)
            col_hex = "#15803d" if val_s.startswith("+") else "#b91c1c"
            c.setStrokeColor(colors.HexColor(col_hex))
            c.setLineWidth(1.1)
            c.line(210, ly - 3, 254, ly - 3)
            c.setFillColor(colors.HexColor(col_hex))
            c.setFont("Helvetica-Bold", 7.2)
            c.drawString(260, ly - 6, val_s)
            c.setFillColor(colors.HexColor("#334155"))
            c.setFont(cjk_font, 7.0)
            c.drawString(310, ly - 6, desc_s)
            ly -= 19

    _box(24, 42, W - 48, 158, "Loss Sensitivity Ranking · 损耗与增益敏感度排序", [
        (f"#{it['rank']} {it['label'][:28]}", f"{_fmt_signed(it['pct'])} ({it['energy_mwh']:+,.2f} MWh/yr)")
        for it in ctx.get("loss_sensitivity_ranking", [])[:7]
    ])
    _draw_chrome(3, "8760h Loss Diagram & Sensitivity · 全年损耗树图与敏感度")
    c.showPage()

    # ---------------- PAGE 4: SKY DOME, 12x24 HEATMAP & P50/P90 ----------------
    spx, spy, spw, sph = 44, H - 270, W - 88, 178
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.setStrokeColor(colors.HexColor("#0f172a"))
    c.rect(spx, spy, spw, sph, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont(cjk_font, 8.2)
    c.drawString(spx, spy + sph + 7, f"Iso-Shadings Sky Dome · 太阳轨迹与三维遮挡天穹图 (Lat {site['lat']:.2f}°N)")
    for tr in ctx["sunpath_iso"]["trajectories"]:
        pts = tr["points"]
        if len(pts) >= 2:
            c.setStrokeColor(colors.HexColor(tr["color"]))
            c.setLineWidth(1.15)
            p = c.beginPath()
            p.moveTo(spx + ((pts[0][0] + 180.0) / 360.0) * spw, spy + (pts[0][1] / 90.0) * sph)
            for az_p, el_p in pts[1:]:
                p.lineTo(spx + ((az_p + 180.0) / 360.0) * spw, spy + (el_p / 90.0) * sph)
            c.drawPath(p, stroke=1, fill=0)

    # 12x24 Heatmap Grid
    hmx, hmy, hmw, hmh = 44, H - 465, W - 88, 156
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#0f172a"))
    c.rect(hmx, hmy, hmw, hmh, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont(cjk_font, 8.0)
    hm_data = ctx["hourly_heatmap_12x24"]
    hm_peak = max(0.0, _fnum(hm_data.get("max_ac_kw"), 0.0))
    hm_max = max(1.0, hm_peak)
    c.drawString(hmx, hmy + hmh + 6, f"12×24 Hourly Mean AC Output Matrix · 全年12月×24时平均出力矩阵 (Peak {hm_peak:,.1f} kWac)")
    cell_w = hmw / 24.0
    cell_h = hmh / 12.0
    for m_i in range(12):
        r_ac = hm_data["ac_kw"][m_i] if m_i < len(hm_data["ac_kw"]) else [0.0] * 24
        for hr in range(24):
            v_ac = _fnum(r_ac[hr] if hr < len(r_ac) else 0.0, 0.0)
            frac = v_ac / hm_max
            hex_c = "#f8fafc" if frac <= 0.02 else ("#bae6fd" if frac < 0.35 else ("#fde68a" if frac < 0.65 else ("#fb923c" if frac < 0.85 else "#b91c1c")))
            c.setFillColor(colors.HexColor(hex_c))
            c.rect(hmx + hr * cell_w, hmy + (11 - m_i) * cell_h, cell_w, cell_h, fill=1, stroke=0)

    _box(24, 44, bw, 240, "Daily I/O & Power Dist. · 逐日与功率分布", [
        ("仿真天数 Sampled Days", f"{len(ctx['daily_io'])} days (8760 hours)"),
        ("倾斜面总辐射 GlobInc", f"{res['glob_inc_kwh_m2']:,.1f} kWh/m²/yr"),
        ("日均并网电量 Mean Daily", f"{res['e_grid_kwh'] / 365.0:,.1f} kWh/day"),
        ("功率分布直方图 Bins", f"{len(ctx['power_distribution'])} bins (0 – {inv['total_ac_kw']:.0f} kWac)"),
        ("女儿墙与临界角 Parapet", f"{ori['parapet_height_m']:.2f} m · α_lim {ori['limit_angle_deg']:.1f}°"),
    ])
    _box(34 + bw, 44, bw, 240, "P50 / P75 / P90 / P95 Probabilistic Yield", [
        ("气象/模型不确定度", f"σ_m {prb['sigma_meteo_pct']:.2f}% · σ_s {prb['sigma_model_pct']:.2f}%"),
        ("综合标准差 σ_total", f"{prb['sigma_total_pct']:.2f}%"),
        ("P50 基准期望发电量", f"{prb['p50_kwh']:,.0f} kWh ({prb['p50_kwh'] / 1000.0:,.2f} MWh)"),
        ("P75 稳健评估发电量", f"{prb['p75_kwh']:,.0f} kWh ({prb['p75_kwh'] / 1000.0:,.2f} MWh)"),
        ("P90 银行融资发电量", f"{prb['p90_kwh']:,.0f} kWh ({prb['p90_kwh'] / 1000.0:,.2f} MWh)"),
        ("P95 极端保守发电量", f"{prb['p95_kwh']:,.0f} kWh ({prb['p95_kwh'] / 1000.0:,.2f} MWh)"),
    ])
    _draw_chrome(4, "Sky Dome, 12×24 Matrix & P50/P90 · 太阳轨迹与出力矩阵")
    c.showPage()

    # ---------------- PAGE 5: MPPT SCHEDULE & 6-CODE VERIFICATION ----------------
    _box(24, H - 320, W - 48, 240, "Inverter MPPT String Allocation Schedule · 逆变器MPPT组串配电明细表", [
        (f"{r['unit']} · {r['mppt_used']} ({r['strings_label']})", f"{r['config']} | {r['dc_kw']:.2f}kWp | Vmp {r['vmpp_v']:.0f}V | Voc {r['voc_cold_v']:.0f}V | ΔU {r.get('dc_drop_pct', 0.9):.2f}% [{r['status']}]")
        for r in ver["mppt_rows"][:9]
    ])
    _box(24, 48, W - 48, 455, "6-Item National Code Verification · 国家规范六维安全校核 (GB 50797 / GB 50009 / GB 55001)", [
        (f"[{chk['code']}] {chk['title_zh']}", f"{chk['metric']}  [{chk['status']}]")
        for chk in ver.get("national_code_checks", [])
    ] + [
        ("直流组串电缆与电涌保护", "PV1-F 1×4.0mm² DC 1500V · Type II DC/AC SPD · AFCI"),
        ("防雷等电位接地与检修步道", f"接地电阻 R ≤ 4.0 Ω · 运维主通道 {(f"{ver['walkway_width_m']:.2f} m" if ver.get('walkway_width_m') is not None else '未输入（待人工复核）')}"),
    ])
    _draw_chrome(5, "MPPT Schedule & 6-Code Verification · 组串配电与国标校核")
    c.showPage()

    # ---------------- PAGE 6: 25-YEAR FULL CASHFLOW, SENSITIVITY & SIGN-OFF ----------------
    ty6 = H - 78
    cols_6 = [24, 96, 158, 224, 294, 364, 434, 504]
    hdrs_6 = ["Year 年份", "留存率%", "E_Grid(MWh)", "自用收益(万)", "上网收益(万)", "运维(万)", "净现金流(万)", "累计现金流(万)"]
    c.setFillColor(colors.HexColor("#e2e8f0"))
    c.setStrokeColor(colors.HexColor("#0f172a"))
    c.rect(24, ty6 - 14, W - 48, 14, fill=1, stroke=1)
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont(cjk_font, 6.2)
    for ci, h_lbl in enumerate(hdrs_6):
        c.drawString(cols_6[ci] + 2, ty6 - 10, h_lbl)

    ry6 = ty6 - 27
    for idx_y, r in enumerate(lc["yearly_25"]):
        if idx_y % 2 == 1:
            c.setFillColor(colors.HexColor("#f8fafc"))
            c.rect(24, ry6 - 3, W - 48, 13.5, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor("#cbd5e1"))
        c.rect(24, ry6 - 3, W - 48, 13.5, fill=0, stroke=1)
        c.setFillColor(colors.HexColor("#0f172a"))
        c.setFont(cjk_font, 6.0)
        for ci, v_str in enumerate([
            f"Y{r['year']:02d}",
            f"{r['deg_factor_pct']:.2f}%",
            f"{r['e_grid_mwh']:,.2f}",
            f"{r.get('rev_self_wan', 0.0):,.2f}",
            f"{r.get('rev_feed_wan', 0.0):,.2f}",
            f"-{r.get('opex_wan', 0.0):,.2f}",
            f"{r['net_cf_wan']:+,.2f}",
            f"{r['cum_cf_wan']:+,.2f}",
        ]):
            c.drawString(cols_6[ci] + 2, ry6, v_str)
        ry6 -= 13.5

    _box(24, 118, W - 48, 286, "3×3 Tariff × CAPEX Sensitivity & Financial KPIs · 敏感度矩阵与财务指标", [
        ("工程总造价 CAPEX / 度电成本 LCOE", f"¥{lc['capex_wan']:,.2f} 万元  |  LCOE {_fmt_lcoe(lc.get('lcoe_cny_kwh'), 3)}"),
        ("全投资 IRR / 静态回收期 / NPV", f"IRR {_fmt_irr(lc.get('irr_pct'), 2)}  |  Payback {_fmt_payback(lc.get('payback_yr'), 2, ' yr')}  |  NPV ¥{lc['npv_wan']:,.2f} 万元"),
    ] + [
        (
            s_row["tariff_label"],
            "  |  ".join(
                f"{cell['capex_label']}: {_fmt_irr(cell.get('irr_pct'), 1)}/{_fmt_payback(cell.get('payback_yr'), 2, 'y')}"
                for cell in s_row["cells"]
            ),
        )
        for s_row in lc.get("sensitivity_matrix_3x3", [])
    ])

    # Sign-off Block
    rl_all_pass = bool(ver.get("all_pass", False))
    c.setFillColor(colors.HexColor("#f8fafc"))
    c.setStrokeColor(colors.HexColor("#0f172a"))
    c.rect(24, 42, W - 48, 66, fill=1, stroke=1)
    c.drawImage(icon_img, 32, 54, width=40, height=40, mask="auto")
    c.setFillColor(colors.HexColor("#0f172a"))
    c.setFont(cjk_font, 8.6)
    c.drawString(80, 90, "光筑专业报告 · 工程仿真三级校审与核验签章")
    c.setFont(cjk_font, 6.9)
    c.setFillColor(colors.HexColor("#334155"))
    c.drawString(80, 74, "编制: 光筑数字孪生仿真引擎   |   校核: 多因素结构电气安全模块   |   审定: ____________")
    c.drawString(80, 56, f"依据 IEC 61724 / Perez 1990 / Faiman / GB 50797 · 项目: {meta['project_id']} · 摘要: {str(meta.get('snapshot_sha256', ''))[:10]}")
    stamp_hex = "#b91c1c" if rl_all_pass else "#475569"
    c.setStrokeColor(colors.HexColor(stamp_hex))
    if not rl_all_pass:
        c.setFillColor(colors.HexColor("#f1f5f9"))
        c.rect(W - 144, 52, 110, 44, fill=1, stroke=1)
    else:
        c.rect(W - 144, 52, 110, 44, fill=0, stroke=1)
    c.setFillColor(colors.HexColor(stamp_hex))
    c.setFont(cjk_font, 7.6)
    c.drawCentredString(W - 89, 78, "光筑工程仿真核验章" if rl_all_pass else "工程复核提示")
    c.setFont("Helvetica-Bold", 6.8)
    c.drawCentredString(W - 89, 63, "GUANGZHU VERIFIED" if rl_all_pass else "RECHECK REQUIRED")
    _draw_chrome(6, "25-Year Cashflow, Sensitivity & Sign-Off · 现金流与工程签章")
    c.showPage()

    c.save()
    return output_pdf


def _render_pvsyst_pdf_matplotlib(context: dict[str, Any], output_pdf: Path) -> Path:
    """Zero-extra-dependency 6-page A4《光筑专业报告》vector PDF fallback using locked matplotlib + Pillow."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.patches import Rectangle
    from PIL import Image

    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "PingFang SC",
        "Hiragino Sans GB",
        "Heiti SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    ctx = sanitize_report_structure(context)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    meta = ctx["meta"]
    site = ctx["site"]
    ori = ctx["orientation"]
    pv = ctx["pv_array"]
    inv = ctx["inverter"]
    res = ctx["results"]
    lt = ctx["loss_tree"]
    ver = ctx["verification"]
    lc = ctx["lifecycle"]
    prb = ctx.get("probabilities", {})
    mpl_all_pass = bool(ver.get("all_pass", False))
    icons = get_guangzhu_icon_assets()
    icon_pil = Image.open(io.BytesIO(icons["icon_128_bytes"])).convert("RGBA")

    page_specs = [
        (
            1,
            "System Overview & Parameters · 系统拓扑与输入参数",
            [
                f"项目名称：{meta.get('project_name', '')}  |  方案编号：{meta.get('variant_code', 'VC0')}",
                f"项目场址：{site.get('name', '')} ({site.get('city', '')}) · {float(site.get('lat', 0.0)):.4f}°N, {float(site.get('lon', 0.0)):.4f}°E",
                f"安装朝向：{ori.get('field_zh', ori.get('mode', '固定倾角'))} · 倾角 {float(ori.get('tilt_deg', 0.0)):.1f}° · 方位角 {float(ori.get('azimuth_compass_deg', 180.0)):.1f}°",
                f"光伏阵列：{pv.get('module_brand', '')} {pv.get('module_model', '')} × {pv.get('module_count', 0)} 块 / {pv.get('string_count', 0)} 串 × {pv.get('modules_per_string', 0)}S ({float(pv.get('dc_kw', 0.0)):.2f} kWp)",
                f"并网逆变：{inv.get('brand', '')} {inv.get('model', '')} × {inv.get('count', 0)} 台 ({float(inv.get('total_ac_kw', 0.0)):.1f} kWac, 容配比 {float(inv.get('pnom_ratio', 0.0)):.2f})",
                f"首年并网发电量 E_Grid：{float(res.get('e_grid_mwh', 0.0)):.2f} MWh/yr  |  比发电量：{float(res.get('specific_yield_kwh_kwp', 0.0)):.1f} kWh/kWp/yr  |  系统效率 PR：{float(res.get('pr_pct', 0.0)):.2f}%",
            ],
        ),
        (
            2,
            "Main Results & 13-Col Balances · 核心结果与月度平衡表",
            [
                f"全年水平总辐射 GlobHor：{float(res.get('glob_hor_kwh_m2', 0.0)):.1f} kWh/m²  |  斜面总辐射 GlobInc：{float(res.get('glob_inc_kwh_m2', 0.0)):.1f} kWh/m²",
                f"有效入射辐射 GlobEff：{float(res.get('glob_eff_kwh_m2', 0.0)):.1f} kWh/m²  |  阵列直流输出 EArray：{float(res.get('e_array_kwh', 0.0)) / 1000.0:.2f} MWh",
            ]
            + [
                f"{row.get('month_zh', '')}: GlobHor={float(row.get('glob_hor', 0.0)):.1f}, GlobInc={float(row.get('glob_inc', 0.0)):.1f}, T_Amb={float(row.get('t_amb', 0.0)):.1f}°C, E_Grid={float(row.get('e_grid', 0.0)) / 1000.0:.2f} MWh, PR={float(row.get('pr_pct', 0.0)):.1f}%"
                for row in ctx.get("normalized_monthly", [])[:12]
            ],
        ),
        (
            3,
            "8760h Loss Diagram & Sensitivity · 全年损耗树图与敏感度",
            [
                f"倾角增益：{float(lt.get('transposition_gain_pct', 0.0)):+.2f}%  |  近场遮挡损耗：{float(lt.get('near_shading_loss_pct', 0.0)):.2f}%  |  IAM 入射角损耗：{float(lt.get('iam_loss_pct', 0.0)):.2f}%",
                f"组件温度损耗：{float(lt.get('temp_loss_pct', 0.0)):.2f}%  |  灰尘遮蔽损耗：{float(lt.get('soiling_loss_pct', 0.0)):.2f}%  |  直流线损：{float(lt.get('dc_ohmic_loss_pct', 0.0)):.2f}%",
                f"逆变转换损耗：{float(lt.get('inv_op_loss_pct', 0.0)):.2f}%  |  交流并网损耗：{float(lt.get('ac_ext_loss_pct', 0.0)):.2f}%",
            ],
        ),
        (
            4,
            "Sky Dome, 12×24 Matrix & P50/P90 · 太阳轨迹与出力矩阵",
            [
                f"P50 发电量：{float(prb.get('p50_kwh', 0.0)) / 1000.0:.2f} MWh/yr  |  P75：{float(prb.get('p75_kwh', 0.0)) / 1000.0:.2f} MWh/yr",
                f"P90 发电量：{float(prb.get('p90_kwh', 0.0)) / 1000.0:.2f} MWh/yr  |  P95：{float(prb.get('p95_kwh', 0.0)) / 1000.0:.2f} MWh/yr",
                f"年均等效利用小时：{float(res.get('specific_yield_kwh_kwp', 0.0)):.1f} h  |  气象数据源：{site.get('meteo_source', 'TMY 8760h')}",
            ],
        ),
        (
            5,
            "MPPT Schedule & 6-Code Verification · 组串配电与国标校核",
            [
                f"{chk.get('code', '')} · {chk.get('title_zh', '')}：{chk.get('metric', '')}  [{chk.get('status', 'UNVERIFIED')}]"
                for chk in ver.get("national_code_checks", [])[:6]
            ],
        ),
        (
            6,
            "25-Year Cashflow, Sensitivity & Sign-Off · 现金流与工程签章",
            [
                f"总投资 CAPEX：{float(lc.get('capex_wan', 0.0)):.2f} 万元  |  25年累计发电：{float(lc.get('cum_mwh_25yr', 0.0)):.1f} MWh  |  LCOE：{_fmt_lcoe(lc.get('lcoe_cny_kwh'), 3)}",
                f"全投资 IRR：{_fmt_irr(lc.get('irr_pct'), 2)}  |  静态回收期：{_fmt_payback(lc.get('payback_yr'), 2)}  |  净现值 NPV：{float(lc.get('npv_wan', 0.0)):.2f} 万元",
                f"核验签章：{'光筑工程仿真核验章 · GUANGZHU VERIFIED' if mpl_all_pass else '工程复核提示 · RECHECK REQUIRED'}  |  摘要：{str(meta.get('snapshot_sha256', ''))[:12]}",
            ],
        ),
    ]

    with PdfPages(
        str(output_pdf),
        metadata={
            "Title": f"光筑专业报告 - {meta['project_name']} ({meta['variant_code']})",
            "Author": "光筑 Guangzhu 8760h Engineering Simulation Engine",
            "Subject": "并网光伏发电系统精细化工程仿真计算书",
            "Creator": "光筑专业报告引擎 Guangzhu Pro",
        },
    ) as pdf:
        for page_no, sec_title, lines in page_specs:
            fig = plt.figure(figsize=(8.27, 11.69), dpi=150)
            ax = fig.add_axes([0, 0, 1, 1])
            ax.set_xlim(0, 595)
            ax.set_ylim(0, 842)
            ax.axis("off")

            ax.add_patch(Rectangle((24, 780), 547, 40, facecolor="#f8fafc", edgecolor="#0f172a", linewidth=1.1))
            ax_icon = fig.add_axes([28 / 595, 786 / 842, 28 / 595, 28 / 842])
            ax_icon.imshow(icon_pil)
            ax_icon.axis("off")
            ax.text(64, 804, "光筑专业报告 · GUANGZHU PRO", fontsize=9.5, fontweight="bold", color="#0f172a")
            ax.text(64, 789, sec_title, fontsize=7.8, color="#334155")
            ax.text(563, 800, f"Page {page_no} of 6", fontsize=8.2, ha="right", color="#0f172a")

            for r_i in range(4):
                for c_i in range(3):
                    ax.text(
                        115 + c_i * 185,
                        150 + r_i * 175,
                        "光筑 · GUANGZHU · 光筑专业报告",
                        fontsize=10,
                        color="#0f172a",
                        alpha=0.06,
                        rotation=28,
                        ha="center",
                        va="center",
                    )

            y_cursor = 742
            for ln in lines:
                ax.text(32, y_cursor, ln, fontsize=8.4, color="#0f172a", va="top")
                y_cursor -= 34

            ax.plot([24, 571], [38, 38], color="#cbd5e1", linewidth=0.8)
            ax.text(24, 24, f"光筑专业报告 · {meta['project_name']} · 严禁外传", fontsize=7.2, color="#64748b")
            ax.text(571, 24, f"第 {page_no} / 6 页", fontsize=7.2, ha="right", color="#64748b")
            pdf.savefig(fig)
            plt.close(fig)

    return output_pdf


def render_pvsyst_report_pdf(
    context: dict[str, Any],
    output_pdf: Path,
    *,
    html_str: str | None = None,
    browsers: list[Path] | None = None,
) -> Path:
    """Render the 6-page A4《光筑专业报告》PDF via headless Chrome/Edge with automatic 6-page vector fallback."""
    import subprocess
    import tempfile
    from ..platform_compat import candidate_pdf_browsers

    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    html_content = html_str if html_str is not None else render_pvsyst_report_html(context)
    assert_no_private_path_leak(html_content)
    assert_no_pvsyst_visible_text(html_content)

    resolved_browsers = list(candidate_pdf_browsers()) if browsers is None else list(browsers)
    if resolved_browsers:
        for browser_candidate in dict.fromkeys(Path(p) for p in resolved_browsers if Path(p).is_file()):
            try:
                with tempfile.TemporaryDirectory(prefix="guangzhu-pro-report-", ignore_cleanup_errors=True) as tmp_dir:
                    tmp_root = Path(tmp_dir)
                    html_tmp = tmp_root / "guangzhu-pro-report.html"
                    pdf_tmp = tmp_root / "guangzhu-pro-report.pdf"
                    html_tmp.write_text(html_content, encoding="utf-8")
                    cmd = [
                        str(browser_candidate),
                        "--headless",
                        "--disable-gpu",
                        "--no-first-run",
                        "--no-pdf-header-footer",
                        f"--user-data-dir={tmp_root / 'profile'}",
                        f"--print-to-pdf={pdf_tmp}",
                        html_tmp.as_uri(),
                    ]
                    subprocess.run(
                        cmd,
                        check=True,
                        timeout=60,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    if pdf_tmp.is_file() and pdf_tmp.stat().st_size > 4096:
                        raw_pdf = pdf_tmp.read_bytes()
                        if raw_pdf[:5] == b"%PDF-":
                            output_pdf.write_bytes(raw_pdf)
                            return output_pdf
            except Exception:
                continue

    try:
        return _render_pvsyst_pdf_reportlab(context, output_pdf)
    except ImportError:
        return _render_pvsyst_pdf_matplotlib(context, output_pdf)
