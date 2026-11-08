"""Generate engineering PDF deliverables (report-v{ver}.pdf & drawing-v{ver}.pdf) directly in exports/v{ver}/."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle, FancyBboxPatch, Polygon as MplPolygon, Rectangle

from .. import electrical, project as storage

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def _draw_cad_dim_h(ax, x1: float, x2: float, y_ref: float, y_dim: float, label: str, fontsize: float = 7.5):
    """Draw a standard GB CAD horizontal dimension with extension lines and <-> arrows."""
    if abs(x2 - x1) < 0.2:
        return
    ya, yb = (min(y_ref, y_dim), max(y_ref, y_dim))
    over = 0.6 if y_dim >= y_ref else -0.6
    ax.plot([x1, x1], [y_ref, y_dim + over], color="#0F172A", linewidth=0.55, zorder=6)
    ax.plot([x2, x2], [y_ref, y_dim + over], color="#0F172A", linewidth=0.55, zorder=6)
    ax.annotate(
        "",
        xy=(x1, y_dim),
        xytext=(x2, y_dim),
        arrowprops=dict(arrowstyle="<|-|>", color="#0F172A", lw=0.75, mutation_scale=7),
        zorder=7,
    )
    ax.text(
        (x1 + x2) / 2,
        y_dim + (0.28 if y_dim >= y_ref else -0.35),
        label,
        ha="center",
        va="bottom" if y_dim >= y_ref else "top",
        fontsize=fontsize,
        color="#0F172A",
        bbox=dict(boxstyle="square,pad=0.06", facecolor="#FFFFFF", edgecolor="none", alpha=0.88),
        zorder=8,
    )


def _draw_cad_dim_v(ax, y1: float, y2: float, x_ref: float, x_dim: float, label: str, fontsize: float = 7.5):
    """Draw a standard GB CAD vertical dimension with extension lines and <-> arrows."""
    if abs(y2 - y1) < 0.2:
        return
    over = 0.6 if x_dim >= x_ref else -0.6
    ax.plot([x_ref, x_dim + over], [y1, y1], color="#0F172A", linewidth=0.55, zorder=6)
    ax.plot([x_ref, x_dim + over], [y2, y2], color="#0F172A", linewidth=0.55, zorder=6)
    ax.annotate(
        "",
        xy=(x_dim, y1),
        xytext=(x_dim, y2),
        arrowprops=dict(arrowstyle="<|-|>", color="#0F172A", lw=0.75, mutation_scale=7),
        zorder=7,
    )
    ax.text(
        x_dim + (-0.35 if x_dim < x_ref else 0.35),
        (y1 + y2) / 2,
        label,
        ha="right" if x_dim < x_ref else "left",
        va="center",
        rotation=90,
        fontsize=fontsize,
        color="#0F172A",
        bbox=dict(boxstyle="square,pad=0.06", facecolor="#FFFFFF", edgecolor="none", alpha=0.88),
        zorder=8,
    )


def _draw_roof_axes(ax, project: dict, design: dict, electric: dict, structure: dict, mode: str = "layout"):
    roof = dict(project.get("roof") or {})
    if roof.get("type") in ("ground", "carport") and design.get("installation_roof"):
        roof = design["installation_roof"]
    outline = roof.get("outline") or [[0, 0], [40, 0], [40, 24], [0, 24]]
    xs = [pt[0] for pt in outline]
    ys = [pt[1] for pt in outline]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)

    ax.set_facecolor("#FFFFFF")
    ax.patch.set_alpha(0.0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    # Centerlines (dot-dash CAD axes)
    cx_mid, cy_mid = (min_x + max_x) / 2, (min_y + max_y) / 2
    ax.plot([min_x - span_x * 0.05, max_x + span_x * 0.05], [cy_mid, cy_mid],
            linestyle="-.", color="#64748B", linewidth=0.5, zorder=1)
    ax.plot([cx_mid, cx_mid], [min_y - span_y * 0.05, max_y + span_y * 0.05],
            linestyle="-.", color="#64748B", linewidth=0.5, zorder=1)

    # Roof outer contour (thick solid line) + inner parapet setback line (dashed)
    roof_poly = MplPolygon(
        [(pt[0], pt[1]) for pt in outline],
        closed=True,
        facecolor="#FFFFFF",
        edgecolor="#0F172A",
        linewidth=1.9,
        zorder=2,
    )
    ax.add_patch(roof_poly)

    # Keepouts (corridors / skylights) with CAD dimension callouts
    for idx_k, kp in enumerate((roof.get("keepouts") or []) + (design.get("added_keepouts") or []), 1):
        poly = kp.get("polygon") or []
        if len(poly) >= 3:
            ax.add_patch(
                MplPolygon(
                    [(pt[0], pt[1]) for pt in poly],
                    closed=True,
                    facecolor="#F8FAFC",
                    edgecolor="#0F172A",
                    linestyle="--",
                    linewidth=0.85,
                    hatch="..",
                    zorder=2.5,
                )
            )
            kxs = [p[0] for p in poly]
            kys = [p[1] for p in poly]
            kw = max(kxs) - min(kxs)
            kh = max(kys) - min(kys)
            if kw >= 1.5 and kh >= 0.8:
                ax.text(
                    (min(kxs) + max(kxs)) / 2,
                    (min(kys) + max(kys)) / 2,
                    f"{int(round(kw * 1000))}×{int(round(kh * 1000))}",
                    fontsize=6.2,
                    ha="center",
                    va="center",
                    color="#0F172A",
                    bbox=dict(boxstyle="square,pad=0.05", facecolor="#FFFFFF", edgecolor="none", alpha=0.82),
                    zorder=6,
                )

    # Obstacles with CAD dimension lines
    for obs in roof.get("obstacles") or []:
        if obs.get("kind") == "cylinder" and obs.get("center"):
            cx, cy = obs["center"][:2]
            r = float(obs.get("radius_m") or 1.0)
            ax.add_patch(
                Circle(
                    (cx, cy),
                    radius=r,
                    facecolor="#FFFFFF",
                    edgecolor="#0F172A",
                    linewidth=1.15,
                    hatch="//",
                    zorder=3,
                )
            )
            ax.plot([cx - r * 1.25, cx + r * 1.25], [cy, cy], linestyle="-.", color="#334155", linewidth=0.45, zorder=3.5)
            ax.plot([cx, cx], [cy - r * 1.25, cy + r * 1.25], linestyle="-.", color="#334155", linewidth=0.45, zorder=3.5)
            diam_mm = int(round(r * 2000))
            h_mm = int(round(float(obs.get("height_m") or 1.8) * 1000))
            ax.annotate(
                f"Φ{diam_mm} (H={h_mm})",
                xy=(cx + r * 0.7, cy + r * 0.7),
                xytext=(cx + r + 1.2, cy + r + 1.0),
                fontsize=6.5,
                color="#0F172A",
                arrowprops=dict(arrowstyle="->", color="#0F172A", lw=0.65),
                zorder=7,
            )
        elif obs.get("footprint"):
            fp = obs["footprint"]
            ax.add_patch(
                MplPolygon(
                    [(pt[0], pt[1]) for pt in fp],
                    closed=True,
                    facecolor="#FFFFFF",
                    edgecolor="#0F172A",
                    linewidth=1.15,
                    hatch="//",
                    zorder=3,
                )
            )
            oxs = [pt[0] for pt in fp]
            oys = [pt[1] for pt in fp]
            ox0, ox1 = min(oxs), max(oxs)
            oy0, oy1 = min(oys), max(oys)
            ow_mm = int(round((ox1 - ox0) * 1000))
            oh_mm = int(round((oy1 - oy0) * 1000))
            hz_mm = int(round(float(obs.get("height_m") or 1.8) * 1000))
            _draw_cad_dim_h(ax, ox0, ox1, oy1, oy1 + 0.95, f"{ow_mm}", fontsize=6.3)
            _draw_cad_dim_v(ax, oy0, oy1, ox1, ox1 + 0.95, f"{oh_mm}", fontsize=6.3)
            ax.text(
                (ox0 + ox1) / 2,
                (oy0 + oy1) / 2,
                f"H={hz_mm}",
                fontsize=6.2,
                ha="center",
                va="center",
                color="#0F172A",
                bbox=dict(boxstyle="square,pad=0.05", facecolor="#FFFFFF", edgecolor="none", alpha=0.85),
                zorder=6,
            )

    # Map modules to strings and wind zones
    mod_to_string = {}
    palette = ["#1D4ED8", "#047857", "#B45309", "#6D28D9", "#BE185D", "#0E7490", "#4338CA", "#4D7C0F", "#C2410C", "#0F766E"]
    string_color = {}
    for idx, s in enumerate(electric.get("strings") or []):
        sid = s.get("id", f"S{idx + 1}")
        string_color[sid] = palette[idx % len(palette)]
        for mid in s.get("module_ids") or []:
            mod_to_string[mid] = sid

    wind_modules = {m.get("id"): m for m in (structure.get("wind", {}).get("modules") or [])}
    zone_colors = {
        "corner": ("#FEE2E2", "#991B1B"),
        "edge": ("#FEF3C7", "#92400E"),
        "middle": ("#DCFCE7", "#166534"),
        "interior": ("#DCFCE7", "#166534"),
        "center": ("#DCFCE7", "#166534"),
    }

    panels = design.get("modules") or []
    for mod in panels:
        corners = mod.get("corners") or []
        if len(corners) < 3:
            continue
        mid = mod.get("id")
        if mode == "electrical":
            sid = mod_to_string.get(mid, "")
            fc = "#FFFFFF"
            ec = string_color.get(sid, "#1D4ED8")
            lw = 0.75
            alpha = 0.95
        elif mode == "wind":
            wm = wind_modules.get(mid, {})
            z = str(wm.get("zone") or "interior").lower()
            fc, ec = zone_colors.get(z, ("#F8FAFC", "#0F172A"))
            lw = 0.65
            alpha = 0.9
        else:
            fc = "#F8FAFC"
            ec = "#0F172A"
            lw = 0.6
            alpha = 0.95

        ax.add_patch(
            MplPolygon(
                [(pt[0], pt[1]) for pt in corners],
                closed=True,
                facecolor=fc,
                edgecolor=ec,
                linewidth=lw,
                alpha=alpha,
                zorder=4,
            )
        )

    # String labels & DC/AC routing for electrical sheet
    if mode == "electrical":
        panel_map = {m["id"]: m for m in panels if "id" in m}
        for idx, s in enumerate(electric.get("strings") or []):
            mids = s.get("module_ids") or []
            if not mids or mids[0] not in panel_map:
                continue
            pts = []
            for mid in mids:
                m = panel_map.get(mid)
                if m and m.get("center"):
                    pts.append(m["center"][:2])
                elif m and m.get("corners"):
                    c = m["corners"]
                    pts.append([sum(p[0] for p in c) / len(c), sum(p[1] for p in c) / len(c)])
            if len(pts) >= 2:
                col = string_color.get(s.get("id"), "#1D4ED8")
                ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, linewidth=1.0, zorder=5.2)
            p0 = panel_map[mids[0]]["corners"][0][:2]
            ax.text(
                p0[0], p0[1], s.get("id", f"S{idx+1}"),
                fontsize=6.0, fontweight="bold", color="#0F172A",
                bbox=dict(boxstyle="square,pad=0.1", facecolor="#FFFFFF", edgecolor="#0F172A", lw=0.5, alpha=0.9),
                zorder=6,
            )

        cables = electric.get("cables") or {}
        for dc_row in cables.get("dc") or []:
            path_pts = dc_row.get("path") or dc_row.get("points") or []
            if len(path_pts) >= 2:
                ax.plot(
                    [p[0] for p in path_pts],
                    [p[1] for p in path_pts],
                    color="#0F172A",
                    linestyle="--",
                    linewidth=0.95,
                    zorder=5.5,
                )
        for ac_row in cables.get("ac") or []:
            path_pts = ac_row.get("path") or ac_row.get("points") or []
            if len(path_pts) >= 2:
                ax.plot(
                    [p[0] for p in path_pts],
                    [p[1] for p in path_pts],
                    color="#DC2626",
                    linewidth=1.5,
                    zorder=5.8,
                )

        for idx, pos in enumerate(roof.get("inverter_positions") or []):
            ax.scatter([pos[0]], [pos[1]], s=45, marker="s", c="#FFFFFF", edgecolors="#0F172A", linewidths=1.4, zorder=7)
            ax.text(pos[0] + 0.5, pos[1] + 0.5, f"INV-{idx+1}", fontsize=7.0, fontweight="bold", color="#0F172A", zorder=7)
        gp = roof.get("grid_point")
        if gp and len(gp) >= 2:
            ax.scatter([gp[0]], [gp[1]], s=55, marker="^", c="#FFFFFF", edgecolors="#DC2626", linewidths=1.5, zorder=7)
            ax.text(gp[0] + 0.5, gp[1] - 0.5, "GP", fontsize=7.0, fontweight="bold", color="#DC2626", zorder=7)

    # Full GB CAD Dimensioning: Segmented edges + Overall bounding dimensions + Array setback/pitch
    pad_x = max(5.5, span_x * 0.14)
    pad_y = max(5.5, span_y * 0.18)

    # 1. Unique X breakpoints along top & bottom for chained horizontal dimensions
    ux = sorted({round(pt[0], 2) for pt in outline})
    if len(ux) > 2:
        for i in range(len(ux) - 1):
            seg_m = ux[i + 1] - ux[i]
            if seg_m >= 1.0:
                _draw_cad_dim_h(ax, ux[i], ux[i + 1], max_y, max_y + pad_y * 0.36, f"{int(round(seg_m * 1000))} ({seg_m:.1f}m)", fontsize=7.0)
    # Overall horizontal dimension (Top outer & Bottom)
    _draw_cad_dim_h(ax, min_x, max_x, max_y, max_y + pad_y * 0.68, f"{int(round(span_x * 1000))} ({span_x:.1f}m)", fontsize=7.8)
    _draw_cad_dim_h(ax, min_x, max_x, min_y, min_y - pad_y * 0.45, f"{int(round(span_x * 1000))}", fontsize=7.5)

    # 2. Unique Y breakpoints along left & right for chained vertical dimensions
    uy = sorted({round(pt[1], 2) for pt in outline})
    if len(uy) > 2:
        for i in range(len(uy) - 1):
            seg_m = uy[i + 1] - uy[i]
            if seg_m >= 1.0:
                _draw_cad_dim_v(ax, uy[i], uy[i + 1], min_x, min_x - pad_x * 0.36, f"{int(round(seg_m * 1000))} ({seg_m:.1f}m)", fontsize=7.0)
    # Overall vertical dimension (Left outer & Right)
    _draw_cad_dim_v(ax, min_y, max_y, min_x, min_x - pad_x * 0.68, f"{int(round(span_y * 1000))} ({span_y:.1f}m)", fontsize=7.8)
    _draw_cad_dim_v(ax, min_y, max_y, max_x, max_x + pad_x * 0.45, f"{int(round(span_y * 1000))}", fontsize=7.5)

    # 3. Array setback & row pitch callouts if modules exist
    if panels:
        m_xs = [pt[0] for m in panels for pt in (m.get("corners") or [])]
        m_ys = [pt[1] for m in panels for pt in (m.get("corners") or [])]
        if m_xs and m_ys:
            left_setback = max(0.0, min(m_xs) - min_x)
            bot_setback = max(0.0, min(m_ys) - min_y)
            if left_setback >= 0.3:
                _draw_cad_dim_h(ax, min_x, min(m_xs), min(m_ys), min(m_ys) - pad_y * 0.20, f"退距 {int(round(left_setback * 1000))}", fontsize=6.5)
            if bot_setback >= 0.3:
                _draw_cad_dim_v(ax, min_y, min(m_ys), min(m_xs), min(m_xs) - pad_x * 0.20, f"退距 {int(round(bot_setback * 1000))}", fontsize=6.5)
        # Get module dimensions from project equipment or design
        module_id = (project.get('equipment') or {}).get('module_id', '')
        module_pmax = float((design.get('statistics') or {}).get('module_pmax_w') or 0)
        mod_w = float((project.get('equipment') or {}).get('module_width_mm') or 0)
        mod_h = float((project.get('equipment') or {}).get('module_height_mm') or 0)
        mod_d = float((project.get('equipment') or {}).get('module_depth_mm') or 30)
        # Fallback: estimate dimensions from first module corners if available
        if (mod_w <= 0 or mod_h <= 0) and design.get('modules'):
            m0 = design['modules'][0]
            corners = m0.get('corners', [])
            if len(corners) >= 4:
                w = math.dist(corners[0][:2], corners[1][:2])
                h = math.dist(corners[1][:2], corners[2][:2])
                mod_w = int(round(max(w, h) * 1000))
                mod_h = int(round(min(w, h) * 1000))
                mod_d = 30
        row_pitch = float((design.get("params") or {}).get("row_spacing_m") or (design.get("statistics") or {}).get("row_spacing_m") or 0.0)
        if row_pitch > 0:
            ax.text(
                min_x + span_x * 0.02,
                max_y + pad_y * 0.14,
                f"阵列排距 D={int(round(row_pitch * 1000))}mm ({row_pitch:.2f}m)   组件规格 {int(mod_w)}×{int(mod_h)}×{int(mod_d)}mm   倾角 {(design.get('params') or {}).get('tilt_deg', 15)}°",
                fontsize=7.2,
                color="#0F172A",
                ha="left",
                va="bottom",
                zorder=8,
            )

    ax.set_xlim(min_x - pad_x, max_x + pad_x)
    ax.set_ylim(min_y - pad_y, max_y + pad_y)
    ax.set_aspect("equal", adjustable="box")


def _draw_gb_cad_sheet(fig, project: dict, version: int, sheet_code: str, sheet_title: str,
                       dc_kw: float, mod_count: int, tech_reqs: list[str], sheet_idx: int, total_sheets: int = 4,
                       module_label: str = "光伏组件", status_label: str = "规则预检"):
    """Draw a GB/T 14689 & GB/T 10609.1 standard CAD border, corner alignment marks, compact 4-line
    technical requirements, and bottom-right title block matching the user's CAD reference image."""
    fig.patch.set_facecolor("#FFFFFF")
    frame = fig.add_axes([0.0, 0.0, 1.0, 1.0], zorder=1)
    frame.set_xlim(0, 420)
    frame.set_ylim(0, 297)
    frame.axis("off")

    # 1. Outer thin frame & Inner thick GB frame (A3 420x297mm coordinates)
    ox0, oy0, ox1, oy1 = 10.0, 10.0, 410.0, 287.0
    ix0, iy0, ix1, iy1 = 25.0, 15.0, 405.0, 282.0
    frame.add_patch(Rectangle((ox0, oy0), ox1 - ox0, oy1 - oy0, fill=False, edgecolor="#0F172A", linewidth=0.7))
    frame.add_patch(Rectangle((ix0, iy0), ix1 - ix0, iy1 - iy0, fill=False, edgecolor="#0F172A", linewidth=1.8))

    # 2. Four corner alignment L-marks & four midpoint centering ticks
    cl = 7.0
    for cx, cy, dx, dy in [
        (ix0 - 4, iy1 + 2, 1, -1),
        (ix1 + 4, iy1 + 2, -1, -1),
        (ix0 - 4, iy0 - 2, 1, 1),
        (ix1 + 4, iy0 - 2, -1, 1),
    ]:
        frame.plot([cx, cx + dx * cl], [cy, cy], color="#0F172A", linewidth=1.1)
        frame.plot([cx, cx], [cy, cy + dy * cl], color="#0F172A", linewidth=1.1)
    mx, my = (ix0 + ix1) / 2, (iy0 + iy1) / 2
    frame.plot([mx, mx], [oy1, iy1 - 3.5], color="#0F172A", linewidth=0.9)
    frame.plot([mx, mx], [oy0, iy0 + 3.5], color="#0F172A", linewidth=0.9)
    frame.plot([ox0, ix0 + 3.5], [my, my], color="#0F172A", linewidth=0.9)
    frame.plot([ox1, ix1 - 3.5], [my, my], color="#0F172A", linewidth=0.9)

    # Top-right surface/unit callout + North arrow
    frame.text(ix1 - 28, iy1 - 8, "单位: mm (m)", fontsize=8.0, color="#0F172A", ha="right", va="center")
    frame.plot([ix1 - 22, ix1 - 18, ix1 - 14], [iy1 - 8, iy1 - 12, iy1 - 5], color="#0F172A", linewidth=1.0)
    frame.annotate("N", xy=(ix1 - 8, iy1 - 4), xytext=(ix1 - 8, iy1 - 14),
                   ha="center", va="bottom", fontsize=9.0, fontweight="bold", color="#0F172A",
                   arrowprops=dict(arrowstyle="<-", lw=1.3, color="#0F172A"))

    # 3. Compact 4-line 技术要求 directly above the bottom-right title block
    tx0, ty0 = 265.0, 61.5
    frame.text(tx0, ty0 + 17.5, "技术要求", fontsize=8.2, fontweight="bold", color="#0F172A")
    for idx, line in enumerate(tech_reqs[:4], 1):
        frame.text(tx0, ty0 + 17.5 - idx * 4.2, f"{idx}. {line}", fontsize=7.2, color="#0F172A")

    # 4. Standard GB/T 10609.1 Bottom-Right Title Block (flush with ix1=405, iy0=15; width=180mm, height=42mm)
    tb_x0, tb_y0, tb_w, tb_h = 225.0, 15.0, 180.0, 42.0
    tb_x1, tb_y1 = tb_x0 + tb_w, tb_y0 + tb_h
    frame.add_patch(Rectangle((tb_x0, tb_y0), tb_w, tb_h, facecolor="#FFFFFF", edgecolor="#0F172A", linewidth=1.5))

    # Horizontal grid lines inside title block (6 rows of 7mm = 42mm)
    row_h = 7.0
    for r in range(1, 6):
        y = tb_y0 + r * row_h
        # Left sub-table spans tb_x0 (225) to 305 across all 6 rows
        frame.plot([tb_x0, 305.0], [y, y], color="#0F172A", linewidth=0.7)
    # Right side horizontal dividers (x: 305 to 405)
    frame.plot([305.0, 405.0], [tb_y0 + 7.0, tb_y0 + 7.0], color="#0F172A", linewidth=0.7)
    frame.plot([305.0, 405.0], [tb_y0 + 14.0, tb_y0 + 14.0], color="#0F172A", linewidth=0.7)
    frame.plot([305.0, 405.0], [tb_y0 + 28.0, tb_y0 + 28.0], color="#0F172A", linewidth=0.9)

    # Vertical grid lines inside left table (225..305)
    for vx in [235.0, 245.0, 255.0, 275.0, 290.0, 305.0]:
        frame.plot([vx, vx], [tb_y0, tb_y1], color="#0F172A", linewidth=0.7)
    # Vertical grid lines on right side (305..405)
    frame.plot([350.0, 350.0], [tb_y0, tb_y1], color="#0F172A", linewidth=0.9)
    for vx in [316.0, 327.0, 338.0]:
        frame.plot([vx, vx], [tb_y0 + 7.0, tb_y0 + 21.0], color="#0F172A", linewidth=0.7)
    for vx in [368.0, 386.0]:
        frame.plot([vx, vx], [tb_y0, tb_y0 + 14.0], color="#0F172A", linewidth=0.7)

    # Populate GB standard labels
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y.%m.%d")
    headers_r3 = [(230, "标记"), (240, "处数"), (250, "分区"), (265, "更改文件号"), (282.5, "签名"), (297.5, "年、月、日")]
    for hx, htxt in headers_r3:
        frame.text(hx, tb_y0 + 24.5, htxt, fontsize=6.3, ha="center", va="center", color="#0F172A")

    roles = [
        (tb_y0 + 17.5, "设  计", "光筑AI", "标准化", "GB50797"),
        (tb_y0 + 10.5, "校  核", "规则预检", "借(通)用件登记", ""),
        (tb_y0 + 3.5, "工  艺", "CAD制图", "日  期", now_str),
    ]
    for ry, r1, v1, r2, v2 in roles:
        frame.text(230.0, ry, r1, fontsize=6.3, ha="center", va="center", color="#0F172A")
        frame.text(245.0, ry, v1, fontsize=6.0, ha="center", va="center", color="#0F172A")
        frame.text(265.0, ry, r2, fontsize=6.0, ha="center", va="center", color="#0F172A")
        frame.text(297.5, ry, v2, fontsize=6.0, ha="center", va="center", color="#0F172A")

    # Center cell: 材料标记 (305..350, y: 28..42)
    frame.text(327.5, tb_y0 + 37.5, "材料标记", fontsize=7.5, fontweight="bold", ha="center", va="center", color="#0F172A")
    frame.text(327.5, tb_y0 + 31.5, f"{module_label}×{mod_count}块 ({dc_kw:.1f}kWp)", fontsize=6.8, ha="center", va="center", color="#0F172A")

    # Stage / Weight / Scale (305..350, y: 7..21)
    for sx, stxt, sval in [(310.5, "阶段标记", "S"), (321.5, "重  量", "-"), (332.5, "比  例", "1:200"), (344.0, "版本", f"v{version}")]:
        frame.text(sx, tb_y0 + 17.5, stxt, fontsize=5.8, ha="center", va="center", color="#0F172A")
        frame.text(sx, tb_y0 + 10.5, sval, fontsize=6.5, fontweight="bold", ha="center", va="center", color="#0F172A")

    frame.text(327.5, tb_y0 + 3.5, f"共 {total_sheets} 张    第 {sheet_idx} 张", fontsize=6.8, ha="center", va="center", color="#0F172A")

    # Right cells: Unit / Drawing No / Title (350..405)
    frame.text(377.5, tb_y0 + 35.0, "光筑 GUANGZHU · 工程制图", fontsize=8.5, fontweight="bold", ha="center", va="center", color="#0F172A")
    frame.text(377.5, tb_y0 + 21.0, f"图号  {sheet_code} ({sheet_title})", fontsize=8.2, fontweight="bold", ha="center", va="center", color="#0F172A")
    proj_title = str(project.get("name") or project.get("id") or "厂房屋顶光伏项目")[:18]
    frame.text(359.0, tb_y0 + 10.5, "工程名称", fontsize=6.0, ha="center", va="center", color="#0F172A")
    frame.text(377.0, tb_y0 + 10.5, "图纸编号", fontsize=6.0, ha="center", va="center", color="#0F172A")
    frame.text(395.5, tb_y0 + 10.5, "校验状态", fontsize=6.0, ha="center", va="center", color="#0F172A")
    frame.text(359.0, tb_y0 + 3.5, proj_title[:8], fontsize=6.2, ha="center", va="center", color="#0F172A")
    frame.text(377.0, tb_y0 + 3.5, f"{sheet_code}-v{version}", fontsize=6.5, fontweight="bold", ha="center", va="center", color="#0F172A")
    frame.text(395.5, tb_y0 + 3.5, status_label, fontsize=6.2, ha="center", va="center", color="#0F172A")


