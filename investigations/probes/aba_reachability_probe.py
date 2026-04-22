"""Probe whether annotation-guard emission is enabled and if so whether
the resulting GuardType bug is reachable.

cinderjit exposes disable_emit_type_annotation_guards. If guards are off
by default, GuardType is NOT emitted for annotations, and Path A is
unreachable from default-config Python.
"""
import cinderjit


# Check what's the default and what the toggle does.
print(f"disable_emit_type_annotation_guards: {cinderjit.disable_emit_type_annotation_guards}", flush=True)

# Try to detect the default value by force_compiling a function with an
# annotation and checking if GuardType appears in HIR opcode counts.

class C:
    pass

class D:
    pass


def f(x: C) -> object:
    return x


c_inst = C()
for _ in range(2000):
    f(c_inst)

cinderjit.force_compile(f)
counts = cinderjit.get_function_hir_opcode_counts(f)
print(f"f HIR opcodes (default config): {counts}", flush=True)
guard_type_count = counts.get("GuardType", 0)
print(f"GuardType emitted in default config: {guard_type_count > 0}", flush=True)

# Behavioural confirmation: pass a non-C — does it deopt or raise?
result = f(D())
print(f"f(D()) returned: {result!r}, type is D: {type(result) is D}", flush=True)


# Now try Path B — LOAD_ATTR-style. Look at f2 from the previous probe.
class HasValue:
    value = "VV"


def g(x):
    return x.value  # No annotation; specialise via profiling.


hv = HasValue()
for _ in range(2000):
    g(hv)

cinderjit.force_compile(g)
counts_g = cinderjit.get_function_hir_opcode_counts(g)
print(f"g HIR opcodes (no annotation, polymorphic warmup): {counts_g}", flush=True)
print(f"GuardType in g: {counts_g.get('GuardType', 0) > 0}", flush=True)

# Pass a non-HasValue type
class Empty:
    pass


empty = Empty()
try:
    result_g = g(empty)
    print(f"g(Empty()) returned: {result_g!r}", flush=True)
except AttributeError as exc:
    print(f"g(Empty()) raised AttributeError: {exc}", flush=True)
