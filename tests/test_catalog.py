"""Locked CEC equipment loads are tested without public network access."""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

import pandas as pd
import pytest
import requests

from guangzhu import catalog


SUBSET_FILES = {
    "modules": "cec_modules_subset.csv",
    "inverters": "cec_inverters_subset.csv",
}
CACHE_FILES = {"modules": "CEC Modules.csv", "inverters": "CEC Inverters.csv"}
LOCKED_FULL_HASHES = {
    "modules": "a28cf8956a839ed98bb941809b439e4907f5b4c237bd9299bc123fb502c29aff",
    "inverters": "0c1b2188415dad6928f91f1a4c9a820dadc80962549f903d57d9282ba3753760",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, bytes]:
    """Each test receives its own exact copy of the committed offline pair."""
    recorded = {
        kind: (catalog.CATALOG_DIR / filename).read_bytes()
        for kind, filename in SUBSET_FILES.items()
    }
    subset_dir = tmp_path / "catalog"
    subset_dir.mkdir()
    for kind, filename in SUBSET_FILES.items():
        (subset_dir / filename).write_bytes(recorded[kind])
    monkeypatch.setattr(catalog, "CATALOG_DIR", subset_dir)
    monkeypatch.setattr(catalog, "CACHE_DIR", tmp_path / "cache")

    def unexpected_request(*args, **kwargs):
        pytest.fail("A catalog test attempted a real network request.")

    def unexpected_download(url: str):
        pytest.fail(f"Unexpected catalog download: {url}")

    monkeypatch.setattr(requests.Session, "request", unexpected_request)
    monkeypatch.setattr(catalog, "_download_bytes", unexpected_download)
    return recorded


def use_transport_fixture(monkeypatch: pytest.MonkeyPatch, recorded: dict[str, bytes]) -> None:
    """Use tiny known data to test transport, never claim it is the full SAM library."""
    monkeypatch.setattr(catalog, "MODULE_SHA256", sha256(recorded["modules"]))
    monkeypatch.setattr(catalog, "INVERTER_SHA256", sha256(recorded["inverters"]))


def rewrite_subset(kind: str, transform, monkeypatch: pytest.MonkeyPatch) -> None:
    path = catalog.CATALOG_DIR / SUBSET_FILES[kind]
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    transform(rows)
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    data = output.getvalue().encode("utf-8")
    path.write_bytes(data)
    constant = "MODULE_SUBSET_SHA256" if kind == "modules" else "INVERTER_SUBSET_SHA256"
    monkeypatch.setattr(catalog, constant, sha256(data))


def test_locked_sources_and_offline_pair(isolated_storage: dict[str, bytes]) -> None:
    assert catalog.MODULE_SHA256 == LOCKED_FULL_HASHES["modules"]
    assert catalog.INVERTER_SHA256 == LOCKED_FULL_HASHES["inverters"]
    commit = "cba319ded1c32a7f5b3ac76545a29e1f7181d238"
    assert commit in catalog.MODULE_URL and commit in catalog.INVERTER_URL
    module, inverter, meta = catalog.load_cec_equipment(offline=True)
    assert module.name == catalog.MODULE_KEY == "Trina_Solar_TSM_550DE19"
    assert inverter.name == catalog.INVERTER_KEY == "Sungrow__SG60CX_US_{480V}"
    assert module["STC"] == pytest.approx(550)
    assert module["Technology"] == "Mono-c-Si" and float(module["Bifacial"]) == 0
    assert float(module["V_mp_ref"]) == pytest.approx(31.6)
    assert float(inverter["Paco"]) == pytest.approx(60182)
    assert meta["module_name"] == catalog.MODULE_NAME == "Trina Solar TSM-550DE19"
    assert meta["inverter_name"] == catalog.INVERTER_NAME == "Sungrow: SG60CX-US {480V}"
    assert meta["module_key"] == module.name and meta["inverter_key"] == inverter.name
    assert meta["series"] == 22 and meta["parallel"] == 6
    assert meta["dc_capacity_kw"] == pytest.approx(72.6)
    assert meta["dc_ac_ratio"] == pytest.approx(72600 / 60182)
    assert 1.1 <= meta["dc_ac_ratio"] <= 1.25
    assert float(inverter["Mppt_low"]) <= 22 * float(module["V_mp_ref"]) <= float(inverter["Mppt_high"])
    assert meta["source_used"] == "subset"
    assert meta["fullfile_sha256"] == LOCKED_FULL_HASHES
    assert meta["sha256"] == {kind: sha256(data) for kind, data in isolated_storage.items()}


