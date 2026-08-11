# JOIN-Gate Exemption — Operator Guide

**Scope**: `scripts/orchestrator.sh` — `join_check_epic` / ABS-210
**Status**: Shipped v2.24.x (commit `ea517f4`)
**See also**: [ORCHESTRATOR_SOP.md §JOIN rule + guards](ORCHESTRATOR_SOP.md#join-rule--guards-spec-31-36)

---

## Problem it solves

Before ABS-210 the epic JOIN gate required **all** children to be `Done`. A
deliberately-parked optional child — for example a TDM external-dependency
triage that will never resolve in the current run — held the epic silently in
`Stories In Flight` until an operator adjudicated manually (ABS-181/ABS-189,
>20 min stall). There was no machine-readable signal to distinguish a genuine
blocker from an intentionally parked one.

The exemption mechanism adds exactly that signal.

---

## When to use it

Apply an exemption when **all** of the following hold:

1. The child is genuinely optional or externally-dependent — completing it in
   this run is not a prerequisite for the epic's acceptance criteria.
2. A triage seat (TDM or PO) has consciously decided to park it for this run.
3. Every other child of the epic is already `Done` (or will be once the current
   stories land).

**Do not** use it to skip a child that is merely slow, has an unresolved
follow-up, or is a genuine scope blocker. The JOIN gate's `AC2` guarantee — a
child without the marker keeps the gate open and names itself — exists to catch
that case.

---

## Runner enforcement (ABS-297)

Since ABS-297 the runner verifies the `JOIN-EXEMPT (triage)` marker **before accepting a handoff
that claims it**. A po-agent handoff that declares a child exempt — but has not yet posted the
marker on that child — is **refused**: no transition is applied, a `MARKER-MISSING` gate-results
comment names the required marker and the child ticket, and the seat is re-spawned to fix it.

**Implication for po-agent seats**: post the `kind: decision` marker on the child *first*, then
include the claim in the handoff. The order matters.

---

## How to apply the exemption

Post a **`kind: decision` comment** on the **child ticket** (not the epic) whose
body contains the exact marker text:

```
JOIN-EXEMPT (triage)
```

The comment header must match the tracker's `kind: decision` format:

```
### <ISO-8601-timestamp> | kind: decision | actor: <your-role>

Rationale: <why this child is parked>. JOIN-EXEMPT (triage)
```

### What the marker must be

| Requirement | Detail |
|-------------|--------|
| **Exact text** | `JOIN-EXEMPT (triage)` — case-sensitive, verbatim |
| **Comment kind** | `kind: decision` header — not `kind: handoff`, `kind: gate-results`, or any other kind |
| **Location** | On the **child ticket** that is parked, not on the epic |
| **Author** | Any actor a triage seat (TDM/PO) uses; the runner checks the body, not the actor |

### What the marker must not be

- A plain mention in a `kind: handoff`, `kind: gate-results`, or free-text
  comment — the awk parser ignores the marker unless it appears inside a
  `kind: decision` comment body. This is the ADR-A-0019 "declared marker"
  anchoring: a stray quote in a status update cannot accidentally exempt a child.

---

## What the runner does next

At the next JOIN evaluation the runner calls `join_check_epic` for the epic.
It partitions the not-`Done` children into two sets:

| Set | Criteria | Effect |
|-----|----------|--------|
| **Exempt** | carries `JOIN-EXEMPT (triage)` in a `kind: decision` body | excluded from the blocker count |
| **Pending** | not `Done` and no marker | genuine blocker; gate stays closed |

**All-exempt-or-Done path** — no pending children remain → epic transitions to
`Epic Integration`; the runner emits:

```
INTENT JOIN-EXEMPT <epic-id> - Stories In Flight exempt-children:<child-id>
```

**Genuine-blocker path** — at least one pending child → gate stays open; the
runner emits once (not on every poll):

```
INTENT JOIN-WAIT <epic-id> - Stories In Flight pending-children:<child-id>
```

**Mixed path** (exempt child + genuine blocker) — gate stays open; the pending
child is named and the exempt child is also logged, so the operator can see both
at a glance.

---

## Scope constraints (ABS-210)

The exemption changes **only the JOIN evaluation**. It does not:

- Cancel the child ticket or change its status.
- alter Blocked/TDM-triage semantics (ABS-76 is unchanged).
- auto-resolve the child or remove it from the epic's child list.

The child remains parked in whatever status it is in. If the situation changes
and the child becomes feasible again, a triage seat removes or supersedes the
`kind: decision` comment (or adds a new `kind: decision` comment that overrides
the intent); at the next JOIN sweep the runner re-evaluates.

---

## Troubleshooting

### Epic still sitting in `Stories In Flight` after posting the marker

1. **Check the comment kind.** Open the child ticket and verify the comment
   header says `kind: decision`. A `kind: handoff` or `kind: gate-results`
   comment is not scanned.
2. **Check the exact text.** The awk parser does a substring match on
   `JOIN-EXEMPT (triage)`. Extra spaces inside the parentheses or a different
   capitalisation will cause a miss.
3. **Check which ticket you posted on.** The marker must be on the **child**,
   not on the epic.
4. **Wait for the next reconcile sweep.** JOIN evaluation fires when a child
   reaches `Done` or on the next reconcile cadence, whichever comes first. If
   all other children are already `Done`, the next sweep will fire JOIN.

### Log says `INTENT JOIN-WAIT` with the child you exempted as `pending-children`

The marker was not found. Apply checks 1–3 above.

### Log says `INTENT JOIN-EXEMPT` but epic did not transition

Another child is genuinely pending (`INTENT JOIN-WAIT` will also appear naming
it). The exemption fired correctly; the genuine blocker is the gate-holder.

---

## References

- `scripts/orchestrator.sh` — `join_exempt_marker()`, `child_join_exempt()`, `join_check_epic()`
- `tests/tooling/test-orchestrator.sh` — ABS-210 JOIN exemption section (13 assertions)
- [ORCHESTRATOR_SOP.md §JOIN rule + guards](ORCHESTRATOR_SOP.md#join-rule--guards-spec-31-36) — inline guard description
- ADR-A-0019 — declared-marker pattern (escalation-resume-to-origin)
- ABS-76 — Blocked/TDM-triage semantics (explicitly out of scope here)
- ABS-181/ABS-189 — origin incident (JOIN stalled >20 min on parked child)
