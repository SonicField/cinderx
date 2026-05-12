---
status: spec for hypothesis (a) shared-state probe per supervisor 2026-05-12 13:55:00Z heavyweight investigation dispatch
owner: theologian (spec); generalist (execution); gatekeeper (pre-flight verify)
trigger: alexie 2026-05-12 13:54:22Z option 4 pick "do the work on x86 - find and ratify on ARM"; supervisor 13:55:00Z dispatch with theologian-leads-spec on hypothesis (a) shared-state first
scope: hypothesis (a) of 3 enumerated by supervisor — does this patch's added file-local state (type_invalidation_counts map + volatile_types set in ic_volatile_types.cpp) get READ by jit::GlobalCacheManager::notifyDictUpdate's hot path or any of the other 4 hot-path functions on yield_from? Falsifies (a) if 0 reads/writes during yield_from inner loop.
audience: generalist (execution); gatekeeper (pre-flight); testkeeper (post-bench verify)
---

# Cluster5 — yield_from Shared-State Probe (Hypothesis A)

## Hypothesis under test

Hypothesis (a) per supervisor 13:55:00Z dispatch: "shared state — does our patch's added code (per-type counter / volatile-types set / recordTypeInvalidation) get READ by notifyDictUpdate's hot path even though it's not on our patch's call-graph?"

If 0 reads + 0 writes of `type_invalidation_counts` and `volatile_types` during a yield_from-isolated bench, hypothesis (a) is FALSIFIED for that benchmark; investigation moves to hypothesis (b) cache-line interaction (per supervisor 13:55:00Z spec).

## Hot-path functions per generalist 09:19:10Z perf-record primary-source

(Verified same-turn via `nbs-chat search "GlobalCacheManager::notifyDictUpdate"` per chat-discipline umbrella + my pre-post chat-recency check codification at 1471bed9.)

cluster5-pr 0c99ac89 + LTO=ON x86, yield_from chain bench:
- `jit::GlobalCacheManager::notifyDictUpdate` — 23.98% of cycles
- `jitgen_am_send` — 9.34% of cycles
- `cinderx_dict_watcher` — 3.17% of cycles
- `_PyClassLoader_NotifyDictChange` — 1.83% of cycles
- `JITRT_GenSend` — 1.60% of cycles

Patch's added functions: `notifyICsTypeChanged`, `recordTypeInvalidation`, `isVolatileType`, `TypeWatcher::watch` — ALL 0% per generalist 09:19:10Z perf-record (NOT on yield_from hot path).

## Probe shape

**Branch**: `cluster5-pr-tu-isolated-shared-state-probe` off `cluster5-pr-tu-isolated` (HEAD 92f5ae72) — uses TU-split substrate so the file-local state lives in `ic_volatile_types.cpp`. Same shape applies to cluster5-pr (HEAD 0c99ac89) pre-TU-split if alexie wants both substrates measured; spec defaults to TU-split substrate per alexie's ship-direction context.

**Instrumentation** in `cinderx/Jit/ic_volatile_types.cpp`:

```cpp
// Add at file scope:
static std::atomic<uint64_t> g_isVolatileType_read_count{0};
static std::atomic<uint64_t> g_recordTypeInvalidation_call_count{0};
static std::atomic<uint64_t> g_volatile_types_size_max{0};

// Inside isVolatileType(), before return:
g_isVolatileType_read_count.fetch_add(1, std::memory_order_relaxed);

// Inside recordTypeInvalidation(), before return:
g_recordTypeInvalidation_call_count.fetch_add(1, std::memory_order_relaxed);
uint64_t cur_size = volatile_types.size();
uint64_t prev_max = g_volatile_types_size_max.load(std::memory_order_relaxed);
while (cur_size > prev_max && !g_volatile_types_size_max.compare_exchange_weak(
    prev_max, cur_size, std::memory_order_relaxed)) {}

// Add reporting hook (callable from Python):
extern "C" void cinderx_volatile_type_probe_report(FILE* out) {
  fprintf(out,
      "isVolatileType_reads: %lu\n"
      "recordTypeInvalidation_calls: %lu\n"
      "volatile_types_size_max: %lu\n",
      g_isVolatileType_read_count.load(std::memory_order_relaxed),
      g_recordTypeInvalidation_call_count.load(std::memory_order_relaxed),
      g_volatile_types_size_max.load(std::memory_order_relaxed));
}
```

