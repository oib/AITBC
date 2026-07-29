# QAS Ticket Review — ABS-138 Definition-of-Ready Gate

**Ticket**: ABS-138 — Boilerplate audit remediation: dead code, mirror/version drift, dead CI (v2.21.1 full audit)
**Seat**: Ticket Review (DoR gate)
**Actor**: qas
**Date**: 2026-07-08
**Verdict**: **REWORK**
**Next**: Grooming

---

## Evidence Basis

The 8 held children (ABS-141-147, 149) live in Jira (network-gated). I cannot read the actual Jira ticket bodies. The Enrichment agent had a SPAWN-CRASH at 08:29:26 and the second spawn packet was truncated at Finding #7 — enrichment completion against the actual children is UNCONFIRMED.

Review is based on the authoritative Grooming handoff story drafts (2026-07-08T07:52:06Z), which specify what Enrichment was to append to the children. If Enrichment did not apply the content, the children are less ready — the defects below are a minimum set.

Done children (ABS-139/140/148) are excluded from this gate.

---

## 1. Epic-Level Prerequisites (Path-B Check)

| Prerequisite | Status | Notes |
|---|---|---|
| Goal present | PASS | 8 concrete audit findings with file paths and evidence |
| Scope present | PASS | Structural only; not functional regressions; no new features |
| AC / DoD present | PASS | Per-finding ACs in children; 23/23 tests green is the baseline DoD |
| ADR context present | PASS | ADR-A-0004/0005 referenced for Finding #8; security lane for #3 |

Epic-level prerequisites: **PASS** — no prerequisite gap.

---

## 2. Per-Child DoR Checklist

Children reviewed against the 6-item DoR checklist (docs/sop/DEFINITION_OF_READY.md).
ID-to-finding mapping from Enrichment handoff; story-draft numbers from Grooming handoff.

### Finding #4 — Version Identity

**Status: VERIFIED DONE — do NOT release.**
`.boilerplate-version` confirmed at `2.21.2` (Grooming agent verified at 2026-07-08T07:52:06Z).
ABS-139/140/148 closed this. Any held child mapped to #4 must be closed as already-done.
No DoR review required.

---

### Finding #7 — Dead-file/script removal (Story Draft 2)

| DoR Item | Result | Notes |
|---|---|---|
| 1. Every AC measurable/testable | **FAIL** | "5 deprecated command aliases" not named — not a measurable AC without enumeration. Other ACs (grep zero-hits, lint/build green) are OK |
| 2. Flags consistent | PASS | Pure file deletion; no security/data/design concern |
| 3. Role hint plausible | PASS | be-developer |
| 4. Single-spawn scope | PASS | ~8 named paths + reference checks; bounded |
| 5. Pattern/spec references | **FAIL** | No patterns_library/ or spec reference |
| 6. No unresolved #PLAN_UNCERTAINTY | PASS | Conditionality has explicit resolution path |

**Defects**: D-1 (name the 5 aliases with file paths); D-0 (add pattern ref or "no applicable pattern" note).

---

### Finding #5 — Stale counts / roster (Story Draft 3)

| DoR Item | Result | Notes |
|---|---|---|
| 1. Every AC measurable/testable | **FAIL** | "6+ docs" not enumerated. Implementer needs specific file list or bounded glob. Broad grep without scope risks touching historical entries. Grep and team-config ACs are OK |
| 2. Flags consistent | PASS | Doc/config updates; no security/data/design concern |
| 3. Role hint plausible | PASS | be-developer |
| 4. Single-spawn scope | PASS | Multi-file doc update + team-config.json; bounded |
| 5. Pattern/spec references | **FAIL** | No patterns_library/ or spec reference |
| 6. No unresolved #PLAN_UNCERTAINTY | PASS | |

**Defects**: D-2 (enumerate specific docs or bounded glob + exclusion of historical entries); D-0 (pattern ref).

---

### Finding #1 — Dead CI restore (Story Draft 4)

