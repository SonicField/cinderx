// Copyright (c) Meta Platforms, Inc. and affiliates.
#include "cinderx/Jit/iterator_types.h"

namespace jit {

PyTypeObject* g_range_iterator_type = nullptr;

void init_iterator_types() {
  // Get range_iterator type by creating a temporary range iterator.
  // This avoids referencing PyRangeIter_Type which is not exported
  // from the Python executable (not accessible to dynamically loaded
  // extension modules like _cinderx.so).
  PyObject* range_obj = PyObject_CallFunction(
      reinterpret_cast<PyObject*>(&PyRange_Type), "iii", 0, 1, 1);
  if (range_obj == nullptr) {
    PyErr_Clear();
    return;
  }
  PyObject* iter_obj = PyObject_GetIter(range_obj);
  Py_DECREF(range_obj);
  if (iter_obj == nullptr) {
    PyErr_Clear();
    return;
  }
  g_range_iterator_type = Py_TYPE(iter_obj);
  Py_DECREF(iter_obj);
}

} // namespace jit
