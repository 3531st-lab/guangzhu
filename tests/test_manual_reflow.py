"""A locked manual edit can be followed by reflow and another exact transform."""
import json

import numpy as np

from guangzhu import project as storage, shading
from guangzhu.config import DATA_DIR
from guangzhu.design_locks import apply_operation, locked_ids, reflow
from guangzhu.layout import _catalog, generate_layout
from guangzhu.manual_modules import apply
from guangzhu.models import Project
from guangzhu.rules import walkway_check


def test_reflow_new_oblique_grid_preserves_rounding_provenance_for_next_manual_move():
    raw = json.loads((DATA_DIR/'demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    raw['roof'].update(outline=[[0, 0], [40, 0], [40, 24], [0, 24]], obstacles=[], keepouts=[], surroundings=[])
    site = Project.model_validate(raw)
    original = generate_layout(site, dict(tilt_deg=15, azimuth_deg=197))
    site.roof.outline = [(-1, -1), (41, -1), (41, 25), (-1, 25)]
    moved, _ = apply(site, original, dict(op='move_modules', module_ids=[m.id for m in original.modules],
                                         dx_m=.1, dy_m=.1))
    protected = moved.modules[0].model_copy(deep=True)
    apply_operation(site, moved, dict(op='lock_modules', module_ids=[protected.id]), 'user')
    fresh = reflow(site, moved, moved.params)
    locked = locked_ids(fresh)
    unlocked = [m.id for m in fresh.modules if m.id not in locked]
    assert len(unlocked) > 20
    # Reflow creates new millimetre-rounded centres. Restoring their exact catalogue
    # edges must retain that uncertainty, just like the original generated grid.
    shifted, _ = apply(site, fresh, dict(op='move_modules', module_ids=unlocked, dx_m=.01, dy_m=.01))
    assert next(m for m in shifted.modules if m.id == protected.id) == protected
    catalogue, _, _ = _catalog(site, shifted.params)
    before = {m.id: m for m in fresh.modules}
    for module in shifted.modules:
        if module.id in locked:
            continue
        corners = np.asarray(module.corners)
        width, depth = ((catalogue['width_m'], catalogue['length_m']) if module.orientation == 'portrait'
                        else (catalogue['length_m'], catalogue['width_m']))
        np.testing.assert_allclose(np.linalg.norm(corners[1]-corners[0]), float(width), atol=1e-10, rtol=0)
        np.testing.assert_allclose(np.linalg.norm(corners[3]-corners[0]), float(depth), atol=1e-10, rtol=0)
        np.testing.assert_allclose(module.center[:2], np.asarray(before[module.id].center[:2])+.01, atol=1e-10, rtol=0)
    assert set(unlocked) <= set(shifted.statistics['manual_legacy_geometry_ids'])


def regular_with_required_walkway():
    raw = json.loads((DATA_DIR/'demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    raw.update(id='manual-method-restore', designs=[])
    raw['roof'].update(outline=[[0, 0], [40, 0], [40, 24], [0, 24]], obstacles=[], keepouts=[], surroundings=[])
    raw['requirements']['structured']['walkway_m_min'] = .6
    site = Project.model_validate(raw)
    original = generate_layout(site, dict(tilt_deg=15, azimuth_deg=197, walkway_every_n_rows=1, walkway_width_m=1.2))
    site.roof.outline = [(-1, -1), (41, -1), (41, 25), (-1, 25)]
    assert walkway_check(site, original)['status'] == 'pass'
    return site, original


def assert_geometry_sky_without_irregular_rule_semantics(site, design):
    assert not design.statistics.get('manual_edits')
    assert design.statistics.get('geometry_sky') is True
    assert walkway_check(site, design)['status'] == 'pass'
    # Exercise the real analysis dispatch using one saved panel, keeping this
    # provenance test inexpensive while still checking the selected algorithm.
    sample = design.model_copy(deep=True, update={'modules': design.modules[:1]})
    result = shading.analyze_design(site, sample, offline=True)
    assert result['metadata']['sky_visibility_method'] == 'isotropic_geometry_quadrature'


def test_full_unlocked_reflow_restores_regular_rules_but_retains_sky_algorithm():
    site, original = regular_with_required_walkway()
    manual, _ = apply(site, original, dict(op='move_modules', module_ids=[m.id for m in original.modules], dx_m=.1, dy_m=.1))
    assert manual.statistics['manual_edits'] is True
    assert walkway_check(site, manual)['status'] == 'fail'
    fresh = reflow(site, manual, manual.params)
    assert not locked_ids(fresh)
    assert_geometry_sky_without_irregular_rule_semantics(site, fresh)


def test_undo_restores_exact_regular_geometry_and_rules_while_retaining_sky_algorithm(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, 'PROJECTS_DIR', tmp_path/'projects')
    site, original = regular_with_required_walkway()
    storage.save(site)
    storage.save_design(site.id, original, offline=True)
    stored_before = storage._path(site.id, 'designs/v1.json').read_bytes()
    moved = storage.edit_design(site.id, 1, [dict(op='move_modules', module_ids=[m.id for m in original.modules],
                                               dx_m=.1, dy_m=.1)], '校正位置', 'user', offline=True)
    undone = storage.edit_design(site.id, moved['version'], [dict(op='undo_last_edit')], '撤销位置校正', 'user', offline=True)
    restored = storage.load_design(site.id, undone['version'])
    assert restored.modules == original.modules
    assert_geometry_sky_without_irregular_rule_semantics(site, restored)
    assert storage._path(site.id, 'designs/v1.json').read_bytes() == stored_before
