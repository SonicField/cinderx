# CinderX JIT Exception Handling — Design for co_exceptiontable Support

**Date:** 19 February 2026
**Author:** @theologian
**Status:** Design revised after code review. Scope larger than initially estimated.

## Problem

JIT-compiled functions that use `try/except` deopt to the interpreter on every exception. The `exceptions` benchmark (50% KeyError rate in a hot loop) shows 0.91x — the JIT is 9% slower than vanilla CPython because every exception triggers:

1. kNotZero guard fires (NULL return from dict lookup)
2. Deopt to interpreter
3. Interpreter uses `co_exceptiontable` to find except clause
4. Interpreter executes except clause
5. Re-enter JIT on next iteration

CPython's interpreter handles the same exception inline (~10 instructions: push exc_info, match type, jump). The deopt round-trip costs ~100+ instructions.

## Root Cause

CinderX has **two Python compilers**, and they produce different bytecode for `try/except`:

### CinderX compiler (pycodegen.py)

Emits synthetic `SETUP_FINALLY` opcodes (opcode 256, defined in `cinder_opcode_ids.h:256`). The HIR builder partially handles these:

1. `emitSetupFinally()` (builder.cpp:4271) pushes an `ExecutionBlock{SETUP_FINALLY, handler_off, stack_level}` onto `block_stack`
2. This is metadata only — no HIR instructions are emitted
3. **CRITICAL:** The exception handler blocks are never compiled. `PUSH_EXC_INFO`, `CHECK_EXC_MATCH`, `POP_EXCEPT`, `RERAISE` all trigger `JIT_ABORT` (builder.cpp:1544-1549)
4. Exception handler blocks are unreachable in the HIR because the only path to them is via exception dispatch, which currently deopts

### CPython's compiler (standard Python 3.12)

Does NOT emit `SETUP_FINALLY`. Instead uses `co_exceptiontable` — a compact binary table in the code object that maps bytecode ranges to handler offsets:

```
ExceptionTable:
  4 to 10 -> 14 [0]      # bytecodes 4-10 handled by offset 14, stack depth 0
  14 to 30 -> 38 [1]     # bytecodes 14-30 handled by offset 38, stack depth 1
```

The JIT has **zero references** to `co_exceptiontable` anywhere in `cinderx/Jit/`. Confirmed by:
```
grep -rn 'co_exceptiontable' cinderx/Jit/ → 0 matches
```

### Consequence

**Neither CinderX-compiled nor CPython-compiled functions get native exception handling in the JIT.** CinderX-compiled code gets the SETUP_FINALLY metadata (block_stack entry), but the handler blocks are never compiled — they're treated as unreachable. CPython-compiled code doesn't even get the metadata.

The JIT_ABORT on PUSH_EXC_INFO/CHECK_EXC_MATCH is a defensive assertion: "these opcodes should only appear in exception handlers, which we never reach". It's correct, because exception dispatch always deopts.

Confirmed by generalist's x86 analysis: x86 JIT has the identical limitation. This is a feature gap, not an aarch64-specific bug.

## Revised Fix Design — Three Layers

### Layer 1: Parse co_exceptiontable and insert synthetic SETUP_FINALLY

**Location:** `BytecodeInstructionBlock` constructor (bytecode.cpp:223) or a new preprocessing step.

**Mechanism:** Parse `co_exceptiontable` and insert synthetic `SETUP_FINALLY` at the start of each exception-covered bytecode range. This gives the builder the metadata it needs.

Python 3.12 exception table format:
- Variable-length encoded entries
- Each entry: `(start, length, target, depth, lasti_flag)`
- `start`: first bytecode offset covered
- `length`: number of bytecodes covered
- `target`: handler offset (PUSH_EXC_INFO bytecode)
- `depth`: stack depth at handler entry
- `lasti_flag`: whether to push `lasti` before handler

CPython provides `_PyCode_GetExceptionTable()` or we parse raw bytes using the same algorithm as `_PyCode_GetExceptionTableEntry()` in `Python/ceval.c`.

**Effort:** ~50 lines.

### Layer 2: Compile exception handler blocks

Currently, builder.cpp:1544-1549 aborts on exception-handler opcodes:

```cpp
case CHECK_EG_MATCH:
case CHECK_EXC_MATCH:
case CLEANUP_THROW:
case PUSH_EXC_INFO:
  JIT_ABORT("Opcode {} ({}) should only appear in exception handlers",
            opcode, opcodeName(opcode));
```

We need to implement these opcodes instead of aborting:

#### PUSH_EXC_INFO (handler entry)
- The exception is on the Python stack (pushed by the runtime exception dispatch)
- Need to: save current `tstate->exc_info`, push exception onto exc_info chain
- HIR equivalent: emit an instruction that reads the current exception from `tstate->current_exception` and pushes it + saves previous exc_info

#### CHECK_EXC_MATCH
- Pops exception type from stack, peeks at the pending exception
- Returns True/False for whether the exception matches the type
- Used by the subsequent `POP_JUMP_IF_FALSE` to decide except vs reraise
- HIR equivalent: emit a `CheckExcMatch` instruction that calls `PyErr_GivenExceptionMatches()`

#### POP_EXCEPT
- Restores previous `tstate->exc_info` from the saved one
- HIR equivalent: emit instruction that pops the exc_info chain

#### RERAISE
- Re-raises the current exception (with traceback)
- If inside a try/except, the containing handler catches it
- If no containing handler, deopt to interpreter
- HIR equivalent: emit a `Raise` instruction or branch to the containing exception handler

