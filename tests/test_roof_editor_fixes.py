"""Codex review R01-R03, R07-R09, R12 in a real browser: the roof editor keeps the real shape through rescaling, new drawings, mode
changes, north, arcs, leaving the page and corner-by-corner editing. Saved values are read back from the real backend's files."""
import io
import math

import ezdxf
import pytest
from PIL import Image, ImageDraw

from test_roof_editor_dom import click_at, editor, saved  # noqa: F401

SAMPLE = [(0, 0), (60, 0), (60, 30), (48, 30), (48, 36), (0, 36), (0, 26), (8, 26), (8, 10), (0, 10)]  # 60×36 − 12×6 − 8×16 = 1960 m²


def area(points):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]))) / 2


def shown(page):
    """The outline as drawn on the canvas, in metres (the canvas draws y downwards)."""
    return [(float(x), -float(y)) for x, y in (pair.split(",") for pair in page.get_attribute("#re-svg .re-roof", "points").split())]


def screen(page, x, y):
    return page.evaluate("""([x, y]) => { const svg = document.getElementById('re-svg'), p = svg.createSVGPoint();
      [p.x, p.y] = [x, -y]; const q = p.matrixTransform(svg.getScreenCTM()); return [q.x, q.y]; }""", [x, y])


def click_pixel(page, u, v, width):
    """Click pixel (u, v) of the imported drawing wherever the canvas shows it: scaled, moved or turned to north."""
    point = page.evaluate("""([u, v, width]) => { const image = document.querySelector('#re-svg image'), p = document.getElementById('re-svg').createSVGPoint();
      const s = Number(image.getAttribute('width')) / width;
      [p.x, p.y] = [Number(image.getAttribute('x')) + u * s, Number(image.getAttribute('y')) + v * s];
      const q = p.matrixTransform(image.getScreenCTM()); return [q.x, q.y]; }""", [u, v, width])
    page.mouse.click(*point)


def drag(page, start, end):
    page.mouse.move(*screen(page, *start))
    page.mouse.down()
    page.mouse.move(*screen(page, *end), steps=8)
    page.mouse.up()


def trace(page, corners, *, close=True):
    page.click('[data-re-act="trace"]')
    for corner in corners:
        click_at(page, *corner)
    if close:
        page.click('[data-re-act="close"]')


def save(page, name="测试厂房"):
    page.fill('[data-re="name"]', name)
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")


def reopen(page, folder):
    page.evaluate(f"location.hash = '#roof/{folder.name}'")
    page.wait_for_function("document.querySelector('.head h1')?.textContent === '编辑屋顶' && document.querySelector('#re-svg .re-roof')")


def refused(page, words):
    page.evaluate("document.getElementById('notice').textContent = ''")
    page.click('[data-re-act="save"]')
    page.wait_for_function(f"document.getElementById('notice').textContent.includes({words!r})")
    assert page.evaluate("location.hash").startswith("#roof")


def blank_drawing(path, size=(1000, 600)):
    Image.new("RGB", size, "white").save(path)
    return size[0]


def to_pixels(points, calibration):
    """models.px_to_m in reverse: where saved metres sit on the drawing."""
    (u1, v1), (u2, v2) = calibration["p1_px"], calibration["p2_px"]
    k, a = math.hypot(u2 - u1, v2 - v1) / calibration["distance_m"], math.radians(calibration.get("north_deg", 0))
    return [(u1 + k * (x * math.cos(a) + y * math.sin(a)), v1 - k * (-x * math.sin(a) + y * math.cos(a))) for x, y in points]


