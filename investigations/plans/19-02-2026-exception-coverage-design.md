# Exception Handling Coverage Design — CinderX JIT (aarch64)

**Date:** 19 February 2026
**Author:** @testkeeper
**Purpose:** Design regression tests for Gap 9 (LOAD_ATTR in try/except crashes)

## Background

~~The CinderX JIT on aarch64 SEGFAULTs when a data-access opcode (LOAD_ATTR, BINARY_SUBSCR, etc.) raises an exception inside a try/except block in a JIT-compiled function.~~ **CORRECTED (19 Feb 07:45Z):** The bug is **LOAD_ATTR-specific**. All other data-access opcodes (BINARY_SUBSCR, STORE_ATTR, DELETE_ATTR, LOAD_GLOBAL) correctly catch exceptions in try/except when JIT-compiled.

The existing `test_jit_exception.py` (15 tests, all pass) only tests exceptions from **function calls** and **explicit raises** — never from LOAD_ATTR.

### Root Cause Summary (CORRECTED)

~~Initially hypothesised as "exception tables not parsed".~~ Empirical testing falsified this:

| Opcode | try/except works in JIT? | LIR Guard emitted? |
|--------|-------------------------|-------------------|
| CALL (func()) | YES | YES (Guard after Call) |
| BINARY_SUBSCR (d[k]) | YES | YES (Guard after Call) |
| STORE_ATTR (obj.x = v) | YES | YES |
| DELETE_ATTR (del obj.x) | YES | YES |
| LOAD_GLOBAL (name) | YES | YES |
| **LOAD_ATTR (obj.attr)** | **NO** | **NO — missing Guard** |

The actual root cause:

1. **Exception tables DO work** — the JIT deopts to the interpreter on NULL returns, and the interpreter dispatches to the exception handler via `co_exceptiontable`. This works for all tested opcodes except LOAD_ATTR.
2. **BinaryOp<Subscript>** in the LIR has: `Call ... → Guard kNotZero (deopt on NULL)`. The Guard triggers deopt when the call returns NULL.
3. **LoadAttrCached** in the LIR has: `Call ... → (no Guard)`. The NULL return value propagates unchecked.
4. The LoadAttrCached LIR generation at generator.cpp:~1338 uses `appendCallInstruction()` without adding a Guard. BinaryOp's translation does add a Guard.
5. builder.cpp:555 comment about SETUP_FINALLY is a red herring — exception handling IS implemented via deopt+interpreter, not via HIR blocks. SETUP_FINALLY is dead code on 3.12 but irrelevant to the bug.

**Fix:** Remove the single line `case Opcode::kLoadAttrCached:` from the exemption list at generator.cpp:3551. Then `emitExceptionCheck` runs for it via the `default:` case, adding the missing Guard. All other exempted opcodes (kStoreAttr, kStoreAttrCached, kStoreSubscr, etc.) correctly handle their own exceptions — verified empirically on devgpu004.

### Existing Coverage (test_jit_exception.py)

| Test | Pattern | Exception Source | Passes |
|------|---------|-----------------|--------|
| test_raise_and_catch | `try: func() except:` | CALL | Yes |
| test_multiple_except_blocks | `try: func() except Err1: except Err2:` | CALL | Yes |
| test_reraise | `try: func() except: raise` | CALL | Yes |
| test_try_except_in_loop | nested try/except in for loop | CALL (f(i)) | Yes |
| test_nested_try_except | triple-nested try/except | CALL (f()) | Yes |
| test_except_in_generator | generator with try/except | CALL (f(i)) | Yes |
| test_try_finally | `try: raise ... finally:` | RAISE | Yes |
| test_try_except_finally | `try: raise ... except: finally:` | RAISE | Yes |
| test_return_in_finally (×4) | return in finally variants | RAISE / 1/0 | Yes |
| test_break_in_finally_after_return (×2) | break in finally | implicit | Yes |
| test_continue_in_finally_after_return (×2) | continue in finally | implicit | Yes |
| test_return_in_loop_in_finally | return in loop in finally | implicit | Yes |
| test_conditional_return_in_finally | conditional return in try | implicit | Yes |
| test_nested_finally | nested try/finally | implicit | Yes |

**Gap**: Zero tests for exceptions from LOAD_ATTR inside try/except. Other data-access opcodes (BINARY_SUBSCR, STORE_ATTR, DELETE_ATTR, LOAD_GLOBAL) are also untested but work correctly — verified empirically on devgpu004 (19 Feb 07:40Z).

## Proposed Test Cases

All tests should use `@cinder_support.failUnlessJITCompiled` to ensure JIT compilation, matching the existing test_jit_exception.py pattern. Tests for the known-crashing pattern (LOAD_ATTR in try/except) should be marked `@unittest.expectedFailure` until the fix lands.

### Group 1: LOAD_ATTR in try/except (crashes — Gap 9 core reproducer)

These are the minimal tests that expose the SEGFAULT.

```python
class DataAccessExceptionTests(unittest.TestCase):
    """Tests for exceptions from data-access opcodes in try/except.

    These opcodes (LOAD_ATTR, BINARY_SUBSCR, etc.) raise exceptions
    when the attribute/key doesn't exist. The JIT must catch these
    via the exception table, not crash.

    Gap 9 in the coverage audit: the JIT compiles the happy path
    only (no exception handler blocks) for these opcodes.
    """

    @unittest.expectedFailure  # Gap 9: SEGFAULT on aarch64
    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def load_attr_except(self, obj, attr_name):
        """LOAD_ATTR raising AttributeError inside try/except."""
        try:
            return getattr(obj, attr_name)
        except AttributeError:
            return "caught"

    def test_load_attr_missing_attribute(self):
        """Missing attribute on regular object → AttributeError caught."""
        class C:
            pass
        self.assertEqual(self.load_attr_except(C(), "nonexistent"), "caught")

    def test_load_attr_existing_attribute(self):
        """Existing attribute → normal return (happy path)."""
        class C:
            x = 42
        self.assertEqual(self.load_attr_except(C(), "x"), 42)

    @unittest.expectedFailure  # Gap 9
    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def load_attr_direct(self, obj):
        """Direct LOAD_ATTR (not getattr) raising inside try/except."""
        try:
            return obj.nonexistent_attr
        except AttributeError:
            return "caught"

    def test_load_attr_direct_missing(self):
        class C:
            pass
        self.assertEqual(self.load_attr_direct(C()), "caught")
```

