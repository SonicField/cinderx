# ABBA Baseline-Drift Policy

**Author:** generalist
**Date:** 2026-04-22
**Spec source:** supervisor 05:34:46Z (3 components) + supervisor 05:48:22Z (autonomous resolutions to open design choices) + alexie 05:34:17Z (originating request)
**Companion document:** `abba_fast_mode_proposal.md` (per-commit gate mechanics + calibration counter)

## Problem

Per-commit ABBA gating naïvely compares each commit against its immediate parent. That allows monotonic drift: every commit can be 4.9% slower than its parent and pass a 5% threshold, but after 10 such commits the bundle is ~40% slower than its bundle-parent. Alexie 05:34:17Z named this and asked for baseline-relative comparison plus a ratchet for genuine improvements.

## Three components

### 1. Baseline anchor — HEAD vs CANONICAL BASELINE

Comparison is HEAD-of-bundle (or HEAD-of-commit, in per-commit gating after fast-mode promotion) vs the **canonical baseline**, not vs the immediate parent commit.

- The canonical baseline is the most recent commit that has a stored full-mode ABBA result blessed as the reference.
- A commit's parent has no special status in this comparison; only the canonical baseline does.
- This prevents the slow-drift failure mode (each commit individually under threshold; cumulative drift far exceeds threshold).

**Worked example for the current 11-commit bundle:**
- Bundle commits: 794d8270 → 60701da2 (per `git log @{u}..HEAD` this turn).
- Canonical baseline: 9df470d0 (the commit immediately before 794d8270; verified via `git rev-parse 794d8270~1` per medic 05:16:29Z + supervisor 05:16:39Z).
- Criterion (k) gate: HEAD (60701da2) ABBA per-benchmark + geomean compared against 9df470d0 ABBA per-benchmark + geomean. Tooling: `abba_compare.py benchmarks/<HEAD>.txt benchmarks/<BASELINE>.txt --mode=full`.

### 2. Ratchet on improvement

When a commit's ABBA shows a genuine improvement over the canonical baseline, the canonical baseline ADVANCES to that commit on push. This locks in the gain — future commits cannot regress below the new (better) line.

**Trigger threshold:** 2% improvement on a benchmark. Per-benchmark independently (no all-or-nothing geomean trigger).

- Rationale for 2% (not 0%): pure 0% would ratchet on noise; per the variance analysis in `abba_fast_mode_proposal.md` (per-benchmark σ ≈ 2% at full mode reps=5; std error of the mean σ/√5 ≈ 0.9%), 2% improvement = ~2.2σ above mean noise. This is the **meaningful improvement** threshold — significant enough to be unlikely noise — NOT the **statistically certain improvement** threshold (which would require larger N or wider gap). Interpretation: 2% ratchet is conservative for noise rejection, reasonable for genuine-improvement detection. Acknowledged trade-off: occasional ratchet on a true noise excursion at the tail; corrected by the ratchet-thrashing falsifier (see Falsifier section below).
- Rationale for per-benchmark independent: matches Q9 OR semantics (BLOCK if EITHER fails). Symmetric ratchet (RATCHET if EITHER improves ≥2%) keeps the policy honest in both directions.

**Update mechanics:**
- When HEAD passes gate (k) AND any benchmark shows ≥2% improvement vs baseline, the per-benchmark canonical-baseline value for that benchmark advances to HEAD's value.
- The canonical-baseline-tracking artifact (`benchmarks/baseline.json` — see Storage below) gets a commit on push with the per-benchmark advance entries listed in the commit message.
- Benchmarks that did NOT improve ≥2% retain their existing baseline value.
- Geomean baseline tracks the geomean speedup of the *current* per-benchmark baseline values; recomputed automatically on each baseline.json edit.

### 3. Periodic re-anchoring

When the canonical baseline changes for reasons other than ratchet — release cut, main-merge, hardware change, vanilla CPython upgrade, build-toolchain change — all per-commit comparisons re-anchor to the new baseline.

- Re-anchoring runs full-mode ABBA on the new anchor commit AND populates baseline.json with the fresh per-benchmark values.
- Until re-anchoring runs, per-commit gating uses the prior baseline (acceptable for short windows; flag for re-anchoring if it stays stale > 1 week).
- Re-anchoring events get a marker in baseline.json (`reanchor_at: <commit>, <reason>, <date>`) so future agents can read the history.

## Storage

`benchmarks/baseline.json` — text file (JSON, git-tracked). Schema:

```json
{
  "anchor_commit": "9df470d0",
  "anchor_date": "2026-04-21",
  "hardware": "x86_64",
  "vanilla_python": "3.12.13",
  "reanchor_history": [
    { "commit": "9df470d0", "date": "2026-04-21", "reason": "initial-anchor" }
  ],
  "geomean_speedup": 1.23,
  "benchmarks": {
    "fibonacci": { "vanilla_ms": 1152.59, "cinderx_ms": 471.64, "speedup": 2.44 },
    "method_calls": { "vanilla_ms": 620.34, "cinderx_ms": 908.61, "speedup": 0.68 }
  }
}
```

- One entry per `(benchmark, hardware)` tuple; if the project ever runs ABBA on multiple architectures, the schema extends with one file per arch (e.g., `baseline-x86_64.json`, `baseline-aarch64.json`).
- `abba_compare.py` reads this file when given `--baseline=benchmarks/baseline.json` instead of a raw ABBA log; comparison uses the per-benchmark stored speedup as the truth.
- Ratchet update emits the new baseline.json in a separate commit on push (not bundled with the gate-(k) PASS commit, so the baseline-advance is auditable independently).

## Operational integration

1. **Gate (k) check:** `abba_compare.py <head_log> --baseline=benchmarks/baseline.json --mode=fast` (or `--mode=full`). Exit 0 = no per-benchmark or geomean regression vs baseline; exit 1 = BLOCK.
2. **On gate (k) PASS:** if any benchmark improved ≥2% vs baseline, supervisor commits a baseline.json update with those advances. Commit message lists each advance: `Advance baseline.json: fibonacci 2.44x → 2.49x (+2.1%); int_arith 1.58x → 1.62x (+2.5%)`. Other benchmarks unchanged.
3. **Periodic re-anchor:** when triggered (release cut, hardware change, etc.), supervisor runs full ABBA on the new anchor commit, regenerates baseline.json with fresh values, appends to `reanchor_history`, commits.

## Baseline-cannot-run carve-out

**Default expectation:** the canonical baseline (the commit that anchors `benchmarks/baseline.json`) can complete a clean ABBA run. Gate (k) compares HEAD ABBA to that baseline ABBA per the operational rules above.

**Carve-out:** when the canonical baseline CANNOT complete ABBA — for example because the bug being fixed in the current bundle crashes the benchmark runner — the bundle uses the **first crash-fix-clean commit** as effective baseline instead of the true parent. Pre-effective-baseline commits in the bundle are gated by **crash-fix evidence** (a falsifier-proven matrix at `investigations/probes/`) instead of ABBA.

**Per-occurrence documentation requirement:** every carve-out invocation MUST land an entry in this section listing (a) the failing baseline commit, (b) the failure evidence (cite the truncated ABBA log), (c) the chosen effective baseline + reason, (d) the crash-fix evidence covering the un-ABBA-able pre-effective-baseline commits, (e) cross-day/cross-environment noise notes if applicable.

### Invocation 1 — speculation-experiment bundle (2026-04-22)

- **Failing baseline commit:** 9df470d0 (parent of 794d8270, the first commit in the bundle).
- **Failure evidence:** `/tmp/abba_BASE_9df470d0.txt` shows `Run 4/20: JIT_ON (rep 1) ... Worker failed (exit -7): FAILED`. SIGBUS = -7. Bench_deep_class workload triggers the very crash this bundle fixes (slab-init UAF + forgetCode use-after-free). True-parent ABBA is empirically impossible — the parent's own bug crashes the runner. (Testkeeper 05:57:56Z report.)
- **Chosen effective baseline:** c4e1900c (commit 3 in the bundle; first crash-fix-clean state). ABBA log at `benchmarks/2026-04-21_151928_c4e1900c_x86_64_abba.txt` (mtime 2026-04-21 16:45 UTC, GEOMEAN 1.23x). `benchmarks/baseline.json` initialized from this file with the carve-out cited in `reanchor_history`.
- **Crash-fix evidence for pre-c4e1900c commits (794d8270, 78cee3c7, c4e1900c, fbefef0a):** `investigations/probes/compound_crash_*` — n=5 4-cell matrix shows 5/5 EXIT=0 on fix tree, 5/5 EXIT=139 SIGSEGV on revert tree. These commits are correctness fixes, never had perf goals; ABBA was never the right gate. (See defensive-patch-tracker.md JOINT entry for 78cee3c7+c4e1900c.)
- **Cross-day noise note:** the c4e1900c ABBA was captured at 2026-04-21 16:45 UTC; HEAD ABBA will be captured at 2026-04-22 some hours later (exact time when testkeeper completes the run). Cross-day comparison includes hardware/load noise that same-day comparison would not. The 5% per-benchmark threshold absorbs typical noise of this magnitude (per σ ≈ 2% analysis in `abba_fast_mode_proposal.md`); transparency about the cross-day window is the requirement, not a defeating problem.

