#!/bin/bash
# run_cinderx_tests.sh — Canonical CinderX JIT test runner
#
# Runs CinderX test suites and CPython regression tests.
#
# Usage:
#   ./run_cinderx_tests.sh              # Run all CinderX tests (default)
#   ./run_cinderx_tests.sh jit          # Run only JIT tests
#   ./run_cinderx_tests.sh runtime      # Run only runtime tests
#   ./run_cinderx_tests.sh compiler     # Run only compiler tests (SBS shards)
#   ./run_cinderx_tests.sh compiler-full # Run all compiler tests (SBS + individual)
#   ./run_cinderx_tests.sh overrides    # Run CPython override tests
#   ./run_cinderx_tests.sh cpython      # Run CPython regression suite (large)
#   ./run_cinderx_tests.sh full         # Run everything: CinderX + CPython
#   ./run_cinderx_tests.sh TESTNAME     # Run a specific test module
#   ./run_cinderx_tests.sh --fix-opcode # Fix cinderx.opcode and exit
#
# Environment:
#   PYTHONPATH is set to include PythonLib for the opcode module.
#   CinderX tests use force_compile() internally — no JIT env var needed.
#   CINDERX_ROOT defaults to the directory containing this script.
#
# Gate: Aborts immediately if CinderX JIT is not importable or not enabled.
#       Will NOT silently run tests on stock Python.

set -uo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CINDERX_ROOT="${CINDERX_ROOT:-$_SCRIPT_DIR}"
CINDERX_VENV="${CINDERX_VENV:-$(cd "$_SCRIPT_DIR/.." && pwd)/venv}"
PYTHONLIB="$CINDERX_ROOT/cinderx/PythonLib"
TEST_DIR="$PYTHONLIB/test_cinderx"
RESULTS_FILE="/tmp/cinderx_test_results_$(date +%Y%m%d_%H%M%S).txt"

# Activate venv — fail fast if missing
if [ ! -f "$CINDERX_VENV/bin/activate" ]; then
    echo "FATAL: venv not found at $CINDERX_VENV"
    echo "Create it with: python3 -m venv $CINDERX_VENV"
    exit 1
fi
# shellcheck disable=SC1091
source "$CINDERX_VENV/bin/activate"

# Ensure opcode.py is in place (cmake build skips this step from setup.py)
fix_opcode() {
    local opcode_src="$PYTHONLIB/opcodes/3.12/opcode.py"
    local opcode_dst="$PYTHONLIB/cinderx/opcode.py"
    if [ -f "$opcode_src" ] && [ ! -f "$opcode_dst" ]; then
        echo "Copying opcode.py (cmake build fixup)..."
        cp "$opcode_src" "$opcode_dst"
    fi
}

# NOTE: CINDERJIT_ENABLE is NOT a real CinderX env var. The real env vars are:
#   PYTHONJITALL=1  — compile every function
#   PYTHONJITAUTO=N — compile functions after N calls (hot-loop detection)
#   PYTHONJIT=1     — enable JIT subsystem (allows force_compile)
# CinderX tests use force_compile() internally, so we don't set any of these.
# cinderjit.is_enabled() returns True even without PYTHONJITALL/AUTO — it just
# means the JIT subsystem is loaded and force_compile() will work.
export PYTHONPATH="$PYTHONLIB${PYTHONPATH:+:$PYTHONPATH}"

