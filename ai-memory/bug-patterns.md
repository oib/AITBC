# Bug Patterns Memory

A catalog of recurring failure modes and their proven fixes. Consult before attempting a fix.

## Pattern: Python ImportError for app.services

**Symptom**
```
ModuleNotFoundError: No module named 'trading_surveillance'
```
or
```
ImportError: cannot import name 'X' from 'app.services'
```

**Root Cause**
CLI command modules attempted to import service modules using relative imports or path hacks. The `services/` directory lacked `__init__.py`, preventing package imports. Previous code added user-specific fallback paths.

**Correct Solution**
1. Ensure `apps/coordinator-api/src/app/services/__init__.py` exists (can be empty).
2. Add `apps/coordinator-api/src` to `sys.path` in the CLI command module.
3. Import using absolute package path:
   ```python
   from app.services.trading_surveillance import start_surveillance
   ```
4. Provide stub fallbacks with clear error messages if the module fails to import.

**Example Fix Location**
- `cli/aitbc_cli/commands/surveillance.py`
- `cli/aitbc_cli/commands/ai_trading.py`
- `cli/aitbc_cli/commands/ai_surveillance.py`
- `cli/aitbc_cli/commands/advanced_analytics.py`
- `cli/aitbc_cli/commands/regulatory.py`
- `cli/aitbc_cli/commands/enterprise_integration.py`

**See Also**
- PR #10: resolves these import errors
- Architecture note: coordinator-api services use `app.services.*` namespace

---

## Pattern: Missing README blocking package installation

**Symptom**
```
error: Missing metadata: "description"
```
when running `pip install -e .` on a package.

**Root Cause**
`setuptools`/`build` requires either long description or minimal README content. Empty or absent README causes build to fail.

**Correct Solution**
Create a minimal `README.md` in the package root with at least:
- One-line description
- Installation instructions (optional but recommended)
- Basic usage example (optional)

**Example**
```markdown
# AITBC Agent SDK

The AITBC Agent SDK enables developers to create AI agents for the decentralized compute marketplace.

## Installation
pip install -e .
```
(Resolved in PR #6 for `aitbc-agent-sdk`)

---

## Pattern: Test ImportError due to missing package in PYTHONPATH

**Symptom**
```
ImportError: cannot import name 'aitbc' from 'aitbc'
```
when running tests in `packages/py/aitbc-core/tests/`.

**Root Cause**
`aitbc-core` not installed or `PYTHONPATH` does not include `src/`.

**Correct Solution**
Install the package in editable mode:
```bash
pip install -e ./packages/py/aitbc-core
```
Or set `PYTHONPATH` to include `packages/py/aitbc-core/src`.

---

## Pattern: Git clone permission denied (SSH)

**Symptom**
```
git@...: Permission denied (publickey).
fatal: Could not read from remote repository.
```

**Root Cause**
SSH key not added to Gitea account or wrong remote URL.

**Correct Solution**
1. Add `~/.ssh/id_ed25519.pub` to Gitea SSH Keys (Settings → SSH Keys).
2. Use SSH remote URLs: `git@gitea.bubuit.net:oib/aitbc.git`.
3. Test: `ssh -T git@gitea.bubuit.net`.

---

## Pattern: Gitea API empty results despite open issues

**Symptom**
`curl .../api/v1/repos/.../issues` returns `[]` when issues clearly exist.

**Root Cause**
Insufficient token scopes (needs `repo` access) or repository visibility restrictions.

**Correct Solution**
Use a token with at least `repository: Write` scope and ensure the user has access to the repository.

---

## Pattern: CI only runs on Python 3.11/3.12, not 3.13

**Symptom**
CI matrix missing 3.13; tests never run on default interpreter.

**Root Cause**
Workflow YAML hardcodes versions; default may be 3.13 locally.

**Correct Solution**
Add `3.13` to CI matrix; consider using `python-version: '3.13'` as default.

---

## Pattern: Claim branch creation fails (already exists)

**Symptom**
`git push origin claim/7` fails with `remote: error: ref already exists`.

**Root Cause**
Another agent already claimed the issue (atomic lock worked as intended).

**Correct Solution**
Pick a different unassigned issue. Do not force-push claim branches.
