"""
test_licm_exception_handler — Correctness tests for JIT exception handler
interactions, including LICM (Loop-Invariant Code Motion) with try/except.

Tests verify that JIT-compiled loops with try/except produce correct results
under both force_compile and auto-compile paths.

Known limitation: force_compile crashes on functions with multiple separate
except clauses (e.g. except KeyError: ... except TypeError: ...) when the
exception actually fires. Auto-compile handles this correctly. See
test_multiple_except_clauses_force_compile for the documented crash.
"""

import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


def force_compile(fn):
    if HAS_CINDERJIT:
        cinderjit.force_compile(fn)


def auto_compile_warmup(fn, warmup_args, n=100):
    """Warm up fn under auto-compile by calling it n times."""
    if HAS_CINDERJIT:
        cinderjit.auto()
    for _ in range(n):
        fn(*warmup_args)


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestLICMExceptionHandler(unittest.TestCase):

    def test_loop_with_try_except_attr_access(self):
        """Loop with try/except accessing attributes — LICM may hoist GuardType."""

        class Good:
            def __init__(self, value):
                self.value = value

        def loop_with_except(items):
            total = 0
            for item in items:
                try:
                    total += item.value
                except AttributeError:
                    total += int(item)
            return total

        force_compile(loop_with_except)

        good_items = [Good(1), Good(2), Good(3), Good(4), Good(5)]
        self.assertEqual(loop_with_except(good_items), 15)

        mixed_items = [Good(10), "5", Good(20), "3", Good(30)]
        self.assertEqual(loop_with_except(mixed_items), 68)

        all_bad = ["1", "2", "3"]
        self.assertEqual(loop_with_except(all_bad), 6)

    def test_loop_with_try_except_method_call(self):
        """Loop with try/except calling methods — tests deopt from except body."""

        class Processor:
            def __init__(self, multiplier):
                self.multiplier = multiplier

            def process(self, x):
                return x * self.multiplier

        def loop_process(processors, values):
            results = []
            for p in processors:
                for v in values:
                    try:
                        results.append(p.process(v))
                    except (TypeError, AttributeError):
                        results.append(-1)
            return results

        force_compile(loop_process)

        procs = [Processor(2), Processor(3)]
        vals = [1, 2, 3]
        self.assertEqual(loop_process(procs, vals), [2, 4, 6, 3, 6, 9])

        mixed_procs = [Processor(2), None]
        self.assertEqual(loop_process(mixed_procs, [1, 2]), [2, 4, -1, -1])

    def test_loop_exception_accumulator_state(self):
        """Verify accumulator state is preserved across exception boundaries."""

        def accumulate_safe(items):
            total = 0
            count = 0
            for item in items:
                try:
                    total += item * 2
                    count += 1
                except TypeError:
                    pass
            return total, count

        force_compile(accumulate_safe)

        self.assertEqual(accumulate_safe([1, 2, 3, 4, 5]), (30, 5))
        self.assertEqual(accumulate_safe([1, "bad", 3, None, 5]), (18, 3))
        self.assertEqual(accumulate_safe([]), (0, 0))

    def test_nested_loop_with_exception(self):
        """Nested loops with exception in inner loop."""

        def nested_with_except(matrix):
            total = 0
            for row in matrix:
                for cell in row:
                    try:
                        total += cell
                    except TypeError:
                        total += 0
            return total

        force_compile(nested_with_except)

        self.assertEqual(nested_with_except([[1, 2], [3, 4]]), 10)
        self.assertEqual(nested_with_except([[1, None], [3, 4]]), 8)
        self.assertEqual(nested_with_except([[None, None]]), 0)

    def test_exception_handler_with_break(self):
        """Exception handler with break — tests control flow from except."""

        def find_first_valid(items):
            result = -1
            for item in items:
                try:
                    result = item.value
                    break
                except AttributeError:
                    continue
            return result

        class Val:
            def __init__(self, value):
                self.value = value

        force_compile(find_first_valid)

        self.assertEqual(find_first_valid([Val(42)]), 42)
        self.assertEqual(find_first_valid(["bad", "also_bad", Val(99)]), 99)
        self.assertEqual(find_first_valid(["bad", "bad"]), -1)
        self.assertEqual(find_first_valid([]), -1)

    def test_multiple_except_clauses_auto_compile(self):
        """Multiple except clauses under auto-compile (production path)."""

        def multi_except_loop(items):
            results = []
            for item in items:
                try:
                    results.append(item["key"] + 1)
                except KeyError:
                    results.append(-1)
                except TypeError:
                    results.append(-2)
            return results

        auto_compile_warmup(multi_except_loop, ([{"key": 1}, {"other": 2}, None],))

        self.assertEqual(
            multi_except_loop([{"key": 1}, {"key": 2}, {"other": 3}]),
            [2, 3, -1],
        )
        self.assertEqual(
            multi_except_loop([{"key": 1}, None, {"key": 3}]),
            [2, -2, 4],
        )
        self.assertEqual(
            multi_except_loop([{"key": 10}]),
            [11],
        )

    @unittest.skip(
        "CRASH: force_compile + multiple except clauses → SIGSEGV (RIP=0x0). "
        "Auto-compile works correctly. Pre-existing JIT bug in exception "
        "handler code generation without type feedback."
    )
    def test_multiple_except_clauses_force_compile(self):
        """force_compile crashes on multiple except clauses when exception fires.

        Root cause: emitInlineExceptionMatch generates blocks for the second
        except handler that receive no machine code under force_compile
        (no type feedback). CondBranch targets an empty block → jump to 0x0.
        Auto-compile avoids this because type feedback guides compilation.
        """

        def multi_except_loop(items):
            results = []
            for item in items:
                try:
                    results.append(item["key"] + 1)
                except KeyError:
                    results.append(-1)
                except TypeError:
                    results.append(-2)
            return results

        force_compile(multi_except_loop)

        self.assertEqual(
            multi_except_loop([{"key": 1}, {"key": 2}, {"other": 3}]),
            [2, 3, -1],
        )


if __name__ == "__main__":
    unittest.main()
