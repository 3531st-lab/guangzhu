"""Read back actual CAD output for per-module manual geometry and legacy notes."""
import json
import math

import ezdxf
import pytest

from guangzhu import project as storage
from guangzhu.report.deliverables import write_deliverables
from test_design_edits_api import editable_project  # noqa: F401


@pytest.mark.parametrize('manual', [False, True])
def test_dxf_uses_each_saved_corner_and_does_not_claim_one_azimuth_for_manual_layout(editable_project, tmp_path, manual):
    project = editable_project
    design = storage.load_design(project.id, 1).model_dump(mode='json')
    design['modules'] = design['modules'][:3]
    if manual:
        panel = design['modules'][1]
        angle = math.radians(37)
        cx, cy = panel['center'][:2]
        for point in panel['corners']:
            x, y = point[0]-cx, point[1]-cy
            point[:2] = [cx+x*math.cos(angle)+y*math.sin(angle), cy-x*math.sin(angle)+y*math.cos(angle)]
        panel['azimuth'] = (panel['azimuth']+37) % 360
        design['statistics']['manual_edits'] = True
    design['statistics']['dc_kw'] = 1.815
    # The output writer consumes persisted engineering results; these compact
    # format fixtures keep the test independent of weather and sizing services.
    electrical = dict(version=1, inverter_model='format-fixture', inverter_count=1, string_count=1,
                      modules_per_string=3, voc_cold_v=150, vmp_hot_v=100,
                      strings=[dict(id='S1', inverter=1, mppt=1, module_ids=[m['id'] for m in design['modules']])],
                      mppt_currents=[dict(inverter=1, mppt=1, working_a=10, short_a=11)])
    economy = dict(capex_cny=1, payback_years=1, dynamic_payback_years=1, irr_pct=1,
                   npv_cny=1, lcoe_cny_kwh=1, cashflows=[], params={}, source={})
    for path, value in [('designs/v1.json', design), ('analysis/v1/electrical.json', electrical),
                        ('analysis/v1/economics.json', economy), ('analysis/v1/structure.json', {'mass_kg': 90}),
                        ('analysis/v1/shading.json', {})]:
        target = storage._path(project.id, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value), encoding='utf-8')
    output = tmp_path/'manual-output'
    output.mkdir()
    files = write_deliverables(project.id, 1, output)
    assert set(files) == {'layout-v1.dxf', 'bom-v1.xlsx'}
    drawing = ezdxf.readfile(output/'layout-v1.dxf')
    space = drawing.modelspace()
    exported = list(space.query('LWPOLYLINE[layer=="PV"]'))
    assert len(exported) == 3
    for polyline, module in zip(exported, design['modules'], strict=True):
        assert polyline.closed
        for point, corner in zip(polyline.get_points('xy'), module['corners'], strict=True):
            assert point == pytest.approx(corner[:2], abs=1e-10)
    notes = [entity.dxf.text for entity in space.query('TEXT[layer=="TEXT"]')]
    if manual:
        assert any('Manual per-module placement and rotation' in note and 'actual corners' in note for note in notes)
        assert not any('tilt ' in note or 'azimuth ' in note for note in notes)
    else:
        assert any(f"tilt {design['params']['tilt_deg']} deg | azimuth {design['params']['azimuth_deg']} deg" in note for note in notes)
