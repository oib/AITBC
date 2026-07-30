---
name: issue-enrichment
description: Agent-ready ticket formatting and guardrail annotation before ticket
  creation. Use AFTER the duplicate-detection gate returns an append/create verdict.
  Formats a drafted requirement into the goal/scope/acceptance-criteria/references
  structure, runs the guardrail-feasibility checklist (ADR hierarchy, human-approval
  boundaries, minimal-change default), and produces the guardrail annotation block
  written into the ticket body.
triggers:
- user
- model
allowed-tools:
- exec
- grep
- read
---

# Issue Enrichment Skill

## Purpose

Turn a drafted requirement into an **agent-ready ticket**: structured so an
implementing agent can act on it without clarification, and annotated with the
guardrails that constrain it. This skill formats and annotates — it NEVER adds
requirements the draft does not contain.

**Owner**: Issue Enrichment Agent (`harness/devin/agents/issue-enrichment.md`) — this
skill runs as step 2 of its enrichment pipeline, strictly AFTER the
`duplicate-detection` skill has returned an `append` or `create` verdict and
strictly BEFORE any tracker operation.

## When to Use

Invoke this skill when:

- The dedup gate returned `create` — format the draft into a new ticket body
- The dedup gate returned `append` — format the addition for the matched ticket
- A ticket body needs a guardrail-feasibility re-check after scope changes

## Agent-Ready Ticket Template

```markdown
# [Title — concise, action-oriented, from the draft]

## Goal

[Observable end state, one short paragraph. From the draft's Problem +
Desired Outcome — rephrased, not extended.]

## Scope

- **In scope**: [explicit boundaries from the draft]
- **Out of scope**: [explicit exclusions from the draft]

## Acceptance Criteria

- [ ] [Specific, testable criterion — from the draft's acceptance hints]
- [ ] [Specific, testable criterion]

## References

- **Origin**: [source agent + context ticket, e.g. "SecEng audit, AITBC-142"]
- **Related**: [tickets/links from the dedup verdict, or "none"]
- **Patterns/Specs**: [relevant `patterns_library/` or `specs/` references, or "none"]

## Guardrail Annotation

[See annotation block format below]
```

Formatting rules:

1. Every section maps back to draft content. A missing section means the draft
   is too thin → return it to the requester with specific questions. Never fill
   gaps with assumptions.
2. Acceptance criteria must be individually testable (one observable outcome
   per checkbox).
3. Links from the dedup verdict (matched done/in-progress tickets) go under
   **References → Related** AND are recorded in the tracker as links.
4. **Executed AC for procedural deliverables**: every ticket that defines a
   procedure an agent will follow (a charter, an SOP section, a workflow)
   MUST include at least one acceptance criterion that EXECUTES the
   procedure's command sequence and asserts its postcondition — even a cheap
   non-LLM simulation counts (bash the charter's adapter commands against the
   mock tracker and assert the postcondition). Grep-only ACs are insufficient
   for procedural deliverables: the gates verify exactly the ACs, and a grep
   proves the text exists, not that the procedure works.

   Worked example (the ABS-60 gap): the decomposition charter's `create`
   command could not persist the enriched child body (children stayed
   `_TBD_`). Every command in the charter was individually real, but the
   procedure could not achieve its postcondition — and all three gates passed
   it because every AC was a grep or suite run. The executed AC that catches
   it in seconds — `create` a child, then `get` it and assert the body is not
   `_TBD_`:

   ```bash
   mkdir -p work/scratch
   BODY_FILE="work/scratch/enrichment-body-sim.md"
   printf '# Simulated child\n\nEnriched goal/scope/AC body.\n' > "$BODY_FILE"
   CHILD=$(scripts/mock-tracker.sh create --type ticket \
     --title "Executed-AC simulation" --body-file "$BODY_FILE")
   scripts/mock-tracker.sh get "$CHILD" | grep -q '_TBD_' \
     && echo "FAIL: enrichment output dropped" || echo "PASS: body persisted"
   ```

   This AC fails against the pre-fix adapter.
5. **Every claimed file gets an AC**: each file the ticket claims to change
   must appear in at least one acceptance criterion (a grep or diff assertion
   against that file). If no AC names a file, no gate checks it — ABS-61
   shipped without its claimed `po-agent.md` section because no AC named the
   file.

