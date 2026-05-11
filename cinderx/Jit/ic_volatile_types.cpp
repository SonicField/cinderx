// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/ic_volatile_types.h"

#include "cinderx/Jit/containers.h"
#include "cinderx/Common/ref.h"

namespace jit {

namespace {

constexpr int kVolatileTypeThreshold = 10;

jit::UnorderedMap<BorrowedRef<PyTypeObject>, int> type_invalidation_counts;
jit::UnorderedSet<BorrowedRef<PyTypeObject>> volatile_types;

}  // namespace

bool isVolatileType(BorrowedRef<PyTypeObject> type) {
  return volatile_types.count(type) > 0;
}

void recordTypeInvalidation(BorrowedRef<PyTypeObject> type) {
  int& count = type_invalidation_counts[type];
  count++;
  if (count >= kVolatileTypeThreshold) {
    volatile_types.emplace(type);
  }
}

}  // namespace jit