# Test suite definitions
# Category 1: JIT tests (17 suites)
JIT_TESTS=(
    test_cinderjit
    test_jit_async_generators
    test_jit_attr_cache
    test_jit_coroutines
    test_jit_count_calls
    test_jit_disable
    test_jit_exception
    test_jit_frame
    test_jit_generator_aarch64
    test_jit_generators
    test_jit_global_cache
    test_jitlist
    test_jit_perf_map
    test_jit_preload
    test_jit_specialization
    test_jit_inline_exception
    test_jit_kwarg_fastpath
    test_jit_lazy_init
    test_jit_yield_from
    test_jit_specialised_opcode_deopt
    test_jit_speculative_inlining
    test_jit_support_instrumentation
    test_jit_type_annotations
    test_jitconfig_layout_sentinel
    test_binary_subscr_correctness
    test_binary_subscr_deopt
    test_diamond_self_identity
    test_exception_handler_inlining
    test_for_iter_list_mutation
    test_for_iter_polymorphic_deopt
    test_load_attr_instance_value
    test_load_attr_module_inline
    test_store_attr_instance_value
    test_adversarial_emitcond
    test_adversarial_multiop
    test_adversarial_recompilation
    test_adversarial_selective
    test_adversarial_valuechain
    test_double_binary_op
    test_jit_exception_edge_cases
    test_safe_type_gc_optout
)

RUNTIME_TESTS=(
    test_asynclazyvalue
    test_coro_extensions
    test_enabling_parallel_gc
    test_frame_evaluator
    test_immortalize
    test_oss_quick
    test_parallel_gc
    test_perfmaps
    test_perf_profiler_precompile
    test_python310_bytecodes
    test_python312_bytecodes
    test_python314_bytecodes
    test_shadowcode
    test_type_cache
)

COMPILER_TESTS=(
    test_compiler_sbs_stdlib_0
    test_compiler_sbs_stdlib_1
    test_compiler_sbs_stdlib_2
    test_compiler_sbs_stdlib_3
    test_compiler_sbs_stdlib_4
    test_compiler_sbs_stdlib_5
    test_compiler_sbs_stdlib_6
    test_compiler_sbs_stdlib_7
    test_compiler_sbs_stdlib_8
    test_compiler_sbs_stdlib_9
)

# Category 4: Compiler individual tests (16 suites — NOT the SBS shards)
# These use the dotted module path: test_cinderx.test_compiler.test_X
COMPILER_INDIVIDUAL_TESTS=(
    test_compiler.test_api
    test_compiler.test_cinder
    test_compiler.test_code_sbs
    test_compiler.test_corpus
    test_compiler.test_errors
    test_compiler.test_exception_table
    test_compiler.test_flags
    test_compiler.test_graph
    test_compiler.test_linepos
    test_compiler.test_optimizer
    test_compiler.test_py310
    test_compiler.test_pysourceloader
    test_compiler.test_sbs_external
    test_compiler.test_symbols
    test_compiler.test_unparse
    test_compiler.test_visitor
)

# Category 5: CPython override tests (12 suites)
# CinderX-specific replacements for CPython tests where behaviour diverges
CPYTHON_OVERRIDE_TESTS=(
    test_cpython_overrides.test_asyncgen
    test_cpython_overrides.test_coroutines
    test_cpython_overrides.test_dis
    test_cpython_overrides.test_fork1
    test_cpython_overrides.test_gdb
    test_cpython_overrides.test_generators
    test_cpython_overrides.test_inspect
    test_cpython_overrides.test__opcode
    test_cpython_overrides.test_repl
    test_cpython_overrides.test_tracemalloc
    test_cpython_overrides.test_trace
    test_cpython_overrides.test_types
)

# Colour codes (disabled if not a terminal)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    RED='' GREEN='' YELLOW='' BOLD='' RESET=''
fi

# Handle --fix-opcode before anything else
if [ "${1:-}" = "--fix-opcode" ]; then
    fix_opcode
    echo "Done."
    exit 0
fi

# Select test suites
# Strip leading -- from argument (accept both --all and all)
ARG="${1:-all}"
ARG="${ARG#--}"
RUN_CPYTHON=""

