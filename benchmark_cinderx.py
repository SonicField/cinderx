#!/usr/bin/env python3
"""Consolidated CinderX benchmark suite for aarch64.

Replaces: benchmark_abba.py, benchmark_g1_next_abba.py,
          cinderx_jit_benchmark.sh, benchmark_specialisation.sh

METHODOLOGY: All comparisons use ABBA interleaving (A, B, B, A) to
control for thermal drift and co-located workload noise.

SUBCOMMANDS:
  abba    — Builtin micro-benchmarks: JIT function vs interpreter function
            (in-process, same Python, independent function objects)
  g1      — G1 fast path: JIT caller+JIT gen vs JIT caller+interp gen
            (in-process, isolates JITRT_InvokeIterNext contribution)
  jit     — Overall JIT vs vanilla Python across many workloads
            (subprocess isolation: venv CinderX vs system Python -I)
  spec    — Specialisation ON vs OFF (enable_specialized_opcodes effect)
            (subprocess isolation: same Python, different config)
  all     — Run all of the above

COMPILE MODES:
  --compile=force  Force-compile via cinderjit.force_compile() (default)
  --compile=auto   Use cinderjit.auto() and warmup to trigger compilation

FALSIFICATION:
  - Control: run without CinderX → delta should be ~0 for in-process tests
  - IQR must not span zero for a result to be marked significant
  - Raw block deltas printed for manual drift inspection

USAGE:
  # On devgpu (aarch64) with CinderX venv:
  PYTHONJIT=1 /path/to/venv/bin/python3 benchmark_cinderx.py abba
  PYTHONJIT=1 /path/to/venv/bin/python3 benchmark_cinderx.py all
  PYTHONJIT=1 /path/to/venv/bin/python3 benchmark_cinderx.py jit --reps=3
  PYTHONJIT=1 /path/to/venv/bin/python3 benchmark_cinderx.py spec --compile=auto

  # Worker mode (used internally for subprocess-isolated benchmarks):
  python3 benchmark_cinderx.py --worker=jit --condition=on
"""

import argparse
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time


# ═══════════════════════════════════════════════════════════════════════════
# Configuration defaults
# ═══════════════════════════════════════════════════════════════════════════

ABBA_BLOCKS = 15
BENCH_ITERS = 50_000
INNER_ITERS = 100
WARMUP_ITERS = 5_000
COMPILE_THRESHOLD = 999_999_999  # Prevent auto-compilation when not wanted


# ═══════════════════════════════════════════════════════════════════════════
# CinderX helpers
# ═══════════════════════════════════════════════════════════════════════════

def init_cinderjit(compile_mode="force"):
    """Initialise CinderX JIT. Returns cinderjit module or None."""
    try:
        import cinderx
        if hasattr(cinderx, "init"):
            cinderx.init()
        import cinderjit

        if compile_mode == "auto":
            cinderjit.auto()
        else:
            # Prevent auto-compilation; we will force-compile selectively
            try:
                cinderjit.compile_after_n_calls(COMPILE_THRESHOLD)
            except (AttributeError, TypeError):
                pass

        return cinderjit
    except (ImportError, AttributeError):
        return None


def warmup_function(func, iters=None):
    """Warmup a function with small inputs."""
    iters = iters or WARMUP_ITERS
    for _ in range(iters):
        func(1)


def force_compile(func, cinderjit_mod):
    """Force JIT-compile a function. Returns True if compiled."""
    if not cinderjit_mod:
        return False
    try:
        cinderjit_mod.force_compile(func)
        return is_compiled(func, cinderjit_mod)
    except Exception:
        return False


def is_compiled(func, cinderjit_mod):
    """Check if function is JIT-compiled."""
    if not cinderjit_mod:
        return False
    try:
        return func in cinderjit_mod.get_compiled_functions()
    except Exception:
        try:
            return cinderjit_mod.is_jit_compiled(func)
        except Exception:
            return False


def enable_specialised_opcodes(cinderjit_mod):
    """Enable specialised opcodes if available."""
    if not cinderjit_mod:
        return False
    try:
        cinderjit_mod.enable_specialized_opcodes()
        return True
    except (AttributeError, Exception):
        return False


# ═══════════════════════════════════════════════════════════════════════════
# ABBA engine (shared by all subcommands)
# ═══════════════════════════════════════════════════════════════════════════

def time_one(func, n):
    """Time a single benchmark invocation. Returns seconds."""
    t0 = time.perf_counter()
    func(n)
    t1 = time.perf_counter()
    return t1 - t0


