# CinderX JIT Generator Dispatch Overhead Analysis

**Date:** 19 February 2026
**Author:** theologian (architectural analysis agent)
**Status:** COMPLETE. G1-aggressive committed (433acc4b). G2 attempted and reverted (neutral). Full ABBA: 18/23 PASS, 1.08x geomean.

## Problem

JIT-compiled generators are 10-22% slower than interpreter generators:

| Benchmark | Regression | Description |
|-----------|-----------|-------------|
| yield_from_chain | 0.81x (19%) | 3-level generator chain via `yield from` |
| gen_parameterised | 0.92x (8%) | Parameterised generator with varying work |
| coroutine_chain | 0.94x (6%) | Async coroutine chain |
| gen_simple | 0.90x (10%) | Simple generator yielding integers (earlier measurement) |

## Root Cause

The JIT generator yield/resume path goes through **5 function call levels** per iteration. The interpreter's specialised path (`FOR_ITER_GEN`) uses zero function calls.

### JIT Dispatch Chain (per yield/resume)

When a JIT-compiled `for` loop iterates over a JIT generator:

```
JIT code
  |  call JITRT_InvokeIterNext              (1) C function call
  |
  v
JITRT_InvokeIterNext (jit_rt.cpp:2256)
  |  iternext_f = Py_TYPE(iter)->tp_iternext   indirect vtable lookup
  |  val = iternext_f(iterator)             (2) indirect call through type slot
  |
  v
jitgen_iternext (generators_rt.cpp:238)
  |  jitgen_am_send(obj, nullptr, &result)  (3) direct C++ call
  |
  v
jitgen_am_send (generators_rt.cpp:142)
  |  - JitGenObject::cast type check
  |  - Frame state validation
  |  - exc_info swap (tstate->exc_info = &gen->gi_exc_state)
  |  - gi_frame_state = FRAME_EXECUTING
  |  send_core(gen, arg, tstate)            (4) direct C++ call
  |
  v
send_core (generators_rt.cpp:92)
  |  - frame->previous = currentFrame(tstate)
  |  - setCurrentFrame(tstate, frame)
  |  gen_footer->resumeEntry(...)           (5) indirect call into JIT code
  |
  v
JIT generator code executes, yields
  |
  v  (returns through all 5 layers)
```

Each function call/return pair on ARM64 costs ~6-8 instructions (stp/ldp x29,x30, possible callee-save registers). Total dispatch overhead: **~40-50 instructions per yield/resume**.

### Interpreter Fast Path (FOR_ITER_GEN)

When the interpreter's `for` loop iterates over a regular generator:

```
FOR_ITER_GEN (generated_cases.c.h:3255-3274)
  |  _PyFrame_StackPush(gen_frame, Py_None)     push sent value
  |  gen->gi_frame_state = FRAME_EXECUTING
  |  gen->gi_exc_state.previous_item = tstate->exc_info
  |  tstate->exc_info = &gen->gi_exc_state
  |  DISPATCH_INLINED(gen_frame)                 frame switch + goto start_frame
  |
  v
Generator bytecodes execute normally
  |
  v
YIELD_VALUE
  |  gi_frame_state = FRAME_SUSPENDED
  |  frame = frame->previous                     pop frame
  |  goto resume_frame                           back to consumer
```

Total dispatch overhead: **~14 instructions per yield/resume**. Zero function calls. All inline in the eval loop.

### Why JIT Generators Never Get FOR_ITER_GEN

JIT generators use a separate heap type created via `PyType_FromSpec` from `JitGen_Spec` (generators_rt.cpp:600-631). This type is stored in module state (`cinderx::getModuleState()->genType()`), NOT as the static `PyGen_Type` singleton.

The `FOR_ITER_GEN` specialisation guards on exact type identity:

```c
// generated_cases.c.h:3258
DEOPT_IF(Py_TYPE(gen) != &PyGen_Type, FOR_ITER);
```

Since `Py_TYPE(jit_gen) != &PyGen_Type` is always true, JIT generators always deopt to the generic `FOR_ITER` path, which calls `tp_iternext`.

The same gap exists in `SEND_GEN` (cinder-bytecodes.c:250):

```c
DEOPT_IF(Py_TYPE(gen) != &PyGen_Type &&
         Py_TYPE(gen) != &PyCoro_Type, SEND);
```

Neither specialisation was updated to accept JIT generator/coroutine types.

### Impact on yield_from_chain

`yield from` uses the `SEND` bytecode. The JIT's `Send` HIR instruction (builder.cpp:4886) lowers to `call JITRT_GenSend` (lir/generator.cpp:3449) which calls `PyIter_Send` → `am_send` → `jitgen_am_send` → `send_core` → `resumeEntry`. Same 5-level chain.

`yield_from_chain` chains 3 generators. Each value propagation does N SENDs (one per chain level). With 3 levels: 3 x 5 = 15 function call/return pairs per final value. The interpreter does 3 x DISPATCH_INLINED = 3 frame switches = ~18 instructions total. The JIT version costs ~150 instructions.

This explains why `yield_from_chain` (0.81x) is much worse than `gen_simple` (0.90x). Dispatch overhead multiplies with chain depth.

## This Is NOT Architectural

The overhead is a **missing optimisation**, not a fundamental limit. The interpreter achieves fast generator resume by inlining the frame switch. The JIT could do the same.

Both systems run on the same hardware. The interpreter proves that generator resume can be done in ~14 instructions. The JIT currently uses ~50 instructions because it goes through 5 function call layers that each add frame setup/teardown overhead.

