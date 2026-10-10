"""Hourly public weather, exact-site disk caches, and transparent quality checks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import uuid

import numpy as np
import pandas as pd
import pvlib
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import DATA_DIR


CACHE_DIR = DATA_DIR / "cache" / "weather"
DEMO_DIR = DATA_DIR / "demo" / "weather"
COLUMNS = ["ghi", "dni", "dhi", "temp_air", "wind_speed"]
NASA_PARAMETERS = {
    "ALLSKY_SFC_SW_DWN": "ghi", "ALLSKY_SFC_SW_DNI": "dni",
    "ALLSKY_SFC_SW_DIFF": "dhi", "T2M": "temp_air", "WS10M": "wind_speed",
}
PVGIS_PARAMETERS = {"G(h)": "ghi", "Gb(n)": "dni", "Gd(h)": "dhi", "T2m": "temp_air", "WS10m": "wind_speed"}
NASA_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/tmy"
NASA_TIME_SOURCE = "https://power.larc.nasa.gov/docs/faqs/other/#time-range"
PVGIS_TIME_SOURCE = (
    "https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/"
    "using-pvgis-5/pvgis-5-user-manual_en"
)
TMY_YEAR = 1990


class WeatherDataError(RuntimeError):
    """Weather cannot be retrieved or its provenance cannot be verified."""


def _validate_site(lat: float, lon: float) -> tuple[float, float]:
    lat, lon = float(lat), float(lon)
    if not math.isfinite(lat) or not -90 <= lat <= 90:
        raise ValueError("Latitude must be finite and between -90 and 90.")
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise ValueError("Longitude must be finite and between -180 and 180.")
    return lat, lon


def _cache_key(source: str, lat: float, lon: float, year: int) -> str:
    lat, lon = _validate_site(lat, lon)
    return f"{source}_{lat:.4f}_{lon:.4f}_{year}"


def _normalize(df: pd.DataFrame, offset_minutes: float = 30) -> pd.DataFrame:
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.tz is None:
        raise WeatherDataError("Weather timestamps must have an explicit timezone.")
    if df.index.has_duplicates:
        raise WeatherDataError("Weather timestamps contain duplicates.")
    missing = set(COLUMNS) - set(df.columns)
    if missing:
        raise WeatherDataError("Weather is missing required columns: " + ", ".join(sorted(missing)))
    df = df[COLUMNS].apply(pd.to_numeric, errors="coerce").replace(-999, np.nan).sort_index()
    df.index = df.index.tz_convert("UTC")
    df.index.name = "time"
    df.attrs["hour_midpoint_offset_minutes"] = float(offset_minutes)
    return df


def _parse_nasa_payload(payload: dict) -> pd.DataFrame:
    # NASA's official FAQ identifies the timestamp as the START of the hour:
    # https://power.larc.nasa.gov/docs/faqs/other/#time-range
    # The Wh/m2 value for a one-hour interval is numerically its mean W/m2;
    # solar position must therefore use timestamp + 30 minutes.
    try:
        if payload.get("header", {}).get("time_standard", "UTC") != "UTC":
            raise WeatherDataError("NASA response is not in the requested UTC time standard.")
        parameters = payload["properties"]["parameter"]
        df = pd.DataFrame({column: parameters[name] for name, column in NASA_PARAMETERS.items()})
        df.index = pd.to_datetime(df.index, format="%Y%m%d%H", utc=True)
        fill = payload.get("header", {}).get("fill_value", -999)
        return _normalize(df.replace(fill, np.nan))
    except (KeyError, TypeError, ValueError) as error:
        raise WeatherDataError("Malformed NASA hourly response.") from error


def _parse_pvgis_payload(payload: dict) -> pd.DataFrame:
    # The JRC user manual states TMY CSV/JSON HH:00 represents ERA5 HH:30.
    # https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/pvgis-5-user-manual_en
    try:
        hourly = pd.DataFrame(payload["outputs"]["tmy_hourly"])
        times = pd.to_datetime(hourly["time(UTC)"], format="%Y%m%d:%H%M", utc=True)
        # TMY months originate in different years. A non-leap reference year
        # preserves their month/day/hour while providing one continuous year.
        keep = ~((times.dt.month == 2) & (times.dt.day == 29))
        df = hourly.loc[keep, list(PVGIS_PARAMETERS)].rename(columns=PVGIS_PARAMETERS)
        df.index = pd.DatetimeIndex([stamp.replace(year=TMY_YEAR) for stamp in times[keep]])
        offset = float(payload.get("inputs", {}).get("location", {}).get("irradiance_time_offset", 0.5))
        return _normalize(df, offset * 60)
    except (KeyError, TypeError, ValueError) as error:
        raise WeatherDataError("Malformed PVGIS typical-year response.") from error


def _metadata(source: str, lat: float, lon: float, year: int, df: pd.DataFrame,
              request_url: str, payload: dict) -> dict:
    meta = {
        "schema": "guangzhu.weather/1", "source": source,
        "source_description": "NASA POWER UTC hourly" if source == "nasa" else "PVGIS 5.3 ERA5 typical meteorological year",
        "latitude": lat, "longitude": lon, "year": year,
        "request_url": request_url, "download_time": datetime.now(timezone.utc).isoformat(),
        "used": "download", "timezone": "UTC", "interval_minutes": 60,
        "hour_midpoint_offset_minutes": df.attrs["hour_midpoint_offset_minutes"],
        "units": {"ghi": "W/m2", "dni": "W/m2", "dhi": "W/m2", "temp_air": "degC", "wind_speed": "m/s"},
        "missing_counts": {column: int(df[column].isna().sum()) for column in COLUMNS},
    }
    if source == "nasa":
        meta.update({"timestamp_semantics": "start of one-hour interval", "timestamp_source": NASA_TIME_SOURCE,
                     "nasa_header": payload.get("header", {}), "nasa_parameters": payload.get("parameters", {})})
    else:
        inputs = payload.get("inputs", {})
        meta.update({"timestamp_semantics": "TMY HH:00 label; ERA5 irradiance at HH:30",
                     "timestamp_source": PVGIS_TIME_SOURCE, "normalization_year": TMY_YEAR,
                     "months_selected": payload.get("outputs", {}).get("months_selected", []),
                     "pvgis_inputs": inputs,
                     "irradiance_time_offset": inputs.get("location", {}).get("irradiance_time_offset", 0.5)})
    return meta


def _atomic_write(path: Path, contents: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        temporary.write_bytes(contents)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_dataset(directory: Path, key: str, df: pd.DataFrame, meta: dict) -> dict:
    """Write normalized CSV.gz and its integrity/provenance JSON; return metadata."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    normalized = _normalize(df, df.attrs.get("hour_midpoint_offset_minutes", 30))
    contents = gzip.compress(normalized.to_csv().encode("utf-8"), mtime=0)
    result = dict(meta)
    result.update({"data_file": key + ".csv.gz", "data_file_sha256": hashlib.sha256(contents).hexdigest(),
                   "hour_midpoint_offset_minutes": normalized.attrs["hour_midpoint_offset_minutes"],
                   "missing_counts": {column: int(normalized[column].isna().sum()) for column in COLUMNS}})
    _atomic_write(directory / (key + ".csv.gz"), contents)
    _atomic_write(directory / (key + ".json"), json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    return result


def _read_dataset(directory: Path, key: str, *, used: str) -> tuple[pd.DataFrame, dict] | None:
    data_path, meta_path = Path(directory) / (key + ".csv.gz"), Path(directory) / (key + ".json")
    if not data_path.exists() and not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        contents = data_path.read_bytes()
        if hashlib.sha256(contents).hexdigest() != meta["data_file_sha256"]:
            raise WeatherDataError("Weather dataset checksum does not match its metadata.")
        expected = _cache_key(meta["source"], meta["latitude"], meta["longitude"], meta["year"])
        if key != expected:
            raise WeatherDataError("Weather dataset metadata does not match the requested site/year.")
        df = pd.read_csv(io.BytesIO(contents), compression="gzip", index_col=0)
        df.index = pd.to_datetime(df.index, utc=True)
        df = _normalize(df, float(meta["hour_midpoint_offset_minutes"]))
        if {column: int(df[column].isna().sum()) for column in COLUMNS} != meta["missing_counts"]:
            raise WeatherDataError("Weather missing-value counts do not match its metadata.")
        meta = dict(meta, used=used)
        return df, meta
    except (OSError, KeyError, TypeError, ValueError, EOFError) as error:
        raise WeatherDataError("Weather dataset or metadata is unreadable.") from error


def _download_json(request_url: str) -> dict:
    retry = Retry(total=0)  # AGH calls have a 60s budget; do not multiply request timeouts.
    with requests.Session() as session:
        session.mount("https://", HTTPAdapter(max_retries=retry))
        response = session.get(request_url, timeout=(3, 15))
        response.raise_for_status()
        return response.json()


def _load(source: str, lat: float, lon: float, year: int, *, offline: bool) -> tuple[pd.DataFrame, dict]:
    lat, lon = _validate_site(lat, lon)
    key = _cache_key(source, lat, lon, year)
    failures = []
    try:
        cached = _read_dataset(CACHE_DIR, key, used="cache")
        if cached is not None:
            return cached
    except WeatherDataError as error:
        failures.append(str(error))
    if not offline:
        if source == "nasa":
            parameters = {"latitude": lat, "longitude": lon, "start": f"{year}0101", "end": f"{year}1231",
                          "parameters": ",".join(NASA_PARAMETERS), "community": "RE", "time-standard": "UTC", "format": "JSON"}
            request_url = requests.Request("GET", NASA_URL, params=parameters).prepare().url
        else:
            parameters = {"lat": lat, "lon": lon, "outputformat": "json", "raddatabase": "PVGIS-ERA5"}
            request_url = requests.Request("GET", PVGIS_URL, params=parameters).prepare().url
        try:
            payload = _download_json(request_url)
            df = _parse_nasa_payload(payload) if source == "nasa" else _parse_pvgis_payload(payload)
            meta = _metadata(source, lat, lon, year, df, request_url, payload)
            return df, _write_dataset(CACHE_DIR, key, df, meta)
        except (requests.RequestException, WeatherDataError, ValueError, OSError) as error:
            failures.append(type(error).__name__)
    try:
        demo = _read_dataset(DEMO_DIR, key, used="demo")
        if demo is not None:
            df, meta = demo
            if failures:
                meta["fallback_reason"] = "; ".join(failures)
            return df, meta
    except WeatherDataError as error:
        failures.append(str(error))
    reason = "offline mode" if offline else "download failed"
    raise WeatherDataError(f"No usable weather for {key}: {reason}; no matching site/year cache or demo." + (" " + "; ".join(failures) if failures else ""))


def load_nasa_hourly(lat: float, lon: float, year: int, *, offline: bool = False) -> tuple[pd.DataFrame, dict]:
    if isinstance(year, bool) or not isinstance(year, int) or not 1981 <= year <= 2100:
        raise ValueError("NASA year must be an integer between 1981 and 2100.")
    return _load("nasa", lat, lon, year, offline=offline)


def load_pvgis_tmy(lat: float, lon: float, *, offline: bool = False) -> tuple[pd.DataFrame, dict]:
    return _load("pvgis", lat, lon, TMY_YEAR, offline=offline)


def _daily_frame(df: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    df = df[["T2M_MIN", "T2M_MAX"]].apply(pd.to_numeric, errors="coerce").replace(-999, np.nan).sort_index()
    expected = pd.date_range(f"{start_year}-01-01", f"{end_year}-12-31", name="date")
    if not df.index.equals(expected):
        raise WeatherDataError("NASA daily dates are missing, duplicated, or outside the requested full years.")
    if not np.isfinite(df.to_numpy()).all() or ((df < -100) | (df > 70)).any().any():
        raise WeatherDataError("NASA daily temperatures are missing or outside -100..70 degC.")
    if (df.T2M_MIN > df.T2M_MAX).any():
        raise WeatherDataError("NASA daily minimum exceeds maximum temperature.")
    return df


def _read_daily(directory: Path, key: str, lat: float, lon: float, start: int, end: int, used: str):
    data_path, meta_path = Path(directory) / (key + ".csv.gz"), Path(directory) / (key + ".json")
    if not data_path.exists() and not meta_path.exists():
        return None
    try:
        meta, contents = json.loads(meta_path.read_text(encoding="utf-8")), data_path.read_bytes()
        if hashlib.sha256(contents).hexdigest() != meta["data_file_sha256"]:
            raise WeatherDataError("NASA daily dataset checksum does not match its metadata.")
        identity = (meta["source"], round(meta["latitude"], 4), round(meta["longitude"], 4),
                    meta["start_year"], meta["end_year"], meta["time_standard"], meta["data_file"])
        if identity != ("nasa_daily", round(lat, 4), round(lon, 4), start, end, "LST", key + ".csv.gz"):
            raise WeatherDataError("NASA daily metadata does not match the requested site/year range.")
        df = pd.read_csv(io.BytesIO(contents), compression="gzip", index_col=0, parse_dates=True)
        df = _daily_frame(df, start, end)
        if len(df) != meta["row_count"]:
            raise WeatherDataError("NASA daily row count does not match its metadata.")
        return df, dict(meta, used=used)
    except (OSError, KeyError, TypeError, ValueError, EOFError) as error:
        raise WeatherDataError("NASA daily dataset or metadata is unreadable.") from error


def load_nasa_daily_extremes(lat: float, lon: float, *, start_year: int, end_year: int,
                             offline: bool = False) -> dict:
    """Full-year daily 2 m air extremes, with exact-site verified cache/demo fallback."""
    lat, lon = _validate_site(lat, lon)
    if (any(isinstance(y, bool) or not isinstance(y, int) for y in (start_year, end_year))
            or not 1981 <= start_year <= end_year < datetime.now(timezone.utc).year):
        raise ValueError("NASA daily years must be completed integer years from 1981, in increasing order.")
    key = f"nasa_daily_{lat:.4f}_{lon:.4f}_{start_year}_{end_year}"
    failures, result = [], None
    try:
        result = _read_daily(CACHE_DIR, key, lat, lon, start_year, end_year, "cache")
    except WeatherDataError as error:
        failures.append(str(error))
    if result is None and not offline:
        # Daily API defaults to LST; specify it so dates are unambiguous, not UTC hours.
        # https://power.larc.nasa.gov/docs/services/api/temporal/daily/
        params = {"latitude": lat, "longitude": lon, "start": f"{start_year}0101", "end": f"{end_year}1231",
                  "parameters": "T2M_MIN,T2M_MAX", "community": "RE", "time-standard": "LST", "format": "JSON"}
        url = requests.Request("GET", "https://power.larc.nasa.gov/api/temporal/daily/point", params=params).prepare().url
        try:
            payload = _download_json(url)
            if payload.get("header", {}).get("time_standard", "LST") != "LST":
                raise WeatherDataError("NASA daily response is not in the requested LST time standard.")
            df = pd.DataFrame({name: payload["properties"]["parameter"][name] for name in ("T2M_MIN", "T2M_MAX")})
            df.index = pd.to_datetime(df.index, format="%Y%m%d")
            df.index.name = "date"
            df = _daily_frame(df.replace(payload.get("header", {}).get("fill_value", -999), np.nan), start_year, end_year)
            contents = gzip.compress(df.to_csv().encode("utf-8"), mtime=0)
            meta = {"schema": "guangzhu.weather.daily/1", "source": "nasa_daily", "source_description": "NASA POWER LST daily 2 m air temperature",
                    "latitude": lat, "longitude": lon, "start_year": start_year, "end_year": end_year,
                    "request_url": url, "download_time": datetime.now(timezone.utc).isoformat(), "used": "download",
                    "time_standard": "LST", "row_count": len(df), "missing_counts": {"T2M_MIN": 0, "T2M_MAX": 0},
                    "units": {"T2M_MIN": "degC", "T2M_MAX": "degC"}, "nasa_header": payload.get("header", {}),
                    "nasa_parameters": payload.get("parameters", {}), "license": "CC-BY-4.0",
                    "data_file": key + ".csv.gz", "data_file_sha256": hashlib.sha256(contents).hexdigest()}
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _atomic_write(CACHE_DIR / meta["data_file"], contents)
            _atomic_write(CACHE_DIR / (key + ".json"), json.dumps(meta, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
            result = df, meta
        except (requests.RequestException, WeatherDataError, KeyError, TypeError, ValueError, OSError) as error:
            failures.append(str(error))
    if result is None:
        try:
            result = _read_daily(DEMO_DIR, key, lat, lon, start_year, end_year, "demo")
        except WeatherDataError as error:
            failures.append(str(error))
        if result is None:
            raise WeatherDataError(f"No usable NASA daily data for {key}; no matching site/year range cache or demo. " + "; ".join(failures))
        if failures:
            result[1]["fallback_reason"] = "; ".join(failures)
    df, meta = result
    return {"temp_min_c": float(df.T2M_MIN.min()), "temp_max_c": float(df.T2M_MAX.max()),
            "min_date": df.T2M_MIN.idxmin().date().isoformat(), "max_date": df.T2M_MAX.idxmax().date().isoformat(),
            "start_year": start_year, "end_year": end_year, "metadata": meta}


def weather_qc(df: pd.DataFrame, lat: float, lon: float) -> dict:
    lat, lon = _validate_site(lat, lon)
    offset = float(df.attrs.get("hour_midpoint_offset_minutes", 30))
    df = _normalize(df, offset)
    midpoint = df.index + pd.Timedelta(minutes=offset)
    solar = pvlib.solarposition.get_solarposition(midpoint, lat, lon)
    cosine = np.maximum(np.cos(np.radians(solar["zenith"].to_numpy())), 0)
    residual = (df["ghi"] - (df["dni"] * cosine + df["dhi"])).dropna()
    def number(value):
        return None if pd.isna(value) else float(value)
    def quantiles(values: pd.Series) -> dict:
        if values.empty:
            return {"median": None, "p95": None}
        return {"median": number(values.median()), "p95": number(values.quantile(0.95))}
    return {
        "rows": len(df), "missing_counts": {column: int(df[column].isna().sum()) for column in COLUMNS},
        "hourly_continuous": bool(len(df) < 2 or (df.index.to_series().diff().iloc[1:] == pd.Timedelta(hours=1)).all()),
        "hour_midpoint_offset_minutes": offset,
        "range_violations": {
            "ghi": int(((df.ghi < 0) | (df.ghi > 1400)).sum()),
            "dni": int(((df.dni < 0) | (df.dni > 1300)).sum()),
            "dhi_gt_ghi_plus_50": int((df.dhi > df.ghi + 50).sum()),
            "temp_air": int(((df.temp_air < -40) | (df.temp_air > 55)).sum()),
        },
        "closure_residual_w_m2": {"signed": quantiles(residual), "absolute": quantiles(residual.abs())},
        "annual_ghi_kwh_m2": number(df.ghi.sum(min_count=1) / 1000),
        "temp_air_min_c": number(df.temp_air.min()), "temp_air_max_c": number(df.temp_air.max()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    fetch = parser.add_subparsers(dest="command", required=True).add_parser("fetch")
    fetch.add_argument("--source", choices=["nasa", "pvgis"], required=True)
    fetch.add_argument("--lat", type=float, required=True)
    fetch.add_argument("--lon", type=float, required=True)
    fetch.add_argument("--year", type=int)
    fetch.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    if args.source == "nasa" and args.year is None:
        parser.error("NASA requires --year.")
    try:
        if args.source == "nasa":
            df, meta = load_nasa_hourly(args.lat, args.lon, args.year, offline=args.offline)
        else:
            df, meta = load_pvgis_tmy(args.lat, args.lon, offline=args.offline)
        print(json.dumps({"metadata": meta, "qc": weather_qc(df, args.lat, args.lon)}, ensure_ascii=False, indent=2, allow_nan=False))
    except (WeatherDataError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
