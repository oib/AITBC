# Git Workflow

This project enforces a **rebase-first workflow** validated by CI/CD automation. Apply this rule to ALL git operations. See `CONTRIBUTING.md` for the full guide.

## Branch Naming

**Required format:** `AITBC-{number}-{short-description}`

Examples:
- `AITBC-42-add-user-authentication`
- `AITBC-57-fix-profile-image-upload`

Rules:
- MUST start with `AITBC-{number}`
- Use lowercase letters and hyphens only
- Keep total length under 50 characters
- Never include personal names or dates
- CI will reject branches that do not follow this format

## Commit Message Format

**Required format:** `type(scope): description [AITBC-XXX]`

### Types

- `feat` -- New feature
- `fix` -- Bug fix
- `docs` -- Documentation changes
- `style` -- Code formatting (no logic changes)
- `refactor` -- Code restructuring
- `test` -- Adding or updating tests
- `chore` -- Maintenance tasks, dependencies
- `ci` -- CI/CD pipeline changes

### Scopes (optional)

- `payments`, `auth`, `ui`, `api`, `db`, `scheduler`, `security`

### Examples

```
feat(payments): add Stripe checkout integration [AITBC-42]
fix(auth): resolve login redirect issue [AITBC-57]
docs: update API documentation [AITBC-123]
```

CI will reject commits that do not include a ticket reference.

## Workflow Steps

```bash
# 1. Start from latest base branch
git checkout main
git pull origin main
git checkout -b AITBC-{number}-{description}

# 2. Make changes and commit
git add <files>
git commit -m "feat(scope): description [AITBC-XXX]"

# 3. Keep branch updated (rebase, NEVER merge)
git fetch origin
git rebase origin/main

# 4. Validate before pushing
# Run: {{CI_VALIDATE_COMMAND}}

# 5. Push
git push --force-with-lease origin AITBC-{number}-{description}

# 6. Create PR using .github/pull_request_template.md
# 7. Merge using "Rebase and merge" ONLY (never squash or merge commit)
```

## Rules

- **Rebase-first**: Never create merge commits. Always rebase onto the base branch.
- **Force-with-lease**: Use `--force-with-lease` after rebase, never `--force`.
- **Linear history**: The project requires a clean linear commit history.
- **One ticket per branch**: Each branch maps to exactly one project management ticket.
- **PR template**: Always use `.github/pull_request_template.md` and fill ALL sections.

## Role Collapsing

- **RTE** role is collapsible (PR creation can be done by implementer)
- **QAS** role is NOT collapsible (independence gate)
- **SecEng** role is NOT collapsible (security audit requires independence)
