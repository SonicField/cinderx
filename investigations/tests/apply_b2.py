#!/usr/bin/env python3
"""Apply B2: inline exception match in JIT.

Files changed:
1. jit_rt.h  — JITRT_MatchAndClearException declaration
2. jit_rt.cpp — JITRT_MatchAndClearException implementation
3. hir/hir.h — Add to CallCFunc_FUNCS macro
4. hir/builder.h — Add B2 method declarations
5. hir/builder.cpp — B2 logic + POP_EXCEPT no-op
"""

import sys
import os

BASE = os.path.expanduser("~/local/cinderx_dev/cinderx/cinderx/Jit")

def read_file(path):
    with open(path, 'r') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w') as f:
        f.write(content)

def apply_edit(content, old, new, desc):
    if old not in content:
        print(f"  FAIL: {desc}")
        print(f"    Could not find: {repr(old[:100])}...")
        return content, False
    n = content.count(old)
    if n > 1:
        print(f"  WARN: {desc} — {n} occurrences, replacing first")
        idx = content.index(old)
        return content[:idx] + new + content[idx+len(old):], True
    return content.replace(old, new), True

ok_count = 0
fail_count = 0

def check(ok, desc):
    global ok_count, fail_count
    if ok:
        ok_count += 1
        print(f"  OK: {desc}")
    else:
        fail_count += 1
        print(f"  FAIL: {desc}")

# ============================================================
# 1. jit_rt.h
# ============================================================
print("=== jit_rt.h ===")
p = f"{BASE}/jit_rt.h"
c = read_file(p)

# Insert after JITRT_Vectorcall declaration
marker = "PyObject* JITRT_Vectorcall("
idx = c.find(marker)
if idx >= 0:
    # Find end of this declaration block (the semicolon + newline)
    semi = c.index(";", idx)
    nl = c.index("\n", semi)
    insert = nl + 1
    decl = (
        "\n"
        "// B2: Match pending exception against type and clear if matched.\n"
        "// Returns 1 if matched (exception cleared), 0 if no match.\n"
        "int JITRT_MatchAndClearException(PyObject* exc_type);\n"
    )
    c = c[:insert] + decl + c[insert:]
    write_file(p, c)
    check(True, "JITRT_MatchAndClearException declaration")
else:
    check(False, "could not find JITRT_Vectorcall marker")

# ============================================================
# 2. jit_rt.cpp
# ============================================================
print("=== jit_rt.cpp ===")
p = f"{BASE}/jit_rt.cpp"
c = read_file(p)

impl = (
    "\n"
    "// B2: Match pending exception against type and clear if matched.\n"
    "int JITRT_MatchAndClearException(PyObject* exc_type) {\n"
    "  PyObject* exc = PyErr_GetRaisedException();\n"
    "  if (exc == nullptr) {\n"
    "    return 0;\n"
    "  }\n"
    "  int matched = PyErr_GivenExceptionMatches(exc, exc_type);\n"
    "  if (matched) {\n"
    "    Py_DECREF(exc);\n"
    "    return 1;\n"
    "  }\n"
    "  // Restore exception for interpreter to handle.\n"
    "  PyErr_SetRaisedException(exc);\n"
    "  return 0;\n"
    "}\n"
)

# Append to end of file
c = c.rstrip() + "\n" + impl
write_file(p, c)
check(True, "JITRT_MatchAndClearException implementation")

# ============================================================
# 3. hir/hir.h — CallCFunc_FUNCS macro
# ============================================================
print("=== hir/hir.h ===")
p = f"{BASE}/hir/hir.h"
c = read_file(p)

# Add to 3.12+ macro
old = (
    "#define CallCFunc_FUNCS(X)         \\\n"
    "  X(Cix_PyAsyncGenValueWrapperNew) \\\n"
    "  X(JitCoro_GetAwaitableIter)      \\\n"
    "  X(JitGen_yf)"
)
new = (
    "#define CallCFunc_FUNCS(X)         \\\n"
    "  X(Cix_PyAsyncGenValueWrapperNew) \\\n"
    "  X(JitCoro_GetAwaitableIter)      \\\n"
    "  X(JitGen_yf)                     \\\n"
    "  X(JITRT_MatchAndClearException)"
)
c, ok1 = apply_edit(c, old, new, "3.12+ macro")
check(ok1, "CallCFunc_FUNCS 3.12+")

