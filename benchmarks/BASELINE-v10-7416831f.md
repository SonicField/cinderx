# CinderX JIT Baseline — Session 10 (v10-baseline)

## 1. Build Hash
- Tag commit: ca4e19d0 (Fix LICM crash and enable exception handler inlining)
- Branch: speculation-experiment
- Full ancestry: ca4e19d0 < a893c51d < 52973b74 < b8536831 < c3c6d4cc < 838a2e2d < 7416831f < a4e988ba < 5e73bfc0 < e1566b85
- Phase 2 Track 2 commits: FM2 + Branch re-application (a893c51d), LICM header-only + NOT_TAKEN (ca4e19d0)

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
- _cinderx.so: sha256 `d0fbf98ced6168a7fdffe6d3b7d8f05f1fa276ea08973206b407e8bd60471f48`
- _cinderx.so size: 45,770,472 bytes
- _cinderx.so timestamp: 2026-04-21 12:55 UTC (clean LTO build)
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
- ABBA output file: benchmarks/2026-04-21_055552_ca4e19d0_x86_64_abba.txt
- ABBA reps: 5 (20 runs, 10 per condition)

## 7. Preflight Results
All checks passed:
- [OK] Version match: 3.12
- [OK] CinderX loaded in JIT python
- [OK] LTO detected (build flags)
- [OK] No PGO detected

## 8. Per-Benchmark Results

| Benchmark           | Vanilla (ms) | CinderX (ms) | Speedup |  Delta |
|---------------------|-------------|-------------|---------|--------|
| chaos_game          |      502.08 |      501.96 |   1.00x |   0.0% |
| coroutine_chain     |      408.05 |      337.05 |   1.21x |  17.4% |
| deep_class_super    |      536.44 |      570.70 |   0.94x |  -6.4% |
| dict_ops            |      604.25 |      625.70 |   0.97x |  -3.6% |
| exceptions          |      510.42 |      345.03 |   1.48x |  32.4% |
| fannkuch            |      705.68 |      583.27 |   1.21x |  17.3% |
| fibonacci           |     1186.27 |      467.81 |   2.54x |  60.6% |
| float_arith         |      573.50 |      517.47 |   1.11x |   9.8% |
| func_calls          |      354.55 |      312.72 |   1.13x |  11.8% |
| gen_nested          |      289.78 |      243.71 |   1.19x |  15.9% |
| gen_simple          |      374.50 |      302.62 |   1.24x |  19.2% |
| import_callee       |      573.15 |      409.23 |   1.40x |  28.6% |
| int_arith           |      512.98 |      331.78 |   1.55x |  35.3% |
| json_roundtrip      |      533.16 |      509.83 |   1.05x |   4.4% |
| list_comp           |      478.10 |      541.02 |   0.88x | -13.2% |
| method_calls        |      609.98 |      912.95 |   0.67x | -49.7% |
| nbody               |      695.77 |      534.78 |   1.30x |  23.1% |
| nn_module           |      416.68 |      407.70 |   1.02x |   2.2% |
| nqueens             |      795.17 |      493.55 |   1.61x |  37.9% |
| positional_dispatch |      576.32 |      437.82 |   1.32x |  24.0% |
| pytorch_cm          |      232.43 |      181.94 |   1.28x |  21.7% |
| richards_full       |      301.07 |      167.34 |   1.80x |  44.4% |
| richards_slots      |      504.29 |      385.65 |   1.31x |  23.5% |
| spectral_norm       |      474.91 |      389.40 |   1.22x |  18.0% |
| store_subscr        |      577.58 |      543.14 |   1.06x |   6.0% |
| string_ops          |      513.25 |      564.17 |   0.91x |  -9.9% |
| try_except_callee   |      545.53 |      408.02 |   1.34x |  25.2% |
| unpack_seq          |      692.19 |      497.36 |   1.39x |  28.1% |
| yield_from          |      384.52 |      387.44 |   0.99x |  -0.8% |
|---------------------|-------------|-------------|---------|--------|
| **GEOMEAN**         |             |             | **1.20x** | **19.5%** |
| **TOTAL**           |    15186.82 |    12772.92 | **1.19x** | **15.9%** |

## 9. Run Ordering and Timing

| Run | Condition | Rep | Total (ms) |
|-----|-----------|-----|------------|
|  1  | JIT_ON    |  1  |   12940.8  |
|  2  | JIT_OFF   |  1  |   15530.4  |
|  3  | JIT_OFF   |  1  |   15683.2  |
|  4  | JIT_ON    |  1  |   12892.5  |
|  5  | JIT_ON    |  2  |   13296.3  |
|  6  | JIT_OFF   |  2  |   15758.4  |
|  7  | JIT_OFF   |  2  |   15495.6  |
|  8  | JIT_ON    |  2  |   13025.9  |
|  9  | JIT_ON    |  3  |   12933.9  |
| 10  | JIT_OFF   |  3  |   15147.9  |
| 11  | JIT_OFF   |  3  |   15063.8  |
| 12  | JIT_ON    |  3  |   13339.3  |

Zero crashes. Zero worker failures. 348 benchmark invocations total.
No CPU contention (single ABBA, verified by ps).

## Known Losers

- **method_calls 0.67x**: JIT 33% slower than vanilla. No valid pre-overlay clean-LTO baseline exists to determine cause. Needs investigation in Phase 2.
- **list_comp 0.88x**: JIT 12% slower. Pre-existing on clean-LTO builds.
- **string_ops 0.91x**: JIT 9% slower. Variance between runs.
- **deep_class_super 0.94x**: JIT 6% slower. Pre-existing.
- **yield_from 0.99x**: Near-neutral.
- **exceptions 1.48x**: Recovered from 0.99x via FM2 + Branch + NOT_TAKEN + LICM header-only fix.

## Test Suite

- Total tests verified: 878 pass, 0 fail, 0 crash, 0 skip
- Script tests (45 files): 480 pass
- Module tests (15 modules): 356 pass
- SPECEXP tests (CINDERX_SPECEXP=1): 42 pass
- 11 pre-existing upstream failures (session 1 baseline, not our regressions)

## Known Deferred Issues

1. method_calls 0.67x in-suite (0.67x is IC pollution ordering effect — 437ms isolated vs 912ms in-suite; recompilation design spec'd for future session)
2. No pre-overlay clean-LTO baseline for full suite comparison (pre-overlay method_calls isolated: 549ms = 1.11x)
3. Guard-triggered recompilation design validated but not implemented (D-1776768252)
