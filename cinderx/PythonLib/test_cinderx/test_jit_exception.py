# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-unsafe

import sys
import unittest

import cinderx.test_support as cinder_support

from .common import failUnlessHasOpcodes


POST_311 = sys.version_info >= (3, 11)

# Opcode to look for when inspecting code objects that use try/except/finally.
EXN_OPCODE = "PUSH_EXC_INFO" if POST_311 else "SETUP_FINALLY"


class Err1(Exception):
    pass


class Err2(Exception):
    pass


class DummyContainer:
    def __len__(self):
        raise Exception("hello!")


class ExceptionInConditional(unittest.TestCase):
    @cinder_support.failUnlessJITCompiled
    def doit(self, x):
        if x:
            return 1
        return 2

    def test_exception_thrown_in_conditional(self) -> None:
        with self.assertRaisesRegex(Exception, "hello!"):
            self.doit(DummyContainer())


class ExceptionHandlingTests(unittest.TestCase):
    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def try_except(self, func):
        try:
            func()
        except:  # noqa: B001
            return True
        return False

    def test_raise_and_catch(self) -> None:
        def f():
            raise Exception("hello")

        self.assertTrue(self.try_except(f))

        def g():
            pass

        self.assertFalse(self.try_except(g))

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def catch_multiple(self, func):
        try:
            func()
        except Err1:
            return 1
        except Err2:
            return 2

    def test_multiple_except_blocks(self) -> None:
        def f():
            raise Err1("err1")

        self.assertEqual(self.catch_multiple(f), 1)

        def g():
            raise Err2("err2")

        self.assertEqual(self.catch_multiple(g), 2)

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def reraise(self, func):
        try:
            func()
        except:  # noqa: B001
            raise

    def test_reraise(self) -> None:
        def f():
            raise Exception("hello")

        with self.assertRaisesRegex(Exception, "hello"):
            self.reraise(f)

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def try_except_in_loop(self, niters, f):
        for i in range(niters):
            try:
                try:
                    f(i)
                except Err2:
                    pass
            except Err1:
                break
        return i

    def test_try_except_in_loop(self) -> None:
        def f(i):
            if i == 10:
                raise Err1("hello")

        self.assertEqual(self.try_except_in_loop(20, f), 10)

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def nested_try_except(self, f):
        try:
            try:
                try:
                    f()
                except:  # noqa: B001
                    raise
            except:  # noqa: B001
                raise
        except:  # noqa: B001
            return 100

    def test_nested_try_except(self) -> None:
        def f():
            raise Exception("hello")

        self.assertEqual(self.nested_try_except(f), 100)

    @cinder_support.failUnlessJITCompiled
    def try_except_in_generator(self, f):
        try:
            yield f(0)
            yield f(1)
            yield f(2)
        except:  # noqa: B001
            yield 123

    def test_except_in_generator(self) -> None:
        def f(i):
            if i == 1:
                raise Exception("hello")
            return

        g = self.try_except_in_generator(f)
        next(g)
        self.assertEqual(next(g), 123)

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE, "RERAISE")
    def try_finally(self, should_raise):
        result = None
        try:
            if should_raise:
                raise Exception("testing 123")
        finally:
            result = 100
        return result

    def test_try_finally(self) -> None:
        self.assertEqual(self.try_finally(False), 100)
        with self.assertRaisesRegex(Exception, "testing 123"):
            self.try_finally(True)

    @cinder_support.failUnlessJITCompiled
    def try_except_finally(self, should_raise):
        result = None
        try:
            if should_raise:
                raise Exception("testing 123")
        except Exception:
            result = 200
        finally:
            if result is None:
                result = 100
        return result

    def test_try_except_finally(self) -> None:
        self.assertEqual(self.try_except_finally(False), 100)
        self.assertEqual(self.try_except_finally(True), 200)

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def return_in_finally(self, v):
        try:
            pass
        finally:
            return v  # noqa: B012

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def return_in_finally2(self, v):
        try:
            return v
        finally:
            return 100  # noqa: B012

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def return_in_finally3(self, v):
        try:
            1 / 0
        finally:
            return v  # noqa: B012

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def return_in_finally4(self, v):
        try:
            return 100
        finally:
            try:
                1 / 0
            finally:
                return v  # noqa: B012

    def test_return_in_finally(self) -> None:
        self.assertEqual(self.return_in_finally(100), 100)
        self.assertEqual(self.return_in_finally2(200), 100)
        self.assertEqual(self.return_in_finally3(300), 300)
        self.assertEqual(self.return_in_finally4(400), 400)

    @cinder_support.failUnlessJITCompiled
    def break_in_finally_after_return(self, x):
        for count in [0, 1]:
            count2 = 0
            while count2 < 20:
                count2 += 10
                try:
                    return count + count2
                finally:
                    if x:
                        break  # noqa: B012
        return "end", count, count2

    @cinder_support.failUnlessJITCompiled
    def break_in_finally_after_return2(self, x):
        for count in [0, 1]:
            for count2 in [10, 20]:
                try:
                    return count + count2
                finally:
                    if x:
                        break  # noqa: B012
        return "end", count, count2

    def test_break_in_finally_after_return(self) -> None:
        self.assertEqual(self.break_in_finally_after_return(False), 10)
        self.assertEqual(self.break_in_finally_after_return(True), ("end", 1, 10))
        self.assertEqual(self.break_in_finally_after_return2(False), 10)
        self.assertEqual(self.break_in_finally_after_return2(True), ("end", 1, 10))

    @cinder_support.failUnlessJITCompiled
    def continue_in_finally_after_return(self, x):
        count = 0
        while count < 100:
            count += 1
            try:
                return count
            finally:
                if x:
                    continue  # noqa: B012
        return "end", count

    @cinder_support.failUnlessJITCompiled
    def continue_in_finally_after_return2(self, x):
        for count in [0, 1]:
            try:
                return count
            finally:
                if x:
                    continue  # noqa: B012
        return "end", count

    def test_continue_in_finally_after_return(self) -> None:
        self.assertEqual(self.continue_in_finally_after_return(False), 1)
        self.assertEqual(self.continue_in_finally_after_return(True), ("end", 100))
        self.assertEqual(self.continue_in_finally_after_return2(False), 0)
        self.assertEqual(self.continue_in_finally_after_return2(True), ("end", 1))

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def return_in_loop_in_finally(self, x):
        try:
            for _ in [1, 2, 3]:
                if x:
                    return x
        finally:
            pass
        return 100

    def test_return_in_loop_in_finally(self) -> None:
        self.assertEqual(self.return_in_loop_in_finally(True), True)
        self.assertEqual(self.return_in_loop_in_finally(False), 100)

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def conditional_return_in_finally(self, x, y, z):
        try:
            if x:
                return x
            if y:
                return y
        finally:
            pass
        return z

    def test_conditional_return_in_finally(self) -> None:
        self.assertEqual(self.conditional_return_in_finally(100, False, False), 100)
        self.assertEqual(self.conditional_return_in_finally(False, 200, False), 200)
        self.assertEqual(self.conditional_return_in_finally(False, False, 300), 300)

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def nested_finally(self, x):
        try:
            if x:
                return x
        finally:
            try:
                y = 10
            finally:
                z = y
        return z

    def test_nested_finally(self) -> None:
        self.assertEqual(self.nested_finally(100), 100)
        self.assertEqual(self.nested_finally(False), 10)


