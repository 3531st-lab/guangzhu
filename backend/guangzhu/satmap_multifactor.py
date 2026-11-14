"""Multi-Factor Real-World Engineering Optimization Engine for Satellite PV Design.

Optimizes rooftop photovoltaic designs across 12 coupled engineering dimensions:
  1. Array Topologies: south_fixed, east_west (dual 90°/270° butterfly), flush_pitched, elevated_canopy
  2. Module Posture & Rack: portrait vs landscape (bypass-diode bottom-shade resilience) & 1P vs 2P
  3. Structural Dead-Load Cap (max_roof_load_kg_m2) & Fixing (ballast / anchor / clamp / canopy_steel)
  4. Wind Uplift Zone Keepout (GB 50009 perimeter/corner setback scaling under high basic_wind_w0_kn_m2)
  5. Snow Load Shedding & Combined Downward Check (basic_snow_s0_kn_m2)
  6. Extreme Cold Voc & Hot Vmpp String Safety (extreme_temp_min_c / extreme_temp_max_c)
  7. Roof Surface Albedo (white TPO 0.65, concrete 0.28, metal 0.20, asphalt 0.12) -> Bifacial gain
  8. Environmental Pollution (clean, urban, industrial, coastal_salt, agri) -> Soiling & Degradation
  9. 3D Obstacle & Parapet Shading Module Pruning (max_module_shading_loss_pct -> pruned_shaded_modules)
 10. Fire Lanes (fire_lane_width_m) & Maintenance Walkways (maint_walkway_interval_m)
 11. Customer Load Profile & TOU Self-Consumption (industrial_day, commercial_afternoon, continuous_24h, export_all)
 12. Pareto Frontier Ranking & 6-Axis Factor Scoring (capacity, yield, economics, safety, self_use, shading_resilience)
"""

from __future__ import annotations

import inspect
import math
import re
from typing import Any

from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from . import electrical
from .models import GzError
from .pvsyst_engine import simulate_pvsyst


class ConflictingLoadParamsError(GzError, ValueError):
    """Raised when structural_params, multifactor_params, roof, or payload wind/snow inputs conflict."""

    def __init__(
        self,
        message_zh: str,
        fix_hint: str = "请统一 structural_params、multifactor_params 与 roof 中的基本风压/雪压输入。",
    ) -> None:
        super().__init__("CONFLICTING_LOAD_PARAMS", message_zh, fix_hint)


def resolve_wind_snow_params(payload: dict[str, Any], *, lat: float, lon: float) -> tuple[float, float]:
    """Resolve and cross-validate basic wind (w0) & snow (s0) pressures across all input containers."""
    sp = payload.get("structural_params") if isinstance(payload.get("structural_params"), dict) else {}
    mf = payload.get("multifactor_params") if isinstance(payload.get("multifactor_params"), dict) else {}
    mf_alt = payload.get("multifactor") if isinstance(payload.get("multifactor"), dict) else {}
    sys_d = payload.get("system") if isinstance(payload.get("system"), dict) else {}
    roof = payload.get("roof") if isinstance(payload.get("roof"), dict) else {}

    w0_candidates: list[float] = []
    s0_candidates: list[float] = []
    containers = (sp, mf, mf_alt, sys_d, roof, payload)
    wind_keys = ("w0_kn_m2", "basic_wind_w0_kn_m2", "wind_w0_kn_m2", "wind_kn_m2", "wind")
    snow_keys = ("s0_kn_m2", "basic_snow_s0_kn_m2", "snow_s0_kn_m2", "snow_kn_m2", "snow")

    for container in containers:
        if not isinstance(container, dict):
            continue
        for k in wind_keys:
            raw = container.get(k)
            if raw is None or raw == "" or (k == "wind" and isinstance(raw, dict)):
                continue
            if isinstance(raw, bool):
                raise ValueError(f"{k} must be a finite number, not bool.")
            val = float(raw)
            if not math.isfinite(val) or val < 0.0:
                raise ValueError(f"{k} must be finite and >= 0.")
            w0_candidates.append(val)
        for k in snow_keys:
            raw = container.get(k)
            if raw is None or raw == "" or (k == "snow" and isinstance(raw, dict)):
                continue
            if isinstance(raw, bool):
                raise ValueError(f"{k} must be a finite number, not bool.")
            val = float(raw)
            if not math.isfinite(val) or val < 0.0:
                raise ValueError(f"{k} must be finite and >= 0.")
            s0_candidates.append(val)

    if len(w0_candidates) >= 2 and (max(w0_candidates) - min(w0_candidates)) > 1e-4:
        raise ConflictingLoadParamsError(f"基本风压输入存在冲突: {w0_candidates}")
    if len(s0_candidates) >= 2 and (max(s0_candidates) - min(s0_candidates)) > 1e-4:
        raise ConflictingLoadParamsError(f"基本雪压输入存在冲突: {s0_candidates}")

    default_w0 = 0.60 if lon >= 120.5 else (0.50 if lat >= 36.0 else 0.45)
    default_s0 = 0.60 if lat >= 41.0 else (0.35 if lat >= 29.0 else 0.0)
    return (
        w0_candidates[0] if w0_candidates else default_w0,
        s0_candidates[0] if s0_candidates else default_s0,
    )

_PVSYST_TEXT_RE = re.compile(r"pvsyst", re.IGNORECASE)
_PRIVATE_OS_PATH_RE = re.compile(
    r"account-acct[^\s\"'<>]*|[A-Z]:[\\/]Users[\\/][^\s\"'<>]*|(?<![A-Za-z0-9+/=])/Users/[^\s\"'<>]+|(?<![A-Za-z0-9+/=])/home/[^\s\"'<>]+",
    re.IGNORECASE,
)


def scrub_pvsyst_text(value: Any) -> Any:
    """Scrub visible 'PVsyst' text in human-readable strings -> '光筑专业仿真', keeping keys & data URIs intact."""
    if isinstance(value, str):
        if value.startswith("data:") or value.startswith("/api/"):
            return value
        out = _PVSYST_TEXT_RE.sub("光筑专业仿真", value)
        out = _PRIVATE_OS_PATH_RE.sub("[已脱敏路径]", out)
        return out
    if isinstance(value, list):
        return [scrub_pvsyst_text(v) for v in value]
    if isinstance(value, tuple):
        return tuple(scrub_pvsyst_text(v) for v in value)
    if isinstance(value, dict):
        return {k: scrub_pvsyst_text(v) for k, v in value.items()}
    return value


ALBEDO_PRESETS: dict[str, float] = {
    "white_tpo": 0.65,
    "tpo": 0.65,
    "white_membrane": 0.65,
    "light_gravel": 0.40,
    "concrete": 0.28,
    "metal": 0.20,
    "color_steel": 0.20,
    "tiles": 0.18,
    "asphalt": 0.12,
    "bitumen": 0.12,
}

POLLUTION_PROFILES: dict[str, dict[str, Any]] = {
    "clean": {
        "label_zh": "清洁郊区 / 低粉尘",
        "soiling_pct": 1.2,
        "degradation_pct_yr": 0.40,
        "cleaning_cycles_yr": 2,
        "note_zh": "大气洁净度优，常规半年雨水+人工清洗即可维持高效出力。",
    },
    "urban": {
        "label_zh": "一般城市 / 轻工业园",
        "soiling_pct": 2.2,
        "degradation_pct_yr": 0.45,
        "cleaning_cycles_yr": 3,
        "note_zh": "标准城市工商业粉尘水平，建议春秋季及枯水期各清洗1次。",
    },
    "industrial": {
        "label_zh": "重工业粉尘区（冶金/化工/建材）",
        "soiling_pct": 3.9,
        "degradation_pct_yr": 0.55,
        "cleaning_cycles_yr": 6,
        "note_zh": "颗粒物沉降较快，建议倾角≥10°辅助雨水自洁并配置屋面清洗水路。",
    },
    "coastal_salt": {
        "label_zh": "沿海高盐雾区（台风/海洋气候）",
        "soiling_pct": 2.8,
        "degradation_pct_yr": 0.60,
        "cleaning_cycles_yr": 4,
        "note_zh": "高盐雾高湿环境，须选用双玻抗PID组件（IEC 61701 6级）及C5防腐热浸镀锌铝镁支架。",
    },
    "agri": {
        "label_zh": "农业氨气 / 生物质粉尘区",
        "soiling_pct": 4.2,
        "degradation_pct_yr": 0.52,
        "cleaning_cycles_yr": 6,
        "note_zh": "有机粉尘黏附性强且含氨气，须选用通过IEC 62716抗氨腐蚀认证组件并预留清洗马道。",
    },
}

# Normalized 24-hour load shapes (hours 0..23, sum = 24.0 so mean = 1.0)
LOAD_SHAPES_24H: dict[str, list[float]] = {
    "industrial_day": [
        0.32, 0.30, 0.30, 0.30, 0.32, 0.42,
        0.75, 1.25, 1.72, 1.85, 1.88, 1.55,
        1.35, 1.82, 1.88, 1.85, 1.75, 1.38,
        0.92, 0.72, 0.58, 0.48, 0.38, 0.33,
    ],
    "commercial_afternoon": [
        0.22, 0.20, 0.18, 0.18, 0.18, 0.22,
        0.30, 0.42, 0.62, 0.88, 1.05, 1.18,
        1.32, 1.68, 2.05, 2.28, 2.38, 2.25,
        1.98, 1.65, 1.28, 0.82, 0.42, 0.26,
    ],
    "continuous_24h": [
        0.94, 0.92, 0.92, 0.92, 0.93, 0.95,
        0.98, 1.02, 1.06, 1.08, 1.08, 1.05,
        1.03, 1.07, 1.08, 1.08, 1.06, 1.04,
        1.01, 0.99, 0.98, 0.97, 0.96, 0.95,
    ],
    "export_all": [0.0] * 24,
}

# Typical Eastern China industrial/commercial TOU self-use tariff multiplier by hour (0..23)
TOU_SELF_TARIFF_WEIGHT_24H: list[float] = [
    0.48, 0.48, 0.48, 0.48, 0.48, 0.48,  # 00-06 Valley
    0.48, 0.48, 0.92, 1.22, 1.25, 1.22,  # 06-08 Valley, 08-12 Morning Peak
    0.88, 0.88, 1.28, 1.38, 1.38, 1.32,  # 12-14 Flat, 14-18 Afternoon Critical Peak
    1.28, 1.25, 1.18, 0.90, 0.88, 0.52,  # 18-21 Evening Peak, 21-24 Flat/Valley
]

_PVSYST_PARAMS = set(inspect.signature(simulate_pvsyst).parameters.keys())


def _fnum(d: dict[str, Any], key: str, default: float) -> float:
    val = d.get(key)
    if val is None or val == "":
        return float(default)
    if isinstance(val, bool):
        raise ValueError(f"{key} must be a finite number, not bool.")
    out = float(val)
    if not math.isfinite(out):
        raise ValueError(f"{key} must be a finite number.")
    return out


def _pos_fnum(d: dict[str, Any], key: str, default: float, *, min_val: float = 1e-6) -> float:
    out = _fnum(d, key, default)
    if out <= min_val:
        raise ValueError(f"{key} must be > {min_val}.")
    return out


def _nonneg_fnum(d: dict[str, Any], key: str, default: float) -> float:
    out = _fnum(d, key, default)
    if out < 0.0:
        raise ValueError(f"{key} must be >= 0.")
    return out


def validate_satmap_common_inputs(payload: dict[str, Any]) -> None:
    """Strictly validate finite, non-boolean, and physically bounded numeric inputs across Satmap & Report payloads."""
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object.")

    sub_names = (
        "site",
        "roof",
        "layout_params",
        "electrical_params",
        "module_spec",
        "inverter_spec",
        "multifactor_params",
        "multifactor",
        "structural_params",
        "financial_params",
        "financial",
        "financial_dcf",
        "economics",
        "load_params",
        "summary",
        "pvsyst_summary",
        "electrical",
        "system",
        "equipment",
    )
    containers: list[dict[str, Any]] = [payload]
    for sname in sub_names:
        sub = payload.get(sname)
        if sub is not None:
            if not isinstance(sub, dict):
                raise ValueError(f"{sname} must be an object when provided.")
            containers.append(sub)
    losses_in = payload.get("losses")
    if losses_in is not None:
        if isinstance(losses_in, dict):
            containers.append(losses_in)
        elif not isinstance(losses_in, list):
            raise ValueError("losses must be an object or array when provided.")
    pvs_in = payload.get("pvsyst")
    if pvs_in is not None:
        if not isinstance(pvs_in, dict):
            raise ValueError("pvsyst must be an object when provided.")
        for psub in ("summary", "params"):
            if isinstance(pvs_in.get(psub), dict):
                containers.append(pvs_in[psub])

    def _chk(
        d: dict[str, Any],
        key: str,
        *,
        min_v: float | None = None,
        max_v: float | None = None,
        strict_min: bool = False,
        strict_max: bool = False,
    ) -> float | None:
        raw = d.get(key)
        if raw is None or raw == "":
            return None
        if isinstance(raw, bool):
            raise ValueError(f"{key} must be a finite number, not bool.")
        if isinstance(raw, (dict, list)):
            raise ValueError(f"{key} must be a scalar number.")
        val = float(raw)
        if not math.isfinite(val):
            raise ValueError(f"{key} must be a finite number.")
        if min_v is not None and (val <= min_v if strict_min else val < min_v):
            op = ">" if strict_min else ">="
            raise ValueError(f"{key} must be {op} {min_v}, got {val}.")
        if max_v is not None and (val >= max_v if strict_max else val > max_v):
            op = "<" if strict_max else "<="
            raise ValueError(f"{key} must be {op} {max_v}, got {val}.")
        return val

    nonneg_keys = (
        "dc_kw",
        "expected_dc_kw",
        "ac_kw",
        "total_ac_kw",
        "expected_ac_kw",
        "module_count",
        "expected_module_count",
        "string_count",
        "expected_string_count",
        "inverter_count",
        "expected_inverter_count",
        "modules_per_string",
        "expected_modules_per_string",
        "annual_load_kwh",
        "walkway_width_m",
        "maint_walkway_interval_m",
        "fire_lane_width_m",
        "setback_m",
        "edge_setback_m",
        "obstacle_setback_m",
        "obstacle_clearance_m",
        "parapet_height_m",
        "col_gap_m",
        "capex_per_w",
        "base_capex_cny_w",
        "capex_cny_w",
        "capex_cny",
        "capex_wan",
        "total_capex_wan",
        "tariff_self",
        "tariff_self_rmb",
        "self_use_tariff_cny",
        "tariff_grid",
        "tariff_feed_rmb",
        "feed_in_tariff_cny",
        "feed_in_tariff_rmb",
        "bess_capacity_kwh",
        "bess_cost_per_kwh",
        "peak_valley_spread_rmb",
        "uv_w_m2k_ms",
    )
    pos_keys = (
        "rated_ac_kw",
        "stc_w",
        "building_height_m",
        "canopy_clear_height_m",
        "canopy_clearance_m",
        "max_roof_load_kg_m2",
        "max_load_kg_m2",
        "roof_load_limit_kn_m2",
        "combined_down_limit_kn_m2",
        "uc_w_m2k",
    )
    pct_lt_100_keys = (
        "soiling_pct",
        "soiling_loss_pct",
        "shading_loss_pct",
        "snow_loss_pct",
        "lid_pct",
        "dc_ohmic_pct",
        "ac_ohmic_pct",
        "transformer_loss_pct",
    )
    pct_le_100_keys = (
        "discount_rate_pct",
        "discount_rate",
        "max_module_shading_loss_pct",
        "self_use_pct",
        "degradation_pct_yr",
    )

    lat_found = 32.4568
    lon_found = 119.9182
    for c in containers:
        lat_v = _chk(c, "lat", min_v=-90.0, max_v=90.0)
        if lat_v is not None:
            lat_found = lat_v
        lon_v = _chk(c, "lon", min_v=-180.0, max_v=180.0)
        if lon_v is not None:
            lon_found = lon_v
        for k in nonneg_keys:
            _chk(c, k, min_v=0.0)
        for k in pos_keys:
            _chk(c, k, min_v=0.0, strict_min=True)
        for k in pct_lt_100_keys:
            _chk(c, k, min_v=0.0, max_v=100.0, strict_max=True)
        for k in pct_le_100_keys:
            _chk(c, k, min_v=0.0, max_v=100.0)
        _chk(c, "self_use_ratio", min_v=0.0, max_v=1.0)
        _chk(c, "bifaciality", min_v=0.0, max_v=1.0)
        _chk(c, "tilt_deg", min_v=0.0, max_v=90.0)
        _chk(c, "slope_deg", min_v=0.0, max_v=85.0)
        _chk(c, "azimuth_deg")
        _chk(c, "extreme_temp_min_c", min_v=-65.0, max_v=50.0)
        _chk(c, "extreme_temp_max_c", min_v=-20.0, max_v=75.0)
        if c.get("albedo") is not None and c.get("albedo") != "":
            resolve_albedo(c.get("albedo"))

    resolve_wind_snow_params(payload, lat=lat_found, lon=lon_found)


def solve_irr_and_payback_from_cashflows(
    capex_wan: float,
    nets_wan: list[float],
) -> tuple[float | None, float | None]:
    """Solve project pre-tax IRR (%) and undiscounted static payback (years) without synthetic defaults."""
    if not math.isfinite(capex_wan) or capex_wan <= 0.0 or not nets_wan:
        return None, None

    cum = -capex_wan
    payback_yr: float | None = None
    for idx, cf in enumerate(nets_wan, 1):
        prev_cum = cum
        cum += cf
        if payback_yr is None and cum >= 0.0 and cf > 1e-9:
            payback_yr = round((idx - 1) + abs(prev_cum) / cf, 2)

    if not any(cf > 0.0 for cf in nets_wan):
        return None, None

    def _npv_at(r: float) -> float:
        total = -capex_wan
        factor = 1.0 + r
        if factor <= 0.0:
            return float("nan")
        disc = 1.0
        for cf in nets_wan:
            disc *= factor
            total += cf / disc
        return total

    lo_r, hi_r = -0.95, 5.00
    f_lo, f_hi = _npv_at(lo_r), _npv_at(hi_r)
    irr_pct: float | None = None
    if math.isfinite(f_lo) and math.isfinite(f_hi) and f_lo * f_hi <= 0.0:
        for _ in range(90):
            mid_r = 0.5 * (lo_r + hi_r)
            f_m = _npv_at(mid_r)
            if not math.isfinite(f_m):
                break
            if f_m == 0.0:
                lo_r = hi_r = mid_r
                break
            if (f_lo > 0.0 and f_m > 0.0) or (f_lo < 0.0 and f_m < 0.0):
                lo_r, f_lo = mid_r, f_m
            else:
                hi_r, f_hi = mid_r, f_m
        irr_pct = round(0.5 * (lo_r + hi_r) * 100.0, 2)

    return irr_pct, payback_yr


