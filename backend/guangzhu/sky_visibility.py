"""Deterministic sky-view integration for manually placed, irregular PV layouts.

Equal intervals in azimuth and sin(elevation) represent equal solid angles.
The receiver cosine comes from the physical module corners, not row numbers or
the original layout pitch. This is an isotropic sky approximation; the caller
applies its visibility factor to the existing annual Perez sky irradiance.
"""
from collections import defaultdict

import numpy as np

from .shading_geometry import ray_hits


AZIMUTH_SAMPLES = 16
ELEVATION_SAMPLES = 8


def sky_visibility(design, scene, points, owners, *, hits=ray_hits):
    count = len(design.modules)
    if not count:
        return np.zeros(0), {}
    corners = np.asarray([module.corners for module in design.modules], dtype=float)
    normals = np.cross(corners, np.roll(corners, -1, axis=1)).sum(axis=1)
    magnitudes = np.linalg.norm(normals, axis=1)
    if not np.isfinite(magnitudes).all() or (magnitudes <= 1e-10).any():
        raise ValueError('组件几何退化，无法计算天空可见度')
    normals /= magnitudes[:, None]
    normals[normals[:, 2] < 0] *= -1
    received = np.zeros(count)
    blocked = defaultdict(lambda: np.zeros(count))
    for elevation_index in range(ELEVATION_SAMPLES):
        z = (elevation_index + .5) / ELEVATION_SAMPLES
        horizontal = np.sqrt(1 - z * z)
        for azimuth_index in range(AZIMUTH_SAMPLES):
            angle = 2 * np.pi * (azimuth_index + .5) / AZIMUTH_SAMPLES
            direction = np.array([horizontal * np.sin(angle), horizontal * np.cos(angle), z])
            weights = np.maximum(normals @ direction, 0)
            received += weights
            if not weights.any():
                continue
            intersections = hits(scene, points, direction, owners)
            for cause in np.unique(intersections):
                if cause:
                    blocked[str(cause)] += weights * (intersections == cause).mean(axis=(1, 2))
    shares = {cause: np.divide(values, received, out=np.zeros(count), where=received > 0)
              for cause, values in blocked.items()}
    fraction = np.clip(sum(shares.values(), np.zeros(count)), 0, 1)
    return fraction, shares