## Guardrail-Feasibility Checklist

Run every check; record the outcome per check. Any `block` stops the pipeline —
the ticket is NOT created; the draft returns to the requester with the failed
check and reasoning.

| # | Check | Against | Outcome |
| - | ----- | ------- | ------- |
| 1 | **ADR hierarchy conflict** — does the requested work contradict an accepted ADR? Resolve by authority order: project > company > agentic. | `adrs/agentic/ADR-A-0001-three-level-adr-hierarchy.md` + the `adrs/` tree | Contradicts an accepted ADR → `block`. Touches an ADR's subject without contradicting it → `flag` (name the ADR in the annotation). |
| 2 | **Human-approval boundaries** — does fulfillment require merging to a protected branch, deploying to production, accepting an ADR, or incurring license/LLM costs? | `adrs/agentic/ADR-A-0004-human-approval-boundaries.md` | Only satisfiable by an agent crossing a boundary → `block`. Requires a human approval step along the way → `flag` (name the boundary in the annotation). |
| 3 | **Minimal-change default** — does the draft demand a broad refactor, rewrite, or dependency sprawl inside a feature ticket? | `adrs/agentic/ADR-A-0010-minimal-change-default.md` | Inherently a broad refactor disguised as a feature → `block` (route back: refactors need their own prioritized ticket). Feature satisfiable minimally but with refactor temptation nearby → `flag` (state the minimal-change constraint in the annotation). |

Aggregate feasibility:

- All checks `pass` → **pass**
- Any `flag`, no `block` → **flagged** — create the ticket WITH the annotation
- Any `block` → **blocked** — do not create; return to requester

## Guardrail Annotation Block Format

This block is written into the ticket body (last section of the template):

```markdown
## Guardrail Annotation

- **Feasibility**: pass | flagged
- **Applicable ADRs**: [ADR ids + one-line relevance each, or "none beyond defaults"]
- **Approval Boundaries**: [human approvals required per ADR-A-0004, or "none"]
- **Constraints**: [minimal-change scope notes per ADR-A-0010; other constraints]
```

For a `blocked` outcome, no ticket exists — the same fields go into the return
message to the requester instead, plus which check fired and why.

## Worked Example: Input Draft → Enriched Ticket

Input — a BSA Follow-Up Ticket Draft (per `docs/sop/FOLLOW_UP_TICKET_SOP.md`):

```markdown
## Follow-Up Ticket Draft

- **Title**: Add rate limiting to webhook endpoints
- **Problem**: Webhook endpoints accept unlimited requests; SecEng audit on AITBC-142 flagged abuse potential
- **Desired Outcome**: All webhook endpoints reject requests exceeding a configurable rate threshold
- **Scope**: In: webhook routes, middleware, configuration. Out: non-webhook API routes, WAF-level controls
- **Acceptance Hints**: Requests over threshold return 429; limits configurable per endpoint; existing webhook tests still pass
- **Origin**: SecEng audit, AITBC-142
```

Dedup gate already returned `create` (no match). Guardrail checks: (1) no ADR
contradiction — pass; (2) no merge/deploy/cost required of an agent — pass;
(3) middleware addition is scoped, but "all webhook endpoints" invites a
routing refactor — `flag` with a minimal-change constraint. Feasibility:
**flagged** → create with annotation.

Output — the enriched ticket body:

```markdown
# Add rate limiting to webhook endpoints

## Goal

All webhook endpoints reject requests exceeding a configurable rate
threshold, closing the abuse potential flagged by the SecEng audit.

## Scope

- **In scope**: webhook routes, rate-limiting middleware, configuration
- **Out of scope**: non-webhook API routes, WAF-level controls

## Acceptance Criteria

- [ ] Requests over the threshold return HTTP 429
- [ ] Rate limits are configurable per endpoint
- [ ] Existing webhook tests still pass

## References

- **Origin**: SecEng audit, AITBC-142
- **Related**: none (dedup verdict: create, no match)
- **Patterns/Specs**: patterns_library/api/webhook-handler.md

## Guardrail Annotation

- **Feasibility**: flagged
- **Applicable ADRs**: ADR-A-0010 (minimal-change default applies to the middleware integration)
- **Approval Boundaries**: none — no merge/deploy/cost action required of agents (ADR-A-0004 default still applies to the eventual PR merge)
- **Constraints**: Add middleware at the existing webhook route boundary; do NOT restructure webhook routing to "unify" endpoints — a routing refactor is out of scope and would need its own ticket (ADR-A-0010)
```

