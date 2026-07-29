# QA Validation — ABS-600

**Verdict: APPROVED**
Ticket-scoped id allocation for parallel-safe registries.

- Branch: `ABS-600-auto`
- Commit under test: `8f14d0aa` (pushed to `gitlab/ABS-600-auto`)
- Baseline commit: `cf859028` (main, measured back-to-back in throwaway worktree)
- QAS run date: 2026-07-27

---

## Acceptance Criteria

### AC1 — Common rule, justified candidate choice

**PASS.** `docs/registry-id-allocation.md` (77 lines, new) documents the rule and evaluates all four candidates from the ticket:

- (a) Ticket-scoped: **CHOSEN.** Tracker mints ticket ids centrally and never in parallel, so `R-<TICKET>-<n>` is unique at mint time with zero cross-branch coordination.
- (b) Runner-allocated at merge: rejected — moves file-rewriting into merge machinery; still needs a counter.
- (c) Reservation blocks: rejected — a reservation registry is itself edited in parallel (same problem one level up).
- (d) Key by file+heading: rejected — viable for the rule-ledger but impossible for migrations (prefix = order) and ADRs (filename = id); non-uniform.

The justification is grounded in the property that dissolves the class: collision-freedom by construction with no shared state.

### AC2 — Rule applied uniformly; exemptions documented

**PASS.** All three registries covered in `docs/registry-id-allocation.md`:

| Registry | Status |
|---|---|
| `docs/rule-ledger.yaml` | Adopted + enforced. `scripts/next-rule-ledger-id.sh` mints; `rule-ledger-check.sh` C1 validates. |
| ADR numbers | Same rule; format change routed to System Architect. Reason: citation key `ADR-A-[0-9]+` is hard-coded in 4 tools and `ADR-A-0001`. Result backstop (`tests/test-adr-id-uniqueness.sh`) stays in place. |
| Migrations (`NNN_*.sql`) | Exempt. Reason: prefix encodes execution order, which a ticket id cannot provide. Existing `scripts/next-migration-number.sh` + collision gate (ABS-428/449) retained. |

### AC3 — Parallel-case falsifier test

**PASS. 7/7.** `tests/test-registry-id-parallel.sh` reproduces the actual collision scenario:

```
bash tests/test-registry-id-parallel.sh
```

Run output (commit `8f14d0aa`):

```
=== Parallel-branch id allocation (ABS-600) ===

Ticket-scoped allocation (the fix)
  PASS  ids derive from the ticket, not a shared counter
  PASS  parallel allocation integrates with NO collision (AC3)

Running-counter allocation (what we replaced) — proves the backstop
  PASS  duplicate running-counter id -> exit 1 (AC4 backstop)
  PASS  backstop names the colliding id
  PASS  backstop names the first occurrence's heading (AC5)
  PASS  backstop names the second occurrence's heading (AC5)
  PASS  backstop names the source file (AC5)

=== Test Results ===

  Total:  7
  Passed: 7
  ALL PASS
```

The test allocates from a shared base using two different ticket ids (ABS-595, ABS-596), merges the results, and asserts no collision. It also runs the old counter scheme, which does collide, to prove the test bites and the backstop fires.

### AC4 — Duplicate backstop retained

**PASS.** `rule-ledger-check.sh` C1 still exits 1 on any duplicate id. Confirmed by test case 3 above (exit code assertion) and a direct fixture run.

### AC5 — Backstop message names file and heading per colliding row

**PASS.** New awk block in `rule-ledger-check.sh` emits:

```
RULE-LEDGER: C1: duplicate rule ids: R-0002
    R-0002  <-  docs/RULES.md  ›  "Rule A1"
    R-0002  <-  docs/RULES.md  ›  "Rule B1"
```

Confirmed by direct fixture run and by test cases 5/6/7.

---

## Existing test suite

`tests/test-rule-ledger.sh`: **18/19 PASS** — same result on both branch (`8f14d0aa`) and base (`cf859028`).

The 1 FAIL is the "Real repo ledger" case: `rule-ledger-check.sh` exits 1 due to a pre-existing C4 dangling-anchor on `.claude/agents/be-developer.md` (a generated governor mirror). Identical on the base commit. Not introduced by this story.

---

## Script behavior (ABS-66 verification)

```
scripts/next-rule-ledger-id.sh ABS-600      → R-ABS-600-1   (exit 0)
scripts/next-rule-ledger-id.sh bad-id       → error + exit 64
scripts/next-rule-ledger-id.sh              → error + exit 64
```

The ticket-id input is regex-validated (`^[A-Z][A-Z0-9]*-[0-9]+$`) so no grep injection via the argument.

---

## Flags check

Ticket `ABS-600` carries no `design` flag. Exit target: `Story Acceptance`.
