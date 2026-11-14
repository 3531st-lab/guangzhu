"""Comprehensive tests for Satellite <-> 3D Bidirectional Linkage & 12-Factor Optimization Engine."""

from __future__ import annotations

import shutil
from fastapi.testclient import TestClient

from guangzhu import myroofs, project as storage
from guangzhu.api import app
from guangzhu.config import PROJECTS_DIR, ROOT
from guangzhu.satmap_multifactor import (
    compute_string_voc_safety,
    compute_wind_snow_structural,
    optimize_satmap_multifactor,
)


def test_3d_catalog_and_from_3d_template_conversion():
    """GET /api/satmap/3d-catalog and GET /api/satmap/from-3d/template/{id} return valid Satellite state."""
    client = TestClient(app)

    r_cat = client.get("/api/satmap/3d-catalog")
    assert r_cat.status_code == 200
    cat = r_cat.json()
    assert cat["ok"] is True
    assert isinstance(cat["projects"], list)
    assert isinstance(cat["my_roofs"], list)
    assert isinstance(cat["templates"], list)
    assert any(t["id"] == "changzhou-demo" for t in cat["templates"])

    r_conv = client.get("/api/satmap/from-3d/template/changzhou-demo")
    assert r_conv.status_code == 200
    conv = r_conv.json()
    assert conv["ok"] is True
    assert conv["source"]["kind"] == "template"
    assert conv["source"]["id"] == "changzhou-demo"
    assert abs(conv["site"]["lat"] - 31.81) < 0.05
    assert len(conv["roof"]["polygon_m"]) >= 4
    # Verify roof polygon is centered around (0, 0) for the satellite map canvas
    xs = [pt[0] for pt in conv["roof"]["polygon_m"]]
    ys = [pt[1] for pt in conv["roof"]["polygon_m"]]
    assert abs(0.5 * (min(xs) + max(xs))) < 0.01
    assert abs(0.5 * (min(ys) + max(ys))) < 0.01
    assert conv["roof"]["building_height_m"] > 0
    assert conv["roof"]["max_load_kg_m2"] > 20.0
    # changzhou-demo has both prism/cylinder obstacles and keepouts
    assert len(conv["obstacles"]) >= 2
    obs_first = conv["obstacles"][0]
    for k in ("id", "kind", "name", "x_m", "y_m", "w_m", "h_m", "height_m", "polygon_m"):
        assert k in obs_first
    assert conv["design"]["orientation_mode"] in ("south_fixed", "east_west", "flush_pitched")
    assert conv["design"]["mount_orientation"] in ("portrait", "landscape")
    assert "dc_kw" in conv["reference_metrics"]

    # Invalid kind -> 422, unknown item -> 404
    assert client.get("/api/satmap/from-3d/invalid-kind/foo").status_code == 422
    assert client.get("/api/satmap/from-3d/project/non-existent-sat-proj-9999").status_code == 404


