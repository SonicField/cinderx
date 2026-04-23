# method_calls JIT optimization plan

**Status:** DESIGN DOC. No implementation yet. Per supervisor 02:44Z direction
during alexie-hold; queued task #15 method_calls JIT-optimization plan
(alexie-authorized 09:41Z).

**Owner:** generalist (impl), testkeeper (verify), theologian (Phase 4
falsifier review post-spec endorsement).

**Compute-quiet authoring** per alexie 23:23:40Z idle-during-wait
directive + feedback_compute_quiet_definition.md.

---

## Problem statement

`bench_method_calls` (benchmark_cinderx.py:971-979) consistently shows
JIT_ON SLOWER than JIT_OFF: 0.67x in 4/19 8b74c4c2 baseline AUTO mode,
0.62x in today HEAD FORCE mode (recovered to ~baseline in HEAD AUTO per
testkeeper 00:55:53Z). Pre-existing loser per multiple ABBA records;
NOT a new regression.

The benchmark exercises:
- `_MethodPoint` class with `__slots__ = ("x", "y")` (slot descriptor
  attribute access path)
- 100-element list of points
- Inner loop calling two methods: `distance_to(other)` returning float;
  `translate(dx, dy)` returning a NEW `_MethodPoint` instance
- Each iteration: `points[i] = points[i].translate(...)` rebinding

Hot-path bytecode (per CPython 3.12 dis):
- `LOAD_FAST points` + `BINARY_SUBSCR i` (or LOAD_CONST + similar)
- `LOAD_METHOD distance_to` (or `LOAD_ATTR` on 3.12+ since LOAD_METHOD
  was unified into LOAD_ATTR with `is_meth` bit)
- `CALL_METHOD 1` / `CALL 1`
- Same shape for `translate` with 2 args
- `STORE_SUBSCR` for the rebinding

