"""Tests for inlining functions with exception handlers (Phase 2).

Falsifiers for the kHasExceptionHandlers restriction removal:
- Case 1: Inlined callee with try/except, no exception raised (happy path)
- Case 2: Inlined callee catches its own exception (deopt → interpreter)
- Case 3: Inlined callee has wrong except type, exception propagates
- Case 4: Caller catches exception from inlined callee (deopt to caller)
- Case 5: Inlined callee with nested try/except
- Case 6: Inlined callee with try/finally
- Case 7: B2 pattern — dict subscript in try/except KeyError (critical)

Callee functions MUST be at module scope (accessed via LOAD_GLOBAL) so the
JIT preloader can find them and the inliner can inline them. Functions
defined inside test methods are accessed via LOAD_DEREF (closure) and
CANNOT be inlined.

Usage: cd /data/users/alexturner/cinderx_dev/cinderx && \
       source /data/users/alexturner/cinderx_dev/venv/bin/activate && \
       PYTHONJIT=1 python3 test_exception_handler_inlining.py
"""
import unittest

try:
    import cinderjit
    HAS_JIT = True
except ImportError:
    HAS_JIT = False


# =====================================================================
# Module-level callee functions — accessed via LOAD_GLOBAL by callers.
# The JIT preloader resolves these from LOAD_GLOBAL and marks them as
# inlining candidates. If they were defined inside test methods, they
# would be accessed via LOAD_DEREF (closure) and skipped by the inliner.
# =====================================================================

def callee_try_no_raise(x):
    """Case 1: try/except, no exception raised."""
    try:
        result = x * 2
    except ValueError:
        result = -1
    return result


def callee_catches_own(x):
    """Case 2: try/except, callee catches its own exception."""
    try:
        if x < 0:
            raise ValueError("negative")
        result = x * 3
    except ValueError:
        result = 0
    return result


def callee_wrong_except(x):
    """Case 3: try/except catches wrong type, exception propagates."""
    try:
        if x is None:
            raise TypeError("got None")
        result = x + 1
    except ValueError:
        # Catches ValueError, NOT TypeError — TypeError propagates
        result = -1
    return result


def callee_raises_uncaught(x):
    """Case 4: callee with try/except raises uncaught exception."""
    try:
        if x < 0:
            raise RuntimeError("bad value")
        result = x * 10
    except ValueError:
        # Wrong handler — RuntimeError propagates
        result = -1
    return result


def callee_nested_try(x):
    """Case 5: nested try/except blocks."""
    result = 0
    try:
        try:
            if x == 0:
                raise ZeroDivisionError("zero")
            result = 100 // x
        except ZeroDivisionError:
            result = -1
        # After inner try — continue in outer try
        result += 10
    except Exception:
        # Should not reach for ZeroDivisionError (caught by inner)
        result = -999
    return result


_finally_tracker = []

def callee_with_finally(x):
    """Case 6: try/finally — finally must always run."""
    global _finally_tracker
    try:
        if x < 0:
            raise ValueError("negative")
        result = x + 1
    finally:
        _finally_tracker.append("finally")
    return result


_b2_dict = {"a": 1, "b": 2, "c": 3}

def callee_b2_subscript(key):
    """Case 7 (B2 pattern): dict subscript in try/except KeyError.

    This is the CRITICAL falsifier. Without exception_table_.clear() in
    builder.cpp, the B2 optimisation (emitBinaryOp → findExceptionHandler
    → emitInlineExceptionMatch) would create reachable handler blocks in
    the inlined CFG, potentially crashing getUnitFrames.
    """
    try:
        return _b2_dict[key]
    except KeyError:
        return "default"


# =====================================================================
# Test class
# =====================================================================