### Group 2: BINARY_SUBSCR in try/except

```python
    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def subscr_except(self, container, key):
        """BINARY_SUBSCR raising inside try/except."""
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
```

### Group 3: Other data-access opcodes

```python
    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def store_attr_except(self, obj, value):
        """STORE_ATTR raising inside try/except."""
        try:
            obj.x = value
            return "stored"
        except AttributeError:
            return "caught"

    def test_store_attr_on_frozen(self):
        """Store to frozen/read-only object."""
        self.assertEqual(self.store_attr_except(42, 99), "caught")

    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def delete_attr_except(self, obj):
        """DELETE_ATTR raising inside try/except."""
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
        """STORE_SUBSCR raising inside try/except."""
        try:
            container[key] = value
            return "stored"
        except TypeError:
            return "caught"

    def test_store_subscr_immutable(self):
        self.assertEqual(self.store_subscr_except((1, 2), 0, 99), "caught")
```

### Group 4: Mixed patterns (call + data-access in same try block)

```python
    @cinder_support.failUnlessJITCompiled
    @failUnlessHasOpcodes(EXN_OPCODE)
    def mixed_call_and_attr(self, obj, func):
        """Both CALL and LOAD_ATTR in same try block."""
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
```

### Group 5: Auto-compile integration (not unit tests)

These test the import-time SEGFAULT scenario at a higher level:

```python
    def test_auto_compile_skips_exception_functions(self):
        """After bail-out fix: auto-compile must skip functions with
        exception handlers, not crash.

        This is the integration-level falsifier for the import-time
        SEGFAULT. If auto-compile no longer crashes on functions
        with try/except, the import-time crash is resolved.
        """
        import cinderjit
        # Enable auto-compile with low threshold
        cinderjit.auto()

        # Define a function with try/except that will be called
        # enough times to trigger auto-compilation
        def safe_getattr(obj, name, default=None):
            try:
                return getattr(obj, name)
            except AttributeError:
                return default

        class Obj:
            x = 42

        # Call many times — should either:
        # (a) Auto-compile and work correctly, OR
        # (b) Skip compilation (bail out) and run in interpreter
        # Must NOT crash.
        o = Obj()
        for i in range(500):
            result = safe_getattr(o, "x")
            assert result == 42, f"Expected 42, got {result}"
            result = safe_getattr(o, "missing", -1)
            assert result == -1, f"Expected -1, got {result}"
```

## Where to Add These Tests

**Option A** (recommended): Add `DataAccessExceptionTests` class to the existing `test_jit_exception.py`. This keeps all exception-handling tests in one file and follows the existing pattern.

**Option B**: Create a new file `test_jit_exception_data_access.py` in `test_cinderx/`. This avoids modifying existing code but adds a new suite to the runner.

I recommend Option A — it's the existing convention, and the existing tests use exactly the same decorators and patterns.

## Test Categorisation (CORRECTED)

| Test | Current Status | After Guard Fix |
|------|---------------|----------------|
| Group 1 (LOAD_ATTR) | Exception escapes / SEGFAULT | PASS |
| Group 2 (SUBSCR) | **PASS** (verified) | PASS |
| Group 3 (STORE/DELETE) | **PASS** (verified) | PASS |
| Group 4 (Mixed call+attr) | Partial (attr part fails) | PASS |
| Group 5 (Auto-compile) | SEGFAULT | PASS |

Groups 2 and 3 can be added immediately as passing regression tests. Group 1 tests should be marked `@unittest.expectedFailure` until the Guard fix lands. Group 4 will partially fail (the LOAD_ATTR path). Group 5 depends on whether auto-compile hits LOAD_ATTR in try/except patterns.

## Falsifiers

1. **If Group 1 tests pass WITHOUT any fix**: Our root cause analysis is wrong — LoadAttrCached does have a Guard. We should re-examine the LIR dump.
2. ~~If Group 2 tests pass but Group 1 doesn't~~ **CONFIRMED**: BINARY_SUBSCR has a Guard but LOAD_ATTR doesn't. This is the actual bug pattern.
3. **If adding a Guard after LoadAttrCached Call fixes Group 1**: Root cause confirmed — the fix is complete.
4. **If Group 5 still crashes after Guard fix**: There are other opcodes without Guards, or the import-time crash has a different root cause.
5. **If existing test_jit_exception tests regress**: Our changes broke something — revert immediately.

## Coordination

@claude should add a Guard (kNotZero, deopt on NULL) after the `appendCallInstruction` for LoadAttrCached in generator.cpp:~1338. This matches the pattern used by BinaryOp<Subscript> which inserts a Guard after its Call.

The test design above works with either approach:

- **Guard fix (recommended)**: Group 1 tests pass. Remove `expectedFailure` markers.
- **Bail-out fix**: Group 1 tests raise RuntimeError from force_compile (compilation refused). The `failUnlessJITCompiled` decorator handles this — tests are skipped.

Groups 2-3 can be added immediately as they already pass. They serve as regression gates to ensure other opcodes don't lose their Guards in future changes.
