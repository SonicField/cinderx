# Defensive Patch Tracker

## MAIN-MERGE PRE-FLIGHT CHECKLIST

**Read this before approving any sonicfield/speculation-experiment → facebookincubator/main merge.**

For every entry in this tracker:

1. **Read the entry.** Note the commit SHA(s) and the audit triggers.
2. **Run each audit trigger against the current code state.** Use the cited probes (e.g., `investigations/probes/`) and config grep commands verbatim where given.
3. **Decide go-or-revert PER ENTRY before merge.** If any audit trigger fires, the merge is NOT auto-approved on the basis of overall green; the entry's commit must either be reverted from the merge OR re-justified with new evidence.
4. **Record the decision.** Add a 'Last main-merge audit' row update to each entry: date, commit reviewed, verdict (kept / reverted / re-justified with link).

This checklist is the deferral mechanism the entries below depend on. Defensive patches in this tracker were committed under the asymmetric (d) policy on the basis that criterion-(d) gating applies at main-merge, NOT at feature-branch sync push. If this checklist is skipped, that policy collapses — defensive-only patches accumulate in main without verification.

**Falsifier on the checklist:** if a main-merge happens without a 'Last main-merge audit' row update on any entry, the checklist was skipped. The next maintainer to notice should escalate to the team's policy thread.

---

Audit registry for defensive-only patches: patches that protect against bug classes that were not reachable in default config at the time of commit, but could become reachable via config flips, new emit sites, or upstream changes. Each entry records the reachability gates whose state determines whether the patch is still necessary.

## Audit policy

- **Trigger:** any flip of a recorded reachability-gate config default; any new emit site that targets a recorded predicate; calendar-based re-audit at maintainer discretion.
- **Verdict on audit:** *still defensive only* (no observed regression, all gates still false) → keep, update last-audit date. *Now reachable* (gate flipped or new emit site) → patch is load-bearing, downgrade priority on revert. *Reachable but no observed exercise* → revert candidate; raise to maintainer for next maintenance window.
- **Owner split:** scribe owns the file; theologian (or whoever proposes a defensive patch) contributes new entries on commit; librarian runs periodic audits against the recorded triggers.

## Schema

Each entry records:

- **Commit SHA + short description**
- **Reachability gates:** the config flags / emit-site predicates whose collective falsity makes the patch unnecessary
- **Committed date**
- **Last audit date**
- **Audit verdict** — `still-defensive` / `now-reachable` / `reachable-no-exercise` / `superseded`

## Entries

### 794d8270 — GuardType: compare version tag instead of pointer (ABA safety)

- **Commit:** 794d8270 (theologian-spec D-1776812737, shipped before reachability falsified by D-1776813677)
- **Reachability gates** (all must remain FALSE for entry to stay defensive-only):
  - `getConfig().emit_type_annotation_guards` default — must remain `false`. If flipped or any production build enables it, GuardType paths through `cinderx/Jit/hir/builder.cpp::emitTypeAnnotationGuards` (~L898-944) become reachable on user-defined types.
  - `getConfig().multithreaded_compile_test` default — must remain `false`. If enabled (or any other path enabling concurrent JIT compile lands), GuardType paths through `LOAD_ATTR_SLOT` / `LOAD_ATTR_INSTANCE_VALUE` (`builder.cpp` ~L3318-3338) become race-vulnerable to ABA.
  - **No new `emit<GuardType>` site landing** that targets user-defined types and bypasses `findTypeByVersionTag`'s `version=0` filter.