# Add to pre-3.12 macro
old2 = (
    "#define CallCFunc_FUNCS(X)         \\\n"
    "  X(Cix_PyAsyncGenValueWrapperNew) \\\n"
    "  X(Cix_PyCoro_GetAwaitableIter)   \\\n"
    "  X(Cix_PyGen_yf)"
)
new2 = (
    "#define CallCFunc_FUNCS(X)         \\\n"
    "  X(Cix_PyAsyncGenValueWrapperNew) \\\n"
    "  X(Cix_PyCoro_GetAwaitableIter)   \\\n"
    "  X(Cix_PyGen_yf)                  \\\n"
    "  X(JITRT_MatchAndClearException)"
)
c, ok2 = apply_edit(c, old2, new2, "pre-3.12 macro")
check(ok2, "CallCFunc_FUNCS pre-3.12")

write_file(p, c)

# ============================================================
# 4. hir/builder.h — B2 declarations
# ============================================================
print("=== hir/builder.h ===")
p = f"{BASE}/hir/builder.h"
c = read_file(p)

# Add CFG& to emitBinaryOp signature
old_sig = (
    "  void emitBinaryOp(\n"
    "      TranslationContext& tc,\n"
    "      const jit::BytecodeInstruction& bc_instr);"
)
new_sig = (
    "  void emitBinaryOp(\n"
    "      CFG& cfg,\n"
    "      TranslationContext& tc,\n"
    "      const jit::BytecodeInstruction& bc_instr);"
)
c, ok = apply_edit(c, old_sig, new_sig, "emitBinaryOp signature")
check(ok, "emitBinaryOp declaration")

# Add B2 method declarations after findExceptionHandler
old_find = (
    "  // Find exception handler for a given bytecode offset\n"
    "  const ExceptionTableEntry* findExceptionHandler(BCOffset off) const;"
)
new_find = (
    "  // Find exception handler for a given bytecode offset\n"
    "  const ExceptionTableEntry* findExceptionHandler(BCOffset off) const;\n"
    "\n"
    "  // B2: Info about a simple except pattern suitable for inlining.\n"
    "  struct SimpleExceptInfo {\n"
    "    int name_idx;           // Index into co_names for the exc type\n"
    "    PyObject* exc_type;     // Resolved exception type (borrowed ref)\n"
    "    BCOffset except_body;   // Offset of except body (after POP_TOP)\n"
    "  };\n"
    "\n"
    "  // B2: Check if handler has simple except pattern and extract info.\n"
    "  bool getSimpleExceptInfo(\n"
    "      const ExceptionTableEntry& handler,\n"
    "      SimpleExceptInfo& info) const;\n"
    "\n"
    "  // B2: Emit inline exception match for subscript inside try block.\n"
    "  void emitInlineExceptionMatch(\n"
    "      CFG& cfg,\n"
    "      TranslationContext& tc,\n"
    "      const jit::BytecodeInstruction& bc_instr,\n"
    "      const ExceptionTableEntry& handler,\n"
    "      const SimpleExceptInfo& info,\n"
    "      Register* left,\n"
    "      Register* right,\n"
    "      Register* result);"
)
c, ok = apply_edit(c, old_find, new_find, "B2 declarations")
check(ok, "B2 method declarations")

write_file(p, c)

# ============================================================
# 5. hir/builder.cpp — B2 implementation
# ============================================================
print("=== hir/builder.cpp ===")
p = f"{BASE}/hir/builder.cpp"
c = read_file(p)

# 5a. Add jit_rt.h include
inc = '#include "cinderx/Jit/hir/builder.h"'
if '#include "cinderx/Jit/jit_rt.h"' not in c:
    c, ok = apply_edit(c, inc, inc + '\n#include "cinderx/Jit/jit_rt.h"', "include")
    check(ok, "jit_rt.h include")

# 5b. Update emitBinaryOp call site
old_call = "          emitBinaryOp(tc, bc_instr);"
new_call = "          emitBinaryOp(irfunc.cfg, tc, bc_instr);"
c, ok = apply_edit(c, old_call, new_call, "call site")
check(ok, "emitBinaryOp call site")

