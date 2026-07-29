# Claude Code Configuration

This directory contains the AITBC Claude Code harness: hooks, slash commands, and (coming soon) skills for workflow automation.

## Harness Architecture

```text
┌──────────────────────────────────────────────────────────────────────┐
│                      AITBC Claude Code Harness                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  HOOKS (Guardrails)              SLASH COMMANDS (User-Invoked)        │
│  ├─ Pre-commit reminders         ├─ /start-work                       │
│  ├─ Push blocker (uncommitted)   ├─ /remote-deploy                    │
│  └─ Auto-format on edit          └─ /pre-pr                           │
│                                                                       │
│  SKILLS (Model-Invoked) ✅ Available                                  │
│  ├─ safe-workflow      (SAFe commit/PR patterns)                      │
│  ├─ pattern-discovery  (search patterns_library/ first)               │
│  ├─ rls-patterns       (database security helpers)                    │
│  └─ frontend-patterns  (Clerk, shadcn, Next.js App Router)            │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

**Key distinction:**

- **Hooks**: Automatic guardrails (reminders and critical blockers)
- **Slash Commands**: Explicit user-invoked workflows (`/start-work`, `/pre-pr`)
- **Skills**: Model-invoked expertise packs (Claude auto-loads relevant context)

_These are the **harness** layers. The default **application** architecture (Data / Business / Frontend) is governed by [ADR-A-0011](../adrs/agentic/ADR-A-0011-three-layer-application-architecture.md)._

### Editing this source (apply path)

`harness/claude/` is the **headless-editable** agent-def source: an agent seat can edit it under
`--permission-mode dontAsk` (the `.claude`-named tree is a generated artifact, hard-denied to
writes). To change agents, hooks, or skills:

1. Edit under `harness/claude/**`.
2. Run `scripts/generate-governor.sh --providers` to regenerate `agent_providers/claude_code/`.
3. Commit both. The live `.claude/` is refreshed only at governor promotion, not per ticket.

No operator-apply step is needed. See [ADR-A-0016](../adrs/agentic/ADR-A-0016-claude-target-apply-path.md).

## Team Principles (SAFe + Round Table)

This harness is designed to help every teammate (human + AI) uphold:

- **SAFe Pillars**: Alignment, Built-in Quality, Program Execution, Transparency
- **AITBC Round Table**: humans + AI agents are peers; Stop-the-Line authority is encouraged

Canonical reference: `.cursor/rules/06-team-culture.mdc`

## Role Execution Modes (AITBC-499)

### Collapsed vs Separated Roles

The vNext workflow defines role separation (Implementation → QAS → RTE → HITL), but roles can be **collapsed** for efficiency when appropriate.

**Key principle**: Subagents are for efficiency _and_ independence; only coordination roles may be collapsed.

### Role Classification

| Role                      | Type                    | Collapsible?    | Notes                                |
| ------------------------- | ----------------------- | --------------- | ------------------------------------ |
| Implementation (BE/FE/DE) | Execution               | N/A (base role) | -                                    |
| RTE                       | Coordination/Automation | ✅ Yes          | PR creation, CI shepherding          |
| QAS                       | Independence Gate       | ❌ No\*         | \*See Self-QA exception below        |
| SecEng                    | Independence Gate       | ❌ No\*         | Security audit requires independence |
| HITL                      | Final Authority         | ❌ Never        | oib merges                         |

### Collapsed Roles (In-Flow with HITL)

The main Claude instance can collapse **coordination roles** (RTE) when:

- Working in-flow with HITL (sequential, no parallelism benefit)
- PR creation is the natural next step after implementation
- Already have full context from implementation

**Hat Convention** for traceability:

- "Operating as **Implementation** → exit state `Ready for QAS`"
- "Operating as **RTE (collapsed)** → PR creation + CI shepherding → exit state `Ready for HITL Review`"

### Independence Roles (Never Silently Collapsed)

**QAS** and **SecEng** are independence gates, not efficiency roles:

- **Default = spawn subagent** for independent verification
- If collapsed: Must be explicitly labeled **"Self-QA (non-independent)"**
- Self-QA only allowed when:
  - Change is docs-only / harness-only / low-risk, **AND**
  - Exception recorded in Linear (reason + evidence)
- Still requires next independent gate (HITL) before merge

### Invariants (Always Apply)

Regardless of role collapsing, these invariants are **never relaxed**:

- ✅ Stop-the-Line gate (AC/DoD must exist before implementation)
- ✅ Validation loop (tests pass, lint clean)
- ✅ Evidence in Linear (system of record)
- ✅ HITL merge authority

See: `docs/workflow/ARCHITECT_IN_CLI_ROLE.md` for orchestrator authority.

## Slash Commands

### Workflow Commands

| Command           | Purpose                               | Usage                              |
| ----------------- | ------------------------------------- | ---------------------------------- |
| `/start-work`     | Begin new ticket with proper workflow | `/start-work 347` or `/start-work` |
| `/pre-pr`         | Run complete validation before PR     | `/pre-pr`                          |
| `/end-work`       | Complete work session cleanly         | `/end-work`                        |
| `/check-workflow` | Quick status check of workflow        | `/check-workflow`                  |
| `/update-docs`    | Identify and update documentation     | `/update-docs`                     |
| `/retro`          | Conduct retrospective analysis        | `/retro`                           |
| `/sync-linear`    | Sync current work with Linear ticket  | `/sync-linear`                     |

### Local Operations

| Command         | Purpose                             | Usage           |
| --------------- | ----------------------------------- | --------------- |
| `/local-sync`   | Full sync after git pull            | `/local-sync`   |
| `/local-deploy` | Deploy to local Docker environment  | `/local-deploy` |
| `/quick-fix`    | Fast-track workflow for small fixes | `/quick-fix`    |

### Remote Operations (Pop OS)

These are the **canonical commands** for Pop OS machine operations.

| Command            | Purpose                              | Usage              |
| ------------------ | ------------------------------------ | ------------------ |
| `/remote-status`   | Check if Docker environment outdated | `/remote-status`   |
| `/remote-deploy`   | Deploy latest image to staging       | `/remote-deploy`   |
| `/remote-health`   | Full health dashboard                | `/remote-health`   |
| `/remote-logs`     | View container logs                  | `/remote-logs`     |
| `/remote-rollback` | Rollback to previous image           | `/remote-rollback` |

### Other Commands

| Command           | Purpose                            | Usage                 |
| ----------------- | ---------------------------------- | --------------------- |
| `/test-pr-docker` | Test PR Docker workflow            | `/test-pr-docker 225` |
| `/audit-deps`     | Run comprehensive dependency audit | `/audit-deps`         |
| `/search-pattern` | Search for code patterns           | `/search-pattern`     |

## Dual-Mode Deployment (AITBC-445 Terminology Contract)

Pop OS supports two deployment modes. **Use canonical terminology:**

| Mode        | Container Name     | Port | Use Case                     |
| ----------- | ------------------ | ---- | ---------------------------- |
| **Dev**     | `aitbc-dev`     | 3000 | Daily development (STANDARD) |
| **Staging** | `aitbc-staging` | 3001 | Release validation/UAT       |

**Important:**

- "dev branch" = Git branch (source code)
- "dev-mode container" = Docker deployment on Pop OS (port 3000)
- "staging-mode container" = Docker deployment on Pop OS (port 3001)

Both containers run images built from the `dev` branch. The difference is configuration (ports, volume mounts).

## Typical Workflow

```bash
# 1. Start new ticket
/start-work 347

# 2. Make changes, commit work...
# git add . && git commit -m "feat(scope): description [AITBC-347]"

# 3. Check status periodically
/check-workflow

# 4. Update documentation before PR
/update-docs

# 5. Validate before creating PR
/pre-pr

# 6. Create PR (if validation passes)
# git push --force-with-lease origin AITBC-347-branch
# # Use the PR template as your PR body baseline:
# # gh pr create --title "feat(scope): description [AITBC-347]" --body "$(cat .github/pull_request_template.md)"
# gh pr create ...

# 7. End session cleanly
/end-work
```

## Hooks Configuration

Hooks provide automatic reminders, validation, and critical blockers during development.

**Where the wiring lives (ABS-32)**: the live hooks are in the `"hooks"` block of
`.claude/settings.template.json`. Claude Code **auto-loads** `.claude/settings.json`, so once you
copy the template to `settings.json` (see [SETUP.md](SETUP.md)) the hooks fire with no further
setup — there is **no copy-paste-into-settings step**. `.claude/hooks-config.json` is kept only as
an annotated, human-readable mirror (source-of-record); editing it does **not** change runtime
behavior.

**Prerequisite: `jq`.** Every command-conditioned hook reads the tool-call JSON on stdin and
extracts the field it needs with `jq` (e.g. `jq -r '.tool_input.command // empty'`). If `jq` is not
installed, those hooks **fail open** (exit 0) with a one-line stderr warning rather than block your
work. Install `jq` to get the reminders and guards.

### Active Hooks (from settings.template.json)

**Session Lifecycle:**

| Event          | Behavior                                        |
| -------------- | ----------------------------------------------- |
| `SessionStart` | Shows available commands and workflow reminders |
| `SessionEnd`   | Warns if uncommitted changes exist              |

**Pre-Tool Hooks (Prevention):**

| Trigger               | Behavior                                                                      |
| --------------------- | ----------------------------------------------------------------------------- |
| On prompt submit      | Reminds about `AITBC-{number}` branch naming convention                         |
| Before `git commit`   | Reminds about SAFe commit format                                              |
| Before `git push`     | ❌ **BLOCKS** (exit 2) if on `main`; ❌ **BLOCKS** (exit 2) if uncommitted; warns if behind |
| Before `gh pr create` | Reminds to run `/pre-pr` validation first                                     |
| On a gate bounce (`Iteration N of M`) | ❌ **BLOCKS** (exit 2) once the ticket's iteration cap is reached; forces human escalation (ABS-12) |

> **Matcher note**: Claude Code `PreToolUse`/`PostToolUse` matchers match the tool **name** only
> (`"Bash"`, `"Write|Edit"`), never the command text. So every Bash-command hook above uses matcher
> `"Bash"` and re-derives the command from the tool-call JSON on stdin — `payload=$(cat)` then
> `printf '%s' "$payload" | jq -r '.tool_input.command // empty'` — acting only when it matches. A
> matcher like `"Bash.*git push"` **never fires** (it is compared against the literal string
> `"Bash"`). There is **no `$TOOL_INPUT` env var**; blockers signal by exit code 2 (stderr is fed
> back to Claude), not exit 1.

**Post-Tool Hooks (Feedback):**

| Trigger                         | Behavior                                                                 |
| ------------------------------- | ------------------------------------------------------------------------ |
| After `Write`/`Edit` of a `.md` | Auto-formats with Prettier + markdownlint (`.tool_input.file_path`)      |
| After `Write`/`Edit` of a high-impact doc | Reminds to update related documentation in the PR              |
| After `Write`/`Edit` (evolver provider) | ABS-25 Evolver `--review` (rate-limited, fail-open)              |

### Wired Hook Scripts

Hook scripts invoked from the `"hooks"` block in `settings.template.json`:

| Script                         | Trigger            | Purpose                                                  |
| ------------------------------ | ------------------ | -------------------------------------------------------- |
| `scripts/hooks/iteration-guard.sh` | `PreToolUse` Bash, when the command carries an `Iteration N of M` marker | Reads the payload on stdin; enforces the iteration cap on gate bounces only; blocks ambiguous multi-ticket compound commands (exit 2). See `specs/ABS-12-iteration-guard-spec.md` |
| `scripts/hooks/evolver-lifecycle.sh` | `SessionStart` / `PostToolUse` / `Stop` | ABS-25 Evolver lifecycle: invoke `evolver --review` when the evolution provider is `evolver` (rate-limited, fail-open) |
| `scripts/hooks/extract-bash-command.sh` | Helper used by `iteration-guard.sh` | Reads the PreToolUse JSON on stdin and prints `tool_input.command` (matchers see the tool name only). The inline hook commands themselves use `jq` directly. |

**Human override**: the guard blocks a *mechanical* bounce; it does not resolve the ticket. After
escalation, a human triages the root cause (e.g. provisions a missing credential, corrects the
spec, or accepts the work) and either closes the ticket or raises the per-ticket cap. To raise the
cap, the human posts a corrected `Iteration N of M` marker with a larger `M` **directly in a
terminal outside Claude Code** — hooks only run inside the harness, so a direct adapter call is
not intercepted.

### Installing Hooks

No manual copy-paste is needed. Claude Code auto-loads `.claude/settings.json`, and the hooks ship
in its template:

1. Copy the template to the loaded settings file (once per project):
   `cp .claude/settings.template.json .claude/settings.json`
2. Ensure `jq` is installed (`jq --version`) so command-conditioned hooks run.
3. Restart / reload Claude Code — the `"hooks"` block is picked up automatically.

Verify with `claude --debug` (hook execution is logged) or run
`bash tests/test-hooks-behavioral.sh` to exercise every hook command against realistic payloads.

## Skills

Skills are model-invoked expertise packs that Claude loads automatically when relevant context is detected.

### Skills Index (18 Skills)

| Skill | Purpose | Related Skills |
|-------|---------|----------------|
| [safe-workflow](skills/safe-workflow/) | Branch naming, commit format, PR workflow | release-patterns, git-advanced |
| [release-patterns](skills/release-patterns/) | PR creation, CI/CD validation | safe-workflow, deployment-sop |
| [pattern-discovery](skills/pattern-discovery/) | Search patterns before implementing | api-patterns, frontend-patterns |
| [agent-coordination](skills/agent-coordination/) | Agent assignment, blocker escalation | orchestration-patterns, linear-sop |
| [rls-patterns](skills/rls-patterns/) | Row Level Security for database ops | api-patterns, security-audit |
| [spec-creation](skills/spec-creation/) | Specs with acceptance criteria | pattern-discovery, testing-patterns |
| [orchestration-patterns](skills/orchestration-patterns/) | Multi-step task orchestration | agent-coordination, linear-sop |
| [testing-patterns](skills/testing-patterns/) | Jest and Playwright patterns | api-patterns, spec-creation |
| [security-audit](skills/security-audit/) | RLS validation, vulnerability scanning | rls-patterns, api-patterns |
| [linear-sop](skills/linear-sop/) | Linear ticket management | orchestration-patterns |
| [migration-patterns](skills/migration-patterns/) | Database migrations with RLS | rls-patterns |
| [frontend-patterns](skills/frontend-patterns/) | Next.js, Clerk, shadcn/ui | api-patterns, testing-patterns |
| [api-patterns](skills/api-patterns/) | API routes with Zod validation | rls-patterns, testing-patterns |
| [git-advanced](skills/git-advanced/) | Rebase, bisect, cherry-pick | safe-workflow |
| [stripe-patterns](skills/stripe-patterns/) | Payment integration, webhooks | api-patterns, security-audit |
| [team-coordination](skills/team-coordination/) | Agent Teams orchestration (experimental) | agent-coordination, orchestration-patterns |
| [deployment-sop](skills/deployment-sop/) | Deployment workflows, smoke tests | release-patterns |
| [confluence-docs](skills/confluence-docs/) | ADRs, runbooks, architecture docs | spec-creation |

### Skill Structure

Each skill folder contains:
- `SKILL.md` - Main skill definition (Claude loads this)
- `README.md` - Quick reference and metadata

Skills live in `.claude/skills/{skill-name}/`.

### Creating New Skills

See the **[Skill Authoring Guide](../docs/guides/SKILL_AUTHORING_GUIDE.md)** for:
- Official Anthropic resources
- Community checklists (jezweb/claude-skills)
- Our harness quality standards
- Step-by-step skill creation

### Listing Available Skills

**Known Issue**: The `/skills` command has a display bug in Claude Code v2.0.73 (GitHub Issue #14733).
Skills ARE working, but won't appear in `/skills` output.

**Workaround**: Ask Claude directly:

```text
What skills are available?
```

Or list the filesystem:

```bash
ls .claude/skills/
```

## Customization

### Adding New Slash Commands

Create a new markdown file in `.claude/commands/`:

```markdown
---
description: Command purpose
argument-hint: [optional args]
---

Command instructions here.

Use $1, $2 for positional arguments.
Use $ARGUMENTS for all arguments.
```

### Modifying Hooks

Edit the `"hooks"` block in `.claude/settings.template.json` (the auto-loaded file), then re-copy it
to `.claude/settings.json`. `matcher` is a **tool name** (`"Bash"`, `"Write|Edit"`) or omitted for
lifecycle events; put command-level conditions **inside** the command, reading stdin once and
extracting fields with `jq`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "payload=$(cat); command -v jq >/dev/null 2>&1 || { echo 'hooks: jq not found; skipping' >&2; exit 0; }; cmd=$(printf '%s' \"$payload\" | jq -r '.tool_input.command // empty'); printf '%s' \"$cmd\" | grep -qE 'git[[:space:]]+push' || exit 0; echo 'reminder'",
            "description": "What this hook does (exit 2 to BLOCK; stderr is fed back to Claude)"
          }
        ]
      }
    ]
  }
}
```

Keep `.claude/hooks-config.json` in step as the annotated mirror, and update
`tests/test-hooks-behavioral.sh` for any new behavior.

## Documentation

- **CONTRIBUTING.md**: Project workflow requirements
- **Slash Commands Guide**: [Claude Code slash commands](https://docs.anthropic.com/en/docs/claude-code/slash-commands)
- **Hooks Guide**: [Claude Code hooks](https://docs.anthropic.com/en/docs/claude-code/hooks)

## Troubleshooting

### Slash Commands Not Working

1. Verify `.claude/commands/` directory exists
2. Check file permissions (should be readable)
3. Restart Claude Code
4. Run `claude --debug` to see command loading

### Hooks Not Triggering

1. Confirm you copied `.claude/settings.template.json` to `.claude/settings.json` (auto-loaded).
2. Check `jq` is installed — command-conditioned hooks fail open (silent) without it.
3. Verify matchers are **tool names** (`"Bash"`, `"Write|Edit"`), not command text; a matcher like
   `"Bash.*git push"` never fires.
4. Check JSON syntax: `jq empty .claude/settings.json`.
5. Run `claude --debug` to see hook execution.

## Maintenance

These configurations are part of the project and should be:

- Committed to version control
- Updated when workflow changes
- Documented when modified
- Tested after changes

---

**Last Updated**: 2026-07-03
**Maintained by**: AITBC Development Team + ARCHitect-in-the-IDE (Auggie)
