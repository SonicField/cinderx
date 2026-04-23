# Spec-discipline-tightening: empirical mechanism pre-confirm

## Rule

Before theologian writes a fix-spec for any failing test or perf regression, testkeeper MUST empirically confirm the root-cause mechanism. The spec then references the empirical evidence; generalist impl proceeds only after the spec cites that evidence.

## Why this rule exists

On 2026-04-23 (single push window), 4 spec-discipline gates fired late:

1. **B4 v1 (after_fork-CLOEXEC):** spec assumed CLOEXEC was the issue; testkeeper later found root cause was `perf::registerFunction` writing trampolines unconditionally at compiler-context init time. Spec was wrong scope; impl shipped a fix that didn't close the test.

2. **B5 (yield_from from 794d8270 ABA-safety GuardType):** spec attributed regression to 794d8270 ABA-safety codegen. Testkeeper counterfactual ABBA showed the revert produced no improvement at geomean (1.20x vs 1.20x); 794d8270 was NOT the source. Hypothesis falsified pre-impl.

3. **B2 (post-fork JIT does not re-emit perf-map for inherited functions):** spec assumed missing-emission as root cause. Testkeeper empirical: emission happens; content is wrong. Spec hypothesis falsified.

4. **B2' (PerfMapState FD-routing):** spec assumed FD-routing as B2 root cause. Generalist impl + testkeeper post-impl test found ANOTHER different root cause: HIR inliner inlines parent/child1/child2; they never standalone-compile; so they never get perf-map entries. Test fails for a different reason than the FD-routing fix addresses. B2' shipped as defensive but didn't close test; B2'' was the real fix (test-side update to current inliner semantics).

In every case, theologian wrote a spec without empirical mechanism confirmation. Generalist implemented per spec. Testkeeper post-impl verification revealed a different root cause. 1-2 hours of impl work each time, 4-8 hours total, with shipping pressure on each iteration.

The pattern: **theological inference about root cause is unreliable without empirical confirmation.** Spec attribution must rest on testkeeper-confirmed mechanism, not just code-reading inference.

## How to apply (the gate)

**For test failures:**

1. Testkeeper empirically reproduces the failure + identifies the mechanism (which code path is invoked, what state it's in, what the test asserts vs what's observed).
2. Testkeeper posts mechanism evidence to chat (Bash output, perf-map content, inliner-toggle differential, etc.).
3. Theologian writes spec citing testkeeper's empirical mechanism evidence (timestamp + handle + finding).
4. Gatekeeper reviews spec for empirical-evidence citation; BLOCKS endorsement if missing.
5. Supervisor verifies empirical-evidence citation before directing generalist impl.
6. Generalist impl proceeds.
7. Testkeeper post-impl verification confirms test PASS; if not PASS for a different mechanism than spec assumed, treat as new spec-discipline gate fire.

**For perf regressions:**

1. Testkeeper runs counterfactual ABBA (revert candidate commit, fast-mode preferred per alexie 08:13:25Z).
2. Testkeeper posts per-bench delta evidence + crash signature if applicable.
3. Theologian spec cites testkeeper's empirical evidence + identifies the specific dispatch path / instruction class affected.
4. Gatekeeper + supervisor verification gates fire as above.
5. Generalist impl proceeds.

## What the gate does NOT cover

- Defensive fixes for known-real-future-bugs (B2' shape) MAY ship without empirical-test-failure-mechanism evidence, BUT must declare in commit message that they do not close any current test and identify the separate bug (e.g., B2'').
- Test-side updates that align tests to current correct semantics (B3 3.12 opcode-removal, B2'' inliner-by-design) follow the same gate but the empirical evidence is "test asserts X; current behavior is Y; Y is correct" not "fix Y to match X".
- Pure refactors with no behavior change.

## Forcing function (per pythia 27 #2 retire-or-codify)

If spec-discipline gate fires fewer than 2 times in next 7 days of substantive workstream activity: rule has bitten; retain.
If gate fires 3+ times in same period: pattern persists; rule didn't help; investigate why agents skip the gate (rather than just adding more layers).
If gate is invoked but no spec-error caught: pattern is over-applied; relax scope.

## Origin

- Codified 2026-04-23 08:50Z per librarian recursive-policy-collapse catch (3 chat-only codification deferrals same day).
- Trigger: 4 spec-discipline gate fires same push window (B4 v1, B5, B2, B2').
- Authored to honor recursive-policy-collapse rule (`project_recursive_policy_collapse_pattern.md`): deferral-mechanism artifacts MUST ship same-push.

## Cross-references

- `feedback_spec_discipline_empirical_pre_confirm.md` (auto-memory layer 2)
- `feedback_layered_enforcement_for_prose_rules.md` (4-layer pattern source)
- `feedback_recursive_policy_collapse_pattern.md` (artifact-must-ship-same-push)
- `project_cinderx_terminal_goal.md` (Phase 1 priority context)
