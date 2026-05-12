---
status: pre-staged for alexie engagement OR 06:00 UTC trigger
owner: supervisor
trigger: pythia 280 risk-2 (bundled-correction owed to alexie at engagement was chat-only deferral; pre-stage as artifact per project_recursive_policy_collapse_pattern.md 0/3 chat-only survival)
audience: alexie at next engagement on cluster5-pr ship decision
---

# Bundled correction text for alexie at next engagement

## What this document is

Pre-staged plain-English text supervisor will post to alexie when she next engages on the cluster5-pr ship-or-fix decision (or at 06:00 UTC trigger if engagement does not arrive first). Pre-staged per pythia 280 risk-2 to avoid real-time reconstruction under the conditions chat-discipline umbrella was codified to prevent.

## Bundled correction (plain-English text — paste as-is to alexie)

Three updates from where we left off in my 22:42:08Z post:

### 1. Cross-arch substrate decoupling (pythia 278 caveat I owed you)

Earlier I told you "10% ARM / 3% x86" on yield_from. That collapsed an important subtlety. The ship configurations differ on the LTO axis — x86 ships LTO-ON by default, ARM ships LTO-OFF per the workbook stability note. Under matched LTO=OFF probe, x86 yield_from was 0.95x and ARM 0.90x — a 0.05x cross-arch gap. But under ship-config asymmetry (x86 LTO-ON 1.05x vs ARM LTO-OFF 0.90x), the cross-arch user-experience gap is 0.15x — three times the matched-probe gap. The substrate is doing real work; "10% ARM / 3% x86" isn't wrong but it understates how different the two arches' user experience would be on shipped binaries.

### 2. Inline-shim probe re-targeted to ARM (pythia 280 substrate-correction)

