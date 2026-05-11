---
status: DRAFT — pending alexie scope verdict + librarian D-1778112324 pre-vs-post-port primary-source verify
owner: theologian
trigger:
  - supervisor 2026-05-11 12:42:15Z point (4): "Even if alexie picks ship-narrow, the PR body's 'what this does NOT do' section should record empirically: 'broader-suite control bench measured 5 benchmarks showing 4-6% slowdown; mechanism currently unconfirmed; investigation tracking continues.' That preserves the bisect trail. Not committing to that text yet — gates on alexie scope decision + librarian (3) outcome."
  - pythia 2026-05-11 13:19:08Z point (2): "Theologian v5 IDEA-spec text 'staged in context' only — no artifact, no commit, no investigations/ file. Fixup just MandatoryRestart'd 2 agents at 12:53:54Z. If theologian's session restarts before alexie verdict lands, the v5 PR-body 'what this does NOT do' empirical-record draft vanishes."
  - memory project_recursive_policy_collapse_pattern.md: deferral-mechanism artifacts must ship in same push; chat-only deferrals don't survive. Memory feedback_recursive_policy_collapse.md (theologian binding): demand artifact in bundle.
scope: Draft text for IDEA-spec v5 PR body "what this does NOT do" empirical-observation paragraph addition. NOT yet incorporated into IDEA-spec on speculation-experiment; this artifact is RPC-collapse-mitigation only.
audience: theologian (executor on v5 commit when gates resolve); supervisor (sequencer); librarian (RPC-collapse witness)
---

# Cluster 5 — PR-body Bisect-trail Amendment (DRAFT v5)

## What this document is

A pre-staged DRAFT of additional text for the PR body "What this patch does NOT do" section in `2026-05-11-cluster5-ic-churn-detection-pr-idea-articulation.md` (currently at speculation-experiment cb074dd0 v4). The text is gated on two outcomes per supervisor 12:42:15Z point (4):
1. alexie scope verdict on the open 3Q stack (instrument-1 / ARM control / ship-narrow)
2. librarian primary-source verify on D-1778112324 yield_from substrate (pre-IDEA-port vs post-IDEA-port)

Rather than holding the text in chat-only deferral (RPC-collapse pattern per memory), the text is committed here as a durable artifact. When the gating outcomes resolve, the corresponding edit to the IDEA-spec on speculation-experiment proceeds via the worktree pattern; the executor lifts the relevant block from this draft and adapts it to the resolved scope.

## Draft text — to insert into IDEA-spec PR body "What this patch does NOT do" section as item 3

```
3. **Broader-suite empirical observation (mechanism unconfirmed).** A
   control benchmark on the same upstream master HEAD without this
   patch (otherwise identical build flags + bench harness, reps=5,
   full 29-bench subprocess ABBA) measured 5 benchmarks showing
   4-6% slowdown vs the patched build: chaos_game (-0.06x),
   richards_full (-0.05x), spectral_norm (-0.06x), try_except_callee
   (-0.04x), yield_from (-0.04x). The mechanism is not currently
   confirmed; an instrumented run that records per-type invalidation
   counts during these benches would distinguish whether the
   regressions are caveat-2-shape (slow-path-lookup overhead on
   volatile-classified hot-path types) or a different mechanism
   (always-paid per-type counter cost, compiler-inlining shifts from
   the +21-line code-size addition, or another pathway). The
   regressions are documented here so future bisects can correlate;
   investigation tracking continues outside this PR.
```

## Conditional language — adapt based on alexie verdict + librarian outcome

The above draft assumes ship-narrow scope (alexie picks option 3) AND librarian-verify on D-1778112324 confirms post-IDEA-port substrate (cross-cycle persistence stands).

If alexie picks **instrument-1 first** (option 1) AND the instrumentation **falsifies** caveat-#2-shape on yield_from (zero threshold-crosses for hot-path types):
- Replace "an instrumented run that ... would distinguish" with "an instrumented run on yield_from established that no hot-path type crosses the 10-invalidation threshold during the bench, falsifying caveat-2-shape attribution for at least that bench. Mechanism investigation continues for the remaining 4 benchmarks."

If alexie picks **instrument-1 first** AND the instrumentation **confirms** caveat-#2-shape on yield_from (threshold-crosses present):
- Replace "an instrumented run ... would distinguish" with "an instrumented run on yield_from confirmed hot-path types crossing the 10-invalidation threshold, consistent with caveat-2-shape (slow-path-lookup overhead on volatile-classified types). The remaining 4 benchmarks plausibly share the mechanism but have not been independently instrumented."

If alexie picks **ARM control-ABBA** (option 2) — independently of instrument-1 — and ARM control reveals different broader-suite distribution than x86:
- Add to the paragraph: "ARM control bench measured a different distribution of broader-suite slowdowns than x86; cross-arch the regressions are not identical."

If librarian-verify on D-1778112324 reveals the May 7 yield_from -12.9% measurement was on **PRE-IDEA-port substrate**:
- This DIRECTLY FALSIFIES IDEA-attribution for yield_from. The 4-6% slowdown framing for yield_from must be removed from the paragraph; remaining 4 benchmarks (chaos_game, richards_full, spectral_norm, try_except_callee) keep the framing.
- Additionally: librarian D-1778503034 cross-cycle persistence inference is invalidated; cross-cycle convergence becomes coincidental-magnitudes, not corroborating evidence (per pythia 272 second-order risk).

## Cross-references at execution time

When the gating outcomes resolve and v5 IDEA-spec commit executes:
- Source-of-truth for v5 commit message + body: `git show {v5-sha}:investigations/plans/2026-05-11-cluster5-ic-churn-detection-pr-idea-articulation.md`
- This draft remains as historical record (not deleted post-v5); status field at top updated to "RESOLVED — incorporated into IDEA-spec v5 at {sha}"
- Generalist re-amends cluster5-pr branch commit (currently 0c99ac89) with v5 commit-message text via worktree-edit-amend pattern (same as v3 → v4 transition)

## What this draft does NOT do

- Does NOT modify IDEA-spec at speculation-experiment cb074dd0; this is a separate artifact.
- Does NOT pre-commit to a mechanism attribution for the 5 broader-suite slowdowns; explicitly preserves the "mechanism unconfirmed" framing per testkeeper 2026-05-11 11:52:22Z falsifier on theologian's earlier caveat-#2-attribution.
- Does NOT incorporate any inference from librarian D-1778503034 cross-cycle yield_from finding without the substrate-disambiguation pythia 272 flagged.
- Does NOT address the ARM-control-ABBA gap on theologian v4 commit-message claim that "mechanism reproduces on both architectures" — that's a separate v5/v6 tightening if ARM control runs.
