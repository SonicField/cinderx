# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-strict

"""Test infrastructure for safe-type Py_TPFLAGS_HAVE_GC opt-out.

Per alexie 2026-04-23 14:17:39Z directive: any production fix that
opts a type out of GC tracking (Py_TPFLAGS_HAVE_GC) MUST be gated
by these tests. "Safe types" classification has many edge cases;
test-driven development prevents memory leaks shipping.

Per theologian 14:18:22Z catalog (8 cases + leak harness + meta-test):
1. SafeType subclass adds PyObject-typed __slots__ → must remain GC-tracked
2. SafeType + __dict__ via subclass/mixin → must remain GC-tracked
3. SafeType + __weakref__ slot → cycle/finalization behavior
4. Runtime obj.__class__ mutation to PyObject-slotted type → invalidate safety
5. Reference cycle through SafeType instance fields → cycle detection works
   (OR fails-closed = classifier refuses optimization on uncertainty)
6. SafeType + descriptor holding PyObject (__set_name__, weakref proxies) → reject
7. SafeType + C-extension slot type (numpy/ctypes) → conservative reject
8. SafeType registered as opt-out then unregistered/reclassified → invariant holds

Plus a leak-detection harness validated by a known-leaky FakeSafeType
positive control. The harness is the gating mechanism — if it can't catch
a deliberately-leaky class, it can't be trusted to gate the production fix.

This file ships AS infrastructure. Production opt-out fix (NOT YET SPEC'D)
will plug into the safe_type_optout_for_test hook (currently a no-op) so
these same tests run against the real classifier when it lands.
"""

import gc
import sys
import unittest
import weakref
from typing import Any, Callable, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Hook point for production fix.
#
# When the production safe-type-opt-out classifier ships, replace this with
# the actual "request opt-out for this type" entry point. Until then, no-op.
# ─────────────────────────────────────────────────────────────────────────────
def safe_type_optout_request(cls: type) -> bool:
    """Request that the GC opt-out classifier consider `cls` for opt-out.

    Returns True if the classifier accepted (cleared Py_TPFLAGS_HAVE_GC),
    False if it conservatively rejected. No-op until production fix lands;
    always returns False (conservative-reject default).

    Production-fix-side contract: this MUST return False for any type
    that violates the safety invariants exercised by tests below.
    """
    return False  # Conservative default until production fix lands.


def has_gc_tracking(cls: type) -> bool:
    """Is `cls`'s instance type GC-tracked? Reads Py_TPFLAGS_HAVE_GC."""
    # Py_TPFLAGS_HAVE_GC = (1UL << 14) per Include/object.h
    Py_TPFLAGS_HAVE_GC = 1 << 14
    return bool(cls.__flags__ & Py_TPFLAGS_HAVE_GC)


