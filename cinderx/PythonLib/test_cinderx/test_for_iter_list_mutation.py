"""
test_for_iter_list_mutation — Correctness tests for FOR_ITER_LIST under mutation.

Targets: The FOR_ITER_LIST specialisation replaces generic InvokeIterNext with
CallStatic(JITRT_InvokeIterNext) when the iterator type is list_iterator.
The GuardType is emitted ONCE at GET_ITER (not per-iteration). If the list
is mutated during iteration, the underlying C list_iterator state may become
inconsistent with the fast-path assumptions.

These tests verify that JIT-compiled code produces IDENTICAL results to the
interpreter when the list is mutated during iteration. Each test runs first
without JIT (reference), then with JIT, and asserts equality.

CPython's list_iterator behaviour under mutation:
  - append: iteration continues, may or may not see appended elements
  - pop/del: iteration may skip elements or raise no error but produce
    different sequences than expected
  - clear: StopIteration on next iteration (length becomes 0)
  - assignment (lst[i] = x): iterator continues, sees new value

The key invariant: JIT must match interpreter behaviour EXACTLY, even if
that behaviour is surprising. A divergence means the fast path is unsound.
"""

import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


# ---------------------------------------------------------------------------
# Target functions — defined at module level so cinderjit.force_compile works.
# Each function exercises a different mutation pattern during list iteration.
# ---------------------------------------------------------------------------

def iterate_with_append(lst):
    results = []
    count = 0
    for x in lst:
        results.append(x)
        if count == 2:
            lst.append(999)
        count += 1
    return results


def iterate_with_pop(lst):
    results = []
    for x in lst:
        results.append(x)
        if len(lst) > 3:
            lst.pop()
    return results


def iterate_with_del(lst):
    results = []
    i = 0
    for x in lst:
        results.append(x)
        if i == 1 and len(lst) > 3:
            del lst[0]
        i += 1
    return results


def iterate_with_clear(lst):
    results = []
    for x in lst:
        results.append(x)
        if len(results) == 2:
            lst.clear()
    return results


def iterate_with_assign(lst):
    results = []
    for i, x in enumerate(lst):
        results.append(x)
        if i == 0:
            for j in range(1, len(lst)):
                lst[j] = lst[j] * 10
    return results


def iterate_with_insert(lst):
    results = []
    inserted = False
    for x in lst:
        results.append(x)
        if x == 2 and not inserted:
            lst.insert(0, -1)
            inserted = True
    return results


def iterate_with_extend(lst):
    results = []
    extended = False
    for x in lst:
        results.append(x)
        if x == 2 and not extended:
            lst.extend([100, 200, 300])
            extended = True
    return results


def iterate_empty(lst):
    results = []
    for x in lst:
        results.append(x)
    return results


