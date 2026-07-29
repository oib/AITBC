---
id: ADR-A-0004
title: Humans own irreversibility — fixed approval boundaries
status: proposed
scope: agentic
date: "2026-07-02"
---

## Context

Agent autonomy is valuable exactly up to the point where a mistake is hard to undo. The line
must be structural, not behavioral: "the agent shouldn't" fails eventually; "the agent can't"
doesn't.

## Decision

We will require human approval for: architecture changes, breaking changes, merges to main,
additional license costs, additional LLM API costs, production deployments, accepted ADRs, and
final epic acceptance (`.agentic/governance/approval-boundaries.md`). Enforcement is structural
where possible: the git adapter exposes no merge operation for protected branches; the ADR status
guard (`tests/test-adr-status.sh`) requires any `accepted`/`superseded` ADR to carry
`accepted_by`/`accepted_date` — the human-acceptance evidence a `proposed` ADR omits (an evidence
check, **not** an authorship block; acceptance stays a human PR-review act per ADR-A-0001, see the
2026-07-26 amendment); no role is granted deploy capability.
Agents may create PRs and prepare deployments — never merge, never deploy, never accept ADRs.

## Consequences

Humans concentrate on planning, architectural approvals, cost approvals, epic acceptance, and
merging — everything else is delegated. These boundaries are permanent, not v1 caution; loosening
them requires superseding this ADR at company level or above, which the authority order makes a
deliberate, human-owned act.

## Amendment 2026-07-02 (ABS-9)

The PO-Agent (`.claude/agents/po-agent.md`) is granted, within the guardrails of this ADR:

- **Full story-acceptance authority** — accept/reject decisions on stories, issued only after
  the QAS gate, with reasoning recorded on the ticket via the task-tracking adapter.
- **Epic-completion determination** — the PO-Agent determines and records when an epic is done
  (all child stories accepted + epic Definition of Done met). This narrows the original
  "final epic acceptance" boundary: completion determination is delegated; the human merge and
  cost gates below still bound every path to production.
- **Autonomous backlog prioritization** — WSJF-based ordering of existing scope, decisions
  recorded on tickets. No human approval required for ordering.

Three decisions remain **human-only** — the PO-Agent prepares and escalates, never decides:

1. **Creating new features** — feature initiation is human; the PO-Agent manages and prioritizes
   existing scope only. Escalation: feature proposal document to the human POPM.
2. **Merging to main** — per ADR-A-0005 (all agent work reaches main only through PRs; the merge
   button is the human gate). Escalation: hand to RTE → HITL.
3. **Approving additional costs** — per ADR-A-0009 (license and LLM API costs pause at the
   `additional-costs` human gate). Escalation: cost summary to the human; the human approves or
   rejects each flag in the tracker.

All other boundaries in the original Decision (architecture changes, breaking changes,
production deployments, accepted ADRs) are unchanged.

## Amendment 2026-07-03 (ABS-11)

Provisioning credentials, secrets, API keys, and external service accounts is
the fourth human-only boundary, alongside feature initiation, merges to main,
and cost approval. Agents never create, obtain, or work around missing
credentials — regardless of whether the credential is free or paid. An agent
that hits a missing credential stops and escalates to a human with: the
credential name, the consuming library/service, and where it must be
configured. Rationale: uncodified, free-tier credentials previously triggered
no boundary, producing unfixable tester/implementer iteration loops.

## Amendment 2026-07-14 (ABS-295, ABS-296, ABS-298, ABS-301) — AD-1: self-reversal rule

**AD-1 (general rule for reconcile heal stories):** The runner may autonomously
reverse **only a state it itself caused and recorded in a machine-readable marker
of its own making**, and only back to the origin that marker records. It may never
synthesize product state and never advance a ticket on a human's behalf.

This is reconcile authority — equivalent to REPAIR-HANDOFF (ABS-132) — not a
product decision, and therefore does not require human approval beyond the normal
PR review gate.

**Application to heal stories:**

