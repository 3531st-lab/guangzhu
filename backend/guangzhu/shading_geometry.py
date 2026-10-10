"""Exact planar ray intersections and roof-plane shadow projections."""

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .models import Design, GzError, obstacle_polygon, validate_project, validated
from .solar import sun_position
from .roofplane import elevation, minimum, path3d

EPS = 1e-8


@dataclass
class Scene:
    project: object
    design: Design
    faces: list
    owners: np.ndarray
    causes: np.ndarray
    identifiers: list
    normals: np.ndarray
    anchors: np.ndarray
    bases: dict
    face_groups: list


def build_scene(project, design):
    project, design = validate_project(project), validated(Design, design, "DESIGN_INVALID")
    from .installation import effective
    project = effective(project, design)
    faces, owners, causes, identifiers, bases = [], [], [], [], {}

    def add(vertices, owner, cause, identifier):
        faces.append(np.asarray(vertices, dtype=float))
        owners.append(owner)
        causes.append(cause)
        identifiers.append(identifier)

    if project.roof.type in ('pitched', 'carport'):
        from .roofplane import plane_elevation
        for plane in project.roof.planes:
            add([[*p, plane_elevation(plane, p)] for p in plane.outline], -1, 'roof', f'P{plane.id}')

    for obstacle in [*project.roof.obstacles, *project.roof.surroundings]:
        xy = np.asarray(obstacle_polygon(obstacle).exterior.coords[:-1])
        z = [elevation(project.roof, p) if obstacle in project.roof.obstacles and project.roof.type != 'carport' else 0 for p in xy]
        if project.roof.type == 'pitched' and obstacle in project.roof.obstacles:
            z = [minimum(project.roof, Polygon(xy))] * len(xy)
        base = np.c_[xy, z]
        top = np.c_[xy, np.asarray(z) + obstacle.height_m]
        bases[obstacle.id] = Polygon(xy)
        add(top, -1, obstacle.id, obstacle.id)
        for i in range(len(xy)):
            j = (i + 1) % len(xy)
            add([base[i], base[j], top[j], top[i]], -1, obstacle.id, obstacle.id)
    if project.roof.parapet_height_m > 0:
        outline = np.asarray(project.roof.outline)
        for i, a in enumerate(outline):
            b = outline[(i + 1) % len(outline)]
            height = project.roof.parapet_height_m
            za, zb = elevation(project.roof, a), elevation(project.roof, b)
            if project.roof.type == 'pitched':
                points = path3d(project.roof, [a, b])
                for first, last in zip(points, points[1:]):
                    top = [[*p[:2], p[2] + height] for p in (last, first)]
                    add([first, last, *top], -1, 'parapet', 'parapet')
                continue
            add([[*a, za], [*b, zb], [*b, zb + height], [*a, za + height]], -1, "parapet", "parapet")
    for owner, module in enumerate(design.modules):
        corners = np.asarray(module.corners)
        # Stored millimetre-rounded corners can be slightly noncoplanar.
        for indices in [[0, 1, 2], [0, 2, 3]]:
            add(corners[indices], owner, "front_row", module.id)
    normals = np.asarray([np.cross(face, np.roll(face, -1, axis=0)).sum(axis=0) for face in faces]).reshape(-1, 3)
    if len(normals):
        normals /= np.linalg.norm(normals, axis=1)[:, None]
    face_groups = []
    for count in sorted({len(face) for face in faces}):
        indices = np.array([i for i, face in enumerate(faces) if len(face) == count])
        face_groups.append((indices, np.array([faces[i] for i in indices])))
    return Scene(project, design, faces, np.asarray(owners), np.asarray(causes, dtype=object), identifiers,
                 normals, np.asarray([face[0] for face in faces]).reshape(-1, 3), bases, face_groups)


def sample_points(design):
    corners = np.asarray([module.corners for module in design.modules], dtype=float).reshape(-1, 4, 3)
    fractions = np.array([1 / 6, 1 / 2, 5 / 6])
    u, v = np.meshgrid(fractions, fractions, indexing="ij")
    def edge(a, b):
        return (corners[:, a] - corners[:, b])[:, None, None]
    first = corners[:, 0, None, None] + u[..., None] * edge(1, 0) + v[..., None] * edge(2, 1)
    second = corners[:, 0, None, None] + u[..., None] * edge(2, 3) + v[..., None] * edge(3, 0)
    return np.where((u >= v)[None, ..., None], first, second)


def sun_vector(elevation, azimuth):
    alpha, bearing = np.radians([elevation, azimuth])
    return np.array([np.cos(alpha) * np.sin(bearing), np.cos(alpha) * np.cos(bearing), np.sin(alpha)])


def _project(vertices, vector):
    return vertices[..., :2] - vertices[..., 2, None] * vector[:2] / vector[2]


