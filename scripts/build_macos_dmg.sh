#!/usr/bin/env bash
# Build self-contained 光筑.app and macOS .dmg installer (Apple Silicon arm64 & Intel x64).
# Usage on macOS:
#   bash scripts/build_macos_dmg.sh [--arch arm64|x64] [--agh-archive /path/to/agnes-darwin.tar.gz]
set -euo pipefail

APP_NAME="光筑"
APP_VERSION="0.3.0"
ARCH_OVERRIDE=""
AGH_ARCHIVE=""
PYTHON_TARBALL=""
CODESIGN_ID="${CODESIGN_IDENTITY:--}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch)
      ARCH_OVERRIDE="$2"
      shift 2
      ;;
    --agh-archive)
      AGH_ARCHIVE="$2"
      shift 2
      ;;
    --python-tarball)
      PYTHON_TARBALL="$2"
      shift 2
      ;;
    --codesign)
      CODESIGN_ID="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Error: build_macos_dmg.sh must be executed on macOS (or via .github/workflows/build-macos.yml)." >&2
  exit 1
fi

HOST_MACHINE="$(uname -m)"
if [[ -n "$ARCH_OVERRIDE" ]]; then
  ARCH_TAG="$ARCH_OVERRIDE"
elif [[ "$HOST_MACHINE" == "arm64" || "$HOST_MACHINE" == "aarch64" ]]; then
  ARCH_TAG="arm64"
else
  ARCH_TAG="x64"
fi

if [[ "$ARCH_TAG" == "arm64" ]]; then
  PBS_TRIPLE="aarch64-apple-darwin"
  CLANG_ARCH="arm64"
elif [[ "$ARCH_TAG" == "x64" ]]; then
  PBS_TRIPLE="x86_64-apple-darwin"
  CLANG_ARCH="x86_64"
else
  echo "Unsupported --arch '$ARCH_TAG' (expected arm64 or x64)" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CACHE_DIR="$ROOT/build/macos-installer-cache"
STAGE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/guangzhu-macos-stage.XXXXXX")"
trap 'rm -rf "$STAGE_ROOT"' EXIT

PAYLOAD_STAGE="$STAGE_ROOT/payload"
RUNTIME_STAGE="$STAGE_ROOT/runtime"
BUNDLE_DIR="$STAGE_ROOT/${APP_NAME}.app"
DMG_STAGE="$STAGE_ROOT/dmg-root"
DIST_DIR="$ROOT/dist/installer"

mkdir -p "$CACHE_DIR" "$PAYLOAD_STAGE" "$RUNTIME_STAGE" "$DIST_DIR"

echo "==> [1/7] Preparing standalone Python 3.12 runtime ($PBS_TRIPLE)..."
PBS_TAG="20250212"
PBS_VER="3.12.9"
PBS_FILENAME="cpython-${PBS_VER}+${PBS_TAG}-${PBS_TRIPLE}-install_only.tar.gz"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${PBS_FILENAME}"

if [[ -n "$PYTHON_TARBALL" ]]; then
  CACHED_PY_TAR="$PYTHON_TARBALL"
else
  CACHED_PY_TAR="$CACHE_DIR/$PBS_FILENAME"
  if [[ ! -s "$CACHED_PY_TAR" ]]; then
    echo "    Downloading $PBS_URL ..."
    curl -fL --retry 3 --connect-timeout 30 -o "$CACHED_PY_TAR.tmp" "$PBS_URL"
    mv "$CACHED_PY_TAR.tmp" "$CACHED_PY_TAR"
  fi
fi

mkdir -p "$RUNTIME_STAGE/python"
tar -xzf "$CACHED_PY_TAR" -C "$RUNTIME_STAGE/python" --strip-components=1
BUNDLED_PY="$RUNTIME_STAGE/python/bin/python3"

if [[ ! -x "$BUNDLED_PY" ]]; then
  echo "Error: Standalone Python binary missing at $BUNDLED_PY" >&2
  exit 1
fi