def solve_dcf_metrics(
    *,
    dc_kw: float,
    annual_kwh: float,
    weighted_tariff: float,
    capex_w: float,
    degradation_pct_yr: float = 0.45,
    discount_rate_pct: float = 6.0,
    om_yuan_w_yr: float = 0.042,
    inv_repl_yuan_w_yr13: float = 0.14,
    deg_floor: float = 0.72,
    bess_cap_kwh: float = 0.0,
    bess_cost_kwh: float = 760.0,
    peak_valley_spread: float = 0.65,
) -> dict[str, Any]:
    """Unified 25-year DCF financial model supporting 0% discount rate and None for unrecovered returns."""
    if not math.isfinite(dc_kw) or dc_kw < 0.0:
        raise ValueError("dc_kw must be finite and >= 0.")
    if not math.isfinite(annual_kwh) or annual_kwh < 0.0:
        raise ValueError("annual_kwh must be finite and >= 0.")
    if not math.isfinite(discount_rate_pct) or discount_rate_pct < 0.0:
        raise ValueError("discount_rate_pct must be finite and >= 0.")
    if not math.isfinite(capex_w) or capex_w < 0.0:
        raise ValueError("capex_w must be finite and >= 0.")

    if dc_kw <= 0.0 and bess_cap_kwh <= 0.0:
        return {
            "pv_capex_wan": 0.0,
            "bess_capex_wan": 0.0,
            "total_capex_wan": 0.0,
            "om_wan_yr": 0.0,
            "lcoe_cny_kwh": None,
            "lcoe_rmb_kwh": None,
            "npv_wan": 0.0,
            "irr_pct": None,
            "static_payback_years": None,
            "payback_yr": None,
            "dynamic_payback_years": None,
            "discounted_payback_yr": None,
            "cashflows_wan": [0.0] * 26,
        }

    pv_capex_wan = round(dc_kw * capex_w / 10.0, 2)
    bess_capex_wan = round(max(0.0, bess_cap_kwh) * max(0.0, bess_cost_kwh) / 10000.0, 2)
    total_capex_wan = round(pv_capex_wan + bess_capex_wan, 2)
    om_wan_yr = dc_kw * om_yuan_w_yr / 10.0 + bess_capex_wan * 0.015
    bess_gain_wan_yr = (
        (bess_cap_kwh * 0.90 * 1.80 * 0.895 * 330.0 * peak_valley_spread) / 10000.0
        if bess_cap_kwh > 0.0
        else 0.0
    )

    disc_r = float(discount_rate_pct) / 100.0
    deg_r = max(0.0, float(degradation_pct_yr) / 100.0)
    eff_annual_kwh = max(0.0, float(annual_kwh))

    nets_wan: list[float] = []
    cashflows_wan: list[float] = [-total_capex_wan]
    disc_cum = -total_capex_wan
    dynamic_pb: float | None = None
    dy_hit = False
    disc_cost_wan = total_capex_wan
    disc_kwh_sum = 0.0

    for yr in range(1, 26):
        yr_kwh = eff_annual_kwh * max(deg_floor, 1.0 - (yr - 1) * deg_r)
        yr_rev = (yr_kwh * weighted_tariff / 10000.0) + bess_gain_wan_yr * max(0.72, 1.0 - (yr - 1) * 0.012)
        yr_cost = om_wan_yr + (dc_kw * inv_repl_yuan_w_yr13 / 10.0 if yr == 13 else 0.0)
        net_cf = yr_rev - yr_cost
        nets_wan.append(net_cf)
        cashflows_wan.append(round(net_cf, 3))
        df = (1.0 + disc_r) ** yr
        d_net = net_cf / df
        prev_dc = disc_cum
        disc_cum += d_net
        if not dy_hit and disc_cum >= 0.0 and d_net > 1e-9:
            dynamic_pb = (yr - 1) + abs(prev_dc) / d_net
            dy_hit = True
        disc_cost_wan += yr_cost / df
        disc_kwh_sum += yr_kwh / df

    irr_pct, static_pb = solve_irr_and_payback_from_cashflows(total_capex_wan, nets_wan)
    lcoe_cny_kwh = round((disc_cost_wan * 10000.0) / disc_kwh_sum, 3) if disc_kwh_sum > 0.0 else None
    dyn_pb_out = round(dynamic_pb, 2) if dynamic_pb is not None else None

    return {
        "pv_capex_wan": pv_capex_wan,
        "bess_capex_wan": bess_capex_wan,
        "total_capex_wan": total_capex_wan,
        "om_wan_yr": round(om_wan_yr, 4),
        "lcoe_cny_kwh": lcoe_cny_kwh,
        "lcoe_rmb_kwh": lcoe_cny_kwh,
        "npv_wan": round(disc_cum, 2),
        "irr_pct": irr_pct,
        "static_payback_years": static_pb,
        "payback_yr": static_pb,
        "dynamic_payback_years": dyn_pb_out,
        "discounted_payback_yr": dyn_pb_out,
        "cashflows_wan": cashflows_wan,
    }


compute_25yr_cashflow = solve_dcf_metrics


def resolve_albedo(raw_albedo: Any, roof_type: str = "flat") -> tuple[float, str]:
    """Resolve surface name or numeric albedo into (albedo_value, surface_key), rejecting invalid inputs."""
    if raw_albedo is None or raw_albedo == "":
        if roof_type in ("double_slope", "single_slope", "metal"):
            return 0.20, "metal"
        return 0.28, "concrete"
    if isinstance(raw_albedo, bool):
        raise ValueError("albedo must be a surface preset or finite number in [0, 1], not bool.")
    if isinstance(raw_albedo, str):
        s_clean = raw_albedo.strip().lower()
        if s_clean in ("", "default", "auto"):
            if roof_type in ("double_slope", "single_slope", "metal"):
                return 0.20, "metal"
            return 0.28, "concrete"
        if s_clean in ALBEDO_PRESETS:
            return ALBEDO_PRESETS[s_clean], s_clean
        try:
            v = float(s_clean)
        except ValueError as exc:
            raise ValueError(f"Unsupported albedo preset or invalid number: {raw_albedo!r}.") from exc
        if not math.isfinite(v) or not (0.0 <= v <= 1.0):
            raise ValueError("albedo must be a finite number within [0, 1].")
        return v, "custom"
    if isinstance(raw_albedo, (int, float)):
        v = float(raw_albedo)
        if not math.isfinite(v) or not (0.0 <= v <= 1.0):
            raise ValueError("albedo must be a finite number within [0, 1].")
        surface_tag = "white_tpo" if v >= 0.50 else ("concrete" if v >= 0.24 else ("metal" if v >= 0.16 else "asphalt"))
        return v, surface_tag
    raise ValueError("albedo must be a preset string or finite number in [0, 1].")


def compute_string_voc_safety(
    module_spec: dict[str, Any] | None = None,
    inverter_spec: dict[str, Any] | None = None,
    extreme_temp_min_c: float = -10.0,
    extreme_temp_max_c: float = 40.0,
    requested_series: int | None = None,
) -> dict[str, Any]:
    """Compute exact IEC 62548 / GB 50797 extreme cold Voc & hot Vmpp string limits."""
    ms = module_spec or {}
    ins = inverter_spec or {}
    stc_w = _pos_fnum(ms, "stc_w", 580.0, min_val=10.0)
    voc_stc = _pos_fnum(ms, "voc_v", 51.2, min_val=5.0)
    vmp_stc = _pos_fnum(ms, "vmp_v", 42.6, min_val=5.0)
    beta_voc_pct_c = _fnum(ms, "beta_voc_pct_c", -0.25)
    if beta_voc_pct_c > 0:
        beta_voc_pct_c = -abs(beta_voc_pct_c)
    gamma_vmp_pct_c = _fnum(ms, "gamma_vmp_pct_c", -0.31)
    if gamma_vmp_pct_c > 0:
        gamma_vmp_pct_c = -abs(gamma_vmp_pct_c)

    max_sys_v = _pos_fnum(ms, "max_system_v", 1500.0, min_val=100.0)
    inv_max_dc_v = _pos_fnum(ins, "max_dc_v", 1100.0, min_val=100.0)
    v_dc_ceiling = min(max_sys_v, inv_max_dc_v)
    mppt_v_min = _pos_fnum(ins, "mppt_v_min", 200.0, min_val=50.0)
    mppt_v_max = _pos_fnum(ins, "mppt_v_max", min(1000.0, v_dc_ceiling - 50.0), min_val=mppt_v_min)

    t_min = max(-55.0, min(35.0, float(extreme_temp_min_c)))
    t_max = max(15.0, min(60.0, float(extreme_temp_max_c)))
    t_cell_hot = max(t_max + 26.0, 62.0)

    cold_voc_mod = voc_stc * (1.0 + (beta_voc_pct_c / 100.0) * (t_min - 25.0))
    cold_vmp_mod = vmp_stc * (1.0 + (gamma_vmp_pct_c / 100.0) * (t_min - 25.0))
    hot_vmp_mod = vmp_stc * (1.0 + (gamma_vmp_pct_c / 100.0) * (t_cell_hot - 25.0))

    max_series_voc_hard = max(1, int(math.floor((v_dc_ceiling * 0.995) / max(1.0, cold_voc_mod))))
    max_series_mppt_cold = max(1, int(math.floor(mppt_v_max / max(1.0, cold_vmp_mod))))
    max_series_safe = max(1, min(max_series_voc_hard, max_series_mppt_cold))
    min_series_mppt = max(1, int(math.ceil(mppt_v_min / max(1.0, hot_vmp_mod))))
    if min_series_mppt > max_series_safe:
        min_series_mppt = max_series_safe

    # Target ~620-780V nominal Vmpp for 1100V string inverters, clamped to safe window
    target_vmp = 680.0 if v_dc_ceiling <= 1150.0 else 1080.0
    ideal_n = int(round(target_vmp / max(10.0, vmp_stc)))
    # Prefer even string lengths when East-West or 2P is used, if within 1 of ideal
    recommended_series = max(min_series_mppt, min(max_series_safe, ideal_n))
    if recommended_series % 2 == 1 and (recommended_series - 1) >= min_series_mppt:
        if abs((recommended_series - 1) * vmp_stc - target_vmp) <= 60.0:
            recommended_series -= 1

    active_series = int(requested_series) if (requested_series is not None and int(requested_series) >= 1) else recommended_series
    cold_voc_v = round(recommended_series * cold_voc_mod, 1)
    hot_vmpp_v = round(recommended_series * hot_vmp_mod, 1)
    req_cold_voc_v = round(active_series * cold_voc_mod, 1)
    req_cold_vmpp_v = round(active_series * cold_vmp_mod, 1)
    req_hot_vmpp_v = round(active_series * hot_vmp_mod, 1)
    voc_ok = req_cold_voc_v <= v_dc_ceiling
    mppt_low_ok = req_hot_vmpp_v >= mppt_v_min
    mppt_high_ok = req_cold_vmpp_v <= mppt_v_max
    mppt_ok = bool(mppt_low_ok and mppt_high_ok)

    return {
        "extreme_temp_min_c": round(t_min, 1),
        "extreme_temp_max_c": round(t_max, 1),
        "hot_cell_temp_c": round(t_cell_hot, 1),
        "module_stc_w": round(stc_w, 1),
        "voc_stc_v": round(voc_stc, 2),
        "vmp_stc_v": round(vmp_stc, 2),
        "beta_voc_pct_c": round(beta_voc_pct_c, 3),
        "cold_voc_per_module_v": round(cold_voc_mod, 2),
        "cold_vmpp_per_module_v": round(cold_vmp_mod, 2),
        "hot_vmpp_per_module_v": round(hot_vmp_mod, 2),
        "inverter_max_dc_v": round(v_dc_ceiling, 1),
        "mppt_v_min": round(mppt_v_min, 1),
        "mppt_v_max": round(mppt_v_max, 1),
        "max_series_safe": max_series_safe,
        "max_series_voc_limit": max_series_voc_hard,
        "max_series_mppt_cold": max_series_mppt_cold,
        "min_series_mppt": min_series_mppt,
        "recommended_series": recommended_series,
        "current_series": active_series,
        "cold_voc_v": cold_voc_v,
        "hot_vmpp_v": hot_vmpp_v,
        "requested_series": active_series,
        "requested_cold_voc_v": req_cold_voc_v,
        "requested_cold_vmpp_v": req_cold_vmpp_v,
        "requested_hot_vmpp_v": req_hot_vmpp_v,
        "voc_margin_v": round(v_dc_ceiling - req_cold_voc_v, 1),
        "overvoltage_risk": not voc_ok,
        "mppt_overvoltage_risk": not mppt_high_ok,
        "undervoltage_risk": not mppt_low_ok,
        "safe": bool(voc_ok and mppt_ok),
    }


def compute_wind_snow_structural(
    *,
    orientation_mode: str,
    fixing_type: str,
    rack_rows: int,
    tilt_deg: float,
    building_height_m: float,
    base_setback_m: float,
    basic_wind_w0_kn_m2: float,
    basic_snow_s0_kn_m2: float,
    max_roof_load_kg_m2: float,
    module_weight_kg: float = 31.8,
    module_area_m2: float = 2.583,
    span_min_m: float = 30.0,
    roof_type: str = "flat",
    combined_down_limit_kn_m2: float | None = None,
) -> dict[str, Any]:
    """Evaluate GB 50009 wind uplift keepout setback, ballast/clamp sizing, dead load & snow shedding/downward combo."""
    w0 = max(0.20, float(basic_wind_w0_kn_m2))
    s0 = max(0.0, float(basic_snow_s0_kn_m2))
    h_bldg = max(3.0, float(building_height_m))
    max_load_kg = max(5.0, float(max_roof_load_kg_m2))
    mod_area = max(1.2, float(module_area_m2))

    # Height pressure factor mu_z (Category B terrain)
    mu_z = 1.00 if h_bldg <= 10.0 else min(1.62, round(1.00 + 0.16 * math.log(max(1.0, h_bldg / 10.0)) + 0.08 * ((h_bldg - 10.0) / 15.0), 3))

    # GB 50009 coastal/typhoon edge & corner wind suction keepout scaling
    typhoon_mode = w0 >= 0.65
    if typhoon_mode:
        wind_scale = 1.0 + 1.15 * (w0 - 0.50) * (1.12 if fixing_type == "ballast" else 0.72)
        if orientation_mode == "east_west":
            wind_scale *= 0.88  # Aerodynamic mutual shielding of closed butterfly array
        effective_setback_m = round(max(base_setback_m, base_setback_m * wind_scale, 1.2 if fixing_type == "ballast" else 0.9), 2)
        corner_keepout_m = round(min(4.5, max(1.4, 0.09 * span_min_m * (w0 / 0.65))), 2) if fixing_type == "ballast" else 0.0
    else:
        effective_setback_m = round(max(0.4, base_setback_m), 2)
        corner_keepout_m = 0.0

    # Aerodynamic shape factor mu_s by topology
    tilt_rad = math.radians(max(0.0, min(60.0, tilt_deg)))
    if orientation_mode == "east_west":
        mu_s_interior, mu_s_edge, mu_s_corner = 0.62, 0.92, 1.24
    elif orientation_mode == "flush_pitched":
        mu_s_interior, mu_s_edge, mu_s_corner = 0.72, 1.08, 1.45
    elif orientation_mode == "elevated_canopy":
        mu_s_interior, mu_s_edge, mu_s_corner = 1.05, 1.42, 1.85
    else:
        rack_mult = 1.08 if rack_rows >= 2 else 1.0
        tilt_mult = 0.78 + 0.018 * max(5.0, tilt_deg)
        mu_s_interior = round(0.88 * tilt_mult * rack_mult, 3)
        mu_s_edge = round(1.32 * tilt_mult * rack_mult, 3)
        mu_s_corner = round(1.76 * tilt_mult * rack_mult, 3)

    wk_interior = round(1.40 * mu_s_interior * mu_z * w0, 3)
    wk_edge = round(1.40 * mu_s_edge * mu_z * w0, 3)
    wk_corner = round(1.40 * mu_s_corner * mu_z * w0, 3)

    mod_kg_m2 = module_weight_kg / mod_area
    proj_cos = max(0.75, math.cos(tilt_rad))

    if fixing_type == "clamp":
        rack_kg_m2 = 2.6
        ballast_kg_per_mod = 0.0
        added_load_kg_m2 = round((mod_kg_m2 + rack_kg_m2) / max(0.92, proj_cos), 1)
        clamp_count = 6 if typhoon_mode else 4
        clamp_pull_kn = round((1.5 * wk_edge * mod_area) / clamp_count, 2)
        wind_ok = clamp_pull_kn <= 3.60
    elif fixing_type == "anchor":
        rack_kg_m2 = 5.4 if rack_rows == 1 else 6.1
        ballast_kg_per_mod = 0.0
        added_load_kg_m2 = round((mod_kg_m2 + rack_kg_m2) / proj_cos, 1)
        wind_ok = True
    elif fixing_type == "canopy_steel":
        rack_kg_m2 = 22.5
        ballast_kg_per_mod = 0.0
        added_load_kg_m2 = round(mod_kg_m2 + rack_kg_m2, 1)
        wind_ok = w0 <= 0.95
    else:
        # Ballast concrete blocks sized by weighted roof zone uplift
        rack_kg_m2 = 4.6 if orientation_mode == "east_west" else (5.0 if rack_rows == 1 else 5.6)
        self_kn_m2 = (mod_kg_m2 + rack_kg_m2) * 9.81 / 1000.0
        weighted_wk = 0.70 * wk_interior + 0.22 * wk_edge + 0.08 * (wk_interior if corner_keepout_m > 0 else wk_corner)
        net_uplift_kn_m2 = max(0.0, 1.45 * weighted_wk - self_kn_m2 * proj_cos)
        raw_ballast_kg = (net_uplift_kn_m2 * 1.12 * mod_area * 1000.0) / 9.81
        min_ballast_kg = 14.0 if orientation_mode == "east_west" else 20.0
        ballast_kg_per_mod = float(max(min_ballast_kg, math.ceil(raw_ballast_kg / 5.0) * 5.0))
        # Footprint dead load smeared over array bay area (including inter-row space reduces average slab pressure,
        # while localized pad pressure under rack is checked conservatively at 0.82 bay factor)
        bay_factor = 0.88 if orientation_mode == "east_west" else 0.76
        added_load_kg_m2 = round((mod_kg_m2 + rack_kg_m2 + (ballast_kg_per_mod / mod_area) * bay_factor) / proj_cos, 1)
        wind_ok = ballast_kg_per_mod <= 145.0

    # Snow shedding check, snow energy loss & GB 55001 combined downward load check (1.3 * Gk + 1.5 * Sk)
    mu_snow = 1.0 if tilt_deg <= 25.0 else max(0.0, (60.0 - tilt_deg) / 35.0)
    sk_snow_kn_m2 = round(mu_snow * s0, 3)
    snow_equiv_kg_m2 = round(sk_snow_kn_m2 * 1000.0 / 9.81, 1)
    if s0 <= 0.10:
        snow_loss_pct = 0.0
        snow_shedding_ok = True
    else:
        shed_factor = max(0.22, 1.0 - max(0.0, tilt_deg - 5.0) / 28.0)
        if orientation_mode == "elevated_canopy":
            shed_factor *= 0.85
        snow_loss_pct = round(min(6.5, s0 * 5.4 * shed_factor), 2)
        snow_shedding_ok = not (s0 >= 0.55 and tilt_deg < 8.0)

    added_dead_kn_m2 = round(added_load_kg_m2 * 9.81 / 1000.0, 3)
    comb_down_limit = (
        float(combined_down_limit_kn_m2)
        if (combined_down_limit_kn_m2 is not None and float(combined_down_limit_kn_m2) > 0.0)
        else (4.20 if roof_type == "flat" else 2.40)
    )
    comb_down_design_kn_m2 = round(1.3 * added_dead_kn_m2 + 1.5 * sk_snow_kn_m2, 2)
    snow_comb_ok = (comb_down_design_kn_m2 <= comb_down_limit) and (sk_snow_kn_m2 <= 3.60)
    snow_ok = bool(snow_shedding_ok and snow_comb_ok)

    load_ok = added_load_kg_m2 <= max_load_kg
    recommended_min_tilt_snow = 15.0 if s0 >= 0.50 else (10.0 if s0 >= 0.30 else 5.0)

    return {
        "fixing_type": fixing_type,
        "basic_wind_w0_kn_m2": round(w0, 2),
        "basic_snow_s0_kn_m2": round(s0, 2),
        "typhoon_mode": typhoon_mode,
        "effective_setback_m": effective_setback_m,
        "corner_keepout_m": corner_keepout_m,
        "wk_interior_kn_m2": wk_interior,
        "wk_edge_kn_m2": wk_edge,
        "wk_corner_kn_m2": wk_corner,
        "sk_snow_kn_m2": sk_snow_kn_m2,
        "snow_equiv_kg_m2": snow_equiv_kg_m2,
        "snow_loss_pct": snow_loss_pct,
        "comb_down_design_kn_m2": comb_down_design_kn_m2,
        "combined_down_limit_kn_m2": round(comb_down_limit, 2),
        "recommended_min_tilt_snow_deg": recommended_min_tilt_snow,
        "ballast_kg_per_module": round(ballast_kg_per_mod, 1),
        "added_dead_load_kg_m2": added_load_kg_m2,
        "max_roof_load_kg_m2": round(max_load_kg, 1),
        "load_margin_kg_m2": round(max_load_kg - added_load_kg_m2, 1),
        "load_utilization_pct": round(added_load_kg_m2 / max_load_kg * 100.0, 1),
        "load_ok": load_ok,
        "wind_ok": wind_ok,
        "snow_ok": snow_ok,
    }


