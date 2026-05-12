---
status: spec for hypothesis (b) cache-line probe per supervisor 2026-05-12 13:55:00Z heavyweight investigation dispatch + generalist 14:06:13Z hypothesis (a) FALSIFIED
owner: theologian (spec); generalist (execution); gatekeeper (pre-flight verify)
trigger: hypothesis (a) shared-state probe FALSIFIED at 14:06:13Z (0 reads + 0 calls during yield_from inner loop); per spec sequencing + supervisor 13:55:00Z dispatch, investigation moves to hypothesis (b) cache-line interaction
scope: hypothesis (b) of 3 enumerated by supervisor — does this patch's added data (file-local statics in ic_volatile_types.cpp post-TU-split, OR added bytes anywhere in binary pre-TU-split) cause L1/L2/LLC cache misses on the hot-path functions (notifyDictUpdate / jitgen_am_send / cinderx_dict_watcher / _PyClassLoader_NotifyDictChange / JITRT_GenSend)? Falsifies (b) if cache miss rates on yield_from bench match between IDEA-port and control builds.
audience: generalist (execution); gatekeeper (pre-flight); testkeeper (post-bench verify)
---

# Cluster5 — yield_from Cache-Line Probe (Hypothesis B)

## Hypothesis under test

Hypothesis (b) per supervisor 13:55:00Z dispatch: "cache-line interaction — does our patch's added data live close enough to notifyDictUpdate's hot data to cause L1/L2 misses?"

Refined scope per generalist 14:06:13Z hypothesis (a) FALSIFICATION evidence: patch's file-local state is NEVER touched during yield_from (0 reads + 0 calls process-lifetime). So direct shared-state cache effects are ruled out. The remaining cache-line mechanism candidates:

(b1) **Code-bytes layout shift**: patch adds 21 lines of code anywhere in binary; downstream symbols' addresses shift; instruction-cache layout for hot-path functions changes; iCache miss rate increases on hot path.

(b2) **Data-section layout shift**: patch adds file-local statics (type_invalidation_counts + volatile_types) to BSS/data segment; downstream symbols' addresses shift; data-cache layout for hot-path data accesses changes; dCache miss rate increases on hot path.

(b3) **False sharing (c2c)**: patch's data lands on cache line shared with hot-path data, even though never accessed during yield_from; cache coherency traffic (e.g., from background type-invalidation in OTHER threads or cold-path workloads) evicts the shared line containing hot-path data. Less likely given testkeeper 16:46:04Z showed 0 invalidation calls on yield_from-isolated run, but possible if invalidations happen during process startup / module-load.

Falsifies (b) entirely if all three sub-mechanisms show null cache-miss-rate delta between IDEA-port and control builds.

## Probe shape

**Substrates** (compare two builds on x86 LTO=ON to match ship config):
- IDEA-port-on: `cluster5-pr-tu-isolated` (HEAD 92f5ae72) — TU-split substrate, x86 LTO=ON, fresh build
- IDEA-port-off: `cinderx-main` (HEAD 28a57df8 per generalist 09:19:10Z + 09:46:47Z perf-record substrate) — control build, x86 LTO=ON, fresh build

Both builds use the SAME bench harness (spec-exp build.sh + benchmark_cinderx.py per generalist 08:04:00Z x86 build-tooling caveat) for direct comparability.

**Tool**: `perf stat -e <cache-events>` on yield_from-isolated bench script (same shape as testkeeper 16:46:04Z RUN 2 — 10000 warmup + 300K timed iter).

**Cache events** (Linux perf hardware counters; verify availability via `perf list` per gatekeeper pre-flight):
- `L1-icache-load-misses` — instruction cache misses (tests b1 code-layout shift)
- `L1-dcache-load-misses` — L1 data cache misses (tests b2 data-layout shift)
- `LLC-load-misses` — last-level cache misses (tests b1+b2 at LLC level)
- `cache-misses` — generic cache misses fallback if specific events unavailable
- Optional: `cache-references` for normalization (miss rate = misses / references)

**Per gatekeeper 13:55:00Z (4) constraint**: perf hardware counters DO NOT modify codegen — they read CPU performance counters directly. Constraint satisfied trivially. No codegen-diff pre-flight needed (vs hypothesis (a) probe which added counter increments).

**False-sharing refinement (b3)**: if (b1) + (b2) coarse-grained probes show null delta, fall back to `perf c2c` on yield_from bench against IDEA-port-on substrate to detect cache-line sharing patterns on patch's added data symbols (type_invalidation_counts + volatile_types).

## Bench shape

