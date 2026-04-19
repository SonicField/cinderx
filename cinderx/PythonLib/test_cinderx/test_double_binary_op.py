"""Test double modulo and floor division in JIT.

Verifies that DoubleBinaryOp correctly handles kModulo and kFloorDivide
after the fix in generator.cpp. Tests both force_compile and auto-JIT paths.
"""
import math
import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False

TEST_CASES = [
    (7.5, 2.5, 0.0, 3.0),
    (10.0, 3.0, 1.0, 3.0),
    (-10.0, 3.0, 2.0, -4.0),
    (10.0, -3.0, -2.0, -4.0),
    (-10.0, -3.0, -1.0, 3.0),
    (1.5, 0.5, 0.0, 3.0),
    (2.5, 1.0, 0.5, 2.0),
    (0.0, 1.0, 0.0, 0.0),
    (1e-10, 1.0, 1e-10, 0.0),
    (1e10, 3.0, 1.0, 3333333333.0),
]


def double_mod(a, b):
    return a % b


def double_floordiv(a, b):
    return a // b


def double_combined(a, b):
    return (a % b, a // b)


class TestDoubleBinaryOpInterpreter(unittest.TestCase):
    """Verify correctness without JIT compilation."""

    def test_mod(self):
        for a, b, exp_mod, _ in TEST_CASES:
            with self.subTest(a=a, b=b):
                self.assertTrue(
                    math.isclose(double_mod(a, b), exp_mod, rel_tol=1e-9, abs_tol=1e-15),
                    f"{a} % {b} = {double_mod(a, b)}, expected {exp_mod}",
                )

    def test_floordiv(self):
        for a, b, _, exp_fdiv in TEST_CASES:
            with self.subTest(a=a, b=b):
                self.assertTrue(
                    math.isclose(double_floordiv(a, b), exp_fdiv, rel_tol=1e-9, abs_tol=1e-15),
                    f"{a} // {b} = {double_floordiv(a, b)}, expected {exp_fdiv}",
                )


@unittest.skipUnless(HAS_CINDERJIT, "CinderX JIT not available")
class TestDoubleBinaryOpJIT(unittest.TestCase):
    """Verify correctness after force_compile."""

    @classmethod
    def setUpClass(cls):
        cinderjit.force_compile(double_mod)
        cinderjit.force_compile(double_floordiv)
        cinderjit.force_compile(double_combined)

    def test_mod_jit(self):
        self.assertTrue(cinderjit.is_jit_compiled(double_mod))
        for a, b, exp_mod, _ in TEST_CASES:
            with self.subTest(a=a, b=b):
                self.assertTrue(
                    math.isclose(double_mod(a, b), exp_mod, rel_tol=1e-9, abs_tol=1e-15),
                    f"{a} % {b} = {double_mod(a, b)}, expected {exp_mod}",
                )

    def test_floordiv_jit(self):
        self.assertTrue(cinderjit.is_jit_compiled(double_floordiv))
        for a, b, _, exp_fdiv in TEST_CASES:
            with self.subTest(a=a, b=b):
                self.assertTrue(
                    math.isclose(double_floordiv(a, b), exp_fdiv, rel_tol=1e-9, abs_tol=1e-15),
                    f"{a} // {b} = {double_floordiv(a, b)}, expected {exp_fdiv}",
                )

    def test_combined_jit(self):
        self.assertTrue(cinderjit.is_jit_compiled(double_combined))
        for a, b, exp_mod, exp_fdiv in TEST_CASES[:5]:
            with self.subTest(a=a, b=b):
                got = double_combined(a, b)
                self.assertTrue(
                    math.isclose(got[0], exp_mod, rel_tol=1e-9, abs_tol=1e-15),
                    f"({a} % {b}) in combined = {got[0]}, expected {exp_mod}",
                )
                self.assertTrue(
                    math.isclose(got[1], exp_fdiv, rel_tol=1e-9, abs_tol=1e-15),
                    f"({a} // {b}) in combined = {got[1]}, expected {exp_fdiv}",
                )


if __name__ == "__main__":
    unittest.main()
