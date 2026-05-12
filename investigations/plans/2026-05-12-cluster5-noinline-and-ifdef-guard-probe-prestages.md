---
status: pre-stage specs for 2 cheap probes per supervisor 2026-05-12 06:10:11Z naming + shepard 06:37:42Z theologian dispatch
owner: theologian (specs); generalist (execution if alexie picks "try one more")
trigger:
  - supervisor 06:10:11Z naming: "two more cheap probes are possible (a noinline-attribute wrapper that forces non-inlining, or an ifdef-guard that compiles the patch out entirely) — both could also return null if mechanism is something else again"
  - shepard 06:37:42Z dispatch: "@theologian → pre-stage spec for noinline-attr + ifdef-guard probes per supervisor 06:10:11Z, in case alexie picks 'try one more'"
  - per librarian 20:46:28Z: probe-creep moratorium scoped to NEW suggestions; supervisor-named-probe shape-clarification in-scope
  - prior null probes: matched-LTO (D-1778537595) + ARM-LTO=OFF inline-shim (D-1778550854 → IDENTICAL bytes) — both informed shape of these two
scope: 2 probe specs as fast-fire-ready material if alexie picks option (4) "try one more probe" from supervisor 06:10:11Z 4-option menu. NOT proposing the probes; specifying their shape so the dispatch loop is short.
audience: generalist (execution); supervisor (dispatch); gatekeeper (gate-shape pre-stage)
---

# Cluster 5 — Noinline-Attr + Ifdef-Guard Probe Pre-Stages

## What this document is

Two cheap-probe specs, each ready for fast dispatch if alexie picks option (4) "try one more" from supervisor 06:10:11Z 4-option menu. Each spec includes shape, substrate, falsifier interpretation, scope-limits, and time-cost. Per umbrella rule 4 symmetric-rigor: scope-limits explicit at pre-stage, not post-bench.

Both specs anchor on cluster5-pr-tu-isolated-shim-moved branch (d292a01e) as the most-recent branch with all wrapper infrastructure already in place; alternate-anchor on cluster5-pr-tu-isolated (92f5ae72) is also viable.

---

## Probe A: Noinline-Attribute Wrapper

### Goal

Force the wrapper functions in `ic_volatile_types.h` to NOT inline at compile time, so the wrapper's CALL/RET instructions live in `inline_cache.cpp.o` instead of inlining into the call site. Tests whether moving the inlined bytes OUT of `inline_cache.cpp` adjacent code changes mech #3 contribution from the inlined wrapper bytes.

### Shape

Same 3-file shape as inline-shim spec b215dcc5 + the d292a01e wrapper edit, with one modification: add `[[gnu::noinline]]` (GCC/clang attribute, supported on both x86 and ARM toolchains) to the wrapper function definitions in `ic_volatile_types.h`.

```cpp
// cinderx/Jit/ic_volatile_types.h — modified for Probe A
#pragma once
#include "cinderx/Common/borrowed_ref.h"

namespace jit {

[[gnu::noinline]]
inline bool watchSkipVolatile(BorrowedRef<PyTypeObject> type) {
  return isVolatileType(type);
}

[[gnu::noinline]]
inline void watchRecord(BorrowedRef<PyTypeObject> type) {
  recordTypeInvalidation(type);
}

bool isVolatileType(BorrowedRef<PyTypeObject> type);
void recordTypeInvalidation(BorrowedRef<PyTypeObject> type);

}  // namespace jit
```

`inline_cache.cpp` call sites unchanged from d292a01e (they already call `watchSkipVolatile` / `watchRecord`).

Result: `inline_cache.cpp.o` now contains explicit CALL instructions for the 2 wrapper sites (TypeWatcher::watch + notifyICsTypeChanged) instead of inlined wrapper bodies. Wrapper bodies live as out-of-line functions in `ic_volatile_types.cpp.o` (or possibly inlined-elsewhere; verify).

### Substrate

ARM-LTO=OFF (devgpu004), same as ARM inline-shim probe substrate per pythia 280 substrate-shift reasoning + matched-LTO finding (largest residual lives at ARM-LTO=OFF).

### Pre-flight gates (per gatekeeper REV3 + workbook §A discipline)

