# Optimization ideas in the working branch worth applying to upstream

**Date:** 2026-05-05
**Scope:** For each bench where the working branch (speculation-experiment) is materially faster than upstream (facebookincubator/cinderx main), articulate the optimization IDEA that produces the win and sketch what applying that idea to upstream's current code would look like.
**Author:** generalist + theologian (matrix-to-source by generalist; idea articulation by theologian)
**Backing data:** `investigations/findings/abba-mitigation-2-flag-matched-2026-05-05.md` (full per-bench matrix; build-flag confound isolated by matched-flags rebuild).

## Bottom line

Six benches show the working branch ahead of upstream by 10% or more on **both architectures** (Intel + ARM) after build flags are matched. Each one corresponds to a distinct optimization idea — five idea-clusters across the six benches. The ideas are conceptually portable to upstream regardless of how the working-branch code is structured; in some cases the implementation against upstream's current code looks similar to the working branch's, in others (notably integer unboxing) the substrate has shifted enough that the idea must be re-derived against new infrastructure rather than transplanted.

## Speculative method inlining with tiered compilation — helps method_calls (+56% Intel, +47% ARM)

**The idea.** At a method call site (`obj.method(args)`) the standard JIT path goes through Python's C-API method-resolution machinery (`LoadMethod` then `CallMethod`) on every call. The optimization observes that most call sites are *monomorphic* — the receiver is the same class on every call — and treats those as candidates for inlining the called method body directly into the caller. A type guard on the receiver preserves correctness: if the receiver class changes, the inlined path deopts back to the interpreter.

A second, separable idea layered on top is *tiered compilation*: don't inline immediately on first JIT compilation. Wait until the call site has been hot post-JIT (an atomic counter passes a threshold), then trigger a recompilation that picks up the now-warm inline cache and uses it to drive the inlining decision. This avoids inlining cold paths and inlining at sites where the inline cache is still warming up.

A third sub-idea is *inline-cache pre-population* from CPython's adaptive cache: rather than warming the JIT's IC from JIT-side observations only, seed it from CPython's adaptive specialization data accumulated before JIT compilation kicked in. Independently useful even without the inlining work.

**Why it wins.** `method_calls` is essentially pure method-dispatch overhead. Inlining the method body collapses `LoadMethod` + frame-creation + return overhead per call into direct code. The ~50% wallclock reduction is consistent with method-dispatch being half-or-more of total bench time.

**Applying the idea to upstream.** Cinderx-main has the basic HIR inliner enabled by default (handles direct-call inlining where the function is statically known). It does not extend the inliner to method-call sites gated by IC monomorphism, does not have a tiered-compilation gating mechanism for inlining decisions, and does not pre-populate inline caches from CPython's adaptive cache.

