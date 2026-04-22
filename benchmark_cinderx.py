#!/usr/bin/env python3
"""Consolidated CinderX benchmark suite.

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
  --compile=auto   Use cinderjit.auto() and warmup to trigger compilation (default)
  --compile=force  Force-compile via cinderjit.force_compile()
                   WARNING: NOT diagnostic of production performance (alexie
                   2026-Feb-22 directive); bypasses type profiling/IC
                   specialization required for representative measurements.

FALSIFICATION:
  - Control: run without CinderX → delta should be ~0 for in-process tests
  - IQR must not span zero for a result to be marked significant
  - Raw block deltas printed for manual drift inspection

USAGE:
  # With CinderX venv:
  PYTHONJIT=1 /path/to/venv/bin/python3 benchmark_cinderx.py abba
  PYTHONJIT=1 /path/to/venv/bin/python3 benchmark_cinderx.py all
  PYTHONJIT=1 /path/to/venv/bin/python3 benchmark_cinderx.py jit --reps=3
  PYTHONJIT=1 /path/to/venv/bin/python3 benchmark_cinderx.py spec --compile=auto

  # Worker mode (used internally for subprocess-isolated benchmarks):
  python3 benchmark_cinderx.py --worker=jit --condition=on
"""

import argparse
import contextlib
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
        import _cinderx
        _cinderx.install_frame_evaluator()
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


# --- Richards full (pyperformance variant) ---
# Polymorphic task dispatch, no __slots__, linked-list packets.

_RICHARDS_BUFSIZE = 4
_RICHARDS_I_IDLE = 1
_RICHARDS_I_WORK = 2
_RICHARDS_I_HANDLERA = 3
_RICHARDS_I_HANDLERB = 4
_RICHARDS_I_DEVA = 5
_RICHARDS_I_DEVB = 6
_RICHARDS_K_DEV = 1000
_RICHARDS_K_WORK = 1001


class _RPacket:
    def __init__(self, l, i, k):
        self.link = l
        self.ident = i
        self.kind = k
        self.datum = 0
        self.data = [0] * _RICHARDS_BUFSIZE

    def append_to(self, lst):
        self.link = None
        if lst is None:
            return self
        p = lst
        nxt = p.link
        while nxt is not None:
            p = nxt
            nxt = p.link
        p.link = self
        return lst


class _RTaskState:
    def __init__(self):
        self.packet_pending = True
        self.task_waiting = False
        self.task_holding = False

    def packetPending(self):
        self.packet_pending = True
        self.task_waiting = False
        self.task_holding = False
        return self

    def waiting(self):
        self.packet_pending = False
        self.task_waiting = True
        self.task_holding = False
        return self

    def running(self):
        self.packet_pending = False
        self.task_waiting = False
        self.task_holding = False
        return self

    def waitingWithPacket(self):
        self.packet_pending = True
        self.task_waiting = True
        self.task_holding = False
        return self

    def isPacketPending(self):
        return self.packet_pending

    def isTaskWaiting(self):
        return self.task_waiting

    def isTaskHolding(self):
        return self.task_holding

    def isTaskHoldingOrWaiting(self):
        return self.task_holding or (
            not self.packet_pending and self.task_waiting
        )

    def isWaitingWithPacket(self):
        return (
            self.packet_pending and self.task_waiting and not self.task_holding
        )


class _RTaskWorkArea:
    def __init__(self):
        self.taskTab = [None] * 10
        self.taskList = None
        self.holdCount = 0
        self.qpktCount = 0


class _RTask(_RTaskState):
    def __init__(self, wa, i, p, w, initialState, r):
        self.link = wa.taskList
        self.ident = i
        self.priority = p
        self.input = w
        self.packet_pending = initialState.isPacketPending()
        self.task_waiting = initialState.isTaskWaiting()
        self.task_holding = initialState.isTaskHolding()
        self.handle = r
        wa.taskList = self
        wa.taskTab[i] = self
        self._wa = wa

    def fn(self, pkt, r):
        raise NotImplementedError

    def addPacket(self, p, old):
        if self.input is None:
            self.input = p
            self.packet_pending = True
            if self.priority > old.priority:
                return self
        else:
            p.append_to(self.input)
        return old

    def runTask(self):
        if self.isWaitingWithPacket():
            msg = self.input
            self.input = msg.link
            if self.input is None:
                self.running()
            else:
                self.packetPending()
        else:
            msg = None
        return self.fn(msg, self.handle)

    def waitTask(self):
        self.task_waiting = True
        return self

    def hold(self):
        self._wa.holdCount += 1
        self.task_holding = True
        return self.link

    def release(self, i):
        t = self._wa.taskTab[i]
        t.task_holding = False
        if t.priority > self.priority:
            return t
        return self

    def qpkt(self, pkt):
        t = self._wa.taskTab[pkt.ident]
        self._wa.qpktCount += 1
        pkt.link = None
        pkt.ident = self.ident
        return t.addPacket(pkt, self)


class _RDeviceTask(_RTask):
    def fn(self, pkt, r):
        if pkt is None:
            pkt = r.pending
            if pkt is None:
                return self.waitTask()
            r.pending = None
            return self.qpkt(pkt)
        r.pending = pkt
        return self.hold()


class _RHandlerTask(_RTask):
    def fn(self, pkt, r):
        if pkt is not None:
            if pkt.kind == _RICHARDS_K_WORK:
                r.work_in = pkt.append_to(r.work_in)
            else:
                r.device_in = pkt.append_to(r.device_in)
        work = r.work_in
        if work is None:
            return self.waitTask()
        count = work.datum
        if count >= _RICHARDS_BUFSIZE:
            r.work_in = work.link
            return self.qpkt(work)
        dev = r.device_in
        if dev is None:
            return self.waitTask()
        r.device_in = dev.link
        dev.datum = work.data[count]
        work.datum = count + 1
        return self.qpkt(dev)


class _RIdleTask(_RTask):
    def __init__(self, wa, i, p, w, s, r):
        _RTask.__init__(self, wa, i, 0, None, s, r)

    def fn(self, pkt, r):
        r.count -= 1
        if r.count == 0:
            return self.hold()
        if r.control & 1 == 0:
            r.control //= 2
            return self.release(_RICHARDS_I_DEVA)
        r.control = r.control // 2 ^ 0xD008
        return self.release(_RICHARDS_I_DEVB)


