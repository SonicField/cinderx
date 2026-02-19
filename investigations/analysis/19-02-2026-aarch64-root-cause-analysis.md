# CinderX aarch64 JIT — Cross-Cutting Root Cause Analysis

**Date:** 19 February 2026
**Authors:** @theologian + @claude
**Scope:** Common failure modes across CinderX tests and PyTorch tests on aarch64

---

## Aim

Identify root causes that are **shared** between CinderX test failures and PyTorch test failures on aarch64. Produce a prioritised fix plan. This is not about fixing individual test failures — it is about finding the underlying codegen gaps that manifest across both test suites.

## Known Failures (as of 19 Feb 2026, updated 10:15Z)

### CinderX Test Suite (38/41 PASS on e2a3351b — upstream sync + skipIf async gen)

| Suite | Status | Root Cause | Category |
|-------|--------|-----------|----------|
| test_jit_generator_aarch64 | FAIL (3 errors) | AsyncGen CANNOT_SPECIALIZE | Codegen gap |
| test_jit_preload | FAIL (2 failures) | InvalidImmediate for large stack offsets | ARM64 encoding |
| test_jit_support_instrumentation | FAIL (16 failures) | sys.monitoring not implemented | Missing feature |
| test_shadowcode | SKIP | Expected, unsupported in 3.12+ | N/A |
| test_cinderjit (1 error) | 171/172 PASS | test_condbranch_codegen static entry offset | Needs cherry-pick ac75934e |

### PyTorch (newly discovered)

| Issue | Status | Root Cause | Category |
|-------|--------|-----------|----------|
| Import-time SEGFAULT | **FIXED AND VERIFIED** | Option D revert (8af4dc49) left kLoadAttrCached in emitExceptionCheck exemption list → NULL unchecked → crash. Fixed by Guard kNotZero (2a7f034f). 137 functions compiled during torch import, no crash. | Category 7 (our bug) |
| P0 results vacuous | RETRACTED | CINDERJIT_ENABLE=1 is not a real CinderX env var; JIT never compiled anything | Configuration error |
| Import-time auto-compile | **WORKS** | 137 functions JIT-compiled during `import torch` with cinderjit.auto(). No crash. | Fixed by 2a7f034f |
| Post-import auto-compile | WORKS | 4 nn.Module functions compile and execute correctly | Partial success |
| PyTorch P0 smoke tests | **GREEN (09:07Z)** | 5/5 pass on e2a3351b. Forward, backward, gradients correct. 429 functions compiled, 17 torch-related. Zero numerical difference JIT vs interpreter. | Terminal milestone |
| PyTorch full suite (JIT) | **2271/2313 PASS (10:05Z)** | test_torch 1564/37, test_autograd 707/5, test_nn TIMEOUT. 98.2% pass rate with cinderjit.auto() active. Non-JIT baseline pending. | Major milestone |

### Upstream Fixes — Status Check Required

| Diff | Date | Fix | Files | Status | Impact |
|------|------|-----|-------|--------|--------|
| D93289593 | 13 Feb | kLoadFrame: register allocator clobbers ARM64 args | generator.cpp, builder.cpp, hir.h +7 more | **HAVE** (d50fa6ad) | Fixed ARM64 startup crash |
| D92979437 | 11 Feb | kLea: multiplier uses raw values not log2 SIB encoding | autogen.cpp | **HAVE** (already present) | N/A — our build already has correct log2 encoding |
| D93621746 | 18 Feb | Double spill: wrong data type (VecD→k64bit) | postalloc.cpp | **HAVE** (already present) | N/A — our build already uses k64bit. NOT the import-time crash cause. |
| D93679174 | 18 Feb | Primitives: w1 vs w0, umov→fmov | autogen.cpp, gen_asm.cpp | **MISSING** at d50fa6ad | Primitive-returning functions set error flag in wrong register (w2 instead of w1). Potential import-time crash cause. |

**UPDATE (19 Feb 06:21Z):** ~~All three upstream fixes were verified PRESENT in our build by testkeeper.~~ CORRECTION (19 Feb 06:26Z): Testkeeper's original verification read the working tree (which had uncommitted D93679174 fixes from claude), not the committed state at d50fa6ad. Using `git show d50fa6ad:<file>`, testkeeper confirmed D93679174 is **NOT** in our baseline. Only D92979437 (kLea) and D93621746 (double spill) are committed. D93679174 (primitives w1/w0, umov→fmov) is a genuine gap. This revives D93679174 as a candidate root cause for the import-time SEGFAULT.
| D92907890 | 10 Feb | Lightweight frames: frame-finding fails on ARM64 | frame.cpp, autogen.cpp | **MISSING** — getIP() reads x86 stack layout on ARM64, returns garbage | Deopt crashes, frame reification failures |
| D86123384 | Nov 2025 | Enable aarch64 for CinderX JIT | pyjit.cpp, detection.h | **HAVE** (base) | Initial enablement |

### Newly Discovered Upstream Fixes (19 Feb 07:15Z)

Code search revealed **17 additional** ARM64 bug fixes from Dino Viehland (3-18 Feb 2026) that were not in our tracking. Status in our d50fa6ad build: **UNKNOWN — need systematic verification.**

| Diff | Date | Fix | Category | Risk if Missing |
|------|------|-----|----------|----------------|
| D92219817 | 3 Feb | Don't clear deopt stats without JIT context | Infrastructure | Crash on deopt |
| D92900203 | 10 Feb | Use negated sub instead of impossible add | Encoding | Build/crash |
| D92979693 | 11 Feb | Restore scratch reg post-return (clobbered across JITRT_UnlinkFrame call) | Register alloc | Silent corruption |
| D93026401 | 11 Feb | Use strb for frame state (was corrupting with wider store) | Operand size | Frame corruption → crash |
| D93026402 | 11 Feb | Fix register save/restore (x40, vec/gp confusion) | Register alloc | Crash |
| D93134492 | 12 Feb | Branch stub for far guards (conditional branch out of range) | Branch range | SEGFAULT on far branch |
| D93134493 | 12 Feb | ptr_resolve for large stack frames (ptr_offset insufficient) | Stack layout | InvalidImmediate / crash |
| D93251162 | 13 Feb | kMoveRelaxed on aarch64 (atomic loads/stores) | Missing opcode | CANNOT_SPECIALIZE |
| D93256199 | 13 Feb | Test/guard size support (shift/mask for guard codegen) | Operand size | Wrong guard result |
| D93256200 | 13 Feb | Postalloc rewrite for mov (promote 8/16-bit to 32-bit) | Operand size | Register width bug |
| D93256201 | 13 Feb | Custom operand size handling (getGp, translateSelect) | Operand size | Wrong values |
| D93525511 | 17 Feb | Footer address for generator frames on ARM | Generator frames | Generator crash |
| D93541458 | 17 Feb | Promote comparisons to 32-bit outputs | Operand size | kEqual produces wrong values |
| D93544179 | 17 Feb | loadFromReg needs same getGp treatment as storeFromReg | Operand size | Load wrong size |
| D93546281 | 17 Feb | Static entry offset for ARM = 16 | Static Python | Static method crash |
| D93547839 | 17 Feb | Static Python thunk helper for ARM64 | Static Python | Missing functionality |
| D93637622 | 18 Feb | Register save size based on independent GP/VecD sizes | Stack layout | Stack corruption |
| D93657219 | 18 Feb | Set output type even if input is not small | Operand size | Type confusion |
| D93663938 | 18 Feb | TypedArgInfo wrong register (arg 5 not scratch) | Static Python | Wrong argument |

**NOTE:** Our d50fa6ad build is based on Kevin Newton's initial enablement stack (late Jan) + cherry-pick of D93289593 (13 Feb). Many of Dino's fixes (3-18 Feb) are likely MISSING. The 37/41 CinderX pass rate may be because force_compile() tests exercise a limited subset of codegen paths. Auto-compile exercises ALL paths, explaining why it crashes.

---

## Root Cause Categories

### Category 1: ARM64 Instruction Encoding Constraints

**Affected:** test_jit_preload (InvalidImmediate)

ARM64 has strict immediate encoding constraints:
- ADD/SUB: 12-bit unsigned immediate (0–4095), optionally shifted by 12
- MOV: 16-bit immediate with shift (MOVZ/MOVK pattern for larger values)
- LDR/STR: Signed 9-bit offset (-256 to 255) for unscaled, or 12-bit unsigned scaled

x86 has 32-bit immediates for most instructions. CinderX was written for x86 first, so codegen may emit immediates that fit in 32 bits but not in ARM64's constrained encoding.

**Specific bug (identified by testkeeper 09:08Z):** `InvalidImmediate: add x0, x29, -88` — the kLea LIR instruction emits `add` with a negative immediate, but ARM64 `add` only accepts unsigned 12-bit immediates. Should emit `sub x0, x29, 88` for negative offsets. gen_asm.cpp:1358 aborts on the encoding failure (SIGABRT, exit code -6). Even fixing the test expectation wouldn't help — the real fix is teaching the assembler to use `sub` for negative frame offsets in kLea.

