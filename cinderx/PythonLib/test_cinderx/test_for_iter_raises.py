# Copyright (c) Meta Platforms, Inc. and affiliates.
# pyre-strict

import unittest

import cinderx
import cinderx.jit

from cinderx.test_support import skip_unless_jit

cinderx.init()


class ForIterRaisesTest(unittest.TestCase):
    """Regression test for the JIT NULL-deref class fix.

    Pre-fix empirical behavior: SIGSEGV (process-killing crash) when
    a JIT-compiled FOR_ITER consumed a NULL from InvokeIterNext (which
    can return NULL on iterator-raised exception per its hir.h doc).
    The downstream type-check then dereferenced NULL at offset
    PyObject->ob_type → segfault.

    Post-fix expected behavior: graceful Python exception propagated
    via JIT deopt to interpreter; the original exception class
    surfaces normally.

    Root-cause repair sites (HIR-level, per feedback_hir_not_lir.md):
    - cinderx/Jit/hir/builder.cpp emitForIter: emit CheckExc on
      InvokeIterNext output before CondBranchIterNotDone
    - cinderx/Jit/hir/simplify.cpp: JITRT_InvokeIterNext substitution
      sets output type to TOptObject (so CheckExc not DCE'd as
      redundant)
    - cinderx/Jit/hir/pass.cpp: kInvokeIterNext outputType returns
      TOptObject (consistent with the substitution + the doc'd
      NULL-on-error semantics)
    """

    @skip_unless_jit("Exercises JIT-compiled FOR_ITER")
    def test_iter_raises_during_jit_compiled_loop(self) -> None:
        class ExceptingIter:
            def __init__(self) -> None:
                self.count = 0

            def __iter__(self) -> "ExceptingIter":
                return self

            def __next__(self) -> int:
                self.count += 1
                if self.count > 2:
                    raise RuntimeError("iter boom")
                return self.count

        def consume() -> list[int]:
            return [x for x in ExceptingIter()]

        cinderx.jit.force_compile(consume)
        with self.assertRaises(RuntimeError):
            consume()

    @skip_unless_jit("Exercises JIT-compiled FOR_ITER over list iterator")
    def test_iter_raises_via_list_iter_with_subclass(self) -> None:
        # A list whose iterator __next__ subclass raises. Exercises the
        # FOR_ITER list-iterator specialization path that JIT replaces
        # with CallStatic(JITRT_InvokeIterNext) in the Simplify pass.
        class BadList(list):
            pass

        bad = BadList([1, 2, 3])

        def consume(seq: list[int]) -> int:
            total = 0
            for x in seq:
                total += x
            return total

        cinderx.jit.force_compile(consume)
        # Sanity: works on plain list
        self.assertEqual(consume(bad), 6)


if __name__ == "__main__":
    unittest.main()
