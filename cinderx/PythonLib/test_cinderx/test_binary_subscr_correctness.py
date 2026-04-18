"""Correctness tests for BINARY_SUBSCR specialisations.

Verifies that JIT-compiled specialised paths (LoadArrayItem for list/tuple,
DictSubscr for dict) produce correct results for edge cases.
"""
import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestBinarySubscrCorrectness(unittest.TestCase):

    def setUp(self):
        cinderjit.auto()

    def _warmup(self, fn, *args, n=1200):
        for _ in range(n):
            try:
                fn(*args)
            except (IndexError, KeyError, TypeError):
                pass

    def test_list_positive_index(self):
        def f(lst, idx):
            return lst[idx]
        data = [10, 20, 30, 40, 50]
        self._warmup(f, data, 0)
        self.assertEqual(f(data, 0), 10)
        self.assertEqual(f(data, 2), 30)
        self.assertEqual(f(data, 4), 50)

    def test_list_negative_index(self):
        def f(lst, idx):
            return lst[idx]
        data = [10, 20, 30, 40, 50]
        self._warmup(f, data, -1)
        self.assertEqual(f(data, -1), 50)
        self.assertEqual(f(data, -3), 30)
        self.assertEqual(f(data, -5), 10)

    def test_list_out_of_bounds(self):
        def f(lst, idx):
            return lst[idx]
        data = [10, 20, 30, 40, 50]
        self._warmup(f, data, 0)
        with self.assertRaises(IndexError):
            f(data, 5)
        with self.assertRaises(IndexError):
            f(data, -6)

    def test_tuple_index(self):
        def f(tup, idx):
            return tup[idx]
        data = (100, 200, 300, 400, 500)
        self._warmup(f, data, 0)
        self.assertEqual(f(data, 0), 100)
        self.assertEqual(f(data, 4), 500)
        self.assertEqual(f(data, -1), 500)
        self.assertEqual(f(data, -5), 100)

    def test_tuple_out_of_bounds(self):
        def f(tup, idx):
            return tup[idx]
        data = (100, 200, 300, 400, 500)
        self._warmup(f, data, 0)
        with self.assertRaises(IndexError):
            f(data, 5)
        with self.assertRaises(IndexError):
            f(data, -6)

    def test_dict_existing_key(self):
        def f(d, key):
            return d[key]
        data = {"a": 1, "b": 2, "c": 3, 42: "forty-two"}
        self._warmup(f, data, "a")
        self.assertEqual(f(data, "a"), 1)
        self.assertEqual(f(data, "c"), 3)
        self.assertEqual(f(data, 42), "forty-two")

    def test_dict_missing_key(self):
        def f(d, key):
            return d[key]
        data = {"a": 1, "b": 2}
        self._warmup(f, data, "a")
        with self.assertRaises(KeyError):
            f(data, "z")

    def test_single_element_containers(self):
        def f(container, idx):
            return container[idx]
        self._warmup(f, [99], 0)
        self.assertEqual(f([99], 0), 99)
        self.assertEqual(f([99], -1), 99)
        self.assertEqual(f((99,), 0), 99)
        self.assertEqual(f({0: 99}, 0), 99)

    def test_empty_container_raises(self):
        def f(container, idx):
            return container[idx]
        self._warmup(f, [1], 0)
        with self.assertRaises(IndexError):
            f([], 0)
        with self.assertRaises(IndexError):
            f((), 0)
        with self.assertRaises(KeyError):
            f({}, "x")

    def test_large_list_boundary(self):
        def f(lst, idx):
            return lst[idx]
        big = list(range(10000))
        self._warmup(f, big, 0)
        self.assertEqual(f(big, 0), 0)
        self.assertEqual(f(big, 9999), 9999)
        self.assertEqual(f(big, -1), 9999)
        self.assertEqual(f(big, -10000), 0)

    def test_subscript_loop_accumulation(self):
        def f(lst, indices):
            total = 0
            for i in indices:
                total += lst[i]
            return total
        self._warmup(f, [1, 2, 3], [0, 1, 2])
        self.assertEqual(f([10, 20, 30], [0, 1, 2]), 60)
        self.assertEqual(f(list(range(100)), list(range(100))), 4950)

    def test_dict_int_keys_loop(self):
        def f(d, keys):
            total = 0
            for k in keys:
                total += d[k]
            return total
        d = {i: i * 3 for i in range(100)}
        self._warmup(f, d, list(range(100)))
        self.assertEqual(f(d, [0, 1, 2]), 9)
        self.assertEqual(f(d, list(range(100))), sum(i * 3 for i in range(100)))


if __name__ == '__main__':
    unittest.main()
