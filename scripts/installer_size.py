"""Record the built installer hash and enforce a strict decimal 195 MB ceiling."""
import argparse
import hashlib
import json
from pathlib import Path


MAX_BYTES = 195_000_000


def inspect(installer, limit=MAX_BYTES):
    installer = Path(installer)
    size = installer.stat().st_size
    with installer.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(file=installer.name, bytes=size, decimal_mb=round(size / 1_000_000, 3),
                limit_bytes=limit, passed=0 < size < limit, sha256=digest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('installer', type=Path)
    args = parser.parse_args()
    result = inspect(args.installer)
    target = args.installer.with_suffix('.size.json')
    target.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f"Installer size: {result['bytes']} bytes; required: 0 < bytes < {MAX_BYTES}; passed: {result['passed']}")
    print(f"Size and SHA256 audit: {target}")
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