def run_abba(func_a, func_b, n_blocks, bench_iters):
    """Run ABBA interleaved comparison.

    Each block: A, B, B, A. Monotonic drift within a block cancels.

    Returns dict with raw times, deltas, median, IQR, significance.
    """
    a_times = []
    b_times = []
    deltas = []

    for _ in range(n_blocks):
        ta1 = time_one(func_a, bench_iters)
        tb1 = time_one(func_b, bench_iters)
        tb2 = time_one(func_b, bench_iters)
        ta2 = time_one(func_a, bench_iters)

        a_times.extend([ta1, ta2])
        b_times.extend([tb1, tb2])

        block_a_mean = (ta1 + ta2) / 2
        block_b_mean = (tb1 + tb2) / 2
        deltas.append(block_a_mean - block_b_mean)

    a_times.sort()
    b_times.sort()
    deltas.sort()

    median_a = statistics.median(a_times)
    median_b = statistics.median(b_times)
    median_delta = statistics.median(deltas)

    q1_idx = len(deltas) // 4
    q3_idx = 3 * len(deltas) // 4
    iqr_lo = deltas[q1_idx]
    iqr_hi = deltas[q3_idx]

    # Significant if IQR does not span zero
    significant = (iqr_lo > 0 and iqr_hi > 0) or (iqr_lo < 0 and iqr_hi < 0)

    total_calls = bench_iters * INNER_ITERS
    ns_a = median_a / total_calls * 1e9 if total_calls > 0 else 0
    ns_b = median_b / total_calls * 1e9 if total_calls > 0 else 0
    pct = (median_b - median_a) / median_b * 100 if median_b > 0 else 0

    return {
        "a_times": a_times,
        "b_times": b_times,
        "deltas": deltas,
        "median_a": median_a,
        "median_b": median_b,
        "ns_a": ns_a,
        "ns_b": ns_b,
        "median_delta": median_delta,
        "iqr_lo": iqr_lo,
        "iqr_hi": iqr_hi,
        "significant": significant,
        "pct_improvement": pct,
    }


def print_abba_results(results, labels=("A", "B")):
    """Print a table of ABBA results."""
    label_a, label_b = labels
    print(
        f"{'Benchmark':20s} {label_a + ' ns/call':>12s} {label_b + ' ns/call':>12s} "
        f"{'Improv%':>8s} {'Signif':>7s} {'IQR':>22s}"
    )
    print("-" * 85)

    for r in results:
        sig = "YES" if r["significant"] else "no"
        iqr_str = f"[{r['iqr_lo']*1e3:+.3f}, {r['iqr_hi']*1e3:+.3f}] ms"
        label = r.get("label", "?")[:20]
        print(
            f"  {label:20s} {r['ns_a']:10.1f}   {r['ns_b']:10.1f}   "
            f"{r['pct_improvement']:+6.1f}%  {sig:>7s}  {iqr_str}"
        )

    print()
    sig_count = sum(1 for r in results if r["significant"])
    print(f"Significant results: {sig_count}/{len(results)}")
    print()
    print("Interpretation:")
    print("  Signif=YES: IQR of per-block deltas does not span zero.")
    print("  Signif=no:  IQR spans zero. Cannot distinguish from noise.")
    print("  Improv%:    Positive = A faster than B. Negative = B faster.")
    print()
    print("Raw per-block deltas (ms) — inspect for drift patterns:")
    for r in results:
        deltas_ms = [f"{d*1e3:+.3f}" for d in r["deltas"]]
        label = r.get("label", "?")[:20]
        print(f"  {label:20s} [{', '.join(deltas_ms)}]")
    print()


# ═══════════════════════════════════════════════════════════════════════════
# Benchmark definitions
# ═══════════════════════════════════════════════════════════════════════════

# --- ABBA micro-benchmark targets ---

class _Obj:
    __slots__ = ("x", "y", "z")
    def __init__(self):
        self.x = 1
        self.y = 2
        self.z = 3

class _Animal:
    pass

class _Dog(_Animal):
    pass

def _gen():
    while True:
        yield 1


def make_isinstance():
    def bench(n):
        obj = _Dog()
        total = 0
        for _ in range(n):
            for _ in range(INNER_ITERS):
                total += isinstance(obj, _Animal)
        return total
    return bench, INNER_ITERS

def make_issubclass():
    def bench(n):
        total = 0
        for _ in range(n):
            for _ in range(INNER_ITERS):
                total += issubclass(_Dog, _Animal)
        return total
    return bench, INNER_ITERS

def make_hasattr():
    def bench(n):
        obj = _Obj()
        total = 0
        for _ in range(n):
            for _ in range(INNER_ITERS):
                total += hasattr(obj, "x")
        return total
    return bench, INNER_ITERS

def make_getattr_bench():
    def bench(n):
        obj = _Obj()
        total = 0
        for _ in range(n):
            for _ in range(INNER_ITERS):
                total += getattr(obj, "x")
        return total
    return bench, INNER_ITERS

def make_next_bench():
    def bench(n):
        g = _gen()
        total = 0
        for _ in range(n):
            for _ in range(INNER_ITERS):
                total += next(g)
        return total
    return bench, INNER_ITERS