echo "==> [2/7] Installing locked macOS Python dependencies..."
export PYTHONUTF8=1
export PIP_NO_CACHE_DIR=1
"$BUNDLED_PY" -m pip install --upgrade pip setuptools wheel >/dev/null
"$BUNDLED_PY" -m pip install --no-compile -r "$ROOT/requirements-macos.txt"

# Remove pip-generated script wrappers with build-machine shebangs; keep only python* binaries/links
find "$RUNTIME_STAGE/python/bin" -maxdepth 1 ! -name 'python*' ! -path "$RUNTIME_STAGE/python/bin" -exec rm -rf {} +

SITE_PACKAGES="$("$BUNDLED_PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
find "$SITE_PACKAGES" -name "direct_url.json" -type f -delete || true

# Relative from Contents/Resources/runtime/python/lib/python3.12/site-packages -> Contents/Resources/payload
cat > "$SITE_PACKAGES/guangzhu_bundle.pth" <<'EOF'
../../../../../payload/backend
../../../../../payload
EOF

# Optional official AGH darwin runtime
mkdir -p "$RUNTIME_STAGE/agh"
if [[ -n "$AGH_ARCHIVE" && -f "$AGH_ARCHIVE" ]]; then
  echo "==> [2b/7] Extracting bundled AGH macOS runtime..."
  if [[ "$AGH_ARCHIVE" == *.zip ]]; then
    unzip -q "$AGH_ARCHIVE" -d "$RUNTIME_STAGE/agh"
  else
    tar -xzf "$AGH_ARCHIVE" -C "$RUNTIME_STAGE/agh"
  fi
  for nested in "$RUNTIME_STAGE"/agh/agnes-darwin-*.tar.gz; do
    if [[ -f "$nested" ]]; then
      tar -xzf "$nested" -C "$RUNTIME_STAGE/agh"
      rm -f "$nested"
    fi
  done
fi

echo "==> [3/7] Staging clean application payload..."
for rel in backend/guangzhu desktop data/catalog data/demo data/roofs .agh/skills; do
  mkdir -p "$(dirname "$PAYLOAD_STAGE/$rel")"
  cp -R "$ROOT/$rel" "$PAYLOAD_STAGE/$rel"
done

mkdir -p "$PAYLOAD_STAGE/data/demo/park-seeds/taizhou-cmc-demo"
cp "$ROOT/data/parks/taizhou-cmc-demo/park.json" "$PAYLOAD_STAGE/data/demo/park-seeds/taizhou-cmc-demo/park.json"

for notice in LICENSE THIRD_PARTY_NOTICES.md; do
  cp "$ROOT/$notice" "$PAYLOAD_STAGE/$notice"
done

mkdir -p "$PAYLOAD_STAGE/scripts" "$PAYLOAD_STAGE/projects" "$PAYLOAD_STAGE/runs" "$PAYLOAD_STAGE/data/showcase"
cp -R "$ROOT/runs/gz-changzhou-demo-1008-2113" "$PAYLOAD_STAGE/data/showcase/gz-changzhou-demo-1008-2113"

for sname in agh_export_run.py agh_verify_run.py check_secrets.py sync_macos_workspace.py; do
  cp "$ROOT/scripts/$sname" "$PAYLOAD_STAGE/scripts/$sname"
done

rm -f "$PAYLOAD_STAGE/desktop/start.cmd" "$PAYLOAD_STAGE/desktop/settings.json"
rm -rf "$PAYLOAD_STAGE/desktop/launcher"
find "$PAYLOAD_STAGE" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$PAYLOAD_STAGE" -name ".DS_Store" -type f -delete

if command -v npm >/dev/null 2>&1 && [[ -f "$ROOT/agh-plugin/guangzhu-studio/package.json" ]]; then
  echo "    Building guangzhu-studio plugin snapshot..."
  npm --prefix "$ROOT/agh-plugin/guangzhu-studio" ci --ignore-scripts --silent
  PLUGIN_OUT="$(PYTHONPATH="$ROOT/backend" "$BUNDLED_PY" -B "$ROOT/scripts/build_agh_plugin.py" --check --release | grep '^Package source: file:\./' | sed 's|^Package source: file:\./||')"
  if [[ -n "$PLUGIN_OUT" && -d "$ROOT/$PLUGIN_OUT" ]]; then
    mkdir -p "$PAYLOAD_STAGE/plugins"
    cp -R "$ROOT/$PLUGIN_OUT" "$PAYLOAD_STAGE/plugins/"
  fi