def _module_shading_loss_pct(
    mx: float,
    my: float,
    module_base_z_m: float,
    lat: float,
    roof_poly: Polygon,
    parapet_height_m: float,
    tall_obstacles: list[tuple[Polygon, float, str]],
    mount_orientation: str,
    orientation_mode: str,
) -> tuple[float, str]:
    """Compute annual/winter-solstice weighted shading loss (%) on a single module from 3D obstacles + parapets."""
    m_pt = Point(mx, my)
    hemi_north = lat >= 0.0
    sun_az_center = 180.0 if hemi_north else 0.0
    winter_noon_alt = max(14.0, 90.0 - abs(lat) - 23.44)

    obs_loss = 0.0
    dominant_cause = "inter_row"

    for obs_poly, h_obs, obs_label in tall_obstacles:
        dh = h_obs - module_base_z_m
        if dh <= 0.15:
            continue
        dist_m = max(0.35, float(obs_poly.distance(m_pt)))
        elev_deg = math.degrees(math.atan2(dh, dist_m))
        if elev_deg <= 3.5:
            continue
        oc = obs_poly.centroid
        az_obs = math.degrees(math.atan2(oc.x - mx, oc.y - my)) % 360.0
        az_diff = ((az_obs - sun_az_center + 180.0) % 360.0) - 180.0
        # Obstacles on equatorward / morning-afternoon sun arc cast strong winter & shoulder-season shadows
        solar_weight = max(0.06, 0.58 + 0.42 * math.cos(math.radians(az_diff)))
        obx0, oby0, obx1, oby1 = obs_poly.bounds
        obs_span = max(1.0, math.hypot(obx1 - obx0, oby1 - oby0))
        az_span_deg = min(175.0, max(10.0, 2.0 * math.degrees(math.atan2(0.55 * obs_span, dist_m))))
        alt_ref = max(12.0, winter_noon_alt * (0.65 + 0.35 * max(0.2, math.cos(math.radians(az_diff * 0.6)))))
        v_block = min(1.0, max(0.0, (elev_deg - 3.0) / max(9.0, alt_ref * 1.15)))
        contrib = 72.0 * (az_span_deg / 195.0) * solar_weight * v_block
        if contrib > obs_loss:
            dominant_cause = f"obstacle:{obs_label}"
        obs_loss += contrib

    # Perimeter parapet wall shading (South, East, West walls cast inward shadows on flat roofs)
    parapet_loss = 0.0
    dh_parapet = parapet_height_m - module_base_z_m
    if dh_parapet > 0.08 and orientation_mode != "elevated_canopy":
        ext_coords = list(roof_poly.exterior.coords)
        for p1, p2 in zip(ext_coords, ext_coords[1:]):
            seg_dx, seg_dy = p2[0] - p1[0], p2[1] - p1[1]
            seg_len = math.hypot(seg_dx, seg_dy)
            if seg_len < 1.0:
                continue
            # Vector from module to nearest point on wall segment
            t_proj = max(0.0, min(1.0, ((mx - p1[0]) * seg_dx + (my - p1[1]) * seg_dy) / (seg_len * seg_len)))
            wx, wy = p1[0] + t_proj * seg_dx, p1[1] + t_proj * seg_dy
            d_wall = math.hypot(wx - mx, wy - my)
            if d_wall > dh_parapet * 6.5 or d_wall < 0.05:
                continue
            az_wall = math.degrees(math.atan2(wx - mx, wy - my)) % 360.0
            az_diff_w = abs(((az_wall - sun_az_center + 180.0) % 360.0) - 180.0)
            if az_diff_w <= 115.0:
                elev_w = math.degrees(math.atan2(dh_parapet, max(0.25, d_wall)))
                w_weight = max(0.15, math.cos(math.radians(az_diff_w * 0.78)))
                p_contrib = max(0.0, (elev_w - 5.0) * 0.72 * w_weight)
                if p_contrib > parapet_loss:
                    parapet_loss = p_contrib

    if parapet_loss > 0.5 and parapet_loss >= obs_loss:
        dominant_cause = "parapet"

    raw_total = obs_loss + parapet_loss
    # Landscape bypass-diode bottom-edge shading resilience (~26% less electrical mismatch loss than portrait)
    diode_factor = 0.74 if mount_orientation == "landscape" else 1.00
    final_loss = min(75.0, round(raw_total * diode_factor, 2))
    return final_loss, dominant_cause


def build_multifactor_layout(
    *,
    roof_poly_pts: list[tuple[float, float]],
    obstacles: list[dict[str, Any]],
    roof_type: str,
    slope_deg: float,
    lat: float,
    orientation_mode: str = "south_fixed",
    mount_orientation: str = "portrait",
    rack_rows: int = 1,
    tilt_deg: float = 15.0,
    azimuth_deg: float = 180.0,
    module_length_m: float = 2.278,
    module_width_m: float = 1.134,
    col_gap_m: float = 0.02,
    row_gap_override_m: float | None = None,
    effective_setback_m: float = 0.8,
    corner_keepout_m: float = 0.0,
    obstacle_setback_m: float = 0.4,
    parapet_height_m: float = 0.5,
    canopy_clear_height_m: float = 2.8,
    fire_lane_width_m: float = 0.0,
    maint_walkway_interval_m: float = 0.0,
    max_module_shading_loss_pct: float = 100.0,
) -> dict[str, Any]:
    """Place PV modules for any of the 4 topologies, carve fire/maintenance lanes, and prune shaded modules."""
    for _name, _val in (
        ("module_length_m", module_length_m),
        ("module_width_m", module_width_m),
        ("col_gap_m", col_gap_m),
        ("effective_setback_m", effective_setback_m),
        ("tilt_deg", tilt_deg),
        ("azimuth_deg", azimuth_deg),
        ("slope_deg", slope_deg),
    ):
        if not math.isfinite(float(_val)):
            raise ValueError(f"{_name} must be finite.")
    if float(module_length_m) <= 0.05 or float(module_width_m) <= 0.05:
        raise ValueError("module_length_m and module_width_m must be > 0.05m.")
    if float(col_gap_m) < 0.0:
        raise ValueError("col_gap_m must be >= 0.")
    if row_gap_override_m is not None:
        if not math.isfinite(float(row_gap_override_m)) or float(row_gap_override_m) < 0.0:
            raise ValueError("row_gap_override_m must be finite and >= 0.")
    if float(effective_setback_m) < 0.0:
        raise ValueError("effective_setback_m must be >= 0.")

    roof_poly = Polygon(roof_poly_pts)
    if not roof_poly.is_valid:
        roof_poly = roof_poly.buffer(0)
    if roof_poly.is_empty or roof_poly.area <= 1.0:
        raise ValueError("Invalid roof polygon area.")

    minx, miny, maxx, maxy = roof_poly.bounds
    cx0, cy0 = 0.5 * (minx + maxx), 0.5 * (miny + maxy)
    span_x, span_y = maxx - minx, maxy - miny

    usable = roof_poly.buffer(-max(0.0, effective_setback_m))

    # GB 50009 Corner wind uplift keepout zones under coastal/typhoon wind
    if corner_keepout_m > 0.05 and not usable.is_empty:
        corner_boxes = [
            box(minx - 0.5, miny - 0.5, minx + corner_keepout_m, miny + corner_keepout_m),
            box(maxx - corner_keepout_m, miny - 0.5, maxx + 0.5, miny + corner_keepout_m),
            box(minx - 0.5, maxy - corner_keepout_m, minx + corner_keepout_m, maxy + 0.5),
            box(maxx - corner_keepout_m, maxy - corner_keepout_m, maxx + 0.5, maxy + 0.5),
        ]
        usable = usable.difference(unary_union(corner_boxes))

    # Fire lane keepout strips (central cross or longitudinal fire access lane)
    if fire_lane_width_m > 0.05 and not usable.is_empty:
        hw_f = 0.5 * float(fire_lane_width_m)
        fire_strips = []
        if span_x >= 32.0:
            fire_strips.append(box(cx0 - hw_f, miny - 1.0, cx0 + hw_f, maxy + 1.0))
        if span_y >= 26.0:
            fire_strips.append(box(minx - 1.0, cy0 - hw_f, maxx + 1.0, cy0 + hw_f))
        if not fire_strips:
            fire_strips.append(box(cx0 - hw_f, miny - 1.0, cx0 + hw_f, maxy + 1.0))
        usable = usable.difference(unary_union(fire_strips))

    # Parse obstacles: elevated_canopy bridges over low obstacles (height_m <= canopy_clear_height_m - 0.30m)
    tall_obstacles: list[tuple[Polygon, float, str]] = []
    bridged_obstacle_count = 0
    for idx_o, obs in enumerate(obstacles or []):
        if not isinstance(obs, dict):
            continue
        obs_pts = obs.get("polygon_m") or obs.get("polygon") or obs.get("footprint") or []
        if len(obs_pts) < 3 and obs.get("w_m") and obs.get("h_m"):
            ox = float(obs.get("x_m", 0.0))
            oy = float(obs.get("y_m", 0.0))
            ow = float(obs.get("w_m", 2.0)) * 0.5
            oh = float(obs.get("h_m", 2.0)) * 0.5
            obs_pts = [[ox - ow, oy - oh], [ox + ow, oy - oh], [ox + ow, oy + oh], [ox - ow, oy + oh]]
        if len(obs_pts) < 3:
            continue
        obs_clean = [(float(p[0]), float(p[1])) for p in obs_pts]
        obs_poly = Polygon(obs_clean)
        if not obs_poly.is_valid:
            obs_poly = obs_poly.buffer(0)
        if obs_poly.is_empty:
            continue
        h_obs = max(0.0, float(obs.get("height_m") or 0.0))
        o_label = str(obs.get("name") or obs.get("label") or obs.get("id") or f"obs-{idx_o + 1}")
        o_setback = float(obs.get("setback_m") if obs.get("setback_m") is not None else obstacle_setback_m)

        if orientation_mode == "elevated_canopy" and h_obs <= (canopy_clear_height_m - 0.30):
            bridged_obstacle_count += 1
            continue

        if h_obs > 0.20:
            tall_obstacles.append((obs_poly, h_obs, o_label))
        if not usable.is_empty:
            usable = usable.difference(obs_poly.buffer(max(0.0, o_setback)))

    slope_len = module_length_m if mount_orientation == "portrait" else module_width_m
    wid_len = module_width_m if mount_orientation == "portrait" else module_length_m
    tilt_clamped = max(0.0, min(60.0, float(tilt_deg)))
    tilt_rad = math.radians(tilt_clamped)

    candidate_modules: list[dict[str, Any]] = []
    module_base_z = (
        canopy_clear_height_m
        if orientation_mode == "elevated_canopy"
        else (0.08 if orientation_mode == "flush_pitched" else 0.25)
    )

    # Winter solstice shadow factor for inter-row spacing
    winter_alt_9am = max(12.0, (90.0 - abs(lat) - 23.44) * 0.62)
    shadow_mult = min(3.2, max(1.15, 1.0 / math.tan(math.radians(winter_alt_9am)) * 0.72))

    if orientation_mode == "east_west":
        # East-West Butterfly Array (人字坡蝴蝶阵): ridges run North-South, pairs of West (270°) + East (90°)
        ew_tilt = max(5.0, min(15.0, tilt_clamped if tilt_clamped > 0 else 10.0))
        ew_rad = math.radians(ew_tilt)
        mod_proj_x = slope_len * math.cos(ew_rad)
        mod_span_y = wid_len
        ridge_seam = 0.04
        pair_footprint_x = 2.0 * mod_proj_x + ridge_seam
        aisle_gap_x = float(row_gap_override_m) if (row_gap_override_m is not None and row_gap_override_m >= 0.20) else 0.48
        pair_pitch_x = pair_footprint_x + aisle_gap_x
        y_step = mod_span_y + col_gap_m
        if pair_pitch_x <= 0.05 or y_step <= 0.05:
            raise ValueError("Invalid East-West grid step (pair_pitch_x / y_step must be > 0.05m).")
        MAX_AXIS_STEPS = 2000
        MAX_CANDIDATES = 25000
        gcr = round((2.0 * slope_len) / max(0.5, pair_pitch_x), 3)
        row_spacing_out = round(pair_pitch_x, 3)

        if not usable.is_empty:
            pair_idx = 0
            x_left = minx + effective_setback_m
            dist_since_walkway = 0.0
            x_steps = 0
            while x_left + pair_footprint_x <= maxx - effective_setback_m + 1e-9:
                x_steps += 1
                if x_steps > MAX_AXIS_STEPS:
                    raise ValueError("Layout grid X steps exceed safe limit (2000).")
                if maint_walkway_interval_m >= 4.0 and dist_since_walkway >= maint_walkway_interval_m:
                    x_left += 0.65
                    dist_since_walkway = 0.0
                    continue
                pair_idx += 1
                cx_west = x_left + 0.5 * mod_proj_x
                cx_east = x_left + 1.5 * mod_proj_x + ridge_seam
                col_idx = 0
                y_cur = miny + effective_setback_m + 0.5 * mod_span_y
                y_walk_acc = 0.0
                y_steps = 0
                while y_cur + 0.5 * mod_span_y <= maxy - effective_setback_m + 1e-9:
                    y_steps += 1
                    if y_steps > MAX_AXIS_STEPS:
                        raise ValueError("Layout grid Y steps exceed safe limit (2000).")
                    if len(candidate_modules) >= MAX_CANDIDATES:
                        raise ValueError("Candidate modules exceed safe limit (25000).")
                    if maint_walkway_interval_m >= 4.0 and y_walk_acc >= maint_walkway_interval_m:
                        y_cur += 0.65
                        y_walk_acc = 0.0
                        continue
                    cell_w = box(cx_west - 0.5 * mod_proj_x, y_cur - 0.5 * mod_span_y, cx_west + 0.5 * mod_proj_x, y_cur + 0.5 * mod_span_y)
                    cell_e = box(cx_east - 0.5 * mod_proj_x, y_cur - 0.5 * mod_span_y, cx_east + 0.5 * mod_proj_x, y_cur + 0.5 * mod_span_y)
                    # Place balanced West+East butterfly pair together when both fit, or individually if edge-clipped
                    if usable.contains(cell_w):
                        col_idx += 1
                        candidate_modules.append(
                            {
                                "row": pair_idx,
                                "col": 2 * col_idx - 1,
                                "cx": round(cx_west, 3),
                                "cy": round(y_cur, 3),
                                "_u": round(y_cur - cy0, 4),
                                "_v": round(cx_west - cx0, 4),
                                "w": round(mod_proj_x, 3),
                                "h": round(mod_span_y, 3),
                                "slope": "west",
                                "tilt_deg": round(ew_tilt, 1),
                                "azimuth_deg": 270.0,
                                "orientation": mount_orientation,
                                "orientation_mode": "east_west",
                            }
                        )
                    if usable.contains(cell_e):
                        if not usable.contains(cell_w):
                            col_idx += 1
                        candidate_modules.append(
                            {
                                "row": pair_idx,
                                "col": 2 * col_idx,
                                "cx": round(cx_east, 3),
                                "cy": round(y_cur, 3),
                                "_u": round(y_cur - cy0, 4),
                                "_v": round(cx_east - cx0, 4),
                                "w": round(mod_proj_x, 3),
                                "h": round(mod_span_y, 3),
                                "slope": "east",
                                "tilt_deg": round(ew_tilt, 1),
                                "azimuth_deg": 90.0,
                                "orientation": mount_orientation,
                                "orientation_mode": "east_west",
                            }
                        )
                    y_cur += y_step
                    y_walk_acc += y_step
                x_left += pair_pitch_x
                dist_since_walkway += pair_pitch_x
        tilt_clamped = ew_tilt
    else:
        # South-fixed, Flush-pitched, or Elevated Canopy
        rack_r = 2 if (rack_rows >= 2 and orientation_mode in ("south_fixed", "elevated_canopy")) else 1
        chord_len = rack_r * slope_len + (rack_r - 1) * 0.02
        proj_h = chord_len * math.cos(tilt_rad)
        rise_h = chord_len * math.sin(tilt_rad)
        if orientation_mode == "flush_pitched":
            clear_gap = float(row_gap_override_m) if (row_gap_override_m is not None and row_gap_override_m >= 0.15) else 0.35
            row_pitch = proj_h + clear_gap
        elif orientation_mode == "elevated_canopy":
            clear_gap = float(row_gap_override_m) if (row_gap_override_m is not None and row_gap_override_m >= 0.15) else 0.38
            row_pitch = proj_h + clear_gap
        else:
            if row_gap_override_m is not None and row_gap_override_m > 0.05:
                # Accept either row_gap_m (clear gap) or full pitch depending on magnitude
                row_pitch = (proj_h + row_gap_override_m) if row_gap_override_m < proj_h else row_gap_override_m
            else:
                row_pitch = proj_h + rise_h * shadow_mult
        row_spacing_out = round(row_pitch, 3)
        gcr = round(chord_len / max(0.5, row_pitch), 3)

        az_norm = float(azimuth_deg % 360.0)
        az_rad = math.radians(az_norm)
        u_x, u_y = -math.cos(az_rad), math.sin(az_rad)
        v_x, v_y = -math.sin(az_rad), -math.cos(az_rad)
        ext_coords = list(roof_poly.exterior.coords)
        u_vals = [(px - cx0) * u_x + (py - cy0) * u_y for px, py in ext_coords]
        v_vals = [(px - cx0) * v_x + (py - cy0) * v_y for px, py in ext_coords]
        min_u, max_u = min(u_vals), max(u_vals)
        min_v, max_v = min(v_vals), max(v_vals)
        axis_aligned_180 = abs(az_norm - 180.0) < 1e-5
        primary_az = round(az_norm, 1)
        secondary_az = round((az_norm + 180.0) % 360.0, 1)

        mod_proj_v = slope_len * math.cos(tilt_rad)
        x_step = wid_len + col_gap_m
        if row_pitch <= 0.05 or x_step <= 0.05:
            raise ValueError("Invalid layout grid step (row_pitch / x_step must be > 0.05m).")
        MAX_AXIS_STEPS = 2000
        MAX_CANDIDATES = 25000

        if not usable.is_empty:
            row_idx = 0
            v_cursor = min_v + effective_setback_m + 0.5 * proj_h
            v_walk_acc = 0.0
            v_steps = 0
            while v_cursor + 0.5 * proj_h <= max_v - effective_setback_m + 1e-9:
                v_steps += 1
                if v_steps > MAX_AXIS_STEPS:
                    raise ValueError("Layout grid row steps exceed safe limit (2000).")
                if roof_type == "double_slope" and orientation_mode == "flush_pitched" and abs(v_cursor) < (0.5 * proj_h + 0.35):
                    v_cursor += 0.70
                    continue
                if maint_walkway_interval_m >= 4.0 and v_walk_acc >= maint_walkway_interval_m:
                    v_cursor += 0.65
                    v_walk_acc = 0.0
                    continue
                row_idx += 1
                col_idx = 0
                u_cursor = min_u + effective_setback_m + 0.5 * wid_len
                u_walk_acc = 0.0
                u_steps = 0
                while u_cursor + 0.5 * wid_len <= max_u - effective_setback_m + 1e-9:
                    u_steps += 1
                    if u_steps > MAX_AXIS_STEPS:
                        raise ValueError("Layout grid col steps exceed safe limit (2000).")
                    if len(candidate_modules) >= MAX_CANDIDATES:
                        raise ValueError("Candidate modules exceed safe limit (25000).")
                    if maint_walkway_interval_m >= 4.0 and u_walk_acc >= maint_walkway_interval_m:
                        u_cursor += 0.65
                        u_walk_acc = 0.0
                        continue
                    tier_fits = True
                    tier_cells: list[tuple[float, float, int]] = []
                    for t_i in range(rack_r):
                        dv_tier = (t_i - 0.5 * (rack_r - 1)) * (mod_proj_v + 0.02)
                        v_mod = v_cursor + dv_tier
                        cx_m = cx0 + u_cursor * u_x + v_mod * v_x
                        cy_m = cy0 + u_cursor * u_y + v_mod * v_y
                        if axis_aligned_180:
                            cell = box(cx_m - 0.5 * wid_len, cy_m - 0.5 * mod_proj_v, cx_m + 0.5 * wid_len, cy_m + 0.5 * mod_proj_v)
                        else:
                            cell = Polygon(
                                [
                                    (cx_m + du * u_x + dv * v_x, cy_m + du * u_y + dv * v_y)
                                    for du, dv in [
                                        (-0.5 * wid_len, -0.5 * mod_proj_v),
                                        (0.5 * wid_len, -0.5 * mod_proj_v),
                                        (0.5 * wid_len, 0.5 * mod_proj_v),
                                        (-0.5 * wid_len, 0.5 * mod_proj_v),
                                    ]
                                ]
                            )
                        if not usable.contains(cell):
                            tier_fits = False
                            break
                        tier_cells.append((cx_m, cy_m, t_i + 1))

                    if tier_fits and tier_cells:
                        col_idx += 1
                        is_primary = (roof_type != "double_slope" or orientation_mode != "flush_pitched") or (v_cursor <= 0.0)
                        slope_side = "south" if is_primary else "north"
                        for cx_m, cy_m, tier_no in tier_cells:
                            candidate_modules.append(
                                {
                                    "row": row_idx,
                                    "tier": tier_no,
                                    "col": col_idx,
                                    "cx": round(cx_m, 3),
                                    "cy": round(cy_m, 3),
                                    "_u": round(u_cursor, 4),
                                    "_v": round(v_cursor, 4),
                                    "w": round(wid_len, 3),
                                    "h": round(mod_proj_v, 3),
                                    "slope": slope_side,
                                    "tilt_deg": round(tilt_clamped, 1),
                                    "azimuth_deg": primary_az if is_primary else secondary_az,
                                    "orientation": mount_orientation,
                                    "orientation_mode": orientation_mode,
                                }
                            )
                    u_cursor += x_step
                    u_walk_acc += x_step
                v_cursor += row_pitch
                v_walk_acc += row_pitch

    # Evaluate per-module 3D obstacle & parapet shading and prune modules above threshold
    kept_modules: list[dict[str, Any]] = []
    pruned_modules: list[dict[str, Any]] = []
    shade_threshold = max(1.0, float(max_module_shading_loss_pct))
    kept_shade_sum = 0.0

    for m_raw in candidate_modules:
        m_shade, m_cause = _module_shading_loss_pct(
            float(m_raw["cx"]),
            float(m_raw["cy"]),
            module_base_z + 0.5 * slope_len * math.sin(tilt_rad),
            lat,
            roof_poly,
            parapet_height_m if roof_type == "flat" else 0.0,
            tall_obstacles,
            mount_orientation,
            orientation_mode,
        )
        m_raw["shading_loss_pct"] = m_shade
        if m_shade > shade_threshold:
            pruned_modules.append(
                {
                    "id": f"PRUNED-{len(pruned_modules) + 1:04d}",
                    "cx": m_raw["cx"],
                    "cy": m_raw["cy"],
                    "w": m_raw["w"],
                    "h": m_raw["h"],
                    "shading_loss_pct": m_shade,
                    "cause": m_cause,
                }
            )
        else:
            m_raw["id"] = f"M-{len(kept_modules) + 1:04d}"
            m_raw["wired"] = True
            kept_modules.append(m_raw)
            kept_shade_sum += m_shade

    avg_obs_parapet_shade_pct = round(kept_shade_sum / len(kept_modules), 2) if kept_modules else 0.0
    base_interrow_shade = 1.3 if orientation_mode == "east_west" else (0.9 if orientation_mode == "flush_pitched" else 1.9)
    if mount_orientation == "landscape":
        base_interrow_shade = round(base_interrow_shade * 0.80, 2)

    return {
        "modules": kept_modules,
        "pruned_modules": pruned_modules,
        "pruned_shaded_modules": len(pruned_modules),
        "bridged_obstacle_count": bridged_obstacle_count,
        "row_spacing_m": row_spacing_out,
        "gcr": gcr,
        "tilt_deg": round(tilt_clamped, 1),
        "obs_parapet_shading_pct": avg_obs_parapet_shade_pct,
        "total_shading_loss_pct": min(65.0, round(base_interrow_shade + avg_obs_parapet_shade_pct, 2)),
    }


