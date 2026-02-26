"""
test_binary_op_add_int.py — Correctness and deopt tests for BINARY_OP integer
arithmetic specialisations.

Targets: BINARY_OP_ADD_INT, BINARY_OP_SUBTRACT_INT, BINARY_OP_MULTIPLY_INT.

These specialisations emit GuardType on both operands to confirm they are int,
then use the fast nb_add/nb_subtract/nb_multiply slot directly (or an inlined
integer arithmetic path) instead of generic binary_op dispatch.

When a function is JIT-compiled with int operands and then called with a
different operand type (float, str, custom __add__), the GuardType must fire,
triggering deoptimisation back to the interpreter. The interpreter must then
produce the correct result.

Tests cover:
  - Basic int arithmetic correctness (add, subtract, multiply)
  - Edge cases: zero, negative, large values
  - Overflow to bigint (sys.maxsize + 1)
  - Deopt: int-compiled then called with float operands
  - Deopt: int-compiled then called with custom __add__ objects
  - Deopt: mixed type operands (int + float)
  - Accumulator loops (common pattern in real code)
  - Rapid type alternation stability
  - Subtraction and multiplication deopt paths

FALSIFICATION DESIGN:
  Each test verifies:
  1. Correct result when JIT-compiled (warmup -> JIT -> check result)
  2. Correct deopt when operand type changes
  3. Correct result for both original and new types after deopt

  A test PASSES only if all assertions hold.
  A test FAILS if any assertion fires or an unexpected exception occurs.
"""

import math
import sys
import unittest

try:
    import cinderjit
    HAS_CINDERJIT = True
except ImportError:
    HAS_CINDERJIT = False


def warmup(fn, *args, n=15000):
    for _ in range(n):
        try:
            fn(*args)
        except (TypeError, ValueError):
            pass


class Vector:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __add__(self, other):
        return Vector(self.x + other.x, self.y + other.y)

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y


# -- Test 1: Basic int addition --

def add_ints_1(a, b):
    return a + b


# -- Test 2: Basic int subtraction --

def sub_ints_2(a, b):
    return a - b


# -- Test 3: Basic int multiplication --

def mul_ints_3(a, b):
    return a * b


# -- Test 4: Overflow to bigint (add) --

def add_overflow_4(a, b):
    return a + b


# -- Test 5: Overflow to bigint (multiply) --

def mul_overflow_5(a, b):
    return a * b


# -- Test 6: Add deopt — int-compiled, then float operands --

def add_deopt_6(a, b):
    return a + b


# -- Test 7: Subtract deopt — int-compiled, then float operands --

def sub_deopt_7(a, b):
    return a - b


# -- Test 8: Multiply deopt — int-compiled, then float operands --

def mul_deopt_8(a, b):
    return a * b


# -- Test 9: Mixed operand deopt — one int, one float --

def add_mixed_9(a, b):
    return a + b


# -- Test 10: Custom __add__ deopt --

def add_custom_10(a, b):
    return a + b


# -- Test 11: String concatenation deopt --

def add_str_11(a, b):
    return a + b


# -- Test 12: Accumulator loop --

def accumulate_12(values):
    total = 0
    for v in values:
        total += v
    return total


# -- Test 13: Multiply accumulator (factorial-like) --

def product_13(values):
    result = 1
    for v in values:
        result *= v
    return result


# -- Test 14: Subtraction accumulator (countdown) --

def countdown_14(start, steps):
    value = start
    for s in steps:
        value -= s
    return value


# -- Test 15: Accumulator deopt — int loop then float input --

def accumulate_deopt_15(values):
    total = 0
    for v in values:
        total += v
    return total


# -- Test 16: Rapid type alternation --

def add_alt_16(a, b):
    return a + b


# -- Test 17: TypeError for incompatible types --

def add_typeerr_17(a, b):
    return a + b


# -- Test 18: Combined arithmetic expression --

def combined_18(a, b, c):
    return a + b * c - a


# -- Test 19: Boolean operands (bool is subclass of int) --

def add_bool_19(a, b):
    return a + b


# -- Test 20: List/str multiply deopt --

def mul_repeat_20(a, b):
    return a * b