JIT-loser hypothesis (UNVERIFIED; needs empirical confirmation per
D-1776907849 #2 spec-discipline gate before any impl): one or more of:
- LOAD_METHOD/LOAD_ATTR slow path on `__slots__` descriptors
- CallMethod HIR instruction lacks IC-fast-path for bound-method shape
- Per-iteration `_MethodPoint` allocation + GC pressure exceeds JIT
  speedup on the arithmetic
- Inline-cache miss rate on dispatch site higher than expected

## Source landscape (current state)

**HIR builder (cinderx/Jit/hir/builder.cpp):**
- LOAD_METHOD handled at lines 177, 1322, 3326-area
- CALL_METHOD handled at lines 87, 1254, 2282 — emits `CallMethod` HIR
  instruction with operand count = oparg + 2 (callable + receiver +
  args)
- No specialized fast-path for `__slots__`-receiver shape visible at
  builder layer

**HIR opcodes:**
- `CallMethod` is the HIR-level call opcode emitted from CALL_METHOD
- Lowered to runtime call in codegen; falls back to CPython
  PyObject_Call shape unless guarded inline-cached

**Inline cache layer (config.h:148):**
- `attr_caches{true}` default — LOAD_ATTR cached
- `attr_cache_size{4}` — 4 inline cache slots per call site
- Only applies to LOAD_ATTR/STORE_ATTR per builder integration; CALL
  path may not benefit

## Optimization candidates

### Candidate (A): LOAD_METHOD / LOAD_ATTR fast-path for `__slots__`

`__slots__` descriptors are class-level slot wrappers (PyMemberDef-like
structures). Attribute access goes through tp_getset / tp_members which
is already C-fast on CPython side, but CinderX's HIR may not specialize
on this path.

Investigation: profile bench_method_calls under JIT to see where time
is spent. If LOAD_ATTR-on-slot is hot, add a HIR LoadSlotFastPath
instruction emitted when type guard confirms slot descriptor.

Risk: most attribute access today is dict-lookup; specializing for
__slots__ may not help non-__slots__ classes; conditional emit only.

### Candidate (B): Inline-cache for CALL_METHOD bound-method shape

CallMethod currently emits a generic call. Add inline cache that
records {receiver type, method func} on first invocation; fast-path
direct call to the cached PyCFunction / PyMethodDef on cache hit.

This is the IC-specialization path alexie repeatedly named (22:45:28Z)
as the source of recent perf gains. method_calls hot path has small
receiver-type cardinality (1: _MethodPoint); IC hit rate ~100%.

Risk: needs bound-method invariant (Method called on receiver of
expected type); guard cost + slow-path fallback. If IC adds 5ns +
dispatch saves 20ns: net 15ns/call gain, on 1.05M iterations = 16ms.
Benchmark @~500ms/iteration → small percentage but compounds with other
optimizations.

### Candidate (C): Reduce `_MethodPoint` allocation in `translate`

Per-iteration `points[i].translate(0.01, 0.02)` allocates a fresh
`_MethodPoint`. Allocation + GC + descriptor init is non-trivial.
Vanilla CPython has the same cost; JIT-loser status means JIT pays
MORE for the allocation than the interpreter, possibly via:
- Inline allocation slow path
- Frame setup cost for the constructor call
- Refcount churn on the discarded old `_MethodPoint`

Investigation: instrument allocation count + GC pressure during run.
If allocation dominates, consider:
- (C.1) Specialize `__init__` for `__slots__`-class with all-positional
  args (skip generic argument parsing)
- (C.2) Inline allocation via type's tp_alloc fast path

Risk: allocation specialization cuts across many class shapes; scope
creep risk.

### Candidate (D): Fold `translate` constructor + assignment

`points[i] = points[i].translate(0.01, 0.02)` constructs a new
_MethodPoint, then immediately replaces the old one in the list.
Possible optimization: in-place mutation instead of new-object
allocation. But this is ARGUABLY a behavioral change (different
identity) and probably out-of-scope for JIT (would require
escape-analysis the JIT doesn't have).

REJECTED unless escape-analysis lands as separate workstream.

## Recommended sequencing

1. **Empirical profiling FIRST** (testkeeper-owned per
   D-1776907849 #2 spec-discipline gate): instrument bench_method_calls
   under JIT_ON to identify dominant time-spend (LOAD_ATTR vs CALL vs
   allocation vs other). NO impl until profile lands. ~1hr.

2. **Triage candidates** based on profile:
   - If LOAD_ATTR dominant → Candidate (A)
   - If CALL dispatch dominant → Candidate (B)
   - If allocation dominant → Candidate (C)
   - If multiple → start with Candidate (B) (smallest blast radius;
     IC-specialization template already exists in codebase)

3. **Spec the chosen candidate** (theologian-owned post-profile per
   shepard 01:38:01Z + supervisor 01:30:19Z #2 spec-discipline gate):
   - Falsifier branches enumerated
   - Verification gates (gate (j), gate (k) AUTO mode, B5-yield_from no
     regression as method_calls and yield_from share dispatch path)
   - Owner triple confirmed

4. **Generalist implementation** (~2-4hr depending on candidate):
   - Candidate (A): ~2hr (HIR opcode + codegen lowering + IC)
   - Candidate (B): ~3-4hr (IC infrastructure for CallMethod)
   - Candidate (C): ~2-3hr (allocation fast-path)

5. **Testkeeper verify** + theologian Phase 4 review per standard
   pipeline.

## Verification gates

- **Gate (j):** failure count UNCHANGED (no test breaks)
- **Gate (k) AUTO mode:** method_calls geomean improves by ≥10%
  (move from 0.67x toward 0.85x or better); NO regression on other
  benchmarks (especially func_calls / yield_from / coroutine_chain
  which share dispatch path)
- **Layer 3 same-turn check:** Compile mode header verified auto
  per gatekeeper 23:54:22Z artifact + nbs-ts-passthrough wrapper per
  supervisor 01:32:14Z + testkeeper 02:07:57Z forward-discipline

## Non-goals

- NOT touching specialized opcodes config (separate workstream per
  Static Python optimization track)
- NOT changing `_MethodPoint` benchmark itself (per
  feedback_no_benchmark_workarounds.md)
- NOT in-scope for B4 v2 perfmap leak (separate workstream;
  perfmap-leak-fix doesn't affect method dispatch)

## Cross-references

- benchmark_cinderx.py:971-979 (bench_method_calls source)
- benchmark_cinderx.py:1559 (FAST_JIT_BENCHMARK_NAMES inclusion as
  representative dispatch hot-path benchmark)
- cinderx/Jit/hir/builder.cpp:2282-2313 (CALL_METHOD HIR emission)
- cinderx/Jit/config.h:148 (attr_cache config)
- alexie 22:45:28Z (IC specialization framing)
- supervisor 02:44Z (compute-quiet design-doc directive)
- D-1776907849 #2 (empirical-confirmation gate before spec endorsed
  for impl)
