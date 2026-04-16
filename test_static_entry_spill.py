"""Regression test for static entry path stack allocation (commit 36be9d93).

The JIT has two entry points: generic (via vectorcall) and static (direct
JIT-to-JIT calls). The static entry path previously skipped stack frame
allocation (allocateHeaderAndSpillSpace), causing spill slot writes to
corrupt the caller's stack frame.

This test exercises: spill slots on static entry, deep recursion, and
many compiled functions — the three conditions that triggered the crash.
"""
import cinderjit


def test_recursive_spill():
    """Recursive function with many args to force spill slots."""
    def recursive_spill(n, a=0, b=0, c=0, d=0, e=0, f=0):
        if n <= 0:
            return a + b + c + d + e + f
        return recursive_spill(n - 1, a + 1, b + 2, c + 3, d + 4, e + 5, f + 6)

    cinderjit.force_compile(recursive_spill)

    result = recursive_spill(500)
    expected = 500 * (1 + 2 + 3 + 4 + 5 + 6)  # 10500
    assert result == expected, f"Expected {expected}, got {result}"


def test_recursive_spill_with_many_compilations():
    """Same test but with many other functions compiled first."""
    def recursive_spill(n, a=0, b=0, c=0, d=0, e=0, f=0):
        if n <= 0:
            return a + b + c + d + e + f
        return recursive_spill(n - 1, a + 1, b + 2, c + 3, d + 4, e + 5, f + 6)

    # Compile many functions to increase code cache pressure
    def make_fn(i):
        def fn(x):
            return x + i
        return fn

    fns = [make_fn(i) for i in range(50)]
    for fn in fns:
        cinderjit.force_compile(fn)

    cinderjit.force_compile(recursive_spill)
    result = recursive_spill(500)
    expected = 500 * 21
    assert result == expected, f"Expected {expected}, got {result}"


if __name__ == "__main__":
    test_recursive_spill()
    print("test_recursive_spill: PASS")
    test_recursive_spill_with_many_compilations()
    print("test_recursive_spill_with_many_compilations: PASS")
    print("All static entry tests: PASS")
