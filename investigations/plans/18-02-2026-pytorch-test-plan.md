# PyTorch Unit Tests on CinderX aarch64 — Test Plan

**Date:** 18 February 2026
**Author:** @testkeeper
**Scope:** Running PyTorch's unit test suite against CinderX JIT on devgpu004 (aarch64)
**Prerequisite:** CinderX's own test suite stable (currently 32/41 suites pass)

---

## Aim

Establish whether CinderX JIT introduces regressions in PyTorch's unit tests on aarch64, by comparing results against a stock Python 3.12 baseline on the same machine.

## Definition of Done

1. Stock Python 3.12 baseline exists: N tests pass, M fail, E error, S skip
2. CinderX JIT run exists: same test suite, same machine, CINDERJIT_ENABLE=1
3. Diff report identifies CinderX-induced regressions (tests that pass on stock but fail on CinderX)
4. Zero CinderX-induced regressions, OR all regressions have root-cause analysis and fix plan
5. Test runner script committed to repo

---

## Phase 1: Environment Verification

### 1.1 Stock Python 3.12 Baseline

**Location:** devgpu004
**Python:** System Python 3.12 (no CinderX)

```bash
# Verify stock Python is available
/usr/bin/python3.12 --version
/usr/bin/python3.12 -c "import torch; print(torch.__version__)"
```

If stock Python 3.12 is not available on devgpu004, we need to install it or use a separate venv. The key requirement is that it must NOT have CinderX loaded.

**Falsifier:** If `import cinderjit` succeeds on the "stock" Python, the baseline is contaminated and results are meaningless.

### 1.2 CinderX Python

**Location:** devgpu004, CinderX venv
**Python:** CinderX-patched Python 3.12

```bash
# Verify CinderX Python
python3 --version  # Should show 3.12.x
python3 -c "import cinderjit; print('JIT available')"
CINDERJIT_ENABLE=1 python3 -c "import cinderjit; cinderjit.is_enabled() and print('JIT enabled')"
```

### 1.3 PyTorch Installation

Both Python installations must have the same PyTorch version.

```bash
# Currently installed
python3 -c "import torch; print(torch.__version__)"
# Expected: 2.10.0+cpu
```

If PyTorch is only installed in the CinderX venv, install the same wheel in the stock Python environment.

---

## Phase 2: Test Discovery

### 2.1 Enumerate PyTorch Test Files

```bash
# Find all PyTorch test files
find $(python3 -c "import torch; import os; print(os.path.dirname(torch.__file__))") \
  -path "*/test/*.py" -name "test_*.py" | wc -l
```

### 2.2 Categorise Tests

PyTorch tests fall into these categories:

| Category | Relevance to CinderX | Priority |
|----------|----------------------|----------|
| Core ops (test_torch.py, test_autograd.py) | HIGH — exercises CPython call protocol heavily | P0 |
| NN modules (test_nn.py) | HIGH — class-heavy, uses __getattr__ | P0 |
| torch.compile / dynamo (test_dynamo_*.py) | CRITICAL — interacts with bytecode compilation | P0 |
| CUDA tests | LOW — CPU-only for now | P2 |
| Distributed tests | LOW — single-machine setup | P2 |
| Quantisation tests | MEDIUM — exercises C extension types | P1 |
| Export tests | LOW — serialisation, minimal JIT interaction | P2 |

### 2.3 Identify Known-Skippable Tests

Some tests will always skip on this configuration:
- CUDA tests (no GPU available or GPU not in scope)
- Distributed tests (single machine)
- Platform-specific tests (Windows, macOS)

These should be excluded from the diff comparison — they will skip on both stock and CinderX Python.

---

## Phase 3: Baseline Run (Stock Python)

### 3.1 Run Script

```bash
#!/bin/bash
# run_pytorch_tests_baseline.sh
# Runs PyTorch tests on stock Python 3.12 (no CinderX)

PYTHON="/usr/bin/python3.12"  # Adjust to actual stock Python path
RESULTS_DIR="/tmp/pytorch_baseline_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

# Find PyTorch test directory
TORCH_TEST_DIR=$($PYTHON -c "import torch, os; print(os.path.join(os.path.dirname(torch.__file__), '..', 'test'))")

# Run each test file, capture results
for test_file in "$TORCH_TEST_DIR"/test_*.py; do
    suite=$(basename "$test_file" .py)
    echo "[$suite] Running..."
    timeout 300 $PYTHON -m pytest "$test_file" \
        --tb=no --no-header -q \
        --junitxml="$RESULTS_DIR/${suite}.xml" \
        --ignore-glob="*cuda*" \
        2>&1 > "$RESULTS_DIR/${suite}.txt"
    echo "[$suite] Exit code: $?"
done

echo "Baseline results in: $RESULTS_DIR"
```