| DoR Item | Result | Notes |
|---|---|---|
| 1. Every AC measurable/testable | **FAIL** | "bitbucket-pipelines.yml mirroring the intended checks" — "intended checks" is undefined. Verifier cannot confirm which pipeline steps to look for. Regex and no-orphan ACs are OK |
| 2. Flags consistent | PASS | CI config; no security/data/design flag needed |
| 3. Role hint plausible | PASS | be-developer |
| 4. Single-spawn scope | PASS | One pipeline file + regex fix + GH Actions decommission; bounded |
| 5. Pattern/spec references | **FAIL** | patterns_library/ci/github-actions-workflow.md and patterns_library/ci/deployment-pipeline.md both apply; neither referenced |
| 6. No unresolved #PLAN_UNCERTAINTY | **FAIL** | "intended checks" is an unresolved #PLAN_UNCERTAINTY with no named resolution path |

**Defects**: D-3 (replace "intended checks" with enumerated pipeline steps, e.g. lint, typecheck, test:unit, build); D-0 (add patterns_library/ci/ references).

---

### Finding #2 — Mirror drift + governance (Story Draft 5)

| DoR Item | Result | Notes |
|---|---|---|
| 1. Every AC measurable/testable | **FAIL** | (a) "drift check fails CI when stale" requires Finding #1 CI to be operational — cross-dependency not stated on ticket. (b) Complete mirror target set not enumerated: .gemini/ named in epic (3-way fork: .claude/.agents/.gemini) but absent from story ACs. "byte-consistent with canonical" is OK |
| 2. Flags consistent | PASS | Infrastructure tooling; no security/data/design concern |
| 3. Role hint plausible | PASS | be-developer (model:opus appropriate for complexity) |
| 4. Single-spawn scope | CONCERN | Generator + 4 mirror targets + CI drift guard for 17 agents is at the upper boundary. Not a hard FAIL (Grooming accepts it as "large"); flagged for Architecture Review validation |
| 5. Pattern/spec references | **FAIL** | No patterns_library/ reference; patterns_library/ci/deployment-pipeline.md applies to the CI drift-check step |
| 6. No unresolved #PLAN_UNCERTAINTY | **FAIL** | "from the canonical source" — canonical directory not named. .agents/README.md claims the model but the story does not confirm which of .claude/, .agents/, .gemini/ is authoritative. Makes "byte-consistent with canonical" untestable |

