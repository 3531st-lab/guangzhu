"""Geometric rule checks for layouts whose row labels are no longer spatial."""
import math

import numpy as np

from .layout import true_solar_times
from .shading_geometry import build_scene, ray_hits, sample_points, sun_vector
from .solar import sun_position


def winter_module_shadows(project, design):
    """Sample mutual module shading, excluding buildings from the row-only rule."""
    if not design.modules:
        return set()
    scene_project = project.model_copy(deep=True)
    scene_project.roof.obstacles = []
    scene_project.roof.surroundings = []
    scene_project.roof.parapet_segments = []
    scene = build_scene(scene_project, design)
    points = sample_points(design)
    owners = np.broadcast_to(np.arange(len(design.modules))[:, None, None], points.shape[:-1])
    corners = np.asarray([module.corners for module in design.modules])
    normals = np.cross(corners, np.roll(corners, -1, axis=1)).sum(axis=1)
    normals[normals[:, 2] < 0] *= -1
    start, end = design.params.winter_window_hours
    hours = np.linspace(start, end, math.ceil((end - start) * 12) + 1)
    times = true_solar_times(project.site.lon, hours)
    positions = sun_position(times, project.site.lat, project.site.lon)
    blocked = np.zeros(len(design.modules), dtype=bool)
    for position in positions.itertuples():
        if position.elevation <= 0:
            continue
        direction = sun_vector(position.elevation, position.azimuth)
        hits = ray_hits(scene, points, direction, owners)
        blocked |= (hits == 'front_row').any(axis=(1, 2)) & (normals @ direction > 0)
    return {module.id for module, shaded in zip(design.modules, blocked, strict=True) if shaded}
