// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/speculative_expansion.h"

#include "cinderx/Jit/hir/hir.h"
#include "cinderx/Jit/hir/pass.h"
#include "cinderx/Jit/hir/ssa.h"

#include <vector>

namespace jit::hir {

namespace {

// Check if a GuardType instruction is a candidate for speculative expansion.
// We expand GuardType instructions that:
// 1. Guard an exact type
// 2. Have a FrameState (needed for the deopt block)
// 3. Have uses (the guard output is consumed by downstream code)
// 4. Directly feed a LoadAttr instruction (pre-Simplify pattern)
bool isCandidate(
    const GuardType& guard,
    const RegUses& reg_uses,
    Instr** out_load_attr) {
  if (!guard.target().isExact()) {
    return false;
  }
  if (!guard.frameState()) {
    return false;
  }

  Register* guard_out = guard.output();
  auto it = reg_uses.find(guard_out);
  if (it == reg_uses.end() || it->second.empty()) {
    return false;
  }

  // Look for a LoadAttr use (pre-Simplify pattern)
  for (Instr* use : it->second) {
    if (use->IsLoadAttr()) {
      *out_load_attr = use;
      return true;
    }
  }

  return false;
}

} // namespace

void SpeculativeExpansion::Run(Function& irfunc) {
  RegUses reg_uses = collectDirectRegUses(irfunc);

  // Collect candidates (GuardType + LoadAttr pairs)
  struct Candidate {
    GuardType* guard;
    Instr* load_attr;
  };
  std::vector<Candidate> candidates;

  for (BasicBlock& block : irfunc.cfg.blocks) {
    for (Instr& instr : block) {
      if (!instr.IsGuardType()) {
        continue;
      }
      auto& guard = static_cast<GuardType&>(instr);
      Instr* load_attr = nullptr;
      if (isCandidate(guard, reg_uses, &load_attr)) {
        candidates.push_back({&guard, load_attr});
      }
    }
  }

  // Currently finds 0 candidates after Simplify has lowered LoadAttr.
  // TODO: Either run before Simplify or match post-Simplify patterns
  // (LoadField, CallStatic, etc.) to expand more guards.
  if (candidates.empty()) {
    return;
  }

  // Future: expand candidates here
  reflowTypes(irfunc);
}

} // namespace jit::hir
