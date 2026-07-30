---
name: duplicate-detection
description: Mandatory dedup gate before any ticket creation. Use BEFORE creating
  any ticket in the tracker. Searches the tracker full-text for identical/similar
  tickets and returns a reject/append/create verdict with matched references and reasoning.
triggers:
- user
- model
allowed-tools:
- exec
- grep
- read
---

# Duplicate Detection Skill

## Purpose

Prevent duplicate tickets, protect sprint scope, and surface regressions. This
skill is a **mandatory pre-creation gate**: no ticket is created in the tracker
until this skill has run and returned a verdict.

**Owner**: Issue Enrichment Agent (`harness/devin/agents/issue-enrichment.md`) — this
skill is executed as a mandatory step of its enrichment pipeline, before any
`create_ticket` call. Other agents that create tickets (e.g. BSA, TDM) must run
this gate too.

## When to Use

Invoke this skill when:

- About to create ANY ticket (epic, ticket, subtask, follow-up, bug)
- Enriching inbound feedback/requests into tickets
- Splitting a spec into stories (gate each story)
- A user or agent reports an issue that "sounds familiar"

## Search Capability (two modes)

The skill talks "search"; configuration decides which tracker answers
(adapter model per `adrs/agentic/ADR-A-0007-adapter-model.md`; active task
tracking per `adrs/agentic/ADR-A-0006-active-task-tracking.md`).

### Production: tracker MCP full-text search

Use the configured tracker MCP. The owning agent's tool configuration MUST
include the tracker MCP server (e.g. `mcp__linear-mcp__*` or the
Jira MCP), otherwise this gate cannot run.

```text
# Jira (JQL full-text)
mcp__jira-mcp__searchJiraIssuesUsingJql({
  jql: 'project = AITBC AND text ~ "password reset email"',
})

# Linear
mcp__linear-mcp__list_issues({
  query: "password reset email",
  team: "{{PROJECT_TEAM_NAME}}",
})
```

### Local/dev: mock adapter

Use the zero-dependency mock tracker (`scripts/mock-tracker.sh`):

```bash
# Case-insensitive substring match against ticket titles AND bodies
scripts/mock-tracker.sh search --text "password reset email"

# Combine with structural filters
scripts/mock-tracker.sh search --text "password reset" --status "In Progress"

# Inspect a candidate match in full
scripts/mock-tracker.sh get DEMO-42
```

### Search protocol

1. Extract 2-4 key phrases from the request (feature nouns, error messages,
   component names). Search each phrase — not just the literal title.
2. Search open AND closed tickets (done tickets matter for rule 2).
3. Read every candidate in full (`get`) before classifying it as identical
   (same defect/request) or similar (overlapping scope).
4. **Concurrent-submission / cross-lineage sweep (ABS-452).** The bare
   full-text search above only catches tickets that already exist against
   *bestand*; it misses near-simultaneous submissions from parallel seats, so
   twin tickets get created in the same minute and their duplicate DDL /
   migrations collide later. Before verdict, run two extra searches:
   - **Sibling lineage** — same trigger/parent. `search --parent <parent>`
     (and, for a review/QAS follow-up, search for the *source* ticket key of
     the thing you are reviewing). Two seats reviewing the same origin file the
     same finding twice.
   - **Recently-opened window** — the last ~72h of OPEN tickets (any status
     except `Done`). The adapter has no time filter, so search by the *concrete
     identifier* of the change and inspect the `updated` field of each match:
     add the **affected file path, DB column, or migration number** as its own
     search phrase (e.g. `--text "migration 010"`, `--text "reason column"`).
     Identical DDL on a not-yet-merged twin is the signal.
   A hit here means the "otherwise → create" default (rule 5) does **not**
   apply — see the cross-lineage rule below.

### Follow-up creation (Security-Review / QAS, `kind: follow-up`) — MANDATORY pre-search

A follow-up ticket (a Security-Review or QAS review that spawns remediation
work) is the single biggest source of cross-lineage twins: parallel reviewers
of parallel stories each raise "the same" finding. **Before creating any
follow-up, the pre-search is mandatory and MUST include both:**

1. the **title core terms** of the finding, AND
2. the **affected file / DB column / migration number** the finding is about.

Then run the sibling-lineage search (`search --parent <parent>`, and search the
**source ticket key** being reviewed) so a co-reviewer's just-filed twin is
found. If either surfaces an open ticket for the same finding → `append`, do not
`create`. This is not optional and is not covered by the plain full-text search
alone.

