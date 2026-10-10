"""Exercise exact byte boundaries without building or executing an installer."""
import hashlib
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('installer_size', Path(__file__).parents[1] / 'scripts/installer_size.py')
size_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(size_gate)


@pytest.mark.parametrize('size,passed', [(0, False), (9, True), (10, False), (11, False)])
def test_size_gate_is_strict_and_records_actual_bytes_and_hash(tmp_path, size, passed):
    payload = tmp_path / 'fixture.bin'
    content = b'x' * size
    payload.write_bytes(content)
    result = size_gate.inspect(payload, limit=10)
    assert result['passed'] is passed
    assert result['bytes'] == size
    assert result['sha256'] == hashlib.sha256(content).hexdigest()
    assert size_gate.MAX_BYTES == 195_000_000


def test_missing_installer_cannot_pass(tmp_path):
    with pytest.raises(FileNotFoundError):
        size_gate.inspect(tmp_path / 'missing.bin')
