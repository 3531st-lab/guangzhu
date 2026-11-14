#!/usr/bin/env bash
# Fallback POSIX launcher for 光筑.app when compiled without clang/Xcode CLT.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTENTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
RUNTIME_DIR="$RESOURCES_DIR/runtime"
PYTHON_BIN="$RUNTIME_DIR/python/bin/python3"
BOOTSTRAP_PY="$RESOURCES_DIR/bootstrap_macos.py"

if [[ ! -x "$PYTHON_BIN" ]]; then
  /usr/bin/osascript -e 'display alert "光筑" message "光筑的安装文件不完整（缺少内置 Python 3.12），请重新安装光筑 Mac 版。" as critical buttons {"好"} default button 1' || true
  exit 1
fi

export PYTHONUTF8=1
export PYTHONDONTWRITEBYTECODE=1
export GUANGZHU_RUNTIME_ROOT="$RUNTIME_DIR"

if [[ $# -eq 0 ]] || [[ $# -eq 1 && "$1" == -psn_* ]]; then
  exec "$PYTHON_BIN" -B "$BOOTSTRAP_PY"
else
  exec "$PYTHON_BIN" "$@"
fi
