"""Adversarial tests for Step 3: table-driven C-API slow paths.

Falsification target:
  StoreAttr and Compare downstream ops now get C-API slow paths
  instead of deopt on type mismatch. StoreAttr uses PyObject_SetAttr,
  Compare uses PyObject_RichCompare.

Test strategy:
  - StoreAttr: warm with TypeA, set attr, then call with TypeB
  - Compare: warm with TypeA, compare, then call with TypeB
  - Both: verify no deopt, correct results on type mismatch
  - Edge cases: descriptors, RichCompare returning non-bool
"""
import sys
import os
import unittest

try:
    import cinderjit
    HAS_JIT = True
except ImportError:
    HAS_JIT = False


@unittest.skipUnless(HAS_JIT, "requires CinderX JIT")
@unittest.skipUnless(os.environ.get("CINDERX_SPECEXP"), "requires CINDERX_SPECEXP=1")
class TestStoreAttrSlowPath(unittest.TestCase):
    """Test C-API slow path for StoreAttr (PyObject_SetAttr)."""

    def test_store_attr_type_mismatch(self):
        """Store attribute on mismatched type — PyObject_SetAttr slow path."""
        class TypeA:
            pass

        class TypeB:
            pass

        def set_value(obj, val):
            obj.value = val

        a = TypeA()
        for _ in range(100):
            set_value(a, 42)

        cinderjit.force_compile(set_value)

        # Fast path
        a2 = TypeA()
        set_value(a2, 99)
        self.assertEqual(a2.value, 99)

        # Slow path — TypeB via PyObject_SetAttr
        b = TypeB()
        set_value(b, "hello")
        self.assertEqual(b.value, "hello",
                         "StoreAttr slow path did not set attribute correctly on TypeB")

    def test_store_attr_alternating_types(self):
        """Rapidly alternate types for store attr."""
        class TypeA:
            pass

        class TypeB:
            pass

        def set_name(obj, name):
            obj.name = name

        a = TypeA()
        for _ in range(100):
            set_name(a, "A")

        cinderjit.force_compile(set_name)

        for i in range(200):
            if i % 2 == 0:
                obj = TypeA()
                set_name(obj, f"A_{i}")
                self.assertEqual(obj.name, f"A_{i}")
            else:
                obj = TypeB()
                set_name(obj, f"B_{i}")
                self.assertEqual(obj.name, f"B_{i}")

    def test_store_attr_with_descriptor(self):
        """Store attr where type has a descriptor with __set__ —
        PyObject_SetAttr should invoke the descriptor protocol."""
        class Validator:
            def __set_name__(self, owner, name):
                self.name = name

            def __set__(self, obj, value):
                if not isinstance(value, int):
                    raise TypeError(f"{self.name} must be int")
                obj.__dict__[self.name] = value

            def __get__(self, obj, objtype=None):
                if obj is None:
                    return self
                return obj.__dict__.get(self.name, 0)

        class TypeA:
            score = Validator()

        class TypeB:
            score = Validator()

        def set_score(obj, val):
            obj.score = val

        a = TypeA()
        for _ in range(100):
            set_score(a, 42)

        cinderjit.force_compile(set_score)

        # Fast path
        a2 = TypeA()
        set_score(a2, 10)
        self.assertEqual(a2.score, 10)

        # Slow path — TypeB with same descriptor
        b = TypeB()
        set_score(b, 20)
        self.assertEqual(b.score, 20)

        # Slow path — descriptor rejects non-int
        with self.assertRaises(TypeError):
            set_score(b, "not_int")

    def test_store_and_load_same_object(self):
        """Store then load on same object — both guards expanded together."""
        class TypeA:
            data = 0

        class TypeB:
            data = 0

        def set_and_get(obj, val):
            obj.data = val
            return obj.data

        a = TypeA()
        for _ in range(100):
            set_and_get(a, 42)

        cinderjit.force_compile(set_and_get)

        self.assertEqual(set_and_get(TypeA(), 10), 10)
        self.assertEqual(set_and_get(TypeB(), 20), 20,
                         "Store+Load on same mismatched object failed. "
                         "Both guards should be expanded via value-chain.")