```
# IDEA-port-on:
perf stat -e L1-icache-load-misses,L1-dcache-load-misses,LLC-load-misses,cache-misses,cache-references \
  -- /usr/local/bin/python3 -c '<yield_from-isolated probe script>'

# IDEA-port-off (control):
# Same command, same substrate (cinderx-main 28a57df8 + same build flags) different installed _cinderx.so

# Run reps=5 each side; compute mean + variance per event
```

Same yield_from-isolated probe shape as testkeeper 16:46:04Z RUN 2 + generalist 14:06:13Z probe report scaffolding (re-use the bench driver script).

## Outcome interpretation

Per-event delta = (IDEA-port-on miss rate) − (control miss rate); positive delta = IDEA-port has more misses.

| Event | Delta interpretation |
|--|--|
| `L1-icache-load-misses` significantly higher on IDEA-port (>10% relative) | b1 code-layout shift confirmed; iCache mechanism on yield_from hot path. |
| `L1-dcache-load-misses` significantly higher on IDEA-port | b2 data-layout shift confirmed; dCache mechanism on yield_from hot path. |
| `LLC-load-misses` significantly higher on IDEA-port (without L1 deltas) | LLC-level effect; possibly b3 false-sharing or longer-tail eviction patterns. |
| ALL events within ±5% noise band | hypothesis (b) FALSIFIED at coarse level; consider perf c2c (b3) refinement OR move to hypothesis (c) "something else." |

R5-band ±0.02 from feedback_r5_upper_edge_tolerance.md applies to wallclock; cache-event variance is typically higher (hardware counters can drift); recommend at least reps=5 per substrate + report mean ± std-dev. Mid-band ambiguity defers to supervisor.

## Pre-flight gates

(P1) Build verify: both IDEA-port-on and IDEA-port-off builds clean, same flags, same harness.
(P2) `perf list | grep -E "L1-icache|L1-dcache|LLC|cache-misses"` to verify event availability on x86 host (devgpu009 / x86 dev).
(P3) `perf-event-paranoid` permits hardware-counter access (may need root or `/proc/sys/kernel/perf_event_paranoid` ≤ 2).
(P4) Bench substrate sanity: IDEA-port-on `_cinderx.so` contains the volatile-type symbols; IDEA-port-off does NOT (per generalist 09:19:10Z + 09:46:47Z verifier scripts).
(P5) **Smoke gate (mandatory)**: `cinderjit.is_jit_compiled(f) == True` after warmup at all 3 levels of the yield_from chain (top / mid / bottom delegation frames) per `feedback_auto_mode_pre_abba_smoke_gate.md` + supervisor 14:08:37Z (P3) recovery directive on hypothesis (a). Skip rationale "build-side cinderjit.auto() in driver script confirms JIT live" is INSUFFICIENT — explicit per-function `is_jit_compiled()` check required pre-bench. Generalist 14:06:13Z's (P3) skip on (a) was supervisor-corrected at 14:07:06Z; (b) inherits that correction as mandatory P5.

If (P3) fails → escalate per `feedback_tractable_infra_boundary.md` (root-blocked); generalist's prior workaround (sudo dnf, alexie-authorized 10:30:07Z) suggests perf-event-paranoid adjustment is also alexie-authorizable if needed.

If (P5) fails → BLOCK bench; the yield_from chain frames must be JIT-compiled to test the actual hot-path codegen we care about. Interpreter-fallback would measure the wrong thing.

## Time-cost estimate

- Pre-flight (P1)-(P4): ~10min
- Bench × 2 substrates × reps=5 each: ~10-15min total (yield_from-isolated is fast; cache-event sampling overhead minimal)
- Result extract + analysis + delta computation: ~15-20min
- (Optional) perf c2c follow-up if (b1)+(b2) null: ~30-60min

Total: ~45-60min for hypothesis (b1)+(b2) discharge; +30-60min if (b3) c2c needed.

## Sequencing per supervisor 13:55:00Z

1. **Now**: this spec executes (hypothesis (b) cache-line via perf stat).
2. **If (b1)+(b2) FALSIFIED**: perf c2c follow-up for (b3) false-sharing OR move to hypothesis (c) "something else we haven't hypothesized."
3. **If (b) CONFIRMED at any sub-mechanism**: theologian assesses fix paths (e.g., `__attribute__((aligned))` on patch's data, or moving data to an isolated section); v9 IDEA-spec amendment likely.
4. **After x86 finding lands**: ratify on ARM per alexie 13:54:22Z sequence.

## Theologian standby

When result lands, theologian assesses outcome interpretation table + dispatches next spec (hypothesis (c) OR fix-path spec) per supervisor's gate. Pythia + librarian primary-source verification expected on the cited percentages + falsification thresholds before generalist execution; per chat-discipline umbrella, theologian does NOT post architectural read until peer-empirical-settled.
