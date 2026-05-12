---
status: deferred-with-explicit-expiry
owner: supervisor (codification spec); shepard + gatekeeper (skill-file consumers)
trigger: shepard 2026-05-11 21:49:30Z RPC-collapse-risk flag on supervisor 21:25:22Z "banked for next-touch" framing
---

# Preventive umbrella for chat-discipline (skill-file edits)

## What this defers

`feedback_chat_discipline_umbrella_post_data_iteration.md` (committed 2026-05-11 21:06:51Z) is the RETROACTIVE form of the umbrella — codified rules that agents bind themselves to AFTER violating them. The PREVENTIVE form requires editing shepard + gatekeeper skill files so the rules fire at agent-startup as built-in discipline, not as post-violation self-binds.

Specifically, the 4 rules (peer-empirical-settled wait + primary-source-grep on cites + 1 canonical post per data-cycle + symmetric falsification/confirmation rigor) need to be:
1. Embedded in shepard's checkpoint protocol (so flag fires pre-architectural-read, not post)
2. Embedded in gatekeeper's pre-stage gates (so primary-source-grep on cited flags is a build-in check)
3. Embedded in supervisor's stop-rule (so 3+ self-binds in 2hr triggers automatic moratorium-bind on the offending agent without per-instance dispatch)

## Why deferred

Tonight's critical path is yield_from cross-arch root-cause + alexie's pending 3-option ship-or-fix decision on cluster5-pr-tu-isolated. Skill-file edits would change agent behavior mid-stream and risk introducing coordination drift at exactly the moment the team is converging on a value-decision.

## Explicit expiry

**Earliest of:**
- 2026-05-13 17:00 UTC (end of next workday, ~36 hours from now), OR
- alexie next ship-decision on cluster5-pr (whichever comes first)

If neither has happened by 2026-05-13 17:00 UTC, supervisor MUST either:
(a) execute the skill-file edits, OR
(b) re-defer with NEW explicit expiry + reason (NOT "next-touch")

This artifact existence is the forcing function per `project_recursive_policy_collapse_pattern.md` ("deferral-mechanism artifacts must ship in same push; 0/3 chat-only deferrals survived"). Closes shepard's 3rd-instance flag (per `project_spec_discipline_codification_deferred.md` deferred 2x already).

## What the skill-file edits would do (spec for next-touch)

**shepard checkpoint protocol additions:**
- On any architectural-read post by an agent who has fired ≥2 self-binds in current session: pre-emptively flag "@<agent> moratorium-eligible per chat-discipline umbrella; await empirical-on-disk before next architectural-read."
- On any falsifier-candidate post citing a build-flag / API / file-path: require @-mention of librarian for primary-source verify before chat-bind.

**gatekeeper pre-stage additions:**
- For any peer-cited mechanism-attribution: same-turn primary-source check on the cited evidence (file:line, commit SHA, build-flag presence) before stage-gate fires.

**supervisor stop-rule:**
- 3+ self-binds by single agent in same workday → auto-dispatch moratorium-bind for that agent (no further architectural-read posts until next empirical artifact lands), without per-instance prose-only dispatch.

**supervisor self-bind at codification time (NEW per pythia 278 risk-4 2026-05-11 23:11:46Z):**
- When supervisor codifies a chat-discipline umbrella, the same-bundle codification commit MUST include an explicit "supervisor binds self to umbrella rules effective immediately" clause. The 2026-05-11 codifier-violates-95min-later incident showed retroactive binding (after shepard fires) leaves a structurally-repeatable blind spot: every agent in-scope for the umbrella inherits the bind, EXCEPT the codifier — who shipped the rules and is implicitly out-of-scope until peer enforcement fires. Skill-file edit must make codifier-self-binding the default for any agent that codifies an umbrella, not an opt-in retroactive ack.

**theologian (and any architectural-reader) pre-commit primary-source verify on cited symbols (NEW per librarian 2026-05-12 11:19:32Z forward-bind fold-in):**
- Before any commit whose content cites another agent's empirical (function names, symbol mangling, file:line, percentages, callsite chains), the committing agent MUST same-turn open + grep the cited primary source. The 2026-05-12 v7→v8 incident: theologian composed pytorch_cm paragraph from supervisor's summary + internal model rather than reading generalist's primary-source post (medic + nbs-ts-grep evidence: 0 hits on `notifyTypeModified` in theologian's session-log). Wrong function name (`notifyDictUpdate` substituted from yield_from context) landed in durable PR-body; required medic catch + theologian v8 fixup. Skill-file edit must make pre-commit primary-source-grep the default amender-side check, not just gatekeeper retro-check.

**gatekeeper "verified-clean" cross-source check on PR-body content citing peer empirical (NEW per shepard 2026-05-12 10:46:59Z forward-bind fold-in):**
- When gatekeeper issues "verified-clean" on a PR-body amendment whose content cites another agent's empirical, diff-read alone is INSUFFICIENT. Gatekeeper MUST same-turn cross-source primary-source check the cited content against the cited speaker's exact post. The 2026-05-12 v7 incident: gatekeeper passed v7 "verified-clean" on a wrong function name because diff-read confirmed the diff matched the spec but the spec content itself was fabricated. Skill-file edit must extend gatekeeper's verified-clean criterion to include "any peer-cited content has been opened + grep'd against the citation source."

## Provenance

- Trigger artifact: `feedback_chat_discipline_umbrella_post_data_iteration.md` (2026-05-11 21:06Z)
- Original RPC-pattern source: `project_recursive_policy_collapse_pattern.md`
- Spec-discipline-codification 2x prior deferrals: `project_spec_discipline_codification_deferred.md`
- Shepard 3rd-instance flag: chat 2026-05-11 21:49:30Z
