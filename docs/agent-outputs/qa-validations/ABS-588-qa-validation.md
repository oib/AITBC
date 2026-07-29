# QA Validation — ABS-588
**Epic-Übergabe endet an einem Branchnamen: 'Ready for Epic Acceptance' ohne prüffähiges Artefakt**

| Field | Value |
|---|---|
| Ticket | ABS-588 |
| Commit under test | `b837c0ab` |
| Branch | `ABS-588-auto` |
| Remote | pushed: `origin/ABS-588-auto`, `gitlab/ABS-588-auto` |
| QAS run date | 2026-07-27 |
| Verdict | **APPROVED** |

---

## Test Run Results

### ops-sweep-sensors tests (test-ops-sweep-sensors.sh)
```
8b. epic-handoff-missing (ABS-588)
  PASS epic at Ready for Epic Acceptance with no artifact marker -> flagged (AC4)
  PASS epic-handoff-missing carries the remediation suggestion
  PASS artifact marker present -> not flagged (negative)
  PASS status != Ready for Epic Acceptance -> not flagged (negative)
=== Test Results ===
  Total:  39   Passed: 39   Failed: 0
  ALL TESTS PASSED
```

### Harness-parity (test-harness-parity.sh)
```
  Total:  6   Passed: 6   Failed: 0
  ALL TESTS PASSED
generate-governor.sh --providers --check: OK (agent_providers/claude_code == generated(harness/claude))
```

### Staged suite
| Stage | Result | Count | Notes |
|---|---|---|---|
| `stories` | PASS | 60/60 | ABS-588-epic-handoff-artifact.sh: PASS |
| `orch-core` | PASS | 741/741 | — |
| `pool` | FAIL\* | — | \*sole failure: pre-existing `test-rule-ledger.sh` dangling-anchor C4 in `be-developer.md`, present in parent commit `cf859028` before ABS-588 |

**Pre-existing failure confirmation**: ran `rule-ledger-check.sh` against `cf859028` (the v2.34.0 release commit, parent of `b837c0ab`) — identical C4 output. ABS-588 introduced zero new failures.

---

## AC Verification

**AC1** — After 'Ready for Epic Acceptance', exactly ONE named next step; no reconstructing the story list from the log.

- `rte.md` handoff format now contains `**Human next step (the ONE step, ABS-588 AC1)**` with a single copy-paste `glab mr create` command.
- Format includes `**Stories** (all Done): AITBC-XXX ...` so the human reads the child list in the artifact, not the git log.
- `ABS-588-epic-handoff-artifact.sh` asserts `"Human next step (the ONE step"`, `"glab mr create --source-branch epic/"`, and `"**Stories** (all Done):"` — all PASS.

**AC2** — ADR-A-0014 boundary stays verbatim; proven in the chosen path (b+c), not merely asserted.

- `rte.md` retains `You never open or merge a PR to \`main\` from this seat` and `RTE does not open or touch that \`main\`-bound PR` — both strings pass the test assertions.
- Path chosen: RTE posts a gate-results comment carrying the prepared `glab mr create` command. The HUMAN runs it. No agent opens or merges the main-bound MR.
- `ABS-588-epic-handoff-artifact.sh` asserts both boundary strings — PASS.

**AC3** — Verification state (commit, suite, result) is part of the handoff.

- Artifact format includes `**Epic branch**: epic/... @ <epic-tip sha>` and `**Full suite on epic tip** (ABS-453): <counter, e.g. 142 passed, 0 failed> @ <epic-tip sha>`.
- The live remote has no CI (ABS-559); the state is produced at release time by the RTE, not assumed from a pipeline.

**AC4** — An epic at 'Ready for Epic Acceptance' without the handoff artifact is reported as a finding, not silently shown as "waiting for human".

- `scripts/ops-sweep-sensors.sh` detector 9 `epic-handoff-missing`: scans `OPS_TICKETS_DIR/*.md` for `status: Ready for Epic Acceptance` tickets missing the `EPIC-HANDOFF-READY` marker.
- `--list` output includes `epic-handoff-missing` — sensor is registered.
- Positive fixture (PILOT-58, no marker): flagged with `epic-handoff-missing PILOT-58 status=Ready-for-Epic-Acceptance,artifact=absent` — PASS.
- Negative fixtures (PILOT-59 with marker, PILOT-62 at different status): not flagged — PASS.
- Marker default in sensor (`OPS_EPIC_HANDOFF_MARKER:-EPIC-HANDOFF-READY`) matches the token in `rte.md` exactly — coherence test PASS.

---

## Harness↔Provider Parity (ABS-317)

`harness/claude/agents/rte.md` edited → `agent_providers/claude_code/prompts/rte.md` regenerated in the same commit.
`generate-governor.sh --providers --check`: OK. `test-harness-parity.sh` 6/6 PASS.

---

## Verdict

All 4 ACs met. Harness parity clean. Both targeted test suites green (39/39 sensors, 60/60 stories, 741/741 orch-core). Pool stage has one pre-existing failure unrelated to this ticket. Commit `b837c0ab` is pushed to `origin` and `gitlab`.

**APPROVED — releasing to Design Test (design flag set).**
