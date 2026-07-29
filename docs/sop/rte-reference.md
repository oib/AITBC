# RTE Reference — Templates, Examples & Rationale

Extracted detail for the Release Train Engineer role (`.claude/agents/rte.md`, ABS-171).
The agent definition carries the decision rules, gates, handoff contracts, and escalation
triggers; this file carries the **copy-paste templates, worked examples, and rationale** the
RTE pulls in on demand.

Generic git/PR workflow (branch naming, commit format, rebase-first, pre-PR checklist, PR body
template, merge strategy) is **not** repeated here — it lives in the auto-loaded skills:

- `release-patterns` — PR creation template, pre-PR checklist, CI/CD validation command, QAS gate
- `safe-workflow` — branch naming, SAFe commit format, rebase-first workflow
- `git-advanced` — rebase / bisect / conflict-resolution procedures

Canonical PR body: `.github/pull_request_template.md`. Full workflow: `CONTRIBUTING.md`.

---

## Success & compliance validation commands

```bash
# Pre-PR validation (MANDATORY)
yarn ci:validate && echo "RTE SUCCESS" || echo "RTE FAILED"

# Commit format check
git log --oneline -10 | grep -E "AITBC-[0-9]+" && echo "COMMIT FORMAT SUCCESS"

# Linear-history check (no merge commits)
git log --oneline --graph --all | grep -c "Merge branch" \
  && echo "MERGE COMMITS FOUND - REBASE REQUIRED" || echo "LINEAR HISTORY SUCCESS"

# CI status via host PR CLI (gh: bb on Bitbucket, gh on GitHub)
gh pr checks && echo "CI SUCCESS"

# Branch-name format
git branch --show-current | grep -E "^AITBC-[0-9]+-" && echo "Branch name valid"
```

## Pre-PR validation checklist

```markdown
### Git Compliance
- [ ] Branch name: `AITBC-{number}-{description}`
- [ ] Commits: `type(scope): description [AITBC-XXX]`
- [ ] Rebased on latest main / epic branch (no merge commits)

### CI/CD
- [ ] `yarn type-check` / `lint` / `test:unit` / `format:check` / `build` pass

### Evidence
- [ ] Session IDs from all agents collected
- [ ] Validation results documented
```

## CI/CD pipeline stages (`.github/workflows/`)

1. Structure validation (branch/commit format)
2. Rebase-status check (linear history)
3. Comprehensive testing (all suites)
4. Quality & security (lint, TypeScript, audit)
5. Build verification (production build)
6. Conflict detection (high-risk file monitoring)

### Watch / triage CI

```bash
gh pr checks                 # bb / gh
# GitHub: gh run watch ; gh run view --log-failed
# Bitbucket: track via `bb pr view` or the Pipelines web UI
```

On failure: fix locally → commit `fix(ci): ... [AITBC-XXX]` → `git fetch origin &&
git rebase origin/main` → `git push --force-with-lease`. Structural/pattern failures
route to System Architect; implementation bugs route back to the implementer (never fix product
code yourself).

## Post-merge cleanup (after HITL merges)

```bash
git checkout main && git pull origin main
git log --oneline -5 | grep "AITBC-XXX"   # verify merge
# Tickets referenced in commit messages auto-move to Done; manually close unreferenced children,
# attach the PR link, tag POPM for final review.
```

## Evidence attachment template (RTE Release Report)

```markdown
## RTE Release Report — AITBC-XXX

### Session ID
[Claude session ID]

### PR Details
- PR: #XXX — feat(scope): description [AITBC-XXX]
- Base: dev / epic branch    Compare: AITBC-XXX-description

### Pre-Merge Validation
- `yarn ci:validate` — all checks passed
- `git log --oneline --graph -10` — linear history confirmed
- `gh pr checks` — all CI checks passed
- `scripts/merge-target-guard.sh check "<the ACTUAL MR target branch>"` — exit 0 (target not protected). Pass the real branch the MR is opened against, never a hard-coded slug (an empty var trips the guard's usage error, exit 64, not the clean `MERGE-GUARD-REFUSE` line). A protected target (`main`) exits 1 → hand off to HITL. This is also enforced mechanically by the PreToolUse merge chokepoint (`.claude/hooks/pre-bash-merge-guard.sh`, PILOT-11), which blocks a protected-branch `bb pr merge`/`glab mr merge` even if this step is skipped.

### Reviewer Approvals
- System Architect (stage 1): approved
- ARCHitect (stage 2): approved
- CODEOWNERS auto-assigned: yes

### Merge Details
- Method: Rebase and merge · Branch deleted · Linear history maintained

### Deployment Status
- Dev / Staging / Production: [status]

### Post-Merge Actions
- Ticket moved to Done · POPM tagged · Local branch cleaned up
```

## Common release patterns

### Pattern 1 — Standard feature release

