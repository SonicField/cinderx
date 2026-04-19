# JIT Architecture Reference

A map of how CinderX compiles Python to machine code. Written for someone who needs to touch this code, not admire it.

---

## Pipeline

```
Python Bytecode (PyCodeObject)
    │
    ▼
Preload globals/constants          [hir/preload.cpp]
    │
    ▼
HIR Generation                     [hir/builder.cpp]
    │
    ▼
HIR Optimisation Passes            [compiler.cpp:69-130]
    │
    ▼
LIR Generation                     [lir/generator.cpp]
    │
    ▼
Register Allocation                [lir/regalloc.cpp]
    │
    ▼
Native Code Emission               [codegen/gen_asm.cpp via asmjit]
```

The pipeline is single-pass — no iterative convergence. Each stage transforms the representation and hands it to the next. The order matters: SSAify must run before anything that assumes SSA form; RefcountInsertion must run after everything that might create or destroy references.

---

## Pass Ordering (compiler.cpp:69-130)

| # | Pass | Constraint |
|---|------|-----------|
| 1 | SSAify | Must run first — converts to SSA form |
| 2 | Simplify | Constant folding, algebraic simplifications, type-based lowerings (BinaryOp → LongBinaryOp, FloatBinaryOp → DoubleBinaryOp, etc.) |
| 3 | DynamicComparisonElimination | Optimises dynamic comparisons |
| 4 | GuardTypeRemoval | Removes redundant type guards |
| 5 | PhiElimination | Removes redundant Phi nodes |
| 6 | Inliner (+re-simplify) | IC-guided speculative inlining, then re-run Simplify on inlined code |
| 7 | BuiltinLoadMethodElimination | Optimise LOAD_METHOD for builtins |
| 8 | CleanCFG | Remove unreachable blocks |
| 9 | DeadCodeElimination | Remove unused instructions |
| 10 | LICM | Loop-invariant code motion for guards |
| 11 | PhiUnboxing | Specialise integer Phis to carry CInt64 |
| 12 | RefcountInsertion | Must run last — inserts Incref/Decref based on liveness |

### Key Interactions

- **Simplify** does the heavy lifting. Most optimisations (float specialisation, integer unboxing, dunder resolution, iterator specialisation) are implemented as pattern matches inside Simplify.
- **Inliner** runs after Simplify so that type information from guards is available. After inlining, Simplify runs again to optimise the inlined code.
- **LICM** runs after DCE so it doesn't hoist dead guards. It runs before RefcountInsertion because hoisting changes liveness.
- **PhiUnboxing** runs after LICM (hoisted guards may create new unboxing opportunities) and before RefcountInsertion (unboxed values need different reference counting).

---

## Key Directories

| Directory | Contents |
|-----------|----------|
| `cinderx/Jit/` | Root: config, runtime support, entry points |
| `cinderx/Jit/hir/` | High-Level IR: builder, passes, type system |
| `cinderx/Jit/lir/` | Low-Level IR: HIR→LIR lowering, register allocation |
| `cinderx/Jit/codegen/` | Native code: x86-64/ARM64 emission via asmjit |

---

## Critical Files

| File | Size | Role |
|------|------|------|
| hir/builder.cpp | large | Bytecode → HIR. Handles specialised opcodes, exception tables, SEND_GEN |
| hir/simplify.cpp | 74KB | Type-based lowerings, constant folding, integer/float unboxing, dunder resolution |
| hir/type.cpp | | Type lattice operations, subtype checking |
| hir/refcount_insertion.cpp | 41KB | Reference counting insertion |
| hir/licm.cpp | ~200 lines | Loop-invariant code motion |
| hir/phi_unboxing.cpp | ~167 lines | Integer Phi specialisation |
| lir/generator.cpp | 131KB | HIR→LIR translation, inline type/state checks for generators |
| lir/regalloc.cpp | 51KB | Linear scan register allocator |
| codegen/gen_asm.cpp | 122KB | Native code emission, frame setup, deopt trampolines |
| codegen/autogen.cpp | 93KB | Pattern-matching instruction translator |
| compiler.cpp | | Pipeline orchestration, pass ordering |
| pyjit.cpp | | Entry points: scheduleJitCompile, compileFunction, force_compile |
| deopt.cpp/h | | DeoptMetadata, reifyFrame, FrameState |
| inline_cache.cpp | 50KB | AttributeCache, type version guarding, PIC |
| jit_rt.cpp | | Runtime helpers: InvokeIterNext, ResumeJitGen, RangeIterNext, BindKeywordArgs |
| generators_rt.cpp/h | | JitGenObject, deopt_jit_gen |

---

## HIR Type System

The HIR uses a type lattice where every value has a static type drawn from:

| Type | Meaning |
|------|---------|
| TObject | Any Python object |
| TLongExact | Exactly `int` (not a subclass) |
| TFloatExact | Exactly `float` |
| TDictExact | Exactly `dict` |
| TCInt64 | Unboxed machine integer (ssize_t) |
| TCDouble | Unboxed machine double |
| TTop | Unknown — could be anything |
| TBottom | Unreachable |

Types support set operations: `couldBe(T)` (intersection non-empty), `isA(T)` (subset), `|` (union), `&` (intersection). Guards narrow types: after `GuardType(x, TLongExact)`, uses of `x` dominated by the guard see `TLongExact`.

---

## Deoptimisation

Three-stage trampoline:

