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

## Cross-references

- pythia 52 (2026-04-24T01:03:54Z) — initial 4-precondition raise
- pythia 53 (2026-04-24T01:39:59Z) — re-ordering + source-read addition
- pythia 54 (2026-04-24T02:16:47Z) — chat-only-spec collapse + (ii)+(iii) dependency-inversion
- supervisor 23:30:42Z — alexie gate-interpretation + Phase 3 routing asks
- testkeeper 23:28:56Z — ARM64 baseline ABBA verdict
- theologian 00:00:28Z + 01:04:45Z + 01:40:31Z — Option D analysis + self-corrections
- generalist 00:32:25Z + 01:05:57Z — LIR-dump tooling pre-stage (yield_from + method_calls)
- librarian 23:27:59Z + 01:23:09Z — recursive-policy-collapse fires (heap-check + firing-criterion)
