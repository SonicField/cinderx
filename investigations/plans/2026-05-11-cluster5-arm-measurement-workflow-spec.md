---
status: pre-spec for instant-fire on alexie ARM-measurement greenlight
owner: theologian (workflow design); generalist (execution when fired)
trigger: shepard 2026-05-11 09:53:20Z dispatch "@theologian → pre-spec ARM workflow (devgpu004 nbs-remote-session per reference_arm64_workbook.md) for instant fire if alexie picks 4a"
scope: ARM measurement of cluster5-pr branch (cluster5-ic-churn-detection-pr @ 15be7756) on devgpu004; supplies the ARM cell currently marked "(validation pending)" in IDEA-spec v2 Empirical evidence table
audience: generalist (execution); supervisor (dispatch); theologian (IDEA-spec v3 update post-bench)
backing references:
  - reference_arm64_workbook.md auto-memory pointer → ~/docs/arm64-workbook-generic.md
  - today's x86 measurement: benchmarks/2026-05-11_010339_28a57df8_x86_64_abba.txt
  - PR branch commit on cluster5-pr: 15be7756
  - IDEA-spec v2 source-of-truth: speculation-experiment 3379c3e8
  - generalist 2026-05-11 08:04:00Z (x86 build-tooling caveat: spec-exp build.sh + benchmark_cinderx.py borrowed as untracked; build.sh modified +2 lines for upstream CMakeLists compat: DENABLE_DISASSEMBLER:OFF + DENABLE_ZLIB:OFF)
---

# Cluster 5 — ARM Measurement Workflow Spec for cluster5-pr

## What this document is

A pre-spec'd ARM measurement workflow for cluster5-ic-churn-detection-pr (commit 15be7756) on devgpu004. Designed for instant-fire when alexie greenlights ARM measurement. Workflow shape mirrors today's x86 process (generalist 09:25:27Z → 09:35:35Z) with ARM-specific adaptations from `reference_arm64_workbook.md`.

## Substrate

