# Failed and Reverted Optimisations

Failures are where the learning is. Every revert taught something about the JIT's architecture that the successful commits did not.

---

## ARM64 Branch

### Option D: LIR Inline LOAD_ATTR Fast Path

**Commits:** `3c4ff942`, `d2bbb9f5`, `8af4dc49` (revert)

**What it tried:** Inline the type check + slot access directly into LIR-generated machine code, eliminating the C function call to `LoadAttrCache::invoke()` entirely. The generated code would check `ob_type == expected_type`, then load the slot value directly via a computed offset.

**Initial result:** slot_read 0.80x → 0.96x (+16pp). The most promising attribute access optimisation attempted.

**Why it failed:** The LIR inline fast path created a diamond CFG with two virtual registers for the same HIR output. The incref block wrote `%31 = Move slot_value`. The call block wrote `%33 = Call invoke(...)`. Since `%33` was never read by anything downstream (the Phi at the merge point used `%31`), the register allocator eliminated it. On ARM64, no `mov x19, x0` was emitted after the call, so x19 retained its stale value — the function pointer itself, not the attribute value.

**Symptom:** `self.x` returned `<function get_x>` instead of `42`. Silent data corruption.

**Architectural lesson:** LIR diamond CFGs must use the prior-art pattern from `kIsNegativeAndErrOccurred` (generator.cpp:1174-1208): initialise the output register BEFORE the branch, then modify in each path. The two-register approach violates SSA constraints that the register allocator relies on.

---

### GenDataFooter frame_header Initialisation

**Commits:** `5b3cf6b3`, `d8a1e059` (revert)

**What it tried:** Initialise `frame_header` in `GenDataFooter` during generator allocation, enabling frame walking for JIT generators (tracebacks, profilers).

**Why it failed:** The initialisation was premature — exception paths and async generators had assumptions about `frame_header` being uninitialised until resume. The exact failure mode was not documented beyond "breaks async generators."

**Architectural lesson:** Generator frame state has ordering dependencies with exception handling and async protocols. Frame initialisation must happen at resume time, not allocation time.

---

### LICM FrameState Bug

**Commits:** `e6d83dea` (LICM pass), `f44f531d` (fix)

Not strictly reverted, but the pass was initially broken in a way that produced crashes.

**What went wrong:** LICM hoisted `GuardType` based on explicit operands being loop-invariant. But `GuardType` inherits from `DeoptBase`, which carries a `FrameState` containing `live_regs` — a list of registers needed to reconstruct the interpreter frame on deopt. Some of those registers were defined inside the loop body.

When the hoisted guard fired in the loop preheader, it tried to materialise values from registers that had not yet been defined (the loop body had not executed yet).

**Fix:** `allUsesOutsideLoop` now checks ALL register references via `visitUses`, including FrameState `live_regs`.

**Architectural lesson:** Any instruction inheriting from `DeoptBase` has hidden dependencies through its FrameState. Moving such instructions requires checking not just the explicit operands but also the implicit FrameState references.

---

## Speculation-Experiment Branch

### Speculative Expansion (All 5 Approaches)

**Commits:** 17 commits, all eventually removed in `5a5b50e0`

**What it tried:** Replace `GuardType` (binary: fast path or deopt) with multi-path type dispatch chains (Compare Is + CondBranch per type, Phi merge, C-API slow path for unrecognised types). Five approaches:

1. **Simplify pass expansion** — peephole in `simplifyGuardType`
2. **C-API slow path** — replace Deopt with `CallStatic(PyObject_GetAttr)`
3. **Builder-level dispatch** — emit speculative CFG in `builder.cpp`
4. **Standalone pass** — dedicated `SpeculativeExpansion` pass with value-chain grouping
5. **Deopt-aware selective expansion** — query `DeoptStats` on Tier 2 recompilation

**Why it failed:** The optimisation gap did not exist. CinderX already handles polymorphic dispatch through three mechanisms:
- **Subclass graph optimisation:** The builder skips exact-type guards for types with known subclasses
- **LoadAttrCached:** Handles attribute access on mismatched types without deopting through GuardType
- **PIC (Polymorphic Inline Cache):** Replaces single-type guards with dispatch chains at call sites

GuardType rarely deopts in practice. All benchmark gains at n=3 ABBA collapsed to noise at n>=5.

**Architectural lesson:** JVM speculation models do not directly transfer to CinderX. The JVM's type guards are the primary deopt source; in CinderX, the inline cache layer handles type diversity below the guard level. Measure before building — 17 commits and ~5 approaches were required to discover this, when a single controlled experiment could have falsified the hypothesis.

**What survived:** `BasicBlock::CodeSection` annotation for cold path outlining (~14 lines). The `SimplifyEarly/SimplifyLate` split architecture is in git stash.

---

### Builder Speculative Dispatch (Recompilation Bug)

**Commits:** `75597cb6`, `bf075b53` (revert), `485d68ed`, `0db0f994` (WIP investigation)

**What it tried:** Emit speculative CFG directly in `builder.cpp`, tracking expanded code objects to prevent stale IC types on recompilation.

