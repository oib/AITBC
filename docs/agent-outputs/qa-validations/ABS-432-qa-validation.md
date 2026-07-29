# QA Validation Report — ABS-432

**Ticket**: ABS-432 — CR/\r parity for reserved-marker guard vs `build_packet` consumer (S4 `policies` op, defense-in-depth)
**Branch**: `ABS-432-auto`
**Commit**: `f8f96a2`
**Validator**: QAS (independent gate)
**Date**: 2026-07-18
**Verdict**: ✅ APPROVED

---

## Acceptance Criteria Verification

### AC1 — CRLF-terminated reserved marker causes `renderEffectivePolicy()` to throw ✅ PASS

Two new unit tests in `backend/packages/core/test/policy-resolution.test.ts`:

| Test | Result |
|---|---|
| `ABS-432: a CRLF-terminated '=== TICKET ===\r' marker line fails loudly (AC1)` | ✔ PASS (0.08025ms) |
| `ABS-432: a CRLF-terminated 'policy_rev:\r' marker line fails loudly (AC1)` | ✔ PASS (0.09ms) |

Both assert `throws /reserved marker line/` — independently verified by running the full test suite.

Implementation: `assertNoReservedMarkers()` in `backend/packages/core/src/policies.ts` now tests
`rawLine.replace(/\r/g, "")` before `RESERVED_POLICY_LINE`, so CRLF-terminated and CR-obfuscated
markers are rejected. The error message reports the raw (unstripped) line via `JSON.stringify(rawLine)`
for diagnostic clarity.

### AC2 — Contract doc states the CR-parity invariant explicitly ✅ PASS

```bash
# grep evidence:
docs/guides/AGENTIC-BACKEND-API.md:1965:**CR-parity invariant (ABS-432 — defense-in-depth).** The render-time guard and any
```

Clause is present at `AGENTIC-BACKEND-API.md:1965`, immediately adjacent to the ABS-425
reserved-markers clause. The clause describes the invariant, its mechanism, and the fail-closed
intent if the policy trust model later loosens.

### AC3 — Well-formed policy renders byte-identically (no regression) ✅ PASS

```
✔ ABS-432: a clean body (no CR markers) renders byte-identically to today (AC3, no regression) (0.115875ms)
```

The test asserts:
1. `eff.rendered == again.rendered` — byte-stable across two identical calls
2. `eff.policyRev == sha256(eff.rendered, "utf8").hex` — hash matches
3. `eff.rendered` does not match `/\r/` — no CR introduced by the guard path

Existing ABS-425 tests remain green:
- `ABS-425: a body with a leading 'policy_rev:' line fails loudly at render time (AC2)` ✔
- `ABS-425: a body with a '=== TICKET ===' marker line fails loudly (AC3)` ✔
- `ABS-425: a body with a '=== POLICY (policy_rev: …) ===' marker line fails loudly (AC3)` ✔
- `ABS-425: a well-formed body with only look-alike prose renders unchanged (AC4, no false positive)` ✔

### AC4 — tsc/eslint green; shellcheck N/A ✅ PASS

```
pnpm -r typecheck  → Done (5 projects: packages/core, apps/web, packages/forge, packages/webhooks, apps/server)
pnpm lint          → exit 0 (no output = clean)
shellcheck         → N/A: no shell scripts touched in commit f8f96a2
```

---

## Full Test Suite Run

```
pnpm test (backend/packages/core):
  tests 211 | pass 126 | fail 0 | skipped 85 | duration 3302ms
  
  DB-gated skips: 85 cases require DATABASE_URL; execute in CI (expected, documented in ticket).
  ABS-432 specific: 3/3 PASS (0 fail)
```

---

## Security / Architecture Notes (re-verified independently)

- **Fail-closed direction**: guard is now **stricter** than the `build_packet` consumer.
  The consumer at `orchestrator.sh:7425-7428` uses `^`-anchored `sed` with **no CR stripping** —
  a CRLF marker is rejected by the `sed` `^` anchor. The guard strips ALL `\r` before testing,
  rejecting what any CR-stripping consumer would also reject AND what the current non-CR-stripping
  consumer rejects. Stricter-than-consumer is the correct defense-in-depth direction (confirmed by
  System Architect Stage 1 + Security Review gate).
- **No mutation of `rendered`**: `rawLine.replace(/\r/g, "")` operates on a local variable; the
  `rendered` string itself is untouched. Clean input (no `\r`) produces byte-identical output.
- **No RLS/authz/migration surface touched**: `resolveEffectivePolicy` and all DB paths are
  unchanged.
- 1 non-blocking follow-up filed by security-engineer (generalize parity to non-LF Unicode line
  terminators when Phase-3 policy-authorship surface matures) — out of scope for ABS-432.

---

## Files Changed in Commit f8f96a2

| File | Purpose |
|---|---|
| `backend/packages/core/src/policies.ts` | CR-strip guard in `assertNoReservedMarkers()` |
| `backend/packages/core/test/policy-resolution.test.ts` | 3 new ABS-432 tests (AC1 ×2 + AC3) |
| `docs/guides/AGENTIC-BACKEND-API.md` | CR-parity invariant clause (AC2) |

---

## Verdict

**APPROVED for Story Acceptance.**

All 4 ACs met. Test suite: 126 pass / 0 fail (85 DB-gated skips expected). Typecheck Done.
Lint clean. No shell scripts touched (shellcheck N/A). Security-flagged story reviewed and
approved by both System Architect and Security Engineer prior to this gate. Guard is fail-closed
(stricter than the consumer), rendered bytes unchanged for clean input.

`flags: [security]` — no `design` flag → exit transition: **Story Acceptance**.
