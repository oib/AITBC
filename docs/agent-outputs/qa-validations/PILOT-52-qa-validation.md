# QA Validation Report — PILOT-52

**Ticket:** PILOT-52 / ABS-561  
**Title:** ADR-Status-Hygiene: Sensor für die Gegenrichtung des Acceptance-Drifts + Flip-Liste  
**Branch:** PILOT-52-auto  
**Head commit:** ac0d9d6c  
**QAS run date:** 2026-07-26  
**Verdict:** ✅ APPROVED

---

## Acceptance Criteria Validation

### AC1 — Sensor for reverse direction (proposed + enforced → DRIFT)

**Result:** ✅ PASS

`scripts/adr-enforced-status-drift.sh` reads `docs/rule-ledger.yaml` and reports all ADRs
named by a `kind: enforced` or `kind: derived` ledger row that still carry `status: proposed`
in their file frontmatter. Live run (exit 1, advisory):

```
DRIFT: ADR-A-0009 status:proposed but its mechanic is enforced — ledger R-0303
       [sensors: scripts/orchestrator.sh:budget_exhausted,
       tests/orchestrator.d/ABS-293-budget-recovery.sh]
DRIFT: ADR-A-0025 status:proposed but its mechanic is enforced — ledger R-0312
       [sensors: scripts/orchestrator.sh:merge_token_gate,
       tests/test-merge-token.sh, tests/test-merge-wait.sh]
DRIFT: ADR-A-0024 status:proposed but its mechanic is enforced — ledger R-0319
       [sensors: scripts/orchestrator.sh:handoff_work_verified,
       scripts/orchestrator.sh:handoff_claims_commit]
```

### AC2 — Reports only; acceptance stays human (ADR-A-0004)

**Result:** ✅ PASS

- Script exits 1 as an **advisory** (`exit 1` on drift), explicitly documented as
  "ADVISORY — do NOT wire as a blocking CI gate".
- `git grep` confirms `adr-enforced-status-drift.sh` is **not** called from any
  CI config, pre-commit hook, or orchestrator gate — only from `docs/adr-flip-list.md`
  (documentation) and its own test.
- The script never edits or transitions any ADR file (`grep -n 'sed\|awk.*-i\|echo.*>'`
  shows no file-write paths).

### AC3 — Operator flip-list with Belegstelle per ADR

**Result:** ✅ PASS

`docs/adr-flip-list.md` exists with a committed snapshot table. `--flip-list` mode output
(one line per ADR, Belegstelle = ledger row + sensors):

```
ADR-A-0009   | proposed -> accepted? | enforced by R-0303 [...] | HUMAN-ONLY flip (ADR-A-0004)
ADR-A-0024   | proposed -> accepted? | enforced by R-0319 [...] | HUMAN-ONLY flip (ADR-A-0004)
ADR-A-0025   | proposed -> accepted? | enforced by R-0312 [...] | HUMAN-ONLY flip (ADR-A-0004)
```

Note: ADR-A-0016/0021/0022/0023 (named in the BEFUND) are correctly absent — no
`enforced`/`derived` ledger row names them yet; the evidence bar is not machine-provable,
and the flip-list doc explains this explicitly.

### AC4 — ADR-A-0027 self-contradiction resolved; index documenting it

**Result:** ✅ PASS

- Frontmatter: `status: accepted`, `accepted_by: Raphael Sahann (POPM)`,
  `accepted_date: "2026-07-20"` — no self-contradiction.
- Body paragraph (line ~76) now reads: *"this paragraph is reconciled to that state
  (PILOT-52/ABS-561), resolving the prior `proposed`-vs-`accepted` self-contradiction."*
- `adrs/agentic/README.md` index entry (line 56) documents: *"the body's status
  paragraph was reconciled to `accepted` in PILOT-52/ABS-561, resolving the prior
  self-contradiction."*
- Only one remaining `proposed` reference in the file (line 76) is descriptive prose
  about the prior contradiction, not a status claim.

### AC5 — Falsification: kind:enforced + status:proposed ⇒ sensor red

**Result:** ✅ PASS

Test suite `tests/test-adr-enforced-status-drift.sh` — **7/7 passed, 0 failed**:

```
✓ AC5 falsification: kind:enforced + status:proposed => sensor rot
✓ kind:derived + proposed => drift
✓ accepted + enforced => no drift
✓ proposed + unenforced-only => no drift
✓ proposed but unnamed by any enforced row => no drift
✓ --flip-list: operator decision line with Belegstelle
✓ real tree: sensor runs advisory (rc=1), DRIFT lines well-formed
```

Command run:
```bash
unset BACKEND_URL BACKEND_TOKEN TRACKER_CMD ORCH_INSTANCE_ID
bash tests/test-adr-enforced-status-drift.sh
# → Passed: 7  Failed: 0  Total: 7
```

---

## Related Test Suites

| Suite | Result |
|-------|--------|
| `tests/test-adr-enforced-status-drift.sh` | **7/7 PASS** |
| `tests/test-adr-status.sh` | **35/0 PASS** |
| `tests/test-adr-reference-lint.sh` | **6/6 PASS** |

All run against commit `ac0d9d6c` with backend env vars unset.

---

## Files Delivered

| File | Purpose |
|------|---------|
| `scripts/adr-enforced-status-drift.sh` | Reverse-direction drift sensor (AC1, AC2, AC3) |
| `tests/test-adr-enforced-status-drift.sh` | Falsification fixture + 6 additional cases (AC5) |
| `docs/adr-flip-list.md` | Operator decision vehicle — flip-list snapshot (AC3) |
| `adrs/agentic/ADR-A-0027-dashboard-url-grammar.md` | Self-contradiction reconciled (AC4) |
| `adrs/agentic/README.md` | Index entry updated with reconciliation note (AC4) |

No product code modified. No harness/mirror files touched. No RLS/auth/DB surface.

---

## Verdict

**✅ APPROVED — Approved for RTE**

All 5 acceptance criteria verified against live sensor run and test suite. No design flag
present → transition to `Story Acceptance`.
