"""Four explicitly documented photovoltaic yield models for a 1 kWp reference."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import itertools
import json
import math
from pathlib import Path
import time

import numpy as np
import pandas as pd
import pvlib
import requests

from .config import DATA_DIR, ROOT
from .native_runtime import prepare_pysam
from .weather import load_nasa_hourly, load_pvgis_tmy


CACHE_DIR = DATA_DIR / "cache" / "yields"
DEMO_DIR = DATA_DIR / "demo" / "yields"
PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
LOSS_PERCENT = 14.0
DC_AC_RATIO = 1.2
INVERTER_EFFICIENCY = 0.96
GAMMA_PDC = -0.0037
ROOF_NOCT_C = 49.0
STANDARD_EFFICIENCY = 0.19
SSC_SOURCE_CODE = "https://raw.githubusercontent.com/NatLabRockies/ssc/2025.4.16.r2.ssc.306/ssc/cmod_pvwattsv8.cpp"


class MissingPVGISResult(ValueError):
    """No matching PVGIS record exists; distinguish absence from corrupt data."""


def _validate_loss(loss_percent: float) -> None:
    if not math.isfinite(loss_percent) or not 0 <= loss_percent < 100:
        raise ValueError("System loss must be finite and between 0 and 100 percent (exclusive).")


def _validate_geometry(lat: float, lon: float, tilt: float, azimuth: float) -> None:
    if not all(math.isfinite(value) for value in (lat, lon, tilt, azimuth)):
        raise ValueError("Site and orientation values must be finite.")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Site coordinates are outside their physical ranges.")
    if not 0 <= tilt <= 90 or not 0 <= azimuth <= 360:
        raise ValueError("Tilt must be 0..90 and azimuth 0..360 degrees.")


def _weather_data(weather: pd.DataFrame, *, full_year: bool = False) -> pd.DataFrame:
    columns = ["ghi", "dni", "dhi", "temp_air", "wind_speed"]
    if not isinstance(weather.index, pd.DatetimeIndex) or weather.index.tz is None:
        raise ValueError("Yield weather must use timezone-aware timestamps.")
    if any(column not in weather for column in columns):
        raise ValueError("Yield weather must contain the five standardized weather columns.")
    df = weather[columns].copy()
    df.index = df.index.tz_convert("UTC")
    if not len(df) or df.index.has_duplicates or not df.index.is_monotonic_increasing:
        raise ValueError("Yield weather must be nonempty, sorted, and have unique timestamps.")
    if not np.isfinite(df.to_numpy(dtype=float)).all():
        raise ValueError("Yield weather contains missing or nonfinite values.")
    if (df[["ghi", "dni", "dhi", "wind_speed"]] < 0).any().any():
        raise ValueError("Irradiance and wind speed must be nonnegative.")
    if len(df) > 1 and not (df.index.to_series().diff().iloc[1:] == pd.Timedelta(hours=1)).all():
        raise ValueError("Yield weather must have continuous hourly timestamps.")
    if full_year:
        year = int(df.index[0].year)
        expected = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq="h", tz="UTC", inclusive="left")
        if not df.index.equals(expected):
            raise ValueError("PySAM requires a complete UTC calendar year of hourly weather.")
    df.attrs["hour_midpoint_offset_minutes"] = weather.attrs.get("hour_midpoint_offset_minutes", 30)
    return df


def _poa_and_effective(weather: pd.DataFrame, lat: float, lon: float, tilt: float, azimuth: float):
    from .solar import poa_irradiance, sun_position
    offset = float(weather.attrs["hour_midpoint_offset_minutes"])
    midpoint = weather.index + pd.Timedelta(minutes=offset)
    sun = sun_position(midpoint, lat, lon, temp_c=weather.temp_air.to_numpy())
    poa = poa_irradiance(weather, sun, tilt, azimuth, albedo=0.2, model="perez")
    if not np.isfinite(poa.to_numpy(dtype=float)).all():
        raise ValueError("POA transposition produced nonfinite values.")
    aoi = pvlib.irradiance.aoi(tilt, azimuth, sun.apparent_zenith.to_numpy(), sun.azimuth.to_numpy())
    # The documented physical glass IAM and Marion hemispherical integration
    # are standard pvlib models, not coefficients fitted to the crosscheck.
    # PVWatts v8 uses its own antireflective-cover optical model instead.
    beam_iam = pvlib.iam.physical(aoi)
    diffuse_iam = pvlib.iam.marion_diffuse("physical", tilt)
    effective = (poa.poa_direct.to_numpy() * beam_iam
                 + poa.poa_sky_diffuse.to_numpy() * diffuse_iam["sky"]
                 + poa.poa_ground_diffuse.to_numpy() * diffuse_iam["ground"])
    if not np.isfinite(effective).all():
        raise ValueError("Optical irradiance model produced nonfinite values.")
    return poa, pd.Series(np.maximum(effective, 0), index=weather.index)


def _summary(ac_w, index: pd.DatetimeIndex, metadata: dict) -> dict:
    # Sandia and SSC can report negative nighttime tare consumption. These
    # results represent generated AC energy, so consumption is clipped at zero.
    values = np.maximum(np.asarray(ac_w, dtype=float), 0)
    if not np.isfinite(values).all():
        raise ValueError("The generation model produced nonfinite AC power.")
    energy = pd.Series(values / 1000, index=index.tz_convert("UTC"))
    monthly = energy.groupby(energy.index.month).sum().reindex(range(1, 13), fill_value=0)
    annual = float(monthly.sum())
    return {"monthly_kwh": [float(value) for value in monthly], "annual_kwh": annual,
            "specific_yield_kwh_kwp": annual, "metadata": dict(metadata, output_dc_capacity_kw=1.0,
            aggregation_timezone="UTC", negative_night_tare="clipped to zero for generated energy")}


def simulate_pvlib_simple(weather: pd.DataFrame, lat: float, lon: float, *, tilt=25, azimuth=180,
                          loss_percent=LOSS_PERCENT) -> dict:
    _validate_geometry(lat, lon, tilt, azimuth)
    _validate_loss(loss_percent)
    df = _weather_data(weather)
    poa, effective = _poa_and_effective(df, lat, lon, tilt, azimuth)
    # SAM's documented v8 standard module has 19% efficiency and -0.37%/C:
    # https://samrepo.nlr.gov/help/pvwatts_system_design.html
    # Roof-mounted PVWatts v8 uses SAM NOCT with 49C, not legacy Fuentes:
    # https://raw.githubusercontent.com/NatLabRockies/ssc/2025.4.16.r2.ssc.306/ssc/cmod_pvwattsv8.cpp
    # SSC supplies its proxy module's optical/spectral and efficiency inputs;
    # this simplified NOCT call uses the nominal 19% efficiency and POA ratio 1.
    cell = pvlib.temperature.noct_sam(poa.poa_global, df.temp_air, df.wind_speed,
                                     noct=ROOF_NOCT_C, module_efficiency=STANDARD_EFFICIENCY)
    dc = pvlib.pvsystem.pvwatts_dc(effective, cell, pdc0=1000, gamma_pdc=GAMMA_PDC)
    dc = dc * (1 - loss_percent / 100)  # One system loss, before conversion.
    # pvwatts inverter pdc0 is its DC INPUT rating, not the array's 1000 W:
    # Pac0=1000/1.2 W; Pdc0=Pac0/0.96=868.0555556 W, matching SSC's limits.
    inverter_pdc0 = 1000 / DC_AC_RATIO / INVERTER_EFFICIENCY
    ac = pvlib.inverter.pvwatts(dc, inverter_pdc0, eta_inv_nom=INVERTER_EFFICIENCY)
    return _summary(ac, df.index, {"model": "pvlib PVWatts DC + SAM NOCT + PVWatts inverter",
                    "gamma_pdc": GAMMA_PDC, "noct_c": ROOF_NOCT_C, "module_efficiency": STANDARD_EFFICIENCY,
                    "dc_ac_ratio": DC_AC_RATIO, "inverter_efficiency": INVERTER_EFFICIENCY,
                    "inverter_pdc0_w": inverter_pdc0, "loss_percent": loss_percent,
                    "iam": "physical glass; Marion diffuse integration", "transposition": "perez",
                    "hour_midpoint_offset_minutes": df.attrs["hour_midpoint_offset_minutes"]})


def simulate_pvlib_detailed(weather: pd.DataFrame, lat: float, lon: float, *, tilt=25, azimuth=180,
                           loss_percent=LOSS_PERCENT, offline=False, equipment=None) -> dict:
    _validate_geometry(lat, lon, tilt, azimuth)
    _validate_loss(loss_percent)
    if equipment is None:
        from .catalog import load_cec_equipment
        equipment = load_cec_equipment(offline=offline)
    module, inverter, catalog_meta = equipment
    series, parallel = int(catalog_meta["series"]), int(catalog_meta["parallel"])
    capacity = float(module["STC"]) * series * parallel / 1000
    if not math.isclose(capacity, float(catalog_meta["dc_capacity_kw"]), rel_tol=1e-9):
        raise ValueError("Catalog array DC capacity does not match its unmodified module STC power.")
    df = _weather_data(weather)
    poa, effective = _poa_and_effective(df, lat, lon, tilt, azimuth)
    # T_NOCT remains the selected catalog's 45.7C; it is not changed to force
    # agreement with the roof-mounted generic PVWatts module's 49C NOCT.
    efficiency = float(module["STC"]) / (1000 * float(module["A_c"]))
    cell = pvlib.temperature.noct_sam(poa.poa_global, df.temp_air, df.wind_speed,
                                     noct=float(module["T_NOCT"]), module_efficiency=efficiency)
    names = ("alpha_sc", "a_ref", "I_L_ref", "I_o_ref", "R_sh_ref", "R_s", "Adjust")
    # The illuminated module uses the CEC solver. At zero effective irradiance
    # its generated power is exactly zero; avoid a degenerate dark IV optimizer.
    illuminated = effective > 0
    array_vmp = pd.Series(0.0, index=df.index)
    array_dc = pd.Series(0.0, index=df.index)
    if illuminated.any():
        parameters = pvlib.pvsystem.calcparams_cec(effective[illuminated], cell[illuminated],
                     **{name: float(module[name]) for name in names})
        mpp = pvlib.pvsystem.singlediode(*parameters, method="lambertw")
        array_vmp.loc[illuminated] = mpp["v_mp"] * series
        array_dc.loc[illuminated] = mpp["p_mp"] * series * parallel * (1 - loss_percent / 100)
    ac = pvlib.inverter.sandia(array_vmp, array_dc, inverter)
    # Simulate the real 132-module array and real inverter first. Normalize AC
    # energy to 1 kWp only afterwards; neither equipment parameter is scaled.
    meta = {"model": "CEC single diode + SAM NOCT + Sandia inverter", "catalog": catalog_meta,
            "array_dc_capacity_kw": capacity, "array_ac_rating_kw": float(inverter["Paco"]) / 1000,
            "array_annual_generated_kwh": float(np.maximum(np.asarray(ac), 0).sum() / 1000),
            "normalization_factor": 1 / capacity, "loss_percent": loss_percent,
            "noct_c": float(module["T_NOCT"]), "module_efficiency": efficiency,
            "iam": "physical glass; Marion diffuse integration", "transposition": "perez",
            "hour_midpoint_offset_minutes": df.attrs["hour_midpoint_offset_minutes"]}
    result = _summary(np.asarray(ac) / capacity, df.index, meta)
    result["hourly"] = dict(utc=[stamp.isoformat() for stamp in df.index.tz_convert("UTC")],
                            kwh=[float(value) for value in np.maximum(np.asarray(ac), 0) / capacity / 1000])
    return result


def _pysam_module():
    prepare_pysam()
    return importlib.import_module("PySAM.Pvwattsv8")


def simulate_pysam(weather: pd.DataFrame, lat: float, lon: float, *, tilt=25, azimuth=180,
                   loss_percent=LOSS_PERCENT) -> dict:
    _validate_geometry(lat, lon, tilt, azimuth)
    _validate_loss(loss_percent)
    df = _weather_data(weather, full_year=True)
    offset = float(df.attrs["hour_midpoint_offset_minutes"])
    if offset != 30:
        raise ValueError("The PVWatts hourly crosscheck requires a 30-minute interval midpoint.")
    midpoint = df.index + pd.Timedelta(minutes=offset)
    model = _pysam_module().default("PVWattsNone")
    model.SolarResource.solar_resource_data = {
        "lat": lat, "lon": lon, "tz": 0, "elev": 0,
        "year": midpoint.year.tolist(), "month": midpoint.month.tolist(), "day": midpoint.day.tolist(),
        "hour": midpoint.hour.tolist(), "minute": midpoint.minute.tolist(),
        "gh": df.ghi.tolist(), "dn": df.dni.tolist(), "df": df.dhi.tolist(),
        "tdry": df.temp_air.tolist(), "wspd": df.wind_speed.tolist(),
    }
    model.SolarResource.albedo = [0.2] * 12
    # Identical 1 kWp, standard module, fixed roof, 1.2 ratio, 96% inverter
    # efficiency, and one system loss. No extra snow, soiling, shading or tare loss.
    model.SystemDesign.assign({"system_capacity": 1, "module_type": 0, "array_type": 1,
        "tilt": tilt, "azimuth": azimuth, "dc_ac_ratio": DC_AC_RATIO, "inv_eff": 100 * INVERTER_EFFICIENCY,
        "losses": loss_percent, "bifaciality": 0, "en_snowloss": 0, "soiling": [0] * 12,
        "xfmr_ll": 0, "xfmr_nll": 0})
    model.Shading.assign({"shading_en_azal": 0, "shading_en_diff": 0, "shading_en_mxh": 0,
                          "shading_en_timestep": 0})
    model.AdjustmentFactors.adjust_constant = 0
    model.Lifetime.system_use_lifetime_output = 0
    model.execute()
    return _summary(model.Outputs.ac, df.index, {"model": "SSC PySAM PVWatts v8", "system_capacity_kw": 1,
        "module_type": 0, "array_type": 1, "dc_ac_ratio": DC_AC_RATIO, "inverter_efficiency": INVERTER_EFFICIENCY,
        "loss_percent": loss_percent, "timezone_hours": 0, "minute": 30,
        "self_shading": False, "temperature_model": "SAM NOCT (49C fixed roof)",
        "dc_model": "SSC CEC proxy module (Canadian Solar CS1H-320MS)",
        "inverter_model": "SSC generic Sandia inverter", "ssc_source_code": SSC_SOURCE_CODE,
        "hour_midpoint_offset_minutes": offset})


def _pvgis_key(lat: float, lon: float, tilt: float, azimuth: float, loss_percent=LOSS_PERCENT) -> str:
    key = f"pvgis_{lat:.4f}_{lon:.4f}_tilt{tilt:.4f}_azimuth{azimuth:.4f}"
    return key if loss_percent == LOSS_PERCENT else key + f"_loss{float(loss_percent)!r}"


def _parse_pvgis_result(payload: dict, metadata: dict) -> dict:
    try:
        if "loss_percent" in metadata and not math.isclose(
                float(payload["inputs"]["pv_module"]["system_loss"]), metadata["loss_percent"], abs_tol=1e-10):
            raise ValueError("PVGIS response system loss does not match its request metadata.")
        rows = payload["outputs"]["monthly"]["fixed"]
        months = {int(row["month"]): float(row["E_m"]) for row in rows}
        if set(months) != set(range(1, 13)) or len(rows) != 12:
            raise ValueError("PVGIS response does not contain twelve unique months.")
        annual = float(payload["outputs"]["totals"]["fixed"]["E_y"])
        values = [months[month] for month in range(1, 13)]
        if not all(math.isfinite(value) and value >= 0 for value in [annual, *values]):
            raise ValueError("PVGIS result contains invalid energy values.")
        return {"monthly_kwh": values, "annual_kwh": annual, "specific_yield_kwh_kwp": annual,
                "metadata": dict(metadata, model="PVGIS 5.3 PVcalc; independent ERA5 weather",
                pvgis_inputs=payload.get("inputs", {}), pvgis_totals=payload["outputs"]["totals"]["fixed"])}
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Malformed PVGIS calculation response.") from error


def _write_pvgis_record(directory: Path, key: str, payload: dict, metadata: dict) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    contents = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    metadata = dict(metadata, data_file=key + ".json", data_file_sha256=hashlib.sha256(contents).hexdigest())
    # Validate before publishing cache files. These contain a real API response.
    _parse_pvgis_result(payload, metadata)
    (directory / (key + ".json")).write_bytes(contents)
    (directory / (key + ".meta.json")).write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8", newline="\n")
    return metadata


def _read_pvgis_record(directory: Path, key: str, used: str) -> dict | None:
    data, sidecar = directory / (key + ".json"), directory / (key + ".meta.json")
    if not data.exists() and not sidecar.exists():
        return None
    try:
        contents = data.read_bytes()
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        if hashlib.sha256(contents).hexdigest() != meta["data_file_sha256"]:
            raise ValueError("PVGIS cached response checksum mismatch.")
        if _pvgis_key(meta["latitude"], meta["longitude"], meta["tilt"], meta["azimuth"], meta["loss_percent"]) != key:
            raise ValueError("PVGIS record does not match the requested site/orientation/loss.")
        return _parse_pvgis_result(json.loads(contents), dict(meta, used=used))
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise ValueError("PVGIS cached calculation is invalid: " + str(error)) from error


def _download_pvgis(request_url: str) -> dict:
    response = requests.get(request_url, timeout=(3, 15))
    response.raise_for_status()
    return response.json()


def load_pvgis_result(lat: float, lon: float, *, tilt=25, azimuth=180, loss=LOSS_PERCENT,
                      offline=False) -> dict:
    _validate_geometry(lat, lon, tilt, azimuth)
    _validate_loss(loss)
    key = _pvgis_key(lat, lon, tilt, azimuth, loss)
    errors, invalid_record = [], False
    try:
        cached = _read_pvgis_record(CACHE_DIR, key, "cache")
        if cached is not None:
            return cached
    except ValueError as error:
        errors.append(str(error))
        invalid_record = True
    if not offline:
        parameters = {"lat": lat, "lon": lon, "peakpower": 1, "loss": loss,
                      "angle": tilt, "aspect": azimuth - 180, "raddatabase": "PVGIS-ERA5", "outputformat": "json"}
        request_url = requests.Request("GET", PVGIS_URL, params=parameters).prepare().url
        try:
            payload = _download_pvgis(request_url)
            meta = {"source": "pvgis_pvcalc", "latitude": lat, "longitude": lon, "tilt": tilt,
                    "azimuth": azimuth, "peakpower_kw": 1, "loss_percent": loss,
                    "request_url": request_url, "download_time": datetime.now(timezone.utc).isoformat(), "used": "download"}
            meta = _write_pvgis_record(CACHE_DIR, key, payload, meta)
            return _parse_pvgis_result(payload, meta)
        except (requests.RequestException, ValueError, OSError) as error:
            errors.append(type(error).__name__)
    try:
        demo = _read_pvgis_record(DEMO_DIR, key, "demo")
        if demo is not None:
            return demo
    except ValueError as error:
        errors.append(str(error))
        invalid_record = True
    error_type = ValueError if invalid_record else MissingPVGISResult
    raise error_type(f"No matching PVGIS result for {key}; no usable exact-site/orientation cache or demo. " + "; ".join(errors))


def simulate_design_yields(lat: float, lon: float, *, tilt: float, azimuth: float,
                           loss_percent: float, offline=False, module_id=None) -> dict:
    """Five 1 kWp estimates with controlled model/weather comparisons and one loss."""
    from .catalog import load_cec_equipment
    _validate_geometry(lat, lon, tilt, azimuth)
    _validate_loss(loss_percent)
    nasa, nasa_meta = load_nasa_hourly(lat, lon, 2023, offline=offline)
    tmy, tmy_meta = load_pvgis_tmy(lat, lon, offline=offline)
    equipment = load_cec_equipment(offline=offline, module_id=module_id)
    params = {"tilt": tilt, "azimuth": azimuth, "loss_percent": loss_percent}
    results = {"a": simulate_pvlib_simple(nasa, lat, lon, **params),
               "b": simulate_pvlib_detailed(nasa, lat, lon, equipment=equipment, **params),
               "c": simulate_pysam(nasa, lat, lon, **params),
               "b_tmy": simulate_pvlib_detailed(tmy, lat, lon, equipment=equipment, **params)}
    omitted = {}
    try:
        results["d"] = load_pvgis_result(lat, lon, tilt=tilt, azimuth=azimuth, loss=loss_percent, offline=offline)
    except MissingPVGISResult as error:
        omitted["d"] = "缺PVGIS：" + str(error)
    for key in results:
        results[key]["metadata"]["weather_source"] = "PVGIS ERA5 TMY" if key == "b_tmy" else (
            "PVGIS ERA5 multiyear PVcalc" if key == "d" else "NASA POWER 2023")
    return {"site": dict(latitude=lat, longitude=lon, tilt=tilt, azimuth=azimuth),
            "loss_percent": loss_percent, "weather_metadata": {"nasa": nasa_meta, "pvgis_tmy": tmy_meta},
            "results": results, "omitted": omitted, "comparison_metadata": {
                "weather_difference": "b versus b_tmy: same CEC/Sandia model, NASA 2023 versus ERA5 TMY",
                "model_difference": "a/b/c: same NASA 2023; b_tmy/d: ERA5 weather products also differ",
                "inverter_approximation": "b and b_tmy use the reference array inverter efficiency curve"}}


def _plot_monthly(results: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    path.parent.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(figsize=(10, 5))
    names = {"a": "pvlib simplified", "b": "pvlib CEC detailed", "c": "PySAM PVWatts v8", "d": "PVGIS ERA5"}
    for label, result in results.items():
        axes.plot(range(1, 13), result["monthly_kwh"], marker="o", label=names[label])
    axes.set(xlabel="Month", ylabel="Generated energy (kWh per 1 kWp)", xticks=range(1, 13))
    axes.grid(alpha=0.25)
    axes.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def crosscheck(lat: float, lon: float, year: int, *, tilt=25, azimuth=180, offline=False, figure_path=None) -> dict:
    from .catalog import load_cec_equipment
    _validate_geometry(lat, lon, tilt, azimuth)
    weather, weather_meta = load_nasa_hourly(lat, lon, year, offline=offline)
    equipment = load_cec_equipment(offline=offline)
    # Fetch first and warm native imports before timing. The measured run below
    # includes all three local chains and reading the recorded PVGIS result.
    acquired_pvgis = load_pvgis_result(lat, lon, tilt=tilt, azimuth=azimuth, offline=offline)
    importlib.import_module("guangzhu.solar")
    _pysam_module()
    started = time.perf_counter()
    results = {
        "a": simulate_pvlib_simple(weather, lat, lon, tilt=tilt, azimuth=azimuth),
        "b": simulate_pvlib_detailed(weather, lat, lon, tilt=tilt, azimuth=azimuth, equipment=equipment),
        "c": simulate_pysam(weather, lat, lon, tilt=tilt, azimuth=azimuth),
        "d": load_pvgis_result(lat, lon, tilt=tilt, azimuth=azimuth, offline=True),
    }
    elapsed = time.perf_counter() - started
    results["d"]["metadata"]["timed_read_used"] = results["d"]["metadata"]["used"]
    results["d"]["metadata"]["used"] = acquired_pvgis["metadata"]["used"]
    differences = []
    for left, right in itertools.combinations(results, 2):
        a, b = results[left]["specific_yield_kwh_kwp"], results[right]["specific_yield_kwh_kwp"]
        differences.append({"left": left, "right": right, "difference_kwh_kwp": a - b,
                            "relative_percent_of_right": 100 * (a - b) / b if b else None})
    figure_path = Path(figure_path) if figure_path is not None else ROOT / "reports" / "assets" / "T03-monthly.png"
    _plot_monthly(results, figure_path)
    return {"site": {"latitude": lat, "longitude": lon, "year": year, "tilt": tilt, "azimuth": azimuth},
            "weather_metadata": weather_meta, "results": results, "pairwise_differences": differences,
            "elapsed_compute_seconds": elapsed, "timing_scope": "three local chains plus recorded PVGIS read; network, startup imports and plot excluded",
            "monthly_figure": str(figure_path)}


def without_hourly(value):
    """Copy JSON results for persistence, retaining hourly series only in memory."""
    if isinstance(value, dict):
        return {key: without_hourly(item) for key, item in value.items() if key != 'hourly'}
    if isinstance(value, list):
        return [without_hourly(item) for item in value]
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    check = parser.add_subparsers(dest="command", required=True).add_parser("crosscheck")
    for name, default in (("lat", None), ("lon", None), ("tilt", 25), ("azimuth", 180)):
        check.add_argument("--" + name, type=float, required=default is None, default=default)
    check.add_argument("--year", type=int, required=True)
    check.add_argument("--offline", action="store_true")
    check.add_argument("--figure", type=Path)
    args = parser.parse_args(argv)
    try:
        result = crosscheck(args.lat, args.lon, args.year, tilt=args.tilt, azimuth=args.azimuth,
                            offline=args.offline, figure_path=args.figure)
        print(json.dumps(without_hourly(result), ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, RuntimeError, requests.RequestException) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