| Story | Marker reversed | Origin recorded in |
|---|---|---|
| ABS-295 (CRASH-REPAIR) | `SPAWN-CRASH status=… instance=…` | gate-results comment |
| ABS-296 | _open — not recorded here; AD-1 governs any reversal (2026-07-26 amendment)_ | per-story marker |
| ABS-298 | _open — not recorded here; AD-1 governs any reversal (2026-07-26 amendment)_ | per-story marker |
| ABS-301 | _open — not recorded here; AD-1 governs any reversal (2026-07-26 amendment)_ | per-story marker |

**Constraints (non-negotiable):**
- The marker must have been written by this runner's own `ORCH_INSTANCE_ID` — never
  touch a foreign runner's ticket (two-runner safety).
- Only reverse to the exact origin status the marker recorded; never advance.
- Every heal ships its own `ORCH_*` off-switch (knob `0` = off = NOTIFY-only).
- All PRs remain human-gated (ADR-A-0005 unchanged).

## Amendment 2026-07-15 (ABS-315) — ADR-acceptance close-out step

Accepting an ADR is human-only (Decision, above). But acceptance recorded only in
the tracker leaves the ADR **file** contradicting the decision: ADR-A-0017 stayed
`status: proposed` / `accepted_by: TBD` after a human accepted it on ABS-190, the
gap was flagged three times, and no seat owned closing it (the PO may not edit ADRs;
the implementer story is not scoped to governance frontmatter). This amendment names
the close-out step so the loop closes:

- **The flip stays a human/governance action** (this ADR's boundary is unchanged).
  Once a human accepts an ADR on a ticket, the **System Architect** seat — the owner
  of ADR files (`.claude/agents/system-architect.md`) — flips the file's
  `status: proposed → accepted` and sets `accepted_by`/`accepted_date`, in the same
  acceptance PR. The System Architect executes the mechanical edit that records the
  human's decision; it never *makes* the acceptance decision.
- **DoD gate.** Any epic whose acceptance criteria include "ADR … accepted" is not
  Done until the ADR file is closed out (PO-Agent epic-completion step 3,
  `.claude/agents/po-agent.md`). `scripts/adr-acceptance-drift.sh` detects a
  tracker-accepted-but-file-`proposed` drift; `scripts/adr-reference-lint.sh` fails a
  renumber that left dangling citations. Both are wired into `pre-release-check.sh`.
  The checks only DETECT — they never flip a status (this boundary is preserved).

## Amendment 2026-07-26 (PILOT-53 / ABS-562) — correcting the false ADR-checker authorship claim + open marker rows

**Correction to the Decision.** The Decision listed, among the structural enforcements, "the ADR
checker rejects agent-authored non-`proposed` statuses." **No such authorship check exists.** The ADR
status guard (`tests/test-adr-status.sh`) asserts only that (1) every ADR carries a valid `status:`
and (2) an `accepted`/`superseded` ADR also carries `accepted_by` **and** `accepted_date` — the
human-acceptance evidence a `proposed` ADR omits. It never inspects **who** authored the change: an
agent that sets `status: accepted` together with both fields passes the guard unchanged. The Decision
text is corrected above to describe this **evidence** check, not an authorship block. Acceptance stays
human-owned by **process and PR review** (ADR-A-0001 — agents cannot accept ADRs), never by a
mechanical author gate. Claiming a non-existent mechanical block produced exactly the false-safety
class this ADR exists to prevent, so the claim is removed rather than left to mislead.

**Marker table (Amendment 2026-07-14) — open rows made explicit.** Three rows carried "TBD by story
implementation" for the marker each heal story reverses. Those cells are now marked **explicitly
open**: ABS-296, ABS-298, and ABS-301 have not recorded their concrete markers here. Until each story
records its own marker, the **AD-1 general rule** above governs any reversal (the runner may reverse
only a state it itself caused and recorded, back only to the recorded origin) — the open rows narrow
nothing, grant nothing, and add no reversal authority.

**Acceptance.** This amendment corrects a factual claim and is prepared by the implementer for the
normal human PR-review acceptance gate; no agent accepts it (ADR-A-0001).
