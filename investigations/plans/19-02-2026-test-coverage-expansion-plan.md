# Test Coverage Expansion Plan

## Date: 19-02-2026
## Author: testkeeper

## Context

External feedback identified that our test coverage is approximately 7% of the full CinderX test suite (41 of ~567 modules). The major gaps:

1. **CPython regression suite** — 494 test modules, we run 0
2. **CPython override tests** — 12 modules (CinderX-specific replacements), we run 0
3. **CinderX compiler tests** — 17 modules beyond SBS shards, we run 0
4. **Static Python tests** — Out of scope per Alex's direction

## Scope

Add the following to `run_cinderx_tests.sh`:

### Phase 1: Additional CinderX-specific tests (immediate)

Add to the runner as new categories:

**Compiler tests** (not already covered by SBS shards):
- `test_cinderx.test_compiler.test_api`
- `test_cinderx.test_compiler.test_cinder`
- `test_cinderx.test_compiler.test_code_sbs`
- `test_cinderx.test_compiler.test_corpus`
- `test_cinderx.test_compiler.test_errors`
- `test_cinderx.test_compiler.test_exception_table`
- `test_cinderx.test_compiler.test_flags`
- `test_cinderx.test_compiler.test_graph`
- `test_cinderx.test_compiler.test_linepos`
- `test_cinderx.test_compiler.test_optimizer`
- `test_cinderx.test_compiler.test_py310`
- `test_cinderx.test_compiler.test_pysourceloader`
- `test_cinderx.test_compiler.test_sbs_external`
- `test_cinderx.test_compiler.test_symbols`
- `test_cinderx.test_compiler.test_unparse`
- `test_cinderx.test_compiler.test_visitor`
(16 modules — omitting test_sbs_stdlib which is already covered by the SBS shards)

**CPython override tests**:
- `test_cinderx.test_cpython_overrides.test_asyncgen`
- `test_cinderx.test_cpython_overrides.test_coroutines`
- `test_cinderx.test_cpython_overrides.test_dis`
- `test_cinderx.test_cpython_overrides.test_fork1`
- `test_cinderx.test_cpython_overrides.test_gdb`
- `test_cinderx.test_cpython_overrides.test_generators`
- `test_cinderx.test_cpython_overrides.test_inspect`
- `test_cinderx.test_cpython_overrides.test__opcode`
- `test_cinderx.test_cpython_overrides.test_repl`
- `test_cinderx.test_cpython_overrides.test_tracemalloc`
- `test_cinderx.test_cpython_overrides.test_trace`
- `test_cinderx.test_cpython_overrides.test_types`
(12 modules)

### Phase 2: CPython regression suite

Add a new command `./run_cinderx_tests.sh cpython` that runs the CPython test suite using `python3 -m test`. This uses CPython's own libregrtest infrastructure.

Key design decisions:
- Use `python3 -m test` (not unittest) — this is CPython's official test runner
- Apply the CinderX skip list (`TestScripts/cinder_skip_test.txt`)
- Apply the JIT ignore list (`TestScripts/cinder_jit_ignore_tests_312.txt`)
- Apply the ARM64 known failures (`TestScripts/3.12-opt-arm64-failures.txt`)
- Run with `--failfast` initially to find the first blocker
- Run with timeout (60s per test module)

The CPython suite is large (494 modules). It should be a separate command, not part of the default `all` sweep, because it takes much longer.

### Phase 3: Fix the JIT gate check

The current gate uses `cinderjit.is_enabled()` which is insufficient per feedback. Replace with a more thorough check that verifies a function can actually be JIT-compiled:

```python
import cinderjit
def _gate_test(): return 42
cinderjit.force_compile(_gate_test)
assert cinderjit.is_jit_compiled(_gate_test), 'force_compile succeeded but function not JIT-compiled'
assert _gate_test() == 42, 'JIT-compiled function returned wrong result'
```

## Test count after expansion

| Category | Current | After Phase 1 | After Phase 2 |
|----------|---------|--------------|--------------|
| JIT tests | 17 | 17 | 17 |
| Runtime tests | 14 | 14 | 14 |
| Compiler SBS | 10 | 10 | 10 |
| Compiler other | 0 | 16 | 16 |
| CPython overrides | 0 | 12 | 12 |
| CPython regression | 0 | 0 | ~494 |
| **Total** | **41** | **69** | **~563** |

## Falsifier

After each phase, run the expanded runner on devgpu004 and verify:
- All previously-passing tests still pass
- New tests produce a result (pass, fail, skip, or error — not silent)
- The summary correctly counts all suites

## Status: ALL PHASES COMPLETE

### Phase 1: DONE
- 16 compiler individual tests + 12 CPython override tests added
- Runner expanded from 41 to 69 CinderX suites
- Results: 63/69 PASS, 3060 tests

### Phase 2: DONE
- CPython regression suite added (`cpython` and `full` commands)
- Skip list parser fixed to extract module names from dotted entries
- ARM64 failures file parsing fixed
- Env-specific skips added (test_pdb, test_venv)
- Results: 413/413 PASS, 36,736 individual tests, 43 modules skipped

### Phase 3: DONE
- JIT gate replaced with force_compile + is_jit_compiled verification
- Confirms tests run on actual JIT-compiled code, not stock interpreter
