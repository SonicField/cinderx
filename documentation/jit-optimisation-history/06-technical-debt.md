# Technical Debt and Open Issues

## Active Crashes

### 1. ~~Inline Exception Handler Frame State Corruption~~ FIXED (Session 9)

**Fixed in:** commits ec9db191 (over-Decref fix) + 63c617ab (JUMP_BACKWARD Branch)

The root cause was not SSA corruption but over-Decref of localsplus-aliased stack values. `LOAD_FAST` pushes registers without Incref; the handler Decref'd all excess stack values unconditionally, freeing registers still referenced by localsplus. Fix: skip Decref for registers aliased to localsplus. With the refcount fix, the simple Branch to the loop header works correctly. try_except_callee improved from 1.35x to 1.52x.

### 2. Speculative Inlining Closure Bug

**Location:** HIR inliner (inliner.cpp area)
**Test:** `test_jit_speculative_inlining` — "cell object has no attribute 'speak'"

The inliner loads the cell object itself instead of dereferencing cell contents via `LoadCellItem`. Pre-existing bug from the ARM64 branch, not introduced by the speculation work.

**Fix direction:** Dereference cell contents via `LoadCellItem` in the inliner when the target function has free variables.

### 3. Constructor Type Inference Crashes (with-statement)

**Location:** `cinderx/Jit/hir/simplify.cpp` (simplifyLoadAttrSpecial)

Three attempts to narrow return types from constructor calls all crashed:
- `UseType` → assertion in Simplify invariant
- `set_type()` → SIGSEGV in RefcountInsertion (FrameState dangling refs)
- `RefineType` → SIGILL (ud2 = unreachable) at runtime

Root cause: `simplifyLoadAttrSpecial` resolves `__enter__`/`__exit__` to `CallStatic`, which breaks the `WITH_CLEANUP` stack protocol. The entire with-body is eliminated as dead code.

**Fix direction:** Implement `BEFORE_WITH` inlining that models the with-statement protocol, not just individual dunder resolution.

**Severity:** Low — pytorch_cm performs at 1.32x without this fix.

### 4. Pre-Existing Test Failures (4)

These exist on both the main branch and all feature branches:
- `test_jit_perf_map`: perf map fork issue
- `test_jit_preload`: SIGSEGV on function destruction during preload
- `test_jit_support_instrumentation`: JIT doesn't deopt on setprofile/settrace
- `test_cpython_overrides.test__opcode`: references removed Python 3.10 opcodes

---

## Active Performance Regressions

### 1. list_comp: 0.89x (11% slower than interpreter)

The JIT creates and destroys an eval frame for the comprehension's code object on every iteration. The interpreter's comprehension frame is lighter.

The range iterator fast path (commit `8f767f05`) was verified to have no effect. Profiling suggests `ListAppend` or `PyLong_FromLong` allocation dominates, not dispatch.

**Fix direction:** Inline comprehension frames (avoid creating a separate code object) or implement inline dispatch (emit the same operations the interpreter does directly in JIT code). Both are multi-session efforts.

### 2. deep_class_super: 0.94x (6% slower than interpreter)

5-level class hierarchy with `super()` calls. Profiling shows diffuse overhead:
- `_PyObject_Malloc`: +1.2pp over interpreter
- `_PyEvalFrameClearAndPop`: +0.84pp (JIT-only frame teardown)
- `do_super_lookup`: +0.2pp
- `_PyObject_MakeTpCall`: +0.1pp

No single extractable component — the overhead is the sum of many small per-call penalties across 5 inheritance levels.

**Fix direction:** At 0.94x (1 point from the 0.95x gate), the most promising lead is `_PyObject_Malloc` — if the JIT is allocating objects the interpreter avoids, that is a codegen issue. Threshold tension also affects this benchmark: it needs threshold=1 for good IC behaviour but method_calls needs threshold=10+ for bytecode specialisation.

---

## Architectural Debt

### 1. JIT Code Memory Never Deallocated

**Location:** `cinderx/Jit/code_allocator.cpp:191-194` and `:323-327`

Both `releaseCode()` implementations are no-ops (marked TODO). JIT-compiled code is allocated but never freed, even when functions are recompiled or garbage collected.

In short-lived processes this is harmless. In long-running servers, JIT code memory accumulates indefinitely.

### 2. LIR Generator Is a Copy of Codegen

**Location:** `cinderx/Jit/lir/generator.cpp:52-55`

