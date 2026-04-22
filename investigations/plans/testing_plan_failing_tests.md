# Testing Plan: Zero Testing Gaps for Failing-Test Fixes

**Author:** testkeeper
**Date:** 2026-04-22
**Driver:** alexie (via vib-jit.chat 05:17:37Z)
**Companion to:** investigations/plans/triage_plan_failing_tests.md (theologian, 2026-04-22)
**Source of failure list:** theologian's plan, derived from testkeeper 05:12:46Z chat post.

## Scope

Specifies the testing requirements for every fix in theologian's triage plan.
Covers regression tests, coverage gaps, falsifier-proof protocol, and
gate-(j) compatibility. Excludes the bench_deep_class SIGSEGV (already
covered by `cinderx/PythonLib/test_cinderx/test_small_warmup_smoke.py` in
the current 11-commit bundle).

## Cross-cutting rules

These bind every fix landing under theologian's plan:

1. **Regression test in same commit as fix.** No fix-then-test split. The
   commit that fixes bug X MUST add the test that catches a regression of
   bug X.
2. **Falsifier-proven.** Before the regression test commit lands, testkeeper
   MUST observe the test FAIL on the bug-present tree AND PASS on the
   bug-fixed tree. Captured raw output for both. No exceptions.
3. **Gate-(j) compatibility (alexie 05:15:12Z binding).** Each fix commit
   MUST NOT increase failing or skipped test counts in
   `./run_cinderx_tests.sh full` versus its parent. Adding a new
   regression test that passes is fine; adding a new test that skips is
   NOT fine (counts as skip increase).
4. **Same-suite-as-failure.** The regression test lives in the same suite
   that originally caught (or would have caught) the bug. New tests for
   `test_jit_preload` failures go in the `test_jit_preload` module, not
   in a new module. Discoverability before novelty.
5. **No xfail / skip as 'fix'.** A bug is fixed only when the test passes
   without xfail / skip / @unittest.expectedFailure. If a deferral is
   needed, it's a separate documented decision, not a quiet test marker.
6. **Source-attribution discipline.** Every claim about a test's behavior
   must cite the same-turn tool call (Read of file, Bash run of test,
   chat-record cross-reference). Per memory
   project_recursive_policy_collapse_pattern.md + 5 catches in this
   work-cycle.

## Per-bug testing requirements

Mirrors theologian's plan structure; this section adds the testing-side
spec her plan elides.

### Group A — Process-killing failures

#### A1. test_jit_preload.test_func_destroyed_during_preload

**Existing test:** `cinderx/PythonLib/test_cinderx/test_jit_preload.py:test_func_destroyed_during_preload`
asserts subprocess returncode 0; currently asserts fail (returncode=1).

**Fix-time test requirements:**
- The existing test is the regression test. It already asserts the
  invariant. No new test needed; the existing assertion becomes
  passing.
- If theologian's hypothesis is wrong and the bug is upstream
  (CPython 3.12.13 OverflowError without cinderx), the test must
  remain in tree as `@unittest.skip("upstream OverflowError, see
  tracker entry for X")` — NOT a quiet skip. The skip annotation
  makes the deferral visible in the gate-(j) skip count.
- **Coverage gap to close:** add a sibling test
  `test_func_destroyed_during_preload_minimal_repro` that exercises
  the same code path with a smaller repro than the current test —
  if the original test falls into upstream-skip, the minimal repro
  may avoid the upstream trigger AND still catch the JIT-side bug.

**Falsifier-proof cycle (testkeeper):**
- Before fix lands: rerun test on bug-present tree → confirm
  returncode=1 still observed (5/5).
- After fix lands: rerun on bug-fixed tree → returncode=0 (5/5).

### Group B — Reproducible test assertion failures

#### B1. test_jit_support_instrumentation cluster (8F + 8E)

**Existing tests:** `cinderx/PythonLib/test_cinderx/test_jit_support_instrumentation.py`
contains 16 failing methods spanning JitMonitoringIntegrationTest +
JitSetProfileIntegrationTest + JitSetTraceIntegrationTest +
JitCombinedTracingIntegrationTest classes.

