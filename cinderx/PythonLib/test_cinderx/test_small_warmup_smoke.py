"""Compound-crash regression test for 78cee3c7 + c4e1900c.

Falsification target:
  The original-crash workload (cinderjit.auto + bench_deep_class +
  bench_json_roundtrip with compile_after_n_calls=10) must complete
  without SIGSEGV.

Empirical matrix (testkeeper, 2026-04-21; archived at
investigations/probes/compound_crash_falsifier_matrix_2026-04-21.md):
  - Both fixes applied (HEAD): 5/5 EXIT=0
  - 78cee3c7 reverted only:    EXIT=0
  - c4e1900c reverted only:    EXIT=0
  - BOTH reverted:             5/5 EXIT=139 (SIGSEGV)

The two fixes are JOINTLY necessary in default-config builds; neither
alone surfaces the crash. This test drives the workload via subprocess
so a SIGSEGV on revert exits the worker (returncode != 0) without
killing the unittest runner.

Why the inlined version (drafted 2026-04-21 ~15:50 PDT, deleted in
the same session) was insufficient:
  - No cinderjit.auto() call → different compile-trigger semantics.
  - Inlined functions live in the test module's globals, not in the
    JIT-warmed benchmark module — IC + slab allocation pattern diverges.

Pass condition: subprocess returncode == 0 across 3 runs.
Failure mode the test catches: SIGSEGV (returncode == -11 / 139),
SIGBUS (-7 / 135), abort (-6 / 134), or non-zero exit from any
worker.

Reproducing the falsifier (revert path):
  See investigations/probes/compound_crash_falsifier_matrix_2026-04-21.md
  for the surgical revert recipe (78cee3c7 context.cpp + c4e1900c
  slab_arena.h together; OR 78cee3c7 alone — also a sufficient
  falsifier per the n=5 matrix).

Limitations (per pythia 4 critique, 2026-04-22 01:19:08Z):
  - Falsifier matrix was n=5 per cell on a single host (devvm),
    single glibc, single malloc tunable, single ASLR/PIE config.
    Sufficient to OBSERVE the regime, not to PROVE the bug's
    structure across environments.
  - Cell 3 (slab-only revert) was 5/5 clean at default config.
    A future single-fix regression on c4e1900c may surface on a
    different host; this test does NOT catch slab-only regressions
    in default config. Soft-coverage gap acknowledged.
  - Cross-host replication is post-push followup, not yet performed.
"""

import os
import subprocess
import sys
import textwrap
import unittest

try:
    import cinderjit  # noqa: F401
    HAS_JIT = True
except ImportError:
    HAS_JIT = False


_WORKLOAD = textwrap.dedent(
    """
    import sys

    import cinderjit

    cinderjit.auto()
    cinderjit.compile_after_n_calls(10)

    sys.path.insert(0, '.')
    import benchmark_cinderx as bm

    for _ in range(12):
        bm.bench_deep_class(100)
    bm.bench_deep_class(50000)
    for _ in range(12):
        bm.bench_json_roundtrip(100)
    bm.bench_json_roundtrip(50000)
    print("DONE")
    """
).strip()


def _find_repo_root():
    # Walk up from this file until we find build.sh (the cinderx repo root).
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(10):
        if os.path.exists(os.path.join(cur, "build.sh")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


@unittest.skipUnless(HAS_JIT, "requires CinderX JIT")
class TestCompoundCrashSentinel(unittest.TestCase):
    """Regression test for the small-warmup compound crash class."""

    def test_original_workload_no_segfault(self):
        repo_root = _find_repo_root()
        if repo_root is None:
            self.skipTest("repo root not found (no build.sh in ancestor dirs)")
        if not os.path.exists(os.path.join(repo_root, "benchmark_cinderx.py")):
            self.skipTest("benchmark_cinderx.py not at repo root")

        env = os.environ.copy()
        # Ensure the worker subprocess sees cinderjit by inheriting PYTHONPATH.
        # The current test was launched with PYTHONPATH including PythonLib;
        # propagate that to the subprocess.

        for run in range(3):
            with self.subTest(run=run):
                result = subprocess.run(
                    [sys.executable, "-c", _WORKLOAD],
                    cwd=repo_root,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                # Negative returncode on POSIX = killed by signal abs(rc).
                # 139 = 128 + 11 (SIGSEGV) when shell maps it.
                self.assertEqual(
                    result.returncode,
                    0,
                    msg=(
                        f"run {run} returncode={result.returncode}\n"
                        f"stdout: {result.stdout[-500:]}\n"
                        f"stderr: {result.stderr[-500:]}"
                    ),
                )
                self.assertIn("DONE", result.stdout)


if __name__ == "__main__":
    unittest.main()
