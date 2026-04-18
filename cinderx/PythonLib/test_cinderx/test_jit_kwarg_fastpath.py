"""Correctness tests for JITRT_CallWithKeywordArgs fast path."""
import unittest
import cinderjit


def add(a, b):
    return a + b

def add3(a, b, c):
    return a + b + c

def with_defaults(a, b=10, c=20):
    return a + b + c

def posonly(a, b, /, c, d):
    return a + b + c + d

def varargs(a, b, *args):
    return a + b + sum(args)

def varkw(a, b, **kwargs):
    return a + b + sum(kwargs.values())

def kwonly(a, *, b):
    return a + b


class TestKwargFastPath(unittest.TestCase):

    def setUp(self):
        cinderjit.auto()
        for _ in range(1100):
            add(1, 2); add3(1, 2, 3)
            with_defaults(1, 2, 3); with_defaults(1)
            posonly(1, 2, c=3, d=4)
            varargs(1, 2, 3); varkw(1, 2, x=3); kwonly(1, b=2)

    def test_all_kwarg_in_order(self):
        self.assertEqual(add(a=10, b=20), 30)
        self.assertEqual(add3(a=1, b=2, c=3), 6)

    def test_wrong_kwarg_order(self):
        self.assertEqual(add(b=20, a=10), 30)
        self.assertEqual(add3(c=3, a=1, b=2), 6)

    def test_mixed_positional_kwarg(self):
        self.assertEqual(add(10, b=20), 30)
        self.assertEqual(add3(1, b=2, c=3), 6)
        self.assertEqual(add3(1, 2, c=3), 6)

    def test_defaults_with_partial_kwargs(self):
        self.assertEqual(with_defaults(1), 31)
        self.assertEqual(with_defaults(1, b=5), 26)
        self.assertEqual(with_defaults(a=1, b=5, c=10), 16)

    def test_positional_only_with_kwargs(self):
        self.assertEqual(posonly(1, 2, c=3, d=4), 10)

    def test_dict_unpacking(self):
        d = {'a': 10, 'b': 20}
        self.assertEqual(add(**d), 30)

    def test_varargs_varkw_kwonly(self):
        self.assertEqual(varargs(a=1, b=2), 3)
        self.assertEqual(varkw(a=1, b=2, x=10), 13)
        self.assertEqual(kwonly(a=1, b=2), 3)


if __name__ == '__main__':
    unittest.main()
