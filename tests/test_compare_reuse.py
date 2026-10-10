"""Exact reuse keeps all ray samples while deleted racks can reveal farther hits."""

import pytest
import numpy as np
from types import SimpleNamespace

from guangzhu import layout, shading
from guangzhu.models import validate_project
from guangzhu.config import ROOT
from guangzhu.shading_geometry import candidate_hits
import json


def roof():
    payload = json.loads((ROOT / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    payload['roof'].update(outline=[[0, 0], [25, 0], [25, 24], [0, 24]], keepouts=[], obstacles=[])
    payload['requirements']['structured']['keep_clear_ids'] = []
    return validate_project(payload)


@pytest.mark.parametrize('orientation', ['portrait', 'landscape'])
def test_deletion_reuse_matches_fresh_rays_and_front_mask(orientation):
    project = roof()
    design = layout.generate_layout(project, {'tilt_deg': 30, 'orientation': orientation})
    shared = shading.SiteShading(project, offline=True)
    reuse = shading.RemovalShading(project, design, site=shared)
    baseline = reuse.analyze(design)
    smaller = design.model_copy(deep=True)
    first_row = min(module.row for module in smaller.modules)
    smaller.modules = [module for module in smaller.modules if module.row != first_row]
    assert len(smaller.modules) < len(design.modules)
    for candidate in (design, smaller):
        reused = reuse.analyze(candidate)
        fresh = shading.analyze_design(project, candidate, offline=True)
        assert reused['modules'] == fresh['modules']
        assert reused['summary'] == fresh['summary']
        for key in ('representative_days', 'daylight_hours', 'points_per_module', 'weather_sha256'):
            assert reused['metadata'][key] == fresh['metadata'][key]
    previous = {row['id']: row['total_loss_pct'] for row in baseline['modules']}
    assert any(row['total_loss_pct'] < previous[row['id']] for row in reuse.analyze(smaller)['modules'])
    assert 0 < reuse.cache_bytes <= reuse.max_cache_bytes


def test_removal_reuse_has_bounded_memory_and_keeps_obstacle_parapet_attribution():
    project = roof()
    # Keep the original parapet and add an obstacle over a subset of the roof.
    source = validate_project(json.loads((ROOT / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8')))
    project.roof.obstacles = source.roof.obstacles[:1]
    project.roof.obstacles[0].footprint = [(x, y - 15) for x, y in project.roof.obstacles[0].footprint]
    design = layout.generate_layout(project, {'tilt_deg': 15})
    reuse = shading.RemovalShading(project, design, offline=True, max_cache_bytes=1)
    original = reuse.analyze(design)
    design.modules = design.modules[::2]
    reused = reuse.analyze(design)
    fresh = shading.analyze_design(project, design, offline=True)
    assert reused['modules'] == fresh['modules'] and reused['summary'] == fresh['summary']
    assert reuse.cache_bytes <= 1
    assert original['metadata']['points_per_module'] == 9
    assert original['metadata']['daylight_hours'] == 144


def test_reuse_rejects_geometry_or_parameters_changed_after_reference():
    project = roof()
    design = layout.generate_layout(project, {'tilt_deg': 20})
    reuse = shading.RemovalShading(project, design, offline=True)
    modified = design.model_copy(deep=True)
    x, y, z = modified.modules[0].corners[0]
    modified.modules[0].corners = ((x + .1, y, z), *modified.modules[0].corners[1:])
    with pytest.raises(ValueError, match='geometry'):
        reuse.analyze(modified)
    modified = design.model_copy(deep=True)
    modified.params.tilt_deg = 25
    with pytest.raises(ValueError, match='geometry'):
        reuse.analyze(modified)


def test_removed_nearest_face_reveals_next_blocker_and_preserves_tie_order():
    scene = SimpleNamespace(owners=np.array([0, 1, -1, -1]),
                            causes=np.array(['front_row', 'front_row', 'far-wall', 'near-wall'], dtype=object))
    # Candidate order is already ray/distance/stable-face order. Ray0's two
    # wall hits tie; ray1 has a farther rack before its farther wall.
    candidates = (np.array([0, 0, 0, 1, 1, 1]), np.array([0, 2, 3, 0, 1, 2]))
    assert candidate_hits(scene, (2,), candidates).tolist() == ['front_row', 'front_row']
    assert candidate_hits(scene, (2,), candidates, np.array([False, True])).tolist() == ['far-wall', 'front_row']
    assert candidate_hits(scene, (2,), candidates, np.array([False, False])).tolist() == ['far-wall', 'far-wall']


def test_empty_roof_without_any_faces_keeps_fresh_and_cached_zero_results():
    project = roof()
    project.roof.parapet_height_m = 0
    project.roof.outline = [(0, 0), (2, 0), (2, 2), (0, 2)]
    design = layout.generate_layout(project, {'tilt_deg': 0})
    assert not design.modules
    reuse = shading.RemovalShading(project, design, offline=True)
    fresh = shading.analyze_design(project, design, offline=True)
    reused = reuse.analyze(design)
    assert reused['modules'] == fresh['modules'] == []
    assert reused['summary'] == fresh['summary']
    assert reused['summary']['avg_loss_pct'] == 0
