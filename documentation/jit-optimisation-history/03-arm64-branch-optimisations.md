# ARM64 Branch: Optimisation History

**Branch:** `aarch64-jit-generators`
**Commits:** 93 (from `14b48134` to `9501e43a`)
**Duration:** 17-24 February 2026 (8 days)
**Starting point:** CinderX had partial ARM64 support — the backend existed but was incomplete and generators could not be JIT-compiled.

---

## Phase 1: Frame Mechanics

*4 commits, 17 February 2026*

The JIT must save return addresses during calls so that frame reification (tracebacks, debuggers) can reconstruct the Python call stack. On x86-64, the CALL instruction pushes the return address automatically. On ARM64, LR (x30) must be saved explicitly.

Three attempts before the correct solution:

1. **`frame_base + kPointerSize`** — reads the caller's LR from the prologue. Produces wrong IP values but does not crash.
2. **`[SP, #8]`** — explicit save before each BL/BLR. Fixed double-counting and register clobbering, but the save slot overlapped with `kVectorcallArgsOffset` (vectorcall args[0]).
3. **`[FP + saved_ip_fp_offset]`** (commit `322d20f2`) — the final solution. Pre-computed FP-relative offset verified by `JIT_CHECK` assertion in `computeFrameInfo`. No overlap with anything.

**Impact:** Code generation (gen_asm.cpp), frame reification (frame.cpp). Without this, all subsequent work would produce wrong tracebacks.

**Bugs discovered:**
- Register clobbering: call target in x12/x13 overwritten by `saveReturnAddress`
- Scratch register interference: large frame offsets used x13 for pointer resolution, clobbering the call target
- The vectorcall overlap was the subtlest — only manifested when generators received arguments

---

## Phase 2: Generator Compilation

*11 commits, 17-18 February 2026*

Generators could not be JIT-compiled on ARM64. The problem was that `generateResumeEntry()` reassigns FP (x29) to point at the heap-allocated `GenDataFooter`. Any subsequent saved-IP write at `[FP + offset]` would corrupt the heap.

The solution (commit `fa3f12e9`): compute the `GenDataFooter` address at JIT compile time using a formula with all terms known at compile time:

```
gen + _PyObject_VAR_SIZE(genType, computeSlots) - sizeof(GenDataFooter)
```

This emits as a single ADD instruction. The three deopt guards that previously blocked generator compilation on ARM64 were removed.

**One revert:** Commit `5b3cf6b3` tried to initialise `frame_header` in `GenDataFooter` during allocation, enabling frame walking for JIT generators. Reverted — the initialisation was premature and broke exception paths and async generators.

**Result:** All generator-heavy Python code (iteration, async, comprehensions) could now be JIT-compiled on ARM64.

---

## Phase 3: Inline Cache C++ Optimisation

*2 successful commits + 1 reverted experiment, 18 February 2026*

### A-lite: Runtime Fast Paths (Success)

Two commits (`9e78b1ad`, `e4aca5b8`) optimised the inline cache C++ implementation — not the generated assembly, but the C++ runtime that the generated code calls.

For `__slots__` attribute access (`T_OBJECT_EX` member descriptors):
- **Load:** Inlined `PyMember_GetOne` type dispatch into a direct pointer dereference, bypassing `doInvoke` virtual call
- **Store:** Same pattern for `PyMember_SetOne`, plus inlining the `invoke()` fast path

**Measured impact:**
- Slots read: 0.73x → 0.85x (+12pp)
- Slots write: reached 0.94x
- Richards benchmark: 0.89x → 0.93x

**Where it sits:** Runtime (inline_cache.cpp). The JIT's generated code calls into the inline cache runtime; this makes those calls faster.

### Option D: LIR Inline Type Guard (Reverted)

Commit `3c4ff942` attempted something more ambitious: inline the type check + slot access directly into LIR-generated machine code, eliminating the C function call to `LoadAttrCache::invoke()` entirely.

Initial result: slot_read 0.80x → 0.96x (+16pp). But it was reverted (commit `8af4dc49`).

**Why it failed:** The LIR inline fast path created two virtual registers for the same HIR output (`dst`), violating SSA. The incref block wrote `%31 = Move slot_value` while the call block wrote `%33 = Call invoke(...)`. The register allocator, seeing that `%33` was never read, eliminated it. On ARM64, no `mov x19, x0` was emitted after the call, so x19 retained its stale value (the function pointer). Symptom: `self.x` returned `<function get_x>` instead of `42`.

**What it taught:** LIR-level inline fast paths that create diamond CFGs must use the prior-art pattern from `kIsNegativeAndErrOccurred` (generator.cpp:1174-1208) — initialise the output register before the branch, modify in each path. The two-register approach violates SSA and silently produces wrong results.

