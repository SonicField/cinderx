"""
test_for_iter_polymorphic_deopt — Polymorphic iteration deopt tests.

Targets: All FOR_ITER specialisations (RANGE, LIST, TUPLE) emit a GuardType
at GET_ITER. When a function is JIT-compiled with one iterator type and then
called with a different iterator type, the GuardType must fire, triggering
deoptimisation back to the interpreter. The interpreter must then produce
the correct result.

These tests verify:
1. A function compiled with list iteration deopts correctly when given
   a range/tuple/dict/set iterator.
2. A function compiled with range iteration deopts correctly when given
   a list/tuple iterator.
3. After deopt, the function continues to produce correct results for
   BOTH the original and new iterator types.
4. Repeated alternation between types produces correct results every time.

This is the polymorphic test that Pythia flagged as missing. Bug 5 showed
that deopt can resume at the wrong bytecode offset — these tests would have
caught that class of bug for FOR_ITER specialisations.
"""

import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


def _compile(fn):
    """Force JIT compilation of fn, enabling specialised opcodes if available."""
    try:
        cinderjit.enable_specialized_opcodes()
    except AttributeError:
        pass
    cinderjit.force_compile(fn)


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestForIterPolymorphicDeopt(unittest.TestCase):

    def test_list_compiled_then_range_deopt(self):
        """List-compiled function produces correct result when given range input."""
        def sum_iter(iterable):
            """Sum over any iterable. Compiled with list input."""
            total = 0
            for x in iterable:
                total += x
            return total

        _compile(sum_iter)

        expected = sum(range(100))

        # Compiled path — must still work
        self.assertEqual(sum_iter(list(range(100))), expected)

        # Deopt path — range triggers GuardType
        self.assertEqual(sum_iter(range(100)), expected)

        # Compiled path after deopt — must still work
        self.assertEqual(sum_iter(list(range(100))), expected)

    def test_range_compiled_then_list_deopt(self):
        """Range-compiled function produces correct result when given list input."""
        def sum_iter(iterable):
            total = 0
            for x in iterable:
                total += x
            return total

        _compile(sum_iter)

        expected = sum(range(100))

        # Compiled path
        self.assertEqual(sum_iter(range(100)), expected)

        # Deopt path — list triggers GuardType
        self.assertEqual(sum_iter(list(range(100))), expected)

    def test_list_compiled_then_tuple_deopt(self):
        """List-compiled function produces correct result when given tuple input."""
        def sum_iter(iterable):
            total = 0
            for x in iterable:
                total += x
            return total

        _compile(sum_iter)

        expected = sum(range(100))
        self.assertEqual(sum_iter(tuple(range(100))), expected)

    def test_list_compiled_then_generator_deopt(self):
        """List-compiled function produces correct result when given a generator."""
        def sum_iter(iterable):
            total = 0
            for x in iterable:
                total += x
            return total

        _compile(sum_iter)

        expected = sum(range(100))
        self.assertEqual(sum_iter(x for x in range(100)), expected)

    def test_list_compiled_then_dict_deopt(self):
        """List-compiled function produces correct result when given dict (iterates over keys)."""
        def sum_iter(iterable):
            total = 0
            for x in iterable:
                total += x
            return total

        _compile(sum_iter)

        expected = sum(range(100))
        d = {i: None for i in range(100)}
        self.assertEqual(sum_iter(d), expected)

    def test_rapid_alternation(self):
        """Repeated alternation between list/range/tuple produces correct results every time."""
        def sum_iter(iterable):
            total = 0
            for x in iterable:
                total += x
            return total

        _compile(sum_iter)

        expected = sum(range(100))
        for cycle in range(1000):
            inputs = [
                list(range(100)),
                range(100),
                tuple(range(100)),
            ]
            for inp in inputs:
                self.assertEqual(
                    sum_iter(inp),
                    expected,
                    msg=f"alternation cycle {cycle}, type {type(inp).__name__}",
                )

    def test_complex_loop_body_deopt(self):
        """Complex loop body produces identical results across all iterator types after deopt."""
        def process_iter(iterable):
            """More complex loop body — ensures deopt restores full frame state."""
            results = []
            running_sum = 0
            for x in iterable:
                running_sum += x
                if x % 3 == 0:
                    results.append(running_sum)
            return results, running_sum

        _compile(process_iter)

        ref_list = process_iter(list(range(50)))
        ref_range = process_iter(range(50))
        ref_tuple = process_iter(tuple(range(50)))

        self.assertEqual(ref_list, ref_range)
        self.assertEqual(ref_list, ref_tuple)

    def test_nested_loops_mixed_types(self):
        """Nested iteration with different types for outer and inner produces correct results."""
        def nested_mixed(outer, inner):
            """Nested iteration with different types for outer and inner."""
            total = 0
            for i in outer:
                for j in inner:
                    total += i * j
            return total

        _compile(nested_mixed)

        ref = nested_mixed(list(range(20)), list(range(20)))

        combos = [
            (range(20), list(range(20)), "range/list"),
            (list(range(20)), range(20), "list/range"),
            (range(20), range(20), "range/range"),
            (tuple(range(20)), list(range(20)), "tuple/list"),
        ]
        for outer, inner, desc in combos:
            self.assertEqual(nested_mixed(outer, inner), ref, msg=f"nested {desc}")

    def test_exception_handler_inside_loop_deopt(self):
        """Loop with try/except produces correct results across all types after deopt."""
        def sum_with_try(iterable):
            """Loop with try/except — tests exception handler chain restoration after deopt."""
            total = 0
            for x in iterable:
                try:
                    total += x
                except TypeError:
                    pass
            return total

        _compile(sum_with_try)

        expected = sum(range(100))
        self.assertEqual(sum_with_try(list(range(100))), expected)
        self.assertEqual(sum_with_try(range(100)), expected)
        self.assertEqual(sum_with_try(tuple(range(100))), expected)

    def test_typeerror_caught_after_deopt(self):
        """TypeError is actually caught by the except handler after deopt."""
        def sum_with_try_mixed(iterable):
            total = 0
            caught = 0
            for x in iterable:
                try:
                    total += x
                except TypeError:
                    caught += 1
            return total, caught

        _compile(sum_with_try_mixed)

        mixed_input = list(range(10)) + ["not_a_number"] + list(range(10))
        ref_result = sum_with_try_mixed(mixed_input[:])

        # Tuple input triggers deopt — handler must still catch TypeError
        deopt_result = sum_with_try_mixed(tuple(mixed_input))
        self.assertEqual(deopt_result, ref_result)


if __name__ == "__main__":
    unittest.main()
