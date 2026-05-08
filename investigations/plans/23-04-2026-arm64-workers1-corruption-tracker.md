# ARM64 test_jit_preload deferred mechanisms — tracker

**Status:** DEFERRED (2 confirmed mechanisms; additional sub-mechanisms possible if configs A vs B prove distinct under future heap-instrumentation. Defensive-depth Option B shipped 01a373f2; ASan/Valgrind tooling all blocked on devgpu004 ARM64.)

**Mechanism-count framing note (pythia 51 #3 reconciliation, 2026-04-23T23:29:36Z):** supervisor's earlier "≥3 distinct" framing (D-1776984045) was conservative-upper-bound; tracker confirms 2 mechanisms empirically. Configs A (4 workers + lazy + jit-all) and B (1 worker + lazy + jit-all) both produce OverflowError but may turn out to be distinct sub-mechanisms once heap-instrumentation works on ARM64.

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

**2026-05-08 update — cross-arch + ASan probe (generalist 10:01:20Z directive):**

- **Cross-arch.** OverflowError reproduces on x86_64 (Meta-Python 3.12.13+meta) with `python -X jit-all -L -c "re.compile(complex_pattern)"`. Trigger isolated to combination `-X jit-all + -L`; either alone is OK. Closes "may-be-ARM64-specific" gate above. Bug is platform-portable.
- **ASan probe.** Repro run under `LD_PRELOAD=/usr/lib/clang/21/lib/x86_64-redhat-linux-gnu/libclang_rt.asan.so` + `scratch/build-asan/_cinderx.so` (ASan-instrumented build of cinderx). ASan canary verified functional in same env (catches synthetic heap-buffer-overflow). Repro under ASan: only OverflowError fires; **no ASan diagnostics**. Per supervisor 10:01:20Z framework: "ASan clean → OverflowError isn't heap-corruption (different hypothesis needed)."
- **Inspection of `re._parser.SubPattern.data` at the moment of overflow** (monkey-patched `getwidth`): data is **structurally normal** — `[(ANY, None)]` (inner SubPattern, len=1) and outer with len=13 of well-formed `(op, av)` tuples (LITERAL/MAX_REPEAT/SUBPATTERN/IN/etc., no oversized ints, all values consistent with vanilla re._parser output). The OverflowError fires on `for op, av in self.data:` despite normal data — i.e., during list iteration / tuple unpacking, NOT on access of any specific element value.
- **Updated hypothesis (INFERENTIAL).** Bug is in cinderx JIT specialization of list iteration / tuple unpacking under lazy-imports, not in module-load or class-resolution lazy-import path. The specialized iteration produces an interpretation step that overflows ssize_t conversion despite the underlying object being a normal Python list of normal Python tuples. Possible specific paths: SEND_ITER / FOR_ITER specialization on tuple-unpack, or LOAD_FAST_AND_CLEAR on the loop-var tuple. Pre-impl gate now: HIR-dump on this hot path under `-X jit-all -L` + bisect specialization opcodes.
- **Status note.** Mechanism class still test_jit_preload-blocking; Option B (commit 01a373f2) remains defensive-depth-only as previously framed. Bug-hunt next step is HIR-dump + specialized-opcode bisect, not heap-corruption deep-dive.

**Cross-references:**
- testkeeper 22:39:52Z 5-config matrix post-Option-B
- testkeeper 22:43:27Z + 22:44:43Z all-ARM64-heap-check-tools-blocked summary
- theologian 22:35:31Z idempotency principle (LOAD_GLOBAL pattern uses idempotent PyDict_GetItem; ResolveContainer is non-idempotent)
- supervisor 22:45:14Z defer endorsement
- 01a373f2 defensive-depth commit (honest "DOES NOT close test" framing)
- generalist 09:55:50Z + 10:01:20Z + 10:13Z 2026-05-08 cross-arch + ASan-probe + data-inspection findings (this section update)
- supervisor 10:01:20Z directive accepting (a) ASan probe and authorizing tracker update regardless of outcome

**2026-05-08 update — HIR-dump narrowing (generalist 10:13Z under supervisor 10:09:01Z directive):**

HIR-dump captured at `investigations/findings/test_jit_preload_overflow_hir_2026-05-08.txt` (2.2MB, 54701 lines, full final-HIR for the repro run).

**Key HIR section: re._parser:SubPattern.getwidth bb 2-40** (the for-loop body at L183 `for op, av in self.data:`).

Pipeline shape:
- v230 = GetIter v758 (where v758 = self.data, a list)
- v254 = InvokeIterNext v230 (per-iteration)
- bb 4: CondBranchCheckType<TupleExact, fast/slow> v254
- bb 39 (TupleExact path): v257 = LoadFieldAddress v254 +24 (inline ob_item for tuple)
- bb 38 (ListExact path): v258 = LoadField<ob_item@24, CPtr, borrowed> v254 (heap items pointer)
- bb 36: Phi(v258, v257) → v264; v260 = LoadVarObjectSize v254; PrimitiveCompare<Equal> v260 with CInt64[2]
- bb 40 (size==2 path): LoadArrayItem v264 [1] = v265 (av), LoadArrayItem v264 [0] = v267 (op)
- bb 35 (else): Deopt 'UNPACK_SEQUENCE' GuiltyReg v254

The specialized unpack path is structurally correct for both TupleExact and ListExact 2-tuples and would deopt cleanly on shape mismatch.

**Refined hypothesis (still INFERENTIAL per pass-semantics rule):** OverflowError likely originates in `InvokeIterNext` (v254) for the LIST iterator over self.data, NOT in the tuple-unpack itself. Suspect: cinderx JIT specialized list-iterator state (`it_index` field, Py_ssize_t) is being corrupted by a prior recursive `getwidth` call that has MAX_REPEAT entries with `av[1] = MAXREPEAT = 4294967295` (verified in inspected SubPattern.data, e.g. `(MAX_REPEAT, (0, MAXREPEAT, [...]))`). Under lazy-imports, the int constant 4294967295 may be specialized/cached in a way that leaks into the list-iterator's it_index slot, causing the next-iteration increment to compute it_index+1 and overflow ssize_t.

**Next-step candidates** (deeper bisect; deferred per supervisor 10:13:09Z archive+park):
1. LIR-dump on `InvokeIterNext v254` register sequence to confirm `it_index` tracking and check for leak from recursive frame.
2. Repro-isolation: try patterns that include MAXREPEAT-equivalent constants without the full coding_re structure (narrow what triggers the leak).
3. Audit cinderx JIT list-iterator specialization code for int-overflow on it_index increment, especially under lazy-import binding context.

**Status note (2026-05-08):** Phase 1 substantive defect — investigated to specific HIR hypothesis (InvokeIterNext + list-iterator it_index leak under lazy-import binding); deeper bisect deferred per supervisor 10:13:09Z. Cross-arch repro confirmed (no longer ARM64-specific). HIR artifact preserved in findings/ for future bisect.

## Baseline-recollect risk: Option B in baseline-ABBA HEAD

**Status:** OPEN follow-up (pythia 51 #2, 2026-04-23T23:12:08Z). Filed per supervisor 23:12:51Z synthesizer-pattern commitment + recursive-policy-collapse rule.

**Risk:** Baseline ABBA at HEAD 01a373f2 (in flight 22:49Z, ETA ~24:04-24:19Z) absorbs Option B's `resolve_target_descr` PyImport_GetModule warm-up overhead into the regression-floor. Option B is empirically defensive-depth — DOES NOT close test_jit_preload; addresses module-load lazy-import side-effect class only. Future optimization deltas measured against this baseline include never-validated defensive runtime cost.

**Mitigation rule:** if Option B is later reverted (e.g., proper class/method-resolution fix replaces it, or Option B proves load-bearing for an unrelated path → kept), baseline MUST be recollected BEFORE next ABBA cycle that consumes the baseline as regression-floor. Cite this entry in the revert/replacement commit message; gatekeeper BLOCK any post-revert ABBA that uses pre-revert baseline.

**Cross-references:**
- pythia 51 (2026-04-23T23:12:08Z) #2 second-order risk
- supervisor 23:12:51Z synthesizer-pattern response (mitigation commitment)
- librarian 23:27:59Z recursive-policy-collapse fire (chat-only deferral collapse → artifact required)
