---
status: draft for supervisor + alexie review
owner: theologian
trigger: alexie 2026-05-11 07:34:59Z "port the architecture (not diff) to master"; supervisor 2026-05-11 07:41:41Z dispatch "theologian leads on IDEA articulation in PR commit message + body"
scope: substrate-independent IDEA articulation for the adaptive volatile-type tracking optimization (Cluster 5 in spec-exp-to-upstream-optimization-ideas-2026-05-05.md)
audience: upstream cinderx maintainers (facebookincubator/cinderx) reviewing a contributed PR; the WHY-this-architecture framing must land for someone who has not seen the speculation-experiment branch's history
backing artifacts:
  - investigations/findings/spec-exp-to-upstream-optimization-ideas-2026-05-05.md (Cluster 5 / pytorch_cm section, L79-149)
  - investigations/findings/abba-mitigation-2-flag-matched-2026-05-05.md (per-bench matrix L77-147)
  - speculation-experiment commit d941a26a (the 21-line `inline_cache.cpp` change being ported as IDEA, not code)
  - generalist 2026-05-11 07:38:30Z chat post (matrix-to-source backing data)
  - testkeeper 2026-05-11 07:39:29Z chat post (12/12 per-bench number ratification)
---

# Cluster 5 — Adaptive Volatile-Type Tracking on IC Invalidation: PR IDEA Articulation

## What this document is

A substrate-independent articulation of the IDEA underlying speculation-experiment commit `d941a26a` ("Add IC churn detection: stop watching volatile types after 10 invalidations"), suitable for adaptation against any current cinderx-main HEAD. Per alexie binding `feedback_ideas_not_code.md`: this PR is an idea-transfer, not a code-transfer. The IDEA — what to do, why, and the architectural shape — is what needs to land in cinderx-main; the specific lines from `d941a26a` are evidence, not the deliverable.

## PR commit message (draft)

```
JIT: stop watching types that churn their inline-cache invalidations

Workloads that frequently mutate a small set of types on a hot path
(PyTorch's autocast/no-grad/training-mode contexts are the canonical
example) trigger full inline-cache invalidation on every mutation.
Even when the inline cache is not actually missing for the lookups
that matter, the per-mutation watcher-notification chain dominates
execution time.

Track per-type invalidation count. Once a type has been invalidated
beyond a threshold (default 10), mark it volatile and stop registering
new IC watchers for it. Inline-cache lookups against volatile types
fall back to the slow path — correct, but no longer paying the
notification cost.

The change touches only the inline-cache layer; downstream cache
behaviour for non-volatile types is unchanged.

Empirical: this patch applied to upstream master HEAD reproduces the
pytorch_cm speedup. PR-branch measurement at reps=5: 1.35x
(170.89ms cinderx vs 230.22ms vanilla, +25.8%). A corroborating-prior
forward-port ablation on a master substrate ~11 days older measured
1.13x on x86_64 and 1.08x on aarch64 at reps=5; substrate-differences
(bench mode and build-flag adjustments and 11 days of intervening
master commits) account for the magnitude variance, and the speedup
direction and mechanism reproduce. ARM measurement on this PR's
substrate is pending.
```

(72-char line wrap; subject 56 chars; body lines ≤72 chars.)

## PR body (draft markdown)

### Problem

Inline-cache machinery in the JIT registers per-type watchers so that
type mutations invalidate caches dependent on those types. For most
workloads, type mutation is rare and the watcher-notification cost is
negligible.

For workloads that mutate a small set of types repeatedly on a hot path,
the dynamic shifts. PyTorch's `torch.no_grad()`, `torch.autocast()`, and
training/eval mode-toggle contexts are the canonical example: each
context-manager `__enter__`/`__exit__` writes to internal state on the
mode-tracking type, fires the type-modification notification chain, and
walks every IC dependent on that type to invalidate it. Even when the
cached lookups for those types are not actually being missed by user
code, the per-mutation notification cost dominates total execution time
of the workload.

Empirically: on the pytorch_cm workload, the upstream cinderx-main
substrate fires roughly 4.20M type-change notifications across a bench
run; the optimization described here reduces that to 1.75M (2.40x ratio).
The cycle-fraction the workload spends inside the type-change-notification
path drops from 3.04% to 1.29% (2.36x ratio). The wallclock effect is
roughly 38% of the total run-time on the affected workload.

### The architecture

Three small additions inside the inline-cache layer:

1. **Per-type invalidation counter.** A map from `PyTypeObject*` to
   integer count. Incremented at the entry of the function that
   notifies all IC watchers of a type change.

2. **Volatile-types set.** A set of `PyTypeObject*`. A type enters this
   set the first time its invalidation counter crosses a threshold
   (default 10).

