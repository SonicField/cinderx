# ARM64 heap-check toolchain blocker — tracker

**Status:** UNRESOLVED ROOT BLOCKER. Will re-fire on next ARM64 SIGSEGV / heap-corruption / use-after-free / double-free class bug. Filed per supervisor 23:12:51Z synthesizer-pattern commitment (pythia 51 #4) + recursive-policy-collapse rule (librarian 23:27:59Z fire).

## Problem

`feedback_asan_first.md` rule mandates ASan-first triage for SIGSEGV / heap-corruption / GC class bugs ("found root cause in minutes after 6 falsified theories"). On devgpu004 ARM64 (current Phase 3 dev host), NO heap-check tool works on cinderx binaries:

| Tool | Path | Failure mode | Verified |
|------|------|--------------|----------|
| clang 21 ASan | `/usr/bin/clang-21` | clang_rt subdir empty: missing `libclang_rt.asan.a` + `libclang_rt.asan_static.a` | testkeeper 19:34Z + 22:42:17Z |
| platform010-aarch64 clang | `/usr/local/fbcode/platform010-aarch64/bin/` | NO clang binary present in dir; NO `libclang_rt` / `libasan` in `lib/` | testkeeper 22:42:17Z + 22:43:27Z |
| gcc 11 ASan | system gcc | `libasan.so.6` PRESENT but cinderx build fails on clang-specific `-Wno-*` flags (build-script gcc-incompatible) | testkeeper 22:43:27Z |
| valgrind 3.22 memcheck | system | Cannot decode ARM64 instruction `0x9901027F` at `create_gil` (Meta-Python ARM64 uses instructions valgrind 3.22 doesn't yet support) | testkeeper 22:43:27Z + 22:44:43Z |

## Why this is a root blocker (not a per-bug routed-around)

1. **ASan-first rule mandates this tool class.** Memory `feedback_asan_first.md` codified after 6 falsified theories → ASan pinned root cause in minutes. Without any heap-check tool, every ARM64 heap-corruption-class bug rolls back to theory-driven debugging.

2. **Already routed-around once.** test_jit_preload OverflowError (Mechanism 2 in `23-04-2026-arm64-workers1-corruption-tracker.md`) deferred via Option B defensive-depth + tracker because no ASan/Valgrind path. Next ARM64 heap-corruption bug will hit the same wall.

3. **Pythia 51 prediction:** "When ARM64 next fires 'weird memory error in preload' the team re-discovers M1/M2/M3 from the tracker — and re-discovers that none of the heap-check tools work on devgpu004 either, because that root blocker was routed-around rather than resolved."

## Resolution paths (none yet validated)

| Path | Estimate | Risk |
|------|----------|------|
| A. Install `libclang_rt.asan*` for clang 21 (package manager) | unknown — depends on devgpu004 package availability + sudo | low risk if successful; standard ASan workflow |
| B. Adapt cinderx build for gcc (replace clang-specific `-Wno-*` flags with gcc equivalents under conditional) | ~2-4hr build-system work | medium risk — gcc may surface warning/error class clang silenced; ABI-compat must be verified |
| C. Install valgrind 3.23+ (supports newer ARM64 instructions) | unknown — package manager availability | low if successful; valgrind ~10-30x slowdown but workable |
| D. Cross-validate on x86_64 (where ASan works per existing 18:14Z evidence) | ~1hr per bug | only catches non-ARM64-specific corruption; misses ARM64-only |
| E. Custom gdb breakpoint + malloc/free instrumentation | ~hours per bug | fragile; not class-fix |

## Pre-impl gate

When this blocker re-fires (next ARM64 heap-corruption bug):
1. Cite this artifact in the bug's tracker / fix-spec.
2. Attempt Path A first (lowest cost if available).
3. If Path A fails, Path C, then Path B (build-system work).
4. Path D (cross-validate on x86_64) only as triage shortcut, NOT as resolution.
5. Path E only when (A,C,B,D) all blocked; document in tracker as fallback.

## Triggers for forcing-function review

- If this blocker fires 2+ times in 7 days substantive ARM64 work → escalate to alexie for Path A/B/C resourcing.
- If Phase 3 ARM64 (per `project_cinderx_next_phases.md`) gets blocked on a SIGSEGV with no heap-check tool → block Phase 3 progress on resolving this artifact, not on routing around per-bug.

## Cross-references

- pythia 51 (2026-04-23T23:12:08Z) #4 + #d
- supervisor 23:12:51Z synthesizer-pattern commitment
- librarian 23:27:59Z recursive-policy-collapse fire
- `feedback_asan_first.md` (the rule this blocker neutralizes on ARM64)
- `investigations/plans/23-04-2026-arm64-workers1-corruption-tracker.md` (first instance routed around: M2 OverflowError)
- testkeeper 22:42:17Z + 22:43:27Z + 22:44:43Z empirical tool-availability matrix
