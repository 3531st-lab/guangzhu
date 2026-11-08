"""Regression cases for catalog-bound conductors, brands and declared CEC proxies."""
import copy
import math

import pytest
import pvlib
import requests

from guangzhu import brief, cables, catalog, costs, electrical
from guangzhu.models import Equipment, GzError
from test_electrical import project, design


@pytest.fixture(autouse=True)
def no_public_network(monkeypatch):
    monkeypatch.setattr(requests.Session, 'request', lambda *a, **k: pytest.fail('offline regression'))


def chosen(kind, family, distance=100, current=220, voltage=400, required=220):
    option = design(0)
    option.statistics[kind + '_cable_family'] = family
    return cables.conductor(kind, distance, current, voltage, required, option)


def test_aluminum_selection_uses_own_resistivity_ampacity_and_available_sections():
    row = chosen('ac', 'YJLH22')
    assert row['cable_id'] == 'YJLH22-4x185'
    assert row['ampacity_a'] == 270
    rho = .0283 * (1 + .00403 * (90 - 20))
    assert row['drop_pct'] == pytest.approx(math.sqrt(3) * rho * 100 * 220 / (185 * 400) * 100)
    assert row['rho'] == pytest.approx(rho)
    assert row['material'] == 'aluminum' and row['feasible']
    assert row['unit_price_cny_m'] == 138


def test_requested_cable_family_never_invents_an_unlisted_size():
    row = chosen('ac', 'YJLH22', distance=150)
    listed = electrical.load_catalog('cables.csv')
    assert row['cable_id'] in listed
    assert not row['feasible']
    assert row['section_mm2'] == 185
    assert row['drop_pct'] > 2


def test_pv_cable_family_uses_its_own_ampacity():
    row = chosen('dc', 'H1Z2Z2-K', distance=1, current=44, voltage=800, required=45)
    assert row['cable_id'] == 'H1Z2Z2-K-1x4'
    assert row['ampacity_a'] == 46 and row['feasible']


def test_unrecognized_cable_family_is_rejected_instead_of_relabelled():
    with pytest.raises(GzError, match='电缆'):
        chosen('ac', 'not-a-real-family')


def test_cable_voltage_rating_is_part_of_feasibility():
    row = chosen('dc', 'PV1-F', distance=1, current=10, voltage=1600, required=10)
    assert not row['feasible']
    assert not row['voltage_ok']


def test_electrical_summary_and_quote_use_the_same_aluminum_row(project):
    option = design(200, 20)
    option.statistics['ac_cable_family'] = 'YJLH22'
    project.roof.inverter_positions = [(0, 0)]
    project.roof.grid_point = (40, 0)
    electric = electrical.calculate(project, option, offline=True)
    summary = next(r for r in electric['cables']['summary'] if r['kind'] == 'ac')
    source = electrical.load_catalog('cables.csv')[summary['cable_id']]
    assert summary['material'] == source['material'] == 'aluminum'
    assert summary['unit_price_cny_m'] == source['unit_price_cny_m']
    project.economics.capex_cny_per_w = None
    quote = costs.itemized(project, 110, option, electric, {})
    price = next(r for r in quote['items'] if r['key'] == 'ac_cable')
    assert price['cable_id'] == summary['cable_id']
    assert price['name'] == source['model']
    assert price['unit_price_cny'] == source['unit_price_cny_m']
    assert price['subtotal_cny'] == pytest.approx(summary['length_m'] * source['unit_price_cny_m'])
    assert price['source']['状态'] == '示意'


def test_all_consumed_cable_prices_participate_in_quote_fingerprint(project):
    project.economics.capex_cny_per_w = None
    option = design(20)
    first = dict(chosen('dc', 'PV1-F', 1, 10, 800, 10), kind='dc', length_m=100)
    second = dict(chosen('dc', 'H1Z2Z2-K', 1, 10, 800, 10), kind='dc', length_m=50)
    electric = dict(per_inverter=[], cables=dict(summary=[first, second]))
    before = costs.itemized(project, 11, option, electric, {})
    changed = copy.deepcopy(electric)
    changed['cables']['summary'][0]['unit_price_cny_m'] += 1
    after = costs.itemized(project, 11, option, changed, {})
    assert after['source_fingerprint'] != before['source_fingerprint']
    assert after['quoted_capex_cny'] - before['quoted_capex_cny'] == pytest.approx(100)


@pytest.mark.parametrize('alias', ['Ginlong', 'Ginlong Solis', 'Solis', 'ginlong', '锦浪'])
def test_ginlong_aliases_normalize_before_project_selection(alias):
    selected = Equipment(module_id='trina-tsm-550de19', inverter_brand=alias)
    assert selected.inverter_brand == 'Ginlong'
    values = dict(inverter_brand=alias, inverter_id='solis-s5-gc60k')
    brief.check_equipment(values)
    assert values['inverter_brand'] == 'Ginlong'


def test_ginlong_catalog_brief_and_electrical_selection_agree(project):
    for identifier in ['solis-s5-gc60k', 'solis-s5-gc110k']:
        row = electrical.load_catalog('inverters.csv', include_extended=True)[identifier]
        assert row['manufacturer'] == 'Ginlong'
        assert row['manufacturer_display'] == 'Ginlong Solis'
        brief.check_equipment(dict(inverter_brand='Ginlong', inverter_id=identifier))
        project.equipment.inverter_brand = 'Ginlong'
        project.equipment.inverter_id = identifier
        result = electrical.calculate(project, design(200, 20), offline=True)
        assert result['inverter_id'] == identifier


