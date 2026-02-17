# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# Tests for aarch64 JIT generator saved-IP crash vectors.
#
# On aarch64, generators reassign FP (x29) to GenDataFooter on the heap
# after the prologue. The FP-relative saved-IP store (ADR+STR at
# [FP+saved_ip_fp_offset]) then writes into heap memory instead of the
# stack, corrupting generator state.
#
# These tests exercise every code path where this corruption can manifest.
# Each test should:
#   - PASS when generators are deopt'd (interpreted) or when the
#     saved-IP store is correctly skipped/redirected for generators
#   - CRASH (SIGSEGV/SIGBUS) without the fix on aarch64
#
# pyre-unsafe

import asyncio
import platform
import sys
import traceback
import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


def force_compile(func):
    """Force JIT compilation if cinderjit is available."""
    if HAS_CINDERJIT:
        cinderjit.force_compile(func)
    return func


def is_aarch64():
    return platform.machine() == "aarch64"


# Helper functions that will be JIT-compiled and called from generators.
def add3(a, b, c):
    return a + b + c


def identity(x):
    return x


def double(x):
    return x * 2


def raise_if_negative(x):
    if x < 0:
        raise ValueError(f"negative: {x}")
    return x


class TestGeneratorCallsJitFunction(unittest.TestCase):
    """Generator body calls a JIT-compiled function — triggers ADR+STR."""

    def test_generator_calls_jit_function_simple(self):
        """Generator yields result of a JIT'd function call."""
        def gen():
            yield add3(1, 2, 3)
            yield add3(4, 5, 6)

        force_compile(add3)
        force_compile(gen)

        g = gen()
        self.assertEqual(next(g), 6)
        self.assertEqual(next(g), 15)
        with self.assertRaises(StopIteration):
            next(g)

    def test_generator_calls_jit_function_many_args(self):
        """Generator calls JIT'd function with 5 args (exercises arg buffer)."""
        def add5(a, b, c, d, e):
            return a + b + c + d + e

        def gen():
            for i in range(10):
                yield add5(i, i+1, i+2, i+3, i+4)

        force_compile(add5)
        force_compile(gen)

        results = list(gen())
        expected = [sum(range(i, i+5)) for i in range(10)]
        self.assertEqual(results, expected)

    def test_generator_calls_jit_function_with_star_args(self):
        """Generator calls JIT'd function using *args unpacking."""
        def summer(*args):
            return sum(args)

        def gen():
            for i in range(5):
                args = list(range(i + 1))
                yield summer(*args)

        force_compile(summer)
        force_compile(gen)

        results = list(gen())
        expected = [sum(range(i + 1)) for i in range(5)]
        self.assertEqual(results, expected)

    def test_generator_calls_jit_function_with_kwargs(self):
        """Generator calls JIT'd function using **kwargs."""
        def kwfunc(a=0, b=0, c=0):
            return a + b + c

        def gen():
            yield kwfunc(a=1, b=2, c=3)
            yield kwfunc(a=10, b=20)
            yield kwfunc(c=100)

        force_compile(kwfunc)
        force_compile(gen)

        results = list(gen())
        self.assertEqual(results, [6, 30, 100])

    def test_generator_calls_multiple_jit_functions(self):
        """Generator calls multiple JIT'd functions per iteration."""
        def gen():
            for i in range(5):
                a = identity(i)
                b = double(a)
                c = add3(a, b, i)
                yield c

        force_compile(identity)
        force_compile(double)
        force_compile(add3)
        force_compile(gen)

        results = list(gen())
        # i=0: a=0, b=0, c=0+0+0=0; i=1: a=1, b=2, c=1+2+1=4; i=2: a=2, b=4, c=2+4+2=8; etc.
        expected = [0, 4, 8, 12, 16]
        self.assertEqual(results, expected)


class TestGeneratorThrow(unittest.TestCase):
    """gen.throw() triggers frame reification — reads saved-IP."""

    def test_throw_with_jit_call_in_body(self):
        """Throw into a generator that has called a JIT'd function."""
        def gen():
            x = identity(42)
            try:
                yield x
            except ValueError:
                yield identity(-1)

        force_compile(identity)
        force_compile(gen)

        g = gen()
        self.assertEqual(next(g), 42)
        self.assertEqual(g.throw(ValueError, "test"), -1)

    def test_throw_propagates_through_generator(self):
        """Throw propagates when generator doesn't catch it."""
        def gen():
            yield identity(1)
            yield identity(2)

        force_compile(identity)
        force_compile(gen)

        g = gen()
        next(g)
        with self.assertRaises(RuntimeError):
            g.throw(RuntimeError, "uncaught")

    def test_throw_into_yield_from(self):
        """Throw into generator using yield from."""
        def inner():
            try:
                yield identity(1)
                yield identity(2)
            except ValueError:
                yield identity(-1)

        def outer():
            yield from inner()

        force_compile(identity)
        force_compile(inner)
        force_compile(outer)

        g = outer()
        self.assertEqual(next(g), 1)
        self.assertEqual(g.throw(ValueError, "test"), -1)


class TestGeneratorClose(unittest.TestCase):
    """gen.close() triggers GeneratorExit with frame reification."""

    def test_close_with_jit_call_in_body(self):
        """Close a generator that has called a JIT'd function."""
        cleanup_called = False

        def gen():
            nonlocal cleanup_called
            try:
                yield identity(1)
                yield identity(2)
            finally:
                cleanup_called = True
                identity(99)  # JIT call in finally block

        force_compile(identity)
        force_compile(gen)

        g = gen()
        next(g)
        g.close()
        self.assertTrue(cleanup_called)


