# ABS-122 Evaluation — Cursor Agent as Spawn Provider (GO/NO-GO)

**Date**: 2026-07-07 · **Driver**: quota relief — Claude stays the default provider, Cursor is an
overflow valve (operator refinement). Candidate seats include DEV implementers (the big quota
lever), never po-agent/system-architect (quality rule).

## Verdict: **CONDITIONAL GO — blocked on a human login, do not wire seats yet**

The seam fits and the adapter exists (`scripts/orchestrator-spawn-cursor.sh`, EVALUATION status);
the CLI verifiably has everything the contract needs, INCLUDING a resume equivalent. What could
not be verified is live behavior (JSON field names, resume semantics, sandbox behavior of
code-writing seats) because `cursor agent` on this machine is **unauthenticated** and
`cursor agent login` / `CURSOR_API_KEY` provisioning is a human-only credential step
(ADR-A-0004). Evidence of the blocker:

```
$ cursor agent -p "Reply with exactly: OK" --output-format json --trust
Error: Authentication required. Please run 'cursor agent login' first, or set CURSOR_API_KEY ...
```

## (a) Per-role provider override — BUILT (independent of the GO, per ticket AC)

`ORCH_SPAWN_CMD_<ROLE>` (analog `ORCH_MODEL_<ROLE>`) resolves in `run_spawn_cmd`; stub-tested in
`tests/test-orchestrator.sh` (ABS-122 section): the overridden seat runs the alternative
provider, all other seats stay on the default, scoping is per role.

## (b) Agent-def mapping — FEASIBLE, one structural difference

`cursor agent --help` (v2025.x, captured 2026-07-07) confirms headless mode: `-p/--print`,
`--output-format json|stream-json`, `--model`, `--workspace <path>`, `--resume [chatId]`,
`--force`/`--sandbox`. There is **no `--agents` equivalent**, so the adapter prepends the role
def's PROMPT BODY to the packet as the instruction preamble. `tools:` frontmatter has NO
enforcement surface on Cursor — least-privilege enforcement is lost; only worktree isolation
(C9) and Cursor's sandbox remain. The adapter's contract shape (role preamble + packet in one
prompt, JSON invocation, model passthrough, stdout to the seam) is pinned by an offline
fake-binary test.

## (c) Resume — EXISTS but UNVERIFIED; trade-off quantified anyway

`--resume [chatId]` is a real flag, so the feared resume-less-dev-seat scenario likely does NOT
apply — pending live verification of (1) the chat-id field name in the JSON result (the runner's
`extract_session_id` expects `session_id`; the adapter guesses `chatId`) and (2) whether a
resumed chat retains workspace context. IF resume turns out unusable: per the ABS-102 run data a
dev seat averages 1–2 rework bounces per story; each bounce on a resume-less provider pays a full
cold start (packet re-read + context rebuild ≈ the dominant token cost of a dev spawn,
empirically ~2–3× the marginal cost of a resumed continuation, see ABS-120 SPAWN-USAGE data once
live). Net: without resume, Cursor dev seats only pay off when Claude quota is the binding
constraint — exactly the operator's overflow-valve framing, so even the degraded case is
acceptable FOR OVERFLOW USE, not as default.

## (d) Permission model — residual risk assessment for code-writing seats

No settings.local.json semantics: Cursor won't honor the repo allowlist. Mitigations: worktree
isolation carries most of the safety (the seat physically works in tmp/<ticket>-work); Cursor's
own sandbox stays ON by default in the adapter (`--force` only via ORCH_CURSOR_FORCE=1); tracker
writes still go through the adapter scripts. Residual: a dev seat could run arbitrary shell
inside the worktree (Claude seats are allowlist-constrained there too, so the delta is the
allowlist granularity, not the blast radius). Acceptable for overflow use on dev seats;
review-type seats (read-only expectations) should NOT move to Cursor until a read-only mode
equivalent (`--mode ask/plan` looks promising — unverified) is validated.

## Recommendation per seat type

| Seat type | Recommendation |
|---|---|
| Dev implementers (be/fe/data) | GO for overflow, AFTER human login + live verification of resume + JSON fields |
| Mechanical (qas, tech-writer, rte) | possible, but sonnet defaults (ABS-120) already cut their cost — low win |
| Review seats (system-architect at In Review, security) | NO until a verified read-only mode exists |
| po-agent / system-architect (judgment) | NEVER (operator quality rule) |

## Next steps (human)

1. `cursor agent login` (or provision CURSOR_API_KEY) — human-only.
2. Re-run the live probes: JSON result shape (chat id field), `--resume` semantics, `--mode ask`
   read-only behavior, one full seat dry-run via `ORCH_SPAWN_CMD_QAS=scripts/orchestrator-spawn-cursor.sh`
   in the e2e dry-run environment.
3. Only then wire a real seat; telemetry (ABS-125) will be empty for Cursor seats — known gap.