## Decision Algorithm

**Rule 0 — cross-lineage / concurrent duplicate (evaluated FIRST, ABS-452).**
If the sibling-lineage or recently-opened sweep (search step 4) finds an OPEN
ticket describing the **same concrete change** — same affected file, DB column,
or migration number, or the same finding against the same source ticket —
verdict `append` (fold this into the earlier ticket) or `reject` (point the
requester at it). This holds **even if that earlier ticket is already In
Progress**: a byte-for-byte twin is not a scope extension, so the in-progress
sprint-scope protection (rules 3–4) does **not** shield it. Appending to the
earliest of the pair prevents the twin migration / duplicate-DDL collision this
rule exists to stop. Only when no such concrete-change match exists do the
scope-based rules below apply.

Then apply the first matching rule, in order:

1. Identical ticket exists and is open (not done) → verdict `reject` — return the existing ticket reference; an identical ticket is never created.
2. Identical ticket exists but is already done → root-cause check, then `create` + link: analyze WHY this is requested again although completed (regression / incomplete fix / scope misunderstanding / duplicate feedback), record the finding in the verdict and in the new ticket, linked to the closed one. If the request is fully covered by the done ticket (no new defect) → `reject` with reasoning instead.
3. Similar ticket exists whose scope covers the task AND it has not been started yet → verdict `append` to that ticket. In-progress tickets are NEVER extended (sprint-scope protection).
4. Similar ticket exists but is in progress → verdict `create` + relation link to the in-progress one.
5. Otherwise → verdict `create`.

**Status interpretation** (canonical statuses,
`profiles/neutral/adapters/statuses.yaml`):

| Classification | Canonical statuses                                                                                |
| -------------- | ------------------------------------------------------------------------------------------------- |
| Not started    | `Backlog`, `Ready for Development`                                                                |
| In progress    | `In Progress`, `In Review`, `In Test`, `Ready for Human Acceptance`, `Ready for Merge`, `Blocked` |
| Done           | `Done`                                                                                            |

## Verdict Format

Every gate run returns ALL three fields:

```markdown
**Verdict**: reject | append | create
**Matched**: <ticket reference(s), or "none">
**Reasoning**: <which rule fired and why; for rule 2, the root-cause finding>
```

- `reject` — do not create; hand the requester the matched reference.
- `append` — extend the matched not-started ticket's scope/AC instead of
  creating; comment the addition on that ticket.
- `create` — create the ticket; if rule 2 or 4 fired, also record the link
  (`origin-review`/`depends-on`-style relation, or tracker "relates to") and,
  for rule 2, write the root-cause finding into the new ticket's description.

## Usage Examples

### Example 1: reject — identical and open (rule 1)

Request: "Users can't reset their password via email."

```bash
scripts/mock-tracker.sh search --text "password reset"
# DEMO-12  ticket  In Progress  Fix password reset email not sending
```

```markdown
**Verdict**: reject
**Matched**: DEMO-12
**Reasoning**: Rule 1 — DEMO-12 describes the identical defect and is open
(In Progress). No new ticket; requester pointed to DEMO-12.
```

### Example 2: create + link — identical but done (rule 2, root-cause check)

Request: "Password reset emails are broken again."

```bash
scripts/mock-tracker.sh search --text "password reset"
# DEMO-12  ticket  Done  Fix password reset email not sending
scripts/mock-tracker.sh get DEMO-12   # done 3 weeks ago; fix touched SMTP config
```

Root-cause analysis: fix verified at the time; new reports started after last
week's mail-provider migration → **regression**, not duplicate feedback.

```markdown
**Verdict**: create
**Matched**: DEMO-12 (done)
**Reasoning**: Rule 2 — identical to closed DEMO-12. Root cause: regression
introduced by the mail-provider migration, not an incomplete fix. Creating a
new ticket with this finding in its description, linked to DEMO-12.
```

```bash
NEW=$(scripts/mock-tracker.sh create --type ticket --title "Regression: password reset email broken after mail-provider migration")
scripts/mock-tracker.sh link "$NEW" DEMO-12 origin-review
```

(If analysis had shown the request is fully covered by DEMO-12 — e.g. the
reporter tested against a stale deployment, no new defect — the verdict would
be `reject` with that reasoning instead.)

### Example 3: append — similar, scope covers it, not started (rule 3)

Request: "Add a 'resend verification email' button to the profile page."

