# Coding Standards

## Issue Creation
All agents must create issues using the **structured template**:
- Use the helper script `scripts/create_structured_issue.py` or manually follow the `.gitea/ISSUE_TEMPLATE/agent_task.md` template.
- Include all required fields: Task, Context, Expected Result, Files Likely Affected, Suggested Implementation, Difficulty, Priority, Labels.
- Prefer small, scoped tasks. Break large work into multiple issues.

## Code Style
- Follow PEP 8 for Python.
- Use type hints.
- Handle exceptions specifically (avoid bare `except:`).
- Replace `print()` with `logging` in library code.

## Commits
- Use Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
- Reference issue numbers in commit bodies (`Fixes #123`).

## PR Reviews
- Review for security, performance, and readability.
- Ensure PR passes tests and lint.
- Approve according to stability rings (Ring 0 requires manual review by a human; Ring 1+ may auto-approve after syntax validation).

## Memory Usage
- Record architectural decisions in `ai-memory/decisions/architectural-decisions.md`.
- Log daily work in `ai-memory/daily/YYYY-MM-DD.md`.
- Append new failure patterns to `ai-memory/failures/failure-archive.md`.
