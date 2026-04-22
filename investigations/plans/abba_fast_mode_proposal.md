# ABBA Fast-Mode Proposal

**Author:** generalist
**Date:** 2026-04-22
**Spec source:** supervisor 05:23:46Z + gatekeeper 05:23:29Z (criterion-(k) per-commit gating)
**Status:** DRAFT — awaiting alexie's runtime-budget answer; defaults to ~25 min target

## Goal

Add a "fast" ABBA mode for per-commit criterion-(k) gating that catches ≥5–10% per-benchmark or geomean regressions with no false negatives on regressions of that magnitude, in a runtime budget of ~25 min (vs ~5–6 min raw + overhead for current full mode at `--reps=5`, or ~30+ min for full nightly with cold builds + warmup).

## Hard requirements (from gatekeeper 05:23:29Z, supervisor 05:23:46Z)

1. Catch ≥5–10% regression on any individual benchmark and on geomean.
2. False positives tolerable (re-verify with full); **false negatives NOT tolerable**.
3. Output shape compatible with criterion-(k) tooling (same diff/comparison as full).
4. Documented confidence interval (`fast catches X% regressions at Y% confidence`).

## Survey of current (full) ABBA shape

Same-turn verified by Read of `benchmark_cinderx.py:58-61` and `benchmarks/2026-04-21_151928_c4e1900c_x86_64_abba.txt`:

- `BENCH_ITERS = 50_000` per measurement
- `WARMUP_ITERS = 5_000`
- `INNER_ITERS = 100`
- `--reps=2` is the in-script default; the most recent ABBA used `--reps=5` (= 20 subprocess runs, 10 per condition).
- 29 benchmarks span the full suite (chaos_game → yield_from).
- Per-run wall time on the recent c4e1900c file: JIT ~13.0s, vanilla ~15.4s (one outlier 20.0s at run 14/20).
- Total benchmark execution at reps=5: ~5–6 min. Documented full-mode wall time of ~25–30 min on alexie's box appears to be dominated by build + warmup steps + preflight, not the benchmark loop.

## Two design candidates

### Option A — full benchmark set, reduced reps (gatekeeper's suggestion)

**Shape:** keep all 29 benchmarks; lower `--reps` from 5 to 2.

- Statistical power scales as √N. At reps=2 vs reps=5, std error of the per-benchmark mean is `sqrt(5/2) ≈ 1.58x` larger.
- To keep false negatives at the same rate as full-mode-at-5%, the per-benchmark detection threshold must widen by ~1.58x: **fast threshold ≈ 8% per-benchmark; geomean stays at 5% per the separate argument below (large effective N).**
- Geomean has lower std error than any individual benchmark (effective N is the product of per-benchmark counts), so the 5% geomean detection threshold remains tight at reps=2 — see "Threshold rationale" below for the σ math.
- Wall-time saving: benchmark-loop time scales linearly with reps; reps=2 ≈ 40% of reps=5 raw time. Holding build/warmup constant, ~25 min total target is achievable (the benchmark loop is small relative to overhead, so the 60% reps reduction translates to roughly proportional savings only if overhead is bounded).

**Pros:** preserves full benchmark coverage. No regression-class can be silently dropped. Same tooling; same comparison shape; trivially compatible with criterion-(k) diff machinery.

**Cons:** noisy per-benchmark — wider per-benchmark threshold means fast mode misses 5–8% per-benchmark regressions; full mode escalation is required to confirm/refute.

### Option B — subset of 6–10 regression-sensitive benchmarks at full reps

**Shape:** pick 6–10 benchmarks that exercise distinct JIT codegen paths. Run them at the same reps=5 as full mode.

**Falsifier on Option B:** does a 6–10 benchmark subset actually capture all the regression-sensitive paths? Verify by:

1. Look at recent ABBA losers and known performance-sensitive paths (per session memory): method_calls (-46%), list_comp (-13%), deep_class_super (-7%), chaos_game (~neutral). These are the recent "interesting" benchmarks.
2. Look at JIT codegen surface coverage: integer arithmetic (int_arith, fibonacci, fannkuch), generators (gen_simple, gen_nested, yield_from, coroutine_chain), exceptions (try_except_callee, exceptions), method dispatch (method_calls, positional_dispatch), allocation/dict (dict_ops, store_subscr), list ops (list_comp, unpack_seq), float arithmetic (float_arith, nbody, spectral_norm), inlining (richards_full, richards_slots).
3. **Conclusion against Option B:** The 29-benchmark set was chosen to span these paths; any subset of 6–10 leaves gaps. A regression in a dropped path would be invisible to fast mode → **false negative on a real regression class.** That violates hard requirement #2 (false negatives not tolerable). Option B is rejected on the hard requirement.

