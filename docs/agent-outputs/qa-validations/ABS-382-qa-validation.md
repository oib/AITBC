# QA Validation — ABS-382 (ABS-231 S5: `build_packet` policy injection)

- **Verdict**: APPROVED
- **Gate**: In Test (QAS)
- **Branch**: `ABS-382-auto` · **Commit**: `0a0a916`
- **Adapter under test**: `scripts/mock-tracker.sh` (default) + `tests/fixtures/policies-cap-tracker.sh` (policies-capable)
- **Date**: 2026-07-18

## Context sequence (ADR-A-0003)
Read ticket + Context Pack (spec ABS-231-phase3, PO/architect/SecEng comments) → diff `0a0a916` on `scripts/orchestrator.sh` (single `build_packet` edit) → test suite + focused harnesses. No broad grep needed.

## Acceptance Criteria — independently re-verified

| AC | Criterion | Result | Evidence |
|----|-----------|--------|----------|
| AC1 | Capable adapter: packet carries `=== POLICY (policy_rev: <hash>) ===` + role's effective policy, before `=== TICKET ===` | PASS | Suite (4 assertions: block present, rendered text injected, POLICY-FIRST ordering, trailing `policy_rev:` line stripped) + AC4 harness (header hash matches sig) |
| AC2 | mock/jira (no `policies` op): byte-identical to today's packet, no POLICY block | PASS | Suite + **byte-parity harness**: current build `cmp`-identical (1214 bytes) to pre-ABS-382 parent build for the same ticket/state |
| AC3 | `ORCH_POLICY_INJECT=off`: byte-identical legacy packet on a capable adapter | PASS | Suite + **byte-parity harness**: `cmp`-identical (1229 bytes) to pre-ABS-382 parent build |
| AC4 | Policy change bumps `policy_rev` + invalidates cache (rebuild); unchanged re-hits | PASS | **Focused build_packet harness**: unchanged policy → cache hit (byte-identical packet, same sig); policy A→B → `policy_rev` in sig changed → cache miss → new packet built |
| AC5 | Each spawn writes a `run.log` line recording its `policy_rev` | PASS | Suite (POLICY-INJECT line; `policy_rev=none` on non-capable adapter) + harness (3 POLICY-INJECT lines — fires on both cache hit AND miss; header/sig/audit hashes match) |
| AC6 | e2e via run-boilerplate sandbox `--once`: dispatch → POLICY block in packet → spawn recorded with `policy_rev`; shellcheck/lint green | PASS | Suite in-process `orch --live --once` against the capable fixture; shellcheck net-zero new findings |

## Gates re-run by QAS
- `shellcheck -x scripts/orchestrator.sh`: **21 findings on HEAD == 21 on parent** → net-zero new findings. The one finding in the new code region (line 7211) is a pre-existing `seat_note_directive` heredoc (SC1011 apostrophe false-positive), untouched by this diff.
- `tests/test-orchestrator.sh`: **EXITCODE=0, 1167 pass, 0 real failures** (the lone `orch-abort-…` FAIL line is the ABS-370 self-test's deliberate aborting-include fixture; aggregate "Failed: 0"). Includes 9 new ABS-382 assertions.

## Security flag (In Test scope)
Story carries `flags: [security]`; the Security Review station (ARCHitect Stage 2) already passed it forward. SecEng logged a **non-blocking** hardening follow-up (delimiter-robustness for `policy_rev:`/`=== TICKET ===` markers *if the policy-text trust model ever loosens*) — not a live vulnerability: policy text is trusted, human-authored, revision-pinned; agents cannot write policy (server-side 403 in S2/S3). No gating finding. Injection is context-only — grants the seat no new authority, touches no human-only boundary (ADR-A-0004 clean).

## Verdict
**APPROVED.** All 6 ACs met and independently re-verified (2 via the suite, AC4 + byte-parity for AC2/AC3 via focused live harnesses). Default-safe design confirmed byte-identical to the legacy packet on mock/jira and under `ORCH_POLICY_INJECT=off`. No `design` flag → exit to **Story Acceptance**.
