---
status: spec for generalist execution; ~2-3hr time-box per supervisor 17:03:14Z
owner: theologian (spec); generalist (execution)
trigger: alexie 2026-05-11 17:02:28Z directive to investigate yield_from mechanism + supervisor 17:03:14Z dispatch for TU-isolation experiment as cleanest mechanism #3 test
scope: split IDEA-port symbols out of cinderx/Jit/inline_cache.cpp into a new translation unit; rebuild; re-bench yield_from. Falsifies/confirms compiler-inlining-shift mechanism (#3) on yield_from cross-arch regression. NOT a PR-shape change yet — this is a mechanism-falsification experiment.
audience: generalist (execution); supervisor (sequencer); testkeeper (verify post-bench)
backing references:
  - PR commit on cluster5-pr branch: 0c99ac89
  - IDEA-port code: cinderx/Jit/inline_cache.cpp +21 lines
  - testkeeper 2026-05-11 16:46:04Z: caveat-#2 + always-paid mechanism candidates EMPIRICALLY FALSIFIED on yield_from
  - generalist 2026-05-11 16:55:38Z: yield_from is the only cross-arch IDEA-port-attributable regression
  - theologian 2026-05-11 16:55:11Z + 16:57:43Z bimodal mechanism + TU-isolation framing
  - CMakeLists.txt L374: file(GLOB_RECURSE JIT_SOURCES Jit/*.cpp ...) — auto-picks-up new .cpp files in Jit/
---

# Cluster 5 — TU-isolation Patch Spec

## What this experiment tests

Hypothesis: yield_from -4-6% cross-arch regression is caused by mechanism #3 (compiler-inlining shift on cinderx/Jit/inline_cache.cpp adjacent paths from the +21-line IDEA-port code-size addition).

Test: move the IDEA-port symbols out of inline_cache.cpp into a new translation unit (new .cpp). If yield_from regression DISAPPEARS post-rebuild, mechanism #3 is CONFIRMED + we have a ship-with-TU-split path. If yield_from regression PERSISTS, mechanism #3 is FALSIFIED + the search returns to "different mechanism for yield_from."

This is a mechanism-falsification experiment, not a PR-shape change. Branch: `cluster5-pr-tu-isolated` off `cluster5-pr` (= 0c99ac89). The current cluster5-pr branch state stays untouched until alexie verdicts on outcome.

## Symbols to MOVE out of cinderx/Jit/inline_cache.cpp

Source: speculation-experiment commit d941a26a, lines now in inline_cache.cpp at the 0c99ac89 substrate (anonymous namespace block):

```cpp
constexpr int kVolatileTypeThreshold = 10;

jit::UnorderedMap<BorrowedRef<PyTypeObject>, int> type_invalidation_counts;
jit::UnorderedSet<BorrowedRef<PyTypeObject>> volatile_types;

bool isVolatileType(BorrowedRef<PyTypeObject> type) {
  return volatile_types.count(type) > 0;
}

void recordTypeInvalidation(BorrowedRef<PyTypeObject> type) {
  int& count = type_invalidation_counts[type];
  count++;
  if (count >= kVolatileTypeThreshold) {
    volatile_types.emplace(type);
  }
}
```

(5 entities: 1 constant + 1 map + 1 set + 2 functions; 14 lines of substantive code.)

## Symbols that STAY in cinderx/Jit/inline_cache.cpp

Source: 2 invocation points the moved helpers are called from. These call into the moved helpers but their bodies stay in inline_cache.cpp.

(a) Inside `TypeWatcher::watch()` body, first line — early-return:
```cpp
if (isVolatileType(type)) {
  return;
}
```

(b) Inside `notifyICsTypeChanged()` body, first line — record invocation:
```cpp
recordTypeInvalidation(type);
```

These 4 lines (2 + 2 with brace formatting) stay at the original sites in inline_cache.cpp. Total inline_cache.cpp net delta vs upstream = +4 lines (the invocations) + #include of new header. Was +21 lines under current 0c99ac89 cluster5-pr substrate.

## NEW FILE: cinderx/Jit/ic_volatile_types.cpp

Holds the moved 14 lines (constant + map + set + 2 functions). Anonymous-namespace-internal state (the map + set) stays file-local to this new .cpp. The 2 functions become external symbols (header-declared) so inline_cache.cpp can call them.

```cpp
// cinderx/Jit/ic_volatile_types.cpp
//
// Per-type IC invalidation tracking + volatile-type predicate.
// Split from inline_cache.cpp at the cluster5-pr-tu-isolated branch
// (theologian 2026-05-11) to test the mechanism #3 hypothesis: that
// the +21-line code-size addition in inline_cache.cpp shifts compiler
// inlining decisions on adjacent hot paths in the same translation
// unit.

#include "cinderx/Jit/ic_volatile_types.h"

#include "cinderx/Common/hashed_map.h" // jit::UnorderedMap, jit::UnorderedSet
#include "cinderx/Common/borrowed_ref.h" // BorrowedRef<PyTypeObject>

namespace jit {

namespace {

constexpr int kVolatileTypeThreshold = 10;

jit::UnorderedMap<BorrowedRef<PyTypeObject>, int> type_invalidation_counts;
jit::UnorderedSet<BorrowedRef<PyTypeObject>> volatile_types;

}  // namespace

bool isVolatileType(BorrowedRef<PyTypeObject> type) {
  return volatile_types.count(type) > 0;
}

void recordTypeInvalidation(BorrowedRef<PyTypeObject> type) {
  int& count = type_invalidation_counts[type];
  count++;
  if (count >= kVolatileTypeThreshold) {
    volatile_types.emplace(type);
  }
}

}  // namespace jit
```

Note: `#include` paths above are placeholders — generalist verify the actual cinderx headers for `jit::UnorderedMap` / `jit::UnorderedSet` (likely `cinderx/Common/util.h` or similar) and `BorrowedRef<>` (likely `cinderx/Common/ref.h` or `cinderx/Common/borrowed.h`). Same headers inline_cache.cpp uses for these types.

## NEW HEADER: cinderx/Jit/ic_volatile_types.h

Declares the 2 functions for use from inline_cache.cpp.

```cpp
// cinderx/Jit/ic_volatile_types.h
#pragma once

#include "cinderx/Common/borrowed_ref.h"  // BorrowedRef<PyTypeObject>

namespace jit {

bool isVolatileType(BorrowedRef<PyTypeObject> type);
void recordTypeInvalidation(BorrowedRef<PyTypeObject> type);

}  // namespace jit
```

## EDITS to cinderx/Jit/inline_cache.cpp

(1) Add `#include "cinderx/Jit/ic_volatile_types.h"` at top with other Jit/ includes.

(2) DELETE the 14-line block in the anonymous namespace (the constant + map + set + isVolatileType + recordTypeInvalidation function bodies). Leave the surrounding `namespace jit { namespace { ... } }` structure intact for any other anonymous-namespace contents.

(3) The 2 invocation points stay AS-IS:
- `if (isVolatileType(type)) { return; }` at top of `TypeWatcher::watch()` body
- `recordTypeInvalidation(type);` at top of `notifyICsTypeChanged()` body

After edits, inline_cache.cpp delta vs upstream master = +4 lines (the 2 invocations) + 1 header include. Was +21 lines under cluster5-pr substrate.

## Build

CMakeLists.txt L374 uses `file(GLOB_RECURSE JIT_SOURCES Jit/*.cpp ...)` — the new ic_volatile_types.cpp is auto-picked-up by glob. No CMake edits needed.

Build command (matches today's cluster5-pr build invocation):
```
PATH=/data/users/alexturner/dotsync-home/.local/bin:$PATH ./build.sh --clean
```
(Uses dotsync cmake per arm64-workbook §A.2 if on devgpu004; on x86 host, default cmake.)

## Smoke gate (per memory feedback_auto_mode_pre_abba_smoke_gate.md)

```
PYTHONPATH=cinderx/PythonLib /usr/local/bin/python3 -c "
import cinderjit
def f(x): return x*2+1
cinderjit.auto()
cinderjit.compile_after_n_calls(10)
for _ in range(20): f(42)
assert cinderjit.is_jit_compiled(f), 'JIT not active'
print('Smoke gate PASS')
"
```

## Bench

(a) yield_from-isolated quick bench (~5 min): same shape as testkeeper 16:46:04Z RUN 2 — yield_from inner loop, 10000 warmup + 300K timed iter. Quick falsifier.

(b) If (a) shows yield_from regression DISAPPEARS or shrinks meaningfully on cluster5-pr-tu-isolated vs cluster5-pr, run full 29-bench reps=5 for cross-arch verify framing:
```
PYTHONPATH=cinderx/PythonLib /usr/local/bin/python3 ./benchmark_cinderx.py jit --compile=auto --reps=5
```

## Result interpretation

Compare yield_from speedup on cluster5-pr-tu-isolated artifact vs:
- TODAY's port-on artifact: benchmarks/2026-05-11_010339_28a57df8_x86_64_abba.txt (yield_from 1.04x)
- TODAY's control artifact: benchmarks/2026-05-11_032727_28a57df8_x86_64_abba_CONTROL.txt (yield_from 1.08x)

| outcome | inference |
|---------|-----------|
| TU-isolated yield_from ≈ control 1.08x | mechanism #3 CONFIRMED — TU-split removes the inlining-shift; ship-with-TU-split path opens for v6 IDEA-spec |
| TU-isolated yield_from ≈ port-on 1.04x | mechanism #3 FALSIFIED for yield_from — different mechanism; investigation continues |
| TU-isolated yield_from somewhere between 1.04x and 1.08x | partial mitigation — TU-split shrinks but doesn't eliminate (LTO cross-TU inlining residual); v6 framing scoped to "partial mitigation possible" |

If mechanism #3 CONFIRMED, full 29-bench reps=5 will also show whether the 4 x86-specific regressions move (per testkeeper 16:57:01Z framing they likely don't, since they're cross-arch-inconsistent and not within-TU inlining-shift family).

## Branch / commit shape

(1) `git checkout -b cluster5-pr-tu-isolated cluster5-pr` (off 0c99ac89)
(2) Apply this spec's edits (3 files: ic_volatile_types.cpp NEW + ic_volatile_types.h NEW + inline_cache.cpp MODIFIED -14/+5)
(3) Build + smoke + bench
(4) Commit on cluster5-pr-tu-isolated branch with descriptive message ("experimental: TU-isolation of IDEA-port symbols for mechanism #3 falsification on yield_from")
(5) DO NOT push; experimental branch only. cluster5-pr stays at 0c99ac89.

## Time-cost estimate

- Spec-application: ~10 min (3 file edits)
- Build + smoke gate: ~10-15 min
- yield_from-isolated bench: ~5 min
- Full 29-bench (if yield_from looks promising): ~25-35 min
- Result analysis + post: ~10 min

Total: ~60-90 min for the falsification experiment. Per supervisor's ~2-3hr time-box, ample budget.

## Theologian standby for outcome

When result lands, theologian executes v6 IDEA-spec amendment via worktree pattern. Path-conditional content depends on outcome per Result interpretation table above; v6 draft text already staged at 6be712de + 371e2a1c.
