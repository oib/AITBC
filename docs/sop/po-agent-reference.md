# PO-Agent Reference (examples, templates, rationale)

Companion to `.claude/agents/po-agent.md`. The agent definition keeps the
decision rules, gates, human-only boundaries, output formats, and exit
transitions; this file holds the worked examples, long-form bash sequences, and
rationale the PO-Agent pulls in **only when actually performing** the task named
in each "Trigger" below. Nothing here overrides the authority split in
`adrs/agentic/ADR-A-0004-human-approval-boundaries.md` (Amendments ABS-9,
ABS-11) — those boundaries live verbatim in the agent definition.

---

## WSJF scoring — detail

Trigger: prioritizing the backlog or scoring an epic in `PO Triage`.

```text
WSJF = Cost of Delay / Job Size
Cost of Delay = Business Value + Time Criticality + Risk Reduction / Opportunity Enablement
```

Score each component on the relative scale **1, 2, 3, 5, 8, 13, 20** (compare
tickets against each other, not absolutes):

| Component            | Question                                                       |
| -------------------- | -------------------------------------------------------------- |
| **Business Value**   | How much user/business value does this deliver?                |
| **Time Criticality** | How much does the value decay if we wait? Is there a deadline? |
| **Risk Reduction**   | How much risk does this remove or opportunity does it enable?  |
| **Job Size**         | Relative effort/duration to deliver (the divisor)              |

Rules: highest WSJF first; ties break toward the smaller job; re-score when new
tickets arrive, an epic completes, or facts change (never let scores go stale);
record every prioritization decision on the affected tickets via the adapter
(scores + resulting rank + reasoning) so ordering is auditable. Prioritization
covers **existing scope only** — a gap needing a new feature is human-only.

---

## Acceptance decision — worked format

Trigger: recording a story accept/reject (both the "Story Acceptance (Full
Authority)" flow and the v3 `Story Acceptance` seat use this shape).

```markdown
## PO-Agent Acceptance Decision

- **Ticket**: AITBC-XXX
- **Decision**: accept | reject
- **Test gate**: [QAS evidence / exit state ref; Design Test ref if design-flagged]
- **AC Verification**: [per-criterion: met / not met, with evidence reference]
- **Defect list** (reject only): [AC-N: concrete defect, one per line]
- **Reasoning**: [why accepted, or exactly what is missing]
```

On reject, the reasoning names the failed criteria; the ticket returns to a
fresh implementer (via TDM). Rejection feeds the ABS-74 rework counter (three
bounces → the runner routes to `Needs PO Decision`). Out-of-scope findings from
acceptance route to the BSA as a `kind: follow-up` comment — never folded
silently.

---

## Epic decomposition (Branch B) — full worked sequence

Trigger: spawned on `Needs PO Decision` with a `type: epic` packet whose
`children <epic-id>` returns empty (a bare epic submitted for decomposition).
The loop cannot spawn the Issue Enrichment Agent as a nested subagent, so run
its protocol inline via the `duplicate-detection` and `issue-enrichment` skills.

```bash
# 1. Confirm bare: empty output → decompose; non-empty → treat as Branch A
"${TRACKER_CMD:-scripts/mock-tracker.sh}" children <epic-id>

# 3a. Per child — dedup gate (duplicate-detection skill): link/annotate instead
#     of creating a real duplicate
"${TRACKER_CMD:-scripts/mock-tracker.sh}" search --text "<child title / keywords>"

# 3b. Per child — enrichment (issue-enrichment skill): structure as
#     goal / scope / acceptance criteria / references + guardrail annotation,
#     written to a scratch file the implementer reads as the child body.

# 4. Create each child, parented to the epic, with the role hint (ABS-36 §2.2)
#    and the enriched body via --body-file (the adapter is the only sanctioned
#    writer — agents never touch work/tickets/*.md directly)
"${TRACKER_CMD:-scripts/mock-tracker.sh}" create --type ticket --parent <epic-id> \
  --role <be-developer|fe-developer|data-engineer> --title "<enriched child title>" \
  --body-file <path-to-enriched-body>

# 5. Set each child Ready for Development so the Coordinator can dispatch it
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <child-id> "Ready for Development" --actor po-agent \
  --reason "Decomposed from epic <epic-id>; enriched + dedup-checked"

# 6. Post a decision comment on the epic with every child id + title AND the
#    total count, so a human can size ORCH_MAX_SPAWNS_PER_RUN before fan-out
#    (ADR-A-0009: decomposition fan-out must be budget-visible)
"${TRACKER_CMD:-scripts/mock-tracker.sh}" comment <epic-id> --kind decision --actor po-agent \
  --body "Epic decomposition: created N children — <id> <title>; …; Total: N. Human: size ORCH_MAX_SPAWNS_PER_RUN accordingly before the run."

# 7. Return the epic to Backlog — the epic itself is not implementable; it rests
#    until the epic-completion check fires when its children are done
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <epic-id> "Backlog" --actor po-agent \
  --reason "Decomposition complete: N children created + set Ready for Development; epic rests until the completion check"
```