case "$ARG" in
    jit)           SUITES=("${JIT_TESTS[@]}") ;;
    runtime)       SUITES=("${RUNTIME_TESTS[@]}") ;;
    compiler)      SUITES=("${COMPILER_TESTS[@]}") ;;
    compiler-full) SUITES=("${COMPILER_TESTS[@]}" "${COMPILER_INDIVIDUAL_TESTS[@]}") ;;
    overrides)     SUITES=("${CPYTHON_OVERRIDE_TESTS[@]}") ;;
    all)           SUITES=("${JIT_TESTS[@]}" "${RUNTIME_TESTS[@]}" "${COMPILER_TESTS[@]}" "${COMPILER_INDIVIDUAL_TESTS[@]}" "${CPYTHON_OVERRIDE_TESTS[@]}") ;;
    cpython)       RUN_CPYTHON=1; SUITES=() ;;
    full)          SUITES=("${JIT_TESTS[@]}" "${RUNTIME_TESTS[@]}" "${COMPILER_TESTS[@]}" "${COMPILER_INDIVIDUAL_TESTS[@]}" "${CPYTHON_OVERRIDE_TESTS[@]}"); RUN_CPYTHON=1 ;;
    help|-h)
        echo "Usage: $0 [all|jit|runtime|compiler|compiler-full|overrides|cpython|full|TESTNAME|--fix-opcode]"
        echo ""
        echo "  all            Run all CinderX tests: JIT + runtime + compiler + overrides (default)"
        echo "  jit            Run 17 JIT test suites only"
        echo "  runtime        Run 14 runtime test suites only"
        echo "  compiler       Run 10 compiler SBS test suites only"
        echo "  compiler-full  Run all compiler tests (10 SBS + 16 individual)"
        echo "  overrides      Run 12 CPython override test suites"
        echo "  cpython        Run CPython regression suite (~494 tests, slow)"
        echo "  full           Run everything: all CinderX + CPython regression"
        echo "  TESTNAME       Run a specific test module (e.g. test_jit_attr_cache)"
        echo "  --fix-opcode   Fix cinderx.opcode import and exit"
        exit 0
        ;;
    *)
        # Single test module
        SUITES=("$ARG")
        ;;
esac

# Always fix opcode first
fix_opcode

# Results tracking
TOTAL_PASS=0
TOTAL_FAIL=0
TOTAL_ERROR=0
TOTAL_SKIP=0
PASSED_SUITES=()
FAILED_SUITES=()
ERROR_SUITES=()
SKIPPED_SUITES=()
SUITE_COUNT=0

echo -e "${BOLD}CinderX Test Runner${RESET}"
echo "Root:     $CINDERX_ROOT"
echo "Python:   $(python3 --version 2>&1)"
echo "Suites:   ${#SUITES[@]} CinderX${RUN_CPYTHON:+ + CPython regression}"
echo "Results:  $RESULTS_FILE"
echo "Started:  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "---"

# HARD GATE: verify CinderX JIT is actually usable.
# cinderjit.is_enabled() is NOT sufficient — it returns True even without
# PYTHONJITALL/PYTHONJITAUTO. We verify that force_compile() actually works
# by compiling a test function and checking is_jit_compiled().
echo -n "Verifying CinderX JIT... "
CINDERX_CHECK=$(python3 -c "
import cinderjit
def _gate(): return 42
cinderjit.force_compile(_gate)
assert cinderjit.is_jit_compiled(_gate), 'force_compile ran but function not JIT-compiled'
assert _gate() == 42, 'JIT-compiled function returned wrong result'
print('OK (force_compile verified)')
" 2>&1) || {
    echo -e "${RED}FATAL: CinderX JIT not available${RESET}"
    echo "$CINDERX_CHECK"
    echo ""
    echo "Tests CANNOT run without CinderX JIT. Ensure:"
    echo "  1. Python is the CinderX-patched build (not stock Python)"
    echo "  2. cinderjit module is importable and JIT is enabled"
    exit 1
}
echo -e "${GREEN}$CINDERX_CHECK${RESET}"

# Clear results file
> "$RESULTS_FILE"

cd "$PYTHONLIB"

