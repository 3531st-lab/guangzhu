"""Test-only stdio launcher: keep production waiting or explicitly shorten it."""
import argparse
import json
import os
from pathlib import Path
import sys

from guangzhu import mcp_server, runtime_diagnostics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-evidence", type=Path, required=True)
    parser.add_argument("--diagnostics-dir", type=Path, required=True)
    parser.add_argument("--test-wait-seconds", type=float)
    args, remaining = parser.parse_known_args()
    if args.test_wait_seconds is not None:
        assert 0 < args.test_wait_seconds < 40
        mcp_server.WAIT_SECONDS = args.test_wait_seconds
    runtime_diagnostics.LOG_DIR = args.diagnostics_dir
    evidence = dict(environment_keys=sorted(os.environ), cwd=os.getcwd(), executable=sys.executable,
                    source=str(Path(mcp_server.__file__).resolve()), wait_seconds=mcp_server.WAIT_SECONDS,
                    test_threshold_override=args.test_wait_seconds is not None)
    args.launch_evidence.parent.mkdir(parents=True, exist_ok=True)
    args.launch_evidence.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.argv = [sys.argv[0], *remaining]
    mcp_server.main()


if __name__ == "__main__":
    main()