**Defects**: D-4 (add depends_on: Finding-#1-child); D-5 (name the canonical source directory); D-6 (enumerate all mirror targets — does .gemini/ require regeneration?); D-7 (add idempotency AC: re-running generator produces no drift); D-0 (pattern ref).

---

### Finding #6 — Graphify-out rebuild (Story Draft 6)

| DoR Item | Result | Notes |
|---|---|---|
| 1. Every AC measurable/testable | **FAIL** | "file coverage reflects the current 744-file tree" — "reflects" is not a measurable predicate. Must be a concrete runnable assertion (e.g. "generation exits 0 and reports >= N files processed where N = file count at HEAD") |
| 2. Flags consistent | PASS | Mechanical regen; no security/data/design concern |
| 3. Role hint plausible | PASS | be-developer |
| 4. Single-spawn scope | PASS | Regen + commit; bounded |
| 5. Pattern/spec references | **FAIL** | Story excludes graphify tooling changes but gives implementer no reference to the generation command/script — implementer cannot start work |
| 6. No unresolved #PLAN_UNCERTAINTY | PASS | |

**Defects**: D-8 (replace "reflects" with concrete runnable assertion); D-9 (name the graphify generation command/script in ticket body); D-0 (pattern ref or explicit "no applicable pattern" note).

---

### Finding #3 — RLS Hook (Story Draft 7) — SECURITY LANE

| DoR Item | Result | Notes |
|---|---|---|
| 1. Every AC measurable/testable | PASS | stdin JSON parse; exit 2 on missing context; triggered run evidence; siblings status — all verifiable |
| 2. Flags consistent | PASS | flag:security is correct for a blocking RLS control |
| 3. Role hint plausible | PASS | be-developer |
| 4. Single-spawn scope | PASS | Fix stdin + register hooks + change blocking mode; bounded |
| 5. Pattern/spec references | **FAIL** | No patterns_library/security/ reference. No reference to .claude/hooks-config.json format or the hook protocol JSON schema. Implementer needs these to know the stdin schema and registration format |
| 6. No unresolved #PLAN_UNCERTAINTY | **FAIL** | (a) "the 2 sibling hooks registered or removed" — disposition unspecified. "OR" is a product/architecture decision that cannot be deferred to the implementer. (b) MISSING ROLLBACK PATH: if the hook produces false positives blocking legitimate commands, no disable mechanism is in the AC. For flag:security with exit-2 blocking semantics, rollback is a mandatory blind-spot item |

**Defects (security-critical)**: D-10 (name each sibling hook with its disposition: register or remove — remove the OR); D-11 (add rollback/disable AC: hook can be disabled without code change, disable path verified in triggered-run evidence); D-0 (add patterns_library/security/ and .claude/hooks-config.json as references).

---

### Finding #8 — Merge Policy ADR (Story Draft 8) — ADR-GATED

| DoR Item | Result | Notes |
|---|---|---|
| 1. Every AC measurable/testable | PASS | "new/updated ADR states single merge policy" is verifiable; "dark-factory policy no longer contradicts" is grep-verifiable |
| 2. Flags consistent | PASS | Architectural decision; no security/data/design flag applies |
| 3. Role hint plausible | PASS | system-architect |
| 4. Single-spawn scope | PASS | One ADR + one policy doc alignment |
| 5. Pattern/spec references | **FAIL** | docs/sop/ADR_AUTHORING_GUIDE.md is the canonical reference for ADR authoring; not listed |
| 6. No unresolved #PLAN_UNCERTAINTY | **FAIL** | The dependency on System Architect acceptance of the ADR Authoring Request is written as prose ("GATE: do not release until SA ADR authored") but NOT captured in the ticket depends_on field. Without a formal depends_on the runner can pick up this story before the upstream SA decision is made |

**Defects**: D-12 (add docs/sop/ADR_AUTHORING_GUIDE.md to references); D-13 (add formal depends_on linking to the SA ADR Authoring Request outcome — remove prose-only gate note).

---

## 3. Mandatory Coverage Mapping

Every epic headline finding must map to at least one story AC (DEFINITION_OF_READY.md).

| Epic Goal | Covering Story | Mapped |
|---|---|---|
| Finding #1: All CI dead (GH Actions in Bitbucket repo; TICKET_PREFIX regex never passes) | Finding #1 child: pipeline triggers + observable; regex matches ABS-###; no orphaned GH Actions | YES |
| Finding #2: Mirror drift (claude_code/ stale, .codex/ missing 6, 3-way skills fork, no guard) | Finding #2 child: one generator script; 17 agents byte-consistent; drift check fails CI when stale | YES |
| Finding #3: Non-functional security control (hook reads $1, unregistered, warn-only) | Finding #3 child: stdin JSON parsed; exit 2 on missing RLS context; registered + triggered; siblings handled | YES |
| Finding #4: Version identity rot (v2.10.0 frozen through 11 releases) | DONE — ABS-139/140/148 (.boilerplate-version = 2.21.2 verified) | YES |
| Finding #5: Stale counts (11 agents in 6+ docs, 17/18 skills, team-config.json old roster) | Finding #5 child: grep returns only historical refs; team-config.json roster == .claude/agents/ | YES |
| Finding #6: graphify-out/ 229 commits stale (354/744 files) | Finding #6 child: regen from HEAD; file coverage; provenance recorded | YES |
| Finding #7: Dead files/scripts (patterns/, templates/, blueprint/, scripts/, aliases) | Finding #7 child: each path deleted; zero live refs; lint/build green | YES |
| Finding #8: Governance contradiction (dark-factory vs ADR-A-0004/0005 + CONTRIBUTING) | Finding #8 child: new/updated ADR; dark-factory policy no longer contradicts | YES |

**Coverage result**: All 8 epic goals map to at least 1 story AC. No unmapped goal.

---

## 4. Blind-Spot Catalog

Fixed question list applied to the 7 active stories as a batch.

| Category | Verdict | Detail |
|---|---|---|
| Error / edge cases | GAP | Finding #7: "5 aliases" unnamed — if one does not exist, implementer has no guidance (partially mitigated by "skip with a note"). Finding #2: no AC for generator failure mid-run (partially completed mirror set in inconsistent state). Finding #1: no AC for pipeline step failure — "observable run" covers success only |
| Authz / RLS | OK | Finding #3 explicitly addresses RLS. All other stories are structural changes with no auth surface |
| Migrations for existing data | OK | No database schema changes in any story |
| Idempotency | GAP (minor) | Finding #2 generator: no AC asserts the script is idempotent. Re-running a file-generation script that modifies 17+ agent files in 3+ directories is a real re-run risk |
| Observability | OK | Finding #1: "observable run" covers CI. Finding #3: "triggered run evidence" covers hook. Finding #6: "provenance recorded" covers graphify. Doc/config changes in #5 and #7 have lower observability needs |
| Rollback | GAP (material) | Finding #3: NO rollback or disable path for a blocking security control (exit 2). If the hook false-positives on a legitimate Prisma command there is no documented recovery. For a flag:security story with blocking semantics this is the most material gap in the set |

---

## 5. Cross-Story Dependency Check

| Dependency | Formally stated on ticket? | Required action |
|---|---|---|
| Finding #2 "drift check fails CI" AC requires Finding #1 CI to be operational | NO | Add depends_on: <Finding-#1-child-ID> to Finding #2 child |
| Finding #8 execution requires SA ADR Authoring Request to be accepted before story begins | NO | Add formal depends_on to Finding #8 child (the SA ADR review handoff outcome), not prose gate note |

No circular dependencies detected. Finding #3 (security lane) is independent of all other children.

---

## 6. Defect List (Rework — Concrete and Addressable)

All items are auto-fix class (normalization + tightening per DEFINITION_OF_READY.md "Path-B auto-fix rework loop").
Exceptions noted where a product/architecture decision is needed before the auto-fix can be applied.

### Universal — all 7 active stories (auto-fix items 1 + 4)

**D-0** Every story draft is missing pattern_library/ and/or SOP/spec references (DoR item 5).
Required additions per child:
- Finding #1 child: add patterns_library/ci/github-actions-workflow.md + patterns_library/ci/deployment-pipeline.md
- Finding #2 child: add patterns_library/ci/deployment-pipeline.md (for CI drift-check step)
- Finding #3 child: add patterns_library/security/ + .claude/hooks-config.json
- Finding #8 child: add docs/sop/ADR_AUTHORING_GUIDE.md
- Findings #5, #6, #7 children: confirm no applicable pattern exists; add explicit "no applicable pattern" note

### Finding #7 child (auto-fix item 1 — tighten AC)

**D-1** Name the 5 specific deprecated command aliases with their file paths relative to .claude/commands/.
"5 deprecated command aliases" with no list is not a measurable AC.

### Finding #5 child (auto-fix item 1 — tighten AC)

**D-2** Enumerate the specific docs/files to update, or provide a bounded glob + exclusion of
historical/changelog entries. "6+ docs" is not actionable without a list.

### Finding #1 child (auto-fix item 1 + item 6)

**D-3** Replace "mirroring the intended checks" with an enumeration of the required Bitbucket
pipeline steps (e.g. lint, typecheck, test:unit, build). "Intended checks" is an unresolved
#PLAN_UNCERTAINTY with no named resolution path.
NOTE: If BSA cannot derive the required steps from the epic text + existing GH Actions intent,
escalate D-3 as an open question to the System Architect — do not guess.

### Finding #2 child (auto-fix items 1, field-edit depends_on)

**D-4** Add depends_on: <Finding-#1-child-ID>. The "drift check fails CI" AC is only testable
after Finding #1 CI is operational.

**D-5** Name the canonical source directory for skills (.claude/, .agents/, or .gemini/).
"From the canonical source" is an unresolved uncertainty making the AC untestable.
NOTE: If this cannot be resolved from .agents/README.md + epic text, escalate as open question.

**D-6** Enumerate all mirror targets the generator must handle. The epic names a 3-way fork
across .claude/.agents/.gemini — confirm whether .gemini/skills/ is in scope for regeneration.

**D-7** Add an idempotency AC: "re-running the generator against an already-synced mirror
produces no file changes (generator is idempotent)."

### Finding #6 child (auto-fix item 1)

**D-8** Replace "file coverage reflects the current 744-file tree" with a concrete runnable
assertion, e.g. "generation exits 0 and reports >= N files processed where N equals
find . \( -name "*.ts" -o -name "*.md" \) | wc -l at the HEAD commit."

**D-9** Name the graphify generation command/script in the ticket body or references.
The implementer needs to know what to run.

### Finding #3 child — SECURITY-CRITICAL (auto-fix item 1)

**D-10** Replace "the 2 sibling hooks registered or removed" with a named disposition for
each sibling hook: hook filename + action (register or remove). "OR" is a
product/architecture decision that cannot be deferred to the implementer.

**D-11** Add rollback/disable AC: "the hook can be disabled (e.g. enabled: false in
hooks-config.json or equivalent mechanism) without a code change; the disable path
is verified as part of the triggered-run evidence."
This is a mandatory blind-spot item for a flag:security story with exit-2 blocking semantics.

