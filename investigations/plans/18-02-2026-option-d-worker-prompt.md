# Option D Worker Prompt — Version-Tag Guard for LOAD_ATTR

## Context

You are implementing a JIT codegen optimisation for CinderX's aarch64 backend on devgpu004. The ssh session `pty_devgpu-claude` is already connected.

CinderX source is at: `~/local/cinderx_dev/cinderx/`

## Problem

CinderX JIT emits a function call (BL instruction) to `LoadAttrCache::invoke()` for every LOAD_ATTR bytecode. This costs ~20 cycles on Neoverse (register saves, branch prediction, prologue/epilogue). CPython's interpreter does the same work with 4 inline instructions: load type, compare version tag, load at offset, done.

Current benchmark: slot_read = 0.80x (JIT is 20% slower than interpreter). The 20% gap IS the function call overhead.

## What to implement: Option D — Version-Tag Guard

Emit a new guard in JIT code that:
1. Loads `Py_TYPE(obj)->tp_version_tag` (uint32)
2. Compares against a cached version value (known at JIT compile time)
3. If match: loads attribute directly at cached byte offset (single LDR)
4. If mismatch: falls through to existing `LoadAttrCache::invoke()` slow path

This mirrors CPython's `LOAD_ATTR_SLOT` fast path exactly.

## Key files

- `Jit/hir/simplify.cpp` — `simplifyLoadAttr()` / `simplifyLoadAttrCached()`
- `Jit/lir/generator.cpp` — `kLoadAttrCached` case (line ~1338)
- `Jit/lir/generator.cpp` — `kHasType` case (the existing GuardType pattern to study)
- `Jit/inline_cache.h` / `Jit/inline_cache.cpp` — LoadAttrCache, AttributeMutator
- `Include/cpython/object.h` — PyTypeObject layout, tp_version_tag offset

## Pre-verified findings (DO NOT re-investigate)

1. **HintType/FixedTypeProfiler is DEAD CODE** — never emitted by the builder. Do NOT try to use profiled types.
2. **x86 and aarch64 are identical** for LoadAttrCached — both emit a plain CALL. No existing inline pattern to port.
3. **GuardType + kHasType already works on aarch64** — emits LDR + CMP + B.NE + deopt. Study this pattern for your new guard.
4. **The interpreter's inline cache for LOAD_ATTR_SLOT** stores: type_version (uint32) + member_index (uint16). Read these from the bytecode inline cache at JIT compile time.
5. **tp_version_tag** is a uint32 field in PyTypeObject at a fixed offset.

## Implementation approach

**Option 1 (HIR level):** Add a new HIR opcode (e.g., GuardVersionTag) that the simplifier emits when it detects a LOAD_ATTR_SLOT specialisation in the bytecode. The LIR generator then emits the version-tag compare + branch, similar to kHasType.

**Option 2 (LIR level):** Modify the kLoadAttrCached case in generator.cpp to emit the version-tag check inline before the BL to invoke. On match, emit direct LDR at offset. On mismatch, fall through to BL.

Either approach works. Option 2 is more localised (changes only generator.cpp). Option 1 is cleaner architecturally.

## Success criteria

- slot_read improves from 0.80x toward 0.95x+ (10pp+ improvement)
- All 37 LOAD_ATTR tests pass (test suite at `/tmp/test_loadattr_inline_fastpath.py`)
- All 30/33 generator tests pass
- No crashes
- Post results to chat with handle `claude`

## Build commands

```bash
cd ~/local/cinderx_dev/cinderx
# Edit source files
cmake --build build -j8
# Test
CINDERJIT_ENABLE=1 PYTHONFAULTHANDLER=1 ../cpython-3.12/python /tmp/test_loadattr_inline_fastpath.py -v
```

## Chat

Post progress and results to: `/home/alexturner/claude_docs/nbs-framework/.nbs/chat/live.chat` using handle `claude`:
```bash
~/.nbs/bin/nbs-chat send /home/alexturner/claude_docs/nbs-framework/.nbs/chat/live.chat claude "message"
```
