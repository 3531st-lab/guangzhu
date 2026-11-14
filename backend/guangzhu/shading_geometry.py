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
from .roofplane import elevation, minimum, parapet_faces

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
    cause_names: tuple = ()
    cause_codes: np.ndarray | None = None
    is_convex: np.ndarray | None = None
    group_arity: np.ndarray | None = None
    group_slot: np.ndarray | None = None
    face_zmax: np.ndarray | None = None


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
        from .roofplane import plane_elevation, step_walls
        for plane in project.roof.planes:
            add([[*p, plane_elevation(plane, p)] for p in plane.outline], -1, 'roof', f'P{plane.id}')
        for index, wall in enumerate(step_walls(project.roof)):
            add(wall, -1, 'roof', f'roof-step-{index + 1}')

    for obstacle in [*project.roof.obstacles, *project.roof.surroundings]:
        xy = np.asarray(obstacle_polygon(obstacle).exterior.coords[:-1])
        z = [elevation(project.roof, p) if obstacle in project.roof.obstacles and project.roof.type != 'carport' else 0 for p in xy]
        if project.roof.type == 'pitched' and obstacle in project.roof.obstacles:
            z = [minimum(project.roof, Polygon(xy), obstacle.plane_id)] * len(xy)
        base = np.c_[xy, z]
        top = np.c_[xy, np.asarray(z) + obstacle.height_m]
        bases[obstacle.id] = Polygon(xy)
        add(top, -1, obstacle.id, obstacle.id)
        for i in range(len(xy)):
            j = (i + 1) % len(xy)
            add([base[i], base[j], top[j], top[i]], -1, obstacle.id, obstacle.id)
    for face in parapet_faces(project.roof):
        add(face, -1, 'parapet', 'parapet')
    for owner, module in enumerate(design.modules):
        corners = np.asarray(module.corners)
        # Stored millimetre-rounded corners can be slightly noncoplanar.
        for indices in [[0, 1, 2], [0, 2, 3]]:
            add(corners[indices], owner, "front_row", module.id)
    n_faces = len(faces)
    face_groups = []
    normals = np.empty((n_faces, 3), dtype=float)
    anchors = np.empty((n_faces, 3), dtype=float)
    face_zmax = np.empty(n_faces, dtype=float)
    is_convex = np.zeros(n_faces, dtype=bool)
    group_arity = np.zeros(n_faces, dtype=np.int32)
    group_slot = np.zeros(n_faces, dtype=np.int32)
    for count in sorted({len(face) for face in faces}):
        indices = np.array([i for i, face in enumerate(faces) if len(face) == count])
        verts = np.array([faces[i] for i in indices], dtype=float)
        face_groups.append((indices, verts))
        raw_n = np.cross(verts, np.roll(verts, -1, axis=1)).sum(axis=1)
        norms = np.linalg.norm(raw_n, axis=1)
        normals[indices] = raw_n / norms[:, None]
        anchors[indices] = verts[:, 0]
        face_zmax[indices] = verts[:, :, 2].max(axis=1)
        group_arity[indices] = count
        group_slot[indices] = np.arange(len(indices), dtype=np.int32)
        if count == 3:
            is_convex[indices] = np.isfinite(norms) & (norms > EPS)
        elif count == 4:
            e1 = np.roll(verts, -1, axis=1) - verts
            e2 = np.roll(verts, -2, axis=1) - np.roll(verts, -1, axis=1)
            turns = np.einsum("fij,fj->fi", np.cross(e1, e2), normals[indices])
            is_convex[indices] = np.isfinite(norms) & (norms > EPS) & ((turns > 1e-9).all(axis=1) | (turns < -1e-9).all(axis=1))
    causes_arr = np.asarray(causes, dtype=object)
    cause_names = tuple(sorted({c for c in causes if c}))
    cause_lookup = {name: i + 1 for i, name in enumerate(cause_names)}
    cause_codes = np.array([cause_lookup.get(c, 0) for c in causes], dtype=np.int16)
    return Scene(
        project, design, faces, np.asarray(owners), causes_arr, identifiers,
        normals, anchors, bases, face_groups,
        cause_names=cause_names, cause_codes=cause_codes,
        is_convex=is_convex, group_arity=group_arity, group_slot=group_slot, face_zmax=face_zmax,
    )


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
    if not len(face_indices):
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)

    if scene.is_convex is None or scene.face_zmax is None:
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
        order = np.lexsort((face_index, distance, point_index))
        return point_index[order].astype(np.int32), face_index[order].astype(np.int32)

    shift = vector[:2] / vector[2]
    pts_xy = flat[:, :2] - flat[:, 2:3] * shift
    pts_s = flat @ vector
    flat_owners = np.broadcast_to(owners, shape).reshape(-1)

    h_norm = float(np.hypot(vector[0], vector[1]))
    if h_norm > 1e-12:
        wx, wy = vector[0] / h_norm, vector[1] / h_norm
        ux, uy = -wy, wx
    else:
        ux, uy, wx, wy = 1.0, 0.0, 0.0, 1.0

    pts_u = pts_xy[:, 0] * ux + pts_xy[:, 1] * uy
    pts_w = pts_xy[:, 0] * wx + pts_xy[:, 1] * wy
    box_pad = 1e-9

    n_faces = len(scene.faces)
    f_umin = np.empty(n_faces, dtype=float)
    f_umax = np.empty(n_faces, dtype=float)
    f_wmin = np.empty(n_faces, dtype=float)
    f_wmax = np.empty(n_faces, dtype=float)
    f_smax = np.empty(n_faces, dtype=float)
    proj_groups = {}
    for indices, vertices in scene.face_groups:
        pv = vertices[..., :2] - vertices[..., 2:3] * shift
        nxt = np.roll(pv, -1, axis=1)
        ed = nxt - pv
        a2 = (pv[:, :, 0] * nxt[:, :, 1] - pv[:, :, 1] * nxt[:, :, 0]).sum(axis=1)
        proj_groups[vertices.shape[1]] = (pv, ed, a2)
        pvu = pv[:, :, 0] * ux + pv[:, :, 1] * uy
        pvw = pv[:, :, 0] * wx + pv[:, :, 1] * wy
        f_umin[indices] = pvu.min(axis=1) - box_pad
        f_umax[indices] = pvu.max(axis=1) + box_pad
        f_wmin[indices] = pvw.min(axis=1) - box_pad
        f_wmax[indices] = pvw.max(axis=1) + box_pad
        f_smax[indices] = (vertices @ vector).max(axis=1)

    if len(shape) >= 2 and shape[0] >= 1 and len(flat) // shape[0] >= 4:
        g_count = shape[0]
        k_pts = len(flat) // g_count
        gu = pts_u.reshape(g_count, k_pts)
        gw = pts_w.reshape(g_count, k_pts)
        gu0, gu1 = gu.min(axis=1), gu.max(axis=1)
        gw0, gw1 = gw.min(axis=1), gw.max(axis=1)
        gz0 = flat[:, 2].reshape(g_count, k_pts).min(axis=1)
        gs0 = pts_s.reshape(g_count, k_pts).min(axis=1)
    else:
        g_count, k_pts = len(flat), 1
        gu0 = gu1 = pts_u
        gw0 = gw1 = pts_w
        gz0 = flat[:, 2]
        gs0 = pts_s

    fu0, fu1 = f_umin[face_indices], f_umax[face_indices]
    fw0, fw1 = f_wmin[face_indices], f_wmax[face_indices]
    fz1, fs1 = scene.face_zmax[face_indices], f_smax[face_indices]
    if g_count * len(face_indices) <= 2_500_000:
        u_hit = (gu1[:, None] >= fu0[None, :]) & (gu0[:, None] <= fu1[None, :])
        gi, act_sub = np.nonzero(u_hit)
        if not len(gi):
            return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)
        wzs_ok = (
            (gw1[gi] >= fw0[act_sub])
            & (gw0[gi] <= fw1[act_sub])
            & (gs0[gi] < fs1[act_sub] - 0.5 * EPS)
            & (gz0[gi] < fz1[act_sub] + box_pad)
        )
        gi, fi_g = gi[wzs_ok], face_indices[act_sub[wzs_ok]]
    else:
        f_boxes = shapely.box(fu0, fw0, fu1, fw1)
        g_boxes = shapely.box(gu0, gw0, gu1, gw1) if k_pts > 1 else shapely.points(np.c_[pts_u, pts_w])
        gp = STRtree(f_boxes).query(g_boxes)
        if not gp.shape[1]:
            return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)
        gi, fi_g = gp[0], face_indices[gp[1]]

    if not len(gi):
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)

    if k_pts > 1:
        g_owners = flat_owners.reshape(g_count, k_pts)
        if (g_owners == g_owners[:, :1]).all():
            go_ok = (scene.owners[fi_g] < 0) | (scene.owners[fi_g] != g_owners[gi, 0])
            gi, fi_g = gi[go_ok], fi_g[go_ok]
        if not len(gi):
            return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)
        point_index = (gi[:, None] * k_pts + np.arange(k_pts)[None, :]).reshape(-1)
        face_index = np.repeat(fi_g, k_pts)
        pu_c, pw_c, ps_c = pts_u[point_index], pts_w[point_index], pts_s[point_index]
        in_box = (
            (pu_c >= f_umin[face_index])
            & (pu_c <= f_umax[face_index])
            & (pw_c >= f_wmin[face_index])
            & (pw_c <= f_wmax[face_index])
            & (ps_c < f_smax[face_index] - 0.5 * EPS)
        )
        point_index, face_index = point_index[in_box], face_index[in_box]
    else:
        point_index, face_index = gi, fi_g

    if not len(point_index):
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)

    same_owner = scene.owners[face_index] == flat_owners[point_index]
    keep_owner = (~same_owner) | (scene.owners[face_index] < 0)
    point_index, face_index = point_index[keep_owner], face_index[keep_owner]
    if not len(point_index):
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)

    distance = np.einsum("ij,ij->i", scene.anchors[face_index] - flat[point_index], scene.normals[face_index]) / denominator[face_index]
    valid = distance > EPS
    point_index, face_index, distance = point_index[valid], face_index[valid], distance[valid]
    if not len(point_index):
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)

    hit = np.zeros(len(point_index), dtype=bool)
    undecided = ~scene.is_convex[face_index]
    tol = 1e-9
    for k, (pv_all, ed_all, a2_all) in proj_groups.items():
        mask_k = scene.is_convex[face_index] & (scene.group_arity[face_index] == k)
        if not mask_k.any():
            continue
        pos_k = np.flatnonzero(mask_k)
        slots = scene.group_slot[face_index[pos_k]]
        verts_k = pv_all[slots]
        edges_k = ed_all[slots]
        area2 = a2_all[slots]
        qx = pts_xy[point_index[pos_k], 0:1] - verts_k[:, :, 0]
        qy = pts_xy[point_index[pos_k], 1:2] - verts_k[:, :, 1]
        cross = edges_k[:, :, 0] * qy - edges_k[:, :, 1] * qx
        ccw_in = (area2 > tol) & (cross > tol).all(axis=1)
        cw_in = (area2 < -tol) & (cross < -tol).all(axis=1)
        ccw_out = (area2 > tol) & (cross < -tol).any(axis=1)
        cw_out = (area2 < -tol) & (cross > tol).any(axis=1)
        k_hit = ccw_in | cw_in
        k_ambig = ~(k_hit | ccw_out | cw_out)
        hit[pos_k[k_hit]] = True
        undecided[pos_k[k_ambig]] = True

    if undecided.any():
        u_idx = np.flatnonzero(undecided)
        u_fi, u_pi = face_index[u_idx], point_index[u_idx]
        uniq_fi, inv_fi = np.unique(u_fi, return_inverse=True)
        uniq_polys = np.empty(len(uniq_fi), dtype=object)
        for idx_u, f_id in enumerate(uniq_fi):
            uniq_polys[idx_u] = shapely.polygons(_project(scene.faces[f_id], vector))
        u_pts = shapely.points(pts_xy[u_pi])
        hit[u_idx] = shapely.intersects(uniq_polys[inv_fi], u_pts)

    point_index, face_index, distance = point_index[hit], face_index[hit], distance[hit]
    # Stable face order resolves only physically coincident nearest surfaces.
    order = np.lexsort((face_index, distance, point_index))
    return point_index[order].astype(np.int32), face_index[order].astype(np.int32)


