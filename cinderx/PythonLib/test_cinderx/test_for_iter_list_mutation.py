"""FOR_ITER_LIST mutation tests.

Verifies JIT-compiled code produces identical results to the interpreter
when a list is mutated during iteration.
"""
import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestForIterListMutation(unittest.TestCase):

    def setUp(self):
        cinderjit.auto()

    def _run_and_compare(self, fn, make_input, warmup=1200):
        ref = fn(make_input())
        for _ in range(warmup):
            fn(make_input())
        jit_result = fn(make_input())
        self.assertEqual(jit_result, ref)
        for _ in range(100):
            self.assertEqual(fn(make_input()), ref)

    def test_append_during_iteration(self):
        def f(lst):
            results = []
            count = 0
            for x in lst:
                results.append(x)
                if count == 2:
                    lst.append(999)
                count += 1
            return results
        self._run_and_compare(f, lambda: list(range(5)))

    def test_pop_during_iteration(self):
        def f(lst):
            results = []
            for x in lst:
                results.append(x)
                if len(lst) > 3:
                    lst.pop()
            return results
        self._run_and_compare(f, lambda: list(range(10)))

    def test_del_during_iteration(self):
        def f(lst):
            results = []
            i = 0
            for x in lst:
                results.append(x)
                if i == 1 and len(lst) > 3:
                    del lst[0]
                i += 1
            return results
        self._run_and_compare(f, lambda: list(range(8)))

    def test_clear_during_iteration(self):
        def f(lst):
            results = []
            for x in lst:
                results.append(x)
                if len(results) == 2:
                    lst.clear()
            return results
        self._run_and_compare(f, lambda: list(range(10)))

    def test_assignment_during_iteration(self):
        def f(lst):
            results = []
            for i, x in enumerate(lst):
                results.append(x)
                if i == 0:
                    for j in range(1, len(lst)):
                        lst[j] = lst[j] * 10
            return results
        self._run_and_compare(f, lambda: list(range(1, 6)))

    def test_insert_during_iteration(self):
        def f(lst):
            results = []
            inserted = False
            for x in lst:
                results.append(x)
                if x == 2 and not inserted:
                    lst.insert(0, -1)
                    inserted = True
            return results
        self._run_and_compare(f, lambda: list(range(5)))

    def test_extend_during_iteration(self):
        def f(lst):
            results = []
            extended = False
            for x in lst:
                results.append(x)
                if x == 2 and not extended:
                    lst.extend([100, 200, 300])
                    extended = True
            return results
        self._run_and_compare(f, lambda: list(range(4)))

    def test_empty_list(self):
        def f(lst):
            results = []
            for x in lst:
                results.append(x)
            return results
        self._run_and_compare(f, lambda: [])

    def test_single_element(self):
        def f(lst):
            results = []
            for x in lst:
                results.append(x)
            return results
        self._run_and_compare(f, lambda: [42])


if __name__ == '__main__':
    unittest.main()
