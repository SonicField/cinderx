---
status: spec for hypothesis (c) unified uarch probe per supervisor 2026-05-12 14:23:13Z dispatch
owner: theologian (spec); generalist (execution); gatekeeper (pre-flight verify)
trigger: hypothesis (a)/(b)/(b3) all FALSIFIED; LLC mid-band re-classified as variance per supervisor 14:23:13Z; coarse cache + false-sharing mechanisms exhausted; dispatch unified (c) probe covering (c1) TLB + (c4) branch-predictor + (c5) HW-prefetcher in single perf-stat invocation. (c2) dynamic-linker + (c3) JIT-runtime indirect-call deferred per supervisor.
scope: 3 sub-mechanism candidates from theologian 14:16:17Z offline pre-stage now committed: (c1) TLB pressure from added BSS/data; (c4) branch-predictor BTB/RSB pollution from added code addresses; (c5) HW pre-fetcher pattern mis-train. Single perf-stat invocation with 6-8 hardware events per substrate; reps=5 each side. Same (P1)-(P5) template as (b)/(b3).
audience: generalist (execution); gatekeeper (pre-flight); testkeeper (post-bench verify)
---

# Cluster5 — yield_from Unified Microarchitectural Probe (Hypothesis C)

## Hypothesis under test

Per supervisor 14:23:13Z: "Move to hypothesis (c). Coarse cache + false-sharing mechanisms exhausted." Unified probe covering 3 microarchitectural sub-mechanism candidates:

(c1) **TLB pressure**: patch's added BSS/data (type_invalidation_counts UnorderedMap header + volatile_types UnorderedSet header) increase mapped page footprint; downstream symbols' addresses shift; TLB layout for hot-path data accesses changes; dTLB / iTLB miss rate increases on hot path.

(c4) **Branch-predictor BTB/RSB pollution**: patch's added functions (notifyICsTypeChanged + recordTypeInvalidation + isVolatileType + TypeWatcher::watch wrapper) live at addresses in binary; even with 0% execution per generalist 14:06:13Z, BTB-tag-aliasing with hot-path branches in notifyDictUpdate / jitgen_am_send / etc. could cause branch-misprediction rate increase on hot path.

(c5) **HW pre-fetcher mis-train**: patch's added data accesses during process startup / module-load / warmup train pre-fetcher; downstream yield_from inner loop accesses are mis-predicted by pre-fetcher trained on patch's pattern. Less likely given (a) showed 0 reads/writes during yield_from inner loop, but plausible for warmup-phase training that persists into timed window.

Falsifies (c) entirely if all 3 sub-mechanism event-classes show null delta (within ±5% noise) between IDEA-port-on and IDEA-port-off substrates. Then yield_from residual mechanism is empirically unidentified at perf-stat granularity; remaining paths require either (c2) dynamic-linker analysis (deferred per supervisor) or (c3) JIT-runtime indirect-call layout (deferred), or accepting residual as unattributed.

## Probe shape

**Substrates** (same as (b)/(b3)):
- IDEA-port-on: `cluster5-pr-tu-isolated` HEAD 92f5ae72 + LTO=ON x86 (reuse (b) build)
- IDEA-port-off: `cinderx-main` HEAD 28a57df8 + LTO=ON x86 (control; reuse (b) build)

**Tool**: `perf stat -e <events>` on yield_from-isolated bench (same harness as (a)/(b)/(b3)).

**Events** (verify availability via `perf list` per (P2)):
- (c1) TLB: `dTLB-load-misses`, `dTLB-store-misses`, `iTLB-load-misses`
- (c4) Branch-predictor: `branch-misses`, `branch-instructions` (compute branch-miss-rate = misses / instructions); on Intel optionally `br_misp_retired.all_branches` family
- (c5) HW pre-fetcher: indirect proxy via existing miss counters; primary: `L2_RQSTS.all_pf` (L2 prefetch requests) on Intel, OR `cache-misses` re-used as gross proxy. Direct pre-fetcher mis-train detection requires sampling-based analysis not in scope; perf-stat-level proxy is acceptable for coarse falsification.

**Per gatekeeper 13:55:00Z (4) constraint**: perf hardware counters DO NOT modify codegen — constraint trivially satisfied. No codegen-diff pre-flight needed.

## Bench shape

