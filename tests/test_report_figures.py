"""Numerical labels remain traceable without changing plotted data."""
import re

from guangzhu.report.figures import bars, cashflow, nice_length, number, plan


def test_svg_half_up_labels_have_raw_titles():
    energy = str(bars([('a', 1111.4989), ('b', 1112.5)], 'kWh/kWp'))
    assert '原值 1111.4989</title>1,111</text>' in energy
    assert '原值 1112.5</title>1,113</text>' in energy
    sensitivity = str(bars([('报价 ↓', -0.125)], '回本变化（年）'))
    assert '原值 -0.125</title>-0.13</text>' in sensitivity
    assert number(4.165, 2) == '4.17'


def test_cashflow_labels_retain_exact_raw_values():
    figure = str(cashflow(dict(cashflows=[dict(year=0, cumulative_cny=-50.5),
                                        dict(year=25, cumulative_cny=250.5)], payback_years=4.165)))
    assert '最高 251；最低 -51' in figure
    assert '原值 250.5；-50.5' in figure
    assert '原值 4.165</title>回本 4.17年' in figure


def roof(width, depth, columns=0, size=1.0):
    """A plain rectangular roof with one row of modules, each module its own string."""
    modules = [dict(id=f'M{i}', corners=[[i * size, 0], [i * size + size, 0], [i * size + size, size], [i * size, size]],
                    center=[i * size + size / 2, size / 2]) for i in range(columns)]
    return dict(project=dict(roof=dict(outline=[[0, 0], [width, 0], [width, depth], [0, depth]], keepouts=[], obstacles=[])),
                design=dict(modules=modules), shading=dict(modules=[]),
                electrical=dict(strings=[dict(id=f'S{i}', module_ids=[f'M{i}']) for i in range(columns)]))


def outline(figure):
    """Pixel box of the roof polygon (the one titled with the axes)."""
    points = re.search(r'<polygon points="([^"]+)"[^>]*><title>屋顶轮廓', str(figure))[1]
    xs, ys = zip(*(map(float, p.split(',')) for p in points.split()))
    return max(xs) - min(xs), max(ys) - min(ys), int(re.search(r'viewBox="0 0 700 (\d+)"', str(figure))[1])


def test_plan_follows_the_roof_shape_instead_of_a_fixed_canvas():
    # T20: a wide roof fills the width and a deep roof fills the height cap, both at true proportions.
    width, height, canvas = outline(plan(roof(200, 40)))
    assert width == 640 and abs(height / width - 40 / 200) < 1e-9 and canvas == round(34 + height + 56)
    width, height, canvas = outline(plan(roof(30, 150)))
    assert height == 900 and abs(width / height - 30 / 150) < 1e-9
    assert outline(plan(roof(30, 150), tallest=520))[1] == 520


def test_string_labels_only_when_modules_are_big_enough_on_paper():
    big, small = str(plan(roof(20, 5, 3, 2.0))), str(plan(roof(600, 150, 3, 2.0)))
    assert all(f'>S{i}</text>' in big for i in range(3)) and '串号太密' not in big
    assert not re.search(r'>S\d</text>', small) and '串号太密未全部标出，见电气页' in small


def test_scale_bar_is_one_two_or_five_times_a_power_of_ten():
    assert [nice_length(span) for span in (3, 40, 95, 260, 1800)] == [0.5, 10, 20, 50, 500]