@unittest.skipUnless(HAS_JIT, "requires CinderX JIT")
@unittest.skipUnless(os.environ.get("CINDERX_SPECEXP"), "requires CINDERX_SPECEXP=1")
class TestCompareSlowPath(unittest.TestCase):
    """Test C-API slow path for Compare (PyObject_RichCompare)."""

    def test_compare_eq_type_mismatch(self):
        """Equality comparison on mismatched type — RichCompare slow path."""
        class TypeA:
            def __init__(self, val):
                self.val = val

            def __eq__(self, other):
                return self.val == other.val

        class TypeB:
            def __init__(self, val):
                self.val = val

            def __eq__(self, other):
                return self.val == other.val

        def are_equal(a, b):
            return a == b

        ta1 = TypeA(1)
        ta2 = TypeA(1)
        for _ in range(100):
            are_equal(ta1, ta2)

        cinderjit.force_compile(are_equal)

        # Fast path
        self.assertTrue(are_equal(TypeA(5), TypeA(5)))
        self.assertFalse(are_equal(TypeA(5), TypeA(6)))

        # Slow path — TypeB via PyObject_RichCompare
        self.assertTrue(are_equal(TypeB(5), TypeB(5)))
        self.assertFalse(are_equal(TypeB(5), TypeB(6)))

    def test_compare_lt_type_mismatch(self):
        """Less-than comparison on mismatched type."""
        class TypeA:
            def __init__(self, val):
                self.val = val

            def __lt__(self, other):
                return self.val < other.val

        class TypeB:
            def __init__(self, val):
                self.val = val

            def __lt__(self, other):
                return self.val < other.val

        def is_less(a, b):
            return a < b

        for _ in range(100):
            is_less(TypeA(1), TypeA(2))

        cinderjit.force_compile(is_less)

        self.assertTrue(is_less(TypeA(1), TypeA(2)))
        self.assertFalse(is_less(TypeA(2), TypeA(1)))

        # Slow path
        self.assertTrue(is_less(TypeB(1), TypeB(2)))
        self.assertFalse(is_less(TypeB(2), TypeB(1)))

    def test_compare_all_rich_ops(self):
        """All 6 rich comparison ops work on mismatched types."""
        class TypeA:
            def __init__(self, val):
                self.val = val

            def __lt__(self, o): return self.val < o.val
            def __le__(self, o): return self.val <= o.val
            def __eq__(self, o): return self.val == o.val
            def __ne__(self, o): return self.val != o.val
            def __gt__(self, o): return self.val > o.val
            def __ge__(self, o): return self.val >= o.val

        class TypeB:
            def __init__(self, val):
                self.val = val

            def __lt__(self, o): return self.val < o.val
            def __le__(self, o): return self.val <= o.val
            def __eq__(self, o): return self.val == o.val
            def __ne__(self, o): return self.val != o.val
            def __gt__(self, o): return self.val > o.val
            def __ge__(self, o): return self.val >= o.val

        def do_lt(a, b): return a < b
        def do_le(a, b): return a <= b
        def do_eq(a, b): return a == b
        def do_ne(a, b): return a != b
        def do_gt(a, b): return a > b
        def do_ge(a, b): return a >= b

        ops = [do_lt, do_le, do_eq, do_ne, do_gt, do_ge]

        for op in ops:
            for _ in range(100):
                op(TypeA(1), TypeA(2))
            cinderjit.force_compile(op)

        a1, a2 = TypeA(1), TypeA(2)
        b1, b2 = TypeB(1), TypeB(2)

        # Fast path
        self.assertTrue(do_lt(a1, a2))
        self.assertTrue(do_le(a1, a2))
        self.assertFalse(do_eq(a1, a2))
        self.assertTrue(do_ne(a1, a2))
        self.assertFalse(do_gt(a1, a2))
        self.assertFalse(do_ge(a1, a2))

        # Slow path — same results on TypeB
        self.assertTrue(do_lt(b1, b2))
        self.assertTrue(do_le(b1, b2))
        self.assertFalse(do_eq(b1, b2))
        self.assertTrue(do_ne(b1, b2))
        self.assertFalse(do_gt(b1, b2))
        self.assertFalse(do_ge(b1, b2))

    def test_compare_returns_non_bool(self):
        """RichCompare returning non-bool object — must propagate correctly."""
        class TypeA:
            def __init__(self, val):
                self.val = val

            def __eq__(self, other):
                # Return a string instead of bool
                return "equal" if self.val == other.val else "not_equal"

        class TypeB:
            def __init__(self, val):
                self.val = val

            def __eq__(self, other):
                return "yes" if self.val == other.val else "no"

        def compare(a, b):
            return a == b

        for _ in range(100):
            compare(TypeA(1), TypeA(1))

        cinderjit.force_compile(compare)

        self.assertEqual(compare(TypeA(1), TypeA(1)), "equal")
        self.assertEqual(compare(TypeA(1), TypeA(2)), "not_equal")

        # Slow path
        self.assertEqual(compare(TypeB(1), TypeB(1)), "yes")
        self.assertEqual(compare(TypeB(1), TypeB(2)), "no")


@unittest.skipUnless(HAS_JIT, "requires CinderX JIT")
@unittest.skipUnless(os.environ.get("CINDERX_SPECEXP"), "requires CINDERX_SPECEXP=1")
class TestCombinedOps(unittest.TestCase):
    """Test multiple op types on the same object."""

    def test_load_store_compare_same_object(self):
        """Load, store, and compare on same object — all expanded."""
        class TypeA:
            score = 0

        class TypeB:
            score = 0

        def update_and_check(obj, new_score, threshold):
            old = obj.score
            obj.score = new_score
            return obj.score > threshold

        a = TypeA()
        for _ in range(100):
            update_and_check(a, 10, 5)

        cinderjit.force_compile(update_and_check)

        a2 = TypeA()
        self.assertTrue(update_and_check(a2, 10, 5))
        self.assertFalse(update_and_check(a2, 3, 5))

        # Slow path — TypeB
        b = TypeB()
        self.assertTrue(update_and_check(b, 10, 5))
        self.assertFalse(update_and_check(b, 3, 5))


if __name__ == "__main__":
    unittest.main()
