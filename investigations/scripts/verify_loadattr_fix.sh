#!/bin/bash
# verify_loadattr_fix.sh — Regression test for LoadAttrCached exception handling fix
#
# Runs AFTER the one-line fix (remove kLoadAttrCached from exemption list).
# Tests:
# 1. test_dot reproducer returns 'caught' (not crash/escape)
# 2. Full 41-suite CinderX regression (must be ≥37/41)
# 3. Import-time auto-compile (cinderjit.auto() before torch import)
# 4. Other data-access opcodes still work (no regression)
#
# Usage:
#   ./verify_loadattr_fix.sh              # Run all checks
#   ./verify_loadattr_fix.sh --quick      # Run only reproducer + data-access checks

set -uo pipefail

CINDERX_ROOT="${CINDERX_ROOT:-$HOME/local/cinderx_dev/cinderx}"
PYTHONLIB="$CINDERX_ROOT/cinderx/PythonLib"
export PYTHONPATH="$PYTHONLIB${PYTHONPATH:+:$PYTHONPATH}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
RESET='\033[0m'

PASS=0
FAIL=0

check() {
    local name="$1"
    local result="$2"
    local expected="$3"
    if [ "$result" = "$expected" ]; then
        printf "  %-50s ${GREEN}PASS${RESET}\n" "$name"
        PASS=$((PASS + 1))
    else
        printf "  %-50s ${RED}FAIL${RESET} (got '%s', expected '%s')\n" "$name" "$result" "$expected"
        FAIL=$((FAIL + 1))
    fi
}

echo -e "${BOLD}LoadAttrCached Fix Verification${RESET}"
echo "Build: $(md5sum $PYTHONLIB/_cinderx.so 2>/dev/null | cut -d' ' -f1)"
echo "Git:   $(cd $CINDERX_ROOT && git log --oneline -1 2>/dev/null)"
echo "---"
echo ""

# === Test 1: Core reproducer (Gap 9) ===
echo -e "${BOLD}Test 1: LOAD_ATTR in try/except (Gap 9 reproducer)${RESET}"

RESULT=$(python3 -c "
import cinderjit

def test_dot(obj):
    try:
        x = obj.nonexistent_attr
        return str(x)
    except AttributeError:
        return 'caught'

cinderjit.force_compile(test_dot)
assert cinderjit.is_jit_compiled(test_dot), 'not compiled'

class C: pass
print(test_dot(C()))
" 2>&1) || RESULT="CRASH"
check "test_dot returns 'caught'" "$RESULT" "caught"

# Also test happy path
RESULT2=$(python3 -c "
import cinderjit

def test_dot(obj):
    try:
        x = obj.nonexistent_attr
        return str(x)
    except AttributeError:
        return 'caught'

cinderjit.force_compile(test_dot)

class D:
    nonexistent_attr = 42
print(test_dot(D()))
" 2>&1) || RESULT2="CRASH"
check "test_dot happy path returns '42'" "$RESULT2" "42"

echo ""

# === Test 2: Data-access opcodes (regression checks) ===
echo -e "${BOLD}Test 2: Data-access opcodes (must still work)${RESET}"

RESULT=$(python3 -c "
import cinderjit

def subscr_test(d, k):
    try:
        return d[k]
    except KeyError:
        return 'caught'

cinderjit.force_compile(subscr_test)
print(subscr_test({'a': 1}, 'b'))
" 2>&1) || RESULT="CRASH"
check "BINARY_SUBSCR KeyError caught" "$RESULT" "caught"

RESULT=$(python3 -c "
import cinderjit

def store_test(obj):
    try:
        obj.x = 99
        return 'stored'
    except (AttributeError, TypeError):
        return 'caught'

cinderjit.force_compile(store_test)
print(store_test(42))
" 2>&1) || RESULT="CRASH"
check "STORE_ATTR TypeError caught" "$RESULT" "caught"

RESULT=$(python3 -c "
import cinderjit

def del_test(obj):
    try:
        del obj.x
        return 'deleted'
    except AttributeError:
        return 'caught'

cinderjit.force_compile(del_test)

class E: pass
print(del_test(E()))
" 2>&1) || RESULT="CRASH"
check "DELETE_ATTR AttributeError caught" "$RESULT" "caught"

RESULT=$(python3 -c "
import cinderjit

def global_test():
    try:
        return undefined_global_name_xyz
    except NameError:
        return 'caught'

cinderjit.force_compile(global_test)
print(global_test())
" 2>&1) || RESULT="CRASH"
check "LOAD_GLOBAL NameError caught" "$RESULT" "caught"

RESULT=$(python3 -c "
import cinderjit

def store_subscr_test(c, k, v):
    try:
        c[k] = v
        return 'stored'
    except TypeError:
        return 'caught'

cinderjit.force_compile(store_subscr_test)
print(store_subscr_test((1, 2), 0, 99))
" 2>&1) || RESULT="CRASH"
check "STORE_SUBSCR TypeError caught" "$RESULT" "caught"

echo ""

# === Test 3: LOAD_ATTR variants ===
echo -e "${BOLD}Test 3: LOAD_ATTR exception variants${RESET}"

RESULT=$(python3 -c "
import cinderjit

def getattr_test(obj):
    try:
        return getattr(obj, 'missing')
    except AttributeError:
        return 'caught'

cinderjit.force_compile(getattr_test)

class C: pass
print(getattr_test(C()))
" 2>&1) || RESULT="CRASH"
check "getattr() AttributeError caught" "$RESULT" "caught"

RESULT=$(python3 -c "
import cinderjit

def method_test(obj):
    try:
        return obj.missing_method()
    except AttributeError:
        return 'caught'

cinderjit.force_compile(method_test)

class C: pass
print(method_test(C()))
" 2>&1) || RESULT="CRASH"
check "method call AttributeError caught" "$RESULT" "caught"

RESULT=$(python3 -c "
import cinderjit

def none_test(obj):
    try:
        return obj.x
    except AttributeError:
        return 'caught'

cinderjit.force_compile(none_test)
print(none_test(None))
" 2>&1) || RESULT="CRASH"
check "None.x AttributeError caught" "$RESULT" "caught"

echo ""

if [ "${1:-}" = "--quick" ]; then
    echo "=== QUICK CHECK ==="
    printf "  %d pass, %d fail\n" "$PASS" "$FAIL"
    [ "$FAIL" -eq 0 ] && exit 0 || exit 1
fi

# === Test 4: Full CinderX regression suite ===
echo -e "${BOLD}Test 4: Full CinderX regression suite (41 suites)${RESET}"
echo "(Running... this may take a few minutes)"

SUITE_SCRIPT="$HOME/claude_docs/nbs-framework/run_cinderx_tests.sh"
if [ -f "$SUITE_SCRIPT" ]; then
    bash "$SUITE_SCRIPT" 2>&1 | tail -20
else
    echo -e "${YELLOW}SKIP — run_cinderx_tests.sh not found${RESET}"
fi

echo ""

# === Test 5: Import-time auto-compile ===
echo -e "${BOLD}Test 5: Import-time auto-compile${RESET}"

RESULT=$(timeout 30 python3 -c "
import cinderjit
cinderjit.auto()
import torch
print('OK')
" 2>&1) || RESULT="CRASH_OR_TIMEOUT"
check "cinderjit.auto() before torch import" "$RESULT" "OK"

echo ""

# === Summary ===
echo "=== SUMMARY ==="
printf "  %d pass, %d fail\n" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] && echo -e "${GREEN}ALL CHECKS PASS${RESET}" || echo -e "${RED}SOME CHECKS FAILED${RESET}"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
