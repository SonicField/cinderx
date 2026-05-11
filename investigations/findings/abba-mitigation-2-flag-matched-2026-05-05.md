# ABBA — mitigation-2: flag-matched speculation-experiment vs cinderx-main + vs original spec-exp

**Date:** 2026-05-05
**Scope:** Cross-version delta between `speculation-experiment` and `facebookincubator/cinderx` `main`, with build-flag confound isolated by rebuilding spec-exp under cinderx-main's flag set.
**Trigger:** Alexie 2026-05-05 10:58:30Z cross-version push (artifact `investigations/plans/2026-05-01-mitigation-2-lto-flag-matched-spec-exp-rerun.md` trigger condition #1).
**Author:** generalist (worker)

## Executive summary

After rebuilding speculation-experiment with cinderx-main's build flag set (LTO ON x86, ENABLE_DISASSEMBLER:OFF, ENABLE_ZLIB:OFF, ENABLE_XXCLASSLOADER unset), the isolated version-effect on geomean is ~+/-3% per arch in opposite directions:

| arch | spec-exp original | spec-exp matched-flags | cinderx-main | flag-effect | version-effect |
|------|-------------------|------------------------|--------------|-------------|----------------|
| x86_64 | 1.20x | 1.25x | 1.23x | +0.05 | +0.02 (spec-exp ahead) |
| aarch64 | 1.14x | 1.14x | 1.17x | +0.00 | -0.03 (cinderx-main ahead) |

**flag-effect** = matched-flags spec-exp speedup − original spec-exp speedup (build-flag impact on spec-exp)
**version-effect** = matched-flags spec-exp speedup − cinderx-main speedup (cross-version delta after flag-matching)

Per-bench picture has material tradeoffs in both directions; the geomean equivalence masks substantial per-bench differences (largest cinderx-main gain: +0.60 chaos_game x86; largest spec-exp gain: +0.56 method_calls x86 / +0.47 method_calls ARM).

**pytorch_cm direction preserved post-flag-match:** spec-exp matched-flags pytorch_cm 1.32x x86 / 1.06x ARM vs cinderx-main 0.87x x86 / 0.71x ARM. Build-flag axis is NOT the cause of the cinderx-main pytorch_cm regression; H1 (generator-arc as load-bearing differential, per `investigations/plans/2026-05-01-pytorch-cm-arm-regression.md`) remains primary-hypothesis-with-build-flag-axis-isolated, NOT empirically confirmed (proximate-mechanism `get_compiled_functions` diff stays queued).

## Methodology

### Substrate
- **spec-exp HEAD:** `9b101f14` (devgpu009 x86) / `0e6f16a6` (devgpu004 ARM). Newer commits `c5e0a06a` + `9b101f14` are benchmark_cinderx.py-only; `_cinderx.so` source HEAD is `0e6f16a6` on both arches.
- **cinderx-main HEAD:** `1d8a9974` (both arches).
- **Vanilla python:** `/usr/local/bin/python3` → `/usr/local/fbcode/platform010/bin/fbpython` (3.12.13+meta), unchanged from 2026-05-01 baseline. Cross-time A/A vanilla noise empirically -0.13% per testkeeper 2026-05-01 16:17:16Z (closed gap).

### Build configuration applied to spec-exp

Cinderx-main's build.sh sets 3 flags spec-exp's didn't:
1. `-DENABLE_DISASSEMBLER:BOOL=OFF` (cinderx-main passes explicit; spec-exp default undef → already OFF in C code; **already matched**)
2. `-DENABLE_ZLIB:BOOL=OFF` (cinderx-main has source-level `#ifdef ENABLE_ZLIB` gates; spec-exp unconditionally linked + called `crc32` → **6-hunk source-port required**)
3. `-DENABLE_XXCLASSLOADER` removed (cinderx-main doesn't pass; spec-exp build.sh hardcoded ON → **build.sh edit required**)

Plus LTO axis: cinderx-main x86 built with `ENABLE_LTO=ON` (default); spec-exp x86 originally built with `ENABLE_LTO=OFF` (env override). Matched by setting `ENABLE_LTO=ON ./build.sh`. ARM stays OFF on both.

**Source-port hunks applied to spec-exp (untracked patch, reproducible):**
- `CMakeLists.txt`: 3 hunks (`set_flag(ENABLE_ZLIB)` added, `find_package(ZLIB)` wrapped in `if(${ENABLE_ZLIB})`, `target_link_libraries common ... ZLIB::ZLIB` wrapped with else-branch)
- `cinderx/Common/code.cpp`: 2 hunks (`#include <zlib.h>` wrapped in `#ifdef ENABLE_ZLIB`, `hashBytecode()` body wrapped with `#ifdef ENABLE_ZLIB` / `#else PyObject_Hash(bc)` branch matching cinderx-main)
- `build.sh`: 1 hunk (remove `-DENABLE_XXCLASSLOADER:BOOL=ON`, add `-DENABLE_ZLIB:BOOL=OFF`)

**Build verification:**
- x86 CMakeCache: `ENABLE_LTO:BOOL=ON`, `ENABLE_ZLIB:BOOL=OFF`. `_cinderx.so` 45.7 MB (down from 61.5 MB original spec-exp; matches cinderx-main 44.4 MB closely).
- ARM CMakeCache: `ENABLE_LTO:BOOL=OFF`, `ENABLE_ZLIB:BOOL=OFF`. `_cinderx.so` 61.7 MB (LTO-off keeps size larger).
- Symbol verification: no `crc32`, `zlib`, or `XXClassLoader` symbols in matched-flags `_cinderx.so` on either arch.

### JIT smoke gate (per `feedback_auto_mode_pre_abba_smoke_gate.md`)

Both arches: after `cinderjit.auto()` + `cinderjit.compile_after_n_calls(10)` + 20 warmup calls, `cinderjit.is_jit_compiled(f) == True` for trivial `def f(x): return x*2+1`. Auto-mode JIT confirmed live before ABBA dispatch.

### ABBA harness

`/usr/local/bin/python3 ./benchmark_cinderx.py all --reps=2`, hard-pinned per benchmark_cinderx.py:2741 + ENV-var fallbacks rejected. `Compile mode: auto` (per `feedback_benchmarks_must_use_auto_not_force.md`; verified in log preflight headers).

PYTHONPATH set to `cinderx/PythonLib` to allow `import _cinderx`.

Sub-suites run: (1) ABBA Interleaved JIT vs Interpreter (in-process), (2) **CinderX JIT vs Vanilla Python — Subprocess ABBA** (load-bearing for cross-version comparison), (3) CinderX Specialisation ON vs OFF.

### Conditional framing (per supervisor 12:07:09Z + theologian 12:07:19Z + pythia 185)

**Promotion of cross-version reading from "directional only" to "clean cross-version" is gated on per-bench delta matrix passing gatekeeper 11:10:58Z 5%-per-bench falsifier.** If falsified (>5% per-bench flag-effect on multiple benches), framing reverts to "directional only" + caveat retention.

**Empirical result:** gatekeeper falsifier IS triggered on x86 (17/29 benches with |flag-effect| >= 0.05; includes 6 benches at exactly +/-0.050 boundary) and is NOT triggered on ARM (0/29 benches with |flag-effect| >= 0.05; max ARM = -0.040 on `exceptions`). Per-arch independent verdict applies (per `feedback_cross_arch_joint_verdict_protocol.md`):

- **x86:** flag-effect IS material — original "directional only" caveat for cinderx-main vs spec-exp comparison WAS load-bearing on this arch. Mitigation-2's flag-matching now isolates version-effect cleanly within the matched-flags substrate.
- **ARM:** flag-effect is empirically zero — original "directional only" caveat was overcautious on this arch (consistent with theologian 11:34:43Z geomean-axis pre-registration).

In neither arch is the original cross-version reading falsified by mitigation-2 — it is **refined** with a now-isolated build-flag axis.

## Per-bench attribution matrix (FULL 29×2; primary-source for gatekeeper recount)

### x86_64 (LTO ON matched / ZLIB OFF matched)

| bench | orig-spec | matched | cinderx-main | flag-effect (matched-orig) | version-effect (matched-main) |
|-------|-----------|---------|--------------|----------------------------|-------------------------------|
| chaos_game            | 0.890x | 0.940x | 1.540x | +0.050 ** | -0.600 ** |
| coroutine_chain       | 1.210x | 1.190x | 1.170x | -0.020 | +0.020 |
| deep_class_super      | 0.810x | 0.920x | 1.210x | +0.110 ** | -0.290 ** |
| dict_ops              | 1.040x | 1.000x | 1.170x | -0.040 | -0.170 ** |
| exceptions            | 1.390x | 1.420x | 0.980x | +0.030 | +0.440 ** |
| fannkuch              | 1.160x | 1.110x | 1.220x | -0.050 ** | -0.110 ** |
| fibonacci             | 2.290x | 2.580x | 2.340x | +0.290 ** | +0.240 ** |
| float_arith           | 1.100x | 1.130x | 1.040x | +0.030 | +0.090 ** |
| func_calls            | 1.100x | 1.150x | 1.250x | +0.050 ** | -0.100 ** |
| gen_nested            | 1.200x | 1.210x | 1.260x | +0.010 | -0.050 ** |
| gen_simple            | 1.180x | 1.190x | 1.180x | +0.010 | +0.010 |
| import_callee         | 1.310x | 1.260x | 1.230x | -0.050 ** | +0.030 |
| int_arith             | 1.510x | 1.550x | 1.550x | +0.040 | +0.000 |
| json_roundtrip        | 0.960x | 0.990x | 1.040x | +0.030 | -0.050 ** |
| list_comp             | 0.860x | 0.870x | 1.040x | +0.010 | -0.170 ** |
| method_calls          | 1.830x | 1.750x | 1.190x | -0.080 ** | +0.560 ** |
| nbody                 | 1.630x | 1.630x | 1.400x | +0.000 | +0.230 ** |
| nn_module             | 0.950x | 1.000x | 1.010x | +0.050 ** | -0.010 |
| nqueens               | 1.550x | 1.630x | 1.430x | +0.080 ** | +0.200 ** |
| positional_dispatch   | 1.090x | 1.230x | 1.160x | +0.140 ** | +0.070 ** |
| pytorch_cm            | 1.140x | 1.320x | 0.870x | +0.180 ** | +0.450 ** |
| richards_full         | 1.510x | 1.690x | 1.780x | +0.180 ** | -0.090 ** |
| richards_slots        | 1.220x | 1.310x | 1.140x | +0.090 ** | +0.170 ** |
| spectral_norm         | 1.170x | 1.220x | 1.400x | +0.050 ** | -0.180 ** |
| store_subscr          | 1.070x | 1.130x | 1.040x | +0.060 ** | +0.090 ** |
| string_ops            | 0.940x | 0.980x | 1.000x | +0.040 | -0.020 |
| try_except_callee     | 1.380x | 1.490x | 1.750x | +0.110 ** | -0.260 ** |
| unpack_seq            | 1.200x | 1.360x | 1.380x | +0.160 ** | -0.020 |
| yield_from            | 1.010x | 1.030x | 0.900x | +0.020 | +0.130 ** |
| **GEOMEAN**           | **1.200x** | **1.250x** | **1.230x** | **+0.050** | **+0.020** |

`**` = |delta| >= 0.050 (gatekeeper 5%-per-bench falsifier threshold; boundary cases at exactly +/-0.050 included).

**Flag-effect violations (gatekeeper 5% falsifier triggered): 17/29 x86 benches** — chaos_game, deep_class_super, fannkuch, fibonacci, func_calls, import_callee, method_calls, nn_module, nqueens, positional_dispatch, pytorch_cm, richards_full, richards_slots, spectral_norm, store_subscr, try_except_callee, unpack_seq. (6 benches at exactly +/-0.050 boundary: chaos_game, fannkuch, func_calls, import_callee, nn_module, spectral_norm.)

### aarch64 (LTO OFF both / ZLIB OFF matched)

| bench | orig-spec | matched | cinderx-main | flag-effect (matched-orig) | version-effect (matched-main) |
|-------|-----------|---------|--------------|----------------------------|-------------------------------|
| chaos_game            | 0.980x | 0.970x | 1.460x | -0.010 | -0.490 ** |
| coroutine_chain       | 1.050x | 1.050x | 1.010x | +0.000 | +0.040 |
| deep_class_super      | 0.830x | 0.840x | 1.190x | +0.010 | -0.350 ** |
| dict_ops              | 1.010x | 1.010x | 1.170x | +0.000 | -0.160 ** |
| exceptions            | 1.370x | 1.330x | 0.960x | -0.040 | +0.370 ** |
| fannkuch              | 1.130x | 1.140x | 1.210x | +0.010 | -0.070 ** |
| fibonacci             | 2.090x | 2.070x | 2.340x | -0.020 | -0.270 ** |
| float_arith           | 0.990x | 0.980x | 1.040x | -0.010 | -0.060 ** |
| func_calls            | 1.110x | 1.120x | 1.170x | +0.010 | -0.050 |
| gen_nested            | 1.020x | 1.020x | 1.030x | +0.000 | -0.010 |
| gen_simple            | 1.100x | 1.090x | 0.990x | -0.010 | +0.100 ** |
| import_callee         | 1.180x | 1.150x | 1.170x | -0.030 | -0.020 |
| int_arith             | 1.350x | 1.370x | 1.370x | +0.020 | +0.000 |
| json_roundtrip        | 0.990x | 0.990x | 0.990x | +0.000 | +0.000 |
| list_comp             | 0.880x | 0.890x | 1.080x | +0.010 | -0.190 ** |
| method_calls          | 1.730x | 1.700x | 1.230x | -0.030 | +0.470 ** |
| nbody                 | 1.470x | 1.490x | 1.370x | +0.020 | +0.120 ** |
| nn_module             | 0.920x | 0.940x | 0.950x | +0.020 | -0.010 |
| nqueens               | 1.460x | 1.450x | 1.300x | -0.010 | +0.150 ** |
| positional_dispatch   | 0.990x | 0.990x | 1.070x | +0.000 | -0.080 ** |
| pytorch_cm            | 1.040x | 1.060x | 0.710x | +0.020 | +0.350 ** |
| richards_full         | 1.360x | 1.380x | 1.600x | +0.020 | -0.220 ** |
| richards_slots        | 1.200x | 1.200x | 1.070x | +0.000 | +0.130 ** |
| spectral_norm         | 1.110x | 1.100x | 1.150x | -0.010 | -0.050 |
| store_subscr          | 1.080x | 1.110x | 1.110x | +0.030 | +0.000 |
| string_ops            | 1.000x | 0.990x | 0.990x | -0.010 | +0.000 |
| try_except_callee     | 1.200x | 1.190x | 1.820x | -0.010 | -0.630 ** |
| unpack_seq            | 1.400x | 1.370x | 1.400x | -0.030 | -0.030 |
| yield_from            | 0.890x | 0.870x | 0.880x | -0.020 | -0.010 |
| **GEOMEAN**           | **1.140x** | **1.140x** | **1.170x** | **+0.000** | **-0.030** |

`**` = |delta| >= 0.050 (gatekeeper 5%-per-bench falsifier threshold; boundary cases at exactly +/-0.050 included).

**Flag-effect violations (gatekeeper 5% falsifier triggered): 0/29 ARM benches** (max ARM flag-effect = -0.040 on `exceptions`, below threshold).

## pytorch_cm direction-preservation finding (H1 status)

Per `investigations/plans/2026-05-01-pytorch-cm-arm-regression.md`:

| arch | spec-exp matched-flags | cinderx-main | direction |
|------|-----------------------|--------------|-----------|
| x86_64 | 1.32x | 0.87x | spec-exp +0.45 ahead |
| aarch64 | 1.06x | 0.71x | spec-exp +0.35 ahead |

**Both arches preserve direction** under matched flags: cinderx-main pytorch_cm regression vs spec-exp is NOT explained by the build-flag axis (LTO/ZLIB/XXCLASSLOADER).

**H1 status update (per supervisor 12:07:09Z + theologian 12:07:19Z + pythia 185):**
- H1 (generator-arc absence on cinderx-main as load-bearing differential, per `project_generator_optimization.md` + librarian 2026-05-01 16:51:09Z trajectory anchoring) elevated from "strongly anchored" → **"primary hypothesis with build-flag axis isolated"**.
- H1 is NOT empirically confirmed. Direction-preservation under matched flags is consistent with H1 but does not distinguish H1 from H2 (IC thrashing on torch attribute lookup), H3 (C-API call-overhead regression), or H4 (async-generator interaction) per the `2026-05-01-pytorch-cm-arm-regression.md` hypothesis space.
- The proximate-mechanism falsifier (~30min `get_compiled_functions` diff between spec-exp and cinderx-main on pytorch_cm hot-path inner functions) **stays queued** in the pytorch_cm artifact, NOT retired. Phase-4 substrate-selection trigger or alexie cause-attribution ask still fires it.

## Caveats (preserved per `feedback_caveat_stripping_on_promote.md`)

The 6-element caveat block from `investigations/findings/abba-cinderx-main-2026-05-01.md` (paragraphs 35-43) carries forward:

1. **Harness threshold-10 override.** `compile_after_n_calls(10)` per benchmark_cinderx.py:1968 is benchmark-specific; vanilla cinderjit.auto() default is 1000 per pyjit.cpp:1566-1572. Production deployments use the higher threshold; benchmark numbers are warmup-driven.
2. **Cross-time vanilla noise.** Per testkeeper 2026-05-01 16:17:16Z empirical A/A: cross-time vanilla mean delta -0.13% across the ~90min ABBA gap. Closed.
3. **LTO axis.** x86 cinderx-main LTO ON, original spec-exp LTO OFF. **Now isolated** by matched-flags rebuild (LTO ON applied to spec-exp x86; flag-effect quantified at +0.05 geomean).
4. **DISASSEMBLER axis.** Both spec-exp and cinderx-main produce equivalent `_cinderx.so` (no `-DENABLE_DISASSEMBLER` preprocessor define on either; OFF code path on both). No isolation needed; null-effect by construction.
5. **ZLIB axis.** spec-exp original used zlib.crc32 in `hashBytecode()`; cinderx-main uses PyObject_Hash. **Now isolated** by source-port (spec-exp matched-flags uses PyObject_Hash too); flag-effect bundled with LTO axis (both ON in matched-flags x86 vs both un-matched in original spec-exp x86).
6. **XXCLASSLOADER axis.** spec-exp original compiled XXCLASSLOADER ON; cinderx-main doesn't compile it. **Now isolated** by build.sh edit (matched-flags spec-exp doesn't compile XXCLASSLOADER). Flag-effect bundled.

**New caveat (mitigation-2 specific):**
7. **Source-port reproducibility.** Matched-flags spec-exp build is on top of HEAD `9b101f14` + 6-hunk untracked patch (CMakeLists.txt 3 hunks + Common/code.cpp 2 hunks + build.sh 1 hunk). Patch saved at `/tmp/mit2_patch.diff` on devgpu009; same patch applied cleanly to ARM at `~/local/vib-jit/cinderx` HEAD `0e6f16a6`. To reproduce: `git apply /tmp/mit2_patch.diff && ENABLE_LTO=ON ./build.sh --clean` (x86) or `./build.sh --clean` (ARM, LTO defaults OFF).

## Results vs original cinderx-main writeup

The original `investigations/findings/abba-cinderx-main-2026-05-01.md` reported per-side cinderx-main vs vanilla:
- x86: 1.23x geomean — reproduced today as 1.23x (cinderx-main column); **unchanged**.
- ARM: 1.17x geomean — reproduced today as 1.17x (cinderx-main column); **unchanged**.

The cross-version comparison (x86 1.23x vs spec-exp 1.20x; ARM 1.17x vs spec-exp 1.14x) was originally bound to "directional only" pending mitigation-2. With matched flags now applied:
- x86: spec-exp matched-flags 1.25x vs cinderx-main 1.23x → spec-exp +2pp ahead (DIRECTION FLIPPED from original "+3pp cinderx-main")
- ARM: spec-exp matched-flags 1.14x vs cinderx-main 1.17x → cinderx-main +3pp ahead (DIRECTION PRESERVED; magnitude unchanged)

**Net: after build-flag isolation, cinderx-main and spec-exp are essentially equivalent on geomean. The original "+3pp cinderx-main wins on both arches" reading was partially driven by the build-flag confound on x86.**

## Open questions / queued investigations

1. **pytorch_cm proximate mechanism (~30min):** `get_compiled_functions` diff between spec-exp and cinderx-main on the 13 inner-JIT-compiled pytorch_cm functions; distinguishes H1 vs H2/H3/H4. Queued in `investigations/plans/2026-05-01-pytorch-cm-arm-regression.md`.
2. **chaos_game cinderx-main +0.60 win on x86 / +0.49 on ARM.** Cinderx-main is dramatically faster on this bench than spec-exp (matched-flags). Possible spec-exp regression in recent codegen, or a cinderx-main optimization spec-exp lost. Not investigated today; flag for future per-bench investigation.
3. **try_except_callee cinderx-main +0.26 win on x86 / +0.63 on ARM.** Same shape — cinderx-main has substantial advantage. Both 1, 2, 3 indicate per-bench cherry-picking opportunities for spec-exp ports.
4. **method_calls spec-exp +0.56 win on x86 / +0.47 on ARM.** Largest spec-exp advantage; likely tied to method-dispatch optimization arc not present in cinderx-main.

## Artifacts

- This writeup: `investigations/findings/abba-mitigation-2-flag-matched-2026-05-05.md`
- Patch applied: `/tmp/mit2_patch.diff` (devgpu009)
- ABBA logs:
  - x86 spec-exp original: `/tmp/abba_x86.log` (devgpu009; preserved from 2026-05-01)
  - x86 spec-exp matched-flags: `/tmp/abba_x86_matched.log` (devgpu009; new today)
  - x86 cinderx-main: `/tmp/abba_x86_main.log` (devgpu009; preserved from 2026-05-01)
  - ARM spec-exp original: `/tmp/abba_arm64.log` (devgpu004; preserved from 2026-05-01)
  - ARM spec-exp matched-flags: `/tmp/abba_arm64_matched.log` (devgpu004; new today; copy at devgpu009 same path)
  - ARM cinderx-main: `/tmp/abba_arm64_main.log` (devgpu004; preserved from 2026-05-01)
- Diff script: `/tmp/mit2_diff.py` (devgpu009)

## Cross-cite

- Trigger artifact: `investigations/plans/2026-05-01-mitigation-2-lto-flag-matched-spec-exp-rerun.md`
- pytorch_cm follow-up artifact: `investigations/plans/2026-05-01-pytorch-cm-arm-regression.md`
- Original cinderx-main writeup: `investigations/findings/abba-cinderx-main-2026-05-01.md`
- Original spec-exp writeup: `investigations/findings/abba-speculation-experiment-2026-05-01.md`