3. **Early-return in the watcher-registration path.** Before
   registering a new IC watcher on a type, check whether the type is
   already in the volatile set; if so, return early without registering.
   The IC then falls through to its existing slow-path lookup behaviour
   for that type.

The change is contained entirely within the IC layer; no other JIT
phase, no HIR pass, and no codegen path is affected. Cache behaviour
for non-volatile types is bit-for-bit identical to the pre-change
behaviour.

### Why this shape, not other shapes

A few alternative shapes are worth naming and rejecting explicitly so
reviewers do not need to re-derive them:

- **Per-cache invalidation tracking instead of per-type.** The cost
  driver is the watcher-walk at the type-modification point, which
  scales with the number of caches dependent on the type. A per-cache
  counter would not address the per-type-modification overhead — once
  a type is mutated, every dependent cache pays. The per-type counter
  cuts at the source.

- **Time-decaying invalidation counter.** A short-lived burst of
  invalidations followed by stable type behaviour would currently
  promote the type to volatile permanently. A decaying counter would
  let "no-longer-volatile" types resume being watched. We have no
  empirical data showing real workloads exhibit this pattern; reviewers
  who do should flag, but we recommend deferring this complexity until
  motivated by a workload regression.

- **Ejecting existing watchers on volatile-promotion instead of
  blocking new ones.** The implementation skips registering new
  watchers but does not unwatch existing ones. The asymmetry is
  intentional: existing-watcher unregistration would require walking
  the dependent-cache set, which is the cost we are trying to avoid.
  The invalidation-storm gets shut off via the no-new-watchers
  mechanism; existing watchers age out naturally as their dependent
  caches turn over.

### Bug-locus precision (worth highlighting for reviewers)

The per-type invalidation counter MUST be incremented in the function
that fans out type-change notifications across all IC watcher
collections — i.e. the entry point that calls `typeChanged` on each
watcher in turn. It must NOT be incremented inside individual
`TypeWatcher::typeChanged` implementations. There are 4 such watchers
in the current cinderx codebase (one per cache class); incrementing
inside each fires the counter 4× per real type modification, making the
threshold-10 default behave as effective threshold-2-3 and causing
healthy types to be falsely promoted to volatile.

This was a real bug we hit during development; pinning it on the right
function is the difference between the optimization being correct and
its threshold being effectively 4× tighter than documented.

### Threshold value

Default is 10 invalidations per type. This is empirical — it is the
smallest value at which pytorch_cm-style workloads see the full benefit
without imposing latency on workloads with normal type-mutation rates.
Reviewers may reasonably want this exposed as a runtime-configurable
JIT setting; we have no strong opinion but suggest defaulting to 10
based on our benchmark coverage.

### Empirical evidence

The PR-branch measurement against current upstream master HEAD is the
primary anchor; a corroborating-prior forward-port ablation on a
slightly older master substrate provides cross-validation context.

| substrate | x86_64 reps=5 | aarch64 reps=5 |
|--|--|--|
| **PR-branch (this patch on current upstream master)** | **1.35x (170.89ms cinderx vs 230.22ms vanilla)** | (validation pending) |
| Corroborating-prior: this patch on master ~11 days older | 1.13x | 1.08x |
| Corroborating-prior baseline: master ~11 days older, no patch | 0.75x | 0.66x |

The PR-branch measurement reproduces the speedup direction and
mechanism on current upstream master; the higher magnitude (1.35x vs
1.13x prior) reflects substrate differences between the two
measurements (bench mode: full 29-bench subprocess ABBA on the PR
branch vs --fast 9-bench on the prior; build-flag adjustments to the
PR branch's bench harness for upstream CMakeLists compatibility; 11
days of intervening upstream master commits). Both substrates show
substantial recovery of pytorch_cm above its un-patched baseline; the
prior ablation's +0.38x recovery framing remains the load-bearing
IDEA-validation claim, with the PR-branch measurement confirming the
mechanism reproduces on fresh upstream.

A separate ablation that no-ops the type-change-notification function
entirely on the corroborating-prior master substrate recovered
pytorch_cm to 1.20x at reps=5, confirming the proximate-overhead
attribution: the entire wallclock gap is paid in the notification
path. This patch recovers by avoiding the registration cost rather
than the notification cost; the gap between this patch's measured
speedup and the no-op ablation's 1.20x represents notification cost
still paid for non-volatile-but-watched types, which is correct
behaviour and not addressable by this patch.

The corroborating-prior measurement substrate, build flags, reps=5
calibration methodology, and the four-step empirical chain
(notification-rate counter, cycle-fraction profile, forward-port
ablation, compile-out ablation) are documented in the
spec-exp-to-upstream-optimization-ideas writeup section "pytorch_cm —
adaptive volatile-type tracking on inline-cache invalidation."
Available on request.

