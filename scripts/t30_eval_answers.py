"""Recompute only T30 economics of the frozen 24 original offline witnesses."""
import argparse
import copy
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from guangzhu import analysis, economics, layout, project as storage, weather, yieldsim
from guangzhu.models import Project, Requirements, StructuredRequirements


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def grid_reference(case, grid):
    instance = Project.model_validate_json((ROOT / 'data/roofs' / case['template'] / 'project.json').read_text(encoding='utf-8'))
    instance.economics = instance.economics.model_copy(update=case['economics'])
    if instance.economics.capex_cny_per_w is None:
        instance.economics.capex_cny_per_w = 2.59
    data, _ = weather.load_nasa_hourly(instance.site.lat, instance.site.lon, 2023, offline=True)
    loss = economics.load_assumptions()['design_system_loss_pct']['value']
    values = []
    for tilt, azimuth in itertools.product(grid['tilt_deg'], grid['azimuth_deg']):
        generated = yieldsim.simulate_pvlib_detailed(data, instance.site.lat, instance.site.lon,
                                                   tilt=tilt, azimuth=azimuth, loss_percent=loss, offline=True)
        total = generated['specific_yield_kwh_kwp']
        energy = dict(p50=total, low=total, high=total, hourly=generated['hourly'])
        value = economics.calculate(instance, 1, energy, sensitivity=False)['payback_years']
        values.append(value if value is not None else float('inf'))
    return min(values)


def recompute(cases):
    changes = []
    for case in cases:
        instance = Project.model_validate_json((ROOT / 'data/roofs' / case['template'] / 'project.json').read_text(encoding='utf-8'))
        values = copy.deepcopy(case['structured'])
        witness = case['witness'] if case['feasible'] else case['relaxation']['witness']
        if not case['feasible']:
            section, field = case['relaxation']['field'].split('.')
            if section == 'roof':
                setattr(instance.roof, field, case['relaxation']['to'])
            else:
                values[field] = case['relaxation']['to']
        instance.requirements = Requirements(text=case['text'], structured=StructuredRequirements.model_validate(values))
        instance.economics = instance.economics.model_copy(update=case['economics'])
        design = layout.generate_layout(instance, witness['params'])
        indexed = {m.id: m for m in design.modules}
        design.modules = [indexed[mid] for mid in witness['kept_module_ids']]
        design.modules_per_string = witness['modules_per_string']
        design.statistics.update(module_count=len(design.modules), dc_kw=len(design.modules) * .55,
                                 rows=len({m.row for m in design.modules}))
        storage.save(instance)
        storage.save_design(instance.id, design)
        summary = analysis.analyze(instance.id, 1, offline=True)
        rules = json.loads(storage._path(instance.id, 'analysis/v1/rules.json').read_text(encoding='utf-8'))
        cash = json.loads(storage._path(instance.id, 'analysis/v1/economics.json').read_text(encoding='utf-8'))
        failed = [r['id'] for r in rules['items'] if r['level'] == 'hard' and r['status'] == 'fail']
        original = copy.deepcopy(witness['result'])
        witness['result'].update(capex_cny=summary['economics']['capex_cny'], payback_years=summary['economics']['payback_years'])
        changes.append(dict(id=case['id'], relaxed=not case['feasible'], before=original, after=witness['result'],
                            current_hard_failed=failed, weighted_price=cash['tariff']['weighted_price_cny_kwh'],
                            reason='原题和几何不变；实际工程分项、426分时、运维细项和绿证重算。'))
        print(case['id'], failed, summary['economics']['payback_years'], flush=True)
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    storage.PROJECTS_DIR = args.work / 'projects'
    args.output.mkdir(parents=True, exist_ok=True)
    cases = json.loads(args.before.read_text(encoding='utf-8'))
    changes = recompute(cases)
    write(args.output / 'eval-answer-changes.json', changes)
    write(args.output / 'cases-proposed.json', cases)


if __name__ == '__main__':
    main()
