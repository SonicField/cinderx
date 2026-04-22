# Triage Plan: Currently Failing JIT Tests + Crashes

**Author:** theologian
**Date:** 2026-04-22
**Driver:** alexie (via vib-jit.chat 05:17:37Z)
**Source of failure list:** testkeeper 05:12:46Z chat post (vib-jit.chat). NOT independently re-enumerated by theologian; Step 0a baseline must reconfirm.

## Scope

~10 known failing test methods + 1 process-killing exception. Excludes the bench_deep_class SIGSEGV (fixed by current speculation-experiment bundle, push pending criterion (j) verification per supervisor 05:15:36Z).

## Cross-cutting rules

- **Stepwise** — each step gates the next; no parallel work in this plan unless explicitly authorized
- Each fix lands as ONE commit with regression test in same commit
- Each commit subject to **criterion (j)** (alexie 05:15:12Z): no increase in failing tests, no increase in skipped tests per `./run_cinderx_tests.sh full` vs prior commit
- **Roles:** generalist = implementation; gatekeeper = gating; testkeeper = runtime verification + regression tests; theologian = root-cause analysis review + falsifier validity per step
- **Falsifier discipline:** every step's hypothesis MUST be explicitly falsifiable. If hypothesis is falsified, plan adapts (re-classify, re-prioritize) — silent drop is not allowed
- **Source-attribution discipline:** every claim about a test's behavior must be cited (chat-record, file Read, or same-turn tool call)

## Step 0: Baseline establishment

### 0a. Reconfirm failure list at HEAD
Run `./run_cinderx_tests.sh full` at the post-bundle commit (after speculation-experiment merges to main). Capture full failure list (test name, error mode, top-of-stack), failing count, skipped count.

If testkeeper's 05:15:49Z criterion-(j) HEAD run completes first, its output IS the baseline; do not re-run.

- **Verification:** counts + failure list recorded with commit SHA in `investigations/triage_baseline.txt`
- **Falsifier:** if HEAD failing-set != testkeeper 05:12:46Z list (10), the plan adapts: extra failures get added to relevant group; missing failures removed with documented reason. Plan does not silently drop newly-discovered failures.

### 0b. Reproducer matrix
Per failing test, capture:
- Exact reproduction command
- Reproducibility (5 runs in isolation; mark deterministic vs flake)
- Last-passing commit estimate (bisect scope, not full bisect yet)

- **Falsifier:** if a test passes 5/5 in isolation, classify as parallel-only failure — different root cause class than deterministic failure. Re-route to Group D protocol.
- **Per-fix-commit update:** when a fix lands, the fix commit MUST log the post-fix reproducer outcome (5/5 runs in isolation + criterion-(j) failing/skipped delta) in the plan adaptation log below. Keeps the matrix honest as the plan executes; prevents "last-passing commit estimate" from going stale.

## Step ordering rationale

- **Group A** (process-killing) → highest blast radius, fix first
- **Group B** (reproducible test assertion failures) → JIT-internal bugs, medium radius
- **Group C** (environment / upstream-caused) → may resolve to "not cinderx" disposition
- **Group D** (flakes) → lowest priority since tests are functional in isolation

Within each group: smaller blast-radius first.

---

## Group A: Process-killing failures (1 item)

### A1. test_jit_preload.test_func_destroyed_during_preload

- **Symptom (per testkeeper):** subprocess returncode 1; OverflowError in CPython `re._compiler` triggered via JIT-preload path
- **Hypothesis:** JIT-preload mechanism passes invalid argument or environment to `re._compiler` when a function is destroyed mid-preload
- **Verification mode:**
  - Reduce to minimal repro (smallest module that triggers)
  - ASan run on the repro to rule out memory corruption masquerading as OverflowError
  - Confirm OverflowError fires inside `re._compiler` not from JIT proper (stack trace inspection)
- **Falsifier:** if minimal repro triggers OverflowError under VANILLA CPython 3.12.13 (same env, no cinderx), bug is upstream — close-as-upstream with tracker entry; OUT of this plan
- **Fix-success:** 5/5 runs return 0; **ASan clean on repro** (so memory-corruption masquerade does not slip through); sentinel test added; criterion (j) holds at fix commit
- **Owner:** generalist (impl), testkeeper (verify), theologian (root-cause + falsifier review)

#### A1 Execution Protocol (5 phases)

**Phase 0 — Reproduction (testkeeper)**
- Run failing test in isolation: `PYTHONPATH=cinderx/PythonLib python3 -m unittest test.test_jit_preload.test_func_destroyed_during_preload -v`
- Capture stack trace + return code → `/tmp/A1_repro_TS.log`
- **Falsifier:** if test passes 5/5 in isolation, reroute to D1 (parallel-only class). Do NOT proceed to Phase 1. Log the reroute in the plan adaptation log below.