1. **Stage 1 (per-guard):** push deopt metadata index, jump to Stage 2
2. **Stage 2 (per-function):** push epilogue return address, jump to Stage 3
3. **Stage 3 (runtime-wide):** spill all registers, call `reifyFrame()`, call `_PyEval_EvalFrameEx()`

`reifyFrame()` reconstructs a CPython interpreter frame from the JIT's register state using the `FrameState` captured at the guard point. Every guard that can deopt must have a `FrameState` that accurately represents the interpreter's stack, locals, and instruction pointer at that bytecode offset.

**Correctness invariant:** the interpreter must be able to resume execution from the deopt point as if the JIT had never run. This means the FrameState must push the right values in the right order — not the JIT's intermediate results, but the values the interpreter expects at that bytecode offset.

---

## Generator Support

### Lifecycle

1. `InitialYield` creates a `JitGenObject` (wrapping `PyGenObject`) at function entry
2. `YieldValue` suspends execution; `GenDataFooter` stores frame state
3. Resume entry in gen_asm.cpp restores state from `GenDataFooter`
4. Generator deoptimisation: `deopt_jit_gen()` reconstructs interpreter frame from JIT frame

### GenDataFooter Layout

| Field | Type | Size | Purpose |
|-------|------|------|---------|
| linkAddress | uint64_t | 8 | Frame chain linkage |
| returnAddress | uint64_t | 8 | Where to return after yield |
| originalFramePointer | uint64_t | 8 | Caller's frame pointer |
| yieldPoint | GenYieldPoint* | 8 | Which yield point we suspended at |
| spillWords | size_t | 8 | Number of spilled registers |
| resumeEntry | GenResumeFunc | 8 | Function pointer for resume |
| gen | PyGenObject* | 8 | Back-pointer to generator object |
| code_rt | CodeRuntime* | 8 | JIT code runtime data |
| frame_header | FrameHeader | 8 | Lightweight frame for profiling |
| savedIP (aarch64 only) | uint64_t | 8 | Saved instruction pointer |

**Total:** 72 bytes (x86-64), 80 bytes (aarch64)

All codegen accesses use `offsetof()` — no hardcoded numeric offsets.

### Generator Resume Fast Path (G2)

The LIR generator emits inline checks for generator dispatch:

```
load ob_type → compare against &PyGen_Type
load gi_frame_state → compare against FRAME_SUSPENDED
(for kSend: load sent_value → compare against Py_None)
    → fast path: call JITRT_ResumeJitGen (minimal resume)
    → slow path: call JITRT_InvokeIterNext (full protocol)
```

This avoids a function call to check whether the generator is JIT-compiled, doing the check inline in the caller's code.

---

## Inline Caching

4-entry polymorphic inline cache (PIC) for attribute access. Each entry stores:
- `PyTypeObject*` — the receiver type
- Type version tag — for invalidation detection
- Slot offset or descriptor — the cached lookup result

The cache is keyed by type identity (pointer equality), not type version. Type version is checked after the identity match to detect stale entries.

### IC Skip Flag (07d176b1)

Types with custom `__getattro__` (like nn.Module) bypass the cache entirely. The cache was attempting fills that would never hit — the custom `__getattro__` must be called regardless.

### IC Churn Detection (d941a26a)

Types modified at runtime (metaclasses, monkey-patching) cause cache thrashing. After 10 invalidations, a type is marked "volatile" and excluded from type watching.

---

## Tiered Compilation

| Tier | Trigger | Profile Data | Inlining |
|------|---------|-------------|----------|
| 1 | Call count crosses threshold (default 10) | CPython adaptive interpreter bytecodes | None |
| 2 | Post-JIT invocation count crosses threshold (1000) | Warm inline caches | IC-guided speculative inlining |

Tier 1 compilation uses HintType data from CPython's adaptive interpreter. The compile threshold of 10 ensures bytecodes are specialised (LOAD_ATTR_INSTANCE_VALUE instead of LOAD_ATTR) before the JIT sees them.

Tier 2 recompilation calls `forgetCode()` then recompiles with the IC entries from Tier 1 execution. The inliner resolves methods from IC entries, inserts GuardType + GuardIs for safety, and eliminates the now-redundant LoadMethodCached.

---

## Key Invariants

1. **FrameState accuracy:** every DeoptBase instruction must have a FrameState that, when materialised, produces a valid interpreter frame at the corresponding bytecode offset.

2. **Reference counting:** RefcountInsertion is the last pass and sees the final CFG. No pass after it may create or destroy references. Box/unbox pairs that cancel must still maintain correct reference counts at deopt boundaries.

3. **SSA form:** all passes between SSAify and LIR generation operate on SSA. Phi nodes merge values from multiple predecessors. Violating SSA (creating two virtual registers for the same value) causes register allocation to produce incorrect code.

4. **Queue-vs-inline blocks:** blocks emitted through the builder queue receive frame state propagation and BlockCanonicalizer processing. Blocks emitted inline (e.g., in emitInlineExceptionMatch) do not. Edges between the two are dangerous — the inline block lacks the frame state that queue-processed blocks expect from predecessors.

5. **Guard ordering:** guards with side effects (GuardType narrows type, GuardOverflow reads overflow flag) must be ordered correctly relative to the operations they protect. The overflow flag is set by IntBinaryOp and must be read by GuardOverflow before any other instruction that might modify flags.
