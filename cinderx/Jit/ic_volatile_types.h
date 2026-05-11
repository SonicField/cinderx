// Copyright (c) Meta Platforms, Inc. and affiliates.
#pragma once

#include "cinderx/Common/ref.h"

namespace jit {

bool isVolatileType(BorrowedRef<PyTypeObject> type);
void recordTypeInvalidation(BorrowedRef<PyTypeObject> type);

}  // namespace jit
