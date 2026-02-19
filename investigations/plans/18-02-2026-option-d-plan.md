# Option D: Version-Tag Guard for LOAD_ATTR — Implementation Plan

## Problem Statement

CinderX JIT emits a function call (`BL`) to `LoadAttrCache::invoke()` for every `LOAD_ATTR` bytecode. This costs ~20 cycles on Neoverse (register saves, branch prediction, prologue/epilogue). CPython's interpreter does the same work with 4 inline instructions: load type, compare version tag, load at offset, done.

Current benchmark: `slot_read = 0.80x` (JIT is 20% slower than interpreter).

## Verified Facts

| Fact | Value | How verified |
|------|-------|-------------|
| `ob_type` offset in `PyObject` | 8 bytes | Compiled C probe on devgpu004 |
| `tp_version_tag` offset in `PyTypeObject` | 384 bytes | Compiled C probe on devgpu004 |
| `tp_version_tag` size | 4 bytes (uint32) | Compiled C probe on devgpu004 |
| Python version | 3.12.12+meta | `sys.version` on devgpu004 |
| LOAD_ATTR_SLOT already whitelisted | Yes | bytecode.cpp shows it in `specializedOpcode` |
| LoadAttrCache is empty at JIT compile time | Yes | Cache allocated by `allocateLoadAttrCache()`, populated on first invoke |
| No bytecode access from LIR generator | Confirmed | FrameState has `cur_instr_offs` but no code object reference |

## Design: Runtime Inline Cache Read (Revised)

### Core Insight

The `LoadAttrCache` is allocated at JIT compile time but populated at runtime. The JIT code knows the **address** of the cache (it's burned in as an immediate). Rather than calling `invoke()`, the JIT can read the cache's fields directly.

### Approach: Add fast-path fields to LoadAttrCache

Add two new fields to `LoadAttrCache`:
```cpp
class LoadAttrCache : public AttributeCache {
 public:
  // ... existing ...

  // Fast-path data for inline slot access
  // Set by fill() when a MemberDescr entry is detected
  PyTypeObject* fast_type_{nullptr};   // 8 bytes — cached type for monomorphic fast path
  Py_ssize_t fast_offset_{-1};         // 8 bytes — byte offset of slot in instance
};
```

When `fill()` creates a `MemberDescrMutator`, it also populates these fields. When the type watcher fires `typeChanged()`, reset them to null/-1.

### JIT Code Generation

In `kLoadAttrCached` case of `generator.cpp`, emit:

```
; Check if fast path is available
LDR x_cached_type, [cache_addr, #fast_type_offset]
CBZ x_cached_type, slow_path            ; not populated yet

; Load Py_TYPE(obj)
LDR x_type, [x_obj, #8]

; Compare type pointers
CMP x_type, x_cached_type
B.NE slow_path

; Fast path: load slot at cached offset
LDR x_fast_offset, [cache_addr, #fast_offset_offset]
LDR x_result, [x_obj, x_fast_offset]

; Check for NULL (T_OBJECT_EX slots)
CBZ x_result, slow_path

; INCREF
... incref ...
B done

slow_path:
BL LoadAttrCache::invoke              ; existing call path
done:
```

### Files Changed

1. `cinderx/Jit/inline_cache.h` — Add `fast_type_` and `fast_offset_` fields
2. `cinderx/Jit/inline_cache.cpp` — Populate fields in `fill()`, reset in `typeChanged()`
3. `cinderx/Jit/lir/generator.cpp` — Emit inline fast path before BL

### Falsification Criteria

1. **fast_type_ is NULL on first call** → falls through to BL invoke → cache populates → subsequent calls hit fast path
2. **Type mismatch** → CMP fails → falls through to BL invoke (polymorphic or type changed)
3. **NULL slot (T_OBJECT_EX)** → CBZ catches → falls through to BL invoke (which raises AttributeError properly)
4. **Type modification** → typeChanged() resets fast_type_ to NULL → next call goes through BL invoke → repopulates if still MemberDescr
5. **Non-MemberDescr attributes** → fast_type_ stays NULL → always goes through BL invoke (no regression)
6. **Refcounting** → fast path must INCREF result before returning

### Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Cache field offsets must be compile-time constants for LIR | Use `offsetof(LoadAttrCache, fast_type_)` |
| fast_type_ read is racy with typeChanged() | On aarch64, pointer-aligned loads are atomic; worst case is a spurious cache miss |
| `fast_offset_` is Py_ssize_t (64-bit signed) but used as offset | OK — LDR with register offset supports this |
| Incref logic must match existing pattern | Copy from existing MakeIncref code |
