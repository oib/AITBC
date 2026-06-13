# Type Checking Guide - Gradual Approach

## Overview

This project uses a **gradual type checking approach** to improve code quality without requiring a massive upfront effort to fix all existing type errors.

## Current State

**v0.4.18 Achievements:**
- ✅ coordinator-api: 0 MyPy errors (360 files checked, 148 excluded by config)
- ✅ agent-coordinator: 0 MyPy errors (49 source files)
- ✅ Ruff G004: 0 errors (all logging f-strings converted)
- ✅ 163 files with per-file ignores across apps

**v0.4.19 Progress:**
- ✅ edge: 0 MyPy errors (25 source files) - FIXED
- ⚠️ pool-hub: 29 errors (deferred to v0.4.20)
- ⚠️ agent-management: 82 errors (deferred to v0.4.20)
- ⚠️ blockchain-node: ~477 errors (excluded from MyPy checks)

**Remaining per-file ignores by app:**
- coordinator-api: 81 files (0 MyPy errors with current config)
- blockchain-node: 31 files (excluded from MyPy checks)
- pool-hub: 17 files (29 errors, deferred)
- wallet: 10 files (pending investigation)
- agent-management: 6 files (82 errors, deferred)
- hermes: 1 file (pending investigation)
- edge: 0 files ✅ MyPy clean

## How It Works

### 1. Pre-Commit Hook

When you run `git commit`, the pre-commit hook automatically checks type annotations on:
- Staged Python files
- Modified Python files

```bash
# Check a single file manually
venv/bin/python -m mypy your_file.py --follow-imports=skip --ignore-missing-imports
```

### 2. CI/CD Integration

The CI workflow runs mypy on changed files only:
- Compares against the previous commit
- Fails the build if new type errors are introduced
- Skips check if no Python files changed

### 3. What Gets Checked

✅ **Checked:**
- New Python files you create
- Modified Python files in your commits
- Files with newly added type annotations

❌ **Not Checked:**
- Existing unmodified files (they remain excluded)
- Files in the mypy exclusion list (see `pyproject.toml`)

## Developer Guidelines

### When Touching Existing Code

If you modify a file that has type errors:

1. **Fix the errors** in the functions you're modifying:
   ```python
   # Before (missing types)
   def process_data(data):
       return data.upper()
   
   # After (with types)
   def process_data(data: str) -> str:
       return data.upper()
   ```

2. **If you can't fix all errors**, use targeted `# type: ignore` comments:
   ```python
   # type: ignore[no-untyped-def]  # TODO: Add type annotations
   def legacy_function(data):
       ...
   ```

### Best Practices

1. **Add types to new code**:
   - Function signatures
   - Return types
   - Variable annotations for complex types

2. **Common patterns**:
   ```python
   from typing import Optional, dict, list, Any
   
   def fetch_user(user_id: int) -> Optional[dict[str, Any]]:
       ...
   
   def process_items(items: list[str]) -> list[int]:
       ...
   ```

3. **Use Pydantic models** where appropriate (they provide automatic type validation)

### Bypassing (Emergency Only)

If you absolutely must commit with type errors:

```bash
git commit --no-verify -m "Your message"
```

⚠️ **Warning**: This bypasses ALL pre-commit checks, not just mypy.

## Troubleshooting

### Mypy Command Not Found

```bash
venv/bin/pip install mypy
```

### Too Many Errors in Changed File

If a file you modified has many pre-existing type errors:

1. Fix the errors in functions you actually modified
2. Add `# type: ignore` comments for pre-existing errors you didn't touch
3. Create a follow-up ticket to fix the remaining errors

### False Positives

Mypy may report errors on valid code. Use explicit `# type: ignore` with error codes:

```python
# type: ignore[no-untyped-def]  # Function intentionally untyped
# type: ignore[attr-defined]    # Dynamic attribute access
# type: ignore[return-value]    # Complex return type
```

## Future Roadmap

1. **Phase 1** (v0.4.17): Complex files suppressed with per-file ignores ✅ Complete
2. **Phase 2** (v0.4.18 - v0.4.20): Gradually remove per-file ignores and fix type issues ⚠️ In Progress
   - v0.4.18: coordinator-api and agent-coordinator MyPy clean ✅
   - v0.4.19: edge MyPy clean ✅, pool-hub and agent-management deferred
   - v0.4.20: Fix pool-hub, agent-management, wallet, hermes
3. **Phase 3** (v0.5.0): Remove all per-file ignores and enforce strict type checking 📅 Planned

## Related Documentation

- [pyproject.toml](../../pyproject.toml) - Mypy configuration
- [scripts/ci/check-mypy-changed.sh](../../scripts/ci/check-mypy-changed.sh) - CI script
- [Python Type Hints Cheat Sheet](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html)

## Questions?

- Check the [gap analysis notes](../reference/TYPE_SAFETY_GAP_ANALYSIS.md)
- Ask in #dev-python on Slack
- Tag PRs with `type-safety` label for review
