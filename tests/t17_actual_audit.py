"""Read-only verification of the two saved T17 product runs; no model or physics calls."""
import hashlib
import json
from pathlib import Path
import re
import sys

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from agh_export_run import read_events, resolve_results, tool_name
from agh_verify_run import export_approvals, verify


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifacts(run, info):
    for relative, expected in info['artifacts'].items():
        path = run / relative if relative.startswith('report/') else run / info['capture'] / relative
        assert sha(path) == expected, path
    return len(info['artifacts'])


def actual(case, saved):
    run = ROOT / 'runs' / saved['run_id']
    info = load(run / 'run.json')
    capture = run / info['capture']
    review_capture = run / info['review_capture']
    events = read_events(capture / 'ledger.agnes.jsonl')
    reviews = read_events(review_capture / 'ledger.agnes.jsonl')
    assert sha(capture / 'ledger.agnes.jsonl') == saved['native_ledger_sha256']
    assert sha(review_capture / 'ledger.agnes.jsonl') == saved['review_ledger_sha256']
    result = verify(events, reviews=[reviews])
    stored = load(run / 'verification.json')
    assert result == saved['verifier_replay']
    assert result['passed'] and len(result['checks']) == 4 and all(c['passed'] for c in result['checks'])
    assert result['review'] == {k: v for k, v in stored['review'].items() if k != 'associations'}
    assert all(result[k] == stored[k] for k in result if k != 'review')
    rows, unlinked = resolve_results(events)
    assert not unlinked and not result['pending_calls']
    compare = next(r for r in rows if r['name'] == 'gz_compare_options')
    export = next(r for r in rows if r['name'] == 'gz_export')
    assert sum(r['name'] == 'gz_compare_options' for r in rows) == 1
    assert len(compare['value']['options']) == 3
    assert all(o['hard_pass'] is True and not o['violated_requirements'] for o in compare['value']['options'])
    version = saved['selected_version']
    assert version == compare['value']['recommended']['balanced']['version'] == info['export_version']
    assert saved['recommended'] == compare['value']['recommended']
    chain = saved['final_chain']
    analysis = next(r for r in rows if r['call']['seq'] == chain['analyze_call'])
    crosscheck = next(r for r in rows if r['call']['seq'] == chain['crosscheck_call'])
    assert analysis['value']['rules']['hard_failed'] == 0 and analysis['value']['rules']['failed'] == []
    assert analysis['value']['version'] == crosscheck['value']['version'] == export['value']['version'] == version
    assert analysis['result']['seq'] < crosscheck['call']['seq'] < crosscheck['result']['seq'] < export['call']['seq']
    approvals = export_approvals(events, export)
    assert len(approvals) == 1 and approvals[0]['seq'] == chain['approval_seq']
    assert approvals[0]['data']['verdict'] == 'allowed-once'
    project = load(capture / 'project/project.json')
    brief = next(json.loads(raw) for e in events if e['type'] == 'inbox'
                 for item in e['data'].get('items', []) for block in item.get('content', [])
                 for raw in re.findall(r'```json\s*\n(.*?)\n```', block.get('text', ''), re.S)
                 if json.loads(raw).get('brief') == 'guangzhu.brief/1')
    assert brief['requirements'] == saved['original_requirements']
    assert project['requirements'] == saved['saved_requirements']
    assert brief['requirements']['text'] == project['requirements']['text']
    assert all(project['requirements']['structured'][k] == v for k, v in brief['requirements']['structured'].items())
    assert brief['run']['compare'] and brief['run']['export'] and brief['run']['review']['enabled']
    assert brief['run']['prefer'] == 'balanced' and brief['run']['review']['mode'] == 'independent'
    returned = [compare['value']['current'], *compare['value']['options']]
    for candidate, option in zip(returned, saved['options'], strict=True):
        assert all(option[k] == v for k, v in candidate.items())
        design = load(capture / f"project/designs/v{candidate['version']}.json")
        assert len(design['modules']) == option['modules']
        rules = load(capture / f"project/analysis/v{candidate['version']}/rules.json")
        assert rules['hard_failed'] == 0
        assert not any(i['level'] == 'hard' and i['status'] == 'fail' for i in rules['items'])
    if case == 'real12':
        assert all(o['capex_cny'] <= 1800000 for o in returned)
    else:
        assert all(o['dc_kw'] <= 800 for o in returned)
        assert next(r for r in rows if r['call']['seq'] == 150)['call']['data']['args'] == next(
            r for r in rows if r['call']['seq'] == 188)['call']['data']['args']
    review_rows, orphaned = resolve_results(reviews)
    assert not orphaned
    record = next(r for r in review_rows if r['name'] == 'gz_record_review')
    assert record['call']['data']['args'] == saved['independent_review']['args']
    assert record['call']['data']['args']['verdict'] == 'approve'
    findings = record['call']['data']['args']['findings']
    assert findings == [] if case == 'real12' else len(findings) == 4 and all(f['severity'] == 'low' for f in findings)
    names = [tool_name(e) or e['data']['name'] for e in events if e['type'] == 'tool/call']
    assert names.count('skill_read') == 1 and names.count('todo') == (2 if case == 'real12' else 0)
    pdf = PdfReader(ROOT / saved['pdf']['path'])
    text = pdf.pages[2].extract_text()
    assert text == saved['pdf']['page3_text'] and len(pdf.pages) == saved['pdf']['pages']
    assert text.count('满足') == 5 and '选定' in text
    assert sha(ROOT / saved['pdf']['page3_png']) == saved['pdf']['png_sha256']
    assert saved['pdf']['visual_pass'] is True
    assert info['report'] == saved['report'] and info['report']['regenerated'] is False
    return events, reviews, artifacts(run, info)


def main():
    evidence = load(ROOT / 'reports/assets/T17/actual-evidence.json')
    ledgers, counts = [], {}
    for case in ('real12', 'real04'):
        events, reviews, counts[case] = actual(case, evidence[case])
        ledgers.extend([events, reviews])
    failed = evidence['failed_first_attempt']
    run = ROOT / 'runs' / failed['run_id']
    info = load(run / 'run.json')
    events = read_events(run / info['capture'] / 'ledger.agnes.jsonl')
    assert sha(run / info['capture'] / 'ledger.agnes.jsonl') == failed['native_ledger_sha256']
    assert load(run / 'verification.json') == failed['verifier'] and not failed['verifier']['passed']
    counts['failed'] = artifacts(run, info)
    ledgers.append(events)
    effects = {}
    for ledger in ledgers:
        for event in ledger:
            if event['type'] == 'cost/ledger' and not event['data'].get('adjustment'):
                cost = event['data']
                assert cost['effectId'] not in effects
                effects[cost['effectId']] = cost
    saved = {c['effectId']: {k: v for k, v in c.items() if k != 'scope'} for c in evidence['costs']['all_unique_effects']}
    assert effects == saved and len(effects) == evidence['costs']['unique_effect_count'] == 58
    usd_micros = sum(c.get('billing', {}).get('usdMicros', 0) for c in effects.values())
    assert usd_micros == evidence['costs']['usd_micros'] == 143554
    identity = evidence['code_identity']
    assert sha(ROOT / 'reports/assets/T17/final-preflight.json') == identity['preflight_sha256']
    assert identity['registered']['commit'] == '3990ca47720e09081e5d4fd8dac6bfc69c1f90b6'
    assert identity['registered']['process_id'] == 34372
    print(json.dumps(dict(passed=True, artifacts=counts, unique_effects=len(effects), usd_micros=usd_micros)))


if __name__ == '__main__':
    main()
