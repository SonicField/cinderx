#\!/bin/bash
# CinderX Standardised Build Script
# ALL builds must use this script. No ad-hoc build commands.
# Created: 2026-02-17 by supervisor

set -euo pipefail

CINDERX_ROOT="${CINDERX_ROOT:-$HOME/local/cinderx_dev/cinderx}"
PYTHON_INSTALL="${PYTHON_INSTALL:-$HOME/local/cinderx_dev/python-install}"
VENV="$HOME/local/cinderx_dev/venv"
SO_NAME="_cinderx.cpython-312-aarch64-linux-gnu.so"
OUTPUT_DIR="$CINDERX_ROOT/scratch/lib.linux-aarch64-cpython-312/cinderx"
PYTHONLIB_DIR="$CINDERX_ROOT/cinderx/PythonLib"
# Ensure Python shared library is findable
export LD_LIBRARY_PATH="${PYTHON_INSTALL}/lib:${LD_LIBRARY_PATH:-}"

# Verify we are on aarch64
ARCH=$(uname -m)
if [ "$ARCH" \!= "aarch64" ]; then
    echo "ERROR: Must build on aarch64. Current arch: $ARCH"
    exit 1
fi

echo "=== CinderX Build Script ==="
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Arch: $ARCH"
echo "Source: $CINDERX_ROOT"

# Use setup.py (matches working 09:55 .so build method)
cd "$CINDERX_ROOT"

# Set compiler — prefer /opt/llvm/stable if available, fall back to system clang.
# clang 19.1.7 was installed via dnf on 2026-03-18 as /usr/bin/clang++.
if [ -x /opt/llvm/stable/Toolchains/llvm-sand.xctoolchain/usr/bin/clang++ ]; then
    export CC=/opt/llvm/stable/Toolchains/llvm-sand.xctoolchain/usr/bin/clang
    export CXX=/opt/llvm/stable/Toolchains/llvm-sand.xctoolchain/usr/bin/clang++
elif [ -x /usr/bin/clang++ ]; then
    export CC=/usr/bin/clang
    export CXX=/usr/bin/clang++
else
    echo "ERROR: No clang compiler found. Install clang via: sudo dnf install clang"
    exit 1
fi

# Use python-install Python (pinned version, not fbcode platform Python which
# may be updated by fbcode and break CinderX ABI compatibility).
# Falls back to venv python if python-install is not available.
BUILD_PYTHON="$PYTHON_INSTALL/bin/python3.12"
if [ ! -x "$BUILD_PYTHON" ]; then
    BUILD_PYTHON="$VENV/bin/python3"
    echo "WARNING: python-install not found, falling back to venv Python"
fi

echo "=== Building with setup.py ==="
echo "Python: $BUILD_PYTHON ($($BUILD_PYTHON --version 2>&1))"
"$BUILD_PYTHON" setup.py build_ext --inplace 2>&1

# Copy to PythonLib
if [ -f "$OUTPUT_DIR/$SO_NAME" ]; then
    cp "$OUTPUT_DIR/$SO_NAME" "$PYTHONLIB_DIR/_cinderx.so"
    echo "=== Build Complete ==="
    echo "SO: $PYTHONLIB_DIR/_cinderx.so"
    echo "Size: $(stat -c %s "$PYTHONLIB_DIR/_cinderx.so") bytes"
    echo "MD5: $(md5sum "$PYTHONLIB_DIR/_cinderx.so" | cut -d" " -f1)"
    echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
else
    echo "ERROR: Build output not found at $OUTPUT_DIR/$SO_NAME"
    exit 1
fi