**Phase 1 — Hypothesis confirmation OR falsification (generalist + theologian)**
- 1a: construct minimal repro (smallest input that triggers OverflowError via JIT-preload)
- 1b: ASan run on repro
  - If ASan fires BEFORE OverflowError → hypothesis falsified (memory-corruption masquerade, not arg-passing). Reroute to memory-corruption triage; new triage_plan item added to Group A.
  - If ASan clean and OverflowError persists → hypothesis stands; proceed to 1c.
- 1c: vanilla CPython 3.12.13 differential on minimal repro
  - If OverflowError fires under vanilla → close-as-upstream per A1 falsifier above; OUT of plan; tracker entry created.
  - If vanilla passes → cinderx-side bug confirmed; proceed to Phase 2.

**Phase 2 — Root cause (generalist implements, theologian reviews)**
- Trace destroyed-function-mid-preload code path; identify the arg passed to `re._compiler`
- Read `cinderx/Jit/hir/preload.cpp` + adjacent
- Document root cause in fix commit message (cause + mechanism, not just symptom)

**Phase 3 — Fix (generalist)**
- ONE commit; includes regression sentinel that drives the original failing scenario via subprocess (returncode-asserting, similar shape to `test_small_warmup_smoke.py` from this bundle)
- Discipline: address root cause; NO try/except suppression of the OverflowError
- **Pre-commit gates (all must pass):**
  - 5/5 PASS on the original failing test in isolation
  - 5/5 PASS on the new sentinel
  - ASan clean on the minimal repro
  - Criterion (j) full suite at fix-commit vs prior commit (failing+skipped both ≤)
  - Criterion (l) staged-diff empty post-stage; matches intended files only

**Phase 4 — Theologian falsifier review (theologian, post-commit)**
- Did the fix address the named root cause, or suppress the symptom?
- Does the regression sentinel actually exercise the originally-failing path? (coverage.py verification per testkeeper testing_plan C1.x sub-step)
- Are the verification gates documented in commit message?

**Phase 5 — Plan adaptation log entry (generalist or theologian)**
- Append to the adaptation log section below with: timestamp, A1 outcome (fix landed / closed-as-upstream / falsified-and-reclassified), evidence pointer (commit SHA or tracker entry ID)

**Phase exit conditions:**
- A1 closes when Phase 4 + Phase 5 complete with no unresolved falsifier-fires
- B1 begins per Group A→B ordering

---

## Group B: Reproducible test assertion failures (3 items)

### B1. test_jit_support_instrumentation cluster (8 failures + 8 errors)

- **Symptom:** 16 failures in setprofile/settrace integration with JIT
- **Step B1.0 (classification — must precede hypothesis):** group the 16 by error message + top-of-stack. Are they all the same root cause or multiple?
  - **Falsifier:** if failures split into ≥2 distinct root-cause classes, sub-task each class separately as B1a, B1b, ... Each sub-task gets its own hypothesis + falsifier.
- **Hypothesis (subject to B1.0 outcome):** single root cause — JIT-compiled frames don't emit profile/trace events, OR emit wrong frame-type for sys.setprofile callback
- **Verification mode:**
  - HIR dump of one failing trace to confirm whether trace-event emission is in IR
  - Compare to interpreter path event emission for same code
- **Falsifier:** if HIR shows trace events ARE emitted but tests still fail, hypothesis wrong — failure is in event content (frame type, line number, etc.), not event emission. Re-classify.
- **Fix-success:** 0F/0E across 5 runs; criterion (j) holds at fix commit
- **Owner:** generalist (impl, requires HIR familiarity), testkeeper (verify)

### B2. test_jit_perf_map.test_forked_pid_map

- **Symptom:** perf-map missing parent function name in forked process
- **Hypothesis:** post-fork JIT does not re-emit perf-map entries for functions inherited across fork boundary
- **Verification mode:**
  - Instrumented run: dump perf-map file before fork and after fork
  - Check whether parent's function names exist in either map
- **Falsifier:** if perf-map IS emitted post-fork but with truncated/wrong content, hypothesis wrong — content bug not emission bug. Re-classify as B2'.
- **Fix-success:** 5/5 PASS; perf-map verified to contain parent function name; criterion (j) holds
- **Owner:** generalist (impl), testkeeper (verify)

### B3. test_cpython_overrides.test__opcode (DUP_TOP_TWO, JUMP_IF_TRUE_OR_POP KeyErrors)

