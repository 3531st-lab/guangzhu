"""T19: tilts follow the site's latitude and weather; the user's tilt range always wins."""
import math

import numpy as np
import pandas as pd
import pvlib
import pytest

from guangzhu import tilt, weather, yieldsim


def clear_sky_year(lat, lon):
    """A cloudless 2023 at the site: enough to show how the optimum moves with latitude, no network needed."""
    times = pd.date_range('2023-01-01', '2024-01-01', freq='h', tz='UTC', inclusive='left')
    sky = pvlib.location.Location(lat, lon).get_clearsky(times + pd.Timedelta(minutes=30), model='ineichen')
    frame = pd.DataFrame(dict(ghi=sky.ghi.to_numpy(), dni=sky.dni.to_numpy(), dhi=sky.dhi.to_numpy(), temp_air=20.0, wind_speed=2.0),
                         index=times)
    frame.attrs['hour_midpoint_offset_minutes'] = 30
    return frame


@pytest.fixture(scope='module')
def changzhou():
    nasa, _ = weather.load_nasa_hourly(31.81, 119.97, 2023, offline=True)
    return nasa, tilt.irradiation_by_tilt(nasa, 31.81, 119.97)


def test_sweep_uses_the_same_optics_as_the_yield_chain(changzhou):
    nasa, totals = changzhou
    _, effective = yieldsim._poa_and_effective(yieldsim._weather_data(nasa), 31.81, 119.97, 25, 180)
    assert totals[25] == pytest.approx(effective.sum() / 1000, abs=.001)
    assert sorted(totals) == list(range(36))


def test_changzhou_tilts_come_from_local_weather(changzhou):
    _, totals = changzhou
    plan = tilt.choose(totals)
    assert plan['best'] == 32 and plan['capacity'] == 10 and plan['balanced'] == 12 and plan['trials'] == [26, 29, 32]
    assert plan['loss_pct'] == dict(capacity=5.8, balanced=4.7)
    best = max(totals.values())
    assert totals[12] >= best / 1.05 > totals[11]


def test_higher_latitude_gives_a_higher_best_tilt():
    best = {city: max((tilt.irradiation_by_tilt(clear_sky_year(lat, lon), lat, lon)).items(), key=lambda row: row[1])[0]
            for city, lat, lon in (('海口', 20.04, 110.32), ('常州', 31.81, 119.97), ('哈尔滨', 45.75, 126.65))}
    assert best['海口'] < best['常州'] < best['哈尔滨']


@pytest.mark.parametrize('bounds,capacity,balanced,trials', [
    ((15, 25), 15, 20, [19, 22, 25]),
    ((15.2, 15.4), 15.2, 15.2, [15.2]),
    ((20, 30), 20, 25, [24, 27, 30]),
    ((5, 35), 5, 20, [29, 32, 35]),
])
def test_user_range_wins_and_decimal_ranges_keep_the_t17_rule(bounds, capacity, balanced, trials):
    rising = {angle: 1000 + angle for angle in range(36)}
    plan = tilt.choose(rising, bounds)
    assert (plan['capacity'], plan['balanced'], plan['trials']) == (capacity, balanced, trials)
    assert all(bounds[0] <= angle <= bounds[1] for angle in [plan['capacity'], plan['balanced'], *plan['trials']])


def test_balanced_is_the_lowest_tilt_within_the_payback_ratio_when_it_differs_from_capacity():
    steep = {angle: 1000 * math.cos(math.radians(abs(angle - 38))) ** 3 for angle in range(36)}
    plan = tilt.choose(steep)
    best = steep[plan['trials'][-1]]
    assert steep[plan['balanced']] >= best / tilt.PAYBACK_RATIO > steep[plan['balanced'] - 1]
    assert plan['capacity'] < plan['balanced'] < plan['trials'][-1]


def test_flat_curve_keeps_three_distinct_options():
    flat = {angle: 1000 * math.cos(math.radians(abs(angle - 14))) ** 1.2 for angle in range(36)}
    plan = tilt.choose(flat)
    assert plan['capacity'] == 10 and plan['balanced'] == 12 and plan['trials'] == [10, 11, 14]


def test_roof_tilt_hint_endpoint_uses_cached_weather_and_explains_the_trade(monkeypatch):
    from fastapi.testclient import TestClient
    from guangzhu import api
    monkeypatch.setattr(api, 'TILT_HINTS', {})
    hint = TestClient(api.app).get('/api/roofs/changzhou-demo/tilt').json()
    assert hint['available'] is True and hint['best'] == 32 and hint['balanced'] == 12 and hint['capacity'] == 10
    assert hint['loss_pct'] == dict(capacity=5.8, balanced=4.7) and 30 <= hint['more_rows_pct'] <= 45
    assert TestClient(api.app).get('/api/roofs/no-such-roof/tilt').status_code == 400
