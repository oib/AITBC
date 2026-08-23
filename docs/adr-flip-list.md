# ADR Enforcement-Status Flip-List (operator decision vehicle)

> **Scope:** the *reverse* acceptance drift — ADRs whose mechanic is already
> enforced by code/sensors (shipped, load-bearing, default-on) but whose file
> frontmatter still says `status: proposed`. The forward direction (accepted in
> the record, file still `proposed`) is guarded by
> `scripts/adr-acceptance-drift.sh`; this
> list covers the direction that had **no sensor** before PILOT-52 / ABS-561.

## What this is

A decision vehicle for the human operator — **not** an action list for agents.
Per **ADR-A-0004**, accepting an ADR (flipping `status:` +
`accepted_by:` + `accepted_date:` in the file frontmatter) is a **human-only**
act. The sensor below only *reports*; it never edits an ADR status.

Each candidate is an ADR that a `kind: enforced` or `kind: derived` row in
[`docs/rule-ledger.yaml`](rule-ledger.yaml) names — meaning a deterministic
sensor already enforces its mechanic (ADR-A-0028 §2) — while the ADR file is
still `proposed`. The ledger row + its sensors are the **Belegstelle** (evidence
of enforcement) that justifies a flip.

## Regenerate (source of truth)

This table is a **snapshot**. The live list is whatever the sensor prints:

```bash
scripts/adr-enforced-status-drift.sh --flip-list   # operator decision lines
scripts/adr-enforced-status-drift.sh               # gate mode: DRIFT: lines, exit 1 on drift
```

The gate mode is **advisory** — do not wire it as a blocking CI gate, because
the tree is *expected* to carry entries here until a human works the list.

## Current candidates (snapshot 2026-07-26)

| ADR | Enforcement Belegstelle (ledger row → sensors) | Flip = human act |
|-----|-------------------------------------------------|------------------|
| [ADR-A-0009](../adrs/agentic/ADR-A-0009-cost-approval-gate.md) — Cost Approval Gate | `R-0303` → `scripts/orchestrator.sh:budget_exhausted`, `tests/orchestrator.d/ABS-293-budget-recovery.sh` | proposed → accepted? (ADR-A-0004) |
| [ADR-A-0024](../adrs/agentic/ADR-A-0024-handoff-commit-verification.md) — Handoff Commit Verification | `R-0319` → `scripts/orchestrator.sh:handoff_work_verified`, `scripts/orchestrator.sh:handoff_claims_commit` | proposed → accepted? (ADR-A-0004) |
| [ADR-A-0025](../adrs/agentic/ADR-A-0025-per-epic-merge-token.md) — Per-Epic Merge Token | `R-0312` → `scripts/orchestrator.sh:merge_token_gate`, `tests/test-merge-token.sh`, `tests/test-merge-wait.sh` | proposed → accepted? (ADR-A-0004) |

> The BEFUND behind ABS-561 also names ADR-A-0016/0021/0022/0023 as shipped-yet-
> `proposed`. They are **not** in this table because no `enforced`/`derived`
> ledger row names them yet — their mechanic has no ledger-tagged sensor, so the
> evidence bar for a flip is not (yet) machine-provable. Add the sensor + ledger
> row first; they then surface here automatically.
