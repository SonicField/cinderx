"""Adversarial tests for emitCond Snapshot propagation.

Pythia gap #1: The emitCond Snapshot propagation fix was verified only for
the single-Snapshot case. This test constructs cases where emitCond splits
a block containing MULTIPLE GuardType+LoadAttr pairs — each potentially
needing distinct FrameState at different bytecode offsets.

Falsification target:
  The Snapshot propagation (simplify.cpp:374-376) walks backward to find
  the MOST RECENT Snapshot and propagates only that one to the tail block.
  If the tail block contains a second GuardType+LoadAttr pair whose correct
  FrameState differs from the propagated one, the deopt/CheckExc could
  reference the wrong bytecode offset — crash or wrong behavior.

Test strategy:
  1. Create functions with multiple consecutive attribute accesses on
     different heap-type variables (generates multiple GuardType+LoadAttr
     pairs in the same basic block).
  2. Exercise both fast path (matching types) and slow path (mismatched
     types) for each access independently.
  3. Verify correct return values in all combinations.
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
class TestEmitCondMultiGuard(unittest.TestCase):
    """Test emitCond with multiple GuardType+LoadAttr pairs in one block."""

    def test_two_consecutive_attr_accesses_fast_fast(self):
        """Two heap-type attr accesses, both matching (fast path for both)."""
        class TypeA:
            value = "A_val"

        class TypeB:
            value = "B_val"

        def two_attrs(a, b):
            # Each generates GuardType + LoadAttr
            x = a.value
            y = b.value
            return x + "_" + y

        # Warm up IC with these types
        for _ in range(100):
            two_attrs(TypeA(), TypeB())

        cinderjit.force_compile(two_attrs)

        # Both fast path
        result = two_attrs(TypeA(), TypeB())
        self.assertEqual(result, "A_val_B_val",
                         "Two consecutive fast-path attr accesses returned wrong result")

    def test_two_consecutive_attr_accesses_fast_slow(self):
        """First attr matches (fast), second mismatches (slow C-API path)."""
        class TypeA:
            value = "A_val"

        class TypeB:
            value = "B_val"

        class TypeC:
            value = "C_val"

        def two_attrs(a, b):
            x = a.value
            y = b.value
            return x + "_" + y

        # Warm IC with TypeA, TypeB
        for _ in range(100):
            two_attrs(TypeA(), TypeB())

        cinderjit.force_compile(two_attrs)

        # TypeA matches (fast), TypeC mismatches second guard (slow)
        result = two_attrs(TypeA(), TypeC())
        self.assertEqual(result, "A_val_C_val",
                         "Fast+slow path combination returned wrong result. "
                         "Second GuardType may have wrong FrameState from Snapshot propagation.")

    def test_two_consecutive_attr_accesses_slow_fast(self):
        """First attr mismatches (slow), second matches (fast)."""
        class TypeA:
            value = "A_val"

        class TypeB:
            value = "B_val"

        class TypeD:
            value = "D_val"

        def two_attrs(a, b):
            x = a.value
            y = b.value
            return x + "_" + y

        for _ in range(100):
            two_attrs(TypeA(), TypeB())

        cinderjit.force_compile(two_attrs)

        # TypeD mismatches first guard (slow), TypeB matches second (fast)
        result = two_attrs(TypeD(), TypeB())
        self.assertEqual(result, "D_val_B_val",
                         "Slow+fast path combination returned wrong result. "
                         "First emitCond split may corrupt second guard's context.")

    def test_two_consecutive_attr_accesses_slow_slow(self):
        """Both attrs mismatch (slow C-API path for both)."""
        class TypeA:
            value = "A_val"

        class TypeB:
            value = "B_val"

        class TypeC:
            value = "C_val"

        class TypeD:
            value = "D_val"

        def two_attrs(a, b):
            x = a.value
            y = b.value
            return x + "_" + y

        for _ in range(100):
            two_attrs(TypeA(), TypeB())

        cinderjit.force_compile(two_attrs)

        # Both mismatch — both go through C-API slow path
        result = two_attrs(TypeC(), TypeD())
        self.assertEqual(result, "C_val_D_val",
                         "Double slow path returned wrong result. "
                         "Both guards hit C-API PyObject_GetAttr — FrameState must be distinct.")

    def test_three_consecutive_attr_accesses_mixed(self):
        """Three consecutive attr accesses with mixed fast/slow paths."""
        class TypeA:
            name = "A"

        class TypeB:
            name = "B"

        class TypeC:
            name = "C"

        class TypeX:
            name = "X"

        class TypeY:
            name = "Y"

        def three_attrs(a, b, c):
            x = a.name
            y = b.name
            z = c.name
            return f"{x}{y}{z}"

        for _ in range(100):
            three_attrs(TypeA(), TypeB(), TypeC())

        cinderjit.force_compile(three_attrs)

        # All fast
        self.assertEqual(three_attrs(TypeA(), TypeB(), TypeC()), "ABC")
        # First slow, rest fast
        self.assertEqual(three_attrs(TypeX(), TypeB(), TypeC()), "XBC")
        # Middle slow
        self.assertEqual(three_attrs(TypeA(), TypeX(), TypeC()), "AXC")
        # Last slow
        self.assertEqual(three_attrs(TypeA(), TypeB(), TypeX()), "ABX")
        # All slow
        self.assertEqual(three_attrs(TypeX(), TypeY(), TypeX()), "XYX")

    def test_attr_access_with_intermediate_computation(self):
        """Attr accesses separated by computation — different bytecode offsets."""
        class Counter:
            count = 0

        class Multiplier:
            factor = 2

        class OtherCounter:
            count = 100

        class OtherMultiplier:
            factor = 10

        def compute(counter, mult):
            c = counter.count   # GuardType+LoadAttr #1
            base = c + 1        # Intermediate computation
            f = mult.factor     # GuardType+LoadAttr #2 (different bytecode offset)
            return base * f

        for _ in range(100):
            compute(Counter(), Multiplier())

        cinderjit.force_compile(compute)

        # Fast+fast
        self.assertEqual(compute(Counter(), Multiplier()), 2)
        # Slow+slow (different types)
        self.assertEqual(compute(OtherCounter(), OtherMultiplier()), 1010)
        # Mixed
        self.assertEqual(compute(Counter(), OtherMultiplier()), 10)
        self.assertEqual(compute(OtherCounter(), Multiplier()), 202)

    def test_attr_access_result_used_as_operand(self):
        """First attr result used in second attr access — chained dependency."""
        class Container:
            inner = None

            def __init__(self, inner=None):
                self.inner = inner

        class Leaf:
            value = 42

        class AltContainer:
            inner = None

            def __init__(self, inner=None):
                self.inner = inner

        class AltLeaf:
            value = 99

        def chained(obj):
            inner = obj.inner   # GuardType+LoadAttr #1
            val = inner.value   # GuardType+LoadAttr #2 on result of #1
            return val

        leaf = Leaf()
        container = Container(leaf)
        for _ in range(100):
            chained(container)

        cinderjit.force_compile(chained)

        # Fast path for both
        self.assertEqual(chained(Container(Leaf())), 42)
        # Outer slow, inner still Leaf (fast on inner)
        self.assertEqual(chained(AltContainer(Leaf())), 42)
        # Outer fast, inner slow
        self.assertEqual(chained(Container(AltLeaf())), 99)
        # Both slow
        self.assertEqual(chained(AltContainer(AltLeaf())), 99)

    def test_rapid_type_alternation_stress(self):
        """Rapidly alternate types to stress emitCond split paths."""
        class TypeA:
            val = 1
        class TypeB:
            val = 2
        class TypeC:
            val = 3
        class TypeD:
            val = 4

        types_ab = [TypeA, TypeB]
        types_cd = [TypeC, TypeD]

        def dual_access(a, b):
            return a.val + b.val

        # Warm with A, C
        for _ in range(100):
            dual_access(TypeA(), TypeC())

        cinderjit.force_compile(dual_access)

        # Rapid alternation — stress both guard paths
        for i in range(1000):
            a_cls = types_ab[i % 2]
            b_cls = types_cd[i % 2]
            result = dual_access(a_cls(), b_cls())
            expected = a_cls.val + b_cls.val
            self.assertEqual(result, expected,
                             f"Iteration {i}: got {result}, expected {expected}")


if __name__ == "__main__":
    unittest.main()