Out-of-scope needs surfaced while decomposing follow the usual routes — new
features to the human POPM (Human-Only Decision 1), follow-up recommendations to
the BSA (Orchestration Triggers (c)).

---

## Escalation packages — contents

Trigger: preparing one of the human-only escalations (the PO-Agent prepares and
escalates; it never makes these calls).

- **Feature proposal** (Human-Only Decision 1): problem, evidence, expected
  value, rough WSJF estimate — **no implementation detail**. To the human POPM
  (oib), who decides whether the feature exists.
- **Cost summary** (Human-Only Decision 3): the option, the cost source, the
  no-cost alternative, the trade-off. To the human POPM, who approves/rejects
  each cost flag in the tracker (ADR-A-0009).
- **Credential request** (Human-Only Decision 4): the credential name, the
  consuming library/service, and where it must be configured. To the human POPM,
  who provisions it or advises an alternative path (ADR-A-0004 Amendment ABS-11).

For a human-only ask discovered during `PO Triage`, do NOT groom — file a
`kind: notification` escalation comment and hold the epic (no forward
transition):

```bash
"${TRACKER_CMD:-scripts/mock-tracker.sh}" comment <epic-id> --kind notification --actor po-agent \
  --body "ESCALATION (human-only): <feature framing | cost | credential> needed before grooming. <what/where>."
```

---

## Backlog-triage exit — declared target or transition (ABS-409)

Trigger: the prioritization sweep spawned you on a **parentless `Backlog` ticket**
(`Backlog → SPAWN po-agent`) and you have scored it. `Backlog` has **no self-loop**:
the exit is the routing, and it is one of — an **executed transition**, a
**declared machine-readable `to:` target** the runner applies for you, or a
**reasoned `Blocked`/`Needs PO Decision` escalation**. A "dispatchable" verdict
whose destination lives only in prose is a `HANDOFF-NOMOVE` the runner cannot act
on (respawn loop → `Needs PO Decision` detour; ABS-409).

```bash
# Option A — execute the transition yourself (always valid)
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <id> "Ready for Development" --actor po-agent \
  --reason "Backlog triage: WSJF <score>, dispatchable — released to a fresh implementer"
```

Option B — declare a **machine-readable target** in the handoff and let the runner
apply it (a *runner-applied handoff target*, `handoff_target_status`). The runner
parses a bare declarative field, precedence `to > next-status > next`; it does
**not** parse the human `**Next**:` prose line. Put the machine field on its own
line:

```markdown
## Backlog Triage Decision
- **Ticket**: AITBC-XXX
- **WSJF**: BV=_ TC=_ RR=_ / JS=_ → score=_
- **Verdict**: dispatch | design | deprioritize | escalate
- **Reasoning**: [why this routing]
to: Ready for Development
```

Legal `Backlog` targets (`profiles/neutral/adapters/statuses.yaml` → `Backlog.next`):
`Ready for Development`, `Design`, `PO Triage`, `Stories In Flight` (decomposed-epic
JOIN-rest only), `Backlog`, `Blocked`, `Needs PO Decision`. Genuinely human-only
asks are escalated via a `kind: notification` comment (see the PO Triage seat below).

---

## Seat exit transitions — full commands