for suite in "${SUITES[@]}"; do
    SUITE_COUNT=$((SUITE_COUNT + 1))
    printf "[%d/%d] %-45s " "$SUITE_COUNT" "${#SUITES[@]}" "$suite"

    # Run with timeout (120s per suite) and capture output
    OUTPUT=$(timeout 120 python3 -m unittest "test_cinderx.$suite" 2>&1)
    TEST_EXIT=$?

    # Parse results from unittest output
    RAN_LINE=$(echo "$OUTPUT" | grep -E '^Ran [0-9]+ test' || echo "")
    # STATUS_LINE is the line after "Ran N tests" — look for OK/FAILED there
    STATUS_LINE=$(echo "$OUTPUT" | grep -E '^(OK|FAILED)' | tail -1 || echo "")

    if [ -z "$RAN_LINE" ]; then
        # No "Ran N tests" line — check crash, timeout, skip, or import error
        if [ $TEST_EXIT -eq 124 ]; then
            # timeout(1) returns 124 when the command times out
            PARTIAL_DOTS=$(echo "$OUTPUT" | grep -c '\.\.\.' || echo 0)
            printf "${RED}TIMEOUT${RESET} (120s, ~%d tests ran before timeout)\n" "$PARTIAL_DOTS"
            FAILED_SUITES+=("$suite")
            TOTAL_FAIL=$((TOTAL_FAIL + 1))
            echo "$OUTPUT" > "/tmp/cinderx_timeout_${suite}.log"
        elif [ $TEST_EXIT -gt 128 ]; then
            # Process killed by signal (SIGSEGV=11, SIGBUS=7, SIGABRT=6)
            SIG=$((TEST_EXIT - 128))
            PARTIAL_DOTS=$(echo "$OUTPUT" | grep -c '\.\.\.' || echo 0)
            printf "${RED}CRASH${RESET} (signal %d, ~%d tests ran before crash)\n" "$SIG" "$PARTIAL_DOTS"
            FAILED_SUITES+=("$suite")
            TOTAL_FAIL=$((TOTAL_FAIL + 1))
            echo "$OUTPUT" > "/tmp/cinderx_crash_${suite}.log"
        elif echo "$OUTPUT" | grep -qE 'SkipTest:'; then
            SKIP_REASON=$(echo "$OUTPUT" | grep -oP 'SkipTest: \K.*' | head -1 || echo "")
            printf "${YELLOW}SKIP${RESET} (%s)\n" "${SKIP_REASON:-module-level skip}"
            SKIPPED_SUITES+=("$suite")
            TOTAL_SKIP=$((TOTAL_SKIP + 1))
        else
            # Genuine error — suite did not execute
            ERR_MSG=$(echo "$OUTPUT" | grep -E '(ModuleNotFoundError|ImportError|SyntaxError|AttributeError):' | tail -1 | head -c 60)
            printf "${RED}ERROR${RESET} (%s)\n" "${ERR_MSG:-did not execute}"
            ERROR_SUITES+=("$suite")
            TOTAL_ERROR=$((TOTAL_ERROR + 1))
            # Save full output for diagnosis
            echo "$OUTPUT" > "/tmp/cinderx_fail_${suite}.log"
        fi
    else
        TESTS=$(echo "$RAN_LINE" | grep -oP '^Ran \K[0-9]+' || echo 0)

        if [ "$TESTS" -eq 0 ]; then
            # Ran 0 tests — treat as skip
            SKIP_REASON=$(echo "$OUTPUT" | grep -oP 'SkipTest: \K.*' | head -1 || echo "")
            printf "${YELLOW}SKIP${RESET} (%s)\n" "${SKIP_REASON:-all tests skipped}"
            SKIPPED_SUITES+=("$suite")
            TOTAL_SKIP=$((TOTAL_SKIP + 1))
        elif echo "$STATUS_LINE" | grep -q 'FAILED'; then
            FAILS=$(echo "$STATUS_LINE" | grep -oP 'failures=\K[0-9]+' || echo 0)
            ERRS=$(echo "$STATUS_LINE" | grep -oP 'errors=\K[0-9]+' || echo 0)
            PASSED=$((TESTS - FAILS - ERRS))
            printf "${RED}FAIL${RESET} (%d pass, %d fail, %d error)\n" "$PASSED" "$FAILS" "$ERRS"
            FAILED_SUITES+=("$suite")
            TOTAL_PASS=$((TOTAL_PASS + PASSED))
            TOTAL_FAIL=$((TOTAL_FAIL + FAILS))
            TOTAL_ERROR=$((TOTAL_ERROR + ERRS))
            # Save full output for diagnosis
            echo "$OUTPUT" > "/tmp/cinderx_fail_${suite}.log"
        elif echo "$STATUS_LINE" | grep -q 'OK'; then
            SKIPS=$(echo "$STATUS_LINE" | grep -oP 'skipped=\K[0-9]+' || echo 0)
            printf "${GREEN}OK${RESET}   (%d pass" "$((TESTS - SKIPS))"
            if [ "$SKIPS" -gt 0 ]; then
                printf ", %d skip" "$SKIPS"
                TOTAL_SKIP=$((TOTAL_SKIP + SKIPS))
            fi
            printf ")\n"
            PASSED_SUITES+=("$suite")
            TOTAL_PASS=$((TOTAL_PASS + TESTS - SKIPS))
        else
            # Unknown status — report as unknown but count test
            printf "${YELLOW}???${RESET}  (%d tests, status unclear)\n" "$TESTS"
            ERROR_SUITES+=("$suite")
        fi
    fi

    # Record per-suite results to CSV
    echo "$suite|$SUITE_COUNT|${TESTS:-0}|${PASSED:-0}|${FAILS:-0}|${ERRS:-0}|${SKIPS:-0}" >> "$RESULTS_FILE"
