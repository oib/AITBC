# QA Validation Report — ABS-376

**Ticket**: ABS-376 — Core workflow parser rejects the `terminal` status field (ABS-301 config drift)
**QAS actor**: qas
**Date**: 2026-07-17
**Branch**: ABS-376-auto
**Commit**: eab79d6

---

## Summary

Independent QAS validation of the `parseWorkflow` terminal-field fix. All four acceptance criteria pass. No regression found.

---

## AC Validation

### AC1 — `terminal: true` and `terminal: false` parse without throwing; unit tests assert this

**Result**: ✅ PASS

Verified by directly running:
```
node --import tsx --test packages/core/test/workflow.test.ts
```

Tests present and passing:
- `✔ terminal: true is accepted without throwing`
- `✔ terminal: false is accepted without throwing`

Parser change: `backend/packages/core/src/workflow.ts` — `terminal?: boolean` added to `StatusDef` (public) and `PartialStatus` (internal); field handler accepts `"true"` / `"false"` strings and coerces to boolean; carry-through in `finish()` follows the existing `entered_when`/`triggers` pattern.

---

### AC2 — Parsing shipped `profiles/neutral/adapters/statuses.yaml` succeeds; full test suite green including 26-status count and drift assertion

**Result**: ✅ PASS

- `diff backend/packages/core/src/workflows/statuses.yaml profiles/neutral/adapters/statuses.yaml` → **IDENTICAL** (byte-for-byte)
- Test output: `✔ AC#1: parses the shipped statuses.yaml — all 26 statuses`
- Test output: `✔ the bundled built-in copy is byte-identical to the repo file (no drift)`
- Full suite: **30 pass / 0 fail**

---

### AC3 — `terminal: notabool` throws `WorkflowParseError` naming source filename

**Result**: ✅ PASS

Test present and passing:
- `✔ terminal: non-boolean value throws WorkflowParseError naming the source (AC3)`

Implementation: non-`true`/`false` values throw `new WorkflowParseError(source, \`terminal: expected boolean (true|false), got ...\`, lineNo)` — strict fail-fast contract preserved.

---

### AC4 — `pnpm -r typecheck` and `pnpm lint` pass; test file green

**Result**: ✅ PASS

Commands run from `backend/`:
```
pnpm -C backend -r typecheck → exit 0 (core, apps/web, apps/server all clean)
pnpm -C backend lint        → exit 0
node --import tsx --test ... → 30/30 pass
```

---

## Evidence Summary

| Check | Command | Result |
|-------|---------|--------|
| Unit tests | `node --import tsx --test packages/core/test/workflow.test.ts` | 30/30 PASS |
| Typecheck | `pnpm -r typecheck` (from backend/) | exit 0 |
| Lint | `pnpm lint` (from backend/) | exit 0 |
| Drift assertion | `diff core/statuses.yaml profiles/statuses.yaml` | IDENTICAL |

---

## Scope Creep Check

- `profiles/neutral/adapters/statuses.yaml` is **untouched** by commit `eab79d6` — confirmed via `git show eab79d6 -- profiles/...` (empty)
- The large `statuses.yaml` diff in `backend/packages/core/src/workflows/statuses.yaml` is accumulated drift repair from prior merged commits (ABS-284/301/323 edges)
- The `allowedNext("In Progress")` test update reflects a pre-existing profile edge (not behavior introduced by this ticket)
- No regression in any other test

---

## Flags Check

- `flags` line on ticket: **none** (no `design` flag)
- Exit target: **Story Acceptance** (no design gate in pipeline)

---

## Final Verdict

**APPROVED** — All four AC/DoD criteria independently verified. Commit `eab79d6` on branch `ABS-376-auto` is ready for Story Acceptance.

Transitioning: `In Test → Story Acceptance`