# 5c. Update emitBinaryOp definition signature
old_def = (
    "void HIRBuilder::emitBinaryOp(\n"
    "    TranslationContext& tc,\n"
    "    const jit::BytecodeInstruction& bc_instr) {"
)
new_def = (
    "void HIRBuilder::emitBinaryOp(\n"
    "    CFG& cfg,\n"
    "    TranslationContext& tc,\n"
    "    const jit::BytecodeInstruction& bc_instr) {"
)
c, ok = apply_edit(c, old_def, new_def, "definition")
check(ok, "emitBinaryOp definition")

# 5d. Add B2 check before BinaryOp emission
old_emit = (
    "  tc.emit<BinaryOp>(result, op_kind, left, right, tc.frame);\n"
    "  stack.push(result);\n"
    "}"
)
new_emit = (
    "  // B2: For subscript inside try block with simple except pattern,\n"
    "  // emit inline exception match instead of BinaryOp (which auto-deopts).\n"
    "  if (op_kind == BinaryOpKind::kSubscript) {\n"
    "    BCOffset cur_off = bc_instr.baseOffset();\n"
    "    auto* handler = findExceptionHandler(cur_off);\n"
    "    if (handler != nullptr) {\n"
    "      SimpleExceptInfo info;\n"
    "      if (getSimpleExceptInfo(*handler, info)) {\n"
    "        emitInlineExceptionMatch(\n"
    "            cfg, tc, bc_instr, *handler, info,\n"
    "            left, right, result);\n"
    "        stack.push(result);\n"
    "        return;\n"
    "      }\n"
    "    }\n"
    "  }\n"
    "\n"
    "  tc.emit<BinaryOp>(result, op_kind, left, right, tc.frame);\n"
    "  stack.push(result);\n"
    "}"
)
c, ok = apply_edit(c, old_emit, new_emit, "B2 check")
check(ok, "B2 check in emitBinaryOp")

# 5e. Add except body offset as block start
old_bs = (
    "  // Parse co_exceptiontable and add handler targets as block starts.\n"
    "  // This ensures exception handler basic blocks are created in the HIR,\n"
    "  // even though Python 3.12+ does not emit SETUP_FINALLY opcodes.\n"
    "  parseExceptionTable();\n"
    "  for (const auto& entry : exception_table_) {\n"
    "    block_starts.insert(entry.target.asIndex());\n"
    "  }"
)
new_bs = (
    "  // Parse co_exceptiontable and add handler targets as block starts.\n"
    "  // This ensures exception handler basic blocks are created in the HIR,\n"
    "  // even though Python 3.12+ does not emit SETUP_FINALLY opcodes.\n"
    "  parseExceptionTable();\n"
    "  for (const auto& entry : exception_table_) {\n"
    "    block_starts.insert(entry.target.asIndex());\n"
    "    // B2: Also add except body start so we can branch to it.\n"
    "    SimpleExceptInfo info;\n"
    "    if (getSimpleExceptInfo(entry, info)) {\n"
    "      block_starts.insert(info.except_body.asIndex());\n"
    "    }\n"
    "  }"
)
c, ok = apply_edit(c, old_bs, new_bs, "block_starts")
check(ok, "except body block starts")

# 5f. Add getSimpleExceptInfo and emitInlineExceptionMatch implementations
old_feh = (
    "const HIRBuilder::ExceptionTableEntry* HIRBuilder::findExceptionHandler(\n"
    "    BCOffset off) const {\n"
    "  for (const auto& entry : exception_table_) {\n"
    "    if (off >= entry.start && off < entry.end) {\n"
    "      return &entry;\n"
    "    }\n"
    "  }\n"
    "  return nullptr;\n"
    "}"
)

