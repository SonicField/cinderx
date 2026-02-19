"""B2 Benchmark — Measure exception handling performance in JIT."""
import time
import cinderjit

def bench_exceptions(n):
    """All hits — no exceptions raised."""
    d = {i: i for i in range(1000)}
    total = 0
    for i in range(n):
        try:
            total += d[i % 1000]
        except KeyError:
            total += 1
    return total

def bench_exceptions_miss(n):
    """50% miss — frequent exceptions."""
    d = {i: i for i in range(500)}
    total = 0
    for i in range(n):
        try:
            total += d[i % 1000]
        except KeyError:
            total += 1
    return total

cinderjit.force_compile(bench_exceptions)
cinderjit.force_compile(bench_exceptions_miss)

bench_exceptions(1000)
bench_exceptions_miss(1000)
cinderjit.get_and_clear_runtime_stats()

N = 2_000_000

print("=== Mostly hits (no exceptions) ===")
times = []
for _ in range(5):
    t0 = time.perf_counter()
    bench_exceptions(N)
    t1 = time.perf_counter()
    times.append(t1 - t0)
avg = sum(times) / len(times)
print(f"  Average: {avg:.4f}s over {N} iterations")

stats = cinderjit.get_and_clear_runtime_stats()
deopts = stats.get("deopt", [])
print(f"  Deopts: {len(deopts)}")

print("=== 50% miss (frequent exceptions) ===")
times = []
for _ in range(5):
    t0 = time.perf_counter()
    bench_exceptions_miss(N)
    t1 = time.perf_counter()
    times.append(t1 - t0)
avg = sum(times) / len(times)
print(f"  Average: {avg:.4f}s over {N} iterations")

stats = cinderjit.get_and_clear_runtime_stats()
deopts = stats.get("deopt", [])
print(f"  Deopts: {len(deopts)}")
for d in deopts:
    fn = d.get("func_fullname", "?")
    reason = d.get("reason", "?")
    count = d.get("count", "?")
    print(f"    {fn}: reason={reason} count={count}")

print("\nBenchmark complete.")