Then the tracker operation (local/dev, mock adapter). Persist the enriched body
by writing it to a body-draft file under the **sanctioned scratch path
`work/scratch/`** and passing it via `--body-file` — without that flag the
adapter seeds the `_TBD_` template and the enrichment output is dropped.
`work/scratch/**` is the default because it is the one repo-relative path in the
`Write`/`Edit` allowlist of `.claude/settings.template.json` and it is gitignored
(ABS-253); a repo-root path or a bare `$(mktemp)` is outside the allowlist, so
the `Write` is denied under `--permission-mode dontAsk` and the body is lost
silently. Never write `work/tickets/*.md` directly; ticket bodies are persisted
only through the adapter (adapter-only boundary, ADR-A-0007):

```bash
mkdir -p work/scratch
BODY_FILE="work/scratch/enrichment-body-rate-limiting.md"
cat > "$BODY_FILE" <<'EOF'
# Add rate limiting to webhook endpoints
... enriched goal/scope/AC/references + guardrail annotation ...
EOF
NEW=$(scripts/mock-tracker.sh create --type ticket \
  --title "Add rate limiting to webhook endpoints" --body-file "$BODY_FILE")
printf '%s\n' "Enriched ticket body (goal/scope/AC/references + guardrail annotation) — see draft origin AITBC-142." \
  > work/scratch/enrichment-handoff.md
scripts/mock-tracker.sh comment "$NEW" --kind handoff --actor issue-enrichment \
  --body-file work/scratch/enrichment-handoff.md
```

### `append` verdicts and AC-rework: rewrite the body (ABS-252)

An `append` verdict — and any AC-rework after enrichment — **rewrites the matched
ticket's body** through the adapter. Do not patch scope/AC with a comment alone:
the comment is the audit trail, but the BODY is what the implementer reads, and a
body that still shows the pre-rework ACs sends the seat at the wrong target.

```bash
mkdir -p work/scratch
"${TRACKER_CMD:-scripts/mock-tracker.sh}" get "$MATCH" > work/scratch/match-current.md
BODY_FILE="work/scratch/match-body.md"
# ...merge the addition into the full goal/scope/AC body -> "$BODY_FILE"
#    (body only: NO frontmatter, NO comments, NO bare `## Comments` heading —
#     the mock uses that line as the body/comments boundary; carrying it in
#     $BODY_FILE confuses a later rewrite; the Jira binding is immune)...
"${TRACKER_CMD:-scripts/mock-tracker.sh}" update "$MATCH" body-file "$BODY_FILE"
printf '%s\n' "Appended scope from draft AITBC-142; body reworked (AC3 added)." \
  > work/scratch/append-handoff.md
"${TRACKER_CMD:-scripts/mock-tracker.sh}" comment "$MATCH" --kind handoff --actor issue-enrichment \
  --body-file work/scratch/append-handoff.md
```

`update … body-file` REPLACES the body and preserves the frontmatter and every
existing comment — so `$BODY_FILE` must carry the ticket's FULL scope/AC, not just
the delta. Prefer `body-file` over the inline `update <id> body "<text>"` form: a
body containing `<` or `>` on the command line is read as shell redirection under
`dontAsk` and denied (ABS-163).

## Authoritative References

- **Owning agent**: `harness/devin/agents/issue-enrichment.md` (ABS-8)
- **Upstream gate**: `harness/devin/skills/duplicate-detection/SKILL.md` (runs FIRST, always)
- **ADR hierarchy**: `adrs/agentic/ADR-A-0001-three-level-adr-hierarchy.md`
- **Approval boundaries**: `adrs/agentic/ADR-A-0004-human-approval-boundaries.md`
- **Minimal-change default**: `adrs/agentic/ADR-A-0010-minimal-change-default.md`
- **Adapter model**: `adrs/agentic/ADR-A-0007-adapter-model.md`
- **Mock adapter**: `scripts/mock-tracker.sh`
- **Upstream SOP**: `docs/sop/FOLLOW_UP_TICKET_SOP.md`
