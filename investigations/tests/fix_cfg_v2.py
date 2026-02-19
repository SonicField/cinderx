#!/usr/bin/env python3
"""Fix the CFG bug in Option D kLoadAttrCached inline fast path.

Bug: appendBranch(kBranch, done_block) creates a kBranch instruction with no
label operand. The post-alloc pass (postalloc.cpp:427) skips blocks that
already have a kBranch, so the label never gets added. The verifier then fails:
  ERROR: Basic block N does not contain a jump to non-immediate successor M

Additionally, appendBlock(call_block) after incref_block's branch adds
call_block as a spurious fall-through successor of incref_block.

Fix: Follow the established pattern from HIR kBranch lowering (generator.cpp
line 340-347) — just add successor edges, don't emit kBranch instructions.
The post-alloc pass will add kBranch with proper label operands where needed.
Use switchBlock() instead of appendBlock() where no fall-through edge is wanted.
"""

import sys

GENERATOR_CPP = sys.argv[1] if len(sys.argv) > 1 else \
    "/data/users/alexturner/cinderx_dev/cinderx/cinderx/Jit/lir/generator.cpp"

# Read the file
with open(GENERATOR_CPP, 'r') as f:
    content = f.read()

# The buggy section (lines 1397-1418 approximately)
OLD = """\
          // Incref block: INCREF, write to dst, goto done
          bbb.appendBlock(incref_block);
          bbb.appendInvokeInstruction(Py_IncRef, slot_value);
          bbb.appendInstr(dst, Instruction::kMove, slot_value);
          bbb.appendBranch(Instruction::kBranch, done_block);

          // Call block: invoke with deopt guard, goto done
          bbb.appendBlock(call_block);
          bbb.appendCallInstruction(
              dst, jit::LoadAttrCache::invoke, cache, base, name);
          emitExceptionCheck(*instr, bbb);
          bbb.appendBranch(Instruction::kBranch, done_block);

          // Done block
          bbb.appendBlock(done_block);"""

NEW = """\
          // Incref block: INCREF, write to dst, fall through to done
          bbb.appendBlock(incref_block);
          bbb.appendInvokeInstruction(Py_IncRef, slot_value);
          bbb.appendInstr(dst, Instruction::kMove, slot_value);
          // Add successor edge only — post-alloc adds kBranch with label.
          // Do NOT use appendBranch(kBranch) here: it creates a kBranch
          // without a label operand, and post-alloc skips existing kBranch.
          incref_block->addSuccessor(done_block);

          // Call block: invoke with deopt guard, fall through to done.
          // Use switchBlock (not appendBlock) to avoid adding call_block
          // as a spurious fall-through successor of incref_block.
          bbb.switchBlock(call_block);
          bbb.appendCallInstruction(
              dst, jit::LoadAttrCache::invoke, cache, base, name);
          emitExceptionCheck(*instr, bbb);
          // Add successor edge only — post-alloc adds kBranch with label
          // if call_block is not the immediate predecessor of done_block
          // in layout (which it is, so this will be a fall-through).
          call_block->addSuccessor(done_block);

          // Done block — use switchBlock to avoid duplicate successor edge
          bbb.switchBlock(done_block);"""

if OLD not in content:
    print("ERROR: Could not find the old code block. File may have been modified.")
    print("Searched for:")
    print(OLD[:200])
    sys.exit(1)

count = content.count(OLD)
if count != 1:
    print(f"ERROR: Found {count} occurrences of old code (expected 1)")
    sys.exit(1)

content = content.replace(OLD, NEW)

with open(GENERATOR_CPP, 'w') as f:
    f.write(content)

print("Fix applied successfully.")
print(f"File: {GENERATOR_CPP}")
