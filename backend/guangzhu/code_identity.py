"""Freeze the process's code identity when the tool implementation is loaded."""

from datetime import datetime, timezone
import hashlib
import os
import subprocess

from .config import ROOT


def current_identity():
    digest = hashlib.sha256()
    for path in sorted((ROOT / 'backend/guangzhu').rglob('*.py')):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b'\0' + path.read_bytes() + b'\0')
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True, capture_output=True, text=True, timeout=5).stdout.strip()
        scope = ['backend', 'scripts', 'desktop', 'agh-plugin', 'pyproject.toml', 'requirements*.txt']
        dirty = bool(subprocess.run(['git', 'status', '--porcelain', '--', *scope],
                     cwd=ROOT, check=True, capture_output=True, text=True, timeout=5).stdout)
    except (OSError, subprocess.SubprocessError):
        commit = dirty = None
    skill = (ROOT / '.agh/skills/pv-rooftop-design/SKILL.md').read_bytes().split('\n## 经验'.encode(), 1)[0].rstrip()
    return dict(commit=commit, dirty=dirty, source_sha256=digest.hexdigest(), skill_rules_sha256=hashlib.sha256(skill).hexdigest(),
                process_id=os.getpid(), started_at=datetime.now(timezone.utc).isoformat())


CODE_IDENTITY = current_identity()
