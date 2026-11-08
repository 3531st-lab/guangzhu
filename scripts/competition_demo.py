"""Reproducible synthetic compound-factory demo; no model calls or export approval."""
import argparse
import hashlib
import json
from pathlib import Path

from guangzhu import layout, project as storage
from guangzhu.config import DATA_DIR, ROOT
from guangzhu.models import Project


def rectangle(x, y, width, depth):
    return [[x,y],[x+width,y],[x+width,y+depth],[x,y+depth]]


def example():
    values = json.loads((DATA_DIR / 'demo/projects/changzhou-demo/project.json').read_text(encoding='utf-8'))
    values.update(id='compound-factory-demo', name='高低跨组合厂房（示意）', designs=[])
    values['requirements'] = {'text':'组合屋面和人工锁定演示；尺寸、承重与经济参数均为示意输入。', 'structured':{}}
    values['roof'] = dict(type='pitched', outline=rectangle(0,0,60,24), height_m=5,
                          parapet_height_m=0, load_capacity_kn_m2=.45, load_verified=False,
                          seam_setback_m=.5,
                          parts=[dict(id='main', label='双坡主厂房', outline=rectangle(0,0,60,24),
                                      kind='gable', eave_height_m=9, slope_deg=8, material='metal'),
                                 dict(id='annex', label='低跨平顶附楼', outline=rectangle(60,0,20,12),
                                      kind='flat', eave_height_m=5, material='concrete')],
                          obstacles=[dict(id='annex-hvac', label='附楼机房（示意）', kind='prism',
                                          footprint=rectangle(65,4,4,3), height_m=2)],
                          keepouts=[dict(id=f'skylight-{i+1}', label=f'采光带{i+1}', preset='skylight',
                                         polygon=rectangle(4+8*i,5,2,1), clearance_m=.3) for i in range(6)])
    values['equipment']['racking'] = 'plane_flush'
    return Project.model_validate(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default='compound-upgrade-demo', help='New project ID; existing projects are never overwritten')
    parser.add_argument('--analyze', action='store_true', help='Run cached-weather engineering calculations for the final version')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/competition-upgrade')
    args = parser.parse_args()
    record = example().model_copy(update={'id':args.project})
    if storage._path(args.project).exists():
        parser.error('项目编号已存在，请使用新的 --project 编号。')
    record = storage.save(record)
    initial = storage.save_design(record.id, layout.generate_layout(record, {}), offline=True)
    plane_id = next(p.id for p in record.roof.planes if p.part_id == 'main')
    locked = storage.edit_design(record.id, initial.version, [dict(op='lock_plane',plane_id=plane_id)],
                                 '人工确定主厂房一侧，锁定其组件与空白区', 'user', offline=True)
    ops = [dict(op='reflow_unlocked', params={'orientation':'landscape'})]
    reason = '保留锁定屋面，比较其余屋面的横排方案'
    preview = storage.preview_edit(record.id, locked['version'], ops, reason, 'user', offline=True)
    saved = storage.edit_design(record.id, locked['version'], ops, reason, 'user', offline=True,
                                expected_fingerprint=preview['fingerprint'])
    result = dict(project_id=record.id, version=saved['version'], changes=preview['changes'],
                  url=f'http://127.0.0.1:8765/#result/{record.id}?version={saved["version"]}',
                  basis='合成示意厂房，复用常州天气快照；不是实测厂房或客户成果。',
                  model_calls=0, analysis_complete=False)
    if args.analyze:
        from guangzhu.analysis import analyze
        result['analysis'] = analyze(record.id, saved['version'], offline=True)
        result['analysis_complete'] = True
        result['reflow_version'] = saved['version']
        # Demonstrate rule feedback on this synthetic project, retaining every failing version.
        result['checks'] = [dict(version=saved['version'], rules=result['analysis']['rules'])]
        for _ in range(2):
            if not result['analysis']['rules']['hard_failed']:
                break
            corrections = [op for op in result['analysis']['suggestions'] if op.get('op') == 'remove_modules']
            if not corrections:
                break
            corrected = storage.preview_edit(record.id, result['version'], corrections,
                                              '示意案例：依据规则移除未锁定的遮挡超限组件', 'rule', offline=True)
            if not corrected['design']['modules']:
                break
            saved = storage.edit_design(record.id, result['version'], corrections,
                                         '示意案例：依据规则移除未锁定的遮挡超限组件', 'rule', offline=True,
                                         expected_fingerprint=corrected['fingerprint'])
            result['version'] = saved['version']
            result['analysis'] = analyze(record.id, saved['version'], offline=True)
            result['checks'].append(dict(version=saved['version'], rules=result['analysis']['rules']))
        result['url'] = f'http://127.0.0.1:8765/#result/{record.id}?version={result["version"]}'
    args.output.mkdir(parents=True,exist_ok=True)
    for version in range(1,result['version']+1):
        path = storage._path(record.id,f'designs/v{version}.json')
        result.setdefault('sha256',{})[f'v{version}'] = hashlib.sha256(path.read_bytes()).hexdigest()
    target = args.output / f'{record.id}.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(project_id=record.id, version=saved['version'], summary=preview['summary'],
                          analysis_complete=result['analysis_complete'], result_file=str(target)),ensure_ascii=False))


if __name__ == '__main__':
    main()