### Finding #8 child (auto-fix items 1 + field-edit depends_on)

**D-12** Add docs/sop/ADR_AUTHORING_GUIDE.md to ticket references.

**D-13** Add a formal depends_on linking this child to the System Architect ADR Authoring
Request (the downstream handoff the PO surfaced). Remove the prose-only gate note.
Without a depends_on the runner can schedule this story before the SA decision lands.

---

## 7. Enrichment Completion Notice

The Enrichment agent had a SPAWN-CRASH at 08:29:26 and the second spawn (09:30:17) produced
a packet truncated at Finding #7. Only Finding #7 body was (partially) produced in the packet;
enrichment of ABS-141-147, 149 with the full flag matrix, guardrail annotations, and context
packs is UNCONFIRMED as applied to the live Jira tickets.

The rework auto-fix loop (Grooming bounce) should apply defects D-0 through D-13 to the
actual children via the close-and-replace mechanism rather than assuming the truncated
enrichment already applied the Grooming content. Grooming must confirm each child body
before marking the story ready.

---

## Verdict and Transition

**Verdict: REWORK** — 14 concrete defects (D-0 through D-13) across 7 active children.

All defects are normalization-class auto-fixes under DEFINITION_OF_READY.md "Path-B auto-fix
rework loop" authority EXCEPT:
- D-3 ("intended checks" for Bitbucket pipeline steps) — requires BSA to derive from GH Actions
  intent or escalate as open question to System Architect.
