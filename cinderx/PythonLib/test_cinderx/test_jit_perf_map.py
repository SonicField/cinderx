# Copyright (c) Meta Platforms, Inc. and affiliates.

# pyre-strict

import os.path
import re
import subprocess
import sys
import unittest

import cinderx

cinderx.init()

from cinderx.test_support import ENCODING, skip_unless_jit, subprocess_env


class PerfMapTests(unittest.TestCase):
    @skip_unless_jit("Runs a subprocess with the JIT enabled")
    def test_forked_pid_map(self) -> None:
        """Each forked process should generate a /tmp/perf-<pid>.map file
        containing the JIT-compiled functions present at standalone-frame
        granularity. The HIR inliner subsumes simple wrapper functions
        (parent / child1 / child2 in the helper) into their callers, so
        only main + compute appear as standalone perf-map entries — that
        is correct under the current JIT architecture (B2'' empirical
        confirmation 2026-04-23 08:43:51Z; HIR inliner BY-DESIGN).
        """
        helper_file = os.path.join(
            os.path.dirname(__file__),
            "perf_fork_helper.py",
        )
        proc: subprocess.CompletedProcess[str] = subprocess.run(
            [sys.executable, "-X", "jit-perfmap", helper_file],
            stdout=subprocess.PIPE,
            encoding=ENCODING,
            env=subprocess_env(),
        )
        self.assertEqual(proc.returncode, 0)

        def find_mapped_funcs(which: str) -> set[str]:
            pattern = rf"{which}\(([0-9]+)\) computed "
            m = re.search(pattern, proc.stdout)
            self.assertIsNotNone(
                m, f"Couldn't find /{pattern}/ in stdout:\n\n{proc.stdout}"
            )
            pid = int(m[1])
            map_contents = ""
            try:
                with open(f"/tmp/perf-{pid}.map") as f:
                    map_contents = f.read()
            except FileNotFoundError:
                self.fail(f"{which} process (pid {pid}) did not generate a map")

            funcs = set(re.findall("__CINDER_JIT:__main__:(.+)", map_contents))
            return funcs

        # Inliner subsumes parent/child1/child2 wrappers into main; only
        # main + compute remain as standalone-compiled artifacts. Each
        # forked process MUST still produce a perf-map file containing
        # both — that is the load-bearing fork-perf-map invariant.
        expected = {"main", "compute"}
        self.assertEqual(find_mapped_funcs("parent"), expected)
        self.assertEqual(find_mapped_funcs("child1"), expected)
        self.assertEqual(find_mapped_funcs("child2"), expected)
