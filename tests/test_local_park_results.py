"""Local park previews require current, complete calculations and explicit selection."""
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from guangzhu import park, park_store, layout
from guangzhu.models import Project
from guangzhu.analysis_inputs import project_signature, write_completion

ROOT = Path(__file__).parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n', encoding='utf-8')


@pytest.fixture
def local_park(tmp_path):
    key = 'taizhou-lixiahe-coldchain'
    shutil.copytree(ROOT / 'data/demo/projects' / key, tmp_path / 'data/demo/projects' / key)
    saved = park_store.save(dict(id='acceptance-park', name='组合演示', buildings=[dict(template=key)]), tmp_path)
    source = tmp_path / 'data/parks/acceptance-park/roofs' / ('acceptance-park--' + key) / 'project.json'
    record = Project.model_validate_json(source.read_text(encoding='utf-8'))
    record.id = 'new-unique-batch-id'
    design = layout.generate_layout(record, {})
    design.version = 2
    base = tmp_path / 'projects' / record.id
    write(base / 'project.json', record.model_dump(mode='json'))
    write(base / 'designs/v2.json', design.model_dump(mode='json'))
    # A later comparison candidate must not replace the explicitly selected v2.
    other = design.model_copy(deep=True)
    other.version = 3
    write(base / 'designs/v3.json', other.model_dump(mode='json'))
    write(base / 'local-selection.json', dict(version=2))
    metadata = dict(project_inputs_sha256=project_signature(record),
                    design_sha256=hashlib.sha256((base / 'designs/v2.json').read_bytes()).hexdigest(),
                    completion_required=True)
    directory = base / 'analysis/v2'
    summary = dict(version=2, modules=len(design.modules), dc_kw=10., electrical=dict(dc_ac_ratio=1.), yield_kwh=dict(p50=12000.))
    cash = dict(version=2, capex_cny=30000., payback_years=5., irr_pct=10., co2_t_per_year=6.,
                cashflows=[dict(net_cny=-30000), dict(net_cny=6000)], analysis_metadata=metadata)
    electric = dict(version=2, inverter_count=1, per_inverter=[dict(inverter='INV1', dc_kw=10., dc_ac_ratio=1., rated_ac_kw=10.)])
    records = {'summary':summary, 'economics':cash, 'electrical':electric,
               'structure':dict(version=2), 'shading':dict(version=2, metadata=metadata),
               'rules':dict(version=2, items=[dict(id='R01', status='pass', level='hard')])}
    for name, value in records.items():
        write(directory / (name + '.json'), value)
    write_completion(directory, 2, metadata['design_sha256'], metadata['project_inputs_sha256'])
    return tmp_path, park_store.Park.model_validate(saved), base


def test_unique_project_id_is_found_and_selected_version_is_previewed(local_park):
    root, saved, base = local_park
    result = park.named(saved, [], root)
    row = result['buildings'][0]['result']
    assert row['project_id'] == base.name and row['version'] == 2
    assert row['status_label'] == '规则计算候选·待批准导出'
    assert result['all']['dc_kw'] == 10.
    assert park.named(saved, [], root, require_export=True)['all']['count'] == 0


def test_modified_analysis_is_not_aggregated(local_park):
    root, saved, base = local_park
    path = base / 'analysis/v2/summary.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    payload['dc_kw'] = 9999
    write(path, payload)
    assert park.named(saved, [], root)['all']['count'] == 0


def test_changed_park_position_excludes_old_neighbor_calculation(local_park):
    root, saved, _ = local_park
    payload = saved.model_dump(mode='json')
    payload['buildings'][0]['x_m'] = 30.
    changed = park_store.Park.model_validate(park_store.save(payload, root))
    result = park.named(changed, [], root)
    assert result['all']['count'] == 0
    assert '园区位置或屋顶输入已变化' in result['skipped'][0]
