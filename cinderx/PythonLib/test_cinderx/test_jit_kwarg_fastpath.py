"""Correctness tests for JITRT_CallWithKeywordArgs fast path.

Tests that the kwarg-to-positional fast path produces correct results
for all call patterns, and that non-matching patterns correctly fall
through to the slow path.
"""
import sys
sys.path.insert(0, 'cinderx/PythonLib')
import _cinderx
import cinderjit

# Force compilation
cinderjit.auto()

# Test functions
def add(a, b):
    return a + b

def add3(a, b, c):
    return a + b + c

def with_defaults(a, b=10, c=20):
    return a + b + c

def posonly(a, b, /, c, d):
    return a + b + c + d

def varargs(a, b, *args):
    return a + b + sum(args)

def varkw(a, b, **kwargs):
    return a + b + sum(kwargs.values())

def kwonly(a, *, b):
    return a + b

# Warmup all functions for JIT compilation
for _ in range(1100):
    add(1, 2)
    add3(1, 2, 3)
    with_defaults(1, 2, 3)
    with_defaults(1)
    posonly(1, 2, c=3, d=4)
    varargs(1, 2, 3)
    varkw(1, 2, x=3)
    kwonly(1, b=2)

# ============================================================
# TEST 1: All-kwarg call matching params in order → fast path
# ============================================================
result = add(a=10, b=20)
assert result == 30, f"Test 1 failed: add(a=10, b=20) = {result}, expected 30"

result = add3(a=1, b=2, c=3)
assert result == 6, f"Test 1b failed: add3(a=1,b=2,c=3) = {result}, expected 6"
print("Test 1 PASSED: all-kwarg in order")

# ============================================================
# TEST 2: All-kwarg with wrong order → slow path, correct result
# ============================================================
result = add(b=20, a=10)
assert result == 30, f"Test 2 failed: add(b=20, a=10) = {result}, expected 30"

result = add3(c=3, a=1, b=2)
assert result == 6, f"Test 2b failed: add3(c=3,a=1,b=2) = {result}, expected 6"
print("Test 2 PASSED: wrong kwarg order")

# ============================================================
# TEST 3: Mixed positional + kwarg → fast path (if in order)
# ============================================================
result = add(10, b=20)
assert result == 30, f"Test 3 failed: add(10, b=20) = {result}, expected 30"

result = add3(1, b=2, c=3)
assert result == 6, f"Test 3b failed: add3(1,b=2,c=3) = {result}, expected 6"

result = add3(1, 2, c=3)
assert result == 6, f"Test 3c failed: add3(1,2,c=3) = {result}, expected 6"
print("Test 3 PASSED: mixed positional + kwarg")

# ============================================================
# TEST 4: Function with defaults, partial kwargs → slow path
# ============================================================
result = with_defaults(1)
assert result == 31, f"Test 4a failed: with_defaults(1) = {result}, expected 31"

result = with_defaults(1, b=5)
assert result == 26, f"Test 4b failed: with_defaults(1,b=5) = {result}, expected 26"

result = with_defaults(a=1, b=5, c=10)
assert result == 16, f"Test 4c failed: with_defaults(a=1,b=5,c=10) = {result}, expected 16"
print("Test 4 PASSED: defaults with partial kwargs")

# ============================================================
# TEST 5: Positional-only params (/) with kwargs for remaining
# ============================================================
result = posonly(1, 2, c=3, d=4)
assert result == 10, f"Test 5 failed: posonly(1,2,c=3,d=4) = {result}, expected 10"
print("Test 5 PASSED: positional-only + kwargs")

# ============================================================
# TEST 6: Dict unpacking (non-interned keys) → slow path
# ============================================================
d = {'a': 10, 'b': 20}
result = add(**d)
assert result == 30, f"Test 6 failed: add(**d) = {result}, expected 30"
print("Test 6 PASSED: dict unpacking")

# ============================================================
# Additional: *args and **kwargs functions → slow path
# ============================================================
result = varargs(a=1, b=2)
assert result == 3, f"Test 7a failed: varargs(a=1,b=2) = {result}, expected 3"

result = varkw(a=1, b=2, x=10)
assert result == 13, f"Test 7b failed: varkw(a=1,b=2,x=10) = {result}, expected 13"

result = kwonly(a=1, b=2)
assert result == 3, f"Test 7c failed: kwonly(a=1,b=2) = {result}, expected 3"
print("Test 7 PASSED: *args, **kwargs, kw-only (all slow path)")

print("\n=== All kwarg fast path correctness tests PASSED ===")
