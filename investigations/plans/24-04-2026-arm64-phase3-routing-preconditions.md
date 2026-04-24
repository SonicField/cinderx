# ARM64 Phase 3 routing preconditions — Option D bug-spec

**Status:** AWAITING alexie greenlight (gate-interpretation D-1776986402 #1 + Phase 3 routing D-1776986402 #2 since supervisor 23:30:42Z; ~2h25m at 02:17Z).

**Filed per supervisor 02:17Z synthesizer-pattern commitment + recursive-policy-collapse rule** (chat-only 6-precondition spec from supervisor 01:40:53Z post-pythia 53 = 5th deferral mechanism this push; criterion IS the mechanism artifact, ships same-push as commitment per librarian 4 prior fires this push).

**Companion artifact (meta-discipline scaffolding):** `investigations/plans/24-04-2026-arm64-meta-discipline.md` — stop-the-bleeding rule, post-reply action ordering, tracker-cleanup-on-greenlight forward review-trigger, push-window-survival list. Split per pythia 58 #4 (2026-04-24T05:21:30Z) bloat critique to keep this file scoped to substantive Option D bug-spec.

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

## Cross-references

- pythia 52 (2026-04-24T01:03:54Z) — initial 4-precondition raise
- pythia 53 (2026-04-24T01:39:59Z) — re-ordering + source-read addition
- pythia 54 (2026-04-24T02:16:47Z) — chat-only-spec collapse + (ii)+(iii) dependency-inversion
- pythia 55 (2026-04-24T03:30:26Z) — six-month regret + cascading-hallucination class
- pythia 56 (2026-04-24T04:07:46Z) — trigger-scope refinement (in companion artifact)
- pythia 57 (2026-04-24T04:45:23Z) — fleet-awaiting-orders + first-action ordering (in companion artifact)
- pythia 58 (2026-04-24T05:21:30Z) — bloat critique → split into companion artifact
- supervisor 23:30:42Z — alexie gate-interpretation + Phase 3 routing asks
- testkeeper 23:28:56Z — ARM64 baseline ABBA verdict
- theologian 00:00:28Z + 01:04:45Z + 01:40:31Z — Option D analysis + self-corrections
- generalist 00:32:25Z + 01:05:57Z — LIR-dump tooling pre-stage (yield_from + method_calls)
- librarian 23:27:59Z + 01:23:09Z + 03:41:55Z — recursive-policy-collapse fires (heap-check + firing-criterion + tracker-cleanup-on-greenlight)
- `investigations/plans/24-04-2026-arm64-meta-discipline.md` — companion artifact (process scaffolding)