@unittest.skipUnless(HAS_JIT, "requires CinderX JIT")
class TestExceptionHandlerInlining(unittest.TestCase):

    def _force_compile_and_warm(self, caller, warm_args_list, n=1200):
        """Force-compile caller and warm with repeated calls.

        The caller accesses the callee via LOAD_GLOBAL. force_compile
        triggers the inliner which checks canInline() — after Phase 2,
        callees with exception handlers should pass this check.
        """
        cinderjit.force_compile(caller)
        for _ in range(n):
            for args in warm_args_list:
                caller(*args)

    def test_case1_no_raise_happy_path(self):
        """Inlined callee with try/except, no exception on hot path."""
        def caller(x):
            return callee_try_no_raise(x) + 1

        self._force_compile_and_warm(caller, [(5,), (10,), (0,)])
        self.assertEqual(caller(5), 11)
        self.assertEqual(caller(0), 1)
        self.assertEqual(caller(-3), -5)

    def test_case2_callee_catches_own_exception(self):
        """Inlined callee catches its own exception (deopt path).

        When x < 0, callee raises ValueError inside try and catches it.
        Deopt → interpreter → co_exceptiontable lookup → handler runs.
        If getUnitFrames crashes, this is the first test to fail.
        """
        def caller(x):
            return callee_catches_own(x) + 100

        self._force_compile_and_warm(caller, [(5,), (10,), (1,)])

        # Happy path (no exception)
        self.assertEqual(caller(5), 115)
        # Exception path (callee catches)
        self.assertEqual(caller(-1), 100)  # 0 + 100
        self.assertEqual(caller(-100), 100)

    def test_case3_wrong_except_type_propagates(self):
        """Callee catches ValueError but raises TypeError — propagates."""
        def caller(x):
            return callee_wrong_except(x) + 50

        self._force_compile_and_warm(caller, [(5,), (10,), (1,)])

        # Happy path
        self.assertEqual(caller(5), 56)
        # TypeError propagates (not caught by except ValueError)
        with self.assertRaises(TypeError):
            caller(None)

    def test_case4_caller_catches_callee_exception(self):
        """Caller catches exception from inlined callee.

        The callee has try/except (catching wrong type), so it WILL be
        affected by Phase 2. The RuntimeError propagates through the
        callee's except ValueError, then the caller catches it.
        """
        def caller(x):
            try:
                return callee_raises_uncaught(x) + 1
            except RuntimeError:
                return -999

        self._force_compile_and_warm(caller, [(5,), (10,), (1,)])

        # Happy path
        self.assertEqual(caller(5), 51)
        # Exception path — caller catches
        self.assertEqual(caller(-1), -999)

    def test_case5_nested_try_except(self):
        """Inlined callee with nested try/except blocks."""
        def caller(x):
            return callee_nested_try(x) + 1000

        self._force_compile_and_warm(caller, [(5,), (10,), (2,)])

        # Happy path: 100//5 + 10 + 1000 = 1030
        self.assertEqual(caller(5), 1030)
        # Inner except catches ZeroDivisionError: -1 + 10 + 1000 = 1009
        self.assertEqual(caller(0), 1009)

    def test_case6_try_finally(self):
        """Inlined callee with try/finally — finally always runs."""
        global _finally_tracker

        def caller(x):
            return callee_with_finally(x)

        self._force_compile_and_warm(caller, [(5,), (10,)])

        # Happy path: finally runs, correct result
        _finally_tracker.clear()
        result = caller(5)
        self.assertEqual(result, 6)
        self.assertIn("finally", _finally_tracker)

        # Exception path: finally runs, exception propagates
        _finally_tracker.clear()
        with self.assertRaises(ValueError):
            caller(-1)
        self.assertIn("finally", _finally_tracker)

    def test_case7_b2_subscript_in_try_except(self):
        """B2 pattern: dict subscript in try/except KeyError.

        This is the CRITICAL targeted falsifier for Option A. Without
        exception_table_.clear() in builder.cpp, the B2 optimisation
        (emitBinaryOp → findExceptionHandler → emitInlineExceptionMatch)
        could create reachable handler blocks in the inlined CFG.

        With exception_table_.clear(), findExceptionHandler returns nullptr,
        B2 does not fire, and all exceptions deopt to the interpreter.
        """
        def caller(key):
            return callee_b2_subscript(key)

        self._force_compile_and_warm(caller, [("a",), ("b",), ("c",)])

        # Happy path (key exists)
        self.assertEqual(caller("a"), 1)
        self.assertEqual(caller("b"), 2)
        self.assertEqual(caller("c"), 3)

        # Exception path (key missing — KeyError caught by callee)
        self.assertEqual(caller("missing"), "default")
        self.assertEqual(caller("xyz"), "default")

    def test_case2_type_switch_after_warmup(self):
        """Type switch after warmup: warm with no-exception, then trigger.

        Exercises the deopt path transition: JIT hot → deopt → interpreter.
        Similar to Phase 1 type_change_deopt_correctness but with exception
        handlers in the inlined callee.
        """
        values = [5]

        def caller():
            return callee_catches_own(values[0]) + 100

        cinderjit.force_compile(caller)
        # Warm with no-exception path
        for _ in range(1200):
            self.assertEqual(caller(), 115)

        # Switch to exception path
        values[0] = -1
        self.assertEqual(caller(), 100)

        # Switch back
        values[0] = 10
        self.assertEqual(caller(), 130)


if __name__ == "__main__":
    unittest.main()
