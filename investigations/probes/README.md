# Investigation Probes

Falsifier scripts kept in-repo so they outlive any single session and can
be re-run against future builds. Each probe has a paired `_output_<date>.txt`
that records the verdict at the time it last ran.

If you find one of these probes via grep or scribe-query, **re-run it
against the build of the day** before drawing conclusions from the recorded
output. The reachability calculus depends on `cinderx/Jit/config.h` defaults
that may change.

## Probes

### `addreference_pinning_probe.py`
Tests whether `CodeRuntime::addReference()` pins a `GuardType` target's
`PyTypeObject` so that ABA pointer reuse is structurally impossible.

- 2026-04-21 verdict: addReference does NOT pin in the list-subclass path
  (refcount unchanged before/after `force_compile`; weakref dies after
  `del`+`gc.collect`).
- Theologian's hypothesis (vib-jit chat 2026-04-21 23:12:50): the JIT
  guarded on `PyList_Type` (immortal base) rather than on the user
  subclass, so `A` itself never entered `references_`.

### `aba_reachability_probe.py`
Probes whether the version_tag=0 GuardType bug is reachable from
default-config Python by examining HIR opcode counts of compiled functions.

- 2026-04-21 verdict: `GuardType` is NOT emitted in default config for
  either annotation guards (Path A) or `LOAD_ATTR_INSTANCE_VALUE` (Path B).
- Reachability gates per `cinderx/Jit/config.h:159` (`emit_type_annotation_guards{false}`)
  and `cinderx/Jit/annotation_index.cpp:9-31` (annotation index is null in default builds).

### `guardtype_emission_probe.py`
Earlier version of the reachability probe. Dumps HIR opcode counts for two
shapes (`f(x: C) -> x` and `f2(x: HasValue) -> x.value`) and checks
behaviour on type-mismatched inputs.

## Pre-run setup

```bash
source ../venv/bin/activate
export PYTHONPATH="$PWD/cinderx/PythonLib:$PYTHONPATH"
python3 investigations/probes/aba_reachability_probe.py
```

Capture stdout next to the script with the date suffix:
`<probe>_output_<YYYY-MM-DD>.txt`.

## Decision rules

Each probe's docstring states the decision rule. The rule binds the
reader: do not act on a stale verdict; re-run, then decide.