def test_codex_r01_scale_80_then_40_m_keeps_the_roof_and_items_on_the_drawing_with_a_new_origin(editor, tmp_path):
    page, errors, root = editor
    width = blank_drawing(tmp_path / "80米.png")
    page.click('[data-re-mode="2"]')
    page.set_input_files("#re-file", str(tmp_path / "80米.png"))
    page.wait_for_function("document.querySelector('#re-svg image')")
    click_pixel(page, 100, 500, width)
    click_pixel(page, 900, 500, width)
    page.fill('[data-re="distance"]', "80")
    page.click('[data-re-act="calibrate"]')
    page.click('[data-re-act="trace"]')
    for u, v in ((100, 500), (900, 500), (900, 100), (100, 100)):
        click_pixel(page, u, v, width)
    page.click('[data-re-act="close"]')
    page.click('[data-re-tool="device"]')
    click_pixel(page, 200, 400, width)
    click_pixel(page, 240, 370, width)
    save(page)
    first, folder = saved(root)
    assert abs(area(first["roof"]["outline"]) - 3200) / 3200 < 0.01
    reopen(page, folder)
    before = shown(page)
    page.click('[data-re-act="recalibrate"]')  # halfway through, the old scale can still be kept
    click_pixel(page, 900, 500, width)
    page.click('[data-re-act="keep-scale"]')
    assert shown(page) == before
    page.click('[data-re-act="recalibrate"]')  # the same two points, now 40 m apart, and the origin moves to the other end
    click_pixel(page, 900, 500, width)
    click_pixel(page, 100, 500, width)
    page.fill('[data-re="distance"]', "40")
    page.click('[data-re-act="calibrate"]')
    assert abs(area(shown(page)) - 800) / 800 < 0.01 and max(x for x, _ in shown(page)) < 0.5
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    second = saved(root)[0]
    roof, old = second["roof"], first["roof"]
    assert abs(area(roof["outline"]) * 4 / area(old["outline"]) - 1) < 0.01
    new_device, old_device = roof["obstacles"][0]["footprint"], old["obstacles"][0]["footprint"]
    assert abs(area(new_device) * 4 / area(old_device) - 1) < 0.01
    for now, then in ((roof["outline"], old["outline"]), (new_device, old_device)):  # every corner is still on the same pixel of the drawing
        assert max(map(math.dist, to_pixels(now, roof["underlay"]["calibration"]), to_pixels(then, old["underlay"]["calibration"]))) < 0.5
    reopen(page, folder)
    assert max(map(math.dist, shown(page), roof["outline"])) < 0.01 and errors == []


def test_codex_r02_only_a_traced_or_confirmed_outline_is_saved_for_a_new_image_or_pdf(editor, tmp_path):
    page, errors, root = editor
    width = blank_drawing(tmp_path / "图.png")
    page.click('[data-re-mode="2"]')
    page.set_input_files("#re-file", str(tmp_path / "图.png"))
    page.wait_for_function("document.querySelector('#re-svg image')")
    refused(page, "还没定比例")
    click_pixel(page, 100, 500, width)
    click_pixel(page, 900, 500, width)
    page.fill('[data-re="distance"]', "80")
    page.click('[data-re-act="calibrate"]')
    assert page.locator("#re-svg .re-roof.stale").count() == 1  # the sample rectangle is only a dashed suggestion now
    refused(page, "还没描屋顶外边")
    page.click('[data-re-act="trace"]')  # cancelled halfway: still nothing confirmed
    click_pixel(page, 100, 500, width)
    click_pixel(page, 900, 500, width)
    page.keyboard.press("Escape")
    refused(page, "还没描屋顶外边")
    image = Image.new("RGB", (1000, 600), "white")
    image.save(tmp_path / "换一张.pdf", "PDF")  # a different drawing replaces the first one
    page.set_input_files("#re-file", str(tmp_path / "换一张.pdf"))
    page.wait_for_function("document.getElementById('re-scale').textContent.includes('还没定比例')")
    refused(page, "还没定比例")
    pdf_width = int(float(page.get_attribute("#re-svg image", "width")))
    s = pdf_width / 1000
    click_pixel(page, 100 * s, 500 * s, pdf_width)
    click_pixel(page, 900 * s, 500 * s, pdf_width)
    page.fill('[data-re="distance"]', "80")
    page.click('[data-re-act="calibrate"]')
    refused(page, "还没描屋顶外边")
    page.click('[data-re-act="trace"]')
    for u, v in ((100, 500), (900, 500), (900, 100), (100, 100)):
        click_pixel(page, u * s, v * s, pdf_width)
    page.click('[data-re-act="close"]')
    save(page)
    project = saved(root)[0]
    assert abs(area(project["roof"]["outline"]) - 3200) / 3200 < 0.01 and project["roof"]["underlay"]["calibration"]["distance_m"] == 80
    assert errors == []