def write_drawing_pdf(project: dict, design: dict, summary: dict, electric: dict, structure: dict,
                      economy: dict, rules: dict, version: int, output_path: Path):
    """Write 4-sheet A3 landscape GB-standard CAD blueprint PDF (drawing-v{version}.pdf) with clean geometry and dimensions."""
    dc_kw = float(design.get("statistics", {}).get("dc_kw") or summary.get("dc_kw") or 0.0)
    mod_count = len(design.get("modules") or [])
    params = design.get("params") or {}
    string_label, inverter_label = electrical.labels(electric)
    wind = structure.get("wind") or {}
    assumptions = wind.get("assumptions") or {}
    status_label = "硬性全过" if int((rules or {}).get("hard_failed", 0) or 0) == 0 else "待消缺"

    # Compute dynamic module label for title block material marking
    _mid = (project.get('equipment') or {}).get('module_id', '')
    _mpmax = float((design.get('statistics') or {}).get('module_pmax_w') or 0)
    module_label = _mid[:20] if _mid else f"{int(_mpmax)}W" if _mpmax > 0 else "光伏组件"

    with PdfPages(output_path) as pdf:
        # Sheet 1: PV-01 屋面光伏阵列总平面尺寸图
        fig = plt.figure(figsize=(16.54, 11.69), dpi=150)
        _draw_gb_cad_sheet(
            fig, project, version, "PV-01", "总平面排布尺寸图", dc_kw, mod_count,
            [
                f"未注尺寸单位为 mm(m)，屋面外沿退距 e={int(round(float(params.get('edge_setback_m', 1.0))*1000))}mm。",
                f"组件倾角 {params.get('tilt_deg', 15)}°，方位角 {params.get('azimuth_deg', 180)}°，前后排距 D={int(round(float(params.get('row_spacing_m', 1.2))*1000))}mm。",
                "阴影斜线区为屋面既有设备障碍物，虚线区为采光带与消防检修通道禁布区。",
                "所有阵列严禁跨越建筑变形缝、采光天窗及消防通道，施工前须现场复核红线尺寸。",
            ],
            sheet_idx=1,
            module_label=module_label,
            status_label=status_label,
        )
        ax_map = fig.add_axes([0.08, 0.28, 0.84, 0.63], zorder=2)
        _draw_roof_axes(ax_map, project, design, electric, structure, mode="layout")
        pdf.savefig(fig)
        plt.close(fig)

        # Sheet 2: PV-02 组串电气分区与交直流走线尺寸图
        fig = plt.figure(figsize=(16.54, 11.69), dpi=150)
        dc_cable_rows = [r for r in ((electric.get("cables") or {}).get("summary") or []) if isinstance(r, dict) and r.get("kind") == "dc"]
        dc_cable_model = (dc_cable_rows[0].get("cable_model") or dc_cable_rows[0].get("cable_id")) if dc_cable_rows else "PV1-F 1×4.0mm²"
        dc_cable_short = dc_cable_rows[0].get("cable_id", "PV1-F 1×4mm²") if dc_cable_rows else "PV1-F 1×4mm²"
        e_checks = electric.get("checks") or {}
        e01_limit = float((e_checks.get("E01") or {}).get("limit") or 1100.0)
        e10_limit = float((e_checks.get("E10") or {}).get("limit") or 2.0)
        _draw_gb_cad_sheet(
            fig, project, version, "PV-02", "组串与走线尺寸图", dc_kw, mod_count,
            [
                f"全站共 {electric.get('string_count', 0)} 串（{string_label}），配 {inverter_label} 台。",
                f"极寒开路电压 Voc={electric.get('voc_cold_v', 0):.1f}V≤{e01_limit:g}V，直流最大压降 {electric.get('dc_drop_pct_max', 0):.2f}%≤{e10_limit:g}%。",
                f"直流光伏线（{dc_cable_model[:28]}）沿金属桥架正交避障敷设，禁止屋面裸露散放。",
                "桥架跨越屋面通道及女儿墙处须加装防火金属盖板与过桥弯通。",
            ],
            sheet_idx=2,
            module_label=module_label,
            status_label=status_label,
        )
        ax_map = fig.add_axes([0.08, 0.28, 0.84, 0.63], zorder=2)
        _draw_roof_axes(ax_map, project, design, electric, structure, mode="electrical")
        pdf.savefig(fig)
        plt.close(fig)

        # Sheet 3: PV-03 GB 50009 风载分区与配重/夹具定位图
        fig = plt.figure(figsize=(16.54, 11.69), dpi=150)
        added_load = float(structure.get("average_kn_m2") or structure.get("added_kn_m2") or structure.get("dead_load_kn_m2") or 0.0)
        b_blocks = wind.get("ballast_blocks", wind.get("total_ballast_blocks", 0))
        c_clamps = wind.get("clamp_count", wind.get("total_clamps", 0))
        a_anchors = wind.get("anchor_count", 0)
        fix_str = f"压块 {b_blocks} 块" if b_blocks else (f"锚栓 {a_anchors} 个" if a_anchors else f"夹具 {c_clamps} 个")
        _draw_gb_cad_sheet(
            fig, project, version, "PV-03", "风载与配重施工图", dc_kw, mod_count,
            [
                f"按 GB 50009 50年一遇基本风压 w0={wind.get('basic_pressure_kpa', assumptions.get('w0_kn_m2', 0.45))}kN/m² 校核。",
                f"屋面允许活荷载 {(project.get('roof') or {}).get('load_capacity_kn_m2', 0.5):.2f}kN/m²，光伏附加荷载 {added_load:.3f}kN/m²。",
                f"全站抗风固定：{fix_str}（系统总质量 {structure.get('mass_kg', 0):,.0f}kg）。",
                "红色为屋面角部高风吸力加密区，黄色为屋檐边区，绿色为屋面中心标准区。",
            ],
            sheet_idx=3,
            module_label=module_label,
            status_label=status_label,
        )
        ax_map = fig.add_axes([0.08, 0.28, 0.84, 0.63], zorder=2)
        _draw_roof_axes(ax_map, project, design, electric, structure, mode="wind")
        pdf.savefig(fig)
        plt.close(fig)

        # Sheet 4: PV-04 并网电气一次系统图 (SLD)
        fig = plt.figure(figsize=(16.54, 11.69), dpi=150)
        ac_kw = float(electric.get("ac_kw") or (dc_kw / max(float(electric.get("dc_ac_ratio") or 1.1), 0.8)))
        min_kva = int(math.ceil(ac_kw / 0.8)) if ac_kw > 0 else 100
        std_kvas = [100, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500, 3150]
        rec_kva = next((s for s in std_kvas if s >= min_kva), std_kvas[-1])
        rated_a = ac_kw / (math.sqrt(3) * 0.4 * 0.95) if ac_kw > 0 else 0.0
        std_amps = [63, 100, 160, 250, 400, 630, 800, 1000, 1250, 1600, 2000, 2500]
        breaker_a = next((s for s in std_amps if s >= math.ceil(rated_a * 1.25)), std_amps[-1])
        icu_ka = 50 if rec_kva >= 1250 else 35
        svg_kvar = max(15, int(round(ac_kw * 0.2)))
        bess_units = max(1, min(8, int(round(max(ac_kw / 260.0, 1.0)))))

        _draw_gb_cad_sheet(
            fig, project, version, "PV-04", "电气一次系统图", dc_kw, mod_count,
            [
                f"并网总断路器 In={breaker_a}A (Icu≥{icu_ka}kA)，建议配电专变容量 ≥{rec_kva}kVA。",
                "并网柜内置防孤岛保护与双向 0.5S 计量表，进线 CT 检测到逆功率 <2s 快速切机。",
                "屋面四周敷设 40×4mm 热浸镀锌扁钢接闪网，组件边框用 BVR-6mm² 铜线跨接。",
                "防雷与保护接地联合接地电阻 R≤4.0Ω（GB 50057）。",
            ],
            sheet_idx=4,
            module_label=module_label,
            status_label=status_label,
        )
        ax_sld = fig.add_axes([0.08, 0.28, 0.84, 0.62], zorder=2)
        ax_sld.set_xlim(0, 100)
        ax_sld.set_ylim(0, 100)
        ax_sld.axis("off")

        # Top main busbar & key parameter header bar (y=86..96)
        ax_sld.add_patch(MplPolygon([(3, 86), (98, 86), (98, 96), (3, 96)],
                                    closed=True, facecolor="#F8FAFC", edgecolor="#0F172A", linewidth=1.1))
        ax_sld.plot([3, 98], [91.2, 91.2], color="#CBD5E1", linewidth=0.7)
        ax_sld.text(50.5, 93.6,
                    f"分布式光伏发电系统 0.4kV 并网一次主接线图  （直流装机 {dc_kw:.2f} kWp  /  额定交流 {ac_kw:.1f} kWac  /  容配比 {float(electric.get('dc_ac_ratio') or 1.1):.2f}）",
                    ha="center", va="center", fontsize=8.6, fontweight="bold", color="#0F172A")
        rule_map = {r.get("id"): r.get("value") for r in (rules.get("items") or []) if isinstance(r, dict)}
        vmp_low = float(electric.get("vmp_hot_v") or rule_map.get("E03") or 450.0)
        vmp_high = float(electric.get("vmp_cold_v") or rule_map.get("E04") or 850.0)
        voc_cold = float(electric.get("voc_cold_v") or rule_map.get("E01") or 1000.0)
        ax_sld.text(50.5, 88.6,
                    f"直流回路：{electric.get('string_count', 0)} 串（{string_label}） | 极寒 Voc={voc_cold:.1f}V | MPPT 工作电压 {vmp_low:.0f}~{vmp_high:.0f}V | 并网母线：380V/50Hz TN-S",
                    ha="center", va="center", fontsize=7.6, color="#334155")

        sld_boxes = [
            (3, 55, 17, 26, "屋面光伏组串阵列", f"{electric.get('string_count', 0)}串 / {mod_count}块\n{dc_kw:.1f} kWp\n{dc_cable_short}"),
            (23, 55, 17, 26, "组串式逆变器(DC/AC)", f"{inverter_label} 台\n{ac_kw:.1f} kWac\nMPPT + AFCI拉弧保护"),
            (43, 55, 17, 26, "光伏交流并网柜", f"断路器 {breaker_a}A\nIcu ≥ {icu_ka}kA\n失压脱扣 + 二级防雷SPD"),
            (63, 55, 17, 26, "关口计量与防逆流", "0.5S级双向智能电表\n防孤岛保护装置\n进线CT逆功率<2s切机"),
            (82, 55, 16, 26, "厂区配电专变与母线", f"建议专变 ≥ {rec_kva} kVA\n0.4kV / 10kV厂区母线\n装机≤专变容量80%"),
        ]
        for bx, by, bw, bh, title_t, body_t in sld_boxes:
            ax_sld.add_patch(MplPolygon([(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh)],
                                        closed=True, facecolor="#FFFFFF", edgecolor="#0F172A", linewidth=1.3))
            ax_sld.plot([bx, bx + bw], [by + bh - 8.5, by + bh - 8.5], color="#0F172A", linewidth=0.8)
            ax_sld.text(bx + bw / 2, by + bh - 4.5, title_t, ha="center", va="center", fontsize=8.5, fontweight="bold", color="#0F172A")
            ax_sld.text(bx + bw / 2, by + (bh - 8.5) / 2, body_t, ha="center", va="center", fontsize=7.6, color="#0F172A")

        for x0, x1 in [(20, 23), (40, 43), (60, 63), (80, 82)]:
            ax_sld.annotate("", xy=(x1, 68), xytext=(x0, 68), arrowprops=dict(arrowstyle="-|>", lw=1.4, color="#0F172A"))

        ax_sld.plot([51.5, 51.5], [55, 42], color="#0F172A", linestyle="--", linewidth=1.1)
        ax_sld.plot([28, 74], [42, 42], color="#0F172A", linestyle="--", linewidth=1.1)
        ax_sld.plot([28, 28], [42, 35], color="#0F172A", linewidth=1.1)
        ax_sld.plot([74, 74], [42, 35], color="#0F172A", linewidth=1.1)

        sub_boxes = [
            (10, 10, 36, 25, f"SVG 动态无功补偿柜 (±{svg_kvar} kVar)",
             "GB/T 14549 电能质量标准  |  并网点 cosφ ≥ 0.95  |  THDi ≤ 3%"),
            (54, 10, 38, 25, f"工商业储能接口 ({bess_units}×100kW/215kWh)",
             "磷酸铁锂液冷机柜 + BMS/EMS/PCS 协同控制  |  午间余电消纳与削峰填谷"),
        ]
        for bx, by, bw, bh, title_t, body_t in sub_boxes:
            ax_sld.add_patch(MplPolygon([(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh)],
                                        closed=True, facecolor="#FFFFFF", edgecolor="#0F172A", linewidth=1.2))
            ax_sld.plot([bx, bx + bw], [by + bh - 8.5, by + bh - 8.5], color="#0F172A", linewidth=0.7)
            ax_sld.text(bx + bw / 2, by + bh - 4.5, title_t, ha="center", va="center", fontsize=8.2, fontweight="bold", color="#0F172A")
            ax_sld.text(bx + bw / 2, by + (bh - 8.5) / 2, body_t, ha="center", va="center", fontsize=7.4, color="#0F172A")

        pdf.savefig(fig)
        plt.close(fig)


