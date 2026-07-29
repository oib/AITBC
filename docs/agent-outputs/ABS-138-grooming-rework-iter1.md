# ABS-138 — Grooming REWORK (Ticket Review DoR bounce, iteration 1/3)

> **Tooling constraint (declared, not worked around):** this Grooming re-spawn had
> `Read` disabled and `Bash` denied — only `Write` available. I could **not** read
> `docs/agent-outputs/qa-validations/ABS-138-qa-validation.md`, the child ticket bodies
> (ABS-141–147, 149), or run `$TRACKER_CMD`. This artifact fixes the DoR defects
> **inferable from my own v1 Grooming handoff**; anything the QA report flagged that is
> not covered here needs the report surfaced into the packet for a targeted second pass.
> I did not and will not fabricate QA findings I could not read.

## DoR defects addressed in this pass (inferred, systemic)

1. **Unresolved template tokens in acceptance criteria** (`{{LINT_COMMAND}}`,
   `AITBC`) — replaced with runnable/verifiable phrasing. Where a concrete
   command is known it is named (`yarn lint:md` for markdown); where the repo's code-lint
   entrypoint is a placeholder-by-design in this boilerplate, ACs reference "the repo's
   configured lint+build (package.json scripts) exit 0" — measurable by exit code, no
   invented command name.
2. **Missing `Environment Prerequisites` section** — added to every draft (all `none`;
   this is internal-tooling remediation — no secrets, env vars, or external accounts).
3. **Weakly-measurable ACs** — every AC is now a command, a diff, or an observable file
   state.
4. **Unbound ID→finding mapping** — see the readiness note; the DoR-ready set is
   explicitly enumerated and the ADR-gated / already-done children are excluded.

## Readiness set (what the DoR gate should evaluate as Ready)

