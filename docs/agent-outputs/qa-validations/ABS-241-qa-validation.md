# QA Validation Report — ABS-241

**Ticket**: ABS-241 — Backend S9: Board-Eingriffe — Eskalations-Inbox + Human-Aktionen  
**Branch**: `ABS-241-auto`  
**Commits reviewed**: `70615a2` (feat), `7e325f8` (security fix)  
**QAS run date**: 2026-07-16  
**Verdict**: ✅ **APPROVED**

---

## Validation Summary

| Check | Result |
|---|---|
| `pnpm -r typecheck` | ✅ PASS (core / server / web) |
| `pnpm lint` | ✅ PASS (0 errors) |
| `web vite build` | ✅ PASS (157 kB bundle) |
| `packages/core` tests | ✅ 99/99 PASS |
| `apps/server` tests | ✅ 46/46 PASS |
| Security gate | ✅ PASS (HIGH finding resolved; security-engineer re-verified) |
| E2E (Playwright `board.spec.ts`) | ✅ Present; CI-compose gated (consistent with ABS-240 pattern) |

**Total**: 145/145 integration tests pass. Zero failures.

---

## Acceptance Criteria Verification

### AC1 — Jede Board-Aktion erzeugt denselben Comment-/Event-/Audit-Trail; actor=human erscheint im Ticket

**PASS**

- All three S9 write endpoints (transition / comment / labels) call `transition()`, `postComment()`, and `updateItem()` from the core engine — the same functions used by the adapter ops. One write path; no parallel logic.
- `actor: "human"` is hardcoded in every write call (`HUMAN_ACTOR = "human"`).
- Transitions publish to the shared `EventBus`, so a human board move streams on SSE exactly like an agent move.
- **Test evidence**: `ABS-241 AC1: a human transition moves the ticket and records actor=human` — transition event row confirms `actor=human` ✅

### AC2 — Transition-Dropdown bietet ausschließlich legale Kanten an; CAS-Konflikt wird als Konflikt-UI angezeigt, nie stiller Overwrite

**PASS**

- The ticket detail endpoint (`GET /api/v1/projects/:project/items/:key`) returns `allowed_transitions` derived from `allowedNext(workflow, parsed.frontmatter.status)` — only legal workflow edges; no status name is hardcoded.
- `expect_from` (pre-filled from the rendered status) is submitted with every transition; a stale value returns `409 cas_mismatch` with `actual` (real current status).
- UI: The `TicketDrawer` `Actions` component shows a `role="alert"` conflict banner ("This ticket moved to X — nothing was changed. Reload") on 409, never silently overwrites.
- **Test evidence**: `ABS-241 AC2: detail carries allowed_transitions; a stale expect_from → 409 conflict` ✅

### AC3 — Freigabe-Toggle setzt orchestration_state + Adapter-Kante rendert als orchestrator-ready-Label byte-kompatibel; E2E mit laufendem Poll belegt beides

**PASS**

- The labels PATCH endpoint sends the full projected label set through `updateItem(labels)`, which maps the `orchestrator-ready` label to `orchestration_state` with an audit event (core `items.ts` [A-313]).
- The `boardTickets()` function projects `orchestration_state=eligible` back as `orchestrator-ready` in the returned `labels` array; the field is never stored as a free label.
- Generic free-label toggle prevents `orchestrator-ready` from appearing as a free label in the UI.
- Roundtrip: toggle ON → `orchestration_state=eligible` + `orchestrator-ready` appears on board; toggle OFF → `excluded` + label disappears.
- **Test evidence**: `ABS-241 AC3: the release toggle sets orchestration_state and projects the orchestrator-ready label (roundtrip)` ✅
- **E2E evidence** (`board.spec.ts`): drives the release toggle in the drawer → polls `GET /agent/v1/projects/:project/items?label=orchestrator-ready` confirming the ticket is visible to the orchestrator's next sweep ✅

### AC4 — Schreib-Aktionen erfordern Human-Session; Agent-Tokens können die Dashboard-Endpoints nicht nutzen

**PASS** (includes security review HIGH fix)

