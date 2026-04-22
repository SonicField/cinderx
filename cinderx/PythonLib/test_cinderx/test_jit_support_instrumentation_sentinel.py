# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-strict

"""Sentinel tests for the _enable_support_instrumentation_for_tests API.

These tests guard the API contract surfaces named at the X-commit
(2de8b263) authoring time and the pythia 24 #1 mitigation framing
(underscore-prefix marks the C symbol as test-only-private-by-convention).
They do not exercise the JIT deopt mechanics — that is the job of
test_jit_support_instrumentation. The sentinels exist so that future
refactors of the C function or its Python wrapper trip a clear failure
when contract assumptions break.
"""

import sys
import unittest

from cinderx.test_support import enable_support_instrumentation


class SupportInstrumentationApiSentinel(unittest.TestCase):
    """Contract-surface sentinels for the in-process opt-in API."""

    def test_idempotent(self) -> None:
        """Repeated calls no-op after the first.

        The C function gates re-patching on the support_instrumentation
        flag; if a future refactor removes the gate, this sentinel fires.
        """
        enable_support_instrumentation()
        before = sys.setprofile
        enable_support_instrumentation()
        after = sys.setprofile
        self.assertIs(before, after)

    def test_irreversible(self) -> None:
        """No public API exists to undo the patching once applied.

        The patches are install-once + process-lifetime. If a future
        refactor exposes a disable API, this sentinel fires and the
        irreversibility framing in test_support.py docstring + the
        commit X message KNOWN LIMITATIONS section needs to be revised.
        """
        import cinderjit

        for name in dir(cinderjit):
            self.assertNotIn(
                "disable_support_instrumentation",
                name,
                f"Found unexpected disable API on cinderjit: {name}",
            )

    def test_enable_then_setprofile_smoke(self) -> None:
        """sys.setprofile remains callable post-enable; doesn't raise.

        Smoke test that the patched sys.setprofile is a working callable,
        not a broken stub. A future refactor that breaks the patched
        function's call signature would fire this sentinel.
        """
        enable_support_instrumentation()

        def noop_profiler(frame: object, event: str, arg: object) -> None:
            return None

        try:
            sys.setprofile(noop_profiler)
            sys.setprofile(None)
        except Exception as e:
            self.fail(f"sys.setprofile raised after enable: {e!r}")

    def test_underscore_prefix_signals_private_at_c_level(self) -> None:
        """The C-level symbol is underscore-prefixed per pythia 24 #1.

        Underscore prefix on the C function name signals
        test-only-private-by-convention. If a future refactor renames
        the symbol without the underscore prefix, the convention-mitigation
        for production-accidental-adoption breaks; this sentinel fires
        so the gatekeeper g.3 production-caller-scan re-runs.
        """
        try:
            import cinderjit
        except ImportError:
            self.skipTest("cinderjit not available")

        self.assertTrue(
            hasattr(cinderjit, "_enable_support_instrumentation_for_tests"),
            "Underscore-prefixed C symbol missing — pythia 24 #1 "
            "mitigation broken",
        )
        self.assertFalse(
            hasattr(cinderjit, "enable_support_instrumentation_for_tests"),
            "Non-underscored alias present — pythia 24 #1 "
            "mitigation diluted",
        )

    def test_enable_then_monkey_patch_does_not_crash(self) -> None:
        """User re-patching sys.setprofile after enable() doesn't crash.

        Once the patched sys.setprofile is installed, a user that
        further re-assigns sys.setprofile to their own callable (e.g.
        a custom profiler library) should not crash the JIT. The patched
        callable is replaced; the JIT-side state remains consistent.
        Failure mode this guards: if future refactors add JIT-internal
        state that assumes sys.setprofile-is-our-patched-callable, this
        sentinel fires.
        """
        enable_support_instrumentation()

        def user_profiler(frame: object, event: str, arg: object) -> None:
            return None

        sys.setprofile(user_profiler)
        try:
            self.assertIs(sys.getprofile(), user_profiler)
        finally:
            sys.setprofile(None)


if __name__ == "__main__":
    unittest.main()
