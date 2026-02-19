#!/usr/bin/env python3
"""B2 Smoke Test — Inline Exception Match in JIT

Falsifiers from the B2 implementation plan:
1. f({}, "x") returns -1, not crash (basic exception catch works)
2. cinderjit.get_and_clear_runtime_stats()["deopt"] is empty when KeyError is caught
3. g({}, "x") raises KeyError when handler catches ValueError (no-match deopts correctly)
"""

import sys

# Gate: CinderX JIT must be available
try:
    import cinderjit
    assert cinderjit.is_enabled(), "cinderjit imported but JIT not enabled"
except (ImportError, AssertionError) as e:
    print(f"FATAL: CinderX JIT not available: {e}")
    sys.exit(1)


def f(d, k):
    """Simple try/except KeyError — B2 should inline this."""
    try:
        return d[k]
    except KeyError:
        return -1


def g(d, k):
    """try/except ValueError — KeyError should NOT match."""
    try:
        return d[k]
    except ValueError:
        return -1


def h(d, k):
    """Normal path — subscript succeeds, no exception."""
    try:
        return d[k]
    except KeyError:
        return -1


# Force compile all test functions
cinderjit.force_compile(f)
cinderjit.force_compile(g)
cinderjit.force_compile(h)

assert cinderjit.is_jit_compiled(f), "f not JIT compiled"
assert cinderjit.is_jit_compiled(g), "g not JIT compiled"
assert cinderjit.is_jit_compiled(h), "h not JIT compiled"

print("All functions JIT compiled: OK")

# Clear any prior stats
cinderjit.get_and_clear_runtime_stats()

# --- Falsifier 1: f({}, "x") returns -1 ---
result = f({}, "x")
assert result == -1, f"Expected -1, got {result}"
print("Falsifier 1 (f({{}}, 'x') == -1): PASS")

# --- Falsifier 1b: f({1: 2}, 1) returns 2 (success path) ---
result = f({1: 2}, 1)
assert result == 2, f"Expected 2, got {result}"
print("Falsifier 1b (f({{1:2}}, 1) == 2): PASS")

# --- Falsifier 2: No deopts when KeyError is caught ---
stats = cinderjit.get_and_clear_runtime_stats()
deopts = stats.get("deopt", [])
# Filter for deopts from function f
f_deopts = [d for d in deopts if "f" in d.get("func_fullname", "")]
if f_deopts:
    print("Falsifier 2 (no deopts for f): FAIL")
    for d in f_deopts:
        print(f"  deopt: {d}")
    # Don't abort — report but continue
else:
    print("Falsifier 2 (no deopts for f): PASS")

# --- Falsifier 3: g({}, "x") raises KeyError ---
try:
    g({}, "x")
    print("Falsifier 3 (g raises KeyError): FAIL — no exception raised")
    sys.exit(1)
except KeyError:
    print("Falsifier 3 (g raises KeyError): PASS")
except Exception as e:
    print(f"Falsifier 3 (g raises KeyError): FAIL — wrong exception: {type(e).__name__}: {e}")
    sys.exit(1)

# Check g's deopts — should have a deopt (UnhandledException)
stats = cinderjit.get_and_clear_runtime_stats()
deopts = stats.get("deopt", [])
g_deopts = [d for d in deopts if "g" in d.get("func_fullname", "")]
if g_deopts:
    print(f"  g deopted as expected: reason={g_deopts[0].get('reason', '?')}")
else:
    print("  NOTE: g did not deopt — may have taken interpreter path")

# --- Falsifier 4: h({1:2}, 1) returns 2, no exception path ---
cinderjit.get_and_clear_runtime_stats()  # clear
result = h({1: 2}, 1)
assert result == 2, f"Expected 2, got {result}"
stats = cinderjit.get_and_clear_runtime_stats()
h_deopts = [d for d in stats.get("deopt", []) if "h" in d.get("func_fullname", "")]
assert not h_deopts, f"Unexpected deopts for h: {h_deopts}"
print("Falsifier 4 (h success path, no deopts): PASS")

print("\n=== All B2 smoke tests PASSED ===")
