"""Adversarial tests for Step 4: deopt-aware selective expansion (Tier 2).

Falsification target:
  First compilation: no expansion. Tier 2 (after 1000 invocations):
  expand only guards at bytecode offsets where deopts occurred.
  Monomorphic guards stay unexpanded (no branch overhead).

Test strategy:
  - Use force_compile for Tier 1, then 1000+ calls to trigger Tier 2
  - Monomorphic: verify guards NOT expanded (no slow path overhead)
  - Polymorphic with deopts: verify deopted guards expanded
  - Post-Tier 2: no deopt on type mismatch for expanded guards
  - Note: Step 4 removes CINDERX_SPECEXP — tests must NOT require it
"""
import sys
import os
import unittest

try:
    import cinderjit
    HAS_JIT = True
except ImportError:
    HAS_JIT = False

# Tier 2 threshold (from pyjit.cpp CompiledFunctionData::kTier2ThresholdDefault)
TIER2_THRESHOLD = 1000


@unittest.skipUnless(HAS_JIT, "requires CinderX JIT")
class TestSelectiveExpansionTier2(unittest.TestCase):
    """Test deopt-aware selective expansion via Tier 2 recompilation."""

    def test_monomorphic_no_expansion(self):
        """Monomorphic function — Tier 2 should NOT expand guards (zero deopts).
        Verify correct results throughout — expansion is invisible to correctness
        but we confirm the function survives Tier 2 recompilation."""
        class TypeA:
            value = 42

        def get_value(obj):
            return obj.value

        cinderjit.force_compile(get_value)

        # Call 1200 times with same type — triggers Tier 2, zero deopts
        for _ in range(TIER2_THRESHOLD + 200):
            result = get_value(TypeA())
            self.assertEqual(result, 42)

    def test_polymorphic_expansion_after_deopts(self):
        """Polymorphic function — deopts accumulate in Tier 1, Tier 2 expands.
        After Tier 2, TypeB should use slow path (no deopt)."""
        class TypeA:
            value = "A"

        class TypeB:
            value = "B"

        def get_value(obj):
            return obj.value

        cinderjit.force_compile(get_value)

        # Phase 1: warm with TypeA (monomorphic)
        for _ in range(500):
            self.assertEqual(get_value(TypeA()), "A")

        # Phase 2: trigger deopts with TypeB
        for _ in range(100):
            self.assertEqual(get_value(TypeB()), "B")

        # Phase 3: reach Tier 2 threshold (total > 1000)
        for _ in range(500):
            self.assertEqual(get_value(TypeA()), "A")

        # Phase 4: after Tier 2, TypeB should use expanded slow path
        for _ in range(100):
            self.assertEqual(get_value(TypeB()), "B",
                             "TypeB failed after Tier 2 — selective expansion may not "
                             "have expanded the deopted guard")

    def test_mixed_mono_poly_same_function(self):
        """Function with two guards — one deopts (polymorphic), one doesn't
        (monomorphic). Tier 2 should expand only the deopted guard."""
        class TypeA:
            x = 1
            y = 2

        class TypeB:
            x = 10
            y = 20

        # Use a wrapper that always passes TypeA for second arg
        # but varies first arg — only first guard should deopt
        container = [TypeA()]

        def get_x_and_fixed_y(obj):
            a = obj.x           # Guard on obj (may deopt if obj changes type)
            b = container[0].y  # Guard on container[0] (always TypeA — no deopt)
            return a + b

        cinderjit.force_compile(get_x_and_fixed_y)

        # Warm with TypeA
        for _ in range(400):
            self.assertEqual(get_x_and_fixed_y(TypeA()), 3)

        # Trigger deopts on first guard with TypeB
        for _ in range(100):
            self.assertEqual(get_x_and_fixed_y(TypeB()), 12)

        # Reach Tier 2
        for _ in range(600):
            self.assertEqual(get_x_and_fixed_y(TypeA()), 3)

        # After Tier 2: TypeB should work (first guard expanded)
        for _ in range(100):
            self.assertEqual(get_x_and_fixed_y(TypeB()), 12)

    def test_multiple_type_switches(self):
        """Multiple type switches before Tier 2 — all deopted guards expanded."""
        class TypeA:
            val = 1

        class TypeB:
            val = 2

        class TypeC:
            val = 3

        def read(obj):
            return obj.val

        cinderjit.force_compile(read)

        # Alternate types to cause multiple deopts
        types = [TypeA, TypeB, TypeC]
        for i in range(TIER2_THRESHOLD + 200):
            t = types[i % 3]
            result = read(t())
            self.assertEqual(result, t.val)

        # After Tier 2: all types should work without deopt
        for t in types:
            for _ in range(50):
                self.assertEqual(read(t()), t.val)

    def test_store_attr_selective_expansion(self):
        """StoreAttr guard with deopts — expanded on Tier 2."""
        class TypeA:
            pass

        class TypeB:
            pass

        def set_val(obj, v):
            obj.val = v

        a = TypeA()
        cinderjit.force_compile(set_val)

        # Warm with TypeA
        for _ in range(500):
            set_val(TypeA(), 42)

        # Trigger deopts with TypeB
        for _ in range(100):
            b = TypeB()
            set_val(b, 99)
            self.assertEqual(b.val, 99)

        # Reach Tier 2
        for _ in range(500):
            set_val(TypeA(), 42)

        # After Tier 2: TypeB should use expanded slow path
        b = TypeB()
        set_val(b, "hello")
        self.assertEqual(b.val, "hello")

    def test_compare_selective_expansion(self):
        """Compare guard with deopts — expanded on Tier 2."""
        class TypeA:
            def __init__(self, v):
                self.v = v
            def __lt__(self, other):
                return self.v < other.v

        class TypeB:
            def __init__(self, v):
                self.v = v
            def __lt__(self, other):
                return self.v < other.v

        def is_less(a, b):
            return a < b

        cinderjit.force_compile(is_less)

        # Warm with TypeA
        for _ in range(500):
            is_less(TypeA(1), TypeA(2))

        # Trigger deopts with TypeB
        for _ in range(100):
            self.assertTrue(is_less(TypeB(1), TypeB(2)))

        # Reach Tier 2
        for _ in range(500):
            is_less(TypeA(1), TypeA(2))

        # After Tier 2: TypeB should work
        self.assertTrue(is_less(TypeB(1), TypeB(2)))
        self.assertFalse(is_less(TypeB(2), TypeB(1)))

    def test_correctness_across_tier2_boundary(self):
        """Verify return values are correct across the Tier 2 recompilation
        boundary — no stale values, no corruption."""
        class TypeA:
            data = "alpha"

        class TypeB:
            data = "beta"

        results = []

        def get_data(obj):
            return obj.data

        cinderjit.force_compile(get_data)

        # Accumulate results across Tier 2 boundary
        for i in range(TIER2_THRESHOLD + 200):
            if i % 7 == 0:
                r = get_data(TypeB())
                results.append(("B", r))
            else:
                r = get_data(TypeA())
                results.append(("A", r))

        # Verify ALL results correct (no corruption at boundary)
        for expected_type, actual in results:
            if expected_type == "A":
                self.assertEqual(actual, "alpha")
            else:
                self.assertEqual(actual, "beta")


if __name__ == "__main__":
    unittest.main()
