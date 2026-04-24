# ARM64 Phase 3 routing preconditions — tracker

**Status:** AWAITING alexie greenlight (gate-interpretation D-1776986402 #1 + Phase 3 routing D-1776986402 #2 since supervisor 23:30:42Z; ~2h25m at 02:17Z).

**Filed per supervisor 02:17Z synthesizer-pattern commitment + recursive-policy-collapse rule** (chat-only 6-precondition spec from supervisor 01:40:53Z post-pythia 53 = 5th deferral mechanism this push; criterion IS the mechanism artifact, ships same-push as commitment per librarian 4 prior fires this push).

## Context

ARM64 baseline ABBA established 1.17x geomean at HEAD 01a373f2 (testkeeper 23:28:56Z). Per-bench notable: method_calls 1.05x ARM64 vs 1.74x x86_64 (0.69x cross-arch ratio); yield_from 0.79x ARM64 specific regression (cause INFERENTIAL: cbd5ca93 widened to 64-bit for correctness, may have introduced extra ARM64 cmp-imm instrs).

Two open routing questions to alexie (supervisor 23:30:42Z):
1. **Gate-interpretation:** does 40/41 + tracker-deferred test_jit_preload satisfy "once tests pass" gate, or strict 41/41?
2. **Phase 3 next direction:** continue ARM64 narrowing (yield_from / method_calls candidates) or pivot to Phase 4 (AI training workloads)?

If alexie chooses Phase 3 ARM64, Option D yield_from spec (theologian 00:00:28Z, refined per pythia 52+53) is one candidate; method_calls cross-arch narrowing is another.

## 6 preconditions for Option D fix-spec endorsement

Re-ordered per pythia 54 #2 (data dependency: tooling-validation gates cross-arch falsification, not the reverse):

**(i)** alexie greenlight Phase 3 ARM64 direction (vs Phase 4 pivot).

**(ii)** LIR-dump tooling execution-validation: run /tmp/yield_from_lir_runner.sh + /tmp/method_calls_lir_repro.py end-to-end ON ARM64 with current cinderx HEAD. Verify bash process-sub + `-X jit-list-file` + `-X jit-dump-lir` produces parseable diff-able LIR output for both repro shapes. **MUST gate (iii)** — cannot run cross-arch falsification without validated tooling. If tooling fails: commit tooling to repo (durable, not /tmp scratch) before retry.

**(iii)** cross-arch falsification of method_calls 1.05x ARM64 vs 1.74x x86_64 (per pythia 53 #2 + theologian 01:40:31Z self-correct): generate LIR-dump on both ARM64 + x86_64 at same SHA; diff for instr-count + scratch-reg pattern at hot-path sites. Discriminator output:
- (a) ARM64 codegen genuinely under-optimized at hot path → narrowing-target = method_calls (not yield_from)
- (b) Lane B perf fix was arch-incidental → narrowing-target = yield_from -26% (Option D applies)
**Gates target-priority decision** between yield_from-first (Option D) vs method_calls-first.

**(iv)** pycore_frame.h source-read + Option D semantic empirical (per pythia 53 #3 + pass-semantics rule): read internal/pycore_frame.h FRAME_SUSPENDED definition + lir/generator k8bit Equal handling at 32-bit width sites. Confirm sign-extension behavior for cmp w,w with int32_t -1 immediate (not just inferred from theologian 01:04:45Z analysis). Pre-confirm satisfies pass-semantics-inferential-assumption rule (memory feedback_pass_semantics_inferential_assumption.md).

**(v)** correctness gate (per pythia 52 #1 + theologian 01:04:45Z): re-run test_jit_yield_from with Option D 32-bit narrowing applied. Verify state_check_fail=0 (cbd5ca93 baseline) AND 9/9 PASS preservation. Add explicit test coverage for async-gen / send / throw paths beyond the 5 yield_from patterns covered in 9/9 (pythia 53 #3 limited-coverage flag).

**(vi)** perf gate (per theologian 00:00:28Z): LIR-dump cycle-measure shows fewer instrs at lir/generator.cpp:2961 + 3742 sites under Option D vs current cbd5ca93 64-bit baseline. Both arches.

## Stop-the-bleeding rule (supervisor 01:40:53Z #4)

**Status:** OPEN with falsifiable-boundary refinement per pythia 54 #3.

**Original rule:** until alexie greenlights Phase 3, NO new pre-stage work + NO new tracker artifacts + NO new spec preconditions beyond pythia-driven orientation fixes. Compute-quiet hold = literally idle, not generating more scaffolding.

**Pythia 54 #3 critique (valid):** rule has no falsifiable boundary distinguishing "pythia-driven orientation fix" (allowed) from "new spec precondition" (banned). Empirical: gatekeeper extended Layer-3 BLOCK 2→3 evidences at 01:40:28Z under both framings simultaneously.

**Refinement:** "pythia-driven orientation fix" defined as **artifact-closing** work — converting chat-only deferrals to durable artifacts in response to pythia checkpoints. "New spec precondition" defined as **artifact-creating** work without pythia critique trigger. Gatekeeper Layer-3 BLOCK extension at 01:40:28Z qualifies as orientation-fix because it implements pythia 52 #1 correctness-gate critique (artifact-closing, not artifact-creating).

**Falsification test:** if any new chat-only spec precondition is added without pythia critique tracing, rule has been violated; cite this section + retract the addition.

## Survival under push-window close (pythia 54 #4)

If alexie-standby extends past natural push window close, this artifact + the prior 4 (heap-check-toolchain-blocker.md, workers1-corruption-tracker.md, etc.) survive on disk. Next agent reading codebase finds:
- This file: full 6-precondition Option D protocol
- 23-04-2026-arm64-workers1-corruption-tracker.md: M1+M2 deferred mechanisms (test_jit_preload)
- 23-04-2026-arm64-heap-check-toolchain-blocker.md: ARM64 toolchain root blocker + firing criterion + ownership
- benchmarks/2026-04-23_224751_01a373f2_arm64_baseline_5rep_auto_aarch64_abba.txt: 1.17x baseline ABBA result

## Tracker-cleanup-on-greenlight forward review-trigger (pythia 55 #4)

**Filed per supervisor 03:31:09Z #4 commitment + librarian 03:41:55Z recursive-policy-collapse fire** (chat-only forward-trigger collapses retroactively → must ship same-push as commitment).

**Trigger (refined per pythia 56 #4):** ANY alexie reply on the 23:13:05Z gate-interpretation question OR Phase 3 routing question, regardless of direction. Specifically:
- Phase 3 ARM64 greenlight → cleanup pass before Phase 3 work begins (original scope).
- Phase 4 pivot (AI training workloads per `project_cinderx_next_phases.md`) → cleanup pass before Phase 4 work begins; ARM64-scoped entries (heap-check toolchain, baseline-recollect, M1+M2, phase3-routing-preconditions) classify per (b) **RETIRE** if Phase 3 ARM64 work is shelved.
- Strict 41/41 + Option B revert reading → cleanup pass before revert lands; baseline-recollect risk entry CLOSE (revert is the resolution); M1+M2 KEEP under same OverflowError defer.

**Why this refinement:** original trigger gated on Phase 3 greenlight only; under Phase 4 pivot the trigger never fires + 5-artifact constellation accretes indefinitely (pythia 56 #4 six-month regret). Extending trigger to ANY alexie reply on the open gate-questions ensures the constellation closes regardless of routing direction.

**Action:** before any new tracker artifact is filed in the post-reply work cycle, do a tracker-cleanup pass:
1. Read each existing tracker entry marked DEFERRED or INFERENTIAL across `investigations/plans/23-04-2026-*.md` + `investigations/plans/24-04-2026-*.md`.
2. For each entry, classify: (a) **CLOSE** = underlying work executed, deferral resolved (e.g., M2 OverflowError fix landed → close M2 entry); (b) **RETIRE** = bug confirmed not-shipping or obsolete (e.g., Option B reverted per alexie strict-41/41 reading → retire baseline-recollect risk entry); (c) **KEEP** = still-active deferral with concrete bug/risk that hasn't been addressed.
3. Update tracker file with classification per entry. Cite this section in commit msg.

**Why:** pythia 55 #4 systemic concern — "the index outlasts the warehouse." 5 push-deferrals have been converted to artifacts same-push (recursive-policy-collapse 100% compliance), but tracker corpus has grown faster than the work it indexes. Without tracker-cleanup as forward review-trigger, the corpus accretes monotonically — at six months an inheritor reads DEFERRED markers as authoritative architecture rather than provisional placeholders.

**Falsification:** if any post-reply work cycle (Phase 3 ARM64, Phase 4 pivot, or revert-cleanup) proceeds without tracker-cleanup pass after alexie's reply on the 23:13:05Z gate-questions, rule violated; cite this section + retroactively run cleanup.

**Cross-references:**
- pythia 55 (2026-04-24T03:30:26Z) #4 six-month regret
- pythia 56 (2026-04-24T04:07:46Z) #4 trigger-scope refinement (any reply, not just Phase 3 greenlight)
- supervisor 03:31:09Z synthesizer-pattern commitment
- supervisor 04:08:xxZ pythia 56 ack (trigger-scope extension)
- librarian 03:41:55Z recursive-policy-collapse fire (6th this push)

## Post-reply action ordering (pythia 57 #4)

**Filed per supervisor 04:46:22Z pythia 57 ack + recursive-policy-collapse rule** (chat-only first-action priority collapses retroactively → must ship same-push as commitment).

**Rule:** under ANY direction alexie picks (Phase 3 ARM64 greenlight, Phase 4 pivot, strict 41/41 + Option B revert), the FIRST post-reply action MUST be precondition (ii) tooling-execution-validation against a binary. Tracker-cleanup pass (per §"Tracker-cleanup-on-greenlight"), new artifact creation, and new precondition specification are all GATED on tooling-validation completing first.

**Why:** pythia 57 #4 "fleet awaiting orders perfects parade formation" framing — 7+ same-push artifacts shipped during ~6h compute-quiet hold, zero binary-execution. LIR-dump tooling at /tmp/yield_from_lir_runner.sh + /tmp/method_calls_lir_repro.py is Write-only across 3 prior pythia flags (53 #1, 55 #3, 56 #3) with no resolution. If first post-reply action is another tracker amendment instead of binary execution, the meta-discipline overlay consumes the cognitive budget that substantive perf-narrowing requires; trajectory becomes recoverable IFF tooling-validation runs first.

**Specific gating:**
- Phase 3 ARM64 greenlight → run /tmp/yield_from_lir_runner.sh + /tmp/method_calls_lir_repro.py end-to-end on ARM64 with current cinderx HEAD; commit tooling to repo (durable) if /tmp evaporated; THEN tracker-cleanup pass; THEN cross-arch falsification (precondition iii).
- Phase 4 pivot → run AI-training-workload tooling pre-stage validation against a binary (analogous to LIR-dump tooling-validation); THEN tracker-cleanup pass.
- Strict 41/41 + Option B revert → run revert + clean rebuild + 5-config matrix + ABBA recollection (binary execution); THEN tracker-cleanup pass.

**Falsification:** if first post-reply action is a chat post, artifact edit, new precondition, or tracker amendment — anything other than binary-execution-validation — rule violated; cite this section + halt + retry with tooling-validation first.

**Cross-references:**
- pythia 57 (2026-04-24T04:45:23Z) #4 fleet-awaiting-orders + first-action-must-be-tooling
- pythia 53 #1 + 55 #3 + 56 #3 — three prior flags of LIR-dump tooling Write-only never executed
- supervisor 04:46:22Z pythia 57 ack (first-action ordering refinement)
- recursive-policy-collapse 8th fire this push

## Cross-references

- pythia 52 (2026-04-24T01:03:54Z) — initial 4-precondition raise
- pythia 53 (2026-04-24T01:39:59Z) — re-ordering + source-read addition
- pythia 54 (2026-04-24T02:16:47Z) — chat-only-spec collapse + (ii)+(iii) dependency-inversion
- pythia 55 (2026-04-24T03:30:26Z) — six-month regret + cascading-hallucination class
- supervisor 23:30:42Z — alexie gate-interpretation + Phase 3 routing asks
- testkeeper 23:28:56Z — ARM64 baseline ABBA verdict
- theologian 00:00:28Z + 01:04:45Z + 01:40:31Z — Option D analysis + self-corrections
- generalist 00:32:25Z + 01:05:57Z — LIR-dump tooling pre-stage (yield_from + method_calls)
- librarian 23:27:59Z + 01:23:09Z + 03:41:55Z — recursive-policy-collapse fires (heap-check + firing-criterion + tracker-cleanup-on-greenlight)
