# ADR Authoring Guide

**Purpose**: Define when and how to author Architecture Decision Records (ADRs) with the System Architect as guide

**Version**: 1.0 (Guided ADR Authoring - ABS-2)
**Last Updated**: 2026-07-02

---

## Overview

All ADRs are authored **through the System Architect** - it owns ADRs and guides every authoring
session, whether requested by a human or handed off by another agent. The full protocol lives in
the System Architect role definition
([`.claude/agents/system-architect.md`](../../.claude/agents/system-architect.md), "Guided ADR
Authoring"). This guide covers when to author, how the guidance works, and the stop-the-line rule.

ADR templates live in the `confluence-docs` skill - never copy template content into other docs.

---

## When to Author an ADR

Author (or update) an ADR when a decision is:

- **Significant**: Changes architecture, security model, data governance, or a cross-cutting pattern
- **Hard to reverse**: Future work will build on it
- **Contested or repeated**: The same question keeps coming up in specs or reviews

Do NOT author an ADR for routine implementation choices already covered by
`patterns_library/` or an existing ADR - the System Architect will propose an **update to the
existing ADR** instead of a new one.

---

## How the System Architect Guides Authoring

The System Architect walks the author through five steps:

1. **Hierarchy first**: Reads
   [`adrs/agentic/ADR-A-0001-three-level-adr-hierarchy.md`](../../adrs/agentic/ADR-A-0001-three-level-adr-hierarchy.md)
   and places the ADR at the correct level (`adrs/company/`, `adrs/agentic/`, or `adrs/project/`,
   plus any project-level ADR directories such as `docs/adr/`)
2. **Scan before create**: Searches all ADR levels for a decision already covering the topic and
   proposes update-vs-new
3. **House template**: Guides the author section-by-section through the ADR template from the
   `confluence-docs` skill
4. **Bidirectional links**: Detects related/superseded/superseding ADRs and updates BOTH files
   (superseded ADR gets "Superseded by", new ADR names what it supersedes)
5. **Conflict check**: Stops the line on any conflict with an accepted broader-level ADR (see below)

The ADR ships as `proposed`; only a human accepts it.

---

## Worked Example

**Scenario**: The team wants to decide "all background jobs must be idempotent".

### Path A: Human Direct Invocation

```text
Human: @system-architect I need an ADR requiring idempotent background jobs.

System Architect:
1. Reads ADR-A-0001 → this is a project-local decision → adrs/project/
2. Scans adrs/** and docs/adr/ → finds no ADR covering job idempotency,
   but ADR-A-0006 (active task tracking) is related
3. Guides the human through the confluence-docs ADR template
   (Context, Decision, Consequences, alternatives considered)
4. Creates adrs/project/ADR-P-0001-idempotent-background-jobs.md (status: proposed)
   and links ADR-A-0006 as related in both directions
5. Human reviews and accepts (status: accepted, accepted_by)
```

### Path B: PO-Agent Handoff

The PO-Agent ([`.claude/agents/po-agent.md`](../../.claude/agents/po-agent.md)) detects during
backlog refinement that a story implies an undocumented architectural decision, and hands off
programmatically:

```markdown
## ADR Authoring Request

**From**: PO-Agent
**Ticket**: AITBC-231
**Topic**: Idempotent background jobs
**Context**: Story AITBC-231 retries failed jobs; duplicate side effects possible
**Proposed Level**: project - System Architect validates
```

The System Architect runs the same five steps and reports the resulting ADR path (or an
update proposal for an existing ADR) back to the PO-Agent, which links it in the ticket.

---

## Stop-the-Line Rule

If a proposed ADR conflicts with an **accepted broader-level ADR** (project vs. company/agentic),
the System Architect halts authoring and issues an explicit warning naming the conflicting ADR -
this is the existing stop-the-line authority applied to ADR authoring.

Per ADR-A-0001, a narrower ADR may override a broader one ONLY when:

1. A human explicitly accepts the override, AND
2. The overriding ADR names the overridden ADR in its `overrides` field

The System Architect never accepts an override itself - the decision escalates to HITL.

---

## ADR Acceptance Closeout (ABS-212)

Accepting an ADR is **human-only** (ADR-A-0004): a human accepts it by merging the ADR's PR
(`adrs/README.md` lifecycle). That acceptance is not complete until the ADR **file frontmatter**
is flipped in the **same acceptance PR** — otherwise the file drifts from the record. ADR-A-0017
was accepted in the tracker on 2026-07-11 but its file stayed `proposed`; the gap was flagged
three times and never closed, forcing a manual flip at the v2.24.0 release (A-0018/A-0019 were
similar operator handwork).

**Who flips, when, via which PR:**

- **Who**: the human accepter (or the operator/PO shepherding the acceptance) — never an agent.
- **When**: at the moment of acceptance, in the same work-zug — not as a loose follow-up.
- **Which PR**: the acceptance PR itself (the PR whose merge constitutes acceptance). Set:
  - `status: accepted`
  - `accepted_by: "<Name (role)>"`
  - `accepted_date: "YYYY-MM-DD"`
  - update the ADR's row in [`adrs/agentic/README.md`](../../adrs/agentic/README.md) to `— **Accepted**`.

**Guardrail**: [`scripts/adr-acceptance-drift.sh`](../../scripts/adr-acceptance-drift.sh) detects
ADRs accepted in the record (index row marked **Accepted**, or `accepted_by`/`accepted_date`
present) whose file `status:` is still `proposed`. It runs as a **warning** in
[`scripts/pre-release-check.sh`](../../scripts/pre-release-check.sh) (section 9) so a release
either closes the drift out or acknowledges it; run it standalone any time with
`bash scripts/adr-acceptance-drift.sh`.

**For ADR-bearing stories**: the story's Definition of Done includes this closeout as part of the
acceptance mechanic — see the `Definition of Done` note in
[`specs_templates/spec_template.md`](../../specs_templates/spec_template.md).

---

## ADR Id Numbering and the Uniqueness Guard (ABS-283)

ADR ids (`ADR-A-NNNN`, `ADR-C-NNNN`, `ADR-P-NNNN`) are the citation keys used in
agent defs, SOPs, tickets, and scripts. An id that points at more than one decision
makes every citation ambiguous. That is not hypothetical: four parallel branches
(ABS-254, ABS-255, ABS-256, ABS-258) each grabbed `ADR-A-0022` while `main` topped
out at `0021`, and `ORCHESTRATOR_SOP.md` ended up citing "ADR-A-0022" for two
different decisions.

**Claim your number late, not early.** Assign the next available id only when you are
ready to commit the file. Seats that grab a number while still drafting block it for
the duration of their branch, which is the root cause of the four-way collision above.

**Mechanical guard.** `tests/test-adr-id-uniqueness.sh` (introduced ABS-283) catches:

- Two ADR files under `adrs/**/*.md` sharing the same frontmatter `id:`.
- A frontmatter `id:` that disagrees with the id encoded in the filename
  (`ADR-A-0023-foo.md` must carry `id: ADR-A-0023`).

The guard runs automatically on two paths: GitHub Actions discovers it via the
`tests/test-*.sh` glob (`.github/workflows/tests.yml`, and `scripts/pre-release-check.sh`),
AND — because the active push remote is GitLab, where GitHub Actions never run — the
`.gitlab-ci.yml` `adr-id-uniqueness` job runs it on the live remote on every push and
merge request (PILOT-59). So a collision surfaces on whichever remote actually gates the
merge, not just at the next confused reader. See
[`docs/ci-cd/GOVERNANCE_SENSOR_ENFORCEMENT.md`](../ci-cd/GOVERNANCE_SENSOR_ENFORCEMENT.md)
for the full sensor→path matrix. Run it locally any time from the repo root:

```bash
bash tests/test-adr-id-uniqueness.sh   # exit 0 = clean; exit 1 = collision found
```

**When a collision does occur,** the resolution rule (from the `ADR-A-0024` renumber
note) is: the ADR already on `origin` retains its number; the remaining colliders
renumber in ticket-id order. The renumber is a governance correction, not an ADR
acceptance — `status:` and decision content stay unchanged (ADR-A-0004 guardrail).

---

## Every Classification Must Name Its Effect (PILOT-69)

**A classification without a named effect is incomplete.** When an ADR introduces a
taxonomy — a set of classes a mechanism sorts inputs into (blocker classes, readiness
states, priority tiers, gate verdicts) — every class MUST name the concrete effect it
produces. A class that is only *detected and recorded* but never *acted on* is not a
decision; it is log-noise, and worse, it invites the reader to assume an effect that does
not exist.

This is not hypothetical. ADR-A-0018 classified blockers into
`environment-denial` / `transient` / `logic`, but only `environment-denial` triggered
anything (the cross-visit auto-park). `transient` was recorded and then ignored by the
very iteration/rework counters it should have spared, so a transient infrastructure abort
kept driving those counters and parked finished work (PILOT-32). ADR-A-0024's
`HANDOFF-CLAIM-NOHASH` advisory was emitted but never counted, so its own written
promotion criterion could be neither met nor struck across six releases.

**Authoring checklist for any new taxonomy:**

- Enumerate the classes AND, per class, the mechanical effect (which counter, which
  transition, which NOTIFY, which gate — with the function/sensor that realizes it).
- If a class is *deliberately* inert (advisory-only, reserved-for-future), say so
  explicitly and name the measure that would end the inertness (a criterion and a review
  cadence), so "does nothing yet" is a decision, not an oversight.
- A class whose effect is "budget-neutral" / "no-op" is fine — but that no-op must be
  *named* and wired, not merely implied by omission.

Enforcement is authoring-review discipline (the System Architect and the Stop-the-Line
rule), not a dedicated sensor — a general "every class is wired" check is not mechanically
decidable across arbitrary taxonomies.

---

## Related Documents

- [`.claude/agents/system-architect.md`](../../.claude/agents/system-architect.md) - Full guided ADR authoring protocol
- [`adrs/agentic/ADR-A-0001-three-level-adr-hierarchy.md`](../../adrs/agentic/ADR-A-0001-three-level-adr-hierarchy.md) - Three-level hierarchy and authority order
- [`adrs/agentic/README.md`](../../adrs/agentic/README.md) - Agentic ADR index and acceptance lifecycle
- `confluence-docs` skill - ADR/runbook/architecture templates
