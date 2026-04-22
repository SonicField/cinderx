"""Empirical check: does `class C: pass` have tp_version_tag == 0?

Uses ctypes to read the field directly. PyTypeObject layout in CPython 3.12:
- PyObject_VAR_HEAD: ob_refcnt(ssize_t) + ob_type(ptr) + ob_size(ssize_t) = 24 bytes (8+8+8)
- tp_name: ptr = 8
- tp_basicsize: ssize_t = 8
- tp_itemsize: ssize_t = 8
- tp_dealloc: ptr = 8
- tp_vectorcall_offset: ssize_t = 8
- tp_getattr: ptr = 8
- tp_setattr: ptr = 8
- tp_as_async: ptr = 8
- tp_repr: ptr = 8
- tp_as_number: ptr = 8
- tp_as_sequence: ptr = 8
- tp_as_mapping: ptr = 8
- tp_hash: ptr = 8
- tp_call: ptr = 8
- tp_str: ptr = 8
- tp_getattro: ptr = 8
- tp_setattro: ptr = 8
- tp_as_buffer: ptr = 8
- tp_flags: ulong = 8
- tp_doc: ptr = 8
- tp_traverse: ptr = 8
- tp_clear: ptr = 8
- tp_richcompare: ptr = 8
- tp_weaklistoffset: ssize_t = 8
- tp_iter: ptr = 8
- tp_iternext: ptr = 8
- tp_methods: ptr = 8
- tp_members: ptr = 8
- tp_getset: ptr = 8
- tp_base: ptr = 8
- tp_dict: ptr = 8
- tp_descr_get: ptr = 8
- tp_descr_set: ptr = 8
- tp_dictoffset: ssize_t = 8
- tp_init: ptr = 8
- tp_alloc: ptr = 8
- tp_new: ptr = 8
- tp_free: ptr = 8
- tp_is_gc: ptr = 8
- tp_bases: ptr = 8
- tp_mro: ptr = 8
- tp_cache: ptr = 8
- tp_subclasses: ptr = 8
- tp_weaklist: ptr = 8
- tp_del: ptr = 8
- tp_version_tag: unsigned int = 4
- tp_finalize: ptr = 8
- ...

The exact offset of tp_version_tag in 3.12 is non-trivial to compute. Instead
of reading via ctypes (fragile), use a behavioural probe:

cinderjit.print_hir(f) shows the HIR, which includes GuardType operands. If we
JIT-compile f(x: C) -> x, we can inspect whether HIR emits GuardType(C) and
what it says about C's tag.
"""
import cinderjit


# Probe 1: fresh class, no body access — print HIR after compile.
class C:
    pass


def f1(x: C) -> object:
    return x


# Warmup so JIT will compile when we ask.
c_inst = C()
for _ in range(2000):
    f1(c_inst)

cinderjit.force_compile(f1)
print(f"f1 is_jit_compiled: {cinderjit.is_jit_compiled(f1)}", flush=True)
# print_hir requires a debug build, skip.
print("=== HIR opcode counts for f1 ===", flush=True)
try:
    counts = cinderjit.get_function_hir_opcode_counts(f1)
    print(counts, flush=True)
except Exception as exc:
    print(f"get_function_hir_opcode_counts failed: {exc}", flush=True)

# Probe 3: behavioural — pass an unrelated class D. If guard fires correctly,
# we expect some kind of error/deopt; if guard wrongly passes, the body
# returns the D instance silently (functionally OK because body is identity).
class D:
    pass


d_inst = D()
result = f1(d_inst)
print(f"f1(D()) returned: {result!r}", flush=True)
print(f"type(result) is D: {type(result) is D}", flush=True)

# Probe 4: a function whose body DOES type-specific work, so a wrongly-passed
# guard would corrupt or AttributeError.
class HasValue:
    value = "HAS_VALUE"


def f2(x: HasValue) -> str:
    return x.value


hv_inst = HasValue()
for _ in range(2000):
    f2(hv_inst)

cinderjit.force_compile(f2)
print(f"f2 is_jit_compiled: {cinderjit.is_jit_compiled(f2)}", flush=True)
print("=== HIR opcode counts for f2 ===", flush=True)
try:
    counts2 = cinderjit.get_function_hir_opcode_counts(f2)
    print(counts2, flush=True)
except Exception as exc:
    print(f"get_function_hir_opcode_counts failed: {exc}", flush=True)


class NoValue:
    pass


nv_inst = NoValue()
print("=== Calling f2(NoValue()) — annotation says HasValue ===", flush=True)
try:
    result2 = f2(nv_inst)
    print(f"f2(NoValue()) returned: {result2!r}", flush=True)
except Exception as exc:
    print(f"f2(NoValue()) raised {type(exc).__name__}: {exc}", flush=True)
