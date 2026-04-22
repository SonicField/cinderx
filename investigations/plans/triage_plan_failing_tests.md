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
- **A-class partial-close priority rule** (added 2026-04-22 per supervisor 12:16:04Z + pythia 19 #2 floor-not-ceiling concern; originally landed in 2355bd0c, re-applied here after revert b50319ef of the failed A1 fix bundle): when an A-class triage item PARTIAL-CLOSES by spawning a B-class entry (e.g., A1→A2), the spawned entry takes PRIORITY over not-yet-started A-class items in the next-priority queue. Specifically, A-class spawned siblings must be fully closed before continuing other A-class work. Prevents the failure-count-9-as-floor pattern where A-class partial-closes accumulate B-class siblings without ever reducing the failing count.

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

### B4. test.test_subprocess.test_pass_fds_redirected (surfaced by commit 16 cleanup)

- **Symptom:** `test_pass_fds_redirected` fails 5/5 in isolation under cinderx-built python; PASSES under vanilla CPython 3.12.13 in same environment. Subprocess child inherits an extra FD beyond {0,1,2}|pass_fds — the leaked FD points at `/tmp/perf-<pid>.map`.
- **How it surfaced:** commit 16 (9e816756) removed wildcard-class skip entries from `cinder_skip_test.txt` (38 stale entries from Phase 2 dual-failure triage). This wildcard had been masking an individual-method failure in `test.test_subprocess`. Cleanup did NOT introduce the bug — it surfaced a previously-hidden cinderx bug. (Testkeeper 07:48:01Z gate-(j) re-run report; dual-failure verified per alexie 05:32:57Z rule.)

**HYPOTHESIS (refined per generalist 08:03:54Z empirical investigation):**

The leak source is the cinderx `after_fork_child` callback, NOT a cinderx-direct file open. Specifically:

1. cinderx/Jit/pyjit.cpp:2617 `after_fork_child` registers via `os.register_at_fork`.
2. After `fork()` in the child, BEFORE `exec()`, `perf::afterForkChild()` runs (cinderx/Jit/perf_jitdump.cpp:531):
   - Calls `PyUnstable_PerfMapState_Fini()` to close the parent's perf-map FD inherited by fork
   - Calls `copyParentPidMap()` / `copyJitdumpFile()` which use `PyUnstable_WritePerfMapEntry` (CPython upstream API)
3. `PyUnstable_WritePerfMapEntry` opens the child's new perf-map FD WITHOUT CLOEXEC (upstream CPython behavior; cinderx cannot influence the open call directly).
4. The new FD persists through `exec()` because it lacks CLOEXEC; the test child sees it.

Empirical confirmation (generalist 08:03:54Z): post-CLOEXEC-fix (commit 861762a0), all cinderx-direct opens (including jit_perfmap when enabled, jit_gdb_support, mmap_file, perf_jitdump's own opens, symbolizer, pyjit log) verified `FD_CLOEXEC=True` via `fcntl(F_GETFD)`. Despite this, test_pass_fds_redirected still fails 5/5 with the same shape, confirming the leak source is the post-fork CPython API call, not a cinderx-direct open.

**Three architectural fix options as next-priority work (theologian 08:05:03Z):**

A. **Get CLOEXEC on the CPython-opened FD** — requires upstream CPython API support OR a way for cinderx to discover the FD post-open and `fcntl(fd, F_SETFD, FD_CLOEXEC)`. May be blocked on upstream changes.

B. **Skip after_fork_child perf-map copy when subprocess context is detectable** — risk: breaks fork-without-exec multiprocessing where child genuinely needs parent's perf entries. Cannot reliably distinguish at fork time whether `exec()` will follow.

C. **Skip after_fork_child perf-map work UNCONDITIONALLY** — accepts no-perf-map-in-children for all forks. Loses perf observability for `multiprocessing` children. Largest blast radius but cleanest fix.

D. **Default-off `jit_perfmap`** — changes user-visible default; affects production users who rely on perf integration.

**Verification mode (when fix is attempted):**
- Reproduce in isolation: `PYTHONJIT=1 PYTHONPATH=cinderx/PythonLib python3 -m unittest test.test_subprocess.POSIXProcessTestCase.test_pass_fds_redirected -v`
- FD inspection: `fcntl(F_GETFD)` on each FD in cinderx-built python before and after `cinderjit.force_compile`; all should show `FD_CLOEXEC=True` for cinderx-opened FDs (already passes per commit 861762a0)
- Post-fix: re-run subprocess test 5/5 and confirm child FDs match `{0,1,2}|pass_fds` exactly

**Falsifier on each option:**
- If A is attempted and CPython upstream rejects the change → fall back to B/C
- If B is attempted and `multiprocessing` fork-without-exec children lose perf entries → reverse, evaluate C
- If C is attempted and perf observability loss is unacceptable per user feedback → reverse, evaluate D
- If D is attempted and production users complain about behavior change → reverse, escalate to alexie

**Fix-success:** 5/5 PASS on `test.test_subprocess.POSIXProcessTestCase.test_pass_fds_redirected` in isolation under cinderx; full-suite re-run shows failure count returns to pre-commit-16 level (currently 9 with this test skipped via commit 4a80ee2d; should remain 9 after fix with skip removed).

**Disposition this push:**
- Parent-side cinderx-direct opens fixed via O_CLOEXEC in commit 861762a0 (defensive depth value; closes leak class even though doesn't fix this specific test)
- Test skipped via cinder_skip_test.txt entry in commit 4a80ee2d pending B4 deeper-fix
- Skip is TEMPORARY pending B4 work landing; NOT a scope-limitation declaration

**Owner:** theologian (architectural decision A/B/C/D), generalist (impl after decision), testkeeper (verify)

**Cross-references:**
- testkeeper 07:48:01Z (surfaced via gate-(j) re-run)
- generalist 08:03:54Z (empirical root cause: PyUnstable_WritePerfMapEntry post-fork)
- supervisor 07:49:11Z + 08:04:51Z (routing: triage_plan B-group, NOT scope_limitations)
- theologian 07:49:05Z + 08:05:03Z (honest path; 3 architectural options)
- gatekeeper 08:04:37Z (Option B refined: ship CLOEXEC + skip + carve-out)
- commit 861762a0 (CLOEXEC parent-side fix)
- commit 4a80ee2d (skip annotation pending B4)

### B5. yield_from perf regression from 794d8270 ABA-safety GuardType codegen

- **Symptom:** `bench_yield_from_chain` ABBA shows +5.35% regression on the speculation-experiment bundle (HEAD `60701da2`) vs effective baseline `c4e1900c` (per generalist abba_compare.py 07:33:54Z output). Per-benchmark threshold (5%) violated; geomean PASSES (-2.44%).
- **How it surfaced:** gate (k) verification on this push (testkeeper HEAD ABBA + abba_compare).
- **Why this is in triage_plan, not "fix in this push":** mechanism is real (theologian 08:11:11Z root-cause analysis confirmed by generalist 08:13:11Z LICM check); existing GuardType LICM doesn't catch SEND_GEN GuardTypes (call-context, differing types per send, structural per-emission cost). Realistic optimization range 2–8 hr, no 30-min path exists (theologian retracted initial estimate at 08:13:35Z). Trade-off accepted for this push per supervisor 08:13:41Z; documented in `investigations/policies/gate_k_correctness_tradeoff_carveout.md` Invocation 1.
- **Hypothesis (already root-caused, this is the fix-not-the-investigation entry):**
  - 794d8270 changed GuardType from 1-instruction `cmp [reg+ob_type], imm` to 2-instruction `mov scratch, [reg+ob_type]; cmp [scratch+tp_version_tag], imm`.
  - Per `bench_yield_from_chain` run: ~6M GuardType emissions × ~3 cycles per L1-hit dependent load = ~6 ms direct cost. Observed +21 ms / +5.35 %. Direct cost explains ~30%; remainder from pipeline stalls (dependent load + dependent compare) and scratch-register pressure.
- **Verification of mechanism attribution (FIRST sub-step before optimization, encodes testkeeper 10:00:43Z chat commitment):**
  - The hypothesis above attributes the regression to commit 794d8270. Direct cost (~6 ms) explains only ~30% of observed delta (~21 ms); the remaining ~70% is labeled "pipeline stalls / register pressure" but has not been measured directly. Other recent commits (e.g., `07d938f8` threading guard, build-system effects) could plausibly contribute.
  - **Action (FIRST B5 sub-step before any optimization implementation):** Run counterfactual ABBA: HEAD vs HEAD-with-794d8270-reverted-only. Measure actual yield_from delta attributable to 794d8270 in isolation.
  - **Threshold:** Δ ≥ 4 ms (≥ 20% of original 21 ms): theological attribution holds; proceed to optimization options A/B/C as scoped above. Δ < 4 ms: attribution wrong; investigate other commits before committing to A/B/C mechanism (HIR LICM dedup may not be the right fix).
  - **Why this is encoded here, not chat-only:** per recursive-policy-collapse pattern (feedback_recursive_policy_collapse_pattern.md) + pythia checkpoint #17, chat-only commitments don't survive into picked-up work-cycles. testkeeper committed to this in chat at 10:00:43Z (responding to generalist's pythia-#16-driven absorbtion note); without artifact encoding, the obligation collapses retroactively.
  - **Owner:** generalist or testkeeper (whoever picks up B5 next).
- **Optimization options (all are subsequent B-group work; numbers from generalist 08:13:11Z assessment):**
  - **A. HIR-level deduplication of consecutive GuardType on same value.** Modifies HIR pass to recognize redundant guards within a single function. Estimate 2–4 hr. Risk: medium — subtle correctness risk if dedup misses a type-modification window.
  - **B. LIR-level scratch-register cache.** Track 'last value loaded into scratch' across LIR instructions; reuse without reload. Estimate 3–5 hr. Risk: high — interacts with register allocation; cross-block tracking is non-trivial.
  - **C. Restructure SEND_GEN HIR to use a different fast-path that skips the type guard for known-stable generator types.** HIR structural change. Estimate 4–8 hr. Risk: high — risk of breaking generator semantics; needs comprehensive falsifier coverage.
- **Verification mode (when fix is attempted):**
  - Reproduce baseline: re-run ABBA at `c4e1900c` baseline, capture per-benchmark numbers
  - Apply optimization
  - Re-run ABBA at HEAD post-optimization
  - Compare: yield_from delta vs `c4e1900c` should be < 5% (target: ≈ baseline, no regression)
  - Verify all other benchmarks remain within ±5% threshold (no new regressions introduced by optimization)
  - Falsifier-on-the-fix: compound_crash_falsifier_matrix re-run at n=5 must still show 5/5 EXIT=0 on fix tree (correctness preserved); 5/5 EXIT=139 on revert (ABA bug class still detected).
- **Verification of carve-out-scope generalization (precedes optimization, encodes commit-32 Scope deferral):**
  - The gate_k_correctness_tradeoff_carveout.md `## Scope of this carve-out` section bounds the "narrow scope" claim to yield-from-of-generator benches in the CURRENT ABBA suite. Falsifier #4 fires if SEND_GEN cost surfaces on benches outside the current suite — but that falsifier is passive (only fires if someone runs the additional benches). This sub-step encodes the active verification step.
  - **Action:** Run `bench_gen_quick.py` (untracked at repo root) and any other generator-heavy benches that exist (currently identified: `bench_gen_quick.py` only; future SEND_GEN-exercising benches added by any agent must be added to this list) at HEAD `60701da2` and at baseline `c4e1900c` using the standard ABBA harness invocation pattern.
  - **Threshold:** Per-benchmark delta > 5% on any additional bench → broaden perf-recovery scope; the carve-out's "narrow scope" assertion is contradicted (falsifier #4 of gate_k carve-out fires); options A/B/C above must be re-scoped to address the broader bench class, OR Invocation 1 must be marked RESCINDED and the alternate rollback path (REVERT 794d8270) invoked per gate_k_correctness_tradeoff_carveout.md `## Alternate rollback path`.
  - **Threshold:** Per-benchmark delta ≤ 5% on all additional benches → carve-out narrow-scope assertion HOLDS empirically; proceed to optimization options A/B/C as originally scoped.
  - **Owner:** generalist or testkeeper (whoever picks up B5 next).
  - **Why this is encoded here, not chat-only:** per recursive-policy-collapse pattern (feedback_recursive_policy_collapse_pattern.md), deferral mechanisms must ship in the same push that creates the obligation. Commit 32 created the falsifier-#4 obligation; this entry is the artifact-side encoding of the verification step that satisfies it. Without this entry, the deferral is chat-only and the carve-out's Scope clarification is unenforceable.
- **Falsifier on each option:**
  - If A is attempted and the dedup misses a type-modification window → ABA bug returns; falsifier matrix catches it; revert
  - If B is attempted and register allocation interaction breaks compilation → falsified at build time; revert
  - If C is attempted and generator semantics break → falsifier coverage flags it; revert; evaluate D (deferred per scope-limitation framing)
- **Fix-success:** yield_from per-bench Δ < 5% vs `c4e1900c` baseline AND geomean unchanged or improved AND ABA-safety matrix preserved AND no regression on other benchmarks.
- **Disposition this push:** trade-off accepted via gate_k_correctness_tradeoff_carveout.md Invocation 1; commit 4e0f26ab. Optimization deferred until B5 work lands.
- **Owner:** theologian (architectural decision A/B/C), generalist (impl after decision), testkeeper (verify ABBA delta + falsifier matrix)
- **Cross-references:**
  - testkeeper 07:33:54Z (gate (k) verdict surfaced regression)
  - theologian 08:11:11Z (root-cause: 794d8270 + 6M GuardType emissions)
  - generalist 08:13:11Z (LICM check; 2-8 hr realistic estimate)
  - theologian 08:13:35Z (retraction of 30-min estimate)
  - supervisor 08:13:41Z (Option B adopted; ship + B5 routing)
  - commit 4e0f26ab (gate_k_correctness_tradeoff_carveout.md companion artifact)
  - commit 794d8270 (the source of the trade-off)

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
5. **Plan execution timing:** start immediately after bundle pushes, or queue behind other priorities?

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
