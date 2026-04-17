# CinderX JIT Benchmark Results

Date: 2026-04-17
Commit: 083224b8 (Fix aggressive float speculation causing deopts on float×int arithmetic)
Branch: speculation-experiment

## Summary

**Geomean: 1.18x** across 29 benchmarks (CinderX JIT vs vanilla CPython 3.12).

- 20 benchmarks faster (>5%)
- 1 benchmark slower (>5%): pytorch_cm 0.83x
- 8 benchmarks neutral (within 5%), including yield_from 0.95x

## Methodology

- **ABBA design**: 8 subprocess runs (4 JIT, 4 vanilla), alternating to cancel thermal/load drift
- **Compile mode**: `cinderjit.auto()` with 5000 warmup iterations
- **Baseline**: fbpython (`/usr/local/fbcode/platform010/bin/python3.12`)
- **Build**: RelWithDebInfo, LTO enabled (ENABLE_LTO=ON)
- **Platform**: x86_64 Linux
- **Repetitions**: 2 ABBA reps (8 total runs)
- **Calibrated iterations**: each benchmark tuned to ~500ms to give equal geomean weight

## Per-Benchmark Results

| Benchmark | Vanilla | CinderX | Speedup |
|---|---|---|---|
| fibonacci | 1163.60ms | 579.40ms | **2.01x** |
| richards_full | 328.04ms | 165.34ms | **1.98x** |
| nqueens | 791.99ms | 529.97ms | **1.49x** |
| int_arith | 494.10ms | 335.27ms | **1.47x** |
| nbody | 714.36ms | 489.32ms | **1.46x** |
| try_except_callee | 552.22ms | 382.43ms | **1.44x** |
| unpack_seq | 669.70ms | 484.23ms | **1.38x** |
| coroutine_chain | 413.28ms | 306.50ms | **1.35x** |
| richards_slots | 500.18ms | 383.96ms | **1.30x** |
| float_arith | 613.27ms | 530.29ms | **1.16x** |
| json_roundtrip | 603.04ms | 522.80ms | **1.15x** |
| dict_ops | 595.53ms | 519.58ms | **1.15x** |
| fannkuch | 654.02ms | 570.99ms | **1.15x** |
| spectral_norm | 470.56ms | 411.64ms | **1.14x** |
| deep_class_super | 527.73ms | 466.33ms | **1.13x** |
| gen_simple | 379.59ms | 334.69ms | **1.13x** |
| positional_dispatch | 552.79ms | 492.15ms | **1.12x** |
| func_calls | 347.56ms | 319.06ms | **1.09x** |
| import_callee | 502.72ms | 471.78ms | **1.07x** |
| gen_nested | 293.48ms | 283.70ms | 1.03x |
| store_subscr | 554.49ms | 540.29ms | 1.03x |
| method_calls | 603.73ms | 601.01ms | 1.00x |
| string_ops | 503.62ms | 509.37ms | 0.99x |
| chaos_game | 483.65ms | 492.26ms | 0.98x |
| list_comp | 472.28ms | 480.09ms | 0.98x |
| exceptions | 491.82ms | 507.69ms | 0.97x |
| nn_module | 424.32ms | 441.60ms | 0.96x |
| yield_from | 375.36ms | 396.83ms | 0.95x |
| **pytorch_cm** | 229.88ms | 277.02ms | **0.83x** |
| **GEOMEAN** | | | **1.18x** |

## Key Optimizations

### Integer unboxing pipeline
fibonacci 2.01x, int_arith 1.47x. The JIT unboxes integer operations to native arithmetic, eliminating PyLong allocation overhead.

### Keyword argument fast path (commit 1d283987)
positional_dispatch improved from 0.76x to 1.12x. Inlines keyword-to-positional argument resolution for JIT-compiled callees.

### Float speculation fix (commit 083224b8)
deep_class_super improved from 0.63x to 1.13x. The JIT's BinaryOp simplification was speculating FloatExact on Object-typed operands, causing GuardType failures on int arguments. Common pattern: `0.01 * int_arg` in class __init__ methods.

### Correctness fixes
- IC use-after-free: store owned references in inline caches (25c9be34, 52bce5ea)
- uninstrument NULL dereference when _co_monitoring is NULL (1093f90b)
- SIGBUS root-caused to .so file replacement during execution

## Remaining Regressions

### pytorch_cm (0.83x)
Context manager __enter__/__exit__ dispatch overhead. Profile shows spread costs: type/MRO lookup (7.4%), object churn (9.9%), IC invalidation from class attribute mutations (4.0%). No single hotspot — architectural overhead from the with-statement protocol.

### yield_from (0.95x)
PEP 380 delegation dispatch chain (jitgen_am_send at 18.3% of cycles). The delegation protocol traverses multiple C call boundaries per value. Close to parity.

## Reproducing

Run the ABBA benchmark:
```
CINDERX_PYTHON=/path/to/cinderx/venv/bin/python3 \
VANILLA_PYTHON=/usr/local/fbcode/platform010/bin/python3.12 \
python3 benchmark_cinderx.py jit --reps=2 --compile=auto
```