class _RWorkTask(_RTask):
    def fn(self, pkt, r):
        if pkt is None:
            return self.waitTask()
        dest = (
            _RICHARDS_I_HANDLERB
            if r.destination == _RICHARDS_I_HANDLERA
            else _RICHARDS_I_HANDLERA
        )
        r.destination = dest
        pkt.ident = dest
        pkt.datum = 0
        for i in range(_RICHARDS_BUFSIZE):
            r.count += 1
            if r.count > 26:
                r.count = 1
            pkt.data[i] = ord("A") + r.count - 1
        return self.qpkt(pkt)


class _RDeviceTaskRec:
    def __init__(self):
        self.pending = None


class _RIdleTaskRec:
    def __init__(self):
        self.control = 1
        self.count = 10000


class _RHandlerTaskRec:
    def __init__(self):
        self.work_in = None
        self.device_in = None


class _RWorkerTaskRec:
    def __init__(self):
        self.destination = _RICHARDS_I_HANDLERA
        self.count = 0


def _richards_schedule(wa):
    t = wa.taskList
    while t is not None:
        if t.isTaskHoldingOrWaiting():
            t = t.link
        else:
            t = t.runTask()


def _richards_run_once(wa):
    wa.holdCount = 0
    wa.qpktCount = 0
    _RIdleTask(
        wa, _RICHARDS_I_IDLE, 1, 10000,
        _RTaskState().running(), _RIdleTaskRec(),
    )
    wkq = _RPacket(None, 0, _RICHARDS_K_WORK)
    wkq = _RPacket(wkq, 0, _RICHARDS_K_WORK)
    _RWorkTask(
        wa, _RICHARDS_I_WORK, 1000, wkq,
        _RTaskState().waitingWithPacket(), _RWorkerTaskRec(),
    )
    wkq = _RPacket(None, _RICHARDS_I_DEVA, _RICHARDS_K_DEV)
    wkq = _RPacket(wkq, _RICHARDS_I_DEVA, _RICHARDS_K_DEV)
    wkq = _RPacket(wkq, _RICHARDS_I_DEVA, _RICHARDS_K_DEV)
    _RHandlerTask(
        wa, _RICHARDS_I_HANDLERA, 2000, wkq,
        _RTaskState().waitingWithPacket(), _RHandlerTaskRec(),
    )
    wkq = _RPacket(None, _RICHARDS_I_DEVB, _RICHARDS_K_DEV)
    wkq = _RPacket(wkq, _RICHARDS_I_DEVB, _RICHARDS_K_DEV)
    wkq = _RPacket(wkq, _RICHARDS_I_DEVB, _RICHARDS_K_DEV)
    _RHandlerTask(
        wa, _RICHARDS_I_HANDLERB, 3000, wkq,
        _RTaskState().waitingWithPacket(), _RHandlerTaskRec(),
    )
    _RDeviceTask(
        wa, _RICHARDS_I_DEVA, 4000, None,
        _RTaskState().waiting(), _RDeviceTaskRec(),
    )
    _RDeviceTask(
        wa, _RICHARDS_I_DEVB, 5000, None,
        _RTaskState().waiting(), _RDeviceTaskRec(),
    )
    _richards_schedule(wa)
    return wa.holdCount == 9297 and wa.qpktCount == 23246


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


