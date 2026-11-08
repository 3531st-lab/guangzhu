"""Stable fingerprints for the engineering inputs behind a saved calculation."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

from .models import Project
from .config import DATA_DIR

ANALYSIS_FILES = ('shading.json', 'electrical.json', 'structure.json', 'economics.json', 'rules.json', 'summary.json')
ENGINE_REVISION = '2026-11-04-reliability-1'
CATALOG_DIR = DATA_DIR / 'catalog'


def engine_inputs():
    """A catalogue or engine correction invalidates reuse of earlier calculations."""
    return dict(revision=ENGINE_REVISION, catalog_files={
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(CATALOG_DIR.glob('*.csv'))})


def project_signature(project):
    model = project if isinstance(project, Project) else Project.model_validate(project)
    values = model.model_dump(mode='json')
    # Adding another design or renaming a project does not change its physics.
    for key in ('schema', 'id', 'name', 'collection', 'designs'):
        values.pop(key, None)
    values['calculation_engine'] = engine_inputs()
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def write_completion(directory, version, design_sha256, project_inputs_sha256, *, expected_hashes=None):
    """Publish a completion record only after all calculation files were written.

    An interrupted rewrite leaves either the previous manifest (whose file hashes
    no longer match) or no manifest. Neither can claim a complete current result.
    """
    directory = Path(directory)
    actual = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in ANALYSIS_FILES}
    if expected_hashes is not None and actual != expected_hashes:
        raise ValueError('计算输出在保存期间发生变化，未发布完成清单，请重新计算。')
    packet = dict(schema='guangzhu.analysis-completion/1', version=version,
                  design_sha256=design_sha256, project_inputs_sha256=project_inputs_sha256,
                  completed_at=datetime.now(timezone.utc).isoformat(),
                  files=dict(expected_hashes) if expected_hashes is not None else actual)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=directory,
                                         prefix='.completion-', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            json.dump(packet, output, ensure_ascii=False, sort_keys=True, allow_nan=False)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, directory / 'completion.json')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return packet
