"""NREL SPA solar position and transparent plane-of-array transposition."""

import math

import numpy as np
import pandas as pd
import pvlib


def sun_position(times, lat, lon, altitude_m=0, pressure_pa=None, temp_c=None):
    """Calculate positions at the supplied instants, preserving their timezone.

    Hourly NASA labels are starts: callers supply label + 30 minutes.
    https://power.larc.nasa.gov/docs/faqs/other/#time-range
    SPA uses its documented default delta_t=67 s, matching the NREL example:
    https://www.nrel.gov/docs/fy08osti/34302.pdf
    """
    times = pd.DatetimeIndex(times)
    if times.tz is None:
        raise ValueError("Solar position requires an explicit timezone.")
    if not math.isfinite(lat) or not -90 <= lat <= 90:
        raise ValueError("Latitude must be finite and within [-90, 90].")
    if not math.isfinite(lon) or not -180 <= lon <= 180:
        raise ValueError("Longitude must be finite and within [-180, 180].")
    sun = pvlib.solarposition.get_solarposition(
        times, latitude=lat, longitude=lon, altitude=altitude_m,
        pressure=pressure_pa, temperature=12 if temp_c is None else temp_c,
        method="nrel_numpy", delta_t=67,
    )
    return sun[["apparent_zenith", "zenith", "elevation", "azimuth"]]


def poa_irradiance(weather, sun, tilt, azimuth, albedo=0.2, model="perez"):
    """Transpose W/m2 to a tilted surface; sun rows correspond by position.

    The output keeps the weather interval labels while the sun index holds
    interval midpoints. Passing Series with different labels would incorrectly
    align starts and midpoints, so all pvlib inputs below are positional arrays.
    """
    if model not in {"perez", "isotropic"}:
        raise ValueError("Supported sky models are perez and isotropic.")
    if not math.isfinite(tilt) or not 0 <= tilt <= 90:
        raise ValueError("Tilt must be finite and within [0, 90].")
    if not math.isfinite(azimuth) or not 0 <= azimuth <= 360:
        raise ValueError("Azimuth must be finite and within [0, 360].")
    if not math.isfinite(albedo) or not 0 <= albedo <= 1:
        raise ValueError("Albedo must be finite and within [0, 1].")
    if len(weather) != len(sun):
        raise ValueError("Weather and solar-position rows must have equal lengths.")
    irradiance = weather[["ghi", "dni", "dhi"]].to_numpy(dtype=float)
    if not np.isfinite(irradiance).all():
        raise ValueError("Irradiance inputs must be finite; run weather QC first.")
    zenith = sun.apparent_zenith.to_numpy()
    result = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt, surface_azimuth=azimuth, solar_zenith=zenith,
        solar_azimuth=sun.azimuth.to_numpy(),
        ghi=irradiance[:, 0], dni=irradiance[:, 1], dhi=irradiance[:, 2],
        dni_extra=pvlib.irradiance.get_extra_radiation(sun.index).to_numpy(),
        airmass=pvlib.atmosphere.get_relative_airmass(zenith),
        albedo=albedo, model=model,
    )
    poa = pd.DataFrame(result, index=weather.index)
    # Perez's sky-clearness ratio is undefined for a completely dark input,
    # even in daylight. All POA components are physically zero in those rows.
    # Other undefined daytime inputs remain errors rather than being filled.
    poa.loc[np.all(irradiance == 0, axis=1)] = 0.0
    # Perez's undefined airmass at night represents zero sky irradiance.
    night = zenith >= 90
    poa.loc[night] = poa.loc[night].fillna(0)
    if poa.isna().any().any():
        raise ValueError("Transposition produced undefined daytime irradiance.")
    return poa