**Fix-time test requirements:**
- All 16 methods are pre-existing regression tests. They pass when
  the bug is fixed.
- **Coverage gap to close:** the 16 methods are the symptom-set;
  per theologian's B1.0 step, classify root causes. For EACH
  distinct root cause class (B1a, B1b, ...), add ONE focused
  regression test that exercises ONLY that root cause path. The
  16 broad tests catch any regression; the focused tests pinpoint
  which root cause class is regressing.
- **Coverage gap to add:** verify whether the JIT does the right
  thing under sys.setprofile with a tracer that itself raises an
  exception (currently untested per Read of test file). This is an
  adjacent surface the existing tests don't cover.

**Falsifier-proof cycle:**
- Per fix commit, rerun the relevant subset of 16 tests on
  bug-present and bug-fixed trees.
- If a fix splits the cluster (B1a fix doesn't fix B1b), document
  the partial-fix in the plan adaptation log; the gate-(j) failing
  count must still decrease, not stay flat.

#### B2. test_jit_perf_map.test_forked_pid_map

**Existing test:** `cinderx/PythonLib/test_cinderx/test_jit_perf_map.py:test_forked_pid_map`
asserts the fork's perf-map contains parent function names.

**Fix-time test requirements:**
- Existing test is the regression test.
- **Coverage gap to close:** add a multi-fork test
  (`test_double_forked_pid_map` or similar) that forks twice;
  current test covers single-fork only. Multi-fork is a plausible
  adjacent regression surface.

**Falsifier-proof cycle:** same shape — verify FAIL on bug-present,
PASS on bug-fixed.

#### B3. test_cpython_overrides.test__opcode (DUP_TOP_TWO, JUMP_IF_TRUE_OR_POP)

**Existing test:** `cinderx/PythonLib/test_cinderx/test_cpython_overrides/test__opcode.py`
asserts 3.10/3.11 opcodes that don't exist in 3.12.

**Fix-time test requirements (depends on alexie's answer to theologian's
open question 2):**
- If patching the test is acceptable: the patched test IS the
  regression test. Add a comment citing 3.12 opcode set.
- If JIT must preserve removed opcodes: the existing test stands;
  the fix must satisfy it.
- **Coverage gap to close:** if patched, add a positive test that
  asserts the EXPECTED 3.12 opcode set (`POP_JUMP_FORWARD_IF_TRUE`,
  etc.) is present and JIT-handled. Otherwise we silently lose
  signal on opcode-table changes.

**Falsifier-proof cycle:** rerun the patched / unpatched test on
bug-present and bug-fixed trees.

### Group C — Environment / stale failures (5 stdlib tests)

#### C1.x. test_cmd_line / test_urllib / test_urllib2 / test_uu / test_zipfile

**Existing tests:** CPython stdlib, run via `python3 -m test test_X`. Not
under cinderx ownership; treated as integration probes.

**Fix-time test requirements (depends on triage outcome per theologian C1):**
- If close-as-upstream (test fails under vanilla 3.12.13 same env):
  the gate-(j) skip-count tradeoff is NOT acceptable to silently
  skip these via the suite runner. Either:
  - (a) Patch `cinderx/TestScripts/cinder_skip_test.txt` to add
    these to the documented-skip list (with a tracker-entry citation
    for each). This INCREASES skipped count, which BLOCKS gate-(j).
    Therefore...
  - (b) Patch the underlying environment issue (the cleaner option).
  - The team will need alexie's call: gate-(j) prohibits skip-count
    increase, so close-as-upstream cannot land without either fixing
    the env or alexie carving out an exception.
- If JIT codegen bug: regression test added to `test_cinderx` OR the
  failing module patched and committed upstream-style.
- **Coverage gap to close:** for each stdlib failure, add a
  cinderx-side smoke test that exercises the same code path with a
  smaller fixture. This catches future regressions even if the
  upstream test changes.
  - **Sub-step (per gatekeeper 05:24:47Z falsifier-validity review):**
    verify each smoke test actually hits the originally-failing
    function/line set via coverage.py (or strace where coverage.py
    doesn't apply). Smoke-test-as-coverage without that verification
    is structural reasoning, not falsifier evidence — the test could
    pass while the real path remains unexercised. Capture coverage
    delta between baseline and smoke-test runs; require ≥1 newly-hit
    line on the bug-relevant function.

**Falsifier-proof cycle:** rerun each stdlib module on bug-present and
bug-fixed trees.

### Group D — Flakes

#### D1. test_docxmlrpc parallel-run flake (~17%)

**Existing test:** `python3 -m test test_docxmlrpc` (CPython stdlib).
Passes 5/5 in isolation, fails ~1/6 in full-suite parallel-run.

**Fix-time test requirements:**
- If port-collision hypothesis confirmed and patchable upstream:
  cinderx applies the patch in a CPython override. The override IS
  the regression test (replaces the broken stdlib module).
- If hypothesis falsified: re-classify per theologian's plan and
  re-spec.
- **Coverage gap to close:** add a meta-test that runs
  `test_docxmlrpc` in 10-parallel-shell-mode, asserts 0/10
  failures. This pins down whether the fix works at the same
  concurrency level the original failure surfaced at.

**Falsifier-proof cycle:**
- Before fix: 1/6 or higher fail rate at HEAD full-suite (already
  observed).
- After fix: 0/20 fail rate across N parallel runs.
  - **Statistical justification (per gatekeeper 05:24:47Z):** at the
    observed ~17% baseline rate, P(0/20 by luck) = (1-0.17)^20 ≈
    2.4%. 20 runs is therefore sufficient evidence at the 95%
    confidence level for fix confirmation. 5 runs would give
    P(0/5) ≈ 39% — insufficient. 100 runs would be wasteful.

## Coverage gaps by category

### Currently unexercised paths (testkeeper-known)

- **forgetCode + concurrent type modification:** the in-bundle
  test_small_warmup_smoke.py covers the compound-revert scenario
  but does NOT cover concurrent-type-modification under
  multithreaded JIT compile (config.h:multithreaded_compile_test
  defaults false, so this path is unreachable in default config —
  but if config flips, the test surface needs to expand).
- **GuardType version_tag=0 path:** unreachable in default config
  per investigations/probes/aba_reachability_probe.py. If
  emit_type_annotation_guards or multithreaded_compile_test flips,
  test_guard_type_version_tag.py inline-op sentinels need to be
  upgraded to falsifiers (currently honest about being non-falsifying
  per theologian D-1776812737 STALE-CHECK marker).
- **slab arena UAF (c4e1900c):** ASan-detectable but NOT exercised
  by default-config tests. The team currently has no ASan-specific
  CI lane. Coverage gap = real; closing it requires ASan build +
  test wiring (out of this plan's scope; tracker followup).

### Adjacent failures to anticipate

For each fix, anticipate ONE adjacent failure surface and add a
preemptive regression test:
- A1 fix → add minimal-repro test (per A1 above)
- B1 fix → add tracer-raises-exception adjacent test (per B1 above)
- B2 fix → add multi-fork test (per B2 above)
- B3 fix → add positive 3.12-opcode-set test (per B3 above)
- C1.x fix → add cinderx-side smoke test for each (per C1 above)
- D1 fix → add 10-parallel-shell meta-test (per D1 above)

## Test infrastructure requirements

### Gate-(j) integration (alexie 05:15:12Z)

- `./run_cinderx_tests.sh full` is the canonical gate. Every fix
  commit must pass it without increasing fail/skip count.
- New regression tests added by fix commits must PASS in the same
  invocation; if they fail at land time, the commit is incomplete.
- Skip markers (`@unittest.skip`, `@unittest.skipUnless`) on new
  tests count toward the skip-count gate. Use them only with
  documented justification; default to no-skip.

### CI surface (open question)

- Currently no automated CI runs `./run_cinderx_tests.sh full` per
  commit. The gate is enforced manually by testkeeper at push time.
- For the fix workstream's regression tests to provide ongoing
  protection, CI integration is needed. Out of this plan's scope;
  tracker followup.

### ASan lane (open question)

- Some fixes (slab arena UAF class, forgetCode UAF class) are
  ASan-detectable but NOT default-config-fatal. Without an ASan CI
  lane, regressions in these classes go undetected until production
  load.
- Tracker followup item; not in this plan.

## Verification protocol per fix

For every fix commit landing under theologian's plan:

1. **testkeeper observes test FAIL on bug-present tree.** Capture
   raw output, exit code, command. (If the bug is reproducible only
   under specific conditions, capture those.)
2. **generalist applies fix, commits with regression test in same
   commit.**
3. **testkeeper observes test PASS on bug-fixed tree.** Same shape
   as step 1 — raw output, exit code, command.
4. **testkeeper runs `./run_cinderx_tests.sh full` post-commit.**
   Count failing + skipped vs prior commit. Both must be ≤ prior.
   If either increases, BLOCK and investigate.
5. **gatekeeper reviews the diff.** Verifies regression test
   actually exercises the fix path; not theatre.
6. **theologian reviews the falsifier outcome.** Updates the triage
   plan's adaptation log.

## Open questions (test-side) — RESOLVED per alexie 05:32:57Z

1. **Gate-(j) on close-as-upstream skips:** RESOLVED.
   - Rule: if gatekeeper verifies a test fails on BOTH vanilla
     CPython AND CinderX in the same environment, the test may
     be skipped as environmental.
   - Mechanism: `cinderx/TestScripts/cinder_skip_test.txt` with
     a tracker entry per added skip. Gatekeeper sign-off required
     before the skip lands.
   - Implication: Group C close-as-upstream IS a valid disposition
     when the dual-failure verification holds. Otherwise env-patch
     or fix is required.

2. **Test surface for ASan-only bug classes:** RESOLVED.
   - Rule: ASan-found bugs in CinderX MUST be fixed. Exception only
     when shown CinderX-only-under-ASan (false positive) AND the
     false-positive rate is very rare. False-positive frequency >
     "very rare" indicates a CinderX problem that needs fixing.
   - Implication: slab arena UAF, forgetCode UAF, and similar
     ASan-detectable classes are fix-required, not best-effort.
     ASan CI lane wiring becomes follow-up infrastructure work to
     enable continuous detection — not a gate for individual fixes.

3. **CI integration for regression tests:** RESOLVED.
   - Rule: manual cross-validation by gatekeeper + the rest of the
     team is acceptable. No per-commit CI required for this work-cycle.
   - Implication: each fix commit passes through gatekeeper +
     testkeeper + theologian review (three-agent cross-check) before
     landing. This is the enforcement mechanism for gate-(j).

4. **Adjacent-failure tests:** CLARIFIED + RESOLVED.
   - Alexie clarified the question itself: "If you mean which tests
     are RUN, the answer is always all of them. If you mean which
     tests are WRITTEN, then N needs to be driven by testing GAPS,
     not some arbitrary number."
   - Rule: ALL existing tests run on every commit (gate-(j)
     unchanged). NEW tests are written to close identified COVERAGE
     GAPS, not to hit a per-fix N quota.
   - Implication: the per-fix "+1 adjacent test" suggestion in this
     plan is upgraded to "add tests for every gap identified during
     fix work; if no gap is identified, no extra test required."
     The B1/B2/B3/C1/D1 adjacent-test suggestions stand because
     each one IS an identified gap.

## Handoff

- **Plan review:** gatekeeper validates each fix's regression-test
  shape per criterion (j) BEFORE the fix commit lands.
- **Execution drive:** supervisor delegates per group; per fix,
  testkeeper owns the falsifier-proof cycle (steps 1, 3, 4 above).
- **Theologian role:** updates the triage plan's adaptation log
  when a falsifier fires; testkeeper updates this plan's adaptation
  log mirror.

## Plan adaptation log

Append entries here when a falsifier fires or a coverage gap is
discovered mid-execution. Format:

```
- YYYY-MM-DDTHH:MM:SSZ — <bug-id> — <falsifier outcome / new gap> — <plan delta>
```

(empty)
