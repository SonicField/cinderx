"""Fix B2 no-match deopt: use handler.target instead of bc_instr.baseOffset().

Root cause: tc.frame has left/right popped by emitBinaryOp. Deopt at
BINARY_SUBSCR offset expects them on the stack -> stack corruption.

Fix: deopt to handler.target (PUSH_EXC_INFO) with stack truncated to
handler.depth. Exception is pending (JITRT_MatchAndClearException restored it).
Interpreter processes handler normally.
"""
import sys

p = "/root/local/cinderx_dev/cinderx/cinderx/Jit/hir/builder.cpp"
with open(p) as f:
    c = f.read()

old = """    // === Deopt block (no match -- let interpreter handle) ===
    // Point cur_instr_offs at the original BINARY_SUBSCR instruction.
    // The interpreter will use the exception table to find the handler
    // and process the exception normally through PUSH_EXC_INFO etc.
    {
      TranslationContext deopt_tc{deopt_block, tc.frame};
      deopt_tc.frame.cur_instr_offs = bc_instr.baseOffset();
      deopt_tc.emitSnapshot();
      deopt_tc.emit<Deopt>();
    }"""

new = """    // === Deopt block (no match -- let interpreter handle) ===
    // Deopt to handler.target (PUSH_EXC_INFO) with stack at handler.depth.
    // tc.frame has left/right already popped (by emitBinaryOp), so we
    // cannot deopt to bc_instr.baseOffset (BINARY_SUBSCR expects them).
    // Instead, resume the interpreter at the exception handler entry point.
    // The exception is still pending (JITRT_MatchAndClearException restored
    // it), so PUSH_EXC_INFO -> CHECK_EXC_MATCH -> reraise works normally.
    {
      TranslationContext deopt_tc{deopt_block, tc.frame};
      // Truncate stack to handler.depth (what interpreter expects at handler).
      while (static_cast<int>(deopt_tc.frame.stack.size()) > handler.depth) {
        deopt_tc.frame.stack.pop();
      }
      deopt_tc.frame.cur_instr_offs = handler.target;
      deopt_tc.emitSnapshot();
      deopt_tc.emit<Deopt>();
    }"""

if old in c:
    c = c.replace(old, new)
    with open(p, "w") as f:
        f.write(c)
    print("OK: deopt block fixed to use handler.target with truncated stack")
else:
    print("FAIL: could not find old deopt block")
    idx = c.find("Deopt block (no match")
    if idx >= 0:
        print("Found at", idx)
        print(repr(c[idx:idx+200]))
    else:
        print("No deopt block found")
    sys.exit(1)