def make_next_default():
    def bench(n):
        g = _gen()
        total = 0
        for _ in range(n):
            for _ in range(INNER_ITERS):
                total += next(g, 0)
        return total
    return bench, INNER_ITERS

def make_divmod_bench():
    def bench(n):
        total = 0
        for _ in range(n):
            for _ in range(INNER_ITERS):
                q, r = divmod(1000007, 37)
                total += q
        return total
    return bench, None


ABBA_BENCHMARKS = [
    ("isinstance",   make_isinstance),
    ("issubclass",   make_issubclass),
    ("hasattr",      make_hasattr),
    ("getattr",      make_getattr_bench),
    ("next",         make_next_bench),
    ("next_default", make_next_default),
    ("divmod",       make_divmod_bench),
]


# --- G1 fast path targets ---

def _gen_jit():
    """Generator function — will be JIT-compiled."""
    while True:
        yield 1

def _gen_interp():
    """Generator function — stays interpreter-only."""
    while True:
        yield 1

def make_g1_caller(gen_func):
    """Create a G1 benchmark caller. Closure variable determines gen state."""
    def bench(n):
        g = gen_func()
        total = 0
        for _ in range(n):
            for _ in range(INNER_ITERS):
                total += next(g)
        return total
    return bench


# --- JIT vs vanilla benchmark functions ---
# These are used by the subprocess worker mode.

def _fib(n):
    if n < 2:
        return n
    return _fib(n - 1) + _fib(n - 2)

class _RichardsTask:
    __slots__ = ("id", "pri", "nxt", "state")
    def __init__(self, tid, pri):
        self.id = tid
        self.pri = pri
        self.nxt = None
        self.state = 0

def _nqueens_solve(n, row=0, cols=0, diag1=0, diag2=0):
    if row == n:
        return 1
    count = 0
    available = ((1 << n) - 1) & ~(cols | diag1 | diag2)
    while available:
        bit = available & (-available)
        available ^= bit
        count += _nqueens_solve(
            n, row + 1, cols | bit,
            (diag1 | bit) << 1, (diag2 | bit) >> 1,
        )
    return count

_SPECTRAL_N = 100