Trigger: executing the single exit transition for a v3 seat spawn. The agent
definition lists the transition **targets** per outcome (behavior); these are the
full adapter command forms. Canonical shape: `"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <id> "<status>" --actor po-agent --reason "<reason>"`.

**PO Triage Seat** (`Backlog → PO Triage → Grooming`) — packet: `role: po-agent`,
`ticket_id` (epic), `from_status: Backlog`, `to_status: PO Triage`, epic dump,
latest `kind: handoff` comment.

```bash
# Worth grooming now → release to the BSA Grooming seat
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <epic-id> "Grooming" --actor po-agent \
  --reason "PO Triage: WSJF <score>, scope coherent — released to Grooming"
# Deprioritized (thin, duplicate, or lower WSJF than current work)
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <epic-id> "Backlog" --actor po-agent \
  --reason "PO Triage: deprioritized — <WSJF/duplicate reasoning>"
# Needs a product/direction call before grooming (not human-only)
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <epic-id> "Needs PO Decision" --actor po-agent \
  --reason "PO Triage: <the open product question>"
# Genuinely human-only ask → escalate via notification, do NOT transition
"${TRACKER_CMD:-scripts/mock-tracker.sh}" comment <epic-id> --kind notification --actor po-agent \
  --body "ESCALATION (human-only): <feature framing | cost | credential> needed before grooming. <what/where>."
```

**Story Acceptance Seat** (`Design Test → Story Acceptance → Merging`) — packet:
`role: po-agent`, `ticket_id` (story), `from_status` (prior test stage — `In Test`
or `Design Test`), `to_status: Story Acceptance`, story dump (ACs + QAS/QAS-Design
evidence), latest `kind: handoff` comment.

```bash
# Accepted → release to the RTE Merging seat
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <story-id> "Merging" --actor po-agent \
  --reason "Story Acceptance: all ACs met against evidence — released to Merging"
# Rejected → fresh implementer with the concrete defect list
"${TRACKER_CMD:-scripts/mock-tracker.sh}" transition <story-id> "Ready for Development" --actor po-agent \
  --reason "Story Acceptance: rejected — defects: <AC-N: what is missing>; <AC-M: ...>"
```

Handoff-format bodies for these seats:

```markdown
## PO Triage Decision
- **Epic**: AITBC-XXX
- **WSJF**: BV=_ TC=_ RR=_ / JS=_ → score=_
- **Verdict**: groom | deprioritize | escalate
- **Guardrails for grooming**: [notes | none]
- **Next**: Grooming (BSA) | Backlog | Needs PO Decision | human escalation filed

## PO-Agent Story Acceptance Decision
- **Story**: AITBC-XXX
- **Decision**: accept | reject
- **Test gate**: [QAS evidence ref; Design Test ref if design-flagged]
- **AC verification**: [per-AC: met / not met, with evidence reference]
- **Defect list** (reject only): [AC-N: concrete defect, one per line]
- **Next**: Merging (RTE) | Ready for Development (fresh implementer)
```

`Needs PO Decision` Branch A exits: `Backlog`, `Ready for Development`, or
`Blocked` for a plain product decision; for a v3 escalation resume onto the
pipeline instead — **epics** → `PO Triage` / `Grooming` / `Stories In Flight`;
**stories** → `Design` (the status's full outgoing set;
`profiles/neutral/adapters/statuses.yaml`).

---

## ADR Authoring Request — template

Trigger: work surfaces an undocumented architectural decision (Orchestration
Trigger (b)). Hand this to the System Architect, who owns the protocol and
reports the ADR path back; the PO-Agent links it on the ticket and NEVER authors
or accepts ADRs itself (`docs/sop/ADR_AUTHORING_GUIDE.md`).

```markdown
## ADR Authoring Request
**From**: PO-Agent  **Ticket**: AITBC-XXX
**Topic**: [decision topic]  **Context**: [why a decision is needed now]
**Proposed Level**: [company/agentic/project — System Architect validates]
```

---

## Full-detail SOP

The authoritative long-form procedure for every seat (Story Acceptance,
Epic-Completion Detection, `Needs PO Decision`, `PO Triage`, `Story Acceptance`)
is `docs/sop/PO_AGENT_SOP.md` — read it when a case is not covered by the agent
definition above.
