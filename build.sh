#!/bin/bash
# build.sh — Build CinderX from source
#
# Builds the CinderX extension module using pip install -e . with local
# dependency overrides (no network access required).
#
# Usage:
#   ./build.sh              # Build CinderX in the active venv
#   ./build.sh --clean      # Clean build artefacts first
#   ./build.sh --help       # Show this help
#
# Environment:
#   CINDERX_VENV     Path to the Python venv (default: ../venv)
#   CC / CXX         Override C/C++ compilers
#
# Prerequisites:
#   - A Python 3.12 venv with pip and setuptools
#   - GCC >= 13 or Clang
#   - cmake >= 3.19

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Parse arguments ---
CLEAN=""
for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=1 ;;
        --help|-h)
            head -16 "$0" | tail -14
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
    rm -rf scratch/ *.egg-info/
    find . -name '*.so' -path './cinderx/*' -delete 2>/dev/null || true
    echo "Clean done."
fi

# --- Local dependency overrides ---
# These tell cmake's FetchContent to use vendored sources instead of
# fetching from GitHub (which is blocked behind the proxy).
export CMAKE_ARGS="${CMAKE_ARGS:-}"
CMAKE_ARGS="$CMAKE_ARGS -DFETCHCONTENT_SOURCE_DIR_ASMJIT=$SCRIPT_DIR/deps/asmjit-src"
CMAKE_ARGS="$CMAKE_ARGS -DFETCHCONTENT_SOURCE_DIR_FMT=$SCRIPT_DIR/deps/fmt-src"
CMAKE_ARGS="$CMAKE_ARGS -DFETCHCONTENT_SOURCE_DIR_PARALLEL-HASHMAP=$SCRIPT_DIR/deps/parallel-hashmap-src"
CMAKE_ARGS="$CMAKE_ARGS -DFETCHCONTENT_SOURCE_DIR_USDT=$SCRIPT_DIR/deps/usdt-src"
export CMAKE_ARGS

echo "Building CinderX..."
echo "  CMAKE_ARGS: $CMAKE_ARGS"
echo ""

# --- Build ---
pip install -e . --no-build-isolation 2>&1

# --- Verify ---
echo ""
echo "Verifying build..."
python3 -c "
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
