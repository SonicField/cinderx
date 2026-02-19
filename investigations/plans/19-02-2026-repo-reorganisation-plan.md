# Repo Reorganisation Plan

## Date: 19-02-2026
## Author: testkeeper

## Problem

CinderX-related artefacts are split across two repos:

1. **nbs-framework** (`github.com/SonicField/nbs-framework`) — should contain only NBS framework code, docs, and tooling
2. **cinderx fork** (`github.com/SonicField/cinderx`, branch `aarch64-jit-generators`) — should contain all CinderX investigation artefacts

Currently, nbs-framework has accumulated ~40 CinderX-specific files (plans, test scripts, benchmarks, analysis docs, Python patches) that don't belong there. The cinderx fork has the actual C++ changes and benchmark methodology doc but is missing the investigation documentation and test tooling.

## Inventory

### Files in nbs-framework that belong in cinderx fork

**Scripts (executable artefacts):**
- `run_cinderx_tests.sh` — test runner (canonical copy already on devgpu004)
- `abba_benchmark.sh` — ABBA benchmark runner
- `cinderx_jit_benchmark.sh` — JIT benchmark script
- `run_cinderx_torch_smoke_tests.sh` — PyTorch smoke tests
- `verify_loadattr_fix.sh` — LOAD_ATTR verification
- `17-02-2026-cinderx-baseline-test.sh` — baseline test
- `17-02-2026-cinderx-rebuild.sh` — rebuild script
- `17-02-2026-cinderx-build-pytorch.sh` — PyTorch build script

**Python patches/tests:**
- `apply_b2.py` — B2 patch applier
- `apply_optd.py` — Option D patch applier
- `fix_deopt.py` — deopt fix
- `fix_runner.py` — runner fix
- `b2_bench.py` — B2 benchmark
- `b2_gdb_test.py` — B2 GDB test
- `closure_crash_repro.py` — crash reproduction
- `test_b2_nested.py` — B2 nested test
- `test_b2_smoke.py` — B2 smoke test
- `test_loadattr_inline_fastpath.py` — LOAD_ATTR test suite
- `17-02-2026-cinderx-baseline-compare.py` — baseline comparison
- `17-02-2026-cinderx-smoke-test.py` — smoke test
- `arm-optimisation/fix_cfg_v2.py` — CFG fix
- `arm-optimisation/test_jit_exception_data_access.py` — exception test
- `arm-optimisation/test_loadattr_inline_fastpath.py` — LOAD_ATTR test (duplicate)

**Investigation documentation (should move to cinderx `investigations/` folder):**
- `17-02-2026-cinderx-arm-jit-plan.md` — initial plan
- `17-02-2026-cinderx-jit-architecture.md` — architecture analysis
- `17-02-2026-cinderx-phase2a-results.md` — Phase 2a results
- `17-02-2026-cinderx-pr-plan.md` — PR plan
- `18-02-2026-option-d-plan.md` — Option D plan
- `18-02-2026-phase5f-scope.md` — Phase 5f scope
- `18-02-2026-pr13-analysis.md` — PR13 analysis
- `18-02-2026-test-coverage-audit.md` — test coverage audit
- `18-02-2026-loadattr-test-strategy.md` — LOAD_ATTR test strategy
- `18-02-2026-x86-regression-plan.md` — x86 regression plan
- `18-02-2026-pytorch-test-plan.md` — PyTorch test plan
- `19-02-2026-aarch64-root-cause-analysis.md` — root cause analysis
- `19-02-2026-b1-stack-depth-analysis.md` — B1 stack depth
- `19-02-2026-b2-implementation-plan.md` — B2 plan
- `19-02-2026-b2-implementation-spec.md` — B2 spec
- `19-02-2026-b2-open-questions-analysis.md` — B2 open questions
- `19-02-2026-b2-progress.md` — B2 progress log
- `19-02-2026-c-to-c-call-analysis.md` — C-to-C call analysis
- `19-02-2026-exception-coverage-design.md` — exception coverage
- `19-02-2026-exception-handling-design.md` — exception handling
- `19-02-2026-g1-gate-checklist.md` — G1 gate checklist
- `19-02-2026-generator-dispatch-analysis.md` — generator analysis
- `19-02-2026-generator-dispatch-plan.md` — generator plan
- `19-02-2026-test-coverage-expansion-plan.md` — test expansion plan
- `19-02-2026-x86-exception-handling-analysis.md` — x86 exception analysis
- `arm-optimisation/18-02-2026-loadattr-progress.md` — LOAD_ATTR progress (76KB)
- `arm-optimisation/18-02-2026-loadattr-test-strategy.md` — test strategy
- `arm-optimisation/18-02-2026-option-d-worker-prompt.md` — worker prompt
- `arm-optimisation/18-02-2026-x86-regression-plan.md` — x86 regression
- `arm-optimisation/github-issue-cfg-bug.md` — CFG bug report