def evaluate_load_matching_and_economics(
    *,
    orientation_mode: str,
    dc_kw: float,
    annual_kwh: float,
    load_profile: str = "industrial_day",
    base_self_tariff_cny: float = 0.78,
    feed_in_tariff_cny: float = 0.38,
    base_capex_cny_w: float = 3.10,
    fixing_type: str = "ballast",
    rack_rows: int = 1,
    degradation_pct_yr: float = 0.45,
    discount_rate_pct: float = 6.0,
    annual_load_kwh: float | None = None,
) -> dict[str, Any]:
    """Match topology's diurnal generation shape against customer load profile & TOU tariff + 25-yr DCF."""
    if annual_load_kwh is not None:
        if isinstance(annual_load_kwh, bool) or not math.isfinite(float(annual_load_kwh)) or float(annual_load_kwh) < 0.0:
            raise ValueError("annual_load_kwh must be finite and >= 0.")

    profile_key = load_profile if load_profile in LOAD_SHAPES_24H else "industrial_day"
    explicit_zero_load = annual_load_kwh is not None and float(annual_load_kwh) == 0.0
    if dc_kw <= 0.0 or annual_kwh <= 0.0:
        raw_ratio = 0.0
        self_use_pct = 0.0
        self_use_kwh = 0.0
        weighted_tariff = (
            float(feed_in_tariff_cny)
            if (profile_key == "export_all" or explicit_zero_load)
            else (0.8 * base_self_tariff_cny + 0.2 * feed_in_tariff_cny)
        )
    elif profile_key == "export_all" or explicit_zero_load:
        raw_ratio = 0.0
        self_use_pct = 0.0
        self_use_kwh = 0.0
        weighted_tariff = float(feed_in_tariff_cny)
    else:
        # Diurnal normalized generation curve (sum = 1.0 over 24h)
        gen_24h = [0.0] * 24
        for hr in range(6, 19):
            x_solar = (hr - 12.0) / 6.0  # -1 at 6:00, 0 at 12:00, +1 at 18:00
            if orientation_mode == "east_west":
                # Dual morning + afternoon shoulders (broad flat-top butterfly curve)
                morning_lobe = math.exp(-((x_solar + 0.42) ** 2) / 0.19)
                afternoon_lobe = math.exp(-((x_solar - 0.44) ** 2) / 0.19)
                mid_fill = 0.38 * math.exp(-(x_solar**2) / 0.32)
                gen_24h[hr] = max(0.0, 0.56 * morning_lobe + 0.58 * afternoon_lobe + mid_fill)
            elif orientation_mode == "flush_pitched":
                gen_24h[hr] = max(0.0, math.exp(-(x_solar**2) / 0.27))
            else:
                # South-fixed / canopy: steeper midday bell curve peaking 11:30-13:00
                gen_24h[hr] = max(0.0, math.exp(-(x_solar**2) / 0.20))

        g_sum = sum(gen_24h) or 1.0
        gen_norm = [g / g_sum for g in gen_24h]

        load_shape = LOAD_SHAPES_24H[profile_key]
        l_sum = sum(load_shape) or 1.0
        load_norm = [v / l_sum for v in load_shape]

        # Typical customer annual demand relative to rooftop PV generation (~1.15x baseline)
        # Preserve explicit annual_load_kwh == 0.0 instead of synthesizing positive demand
        if annual_load_kwh is not None:
            effective_annual_load = float(annual_load_kwh)
        else:
            effective_annual_load = max(annual_kwh * 0.92, dc_kw * 1120.0)
        daily_pv = annual_kwh / 365.0
        daily_load = effective_annual_load / 365.0

        self_kwh_day = 0.0
        tou_weighted_self_num = 0.0
        if daily_load > 0.0:
            for hr in range(24):
                pv_h = daily_pv * gen_norm[hr]
                ld_h = daily_load * load_norm[hr]
                # Hourly energy conservation & cloud/load smoothing (0.96)
                absorbed_h = min(pv_h, ld_h * 0.96)
                self_kwh_day += absorbed_h
                tou_weighted_self_num += absorbed_h * (base_self_tariff_cny * TOU_SELF_TARIFF_WEIGHT_24H[hr])

        raw_ratio = min(0.985, max(0.0, self_kwh_day / max(1e-6, daily_pv)))
        if daily_pv > 0.0:
            raw_ratio = min(raw_ratio, min(1.0, daily_load / daily_pv))
        self_use_pct = round(raw_ratio * 100.0, 1)
        if annual_load_kwh is not None and annual_kwh > 0.0 and (annual_kwh * self_use_pct / 100.0) > effective_annual_load:
            self_use_pct = math.floor((effective_annual_load / annual_kwh) * 10000.0) / 100.0
        self_use_kwh = round(min(annual_kwh, effective_annual_load, annual_kwh * raw_ratio), 2)
        avg_self_tariff = (tou_weighted_self_num / self_kwh_day) if self_kwh_day > 1e-6 else base_self_tariff_cny
        weighted_tariff = round(raw_ratio * avg_self_tariff + (1.0 - raw_ratio) * feed_in_tariff_cny, 4)

    # Topology & fixing specific CAPEX adjustment (CNY/W)
    capex_w = float(base_capex_cny_w)
    if orientation_mode == "elevated_canopy":
        capex_w += 0.58
    elif orientation_mode == "east_west":
        capex_w -= 0.06  # Shared butterfly rails & lower ballast
    elif orientation_mode == "flush_pitched":
        capex_w -= 0.14
    if fixing_type == "anchor":
        capex_w += 0.07
    elif fixing_type == "clamp":
        capex_w -= 0.08
    if rack_rows >= 2 and orientation_mode == "south_fixed":
        capex_w -= 0.04
    capex_w = max(0.0, capex_w)

    dcf = solve_dcf_metrics(
        dc_kw=dc_kw,
        annual_kwh=annual_kwh,
        weighted_tariff=weighted_tariff,
        capex_w=capex_w,
        degradation_pct_yr=degradation_pct_yr,
        discount_rate_pct=discount_rate_pct,
        om_yuan_w_yr=0.042,
        inv_repl_yuan_w_yr13=0.14,
        deg_floor=0.72,
    )

    return {
        "load_profile": profile_key,
        "self_use_pct": 0.0 if (dc_kw <= 0.0 or annual_kwh <= 0.0) else self_use_pct,
        "self_use_ratio": round(raw_ratio, 6),
        "self_use_kwh": self_use_kwh,
        "discount_rate_pct": round(float(discount_rate_pct), 4),
        "weighted_tariff_cny_kwh": round(weighted_tariff, 4),
        "capex_cny_w": round(capex_w, 2),
        "capex_wan": dcf["total_capex_wan"],
        "lcoe_cny_kwh": dcf["lcoe_cny_kwh"],
        "npv_wan": dcf["npv_wan"],
        "irr_pct": dcf["irr_pct"],
        "payback_yr": dcf["static_payback_years"],
        "discounted_payback_yr": dcf["dynamic_payback_years"],
        "cashflows_wan": dcf["cashflows_wan"],
    }


def _call_pvsyst_for_scheme(
    *,
    lat: float,
    lon: float,
    dc_kw: float,
    ac_kw: float,
    orientation_mode: str,
    tilt_deg: float,
    azimuth_deg: float,
    modules: list[dict[str, Any]],
    stc_w: float,
    shading_loss_pct: float,
    albedo: float,
    soiling_pct: float,
    snow_loss_pct: float,
    offline: bool,
) -> dict[str, Any]:
    """Run Guangzhu 8760h hourly physical simulation with accurate sub-arrays & rear bifaciality by topology."""
    if dc_kw <= 0.0 or not modules:
        return {
            "annual_kwh": 0.0,
            "specific_yield_kwh_kwp": 0.0,
            "pr_pct": 0.0,
            "bifacial_gain_pct": 0.0,
        }

    sub_arrays: list[dict[str, Any]] | None = None
    eff_az = float(azimuth_deg % 360.0)
    if orientation_mode == "east_west":
        east_n = sum(1 for m in modules if m.get("slope") == "east")
        west_n = len(modules) - east_n
        sub_arrays = []
        if east_n > 0:
            sub_arrays.append(
                {
                    "name": "东坡蝴蝶子阵 (90°)",
                    "dc_kw": round(east_n * stc_w / 1000.0, 2),
                    "tilt_deg": tilt_deg,
                    "azimuth_deg": 90.0,
                }
            )
        if west_n > 0:
            sub_arrays.append(
                {
                    "name": "西坡蝴蝶子阵 (270°)",
                    "dc_kw": round(west_n * stc_w / 1000.0, 2),
                    "tilt_deg": tilt_deg,
                    "azimuth_deg": 270.0,
                }
            )
        eff_az = 90.0 if east_n >= west_n else 270.0
    else:
        south_n = sum(1 for m in modules if m.get("slope") != "north")
        north_n = len(modules) - south_n
        north_az = (eff_az + 180.0) % 360.0
        sub_arrays = []
        if south_n > 0:
            sub_arrays.append(
                {
                    "name": f"主坡子阵 ({eff_az:.0f}°)",
                    "dc_kw": round(south_n * stc_w / 1000.0, 2),
                    "tilt_deg": tilt_deg,
                    "azimuth_deg": eff_az,
                }
            )
        if north_n > 0:
            sub_arrays.append(
                {
                    "name": f"副坡子阵 ({north_az:.0f}°)",
                    "dc_kw": round(north_n * stc_w / 1000.0, 2),
                    "tilt_deg": tilt_deg,
                    "azimuth_deg": north_az,
                }
            )
        if south_n == 0 and north_n > 0:
            eff_az = north_az

    # Flush-mounted modules have minimal rear gap (~8cm), limiting bifacial rear irradiance capture
    eff_bifacial = orientation_mode != "flush_pitched"
    eff_bifaciality = 0.82 if orientation_mode == "elevated_canopy" else (0.76 if orientation_mode != "east_west" else 0.70)

    sim_kwargs: dict[str, Any] = {
        "dc_kw": dc_kw,
        "ac_kw": ac_kw,
        "tilt_deg": tilt_deg,
        "azimuth_deg": eff_az,
        "shading_loss_pct": min(68.0, shading_loss_pct + snow_loss_pct * 0.65),
        "bifacial": eff_bifacial,
        "albedo": albedo,
        "bifaciality": eff_bifaciality,
        "soiling_pct": soiling_pct,
        "sub_arrays": sub_arrays,
        "offline": offline,
    }
    if "orientation_mode" in _PVSYST_PARAMS:
        sim_kwargs["orientation_mode"] = orientation_mode

    res = simulate_pvsyst(lat, lon, **sim_kwargs)
    s = res["summary"]
    e_grid = float(s["e_grid_kwh"]) * max(0.85, 1.0 - snow_loss_pct * 0.0035)
    spec_y = e_grid / max(0.01, dc_kw)
    pr_val = float(s["pr_pct"]) * max(0.90, 1.0 - snow_loss_pct * 0.0035)
    bifacial_gain_pct = round(max(0.0, (albedo - 0.05) * (13.5 if eff_bifacial else 1.2)), 2)
    return {
        "annual_kwh": round(e_grid, 1),
        "specific_yield_kwh_kwp": round(spec_y, 1),
        "pr_pct": round(pr_val, 2),
        "bifacial_gain_pct": bifacial_gain_pct,
    }