def ray_candidates(scene, points, sun_vector, owners):
    """Return all positive intersections, ordered by ray, distance and face."""
    points = np.asarray(points, dtype=float)
    shape, flat = points.shape[:-1], points.reshape(-1, 3)
    vector = np.asarray(sun_vector, dtype=float)
    if not len(flat) or not scene.faces or vector[2] <= 0:
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)
    denominator = scene.normals @ vector
    face_indices = np.flatnonzero(np.abs(denominator) > EPS)
    polygons = np.empty(len(scene.faces), dtype=object)
    for indices, vertices in scene.face_groups:
        polygons[indices] = shapely.polygons(_project(vertices, vector))
    pairs = STRtree(polygons[face_indices]).query(shapely.points(_project(flat, vector)), predicate="intersects")
    if not pairs.shape[1]:
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)
    point_index, face_index = pairs[0], face_indices[pairs[1]]
    distance = np.einsum("ij,ij->i", scene.anchors[face_index] - flat[point_index], scene.normals[face_index]) / denominator[face_index]
    same_owner = scene.owners[face_index] == np.broadcast_to(owners, shape).reshape(-1)[point_index]
    valid = (distance > EPS) & (~same_owner | (scene.owners[face_index] < 0))
    point_index, face_index, distance = point_index[valid], face_index[valid], distance[valid]
    # Stable face order resolves only physically coincident nearest surfaces.
    order = np.lexsort((face_index, distance, point_index))
    return point_index[order].astype(np.int32), face_index[order].astype(np.int32)


def candidate_hits(scene, shape, candidates, active_owners=None):
    point_index, face_index = candidates
    if active_owners is not None and len(face_index):
        owners = scene.owners[face_index]
        keep = owners < 0
        keep[~keep] = active_owners[owners[~keep]]
        point_index, face_index = point_index[keep], face_index[keep]
    output = np.full(int(np.prod(shape)), "", dtype=object)
    unique, first = np.unique(point_index, return_index=True)
    output[unique] = scene.causes[face_index[first]]
    return output.reshape(shape)


def ray_hits(scene, points, sun_vector, owners):
    """STRtree culls projected faces; positive plane distance gives nearest hit."""
    return candidate_hits(scene, np.asarray(points).shape[:-1], ray_candidates(scene, points, sun_vector, owners))


def beam_fractions(hits, orientations):
    hits = np.asarray(hits, dtype=object)
    segments = hits.copy()
    landscape = np.asarray(orientations) == "landscape"
    segments[landscape] = hits[landscape].swapaxes(1, 2)
    blocked = (segments != "").any(axis=2)
    fraction = blocked.mean(axis=1)
    causes = sorted(set(segments.ravel()) - {""})
    if not causes:
        return fraction, {}
    votes = np.stack([(segments == cause).sum(axis=2) for cause in causes])
    chosen = votes.argmax(axis=0)  # sorted causes make a tied vote lexicographic
    return fraction, {cause: ((chosen == i) & blocked).sum(axis=1) / 3 for i, cause in enumerate(causes)}


def _sun_at(lat, lon, time):
    try:
        stamp = pd.Timestamp(time)
        if pd.isna(stamp) or stamp.tzinfo is None:
            raise ValueError("explicit timezone required")
        sun = sun_position(pd.DatetimeIndex([stamp]), lat, lon).iloc[0]
        return float(sun.elevation), float(sun.azimuth)
    except (TypeError, ValueError, OverflowError) as error:
        raise GzError("SHADING_INPUT_INVALID", "太阳位置需要有效经纬度与带时区的时刻", "填写有效经纬度与ISO时刻，例如2026-10-05T10:00+08:00") from error


def shadow_polygons(scene, time):
    elevation, azimuth = _sun_at(scene.project.site.lat, scene.project.site.lon, time)
    if elevation <= 0:
        return {}
    vector = sun_vector(elevation, azimuth)
    pieces = {identifier: [base] for identifier, base in scene.bases.items()}
    for identifier, face in zip(scene.identifiers, scene.faces):
        polygon = Polygon(_project(face, vector))
        if polygon.area > EPS:
            pieces.setdefault(identifier, []).append(polygon)
    return {identifier: unary_union(polygons) for identifier, polygons in pieces.items()}


def pole_shadow(lat, lon, time, height_m):
    try:
        if not math.isfinite(height_m) or height_m <= 0:
            raise ValueError("height must be positive")
    except (TypeError, ValueError) as error:
        raise GzError("SHADING_INPUT_INVALID", "杆高必须是大于0的有限数值", "填写实测杆高，单位米") from error
    elevation, azimuth = _sun_at(lat, lon, time)
    if elevation <= 0:
        raise GzError("SUN_BELOW_HORIZON", "太阳在地平线下，没有可测量的直射影子", "选用当地日出到日落之间的时刻")
    return dict(sun_elevation_deg=elevation, sun_azimuth_deg=azimuth,
                shadow_length_m=height_m / math.tan(math.radians(elevation)), shadow_direction_deg=(azimuth + 180) % 360)
