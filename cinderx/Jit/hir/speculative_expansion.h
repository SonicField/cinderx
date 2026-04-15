// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include "cinderx/Jit/hir/pass.h"

namespace jit::hir {

// SpeculativeExpansion replaces GuardType + LoadAttr patterns with
// CondBranchCheckType → fast path (LoadAttr with refined type) /
// slow path (CallCFunc PyObject_GetAttr) → Phi merge.
//
// No DeoptBase instructions on either path — the slow path calls
// the C-API directly without interpreter re-entry.
class SpeculativeExpansion : public Pass {
 public:
  SpeculativeExpansion() : Pass("SpeculativeExpansion") {}

  void Run(Function& irfunc) override;
};

} // namespace jit::hir
