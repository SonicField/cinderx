---
status: spec for hypothesis (b3) perf c2c false-sharing per supervisor 2026-05-12 14:18:18Z LLC-mid-band dispatch
owner: theologian (spec); generalist (execution); gatekeeper (pre-flight verify)
trigger: hypothesis (b1)+(b2) discharged at 14:15:57Z (b2 L1-dcache FALSIFIED +0.07%; b1 L1-icache INFERENTIALLY-EXCLUDED CPU event unavailable; LLC +11.2% MID-BAND); supervisor 14:18:18Z dispatch — false-sharing is leading mechanism for LLC delta without L1-dcache signal; b3 c2c directly tests it
scope: hypothesis (b3) of supervisor 13:55:00Z (b)-class — false-sharing on patch's added data (type_invalidation_counts + volatile_types in ic_volatile_types.cpp post-TU-split) creating coherency traffic on cache lines shared with hot-path data accessed by notifyDictUpdate + 4 other yield_from hot-path functions. Falsifies (b3) if no patch-data cache lines appear in perf c2c contention output.
audience: generalist (execution); gatekeeper (pre-flight); testkeeper (post-bench verify)
---

# Cluster5 — yield_from False-Sharing c2c Probe (Hypothesis B3)

## Hypothesis under test

Hypothesis (b3) per supervisor 13:55:00Z + 14:18:18Z LLC-mid-band dispatch: "false sharing — patch's added data lands on cache line shared with hot-path data, even though never accessed during yield_from inner loop. Background type-invalidation traffic (e.g., during process startup or warmup) causes coherency traffic that evicts shared lines, manifesting as LLC misses on hot-path code without L1-dcache signal."

LLC delta from (b) probe was +11.2% raw (above ±5% noise band), L1-dcache delta was +0.07% (below noise). The signature "LLC delta without L1-dcache signal" is the canonical pattern for cross-core cache-line bouncing. False sharing is the leading mechanism for that signature.

Falsifies (b3) if perf c2c report shows NO patch-data cache lines (containing `type_invalidation_counts`, `volatile_types`, or `kVolatileTypeThreshold`) in the high-contention list. If null → LLC re-classifies as variance + dispatch to hypothesis (c) per supervisor 14:18:18Z.

## Probe shape

**Substrates** (same as hypothesis (b)):
- IDEA-port-on: `cluster5-pr-tu-isolated` HEAD 92f5ae72 + LTO=ON x86 fresh build
- IDEA-port-off: `cinderx-main` HEAD 28a57df8 + LTO=ON x86 fresh build (control)

Both reuse the (b) probe's existing builds if still available; otherwise fresh per (b) spec build steps.

**Tool**: `perf c2c record` + `perf c2c report`. Captures cache-line modification + read patterns across cores; identifies false-sharing candidates by reporting cache lines with high cross-core access intensity.

**Per gatekeeper 13:55:00Z (4) constraint**: perf c2c uses hardware sampling — no codegen modification. Constraint trivially satisfied.

## Bench shape

```
# IDEA-port-on:
perf c2c record -F max -- /usr/local/bin/python3 -c '<yield_from-isolated probe script>'
perf c2c report --stdio --full-symbol > /tmp/c2c_idea_port_on.txt

# IDEA-port-off:
# Same command, control substrate _cinderx.so installed
perf c2c report --stdio --full-symbol > /tmp/c2c_idea_port_off.txt
```

Same yield_from-isolated probe shape as (b) — testkeeper 16:46:04Z RUN 2 + generalist 14:06:13Z probe driver.

`-F max` requests maximum sampling frequency permitted by perf-event-paranoid; if rate-limited, fall back to default.

## Outcome interpretation

Examine `perf c2c report --stdio --full-symbol` output `Cacheline (LLC misses)` table:

| Pattern | Interpretation |
|--|--|
| Patch-data symbols (`type_invalidation_counts`, `volatile_types`, `kVolatileTypeThreshold`) appear in IDEA-port-on top-N contended cache lines, ABSENT from IDEA-port-off | **(b3) CONFIRMED** — false-sharing mechanism on patch's added data; fix-path opens (`__attribute__((aligned(64)))` on patch's static data, OR move to dedicated cache-aligned section). |
| Patch-data symbols NOT in IDEA-port-on top-N contended cache lines | **(b3) FALSIFIED** — no false-sharing on patch's added data observable. LLC delta from (b) probe re-classifies as variance OR is mediated by some non-data cache effect. Move to hypothesis (c). |
| Patch-data symbols appear on BOTH substrates' contention lists (similar position) | False-sharing exists but is NOT IDEA-port-attributable — pre-existing pattern. Discharge (b3) as not-the-mechanism. |
| perf c2c output shows hot-path-function contention on cache lines NOT containing patch data, but with delta vs control | Non-patch contention pattern shifted by patch presence — record for hypothesis (c) candidate; (b3) inconclusive on patch-data sharing. |

Per spec (b) L72 cache-event variance: c2c reports are similarly noisy; recommend reps=2 per substrate + manual diff-review on top-20 cache lines (vs auto-comparison).

## Pre-flight gates

(P1) Build verify: both substrates clean; same flags as (b) probe (LTO=ON x86).
(P2) `perf c2c --help` returns non-error (tool available on x86 host).
(P3) `perf-event-paranoid` permits c2c access (typically requires ≤ 1 OR root).
(P4) Bench substrate sanity: IDEA-port-on `_cinderx.so` contains `type_invalidation_counts`, `volatile_types`, `kVolatileTypeThreshold` symbols (per `nm`); IDEA-port-off does NOT.
(P5) **Smoke gate (mandatory per (a)-recovery + (b)-inheritance)**: `cinderjit.is_jit_compiled(f) == True` after warmup at all 3 levels of yield_from chain (top / mid / bottom delegation frames). Skip-rationale "build-side cinderjit.auto() confirms" explicitly REJECTED per supervisor 14:08:37Z (P3) recovery directive. BLOCK bench if (P5) fails.

If (P3) fails → escalate per `feedback_tractable_infra_boundary.md`; perf-event-paranoid adjustment is alexie-authorizable per 10:30:07Z precedent.

## Time-cost estimate

- Pre-flight (P1)-(P5): ~10min (substrates already built from (b))
- perf c2c record × 2 substrates × reps=2 each: ~5-10min total
- perf c2c report extract + manual top-20 diff-review: ~15-25min (c2c output is dense; manual analysis required)
- Caller-chain refinement if patch data appears: +15-30min

Total: ~30-60min for (b3) discharge.

## Sequencing per supervisor 14:18:18Z

1. **Now**: this spec executes ((b3) c2c false-sharing).
2. **If (b3) CONFIRMED**: theologian assesses fix paths (alignment / section-isolation); v9 IDEA-spec amendment likely. Mechanism identified.
3. **If (b3) FALSIFIED**: LLC re-classifies as variance + hypothesis (c) dispatch (theologian (c) candidates already staged offline per shepard 14:15:34Z + my 14:16:00Z ack: c1 TLB / c2 dynamic-linker / c3 JIT-runtime indirect-call / c4 branch-predictor BTB / c5 HW pre-fetcher).
4. **After x86 finding lands**: ratify on ARM per alexie 13:54:22Z sequence.

## Theologian standby

When (b3) result lands, theologian assesses outcome interpretation table + dispatches next spec (fix-path OR (c) hypothesis) per supervisor's gate. Per chat-discipline umbrella + my pre-post chat-recency check: cited functions/percentages re-verified against generalist 09:19:10Z + 14:15:57Z primary-sources before any v9 IDEA-spec or follow-on probe spec composes.