**Miscellaneous:**
- `phase5e-review-diff.txt` — diff review
- `NEXT-TERMINAL-GOAL.md` — terminal goal
- `NEW-TERMINAL-GOAL.md` — terminal goal

### Files that should stay in nbs-framework
- `README.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md` — repo docs
- `nbs-gdb-skill.md` — NBS skill (generic)
- `bin/`, `src/`, `.nbs/` — NBS framework code and config
- NBS-specific plans (12-02, 16-02 dated files about nbs-chat, cross-machine, etc.)

### Files already in cinderx fork (correct location)
- `investigations/benchmark-methodology.md` — just committed (6175a1d2)
- All C++ source changes (builder.cpp, jit_rt.cpp, etc.)
- `arm-optimisation/run_cinderx_tests.sh` — test runner on devgpu004

## Plan

### Phase 1: Move investigation docs to cinderx fork (on devgpu004)

1. Create `investigations/` directory in cinderx fork (already exists from benchmark docs)
2. Copy all investigation `.md` files from nbs-framework to cinderx `investigations/`
3. Organise by topic:
   - `investigations/plans/` — plans and specs
   - `investigations/analysis/` — root cause analyses, architecture docs
   - `investigations/progress/` — progress logs
   - `investigations/gate-checklists/` — gate checklists
4. Commit and push on the fork

### Phase 2: Move scripts and test files to cinderx fork

1. Copy scripts to `investigations/scripts/` in cinderx fork
2. Copy test files to `investigations/tests/` in cinderx fork
3. Verify the canonical `run_cinderx_tests.sh` at `arm-optimisation/` is the latest version
4. Commit and push

### Phase 3: Verify copies

1. Confirm all investigation docs are accessible in the cinderx fork
2. Confirm test runner still works on devgpu004
3. Diff spot-check: verify 3 random files match between source and destination

### Phase 4: Clean up nbs-framework

1. Remove all CinderX-specific files from nbs-framework (only after Phase 3 passes)
2. Remove this plan file itself (it's CinderX-specific — move to cinderx `investigations/`)
3. Keep only NBS framework code, NBS-specific docs, and NBS plans
4. Commit with message explaining the reorganisation
5. Push

## Constraints

- **Accept git history break.** Files are being copied across repos (nbs-framework → cinderx fork). `git log --follow` won't work across repos. The nbs-framework git log retains the original history. These are ephemeral investigation docs, not production code.
- **Coordinate with claude.** She is actively working on devgpu004 — avoid conflicts with her dict specialisation work.
- **The test runner on devgpu004 (`arm-optimisation/run_cinderx_tests.sh`) is the canonical copy.** The one in nbs-framework is a local copy for reference. After reorganisation, there should be exactly ONE copy in the cinderx fork.

## Falsifier

After each phase, verify:
- `git status` shows clean working tree
- All files are accessible at their new locations
- No CinderX artefacts remain in nbs-framework (grep for "cinderx" in filenames)
- Test runner still executes on devgpu004
