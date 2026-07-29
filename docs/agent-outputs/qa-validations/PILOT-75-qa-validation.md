# QA Validation — PILOT-75

**Ticket**: PILOT-75 — Vorwärts-Transition ohne Push  
**Branch**: PILOT-75-auto  
**Commits under test**: `b27ac1fb` (implementation, in epic), `0c1940d3` (docs forward-fix, branch HEAD)  
**QAS run**: 2026-07-27 (resumed at In Test after architect forward-fix)  
**Commit at run**: `0c1940d3` (HEAD on active remote `gitlab/PILOT-75-auto`)

---

## Remote Reachability Verified

Branch HEAD `0c1940d3` confirmed on active remote:

```
git rev-parse refs/remotes/gitlab/PILOT-75-auto
  0c1940d301e2bd8f6c694dabec938cbaa847413e
```

Implementation `b27ac1fb` is in the epic integration branch:

```
git merge-base --is-ancestor b27ac1fb refs/remotes/gitlab/epic/PILOT-71-autonomie-haertung
  → IS ancestor (exit 0)
```

---

## Forward-Fix Scope (0c1940d3)

Docs-only: adds R-1109..R-1117 to `docs/rule-ledger.yaml`, registering 9 SOP headings
under `docs/sop/ORCHESTRATOR_SOP.md`. All 9 headings verified to exist at lines 1489–1586:

| Row | Heading | Kind |
|-----|---------|------|
| R-1109 | Remote Push Verification (PILOT-75, ADR-A-0024 + ADR-A-0030) | enforced |
| R-1110 | Why this gate exists — four incidents across three runs | informative |
| R-1111 | Scope | informative |
| R-1112 | What the gate checks | unenforced |
| R-1113 | Failure semantics | informative |
| R-1114 | AC3 — main-checkout seat sensor | derived |
| R-1115 | Seat contract (applies to all seats) | unenforced |
| R-1116 | Kill-switch | informative |
| R-1117 | Test suite | informative |

---

## AC Checklist

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | Forward transitions (In Review+) refused when commits not on active remote; remote via `active_remote_name()`, never hardcoded origin (ADR-A-0030) | ✅ PASS | `push_verify_failures()` checks `refs/remotes/<active-remote>/`; fixture: refusal names `gitlab` remote; R-1109 ledger row (kind: enforced) |
| AC2 | Violation is mis-report per ADR-A-0024 (transition not applied; not advisory) | ✅ PASS | `push_verify_failures()` output fed into `$failures` in `handoff_followthrough()` → `record_misreport()`; fixture asserts `HANDOFF-MISREPORT` |
| AC3 | Sensor flags unclean main checkout (tracked uncommitted changes); `_common-rules.md` §1 updated | ✅ PASS | `detect_worktree_hygiene()` in ops-sweep-sensors.sh checks `git status --porcelain --untracked-files=no`; 35/35 ops-sweep passed including PILOT-75 AC3 assertion |
| AC4 | Falsification: local-only commit → refused; same commit pushed → accepted; In Progress exempt; kill switch works | ✅ PASS | 7/7 PILOT-75 fixture at `0c1940d3` |
| AC5 | 13 pilot-#7 local-only branches secured | ⚠️ OPERATOR ACTION | Non-code-enforceable; not in this checkout; ABS-549 `branch-recoverable` sensor surfaces for operator; non-blocking per architect + PO classification |

---

## Test Results

### PILOT-75 Fixture (run at `0c1940d3`)

```
SUITE_INCLUDE_ONLY=PILOT-75-remote-push-verify.sh bash tests/test-orchestrator.sh

  AC1/AC4: local-only commit + forward transition (In Review) → REFUSED
  PASS  PILOT-75 AC2: never-pushed commit refused on mis-report path
  PASS  PILOT-75 AC1: refusal names remote-reachability failure
  PASS  PILOT-75 AC1: refusal names the active remote (never hardcoded origin)
  PASS  PILOT-75: refusal names the failing commit hash
  AC4 (control): same commit PUSHED → ACCEPTED
  PASS  PILOT-75 AC4: commit on active remote never refused
  Scope: local-only commit on NON-completion target (In Progress) → EXEMPT
  PASS  PILOT-75 scope: push gate fires on In Review..Done only
  Kill switch: ORCH_VERIFY_PUSH=0 → gate disabled
  PASS  PILOT-75 kill-switch: ORCH_VERIFY_PUSH=0 disables refusal

  Total: 7  Passed: 7  Failed: 0
```

### Supporting Suites

| Suite | Count | Result |
|-------|-------|--------|
| ops-sweep-sensors (AC3) | 35/35 | ✅ PASS |
| harness-parity (mirror regenerated with _common-rules.md) | 6/6 | ✅ PASS |

### Known Red (not PILOT-75 debt)

- `test-orch-knob-drift.sh`: 3/4 PASS — 1 FAIL on `ORCH_TICKET_TAG_GUARD` (PILOT-79 debt)
- `rule-ledger-check.sh`: FAIL on `PILOT-81` (Harness-release preflight heading), PILOT-76 (`rte-reference.md` headings), PILOT-79 (`COMMIT_TAG_GUARD_SOP.md`) — none are PILOT-75 entries

---

## Implementation Spot-Check

`push_verify_failures()` (orchestrator.sh:4618):
- Scope guard: `chain_index "$to"` must be 4–12 (In Review..Done)
- Remote: `active_remote_name()` → strips branch from `resolve_active_main_ref` output (ADR-A-0030)
- Check: `git for-each-ref --contains "$sha" --count=1 refs/remotes/$remote/` — network-free
- Fail path: appended to `$failures` in `handoff_followthrough()` → `record_misreport()` (hard gate)
- Kill switch: `ORCH_VERIFY_PUSH=0` returns early (line 4620)
- Double-report discipline: skips hashes not locally present (left to `commit_verify_failures`)

`active_remote_name()` (orchestrator.sh:7412):
- Strips `/<main-branch>` from `resolve_active_main_ref` output
- Inherits resolution order: `ORCH_MAIN_REMOTE` → `branch@{push}` → `remote.pushDefault` → sole remote
- Never `origin`

`detect_worktree_hygiene()` (ops-sweep-sensors.sh:141):
- Sub-case (c): `git status --porcelain --untracked-files=no` non-empty on main checkout
- Reports `unclean-main-checkout=N-file(s)` + remediation `commit-and-push-or-discard-main-checkout-edits`

`_common-rules.md §1` (Evidence-Disziplin):
- PILOT-75 addition: "COMMIT and PUSH to the active remote before you transition forward"
- Explicitly covers main-checkout seats (docs/PO/RTE)

---

## Verdict

**APPROVED for Story Acceptance**

AC1–AC4 pass. Forward-fix `0c1940d3` is docs-only and correct: 9 ledger rows (R-1109..R-1117) map 1:1 to existing SOP headings. Full PILOT-75 fixture 7/7 at HEAD on the active remote. AC5 is a pre-classified operator action, non-blocking.
