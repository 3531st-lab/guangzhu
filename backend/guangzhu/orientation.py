"""Shared surface/orientation groups; legacy designs retain their exact view."""

from collections import defaultdict
import math
import numpy as np


def key(module):
    surface = int(module.id.split("-", 1)[0][1:]) if module.id.startswith("P") else 0
    return surface, module.tilt, module.azimuth


def groups(design):
    grouped = defaultdict(list)
    for module in design.modules:
        grouped[key(module)].append(module)
    if not grouped:
        grouped[0, design.params.tilt_deg, design.params.azimuth_deg] = []
    return grouped


def views(design):
    grouped = groups(design)
    for identity, modules in grouped.items():
        if not modules:
            yield identity, design
            continue
        legacy = identity[0] == 0 and all(key(m) == identity and m.orientation == design.params.orientation
                                        for m in [*modules, *design.removed_modules])
        if legacy and len(grouped) == 1 and identity[1:] == (design.params.tilt_deg, design.params.azimuth_deg):
            yield identity, design
            continue
        members = [m for m in [*modules, *design.removed_modules] if key(m) == identity]
        params = design.params.model_copy(update=dict(tilt_deg=identity[1], azimuth_deg=identity[2],
                                                       rows_per_rack=max(m.tier for m in members)))
        if identity[0]:
            params = params.model_copy(update=dict(surface=True))
        back = np.array([-math.sin(math.radians(identity[2])), -math.cos(math.radians(identity[2]))])
        racks = defaultdict(list)
        active = {(m.row, m.col) for m in modules}
        for module in members:
            if (module.row, module.col) in active:
                racks[module.row, module.col].extend(np.array(module.corners)[:, :2] @ back)
        length = max(max(points) - min(points) for points in racks.values()) / math.cos(math.radians(identity[1]))
        rows = sorted({m.row for m in modules})
        positions = [float(np.mean([min(points) for (row, _), points in racks.items() if row == number])) for number in rows]
        gaps = np.abs(np.diff(positions))
        pitch = float(gaps.min()) if len(gaps) and gaps.min() > 0 else length
        stats = dict(design.statistics, gcr=length / pitch, row_spacing_m=pitch, group_row_positions=positions)
        yield identity, design.model_copy(update=dict(modules=modules, params=params, statistics=stats))


def simulations(project, design, *, offline=False):
    from . import economics, yieldsim
    loss = economics.load_assumptions()['design_system_loss_pct']['value']
    cache = {}
    for identity, view in views(design):
        angle = identity[1:]
        if angle not in cache:
            cache[angle] = yieldsim.simulate_design_yields(project.site.lat, project.site.lon,
                            tilt=angle[0], azimuth=angle[1], loss_percent=loss, offline=offline, module_id=project.equipment.module_id)
        yield identity, view, cache[angle]
