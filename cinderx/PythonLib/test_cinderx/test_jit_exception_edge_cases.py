"""Edge case tests for JIT exception handling.

These tests guard against the class of bugs that caused the Deopt→Branch
crash (328038e4, reverted as c193d3d2). The crash manifested only at high
iteration counts with specialized bytecodes — conditions that the existing
test_exception_handler_inlining.py does not cover.

Each test exercises a specific edge case:
- High iteration counts (n=100, n=1000) that trigger bytecode specialization
- Nested try/except at 3+ levels
- Exception handling inside generators
- Mixed hit/miss patterns that stress IC and deopt paths
- Exception handler interaction with for-loops and comprehensions
"""
import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


# =====================================================================
# Module-level functions — must be at module scope for JIT inlining.
# =====================================================================

def dict_lookup_with_fallback(d, key):
    try:
        return d[key]
    except KeyError:
        return -1


def nested_three_level(x):
    try:
        try:
            try:
                if x == 0:
                    raise ZeroDivisionError
                return 100 // x
            except ZeroDivisionError:
                return -1
        except ValueError:
            return -2
    except Exception:
        return -3


def exception_in_generator(n):
    d = {"a": 1, "b": 2}
    for i in range(n):
        try:
            yield d["a"] + i
        except KeyError:
            yield -1


def exception_in_generator_miss(n):
    d = {"a": 1}
    for i in range(n):
        key = "a" if i % 2 == 0 else "missing"
        try:
            yield d[key]
        except KeyError:
            yield -1


def exception_in_generator_conditional_yield(n):
    d = {"a": 1}
    for i in range(n):
        key = "a" if i % 2 == 0 else "missing"
        try:
            yield d[key]
        except KeyError:
            if i % 4 == 1:
                yield -1
            else:
                yield -2


def callee_in_loop_body(d, key):
    try:
        return d[key]
    except KeyError:
        return None


def mixed_exception_pattern(d, keys):
    total = 0
    for k in keys:
        try:
            total += d[k]
        except KeyError:
            total += 1
    return total


def try_except_in_comprehension(d, keys):
    def safe_get(k):
        try:
            return d[k]
        except KeyError:
            return 0
    return [safe_get(k) for k in keys]


def nested_finally_except(x):
    result = 0
    try:
        try:
            result = 10 // x
        except ZeroDivisionError:
            result = -1
        finally:
            result += 100
    except Exception:
        result = -999
    return result


# =====================================================================
# Tests
# =====================================================================

