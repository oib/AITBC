# Branch Protection Configuration Guide

## Overview

This document outlines the recommended branch protection settings for the AITBC repository to ensure code quality, security, and collaboration standards.

## GitHub Branch Protection Settings

### Main Branch Protection

Navigate to: `Settings > Branches > Branch protection rules`

#### Create Protection Rule for `main`

**Branch name pattern**: `main`

**Require status checks to pass before merging**
- ✅ Require branches to be up to date before merging
- ✅ Require status checks to pass before merging

**Required status checks**
- ✅ Lint (ruff)
- ✅ Check .env.example drift
- ✅ Test (pytest)
- ✅ contracts-ci / Lint
- ✅ contracts-ci / Slither Analysis
- ✅ contracts-ci / Compile
- ✅ contracts-ci / Test
- ✅ dotenv-check / dotenv-validation
- ✅ dotenv-check / dotenv-security
- ✅ security-scanning / bandit
- ✅ security-scanning / codeql
- ✅ security-scanning / safety
- ✅ security-scanning / trivy
- ✅ security-scanning / ossf-scorecard

**Require pull request reviews before merging**
- ✅ Require approvals
  - **Required approving reviews**: 2
- ✅ Dismiss stale PR approvals when new commits are pushed
- ✅ Require review from CODEOWNERS
- ✅ Require review from users with write access in the target repository
- ✅ Limit the number of approvals required (2) - **Do not allow users with write access to approve their own pull requests**

**Restrict pushes**
- ✅ Limit pushes to users who have write access in the repository
- ✅ Do not allow force pushes

**Restrict deletions**
- ✅ Do not allow users with write access to delete matching branches

**Require signed commits**
- ✅ Require signed commits (optional, for enhanced security)

### Develop Branch Protection

**Branch name pattern**: `develop`

**Settings** (same as main, but with fewer required checks):
- Require status checks to pass before merging
- Required status checks: Lint, Test, Check .env.example drift
- Require pull request reviews before merging (1 approval)
- Limit pushes to users with write access
- Do not allow force pushes

## Required Status Checks Configuration

### Continuous Integration Checks

| Status Check | Description | Workflow |
|-------------|-------------|----------|
| `Lint (ruff)` | Python code linting | `.github/workflows/ci.yml` |
| `Check .env.example drift` | Configuration drift detection | `.github/workflows/ci.yml` |
| `Test (pytest)` | Python unit tests | `.github/workflows/ci.yml` |
| `contracts-ci / Lint` | Solidity linting | `.github/workflows/contracts-ci.yml` |
| `contracts-ci / Slither Analysis` | Solidity security analysis | `.github/workflows/contracts-ci.yml` |
| `contracts-ci / Compile` | Smart contract compilation | `.github/workflows/contracts-ci.yml` |
| `contracts-ci / Test` | Smart contract tests | `.github/workflows/contracts-ci.yml` |
| `dotenv-check / dotenv-validation` | .env.example format validation | `.github/workflows/dotenv-check.yml` |
| `dotenv-check / dotenv-security` | .env.example security check | `.github/workflows/dotenv-check.yml` |
| `security-scanning / bandit` | Python security scanning | `.github/workflows/security-scanning.yml` |
| `security-scanning / codeql` | CodeQL analysis | `.github/workflows/security-scanning.yml` |
| `security-scanning / safety` | Dependency vulnerability scan | `.github/workflows/security-scanning.yml` |
| `security-scanning / trivy` | Container security scan | `.github/workflows/security-scanning.yml` |
| `security-scanning / ossf-scorecard` | OSSF Scorecard analysis | `.github/workflows/security-scanning.yml` |

### Additional Checks for Feature Branches

For feature branches, consider requiring:
- `comprehensive-tests / unit-tests`
- `comprehensive-tests / integration-tests`
- `comprehensive-tests / api-tests`
- `comprehensive-tests / blockchain-tests`

## CODEOWNERS Integration

The branch protection should be configured to require review from CODEOWNERS. This ensures that:

1. **Domain experts review relevant changes**
2. **Security team reviews security-sensitive files**
3. **Core team reviews core functionality**
4. **Specialized teams review their respective areas**

### CODEOWNERS Rules Integration

```bash
# Security files require security team review
/security/ @aitbc/security-team
*.pem @aitbc/security-team

# Smart contracts require Solidity team review
/contracts/ @aitbc/solidity-team
*.sol @aitbc/solidity-team

# CLI changes require CLI team review
/cli/ @aitbc/cli-team
aitbc_cli/ @aitbc/cli-team

# Core files require core team review
pyproject.toml @aitbc/core-team
poetry.lock @aitbc/core-team
```

## Pre-commit Hooks Integration

Branch protection works best with pre-commit hooks:

### Required Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-toml
      - id: check-merge-conflict

  - repo: https://github.com/psf/black
    rev: 24.3.0
    hooks:
      - id: black
        language_version: python3.13

  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.1.15
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        args: [--ignore-missing-imports]

  - repo: local
    hooks:
      - id: dotenv-linter
        name: dotenv-linter
        entry: python scripts/focused_dotenv_linter.py
        language: system
        args: [--check]
        pass_filenames: false