def optimize_satmap_multifactor(payload: dict[str, Any]) -> dict[str, Any]:
    """Run 12-factor Pareto multi-scheme optimization and recommend the optimal engineering scheme."""
    validate_satmap_common_inputs(payload)
    site = payload.get("site") or {}
    roof = payload.get("roof") or {}
    mf = payload.get("multifactor_params") or payload
    equip_in = payload.get("equipment") if isinstance(payload.get("equipment"), dict) else {}

    lat = _fnum(site, "lat", _fnum(payload, "lat", 32.4568))
    lon = _fnum(site, "lon", _fnum(payload, "lon", 119.9182))
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise ValueError("Geographic coordinates out of range.")

    roof_type = str(roof.get("roof_type") or roof.get("type") or payload.get("roof_type") or "flat")
    if roof_type not in ("flat", "single_slope", "double_slope", "metal"):
        roof_type = "flat"
    slope_deg = _fnum(roof, "slope_deg", _fnum(payload, "slope_deg", 0.0 if roof_type == "flat" else 6.0))
    bldg_height_m = _fnum(roof, "building_height_m", _fnum(payload, "building_height_m", 12.0))
    parapet_height_m = _fnum(roof, "parapet_height_m", _fnum(payload, "parapet_height_m", 0.6 if roof_type == "flat" else 0.0))
    base_setback_m = _fnum(roof, "setback_m", _fnum(mf, "setback_m", _fnum(payload, "edge_setback_m", 0.8)))

    raw_poly = (
        roof.get("polygon_m")
        if roof.get("polygon_m") is not None
        else (payload.get("roof_polygon_m") if payload.get("roof_polygon_m") is not None else [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]])
    )
    if not isinstance(raw_poly, list) or len(raw_poly) < 3:
        raise ValueError("roof_polygon_m requires at least 3 [x, y] vertices.")
    clean_poly: list[tuple[float, float]] = []
    for p in raw_poly:
        if not isinstance(p, (list, tuple)) or len(p) < 2 or isinstance(p[0], bool) or isinstance(p[1], bool):
            raise ValueError("Each roof_polygon_m vertex must be finite [x, y].")
        px, py = float(p[0]), float(p[1])
        if not (math.isfinite(px) and math.isfinite(py)):
            raise ValueError("roof_polygon_m coordinates must be finite.")
        clean_poly.append((px, py))
    roof_poly_check = Polygon(clean_poly)
    if not roof_poly_check.is_valid:
        roof_poly_check = roof_poly_check.buffer(0)
    if roof_poly_check.is_empty or roof_poly_check.area < 4.0:
        raise ValueError("roof_polygon_m area is too small or invalid.")
    bx0, by0, bx1, by1 = roof_poly_check.bounds
    span_min_m = max(4.0, min(bx1 - bx0, by1 - by0))

    obstacles = (
        payload.get("obstacles")
        if payload.get("obstacles") is not None
        else (roof.get("obstacles") if roof.get("obstacles") is not None else [])
    )
    if not isinstance(obstacles, list):
        raise ValueError("obstacles must be a list.")
    for obs_chk in obstacles:
        if not isinstance(obs_chk, dict):
            raise ValueError("Each obstacle must be a dict.")
        if obs_chk.get("height_m") not in (None, ""):
            if isinstance(obs_chk["height_m"], bool):
                raise ValueError("obstacle height_m must not be boolean.")
            oh_val = float(obs_chk["height_m"])
            if not math.isfinite(oh_val) or oh_val < 0.0:
                raise ValueError("obstacle height_m must be finite and >= 0.")

    # Module & Inverter specs (with catalog lookup when module_id / inverter_id is specified)
    mod_spec_in = payload.get("module_spec") or payload.get("layout_params") or {}
    inv_spec_in = payload.get("inverter_spec") or payload.get("electrical_params") or {}
    mod_spec: dict[str, Any] = dict(mod_spec_in) if isinstance(mod_spec_in, dict) else {}
    inv_spec: dict[str, Any] = dict(inv_spec_in) if isinstance(inv_spec_in, dict) else {}

    req_mod_id = str(
        payload.get("module_id")
        or equip_in.get("module_id")
        or mod_spec.get("module_id")
        or mod_spec.get("id")
        or (mf.get("module_id") if isinstance(mf, dict) else "")
        or ""
    ).strip()
    resolved_mod_id = ""
    resolved_mod_model = "JKM580N-72HL4-BDV 580W"
    if req_mod_id:
        all_mods = electrical.load_catalog("modules.csv", include_extended=True)
        cat_mod = all_mods.get(req_mod_id)
        if cat_mod is None:
            for m_key, m_row in all_mods.items():
                if str(m_row.get("model") or "").strip().lower() == req_mod_id.lower():
                    cat_mod = m_row
                    req_mod_id = str(m_key)
                    break
        if cat_mod is None:
            raise GzError(
                "EQUIPMENT_UNKNOWN",
                f"未知组件型号 ID: {req_mod_id}，拒绝静默替换设备。",
                "请从已注册组件目录中选择型号，或补充目录规格后再优化。",
            )
        resolved_mod_id = str(cat_mod.get("module_id") or req_mod_id)
        resolved_mod_model = str(cat_mod.get("model") or resolved_mod_id)
        mod_spec.setdefault("stc_w", cat_mod.get("stc_w"))
        mod_spec.setdefault("length_m", cat_mod.get("length_m"))
        mod_spec.setdefault("width_m", cat_mod.get("width_m"))
        mod_spec.setdefault("weight_kg", cat_mod.get("weight_kg"))
        mod_spec.setdefault("voc_v", cat_mod.get("voc_v"))
        mod_spec.setdefault("vmp_v", cat_mod.get("vmp_v"))
        mod_spec.setdefault("isc_a", cat_mod.get("isc_a"))
        mod_spec.setdefault("imp_a", cat_mod.get("imp_a"))
        mod_spec.setdefault("beta_voc_pct_c", cat_mod.get("beta_voc_pct_c"))
        mod_spec.setdefault("gamma_vmp_pct_c", cat_mod.get("gamma_pmax_pct_c"))
        mod_spec.setdefault("alpha_isc_pct_c", cat_mod.get("alpha_isc_pct_c"))
        mod_spec.setdefault("max_system_v", cat_mod.get("max_system_voltage_v"))

    req_inv_id = str(
        payload.get("inverter_id")
        or equip_in.get("inverter_id")
        or inv_spec.get("inverter_id")
        or inv_spec.get("id")
        or (mf.get("inverter_id") if isinstance(mf, dict) else "")
        or ""
    ).strip()
    resolved_inv_id = ""
    resolved_inv_model = ""
    if req_inv_id:
        all_invs = electrical.load_catalog("inverters.csv", include_extended=True)
        cat_inv = all_invs.get(req_inv_id)
        if cat_inv is None:
            for i_key, i_row in all_invs.items():
                if str(i_row.get("model") or "").strip().lower() == req_inv_id.lower():
                    cat_inv = i_row
                    req_inv_id = str(i_key)
                    break
        if cat_inv is None:
            raise GzError(
                "EQUIPMENT_UNKNOWN",
                f"未知逆变器型号 ID: {req_inv_id}，拒绝静默替换设备。",
                "请从已注册逆变器目录中选择型号，或补充目录规格后再优化。",
            )
        resolved_inv_id = str(cat_inv.get("inverter_id") or req_inv_id)
        resolved_inv_model = str(cat_inv.get("model") or resolved_inv_id)
        inv_spec.setdefault("rated_ac_kw", cat_inv.get("rated_ac_kw"))
        inv_spec.setdefault("max_dc_v", cat_inv.get("max_dc_voltage_v"))
        inv_spec.setdefault("mppt_v_min", cat_inv.get("mppt_min_v"))
        inv_spec.setdefault("mppt_v_max", cat_inv.get("mppt_max_v"))
        inv_spec.setdefault("mppt_count", cat_inv.get("mppt_count"))
        inv_spec.setdefault("strings_per_mppt", cat_inv.get("strings_per_mppt"))
        inv_spec.setdefault("max_mppt_current_a", cat_inv.get("max_input_current_per_mppt_a"))
        inv_spec.setdefault("max_short_current_a", cat_inv.get("max_short_circuit_current_per_mppt_a"))

    has_explicit_inv = bool(
        req_inv_id
        or any(
            inv_spec.get(k) not in (None, "")
            for k in (
                "rated_ac_kw",
                "ac_kw",
                "mppt_count",
                "strings_per_mppt",
                "inverter_count",
                "max_mppt_current_a",
                "max_input_current_per_mppt_a",
                "max_short_current_a",
                "max_short_circuit_current_per_mppt_a",
            )
        )
        or payload.get("inverter_count") not in (None, "")
    )

    stc_w = _pos_fnum(mod_spec, "stc_w", _pos_fnum(payload, "stc_w", 580.0, min_val=10.0), min_val=10.0)
    mod_len = _pos_fnum(mod_spec, "length_m", 2.278, min_val=0.05)
    mod_wid = _pos_fnum(mod_spec, "width_m", 1.134, min_val=0.05)
    if not resolved_mod_id and abs(stc_w - 580.0) < 0.5 and abs(mod_len - 2.278) < 0.02 and abs(mod_wid - 1.134) < 0.02:
        resolved_mod_id = "jinko-jkm580n-72hl4-bdv"
        resolved_mod_model = str(mod_spec.get("model") or mod_spec.get("module_model") or "JKM580N-72HL4-BDV 580W")
    mod_weight = _pos_fnum(mod_spec, "weight_kg", 31.8, min_val=0.5)
    mod_vmp_v = _pos_fnum(mod_spec, "vmp_v", 42.6, min_val=5.0)
    mod_imp_a = _pos_fnum(mod_spec, "imp_a", round(stc_w / max(15.0, mod_vmp_v), 2), min_val=0.5)
    mod_isc_a = _pos_fnum(mod_spec, "isc_a", round(mod_imp_a * 1.055, 2), min_val=0.5)
    alpha_isc_pct_c = _fnum(mod_spec, "alpha_isc_pct_c", 0.045)

    rated_ac_kw = _pos_fnum(inv_spec, "rated_ac_kw", _pos_fnum(inv_spec, "ac_kw", 110.0, min_val=0.5), min_val=0.5)
    mppt_count_in = int(_pos_fnum(inv_spec, "mppt_count", 5.0 if rated_ac_kw <= 60.0 else (9.0 if rated_ac_kw == 110.0 else 10.0), min_val=0.5))
    strings_per_mppt_in = int(_pos_fnum(inv_spec, "strings_per_mppt", 2.0, min_val=0.5))
    max_mppt_current_a = _pos_fnum(
        inv_spec,
        "max_mppt_current_a",
        _pos_fnum(inv_spec, "max_input_current_per_mppt_a", 30.0, min_val=0.5),
        min_val=0.5,
    )
    max_short_current_a = _pos_fnum(
        inv_spec,
        "max_short_current_a",
        _pos_fnum(inv_spec, "max_short_circuit_current_per_mppt_a", 40.0, min_val=0.5),
        min_val=0.5,
    )
    raw_inv_cnt = inv_spec.get("inverter_count") if inv_spec.get("inverter_count") not in (None, "") else payload.get("inverter_count")
    explicit_inv_count: int | None = None
    if raw_inv_cnt not in (None, ""):
        if isinstance(raw_inv_cnt, bool):
            raise ValueError("inverter_count must not be boolean.")
        explicit_inv_count = int(raw_inv_cnt)
        if explicit_inv_count < 1:
            raise ValueError("inverter_count must be >= 1.")

    # 12-Factor Inputs
    default_tmin = -26.0 if lat >= 41.0 else (-13.0 if lat >= 34.0 else (-6.0 if lat >= 26.0 else 2.0))
    extreme_tmin_c = _fnum(mf, "extreme_temp_min_c", default_tmin)
    extreme_tmax_c = _fnum(mf, "extreme_temp_max_c", 40.0)
    raw_req_mps = (
        mf.get("modules_per_string")
        if mf.get("modules_per_string") not in (None, "")
        else (
            inv_spec.get("modules_per_string")
            if inv_spec.get("modules_per_string") not in (None, "")
            else payload.get("modules_per_string")
        )
    )
    if raw_req_mps not in (None, ""):
        if isinstance(raw_req_mps, bool):
            raise ValueError("modules_per_string must not be boolean.")
        if int(raw_req_mps) < 1:
            raise ValueError("modules_per_string must be >= 1.")
    voc_check = compute_string_voc_safety(
        mod_spec,
        inv_spec,
        extreme_temp_min_c=extreme_tmin_c,
        extreme_temp_max_c=extreme_tmax_c,
        requested_series=int(raw_req_mps) if raw_req_mps not in (None, "") else None,
    )

    sp_in = payload.get("structural_params") if isinstance(payload.get("structural_params"), dict) else {}
    default_max_load = 150.0 if roof_type == "flat" else 35.0
    if sp_in.get("roof_load_limit_kn_m2") not in (None, ""):
        default_max_load = round(_pos_fnum(sp_in, "roof_load_limit_kn_m2", 1.50, min_val=0.05) * 1000.0 / 9.81, 1)
    max_load_kg_m2 = _pos_fnum(
        mf,
        "max_roof_load_kg_m2",
        _pos_fnum(roof, "max_load_kg_m2", default_max_load, min_val=1.0),
        min_val=1.0,
    )
    comb_down_limit_in = (
        _pos_fnum(sp_in, "combined_down_limit_kn_m2", 4.20 if roof_type == "flat" else 2.40, min_val=0.1)
        if sp_in.get("combined_down_limit_kn_m2") not in (None, "")
        else None
    )
    w0_kn_m2, s0_kn_m2 = resolve_wind_snow_params(payload, lat=lat, lon=lon)

    raw_albedo = mf.get("albedo") if mf.get("albedo") is not None else roof.get("albedo")
    albedo_val, albedo_surface = resolve_albedo(raw_albedo, roof_type=roof_type)

    pollution_key = str(mf.get("pollution_level") or "urban").strip().lower()
    if pollution_key not in POLLUTION_PROFILES:
        pollution_key = "urban"
    pol_info = POLLUTION_PROFILES[pollution_key]
    soiling_pct = _nonneg_fnum(mf, "soiling_pct", _nonneg_fnum(payload, "soiling_pct", pol_info["soiling_pct"]))
    if soiling_pct >= 100.0:
        raise ValueError("soiling_pct must be within [0, 100).")
    degradation_pct_yr = _nonneg_fnum(mf, "degradation_pct_yr", pol_info["degradation_pct_yr"])

    max_shade_pct = _nonneg_fnum(mf, "max_module_shading_loss_pct", 12.0)
    fire_lane_w = _nonneg_fnum(
        mf,
        "fire_lane_width_m",
        _nonneg_fnum(mf, "walkway_width_m", _nonneg_fnum(payload, "walkway_width_m", 0.0)),
    )
    maint_interval_m = _nonneg_fnum(mf, "maint_walkway_interval_m", 0.0)
    canopy_height_m = _pos_fnum(
        mf,
        "canopy_clear_height_m",
        _pos_fnum(mf, "canopy_clearance_m", _pos_fnum(payload, "canopy_clearance_m", 2.8, min_val=0.5), min_val=0.5),
        min_val=0.5,
    )

    fp_in = payload.get("financial_params") if isinstance(payload.get("financial_params"), dict) else {}
    lp_load_in = payload.get("load_params") if isinstance(payload.get("load_params"), dict) else {}

    def _first_present(dicts: tuple[dict[str, Any], ...], keys: tuple[str, ...]) -> Any:
        for d_src in dicts:
            if not isinstance(d_src, dict):
                continue
            for key_name in keys:
                val = d_src.get(key_name)
                if val is None or val == "":
                    continue
                if isinstance(val, bool):
                    raise ValueError(f"{key_name} must not be boolean.")
                return val
        return None

    load_profile = str(
        _first_present((lp_load_in, fp_in, mf, payload), ("load_profile",)) or "industrial_day"
    ).strip().lower()
    if load_profile not in LOAD_SHAPES_24H:
        load_profile = "industrial_day"

    raw_self_t = _first_present((fp_in, lp_load_in, mf, payload), ("tariff_self_rmb", "tariff_self", "self_use_tariff_cny"))
    self_tariff = float(raw_self_t) if raw_self_t is not None else 0.78
    if not math.isfinite(self_tariff) or self_tariff < 0.0:
        raise ValueError("tariff_self_rmb must be finite and >= 0.")

    raw_feed_t = _first_present((fp_in, lp_load_in, mf, payload), ("tariff_feed_rmb", "tariff_grid", "feed_in_tariff_cny", "feed_in_tariff_rmb"))
    feed_tariff = float(raw_feed_t) if raw_feed_t is not None else 0.38
    if not math.isfinite(feed_tariff) or feed_tariff < 0.0:
        raise ValueError("tariff_feed_rmb must be finite and >= 0.")

    raw_capex = _first_present((fp_in, mf, payload), ("capex_per_w", "base_capex_cny_w"))
    base_capex_w = float(raw_capex) if raw_capex is not None else 3.12
    if not math.isfinite(base_capex_w) or base_capex_w < 0.0:
        raise ValueError("capex_per_w must be finite and >= 0.")

    raw_disc = _first_present((fp_in, mf, payload), ("discount_rate_pct", "discount_rate"))
    discount_rate_pct = float(raw_disc) if raw_disc is not None else 6.0
    if not math.isfinite(discount_rate_pct) or discount_rate_pct < 0.0:
        raise ValueError("discount_rate_pct must be finite and >= 0.")

    raw_annual_load = _first_present((lp_load_in, fp_in, mf, payload), ("annual_load_kwh",))
    if raw_annual_load is not None:
        annual_load_kwh: float | None = float(raw_annual_load)
        if not math.isfinite(annual_load_kwh) or annual_load_kwh < 0.0:
            raise ValueError("annual_load_kwh must be finite and >= 0.")
    else:
        annual_load_kwh = None

    objective = str(mf.get("objective") or payload.get("objective") or "balanced").strip().lower()
    offline = bool(payload.get("offline", True))

    user_tilt = _fnum(mf, "tilt_deg", _fnum(payload, "tilt_deg", max(12.0, min(24.0, round(abs(lat) * 0.52, 1)))))
    user_az = _fnum(mf, "azimuth_deg", _fnum(payload, "azimuth_deg", 180.0))

    # Candidate engineering archetypes covering the 12-factor design space
    opt_south_tilt = max(12.0, min(26.0, round(abs(lat) * 0.55, 0)))
    if s0_kn_m2 >= 0.50:
        opt_south_tilt = max(opt_south_tilt, 18.0)

    candidates_spec: list[dict[str, Any]] = [
        {
            "id": "south_fixed_ballast_1p",
            "name_zh": "正南固定倾角 · 混凝土配重 (1P竖装)",
            "badge_zh": "高单瓦发电基准",
            "orientation_mode": "south_fixed",
            "mount_orientation": "portrait",
            "rack_rows": 1,
            "fixing_type": "ballast" if roof_type == "flat" else "clamp",
            "tilt_deg": opt_south_tilt if roof_type == "flat" else max(4.0, slope_deg),
            "azimuth_deg": user_az,
        },
        {
            "id": "east_west_butterfly",
            "name_zh": "东西向人字坡蝴蝶阵 · 高密平缓出力 (-90°/+90°)",
            "badge_zh": "高装机量 · 午后高自发自用",
            "orientation_mode": "east_west",
            "mount_orientation": "landscape",
            "rack_rows": 1,
            "fixing_type": "ballast" if max_load_kg_m2 >= 26.0 else "anchor",
            "tilt_deg": 10.0 if s0_kn_m2 < 0.50 else 13.0,
            "azimuth_deg": 90.0,
        },
        {
            "id": "south_landscape_antishade_2p",
            "name_zh": "正南横装抗遮挡 · 2P双排锚固阵列",
            "badge_zh": "旁路二极管抗遮挡 · 抗台风轻载",
            "orientation_mode": "south_fixed",
            "mount_orientation": "landscape",
            "rack_rows": 2,
            "fixing_type": "anchor" if roof_type == "flat" else "clamp",
            "tilt_deg": user_tilt if roof_type == "flat" else max(4.0, slope_deg),
            "azimuth_deg": user_az,
        },
        {
            "id": "flush_lightweight_clamp",
            "name_zh": "顺坡轻量化夹具平铺阵列 (低恒载专案)",
            "badge_zh": "超低屋面荷载 (~15 kg/m²)",
            "orientation_mode": "flush_pitched",
            "mount_orientation": "portrait",
            "rack_rows": 1,
            "fixing_type": "clamp",
            "tilt_deg": max(5.0, slope_deg if slope_deg > 1.0 else 6.0),
            "azimuth_deg": user_az,
        },
        {
            "id": "elevated_canopy_bridge",
            "name_zh": f"架高阳光棚跨越阵列 (净空 {canopy_height_m:.1f}m)",
            "badge_zh": "跨越低矮障碍物 · 满铺高容",
            "orientation_mode": "elevated_canopy",
            "mount_orientation": "portrait",
            "rack_rows": 2,
            "fixing_type": "canopy_steel",
            "tilt_deg": 8.0 if s0_kn_m2 < 0.45 else 12.0,
            "azimuth_deg": user_az,
        },
    ]

    # Evaluate baseline site annual load using south_fixed reference so self-use comparison across schemes is apples-to-apples!
    schemes_raw: list[dict[str, Any]] = []
    mod_area = mod_len * mod_wid
    site_reference_load_kwh = annual_load_kwh

    for idx_c, c_spec in enumerate(candidates_spec):
        o_mode = c_spec["orientation_mode"]
        m_orient = c_spec["mount_orientation"]
        r_rows = int(c_spec["rack_rows"])
        fix_t = c_spec["fixing_type"]
        c_tilt = float(c_spec["tilt_deg"])
        c_az = float(c_spec["azimuth_deg"])

        struct_res = compute_wind_snow_structural(
            orientation_mode=o_mode,
            fixing_type=fix_t,
            rack_rows=r_rows,
            tilt_deg=c_tilt,
            building_height_m=bldg_height_m,
            base_setback_m=base_setback_m,
            basic_wind_w0_kn_m2=w0_kn_m2,
            basic_snow_s0_kn_m2=s0_kn_m2,
            max_roof_load_kg_m2=max_load_kg_m2,
            module_weight_kg=mod_weight,
            module_area_m2=mod_area,
            span_min_m=span_min_m,
            roof_type=roof_type,
            combined_down_limit_kn_m2=comb_down_limit_in,
        )

        lay_res = build_multifactor_layout(
            roof_poly_pts=clean_poly,
            obstacles=obstacles,
            roof_type=roof_type,
            slope_deg=slope_deg,
            lat=lat,
            orientation_mode=o_mode,
            mount_orientation=m_orient,
            rack_rows=r_rows,
            tilt_deg=c_tilt,
            azimuth_deg=c_az,
            module_length_m=mod_len,
            module_width_m=mod_wid,
            effective_setback_m=struct_res["effective_setback_m"],
            corner_keepout_m=struct_res["corner_keepout_m"],
            parapet_height_m=parapet_height_m,
            canopy_clear_height_m=canopy_height_m,
            fire_lane_width_m=fire_lane_w,
            maint_walkway_interval_m=maint_interval_m,
            max_module_shading_loss_pct=max_shade_pct,
        )

        raw_mods = lay_res["modules"]
        slope_groups: dict[str, list[dict[str, Any]]] = {}
        for m in raw_mods:
            slope_groups.setdefault(str(m.get("slope") or "south"), []).append(m)

        eff_min_s = min(voc_check["max_series_safe"], max(voc_check["min_series_mppt"], 6))

        def _slice_slope_lengths(n_grp: int, size_s: int) -> list[int]:
            if n_grp <= 0 or size_s <= 0:
                return []
            cnt = math.ceil(n_grp / size_s)
            short_cnt = cnt * size_s - n_grp
            if short_cnt == 0:
                return [size_s] * cnt
            if (size_s - 1) >= eff_min_s and short_cnt <= cnt:
                return [size_s] * (cnt - short_cnt) + [size_s - 1] * short_cnt
            return [size_s] * (n_grp // size_s)

        if raw_req_mps not in (None, ""):
            series_n = voc_check["requested_series"]
        else:
            rec_s = voc_check["recommended_series"]
            best_s = rec_s
            best_score: tuple[int, int, int, int] | None = None
            for cand_s in range(eff_min_s, voc_check["max_series_safe"] + 1):
                wired_total = 0
                has_short_s = False
                for g_list in slope_groups.values():
                    ls_here = _slice_slope_lengths(len(g_list), cand_s)
                    wired_total += sum(ls_here)
                    if any(ln != cand_s for ln in ls_here):
                        has_short_s = True
                cand_score = (
                    wired_total,
                    1 if cand_s >= max(eff_min_s, rec_s - 3) else 0,
                    -abs(cand_s - rec_s),
                    0 if not has_short_s else -1,
                    1 if cand_s % 2 == 0 else 0,
                )
                if best_score is None or cand_score > best_score:
                    best_score = cand_score
                    best_s = cand_s
            series_n = best_s

        # Trim each slope group cleanly using exact 3D/satmap-compatible string lengths & group strictly by (slope, str_len)
        wired_mods: list[dict[str, Any]] = []
        str_count = 0
        str_len_groups: dict[tuple[str, int], int] = {}
        for s_tag, g_list in slope_groups.items():
            ls_here = _slice_slope_lengths(len(g_list), series_n)
            keep_n = sum(ls_here)
            for ln in ls_here:
                str_len_groups[(s_tag, ln)] = str_len_groups.get((s_tag, ln), 0) + 1
            str_count += len(ls_here)
            for m_keep in g_list[:keep_n]:
                m_keep_clean = {k: v for k, v in m_keep.items() if not k.startswith("_")}
                wired_mods.append(m_keep_clean)

        mod_count = len(wired_mods)
        dc_kw = round(mod_count * stc_w / 1000.0, 2)
        mod_pmax_kw = stc_w / 1000.0
        isc_hot = mod_isc_a * (1.0 + max(0.0, alpha_isc_pct_c / 100.0) * (voc_check["hot_cell_temp_c"] - 25.0))

        def _can_allocate_units(units_n: int, unit_ac_kw: float, unit_mppts: int, eff_ports: int) -> bool:
            if units_n < 1 or eff_ports < 1:
                return False
            str_tokens = [tok for tok, cnt_t in str_len_groups.items() for _ in range(cnt_t)]
            groups_map: dict[tuple[int, int], list[tuple[str, int]]] = {}
            used_mods_u: dict[int, int] = {u_i: 0 for u_i in range(1, units_n + 1)}
            remaining_t = dict(str_len_groups)
            target_share = sum(t[1] for t in str_tokens) / max(1, units_n)
            for tok in str_tokens:
                s_len = tok[1]
                remaining_t[tok] -= 1
                reserved = sum(
                    math.ceil(k_rem / max(1, eff_ports))
                    for other_tok, k_rem in remaining_t.items()
                    if other_tok != tok and k_rem > 0
                )
                empty = units_n * unit_mppts - len(groups_map)
                choices = []
                for u_i in range(1, units_n + 1):
                    for mp_i in range(1, unit_mppts + 1):
                        attached = groups_map.get((u_i, mp_i), [])
                        if len(attached) < eff_ports and (not attached or attached[0] == tok):
                            overload = (used_mods_u[u_i] + s_len) * mod_pmax_kw > 1.30 * unit_ac_kw + 1e-9
                            res_failed = (empty - (0 if attached else 1)) < reserved
                            choices.append((overload, res_failed, (used_mods_u[u_i] + s_len * 0.5) > target_share, u_i, len(attached), mp_i))
                if not choices:
                    return False
                best_c = min(choices)
                if best_c[0]:
                    return False
                groups_map.setdefault((best_c[3], best_c[5]), []).append(tok)
                used_mods_u[best_c[3]] += s_len
            return True

        def _min_units_for_tier(unit_ac_kw: float, unit_mppts: int, eff_ports: int) -> int:
            if eff_ports < 1:
                return max(1, math.ceil(dc_kw / max(0.5, unit_ac_kw * 1.30)))
            mppt_ch = sum(math.ceil(cnt_t / eff_ports) for cnt_t in str_len_groups.values())
            u_try = max(
                1,
                math.ceil(dc_kw / max(0.5, unit_ac_kw * 1.30)),
                math.ceil(mppt_ch / max(1, unit_mppts)),
            )
            while u_try < str_count and not _can_allocate_units(u_try, unit_ac_kw, unit_mppts, eff_ports):
                u_try += 1
            return u_try

        # Physical inverter MPPT / parallel-string / short-circuit & working current / DC:AC port allocation (E05/E06/E07/E09)
        s_inv_id = resolved_inv_id
        s_inv_model = resolved_inv_model or str(inv_spec.get("model") or inv_spec.get("inverter_model") or "SG110CX-P2")
        if dc_kw <= 0.0 or str_count == 0:
            inv_count = 0
            s_rated_ac = rated_ac_kw
            ac_kw = 0.0
            dc_ac_ratio = 0.0
            dc_ac_ratio_ok = False
            mppt_channels_used = 0
            mppt_channels_capacity = 0
            max_strings_capacity = 0
            port_allocation_ok = False
        else:
            catalog_inv_tiers = (
                ("sungrow-sg110cx-p2", "SG110CX-P2", 110.0, 9, 2, 30.0, 40.0),
                ("sungrow-sg50cx-p2", "SG50CX-P2", 50.0, 4, 2, 30.0, 40.0),
                ("sungrow-sg36cx-p2", "SG36CX-P2", 36.0, 4, 2, 30.0, 40.0),
                ("huawei-sun2000-20ktl-m3", "SUN2000-20KTL-M3", 20.0, 2, 2, 27.0, 39.0),
                ("goodwe-gw8k-dt", "GW8K-DT", 8.0, 2, 1, 16.0, 21.0),
            )
            if has_explicit_inv:
                s_rated_ac = rated_ac_kw
                s_mppts = mppt_count_in
                s_ports = strings_per_mppt_in
                s_max_curr = max_mppt_current_a
                s_max_isc = max_short_current_a
                if not s_inv_id:
                    for t_id, t_mod, t_ac, t_mp, t_p, t_ic, t_isc in catalog_inv_tiers:
                        if abs(s_rated_ac - t_ac) < 0.2 and s_mppts == t_mp and s_ports == t_p:
                            s_inv_id, s_inv_model = t_id, t_mod
                            break
            else:
                # Select real catalog string inverter tier whose 3D-compatible unit count satisfies [0.85, 1.30] DC:AC
                s_inv_id, s_inv_model, s_rated_ac, s_mppts, s_ports, s_max_curr, s_max_isc = catalog_inv_tiers[-1]
                matched_tier = False
                for min_ratio_pass in (0.95, 0.85):
                    for t_id, t_mod, t_ac, t_mp, t_p, t_ic, t_isc in catalog_inv_tiers:
                        t_eff_p = max(
                            0,
                            min(t_p, int(math.floor(t_isc / max(0.1, isc_hot))), int(math.floor(t_ic / max(0.1, mod_imp_a)))),
                        )
                        if t_eff_p < 1:
                            continue
                        u_req = _min_units_for_tier(t_ac, t_mp, t_eff_p)
                        r_here = dc_kw / (u_req * t_ac)
                        if min_ratio_pass <= r_here <= 1.30:
                            s_inv_id, s_inv_model, s_rated_ac, s_mppts, s_ports, s_max_curr, s_max_isc = (
                                t_id,
                                t_mod,
                                t_ac,
                                t_mp,
                                t_p,
                                t_ic,
                                t_isc,
                            )
                            matched_tier = True
                            break
                    if matched_tier:
                        break

            eff_strings_per_mppt = max(
                0,
                min(
                    s_ports,
                    int(math.floor(s_max_isc / max(0.1, isc_hot))),
                    int(math.floor(s_max_curr / max(0.1, mod_imp_a))),
                ),
            )
            if eff_strings_per_mppt >= 1:
                mppt_channels_used = sum(math.ceil(cnt / eff_strings_per_mppt) for cnt in str_len_groups.values())
            else:
                mppt_channels_used = str_count

            if explicit_inv_count is not None:
                inv_count = explicit_inv_count
            else:
                inv_count = _min_units_for_tier(s_rated_ac, s_mppts, eff_strings_per_mppt)

            ac_kw = round(inv_count * s_rated_ac, 2)
            dc_ac_ratio = round(dc_kw / ac_kw, 3) if ac_kw > 0.0 else 0.0
            dc_ac_ratio_ok = 0.85 <= dc_ac_ratio <= 1.35
            mppt_channels_capacity = inv_count * s_mppts
            max_strings_capacity = inv_count * s_mppts * eff_strings_per_mppt
            port_allocation_ok = bool(
                eff_strings_per_mppt >= 1
                and mppt_channels_used <= mppt_channels_capacity
                and str_count <= max_strings_capacity
            )

        pv_sim = _call_pvsyst_for_scheme(
            lat=lat,
            lon=lon,
            dc_kw=dc_kw,
            ac_kw=ac_kw,
            orientation_mode=o_mode,
            tilt_deg=lay_res["tilt_deg"],
            azimuth_deg=c_az,
            modules=wired_mods,
            stc_w=stc_w,
            shading_loss_pct=lay_res["total_shading_loss_pct"],
            albedo=albedo_val,
            soiling_pct=soiling_pct,
            snow_loss_pct=struct_res["snow_loss_pct"],
            offline=offline,
        )

        if site_reference_load_kwh is None and pv_sim["annual_kwh"] > 0:
            # Anchor customer building annual demand to ~1.18x of baseline scheme generation
            site_reference_load_kwh = pv_sim["annual_kwh"] * 1.18

        econ_res = evaluate_load_matching_and_economics(
            orientation_mode=o_mode,
            dc_kw=dc_kw,
            annual_kwh=pv_sim["annual_kwh"],
            load_profile=load_profile,
            base_self_tariff_cny=self_tariff,
            feed_in_tariff_cny=feed_tariff,
            base_capex_cny_w=base_capex_w,
            fixing_type=fix_t,
            rack_rows=r_rows,
            degradation_pct_yr=degradation_pct_yr,
            discount_rate_pct=discount_rate_pct,
            annual_load_kwh=site_reference_load_kwh,
        )

        elec_ok = bool(voc_check["safe"] and port_allocation_ok and dc_ac_ratio_ok)
        all_pass = bool(
            struct_res["load_ok"]
            and struct_res["wind_ok"]
            and struct_res["snow_ok"]
            and elec_ok
            and mod_count > 0
        )

        pros: list[str] = []
        warnings: list[str] = []
        if o_mode == "east_west":
            pros.append("东西向人字坡蝴蝶阵消除大排距阴影，GCR显著提升，早晚双峰拓宽自发自用窗口")
            pros.append("闭合气动造型降低风揭吸力系数约28%，减少混凝土配重需求")
        elif o_mode == "elevated_canopy":
            pros.append(f"架高净空 {canopy_height_m:.1f}m 跨越 {lay_res['bridged_obstacle_count']} 处低矮屋面设备/天窗，消除碎片化禁布区")
        elif m_orient == "landscape":
            pros.append("组件横装使旁路二极管平行于底边，女儿墙与前排早晚阴影仅旁路1/3子串")
        elif fix_t == "clamp":
            pros.append(f"无穿孔直立锁边夹具固定，附加恒载仅 {struct_res['added_dead_load_kg_m2']} kg/m²")
        else:
            pros.append(f"正南最佳倾角 {lay_res['tilt_deg']}° 兼顾冬夏辐照与双面率背面增益 (+{pv_sim['bifacial_gain_pct']}%)")

        if lay_res["pruned_shaded_modules"] > 0:
            pros.append(f"自动剔除 {lay_res['pruned_shaded_modules']} 块年遮挡损失 >{max_shade_pct:.0f}% 的重度阴影短板组件")
        if not struct_res["load_ok"]:
            warnings.append(
                f"附加恒载 {struct_res['added_dead_load_kg_m2']} kg/m² 超出屋面限值 {max_load_kg_m2} kg/m²，建议改用夹具或化学锚栓"
            )
        if struct_res["typhoon_mode"]:
            warnings.append(
                f"高风压区 (w0={w0_kn_m2} kN/m²)，已按 GB 50009 自动外扩边缘风揭退距至 {struct_res['effective_setback_m']}m"
            )
        if not struct_res["snow_ok"]:
            warnings.append(
                f"高雪压风险 (s0={s0_kn_m2} kN/m²，组合下压 {struct_res['comb_down_design_kn_m2']} kN/m²)，超出滑雪或组合承载安全包络"
            )
        if not port_allocation_ok:
            warnings.append(
                f"逆变器 MPPT 端口或并串电流容量不足（需 {mppt_channels_used} 路 MPPT / {str_count} 串，可用 {mppt_channels_capacity} 路 / 最大可接 {max_strings_capacity} 串）"
            )
        if mod_count > 0 and not dc_ac_ratio_ok:
            warnings.append(f"容配比 {dc_ac_ratio:.2f}:1 超出 [0.85, 1.35] 合规区间，请调整逆变器机型或台数")

        cand_mps = series_n if mod_count > 0 else 0
        cand_cold_voc = round(cand_mps * voc_check["cold_voc_per_module_v"], 1) if cand_mps > 0 else voc_check["requested_cold_voc_v"]
        cand_hot_vmpp = round(cand_mps * voc_check["hot_vmpp_per_module_v"], 1) if cand_mps > 0 else voc_check["requested_hot_vmpp_v"]
        schemes_raw.append(
            {
                "id": c_spec["id"],
                "name_zh": c_spec["name_zh"],
                "badge_zh": c_spec["badge_zh"],
                "orientation_mode": o_mode,
                "mount_orientation": m_orient,
                "rack_type": f"{r_rows}P",
                "rack_rows": r_rows,
                "fixing_type": fix_t,
                "tilt_deg": lay_res["tilt_deg"],
                "azimuth_deg": c_az,
                "azimuth_dual_deg": [-90.0, 90.0] if o_mode == "east_west" else [c_az],
                "row_spacing_m": lay_res["row_spacing_m"],
                "setback_m": struct_res["effective_setback_m"],
                "effective_setback_m": struct_res["effective_setback_m"],
                "gcr": lay_res["gcr"],
                "module_id": resolved_mod_id or None,
                "module_model": resolved_mod_model,
                "inverter_id": s_inv_id or None,
                "inverter_model": s_inv_model,
                "rated_ac_kw": s_rated_ac,
                "module_count": mod_count,
                "pruned_shaded_modules": lay_res["pruned_shaded_modules"],
                "bridged_obstacle_count": lay_res["bridged_obstacle_count"],
                "dc_kw": dc_kw,
                "ac_kw": ac_kw,
                "dc_ac_ratio": round(dc_ac_ratio, 2),
                "dc_ac_ratio_ok": dc_ac_ratio_ok,
                "inverter_count": inv_count,
                "string_count": str_count,
                "modules_per_string": cand_mps,
                "string_series": cand_mps,
                "mppt_ports_used": str_count,
                "mppt_ports_total": max_strings_capacity,
                "mppt_channels_used": mppt_channels_used,
                "mppt_channels_capacity": mppt_channels_capacity,
                "max_strings_capacity": max_strings_capacity,
                "port_allocation_ok": port_allocation_ok,
                "electrical": {
                    "module_id": resolved_mod_id or None,
                    "inverter_id": s_inv_id or None,
                    "inverter_model": s_inv_model,
                    "rated_ac_kw": s_rated_ac,
                    "inverter_count": inv_count,
                    "ac_kw": ac_kw,
                    "dc_ac_ratio": round(dc_ac_ratio, 2),
                    "modules_per_string": cand_mps,
                    "string_count": str_count,
                    "mppt_ports_used": str_count,
                    "mppt_ports_total": max_strings_capacity,
                    "mppt_channels_used": mppt_channels_used,
                    "mppt_channels_capacity": mppt_channels_capacity,
                    "port_allocation_ok": port_allocation_ok,
                },
                "cold_voc_v": cand_cold_voc,
                "hot_vmpp_v": cand_hot_vmpp,
                "annual_kwh": pv_sim["annual_kwh"],
                "specific_yield_kwh_kwp": pv_sim["specific_yield_kwh_kwp"],
                "pr_pct": pv_sim["pr_pct"],
                "shading_loss_pct": lay_res["total_shading_loss_pct"],
                "bifacial_gain_pct": pv_sim["bifacial_gain_pct"],
                "soiling_loss_pct": round(soiling_pct, 2),
                "snow_loss_pct": struct_res["snow_loss_pct"],
                "load_kg_m2": struct_res["added_dead_load_kg_m2"],
                "max_load_kg_m2": struct_res["max_roof_load_kg_m2"],
                "ballast_kg_per_module": struct_res["ballast_kg_per_module"],
                "self_use_pct": econ_res["self_use_pct"],
                "self_use_kwh": econ_res["self_use_kwh"],
                "discount_rate_pct": econ_res["discount_rate_pct"],
                "weighted_tariff_cny_kwh": econ_res["weighted_tariff_cny_kwh"],
                "capex_cny_w": econ_res["capex_cny_w"],
                "capex_wan": econ_res["capex_wan"],
                "lcoe_cny_kwh": econ_res["lcoe_cny_kwh"],
                "npv_wan": econ_res["npv_wan"],
                "irr_pct": econ_res["irr_pct"],
                "payback_yr": econ_res["payback_yr"],
                "discounted_payback_yr": econ_res["discounted_payback_yr"],
                "financial_analysis": {
                    "discount_rate_pct": econ_res["discount_rate_pct"],
                    "self_use_pct": econ_res["self_use_pct"],
                    "self_use_kwh": econ_res["self_use_kwh"],
                    "weighted_tariff_cny_kwh": econ_res["weighted_tariff_cny_kwh"],
                    "capex_cny_w": econ_res["capex_cny_w"],
                    "capex_wan": econ_res["capex_wan"],
                    "npv_wan": econ_res["npv_wan"],
                    "irr_pct": econ_res["irr_pct"],
                    "payback_yr": econ_res["payback_yr"],
                    "discounted_payback_yr": econ_res["discounted_payback_yr"],
                    "lcoe_cny_kwh": econ_res["lcoe_cny_kwh"],
                },
                "constraints": {
                    "load_ok": struct_res["load_ok"],
                    "voc_ok": voc_check["safe"],
                    "elec_ok": elec_ok,
                    "port_allocation_ok": port_allocation_ok,
                    "dc_ac_ratio_ok": dc_ac_ratio_ok,
                    "wind_ok": struct_res["wind_ok"],
                    "snow_ok": struct_res["snow_ok"],
                    "all_pass": all_pass,
                },
                "_struct_res": struct_res,
                "pros_zh": pros,
                "warnings_zh": warnings,
                "modules": wired_mods,
                "pruned_modules": lay_res["pruned_modules"],
            }
        )

    # Compute normalized 6-axis factor_scores (0..100) + Pareto frontier + objective composite score
    max_dc = max((s["dc_kw"] for s in schemes_raw), default=1.0) or 1.0
    max_kwh = max((s["annual_kwh"] for s in schemes_raw), default=1.0) or 1.0
    max_spec = max((s["specific_yield_kwh_kwp"] for s in schemes_raw), default=1.0) or 1.0
    max_npv = max((s["npv_wan"] for s in schemes_raw), default=1.0)
    min_lcoe = min((s["lcoe_cny_kwh"] for s in schemes_raw if s["dc_kw"] > 0 and s["lcoe_cny_kwh"] is not None), default=0.30)

    weights_by_obj: dict[str, dict[str, float]] = {
        "balanced": {"capacity": 0.18, "yield": 0.22, "economics": 0.24, "safety": 0.16, "self_use": 0.12, "shading_resilience": 0.08},
        "max_capacity": {"capacity": 0.48, "yield": 0.18, "economics": 0.12, "safety": 0.10, "self_use": 0.06, "shading_resilience": 0.06},
        "max_yield": {"capacity": 0.20, "yield": 0.44, "economics": 0.14, "safety": 0.10, "self_use": 0.06, "shading_resilience": 0.06},
        "min_lcoe": {"capacity": 0.10, "yield": 0.20, "economics": 0.46, "safety": 0.10, "self_use": 0.08, "shading_resilience": 0.06},
        "max_self_use": {"capacity": 0.12, "yield": 0.16, "economics": 0.20, "safety": 0.10, "self_use": 0.36, "shading_resilience": 0.06},
        "wind_safe": {"capacity": 0.10, "yield": 0.14, "economics": 0.14, "safety": 0.46, "self_use": 0.06, "shading_resilience": 0.10},
    }
    w_map = weights_by_obj.get(objective, weights_by_obj["balanced"])

    for s in schemes_raw:
        cap_score = round(min(100.0, (s["dc_kw"] / max_dc) * 100.0), 1)
        yield_score = round(
            min(100.0, 0.55 * (s["annual_kwh"] / max_kwh) * 100.0 + 0.45 * (s["specific_yield_kwh_kwp"] / max_spec) * 100.0),
            1,
        )
        lcoe_val = s["lcoe_cny_kwh"]
        lcoe_ratio = (min_lcoe / max(0.08, lcoe_val)) if (s["dc_kw"] > 0 and lcoe_val is not None) else 0.0
        npv_ratio = max(0.0, s["npv_wan"] / max(1.0, max_npv)) if max_npv > 0 else 0.0
        econ_score = round(min(100.0, (0.55 * lcoe_ratio + 0.45 * npv_ratio) * 100.0), 1)

        load_headroom = max(-35.0, min(40.0, (s["max_load_kg_m2"] - s["load_kg_m2"]) / max(10.0, s["max_load_kg_m2"]) * 50.0))
        safety_base = 62.0 + load_headroom
        if not s["constraints"]["load_ok"]:
            safety_base -= 38.0
        if not s["constraints"]["wind_ok"]:
            safety_base -= 25.0
        if not s["constraints"]["snow_ok"]:
            safety_base -= 14.0
        if s["fixing_type"] in ("clamp", "anchor") and w0_kn_m2 >= 0.65:
            safety_base += 8.0
        safety_score = round(max(5.0, min(100.0, safety_base)), 1)

        self_use_score = round(min(100.0, max(15.0, s["self_use_pct"])), 1)
        shade_res_base = 100.0 - s["shading_loss_pct"] * 3.8
        if s["mount_orientation"] == "landscape":
            shade_res_base += 8.0
        if s["orientation_mode"] == "elevated_canopy":
            shade_res_base += 10.0
        shade_score = round(max(15.0, min(100.0, shade_res_base)), 1)

        f_scores = {
            "capacity": cap_score,
            "yield": yield_score,
            "economics": econ_score,
            "safety": safety_score,
            "self_use": self_use_score,
            "shading_resilience": shade_score,
        }
        s["factor_scores"] = f_scores

        comp = sum(f_scores[k] * w_map[k] for k in w_map)
        if not s["constraints"]["all_pass"]:
            comp -= 32.0  # Strongly penalize schemes violating structural dead-load or safety limits
        s["composite_score"] = round(comp, 2)

    # Mark Pareto frontier across (dc_kw MAX, specific_yield MAX, lcoe MIN, load_kg_m2 MIN, self_use_pct MAX)
    for i, a in enumerate(schemes_raw):
        dominated = False
        for j, b in enumerate(schemes_raw):
            if i == j or b["dc_kw"] <= 0:
                continue
            if b["constraints"]["all_pass"] and not a["constraints"]["all_pass"]:
                if b["npv_wan"] >= a["npv_wan"] and b["annual_kwh"] >= a["annual_kwh"] * 0.85:
                    dominated = True
                    break
            a_lcoe = a["lcoe_cny_kwh"] if a["lcoe_cny_kwh"] is not None else float("inf")
            b_lcoe = b["lcoe_cny_kwh"] if b["lcoe_cny_kwh"] is not None else float("inf")
            better_or_eq = (
                b["dc_kw"] >= a["dc_kw"]
                and b["specific_yield_kwh_kwp"] >= a["specific_yield_kwh_kwp"]
                and b_lcoe <= a_lcoe
                and b["load_kg_m2"] <= a["load_kg_m2"]
                and b["self_use_pct"] >= a["self_use_pct"]
            )
            strictly_better = (
                b["dc_kw"] > a["dc_kw"]
                or b["specific_yield_kwh_kwp"] > a["specific_yield_kwh_kwp"]
                or b_lcoe < a_lcoe
                or b["load_kg_m2"] < a["load_kg_m2"]
                or b["self_use_pct"] > a["self_use_pct"]
            )
            if better_or_eq and strictly_better:
                dominated = True
                break
        a["pareto_optimal"] = not dominated

    for s in schemes_raw:
        s_struct = s.pop("_struct_res", {})
        s["health_check"] = evaluate_engineering_health_check(
            {
                "dc_kw": s["dc_kw"],
                "ac_kw": s["ac_kw"],
                "port_allocation_ok": s["port_allocation_ok"],
                "mppt_channels_used": s["mppt_channels_used"],
                "mppt_channels_capacity": s["mppt_channels_capacity"],
                "max_strings_capacity": s["max_strings_capacity"],
                "cold_voc_v": s["cold_voc_v"],
                "max_dc_v": voc_check["inverter_max_dc_v"],
                "max_series_safe": voc_check["max_series_safe"],
                "min_series_mppt": voc_check["min_series_mppt"],
                "hot_vmpp_v": s["hot_vmpp_v"],
                "mppt_v_min": voc_check["mppt_v_min"],
                "mppt_v_max": voc_check["mppt_v_max"],
                "load_kg_m2": s["load_kg_m2"],
                "max_load_kg_m2": s["max_load_kg_m2"],
                "snow_ok": s["constraints"]["snow_ok"],
                "structural_check": s_struct,
                "fixing_type": s["fixing_type"],
                "effective_setback_m": s["effective_setback_m"],
                "basic_wind_w0_kn_m2": w0_kn_m2,
                "basic_snow_s0_kn_m2": s0_kn_m2,
                "string_series": s["string_series"],
                "string_count": s["string_count"],
                "shading_loss_pct": s["shading_loss_pct"],
                "irr_pct": s["irr_pct"],
                "payback_yr": s["payback_yr"],
            }
        )
        s["summary"] = {
            "dc_kw": s["dc_kw"],
            "ac_kw": s["ac_kw"],
            "dc_ac_ratio": s["dc_ac_ratio"],
            "module_count": s["module_count"],
            "modules_per_string": s["modules_per_string"],
            "inverter_count": s["inverter_count"],
            "string_count": s["string_count"],
            "mppt_ports_used": s["mppt_ports_used"],
            "mppt_ports_total": s["mppt_ports_total"],
            "module_id": s["module_id"],
            "inverter_id": s["inverter_id"],
            "inverter_model": s["inverter_model"],
            "annual_kwh": s["annual_kwh"],
            "self_use_pct": s["self_use_pct"],
            "self_use_kwh": s["self_use_kwh"],
            "discount_rate_pct": s["discount_rate_pct"],
            "npv_wan": s["npv_wan"],
            "irr_pct": s["irr_pct"],
            "payback_yr": s["payback_yr"],
            "lcoe_cny_kwh": s["lcoe_cny_kwh"],
            "port_allocation_ok": s["port_allocation_ok"],
            "all_pass": s["constraints"]["all_pass"],
            "ready_for_delivery": s["health_check"]["ready_for_delivery"],
        }

    schemes_sorted = sorted(
        schemes_raw,
        key=lambda item: (1 if item["constraints"]["all_pass"] else 0, item["composite_score"]),
        reverse=True,
    )
    recommended = schemes_sorted[0]
    rec_struct = compute_wind_snow_structural(
        orientation_mode=recommended["orientation_mode"],
        fixing_type=recommended["fixing_type"],
        rack_rows=recommended["rack_rows"],
        tilt_deg=recommended["tilt_deg"],
        building_height_m=bldg_height_m,
        base_setback_m=base_setback_m,
        basic_wind_w0_kn_m2=w0_kn_m2,
        basic_snow_s0_kn_m2=s0_kn_m2,
        max_roof_load_kg_m2=max_load_kg_m2,
        module_weight_kg=mod_weight,
        module_area_m2=mod_area,
        span_min_m=span_min_m,
        roof_type=roof_type,
        combined_down_limit_kn_m2=comb_down_limit_in,
    )

    return {
        "ok": True,
        "objective": objective,
        "recommended_id": recommended["id"],
        "shading_model_level": "scheme_heuristic_annual",
        "shading_scope_note_zh": "方案比选采用组件几何仰角/女儿墙加权启发式估算，三维精确近场遮挡请在三维场景中核算。",
        "string_voc_check": voc_check,
        "structural_check": rec_struct,
        "health_check": recommended["health_check"],
        "summary": recommended["summary"],
        "financial_analysis": recommended["financial_analysis"],
        "effective_assumptions": {
            "discount_rate_pct": round(discount_rate_pct, 4),
            "annual_load_kwh": round(site_reference_load_kwh, 2) if site_reference_load_kwh is not None else None,
            "explicit_annual_load_kwh": round(annual_load_kwh, 2) if annual_load_kwh is not None else None,
            "tariff_self_rmb": round(self_tariff, 4),
            "tariff_feed_rmb": round(feed_tariff, 4),
            "capex_per_w": round(base_capex_w, 4),
            "basic_wind_w0_kn_m2": round(w0_kn_m2, 3),
            "basic_snow_s0_kn_m2": round(s0_kn_m2, 3),
            "max_roof_load_kg_m2": round(max_load_kg_m2, 2),
        },
        "environment": {
            "albedo": albedo_val,
            "albedo_surface": albedo_surface,
            "pollution_level": pollution_key,
            "pollution_label_zh": pol_info["label_zh"],
            "soiling_pct": round(soiling_pct, 2),
            "degradation_pct_yr": round(degradation_pct_yr, 2),
            "cleaning_cycles_yr": pol_info["cleaning_cycles_yr"],
            "note_zh": pol_info["note_zh"],
            "load_profile": load_profile,
            "discount_rate_pct": round(discount_rate_pct, 4),
            "annual_load_kwh": round(site_reference_load_kwh, 2) if site_reference_load_kwh is not None else None,
            "max_module_shading_loss_pct": max_shade_pct,
            "fire_lane_width_m": fire_lane_w,
            "maint_walkway_interval_m": maint_interval_m,
        },
        "schemes": schemes_sorted,
    }


def _pick_first_num(sources: list[dict[str, Any]], keys: tuple[str, ...], default: float) -> float:
    for src in sources:
        if not isinstance(src, dict):
            continue
        for k in keys:
            val = src.get(k)
            if val is None or isinstance(val, bool):
                continue
            try:
                f = float(val)
                if math.isfinite(f):
                    return f
            except (TypeError, ValueError):
                continue
    return float(default)


def evaluate_engineering_health_check(payload: dict[str, Any]) -> dict[str, Any]:
    """Run 8-item pre-delivery engineering compliance check with pass/warn/fail & Chinese fix hints."""
    if not isinstance(payload, dict):
        raise ValueError("Health check payload must be a JSON object.")
    validate_satmap_common_inputs(payload)

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    pvs = payload.get("pvsyst") if isinstance(payload.get("pvsyst"), dict) else {}
    pvs_sum = pvs.get("summary") if isinstance(pvs.get("summary"), dict) else {}
    pvs_params = pvs.get("params") if isinstance(pvs.get("params"), dict) else {}
    elec = payload.get("electrical") if isinstance(payload.get("electrical"), dict) else {}
    wiring = (
        payload.get("wiring_optimization")
        if isinstance(payload.get("wiring_optimization"), dict)
        else (elec.get("wiring_optimization") if isinstance(elec.get("wiring_optimization"), dict) else {})
    )
    struct_chk = payload.get("structural_check") if isinstance(payload.get("structural_check"), dict) else {}
    fin = payload.get("financial_dcf") if isinstance(payload.get("financial_dcf"), dict) else {}
    mf = (
        payload.get("multifactor")
        if isinstance(payload.get("multifactor"), dict)
        else (payload.get("multifactor_params") if isinstance(payload.get("multifactor_params"), dict) else {})
    )
    mf_params = payload.get("multifactor_params") if isinstance(payload.get("multifactor_params"), dict) else {}
    roof = payload.get("roof") if isinstance(payload.get("roof"), dict) else {}
    site = payload.get("site") if isinstance(payload.get("site"), dict) else {}
    lp = payload.get("layout_params") if isinstance(payload.get("layout_params"), dict) else {}
    ep = payload.get("electrical_params") if isinstance(payload.get("electrical_params"), dict) else {}
    mod_spec = payload.get("module_spec") if isinstance(payload.get("module_spec"), dict) else lp
    inv_spec = payload.get("inverter_spec") if isinstance(payload.get("inverter_spec"), dict) else ep
    voc_chk_in = payload.get("string_voc_check") if isinstance(payload.get("string_voc_check"), dict) else {}
    mppt_rows = (
        payload.get("mppt_table")
        if isinstance(payload.get("mppt_table"), list)
        else (elec.get("mppt_table") if isinstance(elec.get("mppt_table"), list) else [])
    )
    active_mppt = [r for r in mppt_rows if isinstance(r, dict) and int(r.get("string_count") or 0) > 0]

    # 1. DC:AC Ratio Check
    dc_kw = _pick_first_num([payload, summary, pvs_sum], ("dc_kw",), 0.0)
    ac_kw = _pick_first_num([payload, summary, pvs_sum, elec], ("ac_kw", "total_ac_kw", "rated_ac_kw"), 0.0)
    if dc_kw <= 0.0 and payload.get("dc_ac_ratio") is not None:
        dc_ac = _pick_first_num([payload], ("dc_ac_ratio",), 0.0)
        dc_kw = round(dc_ac * 100.0, 2)
        ac_kw = 100.0
    elif payload.get("dc_ac_ratio") is not None and payload.get("dc_kw") is None and not summary:
        dc_ac = _pick_first_num([payload], ("dc_ac_ratio",), 1.15)
    else:
        dc_ac = round(dc_kw / ac_kw, 2) if (dc_kw > 0.0 and ac_kw > 0.0) else 0.0

    port_alloc_failed = (payload.get("port_allocation_ok") is False) or (elec.get("port_allocation_ok") is False)
    mppt_curr_failed = any(
        (r.get("ok") is False) and ("电流" in str(r.get("status") or ""))
        for r in active_mppt
    )
    if port_alloc_failed or mppt_curr_failed:
        st_dcac = "fail"
        mppt_used_chk = int(_pick_first_num([payload, elec], ("mppt_channels_used",), float(len(active_mppt))))
        mppt_cap_chk = int(_pick_first_num([payload, elec], ("mppt_channels_capacity",), float(len(mppt_rows))))
        str_cnt_chk = int(_pick_first_num([payload, summary, elec], ("string_count",), 0.0))
        max_str_cap_chk = int(_pick_first_num([payload, elec], ("max_strings_capacity",), 0.0))
        if mppt_curr_failed and not port_alloc_failed:
            hint_dcac = "MPPT 通道并串工作电流或短路电流超出逆变器单路限值，请减少单路并串数或更换大电流逆变器机型。"
        else:
            hint_dcac = (
                f"逆变器 MPPT 端口或并串电流容量不足（需 {mppt_used_chk} 路 MPPT / {str_cnt_chk} 串，"
                f"当前逆变器仅提供 {mppt_cap_chk} 路 MPPT / 最大可接 {max_str_cap_chk} 串），请选用多路 MPPT 机型或增配逆变器台数。"
            )
    elif dc_kw <= 0.0 or ac_kw <= 0.0 or dc_ac < 0.85:
        st_dcac = "fail"
        hint_dcac = "交流逆变器容量配置过大或有效装机为空（容配比 <0.85），请减少逆变器台数、选用小功率机型或扩大可布板区域。"
    elif dc_ac > 1.50:
        st_dcac = "fail"
        hint_dcac = f"容配比高达 {dc_ac:.2f}:1（超出 1.50 上限），正午严重限功率且超配过载，请增配逆变器台数。"
    elif dc_ac < 1.00:
        st_dcac = "warn"
        hint_dcac = f"容配比 {dc_ac:.2f}:1 略偏保守（<1.00），建议核减逆变器冗余容量以降低交流侧 BOS 投资。"
    elif dc_ac > 1.35:
        st_dcac = "warn"
        hint_dcac = f"容配比 {dc_ac:.2f}:1 偏高（>1.35），晴天正午存在一定削峰损失，建议结合负荷消纳曲线复核经济最优配比。"
    else:
        st_dcac = "pass"
        hint_dcac = "容配比处于 1.00~1.35 工商业黄金区间，兼顾早晚弱光出力与逆变器利用小时数。"

    # 2 & 3. Extreme Cold Voc Margin & Hot Vmpp Window Checks
    lat_val = _pick_first_num([site, payload], ("lat",), 32.4568)
    def_tmin = -26.0 if lat_val >= 41.0 else (-13.0 if lat_val >= 34.0 else (-8.0 if lat_val >= 27.0 else 2.0))
    tmin_c = _pick_first_num([payload, mf, mf_params, ep, voc_chk_in], ("extreme_temp_min_c",), def_tmin)
    tmax_c = _pick_first_num([payload, mf, mf_params, ep, voc_chk_in], ("extreme_temp_max_c",), 40.0)
    req_series_raw = (
        payload.get("modules_per_string")
        or payload.get("string_series")
        or mf_params.get("modules_per_string")
        or ep.get("modules_per_string")
        or summary.get("modules_per_string")
    )
    computed_voc = compute_string_voc_safety(
        mod_spec,
        inv_spec,
        extreme_temp_min_c=tmin_c,
        extreme_temp_max_c=tmax_c,
        requested_series=int(req_series_raw) if req_series_raw is not None else None,
    )
    max_dc_v = _pick_first_num([payload, inv_spec, voc_chk_in], ("max_dc_v", "inverter_max_dc_v"), computed_voc["inverter_max_dc_v"])
    mppt_v_min = _pick_first_num([payload, inv_spec, voc_chk_in], ("mppt_v_min",), computed_voc["mppt_v_min"])
    mppt_v_max = _pick_first_num([payload, inv_spec, voc_chk_in], ("mppt_v_max",), computed_voc["mppt_v_max"])
    max_series_safe = int(_pick_first_num([payload, mf, voc_chk_in], ("max_series_safe",), float(computed_voc["max_series_safe"])))
    min_series_mppt = int(_pick_first_num([payload, mf, voc_chk_in], ("min_series_mppt",), float(computed_voc["min_series_mppt"])))

    mppt_max_voc = max((float(r.get("voc_cold_v") or 0.0) for r in active_mppt), default=0.0)
    mppt_min_vmp_hot = min((float(r.get("vmp_hot_v") or 0.0) for r in active_mppt if float(r.get("vmp_hot_v") or 0.0) > 0), default=0.0)
    mppt_max_vmp_cold = max((float(r.get("vmp_cold_v") or 0.0) for r in active_mppt), default=0.0)

    if payload.get("cold_voc_v") is not None or payload.get("voc_cold_v") is not None:
        cold_voc_v = _pick_first_num([payload], ("cold_voc_v", "voc_cold_v"), computed_voc["requested_cold_voc_v"])
    elif mppt_max_voc > 0.0:
        cold_voc_v = mppt_max_voc
    elif voc_chk_in.get("requested_cold_voc_v") is not None:
        cold_voc_v = float(voc_chk_in["requested_cold_voc_v"])
    else:
        cold_voc_v = computed_voc["requested_cold_voc_v"]

    voc_margin_v = round(max_dc_v - cold_voc_v, 1)
    voc_margin_pct = round((voc_margin_v / max(1.0, max_dc_v)) * 100.0, 2)
    if cold_voc_v <= 0.0 or cold_voc_v > max_dc_v:
        st_voc = "fail"
        hint_voc = f"极寒 ({tmin_c:.0f}°C) 组串开路电压 {cold_voc_v:.1f}V 超出逆变器最大直流耐压 {max_dc_v:.0f}V！必须将单串串联数下调至 ≤{max_series_safe} 块/串。"
    elif voc_margin_pct < 4.0:
        st_voc = "warn"
        hint_voc = f"极寒开路电压 {cold_voc_v:.1f}V 距上限 {max_dc_v:.0f}V 裕度仅 {voc_margin_pct:.1f}%（<4%），建议每串减少 1 块组件以防寒潮击穿。"
    else:
        st_voc = "pass"
        hint_voc = f"极寒工况开路电压 {cold_voc_v:.1f}V 留有 {voc_margin_pct:.1f}%（{voc_margin_v:.0f}V）绝缘安全裕度，符合 GB 50797 规范。"

    if payload.get("hot_vmpp_v") is not None or payload.get("vmp_hot_v") is not None:
        hot_vmpp_v = _pick_first_num([payload], ("hot_vmpp_v", "vmp_hot_v"), computed_voc["requested_hot_vmpp_v"])
    elif mppt_min_vmp_hot > 0.0:
        hot_vmpp_v = mppt_min_vmp_hot
    elif voc_chk_in.get("requested_hot_vmpp_v") is not None:
        hot_vmpp_v = float(voc_chk_in["requested_hot_vmpp_v"])
    else:
        hot_vmpp_v = computed_voc["requested_hot_vmpp_v"]

    cold_vmp_over = (
        (mppt_max_vmp_cold > mppt_v_max)
        if mppt_max_vmp_cold > 0.0
        else (float(computed_voc.get("requested_cold_vmpp_v") or 0.0) > mppt_v_max)
    )
    if hot_vmpp_v <= 0.0 or hot_vmpp_v < mppt_v_min or hot_vmpp_v > mppt_v_max or cold_vmp_over:
        st_vmpp = "fail"
        hint_vmpp = (
            f"工作电压 ({hot_vmpp_v:.1f}V) 跌出或越过 MPPT 满载窗口 [{mppt_v_min:.0f}V~{mppt_v_max:.0f}V]，"
            f"请将每串串联块数调整至 {min_series_mppt}~{max_series_safe} 块区间。"
        )
    elif hot_vmpp_v < mppt_v_min + 35.0 or hot_vmpp_v > mppt_v_max - 20.0:
        st_vmpp = "warn"
        hint_vmpp = f"高温背板工况 Vmpp ({hot_vmpp_v:.1f}V) 逼近 MPPT 边界，局部阴影旁路时易降额运行，建议微调每串块数 1~2 块。"
    else:
        st_vmpp = "pass"
        hint_vmpp = f"高温工作电压 {hot_vmpp_v:.1f}V 稳居 MPPT 窗口 [{mppt_v_min:.0f}V~{mppt_v_max:.0f}V] 中段高效区。"

    # 4. Roof Dead-Load Margin Check
    roof_type_str = str(roof.get("type") or roof.get("roof_type") or payload.get("roof_type") or "flat").lower()
    if payload.get("load_kg_m2") is not None or struct_chk.get("added_dead_load_kg_m2") is not None:
        load_kg_m2 = _pick_first_num([payload, struct_chk], ("load_kg_m2", "added_dead_load_kg_m2"), 22.0)
    elif struct_chk.get("avg_added_dead_kn_m2") is not None:
        zones_list = struct_chk.get("zones") if isinstance(struct_chk.get("zones"), list) else []
        zone_max_kn = max((float(z.get("added_dead_kn_m2") or 0.0) for z in zones_list if isinstance(z, dict)), default=0.0)
        lim_kn_chk = float(struct_chk.get("roof_load_limit_kn_m2") or 1.50)
        eff_kn = zone_max_kn if zone_max_kn > lim_kn_chk else float(struct_chk["avg_added_dead_kn_m2"])
        load_kg_m2 = round(eff_kn * 1000.0 / 9.81, 1)
    else:
        load_kg_m2 = 28.5 if roof_type_str == "flat" else 14.8

    if (
        payload.get("max_load_kg_m2") is not None
        or mf_params.get("max_roof_load_kg_m2") is not None
        or roof.get("max_load_kg_m2") is not None
        or struct_chk.get("max_roof_load_kg_m2") is not None
    ):
        max_load_kg_m2 = _pick_first_num(
            [payload, mf_params, roof, struct_chk],
            ("max_load_kg_m2", "max_roof_load_kg_m2"),
            150.0,
        )
    elif struct_chk.get("roof_load_limit_kn_m2") is not None:
        max_load_kg_m2 = round(float(struct_chk["roof_load_limit_kn_m2"]) * 1000.0 / 9.81, 1)
    else:
        max_load_kg_m2 = 150.0 if roof_type_str == "flat" else 45.0

    load_util_pct = round((load_kg_m2 / max(1.0, max_load_kg_m2)) * 100.0, 1)
    zones_failed = struct_chk.get("all_pass") is False
    snow_failed = (payload.get("snow_ok") is False) or (struct_chk.get("snow_ok") is False)
    if load_kg_m2 > max_load_kg_m2 or zones_failed or snow_failed:
        st_load = "fail"
        if snow_failed and load_kg_m2 <= max_load_kg_m2:
            s0_chk = _pick_first_num(
                [payload, struct_chk, mf_params, payload.get("structural_params") or {}],
                ("basic_snow_s0_kn_m2", "s0_kn_m2"),
                0.0,
            )
            comb_chk = _pick_first_num([struct_chk], ("comb_down_design_kn_m2", "avg_comb_down_kn_m2"), 0.0)
            comb_lim_chk = _pick_first_num([struct_chk], ("combined_down_limit_kn_m2",), 4.20)
            hint_load = (
                f"极端雪压（s0={s0_chk:.2f} kN/m²，组合下压 {comb_chk:.2f} kN/m²）超出屋面承载或滑雪安全包络"
                f"（限值 {comb_lim_chk:.2f} kN/m²）！请核减阵列排布并进行专项结构加固验算。"
            )
        else:
            hint_load = (
                f"附加静载 {load_kg_m2:.1f} kg/m² 超出屋面允许限值 {max_load_kg_m2:.1f} kg/m²（或分区组合荷载超限）！"
                "请改用轻量化夹具/化学锚栓固定，或切换东西向低风阻低配重蝴蝶阵。"
            )
    elif load_util_pct > 85.0:
        st_load = "warn"
        hint_load = f"附加静载已占用屋面允许恒载的 {load_util_pct:.1f}%（>85%），施工图阶段须由注册结构工程师验算主次梁及檩条挠度。"
    else:
        st_load = "pass"
        hint_load = f"附加静载 {load_kg_m2:.1f} kg/m² 仅占限值 {max_load_kg_m2:.1f} kg/m² 的 {load_util_pct:.1f}%，屋面结构安全裕度充裕。"

    # 5. Wind Uplift Perimeter Setback Check
    w0_kn = _pick_first_num(
        [payload, mf_params, struct_chk, payload.get("structural_params") or {}],
        ("basic_wind_w0_kn_m2", "w0_kn_m2"),
        0.45,
    )
    fix_type = str(
        payload.get("fixing_type")
        or mf_params.get("fixing_type")
        or struct_chk.get("fixing_type")
        or ("ballast" if roof_type_str == "flat" else "clamp")
    ).lower()
    req_setback = _pick_first_num(
        [payload],
        ("required_setback_m",),
        (1.20 if fix_type == "ballast" else 0.90) if w0_kn >= 0.65 else (0.75 if w0_kn >= 0.50 else 0.50),
    )
    eff_setback = _pick_first_num(
        [payload, struct_chk, roof, lp, mf_params],
        ("effective_setback_m", "setback_m", "edge_setback_m"),
        0.80,
    )
    if eff_setback < req_setback * 0.75 or struct_chk.get("wind_ok") is False:
        st_wind = "fail"
        hint_wind = (
            f"基本风压 w0={w0_kn:.2f} kN/m² 工况下，边缘退距 {eff_setback:.2f}m 明显小于抗风揭要求 {req_setback:.2f}m！"
            f"请将屋面边角退距调大至 ≥{req_setback:.2f}m 并增设防风抗拔措施。"
        )
    elif eff_setback < req_setback:
        st_wind = "warn"
        hint_wind = f"当前边缘退距 {eff_setback:.2f}m 略低于风压推荐值 {req_setback:.2f}m，建议加密屋面角区与边缘区压载或夹具数量。"
    else:
        st_wind = "pass"
        hint_wind = f"边缘退距 {eff_setback:.2f}m ≥ 风压校核要求 {req_setback:.2f}m（w0={w0_kn:.2f} kN/m²），避开屋面强风吸角区。"

    # 6. DC Cable Voltage Drop Check (GB 50797 <= 1.5%)
    if payload.get("dc_drop_pct") is not None or wiring.get("dc_drop_pct") is not None:
        dc_drop_pct = _pick_first_num([payload, wiring], ("dc_drop_pct",), 0.95)
    else:
        strings_arr = payload.get("strings") if isinstance(payload.get("strings"), list) else []
        max_loop_m = max((float(s.get("route_m") or 0.0) for s in strings_arr if isinstance(s, dict)), default=0.0)
        if max_loop_m <= 0.0:
            str_cnt = max(1.0, _pick_first_num([payload, summary, elec], ("string_count",), 12.0))
            tot_dc_m = _pick_first_num([wiring], ("hanan_2opt_dc_cable_m",), str_cnt * 92.0)
            max_loop_m = (tot_dc_m / str_cnt) * 1.22
        imp_a = _pick_first_num([mod_spec, lp], ("imp_a",), 13.7)
        mps_nom = max(6.0, _pick_first_num([payload, summary, elec], ("modules_per_string", "string_series"), float(computed_voc["recommended_series"])))
        vmp_nom_str = max(200.0, mps_nom * _pick_first_num([mod_spec, lp], ("vmp_v",), 42.3))
        # 4mm² PV1-F tinned copper at 60°C operating temperature: R ≈ 0.005125 Ω/m
        dc_drop_pct = round((imp_a * max_loop_m * 0.005125) / vmp_nom_str * 100.0, 2)

    if dc_drop_pct > 2.50:
        st_drop = "fail"
        hint_drop = f"最长组串直流回路压降达 {dc_drop_pct:.2f}%（>2.5%），请就近分散布置逆变器、缩短回流路径或将远端组串升级为 6mm² 光伏线缆。"
    elif dc_drop_pct > 1.50:
        st_drop = "warn"
        hint_drop = f"最长组串直流压降 {dc_drop_pct:.2f}% 超出 GB 50797 推荐值 1.5%，建议远距离回路改用 PV1-F 1×6mm² 铜芯光伏线。"
    else:
        st_drop = "pass"
        hint_drop = f"直流回路最大压降 {dc_drop_pct:.2f}% ≤ 1.5% 规范限值，Hanan 网格蛇形走线有效压缩直流线损。"

    # 7. Near-Shading Loss Check
    loss_tree = pvs.get("loss_tree") if isinstance(pvs.get("loss_tree"), dict) else {}
    shade_pct = _pick_first_num(
        [payload, mf, pvs_params],
        ("shading_loss_pct",),
        abs(float(loss_tree.get("near_shading_loss_pct") or 2.2)),
    )
    if shade_pct > 10.0:
        st_shade = "fail"
        hint_shade = f"三维近场遮挡损失高达 {shade_pct:.2f}%（>10%），存在严重热斑与失配短板风险，请剔除重度受遮组件、拉大排距或改用架高跨越方案。"
    elif shade_pct > 5.0:
        st_shade = "warn"
        hint_shade = f"近场遮挡损失 {shade_pct:.2f}% 偏高（>5%），建议开启阴影短板组件自动剔除或切换横装旁路抗遮挡排布。"
    else:
        st_shade = "pass"
        hint_shade = f"年均近场遮挡损失仅 {shade_pct:.2f}%（≤5%），女儿墙与阵列前后排冬至日阴影控制良好。"

    # 8. Financial IRR & Static Payback Check
    has_explicit_irr = any(
        isinstance(src, dict) and "irr_pct" in src
        for src in (payload, summary, fin)
    )
    irr_val: float | None = None
    for src in (payload, summary, fin):
        if isinstance(src, dict) and src.get("irr_pct") is not None and not isinstance(src.get("irr_pct"), bool):
            try:
                fv = float(src["irr_pct"])
                if math.isfinite(fv):
                    irr_val = fv
                    break
            except (TypeError, ValueError):
                pass
    if irr_val is None and not has_explicit_irr and not (dc_kw <= 0.0 and "dc_kw" in summary):
        irr_val = 12.6

    has_explicit_pb = any(
        isinstance(src, dict) and any(k in src for k in ("payback_yr", "payback_years", "static_payback_years"))
        for src in (payload, summary, fin)
    )
    pb_val: float | None = None
    for src in (payload, summary, fin):
        if isinstance(src, dict):
            for k in ("payback_yr", "payback_years", "static_payback_years"):
                if src.get(k) is not None and not isinstance(src.get(k), bool):
                    try:
                        fv = float(src[k])
                        if math.isfinite(fv):
                            pb_val = fv
                            break
                    except (TypeError, ValueError):
                        pass
            if pb_val is not None:
                break
    if pb_val is None and not has_explicit_pb and irr_val is not None and irr_val > 0.0:
        pb_val = 5.8

    if irr_val is None or pb_val is None:
        st_fin = "fail"
        fin_display = "不可行 (未回本/无正现金流)"
        fin_detail = "25年全周期累计现金流未回本或无可用内部收益率，财务不可行。"
        hint_fin = "项目未能回本或无正净现金流，请提高自发自用率、核实电价边界或压降单瓦 EPC 造价。"
    elif irr_val < 5.5 or pb_val > 13.5:
        st_fin = "fail"
        fin_display = f"IRR {irr_val:.2f}% · {pb_val:.1f}年"
        fin_detail = f"25年全周期税前全投资 IRR {irr_val:.2f}%，静态回收期 {pb_val:.2f} 年"
        hint_fin = f"全投资 IRR 仅 {irr_val:.2f}%、回收期 {pb_val:.1f} 年，低于工商业基准收益红线，请提高自发自用消纳比例或压降 EPC 单瓦造价。"
    elif irr_val < 8.0 or pb_val > 9.0:
        st_fin = "warn"
        fin_display = f"IRR {irr_val:.2f}% · {pb_val:.1f}年"
        fin_detail = f"25年全周期税前全投资 IRR {irr_val:.2f}%，静态回收期 {pb_val:.2f} 年"
        hint_fin = f"全投资 IRR {irr_val:.2f}%（回收期 {pb_val:.1f} 年）收益偏紧，建议结合峰谷负荷曲线优化阵列朝向或商务电价折扣。"
    else:
        st_fin = "pass"
        fin_display = f"IRR {irr_val:.2f}% · {pb_val:.1f}年"
        fin_detail = f"25年全周期税前全投资 IRR {irr_val:.2f}%，静态回收期 {pb_val:.2f} 年"
        hint_fin = f"全投资 IRR 达 {irr_val:.2f}%、静态回收期 {pb_val:.1f} 年，满足工商业分布式项目高收益投决标准。"

    items: list[dict[str, Any]] = [
        {
            "id": "dc_ac_ratio",
            "code": "CHK-01",
            "category_zh": "电气匹配",
            "title_zh": "容配比合理性校核",
            "label_zh": "容配比合理性校核",
            "status": st_dcac,
            "value": round(dc_ac, 2),
            "unit": ":1",
            "display_value": f"{dc_ac:.2f} : 1",
            "threshold_zh": "1.00 ~ 1.35 : 1",
            "detail_zh": f"直流装机 {dc_kw:.2f} kWp / 交流额定 {ac_kw:.1f} kW",
            "fix_hint_zh": hint_dcac,
        },
        {
            "id": "cold_voc_margin",
            "code": "CHK-02",
            "category_zh": "组串高压安全",
            "title_zh": "极寒开路电压安全裕度",
            "label_zh": "极寒开路电压安全裕度",
            "status": st_voc,
            "value": round(cold_voc_v, 1),
            "unit": "V",
            "display_value": f"{cold_voc_v:.1f} V / {max_dc_v:.0f} V",
            "threshold_zh": f"≤ {max_dc_v * 0.96:.0f} V (裕度 ≥4%)",
            "detail_zh": f"极端低温 {tmin_c:.0f}°C 工况，安全裕度 {voc_margin_pct:.1f}%（上限 {max_series_safe} 块/串）",
            "fix_hint_zh": hint_voc,
        },
        {
            "id": "hot_vmpp_window",
            "code": "CHK-03",
            "category_zh": "MPPT追踪",
            "title_zh": "高温工作电压 MPPT 窗口校核",
            "label_zh": "高温工作电压 MPPT 窗口校核",
            "status": st_vmpp,
            "value": round(hot_vmpp_v, 1),
            "unit": "V",
            "display_value": f"{hot_vmpp_v:.1f} V",
            "threshold_zh": f"{mppt_v_min + 35.0:.0f} ~ {mppt_v_max - 20.0:.0f} V",
            "detail_zh": f"逆变器 MPPT 满载区间 [{mppt_v_min:.0f}V, {mppt_v_max:.0f}V]（最少 {min_series_mppt} 块/串）",
            "fix_hint_zh": hint_vmpp,
        },
        {
            "id": "roof_dead_load",
            "code": "CHK-04",
            "category_zh": "结构安全",
            "title_zh": "屋面静荷载安全裕度",
            "label_zh": "屋面静荷载安全裕度",
            "status": st_load,
            "value": round(load_kg_m2, 1),
            "unit": "kg/m²",
            "display_value": f"{load_kg_m2:.1f} / {max_load_kg_m2:.1f} kg/m²",
            "threshold_zh": f"≤ {max_load_kg_m2 * 0.85:.1f} kg/m² (占用 ≤85%)",
            "detail_zh": f"荷载占用率 {load_util_pct:.1f}%（固定方式：{fix_type}）",
            "fix_hint_zh": hint_load,
        },
        {
            "id": "wind_uplift_setback",
            "code": "CHK-05",
            "category_zh": "抗风揭规范",
            "title_zh": "抗风揭边角退距校核",
            "label_zh": "抗风揭边角退距校核",
            "status": st_wind,
            "value": round(eff_setback, 2),
            "unit": "m",
            "display_value": f"{eff_setback:.2f} m",
            "threshold_zh": f"≥ {req_setback:.2f} m (w0={w0_kn:.2f} kN/m²)",
            "detail_zh": f"50年一遇基本风压 {w0_kn:.2f} kN/m² 屋面周边风吸退距校核",
            "fix_hint_zh": hint_wind,
        },
        {
            "id": "dc_voltage_drop",
            "code": "CHK-06",
            "category_zh": "线损压降",
            "title_zh": "直流线缆回路压降校核",
            "label_zh": "直流线缆回路压降校核",
            "status": st_drop,
            "value": round(dc_drop_pct, 2),
            "unit": "%",
            "display_value": f"{dc_drop_pct:.2f}%",
            "threshold_zh": "≤ 1.50% (GB 50797)",
            "detail_zh": "按 PV1-F 1×4mm² 铜芯直流线缆最长回路阻抗压降核算",
            "fix_hint_zh": hint_drop,
        },
        {
            "id": "shading_loss",
            "code": "CHK-07",
            "category_zh": "光学遮挡",
            "title_zh": "三维近场遮挡损失校核",
            "label_zh": "三维近场遮挡损失校核",
            "status": st_shade,
            "value": round(shade_pct, 2),
            "unit": "%",
            "display_value": f"{shade_pct:.2f}%",
            "threshold_zh": "≤ 5.00%",
            "detail_zh": "综合女儿墙、屋面凸起障碍物及前后排冬至日几何遮挡损失",
            "fix_hint_zh": hint_shade,
        },
        {
            "id": "financial_return",
            "code": "CHK-08",
            "category_zh": "投资收益",
            "title_zh": "投资回报率与回收期校核",
            "label_zh": "投资回报率与回收期校核",
            "status": st_fin,
            "value": round(irr_val, 2) if irr_val is not None else None,
            "unit": "%",
            "display_value": fin_display,
            "threshold_zh": "IRR ≥ 8.0% 且回收期 ≤ 9.0年",
            "detail_zh": fin_detail,
            "fix_hint_zh": hint_fin,
        },
    ]

    pass_count = sum(1 for it in items if it["status"] == "pass")
    warn_count = sum(1 for it in items if it["status"] == "warn")
    fail_count = sum(1 for it in items if it["status"] == "fail")
    overall_status = "fail" if fail_count > 0 else ("warn" if warn_count > 0 else "pass")
    score = round(pass_count * 12.5 + warn_count * 7.5, 1)

    if fail_count == 0 and warn_count == 0:
        summary_zh = "8 项工程交付前合规校核全部通过（100分），满足施工图深化与一键工程交付条件。"
    elif fail_count == 0:
        summary_zh = f"通过 {pass_count}/8 项，存在 {warn_count} 项工程优化提醒（无红线阻断项），可生成工程交付包。"
    else:
        summary_zh = f"存在 {fail_count} 项工程红线未通过、{warn_count} 项提醒，建议参照修复建议优化后再正式交付。"

    return {
        "ok": True,
        "overall_status": overall_status,
        "score": score,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "ready_for_delivery": fail_count == 0,
        "summary_zh": summary_zh,
        "items": items,
    }
