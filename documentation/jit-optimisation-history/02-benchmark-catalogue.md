# Benchmark Catalogue

29 benchmarks in the JIT suite, each targeting a different aspect of Python execution. The question each benchmark answers is: does the JIT make this pattern faster, slower, or the same as CPython's interpreter?

Real-world Python does not look like any single benchmark. It looks like some combination of all of them. The geomean compresses that into one number.

## Compute-Heavy Benchmarks

These stress integer and float arithmetic, recursion, and loop performance. A JIT should dominate here — this is what native code generation is for.

### fibonacci

Recursive fibonacci: `fib(20)` computed 750 times.

**Algorithm:** Classic recursive descent. Each call spawns two sub-calls. fib(20) creates 21,891 function calls.

**What it tests:** Function call overhead, integer addition, recursive call stack management. No object allocation in the hot path — pure call+add+return.

**JIT relevance:** The JIT's best case. No type guards needed (arguments are always int), no attribute lookups, no object protocol. Tests whether the JIT's call convention is cheaper than CPython's CALL opcode dispatch. The 2.57x speedup (session 6) proves native call+return is substantially faster than interpreter dispatch.

**Real-world analogue:** Any recursive algorithm: tree traversals, divide-and-conquer, parser combinators. Also a proxy for any tight loop doing integer arithmetic with function calls.

### int_arith

Pure integer arithmetic in a tight loop: add, multiply, modulo.

**Algorithm:** `total += a * i + b; a = (a+1) % 127; b = (b+3) % 131` — varies both operands to prevent constant folding.

**What it tests:** BINARY_OP_ADD_INT, BINARY_OP_MULTIPLY_INT specialised opcodes. Whether the JIT can use the unboxed integer fast path (CInt64 arithmetic without PyLong boxing).

**JIT relevance:** Tests the integer unboxing pipeline: PhiUnboxing pass → LongBinaryOp → PrimitiveUnbox → native ADD/IMUL/IDIV instructions. The 1.58x speedup validates that unboxed arithmetic avoids PyLong_FromLong/PyLong_AsLongLong overhead.

**Real-world analogue:** Array index calculations, hash computations, counter loops, bitwise flag manipulation.

### float_arith

Float operations with math module calls: `sin(x) * cos(x) + sqrt(abs(x) + 1.0)`.

**Algorithm:** Each iteration does 4 C math library calls plus float multiply, add, and abs.

**What it tests:** Float boxing/unboxing overhead, C function call dispatch for math builtins. The JIT converts BinaryOp on floats to DoubleBinaryOp (native double-precision arithmetic) but still calls through to libm for transcendentals.

**JIT relevance:** Tests the float specialisation pipeline in the Simplify pass: BinaryOp → FloatBinaryOp → DoubleBinaryOp. The 1.12x speedup shows moderate benefit — the transcendental calls dominate, so the JIT's win is mainly on the arithmetic between them.

**Real-world analogue:** Scientific computing, signal processing, physics simulations. Any code mixing math.* calls with float arithmetic.

### nbody

N-body gravitational simulation: 5 bodies, pairwise force calculation, position update.

**Algorithm:** O(n^2) force computation with `sqrt(dx^2 + dy^2 + dz^2)`, mutual force application, Euler integration. Bodies stored as lists of 7 floats.

**What it tests:** Float arithmetic in nested loops, list element access (BINARY_SUBSCR_LIST), list mutation (STORE_SUBSCR_LIST_INT), math.sqrt calls.

**JIT relevance:** Tests both float specialisation and list access specialisation. The 1.43x speedup shows the JIT handles the combination well. The list-of-floats representation means every access involves BINARY_SUBSCR_LIST → float unboxing → arithmetic → float boxing → STORE_SUBSCR_LIST_INT.

**Real-world analogue:** Particle simulations, molecular dynamics, game physics. Any O(n^2) pairwise computation on structured numeric data.

### nqueens

