# C-to-C Function Call Optimisation Analysis — CinderX JIT on aarch64

**Date:** 19 February 2026
**Author:** generalist (research agent)
**Source:** Direct investigation of CinderX source on devgpu004 + background agent a7231f1

## 1. Current JIT Call Path

### 1.1 Bytecode to HIR Translation

All Python function call bytecodes (`CALL`, `CALL_FUNCTION`, `CALL_FUNCTION_KW`, `CALL_METHOD`, `INVOKE_FUNCTION`, `INVOKE_METHOD`) are dispatched through:

**`cinderx/Jit/hir/builder.cpp:1881`** — `HIRBuilder::emitAnyCall()`

This routes to different HIR instructions:

| Bytecode | HIR Instruction | Mechanism |
|----------|----------------|-----------|
| `CALL` / `CALL_METHOD` | `CallMethod` → `VectorCall` | Full Python vectorcall protocol |
| `CALL_FUNCTION` / `CALL_FUNCTION_KW` | `VectorCall` | Full Python vectorcall protocol |
| `INVOKE_FUNCTION` | `InvokeStaticFunction` (Static Python) or `VectorCall` (fallback) | Direct call to static entry OR full protocol |
| `INVOKE_METHOD` | `CallInd` (vtable) or `VectorCall` | Indirect via vtable OR full protocol |

### 1.2 LIR Lowering

**VectorCall** (`generator.cpp:1972`): All ordinary calls go through `_PyObject_Vectorcall` or `JITRT_Vectorcall`. There is NO JIT-to-JIT shortcut for regular calls.

**InvokeStaticFunction** (`generator.cpp:2173`): The **only** case where a JIT-to-JIT shortcut exists. For Static Python functions where the callee is already JIT-compiled, CinderX calls the static entry point directly.

### 1.3 Full Call Chain for JIT-to-JIT (Non-Static)

For a normal Python function calling another JIT-compiled function:

1. Bytecode `CALL` → HIR `CallMethod` (or `VectorCall`)
2. LIR `kVectorCall` → calls `_PyObject_Vectorcall` (or `JITRT_Vectorcall`)
3. `_PyObject_Vectorcall` reads `func->vectorcall` from the PyFunctionObject
4. JIT vectorcall entry: sets up native frame, validates args, links Python frame, loads args from `PyObject**` array, executes body, unlinks frame, returns

**Overhead per JIT-to-JIT call:**
- Indirect function pointer load from callable object
- Full vectorcall dispatch (including type checks on callable)
- Argument marshalling through `PyObject**` array
- Frame creation and linking
- Frame unlinking on return

## 2. Static Entry Point Mechanism

### 2.1 Layout

From `cinderx/Jit/compiled_function.h:15-46`:

```
[static entry code] ... [reentry code] [vectorcall entry] [prologue] [body]
                                        ^
                                        |
                                func->vectorcall points here
```

| Entry Point | x86 Offset | aarch64 Offset | Purpose |
|------------|-----------|----------------|---------|
| Vectorcall | 0 | 0 | Standard entry (vectorcall ABI) |
| Reentry | -6 | -12 | Re-enter after argument binding |
| Static | -11 | ~~0~~ **-16 (fixed, commit 2f81a0e0)** | Direct call bypassing arg validation |

### 2.2 Static Entry — Previously Broken on aarch64

`JITRT_STATIC_ENTRY_OFFSET` was 0 on aarch64 (`compiled_function.h:36-41`), meaning `JITRT_GET_STATIC_ENTRY(entry)` returned the vectorcall entry. The static entry code WAS generated (`gen_asm.cpp:2644-2764`) but the offset macro was wrong.

**Fix:** Commit 2f81a0e0 corrected the offset to -16 on aarch64. This is already in the current build.

## 3. asmjit Limitation — Indirect Calls

From `cinderx/Jit/codegen/gen_asm_utils.cpp:35-48`:

```cpp
// x86:
env.as->call(func);  // Single instruction, 32-bit relative offset

// aarch64:
env.as->mov(arch::reg_scratch_br, func);  // Load address into x16
env.as->blr(arch::reg_scratch_br);        // Branch-and-link via register
```