EXTENDED_IDS = [
    'longi-himo9-660m', 'longi-himo7-620m', 'trina-vertex-n-720m',
    'jinko-tiger-neo-635m', 'ja-deepblue4-610m', 'tongwei-tnc-590m',
    'canadian-hiku7-700m', 'longi-bipv-ancient-450m',
]
CEC_KEYS = ('alpha_sc', 'a_ref', 'I_L_ref', 'I_o_ref', 'R_sh_ref', 'R_s', 'Adjust')


@pytest.mark.parametrize('identifier', EXTENDED_IDS)
def test_extended_model_is_a_traceable_proxy_with_final_stc_validation(identifier):
    module, _, meta = catalog.load_cec_equipment(offline=True, module_id=identifier)
    row = electrical.load_catalog('modules.csv', include_extended=True)[identifier]
    assert meta['model_status'] == 'proxy'
    provenance = meta['model_provenance']
    assert provenance['source_module_name'] == row['sam_original_name']
    assert provenance['source_module_key'] == row['pvlib_key']
    assert provenance['target_module_id'] == identifier
    assert provenance['target_parameters_status'] == 'unverified'
    assert provenance['manufacturer_certified'] is False
    assert provenance['annual_energy_error_pct'] is None
    assert len(provenance['parameter_sha256']) == 64
    assert meta['module_key'] == module.name and module.name.startswith('proxy__')
    actual = pvlib.pvsystem.singlediode(*pvlib.pvsystem.calcparams_cec(
        1000, 25, **{key: float(module[key]) for key in CEC_KEYS}), method='lambertw')
    assert actual['p_mp'] == pytest.approx(row['pmax_w'], rel=1e-6)
    assert actual['v_mp'] == pytest.approx(row['vmp_v'], rel=1e-6)
    validation = provenance['validation']
    assert validation['stc']['p_mp_w'] == pytest.approx(actual['p_mp'])
    assert validation['stc']['voc_error_pct'] == pytest.approx((actual['v_oc'] / row['voc_v'] - 1) * 100)
    assert validation['operating_grid']['passed']
    assert validation['operating_grid']['sample_count'] >= 12


def test_extension_parameter_claims_are_marked_unverified_in_installation_catalog():
    row = electrical.load_catalog('modules.csv', include_extended=True)['longi-himo9-660m']
    assert row['model_status'] == 'proxy'
    assert row['parameter_status'] == 'unverified'
    assert row['proxy_source_module_id'] == 'trina-tsm-605neg19rc20'


def test_proxy_rejects_nonphysical_target_inputs(monkeypatch):
    original = electrical.load_catalog
    def corrupt(filename, **kwargs):
        rows = original(filename, **kwargs)
        if filename == 'modules.csv' and kwargs.get('include_extended'):
            rows['longi-himo9-660m']['vmp_v'] = -1
        return rows
    monkeypatch.setattr(electrical, 'load_catalog', corrupt)
    with pytest.raises(catalog.CatalogDataError):
        catalog.load_cec_equipment(offline=True, module_id='longi-himo9-660m')


def test_proxy_rejects_stc_power_greater_than_incident_solar_power(monkeypatch):
    original = electrical.load_catalog
    def corrupt(filename, **kwargs):
        rows = original(filename, **kwargs)
        if filename == 'modules.csv' and kwargs.get('include_extended'):
            row = rows['longi-himo9-660m']
            row.update(stc_w=10000, pmax_w=10000, imp_a=10000 / row['vmp_v'], isc_a=11000 / row['vmp_v'])
        return rows
    monkeypatch.setattr(electrical, 'load_catalog', corrupt)
    with pytest.raises(catalog.CatalogDataError, match='STC efficiency'):
        catalog.load_cec_equipment(offline=True, module_id='longi-himo9-660m')


def test_electrical_output_preserves_unverified_extended_specification_status(project):
    project.equipment.module_id = 'longi-himo9-660m'
    project.equipment.inverter_id = 'solis-s5-gc60k'
    project.equipment.inverter_brand = 'Ginlong'
    result = electrical.calculate(project, design(200), offline=True)
    assert result['metadata']['module_parameter_status'] == 'unverified'
    assert result['metadata']['inverter_parameter_status']['solis-s5-gc60k'] == 'unverified'
    assert result['metadata']['equipment_limitations']


@pytest.mark.parametrize('identifier', EXTENDED_IDS)
def test_extended_proxy_completes_real_weather_year_without_losing_provenance(identifier):
    from guangzhu import weather, yieldsim
    hourly, _ = weather.load_nasa_hourly(31.81, 119.97, 2023, offline=True)
    equipment = catalog.load_cec_equipment(offline=True, module_id=identifier)
    result = yieldsim.simulate_pvlib_detailed(hourly, 31.81, 119.97, equipment=equipment)
    assert len(result['hourly']['kwh']) == 8760
    assert all(math.isfinite(v) and v >= 0 for v in result['hourly']['kwh'])
    assert sum(result['monthly_kwh']) == pytest.approx(sum(result['hourly']['kwh']))
    assert result['annual_kwh'] > 0
    provenance = result['metadata']['catalog']['model_provenance']
    assert provenance['target_module_id'] == identifier
    assert provenance['annual_energy_error_pct'] is None
