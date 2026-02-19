#!/bin/bash
# ABBA-style benchmark: CinderX JIT ON vs JIT OFF
# Uses pyperf timeit for statistical rigour.
# Pattern: ON OFF OFF ON ON OFF OFF ON (8 runs, 4 per condition)
#
# Usage: ./abba_benchmark.sh
# Output: benchmark_results/<timestamp>/ directory

set -euo pipefail

RESULTS_DIR="${HOME}/local/cinderx_dev/cinderx/benchmark_results"
CINDERX_VENV="${CINDERX_VENV:-$HOME/local/cinderx_dev/venv}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RUN_DIR="${RESULTS_DIR}/${TIMESTAMP}"

# Activate venv — fail fast if missing
if [ ! -f "$CINDERX_VENV/bin/activate" ]; then
    echo "FATAL: venv not found at $CINDERX_VENV"
    echo "Create it with: python3 -m venv $CINDERX_VENV"
    exit 1
fi
# shellcheck disable=SC1091
source "$CINDERX_VENV/bin/activate"

PYTHON="${CINDERX_PYTHON:-python3}"

mkdir -p "$RUN_DIR"

# Define benchmarks as pyperf timeit statements
# Each benchmark: NAME|SETUP|STMT
BENCHMARKS=(
    "generator_simple|def gen():\n for i in range(1000):\n  yield i|list(gen())"
    "generator_parameterised|def gen(n):\n for i in range(n):\n  yield i * 2|list(gen(1000))"
    "generator_closure|x=42\ndef gen():\n for i in range(1000):\n  yield i + x|list(gen())"
    "generator_yield_from|def inner():\n yield from range(500)\ndef outer():\n yield from inner()\n yield from inner()|list(outer())"
    "generator_send|def gen():\n val = 0\n for _ in range(100):\n  val = yield val\n  val = (val or 0) + 1|g=gen();next(g);[g.send(i) for i in range(99)]"
    "comprehension_list|None|[i*2 for i in range(1000)]"
    "comprehension_dict|None|{i: i*2 for i in range(1000)}"
    "function_calls|def f(x):\n return x + 1|sum(f(i) for i in range(1000))"
    "nested_calls|def f(x): return x+1\ndef g(x): return f(x)+1\ndef h(x): return g(x)+1|sum(h(i) for i in range(1000))"
    "fibonacci|def fib(n):\n a,b=0,1\n for _ in range(n):\n  a,b=b,a+b\n return a|fib(100)"
    "nbody_simple|import math\ndef nbody(n):\n bodies=[(i*0.1,i*0.2,i*0.3) for i in range(10)]\n for _ in range(n):\n  for i,b in enumerate(bodies):\n   bodies[i]=(b[0]+0.01,b[1]+0.02,b[2]+0.03)\n return bodies|nbody(100)"
    "float_arithmetic|None|sum(i*0.1+i*0.2 for i in range(1000))"
    "string_formatting|None|' '.join(f'item_{i}' for i in range(1000))"
    "dict_operations|d={i:i*2 for i in range(1000)}|sum(d.values());d.update({i:i*3 for i in range(500)})"
    "exception_handling|def f(x):\n try:\n  return 1/x\n except ZeroDivisionError:\n  return 0|[f(i) for i in range(1000)]"
)

# ABBA pattern
PATTERN=("on" "off" "off" "on" "on" "off" "off" "on")

echo "=== ABBA Benchmark: pyperf timeit ==="
echo "=== Output: $RUN_DIR ==="
echo "=== ${#BENCHMARKS[@]} benchmarks x ${#PATTERN[@]} runs ==="
echo "=== Started: $(date) ==="
echo ""

for run_idx in "${!PATTERN[@]}"; do
    run_num=$((run_idx + 1))
    condition="${PATTERN[$run_idx]}"

    echo "========================================="
    echo "=== Run $run_num/8: JIT $condition ==="
    echo "=== Started: $(date) ==="
    echo "========================================="

    run_file="${RUN_DIR}/run${run_num}_jit_${condition}.json"

    for bench_spec in "${BENCHMARKS[@]}"; do
        IFS='|' read -r name setup stmt <<< "$bench_spec"

        # Convert \n in setup to actual newlines
        setup_arg=$(echo -e "$setup")

        bench_file="${RUN_DIR}/run${run_num}_jit_${condition}_${name}.json"

        echo -n "  $name... "

        if [ "$condition" = "on" ]; then
            $PYTHON -m pyperf timeit \
                --setup "$setup_arg" \
                --name "$name" \
                -o "$bench_file" \
                --min-time 0.5 \
                -- "$stmt" 2>/dev/null && echo "OK" || echo "FAIL"
        else
            PYTHONJITDISABLE=1 $PYTHON -m pyperf timeit \
                --setup "$setup_arg" \
                --name "$name" \
                -o "$bench_file" \
                --min-time 0.5 \
                -- "$stmt" 2>/dev/null && echo "OK" || echo "FAIL"
        fi
    done

    echo "  Run $run_num complete: $(date)"
    echo ""
done

echo "=== All runs complete: $(date) ==="
echo ""

# Comparison: aggregate ON vs OFF for each benchmark
echo "=== Comparison ==="
echo ""

for bench_spec in "${BENCHMARKS[@]}"; do
    IFS='|' read -r name setup stmt <<< "$bench_spec"

    # Find first ON and first OFF file for this benchmark
    on_file="${RUN_DIR}/run1_jit_on_${name}.json"
    off_file="${RUN_DIR}/run2_jit_off_${name}.json"

    if [ -f "$on_file" ] && [ -f "$off_file" ]; then
        echo "--- $name ---"
        $PYTHON -m pyperf compare_to "$off_file" "$on_file" 2>/dev/null || echo "  (comparison failed)"
        echo ""
    fi
done

echo "=== Full results in: $RUN_DIR ==="
echo "=== To compare manually: ==="
echo "python3 -m pyperf compare_to <off.json> <on.json>"
echo ""
echo "=== Done ==="
