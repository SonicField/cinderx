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
- **A-class partial-close priority rule** (added 2026-04-22 per supervisor 12:16:04Z + pythia 19 #2 floor-not-ceiling concern; originally landed in 2355bd0c, re-applied here after revert b50319ef of the failed A1 fix bundle): when an A-class triage item PARTIAL-CLOSES by spawning a sibling A-class or B-class entry, the spawned entry takes PRIORITY over not-yet-started A-class items in the next-priority queue. Specifically, A-class spawned siblings must be fully closed before continuing other A-class work. Prevents the failure-count-N-as-floor pattern where A-class partial-closes accumulate sibling entries without ever reducing the failing count. (Note: prior example "A1→A2" referenced an A2 entry that was deleted by b50319ef revert; current A2 is a separate adjacent-bug retry workstream per testkeeper 14:10:40Z framing correction. Rule shape applies generally to any A-class partial-close pattern.)
- **Hypothesis-revision-budget cross-cutting rule** (added 2026-04-22 per shepard 15:15:03Z proposal + supervisor 16:50:09Z direction + theologian 16:49:39Z carrier; first concrete application case = today's B1 cycle pivot count = 7): when a workstream undergoes 4+ hypothesis pivots within a single work-cycle, pause for falsifier-design review before continuing. Falsifier-design review = explicit naming of WHAT empirical evidence would falsify the next pivot, BEFORE attempting it. Verification burden on Phase 4 reviewers compounds with pivot count; pause-and-design protects reviewer bandwidth. Trigger: 4+ pivots. Owner: workstream-active agent self-applies; supervisor enforces if missed. Today's B1 cycle pivots (memorialization): 1=B1.0 single-vs-multi-class; 2=cascade-vs-separate B1c; 3=Subbarao-default-flip-vs-test-API; 4=ALLCAPS-suffix-vs-underscore-prefix; 5=candidate-list-vs-single-name; 6=B1-fix-validates-vs-build-staleness; 7=build-staleness-simple-vs-struct-layout-divergence. Rule fires retroactively at pivot 5 as the canonical first application case.

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

## Group A: Process-killing failures + active workstream (3 items)

### A1. test_jit_preload.test_func_destroyed_during_preload

- **Symptom (per testkeeper Phase 0 + 14:10Z framing correction):** subprocess returncode 1; OverflowError 'Python int too large to convert to C ssize_t' in `re._parser.SubPattern.getwidth` at `for op, av in self.data:` (FOR_ITER over self.data, where self.data is a list of tuples). Test uses `-L` (lazy imports) flag; failure is deterministic 5/5 under the test's exact subprocess invocation.
- **Hypothesis (corrected per testkeeper 14:10Z + theologian 14:10:35Z):** JIT FOR_ITER specialization for list iterators corrupts int representation during unpack `for X, Y in items:` where Y is an int participating in downstream ssize_t conversion. Surfaces as OverflowError in `re._parser.SubPattern.getwidth` because that function unpacks tuple elements containing potentially-large ints.
- **Note on prior hypotheses (now falsified per work-cycle 13:40Z gate (k) BLOCK):** earlier hypothesis "JIT-preload mechanism passes invalid argument" was based on initial test name; investigation revealed no preload-mechanism involvement. Subsequent hypothesis "NULL deref via missing CheckExc on InvokeIterNext" (commits c64e7682 + 621b44ad + 2355bd0c, reverted by b50319ef) was a SEPARATE bug (Bug A: SIGSEGV in no-L diagnostic variant), NOT this test's failure mode. The test (with `-L`) always failed via the FOR_ITER int corruption path; Bug A only surfaced via the no-L diagnostic repro. Both A1 (Bug B) and Bug A (separate) are real bugs; only A1 matters for the failing-test count.
- **Verification mode:**
  - HIR-final-dump-FIRST diagnostic (per memory feedback_lir_dump_first_for_null_deref_sigsegv.md analog for graceful-exception class): dump JIT-compiled `re._parser.SubPattern.getwidth` with `-X jit-dump-final-hir` (printer.cpp:265 kGuardOverflow case fix per commit 46c26256 unblocks this for any function with GuardOverflow op)
  - Trace int representation through the FOR_ITER + UNPACK_SEQUENCE chain in final HIR
  - Identify the corruption point: codegen-level vs runtime-helper vs HIR-pass-elision
- **Falsifier branches (Phase 2 mechanism candidates):**
  - (a) **LIR codegen bug:** JIT-emitted FOR_ITER + UNPACK_SEQUENCE code mishandles int representation (e.g., wrong-width int op, sign-extension bug, unboxed-int overflow not detected at boundary)
  - (b) **JITRT runtime bug:** JITRT helper for list-iter unpack (likely in cinderx/Jit/jit_rt.cpp) returns corrupted int
  - (c) **HIR-pass elision:** type-narrowing / refine-type / copy-prop pass eliminates overflow-check that builder originally emitted
  - (d) **Inlined-call speculation:** getwidth recursively inlined under wrong type assumption (e.g., element-type narrowed below actual range)
- **Falsifier on the bug class:** if minimal repro triggers OverflowError under VANILLA CPython 3.12.13 (same env, no cinderx) → bug is upstream, close-as-upstream OUT of plan. (Pre-checked: vanilla passes; falsifier does NOT fire.)
- **Bug-class naming convention (added 2026-04-22 per librarian 14:33:42Z + theologian reconflation pattern N=3+):** A1 entry covers Bug B (FOR_ITER list-iter int corruption causing OverflowError); A2 entry (separate Group A item) covers Bug A (NULL-deref SIGSEGV in InvokeIterNext path). When citing repros or test variants in chat or commit messages, refer EXPLICITLY by Bug class (Bug-B-repro / Bug-A-repro), NOT by ambiguous flag distinction (-L / no-L). Reason: same agent reconflated A1↔Bug-A 3+ times in same day despite explicit self-corrections. Future-agent inheritance benefits from unambiguous naming.
- **Fix-success:** 5/5 PASS on original test_jit_preload (subprocess returncode 0); 5/5 PASS on Bug-B-repro `re.compile(rb'a*b')` under -X jit-all -L; sentinel test added; criterion (j) holds at fix commit; failure count drops to 8.
- **Owner:** generalist (impl), testkeeper (verify), theologian (root-cause + falsifier review)
- **Cross-references:**
  - testkeeper 14:10:40Z framing correction (test always Bug B; Bug A was separate diagnostic-only)
  - theologian 14:10:35Z self-correction on prior A1→A2 reclassification framing
  - theologian 13:00:18Z A2-now-A1 falsifier scaffolding (HIR-final-dump-FIRST)
  - theologian 12:42:18Z + 13:08:31Z A1 sentinel test draft (3-test design)
  - generalist 11:46:26Z Bug B initial identification post-Bug-A-fix
  - work-cycle 10:18Z–13:40Z full investigation log
- **Adjacent bug (separate workstream, not part of A1):** Bug A = no-L SIGSEGV in InvokeIterNext path; tracked for retry via Option G (3-way branch in CondBranchIterNotDone) per theologian 13:48:32Z; NOT priority for failure-count reduction (doesn't affect test failure mode).

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
- B1 begins per Group A→B ordering AFTER A2 closes (per A-class-partial-close priority rule + adjacent-bug discipline; A2 is theologian-spec'd retry of c64e7682 fix attempt class)

---

### A2. Latent Bug A: SIGSEGV in InvokeIterNext NULL-on-iter-exception path (no-L diagnostic variant; not in failing-test list)

- **Symptom:** `python -X jit-all script.py` (without `-L`) where script triggers an iterator whose `__next__` raises an exception → JIT-compiled FOR_ITER calls JITRT_InvokeIterNext which returns NULL on the exception path; downstream CondBranchCheckType reads ob_type at offset 8 from NULL → SIGSEGV exit 139. Reproducible 5/5 via `/tmp/A1_minimal_repro_no_L.py` per work-cycle 11:33Z investigation.
- **Why this is A2 and not in failing-test list:** Bug A is a real production-shape SIGSEGV bug class (any process running JIT without lazy imports + raising iterator hits it), but NO test in the current cinderx test suite exercises this code path. test_jit_preload (the closest test) uses `-L`, which surfaces a DIFFERENT bug (Bug B = A1) that masks Bug A. Bug A was discovered as a diagnostic-side observation during A1 investigation (work-cycle 11:33Z–13:40Z). Failure count = 9 unchanged whether A2 is fixed or not (no test in failing list).
- **Hypothesis (root-cause already identified per work-cycle):** InvokeIterNext returns sentinel | NULL-on-iter-exception | iter value (per its hir.h doc). emitForIter at builder.cpp:4569-4584 emits CondBranchIterNotDone which only distinguishes sentinel-vs-non-sentinel; NULL flows through as 'not done' to body; downstream CondBranchCheckType reads ob_type from NULL → segfault. Coredump RIP confirmed at 0x...c32 / 0x...b7e (work-cycle 10:35Z testkeeper + 10:42Z generalist + 11:05Z generalist mapping to re._parser:SubPattern.getwidth, but the bug class is GENERAL — affects any JIT-compiled FOR_ITER over a raising iterator, not just SubPattern).
- **Prior fix attempt (REVERTED, do not retry as-is):** c64e7682 + 621b44ad + 2355bd0c added CheckExc on InvokeIterNext output + simplify substitution returning TOptObject + pass.cpp returnType TOptObject. EMPIRICALLY FIXED Bug A (SIGSEGV → graceful exception) but imposed gate (k) BLOCK with -9.24% geomean / 12 regressions / gen_nested +85% / gen_simple +57%. Reverted via b50319ef. Mechanism candidate: CheckExc-as-deopt-point inhibits HIR optimization passes from moving state across every for-loop iter (theologian 13:46:35Z architectural hypothesis, NOT empirically verified).
- **Future retry candidate (Option G per theologian 13:48:32Z):** modify CondBranchIterNotDone HIR op to handle 3 outcomes (sentinel / NULL / iter value) via 3-way branch instead of 2-way. NULL goes directly to except handler, NOT deopt-point. Avoids c64e7682's broad perf cost. ~4-8hr generalist work; substantial change scope (HIR op + LIR codegen + simplify substitution all touched).
- **Verification mode (when retry begins):**
  - Re-confirm Bug A reproduces 5/5 SIGSEGV at current HEAD via /tmp/A1_minimal_repro_no_L.py
  - HIR-dump pre-Option-G HIR for a function that hits CondBranchIterNotDone (gen_nested per work-cycle 14:11Z generalist HIR-pre-prepped)
  - Implement Option G; rebuild
  - Empirical gate (k) ABBA: HEAD vs c4e1900c-baseline; verify NO regressions on iteration-heavy benches (gen_nested, gen_simple, coroutine_chain etc.)
  - 5/5 PASS on minimal repro (Bug A converted to controlled deopt or except-handler, NOT SIGSEGV)
- **Falsifier branches:**
  - (a) Option G implementation works + no perf regression → A2 closes; Bug A class fixed at HIR level cleanly
  - (b) Option G implementation works but introduces NEW perf regression on a different benchmark class → Option G has hidden cost; iterate per Phase 5 log
  - (c) Option G architecturally infeasible (e.g., 3-way branch can't be expressed in current HIR/LIR without invasive changes) → defer to deeper architectural workstream; A2 stays open as known-unfixable-cheaply
- **Fix-success:** 5/5 PASS on /tmp/A1_minimal_repro_no_L.py (no SIGSEGV); gate (k) ABBA shows zero per-benchmark regressions vs baseline; gate (j) failure count UNCHANGED at 9 (no test was failing for Bug A; failure count math doesn't change).
- **Owner:** generalist (impl), testkeeper (verify), theologian (root-cause review + Option G architectural validation pre-implementation)
- **Priority:** LOWER than A1 per A-class-partial-close priority rule. A1 is in failing-test list (affects failure count); A2 is latent (does not affect failure count). A1 fix has direct gate (j) impact; A2 fix has zero gate (j) impact but eliminates a real production-shape SIGSEGV crash class.
- **Trigger condition for A2 retry workstream** (added 2026-04-22 per pythia 23 #2 ownership-encoding gap): retry begins when EITHER (a) all in-failing-test-list A-class items closed (currently A1 still open with refined Phi-input hypothesis from 14:18-14:33Z investigation) OR (b) supervisor explicitly elevates A2 priority due to production-shape SIGSEGV pressure (e.g., user-report of in-the-wild crash). Default: do NOT begin A2 work while A1 remains open. A-class-partial-close priority rule applies to in-failing-list items first; A2's lower-priority status (latent, doesn't reduce gate-(j) failure count) means it queues behind A1 and behind any newly-spawned A-class entries that are in failing list.
- **Cross-references:**
  - work-cycle 10:18Z–13:40Z full investigation log (Bug A identification + 4hr work + gate (k) BLOCK + revert)
  - testkeeper 10:35Z + generalist 10:42Z + generalist 11:05Z (coredump + HIR + function mapping)
  - theologian 13:48:32Z (Option G as future retry candidate)
  - revert b50319ef (commit message preserves c64e7682 details for retrieval)
  - testkeeper 14:10:40Z framing correction (Bug A separate from A1)

#### A1 Phase 5 plan adaptation log (2026-04-22 work-cycle)

- 2026-04-22 ~10:18Z: A1 Phase 0 reproduction completed (testkeeper). Failure mode = OverflowError under -L (deterministic 5/5).
- 2026-04-22 11:33Z–13:40Z: 4-hour investigation into hypothesized "missing CheckExc on InvokeIterNext" path (Bug A). Fix attempt #5 = c64e7682 + 621b44ad + 2355bd0c shipped to sonicfield.
- 2026-04-22 13:40Z: gate (k) ABBA at fix-tree HEAD shows -9.24% geomean, 12 regressions (gen_nested +85%, gen_simple +57%, etc.). c64e7682 imposed unacceptable perf cost via CheckExc-as-deopt-point on every for-loop iteration (architectural hypothesis, not empirically verified).
- 2026-04-22 13:50Z: revert via b50319ef (revert c64e7682 + 621b44ad + 2355bd0c) + 46c26256 (re-apply orphaned priority rule + B6 printer fix). Pushed to sonicfield 14:11:39Z.
- 2026-04-22 14:10Z: testkeeper empirical correction surfaced — A1 (the test, with -L) was always failing via FOR_ITER list-iter int corruption (Bug B); Bug A (no-L SIGSEGV) was a SEPARATE diagnostic-only bug. The 4-hour Bug-A investigation didn't address A1. Hypothesis re-pointed to Bug B per testkeeper 14:10:40Z + theologian 14:10:35Z self-correction.
- 2026-04-22 14:13Z: A1 hypothesis updated to Bug B (FOR_ITER list-iter int corruption); A1 retry scaffolding attached.
- 2026-04-22 14:18Z–14:33Z: A1 retry Phase 1 + Phase 2 + Phase 3 attempted by generalist:
  - Phase 1 (HIR-final-dump): empirically located the corruption mechanism. JIT compiles `hi = hi + 1` (re._parser.py:209/210) via `simplifyLongBinaryOp` (cinderx/Jit/hir/simplify.cpp:1011-1032) which emits `PrimitiveUnbox<CInt64>` + `IntBinaryOp` + `GuardOverflow` + `PrimitiveBox`. When `hi = MAXWIDTH` (= 1 << 64 in re._parser.py, > INT64_MAX = Py_ssize_t max), `PrimitiveUnbox<CInt64>` raises OverflowError "Python int too large to convert to C ssize_t" directly, BEFORE the GuardOverflow check fires. The error surfaces at the outer FOR_ITER caller frame because that's where the call originated.
  - Phase 1 falsifier (bounded-quantifier control): `b'a{1,5}b'` PASSES under -X jit-all -L (5/5 exit 0). HIR shape is IDENTICAL to `b'a*b'`; only RUNTIME values differ (bounded path never assigns MAXWIDTH to hi/lo). Confirms attribution to MAXWIDTH-touching unboxing path; (a)+(d) joint mechanism per generalist 14:24:09Z.
  - Phase 3 fix attempt #6 (valueOutsideCInt64 surgical check at simplify.cpp:1011-1032): emits the helper `valueOutsideCInt64(Type)` that returns true when type has objectSpec with overflow per `PyLong_AsLongLongAndOverflow`, then skips the unbox path. EMPIRICALLY FALSIFIED via post-fix HIR diff: same GuardOverflow / IntBinaryOp / PrimitiveUnbox count as pre-fix; Bug B repro still 5/5 OverflowError exit 1. Reverted cleanly (single Edit, no commit).
  - Mechanism deepens: the value flowing into `simplifyLongBinaryOp` is a Phi-merged register (e.g., `v235:Object = Phi v226 v371 v798 ...` per /tmp/A1retry_finalhir_postfix.txt:58). Phi merging at loop-recursive accumulators widens the [overflow] spec away — by the time the unbox check sees its operand, the static type is plain LongExact (no spec). Single-function spec-check at `simplifyLongBinaryOp` is too late in the pipeline.
  - Refined hypothesis (post-Fix-#6): PrimitiveUnbox<CInt64> on values that exceed Py_ssize_t raises OverflowError. The HIR builder should not emit such an unbox when the value's source MAY include MAXWIDTH-class values (Phi-input analysis required). Static-objectSpec check at the consumer is insufficient when the value passes through Phi merges.
- 2026-04-22 14:34Z (this commit): OPTION B (defer A1 retry) per supervisor 14:34:22Z + theologian 14:34:25Z. A1 stays open with refined hypothesis. Future retry candidates (per generalist 14:33:36Z + theologian 14:34:25Z):
  - (1) **Flow-sensitive Phi-input analysis** — recursively check Phi inputs for [overflow] spec; conservative if any input has it. ~2-4hr novel HIR pass work; risk = c64e7682-style broad-impact uncertainty.
  - (2) **PrimitiveUnbox runtime-deopt-on-overflow** — instead of raising OverflowError from PrimitiveUnbox<CInt64> when value doesn't fit, deopt to interpreter (re-execute BINARY_OP). LIR codegen change for kPrimitiveUnbox; per feedback_hir_not_lir.md this is wrong-level but pragmatic.
  - (3) **Defer unbox decision until after Phi resolution** — move simplifyLongBinaryOp specialization to a later pass that runs after Phi-elimination; specialize per-block where types are concrete.
  - (4) **FrameState semantics change** — extend GuardOverflow's deopt path to also cover unbox-failure case via preflight check. Requires understanding deopt path fully.
- A1 retry workstream sequencing: dedicated cycle, 2-4hr candidate; pick (2) or (3) for narrowest scope. Don't commit until empirical pre/post on Bug-B-repro confirms 5/5 PASS (per pythia 22 + work-cycle Bug-A misdirection lesson). Per Bug-class naming convention (already inline in A1 entry per 56f7603a): cite repros by explicit Bug-B / Bug-A class, not by -L / no-L distinction.

---

### A3. Perf-regression-bisect workstream: c4e1900c..HEAD -10% geomean (WITHDRAWN per Step 0 evidence; not in failing-test list; preserve lineage)

- **STATUS (2026-04-22T20:32:03Z post Step 0 verdict):** **WITHDRAWN.** No perf regression exists in c4e1900c..HEAD when measured consistently. Cached baseline /tmp/abba_fresh_c4e1900c_v2.txt (Apr 22 02:49Z, GEOMEAN 1.19x) was environment-stale; fresh c4e1900c clean rebuild (testkeeper 20:32:03Z, GEOMEAN 1.06x) vs HEAD (GEOMEAN 1.07x) shows ~1% delta — within noise band. Per-benchmark "winner→loser" pattern (gen_nested 1.19x→0.63x etc.) was pre-existing in c4e1900c too when measured in current environment; not new regressions. Per alexie 19:49:33Z falsifier discipline + testkeeper 20:32:03Z falsifier-checklist: source-code-invariant (c4e1900c hash unchanged) + measurement-instrument-invariant (benchmark_cinderx.py SHA256-identical) + cached-vs-fresh-differ-significantly → parsimonious explanation = environment-cause (alexie item 5: system load / CPU thermal / cohabitant-process state at 02:49Z cache time). Source-invariant evidence makes "no regression" the parsimonious conclusion. Result: benchmarks/2026-04-22_133127_c4e1900c_step0_rebuild_x86_64_abba.txt. The 47-commit bisect plan + Steps 1-3 + hot-spot candidates (07d938f8 / 861762a0 / 46c26256 / 794d8270) all UNNECESSARY — no regression to bisect. Entry preserved (not deleted) per recursive-policy-collapse rule: withdrawn-with-evidence preserves lineage for future cycles facing similar stale-cached-baseline phantom-regression patterns. Bundle X+Z UNBLOCKS per fix #4 reinterpretation (no regression = no gate (k) BLOCK).
- **Symptom (per testkeeper 18:58:32Z gate (k) ABBA on post-clean-rebuild HEAD):** speculation-experiment HEAD (post-clean-rebuild, B.1+B.1.ii in worktree but X+Z held per fix #4) shows GEOMEAN 1.07x vs cached baseline c4e1900c GEOMEAN 1.19x → -10% delta. 6 NEW per-benchmark losers + 4 winner→loser flips: gen_nested 1.19x→0.63x (-58%), func_calls 1.15x→0.74x (-34%), gen_simple 1.21x→0.76x (-31%), pytorch_cm 1.27x→0.95x (-25%), coroutine_chain 1.07x→0.88x (-14%), yield_from 0.96x→0.82x (-14%). Generator + dispatch hot-paths most affected. Result: benchmarks/2026-04-22_115805_c1982ca5_b1_postfix_x86_64_abba.txt. Pattern is regression-on-prior-build-state (regression confirmed on stale build that did NOT contain B.1+B.1.ii edits per testkeeper 16:59:01Z); cause is INDEPENDENT of B.1.
- **Why this is A3 and not in failing-test list:** perf regression doesn't manifest as a test failure (gate (j) full suite GREEN per testkeeper 17:22:37Z); it manifests as gate (k) BLOCK. NO test in current failing list exercises perf threshold. Active workstream because gate (k) BLOCK = bundle BLOCK regardless of attribution per fix #4: X+Z bundle held until A3 resolution.
- **Hypothesis (root cause class):** cumulative perf cost from one or more commits in 47-commit c4e1900c..HEAD range. Hot-spot candidates per testkeeper diagnostic (19:00:55Z + 18:58:32Z benchmark pattern): 07d938f8 (threading guard mutex; could affect dispatch hot-path), 861762a0 (CLOEXEC fcntl in cinderx-direct opens; init-time cost), 46c26256 (printer.cpp B6 GuardOverflow case; may affect HIR codegen if exercised on hot-path), plus 794d8270 GuardType ABA-safety (already known +5.35% yield_from cost per B5 entry; may compound).
- **Verification mode (4-step bisect plan per supervisor 19:01:59Z):**
  - **Step 0 (testkeeper, in flight per testkeeper 19:03:21Z):** rebuild from c4e1900c isolated worktree (/tmp/cinderx-c4e1900c) + ABBA against current HEAD post-clean-rebuild. ETA ~110 min from 19:03:21Z. Quantitative threshold per supervisor 19:20:18Z: `< 5% delta` from cached baseline geomean = "matches 1.19x ± noise" (operationalizes existing memory feedback_gate_j_skip_variance.md ~3-4% noise variance applied symmetrically to perf benches); `> 5% delta` = "differs significantly" → cached baseline stale → recalculate threshold against fresh c4e1900c-rebuild number.
  - **Step 1 (post Step 0, awaiting fresh-baseline number):** if Step 0 confirms cached baseline current-environment-replicable: bisect midpoint (~commit 24/47 in range). Run ABBA at midpoint vs c4e1900c. If midpoint matches baseline within threshold: regression in second half (commits 24-47); if midpoint matches HEAD-regression: regression in first half (commits 0-24). Iterate.
  - **Step 2 (per Step 1 outcome):** narrow to single commit causing major share of regression. Hot-spot candidates above are first-priority bisect midpoints per Pareto: pick midpoint nearest to candidate commit cluster.
  - **Step 3 (post Step 2):** evaluate fix candidates for the identified culprit commit (revert / re-design / acceptance per supervisor scope decision). Land fix; re-ABBA; X+Z bundle re-attempt at fixed HEAD.
- **Falsifier branches (Phase 2 mechanism candidates):**
  - (a) **Step 0 baseline non-replicable (delta > 5%):** cached /tmp/abba_fresh_c4e1900c_v2.txt is wrong commit OR environment drift since 02:49Z cache. Recalculate threshold; bisect against fresh c4e1900c-rebuild number.
  - (b) **Single-commit cause:** one of hot-spot candidates is dominant cost contributor; Step 2 surfaces single revert + bundle re-attempt is ~immediate.
  - (c) **Multi-commit cumulative cause:** no single commit dominant; multiple sources contribute. Requires per-commit ABBA accumulation; resolution timeline 1-2 day per commit class.
  - (d) **Architectural cause (irreducible):** regression is from a design choice that can't be cheaply reverted (e.g., 794d8270 ABA-safety GuardType pattern compound across new opcodes). Resolution = supervisor scope decision (accept regression vs major rewrite vs gate_k_correctness_tradeoff_carveout.md Invocation 2).
- **Falsifier on the bug class:** if Step 0 ABBA shows c4e1900c-fresh-rebuild geomean ALSO -10% from cached baseline (delta > 5%), the cached baseline is stale not the HEAD regression — recalculate threshold; bisect-via-fresh-baseline. Bisect framework holds; baseline number changes.
- **Fix-success:** A3 closes when bisect identifies cause + fix lands + re-ABBA at fixed HEAD shows < 5% delta from c4e1900c baseline AND no per-benchmark regression beyond threshold. Then X+Z bundle stages + re-runs gate (k); if GREEN, X+Z bundle pushes per fix #4 release path. B1 closure attribution moves from INVESTIGATION-RE-OPEN to FULL CLOSE at that point.
- **Owner:** testkeeper (coordinate + ABBA cycles), generalist (build cycles + bisect-commit checkout sequence), theologian (root-cause + falsifier review per Step + scope decision validation pre-implementation when fix candidates evaluated).
- **Priority:** HIGHEST among A-class active items. Per A-class-partial-close priority rule: A3 BLOCKS X+Z bundle ship (gate (k) BLOCK = bundle BLOCK per fix #4); A1 (still open with refined Phi-input hypothesis) + A2 (latent SIGSEGV, default deferred per A2 trigger condition) queue behind A3 for failure-count-floor reduction priority.
- **Trigger condition for A3 workstream phases:** in flight per testkeeper 19:03:21Z. First decision-point checkpoint when Step 0 ABBA returns (~110 min ETA from 19:03:21Z = ~20:53Z). Subsequent checkpoints per Step 1/2/3 outcome.
- **Cross-references:**
  - testkeeper 18:58:32Z gate (k) BLOCK + per-benchmark breakdown
  - testkeeper 19:00:55Z hot-spot candidates (07d938f8 / 861762a0 / 46c26256 / 794d8270)
  - testkeeper 19:03:21Z Step 0 in-flight (isolated worktree + clean rebuild)
  - supervisor 19:01:59Z 4-step bisect plan + A3 owner triple
  - supervisor 19:20:18Z 5% threshold per memory feedback_gate_j_skip_variance.md
  - pythia 30 #1 quantitative threshold gap + #2 chat-only-deferral risk surface (this entry IS the artifact-side resolution per pythia 30 #2)
  - benchmarks/2026-04-22_115805_c1982ca5_b1_postfix_x86_64_abba.txt (gate (k) BLOCK result)
  - B1 entry STATUS block (cross-references this A3 as the bundle-blocking workstream)
  - B5 entry (existing yield_from regression workstream; A3 may subsume B5 if 794d8270 surfaces as A3 hot-spot)

---

## Group B: Reproducible test assertion failures (3 items)

### B1. test_jit_support_instrumentation cluster (8 failures + 8 errors)

- **Symptom (per testkeeper 05:12:46Z chat post):** 16 distinct failures + errors in `test_jit_support_instrumentation` test module covering setprofile / settrace / monitoring / coverage tool integration with JIT-compiled frames
- **Step B1.0 (classification — must precede hypothesis):** group the 16 by error message + top-of-stack. Are they all the same root cause or multiple?
  - **Falsifier:** if failures split into ≥2 distinct root-cause classes, sub-task each class separately as B1a, B1b, ... Each sub-task gets its own hypothesis + falsifier.
- **Hypothesis (subject to B1.0 outcome):** single root cause — JIT-compiled frames don't emit profile/trace events, OR emit wrong frame-type for sys.setprofile callback
- **Verification mode (HIR-final-dump-FIRST per A1 lessons):**
  - HIR-final-dump for ONE JIT-compiled function in the failing test path (printer.cpp:265 kGuardOverflow case is in tree per 46c26256, unblocks final-HIR-dump diagnostic)
  - Compare HIR to interpreter-path event-emission for the same Python code
  - Identify whether trace event ops (e.g., kEmitProfileEvent, kEmitTraceEvent, kCallProfileFunc — verify exact HIR op names same-turn before fix work) are emitted in the JIT path
- **Falsifier branches (Phase 2 mechanism candidates, mirroring A1 4-branch shape):**
  - (a) **HIR builder gap:** profile/trace event ops are NOT emitted by HIR builder for relevant bytecode patterns (CALL / RETURN / RESUME / etc.). Fix at HIR builder.
  - (b) **HIR-pass elision:** event ops emitted by builder but eliminated by DCE / copy-prop / similar pass that doesn't recognize their side-effect semantics. Fix at the eliminating pass.
  - (c) **LIR codegen bug:** HIR has event ops but LIR translation drops them or emits wrong runtime call. Fix at LIR codegen.
  - (d) **JITRT runtime bug:** event ops correctly emitted + lowered, but JITRT helper that delivers events to Python sys.setprofile callback either fails or passes wrong frame-type. Fix at runtime helper.
- **Falsifier on the bug class:** if a failing test method PASSES under cinderx-built python WITHOUT -X jit-all (i.e., interpreter only), bug is JIT-induced. If it ALSO fails interpreter-only, bug is in cinderx runtime not JIT — escalate to runtime triage. (Pre-checked: testkeeper Phase 0 at 05:12:46Z showed these are JIT-related; falsifier expected NOT to fire but worth re-confirming at fix-commit time.)
- **Bug-class naming convention applied (per A1 entry's convention):** if multiple distinct bugs surface during B1.0 classification, name explicitly as B1-Bug-X / B1-Bug-Y rather than -L / no-L flag distinctions or other ambiguous markers.
- **Fix-success:** 0F/0E across 5 runs of test_jit_support_instrumentation; gate (j) full-suite re-run shows failure count drops by 16 (cluster fully resolved) OR by N where N is the number of root-cause-classes confirmed-fixed (if B1.0 surfaces ≥2 distinct classes); gate (k) ABBA shows no perf regression (per A1 c64e7682 lesson: HIR-pass changes can have broad cost; profile/trace emission additions could affect hot-path perf if added per-call); criterion (l) holds at fix commit.
- **Owner:** generalist (impl, requires HIR familiarity for builder/passes/codegen layers), testkeeper (verify), theologian (root-cause + falsifier review)
- **Priority:** per A-class-partial-close priority rule re-interpretation (theologian 14:39:42Z + supervisor 14:39:38Z concurrence): B1 takes priority over A2 (Bug A latent SIGSEGV) because B1 is in failing list (fixing reduces failure count 9→ depending on cluster split) and A2 is not in failing list (fixing doesn't reduce floor). Rule's stated intent is failure-count-floor reduction; B1 directly serves that.
- **STATUS (2026-04-22T20:32:03Z post Step 0 verdict, supersedes prior 18:58:32Z INVESTIGATION-RE-OPEN):** **FULL CLOSE.** Test-validation-chain integrity validated post-clean-rebuild via 16/16 module pass (testkeeper 17:22:37Z) + 15F+1E sanity check without enable() call (testkeeper 17:22:37Z) confirming tests genuinely require the B.1+B.1.ii new C function path; not a no-op fallback. Perf-side: A3 perf-regression-bisect workstream WITHDRAWN per Step 0 evidence (testkeeper 20:32:03Z) — original gate (k) BLOCK was a comparison-against-stale-cached-baseline artifact; fresh c4e1900c clean rebuild (GEOMEAN 1.06x) vs HEAD (GEOMEAN 1.07x) shows ~1% delta within noise. NO regression in c4e1900c..HEAD. Per fix #4 reinterpretation: gate (k) does not BLOCK when regression doesn't exist when measured consistently. Per pythia 24 #1 mitigation: C-method named `_enable_support_instrumentation_for_tests` (underscore-prefix at C-method layer + cinderx.test_support wrapper at Python layer). Fix bundle B.1+B.1.ii (config-flag-on-by-test-API + cinderx.test_support wrapper) ready to stage per supervisor 20:33:20Z direction with 'measurement noise-band acknowledged' framing in commit X message. Per-module failure count drops 9→8 once X+Z bundle pushes. Pre-rebuild misdirection (16:59Z testkeeper diagnostic): build-state vs source-state divergence at JitConfig offset 0xe (Hypothesis E, residual-by-elimination after A/B/C/D ruled out per testkeeper 17:17:27Z). Dual-rebuild post-clean-rebuild verification (testkeeper 17:22:37Z + 17:32:33Z) confirms post-clean-build correctness; positive struct-diff confirmation deferred to B6 implementation work. NO B1c entry per testkeeper 14:10:40Z cascade-not-separate empirical correction. Three layers of measurement instrument problems traversed today (Bug A misdirection / Hypothesis E build-state divergence / stale-cached-baseline phantom regression); test-validation chain reached ground truth via clean-rebuild + sanity-check + Step 0 falsifier discipline.

#### B1 Execution Protocol (5 phases, mirrors A1 protocol)

**Phase 0 — Reproduction + classification (testkeeper)**
- Run failing test in isolation: `PYTHONPATH=cinderx/PythonLib python3 -m unittest test.test_jit_support_instrumentation -v`
- Capture stack trace + return code per failing method → `/tmp/B1_repro_TS.log`
- **Classification (Step B1.0 falsifier check):** group the 16 (8F + 8E) by error message + top-of-stack. If split into ≥2 root-cause classes, file each as B1a / B1b / ... separately.
- **Falsifier:** if any test method passes 5/5 in isolation, classify as parallel-only (different bug class). Re-route per A1 protocol Phase 0 falsifier.

**Phase 1 — Hypothesis confirmation OR falsification (generalist + theologian)**
- 1a: pick ONE representative failing test method per root-cause class (per Phase 0 classification)
- 1b: HIR-final-dump for that test's JIT-compiled function path (per memory feedback_lir_dump_first_for_null_deref_sigsegv.md analog for graceful-failure class)
- 1c: cinderx-built-without-JIT differential — does the test pass without -X jit-all?
  - If YES → JIT-induced, hypothesis stands; proceed to Phase 2 with HIR/LIR analysis
  - If NO → cinderx runtime bug; reroute to runtime triage; B1 falsifier-on-bug-class fires
- 1d: vanilla CPython 3.12.13 differential — does the test pass under upstream?
  - If NO → bug is upstream; close-as-upstream OUT of plan
  - If YES → cinderx-side bug confirmed (combined with 1c result)

**Phase 2 — Root cause (generalist implements, theologian reviews)**
- Per A1 lessons (LIR-dump-FIRST for SIGSEGV class; HIR-final-dump-FIRST for graceful-failure class): start with EMPIRICAL HIR/LIR data, not chat-reasoning hypothesis chains
- Discriminate falsifier branches (a)/(b)/(c)/(d) via observable HIR/LIR evidence — same shape as A1 Phase 2 falsifier-discipline
- Identify the specific HIR op or LIR codegen step responsible for missing/dropped/wrong event emission
- Document root cause in fix commit message (mechanism, not just symptom)

**Phase 3 — Fix (generalist)**
- ONE commit per root-cause class (multiple commits if B1.0 surfaced ≥2 classes); each includes regression test (sentinel using sys.setprofile / settrace + JIT-compiled function) in the same commit
- Discipline: address root cause; NO suppression / skip-list addition (per alexie 11:37:49Z 'no more skips' binding)
- **Pre-commit gates (all must pass) per A1 Phase 3 protocol:**
  - 5/5 PASS on the original failing test method(s) in isolation
  - 5/5 PASS on the new sentinel
  - Cinderx-built-with-JIT and cinderx-built-without-JIT both pass (regression check)
  - Criterion (j) full suite at fix-commit vs prior commit (failure count strictly DECREASES — by N for N classes fixed; skip count unchanged)
  - Criterion (l) staged-diff empty post-stage; matches intended files only
  - Gate (k) ABBA: no per-benchmark regressions vs baseline (per c64e7682 lesson; profile/trace HIR ops could affect hot-path perf if added per-call)

**Phase 4 — Theologian falsifier review (theologian, post-commit)**
- Did the fix address the named root cause, or suppress the symptom?
- Does the regression sentinel actually exercise the originally-failing path?
- Are the verification gates documented in commit message (Logos-only per alexie 11:38:36Z, no Ethos appeals)?
- Does the fix close all 16 cluster failures or only the targeted root-cause class? If partial, what's the remaining surface?

**Phase 5 — Plan adaptation log entry (generalist or theologian)**
- Append to the B1 entry adaptation log section with: timestamp, B1.0 classification outcome, fix outcomes per class, evidence pointers (commit SHA + sentinel test paths), any newly-surfaced adjacent bugs (per A1's Bug A pattern: bug-A-as-spawned may surface; treat as separate workstream NOT bundled into B1 closure)

**Phase exit conditions:**
- B1 closes when: B1.0 classification complete + each root-cause class has Phase 3+4+5 done + cluster failure count fully accounted for
- B2 begins per Group B internal ordering (B1→B2→B3 per existing entries)

**Lessons-from-A1 explicitly applied to B1 protocol:**
- Empirical-data-bounded pivots only (no chat-reasoning hypothesis chains; HIR-final-dump FIRST)
- Bug-class naming convention from outset (any spawned-adjacent bug gets explicit naming, not flag-distinction)
- Per-fix-commit-empirical verification: pre-fix-FAIL + post-fix-PASS on the actual failing test (not just on a related repro that may surface different bug class — c64e7682 lesson)
- Gate (k) ABBA verification at fix-commit (HIR-pass changes can have broad perf cost — c64e7682 -9.24% lesson)
- Don't claim closure until empirical pre-fix-fail + post-fix-pass on the actual failing test (4 hr Bug-A-misdirection cycle lesson)
- Future-retry candidates documented in Phase 5 if fix is partial (not all 16 cluster failures resolve in single commit)

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

### B6. JitConfig struct-layout invariance check (latent class; not in failing-test list)

- **Symptom (per testkeeper 17:17:27Z Hypothesis E identification):** build-time JitConfig struct layout can diverge from runtime expected layout if any struct field is added/removed/reordered between binary-build-time and current source. Today's B1 cycle: Hypothesis E identified s_config offset 0xe field as the divergent point. Binary checked specialized_opcodes=true (or whatever field landed at offset 0xe in build-time struct layout) instead of intended support_instrumentation=false, causing patchSysSetProfileAndSetTrace to fire unconditionally at startup despite source default false. Result: tests passed for the wrong reason (already-active patching), masking the true B.1 fix mechanism.
- **Why this is B6 and not in failing-test list:** struct-layout-divergence is a build-state class issue; doesn't manifest as test failure when binary IS rebuilt cleanly (today's clean rebuild restored expected behavior, per testkeeper 17:22:37Z + 17:32:33Z dual-rebuild confirmation). NO test in current failing list exercises layout-divergence directly. Defensive engineering against future occurrence; not a current bug.
- **Hypothesis (root cause):** no compile-time or runtime check enforces JitConfig struct layout invariance. Field reorders/additions during normal development can silently shift field offsets without breaking compilation; runtime code reads via &s_config + offset (offset computed at compile time of consuming code, not struct definition). Mismatch silently exists until someone notices wrong-field behavior.
- **Verification mode:** clean rebuild + Hypothesis E direct test (sys.setprofile patching state at fresh Python startup pre-enable() call) per supervisor 17:18:24Z methodology.
- **Fix candidates:**
  - (a) #if static_assert in pyjit.cpp asserting offsetof(JitConfig, support_instrumentation). Catches at compile-time of any consumer file.
  - (b) Runtime startup sanity check comparing expected vs actual layout (e.g., sentinel-canary at end of struct). Catches at startup; adds startup cost.
  - (c) CI gate: build twice (clean + incremental) and diff-check structures via nm/objdump. Catches in CI; doesn't catch dev-environment.
- **Falsifier branches:** as enumerated in fix candidates; supervisor-scope architectural decision when B6 retry begins.
- **Fix-success:** structural invariant enforced (one of a/b/c); regression test via simulated layout drift; gate (j) failure count UNCHANGED (no test failing for B6).
- **Owner:** generalist (impl), testkeeper (verify), theologian (root-cause + fix-candidate architectural validation pre-implementation).
- **Priority:** LOWER than A1 per A-class-partial-close priority rule. B6 is latent (does not affect failure count); fix eliminates a build-state silent-validation failure class.
- **Trigger condition for B6 retry workstream:** retry begins when EITHER (a) ANY future bug investigation surfaces struct-layout-divergence as suspected mechanism OR (b) supervisor explicitly elevates B6 priority due to recurrence. Default: do NOT begin B6 work until either elevation OR accretion-budget review surfaces this as next-priority B-class.
- **Cross-references:**
  - testkeeper 17:17:27Z Hypothesis A/B/C/D/E enumeration + Hypothesis E identification
  - theologian 17:18:15Z Hypothesis E theological framing + struct-layout-invariance discipline candidate
  - gatekeeper 17:18:56Z (h.1.b) split proposal (B6 IS the deferred-to-B-class artifact for h.1.b)
  - supervisor 17:18:24Z + 17:19:49Z (h.1) split + (h.1.b) → triage_plan placement direction
  - testkeeper 17:22:37Z + 17:32:33Z dual-rebuild post-clean-rebuild verification (post-clean-build correctness; does NOT positively confirm struct-layout-divergence mechanism per pythia 27 #3)
  - Pre-rebuild .so overwritten before objdump diff feasible (testkeeper 17:27:01Z); positive struct-diff confirmation deferred to B6 implementation work per option (c) (theologian 17:26:57Z + supervisor 17:28:42Z endorsement)

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

- 2026-04-22T18:58:32Z — B1 — INVESTIGATION-RE-OPEN per gate (k) BLOCK post-clean-rebuild ABBA — fix B.1+B.1.ii (config-flag-on-by-test-API + cinderx.test_support wrapper + pythia 24 #1 underscore-prefix mitigation at C-method) test-validation-chain integrity confirmed via 16/16 module pass + 15F+1E sanity check without enable() call (testkeeper 17:22:37Z); perf regression cause is INDEPENDENT of B.1 (regression present on pre-rebuild stale build that did NOT contain B.1 changes); per gate (k) BLOCK = bundle BLOCK regardless of attribution (theologian fix #4 + supervisor 18:08:11Z): X + Z bundle held pending separate bisect workstream (47 commits in c4e1900c..HEAD range; cached intermediate ABBA at c1982ca5 available per testkeeper 18:58:32Z diagnostics); Y' (this commit) ships standalone per content-categorization (theologian 18:54:53Z + supervisor 18:55:08Z) with A2 ownership encoding (Edit 2) + hypothesis-revision-budget cross-cutting rule (Edit 4) + B6 struct-layout entry (Edit 5). Pre-rebuild misdirection (16:59Z testkeeper diagnostic): build-state vs source-state divergence at JitConfig offset 0xe (Hypothesis E, residual-by-elimination after A/B/C/D ruled out per testkeeper 17:17:27Z); dual-rebuild post-clean-rebuild verification (testkeeper 17:22:37Z + 17:32:33Z) confirms post-clean-build correctness; does NOT positively confirm struct-layout-divergence mechanism per pythia 27 #3 (overreach retracted per theologian 18:07ish + supervisor 18:08:11Z); positive struct-diff structurally unobtainable (pre-rebuild .so overwritten per testkeeper 17:27:01Z); deferred to B6 implementation work. NO B1c entry per testkeeper 14:10:40Z cascade-not-separate empirical correction. Bundle X + Z re-attempt awaits perf-regression-bisect resolution.
- 2026-04-22T19:20:18Z — A3 — NEW workstream entry per pythia 30 #2 chat-only-deferral surface — perf-regression-bisect workstream (c4e1900c..HEAD -10% geomean, 6 new losers + 4 winner→loser flips) added as Group A entry with named owners (testkeeper coordinate + generalist build-cycles + theologian falsifier), 4-step bisect plan (Step 0 in flight per testkeeper 19:03:21Z, ~110 min ETA), hot-spot candidates (07d938f8 / 861762a0 / 46c26256 / 794d8270), and quantitative threshold per supervisor 19:20:18Z (5% delta per memory feedback_gate_j_skip_variance.md operationalized). This commit (Y'') ships standalone with the A3 entry as artifact-side resolution to pythia 30 #2 (bisect workstream was chat-only post-Y'); recursive-policy-collapse risk closed for A3. X+Z bundle remains held pending A3 resolution per fix #4.
- 2026-04-22T20:32:03Z — A3 — WITHDRAWN per Step 0 empirical evidence — fresh c4e1900c clean rebuild ABBA (testkeeper 20:32:03Z) GEOMEAN 1.06x vs HEAD GEOMEAN 1.07x: ~1% delta within noise band. Cached baseline /tmp/abba_fresh_c4e1900c_v2.txt (Apr 22 02:49Z, GEOMEAN 1.19x) was environment-stale. Per alexie 19:49:33Z falsifier discipline + testkeeper 20:32:03Z falsifier-checklist: source-code-invariant + measurement-instrument-invariant + cached-vs-fresh-differ-significantly → parsimonious explanation = environment-cause (alexie item 5: system load / CPU thermal / cohabitant-process state at 02:49Z cache time). The 47-commit bisect plan + Steps 1-3 + hot-spot candidates UNNECESSARY — no regression to bisect. Per pythia 27 #3 + alexie's epistemic discipline: the original "winner→loser" pattern (gen_nested 1.19x→0.63x etc.) was pre-existing in c4e1900c too when measured in current environment; NOT new regressions. Three layers of measurement instrument problems traversed today (Bug A wrong-fix misdirection / Hypothesis E build-state struct-layout divergence / stale-cached-baseline phantom regression); honest accounting via clean-rebuild + sanity-check + Step 0 falsifier discipline reached ground truth.
- 2026-04-22T20:32:03Z — B1 — INVESTIGATION-RE-OPEN → FULL CLOSE per A3 WITHDRAWN — gate (k) BLOCK reinterpreted under fix #4 (no regression = no BLOCK); per supervisor 20:33:20Z direction: bundle X+Z stages with 'measurement noise-band acknowledged' framing in commit X message. Y''' (this commit) ships A3 status update + B1 closure update + this Phase 5 log entry; X commits separately (generalist owns); Z commits separately (testkeeper owns); 3-commit bundle X+Z+Y''' unblocks per fix #4 reinterpretation. Per-module failure count drops 9→8 once X+Z pushes.