N-queens solver: count all solutions for n=8 using recursive backtracking with bitmask representation.

**Algorithm:** Bitwise constraint propagation. `available = ((1<<n)-1) & ~(cols|diag1|diag2)` computes open positions. `bit = available & (-available)` extracts the lowest set bit.

**What it tests:** Integer bitwise operations, recursion, small-integer arithmetic. The bitmask representation avoids any object allocation in the hot path.

**JIT relevance:** Similar to fibonacci — recursive function calls with integer arithmetic. The 1.61x speedup confirms the JIT handles recursion + bitwise ops well. Tests whether GuardType on the integer arguments adds overhead (it should not, since the arguments are always int).

**Real-world analogue:** Constraint solvers, SAT solvers, combinatorial search. Any recursive algorithm with bitmask state.

### spectral_norm

Spectral norm computation: matrix-vector multiplies via list comprehensions over a 100x100 implicit matrix.

**Algorithm:** Power iteration: `v = A^T * A * u` repeated 5 times, then `sqrt(vBv/vv)`. The matrix A is computed functionally: `A(i,j) = 1/((i+j)(i+j+1)/2 + i + 1)`.

**What it tests:** List comprehensions in the inner loop, float arithmetic, generator expressions (sum with zip). The matrix-vector multiply is a comprehension: `[sum(A(i,j)*v[j] for j in range(n)) for i in range(n)]`.

**JIT relevance:** Tests comprehension frame overhead (the same issue as list_comp) plus float arithmetic. The 1.23x speedup suggests the float wins overcome the comprehension overhead.

**Real-world analogue:** Linear algebra without NumPy, data transformation pipelines using comprehensions, functional-style numeric code.

### fannkuch

Fannkuch-Redux: generate all permutations of [0..8], counting the maximum number of "pancake flips" (prefix reversals).

**Algorithm:** Heap's algorithm for permutation generation. For each permutation, repeatedly reverse the first k elements (where k = perm[0]) until perm[0] = 0.

**What it tests:** List slicing (`perm[:k+1] = perm[k::-1]`), list mutation (insert/pop), integer comparison, while-loop control flow.

**JIT relevance:** Tests list operations and loop control. The list slice reversal is the hot operation — the JIT can potentially avoid creating intermediate slice objects. The 1.14x speedup is moderate, suggesting list slice operations still involve significant CPython runtime overhead.

**Real-world analogue:** Combinatorial algorithms, sorting, any code that does heavy in-place list manipulation.

### chaos_game

Iterated function system (Sierpinski triangle): random vertex selection, midpoint computation.

**Algorithm:** Linear congruential RNG (`r = (r * 1103515245 + 12345) & 0x7FFFFFFF`), tuple indexing for vertex lookup, float midpoint: `x = (x + v[0]) / 2`.

**What it tests:** Integer bitwise operations (LCG), tuple indexing, mixed int/float arithmetic. The tuple access pattern is a proxy for small struct field access.

**JIT relevance:** Tests the interaction between integer and float arithmetic in a tight loop. The 1.01x result (neutral) suggests the JIT's overhead on tuple access roughly cancels its win on arithmetic. The LCG and modulo operations are cheap on both JIT and interpreter.

**Real-world analogue:** Monte Carlo simulations, stochastic algorithms, game loops with random state.

## Object-Oriented Benchmarks

These test attribute access, method dispatch, and class hierarchy patterns. This is where the JIT's inline caches and type guards face their hardest challenge — polymorphic code where the receiver type varies.

### richards_slots

Simplified Richards scheduler using `__slots__`: create 10 tasks as a linked list, traverse and sum priorities.

**Algorithm:** Create RichardsTask objects with id/pri/nxt/state slots. Link them. Walk the list summing priorities.

**What it tests:** LOAD_ATTR_SLOT (direct offset access), object creation, linked-list traversal. `__slots__` means attribute access bypasses `__dict__` entirely.

