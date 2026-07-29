# QA Validation Report -- ABS-441

**Ticket**: ABS-441 -- Line-terminator parity for reserved-marker guard vs build_packet consumer
**Branch**: ABS-441-auto
**Commit**: df4a9c6
**QAS actor**: qas
**Date**: 2026-07-18
**Verdict**: APPROVED

---

## Summary

Defense-in-depth security follow-up to ABS-432 CR-parity. Generalises the
assertNoReservedMarkers() guard in renderEffectivePolicy() to reject NEL (U+0085),
LS (U+2028), and PS (U+2029) in addition to the existing LF/CR parity. No live
vulnerability today (consumer is caret-anchored LF-delimited sed); closes the
theoretical guard/consumer parity gap before Phase-3 policy-authorship matures.

---

## Acceptance Criteria Verification

| # | Criterion | Evidence | Result |
|---|-----------|----------|--------|
| AC1 | NEL/LS/PS delimited or terminated reserved markers cause renderEffectivePolicy() to throw | 6 ABS-441: test cases green: NEL x2, LS x2, PS x2 in test/policy-resolution.test.ts:221-233 | PASS |
| AC2 | S4 policies op contract doc generalises CR-parity clause to name NEL/LS/PS | docs/guides/AGENTIC-BACKEND-API.md:1986-2004 -- Line-terminator-parity invariant (ABS-432 CR-parity, generalized by ABS-441); CR clause retained at 1991; NEL/LS/PS named at 1995 | PASS |
| AC3 | Clean body (no embedded Unicode line terminators) renders byte-identically -- no regression | ABS-441 byte-identity test green; existing ABS-425 + ABS-432 clean-render tests all green; guard is throw-only path, no mutation of rendered | PASS |
| AC4 | tsc/eslint green on touched backend files; shellcheck N/A (no shell scripts touched) | pnpm -r typecheck green (5/5 workspaces); pnpm lint exit 0; no .sh files in df4a9c6 | PASS |

---

## Gate Results

| Gate | Command | Result |
|------|---------|--------|
| Unit tests (core) | pnpm test (from backend/packages/core) | 133 pass / 0 fail / 85 skipped (DB-gated, run in CI per ABS-287) |
| TypeScript (all workspaces) | pnpm -r typecheck (5 workspaces) | GREEN |
| Lint (eslint) | pnpm lint | exit 0 |
| Shellcheck | N/A -- no .sh files touched | N/A |

---

## ABS-441 Tests Run (AC1/AC3)

ABS-441: a reserved marker delimited by NEL (U+0085) fails loudly at render time (AC1) - PASS
ABS-441: a policy_rev: marker terminated by NEL (U+0085) fails loudly at render time (AC1) - PASS
ABS-441: a reserved marker delimited by LS (U+2028) fails loudly at render time (AC1) - PASS
ABS-441: a policy_rev: marker terminated by LS (U+2028) fails loudly at render time (AC1) - PASS
ABS-441: a reserved marker delimited by PS (U+2029) fails loudly at render time (AC1) - PASS
ABS-441: a policy_rev: marker terminated by PS (U+2029) fails loudly at render time (AC1) - PASS
ABS-441: a clean body (no Unicode line terminators) renders byte-identically to today (AC3, no regression) - PASS

Prior-generation parity tests confirming no regression:
ABS-432: a CRLF-terminated === TICKET ===\r marker line fails loudly (AC1) - PASS
ABS-432: a CRLF-terminated policy_rev:\r marker line fails loudly (AC1) - PASS
ABS-432: a clean body (no CR markers) renders byte-identically to today (AC3, no regression) - PASS
ABS-425: a body with a leading policy_rev: line fails loudly at render time (AC2) - PASS
ABS-425: a body with a === TICKET === marker line fails loudly (AC3) - PASS

---

## Implementation Review Notes

- Guard runs on final rendered bytes before policyRev = sha256(rendered) and before the S5 build_packet consumer -- byte-parity confirmed.
- Fail-closed: NON_LF_LINE_TERMINATOR = /[u0085u2028u2029]/u is a single O(n) regex on the final rendered string; minimal surface, no over-engineering.
- CR-parity (ABS-432) untouched: per-line rawLine.replace(/r/g, '') still at line 383 of policies.ts.
- VT/FF exclusion is an on-the-record architect + ticket-scope decision (YAGNI, no live consumer) -- not a silent fold.
- Scope: 3 files only (policies.ts, policy-resolution.test.ts, AGENTIC-BACKEND-API.md). Diff is clean, right altitude.

---

## Prior Reviews Accepted

- System Architect (2026-07-18T17:30:45Z): APPROVED -- pattern compliance, trust-boundary correct, fail-closed on every path, layering clean.
- Security Engineer (2026-07-18T17:47:07Z): PASS -- no blocking findings; parity verified; no injection/authz/secret surface; VT/FF omission is documented scope decision.

---

## Verdict

APPROVED -- all 4 ACs met, all gates green, prior reviews passed. No issues found.
Ticket has flags: [security] -- no design flag -- transition to Story Acceptance.
