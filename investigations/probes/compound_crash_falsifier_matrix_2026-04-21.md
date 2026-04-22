# Crash Falsifier Matrix — 2026-04-21 / refined 2026-04-22

Empirical evidence on which fixes (78cee3c7 forgetCode + c4e1900c slab) are
necessary to prevent the small-warmup SIGSEGV first reported in sessions
8-10. Refined twice as cells were filled in.

## Workload

`compound_crash_repro.py` (in this directory) — equivalent to the
original session-8/9/10 crash recipe:

```python
cinderjit.auto()
cinderjit.compile_after_n_calls(10)
import benchmark_cinderx as bm
for _ in range(12): bm.bench_deep_class(100)
bm.bench_deep_class(50000)
for _ in range(12): bm.bench_json_roundtrip(100)
bm.bench_json_roundtrip(50000)
```

## Final matrix (5 runs per cell)

| Cell | 78cee3c7 forgetCode | c4e1900c slab | EXIT codes | Verdict |
|------|---------------------|---------------|------------|---------|
| 1    | applied             | applied       | 0,0,0,0,0  | clean   |
| 2    | reverted            | applied       | 139,139,139,139,139 | SIGSEGV 5/5 |
| 3    | applied             | reverted      | 0,0,0,0,0  | clean   |
| 4    | reverted            | reverted      | 139,139,139,139,139 | SIGSEGV 5/5 |

## Refined narrative (supersedes earlier compound claim)

An earlier 2026-04-21 first-pass had only n=1 for cells 2 and 3 and
concluded "both fixes JOINTLY necessary." Filling cells 2 and 3 to n=5
on 2026-04-22 revised that:

- **78cee3c7 (forgetCode patcher cleanup) IS independently necessary
  at n=5** — cell 2 reproduces SIGSEGV 5/5 even with the slab fix
  applied. The bug it fixes is the load-bearing one in default config.
- **c4e1900c (slab arena zero-init) is NOT independently necessary
  at n=5** — cell 3 runs clean 5/5 with only the forgetCode fix.
  Defense-in-depth at this n; ASan caught the corruption pattern but
  it does not surface as a SIGSEGV in default-config production builds
  at this workload.

The earlier "compound" framing was wrong. Single-fix revert (78cee3c7)
IS sufficient to reproduce the crash; slab fix is defensive against
the same memory-reuse pattern under different layouts (different
glibc, alternate ASLR/PIE, ASan-instrumented runs).

## Decision rule

A future agent considering whether to revert either fix in isolation:

- **Revert 78cee3c7:** WILL cause SIGSEGV on the bench_deep_class +
  json_roundtrip workload at n=5. Do not revert without a replacement
  for the type_deopt_patchers_ cleanup.
- **Revert c4e1900c:** Default-config workload runs clean at n=5, but
  ASan-instrumented runs WILL flag use-of-uninitialised-value in
  LoadTypeAttrCache::reset (per session-10 ASan trace). Slab fix is
  defense-in-depth; do not revert without replacing the constructor's
  Py_XDECREF-on-uninitialised-fields pattern.

## Limitations (per pythia 4 critique, 2026-04-22 01:19:08Z)

- n=5 per cell on a single host (devvm), single glibc, single malloc
  tunable, single ASLR/PIE config. Sufficient to OBSERVE the regime,
  not to PROVE the bug's structure across environments.
- Cross-host replication is post-push followup, not yet performed.
- A future single-fix regression on a different host may surface
  differently than this matrix predicts. Treat verdicts as
  "verified on devvm/2026-04-21-build" rather than as universal.

## Why my regression tests missed this earlier

`cinderx/PythonLib/test_cinderx/test_small_warmup_smoke.py` (drafted
2026-04-21 ~15:50 PDT) inlined a `_deep_class_pass` helper instead
of importing `benchmark_cinderx`. Two relevant differences:
1. No `cinderjit.auto()` in the inlined version.
2. The inlined functions live in the test module's globals, not in
   the JIT-warmed benchmark module — the IC + slab allocation pattern
   diverges from the original.

The test rewrite (2026-04-22, subprocess + bench_deep_class) reverts
BOTH fixes for its falsifier shape. Per this refined matrix, reverting
ONLY 78cee3c7 would also be a sufficient falsifier; the test would
catch single-fix regressions on that side. Slab-only revert at n=5
would NOT trip the test in default config.

## Run logs

- `compound_crash_repro_cell1_fix_2026-04-21.txt` — cell 1 (1 run, EXIT=0)
- `compound_crash_repro_cell1_reverify_2026-04-21.txt` — cell 1 (5 runs, all EXIT=0)
- `compound_crash_repro_cell2_forgetcoderevert_2026-04-22.txt` — cell 2 (5 runs, all EXIT=139)
- `compound_crash_repro_cell3_slabrevert_2026-04-21.txt` — cell 3 (1 run, EXIT=0; superseded)
- `compound_crash_repro_cell3_slabrevert_5runs_2026-04-22.txt` — cell 3 (5 runs, all EXIT=0)
- `compound_crash_repro_cell4_bothrevert_2026-04-21.txt` — cell 4 (5 runs, all EXIT=139)

## Reproducing

```bash
TS=$(date +%s)
LOG=/tmp/crash_matrix_$TS.log

# For each cell, edit cinderx/Jit/context.cpp and/or cinderx/Common/slab_arena.h,
# then rebuild and run 5×:
for run in 1 2 3 4 5; do
  echo "=== run $run ===" >> "$LOG"
  source ../venv/bin/activate
  PYTHONPATH=cinderx/PythonLib python3 \
    investigations/probes/compound_crash_repro.py \
    >> "$LOG" 2>&1
  echo "EXIT=$?" >> "$LOG"
done
```

Cell 2 specifically: keep `cinderx/Common/slab_arena.h` at HEAD; in
`cinderx/Jit/context.cpp` replace `Context::forgetCode` body with the
single-line `compiled_codes_.erase(CompilationKey{func});` (preserving
the post-07d938f8 `ThreadedCompileSerialize guard;` line).

Cell 3: keep `cinderx/Jit/context.cpp` at HEAD; revert
`cinderx/Common/slab_arena.h` (remove `<cstring>` include and the
`std::memset(mem, 0, SizeTrait::size());` line).

Cell 4: both above.