```

## Workflow Status Checks

### CI Workflow Status

The CI workflows should be configured to provide clear status checks:

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: ["**"]
  pull_request:
    branches: ["**"]

jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip poetry
          poetry config virtualenvs.create false
          poetry install --no-interaction --no-ansi
      
      - name: Lint (ruff)
        run: poetry run ruff check .
      
      - name: Check .env.example drift
        run: python scripts/focused_dotenv_linter.py --check
      
      - name: Test (pytest)
        run: poetry run pytest --cov=aitbc_cli --cov-report=term-missing --cov-report=xml
```

## Security Best Practices

### Commit Signing

Consider requiring signed commits for enhanced security:

```bash
# Configure GPG signing
git config --global commit.gpgsign true
git config --global user.signingkey YOUR_GPG_KEY_ID
```

### Merge Methods

Configure merge methods for different branches:

- **Main branch**: Require squash merge with commit message validation
- **Develop branch**: Allow merge commits with proper PR description
- **Feature branches**: Allow any merge method

### Release Branch Protection

For release branches (e.g., `release/v1.0.0`):

- Require all status checks
- Require 3 approving reviews
- Require review from release manager
- Require signed commits
- Do not allow force pushes or deletions

## Enforcement Policies

### Gradual Rollout

1. **Phase 1**: Enable basic protection (no force pushes, require PR reviews)
2. **Phase 2**: Add status checks for linting and testing
3. **Phase 3**: Add security scanning and comprehensive checks
4. **Phase 4**: Enable CODEOWNERS and signed commits

### Exception Handling

Create a process for emergency bypasses:

1. **Emergency changes**: Allow bypass with explicit approval
2. **Hotfixes**: Temporary reduction in requirements
3. **Documentation**: All bypasses must be documented

### Monitoring and Alerts

Set up monitoring for:

- Failed status checks
- Long-running PRs
- Bypass attempts
- Reviewer availability

## Configuration as Code

### GitHub Configuration

Use GitHub's API or Terraform to manage branch protection:

```hcl
# Terraform example
resource "github_branch_protection" "main" {
  repository_id = github_repository.aitbc.node_id
  pattern        = "main"

  required_status_checks {
    strict   = true
    contexts = [
      "Lint (ruff)",
      "Check .env.example drift",
      "Test (pytest)",
      "contracts-ci / Lint",
      "contracts-ci / Slither Analysis",
      "contracts-ci / Compile",
      "contracts-ci / Test"
    ]
  }

  required_pull_request_reviews {
    required_approving_review_count = 2
    dismiss_stale_reviews          = true
    require_code_owner_reviews     = true
  }

  enforce_admins = true
}
```

## Testing Branch Protection

### Validation Tests

Create tests to validate branch protection:

```python
def test_branch_protection_config():
    """Test that branch protection is properly configured"""
    # Test main branch protection
    main_protection = get_branch_protection("main")
    assert main_protection.required_status_checks == EXPECTED_CHECKS
    assert main_protection.required_approving_review_count == 2
    
    # Test develop branch protection
    develop_protection = get_branch_protection("develop")
    assert develop_protection.required_approving_review_count == 1
```

### Integration Tests

Test that workflows work with branch protection:

```python
def test_pr_with_branch_protection():
    """Test PR flow with branch protection"""
    # Create PR
    pr = create_pull_request()
    
    # Verify status checks run
    assert "Lint (ruff)" in pr.status_checks
    assert "Test (pytest)" in pr.status_checks
    
    # Verify merge is blocked until checks pass
    assert pr.mergeable == False
```

## Troubleshooting

### Common Issues

1. **Status checks not appearing**: Ensure workflows have proper names
2. **CODEOWNERS not working**: Verify team names and permissions
3. **Pre-commit hooks failing**: Check hook configuration and dependencies
4. **Merge conflicts**: Enable branch up-to-date requirements

### Debugging Commands

```bash
# Check branch protection settings
gh api repos/aitbc/aitbc/branches/main/protection

# Check required status checks
gh api repos/aitbc/aitbc/branches/main/protection/required_status_checks

# Check CODEOWNERS rules
gh api repos/aitbc/aitbc/contents/CODEOWNERS

# Check recent workflow runs
gh run list --branch main
```

## Documentation and Training

### Team Guidelines

Create team guidelines for:

1. **PR creation**: How to create compliant PRs
2. **Review process**: How to conduct effective reviews
3. **Bypass procedures**: When and how to request bypasses
4. **Troubleshooting**: Common issues and solutions

### Onboarding Checklist

New team members should be trained on:

1. Branch protection requirements
2. Pre-commit hook setup
3. CODEOWNERS review process
4. Status check monitoring

## Conclusion

Proper branch protection configuration ensures code quality, security, and collaboration standards. By implementing these settings, the AITBC repository maintains high standards while enabling efficient development workflows.

Regular review and updates to branch protection settings ensure they remain effective as the project evolves.
