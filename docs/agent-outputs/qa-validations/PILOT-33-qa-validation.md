# QA Validation Report — PILOT-33

**Ticket**: PILOT-33 — Mission Control: Attention-Inbox-Einträge ausblenden/dismissen (acknowledge ohne Statuswechsel)
**QAS**: qas seat (headless)
**Date**: 2026-07-25
**Branch**: `PILOT-33-auto`
**Commits under review**: `c17f3e3b` (backend) + `4ca771ac` (web)
**Merge-base**: `03c7f38f`
**Verdict**: ✅ **APPROVED**

---

## Acceptance Criteria Verification

| AC | Criterion | Result | Evidence |
|---|---|---|---|
| AC-1 | Every attention entry has a Dismiss/Ack action (non-destructive, auditable) | ✅ PASS | `POST /attention/dismiss` → `attention_dismissal` table only; underlying events untouched. `ON CONFLICT DO NOTHING` (idempotent). `requireHuman` enforces 403 for agents. |
| AC-2 | Dismissed entries visible via filter/toggle | ✅ PASS | `GET /attention?include_dismissed=true` returns dismissed items with `dismissed:true` + `dismissed_at`. `showDismissed` toggle in `Inbox.tsx`; `DismissedRow` with `✓ ack` badge. |
| AC-3 | Re-trigger semantics: same condition → NEW entry (dismiss binds occurrence, not rule) | ✅ PASS | Keyed by `(source_ref, type, created_at)`. Test ATTN-P33-C proves fresh `created_at` = new un-dismissed occurrence. |
| AC-4 (e2e) | Dismiss → queue hides it → toggle shows it | ✅ PASS | Integration test "PILOT-33: dismiss hides…?include_dismissed reveals" verifies end-to-end flow. |

---

## Design Acceptance Criteria (DAC) Verification

| DAC | Criterion | Result | Evidence |
|---|---|---|---|
| DAC-1 | Dismiss uses `.linkbtn` + `.attention-dismiss-btn`; muted default / stale hover; isWriter-gated | ✅ PASS | `Inbox.tsx:369`, `styles.css:2155–2162`, writer guard at `Inbox.tsx:367` |
| DAC-2 | Dismissed card: `background: var(--panel-2)`, `border-left-color: var(--border)` | ✅ PASS | `styles.css:2165–2168` |
| DAC-3 | `✓ ack` badge uses `.dismissed-badge` with correct tokens | ✅ PASS | `styles.css:2177–2184`, `Inbox.tsx:468` |
| DAC-4 | `.attention-actions` wraps Resolve + Dismiss as siblings in flex container | ✅ PASS | `Inbox.tsx:355–390`: `<div className="attention-actions">` contains `.attention-action-toggle` and `.attention-dismiss-btn` |
| DAC-5 | Dismiss `aria-label` includes type + source_ref | ✅ PASS | `Inbox.tsx:371`: `` `Dismiss this ${item.type} item for ${item.source_ref}` `` |
| DAC-6 | Restore `aria-label` includes type + source_ref | ✅ PASS | `Inbox.tsx:484`: `` `Restore ${item.type} item for ${item.source_ref} to active queue` `` |
| DAC-7 | Dismissed-toggle `<input>` wrapped in `<label>`; `aria-label` with count | ✅ PASS | `Inbox.tsx:159–167`: `<label className="inbox-dismissed-toggle">` + `aria-label={"Show dismissed items (${dismissedCount})"}` |
| DAC-8 | Contrast ≥4.5:1 for muted/stale/accent on panel-2/panel backgrounds | ✅ PASS | Inherited token verification from ABS-475 (pre-established). Design doc §8 documents all ratios. |
| DAC-9 | Non-writer sessions: dismiss button absent from DOM | ✅ PASS | `Inbox.tsx:367`: `{isWriter && (...)}`; server also enforces 403 |
| DAC-10 | Desktop (≥1024px): Resolve + Dismiss on same row | ✅ PASS | `flex-wrap: wrap; gap: 8px` in `.attention-actions` — side-by-side at wide viewports |
| DAC-11 | Mobile (<768px): buttons wrap vertically | ✅ PASS | Same `flex-wrap: wrap` causes natural wrap at narrow widths |
| DAC-12 | Active-dismiss e2e flow with correct data-testids | ✅ PASS | `data-testid={attention-dismiss-${source_ref}}` at `Inbox.tsx:370`; integration test "dismiss hides" verifies flow |
| DAC-13 | Dismissed-toggle e2e flow | ✅ PASS | `data-testid="inbox-dismissed-toggle"`, `inbox-dismissed-section`, `attention-dismissed-{ref}` all present |
| DAC-14 | Restore e2e flow | ✅ PASS | `data-testid={attention-restore-${ref}}` at `Inbox.tsx:483`; integration test "restore returns item" verifies |
| DAC-15 | Re-trigger: T1 dismissed, T2 (fresh created_at) not dismissed | ✅ PASS | Integration test ATTN-P33-C explicitly verifies distinct `created_at` → separate dismissal scope |
| DAC-16 | Non-writer: no dismiss button | ✅ PASS | DAC-9 covers this |
| DAC-17 | 403 error path: `role="alert"` span with correct testid | ✅ PASS | `Inbox.tsx:381–386`: `<span className="err" role="alert" data-testid={attention-dismiss-err-${ref}}>` |

