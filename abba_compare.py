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


def parse_abba(path: str) -> AbbaResult:
    """Parse a single ABBA subprocess log file."""
    benches: dict[str, BenchRow] = {}
    geomean_speedup = None
    geomean_pct = None
    total_vanilla = None
    total_cinderx = None
    total_speedup = None

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
