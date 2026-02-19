# Data-access opcode exception tests for test_jit_exception.py
# Append this to the end of test_jit_exception.py
#
# Tests exception handling for LOAD_ATTR, BINARY_SUBSCR, STORE_ATTR,
# DELETE_ATTR, STORE_SUBSCR, and LOAD_GLOBAL inside try/except blocks
# in JIT-compiled functions.
#
# Gap 9 in the coverage audit: LOAD_ATTR was missing a Guard after
# LoadAttrCache::invoke(), causing SEGFAULT instead of catching
# AttributeError. Fixed by commit 2a7f034f.
#
# Groups 2-3 (BINARY_SUBSCR, STORE_ATTR, DELETE_ATTR, STORE_SUBSCR,
# LOAD_GLOBAL) already worked pre-fix. They serve as regression gates.

class DataAccessExceptionTests(unittest.TestCase):
    """Tests for exceptions from data-access opcodes in try/except.

    These opcodes raise exceptions when the attribute/key doesn't exist.
    The JIT must catch these via the exception table, not crash.
    """

    # --- Group 1: LOAD_ATTR in try/except (Gap 9 core reproducer) ---

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def load_attr_except(self, obj):
        try:
            return obj.nonexistent_attr
        except AttributeError:
            return "caught"

    def test_load_attr_missing_attribute(self) -> None:
        """Missing attribute on regular object -> AttributeError caught."""
        class C:
            pass
        self.assertEqual(self.load_attr_except(C()), "caught")

    def test_load_attr_existing_attribute(self) -> None:
        """Existing attribute -> normal return (happy path)."""
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

    def test_load_attr_on_none(self) -> None:
        """None.x -> AttributeError caught."""
        self.assertEqual(self.load_attr_none(None), "caught")

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def load_attr_method(self, obj):
        try:
            return obj.missing_method()
        except AttributeError:
            return "caught"

    def test_load_attr_missing_method(self) -> None:
        """Missing method call -> AttributeError caught."""
        class C:
            pass
        self.assertEqual(self.load_attr_method(C()), "caught")

    # --- Group 2: BINARY_SUBSCR in try/except ---

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def subscr_except(self, container, key):
        try:
            return container[key]
        except (KeyError, IndexError, TypeError):
            return "caught"

    def test_dict_missing_key(self) -> None:
        self.assertEqual(self.subscr_except({"a": 1}, "b"), "caught")

    def test_dict_existing_key(self) -> None:
        self.assertEqual(self.subscr_except({"a": 1}, "a"), 1)

    def test_list_index_out_of_range(self) -> None:
        self.assertEqual(self.subscr_except([1, 2], 5), "caught")

    def test_list_valid_index(self) -> None:
        self.assertEqual(self.subscr_except([10, 20], 1), 20)

    # --- Group 3: STORE_ATTR, DELETE_ATTR, STORE_SUBSCR ---

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def store_attr_except(self, obj, value):
        try:
            obj.x = value
            return "stored"
        except (AttributeError, TypeError):
            return "caught"

    def test_store_attr_on_int(self) -> None:
        """Store to immutable object -> caught."""
        self.assertEqual(self.store_attr_except(42, 99), "caught")

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def delete_attr_except(self, obj):
        try:
            del obj.x
            return "deleted"
        except AttributeError:
            return "caught"

    def test_delete_attr_missing(self) -> None:
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

    def test_store_subscr_immutable(self) -> None:
        self.assertEqual(self.store_subscr_except((1, 2), 0, 99), "caught")

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def load_global_except(self):
        try:
            return undefined_global_name_xyz  # noqa: F821
        except NameError:
            return "caught"

    def test_load_global_missing(self) -> None:
        self.assertEqual(self.load_global_except(), "caught")

    # --- Group 4: Mixed patterns (call + data-access in same try block) ---

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def mixed_call_and_attr(self, obj, func):
        try:
            x = obj.value
            return func(x)
        except (AttributeError, TypeError):
            return "caught"

    def test_mixed_attr_fails(self) -> None:
        class C:
            pass
        self.assertEqual(self.mixed_call_and_attr(C(), str), "caught")

    def test_mixed_call_fails(self) -> None:
        class C:
            value = None
        def bad(x):
            raise TypeError("nope")
        self.assertEqual(self.mixed_call_and_attr(C(), bad), "caught")

    def test_mixed_both_succeed(self) -> None:
        class C:
            value = 42
        self.assertEqual(self.mixed_call_and_attr(C(), str), "42")
