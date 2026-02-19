# NEXT TERMINAL GOAL: PyTorch Unit Tests on CinderX aarch64

## Context

The CinderX JIT on aarch64 now passes its own test suite (2183+ tests across 41 suites). The LOAD_ATTR performance fix (Option D) is committed and pushed. The current terminal goal (all CinderX tests running) is nearly met.

The original project plan included Phase 4: "PyTorch tests against CinderX JIT on aarch64". This was never reached — it slipped during the focus on CinderX's own tests.

## Requirement from Alex (18 Feb 2026)

The CinderX JIT must pass PyTorch's unit tests on aarch64.

## Definition of Done

1. PyTorch unit tests run against the CinderX JIT-enabled Python on devgpu004 (aarch64)
2. A **baseline** exists: the same tests run on stock Python 3.12 (no CinderX) on the same machine
3. The test report shows which failures are CinderX regressions vs pre-existing ARM/PyTorch failures
4. Zero CinderX-induced regressions (stock Python failures are acceptable)
5. A test runner script exists that runs the PyTorch test suite with CinderX JIT enabled

## Prerequisites

1. CinderX test suite fully passing (current terminal goal must be met first)
2. PyTorch installed and importable under both stock Python and CinderX Python
3. Baseline test run completed on stock Python (Phase 2a — never done, needs to be done now)

## Known State

- PyTorch 2.10.0+cpu wheel installed in venv on devgpu004
- 6 integration tests pass (linear, NN, backward, SGD, Conv2d, torch.compile)
- Full PyTorch test suite (10,000+ tests) never run against CinderX
- Stock Python baseline never established (Phase 2a was skipped)
- Pythia flagged this gap in checkpoint #15

## Approach

1. **Establish stock Python baseline**: Run PyTorch tests on stock Python 3.12 on devgpu004 (no CinderX). Record pass/fail/error/skip counts.
2. **Run with CinderX JIT**: Run the same tests with CINDERJIT_ENABLE=1. Record results.
3. **Diff the results**: Any test that passes on stock Python but fails on CinderX is a regression.
4. **Fix regressions**: If any exist, investigate and fix.

## Falsifier

If any PyTorch test passes on stock Python 3.12 but fails on CinderX JIT (same machine, same wheel), the goal is NOT met.

## Risks (from Pythia checkpoint #15)

1. PyTorch 2.10.0 wheel may differ from PyTorch HEAD — test results may not be representative
2. torch.compile interop only partially validated (6 tests, no adversarial patterns)
3. GPU tests (GB200/CUDA on ARM) are untouched — this goal is CPU-only