def test_bidirectional_sync_to_3d_roundtrip_and_3d_result_scene():
    """POST /api/satmap/sync-to-3d creates both a custom my-roof AND a versioned 3D project loadable by #result."""
    client = TestClient(app)
    test_pid = "test-sat-sync-3d-bridge"
    test_rid = "my-test-sat-sync-roof"
    proj_dir = PROJECTS_DIR / test_pid
    roof_dir = myroofs.folder(ROOT) / test_rid

    shutil.rmtree(proj_dir, ignore_errors=True)
    shutil.rmtree(roof_dir, ignore_errors=True)

    try:
        # 1. Run Satellite East-West design first to obtain real placed modules
        r_des = client.post(
            "/api/satmap/design",
            json={
                "offline": True,
                "site": {"name": "常州高新蝴蝶阵联动厂房", "lat": 31.81, "lon": 119.97},
                "roof": {
                    "type": "flat",
                    "parapet_height_m": 0.75,
                    "polygon_m": [[-30.0, -16.0], [30.0, -16.0], [30.0, 16.0], [-30.0, 16.0]],
                    "obstacles": [
                        {
                            "id": "obs-ahu-1",
                            "kind": "hvac",
                            "name": "屋面洁净空调机组",
                            "polygon_m": [[-8.0, -6.0], [-3.0, -6.0], [-3.0, -2.0], [-8.0, -2.0]],
                            "height_m": 2.4,
                        },
                        {
                            "id": "kp-sky-1",
                            "kind": "skylight",
                            "name": "北侧采光天窗",
                            "polygon_m": [[5.0, 6.0], [16.0, 6.0], [16.0, 8.2], [5.0, 8.2]],
                            "height_m": 0.15,
                        },
                    ],
                },
                "layout_params": {"orientation": "landscape", "tilt_deg": 10.0},
                "multifactor_params": {"orientation_mode": "east_west", "albedo": "white_tpo"},
            },
        )
        assert r_des.status_code == 200
        des_data = r_des.json()
        assert des_data["summary"]["module_count"] > 40
        assert des_data["summary"]["south_count"] > 0 and des_data["summary"]["north_count"] > 0

        # 2. Sync to 3D (mode="both")
        r_sync = client.post(
            "/api/satmap/sync-to-3d",
            json={
                "offline": True,
                "project_id": test_pid,
                "roof_id": test_rid,
                "sync_mode": "both",
                "name": "常州高新蝴蝶阵联动厂房",
                "site": {"lat": 31.81, "lon": 119.97},
                "roof_polygon_m": [[-30.0, -16.0], [30.0, -16.0], [30.0, 16.0], [-30.0, 16.0]],
                "roof_type": "flat",
                "building_height_m": 13.5,
                "parapet_height_m": 0.75,
                "orientation_mode": "east_west",
                "mount_orientation": "landscape",
                "tilt_deg": 10.0,
                "albedo": 0.65,
                "module_id": "jinko-jkm580n-72hl4-bdv",
                "inverter_id": "sungrow-sg110cx-p2",
                "obstacles": des_data["roof"]["obstacles"],
                "modules_layout": des_data["modules"],
                "pvsyst_summary": des_data["summary"],
            },
        )
        assert r_sync.status_code == 200, r_sync.text
        sync_json = r_sync.json()
        assert sync_json["ok"] is True
        assert sync_json["project_id"] == test_pid
        assert sync_json["version"] == 1
        assert sync_json["roof_id"] == test_rid
        assert sync_json["jump_result_hash"] == f"#result/{test_pid}?version=1"
        assert sync_json["jump_roof_hash"] == "#roof"
        assert sync_json["diff"]["dc_kw_3d"] > 20.0
        assert sync_json["diff"]["module_count_3d"] > 30
        assert sync_json["diff"]["annual_kwh_3d"] > 15000.0
        assert sync_json["diff"]["load_kg_m2"] > 5.0

        # 3. Verify 3D Project really preserved tall 3D Obstacle AND flat Keepout, and #result API loads cleanly!
        proj_loaded = storage.load(test_pid)
        assert len(proj_loaded.roof.obstacles) == 1
        assert proj_loaded.roof.obstacles[0].height_m == 2.4
        assert len(proj_loaded.roof.keepouts) == 1

        r_res3d = client.get(f"/api/projects/{test_pid}/result?version=1")
        assert r_res3d.status_code == 200
        res3d = r_res3d.json()
        assert res3d["project_id"] == test_pid
        assert res3d["missing"] == []
        assert res3d["scene"]["shading"] is not None
        assert res3d["scene"]["electrical"] is not None
        assert "structure" in res3d["sources"]
        assert res3d["scene"]["wind"] is not None
        assert res3d["summary"]["yield_kwh"]["p50"] > 15000.0
        assert len(res3d["scene"]["design"]["modules"]) == sync_json["diff"]["module_count_3d"]
        az_set = {round(float(m["azimuth"]), 1) for m in res3d["scene"]["design"]["modules"]}
        assert az_set == {90.0, 270.0}

        # 4. Verify 3D Catalog now lists both the synced project and my-roof, and from-3d roundtrips both!
        r_cat2 = client.get("/api/satmap/3d-catalog")
        cat2 = r_cat2.json()
        assert any(p["id"] == test_pid and p["has_result"] is True for p in cat2["projects"])
        assert any(mr["id"] == test_rid and mr["obstacle_count"] == 2 for mr in cat2["my_roofs"])

        r_back_proj = client.get(f"/api/satmap/from-3d/project/{test_pid}")
        assert r_back_proj.status_code == 200
        bp = r_back_proj.json()
        assert bp["design"]["orientation_mode"] == "east_west"
        assert bp["design"]["mount_orientation"] == "landscape"
        assert bp["reference_metrics"]["dc_kw"] == sync_json["diff"]["dc_kw_3d"]
        assert len(bp["obstacles"]) == 2

        r_back_roof = client.get(f"/api/satmap/from-3d/my-roof/{test_rid}")
        assert r_back_roof.status_code == 200
        br = r_back_roof.json()
        assert br["source"]["kind"] == "my-roof"
        assert abs(br["roof"]["parapet_height_m"] - 0.75) < 0.02

        # 5. Re-syncing same project_id appends v2 cleanly!
        r_sync_v2 = client.post(
            "/api/satmap/sync-to-3d",
            json={
                "offline": True,
                "project_id": test_pid,
                "sync_mode": "project",
                "name": "常州高新蝴蝶阵联动厂房",
                "site": {"lat": 31.81, "lon": 119.97},
                "roof_polygon_m": [[-30.0, -16.0], [30.0, -16.0], [30.0, 16.0], [-30.0, 16.0]],
                "roof_type": "flat",
                "orientation_mode": "south_fixed",
                "tilt_deg": 16.0,
            },
        )
        assert r_sync_v2.status_code == 200
        assert r_sync_v2.json()["version"] == 2
        assert r_sync_v2.json()["roof_id"] is None
    finally:
        shutil.rmtree(proj_dir, ignore_errors=True)
        shutil.rmtree(roof_dir, ignore_errors=True)