- **Symptom:** test asserts presence of opcodes that don't exist in 3.12
- **Hypothesis:** test was written for 3.10/3.11 and never updated for our 3.12 target; opcodes ARE removed in 3.12
- **Verification mode:**
  - Read the failing test; identify exact assertions
  - Check `dis.opmap` in 3.12 for `DUP_TOP_TWO` and `JUMP_IF_TRUE_OR_POP`
- **Falsifier:** if either opcode IS in 3.12 dis.opmap, hypothesis wrong — JIT is stripping them and that's the actual bug
- **Fix-success:**
  - If hypothesis confirmed: test patched to assert only 3.12-valid opcodes; 5/5 PASS
  - If falsified: JIT codegen fixed to retain these opcodes; 5/5 PASS
- **Owner:** generalist (impl, decision pending falsifier outcome), testkeeper (verify)
- **OPEN QUESTION FOR ALEXIE:** is patching the test acceptable here, or does the test reflect a contract the JIT must satisfy?

---

## Group C: Environment / stale failures (5 items)

Items: test_cmd_line, test_urllib, test_urllib2, test_uu, test_zipfile (CPython stdlib failing under cinderx-built python).

### C1. Triage protocol — applied per test

For each of the 5 stdlib failures:

**C1.x.0 (upstream check):** Run under upstream CPython 3.12.13 in same environment (no cinderx)
- **Falsifier:** if test FAILS under upstream same-env → environment-caused. Close-as-upstream with tracker entry. OUT of this plan.

**C1.x.1 (only if upstream PASSES — JIT-vs-runtime decode):** Run under cinderx-built python with `--no-jit` (or equivalent JIT-disabled flag — generalist confirms exact flag)
- If `--no-jit` FAILS → cinderx runtime bug (not JIT codegen). Hand to runtime triage.
- If `--no-jit` PASSES → JIT codegen bug. Hand to JIT triage with HIR dump of failing function.

- **Fix-success per test:** 5/5 PASS under cinderx-built python; criterion (j) holds at each fix commit
- **Owner:** generalist (impl), testkeeper (verify), theologian reviews per-test root-cause classification

---

## Group D: Flakes (1 item)

### D1. test_docxmlrpc parallel-run flake

- **Symptom:** ~17% failure rate under parallel-run, 5/5 PASS in isolation (per testkeeper 04:08Z + 05:09:15Z chat record)
- **Hypothesis:** socket port collision in parallel test runner
- **Verification mode:**
  - Read test; check if it grabs random port (`sock.bind((host, 0))`) or fixed port
  - If fixed port: hypothesis confirmed
  - If random port: investigate test-runner forking behavior for port-reservation
- **Falsifier:** if test fails ≥1/5 in isolation, hypothesis wrong — root cause not parallel-only. Re-classify (likely Group B).
- **Fix-success:** 0 failures across 20 parallel-run cycles
- **Owner:** generalist (impl), testkeeper (verify)
- **NOTE:** lowest priority since test is functional in isolation. Open question to alexie: block this on plan completion or xfail-mark and deprioritize?

---

## Out of scope for this plan

- Performance regressions (separate workstream — ABBA gate)
- Tests intentionally skipped (xfail/skip markers): this plan does not propose to unskip
- New crashes discovered during fix work: add to plan (not bypass), re-prioritize
- Triage of NBS-process patterns (verification rhetoric, recursive policy collapse): not in scope here

---

## Open questions for alexie

1. **Step ordering:** A → B → C → D as proposed, or different priority?
2. **B3 test-side fix:** patching `test_cpython_overrides.test__opcode` acceptable, or must JIT preserve the removed opcodes?
3. **Group C close-as-upstream:** for tests that fail under upstream same-env, is "close as not-cinderx" acceptable disposition, or must we patch even environment-caused failures?
4. **D1 priority:** flake-only-under-parallel — block or xfail-and-defer?
5. **Plan execution timing:** start during current session (after bundle pushes), or wait for next session?

---

## Handoff

- **Plan review:** gatekeeper validates falsifier per step before execution starts
- **Testing extension:** @testkeeper extends with testing-plan ensuring zero testing gaps (per alexie 05:17:37Z directive)
- **Execution drive:** @supervisor delegates work per group + enforces stepwise ordering
- **Theologian role during execution:** per-step root-cause classification review; updates this plan as falsifiers fire; calls out classification drift

---

## Plan adaptation log

Future maintainers: append entries here when a falsifier fires or scope shifts. Format:

```
- YYYY-MM-DDTHH:MM:SSZ — <step-id> — <falsifier outcome / scope shift> — <plan delta>
```

(empty)