def write_report_pdf(project: dict, design: dict, summary: dict, electric: dict, structure: dict,
                     economy: dict, rules: dict, version: int, output_path: Path):
    """Write 4-page A4 engineering proposal report PDF (report-v{version}.pdf)."""
    dc_kw = float(design.get("statistics", {}).get("dc_kw") or summary.get("dc_kw") or 0.0)
    mod_count = len(design.get("modules") or [])
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

    with PdfPages(output_path) as pdf:
        # Page 1: Executive Summary & Equipment Table
        fig = plt.figure(figsize=(8.27, 11.69), dpi=150)
        fig.text(0.06, 0.94, "光筑 GUANGZHU — 分布式光伏工程初步设计方案书", fontsize=15, fontweight="bold", color="#0F172A")
        fig.text(0.06, 0.912, f"项目名称：{project.get('name', project.get('id'))}    |    方案版本：v{version}    |    生成时间：{now_str}",
                 fontsize=9.5, color="#334155")
        fig.text(0.06, 0.892, "一、项目概况与核心技术经济指标", fontsize=11.5, fontweight="bold", color="#1E3A8A")

        ax1 = fig.add_axes([0.06, 0.54, 0.88, 0.33])
        ax1.axis("off")
        loc = project.get("site") or project.get("location") or {}
        eco_params = economy.get("params") or {}
        yield_obj = summary.get("yield_kwh") or summary.get("yield") or {}
        p50_kwh = float(yield_obj.get("p50") or 0.0)
        low_kwh = float(yield_obj.get("p90") or yield_obj.get("low") or 0.0)
        per_kw_h = float(yield_obj.get("per_kw") or summary.get("specific_yield_kwh_kwp") or (p50_kwh / dc_kw if dc_kw > 0 else 0.0))
        shading_obj = summary.get("shading")
        shading_loss_pct = float(shading_obj.get("avg_loss_pct", 0.0) if isinstance(shading_obj, dict) else summary.get("shading_loss_pct", 0.0))
        dead_load_kn = float(structure.get("added_kn_m2") or structure.get("average_kn_m2") or structure.get("dead_load_kn_m2") or 0.0)
        unit_capex = float((economy.get("costs") or {}).get("effective_cny_per_w") or eco_params.get("capex_cny_per_w") or 3.0)
        lcoe_val = economy.get("lcoe_cny_kwh")
        lcoe_text = f"度电成本 LCOE = {float(lcoe_val):.3f} 元/kWh" if lcoe_val is not None else f"折现率 {float(eco_params.get('discount_rate', 0.06))*100:.1f}%"
        rule_items = rules.get("items") or []
        total_rules = len(rule_items) or int(rules.get("total") or 18)
        passed_rules = sum(1 for item in rule_items if isinstance(item, dict) and item.get("status") == "pass")
        summary_rows = [
            ["指标类别", "指标名称", "计算结果", "工程说明 / 数据来源"],
            ["规模排布", "直流装机容量", f"{dc_kw:.2f} kWp ({mod_count} 块)", f"倾角 {design.get('params', {}).get('tilt_deg', 15)}° / 方位角 {design.get('params', {}).get('azimuth_deg', 180)}°"],
            ["发电预测", "首年基准年发电估算", f"{p50_kwh:,.0f} kWh", "NASA POWER 8760h 逐时太阳辐射驱动"],
            ["发电预测", "多模型下界 / 保守估算", f"{low_kwh:,.0f} kWh", f"首年等效满发 {per_kw_h:.0f} h"],
            ["遮挡损耗", "年度平均三维遮挡损失", f"{shading_loss_pct:.2f} %", "含女儿墙、天窗、机房、排气筒与周边建筑遮挡"],
            ["电气组串", "组串数 / 逆变器台数", f"{electric.get('string_count', 0)} 串 / {electric.get('inverter_count', 0)} 台", f"容配比 {electric.get('dc_ac_ratio', 1.1):.2f}，极寒 Voc={electric.get('voc_cold_v', 0):.1f}V"],
            ["结构荷载", "系统附加恒载估算", f"{dead_load_kn:.3f} kN/m²", f"屋面允许活荷载 {(project.get('roof') or {}).get('load_capacity_kn_m2', 0.5):.2f} kN/m²"],
            ["投资收益", "工程总造价 (CAPEX)", f"{economy.get('capex_cny', 0):,.0f} 元", f"折合单瓦造价 {unit_capex:.2f} 元/W"],
            ["投资收益", "静态投资回收期", f"{economy.get('payback_years', 0):.2f} 年", f"全投资内部收益率 IRR = {economy.get('irr_pct', 0):.2f}%"],
            ["投资收益", "25年净现值 (NPV)", f"{economy.get('npv_cny', 0):,.0f} 元", lcoe_text],
            ["规范校核", f"{total_rules}项工程规范预检", f"通过 {passed_rules}/{total_rules}（硬性未过 {rules.get('hard_failed', 0)} 项）", f"坐标 ({loc.get('lat', 32.45):.3f}°N, {loc.get('lon', 119.92):.3f}°E)"],
        ]
        tbl1 = ax1.table(cellText=summary_rows[1:], colLabels=summary_rows[0], loc="upper center", cellLoc="left",
                         colWidths=[0.16, 0.25, 0.24, 0.35])
        tbl1.auto_set_font_size(False)
        tbl1.set_fontsize(8.0)
        tbl1.scale(1.0, 1.55)
        for (r, c), cell in tbl1.get_celld().items():
            if r == 0:
                cell.set_facecolor("#0F172A")
                cell.set_text_props(color="#FFFFFF", fontweight="bold")
            else:
                cell.set_facecolor("#F8FAFC" if r % 2 == 1 else "#FFFFFF")
            cell.set_edgecolor("#CBD5E1")

        fig.text(0.06, 0.49, "二、屋顶光伏阵列总平面排布图", fontsize=11.5, fontweight="bold", color="#1E3A8A")
        ax_layout = fig.add_axes([0.08, 0.06, 0.84, 0.40])
        _draw_roof_axes(ax_layout, project, design, electric, structure, mode="layout")
        pdf.savefig(fig)
        plt.close(fig)

        # Page 2: Monthly Generation Chart & Rule Compliance Table
        fig = plt.figure(figsize=(8.27, 11.69), dpi=150)
        fig.text(0.06, 0.94, f"三、逐月发电消纳分析与 {total_rules} 项工程规范审查表（v{version}）", fontsize=13, fontweight="bold", color="#0F172A")

        monthly = (economy.get("self_use") or {}).get("monthly") or []
        ax_bar = fig.add_axes([0.09, 0.62, 0.84, 0.27])
        if monthly:
            months = [f"{m.get('month', i+1)}月" for i, m in enumerate(monthly)]
            self_kwh = [float(m.get("self_use_kwh") or 0) for m in monthly]
            exp_kwh = [float(m.get("export_kwh") or 0) for m in monthly]
            ax_bar.bar(months, self_kwh, label="自发自用电量 (kWh)", color="#059669")
            ax_bar.bar(months, exp_kwh, bottom=self_kwh, label="余电上网电量 (kWh)", color="#3B82F6")
            ax_bar.set_title("首年 1-12 月发电消纳与余电上网分布", fontsize=10, fontweight="bold")
            ax_bar.set_ylabel("电量 (kWh)", fontsize=8.5)
            ax_bar.legend(fontsize=8, loc="upper right")
            ax_bar.grid(axis="y", linestyle=":", alpha=0.6)
            ax_bar.tick_params(labelsize=8)
        else:
            ax_bar.text(0.5, 0.5, "逐月消纳数据按年度综合自用比例折算", ha="center", va="center", fontsize=10)
            ax_bar.axis("off")

        ax_rules = fig.add_axes([0.06, 0.05, 0.88, 0.52])
        ax_rules.axis("off")
        rule_rows = [["规则编号", "审查类别 / 规范条目", "级别", "当前计算值", "规范限值", "结论"]]
        for item in (rules.get("items") or [])[:18]:
            status_zh = {"pass": "通过", "fail": "未通过", "warn": "提示", "skip": "不适用"}.get(item.get("status"), str(item.get("status")))
            lvl_zh = "硬性" if item.get("level") == "hard" else "建议"
            rule_rows.append([
                str(item.get("id", "")),
                str(item.get("name_zh") or item.get("name") or "")[:20],
                lvl_zh,
                str(item.get("value", "-"))[:18],
                str(item.get("limit", "-"))[:18],
                status_zh,
            ])
        tbl_r = ax_rules.table(cellText=rule_rows[1:], colLabels=rule_rows[0], loc="upper center", cellLoc="left",
                               colWidths=[0.11, 0.31, 0.09, 0.19, 0.19, 0.11])
        tbl_r.auto_set_font_size(False)
        tbl_r.set_fontsize(7.6)
        tbl_r.scale(1.0, 1.42)
        for (r, c), cell in tbl_r.get_celld().items():
            if r == 0:
                cell.set_facecolor("#1E3A8A")
                cell.set_text_props(color="#FFFFFF", fontweight="bold")
            else:
                cell.set_facecolor("#F8FAFC" if r % 2 == 1 else "#FFFFFF")
            cell.set_edgecolor("#CBD5E1")
        pdf.savefig(fig)
        plt.close(fig)

        # Page 3: BOM Cost Breakdown & 25-Year Cashflow Table
        fig = plt.figure(figsize=(8.27, 11.69), dpi=150)
        fig.text(0.06, 0.94, f"四、BOM 工程造价清单与 25 年财务现金流测算表（v{version}）", fontsize=13, fontweight="bold", color="#0F172A")

        ax_bom = fig.add_axes([0.06, 0.55, 0.88, 0.35])
        ax_bom.axis("off")
        bom_rows = [["序号", "分项工程 / 材料名称", "数量", "单位", "单价 (元)", "合价 (元)", "定额说明"]]
        for idx, item in enumerate(((economy.get("costs") or {}).get("items") or [])[:10], start=1):
            src_note = (item.get("source") or {}).get("来源标题") if isinstance(item.get("source"), dict) else None
            bom_rows.append([
                str(idx),
                str(item.get("name") or item.get("key") or "")[:18],
                f"{item.get('quantity', 0):,.1f}" if isinstance(item.get("quantity"), (int, float)) else str(item.get("quantity", "-")),
                str(item.get("unit") or "-"),
                f"{item.get('unit_price_cny', 0):,.2f}" if isinstance(item.get("unit_price_cny"), (int, float)) else "-",
                f"{item.get('subtotal_cny', 0):,.0f}",
                str(item.get("note") or src_note or "工程估算（示意）")[:16],
            ])
        tbl_b = ax_bom.table(cellText=bom_rows[1:], colLabels=bom_rows[0], loc="upper center", cellLoc="left",
                             colWidths=[0.07, 0.25, 0.12, 0.08, 0.13, 0.15, 0.20])
        tbl_b.auto_set_font_size(False)
        tbl_b.set_fontsize(7.6)
        tbl_b.scale(1.0, 1.48)
        for (r, c), cell in tbl_b.get_celld().items():
            if r == 0:
                cell.set_facecolor("#065F46")
                cell.set_text_props(color="#FFFFFF", fontweight="bold")
            else:
                cell.set_facecolor("#F8FAFC" if r % 2 == 1 else "#FFFFFF")
            cell.set_edgecolor("#CBD5E1")

        ax_cf = fig.add_axes([0.06, 0.06, 0.88, 0.45])
        ax_cf.axis("off")
        cf_rows = [["运营年份", "年发电量 (kWh)", "自用电量 (kWh)", "上网电量 (kWh)", "当年电费收益 (元)", "运维成本 (元)", "净现金流 (元)", "累计净现金流 (元)"]]
        cashflows = economy.get("cashflows") or []
        sample_years = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25]
        for row in cashflows:
            if row.get("year") in sample_years:
                cf_rows.append([
                    f"第 {row['year']} 年",
                    f"{row.get('generation_kwh', 0):,.0f}",
                    f"{row.get('self_use_kwh', 0):,.0f}",
                    f"{row.get('export_kwh', 0):,.0f}",
                    f"{row.get('income_cny', 0):,.0f}",
                    f"{row.get('om_cny', 0):,.0f}",
                    f"{row.get('net_cny', 0):,.0f}",
                    f"{row.get('cumulative_cny', 0):,.0f}",
                ])
        tbl_c = ax_cf.table(cellText=cf_rows[1:], colLabels=cf_rows[0], loc="upper center", cellLoc="right",
                            colWidths=[0.11, 0.13, 0.13, 0.13, 0.13, 0.11, 0.13, 0.13])
        tbl_c.auto_set_font_size(False)
        tbl_c.set_fontsize(7.4)
        tbl_c.scale(1.0, 1.40)
        for (r, c), cell in tbl_c.get_celld().items():
            if r == 0:
                cell.set_facecolor("#0F172A")
                cell.set_text_props(color="#FFFFFF", fontweight="bold")
            else:
                cell.set_facecolor("#F8FAFC" if r % 2 == 1 else "#FFFFFF")
            cell.set_edgecolor("#CBD5E1")
        pdf.savefig(fig)
        plt.close(fig)


def write_pdf_deliverables(project_id: str, version: int, directory: Path, base_dir: Path | None = None) -> dict[str, Path]:
    """Generate both report-v{version}.pdf and drawing-v{version}.pdf inside directory."""
    base = Path(base_dir) if base_dir is not None else storage._path(project_id)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    project = _read_json(base / "project.json", {})
    design = _read_json(base / f"designs/v{version}.json", {})
    summary = _read_json(base / f"analysis/v{version}/summary.json", {})
    electric = _read_json(base / f"analysis/v{version}/electrical.json", {})
    structure = _read_json(base / f"analysis/v{version}/structure.json", {})
    economy = _read_json(base / f"analysis/v{version}/economics.json", {})
    rules = _read_json(base / f"analysis/v{version}/rules.json", {})

    drawing_pdf = directory / f"drawing-v{version}.pdf"
    report_pdf = directory / f"report-v{version}.pdf"

    write_drawing_pdf(project, design, summary, electric, structure, economy, rules, version, drawing_pdf)
    write_report_pdf(project, design, summary, electric, structure, economy, rules, version, report_pdf)
    return {"drawing_pdf": drawing_pdf, "report_pdf": report_pdf}

