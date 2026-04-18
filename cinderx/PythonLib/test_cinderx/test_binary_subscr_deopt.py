"""Polymorphic subscript deopt tests.

Verifies that GuardType fires correctly when JIT-compiled with one container
type and then called with a different type, producing correct results via deopt.
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

    def setUp(self):
        cinderjit.auto()

    def test_list_compiled_then_tuple(self):
        def f(container, indices):
            total = 0
            for i in indices:
                total += container[i]
            return total
        indices = list(range(100))
        for _ in range(1200):
            f(list(range(100)), indices)
        expected = sum(range(100))
        self.assertEqual(f(list(range(100)), indices), expected)
        self.assertEqual(f(tuple(range(100)), indices), expected)
        self.assertEqual(f(list(range(100)), indices), expected)

    def test_tuple_compiled_then_list(self):
        def f(container, indices):
            total = 0
            for i in indices:
                total += container[i]
            return total
        indices = list(range(100))
        for _ in range(1200):
            f(tuple(range(100)), indices)
        self.assertEqual(f(list(range(100)), indices), sum(range(100)))

    def test_dict_compiled_then_defaultdict(self):
        def f(container, keys):
            total = 0
            for k in keys:
                total += container[k]
            return total
        d = {i: i for i in range(100)}
        keys = list(range(100))
        for _ in range(1200):
            f(d, keys)
        dd = defaultdict(int)
        for i in range(100):
            dd[i] = i
        self.assertEqual(f(dd, keys), sum(range(100)))

    def test_list_compiled_then_dict(self):
        def f(container, keys):
            total = 0
            for k in keys:
                total += container[k]
            return total
        for _ in range(1200):
            f(list(range(50)), list(range(50)))
        d = {i: i * 3 for i in range(50)}
        self.assertEqual(f(d, list(range(50))), sum(i * 3 for i in range(50)))

    def test_negative_index_after_deopt(self):
        def f(container, idx):
            return container[idx]
        data = list(range(10))
        for _ in range(1200):
            f(data, 5)
        self.assertEqual(f(data, -1), 9)
        self.assertEqual(f(tuple(range(10)), -2), 8)

    def test_try_except_in_subscript_loop(self):
        def f(container, indices):
            total = 0
            for i in indices:
                try:
                    total += container[i]
                except (IndexError, KeyError):
                    total += -1
            return total
        indices = list(range(50))
        for _ in range(1200):
            f(list(range(50)), indices)
        expected = sum(range(50))
        self.assertEqual(f(tuple(range(50)), indices), expected)
        self.assertEqual(f({i: i for i in range(50)}, indices), expected)

    def test_keyerror_handling_after_deopt(self):
        def f(container, keys):
            found = 0
            for k in keys:
                try:
                    container[k]
                    found += 1
                except (KeyError, IndexError):
                    pass
            return found
        d = {i: i for i in range(50)}
        all_keys = list(range(100))
        for _ in range(1200):
            f(d, all_keys)
        self.assertEqual(f(d, all_keys), 50)
        self.assertEqual(f(list(range(50)), all_keys), 50)

    def test_rapid_type_alternation(self):
        def f(container, indices):
            total = 0
            for i in indices:
                total += container[i]
            return total
        indices = list(range(20))
        for _ in range(1200):
            f(list(range(20)), indices)
        expected = sum(range(20))
        for _ in range(100):
            self.assertEqual(f(list(range(20)), indices), expected)
            self.assertEqual(f(tuple(range(20)), indices), expected)
            self.assertEqual(f({i: i for i in range(20)}, indices), expected)


if __name__ == '__main__':
    unittest.main()