**JIT relevance:** Tests the JIT's fast path for slot-based attribute access. LoadAttrCached with type-version guards should resolve to a single memory load. The 1.31x speedup validates that the inline cache for slot access is effective.

**Real-world analogue:** Data class traversal, ORM model access, any code using `__slots__` for performance-critical objects.

### richards_full

Full Richards benchmark from pyperformance: task scheduler with polymorphic dispatch across 5 task types.

**Algorithm:** Operating system task scheduler simulation. 6 task types (Idle, Work, HandlerA, HandlerB, DeviceA, DeviceB) share a common _RTask base class with polymorphic `fn()` dispatch. Tasks communicate via linked-list packet queues.

**What it tests:** Polymorphic method dispatch (5+ types calling `fn()`), attribute access without `__slots__`, linked-list operations, boolean property checks. The dispatch site in `runTask()` calls `self.fn(msg, self.handle)` where self can be any task type.

**JIT relevance:** This is the polymorphic dispatch stress test. The inline cache must handle multiple receiver types at the `fn()` call site. With the IC churn detection fix (d941a26a), the JIT stops watching volatile types after 10 invalidations, preventing IC thrashing. The 1.66x speedup is the JIT's biggest non-trivial win — it shows the polymorphic IC is effective even with 5+ types.

**Real-world analogue:** Event loop dispatchers, plugin systems, any architecture with a base class and multiple implementations dispatched through a common interface.

### method_calls

Class method dispatch: Point objects with `distance_to()` and `translate()` methods.

**Algorithm:** 100 Point objects, each with x/y float slots. Inner loop calls `distance_to()` (2 subtractions, 2 multiplies, 1 sqrt) and `translate()` (object creation with 2 additions) between adjacent points.

**What it tests:** Method lookup (LOAD_METHOD + CALL), attribute access via `__slots__`, object creation, float arithmetic inside method bodies.

**JIT relevance:** Tests the combined effect of inline caching for method lookup and float specialisation inside the method body. The 1.27x speedup shows the JIT's method dispatch is faster than CPython's LOAD_METHOD + CALL sequence.

**Real-world analogue:** Geometry libraries, physics engines, any OOP code with small methods called frequently.

### nn_module

PyTorch-style neural network: `_SimpleNet` with `_Linear`, `_ReLU`, `_Sequential` layers, custom `__getattr__`/`__setattr__`.

**Algorithm:** Forward pass through a 3-layer network (Linear→ReLU→Linear→ReLU→Linear), parameter iteration, train/eval mode switching. The `_Module.__getattr__` intercepts attribute access to search `_parameters` and `_modules` dicts.

**What it tests:** Custom `__getattr__` overhead, descriptor protocol, `__setattr__` interception, generator-based `parameters()` iteration, isinstance checks.

**JIT relevance:** This was the primary regression target. Types with custom `__getattro__` bypass the inline cache fast path. The IC skip flag fix (07d176b1) taught the JIT to detect these types and skip cache population, avoiding IC pollution. Result: 0.93x → 1.04x.

**Real-world analogue:** PyTorch `nn.Module` subclasses — the single most common Python class in ML codebases. Also any framework that uses descriptor-based attribute interception (Django models, SQLAlchemy, etc.).

### deep_class_super

5-level class hierarchy: DCBase → DCLayer → DCBlock → DCNetwork → DCModel, with `super()` calls, `isinstance` checks, `repr()`.

**Algorithm:** Create a DCModel, call `forward()` (which traverses the hierarchy via `super().forward()`), check isinstance at all 5 levels, read multiple attributes from different hierarchy levels, call `train(False)`, iterate `parameters()`, call `repr()`.

**What it tests:** MRO (Method Resolution Order) traversal cost, `super()` dispatch, `isinstance()` with inheritance, attribute access across multiple `__dict__` levels, `repr()` protocol.

