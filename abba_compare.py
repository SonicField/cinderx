#!/usr/bin/env python3
"""
abba_compare.py — Compare two ABBA log files for criterion-(k) regression detection.

Per investigations/plans/abba_fast_mode_proposal.md:
- Fast mode: per-benchmark threshold 8%, geomean threshold 5%
- Full mode: per-benchmark threshold 5%, geomean threshold 5%

Regression definition: HEAD's CinderX time is slower than baseline's CinderX time
by more than the threshold percentage. Vanilla time is treated as a constant
across commits (interpreter doesn't change between CinderX commits); the JIT's
CinderX-side runtime is what matters.

Exit codes:
  0  PASS — no regression detected at the configured threshold
  1  BLOCK — at least one per-benchmark or geomean regression exceeds threshold
  2  ERROR — input files unparseable or benchmark sets do not match

Usage:
  abba_compare.py HEAD_LOG BASELINE_LOG [--mode=fast|full] [--per-bench=N] [--geomean=N] [--verbose]

The HEAD_LOG and BASELINE_LOG arguments are paths to ABBA output files in the
format produced by benchmark_cinderx.py (subprocess ABBA, the per-benchmark
table with `Vanilla | CinderX | Speedup | Δ%` columns plus a GEOMEAN line).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass


# Per investigations/plans/abba_fast_mode_proposal.md:
THRESHOLDS = {
    "fast": {"per_bench": 8.0, "geomean": 5.0, "reps": 2},
    "full": {"per_bench": 5.0, "geomean": 5.0, "reps": 5},
}


@dataclass
class BenchRow:
    name: str
    vanilla_ms: float
    cinderx_ms: float
    speedup: float
    pct_improvement: float


@dataclass
class AbbaResult:
    benchmarks: dict[str, BenchRow]
    geomean_speedup: float
    geomean_pct: float
    total_vanilla_ms: float
    total_cinderx_ms: float
    total_speedup: float
    # Per-run total ms, captured from "Run N/M: JIT_ON|JIT_OFF (rep K) ... Xms total" lines.
    # Used to bound session-aggregate noise envelope (cross-day vs within-day).
    jit_on_runs_ms: list[float]
    jit_off_runs_ms: list[float]


# Per-benchmark row in the ABBA output looks like:
#   fibonacci             1152.59ms   471.64ms     2.44x   59.1% **
# Capture: name (1+ word chars), vanilla ms, cinderx ms, speedup, pct.
_BENCH_RE = re.compile(
    r"^\s+(\S+)\s+([\d.]+)ms\s+([\d.]+)ms\s+([\d.]+)x\s+([+-]?[\d.]+)%"
)
_GEOMEAN_RE = re.compile(
    r"^\s+GEOMEAN\s+([\d.]+)x\s+([+-]?[\d.]+)%"
)
_TOTAL_RE = re.compile(
    r"^\s+TOTAL\s+([\d.]+)ms\s+([\d.]+)ms\s+([\d.]+)x"
)
# Per-run line: "  Run 14/20: JIT_OFF (rep 4) ... 20046.3ms total"
_RUN_RE = re.compile(
    r"^\s+Run\s+\d+/\d+:\s+(JIT_(?:ON|OFF))\s+\(rep\s+\d+\)\s+\.\.\.\s+([\d.]+)ms"
)


def parse_abba(path: str) -> AbbaResult:
    """Parse a single ABBA subprocess log file."""
    benches: dict[str, BenchRow] = {}
    geomean_speedup = None
    geomean_pct = None
    total_vanilla = None
    total_cinderx = None
    total_speedup = None
    jit_on_runs: list[float] = []
    jit_off_runs: list[float] = []

    try:
        with open(path) as f:
            for line in f:
                m = _BENCH_RE.match(line)
                if m:
                    name = m.group(1)
                    benches[name] = BenchRow(
                        name=name,
                        vanilla_ms=float(m.group(2)),
                        cinderx_ms=float(m.group(3)),
                        speedup=float(m.group(4)),
                        pct_improvement=float(m.group(5)),
                    )
                    continue
                m = _GEOMEAN_RE.match(line)
                if m:
                    geomean_speedup = float(m.group(1))
                    geomean_pct = float(m.group(2))
                    continue
                m = _TOTAL_RE.match(line)
                if m:
                    total_vanilla = float(m.group(1))
                    total_cinderx = float(m.group(2))
                    total_speedup = float(m.group(3))
                    continue
                m = _RUN_RE.match(line)
                if m:
                    cond = m.group(1)
                    ms = float(m.group(2))
                    if cond == "JIT_ON":
                        jit_on_runs.append(ms)
                    else:
                        jit_off_runs.append(ms)
    except OSError as exc:
        print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    if not benches:
        print(f"ERROR: no benchmark rows parsed from {path}", file=sys.stderr)
        sys.exit(2)
    if geomean_speedup is None:
        print(f"ERROR: no GEOMEAN line parsed from {path}", file=sys.stderr)
        sys.exit(2)

    return AbbaResult(
        benchmarks=benches,
        geomean_speedup=geomean_speedup,
        geomean_pct=geomean_pct,
        total_vanilla_ms=total_vanilla,
        total_cinderx_ms=total_cinderx,
        total_speedup=total_speedup,
        jit_on_runs_ms=jit_on_runs,
        jit_off_runs_ms=jit_off_runs,
    )


def _stddev(xs: list[float]) -> float:
    """Sample std deviation. Returns 0 for fewer than 2 samples."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean = sum(xs) / n
    return (sum((x - mean) ** 2 for x in xs) / (n - 1)) ** 0.5