- ARM host: `devgpu004.kcm2.facebook.com` (per workbook §0.1 vib-jit example)
- Project root on ARM: `~/local/vib-jit/cinderx` (cinderx working tree on devgpu004; NOT cpython — workbook's cpython examples do not apply here)
- Vanilla python: `/usr/local/bin/python3` (Meta-internal 3.12.13; same baseline as x86; NOT `~/local/cpython-vanilla/python`)
- Branch to measure: `cluster5-ic-churn-detection-pr` (currently x86-only; needs bundle-transfer to ARM)
- Substrate HEAD target: `origin/main` `28a57df8` + IDEA-port commit `15be7756` (matches today's x86 measurement substrate)
- Build-tooling caveat (per generalist 08:04:00Z x86 finding): `build.sh` + `benchmark_cinderx.py` are not in `origin/main`; need to be borrowed from `speculation-experiment` and `build.sh` modified +2 lines (DENABLE_DISASSEMBLER:OFF + DENABLE_ZLIB:OFF) for upstream CMakeLists parse compat. Same on ARM.

## Pre-flight checks (generalist same-turn before Step 1)

(P1) Reach devgpu004: `nbs-local-run 'ssh devgpu004.kcm2.facebook.com hostname'`
(P2) Verify cinderx working tree on ARM: `nbs-local-run 'ssh devgpu004.kcm2.facebook.com "ls -d ~/local/vib-jit/cinderx"'`
(P3) Verify vanilla python: `nbs-local-run 'ssh devgpu004.kcm2.facebook.com "/usr/local/bin/python3 --version"'` (expect `Python 3.12.13`)

If any pre-flight fails, escalate to supervisor + alexie before proceeding (root-blocked class per `feedback_tractable_infra_boundary.md`).

## Workflow

### Step 1: Bundle-transfer cluster5-pr to devgpu004

On x86 (this host):
```
git bundle create /data/users/alexturner/vib-jit-arm64-cluster5.bundle \
  cluster5-ic-churn-detection-pr origin/main
nbs-local-run 'scp /data/users/alexturner/vib-jit-arm64-cluster5.bundle \
  devgpu004.kcm2.facebook.com:/data/users/alexturner/'
```

On devgpu004 (via nbs-local-run ssh):
```
nbs-local-run 'ssh devgpu004.kcm2.facebook.com "
  cd ~/local/vib-jit/cinderx &&
  git fetch /data/users/alexturner/vib-jit-arm64-cluster5.bundle \
    cluster5-ic-churn-detection-pr:cluster5-ic-churn-detection-pr &&
  git checkout cluster5-ic-churn-detection-pr"'
```

Verify HEAD: `nbs-local-run 'ssh devgpu004.kcm2.facebook.com "cd ~/local/vib-jit/cinderx && git log --oneline -3"'` — expect `15be7756` as HEAD.

### Step 2: Borrow build-tooling from speculation-experiment

On devgpu004 (cluster5-pr branch lacks build.sh + benchmark_cinderx.py per origin/main shape):
```
nbs-local-run 'ssh devgpu004.kcm2.facebook.com "
  cd ~/local/vib-jit/cinderx &&
  git show speculation-experiment:build.sh > build.sh &&
  git show speculation-experiment:benchmark_cinderx.py > benchmark_cinderx.py &&
  chmod +x build.sh"'
```

Apply x86 build-flag edits (`DENABLE_DISASSEMBLER:BOOL=OFF` + `DENABLE_ZLIB:BOOL=OFF`) to the borrowed build.sh per generalist 08:04:00Z x86 process. These stay UNTRACKED on cluster5-pr branch — NOT part of PR.

### Step 3: Build (LTO OFF on ARM per workbook §0.5; auto-clean per §3.5)

Spawn nbs-remote-session per workbook §2.3 (raw ssh / tmux forbidden per Alex 2026-04-16 directive):
```
nbs-remote-session devgpu004.kcm2.facebook.com --name=cluster5-arm --cwd=~/local/vib-jit/cinderx
```

Build with `--handle` REQUIRED when `--chat` set (workbook §2.3 FAILURE MODE — silent stderr otherwise):
```
nbs-remote-build cluster5-arm './build.sh --clean' \
  --chat=/data/users/alexturner/cinderx/.nbs/chat/vib-jit.chat \
  --handle=generalist
```

### Step 4: Verify IDEA-port symbols on ARM `_cinderx.so`

```
nbs-local-run 'ssh devgpu004.kcm2.facebook.com "
  cd ~/local/vib-jit/cinderx &&
  nm scratch/build-aarch64/_cinderx.so | \
    grep -E \"kVolatileTypeThreshold|recordTypeInvalidation|isVolatileType\""'
```

Expect 3 symbols present in anonymous namespace.

### Step 5: Smoke gate (per `feedback_auto_mode_pre_abba_smoke_gate.md`)

```
nbs-local-run 'ssh devgpu004.kcm2.facebook.com "
  cd ~/local/vib-jit/cinderx &&
  PYTHONPATH=cinderx/PythonLib /usr/local/bin/python3 -c \"
import cinderjit
def f(x): return x*2+1
cinderjit.auto()
cinderjit.compile_after_n_calls(10)
for _ in range(20): f(42)
assert cinderjit.is_jit_compiled(f), \\\"JIT not active in auto-mode\\\"
print(\\\"Smoke gate PASS\\\")
\""'
```

### Step 6: Bench (matches today's x86 invocation byte-for-byte; aarch64 artifact name)

```
nbs-remote-build cluster5-arm \
  'PYTHONPATH=cinderx/PythonLib /usr/local/bin/python3 ./benchmark_cinderx.py jit --compile=auto --reps=5' \
  --chat=/data/users/alexturner/cinderx/.nbs/chat/vib-jit.chat \
  --handle=generalist
```

Expected runtime: ~25-35min (full 29-bench subprocess ABBA).

Artifact auto-saved to `~/local/vib-jit/cinderx/benchmarks/2026-05-11_<HHMMSS>_28a57df8_aarch64_abba.txt`.

### Step 7: Compile-mode-header verify (per `feedback_gatekeeper_compile_mode_header_check.md`)

```
nbs-local-run 'ssh devgpu004.kcm2.facebook.com "
  grep -E \"Compile mode\" ~/local/vib-jit/cinderx/benchmarks/2026-05-11_*_28a57df8_aarch64_abba.txt | tail -1"'
```

Expect: `Compile mode: auto`. If `Compile mode: force` → BLOCK per Layer-3 gatekeeper rule.

### Step 8: Result extraction

Primary read — pytorch_cm:
```
nbs-local-run 'ssh devgpu004.kcm2.facebook.com "
  grep pytorch_cm ~/local/vib-jit/cinderx/benchmarks/2026-05-11_*_28a57df8_aarch64_abba.txt"'
```

### Step 9: Transfer artifact back to x86 for archive

```
nbs-local-run 'scp devgpu004.kcm2.facebook.com:~/local/vib-jit/cinderx/benchmarks/2026-05-11_*_28a57df8_aarch64_abba.txt \
  /data/users/alexturner/cinderx/benchmarks/'
```

### Step 10: Result framing (per supervisor 09:27:55Z scope-tighten)

- Primary read: pytorch_cm only.
- 0.95-1.05x deopt-band check per alexie binding (`feedback_abba_deoptimised_assumption_0_95_to_1_05x.md`): if pytorch_cm in band → assumed deoptimised until falsified.
- Reference points (writeup L107-110, May-5 substrate): writeup Step 6 ARM = 1.08x reps=5 (cinderx-main `1d8a9974` + d941a26a); writeup spec-exp matched-flags ARM BOTH = 1.00x.
- DROP broader-suite framing pending ARM control ABBA (same scope-tighten as x86 per supervisor 09:27:55Z + generalist 09:28:31Z spec).

### Step 11: IDEA-spec v3 update (theologian; ~5min via worktree pattern)

If pytorch_cm ARM measurement lands cleanly:
- Replace "(validation pending)" cell in Empirical evidence table at speculation-experiment IDEA-spec with measured ARM number
- Update PR commit-message Empirical paragraph: drop "ARM measurement on this PR's substrate is pending" line; add ARM measurement
- Worktree pattern: `git worktree add /data/users/alexturner/cinderx-spec-exp-theologian-worktree speculation-experiment`; edit; commit; remove worktree
- Generalist re-lifts updated PR commit-message text + creates follow-up commit on cluster5-pr (or amends 15be7756 — supervisor's call)

## Time-cost estimate

- Pre-flight: ~1min
- Bundle-transfer + scp + checkout: ~5min
- Borrow tooling + build-flag edits: ~3min
- Build + symbol verify: ~15-20min
- Smoke gate: ~1min
- Bench: ~25-35min
- Header-verify + result extraction + transfer-back: ~3min
- IDEA-spec v3 update: ~5min

Total: ~60-75min end-to-end.

## Risks / known failure modes

- **Workbook §2.3 FAILURE MODE — silent stderr.** `nbs-remote-build` requires `--handle` whenever `--chat` is set, else stderr goes to a detached file descriptor. Symptom: phantom long-running build with no output. After ≥2 minutes, sanity-check the binary timestamp. ALWAYS include `--handle=generalist`.
- **Workbook §8 issue 8.** Stale `Modules/getbuildinfo.o` causes `-dirty` marker on `Commit:` trailer. `./build.sh --clean` handles this.
- **ARM substrate drift.** ARM-specific upstream commits in the 11-day window `1d8a9974 → 28a57df8` may add measurement variance vs x86. Substrate-difference caveat per writeup framing applies symmetrically.
- **Deopt-band collapse.** If pytorch_cm on ARM lands in 0.95-1.05x deopt-band: assumed deoptimised per alexie binding; ARM control-ABBA becomes prerequisite for IDEA-port-attribution. Treat as blocker for IDEA-spec v3 update; surface to supervisor for control-ABBA-on-ARM dispatch decision.
- **Bundle-transfer race.** If supervisor or alexie advances `cluster5-pr` HEAD on x86 between bundle-creation and ARM checkout, the ARM substrate will lag x86. Substantively unlikely (PR work is alexie-blocked) but worth re-verifying HEAD post-Step-1.

## Cross-references

- `reference_arm64_workbook.md` (auto-memory pointer): `~/docs/arm64-workbook-generic.md`
- Today's x86 measurement: `benchmarks/2026-05-11_010339_28a57df8_x86_64_abba.txt`
- IDEA-spec v2 (PR source-of-truth): `speculation-experiment` `3379c3e8` `investigations/plans/2026-05-11-cluster5-ic-churn-detection-pr-idea-articulation.md`
- PR commit on cluster5-pr branch: `15be7756` 'JIT: stop watching types that churn their inline-cache invalidations'
- supervisor 2026-05-11 09:26:21Z dispatch (ARM measurement question to alexie)
- supervisor 2026-05-11 09:27:55Z dispatch (scope-tighten: pytorch_cm primary)
- shepard 2026-05-11 09:53:20Z dispatch (theologian pre-spec ARM workflow directive)
