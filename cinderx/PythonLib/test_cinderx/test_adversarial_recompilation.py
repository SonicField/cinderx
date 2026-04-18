"""Adversarial tests for C-API slow path under recompilation stress.

Pythia gap #2: The C-API slow path has been correctness-tested but never
stress-tested under recompilation — the exact scenario that produced the
original crash (builder diamond CFG).

Falsification target:
  The emitCond approach works during the simplify pass. When force_compile
  is called again on an already-compiled function, the JIT discards the
  old compiled code and recompiles from scratch. If the recompilation
  process interacts badly with the speculative expansion (e.g., stale
  FrameState references, dangling register allocations, or the simplify
  pass seeing partially-processed HIR), it could crash — reproducing the
  original builder diamond CFG failure in a different form.

Test strategy:
  1. Compile function with type A → specializes for A
  2. Exercise slow path with type B
  3. Force recompilation (force_compile again)
  4. Exercise both fast and slow paths on recompiled code
  5. Repeat multiple times to stress recompilation
  6. Also test recompilation with different type profiles
"""
import sys
import os
import unittest
import gc

try:
    import cinderjit
    HAS_JIT = True
except ImportError:
    HAS_JIT = False


@unittest.skipUnless(HAS_JIT, "requires CinderX JIT")
@unittest.skipUnless(os.environ.get("CINDERX_SPECEXP"), "requires CINDERX_SPECEXP=1")
class TestSlowPathRecompilation(unittest.TestCase):
    """Test C-API slow path correctness across recompilation cycles."""

    def test_recompile_after_slow_path_exercise(self):
        """Recompile after exercising slow path — recompiled code must still work."""
        class TypeA:
            value = "A"

        class TypeB:
            value = "B"

        def get_value(obj):
            return obj.value

        # Phase 1: Compile and warm with TypeA
        for _ in range(100):
            get_value(TypeA())
        cinderjit.force_compile(get_value)
        self.assertEqual(get_value(TypeA()), "A")

        # Phase 2: Exercise slow path with TypeB
        for _ in range(100):
            result = get_value(TypeB())
            self.assertEqual(result, "B")

        # Phase 3: Force recompilation
        cinderjit.force_compile(get_value)

        # Phase 4: Both paths must still work
        self.assertEqual(get_value(TypeA()), "A", "Fast path broken after recompilation")
        self.assertEqual(get_value(TypeB()), "B", "Slow path broken after recompilation")

    def test_repeated_recompilation_cycles(self):
        """Multiple recompilation cycles — each must produce correct results."""
        class TypeA:
            attr = 10

        class TypeB:
            attr = 20

        class TypeC:
            attr = 30

        def read_attr(obj):
            return obj.attr

        types = [TypeA, TypeB, TypeC]

        for cycle in range(5):
            # Warm with one type
            warm_type = types[cycle % len(types)]
            for _ in range(100):
                read_attr(warm_type())

            cinderjit.force_compile(read_attr)

            # Verify all types work after this compilation
            for t in types:
                result = read_attr(t())
                self.assertEqual(result, t.attr,
                                 f"Cycle {cycle}, type {t.__name__}: "
                                 f"got {result}, expected {t.attr}")

    def test_recompile_multi_guard_function(self):
        """Recompile function with multiple GuardType+LoadAttr pairs."""
        class TypeA:
            x = 1
            y = 2

        class TypeB:
            x = 10
            y = 20

        def multi_attr(obj):
            return obj.x + obj.y

        # Phase 1: Compile with TypeA
        for _ in range(100):
            multi_attr(TypeA())
        cinderjit.force_compile(multi_attr)
        self.assertEqual(multi_attr(TypeA()), 3)

        # Phase 2: Slow path
        self.assertEqual(multi_attr(TypeB()), 30)

        # Phase 3: Recompile
        cinderjit.force_compile(multi_attr)

        # Phase 4: Both must work
        self.assertEqual(multi_attr(TypeA()), 3)
        self.assertEqual(multi_attr(TypeB()), 30)

    def test_recompile_two_arg_function(self):
        """Recompile function taking two heap-type args (two independent guards)."""
        class TypeA:
            val = "a"

        class TypeB:
            val = "b"

        class TypeC:
            val = "c"

        def combine(x, y):
            return x.val + y.val

        # Phase 1: Compile with A, B
        for _ in range(100):
            combine(TypeA(), TypeB())
        cinderjit.force_compile(combine)
        self.assertEqual(combine(TypeA(), TypeB()), "ab")

        # Phase 2: Mixed slow paths
        self.assertEqual(combine(TypeC(), TypeB()), "cb")
        self.assertEqual(combine(TypeA(), TypeC()), "ac")
        self.assertEqual(combine(TypeC(), TypeC()), "cc")

        # Phase 3: Recompile
        cinderjit.force_compile(combine)

        # Phase 4: All combinations must work
        self.assertEqual(combine(TypeA(), TypeB()), "ab")
        self.assertEqual(combine(TypeC(), TypeB()), "cb")
        self.assertEqual(combine(TypeA(), TypeC()), "ac")
        self.assertEqual(combine(TypeC(), TypeC()), "cc")

    def test_recompile_during_heavy_slow_path_use(self):
        """Recompile while slow path is heavily exercised — stress test."""
        class Original:
            data = "original"

        class Variant:
            data = "variant"

        def reader(obj):
            return obj.data

        # Initial compilation with Original
        for _ in range(100):
            reader(Original())
        cinderjit.force_compile(reader)

        # Heavy slow path exercise interspersed with recompilation
        for round_num in range(10):
            # Exercise slow path 100x
            for _ in range(100):
                self.assertEqual(reader(Variant()), "variant")

            # Recompile
            cinderjit.force_compile(reader)

            # Verify both paths immediately after recompile
            self.assertEqual(reader(Original()), "original",
                             f"Round {round_num}: fast path broken after recompile")
            self.assertEqual(reader(Variant()), "variant",
                             f"Round {round_num}: slow path broken after recompile")

    def test_recompile_with_gc_pressure(self):
        """Recompile with GC pressure — references must survive collection."""
        class TypeA:
            name = "alpha"

        class TypeB:
            name = "beta"

        def get_name(obj):
            return obj.name

        for _ in range(100):
            get_name(TypeA())
        cinderjit.force_compile(get_name)

        for cycle in range(5):
            # Create GC pressure
            garbage = [TypeA() for _ in range(10000)]
            del garbage
            gc.collect()

            # Exercise slow path
            self.assertEqual(get_name(TypeB()), "beta")

            # Recompile under GC pressure
            more_garbage = [TypeB() for _ in range(10000)]
            cinderjit.force_compile(get_name)
            del more_garbage
            gc.collect()

            # Must still work
            self.assertEqual(get_name(TypeA()), "alpha",
                             f"Cycle {cycle}: broken after recompile+GC")
            self.assertEqual(get_name(TypeB()), "beta",
                             f"Cycle {cycle}: broken after recompile+GC")

    def test_recompile_chained_attr_access(self):
        """Recompile function with chained attribute access (obj.inner.value)."""
        class Inner:
            value = 42

        class Outer:
            def __init__(self, inner):
                self.inner = inner

        class AltInner:
            value = 99

        class AltOuter:
            def __init__(self, inner):
                self.inner = inner

        def chained(obj):
            return obj.inner.value

        inner = Inner()
        outer = Outer(inner)
        for _ in range(100):
            chained(outer)
        cinderjit.force_compile(chained)

        # Exercise all path combinations
        self.assertEqual(chained(Outer(Inner())), 42)
        self.assertEqual(chained(Outer(AltInner())), 99)
        self.assertEqual(chained(AltOuter(Inner())), 42)
        self.assertEqual(chained(AltOuter(AltInner())), 99)

        # Recompile
        cinderjit.force_compile(chained)

        # All must still work
        self.assertEqual(chained(Outer(Inner())), 42)
        self.assertEqual(chained(Outer(AltInner())), 99)
        self.assertEqual(chained(AltOuter(Inner())), 42)
        self.assertEqual(chained(AltOuter(AltInner())), 99)

    def test_recompile_exception_on_slow_path(self):
        """Slow path that raises AttributeError — must propagate correctly
        across recompilation."""
        class HasAttr:
            value = "exists"

        class NoAttr:
            pass  # No 'value' attribute

        def access_value(obj):
            return obj.value

        for _ in range(100):
            access_value(HasAttr())
        cinderjit.force_compile(access_value)

        # Fast path works
        self.assertEqual(access_value(HasAttr()), "exists")

        # Slow path raises AttributeError (PyObject_GetAttr returns NULL)
        with self.assertRaises(AttributeError):
            access_value(NoAttr())

        # Recompile
        cinderjit.force_compile(access_value)

        # Both behaviors must persist
        self.assertEqual(access_value(HasAttr()), "exists")
        with self.assertRaises(AttributeError):
            access_value(NoAttr())

    def test_recompile_property_on_slow_path(self):
        """Slow path accessing a @property — PyObject_GetAttr calls the getter."""
        class Direct:
            value = "direct"

        class WithProperty:
            @property
            def value(self):
                return "computed"

        def get_value(obj):
            return obj.value

        for _ in range(100):
            get_value(Direct())
        cinderjit.force_compile(get_value)

        # Fast path
        self.assertEqual(get_value(Direct()), "direct")
        # Slow path — property getter via PyObject_GetAttr
        self.assertEqual(get_value(WithProperty()), "computed")

        # Recompile
        cinderjit.force_compile(get_value)

        # Both must work
        self.assertEqual(get_value(Direct()), "direct")
        self.assertEqual(get_value(WithProperty()), "computed")


if __name__ == "__main__":
    unittest.main()
