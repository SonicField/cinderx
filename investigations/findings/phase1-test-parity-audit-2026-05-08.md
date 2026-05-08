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

### (3) build regression — `build.sh` dropped `-DENABLE_XXCLASSLOADER:BOOL=ON` on migration to direct cmake

**Symptom.** `import xxclassloader` fails under both cinderx-loaded and vanilla venv: `ModuleNotFoundError: No module named 'xxclassloader'`. Blocks `test_cinderjit` + `test_jit_coroutines` test-load (both transitively import `xxclassloader` via `test_compiler.test_static.compile`).

**Empirical chain.**

1. `xxclassloader.c` is part of `static-python` static library (CMakeLists.txt:316). Module-create call `_Ci_CreateXXClassLoaderModule()` at `_cinderx-lib.cpp:1514` is gated by `#ifdef ENABLE_XXCLASSLOADER`.
2. CMakeLists.txt:61 has `set_flag(ENABLE_XXCLASSLOADER)`. The `set_flag` macro (L39-44) only adds `-DENABLE_XXCLASSLOADER` to compiler flags **if cmake is invoked with `-DENABLE_XXCLASSLOADER=ON`**.
3. Current `build.sh` cmake invocation (L126-141) enumerates 13 `-DENABLE_*` flags but omits `-DENABLE_XXCLASSLOADER`. So `_cinderx.so` is built without xxclassloader's module-create call active.
4. Git history:
   - Commit `65ecc9f8` (2026-02-18, Alex Turner) "Add xxclassloader build support, opcode fix, and test runner" added `set_flag(ENABLE_XXCLASSLOADER)` to CMakeLists.txt **and** `set_option("ENABLE_XXCLASSLOADER", True)` to setup.py.
   - Commit `7f0cc6bb` "Rewrite build.sh to use direct cmake instead of pip" migrated build path from pip (which honored `setup.py`'s `set_option`) to direct cmake — but did NOT carry the `-DENABLE_XXCLASSLOADER` flag forward to the new cmake invocation. Regression.

**Phase 1 classification.** NOT a vanilla-fail-too case (xxclassloader is a cinderx-internal C module, not stdlib). This is a build-config regression, remediable in-scope without alexie.

**Fix.** Single-line append to `build.sh` cmake invocation:

```diff
     -DENABLE_USDT:BOOL=ON \
+    -DENABLE_XXCLASSLOADER:BOOL=ON \
     -DENABLE_ZLIB:BOOL=OFF \
```

**Status.** Fix applied to `build.sh` per supervisor 09:33:31Z directive (this commit / pending). Rebuild + verify deferred until parallel testkeeper sharding (09:33Z) returns — avoids invalidating in-flight test runs by rewriting substrate `_cinderx.so`.

**Verify procedure (post-rebuild).**

```bash
./build.sh
PYTHONPATH=cinderx/PythonLib /data/users/alexturner/venv/bin/python -c "import cinderx; cinderx.init(); import xxclassloader; print(xxclassloader)"
# expect: <module 'xxclassloader' from ...>
```

Then re-run `test_cinderjit` + `test_jit_coroutines` test-load gate (no full execution required to verify fix; import-success at module-load is sufficient).

## Audit-tail status

- 32 of 69 test suites reached within 25min time-box. 30 OK + 1 legitimate SKIP (`test_shadowcode` — "shadow code unsupported in 3.12+") + 3 FAIL/ERROR (the 3 inventoried above).
- Remaining 37/69 suites unreached. Per shepard 09:26:56Z directive, testkeeper sharding A/B/C in flight to cover these.
- Phase 1 binding (vanilla-passing must pass under cinderx, no skips) remains open. 3 named items above; up to 37 more unknown pending sharding return.
- `test_shadowcode` legitimate-skip class is documented per cinderx 3.12+ binding; this skip is not a Phase 1 violation.

## References

- `project_cinderx_terminal_goal.md` — Phase 1 / Phase 2 binding.
- `feedback_close_as_upstream_skip_protocol.md` — vanilla-fail-too discrimination (does not apply to (1)/(2) cinderx defects nor (3) build regression; all 3 are cinderx-side).
- Chat decisions: D-1778231606 (testkeeper run dispatch) → D-1778231906 (results) → D-1778231929 (results-validity self-flag) → supervisor 09:26:54Z (root-cause acceptance + sequencing).
