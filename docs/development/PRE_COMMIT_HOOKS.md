# Pre-Commit Hooks

This project uses pre-commit hooks to ensure code quality and consistency before commits.

## Installation

```bash
# Install pre-commit (if not already installed)
pip install pre-commit

# Install the hooks
pre-commit install

# Install pre-commit hooks for all files (optional)
pre-commit install --hook-type pre-push
```

## Usage

### Running hooks manually

```bash
# Run on all files
pre-commit run --all-files

# Run on staged files only (what happens during commit)
pre-commit run

# Run specific hooks
pre-commit run black flake8 mypy
```

### Automatic execution

Hooks run automatically on `git commit` for staged files. If a hook fails, the commit will be blocked. Fix the issues and try again.

To bypass hooks (not recommended):
```bash
git commit --no-verify
```

## Available Hooks

### Python
- **black**: Code formatting
- **flake8**: Linting (max line length: 120)
- **mypy**: Type checking
- **bandit**: Security scanning

### General
- **trailing-whitespace**: Remove trailing whitespace
- **end-of-file-fixer**: Ensure newline at end of file
- **check-yaml**: Validate YAML syntax
- **check-toml**: Validate TOML syntax
- **check-json**: Validate JSON syntax
- **check-added-large-files**: Prevent large files (>1MB)
- **detect-private-key**: Detect private keys in code
- **mixed-line-ending**: Ensure consistent line endings (LF)

### Configuration Files
- **yamllint**: YAML linting with custom config
- **markdownlint**: Markdown linting (excludes docs/archive)

### JavaScript/TypeScript
- **eslint**: JavaScript/TypeScript linting for packages/js and cli

### Shell Scripts
- **shellcheck**: Shell script linting

## Configuration

- **.pre-commit-config.yaml**: Main pre-commit configuration
- **.yamllint.yaml**: YAML linting rules

## Updating Hooks

```bash
# Update hook versions
pre-commit autoupdate

# Review changes
git diff .pre-commit-config.yaml
```

## Exclusions

Hooks exclude common directories:
- venv/, .venv/ (Python virtual environments)
- build/, dist/ (Build artifacts)
- docs/archive/ (Archived documentation)

## Troubleshooting

### Hook fails but you think it's wrong
Check the specific hook documentation and configuration. Some rules may need adjustment for the project.

### Pre-commit not running
Ensure hooks are installed:
```bash
pre-commit install
```

### Slow execution
Run hooks on specific files only:
```bash
pre-commit run <hook-name> <files...>
```