done

# Summary
echo ""
echo "=== SUMMARY ==="
echo "Finished: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""
printf "  Tests:   %d pass, %d fail, %d error, %d skip\n" "$TOTAL_PASS" "$TOTAL_FAIL" "$TOTAL_ERROR" "$TOTAL_SKIP"
printf "  Suites:  %d pass, %d fail, %d error, %d skip (of %d)\n" \
    "${#PASSED_SUITES[@]}" "${#FAILED_SUITES[@]}" "${#ERROR_SUITES[@]}" "${#SKIPPED_SUITES[@]}" "$SUITE_COUNT"
echo ""

if [ ${#FAILED_SUITES[@]} -gt 0 ]; then
    echo -e "${RED}Failed suites:${RESET}"
    for s in "${FAILED_SUITES[@]}"; do echo "  - $s (log: /tmp/cinderx_fail_${s}.log)"; done
    echo ""
fi

if [ ${#ERROR_SUITES[@]} -gt 0 ]; then
    echo -e "${RED}Error suites (did not run):${RESET}"
    for s in "${ERROR_SUITES[@]}"; do echo "  - $s (log: /tmp/cinderx_fail_${s}.log)"; done
    echo ""
fi

if [ ${#SKIPPED_SUITES[@]} -gt 0 ]; then
    echo -e "${YELLOW}Skipped suites:${RESET}"
    for s in "${SKIPPED_SUITES[@]}"; do echo "  - $s"; done
    echo ""
fi

echo "Results CSV: $RESULTS_FILE"

# ---- CPython Regression Suite ----
if [ -n "$RUN_CPYTHON" ]; then
    echo ""
    echo -e "${BOLD}=== CPython Regression Suite ===${RESET}"
    echo "Running CPython test suite via python3 -m test"
    echo "This validates CinderX does not break standard Python behaviour."
    echo ""

    CPYTHON_RESULTS="/tmp/cpython_test_results_$(date +%Y%m%d_%H%M%S).txt"
    CPYTHON_SKIP_FILE="$CINDERX_ROOT/cinderx/TestScripts/cinder_skip_test.txt"
    CPYTHON_ARM64_FAIL="$CINDERX_ROOT/cinderx/TestScripts/3.12-opt-arm64-failures.txt"

    # Build the ignore list from skip files.
    # Both files contain a mix of formats:
    #   - Bare module names: "test_foo" or "test__opcode"
    #   - Dotted test paths: "test.test_ast.ModuleStateTests.test_subinterpreter"
    #   - Wildcard entries: "test.test__xxsubinterpreters.*"
    #   - CinderX entries: "test_cinderx.test_cinderjit" (ARM64 file only)
    # We extract the CPython module name from all formats and skip the entire
    # module. This is conservative (hides individual test failures within
    # partially-skipped modules) but gives a clean pass/fail signal for
    # detecting NEW regressions.
    CPYTHON_IGNORES=""
    declare -A SEEN_MODULES

    if [ -f "$CPYTHON_SKIP_FILE" ]; then
        while IFS= read -r line; do
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "${line// }" ]] && continue
            if [[ ! "$line" =~ \. ]]; then
                # Bare module name: "test_foo"
                MODULE="$line"
            elif [[ "$line" =~ ^test\.([^.]+) ]]; then
                # Dotted path: "test.test_foo.Class.method" → test_foo
                MODULE="${BASH_REMATCH[1]}"
            else
                continue
            fi
            if [[ -z "${SEEN_MODULES[$MODULE]+x}" ]]; then
                CPYTHON_IGNORES="$CPYTHON_IGNORES -x $MODULE"
                SEEN_MODULES[$MODULE]=1
            fi
        done < "$CPYTHON_SKIP_FILE"
    fi

    # Also skip known ARM64 failures
    if [ -f "$CPYTHON_ARM64_FAIL" ]; then
        while IFS= read -r line; do
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "${line// }" ]] && continue
            if [[ "$line" =~ ^test_cinderx\. ]]; then
                # CinderX test entry — handled by CinderX runner, skip here
                continue
            elif [[ "$line" =~ ^test\.([^.]+) ]]; then
                # Dotted path: "test.test_ctypes" → test_ctypes
                MODULE="${BASH_REMATCH[1]}"
            elif [[ ! "$line" =~ \. ]]; then
                MODULE="$line"
            else
                continue
            fi
            if [[ -z "${SEEN_MODULES[$MODULE]+x}" ]]; then
                CPYTHON_IGNORES="$CPYTHON_IGNORES -x $MODULE"
                SEEN_MODULES[$MODULE]=1
            fi
        done < "$CPYTHON_ARM64_FAIL"
    fi

    # Environment-specific failures (not JIT-related, not in CinderX skip lists)
    # test_pdb: test_basic_completion fails due to ANSI colour codes in readline
    # test_venv: test_upgrade_dependencies fails due to pip upgrade in venv env
    for ENV_SKIP in test_pdb test_venv; do
        if [[ -z "${SEEN_MODULES[$ENV_SKIP]+x}" ]]; then
            CPYTHON_IGNORES="$CPYTHON_IGNORES -x $ENV_SKIP"
            SEEN_MODULES[$ENV_SKIP]=1
        fi
    done

    # Run CPython tests with timeout per test (60s) and overall timeout (30min)
    # Use --failfast for initial runs, remove for full sweep
    echo "Skip file: $CPYTHON_SKIP_FILE"
    echo "ARM64 failures: $CPYTHON_ARM64_FAIL"
    echo "Modules skipped: ${#SEEN_MODULES[@]}"
    echo ""

    # Run and capture output
    timeout 1800 python3 -m test \
        --timeout 60 \
        -j4 \
        $CPYTHON_IGNORES \
        2>&1 | tee "$CPYTHON_RESULTS" | tail -20

    CPYTHON_EXIT=$?

    echo ""
    echo "CPython results saved to: $CPYTHON_RESULTS"

    if [ $CPYTHON_EXIT -eq 0 ]; then
        echo -e "${GREEN}CPython regression suite: PASS${RESET}"
    elif [ $CPYTHON_EXIT -eq 124 ]; then
        echo -e "${YELLOW}CPython regression suite: TIMEOUT (30 min limit)${RESET}"
    else
        echo -e "${RED}CPython regression suite: FAIL (exit $CPYTHON_EXIT)${RESET}"
    fi
fi

# Exit code: 0 if all suites executed (failures ok), 1 if any suite errored (didn't execute)
if [ ${#ERROR_SUITES[@]} -gt 0 ]; then
    exit 1
else
    exit 0
fi