@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestExceptionHighN(unittest.TestCase):
    """Exception handling at high iteration counts.

    The Deopt→Branch crash only manifested at n>=100 with specialized
    bytecodes. These tests ensure correctness at those scales.
    """

    def _compile_and_run(self, func, n, *args):
        cinderjit.force_compile(func)
        for _ in range(n):
            func(*args)

    def test_dict_lookup_high_n_all_hit(self):
        d = {i: i * 10 for i in range(100)}
        self._compile_and_run(dict_lookup_with_fallback, 1000, d, 50)
        self.assertEqual(dict_lookup_with_fallback(d, 50), 500)
        self.assertEqual(dict_lookup_with_fallback(d, 99), 990)

    def test_dict_lookup_high_n_all_miss(self):
        d = {"a": 1}
        self._compile_and_run(dict_lookup_with_fallback, 1000, d, "missing")
        self.assertEqual(dict_lookup_with_fallback(d, "missing"), -1)

    def test_dict_lookup_high_n_mixed(self):
        d = {i: i for i in range(50)}
        cinderjit.force_compile(dict_lookup_with_fallback)
        for i in range(1000):
            key = i % 100
            expected = key if key < 50 else -1
            self.assertEqual(dict_lookup_with_fallback(d, key), expected)

    def test_mixed_pattern_high_n(self):
        d = {i: i for i in range(0, 100, 2)}
        keys = list(range(100))
        cinderjit.force_compile(mixed_exception_pattern)
        for _ in range(100):
            result = mixed_exception_pattern(d, keys)
            expected = sum(i for i in range(0, 100, 2)) + 50
            self.assertEqual(result, expected)


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestExceptionNested(unittest.TestCase):
    """Nested try/except at 3+ levels."""

    def test_three_level_no_exception(self):
        cinderjit.force_compile(nested_three_level)
        for _ in range(200):
            self.assertEqual(nested_three_level(10), 10)

    def test_three_level_innermost_catches(self):
        cinderjit.force_compile(nested_three_level)
        for _ in range(200):
            self.assertEqual(nested_three_level(0), -1)

    def test_three_level_alternating(self):
        cinderjit.force_compile(nested_three_level)
        for i in range(500):
            x = [0, 10, 5, 0, 1][i % 5]
            expected = -1 if x == 0 else 100 // x
            self.assertEqual(nested_three_level(x), expected)

    def test_nested_finally_no_exception(self):
        cinderjit.force_compile(nested_finally_except)
        self.assertEqual(nested_finally_except(10), 101)

    def test_nested_finally_with_exception(self):
        cinderjit.force_compile(nested_finally_except)
        self.assertEqual(nested_finally_except(0), 99)

    def test_nested_finally_high_n(self):
        cinderjit.force_compile(nested_finally_except)
        for i in range(500):
            x = i % 10
            if x == 0:
                self.assertEqual(nested_finally_except(x), 99)
            else:
                self.assertEqual(nested_finally_except(x), 100 + 10 // x)


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestExceptionInGenerator(unittest.TestCase):
    """Exception handling inside generator functions."""

    def test_generator_all_hit(self):
        cinderjit.force_compile(exception_in_generator)
        result = list(exception_in_generator(100))
        self.assertEqual(len(result), 100)
        self.assertEqual(result[0], 1)
        self.assertEqual(result[99], 100)

    def test_generator_mixed_hit_miss(self):
        cinderjit.force_compile(exception_in_generator_miss)
        result = list(exception_in_generator_miss(100))
        self.assertEqual(len(result), 100)
        for i, v in enumerate(result):
            if i % 2 == 0:
                self.assertEqual(v, 1)
            else:
                self.assertEqual(v, -1)

    def test_generator_high_n(self):
        cinderjit.force_compile(exception_in_generator)
        result = list(exception_in_generator(1000))
        self.assertEqual(len(result), 1000)
        self.assertEqual(result[999], 1000)

    def test_generator_mixed_high_n(self):
        cinderjit.force_compile(exception_in_generator_miss)
        result = list(exception_in_generator_miss(1000))
        self.assertEqual(len(result), 1000)
        hits = sum(1 for v in result if v == 1)
        misses = sum(1 for v in result if v == -1)
        self.assertEqual(hits, 500)
        self.assertEqual(misses, 500)

    def test_generator_conditional_yield_in_except(self):
        """Yield behind a conditional in except body.

        This exercises the YIELD_VALUE scan's handling of conditional
        branches. If the scan stops at POP_JUMP_IF_FALSE (as
        isTerminator() would), it misses the YIELD_VALUE and crashes.
        """
        cinderjit.force_compile(exception_in_generator_conditional_yield)
        result = list(exception_in_generator_conditional_yield(100))
        self.assertEqual(len(result), 100)
        for i, v in enumerate(result):
            if i % 2 == 0:
                self.assertEqual(v, 1)
            elif i % 4 == 1:
                self.assertEqual(v, -1)
            else:
                self.assertEqual(v, -2)


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestExceptionInLoopBody(unittest.TestCase):
    """Exception handling in hot loop bodies with callee inlining."""

    def test_callee_in_loop_all_hit(self):
        d = {str(i): i for i in range(100)}
        cinderjit.force_compile(callee_in_loop_body)
        for _ in range(200):
            for k in d:
                self.assertEqual(callee_in_loop_body(d, k), d[k])

    def test_callee_in_loop_all_miss(self):
        d = {"a": 1}
        cinderjit.force_compile(callee_in_loop_body)
        for _ in range(200):
            self.assertIsNone(callee_in_loop_body(d, "missing"))

    def test_callee_in_loop_mixed(self):
        d = {"a": 1, "b": 2, "c": 3}
        cinderjit.force_compile(callee_in_loop_body)
        for _ in range(200):
            self.assertEqual(callee_in_loop_body(d, "a"), 1)
            self.assertIsNone(callee_in_loop_body(d, "z"))
            self.assertEqual(callee_in_loop_body(d, "c"), 3)
            self.assertIsNone(callee_in_loop_body(d, "missing"))

    def test_comprehension_with_exceptions(self):
        d = {i: i * 10 for i in range(50)}
        keys = list(range(100))
        cinderjit.force_compile(try_except_in_comprehension)
        result = try_except_in_comprehension(d, keys)
        self.assertEqual(len(result), 100)
        for i, v in enumerate(result):
            if i < 50:
                self.assertEqual(v, i * 10)
            else:
                self.assertEqual(v, 0)


if __name__ == "__main__":
    unittest.main()