(P1) ARM toolchain check: `[[gnu::noinline]]` supported by clang 21.1.8 (devgpu004) — verify via `echo 'inline __attribute__((noinline)) int f(){return 0;} int main(){return f();}' | clang -x c++ -O3 -c - -o /dev/null` returns 0.
(P2) Bundle-transfer per workbook §0.3 (scp via nbs-local-run; `--handle` mandatory when `--chat` set per workbook §2.3 FAILURE MODE).
(P3) `./build.sh --clean` on devgpu004 (LTO=OFF default; per workbook §A.2 PATH-prepend for cmake).
(P4) Smoke-gate per `feedback_auto_mode_pre_abba_smoke_gate.md`.

### PHASE 1 codegen-diff (~5min)

`objdump -d` on TypeWatcher<AttributeCache>::watch + notifyICsTypeChanged in shim-moved (d292a01e) build vs Probe-A build.

Expected: bytes DIFFER (CALL instructions added; inlined bytes removed). If IDENTICAL, `[[gnu::noinline]]` did not take effect (compiler ignored attribute) — investigate before bench.

### PHASE 2 bench (only if codegen DIFFERS)

ARM yield_from reps=5 per generalist 19:11:31Z + 22:12:48Z bench shape on cluster5-pr-tu-isolated-shim-moved-noinline branch.

### Outcome interpretation (per gatekeeper REV3 R5-band ±0.02)

Compare ARM yield_from:
- TU-baseline (cluster5-pr-tu-isolated 92f5ae72): 0.90x
- shim-moved baseline (d292a01e): 0.90x (codegen-identical to TU per generalist 06:07:27Z)
- Control (no IDEA-port): 0.95x

Probe A outcomes:
- yield_from ≈ 0.95x ± 0.02 (≥ 0.93x): noinline removed within-TU inlined-bytes contribution to mech #3; mech #3 confirmed for wrapper-inlined-bytes slice; ship-with-noinline-wrapper opens as new option.
- yield_from ≈ 0.90x ± 0.02 (≤ 0.92x): noinline did not change yield_from; mech #3 contribution from wrapper-inlined-bytes is null; residual mech is something else (function-call overhead from noinline likely cancelled any inlining-shift gain).
- 0.92-0.93x: defer-to-supervisor mid-band per gatekeeper REV3.

### Scope-limits (per pythia 281 #4 + supervisor 01:41:47Z (4))

- Probe A only tests within-TU inlining-shift contribution from wrapper-inlined-bytes. Other mech #3 contributions (e.g., shim-moved baseline's call instructions to external symbols, ic_volatile_types.cpp.o linking effects) NOT tested.
- ARM-LTO=OFF substrate ≠ x86-LTO=ON ship substrate. Outcome on ARM does NOT directly answer x86 ship-config mech #3 attribution. Per pythia 281 #4: x86-LTO=ON mech #3 attribution remains structurally untestable via this probe family.
- noinline introduces function-call overhead per watcher-registration event (rare per testkeeper 16:46:04Z: 0 calls during yield_from-isolated run). Overhead expected to be ≤1 cycle per registration; not a perf concern at observed rates.

### Time-cost

~50-70min: bundle scp + build clean + smoke + bench reps=5 + transfer-back + codegen-diff verify.

---

## Probe B: Ifdef-Guard Total IDEA-Port Removal

### Goal

Compile out the entire IDEA-port via `#ifdef` guard, so the build produces a binary with NO IDEA-port code anywhere. Tests whether total IDEA-port absence vs presence matches the cross-arch yield_from delta — degenerate but discriminating between "IDEA-port AS A WHOLE causes regression" vs "regression is something orthogonal to IDEA-port."

### Shape

Add `#ifdef ENABLE_VOLATILE_TYPE_TRACKING` guards around 3 sites in `inline_cache.cpp`:
1. The `#include "cinderx/Jit/ic_volatile_types.h"` line
2. The `if (isVolatileType(type)) { return; }` early-return in TypeWatcher::watch
3. The `recordTypeInvalidation(type);` call in notifyICsTypeChanged

```cpp
// inline_cache.cpp modifications for Probe B
#ifdef ENABLE_VOLATILE_TYPE_TRACKING
#include "cinderx/Jit/ic_volatile_types.h"
#endif

// ... inside TypeWatcher::watch():
#ifdef ENABLE_VOLATILE_TYPE_TRACKING
  if (isVolatileType(type)) {
    return;
  }
#endif
  // ... existing code ...

// ... inside notifyICsTypeChanged():
#ifdef ENABLE_VOLATILE_TYPE_TRACKING
  recordTypeInvalidation(type);
#endif
  // ... existing typeChanged calls ...
```

CMakeLists.txt unchanged; the build can be invoked WITH `-DENABLE_VOLATILE_TYPE_TRACKING` (current behavior) or WITHOUT (degenerate test).

