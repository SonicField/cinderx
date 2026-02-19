# B2 Open Questions — Resolved Analysis

**Date:** 19 February 2026
**Author:** generalist (research agent)
**Purpose:** Resolve the four open questions from theologian's B2 implementation spec

## Question 1: Where is the CheckExc guard emitted?

**Answer:** There is no `CheckExc` HIR instruction for `BinaryOp`.

The guard chain for `BinaryOp` (which includes `BINARY_SUBSCR`) is:

1. **HIR emission** (builder.cpp:2139): `tc.emit<BinaryOp>(result, op_kind, left, right, tc.frame)` — emits a single `BinaryOp` instruction. `BinaryOp` extends `DeoptBase` (hir.h:558-562), so it carries its own `FrameState`. No separate `CheckExc` is emitted.

2. **LIR lowering** (generator.cpp:1512-1552): The `kBinaryOp` case calls `bbb.appendCallInstruction(bin_op->output(), helpers[op_kind], ...)`. For `kSubscript`, the helper is `PyObject_GetItem` (generator.cpp:1528).

3. **Guard emission** (generator.cpp:3506-3545): After LIR lowering, every `DeoptBase` that's not in the exemption list (lines 3508-3533) gets `emitExceptionCheck(*db, bbb)` (line 3542). `BinaryOp` is NOT exempt — it falls to `default:`.

4. **Guard type** (generator.cpp:456-467): `emitExceptionCheck` checks `out->isA(TCSigned)` to choose between `kNotNegative` and `kNotZero`. For `BinaryOp` returning `PyObject*`, it's `kNotZero` (NULL = exception).

**Implication for B2:** The spec's architecture diagram shows `CheckExc result` as a separate node, but this doesn't exist. The NULL check is embedded in the LIR lowering of `BinaryOp`. B2 must intervene at ONE of two levels:

- **Option A (HIR level):** In `emitBinaryOp` (builder.cpp), after `tc.emit<BinaryOp>(...)`, emit a `CondBranch` on the result being NULL, branching to a synthetic `exc_match_block`. This requires splitting the basic block.

- **Option B (LIR level):** In the `kBinaryOp` case of the LIR generator, replace `emitExceptionCheck` with custom guard logic when the HIR instruction has a B2 annotation.

**Recommendation:** Option A. Working at HIR level is cleaner — the LIR generator doesn't need to understand exception handlers. The builder already has access to `findExceptionHandler()` (Layer 1) and can make the structural decision during HIR construction.

The specific intervention point: after line 2139 in `emitBinaryOp`, before `stack.push(result)` at line 2140.

## Question 2: How to handle POP_EXCEPT?

**Answer:** `POP_EXCEPT` currently has no handler in the builder emit switch — it falls to `default:` → `JIT_ABORT` (builder.cpp:1546). The builder never encounters it because exception handlers are never compiled (they start with `PUSH_EXC_INFO` which also `JIT_ABORT`s at line 1541-1544).

For B2, `POP_EXCEPT` should be a **no-op**.

Rationale: In CPython, `POP_EXCEPT` pops the exception info that `PUSH_EXC_INFO` pushed and restores the previous `exc_info`. In B2, we never execute `PUSH_EXC_INFO` — we stay in JIT code and clear the exception with `PyErr_Clear()`. The thread state's `exc_info` is already clean. `POP_EXCEPT` has nothing to undo.

**Implementation:** Add `case POP_EXCEPT:` to the builder emit switch with an empty body (or a `break;`). Guard it with a flag (e.g., `in_b2_handler_`) to assert it only occurs in B2-compiled handler blocks. Without the flag, an invalid `POP_EXCEPT` in normal code would silently succeed instead of aborting — this is a correctness risk.

**Falsifier:** After implementing B2, run a test where `POP_EXCEPT` appears outside a B2 handler path. The flag check should trigger `JIT_ABORT`. If it doesn't, the guard is incorrect.

## Question 3: How to scan handler bytecodes for the exception type?

**Answer:** The algorithm scans forward from the handler offset, validating the fixed pattern, and extracts the LOAD_GLOBAL name index.

### Algorithm

