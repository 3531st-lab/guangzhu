"""Pinned SAM CEC equipment with verified full catalogs and offline subsets."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
import hashlib
import math
from pathlib import Path
import uuid
import warnings

import pandas as pd
import pvlib
import requests

from .config import DATA_DIR


CACHE_DIR = DATA_DIR / "cache" / "catalog"
CATALOG_DIR = DATA_DIR / "catalog"
SAM_COMMIT = "cba319ded1c32a7f5b3ac76545a29e1f7181d238"
_BASE_URL = f"https://raw.githubusercontent.com/NREL/SAM/{SAM_COMMIT}/deploy/libraries/"
MODULE_URL = _BASE_URL + "CEC%20Modules.csv"
INVERTER_URL = _BASE_URL + "CEC%20Inverters.csv"
MODULE_SHA256 = "a28cf8956a839ed98bb941809b439e4907f5b4c237bd9299bc123fb502c29aff"
INVERTER_SHA256 = "0c1b2188415dad6928f91f1a4c9a820dadc80962549f903d57d9282ba3753760"
MODULE_SUBSET_SHA256 = "b009b663ac512f276196bb69a51d739836327c81ace9c9313a19c98693cd8796"
INVERTER_SUBSET_SHA256 = "20d16c82e572e585183d980a3dbc7ee0661be1f9425902f961c6a52adfdd8eee"
MODULE_NAME = "Trina Solar TSM-550DE19"
MODULE_KEY = "Trina_Solar_TSM_550DE19"
INVERTER_NAME = "Sungrow: SG60CX-US {480V}"
INVERTER_KEY = "Sungrow__SG60CX_US_{480V}"
SERIES, PARALLEL = 22, 6


class CatalogDataError(RuntimeError):
    """The pinned catalog or selected equipment cannot be used."""


class CatalogIntegrityError(CatalogDataError):
    """Catalog bytes differ from the pinned SHA-256; never fall back."""


@dataclass(frozen=True)
class _CatalogSpec:
    kind: str
    filename: str
    url: str
    sha256: str
    subset_filename: str
    subset_sha256: str
    original_name: str
    key: str


def _specs() -> tuple[_CatalogSpec, _CatalogSpec]:
    return (
        _CatalogSpec("modules", "CEC Modules.csv", MODULE_URL, MODULE_SHA256,
                     "cec_modules_subset.csv", MODULE_SUBSET_SHA256, MODULE_NAME, MODULE_KEY),
        _CatalogSpec("inverters", "CEC Inverters.csv", INVERTER_URL, INVERTER_SHA256,
                     "cec_inverters_subset.csv", INVERTER_SUBSET_SHA256, INVERTER_NAME, INVERTER_KEY),
    )


def _check_bytes(contents: bytes, expected: str, label: str) -> None:
    actual = hashlib.sha256(contents).hexdigest()
    if actual != expected:
        raise CatalogIntegrityError(f"SHA-256 mismatch for {label}: expected {expected}, got {actual}.")


def _verify_file(path: Path, expected: str) -> None:
    try:
        _check_bytes(path.read_bytes(), expected, str(path))
    except OSError as error:
        raise CatalogDataError(f"Cannot read catalog {path}.") from error


def _download_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=(3, 15))
    response.raise_for_status()
    return response.content


def _write_cache(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        temporary.write_bytes(contents)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_selected(path: Path, original_name: str, key: str) -> pd.Series:
    # retrieve_sam skips the two SAM metadata rows after the CSV column header.
    # Count original names as well: distinct raw names can normalize to one key.
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream)
            header, units, mapping = next(reader), next(reader), next(reader)
            if header[0] != "Name" or units[0] != "Units" or mapping[0] != "[0]":
                raise CatalogDataError(f"SAM headers are missing in {path}.")
            name_count = sum(bool(row) and row[0] == original_name for row in reader)
        if name_count != 1:
            raise CatalogDataError(f"Original name {original_name!r} must be unique; found {name_count}.")
        with warnings.catch_warnings():
            # The pinned full module library contains unrelated duplicate names;
            # the chosen normalized key is explicitly checked below.
            warnings.filterwarnings("ignore", message=".*duplicate.*", category=UserWarning)
            table = pvlib.pvsystem.retrieve_sam(path=str(path))
        key_count = int((table.columns == key).sum())
        if key_count != 1:
            raise CatalogDataError(f"pvlib key {key!r} must be unique; found {key_count}.")
        return table[key].copy()
    except (OSError, StopIteration, csv.Error, IndexError, ValueError) as error:
        raise CatalogDataError(f"Cannot parse pinned SAM catalog {path}.") from error


def _number(equipment: pd.Series, key: str) -> float:
    try:
        value = float(equipment[key])
    except (KeyError, TypeError, ValueError) as error:
        raise CatalogDataError(f"Selected equipment has no numeric {key}.") from error
    if not math.isfinite(value):
        raise CatalogDataError(f"Selected equipment has non-finite {key}.")
    return value


def _validate_equipment(module: pd.Series, inverter: pd.Series, series=SERIES, parallel=PARALLEL, selected=None) -> None:
    manufacturer = selected['manufacturer'] if selected else 'Trina Solar'
    if module.get("Manufacturer") != manufacturer or module.get("Technology") != "Mono-c-Si":
        raise CatalogDataError("Selected module manufacturer or monocrystalline technology does not match the catalogue.")
    bifacial = int(selected is not None and float(selected['stc_w']) == 605)
    if _number(module, "Bifacial") != bifacial or not 540 <= _number(module, "STC") <= 630:
        raise CatalogDataError("Selected module bifacial flag or 540–630 W STC rating does not match the supported catalogue.")
    for key in ("A_c", "N_s", "I_sc_ref", "V_oc_ref", "I_mp_ref", "V_mp_ref", "alpha_sc",
                "beta_oc", "T_NOCT", "a_ref", "I_L_ref", "I_o_ref", "R_s", "R_sh_ref", "Adjust"):
        _number(module, key)
    for key in ("Pso", "Paco", "Pdco", "Vdco", "C0", "C1", "C2", "C3", "Pnt",
                "Mppt_low", "Mppt_high"):
        _number(inverter, key)
    paco = _number(inverter, "Paco")
    if not 40000 <= paco <= 120000 or inverter.get("CEC_hybrid") != "N":
        raise CatalogDataError("Selected Sungrow string inverter must be 40–120 kW, not a hybrid.")
    ratio = series * parallel * _number(module, "STC") / paco
    voltage = series * _number(module, "V_mp_ref")
    if not 1.1 <= ratio <= 1.25:
        raise CatalogDataError(f"DC/AC ratio {ratio} is outside 1.1–1.25.")
    if not _number(inverter, "Mppt_low") <= voltage <= _number(inverter, "Mppt_high"):
        raise CatalogDataError(f"STC string Vmp {voltage} V is outside the CEC MPPT range.")


def load_cec_equipment(*, offline: bool = False, module_id=None) -> tuple[pd.Series, pd.Series, dict]:
    """Return unchanged pvlib CEC Series plus the fixed T03 array provenance.

    Explicit offline mode uses the committed subsets. Otherwise existing full
    catalogs are verified on every call before any download; only a network
    failure selects the subsets. Integrity or equipment errors always propagate.
    This catalog is an efficiency-model example, not a T06 installation design.
    """
    specs = _specs()
    selected, series, parallel = None, SERIES, PARALLEL
    if module_id and module_id != 'trina-tsm-550de19':
        from .electrical import load_catalog
        selected = load_catalog('modules.csv').get(module_id)
        arrays = {'runergy-hy-wh144p8-550': (19, 7), 'trina-tsm-605neg19rc20': (20, 6), 'jinko-jkm605n-66hl4m-bdv': (20, 6)}
        if selected is None or module_id not in arrays:
            raise CatalogDataError('Selected module has no verified CEC reference array.')
        series, parallel = arrays[module_id]
        specs = (replace(specs[0], original_name=selected['sam_original_name'], key=selected['pvlib_key']), specs[1])
    paths = [Path(CACHE_DIR) / spec.filename for spec in specs]
    source_used, fallback_reason = "cache", None
    if offline:
        source_used = "subset"
    else:
        # Check both existing files first, so a later network failure cannot hide
        # a corrupt cached file and silently select a subset.
        for spec, path in zip(specs, paths):
            if path.exists():
                _verify_file(path, spec.sha256)
        for spec, path in zip(specs, paths):
            if path.exists():
                continue
            try:
                contents = _download_bytes(spec.url)
            except requests.RequestException as error:
                source_used = "subset"
                fallback_reason = f"{type(error).__name__}: {error}"
                break
            _check_bytes(contents, spec.sha256, spec.url)
            _write_cache(path, contents)
            source_used = "download"
    if source_used == "subset":
        paths = [Path(CATALOG_DIR) / spec.subset_filename for spec in specs]
    for spec, path in zip(specs, paths):
        _verify_file(path, spec.subset_sha256 if source_used == "subset" else spec.sha256)
    module, inverter = (
        _read_selected(path, spec.original_name, spec.key) for spec, path in zip(specs, paths)
    )
    _validate_equipment(module, inverter, series, parallel, selected)
    dc_capacity_kw = series * parallel * float(module["STC"]) / 1000
    metadata = {
        "sam_commit": SAM_COMMIT, "source_used": source_used,
        "series": series, "parallel": parallel, "module_count": series * parallel,
        "dc_capacity_kw": dc_capacity_kw,
        "dc_ac_ratio": dc_capacity_kw * 1000 / float(inverter["Paco"]),
        "stc_string_vmp_v": series * float(module["V_mp_ref"]),
        "stc_string_voc_v": series * float(module["V_oc_ref"]),
        "module_name": specs[0].original_name, "module_key": specs[0].key,
        "inverter_name": INVERTER_NAME, "inverter_key": INVERTER_KEY,
        "urls": {spec.kind: spec.url for spec in specs},
        "fullfile_sha256": {spec.kind: spec.sha256 for spec in specs},
        "sha256": {spec.kind: spec.subset_sha256 if source_used == "subset" else spec.sha256 for spec in specs},
        "files": {spec.kind: str(path) for spec, path in zip(specs, paths)},
        "inverter_application": "US 480 V / 60 Hz efficiency model only; T06 electrical design remains separate",
    }
    if fallback_reason is not None:
        metadata["fallback_reason"] = fallback_reason
    return module, inverter, metadata
