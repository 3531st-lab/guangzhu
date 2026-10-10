"""T06 known added-load answers exclude the open space between rack rows."""

import json
import math

import pytest

from guangzhu import structure
from guangzhu.config import DATA_DIR
from guangzhu.models import Design, LayoutParams, Module, WindSettings, validate_project


def project():
    return validate_project(json.loads((DATA_DIR / "demo/projects/changzhou-demo/project.json").read_text(encoding="utf-8")))


def two_racks(orientation, tiers, separation=10):
    beta = math.radians(25)
    width, slope = (1.096, 2.384) if orientation == "portrait" else (2.384, 1.096)
    modules = []
    for row in (1, 2):
        for tier in range(1, tiers + 1):
            x = 3
            y = 3 + (row - 1) * separation + (tier - 1) * (slope + .02) * math.cos(beta)
            z = .3 + (tier - 1) * (slope + .02) * math.sin(beta)
            dy, dz = slope * math.cos(beta), slope * math.sin(beta)
            modules.append(Module(id=f"R{row:02}-{tier}-C001", row=row, tier=tier, col=1,
                                  center=(x + width / 2, y + dy / 2, z + dz / 2),
                                  corners=((x, y, z), (x + width, y, z), (x + width, y + dy, z + dz), (x, y + dy, z + dz)),
                                  tilt=25, azimuth=180, orientation=orientation))
    return Design(params=LayoutParams(orientation=orientation, rows_per_rack=tiers), modules=modules)


def test_portrait_one_tier_and_landscape_two_tiers_match_independent_load_answers():
    site = project()
    # Isolate rack geometry with an explicit synthetic zero-wind case: 28.6+6 kg/panel.
    # Real default wind failure at the original 0.5 capacity is covered in test_t31.
    site.roof.wind = WindSettings(basic_pressure_kpa=0)
    answers = [("portrait", 1, 69.2, 4.736117979335459, 69.2 * .00981 / 4.736117979335459),
               ("landscape", 2, 138.4, 9.558661469242733, 138.4 * .00981 / 9.558661469242733)]
    for orientation, tiers, mass, area, expected in answers:
        design = two_racks(orientation, tiers)
        before = design.model_dump(mode="json")
        result = structure.calculate(site, design)
        assert result["mass_kg"] == pytest.approx(mass)
        assert result["rack_projection_area_m2"] == pytest.approx(area, abs=1e-10)
        assert result["added_kn_m2"] == pytest.approx(expected, abs=1e-12)
        assert result["status"] == "pass" and result["capacity_kn_m2"] == .5
        assert "总平均" in result["evidence"] and "示意" in result["note"]
        assert "不能代替结构复核" in result["note"] and result['ballast_mass_kg'] == 0
        assert "不含排间空地" in result["note"] and "data/catalog/racking.csv" in result["source_ref"]
        assert result == structure.calculate(site, design)
        assert design.model_dump(mode="json") == before
        distant = structure.calculate(site, two_racks(orientation, tiers, separation=100))
        assert distant["rack_projection_area_m2"] == pytest.approx(area)
        assert distant["added_kn_m2"] == pytest.approx(expected)
        # Including row gaps would give a lower, non-conservative load.
        width = 1.096 if orientation == "portrait" else 2.384
        gross_area = width * 10 + area / 2
        assert mass * 9.81 / 1000 / gross_area < expected


def test_load_is_compared_with_user_capacity_and_empty_design_is_zero():
    site, design = project(), two_racks("portrait", 1)
    site.roof.wind = WindSettings(basic_pressure_kpa=0)
    expected = 69.2 * .00981 / 4.736117979335459
    site.roof.load_capacity_kn_m2 = .1
    result = structure.calculate(site, design)
    assert result["status"] == "fail" and result["added_kn_m2"] == pytest.approx(expected)
    site.roof.load_capacity_kn_m2 = expected + 1e-12
    assert structure.calculate(site, design)["status"] == "pass"
    empty = structure.calculate(site, Design(params=LayoutParams()))
    assert empty["status"] == "pass"
    assert empty["added_kn_m2"] == empty["mass_kg"] == empty["rack_projection_area_m2"] == 0