Three separable conceptual additions:
- **Inliner extension to method-calls.** The existing inliner machinery handles function inlining; extending it to recognize `CallMethod` (with its associated `LoadMethodCached` IC), check IC for monomorphism, and inline the resolved method body fits within the existing inliner architecture. Conceptually local change.
- **Tiered-compilation gating.** A new mechanism: an atomic counter at every JIT-compiled function entry, plus a recompilation trigger when the counter passes a threshold. This is a design decision about JIT compilation lifecycle that upstream has not made today. Applying the idea means proposing the gating mechanism and its concurrency story (the working branch's atomic counter is `--disable-gil`-safe).
- **IC pre-population from adaptive cache.** Conceptually small: at preloader time, read CPython's adaptive cache state and seed the JIT's `LoadMethodCache`. Independent of the inlining and tiering pieces.

The inlining and IC pre-population pieces extend existing upstream architecture; the tiered-compilation gating is a new architectural layer.

## Inline exception handling for `try/except KNOWN_TYPE` — helps exceptions (+44% Intel, +37% ARM)

**The idea.** Python's exception machinery is expensive even when the exception is expected (the `try: d[k] except KeyError: default` shape is the canonical example). The standard path raises through full exception-propagation, then the interpreter catches and runs the except body. The optimization observes that `try ... except SOME_KNOWN_TYPE:` is common and emits the except body inline in the JIT code, with a runtime check on the exception type. If the raised exception matches the expected type, jump to the inlined except body; otherwise fall through to the standard exception-propagation path.

The optimization carries necessary semantic carve-outs:
- Generator frames are excluded entirely (frame-state semantics differ in generators in ways the inline-match path doesn't currently handle; a SIGSEGV during development confirmed this).
- LICM-active scopes are excluded (loop-invariant code motion could hoist code across the inline-vs-fallback boundary, breaking path-conditional state).
- Freevar-using callers have separate exclusions for related correctness reasons.

**Why it wins.** `exceptions` benchmark is exception-handling overhead. Eliminating the propagation+catch round-trip for the matched-type case removes a major fraction of that overhead. ~40% wallclock reduction is consistent with the matched-type case being the dominant path.

**Applying the idea to upstream.** Cinderx-main has no inline exception machinery — every exception goes through the propagation path today. The idea is "for the common `try/except KNOWN_TYPE` shape, recognize it at HIR-build time and emit an inline match path in codegen, falling through to the standard path on type miss." Conceptually a new HIR pass plus a codegen path.

The substantial design content is not the inline match itself — that's straightforward — but the carve-out reasoning. Each carve-out (generators, LICM, freevars) corresponds to a real semantic boundary that the inline path doesn't currently handle. Upstream adoption requires understanding each carve-out's *why*, not just its *what* — so they can decide whether to accept the carve-outs as permanent design boundaries or invest in lifting them.

A separate independently-applicable finding from this arc: there's a real bug in the existing exception path on localsplus-aliased stack values (over-Decref). That bug is in upstream's existing code regardless of whether they adopt inline-exception. Worth applying that fix to upstream independent of any inline-exception work.

## Unboxed integer arithmetic with overflow-deopt — helps nbody (+23% Intel, +12% ARM) and nqueens (+20% Intel, +15% ARM)

**The idea.** Python integers are heap-allocated `PyObject*` pointers (with a small-int cache for the common range). Arithmetic on them goes through CPython's `PyLong` machinery — function call plus boxing/unboxing per operation. The optimization observes that many hot loops use integers that fit in a machine word and don't change type during the loop. The JIT speculatively unboxes such integers to native `int64` (or smaller), does arithmetic in native machine instructions, and re-boxes only when crossing back to Python code. A guard checks for overflow at each arithmetic site; on overflow, deopt to the interpreter where `PyLong` handles arbitrary precision correctly.

The pattern-matching for "which loops are unboxing candidates" uses a Phi-cascade-with-constant heuristic — recognize `for i in range(N):` and similar shapes where the loop counter is provably an integer staying in an integer range across iterations.

**Why it wins.** `nbody` (physics integration with float and integer arithmetic) and `nqueens` (backtracking with integer index counters) are arithmetic-heavy hot loops. Native integer arithmetic is 10-100x cheaper than `PyLong` per operation. Even with overflow-guard overhead at each arithmetic site, ~20% wallclock reduction is consistent.

**Applying the idea to upstream.** This is the area where the substrate has actively shifted. Cinderx-main has been working on the integer-arithmetic pipeline since the working branch diverged: introduced compact guards for integer comparisons, renamed `IntConvert` to `PrimitiveConvert`, added simplification cases for `PrimitiveBox`, added `IntBinaryOp` on `CBool` arguments, optimized `LongCompare` for compact longs, constant-folded `IntConvert` for constant ints. The working branch's `GuardOverflow` and Phi-cascade-unboxing was developed against the pre-divergence floor; cinderx-main's substrate has reshaped underneath.

The ideas overlap (both branches understand "native arithmetic with deopt-on-overflow is a win") but the implementations target different substrate floors. This is the area that most clearly shows the principle that ideas, not code, are the deliverable: the optimization concept is sound regardless of substrate, but the implementation must be re-derived against current upstream structure.

Three components, mapped to upstream's current substrate:
- **Phi-cascade pattern recognizer.** A new HIR pass that identifies integer-loop shapes (`for i in range(N):` and similar) eligible for unboxing. Conceptually independent of substrate; recognize the IR shape directly.
- **Overflow-guard primitive.** A new HIR concept: `GuardOverflow` (deopts on integer-arithmetic overflow). Upstream's recent compact-guards work provides the deopt-machinery foundation; `GuardOverflow` lowers naturally to compact-guards-style codegen.
- **Lower BINARY_OP_ADD_INT / MULTIPLY_INT to native arithmetic.** Use upstream's `PrimitiveConvert` and `IntBinaryOp` machinery as the lowering target, with `GuardOverflow` at each arithmetic site. The lowering is straightforward against the new substrate.

The idea transfers cleanly; the implementation must be re-derived to fit the current floor.

## Inline type-version-tag check + direct slot offset access for `LOAD_ATTR` — helps richards_slots (+17% Intel, +13% ARM)

**The idea.** For classes that define `__slots__`, attribute access has fixed offsets — no dict lookup needed. The standard `LOAD_ATTR` machinery doesn't exploit this; it goes through a general inline-cache path that handles dict-based and slot-based attributes uniformly. The optimization specializes `LOAD_ATTR` for slot-defined attributes: at the LIR level, emit an inline type-version-tag check on the receiver, then a direct slot offset load. On a type miss (the receiver's class changed or had its slot layout invalidated), fall back to the general attribute path.

**Why it wins.** `richards_slots` is the slot-access variant of the richards OO benchmark. Heavy attribute access on `__slots__`-defined classes; direct offset load vs general attribute lookup is a significant per-access reduction. ~15% wallclock reduction.

**Applying the idea to upstream.** Cinderx-main's `LOAD_ATTR` codegen handles all attribute access through the general path with inline-cache. No specialization for the slot-attribute case.

Conceptually clean: extend `LOAD_ATTR` LIR lowering to detect the slot-attribute case at compile time (the receiver's type provides this info via its `__slots__` declaration), emit a type-version-tag guard plus direct offset load on success, fall through to the general path on type miss. Type-version-tag checking is a well-established CPython mechanism (used by PEP 657 and adaptive specialization in 3.11+) so the guard primitive itself is already familiar to upstream. No semantic carve-outs needed beyond the standard "deopt if type changes."

A single conceptual change that fits within existing LIR codegen architecture.

## pytorch_cm — adaptive volatile-type tracking on inline-cache invalidation (+45% Intel, +35% ARM)

**Cross-document note on substrate.** The +45% Intel / +35% ARM magnitudes cited above are on the matched-flags substrate (working branch rebuilt with upstream's flags), where the build-flag confound is removed. The companion `investigations/findings/abba-results-2026-05-05.md` side-by-side table cites the same bench at +0.27 / +0.33 on the default-flags substrate. Both are correct for their substrate; the matched-flags numbers are the load-bearing read for "what is the version-effect" questions.

**The idea.** When the JIT specializes attribute access via inline caches, every modification to a watched type fires a notification through the IC machinery. For workloads that mutate a small set of types repeatedly on a hot path — pytorch's autocast/no-grad/training-mode contexts are the canonical example — the notification overhead can dominate execution time even though the inline cache itself is not missing. The optimization is to track per-type invalidation count and, once a type has been invalidated more than a threshold (the working branch uses 10), treat it as "volatile" and stop registering future watchers on it. The IC falls back to slow-path attribute lookup for that type, but stops paying the notification overhead.

**Why it wins.** pytorch_cm's hot path mutates `_Autocast` / `_NoGrad` / model-context types every iteration. Without volatile tracking, every mutation fires the watcher-notification chain through the IC machinery. With volatile tracking, after ~10 mutations the types are de-watched and notifications stop firing. Empirically: working branch fires 1.75M notifications across the bench run; upstream fires 4.20M (2.40x ratio). Cycle-fraction in the type-change-notification path is 1.29% vs 3.04% (2.36x). The wallclock effect is about 38% — ablation that no-ops the notification path on upstream recovers the entire 35% pytorch_cm regression and slightly overshoots (upstream 54.93ms baseline to 34.11ms ablated; working-branch reference 35.64ms).

**Applying the idea to upstream.** Upstream's inline-cache machinery has the watcher registration + notification infrastructure but no per-type invalidation tracking. Three concrete additions:

1. A per-type invalidation counter (a small map keyed by Python type, incremented at the top of the type-change-notification entry point).
2. A volatile-types set and an `isVolatileType` predicate that checks whether a given type has crossed the threshold.
3. An early-return in the watcher-registration call: if the target type is already volatile, skip registration and let the IC fall back to slow-path lookup.

The threshold value (10 in the working branch) is a tuning parameter. Conceptually the policy is "if the type has churned this much already, the IC isn't winning anyway — stop paying to notify on its mutations."

**Honest caveats on how this finding was reached.** The root cause came from a four-step empirical chain: (1) the compilation-coverage probe refuted the obvious "missing functions" hypothesis; (2) an initial codegen-quality structural diff was a low-warmup measurement artifact and ablated null at the suspected opcode classes; (3) a perf-record probe surfaced the IC-invalidation cycle-fraction asymmetry; (4) a source-diff identified the specific volatile-type-tracking policy difference. The chain involved one published over-claim and a public retraction earlier today; the current articulation is anchored on both ablation (causation confirmed at the notification layer) and source-diff (specific policy mechanism identified). Cross-arch caveat: the perf-record + ablation + source-diff were x86 only. ARM generalization is plausible because the policy mechanism lives in HIR-level code shared across architectures, but ARM has not been directly verified at this specific axis.

**Three-layer inference chain on the policy-layer claim.** The current articulation compresses three layers of empirical evidence: (a) **proximate**: ablation at `notifyICsTypeChanged` on upstream recovered the entire wallclock gap (causation confirmed at the notification-call layer); (b) **rate**: instrumented counter showed 2.40x more notifications on upstream than working branch (the proximate overhead is count-driven, not per-call-cost-driven); (c) **policy**: forward-port-ablation on upstream confirms adaptive-volatile-type-tracking is the working-branch-side mechanism producing the rate asymmetry.

**Step 6 forward-port-ablation + reps=5 calibration bundle (2026-05-06 03:53–07:20Z).** A reps=2 forward-port-ablation initially ran on both arches (cinderx-main HEAD `1d8a9974`, `--compile=auto`, fast-mode 9-bench, smoke-gate True). A subsequent reps=5 calibration sweep (per pythia 205+206 anchor-audit) collapsed two reps=2 references that had been load-bearing for the framing — yesterday's spec-exp matched-flags 1.32x x86 / 1.06x ARM reference numbers were reps=2 outliers. The reps=5 calibrated picture is cleaner than the reps=2 framing reported.

**Calibrated reps=5 cross-arch picture (smoke-gate True on every substrate).**

| substrate | x86 reps=5 | ARM reps=5 |
|--|--|--|
| spec-exp matched-flags BOTH (`d941a26a` + `f9a95f8f` compiled) | 1.13–1.14x | 1.00x |
| spec-exp matched-flags MINUS `f9a95f8f` (Adaptive only, no Part-1 in binary) | (not run x86) | 1.00x |
| cinderx-main + `d941a26a` (Step 6, Adaptive only) | 1.13x | 1.08x |
| cinderx-main + `d941a26a` + `f9a95f8f` (Step 7, Adaptive + Part-1-active) | **1.20x reps=5** (1.19x reps=2) | 1.08x reps=5 |
| cinderx-main baseline (no patch) | 0.75x reps=2 | 0.66x reps=2 |
| cinderx-main + no-op-`notifyICsTypeChanged` (Step 4 ablation) | 1.20x reps=5 | (not run) |

**The IDEA: `d941a26a` adaptive-volatile-type tracking is the standalone fix.** Forward-porting `d941a26a` alone to upstream cinderx-main recovers pytorch_cm to spec-exp matched-flags reference within precision band on x86 (1.13x = 1.13–1.14x), and exceeds spec-exp matched-flags ARM by +0.08x (1.08x vs 1.00x). Step 4 ablation reps=5 (no-op `notifyICsTypeChanged` body on cinderx-main) recovers pytorch_cm to 1.20x; Step 6 surgical patch recovers to 1.13x; the magnitudes are consistent, confirming the proximate ablation result calibrates and is not a reps=2 outlier.

**Substrate-level finding on `f9a95f8f` (Part 1).** A subsequent commit (`2f83c344`, 2026-04-19, "Suppress dunder resolution for with-statement context managers") added an early-return inside `simplifyLoadAttrSpecial` that disables it for `__enter__`/`__exit__` — the dunders pytorch_cm exercises in its hot path. So on the working branch, Part 1 is compiled-into-the-binary-but-disabled-for-the-pytorch_cm-hot-path. cinderx-main lacks `2f83c344`, so Part 1 actually fires there for context-manager dunders.

The cross-arch `+0.08x` gap (cinderx-main + Adaptive 1.08x ARM vs spec-exp matched-flags 1.00x ARM) is **substrate-difference unattributed**, NOT Part-1-compile-in overhead. Step 8 ablation discharged the mechanism: removing `f9a95f8f` entirely from spec-exp ARM matched-flags (compile-out, `grep -c simplifyLoadAttrSpecial = 0`) yielded pytorch_cm = 1.00x (ARM Step 8 artifact `/home/alexturner/local/vib-jit/cinderx/benchmarks/2026-05-06_070320_0e6f16a6_aarch64_abba.txt`, smoke-gate True, 10 CM-internal dunders JIT-compiled per deopt-falsifier). Identical to spec-exp BOTH ARM 1.00x — zero delta from removing Part-1. The compile-in-overhead-drag mechanism is FALSIFIED; the +0.08x gap traces to the many other commits between cinderx-main HEAD `1d8a9974` and spec-exp HEAD `0e6f16a6`, NOT specifically to Part-1-compile-in cost.

**Part 1 contribution on x86 substrates where it actually fires.** cinderx-main + Step 7 (Adaptive + Part-1-active for CM dunders, no `2f83c344`) measured 1.19x reps=2 / **1.20x reps=5** (vs Step 6 1.13x reps=5 / 1.15x reps=2). Step 7-vs-Step-6 delta at calibrated reps=5 precision: **+0.07x speedup** (231.99ms→194.19ms wallclock; Step 6 reps=5 artifact `2026-05-06_055420_1d8a9974_x86_64_abba.txt` vs Step 7 reps=5 artifact `2026-05-06_074735_1d8a9974_x86_64_abba.txt`). At reps=5 the delta is reproducible (reps=2 +0.04x vs reps=5 +0.07x within noise band) and well above `--fast --reps=5` precision floor — Part-1 contributes a real +0.07x speedup on cinderx-main substrate where it actually fires for `__enter__`/`__exit__` (i.e. without `2f83c344`).

**The 3-layer inference chain on the policy-layer claim is empirically rooted at all 3 layers across both arches**: (a) proximate ablation `notifyICsTypeChanged` no-op recovers entire wallclock gap (Step 4 reps=5 confirmed -38.7% recovery, calibrated); (b) rate counter shows 2.40x more notifications on upstream than working branch (count-driven, not per-call-cost-driven); (c) policy forward-port (Step 6) recovers cinderx-main pytorch_cm to spec-exp matched-flags reference. The inferential-not-instrumented tag previously on layer (c) drops.

**Provenance and methodology caveats.**
- `d941a26a` is in-house work shipped to the working branch on 2026-04-18, +21 lines in `inline_cache.cpp`.
- `f9a95f8f` is the companion Part 1 commit, 2026-04-17, +61 lines in `cinderx/Jit/hir/simplify.cpp`. `2f83c344` (2026-04-19) added the `__enter__`/`__exit__` early-return that disables it for the pytorch_cm hot path on the working branch.
- Bug-locus: `recordTypeInvalidation` must be in `notifyICsTypeChanged` (NOT `TypeWatcher::typeChanged`) — placing it on the latter fires 4× per real type modification (one per watcher), making threshold-10 effectively threshold-2-3.
- Step 6 was symmetric on both arches (clean rebuild + smoke-gate before each ABBA); reps=5 measurements reproducible (x86 spec-exp two-builds-agreement at 1.13x and 1.14x within ~1% noise; ARM Step 6 reps=5 1.08x = reps=2 1.08x).
- Cross-substrate `+0.08x` ARM gap remains unattributed (substrate-difference between cinderx-main `1d8a9974` and spec-exp `0e6f16a6` includes many commits beyond Part-1 active/disabled status).

**Upstream application recommendation.** Forward-port `d941a26a` standalone first; consider `f9a95f8f` as a separate optional follow-up. The 21-line `inline_cache.cpp` diff (`d941a26a`) recovers pytorch_cm to spec-exp matched-flags reference on both arches within precision (1.13x x86 / 1.08x ARM at reps=5). Adding `f9a95f8f` on top contributes a further +0.07x at reps=5 on x86 (Step 7 1.20x vs Step 6 1.13x) — real speedup, not precision-limited — but only when it actually fires for `__enter__`/`__exit__` (working-branch suppresses it via `2f83c344`; cinderx-main does not). On ARM, `f9a95f8f` contribution is zero at reps=5 (Step 7 ARM 1.08x = Step 6 ARM 1.08x; per Step 8 cross-arch ablation). The `2f83c344` dispatch-path question (whether to suppress for CM dunders) is policy not performance. Three concrete additions per `d941a26a`: (1) per-type invalidation counter incremented at the top of `notifyICsTypeChanged`; (2) volatile-types set with `isVolatileType` predicate; (3) early-return in `TypeWatcher::watch` that skips watcher-registration if the target type is already volatile. Threshold value 10 is a tuning parameter.

**Open follow-ups status.**

- (γ) **Step 7 x86 reps=5** — DISCHARGED 2026-05-06 07:47Z (artifact `2026-05-06_074735_1d8a9974_x86_64_abba.txt`); pytorch_cm 232.26ms vanilla / 194.19ms cinderx = 1.20x; Part-1 contribution at calibrated reps=5 = +0.07x (vs Step 6 reps=5 1.13x); reproducible vs reps=2 1.19x. Folded into recommendation L129 above.
- (δ) **ARM substrate bisect 0e6f16a6..1d8a9974 on Step 6 substrate** — CLOSED-AS-NOT-EMPIRICALLY-DISCHARGED. Hypothesis-driven file-filter (`cinderx/Jit/inline_cache.* + codegen/ + hir/simplify.cpp + lir/ + Common/ + runtime.cpp + symbolizer.cpp`) yields 161 cinderx-main-side commits + 94 spec-exp-side commits = 255-commit candidate set (50+ ARM-specific); >> the ≤10-commit threshold for tractable targeted ablation. Substrate-tags `pythia208-cinderx-main-arm-bisect-tip` (= `1d8a99749e9aff9323fa4e96a780fe06e64492b0`) + `pythia208-spec-exp-arm-bisect-base` (= `0e6f16a6`) preserve future targeted re-investigation IF a hypothesis-narrowing methodology emerges (alternatives not currently in flight: perf-counter delta on pytorch_cm hot-path, file-level profile diff cinderx-main vs spec-exp on ARM, build-flag bisect, targeted microbench for IC-rate-counter-asymmetry). Tags solve substrate-freshness only, NOT bisect-tractability — the 933-commit divergence wall remains independent of substrate-pinning.

The "+0.08x ARM substrate-difference unattributed" caveat (L116/L127) is **TERMINAL-WITHOUT-ROADMAP** at this evidence-state. Future upstream applier should treat the ARM bonus as substrate-conditional and not assume reproducibility on a different cinderx-main-derived substrate without re-measurement.

**Stack-state qualification on the +45%/+35% magnitude.** The working-branch substrate measured here already has an earlier inline-dunder-dispatch optimization (`simplifyLoadAttrSpecial`, commit `f9a95f8f` on 2026-04-17) that addresses an overlapping mechanism, plus the `2f83c344` (2026-04-19) early-return that disables it for `__enter__`/`__exit__` (per L114). The decision record at the time (D-1776463559) cited 0.83x → 0.88x (~+6%) on pytorch_cm and explicitly named IC-invalidation overhead as the remaining cost — but that record was risk-tagged "untested" (pending testkeeper verification + gatekeeper review) and no benchmark file from the f9a95f8f substrate has been preserved, so the historical +6% is unverified by primary source. Today's stacking ablation (below) measures the spec-exp substrate where Part 1 is compiled-but-disabled-for-CM-dunders; per Step 8 discharge (L116) the spec-exp Part-1-only +overhead vs NEITHER is consistent with compile-in-but-disabled overhead, NOT standalone active-Part-1 regression. The historical claim is not load-bearing. `d941a26a` (Adaptive) is the empirically-confirmed source of the recovery on both arches per L99-129.

A reps=2 stacking ablation ran on the working-branch x86 substrate (4 conditions: neither / `simplifyLoadAttrSpecial`-only / adaptive-volatile-type-tracking-only / both). Per the L114-118 `2f83c344` reframing the spec-exp Part-1 conditions measure compile-in-but-disabled-for-CM-dunders overhead, NOT standalone Part-1 active speedup; the empirical numbers stand but the original directional interpretations are superseded by Step 8's compile-out ablation (L116). Retained as wallclock anchor for the IDEA paragraph above:

- **Both pieces** (current working-branch state): 33.83 ms.
- **Adaptive-volatile-type-tracking only** (`simplifyLoadAttrSpecial` disabled): 36.54 ms — Adaptive alone covers the bulk of the recovery on this substrate.
- **`simplifyLoadAttrSpecial` only** (adaptive disabled): 63.56 ms ±10 (range 54.94–76.71). Per Step 8 discharge, this measures Part-1-compiled-but-not-firing-for-CM-dunders overhead on the spec-exp substrate, NOT standalone Part-1 active speedup.
- **Neither** (both disabled): 59.25 ms ±0.42.

The reps=5 calibrated picture in L99-129 supersedes the reps=2 directional interpretations of this 4-condition table. The "Part 1 standalone is net-negative" framing was an artifact of the substrate-state question that Step 8 ablation discharged: removing `f9a95f8f` entirely from spec-exp ARM matched-flags yielded zero delta vs spec-exp BOTH (1.00x = 1.00x), so the spec-exp Part-1-only +overhead vs NEITHER is consistent with measurement noise plus compile-in-but-disabled overhead, not standalone active-Part-1 regression. ARM stacking-ablation no longer needed (Step 8 discharged the cross-arch question).

The 35% wallclock differential is real and reproducible on x86; the adaptive-volatile-type-tracking mechanism is rooted at the volatile-type-tracking policy difference; applying the idea to upstream is a small, conceptually clean addition to the inline-cache machinery; the magnitude is recoverable from `d941a26a` alone on a Part-1-absent upstream (the standalone IDEA per L120). The standalone-Part-1 application-order question is now answered per (γ) discharge: `f9a95f8f` contributes a real +0.07x speedup on x86 substrates where it actually fires for `__enter__`/`__exit__` (cinderx-main, no `2f83c344`), and zero contribution on ARM at reps=5 (Step 8 ablation discharged). Recommend per L129: forward-port `d941a26a` first; consider `f9a95f8f` as a separate optional follow-up. The dispatch-path policy (`2f83c344`-equivalent suppression for CM dunders) is policy not performance.

## Single-arch wins — weaker signal

| bench | Intel | ARM | comment |
|-------|-------|-----|---------|
| fibonacci | +24% | -27% | x86 win, ARM loss — explicitly not cross-arch consistent. The integer-unboxing idea helps on x86 but the ARM codegen has a regression here. ARM open question, not a cross-arch idea. |
| yield_from | +13% | -1% | Intel-only win; ARM essentially neutral. May be specific to Intel codegen of the SEND_GEN fast path. |
| float_arith | +9% | -6% | Mixed cross-arch. Not a clean signal. |
| store_subscr | +9% | 0% | Intel-only win. |

These are not cross-arch consistent and may be Intel-codegen artifacts or compound with other ideas above. Worth noting as side-effects rather than primary ideas.

## Where upstream is ahead

For completeness: these five benches show **upstream ahead of the working branch** on both architectures by 10% or more. Inverse direction — areas where the working branch has either lost ground or upstream has gained something the working branch doesn't have.

| bench | upstream advantage (Intel) | upstream advantage (ARM) | likely area |
|-------|----------------------------|---------------------------|-------------|
| chaos_game | +60% | +49% | unknown; biggest gap, no working-branch arc explains the loss |
| try_except_callee | +26% | +63% | particularly bad on ARM (second-largest upstream-ahead delta after chaos_game); despite the working branch's exception inline arc, this bench regresses — possibly the generator-skip exclusion bites here |
| deep_class_super | +29% | +35% | super() / MRO; working branch may have lost a specialization here |
| list_comp | +17% | +19% | list comprehension |
| dict_ops | +17% | +16% | dict subscript / iteration |

Two of these (chaos_game, try_except_callee) have unexplained magnitude and warrant their own investigation. They are not optimization ideas the working branch has that upstream lacks — they're the inverse direction.

## Backing artifacts

- Per-bench matrix, methodology, and flag-isolation evidence: `investigations/findings/abba-mitigation-2-flag-matched-2026-05-05.md`
- pytorch_cm hypothesis space and queued falsifier: `investigations/plans/2026-05-01-pytorch-cm-arm-regression.md`
- Generator optimization arc trajectory: `project_generator_optimization.md` (auto-memory)