**JIT relevance:** Tests the per-call overhead that compounds across deep hierarchies. At 0.94x (session 6), this is the JIT's second-worst benchmark. Profiling shows the overhead is diffuse: +1.2pp in `_PyObject_Malloc`, +0.84pp in `_PyEvalFrameClearAndPop` (JIT-only frame teardown), +0.2pp in `do_super_lookup`. No single extractable fix exists.

**Real-world analogue:** Deep framework class hierarchies (PyTorch module trees, Django class-based views, complex ORM models with multiple inheritance levels).

### pytorch_cm

PyTorch-style context managers: `no_grad()`, `autocast()`, `training_mode()` (via contextlib), `ProfileScope`, nested 2-3 levels deep.

**Algorithm:** Each iteration enters/exits 4-5 context managers, including a `@contextlib.contextmanager` decorator-based one. State toggles via class variables.

**What it tests:** `__enter__`/`__exit__` dunder dispatch, contextlib generator protocol, class variable access, nested with-statement overhead.

**JIT relevance:** Tests the inline dunder dispatch optimisation (f9a95f8f) which resolves `__enter__`/`__exit__` at compile time via `LoadAttrSpecial`. The 1.32x speedup (session 6) is substantial — though part of this may be clean-rebuild LTO effect rather than our fixes.

**Real-world analogue:** PyTorch training loops (every forward pass uses `no_grad()`, `autocast()`, profiler scopes). Also database transactions, file I/O, any code using context managers in hot paths.

## Generator Benchmarks

These test the JIT's generator compilation: yield/resume machinery, generator dispatch protocol, and yield-from delegation. Generators were the JIT's worst-performing category, driving multiple sessions of optimisation.

### gen_simple

Simple integer generator: `yield i` in a for-range loop, consumed by a for loop.

**Algorithm:** `for i in range(100): yield i` — 100 yields per generator instance, outer loop creates 61,000 generator instances.

**What it tests:** Generator creation, yield/resume dispatch (GenDataFooter save/restore), FOR_ITER protocol, range iteration inside a generator.

**JIT relevance:** Tests the basic generator dispatch overhead. Early sessions showed 0.74-0.81x (JIT 19-26% slower). The G2 fast path optimisations (runtime helper splitting, LIR inline type/state checks) improved this to 1.24x. The overhead was in `JITRT_InvokeIterNext` — the C function call chain for dispatching `next()` on a JIT-compiled generator.

**Real-world analogue:** Iterator-based data processing, lazy evaluation, any generator used as a simple sequence producer.

### gen_nested

Generator with nested function calls: each yield calls a `compute(a, b)` helper.

**Algorithm:** `yield compute(i, i+1)` where `compute` does `a * b + a - b`. Tests generator dispatch PLUS function call from within a generator.

**What it tests:** Generator yield/resume combined with regular function calls inside the generator body. Whether the JIT can inline the compute() call within the generator.

**JIT relevance:** At 1.22x, slightly worse than gen_simple's 1.24x, suggesting the function call inside the generator adds marginal overhead.

**Real-world analogue:** Generators that do computation per yield (data transformation pipelines, ETL, map-style generators).

### coroutine_chain

3-stage coroutine pipeline: stage1 yields floats, stage2 multiplies by 0.99, stage3 adds 1.0.

**Algorithm:** `stage3(stage2(stage1(1000)))` — each stage is a generator consuming from the previous via `for val in source: yield f(val)`.

**What it tests:** Chained generator consumption. Three generators active simultaneously, the runtime must dispatch through each stage's `__next__` protocol on every iteration.

**JIT relevance:** Tests the overhead of generator-calling-generator. The dispatch chain is: for-loop → `__next__` on stage3 → resume → for-loop inside stage3 → `__next__` on stage2 → resume → ... three levels deep. At 1.41x, the G2 optimisations significantly helped here.

**Real-world analogue:** Unix pipe-style data processing, async middleware chains, streaming data transformations.

### yield_from

3-level yield-from delegation: `top → mid → bottom`.

