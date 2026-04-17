# CinderX JIT Benchmark Results — LTO vs LTO

Date: 2026-04-17
Commit: 083224b8 (Fix aggressive float speculation causing deopts on float×int arithmetic)
Branch: speculation-experiment

## Summary

**Geomean: 1.14x** across 29 benchmarks.

CinderX JIT (LTO) vs vanilla CPython 3.12.12 (LTO only, no PGO).

- 19 benchmarks faster (>5%)
- 5 benchmarks slower (>5%)
- 5 benchmarks neutral (within 5%)

## Build Verification

| Component | Build Config | Verification |
|---|---|---|
| CinderX | RelWithDebInfo, ENABLE_LTO=ON | CMakeCache.txt line 375 |
| Vanilla CPython | 3.12.12, --with-lto (no --enable-optimizations, no PGO) | cpython312-lto-only/bin/python3.12 |

Both sides use LTO. No PGO on either side.

## Methodology

- **ABBA design**: 8 subprocess runs (4 JIT, 4 vanilla), alternating to cancel thermal/load drift
- **Compile mode**: `cinderjit.auto()` with 5000 warmup iterations
- **Repetitions**: 2 ABBA reps (8 total runs)
- **Calibrated iterations**: each benchmark tuned to ~500ms to give equal geomean weight
- **Platform**: x86_64 Linux

## Per-Benchmark Results

| Benchmark | Vanilla | CinderX | Speedup |
|---|---|---|---|
| fibonacci | 1215.24ms | 605.34ms | **2.01x** |
| richards_full | 278.31ms | 165.72ms | **1.68x** |
| unpack_seq | 789.06ms | 502.95ms | **1.57x** |
| int_arith | 495.67ms | 349.39ms | **1.42x** |
| try_except_callee | 545.10ms | 397.90ms | **1.37x** |
| richards_slots | 522.79ms | 388.51ms | **1.35x** |
| nbody | 674.16ms | 507.09ms | **1.33x** |
| nqueens | 714.10ms | 555.88ms | **1.28x** |
| gen_simple | 403.11ms | 321.95ms | **1.25x** |
| positional_dispatch | 617.93ms | 498.91ms | **1.24x** |
| coroutine_chain | 393.75ms | 318.24ms | **1.24x** |
| dict_ops | 616.31ms | 536.36ms | **1.15x** |
| fannkuch | 674.24ms | 585.13ms | **1.15x** |
| func_calls | 374.01ms | 329.00ms | **1.14x** |
| deep_class_super | 518.60ms | 457.42ms | **1.13x** |
| list_comp | 532.53ms | 488.58ms | **1.09x** |
| spectral_norm | 456.26ms | 421.37ms | **1.08x** |
| gen_nested | 322.17ms | 302.85ms | **1.06x** |
| store_subscr | 588.15ms | 555.94ms | **1.06x** |
| nn_module | 455.29ms | 443.70ms | 1.03x |
| string_ops | 543.37ms | 526.44ms | 1.03x |
| method_calls | 658.79ms | 646.77ms | 1.02x |
| float_arith | 533.06ms | 531.92ms | 1.00x |
| import_callee | 494.71ms | 492.70ms | 1.00x |
| chaos_game | 470.97ms | 507.84ms | 0.93x |
| exceptions | 465.64ms | 526.82ms | 0.88x |
| yield_from | 337.71ms | 394.97ms | 0.86x |
| json_roundtrip | 441.02ms | 546.65ms | 0.81x |
| **pytorch_cm** | 223.79ms | 297.12ms | **0.75x** |
| **GEOMEAN** | | | **1.14x** |
| **TOTAL** | 15355.87ms | 13203.47ms | **1.16x** |

## Key Optimizations

### Integer unboxing pipeline
fibonacci 2.01x, int_arith 1.42x. Native arithmetic on unboxed integers.

### Keyword argument fast path (commit 1d283987)
positional_dispatch 1.24x. Inlines keyword-to-positional argument resolution.

### Float speculation fix (commit 083224b8)
deep_class_super 1.13x (was 0.63x). Prevents aggressive float-type speculation on int operands.

### Correctness fixes
- IC use-after-free: owned references in inline caches (25c9be34, 52bce5ea)
- uninstrument NULL dereference (1093f90b)
- SIGBUS root-caused to .so file replacement during execution

## Remaining Regressions

| Benchmark | Speedup | Root Cause |
|---|---|---|
| pytorch_cm | 0.75x | Context manager __enter__/__exit__ dispatch overhead (type lookup, object churn, IC invalidation) |
| json_roundtrip | 0.81x | Regression specific to LTO CPython baseline (1.15x vs fbpython) — LTO CPython optimizes JSON paths that the JIT doesn't match |
| yield_from | 0.86x | PEP 380 delegation dispatch chain |
| exceptions | 0.88x | Exception handling overhead |
| chaos_game | 0.93x | Close to parity |

## Reproducing

```
CINDERX_PYTHON=/path/to/cinderx/venv/bin/python3 \
VANILLA_PYTHON=/path/to/cpython312-lto-only/bin/python3.12 \
python3 benchmark_cinderx.py jit --reps=2 --compile=auto
```
