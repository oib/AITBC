# Architecture Review — ABS-138 (Boilerplate audit remediation)

- **Seat**: system-architect, v3 epic pipeline `Architecture Review`
- **Date**: 2026-07-08
- **Inputs**: epic ABS-138 body; PO Triage + BSA Grooming handoffs; QAS Ticket Review
  (Iteration 2, READY); 7 enriched child bodies in `docs/agent-outputs/enrichment-staging/`.
- **Environment**: Bash denied in this seat (live-run tracker `jira-tracker.sh` is
  network-gated/out-of-allowlist, matching prior seats). Per ABS-132 the runner applies the
  epic transition from the declarative `to:` field; this file + the handoff are the
  decision-bearing record. No tracker write was faked.

## Verification performed (graph-before-grep, named files only)

- All referenced patterns/ADRs/knowledge/scripts exist: `patterns_library/ci/{github-actions-workflow,deployment-pipeline}.md`,
  `patterns_library/security/*`, `adrs/agentic/ADR-A-{0001,0003,0004,0005,0010}`,
  `knowledge/{harness-sync-and-manifest,agent-roster-and-gates,orchestrator-hardening-abs-111}.md`,
  `docs/sop/ADR_AUTHORING_GUIDE.md`, `dark-factory/docs/MERGE-QUEUE-POLICY.md`.
