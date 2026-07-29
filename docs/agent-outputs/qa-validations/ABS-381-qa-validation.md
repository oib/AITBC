# QA Validation — ABS-381
**S4: `policies` adapter op + `capabilities` advertisement**
**Date:** 2026-07-18
**Branch:** ABS-381-auto | **Commit:** 9b3fbba
**Validator:** qas

---

## Summary

Independent validation of commit `9b3fbba` on `ABS-381-auto` (4 files, +91/−5).
All five acceptance criteria verified. Full test suite: **142/142 PASS**.

---

## Validation Suite Results

| Check | Command | Result |
|-------|---------|--------|
| TypeScript type-check | `pnpm -r typecheck` | ✅ PASS (5 pkgs) |
| Lint | `pnpm lint` (ESLint) | ✅ PASS (exit 0) |
| Conformance suite | `bash tests/test-backend-tracker.sh` | ✅ 142/142 PASS |

---

## AC/DoD Checklist

### AC 1 — `GET /policies?audience=<role>` returns rendered text + `policy_rev` line; omitting audience returns union

**Status: ✅ PASS**

Evidence (Test 16):
- `policies --audience returns the audience-specific policy` → PASS
- `policies --audience includes policy body` → PASS
- `policies --audience includes audience-NULL (all-audiences) policy` → PASS
- `policies response includes a policy_rev line` → PASS
- `policies (no audience) returns all-audiences union` → PASS
- `policies (no audience) includes policy_rev line` → PASS

Implementation: `registerAgentPolicyRoutes` in `routes/policies.ts` — reuses `resolveEffectivePolicy` from S3 (ABS-380), returns `text/plain` body `${eff.rendered}policy_rev: ${eff.policyRev}\n`. Route scoped via `principal.targetProjectId` (tenant isolation).

### AC 2 — `backend-tracker.sh policies --audience <role>` verbatim, exit 0; error semantics (die) for unknown flag/missing value

**Status: ✅ PASS**

Evidence (Test 16):
- `policies --audience returns the audience-specific policy` → PASS (exit 0, body verbatim)
- `policies: unknown flag rejected with non-zero exit` → PASS
- `policies: --audience without value rejected with non-zero exit` → PASS

Implementation: `cmd_policies` in `scripts/backend-tracker.sh` (line 324-332). Uses `die` for unknown arguments and missing `--audience` value; follows the `cmd_search` `-G ${q[@]+"${q[@]}"}` pattern.

### AC 3 — `capabilities` output includes `policies` (alongside `packet`, `brief`)

**Status: ✅ PASS**

Evidence (Test 14):
- `capabilities lists 'packet' on its own line` → PASS
- `capabilities lists 'brief'` → PASS
- `capabilities lists 'policies' (S4 / ABS-381)` → PASS

Implementation: `server.ts` line 171: `"packet\nbrief\npolicies\n"`.

### AC 4 — Agent token accepted; op performs no writes (no new events)

**Status: ✅ PASS**

Evidence: Route registered under `/agent/v1/*` path which is covered by the global `onRequest` bearer guard (`isGuarded`). Route is `GET` only; delegates entirely to `resolveEffectivePolicy` which performs a single read-only `SELECT` (active policies, org+project scoped). No `INSERT`/`UPDATE`/`DELETE` calls; no event bus emissions. No `requireHuman` gate (agents need read access). System Architect verified auth/tenant-scoping and guardrail.

### AC 5 — `tests/test-backend-tracker.sh` gains `policies` assertions; adapter < line budget; tests + lint green

**Status: ✅ PASS** (with note)

Evidence:
- Test 16: 10 new assertions added to `tests/test-backend-tracker.sh` → all PASS
- Adapter: 364 lines (S3 already exceeded original 300-line target; disclosed by be-developer, accepted by architect)
- `pnpm -r typecheck`: PASS (5 packages)
- `pnpm lint` (ESLint): PASS (exit 0)
- Conformance suite: 142/142 PASS

**Note on line budget:** The original 300-line "target" was exceeded by S3 (ABS-380). S4 adds 18 lines, bringing total to 364. The be-developer disclosed this; the system architect approved it. The constraint intent (keeping the adapter lean) is satisfied in spirit — no blocker.

---

## Guardrail Verification

| Guardrail | Verified |
|-----------|----------|
| READ-ONLY: no write path on the agent surface | ✅ GET route only, no write op |
| Active-only: draft/retired policies excluded | ✅ `resolveEffectivePolicy` uses `status='active'` SQL filter |
| Tenant isolation: foreign-org rows invisible | ✅ `org_id=$1` scoped in both query and renderer |
| No `orchestrator-ready` write semantics | ✅ Confirmed — read-only op |

---

## Test 16 Detail (all 10 assertions)

```
PASS  policies --audience returns the audience-specific policy
PASS  policies --audience includes policy body
PASS  policies --audience includes audience-NULL (all-audiences) policy
PASS  policies response includes a policy_rev line
PASS  policies (no audience) returns all-audiences union
PASS  policies (no audience) includes policy_rev line
PASS  policies --audience with no matching policies exits 0
PASS  policies (no match) still returns a policy_rev line
PASS  policies: unknown flag rejected with non-zero exit
PASS  policies: --audience without value rejected with non-zero exit
```

---

## Verdict

**✅ APPROVED**

All 5 ACs verified. 142/142 conformance assertions PASS. TypeScript clean (5 pkgs). Lint clean.
Guardrail (READ-ONLY, active-only, tenant-scoped) confirmed. Releasing to Story Acceptance.

*No `design` flag in ticket labels — exit target: Story Acceptance.*