We had pre-staged a follow-up probe (move the 5 retained shim lines into a header to test whether they carry residual mech-#3 effect). Initial spec had it on x86-LTO=ON, but at LTO=ON the wrapper inlines trivially → bit-identical codegen → measures the build system not the mechanism. Re-targeted to ARM-LTO=OFF where the wrapper does NOT inline trivially AND the residual is larger (better signal-to-noise). ~50-70 min via devgpu004.

### 3. Updated 5-option menu (replaces my earlier 3-option framing)

1. Ship as-is (cluster5-pr 0c99ac89, no source-file split): 1 cross-arch yield_from regression (~10% ARM / ~3% x86), pytorch_cm +45% gain. Strict zero-regression bar not met.
2. Ship with TU-split (cluster5-pr-tu-isolated 92f5ae72): partial mitigation on yield_from (~17-25% gap recovery cross-arch); 4 x86-only regressions also strongly mitigated; pytorch_cm preserved. Strict zero-regression still not met but smaller residual.
3. Don't ship: trade-off not worth it; investigate alternative architectures or skip Cluster 5.
4. Wait for ARM-LTO=OFF inline-shim probe outcome (~50-70 min): if it shrinks the residual further, ship-with-tu-shim becomes a 4th option; if it doesn't, options 1-3 are the empirically-clean menu.
5. Ship with TU-split AND restrict the patch to x86-LTO-ON conditional: extreme — patch only compiles in for x86 builds with LTO. Avoids ARM regression but defeats cross-arch IDEA goal. Probably a non-starter unless ARM cost is the only blocker.

### What we still don't know

The dominant ~75-83% of the yield_from regression is mechanism-unidentified after caveat-#2 + always-paid + within-TU-mech-#3 (14-line slice) all falsified or partially-discharged. ARM-LTO=OFF inline-shim probe is the cheapest remaining attempt to identify whether the retained 5-line shim contributes; if it doesn't, we have no named mechanism to investigate and the residual stays "unknown" on the PR record.

## Provenance + risk-tracking

- pythia 278 risk-1 (substrate-decoupling) → addressed in section 1
- pythia 280 risk-3 (substrate-selection on inline-shim probe) → addressed in section 2 + dispatch re-shape
- pythia 280 risk-2 (bundled-correction chat-only deferral) → THIS ARTIFACT
- pythia 280 risk-4 (probe-as-discharged-investigation framing) → addressed in section 3 (option 4 keeps the probe live as gating, not closed)
- 06:00 UTC trigger from supervisor 23:50:43Z stands; this artifact serves both engagement-arrival path AND trigger-fire path.

## Amendment 2026-05-12 ~09:47Z (post-trigger updates)

Trigger fired at 06:00 UTC. Bundled-correction posted to chat 06:01:23Z (chat surface). This artifact append-only updates per librarian 09:46:25Z amender-fan-out backstop:

### (a) Substrate-decoupling caveat applies to option 1 framing

Section 3 option 1 reads "~10% ARM / ~3% x86" without the substrate-decoupling caveat that section 1 establishes. Correct option 1 framing: x86-LTO-ON ship 1.05x, ARM-LTO-OFF ship 0.90x, cross-arch user-experience gap 0.15x. The substrate is doing real work; per-arch numbers in isolation understate user-facing cross-arch divergence.

### (b) Menu reduced to 3 options post-trigger empirical (replaces 5-option menu in section 3)

Probe outcomes since trigger:
- ARM-LTO=OFF inline-shim probe (06:07Z): codegen IDENTICAL → SKIP bench. C++ `inline` keyword inlines trivially regardless of LTO, structurally untestable on this substrate.
- Probe A noinline-attr pre-flight (07:12Z): codegen DIFFERS → bench-eligible at first pass.
- Hot-region reachability probe (09:19Z perf-record on cluster5-pr 0c99ac89, yield_from): IDEA-port functions (notifyICsTypeChanged / recordTypeInvalidation / isVolatileType / TypeWatcher::watch) all 0% in yield_from hot path. Probes A + B both DROPPED — codegen-DIFFERS but the differences land in code paths yield_from doesn't execute.

Reduced menu (replaces section 3 menu options 4 + 5):
- Option 1 (ship as-is) per (a) above with substrate-decoupling caveat
- Option 2 (ship with TU-split) unchanged from section 3 — partial mitigation already shown
- Option 3 (don't ship) unchanged
- Option 4 (wait for ARM probe) DROPPED — probe done, no signal
- Option 5 (LTO-restrict) DROPPED — extreme + defeats cross-arch IDEA goal

### (c) Mech-attribution status (replaces "What we still don't know")

Per pythia 285 + theologian 09:44Z self-flag, prior framing ("residual is empirically code-size/cache-effect, source-untestable") was inferential exclusion promoted to positive identification. Honest framing:

- Perf-record on yield_from hot path EXCLUDES IDEA-port direct execution (0% on the 4 IDEA-port functions). This excludes the mechanism family "the new code we added is firing on the hot path."
- It does NOT positively identify the residual mechanism. Live alternative hypotheses still untested:
  - Code-size / cache-line / branch-predictor effects from the 21 lines being present anywhere in the binary
  - Indirect mechanism via the 24%-of-cycles notifyDictUpdate path (different cinderx function, may interact with IDEA-port via shared state)
  - Other mechanisms not enumerated
- Per pythia 285 #3, perf-record was on yield_from only; pytorch_cm not perf-recorded → exclusion does NOT generalize to all benchmarks. pytorch_cm perf-record is the cheap remaining gap (~5-10min).
- Heavyweight discharge path: intrusive JIT instrumentation targeting notifyDictUpdate / jitgen_am_send. Out of cheap-probe budget.

The residual mechanism is unidentified; canonical PR-record framing must NOT promote "we excluded direct execution" to "we identified the cause."

## Provenance — Amendment

- librarian 09:46:25Z 3-axis stale flag → addressed in (a)+(b)+(c)
- pythia 285 #1 inferential-exclusion-promotion → reframed in (c)
- pythia 285 #3 single-bench generalization gap → noted in (c); pytorch_cm perf-record dispatched 09:43Z
- gatekeeper 09:21:10Z caveat-strip catch → addressed in (a)
- supervisor 09:21:46Z chat-side correction; this amendment is the durable-record companion

