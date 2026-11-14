# -*- coding: utf-8 -*-
"""Run timed, reproducible local benchmark tasks (T-01, T-02, T-03) and emit output/benchmark-ledger-20261112.json."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from guangzhu import analysis, api, live_weather, project as storage, satmap_design as sat
from guangzhu.report.deliverables import write_deliverables
from guangzhu.report.pdf_generator import write_pdf_deliverables
from guangzhu.report.pvsyst_report import (
    assert_no_pvsyst_visible_text,
    build_pvsyst_report_context,
    render_pvsyst_report_html,
    render_pvsyst_report_pdf,
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(obj: object) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(raw)


def _machine_info() -> dict:
    cpu_name = platform.processor() or "unknown"
    cores = os.cpu_count()
    ram_gb = None
    try:
        ps = (
            "$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1); "
            "$cs = (Get-CimInstance Win32_ComputerSystem); "
            "@{cpu=$cpu.Name; cores=$cpu.NumberOfCores; logical=$cpu.NumberOfLogicalProcessors; "
            "ram_bytes=$cs.TotalPhysicalMemory} | ConvertTo-Json -Compress"
        )
        res = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        hw = json.loads(res.stdout.strip())
        cpu_name = hw.get("cpu") or cpu_name
        cores = hw.get("logical") or cores
        if hw.get("ram_bytes"):
            ram_gb = round(float(hw["ram_bytes"]) / (1024 ** 3), 2)
    except Exception:
        pass
    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu_model": str(cpu_name).strip(),
        "logical_processors": cores,
        "ram_gb": ram_gb,
    }


def _time_task(name: str, input_payload: object, fn, *, n_warm: int = 3) -> dict:
    in_hash = _sha256_json(input_payload)
    # Run 1 cold iteration (documented separately) + n_warm timed iterations
    cold_t0 = time.perf_counter()
    cold_res = fn(0)
    cold_s = round(time.perf_counter() - cold_t0, 4)

    warm_runs = []
    failures = 0
    last_artifacts = {}
    for idx in range(1, n_warm + 1):
        t0 = time.perf_counter()
        try:
            r = fn(idx)
            elapsed = round(time.perf_counter() - t0, 4)
            warm_runs.append({"iter": idx, "elapsed_s": elapsed, "ok": True, "summary": r.get("summary", {})})
            last_artifacts = r.get("artifacts", {})
        except Exception as exc:
            elapsed = round(time.perf_counter() - t0, 4)
            failures += 1
            warm_runs.append({"iter": idx, "elapsed_s": elapsed, "ok": False, "error": repr(exc)})

    ok_times = [r["elapsed_s"] for r in warm_runs if r["ok"]]
    return {
        "task_id": name,
        "input_sha256": in_hash,
        "cold_run_s": cold_s,
        "cold_summary": cold_res.get("summary", {}),
        "n_timed_repeats": n_warm,
        "failures": failures,
        "min_s": round(min(ok_times), 4) if ok_times else None,
        "median_s": round(statistics.median(ok_times), 4) if ok_times else None,
        "max_s": round(max(ok_times), 4) if ok_times else None,
        "runs": warm_runs,
        "artifact_sha256": last_artifacts,
    }


def main() -> None:
    run_id = datetime.now(timezone.utc).strftime("bench-%Y%m%dT%H%M%SZ")
    orig_projects_dir = storage.PROJECTS_DIR
    orig_sat_projects_dir = sat.PROJECTS_DIR
    orig_api_root = api.ROOT
    orig_lw_dir = live_weather.LIVE_CACHE_DIR

    t01_payload = {
        "name": "76m×36m双坡厂房基准(T-01)",
        "lat": 32.45,
        "lon": 119.91,
        "roof": {
            "type": "double_slope",
            "slope_deg": 6.0,
            "polygon_m": [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]],
            "obstacles": [
                {"id": "sky-1", "kind": "prism", "height_m": 0.4, "footprint": [[-20, -2], [20, -2], [20, 0], [-20, 0]], "keepout": True},
                {"id": "sky-2", "kind": "prism", "height_m": 0.4, "footprint": [[-20, 4], [20, 4], [20, 6], [-20, 6]], "keepout": True},
            ],
        },
        "module_id": "jinko-jkm580n-72hl4-bdv",
        "inverter_id": "sungrow-sg110cx-p2",
        "layout_params": {"orientation": "portrait", "row_spacing_m": 0.25, "edge_setback_m": 0.6, "tilt_deg": 6.0, "azimuth_deg": 180.0},
        "system": {"walkway_width_m": 0.8},
        "offline": True,
    }

    with tempfile.TemporaryDirectory(prefix="gz-bench-20261112-") as tmp:
        tmp_root = Path(tmp)
        proj_dir = tmp_root / "projects"
        proj_dir.mkdir(parents=True, exist_ok=True)
        lw_dir = tmp_root / "live_weather"
        lw_dir.mkdir(parents=True, exist_ok=True)
        storage.PROJECTS_DIR = proj_dir
        sat.PROJECTS_DIR = proj_dir
        api.ROOT = tmp_root
        live_weather.LIVE_CACHE_DIR = lw_dir

        try:
            # T-01: 76m x 36m dual-slope satmap_design + CAD/DXF export + 6-page Pro Report PDF
            def run_t01(idx: int) -> dict:
                res = sat.run_satmap_design(dict(t01_payload))
                dxf_bytes = sat.export_satmap_dxf(res, "all")
                drawings = sat.generate_four_cad_drawings(res)
                ctx = build_pvsyst_report_context(payload={**t01_payload, "summary": res["summary"], "modules": res["modules"], "financial_dcf": res["financial_dcf"], "mppt_table": res["mppt_table"], "structural_check": res["structural_check"]}, offline=True)
                pdf_p = tmp_root / f"t01_{idx}_pro.pdf"
                render_pvsyst_report_pdf(ctx, pdf_p)
                return {
                    "summary": {
                        "modules": res["summary"]["module_count"],
                        "dc_kw": res["summary"]["dc_kw"],
                        "cad_sheets": len(res.get("cad_drawings") or {}),
                        "four_svg_sheets": len(drawings.get("sheets") or []),
                        "dxf_bytes": len(dxf_bytes),
                        "pro_pdf_bytes": pdf_p.stat().st_size,
                    },
                    "artifacts": {
                        "satmap_all.dxf": _sha256_bytes(dxf_bytes),
                        "pro_report_6p.pdf": _sha256_bytes(pdf_p.read_bytes()),
                    },
                }

            t01_rec = _time_task("T-01", t01_payload, run_t01, n_warm=3)
            t01_rec["boundary"] = "SatMap 76m×36m dual-slope+2 keepouts: run_satmap_design(layout+MPPT+8760h+16-sheet CAD) + export_satmap_dxf + 6p Pro Report PDF; offline=True, excludes human polygon tracing."
            t01_rec["token_cost_cny"] = 0.0
            t01_rec["execution_track"] = "offline_deterministic_compute"

            # T-02: High-low factory rule iteration & 3D shading analysis + v1->v2 rule repair
            src_xiangtai = ROOT / "projects" / "taizhou-xiangtai-warehouse"
            t02_input_meta = {"source_project": "taizhou-xiangtai-warehouse", "base_version": 1, "prune_op": "remove_over_s01_8pct"}

            def run_t02(idx: int) -> dict:
                pid = f"bench-xiangtai-{idx}"
                dst = proj_dir / pid
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src_xiangtai / "designs", dst / "designs")
                shutil.copy2(src_xiangtai / "project.json", dst / "project.json")
                pj = json.loads((dst / "project.json").read_text("utf-8"))
                pj["id"] = pid
                (dst / "project.json").write_text(json.dumps(pj, ensure_ascii=False, indent=2), encoding="utf-8")

                an1 = analysis.analyze(pid, 1, offline=True)
                sh1 = json.loads((dst / "analysis" / "v1" / "shading.json").read_text("utf-8"))
                over = [m["id"] for m in sh1.get("modules", []) if float(m.get("total_loss_pct") or 0.0) > 8.0]
                v2_ver = 1
                if over:
                    ed = storage.edit_design(pid, 1, [{"op": "remove_modules", "module_ids": over}], "Prune S01 >8% shaded modules", "rule", offline=True)
                    v2_ver = ed["version"]
                an2 = analysis.analyze(pid, v2_ver, offline=True)
                return {
                    "summary": {
                        "v1_modules": an1["modules"],
                        "v1_hard_failed": an1["rules"]["hard_failed"],
                        "pruned_count": len(over),
                        "v2_version": v2_ver,
                        "v2_modules": an2["modules"],
                        "v2_hard_failed": an2["rules"]["hard_failed"],
                    },
                    "artifacts": {
                        "v2_summary.json": _sha256_bytes((dst / f"analysis/v{v2_ver}/summary.json").read_bytes()),
                        "v2_rules.json": _sha256_bytes((dst / f"analysis/v{v2_ver}/rules.json").read_bytes()),
                    },
                }

            t02_rec = _time_task("T-02", t02_input_meta, run_t02, n_warm=3)
            t02_rec["boundary"] = "Xiangtai high-low 3D factory cloned v1 -> analysis.analyze(v1) + deterministic S01>8% rule prune -> v2 + analysis.analyze(v2); offline rule chain only (online AGH multi-turn LLM billed separately, pending live API run)."
            t02_rec["token_cost_cny"] = 0.0
            t02_rec["execution_track"] = "offline_deterministic_rule_chain"
            t02_rec["online_agh_llm_note"] = "Online AGH dual-session API token ledger pending live metered run; not bundled into offline timing."

            # T-03: Same-version full deliverables export (DXF + XLSX BOM + 23p report PDF + drawing PDF + 6p Pro Report PDF)
            # Prepare analyzed v2 once for pure export benchmark
            t03_pid = "bench-t03-xiangtai"
            dst3 = proj_dir / t03_pid
            shutil.copytree(src_xiangtai / "designs", dst3 / "designs")
            shutil.copy2(src_xiangtai / "project.json", dst3 / "project.json")
            pj3 = json.loads((dst3 / "project.json").read_text("utf-8"))
            pj3["id"] = t03_pid
            (dst3 / "project.json").write_text(json.dumps(pj3, ensure_ascii=False, indent=2), encoding="utf-8")
            analysis.analyze(t03_pid, 1, offline=True)
            sh3 = json.loads((dst3 / "analysis" / "v1" / "shading.json").read_text("utf-8"))
            over3 = [m["id"] for m in sh3.get("modules", []) if float(m.get("total_loss_pct") or 0.0) > 8.0]
            t03_ver = 1
            if over3:
                t03_ver = storage.edit_design(t03_pid, 1, [{"op": "remove_modules", "module_ids": over3}], "T-03 prepare v2", "rule", offline=True)["version"]
            analysis.analyze(t03_pid, t03_ver, offline=True)

            def run_t03(idx: int) -> dict:
                exp_dir = tmp_root / f"t03_exp_{idx}"
                exp_dir.mkdir(parents=True, exist_ok=True)
                files = write_deliverables(t03_pid, t03_ver, exp_dir, base_dir=dst3)
                pdfs = write_pdf_deliverables(t03_pid, t03_ver, exp_dir, base_dir=dst3)
                proj_res = api.result_data(t03_pid, t03_ver)
                ctx = build_pvsyst_report_context({"project_id": t03_pid, "version": t03_ver, "system": {"walkway_width_m": 0.8}}, project_result=proj_res, offline=True)
                html = render_pvsyst_report_html(ctx)
                assert_no_pvsyst_visible_text(html)
                pro_pdf = exp_dir / f"guangzhu-pro-v{t03_ver}.pdf"
                render_pvsyst_report_pdf(ctx, pro_pdf)
                arts = {k: _sha256_bytes((exp_dir / k).read_bytes()) for k in files if (exp_dir / k).is_file()}
                for pk, pp in pdfs.items():
                    arts[pp.name] = _sha256_bytes(pp.read_bytes())
                arts[pro_pdf.name] = _sha256_bytes(pro_pdf.read_bytes())
                return {
                    "summary": {
                        "version": t03_ver,
                        "files": sorted(arts.keys()),
                        "pro_pdf_bytes": pro_pdf.stat().st_size,
                    },
                    "artifacts": arts,
                }

            t03_rec = _time_task("T-03", {"project": "taizhou-xiangtai-warehouse", "version": t03_ver}, run_t03, n_warm=3)
            t03_rec["boundary"] = "Same-version export from analyzed v2: write_deliverables (DXF+XLSX) + write_pdf_deliverables (preliminary PDF + drawing PDF) + 6p 光筑专业报告 PDF."
            t03_rec["token_cost_cny"] = 0.0
            t03_rec["execution_track"] = "offline_deterministic_export"

            ledger = {
                "run_id": run_id,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "machine": _machine_info(),
                "methodology": "Isolated TemporaryDirectory per execution; 1 uncached cold run + N=3 timed runs per task; offline=True; human manual operation baseline not executed here (marked pending independent engineer timing).",
                "tasks": [t01_rec, t02_rec, t03_rec],
            }
            out_path = ROOT / "output" / "benchmark-ledger-20261112.json"
            out_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote {out_path} ({run_id})")
            for t in ledger["tasks"]:
                print(f"  {t['task_id']}: cold={t['cold_run_s']}s, warm_median={t['median_s']}s (min={t['min_s']}s, max={t['max_s']}s), failures={t['failures']}")
        finally:
            storage.PROJECTS_DIR = orig_projects_dir
            sat.PROJECTS_DIR = orig_sat_projects_dir
            api.ROOT = orig_api_root
            live_weather.LIVE_CACHE_DIR = orig_lw_dir


if __name__ == "__main__":
    main()

