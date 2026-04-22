# CinderX Scope Limitations

This file is the authoritative ledger of features that CinderX does NOT
support by team decision. Each entry names (i) the feature, (ii) why it
is out of scope, (iii) which test entries / artifacts the carve-out
covers, and (iv) the falsifier — observable trigger that flips the
feature back into scope.

**Scope-limited ≠ broken.** A scope-limited feature is one the team
deliberately does NOT support. Tests that fail under cinderx but pass
under vanilla CPython for a scope-limited feature are NOT cinderx bugs
to fix — they're documented gaps. The dual-failure rule (vanilla fails
+ cinderx fails → environmental skip) does NOT apply to scope-limited
features; this file is the separate carve-out.

**Per recursive-policy-collapse discipline:** every scope-limited
decision must ship in this artifact. Chat-only deferrals collapse
retroactively; this file is the deferral mechanism.

---

## 1. Subinterpreters

**Status:** OUT OF SCOPE.

**Why:** prior team decision (cited at top of `cinderx/TestScripts/cinder_skip_test.txt`:
"All of these tests use sub-interpreters which are incompatible with
CinderX"). Reaffirmed 2026-04-22 by supervisor in autonomous mode after
Phase 2 dual-failure verification surfaced 20 subinterpreter-related
entries as `SKIP_REJECTED_cinderx_bug` per alexie's strict dual-failure
rule (vanilla CPython 3.12.13 passes; cinderx exits 134 SIGABRT).

The strict reading would classify the 20 as cinderx bugs requiring fix.
The team's deliberate decision is to defer subinterpreter support
entirely. This carve-out documents that deferral honestly rather than
hiding it under "incompatible" framing.

**Coverage:** the 20 entries listed below remain in
`cinderx/TestScripts/cinder_skip_test.txt` with per-entry comment
annotations citing this section.

Verbatim list (from
`investigations/probes/cpython_skip_dual_failure_matrix.tsv`,
classification = `SKIP_REJECTED_cinderx_bug`, all subinterpreter-related):

```
test.test__xxsubinterpreters.*
test.test_atexit.SubinterpreterTest.*
test.test_multibytecodec.Test_IncrementalEncoder.test_subinterp
test.test_threading.SubinterpThreadingTests.*
test_interpreters
test.test_capi.test_misc.SubinterpreterTest.*
test.test_import.SubinterpImportTests.*
test.test_int.IntStrDigitLimitsTests.test_int_max_str_digits_is_per_interpreter
test.test_int.IntSubclassStrDigitLimitsTests.test_int_max_str_digits_is_per_interpreter
test.test_syslog.Test.test_subinterpreter_closelog
test.test_syslog.Test.test_subinterpreter_openlog
test.test_syslog.Test.test_subinterpreter_syslog
test.test_capi.test_misc.TestThreadState.test_gilstate_matches_current
test.test_ast.test_ast.ModuleStateTests.test_subinterpreter
test.test_import.SinglephaseInitTests.test_basic_multiple_interpreters_deleted_no_reset
test.test_import.SinglephaseInitTests.test_basic_multiple_interpreters_main_no_reset
test.test_import.SinglephaseInitTests.test_basic_multiple_interpreters_reset_each
test.test_importlib.test_util.IncompatibleExtensionModuleRestrictionsTests.test_complete_multi_phase_init_module
test.test_importlib.test_util.IncompatibleExtensionModuleRestrictionsTests.test_incomplete_multi_phase_init_module
test.test_importlib.test_util.IncompatibleExtensionModuleRestrictionsTests.test_single_phase_init_module
```

**Falsifier (when this carve-out flips to in-scope):**
- A user / production workload requires subinterpreter support
- A team member proposes investing engineering time in subinterpreter
  compatibility (large work; estimate not in current cycle)
- CPython 3.13+ subinterpreter API changes make compatibility
  significantly cheaper

Until any of those triggers fires, subinterpreter support stays out of
scope and the 20 entries stay skipped per this carve-out.

---

## 2. ARM64 architecture

**Status:** OUT OF SCOPE for current production.

**Why:** team historical decision; CinderX targets x86-64 production
deployment. ARM64 builds may exist for development but are not gated /
benchmarked / fixed-when-broken in the same way as x86-64.

**Coverage:** entries in `cinderx/TestScripts/3.12-opt-arm64-failures.txt`
(12 lines; not enumerated here — see file for current list). Tests
that fail only on ARM64 fall under this carve-out.

**Falsifier:** an ARM64 production target (e.g., a deployment platform
shifts to ARM, a customer requires ARM support); team explicit decision
to add ARM64 to the perf gate.

---

## 3. Free-threaded Python (PEP 703 / no-GIL)

**Status:** OUT OF SCOPE for current production.

**Why:** team historical decision; CinderX assumes GIL-protected
execution model in many invariants (per JIT compile guards, slab
allocation patterns). Removing the GIL would require a substantial
re-audit of the codebase.

**Coverage:** any free-threaded-Python-only test failures.

**Falsifier:** CPython makes the no-GIL build a non-experimental
default (currently Py_GIL_DISABLED is opt-in); a team member proposes
investing in no-GIL compatibility.

---

## Adding a new scope-limited feature

To add a new entry:

1. Verify the feature satisfies "deliberate non-support," NOT "broken
   feature we should fix." If unclear, default to "should fix" and add
   to triage_plan_failing_tests.md instead.
2. Append a numbered section to this file with the four required
   fields (Status / Why / Coverage / Falsifier).
3. Cross-reference from any test-skip files (`cinder_skip_test.txt`,
   `3.12-opt-arm64-failures.txt`, etc.) per-entry.
4. Land the artifact change in the same commit as the carve-out
   decision (recursive-policy-collapse — chat-only deferrals
   collapse).

## Removing a scope-limited feature (flip to in-scope)

When a falsifier fires:

1. Document the trigger in this file: "<date> — <feature> moved
   in-scope, trigger: <observable event>."
2. Add the now-in-scope test entries to triage_plan_failing_tests.md
   as new B-group items.
3. Remove the per-entry annotations from the relevant skip files; let
   the tests fail openly OR fix them.
4. Commit the in-scope flip + the triage_plan additions in the same
   commit set.

## Cross-references

- `cinderx/TestScripts/cinder_skip_test.txt` — per-entry skip list
  with annotation citing this file
- `cinderx/TestScripts/3.12-opt-arm64-failures.txt` — ARM64 failure
  list (not in scope for fix)
- `investigations/probes/cpython_skip_dual_failure_matrix.tsv` — Phase 2
  empirical evidence for the subinterpreter carve-out
- `investigations/plans/triage_plan_failing_tests.md` — in-scope bug
  triage; scope-limited features do NOT belong here