```
# IDEA-port-on:
perf stat -e dTLB-load-misses,dTLB-store-misses,iTLB-load-misses,branch-misses,branch-instructions,cache-misses,L2_RQSTS.all_pf,cache-references \
  -- /usr/local/bin/python3 -c '<yield_from-isolated probe script>'

# IDEA-port-off (control):
# Same command, control substrate _cinderx.so installed
```

reps=5 each side; compute mean ± std-dev per event; signal/noise threshold ±5% noise band per spec (b)/(b3) precedent.

## Outcome interpretation

Per-event delta = (IDEA-port-on rate) − (control rate); positive = IDEA-port has more misses/mispredicts.

| Event class | Sub-mechanism | Falsifier (within ±5% noise) | Confirm (>±5% delta) |
|--|--|--|--|
| dTLB-load + dTLB-store + iTLB miss-rate deltas | (c1) TLB pressure | All 3 within noise → (c1) FALSIFIED | Any >5% → (c1) candidate; refine analysis |
| branch-miss-rate delta (misses / instructions) | (c4) BTB/RSB pollution | Within noise → (c4) FALSIFIED | >5% → (c4) candidate; refine analysis (BTB-vs-RSB discrimination) |
| L2 prefetch counter delta + cache-misses delta | (c5) HW pre-fetcher | Both within noise → (c5) FALSIFIED | Either >5% → (c5) candidate; refine analysis (training-window probe) |

If ALL 3 sub-mechanisms FALSIFY at coarse level → cumulative state is "yield_from residual mechanism unidentified at all coarse-perf-stat probe levels (a + b + b3 + c1 + c4 + c5)". Escalate to alexie: accept residual as unattributed OR authorize (c2) dynamic-linker / (c3) JIT-runtime indirect-call / (c-other) deeper investigation.

If ANY sub-mechanism CONFIRMS → theologian assesses fix-path candidates + dispatches refinement spec; mechanism identified.

## Pre-flight gates

(P1) Build verify: substrates from (b)/(b3) reused; verify still in place + clean.
(P2) `perf list | grep -E "dTLB|iTLB|branch-misses|branch-instructions|L2_RQSTS"` to verify event availability on x86 host (devgpu009 / x86 dev). Note: some events are CPU-vendor-specific (Intel vs AMD); fallback to generic events if Intel-specific unavailable per (b) (b1) iCache precedent.
(P3) `perf-event-paranoid` permits hardware-counter access (alexie-authorized 10:30:07Z baseline).
(P4) Bench substrate sanity: IDEA-port-on `_cinderx.so` contains the volatile-type symbols; IDEA-port-off does NOT (per generalist 09:19:10Z + 09:46:47Z verifier scripts).
(P5) **Smoke gate (mandatory per (a)-recovery + (b)/(b3) inheritance)**: `cinderjit.is_jit_compiled(f) == True` after warmup at all 3 levels of yield_from chain (top / mid / bottom delegation frames). Skip-rationale "build-side cinderjit.auto() confirms" explicitly REJECTED. BLOCK bench if (P5) fails.

## Time-cost estimate

- Pre-flight (P1)-(P5): ~5min (substrates + tooling reused from (b)/(b3))
- perf stat × 2 substrates × reps=5 each: ~10-15min
- Per-event delta computation + 3-sub-mechanism interpretation: ~15-20min

Total: ~30-45min for unified (c1)+(c4)+(c5) discharge.

## Sequencing per supervisor 14:23:13Z

1. **Now**: this spec executes (unified (c) uarch probe).
2. **If ANY sub-mechanism CONFIRMS**: theologian dispatches refinement + fix-path spec; mechanism identified; v9 IDEA-spec amendment likely.
3. **If ALL FALSIFY**: escalate to alexie — accept residual unattributed OR authorize (c2) dynamic-linker investigation OR (c3) JIT-runtime indirect-call OR deeper microarchitectural analysis. Per alexie 13:54:22Z "time budget is well paid" — heavyweight authorized but at supervisor's gate.
4. **After x86 finding lands**: ratify on ARM per alexie 13:54:22Z sequence.

## Theologian standby

When (c) result lands, theologian assesses outcome interpretation table + dispatches next spec (refinement / fix-path / escalation) per supervisor's gate. Per chat-discipline umbrella + my pre-post chat-recency check codification: cited functions/percentages re-verified against generalist 09:19:10Z + 14:15:57Z + 14:22:32Z primary-sources before any v9 IDEA-spec or follow-on probe spec composes.
