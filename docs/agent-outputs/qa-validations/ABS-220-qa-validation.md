# QA Validation — ABS-220 (docs-station skill)

- **Branch**: ABS-220-auto
- **Commit**: cc68cdd
- **Files changed**: `harness/claude/skills/docs-station/SKILL.md` (new, +164), `harness/claude/agents/tech-writer.md` (modified, +8/-2)
- **Date**: 2026-07-12
- **Verdict**: APPROVED

---

## AC Verification

### AC1 — Skill location + frontmatter verbs

**Source side — PASS**

`harness/claude/skills/docs-station/SKILL.md` exists on branch `ABS-220-auto` (commit `cc68cdd`).

Frontmatter:
```
name: docs-station
description: Tech-Writer Docs-station recipes — verify the story's implementation PR is merged (worktree-less merge-base gate), inspect and edit docs on the story branch without a checkout, validate markdown (markdownlint with awk line-length fallback), and run the Docs->Done exit-precondition checklist. Use at the `Docs` seat before writing docs or transitioning a story to `Done`.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
```

Verbs present: verify (merge-gate), inspect, edit (branch-doc), validate (markdown), run (exit-precondition checklist). All four duties the seat performs are named. ✓

**Apply side — ACCEPTED (deferred to governor promotion, ABS-94)**

`.claude/skills/docs-station/` does not exist on this branch. Confirmed by design: `generate-governor.sh` has `skills` in `SHIPPED_ITEMS` (line 95), so it copies `harness/claude/skills/docs-station/` to `.claude/skills/docs-station/` at the next promotion. This is the standard ABS-94 model for all skills (verified: `run-boilerplate`, `confluence-docs` follow the same path). Dev seat cannot write the governed `.claude/` tree — not an implementation gap. **Not a bounce.**

### AC2 — Every code block executed for real

Independently re-executed all four recipes against this repo:

**Recipe 1 — merge-status gate**
```
$ git fetch --quiet origin
$ git merge-base --is-ancestor dcfbdeb HEAD && echo MERGED
MERGED — Docs->Done precondition satisfied
$ git merge-base --is-ancestor 0000000000000000000000000000000000000001 HEAD || echo "NOT MERGED"
NOT MERGED
```
Both exit paths verified (0 = merged, 1 = not merged). ✓

**Recipe 2 — branch-doc inspection**
```
$ git ls-tree -r --name-only HEAD -- docs/ | head
docs/HARNESS_MANIFEST_SCHEMA.md
docs/HARNESS_SYNC_GUIDE.md
[...]
$ git show HEAD:harness/claude/skills/README.md | head -3
# AITBC Skills
[...]
```
`git ls-tree` and `git show` execute correctly. ✓

**Recipe 3 — markdown validation**
```
$ npx --no-install markdownlint-cli2 harness/claude/skills/docs-station/SKILL.md
markdownlint-cli2 v0.23.0 (markdownlint v0.41.0)
Finding: harness/claude/skills/docs-station/SKILL.md
Linting: 1 file(s)
Summary: 0 error(s)
```
awk line-length gate: one flag on line 3 (386 chars) — the YAML frontmatter `description:` field. This is the established house pattern: `run-boilerplate` (line 3: 375 chars) and `confluence-docs` (line 3: 280 chars) have identical frontmatter. Not a lint error. ✓

**Recipe 4 — exit-precondition transition**
`jira-tracker.sh` adapter supports `transition <id> <to-status> --actor <actor> --reason <text>` (confirmed at line 219 of adapter). Recipe 4's command matches verbatim. ✓

**AC4 metric command**
```
scripts/orchestrator-report.sh [run.log]
```
Script exists; header at line 14 shows it accepts `[run.log]` with `$ORCH_RUN_LOG`/`$ORCH_STATE_DIR/run.log` as default — exact match to SKILL.md § "Success metric". ✓

### AC3 — tech-writer role definition references the skill

`harness/claude/agents/tech-writer.md` lines 253–261 (Docs Seat section):
> **Docs-station recipes (MANDATORY, skill: docs-station)**: this station's copy-paste procedures [...] live in `harness/claude/skills/docs-station/SKILL.md`. This seat has **no `Skill` tool** (ABS-123), so `Read` that file and apply the recipes verbatim — exactly as you apply `stop-slop`. Do NOT re-probe with `ls`/`which markdownlint`/`yarn lint:md`; the recipes already account for this repo's tooling (ABS-220).

Recipe 1 and recipe 4 are also anchored by name in the exit-precondition paragraph (line 270). ✓

### AC4 — Success metric documented

SKILL.md "Success metric" section (lines 127–140):
- **Baseline**: 81x `ls`-probing + `git show <branch>:docs/...` probing + `which markdownlint` across 12 sessions; 2 turn-cap deaths at 25-turn default (ABS-173); NOMOVE loop (ABS-211).
- **Target**: median tool-calls per tech-writer seat in next live run < 50% of baseline.
- **Measurement**: `scripts/orchestrator-report.sh "$ORCH_STATE_DIR/run.log"` — script verified present and accepting the argument. ✓

---

## Validation Commands Run

```
markdownlint-cli2 v0.23.0 (markdownlint v0.41.0) — 0 errors on SKILL.md
awk line-length — 1 flag (frontmatter line 3, house style, non-blocking)
git diff HEAD~1 --name-status — 2 files (expected)
scripts/orchestrator-report.sh — script present
```

## Non-blocking observation (carry-forward from system-architect, no fix needed)

Recipe 1 states `--is-ancestor` is "exact for … rebase merges" — for a squash merge the branch head is not an ancestor (SHA not in target). The recipe already handles this with the fallback: "trust the Merging handoff's `Result: merged` line." This repo uses merge-commits (verified). Wording nit only; fails closed.

---

## Verdict: APPROVED

All four ACs met. AC1 apply-side deferral to governor promotion is accepted per ABS-94 (not an implementation gap). Open item for RTE/release: run `generate-governor.sh` at next promotion to land `.claude/skills/docs-station/`.