**Algorithm:** `bottom` yields `range(n)`. `mid` delegates via `yield from bottom(n)`. `top` delegates via `yield from mid(n)`.

**What it tests:** The SEND_GEN / yield-from delegation protocol. Unlike coroutine_chain (which uses explicit for-loops), yield-from uses CPython's internal delegation machinery (SEND opcode).

**JIT relevance:** This was 0.66-0.80x in early sessions — the JIT's worst benchmark. The delegation protocol involves `jitgen_am_send` at each level, creating a deep C function call chain. The SEND_GEN specialisation (0489ae4d) and G2 fast paths improved it to 1.01x (neutral). The remaining structural overhead is the delegation chain depth — fixing it requires JIT-to-JIT direct resume (bypassing the C dispatch entirely).

**Real-world analogue:** asyncio coroutine delegation, iterator composition via `yield from`, recursive generators.

## Data Structure Benchmarks

These test operations on Python's built-in containers.

### dict_ops

Dictionary creation, lookup, and iteration.

**Algorithm:** Create a 100-entry dict via comprehension, iterate with `.items()`, sum values.

**What it tests:** Dict comprehension creation, BINARY_SUBSCR_DICT, `.items()` iterator protocol.

**JIT relevance:** Tests whether the JIT's dict access matches CPython's specialised BINARY_SUBSCR_DICT. At 1.05x (neutral), the JIT and interpreter are near-parity — CPython's adaptive interpreter already has an efficient dict access path.

**Real-world analogue:** Configuration lookups, JSON processing, any code that builds and queries dictionaries.

### list_comp

List comprehension: `[i * i for i in range(100)]` plus `sum()`.

**Algorithm:** Create a list via comprehension, sum it.

**What it tests:** Comprehension frame creation overhead. CPython creates a separate code object for each comprehension, which the JIT must also compile.

**JIT relevance:** At 0.89x, this is the JIT's worst benchmark. The overhead is structural: the JIT creates and destroys an eval frame for the comprehension's code object on every iteration. The interpreter's comprehension frame is lighter. Fixing this requires either inlining comprehension frames (don't create a separate code object) or the inline dispatch approach (emit the same operations the interpreter does directly in JIT code).

**Real-world analogue:** List/dict/set comprehensions in hot loops. Extremely common in Python — comprehensions are idiomatic for data transformation.

### string_ops

String manipulation: join, split, replace, case conversion.

**Algorithm:** Join 100 words, split, reverse, rejoin with different separator. Then upper/lower/replace/count.

**What it tests:** String method dispatch, C library string operations. The actual string work is done in CPython's C implementation — the JIT can only speed up the dispatch, not the operation.

**JIT relevance:** At 0.96x (neutral), confirming that string operations are dominated by C library calls that the JIT cannot accelerate.

**Real-world analogue:** Text processing, log parsing, template rendering.

### unpack_seq

Tuple and list unpacking in loops: `for a, b in pairs` and `for a, b, c in triples`.

**Algorithm:** Unpack 100 pairs and 100 triples per iteration, sum elements.

**What it tests:** UNPACK_SEQUENCE opcode, tuple element access. CPython's UNPACK_SEQUENCE is heavily optimised for 2- and 3-element tuples.

**JIT relevance:** At 1.31x, a solid win. The JIT can unpack directly to registers without the intermediate stack manipulation that the interpreter uses.

**Real-world analogue:** Multiple assignment, for-loop destructuring, returning multiple values from functions.

### json_roundtrip

JSON serialisation and deserialisation of a 50-user nested structure.

**Algorithm:** `json.dumps(data)` followed by `json.loads(s)`, repeated.

**What it tests:** C extension module performance. Both json.dumps and json.loads are implemented in C (_json module). The JIT can only speed up the Python-level loop and dict/list access around the C calls.

**JIT relevance:** At 1.00x (perfect parity), confirming that C extension module calls are identical in cost between JIT and interpreter. The benchmark measures the C module, not the JIT.

