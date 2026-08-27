# ABS-124 Design Spec — Review-Gate Sizing per Ticket (Skip Matrix + Opt-out Flags)

**Ticket**: ABS-124 (epic ABS-114) · **Status**: accepted — the skip matrix is architect-approved
(mandatory review 2026-07-07: CHANGES REQUESTED, matrix confirmed conditional on F1–F5, all
incorporated: F1 `skip-test` is v3-story-only — parentless/v1 tickets are INELIGIBLE (their In
Test skip would derail past the human Ready-for-Merge gate onto the v3 auto-merge tail);
F2 `skip-test ⟹ skip-review` — violating it is a CONTRADICTION (claiming "nothing testable"
while refusing "no executable code"); F3 the gate-skip targets get their own map
(`gate_skip_target` — `skip_forward_target` knows only the conditional stages);
F4 a dedicated `gate_skip` function with `GATE-SKIP`/`GATE-SKIP-CONTRADICTION`/
`GATE-SKIP-INELIGIBLE` events and a comment naming the SET flag (the ABS-84 "flag not set" text
would lie here); F5 test plan extended accordingly. `skip-review` alone is explicitly ALLOWED —
review sized away, the stricter test gate still runs) · **Date**: 2026-07-07

## 0. Goal

At ticket creation (BSA decomposition / enrichment) it is decided which review/test gates a
ticket actually needs — a docs-only or trivial ticket stops paying a full seat duration + tokens
for architecture/security/QAS seats it cannot benefit from. Operator decisions (binding):
opt-OUT default (no flags → ALL gates exactly as today; savings only on deliberately flagged
tickets), QAS is sizable for restrictively defined trivial cases (last content check is then the
PO acceptance), ownership is mechanical (BSA primary + enrichment fallback per the
architect-approved matrix — no per-ticket ack), the human merge gate is NEVER sizable.

## 1. The skip matrix  `#PATH_DECISION` (architect review MANDATORY)

| Gate (status) | Seat | Sizing | Mechanism |
|---|---|---|---|
| Design / Design Test | ui-ux-design / qas-design | opt-IN via `design` flag (existing) | ABS-84 SKIP-FORWARD, unchanged |
| Security Review | security-engineer | opt-IN via `security` flag (existing) | ABS-84 SKIP-FORWARD, unchanged — a set `security` flag ALWAYS runs the gate; no opt-out exists that could remove it (the ticket's "mandatory flags win" AC holds by construction) |
| Test Prep | data-provisioning-eng | opt-IN via `data` flag (existing) | unchanged |
| **In Review** (code/architecture review) | system-architect | opt-OUT via `skip-review` flag | NEW gate-skip: runner re-transitions `In Review → Security Review` (the v3 pass route; the conditional machinery then skips onward for unflagged tickets) — audit comment + run.log event, no spawn, no budget |
| **In Test** (QAS) | qas | opt-OUT via `skip-test` flag, TRIVIAL-ONLY | NEW gate-skip: `In Test → Design Test` (conditional machinery continues to Story Acceptance) |
| Story Acceptance (PO) | po-agent | NEVER | untouched — the PO acceptance remains the last content check for every ticket |
| Ready for Merge / Ready for Epic Acceptance (human) | human | NEVER | human-owned resting statuses; no flag reaches them (negative test) |

Skip criteria (restrictive, set by BSA/enrichment per the matrix):
- `skip-review`: docs-only changes, label/metadata fixes, comment-only edits — no executable code
  touched.
- `skip-test`: strict subset of skip-review cases where nothing is testable (pure docs/label
  fixes). Never for anything touching code, config, schemas or scripts.

Fail-safe rules (operator-decided): missing flags → all gates. CONTRADICTORY flags → all gates:
a `skip-review`/`skip-test` flag combined with ANY opt-in flag (`design`, `security`, `data`) is
contradictory by definition (those flags assert non-trivial content) — the runner ignores the
skip flags, logs `GATE-SKIP-CONTRADICTION`, and every gate runs. Every executed skip is loud:
`kind: skip` audit comment on the ticket (naming the flag) + `GATE-SKIP` run.log event; the flag
justification lives in the ticket body (enrichment guidance).

## 2. Runner implementation

In `dispatch()`'s SPAWN branch, directly after the existing conditional SKIP-FORWARD block: when
`to` is `In Review` or `In Test` and the (re-read) ticket carries the matching skip flag and NO
contradictory opt-in flag, perform the gate skip exactly like `skip_forward` (audit comment,
re-transition to the matrix target, `DISPATCHED_CYCLE` guard, no spawn, no budget). Flags ride
the existing `flags:` frontmatter (mock) / flag-labels (Jira) — the same `ticket_has_flag`
plumbing as ABS-84; no new field or schema (ADR-A-0010).

## 3. Ownership

The matrix above is policy, approved once by the architect review of this spec (ADR-A-0004:
architect/PO set policy, agents apply it mechanically). BSA sets the flags at decomposition;
the enrichment gate adds them as fallback (same pattern as the ABS-121 model label); guidance in
both defs including the justification-in-body requirement.

## 4. Test plan

- docs-only fixture with `skip-review`+`skip-test` → dry-run transition log shows In Review and
  In Test passed WITHOUT seat spawns (audit comments present), PO acceptance still dispatched
- ticket without flags → all gates unchanged (regression)
- contradictory: `skip-review`+`security` → all gates run + `GATE-SKIP-CONTRADICTION` event;
  `security` flag still spawns the security seat (mandatory-flag precedence)
- human merge gate: no flag combination changes the Ready for Merge NOOP row (negative test)
- every skip appears as `GATE-SKIP` in run.log + `kind: skip` comment on the ticket