@pytest.mark.parametrize("kind", SUBSET_FILES)
def test_subset_retains_three_headers_and_selected_original_rows(kind: str) -> None:
    path = catalog.CATALOG_DIR / SUBSET_FILES[kind]
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    assert len(rows) == (7 if kind == "modules" else 4)
    assert rows[0][0] == "Name"
    assert all(len(row) == len(rows[0]) for row in rows)
    expected_name = catalog.MODULE_NAME if kind == "modules" else catalog.INVERTER_NAME
    assert rows[3][0] == expected_name
    if kind == "modules":
        assert rows[4][0] == "Jiangsu Runergy New Energy Technology Co Ltd HY-WH144P8-550"
        second = catalog._read_selected(path, rows[4][0], "Jiangsu_Runergy_New_Energy_Technology_Co_Ltd_HY_WH144P8_550")
        assert second["Technology"] == "Mono-c-Si" and float(second["Bifacial"]) == 0
        assert float(second["STC"]) == 550


def test_explicit_offline_ignores_cache_and_never_downloads() -> None:
    catalog.CACHE_DIR.mkdir()
    (catalog.CACHE_DIR / CACHE_FILES["modules"]).write_bytes(b"untrusted cached data")
    _, _, meta = catalog.load_cec_equipment(offline=True)
    assert meta["source_used"] == "subset"


@pytest.mark.parametrize("kind", SUBSET_FILES)
def test_subset_hash_mismatch_is_a_hard_error(kind: str) -> None:
    path = catalog.CATALOG_DIR / SUBSET_FILES[kind]
    path.write_bytes(path.read_bytes() + b"tampered\n")
    with pytest.raises(catalog.CatalogIntegrityError):
        catalog.load_cec_equipment(offline=True)


