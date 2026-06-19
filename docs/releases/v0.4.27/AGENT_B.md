# Agent B Tasks - v0.4.27

## Overview

Agent B is responsible for **Infrastructure, Tooling & Operations** tasks in v0.4.27. This is a patch release focused on quick wins — no architecture changes, just completion of pending work.

**Total estimated effort**: ~6.5 hours

---

## Task 1: Secret Cleanup 🔒

**Priority**: P0 (Security)
**Estimated effort**: 1 hour
**Risk**: Medium (security risk if keys are real)

### Problem

- `dev/validator_keys.json:3` contains PEM private key material (even if dev key)
- Tracked-but-generated files: `contracts/cache/solidity-files-cache.json`, `pyproject.toml.new`

### Files Involved

- `dev/validator_keys.json` — contains PEM private key
- `contracts/cache/solidity-files-cache.json` — generated cache file
- `pyproject.toml.new` — generated file (likely from package manager)
- `.gitignore` — needs updates for generated files

### Steps

#### 1.1: Replace validator_keys.json with template

1. Read `dev/validator_keys.json` to understand its structure
2. Create `dev/validator_keys.json.template` with placeholder values:
   ```json
   {
     "validator_keys": [
       {
         "public_key": "PLACEHOLDER_PUBLIC_KEY",
         "private_key": "GENERATE_WITH_SCRIPT"
       }
     ]
   }
   ```
3. Create `dev/generate_validator_keys.py` script:
   ```python
   #!/usr/bin/env python3
   """Generate validator keys for development."""
   import json
   from pathlib import Path
   from cryptography.hazmat.primitives.asymmetric import rsa
   from cryptography.hazmat.primitives import serialization
   from cryptography.hazmat.backends import default_backend

   def generate_key_pair():
       private_key = rsa.generate_private_key(
           public_exponent=65537,
           key_size=2048,
           backend=default_backend()
       )

       private_pem = private_key.private_bytes(
           encoding=serialization.Encoding.PEM,
           format=serialization.PrivateFormat.PKCS8,
           encryption_algorithm=serialization.NoEncryption()
       )

       public_key = private_key.public_key()
       public_pem = public_key.public_bytes(
           encoding=serialization.Encoding.PEM,
           format=serialization.PublicFormat.SubjectPublicKeyInfo
       )

       return private_pem.decode(), public_pem.decode()

   def main():
       private_pem, public_pem = generate_key_pair()

       keys = {
           "validator_keys": [
               {
                   "public_key": public_pem,
                   "private_key": private_pem
               }
           ]
       }

       output_path = Path("dev/validator_keys.json")
       with open(output_path, "w") as f:
           json.dump(keys, f, indent=2)

       print(f"Generated keys at {output_path}")

   if __name__ == "__main__":
       main()
   ```
4. Delete the actual `dev/validator_keys.json` file
5. Add to `.gitignore`:
   ```
   # Generated validator keys
   dev/validator_keys.json
   dev/validator_keys.json.template
   ```

#### 1.2: Add ignore rules for generated files

Update `.gitignore`:
```
# Generated cache files
contracts/cache/solidity-files-cache.json

# Package manager generated files
pyproject.toml.new
*.pyc
__pycache__/
```

#### 1.3: Check git history for real keys

1. Check if real keys were ever committed:
   ```bash
   git log --all --full-history -- dev/validator_keys.json
   ```
2. If real keys were found, they must be removed from history:
   ```bash
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch dev/validator_keys.json" \
     --prune-empty --tag-name-filter cat -- --all
   ```
   **WARNING**: This rewrites history. Coordinate with team before doing this.

### Acceptance Criteria

- [ ] `dev/validator_keys.json` deleted from repository
- [ ] Template and generation script created
- [ ] Generated files added to `.gitignore`
- [ ] No committed PEM private keys in repository
- [ ] Git history checked for previous key commits

### Verification

```bash
# Check file is not tracked
git status dev/validator_keys.json

# Check gitignore works
git check-ignore -v dev/validator_keys.json

# Verify no keys in current HEAD
grep -r "BEGIN PRIVATE KEY" dev/
```

---

## Task 2: CI Alignment — Install Project Dependencies 🛡️

**Priority**: P1
**Estimated effort**: 1 hour
**Risk**: Low

### Problem

GitHub CI (`.github/workflows/ci.yml:18,51`) installs only tools (ruff, mypy, pytest) but not project dependencies before running checks. This means CI doesn't validate the actual project state.

