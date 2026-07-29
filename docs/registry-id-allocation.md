# Id allocation for sequential registries (ABS-600)

Several registries in this repo hand out sequential ids: the rule-ledger
(`R-NNNN`), the ADR set (`ADR-A-NNNN`), and the SQL migrations (`NNN_*.sql`).
Each is append-only, and — until ABS-600 — each new entry took **the next
number after the highest one on the author's own branch**.

That allocation rule is a function of the *branch*, not of the *work*. Parallel
stories fork from the same base, each sees the same "highest", and each picks
the same "next". On their own branches the guard is green; at integration the
ids collide. This is not an edge case — parallel stories are the normal operating
mode of the epic-branch model, so the collision is **inevitable**, not unlucky.

Evidence that it is a recurring *class*, not a one-off:

- **Rule-ledger (Pilot 8, 2026-07-27):** four stories (PILOT-75/76/79/81) each
  read `R-1108` and started at `R-1109`; integrated, `R-1109..R-1116` existed
  two-to-four times and `rule-ledger-check` C1 was the last red sensor on the
  epic tip. Resolution cost an operator renumber of 12 rows.
- **Migrations (ABS-428 / ABS-449):** `010_*.sql` was allocated twice across
  parallel branches; already has a guard (see below).
- **ADRs (ABS-558 / ABS-560):** `ADR-A-0028` was allocated twice and had to be
  renumbered to `ADR-A-0029`.

## The rule

> **A sequential id that serves as a stable *reference* (not an *ordering*) is
> derived from the globally-unique ticket that introduces it — never from a
> branch-local running counter.**
>
> New ids take the form `R-<TICKET>-<n>` / `ADR-<TICKET>-<n>`, where `<TICKET>`
> is the introducing ticket (e.g. `ABS-600`) and `<n>` counts that ticket's own
> entries.

### Why derive from the ticket (candidate (a)), and not the alternatives

The ticket (AC1) listed four candidates to weigh. The deciding property is
**collision-freedom by construction on parallel branches, with no cross-branch
coordination** — because coordination is exactly what parallel seats cannot do.

- **(a) Derive from the ticket — CHOSEN.** The tracker mints ticket ids
  centrally and never in parallel, so two different tickets can never share a
  prefix, and within one ticket only one seat allocates. The id is therefore
  unique the moment it is minted, with **zero** shared state to coordinate. Every
  seat already knows its ticket id, so the mechanism is a one-liner
  (`scripts/next-rule-ledger-id.sh`) with no ref scan. Laziest thing that
  actually dissolves the class rather than gating it.
- **(b) Allocate at merge, by the runner.** Moves file-rewriting into the merge
  machinery and re-runs guards on rewritten content — heavy, fragile, and it
  still needs a counter somewhere. Rejected.
- **(c) Reservation blocks per story.** Needs a shared reservation registry that
  is itself edited in parallel — the same collision, one level up. Rejected.
- **(d) Drop ids, key by (file, heading).** Viable for the rule-ledger (whose
  anchoring is *already* `(file, heading)`), but it throws away the stable
  citation key that agent defs, SOPs and tickets cite by id, and it is
  impossible for ADRs (the filename **is** the id) and migrations (the prefix
  **is** the order). Non-uniform. Rejected as the common rule.

## How the rule applies to each registry (AC2)

| Registry | Id | Status under this rule |
| --- | --- | --- |
| `docs/rule-ledger.yaml` | `R-…` | **Adopted + enforced now.** New rows use `R-<TICKET>-<n>`; mint with `scripts/next-rule-ledger-id.sh <TICKET>`. `scripts/rule-ledger-check.sh` C1 accepts the ticket-scoped form, keeps the duplicate backstop, and now names the file+heading of each colliding row. Proven by `tests/test-registry-id-parallel.sh`. Legacy `R-NNNN` ids are frozen. |
| ADR numbers | `ADR-A-…` | **Same rule; format change routed to the System Architect.** The ADR id is a widely-cited *citation key*, and every ADR tool (`name_id`, `adr-reference-lint`, `adr-enforced-status-drift`) is hard-coded to `ADR-A-[0-9]+`. Redefining that convention is an architectural decision owned by the System Architect (belongs in `ADR-A-0001`, per the ADR audit item #6), not a unilateral dev change. The result backstop `tests/test-adr-id-uniqueness.sh` (keyed on the filename, so a frontmatter-less file can't hide) stays in place meanwhile. **Follow-up: ADR-authoring-request to extend `ADR-A-0001` with ticket-scoped ids + update the four ADR tools together.** |
| Migrations (`NNN_*.sql`) | `NNN` | **Exempt — the prefix encodes execution ORDER, which a ticket id does not provide.** Migrations must apply in a defined sequence, so they cannot be ticket-scoped. This registry keeps its existing coordination: `scripts/next-migration-number.sh` reserves the next free number across known refs, and `scripts/migration-number-collision-check.sh` is a merge-base pre-merge gate (ABS-428 / ABS-449). |

## The backstop stays (AC4)

Ticket-scoping prevents the collision; it does not replace the duplicate check.
`rule-ledger-check.sh` C1 still fails on any duplicate id (e.g. a legacy row
copied by hand), and its message now points straight at the colliding rows:

```
RULE-LEDGER: C1: duplicate rule ids: R-0002
    R-0002  <-  docs/RULES.md  ›  "Rule A1"
    R-0002  <-  docs/RULES.md  ›  "Rule B1"
```
