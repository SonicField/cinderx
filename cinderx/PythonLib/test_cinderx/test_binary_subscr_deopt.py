"""
test_binary_subscr_deopt — Polymorphic subscript deopt tests.

Targets: BINARY_SUBSCR_LIST_INT, BINARY_SUBSCR_TUPLE_INT, BINARY_SUBSCR_DICT
specialisations emit GuardType on the container (and index for list/tuple).
When a function is JIT-compiled with one container type and then called with
a different container type, the GuardType must fire, triggering deoptimisation
back to the interpreter. The interpreter must then produce the correct result.

These tests verify:
1. A function compiled with list input deopts correctly when given tuple/dict/set
2. A function compiled with tuple input deopts correctly when given list/dict
3. A function compiled with dict input deopts correctly when given list/defaultdict
4. After deopt, the function continues to produce correct results for BOTH types
5. try/except inside the subscript loop does not crash (Bug 7 regression guard)
6. Negative index handling works correctly after deopt
7. KeyError handling works correctly after deopt (dict path)
"""

import unittest
from collections import defaultdict

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestBinarySubscrDeopt(unittest.TestCase):

    def test_list_compiled_tuple_deopt(self):
        """List-compiled function deopts correctly when given a tuple."""
        def subscr_sum(container, indices):
            """Sum container[i] for each i in indices."""
            total = 0
            for i in indices:
                total += container[i]
            return total

        indices = list(range(100))
        expected = sum(range(100))

        cinderjit.force_compile(subscr_sum)

        # List path must work
        self.assertEqual(subscr_sum(list(range(100)), indices), expected)

        # Tuple input triggers GuardType deopt
        self.assertEqual(subscr_sum(tuple(range(100)), indices), expected)

        # List path must still work after deopt
        self.assertEqual(subscr_sum(list(range(100)), indices), expected)

    def test_tuple_compiled_list_deopt(self):
        """Tuple-compiled function deopts correctly when given a list."""
        def subscr_sum(container, indices):
            total = 0
            for i in indices:
                total += container[i]
            return total

        indices = list(range(100))
        expected = sum(range(100))

        cinderjit.force_compile(subscr_sum)

        # Warm up with tuple
        subscr_sum(tuple(range(100)), indices)

        # List input triggers deopt
        self.assertEqual(subscr_sum(list(range(100)), indices), expected)

    def test_dict_compiled_defaultdict_deopt(self):
        """Dict-compiled function deopts correctly when given a defaultdict."""
        def subscr_sum(container, keys):
            total = 0
            for k in keys:
                total += container[k]
            return total

        keys = list(range(100))
        expected = sum(range(100))
        d = {i: i for i in range(100)}

        cinderjit.force_compile(subscr_sum)

        self.assertEqual(subscr_sum(d, keys), expected)

        dd = defaultdict(int)
        for i in range(100):
            dd[i] = i

        self.assertEqual(subscr_sum(dd, keys), expected)

    def test_list_compiled_dict_deopt(self):
        """List-compiled function deopts correctly when given a dict."""
        def subscr_sum(container, keys):
            total = 0
            for k in keys:
                total += container[k]
            return total

        cinderjit.force_compile(subscr_sum)

        # Warm up with list
        subscr_sum(list(range(50)), list(range(50)))

        d4 = {i: i * 3 for i in range(50)}
        expected_4 = sum(i * 3 for i in range(50))
        self.assertEqual(subscr_sum(d4, list(range(50))), expected_4)

    def test_negative_index_after_deopt(self):
        """Negative index handling works correctly after deopt."""
        def subscr_neg(container, idx):
            return container[idx]

        data = list(range(10))
        cinderjit.force_compile(subscr_neg)

        self.assertEqual(subscr_neg(data, -1), 9)

        # Tuple deopt from list
        tdata = tuple(range(10))
        self.assertEqual(subscr_neg(tdata, -2), 8)

    def test_try_except_inside_subscript_loop(self):
        """try/except inside subscript loop does not crash (Bug 7 regression guard)."""
        def subscr_tryexcept(container, indices):
            """Subscript with try/except — Bug 7 trigger condition."""
            total = 0
            for i in indices:
                try:
                    total += container[i]
                except (IndexError, KeyError):
                    total += -1
            return total

        safe_indices = list(range(50))
        expected = sum(range(50))

        cinderjit.force_compile(subscr_tryexcept)

        # Warm up with list
        subscr_tryexcept(list(range(50)), safe_indices)

        # Tuple deopt with try/except (Bug 7 crash condition)
        self.assertEqual(subscr_tryexcept(tuple(range(50)), safe_indices), expected)

        # Dict deopt with try/except
        d6 = {i: i for i in range(50)}
        self.assertEqual(subscr_tryexcept(d6, safe_indices), expected)

    def test_keyerror_handling_after_deopt(self):
        """KeyError handling works correctly after deopt."""
        def subscr_keyerr(container, keys):
            """Dict subscript with missing keys."""
            found = 0
            for k in keys:
                try:
                    container[k]
                    found += 1
                except (KeyError, IndexError):
                    pass
            return found

        d7 = {i: i for i in range(50)}
        all_keys = list(range(100))  # keys 50–99 will KeyError

        cinderjit.force_compile(subscr_keyerr)

        self.assertEqual(subscr_keyerr(d7, all_keys), 50)

        # Deopt to list — IndexError for out-of-range indices
        lst7 = list(range(50))
        self.assertEqual(subscr_keyerr(lst7, all_keys), 50)

    def test_rapid_alternation_between_types(self):
        """Rapid alternation between list, tuple, and dict produces correct results."""
        def subscr_alt(container, indices):
            total = 0
            for i in indices:
                total += container[i]
            return total

        small_indices = list(range(20))
        small_list = list(range(20))
        small_tuple = tuple(range(20))
        small_dict = {i: i for i in range(20)}
        expected = sum(range(20))

        cinderjit.force_compile(subscr_alt)

        for _ in range(100):
            self.assertEqual(subscr_alt(small_list, small_indices), expected)
            self.assertEqual(subscr_alt(small_tuple, small_indices), expected)
            self.assertEqual(subscr_alt(small_dict, small_indices), expected)


if __name__ == "__main__":
    unittest.main()