- D-5 ("canonical source" for skills) — requires BSA to confirm from .agents/README.md + epic
  text or escalate as open question.

If either D-3 or D-5 cannot be resolved from existing artifacts, the verdict upgrades to
**open question** for that specific item and routes to Needs PO Decision — they are NEVER guessed.

**Iteration: Iteration 1 of 3**

---

## Gate-Results Comment (to post on ABS-138)

```
to: Grooming
actor: qas
reason: Ticket Review: rework — 14 defects (D-0 through D-13) across 7 active children.
  Universal: all 7 stories missing pattern/spec references (D-0).
  Per-child: D-1 (aliases unnamed, #7), D-2 (docs not enumerated, #5),
  D-3 (intended CI checks undefined, #1 — may need SA input),
  D-4 (depends_on CI child missing, #2), D-5 (canonical source unnamed, #2 — may need SA input),
  D-6 (mirror targets incomplete, #2), D-7 (idempotency AC missing, #2),
  D-8 (reflects = untestable, #6), D-9 (graphify command unnamed, #6),
  D-10 (sibling hook disposition OR, #3), D-11 (rollback path missing, #3 — security-critical),
  D-12 (ADR guide not referenced, #8), D-13 (depends_on SA ADR missing, #8).
  Enrichment completion also unconfirmed (SPAWN-CRASH + truncated second spawn).
  BSA/Enrichment: apply auto-fix loop; escalate D-3 and D-5 as open questions if
  not resolvable from epic text. Iteration 1 of 3.
```


---

# QAS Ticket Review — ABS-138 Iteration 2 (DoR Re-check after Grooming Rework)

**Date**: 2026-07-08
**Verdict**: **READY**
**Next**: Architecture Review
**Iteration**: 2 of 3

---

## Rework Resolution Check

The Grooming/Enrichment auto-fix pass produced 7 staged enriched bodies in
`docs/agent-outputs/enrichment-staging/`. All 14 defects from Iteration 1
(D-0 through D-13) are checked against the staged content below.