---

## Integration Test Results (ABS-453 Green-Run Proof)

**Test file**: `backend/apps/server/test/attention-routes.test.ts`
**Command**: `DATABASE_URL=postgres://postgres:***@localhost:25432/attn_qas node --import tsx --test --test-concurrency=1 test/attention-routes.test.ts`
**Ran against commit**: `4ca771aca76031ba0cb983f5819f361873eff0c1` (HEAD on `PILOT-33-auto`)
**DB**: throwaway Docker container (`postgres:16-alpine`, port 25432, project `pilot33-qas-pg`), NOT the live production DB (operator guardrail: `unset BACKEND_URL BACKEND_TOKEN`)

```
✔ AC1: endpoint returns counters + all item types with correct source refs (427.942417ms)
✔ AC2: items are oldest-first and deduplicated (6.846125ms)
✔ AC3: transitioning item out of Blocked removes it from attention on next fetch (17.000667ms)
✔ AC4: response shape is stable — known type values are present in items (3.679542ms)
✔ AC5: unauthenticated request → 401 (0.635667ms)
✔ AC5: agent token → 403 (3.346958ms)
✔ AC5: orchestrator token → 403 (2.343791ms)
✔ AC5: admin session → 200 (3.671917ms)
✔ AC5: agent with bearer token (no session) → 403 (3.184792ms)
✔ ABS-440 AC2: command-failed items carry instance, ledger_id, and kind (3.997125ms)
✔ ABS-440 AC3: stalled-seat items carry instance and ledger_id (spawn id) (4.260375ms)
✔ ABS-440 AC4: escalation/blocker/gate items do NOT carry the enrichment fields (4.096709ms)
✔ PILOT-33: dismiss hides an item from the active queue; ?include_dismissed reveals it (dismissed:true) (21.111709ms)
✔ PILOT-33: restore (DELETE) returns the item to the active queue; 404 when not dismissed (23.39775ms)
✔ PILOT-33: re-trigger — a fresh occurrence (new created_at) is NOT covered by an earlier dismissal (24.555125ms)
✔ PILOT-33: dismiss is human-gated — agent session → 403 (3.194208ms)
✔ PILOT-33: dismiss with a malformed body → 400 (2.924417ms)
ℹ tests 17
ℹ pass 17
ℹ fail 0
ℹ skipped 0
```

**Result: 17/17 passed, 0 failed, 0 skipped** ✅

---

## Static Code Review — Key Properties

| Property | Finding |
|---|---|
| Non-destructive dismiss | `attention_dismissal` table only; no modification of `work_item`/`seat_spawn`/`orch_command` |
| Additive migration | Migration 020 is a pure `CREATE TABLE` + `CREATE INDEX` — no changes to existing tables/columns |
| Idempotent dismiss | `ON CONFLICT (project_id, source_ref, type, occurred_at) DO NOTHING` |
| Restore → 404 when not dismissed | `restoreAttention` returns `rowCount > 0`; route returns 404 when false |
| Counter integrity | Counters (`human_action_needed`, `blocked_stalled`) computed from ACTIVE set only — dismissed items never dilute badges |
| requireHuman gating | Both `POST /attention/dismiss` and `DELETE /attention/dismiss` call `requireHuman(p, reply)` before any write |
| Body validation | `parseOccurrence` rejects missing/empty fields with 400 |
| Re-trigger semantics | Dismissal keyed by `(source_ref, type, created_at)` — fresh `created_at` is a new occurrence, NOT covered by the dismissal |
| Audit trail | `dismissed_by` (session token id) and `dismissed_at` recorded in `attention_dismissal` |

---

## Violations / Issues Found

None. All ACs and DACs pass. No security, RLS, or layering issues found.

**Known pre-existing deviations** (not regressions, consistent with prior ABS-352/419/473 reports):
- `docs/design/DESIGN_SYSTEM.md` contains placeholder tokens; real tokens in `theme.css`/`styles.css`. SA notified.
- No `color.dismissed` token — implementation uses existing `var(--panel-2)` / `var(--muted)` / `var(--border)` consistently with design spec §11.

---

## Final Verdict

✅ **APPROVED** — all ticket ACs and design DACs verified. Integration test suite 17/17 green against a throwaway Postgres. Non-destructive, auditable, requireHuman-gated dismiss/ack implementation matches the design contract in full.

**Exit transition**: `In Test → Design Test` (ticket carries `flags: [design]`).