**Per gatekeeper 13:55:00Z (4) constraint** ("instrumentation should NOT change codegen on the hot path it's measuring"): instrumentation lives in `ic_volatile_types.cpp` — i.e., on this patch's added code path, NOT on `notifyDictUpdate` / `jitgen_am_send` / etc. hot path. Hot-path-function codegen unchanged. The relaxed-atomic increments add measurable cost only IF the functions are called; if hypothesis (a) is right and they're not called on yield_from, instrumentation overhead = 0 cycles on yield_from.

**Reporting hook**: Python-callable via cinderx module export. Bench script invokes the report hook before + after the timed yield_from inner loop.

## Bench

Same shape as testkeeper 16:46:04Z + 09:19:10Z yield_from-isolated direct script:
- 10000 warmup iterations
- 300K timed iterations
- Report hook before + after timed window
- Net delta = reads/calls during the timed inner loop

`PYTHONPATH=cinderx/PythonLib /usr/local/bin/python3 -c '<probe script with report hook + timed yield_from loop>'`

## Outcome interpretation

| Outcome | Interpretation |
|--|--|
| `isVolatileType_reads` delta = 0 AND `recordTypeInvalidation_calls` delta = 0 | Hypothesis (a) FALSIFIED for yield_from. Patch's file-local state is neither read nor written during yield_from inner loop. Investigation moves to hypothesis (b) cache-line interaction. |
| `isVolatileType_reads` delta > 0 OR `recordTypeInvalidation_calls` delta > 0 | Hypothesis (a) PARTIAL CONFIRM — there IS some access to patch's state during yield_from. Caller chain analysis required: which non-patch hot-path function indirectly triggers these calls? Likely candidates (require backtrace instrumentation): `_PyClassLoader_NotifyDictChange` → `notifyTypeModified` → `notifyICsTypeChanged` → `recordTypeInvalidation`; OR `cinderx_dict_watcher` direct path. |
| `volatile_types_size_max` > 0 at probe-end | Some type was classified volatile during the timed loop. If no reads/writes during loop but size > 0 at start, the volatile classification happened during warmup or before. Distinguish by comparing pre-loop and post-loop sizes (additional reporting hook needed). |

## Pre-flight gates

(P1) Build verify: `[[gnu::noinline]]` NOT applied to instrumented functions (let compiler inline as it would in production; relaxed-atomic increments are cheap inline).
(P2) Codegen-diff on `notifyDictUpdate`, `jitgen_am_send`, `cinderx_dict_watcher`, `_PyClassLoader_NotifyDictChange`, `JITRT_GenSend` between probe-instrumented build and current `cluster5-pr-tu-isolated` build: expect IDENTICAL bytes (instrumentation is in ic_volatile_types.cpp only; hot-path functions in different TUs).
(P3) Smoke gate: `is_jit_compiled()` post-warmup per `feedback_auto_mode_pre_abba_smoke_gate.md`.
(P4) Symbol verify: probe report function `cinderx_volatile_type_probe_report` exported.

If (P2) shows DIFFER on any hot-path function, instrumentation has shifted hot-path codegen → investigate before bench (per gatekeeper 13:55:00Z (4) constraint).

## Time-cost estimate

- Instrumentation edit + Python reporting-hook glue: ~20-30min
- Build clean + smoke + codegen-diff verify (P2): ~15-20min
- Bench (yield_from-isolated, 300K iter): ~1-2min
- Report extract + analysis: ~5min

Total: ~45-60min for hypothesis (a) discharge.

## Sequencing per supervisor 13:55:00Z

1. **Now**: this spec executes (hypothesis (a) shared-state).
2. **If (a) FALSIFIED**: theologian writes hypothesis (b) cache-line spec (separate file). Generalist executes.
3. **If (a) PARTIAL CONFIRM**: caller-chain backtrace instrumentation; iterate within (a) before moving to (b).
4. **After x86 finding lands**: ratify on ARM per alexie 13:54:22Z sequence.

## Theologian standby

When result lands, theologian assesses outcome interpretation table + dispatches next spec (hypothesis (b) or caller-chain) per supervisor's gate. v9 IDEA-spec amendment likely needed if mechanism identified.
