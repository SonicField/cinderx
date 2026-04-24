# L2b regression-probes follow-up

> **RPC-deferral grandfathered:** this artifact ships under owner+escalation enforcement (testkeeper 60min post-push extraction commitment + supervisor escalation backstop), NOT explicit expiry-date + CI/auto-check.
>
> **Forward standard (per pythia 76 catch + theologian meta-rule 2026-04-24T18:39Z):** future RPC deferral artifacts in this repo MUST include explicit expiry-date in artifact body + CI/auto-check mechanism that fires on expiry; doc-only-as-RPC stretches without both clauses are out-of-scope.

**Status:** open follow-up; deferred from L1+L2b+sibling-audit bundle push
(supervisor 2026-04-24T18:09:40Z) — to ship as separate commit on
speculation-experiment after the bundle lands.

**Owner:** testkeeper

**Trigger to close:** L1+L2b bundle merge to speculation-experiment +
gatekeeper green on the bundle push.

## Why this exists (artifact for chat-only deferral)

Per `feedback_recursive_policy_collapse_pattern.md`, chat-only deferrals
collapse without an artifact. This file is the artifact. Librarian flagged
the collapse risk at 2026-04-24T18:16:48Z; supervisor confirmed deferral
at 2026-04-24T18:09:40Z.

## Background

L2b (cinderx-vendored asmjit ARM64 `emitCondBranchRelax` CodeBuffer
overflow into adjacent Zone-arena `LabelLink` memory) was empirically
pinned via:
- generalist 2026-04-24T17:39:03Z R2 cumulative-revert: ab247c63 +
  e8159ccd reverted together → 0/30 crashes
- testkeeper 2026-04-24T17:49:24Z N=200 baseline: revert-e8159ccd-only
  was 23/200 = 11.5% [Wilson 95% 7.8%, 16.7%] (not load-bearing on its
  own; ab247c63 is load-bearing)
- 0/90 fix-verify across 3 independent runs / 2 scripts / 2 agents on
  the F2' fix (`ensureSpace(8)` + `bufferData` refresh in
  `emitCondBranchRelax`).

Reproducer that reliably triggers pre-fix:
`probe_warmup_bisect.py --n=1` driving 8 richards hot funcs from
`benchmark_cinderx.py` (warmup-then-`force_compile` pattern packs the
asmjit CodeBuffer remainder to the 4-7-byte window where
`emitCondBranchRelax` overflowed).

testkeeper investigated synthetic standalone reproducers
(8-func and 50-func with conditional branches) on 2026-04-24T18:08Z;
both were 0/30 on the buggy build — could not fail. The L2b bug is
sensitive to the specific code shape that the richards benchmark
generates; synthetic stand-ins do not pack the CodeBuffer to the
trigger boundary. Per testkeeper rule "every test must be able to
fail," a synthetic test would be decoration; not shipped.

## Deliverables (this follow-up)

1. `cinderx/tools/regression_probes/probe_warmup_bisect.py` — copied
   from the empirical reproducer at
   `/home/alexturner/local/vib-jit-l2b/cinderx/probe_warmup_bisect.py`
   (99 LOC).
2. `cinderx/tools/regression_probes/richards.py` — extracted from
   `benchmark_cinderx.py` lines 380-755 (~376 LOC: `_RPacket`,
   `_RTaskState`, `_RTaskWorkArea`, `_RTask` and subclasses,
   `_richards_schedule`, `_richards_run_once`, `bench_richards_full`).
3. `cinderx/tools/regression_probes/README.md` documenting:
   - manual invocation: `for i in $(seq 1 30); do python tools/regression_probes/probe_warmup_bisect.py --n=1; done`
   - acceptance: 0/30 on a healthy ARM64 build; pre-fix
     (~11.5% crash rate, Wilson 95% [7.8, 16.7]) is the negative
     baseline.
   - cite to the L2b fix-spec
     (`investigations/plans/24-04-2026-l2b-asmjit-relax-codebuffer-overflow-fix-spec.md`).

## Acceptance for this follow-up to be closed

- All three files committed to speculation-experiment as a separate
  commit (not amended into the L2b bundle, per supervisor 18:09:40Z).
- The probe runs end-to-end on the post-bundle build with 0/30 crashes
  (testkeeper to verify; cite raw `for`-loop output in the closure
  post-push report).
- A 1-line entry added to this file under "Closure record" with the
  commit SHA and verification timestamp.

## Closure record

(empty — fill at closure)