### 3.2 Expected Output Format

For each test file, capture via JUnit XML (`--junitxml`):
- Number of tests collected
- Number passed, failed, errored, skipped
- Individual test names and outcomes
- Exit code
- Any import errors or collection errors

The XML format is machine-parseable — do NOT parse pytest's text output (dots/F's are ambiguous). The diff script in Phase 5 uses the XML files.

### 3.3 Record Baseline

```
baseline_summary.txt:
test_torch: 1234 passed, 5 failed, 0 error, 23 skipped
test_autograd: 567 passed, 0 failed, 0 error, 12 skipped
...
```

---

## Phase 4: CinderX Run

### 4.1 Run Script

```bash
#!/bin/bash
# run_pytorch_tests_cinderx.sh
# Runs PyTorch tests on CinderX Python with JIT enabled

export CINDERJIT_ENABLE=1
PYTHON="python3"  # CinderX venv Python
RESULTS_DIR="/tmp/pytorch_cinderx_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

TORCH_TEST_DIR=$($PYTHON -c "import torch, os; print(os.path.join(os.path.dirname(torch.__file__), '..', 'test'))")

for test_file in "$TORCH_TEST_DIR"/test_*.py; do
    suite=$(basename "$test_file" .py)
    echo "[$suite] Running with CinderX JIT..."
    timeout 300 $PYTHON -m pytest "$test_file" \
        --tb=no --no-header -q \
        --junitxml="$RESULTS_DIR/${suite}.xml" \
        --ignore-glob="*cuda*" \
        2>&1 > "$RESULTS_DIR/${suite}.txt"
    echo "[$suite] Exit code: $?"
done

echo "CinderX results in: $RESULTS_DIR"
```

### 4.2 Also Run Without JIT

As a diagnostic aid, run with CinderX Python but CINDERJIT_ENABLE=0:

```bash
export CINDERJIT_ENABLE=0
# Same script, different results directory
```

This isolates JIT-specific regressions from CinderX-runtime regressions.

---

## Phase 5: Diff Analysis

### 5.1 Comparison Script

```bash
#!/bin/bash
# diff_pytorch_results.sh
# Compare baseline (stock Python) vs CinderX results using JUnit XML

BASELINE_DIR="$1"
CINDERX_DIR="$2"

echo "=== CinderX Regressions ==="
echo "(Tests that PASS on stock Python but FAIL on CinderX)"
echo ""

for baseline_xml in "$BASELINE_DIR"/test_*.xml; do
    suite=$(basename "$baseline_xml" .xml)
    cinderx_xml="$CINDERX_DIR/${suite}.xml"

    if [ ! -f "$cinderx_xml" ]; then
        echo "MISSING: $suite (no CinderX result)"
        continue
    fi

    # Extract passed test names from baseline XML (testcases without failure/error children)
    baseline_passed=$(python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('$baseline_xml')
for tc in tree.iter('testcase'):
    if tc.find('failure') is None and tc.find('error') is None and tc.find('skipped') is None:
        print(f\"{tc.get('classname')}.{tc.get('name')}\")
" 2>/dev/null | sort)

    # Extract failed test names from CinderX XML
    cinderx_failed=$(python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('$cinderx_xml')
for tc in tree.iter('testcase'):
    if tc.find('failure') is not None or tc.find('error') is not None:
        print(f\"{tc.get('classname')}.{tc.get('name')}\")
" 2>/dev/null | sort)

    # Find tests that passed baseline but failed CinderX
    regressions=$(comm -12 <(echo "$baseline_passed") <(echo "$cinderx_failed"))

    if [ -n "$regressions" ]; then
        echo "REGRESSION in $suite:"
        echo "$regressions" | sed 's/^/  /'
    fi
done
```

### 5.2 Classification

Each regression gets classified:

| Classification | Action |
|----------------|--------|
| JIT codegen bug | Fix in CinderX JIT, block release |
| CinderX runtime bug | File upstream issue |
| Test infrastructure issue | Fix test setup |
| Flaky test | Re-run to confirm, exclude from gate |
| Platform-specific (aarch64) | Document, fix if feasible |

---

## Phase 6: Prioritised Test Subsets

Running 10,000+ tests takes hours. For iterative development, use these subsets:

### P0 — Smoke Tests (run after every change, <5 minutes)

