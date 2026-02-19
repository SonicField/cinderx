# B1 Stack Depth Adjustment — Analysis and Draft

**Date:** 19 February 2026
**Author:** generalist (research agent)
**Task:** Pre-investigate B1 stack depth issue for Approach B

## 1. The Problem

Approach B1 proposes changing the deopt offset from the current instruction (e.g., BINARY_SUBSCR at offset 108) to the exception handler offset (e.g., PUSH_EXC_INFO at offset 136). This skips the `co_exceptiontable` walk in the interpreter.

**However**, the deopt materialiser (`reifyStack` at deopt.cpp:154-189) writes the FrameState snapshot's stack contents onto the interpreter frame. The stack depth at the deopt point differs from what the handler expects.

### Concrete Example (bench_exceptions)

At BINARY_SUBSCR (offset 108), the FrameState stack might contain:
```
[total, d, i_mod_1000, result_of_subscr]  → depth 4
```

The exception table entry for offsets 96-116 says:
```
handler = 136, depth = 1, lasti = 0
```

Meaning at handler entry (PUSH_EXC_INFO at offset 136), the interpreter expects:
```
[iterator]  → depth 1
```

If we deopt with the stack at depth 4 but `cause_instr_idx` pointing to offset 136, the interpreter will see 4 items on the stack where it expects 1. PUSH_EXC_INFO will push the exception onto position 5, and subsequent code will reference wrong stack positions.

## 2. What CPython Does (exception_unwind)

When the interpreter hits an error and finds a handler via `get_exception_handler`, it:

1. **Pops the stack down to `level`**: Decrefs and removes all items above the expected depth
2. **Optionally pushes `lasti`**: If `lasti` flag is set, pushes the instruction offset
3. **Executes PUSH_EXC_INFO**: Pushes the current `exc_info` and the new exception onto the stack
4. **Sets `instr_ptr`** to the handler offset

The stack pop from actual depth to `level` is the critical step B1 must replicate.

## 3. Where B1 Must Intervene

The intervention point is in `reifyStack` (deopt.cpp:154-189) or in a wrapper around it. When the deopt reason is `kUnhandledException` AND we've changed `cause_instr_idx` to a handler offset, we need to:

1. Truncate `frame_meta.stack` to `level` items (the exception table's depth value)
2. Properly decref the items being discarded (they're owned references)
3. Optionally push `lasti` if the exception table entry has `lasti=1`

## 4. Two Implementation Approaches

### 4A: Modify FrameState at CheckExc emission time (~30 lines in generator.cpp)

When emitting the CheckExc guard in `emitExceptionCheck`, if we know the handler offset and expected depth:

```cpp
// In generator.cpp, where CheckExc guard is emitted:
if (has_exception_handler) {
  // Create a modified DeoptMetadata that:
  // 1. Sets cause_instr_idx to handler_offset
  // 2. Truncates stack to exception_depth items
  // 3. Sets reason to kUnhandledException
  auto modified_frame = i.frameState()->copy();
  modified_frame.stack.resize(exception_depth);  // Truncate
  modified_frame.cause_instr_idx = handler_offset;
  appendGuard(bbb, kind, modified_deopt, bbb.getDefInstr(out));
}
```

**Problem**: The DeoptMetadata is constructed AFTER LIR generation, during register allocation. We can't modify it at LIR emission time — we can only set the HIR-level FrameState, which is later consumed by the DeoptMetadata builder.

### 4B: Modify FrameState at HIR level (~20 lines in builder.cpp)

The cleaner approach: create a modified FrameState for CheckExc instructions that are inside a try block. At HIR construction time, when we emit `CheckExc`:

```cpp
// In builder.cpp, where CheckExc is emitted after a potentially-failing call:
if (auto* handler = findExceptionHandler(current_bc_offset)) {
  // Create a copy of the current frame state
  auto handler_frame = tc.frame.copy();
  // Truncate stack to the handler's expected depth
  while (handler_frame.stack.size() > handler->depth) {
    handler_frame.stack.pop();
  }
  // Set the instruction offset to the handler entry
  handler_frame.next_instr_offset = handler->target;
  // Emit CheckExc with the modified frame state
  emit<CheckExc>(out, out, handler_frame);
}
```

**Problem**: This requires `CheckExc` to carry a different FrameState than the surrounding code. Currently, the FrameState is shared by all instructions in the same basic block up to that point. Creating per-instruction FrameStates would require changes to how FrameState is managed.

Actually, each DeoptBase instruction already carries its own FrameState pointer (`frameState()` method). So this IS possible — we just need to create a new FrameState for the CheckExc and have it own a modified copy.

### 4C: Modify at deopt time (~15 lines in deopt.cpp)

The simplest approach: at deopt materialisation time, check if we're deopting to a handler offset, and if so, truncate the stack.

```cpp
// In reifyStack (deopt.cpp:154):
static void reifyStack(...) {
  int stack_size = frame_meta.stack.size();

  // If deopting to an exception handler, truncate stack to handler depth
  if (meta.reason == DeoptReason::kUnhandledException) {
    BorrowedRef<PyCodeObject> code = frameCode(frame);
    BCIndex cause_idx = frame_meta.cause_instr_idx;
    int level, handler, lasti;
    if (get_exception_handler(code, cause_idx.value(), &level, &handler, &lasti)) {
      // Decref items above the handler's expected depth
      MemoryView mem{regs};
      for (int i = level; i < stack_size; i++) {
        const auto& value = meta.getStackValue(i, frame_meta);
        Ref<>::steal(mem.readBorrowed(value));  // Decref
      }
      stack_size = level;
    }
  }

  // Use stack_size instead of frame_meta.stack.size() for the rest
  ...
}
```

**Problem**: This approach means we're STILL doing the `get_exception_handler` walk at deopt time, which is one of the costs B1 was supposed to avoid. However, we avoid the full interpreter re-entry overhead (frame linking, instruction dispatch, etc.).

## 5. Recommendation

**Approach 4B (HIR-level FrameState modification)** is the cleanest:

1. At HIR construction, when emitting `CheckExc` inside a try block (detected via Layer 1's `findExceptionHandler`), create a modified FrameState with:
   - Stack truncated to `handler->depth`
   - `cause_instr_idx` set to `handler->target` (the handler offset)

2. Set the DeoptBase's reason to `kUnhandledException` so `shouldResumeInterpreterInErrorHandler` returns `true` (the interpreter enters the error handler path directly).

3. The interpreter then executes from the handler offset with the correct stack depth. It will run `PUSH_EXC_INFO` which pushes the exception onto the stack, then `CHECK_EXC_MATCH` to verify the exception type, then branch to the except body.

**Key invariant**: The stack items being discarded (those above `handler->depth`) must NOT be in registers that the deopt materialiser tries to write. The FrameState truncation handles this because the deopt materialiser only writes items in the FrameState's stack vector.

**What about decref?** The discarded stack items are owned references. If they're in the FrameState but not written to the frame, they will LEAK. We need to either:
- Still include them in the DeoptMetadata's `live_values` with `RefKind::kOwned` so `releaseRefs()` decrefs them, OR
- Emit explicit Decref instructions before the CheckExc for the items that would be popped

The first option is cleaner — the items are still live in registers, and `releaseRefs()` (deopt.cpp:387+) will decref them after `reifyStack`.

Actually, wait. `releaseRefs` releases ALL live values, and `reifyStack` also takes ownership via `readOwned`. There's a double-decref risk. Let me re-examine.

Looking at `reifyStack` (line 174): `Ref<> obj = mem.readOwned(value)` — this reads and takes ownership. Then `obj.release()` transfers into the frame. So `reifyStack` claims ownership of stack items, and `releaseRefs` claims ownership of OTHER live values (locals, temps). They shouldn't overlap.

For B1 with truncated stack: the items above `handler->depth` are NOT in the truncated FrameState stack. But they ARE still live in registers. If they're not in the DeoptMetadata at all, they LEAK. We need a mechanism to include them as "values to decref but not write to frame".

**This is the core complication of B1.** The FrameState serves dual purposes: it defines what to write to the interpreter frame AND what live values need refcount management. Truncating the stack for the frame breaks the refcount management.

## 6. Revised Recommendation

Given the refcount complication, **B1 is NOT as simple as "change the deopt offset"**. The cleanest path is:

1. **Approach 4B** for the FrameState modification
2. **Emit explicit Decref instructions** in the HIR for the stack items above `handler->depth` before the CheckExc guard
3. The Decrefs execute on the guard-failure path (not the normal path)

Wait — Decrefs before CheckExc would execute on ALL paths, not just the exception path. That's wrong.

Alternative: Create a new basic block for the guard-failure path that:
1. Decrefs the extra stack items
2. Then deopts with the truncated FrameState

This is starting to look like B2 (inline match in JIT) rather than B1.

## 7. Final Assessment

**B1 is more complex than the initial estimate of 10 lines.** The stack depth adjustment requires either:
- A mechanism to decref owned registers not in the deopt FrameState (new infrastructure), OR
- Explicit Decref emission on the exception path (requires control flow changes), OR
- A separate code path in `reifyStack` that handles the truncation and decrefs (approach 4C, ~15 lines, but doesn't save the `co_exceptiontable` walk)

**Approach 4C is the pragmatic choice**: it's the smallest correct change. We accept that we still do the `co_exceptiontable` walk in `reifyStack`, but we save the interpreter loop re-entry overhead. The saving is smaller than hoped but still positive.

**Alternatively, skip B1 entirely and go to B2**: inline the exception check+match in JIT code, which avoids the deopt entirely and sidesteps all refcount issues. B2 is more code (~60 lines) but doesn't have the refcount complication.

## 8. Falsifiers

- **"Stack items above handler->depth leak without explicit decref"** — Falsifiable by running the exceptions benchmark under AddressSanitizer/refcount tracking. If items leak, ASAN will report. If they don't leak, there's a mechanism I've missed.
- **"reifyStack and releaseRefs don't overlap"** — Falsifiable by tracing both functions and checking if any LiveValue is processed by both.
- **"B1 saves less than 5ns if 4C approach used"** — Falsifiable by measuring with a prototype. If the saving is <2ns, B1 isn't worth it.
