# Performance results — working branch and upstream, Intel and ARM

**Date:** 2026-05-05
**Scope:** Consolidated benchmark results for the working branch (speculation-experiment) and upstream (facebookincubator/cinderx main) on Intel (x86_64) and ARM (aarch64), each measured against the same vanilla Meta-Python baseline.
**Companion document (analysis):** `investigations/findings/spec-exp-to-upstream-optimization-ideas-2026-05-05.md` — what the deltas are explained by and which optimization ideas they correspond to.

## Summary

Geomean speedup (vs vanilla Meta-Python on the same machine):

| Branch | Intel (x86_64) | ARM (aarch64) |
|--------|----------------|----------------|
| Working branch (speculation-experiment) | 1.20x | 1.14x |
| Upstream (cinderx-main) | 1.23x | 1.17x |
| Working branch with build flags matched to upstream | 1.25x | 1.14x |

The third row is a methodology cleanup. The original two rows were measured with each branch's default build flags, which differ in ways unrelated to the JIT optimizations themselves (notably link-time optimization on Intel). Rebuilding the working branch with upstream's build flag set isolates the version-effect from the build-flag-effect; with that isolated, the working branch is 2 percentage points ahead on Intel (1.25x vs 1.23x) and upstream is 3 percentage points ahead on ARM (1.17x vs 1.14x).

In all three rows: the JIT delivers a meaningful per-bench speedup overall, with substantial per-bench variation (some benches the JIT wins by 50%+, some it loses by 10-20%).

## Methodology

**Hardware and Python.** Two machines, identical operating environment per arch.
- Intel (x86_64): devgpu009, 192-core Intel platform.
- ARM (aarch64): devgpu004, NVIDIA Catalina-Grace 144-core platform.
- Vanilla Python on both: `/usr/local/bin/python3` → `fbpython` (Meta-Python 3.12.13+meta), hard-pinned by the harness; no fallbacks accepted.

**Harness.** `benchmark_cinderx.py all --reps=2`, three sub-suites per run:
1. JIT vs Interpreter (in-process ABBA).
2. **JIT vs Vanilla Python (subprocess ABBA).** Load-bearing for cross-side comparison; the geomean numbers in the summary above come from this sub-suite.
3. CinderX Specialisation ON vs OFF (subprocess ABBA).

**JIT compile mode.** `auto` — `cinderjit.auto()` plus `cinderjit.compile_after_n_calls(10)`, then warmup before measurement. Auto mode compiles functions once they cross the threshold-10 call count; this is intentionally lower than the default 1000 because the bench functions are called only ~17 times per measurement and the default would never trigger compilation.

**Workload.** 29-benchmark suite covering JIT hot-paths: integer arithmetic (nbody, nqueens, fibonacci, int_arith, fannkuch), method dispatch (method_calls, richards_full, richards_slots), exception handling (exceptions, try_except_callee), generators and contextmanagers (pytorch_cm, gen_simple, gen_nested, coroutine_chain, yield_from), attribute and slot access (deep_class_super, store_subscr, list_comp), JSON / string operations (json_roundtrip, string_ops, dict_ops), and several more. Each measurement: 50000 iterations after 5000 warmup.

**ABBA discipline.** Per arch, 4 JIT-ON subprocess runs interleaved with 4 JIT-OFF subprocess runs (same workload, vanilla Python on the JIT-OFF runs). Per-bench numbers are mean across the 4 runs per condition.

**Pre-flight checks every run.**
- Python version match.
- CinderX module loadable in the JIT side.
- LTO state detected from build flags (recorded in the run log).
- Compiler info on both sides.
- Compile mode "auto" verified in the run header.

