# Phase 1 cinderx test-parity audit — 2026-05-08

Per `project_cinderx_terminal_goal.md` Phase 1 binding: vanilla-CPython-passing tests must pass under cinderx (no skips). This file inventories defects + build-gaps surfaced by the first audit run since 2026-05-01 (substrate flat ~6d 21h prior to 2026-05-08 09:13Z).

## Audit context

- Substrate: `/data/users/alexturner/cinderx` HEAD `e8665f37` (archive commit; substrate-code identical to `9b101f14` 2026-05-01).
- Vanilla baseline: `/data/users/alexturner/venv/bin/python` (Meta-Python 3.12.13, no cinderx PYTHONPATH).
- Runner: canonical `./run_cinderx_tests.sh` (CINDERX_ROOT default = script dir = substrate). Verified vs investigations/scripts/run_cinderx_tests.sh which hardcodes `cinderx_dev` (a different worktree); **only the root-level script is canonical**.
- Run timestamp: 2026-05-08T09:13:48Z (testkeeper) — 32 of 69 suites reached within 25min timeout.
- Discrimination basis (vanilla-passing vs vanilla-failing-too): generalist 09:26:25Z empirical baseline.

## Inventory

### (1) cinderx defect — `code.cpp:211` "Cannot re-initialize code extra index" (singleton violation)

**Symptom.** When vanilla CPython unittest spawns subprocesses that re-call `cinderx.init()`, the second-and-onward calls hit `code.cpp:211` "Cannot re-initialize code extra index". Singleton-init guard missing or wrong-scoped.

**Surfaced by.** testkeeper 09:12:43Z item 2 (`test_cinderx.test_immortalize` cycle).