The 131KB `lir/generator.cpp` is acknowledged as "almost identical copy from codegen.cpp" with XXX comments. Any fix in one file must be mirrored in the other.

### 3. Speculative Expansion: Dead Pass in Codebase

**Location:** `cinderx/Jit/hir/speculative_expansion.cpp`, `speculative_expansion.h`

The `SpeculativeExpansion::Run()` is a no-op. The pass is compiled but never does anything. Include at `compiler.cpp:24` is still present. Adversarial test files (`test_adversarial_*.py`) are gated behind `CINDERX_SPECEXP=1` and never run by default.

Either remove the dead code or document it as dormant infrastructure for future workloads with real GuardType deopt pressure.

### 4. deopt.cpp: Overly Broad TCSigned Guard

**Location:** `cinderx/Jit/deopt.cpp:60-78`

The deopt value reconstruction code accepts any type containing `TCSigned` for re-boxing via `PyLong_FromSsize_t`. A debug-only `JIT_DCHECK` tightens this to `CInt64|Long|Nullptr` unions. The runtime guard should be tightened to `TCInt64` specifically to prevent future unboxing additions from silently going through the wrong reconstruction path.

### 5. Py_GIL_DISABLED: Simplify Optimisations Disabled

**Location:** `cinderx/Jit/hir/simplify.cpp` (6 sites), `builder.cpp` (2 sites)

Under free-threading (`Py_GIL_DISABLED`), these optimisations are compiled out:
- `simplifyLoadAttr`
- `simplifyLoadMethod`
- `simplifyLoadAttrSpecial`
- `emitGetLengthInt64` for list/dict/set
- List/tuple binary operations
- UNPACK_SEQUENCE fast paths

Not blocking the current branch (runs without GIL-disabled) but represents significant missing optimisations for free-threaded builds.

### 6. LIR kEqual Signed Comparison Bug

**Location:** `cinderx/Jit/lir/generator.cpp`

The inline LIR comparison fails for `FRAME_SUSPENDED=-1` due to signed vs unsigned operand promotion in asmjit. Worked around with C helpers (`JITRT_G2CheckFastPath`). The inline fix would eliminate C helper call overhead (~11% on yield_from). Root cause unknown after 7+ attempts.

### 7. codeExtra Fix: 3.12-Only

**Location:** `cinderx/Common/code.cpp`, `Common/code.h`

The `codeExtraFast()` inline accesses CPython 3.12 internal struct layout directly. Python 3.14/3.15 interpreters may use a different layout for `_co_extra`. Each inline dispatch that accesses CPython internal structs adds a version-locked coupling point.

---

## Test Coverage Gaps

### test_double_binary_op Not Registered

**Location:** `cinderx/PythonLib/test_cinderx/test_double_binary_op.py` exists but is absent from `JIT_TESTS`, `RUNTIME_TESTS`, and `COMPILER_TESTS` in `run_cinderx_tests.sh`.

This test covers `DoubleBinaryOp` kModulo/kFloorDivide (commit `9501e43a`). It never runs in the gate. If DoubleBinaryOp regresses, no test catches it.

### Exception Handler Edge Case Tests Not Written

Alexie directed that specialised bytecodes + scaling N + nested try/except must become permanent tests for the inline exception handler. These would have caught the Deopt→Branch crash (commit `328038e4`) before it was committed and then reverted.

Testkeeper proposed and alexie approved, but the tests were never written.

---

## Measurement Debt

### Clean vs Incremental LTO Rebuild Confound

The 1.23x geomean includes build effects that have never been isolated. Clean LTO rebuild produces materially different code than incremental rebuild — a 6-point geomean difference (1.15x incremental vs 1.21x clean) was observed from the same source code.

Deferred 3 sessions. The 2-hour cost of running the comparison grows every session because more confounded measurements accumulate.

### pytorch_cm: 22-Point Unexplained Swing

pytorch_cm jumped from 1.10x to 1.32x between sessions with no code change targeting it. The codeExtra inline fix may account for some of this, but the magnitude is unexplained and may be a clean-rebuild LTO effect.

### Falsifier Build Provenance

The 0.83x vs 1.05x falsifier discrepancy (testkeeper vs generalist on the exceptions benchmark) was attributed to different builds but never controlled-tested. Lesson logged: future falsifiers must document which build/commit they ran against. No enforcement mechanism exists beyond the logged lesson.
