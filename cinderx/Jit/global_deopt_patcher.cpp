// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/global_deopt_patcher.h"

namespace jit {

GlobalDeoptPatcher::GlobalDeoptPatcher(
    BorrowedRef<PyDictObject> globals,
    BorrowedRef<PyUnicodeObject> key_name,
    BorrowedRef<> expected_value)
    : globals_{globals} {
  ThreadedCompileSerialize guard;
  key_name_.reset(key_name);
  expected_value_.reset(expected_value);
}

bool GlobalDeoptPatcher::maybePatch(BorrowedRef<> new_value) {
  if (new_value == expected_value_.get()) {
    return false;
  }
  patch();
  return true;
}

void GlobalDeoptPatcher::onPatch() {
  key_name_.reset();
  expected_value_.reset();
}

} // namespace jit
