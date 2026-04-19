"""Tests for inline exception handling (emitInlineExceptionMatch)."""
import cinderjit
import unittest


class TestInlineExceptionHandling(unittest.TestCase):

    def test_simple_keyerror(self):
        def f():
            d = {0: 'a', 2: 'b'}
            try:
                return d[1]
            except KeyError:
                return 'missing'

        cinderjit.force_compile(f)
        self.assertEqual(f(), 'missing')

    def test_simple_hit(self):
        def f():
            d = {0: 'a', 1: 'b'}
            try:
                return d[1]
            except KeyError:
                return 'missing'

        cinderjit.force_compile(f)
        self.assertEqual(f(), 'b')

    def test_augmented_assignment_mixed(self):
        def f(n):
            d = {i: i * 2 for i in range(0, 1000, 2)}
            total = 0
            for i in range(n):
                try:
                    total += d[i % 1000]
                except KeyError:
                    total += 1
            return total

        cinderjit.force_compile(f)
        self.assertEqual(f(10), 45)
        self.assertEqual(f(100), 4950)
        self.assertEqual(f(1000), 499500)
        self.assertEqual(f(10000), 4995000)

    def test_except_wrong_type(self):
        def f():
            d = {0: 'a'}
            try:
                return d[1]
            except ValueError:
                return 'wrong type'

        cinderjit.force_compile(f)
        with self.assertRaises(KeyError):
            f()

    def test_no_except_block(self):
        def f():
            d = {0: 'a', 1: 'b'}
            return d[1]

        cinderjit.force_compile(f)
        self.assertEqual(f(), 'b')

    def test_large_iteration_mixed(self):
        def f(n):
            d = {i: i * 2 for i in range(0, 1000, 2)}
            total = 0
            for i in range(n):
                try:
                    total += d[i % 1000]
                except KeyError:
                    total += 1
            return total

        cinderjit.force_compile(f)
        result = f(100000)
        self.assertEqual(result, 49950000)


if __name__ == '__main__':
    unittest.main()
