---
description: Run comprehensive dependency audit
allowed-tools: [Read, Write, Edit, Bash, Grep, Glob]
---

Execute a dependency audit for AITBC's Python/Poetry stack to identify security issues and
optimization opportunities. Findings become tickets in the active tracker
(`scripts/gitea-tracker.sh` against the real Gitea issue tracker — this repo's `neutral` profile
has `task-tracking.provider: gitea`; see `profiles/neutral/profile.yaml` and
`docs/sop/ORCHESTRATOR_SOP.md`'s "Gitea Tracker Adapter" section for the required
`GITEA_SITE`/`GITEA_TOKEN`/`GITEA_OWNER`/`GITEA_REPO` env vars), not Linear/Jira/mock.

## Audit Workflow

### 1. Security Audit

Check for known vulnerabilities in installed dependencies (already in `pyproject.toml` as dev
dependencies — `pip-audit`, `safety`; run inside the project venv):

```bash
./venv/bin/python -m pip_audit
./venv/bin/python -m safety check --full-report
```

Report:

- Critical/High severity issues
- Packages with known CVEs
- Recommended upgrades

### 2. Static Security Lint (bandit)

```bash
./venv/bin/python -m bandit -r aitbc/ apps/ cli/ -ll
```

Identify:

- Hardcoded secrets/credentials
- Insecure crypto/subprocess/eval usage
- Other OWASP-adjacent findings ranked by severity

### 3. Unused / Missing Dependencies

```bash
./venv/bin/python -m pip list --not-required   # top-level installs not pulled in by anything else
poetry show --outdated                          # per-package outdated report (if using poetry)
```

Cross-check against actual imports (`grep -rn '^import \|^from ' aitbc/ apps/*/src`) to spot
declared-but-unused packages, and anything imported but missing from `pyproject.toml`.

### 4. Outdated Packages

```bash
poetry show --outdated
```

Report:

- Packages with newer versions
- Major vs minor vs patch updates
- Breaking change risk (read the changelog for majors)

### 5. App-Specific Node/JS Dependencies (optional, per-app)

A few AITBC components have their own `package.json` (e.g. `apps/explorer-web`,
`contracts/` Solidity tooling). Audit those independently, per app, only if in scope:

```bash
cd apps/explorer-web && npm audit
```

Do not run this against the repo root — there is no root-level `package.json`; Python is the
primary stack (see `CLAUDE.md` Technology Stack).

### 6. Create Audit Report

Document findings in `docs/agent-outputs/technical-docs/dependency-audit-report-{date}.md`:

```markdown
# Dependency Audit Report

**Date**: {current-date}
**Scope**: Full dependency audit
**Tools**: pip-audit, safety, bandit, poetry show --outdated

## Executive Summary

- Total packages: {count}
- Security issues: {count} ({severity})
- Optimization potential: {summary}
- Quick wins: {count} tickets

## Findings

### 1. Security Issues (pip-audit / safety / bandit)

- List critical/high issues with CVE ids
- Recommended actions (upgrade to version X, remove package Y, etc.)

### 2. Unused / Missing Dependencies

- Unused (declared, not imported): {list}
- Missing (imported, not declared): {list}

### 3. Outdated Packages

- Major updates: {list}
- Minor updates: {list}
- Patch updates: {list}

## Recommendations

### Immediate Actions (High Priority)

1. {action}

### Short-term (Medium Priority)

1. {action}

### Long-term (Low Priority)

1. {action}

## Implementation Tickets

- AITBC-{number}: {description}
```

### 7. Create Tracker Tickets for Actionable Findings

For each significant finding, create a real Gitea issue via the tracker adapter (requires
`GITEA_SITE`/`GITEA_TOKEN`/`GITEA_OWNER`/`GITEA_REPO` set; run `scripts/gitea-tracker.sh setup`
once beforehand if labels aren't already provisioned):

```bash
scripts/gitea-tracker.sh create --type ticket --title "<short description>" \
    --priority <hotfix|high|normal|low> \
    --body-file <path-to-finding-writeup.md>
```

- Scope each ticket narrowly (one CVE/package/finding per ticket where practical)
- Priority: `hotfix` for actively-exploited CVEs, `high` for critical/high-severity findings,
  `normal`/`low` for outdated-package hygiene
- Leave tickets in `Backlog` for PO-Agent/human prioritization — do not self-assign `Ready for
  Development`

## Audit Frequency

Run audits:

- **Monthly**: Quick security check (`pip-audit` + `safety`)
- **Quarterly**: Full dependency audit (all steps above)
- **Before major releases**: Comprehensive audit
- **After dependency upgrades**: Validation audit

## Success Criteria

- ✅ All audit tools run successfully
- ✅ Findings documented completely
- ✅ Tickets created for actionable items
- ✅ Team has clear prioritization
- ✅ Baseline established for next audit

This provides a systematic approach to dependency management and optimization, scoped to
AITBC's actual Python/Poetry monorepo (plus optional per-app Node audits) and its actual
Gitea Issues ticketing, rather than the generic yarn/Linear template this command started from.
