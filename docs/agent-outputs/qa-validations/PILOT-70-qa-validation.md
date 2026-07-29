# QA Validation — PILOT-70

**Branch:** PILOT-70-auto  
**Commit:** cfd5a6d1fb40b5089020cbb6f3ab292afe4451ef  
**Date:** 2026-07-26  
**Validator:** QAS

---

## Acceptance Criteria Verification

### AC 1: `tests/test-rule-ledger.sh` green (19/19, no C4 on tdm.md)

**PASS**

```
=== Test Results ===
  Total:  19
  Passed: 19
  Failed: 0
  ALL TESTS PASSED
```

`scripts/rule-ledger-check.sh` output: `rule-ledger-check: OK — every scoped rule section has a declared enforcement status.`

### AC 2: Exactly two new ledger rows; heading text exact-matches tdm.md

**PASS**

| Row   | Ledger heading text                                                      | tdm.md line | Source text                                                              | Match |
|-------|--------------------------------------------------------------------------|-------------|--------------------------------------------------------------------------|-------|
| R-1107 | `Ops-Sweep (cadence-triggered janitor, PILOT-42)`                       | 420         | `## Ops-Sweep (cadence-triggered janitor, PILOT-42)`                    | ✅    |
| R-1108 | `Tier activation (PILOT-43) — act ONLY on what the packet enables`      | 454         | `### Tier activation (PILOT-43) — act ONLY on what the packet enables`  | ✅    |

IDs R-1107/R-1108 are unique in the ledger (R-1106 and R-1109 are the nearest neighbours, no collision).

### AC 3: `kind`/sensors justified from PILOT-42/43 context

**PASS**

Both rows use `kind: unenforced`. The rationale in the commit message and `risk:` fields is sound:

- **PILOT-42 sensor** (`tests/orchestrator.d/PILOT-42-ops-sweep-cadence.sh`) pins runner-side dispatch (`INTENT OPS-SWEEP`) and cadence marker seeding. It does not test whether the seat refrains from ticket transitions during Phase 0 — that is LLM adherence only.
- **PILOT-43 sensor** (`tests/orchestrator.d/PILOT-43-ops-sweep-tiers.sh`) pins packet phase/tiers normalization and the no-opt-in=shadow guard. It does not verify the seat acts only on enabled tiers — again LLM adherence only.

`kind: unenforced` with explicit `risk:` fields is correct per the ledger header's wrong-sensor-trap warning. Assigning either sensor as `enforcing` these seat-restraint properties would be false.

### AC 4: ABS-317 mirror parity

**PASS (N/A)**

The fix commit changes only `docs/rule-ledger.yaml`. No `harness/claude/agents/*.md` or `harness/claude/skills/*` file was touched. `generate-governor.sh --providers` is not required.

---

## Diff scope check

```
docs/rule-ledger.yaml   +10 lines (two YAML mapping blocks)
```

No tdm.md prose changed. No other files touched. Scope matches the ticket's IN/OUT bounds.

---

## Verdict

**APPROVED** — all four ACs met, test suite 19/19, diff minimal and correct.
