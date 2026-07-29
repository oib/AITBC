# QA Validation Report — ABS-383

**Ticket:** ABS-383 — Dashboard: ADR register + policy editor with effective-policy preview  
**Branch:** `ABS-383-auto`  
**Commit:** `c8908a3 feat(ui): ADR register + policy editor with effective-policy preview [ABS-383]`  
**Diff scope:** 11 files, +1037/−13 vs `epic/ABS-231-phase3-knowledge`  
**QAS Actor:** qas  
**Date:** 2026-07-18  
**Verdict:** ✅ APPROVED → Design Test (design-flagged story)

---

## Validation Suite (Independently Run)

| Check | Command | Result |
|-------|---------|--------|
| Lint | `pnpm lint` | ✅ PASS — no errors |
| Typecheck | `pnpm -r typecheck` | ✅ PASS — all 5 workspace projects (core, web, forge, webhooks, server) |
| Build | `pnpm --filter @agentic-backend/web build` | ✅ PASS — 181 kB JS, 304 ms |

---

## Acceptance Criteria Verification

### AC1 — ADR register groups `type=adr` items by lifecycle status; detail drawer shows body, revision history, supersedes edges

**Status:** ✅ PASS

Evidence:
- `AdrView.tsx`: filters `t.type === "adr"` from board tickets, then groups by the ordered `ADR_LIFECYCLE` array (`Draft`, `Proposed — awaiting human acceptance`, `Accepted`, `Superseded`). Data-testids `adr-group-{status}` confirm grouping.
- `dashboard.ts` (detail route, +63 lines): for `type=adr` items, runs `Promise.all` over 5 queries to project: (1) comment rows, (2) transition events → `transition-reason` kind for revision history, (3) `supersedes` edge via `work_item_link`, (4) `superseded_by` reverse edge, (5) `fields` fallback. Merged and chronologically sorted.
- `TicketDrawer.tsx`: renders `detail.body` in a `<pre>`, the full `detail.comments` timeline (which for ADRs now includes revision events), and `adr_meta.supersedes`/`adr_meta.superseded_by` fields.
- `types.ts`: `AdrMeta { supersedes: string | null; superseded_by: string | null }` + `TicketDetail.adr_meta: AdrMeta | null`.

### AC2 — Human can transition ADR Draft↔Proposed and Proposed→Accepted; accept control labeled human-only

**Status:** ✅ PASS

Evidence:
- `TicketDrawer.tsx` `Actions` component: transition dropdown uses `detail.allowed_transitions` (legal next statuses from `allowedNext(workflow, status)` — the server enforces the ADR lifecycle edges).
- When `isAdr && to === "Accepted"`, the `adr-human-only-notice` element renders: "⚠ **Human-only action (ADR-A-0004)** — ADR acceptance is exclusively a human decision. Agent and orchestrator tokens are rejected server-side."
- Non-writer sessions (role not in `["admin","maintainer"]`): `isWriter(role)` returns `false` → early return showing `actions-readonly` notice; `transition-submit` absent from DOM (defense-in-depth; server enforces via `requireHuman`).
- Release toggle hidden for ADRs (`isAdr` check): no orchestration-control exposed.

### AC3 — Policy editor creates/edits/activates/retires via `/api/v1`; effective-policy preview shows `rendered` + `policy_rev` before activation

**Status:** ✅ PASS

Evidence:
- `PolicyView.tsx`: full CRUD surface — `doCreate` → `api.createPolicy`, `doUpdate` → `api.updatePolicy`, `doStatus(id, "active")` → `api.setPolicyStatus`, `doStatus(id, "retired")` → `api.setPolicyStatus`. All calls routed through `/api/v1/projects/:project/policies`.
- Activate/Retire buttons labeled with `(human-only)` span and `title="Human-only action (ADR-A-0004)"`.
- Effective-policy preview: `doPreview` → `api.getEffectivePolicy(project, audience)` → `GET /policies/effective?audience=<role>` → `requireHuman` + `resolveEffectivePolicy` (same function as S4/ABS-381) → `{ rendered, policy_rev }` JSON response. Preview displays `policy-preview-rev` (64-char hex) + `policy-preview-text` before the operator activates any policy.
- `policies.ts` diff: new `GET …/policies/effective` endpoint, requiring human session, delegating to `resolveEffectivePolicy`.
- `types.ts`: `EffectivePolicyPreview { rendered: string; policy_rev: string }`.