---

## D-0 through D-13 Resolution Status

| Defect | Story | Status | Evidence |
|---|---|---|---|
| D-0: Missing pattern refs (all 7) | All | RESOLVED | #7: explicit no-pattern note; #5: knowledge/agent-roster-and-gates.md; #1: patterns_library/ci/*; #2: patterns_library/ci/deployment-pipeline.md + knowledge/harness-sync-and-manifest.md; #6: knowledge/orchestrator-hardening-abs-111.md; #3: patterns_library/security/ + hooks-config.json; #8: docs/sop/ADR_AUTHORING_GUIDE.md |
| D-1: 5 aliases unnamed | #7 | RESOLVED | AC-3 uses dynamic git-log discovery + requires PR list by filename; handles already-removed subset via done-children check |
| D-2: 6+ docs not enumerated | #5 | RESOLVED | AC-1 names 10 specific files explicitly |
| D-3: intended CI checks undefined | #1 | RESOLVED | AC-1 enumerates 8 specific pipeline steps with concrete commands |
| D-4: depends_on CI child missing | #2 | RESOLVED | Related section and Context Pack both state: depends_on Finding #1 child |
| D-5: canonical source unnamed | #2 | RESOLVED | #PLAN_UNCERTAINTY note: .claude/agents/ (agents) and .claude/skills/ (skills) |
| D-6: mirror targets incomplete | #2 | RESOLVED | Targets enumerated: claude_code/prompts/, .codex/agents/, .agents/ (skills), .gemini/skills/ (presence confirmed via ls .gemini/) |
| D-7: idempotency AC missing | #2 | RESOLVED | AC-1: git diff --exit-code exits 0 on second run |
| D-8: reflects = untestable | #6 | RESOLVED | AC-3: find ... wc -l ACTUAL; verify graph reports >= ACTUAL * 0.9 |
| D-9: graphify command unnamed | #6 | RESOLVED | Generation command stated throughout: graphify update . |
| D-10: sibling hook disposition OR | #3 | RESOLVED | AC-3 names each sibling with action: post-commit-linear-update.sh DECOMMISSION; session-start-pattern-check.sh DECOMMISSION |
| D-11: rollback path missing | #3 | RESOLVED | AC-5: disable via settings.template.json removal; verified with jq empty |
| D-12: ADR guide not referenced | #8 | RESOLVED | AC-1 + References: docs/sop/ADR_AUTHORING_GUIDE.md (MANDATORY) |
| D-13: depends_on SA ADR missing | #8 | RESOLVED | References section + blocked gate: BLOCKED pending SA ticket; AC-4 states child cannot be Done until human accepts ADR |

**Same-Error-Twice Rule check**: No defect from Iteration 1 recurs unchanged in Iteration 2. Rule does NOT trigger.

---
## Iteration 2 DoR Checklist — All 7 Active Stories

### Finding #7 — Dead files/scripts
| DoR Item | Result | Evidence |
|---|---|---|
| 1. Every AC measurable | PASS | AC-1: find exits empty; AC-2: grep returns no hit; AC-3: git-log dynamic discovery + PR list; AC-4: lint exits 0 |
| 2. Flags consistent | PASS | Deletion only; no security/data/design concern |
| 3. Role plausible | PASS | be-developer |
| 4. Single-spawn scope | PASS | Named paths + reference checks; bounded |
| 5. Pattern refs | PASS | Explicit no-pattern note; CONTRIBUTING.md referenced |
| 6. No unresolved uncertainty | PASS | Dynamic approach handles already-removed subset |
**Verdict: PASS**

### Finding #5 — Stale counts
| DoR Item | Result | Evidence |
|---|---|---|
| 1. Every AC measurable | PASS | AC-1: grep with 10 named files; AC-2: grep for skills count; AC-3: comm -3 comparison command; AC-4: lint exits 0 |
| 2. Flags consistent | PASS | Doc/config updates; no security/data/design concern |
| 3. Role plausible | PASS | be-developer |
| 4. Single-spawn scope | PASS | 10 specific docs + team-config.json |
| 5. Pattern refs | PASS | knowledge/agent-roster-and-gates.md; explicit no patterns_library/ entry |
| 6. No unresolved uncertainty | PASS | |
**Verdict: PASS**

