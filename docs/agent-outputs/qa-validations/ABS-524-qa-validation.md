# QA Validation — ABS-524

**Ticket**: SOP-Ledger-Nachaudit (informative→derived) + datenbasierte Kondensations-Entscheidung  
**Commit**: `5414f4a3` on `ABS-524-auto` (pushed: `gitlab/ABS-524-auto`)  
**QAS run**: 2026-07-27  
**Verdict**: **APPROVED**

---

## Independent Checks

All checks run from the current HEAD (`5414f4a3`) on branch `ABS-524-auto`.

### AC1 — Re-classified rows have verified sensors

13 `ORCHESTRATOR_SOP.md` rows moved `informative → derived`. Each carries a sensor from an already-`enforced` parent row (C2 reuse). Verified sensor file existence independently:

| Sensor path | Exists |
|---|---|
| `tests/orchestrator.d/ABS-261-priority-dispatch.sh` | ✓ |
| `tests/test-claim-mutex.sh` | ✓ |
| `tests/test-claim-dispatch.sh` | ✓ |
| `tests/test-claim.sh` | ✓ |
| `tests/test-merge-token.sh` | ✓ |
| `tests/test-merge-wait.sh` | ✓ |
| `scripts/orchestrator.sh:merge_token_gate` | ✓ (58 matching refs in orchestrator.sh) |
| `scripts/orchestrator.sh:handoff_work_verified` | ✓ |
| `scripts/orchestrator.sh:handoff_followthrough` | ✓ |
| `scripts/orchestrator.sh:push_verify_failures` | ✓ |

`rule-ledger-check.sh` enforces C2 (path+function existence) at check time; it exited 0. **AC1: PASS**

### AC2 — rule-ledger-check.sh green; --report shows new derived count

```
$ bash scripts/rule-ledger-check.sh
rule-ledger-check: OK — every scoped rule section has a declared enforcement status.
exit 0

$ bash scripts/rule-ledger-check.sh --report
# ORCHESTRATOR_SOP.md: enforced 30 / derived 21 / unenforced 21 / informative 68
# (was: derived 8 / informative 81)

$ bash tests/test-rule-ledger.sh
Total: 19 / Passed: 19 / Failed: 0 — ALL TESTS PASSED
exit 0

$ bash scripts/docs-identifier-check.sh
exit 0

$ bash scripts/orch-knob-doc-drift.sh
orch-knob-doc-drift: OK — every ORCH_* knob read in scripts/ is documented in the SOP.
exit 0
```

**AC2: PASS**

### AC3 — Condensation-% estimate posted as ticket comment with section list

Implementer posted a `kind: gate-results` comment at 2026-07-27T16:42:58Z. Contents verified present:

- 13-row section table (id / section / sensor)
- Knob-preserving estimate: **7.2 %** (below ≥10 % gate)
- Best-case estimate: **9.9 %** (below ≥10 % gate)
- Recommendation: **Cancel Schritt 2** (both figures below the <10 % Abbruchkriterium per ABS-514)

**AC3: PASS**

---

## Scope Check

Diff is ledger-only: `docs/rule-ledger.yaml` +26/−41. No SOP rewrite, no `harness/claude/*` changes, no product code touched. Orphan-row removal (7 dangling `be-developer.md` rows, pre-existing C4 failure at v2.34.0) is in-scope — it was the only path to a green checker (AC2); ids retired, not reused, consistent with append-only rule.

## Commit Reachability

```
$ git for-each-ref --contains 5414f4a3 refs/remotes/
5414f4a395f8a7d543e59a1656a9604c1b8655f9 commit  refs/remotes/gitlab/ABS-524-auto
```

Commit exists and is pushed to the active remote. ✓

## Condensation Decision

Data gate: 7.2 % knob-preserving / 9.9 % best-case — both below ≥10 % threshold. Per ticket fallback: **Schritt 2 CANCEL**. The audit is the deliverable.

---

**Final Verdict: APPROVED → Story Acceptance**  
No `design` flag on ticket; no `Design Test` stop required.