```
Input: handler_offset (BCOffset, from exception table entry)
Output: (name_idx: int, exception_type: PyObject*) or UNSUPPORTED

1. Construct BytecodeInstruction at handler_offset:
     bc0 = BytecodeInstruction(code_, handler_offset)
   Assert bc0.opcode() == PUSH_EXC_INFO, else return UNSUPPORTED

2. Advance to next instruction:
     bc1 = bc0.nextInstr()
   Assert bc1.opcode() == LOAD_GLOBAL, else return UNSUPPORTED

3. Extract name index:
     name_idx = loadGlobalIndex(bc1.oparg())
   (loadGlobalIndex handles the 3.11+ oparg>>1 transformation, code.cpp:192-197)

4. Advance to next instruction:
     bc2 = bc1.nextInstr()
   Assert bc2.opcode() == CHECK_EXC_MATCH, else return UNSUPPORTED

5. Advance to next instruction:
     bc3 = bc2.nextInstr()
   Assert bc3.opcode() == POP_JUMP_IF_FALSE, else return UNSUPPORTED

6. Advance to next instruction:
     bc4 = bc3.nextInstr()
   Assert bc4.opcode() == POP_TOP, else return UNSUPPORTED

7. Record except_body_offset = bc4.nextInstrOffset()
   This is where the except body starts (offset 84 in the spec example).

8. Resolve the exception type:
     exception_type = preloader_.global(name_idx)
   If exception_type == nullptr, return UNSUPPORTED
   (nullptr means the global isn't cached — either not in globals/builtins dict,
    or globals caching is disabled for this code object)

9. Return (name_idx, exception_type, except_body_offset)
```

### Why this works

**Preloader coverage:** The preloader iterates ALL bytecodes in the code object (preload.cpp:315-316), including handler bytecodes. The `LOAD_GLOBAL KeyError` at handler offset+2 is preloaded into `global_names_` (preload.cpp:356). So `preloader_.global(name_idx)` will resolve it.

**EXTENDED_ARG handling:** `BytecodeInstruction` handles EXTENDED_ARG transparently — `bc.oparg()` returns the full extended oparg. `nextInstr()` skips over EXTENDED_ARGs. So LOAD_GLOBAL with oparg > 255 (requiring EXTENDED_ARG prefixes) is handled correctly.

**Pattern validation:** Each step asserts the expected opcode. If any assertion fails, we return UNSUPPORTED and fall back to the standard deopt path. This guarantees B2 only activates for the exact pattern it handles.

### Edge cases

- **`except (A, B):`** — bc1 would be BUILD_TUPLE, not LOAD_GLOBAL → UNSUPPORTED. Correct.
- **`except:`** (bare) — bc0 is PUSH_EXC_INFO, but bc1 may be POP_TOP (no type check) → UNSUPPORTED. Correct.
- **`except E as e:`** — bc4 would be STORE_FAST (not POP_TOP) → UNSUPPORTED. Correct.
- **Lazy imports** — The preloader already warms up lazy imports for LOAD_GLOBAL (preload.cpp:338-344). If the lazy import has side effects that invalidate globals caching, `canCacheGlobals()` re-check handles it (preload.cpp:351).

### Concrete code sketch

```cpp
// In builder.cpp, as a new private method of HIRBuilder:
struct B2HandlerInfo {
  int name_idx;
  BorrowedRef<> exception_type;
  BCOffset except_body_offset;
};

std::optional<B2HandlerInfo> HIRBuilder::scanB2Handler(BCOffset handler_offset) {
  BytecodeInstruction bc0{code_, handler_offset};
  if (bc0.opcode() != PUSH_EXC_INFO) return std::nullopt;

  auto bc1 = bc0.nextInstr();
  if (bc1.opcode() != LOAD_GLOBAL) return std::nullopt;

  int name_idx = loadGlobalIndex(bc1.oparg());

  auto bc2 = bc1.nextInstr();
  if (bc2.opcode() != CHECK_EXC_MATCH) return std::nullopt;

  auto bc3 = bc2.nextInstr();
  if (bc3.opcode() != POP_JUMP_IF_FALSE) return std::nullopt;

  auto bc4 = bc3.nextInstr();
  if (bc4.opcode() != POP_TOP) return std::nullopt;

  BCOffset except_body_offset = bc4.nextInstrOffset();

  BorrowedRef<> exc_type = preloader_.global(name_idx);
  if (exc_type == nullptr) return std::nullopt;

  // Verify it's actually an exception type
  if (!PyType_Check(exc_type) ||
      !PyType_IsSubtype((PyTypeObject*)exc_type, (PyTypeObject*)PyExc_BaseException)) {
    return std::nullopt;
  }

  return B2HandlerInfo{name_idx, exc_type, except_body_offset};
}
```

