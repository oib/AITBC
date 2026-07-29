# QA Validation Report — PILOT-53

**Ticket**: PILOT-53 / ABS-562  
**Title**: ADR-A-0004 Falschbehauptung korrigieren + ADR-A-0014 CI-Praemisse mit der Realitaet in Deckung bringen  
**QA Date**: 2026-07-26  
**Commit validated**: `173caf85b8f9ec372880bca9b1b43517b6cbb9c3` (HEAD, `PILOT-53-auto`)  
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Verification

### AC1 — Correct the false ADR-checker authorship claim in ADR-A-0004

**Status**: ✅ PASS

**Evidence**: The old Decision text claimed _"the ADR checker rejects agent-authored non-`proposed` statuses"_.  
Independent inspection of `tests/test-adr-status.sh` (lines 56–58, 110–112) confirms:
- The guard checks only that `accepted`/`superseded` ADRs carry **`accepted_by` AND `accepted_date`** fields.
- It **never inspects authorship** — the positive fixture at line 110–112 passes an agent-authored `accepted` ADR with both fields set, unchanged.

The corrected Decision text now reads: _"the ADR status guard (`tests/test-adr-status.sh`) requires any `accepted`/`superseded` ADR to carry `accepted_by`/`accepted_date` — the human-acceptance evidence a `proposed` ADR omits (an evidence check, **not** an authorship block; acceptance stays a human PR-review act per ADR-A-0001)"_.

The 2026-07-26 amendment to ADR-A-0004 elaborates further, removing the false claim and explaining why authorship-based enforcement would be equally weak (git authorship is trivially settable).

### AC2 — Resolve three "TBD by story implementation" rows

**Status**: ✅ PASS

The three marker-table rows for ABS-296, ABS-298, and ABS-301 were changed from:

```
TBD by story implementation
```

to:

```
_open — not recorded here; AD-1 governs any reversal (2026-07-26 amendment)_
```

This makes the open state **explicit** rather than falsely implying pending work. The AD-1 general rule still governs any reversal — the open rows narrow nothing and grant no new reversal authority.

### AC3 — ADR-A-0014: name the actual mechanical gate on the pipeline-less remote

**Status**: ✅ PASS

ADR-A-0014 received a 2026-07-26 amendment that:
1. Names the **three actual gate components** (seat-run test suite, `work/merge-log.md` merge evidence, base-integrity check).
2. Explicitly flags the **ABS-557 known gap** (seat-run suite does not complete cleanly on the epic branch).
3. Correctly states the **human backstop** remains the epic-PR review + staging test (part 3 — always required, never automated).
4. Moves **no ADR-A-0004/A-0005 boundary** — `main` stays human-merge-only.

The amendment does NOT deliver a `.gitlab-ci.yml` (the companion execution-path story owns that), but it takes the text-correction path permitted by the AC and honestly represents the current state.

### AC4 — Both changes prepared as ADR amendments; no agent accepts them

**Status**: ✅ PASS

Frontmatter verification:
- **ADR-A-0004**: `status: proposed` — **unchanged**; body edits are inline corrections to a proposed ADR (permitted scope).
- **ADR-A-0014**: `status: accepted`, `accepted_by: "Raphael Sahann (POPM)"`, `accepted_date: "2026-07-06"` — **all fields intact**; amendments are pure additions at the end of the accepted body.

Both amendment sections contain explicit language: _"prepared by the implementer for the normal human PR-review acceptance gate; no agent accepts it (ADR-A-0001)"_.

---

## Test Suite Results

All tests run synchronously with `unset BACKEND_URL BACKEND_TOKEN TRACKER_CMD ORCH_INSTANCE_ID`, against commit `173caf85` on branch `PILOT-53-auto`.

| Test | Command | Result |
|---|---|---|
| ADR status guard | `bash tests/test-adr-status.sh` | **35 passed, 0 failed** |
| Rule ledger check | `bash scripts/rule-ledger-check.sh` | **OK** |
| Rule ledger test suite | `bash tests/test-rule-ledger.sh` | **19/19 PASSED** |
| ADR reference lint | `bash scripts/adr-reference-lint.sh` | **exit 0** |
| ADR acceptance drift | `bash scripts/adr-acceptance-drift.sh` | **exit 0** |
| Harness parity | `bash scripts/generate-governor.sh --providers --check` | **OK** |

---

## Additional Checks

- **Commit `173caf85` exists**: confirmed (`git cat-file -e 173caf85^{commit}`)
- **Commit reachable**: confirmed (`refs/heads/PILOT-53-auto` contains it)
- **Files changed**: `adrs/agentic/ADR-A-0004-human-approval-boundaries.md`, `adrs/agentic/ADR-A-0014-workflow-v3-per-epic-merge-gate.md`, `docs/rule-ledger.yaml` — exactly the expected three files, no other modifications
- **Ledger rows R-1094, R-1095**: appended correctly with file + heading matching the new amendment sections
- **Harness parity**: `generate-governor.sh --providers --check` → OK (ADR files have no harness mirror; ledger does not trigger parity guard)
- **No test-touching files** in the diff (only `.md` and `.yaml`) → ABS-453 green-run proof not required

---

## Verdict

**APPROVED — Story Acceptance**

All four ACs are met. The implementation takes the honest text-correction path: the false authorship-check claim is removed (AC1), the TBD rows are made explicitly open (AC2), the A-0014 amendment names the real pipeline-less gate with an honest ABS-557 gap flag (AC3), and both amendments preserve the human-only acceptance boundary (AC4). The full guard suite runs clean (35/0, 19/19, exit-0×2, harness-OK). No regressions introduced.