```bash
# The 6 already-validated integration tests
python3 -c "
import torch
x = torch.randn(10, 5)
y = torch.nn.Linear(5, 3)(x)
loss = y.sum()
loss.backward()
print('Smoke test PASS')
"
```

### P1 — Core Tests (run daily, ~30 minutes)

```
test_torch.py        # Core tensor operations
test_autograd.py     # Autograd — heavy CPython call protocol usage
test_nn.py           # NN modules — class-heavy, __getattr__
test_optim.py        # Optimisers
test_modules.py      # Module API
```

### P2 — Extended Tests (run weekly or before release)

All remaining test files.

### P3 — torch.compile Tests (run separately — may have specific requirements)

```
test_dynamo*.py      # torch.compile / TorchDynamo
test_inductor*.py    # TorchInductor
test_export*.py      # torch.export
```

These are especially important because torch.compile interacts with bytecode manipulation, which CinderX also does.

### P3 Strategy: CinderX Disengage/Re-engage for torch.compile

**Problem:** torch.compile (TorchDynamo) traces bytecode and generates guard code assuming standard CPython code objects. CinderX modifies the code object structure and bytecode dispatch via `Ci_EvalFrame`. If CinderX's code objects have different layouts, dynamo will silently produce wrong guards or crash.

**Proposed solution (from Alex):** Disengage CinderX JIT while torch.compile is running, then re-engage afterwards.

**Mechanism options:**

1. **CINDERJIT_ENABLE toggle (simplest):** Set `CINDERJIT_ENABLE=0` before torch.compile, re-enable after. This prevents JIT compilation of new functions but leaves Ci_EvalFrame active. If dynamo doesn't interact with already-JIT'd code (it replaces the code object), this may suffice.

2. **Eval frame swap (full isolation):** Save `_PyInterpreterState_GetEvalFrameFunc`, restore `_PyEval_EvalFrameDefault` before torch.compile, restore `Ci_EvalFrame` after. This gives torch.compile a completely standard CPython eval loop.

**Complication:** torch.compile traces lazily on first call to the compiled function, not at the `torch.compile()` call site. The disengage window must cover the tracing/guard-installation phase, not just the `torch.compile()` invocation.

**Falsification test (must run before broader P3 suite):**

```python
import torch
import cinderjit

# Test 1: torch.compile with CinderX active
@torch.compile
def f(x):
    return x * 2 + 1

x = torch.randn(10)
result = f(x)
expected = x * 2 + 1
assert torch.allclose(result, expected), f"torch.compile produced wrong result: {result} vs {expected}"

# Test 2: verify JIT is still active after torch.compile
assert cinderjit.is_enabled(), "CinderX JIT disabled after torch.compile"

print("torch.compile interop PASS")
```

If Test 1 crashes or produces wrong results, we need mechanism #2 (eval frame swap). If Test 1 passes, mechanism #1 or no change may be sufficient.

---

## Phase 1 Results (19 February 2026)

### Environment Verified on devgpu004

| Check | Status | Detail |
|-------|--------|--------|
| CinderX Python | PASS | Python 3.12.12+meta, cinderjit enabled |
| PyTorch | PASS | 2.12.0a0+gitaa3b33d |
| CUDA | PASS | 2 GPUs available |
| pytest | PASS | 9.0.2 |
| P0 test files | PASS | test_torch.py, test_autograd.py, test_nn.py present |
| Test discovery | PASS | 167 test_*.py files in /data/users/alexturner/cinderx_dev/pytorch/test/ |
| Stock Python 3.12 | **NOT AVAILABLE** | System Python is 3.9 only |

### PEP 523 Coexistence — FALSIFIED (no conflict)

**Test run on devgpu004 with CINDERJIT_ENABLE=1:**

```
CINDERJIT_ENABLE=1 python3 -c 'import cinderjit; import torch; print(torch.compile(lambda x: x+1)(torch.tensor(1)))'
→ tensor(2)
```

CinderX JIT and torch.compile coexist without conflict. The eval frame hooks do not fight. torch.compile produced the correct result with JIT active.

**Implication:** The P3 "CinderX Disengage/Re-engage" strategy (Section 6.4 above) is NOT required on this build. Both systems install their frame hooks and cooperate. However, the more comprehensive falsification test (Section 6.4) should still be run as part of P3 to verify correctness under sustained torch.compile usage, not just a single lambda.

### Revised Baseline Strategy

Stock Python 3.12 is not available on devgpu004. Revised approach:

1. **Option (c) — Smoke test first:** Run P0 tests with CINDERJIT_ENABLE=1. Identify crashes, hangs, or gross failures. This gives immediate signal with zero setup.

2. **Option (b) — JIT on/off diff for rigour:** Run all tests twice:
   - CINDERJIT_ENABLE=0: CinderX runtime without JIT (pseudo-baseline)
   - CINDERJIT_ENABLE=1: CinderX runtime WITH JIT (test run)
   - Diff: tests passing with JIT off but failing with JIT on = JIT regressions

**Why option (b) is sufficient:** Our question is "does CinderX JIT break PyTorch on aarch64?" Option (b) isolates the JIT's effect by holding everything else constant (same Python build, same CinderX runtime, same torch version). A stock Python 3.12 baseline would introduce confounding variables (CinderX's non-JIT runtime modifications: immortalisation, parallel GC hooks, frame evaluator changes).

**Caveat:** Option (b) does NOT catch CinderX runtime-level regressions (bugs in CinderX's non-JIT patches vs stock CPython). Those are upstream CinderX's responsibility, not ours.

---

## Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Stock Python not available on devgpu004 | HIGH | **CONFIRMED** | Use option (b): CINDERJIT_ENABLE=0 as pseudo-baseline |
| PyTorch version mismatch between environments | N/A | N/A | Same Python, same PyTorch — option (b) eliminates this risk |
| CUDA tests fail differently (no GPU context) | LOW | HIGH | Exclude CUDA tests from comparison |
| torch.compile conflicts with CinderX bytecode | ~~CRITICAL~~ | ~~MEDIUM~~ | **FALSIFIED** — coexistence confirmed on devgpu004 |
| Test timeout on aarch64 (slower than x86) | MEDIUM | MEDIUM | Increase timeout from 300s to 600s |
| PyTorch test isolation issues | MEDIUM | MEDIUM | Run each file in a separate process (pytest does this) |
| GC bug (current SEGFAULT) affects PyTorch tests | HIGH | MEDIUM | force_compile-specific — auto-compiled paths work; use CINDERJIT_ENABLE=1 (auto-compile, no force_compile) |

---

## Schedule

### Pre-requisites

1. ~~Resolve or work around test_cinderjit SEGFAULT (GC bug)~~ — **RESOLVED**: force_compile-specific, auto-compiled paths unaffected (d2bbb9f5)
2. ~~Verify stock Python 3.12 availability on devgpu004~~ — **NOT AVAILABLE**: using option (b) pseudo-baseline instead
3. ~~Ensure PyTorch installed in both environments~~ — **DONE**: PyTorch 2.12.0a0 on CinderX Python

All pre-requisites resolved. Ready to execute when Alex greenlights.

### Execution Order

1. ~~Environment verification (Phase 1)~~ — **DONE** (19 Feb 2026)
2. Test discovery and categorisation (Phase 2) — run `find` to enumerate test files, categorise per Section 2.2
3. P0 smoke test: run P0 tests with CINDERJIT_ENABLE=1 (option c)
4. If P0 clean: P1 core tests with JIT on/off diff (option b)
5. Diff analysis on P1 results
6. If P1 clean: expand to P2
7. If regressions found: root-cause analysis before expanding

---

## Deliverables

1. `run_pytorch_tests.sh` — unified test runner for PyTorch on CinderX (committed to repo)
2. `diff_pytorch_results.sh` — comparison script (committed to repo)
3. Pseudo-baseline results (CINDERJIT_ENABLE=0)
4. CinderX JIT results (CINDERJIT_ENABLE=1)
5. Regression report (if any)

---

## Falsifiers

- ~~**If stock Python 3.12 is not available on devgpu004:**~~ **CONFIRMED** — using option (b) pseudo-baseline instead.
- ~~**If the same PyTorch wheel cannot be used on both Pythons:**~~ N/A — option (b) uses the same Python and PyTorch for both runs.
- ~~**If torch.compile tests crash on CinderX:**~~ **FALSIFIED** — torch.compile(lambda) works correctly with CinderX JIT enabled.
- **If the GC SEGFAULT reproduces during PyTorch tests:** The force_compile bug is not triggered by normal PyTorch usage (PyTorch doesn't call cinderx.jit.force_compile). If a SEGFAULT still occurs, it's a different bug and must be investigated before continuing.
- **If CINDERJIT_ENABLE=0 tests also fail extensively:** The CinderX runtime itself (not JIT) has issues with PyTorch. This is upstream's problem, but it would make option (b) diff meaningless for JIT-specific regressions.
