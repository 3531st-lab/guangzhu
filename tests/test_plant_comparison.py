"""Offline PVDAQ report and real product-chain regressions, without downloading data."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib
import pytest
import requests

from guangzhu import economics, yieldsim
from guangzhu.config import ROOT

SPEC = importlib.util.spec_from_file_location("compare_plant", ROOT / "scripts/compare_plant.py")
plant = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plant)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Plant comparison tests must stay offline")
    monkeypatch.setattr(requests.Session, "request", fail)


def write_csv(tmp_path, times, values):
    path = tmp_path / "channel.csv"
    frame = pd.DataFrame(values, index=times).rename_axis("measured_on")
    frame.to_csv(path)
    return path


def test_sensor_units_full_sample_requirement_and_negative_samples(tmp_path):
    times = pd.date_range("2022-06-21 12:00", periods=12, freq="15min")
    values = {plant.CHANNELS[1]: [68] * 12, plant.CHANNELS[2]: [10] * 12}
    values[plant.CHANNELS[2]][7] = -1
    path = write_csv(tmp_path, times, values)
    index = pd.date_range("2022-06-21 19:00", periods=3, freq="h", tz="UTC")
    frame, complete, invalid, audit = plant.hourly(path, plant.CHANNELS[1:3], index)
    assert frame.iloc[0, 0] == pytest.approx(20)
    assert frame.iloc[0, 1] == pytest.approx(4.4704)
    assert complete.tolist() == [True, True, True]
    assert invalid.tolist() == [False, True, False]
    assert audit == dict(cadence_seconds=900, unresolved_dst=0)
    original = pd.read_csv(path).drop(index=9)
    original.to_csv(path, index=False)
    _, complete, _, _ = plant.hourly(path, plant.CHANNELS[1:3], index)
    assert complete.tolist() == [True, True, False]


def test_dst_fall_repeats_are_kept_when_unambiguous_and_not_guessed_when_missing(tmp_path):
    first = pd.date_range("2022-11-06 00:00", "2022-11-06 01:45", freq="15min")
    second = pd.date_range("2022-11-06 01:00", "2022-11-06 02:45", freq="15min")
    times = first.append(second)
    path = write_csv(tmp_path, times, {plant.CHANNELS[0]: np.arange(len(times)) + 1})
    index = pd.date_range("2022-11-06 07:00", periods=4, freq="h", tz="UTC")
    frame, complete, _, audit = plant.hourly(path, plant.CHANNELS[:1], index)
    assert complete.tolist() == [True, True, True, True]
    assert frame.iloc[1, 0] == pytest.approx(6.5) and frame.iloc[2, 0] == pytest.approx(10.5)
    assert audit["unresolved_dst"] == 0
    times = pd.date_range("2022-11-06 00:00", "2022-11-06 02:45", freq="15min")
    path = write_csv(tmp_path, times, {plant.CHANNELS[0]: [5] * len(times)})
    _, complete, _, audit = plant.hourly(path, plant.CHANNELS[:1], index)
    assert complete.tolist() == [True, False, False, True]
    assert audit["unresolved_dst"] == 4


def test_duplicate_acquisition_times_fail_instead_of_averaging(tmp_path):
    times = pd.date_range("2022-06-21 12:00", periods=8, freq="15min")
    path = write_csv(tmp_path, times.append(times[:1]), {plant.CHANNELS[0]: [1] * 9})
    index = pd.date_range("2022-06-21 19:00", periods=2, freq="h", tz="UTC")
    with pytest.raises(ValueError, match="Duplicate UTC"):
        plant.hourly(path, plant.CHANNELS[:1], index)


def test_utc_year_boundary_reads_the_matching_previous_local_calendar_day(tmp_path):
    times = pd.date_range("2021-12-31 16:00", periods=8, freq="15min")
    path = write_csv(tmp_path, times, {plant.CHANNELS[0]: [8] * len(times)})
    index = pd.date_range("2022-01-01 00:00", periods=2, freq="h", tz="UTC")
    frame, complete, _, audit = plant.hourly(path, plant.CHANNELS[:1], index)
    assert complete.tolist() == [True, True]
    assert frame[plant.CHANNELS[0]].tolist() == [8, 8]
    assert audit["unresolved_dst"] == 0


def test_both_real_product_simulations_zero_exactly_the_same_excluded_hours(monkeypatch):
    index = pd.date_range("2022-06-20", periods=72, freq="h", tz="UTC")
    midpoint = index + pd.Timedelta(minutes=30)
    site = pvlib.location.Location(38.996306, -122.134111)
    sun = site.get_solarposition(midpoint)
    sky = site.get_clearsky(midpoint).set_axis(index)
    nasa = sky.assign(temp_air=20.0, wind_speed=2.0)
    poa = pvlib.irradiance.get_total_irradiance(25, 180, sun.zenith.to_numpy(), sun.azimuth.to_numpy(),
        sky.dni, sky.ghi, sky.dhi, dni_extra=pvlib.irradiance.get_extra_radiation(midpoint).to_numpy(), albedo=.2, model="perez").poa_global
    measured = pd.DataFrame({plant.CHANNELS[0]: poa / 2, plant.CHANNELS[1]: 20.0,
                            plant.CHANNELS[2]: 2.0, plant.CHANNELS[3]: poa}, index=index)
    complete = pd.Series(True, index=index)
    invalid = pd.Series(False, index=index)
    complete.iloc[20] = False
    invalid.iloc[21] = True
    measured.iloc[22, 0] = 0
    original = yieldsim.simulate_pvlib_detailed
    calls = []

    def capture(frame, *args, **kwargs):
        calls.append((frame.copy(), kwargs.copy()))
        return original(frame, *args, **kwargs)

    monkeypatch.setattr(plant.yieldsim, "simulate_pvlib_detailed", capture)
    metadata = dict(latitude=site.latitude, longitude=site.longitude, tilt=25, azimuth=180, capacity_kw=893)
    monthly, qc = plant.compare(measured, complete, invalid, nasa, metadata)
    assert len(calls) == 2
    expected_loss = economics.load_assumptions()["design_system_loss_pct"]["value"]
    assert all(kwargs == dict(tilt=25, azimuth=180, loss_percent=expected_loss, offline=True) for _, kwargs in calls)
    first, second = [frame[["ghi", "dni", "dhi"]].eq(0).all(axis=1) for frame, _ in calls]
    assert all(first.iloc[[20, 21, 22]]) and all(second.iloc[[20, 21, 22]])
    assert first.equals(second)
    assert calls[0][0].index.equals(index) and calls[1][0].index.equals(index)
    assert monthly.loc[6, "missing"] == 1 and monthly.loc[6, "nonphysical"] == 1
    assert monthly.loc[6, "outage_proxy"] == 1
    assert qc["loss_percent"] == expected_loss
    assert qc["reference_model"]["catalog"]["module_name"] == "Trina Solar TSM-550DE19"
    assert "files" not in qc["reference_model"]["catalog"]
    pd.testing.assert_frame_equal(nasa, sky.assign(temp_air=20.0, wind_speed=2.0))


def test_committed_twelve_month_metrics_recompute_and_cleaning_counts_balance():
    data = json.loads((ROOT / "data/field/plant/2107-metadata.json").read_text(encoding="utf-8"))
    monthly = pd.read_csv(ROOT / "data/field/plant/2107-monthly.csv").set_index("month")
    assert monthly.index.tolist() == list(range(1, 13))
    assert (monthly.kept_hours > 0).all() and (monthly.measured_kwh > 0).all()
    assert (monthly.candidate_hours == monthly.kept_hours + monthly.excluded_hours).all()
    assert monthly.candidate_hours.sum() == 8760
    for label in ("nasa", "station"):
        ape = abs(monthly[label + "_kwh"] / monthly.measured_kwh - 1) * 100
        assert np.allclose(ape, monthly[label + "_ape_pct"], atol=1e-8)
        assert data["summary"][label]["mape_pct"] == pytest.approx(ape.mean(), abs=1e-8)
        bias = (monthly[label + "_kwh"].sum() / monthly.measured_kwh.sum() - 1) * 100
        assert data["summary"][label]["bias_pct"] == pytest.approx(bias, abs=1e-8)
    assert data["plant"]["year"] == 2022 and data["plant"]["capacity_kw"] == 893
    assert data["plant"]["license"] == "CC-BY-4.0"
    assert all(len(row["sha256"]) == 64 and row["url"].startswith(plant.BASE) for row in data["sources"])
    assert data["nasa"]["year"] == 2022
    assert data["qc"]["loss_percent"] == economics.load_assumptions()["design_system_loss_pct"]["value"]
    assert data["qc"]["poa_roundtrip_mae_w_m2"] >= 0
    assert (ROOT / "reports/assets/T12/plant-2107.png").stat().st_size > 10000


def test_source_has_no_long_lines_or_multiple_python_statements():
    import ast
    source = (ROOT / "scripts/compare_plant.py").read_text(encoding="utf-8")
    assert all(len(line) <= 160 for line in source.splitlines())
    occupied = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.stmt):
            assert node.lineno not in occupied, (node.lineno, occupied.get(node.lineno), type(node).__name__)
            occupied[node.lineno] = type(node).__name__
