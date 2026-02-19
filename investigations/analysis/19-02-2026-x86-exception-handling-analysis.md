# x86 Exception Handling Patterns in CinderX JIT — Research Analysis

**Date:** 19 February 2026
**Author:** generalist (research agent)
**Source:** Direct investigation via pty-session on devgpu004 + background agent aad345b

## Core Finding

**The CinderX JIT handles exceptions identically on x86 and aarch64.** There is no architecture-specific exception handling path. Both architectures use the same mechanism: deopt to the interpreter, which then dispatches to the exception handler via CPython's `co_exceptiontable`.

The ~10% regression in exception-heavy benchmarks is inherent to the deopt-based design, not a missing aarch64 feature.

## The Exception Flow Through the JIT Pipeline

### 1. HIR Level: Builder (`builder.cpp`)

**`SETUP_FINALLY` handling** at `builder.cpp:4194-4202`:

```cpp
void HIRBuilder::emitSetupFinally(TranslationContext& tc,
    const jit::BytecodeInstruction& bc_instr) {
  BCOffset handler_off = bc_instr.nextInstrOffset()
      + BCIndex{bc_instr.oparg()}.asOffset();
  int stack_level = tc.frame.stack.size();
  tc.frame.block_stack.push(
      ExecutionBlock{SETUP_FINALLY, handler_off, stack_level});
}
```

This pushes exception handler info onto `block_stack` in `FrameState`, captured in deopt snapshots. The JIT does NOT generate HIR-level exception handler blocks. There is no try/except control flow in the HIR CFG.

**Except opcodes explicitly rejected** at `builder.cpp:1550`:

```cpp
case PUSH_EXC_INFO: JIT_ABORT(...)
```

And at `builder.cpp:465-472`:

```cpp
case JUMP_IF_NOT_EXC_MATCH:
case RERAISE:
case WITH_EXCEPT_START: {
  JIT_ABORT("Should not be compiling except blocks ...");
}
```

Exception handler blocks are NEVER compiled on any architecture.

### 2. LIR Level: Guard Emission

**`emitExceptionCheck`** at `generator.cpp:447-467`:

```cpp
void LIRGenerator::emitExceptionCheck(const jit::hir::DeoptBase& i,
    jit::lir::BasicBlockBuilder& bbb) {
  hir::Register* out = i.output();
  if (out->isA(TBottom)) {
    appendGuardAlwaysFail(bbb, i);
  } else {
    auto kind = out->isA(TCSigned) ? InstrGuardKind::kNotNegative
                                   : InstrGuardKind::kNotZero;
    appendGuard(bbb, kind, i, bbb.getDefInstr(out));
  }
}
```

Default guard for any `DeoptBase` instruction:
- Pointer returns: `kNotZero` (NULL = error)
- Signed int returns: `kNotNegative` (negative = error)
- `TBottom`: `kAlwaysFail` (unconditional deopt)

**CheckExc lowering** at `generator.cpp:1890-1896`:

```cpp
case Opcode::kCheckExc: {
  // Guard checking tstate->current_exception
  // If non-null, deopt
}
```

### 3. Machine Code Level: Guard to Deopt

**`TranslateGuard`** at `autogen.cpp`:

| Architecture | Guard Instruction | Effect |
|-------------|-------------------|--------|
| x86 (line 179-251) | `test reg, reg; jz deopt_label` | Branch to deopt on zero |
| aarch64 (line 252-355) | `cbz reg, deopt_label` | Branch to deopt on zero |

Both emit a conditional branch to a deopt label. Structurally equivalent.

### 4. Deopt Trampoline

| Component | x86 | aarch64 |
|-----------|-----|---------|
| Trampoline | `gen_asm.cpp:442-648` | `gen_asm.cpp:649-870` |
| Steps | Save regs → `prepareForDeopt()` → `resumeInInterpreter()` → epilogue | Identical |

Both trampolines:
1. Save all registers
2. Call `prepareForDeopt()` which materialises a PyFrameObject
3. Call `resumeInInterpreter()` which resumes CPython's eval loop
4. Jump to function epilogue

### 5. Interpreter Resume

**`resumeInInterpreter`** at `gen_asm.cpp:325-399`:

```cpp
int err_occurred = shouldResumeInterpreterInErrorHandler(deopt_meta.reason);
result = _PyEval_EvalFrame(tstate, frame, err_occurred);
```

**`shouldResumeInterpreterInErrorHandler`** at `deopt.cpp:299-312`:
- `kGuardFailure`, `kRaise` → `false` (normal deopt)
- `kUnhandledException`, `kUnhandledUnboundLocal` → `true` (error handler)

