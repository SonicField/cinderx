// Copyright (c) Meta Platforms, Inc. and affiliates.

#pragma once

#include "cinderx/Jit/hir/pass.h"

namespace jit::hir {

// Specialize Phis that carry boxed integers (TLongExact) to carry unboxed
// CInt64 when all inputs are unboxable and all uses are PrimitiveUnbox.
// Eliminates per-iteration box/unbox in integer accumulation loops.
class PhiUnboxing : public Pass {
 public:
  PhiUnboxing() : Pass("PhiUnboxing") {}

  void Run(Function& irfunc) override;
};

} // namespace jit::hir
