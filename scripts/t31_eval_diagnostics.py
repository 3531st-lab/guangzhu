"""Replay unchanged historical evaluation witnesses and record current wind consequences."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from guangzhu import analysis, layout, project as storage
from guangzhu.models import Project, Requirements, StructuredRequirements


def main():
    destination = Path(sys.argv[1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    storage.PROJECTS_DIR = Path(os.environ['GUANGZHU_DATA_HOME']) / 't31-eval-projects'
    cases_file = ROOT / 'eval/cases.json'
    results = {}
    for case in json.loads(cases_file.read_text(encoding='utf-8')):
        source = ROOT / 'data/roofs' / case['template'] / 'project.json'
        record = Project.model_validate_json(source.read_text(encoding='utf-8'))
        requirement = copy.deepcopy(case['structured'])
        relaxed = not case['feasible']
        witness = case['relaxation']['witness'] if relaxed else case['witness']
        if relaxed:
            section, key = case['relaxation']['field'].split('.')
            if section == 'roof':
                setattr(record.roof, key, case['relaxation']['to'])
            else:
                requirement[key] = case['relaxation']['to']
        record.requirements = Requirements(text=case['text'], structured=StructuredRequirements.model_validate(requirement))
        record.economics = record.economics.model_copy(update=case['economics'])
        design = layout.generate_layout(record, witness['params'])
        by_id = {m.id: m for m in design.modules}
        design.modules = [by_id[mid] for mid in witness['kept_module_ids']]
        design.modules_per_string = witness['modules_per_string']
        design.statistics.update(module_count=len(design.modules), dc_kw=len(design.modules) * .55,
                                 rows=len({m.row for m in design.modules}))
        storage.save(record)
        storage.save_design(record.id, design)
        summary = analysis.analyze(record.id, 1, offline=True)
        folder = storage._path(record.id, 'analysis/v1')
        checked = json.loads((folder / 'rules.json').read_text(encoding='utf-8'))
        load = json.loads((folder / 'structure.json').read_text(encoding='utf-8'))
        failed = [r['id'] for r in checked['items'] if r['level'] == 'hard' and r['status'] == 'fail']
        results[case['id']] = dict(historical_label=case['feasible'], historical_result=witness['result'],
            original_template_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), relaxation_applied=relaxed,
            actual_design_pass=not failed, failed=failed, summary=summary, zones=load['wind']['zones'],
            load={key: load[key] for key in ('added_kn_m2', 'average_kn_m2', 'capacity_kn_m2', 'mass_kg', 'ballast_mass_kg')},
            rules=checked['items'], conclusion='只评价此原见证，不由一次失败推断所有方案不可行')
        print(case['id'], failed, load['added_kn_m2'], summary['economics']['capex_cny'], flush=True)
    payload = dict(status='current_witness_diagnostics_not_global_feasibility',
                   cases_sha256=hashlib.sha256(cases_file.read_bytes()).hexdigest(), witnesses=results)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