def _spectral_A(i, j):
    return 1.0 / ((i + j) * (i + j + 1) // 2 + i + 1)

def _spectral_mul_Av(v):
    n = _SPECTRAL_N
    return [sum(_spectral_A(i, j) * v[j] for j in range(n)) for i in range(n)]

def _spectral_mul_Atv(v):
    n = _SPECTRAL_N
    return [sum(_spectral_A(j, i) * v[j] for j in range(n)) for i in range(n)]

def _spectral_mul_AtAv(v):
    return _spectral_mul_Atv(_spectral_mul_Av(v))


def bench_fibonacci(n_iter):
    """Recursive fibonacci — tests function call overhead."""
    total = 0
    for _ in range(n_iter // 10):
        total += _fib(20)
    return total

def bench_richards_slots(n_iter):
    """Richards scheduler with __slots__ — attribute access."""
    total = 0
    for _ in range(n_iter):
        tasks = [_RichardsTask(i, i * 10) for i in range(10)]
        for i in range(len(tasks) - 1):
            tasks[i].nxt = tasks[i + 1]
        t = tasks[0]
        while t is not None:
            total += t.pri
            t = t.nxt
    return total

def bench_nqueens(n_iter):
    """N-queens solver — recursive backtracking, bit operations."""
    total = 0
    for _ in range(n_iter // 100):
        total += _nqueens_solve(8)
    return total

def bench_spectral_norm(n_iter):
    """Spectral norm — list comprehensions, floating point."""
    total = 0.0
    for _ in range(n_iter // 1000):
        u = [1.0] * _SPECTRAL_N
        for _ in range(5):
            v = _spectral_mul_AtAv(u)
            u = _spectral_mul_AtAv(v)
        vBv = sum(ui * vi for ui, vi in zip(u, v))
        vv = sum(vi * vi for vi in v)
        total += math.sqrt(vBv / vv)
    return total

def bench_float_arith(n_iter):
    """Float arithmetic — math module, basic ops."""
    total = 0.0
    for i in range(n_iter):
        x = float(i) * 0.001
        total += math.sin(x) * math.cos(x) + math.sqrt(abs(x) + 1.0)
    return total

def bench_gen_simple(n_iter):
    """Simple generator iteration."""
    def gen(n):
        for i in range(n):
            yield i
    total = 0
    for _ in range(n_iter // 100):
        for v in gen(100):
            total += v
    return total

def bench_gen_nested(n_iter):
    """Nested generator with function calls."""
    def compute(a, b):
        return a * b + a - b
    def gen(n):
        for i in range(n):
            yield compute(i, i + 1)
    total = 0
    for _ in range(n_iter // 100):
        for v in gen(100):
            total += v
    return total

def bench_list_comp(n_iter):
    """List comprehension — creation and iteration."""
    total = 0
    for _ in range(n_iter // 100):
        xs = [i * i for i in range(100)]
        total += sum(xs)
    return total

def bench_dict_ops(n_iter):
    """Dictionary operations — creation, lookup, iteration."""
    total = 0
    for _ in range(n_iter // 100):
        d = {i: i * i for i in range(100)}
        for k, v in d.items():
            total += v
    return total

def bench_func_calls(n_iter):
    """Function call overhead — simple argument passing."""
    def add3(a, b, c):
        return a + b + c
    total = 0
    for i in range(n_iter):
        total += add3(i, i + 1, i + 2)
    return total


JIT_BENCHMARKS = [
    ("fibonacci",       bench_fibonacci),
    ("richards_slots",  bench_richards_slots),
    ("nqueens",         bench_nqueens),
    ("spectral_norm",   bench_spectral_norm),
    ("float_arith",     bench_float_arith),
    ("gen_simple",      bench_gen_simple),
    ("gen_nested",      bench_gen_nested),
    ("list_comp",       bench_list_comp),
    ("dict_ops",        bench_dict_ops),
    ("func_calls",      bench_func_calls),
]

# Functions to force-compile for JIT benchmarks
_JIT_COMPILABLE = [
    _fib, _nqueens_solve, _spectral_A, _spectral_mul_Av,
    _spectral_mul_Atv, _spectral_mul_AtAv,
]


# --- Specialisation benchmark targets ---
# Selected to exercise LOAD_ATTR_INSTANCE_VALUE, STORE_ATTR, LOAD_ATTR_MODULE

class _Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

def bench_deep_class(n_iter):
    """Deep class hierarchy — heavy instance attribute access."""
    class Base:
        def __init__(self, name):
            self.name = name
            self.training = True
        def parameters(self):
            return [v for k, v in self.__dict__.items() if isinstance(v, float)]

    class Layer(Base):
        def __init__(self, name, feat):
            Base.__init__(self, name)
            self.in_features = feat
            self.weight = 0.01 * feat
            self.bias = 0.01
        def forward(self, x):
            return x * self.weight + self.bias

    class Network(Layer):
        def __init__(self, name, feat, n=3):
            Layer.__init__(self, name, feat)
            self.layers = [Layer(f"{name}_{i}", feat) for i in range(n)]
        def forward(self, x):
            for layer in self.layers:
                x = layer.forward(x)
            return x

    total = 0.0
    for _ in range(n_iter // 100):
        net = Network("bench", 32)
        result = net.forward(1.0)
        total += result
        _ = net.training
        _ = net.in_features
    return total

def bench_attr_access(n_iter):
    """Pure attribute access — LOAD_ATTR_INSTANCE_VALUE / STORE_ATTR."""
    p = _Point(42, 99)
    total = 0
    for _ in range(n_iter):
        total += p.x + p.y
        p.x = total % 1000
    return total

def bench_module_attr(n_iter):
    """Module attribute access — LOAD_ATTR_MODULE."""
    total = 0.0
    for _ in range(n_iter):
        total += math.pi + math.e
    return total


SPEC_BENCHMARKS = [
    ("deep_class",     bench_deep_class),
    ("attr_access",    bench_attr_access),
    ("module_attr",    bench_module_attr),
    ("richards_slots", bench_richards_slots),
    ("func_calls",     bench_func_calls),
    ("list_comp",      bench_list_comp),
]


# ═══════════════════════════════════════════════════════════════════════════
# Subcommand: abba
# ═══════════════════════════════════════════════════════════════════════════

def cmd_abba(args):
    """Run ABBA micro-benchmarks: JIT function vs interpreter function."""
    print("=" * 72)
    print("ABBA Interleaved Benchmark — JIT vs Interpreter (in-process)")
    print("=" * 72)
    print(f"Python:       {sys.version}")
    print(f"ABBA_BLOCKS:  {args.blocks}")
    print(f"BENCH_ITERS:  {args.iters}")
    print(f"INNER_ITERS:  {INNER_ITERS}")
    print(f"WARMUP_ITERS: {args.warmup}")
    print(f"Compile mode: {args.compile}")
    print()

    cinderjit = init_cinderjit(args.compile)

    if not cinderjit:
        print("MODE: CONTROL (no CinderX JIT available)")
        print("A and B use identical code paths. Delta should be ~0.")
        print()
        mode = "control"
    else:
        print("MODE: JIT vs Interpreter")
        print("A = JIT-compiled function, B = interpreter-only duplicate.")
        print()
        mode = "jit_vs_interp"

    all_results = []

    for bench_name, factory in ABBA_BENCHMARKS:
        func_a, expected = factory()
        func_b, _ = factory()

        # Correctness check
        if expected is not None:
            result_a = func_a(1)
            assert result_a == expected, (
                f"{bench_name} correctness: got {result_a}, expected {expected}"
            )

        if mode == "jit_vs_interp":
            warmup_function(func_a, args.warmup)
            if args.compile == "force":
                force_compile(func_a, cinderjit)
            warmup_function(func_b, args.warmup)
            # B: warmed up but NOT force-compiled
            a_jit = is_compiled(func_a, cinderjit)
            b_jit = is_compiled(func_b, cinderjit)
            label = f"{bench_name} (A:JIT={a_jit})"
        else:
            warmup_function(func_a, args.warmup)
            warmup_function(func_b, args.warmup)
            label = f"{bench_name} (control)"

        result = run_abba(func_a, func_b, args.blocks, args.iters)
        result["label"] = label
        all_results.append(result)

    print_abba_results(all_results, labels=("JIT", "Interp"))
    print("=" * 72)


# ═══════════════════════════════════════════════════════════════════════════
# Subcommand: g1
# ═══════════════════════════════════════════════════════════════════════════

def cmd_g1(args):
    """Run G1 fast path benchmark: JIT gen vs interp gen."""
    print("=" * 72)
    print("G1 Fast Path ABBA Benchmark — JITRT_InvokeIterNext")
    print("=" * 72)
    print(f"Python:       {sys.version}")
    print(f"ABBA_BLOCKS:  {args.blocks}")
    print(f"Compile mode: {args.compile}")
    print()

    cinderjit = init_cinderjit(args.compile)

    caller_a = make_g1_caller(_gen_jit)
    caller_b = make_g1_caller(_gen_interp)

    # Verify shared code object
    same_code = caller_a.__code__ is caller_b.__code__
    print(f"Caller code objects identical: {same_code}")
    if not same_code:
        print("WARNING: callers have different code objects — bias possible.")
    print()

    # Correctness
    assert caller_a(1) == INNER_ITERS, "caller_a correctness failed"
    assert caller_b(1) == INNER_ITERS, "caller_b correctness failed"
    print("Correctness: PASS")
    print()

    if cinderjit:
        print("Compilation setup:")
        warmup_function(caller_a, args.warmup)
        warmup_function(caller_b, args.warmup)

        if args.compile == "force":
            a_ok = force_compile(caller_a, cinderjit)
            b_ok = force_compile(caller_b, cinderjit)
            g_jit_ok = force_compile(_gen_jit, cinderjit)
        else:
            a_ok = is_compiled(caller_a, cinderjit)
            b_ok = is_compiled(caller_b, cinderjit)
            g_jit_ok = is_compiled(_gen_jit, cinderjit)

        g_interp_compiled = is_compiled(_gen_interp, cinderjit)

        print(f"  caller_a (JIT gen):     {'JIT' if a_ok else 'INTERP'}")
        print(f"  caller_b (interp gen):  {'JIT' if b_ok else 'INTERP'}")
        print(f"  gen_jit:                {'JIT' if g_jit_ok else 'INTERP'}")
        print(f"  gen_interp:             {'JIT' if g_interp_compiled else 'INTERP'}")
        print()

        if a_ok and b_ok and g_jit_ok and not g_interp_compiled:
            print("Preconditions: ALL MET")
        else:
            print("Preconditions: PARTIAL — results may be unreliable")
        print()
    else:
        print("MODE: CONTROL (no CinderX)")
        warmup_function(caller_a, args.warmup)
        warmup_function(caller_b, args.warmup)
        print()

    print(f"Running {args.blocks} ABBA blocks...")
    print()

    result = run_abba(caller_a, caller_b, args.blocks, args.iters)

    print("=" * 72)
    print("RESULTS")
    print("=" * 72)
    print()
    print(f"  A (JIT gen):     {result['ns_a']:.1f} ns/call")
    print(f"  B (interp gen):  {result['ns_b']:.1f} ns/call")
    print(f"  Improvement:     {result['pct_improvement']:+.1f}%")
    print(f"  Significant:     {'YES' if result['significant'] else 'NO'}")
    print(
        f"  IQR:             [{result['iqr_lo']*1e3:+.3f}, "
        f"{result['iqr_hi']*1e3:+.3f}] ms"
    )
    print()

    if result["significant"] and result["pct_improvement"] > 0:
        print("VERDICT: G1 fast path provides a REAL speedup.")
    elif result["significant"] and result["pct_improvement"] < 0:
        print("VERDICT: G1 fast path is SLOWER (unexpected).")
    else:
        print("VERDICT: G1 fast path shows NO significant difference.")
    print()

    # Raw deltas
    deltas_ms = [f"{d*1e3:+.3f}" for d in result["deltas"]]
    print(f"Raw per-block deltas (ms): [{', '.join(deltas_ms)}]")
    print()
    print("=" * 72)


# ═══════════════════════════════════════════════════════════════════════════
# Subcommand: jit (subprocess isolation)
# ═══════════════════════════════════════════════════════════════════════════

def _run_worker(python_cmd, condition, compile_mode):
    """Run this script as a subprocess worker, return JSON results."""
    env = os.environ.copy()
    cmd = python_cmd + [
        os.path.abspath(__file__),
        f"--worker=jit",
        f"--condition={condition}",
        f"--compile={compile_mode}",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, env=env,
        )
        if result.returncode != 0:
            print(f"  Worker failed (exit {result.returncode}): {result.stderr[:200]}")
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"  Worker error: {e}")
        return None


def _worker_jit(args):
    """Worker mode: run JIT benchmarks, output JSON."""
    condition = args.condition
    compile_mode = args.compile

    cinderjit_mod = None
    if condition == "on":
        cinderjit_mod = init_cinderjit(compile_mode)
        if cinderjit_mod and compile_mode == "force":
            # Warmup for bytecode specialisation
            for _, func in JIT_BENCHMARKS:
                for _ in range(10):
                    try:
                        func(100)
                    except Exception:
                        pass
            # Force-compile
            for func in _JIT_COMPILABLE:
                try:
                    cinderjit_mod.force_compile(func)
                except Exception:
                    pass
            for _, func in JIT_BENCHMARKS:
                try:
                    cinderjit_mod.force_compile(func)
                except Exception:
                    pass
        if cinderjit_mod:
            enable_specialised_opcodes(cinderjit_mod)

    n_iter = 100_000
    n_warmup = 3
    n_measure = 5

    results = {
        "condition": condition,
        "benchmarks": {},
    }

    for name, func in JIT_BENCHMARKS:
        # Warmup
        for _ in range(n_warmup):
            func(n_iter)

        # Measure
        times = []
        for _ in range(n_measure):
            t0 = time.perf_counter_ns()
            func(n_iter)
            t1 = time.perf_counter_ns()
            times.append((t1 - t0) / 1e6)  # ms

        results["benchmarks"][name] = {
            "times_ms": times,
            "mean_ms": sum(times) / len(times),
            "min_ms": min(times),
        }

    print(json.dumps(results))


def _worker_spec(args):
    """Worker mode: run spec benchmarks, output JSON."""
    condition = args.condition
    compile_mode = args.compile

    cinderjit_mod = init_cinderjit(compile_mode)
    if cinderjit_mod and condition == "on":
        enable_specialised_opcodes(cinderjit_mod)

    if cinderjit_mod and compile_mode == "force":
        for _, func in SPEC_BENCHMARKS:
            warmup_function(func, WARMUP_ITERS)
            try:
                cinderjit_mod.force_compile(func)
            except Exception:
                pass
    else:
        for _, func in SPEC_BENCHMARKS:
            warmup_function(func, WARMUP_ITERS)

    n_iter = 100_000
    n_measure = 5

    results = {
        "condition": condition,
        "benchmarks": {},
    }

    for name, func in SPEC_BENCHMARKS:
        times = []
        for _ in range(n_measure):
            t0 = time.perf_counter_ns()
            func(n_iter)
            t1 = time.perf_counter_ns()
            times.append((t1 - t0) / 1e6)

        results["benchmarks"][name] = {
            "times_ms": times,
            "mean_ms": sum(times) / len(times),
            "min_ms": min(times),
        }

    print(json.dumps(results))


def cmd_jit(args):
    """Run JIT vs vanilla Python benchmarks (subprocess isolated)."""
    print("=" * 72)
    print("CinderX JIT vs Vanilla Python — Subprocess ABBA")
    print("=" * 72)
    print(f"Platform:     {platform.machine()}")
    print(f"Reps:         {args.reps} (= {args.reps * 4} runs, "
          f"{args.reps * 2} per condition)")
    print(f"Compile mode: {args.compile}")
    print()

    # Determine Python commands
    venv_python = os.environ.get(
        "CINDERX_PYTHON",
        os.path.join(
            os.environ.get("CINDERX_VENV", ""),
            "bin/python3",
        ),
    )
    vanilla_python = os.environ.get(
        "VANILLA_PYTHON",
        "/usr/local/fbcode/platform010-aarch64/bin/python3.12",
    )

    # Check availability
    venv_cmd = [venv_python]
    vanilla_cmd = [vanilla_python, "-I"]

    print(f"JIT ON:  {venv_python}")
    print(f"JIT OFF: {vanilla_python} -I")
    print()

    # ABBA runs
    on_results = []
    off_results = []

    run_num = 0
    for rep in range(1, args.reps + 1):
        for condition in ["on", "off", "off", "on"]:
            run_num += 1
            cmd = venv_cmd if condition == "on" else vanilla_cmd
            print(
                f"  Run {run_num}/{args.reps * 4}: "
                f"JIT_{'ON' if condition == 'on' else 'OFF'} "
                f"(rep {rep}) ... ",
                end="", flush=True,
            )

            result = _run_worker(cmd, condition, args.compile)
            if result:
                total_ms = sum(
                    b["mean_ms"] for b in result["benchmarks"].values()
                )
                print(f"{total_ms:.1f}ms total")
                if condition == "on":
                    on_results.append(result)
                else:
                    off_results.append(result)
            else:
                print("FAILED")

            time.sleep(2)  # Let CPU settle

    if not on_results or not off_results:
        print("\nERROR: Not enough results for comparison.")
        return

    # Comparison table
    print()
    print("=" * 75)
    print("CinderX JIT Performance Comparison (aarch64)")
    print("=" * 75)
    print(f"JIT ON runs:  {len(on_results)}")
    print(f"JIT OFF runs: {len(off_results)}")
    print()

    all_benchmarks = sorted(
        set().union(*(r["benchmarks"].keys() for r in on_results + off_results))
    )

    print(
        f"{'Benchmark':<22} {'Vanilla':>10} {'CinderX':>10} "
        f"{'Speedup':>9} {'Δ%':>7}"
    )
    print("-" * 65)

    total_on = 0
    total_off = 0

    for b in all_benchmarks:
        on_means = [
            r["benchmarks"][b]["mean_ms"]
            for r in on_results if b in r["benchmarks"]
        ]
        off_means = [
            r["benchmarks"][b]["mean_ms"]
            for r in off_results if b in r["benchmarks"]
        ]

        on_mean = sum(on_means) / len(on_means) if on_means else 0
        off_mean = sum(off_means) / len(off_means) if off_means else 0

        total_on += on_mean
        total_off += off_mean

        if on_mean > 0:
            speedup = off_mean / on_mean
            delta_pct = ((off_mean - on_mean) / off_mean) * 100
        else:
            speedup = 0
            delta_pct = 0

        marker = "**" if speedup > 1.05 else ("!!" if speedup < 0.95 else "  ")
        print(
            f"  {b:<20} {off_mean:>8.2f}ms {on_mean:>8.2f}ms "
            f"{speedup:>8.2f}x {delta_pct:>6.1f}% {marker}"
        )

    print("-" * 65)
    if total_on > 0:
        overall = total_off / total_on
        overall_pct = ((total_off - total_on) / total_off) * 100
        print(
            f"  {'TOTAL':<20} {total_off:>8.2f}ms {total_on:>8.2f}ms "
            f"{overall:>8.2f}x {overall_pct:>6.1f}%"
        )
    print("=" * 75)
    print()
    print("** = JIT >5% faster   !! = JIT >5% slower")
    print()


# ═══════════════════════════════════════════════════════════════════════════
# Subcommand: spec (subprocess isolation)
# ═══════════════════════════════════════════════════════════════════════════

def cmd_spec(args):
    """Run specialisation ON vs OFF benchmarks (subprocess isolated)."""
    print("=" * 72)
    print("CinderX Specialisation ON vs OFF — Subprocess ABBA")
    print("=" * 72)
    print(f"Platform:     {platform.machine()}")
    print(f"Reps:         {args.reps}")
    print(f"Compile mode: {args.compile}")
    print()

    venv_python = os.environ.get(
        "CINDERX_PYTHON",
        os.path.join(
            os.environ.get("CINDERX_VENV", ""),
            "bin/python3",
        ),
    )
    python_cmd = [venv_python]
    print(f"Python: {venv_python}")
    print()

    # Falsification: verify enable_specialized_opcodes works
    print("--- Falsification check ---")
    check_result = _run_worker(python_cmd, "on", args.compile)
    if check_result:
        print("Spec ON worker: OK")
    else:
        print("FATAL: Spec ON worker failed. Cannot run spec benchmark.")
        return

    check_result = _run_worker(python_cmd, "off", args.compile)
    if check_result:
        print("Spec OFF worker: OK")
    else:
        print("FATAL: Spec OFF worker failed.")
        return
    print()

    # ABBA runs
    on_results = []
    off_results = []

    run_num = 0
    for rep in range(1, args.reps + 1):
        for condition in ["on", "off", "off", "on"]:
            run_num += 1
            print(
                f"  Run {run_num}/{args.reps * 4}: "
                f"SPEC_{'ON' if condition == 'on' else 'OFF'} "
                f"(rep {rep}) ... ",
                end="", flush=True,
            )

            result = _run_worker(python_cmd, condition, args.compile)
            if result:
                total_ms = sum(
                    b["mean_ms"] for b in result["benchmarks"].values()
                )
                print(f"{total_ms:.1f}ms total")
                if condition == "on":
                    on_results.append(result)
                else:
                    off_results.append(result)
            else:
                print("FAILED")

            time.sleep(2)

    if not on_results or not off_results:
        print("\nERROR: Not enough results.")
        return

    # Comparison
    print()
    print("=" * 75)
    print("Specialisation Effect (aarch64)")
    print("=" * 75)
    print()

    all_benchmarks = sorted(
        set().union(*(r["benchmarks"].keys() for r in on_results + off_results))
    )

    print(
        f"{'Benchmark':<22} {'Spec OFF':>10} {'Spec ON':>10} "
        f"{'Ratio':>9} {'Δ%':>7}"
    )
    print("-" * 65)

    for b in all_benchmarks:
        on_means = [
            r["benchmarks"][b]["mean_ms"]
            for r in on_results if b in r["benchmarks"]
        ]
        off_means = [
            r["benchmarks"][b]["mean_ms"]
            for r in off_results if b in r["benchmarks"]
        ]

        on_mean = sum(on_means) / len(on_means) if on_means else 0
        off_mean = sum(off_means) / len(off_means) if off_means else 0

        if on_mean > 0:
            ratio = off_mean / on_mean
            delta_pct = ((off_mean - on_mean) / off_mean) * 100
        else:
            ratio = 0
            delta_pct = 0

        print(
            f"  {b:<20} {off_mean:>8.2f}ms {on_mean:>8.2f}ms "
            f"{ratio:>8.4f}x {delta_pct:>6.1f}%"
        )

    print("=" * 75)
    print()
    print("Ratio > 1.0 = spec ON is faster. Ratio ≈ 1.0 = neutral.")
    print()


# ═══════════════════════════════════════════════════════════════════════════
# Subcommand: all
# ═══════════════════════════════════════════════════════════════════════════

def cmd_all(args):
    """Run all benchmark suites."""
    print("Running all benchmark suites...")
    print()

    cmd_abba(args)
    print()
    cmd_g1(args)
    print()
    cmd_jit(args)
    print()
    cmd_spec(args)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Consolidated CinderX benchmark suite for aarch64.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  benchmark_cinderx.py abba              # Builtin micro-benchmarks
  benchmark_cinderx.py g1                # G1 fast path
  benchmark_cinderx.py jit --reps=3      # JIT vs vanilla (3 ABBA cycles)
  benchmark_cinderx.py spec --compile=auto  # Spec ON vs OFF, auto-compile
  benchmark_cinderx.py all               # Run everything

Environment variables:
  CINDERX_PYTHON   Path to CinderX venv Python (default: $CINDERX_VENV/bin/python3)
  CINDERX_VENV     Path to CinderX venv directory
  VANILLA_PYTHON   Path to vanilla Python (default: system python3.12)
""",
    )

    # Worker mode (internal use for subprocess isolation)
    parser.add_argument(
        "--worker", choices=["jit", "spec"],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--condition", choices=["on", "off"],
        help=argparse.SUPPRESS,
    )

    # Common options
    parser.add_argument(
        "--compile", choices=["force", "auto"], default="force",
        help="Compile mode: force (force_compile) or auto (warmup-driven)",
    )
    parser.add_argument(
        "--blocks", type=int, default=ABBA_BLOCKS,
        help=f"Number of ABBA blocks for in-process tests (default: {ABBA_BLOCKS})",
    )
    parser.add_argument(
        "--iters", type=int, default=BENCH_ITERS,
        help=f"Iterations per measurement (default: {BENCH_ITERS})",
    )
    parser.add_argument(
        "--warmup", type=int, default=WARMUP_ITERS,
        help=f"Warmup iterations (default: {WARMUP_ITERS})",
    )
    parser.add_argument(
        "--reps", type=int, default=2,
        help="ABBA repetitions for subprocess tests (default: 2)",
    )

    # Subcommand (positional, optional — worker mode has no subcommand)
    parser.add_argument(
        "subcommand", nargs="?",
        choices=["abba", "g1", "jit", "spec", "all"],
        help="Benchmark suite to run",
    )

    args = parser.parse_args()

    # Worker mode — output JSON, no banner
    if args.worker == "jit":
        _worker_jit(args)
        return
    if args.worker == "spec":
        _worker_spec(args)
        return

    # Normal mode — require subcommand
    if not args.subcommand:
        parser.print_help()
        sys.exit(1)

    # Architecture check
    if platform.machine() != "aarch64":
        print(
            f"WARNING: Running on {platform.machine()}, "
            f"designed for aarch64. Results may differ."
        )
        print()

    dispatch = {
        "abba": cmd_abba,
        "g1": cmd_g1,
        "jit": cmd_jit,
        "spec": cmd_spec,
        "all": cmd_all,
    }

    dispatch[args.subcommand](args)


if __name__ == "__main__":
    main()
