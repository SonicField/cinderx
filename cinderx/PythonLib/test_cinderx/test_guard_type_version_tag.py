"""Inline-correctness sentinels for JIT-specialised ops on subclassed types.

NOT a falsifier for the GuardType version_tag=0 bug — that bug is
unreachable in default-config builds.

Per testkeeper's 2026-04-21 reachability probes
(investigations/probes/aba_reachability_probe.py + tag_check2.py output):
  - GuardType is NOT emitted in default config for either annotation
    guards (gated by emit_type_annotation_guards{false} in
    cinderx/Jit/config.h:159) or LOAD_ATTR_INSTANCE_VALUE (gated by
    builder.cpp:findTypeByVersionTag rejecting version==0 on the HIR
    side, plus single-threaded compile holding the GIL throughout).
  - Therefore reverting the (proposed but not shipped) Option A
    ensureVersionTag fix would NOT cause these tests to fail in
    default config — they would silently pass either way.

What these tests DO cover:
  - BINARY_SUBSCR specialised on a list subclass (inline GetArrayItem):
    a non-subscriptable type passed at runtime must raise TypeError, not
    crash or return garbage.
  - STORE_SUBSCR specialised on a list subclass (inline StoreArrayItem):
    same, plus a post-call type-check on the receiver to catch silent
    structure corruption.
  - Float arithmetic (unboxed mul via float subclass): non-numeric input
    must raise TypeError.
  - Polymorphic dispatch across many fresh list subclasses + many fresh
    non-subscriptable types: same correctness invariant at scale.

These are inline-op regression sentinels: they fire if the JIT's general
deopt-on-type-mismatch behaviour breaks for any of the above paths.
They do NOT fire for the specific version_tag=0 bug Option A would have
fixed (because that bug is unreachable in default config; see
investigations/probes/aba_reachability_probe.py).

If a future build flips emit_type_annotation_guards or enables
multithreaded compile by default, the version_tag=0 bug becomes
reachable; at that point a NEW test (not these) would be needed.
"""

import gc
import unittest

try:
    import cinderjit
    HAS_JIT = True
except ImportError:
    HAS_JIT = False