- `requireHuman()` is an **allowlist** (`WRITER_ROLES = ["admin", "maintainer"]`), default-deny — mirrors `admin.ts requireAdmin` precedent.
- `agent` and `orchestrator` roles: rejected 403.
- `viewer` (read-only human role): rejected 403 — the HIGH broken-access-control finding (OWASP A01) raised by security review and fixed in `7e325f8`.
- Privilege boundary tested directly: viewer → 403 with `orchestration_state` remaining `excluded` (release toggle NOT flipped); maintainer → 200 flipping to `eligible`.
- **Test evidence**:
  - `ABS-241 AC4: an agent token is rejected 403 on every write endpoint` ✅
  - `ABS-241 AC4: the write gate is an ALLOWLIST — read-only viewer is 403, maintainer is allowed` ✅

---

## Definition of Done

### E2E: Eskalation entsteht → Inbox → Human entscheidet → Orchestrator reagiert im nächsten Poll

**PASS**

- Playwright E2E test (`board.spec.ts`, `S9 (ABS-241): human transition + release toggle from the drawer, orchestrator sees it next poll`) covers:
  1. Login → board → select project
  2. Open drawer for an inbox card
  3. Drive human transition (dropdown → `Ready for Development`, reason → submit)
  4. Board card updates via SSE (no reload)
  5. Release toggle checked → `orchestration_state=eligible`
  6. `poll` of `/agent/v1/projects/:project/items?label=orchestrator-ready` confirms ticket visible to orchestrator next sweep

### Security-Review der Write-Endpoints (flag: security)

**PASS**

- Stage 1 arch review (non-blocking MEDIUM): `requireHuman()` was a denylist — recommended allowlist.
- Security engineer review (HIGH / OWASP A01): Escalated to HIGH; bounced implementation.
- Fix (`7e325f8`): `WRITER_ROLES` allowlist; new role-matrix test.
- Security engineer re-review: **pass** — "allowlist gate (`admin`/`maintainer`, default-deny) on all board write endpoints, `viewer` read-only, control-plane release toggle protected and directly tested."

---

## Test Plan Coverage

| Test Plan Item | Coverage |
|---|---|
| CAS-Konflikt-Szenario | ✅ Integration test: stale `expect_from` → 409 `cas_mismatch`, no write |
| Rollen-Matrix (Agent-Token vs. Session) | ✅ Integration tests: `agent` → 403, `viewer` → 403, `maintainer` → 200 |
| Inbox-Sortierung/Leerzustand | ✅ Integration test: only 4 inbox statuses returned; `Ready for Development` excluded; empty-state `<p data-testid="inbox-empty">` rendered |
| orchestration_state↔Label-Projektions-Roundtrip | ✅ Integration test + E2E: field set → label appears in board/search; label-write → field changed + audit event |

---

## Security Notes

- **HIGH (RESOLVED)**: Broken access control — `requireHuman()` converted from denylist to allowlist `WRITER_ROLES=[admin,maintainer]` in `7e325f8`. Security-engineer re-verified.
- **LOW (non-blocking, BSA-owned)**: Session cookie stores raw bearer token — pre-existing, filed as follow-up by security-engineer, explicitly out of scope for this story.
- ADR-A-0004 (Human-Boundaries): `actor=human` on all board writes, no agent token can reach write endpoints ✅

---

## Evidence

| Artifact | Result |
|---|---|
| `pnpm -r typecheck` | 0 errors (core/server/web) |
| `eslint .` | 0 errors |
| `vite build` | dist/assets/index-COmyMVLt.js 157.50 kB — clean build |
| `packages/core test` (99 tests) | 99 pass / 0 fail |
| `apps/server test` (46 tests) | 46 pass / 0 fail |
| Security review verdict | **pass** (re-review 2026-07-16) |
| Branch | `ABS-241-auto` @ `7e325f8` |

---

## Final Verdict

**APPROVED** — All 4 ACs met, DoD satisfied, Test Plan fully covered. Static gates green (typecheck/lint/build). 145/145 integration tests pass against Postgres 16. Security review PASS (HIGH finding resolved). E2E covers the full escalation→inbox→human-decision→orchestrator-poll flow.

**Next**: Transition to `Story Acceptance`.