def make_rect(page, w, d, turn):
    page.fill('[data-re-rect="w"]', str(w))
    page.fill('[data-re-rect="d"]', str(d))
    page.fill('[data-re-rect="turn"]', str(turn))


@pytest.mark.parametrize("shape", ["rectangle", "turned", "notched"])
def test_codex_r03_switching_drawing_methods_never_changes_a_saved_shape(editor, shape):
    page, errors, root = editor
    if shape == "notched":
        page.click('[data-re-mode="1"]')
        trace(page, SAMPLE)
    else:
        make_rect(page, *((80, 40, 0) if shape == "rectangle" else (50, 30, 20)))
    original = shown(page)
    save(page)
    folder = saved(root)[1]
    reopen(page, folder)
    assert page.get_attribute(f'[data-re-mode="{1 if shape == "notched" else 0}"]', "aria-pressed") == "true"
    if shape != "notched":
        assert [page.input_value(f'[data-re-rect="{k}"]') for k in "wd"] == (["80", "40"] if shape == "rectangle" else ["50", "30"])
        assert abs(float(page.input_value('[data-re-rect="turn"]')) - (0 if shape == "rectangle" else 20)) < 0.01
    for mode in (1, 0, 2, 0, 1, 0):
        page.click(f'[data-re-mode="{mode}"]')
        assert max(map(math.dist, shown(page), original)) < 0.01, mode
    if shape == "notched":
        assert "不是矩形（10 个角）" in page.text_content("#re-panel") and page.is_disabled('[data-re-rect="w"]')
        page.click('[data-re-act="to-rect"]')  # replacing it is a separate, undoable step
        assert len(shown(page)) == 4
        page.click('[data-re-act="undo"]')
        assert max(map(math.dist, shown(page), original)) < 0.01
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    project = saved(root)[0]
    assert len(project["roof"]["outline"]) == len(original) and max(map(math.dist, project["roof"]["outline"], original)) < 0.01
    reopen(page, folder)
    assert max(map(math.dist, shown(page), original)) < 0.01 and errors == []


NOTCHED_L = [(0, 0), (60, 0), (60, 26), (40, 26), (40, 36), (0, 36)]


def turned_drawing(path, north):
    """The L-shaped roof drawn so that north on the paper points `north` degrees clockwise from the top; 10 px per metre."""
    a, k, margin = math.radians(north), 10, 60
    paper = [(x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)) for x, y in NOTCHED_L]
    left, top = min(p[0] for p in paper), max(p[1] for p in paper)
    pixel = lambda p: (margin + k * (p[0] - left), margin + k * (top - p[1]))
    size = (int(k * (max(p[0] for p in paper) - left)) + 2 * margin, int(k * (top - min(p[1] for p in paper))) + 2 * margin)
    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).polygon([pixel(p) for p in paper], outline="black", width=3)
    image.save(path)
    return size[0], [pixel(p) for p in paper]


@pytest.mark.parametrize("north", [0, 30])
def test_codex_r07_a_turned_drawing_with_its_north_set_gives_the_same_roof_as_a_north_up_one(editor, tmp_path, north):
    page, errors, root = editor
    width, corners = turned_drawing(tmp_path / f"北偏{north}.png", north)
    page.click('[data-re-mode="2"]')
    page.set_input_files("#re-file", str(tmp_path / f"北偏{north}.png"))
    page.wait_for_function("document.querySelector('#re-svg image')")
    click_pixel(page, *corners[0], width)
    click_pixel(page, *corners[1], width)
    page.fill('[data-re="distance"]', "60")
    page.fill('[data-re="north"]', str(north))
    page.click('[data-re-act="calibrate"]')
    page.click('[data-re-act="trace"]')
    for corner in corners:
        click_pixel(page, *corner, width)
    page.click('[data-re-act="close"]')
    assert max(map(math.dist, shown(page), NOTCHED_L)) < 0.25  # east is x and north is y whichever way the paper was turned
    save(page)
    project, folder = saved(root)
    assert abs(area(project["roof"]["outline"]) - 1960) / 1960 < 0.01 and project["roof"]["underlay"]["calibration"].get("north_deg", 0) == north
    reopen(page, folder)
    page.fill('[data-re="north"]', str(north + 90))  # turning north afterwards turns the traced roof with the drawing
    page.locator('[data-re="north"]').dispatch_event("change")
    turned = [(-y, x) for x, y in NOTCHED_L]
    assert max(map(math.dist, shown(page), turned)) < 0.3 and errors == []