@unittest.skipUnless(HAS_JIT, "requires CinderX JIT")
class TestInlineOpsOnSubclassedTypes(unittest.TestCase):
    """Inline-op correctness for JIT-specialised paths on subclassed types.

    NOT a falsifier for any specific bug. See module docstring for
    history of why these methods exist with this naming.
    """

    def test_subscript_inlined_get_item(self):
        """BINARY_SUBSCR specialised on a list subclass with tp_version_tag=0.

        Without the fix: GuardType captures Imm{0}; runtime call with a
        non-list whose type also has tag=0 wrongly passes the guard, and
        the inlined GetArrayItem reads from non-list memory →
        segfault / garbage / refcount corruption.

        With the fix: ensureVersionTag forces a non-zero tag at compile;
        runtime tag mismatch → deopt → TypeError raised correctly.
        """
        # Fresh list subclass — tp_version_tag = 0 until first lookup.
        ListSub = type("ListSub_subscr", (list,), {})
        # Fresh non-subscriptable class — tp_version_tag = 0 likewise.
        NotIndexable = type("NotIndexable_subscr", (), {})

        def subscript(seq, i):
            return seq[i]

        ls_inst = ListSub([10, 20, 30])
        for _ in range(100):
            subscript(ls_inst, 0)
            subscript(ls_inst, 1)
            subscript(ls_inst, 2)

        cinderjit.force_compile(subscript)
        self.assertTrue(cinderjit.is_jit_compiled(subscript))

        # Sanity: the warmed type still works.
        self.assertEqual(subscript(ls_inst, 0), 10)
        self.assertEqual(subscript(ls_inst, 2), 30)

        # FALSIFIER: pass a non-subscriptable fresh-tag class.
        ni = NotIndexable()
        with self.assertRaises(TypeError):
            subscript(ni, 0)

        # The original fast path must keep working after deopt.
        self.assertEqual(subscript(ls_inst, 1), 20)

    def test_subscript_inlined_store_item(self):
        """STORE_SUBSCR specialised on a list subclass with tp_version_tag=0.

        Without the fix: inlined StoreArrayItem writes into non-list memory,
        corrupting the receiver's structure (typically a refcount field or
        a type pointer) — observable as a delayed segfault on the next
        operation against the receiver, OR an ASan write-out-of-bounds.
        """
        ListSub = type("ListSub_store", (list,), {})
        NotIndexable = type("NotIndexable_store", (), {})

        def store(seq, i, v):
            seq[i] = v

        ls_inst = ListSub([0, 0, 0])
        for _ in range(100):
            store(ls_inst, 0, 10)
            store(ls_inst, 1, 20)
            store(ls_inst, 2, 30)

        cinderjit.force_compile(store)
        self.assertTrue(cinderjit.is_jit_compiled(store))

        # Sanity: warmed type still works.
        store(ls_inst, 0, 100)
        self.assertEqual(ls_inst[0], 100)

        # FALSIFIER: pass a non-subscriptable fresh-tag instance.
        ni = NotIndexable()
        with self.assertRaises(TypeError):
            store(ni, 0, 99)

        # ni must remain a valid object — touching it must not segfault
        # nor reveal a corrupted type pointer.
        self.assertIs(type(ni), NotIndexable)
        self.assertIn("NotIndexable_store", repr(ni))

    def test_float_arithmetic_inlined_unbox(self):
        """Float arithmetic specialised via GuardType(float) → unboxed mul.

        FloatSub has tp_version_tag=0 until first lookup. NotANumber also
        has tag=0. Without the fix, the inlined unbox reads NotANumber's
        memory as a PyFloatObject ob_fval → garbage product, or segfault
        on a smaller object.
        """
        FloatSub = type("FloatSub_mul", (float,), {})
        NotANumber = type("NotANumber_mul", (), {})

        def mul(a, b):
            return a * b

        fs_a = FloatSub(2.5)
        fs_b = FloatSub(4.0)
        for _ in range(100):
            mul(fs_a, fs_b)

        cinderjit.force_compile(mul)
        self.assertTrue(cinderjit.is_jit_compiled(mul))

        # Sanity: warmed types still produce correct float product.
        self.assertAlmostEqual(mul(fs_a, fs_b), 10.0)

        # FALSIFIER: pass a non-numeric fresh-tag instance — must raise
        # TypeError, NOT return garbage.
        nan = NotANumber()
        with self.assertRaises(TypeError):
            mul(nan, fs_b)

        # And the original fast path must still work after deopt.
        self.assertAlmostEqual(mul(fs_a, fs_b), 10.0)

    def test_many_fresh_classes_polymorphic_subscript(self):
        """Build N fresh list subclasses (all tag=0 until lookup) and dispatch
        through them. Stress the cold-tag space harder.
        """
        list_subs = [type(f"LS_{i}", (list,), {}) for i in range(8)]
        not_subs = [type(f"NS_{i}", (), {}) for i in range(8)]

        def subscript(seq, i):
            return seq[i]

        # Warm only on the first list subclass.
        first = list_subs[0]([100, 200, 300])
        for _ in range(150):
            subscript(first, 0)
            subscript(first, 1)
            subscript(first, 2)

        cinderjit.force_compile(subscript)
        self.assertTrue(cinderjit.is_jit_compiled(subscript))

        # Polymorphic: pass instances of every list subclass.
        for cls in list_subs:
            inst = cls([1, 2, 3])
            self.assertEqual(subscript(inst, 0), 1)
            self.assertEqual(subscript(inst, 2), 3)

        gc.collect()

        # FALSIFIER: pass instances of every NON-subscriptable fresh class.
        # Without the fix, at least one of these wrongly passes the guard
        # and reads garbage from the instance memory.
        for cls in not_subs:
            inst = cls()
            with self.assertRaises(TypeError):
                subscript(inst, 0)


if __name__ == "__main__":
    unittest.main()
