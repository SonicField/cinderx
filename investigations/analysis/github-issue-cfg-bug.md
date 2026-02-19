# GitHub Issue: Latent LIR branch bug in Option D LoadAttrCached inline fast path

**Repository:** SonicField/cinderx
**Branch:** aarch64-jit-generators
**Commit:** 3c4ff942
**File:** cinderx/Jit/lir/generator.cpp
**Priority:** Low (code works correctly today)
**Labels:** bug, aarch64, jit

---

## Title

Latent LIR branch bug: appendBranch(kBranch) emits no label operand in LoadAttrCached inline fast path

## Description

The Option D inline fast path for `kLoadAttrCached` (commit 3c4ff942) contains a latent CFG bug in `generator.cpp`. The code currently works because block layout happens to make `done_block` the immediate fall-through successor, but the generated LIR is structurally incorrect.

### Root Cause

`appendBranch(Instruction::kBranch, done_block)` creates a `kBranch` instruction with **no label operand**. The post-alloc pass (`postalloc.cpp:427`) has logic to add label operands to branches that lack them, but it **skips blocks that already have a kBranch**:

```cpp
// postalloc.cpp line 427
if (last_opcode == Instruction::kBranch) continue;  // skips — no label added
```

The LIR verifier (`verify.cpp:19-28`) then fails because it expects every branch to have a `kLabel` operand:

```
ERROR: Basic block 20 does not contain a jump to non-immediate successor 17
```

### Additional Issue

`appendBlock(call_block)` after the branch adds `call_block` as a spurious fall-through successor to `incref_block`, because `appendBlock()` calls `addSuccessor()` if the current block has fewer than 2 successors:

```cpp
// block_builder.cpp
void BasicBlockBuilder::appendBlock(BasicBlock* block) {
  if (cur_bb_->successors().size() < 2) {
    cur_bb_->addSuccessor(block);  // adds unintended fall-through edge
  }
  switchBlock(block);
}
```

This gives `incref_block` two successors (done_block + call_block) when it should have one (done_block only).

### Why It Works Today

The bug is latent because:
1. Block layout places `done_block` as the immediate successor after `call_block`, so fall-through semantics produce correct execution
2. The LIR verifier may not be active in release/optimised builds
3. The aarch64 backend's branch emission handles the fall-through case correctly

### Risk

If any of the following change, the bug becomes active:
- Block ordering changes (e.g., during optimisation passes)
- The LIR verifier is enabled in release mode
- A new pass is added that relies on correct CFG successor edges

### Proposed Fix

Replace `appendBranch(kBranch, done_block)` with block ordering that uses natural fall-through. Use `switchBlock()` (which does NOT add successor edges) instead of `appendBlock()` for blocks that already have explicit branch targets.

Alternatively, add a label operand to the `appendBranch(kBranch)` call site in `block_builder.h`, or fix the post-alloc pass to handle pre-existing kBranch instructions that lack labels.

### Reproduction

Enable the LIR verifier (debug build or `JIT_VERIFY_LIR=1`) and run:
```bash
cd ~/local/cinderx_dev/cinderx/cinderx/PythonLib
CINDERJIT_ENABLE=1 PYTHONPATH=. python3 -m unittest test_cinderx.test_jit_attr_cache.LoadAttrCacheTests.test_deopt_correctness_type_switch -v
```

The crash is:
```
fatal: ERROR: Basic block 20 does not contain a jump to non-immediate successor 17
```

### Files Involved

- `cinderx/Jit/lir/generator.cpp` — the Option D codegen (bug site)
- `cinderx/Jit/lir/block_builder.cpp` — `appendBlock()` / `switchBlock()` semantics
- `cinderx/Jit/lir/block_builder.h` — `appendBranch()` overloads
- `cinderx/Jit/lir/postalloc.cpp` — post-alloc branch fixup (line 427)
- `cinderx/Jit/lir/verify.cpp` — LIR verifier (lines 10-55)