def test_codex_r08_a_dxf_outline_with_a_half_circle_keeps_its_arc_area(editor, tmp_path):
    page, errors, root = editor
    document = ezdxf.new()
    document.header["$INSUNITS"] = 6
    document.modelspace().add_lwpolyline([(0, 0, 0), (20, 0, 0), (20, 20, 1), (0, 20, 0)], format="xyb", close=True)
    document.saveas(tmp_path / "半圆屋顶.dxf")
    page.click('[data-re-mode="2"]')
    page.set_input_files("#re-file", str(tmp_path / "半圆屋顶.dxf"))
    page.wait_for_selector('[data-cand="0"]')
    page.click('[data-cand="0"]')
    page.click('[data-re-act="dxf-done"]')
    shown_area = float(page.text_content("#re-size").split(" m²")[0].replace(",", ""))
    assert abs(shown_area - (400 + math.pi * 50)) / 557.08 < 0.001
    assert errors == []


def test_codex_r09_leaving_asks_first_and_unsaved_edits_come_back_as_a_draft(editor):
    page, errors, root = editor
    answers, seen = [False, True], []
    page.on("dialog", lambda dialog: (seen.append(dialog.type), dialog.accept() if dialog.type == "beforeunload" or answers.pop(0) else dialog.dismiss()))
    page.fill('[data-re="name"]', "没保存的厂房")
    page.fill('[data-re-rect="w"]', "93")
    page.click('a[href="#records"]')  # answered "cancel": nothing is lost
    page.wait_for_timeout(300)
    assert seen == ["confirm"] and page.evaluate("location.hash") == "#roof" and page.input_value('[data-re-rect="w"]') == "93"
    page.click('a[href="#records"]')  # answered "leave"
    page.wait_for_function("location.hash === '#records'")
    page.evaluate("location.hash = '#roof'")
    page.wait_for_selector(".re-draft")
    assert page.input_value('[data-re="name"]') == "" and page.text_content("#re-size").startswith("2,160 m²")
    page.click('[data-re-act="draft-restore"]')
    assert page.input_value('[data-re="name"]') == "没保存的厂房" and page.text_content("#re-size").startswith("3,348 m²")
    page.reload()  # closing or reloading the window asks too, and the draft is still there afterwards
    page.wait_for_selector(".re-draft")
    assert "beforeunload" in seen
    page.click('[data-re-act="draft-drop"]')
    assert page.locator(".re-draft").count() == 0 and page.input_value('[data-re="name"]') == ""
    page.reload()
    page.wait_for_selector("#re-svg .re-roof")
    assert page.locator(".re-draft").count() == 0 and errors == []


def test_codex_r09_a_saved_roof_with_a_drawing_and_items_gets_its_unsaved_corner_and_keepout_back(editor, tmp_path):
    page, errors, root = editor
    width = blank_drawing(tmp_path / "底图.png")
    page.click('[data-re-mode="2"]')
    page.set_input_files("#re-file", str(tmp_path / "底图.png"))
    page.wait_for_function("document.querySelector('#re-svg image')")
    click_pixel(page, 100, 500, width)
    click_pixel(page, 700, 500, width)
    page.fill('[data-re="distance"]', "60")
    page.click('[data-re-act="calibrate"]')
    page.click('[data-re-act="adopt"]')
    page.click('[data-re-tool="device"]')
    click_at(page, 10, 10)
    click_at(page, 14, 13)
    save(page)
    folder = saved(root)[1]
    reopen(page, folder)
    page.on("dialog", lambda dialog: dialog.accept())
    page.fill('[data-vx="1"]', "64")
    page.click('[data-re-tool="keepout"]')
    click_at(page, 30, 20)
    click_at(page, 40, 24)
    edited = shown(page)
    page.click('a[href="#new"]')
    page.wait_for_function("location.hash === '#new'")
    reopen(page, folder)
    page.click('[data-re-act="draft-restore"]')
    assert max(map(math.dist, shown(page), edited)) < 0.01 and page.locator(".re-item").count() == 2
    assert page.locator("#re-svg image").count() == 1
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    project = saved(root)[0]
    assert len(project["roof"]["keepouts"]) == 1 and max(x for x, _ in project["roof"]["outline"]) == 64 and project["roof"]["underlay"]
    assert errors == []