new_feh = old_feh + """

bool HIRBuilder::getSimpleExceptInfo(
    const ExceptionTableEntry& handler,
    SimpleExceptInfo& info) const {
  // Scan handler bytecodes for the pattern:
  //   PUSH_EXC_INFO, LOAD_GLOBAL <type>, CHECK_EXC_MATCH,
  //   POP_JUMP_IF_FALSE, POP_TOP
  BytecodeInstruction bc{code_, handler.target};

  if (bc.opcode() != PUSH_EXC_INFO) {
    return false;
  }
  bc = bc.nextInstr();

  if (bc.opcode() != LOAD_GLOBAL) {
    return false;
  }
  int name_idx = loadGlobalIndex(bc.oparg());
  bc = bc.nextInstr();

  if (bc.opcode() != CHECK_EXC_MATCH) {
    return false;
  }
  bc = bc.nextInstr();

  if (bc.opcode() != POP_JUMP_IF_FALSE) {
    return false;
  }
  bc = bc.nextInstr();

  if (bc.opcode() != POP_TOP) {
    return false;
  }
  BCOffset except_body = bc.nextInstrOffset();

  // Resolve exception type at JIT compile time via preloader.
  BorrowedRef<> exc_type = preloader_.global(name_idx);
  if (exc_type == nullptr) {
    return false;
  }
  if (!PyExceptionClass_Check(exc_type)) {
    return false;
  }

  info.name_idx = name_idx;
  info.exc_type = exc_type;
  info.except_body = except_body;
  return true;
}

void HIRBuilder::emitInlineExceptionMatch(
    CFG& cfg,
    TranslationContext& tc,
    const jit::BytecodeInstruction& bc_instr,
    const ExceptionTableEntry& handler,
    const SimpleExceptInfo& info,
    Register* left,
    Register* right,
    Register* result) {
  // Emit PyObject_GetItem via CallStatic (not BinaryOp/DeoptBase)
  // so we can handle the error path inline instead of auto-deopting.
  auto call = tc.emit<CallStatic>(
      2, result, reinterpret_cast<void*>(PyObject_GetItem), TOptObject);
  call->SetOperand(0, left);
  call->SetOperand(1, right);

  BasicBlock* ok_block = cfg.AllocateBlock();
  BasicBlock* exc_match_block = cfg.AllocateBlock();

  // Branch: non-null → success, null → exception path
  tc.emit<CondBranch>(result, ok_block, exc_match_block);

  // === Exception match block ===
  tc.block = exc_match_block;

  // Decref stack items above handler depth.
  // left and right were consumed by PyObject_GetItem (popped before emit).
  // The stack has items from before the BinaryOp. Decref those above depth.
  auto& stack = tc.frame.stack;
  while (static_cast<int>(stack.size()) > handler.depth) {
    Register* excess = stack.pop();
    tc.emit<Decref>(excess, TObject);
  }

  // Load exception type as a constant (resolved at compile time).
  Register* exc_type_reg = temps_.AllocateNonStack();
  tc.emit<LoadConst>(exc_type_reg, Type::fromObject(info.exc_type));

  // Call JITRT_MatchAndClearException(exc_type).
  Register* match_result = temps_.AllocateNonStack();
  tc.emit<CallCFunc>(
      1, match_result,
      CallCFunc::Func::kJITRT_MatchAndClearException,
      std::vector<Register*>{exc_type_reg});

  BasicBlock* except_body_block = getBlockAtOff(info.except_body);
  BasicBlock* deopt_block = cfg.AllocateBlock();
  tc.emit<CondBranch>(match_result, except_body_block, deopt_block);

  // === Deopt block (no match — let interpreter handle) ===
  TranslationContext deopt_tc{deopt_block, tc.frame};
  deopt_tc.frame.cur_instr_offs = handler.target;
  // Stack already truncated to handler depth.
  deopt_tc.emitSnapshot();
  deopt_tc.emit<Deopt>();

  // === OK block (no exception, result is non-null) ===
  tc.block = ok_block;
  tc.emit<RefineType>(result, TObject, result);
}"""

c, ok = apply_edit(c, old_feh, new_feh, "B2 implementations")
check(ok, "getSimpleExceptInfo + emitInlineExceptionMatch")

# 5g. Handle POP_EXCEPT as no-op
# Find POP_TOP case and add POP_EXCEPT before it
pop_top = "        case POP_TOP: {"
pop_except = (
    "        case POP_EXCEPT: {\n"
    "          // B2: no-op — we never pushed exc_info in the JIT.\n"
    "          break;\n"
    "        }\n"
)
if pop_top in c:
    c = c.replace(pop_top, pop_except + pop_top, 1)
    check(True, "POP_EXCEPT no-op")
else:
    check(False, "POP_EXCEPT no-op — POP_TOP not found")

write_file(p, c)

# ============================================================
# Summary
# ============================================================
print(f"\n=== Summary: {ok_count} OK, {fail_count} FAIL ===")
if fail_count > 0:
    print("ERRORS — review output above")
    sys.exit(1)
else:
    print("All edits applied successfully")
    sys.exit(0)