class TestGeneratorYieldFrom(unittest.TestCase):
    """yield from delegates to sub-generator — nested frame handling."""

    def test_yield_from_jit_generator(self):
        """Outer generator yield-from inner JIT'd generator."""
        def inner():
            yield add3(1, 2, 3)
            yield add3(4, 5, 6)

        def outer():
            yield from inner()

        force_compile(add3)
        force_compile(inner)
        force_compile(outer)

        results = list(outer())
        self.assertEqual(results, [6, 15])

    def test_nested_yield_from(self):
        """Three levels of yield from with JIT calls."""
        def level3():
            yield identity(1)
            yield identity(2)

        def level2():
            yield from level3()

        def level1():
            yield from level2()

        force_compile(identity)
        force_compile(level3)
        force_compile(level2)
        force_compile(level1)

        results = list(level1())
        self.assertEqual(results, [1, 2])


class TestAsyncGenerator(unittest.TestCase):
    """Async generators have the same FP relocation issue."""

    def test_async_generator_calls_jit_function(self):
        """Async generator calls JIT'd function."""
        async def agen():
            yield identity(1)
            yield add3(1, 2, 3)
            yield double(5)

        force_compile(identity)
        force_compile(add3)
        force_compile(double)
        force_compile(agen)

        async def collect():
            return [x async for x in agen()]

        results = asyncio.run(collect())
        self.assertEqual(results, [1, 6, 10])

    def test_async_generator_throw(self):
        """Throw into async generator with JIT calls."""
        async def agen():
            try:
                yield identity(1)
            except ValueError:
                yield identity(-1)

        force_compile(identity)
        force_compile(agen)

        async def run():
            ag = agen()
            val = await ag.__anext__()
            assert val == 1
            val = await ag.athrow(ValueError, "test")
            assert val == -1

        asyncio.run(run())


class TestCoroutine(unittest.TestCase):
    """Coroutines use the same generator machinery."""

    def test_coroutine_calls_jit_function(self):
        """Coroutine (async def without yield) calls JIT'd function."""
        async def coro():
            return add3(1, 2, 3)

        force_compile(add3)
        force_compile(coro)

        result = asyncio.run(coro())
        self.assertEqual(result, 6)

    def test_coroutine_with_await(self):
        """Coroutine awaits another coroutine, both calling JIT'd functions."""
        async def inner():
            return identity(42)

        async def outer():
            x = await inner()
            return double(x)

        force_compile(identity)
        force_compile(double)
        force_compile(inner)
        force_compile(outer)

        result = asyncio.run(outer())
        self.assertEqual(result, 84)


class TestGeneratorExceptionHandling(unittest.TestCase):
    """Exception handling within generators exercises frame reification."""

    def test_exception_in_generator_body(self):
        """Exception raised inside generator body, caught inside."""
        def gen():
            for i in range(5):
                try:
                    yield raise_if_negative(i - 2)
                except ValueError:
                    yield identity(-999)

        force_compile(raise_if_negative)
        force_compile(identity)
        force_compile(gen)

        results = list(gen())
        # i=0: raise(-2) caught → -999
        # i=1: raise(-1) caught → -999
        # i=2: 0
        # i=3: 1
        # i=4: 2
        self.assertEqual(results, [-999, -999, 0, 1, 2])

    def test_traceback_from_generator(self):
        """Verify traceback through generator frames is readable."""
        def gen():
            yield identity(1)
            raise RuntimeError("gen error")

        force_compile(identity)
        force_compile(gen)

        g = gen()
        next(g)
        try:
            next(g)
            self.fail("Should have raised")
        except RuntimeError:
            tb = traceback.format_exc()
            self.assertIn("gen error", tb)


class TestGeneratorStress(unittest.TestCase):
    """Stress tests to catch intermittent corruption."""

    def test_many_generator_iterations_with_jit_calls(self):
        """1000 iterations of generator calling JIT'd function."""
        def gen(n):
            for i in range(n):
                yield add3(i, i + 1, i + 2)

        force_compile(add3)
        force_compile(gen)

        results = list(gen(1000))
        expected = [3 * i + 3 for i in range(1000)]
        self.assertEqual(results, expected)

    def test_many_generators_created_and_consumed(self):
        """Create and consume 100 generators, each calling JIT'd functions."""
        def gen(start):
            yield identity(start)
            yield double(start)
            yield add3(start, start, start)

        force_compile(identity)
        force_compile(double)
        force_compile(add3)
        force_compile(gen)

        for i in range(100):
            results = list(gen(i))
            self.assertEqual(results, [i, 2 * i, 3 * i])

    def test_interleaved_generators(self):
        """Multiple generators interleaved, all calling JIT'd functions."""
        def gen(base):
            for i in range(5):
                yield add3(base, i, 0)

        force_compile(add3)
        force_compile(gen)

        g1 = gen(0)
        g2 = gen(100)
        g3 = gen(200)

        results = []
        for _ in range(5):
            results.append(next(g1))
            results.append(next(g2))
            results.append(next(g3))

        expected = []
        for i in range(5):
            expected.extend([i, 100 + i, 200 + i])
        self.assertEqual(results, expected)


if __name__ == "__main__":
    unittest.main()
