#!/bin/bash
# build.sh — Build CinderX from source using direct cmake
#
# Builds the CinderX extension module with local dependency overrides
# (no network access required).
#
# Usage:
#   ./build.sh              # Build CinderX
#   ./build.sh --clean      # Clean build artefacts first
#   ./build.sh --help       # Show this help
#
# Environment:
#   CINDERX_VENV     Path to the Python venv (default: ../venv)
#   CC / CXX         Override C/C++ compilers (default: clang/clang++)
#   BUILD_TYPE       cmake build type (default: RelWithDebInfo)
#
# Prerequisites:
#   - A Python 3.12 venv
#   - Clang or GCC >= 13
#   - cmake >= 3.19

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BUILD_DIR="scratch/build-$(uname -m)"
BUILD_TYPE="${BUILD_TYPE:-RelWithDebInfo}"
CC="${CC:-clang}"
CXX="${CXX:-clang++}"

# --- Parse arguments ---
CLEAN=""
for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=1 ;;
        --help|-h)
            head -18 "$0" | tail -16
            exit 0
            ;;
        *) echo "Unknown argument: $arg"; exit 2 ;;
    esac
done

# --- Activate venv ---
CINDERX_VENV="${CINDERX_VENV:-$(cd "$SCRIPT_DIR/.." && pwd)/venv}"
if [ ! -f "$CINDERX_VENV/bin/activate" ]; then
    echo "FATAL: venv not found at $CINDERX_VENV"
    echo "Create it with: python3.12 -m venv $CINDERX_VENV"
    exit 1
fi
# shellcheck disable=SC1091
source "$CINDERX_VENV/bin/activate"

# --- Verify Python version ---
PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
if [ "$PY_VERSION" != "3.12" ]; then
    echo "FATAL: Python 3.12 required, got $PY_VERSION"
    exit 1
fi
echo "Python: $(python3 --version) ($CINDERX_VENV)"

# --- Clean if requested ---
if [ -n "$CLEAN" ]; then
    echo "Cleaning build artefacts..."
    rm -rf "$BUILD_DIR"
    echo "Clean done."
fi

# --- Configure ---
echo "Configuring CinderX..."
echo "  Build dir:  $BUILD_DIR"
echo "  Build type: $BUILD_TYPE"
echo "  CC/CXX:     $CC / $CXX"
echo ""

cmake \
    -DCMAKE_BUILD_TYPE="$BUILD_TYPE" \
    -DCMAKE_C_COMPILER="$CC" \
    -DCMAKE_CXX_COMPILER="$CXX" \
    -DFETCHCONTENT_SOURCE_DIR_ASMJIT="$SCRIPT_DIR/deps/asmjit-src" \
    -DFETCHCONTENT_SOURCE_DIR_FMT="$SCRIPT_DIR/deps/fmt-src" \
    "-DFETCHCONTENT_SOURCE_DIR_PARALLEL-HASHMAP=$SCRIPT_DIR/deps/parallel-hashmap-src" \
    -DFETCHCONTENT_SOURCE_DIR_USDT="$SCRIPT_DIR/deps/usdt-src" \
    -DPY_VERSION:STRING="$PY_VERSION" \
    -DMETA_PYTHON:BOOL=ON \
    -DENABLE_ADAPTIVE_STATIC_PYTHON:BOOL=ON \
    -DENABLE_ELF_READER:BOOL=ON \
    -DENABLE_EVAL_HOOK:BOOL=ON \
    -DENABLE_FUNC_EVENT_MODIFY_QUALNAME:BOOL=ON \
    -DENABLE_GENERATOR_AWAITER:BOOL=ON \
    -DENABLE_INTERPRETER_LOOP:BOOL=ON \
    -DENABLE_LAZY_IMPORTS:BOOL=ON \
    -DENABLE_LIGHTWEIGHT_FRAMES:BOOL=ON \
    -DENABLE_PARALLEL_GC:BOOL=ON \
    -DENABLE_PEP523_HOOK:BOOL=ON \
    -DENABLE_PERF_TRAMPOLINE:BOOL=ON \
    -DENABLE_SYMBOLIZER:BOOL=ON \
    -DENABLE_USDT:BOOL=ON \
    -DENABLE_XXCLASSLOADER:BOOL=ON \
    -B "$BUILD_DIR" .

# --- Copy usdt header (required by build) ---
mkdir -p "$BUILD_DIR/generated/usdt"
cp deps/usdt-src/usdt_upstream.h "$BUILD_DIR/generated/usdt/" 2>/dev/null || true

# --- Build ---
echo ""
echo "Building..."
cmake --build "$BUILD_DIR" --config "$BUILD_TYPE" -- -j"$(nproc)"

# --- Install .so ---
echo ""
echo "Installing _cinderx.so..."
cp "$BUILD_DIR/_cinderx.so" cinderx/PythonLib/
echo "Installed to: cinderx/PythonLib/_cinderx.so"

# --- Verify ---
echo ""
echo "Verifying build..."
PYTHONPATH="$SCRIPT_DIR/cinderx/PythonLib:${PYTHONPATH:-}" python3 -c "
import _cinderx
import cinderjit
def _gate(): return 42
cinderjit.force_compile(_gate)
assert cinderjit.is_jit_compiled(_gate), 'force_compile failed'
assert _gate() == 42, 'JIT function returned wrong result'
print('CinderX JIT: OK (force_compile verified)')
" || {
    echo "FATAL: CinderX build verification failed"
    exit 1
}

echo ""
echo "Build complete."
