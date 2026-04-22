# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-strict

"""B6 sentinel: JitConfig struct-layout invariance regression test.

Hypothesis E (testkeeper 2026-04-22 17:17Z): pre-rebuild stale .so had a
struct-layout divergence at JitConfig offset 0xe; the gate
`if (getConfig().support_instrumentation)` at pyjit.cpp:3615 evaluated
against the wrong field (e.g., specialized_opcodes which defaults true),
causing patchSysSetProfileAndSetTrace to fire unconditionally at startup
despite source default false. Tests passed for the wrong reason
(already-active patching), masking the true B.1 fix mechanism.

This test fires if the symptom recurs: in a fresh subprocess with NO
-X jit-support-instrumentation flag, NO PYTHONJITSUPPORTINSTRUMENTATION
env var, and NO call to enable_support_instrumentation(), sys.setprofile
must remain the built-in (not cinderjit's patched_sys_setprofile).

Regression detection only — does NOT enforce the struct layout itself
(B6 fix candidates a/b/c per triage_plan_failing_tests.md handle that).
This sentinel is the verification side of the discipline; the
implementation side is owned by generalist when B6 work begins.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

from cinderx.test_support import skip_unless_jit


@skip_unless_jit("Requires the JIT subsystem to be loadable")
class JitConfigLayoutSentinel(unittest.TestCase):
    """Sentinel for JitConfig struct-layout-divergence symptom recurrence."""

    def test_sys_setprofile_not_auto_patched_at_startup(self) -> None:
        """sys.setprofile must NOT be auto-patched at fresh-subprocess startup.

        Symptom guarded: if JitConfig struct layout drifts such that the
        gate at pyjit.cpp:3615 reads the wrong byte and that byte happens
        to be true, patchSysSetProfileAndSetTrace fires unconditionally
        at cinderjit init. Detect by checking sys.setprofile's identity
        in a fresh subprocess where cinderjit autoloads via PYTHONPATH
        but no patching-opt-in is requested.
        """
        env = {
            "HOME": os.environ.get("HOME", ""),
            "PATH": "/usr/bin:/bin",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
        }

        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; print(sys.setprofile.__module__); "
             "print(sys.setprofile.__name__)"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0,
                         f"Subprocess failed: stderr={result.stderr!r}")

        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2,
                         f"Unexpected stdout: {result.stdout!r}")
        module_name, func_name = lines

        self.assertEqual(
            module_name, "sys",
            f"sys.setprofile.__module__ = {module_name!r}; expected 'sys'. "
            "If 'cinderjit', JitConfig struct-layout-divergence symptom "
            "(Hypothesis E) has recurred — the gate at pyjit.cpp:3615 is "
            "reading the wrong byte. Investigate per B6 triage entry.",
        )
        self.assertEqual(
            func_name, "setprofile",
            f"sys.setprofile.__name__ = {func_name!r}; expected 'setprofile'. "
            "If 'patched_sys_setprofile', see test docstring.",
        )


if __name__ == "__main__":
    unittest.main()
