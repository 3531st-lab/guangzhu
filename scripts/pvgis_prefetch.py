"""Cache weather and exact PVGIS angles for demo and evaluation roofs; no model calls."""
import argparse
import json
from pathlib import Path
import sys

from guangzhu import economics, weather, yieldsim
from guangzhu.config import ROOT
from guangzhu.models import Project, validated
from guangzhu.templates import catalog


def prefetch(offline=False):
    targets, sites = set(), set()
    for path in catalog(all=True, root=ROOT).values():
        record = validated(Project, json.loads(path.read_text(encoding="utf-8")))
        sites.add((record.site.lat, record.site.lon))
        angles = {0, 5, 10, 15, 20, 25, 30, 35}
        if record.requirements.structured.tilt_deg_range:
            angles.update(record.requirements.structured.tilt_deg_range)
        targets.update((record.site.lat, record.site.lon, tilt, 180) for tilt in angles)
    loss = economics.load_assumptions()["design_system_loss_pct"]["value"]
    records = []
    weather_records = []
    for lat, lon in sorted(sites):
        _, nasa = weather.load_nasa_hourly(lat, lon, 2023, offline=offline)
        _, tmy = weather.load_pvgis_tmy(lat, lon, offline=offline)
        extremes = weather.load_nasa_daily_extremes(lat, lon, start_year=1996, end_year=2025, offline=offline)
        weather_records.append(dict(lat=lat, lon=lon, nasa=nasa, tmy=tmy, extremes=extremes["metadata"]))
    for lat, lon, tilt, azimuth in sorted(targets):
        result = yieldsim.load_pvgis_result(lat, lon, tilt=tilt, azimuth=azimuth, loss=loss, offline=offline)
        records.append(dict(lat=lat, lon=lon, tilt=tilt, azimuth=azimuth, loss_percent=loss,
                            annual_kwh=result["annual_kwh"], metadata=result["metadata"]))
    return dict(ok=True, model_requests=0, agh_modified=False, records=records, weather=weather_records)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/assets/T08-r1-prefetch.json")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        result = prefetch(offline=args.offline)
    except (OSError, ValueError, weather.WeatherDataError):
        print("预取失败：检查天气和PVGIS响应，缓存未就绪时不要开始批量评测。")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(dict(ok=True, cached_angles=[r["tilt"] for r in result["records"]], output=str(args.output)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
