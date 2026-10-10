"""Roof input tolerance never permits colliding modules across real P faces."""
import pytest
from shapely.affinity import rotate
from shapely.geometry import Polygon, box

from guangzhu import costs, electrical, layout, rules, structure
from guangzhu.models import Design, LayoutParams, Project
from test_t32_engineering import project


def overlapping_project(overlap, angle, width=8.908):
    record = project('single', slope_deg=5)
    # Independent Trina550 catalog dimension: 8 * 1.096 + 7 * .02 = 8.908 m.
    whole = box(0, 0, 2 * width - overlap, 10)
    shapes = [box(0, 0, width, 10), box(width - overlap, 0, 2 * width - overlap, 10)]
    outline = lambda shape: list(rotate(shape, angle, origin=(0, 0)).exterior.coords)[:-1]
    data = record.model_dump()
    data['roof'].update(outline=outline(whole), seam_setback_m=0, pitched=None,
                        planes=[dict(id=i + 1, outline=outline(shape), slope_deg=5,
                                     slope_azimuth_deg=180 - angle, material='metal', offset_m=0)
                                for i, shape in enumerate(shapes)])
    return Project.model_validate(data)


def intersecting_pairs(design):
    # Independent brute force checker: positive real area, no roof-tolerance buffer or epsilon.
    shapes = [(m, Polygon([point[:2] for point in m.corners])) for m in design.modules]
    return [(a.id, b.id) for i, (a, left) in enumerate(shapes) for b, right in shapes[i + 1:]
            if a.id.split('-')[0] != b.id.split('-')[0] and left.intersection(right).area > 0]


@pytest.mark.parametrize('angle', [0, 37])
@pytest.mark.parametrize('overlap, count', [(.019, 60), (0, 64)])
def test_tolerated_roof_overlap_never_becomes_module_overlap(angle, overlap, count):
    record = overlapping_project(overlap, angle)
    design = layout.generate_layout(record, dict(edge_setback_m=0))
    independent = {m.id: m for face in record.roof.planes
                   for m in layout.generate_layout(record, design.params, _plane=face).modules}
    assert all(m == independent[m.id] for m in design.modules)
    assert record.roof.seam_setback_m == design.params.edge_setback_m == 0
    assert not intersecting_pairs(design)
    assert len(design.modules) == count
    assert design.statistics['module_count'] == count
    assert design.statistics['dc_kw'] == pytest.approx(count * .55)
    assert design.statistics['rows'] == 8
    for face in design.statistics['planes']:
        actual = [m for m in design.modules if m.id.startswith(f"P{face['id']}-")]
        assert face['module_count'] == face['statistics']['module_count'] == len(actual)
        assert face['dc_kw'] == face['statistics']['dc_kw'] == pytest.approx(len(actual) * .55)
        assert face['statistics']['rows'] == len({m.row for m in actual})
        assert face['statistics']['module_area_ratio'] == pytest.approx(len(actual) * 2.384 * 1.096 / 89.08)
    load = structure.calculate(record, design)
    electric = electrical.calculate(record, design, offline=True)
    quote = costs.itemized(record, count * .55, design, electric, load)
    assert len(load['wind']['modules']) == count
    assert sum(row['quantity'] for row in quote['items'] if row['key'] == 'module') == count * 550
    assert electric['dc_kw'] == pytest.approx(count * .55)
    if overlap:
        assert design.statistics['module_area_ratio'] == pytest.approx(count * 2.384 * 1.096 / (17.797 * 10))


@pytest.mark.parametrize('angle', [0, 37])
def test_g01_independently_rejects_an_unfiltered_record_with_real_cross_face_collisions(angle):
    record = overlapping_project(.019, angle)
    params = LayoutParams(edge_setback_m=0)
    # Compose the old 64-panel record explicitly; do not ask the repaired whole-roof generator for a bad example.
    separate = [layout.generate_layout(record, params, _plane=plane) for plane in record.roof.planes]
    bad = Design(params=params, modules=[m for face in separate for m in face.modules])
    assert len(bad.modules) == 64 and len(intersecting_pairs(bad)) == 4
    load = structure.calculate(record, bad)
    electric = electrical.calculate(record, bad, offline=True)
    shadows = dict(modules=[dict(id=m.id, total_loss_pct=0) for m in bad.modules],
                   summary=dict(avg_loss_pct=0, threshold_pct=8))
    checked = rules.evaluate(record, bad, shadows, electric, load)
    failed = [row for row in checked['items'] if row['id'] == 'G01' and row['status'] == 'fail']
    assert failed and all('相交' in row['hint_zh'] for row in failed)
    removed = {mid for row in failed for mid in row['suggestion']['module_ids']}
    assert all(a in removed or b in removed for a, b in intersecting_pairs(bad))
    assert not intersecting_pairs(bad.model_copy(update=dict(modules=[m for m in bad.modules if m.id not in removed])))
    assert {m.id.split('-')[0] for m in bad.modules} == {'P1', 'P2'}


def test_only_actual_panel_occupancy_removes_modules_and_counts_empty_rows():
    record = overlapping_project(.019, 0)
    single = layout.generate_layout(record, dict(edge_setback_m=0, plane_ids=[2]))
    assert len(single.modules) == 32 and 'cross_face_removed' not in single.statistics
    record = overlapping_project(.019, 0, width=1.096)
    design = layout.generate_layout(record, dict(edge_setback_m=0))
    assert len(design.modules) == 4 and design.statistics['rows'] == 4
    second = design.statistics['planes'][1]
    assert second['module_count'] == second['dc_kw'] == 0
    assert second['statistics']['rows'] == second['statistics']['module_count'] == second['statistics']['dc_kw'] == 0


def test_removed_landscape_main_rows_are_not_counted_as_portrait_fill():
    record = overlapping_project(.019, 0, width=7.192)
    design = layout.generate_layout(record, dict(edge_setback_m=0, orientation='landscape', fill_landscape=True))
    assert len(design.modules) == 45 and not intersecting_pairs(design)
    assert design.statistics['rows'] == 18 and design.statistics['fill_landscape_count'] == 0
    assert all(row['statistics']['fill_landscape_count'] == 0 for row in design.statistics['planes'])