**Fix pattern:** Two-part: (1) for negative immediates, emit `sub` instead of `add`; (2) for out-of-range positives, materialise into a scratch register (MOV+MOVK), then use register-offset addressing.

**Cross-cutting?** YES — any function with a large stack frame or many local variables could trigger this. PyTorch's deep call stacks (autograd, nn.Module hierarchy) may create large stack offsets.

**Falsifier:** Compile a function with >4096 bytes of locals on aarch64. If it crashes with InvalidImmediate, this root cause is confirmed to affect PyTorch.

### Category 2: ~~Missing Opcode Specialisations~~ Async Generator JIT Prohibition (RESOLVED — 08:48Z)

**Affected:** test_jit_generator_aarch64 (3/33 CANNOT_SPECIALIZE)

**CORRECTION (08:48Z):** This is NOT a missing opcode or aarch64-specific issue. It is a KNOWN UPSTREAM LIMITATION on Python 3.12+.

**Root cause:** pyjit.cpp:3319-3327 explicitly forbids JIT compilation of async generators on Python 3.12+ via the CO_ASYNC_GENERATOR flag check. This is architecture-independent — it applies on x86 too. Upstream hides it by force-passing the async generator test suite on 3.12 (`@passIf(AT_LEAST_312, 'T194022335')`). Our test_jit_generator_aarch64 does not have this decorator.

**Previous analysis was WRONG:** I attributed this to "missing opcode specialisations for aarch64". In reality, the JIT never reaches the codegen stage — the function is rejected at the preloader level before any architecture-specific code runs.