def bench_richards_full(n_iter):
    """Richards benchmark (proper pyperformance variant).
    Polymorphic task dispatch, no __slots__, linked-list packets."""
    n = max(1, n_iter // 10000)
    wa = _RTaskWorkArea()
    for _ in range(n):
        wa.taskTab = [None] * 10
        wa.taskList = None
        ok = _richards_run_once(wa)
        assert ok, f"Richards validation failed: hold={wa.holdCount} qpkt={wa.qpktCount}"
    return n

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


def bench_nbody(n_iter):
    """N-body simulation — float arithmetic, list mutation."""
    bodies = [
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 39.47841760435743],
        [4.84, -1.16, -0.10, 0.00166, 0.00769, -0.0000690, 0.000954],
        [8.34, 4.12, -0.40, -0.00276, 0.00499, 0.0000230, 0.000286],
        [12.89, -15.11, -0.22, 0.00296, 0.00237, -0.0000296, 0.0000437],
        [15.38, -25.92, 0.179, 0.00268, 0.00162, -0.0000951, 0.0000517],
    ]
    dt = 0.01
    for _ in range(n_iter // 100):
        for i in range(len(bodies)):
            bi = bodies[i]
            for j in range(i + 1, len(bodies)):
                bj = bodies[j]
                dx = bi[0] - bj[0]
                dy = bi[1] - bj[1]
                dz = bi[2] - bj[2]
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                mag = dt / (dist * dist * dist)
                bi[3] -= dx * bj[6] * mag
                bi[4] -= dy * bj[6] * mag
                bi[5] -= dz * bj[6] * mag
                bj[3] += dx * bi[6] * mag
                bj[4] += dy * bi[6] * mag
                bj[5] += dz * bi[6] * mag
        for b in bodies:
            b[0] += dt * b[3]
            b[1] += dt * b[4]
            b[2] += dt * b[5]
    return bodies[0][0]


def _fannkuch(n):
    perm = list(range(n))
    count = [0] * n
    max_flips = 0
    r = n
    while True:
        while r != 1:
            count[r - 1] = r
            r -= 1
        if perm[0] != 0 and perm[n - 1] != n - 1:
            perm2 = list(perm)
            flips = 0
            k = perm2[0]
            while k:
                perm2[:k + 1] = perm2[k::-1]
                flips += 1
                k = perm2[0]
            if flips > max_flips:
                max_flips = flips
        while r != n:
            perm.insert(r, perm.pop(0))
            count[r] -= 1
            if count[r] > 0:
                break
            r += 1
        else:
            return max_flips
    return max_flips


def bench_fannkuch(n_iter):
    """Fannkuch benchmark — permutation + reversal."""
    return _fannkuch(9)


def bench_chaos_game(n_iter):
    """Chaos game / fractal — float ops, tuple indexing."""
    vertices = [(0.0, 0.0), (1.0, 0.0), (0.5, math.sqrt(3) / 2)]
    x, y = 0.5, 0.5
    total = 0.0
    r = 0
    for _ in range(n_iter):
        r = (r * 1103515245 + 12345) & 0x7FFFFFFF
        v = vertices[r % 3]
        x = (x + v[0]) / 2
        y = (y + v[1]) / 2
        total += x + y
    return total


def _coroutine_stage1(n):
    total = 0.0
    for i in range(n):
        total += i * 0.1
        yield total

def _coroutine_stage2(source):
    for val in source:
        yield val * 0.99

def _coroutine_stage3(source):
    for val in source:
        yield val + 1.0

def bench_coroutine_chain(n_iter):
    """Generator pipeline — chained yield stages."""
    total = 0.0
    for _ in range(n_iter // 1000):
        pipeline = _coroutine_stage3(_coroutine_stage2(_coroutine_stage1(1000)))
        for val in pipeline:
            total = (total + val) % 10000
    return total


def bench_exceptions(n_iter):
    """Exception handling — try/except in hot loop."""
    d = {i: i * 2 for i in range(0, 1000, 2)}
    total = 0
    for i in range(n_iter):
        try:
            total += d[i % 1000]
        except KeyError:
            total += 1
    return total


class _MethodPoint:
    __slots__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y
    def distance_to(self, other):
        dx = self.x - other.x
        dy = self.y - other.y
        return (dx * dx + dy * dy) ** 0.5
    def translate(self, dx, dy):
        return _MethodPoint(self.x + dx, self.y + dy)


def bench_method_calls(n_iter):
    """Class method dispatch overhead."""
    points = [_MethodPoint(i * 0.1, i * 0.2) for i in range(100)]
    total = 0.0
    for _ in range(n_iter // 100):
        for i in range(len(points) - 1):
            total += points[i].distance_to(points[i + 1])
            points[i] = points[i].translate(0.01, 0.02)
    return total


def bench_string_ops(n_iter):
    """String manipulation — join, split, replace, case conversion."""
    words = [f"word_{i}" for i in range(100)]
    total = 0
    for _ in range(n_iter // 100):
        s = " ".join(words)
        parts = s.split(" ")
        s2 = "-".join(reversed(parts))
        total += len(s2)
        s3 = s.upper().lower().replace("word", "item")
        total += s3.count("item")
    return total


def bench_unpack_seq(n_iter):
    """Tuple/list unpacking in tight loops."""
    pairs = [(i, i + 1) for i in range(100)]
    triples = [(i, i + 1, i + 2) for i in range(100)]
    total = 0
    for _ in range(n_iter // 100):
        for a, b in pairs:
            total += a + b
        for a, b, c in triples:
            total += a + b + c
    return total


def bench_json_roundtrip(n_iter):
    """JSON serialisation/deserialisation."""
    data = {
        "users": [
            {"id": i, "name": f"user_{i}", "scores": [j * 1.1 for j in range(10)],
             "active": i % 2 == 0, "tags": [f"tag_{k}" for k in range(5)]}
            for i in range(50)
        ],
        "metadata": {"version": 1, "count": 50},
    }
    total = 0
    for _ in range(n_iter // 1000):
        s = json.dumps(data)
        d = json.loads(s)
        total += len(d["users"])
    return total


def bench_yield_from_chain(n_iter):
    """yield-from delegation chain."""
    def bottom(n):
        for i in range(n):
            yield i
    def mid(n):
        yield from bottom(n)
    def top(n):
        yield from mid(n)
    total = 0
    for val in top(n_iter):
        total += val
    return total


# --- Specialisation-specific benchmark targets (from benchmark_specialisation.sh) ---

class _Parameter:
    def __init__(self, data):
        self.data = data
        self.grad = None
        self.requires_grad = True


class _Module:
    def __init__(self):
        object.__setattr__(self, "_parameters", {})
        object.__setattr__(self, "_modules", {})
        object.__setattr__(self, "training", True)
    def __getattr__(self, name):
        _parameters = self.__dict__.get("_parameters", {})
        if name in _parameters:
            return _parameters[name]
        _modules = self.__dict__.get("_modules", {})
        if name in _modules:
            return _modules[name]
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
    def __setattr__(self, name, value):
        if isinstance(value, _Parameter):
            self.__dict__.setdefault("_parameters", {})[name] = value
        elif isinstance(value, _Module):
            self.__dict__.setdefault("_modules", {})[name] = value
        else:
            object.__setattr__(self, name, value)
    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)
    def parameters(self):
        for p in self._parameters.values():
            yield p
        for m in self._modules.values():
            yield from m.parameters()
    def train(self, mode=True):
        self.training = mode
        for m in self._modules.values():
            m.train(mode)
        return self
    def eval(self):
        return self.train(False)


class _Linear(_Module):
    def __init__(self, in_features, out_features, bias=True):
        _Module.__init__(self)
        self.in_features = in_features
        self.out_features = out_features
        self.weight = _Parameter(0.01 * in_features * out_features)
        if bias:
            self.bias = _Parameter(0.01 * out_features)
    def forward(self, x):
        result = x * self.weight.data
        if hasattr(self, "bias"):
            result += self.bias.data
        return result


class _ReLU(_Module):
    def forward(self, x):
        return max(0.0, x)


class _Sequential(_Module):
    def __init__(self, *modules):
        _Module.__init__(self)
        for i, module in enumerate(modules):
            self._modules[str(i)] = module
    def forward(self, x):
        for module in self._modules.values():
            x = module(x)
        return x


class _SimpleNet(_Module):
    def __init__(self):
        _Module.__init__(self)
        self.features = _Sequential(
            _Linear(64, 128), _ReLU(),
            _Linear(128, 64), _ReLU(),
        )
        self.classifier = _Linear(64, 10)
    def forward(self, x):
        x = self.features(x)
        x = self.classifier(x)
        return x


def bench_nn_module(n_iter):
    """nn.Module-style forward pass — heavy __getattr__/__setattr__."""
    model = _SimpleNet()
    model.train()
    total = 0.0
    for i in range(n_iter // 100):
        x = float(i % 100) * 0.01
        output = model(x)
        total += output % 1000.0
        for p in model.parameters():
            total += p.data * 0.0001
        if i % 100 == 0:
            if model.training:
                model.eval()
            else:
                model.train()
        total = total % 10000.0
    return total


def bench_kwargs_dispatch(n_iter):
    """Keyword argument dispatch and class init — STORE_ATTR heavy."""
    class Layer:
        def __init__(self, in_f=64, out_f=64, bias=True, dtype="float32",
                     device="cpu", requires_grad=True):
            self.in_f = in_f
            self.out_f = out_f
            self.has_bias = bias
            self.dtype = dtype
            self.device = device
            self.requires_grad = requires_grad
            self.weight = 0.01 * in_f
        def forward(self, x, *, training=True, mask=None):
            result = x * self.weight
            if self.has_bias:
                result += 0.01
            return result

    def compute(x, y, z=0.0, scale=1.0, bias=0.0, inplace=False):
        result = (x * y + z) * scale + bias
        return result if inplace else result * 1.0

    layers = [Layer(in_f=i * 8 + 8, out_f=(i + 1) * 8 + 8) for i in range(5)]
    total = 0.0
    for i in range(n_iter // 100):
        total += compute(total % 100, 0.5, z=0.1, scale=0.99, bias=0.001)
        for layer in layers:
            total = layer.forward(total % 100, training=(i % 2 == 0))
        total = total % 10000.0
    return total


def bench_context_manager(n_iter):
    """Nested context managers — __enter__/__exit__ protocol."""
    class NoGrad:
        _enabled = True
        def __enter__(self):
            self._prev = NoGrad._enabled
            NoGrad._enabled = False
            return self
        def __exit__(self, *args):
            NoGrad._enabled = self._prev
            return False
    class Autocast:
        _mode = "float32"
        def __init__(self, mode="float16"):
            self._target = mode
        def __enter__(self):
            self._prev = Autocast._mode
            Autocast._mode = self._target
            return self
        def __exit__(self, *args):
            Autocast._mode = self._prev
            return False

    model = {"training": True, "weight": 1.0, "bias": 0.0}
    total = 0.0
    for i in range(n_iter // 100):
        with NoGrad():
            total += model["weight"] * float(i % 100) + model["bias"]
        with NoGrad():
            with Autocast("float16"):
                total += total % 1000 * 0.99
        total = total % 10000.0
    return total


def bench_decorator_chain(n_iter):
    """Decorated function dispatch — functools.wraps overhead."""
    import functools
    def timer(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    def validator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    class Compute:
        @timer
        @validator
        def add(self, a, b):
            return a + b
        @timer
        @validator
        def multiply(self, a, b):
            return a * b
    comp = Compute()
    total = 0.0
    for i in range(n_iter // 10):
        total += comp.add(total % 100, float(i % 50))
        total += comp.multiply(total % 100, 0.99)
        total = total % 10000.0
    return total


def bench_dunder_protocol(n_iter):
    """Dunder method dispatch — __getattr__, __setattr__, __call__, etc."""
    class DModule:
        def __init__(self, name):
            object.__setattr__(self, "_parameters", {})
            object.__setattr__(self, "_name", name)
            for i in range(5):
                self._parameters[f"weight_{i}"] = float(i) * 0.1
        def __getattr__(self, name):
            if name in self.__dict__.get("_parameters", {}):
                return self._parameters[name]
            raise AttributeError(name)
        def __setattr__(self, name, value):
            if isinstance(value, float):
                self.__dict__.setdefault("_parameters", {})[name] = value
            else:
                object.__setattr__(self, name, value)
        def __call__(self, x):
            return x + self._parameters.get("weight_0", 0.0)
        def __repr__(self):
            return f"DModule({self._name}, params={len(self._parameters)})"
        def __bool__(self):
            return True
    model = DModule("root")
    total = 0.0
    for _ in range(n_iter // 100):
        w0 = model.weight_0
        w1 = model.weight_1
        total += w0 + w1
        model.weight_0 = w0 * 0.99
        result = model(total)
        total = result % 1000.0
        _ = repr(model)
        if model:
            total += 0.0001
    return total


class _Accumulator:
    def __init__(self):
        self.value = 0.0
        self.count = 0


def bench_store_then_use(n_iter):
    """Store-then-load pattern — isolates STORE_ATTR downstream benefit."""
    acc = _Accumulator()
    total = 0.0
    for _ in range(n_iter):
        acc.value = 1.0
        acc.count = acc.count + 1
        total += acc.value * 2.0 + acc.count
    return total


# --- Benchmarks ported from phoenix/benchmark_phoenix.py ---

def _callee_with_import():
    """Callee containing EAGER_IMPORT_NAME (import os)."""
    import os
    return os.sep

def _callee_with_try():
    """Callee containing exception handler (try/except)."""
    try:
        return 42
    except Exception:
        return -1

def bench_import_callee(n_iter):
    """Hot loop calling callee with import -- EAGER_IMPORT_NAME inlining."""
    total = 0
    for _ in range(n_iter):
        total += len(_callee_with_import())
    return total

def bench_try_except_callee(n_iter):
    """Hot loop calling callee with try/except -- exception handler inlining."""
    total = 0
    for _ in range(n_iter):
        total += _callee_with_try()
    return total

def bench_store_subscr(n_iter):
    """List and dict subscript store -- STORE_SUBSCR specialisation."""
    xs = [0] * 100
    d = {}
    total = 0
    for i in range(n_iter):
        idx = i % 100
        xs[idx] = i
        d[idx] = i
        total += xs[idx] + d[idx]
    return total

def bench_int_arith(n_iter):
    """Pure integer arithmetic -- BINARY_OP_ADD_INT / BINARY_OP_MULTIPLY_INT."""
    total = 0
    a, b = 3, 7
    for i in range(n_iter):
        total += a * i + b
        a = (a + 1) % 127
        b = (b + 3) % 131
    return total

def _positional_callee(a=0, b=0):
    return a + b

def bench_positional_dispatch(n_iter):
    """Keyword call-site to positional callee -- ResolveKwargs target."""
    total = 0
    for i in range(n_iter):
        total += _positional_callee(a=i, b=i+1)
    return total

class _DCBase:
    def __init__(self, name):
        self.name = name
        self.training = True
        self._forward_hooks = []
    def parameters(self):
        return [v for k, v in self.__dict__.items() if isinstance(v, float)]
    def train(self, mode=True):
        self.training = mode
        return self

class _DCLayer(_DCBase):
    def __init__(self, name, in_features, out_features):
        super().__init__(name)
        self.in_features = in_features
        self.out_features = out_features
        self.weight = 0.01 * in_features * out_features
        self.bias = 0.01 * out_features
    def forward(self, x):
        return x * self.weight + self.bias

class _DCBlock(_DCLayer):
    def __init__(self, name, features, num_layers=3):
        super().__init__(name, features, features)
        self.num_layers = num_layers
        self.scale = 1.0 / num_layers
        self.layers = [_DCLayer(f"{name}_sub_{i}", features, features)
                       for i in range(num_layers)]
    def forward(self, x):
        residual = x
        for layer in self.layers:
            x = layer.forward(x) * self.scale
        return x + residual

class _DCNetwork(_DCBlock):
    def __init__(self, name, features, num_blocks=2):
        super().__init__(name, features, num_layers=3)
        self.num_blocks = num_blocks
        self.blocks = [_DCBlock(f"{name}_block_{i}", features)
                       for i in range(num_blocks)]
    def forward(self, x):
        for block in self.blocks:
            x = block.forward(x)
        return x

class _DCModel(_DCNetwork):
    def __init__(self, name, features=64, num_blocks=2):
        super().__init__(name, features, num_blocks)
        self.classifier_weight = 0.01 * features
        self.classifier_bias = 0.001
    def forward(self, x):
        x = super().forward(x)
        return x * self.classifier_weight + self.classifier_bias
    def __repr__(self):
        return (f"Model({self.name}, features={self.in_features}, "
                f"blocks={self.num_blocks})")

def bench_deep_class_super(n_iter):
    """5-level class hierarchy with super() -- MRO, isinstance, repr."""
    total = 0.0
    for _ in range(n_iter // 10):
        model = _DCModel("bench", features=32, num_blocks=2)
        result = model.forward(1.0)
        total += result % 100.0
        if isinstance(model, _DCModel):
            total += 0.001
        if isinstance(model, _DCNetwork):
            total += 0.001
        if isinstance(model, _DCBlock):
            total += 0.001
        if isinstance(model, _DCLayer):
            total += 0.001
        if isinstance(model, _DCBase):
            total += 0.001
        _ = model.training
        _ = model.in_features
        _ = model.num_layers
        _ = model.num_blocks
        model.train(False)
        params = model.parameters()
        total += len(params) * 0.001
        _ = repr(model)
    return total

class _NoGrad:
    """Mimics torch.no_grad() -- sets/restores a global flag."""
    _enabled = True
    def __enter__(self):
        self._prev = _NoGrad._enabled
        _NoGrad._enabled = False
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        _NoGrad._enabled = self._prev
        return False

class _Autocast:
    """Mimics torch.autocast() -- sets/restores precision mode."""
    _mode = 'float32'
    def __init__(self, mode='float16'):
        self._target = mode
    def __enter__(self):
        self._prev = _Autocast._mode
        _Autocast._mode = self._target
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        _Autocast._mode = self._prev
        return False

class _ProfileScope:
    """Mimics profiler scope -- tracks entry/exit counts."""
    _depth = 0
    _total = 0
    def __init__(self, name):
        self._name = name
    def __enter__(self):
        _ProfileScope._depth += 1
        _ProfileScope._total += 1
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        _ProfileScope._depth -= 1
        return False

@contextlib.contextmanager
def _training_mode(model_dict, mode=True):
    """Mimics model.train()/model.eval() as context manager."""
    prev = model_dict.get('training', True)
    model_dict['training'] = mode
    try:
        yield model_dict
    finally:
        model_dict['training'] = prev

def bench_pytorch_cm(n_iter):
    """PyTorch-style context managers -- nested, contextlib, state toggle."""
    model = {'training': True, 'weight': 1.0, 'bias': 0.0}
    total = 0.0
    for i in range(n_iter // 10):
        with _NoGrad():
            total += model['weight'] * float(i % 100) + model['bias']
        with _Autocast('float16'):
            with _NoGrad():
                total += float(i % 50) * 0.5
        with _training_mode(model, False) as m:
            total += m['weight'] * 0.1
        with _ProfileScope("layer_1"):
            with _ProfileScope("layer_2"):
                total += float(i % 10) * 0.01
        total = total % 10000.0
    return total


JIT_BENCHMARKS = [
    ("fibonacci",       bench_fibonacci),
    ("richards_slots",  bench_richards_slots),
    ("richards_full",   bench_richards_full),
    ("nqueens",         bench_nqueens),
    ("spectral_norm",   bench_spectral_norm),
    ("float_arith",     bench_float_arith),
    ("gen_simple",      bench_gen_simple),
    ("gen_nested",      bench_gen_nested),
    ("list_comp",       bench_list_comp),
    ("dict_ops",        bench_dict_ops),
    ("func_calls",      bench_func_calls),
    ("nbody",           bench_nbody),
    ("fannkuch",        bench_fannkuch),
    ("chaos_game",      bench_chaos_game),
    ("coroutine_chain", bench_coroutine_chain),
    ("exceptions",      bench_exceptions),
    ("method_calls",    bench_method_calls),
    ("string_ops",      bench_string_ops),
    ("unpack_seq",      bench_unpack_seq),
    ("json_roundtrip",  bench_json_roundtrip),
    ("yield_from",      bench_yield_from_chain),
    ("nn_module",       bench_nn_module),
    ("import_callee",   bench_import_callee),
    ("try_except_callee", bench_try_except_callee),
    ("store_subscr",    bench_store_subscr),
    ("int_arith",       bench_int_arith),
    ("positional_dispatch", bench_positional_dispatch),
    ("deep_class_super", bench_deep_class_super),
    ("pytorch_cm",      bench_pytorch_cm),
]

# Calibrated iteration counts so each benchmark takes ~500ms on JIT.
# Prevents fast benchmarks (gen_simple 6ms) from being drowned by slow ones
# (fibonacci 6.6s). Geomean with rebalanced benchmarks gives equal weight
# to each workload.
# Calibrated on x86_64, commit 92fec179, RelWithDebInfo.
BENCH_CALIBRATED_ITERS = {
    "chaos_game":     1_200_000,
    "coroutine_chain":1_700_000,
    "dict_ops":       4_500_000,
    "exceptions":     2_100_000,
    "fannkuch":          87_000,
    "fibonacci":          7_500,
    "float_arith":    1_900_000,
    "func_calls":     1_800_000,
    "gen_nested":     1_600_000,
    "gen_simple":     6_100_000,
    "json_roundtrip":   840_000,
    "list_comp":      8_900_000,
    "method_calls":   1_050_000,
    "nbody":          7_800_000,
    "nn_module":      3_300_000,
    "nqueens":           78_000,
    "richards_full":     49_000,
    "richards_slots":   123_000,
    "spectral_norm":      8_000,
    "string_ops":     3_500_000,
    "unpack_seq":     5_800_000,
    "yield_from":     3_000_000,
    # Phoenix-ported benchmarks (calibrated from phoenix _PER_BENCH_ITERS)
    "import_callee":  1_700_000,
    "try_except_callee": 6_400_000,
    "store_subscr":   2_700_000,
    "int_arith":      2_500_000,
    "positional_dispatch": 3_000_000,
    "deep_class_super": 300_000,
    "pytorch_cm":     280_000,
}

# Functions to force-compile for JIT benchmarks
_JIT_COMPILABLE = [
    _coroutine_stage1, _coroutine_stage2, _coroutine_stage3,
    _fib, _nqueens_solve, _spectral_A, _spectral_mul_Av,
    _spectral_mul_Atv, _spectral_mul_AtAv, _fannkuch,
    _MethodPoint.__init__, _MethodPoint.distance_to, _MethodPoint.translate,
    _richards_schedule, _richards_run_once,
    _RPacket.__init__, _RPacket.append_to,
    _RTaskState.__init__, _RTaskState.packetPending, _RTaskState.waiting,
    _RTaskState.running, _RTaskState.waitingWithPacket,
    _RTaskState.isPacketPending, _RTaskState.isTaskWaiting,
    _RTaskState.isTaskHolding, _RTaskState.isTaskHoldingOrWaiting,
    _RTaskState.isWaitingWithPacket,
    _RTask.__init__, _RTask.addPacket, _RTask.runTask,
    _RTask.waitTask, _RTask.hold, _RTask.release, _RTask.qpkt,
    _RDeviceTask.fn, _RHandlerTask.fn,
    _RIdleTask.__init__, _RIdleTask.fn, _RWorkTask.fn,
    _callee_with_import, _callee_with_try, _positional_callee,
    _DCBase.__init__, _DCBase.parameters, _DCBase.train,
    _DCLayer.__init__, _DCLayer.forward,
    _DCBlock.__init__, _DCBlock.forward,
    _DCNetwork.__init__, _DCNetwork.forward,
    _DCModel.__init__, _DCModel.forward,
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
    ("deep_class",        bench_deep_class),
    ("attr_access",       bench_attr_access),
    ("module_attr",       bench_module_attr),
    ("richards_slots",    bench_richards_slots),
    ("func_calls",        bench_func_calls),
    ("list_comp",         bench_list_comp),
    ("nn_module",         bench_nn_module),
    ("kwargs_dispatch",   bench_kwargs_dispatch),
    ("context_manager",   bench_context_manager),
    ("decorator_chain",   bench_decorator_chain),
    ("dunder_protocol",   bench_dunder_protocol),
    ("store_then_use",    bench_store_then_use),
    ("nbody",             bench_nbody),
    ("chaos_game",        bench_chaos_game),
    ("coroutine_chain",   bench_coroutine_chain),
    ("exceptions",        bench_exceptions),
    ("method_calls",      bench_method_calls),
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

def _run_worker(python_cmd, condition, compile_mode, filter_benchmarks=None):
    """Run this script as a subprocess worker, return JSON results."""
    env = os.environ.copy()
    cmd = python_cmd + [
        os.path.abspath(__file__),
        f"--worker=jit",
        f"--condition={condition}",
        f"--compile={compile_mode}",
    ]
    if filter_benchmarks:
        cmd.append(f"--filter={','.join(filter_benchmarks)}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600, env=env,
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
    filter_set = set(args.filter.split(",")) if args.filter else None

    # Select benchmarks to run
    benchmarks = [
        (name, func) for name, func in JIT_BENCHMARKS
        if filter_set is None or name in filter_set
    ]

    cinderjit_mod = None
    if condition == "on":
        cinderjit_mod = init_cinderjit(compile_mode)
        if cinderjit_mod and compile_mode == "force":
            # Warmup for bytecode specialisation
            for _, func in benchmarks:
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
            for _, func in benchmarks:
                try:
                    cinderjit_mod.force_compile(func)
                except Exception:
                    pass
        if cinderjit_mod:
            enable_specialised_opcodes(cinderjit_mod)

    default_iter = 10_000 if filter_set else 100_000
    # Auto-compile needs heavy warmup to trigger compilation of all methods.
    # 50K iterations ensures inner methods hit the compilation threshold.
    n_warmup = 5 if (filter_set and compile_mode == "auto") else (2 if filter_set else 12)
    n_measure = 3 if filter_set else 5

    results = {
        "condition": condition,
        "benchmarks": {},
    }

    for name, func in benchmarks:
        n_iter = BENCH_CALIBRATED_ITERS.get(name, default_iter)
        warmup_iter = 50_000 if (filter_set and compile_mode == "auto") else n_iter

        # Warmup — ensure auto-compile triggers. Lower the compile threshold
        # so warmup calls trigger compilation. Threshold=10 allows CPython's
        # adaptive interpreter to specialize bytecodes before JIT compilation.
        if compile_mode == "auto" and cinderjit_mod:
            cinderjit_mod.compile_after_n_calls(10)
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


def _query_python(python_cmd, code):
    """Run a Python snippet in a subprocess and return stdout."""
    try:
        r = subprocess.run(
            python_cmd + ["-c", code],
            capture_output=True, text=True, timeout=30,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _readelf_comment(binary_path):
    """Extract .comment section from ELF binary via readelf."""
    try:
        r = subprocess.run(
            ["readelf", "-p", ".comment", binary_path],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _readelf_dwarf_producer(binary_path):
    """Extract DW_AT_producer lines from DWARF info (first 3 matches)."""
    try:
        r = subprocess.run(
            ["readelf", "--debug-dump=info", binary_path],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return ""
        lines = [l for l in r.stdout.splitlines() if "DW_AT_producer" in l]
        return "\n".join(lines[:3])
    except Exception:
        return ""


def _preflight_checks(jit_cmd, vanilla_cmd):
    """Validate benchmark invariants before running. Aborts on failure."""
    errors = []
    jit_bin = jit_cmd[0]
    vanilla_bin = vanilla_cmd[0]

    ver_code = "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    jit_ver = _query_python(jit_cmd, ver_code)
    van_ver = _query_python(vanilla_cmd, ver_code)
    if jit_ver != van_ver:
        errors.append(f"Version mismatch: JIT={jit_ver}, vanilla={van_ver}")
    else:
        print(f"  [OK] Version match: {jit_ver}")

    cinderx_code = (
        "import _cinderx; _cinderx.install_frame_evaluator(); "
        "import cinderjit; print('loaded')"
    )
    if _query_python(jit_cmd, cinderx_code) != "loaded":
        errors.append("CinderX NOT loaded in JIT python — _cinderx.so missing or broken")
    else:
        print("  [OK] CinderX loaded in JIT python")

    # Check LTO via build flags (most reliable) or binary DWARF.
    # Clang doesn't embed -flto in DWARF producer strings, so checking
    # the cmake build flags is the primary method.
    lto_detected = False
    arch = platform.machine()
    flags_path = os.path.join("scratch", f"build-{arch}",
                              "CMakeFiles", "_cinderx.dir", "flags.make")
    if os.path.exists(flags_path):
        with open(flags_path) as f:
            flags_content = f.read()
        if "-flto" in flags_content:
            lto_detected = True
            print("  [OK] LTO detected (build flags)")
        else:
            print("  [INFO] _cinderx.so built without LTO (build flags)")
    else:
        cinderx_so_for_lto = _query_python(
            jit_cmd, "import _cinderx; print(_cinderx.__file__)")
        if cinderx_so_for_lto:
            so_dwarf = _readelf_dwarf_producer(cinderx_so_for_lto)
            so_lto = ("-flto" in so_dwarf
                      or "-flto" in _readelf_comment(cinderx_so_for_lto))
            if so_lto:
                lto_detected = True
                print("  [OK] LTO detected in _cinderx.so")
            elif so_dwarf:
                print("  [INFO] _cinderx.so built without LTO")
            else:
                errors.append(
                    "LTO detection failed: no build flags and no DWARF info")
        else:
            errors.append("Cannot locate _cinderx.so for LTO check")

    jit_dwarf = _readelf_dwarf_producer(jit_bin)
    van_dwarf = _readelf_dwarf_producer(vanilla_bin)
    jit_pgo = "-fprofile-use" in jit_dwarf
    van_pgo = "-fprofile-use" in van_dwarf
    if jit_pgo or van_pgo:
        errors.append(f"PGO detected: JIT={'pgo' if jit_pgo else 'no-pgo'}, "
                       f"vanilla={'pgo' if van_pgo else 'no-pgo'}")
    else:
        print("  [OK] No PGO detected")

    jit_comment = _readelf_comment(jit_bin)
    van_comment = _readelf_comment(vanilla_bin)
    print(f"  [INFO] JIT compiler: {jit_comment.strip()[:120]}")
    print(f"  [INFO] Vanilla compiler: {van_comment.strip()[:120]}")

    cinderx_so_code = "import _cinderx; print(_cinderx.__file__)"
    so_path = _query_python(jit_cmd, cinderx_so_code)
    if so_path:
        so_comment = _readelf_comment(so_path)
        print(f"  [INFO] _cinderx.so compiler: {so_comment.strip()[:120]}")

    if errors:
        print("\n  PREFLIGHT FAILED:")
        for e in errors:
            print(f"    - {e}")
        print("\n  Aborting. Fix the above issues or set BENCHMARK_SKIP_PREFLIGHT=1 to override.")
        if not os.environ.get("BENCHMARK_SKIP_PREFLIGHT"):
            sys.exit(1)
    else:
        print("  All preflight checks passed.\n")


def _setup_benchmark_log():
    """Create a log file in benchmarks/ with systematic naming."""
    import datetime
    now = datetime.datetime.now()
    try:
        git_hash = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() or "unknown"
    except Exception:
        git_hash = "unknown"
    arch = platform.machine()
    ts = now.strftime("%Y-%m-%d_%H%M%S")
    filename = f"{ts}_{git_hash}_{arch}_abba.txt"
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmarks")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, filename)

    class TeeWriter:
        def __init__(self, original, logfile):
            self.original = original
            self.logfile = logfile
        def write(self, data):
            self.original.write(data)
            self.logfile.write(data)
        def flush(self):
            self.original.flush()
            self.logfile.flush()

    logfile = open(log_path, "w")
    tee = TeeWriter(sys.stdout, logfile)
    sys.stdout = tee
    return log_path


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

    # Python commands (resolved in main() preflight — no fallbacks)
    venv_python = os.environ.get("CINDERX_PYTHON") or os.path.join(
        os.environ.get("CINDERX_VENV", ""), "bin/python3")
    vanilla_python = os.environ["VANILLA_PYTHON"]

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
    print("CinderX JIT Performance Comparison")
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
    speedups = []

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
            speedups.append(speedup)
        else:
            speedup = 0
            delta_pct = 0

        marker = "**" if speedup > 1.05 else ("!!" if speedup < 0.95 else "  ")
        print(
            f"  {b:<20} {off_mean:>8.2f}ms {on_mean:>8.2f}ms "
            f"{speedup:>8.2f}x {delta_pct:>6.1f}% {marker}"
        )

    print("-" * 65)
    if speedups:
        geomean = math.exp(sum(math.log(s) for s in speedups) / len(speedups))
        print(
            f"  {'GEOMEAN':<20} {'':>10} {'':>10} "
            f"{geomean:>8.2f}x {(geomean - 1) * 100:>6.1f}%"
        )
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
    print("Specialisation Effect")
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

TARGET_BENCH_NAMES = {"nn_module", "richards_full"}


def cmd_target(args):
    """Run Phase 2 target benchmarks: nn_module + richards_full (subprocess ABBA)."""
    print("=" * 72)
    print("Phase 2 Target Benchmark — nn_module + richards_full")
    print("=" * 72)
    print(f"Platform:     {platform.machine()}")
    print(f"Reps:         {args.reps} (= {args.reps * 4} runs, "
          f"{args.reps * 2} per condition)")
    # Target benchmark always uses auto-compile (not force_compile)
    compile_mode = "auto"

    print(f"Compile mode: {compile_mode}")
    print()

    # Determine Python commands
    venv_python = os.environ.get(
        "CINDERX_PYTHON",
        os.path.join(
            os.environ.get("CINDERX_VENV", ""),
            "bin/python3",
        ),
    )
    vanilla_python = os.environ["VANILLA_PYTHON"]

    venv_cmd = [venv_python]
    vanilla_cmd = [vanilla_python, "-I"]

    print(f"JIT ON:  {venv_python}")
    print(f"JIT OFF: {vanilla_python} -I")
    print(f"Targets: {', '.join(sorted(TARGET_BENCH_NAMES))}")
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

            result = _run_worker(
                cmd, condition, compile_mode,
                filter_benchmarks=TARGET_BENCH_NAMES,
            )
            if result:
                target_ms = sum(
                    b["mean_ms"]
                    for name, b in result["benchmarks"].items()
                    if name in TARGET_BENCH_NAMES
                )
                print(f"{target_ms:.1f}ms")
                if condition == "on":
                    on_results.append(result)
                else:
                    off_results.append(result)
            else:
                print("FAILED")

            time.sleep(1)

    if not on_results or not off_results:
        print("\nERROR: Not enough results for comparison.")
        return

    # Comparison table (filtered to targets only)
    print()
    print("=" * 75)
    print("Phase 2 Target Performance (nn_module + richards_full)")
    print("=" * 75)
    print(f"JIT ON runs:  {len(on_results)}")
    print(f"JIT OFF runs: {len(off_results)}")
    print()

    print(
        f"{'Benchmark':<22} {'Vanilla':>10} {'CinderX':>10} "
        f"{'Speedup':>9} {'Δ%':>7}"
    )
    print("-" * 65)

    total_on = 0
    total_off = 0
    speedups = []

    for b in sorted(TARGET_BENCH_NAMES):
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
            speedups.append(speedup)
        else:
            speedup = 0
            delta_pct = 0

        marker = "**" if speedup > 1.05 else ("!!" if speedup < 0.95 else "  ")
        print(
            f"  {b:<20} {off_mean:>8.2f}ms {on_mean:>8.2f}ms "
            f"{speedup:>8.2f}x {delta_pct:>6.1f}% {marker}"
        )

    print("-" * 65)
    if speedups:
        geomean = math.exp(sum(math.log(s) for s in speedups) / len(speedups))
        print(
            f"  {'GEOMEAN':<20} {'':>10} {'':>10} "
            f"{geomean:>8.2f}x {(geomean - 1) * 100:>6.1f}%"
        )
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
        description="Consolidated CinderX benchmark suite.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  benchmark_cinderx.py abba              # Builtin micro-benchmarks
  benchmark_cinderx.py g1                # G1 fast path
  benchmark_cinderx.py jit --reps=3      # JIT vs vanilla (3 ABBA cycles)
  benchmark_cinderx.py spec --compile=auto  # Spec ON vs OFF, auto-compile
  benchmark_cinderx.py target            # Phase 2 targets: nn_module + richards_full
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
    parser.add_argument(
        "--filter", default=None,
        help=argparse.SUPPRESS,
    )

    # Common options
    parser.add_argument(
        "--compile", choices=["force", "auto"], default="auto",
        help="Compile mode: auto (warmup-driven; default per alexie "
             "2026-Feb-22 directive D-1776273371) or force (force_compile; "
             "NOT diagnostic of production)",
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
        choices=["abba", "g1", "jit", "spec", "target", "all"],
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

    # Per alexie 2026-Feb-22 binding directive (D-1776273371): force-compile
    # results are NOT diagnostic of production performance because they bypass
    # type profiling / IC specialization required by speculative dispatch.
    # Warn loudly when force mode is explicitly chosen.
    if args.compile == "force":
        print(
            "=" * 78 + "\n"
            "WARNING: --compile=force results are NOT diagnostic of production\n"
            "performance per alexie 2026-Feb-22 binding directive (D-1776273371).\n"
            "Force-compile bypasses type profiling and IC specialization required\n"
            "for representative measurements (analogous to PGO in C/C++).\n"
            "Use --compile=auto (now the default) for production-representative\n"
            "benchmarks. Force mode remains available for diagnostic isolation.\n"
            + "=" * 78,
            file=sys.stderr,
        )

    # Auto-save benchmark output
    log_path = _setup_benchmark_log()

    # Resolve python paths — no fallbacks, require explicit configuration
    venv_python = os.environ.get("CINDERX_PYTHON") or (
        os.path.join(os.environ.get("CINDERX_VENV", ""), "bin/python3")
        if os.environ.get("CINDERX_VENV") else None
    )
    vanilla_python = os.environ.get("VANILLA_PYTHON")
    if not venv_python or not vanilla_python:
        print("ERROR: Both python paths must be set explicitly. No fallbacks.")
        if not venv_python:
            print("  Missing: CINDERX_PYTHON or CINDERX_VENV")
        if not vanilla_python:
            print("  Missing: VANILLA_PYTHON")
        print("\nUsage:")
        print("  CINDERX_VENV=/path/to/venv VANILLA_PYTHON=/path/to/python3.12 \\")
        print("    python3 benchmark_cinderx.py jit --reps=3")
        sys.exit(1)
    print("Preflight checks:")
    _preflight_checks([venv_python], [vanilla_python, "-I"])

    dispatch = {
        "abba": cmd_abba,
        "g1": cmd_g1,
        "jit": cmd_jit,
        "spec": cmd_spec,
        "target": cmd_target,
        "all": cmd_all,
    }

    dispatch[args.subcommand](args)


if __name__ == "__main__":
    main()
