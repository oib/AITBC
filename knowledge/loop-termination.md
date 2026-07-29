---
type: concept
resource: docs/sop/AGENT_WORKFLOW_SOP.md
tags: [workflow, governance, gates]
timestamp: 2026-07-03
---

# Loop termination

Rules that stop QAS/QAS-Design bounce loops from running forever and force human escalation at
defined points (ABS-11 prompt-level rules, ABS-12 mechanical backstop).

## 1. Failure classification (mandatory before any bounce)

Every bounce must classify the failure as exactly one of: **`code`** (implementation bug),
**`spec`** (AC/DAC incomplete or ambiguous), **`environment`** (missing/invalid secrets, env
vars, services, permissions), or **`external-dependency`** (third-party service/account/API key
no agent can provision). `environment` and `external-dependency` failures are **never** routed
back to implementers/designers — escalate to TDM/human on first occurrence.

## 2. Iteration cap

Every bounce comment carries the literal marker `Iteration N of M` (M defaults to 3), where N =
prior bounce count + 1, read from actual tracker comments, never agent memory. At N = M,
bouncing is **forbidden**: collect the failure chain and route to TDM/POPM with "iterations
exhausted."

## 3. Same-error-twice rule

If the identical failure signature appears in two consecutive validation runs after a fix
attempt, escalate immediately regardless of N — repeated identical failures mean fixes aren't
reaching root cause.

## 4. DAC change freeze

Design Acceptance Criteria are immutable during an open iteration cycle. If a DAC is believed
wrong, the ticket reopens at the BSA/spec level, the current cycle ends, and the counter resets
only after revised DACs are re-accepted.

## 5. Arbiter rule

If two fixers each blame the other for a failure's ownership, TDM issues a binding
classification after **one** round trip — no second ping-pong.

## 6. Environment preflight

Implementers must validate the spec's Environment Prerequisites section before starting.
Credential/environment gaps escalate to a human — agents cannot self-provision (ADR-A-0004).

## 7. Mechanical enforcement (ABS-12)

The cap is enforced by the harness, not prompt discipline alone: `scripts/hooks/iteration-guard.sh`,
wired as a `PreToolUse` hook in `.claude/hooks-config.json`, fires on Bash calls that post a
bounce (`comment <ticket>` with `--kind gate-results|handoff`). It counts prior `Iteration N of M`
comment blocks **through the task-tracking adapter** and blocks (exit 2) once the next bounce
would reach the cap — physically preventing another bounce, forcing escalation.

- **Cap source**: parsed from the most recent `Iteration N of M` marker on the ticket; falls back
  to 3 if none parses. Lets a harder ticket declare a larger bound without a code change.
- **Off-by-one, human-confirmed**: blocks when `N ≥ M`, i.e. 2 bounces succeed, the 3rd is
  refused — matching ABS-11's "at N = 3, bouncing is FORBIDDEN" literally.
- **Fail-open**: if the tracker is unreachable, the ticket id can't be extracted, or no cap
  parses, the hook exits 0 with a loud stderr warning (`iteration-guard: WARN ...`) — a broken
  tracker must never deadlock every agent handoff. Rules 1–6 remain the fallback layer.
- **Known limitation**: the hook only intercepts bounces expressed as a matchable tool call
  (adapter Bash/MCP call). A gate agent that "bounces" via prose alone is not mechanically
  interceptable — why the prompt-level rules stay layer one.
- **Human override**: after a block, a human triages and either closes the ticket or raises the
  per-ticket cap by posting a corrected marker directly (hooks only run inside the harness).

## Related

- [ticket-lifecycle-and-statuses.md](ticket-lifecycle-and-statuses.md) — In Review/In Test are
  where this loop runs
- [agent-roster-and-gates.md](agent-roster-and-gates.md) — QAS/QAS-Design as non-collapsible
  independence gates
- [approval-boundaries.md](approval-boundaries.md) — credential gaps are human-only, feeding
  rule 6 here
- Source: `docs/sop/AGENT_WORKFLOW_SOP.md` (Loop Termination Rules, ABS-11),
  `specs/ABS-12-iteration-guard-spec.md`