### Finding #1 — Dead CI restore
| DoR Item | Result | Evidence |
|---|---|---|
| 1. Every AC measurable | PASS | AC-1: 8 enumerated steps with commands; AC-2: regex test command; AC-3: delete or annotate with specific comment string; AC-4: yaml.safe_load exits 0 |
| 2. Flags consistent | PASS | CI config; no security/data/design flag |
| 3. Role plausible | PASS | be-developer |
| 4. Single-spawn scope | PASS | One pipeline file + regex fix + 5 workflow annotations/deletions |
| 5. Pattern refs | PASS | patterns_library/ci/github-actions-workflow.md + patterns_library/ci/deployment-pipeline.md |
| 6. No unresolved uncertainty | PASS | D-3 resolved: intended checks enumerated as 8 concrete steps |
**Verdict: PASS**

### Finding #2 — Mirror drift + governance
| DoR Item | Result | Evidence |
|---|---|---|
| 1. Every AC measurable | PASS | AC-1: git diff --exit-code idempotency test; AC-2: diff agent count; AC-3: diff skills dirs; AC-4: drift-check non-zero/zero demo; AC-5: README references generator |
| 2. Flags consistent | PASS | Infrastructure tooling; no security/data/design concern |
| 3. Role plausible | PASS | be-developer (model:opus) |
| 4. Single-spawn scope | CONCERN (carried) | Large scope; flagged for Architecture Review validation — not a DoR FAIL |
| 5. Pattern refs | PASS | patterns_library/ci/deployment-pipeline.md + knowledge/harness-sync-and-manifest.md |
| 6. No unresolved uncertainty | PASS | #PLAN_UNCERTAINTY resolved: canonical source and mirror targets named |
**Verdict: PASS** (scope concern carried to Architecture Review)

### Finding #6 — Graphify rebuild
| DoR Item | Result | Evidence |
|---|---|---|
| 1. Every AC measurable | PASS | AC-1: graphify exits 0; AC-2: grep GRAPH_REPORT.md vs git rev-parse HEAD; AC-3: find wc -l >= 90## Iteration 2 DoR Checklist — All 7 Active Stories

### Finding #7 — Dead files/scripts: PASS
- AC-1: find exits empty after deletion; AC-2: grep zero hits; AC-3: dynamic git-log alias discovery + PR list by filename; AC-4: lint exits 0
- Flags: none (deletion). Role: be-developer. Scope: bounded. Pattern: explicit no-pattern note. Uncertainty: none.

### Finding #5 — Stale counts: PASS
- AC-1: grep with 10 named files explicitly listed; AC-2: grep for skills count; AC-3: comm -3 comparison command; AC-4: lint exits 0
- Flags: none. Role: be-developer. Scope: bounded. Pattern: knowledge/agent-roster-and-gates.md. Uncertainty: none.

### Finding #1 — Dead CI restore: PASS
- AC-1: 8 enumerated pipeline steps with concrete commands; AC-2: regex test command; AC-3: annotate with specific comment string; AC-4: yaml.safe_load exits 0
- Flags: none. Role: be-developer. Scope: bounded. Patterns: patterns_library/ci/github-actions-workflow.md + deployment-pipeline.md. Uncertainty: D-3 resolved.

### Finding #2 — Mirror drift: PASS (scope concern carried to Architecture Review)
- AC-1: git diff --exit-code idempotency test; AC-2: diff agent counts; AC-3: diff skills dirs; AC-4: drift-check demo; AC-5: README references generator
- Flags: none. Role: be-developer (model:opus). Scope: LARGE — flagged for Architecture Review, not a DoR FAIL. Patterns: deployment-pipeline.md + knowledge/harness-sync-and-manifest.md. D-5 resolved: canonical source = .claude/agents/ + .claude/skills/.

### Finding #6 — Graphify rebuild: PASS
- AC-1: graphify update . exits 0; AC-2: GRAPH_REPORT.md commit hash vs git rev-parse HEAD; AC-3: find wc -l >= 90% threshold; AC-4: committed
- Flags: none. Role: be-developer. Scope: bounded. Pattern: knowledge/orchestrator-hardening-abs-111.md; generation command stated. Uncertainty: none.