### Files Involved

- `.github/workflows/ci.yml` — GitHub Actions workflow
- `pyproject.toml` — project dependencies
- `requirements.txt` or `poetry.lock` — dependency lock file

### Steps

#### 2.1: Read current CI workflow

Read `.github/workflows/ci.yml` to understand current setup:
- Look for steps that install tools
- Check if there's a step that installs project dependencies
- Identify where to add the dependency installation step

#### 2.2: Add dependency installation step

Add a step before running ruff/mypy/tests:

**If using pip**:
```yaml
- name: Install project dependencies
  run: |
    python -m pip install --upgrade pip
    pip install -e .
    pip install -r requirements-dev.txt  # if exists
```

**If using Poetry**:
```yaml
- name: Install Poetry
  run: pip install poetry

- name: Install project dependencies
  run: poetry install --with dev
```

**If using uv**:
```yaml
- name: Install uv
  run: pip install uv

- name: Install project dependencies
  run: uv sync --dev
```

#### 2.3: Verify the package manager

Check which package manager the project uses:
- Look for `pyproject.toml` with `[tool.poetry]` section → Poetry
- Look for `poetry.lock` file → Poetry
- Look for `uv.lock` file → uv
- Otherwise → pip

#### 2.4: Test locally

Before committing, test the CI workflow locally:
```bash
# Simulate CI environment
python -m pip install --upgrade pip
pip install -e .
pip install ruff mypy pytest pytest-cov

# Run the checks
ruff check aitbc/ apps/
mypy aitbc/ apps/
pytest tests/ --collect-only
```

### Acceptance Criteria

- [ ] CI installs project dependencies before running checks
- [ ] CI uses the same package manager as local development
- [ ] CI passes with dependency installation step
- [ ] No false negatives from missing dependencies

### Verification

```bash
# Push a test commit to verify CI works
git add .github/workflows/ci.yml
git commit -m "ci: install project dependencies before checks"
git push

# Check GitHub Actions results
```

---

## Task 3: ShellCheck in CI 🔧

**Priority**: P1
**Estimated effort**: 1 hour
**Risk**: Low

### Problem

Shell scripts have various issues (missing quoting, `cd` without checks). ShellCheck should be added to CI to catch these automatically.

### Files Involved

- `.github/workflows/ci.yml` — GitHub Actions workflow
- `scripts/service-management/stop-services.sh`
- `scripts/service-management/fix-services.sh`
- `scripts/workflow/*.sh` — various workflow scripts

### Steps

#### 3.1: Install ShellCheck in CI

Add to `.github/workflows/ci.yml`:
```yaml
- name: Install ShellCheck
  run: |
    wget -qO- "https://github.com/koalaman/shellcheck/releases/download/stable/shellcheck-stable.linux.x86_64.tar.xz" | tar xJ
    sudo mv shellcheck-stable/shellcheck /usr/bin/
    shellcheck --version

- name: Run ShellCheck
  run: |
    shellcheck scripts/**/*.sh
```

#### 3.2: Fix shell script issues

**For `scripts/service-management/stop-services.sh`**:
- Add quoting around variables: `"$var"` instead of `$var`

**For `scripts/service-management/fix-services.sh`**:
- Add error handling after `cd`: `cd /path || exit 1`

**For `scripts/workflow/*.sh`**:
- Fix various quoting issues
- Add `set -euo pipefail` at the top of each script

#### 3.3: Common shell script fixes

Add this shebang and options to all scripts:
```bash
#!/usr/bin/env bash
set -euo pipefail
```

Quote all variable expansions:
```bash
# BEFORE
service_name=$1

# AFTER
service_name="$1"
```

Add error handling after cd:
```bash
# BEFORE
cd /opt/aitbc

# AFTER
cd /opt/aitbc || exit 1
```

### Acceptance Criteria

- [ ] ShellCheck added to CI workflow
- [ ] All shell scripts pass ShellCheck
- [ ] Shell scripts have proper error handling
- [ ] Variables are properly quoted

### Verification

```bash
# Install ShellCheck locally
sudo apt-get install shellcheck  # or brew install shellcheck on macOS

# Run ShellCheck on all scripts
shellcheck scripts/**/*.sh

# Fix any issues found
```

---

## Task 4: Fix Shell Scripts 🔧

**Priority**: P1
**Estimated effort**: 1 hour
**Risk**: Low
**Dependency**: Should be done with Task 3

### Problem

Shell scripts have various issues that need to be fixed. This is the actual fixing work, while Task 3 adds the CI gate.