def test_codex_r12_the_notched_sample_by_clicks_then_corner_editing_with_undo_redo(editor):
    page, errors, root = editor
    page.click('[data-re-mode="1"]')
    page.click('[data-re-act="trace"]')
    click_at(page, 0, 0)
    click_at(page, 60, 0)
    page.mouse.move(*screen(page, 30, 18))
    page.mouse.wheel(0, 300)  # zooming and panning while tracing never adds a corner
    start = screen(page, 30, 18)
    page.mouse.move(*start)
    page.mouse.down(button="right")
    page.mouse.move(start[0] + 40, start[1] + 30, steps=5)
    page.mouse.up(button="right")
    assert "已点 2 个角" in page.text_content("#re-panel")
    page.click('[data-re-zoom="0"]')
    for corner in SAMPLE[2:]:
        click_at(page, *corner)
    click_at(page, 0, 0)  # clicking the first corner again closes the outline
    assert page.text_content("#re-size").startswith("1,960 m²") and shown(page) == [tuple(map(float, p)) for p in SAMPLE]
    save(page)
    folder = saved(root)[1]
    reopen(page, folder)
    assert page.get_attribute('[data-re-mode="1"]', "aria-pressed") == "true" and len(shown(page)) == 10
    drag(page, (48, 36), (50, 34))  # move a corner by hand
    moved = [(50.0, 34.0) if p == (48, 36) else tuple(map(float, p)) for p in SAMPLE]
    assert shown(page) == moved
    page.keyboard.press("Control+z")
    assert page.text_content("#re-size").startswith("1,960 m²")
    page.keyboard.press("Control+y")
    assert shown(page) == moved
    page.keyboard.press("Control+z")
    drag(page, (30, 0), (30, -3))  # pull a new corner out of the middle of the south edge
    assert len(shown(page)) == 11 and page.text_content("#re-size").startswith("2,050 m²")
    page.keyboard.press("Delete")  # the new corner is still selected
    assert len(shown(page)) == 10 and page.text_content("#re-size").startswith("1,960 m²")
    page.click('[data-re-del="9"]')  # the table's × removes corner 10
    assert len(shown(page)) == 9
    page.click('[data-re-act="undo"]')
    page.fill('[data-len="0"]', "50")  # an edge length moves the next corner along that edge
    assert shown(page)[1] == (50.0, 0.0)
    page.fill('[data-len="0"]', "60")
    page.fill('[data-vx="2"]', "-5")  # corner 3 pulled across the roof: the crossing is named and marked where it is
    assert "交叉了" in page.text_content("#re-problems") and page.locator("#re-svg .re-bad").count() >= 1
    refused(page, "交叉了")
    page.fill('[data-vx="2"]', "60")
    assert page.text_content("#re-problems") == ""
    page.click('[data-re-act="save"]')
    page.wait_for_function("location.hash === '#new'")
    project = saved(root)[0]
    assert project["roof"]["outline"] == [list(p) for p in SAMPLE] and errors == []


def test_codex_r12_exact_coordinates_of_the_sample_turned_17_degrees_keep_1960_square_metres(editor):
    page, errors, root = editor
    page.click('[data-re-mode="1"]')
    trace(page, SAMPLE)
    a = math.radians(17)
    exact = [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)) for x, y in SAMPLE]
    for i, (x, y) in enumerate(exact):
        page.fill(f'[data-vx="{i}"]', f"{x:.6f}")
        page.fill(f'[data-vy="{i}"]', f"{y:.6f}")
    assert page.text_content("#re-size").startswith("1,960 m²") and page.text_content("#re-problems") == ""
    save(page)
    project, folder = saved(root)
    assert abs(area(project["roof"]["outline"]) - 1960) < 0.01 and len(project["roof"]["outline"]) == 10
    reopen(page, folder)
    assert len(shown(page)) == 10 and max(map(math.dist, shown(page), exact)) < 0.01 and errors == []
