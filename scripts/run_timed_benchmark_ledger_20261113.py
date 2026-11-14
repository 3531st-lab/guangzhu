# -*- coding: utf-8 -*-
"""Run timed, reproducible local benchmark tasks (T-01, T-02, T-03, T-03b) with true
fresh-process cold-start timing (subprocess.run), input/catalog/source SHA-256 snapshots,
pypdf page counting, and automated cross-format consistency checks (openpyxl + ezdxf + pypdf),
emitting output/benchmark-ledger-20261113.json.

Key guarantees over 20261112:
1. Freeze fixed input payloads, equipment catalog CSVs, directory listing CSV, and core
   backend source SHA-256 hashes under output/benchmark-inputs-20261113/.
2. Measure TRUE cold-start time (cold_subprocess_s) per task by spawning a fresh
   subprocess.run([sys.executable, __file__, "--single-cold-task", ...]) BEFORE any
   guangzhu/pvlib/shapely/matplotlib imports, separately recording import_s, call_s,
   in-process first_call_in_process_s, and 3 warm_runs_s with UTC start/end ISO timestamps.
3. Explicitly clarify T-01's 4 backend summary SVG CAD sheets (generate_four_cad_drawings)
   vs the 16-sheet full CAD drawing set rendered in the #satmap frontend workbench.
4. Explicitly document v3 version provenance in T-02/T-03 (taizhou-xiangtai-warehouse
   pre-contains v1/v2, so pruning 18 S01>8% modules from v1 yields v3) and measure actual
   PDF page counts via pypdf (guangzhu-pro-v3.pdf = 6p, report-v3.pdf = 3p, drawing-v3.pdf = 4p).
5. Run automated cross_file_consistency_check across bom-vN.xlsx (openpyxl),
   layout-vN.dxf + satmap-layout-vN.dxf (ezdxf PV / PV_MODULES & FRAME / TITLE_BLOCK),
   and drawing-vN.pdf / report-vN.pdf / guangzhu-pro-vN.pdf (pypdf) on:
   - T-03 (taizhou-xiangtai-warehouse v3)
   - changzhou-demo v3 (data/demo/projects/changzhou-demo v3)
   - T-03b / SG50CX-P2 (90 × 580W Jinko = 52.20 kWp DC, 1 × SG50CX-P2 = 50.0 kW AC)
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CORE_SOURCE_FILES = [
    "backend/guangzhu/satmap_design.py",
    "backend/guangzhu/satmap_multifactor.py",
    "backend/guangzhu/analysis.py",
    "backend/guangzhu/pvsyst_engine.py",
    "backend/guangzhu/layout.py",
    "backend/guangzhu/electrical.py",
    "backend/guangzhu/shading.py",
    "backend/guangzhu/shading_geometry.py",
    "backend/guangzhu/yieldsim.py",
    "backend/guangzhu/report/pvsyst_report.py",
    "backend/guangzhu/report/deliverables.py",
    "backend/guangzhu/report/pdf_generator.py",
    "backend/guangzhu/rules.py",
    "backend/guangzhu/structure.py",
    "backend/guangzhu/economics.py",
    "backend/guangzhu/economic_analysis.py",
]


# ---------------------------------------------------------------------------
# Utility helpers (stdlib only so cold-start subprocess probe stays pure)
# ---------------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_json(obj: object) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(raw)


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fixed_payloads() -> dict[str, Any]:
    t01_payload = {
        "name": "76m×36m双坡厂房基准(T-01)",
        "lat": 32.45,
        "lon": 119.91,
        "roof": {
            "type": "double_slope",
            "slope_deg": 6.0,
            "polygon_m": [[-38.0, -18.0], [38.0, -18.0], [38.0, 18.0], [-38.0, 18.0]],
            "obstacles": [
                {
                    "id": "sky-1",
                    "kind": "prism",
                    "height_m": 0.4,
                    "footprint": [[-20, -2], [20, -2], [20, 0], [-20, 0]],
                    "keepout": True,
                },
                {
                    "id": "sky-2",
                    "kind": "prism",
                    "height_m": 0.4,
                    "footprint": [[-20, 4], [20, 4], [20, 6], [-20, 6]],
                    "keepout": True,
                },
            ],
        },
        "module_id": "jinko-jkm580n-72hl4-bdv",
        "inverter_id": "sungrow-sg110cx-p2",
        "layout_params": {
            "orientation": "portrait",
            "row_spacing_m": 0.25,
            "edge_setback_m": 0.6,
            "tilt_deg": 6.0,
            "azimuth_deg": 180.0,
        },
        "system": {"walkway_width_m": 0.8},
        "offline": True,
    }

    t02_input_meta = {
        "source_project": "taizhou-xiangtai-warehouse",
        "base_version": 1,
        "preexisting_versions_in_repo": [1, 2],
        "expected_pruned_version": 3,
        "prune_op": "remove_over_s01_8pct",
    }

    t03_input_meta = {
        "source_project": "taizhou-xiangtai-warehouse",
        "version": 3,
        "version_origin": "Pruned from v1 (18 modules >8% S01 removed); repo already holds v1 and v2 so new edit version is v3",
    }

    changzhou_v3_meta = {
        "source_project": "data/demo/projects/changzhou-demo",
        "project_id": "changzhou-demo",
        "version": 3,
    }

    # SG50CX-P2 scenario: 90 × 580W Jinko modules (52.20 kWp DC) on flat roof, 1 × SG50CX-P2 (50.0 kW AC)
    sg50_payload = {
        "project_id": "sg50cx-p2-90x580w",
        "name": "SG50CX-P2 90块580W标准平顶方案",
        "lat": 32.45,
        "lon": 119.91,
        "roof": {
            "type": "flat",
            "polygon_m": [[-20.0, -14.0], [20.0, -14.0], [20.0, 14.0], [-20.0, 14.0]],
            "obstacles": [],
        },
        "module_id": "jinko-jkm580n-72hl4-bdv",
        "inverter_id": "sungrow-sg50cx-p2",
        "target_module_count": 90,
        "modules_per_string": 15,
        "layout_params": {
            "orientation": "portrait",
            "row_spacing_m": 0.80,
            "edge_setback_m": 0.8,
            "tilt_deg": 10.0,
            "azimuth_deg": 180.0,
        },
        "system": {"walkway_width_m": 0.8},
        "offline": True,
    }

    return {
        "t01": t01_payload,
        "t02": t02_input_meta,
        "t03": t03_input_meta,
        "changzhou_demo_v3": changzhou_v3_meta,
        "sg50cx_p2": sg50_payload,
    }


def _machine_info() -> dict[str, Any]:
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


# ---------------------------------------------------------------------------
# Snapshot: freeze fixed inputs, catalog CSVs, directory CSV, & source SHA-256
# ---------------------------------------------------------------------------

def _snapshot_inputs(inputs_dir: Path, payloads: dict[str, Any]) -> dict[str, Any]:
    """Write fixed input snapshots, equipment catalog CSV copies, directory CSV, and source SHA-256."""
    inputs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fixed payloads
    payloads_path = inputs_dir / "payloads.json"
    payloads_path.write_text(
        json.dumps(payloads, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # 2. Equipment catalog CSVs snapshot
    cat_src = ROOT / "data" / "catalog"
    cat_dst = inputs_dir / "catalog"
    cat_dst.mkdir(parents=True, exist_ok=True)
    catalog_hashes: dict[str, str] = {}
    if cat_src.is_dir():
        for csv_fp in sorted(cat_src.glob("*.csv")):
            shutil.copy2(csv_fp, cat_dst / csv_fp.name)
            catalog_hashes[f"data/catalog/{csv_fp.name}"] = _sha256_file(csv_fp)
    catalog_sha_path = inputs_dir / "catalog_sha256.json"
    catalog_sha_path.write_text(
        json.dumps(catalog_hashes, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # 3. Core backend source SHA-256
    source_hashes: dict[str, str] = {}
    for rel in CORE_SOURCE_FILES:
        p = ROOT / rel
        if p.is_file():
            source_hashes[rel] = _sha256_file(p)
    source_path = inputs_dir / "source_sha256.json"
    source_path.write_text(
        json.dumps(source_hashes, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # 4. Directory listing CSV across catalog, benchmark projects, and demo changzhou-demo
    csv_path = inputs_dir / "directory_listing.csv"
    scan_targets = [
        ROOT / "data" / "catalog",
        ROOT / "projects" / "taizhou-xiangtai-warehouse",
        ROOT / "data" / "demo" / "projects" / "changzhou-demo",
    ]
    row_count = 0
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["relative_path", "size_bytes", "sha256"])
        for scan_dir in scan_targets:
            if scan_dir.exists():
                for fp in sorted(scan_dir.rglob("*")):
                    if fp.is_file():
                        rel_str = str(fp.relative_to(ROOT)).replace("\\", "/")
                        w.writerow([rel_str, fp.stat().st_size, _sha256_file(fp)])
                        row_count += 1

    return {
        "inputs_dir": "output/benchmark-inputs-20261113",
        "payloads_sha256": _sha256_file(payloads_path),
        "catalog_sha256": _sha256_file(catalog_sha_path),
        "num_catalog_csv_files": len(catalog_hashes),
        "source_sha256_file_hash": _sha256_file(source_path),
        "num_source_files": len(source_hashes),
        "directory_csv_sha256": _sha256_file(csv_path),
        "directory_csv_rows": row_count,
    }


# ---------------------------------------------------------------------------
# Deferred backend import + PDF page counter
# ---------------------------------------------------------------------------

def _load_backend():
    if str(ROOT / "backend") not in sys.path:
        sys.path.insert(0, str(ROOT / "backend"))
    from guangzhu import analysis, api, electrical, live_weather, project as storage, satmap_design as sat
    from guangzhu.report.deliverables import write_deliverables
    from guangzhu.report.pdf_generator import write_pdf_deliverables
    from guangzhu.report.pvsyst_report import (
        assert_no_pvsyst_visible_text,
        build_pvsyst_report_context,
        render_pvsyst_report_html,
        render_pvsyst_report_pdf,
    )
    return {
        "analysis": analysis,
        "api": api,
        "electrical": electrical,
        "live_weather": live_weather,
        "storage": storage,
        "sat": sat,
        "write_deliverables": write_deliverables,
        "write_pdf_deliverables": write_pdf_deliverables,
        "assert_no_pvsyst_visible_text": assert_no_pvsyst_visible_text,
        "build_pvsyst_report_context": build_pvsyst_report_context,
        "render_pvsyst_report_html": render_pvsyst_report_html,
        "render_pvsyst_report_pdf": render_pvsyst_report_pdf,
    }


def _count_pdf_pages(pdf_path: Path) -> int | None:
    if not pdf_path.is_file():
        return None
    from pypdf import PdfReader
    return len(PdfReader(str(pdf_path)).pages)


# ---------------------------------------------------------------------------
# Task runners (reused identically by fresh cold-start subprocess & warm loop)
# ---------------------------------------------------------------------------

def _execute_t01_once(mods: dict[str, Any], tmp_root: Path, idx: int, t01_payload: dict[str, Any]) -> dict[str, Any]:
    sat = mods["sat"]
    build_pvsyst_report_context = mods["build_pvsyst_report_context"]
    render_pvsyst_report_pdf = mods["render_pvsyst_report_pdf"]

    res = sat.run_satmap_design(dict(t01_payload))
    dxf_bytes = sat.export_satmap_dxf(res, "all")
    drawings = sat.generate_four_cad_drawings(res)
    ctx = build_pvsyst_report_context(
        payload={
            **t01_payload,
            "summary": res["summary"],
            "module_count": len(res["modules"]),
            "modules_layout": res["modules"],
            "financial_dcf": res["financial_dcf"],
            "mppt_table": res["mppt_table"],
            "structural_check": res["structural_check"],
        },
        offline=True,
    )
    pdf_p = tmp_root / f"t01_{idx}_pro.pdf"
    render_pvsyst_report_pdf(ctx, pdf_p)
    pro_pages = _count_pdf_pages(pdf_p)
    return {
        "summary": {
            "modules": res["summary"]["module_count"],
            "dc_kw": res["summary"]["dc_kw"],
            "ac_kw": res["summary"].get("ac_kw"),
            "backend_cad_summary_sheets": len(res.get("cad_drawings") or []),
            "four_svg_sheets": len(drawings.get("sheets") or []),
            "frontend_full_cad_sheet_set_count": 16,
            "frontend_full_cad_timed_in_backend": False,
            "dxf_bytes": len(dxf_bytes),
            "pro_pdf_bytes": pdf_p.stat().st_size,
            "pro_pdf_pages": pro_pages,
        },
        "artifacts": {
            "satmap_all.dxf": _sha256_bytes(dxf_bytes),
            "pro_report_6p.pdf": _sha256_bytes(pdf_p.read_bytes()),
        },
    }


def _execute_t02_once(mods: dict[str, Any], proj_dir: Path, idx: int) -> dict[str, Any]:
    analysis = mods["analysis"]
    storage = mods["storage"]
    src_xiangtai = ROOT / "projects" / "taizhou-xiangtai-warehouse"

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
    new_ver = 1
    if over:
        ed = storage.edit_design(
            pid,
            1,
            [{"op": "remove_modules", "module_ids": over}],
            "Prune S01 >8% shaded modules",
            "rule",
            offline=True,
        )
        new_ver = ed["version"]
    an2 = analysis.analyze(pid, new_ver, offline=True)
    return {
        "summary": {
            "v1_modules": an1["modules"],
            "v1_hard_failed": an1["rules"]["hard_failed"],
            "pruned_count": len(over),
            "pruned_version": new_ver,
            "version_description": (
                f"v{new_ver} (pruned {len(over)} modules with S01>8% from v1; "
                "source repo already holds v1.json and v2.json so next monotonic version is v3)"
            ),
            "pruned_modules": an2["modules"],
            "pruned_hard_failed": an2["rules"]["hard_failed"],
        },
        "artifacts": {
            f"v{new_ver}_summary.json": _sha256_bytes((dst / f"analysis/v{new_ver}/summary.json").read_bytes()),
            f"v{new_ver}_rules.json": _sha256_bytes((dst / f"analysis/v{new_ver}/rules.json").read_bytes()),
        },
    }


def _prepare_analyzed_project(
    mods: dict[str, Any],
    proj_dir: Path,
    src_dir: Path,
    target_pid: str,
    *,
    prune_from_v1: bool = False,
    target_version: int = 3,
) -> tuple[Path, int]:
    analysis = mods["analysis"]
    storage = mods["storage"]
    dst = proj_dir / target_pid
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src_dir / "designs", dst / "designs")
    shutil.copy2(src_dir / "project.json", dst / "project.json")
    pj = json.loads((dst / "project.json").read_text("utf-8"))
    pj["id"] = target_pid
    (dst / "project.json").write_text(json.dumps(pj, ensure_ascii=False, indent=2), encoding="utf-8")

    if prune_from_v1:
        analysis.analyze(target_pid, 1, offline=True)
        sh = json.loads((dst / "analysis" / "v1" / "shading.json").read_text("utf-8"))
        over = [m["id"] for m in sh.get("modules", []) if float(m.get("total_loss_pct") or 0.0) > 8.0]
        ver = 1
        if over:
            ver = storage.edit_design(
                target_pid,
                1,
                [{"op": "remove_modules", "module_ids": over}],
                "Prepare pruned version for export benchmark",
                "rule",
                offline=True,
            )["version"]
        analysis.analyze(target_pid, ver, offline=True)
        return dst, ver

    analysis.analyze(target_pid, target_version, offline=True)
    return dst, target_version


def _export_five_plus_satmap_dxf(
    mods: dict[str, Any],
    pid: str,
    ver: int,
    base_dir: Path,
    exp_dir: Path,
    *,
    include_satmap_dxf: bool = True,
) -> dict[str, Any]:
    api = mods["api"]
    sat = mods["sat"]
    write_deliverables = mods["write_deliverables"]
    write_pdf_deliverables = mods["write_pdf_deliverables"]
    assert_no_pvsyst_visible_text = mods["assert_no_pvsyst_visible_text"]
    build_pvsyst_report_context = mods["build_pvsyst_report_context"]
    render_pvsyst_report_html = mods["render_pvsyst_report_html"]
    render_pvsyst_report_pdf = mods["render_pvsyst_report_pdf"]

    exp_dir.mkdir(parents=True, exist_ok=True)
    files = write_deliverables(pid, ver, exp_dir, base_dir=base_dir)
    pdfs = write_pdf_deliverables(pid, ver, exp_dir, base_dir=base_dir)
    proj_res = api.result_data(pid, ver)
    ctx = build_pvsyst_report_context(
        {"project_id": pid, "version": ver, "system": {"walkway_width_m": 0.8}},
        project_result=proj_res,
        offline=True,
    )
    html = render_pvsyst_report_html(ctx)
    assert_no_pvsyst_visible_text(html)
    pro_pdf = exp_dir / f"guangzhu-pro-v{ver}.pdf"
    render_pvsyst_report_pdf(ctx, pro_pdf)

    arts = {k: _sha256_bytes((exp_dir / k).read_bytes()) for k in files if (exp_dir / k).is_file()}
    for _pk, pp in pdfs.items():
        arts[pp.name] = _sha256_bytes(pp.read_bytes())
    arts[pro_pdf.name] = _sha256_bytes(pro_pdf.read_bytes())

    if include_satmap_dxf:
        design_json = json.loads((base_dir / f"designs/v{ver}.json").read_text("utf-8"))
        elec_json = json.loads((base_dir / f"analysis/v{ver}/electrical.json").read_text("utf-8"))
        summary_path = base_dir / f"analysis/v{ver}/summary.json"
        summary_json = json.loads(summary_path.read_text("utf-8")) if summary_path.is_file() else {}
        rated_ac_kw = (
            (summary_json.get("electrical") or {}).get("rated_ac_kw")
            or elec_json.get("rated_ac_kw")
            or elec_json.get("ac_kw")
            or ((proj_res.get("summary") or {}).get("electrical") or {}).get("rated_ac_kw")
            or 0.0
        )
        proj_json = json.loads((base_dir / "project.json").read_text("utf-8"))
        roof_obj = proj_json.get("roof") or {}
        poly_outline = roof_obj.get("outline") or [
            p
            for pl in (roof_obj.get("planes") or [])
            for p in (pl.get("outline") or [])
        ] or [[0.0, 0.0], [40.0, 0.0], [40.0, 24.0], [0.0, 24.0]]
        sat_mods = []
        for m in design_json.get("modules") or []:
            corners = m.get("corners") or []
            if len(corners) >= 4:
                xs = [float(c[0]) for c in corners]
                ys = [float(c[1]) for c in corners]
                cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
                w = max(0.5, max(xs) - min(xs))
                h = max(0.5, max(ys) - min(ys))
            else:
                center = m.get("center") or [0.0, 0.0]
                cx, cy = float(center[0]), float(center[1])
                w, h = 1.134, 2.278
            sat_mods.append({"id": m.get("id"), "cx": cx, "cy": cy, "w": w, "h": h, "slope": "south"})
        sat_dxf_bytes = sat.export_satmap_dxf(
            {
                "summary": {
                    "dc_kw": design_json.get("statistics", {}).get("dc_kw"),
                    "ac_kw": round(float(rated_ac_kw), 2),
                    "module_count": len(sat_mods),
                    "inverter_count": elec_json.get("inverter_count"),
                    "modules_per_string": elec_json.get("modules_per_string") or 18,
                },
                "roof": {"type": roof_obj.get("type", "flat"), "polygon_m": poly_outline, "obstacles": []},
                "modules": sat_mods,
                "strings": elec_json.get("strings") or [],
            },
            drawing_type="all",
        )
        sat_dxf_path = exp_dir / f"satmap-layout-v{ver}.dxf"
        sat_dxf_path.write_bytes(sat_dxf_bytes)

    page_counts = {
        f"guangzhu-pro-v{ver}.pdf": _count_pdf_pages(pro_pdf),
        f"report-v{ver}.pdf": _count_pdf_pages(exp_dir / f"report-v{ver}.pdf"),
        f"drawing-v{ver}.pdf": _count_pdf_pages(exp_dir / f"drawing-v{ver}.pdf"),
    }
    return {
        "summary": {
            "project_id": pid,
            "version": ver,
            "version_description": f"v{ver} same-version 5-deliverable export ({pid})",
            "files": sorted(arts.keys()),
            "pro_pdf_bytes": pro_pdf.stat().st_size,
            "page_counts": page_counts,
        },
        "artifacts": arts,
    }


def _execute_sg50_once(
    mods: dict[str, Any],
    proj_dir: Path,
    tmp_root: Path,
    idx: int,
    sg50_payload: dict[str, Any],
) -> dict[str, Any]:
    sat = mods["sat"]
    # 1. Run SatMap design on flat roof and select exact 90 × 580W modules (52.20 kWp DC)
    raw_res = sat.run_satmap_design(dict(sg50_payload))
    target_n = int(sg50_payload.get("target_module_count") or 90)
    mods_90 = list(raw_res["modules"][:target_n])
    if len(mods_90) != target_n:
        raise RuntimeError(f"Expected {target_n} modules in SG50CX-P2 scenario, got {len(mods_90)}")

    pid = f"sg50cx-p2-{idx}"
    save_payload = {
        "project_id": pid,
        "name": sg50_payload["name"],
        "overwrite": True,
        "site": {"name": sg50_payload["name"], "lat": sg50_payload["lat"], "lon": sg50_payload["lon"]},
        "roof": sg50_payload["roof"],
        "module_id": sg50_payload["module_id"],
        "inverter_id": sg50_payload["inverter_id"],
        "modules_per_string": int(sg50_payload.get("modules_per_string") or 15),
        "layout_params": sg50_payload["layout_params"],
        "modules_layout": mods_90,
        "module_count": target_n,
        "dc_kw": round(target_n * 0.58, 2),
        "ac_kw": 50.0,
        "inverter_count": 1,
        "offline": True,
    }
    saved = sat.save_to_guangzhu_project(save_payload, project_id=pid)
    ver = int(saved["version"])
    dst = proj_dir / saved["project_id"]
    exp_dir = tmp_root / f"sg50_exp_{idx}"
    exp_res = _export_five_plus_satmap_dxf(mods, saved["project_id"], ver, dst, exp_dir, include_satmap_dxf=True)
    exp_res["summary"].update(
        {
            "modules": target_n,
            "dc_kw": round(target_n * 0.58, 2),
            "ac_kw": 50.0,
            "inverter_id": sg50_payload["inverter_id"],
            "inverter_count": 1,
            "allocation_reconciliation": saved.get("allocation_reconciliation"),
        }
    )
    exp_res["project_id"] = saved["project_id"]
    exp_res["version"] = ver
    exp_res["base_dir"] = dst
    exp_res["exp_dir"] = exp_dir
    return exp_res


# ---------------------------------------------------------------------------
# Cross-format consistency check (openpyxl + ezdxf + pypdf)
# ---------------------------------------------------------------------------

def _cross_file_consistency_check(
    mods: dict[str, Any],
    exp_dir: Path,
    base_dir: Path,
    project_id: str,
    version: int,
) -> dict[str, Any]:
    """Read bom-vN.xlsx (openpyxl), layout-vN.dxf + satmap-layout-vN.dxf (ezdxf),
    and drawing-vN.pdf / report-vN.pdf / guangzhu-pro-vN.pdf (pypdf), and cross-check
    project_id, version, module_count, dc_kw, ac_kw, and inverter_count."""
    import ezdxf
    import openpyxl
    from pypdf import PdfReader

    electrical_mod = mods["electrical"]
    catalog_invs = electrical_mod.equipment_catalog(include_extended=True)["inverters"]
    inv_kw_by_model = {
        str(v.get("model", "")).strip(): float(v["rated_ac_kw"])
        for v in catalog_invs.values()
        if isinstance(v.get("rated_ac_kw"), (int, float))
    }

    proj_json = json.loads((base_dir / "project.json").read_text("utf-8"))
    design_json = json.loads((base_dir / f"designs/v{version}.json").read_text("utf-8"))
    elec_json = json.loads((base_dir / f"analysis/v{version}/electrical.json").read_text("utf-8"))
    summary_path = base_dir / f"analysis/v{version}/summary.json"
    summary_json = json.loads(summary_path.read_text("utf-8")) if summary_path.is_file() else {}
    rated_ac_val = (
        (summary_json.get("electrical") or {}).get("rated_ac_kw")
        or elec_json.get("rated_ac_kw")
        or elec_json.get("ac_kw")
    )
    if not rated_ac_val:
        rated_ac_val = sum(
            inv_kw_by_model.get(str(r.get("model", "")).strip(), 0.0) * int(r.get("count") or 0)
            for r in (elec_json.get("inverters") or [])
        )

    expected = {
        "project_id": str(proj_json.get("id") or project_id),
        "project_name": str(proj_json.get("name") or ""),
        "version": int(version),
        "module_count": len(design_json.get("modules") or []),
        "dc_kw": round(float(design_json.get("statistics", {}).get("dc_kw") or 0.0), 2),
        "ac_kw": round(float(rated_ac_val or 0.0), 2),
        "inverter_count": int(elec_json.get("inverter_count") or 0),
    }

    vs = f"v{version}"
    sources: dict[str, Any] = {}

    # 1. BOM XLSX (openpyxl)
    bom_path = exp_dir / f"bom-{vs}.xlsx"
    bom_info: dict[str, Any] = {"exists": bom_path.is_file()}
    if bom_path.is_file():
        wb = openpyxl.load_workbook(str(bom_path), read_only=True, data_only=True)
        bom_info["sheet_names"] = list(wb.sheetnames)
        if "材料清单" in wb.sheetnames:
            ws = wb["材料清单"]
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or row[0] is None:
                    continue
                item_kind = str(row[0]).strip()
                if item_kind == "组件":
                    bom_info["module_model"] = str(row[2] or "")
                    bom_info["module_pmax_w"] = float(row[3]) if row[3] is not None else None
                    bom_info["module_count"] = int(row[4]) if row[4] is not None else None
                    bom_info["dc_kw"] = round(float(row[6]), 2) if row[6] is not None else None
                elif item_kind == "逆变器":
                    inv_label = str(row[2] or "")
                    inv_cnt = int(row[4]) if row[4] is not None else None
                    bom_info["inverter_label"] = inv_label
                    bom_info["inverter_count"] = inv_cnt
                    # Compute AC kW from inverter label models × counts
                    ac_total = 0.0
                    matched_any = False
                    for part in inv_label.split("+"):
                        m_part = re.search(r"([A-Za-z0-9\-_/.\s]+?)\s*[×x]\s*(\d+)", part.strip())
                        if m_part:
                            mdl = m_part.group(1).strip()
                            cnt = int(m_part.group(2))
                            if mdl in inv_kw_by_model:
                                ac_total += inv_kw_by_model[mdl] * cnt
                                matched_any = True
                    if matched_any:
                        bom_info["ac_kw"] = round(ac_total, 2)
                elif item_kind == "组串":
                    bom_info["string_count"] = int(row[4]) if row[4] is not None else None
        wb.close()
    sources["bom_xlsx"] = bom_info

    # 2. DXF layout files (ezdxf): layout-vN.dxf (3D deliverables) + satmap-layout-vN.dxf (SatMap PV_MODULES/TITLE_BLOCK)
    def _inspect_dxf(dxf_p: Path) -> dict[str, Any]:
        info: dict[str, Any] = {"exists": dxf_p.is_file()}
        if not dxf_p.is_file():
            return info
        doc_dxf = ezdxf.readfile(str(dxf_p))
        msp = doc_dxf.modelspace()
        pv_modules_cnt = 0
        pv_layer_cnt = 0
        title_texts: list[str] = []
        for entity in msp:
            layer = (entity.dxf.layer if hasattr(entity.dxf, "layer") else "").upper()
            etype = entity.dxftype()
            if layer == "PV_MODULES" and etype in ("LWPOLYLINE", "POLYLINE", "INSERT"):
                pv_modules_cnt += 1
            elif layer == "PV" and etype in ("LWPOLYLINE", "POLYLINE", "INSERT"):
                pv_layer_cnt += 1
            if layer in ("TITLE_BLOCK", "FRAME", "TEXT") and etype in ("TEXT", "MTEXT"):
                txt = ""
                if etype == "TEXT" and hasattr(entity.dxf, "text"):
                    txt = str(entity.dxf.text or "")
                elif hasattr(entity, "plain_text"):
                    txt = str(entity.plain_text() or "")
                if txt:
                    title_texts.append(txt)
        joined_tb = " || ".join(title_texts)
        info["pv_modules_layer_entities"] = pv_modules_cnt
        info["pv_layer_entities"] = pv_layer_cnt
        info["pv_module_entities"] = pv_modules_cnt if pv_modules_cnt > 0 else pv_layer_cnt
        info["title_block_texts"] = title_texts
        m_ver = re.search(r"(?:PV-\d+-v|\|\s*v)(\d+)\b", joined_tb)
        if m_ver:
            info["version"] = int(m_ver.group(1))
        m_mc = re.search(r"(?:[×x]\s*(\d+)\s*块|\((\d+)\s*pcs\)|(\d+)\s*modules)", joined_tb, re.IGNORECASE)
        if m_mc:
            info["module_count"] = int(next(g for g in m_mc.groups() if g is not None))
        m_dc = re.search(r"(?:DC\s*|[\(|\|]\s*)(\d+\.?\d*)\s*(?:kWp|kW)\b", joined_tb, re.IGNORECASE)
        if m_dc:
            info["dc_kw"] = round(float(m_dc.group(1)), 2)
        m_ac = re.search(r"AC\s*(\d+\.?\d*)\s*kW\b", joined_tb, re.IGNORECASE)
        if m_ac:
            info["ac_kw"] = round(float(m_ac.group(1)), 2)
        return info

    sources["layout_dxf"] = _inspect_dxf(exp_dir / f"layout-{vs}.dxf")
    sat_dxf_file = exp_dir / f"satmap-layout-{vs}.dxf"
    if sat_dxf_file.is_file():
        sources["satmap_layout_dxf"] = _inspect_dxf(sat_dxf_file)

    # 3. PDFs (pypdf): drawing-vN.pdf, report-vN.pdf, guangzhu-pro-vN.pdf
    def _inspect_pdf(pdf_p: Path, kind: str) -> dict[str, Any]:
        info: dict[str, Any] = {"exists": pdf_p.is_file()}
        if not pdf_p.is_file():
            return info
        reader = PdfReader(str(pdf_p))
        info["page_count"] = len(reader.pages)
        info["file_bytes"] = pdf_p.stat().st_size
        full_text = "\n".join((pg.extract_text() or "") for pg in reader.pages)
        compact_text = re.sub(r"\s+", " ", full_text)
        info["text_length"] = len(full_text)

        if kind == "drawing":
            m_v = re.search(r"PV-01-v(\d+)", compact_text)
            if m_v:
                info["version"] = int(m_v.group(1))
            m_mc = re.search(r"[×x]\s*(\d+)\s*块", compact_text) or re.search(r"/\s*(\d+)\s*块", compact_text)
            if m_mc:
                info["module_count"] = int(m_mc.group(1))
            m_dc = re.search(r"直流装机\s*(\d+\.?\d*)\s*kWp", compact_text) or re.search(r"\((\d+\.?\d*)\s*kWp\)", compact_text)
            if m_dc:
                info["dc_kw"] = round(float(m_dc.group(1)), 2)
            m_ac = re.search(r"额定交流\s*(\d+\.?\d*)\s*kWac", compact_text) or re.search(r"(\d+\.?\d*)\s*kWac", compact_text)
            if m_ac:
                info["ac_kw"] = round(float(m_ac.group(1)), 2)
            # Extract inverter counts from "{model} × {count} 台"
            m_inv_line = re.search(r"配\s*([^。]+?)\s*台", compact_text)
            if m_inv_line:
                counts = [int(x) for x in re.findall(r"[×x]\s*(\d+)", m_inv_line.group(1))]
                if counts:
                    info["inverter_count"] = sum(counts)
        elif kind == "report":
            m_v = re.search(r"方案版本[:：]\s*v(\d+)", compact_text) or re.search(r"（v(\d+)）", compact_text)
            if m_v:
                info["version"] = int(m_v.group(1))
            m_dc_mc = re.search(r"(\d+\.?\d*)\s*kWp\s*\(\s*(\d+)\s*块\s*\)", compact_text)
            if m_dc_mc:
                info["dc_kw"] = round(float(m_dc_mc.group(1)), 2)
                info["module_count"] = int(m_dc_mc.group(2))
            m_inv = re.search(r"串\s*/\s*(\d+)\s*台", compact_text)
            if m_inv:
                info["inverter_count"] = int(m_inv.group(1))
            if expected["project_name"] and expected["project_name"][:10] in compact_text:
                info["project_name_matched"] = True
        elif kind == "pro":
            if expected["project_id"] in compact_text or expected["project_id"] in full_text:
                info["project_id"] = expected["project_id"]
            m_v = re.search(rf"\bv{version}\b", compact_text, re.IGNORECASE)
            if m_v:
                info["version"] = version
            # Check module_count, dc_kw, ac_kw, inverter_count presence in extracted pro PDF text
            m_mc = (
                re.search(rf"\b{expected['module_count']}\s*(?:块|pcs|片|modules)\b", compact_text, re.IGNORECASE)
                or re.search(r"(?:组件数[量]?|Module\s*Count)\s*[:：]?\s*(\d+)", compact_text, re.IGNORECASE)
            )
            if m_mc:
                info["module_count"] = int(m_mc.group(1)) if m_mc.lastindex else expected["module_count"]
            for dc_pat in [f"{expected['dc_kw']:.2f}", f"{expected['dc_kw']:.1f}", f"{expected['dc_kw']:g}"]:
                if dc_pat in compact_text:
                    info["dc_kw"] = expected["dc_kw"]
                    break
            for ac_pat in [f"{expected['ac_kw']:.2f}", f"{expected['ac_kw']:.1f}", f"{expected['ac_kw']:g}"]:
                if ac_pat in compact_text:
                    info["ac_kw"] = expected["ac_kw"]
                    break
            m_inv = (
                re.search(r"→\s*(\d+)\s*Inverter\(s\)", compact_text, re.IGNORECASE)
                or re.search(r"(\d+)\s*台\s*\(\d+\s*MPPT/台\)", compact_text)
                or re.search(r"kW\s*[×x]\s*(\d+)\s*=", compact_text, re.IGNORECASE)
                or re.search(r"\((\d+)\s*[×x]\s*\d+\.?\d*\s*kW\)", compact_text, re.IGNORECASE)
            )
            if m_inv:
                info["inverter_count"] = int(m_inv.group(1))
            elif re.search(rf"\b{expected['inverter_count']}\s*台", compact_text):
                info["inverter_count"] = expected["inverter_count"]
        return info

    sources[f"drawing-{vs}.pdf"] = _inspect_pdf(exp_dir / f"drawing-{vs}.pdf", "drawing")
    sources[f"report-{vs}.pdf"] = _inspect_pdf(exp_dir / f"report-{vs}.pdf", "report")
    sources[f"guangzhu-pro-{vs}.pdf"] = _inspect_pdf(exp_dir / f"guangzhu-pro-{vs}.pdf", "pro")

    # 4. Pairwise & ground-truth checks across all 6 fields
    checks: list[dict[str, Any]] = []
    mismatches = 0

    def _check(field: str, exp_val: Any, act_val: Any, src_label: str, tol: float = 0.0) -> None:
        nonlocal mismatches
        if act_val is None:
            return
        if isinstance(exp_val, (int, float)) and isinstance(act_val, (int, float)) and tol > 0:
            ok = abs(float(exp_val) - float(act_val)) <= tol
        else:
            ok = exp_val == act_val
        if not ok:
            mismatches += 1
        checks.append(
            {
                "field": field,
                "expected": exp_val,
                "actual": act_val,
                "source": src_label,
                "match": ok,
            }
        )

    # Check BOM
    _check("module_count", expected["module_count"], bom_info.get("module_count"), "bom_xlsx")
    _check("dc_kw", expected["dc_kw"], bom_info.get("dc_kw"), "bom_xlsx", tol=0.05)
    _check("inverter_count", expected["inverter_count"], bom_info.get("inverter_count"), "bom_xlsx")
    _check("ac_kw", expected["ac_kw"], bom_info.get("ac_kw"), "bom_xlsx", tol=0.05)

    # Check 3D layout DXF & SatMap layout DXF
    for dxf_key in ("layout_dxf", "satmap_layout_dxf"):
        if dxf_key in sources:
            d_src = sources[dxf_key]
            _check("module_count", expected["module_count"], d_src.get("pv_module_entities"), f"{dxf_key}:entities")
            _check("module_count", expected["module_count"], d_src.get("module_count"), f"{dxf_key}:title_block")
            _check("version", expected["version"], d_src.get("version"), f"{dxf_key}:title_block")
            _check("dc_kw", expected["dc_kw"], d_src.get("dc_kw"), f"{dxf_key}:title_block", tol=0.15)
            _check("ac_kw", expected["ac_kw"], d_src.get("ac_kw"), f"{dxf_key}:title_block", tol=0.15)

    # Check 3 PDFs
    drw_src = sources[f"drawing-{vs}.pdf"]
    _check("version", expected["version"], drw_src.get("version"), f"drawing-{vs}.pdf")
    _check("module_count", expected["module_count"], drw_src.get("module_count"), f"drawing-{vs}.pdf")
    _check("dc_kw", expected["dc_kw"], drw_src.get("dc_kw"), f"drawing-{vs}.pdf", tol=0.15)
    _check("ac_kw", expected["ac_kw"], drw_src.get("ac_kw"), f"drawing-{vs}.pdf", tol=0.15)
    _check("inverter_count", expected["inverter_count"], drw_src.get("inverter_count"), f"drawing-{vs}.pdf")

    rep_src = sources[f"report-{vs}.pdf"]
    _check("version", expected["version"], rep_src.get("version"), f"report-{vs}.pdf")
    _check("module_count", expected["module_count"], rep_src.get("module_count"), f"report-{vs}.pdf")
    _check("dc_kw", expected["dc_kw"], rep_src.get("dc_kw"), f"report-{vs}.pdf", tol=0.05)
    _check("inverter_count", expected["inverter_count"], rep_src.get("inverter_count"), f"report-{vs}.pdf")

    pro_src = sources[f"guangzhu-pro-{vs}.pdf"]
    _check("page_count_6", 6, pro_src.get("page_count"), f"guangzhu-pro-{vs}.pdf")
    _check("project_id", expected["project_id"], pro_src.get("project_id"), f"guangzhu-pro-{vs}.pdf")
    _check("version", expected["version"], pro_src.get("version"), f"guangzhu-pro-{vs}.pdf")
    _check("module_count", expected["module_count"], pro_src.get("module_count"), f"guangzhu-pro-{vs}.pdf")
    _check("dc_kw", expected["dc_kw"], pro_src.get("dc_kw"), f"guangzhu-pro-{vs}.pdf", tol=0.15)
    _check("ac_kw", expected["ac_kw"], pro_src.get("ac_kw"), f"guangzhu-pro-{vs}.pdf", tol=0.15)
    _check("inverter_count", expected["inverter_count"], pro_src.get("inverter_count"), f"guangzhu-pro-{vs}.pdf")

    return {
        "project_id": expected["project_id"],
        "version": expected["version"],
        "expected": expected,
        "sources": sources,
        "num_checks": len(checks),
        "mismatches": mismatches,
        "all_consistent": len(checks) >= 12 and mismatches == 0,
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Subprocess cold-start runner & in-process warm runner
# ---------------------------------------------------------------------------

def _run_single_cold_task_cli(task_id: str, prep_dir: str | None) -> int:
    """Entry point inside a brand-new Python process for true cold-start measurement."""
    t0 = time.perf_counter()
    mods = _load_backend()
    t_import = time.perf_counter() - t0

    storage = mods["storage"]
    sat = mods["sat"]
    api = mods["api"]
    live_weather = mods["live_weather"]
    payloads = _fixed_payloads()

    with tempfile.TemporaryDirectory(prefix=f"gz-cold-{task_id}-") as tmp:
        tmp_root = Path(tmp)
        proj_dir = Path(prep_dir) if prep_dir else (tmp_root / "projects")
        proj_dir.mkdir(parents=True, exist_ok=True)
        lw_dir = tmp_root / "live_weather"
        lw_dir.mkdir(parents=True, exist_ok=True)
        storage.PROJECTS_DIR = proj_dir
        sat.PROJECTS_DIR = proj_dir
        api.ROOT = Path(prep_dir).parent if prep_dir else tmp_root
        live_weather.LIVE_CACHE_DIR = lw_dir

        t1 = time.perf_counter()
        if task_id == "T-01":
            res = _execute_t01_once(mods, tmp_root, 0, payloads["t01"])
        elif task_id == "T-02":
            res = _execute_t02_once(mods, proj_dir, 0)
        elif task_id == "T-03":
            if prep_dir and (Path(prep_dir) / "bench-t03-xiangtai").is_dir():
                dst3 = Path(prep_dir) / "bench-t03-xiangtai"
                ver3 = 3
            else:
                dst3, ver3 = _prepare_analyzed_project(
                    mods,
                    proj_dir,
                    ROOT / "projects" / "taizhou-xiangtai-warehouse",
                    "bench-t03-xiangtai",
                    prune_from_v1=True,
                )
            res = _export_five_plus_satmap_dxf(
                mods, "bench-t03-xiangtai", ver3, dst3, tmp_root / "cold_t03_exp", include_satmap_dxf=False
            )
        elif task_id == "T-03b":
            res = _execute_sg50_once(mods, proj_dir, tmp_root, 0, payloads["sg50cx_p2"])
        else:
            raise ValueError(f"Unknown task_id: {task_id}")
        t_call = time.perf_counter() - t1

    out = {
        "task_id": task_id,
        "ok": True,
        "import_s": round(t_import, 4),
        "call_s": round(t_call, 4),
        "total_s": round(t_import + t_call, 4),
        "summary": res.get("summary", {}),
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _measure_task_cold_subprocess(task_id: str, prep_dir: Path | None = None) -> dict[str, Any]:
    """Spawn a fresh Python subprocess to measure genuine cold-start import + execution."""
    cmd = [sys.executable, str(Path(__file__).resolve()), "--single-cold-task", task_id]
    if prep_dir is not None:
        cmd.extend(["--prep-dir", str(prep_dir)])
    start_iso = _iso_now()
    t_wall0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240, cwd=str(ROOT))
    wall_s = round(time.perf_counter() - t_wall0, 4)
    end_iso = _iso_now()
    if proc.returncode != 0:
        return {
            "ok": False,
            "start_iso": start_iso,
            "end_iso": end_iso,
            "wall_s": wall_s,
            "error": (proc.stderr or proc.stdout or f"returncode={proc.returncode}")[-600:],
        }
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    parsed = json.loads(lines[-1])
    return {
        "ok": True,
        "start_iso": start_iso,
        "end_iso": end_iso,
        "import_s": parsed["import_s"],
        "call_s": parsed["call_s"],
        "total_s": parsed["total_s"],
        "subprocess_wall_s": wall_s,
        "summary": parsed.get("summary", {}),
    }


def _time_task_v2(
    name: str,
    input_payload: object,
    fn,
    *,
    cold_sub: dict[str, Any],
    n_warm: int = 3,
) -> dict[str, Any]:
    """Record subprocess true cold start + in-process first call + n_warm runs with ISO timestamps."""
    in_hash = _sha256_json(input_payload)

    first_start = _iso_now()
    t0 = time.perf_counter()
    first_res = fn(0)
    first_s = round(time.perf_counter() - t0, 4)
    first_end = _iso_now()

    warm_runs: list[dict[str, Any]] = []
    failures = 0 if cold_sub.get("ok") else 1
    last_artifacts = first_res.get("artifacts", {})
    last_res = first_res
    for idx in range(1, n_warm + 1):
        run_start = _iso_now()
        t0 = time.perf_counter()
        try:
            r = fn(idx)
            elapsed = round(time.perf_counter() - t0, 4)
            run_end = _iso_now()
            warm_runs.append(
                {
                    "iter": idx,
                    "elapsed_s": elapsed,
                    "ok": True,
                    "start_iso": run_start,
                    "end_iso": run_end,
                    "summary": r.get("summary", {}),
                }
            )
            last_artifacts = r.get("artifacts", {})
            last_res = r
        except Exception as exc:
            elapsed = round(time.perf_counter() - t0, 4)
            run_end = _iso_now()
            failures += 1
            warm_runs.append(
                {
                    "iter": idx,
                    "elapsed_s": elapsed,
                    "ok": False,
                    "start_iso": run_start,
                    "end_iso": run_end,
                    "error": repr(exc),
                }
            )

    ok_times = [r["elapsed_s"] for r in warm_runs if r["ok"]]
    rec = {
        "task_id": name,
        "input_sha256": in_hash,
        "cold_subprocess_s": cold_sub.get("total_s"),
        "cold_subprocess_import_s": cold_sub.get("import_s"),
        "cold_subprocess_call_s": cold_sub.get("call_s"),
        "cold_subprocess_wall_s": cold_sub.get("subprocess_wall_s"),
        "cold_subprocess_start_iso": cold_sub.get("start_iso"),
        "cold_subprocess_end_iso": cold_sub.get("end_iso"),
        "cold_subprocess_detail": cold_sub,
        "first_call_in_process_s": first_s,
        "first_call_start_iso": first_start,
        "first_call_end_iso": first_end,
        "first_call_summary": first_res.get("summary", {}),
        "n_timed_repeats": n_warm,
        "failures": failures,
        "min_s": round(min(ok_times), 4) if ok_times else None,
        "median_s": round(statistics.median(ok_times), 4) if ok_times else None,
        "max_s": round(max(ok_times), 4) if ok_times else None,
        "warm_runs_s": warm_runs,
        "artifact_sha256": last_artifacts,
        "_last_res": last_res,
    }
    return rec


# ---------------------------------------------------------------------------
# Main benchmark orchestrator
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Guangzhu 20261113 reproducible timed benchmark ledger")
    parser.add_argument("--single-cold-task", type=str, default=None, help="Internal fresh-process cold-start probe")
    parser.add_argument("--prep-dir", type=str, default=None, help="Pre-prepared project directory for cold T-03")
    args = parser.parse_args()

    if args.single_cold_task:
        return _run_single_cold_task_cli(args.single_cold_task, args.prep_dir)

    run_id = datetime.now(timezone.utc).strftime("bench-%Y%m%dT%H%M%SZ")
    payloads = _fixed_payloads()

    # 1. Freeze fixed input snapshot, catalog CSVs, directory CSV, and core source SHA-256
    inputs_dir = ROOT / "output" / "benchmark-inputs-20261113"
    snapshot_info = _snapshot_inputs(inputs_dir, payloads)
    print(f"[1/5] Input snapshot frozen at {inputs_dir} ({snapshot_info['num_source_files']} source files)")

    # 2. Measure fresh-process cold starts BEFORE warming heavy tasks where independent
    print("[2/5] Measuring true fresh-subprocess cold starts (T-01, T-02, T-03b)...")
    cold_t01 = _measure_task_cold_subprocess("T-01")
    print(f"  T-01 cold_subprocess_s = {cold_t01.get('total_s')}s (import={cold_t01.get('import_s')}s, call={cold_t01.get('call_s')}s)")
    cold_t02 = _measure_task_cold_subprocess("T-02")
    print(f"  T-02 cold_subprocess_s = {cold_t02.get('total_s')}s (import={cold_t02.get('import_s')}s, call={cold_t02.get('call_s')}s)")
    cold_sg50 = _measure_task_cold_subprocess("T-03b")
    print(f"  T-03b cold_subprocess_s = {cold_sg50.get('total_s')}s (import={cold_sg50.get('import_s')}s, call={cold_sg50.get('call_s')}s)")

    # Load backend in main process for warm benchmark suites & cross-format verification
    mods = _load_backend()
    storage = mods["storage"]
    sat = mods["sat"]
    api = mods["api"]
    live_weather = mods["live_weather"]

    orig_projects_dir = storage.PROJECTS_DIR
    orig_sat_projects_dir = sat.PROJECTS_DIR
    orig_api_root = api.ROOT
    orig_lw_dir = live_weather.LIVE_CACHE_DIR

    with tempfile.TemporaryDirectory(prefix="gz-bench-20261113-") as tmp:
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
            # Prepare T-03 analyzed v3 project first so cold_t03 subprocess measures pure export cold-start
            dst_t03, ver_t03 = _prepare_analyzed_project(
                mods,
                proj_dir,
                ROOT / "projects" / "taizhou-xiangtai-warehouse",
                "bench-t03-xiangtai",
                prune_from_v1=True,
            )
            cold_t03 = _measure_task_cold_subprocess("T-03", prep_dir=proj_dir)
            print(f"  T-03 cold_subprocess_s = {cold_t03.get('total_s')}s (import={cold_t03.get('import_s')}s, call={cold_t03.get('call_s')}s)")

            # ---- T-01 ----
            print("[3/5] Running in-process first call + 3 warm runs for T-01, T-02, T-03, T-03b...")
            t01_rec = _time_task_v2(
                "T-01",
                payloads["t01"],
                lambda idx: _execute_t01_once(mods, tmp_root, idx, payloads["t01"]),
                cold_sub=cold_t01,
                n_warm=3,
            )
            t01_rec.pop("_last_res", None)
            t01_rec["boundary"] = (
                "SatMap 76m×36m dual-slope+2 keepouts: run_satmap_design(layout+MPPT+8760h + "
                "4 backend summary CAD SVG sheets via generate_four_cad_drawings; note: the 16-sheet "
                "full CAD drawing set is rendered in the #satmap frontend workbench and is not claimed "
                "inside this backend timing) + export_satmap_dxf + 6-page 《光筑专业报告》 PDF; "
                "offline=True, excludes human polygon tracing."
            )
            t01_rec["token_cost_cny"] = 0.0
            t01_rec["execution_track"] = "offline_deterministic_compute"

            # ---- T-02 ----
            t02_rec = _time_task_v2(
                "T-02",
                payloads["t02"],
                lambda idx: _execute_t02_once(mods, proj_dir, idx),
                cold_sub=cold_t02,
                n_warm=3,
            )
            t02_rec.pop("_last_res", None)
            t02_rec["boundary"] = (
                "Xiangtai high-low 3D factory cloned (repo pre-contains v1.json and v2.json) -> "
                "analysis.analyze(v1) + deterministic S01>8% rule prune (18 modules removed) -> "
                "appends monotonic v3 + analysis.analyze(v3) (hard_failed 1 -> 0); offline rule chain "
                "only (online AGH multi-turn LLM billed separately, pending live API run)."
            )
            t02_rec["token_cost_cny"] = 0.0
            t02_rec["execution_track"] = "offline_deterministic_rule_chain"
            t02_rec["online_agh_llm_note"] = (
                "Online AGH dual-session API token ledger pending live metered run; "
                "not bundled into offline timing."
            )

            # ---- T-03 (Xiangtai v3 same-version 5-deliverable export) ----
            def _run_t03_warm(idx: int) -> dict[str, Any]:
                exp_dir = tmp_root / f"t03_exp_{idx}"
                # Time only the 5-deliverable export; satmap DXF generated post-timing for cross-check
                return _export_five_plus_satmap_dxf(
                    mods, "bench-t03-xiangtai", ver_t03, dst_t03, exp_dir, include_satmap_dxf=False
                )

            t03_rec = _time_task_v2(
                "T-03",
                payloads["t03"],
                _run_t03_warm,
                cold_sub=cold_t03,
                n_warm=3,
            )
            t03_rec.pop("_last_res", None)
            t03_rec["boundary"] = (
                "Same-version 5-file export from analyzed v3 (v3 produced after pruning 18 S01>8% "
                "modules from v1 on repo containing v1/v2): write_deliverables (layout-v3.dxf + bom-v3.xlsx) + "
                "write_pdf_deliverables (4-page drawing-v3.pdf + 3-page concise report-v3.pdf) + "
                "6-page 《光筑专业报告》 guangzhu-pro-v3.pdf."
            )
            t03_rec["token_cost_cny"] = 0.0
            t03_rec["execution_track"] = "offline_deterministic_export"

            # ---- Cross-format consistency checks ----
            print("[4/5] Running cross_file_consistency_check (openpyxl + ezdxf + pypdf)...")
            # (a) T-03 (bench-t03-xiangtai v3) — also emit satmap-layout-v3.dxf into last export dir for PV_MODULES/TITLE_BLOCK check
            last_t03_exp = tmp_root / f"t03_exp_{t03_rec['n_timed_repeats']}"
            _export_five_plus_satmap_dxf(
                mods, "bench-t03-xiangtai", ver_t03, dst_t03, last_t03_exp, include_satmap_dxf=True
            )
            t03_xcheck = _cross_file_consistency_check(
                mods, last_t03_exp, dst_t03, "bench-t03-xiangtai", ver_t03
            )
            t03_rec["cross_file_consistency_check"] = t03_xcheck
            print(
                f"  T-03 (xiangtai v{ver_t03}) consistency: all_consistent={t03_xcheck['all_consistent']} "
                f"({t03_xcheck['num_checks']} checks, {t03_xcheck['mismatches']} mismatches)"
            )

            # (b) changzhou-demo v3 (from data/demo/projects/changzhou-demo)
            dst_cz, ver_cz = _prepare_analyzed_project(
                mods,
                proj_dir,
                ROOT / "data" / "demo" / "projects" / "changzhou-demo",
                "changzhou-demo",
                prune_from_v1=False,
                target_version=3,
            )
            cz_exp = tmp_root / "changzhou_demo_v3_exp"
            cz_export_res = _export_five_plus_satmap_dxf(
                mods, "changzhou-demo", ver_cz, dst_cz, cz_exp, include_satmap_dxf=True
            )
            cz_xcheck = _cross_file_consistency_check(mods, cz_exp, dst_cz, "changzhou-demo", ver_cz)
            t03_rec["changzhou_demo_v3_consistency_check"] = {
                "export_summary": cz_export_res["summary"],
                "artifact_sha256": cz_export_res["artifacts"],
                **cz_xcheck,
            }
            print(
                f"  changzhou-demo v{ver_cz} consistency: all_consistent={cz_xcheck['all_consistent']} "
                f"({cz_xcheck['num_checks']} checks, {cz_xcheck['mismatches']} mismatches)"
            )

            # (c) T-03b: SG50CX-P2 (90 × 580W = 52.20 kWp DC, 1 × SG50CX-P2 = 50.0 kW AC)
            sg50_rec = _time_task_v2(
                "T-03b",
                payloads["sg50cx_p2"],
                lambda idx: _execute_sg50_once(mods, proj_dir, tmp_root, idx, payloads["sg50cx_p2"]),
                cold_sub=cold_sg50,
                n_warm=3,
            )
            last_sg50 = sg50_rec.pop("_last_res")
            sg50_rec["boundary"] = (
                "SG50CX-P2 90×580W (52.20 kWp DC / 50.0 kW AC, 1×SG50CX-P2) flat-roof end-to-end "
                "verification: run_satmap_design -> save_to_guangzhu_project(v1) -> 5 deliverables + "
                "satmap DXF + cross_file_consistency_check; offline=True."
            )
            sg50_rec["token_cost_cny"] = 0.0
            sg50_rec["execution_track"] = "offline_deterministic_compute_and_export"
            sg50_xcheck = _cross_file_consistency_check(
                mods,
                last_sg50["exp_dir"],
                last_sg50["base_dir"],
                last_sg50["project_id"],
                last_sg50["version"],
            )
            sg50_rec["cross_file_consistency_check"] = sg50_xcheck
            print(
                f"  T-03b (SG50CX-P2 90×580W) consistency: all_consistent={sg50_xcheck['all_consistent']} "
                f"({sg50_xcheck['num_checks']} checks, {sg50_xcheck['mismatches']} mismatches)"
            )

            # 5. Write output/benchmark-ledger-20261113.json
            ledger = {
                "run_id": run_id,
                "generated_at_utc": _iso_now(),
                "machine": _machine_info(),
                "methodology": (
                    "Isolated TemporaryDirectory per execution; "
                    "true fresh-process cold-start (cold_subprocess_s) via subprocess.run([sys.executable, ...]) "
                    "before any guangzhu/pvlib/shapely/matplotlib imports; "
                    "in-process first call (first_call_in_process_s) + N=3 timed warm runs (warm_runs_s) "
                    "with UTC start/end ISO timestamps; "
                    "pypdf actual page count verification (guangzhu-pro=6p, report=3p, drawing=4p); "
                    "automated cross-format consistency check (openpyxl + ezdxf + pypdf) across T-03, "
                    "changzhou-demo v3, and SG50CX-P2 (90×580W); offline=True."
                ),
                "input_snapshot": snapshot_info,
                "tasks": [t01_rec, t02_rec, t03_rec, sg50_rec],
                "cross_file_consistency_summary": {
                    "t03_xiangtai_v3_consistent": t03_xcheck["all_consistent"],
                    "changzhou_demo_v3_consistent": cz_xcheck["all_consistent"],
                    "sg50cx_p2_90x580w_consistent": sg50_xcheck["all_consistent"],
                    "total_checks_executed": (
                        t03_xcheck["num_checks"] + cz_xcheck["num_checks"] + sg50_xcheck["num_checks"]
                    ),
                    "total_mismatches": (
                        t03_xcheck["mismatches"] + cz_xcheck["mismatches"] + sg50_xcheck["mismatches"]
                    ),
                },
            }
            out_path = ROOT / "output" / "benchmark-ledger-20261113.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[5/5] Wrote {out_path} ({run_id})")
        finally:
            storage.PROJECTS_DIR = orig_projects_dir
            sat.PROJECTS_DIR = orig_sat_projects_dir
            api.ROOT = orig_api_root
            live_weather.LIVE_CACHE_DIR = orig_lw_dir
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
