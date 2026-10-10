"""Real underlay transforms preserve generated parking geometry and allow rebuilding."""
import math

from PIL import Image
import pytest

from test_roof_editor_dom import editor, click_at, saved


@pytest.mark.parametrize('operation', ['north', 'scale'])
def test_generated_canopies_transform_with_underlay_and_rebuild(editor, tmp_path, operation):
    page, errors, root = editor
    page.locator('[data-re="roofMode"]').select_option('carport')
    page.locator('[data-re="name"]').fill('带底图的停车场')
    page.locator('[data-re-rect="w"]').fill('24')
    page.locator('[data-re-rect="d"]').fill('40')
    page.locator('[data-site-key="direction_deg"]').fill('0')
    page.locator('[data-re-act="parking-build"]').click()
    page.wait_for_selector('[data-canopy="1"]')
    image = tmp_path / 'parking.png'
    Image.new('RGB', (800, 500), 'white').save(image)
    page.locator('[data-re-mode="2"]').click()
    page.set_input_files('#re-file', str(image))
    page.wait_for_selector('#re-svg image')
    click_at(page, 100, 400, pixels=True)
    click_at(page, 700, 400, pixels=True)
    page.locator('[data-re="distance"]').fill('60')
    page.locator('[data-re-act="calibrate"]').click()
    page.locator('[data-re-act="adopt"]').click()
    page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    before, folder = saved(root)
    page.goto('http://offline.test/#roof/' + folder.name)
    page.wait_for_selector('[data-re-act="recalibrate"]')
    if operation == 'north':
        page.locator('[data-re="north"]').fill('37')
    else:
        page.locator('[data-re-act="recalibrate"]').click()
        click_at(page, 100, 400, pixels=True)
        click_at(page, 700, 400, pixels=True)
        page.locator('[data-re="distance"]').fill('48')
        page.locator('[data-re-act="calibrate"]').click()
    assert not errors
    assert 'radians' not in page.locator('#notice').inner_text()
    page.locator('[data-re-act="save"]').click()
    if operation == 'scale':
        page.wait_for_function("document.getElementById('notice').textContent.includes('重新生成停车设施')")
        page.locator('[data-re-act="parking-build"]').click()
        page.wait_for_function("document.querySelector('[data-canopy=\"0\"]') !== null")
        page.locator('[data-re-act="save"]').click()
    page.wait_for_function("location.hash === '#new'")
    after, _ = saved(root)
    old, new = before['roof'], after['roof']
    if operation == 'north':
        pairs = [(old['outline'], new['outline'])]
        pairs += [(a['outline'], b['outline']) for a, b in zip(old['planes'], new['planes'])]
        for key in ['bays', 'aisles', 'strips']:
            pairs += [(a['polygon'], b['polygon']) for a, b in zip(old['carport'][key], new['carport'][key])]
        pairs += [(points, new['carport']['columns'][key]) for key, points in old['carport']['columns'].items()]
        for first, second in pairs:
            assert len(first) == len(second)
            for (x, y), point in zip(first, second):
                angle = math.radians(37)
                expected = [x * math.cos(angle) - y * math.sin(angle), x * math.sin(angle) + y * math.cos(angle)]
                assert point == pytest.approx(expected, abs=1e-6)
        assert new['planes'][0]['slope_azimuth_deg'] == pytest.approx((old['planes'][0]['slope_azimuth_deg'] - 37) % 360)
    else:
        assert math.dist(*new['outline'][:2]) == pytest.approx(19.2, abs=.01)
        assert new['carport']['bays']
        assert len(new['carport']['bays']) < len(old['carport']['bays'])
    assert not errors
