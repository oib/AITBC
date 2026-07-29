# QA Validation Report — ABS-425

**Ticket**: ABS-425 — Reserve `policy_rev:` and `=== … ===` marker lines in rendered policy text (S4 `policies` op contract hardening)
**Branch**: `ABS-425-auto`
**Commits reviewed**: `c04a91f` (Iteration 1, bounced by arch), `4fe786d` (Iteration 2, approved)
**QAS validation date**: 2026-07-18
**Verdict**: ✅ **APPROVED**

---

## Summary

This ticket hardens the S4 `policies` op trust boundary by reserving the `policy_rev:` header syntax and `=== … ===` section-marker syntax in rendered policy body text. The guard lives in `renderEffectivePolicy()` in the real S4 op renderer (`backend/packages/core/src/policies.ts`) — the single source of rendered bytes reused by the S4 read op and the S5 packet injection path. ABS-382 `build_packet` extraction is correctly left unchanged (out of scope).

**Pipeline before QAS gate:**
- Iteration 1 (commit `c04a91f`): Guard implemented only in bash test double (`tests/fixtures/policies-cap-tracker.sh`) → bounced by system-architect (real renderer unguarded, production trust boundary still open)
- Iteration 2 (commit `4fe786d`): Guard moved to the real renderer `renderEffectivePolicy()` in `backend/packages/core/src/policies.ts` → approved by system-architect + security-engineer
- Security Review: passed (security-engineer; non-blocking CRLF note filed for Phase-3 hardening)

---

## Files Changed (commit `4fe786d`)

- `backend/packages/core/src/policies.ts` — `assertNoReservedMarkers(rendered)` added to `renderEffectivePolicy()`, called before `createHash`; `RESERVED_POLICY_LINE = /^policy_rev:|^=== .* ===[ \t]*$/`
- `backend/packages/core/test/policy-resolution.test.ts` — 4 new unit tests on the **real op** (AC2, AC3×2, AC4)
- `docs/guides/AGENTIC-BACKEND-API.md` — Reserved-markers clause (AC1) in S4 contract doc
- `tests/fixtures/policies-cap-tracker.sh` — Harness-side guard mirror (exit 3 on reserved marker)
- `tests/test-orchestrator.sh` — 6 ABS-425 orchestrator assertions

---

## Acceptance Criteria Verification

### AC1 — Reserved-markers clause in S4 op contract doc
- **Requirement**: The S4 `policies` op contract doc contains an explicit clause naming the reserved patterns.
- **Evidence**: `docs/guides/AGENTIC-BACKEND-API.md` line 1952: `**Reserved markers (ABS-425 — trust-boundary hardening).** The policy_rev: header line and any === … === section-marker line are reserved by the op's output framing and MUST NOT appear in rendered policy body text. … A policy source whose rendered text would emit such a line is a contract violation: the op MUST fail loudly at render time (non-zero exit / no forged output)…`
- **Command**: `grep -n "Reserved markers (ABS-425" docs/guides/AGENTIC-BACKEND-API.md` → line 1952
- **Result**: ✅ PASS

### AC2 — Leading `policy_rev:` line → op exits non-zero / no forged hash
- **Requirement**: Given a policy source whose rendered text contains a leading `policy_rev:` line, the `policies` op exits non-zero (or emits escaped output).
- **Evidence (backend unit test)**: `backend/packages/core/test/policy-resolution.test.ts` — `ABS-425: a body with a leading 'policy_rev:' line fails loudly at render time (AC2)` → ✔ (8 pass / 0 fail)
- **Evidence (orchestrator test)**: `ABS-425 AC2: rendered body with a leading 'policy_rev:' line → policies op exits non-zero (no forged policy_rev)` → PASS (1211 pass / 0 fail)
- **Result**: ✅ PASS

### AC3 — `=== TICKET ===` / `=== POLICY … ===` marker → op exits non-zero
- **Requirement**: Given a policy source whose rendered text contains a `=== TICKET ===` (or `=== POLICY … ===`) marker line, the `policies` op exits non-zero.
- **Evidence (backend unit tests)**: 
  - `ABS-425: a body with a '=== TICKET ===' marker line fails loudly (AC3)` → ✔
  - `ABS-425: a body with a '=== POLICY (policy_rev: …) ===' marker line fails loudly (AC3)` → ✔
- **Evidence (orchestrator tests)**:
  - `ABS-425 AC3: rendered body with a '=== TICKET ===' marker line → policies op exits non-zero` → PASS
  - `ABS-425 AC3: rendered body with a '=== POLICY … ===' marker line → policies op exits non-zero` → PASS
- **Result**: ✅ PASS

### AC4 — Well-formed source renders byte-identically (no regression)
- **Requirement**: A well-formed policy source (no reserved patterns) renders byte-identically to today.
- **Evidence (backend unit test)**: `ABS-425: a well-formed body with only look-alike prose renders unchanged (AC4, no false positive)` → ✔ — mid-line `policy_rev` and `3 === 3` arithmetic prose render unchanged; `policyRev == sha256(rendered)` confirmed.
- **Evidence (orchestrator test)**: `ABS-425 AC4: well-formed policy source renders byte-identically (no regression)` → PASS
- **No false positives**: guard is line-anchored (regex `^policy_rev:` / `^=== .* ===$`); mid-line occurrences and look-alike prose are not affected.
- **Result**: ✅ PASS

### AC5 — shellcheck/lint green on touched adapter/op script
- **Evidence**: `shellcheck tests/fixtures/policies-cap-tracker.sh` → exit 0 (no output = no findings)
- **Evidence**: `npx tsc --noEmit` (in `backend/packages/core`) → exit 0 (no type errors)
- **Result**: ✅ PASS

---

## Additional Verification

### build_packet fail-closed behaviour
- `ABS-425: a guarded (violating) policy source injects NO POLICY block (fail-closed)` → PASS
- `ABS-425: build_packet audits policy_rev=none for a guarded source (no forged hash)` → PASS
- Confirms the guard propagates correctly through the full pipeline (renderer throws → route non-2xx → build_packet receives no policy block → audits `policy_rev=none`)

### Out-of-scope compliance
- ABS-382 `build_packet` extraction logic: **not touched** (confirmed by `git diff main...ABS-425-auto --stat` — no changes to `scripts/orchestrator.sh` policy extraction logic)
- S2/S3 write authz: not touched
- New authorship surfaces: not added

### Security flag (flags: [security])
- Security Review gate passed (independent security-engineer review; non-blocking CRLF CRLF-trailing note filed as Phase-3 follow-up — not a blocking finding, guard and consumer are in parity today)

---

## Test Suite Results

| Suite | Passed | Failed | Notes |
|---|---|---|---|
| `backend/packages/core` unit tests | 8 | 0 | 5 DB-gated skipped (CI-only); all 4 ABS-425 assertions pass |
| Orchestrator test suite (`tests/test-orchestrator.sh`) | 1211 | 0 | All 6 ABS-425 assertions pass |
| shellcheck (`tests/fixtures/policies-cap-tracker.sh`) | ✅ | — | No findings |
| TypeScript typecheck (`tsc --noEmit`) | ✅ | — | Exit 0 |

---

## Verdict: ✅ APPROVED

All 5 acceptance criteria are satisfied. The trust-boundary hardening is correctly implemented in the real S4 op renderer (`renderEffectivePolicy()` in `backend/packages/core/src/policies.ts`), proven by unit tests on the real op and validated end-to-end through the orchestrator harness. No regression. ABS-382 `build_packet` extraction left unchanged. Security Review gate passed.

**Next**: Story Acceptance (no `design` flag).
