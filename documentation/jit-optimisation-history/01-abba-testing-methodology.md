# ABBA Testing Methodology

## The Problem

Benchmarking a JIT compiler on shared hardware is measuring a signal inside noise. The machine has other users, thermal throttling, background services, cache pollution. A naive approach — run JIT, record time, run interpreter, record time, compare — produces numbers that drift with the weather.

We observed 5-15 percentage point swings between single-shot and paired measurements on the test server. A benchmark showing 0.77x (JIT 23% slower) on one run came back at 0.99x (parity) on the next, same code, same machine. The difference was not the JIT. It was the machine.

## Why ABBA

ABBA is borrowed from experimental design in psychoacoustics, where it was invented to cancel monotonic drift in a listener's attention. The principle transfers directly: any systematic trend that increases or decreases over time — CPU frequency scaling, thermal throttling, competing workloads ramping up — cancels within each block.

The pattern for each block:

```
A  B  B  A
```

Where A is condition one (e.g. JIT) and B is condition two (e.g. interpreter). Within a single block:

- If the machine gets slower over time, A1 benefits (measured early, fast machine) and A2 suffers (measured late, slow machine). Their mean cancels the drift.
- The same happens for B1 and B2.
- The block delta (mean_A - mean_B) is therefore resistant to monotonic trends.

Over N blocks, we collect N independent deltas. The median delta, and whether the interquartile range spans zero, tell us whether the difference is real.

Simple A-then-B benchmarking is vulnerable because ALL A measurements come before ALL B measurements. Any machine state change between the two groups becomes indistinguishable from the treatment effect. ABBA interleaves the conditions so that temporal effects cancel within each block.

## How It Works in CinderX

### In-Process Mode (abba, g1, spec)

Both conditions run inside the same Python process. The ABBA engine (`run_abba()`) times each invocation with `time.perf_counter()`, which gives nanosecond-resolution monotonic time.

```python
for block in range(n_blocks):
    ta1 = time(func_a, iters)
    tb1 = time(func_b, iters)
    tb2 = time(func_b, iters)
    ta2 = time(func_a, iters)
    
    block_delta = mean(ta1, ta2) - mean(tb1, tb2)
    deltas.append(block_delta)
```

Default: 15 blocks, producing 30 measurements per condition and 15 independent deltas.

### Subprocess Mode (jit)

For JIT-vs-vanilla comparison, the two conditions cannot share a process — one needs CinderX loaded, the other must be clean CPython. Each run spawns a fresh Python subprocess:

```
Rep 1:  JIT_ON    JIT_OFF    JIT_OFF    JIT_ON
Rep 2:  JIT_ON    JIT_OFF    JIT_OFF    JIT_ON
Rep 3:  JIT_ON    JIT_OFF    JIT_OFF    JIT_ON
```

Each subprocess runs ALL benchmarks sequentially, reporting per-benchmark timings as JSON. A 2-second pause between runs allows CPU temperatures to settle.

At 3 reps, this produces 12 runs total (6 JIT_ON, 6 JIT_OFF).

### Statistical Significance

A result is **significant** when the interquartile range (IQR) of the per-block deltas does not span zero:

```python
significant = (iqr_lo > 0 and iqr_hi > 0) or (iqr_lo < 0 and iqr_hi < 0)
```

If the IQR spans zero, the measured difference cannot be distinguished from noise. This is stricter than checking the median alone — it requires that at least 75% of blocks agree on direction.

At n=3 (12 runs), outliers can dominate. The team established empirically that n>=5 is required for reliable IQR significance. Early sessions used n=3 and saw phantom gains collapse to noise at higher N.

### Speedup Calculation

```
speedup = vanilla_time / jit_time
```

- **> 1.0:** JIT is faster
- **= 1.0:** parity
- **< 1.0:** JIT is slower (regression)
- **< 0.95:** fails the 5% gate

The geomean of all per-benchmark speedups is the primary metric. It gives equal weight to each benchmark regardless of absolute runtime.

## Benchmark Parameters

### Compilation

Two modes, each answering a different question:

