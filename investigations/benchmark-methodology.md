# CinderX JIT Benchmark Methodology — aarch64

**Date:** 19 February 2026
**Platform:** devgpu004 (aarch64, NVIDIA Grace, 144 cores, 1325GiB RAM)
**Branch:** fork/aarch64-jit-generators (HEAD: 433acc4b)

## Philosophy

The benchmark suite measures whether the CinderX JIT on aarch64 produces code that is competitive with vanilla CPython 3.12. The goal is not to show the JIT is faster in all cases — it is to show the JIT does not introduce unacceptable regressions while providing genuine speedups on compute-heavy workloads.

**Gate criterion:** Each benchmark must achieve a speedup ratio (vanilla_time / jit_time) >= 0.95. This means the JIT must not be more than 5% slower than vanilla on any individual benchmark.

**Primary metric:** The geometric mean of all benchmark speedup ratios. This single number captures overall JIT quality.

## ABBA Design Pattern

All measurements use the ABBA pattern to control for systematic bias on shared hardware.

### Why ABBA?

On a shared GPU server (devgpu004), performance varies due to:
- **Thermal throttling:** aarch64 cores throttle under sustained load
- **Background processes:** Other users and system services create load spikes
- **Cache effects:** Cold vs warm caches affect first measurements

Single-shot measurements (run JIT once, run vanilla once, compare) are unreliable. We observed 5-15pp swings between single-shot and paired measurements during this investigation.

### How ABBA works

For N repetitions, the pattern is:
```
Rep 1: JIT_ON, JIT_OFF, JIT_OFF, JIT_ON
Rep 2: JIT_ON, JIT_OFF, JIT_OFF, JIT_ON
...
```

Each run is a separate Python process that executes all 23 benchmarks. Between runs, a 2-second pause allows CPU temperatures to settle.

The ABBA ordering means each JIT_ON run has one JIT_OFF neighbour, controlling for temporal drift. Results are aggregated by condition and compared.

### Running the ABBA benchmark

```bash
ssh devgpu004
cd ~/local/cinderx_dev/cinderx
source ~/local/cinderx_dev/venv/bin/activate

# Run with 2 reps (default, 8 total runs)
bash cinderx_jit_benchmark.sh 2

# Run with more reps for higher confidence
bash cinderx_jit_benchmark.sh 5
```

Results are saved to `/tmp/cinderx_benchmark_YYYYMMDD_HHMMSS/` with JSON per run and a comparison script.

## Critical Methodology Requirements

### 1. enable_specialized_opcodes()

**MANDATORY.** Without this call, the JIT compiles from un-specialised bytecodes, producing significantly slower code.

```python
import cinderjit
cinderjit.enable_specialized_opcodes()  # Must call BEFORE warmup
```

**Impact:** gen_parameterised measured 0.77x without specialisation, 0.99x with it — a 22pp difference. This was the single largest methodology error discovered during this investigation.

### 2. Warmup before force_compile

The benchmark must warm up functions (20 iterations minimum) BEFORE calling `cinderjit.force_compile()`. Warmup triggers CPython's adaptive specialisation of bytecodes (BINARY_SUBSCR -> BINARY_SUBSCR_DICT, etc.). If you force_compile before warmup, the JIT compiles generic bytecodes.

```python
# Correct order:
for _ in range(20):
    bench()                          # Warmup — triggers bytecode specialisation

cinderjit.force_compile(hot_func)    # Compile AFTER specialisation
cinderjit.force_compile(bench)
```

### 3. PYTHONJIT=1, NOT PYTHONJITALL=1

Use `PYTHONJIT=1` with explicit `cinderjit.force_compile()` on specific functions.

`PYTHONJITALL=1` crashes with SIGSEGV on our aarch64 fork (pre-existing bug, not caused by our changes). The benchmark script uses force_compile on all hot functions, making PYTHONJITALL unnecessary.

### 4. Vanilla baseline

The vanilla baseline uses the system Python in isolated mode:
```bash
/usr/local/fbcode/platform010-aarch64/bin/python3.12 -I
```

The `-I` flag prevents loading site-packages (including CinderX), ensuring a clean CPython interpreter baseline.

## The 23 Benchmarks

### Generator benchmarks (6)

