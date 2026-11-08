"""Create one editable, synthetic modeling example without changing an existing roof."""
import argparse
import json
from guangzhu.config import ROOT
from guangzhu.models import Project, project_id
from guangzhu.myroofs import folder, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', default='my-precision-workbench')
    args = parser.parse_args()
    identifier = project_id(args.id)
    destination = folder(ROOT) / identifier
    if destination.exists():
        parser.error(f'屋顶 {identifier} 已存在；请用 --id 指定新编号，避免覆盖编辑。')
    template = Project.model_validate_json(
        (ROOT / 'data/demo/projects/compound-factory-demo/project.json').read_text(encoding='utf-8'))
    roof = template.roof.model_dump(mode='json')
    # Edge indices are chosen only after the compound model has its canonical outline.
    segments = []
    for edge_index, point in enumerate(roof['outline']):
        following = roof['outline'][(edge_index + 1) % len(roof['outline'])]
        length = ((point[0]-following[0])**2+(point[1]-following[1])**2)**.5
        if length < 5:
            continue
        # A gap in each long edge makes the distinction from uniform walls easy to inspect.
        if length > 20:
            segments.extend([dict(edge_index=edge_index,start_ratio=0,end_ratio=.42,height_m=.8),
                             dict(edge_index=edge_index,start_ratio=.58,end_ratio=1,height_m=1.2)])
        else:
            segments.append(dict(edge_index=edge_index,start_ratio=0,end_ratio=1,height_m=.8))
    roof['parapet_segments'] = segments
    created = save(dict(id=identifier,name='精确建模工作台示例（合成尺寸）',site=template.site.model_dump(mode='json'),roof=roof),ROOT,create=True)
    print(json.dumps(dict(id=created,path=str(destination / 'project.json'),
                         url=f'http://127.0.0.1:8765/#roof/{created}',
                         parapet_segments=len(segments),synthetic=True),ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