**Real-world analogue:** API serialisation/deserialisation, configuration file I/O, data interchange.

### exceptions

Exception handling with 50% miss rate: dict lookup where half the keys are missing.

**Algorithm:** `d = {i: i*2 for i in range(0, 1000, 2)}` (even keys only). Loop tries `d[i % 1000]` — half the iterations hit KeyError.

**What it tests:** try/except overhead, exception creation and handling, dict access. CPython's BINARY_SUBSCR_DICT uses `PyDict_GetItemRef` (no exception on miss) with manual KeyError. The JIT uses `PyObject_GetItem` (raises exception internally).

**JIT relevance:** At 0.97x (session 6, just above the gate), this was a persistent loser. The codeExtra inline fix (c9501aa5) eliminated a cross-.so PLT call that added per-call overhead, pushing exceptions from 0.93x to 0.97x.

**Real-world analogue:** EAFP (Easier to Ask Forgiveness than Permission) patterns, dict.get() fallbacks, any code that catches expected exceptions in hot paths.

### store_subscr

List and dict subscript store operations.

**Algorithm:** Store to list by index (`xs[idx] = i`) and dict by key (`d[idx] = i`), then read back.

**What it tests:** STORE_SUBSCR_LIST_INT and STORE_SUBSCR_DICT specialised opcodes.

**JIT relevance:** At 1.08x, a moderate win showing the JIT's specialised store paths are effective.

**Real-world analogue:** Array updates, cache population, accumulator patterns.

## Function Call Benchmarks

### func_calls

Simple function call overhead: `add3(a, b, c)` returning `a + b + c`.

**Algorithm:** Call a 3-argument function in a tight loop, summing results.

**What it tests:** CALL opcode, argument passing, return value handling. The function body is trivial — this isolates call/return overhead.

**JIT relevance:** At 1.28x, showing the JIT's call convention is substantially cheaper than the interpreter's. The JIT can inline simple functions or at minimum avoid the interpreter's opcode-dispatch overhead at call boundaries.

**Real-world analogue:** Any code that calls small helper functions frequently. The most common Python pattern.

### import_callee

Hot loop calling a function that contains `import os`.

**Algorithm:** `_callee_with_import()` does `import os; return os.sep`. Called in a tight loop.

**What it tests:** EAGER_IMPORT_NAME opcode handling. CPython caches module imports after the first one, but the import machinery still checks `sys.modules` on every call. The JIT can potentially hoist the import resolution out of the loop.

**JIT relevance:** At 1.24x, showing the JIT handles import-containing callees well. The import resolves to a dict lookup in `sys.modules` on every call.

**Real-world analogue:** Functions with lazy imports (common in large codebases to avoid circular imports), any function that accesses module-level globals.

### try_except_callee

Hot loop calling a function containing try/except.

**Algorithm:** `_callee_with_try()` does `try: return 42; except Exception: return -1`. The except path never executes.

**What it tests:** Exception handler setup overhead when exceptions are never raised. CPython must set up the exception table entry on every call, even if no exception occurs.

**JIT relevance:** At 1.46x, a strong win. The JIT's inline exception handling (fd07d181) eliminates the exception table setup for try/except blocks when the except clause matches a known type. This benchmark shows the win when exceptions are cheap because they never fire.

**Real-world analogue:** Defensive try/except wrappers, error handling in library functions, any code with try/except in a hot path where exceptions are rare.

### positional_dispatch

Keyword call-site to positional callee: `_positional_callee(a=i, b=i+1)`.

**Algorithm:** Call a function with keyword arguments that map to positional parameters.

**What it tests:** Keyword argument resolution overhead. CPython must match keyword names to parameter positions at each call site.

**JIT relevance:** At 1.24x, showing the JIT's keyword argument fast path (1d283987) effectively resolves kwargs to positional at compile time rather than per-call.

**Real-world analogue:** API functions called with keyword arguments for readability, framework method calls with named parameters.