### Files to Fix

| Script | Issues | Fix |
|--------|--------|-----|
| `scripts/service-management/stop-services.sh` | Missing quoting | Add `"$var"` |
| `scripts/service-management/fix-services.sh` | `cd` without check | Add `|| exit` |
| `scripts/workflow/*.sh` | Various quoting | Batch fix |

### Steps

#### 4.1: Add standard header to all scripts

Add this to the top of every shell script:
```bash
#!/usr/bin/env bash
set -euo pipefail
```

#### 4.2: Quote all variables

Search and replace:
```bash
# Find unquoted variables
grep -n '\$[a-zA-Z_][a-zA-Z0-9_]*' scripts/**/*.sh

# Manually fix each one
```

#### 4.3: Add error handling after cd

```bash
# BEFORE
cd /opt/aitbc

# AFTER
cd /opt/aitbc || exit 1
```

#### 4.4: Test each script

After fixing, test each script:
```bash
bash -n scripts/service-management/stop-services.sh  # Syntax check
bash scripts/service-management/stop-services.sh --help  # Runtime check
```

### Acceptance Criteria

- [ ] All shell scripts have `set -euo pipefail`
- [ ] All variables are quoted
- [ ] All `cd` commands have error handling
- [ ] Scripts pass syntax check (`bash -n`)

### Verification

```bash
# Syntax check all scripts
find scripts/ -name "*.sh" -exec bash -n {} \;

# Run ShellCheck
shellcheck scripts/**/*.sh
```

---

## Task 5: detect-secrets in CI 🔒

**Priority**: P1
**Estimated effort**: 30 minutes
**Risk**: Low

### Problem

No automated secret scanning in CI. Commits may contain secrets that should be caught before merging.

### Files Involved

- `.github/workflows/ci.yml` — GitHub Actions workflow
- `.secrets.baseline` — detect-secrets baseline (if exists)

### Steps

#### 5.1: Install detect-secrets in CI

Add to `.github/workflows/ci.yml`:
```yaml
- name: Install detect-secrets
  run: pip install detect-secrets

- name: Run detect-secrets
  run: |
    detect-secrets scan --baseline .secrets.baseline || true

    # If no baseline exists, create one
    if [ ! -f .secrets.baseline ]; then
      detect-secrets scan > .secrets.baseline
      echo "Created initial baseline"
    else
      detect-secrets scan --baseline .secrets.baseline
    fi
```

#### 5.2: Create initial baseline

Run locally to create baseline:
```bash
pip install detect-secrets
detect-secrets scan > .secrets.baseline
```

Review the baseline and remove any actual secrets that should not be committed.

#### 5.3: Configure detect-secrets

Create `.secrets.baseline` configuration:
```json
{
  "version": "1.0",
  "plugins_used": [
    {
      "name": "Base64HighEntropyString",
      "limit": 4.5
    },
    {
      "name": "HexHighEntropyString",
      "limit": 3.0
    },
    {
      "name": "KeywordDetector",
      "keyword_filter": {
        "exclude": [
          "Client",
          "Token",
          "Secret"
        ]
      }
    }
  ],
  "exclude": {
    "files": [
      "tests/",
      "node_modules/",
      "*.pyc"
    ]
  }
}
```

### Acceptance Criteria

- [ ] detect-secrets added to CI workflow
- [ ] Initial baseline created
- [ ] CI fails on new secrets
- [ ] False positives excluded in baseline

### Verification

```bash
# Test locally
pip install detect-secrets
detect-secrets scan --baseline .secrets.baseline

# Test with a fake secret
echo "API_KEY=sk_test_12345" >> test_file.txt
detect-secrets scan test_file.txt
rm test_file.txt
```

---

## Task 6: Fix Ruff Warnings 🧹

**Priority**: P1
**Estimated effort**: 1 hour
**Risk**: Low

### Problem

Ruff has remaining warnings in non-excluded files. These should be fixed to improve code quality.

### Files Involved

- `pyproject.toml` — ruff configuration
- All Python files in `aitbc/`, `apps/`, `cli/`, `packages/`

### Steps

#### 6.1: Run ruff to see current warnings

```bash
ruff check aitbc/ apps/ cli/ packages/
```

#### 6.2: Categorize warnings

Common ruff warnings:
- `F401` — unused imports
- `F841` — unused variables
- `E501` — line too long
- `W291` — trailing whitespace
- `W293` — blank line contains whitespace