| Mode | How | What It Measures |
|------|-----|-----------------|
| `force` | `cinderjit.force_compile()` on specific functions | JIT code quality in isolation |
| `auto` | `cinderjit.auto()` with threshold-based compilation | Production-like behaviour including warmup cost |

**Auto-compile** is the production-relevant mode. It lets the JIT decide when to compile based on invocation count. The threshold is set to 10 (down from CPython's default of 1000) so benchmarks trigger compilation after 10 warmup calls. This allows CPython's adaptive interpreter to specialise bytecodes (BINARY_SUBSCR → BINARY_SUBSCR_DICT, etc.) before the JIT sees them.

### Warmup

Before measurement, each benchmark runs 12 warmup iterations. This serves two purposes:

1. Triggers CPython's adaptive bytecode specialisation
2. In auto-compile mode, crosses the compilation threshold so all hot functions are JIT-compiled before measurement begins

The distinction matters: force-compiling before warmup captures unspecialised bytecodes. This was the single largest methodology error discovered — it produced a 22 percentage point difference on gen_parameterised (0.77x without warmup vs 0.99x with).

### Calibrated Iteration Counts

Each benchmark has a calibrated iteration count targeting approximately 500ms of runtime. Without calibration, fast benchmarks (gen_simple at 6ms) would be drowned by slow ones (fibonacci at 6.6s), making the geomean meaningless.

```python
BENCH_CALIBRATED_ITERS = {
    "fibonacci":       7_500,
    "gen_simple":  6_100_000,
    "list_comp":   8_900_000,
    ...
}
```

Calibrated on x86_64, commit 92fec179.

## The Gate

Every benchmark must achieve a speedup ratio >= 0.95. The JIT must not be more than 5% slower than vanilla CPython on any individual workload.

This is not negotiable. A JIT that makes fibonacci 2.5x faster but list comprehensions 11% slower is shipping a regression. The gate forces the team to address losers rather than hiding them behind a good geomean.

Benchmarks violating the gate are marked with `!!` in output. Benchmarks exceeding 1.05x are marked with `**`.

## Output Format

The benchmark reports:

1. **Per-run totals**: wall-clock time for all benchmarks combined, per condition
2. **Per-benchmark speedups**: vanilla_time / jit_time for each benchmark
3. **Winners** (>1.05x), **Losers** (<0.95x), **Neutral** (0.95x-1.05x)
4. **Geomean**: geometric mean of all speedup ratios
5. **Total**: ratio of total wall-clock times (dominated by slow benchmarks; geomean is the better metric)

Example output:
```
fibonacci        2.57x **
list_comp        0.89x !!
chaos_game       1.01x
GEOMEAN: 1.23x
```

## Lessons Learned

1. **Always ABBA, never single-shot.** Single-shot gave gen_parameterised at 0.77x. ABBA gave 0.99x. The 22-point error came from comparing JIT under load against vanilla on a quieter machine.

2. **enable_specialized_opcodes() is mandatory.** Without it, the JIT compiles from generic BINARY_SUBSCR instead of BINARY_SUBSCR_DICT. 15-30% slower on generator and dict-heavy benchmarks.

3. **Warmup order matters.** force_compile BEFORE warmup captures unspecialised bytecodes. force_compile AFTER warmup captures specialised bytecodes. The difference is 5-15pp on affected benchmarks.

4. **Clean vs incremental LTO rebuilds produce different code.** A clean LTO rebuild (rm -rf build && build.sh) generates materially different native code than an incremental rebuild. The team observed a 6-point geomean difference (1.15x incremental vs 1.21x clean) from the same source code. All A/B comparisons must use the same build methodology.

5. **n=3 ABBA is insufficient for significance.** Outliers dominate at low N. Phantom gains of +19-26% collapsed to noise at n>=5. The team uses n>=5 for any result that informs a decision.

6. **The falsifier discrepancy.** Two independent measurements of the same question (exceptions benchmark performance) gave 0.83x and 1.05x — a 22-point swing. Root cause: different builds (pre/post codeExtra fix). Every falsifier must document which build and commit it ran against.
