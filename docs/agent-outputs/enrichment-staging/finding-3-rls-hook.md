# Fix non-functional RLS pre-bash hook [SECURITY LANE] (Audit Finding #3)

## Goal
`.claude/hooks/pre-bash-rls-validation.sh` becomes an actual security gate: reads stdin
JSON (not `$1`), is registered in `.claude/settings.template.json`, and blocks (exit 2)
when a Prisma/SQL command lacks an RLS context helper. The two unregistered sibling hook
scripts are explicitly decommissioned.

## Scope
- **In scope**: fix `pre-bash-rls-validation.sh` to parse stdin JSON; register it in
  `.claude/settings.template.json` PreToolUse/Bash section; change warn-only exit 0 → exit 2;
  decommission the two sibling hooks (see dispositions in AC-3).
- **Out of scope**: new RLS policy design; changes beyond the three named hook scripts;
  changes to Prisma schema.

## Environment Prerequisites
None.

## Acceptance Criteria
- [ ] AC-1 (stdin JSON parsing): The hook extracts the command via stdin JSON:
  `payload=$(cat); cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')`.
  Test: `printf '{"tool_input":{"command":"npx prisma db pull"}}' | bash
  .claude/hooks/pre-bash-rls-validation.sh`; assert exit code is 2 (blocked) and stderr
  contains a meaningful message.
- [ ] AC-2 (blocking): A command matching `npx prisma|psql|DATABASE_URL` without
  `withUserContext|withAdminContext|withSystemContext` causes exit 2. A command with a
  valid RLS helper causes exit 0.
- [ ] AC-3 (sibling hook dispositions — no OR):
  - `post-commit-linear-update.sh` → **DECOMMISSION**: remove the file. Rationale: this is
    a git PostCommit script (not a Claude Code hook event type), uses the unresolved
    `AITBC` template token, and is unregistered. Not a security control.
  - `session-start-pattern-check.sh` → **DECOMMISSION**: remove the file. Rationale: reads
    `patterns_library/` which is being removed by Finding #7; not a PreBash security control.
  After removal: `find .claude/hooks/ -name "post-commit-linear-update.sh" -o -name
  "session-start-pattern-check.sh"` returns empty.
- [ ] AC-4 (registration): The fixed hook is registered in `.claude/settings.template.json`
  under PreToolUse/Bash (follow the pattern of existing hooks in that file). Verify: `jq
  '.hooks.PreToolUse[]? | select(.matcher == "Bash") | .hooks[].command' 
  .claude/settings.template.json` includes the rls-validation command.
- [ ] AC-5 (rollback path): The hook can be disabled without a code change. Document the
  disable mechanism in the PR description: removing the hook entry from
  `.claude/settings.template.json` (and re-running the copy step to apply to
  `settings.json`) is the rollback path. Verify `jq empty .claude/settings.template.json`
  exits 0 after any settings change (valid JSON).
- [ ] AC-6: Repo lint and build scripts exit 0 after changes.

## References
- **Origin**: BSA Grooming, ABS-138 Finding #3; security lane flagged by PO Triage
- **Related**: none
- **Patterns/Specs**: `patterns_library/security/` (see directory for applicable security
  patterns); `.claude/hooks-config.json` (authoritative reference for hook protocol: stdin
  JSON schema, `PreToolUse/Bash` matcher, exit code semantics — read it FIRST);
  `docs/security/SECURITY_FIRST_ARCHITECTURE.md`

## Guardrail Annotation
- **Feasibility**: flagged — security-critical; SecEng review required at PR
- **Applicable ADRs**: ADR-A-0004 (security controls are within agent scope to fix; merge
  to main remains human gate); ADR-A-0010 (fix the hook minimally — stdin parsing +
  registration + exit code; no new blocking rules beyond original intent)
- **Approval Boundaries**: merge to main = human gate; SecEng review on PR recommended
- **Constraints**: Fix only what is broken. Do NOT expand the set of blocked commands beyond
  original intent. False-positive tuning goes in a separate ticket.

## Context Pack
- ADR-A-0004: security controls are agent-fixable; merge is human gate (`adrs/agentic/ADR-A-0004-human-approval-boundaries.md`)
- ADR-A-0010: fix minimally — stdin + registration + exit code only (`adrs/agentic/ADR-A-0010-minimal-change-default.md`)
- Pattern paths: `patterns_library/security/`; `docs/security/SECURITY_FIRST_ARCHITECTURE.md`
- Code refs: `.claude/hooks/pre-bash-rls-validation.sh:9` (`BASH_COMMAND="$1"` bug; all exit 0);
  `.claude/hooks-config.json` (hook protocol reference — read FIRST; registration is in settings.template.json);
  `.claude/settings.template.json` (live registration target); `.claude/hooks/post-commit-linear-update.sh`
  (decommission); `.claude/hooks/session-start-pattern-check.sh` (decommission)
- Guardrails: 🔒 flag=security; SecEng review; NEVER skip-review or skip-test; `model:sonnet`