**Result:** Option B fails the false-negative requirement. Option A wins on falsifier.

## Recommendation

**Adopt Option A:** full 29-benchmark set at `--reps=2` for fast mode; full set at `--reps=5` for full mode.

### Mechanical specification

| Parameter | Fast mode | Full mode |
| --- | --- | --- |
| Benchmark set | All 29 | All 29 |
| `--reps` | 2 | 5 |
| Per-benchmark regression threshold | 8% | 5% |
| Geomean regression threshold | 5% | 5% |
| Estimated wall time (benchmark loop only) | ~2 min raw | ~5–6 min raw |
| Estimated full wall time (incl. build/warmup/preflight per current flow) | ~25 min target | ~30 min |
| Use case | per-commit gate for criterion (k) | nightly canonical baseline; escalation when fast triggers |

### Threshold rationale

- **Per-benchmark fast = 8%:** Wider than full's 5% to absorb the ~58% std-error inflation at reps=2 vs reps=5. Calibrated so a real 8% per-benchmark regression should still trigger at the same false-negative rate as full-mode-at-5%.
- **Geomean fast = 5%:** Geomean averages over 29 benchmarks; effective sample count is high enough that the same 5% threshold remains tight at reps=2. Concretely (per gatekeeper 05:28:10Z math): if per-benchmark σ ≈ 2% (representative of clean JIT runs from c4e1900c reference; vanilla outlier runs can push higher and require trimmed-mean statistics), geomean σ at reps=2 ≈ 2%/sqrt(29×2) ≈ 0.26%. A 5% geomean threshold is ~19 std errors above noise — false positives at the geomean level are negligible at reps=2.
- **False positives:** at reps=2, expect occasional per-benchmark threshold trips on noisy benchmarks (chaos_game, deep_class_super) without real regression. **Mandatory escalation rule:** any fast-mode failure triggers full-mode re-run before BLOCKing the commit. Full mode is the authoritative gate.

### Output shape

Fast mode emits the same per-benchmark Δ% table + GEOMEAN/TOTAL footer as full mode (per `print_abba_results` in `benchmark_cinderx.py:205+`). Criterion-(k) comparison tooling (per-benchmark diff + geomean diff vs baseline) is unchanged.

### Documented confidence interval

At reps=2 with the threshold choices above:

- Per-benchmark: catches regressions ≥8% with the same statistical confidence as full-mode catches regressions ≥5%.
- Geomean: catches regressions ≥5% with the same statistical confidence as full mode (geomean's effective N stays high enough).
- **Fast mode WILL miss** regressions in the 5–8% per-benchmark range that don't propagate to geomean. These require full mode.

## Calibration counter (gating fast-mode promotion)

**Calibration counter: 0/10.** Fast-mode is **ADVISORY** (logged alongside full mode but does NOT BLOCK pushes) until the counter reaches 10/10 with zero observed false negatives.

Per gatekeeper 05:40:57Z (recursive-policy-collapse on the false-negative falsifier):

1. **While counter < 10:** full mode is the canonical per-commit gate. Fast mode runs alongside as advisory only — its verdict is logged for the calibration record but does not BLOCK or PASS the commit on its own.
2. **Each calibration run** (fast + full at the same HEAD-vs-baseline pair, then per-(benchmark, commit) false-negative count) increments the counter. The counter update lands as an artifact-edit commit on this file (same shape as the docxmlrpc-row update commit 60701da2 — small, traceable, the artifact stays accurate at land time).
3. **At counter == 10 with zero false negatives observed:** fast mode promotes to BLOCK-gate. The promotion is recorded inline in this section ('Fast-mode promoted to BLOCK-gate on YYYY-MM-DD; calibration logs at investigations/probes/abba_calibration_*.md').
4. **At counter == 10 with N > 0 false negatives:** fast mode does NOT promote; the configuration is re-tuned per the false-negative falsifier section above (tighten threshold or raise reps), the counter resets to 0, and the calibration window restarts.
5. **Post-promotion sampled confirmation** continues per false-negative falsifier section: every fast-mode-PASS commit gets a sampled full-mode confirmation run within 24 hours; any missed regression triggers re-tune + retroactive audit + counter reset.

The Operational integration section below describes the steady-state (post-promotion) workflow. Until counter == 10/10, treat the fast-mode bullets as ADVISORY — full mode runs as written + fast mode runs alongside without gating authority.

## Operational integration (post-calibration steady state)

1. **Per-commit CI gate** runs fast (~25 min). If green, commit passes criterion-(k) provisionally.
2. **Any fast-mode failure** → escalate to full-mode run on the same commit before BLOCKing. False positives caught at this stage.
3. **Nightly / weekly** runs full as canonical baseline. Stored at `benchmarks/<date>_<commit>_<arch>_abba.txt` per current convention.
4. **Bundle gate** (e.g., the current 11-commit bundle): fast at HEAD vs fast at baseline (9df470d0). If clean, push proceeds. If fast trips → full at HEAD vs full at baseline.

## Open questions for alexie

1. **Runtime budget:** is the ~25 min target acceptable for per-commit gating? If smaller (e.g., ~10 min), reps=1 + threshold=12% is the next step down (false-negative risk grows). If larger (e.g., ~40 min), reps=3 + threshold=6% is a tighter compromise.
2. **Per-commit vs bundle interpretation of (k):** gatekeeper 05:19:53Z asked the same — does fast mode run per individual commit, or once per bundle at HEAD vs baseline? (Per-commit runs scale with commit count; bundle gate amortizes.)
3. **Threshold tuning:** is 8% per-benchmark fast acceptable, or do you want tighter (and accept more false positives → more full re-runs)?
4. **Geomean vs per-benchmark priority:** if a per-benchmark trip on a single benchmark would BLOCK while geomean is fine, is that the desired behaviour, or should geomean+per-benchmark conjunction (both must be regressed) be the trigger?

## Falsifier on this proposal

Two complementary falsifiers — false-positive and false-negative — must both fire correctly for fast mode to be trustworthy. Per gatekeeper 05:28:10Z, the false-negative falsifier is the load-bearing one (false positives are recoverable via escalation; false negatives let regressions ship).

### False-positive falsifier

If empirical reps=2 runs at HEAD vs baseline 9df470d0 produce ANY per-benchmark Δ outside the ±8% threshold AND full-mode at the same commits shows |Δ| < 5% on every benchmark, fast mode is producing false positives at an unacceptable rate; reps must be raised or threshold widened. The mandatory escalation rule (fast fail → full re-run before BLOCK) catches this in production but the rate matters for cost.

### False-negative falsifier (load-bearing)

On initial calibration AND on the first N=10 production-gate runs after rollout, run BOTH fast and full at the same HEAD-vs-baseline pair. Track every (benchmark, commit) where:

- `Δ_full > 5%` (full mode says regression)
- AND `|Δ_fast| within ±8%` (fast mode says PASS)

This is a false negative — fast mode passed a regression that full mode would have blocked. Hard requirement (gatekeeper 05:23:29Z #2): false negatives NOT tolerable. If observed false-negative rate is > 0/10 over the calibration window, the configuration is wrong:

- First lever: tighten fast threshold (8% → 6%, accepting more false positives).
- Second lever: increase reps (2 → 3, raising runtime but lowering noise).
- Third lever: revisit the design entirely.

After the calibration window, false-negative tracking continues at lower frequency: every fast-mode-PASS commit gets a sampled full-mode confirmation run within 24 hours. If a missed regression is found, the configuration is re-tuned and the missed-window commits are retroactively audited.

### First-calibration-run protocol

The first calibration run MUST compare fast (reps=2) vs full (reps=5) at the same baseline-vs-HEAD pair. Any verdict mismatch (one says BLOCK, the other says PASS) → re-tune before fast mode goes into per-commit-gating service. Do NOT enable fast as the per-commit gate until this calibration succeeds.

## Cross-references

- `benchmark_cinderx.py:58-61` — current iteration constants
- `benchmark_cinderx.py:205+` — `print_abba_results` (output shape)
- `benchmarks/2026-04-21_151928_c4e1900c_x86_64_abba.txt` — most recent full-mode reference, c4e1900c
- gatekeeper 05:23:29Z — gate requirements
- supervisor 05:23:46Z — assignment + structure guidance
- alexie 05:19:12Z — criterion (k); 05:22:48Z — fast/full ask