**Build configuration per side (Intel).**
- Working branch (speculation-experiment): default `build.sh` with link-time optimization off. `_cinderx.so` size 61 MB.
- Upstream (cinderx-main): its own `build.sh`, link-time optimization on by default; also turns off ZLIB, DISASSEMBLER, and XXCLASSLOADER at the build level. `_cinderx.so` size 44 MB.
- Working branch with matched flags (methodology cleanup): rebuilt with link-time optimization on, ZLIB conditionalized via a 6-hunk source-port from upstream's CMakeLists.txt + Common/code.cpp, DISASSEMBLER and XXCLASSLOADER off. `_cinderx.so` size 46 MB (close to upstream's 44 MB).

**Build configuration per side (ARM).**
- Working branch (speculation-experiment): default `build.sh`, link-time optimization off (default on aarch64 per build.sh; LTO on aarch64 is unstable). `_cinderx.so` size 62 MB.
- Upstream (cinderx-main): same LTO-off ARM default, plus ZLIB/DISASSEMBLER/XXCLASSLOADER off as on Intel. `_cinderx.so` size 62 MB.
- Working branch with matched flags: ZLIB source-port + ZLIB/DISASSEMBLER/XXCLASSLOADER off (LTO already off). `_cinderx.so` size 62 MB (same scale as upstream's 62 MB).

**Vanilla baseline stability.** Cross-time A/A on vanilla Python (vanilla-vs-vanilla over the ~90-min gap between runs on Intel) showed -0.13% drift — essentially zero. The vanilla baseline is substitutable across the runs.

**JIT-active probe.** For benches whose speedup falls in the 0.95-1.05x band (where "JIT compiled correctly but wasn't faster" is indistinguishable from "silently fell back to interpreter"), an explicit `cinderjit.is_jit_compiled()` check after warmup confirms JIT-active. For the matched-flags working-branch substrate, this probe was run on the 12 in-band benches (5 Intel, 7 ARM) — all 12 confirmed JIT-active.

## Results — working branch (speculation-experiment) vs vanilla

Numbers are CinderX-JIT speedup over vanilla Python. **Bold** rows are bigger than 5% in either direction.

### Intel (x86_64)

| benchmark | vanilla (ms) | JIT (ms) | speedup | Δ% |
|---|---:|---:|---:|---:|
| chaos_game | 494.95 | 557.60 | **0.89x** | -12.7% |
| coroutine_chain | 414.13 | 342.25 | **1.21x** | +17.4% |
| deep_class_super | 535.63 | 663.83 | **0.81x** | -23.9% |
| dict_ops | 609.30 | 588.32 | 1.04x | +3.4% |
| exceptions | 503.52 | 362.25 | **1.39x** | +28.1% |
| fannkuch | 679.00 | 583.68 | **1.16x** | +14.0% |
| fibonacci | 1135.58 | 495.15 | **2.29x** | +56.4% |
| float_arith | 568.36 | 517.80 | **1.10x** | +8.9% |
| func_calls | 353.17 | 321.70 | **1.10x** | +8.9% |
| gen_nested | 309.18 | 258.68 | **1.20x** | +16.3% |
| gen_simple | 359.58 | 303.95 | **1.18x** | +15.5% |
| import_callee | 535.54 | 410.21 | **1.31x** | +23.4% |
| int_arith | 521.97 | 346.72 | **1.51x** | +33.6% |
| json_roundtrip | 502.06 | 523.43 | 0.96x | -4.3% |
| list_comp | 478.46 | 559.35 | **0.86x** | -16.9% |
| method_calls | 675.45 | 368.71 | **1.83x** | +45.4% |
| nbody | 689.05 | 424.02 | **1.63x** | +38.5% |
| nn_module | 419.96 | 441.54 | 0.95x | -5.1% |
| nqueens | 806.70 | 519.24 | **1.55x** | +35.6% |
| positional_dispatch | 564.57 | 517.10 | **1.09x** | +8.4% |
| pytorch_cm | 234.55 | 205.72 | **1.14x** | +12.3% |
| richards_full | 287.41 | 189.95 | **1.51x** | +33.9% |
| richards_slots | 505.65 | 414.76 | **1.22x** | +18.0% |
| spectral_norm | 479.06 | 408.05 | **1.17x** | +14.8% |
| store_subscr | 548.42 | 514.64 | **1.07x** | +6.2% |
| string_ops | 520.60 | 553.28 | **0.94x** | -6.3% |
| try_except_callee | 565.94 | 409.58 | **1.38x** | +27.6% |
| unpack_seq | 660.95 | 549.23 | **1.20x** | +16.9% |
| yield_from | 371.10 | 366.35 | 1.01x | +1.3% |
| **GEOMEAN** | | | **1.20x** | **+19.7%** |
| TOTAL | 15329.86 | 12717.06 | 1.21x | +17.0% |

### ARM (aarch64)

| benchmark | vanilla (ms) | JIT (ms) | speedup | Δ% |
|---|---:|---:|---:|---:|
| chaos_game | 211.39 | 216.00 | 0.98x | -2.2% |
| coroutine_chain | 185.71 | 176.28 | **1.05x** | +5.1% |
| deep_class_super | 226.63 | 274.49 | **0.83x** | -21.1% |
| dict_ops | 282.54 | 280.35 | 1.01x | +0.8% |
| exceptions | 207.69 | 152.09 | **1.37x** | +26.8% |
| fannkuch | 271.37 | 240.17 | **1.13x** | +11.5% |
| fibonacci | 524.73 | 250.89 | **2.09x** | +52.2% |
| float_arith | 248.10 | 250.77 | 0.99x | -1.1% |
| func_calls | 166.34 | 150.29 | **1.11x** | +9.6% |
| gen_nested | 135.12 | 131.84 | 1.02x | +2.4% |
| gen_simple | 178.22 | 161.87 | **1.10x** | +9.2% |
| import_callee | 211.85 | 179.82 | **1.18x** | +15.1% |
| int_arith | 203.73 | 150.95 | **1.35x** | +25.9% |
| json_roundtrip | 191.60 | 192.90 | 0.99x | -0.7% |
| list_comp | 207.87 | 235.68 | **0.88x** | -13.4% |
| method_calls | 288.03 | 166.75 | **1.73x** | +42.1% |
| nbody | 316.82 | 215.64 | **1.47x** | +31.9% |
| nn_module | 179.81 | 195.85 | **0.92x** | -8.9% |
| nqueens | 339.67 | 232.01 | **1.46x** | +31.7% |
| positional_dispatch | 240.80 | 243.50 | 0.99x | -1.1% |
| pytorch_cm | 93.05 | 89.59 | 1.04x | +3.7% |
| richards_full | 122.39 | 89.68 | **1.36x** | +26.7% |
| richards_slots | 222.65 | 185.65 | **1.20x** | +16.6% |
| spectral_norm | 204.80 | 185.14 | **1.11x** | +9.6% |
| store_subscr | 256.23 | 237.02 | **1.08x** | +7.5% |
| string_ops | 247.38 | 247.67 | 1.00x | -0.1% |
| try_except_callee | 276.03 | 229.56 | **1.20x** | +16.8% |
| unpack_seq | 336.32 | 239.52 | **1.40x** | +28.8% |
| yield_from | 193.26 | 216.02 | **0.89x** | -11.8% |
| **GEOMEAN** | | | **1.14x** | **+14.4%** |
| TOTAL | 6770.13 | 5817.96 | 1.16x | +14.1% |

## Results — upstream (cinderx-main) vs vanilla

### Intel (x86_64)

| benchmark | vanilla (ms) | JIT (ms) | speedup | Δ% |
|---|---:|---:|---:|---:|
| chaos_game | 488.73 | 317.01 | **1.54x** | +35.1% |
| coroutine_chain | 423.27 | 362.41 | **1.17x** | +14.4% |
| deep_class_super | 530.78 | 438.76 | **1.21x** | +17.3% |
| dict_ops | 592.29 | 506.23 | **1.17x** | +14.5% |
| exceptions | 504.15 | 512.28 | 0.98x | -1.6% |
| fannkuch | 665.48 | 545.48 | **1.22x** | +18.0% |
| fibonacci | 1150.05 | 492.26 | **2.34x** | +57.2% |
| float_arith | 560.54 | 541.01 | 1.04x | +3.5% |
| func_calls | 349.45 | 280.49 | **1.25x** | +19.7% |
| gen_nested | 308.64 | 245.55 | **1.26x** | +20.4% |
| gen_simple | 360.15 | 305.73 | **1.18x** | +15.1% |
| import_callee | 503.54 | 408.74 | **1.23x** | +18.8% |
| int_arith | 532.37 | 342.93 | **1.55x** | +35.6% |
| json_roundtrip | 534.65 | 515.90 | 1.04x | +3.5% |
| list_comp | 480.07 | 462.69 | 1.04x | +3.6% |
| method_calls | 611.44 | 513.39 | **1.19x** | +16.0% |
| nbody | 697.80 | 499.75 | **1.40x** | +28.4% |
| nn_module | 421.70 | 418.95 | 1.01x | +0.7% |
| nqueens | 803.99 | 562.39 | **1.43x** | +30.0% |
| positional_dispatch | 576.94 | 497.96 | **1.16x** | +13.7% |
| pytorch_cm | 239.40 | 276.57 | **0.87x** | -15.5% |
| richards_full | 281.54 | 157.76 | **1.78x** | +44.0% |
| richards_slots | 496.35 | 435.41 | **1.14x** | +12.3% |
| spectral_norm | 476.70 | 339.86 | **1.40x** | +28.7% |
| store_subscr | 575.90 | 553.85 | 1.04x | +3.8% |
| string_ops | 520.48 | 518.64 | 1.00x | +0.4% |
| try_except_callee | 581.06 | 331.55 | **1.75x** | +42.9% |
| unpack_seq | 674.27 | 490.11 | **1.38x** | +27.3% |
| yield_from | 368.38 | 407.13 | **0.90x** | -10.5% |
| **GEOMEAN** | | | **1.23x** | **+23.3%** |
| TOTAL | 15310.11 | 12280.78 | 1.25x | +19.8% |

### ARM (aarch64)

| benchmark | vanilla (ms) | JIT (ms) | speedup | Δ% |
|---|---:|---:|---:|---:|
| chaos_game | 209.82 | 143.39 | **1.46x** | +31.7% |
| coroutine_chain | 185.30 | 183.36 | 1.01x | +1.0% |
| deep_class_super | 226.44 | 189.88 | **1.19x** | +16.1% |
| dict_ops | 279.85 | 238.92 | **1.17x** | +14.6% |
| exceptions | 205.61 | 214.85 | 0.96x | -4.5% |
| fannkuch | 270.57 | 224.11 | **1.21x** | +17.2% |
| fibonacci | 523.70 | 223.98 | **2.34x** | +57.2% |
| float_arith | 247.40 | 239.02 | 1.04x | +3.4% |
| func_calls | 163.78 | 139.56 | **1.17x** | +14.8% |
| gen_nested | 133.93 | 129.55 | 1.03x | +3.3% |
| gen_simple | 177.27 | 179.14 | 0.99x | -1.1% |
| import_callee | 209.99 | 180.13 | **1.17x** | +14.2% |
| int_arith | 202.01 | 147.07 | **1.37x** | +27.2% |
| json_roundtrip | 190.84 | 192.68 | 0.99x | -1.0% |
| list_comp | 207.01 | 191.83 | **1.08x** | +7.3% |
| method_calls | 286.35 | 232.79 | **1.23x** | +18.7% |
| nbody | 316.90 | 231.69 | **1.37x** | +26.9% |
| nn_module | 178.29 | 187.55 | 0.95x | -5.2% |
| nqueens | 337.60 | 259.78 | **1.30x** | +23.1% |
| positional_dispatch | 238.24 | 222.40 | **1.07x** | +6.6% |
| pytorch_cm | 92.67 | 130.82 | **0.71x** | -41.2% |
| richards_full | 122.57 | 76.55 | **1.60x** | +37.5% |
| richards_slots | 219.78 | 205.68 | **1.07x** | +6.4% |
| spectral_norm | 202.46 | 176.59 | **1.15x** | +12.8% |
| store_subscr | 254.60 | 229.91 | **1.11x** | +9.7% |
| string_ops | 246.10 | 247.60 | 0.99x | -0.6% |
| try_except_callee | 272.77 | 149.86 | **1.82x** | +45.1% |
| unpack_seq | 334.39 | 239.61 | **1.40x** | +28.3% |
| yield_from | 186.35 | 212.22 | **0.88x** | -13.9% |
| **GEOMEAN** | | | **1.17x** | **+16.8%** |
| TOTAL | 6722.60 | 5620.50 | 1.20x | +16.4% |

## Side-by-side comparison — working branch and upstream

Speedups are shown with each branch's default build flags (the two original-flags rows in the summary table). The bottom-row delta within each arch is the per-bench difference between the working branch and upstream; positive means the working branch is faster on that bench, negative means upstream is faster. **Bold** rows have a cross-branch difference of 10 percentage points or more in either direction. See note at bottom about build-flag confound on Intel.

| benchmark | spec-exp Intel | upstream Intel | Δ Intel | spec-exp ARM | upstream ARM | Δ ARM |
|---|---:|---:|---:|---:|---:|---:|
| **chaos_game** | 0.89x | 1.54x | **-0.65** | 0.98x | 1.46x | **-0.48** |
| coroutine_chain | 1.21x | 1.17x | +0.04 | 1.05x | 1.01x | +0.04 |
| **deep_class_super** | 0.81x | 1.21x | **-0.40** | 0.83x | 1.19x | **-0.36** |
| **dict_ops** | 1.04x | 1.17x | **-0.13** | 1.01x | 1.17x | **-0.16** |
| **exceptions** | 1.39x | 0.98x | **+0.41** | 1.37x | 0.96x | **+0.41** |
| fannkuch | 1.16x | 1.22x | -0.06 | 1.13x | 1.21x | -0.08 |
| **fibonacci** | 2.29x | 2.34x | -0.05 | 2.09x | 2.34x | **-0.25** |
| float_arith | 1.10x | 1.04x | +0.06 | 0.99x | 1.04x | -0.05 |
| **func_calls** | 1.10x | 1.25x | **-0.15** | 1.11x | 1.17x | -0.06 |
| gen_nested | 1.20x | 1.26x | -0.06 | 1.02x | 1.03x | -0.01 |
| gen_simple | 1.18x | 1.18x | 0.00 | 1.10x | 0.99x | **+0.11** |
| import_callee | 1.31x | 1.23x | +0.08 | 1.18x | 1.17x | +0.01 |
| int_arith | 1.51x | 1.55x | -0.04 | 1.35x | 1.37x | -0.02 |
| json_roundtrip | 0.96x | 1.04x | -0.08 | 0.99x | 0.99x | 0.00 |
| **list_comp** | 0.86x | 1.04x | **-0.18** | 0.88x | 1.08x | **-0.20** |
| **method_calls** | 1.83x | 1.19x | **+0.64** | 1.73x | 1.23x | **+0.50** |
| **nbody** | 1.63x | 1.40x | **+0.23** | 1.47x | 1.37x | **+0.10** |
| nn_module | 0.95x | 1.01x | -0.06 | 0.92x | 0.95x | -0.03 |
| **nqueens** | 1.55x | 1.43x | **+0.12** | 1.46x | 1.30x | **+0.16** |
| positional_dispatch | 1.09x | 1.16x | -0.07 | 0.99x | 1.07x | -0.08 |
| **pytorch_cm** | 1.14x | 0.87x | **+0.27** | 1.04x | 0.71x | **+0.33** |
| **richards_full** | 1.51x | 1.78x | **-0.27** | 1.36x | 1.60x | **-0.24** |
| **richards_slots** | 1.22x | 1.14x | +0.08 | 1.20x | 1.07x | **+0.13** |
| **spectral_norm** | 1.17x | 1.40x | **-0.23** | 1.11x | 1.15x | -0.04 |
| store_subscr | 1.07x | 1.04x | +0.03 | 1.08x | 1.11x | -0.03 |
| string_ops | 0.94x | 1.00x | -0.06 | 1.00x | 0.99x | +0.01 |
| **try_except_callee** | 1.38x | 1.75x | **-0.37** | 1.20x | 1.82x | **-0.62** |
| unpack_seq | 1.20x | 1.38x | **-0.18** | 1.40x | 1.40x | 0.00 |
| **yield_from** | 1.01x | 0.90x | **+0.11** | 0.89x | 0.88x | +0.01 |
| **GEOMEAN** | **1.20x** | **1.23x** | **-0.03** | **1.14x** | **1.17x** | **-0.03** |

Pattern from the side-by-side: the geomean cross-branch delta is small (-3% on each arch, with each arch showing the same direction in this default-flags view), but per-bench tradeoffs are substantial in both directions and largely consistent across architectures. Benches where the working branch is meaningfully ahead on both arches: method_calls, exceptions, pytorch_cm, nbody, nqueens. Benches where upstream is meaningfully ahead on both arches: chaos_game, deep_class_super, list_comp, dict_ops, try_except_callee, richards_full.

**Build-flag confound (important for the Intel column).** The Intel side of this table mixes a real version-effect with a build-flag-effect — link-time optimization is on for upstream and off for the working branch in the default-flags rows above. The matched-flags addendum below isolates the version-effect: with build flags matched on Intel, the working branch geomean rises from 1.20x to 1.25x, and the cross-branch direction flips (working branch +0.02 vs upstream's 1.23x rather than the upstream +0.03 the default-flags view shows). On ARM the build-flag effect is empirically zero, so the ARM column above already shows the clean version-effect.

**Cross-document note on pytorch_cm.** The companion optimization-ideas writeup cites the pytorch_cm cross-branch delta at +45% Intel / +35% ARM. That cite uses the matched-flags substrate (working branch rebuilt with upstream's flags), where the per-bench delta is larger because the build-flag confound is removed. The +0.27 Intel / +0.33 ARM values in this side-by-side table are on the default-flags substrate. Both numbers are correct for their substrate; the matched-flags numbers are the load-bearing ones for any "what does the version-effect actually look like" reading.

**Bold-threshold sensitivity.** The bold-name convention (rows with a cross-branch difference of 10 percentage points or more in either arch) is a categorization heuristic, not a stable winner-loser label. Rows close to the threshold (fannkuch -0.06/-0.08, gen_simple 0.00/+0.11, richards_slots +0.08/+0.13) can flip categorization on small re-measurement; the bold-name marker is most stable above ±15 percentage points.

## Results — working branch with build flags matched to upstream (methodology cleanup)

This row was added because the original two branch results were measured under different build configurations on Intel (link-time optimization on for upstream, off for working branch, plus three other flag deltas). To separate "version-effect" from "build-flag-effect," the working branch was rebuilt with upstream's flag set and the same benchmark harness re-run.

The flag-isolation result gives a clean cross-branch comparison on the same build substrate.

### Intel (x86_64), matched flags

| metric | value |
|---|---|
| GEOMEAN vs vanilla | 1.25x (+24.9%) |
| TOTAL vs vanilla | 1.26x (+20.4%) |
| Cross-branch delta vs upstream (1.23x) | working branch +0.02 (2 percentage points ahead) |
| Build-flag effect on Intel (vs working-branch original 1.20x) | +0.05 (link-time optimization is the load-bearing flag) |

17 of 29 Intel benches shifted by 5% or more under matched flags vs the working-branch original — meaning the original "directional only" Intel caveat between the two branches was load-bearing; flag-matching dissolves it.

### ARM (aarch64), matched flags

| metric | value |
|---|---|
| GEOMEAN vs vanilla | 1.14x (+14.3%) |
| TOTAL vs vanilla | 1.16x (+13.9%) |
| Cross-branch delta vs upstream (1.17x) | upstream +0.03 (3 percentage points ahead) |
| Build-flag effect on ARM (vs working-branch original 1.14x) | +0.00 (essentially zero) |

0 of 29 ARM benches shifted by 5% or more under matched flags vs the working-branch original — meaning the source-port (ZLIB conditional, etc.) is benchmark-neutral on the LTO-off architecture; the cross-branch comparison on ARM was already clean.

### Per-bench attribution (full 29 × 2 matrix)

The full per-bench matrix isolating flag-effect from version-effect is in the companion artifact:
- `investigations/findings/abba-mitigation-2-flag-matched-2026-05-05.md` — primary-source per-bench matrix with flag-effect and version-effect columns.

## Caveats

1. **Cross-time vanilla noise.** Empirically -0.13% across the ~90-minute gap between the original two branch runs (vanilla A/A test, Intel). The vanilla baseline is substitutable across runs; cross-side comparisons are not noise-driven at the geomean level.
2. **Harness threshold-10 override.** The benchmark harness sets `compile_after_n_calls(10)` because the bench functions are called only ~17 times per measurement; the default 1000 would never compile. Production deployments use the higher default; the benchmark numbers measure warmup-driven JIT behavior, not steady-state production behavior.
3. **Build-flag deltas.** The original two branch results were measured under different build configurations on Intel (LTO on for upstream, off for working branch; ZLIB unconditionally linked on working branch but off on upstream; XXCLASSLOADER on working branch but off on upstream; DISASSEMBLER off on both via different mechanisms). The matched-flags row above isolates this. ARM had the same flag-set delta but LTO-off on both arches and the source-level delta is benchmark-neutral on ARM.
4. **JIT-active falsification on borderline benches.** For benches in the 0.95-1.05x band, an explicit `is_jit_compiled()` probe confirms the JIT path was active — none of the borderline benches silently fell back to interpreter.
5. **ARM matched-flags substrate validation.** The matched-flags row's ARM side was build-verified (CMakeCache + symbol scan) but the second-test on pytorch_cm codegen was Intel-only; the underlying optimization pass is architecture-independent so the divergence should reproduce on ARM, but a separate ARM-side codegen probe was not run.
6. **Geomean masks per-bench tradeoffs.** The geomean numbers are useful as a single-number summary but obscure substantial per-bench variation in both directions. The per-bench tables above and the per-bench attribution matrix in the companion artifact carry the load-bearing detail.

## Backing artifacts

- Per-bench attribution matrix with flag-effect / version-effect columns: `investigations/findings/abba-mitigation-2-flag-matched-2026-05-05.md`
- Optimization ideas analysis (companion document): `investigations/findings/spec-exp-to-upstream-optimization-ideas-2026-05-05.md`
- pytorch_cm hypothesis space and rooting: `investigations/plans/2026-05-01-pytorch-cm-arm-regression.md`
- Original per-side results (predecessors to this consolidated document):
  - Working branch: `investigations/findings/abba-speculation-experiment-2026-05-01.md`
  - Upstream: `investigations/findings/abba-cinderx-main-2026-05-01.md`
- Raw ABBA logs (devgpu009 + devgpu004):
  - `/tmp/abba_x86.log` (working branch Intel original)
  - `/tmp/abba_arm64.log` (working branch ARM original)
  - `/tmp/abba_x86_main.log` (upstream Intel)
  - `/tmp/abba_arm64_main.log` (upstream ARM)
  - `/tmp/abba_x86_matched.log` (working branch Intel matched-flags)
  - `/tmp/abba_arm64_matched.log` (working branch ARM matched-flags)
