# Generator Dispatch Optimisation Plan

**Date:** 19 February 2026
**Author:** claude
**Status:** PLANNING
**Branch:** `aarch64-jit-generators`

## Goal

Fix the generator dispatch overhead that causes three benchmarks to fail the 5% gate:

| Benchmark | Current | Target | Root Cause |
|-----------|---------|--------|------------|
| yield_from_chain | 0.81x | <0.95x | `JITRT_GenSend` → `PyIter_Send` → full vtable dispatch |
| gen_parameterised | 0.92x | <0.95x | `JITRT_InvokeIterNext` → `jitgen_am_send` → `send_core` (3 function calls) |
| coroutine_chain | 0.94x | <0.95x | `gen.send()` → `jitgen_am_send` → `send_core` |

## Architecture: Current Call Chains

### FOR_ITER path (gen_simple, gen_parameterised, gen_nested, gen_interleaved)
```
HIR: InvokeIterNext(iterator)
  → JITRT_InvokeIterNext(iterator)           [jit_rt.cpp:2262]
    → if JitGen_CheckExact:
        jitgen_am_send(iterator, nullptr, &result)  [generators_rt.cpp:161]
          → state checks, exc_info setup
          → send_core(gen, arg, tstate)              [generators_rt.cpp:109]
              → frame.previous = currentFrame(tstate)
              → setCurrentFrame(tstate, frame)
              → gen_footer->resumeEntry(...)         [actual JIT code]
              → unlink frame, restore exc_info
          → post-send cleanup
    → StopIteration handling
```
**A-lite already eliminates:** `tp_iternext` vtable lookup + `jitgen_iternext` wrapper (2 calls).
**Still remaining:** `JITRT_InvokeIterNext` → `jitgen_am_send` → `send_core` → `resumeEntry` (3 function boundaries).

### YIELD_FROM / SEND path (yield_from_chain)
```
HIR: YieldFrom(out, send_value, iter, frame)
  → JITRT_GenSend(gen, v, finish_yield_from, frame)  [jit_rt.cpp:1634]
    → PyIter_Send(gen, v, &retval)                    [CPython C API]
      → tp_as_async->am_send                          [vtable dispatch]
        → jitgen_am_send(gen, v, &result)             [generators_rt.cpp:161]
          → send_core(gen, v, tstate)
            → resumeEntry(...)
```
**5 function boundaries** between the JIT caller and the JIT callee!

### Coroutine .send() path (coroutine_chain)
```
gen.send(val) [interpreter dispatch]
  → jitgen_send(obj, arg)                        [generators_rt.cpp:246]
    → jitgen_am_send(obj, arg, &result)           [generators_rt.cpp:161]
      → send_core(gen, arg, tstate)               [generators_rt.cpp:109]
        → resumeEntry(...)
```
Similar to FOR_ITER but entered from interpreter rather than JIT.

## Proposed Fix: Phase G (Generator Fast-Path)

### G1: Inline send_core into JITRT_InvokeIterNext

**File:** `cinderx/Jit/jit_rt.cpp`

Replace the current A-lite fast path:
```cpp
if (JitGen_CheckExact(iterator)) {
    PyObject* result = nullptr;
    PySendResult status = jit::jitgen_am_send(iterator, nullptr, &result);
    // ... handle result
}
```

With fully inlined frame linkage:
```cpp
if (JitGen_CheckExact(iterator)) {
    JitGenObject* gen = JitGenObject::cast(iterator);

    // State check (replicate jitgen_am_send's guard)
    if (gen->gi_frame_state == FRAME_SUSPENDED ||
        gen->gi_frame_state == FRAME_SUSPENDED_YIELD_FROM) {

        PyThreadState* tstate = PyThreadState_Get();

        // Exception state threading (from jitgen_am_send)
        _PyErr_StackItem* prev_exc_info = tstate->exc_info;
        gen->gi_exc_state.previous_item = prev_exc_info;
        tstate->exc_info = &gen->gi_exc_state;

        gen->gi_frame_state = FRAME_EXECUTING;
        EVAL_CALL_STAT_INC(EVAL_CALL_GENERATOR);

        // Frame linkage (from send_core)
        GenDataFooter* gen_footer = gen->genDataFooter();
        _PyInterpreterFrame* frame = generatorFrame(gen);
        frame->previous = currentFrame(tstate);
        setCurrentFrame(tstate, frame);

        // Direct call to JIT code
        PyObject* result = gen_footer->resumeEntry(
            reinterpret_cast<PyObject*>(gen),
            Py_None,  // arg = None for iternext
            0,        // finish_yield_from
            tstate);

        // Cleanup (from send_core + jitgen_am_send)
        if (JitGen_CheckAny(reinterpret_cast<PyObject*>(gen))) {
            tstate->exc_info = gen->gi_exc_state.previous_item;
            gen->gi_exc_state.previous_item = nullptr;
            setCurrentFrame(tstate, frame->previous);
            frame->previous = nullptr;

            if (FRAME_STATE_FINISHED(gen->gi_frame_state)) {
                gen->gi_frame_state = FRAME_CLEARED;
                jitFrameClearExceptCode(frame);
            } else {
                gen->gi_frame_state = FRAME_SUSPENDED;
            }
        }

        // Handle result (replicate jitgen_am_send's return logic)
        if (result) {
            if (!FRAME_STATE_FINISHED(gen->gi_frame_state)) {
                // PYGEN_NEXT — yielded value
                return result;
            }
            // PYGEN_RETURN — generator exhausted
            if (result != Py_None) {
                _PyGen_SetStopIterationValue(result);
            }
            Py_CLEAR(result);
            // Fall through to StopIteration handling
        }
        // Error or exhausted — fall through to sentinel handling
    }
    // Else: deopt to slow path (running/created state)
}
```

