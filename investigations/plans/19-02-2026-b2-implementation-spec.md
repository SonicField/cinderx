# B2 Implementation Specification — Inline Exception Match in JIT

**Date:** 19 February 2026
**Author:** @theologian
**Status:** Design specification for implementation

## Goal

Eliminate the deopt overhead (18ns) for exceptions caught by a simple `try/except SomeType` pattern. The JIT checks the exception type inline and branches to the except body without leaving JIT code.

## Scope

B2 handles ONLY the simplest pattern:
```python
try:
    result = expr_that_can_raise()
except SomeType:
    fallback_code
```

Does NOT handle: bare `except:`, `except (A, B):`, `finally`, `else`, nested try, exception value capture (`except X as e`).

## Concrete Bytecode Pattern (bench_exceptions)

```
Offset 36: LOAD_FAST total       ← Try body starts (ET: 36-56 → 66 [depth=1])
Offset 48: BINARY_SUBSCR         ← Can raise KeyError
Offset 52: BINARY_OP +=
Offset 56: STORE_FAST total
Offset 58: JUMP_BACKWARD → 28

Offset 66: PUSH_EXC_INFO         ← Handler entry (not compiled)
Offset 68: LOAD_GLOBAL KeyError
Offset 78: CHECK_EXC_MATCH
Offset 80: POP_JUMP_IF_FALSE → 98
Offset 82: POP_TOP

Offset 84: LOAD_FAST total       ← Except body (to be compiled)
Offset 86: LOAD_CONST 1
Offset 88: BINARY_OP +=
Offset 92: STORE_FAST total
Offset 94: POP_EXCEPT            ← Must handle (no-op for B2)
Offset 96: JUMP_BACKWARD → 28   ← Back to loop
```

## Architecture

### Control Flow (HIR level)

```
                 [try_body_block]
                    BINARY_SUBSCR
                    CheckExc result
                   /            \
            result OK        result NULL
                |                |
         [continue_block]  [exc_match_block]  (new, synthetic)
            BINARY_OP +=       load exc type from global
            STORE_FAST          match = PyErr_GivenExceptionMatches(...)
            JUMP_BACKWARD       /                    \
                            match                 no match
                              |                      |
                        [clear_and_body]          [deopt_block]
                          PyErr_Clear()          standard deopt to
                          → except body           handler offset 66
                          LOAD_FAST total
                          LOAD_CONST 1
                          BINARY_OP +=
                          STORE_FAST total
                          POP_EXCEPT (no-op)
                          JUMP_BACKWARD → 28
```

### Why This Avoids the Refcount Issue

In B1, the problem was: deopt materialises the stack from FrameState, but the items above `handler->depth` would leak because they're not in the truncated FrameState.

In B2, we stay in JIT code. The items above `handler->depth` are in registers. We emit explicit `Decref` (or `XDECREF`) HIR instructions on the exception path for each item we're discarding. No FrameState truncation needed.

### Stack Management on Exception Path

At BINARY_SUBSCR (offset 48), the JIT operand stack might be:
```
Position 0: [iterator]      ← handler depth = 1, this stays
Position 1: [total]         ← pushed for the +=
Position 2: [d[i%1000]]     ← result of subscript (NULL on error)
```

Wait — actually the operand stack in the JIT mirrors the CPython stack. At BINARY_SUBSCR entry, the stack is:
- ... (iterator at depth 0, below our view)
- total (pushed by LOAD_FAST at offset 36)
- d (pushed by LOAD_FAST)
- i%1000 (result of BINARY_OP %)

BINARY_SUBSCR pops d and i%1000, pushes result. So AFTER BINARY_SUBSCR (success):
- stack = [..., total, result]

On failure (NULL), the call to `_PyObject_GetItem` returned NULL. The JIT has already popped the arguments from registers. The result register holds NULL. The stack state IS:
- stack = [..., total]  (d and i%1000 were consumed by the subscr call)

Wait — does the JIT model this correctly? Let me check how `emitBinaryOp` for BINARY_SUBSCR works. The HIR instruction consumes two operands and produces one result. The result is NULL on failure. The operands have already been consumed.

So on exception path, the actual stack state after BINARY_SUBSCR failure is:
- stack = [..., total]  (the result register exists but holds NULL/undefined)

Actually, the HIR models it differently. The HIR instruction `BinaryOp` takes two input registers and writes to an output register. The input registers are NOT consumed from the operand stack — they're just register references. The operand stack manipulation happens at a higher level.

I need to think about this more carefully in terms of the JIT's operand stack model.

### What the Builder Needs to Do

At the point where `emitBinaryOp` (or emitBinarySubscr) is about to emit the error check:

1. Call `findExceptionHandler(current_offset)` to get the exception table entry
2. If found, instead of emitting `CheckExc → deopt`:
   a. Emit conditional branch: if result is NULL, jump to `exc_match_block`
   b. Create `exc_match_block` (a new BasicBlock in the HIR CFG)
   c. In `exc_match_block`:
      - Pop operand stack down to `handler->depth` (emit Decrefs for items above)
      - Load the exception type by scanning handler bytecodes for LOAD_GLOBAL
      - Call `PyErr_GivenExceptionMatches(exc, type)` via runtime helper
      - If no match: deopt to handler offset (standard deopt with truncated stack)
      - If match: call `PyErr_Clear()`, branch to `except_body_block`
   d. Create `except_body_block` starting at the except body bytecodes
      (after POP_TOP, offset 84 in our example)
   e. Handle POP_EXCEPT as no-op
   f. Continue compilation of the except body

### Concrete Changes

| File | Change |
|------|--------|
| builder.cpp | At `emitBinaryOp` (or wherever CheckExc guards are emitted for calls that can fail), add B2 logic |
| builder.cpp | Handle `POP_EXCEPT` as no-op instead of JIT_ABORT (guarded by check that we're in B2-compiled handler) |
| builder.cpp | Scan handler bytecodes to find exception type global |
| jit_rt.cpp or jit_rt.h | Add `JITRT_MatchAndClearException(PyThreadState*, PyObject* type)` helper |

### Open Questions

1. **Where exactly is the CheckExc guard emitted?** Need to find the exact call site in builder.cpp that emits the NULL-return check after BINARY_SUBSCR.

2. **How to handle `POP_EXCEPT`?** Two options:
   - Make it a no-op in the builder (simplest, correct for B2 since we never push exc_info)
   - Don't compile the block containing POP_EXCEPT — skip it and jump directly to JUMP_BACKWARD

3. **How to scan the handler bytecodes for the exception type?** The handler pattern is:
   `PUSH_EXC_INFO, LOAD_GLOBAL <type>, CHECK_EXC_MATCH, POP_JUMP_IF_FALSE, POP_TOP`
   We need to read the LOAD_GLOBAL oparg from the handler bytecodes.

4. **What about guard invalidation?** If the global `KeyError` is reassigned, the JIT code becomes invalid. The JIT already has global-watching infrastructure (`watchGlobal`). We should use it.

## Falsifiers

1. `def f(d,k): try: return d[k]; except KeyError: return -1` — f({}, "x") must return -1, not crash
2. `cinderjit.get_num_deopts()` must NOT increase when KeyError is caught (zero deopts)
3. `def g(d,k): try: return d[k]; except ValueError: return -1` — g({}, "x") must raise KeyError (not match)
4. 172/172 CinderX JIT tests still pass
5. `exceptions` benchmark must improve from 0.91x to ≥0.95x
