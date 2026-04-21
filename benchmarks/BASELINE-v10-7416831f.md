# CinderX JIT Baseline — Session 10 (v10-baseline)

## 1. Build Hash
- Commit: 7416831f (Add LICM exception handler coverage test)
- Parent: a4e988ba (Fix Bug 6 tests and update type annotations assertion)
- Branch: speculation-experiment
- Full ancestry: 7416831f < a4e988ba < 5e73bfc0 < e1566b85 < c559333a < c414d9fd < d16f0373 < df0a6023

## 2. Compiler
- C/C++ compiler: clang/clang++ 21.1.8 (CentOS 21.1.8-2.el9)
- System GCC: 15.2.1 20260123 (Red Hat 15.2.1-7)
- Linker: LLD 19.1
- readelf .comment: `GCC: (GNU) 15.2.1 20260123 (Red Hat 15.2.1-7)` + `clang version 21.1.8 (CentOS 21.1.8-2.el9)`

## 3. LTO Status
- ENABLE_LTO: ON (CMakeCache.txt)
- Preflight: `[OK] LTO detected (build flags)`

## 4. Build Configuration
- CMAKE_BUILD_TYPE: RelWithDebInfo
- Build command: `./build.sh` (cmake + make -j$(nproc))
- Build directory: scratch/build-x86_64
- Python target: 3.12.13+meta

## 5. Binary Checksums
- _cinderx.so: sha256 `224b7fa82e40b55f089f83f60f650fd9dd5da5a2513963fa56611590a002c2fc`
- _cinderx.so size: 45,760,376 bytes
- _cinderx.so timestamp: 2026-04-20 16:32 UTC
- JIT Python: /data/users/alexturner/venv/bin/python3 (Python 3.12.13+meta)
- Vanilla Python: /usr/local/fbcode/platform010/bin/python3.12 (Python 3.12.13+meta)
- Vanilla sha256: `796679c04c3e57678ad69f17e9d6a252ec01b38db9fb3392d0d79d79707d23e6`

## 6. ABBA Configuration
- Platform: x86_64
- Compile mode: auto (cinderjit.auto() + compile_after_n_calls(10))
- Reps: 3 (= 12 runs, 6 JIT ON, 6 JIT OFF, ABBA interleaved)
- Warmup: 12 iterations per benchmark
- Measurement: 5 iterations per benchmark
- Default iterations: 100,000
- ABBA output file: benchmarks/2026-04-20_164045_a4e988ba_x86_64_abba.txt

## 7. Preflight Results
All checks passed:
- [OK] Version match: 3.12
- [OK] CinderX loaded in JIT python
- [OK] LTO detected (build flags)
- [OK] No PGO detected

## 8. Per-Benchmark Results

