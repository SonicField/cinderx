"""
test_binary_subscr_correctness.py — Correctness tests for BINARY_SUBSCR specialisations.

Verifies that the JIT-compiled specialised paths (LoadArrayItem for list/tuple,
DictSubscr for dict) produce correct results for edge cases.

Tests cover:
  - Positive and negative indexing
  - Boundary indices (0, -1, len-1, -len)
  - Out-of-bounds IndexError
  - Dict KeyError on missing key
  - Large containers
  - Single-element containers
  - Empty containers (should raise)
"""

import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


def warmup(fn, *args, n=15000):
    for _ in range(n):
        try:
            fn(*args)
        except (IndexError, KeyError, TypeError):
            pass


def list_pos_idx(lst, idx):
    return lst[idx]


def list_neg_idx(lst, idx):
    return lst[idx]


def list_oob(lst, idx):
    return lst[idx]


def tuple_idx(tup, idx):
    return tup[idx]


def tuple_oob(tup, idx):
    return tup[idx]


def dict_get(d, key):
    return d[key]


def dict_miss(d, key):
    return d[key]


def single_get(container, idx):
    return container[idx]


def empty_get(container, idx):
    return container[idx]


def large_list_get(lst, idx):
    return lst[idx]


def sum_subscr(lst, indices):
    total = 0
    for i in indices:
        total += lst[i]
    return total


def dict_int_keys(d, keys):
    total = 0
    for k in keys:
        total += d[k]
    return total


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestBinarySubscrCorrectness(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        data = [10, 20, 30, 40, 50]
        tdata = (100, 200, 300, 400, 500)
        ddata = {"a": 1, "b": 2, "c": 3, 42: "forty-two"}
        big = list(range(10000))
        d = {i: i * 3 for i in range(100)}

        warmup(list_pos_idx, data, 0)
        warmup(list_neg_idx, data, -1)
        warmup(list_oob, data, 0)
        warmup(tuple_idx, tdata, 0)
        warmup(tuple_oob, tdata, 0)
        warmup(dict_get, ddata, "a")
        warmup(dict_miss, ddata, "a")
        warmup(single_get, [99], 0)
        warmup(empty_get, [1], 0)
        warmup(large_list_get, big, 0)
        warmup(sum_subscr, [1, 2, 3], [0, 1, 2])
        warmup(dict_int_keys, d, list(range(100)))

    def test_list_positive_index(self):
        data = [10, 20, 30, 40, 50]
        self.assertEqual(list_pos_idx(data, 0), 10)
        self.assertEqual(list_pos_idx(data, 2), 30)
        self.assertEqual(list_pos_idx(data, 4), 50)

    def test_list_negative_index(self):
        data = [10, 20, 30, 40, 50]
        self.assertEqual(list_neg_idx(data, -1), 50)
        self.assertEqual(list_neg_idx(data, -3), 30)
        self.assertEqual(list_neg_idx(data, -5), 10)

    def test_list_out_of_bounds(self):
        data = [10, 20, 30, 40, 50]
        with self.assertRaises(IndexError):
            list_oob(data, 5)
        with self.assertRaises(IndexError):
            list_oob(data, -6)

    def test_tuple_positive_and_negative_index(self):
        tdata = (100, 200, 300, 400, 500)
        self.assertEqual(tuple_idx(tdata, 0), 100)
        self.assertEqual(tuple_idx(tdata, 4), 500)
        self.assertEqual(tuple_idx(tdata, -1), 500)
        self.assertEqual(tuple_idx(tdata, -5), 100)

    def test_tuple_out_of_bounds(self):
        tdata = (100, 200, 300, 400, 500)
        with self.assertRaises(IndexError):
            tuple_oob(tdata, 5)
        with self.assertRaises(IndexError):
            tuple_oob(tdata, -6)

    def test_dict_existing_key(self):
        ddata = {"a": 1, "b": 2, "c": 3, 42: "forty-two"}
        self.assertEqual(dict_get(ddata, "a"), 1)
        self.assertEqual(dict_get(ddata, "c"), 3)
        self.assertEqual(dict_get(ddata, 42), "forty-two")

    def test_dict_missing_key_raises_key_error(self):
        ddata = {"a": 1, "b": 2, "c": 3, 42: "forty-two"}
        with self.assertRaises(KeyError):
            dict_miss(ddata, "z")

    def test_single_element_containers(self):
        self.assertEqual(single_get([99], 0), 99)
        self.assertEqual(single_get([99], -1), 99)
        self.assertEqual(single_get((99,), 0), 99)
        self.assertEqual(single_get((99,), -1), 99)
        self.assertEqual(single_get({0: 99}, 0), 99)

    def test_empty_containers_raise(self):
        with self.assertRaises(IndexError):
            empty_get([], 0)
        with self.assertRaises(IndexError):
            empty_get((), 0)
        with self.assertRaises(KeyError):
            empty_get({}, "x")

    def test_large_list_boundary_indices(self):
        big = list(range(10000))
        self.assertEqual(large_list_get(big, 0), 0)
        self.assertEqual(large_list_get(big, 9999), 9999)
        self.assertEqual(large_list_get(big, -1), 9999)
        self.assertEqual(large_list_get(big, -10000), 0)
        self.assertEqual(large_list_get(big, 5000), 5000)

    def test_subscript_in_loop_accumulation(self):
        self.assertEqual(sum_subscr([10, 20, 30], [0, 1, 2]), 60)
        self.assertEqual(sum_subscr([10, 20, 30], [2, 2, 2]), 90)
        self.assertEqual(sum_subscr([10, 20, 30], [-1, -2, -3]), 60)
        self.assertEqual(sum_subscr(list(range(100)), list(range(100))), 4950)

    def test_dict_with_int_keys_loop(self):
        d = {i: i * 3 for i in range(100)}
        self.assertEqual(dict_int_keys(d, [0, 1, 2]), 9)  # 0 + 3 + 6
        self.assertEqual(
            dict_int_keys(d, list(range(100))),
            sum(i * 3 for i in range(100)),
        )


if __name__ == "__main__":
    unittest.main()