**Why it failed:** Under auto-compile, when a function was recompiled (Tier 2), the native codegen or recompilation infrastructure crashed for deep polymorphic dispatch (Richards `runTask` with 5+ task types). Nine hypotheses were falsified without finding the root cause.

**Architectural lesson:** Builder-level expansion is the wrong place for speculative dispatch. The builder runs before Simplify, so type-based lowerings (LongBinaryOp, FloatBinaryOp) have not yet run. The expansion creates CFG complexity that the subsequent passes must handle, but the passes were designed for simpler CFGs.

---

### C-API emitCond Type Compatibility Bug

**Commits:** `d7de58b8`, `0bace5a2` (revert to stable)

**What it tried:** Replace Deopt slow path with C-API `CallStatic(PyObject_GetAttr)` in the Simplify pass's `emitCond` helper.

**Why it failed:** Type compatibility bug in the diamond CFG. The slow path returned the attribute VALUE where the downstream code expected the REFINED RECEIVER. Assertion failures at 50K+ iterations.

**Architectural lesson:** Diamond CFGs with Phi merge must have consistent types across all paths. The fast path produces a refined receiver; the slow path must produce the same type, not a different value entirely.

---

### Integer Unboxing First Attempt

**Commits:** `23cd6ac3`, `37af6c7e` (revert), `e7ccf0fe` (re-landed)

**What happened:** The code was functionally correct but lacked documentation explaining a subtle deopt invariant. The `GuardOverflow` FrameState pushes original boxed operands for deopt re-execution. The deopt handler's `readOwned()` automatically re-boxes `CInt64` values via `PyLong_FromSsize_t`. This behaviour was not documented, leading to concerns about correctness.

Re-landed with the same code and improved documentation.

**Architectural lesson:** Deopt semantics are non-obvious. When a FrameState contains a `CInt64` value, the deopt system must know how to convert it back to a `PyLongObject`. This conversion is implicit in `readOwned()` and must be documented, or the next developer will reasonably doubt the correctness.

---

### Exception Handler Branch to Loop Header

**Commits:** `328038e4`, `c193d3d2` (revert), `17708857` (warning comment)

**What it tried:** Replace the Deopt on `JUMP_BACKWARD` in the inline exception handler with a direct `Branch` to the loop header block. This would keep execution in JIT code after catching an exception in a loop, instead of deopting to the interpreter.

**Why it failed:** The inline-emitted `match_block` bypasses the builder's `pending_b2_blocks_` queue. The queue is where `BlockCanonicalizer` and frame state propagation run. When a Branch targets a queue-processed block from an inline-emitted block, SSAify finds register definitions that do not exist in the inline-emitted block's predecessors.

With unspecialised bytecodes, this worked by accident (the register layouts happened to be compatible). With specialised bytecodes (BINARY_SUBSCR_DICT), the register definitions diverged and SSAify crashed.

**Architectural lesson:** The builder has TWO fundamentally different code paths: queue processing (`pending_b2_blocks_`) and inline emission (`emitInlineExceptionMatch`). Queue-processed blocks carry propagated frame state; inline-emitted blocks do not. These two worlds must never be connected by a Branch — only by Deopt (which reconstructs the interpreter state from scratch).

The warning comment at builder.cpp:708-711 guards this one call site, but the invariant is not enforced structurally. Any future developer who emits a block inline elsewhere in builder.cpp will face the same issue.

---

### Float Speculation on Object-Typed Operands

**Commit:** `083224b8` (fix, not revert — the aggressive speculation was implicit)

**What happened:** The Simplify pass's float specialisation speculated `FloatExact` on `Object`-typed operands. Pattern: `0.01 * int_arg` became `GuardType<FloatExact>(int_arg)`. When the argument was actually an integer, the guard immediately failed, forcing the entire function to deopt and run in the interpreter.

**Result:** deep_class_super regressed to 0.63x. The function's forward() method multiplied `x * self.weight` where `self.weight` was a float but `x` could be an integer.

**Fix:** Skip float speculation when operand `couldBe(LongExact)`.

**Architectural lesson:** Type speculation must be conservative at type boundaries. Function arguments and generic containers hold `Object` types that may be int, float, or anything else. Speculating a single type on a generic value is correct only if the profiling data says that type dominates — and CinderX's speculation was not using profiling data for this decision.

---

## Common Patterns Across Failures

Three patterns appear repeatedly:

1. **SSA violations in diamond CFGs.** Option D, the exception handler Branch, and the emitCond type bug all involve creating diamond-shaped CFGs where the two paths have inconsistent register definitions or type semantics. The JIT's SSA infrastructure (SSAify, register allocator, RefcountInsertion) assumes well-formed SSA. Violations produce silent data corruption or crashes, never clean error messages.

2. **Inline emission vs queue processing.** The builder has two code paths, and they have different invariants. Code emitted inline does not benefit from BlockCanonicalizer, frame state propagation, or FrameState consistency checking. This has bitten twice (exception handler Branch, plus the Simplify emitCond bug) and will bite again.

3. **Measuring at insufficient N.** Every speculative expansion approach showed gains at n=3 ABBA. All collapsed to noise at n>=5. The team learned this empirically and established n>=5 as the minimum for any result that informs a decision. But the cost was 17 commits of work on an optimisation that did not produce measurable improvement.