@unittest.skipUnless(HAS_CINDERJIT, "requires cinderjit")
class TestBinaryOpAddInt(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        warmup(add_ints_1, 3, 7)
        warmup(sub_ints_2, 10, 3)
        warmup(mul_ints_3, 3, 7)
        warmup(add_overflow_4, 100, 200)
        warmup(mul_overflow_5, 10, 20)
        warmup(add_deopt_6, 3, 7)
        warmup(sub_deopt_7, 10, 3)
        warmup(mul_deopt_8, 3, 7)
        warmup(add_mixed_9, 3, 7)
        warmup(add_custom_10, 3, 7)
        warmup(add_str_11, 3, 7)
        warmup(accumulate_12, list(range(100)))
        warmup(product_13, list(range(1, 20)))
        warmup(countdown_14, 100, [1] * 100)
        warmup(accumulate_deopt_15, list(range(50)))
        warmup(add_alt_16, 3, 7)
        warmup(add_typeerr_17, 3, 7)
        warmup(combined_18, 5, 3, 7)
        warmup(add_bool_19, 3, 7)
        warmup(mul_repeat_20, 3, 7)

    def test_01_basic_int_addition(self):
        self.assertEqual(add_ints_1(3, 7), 10)
        self.assertEqual(add_ints_1(0, 0), 0)
        self.assertEqual(add_ints_1(-5, 5), 0)
        self.assertEqual(add_ints_1(-3, -7), -10)
        self.assertEqual(add_ints_1(1, 0), 1)
        self.assertEqual(add_ints_1(0, 1), 1)

    def test_02_basic_int_subtraction(self):
        self.assertEqual(sub_ints_2(10, 3), 7)
        self.assertEqual(sub_ints_2(0, 0), 0)
        self.assertEqual(sub_ints_2(5, 5), 0)
        self.assertEqual(sub_ints_2(-3, 7), -10)
        self.assertEqual(sub_ints_2(3, -7), 10)
        self.assertEqual(sub_ints_2(-3, -7), 4)

    def test_03_basic_int_multiplication(self):
        self.assertEqual(mul_ints_3(3, 7), 21)
        self.assertEqual(mul_ints_3(0, 999), 0)
        self.assertEqual(mul_ints_3(999, 0), 0)
        self.assertEqual(mul_ints_3(-3, 7), -21)
        self.assertEqual(mul_ints_3(-3, -7), 21)
        self.assertEqual(mul_ints_3(1, 42), 42)

    def test_04_overflow_to_bigint_add(self):
        maxint = sys.maxsize
        minint = -sys.maxsize - 1

        result = add_overflow_4(maxint, 1)
        self.assertEqual(result, maxint + 1)
        self.assertIsInstance(result, int)

        result2 = add_overflow_4(maxint, maxint)
        self.assertEqual(result2, 2 * maxint)

        result3 = add_overflow_4(minint, -1)
        self.assertEqual(result3, minint - 1)

    def test_05_overflow_to_bigint_multiply(self):
        maxint = sys.maxsize

        result = mul_overflow_5(maxint, 2)
        self.assertEqual(result, maxint * 2)
        self.assertIsInstance(result, int)

        result2 = mul_overflow_5(maxint, maxint)
        self.assertEqual(result2, maxint * maxint)

    def test_06_add_deopt_int_to_float(self):
        self.assertEqual(add_deopt_6(3, 7), 10)

        float_result = add_deopt_6(3.5, 7.5)
        self.assertEqual(float_result, 11.0)
        self.assertIsInstance(float_result, float)

        int_result = add_deopt_6(3, 7)
        self.assertEqual(int_result, 10)
        self.assertIsInstance(int_result, int)

    def test_07_subtract_deopt_int_to_float(self):
        self.assertEqual(sub_deopt_7(10, 3), 7)

        float_result = sub_deopt_7(10.5, 3.5)
        self.assertEqual(float_result, 7.0)
        self.assertIsInstance(float_result, float)

        self.assertEqual(sub_deopt_7(10, 3), 7)

    def test_08_multiply_deopt_int_to_float(self):
        self.assertEqual(mul_deopt_8(3, 7), 21)

        float_result = mul_deopt_8(3.0, 7.0)
        self.assertEqual(float_result, 21.0)
        self.assertIsInstance(float_result, float)

        self.assertEqual(mul_deopt_8(3, 7), 21)

    def test_09_mixed_operand_deopt(self):
        self.assertEqual(add_mixed_9(3, 7), 10)

        mixed = add_mixed_9(3, 7.5)
        self.assertEqual(mixed, 10.5)
        self.assertIsInstance(mixed, float)

        mixed2 = add_mixed_9(3.5, 7)
        self.assertEqual(mixed2, 10.5)
        self.assertIsInstance(mixed2, float)

        self.assertEqual(add_mixed_9(3, 7), 10)

    def test_10_custom_add_deopt(self):
        self.assertEqual(add_custom_10(3, 7), 10)

        v1 = Vector(1, 2)
        v2 = Vector(3, 4)
        result = add_custom_10(v1, v2)
        self.assertEqual(result, Vector(4, 6))

        self.assertEqual(add_custom_10(3, 7), 10)

    def test_11_string_concatenation_deopt(self):
        self.assertEqual(add_str_11(3, 7), 10)

        str_result = add_str_11("hello", " world")
        self.assertEqual(str_result, "hello world")
        self.assertIsInstance(str_result, str)

        self.assertEqual(add_str_11(3, 7), 10)

    def test_12_accumulator_loop(self):
        data = list(range(100))
        self.assertEqual(accumulate_12(data), 4950)
        self.assertEqual(accumulate_12([]), 0)
        self.assertEqual(accumulate_12([1]), 1)
        self.assertEqual(accumulate_12([-1, 1, -1, 1]), 0)
        self.assertEqual(accumulate_12([sys.maxsize, 1]), sys.maxsize + 1)

    def test_13_multiply_accumulator(self):
        data_mul = list(range(1, 20))
        self.assertEqual(product_13(data_mul), math.factorial(19))
        self.assertEqual(product_13([1]), 1)
        self.assertEqual(product_13([0, 1, 2, 3]), 0)
        self.assertEqual(product_13([-1, 2, 3]), -6)
        self.assertEqual(product_13([-1, -1, -1]), -1)

    def test_14_subtraction_accumulator(self):
        steps = [1] * 100
        self.assertEqual(countdown_14(100, steps), 0)
        self.assertEqual(countdown_14(0, [1, 2, 3]), -6)
        self.assertEqual(countdown_14(10, [-1, -2, -3]), 16)
        self.assertEqual(countdown_14(sys.maxsize, [sys.maxsize]), 0)

    def test_15_accumulator_deopt_int_to_float(self):
        self.assertEqual(accumulate_deopt_15(list(range(50))), 1225)

        float_data = [1.5, 2.5, 3.0]
        float_result = accumulate_deopt_15(float_data)
        self.assertEqual(float_result, 7.0)
        self.assertIsInstance(float_result, float)

        self.assertEqual(accumulate_deopt_15(list(range(50))), 1225)

    def test_16_rapid_type_alternation(self):
        for _ in range(200):
            self.assertEqual(add_alt_16(3, 7), 10)
            self.assertEqual(add_alt_16(3.0, 7.0), 10.0)
            self.assertEqual(add_alt_16("a", "b"), "ab")

    def test_17_typeerror_for_incompatible_types(self):
        with self.assertRaises(TypeError):
            add_typeerr_17(3, "hello")

        with self.assertRaises(TypeError):
            add_typeerr_17("hello", 3)

        self.assertEqual(add_typeerr_17(3, 7), 10)

    def test_18_combined_arithmetic_expression(self):
        # a + b*c - a = b*c
        self.assertEqual(combined_18(5, 3, 7), 21)
        self.assertEqual(combined_18(0, 0, 0), 0)
        self.assertEqual(combined_18(100, 2, 3), 6)
        self.assertEqual(combined_18(-5, -3, -7), 21)

        float_r = combined_18(5.0, 3.0, 7.0)
        self.assertEqual(float_r, 21.0)

        self.assertEqual(combined_18(5, 3, 7), 21)

    def test_19_bool_operands(self):
        result = add_bool_19(True, True)
        self.assertEqual(result, 2)

        result2 = add_bool_19(True, 5)
        self.assertEqual(result2, 6)

        result3 = add_bool_19(False, 0)
        self.assertEqual(result3, 0)

        self.assertEqual(add_bool_19(3, 7), 10)

    def test_20_multiply_deopt_str_list_repetition(self):
        self.assertEqual(mul_repeat_20(3, 7), 21)

        self.assertEqual(mul_repeat_20(3, "ab"), "ababab")

        self.assertEqual(mul_repeat_20("xy", 2), "xyxy")

        self.assertEqual(mul_repeat_20(3, [1, 2]), [1, 2, 1, 2, 1, 2])

        self.assertEqual(mul_repeat_20(3, 7), 21)


if __name__ == "__main__":
    unittest.main()