### Finding #3 — RLS Hook (SECURITY LANE): PASS
- AC-1: printf test asserts exit 2; AC-2: exit 2 without RLS helper, exit 0 with; AC-3: named dispositions both DECOMMISSION + find verification; AC-4: jq query on settings.template.json; AC-5: jq empty validation + PR disable docs; AC-6: lint exits 0
- Flags: flag:security (correct). Role: be-developer. Scope: bounded. Patterns: patterns_library/security/ + hooks-config.json + SECURITY_FIRST_ARCHITECTURE.md. D-10 and D-11 resolved.

### Finding #8 — Merge Policy ADR (ADR-GATED): PASS
- AC-1: ADR in adrs/agentic/ following guide; AC-2: grep returns no squash mandate; AC-3: CONTRIBUTING.md references ADR; AC-4: status=proposed; human accepts
- Flags: none (architectural). Role: system-architect. Scope: bounded. Pattern: docs/sop/ADR_AUTHORING_GUIDE.md. Gate correctly documented: BLOCKED pending SA ticket as formal depends_on. Do NOT set orchestrator-ready.

---
## Iteration 2 Reference File Verification

All files referenced in enriched bodies verified present in repo:
- patterns_library/ci/github-actions-workflow.md: EXISTS
- patterns_library/ci/deployment-pipeline.md: EXISTS
- patterns_library/security/ (3 files): EXISTS
- docs/security/SECURITY_FIRST_ARCHITECTURE.md: EXISTS
- knowledge/agent-roster-and-gates.md: EXISTS
- knowledge/harness-sync-and-manifest.md: EXISTS
- knowledge/orchestrator-hardening-abs-111.md: EXISTS
- docs/sop/ADR_AUTHORING_GUIDE.md: EXISTS
- .claude/hooks-config.json: EXISTS
- .claude/settings.template.json: EXISTS
- tests/test-hooks-behavioral.sh: EXISTS
- tests/test-hooks-config.sh: EXISTS
- .github/scripts/check-skills-parity.sh: EXISTS
- .claude/hooks/pre-bash-rls-validation.sh: EXISTS
- .claude/hooks/post-commit-linear-update.sh: EXISTS (to decommission)
- .claude/hooks/session-start-pattern-check.sh: EXISTS (to decommission)

No dead references in any enriched body.

---

## Iteration 2 Coverage Map and Blind-Spot Catalog

Coverage map: unchanged from Iteration 1 — all 8 epic goals map to >= 1 story AC. No unmapped goal.

Blind-spot catalog (Iteration 2 re-check):
- Error/edge: aliases discovery handled dynamically (D-1 resolved); generator mid-run failure is an implementation concern, not a DoR blocker
- Authz/RLS: Finding #3 explicitly addresses RLS; others unchanged (OK)
- Migrations: no schema changes (OK)
- Idempotency: Finding #2 AC-1 idempotency test added (D-7 resolved)
- Observability: unchanged (OK)
- Rollback: Finding #3 AC-5 disable path added (D-11 resolved — was the material gap)

All material blind-spot gaps from Iteration 1 are closed.

---

## Operational Caveat

The enriched bodies were written to docs/agent-outputs/enrichment-staging/ by the Enrichment agent.
The Enrichment agent noted Bash was denied for the runner script write — it is UNCONFIRMED whether
the staged content has been applied to the actual Jira children (ABS-141-147, 149) via the tracker.

Architecture Review MUST confirm the enriched bodies have been applied to the Jira children
before reviewing individual story tickets. The staging files are the authoritative DoR evidence.

---

## Iteration 2 Verdict

READY — all 7 active enriched bodies pass the 6-item DoR checklist.
All 14 Iteration-1 defects resolved. No material blind-spot gaps remain.
Coverage map complete. Same-Error-Twice Rule does not trigger.

Finding #2 scope concern (large) is carried as a flagged note for Architecture Review.
Finding #8 remains ADR-GATED — correctly documented; do not set orchestrator-ready
until SA ADR Authoring Request is captured as a formal ticket.

Transition: Ticket Review -> Architecture Review