- **Committed:** 2026-04-21
- **Last audit:** 2026-04-22 (initial registration; reachability falsified by testkeeper's harness `/tmp/aba_pinning_check_1776813052/tag_check2.py`, to be preserved at `investigations/probes/aba_reachability_probe.py` per D-1776818641)
- **Audit verdict:** `still-defensive` — gate flags both default-false; no GuardType emit site on user types in default config; ABBA-validated at 1.23x geomean (D-1776818535); no observed regression. Asymmetric criterion (d) per D-1776814202 keeps shipped commit despite reachability gap; revert decision pending alexie per D-1776818661 (Surface B).
- **Cross-references:** D-1776812737 (theologian Option A spec, STALE-CHECK gated by D-1776814943); D-1776813677 (testkeeper empirical falsification); D-1776814202 (asymmetric (d) policy); D-1776816633 (this tracker established); D-1776817090 (schema); D-1776818661 (this entry's creation directive).

### 78cee3c7 (load-bearing) + c4e1900c (defense-in-depth) — bench_deep_class SIGSEGV class

- **Commits:** 78cee3c7 (forgetCode cleanup — load-bearing), c4e1900c (slab arena zero-init — defense-in-depth)
- **Description:** `bench_deep_class` + `bench_json_roundtrip` + small-warmup workload reproducibly SIGSEGVs without 78cee3c7 (5/5 at n=5 single-host on 2026-04-22). The original ASan trace (D-1776809795) identified a UAF in `notifyTypeModified` after `forgetCode` ran without cleaning up `type_deopt_patchers_` entries — fixed by 78cee3c7. c4e1900c was added in parallel as a separate ASan finding (slab garbage in `LoadTypeAttrCache::reset`'s `Py_XDECREF` on uninitialised `value_`), but at n=5 single-host, c4e1900c-only-revert (cell 3) shows 5/5 clean — slab corruption only becomes fatal in conjunction with the forgetCode UAF. The original n=1 cell 2 misled an earlier hypothesis of JOINT compound-necessity (D-1776820345 → D-1776820463 → D-1776821015, all superseded); at n=5 the structure refined: 78cee3c7 is load-bearing, c4e1900c is defense-in-depth. Both ship; only c4e1900c is defensive in the audit-policy sense, but they are tracked together for discoverability.
- **Reachability gates:**
  - **Default config — 78cee3c7:** YES observed SIGSEGV (cell 2: 5/5 at n=5 on 2026-04-22). Load-bearing; reverting alone reproduces the original crash.
  - **Default config — c4e1900c:** NO observed SIGSEGV in default config (cell 3: 5/5 clean at n=5 on 2026-04-22). ASan-detectable corruption IS reachable (D-1776809795); SIGSEGV reachability requires another bug (78cee3c7's UAF) to compose with.
  - **Alternate environments (both):** UNKNOWN — single-host n=5 matrix only. Replication on (a) different host, (b) alternate malloc (e.g., jemalloc), (c) ASLR enabled vs disabled PENDING (Surface B-prime per theologian D-1776820938 / D-1776821479 / D-1776821694). Cell 3's 0/5 may flake-shadow on other hosts.
- **Test coverage:** `cinderx/PythonLib/test_cinderx/test_small_warmup_smoke.py` (subprocess + `bench_deep_class` + both-revert falsifier) catches cell 2 (78cee3c7-only-revert) AND cell 4 (both-revert). Does NOT catch cell 3 (c4e1900c-only-revert) — known soft-coverage gap pending alternate-environment replication.
- **Audit triggers:**
  1. Any single-fix regression from `c4e1900c` observed in production despite 78cee3c7 being in place — re-classify c4e1900c as independently necessary.
  2. Replication on alternate environment shows cell 3 (slab-alone revert) crashes — re-classify c4e1900c as necessary; add separate single-fix test.
  3. `c4e1900c`-only-revert SIGSEGV observed in production — falsifies defense-in-depth classification.
  4. ASan run finds new placement-new-corruption sites — same pattern, may need extension to other arenas.
  5. Any 78cee3c7 single-fix regression — escalate (load-bearing fix; not expected to need re-evaluation, but a flake here would be diagnostic).
- **Committed:** 2026-04-21 (both)
- **Last audit:** 2026-04-22 (initial registration; n=5 single-host matrix observed once)
- **Audit verdict:** 78cee3c7 `necessary` (load-bearing). c4e1900c `still-defensive` — defense-in-depth confirmed at n=5 single-host. Mechanism (silent UAF, fatal only with another bug) is ASan-detectable but does not produce default-config SIGSEGV in isolation on the tested host. Treat single-fix-c4e1900c-revert-is-safe as "shadow risk pending replication," not "verified safe."
- **Cross-references:** `investigations/probes/compound_crash_falsifier_matrix_2026-04-21.md` (raw n=5 matrix); `investigations/probes/compound_crash_repro.py` (workload); `cinderx/PythonLib/test_cinderx/test_small_warmup_smoke.py` (criterion-d falsifier); D-1776809795 (original ASan trace); D-1776820345 (initial n=1 matrix discovery, since corrected); D-1776820847 (pythia 4 single-host caveat); D-1776821441 (testkeeper n=5 narrative correction); D-1776821479 (theologian RETRACT JOINT, post single-fix second draft, since superseded); D-1776821596 (current live softened doctrine entry, supersedes D-1776820463 + D-1776821015); D-1776821694 (theologian third-draft JOINT framing per gatekeeper discoverability suggestion — this entry).