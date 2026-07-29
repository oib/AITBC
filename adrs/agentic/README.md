# Agentic ADRs

Boilerplate-level agentic development decisions. They apply across projects and usually need no
customization by an adopting company.

> **Overlay note.** This three-level ADR hierarchy (company / agentic / project) is part of the
> technology-neutral core layered on the [SAW](../../README.md) base. How it wires to SAW's
> System Architect and the proposed→accepted (human-merge) lifecycle is documented in
> [`../README.md`](../README.md). Some ADR bodies reference the original `.agentic/…` layout;
> read those paths as the design record — each concept's live home is in the
> [crosswalk](../../blueprint/CROSSWALK.md).

**Shipped `proposed`; accepted by you.** The boilerplate ships these in `proposed` status
because agents (and boilerplates) cannot accept ADRs — humans can. During bootstrap, review each
ADR and accept it by editing `status: accepted` and adding `accepted_by: <you>`. Until accepted,
governance defaults apply.

**Acceptance closeout (ABS-212).** Accepting an ADR must flip its **file frontmatter**
(`status` → `accepted`, plus `accepted_by`/`accepted_date`) and this index row (`— **Accepted**`)
in the **same acceptance PR** — not as a loose follow-up. `scripts/adr-acceptance-drift.sh`
(a warning in `scripts/pre-release-check.sh`) flags ADRs accepted in the record but still
`proposed` in file. Full SOP: [`docs/sop/ADR_AUTHORING_GUIDE.md`](../../docs/sop/ADR_AUTHORING_GUIDE.md).

**Owned upstream, accepted locally.** ADR *content* is boilerplate-owned and updated through
upgrades (updates arrive as proposals in the upgrade PR); your acceptance frontmatter is
project-owned. See [`.harness-manifest.yml`](../../.harness-manifest.yml) (`protected` / `replaced`).

