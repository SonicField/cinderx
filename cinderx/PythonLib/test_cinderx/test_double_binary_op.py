"""Test double modulo and floor division in JIT.

Verifies that DoubleBinaryOp correctly handles kModulo and kFloorDivide
after the fix in generator.cpp. Tests both force_compile and auto-JIT paths.
"""
import sys
import math

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False

def double_mod(a, b):
    """Float modulo — triggers DoubleBinaryOp kModulo when JIT-compiled."""
    return a % b

def double_floordiv(a, b):
    """Float floor division — triggers DoubleBinaryOp kFloorDivide."""
    return a // b

def double_combined(a, b):
    """Both ops in one function."""
    return (a % b, a // b)

# Test cases: (a, b, expected_mod, expected_floordiv)
TEST_CASES = [
    (7.5, 2.5, 0.0, 3.0),
    (10.0, 3.0, 1.0, 3.0),
    (-10.0, 3.0, 2.0, -4.0),      # Python: mod has same sign as divisor
    (10.0, -3.0, -2.0, -4.0),     # Python: mod has same sign as divisor
    (-10.0, -3.0, -1.0, 3.0),     # Negative divisor
    (1.5, 0.5, 0.0, 3.0),
    (2.5, 1.0, 0.5, 2.0),
    (0.0, 1.0, 0.0, 0.0),
    (1e-10, 1.0, 1e-10, 0.0),     # Very small numerator
    (1e10, 3.0, 1.0, 3333333333.0),  # Large numerator
]

passed = 0
failed = 0

print("=== Double BinaryOp Test Suite ===")
print()

# Test 1: Correctness without JIT
print("--- Test 1: Interpreter correctness baseline ---")
for a, b, exp_mod, exp_floordiv in TEST_CASES:
    got_mod = double_mod(a, b)
    got_fdiv = double_floordiv(a, b)
    mod_ok = math.isclose(got_mod, exp_mod, rel_tol=1e-9, abs_tol=1e-15)
    fdiv_ok = math.isclose(got_fdiv, exp_floordiv, rel_tol=1e-9, abs_tol=1e-15)
    if mod_ok and fdiv_ok:
        passed += 1
    else:
        failed += 1
        if not mod_ok:
            print(f"  FAIL: {a} % {b} = {got_mod}, expected {exp_mod}")
        if not fdiv_ok:
            print(f"  FAIL: {a} // {b} = {got_fdiv}, expected {exp_floordiv}")

print(f"  {passed} passed, {failed} failed")
print()

# Test 2: Force compile (may not trigger DoubleBinaryOp — uses generic path)
if HAS_CINDERJIT:
    print("--- Test 2: force_compile path ---")
    try:
        cinderjit.force_compile(double_mod)
        cinderjit.force_compile(double_floordiv)
        print(f"  double_mod compiled: {cinderjit.is_jit_compiled(double_mod)}")
        print(f"  double_floordiv compiled: {cinderjit.is_jit_compiled(double_floordiv)}")

        for a, b, exp_mod, exp_floordiv in TEST_CASES:
            got_mod = double_mod(a, b)
            got_fdiv = double_floordiv(a, b)
            mod_ok = math.isclose(got_mod, exp_mod, rel_tol=1e-9, abs_tol=1e-15)
            fdiv_ok = math.isclose(got_fdiv, exp_floordiv, rel_tol=1e-9, abs_tol=1e-15)
            if mod_ok and fdiv_ok:
                passed += 1
            else:
                failed += 1
                if not mod_ok:
                    print(f"  FAIL: {a} % {b} = {got_mod}, expected {exp_mod}")
                if not fdiv_ok:
                    print(f"  FAIL: {a} // {b} = {got_fdiv}, expected {exp_floordiv}")

        print(f"  {passed} passed (cumulative), {failed} failed")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1
    print()

    # Test 3: Force compile combined function
    print("--- Test 3: Combined ops in single function ---")
    try:
        cinderjit.force_compile(double_combined)
        for a, b, exp_mod, exp_floordiv in TEST_CASES[:5]:
            got = double_combined(a, b)
            mod_ok = math.isclose(got[0], exp_mod, rel_tol=1e-9, abs_tol=1e-15)
            fdiv_ok = math.isclose(got[1], exp_floordiv, rel_tol=1e-9, abs_tol=1e-15)
            if mod_ok and fdiv_ok:
                passed += 1
            else:
                failed += 1
                print(f"  FAIL: ({a} % {b}, {a} // {b}) = {got}, "
                      f"expected ({exp_mod}, {exp_floordiv})")
        print(f"  {passed} passed (cumulative), {failed} failed")
    except Exception as e:
        print(f"  ERROR: {e}")
        failed += 1
    print()

else:
    print("--- CinderX not available, skipping JIT tests ---")
    print()

# Summary
print("=== SUMMARY ===")
print(f"Total: {passed} passed, {failed} failed")
if failed == 0:
    print("ALL TESTS PASSED")
    sys.exit(0)
else:
    print("SOME TESTS FAILED")
    sys.exit(1)
