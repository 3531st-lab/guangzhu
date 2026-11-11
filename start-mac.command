#!/usr/bin/env bash
# 光筑 macOS 开发版一键启动脚本（在 Finder 中双击运行，或终端执行 bash start-mac.command）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PYTHONUTF8=1

find_python312() {
  for candidate in python3.12 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>/dev/null; then
        command -v "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "[光筑] 首次在 macOS 启动，正在创建 Python 3.12 虚拟环境 (.venv)..."
  PY312="$(find_python312 || true)"
  if [[ -z "$PY312" ]]; then
    echo "错误：未找到 Python 3.12。请先执行 'brew install python@3.12' 或从 python.org 安装 Python 3.12。" >&2
    exit 1
  fi
  "$PY312" -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/python" -m pip install --upgrade pip
  "$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements-macos.txt"
  "$ROOT/.venv/bin/python" -m pip install -e "$ROOT"
fi

export PYTHONPATH="$ROOT/backend:$ROOT:${PYTHONPATH:-}"
"$ROOT/.venv/bin/python" -m guangzhu.selfcheck
exec "$ROOT/.venv/bin/python" "$ROOT/desktop/app.py"
