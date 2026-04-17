// Copyright (c) Meta Platforms, Inc. and affiliates.

#include "cinderx/Jit/hir/phi_unboxing.h"

#include "cinderx/Jit/hir/hir.h"
#include "cinderx/Jit/hir/pass.h"
#include "cinderx/Jit/hir/type.h"

namespace jit::hir {

void PhiUnboxing::Run(Function& irfunc) {
  bool changed = false;

  for (auto& block : irfunc.cfg.blocks) {
    for (auto it = block.begin(); it != block.end(); ++it) {
      if (!it->IsPhi()) {
        continue;
      }
      auto* phi = static_cast<Phi*>(&*it);
      Register* out = phi->output();

      // Only specialize Phis that currently carry boxed long types
      if (!out->type().couldBe(TLongExact)) {
        continue;
      }

      // Check all non-self inputs are unboxable to CInt64
      bool all_unboxable = true;
      for (std::size_t i = 0; i < phi->NumOperands(); i++) {
        Register* op = phi->GetOperand(i);
        if (op == out) {
          continue;
        }
        // PrimitiveBox(CInt64) → can unwrap to CInt64
        if (op->instr()->IsPrimitiveBox()) {
          auto* box = static_cast<const PrimitiveBox*>(op->instr());
          if (box->GetOperand(0)->type() <= TCInt64) {
            continue;
          }
        }
        // Integer constant → can unbox at compile time
        if (op->type().hasObjectSpec() && PyLong_Check(op->type().objectSpec())) {
          int overflow = 0;
          PyLong_AsLongAndOverflow(op->type().objectSpec(), &overflow);
          if (overflow == 0) {
            continue;
          }
        }
        all_unboxable = false;
        break;
      }
      if (!all_unboxable) {
        continue;
      }

      // Check all uses are PrimitiveUnbox(TCInt64) — scan all instructions
      // that reference this Phi's output register
      bool all_uses_unbox = true;
      for (auto& use_block : irfunc.cfg.blocks) {
        for (auto& instr : use_block) {
          if (&instr == phi) {
            continue;
          }
          for (std::size_t i = 0; i < instr.NumOperands(); i++) {
            if (instr.GetOperand(i) == out) {
              if (instr.IsPhi()) {
                // Self-referencing Phi or another Phi using this one
                if (&instr != phi) {
                  all_uses_unbox = false;
                }
              } else if (instr.IsPrimitiveUnbox()) {
                auto& unbox = static_cast<const PrimitiveUnbox&>(instr);
                if (!(unbox.type() <= TCInt64)) {
                  all_uses_unbox = false;
                }
              } else {
                all_uses_unbox = false;
              }
              if (!all_uses_unbox) break;
            }
          }
          if (!all_uses_unbox) break;
        }
        if (!all_uses_unbox) break;
      }
      if (!all_uses_unbox) {
        continue;
      }

      // === SPECIALIZE: transform Phi to carry CInt64 ===

      // 1. Replace each Phi input with its CInt64 equivalent
      for (std::size_t i = 0; i < phi->NumOperands(); i++) {
        Register* op = phi->GetOperand(i);
        if (op == out) {
          continue;
        }
        if (op->instr()->IsPrimitiveBox()) {
          // Unwrap: PrimitiveBox(x) → x (x is CInt64)
          auto* box = static_cast<PrimitiveBox*>(op->instr());
          phi->SetOperand(i, box->GetOperand(0));
        } else if (op->type().hasObjectSpec()) {
          // Integer constant → create CInt64 constant
          int overflow = 0;
          long val =
              PyLong_AsLongAndOverflow(op->type().objectSpec(), &overflow);
          if (overflow == 0) {
            auto* const_reg = irfunc.env.AllocateRegister();
            auto* load =
                LoadConst::create(const_reg, Type::fromCInt(val, TCInt64));
            // Insert before the predecessor's terminator
            auto& pred_blocks = phi->basic_blocks();
            if (i < pred_blocks.size()) {
              auto* pred = pred_blocks[i];
              auto term_it = pred->end();
              --term_it;
              load->InsertBefore(*term_it);
              phi->SetOperand(i, const_reg);
            }
          }
        }
      }

      // 2. Update Phi output type to CInt64
      out->set_type(TCInt64);

      // 3. Replace PrimitiveUnbox uses — they now receive CInt64 directly
      // Collect first, modify second (avoid iterator invalidation)
      std::vector<PrimitiveUnbox*> unboxes;
      for (auto& use_block : irfunc.cfg.blocks) {
        for (auto use_it = use_block.begin(); use_it != use_block.end();
             ++use_it) {
          if (use_it->IsPrimitiveUnbox()) {
            auto* unbox = static_cast<PrimitiveUnbox*>(&*use_it);
            if (unbox->GetOperand(0) == out) {
              unboxes.push_back(unbox);
            }
          }
        }
      }
      for (auto* unbox : unboxes) {
        // Replace all uses of the unbox output with the Phi output directly
        Register* unbox_out = unbox->output();
        // Walk all instructions and replace references
        for (auto& rb : irfunc.cfg.blocks) {
          for (auto& ri : rb) {
            for (std::size_t i = 0; i < ri.NumOperands(); i++) {
              if (ri.GetOperand(i) == unbox_out) {
                ri.SetOperand(i, out);
              }
            }
          }
        }
        unbox->unlink();
        delete unbox;
      }

      changed = true;
    }
  }

  if (changed) {
    reflowTypes(irfunc);
  }
}

} // namespace jit::hir