**Effort:** ~100 lines across 4 opcode handlers.

### Layer 3: Connect exception dispatch

Currently, when a C API call (e.g., `PyObject_GetItem` for dict lookup) returns NULL, the JIT emits a `CheckExc` guard that deopts on failure. The deopt reconstructs the Python frame and hands control to the interpreter.

We need to change this so that when a `CheckExc` guard fails **inside a try/except block** (i.e., when `block_stack` has a `SETUP_FINALLY` entry), it branches to the exception handler block instead of deopting.

**Mechanism:**
- In `emitCheckExc()` or equivalent, check if `block_stack` has a SETUP_FINALLY entry
- If yes: emit a conditional branch to the handler block on exception
- If no: emit the existing deopt path

The handler block entry needs to:
1. Clear the "exception pending" state from `tstate`
2. Push the exception object onto the JIT operand stack
3. Execute PUSH_EXC_INFO
4. Continue with CHECK_EXC_MATCH / POP_JUMP_IF_FALSE / etc.

**Effort:** ~30 lines for the dispatch change, but the interaction with stack depth is subtle.

### Key Risk: Stack Depth Invariant

The builder comment at line 556 warns:
> "The correctness of the translation depends on the invariant that the depth of the operand stack is constant at each program point. All of the CPython bytecode that we currently support maintain this invariant. However, there are a few bytecodes that do not (e.g. SETUP_FINALLY)."

Exception handlers break this invariant: the handler entry has a different stack depth than the normal path (exception value is pushed). The builder's abstract interpretation tracks stack depth; encountering a block with inconsistent entry depths causes assertion failures.

**Mitigation:** The `ExecutionBlock` records `stack_level`. At handler entry, unwind the stack to `stack_level` and push the exception. This is what CPython does. The builder would need special handling for the first instruction in an exception handler block.

### Alternative: Simpler Deopt-Avoidance (not full native exception handling)

If the full three-layer approach is too complex, a simpler optimisation:

**Inline exception check + match:** Instead of emitting CheckExc → deopt, emit:
1. Check if exception is pending (NULL return)
2. If yes: check if exception matches the expected type (e.g., KeyError)
3. If match: clear exception, jump to the "except" code path (still in JIT)
4. If no match: deopt (reraise)

This avoids the full PUSH_EXC_INFO / POP_EXCEPT machinery. It only works for simple `try: X; except SomeType: Y` patterns, not for nested handlers, finally blocks, or bare `except:`.

**Advantage:** Much simpler. Maybe 50-80 lines total.
**Disadvantage:** Only works for the simplest case. Doesn't generalise.
**Relevance:** The `exceptions` benchmark IS the simplest case (`try: d[i]; except KeyError: total += 1`).

## Falsifiers

1. **HIR dump test:** Compile `def f(d,k): try: return d[k]; except KeyError: return -1` → HIR must show exception handler basic block (not just happy path)
2. **No deopt on exception:** The function should NOT deopt when KeyError is raised. Verify by checking `cinderjit.get_num_deopts()` before and after.
3. **Correctness:** `f({}, 'missing')` returns `-1`, not crash
4. **Correctness gate:** 38/41 CinderX, 8/8 PyTorch smoke
5. **Performance:** `exceptions` benchmark should improve from 0.91x to >0.95x
6. **Negative test:** Non-matching exceptions (`try: d[k]; except ValueError:`) must still propagate correctly

## Implementation Order

1. Decide: full three-layer approach or simpler deopt-avoidance?
2. If full approach:
   a. Write co_exceptiontable parser (standalone, testable)
   b. Insert synthetic SETUP_FINALLY
   c. Implement PUSH_EXC_INFO, CHECK_EXC_MATCH, POP_EXCEPT, RERAISE in builder
   d. Change CheckExc dispatch from deopt to handler branch
   e. Verify HIR dump
   f. Run minimal test case
   g. Run CinderX 38/41 gate
   h. Run exceptions benchmark
3. If simpler approach:
   a. Identify the CheckExc guard for BINARY_SUBSCR
   b. Add inline exception match check
   c. Emit branch to "except" code path on match
   d. Verify with test case
   e. Run CinderX gate
   f. Run benchmark

## Files Modified

| File | Change | Layer |
|------|--------|-------|
| `bytecode.cpp` | Parse co_exceptiontable, insert synthetic SETUP_FINALLY | 1 |
| `bytecode.h` | Add method for exception table parsing | 1 |
| `builder.cpp` | Implement PUSH_EXC_INFO, CHECK_EXC_MATCH, POP_EXCEPT, RERAISE | 2 |
| `builder.cpp` or relevant emit function | Change CheckExc dispatch from deopt to handler branch | 3 |

## Open Questions

1. **Does the builder's existing SETUP_FINALLY handling work for nested try/except?** CinderX compiler generates nested SETUP_FINALLY for nested try blocks — need to verify the block_stack handles this correctly.

2. **What about `finally` blocks?** Python 3.12 also uses co_exceptiontable for finally. The handler entry pushes the exception but continues execution without matching. Finally blocks are more complex because they execute whether or not an exception occurred.

3. **The `lasti` flag** in the exception table — does the builder need to handle this? It controls whether the last instruction offset is pushed onto the stack before the handler, used for restoring position after finally blocks.

4. **Should we do the full approach or the simpler one?** The simpler approach only fixes the `exceptions` benchmark (the simplest try/except pattern). The full approach fixes all try/except patterns. Alex should decide.