def test_multifactor_12_engineering_dimensions_and_endpoint():
    """Verify all 12 real-world physics factors in satmap_multifactor & POST /api/satmap/optimize-multifactor."""
    client = TestClient(app)

    # 1. Extreme Cold Voc & Hot Vmpp String Safety
    voc_warm = compute_string_voc_safety(
        {"voc_v": 51.5, "vmp_v": 43.0, "beta_voc_pct_c": -0.26},
        {"max_dc_v": 1100.0, "mppt_v_min": 200.0, "mppt_v_max": 1000.0},
        extreme_temp_min_c=5.0,
        extreme_temp_max_c=38.0,
        requested_series=21,
    )
    voc_frigid = compute_string_voc_safety(
        {"voc_v": 51.5, "vmp_v": 43.0, "beta_voc_pct_c": -0.26},
        {"max_dc_v": 1100.0, "mppt_v_min": 200.0, "mppt_v_max": 1000.0},
        extreme_temp_min_c=-32.0,
        extreme_temp_max_c=38.0,
        requested_series=21,
    )
    assert voc_frigid["max_series_safe"] < voc_warm["max_series_safe"]
    assert voc_frigid["overvoltage_risk"] is True  # 21 modules x ~59.1V > 1100V!
    assert voc_frigid["cold_voc_v"] <= 1100.0  # Recommended series stays strictly safe

    # 2. Wind Uplift Keepout Setback Scaling & Snow Shedding Check
    st_calm = compute_wind_snow_structural(
        orientation_mode="south_fixed",
        fixing_type="ballast",
        rack_rows=1,
        tilt_deg=15.0,
        building_height_m=15.0,
        base_setback_m=0.8,
        basic_wind_w0_kn_m2=0.40,
        basic_snow_s0_kn_m2=0.20,
        max_roof_load_kg_m2=60.0,
    )
    st_typhoon = compute_wind_snow_structural(
        orientation_mode="south_fixed",
        fixing_type="ballast",
        rack_rows=1,
        tilt_deg=6.0,
        building_height_m=15.0,
        base_setback_m=0.8,
        basic_wind_w0_kn_m2=0.80,
        basic_snow_s0_kn_m2=0.65,
        max_roof_load_kg_m2=60.0,
    )
    assert st_typhoon["typhoon_mode"] is True
    assert st_typhoon["effective_setback_m"] > st_calm["effective_setback_m"]
    assert st_typhoon["corner_keepout_m"] > 1.0
    assert st_typhoon["ballast_kg_per_module"] > st_calm["ballast_kg_per_module"]
    assert st_typhoon["snow_loss_pct"] > st_calm["snow_loss_pct"]
    assert st_typhoon["snow_ok"] is False  # 6° tilt in 0.65 kN/m² heavy snow triggers warning

    # 3. Tight Dead-Load Cap (18 kg/m²) + Obstacles + Parapet Shading Pruning + Commercial Afternoon Load
    roof_poly = [[-34.0, -18.0], [34.0, -18.0], [34.0, 18.0], [-34.0, 18.0]]
    obstacles = [
        # Tall elevator shaft on south side casting winter shadow onto adjacent modules
        {
            "id": "obs-elev",
            "kind": "elevator",
            "name": "南侧电梯机房",
            "polygon_m": [[-6.0, -14.0], [6.0, -14.0], [6.0, -9.0], [-6.0, -9.0]],
            "height_m": 5.2,
        },
        # Low pipe rack (1.1m) that elevated_canopy (2.8m) can bridge right over
        {
            "id": "obs-pipe",
            "kind": "pipe",
            "name": "低矮蒸汽管廊",
            "polygon_m": [[-22.0, 2.0], [22.0, 2.0], [22.0, 5.5], [-22.0, 5.5]],
            "height_m": 1.1,
        },
    ]

    r_opt = client.post(
        "/api/satmap/optimize-multifactor",
        json={
            "offline": True,
            "site": {"lat": 32.4568, "lon": 119.9182},
            "roof": {
                "roof_type": "flat",
                "polygon_m": roof_poly,
                "building_height_m": 14.0,
                "parapet_height_m": 1.35,
            },
            "obstacles": obstacles,
            "multifactor_params": {
                "max_roof_load_kg_m2": 18.0,
                "basic_wind_w0_kn_m2": 0.70,
                "basic_snow_s0_kn_m2": 0.35,
                "extreme_temp_min_c": -12.0,
                "extreme_temp_max_c": 41.0,
                "albedo": "white_tpo",
                "pollution_level": "coastal_salt",
                "max_module_shading_loss_pct": 8.0,
                "fire_lane_width_m": 1.2,
                "maint_walkway_interval_m": 16.0,
                "load_profile": "commercial_afternoon",
                "objective": "balanced",
            },
        },
    )
    assert r_opt.status_code == 200, r_opt.text
    opt = r_opt.json()
    assert opt["ok"] is True
    assert opt["recommended_id"]
    assert "string_voc_check" in opt and opt["string_voc_check"]["cold_voc_v"] < 1100.0
    assert "structural_check" in opt
    assert len(opt["schemes"]) >= 5

    by_id = {s["id"]: s for s in opt["schemes"]}
    rec = by_id[opt["recommended_id"]]
    # Under 18 kg/m² cap, heavy concrete ballast (>30 kg/m²) must fail load_ok and NOT be recommended!
    assert by_id["south_fixed_ballast_1p"]["constraints"]["load_ok"] is False
    assert rec["constraints"]["load_ok"] is True
    assert rec["load_kg_m2"] <= 18.0

    # Verify 6-axis factor_scores exist on every scheme
    for s in opt["schemes"]:
        fs = s["factor_scores"]
        for axis in ("capacity", "yield", "economics", "safety", "self_use", "shading_resilience"):
            assert 0.0 <= fs[axis] <= 100.0
        assert "pareto_optimal" in s

    # Verify 3D obstacle + 1.35m parapet pruned heavily shaded modules (>0 pruned)
    assert any(s["pruned_shaded_modules"] > 0 for s in opt["schemes"])

    # Verify elevated_canopy bridged the low 1.1m pipe rack while keeping the 5.2m elevator tower
    assert by_id["elevated_canopy_bridge"]["bridged_obstacle_count"] == 1

    # Verify East-West butterfly boosts afternoon self-consumption vs South-fixed under commercial_afternoon
    ew_scheme = by_id["east_west_butterfly"]
    south_scheme = by_id["south_fixed_ballast_1p"]
    assert ew_scheme["gcr"] > south_scheme["gcr"]
    assert ew_scheme["self_use_pct"] > south_scheme["self_use_pct"]

    # 4. Verify Albedo & Pollution physical monotonicity
    opt_tpo_clean = optimize_satmap_multifactor(
        {
            "offline": True,
            "lat": 32.4568,
            "lon": 119.9182,
            "roof_polygon_m": [[-25.0, -14.0], [25.0, -14.0], [25.0, 14.0], [-25.0, 14.0]],
            "multifactor_params": {"albedo": 0.65, "pollution_level": "clean"},
        }
    )
    opt_asphalt_ind = optimize_satmap_multifactor(
        {
            "offline": True,
            "lat": 32.4568,
            "lon": 119.9182,
            "roof_polygon_m": [[-25.0, -14.0], [25.0, -14.0], [25.0, 14.0], [-25.0, 14.0]],
            "multifactor_params": {"albedo": 0.12, "pollution_level": "industrial"},
        }
    )
    s_tpo = next(s for s in opt_tpo_clean["schemes"] if s["id"] == "south_fixed_ballast_1p")
    s_asp = next(s for s in opt_asphalt_ind["schemes"] if s["id"] == "south_fixed_ballast_1p")
    assert s_tpo["specific_yield_kwh_kwp"] > s_asp["specific_yield_kwh_kwp"]
    assert s_tpo["bifacial_gain_pct"] > s_asp["bifacial_gain_pct"]