- **DoR-ready (6):** Draft 2 (#7), Draft 3 (#5), Draft 4 (#1), Draft 5 (#2),
  Draft 6 (#6), Draft 7 (#3).
- **NOT ready — excluded from the ready set:**
  - Draft 8 (#8 merge policy) — **ADR-gated** (unresolved dependency → fails DoR by design;
    must not carry `orchestrator-ready` until the System Architect ADR lands).
  - Draft 1 (#4 version identity) — **already remediated** (`.boilerplate-version` = 2.21.2,
    verified); close as done, do not evaluate.

---

## Story Draft 2 — Finding #7: dead-file/script removal

- **Goal**: repo is free of the audit-named dead paths; each deletion preceded by a
  reference-check confirming no live caller.
- **Scope**: in — delete `blueprint/AUDIT-GAP-PLAN.md`, `scripts/generalize_commands.py`,
  `scripts/install-prompts.sh`, `scripts/apply-workflow.sh`, the 5 deprecated
  `.claude/commands/` aliases, and `patterns/`+`templates/` if still present; out —
  behavioural refactors, cleanup beyond the named paths.
- **Environment Prerequisites**: none.
- **Acceptance Criteria**:
  - [ ] For each named path, `find . -path '<path>' -not -path './.git/*'` returns empty
        after the change (or a note if ABS-139/140/148 already removed it).
  - [ ] For each deleted path, `grep -rn '<basename>' . --exclude-dir=.git` returns no hit
        from a live (non-deleted, non-doc-historical) file.
  - [ ] The 5 deprecated `.claude/commands/` aliases are enumerated in the PR description
        and removed.
  - [ ] `yarn lint:md` exits 0 and the repo's configured lint+build (package.json scripts)
        exit 0 after deletions.
- **Role hint**: be-developer. **Flags**: none. **model:sonnet**.
- **Review-scope**: full gates (deleting scripts — confirm truly dead). No skip-review/skip-test.
- **References**: ABS-138 Finding #7; ABS-139/140/148 (Done — confirm prior removals first).

## Story Draft 3 — Finding #5: stale counts / roster

- **Goal**: every agent-count, skill-count, and roster reference reflects reality
  (17 agents, 21 skills, current 17-role roster).
- **Scope**: in — correct "11 agents"→17 across docs + the 2 rule mirrors, "17/18 skills"→21,
  and `team-config.json` roster; out — adding/removing actual agents or skills.
- **Environment Prerequisites**: none.
- **Acceptance Criteria**:
  - [ ] `grep -rn '11 agents' . --exclude-dir=.git` returns only changelog/historical hits
        (no live doc asserting the wrong count).
  - [ ] `grep -rn '17/18 skills' . --exclude-dir=.git` returns no live hit.
  - [ ] The role set in `team-config.json` equals the file set under `.claude/agents/`
        (diff of the two name lists is empty).
- **Role hint**: be-developer. **Flags**: none. **model:sonnet** (bundled with functional
  `team-config.json`). **Review-scope**: full gates (functional config → no skip).
- **References**: ABS-138 Finding #5.

## Story Draft 4 — Finding #1: dead CI restore

- **Goal**: CI actually executes on the Bitbucket-hosted repo, and the never-matching
  ticket-key regex is fixed.
- **Scope**: in — add `bitbucket-pipelines.yml` running the same checks the GitHub Actions
  workflows intended (lint, type-check, build, test); fix the literal `AITBC`
  regex in `pr-validation.yml` to match real keys (e.g. `ABS-[0-9]+`); decommission or
  port the non-running GitHub Actions workflows. Out — new check types beyond current intent.
- **Environment Prerequisites**: none (uses existing repo scripts; no new CI secrets — if a
  Bitbucket pipeline runner variable is required, that is a follow-up, not this ticket).
- **Acceptance Criteria**:
  - [ ] `bitbucket-pipelines.yml` exists at repo root and defines a pipeline for pull
        requests.
  - [ ] The ticket-key regex in the pipeline matches `ABS-123`-style keys and rejects the
        empty/`AITBC` literal (a unit/self-test asserting a real key passes).
  - [ ] No GitHub Actions workflow remains in `.github/workflows/` that implies coverage it
        does not provide (deleted or clearly marked non-authoritative).
  - [ ] The pipeline steps invoke the repo's configured lint/type-check/build/test scripts
        (package.json), matching the intent of the removed workflows.
- **Role hint**: be-developer. **Flags**: none. **model:sonnet**.
- **Review-scope**: full gates (executable CI config → no skip).
- **References**: ABS-138 Finding #1.

## Story Draft 5 — Finding #2: mirror drift + governance

- **Goal**: the canonical-mirror model `.agents/README.md` claims is real — one generator
  produces every provider mirror from a single source, and drift is guarded in CI.
- **Scope**: in — a generator script that produces `agent_providers/claude_code/` and
  `.codex/` from the canonical `.claude/agents/` source, unifies the 3-way-forked skills,
  and a CI drift-check; out — changing agent-prompt *content* semantics.
- **Environment Prerequisites**: none.
- **Acceptance Criteria**:
  - [ ] A single script (named in the PR) regenerates all mirrors idempotently (running it
        twice produces no diff).
  - [ ] `.codex/` and `agent_providers/claude_code/` each contain all 17 agents; a name-list
        diff against `.claude/agents/` is empty.
  - [ ] Skills are sourced from one canonical location; the other two former forks are
        generated or symlinked (no independent copies).
  - [ ] A drift-check command exits non-zero when a mirror is stale (demonstrated by
        touching a source file and running the check).
- **Role hint**: be-developer. **Flags**: none. **model:opus** (architecture-heavy — defines
  the canonical model + guard). **Review-scope**: full gates.
- **References**: ABS-138 Finding #2; `.agents/README.md` canonical-mirror claim.

## Story Draft 6 — Finding #6: graphify-out rebuild

- **Goal**: the mandated agent-context `graphify-out/` reflects current HEAD, not a
  229-commit-stale snapshot.
- **Scope**: in — regenerate `graphify-out/` from current HEAD and commit; out — changing
  graphify tooling itself.
- **Environment Prerequisites**: none.
- **Acceptance Criteria**:
  - [ ] `graphify-out/` is regenerated from current HEAD (provenance/source-commit recorded
        in the report or a header).
  - [ ] The regenerated file/module coverage reflects the current tree (no reference to the
        old `edd4cca6` snapshot; file count consistent with the present source tree).
  - [ ] `graphify-out/GRAPH_REPORT.md` (or `graph.json`) opens and is internally consistent
        (no dangling references to deleted files).
- **Role hint**: be-developer. **Flags**: none. **model:sonnet** (mechanical regen).
- **Review-scope**: full gates (generated agent-context agents depend on — regen correctness
  needs a look). No skip.
- **References**: ABS-138 Finding #6.

## Story Draft 7 — Finding #3: RLS hook (non-functional security control) — SECURITY LANE

- **Goal**: the RLS pre-bash gate actually fires, reads its input correctly, and blocks
  ungoverned DB access.
- **Scope**: in — fix `.claude/hooks/pre-bash-rls-validation.sh` to read the hook's stdin
  JSON (currently `BASH_COMMAND="$1"`, line 9 — verified), register it and the 2 other
  unregistered hook scripts in the hook config, and make it block (exit 2) when RLS context
  is absent; out — new RLS policy design.
- **Environment Prerequisites**: none.
- **Acceptance Criteria**:
  - [ ] The hook extracts the command from stdin JSON (test: pipe a JSON payload, assert the
        command is parsed — not empty).
  - [ ] A `npx prisma`/`psql` command lacking `withUserContext`/`withAdminContext`/
        `withSystemContext` causes the hook to exit 2 (blocked), not exit 0 (warn).
  - [ ] A command with a valid RLS context helper exits 0.
  - [ ] The hook (and the 2 siblings) are registered in the hook config so they are invoked;
        evidence is a triggered-run log, or the siblings are removed if genuinely unused.
- **Role hint**: be-developer. **Flags: security** (RLS control). **model:sonnet**.
- **Review-scope**: full gates + SecEng (security flag) — never skip.
- **References**: ABS-138 Finding #3; verified `.claude/hooks/pre-bash-rls-validation.sh:9`.

## Story Draft 8 — Finding #8: merge-policy contradiction — NOT READY (ADR-gated)

- **Goal**: one authoritative merge policy resolving dark-factory `gh pr merge --auto --squash`
  vs ADR-A-0004/0005 + CONTRIBUTING rebase-only/human-merge; then align the offending doc.
- **Environment Prerequisites**: none.
- **Acceptance Criteria**: [ ] a new/updated ADR states the single merge policy;
  [ ] the dark-factory policy text no longer contradicts it (grep shows no surviving
  `gh pr merge --auto --squash` mandate).
- **Role hint**: system-architect. **Flags**: none. **model:opus**. **Review-scope**: full gates.
- **GATE**: **do not label `orchestrator-ready`** until the System Architect ADR is authored.
  Excluded from the DoR-ready set this pass. Downstream: ADR Authoring Request → System
  Architect (proposed level: agentic), carried from PO Triage.

## Story Draft 1 — Finding #4: version identity — CLOSED (already remediated)

- Verified `.boilerplate-version` = 2.21.2 (matches governor tag). Close the covering child
  as already-done referencing ABS-139/140/148. Not evaluated by DoR.