#### 6.3: Fix warnings automatically where possible

```bash
# Fix import sorting
ruff check --fix --select I aitbc/ apps/ cli/ packages/

# Fix unused imports
ruff check --fix --select F401 aitbc/ apps/ cli/ packages/

# Fix other auto-fixable issues
ruff check --fix aitbc/ apps/ cli/ packages/
```

#### 6.4: Manually fix remaining issues

For issues that can't be auto-fixed:
- Remove unused imports
- Remove unused variables
- Break long lines
- Remove trailing whitespace

#### 6.5: Update ruff configuration if needed

If certain warnings are not relevant, update `pyproject.toml`:
```toml
[tool.ruff]
# Exclude specific rules
ignore = [
    "E501",  # Line too long (if using formatter)
]
```

### Acceptance Criteria

- [ ] Ruff check passes with zero warnings
- [ ] No unused imports
- [ ] No unused variables
- [ ] Code is clean and consistent

### Verification

```bash
# Run ruff check
ruff check aitbc/ apps/ cli/ packages/

# Should exit with code 0 (no errors)
```

---

## Task 7: Refresh Architecture Docs 📚

**Priority**: P2
**Estimated effort**: 1 hour
**Risk**: Low

### Problem

Architecture docs don't match current codebase:
- `docs/architecture/8_codebase-structure.md:28` mentions top-level `systemd/` directory (doesn't exist)
- Documents apps like `marketplace-web`, `wallet-daemon`, `trade-exchange` that don't match current checkout
- `docs/architecture/active_apps.md:3` says v0.4.26 while root version is 0.6.0

### Files Involved

- `docs/architecture/8_codebase-structure.md`
- `docs/architecture/active_apps.md`
- `pyproject.toml` — to check current version

### Steps

#### 7.1: Inventory actual apps

List actual apps in the repository:
```bash
ls -la apps/
```

#### 7.2: Update 8_codebase-structure.md

1. Read the file to understand current structure
2. Remove references to non-existent `systemd/` directory
3. Update app list to match actual apps in `apps/`
4. Remove references to deleted apps (marketplace-web, wallet-daemon, trade-exchange)
5. Add any new apps that exist

#### 7.3: Update active_apps.md

1. Update version from v0.4.26 to current version (check `pyproject.toml`)
2. Update app list to match actual apps
3. Update any other outdated information

#### 7.4: Generate from metadata if possible

If there's a way to generate this from repo metadata, do that instead of manual updates.

### Acceptance Criteria

- [ ] Architecture docs match current codebase
- [ ] No references to non-existent directories
- [ ] App list is accurate
- [ ] Version references are correct

### Verification

```bash
# Check docs match reality
ls apps/  # Compare with docs

# Check version
grep version pyproject.toml  # Compare with docs
```

---

## Execution Order

1. **Task 1** (Secret cleanup) — Security first
2. **Task 2** (CI alignment) — Infrastructure foundation
3. **Task 3 + 4** (ShellCheck + fix scripts) — Can be done together
4. **Task 5** (detect-secrets) — Security gate
5. **Task 6** (Fix ruff warnings) — Code quality
6. **Task 7** (Refresh docs) — Documentation

---

## Common Requirements

### Testing

After each task, run:
```bash
# CI checks
ruff check aitbc/ apps/ cli/ packages/
mypy aitbc/ apps/
pytest tests/ --collect-only

# Shell script checks
shellcheck scripts/**/*.sh
```

### Git Workflow

After each task:
```bash
git add -A
git commit -m "fix: [task description]"
```

### Documentation

Update `docs/releases/v0.4.27/change.log` as tasks are completed:
- Mark tasks as ✅ done
- Add notes about any issues encountered
- Update acceptance criteria checkboxes

---

## Total Time Estimate

| Task | Effort |
|------|--------|
| Task 1: Secret cleanup | 1 hour |
| Task 2: CI alignment | 1 hour |
| Task 3: ShellCheck in CI | 1 hour |
| Task 4: Fix shell scripts | 1 hour |
| Task 5: detect-secrets in CI | 30 min |
| Task 6: Fix ruff warnings | 1 hour |
| Task 7: Refresh architecture docs | 1 hour |
| **Total** | **~6.5 hours** |

---

## Notes

- Tasks 3 and 4 can be done together (ShellCheck setup + fixing scripts)
- Tasks are independent and can be parallelized if needed
- All tasks are infrastructure/tooling focused, no application logic changes
- If blockers encountered, document in change.log and move to next task