- Finding #8 contradiction confirmed firsthand: `MERGE-QUEUE-POLICY.md:27,39` mandates
  `gh pr merge --auto --squash` as the only path with "no manual merge"; contradicts
  `ADR-A-0005` ("merge button is the human gate") and `ADR-A-0004` ("git adapter exposes no
  merge operation for protected branches" — structurally human-only).

## #PATH_DECISION — Finding #8 merge policy (SA authority; ADR Authoring Request outcome)

**Decision (scoped for the Finding #8 child to author):** the dark-factory merge-queue policy
aligns **to** ADR-A-0004/0005 — not the reverse.

- **Authority basis (ADR-A-0001)**: authority order is `project > company > agentic ADR >
  governance defaults`. `MERGE-QUEUE-POLICY.md` is a policy doc, **not** an ADR; it cannot
  override accepted-authority ADRs. Overriding an ADR requires a human-accepted superseding ADR
  that names the overridden ADR — none exists. Therefore the doc is the thing that is wrong.
- **What changes**: remove the `--auto` auto-merge that bypasses the human merge gate. The
  **human remains the merge trigger** (ADR-A-0004/0005), rebase-first per CONTRIBUTING.
- **What may stay**: squash *as a merge method* does not conflict with the human-gate principle
  and may be retained as an option; the concurrency concern (serialized merges) is legitimate
  but must not delete the human gate.
- **Decisive secondary signal**: repo is Bitbucket-hosted (Finding #1) → GitHub merge queue is
  non-functional here regardless.
- **Alternatives considered**:
  1. *Align ADRs to dark-factory (allow auto-merge)* — REJECTED: would delete the human
     irreversibility boundary (ADR-A-0004); requires human-accepted supersession at company
     level, which is not in scope and not requested.
  2. *Leave both, document the tension* — REJECTED: an active policy contradicting an ADR is a
     live governance hazard; the audit flagged it precisely to be resolved.
- **Not a stop-the-line override**: we align doc→ADR (no ADR is being overridden), so no human
  override-escalation is needed for the *direction*. ADR **acceptance** remains the human gate.
- **ADR Authoring Request status**: FULFILLED in-place. The SA review+scoping the child
  depended on is this decision. No separate ADR ticket is required — the Finding #8 child
  (role: system-architect) is the authoring vehicle; it authors a `proposed` ADR under
  `adrs/agentic/` per `docs/sop/ADR_AUTHORING_GUIDE.md`, aligns `MERGE-QUEUE-POLICY.md` +
  `CONTRIBUTING.md`. **Completion is human-gated** (ADR-A-0004): the child CANNOT reach Done
  until a human sets the ADR `accepted`. Do not self-accept.

## Epic-level pattern selection (per child — reuse first; no re-discovery)

| Finding | Child (title-match) | Patterns / sources to reuse | Model | Flags | Release |
|---|---|---|---|---|---|
| #7 dead files | dead files / patterns / templates / scripts | none applicable; `CONTRIBUTING.md` PR workflow; `ADR-A-0010` minimal-change | sonnet | — | **Design** (1st) |
| #5 stale counts | stale counts / roster / team-config | `knowledge/agent-roster-and-gates.md`; SoT = `.claude/agents/` | sonnet | — | **Design** |
| #1 dead CI | CI / Bitbucket / pipelines | `patterns_library/ci/{github-actions-workflow,deployment-pipeline}.md` — for **check intent only** (Bitbucket YAML syntax is new; patterns are not literal reuse) | sonnet | — | **Design** |
| #2 mirror drift | mirror / generator / claude_code / codex | **extend existing `scripts/sync-claude-harness.sh`** (do NOT write a new sync engine); `knowledge/harness-sync-and-manifest.md`; drift-check step reuses `patterns_library/ci/deployment-pipeline.md` | opus | — | **Design** (see split note) |
| #6 graphify | graphify / graph / rebuild | `knowledge/orchestrator-hardening-abs-111.md`; cmd `graphify update .` | sonnet | — | **Design** |
| #3 RLS hook | RLS / hook / pre-bash / stdin | `patterns_library/security/*`; **copy stdin-JSON parsing from an already-registered hook in `.claude/settings.template.json`**; `.claude/hooks-config.json` protocol | sonnet | **security** | **Design** (security lane) |
| #8 merge policy | merge policy / dark-factory / ADR | Guided ADR (`confluence-docs` skill template) + `docs/sop/ADR_AUTHORING_GUIDE.md` + `ADR-A-0001` hierarchy; implement the #PATH_DECISION above | opus | ADR / human-accept gate | **Design** (author `proposed` ADR; human-gated at Done) |
| #4 version identity | — | VERIFIED REMEDIATED (`.boilerplate-version`=2.21.2 via ABS-139/140/148) | — | — | **NOT released** |

**Cross-cutting (all children)**: `ADR-A-0010` minimal-change default (no drive-by refactors —
over-engineering is a defect); `safe-workflow` skill for branch/commit/PR; full gates, no
skip-review/skip-test on any child.

**No new pattern-library entry mandated** (Ponytail): existing `sync-claude-harness.sh` +
`harness-sync-and-manifest.md` cover the mirror model. If the Finding #2 implementer produces a
clean canonical generator, extract it into `patterns_library/` afterward — do not pre-build it.

## Ordering / dependency constraints

- **#1 before #2**: Finding #2 AC-4 (CI drift-check) requires the CI from Finding #1 to exist.
- **#2 single-spawn feasibility (QAS carry-forward)**: bounded and single-spawn feasible as one
  cohesive deliverable (generator + regen + README). **If** generator + all-mirror regen + CI
  drift-check cannot land in one pass, split into (a) generator+regen and (b) CI drift-check —
  (b) depends on #1 anyway. Flag for the implementer; not a blocker to release.
- WSJF release order (from PO/BSA, unchanged): #7 → #5 → #1 → #2 → #6; #3 parallel (security
  lane); #8 authored in parallel, held at Done on the human ADR-acceptance gate.

## Preconditions the runner MUST satisfy at release (unverified from this seat)

1. **Apply staged bodies to Jira children** (QAS carry-forward #3): the 7 bodies in
   `docs/agent-outputs/enrichment-staging/` must be applied to ABS-141–147/149 before the
   stories are worked. Unverifiable here (Bash denied). Runner confirms/applies.
2. **Resolve finding→ID mapping** via `$TRACKER_CMD get <id>` + title match (per enrichment
   mapping table); apply labels/flags per the table above.

## Release actions (for the runner's allowlisted context)

```bash
# Record this decision on the epic
"$TRACKER_CMD" comment ABS-138 --kind decision --actor system-architect \
  --body-file docs/agent-outputs/architecture-reviews/ABS-138-architecture-review.md

# Release each child into Design with patterns/flags per the table (runner resolves IDs).
# Example shape per child:
#   "$TRACKER_CMD" transition <child-id> "Design" --actor system-architect \
#     --reason "Released from ABS-138: patterns=<...>; model=<...>; flags=<...>"
# #3 adds flag:security; #8 carries the #PATH_DECISION + human ADR-accept gate note.
# #4 not released (done via ABS-139/140/148).

# Release the epic to the fan-in resting state
"$TRACKER_CMD" transition ABS-138 "Stories In Flight" --actor system-architect \
  --reason "Architecture Review: patterns selected per child, #PATH_DECISION recorded for Finding #8 (align dark-factory→ADR-A-0004/0005) — releasing 7 stories to Design; #4 already done."
```

JOIN (ABS-73) fires later when all children reach Done → epic `Stories In Flight → Epic
Integration`. Not evaluated here.
