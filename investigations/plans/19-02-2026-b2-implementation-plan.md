# B2 Implementation Plan — Inline Exception Match in JIT

**Date:** 19 February 2026
**Author:** claude
**Status:** Implementation plan

## Overview

Implement B2: inline exception matching for `try/except SomeType` patterns in the JIT.
When a `BinaryOp(kSubscript)` occurs inside a try block, instead of deopting on error,
we check the exception type inline and branch to the except body if it matches.

## Approach

**Key insight**: `BinaryOp` is a `DeoptBase` — the LIR generator automatically emits
a deopt guard. To avoid this, when inside a try block with a simple handler pattern,
we replace `BinaryOp` with `CallStatic` (not a DeoptBase) + `CondBranch`.

### Changes

#### 1. jit_rt.h / jit_rt.cpp — Runtime helper

Add `JITRT_MatchAndClearException(PyObject* exc_type)`:
- Fetches current exception via `PyErr_GetRaisedException()` (3.12+)
- Calls `PyErr_GivenExceptionMatches(exc, exc_type)`
- If match: `Py_DECREF(exc)`, return 1
- If no match: `PyErr_SetRaisedException(exc)` (restore it), return 0
- Returns `int` (1 = matched, 0 = no match)

#### 2. builder.h — Declaration

Add method `bool tryEmitInlineExceptionHandler(CFG&, TranslationContext&, const BytecodeInstruction&, BinaryOpKind, Register*, Register*, Register*)`.

#### 3. builder.cpp — B2 logic in emitBinaryOp

In `emitBinaryOp`, after determining `op_kind`, before the final `tc.emit<BinaryOp>(...)`:

```
if (op_kind == BinaryOpKind::kSubscript) {
  BCOffset cur_off = bc_instr.baseOffset();
  auto* handler = findExceptionHandler(cur_off);
  if (handler && isSimpleExceptPattern(handler)) {
    // B2 path: inline exception match
    emitInlineExceptionMatch(cfg, tc, bc_instr, handler, left, right, result);
    stack.push(result);
    return;
  }
}
// Fall through to normal BinaryOp emission
```

`isSimpleExceptPattern` scans the handler bytecodes for the pattern:
`PUSH_EXC_INFO, LOAD_GLOBAL <type>, CHECK_EXC_MATCH, POP_JUMP_IF_FALSE, POP_TOP`

`emitInlineExceptionMatch`:
1. Emit `CallStatic` to `PyObject_GetItem(left, right)` → result
2. Create 3 blocks: ok_block, exc_match_block, deopt_block
3. Emit `CondBranch(result, ok_block, exc_match_block)` — non-null is true
4. In exc_match_block:
   a. Pop stack down to handler depth (emit Decref for items above)
   b. Load exception type from global (resolved at JIT compile time)
   c. Emit `CallStatic` to `JITRT_MatchAndClearException(exc_type)`
   d. Emit `CondBranch(match_result, except_body_block, deopt_block)`
5. In deopt_block:
   a. Set `cur_instr_offs` to handler->target (the handler entry point)
   b. Emit `Snapshot` + `Deopt` (reason = kUnhandledException)
6. In ok_block: emit `RefineType(result, TObject, result)`, continue normally
7. The except body: jump to the existing handler basic block at handler->target + skip_pattern

Wait — this last part is wrong. We can't just jump to an existing block because the
except body starts AFTER the PUSH_EXC_INFO/LOAD_GLOBAL/CHECK_EXC_MATCH/POP_JUMP_IF_FALSE/POP_TOP
pattern. We need to compile the except body ourselves.

Actually — the except body at offset 84 (in the bench_exceptions example) IS already a
block boundary (Layer 1 added handler->target as a block start, and the bytecodes after
POP_TOP are also reachable via normal translation). The problem is that the handler
block starts at offset 66 (PUSH_EXC_INFO), and we need to skip to offset 84.

Better approach: At JIT compile time, scan the handler to find:
- The except body start offset (after POP_TOP)
- The exception type global name

Then the B2 match path branches directly to `getBlockAtOff(except_body_offset)`.

But wait — `getBlockAtOff` only works for blocks that exist in block_map_. Layer 1 added
handler->target as a block start (offset 66), but the except body (offset 84) may NOT be
a block start.

Solution: In `isSimpleExceptPattern`, also compute `except_body_offset` and add it to
block_starts during createBlocks(). OR: compute it at emit time and add the block then.

Actually, looking again at the bytecodes:
- Offset 82: POP_TOP
- Offset 84: LOAD_FAST total  ← except body starts here

Offset 84 might already be a block start if there are branches targeting it. But it might
not be. I need to ensure it's a block start.

Simplest approach: During `parseExceptionTable` / `createBlocks`, for each handler entry
that matches the simple pattern, also add the except-body-start offset as a block start.

## Implementation Order

1. Add `JITRT_MatchAndClearException` to jit_rt.h/jit_rt.cpp
2. Add `isSimpleExceptPattern` + `except_body_offset` computation
3. Modify `createBlocks` to add except_body_offset as block starts for simple handlers
4. Modify `emitBinaryOp` with B2 path
5. Handle POP_EXCEPT as no-op
6. Build and test

## Falsifiers

1. `f({}, "x")` returns -1, not crash (basic exception catch works)
2. `cinderjit.get_num_deopts()` = 0 when KeyError is caught
3. `g({}, "x")` raises KeyError when handler catches ValueError (no-match deopts correctly)
4. 172/172 CinderX JIT tests pass
5. `exceptions` benchmark improves from 0.91x towards 1.0x
