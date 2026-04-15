// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/speculative_expansion.h"

#include "cinderx/Jit/hir/hir.h"
#include "cinderx/Jit/hir/pass.h"
#include "cinderx/Jit/hir/ssa.h"

#include <vector>

namespace jit::hir {

namespace {

struct Candidate {
  GuardType* guard;
  LoadAttr* load_attr;
};

// Find GuardType + LoadAttr pairs that can be speculatively expanded.
// The GuardType must:
// 1. Guard an exact type
// 2. Have a direct LoadAttr use (the operation being protected)
// 3. Not be an iterator dispatch guard (tagged in builder.cpp)
void collectCandidates(
    Function& func,
    std::vector<Candidate>& candidates) {
  RegUses reg_uses = collectDirectRegUses(func);

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

      Register* guard_out = guard.output();
      auto it = reg_uses.find(guard_out);
      if (it == reg_uses.end()) {
        continue;
      }

      for (Instr* use : it->second) {
        if (use->IsLoadAttr()) {
          auto* load_attr = static_cast<LoadAttr*>(use);
          if (!load_attr->alreadyOptimized()) {
            candidates.push_back({&guard, load_attr});
          }
          break;
        }
      }
    }
  }
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

  // Allocate blocks
  BasicBlock* fast_bb = func.cfg.AllocateBlock();
  BasicBlock* slow_bb = func.cfg.AllocateBlock();

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

  // Remove original LoadAttr (result now comes from Phi)
  load_attr.unlink();

  return true;
}

} // namespace

void SpeculativeExpansion::Run(Function& irfunc) {
  std::vector<Candidate> candidates;
  collectCandidates(irfunc, candidates);

  if (candidates.empty()) {
    return;
  }

  for (auto& cand : candidates) {
    expandCandidate(irfunc, cand);
  }

  reflowTypes(irfunc);
}

} // namespace jit::hir
