// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/speculative_expansion.h"

#include "cinderx/Jit/hir/hir.h"
#include "cinderx/Jit/hir/pass.h"
#include "cinderx/Jit/hir/ssa.h"

#include <cstdlib>
#include <unordered_map>
#include <vector>

namespace jit::hir {

namespace {

struct Candidate {
  GuardType* guard;
  LoadAttr* load_attr; // nullptr for guard-only (no downstream LoadAttr)
};

// Find GuardType + LoadAttr pairs that can be speculatively expanded.
// The GuardType must:
// 1. Guard an exact type
// 2. Have a direct LoadAttr use (the operation being protected)
// 3. Not be an iterator dispatch guard (tagged in builder.cpp)
// Check if the guard target is a heap type (user-defined class).
// Builtin types (int, float, str, etc.) don't benefit from expansion
// because their guards rarely fail in practice.
bool isHeapType(Type type) {
  PyTypeObject* py_type = type.uniquePyType();
  if (py_type == nullptr && type.hasTypeSpec()) {
    py_type = type.typeSpec();
  }
  return py_type != nullptr && (py_type->tp_flags & Py_TPFLAGS_HEAPTYPE);
}

void collectCandidates(
    Function& func,
    std::vector<Candidate>& candidates) {
  RegUses reg_uses = collectDirectRegUses(func);

  // Phase 1: collect all expandable guards with their LoadAttr users (if any).
  std::vector<Candidate> all_guards;
  for (BasicBlock& block : func.cfg.blocks) {
    for (Instr& instr : block) {
      if (!instr.IsGuardType()) {
        continue;
      }
      auto& guard = static_cast<GuardType&>(instr);

      if (!guard.target().isExact()) {
        continue;
      }
      if (guard.isIterGuard()) {
        continue;
      }
      if (!isHeapType(guard.target())) {
        continue;
      }
      if (!guard.frameState()) {
        continue;
      }

      // Find LoadAttr user (may not exist).
      LoadAttr* load_attr = nullptr;
      Register* guard_out = guard.output();
      auto it = reg_uses.find(guard_out);
      if (it != reg_uses.end()) {
        for (Instr* use : it->second) {
          if (use->IsLoadAttr()) {
            auto* la = static_cast<LoadAttr*>(use);
            if (!la->alreadyOptimized()) {
              load_attr = la;
            }
            break;
          }
        }
      }

      all_guards.push_back({&guard, load_attr});
    }
  }

  // Phase 2: group by base value using modelReg.
  std::unordered_map<Register*, std::vector<size_t>> groups;
  for (size_t i = 0; i < all_guards.size(); ++i) {
    Register* base = modelReg(all_guards[i].guard->GetOperand(0));
    groups[base].push_back(i);
  }

  // Phase 3: promote groups — if ANY guard in a group has a LoadAttr,
  // include ALL guards in the group for expansion.
  for (auto& [base, indices] : groups) {
    bool has_load_attr = false;
    for (size_t idx : indices) {
      if (all_guards[idx].load_attr != nullptr) {
        has_load_attr = true;
        break;
      }
    }
    if (has_load_attr) {
      for (size_t idx : indices) {
        candidates.push_back(all_guards[idx]);
      }
    }
  }
}

// Expand a guard-only GuardType (no downstream LoadAttr) into:
//
//   [original_bb]
//     ...
//     CondBranchCheckType(src, type, fast_bb, slow_bb)
//
//   [fast_bb]
//     refined = RefineType(type, src)
//     Branch(merge_bb)
//
//   [slow_bb]
//     Branch(merge_bb)
//
//   [merge_bb]
//     result = Phi(fast: refined, slow: src)
//     Snapshot(...)
//     ...rest...
//
// The slow path passes src through unrefined. Downstream ops receive
// either the refined type (fast) or the original (slow), using generic
// dispatch on the slow path without deopting.
bool expandGuardOnly(Function& func, Candidate& cand) {
  auto& guard = *cand.guard;

  BasicBlock* original_bb = guard.block();
  Register* src = guard.GetOperand(0);
  Type target_type = guard.target();
  Register* result = guard.output();

  // Find Snapshot FrameState before the guard.
  const FrameState* snapshot_fs = nullptr;
  for (auto it = original_bb->iterator_to(guard); it != original_bb->begin();) {
    --it;
    if (it->IsSnapshot()) {
      snapshot_fs = static_cast<const Snapshot&>(*it).frameState();
      break;
    }
  }
  if (!snapshot_fs) {
    return false;
  }

  // Allocate blocks
  BasicBlock* fast_bb = func.cfg.AllocateBlock();
  BasicBlock* slow_bb = func.cfg.AllocateBlock();
  slow_bb->setSection(codegen::CodeSection::kCold);

  // Split after GuardType to create merge_bb
  BasicBlock* merge_bb = func.cfg.splitAfter(guard);

  // Replace GuardType with CondBranchCheckType
  auto* cond_branch = CondBranchCheckType::create(
      src, target_type, fast_bb, slow_bb);
  cond_branch->copyBytecodeOffset(guard);
  guard.ReplaceWith(*cond_branch);

  // Fast path: RefineType
  Register* refined = func.env.AllocateRegister();
  auto* refine = RefineType::create(refined, target_type, src);
  refine->copyBytecodeOffset(*cond_branch);
  fast_bb->Append(refine);

  auto* fast_branch = Branch::create(merge_bb);
  fast_branch->copyBytecodeOffset(*cond_branch);
  fast_bb->Append(fast_branch);

  // Slow path: pass src through (no C-API call, no deopt)
  auto* slow_branch = Branch::create(merge_bb);
  slow_branch->copyBytecodeOffset(*cond_branch);
  slow_bb->Append(slow_branch);

  // Merge: Phi receives refined (fast) or src (slow)
  std::unordered_map<BasicBlock*, Register*> phi_args{
      {fast_bb, refined},
      {slow_bb, src},
  };
  auto* phi = Phi::create(result, phi_args);
  phi->copyBytecodeOffset(*cond_branch);
  merge_bb->push_front(phi);

  // Snapshot propagation
  auto* snapshot = Snapshot::create(*snapshot_fs);
  snapshot->copyBytecodeOffset(*cond_branch);
  merge_bb->insert(snapshot, std::next(merge_bb->begin()));

  return true;
}

// Expand a single GuardType + LoadAttr into:
//
//   [original_bb]
//     ...
//     CondBranchCheckType(src, type, fast_bb, slow_bb)
//
//   [fast_bb]
//     refined = RefineType(type, src)
//     result_fast = LoadAttr(refined, name_idx, frame)  // type-specialized
//     Branch(merge_bb)
//
//   [slow_bb]
//     result_slow = CallCFunc(PyObject_GetAttr, src, attr_name)
//     CheckExc(result_slow)  // handle NULL return
//     Branch(merge_bb)
//
//   [merge_bb]
//     result = Phi(fast: result_fast, slow: result_slow)
//     ...rest...
//
// No DeoptBase on either path. Slow path uses C-API directly.
bool expandCandidate(Function& func, Candidate& cand) {
  auto& guard = *cand.guard;
  auto& load_attr = *cand.load_attr;

  BasicBlock* original_bb = guard.block();
  Register* src = guard.GetOperand(0);
  Type target_type = guard.target();
  int name_idx = load_attr.name_idx();

  // Find the last Snapshot FrameState in the original block before the guard.
  // This is needed for Snapshot propagation: after splitAfter creates the
  // merge block, that block may lack a Snapshot, which causes crashes in
  // RefcountInsertion (see commit 8be25e43).
  const FrameState* snapshot_fs = nullptr;
  for (auto it = original_bb->iterator_to(guard); it != original_bb->begin();) {
    --it;
    if (it->IsSnapshot()) {
      snapshot_fs = static_cast<const Snapshot&>(*it).frameState();
      break;
    }
  }
  if (!snapshot_fs) {
    return false;
  }

  // Allocate blocks
  BasicBlock* fast_bb = func.cfg.AllocateBlock();
  BasicBlock* slow_bb = func.cfg.AllocateBlock();
  slow_bb->setSection(codegen::CodeSection::kCold);

  // Split after LoadAttr to create merge_bb
  BasicBlock* merge_bb = func.cfg.splitAfter(load_attr);
  Register* result = load_attr.output();

  // Replace GuardType with CondBranchCheckType
  auto* cond_branch = CondBranchCheckType::create(
      src, target_type, fast_bb, slow_bb);
  cond_branch->copyBytecodeOffset(guard);
  guard.ReplaceWith(*cond_branch);

  // Fast path: RefineType + LoadAttr (type-specialized)
  Register* refined = func.env.AllocateRegister();
  auto* refine = RefineType::create(refined, target_type, src);
  refine->copyBytecodeOffset(load_attr);
  fast_bb->Append(refine);

  Register* fast_result = func.env.AllocateRegister();
  auto* fast_load = LoadAttr::create(
      fast_result, refined, name_idx, *load_attr.frameState(), true);
  fast_load->copyBytecodeOffset(load_attr);
  fast_bb->Append(fast_load);

  auto* fast_branch = Branch::create(merge_bb);
  fast_branch->copyBytecodeOffset(load_attr);
  fast_bb->Append(fast_branch);

  // Slow path: CallStatic(PyObject_GetAttr, src, attr_name)
  BorrowedRef<PyCodeObject> code = load_attr.frameState()->code;
  BorrowedRef<> attr_name_obj = PyTuple_GET_ITEM(code->co_names, name_idx);

  // LoadConst for the attribute name
  Register* name_reg = func.env.AllocateRegister();
  auto* load_name = LoadConst::create(
      name_reg, Type::fromObject(func.env.addReference(attr_name_obj)));
  load_name->copyBytecodeOffset(load_attr);
  slow_bb->Append(load_name);

  // CallStatic(PyObject_GetAttr, src, name_reg) → slow_result
  Register* slow_result = func.env.AllocateRegister();
  auto* call = CallStatic::create(
      2, slow_result,
      reinterpret_cast<void*>(&PyObject_GetAttr),
      TOptObject,
      src, name_reg);
  call->copyBytecodeOffset(load_attr);
  slow_bb->Append(call);

  // CheckExc — handle NULL return from PyObject_GetAttr
  Register* checked_result = func.env.AllocateRegister();
  auto* check = CheckExc::create(
      checked_result, slow_result, *load_attr.frameState());
  check->copyBytecodeOffset(load_attr);
  slow_bb->Append(check);

  auto* slow_branch = Branch::create(merge_bb);
  slow_branch->copyBytecodeOffset(load_attr);
  slow_bb->Append(slow_branch);

  // Merge: Phi receives results from both paths
  std::unordered_map<BasicBlock*, Register*> phi_args{
      {fast_bb, fast_result},
      {slow_bb, checked_result},
  };
  auto* phi = Phi::create(result, phi_args);
  phi->copyBytecodeOffset(load_attr);
  merge_bb->push_front(phi);

  // Snapshot propagation: emit Snapshot in merge block after Phi.
  // Without this, RefcountInsertion crashes when the merge block lacks
  // a Snapshot (the original Snapshot stayed in original_bb before the split).
  auto* snapshot = Snapshot::create(*snapshot_fs);
  snapshot->copyBytecodeOffset(load_attr);
  merge_bb->insert(snapshot, std::next(merge_bb->begin()));

  // Remove original LoadAttr (result now comes from Phi)
  load_attr.unlink();

  return true;
}

} // namespace

void SpeculativeExpansion::Run(Function& irfunc) {
  if (!getenv("CINDERX_SPECEXP")) {
    return;
  }

  std::vector<Candidate> candidates;
  collectCandidates(irfunc, candidates);

  if (candidates.empty()) {
    return;
  }

  for (auto& cand : candidates) {
    if (cand.load_attr != nullptr) {
      expandCandidate(irfunc, cand);
    } else {
      expandGuardOnly(irfunc, cand);
    }
  }

  reflowTypes(irfunc);
}

} // namespace jit::hir
