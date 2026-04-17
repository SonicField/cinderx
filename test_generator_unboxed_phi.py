"""Adversarial test: generator that yields mid-loop with unboxed integer Phi.

Tests the interaction between PhiUnboxing and generator yield/resume.
When a generator yields while a loop accumulator is unboxed (CInt64),
the spill to GenDataFooter must preserve the value correctly, and
resume must restore it. This exercises the deopt path for CInt64 values
in generator FrameState.
"""
import cinderjit
import sys


def test_generator_integer_accumulate():
    """Generator that accumulates integers and yields mid-loop."""
    def gen_accumulate(n):
        total = 0
        for i in range(n):
            total += i
            if i % 10 == 9:
                yield total
        yield total

    cinderjit.force_compile(gen_accumulate)

    # Collect all yielded values
    results = list(gen_accumulate(100))
    # Should yield at i=9,19,29,...,99 plus final
    expected_partials = []
    total = 0
    for i in range(100):
        total += i
        if i % 10 == 9:
            expected_partials.append(total)
    expected_partials.append(total)  # final yield

    assert results == expected_partials, \
        f"Expected {expected_partials}, got {results}"


def test_generator_integer_overflow_mid_loop():
    """Generator where integer overflow occurs DURING iteration."""
    def gen_overflow(start, step, n):
        total = start
        for i in range(n):
            total += step
            yield total

    cinderjit.force_compile(gen_overflow)

    # Start near maxsize, step will cause overflow
    start = sys.maxsize - 5
    results = list(gen_overflow(start, 1, 10))
    expected = [start + i + 1 for i in range(10)]
    assert results == expected, \
        f"Overflow test: expected {expected}, got {results}"


def test_generator_resume_after_overflow():
    """Generator that overflows, yields, and continues with bignum."""
    def gen_bignum(n):
        total = sys.maxsize - 2
        for i in range(n):
            total += 1
            yield total

    cinderjit.force_compile(gen_bignum)

    results = list(gen_bignum(10))
    expected = [sys.maxsize - 2 + i + 1 for i in range(10)]
    assert results == expected, \
        f"Bignum resume: expected {expected}, got {results}"


def test_nested_generators_integer():
    """Nested generators where inner yields integers to outer accumulator."""
    def inner(n):
        for i in range(n):
            yield i

    def outer(n):
        total = 0
        for val in inner(n):
            total += val
            if val % 20 == 19:
                yield total
        yield total

    cinderjit.force_compile(inner)
    cinderjit.force_compile(outer)

    results = list(outer(100))
    # Verify against non-JIT computation
    expected = []
    total = 0
    for val in range(100):
        total += val
        if val % 20 == 19:
            expected.append(total)
    expected.append(total)

    assert results == expected, \
        f"Nested gen: expected {expected}, got {results}"


def test_generator_mixed_ops():
    """Generator with both += and regular + in the loop."""
    def gen_mixed(n):
        a = 0
        b = 1
        for _ in range(n):
            a, b = b, a + b
            if b > 100:
                yield b

    cinderjit.force_compile(gen_mixed)

    results = list(gen_mixed(20))
    # Compute expected fibonacci values > 100
    a, b = 0, 1
    expected = []
    for _ in range(20):
        a, b = b, a + b
        if b > 100:
            expected.append(b)

    assert results == expected, \
        f"Mixed ops: expected {expected}, got {results}"


if __name__ == "__main__":
    test_generator_integer_accumulate()
    print("test_generator_integer_accumulate: PASS")

    test_generator_integer_overflow_mid_loop()
    print("test_generator_integer_overflow_mid_loop: PASS")

    test_generator_resume_after_overflow()
    print("test_generator_resume_after_overflow: PASS")

    test_nested_generators_integer()
    print("test_nested_generators_integer: PASS")

    test_generator_mixed_ops()
    print("test_generator_mixed_ops: PASS")

    print("All generator unboxed Phi tests: PASS")
