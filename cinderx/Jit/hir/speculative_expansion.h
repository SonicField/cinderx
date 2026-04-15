// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include "cinderx/Jit/hir/pass.h"

namespace jit::hir {

// SpeculativeExpansion replaces binary guard outcomes (fast path XOR full deopt)
// with multi-path type dispatch chains that fall back to C-API calls instead
// of deopting.
//
// Transforms:
//   GuardType(dst, type, src)  // DeoptBase: deopts if type doesn't match
//   LoadAttr(result, dst, name_idx, frame)
//
// Into:
//   CondBranchCheckType(src, type, fast_bb, slow_bb)
//
//   fast_bb:
//     RefineType(refined, type, src)
//     LoadAttr(result_fast, refined, name_idx, frame)
//     Branch(merge_bb)
//
//   slow_bb:
//     LoadAttr(result_slow, src, name_idx, frame)
//     Branch(merge_bb)
//
//   merge_bb:
//     Phi(result, fast_result, slow_result)
//
// The key difference: CondBranchCheckType is NOT DeoptBase. On type mismatch,
// control flows to the slow path (C-API PyObject_GetAttr), not to deopt.
// This eliminates deopt metadata overhead (FrameState capture, live register
// tracking, trampoline setup) on the fast path.
class SpeculativeExpansion : public Pass {
 public:
  SpeculativeExpansion() : Pass("SpeculativeExpansion") {}

  void Run(Function& irfunc) override;

  static std::unique_ptr<SpeculativeExpansion> Factory() {
    return std::make_unique<SpeculativeExpansion>();
  }
};

} // namespace jit::hir
