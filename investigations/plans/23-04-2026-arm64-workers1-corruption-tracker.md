# ARM64 test_jit_preload workers=1 + no-lazy corruption — tracker

**Status:** DEFERRED (separate workstream from resolve_target_descr lazy-imports warm-up fix)

**Empirical:** test_jit_preload SIGABRT on ARM64 with `-X jit-batch-compile-workers=1 -X jit-all` regardless of lazy-imports config (testkeeper config matrix 21:25Z, config D: workers=1 + jit-all + no-lazy = double-free + SIGABRT). Workers>=2 + no-lazy = PASS (only safe combo).

**Hypothesis (INFERENTIAL per pass-semantics rule):** workers=1 takes serial compile_units_preloaded path (pyjit.cpp:1095-1097); each unit's makeCompiledFunction inline-finalizes immediately (context.cpp:446-462). Workers>=2 buffers in completed_compiles_ + finalize-all via finalizeMultiThreadedCompile. Inline-finalize during the workers=1 loop may install vectorcall + invalidate state subsequent units' compile reads. Different ordering vs workers>=2.

**Pre-impl gate:** mechanism positive site pin needed. Source-read or ASan platform010-clang Path A both viable (per testkeeper 21:27Z + librarian 21:32Z).

**Cross-references:**
- testkeeper 21:25Z 5-config matrix
- theologian 21:24Z + 21:28Z source-read on workers=1 vs workers>=2 path differential (context.cpp:446-462 + finalizeMultiThreadedCompile)
- supervisor 21:28Z + 21:57Z deferral past lazy-imports fix
- Recursive-policy-collapse (memory feedback_recursive_policy_collapse_pattern.md): tracker artifact required for deferred workstream