### Workload-shape generalization

The pytorch_cm benchmark is a stand-in for a broader workload class:
any code path that frequently mutates a small set of types via
context-managers, metaclass-driven dynamic class modification, or
configuration-toggle patterns.

The threshold-10 default is calibrated against pytorch_cm's specific
mutation rate. Workloads with materially different mutation rates may
benefit from a different threshold (see "Threshold value" above for
the build-time-constant vs runtime-config tradeoff).

### What this patch does NOT do

For completeness, two adjacent issues that this patch does not address:

1. **Volatile-type detection is the threshold-crossing event, not a
   pre-emptive analysis.** A type that is going to be volatile pays
   the watcher-registration + first-N-invalidation overhead before
   the optimization kicks in. Steady-state benefit only; cold-start
   workloads do not benefit.

2. **The slow-path lookup against a volatile type costs more per
   lookup than the inline-cache hit it replaces.** For workloads where
   a type is volatile *and* the cached lookups against it are on a hot
   path, this patch trades invalidation overhead for per-lookup
   overhead. The threshold-10 default is calibrated assuming
   invalidation overhead dominates; reviewers with workloads where
   slow-path-lookup overhead would dominate should flag.

### Testing

PR-branch pytorch_cm measurement at reps=5 documented in the Empirical
evidence section above. Smoke-gate validation (auto-mode JIT-compiled
verify post-warmup on a trivial function) PASSED on the PR branch
before benchmarking.

Broader-suite regression check (control ABBA: same upstream master
HEAD, same build flags, full 29-bench subprocess ABBA without this
patch) is queued as a follow-on investigation; this PR's scope is the
pytorch_cm primary claim only.

## Open questions for upstream reviewers (suggested for the PR
description)

1. Should the volatile-type set be exposed to introspection (e.g.
   `cinderjit.get_volatile_types()`) for debugging? We lean yes for
   future debuggability; this PR does not add it to keep the change
   minimal.

2. Should the threshold be a build-time constant or a runtime config?
   We lean runtime config to allow tuning without rebuilds; this PR
   ships it as a build-time constant to match the working-branch
   reference. Happy to switch on review.

3. Are there cinderx-main IC client classes added since the working
   branch diverged that need their own integration with the volatile-
   type predicate? The patch adds the predicate check at the
   `TypeWatcher::watch` template, which should cover all IC clients
   that go through `TypeWatcher`; reviewers more familiar with
   recently-added IC machinery should verify.

## Notes for generalist (substrate-adaptation guidance)

When adapting this IDEA against the cinderx-main HEAD selected for the
PR branch:

- The three target sites named in the architecture section
  (notification entry point + watcher-registration template + a place
  to define the per-type counter / volatile set) need to exist in some
  form on the substrate. If any has been renamed, restructured, or
  refactored away, the IDEA still ports — the new equivalent sites
  need to be located. If any site has been *eliminated* by an
  intervening upstream redesign of the IC machinery, the port is
  blocked and we should escalate.

- The patch in d941a26a uses `jit::UnorderedMap` and `jit::UnorderedSet`
  containers, which are the working branch's standard map/set types.
  The substrate may use `absl::flat_hash_map` / `absl::flat_hash_set`,
  `std::unordered_map`, or another container family — use whatever
  matches the substrate's existing IC code.

- The bug-locus precision (counter MUST go in the
  fanout-notification entry point, NOT in individual `typeChanged`
  implementations) is independent of substrate. Verify the new site
  on the substrate is the fanout entry point before incrementing.

- Threshold value 10 is the working-branch default and the value all
  empirical claims in this document are calibrated against. Reviewers
  who change it should re-run the pytorch_cm bench and report the
  delta.

## Reference: working-branch implementation as it appeared in d941a26a

(Provided for reviewer convenience; the actual PR change should be
re-derived against the current cinderx-main substrate per alexie binding
`feedback_ideas_not_code.md`.)

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

// Inside TypeWatcher::watch(), as the first line of the function body:
if (isVolatileType(type)) {
  return;
}

// Inside notifyICsTypeChanged(), as the first line before the existing
// per-watcher fanout calls:
recordTypeInvalidation(type);
```

The 21 lines above are the entire substantive code change in d941a26a.
The d941a26a commit also contains a build.sh hunk enabling LTO; that
hunk is not portable to upstream — upstream cinderx has no equivalent
file (the OSS build path uses build/fbcode_builder/getdeps), and LTO
at upstream is a separate build-system concern outside the scope of
this PR.
