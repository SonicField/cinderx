# ARM64 test_jit_preload deferred mechanisms — tracker

**Status:** DEFERRED (two related mechanisms; defensive-depth Option B shipped 01a373f2; ASan/Valgrind tooling all blocked on devgpu004 ARM64)

## Mechanism 1: workers=1 + no-lazy corruption

**Empirical:** test_jit_preload SIGABRT on ARM64 with `-X jit-batch-compile-workers=1 -X jit-all` regardless of lazy-imports config (testkeeper config matrix 21:25Z, config D: workers=1 + jit-all + no-lazy = double-free + SIGABRT). Workers>=2 + no-lazy = PASS (only safe combo).

**Hypothesis (INFERENTIAL per pass-semantics rule):** workers=1 takes serial compile_units_preloaded path (pyjit.cpp:1095-1097); each unit's makeCompiledFunction inline-finalizes immediately (context.cpp:446-462). Workers>=2 buffers in completed_compiles_ + finalize-all via finalizeMultiThreadedCompile. Inline-finalize during the workers=1 loop may install vectorcall + invalidate state subsequent units' compile reads. Different ordering vs workers>=2.

**Pre-impl gate:** mechanism positive site pin needed. Source-read or ASan platform010-clang Path A both viable (per testkeeper 21:27Z + librarian 21:32Z).

**Cross-references:**
- testkeeper 21:25Z 5-config matrix
- theologian 21:24Z + 21:28Z source-read on workers=1 vs workers>=2 path differential (context.cpp:446-462 + finalizeMultiThreadedCompile)
- supervisor 21:28Z + 21:57Z deferral past lazy-imports fix
- Recursive-policy-collapse (memory feedback_recursive_policy_collapse_pattern.md): tracker artifact required for deferred workstream

## Mechanism 2: lazy-imports + jit-all OverflowError (configs A + B post-Option-B fix)

**Status:** DEFERRED (Option B narrow PyImport_GetModule warm-up shipped 01a373f2 as defensive-depth; addresses module-load lazy-import side-effect class but DOES NOT close test_jit_preload)

**Empirical:** post-Option-B 5-config matrix (testkeeper 22:39:52Z): config A (4 workers + lazy + jit-all) + config B (1 worker + lazy + jit-all) both still produce OverflowError in re._parser. Configs C/E PASS, config D SIGABRT (Mechanism 1).

**Hypothesis (INFERENTIAL per pass-semantics rule):** root cause is in CLASS/METHOD-resolution lazy-import path (NOT module-load path which Option B addresses). Option A's broader `_PyClassLoader_ResolveContainer` warm-up regressed config C → SIGABRT (non-idempotent helper); narrow Option B preserves safety on C but doesn't reach class/method-resolution lazy-import side-effects.

**Pre-impl gate:** mechanism positive site pin requires heap-instrumentation (ASan/Valgrind). All current options blocked on devgpu004 ARM64 (clang/gcc/valgrind all unavailable per testkeeper 22:43:27Z + 22:44:43Z). Cross-validation on x86_64 with ASan possible IF corruption reproduces (may be ARM64-specific).

**Cross-references:**
- testkeeper 22:39:52Z 5-config matrix post-Option-B
- testkeeper 22:43:27Z + 22:44:43Z all-ARM64-heap-check-tools-blocked summary
- theologian 22:35:31Z idempotency principle (LOAD_GLOBAL pattern uses idempotent PyDict_GetItem; ResolveContainer is non-idempotent)
- supervisor 22:45:14Z defer endorsement
- 01a373f2 defensive-depth commit (honest "DOES NOT close test" framing)

## Baseline-recollect risk: Option B in baseline-ABBA HEAD

**Status:** OPEN follow-up (pythia 51 #2, 2026-04-23T23:12:08Z). Filed per supervisor 23:12:51Z synthesizer-pattern commitment + recursive-policy-collapse rule.

**Risk:** Baseline ABBA at HEAD 01a373f2 (in flight 22:49Z, ETA ~24:04-24:19Z) absorbs Option B's `resolve_target_descr` PyImport_GetModule warm-up overhead into the regression-floor. Option B is empirically defensive-depth — DOES NOT close test_jit_preload; addresses module-load lazy-import side-effect class only. Future optimization deltas measured against this baseline include never-validated defensive runtime cost.

**Mitigation rule:** if Option B is later reverted (e.g., proper class/method-resolution fix replaces it, or Option B proves load-bearing for an unrelated path → kept), baseline MUST be recollected BEFORE next ABBA cycle that consumes the baseline as regression-floor. Cite this entry in the revert/replacement commit message; gatekeeper BLOCK any post-revert ABBA that uses pre-revert baseline.

**Cross-references:**
- pythia 51 (2026-04-23T23:12:08Z) #2 second-order risk
- supervisor 23:12:51Z synthesizer-pattern response (mitigation commitment)
- librarian 23:27:59Z recursive-policy-collapse fire (chat-only deferral collapse → artifact required)