fi

# Prune upstream package tests & verify no developer paths remain
mv "$RUNTIME_STAGE" "$PAYLOAD_STAGE/runtime"
HOST_PY="$(command -v python3)"
"$PAYLOAD_STAGE/runtime/python/bin/python3" "$ROOT/scripts/installer_stage.py" \
  "$PAYLOAD_STAGE" \
  --host-python "$HOST_PY" \
  --developer-root "$ROOT" \
  --clean
mv "$PAYLOAD_STAGE/runtime" "$RUNTIME_STAGE"

# Generate build-manifest.json
"$RUNTIME_STAGE/python/bin/python3" - "$PAYLOAD_STAGE" "$APP_VERSION" "$ARCH_TAG" <<'PY'
import hashlib, json, sys
from pathlib import Path

stage = Path(sys.argv[1]).resolve()
version = sys.argv[2]
arch = sys.argv[3]
files = {}
for item in sorted(stage.rglob("*")):
    if not item.is_file() or item.suffix in (".pyc", ".log"):
        continue
    rel = item.relative_to(stage).as_posix()
    files[rel] = hashlib.sha256(item.read_bytes()).hexdigest()

manifest = {
    "version": version,
    "platform": f"darwin-{arch}",
    "application_files": files,
}
(stage / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "==> [4/7] Assembling ${APP_NAME}.app bundle..."
mkdir -p "$BUNDLE_DIR/Contents/MacOS" "$BUNDLE_DIR/Contents/Resources"
cp "$ROOT/installer/macos/Info.plist" "$BUNDLE_DIR/Contents/Info.plist"
cp "$ROOT/desktop/web/assets/guangzhu.icns" "$BUNDLE_DIR/Contents/Resources/guangzhu.icns"
cp "$ROOT/installer/macos/bootstrap_macos.py" "$BUNDLE_DIR/Contents/Resources/bootstrap_macos.py"
mv "$RUNTIME_STAGE" "$BUNDLE_DIR/Contents/Resources/runtime"
mv "$PAYLOAD_STAGE" "$BUNDLE_DIR/Contents/Resources/payload"

if command -v clang >/dev/null 2>&1; then
  echo "    Compiling native Mach-O launcher ($CLANG_ARCH)..."
  clang -O2 -Wall -Wextra \
    -arch "$CLANG_ARCH" \
    -mmacosx-version-min=11.0 \
    "$ROOT/installer/macos/launcher_macos.c" \
    -o "$BUNDLE_DIR/Contents/MacOS/${APP_NAME}"
  chmod 755 "$BUNDLE_DIR/Contents/MacOS/${APP_NAME}"
else
  echo "    clang not found; installing POSIX launcher fallback..."
  cp "$ROOT/installer/macos/launch-fallback.sh" "$BUNDLE_DIR/Contents/MacOS/${APP_NAME}"
  chmod 755 "$BUNDLE_DIR/Contents/MacOS/${APP_NAME}"
fi

echo "==> [5/7] Code-signing ${APP_NAME}.app (identity: $CODESIGN_ID)..."
xattr -cr "$BUNDLE_DIR" || true
find "$BUNDLE_DIR/Contents/Resources/runtime" -type f \( -name "*.dylib" -o -name "*.so" \) -print0 | \
  xargs -0 -I{} codesign --force --sign "$CODESIGN_ID" "{}" 2>/dev/null || true
if [[ -f "$BUNDLE_DIR/Contents/Resources/runtime/python/bin/python3.12" ]]; then
  codesign --force --sign "$CODESIGN_ID" "$BUNDLE_DIR/Contents/Resources/runtime/python/bin/python3.12"
fi
codesign --force --deep --sign "$CODESIGN_ID" "$BUNDLE_DIR"
codesign --verify --deep --strict "$BUNDLE_DIR"

echo "==> [6/7] Running isolated macOS runtime, Mach-O launcher & native PySAM verification..."
VERIFY_HOME="$STAGE_ROOT/verify-home"
mkdir -p "$VERIFY_HOME"
if [[ "$ARCH_TAG" == "$HOST_MACHINE" || ( "$ARCH_TAG" == "x64" && "$HOST_MACHINE" == "x86_64" ) ]]; then
  HOME="$VERIFY_HOME" \
  GUANGZHU_DATA_HOME="$VERIFY_HOME/support" \
  "$BUNDLE_DIR/Contents/MacOS/${APP_NAME}" -B -c "import guangzhu, webview, PySAM; print('    Signed Mach-O launcher import check OK')"

  GUANGZHU_DATA_HOME="$VERIFY_HOME/support" \
  GUANGZHU_RUNTIME_ROOT="$BUNDLE_DIR/Contents/Resources/runtime" \
  "$BUNDLE_DIR/Contents/Resources/runtime/python/bin/python3" -B - "$VERIFY_HOME/support" "$BUNDLE_DIR/Contents/Resources/payload" <<'PY'
import json, os, sys
from pathlib import Path

verify_home = Path(sys.argv[1])
payload = Path(sys.argv[2])
sys.path.insert(0, str(payload / "scripts"))
from sync_macos_workspace import sync_workspace

ws = verify_home / "workspace"
sync_workspace(payload, ws)
os.chdir(ws)
sys.path.insert(0, str(ws / "backend"))

import webview, PySAM, guangzhu
from guangzhu.selfcheck import selfcheck, offline_analysis

checks = selfcheck()
assert checks["passed"], f"selfcheck failed: {checks['failures']}"
offline = offline_analysis()
assert offline["passed"], f"offline_analysis failed: {offline['failures']}"
print("    macOS selfcheck & PySAM offline_analysis passed:", json.dumps({
    "pysam_kwh": offline["pysam_kwh"],
    "satmap_presets": offline["satmap_presets"],
}))
PY
  # Re-verify bundle signature remains 100% untouched after live smoke run!
  codesign --verify --deep --strict "$BUNDLE_DIR"
else
  echo "    Skipping live binary execution (cross-arch target $ARCH_TAG on $HOST_MACHINE host)."
fi
rm -rf "$VERIFY_HOME"

echo "==> [7/7] Creating drag-to-Applications .dmg installer..."
mkdir -p "$DMG_STAGE"
mv "$BUNDLE_DIR" "$DMG_STAGE/${APP_NAME}.app"
ln -s /Applications "$DMG_STAGE/Applications"

DMG_NAME="Guangzhu-Setup-${APP_VERSION}-macos-${ARCH_TAG}.dmg"
DMG_PATH="$DIST_DIR/$DMG_NAME"
rm -f "$DMG_PATH"

for attempt in 1 2 3; do
  if hdiutil create \
    -volname "${APP_NAME} ${APP_VERSION}" \
    -srcfolder "$DMG_STAGE" \
    -ov \
    -format UDZO \
    "$DMG_PATH" >/dev/null; then
    break
  fi
  if [[ "$attempt" -eq 3 ]]; then
    echo "Error: hdiutil failed after 3 attempts" >&2
    exit 1
  fi
  echo "    hdiutil busy (attempt $attempt), retrying in 3s..."
  sleep 3
done

DMG_SHA256="$(shasum -a 256 "$DMG_PATH" | awk '{print $1}')"
DMG_BYTES="$(stat -f%z "$DMG_PATH")"

echo ""
echo "============================================================"
echo "macOS Installer Ready!"
echo "  File   : $DMG_PATH"
echo "  Arch   : macOS $ARCH_TAG"
echo "  Bytes  : $DMG_BYTES"
echo "  SHA256 : $DMG_SHA256"
echo "============================================================"
