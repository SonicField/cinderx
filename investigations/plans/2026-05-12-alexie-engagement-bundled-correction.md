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
