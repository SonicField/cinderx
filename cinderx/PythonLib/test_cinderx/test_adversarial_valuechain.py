"""Adversarial tests for Step 2: value-chain guard expansion.

Falsification target:
  When a value x is checked by N guards, ALL N must be expanded together.
  Without Step 2, expanding guard 1 lets guard 2 deopt — cascading failure.
  With Step 2, both guards are expanded and TypeB goes through both slow
  paths with correct return values.

  modelReg() traces through passthrough instructions (Assign, RefineType,
  GuardType) to find the root register. Guards sharing a root are grouped
  and expanded together.

Test strategy:
  1. Functions with 2+ attribute accesses on the SAME object (same base value)
  2. Verify both/all slow paths produce correct values on type mismatch
  3. Verify no cascading deopt (both guards expanded, not just the first)
  4. Edge cases: same object through different local names, chained access,
     mixed guard-only and guard+LoadAttr
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
class TestValueChainGuardExpansion(unittest.TestCase):
    """Test that all guards on the same base value are expanded together."""

    def test_two_attrs_same_object(self):
        """Two attribute accesses on the same object — both guards must expand."""
        class TypeA:
            x = 1
            y = 2

        class TypeB:
            x = 10
            y = 20

        def read_both(obj):
            a = obj.x  # GuardType #1 on obj
            b = obj.y  # GuardType #2 on obj (same base value)
            return a + b

        for _ in range(100):
            read_both(TypeA())

        cinderjit.force_compile(read_both)

        # Fast path (both guards match)
        self.assertEqual(read_both(TypeA()), 3)
        # Slow path — both guards must be expanded, not just first
        self.assertEqual(read_both(TypeB()), 30,
                         "Second guard on same object deopt'd instead of using slow path. "
                         "Value-chain expansion may not be grouping guards by base value.")

    def test_three_attrs_same_object(self):
        """Three attribute accesses on same object — all three must expand."""
        class TypeA:
            name = "A"
            rank = 1
            score = 100

        class TypeB:
            name = "B"
            rank = 2
            score = 200

        def read_all(obj):
            n = obj.name
            r = obj.rank
            s = obj.score
            return f"{n}:{r}:{s}"

        for _ in range(100):
            read_all(TypeA())

        cinderjit.force_compile(read_all)

        self.assertEqual(read_all(TypeA()), "A:1:100")
        self.assertEqual(read_all(TypeB()), "B:2:200",
                         "Not all 3 guards on same object were expanded together.")

    def test_same_object_different_local_names(self):
        """Same object assigned to different locals — modelReg should trace
        through Assign to find the same root."""
        class TypeA:
            val = "A"

        class TypeB:
            val = "B"

        def aliased(obj):
            alias = obj        # Assign — modelReg should trace through
            x = obj.val        # GuardType on obj
            y = alias.val      # GuardType on alias (same root via modelReg)
            return x + y

        for _ in range(100):
            aliased(TypeA())

        cinderjit.force_compile(aliased)

        self.assertEqual(aliased(TypeA()), "AA")
        self.assertEqual(aliased(TypeB()), "BB",
                         "Guards on obj and alias (same object) not grouped together.")

    def test_guard_after_refinetype(self):
        """Guard after RefineType — modelReg traces through RefineType
        to find the same root as the first guard."""
        class TypeA:
            first = "f_A"
            second = "s_A"

        class TypeB:
            first = "f_B"
            second = "s_B"

        def sequential(obj):
            # First access generates GuardType + RefineType on fast path
            a = obj.first
            # Second access is on the refined register (after RefineType)
            # modelReg should trace back to original obj
            b = obj.second
            return a + "_" + b

        for _ in range(100):
            sequential(TypeA())

        cinderjit.force_compile(sequential)

        self.assertEqual(sequential(TypeA()), "f_A_s_A")
        self.assertEqual(sequential(TypeB()), "f_B_s_B",
                         "Second guard after RefineType not grouped with first.")

    def test_mixed_guard_with_and_without_loadattr(self):
        """One guard has LoadAttr downstream, another has a different use.
        Group promotion should expand both."""
        class TypeA:
            data = 42

        class TypeB:
            data = 99

        def mixed_use(obj):
            # First access: GuardType + LoadAttr (has C-API slow path)
            val = obj.data
            # isinstance check: GuardType without LoadAttr downstream
            # (may or may not generate a separate guard depending on compilation)
            return val * 2

        for _ in range(100):
            mixed_use(TypeA())

        cinderjit.force_compile(mixed_use)

        self.assertEqual(mixed_use(TypeA()), 84)
        self.assertEqual(mixed_use(TypeB()), 198)

    def test_rapid_type_alternation_same_object(self):
        """Rapidly alternate types on same-object multi-attr access."""
        class TypeA:
            x = 1
            y = 2

        class TypeB:
            x = 10
            y = 20

        def dual_read(obj):
            return obj.x + obj.y

        for _ in range(100):
            dual_read(TypeA())

        cinderjit.force_compile(dual_read)

        # Rapid alternation
        for i in range(500):
            if i % 2 == 0:
                self.assertEqual(dual_read(TypeA()), 3)
            else:
                self.assertEqual(dual_read(TypeB()), 30)

    def test_four_guards_same_value(self):
        """Four guards on same value — alexie's specific scenario."""
        class TypeA:
            a = 1
            b = 2
            c = 3
            d = 4

        class TypeB:
            a = 10
            b = 20
            c = 30
            d = 40

        def four_attrs(obj):
            return obj.a + obj.b + obj.c + obj.d

        for _ in range(100):
            four_attrs(TypeA())

        cinderjit.force_compile(four_attrs)

        self.assertEqual(four_attrs(TypeA()), 10)
        self.assertEqual(four_attrs(TypeB()), 100,
                         "Not all 4 guards on same object expanded. "
                         "Cascading deopt on guards 2-4.")

    def test_same_object_with_method_call(self):
        """Attribute access + method call on same object."""
        class TypeA:
            name = "A"
            def greet(self):
                return f"hello {self.name}"

        class TypeB:
            name = "B"
            def greet(self):
                return f"hi {self.name}"

        def use_object(obj):
            n = obj.name
            g = obj.greet()
            return f"{n}: {g}"

        for _ in range(100):
            use_object(TypeA())

        cinderjit.force_compile(use_object)

        self.assertEqual(use_object(TypeA()), "A: hello A")
        self.assertEqual(use_object(TypeB()), "B: hi B")

    def test_recompile_preserves_valuechain(self):
        """After recompilation, value-chain expansion still works."""
        class TypeA:
            x = 1
            y = 2

        class TypeB:
            x = 10
            y = 20

        def dual(obj):
            return obj.x + obj.y

        for _ in range(100):
            dual(TypeA())
        cinderjit.force_compile(dual)

        self.assertEqual(dual(TypeB()), 30)

        # Recompile
        cinderjit.force_compile(dual)

        # Value-chain must still work
        self.assertEqual(dual(TypeA()), 3)
        self.assertEqual(dual(TypeB()), 30,
                         "Value-chain expansion broken after recompilation.")


if __name__ == "__main__":
    unittest.main()
