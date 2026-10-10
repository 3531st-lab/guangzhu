"""The production editor persists defaults, explicit lows and preset identity."""
from test_roof_editor_dom import editor, click_at, saved


def test_grazing_defaults_and_reopen_explicit_low(editor):
    page, errors, root = editor
    page.select_option('[data-re="roofMode"]', 'ground')
    page.select_option('[data-re="use"]', 'grazing')
    assert page.input_value('[data-site-key="lower_edge_m"]') == '1.5'
    page.select_option('[data-re="animal"]', 'cow')
    assert page.input_value('[data-site-key="lower_edge_m"]') == '2.5'
    page.fill('[data-site-key="lower_edge_m"]', '.3')
    page.select_option('[data-re="animal"]', 'sheep')
    assert page.input_value('[data-site-key="lower_edge_m"]') == '0.3'
    page.fill('[data-re="name"]', 'T34低高度显式示意')
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    record, folder = saved(root)
    assert record['roof']['ground']['lower_edge_m'] == .3
    page.goto('http://offline.test/#roof/' + folder.name)
    page.wait_for_selector('[data-re="animal"]')
    page.select_option('[data-re="animal"]', 'cow')
    assert page.input_value('[data-site-key="lower_edge_m"]') == '0.3'
    assert not errors


def test_barn_presets_zero_and_default_rack(editor):
    page, errors, root = editor
    page.select_option('[data-re="roofMode"]', 'metal-single')
    page.select_option('[data-re="use"]', 'barn')
    page.click('[data-re-tool="vent"]')
    click_at(page, 8, 8)
    click_at(page, 11, 11)
    page.fill('[data-item="0"][data-key="clearance"]', '0')
    page.fill('[data-re="name"]', 'T34养殖场示意')
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    record, folder = saved(root)
    assert record['equipment']['racking'] == 'clamp_barn'
    assert record['roof']['keepouts'][0]['preset'] == 'vent'
    assert record['roof']['keepouts'][0]['clearance_m'] == 0
    page.goto('http://offline.test/#roof/' + folder.name)
    page.wait_for_selector('[data-item="0"][data-key="clearance"]')
    assert page.input_value('[data-item="0"][data-key="clearance"]') == '0'
    assert not errors
