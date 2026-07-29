# QA Validation — ABS-210

**Ticket**: ABS-210 — Orchestrator: JOIN-Gate-Ausnahme fuer optional/extern geparkte Kinder
**QAS run**: 2026-07-12
**Branch**: `ABS-210-auto`
**Commit reviewed**: `ea517f4 feat(orch): JOIN-gate exemption for parked optional/external children [ABS-210]`
**Files changed**: `scripts/orchestrator.sh` (+51/-4), `tests/test-orchestrator.sh` (+87), `docs/sop/ORCHESTRATOR_SOP.md` (+12)
**Verdict**: APPROVED

---

## State Re-verification (Session-Resume Etiquette)

- `git status --short`: clean tree (no stash, no uncommitted changes)
- `git log --oneline -1`: `ea517f4 feat(orch): JOIN-gate exemption for parked optional/external children [ABS-210]`
- `git branch --show-current`: `ABS-210-auto`
- Tracker: ABS-210 at `In Test`, updated `2026-07-11T23:32:31Z`
- `bash -n scripts/orchestrator.sh`: PASS
- `bash -n tests/test-orchestrator.sh`: PASS

---

## Acceptance Criteria

### AC1 — Epic with N Done-children + 1 parked child WITH exemption signal → JOIN fires; log names the exemption

**PASS**

`join_check_epic` (orchestrator.sh) partitions not-Done children via `child_join_exempt`. A child carrying `JOIN-EXEMPT (triage)` in the body of a `kind: decision` comment lands in `exempt`; all others land in `pending`. When `pending` is empty and `exempt` is non-empty, the runner emits:

```
INTENT JOIN-EXEMPT ticket=EP-A … exempt-children:X1
INTENT JOIN ticket=EP-A role=- to=Epic Integration
TRANSITION EP-A Epic Integration
```

Test assertions (all PASS, run 2026-07-12):

| Assertion | Result |
|-----------|--------|
| the log emits a JOIN-EXEMPT intent | PASS |
| the JOIN-EXEMPT intent NAMES the excluded child | PASS |
| JOIN fires past the parked child | PASS |
| epic transitions to Epic Integration | PASS |

### AC2 — Parked child WITHOUT signal → JOIN keeps waiting; names the waiting child once (no silent hang)

**PASS**

A not-Done child with no exempt marker stays in `pending`; the runner emits:

```
INTENT JOIN-WAIT ticket=EP-B … pending-children:Y1
```

No transition fires. Mixed case (exempt child + genuine blocker) also keeps waiting: only the genuine blocker's id appears in `pending-children`.

Test assertions (all PASS):

| Assertion | Result |
|-----------|--------|
| a real blocker keeps the gate waiting | PASS |
| the JOIN-WAIT intent NAMES the still-pending child (no silent hang) | PASS |
| JOIN does NOT fire past a genuine blocker | PASS |
| epic is NOT integrated while a real blocker remains | PASS |
| un-exempted blocker Y3 named as pending (mixed case) | PASS |
| JOIN stays put while a genuine blocker co-exists with an exemption | PASS |

### AC3 — Tests in tests/test-orchestrator.sh; suite green

**PASS**

New `ABS-210 JOIN exemption` section: 13 assertions, all green.

Full suite run (2026-07-12, in-tree environment):

```
Total:  609
Passed: 602
Failed: 7
```

All 7 failures are pre-existing self-hosting environment artifacts (provenance harness path mismatch, model-label spawn-seam tests, cap override). None touch `join_check_epic`. System-architect's isolated-worktree baseline comparison (clean HEAD `99d9c64` vs `ea517f4`) confirms **+0 new failures**.

---

## Additional Checks

### anti-quote-disarm (security property of the marker)

The `child_join_exempt` awk parser gates on `in_decision` — a flag set only when the current section header contains `kind: decision`. A `JOIN-EXEMPT (triage)` string in a `kind: handoff` or `kind: gate-results` comment body does **not** exempt the child. This is verified by a dedicated test:

| Assertion | Result |
|-----------|--------|
| marker in a kind: decision body → exempt | PASS |
| no marker → not exempt | PASS |
| marker only in a non-decision comment → NOT exempt | PASS |

### Scope enforcement

`git diff HEAD~1..HEAD` touches exactly the 3 files listed above. No Blocked/TDM-triage semantics changed (ABS-76 out of scope). No auto-cancel. No ABS-211 contamination (be-developer flagged and resolved a stash-race; diff confirmed clean).

### Documentation

`docs/sop/ORCHESTRATOR_SOP.md` — "Optional/parked-child exemption (ABS-210)" paragraph added under the JOIN rule + guards section. Documents marker syntax, anchoring rule, `JOIN-EXEMPT`/`JOIN-WAIT` intent names, and ADR-A-0019 provenance.

---

## Verdict

**APPROVED**. AC1/AC2/AC3 met. 13 new assertions green. Zero new failures introduced. Scope respected. Documentation present. Marker anchoring prevents inadvertent exemption by quoted strings.

Non-blocking advisories for operator/TDM (not a QAS concern, no bounce):
- 7 pre-existing failures in this environment (self-hosting artifacts); 21 in the SA's isolated-worktree environment. Track separately.
- Stash race on shared `tmp/ABS-210-work` tree flagged by be-developer; operator should review.
