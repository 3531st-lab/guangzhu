"""Check a caller-created default clone, writing all receipts outside that clone."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
RUNS = ('gz-t14-changzhou-005', 'gz-t14-lshape-001', 'gz-t14-rotated-002',
        'gz-t14-impossible-001', 'gz-t11-changzhou-006')
IMPORT_PROBE = r'''
from pathlib import Path
import json
import sys
import guangzhu
import guangzhu.api as api
import guangzhu.report.view as view
root = Path.cwd().resolve()
files = [guangzhu.__file__, api.__file__, view.__file__]
assert all(Path(file).resolve().is_relative_to(root / 'backend') for file in files), files
assert api.ROOT.resolve() == root
print(json.dumps(dict(executable=sys.executable, imports=files, root=str(root))))
'''


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('clone', type=Path, help='Absolute path to the already-created default clone')
    parser.add_argument('python', type=Path, help='Absolute source .venv interpreter, shared dependencies')
    parser.add_argument('output', type=Path, help='New output directory under source reports/assets')
    args = parser.parse_args()
    assert args.clone.is_absolute(), 'Clone path must be absolute'
    clone = args.clone.resolve()
    assert clone != ROOT and not clone.is_relative_to(ROOT), 'Use a separate clone outside the source tree'
    assert (clone / '.git').is_dir(), 'A normal caller-created git clone is required'
    output = args.output.resolve()
    assert output.is_relative_to(ROOT / 'reports/assets') and not output.is_relative_to(clone)
    output.mkdir(parents=True, exist_ok=False)
    assert args.python.is_absolute(), 'Shared source venv path must be absolute'
    python = args.python.resolve()
    node, npm = shutil.which('node'), shutil.which('npm')
    assert python.is_file() and node and npm, 'Source venv Python, Node and npm are required'
    npm_cli = Path(npm).parent / 'node_modules' / 'npm' / 'bin' / 'npm-cli.js'
    assert npm_cli.is_file(), 'Use the installed npm CLI through Node rather than a Windows shell shim'
    npm_command = [node, str(npm_cli)]
    env = os.environ.copy()
    env['PYTHONPATH'] = str(clone / 'backend')
    env['PATH'] = str(python.parent) + os.pathsep + env.get('PATH', '')
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    receipts = {}
    summary = {
        'started_at': now(),
        'source': str(ROOT),
        'clone': str(clone),
        'clone_creation': 'Caller-created checkout; this script does not clone or change Git configuration',
        'expected_creation_command': ['git', 'clone', str(ROOT), str(clone)],
        'python_dependency_scope': 'Shared source .venv interpreter and dependencies; no new Python environment installed',
        'python_executable': str(python),
        'npm_cli': str(npm_cli),
        'pythonpath': env['PYTHONPATH'],
        'output': str(output),
    }

    def write(name, value):
        with (output / name).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

    def run(label, command, cwd=clone):
        started, tick = now(), time.monotonic()
        completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, check=False)
        row = {
            'command': command,
            'cwd': str(cwd),
            'environment_overrides': {
                'PYTHONPATH': env['PYTHONPATH'],
                'PATH_prefix': str(python.parent),
                'PYTHONUTF8': '1',
                'PYTHONIOENCODING': 'utf-8',
                'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
            },
            'started_at': started,
            'ended_at': now(),
            'elapsed_seconds': round(time.monotonic() - tick, 3),
            'exit_code': completed.returncode,
        }
        for field in ('stdout', 'stderr'):
            content = getattr(completed, field)
            with (output / f'{label}.{field}.txt').open('xb') as stream:
                stream.write(content)
            row[field] = content.decode('utf-8', errors='replace')
            row[field + '_sha256'] = hashlib.sha256(content).hexdigest()
        write(label + '.json', row)
        receipts[label] = row
        print(json.dumps(dict(check=label, exit_code=completed.returncode)), flush=True)
        return row

    def require(label, command, cwd=clone):
        row = run(label, command, cwd)
        if row['exit_code'] != 0:
            raise RuntimeError(f'{label} failed with exit {row["exit_code"]}')
        return row['stdout']

    def blob_check(label, tree, algorithm):
        rows = []
        for entry in tree.split('\0'):
            if not entry:
                continue
            header, relative = entry.split('\t', 1)
            mode, kind, expected = header.split()
            assert kind == 'blob' and mode in ('100644', '100755'), (relative, mode, kind)
            file = clone / relative
            assert file.resolve().is_relative_to(clone), relative
            content = file.read_bytes()
            digest = hashlib.new(algorithm)
            digest.update(b'blob ' + str(len(content)).encode('ascii') + b'\0' + content)
            actual = digest.hexdigest()
            rows.append(dict(path=relative, bytes=len(content), git_blob=expected, worktree_blob=actual, matched=actual == expected))
        write(label + '.json', dict(files=rows, all_matched=all(row['matched'] for row in rows)))
        assert rows and all(row['matched'] for row in rows), label
        return len(rows)

    try:
        summary['head'] = require('head-before', ['git', 'rev-parse', 'HEAD']).strip()
        system = require('autocrlf-system', ['git', 'config', '--system', '--get', 'core.autocrlf']).strip()
        assert system == 'true', ('System autocrlf must remain default true', system)
        effective = require('autocrlf-effective', ['git', 'config', '--show-origin', '--get', 'core.autocrlf']).strip()
        assert effective.endswith('\ttrue'), effective
        summary['autocrlf_effective'] = effective
        assert require('status-before', ['git', 'status', '--porcelain', '--untracked-files=all']) == ''
        algorithm = require('object-format', ['git', 'rev-parse', '--show-object-format']).strip()
        assert algorithm in ('sha1', 'sha256'), algorithm
        tree = require('tree', ['git', 'ls-tree', '-rz', 'HEAD'])
        summary['tracked_files_checked'] = blob_check('blob-bytes-before', tree, algorithm)
        imported = run('clone-imports', [str(python), '-c', IMPORT_PROBE])
        summary['import_exit_code'] = imported['exit_code']
        if imported['exit_code'] == 0:
            summary['imports'] = json.loads(imported['stdout'])
        package = clone / 'agh-plugin' / 'guangzhu-studio'
        offline = run('npm-ci-offline', [*npm_command, 'ci', '--offline', '--ignore-scripts', '--no-audit', '--no-fund'], package)
        install = 'npm-ci-offline'
        if offline['exit_code'] != 0:
            require('npm-ci-network', [*npm_command, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], package)
            install = 'npm-ci-network'
        summary['dependency_install_receipt'] = install + '.json'
        require('npm-dependencies', [*npm_command, 'ls', '--depth=0', '--json'], package)
        modules = sorted(str(path.relative_to(clone)) for path in (clone / 'tests').rglob('*.test.mjs'))
        plugin = sorted(str(path.relative_to(clone)) for path in (package / 'test').glob('*.test.js'))
        assert modules and plugin
        commands = {
            'pytest': [str(python), '-m', 'pytest', '-q', '-m', 'not network'],
            'node-modules': [node, '--test', *modules],
            'node-plugin': [node, '--test', *plugin],
            'plugin-build': [str(python), 'scripts/build_agh_plugin.py', '--check'],
            'secrets': [str(python), 'scripts/check_secrets.py'],
            'loc': [str(python), 'scripts/loc.py'],
        }
        for name in RUNS:
            command = [str(python), 'tests/validate_t11_run.py', str(clone / 'runs' / name), str(output / name)]
            if name != 'gz-t11-changzhou-006':
                command.append('--report-only')
            commands['report-' + name] = command
        failures = [] if summary['import_exit_code'] == 0 else ['clone-imports']
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(run, label, command): label for label, command in commands.items()}
            for future in as_completed(futures):
                label = futures[future]
                try:
                    if future.result()['exit_code'] != 0:
                        failures.append(label)
                except Exception as error:
                    failures.append(label)
                    write(label + '-runner-error.json', dict(error=repr(error)))
        summary['failed_required_checks'] = failures
        summary['source_lines'] = int(re.search(r'^Total:\s+(\d+)', receipts['loc']['stdout'], re.M)[1])
        assert summary['source_lines'] <= 9500, 'Whole-repository source line cap exceeded'
        summary['tracked_files_rechecked'] = blob_check('blob-bytes-after', tree, algorithm)
        assert require('head-after', ['git', 'rev-parse', 'HEAD']).strip() == summary['head']
        assert not failures, failures
        summary['exit_code'] = 0
    except Exception as error:
        summary.update(exit_code=1, failure=repr(error))
    finally:
        try:
            status = run('status-after', ['git', 'status', '--porcelain', '--untracked-files=all'])
            summary['clone_clean_after'] = status['exit_code'] == 0 and status['stdout'] == ''
            if not summary['clone_clean_after']:
                summary['exit_code'] = 1
        except Exception as error:
            summary.update(exit_code=1, status_after_error=repr(error))
        summary['ended_at'] = now()
        summary['checks'] = {
            label: {key: row[key] for key in ('exit_code', 'elapsed_seconds')} for label, row in sorted(receipts.items())
        }
        write('summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