**Falsifier on the carve-out itself (theologian 05:59:28Z):** this is a ONE-TIME exception for the speculation-experiment bundle because its parent contains the exact bug the bundle fixes. If a FUTURE bundle ALSO requires a non-canonical baseline because its parent crashes ABBA, this exception is no longer one-time and the carve-out has become a recurring pattern. At that point this document needs revision — the policy should explicitly handle 'baseline crashes' as a normal case rather than a deviation, OR investigate why bundles routinely target their own bugs' fixes (which suggests a deeper testing-discipline gap).

After this push lands, the canonical baseline becomes the post-merge HEAD; the next bundle's parent will not have this constraint by construction.

## Open design choices — autonomous resolutions

These were the open choices in supervisor's 05:34:46Z proposal; resolved per supervisor 05:48:22Z autonomous-mode authority.

| Choice | Decision | Reasoning |
| --- | --- | --- |
| Ratchet threshold X | 2% (per-benchmark) | Above noise floor (σ ≈ 2% at full mode); below 5% gate threshold so improvements ratchet before they become regression budget |
| Ratchet trigger | Per-benchmark independently | Matches Q9 OR semantics on the regression side; symmetric on the improvement side |
| Storage | `benchmarks/baseline.json`, git-tracked | Visible to humans; survives reboots; same path convention as benchmark logs |
| Geomean baseline | Computed from per-benchmark baselines | Avoids storing a separate geomean number that can drift from per-benchmark truth |
| Re-anchor trigger | Manual (release cut, main-merge, hardware/toolchain change, vanilla CPython upgrade) | No auto-trigger; supervisor decides when reset is needed |

## Bootstrap procedure

For the current 11-commit bundle (this is how the policy starts running):

1. Wait for testkeeper's full-mode ABBA at 9df470d0 to complete (in flight per supervisor 05:38:14Z).
2. Generate initial `benchmarks/baseline.json` from that ABBA log: parse per-benchmark `vanilla_ms`, `cinderx_ms`, `speedup`; copy `geomean_speedup`. Mark `anchor_commit: 9df470d0`, `reanchor_history: [{commit: "9df470d0", date: "2026-04-21", reason: "initial-anchor"}]`.
3. Commit `benchmarks/baseline.json` to the bundle (12th commit, or land separately as the post-push baseline-init).
4. Run gate (k) for the bundle: `abba_compare.py <60701da2_log> --baseline=benchmarks/baseline.json --mode=full`.
5. If PASS: any benchmarks with ≥2% improvement at HEAD ratchet immediately. New baseline.json reflects HEAD post-ratchet.
6. If BLOCK: bundle re-evaluated per the BLOCK reason; baseline.json stays as initialized.

The 12th-commit bootstrap is the recursive-policy-collapse closure — the policy artifact ships with the bundle that exercises it. (Same shape as the a71c5f71 + deffd3cc + 60701da2 sequence that landed the per-commit-gate documentation.)

## Falsifier on this policy

Three observable falsifiers; any one firing means the policy needs revision:

1. **Cumulative drift detected post-policy:** if 10 consecutive commits all PASS gate (k) at the per-benchmark threshold (no benchmark regresses ≥5%), but the bundle's geomean shows ≥10% regression vs the original baseline (before the 10 commits), the per-benchmark threshold is too loose OR the geomean threshold is missing in cases where per-benchmark is fine. Investigate.

2. **Ratchet thrashing:** if baseline.json is updated for the same benchmark in alternating directions (advance to 2.49x, then advance to 2.45x, then advance to 2.49x — i.e., the threshold is catching noise as 'improvement'), the 2% threshold is too tight relative to actual variance. Raise to 3% and re-evaluate.

3. **Re-anchor staleness:** if a documented re-anchor trigger fires (e.g., release cut) but baseline.json hasn't been refreshed within 1 week, the manual-trigger process is unreliable. Add a CI check or stale-marker mechanism. *Rationale for 1 week:* approximates the typical sprint length, captures stale-after-cut scenarios within a single iteration, and matches the cadence at which a missed re-anchor would already have polluted multiple intervening per-commit gates with the wrong baseline. Tightening to 3 days reduces lag at the cost of false-staleness alerts in normal multi-day quiet periods; loosening to 1 month lets staleness compound. 1 week is the practical compromise; revisit if the project's release cadence diverges materially.

## Cross-references

- `abba_fast_mode_proposal.md` — companion artifact (gate mechanics + thresholds + calibration counter)
- `abba_compare.py` — comparison tool; will accept `--baseline=benchmarks/baseline.json` once the JSON path lands
- supervisor 05:34:46Z — originating 3-component proposal
- supervisor 05:48:22Z — autonomous-mode resolution of open design choices
- alexie 05:34:17Z — originating ratchet-on-improvement framing