| ADR | Decision |
|-----|----------|
| [ADR-A-0001](ADR-A-0001-three-level-adr-hierarchy.md) | Three-level ADR hierarchy, fixed authority order |
| [ADR-A-0002](ADR-A-0002-fresh-subagent-execution.md) | Every task runs in a fresh task-scoped subagent |
| [ADR-A-0003](ADR-A-0003-context-minimization.md) | Context minimization as a quality requirement |
| [ADR-A-0004](ADR-A-0004-human-approval-boundaries.md) | Humans own irreversibility |
| [ADR-A-0005](ADR-A-0005-mandatory-prs.md) | All work reaches main through PRs |
| [ADR-A-0006](ADR-A-0006-active-task-tracking.md) | Active task tracking; canonical statuses |
| [ADR-A-0007](ADR-A-0007-adapter-model.md) | Neutral adapter interfaces; mock as conformance reference |
| [ADR-A-0008](ADR-A-0008-boilerplate-ownership-and-upgrades.md) | Ownership map + version-tracked upgrades (incl. Amendment 2026-07-12 / ABS-228: `scripts/` surface) — **Accepted** |
| [ADR-A-0009](ADR-A-0009-cost-approval-gate.md) | Human gate for cost-incurring options |
| [ADR-A-0010](ADR-A-0010-minimal-change-default.md) | Minimal-change discipline by default |
| [ADR-A-0011](ADR-A-0011-three-layer-application-architecture.md) | Three-layer application architecture (Data / Business / Frontend) by default |
| [ADR-A-0012](ADR-A-0012-agent-team-extension.md) | Agent team extension to 17 roles with skills-based ticket workflow |
| [ADR-A-0013](ADR-A-0013-self-hosting-stable-governs-dev.md) | Self-hosting — a pinned stable release governs dev; promotion is release |
| [ADR-A-0014](ADR-A-0014-workflow-v3-per-epic-merge-gate.md) | Workflow v3 — per-epic integration branch; gated auto-merge onto it; main stays human-merge-only (within ADR-A-0004/0005, unchanged) — **Accepted** |
| [ADR-A-0015](ADR-A-0015-provider-mirror-governance.md) | Provider-mirror governance — one decision per mirror; `agent_providers/claude_code/` generated-from-harness + byte-parity guard; `.codex/` 11-role subset intentional; skills canonical-claim corrected — **Accepted** |
| [ADR-A-0016](ADR-A-0016-claude-target-apply-path.md) | Apply path for .claude / harness agent-def deliverables under dontAsk — source at unprotected harness/claude, generate-governor maps to mirror + live .claude; Options 1 (bypassPermissions) and 3 (operator-apply SOP) rejected — **Proposed** |
| [ADR-A-0017](ADR-A-0017-design-quality-detector-backing.md) | Design-quality detector (impeccable) as backing for the `design-system-check` gate — vendored+pinned, profile-gated, no new role; skill/hook deferred tiers — **Accepted** (renumbered from A-0016, collision with the apply-path ADR) |
| [ADR-A-0018](ADR-A-0018-cross-visit-blocker-classification.md) | Cross-visit blocker classification + loop-breaker — blocker-class taxonomy (environment-denial / transient / logic), per-ticket `work/.orchestrator/blocker-<ticket>` memory, 2nd-same-class-visit auto-park to Blocked, escalation-budget with forward-only reset, NOTIFY-once dedup — **Accepted** |
| [ADR-A-0019](ADR-A-0019-po-deprioritize-vs-misdump-signal.md) | Escalation-resume routing — an explicit declared-target marker (`verdict: deprioritize` / `target: Backlog`), not the transition path, distinguishes a legit PO-deprioritize from a mis-dump; no declared target → resume-to-origin (BLOCKED-FROM) or halt in Blocked; `last_po_park_epoch` guard unchanged — **Accepted** |
| [ADR-A-0020](ADR-A-0020-design-first-story-routing.md) | Design-first story routing — in-place architect-first role switch at `Ready for Development` in `resolve_implementer_role()` (Operator Option B, no new status); `design-first` label latch consumed by the architect handoff appending `design-first-done`; AC3 proposed/accepted guard as a suite test; kill-switch `ORCH_DESIGN_FIRST_ROUTING` — **Accepted** |
| [ADR-A-0021](ADR-A-0021-agentic-delivery-backend.md) | Agentic delivery backend — agent-first tracker platform replacing the Jira binding; neutral `tracker-ops` adapter surface retained; Phase 1 (local SQLite store) unblocks work without external deps |
| [ADR-A-0022](ADR-A-0022-agent-def-overlays.md) | Agent-def overlays — append-only project customization composed at the spawn seam; overlay blocks declared in `agent_providers/`; boilerplate-owned base untouched |
| [ADR-A-0023](ADR-A-0023-session-invalidation-inputs.md) | Session invalidation gates on session-baked inputs, not on the live permission surface — `config_generation` hash covers only spawn-time variables; live env changes are not a skip/resume trigger (renumbered from `0022` by ABS-283) |
| [ADR-A-0024](ADR-A-0024-handoff-commit-verification.md) | Handoff commit verification — the runner verifies every commit hash named in a handoff (`git cat-file -e` + `git for-each-ref --contains`) before it accepts the handoff; a mis-report bounces the ticket back to the seat |
| [ADR-A-0025](ADR-A-0025-per-epic-merge-token.md) | Per-epic merge token — runner-enforced merge serialization token held across a merge-bounce; prevents sibling-merge/rebase-bounce livelocks on the epic integration branch (renumbered from `0022` by ABS-283) |
| [ADR-A-0026](ADR-A-0026-first-class-orchestration-state.md) | First-class orchestration state — typed schema fields/records instead of comment-parsed control state; pathology catalogue P1–P13 (incl. waiting-for-external doctrine, status-machine totality check, marker-liveness reconcile); comment kinds demoted to migration format; v1 single-tenant, no RLS — **Accepted** |
| [ADR-A-0027](ADR-A-0027-dashboard-url-grammar.md) | Dashboard URL grammar v2 — view routes + drawer params (supersedes the ABS-420 hash contract) — **Accepted** (ratified 2026-07-20 via human merge of MR !142, ADR-A-0004); the body's status paragraph was reconciled to `accepted` in PILOT-52/ABS-561, resolving the prior self-contradiction |
| [ADR-A-0028](ADR-A-0028-rule-ledger-executable-enforcement.md) | Rule ledger — every normative instruction-surface rule has a sensor or a declared risk; a new RULES file without ledger lines fails CI — **Accepted** |
| [ADR-A-0029](ADR-A-0029-multi-instance-event-bus.md) | Multi-instance event bus — Postgres LISTEN/NOTIFY backing (amends ADR-A-0021 §e): NOTIFY is a `projectId:seq:kind` pointer inside the event-insert transaction, one global channel filtered in-process, dedicated LISTEN connection with backoff reconnect + seq gap-replay, `EVENT_WAIT_CAP_SECONDS`=55 wait-Cap source — **proposed** (renumbered from `0028` on 2026-07-25: collided with the rule-ledger ADR that reached `origin/main` first) |
| [ADR-A-0030](ADR-A-0030-remote-doctrine.md) | Remote doctrine — the active-remote pin (`ORCH_MAIN_REMOTE`) is the single source of every push/MR/merge/probe target; hardcoded remote names (incl. `origin` fallbacks) forbidden; the Bitbucket release mirror is receive-only (`main`+tag at release time) and never gates the release; failover is an Operator config flip. Disambiguates the triple-overloaded term "mirror" (release-mirror here vs. ADR-A-0015 provider-config-mirror vs. ADR-A-0021 backend PR-mirror). Sensors: `active-remote-guard.sh`, `release-mirror-push.sh` — **proposed** |

Authority order: **accepted project > accepted company > accepted agentic > governance defaults**
([ADR-A-0001](ADR-A-0001-three-level-adr-hierarchy.md)).
