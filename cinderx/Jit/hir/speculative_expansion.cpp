// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/speculative_expansion.h"

namespace jit::hir {

// Speculative expansion pass — currently disabled.
//
// The infrastructure for speculative expansion (C-API slow paths,
// value-chain guard grouping, DeoptStats-driven selective expansion)
// was developed and tested but the optimization gap it targets does
// not exist in CinderX's current architecture: subclass graph checks,
// LoadAttrCached, and PIC already handle polymorphic dispatch without
// deopting GuardType. See investigations/analysis/ for the full report.
//
// The Simplify split architecture (SimplifyEarly/Late) and type_widened
// flag are preserved in git stash for potential future use.
void SpeculativeExpansion::Run(Function& irfunc) {
  (void)irfunc;
}

} // namespace jit::hir