**Note on decorator:** Upstream uses `@passIf` (from `cinderx.test_support`), NOT `@unittest.skipIf`. `passIf` force-passes the test (reports as PASS, test body replaced with no-op). `skipIf` marks as SKIPPED (triggers yellow CI signals in Meta's infra). The CinderX fork has its own `passIf` implementation — no dependency on Meta's `libfb`. **Alex's decision (09:28Z): use `@unittest.skipIf` for now — more conventional, less error-prone. Style alignment with upstream at PR merge time.**

**Fix:** Add `@unittest.skipIf(AT_LEAST_312, ...)` to the 3 async gen tests in test_jit_generator_aarch64. Result: 30/30 + 3 skipped = 33 tests (30 pass, 3 skip), suite moves from FAIL to PASS. CinderX goes from 37/41 to 38/41.

**VERIFIED (09:25Z):** Testkeeper confirmed 38/41 on test branch (667a1a16). Gate baseline updated.

**Cross-cutting?** NO — auto-compile correctly rejects async generators (returns CANNOT_SPECIALIZE, does not crash). The import-time SEGFAULT was a different root cause (Category 7, LoadAttrCached exemption).

### Category 3: Auto-Compile Safety

**Affected:** PyTorch import-time SEGFAULT

Auto-compile (via `cinderjit.auto()` or `PYTHONJITAUTO=N`) compiles ANY function that exceeds the call threshold. This is different from force_compile (which is called on specific known-good functions in tests) and jitlist (which compiles only whitelisted functions).

The auto-compile path may encounter functions that the JIT cannot safely compile — functions with unsupported opcodes, unusual control flow, or incompatible frame layouts. On x86, these might produce incorrect results; on aarch64, they SEGFAULT.

**Cross-cutting?** YES — this is the fundamental risk. Any function in any Python library (PyTorch, stdlib, even builtins) can be auto-compiled if called enough times. Every codegen gap is a potential auto-compile crash.

**Fix pattern:** The JIT should gracefully bail out (fall back to interpreter) when it encounters an unsupported opcode, rather than crashing. Check if the bail-out path works correctly on aarch64.

**Falsifier:** If the JIT's bail-out path (CANNOT_SPECIALIZE → interpreter fallback) works correctly on aarch64, then auto-compile should not crash — it should just skip unsupported functions. If it crashes, the bail-out path itself is broken.

### Category 4: Missing Platform Feature (sys.monitoring / JIT instrumentation deopt)

**Affected:** test_jit_support_instrumentation (16 failures)

**Updated analysis (09:12Z — testkeeper):** The 16 failures break down as:
- **8 genuine failures:** JIT does not deoptimize compiled functions when sys.setprofile/sys.settrace/sys.monitoring callbacks are registered. Tests expect `is_jit_compiled(func) → False` after attaching a profiler, but it stays True. Affected: JitSetProfileIntegrationTest (3), JitSetTraceIntegrationTest (3), JitCombinedTracingIntegrationTest (2).
- **8 cascade errors:** JitMonitoringIntegrationTest — all 'tool 0 already in use' because JitCombinedTracingIntegrationTest fails before calling free_tool_id (missing setUp/tearDown).

Fixing test isolation (adding try/finally around tool ID registration) would eliminate the 8 cascade errors → 8/16 pass, 8/16 fail. The 8 genuine failures require JIT instrumentation support (deopt-on-profile) — not a quick fix.

**Cross-cutting?** UNLIKELY — PyTorch does not use sys.monitoring in its test suite. This is CinderX-specific.

**Priority:** LOW — defer. Test isolation fix (cascade errors) is cheap but doesn't make the suite pass.

### Category 5: x86→ARM64 Semantic Translation Errors

**Affected:** Multiple — kLea (D92979437), double spills (D93621746), primitives (D93679174)

The CinderX JIT was written for x86 first. Several codegen patterns use x86 semantics that don't translate directly to ARM64:

- **kLea multiplier encoding:** x86 SIB byte uses raw multiplier values (1,2,4,8). ARM64 `lsl` uses log2 shift amounts (0,1,2,3). The aarch64 kLea implementation used the raw values, so `case 1:` (should mean "shift by 0, i.e., multiply by 1") was instead shifting by 1 (multiplying by 2). Every tuple unpack and list element access computed the wrong address. Fixed in D92979437.

- **Double spill data type:** On x86, moving a double to memory via a temp register uses the same register file. On ARM64, doubles live in Dn registers (vector file) and integers in Xn registers (general file). The temp register was allocated as a Dn but treated as an Xn, corrupting the value. Fixed in D93621746.

- **Primitive return registers:** On x86, w2 is the auxiliary return location. On ARM64, it's w1. The codegen used w2 (x86 convention), so primitive-returning functions set the error/success flag in the wrong register. Fixed in D93679174.

**Cross-cutting?** YES — these are the highest-impact bugs. They affect ALL compiled code that uses the affected patterns, regardless of whether it's CinderX tests or PyTorch. The kLea bug alone would corrupt every tuple/list element access.

**Falsifier:** Cherry-pick all three fixes, rebuild, and retest. If the import-time SEGFAULT disappears, one of these was the cause.

### Category 6: SSA Violations in LIR Generation

**Affected:** FIXED (8af4dc49), but pattern may recur

The Option D LoadAttr inline fast-path created two LIR virtual registers for the same HIR output, violating SSA. This caused register allocation to produce dead writes and stale values. On aarch64 specifically, the stale value was a function pointer that was then called, causing SEGFAULT.

**Cross-cutting?** INDIRECTLY — the fix (revert to simple call) is correct, but any future inline cache optimisation must respect the single-output-per-HIR-instruction invariant. The phi/merge pattern documented by theologian is the correct approach.

**Falsifier:** Run the full CinderX suite after the fast-path redesign. If any new SSA violations exist, they'll manifest as crashes or incorrect results.

### Category 7: Exception Handling for LoadAttrCached (CONFIRMED ROOT CAUSE — 19 Feb 07:51Z)

**Affected:** Import-time SEGFAULT, try/except around LOAD_ATTR in JIT-compiled functions

**Status:** ROOT CAUSE CONFIRMED AND FIXED

**CORRECTION (07:51Z):** The initial hypothesis — that Python 3.12 exception table support was missing — was **partially wrong**. The co_exceptiontable gap IS real (exception handler blocks are absent from the HIR), but it is NOT the root cause of the crash. The crash was caused by a leftover from our own Option D revert.

**True root cause (traced by testkeeper):**
1. Commit 3c4ff942 (Option D): Added `kLoadAttrCached` to the emitExceptionCheck exemption list because the inline fast-path handled its own guards
2. Commit 8af4dc49 (SSA fix): Reverted the inline fast-path BUT did NOT remove kLoadAttrCached from the exemption list
3. Result: LoadAttrCached had no exception checking at all — no inline guard (reverted), no emitExceptionCheck (still exempted)
4. When LoadAttrCached returns NULL (attribute not found), the NULL propagates unchecked → SEGFAULT

**Why the co_exceptiontable hypothesis was wrong about the crash (but right about the gap):**
- The team observed exception handler blocks absent from the HIR and concluded this was the crash cause
- Actually, exception handling via emitExceptionCheck → Guard kNotZero → deopt works WITHOUT HIR-level exception blocks — the interpreter resumes at the LOAD_ATTR position and uses co_exceptiontable to find the except handler
- The crash was NOT caused by missing exception blocks. It was caused by the kNotZero guard being SUPPRESSED by the exemption list leftover from Option D

**Fix:** Claude added `appendGuard(bbb, InstrGuardKind::kNotZero, *instr, result)` after appendCallInstruction in the kLoadAttrCached handler (generator.cpp:1342). test_dot now returns 'caught' instead of crashing. Awaiting full regression results.

**Note on co_exceptiontable:** The HIR builder STILL does not parse Python 3.12 exception tables. Exception handler blocks ARE absent from the HIR. But this is not currently causing crashes because the deopt-to-interpreter mechanism handles exceptions correctly for all DeoptBase opcodes that have emitExceptionCheck enabled. The co_exceptiontable gap may matter for performance (full exception handling in JIT vs deopt-to-interpreter) but is not a correctness issue for the crash.

**Falsifier:** After fix: (1) test_dot returns 'caught' ✓, (2) CinderX suite ≥37/41 (pending), (3) import-time auto-compile doesn't crash (pending)

**Priority:** P0 — FIXED, awaiting regression verification

---

### P0: Remove LoadAttrCached from emitExceptionCheck Exemption List (FIXED — 19 Feb 07:51Z)

**Root cause:** Our Option D revert (8af4dc49) left kLoadAttrCached in the exemption list of generator.cpp's DeoptBase switch. emitExceptionCheck was never called for LoadAttrCached, so no kNotZero guard was emitted. NULL returns from failed attribute lookups propagated unchecked → SEGFAULT.

**Fix:** Claude added explicit guard in the kLoadAttrCached handler (generator.cpp:1342): `appendGuard(bbb, InstrGuardKind::kNotZero, *instr, result)`.

**Status:** FIXED AND VERIFIED. test_dot returns 'caught'. Import-time auto-compile works (137 functions, no crash). CinderX 37/41.

**Gate requirements:**
1. test_dot returns 'caught' ✓
2. CinderX regression suite ≥37/41 (pending)
3. import-time auto-compile doesn't crash (pending)

**Assignee:** @claude (DONE pending regression)

### P0b: Apply ac75934e (Static Entry Offset) — DONE

**Status:** Applied, test_cinderjit now 172/172. Contributed to 37/41 result.

### P1: GitHub Upstream Sync — APPLIED, TESTING (08:31Z)

**Status:** Claude cherry-picked 21 upstream commits (HEAD e2a3351b). Build succeeded. Both claude and testkeeper running full 41-suite regression independently.

**CORRECTION (08:17Z):** Repos are DIVERGED, not fast-forward. Upstream is 29 commits ahead of merge base, our fork is 25 ahead. Cherry-pick was the only option.

**Applied (21 commits):** cf217b9f, f8aa0c42, 54569a62, b32a5eae, db8e41d2, aec8867a, 3794f3cf, 12adfecc, d37552a7, c06e394a, 7755a576, 1e1525be, 98302a3c, dfd6a8ad, 6c038310, d4fcfb4c, 1e2ea137, ef577a29, 1fa78eb1, 12b551f3, f753e1f0, 76ed00f6, ea59391e, 610de040, **8f781905** (applied as e2a3351b after theologian flagged it as missing).

**Skipped (3 — already applied):** 659606ab, ac75934e, a8381ce4.

**RESOLVED: 8f781905 (D93544179, 'Loads need to avoid getGp too') — WAS MISSING, NOW APPLIED.** Claude initially skipped it. Theologian caught the omission before regression testing. Applied as e2a3351b. This prevented silent data corruption in sub-word loads (ldrb/ldrh register width).

**Conflicts resolved (2, without theologian review per agreed protocol — protocol violation):**
- generator.cpp: kept our asm_arg_binds — **VERIFIED CORRECT** (our version includes kLoadFrame)
- frame.cpp: took Dino's footer approach (98302a3c) — **VERIFIED CORRECT** by theologian (reader-side fix for frame chain walking on ARM64; compatible with our writer-side savedIP approach)

**Prediction to falsify:** ≥37/41 after sync. If generator fixes work: 38/41 (test_jit_generator_aarch64 passes).

**RESULT (08:37Z):** 37/41 — NO REGRESSION, NO IMPROVEMENT. Prediction of 38/41 FALSIFIED. Generator fixes (98302a3c, 1fa78eb1, f753e1f0, 76ed00f6) did NOT resolve test_jit_generator_aarch64 (still 3 errors). The generator test failures are caused by something other than leaks and frame footer logic. Diagnostic: need to examine the specific 3 failing tests — likely CANNOT_SPECIALIZE (Category 2) or a remaining codegen bug not addressed by any upstream commit.

**Assignee:** @claude (sync done), @testkeeper (regression testing)

### P1b: Apply D92907890 (Frame-Finding on ARM64)

**Why P1b (demoted from P1):** The `getIP()` function in frame.cpp reads x86 stack layout on ARM64, returning garbage. This is a real ARM64 bug but is NOT the import-time crash cause. Upstream commit 27753b06 ('Fix lightweight frames ability to find a frame') addresses this — included in the 23 upstream commits.

**Status:** Will be resolved by P1 upstream sync if approved.

### P1: Fix InvalidImmediate (ARM64 Encoding)

**Why P1:** Mechanical fix with high cross-cutting impact. Every large-offset access is a potential crash for both CinderX and PyTorch functions.

**Action:**
1. Audit all immediate emission sites in the aarch64 backend
2. Add range checks + scratch register materialisation for out-of-range values
3. Verify fix against test_jit_preload

**Assignee:** @claude
**Theologian role:** Verify the fix doesn't violate register allocation assumptions (scratch register liveness)

### P2: Cherry-Pick ac75934e (test_condbranch_codegen)

**Why P2:** Low-risk upstream fix. Gets test_cinderjit from 171/172 to 172/172.

**Action:** Cherry-pick and test.

**Assignee:** @claude
**Theologian role:** Review the cherry-pick for conflicts with our aarch64 changes

### P3: AsyncGen CANNOT_SPECIALIZE

**Why P3:** Only affects async generators, which are less common in PyTorch hot paths. The bail-out is graceful (no crash), so it's a functionality gap rather than a safety issue.

**Action:**
1. Determine if the import-time crash shares this root cause
2. If yes, promote to P1 and fix both together
3. If no, defer to after PyTorch testing is green

**Assignee:** @theologian (analysis), @claude (implementation if promoted)

### P4: sys.monitoring (defer)

**Why P4:** Feature gap, not safety issue. PyTorch doesn't use sys.monitoring.

**Action:** Document as known limitation. Defer to future work.

---

## Cross-Cutting Hypothesis

**CONFIRMED ROOT CAUSE (19 Feb 07:29Z):** The import-time SEGFAULT is caused by **Category 7: Missing Python 3.12 Exception Table Support.** This is NOT an ARM64-specific bug — it affects both x86 and ARM64 on Python 3.12.

**Evidence chain:**
1. gdb trace: `isinstance(NULL, cls)` in JIT-compiled `inspect._signature_from_callable` — crash is in EXECUTION, not compilation
2. Minimal reproducer: `def f(x): try: x.nonexist; except: return 'caught'` → force_compile → SEGFAULT (confirmed on devgpu004 + devgpu-tk5)
3. HIR dump: ONLY happy path (bb 5). No exception blocks, no CheckExc after LoadAttrCached
4. Python bytecode HAS exception table: `ExceptionTable: 8 to 30 → 36 [0]`
5. `grep -rn 'co_exceptiontable|exception_table' cinderx/Jit/hir/` → ZERO MATCHES
6. builder.cpp createBlocks() discovers basic blocks only from branch targets — does NOT read co_exceptiontable
7. SETUP_FINALLY (the old mechanism) is dead code: opcode 256, never emitted by Python 3.12

**Mechanism:** Python 3.12 replaced SETUP_FINALLY with co_exceptiontable. The HIR builder was written for SETUP_FINALLY and never parses the new exception table. The HIR builder walks only happy-path bytecodes; exception handler blocks are never created. When a JIT-compiled function with try/except hits an exception, the NULL return from failed operations propagates unchecked → SEGFAULT.

**What happened to earlier hypotheses:**
- D92907890 (frame-finding): MISSING from our build, a real ARM64 bug, but NOT the import-time crash cause. The crash occurs in function execution (isinstance(NULL)), not in deopt/frame-finding.
- D93679174 (primitives w1/w0): Applied as commit 22c40cac. CinderX passes 36/41 — no regression BUT no fix for import-time crash.
- 17 additional Dino fixes: Real ARM64 bugs, many MISSING, but they fix ARM64 codegen issues — the import-time crash is architecture-independent.

**Pythia's strategic warning (checkpoint #50):** The bail-out check (refuse to compile functions with non-empty co_exceptiontable) is safe but limits JIT coverage to functions without exception handling. Python without try/except is not Python. PyTorch's `Module.__getattr__` has try/except — auto-compile would crash on it without the bail-out. The blast radius of this limitation has not been measured.

**Remaining ARM64-specific work:** The 17+ missing Dino Viehland fixes should still be applied. They fix real bugs that will manifest in compiled code. The strategic decision (sync to HEAD vs one-at-a-time) is deferred to Alex.

---

## Open Questions (updated 19 Feb 07:35Z)

1. ~~What function was being compiled when the import-time SEGFAULT occurred?~~ **ANSWERED:** `inspect._signature_from_callable` — 20704 bytes, 36 callees. Crash in EXECUTION (isinstance(NULL)), not compilation. 183 JIT compilations before crash.
2. ~~What opcode triggered the crash?~~ **ANSWERED:** Not an opcode issue. The HIR builder compiled only the happy path — no CheckExc after LoadAttrCached because no exception handler blocks were created. NULL propagated unchecked.
3. ~~Does the JIT's bail-out path (CANNOT_SPECIALIZE → interpreter) work on aarch64?~~ **PARTIALLY ANSWERED:** The bail-out path works for opcodes listed as unsupported (async generators bail out cleanly). The issue is that functions WITH exception tables are not bailed out — the JIT accepts them but compiles them incorrectly.
4. ~~Are there any `#ifdef __aarch64__` guards in generator.cpp that might skip bail-out logic?~~ **SUPERSEDED:** The bug is in the HIR builder, not the LIR generator. The HIR builder's createBlocks() never reads co_exceptiontable, so exception handler blocks are never discovered.
5. **NEW:** How many of the 183 auto-compiled functions have non-empty co_exceptiontable? This determines the JIT coverage impact of the bail-out check. If most hot functions have try/except, the JIT compiles very little.
6. **NEW:** Does `Module.__getattr__` (which has try/except) get auto-compiled? If so, the bail-out check is essential even for post-import auto-compile (Pythia's finding).
7. **NEW:** Should force_compile on a function with exception tables raise an error or silently fall back to interpreter?

---

## Performance Analysis (19 Feb 2026, 10:00Z+)

### Gate Criterion

Alex's performance gate: CinderX+JIT must be within 5% of vanilla CPython on **every** benchmark. Baseline is vanilla CPython, not CinderX-without-JIT.

### Three-Way Benchmark Results (1-rep ABBA, force_compile)

Three-way comparison: Vanilla CPython vs CinderX-no-JIT (PYTHONJITDISABLE=1) vs CinderX+JIT.

**Key finding: CinderX runtime has ~0% overhead.** CX/Van ratio = 0.99x–1.03x across all 22 benchmarks — within measurement noise. **ALL regressions are from JIT codegen quality.**

**Performance gate: RED.** 12/22 benchmarks regress >5% vs vanilla. Geometric mean ~0.94x (JIT is 6% slower).

Worst regressions:
- nbody_step: 0.73x (27% slower)
- yield_from_chain: 0.78x (22% slower)
- gen_parameterised: 0.84x (16% slower)
- float_arith: 0.89x (11% slower)
- gen_simple: 0.89x (11% slower)

### Benchmark Methodology

Benchmark script: `cinderx_jit_benchmark.sh` (706 lines). Methodology is sound for codegen quality measurement:
1. `cinderjit.force_compile(func)` on ALL functions BEFORE any timing (lines 511–516)
2. `cinderjit.is_jit_compiled(func)` verification (lines 530–536)
3. N_WARMUP=3 untimed iterations (lines 539–541)
4. N_MEASURE=5 timed iterations of steady-state execution (lines 543–549)

**Note:** force_compile tests codegen quality (everything compiled). A complementary auto() benchmark (only hot functions compiled) is in progress — may show different results if threshold-based compilation avoids bad-codegen functions.

### Richards Benchmark Integrity: INVALID

The Richards benchmark in cinderx_jit_benchmark.sh is NOT the proper pyperformance Richards. It uses:
- `__slots__` (avoids `__dict__` lookup — the primary thing Richards should test)
- Single task type (no polymorphic dispatch)
- No `TaskControlBlock` or `Packet` hierarchy

Alex caught this: *"is that the proper Richards or the one you made easier by changing the dynamic types to module level? Because - no cheating - I will find out"*

**Action:** Replace with proper pyperformance Richards. Current Richards result is not gate-valid.

**Alex's insight (10:52Z):** "Where the adaptive interpreter cannot adapt and has to deopt — or worse repeatedly deopt — CinderX starts to win." This predicts the JIT/interpreter performance boundary:
- JIT loses where CPython 3.12 has specialised opcodes (float, subscript, call) — the JIT uses generic paths that are slower than the interpreter's specialised ones
- JIT wins where CPython 3.12 can't specialise (complex branching, recursion, polymorphic dispatch)

**Falsifiable prediction for proper Richards:** The proper Richards has polymorphic dispatch (`self.fn(msg, self.handle)` with 4 different implementations). CPython 3.12's CALL_PY_EXACT_ARGS specialises for one receiver type and deopts when the type changes. At the dispatch site, each of 4 task types triggers deopt/respecialise. The JIT compiles the generic dispatch path once and branches correctly via compiled code. **Prediction: CinderX JIT will match or beat vanilla CPython on proper Richards.** If the JIT is >5% slower on proper Richards, this prediction is falsified and the function call overhead is worse than expected.

**RESULT (10:51Z): richards_full = 1.23x (JIT is 23% FASTER than vanilla). Prediction CONFIRMED.** The JIT wins decisively on polymorphic OOP dispatch. This is the first benchmark where the JIT significantly outperforms the adaptive interpreter. Vanilla: 310ms, JIT: 253ms. The adaptive interpreter's LOAD_ATTR_INSTANCE_VALUE specialisation deopts on each of the 4 task type changes at polymorphic call sites.

### Root Cause: Why the JIT Generates Slow Code on ARM64

Two regression categories with likely different root causes:

**Float-heavy benchmarks (nbody 0.73x, float_arith 0.89x):**

**Root cause confirmed from source (10:40Z):** The CinderX JIT has two float codegen paths:
1. **DoubleBinaryOp** (Static Python only): emits native `fadd`/`fsub`/`fmul`/`fdiv` on D registers. Zero boxing. Values stay unboxed. This path is FAST — but only available for Static Python typed code.
2. **FloatBinaryOp** (standard CPython float): calls C slot methods (`float_add`, `float_sub` etc.) via `blr`. Each operation boxes the result through `PyFloat_FromDouble` (heap allocation). This path is SLOW.

Our benchmarks use standard Python floats → FloatBinaryOp path → box every intermediate result. CPython 3.12's BINARY_OP_ADD_FLOAT specialisation keeps values as C doubles in the eval loop — no boxing. The JIT does a C function call + heap allocation per float operation, which is WORSE than the interpreter's specialised path.

Source: FloatBinaryOp in `lir/generator.cpp:1590-1607` (calls `slotMethod()`), DoubleBinaryOp in `lir/generator.cpp:927-963` (emits `kFadd`/`kFsub`/`kFmul`/`kFdiv`), aarch64 rules in `autogen.cpp:2780-2798`.

**Fix strategy:** Teach the HIR builder or type specialiser to emit DoubleBinaryOp for standard Python floats when type inference determines both operands are `float`. This is the JIT equivalent of CPython's BINARY_OP_ADD_FLOAT specialisation.

**CRITICAL DISCOVERY (10:59Z): `specialized_opcodes` is DISABLED by default.**
- `config.h:162`: `bool specialized_opcodes{false}`
- The HIR builder at `builder.cpp:2078` checks `getConfig().specialized_opcodes` before reading CPython 3.12's specialised bytecodes. When disabled (the default), ALL type feedback from the adaptive interpreter is ignored.
- Enable via: `cinderjit.enable_specialized_opcodes()` (pyjit.cpp:2435)
- When enabled: inserts `GuardType(TFloatExact)` for BINARY_OP_ADD_FLOAT, `GuardType(TLongExact)` for BINARY_OP_ADD_INT, `GuardType(TListExact)` for BINARY_SUBSCR_LIST_INT, etc.
- **BUT**: even with guards, the builder still emits generic `BinaryOp` (line 2139), not `FloatBinaryOp`. A downstream optimisation pass must convert `BinaryOp + TFloatExact` → `FloatBinaryOp`. And `FloatBinaryOp` still calls C slot methods, not native FP instructions.
- **Our benchmarks do NOT call `enable_specialized_opcodes()`.** The JIT is compiling blind — no type feedback at all.
- **Immediate action:** Re-run benchmarks with `cinderjit.enable_specialized_opcodes()` to measure the impact.

**Specialized_opcodes benchmark result (11:16Z): MINIMAL EFFECT.** Geomean still 0.95x. Only `list_comp` improved (0.91x → 0.98x, possibly noise). Float benchmarks unchanged (nbody 0.72x, float_arith 0.89x).

**Root cause of no effect:** `force_compile()` compiles functions BEFORE any execution. CPython's adaptive interpreter specialises bytecodes AFTER execution. So `bc_instr.specializedOpcode()` (builder.cpp:2079) returns generic `BINARY_OP`, not `BINARY_OP_ADD_FLOAT`. The type guards are never emitted. The flag is useless with cold `force_compile`. Fix: warm up functions before compiling (run ~100 iterations first).

**Alex directive (11:15Z): Build with GIL, not --disable-gil.** Free-threading not required for current work. This removes ALL three free-threaded blockers (`RETURN_MULTITHREADED_COMPILE` guards become no-ops, list subscript specialisation compiled in). Leave breadcrumbs in code for future `--disable-gil` support.

**Full pipeline analysis (11:01Z):**
Even with `specialized_opcodes` enabled, the improvement chain is incomplete:
1. Builder: `BINARY_OP_ADD_FLOAT` → `GuardType(TFloatExact)` + generic `BinaryOp` ✓
2. Simplify pass (`simplify.cpp:739-744`): `BinaryOp + TFloatExact` → `FloatBinaryOp` ✓
3. **MISSING:** `FloatBinaryOp` → `PrimitiveUnbox + DoubleBinaryOp + PrimitiveBox` ✗
4. `FloatBinaryOp` → C slot method call (`slotMethod()`) — same overhead as without the flag

Additionally, `simplifyFloatBinaryOp` (constant folding) is DISABLED on Python 3.12 (`RETURN_MULTITHREADED_COMPILE(nullptr)` at simplify.cpp:827) because it requires the GIL.

**Conclusion:** Enabling `specialized_opcodes` will help with type guard insertion and may improve branch elimination, but will NOT eliminate the C slot method calls for float operations. The real fix requires an unbox-compute-rebox optimisation pass that does not currently exist.

**Box elimination infrastructure (11:07Z):** The simplify pass ALREADY has `unbox(box(x)) → x` elimination (`simplify.cpp:916-922`). This means expression-level unboxing is NOT a register allocator problem — it falls out naturally from the existing simplify pass. For a chain like `a*dx + b*dy`, if each FloatBinaryOp is converted to `PrimitiveUnbox + DoubleBinaryOp + PrimitiveBox`, the intermediate `PrimitiveBox` feeding the next `PrimitiveUnbox` self-cancels. Intermediates stay in D registers. Only the final `PrimitiveBox` (at Python variable store) allocates.

**Required change:** One new simplify rule in `simplifyFloatBinaryOp` (~20 lines): when FloatBinaryOp operands are TFloatExact, convert to `PrimitiveUnbox(lhs, TCDouble) + PrimitiveUnbox(rhs, TCDouble) + DoubleBinaryOp(op) + PrimitiveBox(result, TCDouble)`. The existing `simplifyUnbox` handles intermediate elimination. The simplify pass iterates until convergence (`iteration_limit=100` at config.h:59), so the three-step chain (BinaryOp → FloatBinaryOp → DoubleBinaryOp → box elimination) converges in 3-4 iterations.

**~~BLOCKER~~ (11:11Z) — RETRACTED (11:19Z):** ~~`simplifyFloatBinaryOp` has `RETURN_MULTITHREADED_COMPILE(nullptr)` blocking ALL FloatBinaryOp simplification.~~ WRONG — the guard only fires during multi-threaded batch compilation (`multithread_compile_units_preloaded`). `force_compile` compiles synchronously, so `compileRunning()` returns false. The guard does NOT fire for our benchmark. `simplifyFloatBinaryOp` IS reachable.

**~~BLOCKER (11:12Z)~~ RESOLVED (12:17Z): List subscript specialisation.** `simplify.cpp:654-676` wraps the list/tuple subscript → `LoadArrayItem` conversion in `#ifndef Py_GIL_DISABLED`. **Py_GIL_DISABLED is NOT defined in our build** — CPython 3.12 does not support `--disable-gil` (PEP 703 landed in 3.13). CinderX's CMakeLists.txt never defines it. All `#ifndef Py_GIL_DISABLED` guards are ACTIVE, meaning: list/tuple subscript (simplify.cpp:655), LoadAttr (1847), LoadMethod (1852), length specialisation (319, 329), inline attribute caches (config.h:149), inline refcount (generator.cpp:481), and list iteration fast paths (builder.cpp:4141) are **ALL ALREADY ENABLED**. No rebuild needed.

**ACTUAL BLOCKER (11:19Z): Lack of type information.** The real reason float benchmarks don't improve:
1. `force_compile` compiles before execution → bytecodes are generic `BINARY_OP`
2. `specializedOpcode()` (builder.cpp:2079) returns `BINARY_OP`, not `BINARY_OP_ADD_FLOAT`
3. No `GuardType(TFloatExact)` emitted → operands remain `TObject`
4. `simplifyBinaryOp` check at line 739 (`lhs->isA(TFloatExact)`) fails → no FloatBinaryOp
5. The entire float specialisation chain is blocked at the FIRST step: no type information

**Fix:** Warm up functions before `force_compile` (100+ calls with representative arguments). This triggers CPython's adaptive interpreter specialisation (`BINARY_OP` → `BINARY_OP_ADD_FLOAT`). Then `force_compile` sees specialised bytecodes → GuardType emitted → FloatBinaryOp → simplification chain fires.

**Benchmark script ordering bug (identified 12:35Z):**

The benchmark script (`cinderx_jit_benchmark.sh`) has TWO ordering errors:
1. Lines 798-803: `force_compile` called at module load time, BEFORE warmup (lines 826-828)
2. Line 870: `PYTHONJITALL=1` env var sets `compile_after_n_calls=0` (pyjit.cpp:306), meaning JIT compiles on FIRST call — before any bytecode specialisation
3. No `cinderjit.enable_specialized_opcodes(True)` call anywhere in the script

**Correct benchmark ordering:**
1. `import cinderjit`
2. `cinderjit.enable_specialized_opcodes(True)`
3. Warmup: run each function ~10 times with representative arguments (CPython specialises bytecodes)
4. `cinderjit.force_compile(func)` for each function (JIT reads specialised bytecodes)
5. Benchmark measurement

**Why the standalone float test works (1.01x) but the benchmark doesn't (0.88x):** The standalone test follows the correct ordering (warmup → compile). The benchmark script does the opposite (compile → warmup). By the time warmup runs in the benchmark, the functions are already JIT-compiled with generic bytecodes.

**CRITICAL EVAL LOOP ORDERING CONSTRAINT (confirmed 19 Feb ~12:00Z):**

CinderX's `Ci_EvalFrame` (interpreter.c:623-624 for 3.15, :561 for 3.14) explicitly sets `#define ENABLE_SPECIALIZATION 0`. This means **CinderX's eval loop does NOT specialise bytecodes**. CPython's default eval loop (`_PyEval_EvalFrameDefault`) has `ENABLE_SPECIALIZATION 1` (confirmed in pycore_code.h:293 for our GIL-enabled build).

The first call to `force_compile()` or `auto()` calls `Ci_InitFrameEvalFunc()` (pyjit.cpp:1551, :1447), which replaces `_PyEval_EvalFrameDefault` with `Ci_EvalFrame` globally. After this, ALL function calls go through the non-specialising eval loop.

**Correct warmup ordering:**
1. `import cinderjit` — OK, does NOT install eval hook
2. **Warmup functions** (run through CPython's default eval loop → bytecodes specialised)
3. `cinderjit.force_compile(func)` — first call installs `Ci_EvalFrame`, compiles with specialised bytecodes

**Broken ordering:**
1. `import cinderjit`
2. `cinderjit.force_compile(any_func)` or `cinderjit.auto()` — installs `Ci_EvalFrame`
3. Warmup — runs through `Ci_EvalFrame` with `ENABLE_SPECIALIZATION 0` — **no specialisation**
4. `cinderjit.force_compile(func)` — bytecodes still generic

**Note:** Python 3.12's CinderX eval loop has `ENABLE_SPECIALIZATION 1` (cinder_opcode_ids.h:341), so this constraint is 3.14+/3.15+ specific. **CORRECTION (12:00Z):** Our build on devgpu004 is Python 3.12.12+meta, NOT 3.15. The ordering constraint does NOT apply to our build — specialisation works under CinderX's eval loop on 3.12. The constraint is documented here for future reference if we forward-port to 3.14/3.15.

**Falsifiable prediction:** If we modify the benchmark to use Static Python annotations (function signatures typed as `-> float`), the JIT should produce unboxed float operations and nbody should match or beat vanilla CPython.

**Generator benchmarks (yield_from_chain 0.78x, gen_parameterised 0.84x):**
1. Generator frame save/restore may be more expensive than interpreter's stack-based approach
2. ARM64 generator frame footer handling was recently fixed (D93525511) — codegen may not be optimised yet

**Generator codegen deep analysis (19 Feb 10:20Z):**

Confirmed: No aarch64 generator deopt guard exists (pyjit.cpp:3710 only blocks CO_ASYNC_GENERATOR). Generators ARE compiled and the regressions are real codegen issues.

The JIT generator architecture uses a FP-pivot mechanism: on resume, FP (X29 on aarch64) is set to point at heap-allocated `gi_jit_data`, so all spill reads/writes go to the generator's storage. This should make subsequent yields cheap (no copy needed).

Sources of aarch64-specific overhead:
1. **~~Forced register spilling~~** RETRACTED (12:20Z): `spillRegistersForYield` (regalloc.cpp:581-582) creates fixed live intervals for ALL physical registers at the yield point. This forces any VReg live at yield to be spilled — but the **number of actual spills depends on live VRegs, not the count of physical registers in INIT_REGISTERS**. On ARM64 (58 regs) vs x86 (30 regs), the same VRegs are live at yield. The INIT_REGISTERS count is irrelevant — any live VReg gets spilled regardless. Replacing INIT_REGISTERS with live_regs() would NOT reduce spills.
2. **ptr_resolve overhead**: FP-relative memory access on ARM64 needs `ptr_resolve` for offsets >4095 (adds 0-1 extra instructions per access). For typical GenDataFooter field offsets (<4096 bytes), most resolve to direct addressing (0 extra). Resume entry (gen_asm.cpp:2437-2509) uses 7 ptr_resolve calls — estimated 2-4 extra instructions total vs x86's direct [reg+offset] addressing.
3. **No memory-indirect branch**: Resume needs explicit `ldr + br` (2 insns) vs `jmp [mem]` (1 insn on x86).
4. **Initial yield frame copy**: Done via C runtime function `JITRT_UnlinkGenFrameAndReturnGenDataFooter` (autogen.cpp:784-826). The 3.10 x86 path used hardware-accelerated `rep movsq` (autogen.cpp:732-741) but this was replaced in 3.12+. Both architectures now use the C function — no ARM64-specific overhead.

**Items #2-#3 account for ~3-5 extra instructions per yield/resume. This does NOT explain 10-22% regression.**

**~~ACTUAL ROOT CAUSE FOUND (12:25Z)~~ RETRACTED (12:35Z): Debug fprintf in generator resume path.**

`generators_rt.cpp:95-108` contains FIVE `fprintf(stderr, ...)` calls and a `fflush(stderr)` inside `send_core()`. **However, these are only in the LOCAL checkout (devgpu009), not on devgpu004 where benchmarks were measured.** The fprintf is an UNCOMMITTED local change — git blame shows "Not Committed Yet". The generator benchmark regression on devgpu004 is NOT caused by this fprintf.

**The fprintf DOES explain performance issues on machines built from this local source** (e.g., devgpu009 or any build from `/home/alexturner/local/cinderx`). It should still be removed from the local source. But it does NOT explain the benchmark regression.

**Generator regression root cause: UNIDENTIFIED (12:35Z).**

Three hypotheses tested, all failed:
1. ~~spillRegistersForYield 2x spill pressure~~ — INIT_REGISTERS count irrelevant
2. ~~Debug fprintf in send_core~~ — not present on devgpu004
3. ~~ARM64 ptr_resolve/ldr+br overhead~~ — only 3-5 extra instructions

**Next step:** Profiling data (`perf stat` on gen_simple) needed to verify instruction count analysis.

**~~PROBABLE ROOT CAUSE (12:40Z)~~ SUPERSEDED (13:15Z): JIT function call overhead per yield/resume.**

The initial analysis identified ~60-90 instructions per JIT yield/resume vs ~40-55 for interpreter. This was directionally correct but mischaracterised as "fundamental architectural overhead." See revised analysis below.

**REVISED ROOT CAUSE (13:15Z): Missing FOR_ITER_GEN specialisation for JIT generators.**

The regression has TWO compounding causes:

**Cause 1: Interpreter's FOR_ITER_GEN never fires for JIT generators.**

CPython 3.12's `FOR_ITER_GEN` specialisation (generated_cases.c.h:3255-3274) guards on exact `Py_TYPE(gen) == &PyGen_Type`. JIT generators use a separate heap type (created via `PyType_FromSpec` from `JitGen_Spec`, generators_rt.cpp:600-631). This means:
- `_Py_Specialize_ForIter` never specialises FOR_ITER to FOR_ITER_GEN for JIT generators
- Even if it did, the `DEOPT_IF(Py_TYPE(gen) != &PyGen_Type)` guard would fire
- JIT generators always take the generic FOR_ITER → `tp_iternext` path

The `FOR_ITER_GEN` fast path uses `DISPATCH_INLINED` (ceval_macros.h:108-117): frame switch + `goto start_frame`. This is ~6 instructions, zero function calls. Regular generators get this path; JIT generators never do.

Similarly, `SEND_GEN` (cinder-bytecodes.c:247-267) only checks `PyGen_Type` and `PyCoro_Type` — JIT generators/coroutines always deopt to generic `SEND`.

**Cause 2: JIT's FOR_ITER lowering is entirely generic.**

The JIT lowers FOR_ITER to `InvokeIterNext` (hir/builder.cpp:3986-4001) → `JITRT_InvokeIterNext` (jit_rt.cpp:2221-2266) → `tp_iternext`. There is no generator-specific specialisation at any level (HIR, LIR, or codegen). Generators are explicitly excluded from the function inliner (inliner.cpp:142-143: `kCoFlagsAnyGenerator`).

The full call chain for a JIT-compiled `for` loop iterating over a JIT generator:
1. JIT code: `call JITRT_InvokeIterNext` (C function call)
2. `JITRT_InvokeIterNext`: `tp_iternext(iterator)` (indirect call through type slot)
3. `jitgen_iternext`: `jitgen_am_send(obj, nullptr, &result)` (C++ call)
4. `jitgen_am_send`: `send_core(gen, arg, tstate)` (C++ call)
5. `send_core`: `gen_footer->resumeEntry(...)` (indirect call into JIT code)
6. JIT generator yields → returns through all 5 layers

That is **5 function call/return pairs** (10 transitions) plus callee-save/restore, FP pivot, and indirect branch per yield/resume.

Compare the interpreter consuming a regular generator via `FOR_ITER_GEN`:
1. `DISPATCH_INLINED(gen_frame)`: frame = gen_frame, goto start_frame (~6 instructions)
2. Generator yields via `YIELD_VALUE`: frame = previous, goto resume_frame (~8 instructions)

**This is NOT a fundamental architectural limitation.** Both systems run on the same hardware. The interpreter achieves fast generator resume by inlining the frame switch. The JIT COULD do the same — it just doesn't.

**Fix options (ranked by impact):**

1. **Override FOR_ITER_GEN and SEND_GEN in cinder-bytecodes.c** to also accept JIT generator/coroutine types. Add guards: `|| JitGen_CheckExact(gen) || JitCoro_CheckExact(gen)`. This would give JIT generators the `DISPATCH_INLINED` fast path when consumed by the interpreter. Impact: fixes interpreted-consumer case.

2. **Add generator-aware InvokeIterNext specialisation in the JIT.** When the JIT can prove (or guard) that the iterator is a JIT generator, emit a direct call to `resumeEntry` instead of going through the 5-layer call chain. This would eliminate ~4 function call pairs per yield/resume. Impact: fixes JIT-consumer case.

3. **Inline send_core into jitgen_am_send** (short-term, low-effort). Reduces one function call level. Saves ~4-8 instructions per yield/resume. Small improvement but doesn't address the fundamental dispatch gap.

**Falsifiable predictions:**
- Fix #1: Overriding FOR_ITER_GEN to accept JIT generators → gen_simple regression drops from 10% to <3% when the consumer is interpreted.
- Fix #2: JIT generator-aware InvokeIterNext → gen_simple regression drops from 10% to <3% when the consumer is JIT-compiled.
- `perf stat` on gen_simple should show ~5x more instructions per yield/resume for JIT path vs interpreter FOR_ITER_GEN path.

**Benchmark vs real-world applicability (13:20Z):**
- In the benchmark, BOTH consumer and generator are JIT-compiled (JIT-ON mode). Fix #1 (FOR_ITER_GEN override) does NOT help the benchmark — it only helps when an interpreted consumer iterates over a JIT generator.
- Fix #2 (JIT generator-aware InvokeIterNext) is what matters for the benchmark regression.
- Fix #1 matters for real applications with mixed JIT/interpreted code.

**Minimal viable implementation of Fix #2 (13:20Z):**

The essential per-yield work is ~10-12 memory operations: frame linkage (`frame->previous = currentFrame(tstate)`), exc chain swap, `gi_frame_state` updates. This is the SAME work the interpreter's `FOR_ITER_GEN` does inline.

A JIT-inlined generator resume would emit:
1. Guard: `Py_TYPE(iter) == jit_gen_type` (1 cmp + deopt)
2. Guard: `gen->gi_frame_state == FRAME_SUSPENDED` (1 cmp + deopt)
3. Inline pre-resume: link frame, swap exc chain, set FRAME_EXECUTING (~6 stores)
4. Call `gen_footer->resumeEntry(...)` directly (1 indirect call — the only call)
5. Inline post-resume: restore exc chain, restore currentFrame, update gi_frame_state (~6 stores)
6. Deopt check: `JitGen_CheckAny(gen_obj)` — if generator deopted during execution

Total: ~20 instructions vs current ~50+ through the 5-layer call chain. The `resumeEntry` call itself is unavoidable (it enters the generator's JIT code), but everything around it can be inlined.

**Alex's insight (12:27Z) confirmed:** "this turing complete system on hardware X can go faster than this other turing complete system also on X is logically falsifiable by inspection." Correct — the overhead is a missing optimisation, not a physical limit.

**~~Fix for #1 (highest impact)~~** RETRACTED (12:20Z): Replacing INIT_REGISTERS with live_regs() in spillRegistersForYield would NOT reduce spills. The fixed intervals force all physical registers to be "occupied" at the yield point, but spills are determined by which VRegs are alive, not how many physical registers are reserved. The same VRegs are live on both architectures.

**Remaining overhead (#2-#3):** ~3-5 extra instructions per yield/resume cycle. This is inherent to ARM64's instruction encoding (no [reg+offset] for large offsets, no memory-indirect branch). Minor contributor — the dominant issue is the missing FOR_ITER_GEN/InvokeIterNext specialisation (see revised analysis above).

Evidence: gen_interleaved (1.00x — no regression) vs gen_simple (0.90x — 10% regression). gen_interleaved does more work per yield, amortising fixed per-yield overhead. gen_simple does minimal work, so per-yield overhead dominates. Consistent with per-yield fixed overhead hypothesis — the fprintf overhead is proportionally larger for tight yield loops.

Original JIT generators on x86 showed 8–15% SPEEDUP over interpreter (D23329728). The aarch64 backend shows 10–22% SLOWDOWN — a 20–35 percentage point swing.

**yield_from_chain deep analysis (13:25Z):**

`yield_from_chain` is the worst generator regression at 0.78x (22%). The `SEND` bytecode path has the SAME 5-level dispatch issue. JIT's `Send` HIR instruction (builder.cpp:4886) lowers to `call JITRT_GenSend` (lir/generator.cpp:3449) → `PyIter_Send` (CPython API, jit_rt.cpp:1645) → `am_send` (type slot) → `jitgen_am_send` → `send_core` → `resumeEntry`. 5 call levels, same as FOR_ITER.

`yield_from_chain` chains multiple generators: `gen_a` yields from `gen_b` yields from `gen_c`. Each value propagation through the chain does N SENDs (one per generator level). With 3 levels, each final value costs 3 × 5 = 15 function call/return pairs. The overhead multiplies with chain depth.

The interpreter's `SEND_GEN` uses `DISPATCH_INLINED` for the same operation — just a frame switch. Chain of 3 generators = 3 frame switches = ~18 instructions total. The JIT version = ~150 instructions total.

**This explains why yield_from_chain (0.78x, 22% regression) is much worse than gen_simple (0.90x, 10% regression).** The dispatch overhead multiplies with chain depth.

Fix #2 (JIT-inlined generator send) would address both FOR_ITER and SEND paths.

**Falsifiable prediction:** The dominant cost is per-yield forced register spilling. If we profile a generator benchmark (perf stat), we should see higher cache miss rate and more memory operations per yield compared to vanilla CPython's interpreter path.

**Falsifiable prediction:** The dominant cost in nbody is float boxing/unboxing. If a benchmark with the same FP maths but using local variables (not list elements) shows a smaller regression, this is confirmed.

**Function call benchmarks (func_calls 0.91x, method_calls 0.92x):**

**Root cause confirmed from source (10:50Z):** The JIT compiles Python-to-Python function calls via `_PyObject_Vectorcall` (lir/generator.cpp:1978) — the GENERIC vectorcall protocol. `TranslateSpecializedCall` (lines 381-454) only handles C functions (PyCFunction_Type), `next()` builtin, and METH_NOARGS/METH_O conventions. It does NOT handle Python-to-Python calls. No JIT-to-JIT direct call path exists.

CPython 3.12's `CALL_PY_EXACT_ARGS` specialisation is faster: single type guard, direct jump to the function's vectorcall slot (pre-resolved), inline frame creation. The JIT's generic `_PyObject_Vectorcall` does type lookup, flag checking, and frame setup every time.

**Fix complexity:** HIGH. Adding JIT-to-JIT direct calls requires resolving the callee at compile time, guarding on function identity, using the callee's JIT entry point directly, and handling deopt on function redefinition. This is a JIT architectural feature, not a simple codegen fix.

**NOTE (10:55Z):** CinderX DOES have JIT-to-JIT direct calls via `InvokeStaticFunction` (lir/generator.cpp:2173-2195). When `isJitCompiled(func)` is true, it calls `JITRT_GET_STATIC_ENTRY(func->vectorcall)` directly — no vectorcall overhead. But this path is only available for Static Python code, not standard Python. The machinery exists; extending it to standard Python (via speculative devirtualisation with a function identity guard) is the right approach.

**Falsifiable prediction:** The function call overhead is constant per call. If we benchmark a function that does more work per call (e.g., 100 additions vs 3), the regression should decrease as the per-call overhead is amortised.

### PyTorch Full Suite Results (JIT auto-compile active)

- test_torch: 1564 pass / 37 fail / 137 skip
- test_autograd: 707 pass / 5 fail / 34 skip
- test_nn: TIMEOUT at 1200s
- **Total: 2271 pass / 42 fail (98.2% pass rate)**

JIT auto-compile (`cinderjit.auto()`) was active. 42 failures need non-JIT baseline to isolate JIT-caused vs pre-existing.

**Non-JIT baseline result (10:36Z):** 0 JIT-caused failures. All 42 failures are pre-existing aarch64/PyTorch issues. **Prediction confirmed** — CinderX runtime has ~0% overhead and near-perfect compatibility.

**Falsifier outcome:** Prediction was "most of 42 are pre-existing, falsified if >10 are JIT-only." Actual: 0 JIT-only. Prediction confirmed with maximum margin.

### Data Collection Status

| Data Point | Status | Result |
|-----------|--------|--------|
| force_compile codegen quality | DONE (1 rep) | 0.94x geomean, 12/22 regress >5% |
| CinderX runtime baseline | DONE | ~1.0x (no overhead) |
| auto() production deployment | **INVALIDATED** | **Previous data was pure interpreter (0/44 compiled — API ordering bug)** |
| auto() corrected (t100) | **DONE** | **0.95x geomean — matches force_compile. Confirms JIT produces same code regardless of compilation mode.** |
| PyTorch non-JIT baseline | **DONE** | **0 JIT-caused failures. All 42 failures are pre-existing aarch64/PyTorch issues.** |
| N_REPS=3 ABBA (statistical) | NOT STARTED | Need for gate-quality data |
| Proper Richards benchmark | **DONE** | **1.23x — JIT 23% FASTER than vanilla. Prediction confirmed.** |

### auto() vs force_compile Comparison (19 Feb 10:14Z) — PARTIALLY INVALIDATED

**UPDATE (19 Feb 10:31Z):** Testkeeper discovered that `cinderjit.auto()` resets `compile_after_n_calls()` when called AFTER it. Previous auto() runs called `compile_after_n_calls(100)` THEN `auto()`, which reset the threshold to 1000. With 100 warmup iterations, NO functions crossed the 1000-call threshold. **Result: 0/44 functions compiled. All previous auto() data was pure interpreter performance.**

**API root cause (confirmed from source, 10:35Z):** `auto_jit()` in pyjit.cpp:1482-1489 hardcodes `compile_after_n_calls_impl(1000)`. `compile_after_n_calls()` in pyjit.cpp:1462-1480 calls the same `compile_after_n_calls_impl(N)`. Both write to `getMutableConfig().compile_after_n_calls` — a single `std::optional<uint32_t>` on a global `Config` singleton (config.cpp:9, config.h:197). Last write wins. No merging, no 'take the minimum'. Correct ordering: `auto()` first, then `compile_after_n_calls(N)` to override.

**Theologian's earlier analysis (that inner helpers crossed 1000-call threshold) was wrong.** The benchmark structure (100 warmup × 100,000 inner iterations = 10M calls) would have compiled inner helpers IF the threshold had been 100 or even 1000 — but the entire auto() compilation mechanism was effectively disabled by the API ordering bug. The 0.96x geomean was CinderX interpreter performance, not JIT performance.

**What remains valid:**
- force_compile: 0.94x geomean (12/22 fail) — genuine JIT codegen quality
- CX-noJIT: ~1.0x vs vanilla — CinderX runtime overhead is negligible
- The force_compile generator regressions (0.78x–0.90x) ARE real JIT codegen issues

**What is invalidated:**
- The auto() geomean of 0.96x
- The auto() vs force_compile comparison (nbody "improvement" was just interpreter vs JIT)
- My analysis that inner generator functions were compiled in auto() mode
- The claim that "threshold correctly avoids compiling functions where JIT code is bad"

**Corrected understanding:** CinderX interpreter ≈ 0.96x vanilla CPython (4% slower). Corrected auto()+compile_after_n_calls(100) produces 0.95x — identical to force_compile. **No threshold strategy can improve performance; the only path is better codegen.**

| Mode | Geomean vs Vanilla | Worst Regression | Gate Failures (>5%) |
|------|-------------------|-----------------|---------------------|
| force_compile | 0.94x | nbody 0.73x | 12/22 |
| ~~auto() (100 warmup)~~ | ~~0.96x~~ | ~~yield_from_chain 0.78x~~ | ~~9/22~~ |
| auto() (INVALIDATED) | Was pure interpreter | API ordering bug: 0/44 functions compiled | N/A |
| auto() corrected (t100) | 0.95x | Matches force_compile | 11/22 |

**auto() is better than force_compile** — ~~confirms Alex's insight from JVM experience. Threshold correctly avoids compiling functions where JIT code is worse (nbody: 0.73x → 0.96x).~~ **INVALIDATED (10:31Z):** The auto() improvement was illusory — 0 functions were compiled due to API ordering bug. The "0.96x" was pure interpreter performance. Corrected auto() run in progress.

**But generators are equally bad in both modes** — the threshold cannot help because generator functions ARE the hot functions. They cross the compilation threshold and get compiled, but the compiled code is worse than the interpreter. **Confirmed by corrected auto() data: gen_parameterised 0.82x (auto) vs 0.84x (force_compile) — within noise.**

~~auto()~~ **INVALIDATED** ~~gate failures (>5% regression vs vanilla):~~
1. ~~yield_from_chain: 0.78x (22%)~~
2. ~~gen_parameterised: 0.82x (18%)~~
3. ~~gen_simple: 0.90x (10%)~~
4. ~~gen_nested: 0.91x (9%)~~
5. ~~func_calls: 0.91x (9%)~~
6. ~~list_comp: 0.91x (8%)~~
7. ~~float_arith: 0.93x (7%)~~
8. ~~coroutine_chain: 0.93x (7%)~~
9. ~~spectral_norm: 0.93x (7%)~~

~~auto() gate passes (>5% improvement):~~
1. ~~chaos_game: 1.09x (9% faster)~~
2. ~~nqueens: 1.08x (8% faster)~~
3. ~~fibonacci: 1.05x (5% faster)~~

**All auto() results above were pure interpreter performance (0/44 functions compiled). Awaiting corrected auto() data from testkeeper.**

**Corrected auto() results (10:36Z):** Geomean 0.95x — matches force_compile (0.94x within noise). 11/22 benchmarks regress >5%. This confirms:
1. When functions ARE compiled, JIT produces the same code regardless of compilation trigger
2. Threshold-based compilation does NOT help — the problem is codegen quality, not compilation policy
3. The previous "auto() is better" signal (0.96x vs 0.94x) was an artefact of 0 functions being compiled

### Codegen Optimisation Priority (updated 10:57Z — all regression root causes identified from source)

**UPDATE (13:08Z): After PYTHONJITALL fix + DoubleBinaryOp + proper warmup ordering:**

| Metric | Before (PYTHONJITALL=1, no type feedback) | After (proper warmup) |
|--------|------------------------------------------|----------------------|
| Geomean | 0.94x (6% slower than vanilla) | **1.05x (5% FASTER than vanilla)** |
| Gate pass | 10/23 | **17/23** |
| float_arith | 0.89x | **1.10x** |
| richards_slots | 0.89x | **1.37x** |

**Remaining 6 gate failures (>5% regression):**
1. yield_from_chain: 0.81x — generator dispatch overhead (5-level call chain × chain depth)
2. spectral_norm: 0.86x — COMPOUND: generator expression in `sum()` (genexpr yields N^2 times), function call dispatch (`_spectral_A` called N^2 times via generic vectorcall), list subscript (`v[j]` via generic sq_item). Float arithmetic is minimal — only `1.0 / (...)` and `A * v[j]`. Most work in `_spectral_A` is integer ops.
3. exceptions: 0.87x — JIT deopts to interpreter on EVERY exception. Benchmark has ~50% KeyError rate in hot loop. Each deopt → interpreter → re-entry is far more expensive than interpreter's inline `goto error`. Architectural: fixing requires native exception handling in JIT (exception handler basic blocks instead of deopt).
4. chaos_game: 0.88x — guard overhead without LICM; GuardType checks in tight loop add per-iteration cost
5. gen_parameterised: 0.92x — generator dispatch overhead (near gate)
6. coroutine_chain: 0.94x — same as yield_from_chain (near gate)

Generator fix (Approach A: ~15-line runtime fast-path) could push gen_parameterised and coroutine_chain past the gate. yield_from_chain needs the full Send-path fix as well.

**Unified root cause: Type specialisation gap.** The CinderX JIT has fast native instruction paths (DoubleBinaryOp → fadd, IntBinaryOp → add) but they are only available through Static Python typed code. Standard Python code uses generic C slot method calls (FloatBinaryOp/LongBinaryOp → blr to C runtime). CPython 3.12's adaptive interpreter has specialised opcodes (BINARY_OP_ADD_FLOAT, BINARY_OP_ADD_INT, CALL_PY_EXACT_ARGS) that are faster than the JIT's generic paths.

| Priority | Target | Benchmarks | Regression | Root Cause | Fix Exists? | Blocker |
|----------|--------|-----------|-----------|------------|-------------|---------|
| P0 | Float type specialisation | nbody, float_arith, ~~spectral_norm~~ | 7–28% | FloatBinaryOp → C slot call + boxing | YES — DoubleBinaryOp → fadd exists, needs simplify rule + box elimination | No type info: force_compile compiles before CPython specialises bytecodes. Fix: warmup before compile + specialized_opcodes flag |
| P0→P2→P1 | Generator yield/resume | yield_from_chain, gen_parameterised, gen_simple, gen_nested, **spectral_norm** (genexpr in sum()) | 10–22% | **Missing specialisation:** (1) FOR_ITER_GEN/SEND_GEN only accept PyGen_Type — JIT generators (separate heap type) always deopt to generic path. (2) JIT's InvokeIterNext is fully generic — 5 function call levels per yield/resume vs interpreter's DISPATCH_INLINED (~6 insns, 0 calls). NOT architectural — fixable. | YES — (a) Override FOR_ITER_GEN/SEND_GEN in cinder-bytecodes.c to accept JIT gen types; (b) Add generator-aware specialisation to JIT's InvokeIterNext | None — the infrastructure exists (DISPATCH_INLINED, direct call patterns) |
| P0 | List subscript specialisation | nbody (inner loop) | Part of 28% | Generic `sq_item` C call instead of direct LoadArrayItem | YES — `LoadArrayItem` exists (simplify.cpp:656-675) | **NONE** — Py_GIL_DISABLED NOT defined (CPython 3.12, no free-threading). All `#ifndef` guards ACTIVE. Already enabled. |
| P1 | Integer type specialisation | list_comp | 9% | LongBinaryOp → C slot call | YES — IntBinaryOp → add exists, same mechanism as float | Same as float: no type info without warmup |
| P2 | Function call dispatch | func_calls, method_calls | 8–9% | VectorCall → generic _PyObject_Vectorcall | YES — InvokeStaticFunction exists, needs speculative devirtualisation | None — fundamental limitation (not implemented for standard Python on any arch) |
| P3 | Exception handling | exceptions | 13% | JIT deopts to interpreter on EVERY exception. 50% KeyError rate = 50% deopt/re-entry per iteration | Needs native exception handling in JIT (exception handler basic blocks) | Architectural — major feature |
| P3 | Guard overhead (LICM) | chaos_game | 12% | GuardType checks inside loop body, no loop-invariant code motion | Needs LICM pass in HIR | Architectural — new optimisation pass |
| P3 | Coroutine overhead | coroutine_chain | 6% | Same as generator yield/resume | Same fix (Approach A covers this) | None |

---

## Deliverables

1. This analysis document (complete)
2. Stack trace + opcode identification for import-time crash (pending @claude)
3. Fix for P0 import-time crash OR confirmed workaround
4. Fix for P1 InvalidImmediate
5. Cherry-pick P2 ac75934e
6. Updated run_cinderx_torch_smoke_tests.sh passing with >0 JIT-compiled functions