def _median(xs: list[float]) -> float:
    """Median of a list. Empty input returns 0."""
    n = len(xs)
    if n == 0:
        return 0.0
    s = sorted(xs)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


def _mad_outliers(xs: list[float], threshold: float = 3.0) -> tuple[list[float], list[float]]:
    """Median Absolute Deviation outlier filter.

    Returns (kept, excluded). A point x is excluded when
    |x - median| > threshold * MAD * 1.4826 (consistency factor for
    Gaussian-like distributions). Threshold default 3 = ~3σ.

    Falls back to keeping all points when MAD == 0 (degenerate case
    when more than half the points are identical) since the rule has no
    informative scale at that point.
    """
    if len(xs) < 3:
        return list(xs), []
    med = _median(xs)
    deviations = [abs(x - med) for x in xs]
    mad = _median(deviations)
    if mad == 0:
        return list(xs), []
    cutoff = threshold * mad * 1.4826
    kept = [x for x in xs if abs(x - med) <= cutoff]
    excluded = [x for x in xs if abs(x - med) > cutoff]
    return kept, excluded


def report_noise_envelope(label: str, result: AbbaResult) -> None:
    """Print session-aggregate noise envelope from per-run totals.

    Computes σ and CV (coefficient of variation = σ / mean) for the
    JIT_ON and JIT_OFF run-total distributions. Bounds the cross-session
    measurement noise floor without per-benchmark per-rep data (which
    the current ABBA log format doesn't expose).

    Reports both raw σ/CV and MAD-filtered σ/CV. Excluded outliers are
    listed inline with their values; if exclusion materially changes the
    CV (raw > 5% but filtered < 5%), the raw version is what gates
    decisions but the filtered version is shown for transparency. No
    silent dropping — outlier handling is explicit.
    """
    print(f"  Noise envelope ({label}):")
    for cond, runs in (("JIT_ON ", result.jit_on_runs_ms),
                       ("JIT_OFF", result.jit_off_runs_ms)):
        if not runs:
            print(f"    {cond}: no per-run data parsed")
            continue
        n = len(runs)
        mean = sum(runs) / n
        sd = _stddev(runs)
        cv_pct = (sd / mean * 100.0) if mean > 0 else 0.0
        print(
            f"    {cond}: n={n} mean={mean:.1f}ms σ={sd:.1f}ms "
            f"CV={cv_pct:.2f}%  range=[{min(runs):.1f}, {max(runs):.1f}]ms"
        )
        kept, excluded = _mad_outliers(runs)
        if excluded:
            kept_n = len(kept)
            kept_mean = sum(kept) / kept_n if kept_n else 0.0
            kept_sd = _stddev(kept)
            kept_cv = (kept_sd / kept_mean * 100.0) if kept_mean > 0 else 0.0
            excl_str = ", ".join(f"{x:.1f}" for x in excluded)
            print(
                f"      MAD-filtered (3σ-equivalent): n={kept_n} "
                f"mean={kept_mean:.1f}ms σ={kept_sd:.1f}ms CV={kept_cv:.2f}%  "
                f"excluded: [{excl_str}]"
            )
            if cv_pct >= 5.0 and kept_cv < 5.0:
                print(
                    f"      NOTE: raw CV={cv_pct:.2f}% is at or above the 5% "
                    f"per-benchmark threshold floor; MAD-filtered CV={kept_cv:.2f}% is below. "
                    f"The {len(excluded)} excluded outlier(s) drive the raw envelope."
                )


