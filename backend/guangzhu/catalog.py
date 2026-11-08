"""Pinned SAM CEC equipment with verified full catalogs and offline subsets."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
import hashlib
import json
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


_CEC_PARAMETERS = ('alpha_sc', 'a_ref', 'I_L_ref', 'I_o_ref', 'R_sh_ref', 'R_s', 'Adjust')


def _iv_point(module, irradiance, temperature):
    params = pvlib.pvsystem.calcparams_cec(irradiance, temperature,
        **{key: _number(module, key) for key in _CEC_PARAMETERS})
    point = pvlib.pvsystem.singlediode(*params, method='lambertw')
    values = {key: float(point[key]) for key in ('p_mp', 'v_mp', 'i_mp', 'v_oc', 'i_sc')}
    if not all(math.isfinite(v) and v > 0 for v in values.values()) or not (
            values['v_mp'] < values['v_oc'] and values['i_mp'] < values['i_sc']):
        raise CatalogDataError('CEC proxy produced a nonphysical illuminated IV curve.')
    return values


def _proxy_module(source, target, source_row):
    """Scale the complete source IV curve; never relabel it as a tested target model.

    V'=s_v V, I'=s_i I preserves the single-diode equation when currents
    (including I0/alpha) scale by s_i, a/beta by s_v, and both resistances by
    s_v/s_i. Matching Pmp and Vmp does not fit Voc, Isc or temperature response.
    """
    positive = ('pmax_w', 'stc_w', 'vmp_v', 'imp_a', 'voc_v', 'isc_a', 'length_m', 'width_m', 'noct_c')
    try:
        values = {key: float(target[key]) for key in positive}
    except (KeyError, TypeError, ValueError) as error:
        raise CatalogDataError('CEC proxy target is missing finite numeric inputs.') from error
    if not all(math.isfinite(v) and v > 0 for v in values.values()) or not (
            values['voc_v'] > values['vmp_v'] and values['isc_a'] > values['imp_a']):
        raise CatalogDataError('CEC proxy target has nonphysical power, voltage, current or geometry.')
    if not math.isclose(values['stc_w'], values['pmax_w'], rel_tol=.01) or not math.isclose(
            values['vmp_v'] * values['imp_a'], values['pmax_w'], rel_tol=.01):
        raise CatalogDataError('CEC proxy target STC power and Vmp*Imp differ by more than the 1% input consistency allowance.')
    if values['pmax_w'] >= 1000 * values['length_m'] * values['width_m']:
        raise CatalogDataError('CEC proxy target STC efficiency must be below 100% of incident solar power.')
    source_stc = _iv_point(source, 1000, 25)
    scale_v = values['vmp_v'] / source_stc['v_mp']
    scale_i = values['pmax_w'] / (values['vmp_v'] * source_stc['i_mp'])
    module = source.copy()
    for key in ('I_L_ref', 'I_o_ref', 'alpha_sc'):
        module[key] = _number(source, key) * scale_i
    for key in ('a_ref', 'beta_oc'):
        module[key] = _number(source, key) * scale_v
    for key in ('R_s', 'R_sh_ref'):
        module[key] = _number(source, key) * scale_v / scale_i
    module['Manufacturer'] = target['manufacturer']
    module['STC'] = values['pmax_w']
    module['A_c'] = values['length_m'] * values['width_m']
    module['T_NOCT'] = values['noct_c']
    module.name = 'proxy__' + target['module_id']
    stc = _iv_point(module, 1000, 25)
    for key, result_key in (('V_mp_ref', 'v_mp'), ('I_mp_ref', 'i_mp'), ('V_oc_ref', 'v_oc'), ('I_sc_ref', 'i_sc')):
        module[key] = stc[result_key]
    if not math.isclose(stc['p_mp'], values['pmax_w'], rel_tol=1e-6) or not math.isclose(stc['v_mp'], values['vmp_v'], rel_tol=1e-6):
        raise CatalogDataError('Final CEC proxy does not reproduce its declared STC power and Vmp.')
    irradiances, temperatures = (100, 200, 600, 1000, 1200), (-20, 25, 75, 85)
    samples = []
    for temperature in temperatures:
        previous = 0.0
        for irradiance in irradiances:
            point = _iv_point(module, irradiance, temperature)
            if point['p_mp'] <= previous:
                raise CatalogDataError('CEC proxy power is not increasing with irradiance.')
            previous = point['p_mp']
            samples.append(dict(irradiance_w_m2=irradiance, cell_temperature_c=temperature, **point))
    cold, hot = _iv_point(module, 1000, 24), _iv_point(module, 1000, 26)
    temperature_coefficients = {}
    for key, field in (('p_mp', 'gamma_pmax_pct_c'), ('v_oc', 'beta_voc_pct_c'), ('i_sc', 'alpha_isc_pct_c')):
        calculated = (hot[key] - cold[key]) / (2 * stc[key]) * 100
        declared = float(target[field])
        if not math.isfinite(declared):
            raise CatalogDataError('CEC proxy target temperature coefficient is not finite.')
        temperature_coefficients[field] = dict(proxy=calculated, catalog_input=declared,
                                               difference_pct_per_c=calculated - declared)
    parameters = {key: _number(module, key) for key in (*_CEC_PARAMETERS, 'STC', 'A_c', 'T_NOCT',
                   'V_mp_ref', 'I_mp_ref', 'V_oc_ref', 'I_sc_ref', 'beta_oc')}
    provenance = dict(status='proxy', target_module_id=target['module_id'], target_model=target['model'],
        target_parameters_status='unverified', manufacturer_certified=False,
        source_module_id=source_row['module_id'], source_module_name=source_row['sam_original_name'],
        source_module_key=source_row['pvlib_key'], method='cec_iv_homothetic_scale_pmp_vmp_v1',
        method_description='完整缩放源CEC的电流、电压和电阻参数，使代理STC功率与工作电压对应目录输入；未拟合目标Voc/Isc/温度曲线',
        scale_current=scale_i, scale_voltage=scale_v, parameters=parameters,
        parameter_sha256=hashlib.sha256(json.dumps(parameters, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        target_input_sha256=hashlib.sha256(json.dumps(target, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        annual_energy_error_pct=None,
        limitation='代理估算；扩展机型的目录输入未逐项核验厂家原始规格书。STC吻合与数值稳定不构成厂家认证或全年精度验证；温度响应继承源模型，未模拟背面增益；年发电误差未知。',
        validation=dict(stc=dict(p_mp_w=stc['p_mp'], v_mp_v=stc['v_mp'], i_mp_a=stc['i_mp'],
            v_oc_v=stc['v_oc'], i_sc_a=stc['i_sc'],
            pmax_error_pct=(stc['p_mp'] / values['pmax_w'] - 1) * 100,
            vmp_error_pct=(stc['v_mp'] / values['vmp_v'] - 1) * 100,
            imp_error_pct=(stc['i_mp'] / values['imp_a'] - 1) * 100,
            voc_error_pct=(stc['v_oc'] / values['voc_v'] - 1) * 100,
            isc_error_pct=(stc['i_sc'] / values['isc_a'] - 1) * 100),
            temperature_coefficients=temperature_coefficients,
            operating_grid=dict(passed=True, sample_count=len(samples), irradiance_w_m2=list(irradiances),
                cell_temperature_c=list(temperatures), checks=['finite_positive', 'vmp_below_voc', 'imp_below_isc', 'power_increases_with_irradiance'],
                samples=samples)))
    return module, provenance


def load_cec_equipment(*, offline: bool = False, module_id=None) -> tuple[pd.Series, pd.Series, dict]:
    """Return pinned CEC Series or an explicitly identified, validated proxy.

    Explicit offline mode uses the committed subsets. Otherwise existing full
    catalogs are verified on every call before any download; only a network
    failure selects the subsets. Integrity or equipment errors always propagate.
    This catalog is an efficiency-model example, not a T06 installation design.
    """
    specs = _specs()
    selected, series, parallel = None, SERIES, PARALLEL
    extended_selected = None
    if module_id and module_id != 'trina-tsm-550de19':
        from .electrical import load_catalog
        base_mods = load_catalog('modules.csv')
        selected = base_mods.get(module_id)
        arrays = {'runergy-hy-wh144p8-550': (19, 7), 'trina-tsm-605neg19rc20': (20, 6), 'jinko-jkm605n-66hl4m-bdv': (20, 6)}
        if selected is None:
            ext_mods = load_catalog('modules.csv', include_extended=True)
            if module_id in ext_mods:
                extended_selected = ext_mods[module_id]
                selected = base_mods.get(extended_selected.get('proxy_source_module_id'))
                if selected is None or any(extended_selected.get(k) != selected[k] for k in ('sam_original_name', 'pvlib_key')):
                    raise CatalogDataError('CEC proxy source ID, original name and key must identify the same pinned module.')
                series, parallel = arrays.get(selected['module_id'], (SERIES, PARALLEL))
        if selected is None or (extended_selected is None and module_id not in arrays):
            raise CatalogDataError('Selected module has no verified CEC reference array.')
        if extended_selected is None:
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
    proxy = None
    if extended_selected is not None:
        module, proxy = _proxy_module(module, extended_selected, selected)
        choices = [(s, p) for s in range(1, 51) for p in range(1, 21)
                   if float(inverter['Mppt_low']) <= s * float(module['V_mp_ref']) <= float(inverter['Mppt_high'])
                   and 1.1 <= s * p * float(module['STC']) / float(inverter['Paco']) <= 1.25]
        if not choices:
            raise CatalogDataError('No eligible efficiency reference array for the final proxy model.')
        series, parallel = min(choices, key=lambda sp: (abs(sp[0] * sp[1] * float(module['STC']) / float(inverter['Paco']) - 1.18),
                                                       abs(sp[0] * float(module['V_mp_ref']) - 680), sp))
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
    if proxy is not None:
        metadata.update(model_status='proxy', model_provenance=proxy,
                        module_name='代理估算：' + extended_selected['model'], module_key=module.name)
    return module, inverter, metadata