---

## Phase 4: Cherry-picks from Upstream

*22 commits, 19 February 2026*

Infrastructure cherry-picks to keep the branch in sync. Not original optimisations, but necessary for correctness.

**ARM64-specific fixes:**
- Footer address for generator frames (upstream fix)
- Comparison promotion to 32-bit outputs
- Register size calculation for GP/VecD
- Static Python thunk helper
- Sub-word load fix (avoid getGp)
- Primitive return register fixes (w2→w1, umov→fmov, movi→fmov)

**Bug fixes:** Generator ref leaks (4 fixes), reftotal race in batch compilation, memory leaks in tests, JIT descriptor leak.

---

## Phase 5: Generator Dispatch and Exception Handling

*13 commits, 19 February 2026*

### G1: Generator Dispatch Inlining (Success)

The FOR_ITER runtime helper (`JITRT_InvokeIterNext`) dispatched through `tp_iternext` vtable lookup for all iterators, including JIT generators. Two commits flattened this:

**A-lite** (commit `de12e97b`): Check if the iterator is a JIT generator (`JitGen_CheckExact`). If so, call `jitgen_am_send` directly, saving 2 function calls per yield/resume.

**G1 Aggressive** (commit `433acc4b`): Inline the entire `send_core + jitgen_am_send` chain into `JITRT_InvokeIterNext`. The fast path handles frame linkage, exception state threading, deopt guards, and post-resume cleanup directly.

**Result:** gen_parameterised 0.915x → 0.956x (crosses the 0.95x gate).

**Where it sits:** Runtime (jit_rt.cpp). This is C-level optimisation of the dispatch protocol, not generated-code optimisation. The JIT emits a call to `JITRT_InvokeIterNext`; this makes that call do less work.

### B2: Inline Exception Match (Success)

Three-layer approach to handling `try/except` in JIT-compiled code:

**Layer 1** (commit `32e1cb3b`): Parse Python 3.12's `co_exceptiontable` (variable-length encoded) during HIR builder `createBlocks()` to discover exception handler boundaries.

**Layer 2** (commit `2654c254`): For `BINARY_SUBSCR` inside a `try` block with a simple handler pattern (`PUSH_EXC_INFO → LOAD_GLOBAL <type> → CHECK_EXC_MATCH → POP_JUMP_IF_FALSE → POP_TOP → POP_EXCEPT → RETURN_CONST`), check the exception type inline. On match, emit the except body inline. On no-match, deopt to interpreter.

**Layer 3** (commit `d4a8e490`): Fix the no-match deopt path — left/right operands were already popped from the deopt stack, causing exception state leaks. Nested try/except skipped outer handlers. Fix: push operands back before deopting, use `kUnhandledException` reason so the interpreter walks `co_exceptiontable` correctly.

**Result:** ~3% improvement on exception-heavy code (exceptions benchmark 0.88x → 0.895x).

**Where it sits:** HIR builder (builder.cpp). The exception matching check that normally happens at interpreter level is pulled into the JIT-generated code.

### Dict Subscript Specialisation (Modest Success)

Commit `62ab1385`: For `BINARY_SUBSCR_DICT` on known dicts, call `PyDict_GetItemWithError` directly instead of going through `PyObject_GetItem → tp_as_mapping → mp_subscript`.

**Result:** ~2pp improvement on exceptions benchmark. Does not cross 0.95x gate alone — remaining overhead is in exception object creation.

**Where it sits:** Runtime (jit_rt.cpp, JITRT_DictGetItem wrapper).

---

## Phase 6: Float Specialisation and LICM

*7 commits, 19-20 February 2026*

### FloatBinaryOp → DoubleBinaryOp (Success)

Commit `785e4c30`: When both operands of a `FloatBinaryOp` are `TFloatExact`, lower to `PrimitiveUnbox + DoubleBinaryOp + PrimitiveBox`. `DoubleBinaryOp` emits native `fadd/fsub/fmul/fdiv` instead of calling Python C slot methods. Box elimination cancels intermediate box/unbox pairs.

**Result:** float_arith 0.88x → 1.11x, nbody 0.72x → 0.96x.

**Where it sits:** Simplify pass (simplify.cpp). The lowering is a type-based transformation in the HIR optimisation pipeline.

### LICM: Loop-Invariant Code Motion (Limited Success)

Commit `e6d83dea`: New HIR compiler pass that hoists loop-invariant `GuardType`/`GuardIs` instructions from loop bodies to loop preheaders. Uses existing `DominatorAnalysis` for back-edge detection and natural loop identification.

**Safety constraints:** Only hoists guards on non-phi SSA values defined outside the loop. Never hoists guards on globals, attributes, or loop-variant values.