def candidate_hits_coded(scene, shape, candidates, active_owners=None):
    point_index, face_index = candidates
    if active_owners is not None and len(face_index):
        owners = scene.owners[face_index]
        keep = owners < 0
        keep[~keep] = active_owners[owners[~keep]]
        point_index, face_index = point_index[keep], face_index[keep]
    output = np.zeros(int(np.prod(shape)), dtype=np.int16)
    if len(point_index):
        unique, first = np.unique(point_index, return_index=True)
        output[unique] = scene.cause_codes[face_index[first]]
    return output.reshape(shape)


def beam_fractions_coded(hit_codes, landscape_mask, cause_names):
    segments = hit_codes.copy()
    if landscape_mask.any():
        segments[landscape_mask] = hit_codes[landscape_mask].swapaxes(1, 2)
    blocked = (segments != 0).any(axis=2)
    fraction = blocked.mean(axis=1)
    present_codes = np.unique(segments)
    present_codes = present_codes[present_codes > 0]
    if not len(present_codes):
        return fraction, {}
    votes = np.stack([(segments == code).sum(axis=2) for code in present_codes])
    chosen = votes.argmax(axis=0)  # sorted cause_names -> sorted codes -> identical lexicographic tie-break
    return fraction, {
        cause_names[int(code) - 1]: ((chosen == idx) & blocked).sum(axis=1) / 3.0
        for idx, code in enumerate(present_codes)
    }


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