The x86 CinderX JIT has the **same dispatch structure** (same 5-level call chain, same `generateResumeEntry` pattern). This is not ARM-specific.

## Fix Approaches

### Approach A: Runtime Fast-Path (Recommended — In Progress)

Add a JIT generator type check at the top of `JITRT_InvokeIterNext` (jit_rt.cpp:2221). If the iterator is a `JitGenObject`, replicate `jitgen_am_send`'s pre-resume work inline and call `send_core` directly, skipping the `tp_iternext` → `jitgen_iternext` → `jitgen_am_send` chain.

**Eliminates:** 3 of 5 function call levels (tp_iternext indirect, jitgen_iternext, jitgen_am_send).
**Keeps:** `send_core` intact (handles frame linkage, resumeEntry, deopt check, cleanup).
**Estimated savings:** ~18-24 instructions per yield/resume.
**Complexity:** ~40-50 lines of careful code (testkeeper's estimate, confirmed).
**Risk:** Must replicate `jitgen_am_send`'s pre/post-resume logic correctly.

**Correctness constraints (from testkeeper's review):**
- `send_core` (generators_rt.cpp:92-135) must still run for cleanup
- Deopt check (`JitGen_CheckAny`) is handled by `send_core` — safe
- Pre-resume: must set `gi_frame_state = FRAME_EXECUTING`, swap `exc_info`, validate state
- Post-resume: `StopIteration` handling, frame state check, exception cleanup
- The same optimisation should also apply to `JITRT_GenSend` (SEND path) for yield_from_chain

**Falsifiers:**
- test_jit_generators (35 tests) + test_jit_generator_aarch64 (30 tests) must all pass
- Exception thrown mid-yield must not corrupt exc_info chain
- Generator deopt during resume must fall back correctly
- gen_simple regression should improve from 10% to <5%

### Approach B: New HIR Instruction (Future)

Add `TJitGen` type to HIR type system. Add `InvokeGenNext` HIR instruction. Simplifier converts `InvokeIterNext` → `InvokeGenNext` when iterator type is known. LIR lowers to fully inlined pre/post-resume + direct `resumeEntry` call.

**Eliminates:** 4 of 5 function call levels (everything except resumeEntry).
**Estimated savings:** ~30-36 instructions per yield/resume.
**Complexity:** Multiple files: type.h/cpp, hir.h, builder.cpp, simplify.cpp, generator.cpp.

### Approach C: Interpreter Specialisation Override (Complementary)

Override `FOR_ITER_GEN` and `SEND_GEN` in `cinder-bytecodes.c` to also accept JIT generator/coroutine types. Adds `|| JitGen_CheckExact(gen) || JitCoro_CheckExact(gen)` to the type guards.

**Impact:** Only helps when an *interpreted* consumer iterates over a JIT generator. Does NOT help the benchmark (where both consumer and generator are JIT-compiled). Matters for real applications with mixed JIT/interpreted code.

## Evidence and Falsification Record

| Hypothesis | Status | Evidence |
|-----------|--------|---------|
| spillRegistersForYield 2x spill pressure | **RETRACTED** | INIT_REGISTERS count irrelevant to actual spill count |
| Debug fprintf in send_core | **RETRACTED** | Not present on devgpu004 (only local uncommitted changes) |
| ARM64 ptr_resolve overhead | **Minor contributor** | Only 3-5 extra instructions per yield — insufficient for 10-22% |
| 5-level function call dispatch | **CONFIRMED** | Source-level trace of both paths; instruction count analysis |
| JIT gen heap type != PyGen_Type | **CONFIRMED** | JitGen_Spec (generators_rt.cpp:600), type.cpp:39 maps TGen to &PyGen_Type |
| FOR_ITER_GEN never fires for JIT gens | **CONFIRMED** | generated_cases.c.h:3258 exact type check |
| x86 has same dispatch structure | **CONFIRMED** | gen_asm.cpp:2385-2436, same 5-level chain |
| No LICM pass in JIT | **CONFIRMED** | Zero matches for LICM/LoopInvariant/hoist in hir/ |

## Related Files

| File | Lines | Role |
|------|-------|------|
| `generators_rt.cpp` | 92-135 | `send_core` — resumes JIT generator |
| `generators_rt.cpp` | 142-223 | `jitgen_am_send` — pre/post-resume wrapper |
| `generators_rt.cpp` | 238-247 | `jitgen_iternext` — tp_iternext slot |
| `generators_rt.cpp` | 600-631 | `JitGen_Spec` — separate heap type definition |
| `jit_rt.cpp` | 2221-2266 | `JITRT_InvokeIterNext` — JIT's generic iterator dispatch |
| `jit_rt.cpp` | 1620-1658 | `JITRT_GenSend` — JIT's SEND dispatch |
| `generated_cases.c.h` | 3255-3274 | `FOR_ITER_GEN` — interpreter's fast generator path |
| `cinder-bytecodes.c` | 247-267 | `SEND_GEN` — interpreter's fast SEND path |
| `ceval_macros.h` | 108-117 | `DISPATCH_INLINED` — zero-cost frame switch |
| `hir/builder.cpp` | 3986-4001 | `emitForIter` — HIR lowering of FOR_ITER |
| `lir/generator.cpp` | 2738-2743 | LIR lowering of InvokeIterNext |
| `hir/inliner.cpp` | 142-143 | Generator exclusion from function inliner |
| `gen_asm.cpp` | 2437-2509 | ARM64 `generateResumeEntry` |
| `gen_asm.cpp` | 2385-2436 | x86 `generateResumeEntry` (same structure) |
