"""Diffuse front-row classification must depend on placement, never fresh row IDs."""
import re

import numpy as np

from guangzhu.config import ROOT
from guangzhu.design_locks import apply_operation, reflow
from guangzhu.layout import generate_layout
from guangzhu.models import Project, RemovedModule
from guangzhu.shading import _front_mask


def project():
    value = Project.model_validate_json((ROOT / 'data/demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    value.roof.outline = [(0, 0), (24, 0), (24, 16), (0, 16)]
    value.roof.obstacles, value.roof.keepouts, value.roof.surroundings = [], [], []
    return value


def test_northern_retained_module_does_not_shade_southern_new_row_by_id():
    site = project()
    original = generate_layout(site, dict(tilt_deg=10))
    north = next(m for m in original.modules if m.row == max(n.row for n in original.modules) and m.col == 5)
    apply_operation(site, original, dict(op='lock_modules', module_ids=[north.id]), 'user')
    changed = reflow(site, original, dict(tilt_deg=10, orientation='landscape'))
    mask = dict(zip((m.id for m in changed.modules), _front_mask(changed)))
    south = min((m for m in changed.modules if min(p[0] for p in m.corners) < north.center[0]
                 < max(p[0] for p in m.corners)), key=lambda m: m.center[1])
    assert south.row > north.row and south.center[1] < north.center[1]
    assert not mask[south.id]
    assert mask[north.id]

    renamed = changed.model_copy(deep=True)
    maximum = max(m.row for m in renamed.modules)
    for module in renamed.modules:
        module.row = maximum + 100 - module.row
        module.id = re.sub(r'R\d+-', f'R{module.row:02d}-', module.id)
    assert np.array_equal(_front_mask(renamed), _front_mask(changed))


def test_partial_reflow_keeps_both_tiers_of_one_rack_in_the_same_front_row():
    original = generate_layout(project(), dict(tilt_deg=10, rows_per_rack=2))
    expected = _front_mask(original)
    changed = original.model_copy(deep=True)
    changed.statistics['partial_reflow'] = True
    assert np.array_equal(_front_mask(changed), expected)
    first_row = min(m.row for m in changed.modules)
    for index, module in enumerate(changed.modules):
        if module.row == first_row:
            assert not expected[index]

    removed = [m for m in changed.modules if m.row == first_row and m.tier == 1]
    changed.modules = [m for m in changed.modules if m not in removed]
    changed.removed_modules += [RemovedModule(**m.model_dump(), reason='第一层被手动移除') for m in removed]
    remaining = _front_mask(changed)
    assert all(not remaining[i] for i, m in enumerate(changed.modules) if m.row == first_row)
