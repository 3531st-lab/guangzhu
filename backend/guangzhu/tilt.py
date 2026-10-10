"""倾角按当地算：用项目所在地的逐时天气，算 0–35° 每一度的全年有效辐照，再定三套方案的倾角。"""
import math

import numpy as np
import pandas as pd
import pvlib

from .solar import poa_irradiance, sun_position

FLOOR_DEG = 10  # 示意：常见的最低倾角，再低雨水冲不走灰；用户给了倾角下限就用用户的
PAYBACK_RATIO = 1.05  # 与 T17 折中推荐一致：回本不超过最快方案的 1.05 倍
BASIS = 'NASA POWER 2023 逐时天气 · Perez 散射 · 玻璃入射角修正'


def irradiation_by_tilt(weather, lat, lon, azimuth=180, albedo=0.2):
    """Annual effective plane-of-array irradiation (kWh/m²) for each integer tilt 0–35°, same optics as the yield chain."""
    from .yieldsim import _weather_data
    df = _weather_data(weather)
    midpoint = df.index + pd.Timedelta(minutes=float(df.attrs['hour_midpoint_offset_minutes']))
    sun = sun_position(midpoint, lat, lon, temp_c=df.temp_air.to_numpy())
    zenith, bearing = sun.apparent_zenith.to_numpy(), sun.azimuth.to_numpy()
    totals = {}
    for tilt in range(36):
        poa = poa_irradiance(df, sun, tilt, azimuth, albedo=albedo, model='perez')
        beam = pvlib.iam.physical(pvlib.irradiance.aoi(tilt, azimuth, zenith, bearing))
        diffuse = pvlib.iam.marion_diffuse('physical', tilt)
        effective = (poa.poa_direct.to_numpy() * beam + poa.poa_sky_diffuse.to_numpy() * diffuse['sky']
                     + poa.poa_ground_diffuse.to_numpy() * diffuse['ground'])
        totals[tilt] = round(float(np.maximum(effective, 0).sum()) / 1000, 3)
    return totals


def value(totals, tilt):
    low, high = math.floor(tilt), math.ceil(tilt)
    return totals[low] + (totals[high] - totals[low]) * (tilt - low)


def choose(totals, bounds=None):
    """Best (physical optimum), max-capacity, balanced tilts and fast-payback trials; the user's range always wins."""
    low, high = bounds if bounds else (FLOOR_DEG, 35)
    clip = lambda tilt: min(max(tilt, low), high)
    whole = list(range(math.ceil(low), math.floor(high) + 1)) or [clip(round((low + high) / 2))]
    best = max(whole, key=lambda tilt: value(totals, tilt))
    enough = value(totals, best) / PAYBACK_RATIO
    balanced = next(tilt for tilt in whole if value(totals, tilt) >= enough)
    if balanced <= low and best > low:
        balanced = clip(round((low + best) / 2))
    trials = list(dict.fromkeys(clip(tilt) for tilt in (best - 6, best - 3, best)))
    optimum = max(totals, key=totals.get)
    return dict(best=optimum, capacity=low, balanced=balanced, trials=trials,
                loss_pct=dict(capacity=round(100 * (1 - value(totals, low) / totals[optimum]), 1),
                              balanced=round(100 * (1 - value(totals, balanced) / totals[optimum]), 1)))
