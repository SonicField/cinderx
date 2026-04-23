# Copyright (c) Meta Platforms, Inc. and affiliates.
import dis
import sys
import unittest

import cinderx.opcode as opcode

# pyre-ignore[21]: can't find test.support
from test.support.import_helper import import_module

_opcode = import_module("_opcode")
# pyre-ignore[21]: can't find _opcode
from _opcode import stack_effect

try:
    # pyre-fixme[21]: Could not find name `shadowop` in `cinderx.opcode`.
    from cinderx.opcode import shadowop
except ImportError:
    if sys.version_info >= (3, 14):
        # pyre-ignore[16]: No attribute _specialized_opmap
        shadowop = set(opcode._specialized_opmap)
    else:
        shadowop = set()


MISSING_STACK_EFFECT = {
    "LOAD_FIELD",
    "STORE_FIELD",
    "LOAD_METHOD_STATIC",
    "INVOKE_METHOD",
    "BUILD_CHECKED_LIST",
    "CAST",
    "LOAD_LOCAL",
    "STORE_LOCAL",
    "PRIMITIVE_BOX",
    "POP_JUMP_IF_ZERO",
    "POP_JUMP_IF_NONZERO",
    "PRIMITIVE_UNBOX",
    "PRIMITIVE_BINARY_OP",
    "PRIMITIVE_UNARY_OP",
    "PRIMITIVE_COMPARE_OP",
    "LOAD_ITERABLE_ARG",
    "LOAD_MAPPING_ARG",
    "INVOKE_FUNCTION",
    "INVOKE_NATIVE",
    "JUMP_IF_ZERO_OR_POP",
    "JUMP_IF_NONZERO_OR_POP",
    "FAST_LEN",
    "CONVERT_PRIMITIVE",
    "LOAD_TYPE",
    "LOAD_CLASS",
    "BUILD_CHECKED_MAP",
    "SEQUENCE_GET",
    "SEQUENCE_SET",
    "LIST_DEL",
    "REFINE_TYPE",
    "PRIMITIVE_LOAD_CONST",
    "RETURN_PRIMITIVE",
    "LOAD_METHOD_SUPER",
    "LOAD_ATTR_SUPER",
    "TP_ALLOC",
}


class CinderX_OpcodeTests(unittest.TestCase):
    def test_stack_effect(self) -> None:
        self.assertEqual(stack_effect(dis.opmap["POP_TOP"]), -1)
        # 3.12 replaced DUP_TOP_TWO with COPY (which takes an arg). Per
        # alexie 2026-04-23 07:34:50Z: 'test should be updated as 3.10
        # support is dropped'.
        self.assertEqual(stack_effect(dis.opmap["COPY"], 1), 1)
        self.assertEqual(stack_effect(dis.opmap["BUILD_SLICE"], 0), -1)
        self.assertEqual(stack_effect(dis.opmap["BUILD_SLICE"], 1), -1)
        self.assertEqual(stack_effect(dis.opmap["BUILD_SLICE"], 3), -2)
        self.assertRaises(ValueError, stack_effect, 30000)
        self.assertRaises(ValueError, stack_effect, dis.opmap["BUILD_SLICE"])
        self.assertRaises(ValueError, stack_effect, dis.opmap["POP_TOP"], 0)
        # All defined opcodes
        for name, code in dis.opmap.items():
            # TASK(T74641077) - Figure out how to deal with static python opcodes
            if name in MISSING_STACK_EFFECT or code in shadowop:
                continue
            # 3.12 pseudo-opcodes (code >= 256: POP_BLOCK, SETUP_*, etc.)
            # and INSTRUMENTED_LINE don't follow the canonical
            # HAVE_ARGUMENT partition; skip from the strict-form check.
            if code >= 256 or name == "INSTRUMENTED_LINE":
                continue

            with self.subTest(opname=name):
                if code < dis.HAVE_ARGUMENT:
                    stack_effect(code)
                    self.assertRaises(ValueError, stack_effect, code, 0)
                else:
                    stack_effect(code, 0)
                    self.assertRaises(ValueError, stack_effect, code)
        # All not defined opcodes
        for code in set(range(256)) - set(dis.opmap.values()):
            with self.subTest(opcode=code):
                self.assertRaises(ValueError, stack_effect, code)
                self.assertRaises(ValueError, stack_effect, code, 0)

    def test_stack_effect_jump(self) -> None:
        # 3.12 replaced JUMP_IF_TRUE_OR_POP with POP_JUMP_IF_TRUE which
        # always pops (no conditional retain-on-true). Per alexie
        # 2026-04-23 07:34:50Z: 'test should be updated as 3.10 support
        # is dropped'.
        POP_JUMP_IF_TRUE = dis.opmap["POP_JUMP_IF_TRUE"]
        self.assertEqual(stack_effect(POP_JUMP_IF_TRUE, 0), -1)
        self.assertEqual(stack_effect(POP_JUMP_IF_TRUE, 0, jump=True), -1)
        self.assertEqual(stack_effect(POP_JUMP_IF_TRUE, 0, jump=False), -1)
        # 3.12 changed FOR_ITER to keep iterator on stack on jump=True
        # (END_FOR pops it later); jump=True stack_effect went -1 → 1.
        FOR_ITER = dis.opmap["FOR_ITER"]
        self.assertEqual(stack_effect(FOR_ITER, 0), 1)
        self.assertEqual(stack_effect(FOR_ITER, 0, jump=True), 1)
        self.assertEqual(stack_effect(FOR_ITER, 0, jump=False), 1)
        JUMP_FORWARD = dis.opmap["JUMP_FORWARD"]
        self.assertEqual(stack_effect(JUMP_FORWARD, 0), 0)
        self.assertEqual(stack_effect(JUMP_FORWARD, 0, jump=True), 0)
        self.assertEqual(stack_effect(JUMP_FORWARD, 0, jump=False), 0)
        # All defined opcodes
        has_jump = dis.hasjabs + dis.hasjrel
        for name, code in dis.opmap.items():
            # TASK(T74641077) - Figure out how to deal with static python opcodes
            if name in MISSING_STACK_EFFECT or code in shadowop:
                continue
            # Skip 3.12 pseudo-opcodes + INSTRUMENTED_LINE (per
            # test_stack_effect skip rationale).
            if code >= 256 or name == "INSTRUMENTED_LINE":
                continue

            with self.subTest(opname=name):
                if code < dis.HAVE_ARGUMENT:
                    common = stack_effect(code)
                    jump = stack_effect(code, jump=True)
                    nojump = stack_effect(code, jump=False)
                else:
                    common = stack_effect(code, 0)
                    jump = stack_effect(code, 0, jump=True)
                    nojump = stack_effect(code, 0, jump=False)
                if code in has_jump:
                    self.assertEqual(common, max(jump, nojump))
                else:
                    self.assertEqual(jump, common)
                    self.assertEqual(nojump, common)


if __name__ == "__main__":
    unittest.main()
