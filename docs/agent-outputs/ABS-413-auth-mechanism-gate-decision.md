# ABS-413 — Auth-model decision: human-only write gates assert mechanism, not role alone

- **Ticket**: ABS-413 (follow-up from the ABS-380 security review)
- **Kind**: Documented team decision (the lighter of the AC1 options). Per the PO
  guardrail on this ticket, a formal ADR is escalated to the System Architect only
  if the decision proves architecturally load-bearing beyond this gate; it does not
  — it hardens the existing `requireHuman`/`WRITER_ROLES` convention in place,
  changes no ADR, and adds no new role or surface.
- **Status**: Adopted
- **Date**: 2026-07-18

## Context

Human-only write surfaces (`policies`, `commands`, `dashboard`) authorize through the
shared `requireHuman` gate, which historically checked **role only**:
`WRITER_ROLES = [admin, maintainer]`. The stated intent — "gated to a HUMAN session"
(dashboard.ts) — was therefore not fully enforced: a **bearer (non-session) API
token** minted with role `admin`/`maintainer` passed `requireHuman`. That is the
human-vs-machine authority line for write surfaces (ADR-A-0004 / ADR-A-0005); a
privileged machine token must not be able to perform a Human act.

This is defense-in-depth, not a live regression: minting such a token requires
provisioning discipline that is itself human-only.

## Decision

Human-only write gates assert the auth **mechanism** in addition to the role. A
principal now carries `via: 'bearer' | 'session'`, stamped by whichever auth path
built it (`auth.ts` bearer path → `bearer`; `sessions.ts` cookie path → `session`).
The single shared `requireHuman` helper rejects `403` unless BOTH hold:

1. `role ∈ WRITER_ROLES` (unchanged allowlist), AND
2. `via === 'session'` (a genuine human dashboard session).

The assertion is centralized in ONE helper (`routes/guards.ts`, imported by
policies / commands / dashboard) so no gate can drift back to role-only.

## Alternatives considered

- **Keep role-only + rely on provisioning discipline (status quo)** — Rejected. The
  entire point of the ABS-380 follow-up is defense-in-depth: not depending solely on
  the discipline of never minting a privileged bearer token, but structurally
  refusing a machine mechanism on Human write surfaces.

## Scope / non-goals

- The role model itself (`orchestrator|agent|admin|viewer|maintainer`) is unchanged.
- Token-minting / provisioning policy is unchanged.
- Read (non-write) surfaces are unchanged.
- The agent-surface ADR→Accepted human-only guard (server.ts) is a separate,
  role-based guard on the `/agent` surface (bearer-only by design) and is out of
  scope — it is not a `WRITER_ROLES` gate.

## References

- ADR-A-0004 (human-approval boundaries), ADR-A-0005 (mandatory PRs / human merge).
- ABS-241 (`WRITER_ROLES` allowlist convention), ABS-333 (opaque server-side
  dashboard session), ABS-380 (policy CRUD security review, origin of this follow-up).