### Substrate

ARM-LTO=OFF (devgpu004), same reasoning as Probe A.

### Caveat per librarian 20:46:28Z

The ifdef-guard change ITSELF modifies `inline_cache.cpp` source bytes (adds preprocessor conditional structure even when defined). Strictly speaking, even the WITH-guard build is not bit-identical to the current `cluster5-pr-tu-isolated` (92f5ae72) build. The Probe B guard-with-ENABLE-defined build serves as Probe B's own baseline; only the WITHOUT-ENABLE-defined build measures total-IDEA-port-absence.

Per pythia 281 #4 + my own 20:10:14Z framing: this is a degenerate probe (un-takes the patch entirely). Useful for "IDEA-port-presence-vs-absence" question; does NOT discriminate WHICH part of the IDEA-port causes regression.

### Pre-flight gates

Same as Probe A (P1-P4) plus:
(P5) Build matrix: 2 builds required — `-DENABLE_VOLATILE_TYPE_TRACKING` (Probe B baseline) + un-defined (Probe B test). Doubles build time vs Probe A.

### PHASE 1 codegen-diff (~10min)

Compare 3-way:
1. Current TU (92f5ae72) vs Probe-B-baseline (with ENABLE defined): expect IDENTICAL bytes (the ifdef-guard structure is preprocessor-only when defined).
2. Probe-B-baseline vs Probe-B-test (without ENABLE defined): expect DIFFER (4 lines of code removed).

If (1) shows DIFFER, the guard structure shifted bytes even when defined → invalidates Probe B as a clean falsifier.

### PHASE 2 bench (only if codegen sequence above passes)

ARM yield_from reps=5 on Probe-B-test build (without ENABLE defined).

### Outcome interpretation (per gatekeeper REV3 R5-band ±0.02)

Compare ARM yield_from on Probe-B-test:
- TU-baseline (cluster5-pr-tu-isolated 92f5ae72): 0.90x
- Control (no IDEA-port; cinderx-main 28a57df8): 0.95x

Probe B outcomes:
- yield_from ≈ 0.95x ± 0.02 (≥ 0.93x): total IDEA-port removal recovers yield_from to control; IDEA-port AS A WHOLE causes the regression. Ship-as-is is empirically the wrong choice; need different IDEA implementation.
- yield_from ≈ 0.90x ± 0.02 (≤ 0.92x): IDEA-port removal does NOT recover yield_from; regression is orthogonal to IDEA-port (substrate effect, ARM-codegen artifact, control-vs-port substrate-axis difference, etc.). Ship-as-is is empirically defensible on yield_from grounds.
- 0.92-0.93x: defer-to-supervisor mid-band per gatekeeper REV3.

### Scope-limits

- Probe B only tests "IDEA-port-as-a-whole-presence-vs-absence" axis, not which specific mech contributes.
- ARM-LTO=OFF substrate ≠ x86-LTO=ON ship substrate; Probe B outcome does NOT directly answer x86 ship-config behavior.
- Caveat per librarian 20:46:28Z + own 20:10:14Z self-flag: ifdef-guard is a degenerate test. If outcome is "no recovery," it does NOT mean mech #3 is real; it means whatever causes the regression survives total IDEA-port absence (which most likely means it's NOT IDEA-port-attributable at all).

### Time-cost

~80-100min (doubles bench cycle vs Probe A: 2 builds + 2 PHASE-1 verifies + 1 PHASE-2 bench).

---

## Recommendation order if alexie picks "try one more"

Probe A first (~50-70min, single substrate, single bench, discriminates within-TU-inlined-bytes contribution). Probe B second (~80-100min, degenerate but orthogonal answer to "is IDEA-port the cause at all").

Both probes inherit the structural-untestability concern: at any LTO substrate, the C++ inline keyword + LTO interactions make source-shape probes structurally limited for mech #3 attribution. Heavyweight intrusive instrumentation in the JIT is the next-level falsifier; both probes are cheap-but-bounded last attempts before that.

## Theologian standby for outcome

When result lands per probe, theologian executes v6 IDEA-spec amendment via worktree pattern. v6 framing must include (per supervisor 01:41:47Z (4)):
- ARM-LTO=OFF probe substrate ≠ x86-LTO=ON ship substrate (documented PR body section, not chat caveat)
- Probe-A or Probe-B outcome explicitly framed with scope-limits

Per umbrella rule 4 symmetric-rigor: outcome interpretation must avoid the "mech #3 confirmed/falsified" caveat-strip pattern that fired earlier today.
