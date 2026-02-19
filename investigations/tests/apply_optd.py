#!/usr/bin/env python3
"""Apply Option D fast-path inline cache to generator.cpp.

Two changes:
1. Replace kLoadAttrCached case with fast-path diamond
2. Add kLoadAttrCached to post-processing exception check skip list
"""
import sys
import os

path = os.path.expanduser(
    '~/local/cinderx_dev/cinderx/cinderx/Jit/lir/generator.cpp'
)

with open(path, 'r') as f:
    content = f.read()

# === Change 1: Replace kLoadAttrCached case ===

old_case = '''case Opcode::kLoadAttrCached: {
        JIT_DCHECK(
            getConfig().attr_caches,
            "Inline caches must be enabled to use LoadAttrCached");
        auto instr = static_cast<const LoadAttrCached*>(&i);
        hir::Register* dst = instr->output();
        hir::Register* base = instr->GetOperand(0);
        Instruction* name = getNameFromIdx(bbb, instr);
        auto cache = getContext()->allocateLoadAttrCache();
        bbb.appendCallInstruction(
            dst, jit::LoadAttrCache::invoke, cache, base, name);
        break;
      }'''

new_case = '''case Opcode::kLoadAttrCached: {
        JIT_DCHECK(
            getConfig().attr_caches,
            "Inline caches must be enabled to use LoadAttrCached");
        auto instr = static_cast<const LoadAttrCached*>(&i);
        hir::Register* dst = instr->output();
        hir::Register* base = instr->GetOperand(0);
        Instruction* name = getNameFromIdx(bbb, instr);
        auto cache = getContext()->allocateLoadAttrCache();
        {
          // Option D: inline fast-path for monomorphic MemberDescr slots.
          // Check cached type pointer; if match, load slot directly.
          // Otherwise fall through to invoke().
          auto call_block = bbb.allocateBlock();
          auto done_block = bbb.allocateBlock();
          auto type_check_block = bbb.allocateBlock();
          auto slot_load_block = bbb.allocateBlock();
          auto incref_block = bbb.allocateBlock();

          // Load cached type pointer (NULL if not yet populated)
          PyTypeObject** fast_type_addr = cache->fastTypeAddr();
          Instruction* cached_type = bbb.appendInstr(
              Instruction::kMove, OutVReg{}, MemImm{fast_type_addr});
          bbb.appendBranch(Instruction::kCondBranch, cached_type,
              type_check_block, call_block);

          // Type check: compare Py_TYPE(obj) against cached type
          bbb.appendBlock(type_check_block);
          Instruction* obj_reg = bbb.getDefInstr(base);
          constexpr int32_t kObTypeOffset = offsetof(PyObject, ob_type);
          Instruction* obj_type = bbb.appendInstr(
              Instruction::kMove, OutVReg{}, Ind{obj_reg, kObTypeOffset});
          Instruction* type_match = bbb.appendInstr(
              Instruction::kEqual,
              OutVReg{OperandBase::k8bit},
              obj_type,
              cached_type);
          bbb.appendBranch(Instruction::kCondBranch, type_match,
              slot_load_block, call_block);

          // Slot load: read attribute at cached offset
          bbb.appendBlock(slot_load_block);
          Py_ssize_t* fast_offset_addr = cache->fastOffsetAddr();
          Instruction* cached_offset = bbb.appendInstr(
              Instruction::kMove, OutVReg{}, MemImm{fast_offset_addr});
          Instruction* slot_addr = bbb.appendInstr(
              Instruction::kAdd, OutVReg{OperandBase::k64bit},
              obj_reg, cached_offset);
          Instruction* slot_value = bbb.appendInstr(
              Instruction::kMove, OutVReg{}, Ind{slot_addr, 0});
          bbb.appendBranch(Instruction::kCondBranch, slot_value,
              incref_block, call_block);

          // Incref block: INCREF result, write to dst, jump to done
          bbb.appendBlock(incref_block);
          bbb.appendInvokeInstruction(Py_IncRef, slot_value);
          bbb.appendInstr(dst, Instruction::kMove, slot_value);
          bbb.appendBranch(Instruction::kBranch, done_block);

          // Call block: slow path with exception check
          bbb.appendBlock(call_block);
          bbb.appendCallInstruction(
              dst, jit::LoadAttrCache::invoke, cache, base, name);
          emitExceptionCheck(*instr, bbb);
          bbb.appendBranch(Instruction::kBranch, done_block);

          // Done block: merge point
          bbb.appendBlock(done_block);
        }
        break;
      }'''

if old_case not in content:
    print("ERROR: Could not find old kLoadAttrCached case. Current state:")
    idx = content.find('case Opcode::kLoadAttrCached:')
    if idx >= 0:
        print(content[idx:idx+200])
    else:
        print("  kLoadAttrCached case not found at all!")
    sys.exit(1)

content = content.replace(old_case, new_case)
print("OK: Replaced kLoadAttrCached case with fast-path diamond")

# === Change 2: Add kLoadAttrCached to exception check skip list ===

old_skip = '        case Opcode::kStoreAttrCached:'
new_skip = '        case Opcode::kLoadAttrCached:\n        case Opcode::kStoreAttrCached:'

if new_skip in content:
    print("OK: kLoadAttrCached already in skip list")
elif old_skip in content:
    content = content.replace(old_skip, new_skip, 1)
    print("OK: Added kLoadAttrCached to exception check skip list")
else:
    print("ERROR: Could not find kStoreAttrCached in skip list")
    sys.exit(1)

# === Write ===

with open(path, 'w') as f:
    f.write(content)

print("DONE: All changes applied to generator.cpp")