## Question 4: Guard invalidation when the global is reassigned

**Answer:** The existing `LoadGlobalCached` + `GuardIs` pattern handles this.

### Mechanism

When `emitLoadGlobal` compiles a LOAD_GLOBAL for a global that's in the cache:

1. `LoadGlobalCached` reads the cached value (preload.cpp:260-268: `getGlobalCache` returns a `PyObject**` pointing into the module's `GlobalCache`)
2. `GuardIs` checks the loaded value matches the expected object. If the global has been reassigned, the guard fails and deopts.

The `GlobalCache` is a watcher on the globals dict — when the dict is mutated, all cached entries for that key are invalidated. This is existing JIT infrastructure (managed by `CacheManager`).

### How B2 should use it

B2 resolves the exception type at compile time via `preloader_.global(name_idx)`. This returns the current value of the global (e.g., `KeyError` type object). B2 should:

1. **Embed the type pointer directly** in the generated code (as an immediate operand to the match-and-clear runtime helper)
2. **Add a `GuardIs` on the exception type global** — this ensures that if someone does `KeyError = SomethingElse`, the JIT code is invalidated via deopt

However, there's a subtlety: the `GuardIs` in `emitLoadGlobal` fires on every call because it loads and checks on the hot path. For B2, we only need invalidation, not per-call checking. Two options:

**Option A (simple):** Emit a `LoadGlobalCached` + `GuardIs` at function entry (or at the top of the try block). This means every call to the function checks that `KeyError` is still `KeyError`. Cost: one pointer comparison per call. This is what the spec should use — it's simple and the overhead is negligible compared to the exception-handling savings.

**Option B (zero overhead):** Use the `GlobalCache` pointer directly. If the cache is invalidated (global reassigned), the `GlobalCache` entry becomes NULL. The runtime helper can check this. But this requires threading the `GlobalCache` pointer through to the generated code, which is more complex.

**Recommendation:** Option A. The `LoadGlobalCached` + `GuardIs` pattern is already proven and well-tested. The overhead of a single pointer comparison is ~1ns, which is negligible compared to the 18ns deopt savings.

Actually, on reflection: B2 doesn't need a separate `GuardIs` at all. The match-and-clear helper can check at exception time. If `KeyError` has been reassigned, the match may give wrong results, but this only matters on the exception path (already slow). The real question is: do we care about correctness when `KeyError` is reassigned?

Yes, we do — if someone monkey-patches `KeyError = ValueError`, our inline check must still work correctly. So we need invalidation.

**Revised recommendation:** Use `LoadGlobalCached` + `GuardIs` for the exception type at function entry. This is ~3 lines of code, uses existing infrastructure, and guarantees correctness even under global mutation.

**Falsifier:** Reassign `KeyError = ValueError` in globals, then call the function with a `KeyError`-raising expression. Without the guard, B2 would match the old `KeyError` type and incorrectly catch `ValueError`. With the guard, the JIT code deopts and the interpreter handles it correctly.

## Summary of Architectural Decisions

| Question | Answer | Key finding |
|----------|--------|-------------|
| Q1: Where is CheckExc? | No CheckExc for BinaryOp. Guard is in LIR generator. | Intervene at HIR level (builder.cpp:2139), not LIR. |
| Q2: POP_EXCEPT handling | Make it a no-op in the builder emit switch | Guard with `in_b2_handler_` flag |
| Q3: Handler scanning | Sequential pattern match starting at handler offset | Preloader already caches handler LOAD_GLOBAL |
| Q4: Guard invalidation | LoadGlobalCached + GuardIs at function entry | Existing infrastructure, ~1ns overhead |

## Architectural Correction to B2 Spec

The spec's "no match" deopt path (line 64-65) says "standard deopt to handler offset 66". This is **incorrect** — as documented in the B1 analysis, deopting to the handler offset with a truncated stack causes refcount leaks.

The correct "no match" path should deopt using the **ORIGINAL `BinaryOp`'s own FrameState and DeoptMetadata**. This means:

1. **DeoptReason:** `kUnhandledException` (the default for `BinaryOp`, see deopt.cpp:433-434)
2. **Resume offset:** `nextInstrOffset()` of BINARY_SUBSCR (deopt.cpp:244 — `kUnhandledException` is not `kGuardFailure`/`kRaise`, so it uses nextInstr)
3. **Error handler entry:** `shouldResumeInterpreterInErrorHandler` returns `true` (deopt.cpp:305)
4. **Stack state:** FrameState has left/right already popped (builder.cpp:2071-2072), which is correct — `exception_unwind` adjusts the stack to handler depth anyway

The interpreter receives `err_occurred=true`, jumps to `exception_unwind`, walks `co_exceptiontable`, and dispatches to the handler. The cost is one `co_exceptiontable` walk, but this only occurs on the no-match path (which is already rare — most caught exceptions match their handler type).

**Implementation:** On the no-match path, simply jump to the standard deopt trampoline for the `BinaryOp` instruction. No new deopt metadata is needed — reuse the one that would have been generated anyway. The B2 optimisation replaces the MATCH path, not the NO-MATCH path.

## Source Locations Referenced

### B2 Implementation Infrastructure

**Runtime helper** (`JITRT_MatchAndClearException`):
```cpp
// jit_rt.h / jit_rt.cpp — ~6 lines
int JITRT_MatchAndClearException(PyObject* exc_type) {
    if (PyErr_ExceptionMatches(exc_type)) {
        PyErr_Clear();
        return 1;  // matched, exception cleared
    }
    return 0;  // no match, exception still set (for deopt)
}
```

**Block allocation for B2:** The builder doesn't store `irfunc` as a member. B2 needs to allocate synthetic blocks (`exc_match_block`, `except_body_block`). Solution: add `Function* irfunc_{nullptr}` to `builder.h` (line ~549), set it at the top of `buildHIRImpl` (line 621). Then `emitBinaryOp` can call `irfunc_->cfg.AllocateBlock()`.

**CondBranch usage pattern** (from builder.cpp:2776):
```cpp
tc.emit<CondBranch>(result, continue_block, exc_match_block);
```
Where `result` is the BinaryOp output — nonzero (success) → continue_block, zero/NULL (error) → exc_match_block.

**Important:** `CondBranch` is a terminator. After emitting it, the current basic block is closed. The builder must switch to a new TranslationContext for each successor block.

## Source Locations Referenced

| File | Lines | Content |
|------|-------|---------|
| builder.cpp | 2067-2141 | `emitBinaryOp` — HIR emission, B2 intervention point at 2139 |
| builder.cpp | 1537-1544 | `JIT_ABORT` for `CHECK_EXC_MATCH`, `PUSH_EXC_INFO` |
| builder.cpp | 1546 | `default:` → `JIT_ABORT` (catches unhandled `POP_EXCEPT`) |
| builder.cpp | 3563-3602 | `emitLoadGlobal` — pattern for `LoadGlobalCached` + `GuardIs` |
| generator.cpp | 1512-1552 | LIR lowering of `kBinaryOp` |
| generator.cpp | 3506-3545 | Guard emission for `DeoptBase` instructions |
| generator.cpp | 456-467 | `emitExceptionCheck` — NULL/negative check |
| preload.cpp | 274-280 | `Preloader::global()` — global resolution |
| preload.cpp | 315-358 | Preloader LOAD_GLOBAL iteration — covers handler bytecodes |
| code.cpp | 192-197 | `loadGlobalIndex` — oparg>>1 for 3.11+ |
| bytecode.h | 22-88 | `BytecodeInstruction` — constructor takes `(code, BCOffset)` |
| bytecode.h | 95-102 | `BytecodeInstructionBlock` — range iteration with `BCIndex` |
| hir.h | 557-586 | `BinaryOp` class — extends `DeoptBase`, carries `FrameState` |
| hir.h | 1251-1258 | `CheckExc` class — NOT used for `BinaryOp` |
| deopt.cpp | 403-437 | `getDeoptReason` — `BinaryOp` falls to `default` → `kUnhandledException` |
| deopt.cpp | 229-246 | `getDeoptResumeIndex` — `kUnhandledException` resumes at next instruction |
| deopt.cpp | 299-312 | `shouldResumeInterpreterInErrorHandler` — `kUnhandledException` → `true` |
| deopt.cpp | 439-532 | `DeoptMetadata::fromInstr` — `cause_instr_idx` from FrameState's `cur_instr_offs` |
| gen_asm.cpp | 234-261 | `resumeInInterpreter` — skips switch when `PyErr_Occurred()` is true |
| bytecode.cpp | 222-232 | `BytecodeInstructionBlock` constructor — single-arg covers entire code object |