**Result:** Infrastructure is correct, but did not improve the target benchmarks (chaos_game, spectral_norm) because those have guards on phi nodes (loop-variant). Improving them requires phi type propagation — a separate optimisation.

**Where it sits:** New pass (licm.h, licm.cpp) in the compiler pipeline after CleanCFG + DCE, before RefcountInsertion.

**Critical bug found later** (commit `f44f531d`): LICM hoisted GuardType based on explicit operands being loop-invariant, but `GuardType` inherits from `DeoptBase` with a `FrameState` containing `live_regs` that reference registers defined inside the loop body. Fix: check ALL register references via `visitUses`, including FrameState live_regs.

### Float InPlaceOp and Constant Folding (Success)

Three commits that extended float specialisation to accumulator patterns:

- **InPlaceOp** (commit `228395b1`): Convert `InPlaceOp` on float operands to `FloatBinaryOp`, enabling `total += x` patterns to use DoubleBinaryOp.
- **Constant-fold int→float** (commit `d8a595c9`): When a BinaryOp has one float and one compile-time-known integer, convert the integer to a float constant at compile time. Enables `x / 2` to be lowered through DoubleBinaryOp.
- **Object speculation** (commit `53a738d9`): When LHS is `Object` (accumulator through Phi) and RHS is `FloatExact`, emit a GuardType to narrow LHS, then emit FloatBinaryOp.

**Combined result:** chaos_game 0.881x → 0.940x.

**Where it sits:** Simplify pass (simplify.cpp).

---

## Phase 7: Speculative Method Inlining

*10 commits, 20-22 February 2026*

### Tiered Compilation with IC-Guided Speculation (Success)

Commit `0f3aae41`: JVM-style tiered compilation for method calls:

1. **Tier 1:** Wrapper `tier1Vectorcall` counts invocations post-JIT (atomic counter, `--disable-gil` safe). Patches out at N1=1000 threshold.
2. **IC warmup:** During Tier 1 execution, the inline cache accumulates type data for each call site.
3. **Tier 2 recompilation:** When threshold fires, the inliner reads IC data, checks for monomorphic call sites, and speculatively inlines the resolved target.
4. **GuardType + GuardIs:** Safety chain before each inline site. If the receiver type or function code changes, deopt to interpreter.

### Full C→C Inlining (Success)

Commit `725004da`: At Tier 2, the inliner preloads method targets from IC data, emits the safety chain, and speculatively inlines the resolved function body with `BeginInlinedFunction`. Also fixes an ARM64 codegen bug: `translateLea` used ADD for negative frame-relative offsets, but ARM64 ADD only accepts unsigned 12-bit immediates.

**Result:** method_calls 1.20x speedup.

### LoadMethodCached Elimination (Success)

Commit `89e86eef`: After speculative inlining resolves a method via IC, the original `LoadMethodCached` instruction still runs at runtime. Replace it with `LoadConst(resolved_func)` + `Assign` from the original receiver. For mutable types, install `TypeAttrDeoptPatcher` to detect method reassignment.

**Result:** method_calls 1.22x → 1.31x, nested_calls 1.10x → 1.29x.

**Where it sits:** HIR inliner (inliner.cpp). The speculative inlining is a HIR-level optimisation that uses runtime profile data (IC) to guide ahead-of-time decisions.

### Exception Handler Guard (Safety)

Commit `23c868ac`: The inliner did not check for exception handlers. Inlining a function with `co_exceptiontable` caused frame metadata to fail. Fix: refuse to inline functions with non-empty `co_exceptiontable`.

### Bugs Found

1. **tier1Vectorcall + JITRT_GET_REENTRY** (commit `d23c1e53`): `tier1Vectorcall` replaced the function's vectorcall pointer, but `JITRT_GET_REENTRY` subtracted a constant offset from it to compute the JIT re-entry point — producing garbage. Fix: use `getJitReentry()` helper that looks up the actual JIT entry via `CompiledFunction`.

2. **LICM FrameState references** (commit `f44f531d`): Already described above. Fix: check all register references including FrameState live_regs.

3. **Inlining deopt FrameState** (commit `68c69a14`): GuardType used the CALL FrameState instead of the LOAD_ATTR FrameState. On type mismatch, deopt resumed with the wrong method already resolved.

---

## Phase 8: Specialised Opcode Integration

*12 commits, 22-24 February 2026*

### Adaptive Specialisation from CPython Feedback (Success)

Commit `6a4b2d9d`: Leverage CPython 3.12 adaptive interpreter feedback to emit GuardType in the HIR builder:

| Specialised Opcode | What It Enables | Improvement |
|---|---|---|
| FOR_ITER_RANGE | Range iterator type narrowing | +25% on tight range loops |
| FOR_ITER_LIST | List iterator fast path | +23% on tight list loops |
| FOR_ITER_TUPLE | Tuple iterator fast path | +26% on tight tuple loops |
| LOAD_ATTR_INSTANCE_VALUE | Direct slot access via split dict | +57% on instance attributes |
| STORE_ATTR_INSTANCE_VALUE/SLOT | Type propagation for stores | Type information only |

All gated behind `cinderjit.enable_specialized_opcodes()`.

### LOAD_ATTR_MODULE Inline (Success, WIP)

Commit `97115737`: Inline module attribute access by reading `dk_version` and dict entry index from CPython's inline cache data. Emits `GuardType(module)` + version guard, then reads the dict entry directly.

**Result:** +32% on module attribute access.

### METH_FASTCALL Builtin Dispatch (Success)

Commit `1e5e54e9`: Bridge the JIT's register-based calling convention to `METH_FASTCALL` args-array convention via `JITRT_FastCall0/1/2/3` wrappers.

**Result:** getattr +17%, issubclass +17%, hasattr +19%, divmod +9%.

### Builtin next() G1 Integration (Success)

Commit `46de56af`: Route `builtin next()` through `JITRT_InvokeIterNext` to leverage the G1 fast path instead of the generic `Ci_Builtin_Next_Core`.

**Result:** 16.5% speedup for `next()` calls.

### Specialised Opcode Enable (Success)

Commit `d0bfbcc0`: Enable the specialised opcode handling on ARM64. Maps CPython 3.12+ specialised opcodes to base forms for deopt, handles `END_FOR`, guards `STORE_SUBSCR_LIST_INT`.

### DoubleBinaryOp Extensions (Success)

Commit `9501e43a`: Add `kModulo` and `kFloorDivide` support to `DoubleBinaryOp` via `JITRT_ModDouble` and `JITRT_FloorDivideDouble` runtime helpers. Consolidates benchmark and test scripts.

### Bugs Found and Fixed

- **Bug 6** (commits `5b33ed59`, `d1f23232`): Specialised opcode blocks emit GuardType without a preceding Snapshot. `bindGuards()` dereferences nullptr. Fix: emit Snapshot first. Regression from the fix: preserving guards' own FrameState caused SIGSEGV on tier-up recompilation. Reverted to unconditional `guard.setFrameState(*fs)`.

- **Bug 7** (commit `2286e368`): GuardType deopt used wrong FrameState (post-pop instead of pre-pop). With try/except, SIGSEGV; without, garbled TypeErrors. Fix: emit Snapshot before stack pops.

- **Bug 8** (commit `fc986d02`): `IsNegativeAndErrOccurred` used `MemImm{nullptr}` on ARM64, which means "load from address 0" — not "compare with 0". Fix: use `Imm{0}`.

- **Inliner + specialised opcodes** (commit `0a24f40c`): `reifyLightweightFrames` processed frames outer-to-inner. The inner inlined frame's `updatePrevInstr` walked `frame->previous` but the outer frame's JIT reifier was already removed. Fix: call `updatePrevInstr` once from `prepareForDeopt` before `reifyLightweightFrames`.

---

## Failed and Reverted Optimisations

| Optimisation | Commits | Why It Failed |
|---|---|---|
| Option D: LIR inline LOAD_ATTR | `3c4ff942`, `d2bbb9f5`, `8af4dc49` | SSA violation in diamond CFG. Two virtual registers for same HIR output. Register allocator eliminated the call-path register, leaving stale value. |
| GenDataFooter frame_header init | `5b3cf6b3`, `d8a1e059` | Premature initialisation broke exception paths and async generators. |
| LICM (partially) | `e6d83dea`, `f44f531d` | Infrastructure correct, but target benchmarks had guards on loop-variant phi nodes. Bug: FrameState live_regs referenced loop-body registers after hoisting. |

---

## Summary

The ARM64 branch accomplished four things in 8 days:

1. **Made generators JIT-compilable on ARM64** — enabling the most common Python iteration pattern to benefit from native code.
2. **Built the generator dispatch fast path (G1)** — reducing the C function call chain for `next()` on JIT generators from 4 calls to 1 inline sequence.
3. **Added float specialisation** — enabling native `fadd/fsub/fmul/fdiv` for Python float arithmetic, turning the JIT from slower-than-interpreter to faster on numeric code.
4. **Integrated CPython adaptive specialisation** — leveraging the interpreter's type feedback for +25-57% on attribute access and iteration patterns.

Two experiments failed (Option D and GenDataFooter init) but produced architectural lessons: LIR diamond CFGs must follow the `kIsNegativeAndErrOccurred` pattern for SSA compliance, and generator frame initialisation requires careful ordering with exception and async paths.

The branch ended at 1.08x geomean over 23 benchmarks, with 5 benchmarks still below the 0.95x gate.