def test_sync_my_roof_only_and_satmap_design_multifactor_enrichment():
    """Verify sync_mode='my_roof', metal roof sync, and enriched POST /api/satmap/design multifactor options."""
    client = TestClient(app)
    test_rid = "my-test-metal-only-roof"
    roof_dir = myroofs.folder(ROOT) / test_rid
    shutil.rmtree(roof_dir, ignore_errors=True)

    try:
        r_roof = client.post(
            "/api/satmap/sync-to-3d",
            json={
                "roof_id": test_rid,
                "sync_mode": "my_roof",
                "name": "靖江彩钢瓦单坡同步测试屋面",
                "site": {"lat": 32.02, "lon": 120.26},
                "roof_polygon_m": [[-40.0, -15.0], [40.0, -15.0], [40.0, 15.0], [-40.0, 15.0]],
                "roof_type": "single_slope",
                "slope_deg": 6.0,
                "building_height_m": 11.5,
                "obstacles": [
                    {
                        "id": "obs-box-1",
                        "kind": "hvac",
                        "name": "排风箱",
                        "x_m": 0.0,
                        "y_m": -5.0,
                        "w_m": 3.0,
                        "h_m": 2.4,
                        "height_m": 1.6,
                    }
                ],
            },
        )
        assert r_roof.status_code == 200
        rj = r_roof.json()
        assert rj["ok"] is True
        assert rj["project_id"] is None
        assert rj["roof_id"] == test_rid
        assert rj["jump_roof_hash"] == "#roof"

        r_from = client.get(f"/api/satmap/from-3d/my_roof/{test_rid}")
        assert r_from.status_code == 200
        fj = r_from.json()
        assert fj["roof"]["roof_type"] == "single_slope"
        assert abs(fj["roof"]["slope_deg"] - 6.0) < 0.2
        assert len(fj["obstacles"]) == 1
        assert fj["obstacles"][0]["height_m"] == 1.6

        # Enriched /api/satmap/design with elevated_canopy + 2P + fire lane + walkway + shade pruning + export_all
        r_canopy = client.post(
            "/api/satmap/design",
            json={
                "offline": True,
                "site": {"lat": 32.4568, "lon": 119.9182},
                "roof": {
                    "type": "flat",
                    "parapet_height_m": 1.2,
                    "polygon_m": [[-36.0, -18.0], [36.0, -18.0], [36.0, 18.0], [-36.0, 18.0]],
                    "obstacles": [
                        {"id": "low-1", "name": "低矮风机", "x_m": 0.0, "y_m": 0.0, "w_m": 6.0, "h_m": 4.0, "height_m": 1.2},
                        {"id": "tall-1", "name": "高耸塔楼", "x_m": -12.0, "y_m": -12.0, "w_m": 4.0, "h_m": 4.0, "height_m": 6.5},
                    ],
                },
                "multifactor_params": {
                    "orientation_mode": "elevated_canopy",
                    "rack_type": "2P",
                    "canopy_clear_height_m": 2.8,
                    "fire_lane_width_m": 1.2,
                    "maint_walkway_interval_m": 14.0,
                    "max_module_shading_loss_pct": 9.0,
                    "load_profile": "export_all",
                },
            },
        )
        assert r_canopy.status_code == 200
        cj = r_canopy.json()
        assert cj["ok"] is True
        assert cj["summary"]["orientation_mode"] == "elevated_canopy"
        assert cj["summary"]["rack_type"] == "2P"
        assert cj["summary"]["self_use_pct"] == 0.0
        assert cj["multifactor"]["pruned_shaded_modules"] == len(cj["pruned_modules"])

        # Invalid sync_mode -> 422
        assert client.post("/api/satmap/sync-to-3d", json={"sync_mode": "invalid_mode"}).status_code == 422
        assert client.post("/api/satmap/optimize-multifactor", json={"roof_polygon_m": [[0, 0], [1, 0]]}).status_code == 422
    finally:
        shutil.rmtree(roof_dir, ignore_errors=True)