Every call on aarch64 is 2 instructions and trashes x16. On x86, it's 1 instruction with relative addressing. The comment notes this is because asmjit doesn't support arm64 relocations for relative calls (tracked in asmjit/asmjit#499).

For JIT-to-JIT calls within 128MB (the `bl` range), a direct `bl` would save one instruction and improve branch prediction.

## 4. Function Inlining — Building Blocks Exist

From `cinderx/Jit/hir/inliner.cpp`:

The `InlineFunctionCalls` pass (line 341) scans for `VectorCall` and `InvokeStaticFunction` where the callee is known at compile time.

**Inlining criteria** (`canInline()`, line 94):
- Globals/builtins are dicts
- No `*args`, `**kwargs`, keyword-only args
- Argument count matches exactly
- Not a generator
- No cell/free variables
- Callee has been preloaded

**Inlining mechanics** (`inlineFunctionCall()`, line 196):
- For VectorCall: `LoadField(func_code)` + `GuardIs(code_obj)` + `BeginInlinedFunction` + `Branch`
- For InvokeStaticFunction: `BeginInlinedFunction` + `Branch`
- `LoadArg` → `Assign` from caller's arguments
- `Return` → `Assign` + `Branch` to continuation
- `BeginInlinedFunctionElimination` can remove frame setup if no deopting instructions

**Key insight:** The inliner already implements guard-based call specialisation. This pattern could be extended to non-inlined direct calls.

## 5. JIT-Compiled Callee Detection

From `cinderx/Jit/compiled_function.cpp:15`:

```cpp
bool isJitCompiled(const PyFunctionObject* func) {
    return code_allocator->contains(
        reinterpret_cast<const void*>(func->vectorcall));
}
```

This check exists but is **only used for `InvokeStaticFunction`** (Static Python). Regular `VectorCall` never checks if the callee is JIT-compiled.

## 6. What True C-to-C Calling Would Require

### Phase 1: Fix Static Entry on aarch64 — **DONE** (commit 2f81a0e0)

Set `JITRT_STATIC_ENTRY_OFFSET` to -16. Enables `InvokeStaticFunction` to use the static entry on aarch64.

### Phase 2: Call-Site Inline Cache for VectorCall (~100 lines)

For `VectorCall` where the callee is `TFunc` with a known value:

1. Guard on `vectorcall` pointer (like the inliner's `GuardIs` on `func_code`)
2. If guard passes: emit direct call to static entry (bypassing vectorcall protocol)
3. If guard fails: deopt or fall back to `_PyObject_Vectorcall`
4. Use `DeoptPatchpoint` for invalidation when `__code__` is swapped

The building blocks exist: guards, deopt patchpoints, static entry, function entry cache. They just aren't wired up for dynamic Python→Python calls.

### Phase 3: True Native-ABI Calls (significant effort)

- Arguments in registers (not `PyObject**` array)
- Lazy frame setup (only materialise on deopt)
- Dual entry points (vectorcall for unknown callers, native for known callers)
- Register convention: x0=func, x1-x7=args, return in x0

### Phase 4: Fix asmjit Relative Calls (~50 lines)

Replace `mov x16, addr; blr x16` with `bl target` when target is within 128MB. Either:
- Update asmjit to support arm64 relocations
- Post-process generated code to patch `mov+blr` → `bl` when in range

## 7. Comparison with Other JITs

| JIT | Mechanism | CinderX Equivalent |
|-----|-----------|-------------------|
| V8 (JavaScript) | Monomorphic/polymorphic inline caches | `InvokeStaticFunction` (monomorphic only) |
| LuaJIT | Trace compilation, inline callee into trace | HIR inliner |
| PyPy | Meta-tracing, function calls become direct within trace | Not available |

CinderX's approach is closest to V8's monomorphic IC, but limited to Static Python. Phase 2 would extend this to dynamic Python.

## 8. Falsifiers

- **Phase 2 value claim:** Falsifiable by measuring VectorCall overhead on a benchmark with many small function calls (e.g., recursive fibonacci). If the overhead is dominated by argument marshalling rather than dispatch, Phase 2's benefit is limited.
- **asmjit limitation claim:** Falsifiable by checking if asmjit has since added arm64 relocation support (issue #499).
- **Static entry fix claim:** Already verified — commit 2f81a0e0 sets offset to -16.

## Key Source Locations

| What | File | Lines |
|------|------|-------|
| `emitAnyCall` (all call dispatch) | `cinderx/Jit/hir/builder.cpp` | 1881 |
| VectorCall LIR lowering | `cinderx/Jit/lir/generator.cpp` | 1972 |
| InvokeStaticFunction LIR lowering | `cinderx/Jit/lir/generator.cpp` | 2173 |
| `emitCall` (x86 vs aarch64) | `cinderx/Jit/codegen/gen_asm_utils.cpp` | 35-48 |
| Static entry offset macro | `cinderx/Jit/compiled_function.h` | 36-41 |
| `isJitCompiled` check | `cinderx/Jit/compiled_function.cpp` | 15 |
| aarch64 static entry generation | `cinderx/Jit/codegen/gen_asm.cpp` | 2644-2764 |
| Function entry cache | `cinderx/Jit/lir/generator.cpp` | 2056-2061 |
| Inliner criteria | `cinderx/Jit/hir/inliner.cpp` | 94-176 |
| Inliner mechanics | `cinderx/Jit/hir/inliner.cpp` | 196-298 |
| aarch64 register definitions | `cinderx/Jit/codegen/arch/aarch64.h` | — |
