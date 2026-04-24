# ARM64 Phase 3 — meta-discipline rules + forward review-triggers

**Status:** OPEN. Filed per pythia 58 #4 (2026-04-24T05:21:30Z) bloat-critique → split from 24-04-2026-arm64-phase3-routing-preconditions.md to separate meta-discipline scaffolding from substantive Option D 6-precondition spec. Net new artifact count +1, net new content 0 (reorganization).

**Why split:** pythia 58 #4 framing — 5 meta-discipline sections (115 lines) accreted in phase3-routing-preconditions.md alongside the 18-line Option D spec, obscuring which is bug-spec and which is process scaffolding. Inheritor at six months reads disciplinary overlay as authoritative architecture vs. provisional process. Split: bug-spec stays in phase3-routing-preconditions.md; process scaffolding lives here.

**Companion artifact:** `investigations/plans/24-04-2026-arm64-phase3-routing-preconditions.md` (Option D 6-precondition spec + context).

## Stop-the-bleeding rule (supervisor 01:40:53Z #4)

**Status:** OPEN with falsifiable-boundary refinement per pythia 54 #3.

**Original rule:** until alexie greenlights Phase 3, NO new pre-stage work + NO new tracker artifacts + NO new spec preconditions beyond pythia-driven orientation fixes. Compute-quiet hold = literally idle, not generating more scaffolding.

**Pythia 54 #3 critique (valid):** rule has no falsifiable boundary distinguishing "pythia-driven orientation fix" (allowed) from "new spec precondition" (banned). Empirical: gatekeeper extended Layer-3 BLOCK 2→3 evidences at 01:40:28Z under both framings simultaneously.

**Refinement:** "pythia-driven orientation fix" defined as **artifact-closing** work — converting chat-only deferrals to durable artifacts in response to pythia checkpoints. "New spec precondition" defined as **artifact-creating** work without pythia critique trigger. Gatekeeper Layer-3 BLOCK extension at 01:40:28Z qualifies as orientation-fix because it implements pythia 52 #1 correctness-gate critique (artifact-closing, not artifact-creating).

**Falsification test:** if any new chat-only spec precondition is added without pythia critique tracing, rule has been violated; cite this section + retract the addition.

## Survival under push-window close (pythia 54 #4)

If alexie-standby extends past natural push window close, this artifact + the prior 4 (heap-check-toolchain-blocker.md, workers1-corruption-tracker.md, etc.) survive on disk. Next agent reading codebase finds:
- This file: meta-discipline rules + forward review-triggers
- 24-04-2026-arm64-phase3-routing-preconditions.md: Option D 6-precondition spec + context
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
- supervisor 04:08:31Z pythia 56 ack (trigger-scope extension)
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

**Gatekeeper Layer-3 enforcement (per pythia 58 #1 + gatekeeper 05:22:51Z):** BLOCK any commit/post citing artifact/spec/precondition advancement BEFORE binary-execution-validation completes. Required evidence = testkeeper empirical post showing "tooling produces parseable diff-able output on ARM64" or equivalent execution evidence.

**Cross-references:**
- pythia 57 (2026-04-24T04:45:23Z) #4 fleet-awaiting-orders + first-action-must-be-tooling
- pythia 58 (2026-04-24T05:21:30Z) #1 self-authored-rule no-enforcement → gatekeeper Layer-3 extension
- pythia 53 #1 + 55 #3 + 56 #3 — three prior flags of LIR-dump tooling Write-only never executed
- supervisor 04:46:22Z pythia 57 ack (first-action ordering refinement)
- gatekeeper 05:22:51Z Layer-3 BLOCK extension
- recursive-policy-collapse 8th fire this push

## Cross-references (this file)

- pythia 58 (2026-04-24T05:21:30Z) #4 — bloat critique → split trigger
- supervisor 05:25:xxZ pythia 58 ack — split execution (9th RPC fire)
- medic 05:25:18Z — caught self-classification carve-out, forced split
- 24-04-2026-arm64-phase3-routing-preconditions.md — companion artifact (Option D bug-spec)