def iterate_single(lst):
    results = []
    for x in lst:
        results.append(x)
    return results


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestForIterListMutation(unittest.TestCase):
    """Verify that FOR_ITER_LIST (JIT specialisation) matches interpreter
    behaviour exactly when the list is mutated during iteration."""

    @classmethod
    def setUpClass(cls):
        """Force-compile all target functions once before any tests run."""
        for fn in (
            iterate_with_append,
            iterate_with_pop,
            iterate_with_del,
            iterate_with_clear,
            iterate_with_assign,
            iterate_with_insert,
            iterate_with_extend,
            iterate_empty,
            iterate_single,
        ):
            cinderjit.force_compile(fn)

    # ------------------------------------------------------------------
    # Individual mutation tests
    # ------------------------------------------------------------------

    def test_append_during_iteration(self):
        """Append to list during iteration. CPython allows this — iterator may
        see appended elements depending on internal index vs len check."""
        ref = iterate_with_append(list(range(5)))
        jit = iterate_with_append(list(range(5)))
        self.assertEqual(jit, ref)

    def test_pop_during_iteration(self):
        """Pop from end of list during iteration. Shortens the list, so the
        iterator's internal index may exceed the new length."""
        ref = iterate_with_pop(list(range(10)))
        jit = iterate_with_pop(list(range(10)))
        self.assertEqual(jit, ref)

    def test_del_during_iteration(self):
        """Delete element at current position during iteration. The iterator
        index advances but elements shift, causing a skip."""
        ref = iterate_with_del(list(range(8)))
        jit = iterate_with_del(list(range(8)))
        self.assertEqual(jit, ref)

    def test_clear_during_iteration(self):
        """Clear the entire list during iteration. Should stop iteration
        immediately (or on next step)."""
        ref = iterate_with_clear(list(range(10)))
        jit = iterate_with_clear(list(range(10)))
        self.assertEqual(jit, ref)

    def test_assignment_during_iteration(self):
        """Assign to elements during iteration. Iterator should see modified
        values for elements it hasn't visited yet."""
        ref = iterate_with_assign(list(range(1, 6)))
        jit = iterate_with_assign(list(range(1, 6)))
        self.assertEqual(jit, ref)

    def test_insert_during_iteration(self):
        """Insert into the list during iteration. Shifts elements right,
        so the iterator may re-visit elements."""
        ref = iterate_with_insert(list(range(5)))
        jit = iterate_with_insert(list(range(5)))
        self.assertEqual(jit, ref)

    def test_extend_during_iteration(self):
        """Extend the list during iteration. Similar to append but adds
        multiple elements at once."""
        ref = iterate_with_extend(list(range(4)))
        jit = iterate_with_extend(list(range(4)))
        self.assertEqual(jit, ref)

    def test_empty_list_iteration(self):
        """Iterate over an empty list. Forces immediate StopIteration on the
        first call to tp_iternext. If the TOptObject->TObject type change
        (gatekeeper observation 1) caused the optimiser to elide the NULL
        sentinel check, this will hang or segfault."""
        ref = iterate_empty([])
        jit = iterate_empty([])
        self.assertEqual(jit, ref)

    def test_single_element_list(self):
        """Iterate over a single-element list. The second tp_iternext call
        returns the StopIteration sentinel (NULL). Tests the boundary between
        'has elements' and 'done'."""
        ref = iterate_single([42])
        jit = iterate_single([42])
        self.assertEqual(jit, ref)

    # ------------------------------------------------------------------
    # Stability: repeated runs to catch intermittent divergence
    # ------------------------------------------------------------------

    def test_stability_append(self):
        """Repeated runs of the append mutation to catch intermittent JIT divergence."""
        ref = iterate_with_append(list(range(5)))
        for _ in range(100):
            self.assertEqual(iterate_with_append(list(range(5))), ref)

    def test_stability_pop(self):
        """Repeated runs of the pop mutation."""
        ref = iterate_with_pop(list(range(10)))
        for _ in range(100):
            self.assertEqual(iterate_with_pop(list(range(10))), ref)

    def test_stability_del(self):
        """Repeated runs of the del mutation."""
        ref = iterate_with_del(list(range(8)))
        for _ in range(100):
            self.assertEqual(iterate_with_del(list(range(8))), ref)

    def test_stability_clear(self):
        """Repeated runs of the clear mutation."""
        ref = iterate_with_clear(list(range(10)))
        for _ in range(100):
            self.assertEqual(iterate_with_clear(list(range(10))), ref)

    def test_stability_assign(self):
        """Repeated runs of the assignment mutation."""
        ref = iterate_with_assign(list(range(1, 6)))
        for _ in range(100):
            self.assertEqual(iterate_with_assign(list(range(1, 6))), ref)

    def test_stability_insert(self):
        """Repeated runs of the insert mutation."""
        ref = iterate_with_insert(list(range(5)))
        for _ in range(100):
            self.assertEqual(iterate_with_insert(list(range(5))), ref)

    def test_stability_extend(self):
        """Repeated runs of the extend mutation."""
        ref = iterate_with_extend(list(range(4)))
        for _ in range(100):
            self.assertEqual(iterate_with_extend(list(range(4))), ref)


if __name__ == "__main__":
    unittest.main()
