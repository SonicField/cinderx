#!/bin/bash
# Phase 2 dual-failure verification for cinderx-explicit skip entries.
#
# Per gatekeeper 2026-04-22 05:43:25Z workflow:
#   1. For each non-comment line in cinderx/TestScripts/cinder_skip_test.txt
#   2. Run under vanilla CPython 3.12.13 (no cinderx)
#   3. Run under cinderx-built python
#   4. Record exit codes; gatekeeper applies dual-failure rule downstream.
#
# Output: TSV matrix at investigations/probes/cpython_skip_dual_failure_matrix.tsv
#         entry \t vanilla_exit \t cinderx_exit \t classification
#
# Usage: ./investigations/probes/cpython_skip_dual_failure_verifier.sh
#
# NOT to be invoked while ABBA is in flight — it spawns ~85 python3
# processes, each ~10s, which would skew ABBA timing measurements.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKIP_FILE="$REPO_ROOT/cinderx/TestScripts/cinder_skip_test.txt"
MATRIX="$REPO_ROOT/investigations/probes/cpython_skip_dual_failure_matrix.tsv"
TS=$(date +%s)
LOG_DIR="/tmp/cpython_skip_dual_$TS"
mkdir -p "$LOG_DIR"

VANILLA_PY="/usr/local/fbcode/platform010/bin/python3.12"
CINDERX_PY="/data/users/alexturner/venv/bin/python3"
CINDERX_PYTHONPATH="$REPO_ROOT/cinderx/PythonLib"

if [ ! -x "$VANILLA_PY" ]; then
    echo "FATAL: vanilla CPython not at $VANILLA_PY"
    exit 1
fi
if [ ! -x "$CINDERX_PY" ]; then
    echo "FATAL: cinderx python not at $CINDERX_PY"
    exit 1
fi

# Header row (not appended to per-entry matrix, written once)
echo -e "entry\tvanilla_exit\tcinderx_exit\tclassification" > "$MATRIX"

# Convert a skip entry to a runnable unittest path.
#   test.test_X.ClassName.method  →  test.test_X.ClassName.method
#   test.test_X.ClassName.*       →  test.test_X.ClassName  (run whole class)
#   test.test_X.*                 →  test.test_X            (run whole module)
#   test_X                        →  test.test_X            (assume CPython prefix)
resolve_entry() {
    local entry="$1"
    # Strip trailing .* (unittest treats class without .* as the class itself)
    entry="${entry%.\*}"
    # If it doesn't start with test., add the prefix (CPython stdlib test module convention)
    if [[ "$entry" != test.* && "$entry" != test_* ]]; then
        entry="test.$entry"
    elif [[ "$entry" == test_* ]]; then
        entry="test.$entry"
    fi
    echo "$entry"
}

count=0
total=$(grep -cv "^#\|^$" "$SKIP_FILE")
echo "Phase 2 verifier: $total entries to check" >&2

while IFS= read -r line; do
    # Skip blanks + comments
    [[ "$line" =~ ^# ]] && continue
    [[ -z "$line" ]] && continue

    count=$((count + 1))
    target=$(resolve_entry "$line")

    # Run under vanilla CPython
    timeout 30 "$VANILLA_PY" -m unittest "$target" \
        > "$LOG_DIR/vanilla_${count}.log" 2>&1
    vanilla_exit=$?

    # Run under cinderx-built python (no JIT env, just available)
    PYTHONPATH="$CINDERX_PYTHONPATH" timeout 30 "$CINDERX_PY" -m unittest "$target" \
        > "$LOG_DIR/cinderx_${count}.log" 2>&1
    cinderx_exit=$?

    # Classify per dual-failure rule (gatekeeper 05:43:25Z):
    #   vanilla != 0 → environmental, SKIP APPROVED
    #   vanilla == 0, cinderx != 0 → CinderX bug, SKIP REJECTED
    #   vanilla == 0, cinderx == 0 → both pass, skip is STALE (test now works in both)
    #   vanilla != 0, cinderx == 0 → unusual; cinderx is more permissive than vanilla
    if [ "$vanilla_exit" -ne 0 ] && [ "$cinderx_exit" -ne 0 ]; then
        classification="SKIP_APPROVED_environmental"
    elif [ "$vanilla_exit" -eq 0 ] && [ "$cinderx_exit" -ne 0 ]; then
        classification="SKIP_REJECTED_cinderx_bug"
    elif [ "$vanilla_exit" -eq 0 ] && [ "$cinderx_exit" -eq 0 ]; then
        classification="STALE_skip_test_now_passes_both"
    else
        classification="UNUSUAL_cinderx_more_permissive"
    fi

    printf "%s\t%d\t%d\t%s\n" "$line" "$vanilla_exit" "$cinderx_exit" "$classification" >> "$MATRIX"
    printf "[%d/%d] %s → %s\n" "$count" "$total" "$line" "$classification" >&2
done < "$SKIP_FILE"

echo "Phase 2 verifier: $count entries processed" >&2
echo "Matrix: $MATRIX" >&2
echo "Per-entry logs: $LOG_DIR" >&2
echo "Summary:" >&2
cut -f4 "$MATRIX" | tail -n +2 | sort | uniq -c | sort -rn >&2