### AC4 — ADRs in `Proposed` appear in escalation inbox (oldest first)

**Status:** ✅ PASS

Evidence:
- `board.ts`: `ESCALATION_INBOX_STATUSES` now includes `"Proposed"` with inline comment confirming it is exclusive to `adr-lifecycle.yaml` — no regular story/epic tickets use this status, so no cross-contamination.
- Inbox query: `ORDER BY status_age_seconds DESC, w.key ASC` — `status_age_seconds` is the seconds since the item entered its current status; `DESC` = highest age first = **oldest first**. Confirmed at line 151 of `board.ts`.

### AC5 — Agent (non-human) sessions: write controls absent/rejected; e2e covers ADR-accept + policy-activate flows; lint green

**Status:** ✅ PASS

Evidence:
- **Server-side rejection:** `policies.ts` `/policies/effective` → `requireHuman(p, reply)` (returns 403 for agent tokens). All policy write endpoints (from S3/ABS-380) already gate via `requireHuman`. Dashboard write endpoints similarly gated. Agent tokens are rejected 403 server-side.
- **Client-side DOM gating:** `isWriter(role)` check in `TicketDrawer.tsx` and `PolicyView.tsx` removes write controls from DOM entirely for non-admin/maintainer sessions. Policy create button (`policy-create-open`) absent; activate/retire buttons absent; transition-submit absent.
- **e2e coverage in `knowledge.spec.ts`** (225 lines):
  - Test 1: ADR-accept flow — imports Proposed ADR via API → login → inbox shows ADR → nav to ADR Register → Proposed group contains ADR → open drawer → select "Accepted" → `adr-human-only-notice` visible → submit transition → ADR moves to Accepted group.
  - Test 2: Policy-activate flow — create fresh project → login → nav to Policies → create draft policy via UI → activate → status badge updates to "active" → preview shows `rendered` text and 64-char hex `policy_rev`.
  - Test 3: Non-writer gate — creates viewer token → logs in as viewer → opens ticket drawer → `actions-readonly` visible, `transition-submit` NOT visible → nav to Policies → `policy-create-open` NOT visible.
- **Lint:** `pnpm lint` exits 0 (confirmed by QAS independently).

---

## Guardrail Verification (ADR-A-0004 human-only boundaries)

| Guardrail | Verification | Result |
|-----------|-------------|--------|
| Agent tokens rejected server-side (all writes) | `requireHuman` on every policy write + effective preview + all dashboard writes | ✅ |
| ADR `Proposed→Accepted` visibly labeled human-only | `adr-human-only-notice` with "Human-only action (ADR-A-0004)" text | ✅ |
| Policy activate/retire visibly labeled human-only | `(human-only)` span on Activate/Retire buttons | ✅ |
| No orchestration control for ADRs | Release toggle hidden for `isAdr === true`; comment: ADRs are `orchestration_state='excluded'` at DB level | ✅ |
| No orchestration control for policies | No `orchestrator-ready` label or related control in PolicyView | ✅ |

---

## Architecture Review Gate (Prior)

System-architect independently verified commit `c8908a3` and approved `In Review → In Test` (gate-results 2026-07-17T23:53:11Z). All 5 ACs and all architecture criteria passed. QAS confirms the same conclusions via independent code inspection and gate runs.

---

## Non-Blocking Advisory (from System Architect, carried forward)

`WRITER_ROLES`/`isWriter` is duplicated across `TicketDrawer.tsx` and `PolicyView.tsx` (client-side copies). Server is authoritative; client copies are defense-in-depth convenience. A shared `web/src/util` helper would DRY this. Not a blocker.

---

## Exit

**Design flag is set** → exit target: **Design Test** (per ABS-246 exit protocol — `flags: [design]`).  
Pipeline: `In Test → Design Test → Story Acceptance`. QAS does NOT transition to Story Acceptance directly.

---

## Summary

All 5 acceptance criteria are satisfied and independently verified. The validation suite (lint, typecheck ×5 packages, build) passes. Server-side human-only guardrails are in place and verified. E2e tests cover all critical flows. No blocking issues found.

**Verdict: ✅ APPROVED — releasing to Design Test**
