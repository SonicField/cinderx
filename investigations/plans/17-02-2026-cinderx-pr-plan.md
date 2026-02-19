# CinderX aarch64 JIT — PR Plan

**Date:** 17 February 2026
**Author:** Dr Alex Turner
**Target:** facebookincubator/cinderx (GitHub)
**Maintainer contact:** Kevin Newton (kddnewton) — Alex's team, to be pinged 18 Feb 2026

## Summary

Submit a PR that enables CinderX JIT compilation on aarch64 (ARM64) for Python 3.12, with a focus on PyTorch workloads. The PR includes frame walking fixes, saved-IP slot management, and a generator deopt guard.

## Pre-requisites

- [x] CLA signed (Alex is Meta senior principal)
- [ ] Contact kddnewton before submitting — he's already reviewing PR #13 (another aarch64 attempt by 113xiaoji, called "AI slop")
- [x] Review PR #13's changes for overlap with our work (completed 17 Feb — see analysis below)
- [x] Phase 4c full validation: 15/15 CPU + 8/8 GPU regression suite with deopt guard (DONE — zero regressions)
- [x] Verify PR #13 generators_rt.cpp semantic compatibility (Pythia #29 flag — RESOLVED: no conflicts, basicsize change is 3.14-only)
- [ ] Test clean-apply on throwaway branch before creating PR branch (Pythia #29 flag)

## Existing PR #13

PR #13 "Arm jit unified" by 113xiaoji, opened 2026-02-16:
- 23 changed files, +763/-68
- No description
- kddnewton commented: "It looks like a combination of a bunch of unrelated changes... Otherwise this just comes across as AI slop with no clear goal."
- CLA bot requested signature from 113xiaoji
- Status: Open, no reviews

**Action:** Alex to discuss with Kevin whether PR #13 should be superseded, merged, or coordinated with our work.

### PR #13 Overlap Analysis (completed 17 Feb 23:21 UTC)

**Overlapping files (7 — merge conflict risk):**
1. `autogen.cpp` — Both remove JIT_ABORT for k8bit/k16bit. PR #13 also adds leaIndex comments.
2. `autogen.h` — Both remove JIT_ABORT for sub-word registers. Same fix.
3. `gen_asm.cpp` — PR #13 has whitespace fix in generateEpilogue. We have 6+ substantive changes.
4. `pyjit.cpp` — PR #13 removes `#ifndef __x86_64__ return 0`. We have the same + generator deopt guard.

**PR #13-only files (not in our changeset):**
- `util.h` — parseNumber rewrite for aarch64 std::from_chars float compat
- `code_patcher.h` — removes std::bit_cast (aarch64 libstdc++ compat)
- `generators_rt.cpp`, `jit_rt.cpp`, `jit_rt.h` — runtime fixes
- `lir/operand.h` — LIR operand changes
- `vtable_defs.c` — StaticPython changes
- `UpstreamBorrow/*` (6 files) — borrowed code updates for 3.14/3.15
- `arm_jit_guide.md` — documentation
- `test_arm_runtime.py` — 3 basic ARM smoke tests
- `scripts/*` — deploy/sync scripts

**Key differences:**
- PR #13 targets Python 3.14/3.15; our work targets 3.12
- PR #13 does NOT fix frame walking / saved-IP (our core fix)
- PR #13 does NOT have generator deopt or crash tests
- PR #13 has portability fixes we don't have (stdlib compat)

**Conclusion:** Complementary, not competing. Need careful coordination on 4 overlapping files.

## Our Changeset

### Commits on devgpu004 (origin/main..HEAD)

```
43434bec  aarch64 JIT port: interim state (WIP)
74111fab  Restore interim fix state (WIP)
68126095  SP-relative saved-IP [SP,#8] (SUPERSEDED)
322d20f2  Phase 4b: FP-relative saved-IP (THE FIX)
dab744b0  Phase 4c: Generator test suite (20 tests)
07e68d92  Phase 4c: Deopt guard for generators on aarch64
c7ad3ead  Phase 4c: Fix test expected values
3c67492d  Phase 4c: Deopt assertion tests + enhanced guard comments
6be29706  Phase 5c: Fix gi_jit_data corruption — enable generator JIT (LATEST)
```

### Phase 5c (commit 6be29706) — Generator JIT via originalFP indirection

**Date:** 18 Feb 2026 04:56 UTC
**Status:** GATE CONDITIONAL GREEN — code correct, tests pass, process concern (see below)

This commit removes the Phase 4c deopt guard and enables generators to be JIT-compiled
on aarch64. The fix uses originalFramePointer indirection:

**Root cause:** After the prologue swaps FP to heap-allocated GenDataFooter, saved-IP
writes at [FP + saved_ip_fp_offset] corrupt gi_jit_data in the generator object.

**Fix — two corruption vectors addressed:**
1. emitCall/translateCall: Load originalFP from [FP+16] (GenDataFooter.originalFramePointer),
   write saved-IP to [originalFP + saved_ip_fp_offset] (stack frame). Applied to all 5 call
   sites (2× emitCall in gen_asm_utils.cpp, 3× translateCall in autogen.cpp).
2. saveCallerRegisters zero-init: Skip zeroing saved-IP slot for generators (would corrupt
   gi_jit_data on heap). Guarded by `!env_.is_generator`.

**Key design decision:** `is_generator` set in gen_asm.cpp before `generateCode()` (not
just in translateYieldInitial) because the FP swap happens in the prologue, before body
code runs. All subsequent emitCall sites need the indirection.

**Files changed:** environ.h (+7), gen_asm.cpp (+22/-4), gen_asm_utils.cpp (+34/-8),
autogen.cpp (+39/-12), jit_rt.cpp (+2/-1), pyjit.cpp (-45), test_jit_generator_aarch64.py (+28/-17)

**Test results (independently verified by gatekeeper):**
- test_jit_generators: 35/35 PASS (generators now JIT-compiled)
- test_jit_frame: 16/16 PASS
- test_jit_exception: 15/15 PASS
- test_jit_generator_aarch64: 24/24 PASS
- test_jit_disable: 15/15 PASS
- test_jitlist: 12/12 PASS

**Process concern:** Committed at 04:56 UTC after 00:43-00:52 UTC team consensus to
revert Phase 5c and keep Phase 4c. No chat notification of second attempt. Alex must
decide whether to keep or revert.

### PR Decision Point (for Alex)

**Option A — PR with Phase 5c (generator JIT enabled):**
- Stronger PR: no known limitations section needed
- Clean-apply produces 3 commits: core fix, generator fix, test suite
- Requires re-running full PyTorch regression (15/15 CPU, 8/8 GPU) on Phase 5c build

**Option B — PR with Phase 4c only (generator deopt):**
- Safer: extensively tested and gate-reviewed
- Phase 5c submitted as follow-up PR
- Known limitation: generators deopted to interpreter

### Proposed Clean-Apply Strategy (3 atomic commits)

**Why clean-apply, not cherry-pick squash:** Our development history includes 7 commits
with 4 superseded intermediate states (SP-relative → FP-relative, interim fixes,
test value corrections). Cherry-picking across these contradictory commits risks merge
conflicts, dead code from superseded approaches, or stale comments leaking through.
Pythia #29 flagged this — the squash plan was never tested and may silently include
artefacts from abandoned approaches.

**Method:** Start from a clean `origin/main` branch. For each logical commit, manually
apply only the final, validated changes by diffing `HEAD` (322d20f2 + 07e68d92 +
c7ad3ead) against `origin/main`. This guarantees no ghost code from intermediate states.

**Procedure:**
```bash
# 1. Create clean PR branch from upstream
git checkout -b aarch64-jit-pr origin/main

# 2. Generate the complete diff of final state vs upstream
git diff origin/main HEAD -- <file-list> > /tmp/full-changes.patch

# 3. For each logical commit, apply only the relevant files:

# Commit 1: Core JIT enablement + frame walking fix
git diff origin/main HEAD -- detection.h pyjit.cpp frame.cpp frame_shadow.cpp \
  gen_asm.cpp gen_asm_utils.cpp autogen.cpp autogen.h frame_asm.cpp \
  environ.h code_runtime.cpp code_runtime.h generator.cpp \
  CMakeLists.txt pyproject.toml | git apply
# Remove the generator deopt guard from pyjit.cpp (that goes in commit 2)
# Verify build + tests
git commit -m "aarch64 JIT: enable JIT compilation on ARM64"

# Commit 2: Generator deopt guard (pyjit.cpp only — the 3 guard sites)
git diff origin/main HEAD -- pyjit.cpp | git apply
# This adds only the kCoFlagsAnyGenerator guards
git commit -m "aarch64 JIT: deopt generators to interpreter"

# Commit 3: Generator test suite
git diff origin/main HEAD -- \
  cinderx/PythonLib/test_cinderx/test_jit_generator_aarch64.py | git apply
git commit -m "aarch64 JIT: add generator crash test suite"
```

**Validation after clean-apply:**
- [ ] Each commit builds independently (no broken intermediate states)
- [ ] Full test suite passes after final commit (15/15 CPU, 8/8 GPU, 105/105 JIT)
- [ ] `git diff aarch64-jit-pr HEAD` is empty (no changes lost or added)
- [ ] Manual review of each commit for stale comments, dead `#ifdef` paths, unused includes
- [ ] No references to SP-relative `[SP,#8]` approach in committed code (superseded)

**Commit 1: "aarch64 JIT: enable JIT compilation on ARM64"**
- Files: detection.h, pyjit.cpp, frame.cpp, frame_shadow.cpp, gen_asm.cpp, gen_asm_utils.cpp, autogen.cpp, autogen.h, frame_asm.cpp, environ.h, code_runtime.cpp, code_runtime.h, generator.cpp, CMakeLists.txt, pyproject.toml
- Description: Remove CINDER_UNSUPPORTED for aarch64, fix frame walking (FP-relative saved-IP slot), fix register clobbers, fix sub-word register mapping, fix large stack frame allocations, add aarch64 build support
- Note: pyjit.cpp changes in this commit are the architecture gate removal only, NOT the generator deopt

**Commit 2: "aarch64 JIT: deopt generators to interpreter"**
- Files: pyjit.cpp
- Description: Skip JIT compilation for generators/coroutines/async generators on aarch64. Root cause: generateResumeEntry() reassigns FP to heap-allocated GenDataFooter, causing saved-IP writes at [FP+offset] to corrupt heap memory. Three guard sites: shouldScheduleCompile (both overloads) + force_compile.

**Commit 3: "aarch64 JIT: add generator crash test suite"**
- Files: test_jit_generator_aarch64.py
- Description: 20 tests covering 10 crash vectors for generator JIT on aarch64. Uses cinderjit.force_compile() to exercise compilation paths. Verifies generators produce correct output when running interpreted under the deopt guard.

### Diffstat (estimated after clean-apply)

~16 files changed, ~700 insertions, ~40 deletions

## PR Description Template

```markdown
## Summary

Enable CinderX JIT compilation on aarch64 (ARM64) for Python 3.12.

### What this PR does

1. **Removes the `CINDER_UNSUPPORTED` block for aarch64** — CinderX JIT now compiles
   and executes Python bytecode on ARM64 via asmjit.

2. **Fixes frame walking on aarch64** — Uses FP-relative saved-IP slot instead of
   SP-relative to avoid overlap with vectorcall argument registers
   (`kVectorcallArgsOffset`). Adds fallback to saved LR when slot is zero.

3. **Fixes aarch64-specific codegen bugs:**
   - Register clobber in frame_asm.cpp (w1 → w12)
   - Sub-word register mapping in autogen.h (k8bit/k16bit → W registers)
   - Large stack frame allocation (isAddSubImm guard for 12-bit encoding limit)
   - Argument register pre-loading conflict in gen_asm.cpp

4. **Deopts generators to interpreter on aarch64** — Generators reassign FP to
   heap-allocated GenDataFooter, making saved-IP writes unsafe. The deopt guard
   is temporary; a proper fix (SP-relative for generators) will follow.

5. **Adds comprehensive generator crash test suite** — 20 tests covering 10 crash
   vectors (generator, async generator, coroutine, yield from, throw, close,
   nested, exception handling, traceback, stress).

### Test results

**PyTorch CPU (15/15 modules, PYTHONJITCOMPILATIONTHRESHOLD=1000):**
39,596 passed, 5 failed (all PyTorch build/bug — verified failing without CinderX),
1,420 skipped. Zero JIT regressions.

**PyTorch GPU (8/8 modules, PYTHONJITCOMPILATIONTHRESHOLD=1000):**
747 passed, 7 failed (all CUDA/hardware — verified failing without CinderX).
Zero JIT regressions.

**CinderX JIT tests (18 suites):**
105/105 passed. Three previously-crashing suites (test_jit_generators,
test_jit_frame, test_jit_exception) now pass with deopt guard.

### Known limitations

- Generators/coroutines/async generators are deopted to interpreter on aarch64
  (safe but ~2-10x slower for generator-heavy code)
- Proper generator fix planned as follow-up

## Test plan

- [x] 15/15 CPU PyTorch test suite — zero regressions
- [x] 8/8 GPU PyTorch test suite — zero regressions
- [x] 18 CinderX JIT test suites — 105/105 pass
- [x] 20 generator crash vector tests — all pass
- [x] Deopt verification — generators NOT compiled, normal functions ARE compiled
- [x] Clean build from committed source verified
```

## Execution Steps

1. **Alex pings Kevin (18 Feb)** — discuss PR #13 overlap, get buy-in
2. ~~**Complete Phase 4c validation**~~ — DONE (15/15 CPU + 8/8 GPU, zero regressions)
3. **Add negative assertion test** — `is_jit_compiled(gen_func) == False` (Pythia recommendation)
4. **Add explanatory comments** — in pyjit.cpp guard sites explaining deopt rationale (Alex's directive)
5. **Clean-apply commits** on devgpu004 (AFTER Kevin conversation):
   - Create `aarch64-jit-pr` branch from `origin/main`
   - Apply final validated changes file-by-file (NOT cherry-pick — see strategy above)
   - Verify each commit builds independently
   - Run full test suite on final state
   - Manual review for stale artefacts from superseded approaches
6. **Fork & push** — Alex forks facebookincubator/cinderx, pushes branch
7. **Open PR** — use template above
8. **Respond to review** — Kevin may want changes, coordinate with PR #13

## Risk Assessment

- **PR #13 conflict:** 4 overlapping files identified. Alex talking to Kevin mitigates this.
- **PR #13 generators_rt.cpp:** Removes `sizeof(GenDataFooter*)` from basicsize — **VERIFIED COMPATIBLE** (18 Feb). This change targets 3.14/3.15 where PyGenObject layout differs. On 3.12 (our target), the removed code path (`sizeof(PyGenObject)`) was never reached anyway. PR #13 does not modify `gen_data_footer.cpp` which computes the GenDataFooter pointer — confirming the basicsize removal is a 3.14-only cleanup. Our changeset touches zero common files with PR #13's generators_rt.cpp changes.
- **CONTRIBUTING.md warning:** "not in a state to accept contributions". Alex being on Kevin's team mitigates this.
- **Build reproducibility:** PR must build and pass CI on GitHub Actions (ubuntu-latest, x86_64 only). Our aarch64 changes are ifdef-guarded so x86_64 CI should be unaffected.
- **Generator deopt as tech debt:** Clearly labelled as temporary. Phase 5 plan will follow.
- **Clean-apply artefacts (Pythia #29):** Must manually verify no stale comments, dead `#ifdef` paths, or unused includes from superseded approaches (SP-relative, interim fixes) survive into PR commits. Clean-apply strategy mitigates this vs cherry-pick squash.