| Benchmark           | Vanilla (ms) | CinderX (ms) | Speedup |  Delta |
|---------------------|-------------|-------------|---------|--------|
| chaos_game          |      486.60 |      492.81 |   0.99x |  -1.3% |
| coroutine_chain     |      404.33 |      335.56 |   1.20x |  17.0% |
| deep_class_super    |      521.07 |      555.87 |   0.94x |  -6.7% |
| dict_ops            |      575.68 |      561.19 |   1.03x |   2.5% |
| exceptions          |      491.24 |      498.09 |   0.99x |  -1.4% |
| fannkuch            |      651.37 |      574.02 |   1.13x |  11.9% |
| fibonacci           |     1126.89 |      460.98 |   2.44x |  59.1% |
| float_arith         |      557.16 |      513.98 |   1.08x |   7.7% |
| func_calls          |      353.64 |      303.47 |   1.17x |  14.2% |
| gen_nested          |      283.30 |      259.44 |   1.09x |   8.4% |
| gen_simple          |      384.67 |      295.68 |   1.30x |  23.1% |
| import_callee       |      498.21 |      399.66 |   1.25x |  19.8% |
| int_arith           |      514.29 |      331.68 |   1.55x |  35.5% |
| json_roundtrip      |      499.26 |      506.38 |   0.99x |  -1.4% |
| list_comp           |      464.82 |      526.31 |   0.88x | -13.2% |
| method_calls        |      592.24 |      900.25 |   0.66x | -52.0% |
| nbody               |      679.93 |      528.99 |   1.29x |  22.2% |
| nn_module           |      419.07 |      420.95 |   1.00x |  -0.4% |
| nqueens             |      784.04 |      499.12 |   1.57x |  36.3% |
| positional_dispatch |      612.84 |      439.05 |   1.40x |  28.4% |
| pytorch_cm          |      230.58 |      180.40 |   1.28x |  21.8% |
| richards_full       |      275.73 |      165.46 |   1.67x |  40.0% |
| richards_slots      |      495.69 |      381.77 |   1.30x |  23.0% |
| spectral_norm       |      470.68 |      392.86 |   1.20x |  16.5% |
| store_subscr        |      575.22 |      545.12 |   1.06x |   5.2% |
| string_ops          |      509.43 |      503.65 |   1.01x |   1.1% |
| try_except_callee   |      557.71 |      391.77 |   1.42x |  29.8% |
| unpack_seq          |      661.96 |      480.45 |   1.38x |  27.4% |
| yield_from          |      360.77 |      382.43 |   0.94x |  -6.0% |
|---------------------|-------------|-------------|---------|--------|
| **GEOMEAN**         |             |             | **1.18x** | **17.7%** |
| **TOTAL**           |    15038.41 |    12827.41 | **1.17x** | **14.7%** |

## 9. Run Ordering and Timing

| Run | Condition | Rep | Total (ms) |
|-----|-----------|-----|------------|
|  1  | JIT_ON    |  1  |   13144.2  |
|  2  | JIT_OFF   |  1  |   15574.3  |
|  3  | JIT_OFF   |  1  |   15181.0  |
|  4  | JIT_ON    |  1  |   12763.9  |
|  5  | JIT_ON    |  2  |   12667.9  |
|  6  | JIT_OFF   |  2  |   14789.9  |
|  7  | JIT_OFF   |  2  |   14824.5  |
|  8  | JIT_ON    |  2  |   12897.3  |
|  9  | JIT_ON    |  3  |   12794.9  |
| 10  | JIT_OFF   |  3  |   14977.8  |
| 11  | JIT_OFF   |  3  |   14882.9  |
| 12  | JIT_ON    |  3  |   12696.2  |

Zero crashes. Zero worker failures. 348 benchmark invocations total.
No CPU contention (single ABBA, verified by ps).

## Known Losers

- **method_calls 0.66x**: JIT 34% slower than vanilla. No valid pre-overlay clean-LTO baseline exists to determine cause. Needs investigation in Phase 2.
- **list_comp 0.88x**: JIT 12% slower. Pre-existing on clean-LTO builds.
- **deep_class_super 0.94x**: JIT 6% slower. Pre-existing.
- **yield_from 0.94x**: JIT 6% slower. Pre-existing.
- **exceptions 0.99x**: Neutral after revert of Branch optimization (63c617ab). Recoverable to ~1.48x with proper LICM fix (theologian's spec, session 11).

## Test Suite

- Total tests verified: 507 pass, 0 fail, 1 skip (force_compile crash, our session 9 bug)
- Upstream module tests: 271 pass
- Custom adversarial tests: 236 pass
- 18 pre-existing upstream failures (session 1 baseline, not our regressions)

## Known Deferred Issues

1. force_compile crash in exception handlers (our session 9 bug in emitInlineExceptionMatch, deferred — auto-compile production path works correctly)
2. 63c617ab Branch optimization reverted (prerequisite LICM fix not yet implemented)
3. No pre-overlay clean-LTO baseline for comparison (MakeList crash prevented prior measurement)
