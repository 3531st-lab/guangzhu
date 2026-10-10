"""PVDAQ 2107/2022: frozen cleaning and the unchanged product P50 reference chain."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pvlib
import requests
from guangzhu import economics, weather, yieldsim
from guangzhu.config import ROOT

BASE = "https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI/"
CACHE = ROOT / "data/cache/plant/2107"
FIELD = ROOT / "data/field/plant"
OUTPUT = ROOT / "reports/assets/T12"
CHANNELS = ["meter_revenue_grade_ac_output_meter_149578", "ambient_temperature_o_149575",
            "wind_speed_o_149576", "poa_irradiance_o_149574"]


def cached(name, download):
    path = CACHE / name.split("/")[-1]
    if not path.exists() and download:
        response = requests.get(BASE + name, timeout=(3, 30))
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    content = path.read_bytes()
    provenance = dict(url=BASE + name, sha256=hashlib.sha256(content).hexdigest(), bytes=len(content),
                      downloaded_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
    return path, provenance


def hourly(path, columns, index):
    raw = pd.read_csv(path, usecols=["measured_on", *columns])
    times = pd.to_datetime(raw.pop("measured_on"))
    start = index[0].tz_convert("PST8PDT").tz_localize(None)
    end = (index[-1] + pd.Timedelta(hours=1)).tz_convert("PST8PDT").tz_localize(None)
    selected = (times >= start) & (times < end)
    raw, times = raw.loc[selected].copy(), times.loc[selected]
    cadence = times.diff()[times.diff() > pd.Timedelta(0)].mode().iloc[0]
    if pd.Timedelta(hours=1) % cadence:
        raise ValueError("Sampling cadence must divide one hour")
    try:
        localized = times.dt.tz_localize("PST8PDT", ambiguous="infer", nonexistent="NaT")
    except ValueError:
        localized = times.dt.tz_localize("PST8PDT", ambiguous="NaT", nonexistent="NaT")
    raw.index = pd.DatetimeIndex(localized).tz_convert("UTC")
    unresolved = int(raw.index.isna().sum())
    raw = raw.loc[~raw.index.isna()]
    if raw.index.has_duplicates:
        raise ValueError("Duplicate UTC samples")
    if CHANNELS[1] in raw:
        raw[CHANNELS[1]] = (raw[CHANNELS[1]] - 32) * 5 / 9
        raw[CHANNELS[2]] *= 0.44704
    physical = np.isfinite(raw).all(axis=1) & (raw.drop(columns=[CHANNELS[1]], errors="ignore") >= 0).all(axis=1)
    if CHANNELS[1] in raw:
        physical &= raw[CHANNELS[1]].between(-100, 70)
    complete = raw.resample("h").count().eq(pd.Timedelta(hours=1) / cadence).all(axis=1).reindex(index, fill_value=False)
    aligned = pd.Series(raw.index.as_unit("ns").asi8 % cadence.value == 0, index=raw.index)
    grid = aligned.resample("h").min().reindex(index, fill_value=False)
    complete &= grid
    invalid = (~physical).resample("h").max().reindex(index, fill_value=False)
    audit = dict(cadence_seconds=cadence.total_seconds(), unresolved_dst=unresolved)
    return raw.resample("h").mean().reindex(index), complete, invalid, audit


def compare(measured, complete, invalid, nasa, metadata):
    lat, lon, tilt, azimuth, capacity = (metadata[k] for k in ("latitude", "longitude", "tilt", "azimuth", "capacity_kw"))
    sun = pvlib.solarposition.get_solarposition(nasa.index + pd.Timedelta(minutes=30), lat, lon)
    aoi = pvlib.irradiance.aoi(tilt, azimuth, sun.zenith, sun.azimuth)
    poa = measured[CHANNELS[3]]
    with warnings.catch_warnings(record=True) as caught:
        inferred = pvlib.irradiance.gti_dirint(poa.set_axis(sun.index), aoi, sun.zenith, sun.azimuth, sun.index,
                                            tilt, azimuth, albedo=0.2, calculate_gt_90=False)
    inferred.index = nasa.index
    night = sun.zenith.to_numpy() >= 90
    inferred.loc[night] = 0
    reasons = pd.DataFrame(dict(missing=~complete, nonphysical=invalid), index=nasa.index)
    reasons["outage_proxy"] = (measured[CHANNELS[0]] <= 0) & (poa >= 200)
    reasons["low_angle"] = ~night & ((sun.zenith.to_numpy() >= 80) | (aoi.to_numpy() >= 80))
    reasons["inversion"] = (~np.isfinite(inferred).all(axis=1) | (inferred < 0).any(axis=1)
                            | (inferred.ghi > 1400) | (inferred.dni > 1300))
    keep = ~reasons.any(axis=1)
    local = inferred.assign(temp_air=measured[CHANNELS[1]], wind_speed=measured[CHANNELS[2]]).where(keep, nasa)
    loss = economics.load_assumptions()["design_system_loss_pct"]["value"]
    results = {}
    for label, frame in (("nasa", nasa.copy()), ("station", local)):
        frame.loc[~keep, ["ghi", "dni", "dhi"]] = 0
        results[label] = yieldsim.simulate_pvlib_detailed(frame, lat, lon, tilt=tilt, azimuth=azimuth, loss_percent=loss, offline=True)
    monthly = reasons.groupby(reasons.index.month).sum().reindex(range(1, 13), fill_value=0)
    monthly["candidate_hours"] = pd.Series(1, index=nasa.index).groupby(nasa.index.month).sum()
    monthly["kept_hours"] = keep.groupby(keep.index.month).sum().reindex(range(1, 13), fill_value=0)
    monthly["excluded_hours"] = monthly.candidate_hours - monthly.kept_hours
    monthly["measured_kwh"] = measured[CHANNELS[0]].where(keep, 0).groupby(nasa.index.month).sum().reindex(range(1, 13), fill_value=0)
    for label, result in results.items():
        monthly[label + "_kwh"] = np.asarray(result["monthly_kwh"]) * capacity
        monthly[label + "_ape_pct"] = (monthly[label + "_kwh"] / monthly.measured_kwh - 1).abs() * 100
    retransposed = pvlib.irradiance.get_total_irradiance(tilt, azimuth, sun.zenith.to_numpy(), sun.azimuth.to_numpy(),
        inferred.dni, inferred.ghi, inferred.dhi, dni_extra=pvlib.irradiance.get_extra_radiation(sun.index).to_numpy(), albedo=0.2, model="perez")
    residual = (retransposed.poa_global - poa)[keep & ~night]
    qc = dict(loss_percent=loss, reference_model=results["nasa"]["metadata"], warnings=sorted(set(str(w.message) for w in caught)),
              poa_roundtrip_mae_w_m2=float(residual.abs().mean()), poa_roundtrip_p95_w_m2=float(residual.abs().quantile(.95)))
    qc["reference_model"]["catalog"].pop("files", None)
    monthly.index.name = "month"
    return monthly, qc


def markdown(frame):
    columns = ["月", *frame.columns]
    rows = ["|" + "|".join(columns) + "|", "|" + "|".join("---" for _ in columns) + "|"]
    for month, row in frame.iterrows():
        rows.append("|" + str(month) + "|" + "|".join(f"{value:.4f}" for value in row) + "|")
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    source, provenance = cached("metadata/2107_system_metadata.json", args.download)
    meta = json.loads(source.read_text(encoding="utf-8"))
    if [meta["Metrics"][key]["units"] for key in CHANNELS] != ["kw", "F", "mph", "W/m^2"]:
        raise ValueError("The fixed sensor unit metadata changed")
    if any(meta[key][name]["time_interval"] != "L" for key, name in (("Meters", "Meter 0"), ("Other Instruments", "Other Instrument 0"))):
        raise ValueError("The fixed left-interval timestamp metadata changed")
    mount = meta["Mount"]["Mount 0"]
    selected = dict(id=2107, year=2022, capacity_kw=meta["System"]["power(kW DC)"], latitude=meta["Site"]["latitude"],
                    longitude=meta["Site"]["longitude"], tilt=mount["tilt"], azimuth=mount["azimuth"], timezone="PST8PDT", license="CC-BY-4.0")
    selected["sensor_metadata"] = {key: meta["Metrics"][key] for key in CHANNELS}
    selected["equipment"] = dict(module="Hyundai HiS-M310TI", inverter="ABB TRIO-27.6-TL-OUTD-S1B", inverter_count=24, mount="ground")
    selected["time_alignment"] = "left (L); unresolved DST samples excluded, never guessed"
    nasa, nasa_meta = weather.load_nasa_hourly(selected["latitude"], selected["longitude"], 2022, offline=not args.download)
    frames, completeness, invalids, sources, sampling = [], [], [], [provenance], []
    for name, columns in (("meter_15m", CHANNELS[:1]), ("environment", CHANNELS[1:3]), ("irradiance", CHANNELS[3:])):
        path, record = cached("data/2107_" + name + "_data.csv", args.download)
        frame, complete, invalid, audit = hourly(path, columns, nasa.index)
        frames.append(frame)
        completeness.append(complete)
        invalids.append(invalid)
        sources.append(record)
        sampling.append(audit)
    monthly, qc = compare(pd.concat(frames, axis=1), pd.concat(completeness, axis=1).all(axis=1),
                          pd.concat(invalids, axis=1).any(axis=1), nasa, selected)
    if (monthly.kept_hours <= 0).any() or (monthly.measured_kwh <= 0).any():
        raise ValueError("The frozen year does not provide twelve valid months")
    summary = {label: dict(mape_pct=float(monthly[label + "_ape_pct"].mean()),
        bias_pct=float((monthly[label + "_kwh"].sum() / monthly.measured_kwh.sum() - 1) * 100)) for label in ("nasa", "station")}
    FIELD.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(FIELD / "2107-monthly.csv", index_label="month", float_format="%.9f")
    record = dict(plant=selected, sources=sources, nasa=nasa_meta, sampling=sampling, qc=qc, summary=summary,
                  monthly=monthly.reset_index().to_dict("records"))
    (FIELD / "2107-metadata.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    ax = monthly[["measured_kwh", "nasa_kwh", "station_kwh"]].div(1000).plot.bar(figsize=(12, 5), rot=0)
    ax.set(xlabel="Month (UTC, 2022)", ylabel="AC energy on retained hours (MWh)", title="PVDAQ 2107: unchanged product reference model")
    ax.legend(["Measured", "NASA POWER", "Station POA inverse"])
    ax.figure.tight_layout()
    ax.figure.savefig(OUTPUT / "plant-2107.png", dpi=160)
    plt.close(ax.figure)
    keys = ["measured_kwh", "nasa_kwh", "station_kwh", "nasa_ape_pct", "station_ape_pct", "kept_hours"]
    energies = monthly[keys].copy()
    energies.columns = ["实测kWh", "NASA kWh", "电站天气kWh", "NASA APE%", "电站APE%", "保留h"]
    report = ["# PVDAQ 2107（2022）真实电站对比", "", "12 个月都有保留小时；全年偏差仅对应共同保留时段。没有调参，不设合格线。", "",
              "电站：893 kW DC，38.996306°N / 122.134111°W，固定 25°、朝南 180°；PST8PDT 转 UTC，区间中点 30 分钟。",
              "来源：[NREL PVDAQ 官方目录](https://catalog.data.gov/dataset/photovoltaic-data-acquisition-pvdaq-public-datasets)，DOI 10.25984/1846021，CC BY 4.0。",
              "[冻结清洗规则与年度覆盖审计](../../../data/field/plant/README.md)；2024 缺 12 月，模拟前按覆盖判据改用同站 2022。", "", markdown(energies), "",
              f"NASA：月度 MAPE {summary['nasa']['mape_pct']:.4f}%，保留时段全年偏差 {summary['nasa']['bias_pct']:+.4f}%。",
              f"电站天气：月度 MAPE {summary['station']['mape_pct']:.4f}%，保留时段全年偏差 {summary['station']['bias_pct']:+.4f}%。", "",
              "## 清洗数量", "", "下表原因计数可重叠；剔除总数按 union，只删除同一组小时，实测和两套模拟一致。", "",
              markdown(monthly.drop(columns=keys)), "",
              f"GTI DIRINT 回投 POA：保留日间小时 MAE {qc['poa_roundtrip_mae_w_m2']:.4f} W/m²，P95 {qc['poa_roundtrip_p95_w_m2']:.4f} W/m²。",
              "反演曾报未收敛警告，原文完整记录于元数据。没有据回投残差剔除样本；高 AOI / 天顶角≥80°由预设规则剔除。",
              "POA 回投误差衡量反演自洽，不能证明独立 GHI/DNI/DHI 精度。本站只有 POA，没有独立水平辐照实测。", "",
              f"产品系统损失固定为 {qc['loss_percent']:.12f}%；直接用 b 链，参考阵列归一化到 1 kWp 后乘 893。",
              "默认参考设备是 Trina TSM-550DE19 / Sungrow SG60CX-US，72.6 kW DC、60.182 kW AC，容配比约 1.206。",
              "实站是 Hyundai HiS-M310TI / 24 台 ABB 27.6 kW，容配比约 1.348，地面支架、设备老化与参考阵列不同；偏差不能全部归因于天气。",
              "没有显式停机或限电标志，只能筛掉 POA≥200 W/m² 且功率≤0 的停机代理；无法确认所有限电均已剔除。",
              "DST 回拨缺少完整重复时段，原采样未消歧点数见元数据 sampling，相关小时由完整采样规则剔除。", "",
              "[原始下载 URL、SHA256、采样和模型元数据](../../../data/field/plant/2107-metadata.json)；原始文件不入库。", "",
              "复跑：`python scripts/compare_plant.py --download`；已有缓存时不加参数完全离线。", "", "![月度对比](plant-2107.png)"]
    (OUTPUT / "plant-2107.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