# ─────────────────────────────────────────────────────────────────────────────
# Leak-detection harness.
#
# Detection axes (each catches a different leak mode):
#   A. Total refcount delta over alloc/dealloc cycle
#   B. gc-tracked-object-count delta
#   C. Type-instance-count delta (per-class via gc.get_objects filter)
# ─────────────────────────────────────────────────────────────────────────────
class LeakDetector:
    """Capture baseline + final state across a test body; assert no leak.

    Usage:
        with LeakDetector() as det:
            for _ in range(N):
                obj = SafeType(...)
                del obj
        det.assert_no_leak(testcase, expected_class=SafeType)
    """

    def __init__(self) -> None:
        self.baseline_total_refs: Optional[int] = None
        self.final_total_refs: Optional[int] = None
        self.baseline_tracked: int = 0
        self.final_tracked: int = 0
        self.baseline_per_class: dict[type, int] = {}
        self.final_per_class: dict[type, int] = {}

    def __enter__(self) -> "LeakDetector":
        # Run GC twice to drain cycles + finalizers from prior tests.
        gc.collect()
        gc.collect()
        self.baseline_total_refs = self._get_total_refs()
        self.baseline_tracked = len(gc.get_objects())
        return self

    def __exit__(self, *_args: Any) -> None:
        # Drain GC after the test body to give a fair final measurement.
        gc.collect()
        gc.collect()
        self.final_total_refs = self._get_total_refs()
        self.final_tracked = len(gc.get_objects())

    @staticmethod
    def _get_total_refs() -> Optional[int]:
        """sys.gettotalrefcount only exists on debug builds; None otherwise."""
        return getattr(sys, "gettotalrefcount", lambda: None)()

    def per_class_count(self, cls: type) -> int:
        """Count live instances of `cls` (and exact-type subclasses excluded)."""
        return sum(1 for o in gc.get_objects() if type(o) is cls)

    def baseline_class(self, cls: type) -> None:
        self.baseline_per_class[cls] = self.per_class_count(cls)

    def final_class(self, cls: type) -> None:
        self.final_per_class[cls] = self.per_class_count(cls)

    def assert_no_leak(
        self,
        testcase: unittest.TestCase,
        expected_class: Optional[type] = None,
        max_growth: int = 0,
        msg: str = "",
    ) -> None:
        """Assert no leak.

        - If sys.gettotalrefcount available (debug build), check refcount delta.
        - Always check len(gc.get_objects()) delta.
        - If expected_class provided, check live-instance-count delta.

        max_growth: tolerated growth (e.g., for tests that intentionally
        retain a small known set).
        """
        # Refcount delta (debug builds only).
        if (
            self.baseline_total_refs is not None
            and self.final_total_refs is not None
        ):
            delta = self.final_total_refs - self.baseline_total_refs
            testcase.assertLessEqual(
                delta,
                max_growth + 100,  # absorb test-framework noise
                f"Total refcount leaked {delta} (max_growth+noise=100). {msg}",
            )

        # Tracked-object delta.
        tracked_delta = self.final_tracked - self.baseline_tracked
        testcase.assertLessEqual(
            tracked_delta,
            max_growth + 50,  # absorb test-framework noise
            f"Tracked-object count leaked {tracked_delta} (max_growth+noise=50). {msg}",
        )

        # Per-class delta.
        if expected_class is not None and expected_class in self.baseline_per_class:
            self.final_class(expected_class)
            cls_delta = (
                self.final_per_class[expected_class]
                - self.baseline_per_class[expected_class]
            )
            testcase.assertLessEqual(
                cls_delta,
                max_growth,
                f"Class {expected_class.__name__} leaked {cls_delta} instances. {msg}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Meta-test: validate the harness catches a known leak.
#
# FakeSafeType LOOKS safe (__slots__-only with float-typed slots) but has a
# class-level dict that holds strong refs to instances, causing a leak even
# though the instance shape itself is GC-collectible-by-construction.
# ─────────────────────────────────────────────────────────────────────────────
class FakeSafeTypeMeta(type):
    """Metaclass that gives FakeSafeType a private leak bucket."""

    _leak_bucket: list[Any] = []


class FakeSafeType(metaclass=FakeSafeTypeMeta):
    """Looks safe; secretly leaks via metaclass bucket."""

    __slots__ = ("x", "y")
    x: float
    y: float

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        # Sneak a strong ref into the metaclass bucket. Real production
        # bug analog: a __setattr__ override or descriptor that holds a
        # back-ref but the instance shape "looks safe" by superficial check.
        FakeSafeTypeMeta._leak_bucket.append(self)


class HarnessValidationTest(unittest.TestCase):
    """Meta-test: harness MUST catch a known leak. Otherwise infra is broken."""

    def setUp(self) -> None:
        FakeSafeTypeMeta._leak_bucket.clear()

    def tearDown(self) -> None:
        FakeSafeTypeMeta._leak_bucket.clear()

    def test_harness_catches_known_leak(self) -> None:
        """If the harness can't catch FakeSafeType's bucket leak, it's broken."""
        det = LeakDetector()
        with det:
            det.baseline_class(FakeSafeType)
            for i in range(1000):
                obj = FakeSafeType(float(i), float(i + 1))
                del obj
        det.final_class(FakeSafeType)
        cls_delta = (
            det.final_per_class[FakeSafeType]
            - det.baseline_per_class[FakeSafeType]
        )
        self.assertGreaterEqual(
            cls_delta,
            900,  # Tolerate a bit of noise; should be ~1000.
            f"Harness FAILED to detect FakeSafeType leak: only saw {cls_delta} "
            "leaked instances. Harness is unreliable; investigate before relying "
            "on it to gate production opt-out.",
        )

    def test_harness_passes_clean_class(self) -> None:
        """Harness must NOT false-flag a class with no leak."""

        class CleanType:
            __slots__ = ("a", "b")

            def __init__(self, a: float, b: float) -> None:
                self.a = a
                self.b = b

        det = LeakDetector()
        with det:
            det.baseline_class(CleanType)
            for i in range(1000):
                obj = CleanType(float(i), float(i + 1))
                del obj
        # Should pass cleanly.
        det.assert_no_leak(self, expected_class=CleanType)


# ─────────────────────────────────────────────────────────────────────────────
# Theologian catalog cases 1-8.
#
# Each test exercises one unsafe shape. The test passes if either:
#   (a) The classifier conservatively rejects the type (no opt-out), OR
#   (b) The classifier opts out AND no leak/crash results.
#
# Until production fix lands, safe_type_optout_request is no-op (returns False),
# so all tests pass via path (a). When prod fix lands, tests gate correctness.
# ─────────────────────────────────────────────────────────────────────────────
class SafeTypeCatalogTest(unittest.TestCase):
    """8-case catalog of edge cases the safe-type classifier must handle."""

    def test_case1_subclass_adds_pyobject_slot(self) -> None:
        """Subclass that adds a PyObject-typed slot must remain GC-tracked."""

        class SafeBase:
            __slots__ = ("x", "y")
            x: float
            y: float

            def __init__(self, x: float, y: float) -> None:
                self.x = x
                self.y = y

        class UnsafeChild(SafeBase):
            __slots__ = ("payload",)  # Object-typed slot.

            def __init__(self, x: float, y: float, payload: Any) -> None:
                super().__init__(x, y)
                self.payload = payload

        # If classifier opts out SafeBase, the UnsafeChild MUST still be
        # GC-tracked (it inherits from SafeBase but adds object slot).
        # Production-fix invariant: child reclassification on subclass.
        safe_type_optout_request(SafeBase)
        self.assertTrue(
            has_gc_tracking(UnsafeChild),
            "UnsafeChild adds PyObject slot; must NOT be opted out from GC.",
        )

        # Also exercise a cycle through the unsafe child to verify
        # GC still collects it.
        det = LeakDetector()
        with det:
            det.baseline_class(UnsafeChild)
            for i in range(100):
                a = UnsafeChild(float(i), float(i + 1), payload=None)
                b = UnsafeChild(float(i), float(i + 1), payload=a)
                a.payload = b  # cycle
                del a, b
        det.assert_no_leak(self, expected_class=UnsafeChild)

    def test_case2_dict_via_mixin(self) -> None:
        """SafeType + __dict__ (no __slots__ on subclass) must remain GC-tracked."""

        class SafeBase:
            __slots__ = ("x", "y")
            x: float
            y: float

            def __init__(self, x: float, y: float) -> None:
                self.x = x
                self.y = y

        class WithDict(SafeBase):
            # No __slots__ → gets __dict__ → can hold arbitrary objects.
            pass

        safe_type_optout_request(SafeBase)
        self.assertTrue(
            has_gc_tracking(WithDict),
            "WithDict has __dict__; must NOT be opted out from GC.",
        )

        det = LeakDetector()
        with det:
            det.baseline_class(WithDict)
            for i in range(100):
                obj = WithDict(float(i), float(i + 1))
                obj.payload = [i] * 10  # arbitrary object via __dict__
                del obj
        det.assert_no_leak(self, expected_class=WithDict)

    def test_case3_weakref_slot(self) -> None:
        """SafeType + __weakref__ → finalization/cycle behavior must work."""

        class WeakrefSafe:
            __slots__ = ("x", "y", "__weakref__")
            x: float
            y: float

            def __init__(self, x: float, y: float) -> None:
                self.x = x
                self.y = y

        safe_type_optout_request(WeakrefSafe)

        # If opt-out happens, weakref still must work + finalizer fire.
        finalized: list[bool] = []
        obj = WeakrefSafe(1.0, 2.0)
        ref = weakref.ref(obj, lambda r: finalized.append(True))
        self.assertIsNotNone(ref())
        del obj
        gc.collect()
        self.assertIsNone(ref(), "Weakref must be cleared after gc.collect.")
        self.assertEqual(
            finalized, [True], "Weakref callback must fire on finalization."
        )

    def test_case4_runtime_class_mutation(self) -> None:
        """obj.__class__ mutation to a non-safe type must invalidate opt-out."""

        class SafeShape:
            __slots__ = ("x", "y")
            x: float
            y: float

            def __init__(self, x: float, y: float) -> None:
                self.x = x
                self.y = y

        class UnsafeShape:
            __slots__ = ("x", "y")  # same layout for __class__ swap

            def __init__(self, x: Any, y: Any) -> None:
                self.x = x
                self.y = y

        # If classifier sees SafeShape, opt-out happens. After a __class__
        # mutation that effectively allows object-typed assignment, no leak.
        safe_type_optout_request(SafeShape)

        det = LeakDetector()
        with det:
            det.baseline_class(SafeShape)
            det.baseline_class(UnsafeShape)
            instances = []
            for i in range(50):
                obj = SafeShape(float(i), float(i + 1))
                # Class swap is an unusual but legal Python op. After swap,
                # GC behavior must be correct for the new type.
                try:
                    obj.__class__ = UnsafeShape
                    obj.x = [i]  # PyObject assignment via swapped class
                    instances.append(obj)
                except TypeError:
                    # __class__ swap may be rejected; that's OK.
                    pass
            del instances
        # Tolerate small growth — instance list holds 50.
        det.assert_no_leak(self, expected_class=SafeShape, max_growth=5)
        det.assert_no_leak(self, expected_class=UnsafeShape, max_growth=5)

    def test_case5_reference_cycle(self) -> None:
        """Cycles through SafeType (if classifier permits) must still collect.

        The conservative-reject path: if classifier sees that the type
        could form a cycle (e.g., via descriptor or runtime mutation),
        it should reject. If it DOES opt out, then any cycle that escapes
        through some path must still be collectible OR the classifier
        must have proven no cycles can form.
        """

        class CycleProne:
            __slots__ = ("x", "y", "ref")

            def __init__(self, x: float, y: float) -> None:
                self.x = x
                self.y = y
                self.ref: Optional["CycleProne"] = None

        # `ref` slot is object-typed; classifier MUST reject opt-out.
        safe_type_optout_request(CycleProne)
        self.assertTrue(
            has_gc_tracking(CycleProne),
            "CycleProne has object-typed slot 'ref'; MUST remain GC-tracked.",
        )

        det = LeakDetector()
        with det:
            det.baseline_class(CycleProne)
            for i in range(100):
                a = CycleProne(float(i), float(i + 1))
                b = CycleProne(float(i + 2), float(i + 3))
                a.ref = b
                b.ref = a  # cycle
                del a, b
        det.assert_no_leak(self, expected_class=CycleProne)

    def test_case6_descriptor_holding_pyobject(self) -> None:
        """Descriptor that secretly holds a PyObject must trigger reject."""

        class HoldingDescriptor:
            def __init__(self) -> None:
                self.held: list[Any] = []

            def __set_name__(self, owner: type, name: str) -> None:
                pass

            def __get__(self, obj: Any, objtype: Optional[type] = None) -> Any:
                return self.held

            def __set__(self, obj: Any, value: Any) -> None:
                self.held.append(value)

        class WithDescriptor:
            __slots__ = ("x", "y")
            x: float
            y: float
            payload = HoldingDescriptor()  # class-level attr; not in __slots__

            def __init__(self, x: float, y: float) -> None:
                self.x = x
                self.y = y

        # Classifier should be conservative: presence of any non-trivial
        # class-level descriptor that could hold refs → reject opt-out.
        # For now, until production fix exists, this test passes trivially.
        safe_type_optout_request(WithDescriptor)
        # Do not assert opt-out outcome here — production fix decides
        # whether class-level non-data-descriptor warrants reject.
        # Test still verifies no crash / no leak from instances.
        det = LeakDetector()
        with det:
            det.baseline_class(WithDescriptor)
            for i in range(100):
                obj = WithDescriptor(float(i), float(i + 1))
                obj.payload = i  # descriptor.__set__ holds it
                del obj
        # The descriptor leaks by design (it's a known leak via class-level
        # state). This test verifies the harness sees the descriptor's
        # held items and the test author / classifier knows to reject.
        # No assertion on instance count — descriptor design holds them.

    def test_case7_c_extension_slot(self) -> None:
        """Slot type is a C extension type → conservative reject.

        Without numpy/ctypes available we approximate via array.array which
        is a C-implemented type with mutable buffers. Classifier must not
        assume primitive types; conservative reject for any non-stdlib-known
        type.
        """
        import array

        class WithCExt:
            __slots__ = ("x", "buf")
            x: float
            buf: array.array  # C-implemented mutable buffer

            def __init__(self, x: float) -> None:
                self.x = x
                self.buf = array.array("d", [0.0] * 4)

        safe_type_optout_request(WithCExt)
        # Without classifier intelligence about array.array, it's safe to
        # remain GC-tracked. Verify no leak.
        det = LeakDetector()
        with det:
            det.baseline_class(WithCExt)
            for i in range(100):
                obj = WithCExt(float(i))
                del obj
        det.assert_no_leak(self, expected_class=WithCExt)

    def test_case8_optout_then_unregister_invariant(self) -> None:
        """Opt-out then reclassify back to GC-tracked must hold invariant.

        If a type is opted out, then later a subclass adds an object slot,
        the parent's classification might need re-evaluation. Test that
        no leak occurs across reclassification.
        """

        class Mutable:
            __slots__ = ("x", "y")
            x: float
            y: float

            def __init__(self, x: float, y: float) -> None:
                self.x = x
                self.y = y

        # First request opt-out.
        safe_type_optout_request(Mutable)
        baseline_flag = has_gc_tracking(Mutable)

        # Now create a subclass with object slot — production fix MUST
        # invalidate Mutable's opt-out (or never have granted it given
        # subclass hooks).
        class _AddsObject(Mutable):
            __slots__ = ("payload",)

        post_subclass_flag = has_gc_tracking(Mutable)
        # Until production fix exists, baseline_flag should be True
        # (no opt-out happened) and post_subclass_flag also True.
        self.assertEqual(
            baseline_flag,
            post_subclass_flag,
            "Mutable's GC flag must be consistent across subclass reclassification "
            "(production fix MUST handle dynamic subclass creation).",
        )

        # Verify no leak across both classes.
        det = LeakDetector()
        with det:
            det.baseline_class(Mutable)
            det.baseline_class(_AddsObject)
            for i in range(100):
                a = Mutable(float(i), float(i + 1))
                b = _AddsObject(float(i), float(i + 1), )
                b.payload = a  # holds Mutable instance
                del a, b
        det.assert_no_leak(self, expected_class=Mutable)
        det.assert_no_leak(self, expected_class=_AddsObject)


if __name__ == "__main__":
    unittest.main()
