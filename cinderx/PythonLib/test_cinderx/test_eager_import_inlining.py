"""Tests for inlining functions containing EAGER_IMPORT_NAME bytecodes.

CinderX converts all IMPORT_NAME to EAGER_IMPORT_NAME on Python 3.12.
Prior to the version guard fix, the inliner rejected all callees with
EAGER_IMPORT_NAME (InlineFailureType::kHasEagerImportName). On 3.12,
the LIR path uses PyImport_Import(name) which has no frame dependency,
so the restriction was unnecessary.

Falsifiers:
- A callee containing EAGER_IMPORT_NAME produces correct import results
  when called from JIT-compiled code
- Multiple successive imports in a callee resolve correctly
- A callee importing a module and accessing its attributes works under
  JIT compilation after warmup
"""
import unittest
import sys
import opcode

try:
    import cinderjit
    HAS_JIT = True
except ImportError:
    HAS_JIT = False


def _has_eager_import(func):
    """Check if a function's bytecode contains EAGER_IMPORT_NAME."""
    eager = opcode.opmap.get("EAGER_IMPORT_NAME")
    if eager is None:
        return False
    bc = func.__code__.co_code
    for i in range(0, len(bc), 2):
        if bc[i] == eager:
            return True
    return False


@unittest.skipUnless(HAS_JIT, "requires CinderX JIT")
class TestEagerImportInlining(unittest.TestCase):

    def test_callee_with_import_produces_correct_result(self):
        """A callee containing EAGER_IMPORT_NAME returns the correct value."""
        def callee():
            import os
            return os.sep

        # Verify the bytecode actually contains EAGER_IMPORT_NAME
        self.assertTrue(
            _has_eager_import(callee),
            "callee should contain EAGER_IMPORT_NAME bytecode"
        )

        def caller():
            return callee()

        cinderjit.force_compile(caller)
        for _ in range(1200):
            result = caller()
            self.assertEqual(result, "/")

    def test_callee_with_multiple_imports(self):
        """A callee with multiple import statements works correctly."""
        def multi_import():
            import os
            import sys
            return (os.sep, sys.platform)

        self.assertTrue(_has_eager_import(multi_import))

        def caller():
            return multi_import()

        cinderjit.force_compile(caller)
        for _ in range(1200):
            sep, platform = caller()
            self.assertEqual(sep, "/")
            self.assertIsInstance(platform, str)

    def test_callee_import_with_attribute_access(self):
        """Import + attribute chain resolves correctly under JIT."""
        def get_path_module():
            import os.path
            return os.path.exists

        self.assertTrue(_has_eager_import(get_path_module))

        def caller():
            return get_path_module()

        cinderjit.force_compile(caller)
        for _ in range(1200):
            exists_func = caller()
            self.assertTrue(callable(exists_func))
            # Verify it's the real os.path.exists
            self.assertTrue(exists_func("/"))

    def test_callee_import_from(self):
        """from-import in callee (IMPORT_FROM after EAGER_IMPORT_NAME)."""
        def import_from_callee():
            from os.path import sep
            return sep

        self.assertTrue(_has_eager_import(import_from_callee))

        def caller():
            return import_from_callee()

        cinderjit.force_compile(caller)
        for _ in range(1200):
            self.assertEqual(caller(), "/")

    def test_import_callee_correctness_after_warmup(self):
        """Import result is correct after tier1 warmup (1200+ calls)."""
        call_count = [0]

        def import_and_compute():
            import os
            call_count[0] += 1
            return len(os.sep)

        self.assertTrue(_has_eager_import(import_and_compute))

        def caller():
            return import_and_compute()

        cinderjit.force_compile(caller)
        # Run enough times for potential tier2 recompilation
        for _ in range(2000):
            result = caller()
            self.assertEqual(result, 1)

        self.assertEqual(call_count[0], 2000)


if __name__ == "__main__":
    unittest.main()
