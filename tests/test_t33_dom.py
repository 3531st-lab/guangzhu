"""Actual editor DOM delegates parking, drawings and save to the in-process API."""
import json

import ezdxf
import pytest

from test_roof_editor_dom import editor, click_at, saved


@pytest.mark.parametrize('mode', ['size', 'points', 'dxf'])
def test_ground_three_drawing_modes_and_site_obstacles(editor, tmp_path, mode):
    page, errors, root = editor
    page.locator('[data-re="roofMode"]').select_option('ground')
    page.locator('[data-re="name"]').fill('T33空地示意-' + mode)
    if mode == 'size':
        page.locator('[data-re-rect="w"]').fill('120')
        page.locator('[data-re-rect="d"]').fill('80')
    elif mode == 'points':
        page.locator('[data-re-mode="1"]').click()
        page.locator('[data-re-act="trace"]').click()
        for point in [(0, 0), (60, 0), (60, 36), (0, 36)]:
            click_at(page, *point)
        page.locator('[data-re-act="close"]').click()
    else:
        document = ezdxf.new()
        document.header['$INSUNITS'] = 6
        document.modelspace().add_lwpolyline([(0, 0), (60, 0), (60, 36), (0, 36)], close=True)
        file = tmp_path / 'site.dxf'
        document.saveas(file)
        page.locator('[data-re-mode="2"]').click()
        page.set_input_files('#re-file', str(file))
        page.wait_for_selector('[data-cand="0"]')
        page.locator('[data-cand="0"]').click()
        page.locator('[data-re-act="dxf-done"]').click()
    page.locator('[data-site-key="lower_edge_m"]').fill('.3')
    page.locator('[data-site-key="road_width_m"]').fill('4.5')
    page.locator('[data-re-tool="pole"]').click()
    click_at(page, 20, 20)
    click_at(page, 20.5, 20)
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    project, _ = saved(root)
    assert project['roof']['type'] == 'ground' and project['roof']['height_m'] == 0
    assert project['roof']['ground']['lower_edge_m'] == .3
    assert project['roof']['ground']['road_width_m'] == 4.5
    assert project['roof']['obstacles'][0]['height_m'] == 8
    assert not errors


def test_carport_generate_edit_delete_save_reopen_does_not_revive(editor):
    page, errors, root = editor
    page.locator('[data-re="roofMode"]').select_option('carport')
    page.locator('[data-re="name"]').fill('T33车棚示意')
    page.locator('[data-re-rect="w"]').fill('24')
    page.locator('[data-re-rect="d"]').fill('40')
    page.locator('[data-site-key="direction_deg"]').fill('0')
    page.locator('[data-re-act="parking-build"]').click()
    page.wait_for_selector('[data-canopy="1"]')
    page.locator('[data-canopy="0"][data-canopy-key="slope_deg"]').fill('0')
    page.locator('[data-canopy="0"][data-canopy-key="outline"]').fill('2,5.5\n21,5.5\n21,16.3\n2,16.3')
    page.locator('[data-re-act="canopy-delete-2"]').click()
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    project, folder = saved(root)
    assert len(project['roof']['planes']) == 1 and project['roof']['planes'][0]['slope_deg'] == 0
    assert len(project['roof']['carport']['bays']) == 40
    assert min(p[0] for p in project['roof']['carport']['columns']['1']) > 2
    page.goto('http://offline.test/#roof/' + folder.name)
    page.wait_for_selector('[data-re-act="canopy-delete-1"]')
    page.locator('[data-re-act="canopy-delete-1"]').click()
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    assert json.loads((folder / 'project.json').read_text(encoding='utf-8'))['roof']['planes'] == []
    assert not errors
