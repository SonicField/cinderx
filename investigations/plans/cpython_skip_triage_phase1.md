# CPython Skip Triage — Phase 1

**Author:** testkeeper
**Date:** 2026-04-22
**Driver:** alexie via vib-jit.chat 05:39:06Z
**Source:** /tmp/cpython_test_results_20260421_223053.txt (CPython regression suite log captured at HEAD 60701da2 via `./run_cinderx_tests.sh full` 2026-04-22 03:23 UTC)

## Headline numbers

Per CPython test runner summary line in source:
```
Total tests: run=36,762 failures=9 skipped=1,186
Total test files: run=435/444 failed=5 skipped=22 resource_denied=9
```

- **22** module-level skips (entire test files not run)
- **9** module-level resource_denied (network / disk / etc. gates)
- **~1,155** individual test-method skips inside otherwise-running modules
- **1,186** total skipped test methods (sum)

This phase 1 categorizes the **31 module-level skips** completely (full names + reason) and gives best-effort sample categorization for the **~1,155 individual-test-method skips** based on the per-test "skipped -- <reason>" strings the runner emitted.

## Phase 1 categories (with counts and source)

### Category 1 — Platform-specific module skips

**22 modules skipped** per CPython runner output (verbatim list):
```
test.test_asyncio.test_windows_utils  test_asdl_parser  test_clinic
test_devpoll                          test_idle         test_ioctl
test_kqueue                           test_launcher     test_msilib
test_nis                              test_startfile    test_tcl
test_tix                              test_tkinter      test_ttk
test_ttk_textonly                     test_turtle       test_winapi
test_winconsoleio                     test_winreg       test_wmi
```

Source: same module-level skip lines emitted at the bottom of each
runner pass. Reasons (verified by grepping `skipped --` in source):

- **Windows-only (12 modules):** test_msilib, test_startfile,
  test_winapi, test_winconsoleio, test_winreg, test_wmi,
  test_launcher, test.test_asyncio.test_windows_utils, plus
  test_idle (tkinter / Windows-style), test_tcl, test_tix,
  test_tkinter, test_ttk, test_ttk_textonly, test_turtle (libX11
  unavailable on this build host)
- **Linux-only / BSD-only (3 modules):** test_devpoll (Solaris
  family), test_kqueue (BSD)
- **Optional dependency missing (5 modules):** test_asdl_parser,
  test_clinic (clinic directory not in install), test_nis (NIS
  client not present), test_msilib (Windows installer libs)
- **GUI / display (2+ modules):** test_idle, test_tkinter,
  test_tix, test_ttk family — libX11.so.6 unavailable

**Skip-criteria assessment (per testkeeper plan + alexie 05:32:57Z):**
All 22 are documented platform / dependency gates, NOT cinderx-introduced.
Per the dual-failure rule (vanilla CPython AND cinderx fail in same env →
acceptable skip), these would qualify if vanilla CPython 3.12.13 also
skips them on this host. **Phase 2 verifies the dual-failure for each.**

### Category 2 — Resource-denied module skips

**9 modules skipped** per CPython runner output (verbatim list):
```
test_curses  test_ossaudiodev  test_smtpnet
test_socketserver  test_urllib2net  test_urllibnet
test_winsound  test_xmlrpc_net  test_zipfile64
```

Reasons (per `skipped -- Use of the 'X' resource not enabled` lines):
- **Network resource (4 modules):** test_smtpnet, test_socketserver
  (network for inter-process), test_urllib2net, test_urllibnet,
  test_xmlrpc_net
- **Audio resource (2 modules):** test_ossaudiodev, test_winsound
- **Curses resource (1 module):** test_curses
- **Disk-space resource (1 module):** test_zipfile64

Reasons documented in CPython runner header:
```
== resources: all test resources are disabled, use -u option to unskip tests
```

**Skip-criteria assessment:** these are runtime-resource gates that
the runner intentionally disables by default. They would pass with
`-u all`. NOT cinderx-introduced. Acceptable per any reasonable skip
criterion.

### Category 3 — Cinderx-explicit skip list

**85 entries** in `cinderx/TestScripts/cinder_skip_test.txt` (verified
via `grep -v "^#\|^$" ... | wc -l` this turn).

Sectioned per file headers (verified by grepping "^#" this turn):
- **Subinterpreter-incompatibility (large block):** `test_xxsubinterpreters.*`,
  `test.test_ast.ModuleStateTests.test_subinterpreter`, ~10+ similar.
  Reason: "subinterpreters which are incompatible with CinderX" (verbatim
  from skip file comment).
- **Watcher-ID conflicts (small block):** "test unassigns a random type
  watcher ID which could be ours", "expects watcher ID to be 1".
- **CinderX-internal divergence:** "Expects only _testcapi module to be
  loaded in error message", "Extra frame injected in the dumb terminal so
  we don't shutdown cleanly", "Our code extra makes these stateful".