def test_sync_to_existing_centered_3d_project_preserves_origin_and_parent_alignment():
    """Appending v3 onto an existing centered 3D project ([-39..39, -14..14]) preserves (orig_minx, orig_miny) so v2 parent wireframe stays aligned."""
    import json
    from guangzhu import analysis, layout
    from guangzhu.models import Project

    client = TestClient(app)
    test_pid = "test-sat-centered-origin-v3"
    test_rid = "my-test-sat-centered-origin"
    proj_dir = PROJECTS_DIR / test_pid
    roof_dir = myroofs.folder(ROOT) / test_rid

    shutil.rmtree(proj_dir, ignore_errors=True)
    shutil.rmtree(roof_dir, ignore_errors=True)

    try:
        # 1. Seed an existing 3D project centered at (0, 0): [-39..39, -14..14] with v1 and v2 designs
        base_tpl = ROOT / "data" / "demo" / "projects" / "changzhou-demo" / "project.json"
        rec = json.loads(base_tpl.read_text(encoding="utf-8"))
        rec["id"] = test_pid
        rec["name"] = "泰州居中坐标对齐复盘仓库"
        rec.pop("collection", None)
        rec.pop("facts", None)
        rec.pop("park", None)
        rec["designs"] = []
        rec["site"] = {"lat": 32.46, "lon": 119.92, "timezone": "Asia/Shanghai", "albedo": 0.25}
        rec["roof"] = {
            "outline": [[-39.0, -14.0], [39.0, -14.0], [39.0, 14.0], [-39.0, 14.0]],
            "type": "flat",
            "height_m": 11.0,
            "parapet_height_m": 0.8,
            "load_capacity_kn_m2": 1.5,
            "obstacles": [
                {
                    "id": "obs-1",
                    "label": "原有机房",
                    "kind": "prism",
                    "height_m": 2.2,
                    "footprint": [[-6.0, -4.0], [2.0, -4.0], [2.0, 2.0], [-6.0, 2.0]],
                }
            ],
            "keepouts": [],
            "surroundings": [],
        }
        proj_obj = Project.model_validate(rec)
        storage.save(proj_obj)

        for ver, tilt in ((1, 20.0), (2, 15.0)):
            d_obj = layout.generate_layout(proj_obj, {"tilt_deg": tilt, "orientation": "portrait"})
            d_obj.version = ver
            d_obj.parent_version = ver - 1 if ver > 1 else None
            d_obj.reason = f"初始版本 v{ver}"
            storage.save_design(test_pid, d_obj, offline=True)
            analysis.analyze(test_pid, ver, offline=True)

        # 2. Run Satellite East-West design on the imported [-39..39, -14..14] outline and sync back to test_pid (v3)
        r_des = client.post(
            "/api/satmap/design",
            json={
                "offline": True,
                "site": {"name": "泰州居中坐标对齐复盘仓库", "lat": 32.46, "lon": 119.92},
                "roof": {
                    "type": "flat",
                    "parapet_height_m": 0.8,
                    "polygon_m": [[-39.0, -14.0], [39.0, -14.0], [39.0, 14.0], [-39.0, 14.0]],
                    "obstacles": [
                        {
                            "id": "obs-1",
                            "kind": "hvac",
                            "name": "原有机房",
                            "polygon_m": [[-6.0, -4.0], [2.0, -4.0], [2.0, 2.0], [-6.0, 2.0]],
                            "height_m": 2.2,
                        }
                    ],
                },
                "layout_params": {"orientation": "landscape", "tilt_deg": 10.0},
                "multifactor_params": {"orientation_mode": "east_west"},
            },
        )
        assert r_des.status_code == 200
        des_data = r_des.json()

        r_sync = client.post(
            "/api/satmap/sync-to-3d",
            json={
                "offline": True,
                "project_id": test_pid,
                "roof_id": test_rid,
                "sync_mode": "both",
                "name": "泰州居中坐标对齐复盘仓库",
                "site": {"lat": 32.46, "lon": 119.92},
                "roof_polygon_m": [[-39.0, -14.0], [39.0, -14.0], [39.0, 14.0], [-39.0, 14.0]],
                "roof_type": "flat",
                "building_height_m": 11.0,
                "parapet_height_m": 0.8,
                "orientation_mode": "east_west",
                "mount_orientation": "landscape",
                "tilt_deg": 10.0,
                "obstacles": des_data["roof"]["obstacles"],
                "modules_layout": des_data["modules"],
                "pvsyst_summary": des_data["summary"],
            },
        )
        assert r_sync.status_code == 200, r_sync.text
        sj = r_sync.json()
        assert sj["version"] == 3

        # 3. Verify project outline, obstacles, v3 modules AND v2 parent_design all remain in [-39..39, -14..14]
        proj_after = storage.load(test_pid)
        out_xs = [pt[0] for pt in proj_after.roof.outline]
        out_ys = [pt[1] for pt in proj_after.roof.outline]
        assert (min(out_xs), min(out_ys), max(out_xs), max(out_ys)) == (-39.0, -14.0, 39.0, 14.0)

        r_res = client.get(f"/api/projects/{test_pid}/result?version=3")
        assert r_res.status_code == 200
        res3 = r_res.json()
        v3_mods = res3["scene"]["design"]["modules"]
        v2_mods = res3["scene"]["parent_design"]["modules"]
        assert len(v3_mods) > 50 and len(v2_mods) > 50

        for m in v3_mods:
            cx, cy = m["center"][0], m["center"][1]
            assert -39.0 <= cx <= 39.0 and -14.0 <= cy <= 14.0
        for m in v2_mods:
            cx, cy = m["center"][0], m["center"][1]
            assert -39.0 <= cx <= 39.0 and -14.0 <= cy <= 14.0
        # Ensure v3 modules truly span negative coordinates (not shifted to [0..78, 0..28])
        assert any(m["center"][0] < -10.0 for m in v3_mods)
        assert any(m["center"][1] < -5.0 for m in v3_mods)
    finally:
        shutil.rmtree(proj_dir, ignore_errors=True)
        shutil.rmtree(roof_dir, ignore_errors=True)


