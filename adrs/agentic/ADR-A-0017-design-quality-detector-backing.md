---
id: ADR-A-0017
title: Design-quality detector as backing for the design-system-check gate — vendored, pinned, profile-gated
status: accepted
scope: agentic
date: "2026-07-09"
accepted_by: "Raphael Sahann (POPM)"
accepted_date: "2026-07-11"
---

## Context

The boilerplate already defines the *seams* for design-quality enforcement but ships no
concrete engine behind them:

- The **design-system adapter** (`profiles/neutral/adapters/design-system.md`) declares a
  `check(change_ref)` operation whose stated job is to back a **`design-system-check`
  quality gate**: "token misuse, off-system components, constraint violations." No
  implementation is bound to it.
- The **qas-design** seat (`.claude/agents/qas-design.md`) is a *gate*, not a reviewer:
  designs do not proceed without its approval. It is `Bash`-only in the headless lane,
  reaches the tracker exclusively via `$TRACKER_CMD` (ADR-A-0007), and must produce
  **objective, testable evidence** per DAC. Today it has no deterministic instrument to
  produce that evidence — it depends on the designer's hand-authored criteria alone.
- The **ui-ux-design** seat consumes a file-backed design system (`{{DESIGN_SYSTEM_PATH}}`,
  default `docs/design/DESIGN_SYSTEM.md`) and is forbidden from inventing ad-hoc styles,
  but has no vocabulary or checklist for the *AI-generated-design-tells* class of defect
  (homogeneous fonts, gray-on-color, purple→blue gradients, sub-44px targets, skipped
  heading levels).

[impeccable](https://github.com/pbakaus/impeccable) (Apache-2.0, Paul Bakaus) supplies
exactly the missing engine: a **deterministic detector** of 45 anti-pattern rules that
runs as a CLI with **no LLM/API call**, emits JSON, is CI-friendly, and carries a
file/line/value waiver system. It also ships a skill with 23 design commands
(`critique`, `polish`, `harden`, `typeset`, `layout`, …) and an optional post-edit hook.

The detector is a near-perfect fit for a `Bash`-only, evidence-producing gate. The skill
and hook are useful but overlap with an existing seat and with the repo's hook-governance
discipline, so they carry more integration risk.

#PATH_DECISION — three ways to consume impeccable were considered:
1. **Floating `npx impeccable`** at gate time — rejected: violates the self-hosting
   provenance model (ADR-A-0013); a governed run cannot depend on an unpinned network
   fetch whose behavior can change between runs.
2. **New `.claude/agents/` role** ("design-quality agent") — rejected: `ui-ux-design`
   already owns design vocabulary and `qas-design` already owns the design gate. Adding a
   role duplicates an owned function (violates the reuse-existing-roles rule and role-
   collapsing guidance).
3. **Vendored + pinned engine behind the existing adapter/gate** — chosen.

## Decision

Adopt impeccable's **detector** as the concrete backing for the design-system adapter's
`check()` operation and the `design-system-check` gate, under three governance constraints.
The skill and hook are staged as *later, optional* tiers, not part of this decision's
mandatory surface.

**1. Detector is the `design-system-check` backing (Tier 1, mandatory surface).**
The detector implements `check(change_ref)`. `qas-design` invokes it via `Bash`, treats
its JSON output as gate evidence (PASS/FAIL per rule), and posts that evidence through
`$TRACKER_CMD` — no new MCP dependency, no LLM call, consistent with the headless lane.
It **augments, never replaces**, the designer's DAC: hand-authored acceptance criteria
remain required; the detector adds a deterministic floor.

**2. Vendored and version-pinned, never floating.**
The detector payload is vendored (git submodule or copied payload pinned to a release
tag), not fetched via unpinned `npx` at gate time. Its pinned version is recorded so the
self-hosting stable checkout (ADR-A-0013) fully determines gate behavior. Apache-2.0
attribution is added to `NOTICE`.

**3. Profile-gated on the design system being enabled.**
The gate is active only when `config.design_system.enabled: true`. The **neutral** profile
and backend-only stacks pull nothing. This mirrors the adapter's existing "stack fully
works without a design system" contract.

**4. Single design-contract source — no duplication.**
impeccable's `init` produces `PRODUCT.md`/`DESIGN.md`; the repo already has
`{{DESIGN_SYSTEM_PATH}}` (`docs/design/DESIGN_SYSTEM.md`). One is the source of truth and
the other a reference — the two MUST NOT become independent design contracts. Reconciling
the mapping is in scope for the implementing epic.

**5. Skill and hook are deferred tiers, opt-in only.**
- *Tier 2 (optional):* the impeccable **skill/commands** are wired as a tool/reference for
  the existing `ui-ux-design` and `fe-developer` seats — as a skill, **not** a new role.
- *Tier 3 (optional):* a post-edit hook that runs the detector after UI-file edits is
  **opt-in per profile only**; the repo's hook governance (unregistered/non-functional
  hooks are release-blockers — see ABS-149) applies unchanged.

## Guardrail

- No floating network fetch in a governed run (constraint 2).
- No new agent role (constraint 5 / #PATH_DECISION option 2).
- No second design-contract source of truth (constraint 4).
- The detector *adds* a deterministic floor; it does not let a gate pass on detector-green
  alone when DACs fail, nor collapse the designer→tester separation
  (`ui-ux-design` still authors DACs; `qas-design` still executes them).
- No blanket auto-enable: absent `config.design_system.enabled`, nothing runs.

## Consequences

- `qas-design` gains an objective, LLM-free evidence source; design gate results become
  reproducible across runs and reviewers.
- The long-declared `check()`/`design-system-check` seam finally has an implementation.
- The boilerplate takes on a pinned third-party dependency (Apache-2.0); upgrades to it
  become a tracked, deliberate step rather than an implicit floating pull.
- Frontend/UI profiles get a design-quality floor for free; neutral/backend profiles are
  unaffected.
- Tier-2/Tier-3 adoption remains a later, separately-decided step; this ADR does not
  mandate the skill or the hook.