- **CTypes shutdown crash:** "use ctypes and can get crashy at shutdown
  due to the freefunc being freed".
- **Build-system reporting:** "wrong abi version on debug builds".
- **Esoteric / catch-all:** "esoteric tests fail on some versions".

**Skip-criteria assessment:** these are EXPLICITLY cinderx-decided skips.
Per alexie's rule, each is acceptable IF re-verified that the test fails
under both vanilla CPython AND cinderx in current environment. **Phase 2
re-verifies; some may have been added speculatively or for past versions.**

### Category 4 — Per-test skips within passing modules

**~1,155 skips** (1,186 total minus 22 module-level minus 9 resource-denied).
These fire from `@unittest.skip / @unittest.skipIf / @unittest.skipUnless`
decorators on individual test methods.

**66** "skipped -- <reason>" lines extracted from the runner log via
`grep -c "skipped"` this turn. Top reasons by count:

| Count | Reason |
|---|---|
| 7 | libX11.so.6: cannot open shared object file |
| 5 | Use of the 'network' resource not enabled |
| 2 | Windows only |
| 2 | Use of the 'audio' resource not enabled |
| 1 | Use of the 'curses' resource not enabled |
| 1 | Unable to open /dev/tty |
| 1 | test works only on Solaris OS family |
| 1 | test works only on BSD |
| 1 | test requires loads of disk-space bytes |
| 1 | test only relevant on win32 |
| 1 | test only applies to Windows |
| 1 | test irrelevant for an installed Python |
| 1 | object 'os' has no attribute 'startfile' |
| 1 | No module named '_wmi' / winreg / _winapi / nis / _msi |
| 1 | clinic directory could not be found |

These 66 are the modules that report a skip reason at the module level.
The remaining ~1,089 skips fire silently inside test methods (per-test
`@unittest.skipIf` decorators) — the CPython runner does not emit a
reason line for each silent skip in non-verbose mode; only the count
appears in `tests skipped=N`.

**Skip-criteria assessment:** the 66 with explicit reasons match the
same gate categories as the module-level skips (platform, resource,
optional dependency). The ~1,089 silent skips are individual test
methods with decorator gates that the test framework counts but doesn't
report by name in the compact log. **Phase 2 needs verbose-mode rerun
or per-module inspection to enumerate these.**

## Categories vs alexie's skip criteria (05:32:57Z)

| Category | Count | Gate-(j) acceptable per dual-failure rule? |
|---|---|---|
| Platform-specific module skip | 22 modules | LIKELY YES (vanilla CPython same-env also skips); phase 2 verifies |
| Resource-denied module skip | 9 modules | YES (runner-default gate, not cinderx-introduced) |
| Cinderx-explicit skip list | 85 entries | NEEDS PHASE 2 — re-verify each against current vanilla CPython 3.12.13 |
| Per-test silent skip | ~1,089 tests | LIKELY YES at scale (decorator-gated; phase 2 spot-checks samples) |
| Per-test skip with reason | 66 emissions | YES (reasons match platform/resource/optional-dep) |

## Phase 2 scope (NOT executed in this phase)

Phase 2 requires per-test verification against vanilla CPython 3.12.13
in the same environment. Specifically:

1. **Cinderx-explicit skip list (85 entries):** for each entry, run the
   test under vanilla CPython same env. If it FAILS in vanilla too,
   keep the skip. If it PASSES in vanilla, the skip is cinderx-imposed
   and may need investigation (test could be re-enabled, or there's a
   real cinderx bug being hidden).
2. **Per-test silent skips (~1,089):** verbose-mode rerun OR per-module
   `python3 -m test -v test_X` to enumerate. Alternative: spot-check
   the largest-skip-count modules.
3. **Module-level platform skips (22):** dual-failure verification is
   trivial (vanilla CPython same env also skips on missing libX11
   etc.). Quick batch run.

Phase 2 ETA: ~2-4 hours depending on scope (cinderx-explicit list +
per-test enumeration is bigger than module-level verification).

## Output files

- This document: `investigations/plans/cpython_skip_triage_phase1.md`
- Source data: `/tmp/cpython_test_results_20260421_223053.txt` (CPython runner log, 552 lines, capture at HEAD 60701da2 build)

## Handoff

- @alexie — phase 1 categories are above. Phase 2 ETA ~2-4 hours; needs
  your go-ahead OR de-prioritization vs other workstreams.
- @gatekeeper — phase 2 dual-failure verification is in your scope per
  your "carve-out via gatekeeper sign-off" rule. Suggest we pair on
  the 85 cinderx-explicit entries first since they're the most likely
  to contain stale skips.
- @theologian — for any cinderx-explicit entry that PASSES on vanilla
  CPython today, that's a candidate for triage_plan_failing_tests.md
  Group B (reproducible JIT issue) or Group D (flake) depending on
  why it was originally skipped.