| Benchmark | Description | Hot functions |
|-----------|-------------|---------------|
| gen_simple | Simple integer generator | _gen_simple |
| gen_parameterised | Generator with arithmetic per yield | _gen_param |
| gen_nested | Generator calling regular function | _gen_nested, _compute_nested |
| gen_interleaved | Multiple generators advancing in lockstep | _gen_interleaved |
| coroutine_chain | 3-stage coroutine pipeline via .send() | _coro_stage, _coro_sink |
| yield_from_chain | 3-level yield-from delegation | _yf_bottom, _yf_mid, _yf_top |

### Standard pyperformance-style (9)

| Benchmark | Description | Hot functions |
|-----------|-------------|---------------|
| func_calls | Regular function call overhead | _f_add3 |
| float_arith | Float-heavy computation | (inline) |
| fibonacci | Recursive call stress test | _fib |
| nbody | N-body simulation step | (inline) |
| spectral_norm | Spectral norm computation | _spectral_A, _spectral_mul_Av/Atv/AtAv |
| chaos_game | IFS fractal generation | _Point class methods |
| richards_slots | Richards benchmark with __slots__ | _RichardsSlotTask |
| richards_full | Full Richards benchmark with classes | _RTask hierarchy |
| fannkuch | Fannkuch-Redux benchmark | _fannkuch |

### Data structure / general (8)

| Benchmark | Description | Hot functions |
|-----------|-------------|---------------|
| nqueens | N-queens solver | _nqueens_solve |
| json_roundtrip | JSON encode/decode cycle | (stdlib) |
| method_calls | Class method dispatch overhead | (inline) |
| dict_ops | Dictionary operations | (inline) |
| list_comp | List comprehension | (inline) |
| string_ops | String operations | (inline) |
| unpack_seq | Sequence unpacking | (inline) |
| exceptions | try/except with 50% miss rate | (inline) |

## Conditions Compared

### JIT_ON (CinderX + JIT)

- Python from venv with CinderX _cinderx.so on PYTHONPATH
- PYTHONJIT=1 environment variable
- cinderjit.enable_specialized_opcodes() called at startup
- All hot functions and benchmark wrappers force_compiled
- 20 warmup iterations before force_compile

### JIT_OFF (Vanilla CPython)

- System Python 3.12 in isolated mode (-I flag)
- No CinderX loaded
- Same benchmark code, same N_ITER (100,000)
- No JIT, no force_compile — pure CPython interpreter with adaptive specialisation

## Interpreting Results

### Speedup ratio

```
speedup = vanilla_time / jit_time
```

- **>1.0:** JIT is faster (good)
- **=1.0:** Parity
- **<1.0:** JIT is slower (regression)
- **<0.95:** Fails the 5% gate

### Markers in output

- `**` = JIT >5% faster (clear win)
- `!!` = JIT >5% slower (gate fail)
- No marker = within ±5% (acceptable)

### Current results (19 Feb 2026, commit 433acc4b)

**Overall: 1.08x geomean — JIT is 8% faster than vanilla.**

Gate score: 18/23 PASS. Five failures:
- gen_parameterised (0.94x) — borderline, passes in targeted ABBA
- coroutine_chain (0.95x) — borderline, right on gate threshold
- chaos_game (0.89x) — needs LICM (loop-invariant code motion)
- spectral_norm (0.89x) — needs LICM
- exceptions (0.88x) — needs dict subscript specialisation in JIT
- yield_from_chain (0.80x) — architectural limit (multi-level C call chain)

## Lessons Learned

### 1. Always use ABBA, never single-shot

Single-shot measurements gave gen_parameterised at 0.77x (wrong) vs ABBA 0.99x (correct). The 22pp error came from comparing JIT time under load against vanilla time taken earlier on a quieter machine.

### 2. enable_specialized_opcodes() is mandatory

Without it, the JIT compiles from generic BINARY_SUBSCR instead of specialised BINARY_SUBSCR_DICT. This produces 15-30% slower code on generator and dict-heavy benchmarks.

### 3. Warmup order matters

force_compile BEFORE warmup captures un-specialised bytecodes. force_compile AFTER warmup captures specialised bytecodes. The difference is measurable (5-15pp on affected benchmarks).

### 4. PYTHONJITALL=1 is broken on aarch64

Pre-existing bug. Even `print("hello")` crashes with SIGSEGV under PYTHONJITALL=1. Use PYTHONJIT=1 with explicit force_compile instead.

### 5. The exceptions benchmark measures dict access, not exception handling

Vanilla CPython's BINARY_SUBSCR_DICT uses PyDict_GetItemRef (no exception on miss) + manual KeyError creation. The JIT uses PyObject_GetItem (raises exception internally). The overhead is in generic vs specialised dict access, not in exception handling itself.
