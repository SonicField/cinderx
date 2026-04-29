#!/usr/bin/env python3
"""tier2_delta_check.py — Hard-Gate #4 tier-2 delta-check (pre-staged per shepard 08:57:48Z).

Per gatekeeper 07:31:55Z + supervisor 07:32:13Z + Hard-Gate #4 spec:
  Bench in [0.95, 1.05] AND on harness-shape doc-list AND ratio diverged >2%
  from prior in-band reading → requires fresh is_jit_compiled() check (not
  doc-cite alone) — band-creep risk.

Usage:
  tier2_delta_check.py --prior-artifact <verdict_abba_artifact> \\
                       --current-artifact <new_abba_artifact> \\
                       [--threshold 0.02] [--band-low 0.95] [--band-high 1.05]

Output: list of bench names that REQUIRE fresh is_jit_compiled() per
gatekeeper Hard-Gate #4 tier-2. Exit 1 if any flagged, exit 0 if none.

Pre-staged for first exercise inline with post-push full-suite ABBA.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


HARNESS_SHAPE_DOCLIST = {
    # 15-bench list per testkeeper 06:18:39Z + theologian 07:00:03Z + supervisor
    # 07:00:39Z + theologian 07:22:29Z (3 ARM benches added). Also includes
    # nn_module ARM as PARTIAL-COVERAGE bucket per pythia 111 + testkeeper
    # 08:48:01Z 4-bucket refinement.
    "chaos_game",
    "coroutine_chain",
    "exceptions",
    "float_arith",
    "func_calls",
    "gen_nested",
    "gen_simple",
    "json_roundtrip",
    "list_comp",
    "method_calls",
    "nn_module",
    "positional_dispatch",
    "pytorch_cm",
    "richards_slots",
    "store_subscr",
}


BENCH_LINE = re.compile(
    r"^\s+(?P<name>[\w_]+)\s+"
    r"(?P<vanilla>[\d.]+)ms\s+"
    r"(?P<cinderx>[\d.]+)ms\s+"
    r"(?P<ratio>[\d.]+)x"
)


def parse_artifact(path: Path) -> dict[str, float]:
    """Parse benchmark_cinderx.py per-bench table into {name: ratio}."""
    out: dict[str, float] = {}
    for line in path.read_text().splitlines():
        m = BENCH_LINE.match(line)
        if m:
            out[m["name"]] = float(m["ratio"])
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--prior-artifact", required=True, type=Path)
    p.add_argument("--current-artifact", required=True, type=Path)
    p.add_argument("--threshold", type=float, default=0.02,
                   help="ratio-delta threshold to flag (default 0.02 = 2%%)")
    p.add_argument("--band-low", type=float, default=0.95)
    p.add_argument("--band-high", type=float, default=1.05)
    p.add_argument("--require-doc-list", action="store_true", default=True,
                   help="only flag benches on the harness-shape doc-list")
    args = p.parse_args()

    prior = parse_artifact(args.prior_artifact)
    current = parse_artifact(args.current_artifact)

    if not prior:
        print(f"ERROR: no per-bench rows parsed from {args.prior_artifact}", file=sys.stderr)
        return 2
    if not current:
        print(f"ERROR: no per-bench rows parsed from {args.current_artifact}", file=sys.stderr)
        return 2

    flagged: list[tuple[str, float, float, float]] = []
    in_band_stable: list[tuple[str, float, float]] = []
    for name, cur_ratio in current.items():
        if not (args.band_low <= cur_ratio <= args.band_high):
            continue
        if args.require_doc_list and name not in HARNESS_SHAPE_DOCLIST:
            # not on doc-list → tier-3 (full per-bench is_jit_compiled())
            continue
        prior_ratio = prior.get(name)
        if prior_ratio is None:
            # new bench, no prior reading → flag for tier-3
            flagged.append((name, float("nan"), cur_ratio, float("nan")))
            continue
        delta = abs(cur_ratio - prior_ratio) / prior_ratio
        if delta > args.threshold:
            flagged.append((name, prior_ratio, cur_ratio, delta))
        else:
            in_band_stable.append((name, prior_ratio, cur_ratio))

    print(f"=== Tier-2 delta-check (threshold {args.threshold*100:.1f}%) ===")
    print(f"Prior artifact:   {args.prior_artifact}")
    print(f"Current artifact: {args.current_artifact}")
    print(f"In-band benches: {sum(1 for r in current.values() if args.band_low <= r <= args.band_high)}")
    print()
    print(f"Stable in-band (doc-cite OK): {len(in_band_stable)}")
    for name, p_, c_ in sorted(in_band_stable):
        print(f"  {name:25s} prior={p_:.3f}x current={c_:.3f}x")
    print()
    print(f"DELTA-CHECK FLAGGED (require fresh is_jit_compiled()): {len(flagged)}")
    for name, p_, c_, d_ in sorted(flagged):
        if p_ != p_:  # NaN check
            print(f"  {name:25s} new-bench (no prior) current={c_:.3f}x")
        else:
            print(f"  {name:25s} prior={p_:.3f}x current={c_:.3f}x delta={d_*100:.1f}%")

    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
