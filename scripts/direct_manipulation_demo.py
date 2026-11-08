"""Exercise the 3D gesture HTTP contract on a fresh, explicitly synthetic demo.

Create the six-version input with manual_modules_demo.py first. This script then
verifies move/undo and rotate/undo through the live local server, including new
analysis completion records. Real pointer interaction is tested separately.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from guangzhu.config import API_ORIGIN, PROJECTS_DIR, ROOT
from guangzhu.models import project_id


def hashes(base):
    return {path.relative_to(base).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in base.rglob('*.json') if path.is_file()}


def geometry(design):
    return {row['id']: {key: row[key] for key in ('center', 'corners', 'tilt', 'azimuth', 'orientation')}
            for row in design['modules']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default='direct-manipulation-demo')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/direct-manipulation/live-roundtrip.json')
    args = parser.parse_args()
    identifier = project_id(args.project)
    base = PROJECTS_DIR / identifier
    if args.output.exists():
        parser.error('证据文件已存在；请保留原记录并指定新输出。')
    project = json.loads((base / 'project.json').read_text(encoding='utf-8'))
    if '合成尺寸' not in project.get('name', '') or '示意' not in project.get('requirements', {}).get('text', ''):
        parser.error('只接受由 manual_modules_demo.py 新生成的合成演示项目。')
    if sorted(p.name for p in (base / 'designs').glob('v*.json')) != [f'v{n}.json' for n in range(1, 7)]:
        parser.error('演示必须停在 v6；拒绝覆盖或重复执行已有版本链。')
    events = []

    def request(path, payload=None):
        started = time.perf_counter()
        req = Request(API_ORIGIN + '/api/' + path, data=None if payload is None else json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json', 'Origin': API_ORIGIN})
        with urlopen(req, timeout=180) as response:
            value = json.load(response)
        events.append(dict(path=path, method='GET' if payload is None else 'POST',
                           elapsed_seconds=round(time.perf_counter() - started, 3), request=payload))
        return value

    endpoint = f'projects/{identifier}/'
    original = request(endpoint + 'result?version=6')
    current = original
    original_hashes = hashes(base)
    historical = {key: value for key, value in original_hashes.items() if key.startswith(('designs/', 'analysis/'))}
    locked = {key: geometry(original['design'])[key] for key in original['locked_modules']}
    module = next(row for row in reversed(original['design']['modules']) if row['id'] not in locked)
    snapshots = []
    operations = [('移动未锁组件', [dict(op='move_modules', module_ids=[module['id']], dx_m=.3, dy_m=.4)]),
                  ('撤销移动', [dict(op='undo_last_edit')]),
                  ('旋转未锁组件', [dict(op='rotate_modules', module_ids=[module['id']], angle_deg=45)]),
                  ('撤销旋转', [dict(op='undo_last_edit')])]
    for title, ops in operations:
        payload = dict(version=current['version'], ops=ops, detailed=True,
                       reason='三维手柄 HTTP 契约演示：' + title + '；合成场景')
        before_preview = hashes(base)
        preview = request(endpoint + 'design-edits/preview', payload)
        assert hashes(base) == before_preview, '预览不应改写文件'
        saved = request(endpoint + 'design-edits/apply', payload | dict(fingerprint=preview['fingerprint']))
        assert saved['analysis_complete'], saved
        current = request(endpoint + f"result?version={saved['version']}")
        assert geometry(current['design']) == geometry(preview['design'])
        assert current['evidence']['analysis']['completion_status'] == 'matched'
        assert current['evidence']['analysis']['input_binding'] == 'matched'
        assert {key: geometry(current['design'])[key] for key in locked} == locked
        assert all(hashes(base)[key] == value for key, value in historical.items())
        if title.startswith('撤销'):
            assert geometry(current['design']) == geometry(original['design'])
        snapshots.append(dict(step=title, version=current['version'], impact=preview['impact'],
                              evidence=current['evidence'], diagnostics=current['diagnostics']))
        print(json.dumps(dict(step=title, version=current['version'], completion='matched'), ensure_ascii=False), flush=True)
    report = dict(project_id=identifier, synthetic=True,
                  method='真实本机 HTTP 三维手柄操作契约；真实指针交互另见浏览器测试和截图记录；无模型调用。',
                  source_version=6, final_version=current['version'], snapshots=snapshots, requests=events,
                  historical_files_unchanged=True, checked_historical_files=len(historical),
                  undo_geometry_restored=True, locked_modules_unchanged=sorted(locked),
                  url=API_ORIGIN + f"/#result/{identifier}?version={current['version']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(url=report['url'], output=str(args.output)), ensure_ascii=False))


if __name__ == '__main__':
    main()