**Vanilla baseline.** Not applicable (vanilla doesn't load cinderx). Pure cinderx defect.

**Phase 1 classification.** Confirmed cinderx defect; Phase 1 binding requires fix.

**Fix scope.** Architectural — likely needs idempotent `cinderx.init()` or per-process guard. Defers to alexie-engagement per supervisor 09:26:54Z.

### (2) cinderx defect — `cinderx -X jit-all -mcinderx.compiler --static` `OverflowError` in `re._parser.getwidth`

**Symptom.** `test_jit_preload::test_func_destroyed_during_preload` runs subprocess `python -X jit-all -X jit-batch-compile-workers=4 -L -mcinderx.compiler --static <helper>`. The subprocess fails at module-import inside `cinderx.compiler.__main__` line 25:

```python
coding_re: Pattern = re.compile(rb"^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)")
```

Compile path goes through `re/_parser.py:202` `getwidth()` → `OverflowError: Python int too large to convert to C ssize_t`.

**Vanilla baseline.** Same regex compiles fine under `/data/users/alexturner/venv/bin/python` — no overflow:

```bash
/data/users/alexturner/venv/bin/python -c "import re; re.compile(rb'^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)')"
# → OK
```

**Phase 1 classification.** Confirmed cinderx defect. Triggered only under cinderx + `-X jit-all` + cinderx.compiler `--static` mode. Vanilla regex semantics intact; cinderx JIT subprocess introduces something that breaks `re._parser` int sizing.

**Fix scope.** Substrate-tractable; isolatable to cinderx JIT/static-compiler path. Next item per supervisor 09:26:54Z sequencing.

**Failure log.** `/tmp/cinderx_fail_test_jit_preload.log` (full trace).

### (3) `import xxclassloader` failure — original build.sh-regression diagnosis FALSIFIED; root cause unidentified within time-box; rebuild empirically resolved.

**Symptom (09:13:48Z testkeeper).** `import xxclassloader` failed under canonical `run_cinderx_tests.sh` against substrate: `ModuleNotFoundError: No module named 'xxclassloader'`. Blocked `test_cinderjit` + `test_jit_coroutines` test-load (both transitively import `xxclassloader` via `test_compiler.test_static.compile`).

**Initial diagnosis (generalist 09:33:03Z) — FALSIFIED.** Initial framing was "build.sh dropped `-DENABLE_XXCLASSLOADER:BOOL=ON` on commit `7f0cc6bb` direct-cmake migration." Librarian 09:39:55Z primary-source verification + supervisor 09:40:29Z acceptance:

- `git log -S "DENABLE_XXCLASSLOADER" -- build.sh` returns ONLY commit `7f0cc6bb`, which **added** the flag. Flag has never been dropped.
- `git show HEAD~1:build.sh` line 139 shows `-DENABLE_XXCLASSLOADER:BOOL=ON` was already present before any of generalist's commits.
- `nm scratch/build-x86_64/_cinderx.so | grep CreateXX` returned the symbol on the pre-rebuild .so (verified separately on `_cinderx.so.b1_postfix_renamed` Apr 22 backup); symbol was always exported.
- `llvm-nm scratch/build-x86_64-pydebug/CMakeFiles/_cinderx.dir/cinderx/_cinderx-lib.cpp.o` (pre-rebuild Apr 23 mtime) shows `U _Ci_CreateXXClassLoaderModule` — call site **was already** compiled in old object file. ENABLE_XXCLASSLOADER macro was active on prior builds.

The build-config was correct already. Initial "regression" framing was wrong.

**What actually happened.** `./build.sh` at 09:38Z rebuilt + reinstalled `cinderx/PythonLib/_cinderx.so` (the file the canonical runner loads via venv). The rebuild empirically resolved `import xxclassloader`. Verified post-rebuild:

- `test_cinderjit`: 172 pass / 0 fail / 0 error / 0 skip
- `test_jit_coroutines`: 23 pass / 0 fail / 0 error / 0 skip

**Root cause of original failure — UNIDENTIFIED within 30min time-box (supervisor 09:50:03Z accepted (B)-deeper-RCA as low-yield since pre-rebuild state was overwritten).** Empirically working state restored. Candidates not falsified:

- (a) Pre-rebuild `cinderx/PythonLib/_cinderx.so` was a stale or differently-built file relative to `scratch/build-x86_64/_cinderx.so`. Rebuild reconciled the install copy with the build copy. Cannot directly verify (overwritten).
- (b) `__pycache__` stale `.pyc` holding wrong binding. Not directly verified.
- (c) Test-load ordering / venv state issue that resolved on re-run.

**Phase 1 classification.** NOT a vanilla-fail-too case (xxclassloader is a cinderx-internal C module, not stdlib). NOT a build-config regression (falsified). Empirical-only: rebuild fixes the symptom; investigate root cause if recurrence.

**Status.** Empirically resolved by `./build.sh` (the rebuild itself, not any code change in commit `5380a997` — that commit's build.sh edit was a no-op duplicate of `-DENABLE_ZLIB:BOOL=OFF` and is reverted in the corrective commit alongside this finding update). 2 of 3 original Phase 1 FAILs cleared (`test_cinderjit` + `test_jit_coroutines`); `test_jit_preload` cinderx-defect (item 2) remains.

**Process self-flag.** This finding originally shipped (commit `5380a997`) with an inaccurate "regression on commit `7f0cc6bb`" mechanism cited in the commit message. Librarian primary-source verification falsified the cite same-turn. Future build-flag claims must be verified against `git log -S` + `git show HEAD~1:` before being framed as regressions. Pattern: import-trust-verify (`feedback_import_trust_verify_umbrella.md`) — third instance in this substrate cycle.

## Audit-tail status

- 32 of 69 test suites reached within 25min time-box. 30 OK + 1 legitimate SKIP (`test_shadowcode` — "shadow code unsupported in 3.12+") + 3 FAIL/ERROR (the 3 inventoried above).
- Remaining 37/69 suites unreached. Per shepard 09:26:56Z directive, testkeeper sharding A/B/C in flight to cover these.
- Phase 1 binding (vanilla-passing must pass under cinderx, no skips) remains open. 3 named items above; up to 37 more unknown pending sharding return.
- `test_shadowcode` legitimate-skip class is documented per cinderx 3.12+ binding; this skip is not a Phase 1 violation.

## References

- `project_cinderx_terminal_goal.md` — Phase 1 / Phase 2 binding.
- `feedback_close_as_upstream_skip_protocol.md` — vanilla-fail-too discrimination (does not apply to (1)/(2) cinderx defects nor (3) build regression; all 3 are cinderx-side).
- Chat decisions: D-1778231606 (testkeeper run dispatch) → D-1778231906 (results) → D-1778231929 (results-validity self-flag) → supervisor 09:26:54Z (root-cause acceptance + sequencing).
