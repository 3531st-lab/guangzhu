"""Reproduce manual placement, protected empty space, real impact and append-only undo."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from fastapi.testclient import TestClient

from guangzhu import api, project as storage
from guangzhu.config import API_ORIGIN, DATA_DIR, PROJECTS_DIR, ROOT
from guangzhu.models import Design, LayoutParams, Project, project_id


def digest(value):
    return hashlib.sha256(value).hexdigest()


def geometry(design):
    return [module.model_dump(mode='json') for module in design.modules]


def geometry_hash(design):
    return digest(json.dumps(geometry(design), sort_keys=True, separators=(',', ':')).encode())


def example(identifier):
    values = json.loads((DATA_DIR / 'demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    values.update(id=identifier, name='手动组件与区域锁示例（合成尺寸）', designs=[])
    values['requirements'] = dict(text='手动补放、区域锁、移动、旋转与撤销演示；尺寸和工程参数均为示意。', structured={})
    values['roof'] = dict(type='flat', outline=[[0, 0], [20, 0], [20, 14], [0, 14]],
                          height_m=9, parapet_height_m=0, load_capacity_kn_m2=2, load_verified=False,
                          parapet_segments=[dict(edge_index=0, start_ratio=0, end_ratio=.4, height_m=.8),
                                            dict(edge_index=1, start_ratio=.3, end_ratio=1, height_m=1.2)],
                          obstacles=[dict(id='hvac-demo', label='设备箱（合成尺寸）', kind='prism',
                                          footprint=[[11, 2], [14, 2], [14, 4], [11, 4]], height_m=2.8)],
                          keepouts=[])
    return Project.model_validate(values)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default='manual-modules-demo', help='New project ID; existing projects are never overwritten')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/manual-modules/demo.json')
    args = parser.parse_args()
    identifier = project_id(args.project)
    base = PROJECTS_DIR / identifier
    if base.exists():
        parser.error('项目编号已存在；请用 --project 指定新编号，避免覆盖。')
    if args.output.exists():
        parser.error('结果文件已存在；请用 --output 指定新文件，保留原有证据。')

    started = time.perf_counter()
    storage.save(example(identifier))
    initial = storage.save_design(identifier, Design(params=LayoutParams(tilt_deg=15),
                                  reason='空白屋顶，等待手动补放', author='user'), offline=True)
    report = dict(project_id=identifier, synthetic=True,
                  basis='20×14m合成平屋顶、6块目录组件、设备箱和分段女儿墙；常州2023年缓存天气。不是实测工程。',
                  method='生产HTTP预览/保存契约，详细预览与保存均运行真实工程链；无模型调用、无手写组件角点。',
                  versions=[], actions=[], proofs={}, project_path=str(base / 'project.json'))
    snapshots = {}

    def check_history():
        for relative, previous in snapshots.items():
            actual = digest((base / relative).read_bytes())
            if actual != previous:
                raise AssertionError(f'旧版文件被改写：{relative}')

    def snapshot(version, step):
        check_history()
        design = storage.load_design(identifier, version)
        paths = [base / f'designs/v{version}.json', *sorted((base / f'analysis/v{version}').glob('*.json'))]
        hashes = {path.relative_to(base).as_posix(): digest(path.read_bytes()) for path in paths}
        snapshots.update(hashes)
        summary_path = base / f'analysis/v{version}/summary.json'
        shading_path = base / f'analysis/v{version}/shading.json'
        summary = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.exists() else None
        shading = json.loads(shading_path.read_text(encoding='utf-8')) if shading_path.exists() else None
        report['versions'].append(dict(version=version, parent_version=design.parent_version, step=step,
            modules=len(design.modules), geometry_sha256=geometry_hash(design), files_sha256=hashes,
            module_positions=[dict(id=m.id, center=m.center, tilt_deg=m.tilt, azimuth_deg=m.azimuth) for m in design.modules],
            metrics=summary, shading=shading and dict(summary=shading['summary'], modules=shading['modules'],
                                                     metadata=shading['metadata'])))
        return design

    snapshot(initial.version, '空白起点；无组件，未计算发电')
    client = TestClient(api.app, base_url=API_ORIGIN, headers={'origin': API_ORIGIN})

    def edit(source, ops, reason, detailed=False):
        before_version = storage.next_version(identifier)
        payload = dict(version=source.version, ops=ops, reason=reason, detailed=detailed)
        response = client.post(f'/api/projects/{identifier}/design-edits/preview', json=payload)
        if response.status_code != 200:
            raise AssertionError(f'预览失败：{response.status_code} {response.text}')
        preview = response.json()
        assert storage.next_version(identifier) == before_version, '预览不应产生版本'
        assert not (base / f'analysis/v{before_version}').exists(), '详细预览不应写入分析目录'
        check_history()
        if detailed:
            assert preview['impact']['available'], preview['impact']
        # The candidate was reviewed above; commit that exact fingerprint and calculate the saved version.
        committed = client.post(f'/api/projects/{identifier}/design-edits/apply',
                                json=payload | dict(detailed=True, fingerprint=preview['fingerprint']))
        if committed.status_code != 200:
            raise AssertionError(f'保存失败：{committed.status_code} {committed.text}')
        result = committed.json()
        assert result['analysis_complete'], result
        saved = snapshot(result['version'], reason)
        assert geometry(saved) == preview['design']['modules'], '保存的组件必须等于预览候选'
        report['actions'].append(dict(source_version=source.version, saved_version=saved.version,
            ops=ops, reason=reason, fingerprint=preview['fingerprint'], changes=preview['changes'],
            impact=preview['impact'], analysis_complete=result['analysis_complete']))
        print(json.dumps(dict(step=reason, version=saved.version, modules=len(saved.modules),
                              hard_failed=result['analysis']['rules']['hard_failed']), ensure_ascii=False), flush=True)
        return saved

    placed = edit(initial, [dict(op='add_modules', placements=[dict(center=center) for center in
        [[3, 4], [6, 4], [3, 9], [6, 9], [12.5, 8.5], [17, 9]]])], '补放6块目录组件')
    empty_candidate = dict(op='add_modules', placements=[dict(center=[8.7, 4])])
    available = client.post(f'/api/projects/{identifier}/design-edits/preview', json=dict(
        version=placed.version, ops=[empty_candidate], reason='锁区前核验空白位置可正常补放'))
    assert available.status_code == 200, available.text
    assert len(available.json()['design']['modules']) == len(placed.modules) + 1
    assert storage.next_version(identifier) == placed.version + 1
    check_history()
    locked = edit(placed, [dict(op='lock_region', id='keep-left-and-empty',
                                polygon=[[1.5, 2], [10, 2], [10, 6], [1.5, 6]])], '锁定左侧两块组件及右侧空白')

    before_version = storage.next_version(identifier)
    rejected = client.post(f'/api/projects/{identifier}/design-edits/preview', json=dict(
        version=locked.version, ops=[empty_candidate], reason='验证锁区内未放组件的空白也不可补放'))
    assert rejected.status_code == 422 and rejected.json()['error_code'] == 'DESIGN_LOCK_CONFLICT', rejected.text
    assert storage.next_version(identifier) == before_version
    check_history()
    report['proofs']['locked_empty_space'] = dict(center=[8.7, 4], legal_without_lock=True,
        rejected_status=rejected.status_code, response=rejected.json(), no_version_created=True)

    target = placed.modules[4].id
    moved = edit(locked, [dict(op='move_modules', module_ids=[target], dx_m=0, dy_m=-2)],
                 '将未锁组件移近南侧设备并复算遮挡', detailed=True)
    rotated = edit(moved, [dict(op='rotate_modules', module_ids=[target], angle_deg=37)],
                   '将该组件旋转37度并比较遮挡和发电', detailed=True)
    restored = edit(rotated, [dict(op='undo_last_edit')], '撤销旋转，恢复移动后的组件几何')
    assert geometry(restored) == geometry(moved), '撤销后必须精确恢复父版本组件'
    assert geometry_hash(rotated) != geometry_hash(restored), '旋转必须确实改变几何'
    protected_ids = {placed.modules[0].id, placed.modules[1].id}
    expected = [row for row in geometry(placed) if row['id'] in protected_ids]
    for design in (locked, moved, rotated, restored):
        assert [row for row in geometry(design) if row['id'] in protected_ids] == expected
    check_history()
    report['proofs'].update(preview_does_not_write=True, saved_geometry_matches_preview=True,
        locked_modules_unchanged=sorted(protected_ids), historical_files_unchanged=True,
        checked_historical_files=len(snapshots), undo=dict(version=restored.version,
            restores_version=moved.version, geometry_equal=True, geometry_sha256=geometry_hash(restored)))
    report.update(final_version=restored.version, manual_comparison_version=rotated.version,
                  url=f'{API_ORIGIN}/#result/{identifier}?version={restored.version}',
                  comparison_url=f'{API_ORIGIN}/#result/{identifier}?version={rotated.version}',
                  elapsed_seconds=round(time.perf_counter() - started, 3))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(project_id=identifier, final_version=restored.version,
                          result_file=str(args.output), url=report['url'], proofs=report['proofs']), ensure_ascii=False))


if __name__ == '__main__':
    main()
