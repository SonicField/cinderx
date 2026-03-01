# Session Summary — CinderX Deopt Investigation (nn_module_forward / pytorch_cm)

**Date:** 1 March 2026, ~19:37-20:49 UTC
**Participants:** supervisor, generalist, theologian, testkeeper, gatekeeper, scribe, fixup, pythia
**Machine:** devgpu004 (aarch64, Grace Hopper GB200)
**Commit base:** 1fa46c9b (aarch64-jit-generators branch)

---

## Terminal Goal

Explain nn_module_forward at 0.72x and pytorch_cm at 0.69x. Find a path to 1.25x for both benchmarks.

## Outcome

**Two confirmed root causes identified. Three-part fix plan agreed. No code changes shipped — session was diagnostic.**

---

## Root Cause A — Polymorphic Receiver (CONFIRMED EMPIRICALLY)

Layer.__init__() is called polymorphically: 75% with self as type Layer, 25% with self as type Network (subclass). The JIT emits GuardType<Layer:Exact> which fails on every Network call.

Evidence:
- Monomorphic test (only Layer instances): NO deopts
- Polymorphic test (Layer + Network subclass): DEOPTS after 1000 guard failures then detach
- Stash test on clean 1fa46c9b: deopts present (pre-existing, not caused by CALL spec changes)

## Root Cause B — Version Tag Not Assigned (UNFALSIFIED HYPOTHESIS)

simplifyLoadAttrSplitDict silently skipped due to Ci_Type_HasValidVersionTag() read-only check in threaded compilation. If locally-defined classes never had their version tag assigned by CPython (lazy assignment), the check fails and split dict optimisation is entirely skipped.

Evidence:
- Warmed HIR dump shows GuardType<Layer:Exact> present but LoadAttrCached (generic) instead of LoadField (direct offset)
- simplifyLoadAttrSplitDict did NOT fire despite exact type guard being satisfied
- Theologian identified 4 preconditions in simplifyLoadAttrInstanceReceiver (simplify.cpp:1446-1466); version tag check is prime suspect

## CALL Specialisation — REJECTED

The CALL_PY_EXACT_ARGS specialisation from 27 Feb session was formally rejected:
- Caused kwargs_dispatch regression: 0.98x to 0.77x
- Caused additional deopts on _GeneratorContextManager.__exit__
- Did NOT cause the core Layer deopts (those are pre-existing)
- Uncommitted changes must be reverted on devgpu004

## Inliner Investigation

- PYTHONJITENABLEHIRINLINER was UNSET on devgpu004
- When enabled: inliner active but NOT firing for targets (Tier 2 threshold)
- Network.forward() gets ~500-1000 calls, at or below kTier2ThresholdDefault=1000
- Test contaminated by CALL spec deopts — needs clean rerun with high n_iter
- Alex directive: all optimisations must be ON by default, env vars only disable

## Agreed Fix Plan

1. Fix A: Subtype/isinstance guard for polymorphic callsites (preserve exact-type guards for monomorphic cases)
2. Fix B: Eagerly assign version tags before JIT compilation (thread-safe, at type-registration time)
3. Inlining test: With A+B fixed, high-n_iter benchmark to trigger Tier 2

## Statistical Significance Gate

Implemented (scripts/significance_gate.py, 280 lines):
- Sign test: 13/15 same-sign deltas (p = 0.0074)
- Minimum effect size: 2%
- Bootstrap 95% CI (10,000 resamples)
- Self-tested: A=A control fails gate, 2.0x effect passes, power at 2% = 99.3%

## Outstanding Items

1. Fix A implementation — subtype guard for polymorphic callsites
2. Fix B verification — confirm threaded compilation ON and Layer lacks valid version tag
3. Fix B implementation — eager version tag assignment
4. Clean inlining test — after A+B, high-n_iter with auto()
5. CALL spec revert — uncommitted changes on devgpu004
6. Statistical gate integration — into benchmark_cinderx.py
7. Inliner default-on code change
8. CinderX doc rebase in nbs-framework