```bash
scripts/mock-tracker.sh search --text "verification email"
# DEMO-30  ticket  Backlog  Rework email verification UX on profile page
```

```markdown
**Verdict**: append
**Matched**: DEMO-30
**Reasoning**: Rule 3 — DEMO-30's scope (verification UX on the profile page)
covers this task and it has not been started (Backlog). Appending the resend
button as an acceptance criterion instead of creating a fragment ticket.
```

```bash
mkdir -p work/scratch
printf '%s\n' "Dedup gate: appended scope — add 'resend verification email' button (AC added)." \
  > work/scratch/demo-30-note.md
scripts/mock-tracker.sh comment DEMO-30 --kind decision --actor issue-enrichment \
  --body-file work/scratch/demo-30-note.md
```

### Example 4: create + link — similar but in progress (rule 4)

Same request, but:

```bash
scripts/mock-tracker.sh search --text "verification email"
# DEMO-30  ticket  In Progress  Rework email verification UX on profile page
```

```markdown
**Verdict**: create
**Matched**: DEMO-30 (in progress)
**Reasoning**: Rule 4 — DEMO-30 is similar but already In Progress; in-progress
tickets are never extended (sprint-scope protection). Creating a separate
ticket with a relation link to DEMO-30.
```

```bash
NEW=$(scripts/mock-tracker.sh create --type ticket --title "Add resend-verification-email button to profile page")
scripts/mock-tracker.sh link "$NEW" DEMO-30 depends-on
```

### Example 5: plain create — no match (rule 5)

Request: "Export the audit log as CSV."

```bash
scripts/mock-tracker.sh search --text "audit log"
scripts/mock-tracker.sh search --text "csv export"
# (no output)
```

```markdown
**Verdict**: create
**Matched**: none
**Reasoning**: Rule 5 — no identical or similar ticket found across title/body
search for "audit log" and "csv export". Creating a new ticket.
```

### Example 6: append — cross-lineage concurrent twin (Rule 0, ABS-452 conformance scenario)

This is the **conformance test for AC1**: it reproduces the ABS-447 vs ABS-448
case, where two Security-Reviews of two parallel stories (ABS-439 / ABS-444)
each about to file the *same* finding and required an operator dedup-merge.

Follow-up request (as a Security-Review of ABS-444): "Persist the reason value
before mutating; add reason column via migration 010."

Bare full-text search alone would miss the twin because the co-reviewer filed
ABS-447 seconds earlier. The mandatory follow-up pre-search (title core terms +
affected column/migration) plus the sibling-lineage sweep finds it:

```bash
# 1. title core terms + the concrete identifier (column + migration number)
"$TRACKER_CMD" search --text "reason column"
"$TRACKER_CMD" search --text "migration 010"
# ABS-447  ticket  In Progress  Persist reason before mutate — add reason column (migration 010)
# 2. sibling lineage — same trigger/parent + the source ticket key under review
"$TRACKER_CMD" search --parent ABS-430
"$TRACKER_CMD" get ABS-447   # updated 40s ago; identical DDL for migration 010
```

```markdown
**Verdict**: append
**Matched**: ABS-447 (In Progress, opened <72h, sibling lineage)
**Reasoning**: Rule 0 — ABS-447 describes the same concrete change (reason
column, migration 010) filed seconds earlier by the parallel Security-Review.
A byte-for-byte twin is not a scope extension, so the in-progress protection
(rules 3–4) does not shield it. Appending this finding to ABS-447 instead of
creating ABS-448 — prevents the twin migration-010 DDL / merge-conflict collision.
```

```bash
mkdir -p work/scratch
printf '%s\n' "Dedup gate (Rule 0, ABS-452): same finding as concurrent sibling ABS-447 (reason column, migration 010). Folded in here instead of creating a twin." \
  > work/scratch/abs447-note.md
"$TRACKER_CMD" comment ABS-447 --kind decision --actor security-engineer \
  --body-file work/scratch/abs447-note.md
```

## Authoritative References

- **Owning agent**: `harness/devin/agents/issue-enrichment.md` (ABS-8)
- **Adapter model**: `adrs/agentic/ADR-A-0007-adapter-model.md`
- **Active task tracking**: `adrs/agentic/ADR-A-0006-active-task-tracking.md`
- **Mock adapter**: `scripts/mock-tracker.sh` (`search --text`)
- **Status machine**: `profiles/neutral/adapters/statuses.yaml`
- **Ticket SOP**: `linear-sop` skill / `docs/sop/AGENT_WORKFLOW_SOP.md`
