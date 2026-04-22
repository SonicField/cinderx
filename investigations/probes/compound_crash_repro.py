"""Replay the exact workload that originally SIGSEGV'd before 78cee3c7 + c4e1900c.

Per chat record (sessions 8-10): the crash was reproduced via
  cinderjit.auto(); cinderjit.compile_after_n_calls(10)
  bench_deep_class(100) x 12 + bench_deep_class(50000) + bench_json_roundtrip ...

If this workload runs to completion on the current build (fixes applied),
that confirms the fixes resolve the bug. The same workload run after a
revert of either fix would crash (per ASan evidence in chat).
"""
import sys

import cinderjit

cinderjit.auto()
cinderjit.compile_after_n_calls(10)

sys.path.insert(0, '.')
import benchmark_cinderx as bm

print("Starting bench_deep_class warmup", flush=True)
for i in range(12):
    bm.bench_deep_class(100)
print(f"warmup done", flush=True)
print("Running bench_deep_class(50000)", flush=True)
bm.bench_deep_class(50000)
print("Running bench_json_roundtrip warmup", flush=True)
for i in range(12):
    bm.bench_json_roundtrip(100)
print("Running bench_json_roundtrip(50000)", flush=True)
bm.bench_json_roundtrip(50000)
print("DONE", flush=True)