def compare(
    head: AbbaResult,
    baseline: AbbaResult,
    per_bench_threshold: float,
    geomean_threshold: float,
    verbose: bool,
) -> tuple[bool, list[str]]:
    """Return (passed, list_of_violations).

    A regression is reported when HEAD takes more time than baseline by more
    than the threshold percentage (positive delta = slower = regression).
    """
    violations: list[str] = []

    # Per-benchmark check on CinderX times.
    head_set = set(head.benchmarks)
    base_set = set(baseline.benchmarks)
    if head_set != base_set:
        only_head = head_set - base_set
        only_base = base_set - head_set
        msg = "ERROR: benchmark sets differ"
        if only_head:
            msg += f" — only in HEAD: {sorted(only_head)}"
        if only_base:
            msg += f" — only in BASELINE: {sorted(only_base)}"
        print(msg, file=sys.stderr)
        sys.exit(2)

    if verbose:
        print(
            f"{'Benchmark':24s} {'BASE_ms':>10s} {'HEAD_ms':>10s} "
            f"{'Δ_ms':>9s} {'Δ%':>7s}  Verdict"
        )
        print("-" * 80)

    for name in sorted(head.benchmarks):
        h = head.benchmarks[name].cinderx_ms
        b = baseline.benchmarks[name].cinderx_ms
        if b <= 0:
            continue
        delta_pct = (h - b) / b * 100.0
        regressed = delta_pct > per_bench_threshold
        if regressed:
            violations.append(
                f"per-benchmark {name}: HEAD {h:.2f}ms vs BASE {b:.2f}ms "
                f"= +{delta_pct:.2f}% > threshold +{per_bench_threshold:.2f}%"
            )
        if verbose:
            verdict = "REGRESSION" if regressed else ("better" if delta_pct < 0 else "ok")
            print(
                f"{name:24s} {b:10.2f} {h:10.2f} {h - b:+9.2f} "
                f"{delta_pct:+6.2f}%  {verdict}"
            )

    # Geomean check on speedup ratios.
    # Regression: HEAD's geomean speedup is less than baseline's by more than
    # the threshold (relative).
    if baseline.geomean_speedup > 0:
        gm_delta_pct = (
            (head.geomean_speedup - baseline.geomean_speedup)
            / baseline.geomean_speedup
            * 100.0
        )
        if gm_delta_pct < -geomean_threshold:
            violations.append(
                f"geomean: HEAD speedup {head.geomean_speedup:.3f}x vs BASE "
                f"{baseline.geomean_speedup:.3f}x = {gm_delta_pct:+.2f}% "
                f"(threshold ±{geomean_threshold:.2f}%)"
            )
        if verbose:
            print()
            print(
                f"GEOMEAN  BASE {baseline.geomean_speedup:.3f}x  "
                f"HEAD {head.geomean_speedup:.3f}x  Δ {gm_delta_pct:+.2f}%"
            )

    return (not violations), violations


def main() -> int:
    p = argparse.ArgumentParser(
        description="Compare two ABBA logs for criterion-(k) regression detection."
    )
    p.add_argument("head_log", help="ABBA log file at HEAD")
    p.add_argument("baseline_log", help="ABBA log file at baseline")
    p.add_argument(
        "--mode",
        choices=["fast", "full"],
        default="full",
        help="Threshold preset (default: full).",
    )
    p.add_argument(
        "--per-bench",
        type=float,
        default=None,
        help="Per-benchmark regression threshold percent (overrides --mode).",
    )
    p.add_argument(
        "--geomean",
        type=float,
        default=None,
        help="Geomean regression threshold percent (overrides --mode).",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-benchmark comparison table.",
    )

    args = p.parse_args()

    cfg = THRESHOLDS[args.mode]
    per_bench = args.per_bench if args.per_bench is not None else cfg["per_bench"]
    geomean = args.geomean if args.geomean is not None else cfg["geomean"]

    head = parse_abba(args.head_log)
    baseline = parse_abba(args.baseline_log)

    print(f"Mode: {args.mode}")
    print(f"Thresholds: per-benchmark ±{per_bench:.1f}%, geomean ±{geomean:.1f}%")
    print(f"HEAD:     {args.head_log}")
    print(f"BASELINE: {args.baseline_log}")
    print()

    # Session-aggregate noise envelope (bounds cross-session noise floor;
    # per supervisor 06:54:38Z + pythia 12 #1 about cross-day vs within-day
    # noise on the carve-out baseline). Per-benchmark σ is not available
    # from the current ABBA log format which only captures per-run TOTAL.
    print("Session-aggregate noise envelope (per-run totals):")
    report_noise_envelope("HEAD    ", head)
    report_noise_envelope("BASELINE", baseline)
    print()

    ok, violations = compare(head, baseline, per_bench, geomean, args.verbose)

    print()
    if ok:
        print("VERDICT: PASS — no regression at configured thresholds.")
        return 0

    print(f"VERDICT: BLOCK — {len(violations)} regression(s) detected:")
    for v in violations:
        print(f"  - {v}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
