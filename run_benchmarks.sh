#!/usr/bin/env bash
# run_benchmarks.sh — CinderX benchmark runner for devgpu004
#
# Ensures correct Python, library paths, and JIT settings every time.
# All paths derived from the cinderx_dev root — nothing hardcoded that drifts.
#
# Usage:
#   ./run_benchmarks.sh abba              # Builtin micro-benchmarks
#   ./run_benchmarks.sh g1                # G1 fast path
#   ./run_benchmarks.sh jit               # JIT vs vanilla Python
#   ./run_benchmarks.sh spec              # Specialisation ON vs OFF
#   ./run_benchmarks.sh all               # Run everything
#   ./run_benchmarks.sh jit --reps=3      # Extra arguments passed through
#
# Environment variables (override if needed):
#   VANILLA_PYTHON   Path to vanilla Python (default: system fbcode python3.12)

set -euo pipefail

# --- Find cinderx_dev root ---
# This script lives in the cinderx/ subdirectory of cinderx_dev.
# Walk up to find the directory containing python-install/.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "${SCRIPT_DIR}/python-install" ]]; then
    CINDERX_DEV="${SCRIPT_DIR}"
elif [[ -d "${SCRIPT_DIR}/../python-install" ]]; then
    CINDERX_DEV="$(cd "${SCRIPT_DIR}/.." && pwd)"
else
    echo "FATAL: Cannot find python-install/ relative to ${SCRIPT_DIR}" >&2
    echo "This script must live in cinderx_dev/ or cinderx_dev/cinderx/" >&2
    exit 1
fi

PYTHON="${CINDERX_DEV}/python-install/bin/python3.12"
CINDERX_SRC="${CINDERX_DEV}/cinderx"
BENCHMARK="${CINDERX_SRC}/benchmark_cinderx.py"

# --- Verify prerequisites exist ---
fail=0
if [[ ! -x "${PYTHON}" ]]; then
    echo "FATAL: CinderX Python not found: ${PYTHON}" >&2
    fail=1
fi
if [[ ! -f "${BENCHMARK}" ]]; then
    echo "FATAL: benchmark_cinderx.py not found: ${BENCHMARK}" >&2
    fail=1
fi
if [[ ! -f "${CINDERX_SRC}/cinderx/PythonLib/_cinderx.so" ]]; then
    echo "FATAL: _cinderx.so not found — run build_cinderx.sh first" >&2
    fail=1
fi
if [[ "${fail}" -eq 1 ]]; then
    exit 1
fi

# --- Set environment ---
export PYTHONPATH="${CINDERX_SRC}/cinderx/PythonLib"
export LD_LIBRARY_PATH="${CINDERX_DEV}/python-install/lib"
export PYTHONJIT=1
export CINDERX_PYTHON="${PYTHON}"

# VANILLA_PYTHON: default to fbcode system python3.12 if not set
export VANILLA_PYTHON="${VANILLA_PYTHON:-/usr/local/fbcode/platform010-aarch64/bin/python3.12}"

# --- Run benchmark ---
# -S skips site.py, which would activate JIT with compile_after_n_calls=0
# and cause SIGSEGV during import-time compilation.
exec "${PYTHON}" -S "${BENCHMARK}" "$@"