@pytest.mark.parametrize("kind", SUBSET_FILES)
@pytest.mark.parametrize("normalized_collision", [False, True])
def test_selected_name_and_pvlib_key_must_be_unique(
    kind: str, normalized_collision: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    def duplicate(rows: list[list[str]]) -> None:
        extra = rows[3].copy()
        if normalized_collision:
            extra[0] = catalog.MODULE_KEY if kind == "modules" else catalog.INVERTER_KEY
        rows.append(extra)

    rewrite_subset(kind, duplicate, monkeypatch)
    with pytest.raises(catalog.CatalogDataError):
        catalog.load_cec_equipment(offline=True)


@pytest.mark.parametrize("kind", SUBSET_FILES)
def test_missing_sam_header_rows_are_rejected(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def remove_headers(rows: list[list[str]]) -> None:
        del rows[1:3]

    rewrite_subset(kind, remove_headers, monkeypatch)
    with pytest.raises(catalog.CatalogDataError):
        catalog.load_cec_equipment(offline=True)


@pytest.mark.parametrize(
    "kind,field,value",
    [
        ("modules", "Technology", "Multi-c-Si"),
        ("modules", "Bifacial", "1"),
        ("modules", "STC", "700"),
        ("modules", "R_s", "nan"),
        ("inverters", "Paco", "30000"),
        ("inverters", "Paco", "70000"),
        ("inverters", "Mppt_low", "700"),
    ],
)
def test_verified_bytes_still_require_eligible_equipment(
    kind: str, field: str, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def change_parameter(rows: list[list[str]]) -> None:
        rows[3][rows[0].index(field)] = value

    rewrite_subset(kind, change_parameter, monkeypatch)
    with pytest.raises(catalog.CatalogDataError):
        catalog.load_cec_equipment(offline=True)


@pytest.mark.parametrize("kind", CACHE_FILES)
def test_corrupt_partial_cache_is_rejected_before_download_or_subset(
    kind: str, isolated_storage: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    use_transport_fixture(monkeypatch, isolated_storage)
    catalog.CACHE_DIR.mkdir()
    (catalog.CACHE_DIR / CACHE_FILES[kind]).write_bytes(b"corrupt cached file")
    with pytest.raises(catalog.CatalogIntegrityError):
        catalog.load_cec_equipment()


def test_download_then_cache_and_every_read_rechecks_hash(
    isolated_storage: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    use_transport_fixture(monkeypatch, isolated_storage)
    calls: list[str] = []
    by_url = {
        catalog.MODULE_URL: isolated_storage["modules"],
        catalog.INVERTER_URL: isolated_storage["inverters"],
    }

    def download(url: str) -> bytes:
        calls.append(url)
        return by_url[url]

    monkeypatch.setattr(catalog, "_download_bytes", download)
    first_module, first_inverter, first_meta = catalog.load_cec_equipment()
    assert calls == [catalog.MODULE_URL, catalog.INVERTER_URL]
    assert first_meta["source_used"] == "download"
    for kind, filename in CACHE_FILES.items():
        assert (catalog.CACHE_DIR / filename).read_bytes() == isolated_storage[kind]
    second_module, second_inverter, second_meta = catalog.load_cec_equipment()
    assert second_meta["source_used"] == "cache" and len(calls) == 2
    pd.testing.assert_series_equal(first_module, second_module)
    pd.testing.assert_series_equal(first_inverter, second_inverter)
    assert second_meta["sha256"] == first_meta["sha256"]
    path = catalog.CACHE_DIR / CACHE_FILES["inverters"]
    path.write_bytes(path.read_bytes() + b"later tampering\n")
    with pytest.raises(catalog.CatalogIntegrityError):
        catalog.load_cec_equipment()
    assert len(calls) == 2


@pytest.mark.parametrize("bad_kind", CACHE_FILES)
def test_download_hash_mismatch_is_a_hard_error(
    bad_kind: str, isolated_storage: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    use_transport_fixture(monkeypatch, isolated_storage)
    by_url = {
        catalog.MODULE_URL: isolated_storage["modules"],
        catalog.INVERTER_URL: isolated_storage["inverters"],
    }
    bad_url = catalog.MODULE_URL if bad_kind == "modules" else catalog.INVERTER_URL
    by_url[bad_url] = b"server returned unverified data"
    monkeypatch.setattr(catalog, "_download_bytes", by_url.__getitem__)
    with pytest.raises(catalog.CatalogIntegrityError):
        catalog.load_cec_equipment()
    assert not (catalog.CACHE_DIR / CACHE_FILES[bad_kind]).exists()
    if catalog.CACHE_DIR.exists():
        assert {path.name for path in catalog.CACHE_DIR.iterdir()} <= set(CACHE_FILES.values())


@pytest.mark.parametrize(
    "error",
    [requests.ConnectionError("disconnected"), requests.Timeout("timed out"), requests.HTTPError("503")],
)
def test_only_network_failures_fall_back_to_complete_subset(
    error: requests.RequestException, monkeypatch: pytest.MonkeyPatch
) -> None:
    def download(url: str) -> bytes:
        raise error

    monkeypatch.setattr(catalog, "_download_bytes", download)
    _, _, meta = catalog.load_cec_equipment()
    assert meta["source_used"] == "subset"
    assert str(error) in meta["fallback_reason"]
    assert meta["sha256"] == {
        "modules": catalog.MODULE_SUBSET_SHA256,
        "inverters": catalog.INVERTER_SUBSET_SHA256,
    }


def test_partial_cache_and_failed_second_download_use_complete_subset(
    isolated_storage: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    use_transport_fixture(monkeypatch, isolated_storage)
    catalog.CACHE_DIR.mkdir()
    (catalog.CACHE_DIR / CACHE_FILES["modules"]).write_bytes(isolated_storage["modules"])
    calls: list[str] = []

    def download(url: str) -> bytes:
        calls.append(url)
        raise requests.ConnectionError("inverter source disconnected")

    monkeypatch.setattr(catalog, "_download_bytes", download)
    _, _, meta = catalog.load_cec_equipment()
    assert calls == [catalog.INVERTER_URL]
    assert meta["source_used"] == "subset"
    assert meta["sha256"] == {
        "modules": catalog.MODULE_SUBSET_SHA256,
        "inverters": catalog.INVERTER_SUBSET_SHA256,
    }


def test_non_network_error_does_not_activate_subset(monkeypatch: pytest.MonkeyPatch) -> None:
    def download(url: str) -> bytes:
        raise ValueError("unexpected downloader bug")

    monkeypatch.setattr(catalog, "_download_bytes", download)
    with pytest.raises(ValueError, match="unexpected downloader bug"):
        catalog.load_cec_equipment()
