"""Tests for yield_from SEND_GEN fast path correctness.

Verifies that yield_from delegation:
- Produces correct results for simple delegation
- Correctly forwards non-None send() values through the chain
- Handles generator.throw() through delegation
- Handles generator.close() through delegation
- Works with nested yield_from chains
"""
import cinderjit
import unittest


class TestYieldFrom(unittest.TestCase):

    def setUp(self):
        cinderjit.auto()

    def test_simple_delegation(self):
        def inner():
            yield 1
            yield 2
            yield 3

        def outer():
            yield from inner()

        for _ in range(1200):
            list(outer())
        self.assertTrue(cinderjit.is_jit_compiled(outer))
        self.assertEqual(list(outer()), [1, 2, 3])

    def test_send_non_none_value(self):
        def inner():
            received = yield 'ready'
            yield f'got:{received}'

        def outer():
            yield from inner()

        for _ in range(1200):
            g = outer()
            next(g)
            try:
                g.send('hello')
            except StopIteration:
                pass

        self.assertTrue(cinderjit.is_jit_compiled(outer))
        g = outer()
        self.assertEqual(next(g), 'ready')
        self.assertEqual(g.send('hello'), 'got:hello')

    def test_send_various_values(self):
        def accumulator():
            total = 0
            while True:
                value = yield total
                if value is None:
                    break
                total += value

        def delegator():
            result = yield from accumulator()
            return result

        for _ in range(1200):
            g = delegator()
            next(g)
            g.send(10)
            g.send(20)
            try:
                g.send(None)
            except StopIteration:
                pass

        self.assertTrue(cinderjit.is_jit_compiled(delegator))
        g = delegator()
        self.assertEqual(next(g), 0)
        self.assertEqual(g.send(10), 10)
        self.assertEqual(g.send(20), 30)
        with self.assertRaises(StopIteration):
            g.send(None)

    def test_throw_through_delegation(self):
        def inner():
            try:
                yield 'running'
            except ValueError:
                yield 'caught ValueError'

        def outer():
            yield from inner()

        for _ in range(1200):
            g = outer()
            next(g)
            try:
                g.throw(ValueError)
            except StopIteration:
                pass

        self.assertTrue(cinderjit.is_jit_compiled(outer))
        g = outer()
        self.assertEqual(next(g), 'running')
        self.assertEqual(g.throw(ValueError), 'caught ValueError')

    def test_close_through_delegation(self):
        closed = []

        def inner(tracker):
            try:
                yield 1
                yield 2
            finally:
                tracker.append('inner closed')

        def outer(tracker):
            yield from inner(tracker)

        for _ in range(1200):
            t = []
            g = outer(t)
            next(g)
            g.close()

        self.assertTrue(cinderjit.is_jit_compiled(outer))
        tracker = []
        g = outer(tracker)
        self.assertEqual(next(g), 1)
        g.close()
        self.assertEqual(tracker, ['inner closed'])

    def test_nested_yield_from(self):
        def bottom():
            yield 'a'
            yield 'b'

        def middle():
            yield from bottom()

        def top():
            yield from middle()

        for _ in range(1200):
            list(top())
        self.assertTrue(cinderjit.is_jit_compiled(top))
        self.assertEqual(list(top()), ['a', 'b'])

    def test_return_value_propagation(self):
        def inner():
            yield 1
            return 42

        def outer():
            result = yield from inner()
            yield result

        for _ in range(1200):
            list(outer())
        self.assertTrue(cinderjit.is_jit_compiled(outer))
        self.assertEqual(list(outer()), [1, 42])


if __name__ == '__main__':
    unittest.main()