```bash
yarn ci:validate
git fetch origin && git rebase origin/dev
git push --force-with-lease origin AITBC-123-feature
gh pr create --title "feat(feature): implement feature [AITBC-123]" --web
gh pr checks
# Handoff to HITL — RTE does NOT merge.
```

### Pattern 2 — Hotfix release

```bash
git checkout main && git pull origin main
git checkout -b AITBC-999-hotfix-critical-bug
# ... fix ...
yarn ci:validate
gh pr create --base main --title "fix(critical): resolve security issue [AITBC-999]"
# Handoff to HITL for emergency merge, then backport to dev:
git checkout dev && git cherry-pick <hotfix-commit-sha> && git push origin dev
```

### Pattern 3 — Multi-agent coordination

```bash
# BE AITBC-124-api must merge before FE AITBC-123-ui.
# RTE coordinates but does NOT merge:
# 1. Notify HITL: "AITBC-124 ready, blocks AITBC-123". Wait for merge.
# 2. After merge, rebase the dependent branch:
git checkout AITBC-123-ui-component
git fetch origin && git rebase origin/dev && git push --force-with-lease
# 3. Notify HITL: "AITBC-123 ready after AITBC-124 merged".
```

## Epic-Integration station — status: OPERATOR-SUPPORTED (PILOT-76)

**Honest statement of record (PILOT-76 AC5).** The Epic-Integration station
(`Stories In Flight → Epic Integration → Ready for Epic Acceptance`, RTE seat) is
**not yet a fully hands-off automated station**. Across four consecutive v3 pilots the
RTE seat did not self-complete it — each time with a different signature — and a human
operator finished the integration by hand:

| Pilot | Epic | Failure signature |
|-------|------|-------------------|
| #4 | PILOT-17 | full suite (~15 min) exceeded the 10-min Bash-tool call limit |
| #5 | PILOT-28 | sync-rebase onto `main` conflicted (`core/src/index.ts`) |
| #6 | PILOT-39 | seat DENIED reading its own `mktemp` scratch under `/var/folders` → no verdict |
| #7 | PILOT-58 | trivial integration (`Already up to date`) yet `nomoves=2 → Needs PO Decision` |

Root cause (full analysis: PILOT-76 gate-results comment): the only forward edge out of
`Epic Integration` — `Ready for Epic Acceptance` — is gated behind the ABS-453 full-suite
`--verify`. When the seat cannot **produce** or **read** that verdict it correctly withholds
the transition, which the runner records as `HANDOFF-NOMOVE`; two of those escalate to
`Needs PO Decision`. Pilots #4/#6/#7 are all instances of the same infrastructure gap, not
four unrelated bugs.

### Enablers now in place

- **Staged full-suite entry (ABS-557).** Run the gate via `tests/staged-suite.sh`
  (`--list` → one `--stage` per Bash call, each < 5 min → `--verify` at the fixed epic tip),
  **never** `tests/run-all.sh` in one shot. Wired into `.claude/agents/rte.md` §218–235.
  Closes pilot #4 (timeout).
- **Per-seat `TMPDIR` inside the worktree (PILOT-76).** The spawn seam
  (`scripts/orchestrator-spawn-claude.sh`) now exports `TMPDIR=<worktree>/tmp`, so every
  `mktemp` the seat and the harness it spawns makes lands inside the already-allowlisted cwd
  and is readable at the gate. Closes pilots #6 (read-denial) and #7 (the trivial case that
  still could not assemble a verdict).

### What remains operator-supported (until PILOT-76 AC4 is falsified by a live run)

- **Sync-rebase conflict resolution (pilot #5).** By doctrine (ABS-90 / ADR-A-0005) the RTE
  **aborts** on a sync-rebase conflict (epic branch untouched) and blocks for TDM triage;
  additive conflict resolution is **human-only** — this is the intended path, not a defect.
  The operator resolves the conflict additively (Feature-Union: keep both sides), then the
  ABS-336 forward-fix route re-reviews and re-integrates.
- **Full-suite scale.** Even with the staged entry + readable scratch, a large epic tip can
  approach the seat's turn/time budget. If the seat cannot complete `--verify`, the operator
  runs the staged suite and, on green, releases the epic to `Ready for Epic Acceptance`.

The falsifying eval for promoting this station to hands-off (PILOT-76 AC4): an epic with all
children `Done` and nothing to merge reaches `Ready for Epic Acceptance` **without operator
intervention**. Until a live pilot demonstrates that, treat this station as operator-supported
and do not silently expect autonomy here.

## Production deployment owner (ABS/AITBC-314)

- Execute PROD migration checklist with Data Engineer (`PROD_MIGRATION_CHECKLIST_TEMPLATE.md`).
- Coordinate disaster recovery (`DISASTER_RECOVERY_PLAYBOOK.md`).
- Validate post-deployment data integrity (table counts, RLS verification).
- Roll back failed migrations via the documented rollback procedures.