**Impact:** Eliminates `jitgen_am_send` + `send_core` call boundaries. The hot path goes from `JITRT_InvokeIterNext` directly to `resumeEntry` with inline setup/teardown.

**Saves:** ~2 function prologues/epilogues (register saves, stack frame setup) = ~16-24 instructions on aarch64 per yield.

### G2: Fast-path JITRT_GenSend for JIT generators

**File:** `cinderx/Jit/jit_rt.cpp`

Add a JIT generator fast path to `JITRT_GenSend`, similar to G1:
```cpp
JITRT_GenSendRes JITRT_GenSend(
    PyObject* gen, PyObject* v, uint64_t finish_yield_from,
    _PyInterpreterFrame* frame) {
  if (v == nullptr) {
    return {nullptr, 1};
  }
  if (finish_yield_from) {
    Py_INCREF(v);
    return {v, 1};
  }

  // G2: Fast path for JIT generators — skip PyIter_Send vtable dispatch
  if (JitGen_CheckExact(gen)) {
    JitGenObject* jgen = JitGenObject::cast(gen);
    if (jgen->gi_frame_state == FRAME_SUSPENDED ||
        jgen->gi_frame_state == FRAME_SUSPENDED_YIELD_FROM) {
      // Inline jitgen_am_send + send_core
      // [same pattern as G1 but with arg=v instead of Py_None]
      // ...
      return {result, result ? 0 : 1};  // 0=NEXT, 1=RETURN/ERROR
    }
  }

  // Fallback: PyIter_Send for non-JIT generators
  PyObject* retval;
  auto gen_status = PyIter_Send(gen, v, &retval);
  // ... existing handling
}
```

**Impact:** Eliminates `PyIter_Send` → `tp_as_async->am_send` → `jitgen_am_send` → `send_core`. The yield-from chain goes from 5 function boundaries to 1.

### G3: Validate coroutine_chain improvement

The coroutine_chain benchmark uses `gen.send(val)` which enters from the interpreter via `jitgen_send` → `jitgen_am_send` → `send_core`. We can't easily optimise the interpreter→JIT call, but G1's inlining of send_core into JITRT_InvokeIterNext indirectly helps if the coroutine chain uses FOR_ITER internally. If not, we'd need to also inline send_core into jitgen_am_send directly — but that's a refactor of jitgen_am_send which is riskier.

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Exception state threading wrong | Copy exact logic from `jitgen_am_send`, verify with test_jit_generators |
| Deopt case (JitGen_CheckAny returns false) | Keep existing deopt handling from send_core |
| FRAME_SUSPENDED_YIELD_FROM state | Check both states in fast-path guard |
| Async generators | Exclude from fast path (different cleanup logic) |
| #ifdef ENABLE_GENERATOR_AWAITER | Exclude awaiter handling from fast path initially |

## Test Plan

1. All existing generator tests: test_jit_generators (33/33)
2. All existing coroutine tests: test_jit_coroutines
3. test_jit_async_generators
4. Benchmark: gen_parameterised, yield_from_chain, coroutine_chain
5. Full JIT test suite: 172/172

## Falsifiers

1. `JITRT_InvokeIterNext` fast path produces same results as slow path for all generator states
2. Exception state is correctly threaded (test with generators that raise inside yield)
3. Deopt during generator execution preserves correct frame linkage
4. `yield from` delegation with non-JIT inner generators falls back correctly
5. Benchmark shows measurable improvement on gen_parameterised (currently 0.92x)

## Implementation Order

1. G1 first (simplest, measurable on gen_parameterised)
2. Run benchmarks to confirm improvement
3. G2 (yield_from_chain fix)
4. Run full benchmark suite
5. Assess whether G3 is needed for coroutine_chain