def test_engineering_health_check_endpoint_and_attached_checks():
    """Verify 8-item POST /api/satmap/engineering-health-check, attached checks in design/multifactor, & /api/guangzhu/* aliases."""
    import json

    client = TestClient(app)
    expected_ids = {
        "dc_ac_ratio",
        "cold_voc_margin",
        "hot_vmpp_window",
        "roof_dead_load",
        "wind_uplift_setback",
        "dc_voltage_drop",
        "shading_loss",
        "financial_return",
    }

    # 1. Healthy design configuration -> 8/8 PASS
    r_ok = client.post(
        "/api/satmap/engineering-health-check",
        json={
            "dc_kw": 290.0,
            "ac_kw": 250.0,
            "cold_voc_v": 995.0,
            "max_dc_v": 1100.0,
            "hot_vmpp_v": 665.0,
            "mppt_v_min": 200.0,
            "mppt_v_max": 1000.0,
            "load_kg_m2": 26.5,
            "max_load_kg_m2": 120.0,
            "effective_setback_m": 1.0,
            "basic_wind_w0_kn_m2": 0.45,
            "dc_drop_pct": 0.92,
            "shading_loss_pct": 2.1,
            "irr_pct": 14.8,
            "payback_yr": 5.3,
        },
    )
    assert r_ok.status_code == 200
    hc_ok = r_ok.json()
    assert hc_ok["ok"] is True
    assert hc_ok["overall_status"] == "pass"
    assert hc_ok["pass_count"] == 8 and hc_ok["fail_count"] == 0
    assert hc_ok["ready_for_delivery"] is True
    assert hc_ok["score"] == 100.0
    assert {it["id"] for it in hc_ok["items"]} == expected_ids
    assert all(it["status"] == "pass" and len(it["fix_hint_zh"]) >= 6 for it in hc_ok["items"])

    # 2. Violating configuration -> 8/8 FAIL with actionable Chinese fix_hint_zh
    r_bad = client.post(
        "/api/satmap/engineering-health-check",
        json={
            "dc_kw": 70.0,
            "ac_kw": 110.0,
            "cold_voc_v": 1168.0,
            "max_dc_v": 1100.0,
            "hot_vmpp_v": 172.0,
            "mppt_v_min": 200.0,
            "mppt_v_max": 1000.0,
            "load_kg_m2": 42.0,
            "max_load_kg_m2": 18.0,
            "effective_setback_m": 0.35,
            "basic_wind_w0_kn_m2": 0.80,
            "dc_drop_pct": 3.15,
            "shading_loss_pct": 14.2,
            "irr_pct": 3.4,
            "payback_yr": 17.5,
        },
    )
    assert r_bad.status_code == 200
    hc_bad = r_bad.json()
    assert hc_bad["overall_status"] == "fail"
    assert hc_bad["fail_count"] == 8
    assert hc_bad["ready_for_delivery"] is False
    assert all(it["status"] == "fail" and it["fix_hint_zh"] for it in hc_bad["items"])

    # 3. Attached health_check in /api/satmap/design and /api/satmap/optimize-multifactor
    r_des = client.post(
        "/api/satmap/design",
        json={
            "offline": True,
            "site": {"name": "常州健康度校核示范厂房", "lat": 31.81, "lon": 119.97},
            "roof": {"type": "flat", "polygon_m": [[-32.0, -16.0], [32.0, -16.0], [32.0, 16.0], [-32.0, 16.0]]},
        },
    )
    assert r_des.status_code == 200
    des_j = r_des.json()
    assert "health_check" in des_j
    assert len(des_j["health_check"]["items"]) == 8

    r_opt = client.post(
        "/api/satmap/optimize-multifactor",
        json={
            "offline": True,
            "site": {"lat": 32.4568, "lon": 119.9182},
            "roof": {"roof_type": "flat", "polygon_m": [[-28.0, -14.0], [28.0, -14.0], [28.0, 14.0], [-28.0, 14.0]]},
        },
    )
    assert r_opt.status_code == 200
    opt_j = r_opt.json()
    assert "health_check" in opt_j and len(opt_j["health_check"]["items"]) == 8
    assert all("health_check" in s and len(s["health_check"]["items"]) == 8 for s in opt_j["schemes"])

    # 4. Brand-clean /api/guangzhu/* aliases work alongside /api/pvsyst/* with zero "pvsyst" text in values
    r_sim = client.post("/api/guangzhu/simulate", json={"lat": 32.4568, "lon": 119.9182, "dc_kw": 290.0, "offline": True})
    assert r_sim.status_code == 200
    assert "pvsyst" not in json.dumps(r_sim.json(), ensure_ascii=False).lower()
    r_wx = client.get("/api/guangzhu/live-weather?lat=32.4568&lon=119.9182&dc_kw=290&offline=true")
    assert r_wx.status_code == 200


