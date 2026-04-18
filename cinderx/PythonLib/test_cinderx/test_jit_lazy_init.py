"""Tests for lazy JIT initialization (Tier 1).

Verifies that importing cinderjit does NOT trigger full JIT initialization
(heap scan, function scheduling) until auto() or force_compile() is called.

The pre-auto test runs in a subprocess to guarantee clean JIT state,
avoiding test-ordering dependencies within the unittest runner.
"""
import subprocess
import sys
import unittest

import cinderjit


class TestLazyInit(unittest.TestCase):

    def test_no_compilation_before_auto(self):
        result = subprocess.run(
            [sys.executable, "-c", """
import cinderjit
assert cinderjit.get_compile_after_n_calls() is None, \
    f"compile_after_n_calls should be None before auto(), got {cinderjit.get_compile_after_n_calls()}"
assert len(cinderjit.get_compiled_functions()) == 0, \
    f"no functions should be compiled before auto(), got {len(cinderjit.get_compiled_functions())}"
def f():
    return 42
assert not cinderjit.is_jit_compiled(f), "function should not be JIT-compiled before auto()"
assert f() == 42, f"function should still work, got {f()}"
print("PASS")
"""],
            capture_output=True, text=True, timeout=30,
            env={**__import__('os').environ,
                 'PYTHONPATH': ':'.join(sys.path)},
        )
        self.assertEqual(result.returncode, 0, f"subprocess failed: {result.stderr}")
        self.assertIn("PASS", result.stdout)

    def test_jit_works_after_auto(self):
        cinderjit.auto()
        def f():
            return 99
        for _ in range(1200):
            f()
        self.assertTrue(cinderjit.is_jit_compiled(f))
        self.assertEqual(f(), 99)

    def test_functions_created_before_auto_compilable(self):
        def g():
            return 7 + 3
        cinderjit.auto()
        for _ in range(1200):
            g()
        self.assertTrue(cinderjit.is_jit_compiled(g))
        self.assertEqual(g(), 10)

    def test_force_compile_works(self):
        def h():
            return 123
        cinderjit.force_compile(h)
        self.assertTrue(cinderjit.is_jit_compiled(h))
        self.assertEqual(h(), 123)


if __name__ == '__main__':
    unittest.main()
