"""addReference pinning empirical check.

Per theologian 2026-04-21 23:10:00 — determines whether
CodeRuntime::addReference() pins a GuardType target's PyTypeObject so that
ABA pointer reuse is structurally impossible. Decision rule:

    A_alive_after_del == True   → addReference pins → Option C is safe
    A_alive_after_del == False  → addReference does NOT pin → Option A required

No JIT codegen revert needed; the question is about CodeRuntime, not GuardType
codegen.
"""
import gc
import sys
import weakref

import cinderjit


print(f"python: {sys.version}", flush=True)
print(f"cinderjit module: built-in (no __file__)", flush=True)
print(f"is_enabled: {cinderjit.is_enabled()}", flush=True)


class A(list):
    pass


def f(x, i):
    return x[i]


a = A([1, 2, 3])
print(f"A address (pre-warmup): 0x{id(A):x}", flush=True)
print(f"A refcount (pre-warmup): {sys.getrefcount(A)}", flush=True)

for _ in range(2000):
    f(a, 0)

cinderjit.force_compile(f)
assert cinderjit.is_jit_compiled(f), "f did not JIT-compile"
print("f is JIT-compiled: True", flush=True)
print(f"A refcount (post-compile, holding a, A): {sys.getrefcount(A)}", flush=True)

A_weak = weakref.ref(A)
A_id = id(A)
print(f"A address (pre-del): 0x{A_id:x}", flush=True)
print(f"A weakref alive (pre-del): {A_weak() is not None}", flush=True)
# Refcount BEFORE we drop our two strong refs (a, A).
# sys.getrefcount adds 1 for its own argument frame.
pre_del_refcount = sys.getrefcount(A)
print(f"A sys.getrefcount (pre-del, includes +1 for arg): {pre_del_refcount}", flush=True)

del A, a
gc.collect()
gc.collect()

alive_after = A_weak() is not None
print(f"A weakref alive (post-del+gc): {alive_after}", flush=True)
print("---DECISION---", flush=True)
if alive_after:
    print("VERDICT: addReference IS pinning — Option C is structurally safe", flush=True)
    print("Live type held by:", A_weak(), flush=True)
    target = A_weak()
    print(f"  target address: 0x{id(target):x}", flush=True)
    print(f"  target refcount (sys.getrefcount, +1 for arg): {sys.getrefcount(target)}", flush=True)
else:
    print("VERDICT: addReference does NOT pin — Option A is required", flush=True)
    print("(weakref dead → no strong ref remained from CodeRuntime::references_)", flush=True)