def test_export_delivery_bundle_four_files_privacy_and_open_folder(monkeypatch):
    """Verify POST /api/satmap/export-delivery-bundle creates PDF + DXF + UTF-8-SIG BOM CSV + JSON with zero path/brand leaks."""
    import io
    import json
    import os
    import zipfile

    client = TestClient(app)
    created_bundles: list[str] = []

    try:
        r_exp = client.post(
            "/api/satmap/export-delivery-bundle",
            json={
                "offline": True,
                "open_folder": False,
                "project_name": "泰州祥泰零碳仓库_PVsyst测试脱敏",
                "site": {"lat": 32.4568, "lon": 119.9182},
                "roof": {
                    "type": "flat",
                    "parapet_height_m": 0.7,
                    "polygon_m": [[-34.0, -16.0], [34.0, -16.0], [34.0, 16.0], [-34.0, 16.0]],
                    "obstacles": [
                        {"id": "obs-1", "name": "排风井", "x_m": -4.0, "y_m": 2.0, "w_m": 3.0, "h_m": 3.0, "height_m": 1.8}
                    ],
                },
                "multifactor_params": {"orientation_mode": "east_west", "albedo": "white_tpo"},
            },
        )
        assert r_exp.status_code == 200, r_exp.text
        bundle = r_exp.json()
        assert bundle["ok"] is True
        bundle_id = bundle["bundle_id"]
        created_bundles.append(bundle_id)

        assert bundle["file_count"] == 4
        assert bundle["storage_mode"] == "cache"
        assert bundle["opened_natively"] is False
        assert bundle["folder_name"].startswith("光筑工程交付包_")

        # Strict check: ZERO raw OS user home paths & ZERO "pvsyst" strings in returned JSON
        raw_resp_str = json.dumps(bundle, ensure_ascii=False)
        assert "Users" not in raw_resp_str
        assert "/home/" not in raw_resp_str
        assert "pvsyst" not in raw_resp_str.lower()

        files_by_key = {f["key"]: f for f in bundle["files"]}
        assert set(files_by_key.keys()) == {"report_pdf", "master_dxf", "bom_csv", "verification_json"}

        # 1. Verify PDF download
        r_pdf = client.get(files_by_key["report_pdf"]["download_url"])
        assert r_pdf.status_code == 200
        assert r_pdf.content[:5] == b"%PDF-"
        assert len(r_pdf.content) > 8192

        # 2. Verify CAD DXF download
        r_dxf = client.get(files_by_key["master_dxf"]["download_url"])
        assert r_dxf.status_code == 200
        dxf_txt = r_dxf.content.decode("utf-8")
        assert "ROOF_OUTLINE" in dxf_txt and "PV_MODULES" in dxf_txt and "PV_STRINGS" in dxf_txt

        # 3. Verify UTF-8-SIG Engineering BOM CSV download
        r_csv = client.get(files_by_key["bom_csv"]["download_url"])
        assert r_csv.status_code == 200
        assert r_csv.content.startswith(b"\xef\xbb\xbf")  # UTF-8-SIG BOM for Excel
        csv_txt = r_csv.content.decode("utf-8-sig")
        assert "光伏发电组件" in csv_txt and "并网逆变设备" in csv_txt and "合计" in csv_txt
        assert "pvsyst" not in csv_txt.lower()
        assert "Users" not in csv_txt

        # 4. Verify Engineering & Multi-Factor Verification JSON download
        r_json = client.get(files_by_key["verification_json"]["download_url"])
        assert r_json.status_code == 200
        ver_txt = r_json.content.decode("utf-8")
        assert "pvsyst" not in ver_txt.lower()
        assert "Users" not in ver_txt
        ver_doc = json.loads(ver_txt)
        assert ver_doc["schema_version"] == "guangzhu.delivery_verification.v2"
        assert len(ver_doc["health_check"]["items"]) == 8
        assert ver_doc["summary"]["dc_kw"] > 20.0

        # 5. Verify ZIP archive download contains all 4 files
        r_zip = client.get(bundle["download_zip_url"])
        assert r_zip.status_code == 200
        with zipfile.ZipFile(io.BytesIO(r_zip.content), "r") as zf:
            names = zf.namelist()
            assert len(names) == 4
            assert any(n.endswith(".pdf") for n in names)
            assert any(n.endswith(".dxf") for n in names)
            assert any(n.endswith(".csv") for n in names)
            assert any(n.endswith(".json") for n in names)

        # 6. Verify open_folder=True invokes os.startfile safely and falls back gracefully on OSError
        opened_paths: list[str] = []
        monkeypatch.setattr(os, "startfile", lambda p: opened_paths.append(p), raising=False)
        r_open = client.post(
            "/api/satmap/export-delivery-bundle",
            json={
                "offline": True,
                "open_folder": True,
                "test_mode": True,
                "project_name": "打开目录验证项目",
                "summary": ver_doc["summary"],
                "site": ver_doc["site"],
                "roof": {
                    "type": "flat",
                    "polygon_m": [[-20.0, -10.0], [20.0, -10.0], [20.0, 10.0], [-20.0, 10.0]],
                    "obstacles": [],
                },
                "modules": [{"id": "M-1", "cx": 0.0, "cy": 0.0, "w": 1.134, "h": 2.278, "slope": "south", "tilt_deg": 15.0, "azimuth_deg": 180.0}],
            },
        )
        assert r_open.status_code == 200
        open_j = r_open.json()
        created_bundles.append(open_j["bundle_id"])
        assert open_j["opened_natively"] is True
        assert len(opened_paths) == 1
        assert "Users" not in json.dumps(open_j, ensure_ascii=False)

        def _raise_os_error(_p: str) -> None:
            raise OSError("headless test environment")

        monkeypatch.setattr(os, "startfile", _raise_os_error, raising=False)
        r_headless = client.post(
            "/api/satmap/export-delivery-bundle",
            json={
                "offline": True,
                "open_folder": True,
                "test_mode": True,
                "project_name": "无头降级验证项目",
                "summary": ver_doc["summary"],
                "site": ver_doc["site"],
                "roof": {"type": "flat", "polygon_m": [[-20.0, -10.0], [20.0, -10.0], [20.0, 10.0], [-20.0, 10.0]], "obstacles": []},
                "modules": [{"id": "M-1", "cx": 0.0, "cy": 0.0, "w": 1.134, "h": 2.278, "slope": "south", "tilt_deg": 15.0, "azimuth_deg": 180.0}],
            },
        )
        assert r_headless.status_code == 200
        hl_j = r_headless.json()
        created_bundles.append(hl_j["bundle_id"])
        assert hl_j["opened_natively"] is False

        # Path traversal / missing bundle -> 404
        assert client.get(f"/api/satmap/delivery-bundle/{bundle_id}/..%2Fsecret.txt").status_code == 404
        assert client.get("/api/satmap/delivery-bundle/bnd-000000-000000/missing.pdf").status_code == 404
    finally:
        for bid in created_bundles:
            shutil.rmtree(ROOT / "data" / "cache" / "delivery-bundles" / bid, ignore_errors=True)

