#!/usr/bin/env bash
# Build stub uplay_r1_loader64.dll (and uplay_r2_loader64.dll symlink) using
# llvm-mingw.  Run from the Madeira repo root after stage 03-llvm-mingw.
#
#   bash build/uplay-stub/build.sh
#
# Output: app/Madeira/arm64ec-windows/uplay_r1_loader64.dll
#         app/Madeira/arm64ec-windows/uplay_r2_loader64.dll  (identical copy)
#
# The DLLs are dropped next to xtajit64.dll so Wine finds them on the DLL
# search path before any system or game-directory copy.  Disrupt_64.dll
# LoadLibraryW("uplay_r1_loader64.dll") resolves here first.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# When invoked from a Madeira CI stage (STAGE_DIR = madeira/), the output dir
# must point back to the *this* repo's app/Madeira tree, not STAGE_DIR.
# GITHUB_WORKSPACE is set by the CI; fall back to REPO_ROOT when running locally.
: "${GITHUB_WORKSPACE:=$REPO_ROOT}"
SRC="$REPO_ROOT/tools/uplay-stub/uplay_r1_loader64.c"
OUT_DIR="$GITHUB_WORKSPACE/app/Madeira/arm64ec-windows"

# Locate llvm-mingw cross-compiler (installed by stage 03).
MINGW_DIR=$(ls -d "$GITHUB_WORKSPACE/toolchains"/llvm-mingw-*/bin 2>/dev/null | head -1)
if [ -z "$MINGW_DIR" ]; then
  echo "llvm-mingw not found under toolchains/; run stage 03-llvm-mingw first" >&2
  exit 1
fi
CC="$MINGW_DIR/x86_64-w64-mingw32-clang"
if [ ! -x "$CC" ]; then
  echo "compiler not found: $CC" >&2; exit 1
fi

mkdir -p "$OUT_DIR"
echo "[uplay-stub] compiling with $CC"

"$CC" \
  -O2 -shared \
  -o "$OUT_DIR/uplay_r1_loader64.dll" \
  "$SRC" \
  -Wl,--kill-at \
  -lkernel32

echo "[uplay-stub] built $OUT_DIR/uplay_r1_loader64.dll ($(wc -c < "$OUT_DIR/uplay_r1_loader64.dll") bytes)"

# Some Steam builds load uplay_r2_loader64.dll instead; provide a copy.
cp "$OUT_DIR/uplay_r1_loader64.dll" "$OUT_DIR/uplay_r2_loader64.dll"
echo "[uplay-stub] copied as uplay_r2_loader64.dll"

# Quick sanity: DLL exports UPLAY_Start
if command -v objdump >/dev/null 2>&1; then
  exports=$(objdump -p "$OUT_DIR/uplay_r1_loader64.dll" 2>/dev/null | grep -c 'UPLAY_Start' || true)
  echo "[uplay-stub] UPLAY_Start exports found: $exports"
fi