class DataAccessExceptionTests(unittest.TestCase):
    """Tests for exceptions from data-access opcodes in try/except."""

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def load_attr_except(self, obj):
        try:
            return obj.nonexistent_attr
        except AttributeError:
            return "caught"

    def test_load_attr_missing_attribute(self):
        class C:
            pass
        self.assertEqual(self.load_attr_except(C()), "caught")

    def test_load_attr_existing_attribute(self):
        class C:
            nonexistent_attr = 42
        self.assertEqual(self.load_attr_except(C()), 42)

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def load_attr_none(self, obj):
        try:
            return obj.x
        except AttributeError:
            return "caught"

    def test_load_attr_on_none(self):
        self.assertEqual(self.load_attr_none(None), "caught")

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def load_attr_method(self, obj):
        try:
            return obj.missing_method()
        except AttributeError:
            return "caught"

    def test_load_attr_missing_method(self):
        class C:
            pass
        self.assertEqual(self.load_attr_method(C()), "caught")

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def subscr_except(self, container, key):
        try:
            return container[key]
        except (KeyError, IndexError, TypeError):
            return "caught"

    def test_dict_missing_key(self):
        self.assertEqual(self.subscr_except({"a": 1}, "b"), "caught")

    def test_dict_existing_key(self):
        self.assertEqual(self.subscr_except({"a": 1}, "a"), 1)

    def test_list_index_out_of_range(self):
        self.assertEqual(self.subscr_except([1, 2], 5), "caught")

    def test_list_valid_index(self):
        self.assertEqual(self.subscr_except([10, 20], 1), 20)

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def store_attr_except(self, obj, value):
        try:
            obj.x = value
            return "stored"
        except (AttributeError, TypeError):
            return "caught"

    def test_store_attr_on_int(self):
        self.assertEqual(self.store_attr_except(42, 99), "caught")

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def delete_attr_except(self, obj):
        try:
            del obj.x
            return "deleted"
        except AttributeError:
            return "caught"

    def test_delete_attr_missing(self):
        class C:
            pass
        self.assertEqual(self.delete_attr_except(C()), "caught")

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def store_subscr_except(self, container, key, value):
        try:
            container[key] = value
            return "stored"
        except TypeError:
            return "caught"

    def test_store_subscr_immutable(self):
        self.assertEqual(self.store_subscr_except((1, 2), 0, 99), "caught")

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def load_global_except(self):
        try:
            return undefined_global_name_xyz
        except NameError:
            return "caught"

    def test_load_global_missing(self):
        self.assertEqual(self.load_global_except(), "caught")

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def mixed_call_and_attr(self, obj, func):
        try:
            x = obj.value
            return func(x)
        except (AttributeError, TypeError):
            return "caught"

    def test_mixed_attr_fails(self):
        class C:
            pass
        self.assertEqual(self.mixed_call_and_attr(C(), str), "caught")

    def test_mixed_call_fails(self):
        class C:
            value = None
        def bad(x):
            raise TypeError("nope")
        self.assertEqual(self.mixed_call_and_attr(C(), bad), "caught")

    def test_mixed_both_succeed(self):
        class C:
            value = 42
        self.assertEqual(self.mixed_call_and_attr(C(), str), "42")
