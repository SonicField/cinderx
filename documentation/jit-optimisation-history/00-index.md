# CinderX JIT Optimisation History

A record of the optimisation work on the CinderX JIT from the ARM64 port through the speculative-dispatch investigation and exception handler recovery, covering February-April 2026.

**Branch:** `aarch64-jit-generators` → `speculation-experiment`
**Commits:** 192 total (93 + 92 + 7)
**Result:** 1.08x → 1.23x geomean over 29 benchmarks, gate failures reduced from 5 to 2

---

## Documents

### [01 — ABBA Testing Methodology](01-abba-testing-methodology.md)

How the benchmark system works, why ABBA interleaving cancels temporal drift, what each parameter controls, and the lessons learned about measurement rigour.

### [02 — Benchmark Catalogue](02-benchmark-catalogue.md)

All 29 JIT benchmarks: algorithm, what aspect of the JIT each stresses, what real-world Python patterns it represents, and the current speedup ratio. Organised by category: compute, object-oriented, generators, data structures, function calls.

### [03 — ARM64 Branch Optimisations](03-arm64-branch-optimisations.md)

93 commits in 8 days: frame mechanics, generator compilation, inline cache C++ optimisation, float specialisation, LICM, speculative method inlining, adaptive specialisation from CPython feedback. Two failed experiments (Option D, GenDataFooter init). Started at nothing, ended at 1.08x geomean.

### [04 — Speculation Branch Optimisations](04-speculation-branch-optimisations.md)

92 commits in 5 days: speculative expansion investigation (17 commits, abandoned after falsification), G2 generator fast paths, integer unboxing (PhiUnboxing pass), inline exception handling, keyword argument fast path, IC improvements. From 1.08x to 1.23x geomean, losers from 5 to 2.

### [05 — Failed and Reverted Optimisations](05-failed-and-reverted-optimisations.md)

Every revert and failure: Option D SSA violation, GenDataFooter init, LICM FrameState bug, all 5 speculative expansion approaches, builder dispatch recompilation bug, exception handler Branch, float speculation on Object types. The three recurring patterns: SSA violations in diamond CFGs, inline emission vs queue processing invariants, and measuring at insufficient N.

### [06 — Technical Debt](06-technical-debt.md)

Active crashes, performance regressions, architectural debt, and measurement gaps. What needs fixing and what the known fix directions are.

### [07 — JIT Architecture Reference](07-architecture.md)

The compilation pipeline, pass ordering, type system, deoptimisation, generator support, inline caching, and tiered compilation. A map for anyone touching this code.

### [08 — Session 9: Exception Handler Recovery](08-session9-exception-recovery.md)

7 commits: generator inline exception handling recovered (YIELD_VALUE scan, generator guard removal), over-Decref refcount bug fixed (root cause of 3-session JUMP_BACKWARD crash), JUMP_BACKWARD Branch to loop header. try_except_callee 1.35x→1.52x, geomean holds at 1.23x. Performance work paused — bottleneck shifted to CPython runtime costs.

---

## Key Numbers

| Metric | ARM64 Branch Start | ARM64 Branch End | Speculation Branch End | Session 9 End |
|--------|-------------------|-----------------|----------------------|---------------|
| Geomean | — | 1.08x | 1.23x* | 1.23x |
| Benchmarks | 23 | 23 | 29 | 29 |
| Gate failures (<0.95x) | — | 5 | 2 | 2 |
| Commits | — | 93 | 92 | 99 |

**\*Measurement caveat:** The 1.23x figure was measured on a clean LTO rebuild. A clean rebuild produces materially different native code than an incremental rebuild — a 6-point difference was observed from the same source code. Of the 8-point improvement over the prior session's 1.15x, only 3-5 points have clean single-variable attribution (IC skip flag for nn_module, codeExtra inline for exceptions). The remaining 3-5 points may be build-environment artifact. pytorch_cm's 22-point swing (1.10x→1.32x) is explicitly unexplained. A controlled A/B rebuild comparison — same code, both clean builds, measuring the build-only delta — was deferred three consecutive sessions and has never been executed. The true attributable improvement from shipped optimisations is likely 1.18-1.20x, not 1.23x.

## Top Optimisations by Impact

| Rank | Optimisation | Impact | Branch | JIT Layer |
|------|-------------|--------|--------|-----------|
| 1 | Integer unboxing (PhiUnboxing) | fibonacci 2.57x, int_arith 1.58x | speculation | HIR pass |
| 2 | Adaptive specialisation (FOR_ITER, LOAD_ATTR) | +25-57% on loops/attrs | ARM64 | HIR builder |
| 3 | Keyword argument fast path | positional_dispatch 0.76x→1.24x | speculation | Runtime |
| 4 | IC churn detection | pytorch_cm 0.61x→1.05x | speculation | Runtime |
| 5 | Float DoubleBinaryOp | float_arith 0.88x→1.11x | ARM64 | Simplify pass |
| 6 | G2 generator fast paths | gen_simple ~1.24x | speculation | LIR + runtime |
| 7 | IC skip flag | nn_module 0.93x→1.04x | speculation | Runtime |
| 8 | Speculative method inlining | method_calls 1.31x | ARM64 | HIR inliner |
| 9 | METH_FASTCALL dispatch | getattr +17%, hasattr +19% | ARM64 | LIR + runtime |
| 10 | Inline codeExtra lookup | exceptions 0.93x→0.97x | speculation | Runtime |
| 11 | Inline exception handler + JUMP_BACKWARD Branch | try_except_callee 1.35x→1.52x | session 9 | HIR builder |

## What the JIT Cannot Speed Up

- **C extension modules** (json_roundtrip: 1.00x) — the work is in C, not Python
- **String operations** (string_ops: 0.96x) — dominated by CPython C library calls
- **List comprehension frames** (list_comp: 0.89x) — structural overhead in comprehension codegen
- **Deep class hierarchies** (deep_class_super: 0.94x) — diffuse per-call overhead across MRO
