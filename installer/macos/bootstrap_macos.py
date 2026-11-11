"""macOS .app bundle entry bootstrap: syncs immutable payload to user workspace, then runs desktop/app.py."""

from __future__ import annotations

import os
from pathlib import Path
import runpy
import sys


def main() -> None:
    resources = Path(__file__).resolve().parent
    payload = resources / "payload"
    runtime = resources / "runtime"
    data_home = Path(
        os.environ.get("GUANGZHU_DATA_HOME")
        or (Path.home() / "Library" / "Application Support" / "Guangzhu")
    )
    workspace = data_home / "workspace"

    os.environ["GUANGZHU_DATA_HOME"] = str(data_home)
    os.environ["GUANGZHU_RUNTIME_ROOT"] = str(runtime)
    os.environ.setdefault("PYTHONUTF8", "1")

    scripts_dir = str(payload / "scripts")
    sys.path.insert(0, scripts_dir)
    from sync_macos_workspace import sync_workspace

    sync_workspace(payload, workspace)

    sys.path[:] = [entry for entry in sys.path if entry != scripts_dir]
    backend_dir = str(workspace / "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    os.chdir(workspace)
    app_entry = workspace / "desktop" / "app.py"
    sys.argv = [str(app_entry)]
    runpy.run_path(str(app_entry), run_name="__main__")


if __name__ == "__main__":
    main()
