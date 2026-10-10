import numpy as np
import pandas as pd
import pytest

from guangzhu.solar import poa_irradiance, sun_position


def test_nrel_spa_standard_example():
    times = pd.DatetimeIndex(["2003-10-17T12:30:30-07:00"])
    sun = sun_position(times, 39.742476, -105.1786, altitude_m=1830.14,
                       pressure_pa=82000, temp_c=11)
    assert abs(sun.apparent_zenith.iloc[0] - 50.11162) < 0.01
    assert abs(sun.azimuth.iloc[0] - 194.34024) < 0.01


@pytest.mark.parametrize("model", ["perez", "isotropic"])
def test_horizontal_poa_equals_closed_horizontal_irradiance(model):
    # A closed synthetic fixture, not a modification to recorded NASA data.
    labels = pd.date_range("2023-06-21T02:00Z", periods=5, freq="h")
    sun = sun_position(labels + pd.Timedelta(minutes=30), 31.81, 119.97)
    dni = np.full(len(labels), 700.0)
    dhi = np.full(len(labels), 100.0)
    ghi = dni * np.cos(np.radians(sun.apparent_zenith.to_numpy())) + dhi
    weather = pd.DataFrame({"ghi": ghi, "dni": dni, "dhi": dhi}, index=labels)
    poa = poa_irradiance(weather, sun, 0, 180, model=model)
    assert poa.index.equals(labels)
    np.testing.assert_allclose(poa.poa_global, ghi, atol=1e-9, rtol=0)


def test_timezone_is_required():
    with pytest.raises(ValueError, match="timezone"):
        sun_position(pd.date_range("2023-01-01", periods=2, freq="h"), 31.81, 119.97)


def test_missing_irradiance_is_not_silently_filled():
    labels = pd.date_range("2023-06-21T04:00Z", periods=1, freq="h")
    sun = sun_position(labels + pd.Timedelta(minutes=30), 31.81, 119.97)
    weather = pd.DataFrame({"ghi": [600.0], "dni": [np.nan], "dhi": [100.0]}, index=labels)
    with pytest.raises(ValueError, match="finite"):
        poa_irradiance(weather, sun, 25, 180)


def test_zero_irradiance_has_zero_poa_in_daylight():
    labels = pd.date_range("2023-06-21T02:00Z", periods=5, freq="h")
    sun = sun_position(labels + pd.Timedelta(minutes=30), 31.81, 119.97)
    assert (sun.apparent_zenith < 90).all()
    weather = pd.DataFrame(0.0, columns=["ghi", "dni", "dhi"], index=labels)
    poa = poa_irradiance(weather, sun, 25, 180)
    np.testing.assert_array_equal(poa.to_numpy(), np.zeros((5, 5)))