When `err_occurred` is true, CPython's `_PyEval_EvalFrame` enters the error handler path and uses `co_exceptiontable` to find the matching `except` block.

### 6. Frame Materialisation

**`reifyFrameImpl`** at `deopt.cpp:314-356` (3.12+):
- Sets `frame->instr_ptr` to the current bytecode offset
- Sets `frame->stacktop` from `FrameState.stack`
- The stack depth at deopt point determines what the interpreter sees

**Critical for Approach B1:** The materialiser sets `frame->stacktop = co_nlocalsplus + frame_meta.stack.size()` (deopt.cpp:168-170). If we change the deopt offset from the current instruction to the handler offset, the stack depth will be wrong — the handler expects a different depth than the CheckExc point has.

## Architecture-Specific Differences

There are NO `#ifdef CINDER_X86_64` or `#ifdef CINDER_AARCH64` in:
- HIR builder exception handling
- `emitExceptionCheck` logic
- `resumeInInterpreter` function
- `shouldResumeInterpreterInErrorHandler` function
- `prepareForDeopt` function

The only architecture-specific code is:
- Register save/restore in deopt trampoline (necessarily different register sets)
- Guard instruction emission in `TranslateGuard` (different ISA instructions)

These are structurally equivalent.

## Empirical Verification

Tested on devgpu004 (19 Feb 2026):

| Opcode | try/except works in JIT? | LIR Guard emitted? |
|--------|-------------------------|-------------------|
| CALL (`func()`) | YES | YES (Guard after Call) |
| BINARY_SUBSCR (`d[k]`) | YES | YES (Guard after Call) |
| STORE_ATTR (`obj.x = v`) | YES | YES |
| DELETE_ATTR (`del obj.x`) | YES | YES |
| LOAD_GLOBAL (`name`) | YES | YES |

The mechanism works: JIT deopts → interpreter finds handler via `co_exceptiontable` → exception is caught.

## Performance Cost Model

From testkeeper's controlled experiment:

| Metric | Value |
|--------|-------|
| Per-exception absolute cost | 100ns |
| Exception creation (PyErr_SetObject) | ~82ns (unavoidable) |
| JIT deopt overhead | ~18ns (eliminable) |
| Try-block overhead (no exception) | ZERO |

**Approach B maximum theoretical improvement:** 0.91x → ~1.0x (eliminates 18ns/exception deopt overhead, cannot eliminate 82ns exception creation).

## Falsifiers

1. **"x86 and aarch64 handle exceptions identically"** — Falsifiable by finding any `#ifdef` in the exception pipeline. Checked: there is none.
2. **"Native exception handling would require explicit HIR exception edges"** — Falsifiable by finding an existing mechanism that dispatches to handlers without deopting. Checked: `RERAISE`, `WITH_EXCEPT_START`, `JUMP_IF_NOT_EXC_MATCH` are explicitly rejected in the builder.
3. **"Deopt overhead is ~18ns"** — Falsifiable by measuring with/without deopt (testkeeper measured: confirmed).

## Key Source Locations

| What | File | Lines |
|------|------|-------|
| `emitExceptionCheck` | `cinderx/Jit/lir/generator.cpp` | 447-467 |
| Guard exemption list | `cinderx/Jit/lir/generator.cpp` | 3506-3533 |
| CheckExc lowering | `cinderx/Jit/lir/generator.cpp` | 1890-1896 |
| `TranslateGuard` (x86) | `cinderx/Jit/codegen/autogen.cpp` | 178-251 |
| `TranslateGuard` (aarch64) | `cinderx/Jit/codegen/autogen.cpp` | 252-355 |
| x86 deopt trampoline | `cinderx/Jit/codegen/gen_asm.cpp` | 442-648 |
| aarch64 deopt trampoline | `cinderx/Jit/codegen/gen_asm.cpp` | 649-870 |
| `shouldResumeInterpreterInErrorHandler` | `cinderx/Jit/deopt.cpp` | 299-312 |
| `resumeInInterpreter` | `cinderx/Jit/codegen/gen_asm.cpp` | 325-399 |
| `prepareForDeopt` | `cinderx/Jit/codegen/gen_asm.cpp` | 138-261 |
| `emitSetupFinally` (metadata only) | `cinderx/Jit/hir/builder.cpp` | 4194-4202 |
| Except opcodes rejected | `cinderx/Jit/hir/builder.cpp` | 465-472, 1550 |
| `ExecutionBlock` / `BlockStack` | `cinderx/Jit/hir/frame_state.h` | 13-42 |
| `DeoptReason` enum | `cinderx/Jit/deopt.h` | 73-87 |
| Frame materialisation | `cinderx/Jit/deopt.cpp` | 168-170, 314-356 |
