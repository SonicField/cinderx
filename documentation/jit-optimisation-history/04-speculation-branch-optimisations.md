# Speculation-Experiment Branch: Optimisation History

**Branch:** `speculation-experiment`
**Commits:** 92 (from `9501e43a` to `17708857`)
**Duration:** 15 April - 19 April 2026 (5 days, 7 sessions)
**Starting point:** ARM64 branch at 1.08x geomean, 5 benchmarks below gate
**Final result:** 1.23x geomean, 2 benchmarks below gate (list_comp 0.89x, deep_class_super 0.94x)

---

## Phase 1: Infrastructure Consolidation

*7 commits, 15 April 2026*

The ARM64 branch left behind 4 separate benchmark scripts (3,692 lines of shell), scattered test files, and a build system that only worked with `pip install`. This phase unified everything:

- **One benchmark script** (`benchmark_cinderx.py`): ABBA interleaving engine, subprocess isolation, IQR significance testing, calibrated iteration counts, auto-save to timestamped logs. Replaces 4 shell scripts.
- **One build script** (`build.sh`): Direct cmake invocation with `FETCHCONTENT_SOURCE_DIR` overrides for local deps. Four fix-up commits before it stabilised (don't delete tracked dirs, handle hyphenated dep names, pass vars through setup.py, final rewrite to direct cmake).
- **One test runner** (`run_cinderx_tests.sh`): Categories for jit, runtime, compiler, overrides, cpython, full.
- **GenDataFooter static_assert** fixed for x86_64 (72 bytes vs 80 on ARM64).

**Where it sits:** Build infrastructure. Not a JIT optimisation, but a prerequisite for reliable measurement.

---

## Phase 2: Speculative Expansion (17 commits — abandoned)

This is the most instructive sequence on the branch. Five different approaches to eliminating `GuardType` deopt overhead for polymorphic dispatch. All abandoned after discovering the problem does not exist in CinderX.

### The Hypothesis

JVM-style JITs use speculative dispatch: replace binary guard outcomes (fast path XOR full deopt) with multi-path type dispatch chains that fall back to C-API calls instead of deopting. The hypothesis was that `GuardType` deopt overhead is a significant cost in CinderX, especially for polymorphic code like `richards_full` and `nn_module`.

Evidence supporting it: specialised opcodes made generators 7-8% *worse* (more guards = more branches). `perf stat` showed 3.9x more cache references and 2.4x more cache misses on richards_full.

### Attempt 1: Simplify Pass Expansion

Commit `0eca8f17`: Replace `GuardType` (which carries deopt metadata) with `CondBranchCheckType + Deopt` block. Hot path skips the guard; cold path deopts. HEAPTYPE filter gates expansion to user-defined classes only.

**Result:** richards_full +8.5%. nn_module neutral (filter too conservative). But this was at n=3 ABBA — later shown to be outlier-driven.

### Attempt 2: C-API Slow Path

Commit `c6b339d3`: Per alexie's directive "no interpreter fallback on any path", replace the Deopt slow path with `CallStatic(PyObject_GetAttr)`. Pattern-matches `GuardType+LoadAttr` pairs.

**Result:** Functional but had a type compatibility bug — returned the attribute value where the refined receiver was expected. Assertion failures at 50K+ iterations. Reverted to stable baseline (`0bace5a2`).

### Attempt 3: Builder-Level Dispatch

Commit `75597cb6`: Emit speculative CFG directly in `builder.cpp`. Track expanded code objects to prevent stale IC types on recompilation.

**Result:** All 22 benchmarks pass but richards_full regressed from polymorphic slow-path overhead. Reverted (`bf075b53`).

### Attempt 4: Standalone Pass (The Systematic Plan)

Following alexie's directive for a systematic, step-based approach:

1. **Step 0** (`b0c13090`): Consolidate expansion in a standalone `SpeculativeExpansion` pass using `collectDirectRegUses` for structural use-chain analysis.
2. **Step 1** (`a3bc0f75`): Cold path outlining via `CodeSection::kCold` annotation on BasicBlocks.
3. **Step 2** (`9e77ba87`): Value-chain guard expansion — group all GuardTypes on the same base value and expand together.
4. **Step 3** (`53ceec98`): Table-driven C-API slow paths for StoreAttr and Compare.
5. **Step 4** (`6f0ff4dc`): Deopt-aware selective expansion via Tier 2 recompilation — only expand guards at bytecode offsets where deopts occurred.

All working. 44 adversarial tests passing. 2,412 existing tests passing with force-all expansion. The infrastructure was correct.

### The Falsification

With n>=5 ABBA, all benchmark gains collapsed to noise:
- nn_module: +19.7% → +5.3% (IQR not significant, driven by single outlier)
- json_roundtrip: +23.2% → -0.1%
- yield_from: +26.6% → +3.2%
- method_calls: +9.9% → +1.2%
- Geomean 1.049x at n=3 was outlier-driven

### Why It Failed

CinderX already handles polymorphic dispatch effectively:

1. **Subclass graph optimisation:** The builder skips exact-type guards for types with known subclasses — the guard is emitted as a hierarchy check, not an exact-type check.
2. **LoadAttrCached:** Handles attribute access on mismatched types without deopting through the GuardType — the IC manages type diversity below the guard level.
3. **Polymorphic Inline Cache (PIC):** Replaces single-type guards with `CondBranchCheckType` chains at call sites.

GuardType rarely deopts in practice on these benchmarks. The JVM speculation model — where guards are the primary deopt source — does not directly apply to CinderX.

### What Survived

Commit `5a5b50e0` removed 611 lines of expansion code. Two things survived:
- `BasicBlock::CodeSection` annotation for cold path outlining (~14 lines)
- The architectural lesson that n=3 ABBA is insufficient for reliable significance testing

**Where it sits:** HIR Simplify pass and standalone pass (removed). The surviving cold-path annotation is in the HIR IR definition.

---

## Phase 3: Generator Optimisation (G2 Fast Paths)

*12 commits, 16-17 April 2026*

The ARM64 branch built G1 — inlining the entire `send_core + jitgen_am_send` chain into `JITRT_InvokeIterNext`. This phase built G2 — moving the type and state checks from the C runtime into LIR-generated machine code.

### Runtime Function Splitting

Commit `d9360ea1`: Extract the core resume logic (frame linkage, exc_info swap, resumeEntry call, post-resume cleanup) from `JITRT_InvokeIterNext` into a minimal `JITRT_ResumeJitGen`. Smaller function enables better C++ compiler optimisation.

**Result:** yield_from 12.5% faster, instructions -2.5%.

### LIR Inline Type+State Checks

Two commits (`3f12c977`, `32be5359`) inline the JitGen type check and `FRAME_SUSPENDED` state check at LIR level for both `kInvokeIterNext` and `kSend`. Fast path calls the minimal `JITRT_ResumeJitGen`; slow path calls the full dispatch.

**Initially broken.** The inline LIR kEqual comparison for `FRAME_SUSPENDED=-1` never matched at runtime, making the G2 fast path dead code. Counter verification confirmed 100% slow path activation. Root cause: `Ind` operand in `addOperands()` was missing `->setDataType()`, causing the memory operand size to default to `kObject` (64-bit). A `movswl` (16-bit sign-extend) was emitted instead of `movsbl` (8-bit sign-extend), reading garbage from adjacent fields.

### The Fix That Made G2 Work

Commit `beb23b9e`: Replace the broken inline comparison with a C helper `JITRT_G2CheckFastPath`. Counter verification confirmed 98.7% fast path activation.

**Result:** gen_simple ~1.13x speedup (163K to 185K ops/sec).

Commit `47596720` later fixed the root cause (`Ind` DataType propagation), restoring the inline LIR path without the C helper.

### Accessor Inlining

Commit `0f9c5a3f`: `getModuleState()` was a trivial global pointer return but paid PLT + function call overhead on every generator create/destroy. Moving to header inline eliminated ~13.3% of gen_simple benchmark cycles.

**Result:** Generator create/destroy gap vs interpreter reduced from 30% to 5.6%.

### SEND_GEN Specialisation

Commit `0489ae4d`: Add `SEND_GEN` to the specialised opcode table so the builder recognises it. Emit `GuardType<generator:Exact>` in `emitSend` when `SEND_GEN` detected. LIR `kSend` skips the runtime type check when operand type is known.

**Where it sits:** Bytecode recognition (bytecode.cpp), HIR builder (builder.cpp), LIR generator (generator.cpp), runtime helpers (jit_rt.cpp). The G2 optimisation spans all four layers of the JIT.

---

## Phase 4: Integer Unboxing

*14 commits, 16-17 April 2026*

### The Problem

Python integers are heap-allocated objects. Adding two integers means: unbox int A from PyLongObject, unbox int B, add, allocate a new PyLongObject, box the result. In a tight loop, 53-61% of cycles are in boxing/allocation.

### GuardOverflow Infrastructure

Commit `354e4ff2`: New HIR instruction `GuardOverflow` that reads the CPU overflow flag (OF on x86, V on ARM64) after `IntBinaryOp`. If overflow occurred, deopt back to interpreter with the original boxed operands, which handles big integers correctly. This is the safety net that makes unboxing correct — the JIT can use native 64-bit arithmetic, and if the result overflows int64, it falls back to Python's arbitrary-precision integers.

### Box/Unbox Cancellation Fix

Commit `31ce97e8`: The simplify pass was supposed to cancel `PrimitiveBox(PrimitiveUnbox(x))` → `x`, but the comparison was wrong — it compared the box's OUTPUT type with the unbox's output type (`TLongExact` vs `TCInt64`, always different). Fixed to compare the box's INPUT type.

**Where it sits:** Simplify pass (simplify.cpp). This is a prerequisite for all unboxing to be effective.

### First Attempt (Reverted)

Commit `23cd6ac3`: Three-part optimisation:
1. `simplifyLongBinaryOp` converts add/subtract to `PrimitiveUnbox + IntBinaryOp + GuardOverflow + PrimitiveBox` when both operands are `TLongExact`.
2. Integer Phi cascade in `simplifyInPlaceOp` guards Object accumulators as `TLongExact`.
3. `GuardOverflow` FrameState pushes original boxed operands back for deopt re-execution.

Reverted (`37af6c7e`) and re-landed (`e7ccf0fe`) with improved documentation of the deopt handler's `readOwned()` auto-reboxing behaviour.

### PhiUnboxing Pass

Commit `92fec179`: Standalone pass that transforms Phis carrying boxed `TLongExact` to carry unboxed `CInt64` when ALL inputs are `PrimitiveBox` or integer constants AND all uses are `PrimitiveUnbox`.

This is the pass that eliminates per-iteration box/unbox overhead in accumulation loops. Without it, every iteration boxes the result (allocating a PyLongObject) and the next iteration immediately unboxes it. With PhiUnboxing, the Phi carries the raw int64 and no boxing occurs until the value escapes the loop.

**Result:** accumulate JIT matches interpreter (~546ms vs ~555ms, previously ~640ms). 53-61% of accumulate cycles were in boxing/allocation.

### Extension to BinaryOp

Commit `300bcf3a`: Add integer speculation for `BinaryOp` (add/subtract) when the non-exact operand comes from a Phi or LoadConst. Covers fibonacci's `a+b` pattern where both operands are Phis. Excludes function call results to avoid adding speculation overhead where type is genuinely unknown.

**Result:** fibonacci 2.33x vs interpreter (up from 2.20x on ARM64 branch).

### Static Entry Stack Corruption (Critical Bug)

Commits `36be9d93`, `d8151964`: `generateStaticEntryPoint()` jumped to `finish_frame_setup` skipping `allocateHeaderAndSpillSpace()`. Functions entered via the static calling convention had no stack allocation for spill slots — writes to `[rbp - N]` corrupted the caller's stack frame.

Symptoms: intermittent SIGBUS, corrupted RBP, GOT page unmapped. Required a critical mass of compiled functions to trigger (the spill region had to overlap with something important).

**Where it sits:** Code generation (gen_asm.cpp). This was not an optimisation — it was a latent bug exposed by the integer unboxing work because PhiUnboxing increased the number of functions with spill slots.

---

## Phase 5: Inline Exception Handling

*6 commits, 17-19 April 2026*

### Varint Parser Fix

Commit `35581067`: Python 3.12's `co_exceptiontable` uses MSB-first (big-endian) varints. The parser used LSB-first (LEB128). Wrong handler targets for multi-byte values meant `emitInlineExceptionMatch` never fired on real code — the handler addresses were garbage.

### Enabling Inline Exception Match

Commit `fd07d181`: With the varint parser fixed, `emitInlineExceptionMatch` starts working. For `try/except KeyError` patterns (the exceptions benchmark), the JIT checks the exception type inline. On match, the except body runs in JIT code. On no-match, deopts to interpreter.

**Result:** exceptions benchmark 0.88x → ~1.00x parity.

### The Branch-to-Loop-Header Attempt (Reverted)

Commit `328038e4`: Replace the Deopt on `JUMP_BACKWARD` with a direct Branch to the loop header BasicBlock. This would eliminate the deopt-reenter cycle when exceptions are caught in a loop.

**Why it failed:** The inline-emitted `match_block` bypasses the builder's `pending_b2_blocks_` queue. `BlockCanonicalizer` and frame state propagation never run on it. When the Branch targets a queue-processed loop header block, SSAify cannot reconcile register definitions — the inline-emitted block defines registers that the loop header Phis expect to come from different sources.

Reverted (`c193d3d2`). Warning comment added (`17708857`) to prevent future attempts without understanding the queue-vs-inline invariant.

**Where it sits:** HIR builder (builder.cpp). The architectural issue is that inline emission and queue processing are two fundamentally different code paths with different invariants for frame state propagation.

---

## Phase 6: Keyword Argument Fast Path

*1 commit, 17 April 2026*

Commit `1d283987`: When all keyword arguments at a call site match the callee's positional parameter names in order (identity compare on interned strings), skip `JITRT_BindKeywordArgs`. No heap allocation, no name-matching loop. Re-enter JIT with `kwnames=nullptr`.

**Result:** positional_dispatch 0.76x → 1.24x.

**Where it sits:** Runtime (jit_rt.cpp). This is a runtime fast-path check, not a compiler optimisation.

**Real-world relevance:** Extremely common Python pattern — `func(a=x, b=y)` where the keyword names match positional parameter names.

---

## Phase 7: Float Speculation Fix

*1 commit, 17 April 2026*

Commit `083224b8`: The Simplify pass speculated `FloatExact` on `Object`-typed operands (function arguments, generic variables). Pattern: `0.01 * int_arg` became `GuardType<FloatExact>(int_arg)` → immediate deopt → forced entire function to interpreter.

Fix: skip float speculation when operand `couldBe(LongExact)`.

**Result:** deep_class_super recovered from 0.63x regression to ~1.13x.

**Where it sits:** Simplify pass (simplify.cpp).

---

## Phase 8: Lazy Initialisation

*3 commits, 18 April 2026*

### Deferred Heap Scan

Commit `45f818d1`: Remove `init_existing_objects()` (GC heap walk) from the import path. This function walks the entire heap to find existing code objects and schedule them for JIT compilation. Moved to only run when JIT actually enables via `compile_after_n_calls_impl()`.

### Watcher Early-Return Guards

Commit `134e4e8d`: Code, dict, and type watcher callbacks now check `state != kRunning` before doing any JIT-related work. Eliminates watcher callback overhead during module import before JIT enables.

**Where it sits:** Module initialisation (_cinderx-lib.cpp). Reduces the baseline tax of having CinderX loaded even when JIT is not yet active.

**Real-world relevance:** PyTorch workloads with heavy dict creation during import — the type and dict watchers were firing on every dict operation even though JIT was not yet running.

---

## Phase 9: Inline Cache Improvements

*2 commits, 18-19 April 2026*

### IC Churn Detection

Commit `d941a26a`: Types that modify class attributes frequently (context managers toggling `_enabled` flags) trigger full IC invalidation on every write. After 10 invalidations, mark the type as volatile and stop registering new IC watchers.

**Result:** pytorch_cm 0.61x → 1.05x. The context manager pattern (`_NoGrad._enabled = False` in `__enter__`, restore in `__exit__`) invalidated every IC entry on every context manager entry/exit.

### IC Skip Flag

Commit `07d176b1`: Types with `tp_getattro != PyObject_GenericGetAttr` can never use the inline cache (their `__getattr__` intercepts all attribute access). After the first slow-path miss, set `skip_cache_` to immediately fall through to `PyObject_GetAttr`, avoiding the empty cache scan overhead.

**Result:** nn_module 0.93x → 1.04x (session 6 ABBA).

**Where it sits:** Runtime (inline_cache.cpp). Both fixes improve the IC's behaviour for pathological patterns without changing the JIT-generated code.

---

## Phase 10: Compile-Time Dunder Resolution

*1 commit, 17 April 2026*

Commit `f9a95f8f`: `LoadAttrSpecial` resolves `__enter__`/`__exit__` dunder methods at compile time via `typeLookupSafe` when the receiver type is exact. Eliminates the runtime `_PyType_Lookup` MRO walk. Guards type stability with `TypeAttrDeoptPatcher`.

**Where it sits:** Simplify pass (simplify.cpp).

**Real-world relevance:** All `with` statement blocks. Python's context manager protocol calls `__enter__` and `__exit__` on every with-statement entry/exit.

---

## Phase 11: Runtime Micro-Optimisations

*2 commits, 18-19 April 2026*

### Range Iterator Fast Path

Commit `8f767f05`: Bypass `tp_iternext` dispatch for range iterators by accessing `_PyRangeIterObject` fields directly.

**Result:** No measured benchmark effect. `PyLong_FromLong` allocation dominates the cost, not dispatch.

### Inline codeExtra Lookup

Commit `c9501aa5`: Replace `PyUnstable_Code_GetExtra` calls with `codeExtraFast()` — 2 pointer dereferences instead of a cross-.so PLT call plus `CriticalSectionGuard`.

**Result:** exceptions 0.93x → 0.97x (crossed the 0.95x gate). The PLT call was 2.4% of total cycles in the prior profile.

**Where it sits:** Runtime (Common/code.cpp, Common/code.h). Every JIT function entry pays this cost.

---

## Phase 12: Bug Fixes

*5 commits across multiple phases*

### Use-After-Free in Inline Caches (Critical)

Commits `25c9be34`, `52bce5ea`: Four inline cache types stored `BorrowedRef<>` without INCREF. GC freed cached objects, leaving dangling pointers. Confirmed via signal handler + core dump. Changed to `Ref<>` (owned reference) for 3 caches; `LoadTypeAttrCache` uses manual INCREF/DECREF because `valueAddr()` returns `&value_` for JIT codegen.

### NULL Dereference in uninstrument()

Commit `1093f90b`: `uninstrument()` accessed `code->_co_monitoring->per_instruction_opcodes` without NULL check. Intermittent SIGSEGV during force_compile batch compilation.

### Auto-Compile Warmup

Commit `b7ffca21`: Previous warmup called each function 3-5 times with large `n_iter`, crossing the threshold for inner loops but not the function itself. Fix: call each function 1100 times to cross the 1000-call auto-compilation threshold.

### Missing Richards Methods

Commit `03628e21`: richards_full was 0.73x because `_RTaskState` query methods (isPacketPending, etc.) were not in `_JIT_COMPILABLE`. 14% of cycles were in `Ci_EvalFrame` — the interpreter was running these hot methods.

**Result:** richards_full 0.73x → 1.20x. Not an optimisation — a benchmarking methodology fix.

---

## Progression Summary

| Session | Geomean | Losers | Key Change |
|---------|---------|--------|------------|
| Start (ARM64) | 1.08x | 5 | Baseline from ARM64 branch |
| Session 1 | 1.08x | — | Infrastructure consolidation, speculative expansion investigation |
| Session 2 | 1.13x | — | Float speculation fix, exception handler, lazy init, G2 foundation |
| Session 3 | 1.13x | — | G2 fast paths fixed, gen_simple improved |
| Session 4 | 1.15x | 4 | Correct baseline established, IC skip flag verified |
| Session 5 | — | — | (continued work) |
| Session 6 | 1.23x | 2 | IC skip flag shipped, codeExtra inline, range fast path |

**Note:** The 1.15x → 1.23x jump includes clean-rebuild LTO effects. The true attributable gain from session 6 commits is estimated at 3-5 points, not 8. A clean A/B rebuild comparison has been deferred 3 sessions and remains the foundational unfalsified measurement claim.
